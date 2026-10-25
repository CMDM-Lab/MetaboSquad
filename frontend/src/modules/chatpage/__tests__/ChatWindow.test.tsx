import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import useChatStream from "@/src/hooks/useChatStream";
import ChatWindow from "../ChatWindow";

const paramsMock = vi.fn();
const searchParamsMock = vi.fn();
const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => paramsMock(),
  useSearchParams: () => searchParamsMock(),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}));

const historyReturnMock = vi.fn();
vi.mock("@/src/hooks/UseQueryHistory", () => ({
  default: () => historyReturnMock(),
}));

vi.mock("@/src/hooks/UseQueryChatList", () => ({
  default: () => ({ data: { chats: [] } }),
}));

vi.mock("@/src/hooks/useChatStream", () => ({
  default: vi.fn(),
}));

// Integration-test scope only: verifying *which panel* a result lands in
// (layout B's routing) does not need ResultCard's own artifacts fetch.
vi.mock("@/src/modules/results/ResultCard", () => ({
  default: ({ intent }: { intent: string | null }) => (
    <div data-testid="result-card">{intent}</div>
  ),
}));

const mockedUseChatStream = vi.mocked(useChatStream);

// jsdom does not implement scrollIntoView; ChatWindow's auto-scroll effect calls it on mount.
Element.prototype.scrollIntoView = vi.fn();

type ChatStreamReturn = ReturnType<typeof useChatStream>;
type HistoryMessageFixture = { id?: number; role: string; content: unknown };

/** next/navigation's ReadonlyURLSearchParams only needs `.get()` in tests. */
function makeSearchParams(entries: Record<string, string>) {
  return { get: (key: string) => entries[key] ?? null } as unknown as ReturnType<
    typeof searchParamsMock
  >;
}

/**
 * Packages a fake useChatStream() return value. `mutate` defaults to
 * mimicking a real react-query mutation by synchronously firing the
 * caller's `onSettled` — this is how the sendGuardRef regression test below
 * proves ChatWindow really hangs its unlock off `onSettled`.
 */
function makeStreamReturn(overrides: {
  streamError?: string | null;
  mutate?: ReturnType<typeof vi.fn>;
  isPending?: boolean;
  trace?: ChatStreamReturn["trace"];
  streamingText?: string;
} = {}) {
  const mutate =
    overrides.mutate ??
    vi.fn((_payload: unknown, options?: { onSettled?: () => void }) => {
      options?.onSettled?.();
    });

  return {
    sendMutation: { isPending: overrides.isPending ?? false, mutate },
    streamingText: overrides.streamingText ?? "",
    trace: overrides.trace ?? [],
    latestStatus: "",
    zipFolder: null,
    setZipFolder: vi.fn(),
    resultBlock: null,
    savedMessageId: null,
    streamError: overrides.streamError ?? null,
    abort: vi.fn(),
  } as unknown as ChatStreamReturn;
}

function aiMessage(text: string, id = 1): HistoryMessageFixture {
  return { id, role: "assistant", content: [{ type: "text", text }] };
}

function renderThread(opts: {
  messages?: HistoryMessageFixture[];
  searchParams?: Record<string, string>;
  streamError?: string | null;
  streamOverrides?: Parameters<typeof makeStreamReturn>[0];
} = {}) {
  paramsMock.mockReturnValue({ id: "th-1" });
  searchParamsMock.mockReturnValue(
    makeSearchParams(opts.searchParams ?? {}),
  );
  historyReturnMock.mockReturnValue({ data: opts.messages ?? [], isLoading: false });

  const stream = makeStreamReturn({ streamError: opts.streamError ?? null, ...opts.streamOverrides });
  mockedUseChatStream.mockReturnValue(stream);

  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  // Re-invokes the JSX factory on rerender (rather than reusing one
  // element reference) — React bails out of re-rendering a top-level
  // element it sees is referentially unchanged, so a mocked hook's new
  // return value would never actually reach the screen otherwise.
  const buildUi = () => (
    <QueryClientProvider client={qc}>
      <LocaleProvider><ChatWindow /></LocaleProvider>
    </QueryClientProvider>
  );
  const utils = render(buildUi());
  return { ...utils, rerenderWindow: () => utils.rerender(buildUi()), stream };
}

