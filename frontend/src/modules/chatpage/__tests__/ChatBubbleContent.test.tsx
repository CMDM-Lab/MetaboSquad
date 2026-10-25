import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import ChatBubbleContent from "../ChatBubbleContent";

// ResultCard calls the artifacts API, so it's mocked here — this file only
// verifies dispatching.
vi.mock("@/src/modules/results/ResultCard", () => ({
  default: ({ intent }: { intent: string | null }) => (
    <div data-testid="result-card">{intent}</div>
  ),
}));

function renderContent(
  content: unknown,
  extra: {
    messageId?: number;
    role?: string;
    panelResultMessageId?: number;
  } = {},
) {
  return render(
    <LocaleProvider>
      <ChatBubbleContent content={content} {...extra} />
    </LocaleProvider>,
  );
}

describe("ChatBubbleContent", () => {
  it("renders a plain string as-is (backward compatible with legacy data)", () => {
    renderContent("哈囉");
    expect(screen.getByText("哈囉")).toBeInTheDocument();
  });

  it("renders a text block", () => {
    renderContent([{ type: "text", text: "分析完成" }]);
    expect(screen.getByText("分析完成")).toBeInTheDocument();
  });

  it("renders an image block", () => {
    renderContent([{ type: "image", url: "/uploads/image/a.png" }]);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src", expect.stringContaining("/uploads/image/a.png"));
  });

  it("renders a result block and passes the intent through", () => {
    renderContent([
      { type: "result", intent: "id_mapping", data: { id_mapping_result: [] } },
    ]);
    expect(screen.getByTestId("result-card")).toHaveTextContent("id_mapping");
  });

  // Layout B: only the
  // `analysis` intent's newest result moves to the thread's side panel,
  // which ChatWindow.tsx renders from the history payload — and only for
  // the exact message the panel is showing (`panelResultMessageId`), so
  // this component must not also render that specific message's card
  // inline, or a physician would see the same analysis card twice.
  it("an analysis-intent result block renders nothing inline when it is the panel's message", () => {
    renderContent(
      [{ type: "result", intent: "analysis", data: { significant_metabolites: ["x"] } }],
      { messageId: 5, panelResultMessageId: 5 },
    );
    expect(screen.queryByTestId("result-card")).not.toBeInTheDocument();
  });

  // Suppressing every analysis-intent block
  // unconditionally (regardless of which message the panel is actually
  // showing) made a second analysis in the same thread delete the first
  // run's significant metabolites, figures and folder from the page
  // entirely. Only the message the panel is showing may go missing inline;
  // an earlier analysis result (a different messageId) must stay reachable.
  it("an analysis-intent result block stays inline when it is not the panel's message", () => {
    renderContent(
      [{ type: "result", intent: "analysis", data: { significant_metabolites: ["x"] } }],
      { messageId: 3, panelResultMessageId: 5 },
    );
    expect(screen.getByTestId("result-card")).toHaveTextContent("analysis");
  });

  it("renders a trace block", () => {
    renderContent([
      { type: "trace", steps: [{ seq: 1, raw: "ID mapping in progress." }] },
    ]);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("downgrades the accompanying text to a footnote when a result block is also present", () => {
    renderContent([
      { type: "text", text: "PubChem 查詢完成，路徑分析中" },
      { type: "result", intent: "id_mapping", data: {} },
    ]);
    expect(screen.getByTestId("result-card")).toBeInTheDocument();
    expect(screen.getByTestId("text-fallback")).toBeInTheDocument();
  });

  it("does not downgrade text when it is the only block", () => {
    renderContent([{ type: "text", text: "你好" }]);
    expect(screen.queryByTestId("text-fallback")).not.toBeInTheDocument();
  });

  it("ignores an unknown block type instead of crashing", () => {
    renderContent([
      { type: "mystery", foo: 1 },
      { type: "text", text: "還在" },
    ]);
    expect(screen.getByText("還在")).toBeInTheDocument();
  });

  it("returns nothing for null or non-array, non-string content", () => {
    const { container } = renderContent(null);
    expect(container).toBeEmptyDOMElement();
  });

  // The assistant turn is start-aligned, never
  // justified — justified CJK at a narrow measure breaks tokens like
  // `|log₂FC| > 1` across lines.
  it("an assistant text block is start-aligned, not justified", () => {
    renderContent([{ type: "text", text: "|log₂FC| > 1" }], { role: "assistant" });
    expect(screen.getByText(/log₂FC/)).toHaveStyle({ textAlign: "start" });
  });

  // The user turn is right-aligned with a 60ch cap and
  // a rule down the left edge — this pins the actual treatment, not just
  // "not justified", so a user block that quietly kept the assistant's
  // full-width style would still fail it.
  it("a user text block gets the 60ch/border-left treatment, not the assistant's full-width style", () => {
    renderContent([{ type: "text", text: "請幫我分析這個檔案" }], { role: "user" });
    const el = screen.getByText("請幫我分析這個檔案");
    expect(el).toHaveClass("max-w-[60ch]", "border-neutral-400");
    expect(el).not.toHaveClass("w-full");
  });
});
