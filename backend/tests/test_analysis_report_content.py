"""Wording of the analysis report: it must not mislead physicians.

Two real findings (report from the fourth real run, 2026-08-04):

1. `**Target File(s)**: ['../../uploads/csv/lcms_table.csv']`
   The `../../` prefix compensates for the three inconsistent BASE_DIRs in the
   frozen zone (see `_graph_file_path` in `api/routers/chat.py`). It is an internal
   implementation detail, yet it was printed straight into the report that
   physicians and reviewers see, where it looks like a bug.

2. The heading says "List of Significant **Metabolites** (Total: 31)", but what is
   listed are m/z/retention-time values such as `327.2/3418` -- all 31 are
   **unidentified** MS features, and 0 are named metabolites. This only appeared in
   status events (the execution trace, which scrolls away); the report itself did
   not say it. Physicians may well take those numbers for metabolites, and they are not.
   (`sig_all = sig_mz_features + sig_identified_metabolites`, see extract_significant
   in `use_tool/pathway_analysis.py`, so both counts can be derived exactly from
   `len(sig_all)` and `len(significant_metabolites)`.)
"""

import shutil

import pytest

from api.artifacts import UPLOAD_ROOT


@pytest.fixture(name="report_dir")
def report_dir_fixture():
    d = UPLOAD_ROOT / "output" / "analysis" / "pytest_report_content"
    d.mkdir(parents=True, exist_ok=True)
    yield "uploads/output/analysis/pytest_report_content"
    shutil.rmtree(d, ignore_errors=True)


def _render(report_dir: str, *, sig_all, identified, files):
    """Run save_significant_node once and return the full text of the written report."""
    from src.graph_agent.graph.analysis_graph import save_significant_node

    state = {
        "date": "2026-08-04-18-20-53",
        "result_dir": report_dir,
        "sig_all": sig_all,
        "significant_metabolites": identified,
        "files": files,
        "analysis_result": {"r_code": "# r code here"},
    }
    out = save_significant_node(state, {"configurable": {}})
    with open(out["output_path"], encoding="utf-8") as f:
        return f.read()


def test_target_file_shows_plain_filename_not_internal_prefix(report_dir):
    """The report should show only the file name. `../../` is an internal detail compensating for the frozen-zone BASE_DIR."""
    content = _render(
        report_dir,
        sig_all=["327.2/3418"], identified=[],
        files=["../../uploads/csv/lcms_table.csv"],
    )
    assert "lcms_table.csv" in content
    assert "../../" not in content, "內部路徑前綴洩漏到醫師看得到的報告裡"


def test_report_states_identified_and_unidentified_counts(report_dir):
    """When none of the 31 features is named, the report must state "0 named, 31 unidentified".

    Writing only "Significant Metabolites (Total: 31)" followed by a list of m/z values
    makes physicians think those 31 are metabolites. This is a result-interpretation
    problem, not just wording.
    """
    mz = [f"3{i}.2/34{i}" for i in range(10, 41)]      # 31 bare m/z values
    assert len(mz) == 31
    content = _render(report_dir, sig_all=mz, identified=[], files=["uploads/csv/x.csv"])

    assert "31" in content
    # The count of named features must appear explicitly, not only be inferable from "Total: 31"
    assert "Identified metabolites (with names): 0" in content, (
        "報告沒有明講有名字的代謝物是 0 個"
    )
    assert "Unidentified" in content


def test_report_counts_are_split_correctly_when_some_are_named(report_dir):
    """Mixed case: sig_all = m/z + named. Each count must be correct on its own.

    This guards against "the total looks right for both sides" -- if the implementation
    hard-coded 0, the test above would still pass.
    """
    content = _render(
        report_dir,
        sig_all=["327.2/3418", "326.2/3415", "citric acid", "L-lactic acid"],
        identified=["citric acid", "L-lactic acid"],
        files=["uploads/csv/x.csv"],
    )
    assert "Identified metabolites (with names): 2" in content
    assert "Unidentified" in content
    # unidentified = 4 - 2 = 2
    import re
    m = re.search(r"Unidentified[^\n:]*:\s*(\d+)", content)
    assert m and m.group(1) == "2", f"未鑑定數量不對：{m.group(0) if m else '找不到那一行'}"
