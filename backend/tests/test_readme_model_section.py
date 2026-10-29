"""README tripwire: the "Changing the model" section must list the files that really create an LLM.

Why this file exists: the section listed `graph/plot_graph.py` as having an
`# ===== Ollama =====` block (it has none) and left out `use_tool/literature_add.py`
(it has one). A reader who follows the README then runs part of the system on
Ollama and part on OpenAI, with no error to show it.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "backend" / "src"
OLLAMA_MARKER = "# ===== Ollama ====="
LLM_CALL = re.compile(r"\b(ChatOpenAI|init_chat_model)\(")


def _model_section() -> str:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^## Changing the model\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, "README.md has no '## Changing the model' section"
    return m.group(1)


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _files_with(pattern) -> set[str]:
    hits = set()
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if (pattern in text) if isinstance(pattern, str) else pattern.search(text):
            hits.add(_rel(p))
    return hits


def _listed(section: str, heading: str) -> set[str]:
    m = re.search(rf"{re.escape(heading)}\n(.*?)(?=\n\n|\Z)", section, re.S)
    assert m, f"README model section has no '{heading}' list"
    return set(re.findall(r"`(backend/[^`]+\.py)`", m.group(1)))


def test_every_ollama_block_is_listed():
    listed = _listed(_model_section(), "Files with a prepared Ollama block:")
    assert listed == _files_with(OLLAMA_MARKER)


def test_every_llm_without_ollama_block_is_listed():
    listed = _listed(_model_section(), "Files without a prepared Ollama block:")
    assert listed == _files_with(LLM_CALL) - _files_with(OLLAMA_MARKER)
