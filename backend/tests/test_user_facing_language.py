"""String literals that reach the user or the LLM must be English.

The public demo is reviewed by editors and referees who do not read Chinese, and
the reports, status lines and error messages come from string literals in the
backend. LLM prompts are scanned too: a Chinese example or instruction in a
prompt makes the model answer in Chinese.

Out of scope (not shown to the user):
  - docstrings (covered by test_comment_language.py)
  - arguments of print() and logger calls (server console only)

ALLOWED lists the literals that are Chinese on purpose, with the reason.
Mirrors the structure of test_comment_language.py.
"""

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[一-鿿　-〿＀-￯]")
SCAN_DIRS = ("src", "api")
# baseline/ keeps the single-agent prompt and skills verbatim from the run reported in the
# manuscript (Tables 1 and 2), so the comparison can be reproduced. Do not translate it.
SKIP_DIRS = {"__pycache__", "baseline"}
LOG_CALLS = {"print", "debug", "info", "warning", "warn", "error", "exception", "critical"}

# (relative path, literal) -> reason. Keep this list short.
ALLOWED: dict[tuple[str, str], str] = {
    ("api/routers/chat.py", "新對話"):
        "legacy default title stored in existing chats; matched, never shown as new text",
}
# Keyword lists that match the user's own (possibly Chinese) input for routing.
ALLOWED_FILES_FOR_KEYWORDS = {
    "src/graph_agent/supervisor.py": {"metabolite_keywords", "lit_keywords"},
}


def _sources() -> list[Path]:
    out = []
    for d in SCAN_DIRS:
        out += [p for p in (BACKEND / d).rglob("*.py")
                if not SKIP_DIRS.intersection(p.relative_to(BACKEND).parts)]
    return sorted(out)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _excluded_subtrees(tree: ast.AST, rel: str) -> set[int]:
    """ids of every node inside a log call or an allowed keyword assignment."""
    ids: set[int] = set()
    keyword_names = ALLOWED_FILES_FOR_KEYWORDS.get(rel, set())
    for node in ast.walk(tree):
        root = None
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in LOG_CALLS:
                root = node
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in keyword_names for t in node.targets):
            root = node.value
        if root is not None:
            ids.update(id(n) for n in ast.walk(root))
    return ids


def cjk_literals(path: Path) -> list[tuple[int, str]]:
    rel = path.relative_to(BACKEND).as_posix() if path.is_relative_to(BACKEND) else path.name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree) | _excluded_subtrees(tree, rel)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in skip and CJK.search(node.value)
                and (rel, node.value) not in ALLOWED):
            found.append((node.lineno, node.value.strip().splitlines()[0][:60]))
    return sorted(found)


def test_scan_finds_sources():
    assert len(_sources()) > 20


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(BACKEND)))
def test_user_facing_strings_are_english(path):
    found = cjk_literals(path)
    assert not found, "Chinese string literals:\n" + "\n".join(f"  line {n}: {s}" for n, s in found)


def test_scanner_flags_strings_but_not_logs_or_docstrings(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""模組說明不算"""\n'
        'x = "報告標題"\n'
        'print("伺服器日誌不算")\n'
        'logger.info(f"日誌 {x} 不算")\n'
        'y = f"共 {x} 條"\n',
        encoding="utf-8",
    )
    # An f-string yields one constant per literal part, so line 5 can appear twice.
    assert sorted({n for n, _ in cjk_literals(sample)}) == [2, 5]
