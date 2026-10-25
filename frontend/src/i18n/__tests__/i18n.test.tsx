import { describe, expect, it, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { LocaleProvider, useT } from "../LocaleContext";
import { statusLabel } from "../statusLabels";
import { zh } from "../messages/zh";
import { en } from "../messages/en";

function Probe() {
  const { t, locale, setLocale } = useT();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="title">{t("nav.home")}</span>
      <span data-testid="interp">{t("result.literatureFunnel", { found: 2, kept: 5 })}</span>
      <button onClick={() => setLocale("en")}>en</button>
    </div>
  );
}

// Kept separate from Probe: only this component ever touches a missing-key
// `t()` call, so other tests don't incidentally trigger the
// `[i18n] missing copy key` console.warn noise.
function MissingKeyProbe() {
  const { t } = useT();
  return <span data-testid="missing">{t("nope.not.here")}</span>;
}

describe("i18n", () => {
  it("defaults to zh and fetches the Chinese copy", () => {
    render(<LocaleProvider><Probe /></LocaleProvider>);
    expect(screen.getByTestId("locale")).toHaveTextContent("zh");
    expect(screen.getByTestId("title").textContent).toBeTruthy();
    expect(screen.getByTestId("title").textContent).not.toBe("nav.home");
  });

  it("returns the key itself and warns on the console when the key is missing", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<LocaleProvider><MissingKeyProbe /></LocaleProvider>);
    expect(screen.getByTestId("missing")).toHaveTextContent("nope.not.here");
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("supports variable interpolation", () => {
    render(<LocaleProvider><Probe /></LocaleProvider>);
    expect(screen.getByTestId("interp").textContent).toContain("2");
    expect(screen.getByTestId("interp").textContent).toContain("5");
  });

  it("writes to localStorage after switching locale, without reloading", () => {
    render(<LocaleProvider><Probe /></LocaleProvider>);
    act(() => { screen.getByText("en").click(); });
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
    expect(localStorage.getItem("metabosquad.locale")).toBe("en");
  });

  it("reads the initial value from localStorage", () => {
    localStorage.setItem("metabosquad.locale", "en");
    render(<LocaleProvider><Probe /></LocaleProvider>);
    expect(screen.getByTestId("locale")).toHaveTextContent("en");
  });
});

describe("statusLabel", () => {
  it("translates the backend's English status into Chinese in zh mode", () => {
    const label = statusLabel(
      "Parameter extraction complete, statistical analysis in progress.", "zh");
    expect(label).toContain("統計分析");
  });

  it("returns the backend's original text as-is in en mode", () => {
    const raw = "Plot review is in progress...";
    expect(statusLabel(raw, "en")).toBe(raw);
  });

  it("returns the original text rather than an empty string when no mapping is found", () => {
    expect(statusLabel("Some brand new status", "zh")).toBe("Some brand new status");
  });

  it("matches a status carrying dynamic content, via a prefix match", () => {
    const label = statusLabel(
      "Significant metabolite data extraction completed (FDR < 0.05), 共 24 筆", "zh");
    expect(label).toContain("顯著代謝物");
  });
});

// `en`'s type is `Partial<Record<keyof typeof zh, string>>`, and `t()` falls
// back to `?? zh` when a key isn't found there — a deliberate safety net so
// an in-between state ("a zh key was added but its en translation hasn't
// caught up yet") still compiles and runs. But this system will eventually
// be tested by an English-language journal reviewer, and a missing en key
// shows up as "Chinese text pops up on the English interface" — completely
// silently.
//
// So the division of labour is: the type permits the in-between state, and
// this test surfaces the outstanding translation before merge. Without this
// test, a missed en translation produces no output to warn anyone.
describe("zh / en key parity in the messages tables", () => {
  it("every zh key has a corresponding en translation", () => {
    const missing = Object.keys(zh).filter((k) => !(k in en));
    expect(missing).toEqual([]);
  });

  it("en has no extra key that doesn't exist in zh", () => {
    const extra = Object.keys(en).filter((k) => !(k in zh));
    expect(extra).toEqual([]);
  });
});

