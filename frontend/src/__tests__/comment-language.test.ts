import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const SRC = path.resolve(__dirname, "..");

// CJK Unified Ideographs plus the CJK punctuation/full-width block used for
// Chinese prose (ideographic space through the CJK symbols & punctuation range).
const CJK = /[一-鿿　-〿]/;

// Ledger of files with a Chinese-language `//` or `/* */` comment, exempt
// from the scan below. Empty: every source file's comments are English.
// Test files and `i18n/messages/*.ts` are included in this scan, unlike the
// style scan in design-tokens.test.ts: this ledger tracks comment language,
// not visual invariants, and copy tables still carry ordinary code comments.
// Kept as a `const []` rather than deleted so a future regression has
// somewhere to be listed and the two tests below keep meaning: the second
// one guards against an entry being re-added for a file that no longer
// needs it.
export const LEGACY_COMMENT_ALLOWLIST: readonly string[] = [];

// `fs.globSync` does not exist on this repo's Node (v20.19.4); `readdirSync`
// with `recursive: true` does (see design-tokens.test.ts for the same note).
function sources(): string[] {
  return readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .filter((p) => /\.tsx?$/.test(p))
    .map((p) => p.split(path.sep).join("/"));
}

// Single-pass scanner over the RAW (unstripped) source text. It walks the
// text once, tracking whether the cursor is currently inside code, a
// string/template literal, or a comment, and only ever tests characters for
// CJK while inside one of the two comment states.
//
// Ordering is the whole point. An earlier version ran a whole-file
// literal-stripping pass — replacing every quoted substring with spaces —
// BEFORE identifying comment boundaries, then scanned the stripped text for
// comments. That blanked CJK text that happened to sit inside quotes within
// a `//` or `/* */` comment before the CJK scan ever ran, so a comment that
// quoted a Chinese answer-scale label (e.g. a Likert-scale option like
// "1 strongly disagree", written in the original language inside the
// quotes) produced zero violations: the comment itself carried an
// untranslated Chinese quotation that escaped detection entirely.
// Fixed here by identifying comment regions first and only ever treating
// literal contents specially while inside CODE (see the "string"/"template"
// states below, which exist solely so a `//` or `/*` inside a code string
// like `"http://x"` is not mistaken for the start of a comment) — never
// inside an already-open comment, where quote characters are just text.
function cjkCommentLines(text: string): number[] {
  type State = "code" | "string" | "template" | "line-comment" | "block-comment";
  let state: State = "code";
  let stringQuote = "";
  let line = 1;
  let commentBuf = "";
  const found: number[] = [];

  const flush = () => {
    if (CJK.test(commentBuf)) found.push(line);
    commentBuf = "";
  };

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (ch === "\n") {
      if (state === "line-comment") {
        flush();
        state = "code";
      } else if (state === "block-comment") {
        flush(); // a CJK line inside a multi-line block comment still counts
      } else if (state === "string") {
        // An unescaped newline inside a single/double-quoted string is a
        // syntax error in real TS source; recover to `code` rather than let
        // one malformed file suppress the rest of the scan.
        state = "code";
      }
      line++;
      continue;
    }

    if (state === "code") {
      if (ch === "/" && text[i + 1] === "/") {
        state = "line-comment";
        i++;
      } else if (ch === "/" && text[i + 1] === "*") {
        state = "block-comment";
        i++;
      } else if (ch === '"' || ch === "'") {
        state = "string";
        stringQuote = ch;
      } else if (ch === "`") {
        state = "template";
      }
    } else if (state === "string") {
      if (ch === "\\") i++;
      else if (ch === stringQuote) state = "code";
    } else if (state === "template") {
      // Template literals may legitimately span multiple lines (the `\n`
      // branch above does not reset this state), matching real backtick
      // string semantics.
      if (ch === "\\") i++;
      else if (ch === "`") state = "code";
    } else if (state === "line-comment") {
      commentBuf += ch;
    } else if (state === "block-comment") {
      if (ch === "*" && text[i + 1] === "/") {
        commentBuf += "*/";
        i++;
        flush();
        state = "code";
      } else {
        commentBuf += ch;
      }
    }
  }
  if (state === "line-comment" || state === "block-comment") flush();

  return found;
}

