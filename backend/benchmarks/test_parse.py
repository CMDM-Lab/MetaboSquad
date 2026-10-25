"""Tests for parsing one `review_result` entry into the prediction contract.

The parser sits between two things that can drift: the plot-review prompt's
output format, and the measurement tool's dict shape. If either moves, these
tests fail here rather than silently producing a benchmark number.

The governing rule under test: **an unparseable verdict must be absent, never
defaulted.** The scorer skips absent keys; a wrong default would be counted as
a correct answer, which is the same class of silent failure (ea99d51) that made
the earlier results unreliable.

    venv/bin/python -m pytest benchmarks/test_parse.py -q
"""

from __future__ import annotations

from benchmarks.figure_bench import parse_review_entry

# Matches the format fixed by PLOT_REVIEW_SYSTEM; reasons are Traditional
# Chinese because the prompt asks for it, while the labels stay English.
FEEDBACK = """Image Type: PCA Score Plot
Scientific Significance: 展示兩組樣本在主成分空間的分離情形。
Visual & Semantic Review:
- Axis Titles & Units: Compliant — 兩軸皆標示變異解釋比例
- Colorblind-Safe Palette: Non-compliant — 紅綠為唯一區分方式，無冗餘編碼
- Legend Legibility: Compliant — 圖例位於畫布外側，未遮蔽資料點
Visual & Layout Deficiencies:
- 無
"""

COMPLIANCE = {
    "file_path": "data/figures/pca_001.png",
    "scale_resolution": {"effective_dpi": 150.0, "px_per_mm": 5.9},
    "text_analysis": [{"estimated_pt": 8.0}, {"estimated_pt": 11.0}],
    "text_report": {"min_pt": 8.0, "avg_pt": 9.5},
    "line_analysis": {"median_width_pt": 0.42, "estimated_true_line_pt": 0.50},
    "pass_status": {"dpi_pass": "FAIL"},
}


def _entry(**over):
    e = {"file_path": "data/figures/pca_001.png", "file_name": "pca_001.png",
         "feedback": FEEDBACK, "compliance_result": COMPLIANCE, "warning": ""}
    e.update(over)
    return e


def test_parses_all_three_semantic_verdicts():
    p = parse_review_entry(_entry())
    assert p["axis_labels_violation"] is False
    assert p["colorblind_safe_violation"] is True
    assert p["legend_violation"] is False


def test_extracts_physical_quantities():
    p = parse_review_entry(_entry())
    assert p["effective_dpi"] == 150.0
    assert p["resolution_violation"] is True          # < 300 dpi
    assert p["font_size_pt"] == 8.0                   # min_pt, not avg
    assert p["font_size_avg_pt"] == 9.5
    assert p["line_width_pt"] == 0.50                 # estimated_true, not median
    assert p["line_width_median_pt"] == 0.42


def test_resolution_at_threshold_is_compliant():
    c = {**COMPLIANCE, "scale_resolution": {"effective_dpi": 300.0}}
    assert parse_review_entry(_entry(compliance_result=c))["resolution_violation"] is False


def test_not_applicable_is_not_a_compliance_decision():
    fb = FEEDBACK.replace("- Legend Legibility: Compliant",
                          "- Legend Legibility: Not Applicable")
    p = parse_review_entry(_entry(feedback=fb))
    assert "legend_violation" not in p


def test_unparseable_verdict_is_absent_not_defaulted():
    fb = "Image Type: Volcano Plot\n（模型未依格式輸出）\n"
    p = parse_review_entry(_entry(feedback=fb))
    for k in ("axis_labels_violation", "colorblind_safe_violation", "legend_violation"):
        assert k not in p, f"{k} must be absent, not defaulted"


def test_measurement_failure_is_recorded_and_yields_no_quantities():
    p = parse_review_entry(_entry(compliance_result={"error": "物理檢測失敗: bad png"}))
    assert p["compliance_error"].startswith("物理檢測失敗")
    for k in ("font_size_pt", "line_width_pt", "resolution_violation"):
        assert k not in p


def test_tolerates_bold_markers_and_hyphen_variant():
    fb = ("Visual & Semantic Review:\n"
          "- **Axis Titles & Units**: **Non compliant** — 缺 y 軸單位\n"
          "* Colorblind-Safe Palette: Compliant — 使用色盲友善配色\n")
    p = parse_review_entry(_entry(feedback=fb))
    assert p["axis_labels_violation"] is True
    assert p["colorblind_safe_violation"] is False


def test_missing_compliance_block_does_not_raise():
    p = parse_review_entry({"feedback": FEEDBACK})
    assert p["colorblind_safe_violation"] is True
    assert "font_size_pt" not in p
