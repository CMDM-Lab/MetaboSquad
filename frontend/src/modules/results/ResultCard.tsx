"use client";

import { useState } from "react";
import { useT } from "@/src/i18n/LocaleContext";
import { ApiError } from "@/src/lib/apiClient";
import type { ResultBlockData } from "@/src/types/results";
import useQueryArtifacts from "@/src/hooks/useQueryArtifacts";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import ZipDownloadBox from "@/src/modules/chatpage/ZipDownloadBox";
import AnalysisHighlights from "./AnalysisHighlights";
import ArtifactGallery from "./ArtifactGallery";
import IdMappingTable, { type IdMappingRow } from "./IdMappingTable";
import LiteraturePanel, { type LiteraturePaper } from "./LiteraturePanel";
import MarkdownReport from "./MarkdownReport";
import PlotReviewPanel from "./PlotReviewPanel";

type Tab = "highlights" | "report" | "files";

type Props = {
  intent: string | null;
  data: ResultBlockData;
  folder: string | null;
};

/**
 * The shared empty state for an artifacts folder that came back empty or
 * failed to load: `ErrorCard` (explicit failure, retryable). An `ApiError`'s
 * `detail` is shown verbatim; everything else (including a dropped-connection
 * `TypeError`) falls back to the i18n "cannot connect" string.
 */
function EmptyArtifactsNotice({
  detail, onRetry,
}: {
  detail: string;
  onRetry: () => void;
}) {
  return <ErrorCard detail={detail} onRetry={onRetry} />;
}

function summaryFor(
  intent: string | null,
  data: ResultBlockData,
  t: (k: string, v?: Record<string, string | number>) => string,
): string | null {
  if (intent === "analysis") {
    // `data.significant_metabolites` is bound to `sig_identified_metabolites`
    // (backend/src/graph_agent/graph/analysis_graph.py:116,135), which
    // `use_tool/pathway_analysis.py:109-120` fills only with significant rows
    // whose Feature label is not a bare m/z string — i.e. NAMED metabolites,
    // not "every significant feature". A run keyed entirely by m/z (such as
    // the bundled lcms_table.csv) reports 0 here even when the R
    // script found dozens of significant features.
    //
    // `data.sig_all` is the true combined total (named + unidentified m/z
    // features) and now reaches this component: `MainState` declares a
    // `sig_all` channel (backend/src/graph_agent/state.py) and
    // `from_analysis_state` (backend/src/graph_agent/supervisor.py) carries
    // it across the subgraph boundary, guarded by
    // backend/tests/test_structured_keys_declared.py and
    // backend/tests/test_sig_all_propagation.py. When present, the headline
    // states both numbers so neither reads as the whole picture on its own:
    // "31 significant features (0 identified)" tells a physician the R
    // script found real signal even though none of it has a name yet.
    //
    // `sig_all` is absent, though, on any thread persisted before this field
    // existed — the stored payload simply has no such key. For those, fall
    // back to the identified-only wording (`result.significantCount`) rather
    // than compute a number from data that was never captured; reopening an
    // old thread must not show a fabricated or broken total.
    //
    // Either way 0 is still rendered rather than treated as "no headline"
    // (falling through to the card's own "—" fallback): an analysis that ran
    // and found zero of either count is a real result worth stating plainly,
    // not hiding behind a bare em dash.
    //
    // `result.significantCountTotal` ends with a "see the full report"
    // pointer because `AnalysisHighlights`' significant-metabolite table is
    // suppressed whenever `significant_metabolites` is empty — so without
    // it a run like the bundled dataset (31 total, 0 identified) would
    // render an honest headline with *no table and no pointer to where the
    // 31 actually are*. The full report markdown (e.g.
    // `uploads/output/analysis/<run>/significant_*.md`) always has a
    // "## List of Significant Features" section listing every one of them
    // by m/z/retention-time, identified or not — so pointing back at the
    // full report is not invented, it is where the answer already lives.
    // The pointer lives in the copy itself (`result.significantCountTotal`,
    // both locales) rather than un-suppressing `AnalysisHighlights`' table: that table has a single
    // "Metabolite" (name) column with no per-row data for bare m/z features,
    // so listing them there would mislabel numbers as names — the same
    // failure mode `AnalysisHighlights`' own doc comment already guards
    // against. Pinned in `i18n.test.tsx`'s `LOCALE_DIVERGENT_PINS` so a
    // revert of either the two-number form or the pointer clause goes red.
    if (data.sig_all !== undefined) {
      const total = data.sig_all.length;
      const named = data.significant_metabolites?.length ?? 0;
      return t("result.significantCountTotal", { total, named });
    }
    const n = data.significant_metabolites?.length ?? 0;
    return t("result.significantCount", { n });
  }
  if (intent === "id_mapping") {
    const n = data.id_mapping_result?.length ?? 0;
    return n ? t("result.metabolitesFound", { n }) : null;
  }
  if (intent === "plot_review") {
    const n = data.review_result?.length ?? 0;
    return n ? t("result.reviewedFigures", { n }) : null;
  }
  return null;
}

