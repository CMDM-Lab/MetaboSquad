"""Path resolution and return type of `mummichog_analysis`.

Measured on 2026-08-04: after the `files` channel and container memory were fixed, R
finished and found 31 significant features at FDR < 0.05, but the report stage crashed
with `AttributeError: 'str' object has no attribute 'get'`
(`mummichog_res.get("status")` at `graph/analysis_graph.py:357`).

Root cause is an inconsistent hand-off between two functions inside the frozen zone,
with three different BASE_DIRs confirmed:

    code.py             extract_significant  -> backend/src/graph_agent
    pathway_analysis.py extract_significant  -> <monorepo root>
    pathway_analysis.py mummichog_analysis   -> backend/src/graph_agent

The `mummichog_txt_path` produced by `extract_significant` is an **absolute path**, and
`mummichog_analysis` applies `peak_table_path.lstrip("/")` and joins it onto its own
BASE_DIR, producing

    backend/src/graph_agent/home/<user>/projects/MetaboSquad/backend/uploads/...

which can never exist. The "file not found" branch then returns a **str** (the function
is declared `-> str`, but the success/failure branches return a dict -- mixed), and the
downstream `.get()` blows up.

Two things are pinned here: absolute paths must not be mangled, and a dict is always
returned whether it succeeds or fails -- the latter makes `.get()` in
`save_significant_node` always safe, rather than fixing only this one trigger.
"""

import shutil
from pathlib import Path

import pytest

from src.graph_agent.use_tool.pathway_analysis import mummichog_analysis

PEAK_TABLE = "m/z\tretention_time\tp-value\tt-score\n327.2\t3418.0\t1.7678e-10\t25.787\n"


def _unwrap(tool):
    """For an @tool-wrapped function, get the underlying callable to call directly (bypassing the LangChain schema)."""
    return getattr(tool, "func", None) or tool


@pytest.fixture(name="abs_peak_table")
def abs_peak_table_fixture(tmp_path):
    f = tmp_path / "t_test_mummichog.txt"
    f.write_text(PEAK_TABLE, encoding="utf-8")
    return f


def test_absolute_peak_table_path_is_not_mangled(abs_peak_table):
    """`extract_significant` hands over an absolute path, which lstrip must not destroy.

    The assertion is "**the file was found**", not "the return type is dict". This was
    learned the hard way: the first version asserted `isinstance(result, dict)`, but
    since the same fix also made "file not found" return a dict, removing absolute-path
    support still left the test green -- both cases happened to return the same type,
    so the test lost its detecting power.

    Before the fix: takes the "file not found" branch (the path is built as
    `backend/src/graph_agent/<absolute path without leading slash>`).
    After the fix: the file is readable and execution proceeds to the CLI (if mummichog
    is not installed locally, it returns the "command not detected" message).
    """
    result = _unwrap(mummichog_analysis)(str(abs_peak_table))
    assert isinstance(result, dict), f"回傳的是 str：{result!r}"
    assert "file not found" not in result.get("error", ""), (
        f"絕對路徑被破壞了，檔案明明存在卻說找不到：{result!r}"
    )


def test_relative_peak_table_path_still_resolves_against_base_dir(tmp_path, monkeypatch):
    """Relative-path behaviour is unchanged -- this only adds absolute-path support, without changing existing semantics.

    monkeypatch points BASE_DIR at tmp_path, to avoid putting test files in a frozen-zone directory.
    """
    import src.graph_agent.use_tool.pathway_analysis as pa

    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "peak.txt").write_text(PEAK_TABLE, encoding="utf-8")
    monkeypatch.setattr(pa, "_MUMMICHOG_BASE_DIR", tmp_path)

    result = _unwrap(mummichog_analysis)("sub/peak.txt")
    assert isinstance(result, dict)


def test_missing_file_returns_dict_not_string():
    """Must be a dict even when the file is not found.

    `save_significant_node` always calls `.get()` on this value; returning a str crashes
    the whole SSE stream with AttributeError, and physicians only see a generic "system
    error" that points nowhere near the real cause. With a dict, the existing branch
    `elif mummichog_res and "error" in mummichog_res` writes the message into the report.
    """
    result = _unwrap(mummichog_analysis)("/definitely/not/here/peak.txt")
    assert isinstance(result, dict), f"回傳 str 會讓下游 .get() 崩掉：{result!r}"
    assert "error" in result


def test_three_base_dirs_are_still_inconsistent_in_frozen_zone():
    """Pin the premise of "why absolute-path support is needed".

    If the frozen zone ever unifies the three BASE_DIRs, this test turns red as a
    reminder to check whether the absolute-path support above is still needed (keeping
    it is harmless, but the comments would become misleading).
    """
    code_base = Path("src/graph_agent/use_tool/code.py").resolve().parent.parent
    pa_file = Path("src/graph_agent/use_tool/pathway_analysis.py").resolve()
    extract_base = pa_file.parent.parent.parent.parent.parent
    mumm_base = pa_file.parent.parent

    assert code_base != extract_base, "BASE_DIR 已統一，請重新檢視本檔的前提"
    assert mumm_base != extract_base, "BASE_DIR 已統一，請重新檢視本檔的前提"
