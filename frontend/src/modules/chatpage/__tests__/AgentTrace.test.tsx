import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import AgentTrace from "../AgentTrace";
import type { TraceStep } from "@/src/types/results";

const steps: TraceStep[] = [
  { seq: 1, raw: "Parameter extraction complete, statistical analysis in progress.", ms: 400 },
  { seq: 2, raw: "Summary complete! Ready to download.", ms: 22300 },
];

function renderTrace(props: { steps?: TraceStep[]; running?: boolean } = {}) {
  return render(
    <LocaleProvider>
      <AgentTrace steps={props.steps ?? steps} running={props.running ?? false} />
    </LocaleProvider>,
  );
}

describe("AgentTrace", () => {
  it("renders nothing when there are no steps and nothing is running", () => {
    const { container } = render(
      <LocaleProvider><AgentTrace steps={[]} running={false} /></LocaleProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the pulse and the current (most recent) step's translated sentence while running", () => {
    renderTrace({ steps: [steps[0]], running: true });
    expect(screen.getByTestId("trace-pulse")).toBeInTheDocument();
    expect(screen.getByText(/統計分析/)).toBeInTheDocument();
  });

  it("falls back to the generic pulse sentence when running starts before any step arrives", () => {
    renderTrace({ steps: [], running: true });
    expect(screen.getByTestId("trace-pulse")).toBeInTheDocument();
    expect(screen.getByText("正在處理你的訊息…")).toBeInTheDocument();
  });

  // The fallback renders at the one moment the UI knows the *least*: the
  // request is in flight and the agent has not reported a single step, so
  // its intent is still unclassified. A physician who merely asked a
  // question — or who has not uploaded a peak table at all, and is about to
  // be told to — was previously shown copy naming two concrete operations
  // (reading the table, running the tests) that are not running and, with
  // no file, cannot be. Layer 1 exists to prove the system is alive;
  // inventing a specific activity to prove it trades a truthful signal for
  // a plausible-looking lie, and this trace is part of what lets a
  // physician decide whether to trust the result.
  //
  // The pattern matches the two claims, not the whole retired sentence: any
  // future rewrite that reintroduces either one should fail here, including
  // one that rephrases the rest.
  it("does not name a specific analysis activity before any step has arrived", () => {
    renderTrace({ steps: [], running: true });
    expect(screen.queryByText(/統計檢定|讀取資料/)).not.toBeInTheDocument();
  });

  it("shows the completed step count and no pulse once finished", () => {
    renderTrace({ running: false });
    expect(screen.queryByTestId("trace-pulse")).not.toBeInTheDocument();
    expect(screen.getByText("已完成 2 個步驟")).toBeInTheDocument();
  });

  it("expands to show each step translated, with its formatted duration", async () => {
    renderTrace();
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/統計分析/)).toBeInTheDocument();
    expect(screen.getByText(/可以下載/)).toBeInTheDocument();
    expect(screen.getByTestId("trace-duration-1")).toHaveTextContent("0.4 s");
    expect(screen.getByTestId("trace-duration-2")).toHaveTextContent("22.3 s");
  });

  it("formats a duration of one minute or more as \"N min N s\"", async () => {
    renderTrace({ steps: [{ seq: 1, raw: "Report writing complete.", ms: 72000 }] });
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("trace-duration-1")).toHaveTextContent("1 min 12 s");
  });

  // Boundary cases: a `<` vs `<=` slip at either threshold would render
  // 1000ms as "1 min 0 s" (treating the second-vs-minutes boundary as
  // exclusive-below-1000 instead of exclusive-below-60000) or 60000ms as
  // "60.0 s" (the opposite slip) without any of the tests above noticing,
  // since neither exercises a value at the threshold itself.
  it("formats exactly 1000ms as one decimal second, not the minutes format", async () => {
    renderTrace({ steps: [{ seq: 1, raw: "Plot review is in progress...", ms: 1000 }] });
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("trace-duration-1")).toHaveTextContent("1.0 s");
  });

  it("formats exactly 60000ms as the minutes-format boundary", async () => {
    renderTrace({ steps: [{ seq: 1, raw: "Report writing complete.", ms: 60000 }] });
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("trace-duration-1")).toHaveTextContent("1 min 0 s");
  });

  it("renders an empty duration cell — never NaN, undefined or 0 s — for a step with no ms", async () => {
    renderTrace({ steps: [{ seq: 1, raw: "Plot review is in progress..." }] });
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("trace-duration-1")).toBeEmptyDOMElement();
  });
});
