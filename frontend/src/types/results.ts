export type ArtifactFile = {
  name: string;
  path: string;
  kind: "md" | "image" | "csv" | "other";
  size: number;
};

export type ArtifactsResponse = {
  folder: string;
  files: ArtifactFile[];
  markdown: Record<string, string>;
};

// `ms` is optional: threads persisted before this field existed have none,
// and `AgentTrace` must render those steps with a blank duration rather
// than a computed or default value.
export type TraceStep = { seq: number; raw: string; ms?: number };

export type ResultBlockData = {
  analysis_result?: Record<string, unknown>;
  review_result?: Array<Record<string, unknown>>;
  id_mapping_result?: Array<Record<string, unknown>>;
  literature_result?: Record<string, unknown>;
  significant_metabolites?: string[];
  /** All significant features (FDR < 0.05): named metabolites plus bare m/z
   * features, i.e. the true total `significant_metabolites` alone does not
   * carry (see that field's own note in `ResultCard.tsx`'s `summaryFor`).
   * Bound to `MainState.sig_all` (`backend/src/graph_agent/state.py`).
   * Optional, not just typed loosely: threads persisted before this field
   * existed have no `sig_all` in their stored payload at all, and
   * `ResultCard` must fall back to the identified-only headline rather than
   * render a wrong or missing number for those. */
  sig_all?: string[];
};
