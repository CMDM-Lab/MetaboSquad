"""Figure-review benchmark runner and scorer.

Backs the manuscript's primary claim. Two things this deliberately does that the
original evaluation did not:

  1. Records provenance on every run — git SHA, model, execution path, timestamp.
     The thesis reports numbers whose originating commit nobody can now name;
     that is the failure this file exists to prevent.

  2. Supports both execution paths (`--path agent` vs `--path node`). Before
     3b33cf5 a plot-review request carrying a file was demoted to plain chat, and
     before ea99d51 the structured `review_result` never reached the API layer.
     Whether those defects touched the reported numbers depends on which path
     produced them. Running both answers it instead of guessing.

Scoring follows the thesis definitions: per-criterion precision/recall/F1 with
McNemar for paired binary decisions, and MAE/MAPE/RMSE/Pearson-r with a Friedman
test across chart types for the continuous estimates.

Usage:
    python -m benchmarks.figure_bench run --path node  --model gpt-4.1-mini
    python -m benchmarks.figure_bench run --path agent --model gpt-4.1-mini
    python -m benchmarks.figure_bench compare runs/<a> runs/<b>
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

BENCH_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCH_DIR / "data"
RUNS_DIR = BENCH_DIR / "runs"

CHART_TYPES = ("pca_score", "volcano", "heatmap", "box", "bar")

# Binary compliance criteria. Each maps a ground-truth record to the expected
# verdict, where True means "this figure violates the criterion".
BINARY_CRITERIA: dict[str, Callable[[dict[str, Any]], bool]] = {
    "resolution":      lambda gt: gt["resolution_dpi"] < 300,
    "axis_labels":     lambda gt: not gt["axis_labels_complete"],
    "colorblind_safe": lambda gt: not gt["colorblind_safe"],
    "legend":          lambda gt: gt["legend_overlapping"],
}

CONTINUOUS_FIELDS = ("font_size_pt", "line_width_pt")


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #

def _git(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), cwd=BENCH_DIR, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


@dataclass
class RunMeta:
    """Everything needed to say what a number means. Never omit a field."""
    timestamp: str
    git_sha: str
    git_dirty: bool
    branch: str
    model: str
    path: str                      # "agent" | "node"
    figure_count: int
    notes: str = ""

    @classmethod
    def capture(cls, model: str, path: str, n: int, notes: str = "") -> "RunMeta":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            git_sha=_git("rev-parse", "HEAD"),
            git_dirty=bool(_git("status", "--porcelain")),
            branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
            model=model, path=path, figure_count=n, notes=notes,
        )


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

@dataclass
class BinaryScore:
    criterion: str
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else float("nan")

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else float("nan")

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:        self.tp += 1
        elif predicted and not actual:  self.fp += 1
        elif not predicted and actual:  self.fn += 1
        else:                           self.tn += 1


def mcnemar(a_correct: Sequence[bool], b_correct: Sequence[bool]) -> dict[str, Any]:
    """Paired test on two systems judged on the same items.

    Exact binomial when discordant pairs are few, which is the common case here —
    the chi-square approximation is unreliable below ~25 and the thesis reports
    p-values in exactly that range.
    """
    if len(a_correct) != len(b_correct):
        raise ValueError("paired inputs must be the same length")
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    c = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "p_value": 1.0, "method": "no discordant pairs"}
    if n < 25:
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
        return {"b": b, "c": c, "p_value": min(1.0, 2 * tail), "method": "exact binomial"}
    chi2 = (abs(b - c) - 1) ** 2 / n
    return {"b": b, "c": c, "chi2": chi2,
            "p_value": math.erfc(math.sqrt(chi2 / 2)), "method": "chi-square w/ continuity correction"}


def continuous_metrics(pred: Sequence[float], true: Sequence[float]) -> dict[str, float]:
    """MAE / MAPE / RMSE / Pearson r, matching the thesis reporting."""
    pairs = [(p, t) for p, t in zip(pred, true)
             if p is not None and t is not None and not math.isnan(p) and not math.isnan(t)]
    if not pairs:
        return {k: float("nan") for k in ("mae", "mae_sd", "mape", "rmse", "pearson_r", "n")}
    errs = [abs(p - t) for p, t in pairs]
    n = len(pairs)
    mae = sum(errs) / n
    var = sum((e - mae) ** 2 for e in errs) / (n - 1) if n > 1 else 0.0
    mape = sum(abs(p - t) / abs(t) for p, t in pairs if t) / n * 100
    rmse = math.sqrt(sum((p - t) ** 2 for p, t in pairs) / n)
    mp = sum(p for p, _ in pairs) / n
    mt = sum(t for _, t in pairs) / n
    num = sum((p - mp) * (t - mt) for p, t in pairs)
    den = math.sqrt(sum((p - mp) ** 2 for p, _ in pairs) * sum((t - mt) ** 2 for _, t in pairs))
    return {"mae": mae, "mae_sd": math.sqrt(var), "mape": mape, "rmse": rmse,
            "pearson_r": num / den if den else float("nan"), "n": n}


def friedman(groups: dict[str, Sequence[float]]) -> dict[str, Any]:
    """Friedman test across chart types (k related samples, equal n).

    Returns the statistic and df; the thesis pairs this with a p-value from
    scipy. Kept dependency-free here so the harness runs anywhere — feed
    `statistic` to scipy.stats.chi2.sf(stat, df) when reporting.
    """
    names = list(groups)
    k = len(names)
    if k < 2:
        raise ValueError("Friedman needs at least two groups")
    cols = [list(groups[nm]) for nm in names]
    n = len(cols[0])
    if any(len(c) != n for c in cols):
        raise ValueError("Friedman requires equal-length groups (same blocks)")
    rank_sums = [0.0] * k
    for i in range(n):
        row = sorted(range(k), key=lambda j: cols[j][i])
        ranks = [0.0] * k
        pos = 0
        while pos < k:                                   # average ties
            end = pos
            while end + 1 < k and cols[row[end + 1]][i] == cols[row[pos]][i]:
                end += 1
            avg = (pos + end) / 2 + 1
            for t in range(pos, end + 1):
                ranks[row[t]] = avg
            pos = end + 1
        for j in range(k):
            rank_sums[j] += ranks[j]
    stat = 12.0 / (n * k * (k + 1)) * sum(r ** 2 for r in rank_sums) - 3 * n * (k + 1)
    return {"statistic": stat, "df": k - 1, "n_blocks": n,
            "groups": names, "rank_sums": rank_sums}


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #

@dataclass
class FigureResult:
    figure_id: str
    chart_type: str
    predicted: dict[str, Any] = field(default_factory=dict)
    ground_truth: dict[str, Any] = field(default_factory=dict)
    raw: Any = None
    error: str | None = None


def load_ground_truth(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        sys.exit(f"ground truth not found: {path}\n"
                 f"See benchmarks/README.md — this file is a delivery condition.")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in records:
        missing = [k for k in ("figure_id", "path", "chart_type", *CONTINUOUS_FIELDS) if k not in r]
        if missing:
            sys.exit(f"{r.get('figure_id', '?')}: missing ground-truth fields {missing}")
        if r["chart_type"] not in CHART_TYPES:
            sys.exit(f"{r['figure_id']}: unknown chart_type {r['chart_type']!r}")
    return records


BENCH_QUERY = "請檢查這張圖是否符合期刊投稿的圖表規範。"

# The three semantic criteria the plot-review prompt is contractually required
# to emit, as `- <Label>: <Compliant|Non-compliant|Not Applicable> — ...`.
_CRITERION_LABELS = {
    "axis_labels":     "Axis Titles & Units",
    "colorblind_safe": "Colorblind-Safe Palette",
    "legend":          "Legend Legibility",
}
# Not pre-compiled: the label is interpolated per criterion.
_VERDICT_TEMPLATE = (
    r"^\s*[-*]?\s*\**\s*{label}\s*\**\s*[:：]\s*\**\s*"
    r"(Compliant|Non-compliant|Non compliant|Not Applicable)"
)


def parse_review_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Turn one `review_result` element into the flat prediction contract.

    Physical quantities come from `compliance_result` (the deterministic
    measurement tool); the three semantic verdicts are parsed out of the LLM's
    `feedback` text, whose format the system prompt fixes.

    Anything that cannot be parsed is **left absent rather than defaulted**.
    A missing verdict silently scored as "compliant" is precisely the failure
    that made the earlier numbers unreliable — absent keys are skipped by the
    scorer, a wrong default would be counted as a correct answer.
    """
    out: dict[str, Any] = {}

    comp = entry.get("compliance_result") or {}
    if "error" in comp:
        out["compliance_error"] = comp["error"]
    else:
        dpi = (comp.get("scale_resolution") or {}).get("effective_dpi")
        if dpi is not None:
            out["effective_dpi"] = dpi
            out["resolution_violation"] = float(dpi) < 300.0

        text_report = comp.get("text_report") or {}
        # min_pt: publication limits are on the *smallest* readable text, which
        # is what the thesis reports against. avg is kept for reference only.
        if text_report.get("min_pt") is not None:
            out["font_size_pt"] = float(text_report["min_pt"])
        if text_report.get("avg_pt") is not None:
            out["font_size_avg_pt"] = float(text_report["avg_pt"])

        line = comp.get("line_analysis") or {}
        for src, dst in (("estimated_true_line_pt", "line_width_pt"),
                         ("median_width_pt", "line_width_median_pt")):
            if line.get(src) is not None:
                out[dst] = float(line[src])
        out.setdefault("line_width_pt", out.get("line_width_median_pt"))

    feedback = entry.get("feedback") or ""
    for key, label in _CRITERION_LABELS.items():
        m = re.search(_VERDICT_TEMPLATE.format(label=re.escape(label)),
                      feedback, re.IGNORECASE | re.MULTILINE)
        if not m:
            continue
        verdict = m.group(1).lower().replace(" ", "-")
        if verdict == "not-applicable":
            continue                       # N/A is not a compliance decision
        out[f"{key}_violation"] = verdict.startswith("non")
    out["_feedback"] = feedback
    return out


