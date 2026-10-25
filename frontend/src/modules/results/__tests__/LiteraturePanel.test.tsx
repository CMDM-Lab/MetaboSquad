import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import { zh } from "@/src/i18n/messages/zh";
import LiteraturePanel, { type LiteraturePaper } from "../LiteraturePanel";

const paper: LiteraturePaper = {
  title: "Effect of maternal PFAS exposure on the offspring metabolome",
  year: 2023,
  journal: "Environmental Health Perspectives",
  pm_url: "https://pubmed.ncbi.nlm.nih.gov/12345678/",
};

function renderPanel(papers: LiteraturePaper[]) {
  return render(
    <LocaleProvider><LiteraturePanel papers={papers} /></LocaleProvider>,
  );
}

describe("LiteraturePanel", () => {
  it("renders the paper title as an outbound PubMed link", () => {
    renderPanel([paper]);
    const link = screen.getByRole("link", { name: paper.title });
    expect(link).toHaveAttribute("href", paper.pm_url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("falls back to a plain title when the payload has no PubMed link", () => {
    renderPanel([{ title: "No link paper" }]);
    expect(screen.getByText("No link paper")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  // The journal name is real (search_pubmed sets it on every
  // paper, and every later pipeline stage mutates the same dict in place —
  // see the component's own doc comment). It must render alongside the year.
  it("shows the journal and year in the meta line", () => {
    renderPanel([paper]);
    expect(screen.getByText("Environmental Health Perspectives · 2023")).toBeInTheDocument();
  });

  it("reads publication_year when year is absent", () => {
    renderPanel([{ title: "Older spelling", publication_year: 2019 }]);
    expect(screen.getByText("2019")).toBeInTheDocument();
  });

  // The backend defaults `journal` to the literal string "N/A" when PubMed's
  // record has no Source (search.py:106's `record.get('Source', 'N/A')`) —
  // that is not a real journal name, and printing it would misrepresent an
  // absent field as a value. Dropping this guard must make this test go red.
  it("omits the journal from the meta line when the backend's own N/A placeholder arrives", () => {
    renderPanel([{ title: "No source paper", year: 2020, journal: "N/A" }]);
    expect(screen.getByText("2020")).toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).toBeNull();
  });

  // `isMissing()` guards `year` the same way it guards
  // `journal` — the backend produces a literal "N/A" year too
  // (search.py:99's `year = ... if pub_date != 'N/A' else 'N/A'`), and
  // nothing previously pinned that half of the guard. A future change that
  // narrows `isMissing`'s call site to `journal` only must make this go red.
  it("omits the year from the meta line when the backend's own N/A placeholder arrives", () => {
    renderPanel([{ title: "No date paper", journal: "The Lancet", year: "N/A" }]);
    expect(screen.getByText("The Lancet")).toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).toBeNull();
  });

  // "We do not render columns we cannot fill": the design's meta line also
  // shows a citation count, which does not exist anywhere on the real payload (only
  // the unused search_europe_pmc tool has one) — that half stays omitted.
  it("does not invent a citation count the payload does not have", () => {
    renderPanel([paper]);
    expect(screen.queryByText(/引用\s*\d+|\d+\s*citations?/i)).toBeNull();
  });

  it("separates multiple papers with a hairline", () => {
    renderPanel([paper, { title: "Second paper" }]);
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  // The safety-relevant requirement: a physician must not treat an
  // LLM-compiled summary as if it were the original abstract. Dropping this
  // note must make this test go red.
  it("states that the summaries are for orientation only", () => {
    renderPanel([paper]);
    expect(screen.getByText(/僅供快速定位|orientation/i)).toBeInTheDocument();
  });

  it("renders nothing for an empty paper list", () => {
    const { container } = renderPanel([]);
    expect(container).toBeEmptyDOMElement();
  });

  // ResultCard already supplies the bordered block and the
  // result.litTitle kicker for every non-analysis intent (the same
  // convention IdMappingTable and PlotReviewPanel follow) — this component
  // must not render a second one, or a wired-in literature_search result
  // would show the same heading twice.
  it("renders no kicker or heading of its own — ResultCard supplies the chrome", () => {
    renderPanel([paper]);
    expect(screen.queryByText(zh["result.litTitle"])).toBeNull();
  });
});