function kickerFor(
  intent: string | null,
  t: (k: string, v?: Record<string, string | number>) => string,
): string {
  if (intent === "id_mapping") return t("result.mapTitle");
  if (intent === "literature_search") return t("result.litTitle");
  if (intent === "plot_review") return t("result.plotTitle");
  return t("result.kicker");
}

/**
 * The dataset name that produced this result, read from the real
 * `analysis_result.config.file_path` (see
 * `backend/src/graph_agent/use_tool/code.py:136-141` for where `config` is
 * built). Group/sample counts and a run timestamp are not available as
 * structured fields on this payload — the counts only exist as prose
 * inside `analysis_result.summary`, and the message's `created_at` is not
 * threaded through `ResultCard`'s props — so both render as an em dash
 * rather than a fabricated value.
 */
function datasetLine(analysisResult: Record<string, unknown> | undefined): string {
  const config = analysisResult?.config;
  const filePath =
    config && typeof config === "object" && !Array.isArray(config)
      ? (config as Record<string, unknown>).file_path
      : undefined;
  if (typeof filePath !== "string" || filePath.length === 0) return "—";
  const parts = filePath.split("/");
  return parts[parts.length - 1] || "—";
}

export default function ResultCard({
  intent, data, folder,
}: Props) {
  const { t } = useT();
  const [tab, setTab] = useState<Tab>("highlights");

  // Only fetch when the physician switches to a tab that actually needs the
  // artifacts folder, to avoid one API call per historical message.
  // Exception: `analysis`'s own highlights tab IS the figure + significant-
  // metabolite table + R source — the figure is how a physician judges
  // correctness, and it must not wait for a tab switch before react-query
  // has a cache entry to serve. So `analysis` fetches on the default tab
  // too; the other three intents render from their own structured fields
  // and never need this extra call on mount.
  const needsArtifacts =
    !!folder && (tab !== "highlights" || intent === "analysis");
  const { data: artifacts, isLoading, isError, error, refetch } = useQueryArtifacts(folder, needsArtifacts);

  // A failed fetch leaves `artifacts` undefined, so every `artifacts?.x ?? []`
  // below collapses to empty — byte-identical to a folder that genuinely
  // produced nothing. Resolving the failure once, here, is what lets the
  // three tabs tell the physician which of the two happened; without it a
  // failed request reads as "your files do not exist" while they sit intact
  // on disk.
  const artifactsError = isError
    ? (error instanceof ApiError ? error.detail : t("error.network"))
    : null;

  const images = (artifacts?.files ?? []).filter((f) => f.kind === "image");
  const markdownEntries = Object.entries(artifacts?.markdown ?? {});
  const summary = summaryFor(intent, data, t) ?? "—";
  const kicker = kickerFor(intent, t);
  // The timestamp half of the stamp is always "—" (see datasetLine's own
  // doc comment — the message's created_at is never threaded through this
  // component's props). When the dataset name is also unknown, showing two
  // stacked em dashes is redundant noise; collapse to a single one instead.
  const dataset = datasetLine(data.analysis_result);
  const stamp = dataset === "—" ? "—" : `${dataset}\n—`;

  const TABS: ReadonlyArray<readonly [Tab, string]> = [
    ["highlights", t("result.tabHighlights")],
    ["report", t("result.tabReport")],
    ["files", t("result.tabFiles")],
  ];

  return (
    <article style={{ border: "1px solid var(--color-divider)", background: "white" }}>
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--space-2) var(--space-3)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-divider)",
        }}
      >
        <div style={{ flex: "1 1 240px", minWidth: "0px" }}>
          <Kicker>{kicker}</Kicker>
          <div style={{ fontWeight: 600, fontSize: "17px", lineHeight: 1.3, marginTop: "3px" }}>
            {summary}
          </div>
        </div>
        {intent === "analysis" && (
          <div
            data-testid="result-stamp"
            style={{
              flex: "0 1 auto",
              minWidth: "0px",
              fontVariantNumeric: "tabular-nums",
              fontSize: "11px",
              lineHeight: 1.5,
              color: "var(--color-neutral-600)",
              whiteSpace: "pre-line",
            }}
          >
            {stamp}
          </div>
        )}
      </header>

      <div
        role="tablist"
        style={{
          display: "flex",
          gap: "var(--space-4)",
          padding: "0 var(--space-4)",
          borderBottom: "1px solid var(--color-divider)",
        }}
      >
        {TABS.map(([key, label]) => {
          const selected = tab === key;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(key)}
              style={{
                appearance: "none",
                background: "transparent",
                border: "none",
                borderBottom: selected ? "2px solid var(--color-accent)" : "2px solid transparent",
                marginBottom: "-1px",
                cursor: "pointer",
                padding: "var(--space-2) 0",
                fontWeight: 600,
                fontSize: "13px",
                letterSpacing: "0.02em",
                color: selected ? "var(--color-text)" : "var(--color-neutral-600)",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div style={{ padding: "var(--space-4)" }}>
        {tab === "highlights" && (
          <>
            {intent === "id_mapping" && (
              <IdMappingTable rows={(data.id_mapping_result ?? []) as IdMappingRow[]} />
            )}
            {intent === "analysis" && (
              <AnalysisHighlights
                analysisResult={data.analysis_result}
                significantMetabolites={data.significant_metabolites}
                images={images}
                isLoading={needsArtifacts && isLoading}
                isError={needsArtifacts && isError}
                errorDetail={artifactsError ?? undefined}
                onRetry={() => refetch()}
              />
            )}
            {intent === "plot_review" && (
              // `review_result` reaches the frontend today: `MainState`
              // (backend/src/graph_agent/state.py) declares
              // `review_result: list[dict[str, Any]]`, guarded by
              // `backend/tests/test_structured_keys_declared.py`, so
              // LangGraph no longer silently drops it. PlotReviewPanel owns
              // its own per-intent visual treatment — this dispatch just
              // needs to not claim the data path is broken when it is not.
              <PlotReviewPanel reviews={(data.review_result ?? []) as never} />
            )}
            {intent === "literature_search" && (
              // `LiteraturePanel` reads the same per-paper list the backend
              // builds from `search_pubmed` and mutates in place through the
              // filter/extract pipeline (see that component's own doc
              // comment); `text_extract` is always this same array under a
              // second name (`supervisor.py`'s `from_lit_state` sets
              // `text_extract = state.get("text_extract") or
              // state.get("abstract_extract", [])`, and no node ever sets
              // `text_extract` itself), so `abstract_extract` is read
              // directly rather than through that alias.
              <LiteraturePanel
                papers={
                  ((data.literature_result as Record<string, unknown> | undefined)
                    ?.abstract_extract ?? []) as LiteraturePaper[]
                }
              />
            )}
          </>
        )}

        {tab === "report" && (
          isLoading ? (
            <p className="text-[13px] text-neutral-500">{t("common.loading")}</p>
          ) : (artifactsError || markdownEntries.length === 0) ? (
            <EmptyArtifactsNotice
              detail={artifactsError ?? t("result.emptyArtifacts")}
              onRetry={() => refetch()}
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
              {markdownEntries.map(([name, md]) => (
                <div key={name} style={{ maxWidth: "62ch" }}>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "11px",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: "var(--color-neutral-600)",
                      borderBottom: "1px solid var(--color-divider)",
                      paddingBottom: "var(--space-1)",
                      marginBottom: "var(--space-3)",
                    }}
                  >
                    {name}
                  </div>
                  <MarkdownReport markdown={md} />
                </div>
              ))}
            </div>
          )
        )}

        {tab === "files" && (
          isLoading ? (
            <p className="text-[13px] text-neutral-500">{t("common.loading")}</p>
          ) : (artifactsError || (artifacts?.files ?? []).length === 0) ? (
            <EmptyArtifactsNotice
              detail={artifactsError ?? t("result.noFiles")}
              onRetry={() => refetch()}
            />
          ) : (
            <div>
              <ArtifactGallery files={artifacts?.files ?? []} />
              {folder && (
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--space-3)" }}>
                  <ZipDownloadBox folderName={folder} />
                </div>
              )}
            </div>
          )
        )}
      </div>
    </article>
  );
}
