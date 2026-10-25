"""The KEGG GMT path must not depend on the process working directory.

`GMT` was the relative string "backend/src/graph_agent/database/...". It
only resolved when the process started from the repository root. The README
starts the backend from `backend/`, where the same string points to
`backend/backend/src/...`, so `run_ora_analysis` and `run_gsea_prerank`
could not open the file and pathway analysis failed.
"""

import inspect
from pathlib import Path

import pytest

from src.graph_agent.use_tool import pathway_analysis as pa

BACKEND = Path(__file__).resolve().parent.parent
EXPECTED = BACKEND / "src" / "graph_agent" / "database" / "kegg_metabolites_hsa.gmt"


@pytest.mark.parametrize("cwd", [BACKEND.parent, BACKEND], ids=["repo-root", "backend"])
def test_gmt_resolves_to_database_dir_from_any_cwd(monkeypatch, cwd):
    monkeypatch.chdir(cwd)
    assert Path(pa.GMT).resolve() == EXPECTED


@pytest.mark.parametrize("tool", [pa.run_ora_analysis, pa.run_gsea_prerank], ids=lambda t: t.name)
def test_tools_default_to_the_gmt_constant(tool):
    default = inspect.signature(tool.func).parameters["gmt_path"].default
    assert default == pa.GMT