function violations(rel: string): string[] {
  const text = readFileSync(path.join(SRC, rel), "utf8");
  return cjkCommentLines(text).map(
    (lineNo) => `src/${rel}:${lineNo} — CJK character in comment`,
  );
}

describe("comment language", () => {
  it("no unlisted file has a CJK comment", () => {
    const allow = new Set(LEGACY_COMMENT_ALLOWLIST);
    const offences = sources()
      .filter((rel) => !allow.has(rel))
      .flatMap(violations);
    expect(offences).toEqual([]);
  });

  // Mirrors design-tokens.test.ts: a file that no longer has a CJK comment
  // must be removed from the ledger in the same diff that cleaned it up.
  it("the allowlist has no stale entries", () => {
    const stale = LEGACY_COMMENT_ALLOWLIST.filter((rel) => violations(rel).length === 0);
    expect(stale).toEqual([]);
  });
});

describe("cjkCommentLines — same-line block-then-line comment", () => {
  // Regression test: a `/* */` block comment that closes mid-line used to
  // make the scanner stop looking at that line entirely, so a `//` comment
  // trailing it on the same line was invisible to the tripwire. This uses an
  // in-memory fixture rather than a real source file, so it doesn't itself
  // trip "no unlisted file has a CJK comment".
  it("still detects a CJK `//` comment that follows a closed `/* */` on the same line", () => {
    const found = cjkCommentLines("const x = 1; /* note */ // 中文說明\n");
    expect(found).toEqual([1]);
  });
});

describe("cjkCommentLines — CJK quoted inside a comment", () => {
  // Regression test: a whole-file literal-stripping
  // pass run before comment identification blanks a quoted CJK phrase before
  // the CJK scan ever sees it, so a Chinese quotation living inside a `//`
  // comment escaped detection entirely. Mutation-checked by temporarily
  // restoring the old strip-then-scan ordering — this test goes red against
  // it, since the whole-file pass blanks the quotes (and their contents)
  // before any comment boundary is known.
  it("detects a CJK phrase quoted inside a `//` comment", () => {
    const found = cjkCommentLines('// see "1　非常不同意"\n');
    expect(found).toEqual([1]);
  });

  it("detects a CJK phrase quoted inside a `/* */` comment", () => {
    const found = cjkCommentLines('/* legacy label was "尚未開始" */\n');
    expect(found).toEqual([1]);
  });

  it("does not flag a CJK string literal that sits in code, not a comment", () => {
    const found = cjkCommentLines('const label = "尚未開始"; // ok, plain English note\n');
    expect(found).toEqual([]);
  });

  it("does not mistake `//` inside a code string literal for the start of a comment", () => {
    const found = cjkCommentLines('const url = "http://example.com/中文路徑"; // fine, no CJK here\n');
    expect(found).toEqual([]);
  });
});

// Neither ratchet above looks at `describe`/`it`/`test` title strings, and
// test titles are required to be English too. Without this scan, Chinese
// test titles can accumulate undetected. This is a separate scan from the
// CJK-comment one above: it only ever looks at the title argument of a
// describe/it/test call, never the test body, so a test body that
// legitimately asserts on real Chinese i18n copy is untouched (deliberately
// not spelled out as a literal example here — this file's own comments are
// subject to the CJK-comment scan above, and an inline Chinese example would
// trip it; see this test file's own "does not flag an English it() title..."
// fixture below for a concrete instance).

// Ledger mirrors LEGACY_COMMENT_ALLOWLIST's shape: shrink-only, and the
// second test below fails if an entry goes stale. Empty because every test
// title is English.
export const LEGACY_TEST_TITLE_ALLOWLIST: readonly string[] = [];

