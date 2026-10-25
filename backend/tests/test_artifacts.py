import pytest

from api.artifacts import BASE_DIR, resolve_uploads_path, UPLOAD_ROOT


def test_resolves_normal_path():
    p = resolve_uploads_path("output/analysis/2026-01-01")
    assert p == UPLOAD_ROOT / "output" / "analysis" / "2026-01-01"


@pytest.mark.parametrize("evil", [
    "../../etc",
    "../../../etc/passwd",
    "output/../../../etc",
    "/etc/passwd",
])
def test_rejects_traversal(evil):
    with pytest.raises(ValueError):
        resolve_uploads_path(evil)


def test_rejects_sibling_prefix_attack():
    """uploads_evil must not pass just because it shares a string prefix (the classic abspath+startswith hole)"""
    with pytest.raises(ValueError):
        resolve_uploads_path("../uploads_evil/secret")


@pytest.mark.parametrize("root_pointing", [
    "",
    ".",
    "/uploads/",
    "uploads/",
    "output/..",
])
def test_rejects_path_resolving_to_upload_root_itself(root_pointing):
    """A folder that resolves to UPLOAD_ROOT itself = a request to list the whole uploads tree,
    including every user's analysis output and its markdown content; it must be rejected.

    The "output/.." case ensures the check compares the *resolved absolute path*, rather
    than only checking whether the cleaned string is empty -- cleaned is non-empty for
    this input, yet it still resolves to the root.
    """
    with pytest.raises(ValueError):
        resolve_uploads_path(root_pointing)


@pytest.mark.parametrize("prefixed", [
    "/uploads/output/analysis/x",
    "uploads/output/analysis/x",
])
def test_strips_uploads_prefix(prefixed):
    """The path field the frontend receives has the /uploads/... form and is sent back as-is in queries."""
    assert resolve_uploads_path(prefixed) == UPLOAD_ROOT / "output" / "analysis" / "x"


def test_endpoint_returns_403_on_traversal(client, session):
    session.commit()

    res = client.get("/api/artifacts",
                     params={"folder": "../../etc"})
    assert res.status_code == 403


def test_endpoint_returns_403_on_empty_folder(client, session):
    """If not blocked, folder="" would list the whole uploads/ tree (see
    test_rejects_path_resolving_to_upload_root_itself); the endpoint must return 403."""
    session.commit()

    res = client.get("/api/artifacts",
                     params={"folder": ""})
    assert res.status_code == 403


def test_endpoint_returns_404_on_missing_folder(client, session):
    session.commit()

    res = client.get("/api/artifacts",
                     params={"folder": "output/analysis/does-not-exist"})
    assert res.status_code == 404


def test_endpoint_lists_files_and_reads_markdown(client, session):
    session.commit()

    target = UPLOAD_ROOT / "output" / "analysis" / "test-fixture"
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.md").write_text("# 標題\n\n內容", encoding="utf-8")
    (target / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (target / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    try:
        res = client.get("/api/artifacts",
                         params={"folder": "output/analysis/test-fixture"})
        assert res.status_code == 200
        body = res.json()
        kinds = {f["name"]: f["kind"] for f in body["files"]}
        assert kinds == {"report.md": "md", "plot.png": "image", "table.csv": "csv"}
        assert body["markdown"]["report.md"].startswith("# 標題")
        assert body["files"][0]["path"].startswith("/uploads/")
    finally:
        for f in target.iterdir():
            f.unlink()
        target.rmdir()


def _read_markdown(client, code: str, folder_name: str, body_text: str) -> str:
    """Write `body_text` as a report and read its markdown content back through the endpoint."""
    target = UPLOAD_ROOT / "output" / "analysis" / folder_name
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.md").write_text(body_text, encoding="utf-8")
    try:
        res = client.get("/api/artifacts",
                         params={"folder": f"output/analysis/{folder_name}"})
        assert res.status_code == 200
        return res.json()["markdown"]["report.md"]
    finally:
        for f in target.iterdir():
            f.unlink()
        target.rmdir()


def test_markdown_does_not_leak_the_server_filesystem_path(client, session):
    """Seen in practice (2026-08-12): mummichog's completion message writes the **absolute**
    path of the output folder into the report (`use_tool/pathway_analysis.py:239`, frozen
    zone), and the report is then shown to the user as-is:

        * **Mummichog Result**: <"Mummichog finished, results saved to">
          /home/<user>/projects/MetaboSquad/backend/uploads/output/analysis/...

    That path leaks the OS account name, the project's location on disk and the
    deployment layout, and is useless to physicians -- what they need to know is
    "which folder", for which `uploads/...` is enough; it is also exactly the relative
    form that `/api/artifacts` and the ZIP download both use.

    The producer is in the frozen zone (changing it would alter behaviour the benchmark
    depends on), so redaction happens at the read boundary: file contents stay
    untouched, and what is sent out carries no server paths.
    """
    session.commit()

    leaked = f"{UPLOAD_ROOT}/output/analysis/lcms_table_20260812_152604"
    out = _read_markdown(
        client, "DRRD1", "redact-1",
        f"* **Mummichog Result**: Mummichog 完成！結果已存至 {leaked}",
    )

    assert str(BASE_DIR) not in out
    assert out.endswith("uploads/output/analysis/lcms_table_20260812_152604")


def test_markdown_redaction_also_covers_the_monorepo_root(client, session):
    """There are two BASE_DIRs in the frozen zone: `pathway_analysis.py` resolves to the
    monorepo root (one level above backend/), while `api/artifacts.py` uses backend/.
    Redacting only the latter would leak, in full, any path of the former that points
    outside backend/.

    This deliberately uses a path under the monorepo root but **not** inside backend/:
    a `{monorepo}/backend/...` path is, as a string, identical to `{BASE_DIR}/...` and
    would be consumed by the backend rule, leaving this rule untested. Conversely, the
    `endswith` in the previous test pins the order of the two rules: if the order were
    reversed, it would be redacted to `backend/uploads/...`.
    """
    session.commit()

    out = _read_markdown(
        client, "DRRD2", "redact-2",
        f"參見 {BASE_DIR.parent}/docs/deployment.md",
    )

    assert str(BASE_DIR.parent) not in out
    assert out.endswith("docs/deployment.md")


def test_markdown_redaction_leaves_ordinary_prose_alone(client, session):
    """Only the server path prefix is redacted, not the report's own content -- statistics,
    metabolite names and strings that are already relative paths must pass through unchanged."""
    session.commit()

    prose = ("# 分析報告\n\n* 顯著特徵 31 個\n"
             "* Citric acid (p = 0.003)\n"
             "* 結果在 uploads/output/analysis/x\n")
    assert _read_markdown(client, "DRRD3", "redact-3", prose) == prose
