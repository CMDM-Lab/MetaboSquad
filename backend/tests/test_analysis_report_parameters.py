"""The report must state clearly "which parameters were used, and why".

Found after a real LC-MS analysis on 2026-08-04: the full report lacked the
parameters used. Every step should have corresponding tunable parameters; instead
results were generated directly, with no explanation of why there were no parameters.

The investigation found two layers:

**A. Computed but discarded.** `recommend_and_analysis` (use_tool/code.py) returns
6 keys, but the report only used `r_code` and `result_files`. Discarded were:
  - `summary`: data characteristics (12 samples / 410 features / two Label groups, n=6 each)
  - `config`: the parameters actually used (transNorm=LogNorm, scaleNorm=AutoNorm, etc.)
  - `recommend`: per-module rationale -- and it was overwritten by a variable-reuse bug:
        result = diagnose_data_and_recommend(group_count)   # recommendation
        ...
        success, result = run_r_code(r_code, file)          # same name overwritten
        return {"recommend": result, ...}                   # returns the list of R files

**B. Most parameters really are not tunable.** `ANALYSIS_KNOWLEDGE` declares `paired`
only for fold-change/t-test/volcano, and 0 for pca; `fc.thresh=2.0`, `threshp=0.05`,
`equal.var=TRUE`, the correction method `"fdr"` and the number of PCA components are
all literals in the R template.
This file only handles A (making them visible). B is a separate feature.

Why "visible" is worth doing on its own: users must be able to judge whether the
results are trustworthy. Only what is visible can be questioned (e.g.
equal.var=TRUE assumes equal variances; for n=6 metabolomics data Welch is usually
recommended).
"""

import shutil

import pytest

from api.artifacts import UPLOAD_ROOT

RECOMMENDATIONS = [
    {"analysis": "fold-change", "reason": "Computes the fold change between the two groups to quickly screen for differential features"},
    {"analysis": "t-test", "reason": "Tests the statistical significance of differences between the two groups"},
    {"analysis": "pca", "reason": "Explores the overall structure of the sample distribution; the basic exploratory step for any analysis"},
]
CONFIG = {
    "file_path": "../../uploads/csv/lcms_table.csv",
    "paired": "FALSE", "format": "colu", "label.type": "disc",
    "rowNorm": "NULL", "transNorm": "LogNorm", "scaleNorm": "AutoNorm",
}
SUMMARY = ("CSV parsed successfully.\n- Total samples: 12\n- Total features: 410\n"
           "- Group column: 'Label' (2 groups: KO, WT; group sizes: KO (n=6), WT (n=6))")


@pytest.fixture(name="report_dir")
def report_dir_fixture():
    d = UPLOAD_ROOT / "output" / "analysis" / "pytest_params"
    d.mkdir(parents=True, exist_ok=True)
    yield "uploads/output/analysis/pytest_params"
    shutil.rmtree(d, ignore_errors=True)


def _render(report_dir: str, *, analysis_result: dict) -> str:
    from src.graph_agent.graph.analysis_graph import save_significant_node

    state = {
        "date": "2026-08-04-22-00-00",
        "result_dir": report_dir,
        "sig_all": ["327.2/3418"],
        "significant_metabolites": [],
        "files": ["../../uploads/csv/lcms_table.csv"],
        "analysis_result": analysis_result,
    }
    out = save_significant_node(state, {"configurable": {}})
    with open(out["output_path"], encoding="utf-8") as f:
        return f.read()


FULL_RESULT = {
    "success": True,
    "summary": SUMMARY,
    "recommend": RECOMMENDATIONS,
    "config": CONFIG,
    "r_code": "# r code",
    "result_files": [],
}


def test_report_shows_data_characteristics(report_dir):
    content = _render(report_dir, analysis_result=FULL_RESULT)
    assert "Total samples: 12" in content
    assert "410" in content
    assert "KO (n=6)" in content