// Recognises a `describe`/`it`/`test` call opener (including
// `.only`/`.skip`/`.todo`/`.each(...)` chained variants) sitting at the very
// end of the code seen so far, right before a string/template literal opens.
const CALL_OPENER_RE =
  /\b(?:describe|it|test)(?:\.(?:only|skip|todo|concurrent|each\([^)]*\))?)*\s*\(\s*$/;

// Single-pass scanner over the RAW text, deliberately mirroring
// `cjkCommentLines`'s state machine rather than a plain regex. A plain regex
// matching `it("...")`-shaped text anywhere in the file would itself be
// fooled by this very file's own fixtures below, which pass a *string*
// containing the literal text `it("...")` as sample input to
// `titleCjkLines` — a naive scan can't tell that occurrence is nested data,
// not a real top-level call, the same "ordering matters" lesson that
// applies to CSS layers. Tracking `code`/`string`/`template`/
// comment state directly avoids it: a call opener is only recognised while
// in `code` state, so a quote sitting inside an already-open string is never
// mistaken for the start of a new one.
function titleCjkLines(text: string): number[] {
  type State = "code" | "string" | "template" | "line-comment" | "block-comment";
  let state: State = "code";
  let stringQuote = "";
  let line = 1;
  let codeTail = "";
  let capturingTitle = false;
  let titleBuf = "";
  let titleStartLine = 0;
  const found: number[] = [];

  const closeTitleIfCapturing = () => {
    if (capturingTitle && CJK.test(titleBuf)) found.push(titleStartLine);
    capturingTitle = false;
    titleBuf = "";
  };

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (ch === "\n") {
      line++;
      if (state === "line-comment") state = "code";
      if (state === "string") state = "code"; // malformed source recovery, see cjkCommentLines
      continue;
    }

    if (state === "code") {
      if (ch === "/" && text[i + 1] === "/") {
        state = "line-comment";
        i++;
        codeTail = "";
      } else if (ch === "/" && text[i + 1] === "*") {
        state = "block-comment";
        i++;
        codeTail = "";
      } else if (ch === '"' || ch === "'") {
        capturingTitle = CALL_OPENER_RE.test(codeTail);
        titleBuf = "";
        titleStartLine = line;
        state = "string";
        stringQuote = ch;
        codeTail = "";
      } else if (ch === "`") {
        capturingTitle = CALL_OPENER_RE.test(codeTail);
        titleBuf = "";
        titleStartLine = line;
        state = "template";
        codeTail = "";
      } else {
        // Bounded tail of recent code text, just enough to test the call
        // opener pattern against.
        codeTail = (codeTail + ch).slice(-80);
      }
    } else if (state === "string" || state === "template") {
      if (ch === "\\") {
        if (capturingTitle) titleBuf += ch + (text[i + 1] ?? "");
        i++;
      } else if ((state === "string" && ch === stringQuote) || (state === "template" && ch === "`")) {
        closeTitleIfCapturing();
        state = "code";
      } else if (capturingTitle) {
        titleBuf += ch;
      }
    } else if (state === "block-comment") {
      if (ch === "*" && text[i + 1] === "/") {
        state = "code";
        i++;
      }
    }
    // "line-comment": nothing to do per character; the `\n` branch above exits it.
  }

  return found;
}

function titleViolations(rel: string): string[] {
  const text = readFileSync(path.join(SRC, rel), "utf8");
  return titleCjkLines(text).map(
    (lineNo) => `src/${rel}:${lineNo} — CJK character in describe/it/test title`,
  );
}

describe("test title language", () => {
  it("no unlisted file has a CJK describe/it/test title", () => {
    const allow = new Set(LEGACY_TEST_TITLE_ALLOWLIST);
    const offences = sources()
      .filter((rel) => !allow.has(rel))
      .flatMap(titleViolations);
    expect(offences).toEqual([]);
  });

  // Mirrors the other two ratchets: a file that no longer has a CJK test
  // title must be removed from the ledger in the same diff that cleaned it
  // up.
  it("the allowlist has no stale entries", () => {
    const stale = LEGACY_TEST_TITLE_ALLOWLIST.filter(
      (rel) => titleViolations(rel).length === 0,
    );
    expect(stale).toEqual([]);
  });
});

describe("titleCjkLines — fixture regression", () => {
  it("detects a CJK it() title", () => {
    const found = titleCjkLines('it("顯示代謝物名稱與 CID", () => {});\n');
    expect(found).toEqual([1]);
  });

  it("detects a CJK describe() title", () => {
    const found = titleCjkLines('describe("側邊欄", () => {});\n');
    expect(found).toEqual([1]);
  });

  // The whole point of scanning only the title argument: a test body that
  // legitimately asserts on real (correct, expected) Chinese i18n copy must
  // not itself trip the scan.
  it("does not flag an English it() title even when the body asserts on Chinese copy", () => {
    const found = titleCjkLines(
      'it("shows the metabolite name", () => {\n' +
        '  expect(screen.getByText("查到 1 筆代謝物")).toBeInTheDocument();\n' +
        "});\n",
    );
    expect(found).toEqual([]);
  });
});
