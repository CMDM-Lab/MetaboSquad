"use client";

import Hairline from "@/src/components/Hairline";
import { useT } from "@/src/i18n/LocaleContext";

export type LiteraturePaper = {
  title?: string;
  /** Both spellings occur in the real payload depending on which node last
   * touched a paper dict — see `abstract_extract_node` /
   * `write_output_node` in
   * backend/src/graph_agent/graph/literature_scoping_only_pubmed.py, which
   * read `p.get("year") or p.get("publication_year")` themselves. */
  year?: number | string;
  publication_year?: number | string;
  pm_url?: string;
  /** Set by `search_pubmed` (backend/src/graph_agent/use_tool/search.py:106)
   * as `record.get('Source', 'N/A')` — present on every paper from the start
   * of the pipeline. When PubMed's record has no `Source`, the backend's own
   * default is the literal string `"N/A"`, not an absent field; see
   * `isMissing` below. */
  journal?: string;
};

const NA = "N/A";

/** True for a field that is either genuinely absent or carries the
 * backend's own `"N/A"` placeholder — both should read as "not shown," not
 * as the literal text "N/A" printed in a citation line. */
function isMissing(value: string | number | undefined | null): boolean {
  return value === undefined || value === null || value === "" || value === NA;
}

/**
 * One `<article>` per paper, hairline-separated. Renders no kicker or border of its
 * own: this component fills `ResultCard`'s highlights-tab content for
 * `literature_search`, and `ResultCard` already supplies both the outer
 * `1px solid` block and the `result.litTitle` kicker in its header — the
 * same convention `IdMappingTable` and `PlotReviewPanel` follow for the same
 * reason (see ResultCard.tsx's `kickerFor` and its bordered `<article>`).
 *
 * The design's meta line names a journal, a year and a citation count. Of
 * those, the
 * journal name is real, not sample data: `search_pubmed`
 * (backend/src/graph_agent/use_tool/search.py:106) sets `"journal":
 * record.get('Source', 'N/A')` on every paper dict at the top of the
 * pipeline, and every later stage (`title_filter_tool`, `abstract_filter_tool`,
 * `abstract_extract` in backend/src/graph_agent/use_tool/literature_add.py)
 * mutates that same dict in place rather than reconstructing it, so
 * `journal` survives unmutated into
 * `literature_result.abstract_extract[].journal`. The citation count does
 * not survive anywhere on this path: that field only exists on the unused
 * `search_europe_pmc` tool, never on `search_pubmed`, which is the tool this
 * graph actually calls. Following the rule "we do not render columns we
 * cannot fill", the meta line renders the journal and year when
 * present and omits the citation count entirely — and also omits the
 * journal when only the backend's own `"N/A"` default arrives, per
 * `isMissing` above.
 *
 * The orientation note is not decoration: `literature_result.summary` is an
 * LLM-compiled synthesis of these abstracts, not the papers themselves — a
 * physician citing it as if it were the original abstract is a real
 * research hazard.
 */
export default function LiteraturePanel({ papers }: { papers: LiteraturePaper[] }) {
  const { t } = useT();
  if (!papers || papers.length === 0) return null;

  return (
    <div>
      <p
        style={{
          fontSize: "12px",
          color: "var(--color-neutral-600)",
          marginBottom: "var(--space-2)",
        }}
      >
        {t("result.litOrientationNote")}
      </p>

      {papers.map((p, idx) => {
        const year = p.year ?? p.publication_year;
        const metaParts = [
          !isMissing(p.journal) ? String(p.journal) : null,
          !isMissing(year) ? String(year) : null,
        ].filter((part): part is string => part !== null);

        return (
          <div key={idx}>
            {idx > 0 && <Hairline />}
            <article style={{ padding: "var(--space-3) 0" }}>
              <div style={{ fontSize: "14px", lineHeight: 1.45 }}>
                {p.pm_url ? (
                  <a href={p.pm_url} target="_blank" rel="noopener noreferrer">
                    {p.title ?? "—"}
                  </a>
                ) : (
                  p.title ?? "—"
                )}
              </div>
              {metaParts.length > 0 && (
                <div
                  style={{
                    marginTop: "3px",
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    fontVariantNumeric: "tabular-nums",
                    color: "var(--color-neutral-600)",
                  }}
                >
                  {metaParts.join(" · ")}
                </div>
              )}
            </article>
          </div>
        );
      })}
    </div>
  );
}
