"use client";

import { useState } from "react";
import { API_BASE } from "@/src/config/constants";
import { useT } from "@/src/i18n/LocaleContext";
import ErrorCard from "@/src/components/ErrorCard";
import Kicker from "@/src/components/Kicker";
import type { ArtifactFile } from "@/src/types/results";

type Props = {
  analysisResult?: Record<string, unknown>;
  significantMetabolites?: string[];
  images: ArtifactFile[];
  /** Whether the artifacts fetch this figure depends on is still in flight.
   * Needed so the first paint of a fresh analysis result shows "loading",
   * not "no figure" — the two look identical from `images.length === 0`
   * alone. */
  isLoading?: boolean;
  /** Whether that fetch failed outright (network/server error), distinct
   * from a fetch that succeeded and simply found no image. */
  isError?: boolean;
  /** What to say when it failed. The caller resolves this from the actual
   * error (an ApiError's `detail` verbatim, anything else the i18n
   * "cannot connect" string); this component used to hardcode the latter,
   * which reported every backend error as a dead network. */
  errorDetail?: string;
  onRetry?: () => void;
};

type PickedFigure = { file: ArtifactFile; isVolcano: boolean };

/**
 * Which artifact stands in as "the" figure, and whether it is safe to
 * caption with `result.fig1` (a volcano-plot-specific claim about its axes
 * and thresholds). A real analysis run's artifacts are things like
 * `aov_0_*`, `fc_0_*`, `heatmap_0_*`, `norm_0_*`, `pca_*`, `tt_0_*` and
 * `volcano_0_*`, and `list_folder` (backend/api/artifacts.py) sorts them by
 * path — so picking `images[0]` unconditionally, as the previous round did,
 * captions whichever file happens to sort first (often an ANOVA or
 * normalization plot) as if it were the volcano plot, asserting axis
 * semantics (log2FC vs -log10 FDR) it does not have. That is worse than a
 * missing value: it is a false statement about the science, on the exact
 * surface a physician judges the result's trustworthiness from.
 *
 * Fix: search for an image whose name starts with `volcano` and prefer it.
 * If found, it gets the specific, informative `result.fig1` caption (which
 * is accurate for that file). Otherwise, fall back to the first image but
 * caption it with its own file name — honest, if less informative, rather
 * than mislabelling a plot type it is not.
 */
export function pickFigure(images: ArtifactFile[]): PickedFigure | null {
  const volcano = images.find((f) => /^volcano/i.test(f.name));
  if (volcano) return { file: volcano, isVolcano: true };
  if (images.length > 0) return { file: images[0], isVolcano: false };
  return null;
}

/**
 * A significant-metabolite row as this component can actually populate it.
 * Only the name comes from the real payload (`significant_metabolites` is a
 * flat `string[]` — see `frontend/src/types/results.ts` and
 * `backend/src/graph_agent/use_tool/analysis_graph.py:135`). Per-metabolite
 * log2FC, FDR and pathway are not present anywhere in the structured
 * payload that reaches the frontend for *any* run, not just some rows: the
 * closest backend-side computation, `metabolite_scores` (feature_name +
 * t_score only, no fold change, FDR or pathway), is dropped before the API
 * boundary because `STRUCTURED_KEYS` in `backend/api/routers/chat.py` does
 * not include it, and `significant_metabolites.csv` (which would carry
 * those columns) does not exist outside the design mock. Following the
 * rule "we do not render columns we cannot fill", those columns are dropped entirely rather than shown as a column of em dashes —
 * a column that is empty on every row of every run is not a per-row gap,
 * it is a column that does not exist, and rendering it next to a summary
 * that cites FDR and an R block that thresholds on it would tell a
 * physician the exact opposite of what the R code actually does.
 */
export default function AnalysisHighlights({
  analysisResult, significantMetabolites, images, isLoading, isError, errorDetail, onRetry,
}: Props) {
  const { t } = useT();
  const [showCode, setShowCode] = useState(false);

  const rCode = typeof analysisResult?.r_code === "string" ? analysisResult.r_code : "";
  const metabolites = significantMetabolites ?? [];
  const picked = pickFigure(images);

  return (
    <div>
      <figure style={{ margin: "0 0 var(--space-4)" }}>
        {isError ? (
          <ErrorCard detail={errorDetail ?? t("error.network")} onRetry={onRetry} />
        ) : (
          <div
            style={{
              width: "100%",
              aspectRatio: "16 / 9",
              position: "relative",
              border: "1px solid var(--color-divider)",
              background: "var(--color-neutral-100)",
            }}
          >
            {isLoading ? (
              // The fetch this figure depends on is still in flight —
              // distinct from "fetched successfully, no image" below, which
              // would otherwise flash on every fresh analysis result before
              // the real figure swaps in.
              <div className="flex h-full items-center justify-center text-[12px] text-neutral-500">
                {t("common.loading")}
              </div>
            ) : picked ? (
              <img
                src={`${API_BASE}${picked.file.path}`}
                alt={picked.file.name}
                className="h-full w-full object-contain"
              />
            ) : (
              // Fetched successfully and there is genuinely no image (still
              // running before any figure node completed, or the node
              // failed before producing one). The box keeps its 16:9
              // footprint — collapsing to zero height would read as a
              // layout bug rather than "no figure", and a broken-image icon
              // would look like a fetch failure rather than an absent
              // result.
              <div className="flex h-full items-center justify-center text-[12px] text-neutral-500">
                {t("result.noFiles")}
              </div>
            )}
          </div>
        )}
        {!isError && picked && (
          <figcaption>{picked.isVolcano ? t("result.fig1") : picked.file.name}</figcaption>
        )}
      </figure>

      {metabolites.length > 0 && (
        <div>
          <Kicker>{t("result.sigTitle")}</Kicker>
          {/* At the 380px result-panel floor a wide table can exceed the
              available width. Scrolling sideways inside its own box keeps
              it legible instead of squeezing — the same convention
              IdMappingTable and MarkdownReport use for their own wide
              tables. */}
          <div className="mt-[var(--space-2)] overflow-x-auto">
            <table className="table" style={{ fontVariantNumeric: "tabular-nums" }}>
              <thead>
                <tr>
                  <th>{t("result.colName")}</th>
                </tr>
              </thead>
              <tbody>
                {metabolites.map((name) => (
                  <tr key={name}>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>{name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {rCode && (
        <div
          style={{
            marginTop: "var(--space-4)",
            borderTop: "1px solid var(--color-divider)",
            paddingTop: "var(--space-3)",
          }}
        >
          <button
            type="button"
            className="btn btn-ghost"
            style={{ paddingLeft: 0 }}
            aria-expanded={showCode}
            onClick={() => setShowCode((v) => !v)}
          >
            {t("result.showRCode")}
          </button>
          {showCode && (
            <pre
              style={{
                margin: "var(--space-2) 0 0",
                padding: "var(--space-3)",
                border: "1px solid var(--color-divider)",
                background: "var(--color-neutral-100)",
                fontSize: "12px",
                lineHeight: 1.7,
                overflowX: "auto",
                whiteSpace: "pre",
              }}
            >
              {rCode}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