def test_report_shows_preprocessing_parameters(report_dir):
    """Physicians must be able to see that the data was log-transformed + auto-scaled -- that directly affects interpretation."""
    content = _render(report_dir, analysis_result=FULL_RESULT)
    assert "transNorm" in content and "LogNorm" in content
    assert "scaleNorm" in content and "AutoNorm" in content
    assert "label.type" in content and "disc" in content


def test_report_shows_why_each_analysis_was_chosen(report_dir):
    """The per-module rationale is exactly the part users reported as "no explanation"."""
    content = _render(report_dir, analysis_result=FULL_RESULT)
    for rec in RECOMMENDATIONS:
        assert rec["analysis"] in content
        assert rec["reason"] in content, f"缺少 {rec['analysis']} 的理由"


def test_report_flags_the_hardcoded_parameters(report_dir):
    """Hard-coded, currently non-tunable parameters must also be listed and marked, not silently omitted.

    equal.var=TRUE is the one most worth questioning here (it assumes equal variances;
    for n=6 metabolomics data Welch is usually recommended). Physicians cannot question
    what they cannot see.
    """
    content = _render(report_dir, analysis_result=FULL_RESULT)
    for token in ["fc.thresh", "threshp", "equal.var", "fdr"]:
        assert token in content, f"沒有列出寫死的參數 {token}"
    # The assertion must pin the **explanation** sentence itself, not just the word
    # for "fixed" -- the table header already contains the fixed-value label, so with
    # an `or` fallback on that word the test would stay green even if the whole
    # explanation were removed (the first version did exactly that; mutation testing caught it).
    assert "cannot be adjusted" in content, (
        "有列出參數，但沒說明它們目前不可調整——醫師會以為那是系統依資料選的，"
        "而不是本版的限制"
    )


def test_report_degrades_gracefully_when_fields_are_missing(report_dir):
    """An old analysis_result (without config/recommend) must not crash the whole report.

    This covers a real failure: when R execution fails, recommend_and_analysis returns
    early with a dict of only one key. The report must still be written.
    """
    content = _render(report_dir, analysis_result={"summary": "Error: file not found"})
    assert "Comprehensive Metabolic Analysis Report" in content
    assert "Error: file not found" in content


def test_recommend_field_carries_recommendations_not_the_r_file_list():
    """The `recommend` field must contain what its name says.

    Before the fix it was overwritten by `success, result = run_r_code(...)` and
    returned the list of paths of the 22 output files. This does not run real R
    (that needs docker + 4 seconds); instead monkeypatch replaces the two dependencies
    and only checks one thing: which value flows into `recommend`.
    """
    import src.graph_agent.use_tool.code as code

    fake_recs = {"recommendations": [{"analysis": "t-test", "reason": "test reason"}]}
    fake_run = (True, {"files": [{"path": "/backend/uploads/output/analysis/x/t_test.csv"}]})

    orig = (code.extract_schema_and_config, code.diagnose_data_and_recommend,
            code.get_default_config, code.generate_combined_code, code.run_r_code)
    try:
        code.extract_schema_and_config = lambda *a, **k: {
            "group_count": 2, "csv_summary": "s", "config_by_data": {},
        }
        code.diagnose_data_and_recommend = lambda *a, **k: fake_recs
        code.get_default_config = lambda *a, **k: {"paired": "FALSE"}
        code.generate_combined_code = lambda *a, **k: "# code"
        code.run_r_code = lambda *a, **k: fake_run

        fn = getattr(code.recommend_and_analysis, "func", None) or code.recommend_and_analysis
        out = fn("../../uploads/csv/x.csv", "Label", False, False)
    finally:
        (code.extract_schema_and_config, code.diagnose_data_and_recommend,
         code.get_default_config, code.generate_combined_code,
         code.run_r_code) = orig

    assert out["recommend"] == fake_recs["recommendations"], (
        f"recommend 沒有裝建議，而是 {out['recommend']!r}"
    )
    # The R output must still be kept under another key -- seeing the docker exit 137
    # OOM message in it is how the memory problem was found, so fixing `recommend`
    # must not cost this diagnostic ability.
    assert out["run_log"] == fake_run[1]
    assert out["result_files"] == ["/backend/uploads/output/analysis/x/t_test.csv"]
