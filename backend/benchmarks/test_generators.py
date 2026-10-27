"""Pin the figure generators to the data the manuscript was computed from.

The generators define the ground truth: a figure's expected verdict is the
parameter it was drawn with. If a generator drifts from the recorded data,
the published numbers no longer describe the figures it produces.

    venv/bin/python -m pytest benchmarks/test_generators.py -q
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from benchmarks.generators import build_plot, build_plot_20, build_plot_50
from benchmarks.table12_13 import load

BENCHMARK_100 = Path(__file__).resolve().parent / "data" / "benchmark_100_ground_truth.csv"

# Cells where build_plot_20.py and benchmark_100_ground_truth.csv disagree.
# Not resolved yet: the author has to say which one the manuscript scored
# against (see README). Listed exactly, so a fix or any new drift turns red.
KNOWN_DISAGREEMENTS = {
    ("benchmark_combined_volcano_07.png", "colorblind"): ("PASS", "FAIL"),
    ("benchmark_combined_heatmap_11.png", "axis"): ("PASS", "FAIL"),
}


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def test_boundary_generator_matches_recorded_nominal_values():
    generated = {
        f"benchmark_{t}_{i:02d}.png": (float(dpi), font, line)
        for t in build_plot.PLOT_TYPES
        for i, (font, line, dpi, _) in enumerate(build_plot.PARAM_COMBOS, start=1)
    }
    recorded = {
        r["figure"]: (r["nominal_dpi"], r["nominal_font_pt"], r["nominal_line_pt"])
        for r in load()
    }
    assert generated == recorded


def test_combined_generator_matches_benchmark_100_except_known_cells():
    generated = {}
    for i, (t, axis, cb, legend, _font, _line, dpi, _) in enumerate(build_plot_20.COMBINED_TEST_CASES, start=1):
        legend = "ok" if t == "heatmap" else legend
        generated[f"benchmark_combined_{t}_{i:02d}.png"] = {
            "axis": _verdict(axis),
            "colorblind": _verdict(cb),
            "legend": _verdict(legend == "ok"),
            "dpi": _verdict(dpi >= build_plot_20.DPI_THRESHOLD),
        }

    with open(BENCHMARK_100, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))[80:100]
    assert {r["input_file"] for r in rows} == set(generated)

    disagreements = {
        (r["input_file"], k): (v, r[f"expected_{k}"])
        for r in rows
        for k, v in generated[r["input_file"]].items()
        if v != r[f"expected_{k}"]
    }
    assert disagreements == KNOWN_DISAGREEMENTS


@pytest.mark.parametrize(
    "module, gt_name, count",
    [
        (build_plot, "benchmark_gt.json", 50),
        (build_plot_50, "benchmark_semantic_gt.json", 50),
        (build_plot_20, "benchmark_combined_gt.json", 20),
    ],
    ids=["boundary", "semantic", "combined"],
)
def test_generator_writes_every_figure_and_its_ground_truth(tmp_path, module, gt_name, count):
    module.main(tmp_path)
    gt = json.loads((tmp_path / gt_name).read_text(encoding="utf-8"))
    assert len(gt) == count
    assert sorted(gt) == sorted(p.name for p in tmp_path.glob("*.png"))


def test_semantic_criteria_each_have_both_verdicts_and_heatmap_legend_is_pass(tmp_path):
    build_plot_50.main(tmp_path)
    gt = json.loads((tmp_path / "benchmark_semantic_gt.json").read_text(encoding="utf-8"))
    for key in ("expected_axis_pass", "expected_colorblind_pass", "expected_legend_pass"):
        assert {v[key] for v in gt.values()} == {"PASS", "FAIL"}
    assert {v["expected_legend_pass"] for v in gt.values() if v["plot_type"] == "heatmap"} == {"PASS"}
