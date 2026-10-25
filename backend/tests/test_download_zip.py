"""ZIP download: content redaction and packaging integrity.

Markdown read through `/api/artifacts` already has server paths redacted at the API
boundary (see `api/artifacts.redact_server_paths`), but the ZIP ships **the files
themselves**, bypassing that path. After unzipping, a physician opening
`significant_*.md` would still see `/home/<user>/projects/...`, so packaging must do
the same thing.
"""

import zipfile

from api.artifacts import BASE_DIR, UPLOAD_ROOT

# Deliberately contains a byte sequence that fails utf-8 decoding (starts with 0x89PNG +
# the full byte range): if packaging does "decode -> edit string -> encode" without
# handling decode failures, this file is silently rewritten by errors="replace", and
# the extracted chart is corrupted without any error.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256))


def _seed(folder: str) -> tuple:
    target = UPLOAD_ROOT / "output" / "analysis" / folder
    (target / "mummichog_output").mkdir(parents=True, exist_ok=True)
    (target / "report.md").write_text(
        f"* 結果已存至 {target}\n* 顯著特徵 31 個\n", encoding="utf-8")
    (target / "plot.png").write_bytes(_PNG_BYTES)
    (target / "mummichog_output" / "tree.js").write_text(
        f'var base = "{target}";\n', encoding="utf-8")
    zip_path = UPLOAD_ROOT / "output" / "zip" / f"analysis_{folder}.zip"
    return target, zip_path


def _cleanup(target, zip_path) -> None:
    for p in sorted(target.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    target.rmdir()
    zip_path.unlink(missing_ok=True)


def test_zip_redacts_server_paths_in_text_files(client):
    """Both the report and the .js produced by mummichog carry absolute paths; both must be redacted."""
    target, zip_path = _seed("zipfix-1")
    try:
        res = client.post("/api/uploads/download-zip",
                          json={"folder_name": "uploads/output/analysis/zipfix-1"})
        assert res.status_code == 200

        with zipfile.ZipFile(zip_path) as zf:
            md = zf.read("report.md").decode("utf-8")
            js = zf.read("mummichog_output/tree.js").decode("utf-8")

        assert str(BASE_DIR) not in md
        assert str(BASE_DIR) not in js
        assert "uploads/output/analysis/zipfix-1" in md
        # Redaction only touches the path prefix; the report's own content is kept as-is.
        assert "顯著特徵 31 個" in md
    finally:
        _cleanup(target, zip_path)


def test_zip_leaves_binary_files_byte_identical(client):
    """Charts (.png) and R's .qs files are binary: any string-level rewrite of them can
    silently corrupt the file. Packaging must copy them as-is, byte-for-byte identical."""
    target, zip_path = _seed("zipfix-2")
    try:
        res = client.post("/api/uploads/download-zip",
                          json={"folder_name": "uploads/output/analysis/zipfix-2"})
        assert res.status_code == 200

        with zipfile.ZipFile(zip_path) as zf:
            assert zf.read("plot.png") == _PNG_BYTES
    finally:
        _cleanup(target, zip_path)


def test_zip_still_contains_every_file_including_subfolders(client):
    """Redaction must not change what is packaged: subfolders (mummichog_output/) are still
    included, and paths stay relative to the packaged folder."""
    target, zip_path = _seed("zipfix-3")
    try:
        res = client.post("/api/uploads/download-zip",
                          json={"folder_name": "uploads/output/analysis/zipfix-3"})
        assert res.status_code == 200

        with zipfile.ZipFile(zip_path) as zf:
            assert sorted(zf.namelist()) == [
                "mummichog_output/tree.js", "plot.png", "report.md",
            ]
    finally:
        _cleanup(target, zip_path)
