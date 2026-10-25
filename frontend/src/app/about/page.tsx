"use client";

import { useT } from "@/src/i18n/LocaleContext";
import Kicker from "@/src/components/Kicker";
import Hairline from "@/src/components/Hairline";
import Colophon from "@/src/modules/about/Colophon";

export default function AboutPage() {
  const { t } = useT();

  return (
    <div className="mx-auto w-full max-w-[960px] px-[var(--space-6)] py-[var(--space-8)]">
      <Kicker size="md">{t("about.kicker")}</Kicker>
      <h2 className="mt-[var(--space-2)] mb-[var(--space-6)] text-[28px]">
        {t("about.title")}
      </h2>

      {/* `columns`/`column-gap`/`column-rule` are layout-critical and a test
          observes them via toHaveStyle, so — per this codebase's convention
          for declarations a test reads directly — they are inline styles
          rather than Tailwind utilities. */}
      <div
        data-testid="about-columns"
        style={{
          columns: "2",
          columnGap: "36.8px",
          columnRule: "1px solid var(--color-divider)",
        }}
        className="text-justify text-[14px] hyphens-auto"
      >
        <p>{t("about.p1")}</p>
        <p>{t("about.p2")}</p>
        <p className="mb-0">{t("about.p3")}</p>
      </div>

      <Hairline />

      <h4 className="mb-[var(--space-3)]">{t("about.colophonTitle")}</h4>
      <Colophon />
    </div>
  );
}
