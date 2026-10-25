"""The analysis report must land under `uploads/`, otherwise physicians cannot see it.

Third real run, 2026-08-04: analysis ran end to end, `saved` was emitted, R produced
22 files, but the `significant_*.md` report was written to

    backend/analysis/lcms_table_20260804_181712/significant_2026-08-04-18-17-04.md

i.e. **outside** `uploads/`. As a result `/api/artifacts` could not read it
(`resolve_uploads_path` in `api/artifacts.py` correctly blocks out-of-bounds paths),
so the ResultCard "full report" tab was empty.

Root cause is `extract_significant` in the frozen-zone `use_tool/pathway_analysis.py`:

    parent_dir = full_path.parent          # <root>/backend/uploads/output/analysis/<dir>
    result_dir = str(Path(parent_dir.parent.name) / parent_dir.name)
                                           # -> "analysis/<dir>", keeps only the last two names

`save_significant_node` in `graph/analysis_graph.py` passes it to
`os.makedirs(workdir)` and writes the file, which is CWD-relative (CWD = `backend/`),
hence `backend/analysis/...`. The fallback in the same function writes
`f"uploads/output/analysis/{date}"`, which shows `result_dir` was always meant to
have that shape.
"""

import pytest

from api.artifacts import UPLOAD_ROOT, resolve_uploads_path

T_TEST_CSV = (
    '"","t.stat","p.value","-log10(p)","FDR"\n'
    '"327.2/3418",25.787,1.7678e-10,9.7524,1.2e-08\n'
    '"326.2/3415",21.274,1.1726e-09,8.9308,3.4e-08\n'
)


def _unwrap(tool):
    return getattr(tool, "func", None) or tool


@pytest.fixture(name="t_test_under_uploads")
def t_test_under_uploads_fixture():
    """Put t_test.csv where real R output lands, and clean it up after the test."""
    import shutil

    d = UPLOAD_ROOT / "output" / "analysis" / "pytest_report_loc"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "t_test.csv"
    f.write_text(T_TEST_CSV, encoding="utf-8")
    # This is the format a real run feeds in: `code.py` computes result_files relative
    # to the monorepo root, so they carry a `/backend/` prefix (measured value:
    # `/backend/uploads/output/analysis/lcms_table_20260804_181712/t_test.csv`).
    # The BASE_DIR of `extract_significant` is also the monorepo root, so the two agree.
    yield "/backend/uploads/output/analysis/pytest_report_loc/t_test.csv"
    shutil.rmtree(d, ignore_errors=True)


def test_result_dir_stays_inside_uploads(t_test_under_uploads):
    """save_significant_node uses `result_dir` as the output directory (CWD-relative),
    so it must start with `uploads/...`; otherwise the report lands outside uploads."""
    from src.graph_agent.use_tool.pathway_analysis import extract_significant

    res = _unwrap(extract_significant)(t_test_under_uploads, fdr_cutoff=0.05)
    assert isinstance(res, dict), f"extract_significant 失敗：{res!r}"

    result_dir = res["result_dir"]
    assert result_dir.startswith("uploads/"), (
        f"result_dir={result_dir!r} 不在 uploads 底下，報告會被寫到專案根目錄，"
        f"/api/artifacts 讀不到 → 醫師的「完整報告」tab 是空的"
    )


def test_result_dir_is_servable_by_the_artifacts_endpoint(t_test_under_uploads):
    """The real acceptance criterion is not "the string looks right" but "the artifacts endpoint can read it".

    `/api/artifacts` goes through `resolve_uploads_path`, which raises ValueError for
    anything out of bounds. Asserting on it directly is closer to what physicians
    actually experience than checking a prefix.
    """
    from src.graph_agent.use_tool.pathway_analysis import extract_significant

    res = _unwrap(extract_significant)(t_test_under_uploads, fdr_cutoff=0.05)
    resolved = resolve_uploads_path(res["result_dir"])   # raises ValueError when out of bounds
    assert resolved.is_dir()


def test_mummichog_txt_path_points_at_a_real_file(t_test_under_uploads):
    """Also pin that the path handed to mummichog_analysis really exists --
    this is upstream of the `'str' object has no attribute 'get'` crash."""
    from pathlib import Path

    from src.graph_agent.use_tool.pathway_analysis import extract_significant

    res = _unwrap(extract_significant)(t_test_under_uploads, fdr_cutoff=0.05)
    mumm = res.get("mummichog_txt_path")
    assert mumm, "沒有產出 mummichog 峰表"
    assert Path(mumm).is_file(), f"mummichog_txt_path 指向不存在的檔案：{mumm}"