def _first_review_entry(state_out: dict[str, Any], image_path: Path) -> dict[str, Any]:
    reviews = state_out.get("review_result") or []
    if isinstance(reviews, dict):
        reviews = [reviews]
    if not reviews:
        raise RuntimeError(
            "review_result is empty — before ea99d51 this channel was silently "
            "dropped by LangGraph; check that MainState declares it")
    name = image_path.name
    for r in reviews:
        if Path(str(r.get("file_path", ""))).name == name or r.get("file_name") == name:
            return r
    return reviews[0]


def review_via_node(image_path: Path, model: str) -> dict[str, Any]:
    """Call the plot-review subgraph directly, bypassing intent routing.

    This path never sees `_correct_misclassification`, so the 3b33cf5 demotion
    (a file-bearing plot_review request downgraded to plain chat) cannot occur.
    """
    from src.graph_agent.graph.plot_graph import plot_review_graph

    out = plot_review_graph.invoke(
        {
            "messages": [{"role": "user", "content": BENCH_QUERY}],
            "files": [str(image_path)],
            "original_query": BENCH_QUERY,
        },
        config={"configurable": {"thread_id": f"bench-node-{image_path.stem}"}},
    )
    return parse_review_entry(_first_review_entry(out, image_path))


def review_via_agent(image_path: Path, model: str) -> dict[str, Any]:
    """Go through the supervisor graph — the path a real request takes.

    Deliberately not over HTTP: both defects in question (3b33cf5 intent
    demotion, ea99d51 dropped channel) live in the graph layer, so invoking the
    compiled supervisor reproduces them exactly while avoiding a running server
    and a Postgres dependency. An in-memory checkpointer is used for the same
    reason — a benchmark must not need the production database.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from src.graph_agent.supervisor import build_main_graph

    agent = build_main_graph(None, MemorySaver())
    out = agent.invoke(
        {
            "messages": [{"role": "user",
                          "content": [{"type": "text", "text": BENCH_QUERY}]}],
            "files": [str(image_path)],
        },
        config={"configurable": {"thread_id": f"bench-agent-{image_path.stem}"}},
    )
    return parse_review_entry(_first_review_entry(out, image_path))


def run(args: argparse.Namespace) -> int:
    gt_records = load_ground_truth(DATA_DIR / "ground_truth.jsonl")
    reviewer = review_via_node if args.path == "node" else review_via_agent
    meta = RunMeta.capture(args.model, args.path, len(gt_records), args.notes)
    if meta.git_dirty:
        print("warning: working tree is dirty — the recorded SHA does not fully "
              "describe what ran", file=sys.stderr)

    out_dir = RUNS_DIR / meta.timestamp.replace(":", "").replace("-", "")[:15]
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[FigureResult] = []
    for i, gt in enumerate(gt_records, 1):
        fr = FigureResult(figure_id=gt["figure_id"], chart_type=gt["chart_type"], ground_truth=gt)
        try:
            fr.predicted = reviewer(BENCH_DIR / gt["path"], args.model)
            fr.raw = fr.predicted
        except Exception as e:                        # noqa: BLE001 — recorded, not swallowed
            fr.error = f"{type(e).__name__}: {e}"
        results.append(fr)
        print(f"  [{i}/{len(gt_records)}] {fr.figure_id}"
              f"{' ERROR ' + fr.error if fr.error else ''}", file=sys.stderr)

    (out_dir / "meta.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    with (out_dir / "raw.jsonl").open("w", encoding="utf-8") as fh:
        for fr in results:
            fh.write(json.dumps(asdict(fr), ensure_ascii=False) + "\n")
    (out_dir / "scores.json").write_text(
        json.dumps(score(results), indent=2, ensure_ascii=False), encoding="utf-8")

    n_err = sum(1 for r in results if r.error)
    print(f"\nwrote {out_dir}  ({len(results)} figures, {n_err} errors)")
    return 1 if n_err else 0


def score(results: Iterable[FigureResult]) -> dict[str, Any]:
    results = [r for r in results if not r.error]
    out: dict[str, Any] = {"binary": {}, "continuous": {}, "per_chart_type": {}}

    for name, expected in BINARY_CRITERIA.items():
        s = BinaryScore(name)
        for r in results:
            if f"{name}_violation" not in r.predicted:
                continue
            s.add(bool(r.predicted[f"{name}_violation"]), expected(r.ground_truth))
        out["binary"][name] = {**asdict(s), "precision": s.precision,
                               "recall": s.recall, "f1": s.f1}

    for fld in CONTINUOUS_FIELDS:
        out["continuous"][fld] = continuous_metrics(
            [r.predicted.get(fld) for r in results],
            [r.ground_truth.get(fld) for r in results])
        by_type = {}
        for ct in CHART_TYPES:
            sub = [r for r in results if r.chart_type == ct]
            if sub:
                by_type[ct] = continuous_metrics(
                    [r.predicted.get(fld) for r in sub],
                    [r.ground_truth.get(fld) for r in sub])
        out["per_chart_type"][fld] = by_type
    return out


def compare(args: argparse.Namespace) -> int:
    """Paired comparison between two runs over the same figure set."""
    def load(d: Path) -> tuple[dict, dict[str, FigureResult]]:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        rows = {}
        for line in (d / "raw.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["figure_id"]] = FigureResult(**r)
        return meta, rows

    ma, ra = load(Path(args.run_a))
    mb, rb = load(Path(args.run_b))
    shared = sorted(set(ra) & set(rb))
    print(f"A: {ma['model']} via {ma['path']} @ {ma['git_sha'][:8]}")
    print(f"B: {mb['model']} via {mb['path']} @ {mb['git_sha'][:8]}")
    print(f"paired on {len(shared)} figures\n")

    for name, expected in BINARY_CRITERIA.items():
        key = f"{name}_violation"
        pairs = [(ra[f], rb[f]) for f in shared
                 if key in ra[f].predicted and key in rb[f].predicted]
        if not pairs:
            continue
        a_ok = [bool(x.predicted[key]) == expected(x.ground_truth) for x, _ in pairs]
        b_ok = [bool(y.predicted[key]) == expected(y.ground_truth) for _, y in pairs]
        m = mcnemar(a_ok, b_ok)
        print(f"{name:16} A={sum(a_ok)}/{len(pairs)}  B={sum(b_ok)}/{len(pairs)}  "
              f"b={m['b']} c={m['c']}  p={m['p_value']:.4f}  ({m['method']})")

    for fld in CONTINUOUS_FIELDS:
        groups = {}
        for ct in CHART_TYPES:
            errs = [abs(ra[f].predicted[fld] - ra[f].ground_truth[fld])
                    for f in shared
                    if ra[f].chart_type == ct and fld in ra[f].predicted]
            if errs:
                groups[ct] = errs
        if len(groups) >= 2 and len({len(v) for v in groups.values()}) == 1:
            fr = friedman(groups)
            print(f"\n{fld} Friedman across chart types: "
                  f"chi2={fr['statistic']:.3f}, df={fr['df']}, blocks={fr['n_blocks']}")
            print("  (p-value: scipy.stats.chi2.sf(statistic, df))")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the benchmark")
    r.add_argument("--path", choices=("agent", "node"), required=True,
                   help="agent = through the supervisor graph (real routing); "
                        "node = plot-review subgraph directly")
    r.add_argument("--model", default="gpt-4.1-mini")
    r.add_argument("--notes", default="")
    r.set_defaults(func=run)

    c = sub.add_parser("compare", help="paired comparison of two runs")
    c.add_argument("run_a")
    c.add_argument("run_b")
    c.set_defaults(func=compare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
