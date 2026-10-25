import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import { ApiError } from "@/src/lib/apiClient";
import ResultCard from "../ResultCard";
import { pickFigure } from "../AnalysisHighlights";

const fetchArtifacts = vi.fn();
vi.mock("@/src/services/artifacts", () => ({
  fetchArtifacts: (f: string) => fetchArtifacts(f),
}));

type CardProps = Parameters<typeof ResultCard>[0];

function renderCard(props: CardProps, overrides: Partial<CardProps> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LocaleProvider><ResultCard {...props} {...overrides} /></LocaleProvider>
    </QueryClientProvider>,
  );
}

// Shared fixture for the analysis intent. `r_code` mirrors the real,
// dynamically generated source (backend/src/graph_agent/use_tool/code.py's
// `generate_combined_code`) closely enough to exercise the disclosure
// without claiming it is a literal backend response.
const analysisResult: CardProps = {
  intent: "analysis",
  data: {
    significant_metabolites: ["Citric acid", "L-Lactic acid"],
    analysis_result: {
      r_code:
        'mSet <- InitDataObjects("pktable", "stat", FALSE)\n' +
        'mSet <- Normalization(mSet, "NULL", "LogNorm", "AutoNorm")',
      config: { file_path: "uploads/csv/lcms_table.csv" },
    },
  },
  folder: "uploads/output/analysis/x",
};