// Every screen in the redesign reads its copy from these tables. A missing key
// renders the key itself ("home.askKicker") at a physician; the console.warn
// that accompanies it is not visible to someone using the app.
const REQUIRED_KEYS = [
  "nav.brandLine",
  "home.kicker", "home.sub", "home.lede",
  "home.askKicker", "home.askHint", "home.askTry", "home.askPlaceholder",
  "home.attach", "home.capTitle", "home.capNote",
  "home.cap1Title", "home.cap1Body", "home.cap1Meta", "home.cap1Cta",
  "home.cap2Title", "home.cap2Body", "home.cap2Meta", "home.cap2Cta",
  "home.cap3Title", "home.cap3Body", "home.cap3Meta", "home.cap3Cta",
  "home.aboutStripTitle", "home.aboutStripBody", "home.aboutStripCta",
  "chat.kicker", "chat.resultPanel", "chat.attach",
  "chat.tracePulseFallback",
  "sidebar.heading", "sidebar.newChat", "sidebar.rename", "sidebar.delete",
  "sidebar.toggle", "sidebar.count", "sidebar.untitled",
  "result.kicker", "result.fig1", "result.sigTitle",
  "result.colName", "result.colPathway", "result.colFile", "result.colKind",
  "result.colSize", "result.download",
  "result.mapTitle", "result.litTitle", "result.plotTitle",
  "result.levelMust", "result.levelNice",
  "tools.kicker", "tools.title", "tools.lede", "tools.inputLabel",
  "tools.run", "tools.empty",
  "about.kicker", "about.title", "about.p1", "about.p2", "about.p3",
  "about.colophonTitle", "about.colophonFrontend", "about.colophonBackend",
  "about.colophonComputation", "about.colophonModel", "about.colophonDatabases",
  "footer.left", "footer.right",
] as const;

describe("redesign copy inventory", () => {
  it("zh defines every key the redesigned screens read", () => {
    const missing = REQUIRED_KEYS.filter((k) => !(k in zh));
    expect(missing).toEqual([]);
  });

  // Placeholders are the silent half of i18n: `{n}` present in zh but absent in
  // en renders a sentence with a hole in it, and no test or type catches it.
  it("zh and en agree on every {placeholder}", () => {
    const holes = (s: string) => (s.match(/\{[a-zA-Z]+\}/g) ?? []).sort().join(",");
    const mismatched = Object.keys(zh)
      .filter((k) => k in en)
      .filter((k) => holes(zh[k as keyof typeof zh]) !== holes(en[k as keyof typeof zh]!));
    expect(mismatched).toEqual([]);
  });
});

// A key present in both tables with byte-identical text is either a deliberate,
// locale-invariant string (a proper noun, product name or version stamp) or an
// unported translation that never got its own English wording (e.g. en.ts
// still holding a pre-redesign English string after zh.ts changed). Key
// presence and placeholder parity (both tested above) stay green in that
// exact state, so nothing else in this file catches it — this test checks
// every key in both tables.
//
// Any key that legitimately needs the same wording in both locales must be
// added below, by name, with a reason — never by weakening the assertion.
const IDENTICAL_ACROSS_LOCALES: readonly (keyof typeof zh)[] = [
  "footer.right", // version stamp, deliberately locale-invariant
  "home.sub", // English subtitle, used verbatim on the zh page too (by design)
  "home.cap2Meta", // database/vendor names, not prose
  "about.colophonFrontend", // framework/version string, not prose
  "about.colophonDatabases", // database names, not prose
  "about.colophonModel", // model name, not prose
];

