import type { ReactNode } from "react";

type KickerSize = "sm" | "md";
type KickerTone = "accent" | "faint";

// Kicker is the only place allowed below 12px, and only because it is an
// uppercase mono label (the design sets kickers at 9.5-11px, uppercase).
const SIZE_CLASS: Record<KickerSize, string> = {
  sm: "text-[9.5px]",
  md: "text-[11px]",
};

const TONE_CLASS: Record<KickerTone, string> = {
  accent: "text-accent-700",
  faint: "text-neutral-500",
};

export default function Kicker({
  children,
  size = "sm",
  tone = "accent",
}: {
  children: ReactNode;
  size?: KickerSize;
  tone?: KickerTone;
}) {
  return (
    // `textTransform` is also set inline (redundant with the `uppercase`
    // utility class below): jsdom's `getComputedStyle` in the test
    // environment does not evaluate Tailwind's compiled stylesheet, only
    // inline styles, so the inline declaration is what makes the
    // "uppercased by CSS, not by the caller" test meaningful in CI.
    <span
      className={`font-mono uppercase tracking-[0.14em] ${SIZE_CLASS[size]} ${TONE_CLASS[tone]}`}
      style={{ textTransform: "uppercase" }}
    >
      {children}
    </span>
  );
}
