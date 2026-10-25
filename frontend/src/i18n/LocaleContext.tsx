"use client";

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import { zh } from "./messages/zh";
import { en } from "./messages/en";

export type Locale = "zh" | "en";
export const LOCALE_KEY = "metabosquad.locale";

type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const LocaleCtx = createContext<Ctx | null>(null);

function interpolate(template: string, vars?: Record<string, string | number>) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    name in vars ? String(vars[name]) : whole,
  );
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");

  // Reads the initial value from localStorage. Kept inside an effect to avoid an SSR/CSR hydration mismatch.
  useEffect(() => {
    const stored = window.localStorage.getItem(LOCALE_KEY);
    if (stored === "zh" || stored === "en") setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-Hant";
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    window.localStorage.setItem(LOCALE_KEY, l);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const dict = locale === "en" ? en : zh;
      const value =
        (dict as Record<string, string>)[key] ??
        (zh as Record<string, string>)[key];
      if (value === undefined) {
        console.warn(`[i18n] 缺少文案 key: ${key}`);
        return key;
      }
      return interpolate(value, vars);
    },
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <LocaleCtx.Provider value={value}>{children}</LocaleCtx.Provider>;
}

export function useT(): Ctx {
  const ctx = useContext(LocaleCtx);
  if (!ctx) throw new Error("useT 必須在 LocaleProvider 內使用");
  return ctx;
}
