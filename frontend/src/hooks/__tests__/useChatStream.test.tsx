import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import useChatStream from "../useChatStream";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function sseResponse(payload: string) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

const FULL_STREAM =
  'event: status\ndata: {"content":"Plot review is in progress...","seq":1}\n\n' +
  'event: status\ndata: {"content":"Report writing complete.","seq":2}\n\n' +
  'event: zip_ready\ndata: {"folder_name":"uploads/output/plot_review/2026-01-01"}\n\n' +
  'event: text\ndata: {"content":"審查完成"}\n\n' +
  'event: result\ndata: {"intent":"plot_review","data":{"review_result":[{"file_name":"a.png","feedback":"字太小"}]}}\n\n' +
  'event: saved\ndata: {"message_id":321}\n\n';

describe("useChatStream", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("accumulates trace entries rather than overwriting them", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(FULL_STREAM)));
    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });

    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "審查" });
    });

    expect(result.current.trace.map((s) => s.seq)).toEqual([1, 2]);
    expect(result.current.trace[0].raw).toContain("Plot review");
  });

  it("receives the structured data from a result event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(FULL_STREAM)));
    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });

    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "審查" });
    });

    expect(result.current.resultBlock?.intent).toBe("plot_review");
    expect(result.current.resultBlock?.data.review_result?.[0].file_name).toBe("a.png");
  });

  it("receives the real message_id from a saved event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(FULL_STREAM)));
    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });

    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "審查" });
    });

    expect(result.current.savedMessageId).toBe(321);
  });

  it("receives the folder from a zip_ready event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(FULL_STREAM)));
    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });

    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "審查" });
    });

    expect(result.current.zipFolder).toBe("uploads/output/plot_review/2026-01-01");
  });

  it("writes a backend error event into streamError without calling alert", async () => {
    const alertSpy = vi.fn();
    vi.stubGlobal("alert", alertSpy);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(
      'event: error\ndata: {"content":"LangGraph 崩潰"}\n\n')));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" });
    });

    expect(result.current.streamError).toContain("LangGraph 崩潰");
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it("keeps the trace received so far after an abort, and sets streamError to error.streamAborted", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(encoder.encode(
          'event: status\ndata: {"content":"Plot review is in progress...","seq":1}\n\n'));
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        // A real SSE response always carries this header; the hook uses it
        // to distinguish "streaming" from "the duplicate-request
        // short-circuit's application/json".
        headers: { "Content-Type": "text/event-stream" },
      })));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    const pending = result.current.sendMutation.mutateAsync({ message: "x" });

    await waitFor(() => expect(result.current.trace.length).toBe(1));

    // After abort(), mutationFn still has to finish running through
    // catch/finally before it truly settles, and that continuation happens
    // in a microtask outside act()'s scope. Wrapping both the abort() call
    // and the wait for settlement in the same async act() lets React flush
    // every state update from this whole sequence before we read
    // result.current, avoiding a read of a not-yet-committed stale snapshot
    // (and avoiding an act() warning).
    await act(async () => {
      result.current.abort();
      await pending.catch(() => {});
    });

    expect(result.current.trace.length).toBe(1);
    expect(result.current.streamError).toBe("error.streamAborted");
  });

  it("sets streamError to error.emptyResponse when the stream ends having received nothing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse("")));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" });
    });

    expect(result.current.streamError).toBe("error.emptyResponse");
  });

  // `chat.py`'s "duplicate-request short-circuit": when the same message
  // was just answered, the backend does not rerun the agent — it returns
  // application/json (not SSE) with not a single `event:` line. Without
  // special handling, this wrongly trips the emptyResponse check and shows
  // the physician "no reply was received this time, please retry", and
  // retrying hits the same path again, an infinite loop. Hit in practice,
  // hence pinned here.
  it("is duplicateRequest, not emptyResponse, when the backend returns application/json (duplicate-request short-circuit)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "success", thread_id: "th-1",
        AI_messages: [{ type: "text", text: "先前的回答" }],
      }), { status: 200, headers: { "Content-Type": "application/json" } })));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" });
    });

    expect(result.current.streamError).toBe("error.duplicateRequest");
  });

  // An HTTP/network-layer failure (before the SSE loop is even reached)
  // must still surface a signal to the user — it must not go silent as
  // "nothing happens after submit".
  it("carries the backend's detail in streamError rather than staying silent when the backend returns HTTP 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "伺服器內部錯誤" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" }).catch(() => {});
    });

    expect(result.current.streamError).toContain("伺服器內部錯誤");
  });

  // On a dropped connection, `fetch` throws `TypeError("Failed to fetch")`,
  // which is still an Error. An implementation using `e.message` would pop
  // an untranslated English technical string in front of a physician on
  // the Chinese interface, so this asserts the i18n key rather than just a
  // truthy value.
  it("sets streamError to error.network, not the raw English text, when the connection drops (fetch throws TypeError)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" }).catch(() => {});
    });

    expect(result.current.streamError).toBe("error.network");
  });

  // The pure-function continuation test for parseSseChunks
  // (sse.test.ts) only verifies "the function's return value is correct" —
  // it doesn't guarantee the hook actually feeds `rest` back into `buffer`.
  // This test uses two enqueue calls to simulate an event genuinely split
  // across a real network packet boundary, verifying end-to-end that the
  // hook really does `buffer = rest`.
  it("still stitches an event back together correctly when it's split across two network chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(encoder.encode(
          'event: status\ndata: {"content":"Plot review is in prog'));
        c.enqueue(encoder.encode('ress...","seq":1}\n\n'));
        c.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        // A real SSE response always carries this header; the hook uses it
        // to distinguish "streaming" from "the duplicate-request
        // short-circuit's application/json".
        headers: { "Content-Type": "text/event-stream" },
      })));

    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });
    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "x" });
    });

    expect(result.current.trace).toHaveLength(1);
    expect(result.current.trace[0]).toEqual({
      seq: 1,
      raw: "Plot review is in progress...",
    });
  });

  // `prev_ms` on a later `status` event closes the *previous* step,
  // and `saved`'s `last_ms` closes the final one. Both are additive to the
  // existing payload shape (see backend/tests/test_trace_durations.py).
  it("stamps prev_ms and last_ms onto the closed steps' ms field", async () => {
    const stream =
      'event: status\ndata: {"content":"Parameter extraction complete, statistical analysis in progress.","seq":1}\n\n' +
      'event: status\ndata: {"content":"Summary complete! Ready to download.","seq":2,"prev_ms":432}\n\n' +
      'event: text\ndata: {"content":"分析完成"}\n\n' +
      'event: saved\ndata: {"message_id":9,"last_ms":22300}\n\n';

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(stream)));
    const { result } = renderHook(() => useChatStream("th-1"), { wrapper });

    await act(async () => {
      await result.current.sendMutation.mutateAsync({ message: "分析" });
    });

    expect(result.current.trace).toEqual([
      { seq: 1, raw: "Parameter extraction complete, statistical analysis in progress.", ms: 432 },
      { seq: 2, raw: "Summary complete! Ready to download.", ms: 22300 },
    ]);
  });
});
