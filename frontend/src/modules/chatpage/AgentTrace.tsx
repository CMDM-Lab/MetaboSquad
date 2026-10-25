"use client";

import { useState } from "react";
import { useT } from "@/src/i18n/LocaleContext";
import { statusLabel } from "@/src/i18n/statusLabels";
import type { TraceStep } from "@/src/types/results";

type Props = {
  steps: TraceStep[];
  running: boolean;
};

/**
 * Formats a step's duration for the trace table's mono duration column.
 * Kept local to this component — nothing else in the app needs it yet.
 * `<1000` and `<60000` both render one decimal second (e.g. "0.4 s",
 * "22.3 s"); `>=60000` switches to "1 min 12 s".
 */
function formatMs(ms: number): string {
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} min ${seconds} s`;
}

/**
 * The agent's execution trace, rendered as two layers.
 *
 * Layer 1 is always visible: a pulsing dot while running, one plain-
 * language sentence for the current (or, once finished, the completed)
 * state, and a toggle for Layer 2. This is how a physician tells the
 * system has not died mid-analysis — a 22-second statistical test and a
 * 0.3-second intent classification must not look identical, which is why
 * Layer 2's rows carry a per-step duration.
 *
 * Layer 2 (expanded) is the step-by-step `<ol>` with mono index, the
 * translated step sentence, and the formatted duration — the source
 * material for the thesis's "Agent Reasoning Traces" figure.
 */
export default function AgentTrace({ steps, running }: Props) {
  const { t, locale } = useT();
  const [open, setOpen] = useState(false);

  // Nothing has happened yet and nothing is running: there is no trace to
  // show. Once running starts, even with zero steps so far, Layer 1 still
  // renders (the pulse + the fallback sentence) — see the sentence below.
  if (steps.length === 0 && !running) return null;

  const lastStep = steps.length > 0 ? steps[steps.length - 1] : null;
  const headline = running
    ? lastStep
      ? statusLabel(lastStep.raw, locale)
      : t("chat.tracePulseFallback")
    : t("chat.traceDone", { n: steps.length });

  return (
    <div
      style={{ borderLeft: "2px solid var(--color-accent)", paddingLeft: "var(--space-4)" }}
    >
      <div className="flex flex-wrap items-center gap-[var(--space-2)]">
        {running && (
          <span
            data-testid="trace-pulse"
            aria-hidden="true"
            className="trace-pulse h-[7px] w-[7px] shrink-0 rounded-full bg-accent-600"
          />
        )}
        <span className="text-[14.5px] font-semibold">{headline}</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="btn btn-ghost text-[12px]"
        >
          {open ? t("chat.traceCollapse") : t("chat.traceExpand")}
        </button>
      </div>

      {open && steps.length > 0 && (
        <ol className="mt-[var(--space-3)] grid list-none gap-[var(--space-2)] p-0">
          {steps.map((step) => (
            <li
              key={step.seq}
              className="grid grid-cols-[22px_1fr_auto] items-baseline gap-[var(--space-3)] text-[12.5px]"
            >
              <span className="text-right font-mono text-accent-700 tabular-nums">
                {step.seq}
              </span>
              <span className="text-neutral-700">{statusLabel(step.raw, locale)}</span>
              <span
                data-testid={`trace-duration-${step.seq}`}
                className="font-mono text-[11px] tabular-nums text-neutral-500"
              >
                {typeof step.ms === "number" ? formatMs(step.ms) : ""}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
