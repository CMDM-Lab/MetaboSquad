// The thread's right-hand result panel (layout B). This is a dumb
// 380px container: it renders the `chat.resultPanel` kicker and hands
// everything else to its children. It does not know what a "result" is —
// ChatWindow decides which intent, if any, belongs here.
//
// The flex/min-width/border/padding declarations are written as inline
// styles rather than Tailwind classes because they are exactly the
// layout-critical values `src/__tests__` needs jsdom's `toHaveStyle` to see
// (mirrors the 520px conversation column in ChatWindow.tsx) and because
// they are exact values from the design.

"use client";

import type { ReactNode } from "react";
import { useT } from "@/src/i18n/LocaleContext";
import Kicker from "@/src/components/Kicker";

export default function ResultPanelShell({ children }: { children: ReactNode }) {
  const { t } = useT();

  return (
    <aside
      data-testid="result-panel"
      style={{
        flex: "1 1 380px",
        minWidth: "min(100%, 380px)",
        borderLeft: "1px solid var(--color-divider)",
        padding: "18.4px",
        background: "color-mix(in srgb, var(--color-surface) 55%, transparent)",
      }}
    >
      <div className="mb-[var(--space-3)]">
        <Kicker size="sm" tone="faint">{t("chat.resultPanel")}</Kicker>
      </div>
      {children}
    </aside>
  );
}
