"""Comments and docstrings in the backend must be English.

The repository is public, so the code has to be readable by people who do not
read Chinese. This scan covers `#` comments and docstrings only. String
literals are out of scope on purpose: LLM prompts and messages shown to users
are product behaviour, not documentation, and some of them are Chinese by
design.

Mirrors `frontend/src/__tests__/comment-language.test.ts`.
"""

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

# CJK Unified Ideographs plus the CJK symbols & punctuation block.
CJK = re.compile(r"[一-鿿　-〿]")

SKIP_DIRS = {"venv", ".venv", "__pycache__", "uploads", ".pytest_cache"}


def _sources() -> list[Path]:
    return sorted(
        p for p in BACKEND.rglob("*.py")
        if not SKIP_DIRS.intersection(p.relative_to(BACKEND).parts)
        and not p.relative_to(BACKEND).parts[0].startswith("temp_")
    )


def _cjk_comment_lines(path: Path) -> list[int]:
    source = path.read_text(encoding="utf-8")
    lines: set[int] = set()

    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT and CJK.search(tok.string):
            lines.add(tok.start[0])

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                    and CJK.search(body[0].value.value)):
                lines.add(body[0].lineno)

    return sorted(lines)


def test_scan_finds_sources():
    assert len(_sources()) > 20


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(BACKEND)))
def test_comments_and_docstrings_are_english(path):
    found = _cjk_comment_lines(path)
    assert not found, f"Chinese comment or docstring at lines {found}"


def test_scanner_flags_chinese_comment_and_docstring(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""模組說明"""\n'
        'x = "中文字串不算"  # 這行要抓\n'
        'def f():\n'
        '    """English only."""\n',
        encoding="utf-8",
    )
    assert _cjk_comment_lines(sample) == [1, 2]