describe("ResultCard", () => {
  beforeEach(() => {
    fetchArtifacts.mockReset();
    fetchArtifacts.mockResolvedValue({ folder: "f", files: [], markdown: {} });
  });

  it("analysis's summary bar shows the number of significant metabolites", () => {
    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a", "b", "c"] },
      folder: null,
    });
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });

  it("id_mapping's summary bar shows the number of rows found", () => {
    renderCard({
      intent: "id_mapping",
      data: { id_mapping_result: [{ query: "x", pubchem_pug_view: { cid: 1 } }] },
      folder: null,
    });
    // Matched on the full sentence rather than a bare /1/ regex — the
    // highlights tab also renders IdMappingTable, whose CID column shows
    // the digit "1" too, so a bare regex would hit two nodes and getByText
    // would throw on multiple matches.
    expect(screen.getByText("查到 1 筆代謝物")).toBeInTheDocument();
  });

  // The test above asserts only the summary-bar sentence, which
  // `summaryFor()` computes purely from `data.id_mapping_result?.length` —
  // independent of whether IdMappingTable itself renders. Unwiring
  // IdMappingTable entirely leaves that test green, the same hole a summary
  // bar test leaves for every per-intent component. This asserts on
  // something only IdMappingTable produces: the outbound PubChem CID link —
  // kept specifically because IdMappingTable keeps all eleven identifier
  // columns and their links rather than cutting to four.
  it("id_mapping renders the PubChem CID as an outbound link via IdMappingTable", () => {
    renderCard({
      intent: "id_mapping",
      data: { id_mapping_result: [{ query: "citric acid", pubchem_pug_view: { cid: 311 } }] },
      folder: null,
    });
    const link = screen.getByRole("link", { name: "311" });
    expect(link).toHaveAttribute("href", "https://pubchem.ncbi.nlm.nih.gov/compound/311");
  });

  it("plot_review's summary bar shows the number of reviewed figures", () => {
    renderCard({
      intent: "plot_review",
      data: { review_result: [{ file_name: "a.png", feedback: "字太小" }] },
      folder: null,
    });
    expect(screen.getByText(/1/)).toBeInTheDocument();
  });

  // The test above only asserts `/1/`, which the summary bar (the Chinese
  // "1 figure reviewed" line) satisfies on its own — it stays green even if
  // `PlotReviewPanel` were unwired entirely.
  // This asserts on something only `PlotReviewPanel` produces: the reviewed
  // figure rendered beside its feedback, which is the whole point of that
  // treatment.
  it("plot_review renders the reviewed figure beside its feedback via PlotReviewPanel", () => {
    renderCard({
      intent: "plot_review",
      data: {
        review_result: [{
          file_name: "a.png",
          file_path: "uploads/image/a.png",
          feedback: "字太小",
        }],
      },
      folder: null,
    });
    expect(screen.getByRole("img")).toHaveAttribute("src", expect.stringContaining("a.png"));
    expect(screen.getByText(/字太小/)).toBeInTheDocument();
  });

  // `literature_search` used to render through `MarkdownReport` on
  // `literature_result.summary`; `LiteraturePanel` is its per-intent
  // treatment, reading `literature_result.abstract_extract` instead. Reverting this wiring (rendering through `MarkdownReport`
  // again) must make this test go red.
  it("literature_search renders papers through LiteraturePanel, reading abstract_extract", () => {
    renderCard({
      intent: "literature_search",
      data: {
        literature_result: {
          summary: "### Positive Viewpoint\nsome synthesis text",
          abstract_extract: [{
            title: "Effect of maternal PFAS exposure on the offspring metabolome",
            year: 2023,
            journal: "Environmental Health Perspectives",
            pm_url: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
          }],
        },
      },
      folder: null,
    });
    expect(screen.getByRole("link", {
      name: "Effect of maternal PFAS exposure on the offspring metabolome",
    })).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/12345678/");
    expect(screen.getByText("Environmental Health Perspectives · 2023")).toBeInTheDocument();
    // The old summary-only rendering must not still be there alongside it.
    expect(screen.queryByText(/some synthesis text/)).toBeNull();
  });

  // ResultCard's header already renders a `result.litTitle`
  // kicker for this intent (see `kickerFor`); `LiteraturePanel` must not
  // render a second one now that it is wired in, or a physician would see
  // the same heading twice. This is the guard against exactly that
  // regression — it must fail if `LiteraturePanel` ever re-adds its own
  // kicker.
  it("does not render the literature kicker twice once LiteraturePanel is wired in", () => {
    renderCard({
      intent: "literature_search",
      data: {
        literature_result: {
          abstract_extract: [{ title: "Solo paper" }],
        },
      },
      folder: null,
    });
    expect(screen.getAllByText(zh["result.litTitle"])).toHaveLength(1);
  });

  it("defaults to the highlights tab, and can switch to the full report", async () => {
    fetchArtifacts.mockResolvedValue({
      folder: "uploads/output/analysis/x",
      files: [{ name: "r.md", path: "/uploads/output/analysis/x/r.md", kind: "md", size: 10 }],
      markdown: { "r.md": "# 綜合分析報告" },
    });

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await userEvent.click(screen.getByRole("tab", { name: "完整報告" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "綜合分析報告" })).toBeInTheDocument());
  });

  it("does not call the artifacts API when there is no folder", () => {
    renderCard({ intent: "analysis", data: {}, folder: null });
    expect(fetchArtifacts).not.toHaveBeenCalled();
  });

  // Analysis's own highlights tab is the default tab, and it is also
  // the tab that needs the figure — the figure is how a physician judges
  // correctness. The previous implementation only fetched artifacts once a
  // physician switched to "full report" or "files", so the first thing
  // they saw when opening an analysis result never had a figure.
  it("analysis calls the artifacts API and renders the figure right on the default highlights tab", async () => {
    fetchArtifacts.mockResolvedValue({
      folder: "uploads/output/analysis/x",
      files: [{ name: "pca.png", path: "/uploads/output/analysis/x/pca.png", kind: "image", size: 10 }],
      markdown: {},
    });

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await waitFor(() => expect(fetchArtifacts).toHaveBeenCalledWith("uploads/output/analysis/x"));
    await waitFor(() => expect(screen.getByAltText("pca.png")).toBeInTheDocument());
  });

  it("a non-analysis intent on the default highlights tab does not call the artifacts API (no need for an extra call)", () => {
    renderCard({
      intent: "id_mapping",
      data: { id_mapping_result: [{ query: "x", pubchem_pug_view: { cid: 1 } }] },
      folder: "uploads/output/id_mapping/x",
    });
    expect(fetchArtifacts).not.toHaveBeenCalled();
  });

  it("shows an explicit empty state when artifacts returns an empty list", async () => {
    fetchArtifacts.mockResolvedValue({ folder: "f", files: [], markdown: {} });
    renderCard({ intent: "analysis", data: {}, folder: "f" });

    await userEvent.click(screen.getByRole("tab", { name: "檔案" }));
    await waitFor(() =>
      expect(screen.getByText(/找不到產出檔案|沒有產出檔案/)).toBeInTheDocument());
  });

  // A FAILED artifacts fetch is not an empty folder, and every tab used to
  // conflate the two: the query throws, `data` is undefined, and
  // `artifacts?.files ?? []` is length 0 — indistinguishable from a folder
  // that genuinely produced nothing. A rejected request (the shape below:
  // an ApiError with a backend detail) therefore told the physician their
  // files did not exist while they sat intact on disk, and the highlights
  // tab additionally blamed the network. Same rule as everywhere else in
  // the app: an ApiError's `detail` is shown verbatim, everything else
  // falls back to the "cannot connect" string.
  describe("a failed artifacts fetch is distinguished from an empty folder", () => {
    const unauthorized = () =>
      fetchArtifacts.mockRejectedValue(new ApiError(403, "無權存取此資料夾"));

    it("surfaces the backend detail on the highlights tab instead of blaming the network", async () => {
      unauthorized();
      renderCard({ intent: "analysis", data: {}, folder: "f" });

      await waitFor(() =>
        expect(screen.getByText("無權存取此資料夾")).toBeInTheDocument());
      expect(screen.queryByText(zh["error.network"])).not.toBeInTheDocument();
    });

    it("surfaces the backend detail on the files tab instead of claiming there are no files", async () => {
      unauthorized();
      renderCard({ intent: "analysis", data: {}, folder: "f" });

      await userEvent.click(screen.getByRole("tab", { name: "檔案" }));
      await waitFor(() =>
        expect(screen.getByText("無權存取此資料夾")).toBeInTheDocument());
      expect(screen.queryByText(zh["result.noFiles"])).not.toBeInTheDocument();
    });

    it("surfaces the backend detail on the report tab instead of claiming there are no artifacts", async () => {
      unauthorized();
      renderCard({ intent: "analysis", data: {}, folder: "f" });

      await userEvent.click(screen.getByRole("tab", { name: "完整報告" }));
      await waitFor(() =>
        expect(screen.getByText("無權存取此資料夾")).toBeInTheDocument());
      expect(screen.queryByText(zh["result.emptyArtifacts"])).not.toBeInTheDocument();
    });

    // A dropped connection has no ApiError and no detail to show, so the
    // i18n "cannot connect" string is the correct answer there — the fix
    // must not overshoot into showing a raw TypeError message.
    it("still falls back to the cannot-connect string for a non-ApiError failure", async () => {
      fetchArtifacts.mockRejectedValue(new TypeError("Failed to fetch"));
      renderCard({ intent: "analysis", data: {}, folder: "f" });

      await waitFor(() =>
        expect(screen.getByText(zh["error.network"])).toBeInTheDocument());
      expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
    });
  });

  // An empty artifacts folder (node failure) must show an explicit failure
  // state, not fail silently. The previous implementation was a bare <p>,
  // with no alert semantics and no retry.
  it("shows a retryable ErrorCard (alert) when the \"Files\" tab is empty", async () => {
    fetchArtifacts.mockResolvedValue({ folder: "f", files: [], markdown: {} });
    renderCard({ intent: "analysis", data: {}, folder: "f" });

    await userEvent.click(screen.getByRole("tab", { name: "檔案" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    const callsBefore = fetchArtifacts.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /重試/ }));
    await waitFor(() =>
      expect(fetchArtifacts.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("shows a retryable ErrorCard (alert) when the \"Full report\" tab is empty", async () => {
    fetchArtifacts.mockResolvedValue({ folder: "f", files: [], markdown: {} });
    renderCard({ intent: "analysis", data: {}, folder: "f" });

    await userEvent.click(screen.getByRole("tab", { name: "完整報告" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    const callsBefore = fetchArtifacts.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /重試/ }));
    await waitFor(() =>
      expect(fetchArtifacts.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  // Both header blocks must be allowed to shrink and wrap. A nowrap stamp
  // here collapses the summary title to one glyph per line — the exact
  // failure this guards against.
  it("the header stamp wraps instead of forcing the title narrow", () => {
    renderCard(analysisResult);
    expect(screen.getByTestId("result-stamp")).toHaveStyle({
      whiteSpace: "pre-line",
      flex: "0 1 auto",
      minWidth: "0px",
    });
  });

  // Tabs are a real tablist: physicians navigate them by keyboard.
  it("tabs expose role=tab and aria-selected", async () => {
    renderCard(analysisResult);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.click(tabs[2]);
    expect(tabs[2]).toHaveAttribute("aria-selected", "true");
  });

  // The R code disclosure is the system's central credibility claim: a
  // physician can check how the number was produced without leaving the
  // card.
  it("reveals the R source behind the result", async () => {
    renderCard(analysisResult);
    await userEvent.click(screen.getByRole("button", { name: zh["result.showRCode"] }));
    expect(screen.getByText(/InitDataObjects|Normalization/)).toBeInTheDocument();
  });

  // Integration-level companion to the pickFigure unit tests above: a real
  // run's artifacts do not sort with the volcano plot first, so this
  // exercises the full path (fetch -> images filter -> figure caption) with
  // an out-of-order file list, not just the pure function in isolation.
  it("captions the volcano plot specifically, not whichever image sorts first", async () => {
    fetchArtifacts.mockResolvedValue({
      folder: "uploads/output/analysis/x",
      files: [
        { name: "aov_0_anova.png", path: "/uploads/output/analysis/x/aov_0_anova.png", kind: "image", size: 10 },
        { name: "volcano_0_1.png", path: "/uploads/output/analysis/x/volcano_0_1.png", kind: "image", size: 10 },
      ],
      markdown: {},
    });

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await waitFor(() => expect(screen.getByAltText("volcano_0_1.png")).toBeInTheDocument());
    expect(screen.queryByAltText("aov_0_anova.png")).not.toBeInTheDocument();
    // Exact-text match, not a partial regex: this assertion exists to prove
    // the *whole* volcano caption is rendered, not merely that the Chinese
    // word for "volcano plot" appears somewhere. `zh["result.fig1"]`
    // contains U+3000 (ideographic full-width space, Unicode category Zs)
    // between the "Fig. 1" segment and the "volcano plot" segment;
    // DOM Testing Library's default normalizer collapses whitespace
    // (including U+3000, which JS `\s` also matches) in the rendered node's
    // text, but never touches the raw string passed to the matcher — so an
    // un-normalized `getByText(zh["result.fig1"])` compares a
    // space-collapsed DOM string against a string that still has the
    // full-width space, and the two differ. Normalizing the query string
    // the same way (`.replace(/\s+/g, " ")`) makes both sides comparable.
    expect(screen.getByText(zh["result.fig1"].replace(/\s+/g, " "))).toBeInTheDocument();
  });

  // The other half of the same fix: when no image is a volcano plot at all,
  // the caption must not claim it is one.
  it("does not caption a non-volcano image with the volcano-specific caption", async () => {
    fetchArtifacts.mockResolvedValue({
      folder: "uploads/output/analysis/x",
      files: [
        { name: "heatmap_0_1.png", path: "/uploads/output/analysis/x/heatmap_0_1.png", kind: "image", size: 10 },
      ],
      markdown: {},
    });

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await waitFor(() => expect(screen.getByAltText("heatmap_0_1.png")).toBeInTheDocument());
    // Exact-text (normalized) match — see the note in the volcano test
    // above for why this is not a regex: a bare substring check for the
    // Chinese word for "volcano plot" would still pass if the caption text
    // were e.g. truncated to just that one word instead of the full,
    // accurate sentence, which would not actually prove the caption text is
    // correct.
    expect(screen.queryByText(zh["result.fig1"].replace(/\s+/g, " "))).not.toBeInTheDocument();
    expect(screen.getByText("heatmap_0_1.png")).toBeInTheDocument();
  });

  // Critical fix: `needsArtifacts` fires the fetch on mount for analysis,
  // so before it resolves, `images` is `[]` exactly like the genuinely-no-
  // image case — without a distinct loading state, every fresh analysis
  // card would flash the Chinese "no output files" message before the real
  // figure swaps in.
  it("shows a loading state, not the no-figure message, while artifacts are still fetching", async () => {
    let resolveFetch: (v: unknown) => void = () => {};
    fetchArtifacts.mockReturnValue(new Promise((resolve) => { resolveFetch = resolve; }));

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await waitFor(() => expect(screen.getByText(zh["common.loading"])).toBeInTheDocument());
    expect(screen.queryByText(zh["result.noFiles"])).not.toBeInTheDocument();

    resolveFetch({ folder: "uploads/output/analysis/x", files: [], markdown: {} });
    await waitFor(() => expect(screen.getByText(zh["result.noFiles"])).toBeInTheDocument());
  });

  // A failed fetch is distinct from a successful fetch that found no image:
  // the former is retryable and must say so, not sit as a permanent,
  // silent "no figure" message.
  it("shows a retryable error state when the artifacts fetch itself fails", async () => {
    fetchArtifacts.mockRejectedValueOnce(new Error("network down"));
    fetchArtifacts.mockResolvedValueOnce({
      folder: "uploads/output/analysis/x",
      files: [{ name: "volcano_0_1.png", path: "/uploads/output/analysis/x/volcano_0_1.png", kind: "image", size: 10 }],
      markdown: {},
    });

    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a"] },
      folder: "uploads/output/analysis/x",
    });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText(zh["result.noFiles"])).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: zh["error.retry"] }));
    await waitFor(() => expect(screen.getByAltText("volcano_0_1.png")).toBeInTheDocument());
  });

  // "We do not render columns we cannot fill": log2FC,
  // FDR and pathway are absent for every row of every run, not just some —
  // a column that is always empty is not a per-row gap, it is a column
  // that should not exist. Rendering it next to a summary that cites FDR
  // and an R block that thresholds on it would contradict both.
  it("renders only the metabolite name column, not empty log2FC/FDR/pathway columns", () => {
    renderCard(analysisResult);
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers).toHaveLength(1);
    expect(headers[0]).toHaveTextContent(zh["result.colName"]);
  });

  // An analysis that ran and named zero IDENTIFIED metabolites (this field
  // is identified-only — see ResultCard.tsx's summaryFor doc comment) is a
  // real result worth stating plainly: it must show "0", not a bare "—"
  // that reads as missing data.
  it("shows the significant-metabolite count as 0, not a blank dash, for a null result", () => {
    renderCard({
      intent: "analysis",
      data: { significant_metabolites: [] },
      folder: null,
    });
    expect(screen.getByText(zh["result.significantCount"].replace("{n}", "0"))).toBeInTheDocument();
  });

  // `sig_all` is the true total of significant
  // features (named + bare m/z), now carried across `MainState` and
  // `from_analysis_state` (backend/src/graph_agent/state.py,
  // supervisor.py). When it is present, the headline must state both
  // numbers together — the bundled analysis dataset is keyed entirely by
  // m/z, so `significant_metabolites` (identified-only) alone reads as
  // "found nothing" even when 31 features cleared FDR < 0.05.
  it("shows the true total alongside the identified count when sig_all is present", () => {
    renderCard({
      intent: "analysis",
      data: {
        // 31 total significant features, only 5 of which are named — a
        // distinct, nonzero pair of numbers so a mutation that hardcodes
        // either `total` or `named` (or swaps them) is caught, not just a
        // mutation that drops the fallback branch entirely.
        sig_all: Array.from({ length: 31 }, (_, i) => `mz_${i}`),
        significant_metabolites: ["Citric acid", "L-Lactic acid", "Glucose", "Alanine", "Serine"],
      },
      folder: null,
    });
    expect(screen.getByText(
      zh["result.significantCountTotal"].replace("{total}", "31").replace("{named}", "5"),
    )).toBeInTheDocument();
  });

  // Fallback contract: threads persisted before `sig_all` existed have no
  // such key on their stored `ResultBlockData` at all (not an empty array —
  // genuinely absent). Reopening one of those must keep showing the old
  // identified-only headline, not a fabricated or broken two-number total.
  it("falls back to the identified-only headline when sig_all is absent (thread persisted before this field existed)", () => {
    renderCard({
      intent: "analysis",
      data: { significant_metabolites: ["a", "b", "c"] },
      folder: null,
    });
    expect(screen.getByText(
      zh["result.significantCount"].replace("{n}", "3"),
    )).toBeInTheDocument();
    expect(screen.queryByText(/顯著特徵/)).not.toBeInTheDocument();
  });
});

describe("pickFigure", () => {
  const img = (name: string) => ({ name, path: `/uploads/x/${name}`, kind: "image" as const, size: 10 });

  // A real analysis run's artifacts sort by path (backend/api/artifacts.py's
  // list_folder), which is very often not the volcano plot alphabetically
  // (e.g. "aov_0_..." sorts before "volcano_0_..."). Picking images[0]
  // unconditionally, as the previous round did, would caption whichever
  // file sorts first with `result.fig1`'s volcano-specific axis claim —
  // a false statement about a plot that is not a volcano plot at all.
  it("prefers the volcano image over an earlier-sorting non-volcano image", () => {
    const images = [img("aov_0_anova.png"), img("volcano_0_1.png"), img("pca_0_scores.png")];
    const picked = pickFigure(images);
    expect(picked).toEqual({ file: images[1], isVolcano: true });
  });

  it("falls back to the first image, marked non-volcano, when none matches", () => {
    const images = [img("heatmap_0_1.png"), img("norm_0_1.png")];
    const picked = pickFigure(images);
    expect(picked).toEqual({ file: images[0], isVolcano: false });
  });

  it("returns null when there are no images at all", () => {
    expect(pickFigure([])).toBeNull();
  });
});
