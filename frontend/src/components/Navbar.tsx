"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/src/i18n/LocaleContext";

export default function Navbar() {
  const pathname = usePathname();
  const { t, locale, setLocale } = useT();
  const navItems = [
    { name: t("nav.home"), href: "/" },
    { name: t("nav.chat"), href: "/chat" },
    { name: t("nav.tools"), href: "/tools" },
    { name: t("nav.about"), href: "/about" },
  ];

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-[var(--space-6)] border-b border-neutral-900 bg-[color-mix(in_srgb,var(--color-bg)_92%,transparent)] px-[var(--space-6)] py-[var(--space-3)] backdrop-blur-[6px]">
      <Link
        href="/"
        className="flex flex-col leading-[1.05] text-text no-underline"
      >
        <span className="text-[20px] font-medium tracking-[0.01em]">MetaboSquad</span>
        <span className="font-mono text-[9.5px] font-normal tracking-[0.18em] uppercase text-neutral-600">
          {t("nav.brandLine")}
        </span>
      </Link>

      {/* Named so this isn't a second unnamed navigation landmark alongside
          any other <nav> the page may render (e.g. Sidebar in /chat). */}
      <nav aria-label="Primary" className="flex items-center gap-[var(--space-4)]">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`border-b border-transparent pb-[2px] text-[13.5px] tracking-[0.02em] no-underline hover:border-accent-600 ${
                isActive ? "border-accent-600 text-accent-600" : "text-text"
              }`}
            >
              {item.name}
            </Link>
          );
        })}
      </nav>

      <button
        type="button"
        onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
        aria-label="switch language"
        className="btn btn-secondary min-w-[44px]"
      >
        {locale === "zh" ? "EN" : "中"}
      </button>
    </header>
  );
}
