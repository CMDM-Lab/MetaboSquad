// A single 1px rule. Elevation in this design is always a hairline, never a
// shadow, so this component is the one place that appearance is defined —
// callers choose the divider hairline (default) or the ink-dark rule via
// `ink`, and never reach for inline styles.
export default function Hairline({ ink = false }: { ink?: boolean }) {
  return <hr className={ink ? "hr hr-ink" : "hr"} />;
}
