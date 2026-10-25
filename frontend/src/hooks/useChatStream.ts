// useChatStream.ts
import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChatRequest } from "@/src/types/type";
import { chatQueryKeys } from "@/src/queryKeys/chat";
import type { ResultBlockData, TraceStep } from "@/src/types/results";
import { ApiError, apiFetch } from "@/src/lib/apiClient";
import { parseSseChunks } from "@/src/lib/sse";

export type ResultBlock = { intent: string | null; data: ResultBlockData };

/**
 * Temporary id used for the optimistic update. `onSuccess` invalidates the
 * history query and triggers a refetch, at which point this temporary entry
 * is replaced by the backend-returned message carrying a real id.
 */
export const PENDING_MESSAGE_ID = -1;

export default function useChatStream(urlId: string) {
  const queryClient = useQueryClient();
  const [streamingText, setStreamingText] = useState("");
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [zipFolder, setZipFolder] = useState<string | null>(null);
  const [resultBlock, setResultBlock] = useState<ResultBlock | null>(null);
  const [savedMessageId, setSavedMessageId] = useState<number | null>(null);
  // `streamError` carries two different kinds of string: (1) an i18n key
  // (e.g. "error.streamAborted", "error.emptyResponse") that the caller
  // must run through `t()`; (2) the backend `error` event's own
  // human-readable text (e.g. an "agent crashed" message), which has no
  // matching i18n key and should just be displayed as-is. The consumer
  // (ChatWindow.tsx's `resolveStreamErrorText`) distinguishes the two with
  // an explicit `error.`-prefix check rather than calling `t()`
  // unconditionally: `t()` does fall back to echoing an unmatched key
  // unchanged, but it also calls `console.warn` on every miss
  // (LocaleContext.tsx), which would fire on every backend-supplied detail
  // string if this were rendered through a bare `t(streamError)`.
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const sendMutation = useMutation({
    mutationFn: async (payload: ChatRequest) => {
      setStreamingText("");
      setTrace([]);
      setResultBlock(null);
      setSavedMessageId(null);
      setStreamError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      let fullText = "";
      let collectedResult: ResultBlock | null = null;
      let collectedTrace: TraceStep[] = [];
      // The backend has explicitly closed out this generation (via `error`
      // or `saved`): even with no text/result/trace, that does not count as
      // "received nothing" and must not be overridden by the emptyResponse
      // check below.
      let receivedTerminalSignal = false;

      try {
        // The `apiFetch` call and the body check are both inside this try:
        // a non-2xx HTTP response (`apiFetch` throws `ApiError`) and a
        // dropped connection (fetch rejects outright) must both reach the
        // same catch below and set `streamError`. The whole class of
        // "failed before the SSE loop even started" (expired 401 token,
        // 500, dropped connection, rate limiting) must not go silent — this
        // is the same "nothing happens after submit" silent failure that
        // the rest of the send path guards against, just at a different
        // failure point.
        const response = await apiFetch(`/api/chat/${urlId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: payload.message,
            file_path: payload.file_path,
          }),
          signal: controller.signal,
        });

        // `chat.py` has a "duplicate-request short-circuit": if the two
        // most recent messages are [assistant, user] and the user content
        // matches this request, the same message was just answered, and the
        // backend does not rerun the agent — it returns `application/json`
        // (`{status, thread_id, AI_messages}`) instead of SSE. That path has
        // not a single `event:` line, so the loop below receives nothing,
        // which would wrongly trip the emptyResponse check and show the
        // physician "no reply was received this time, please retry" — and
        // retrying would hit the exact same path again, an infinite loop.
        // The existing answer is already in history (`onSuccess` invalidates
        // and refetches it), so all this needs to do is return early without
        // reporting an error.
        const contentType = response.headers.get("content-type") ?? "";
        if (!contentType.includes("text/event-stream")) {
          setStreamError("error.duplicateRequest");
          return { text: "", result: null, trace: [] as TraceStep[] };
        }

        if (!response.body) throw new Error("後端未正確啟用 Stream 傳輸");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // `apiFetch` calls the browser's real fetch underneath; when
        // aborted, the browser rejects its own body reader along with it —
        // but the fetch stubbed in tests ignores `signal` entirely, so
        // `reader.read()` would hang forever. `Promise.race` lets the abort
        // signal actively interrupt a pending `read()`, so both scenarios
        // (real fetch / test stub) abort correctly.
        let rejectOnAbort!: (reason: unknown) => void;
        const aborted = new Promise<never>((_, reject) => {
          rejectOnAbort = reject;
        });
        const onAbort = () => {
          rejectOnAbort(new DOMException("Aborted", "AbortError"));
          reader.cancel().catch(() => {});
        };
        controller.signal.addEventListener("abort", onAbort);

        try {
          while (true) {
            const { value, done } = await Promise.race([reader.read(), aborted]);
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const { events, rest } = parseSseChunks(buffer);
            buffer = rest;

            for (const { event, data } of events) {
              const d = data as Record<string, unknown>;

              if (event === "status") {
                // `prev_ms` closes the interval for the *previous* step
                // (this event announces the next one starting), so stamp
                // it onto the last collected step before appending the new
                // one. Both the array update and the new step go through
                // the same setTrace call below, so the live UI never shows
                // durations one render behind.
                if (typeof d.prev_ms === "number" && collectedTrace.length > 0) {
                  const lastIdx = collectedTrace.length - 1;
                  collectedTrace = [
                    ...collectedTrace.slice(0, lastIdx),
                    { ...collectedTrace[lastIdx], ms: d.prev_ms },
                  ];
                }
                const step: TraceStep = {
                  seq: typeof d.seq === "number" ? d.seq : collectedTrace.length + 1,
                  raw: String(d.content ?? ""),
                };
                collectedTrace = [...collectedTrace, step];
                setTrace(collectedTrace);
              } else if (event === "text") {
                fullText += String(d.content ?? "");
                setStreamingText(fullText);
              } else if (event === "result") {
                collectedResult = {
                  intent: (d.intent as string) ?? null,
                  data: (d.data as ResultBlockData) ?? {},
                };
                setResultBlock(collectedResult);
              } else if (event === "saved") {
                if (typeof d.message_id === "number") setSavedMessageId(d.message_id);
                // `last_ms` closes the final step — there is no further
                // status event to do it, so `saved` (the stream's own
                // closing signal) carries it instead.
                if (typeof d.last_ms === "number" && collectedTrace.length > 0) {
                  const lastIdx = collectedTrace.length - 1;
                  collectedTrace = [
                    ...collectedTrace.slice(0, lastIdx),
                    { ...collectedTrace[lastIdx], ms: d.last_ms },
                  ];
                  setTrace(collectedTrace);
                }
                receivedTerminalSignal = true;
              } else if (event === "zip_ready") {
                setZipFolder(String(d.folder_name ?? ""));
              } else if (event === "error") {
                setStreamError(String(d.content ?? ""));
                receivedTerminalSignal = true;
              }
            }
          }
        } finally {
          controller.signal.removeEventListener("abort", onAbort);
        }
      } catch (e) {
        // Abort, non-2xx HTTP, or a dropped connection: keep whatever trace
        // was already received and let the UI show a retryable error card.
        if (e instanceof DOMException && e.name === "AbortError") {
          setStreamError("error.streamAborted");
        } else if (e instanceof ApiError) {
          // An explicit error from the backend: `detail` is already
          // display-ready Chinese (e.g. a "conversation not found"
          // message).
          setStreamError(e.detail);
        } else {
          // Everything else falls back to the i18n "cannot connect"
          // message. The most common case here is actually the
          // `TypeError("Failed to fetch")` the browser throws on a dropped
          // connection — it's still an Error, so using `e.message` would
          // print an untranslated English technical string on the Chinese
          // interface in front of a physician.
          setStreamError("error.network");
        }
        throw e;
      } finally {
        abortRef.current = null;
      }

      // A theoretical edge case: the agent returns normally, but there is no
      // text reply, the structured result was filtered out, there is no
      // status at all, and there is no error/saved closing signal either
      // (in which case the backend persisted nothing at all). The mutation
      // resolves normally, and without handling this, the user would just
      // see "submitted, and nothing happened" with no clue why.
      if (!fullText && !collectedResult && collectedTrace.length === 0 && !receivedTerminalSignal) {
        setStreamError("error.emptyResponse");
      }

      return { text: fullText, result: collectedResult, trace: collectedTrace };
    },

    onMutate: async (newChat) => {
      await queryClient.cancelQueries({ queryKey: chatQueryKeys.history(urlId) });
      const previousHistory = queryClient.getQueryData(chatQueryKeys.history(urlId));

      // Optimistic update: push the user's message to the top the instant
      // it's clicked, so the UI gives immediate feedback.
      queryClient.setQueryData(chatQueryKeys.history(urlId), (old: unknown) => [
        ...((old as unknown[]) || []),
        {
          id: PENDING_MESSAGE_ID,
          role: "user",
          content: [{ type: "text", text: newChat.message }],
          created_at: new Date().toISOString(),
        },
      ]);

      setZipFolder(null);
      return { previousHistory };
    },

    onError: (_err, _newChat, context) => {
      // No alert(): errors are presented via streamError + ErrorCard.
      queryClient.setQueryData(chatQueryKeys.history(urlId), context?.previousHistory);
    },

    onSuccess: () => {
      // The backend has already written the content blocks (including
      // result and trace) to the DB, so refetching history is enough to get
      // the real id — only then can the physician's rating attach to it.
      // No more optimistically inserting a message with a fake id.
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.history(urlId) });
    },

    onSettled: () => {
      // Refresh the list (e.g. an updated sidebar chat title). Note: this
      // does not clear the trace — the physician still needs to see the run
      // that just finished after the reply completes.
      queryClient.invalidateQueries({ queryKey: chatQueryKeys.list() });
      setStreamingText("");
    },
  });

  return {
    sendMutation,
    streamingText,
    trace,
    latestStatus: trace.length ? trace[trace.length - 1].raw : "",
    zipFolder,
    setZipFolder,
    resultBlock,
    savedMessageId,
    streamError,
    abort,
  };
}
