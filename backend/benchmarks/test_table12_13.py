"""Pin thesis Tables 12 and 13 to the versioned measurements.

Every published figure is asserted here. The point is not that the code is
right in the abstract — it is that this code produces the numbers already in
the thesis, so swapping the spreadsheet for a program changes nothing except
that the calculation is now reviewable and re-runnable.

Source of truth for the expected values: table9-15_rawdata.xlsx, sheets
"table_12&13" (totals) and "table_12&13_raw" (P1:V16 calculation block).

    venv/bin/python -m pytest benchmarks/test_table12_13.py -q
"""

from __future__ import annotations

import math

import pytest

from benchmarks.table12_13 import (
    CHART_TYPES, duplicate_groups, line_error, load, table12, table13,
)

ROWS = load()


def approx(x):
    return pytest.approx(x, abs=5e-5)


def test_fifty_figures_five_types():
    assert len(ROWS) == 50
    for ct in CHART_TYPES:
        assert sum(r["chart_type"] == ct for r in ROWS) == 10


# ---- Table 12: global ------------------------------------------------------

def test_table12_font_size_matches_thesis():
    m = table12(ROWS)["font_size_pt"]
    assert m["mae"] == approx(0.9878)
    assert m["sd"] == approx(0.8765)
    assert m["mape"] == approx(0.1194)
    assert m["rmse"] == approx(1.3147)
    assert m["pearson_r"] == approx(0.6954)


def test_table12_line_width_matches_thesis():
    m = table12(ROWS)["line_width_pt"]
    assert m["mae"] == approx(0.2494)
    assert m["sd"] == approx(0.2443)
    assert m["mape"] == approx(0.1520)
    assert m["rmse"] == approx(0.3474)
    # =CORREL(C2:C51,B2:B51) in the author-supplied formula workbook
    assert m["pearson_r"] == approx(0.8818)


# ---- Table 13: per chart type ---------------------------------------------

FONT = {"heatmap": (0.725, 0.0903), "pca": (1.320, 0.1590), "volcano": (1.334, 0.1596),
        "boxplot": (1.075, 0.1263), "bar_error": (0.485, 0.0620)}
LINE = {"heatmap": (0.377, 0.1909), "pca": (0.161, 0.1123), "volcano": (0.161, 0.1123),
        "boxplot": (0.203, 0.1263), "bar_error": (0.345, 0.2183)}
SD = {"heatmap": (0.6654, 0.3675), "pca": (0.8262, 0.1287), "volcano": (0.7886, 0.1287),
      "boxplot": (1.3125, 0.2039), "bar_error": (0.3009, 0.2591)}


@pytest.mark.parametrize("ct", CHART_TYPES)
def test_table13_matches_thesis(ct):
    m = table13(ROWS)[ct]
    mae, mape = FONT[ct]
    assert m["font_size_pt"]["mae"] == approx(mae)
    assert m["font_size_pt"]["mape"] == approx(mape)
    mae, mape = LINE[ct]
    assert m["line_width_pt"]["mae"] == approx(mae)
    assert m["line_width_pt"]["mape"] == approx(mape)
    fsd, lsd = SD[ct]
    assert m["font_size_pt"]["sd"] == approx(fsd)
    assert m["line_width_pt"]["sd"] == approx(lsd)


# ---- the definition that was not obvious ----------------------------------

def test_line_error_uses_median_not_estimated():
    """The heatmaps are where the two diverge, so they pin the definition.

    benchmark_heatmap_03: nominal 2.0, median 2.06, estimated 6.25.
    The thesis value is 0.06, i.e. the median. Using `estimated_line_pt` would
    give 4.25 and inflate the heatmap MAE roughly tenfold.
    """
    r = next(r for r in ROWS if r["figure"].startswith("benchmark_heatmap_03"))
    assert r["median_line_pt"] == approx(2.06)
    assert r["estimated_line_pt"] == approx(6.25)
    assert line_error(r) == approx(0.06)


# ---- data integrity --------------------------------------------------------

def test_three_chart_types_share_line_width_by_construction():
    """Identical line-width measurements across pca/volcano/boxplot are expected.

    This was initially read as a copy-paste defect. It is not. The generator
    (`build_plot.py`) renders every chart type from the same PARAM_COMBOS list,
    so all five share the line_pt sequence 3, 1, 2, 1.5, 2.5, 2.5, 1.5, 1, 3, 2,
    and all of them draw with that single variable. The three line-dominated
    types therefore measure alike; heatmap (colour fills) and bar_error (filled
    rectangles) diverge because their line features differ. Confirmed by the
    author 2026-08-28.

    Kept as a test because the agreement is a real property worth noticing: the
    distance-transform estimator is insensitive to chart type wherever actual
    strokes exist. It also explains why line-width MAE is the one metric whose
    Friedman test came out non-significant — the groups genuinely do not differ.
    """
    dupes = duplicate_groups(ROWS)
    pairs = {(d["a"], d["b"]) for d in dupes}
    assert {("pca", "volcano"), ("pca", "boxplot"), ("volcano", "boxplot")} <= pairs
    for d in dupes:
        assert d["match_ratio"]["nominal_line_pt"] == 1.0, \
            "shared nominal line widths are what makes the agreement expected"


def test_nominal_line_widths_follow_the_generator_sequence():
    """Pin the PARAM_COMBOS sequence the figures were generated from."""
    expected = [3.0, 1.0, 2.0, 1.5, 2.5, 2.5, 1.5, 1.0, 3.0, 2.0]
    for ct in CHART_TYPES:
        got = [r["nominal_line_pt"] for r in ROWS if r["chart_type"] == ct]
        assert got == expected, f"{ct} does not follow PARAM_COMBOS"


def test_font_size_measurements_differ_between_chart_types():
    """Font size, unlike line width, does vary by chart type.

    Same nominal sizes, different measured values — the OCR-based estimator is
    sensitive to what else is on the canvas in a way the stroke estimator is not.
    """
    by = {ct: [r for r in ROWS if r["chart_type"] == ct] for ct in CHART_TYPES}
    identical = sum(a["measured_font_pt"] == b["measured_font_pt"]
                    for a, b in zip(by["pca"], by["volcano"]))
    assert identical < 8, "font measurements should differ between chart types"
