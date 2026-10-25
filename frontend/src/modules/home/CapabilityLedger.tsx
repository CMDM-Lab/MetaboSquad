"use client";

import Link from "next/link";
import { useT } from "@/src/i18n/LocaleContext";

// Positional: entries
// I (data analysis) and III (figure review) both start a conversation, entry
// II (literature & identifiers) opens the standalone tools page instead — it
// is the one capability the app also exposes outside the chat agent.
const ROMAN = ["I", "II", "III"] as const;
const HREFS = ["/chat", "/tools", "/chat"] as const;

// The three-entry capability ledger: the only statement of scope on the
// landing page. No card fills — hairlines top and bottom.
export default function CapabilityLedger() {
  const { t } = useT();

  const capabilities = ROMAN.map((num, i) => {
    const n = i + 1;
    return {
      num,
      title: t(`home.cap${n}Title`),
      body: t(`home.cap${n}Body`),
      meta: t(`home.cap${n}Meta`),
      cta: t(`home.cap${n}Cta`),
      href: HREFS[i],
    };
  });

  return (
    <section className="mt-[var(--space-8)]">
      <div className="mb-[var(--space-4)] flex items-baseline justify-between gap-[var(--space-4)]">
        <h3 className="font-normal">{t("home.capTitle")}</h3>
        <span className="text-[11px] text-[color-mix(in_srgb,var(--color-text)_50%,transparent)]">
          {t("home.capNote")}
        </span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-0 border-t border-divider">
        {capabilities.map((c) => (
          <article
            key={c.num}
            className="flex flex-col gap-[var(--space-2)] border-b border-divider pt-[var(--space-4)] pr-[var(--space-4)] pb-[var(--space-4)]"
          >
            <div className="flex items-baseline gap-[var(--space-2)]">
              <span className="font-mono text-[13px] tracking-[0.1em] tabular-nums text-accent-600">
                {c.num}
              </span>
              <h4 className="m-0 font-semibold">{c.title}</h4>
            </div>
            <p className="m-0 text-justify text-[13.5px] hyphens-auto text-[color-mix(in_srgb,var(--color-text)_78%,transparent)]">
              {c.body}
            </p>
            <div className="text-[11px] tabular-nums text-[color-mix(in_srgb,var(--color-text)_50%,transparent)]">
              {c.meta}
            </div>
            <Link href={c.href} className="self-start text-[12px]">
              {c.cta}
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