describe("ChatWindow", () => {
  beforeEach(() => {
    routerPush.mockClear();
  });

  // The wrap is the responsive rule. The row is flex-wrap with
  // a 520px conversation floor and a 380px panel floor — no media query, no
  // JS width measurement. At iPad width the panel drops below the
  // conversation instead of crushing it. Asserting the declarations is the
  // only way jsdom can see this; a media-query implementation would pass a
  // visual check at 1440 and fail silently at 768.
  it("the body row wraps rather than crushing the conversation", () => {
    renderThread();
    const row = screen.getByTestId("thread-body");
    expect(row).toHaveStyle({ flexWrap: "wrap", alignContent: "flex-start" });
    expect(screen.getByTestId("thread-convo")).toHaveStyle({
      flex: "1 1 520px", minWidth: "min(100%, 520px)",
    });
  });

  // Justified CJK at a narrow measure breaks tokens like `|log₂FC| > 1`
  // across lines. The assistant turn is start-aligned on purpose.
  it("assistant turns are start-aligned, not justified", () => {
    renderThread({ messages: [aiMessage("|log₂FC| > 1")] });
    expect(screen.getByText(/log₂FC/)).toHaveStyle({ textAlign: "start" });
  });

  // sendGuardRef unlock regression. This bug once went uncaught for a long
  // time — its effect is "after the first message sends, nothing else ever
  // sends again", which is enough to stall an entire session. If someone removes the onSettled unlock (or forgets to pass it
  // to mutate), this test must go red.
  it("sending two messages in a row both really call mutate (sendGuardRef unlock regression)", async () => {
    const { stream } = renderThread();

    const input = screen.getByPlaceholderText(/輸入訊息/);

    await userEvent.type(input, "第一則訊息");
    await userEvent.click(screen.getByRole("button", { name: "送出" }));

    await userEvent.type(input, "第二則訊息");
    await userEvent.click(screen.getByRole("button", { name: "送出" }));

    expect(stream.sendMutation.mutate).toHaveBeenCalledTimes(2);
    expect(stream.sendMutation.mutate).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ message: "第一則訊息" }),
      expect.anything(),
    );
    expect(stream.sendMutation.mutate).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ message: "第二則訊息" }),
      expect.anything(),
    );
  });

  // An aborted stream and a genuine error must render differently. If a
  // real backend error is ever mistaken for a user-initiated abort, it would
  // be silently swallowed behind a grey notice with no retry — the physician
  // thinks the run succeeded when that turn actually failed.
  describe("streamError routing", () => {
    it("a user-initiated abort (error.streamAborted) renders a neutral notice, not a red error card, with no retry button", () => {
      renderThread({ streamError: "error.streamAborted" });

      const notice = screen.getByRole("alert");
      expect(notice).toHaveTextContent(zh["chat.stopped"]);
      expect(notice).toHaveClass("border-divider", "bg-neutral-100");
      expect(notice).not.toHaveClass("border-accent-300", "bg-accent-100");
      expect(screen.queryByRole("button", { name: zh["error.retry"] })).not.toBeInTheDocument();
    });

    // This and the streamAborted test above both route through the exact
    // same `<ErrorCard tone="notice">` call site in ChatWindow.tsx — there
    // is no second call site to "correctly stay green" on its own. Without
    // the class assertions, flipping that one call site's tone to "error"
    // would render this as a red card with the text and retry-absence
    // assertions both still trivially true (onRetry is never passed here,
    // so "no retry button" holds under either tone) — the tone itself was
    // never actually checked.
    it("the backend's duplicate-request short-circuit also renders as a neutral notice with no retry button", () => {
      renderThread({ streamError: "error.duplicateRequest" });

      const notice = screen.getByRole("alert");
      expect(notice).toHaveTextContent(zh["error.duplicateRequest"]);
      expect(notice).toHaveClass("border-divider", "bg-neutral-100");
      expect(notice).not.toHaveClass("border-accent-300", "bg-accent-100");
      expect(screen.queryByRole("button", { name: zh["error.retry"] })).not.toBeInTheDocument();
    });

    it("any other i18n-key error (error.network) renders the red error card with a retry button", () => {
      renderThread({ streamError: "error.network" });

      const card = screen.getByRole("alert");
      expect(card).toHaveTextContent(zh["error.network"]);
      expect(card).toHaveClass("border-accent-300", "bg-accent-100");
      expect(screen.getByRole("button", { name: zh["error.retry"] })).toBeInTheDocument();
    });

    it("a backend ApiError's Chinese detail (not an i18n key) renders as-is, without a console.warn from t()", () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      renderThread({ streamError: "伺服器暫時無法處理請求" });

      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("伺服器暫時無法處理請求")).toBeInTheDocument();
      expect(warnSpy).not.toHaveBeenCalled();

      warnSpy.mockRestore();
    });
  });

  // Extra coverage: retry must resend the content of the last real attempt,
  // not whatever text happens to be left in the input (usually already
  // cleared) at retry time.
  it("clicking retry resends the content of the last real attempt", async () => {
    const { rerenderWindow } = renderThread();

    const input = screen.getByPlaceholderText(/輸入訊息/);
    await userEvent.type(input, "foo");
    await userEvent.click(screen.getByRole("button", { name: "送出" }));

    // Simulate the stream reporting a network error after that send.
    const afterError = makeStreamReturn({ streamError: "error.network" });
    mockedUseChatStream.mockReturnValue(afterError);
    rerenderWindow();

    await userEvent.click(screen.getByRole("button", { name: "重試" }));

    expect(afterError.sendMutation.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ message: "foo" }),
      expect.anything(),
    );
  });

  // Extra coverage: the welcome screen hands its first message over as
  // ?firstMsg=. The thread must send it exactly once and then strip the query
  // from the URL, so a reload does not send the same message a second time.
  it("auto-sends the first message once and strips it from the URL", async () => {
    // Must be spied before rendering — the auto-send effect that calls
    // replaceState fires on mount, inside renderThread() below.
    const replaceStateSpy = vi.spyOn(window.history, "replaceState");

    const { stream } = renderThread({ searchParams: { firstMsg: "你好" } });

    await waitFor(() => expect(stream.sendMutation.mutate).toHaveBeenCalledTimes(1));
    expect(stream.sendMutation.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ message: "你好" }),
      expect.anything(),
    );
    expect(replaceStateSpy).toHaveBeenCalledWith(null, "", window.location.pathname);

    replaceStateSpy.mockRestore();
  });

  // Carried requirement: the backend persists a `{"type": "trace", "steps":
  // [...]}` content block on every run (backend/api/routers/chat.py), but
  // that data used to be write-only from the thread's point of view.
  // Reopening a thread (a fresh history fetch, no pending stream) must
  // still show what the run did.
  it("renders a stored trace from history with running=false, so a reopened thread still shows the run's trace", () => {
    renderThread({
      messages: [
        {
          id: 2,
          role: "assistant",
          content: [
            { type: "text", text: "分析完成" },
            { type: "trace", steps: [{ seq: 1, raw: "ID mapping in progress." }] },
          ],
        },
      ],
    });

    expect(screen.getByText("已完成 1 個步驟")).toBeInTheDocument();
  });

  describe("result panel routing (layout B)", () => {
    // Layout B ships: only the `analysis` intent mounts in the thread's side
    // panel; the other three intents stay inline in the conversation.
    it("an analysis-intent result renders inside the side panel, not inline in the conversation", () => {
      renderThread({
        messages: [
          {
            id: 3,
            role: "assistant",
            content: [{ type: "result", intent: "analysis", data: {}, folder: "run_1" }],
          },
        ],
      });

      const panel = screen.getByTestId("result-panel");
      expect(within(panel).getByTestId("result-card")).toHaveTextContent("analysis");
      // Exactly one ResultCard exists at all — it did not also render inline.
      expect(screen.getAllByTestId("result-card")).toHaveLength(1);
    });

    it("a non-analysis intent (e.g. id_mapping) stays inline; no side panel mounts", () => {
      renderThread({
        messages: [
          {
            id: 4,
            role: "assistant",
            content: [{ type: "result", intent: "id_mapping", data: {} }],
          },
        ],
      });

      expect(screen.queryByTestId("result-panel")).not.toBeInTheDocument();
      expect(screen.getByTestId("result-card")).toHaveTextContent("id_mapping");
    });

    // The panel's 380px floor is what makes the wrap rule work —
    // without it, a `flex: 0 0 380px` panel (fixed, non-shrinking) would
    // recreate the exact crushed-conversation failure the wrap rule exists
    // to prevent, and nothing else here would notice.
    it("keeps its 380px floor (flex: 1 1 380px, min-width: min(100%, 380px))", () => {
      renderThread({
        messages: [
          {
            id: 3,
            role: "assistant",
            content: [{ type: "result", intent: "analysis", data: {}, folder: "run_1" }],
          },
        ],
      });

      expect(screen.getByTestId("result-panel")).toHaveStyle({
        flex: "1 1 380px", minWidth: "min(100%, 380px)",
      });
    });

    // Important: suppressing every analysis-intent block unconditionally
    // (rather than only the one message the panel is currently showing)
    // makes a second analysis in the same thread delete the first run's
    // significant metabolites, figures and folder from the page entirely —
    // a physician comparing two runs would silently lose the one they ran
    // first. Only the newest (the one the panel shows) may be missing
    // inline; every earlier analysis result must still be reachable.
    it("keeps an earlier analysis result inline when a second analysis runs in the same thread", () => {
      renderThread({
        messages: [
          {
            id: 10,
            role: "assistant",
            content: [{ type: "result", intent: "analysis", data: {}, folder: "run_1" }],
          },
          {
            id: 20,
            role: "assistant",
            content: [{ type: "result", intent: "analysis", data: {}, folder: "run_2" }],
          },
        ],
      });

      // The newest result (id 20) is the one in the panel...
      const panel = screen.getByTestId("result-panel");
      expect(within(panel).getByTestId("result-card")).toBeInTheDocument();
      // ...and the first (id 10) is still rendered — inline, not gone.
      expect(screen.getAllByTestId("result-card")).toHaveLength(2);
    });
  });
});
