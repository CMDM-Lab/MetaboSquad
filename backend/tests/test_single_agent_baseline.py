"""The single-agent baseline must load its four skills from any working directory.

The baseline is the ReAct controller that the manuscript compares with the
graph-based system. It reads its progressive-disclosure guides from
`baseline/skills/*.md`. The original loader used the relative path "skill",
so it found the guides only when the process started inside the package
directory. From `backend/` it created an empty `skill/` directory and the
agent ran with no skill tools at all.
"""

from pathlib import Path

import pytest

from src.graph_agent.baseline import single_agent as sa

BACKEND = Path(__file__).resolve().parent.parent
SKILLS = {"analysis", "literature", "plot_review", "pubchem"}


@pytest.mark.parametrize("cwd", [BACKEND.parent, BACKEND], ids=["repo-root", "backend"])
def test_skills_load_from_any_cwd(monkeypatch, cwd):
    monkeypatch.chdir(cwd)
    assert {t.name for t in sa.load_all_skills()} == SKILLS


def test_missing_skill_dir_raises_and_creates_nothing(tmp_path):
    missing = tmp_path / "skills"
    with pytest.raises(FileNotFoundError):
        sa.load_all_skills(missing)
    assert not missing.exists()


def test_skill_tool_returns_the_guide_body():
    tool = next(t for t in sa.load_all_skills() if t.name == "pubchem")
    text = tool.invoke({})
    assert "pubchem_id_mapping" in text
    assert "description:" not in text


def _names(tools):
    # `generate_figure_report` is a plain function; create_agent wraps it.
    return {getattr(t, "name", None) or t.__name__ for t in tools}


GRAPH_TOOLS = {"search_pubmed", "pubchem_id_mapping", "recommend_and_analysis",
               "figure_compliance_checker", "generate_figure_report",
               "load_image_as_base64"}


def test_default_registry_has_the_four_guides_as_in_the_paper_run():
    # The paper's baseline run loaded the four skill guides; the author confirmed
    # the skill-tool calls in the LangSmith traces (2026-10-29). Table 2 counts
    # task-tool calls only, so the guide calls do not appear in its numbers.
    names = _names(sa.skill_agent_tools())
    assert GRAPH_TOOLS <= names
    assert SKILLS <= names


def test_registry_without_skills_has_no_guides():
    names = _names(sa.skill_agent_tools(with_skills=False))
    assert GRAPH_TOOLS <= names
    assert not SKILLS & names


@pytest.mark.parametrize("fn", [sa.skill_agent_tools, sa.create_agent_skill, sa.run])
def test_every_entry_point_defaults_to_skills(fn):
    import inspect
    assert inspect.signature(fn).parameters["with_skills"].default is True
