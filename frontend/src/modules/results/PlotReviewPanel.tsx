"use client";

import { API_BASE } from "@/src/config/constants";
import Hairline from "@/src/components/Hairline";
import MarkdownReport from "./MarkdownReport";

type Review = {
  file_path?: string;
  file_name?: string;
  feedback?: string;
  warning?: string;
};

/**
 * The original figure sits beside the reviewer's written feedback — a
 * finding about a plot is not something a physician can act on without the
 * plot itself in view.
 *
 * `review_result` reaches the frontend today. `MainState`
 * (backend/src/graph_agent/state.py:33) declares
 * `review_result: list[dict[str, Any]]`, and every key in `STRUCTURED_KEYS`
 * (backend/api/routers/chat.py:41-47), including this one, is guarded by
 * `backend/tests/test_structured_keys_declared.py` against the LangGraph
 * failure mode this component's comment used to describe (an undeclared
 * channel is silently dropped, so a subgraph's return value never reaches
 * the API). That failure mode is fixed, so unlike an earlier version of this
 * comment, this one does not claim the data path is broken.
 *
 * The payload has no severity field — `Review` above is its whole shape.
 * Inferring a must-fix/suggested tag from the wording of `feedback` would put
 * a false certainty in front of a physician, so `feedback` renders as plain prose and nothing here invents a level.
 */
export default function PlotReviewPanel({ reviews }: { reviews: Review[] }) {
  if (!reviews || reviews.length === 0) return null;

  return (
    <div>
      {reviews.map((r, idx) => {
        const src = r.file_path
          ? `${API_BASE}/uploads/${r.file_path.replace(/^\/?uploads\//, "")}`
          : null;

        return (
          <div key={r.file_name ? `${r.file_name}-${idx}` : idx}>
            {idx > 0 && <Hairline />}
            <div className="grid gap-[var(--space-4)] md:grid-cols-2">
              <figure style={{ margin: 0 }}>
                {src && (
                  <img
                    src={src}
                    alt={r.file_name ?? `Figure ${idx + 1}`}
                    className="max-h-72 w-full border border-divider bg-white object-contain"
                  />
                )}
                <figcaption>{r.file_name ?? `Figure ${idx + 1}`}</figcaption>
                {r.warning && (
                  <p
                    style={{
                      marginTop: "var(--space-1)",
                      fontSize: "12px",
                      color: "var(--color-neutral-600)",
                    }}
                  >
                    {r.warning}
                  </p>
                )}
              </figure>
              <div style={{ minWidth: 0 }}>
                <MarkdownReport markdown={r.feedback ?? ""} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
