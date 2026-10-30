"""artifacts.py - safely enumerate the output folders under uploads

Security: always use os.path.commonpath to decide whether a path is inside UPLOAD_ROOT.
Never use str.startswith -- /app/uploads_evil passes a prefix check against /app/uploads.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# backend/api/artifacts.py → backend/
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = (BASE_DIR / "uploads").resolve()

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_MAX_MARKDOWN_BYTES = 512 * 1024

# Server filesystem path prefixes to redact from outgoing report content. Two, not one: the
# frozen `use_tool/pathway_analysis.py` builds paths from the monorepo root, while `api/` uses
# backend/; handling only one of them leaks the full paths built by the other.
#
# Longest first is required, not cosmetic: backend/ itself lives under the monorepo root,
# so if the monorepo root were matched first, `{root}/backend/uploads/x` would lose only its
# first half and become `backend/uploads/x` instead of `uploads/x` -- that still leaks the
# deployment layout and is not the relative form used by `/api/artifacts` and the ZIP download.
_SERVER_PATH_PREFIXES = sorted(
    {str(BASE_DIR), str(BASE_DIR.parent)}, key=len, reverse=True
)


def redact_server_paths(text: str) -> str:
    """Strip server filesystem path prefixes from outgoing text, leaving only uploads/... relative paths.

    Origin (measured 2026-08-12): mummichog's completion message writes the absolute path of the
    output folder into the report (`use_tool/pathway_analysis.py:239`), `analysis_graph.py:397`
    then puts it into the markdown summary, and the user sees on screen

        Results saved to /home/<user>/projects/MetaboSquad/backend/uploads/output/...

    That prefix leaks the OS account, the project's location on disk and the deployment layout,
    and is useless to physicians -- they need to know which folder, and `uploads/...` is enough.

    Redact at the read boundary rather than at the producer: the producer is in the frozen zone and
    the benchmark depends on its behaviour.
    Files on disk are untouched; only outgoing content changes, so this also covers existing reports.

    Note this only covers API responses. The ZIP download ships the files themselves, which still
    contain absolute paths (see `download_analysis_zip`) -- that is handled separately at packing time.
    """
    for root in _SERVER_PATH_PREFIXES:
        text = text.replace(root + "/", "").replace(root, "")
    return text


def redact_server_paths_bytes(data: bytes) -> bytes:
    """Bytes version of `redact_server_paths`, used for ZIP packing.

    Deliberately avoids "decode -> edit string -> encode": the text files being packed are not
    guaranteed to be valid utf-8 (mummichog's .js/.txt output mixes encodings), and on a decode
    failure `errors="replace"` silently rewrites file content; physicians would find the damage
    only after unzipping, with no error message. The prefixes are ASCII paths, so matching on bytes is enough.
    """
    for root in _SERVER_PATH_PREFIXES:
        raw = root.encode("utf-8")
        data = data.replace(raw + b"/", b"").replace(raw, b"")
    return data


def resolve_uploads_path(rel: str) -> Path:
    """Resolve a relative path to an absolute path under UPLOAD_ROOT; raise ValueError if it escapes."""
    cleaned = (rel or "").replace("\\", "/").strip()
    # The frontend may send "/uploads/output/..." or "output/..."; strip the prefix uniformly
    if cleaned.startswith("/uploads/"):
        cleaned = cleaned[len("/uploads/"):]
    elif cleaned.startswith("uploads/"):
        cleaned = cleaned[len("uploads/"):]
    if cleaned.startswith("/"):
        # Still starting with / after stripping the recognised /uploads/ prefix = the caller gave an
        # absolute filesystem path. Never silently reinterpret it as relative (that would turn "/etc/passwd"
        # into UPLOAD_ROOT/etc/passwd and pass the commonpath check); always reject.
        raise ValueError(f"Path outside the allowed root: {rel}")

    candidate = (UPLOAD_ROOT / cleaned).resolve()

    try:
        common = os.path.commonpath([str(UPLOAD_ROOT), str(candidate)])
    except ValueError:
        # Different drives (Windows)
        raise ValueError(f"Path outside the allowed root: {rel}")

    if common != str(UPLOAD_ROOT):
        raise ValueError(f"Path outside the allowed root: {rel}")

    if candidate == UPLOAD_ROOT:
        # The resolved path equals the root itself ("", ".", "/uploads/", "output/..", etc.) =
        # a request to enumerate the whole uploads tree, including every user's analysis output and markdown.
        # This function's contract is to resolve paths *under* UPLOAD_ROOT; the root itself is outside
        # the contract, so always reject (rather than leaving list_folder to filter afterwards).
        raise ValueError(f"Path outside the allowed root: {rel}")

    return candidate


def _classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "md"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix == ".csv":
        return "csv"
    return "other"


def list_folder(rel: str) -> dict[str, Any]:
    """List the files in a folder (including subfolders) and read the contents of .md files."""
    root = resolve_uploads_path(rel)
    if not root.is_dir():
        raise FileNotFoundError(rel)

    files: list[dict[str, Any]] = []
    markdown: dict[str, str] = {}

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        kind = _classify(path)
        relative_to_uploads = path.relative_to(UPLOAD_ROOT).as_posix()
        display_name = path.relative_to(root).as_posix()
        files.append({
            "name": display_name,
            "path": f"/uploads/{relative_to_uploads}",
            "kind": kind,
            "size": path.stat().st_size,
        })
        if kind == "md" and path.stat().st_size <= _MAX_MARKDOWN_BYTES:
            markdown[display_name] = redact_server_paths(
                path.read_text(encoding="utf-8", errors="replace"))

    return {"folder": rel, "files": files, "markdown": markdown}
