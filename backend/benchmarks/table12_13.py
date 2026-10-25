"""Reproduce thesis Tables 12 and 13 from the per-figure measurements.

These numbers were originally produced in `table9-15_rawdata.xlsx` by hand. The
font half had live Excel formulas (AVERAGE / SUMSQ / CORREL / STDEV.S); the line
half had only pasted values, and one of its helper columns is wrong (see
`LINE_MAPE` below). This module makes both halves reproducible from a CSV under
version control, and `test_table12_13.py` pins every published figure.

Definitions recovered from the spreadsheet, verified against all 50 rows:

  font error  = |measured_font_pt  - nominal_font_pt|
  line error  = |median_line_pt    - nominal_line_pt|
      ^ the MEDIAN estimate, not `estimated_line_pt`. For most figures the two
        are identical, which is why the distinction is invisible until the
        heatmaps, where `estimated_line_pt` degrades badly (nominal 2.0 measured
        6.25) while the median stays sane. The table header labels it as the median.
  MAPE        = mean(error / nominal)
  Pearson r   = CORREL(measured, nominal) over all 50 figures

Formulas confirmed against `data/line_width_formulas_2026-08-28.xlsx`, supplied
by the author on 2026-08-28 — the line half of the original workbook carried
values only, so this is where its arithmetic is actually written down.

    python -m benchmarks.table12_13
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

DATA = Path(__file__).resolve().parent / "data" / "table12_13_measurements.csv"

# Order as reported in the thesis.
CHART_TYPES = ("heatmap", "pca", "volcano", "boxplot", "bar_error")


def load(path: Path = DATA) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        rec: dict[str, Any] = {"figure": r["figure"], "chart_type": r["chart_type"]}
        for k, v in r.items():
            if k not in ("figure", "chart_type"):
                rec[k] = float(v) if v not in ("", None) else None
        out.append(rec)
    return out


def font_error(r: dict[str, Any]) -> float | None:
    if r["measured_font_pt"] is None or r["nominal_font_pt"] is None:
        return None
    return abs(r["measured_font_pt"] - r["nominal_font_pt"])


def line_error(r: dict[str, Any]) -> float | None:
    """Uses the median estimate — see the module docstring."""
    if r["median_line_pt"] is None or r["nominal_line_pt"] is None:
        return None
    return abs(r["median_line_pt"] - r["nominal_line_pt"])


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _stdev_sample(xs: Sequence[float]) -> float:
    """Sample standard deviation — Excel's STDEV.S, i.e. n-1 in the denominator."""
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else float("nan")


def summarise(rows: Iterable[dict[str, Any]], err, nominal_key: str) -> dict[str, float]:
    rows = [r for r in rows if err(r) is not None and r[nominal_key]]
    errs = [err(r) for r in rows]
    return {
        "mae": _mean(errs),
        "sd": _stdev_sample(errs),
        "mape": _mean([err(r) / r[nominal_key] for r in rows]),
        "rmse": math.sqrt(_mean([e * e for e in errs])),
        "n": len(errs),
    }


def table12(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Global accuracy for font size and line width (thesis Table 12)."""
    rows = rows if rows is not None else load()
    font = summarise(rows, font_error, "nominal_font_pt")
    line = summarise(rows, line_error, "nominal_line_pt")
    for key, measured, nominal, target in (
        ("font", "measured_font_pt", "nominal_font_pt", font),
        ("line", "median_line_pt", "nominal_line_pt", line),
    ):
        paired = [r for r in rows if r[measured] is not None and r[nominal] is not None]
        target["pearson_r"] = _pearson([r[measured] for r in paired],
                                       [r[nominal] for r in paired])
    return {"font_size_pt": font, "line_width_pt": line}


def table13(rows: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Per-chart-type breakdown (thesis Table 13)."""
    rows = rows if rows is not None else load()
    out = {}
    for ct in CHART_TYPES:
        sub = [r for r in rows if r["chart_type"] == ct]
        if sub:
            out[ct] = {"font_size_pt": summarise(sub, font_error, "nominal_font_pt"),
                       "line_width_pt": summarise(sub, line_error, "nominal_line_pt")}
    return out


DUPLICATE_THRESHOLD = 0.8


def duplicate_groups(rows: list[dict[str, Any]] | None = None,
                     threshold: float = DUPLICATE_THRESHOLD) -> list[dict[str, Any]]:
    """Chart-type pairs whose line-width measurements repeat row for row.

    Two independently rendered chart types cannot produce identical line
    measurements figure by figure, so a hit means the column was copied when the
    sheet was assembled. Reported, never silently averaged over.

    Matching is proportional rather than all-or-nothing: in the thesis data
    volcano repeats pca in 9 of 10 rows for `median_line_pt` and 10 of 10 for
    `estimated_line_pt`, and requiring every cell to agree would let that pass.
    """
    rows = rows if rows is not None else load()
    by_type = {ct: [r for r in rows if r["chart_type"] == ct] for ct in CHART_TYPES}
    keys = ("nominal_line_pt", "median_line_pt", "estimated_line_pt")

    def same(x, y) -> bool:
        # Tolerance, not equality: one heatmap/volcano cell differs in the last
        # float bits after a round-trip through the spreadsheet. Requiring exact
        # equality would let a copied column pass as independent.
        if x is None or y is None:
            return x is y
        return abs(x - y) <= 1e-9

    dupes = []
    for i, a in enumerate(CHART_TYPES):
        for b in CHART_TYPES[i + 1:]:
            ra, rb = by_type.get(a, []), by_type.get(b, [])
            if len(ra) != len(rb) or not ra:
                continue
            per_key = {k: sum(same(x[k], y[k]) for x, y in zip(ra, rb)) / len(ra)
                       for k in keys}
            worst = min(per_key.values())
            if worst >= threshold:
                dupes.append({"a": a, "b": b, "n": len(ra),
                              "match_ratio": per_key, "min_ratio": worst})
    return dupes


def main() -> int:
    rows = load()
    t12, t13 = table12(rows), table13(rows)
    print(f"Table 12 — global (n={t12['font_size_pt']['n']})")
    for name, m in t12.items():
        r = f"  r={m['pearson_r']:.4f}" if "pearson_r" in m else ""
        print(f"  {name:16} MAE={m['mae']:.4f} ± {m['sd']:.4f}  "
              f"MAPE={m['mape'] * 100:.2f}%  RMSE={m['rmse']:.4f}{r}")

    print("\nTable 13 — per chart type")
    print(f"  {'type':10} {'font MAE':>9} {'font MAPE':>10} {'line MAE':>9} {'line MAPE':>10}")
    for ct, m in t13.items():
        print(f"  {ct:10} {m['font_size_pt']['mae']:9.4f} {m['font_size_pt']['mape']:10.4f} "
              f"{m['line_width_pt']['mae']:9.4f} {m['line_width_pt']['mape']:10.4f}")

    for d in duplicate_groups(rows):
        detail = ", ".join(f"{k}={int(v * d['n'])}/{d['n']}"
                           for k, v in d["match_ratio"].items())
        print(f"\n⚠️  {d['a']} and {d['b']} repeat each other's line-width "
              f"measurements ({detail}). Two independently rendered chart types "
              f"cannot do that, so the reported {d['b']} line figures are not "
              f"independent measurements and need re-measuring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
