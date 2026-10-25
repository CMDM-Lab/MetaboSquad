import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const SRC = path.resolve(__dirname, "..");

// Files not yet converted to the clinical token layer. Every source file has
// been converted, so the list is empty. It is kept as a `const []` so a
// future regression has somewhere to be listed. The second test below fails
// if an entry is stale, so the list can only shrink — a converted file
// cannot quietly stay listed, and a regression in a converted file cannot be
// silenced by re-adding it without the diff showing it.
export const LEGACY_STYLE_ALLOWLIST: readonly string[] = [];

const RULES: ReadonlyArray<readonly [string, RegExp]> = [
  ["dark: variant (there is no dark mode)", /\bdark:/],
  // A Tailwind `dark:` variant can only ever appear in
  // `.tsx` class strings, but a `@media (prefers-color-scheme: dark)` block
  // is plain CSS and would slip past that rule entirely if it landed in
  // globals.css. Same "no dark mode" invariant, the shape CSS actually uses.
  ["prefers-color-scheme: dark (there is no dark mode)", /prefers-color-scheme:\s*dark/],
  ["rounded utility other than rounded-full", /\brounded-(?!full\b)[a-z0-9[]/],
  ["shadow utility (elevation is a 1px rule)", /\bshadow-(?!none\b)[a-z0-9[]/],
  [
    "Tailwind default palette family",
    /\b(?:text|bg|border|ring|from|to|via|fill|stroke|decoration|outline|divide|placeholder|caret|accent)-(?:slate|gray|zinc|stone|blue|indigo|violet|purple|sky|cyan|teal|emerald|green|lime|yellow|amber|orange|red|rose|pink|fuchsia)-\d/,
  ],
  ["raw hex colour in a component", /#[0-9a-fA-F]{3,8}\b/],
];

// Applied only to `.tsx?` files: `globals.css` is the source of truth for
// every design token (`--accent-*`, `--neutral-*`, ...) and necessarily
// declares them as literal hex — that is expected and correct there, not a
// "raw hex in a component" violation.
const CSS_EXEMPT_RULE_LABELS: ReadonlySet<string> = new Set([
  "raw hex colour in a component",
]);

// `fs.globSync` does not exist on this repo's Node (v20.19.4); `readdirSync`
// with `recursive: true` does. Do not "modernise" this to globSync — it fails
// at runtime with `globSync is not a function`, which reads like a test-harness
// problem rather than a version problem.
function sources(): string[] {
  return readdirSync(SRC, { recursive: true, encoding: "utf8" })
    // `.css` is in scope too: walking `.ts`/`.tsx` only would let a
    // `@media (prefers-color-scheme: dark)` block or any other CSS-only
    // violation in globals.css pass unnoticed.
    .filter((p) => /\.tsx?$/.test(p) || /\.css$/.test(p))
    .map((p) => p.split(path.sep).join("/"))
    .filter((p) => !p.includes("__tests__") && !p.startsWith("i18n/messages/"));
}

function violations(rel: string): string[] {
  const text = readFileSync(path.join(SRC, rel), "utf8");
  const isCss = rel.endsWith(".css");
  const found: string[] = [];
  text.split("\n").forEach((line, i) => {
    for (const [label, re] of RULES) {
      if (isCss && CSS_EXEMPT_RULE_LABELS.has(label)) continue;
      if (re.test(line)) found.push(`src/${rel}:${i + 1} — ${label}`);
    }
  });
  return found;
}

describe("clinical token layer", () => {
  it("no converted file violates the visual invariants", () => {
    const allow = new Set(LEGACY_STYLE_ALLOWLIST);
    const offences = sources()
      .filter((rel) => !allow.has(rel))
      .flatMap(violations);
    expect(offences).toEqual([]);
  });

  // Without this, a task could convert a file and leave it allowlisted; the
  // next regression in that file would then be silent. A stale entry is a
  // failure, so the ratchet only turns one way.
  it("the allowlist has no stale entries", () => {
    const stale = LEGACY_STYLE_ALLOWLIST.filter((rel) => violations(rel).length === 0);
    expect(stale).toEqual([]);
  });
});

// CSS cascade layers rank *every* unlayered declaration
// above *every* layered one, regardless of selector specificity — a bare
// top-level rule in globals.css permanently wins over a same-element class
// selector declared inside `@layer components`, even where specificity alone
// would say the class should win. That is exactly how a prior bug shipped: a
// plain `a { color }` rule permanently beat `.btn-primary`'s layered colour,
// making the home page's CTA button text invisible against its own fill.
// A test that only re-checked that specific `a`/`.btn-primary` pairing would
// not catch the same class of bug on any other bare selector, so this
// instead pins the invariant that makes the bug class impossible: no plain
// style rule in globals.css may sit outside an `@layer` block. jsdom does
// not implement cascade layer priority at all, so this has to be a
// source-structure assertion — a computed-style comparison in jsdom would
// not reproduce the bug either way.
describe("CSS cascade layers", () => {
  const GLOBALS_CSS = path.join(SRC, "app/globals.css");

  // Exemptions, both narrow and justified: `:root` and `@theme` only ever
  // declare custom properties / Tailwind build-time design tokens, never a
  // property that competes against a `.btn`/`.input`/`.table`/`.tag`/`.hr`/
  // `.field` declaration for the same element — so leaving them at the top
  // level (the idiomatic Tailwind v4 layout, and how `@theme` is required to
  // appear) cannot reproduce this bug regardless of layer.
  const EXEMPT = [/^@theme\b/, /^:root\b/];

  // Walks the raw text once, tracking brace depth, and records the "header"
  // (selector or at-rule prelude) of every block that opens at depth 0 —
  // i.e. every rule that is NOT nested inside another block such as
  // `@layer ... { }`. A bare `@import "...";` statement has no body, so it
  // never opens a block and is correctly never recorded.
  function topLevelHeaders(cssText: string): string[] {
    const text = cssText.replace(/\/\*[\s\S]*?\*\//g, "");
    const headers: string[] = [];
    let depth = 0;
    let buf = "";
    for (const ch of text) {
      if (depth === 0) {
        if (ch === "{") {
          headers.push(buf.trim());
          buf = "";
          depth = 1;
        } else if (ch === ";") {
          buf = "";
        } else {
          buf += ch;
        }
      } else {
        if (ch === "{") depth++;
        else if (ch === "}") depth--;
      }
    }
    return headers.filter((h) => h.length > 0);
  }

  it("every rule in globals.css sits inside an @layer block", () => {
    const css = readFileSync(GLOBALS_CSS, "utf8");
    const headers = topLevelHeaders(css);
    const offenders = headers.filter(
      (h) => !h.startsWith("@layer") && !EXEMPT.some((re) => re.test(h)),
    );
    expect(offenders).toEqual([]);
  });

  // Regression coverage for the parser itself: a rule that IS correctly
  // layered must not be flagged, and a rule left bare at the top level must
  // be. Uses an in-memory fixture so it doesn't depend on globals.css's
  // current contents staying exactly as they are.
  it("topLevelHeaders flags a bare rule but not a layered one", () => {
    const fixture = `
      :root { --x: 1; }
      @theme inline { --y: 2; }
      @layer base {
        a { color: red; }
      }
      body { color: blue; }
    `;
    expect(topLevelHeaders(fixture)).toEqual(
      expect.arrayContaining(["body"]),
    );
    expect(topLevelHeaders(fixture)).not.toEqual(
      expect.arrayContaining(["a"]),
    );
  });
});
