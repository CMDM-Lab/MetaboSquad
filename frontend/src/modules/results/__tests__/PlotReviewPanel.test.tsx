import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { zh } from "@/src/i18n/messages/zh";
import PlotReviewPanel from "../PlotReviewPanel";

describe("PlotReviewPanel", () => {
  // The payload is prose-only (`{ feedback }`, no
  // severity field). A later "improvement" that infers a must-fix/suggested
  // tag from the wording must make this test go red.
  it("renders the review feedback without inventing a severity tag", () => {
    render(<PlotReviewPanel reviews={[{ file_name: "pca.png", feedback: "建議加上 95% 信賴橢圓" }]} />);
    expect(screen.getByText(/信賴橢圓/)).toBeInTheDocument();
    expect(screen.queryByText(zh["result.levelMust"])).toBeNull();
    expect(screen.queryByText(zh["result.levelNice"])).toBeNull();
  });

  // A review comment makes no sense to check without the plot it is about
  // in view — a feedback block with no image is unusable.
  it("shows the reviewed figure next to its feedback", () => {
    render(<PlotReviewPanel reviews={[{ file_path: "uploads/image/pca.png", feedback: "字太小" }]} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", expect.stringContaining("pca.png"));
    expect(screen.getByText(/字太小/)).toBeInTheDocument();
  });

  it("shows the warning line when the payload carries one", () => {
    render(<PlotReviewPanel reviews={[{
      file_name: "chart.jpg",
      feedback: "ok",
      warning: "JPG 的有損壓縮可能引入邊緣模糊影響偵測精確度",
    }]} />);
    expect(screen.getByText(/有損壓縮/)).toBeInTheDocument();
  });

  it("separates multiple reviewed figures with a hairline", () => {
    render(<PlotReviewPanel reviews={[
      { file_name: "a.png", feedback: "one" },
      { file_name: "b.png", feedback: "two" },
    ]} />);
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  it("renders nothing for an empty review list", () => {
    const { container } = render(<PlotReviewPanel reviews={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not render an image when the review has no file_path", () => {
    render(<PlotReviewPanel reviews={[{ file_name: "no-path.png", feedback: "text only" }]} />);
    expect(screen.queryByRole("img")).toBeNull();
  });
});
