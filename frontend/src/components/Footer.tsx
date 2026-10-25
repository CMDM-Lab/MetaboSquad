"use client";

import { useT } from "@/src/i18n/LocaleContext";

// A client boundary is required here (not just in layout.tsx) because `t()`
// depends on LocaleContext, and `layout.tsx` must stay a Server Component to
// keep its `metadata` export.
export default function Footer() {
  const { t } = useT();
  return (
    <footer className="flex flex-wrap items-baseline justify-between gap-[var(--space-4)] border-t border-divider px-[var(--space-6)] py-[var(--space-4)] text-[11px] text-neutral-600">
      <span>{t("footer.left")}</span>
      <span className="tabular-nums">{t("footer.right")}</span>
    </footer>
  );
}