describe("zh and en hold genuinely different wording", () => {
  it("no key outside the exception list has identical zh and en text", () => {
    const exceptions = new Set<string>(IDENTICAL_ACROSS_LOCALES);
    const matches = Object.keys(zh)
      .filter((k) => k in en)
      .filter((k) => !exceptions.has(k))
      .filter((k) => zh[k as keyof typeof zh] === en[k as keyof typeof zh]);
    expect(matches).toEqual([]);
  });

  // Mirrors the ratcheting pattern in comment-language.test.ts: an exception
  // that stops being identical (one locale's copy changes later) must be
  // removed from this list in the same diff, not left to rot.
  it("the exception list has no stale entries", () => {
    const stale = IDENTICAL_ACROSS_LOCALES.filter((k) => zh[k] !== en[k]);
    expect(stale).toEqual([]);
  });
});

// The "identical across locales" check above guards a *different* failure
// mode (Chinese text leaking into the English table) than a stale English
// wording. Reverting en.ts's chat.ai from "Assistant" back to an older "AI"
// does not make chat.ai's zh and en values equal — the Chinese word for
// "assistant" and "AI" were never equal — so that check alone stays green
// through exactly that regression. Key presence and placeholder parity also
// do not move: the key still exists in both tables and neither value has a
// `{placeholder}`.
//
// So the English wording for keys whose translation is easy to regress is
// pinned here directly. A future edit that updates zh but not en for one of
// these keys now has a test that actually goes red for it.
const LOCALE_DIVERGENT_PINS: Partial<Record<keyof typeof zh, string>> = {
  "chat.ai": "Assistant",
  "chat.traceDone": "{n} steps completed",

  // The entries below guard bug fixes. The same failure mode applies: a
  // plain `zh !== en` or "key exists" check stays green even if a future
  // edit reverts en.ts's wording back to the pre-fix claim while leaving
  // zh.ts alone (or vice versa), because the two strings were never equal in
  // the first place.
  // `result.significantCount` used to read "{n} significant metabolites" in
  // both locales, which reports 0 for every real run of the bundled
  // analysis_lcms dataset (it is keyed
  // entirely by m/z, so `significant_metabolites` — bound to
  // `sig_identified_metabolites` — is empty even though the backend found
  // 31 significant features) while the volcano plot directly above shows
  // roughly thirty points past both thresholds. Pinned to the relabelled,
  // identified-only wording so a revert to the old claim goes red.
  "result.significantCount": "{n} identified metabolites (see the full report for unidentified m/z features)",
  // `result.fig1` used to claim the volcano plot's y-axis is
  // "−log₁₀ FDR"; the real `volcano_0_dpi300.png` prints "-log10(p-value)"
  // with a "P-value" size legend. Pinned to the axis-accurate wording so a
  // revert to the FDR claim goes red.
  "result.fig1": "Fig. 1　Volcano plot: log₂ fold change against −log₁₀ p-value; thresholds FDR < 0.05 and |log₂FC| > 1.",

  // The live headline for every *new* analysis run is
  // `result.significantCountTotal`, not `result.significantCount` above —
  // that older key is now only the fallback for threads persisted before
  // `sig_all` existed (see `ResultCard.tsx`'s `summaryFor`). Without a pin
  // here, only the deprecated fallback path would be guarded and the string
  // every physician actually sees would be free to regress back to a bare,
  // misleading single number with every test staying green. It also carries
  // the pointer to where the unidentified m/z features actually are (the
  // full report's "List of Significant Features" section) — so reverting
  // either the two-number form or just the trailing pointer clause goes red.
  "result.significantCountTotal": "{total} significant features ({named} identified; see the full report for unidentified m/z features)",
};

describe("en pins the wording for keys that diverge from zh", () => {
  it("matches the exact pinned English text", () => {
    const wrong = Object.entries(LOCALE_DIVERGENT_PINS).filter(
      ([k, expected]) => en[k as keyof typeof zh] !== expected,
    );
    expect(wrong).toEqual([]);
  });
});
