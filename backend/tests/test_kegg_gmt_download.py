"""`download_kegg_metabolite_gmt` must not write a silently truncated GMT.

KEGG's REST API answers HTTP 403 once a client sends requests too quickly.
Measured on 2026-10-25: at 0.1 s spacing, requests 1-21 got 200 and every
request after that got 403. The downloader counted each 403 as a failure,
skipped the pathway, and still reported success with exit code 0. A
regenerated file had 215 pathways instead of the 304 in the file the
manuscript used, so pathway enrichment results would differ with no error.

The contract pinned here: transient refusals are retried, and if any pathway
still cannot be fetched the function raises and leaves no output file behind.
"""

import pytest
import requests

from src.graph_agent.use_tool import download_path_db as dl

PATHWAY_LIST = "path:hsa00010\tGlycolysis / Gluconeogenesis - Homo sapiens (human)\n" \
               "path:hsa04912\tGnRH signaling pathway - Homo sapiens (human)\n"
LINKS = {
    "hsa00010": "path:hsa00010\tcpd:C00022\npath:hsa00010\tcpd:C00024\n",
    "hsa04912": "",                                   # empty for hsa: falls back to map
    "map04912": "path:map04912\tcpd:C00076\npath:map04912\tcpd:C00165\n",
}


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _fake_get(refusals):
    """`refusals` maps a URL suffix to the responses to give before the real one."""
    def get(url, headers=None, timeout=None):
        for key, queue in refusals.items():
            if url.endswith(key) and queue:
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                return _Resp(item)
        if url.endswith("/list/pathway/hsa"):
            return _Resp(200, PATHWAY_LIST)
        pid = url.rsplit("/", 1)[1]
        return _Resp(200, LINKS.get(pid, ""))
    return get


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)


def _read(path):
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()]


def test_writes_every_pathway_including_map_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({}))
    out = tmp_path / "kegg.gmt"
    dl.download_kegg_metabolite_gmt(str(out))
    rows = _read(out)
    assert [r[1] for r in rows] == ["hsa00010", "hsa04912"]
    assert rows[1][2:] == ["C00076", "C00165"]


def test_rate_limit_403_is_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({
        "/link/compound/hsa00010": [403, 403],
        "/link/compound/map04912": [403],
    }))
    out = tmp_path / "kegg.gmt"
    dl.download_kegg_metabolite_gmt(str(out))
    assert [r[1] for r in _read(out)] == ["hsa00010", "hsa04912"]


def test_connection_error_is_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({
        "/link/compound/hsa00010": [requests.ConnectionError("reset")],
    }))
    out = tmp_path / "kegg.gmt"
    dl.download_kegg_metabolite_gmt(str(out))
    assert [r[1] for r in _read(out)] == ["hsa00010", "hsa04912"]


def test_persistent_refusal_raises_and_leaves_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({
        "/link/compound/map04912": [403] * 100,
    }))
    out = tmp_path / "kegg.gmt"
    with pytest.raises(RuntimeError, match="hsa04912"):
        dl.download_kegg_metabolite_gmt(str(out))
    assert not out.exists()


def test_persistent_exception_raises_and_leaves_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({
        "/link/compound/hsa00010": [requests.ConnectionError("reset")] * 100,
    }))
    out = tmp_path / "kegg.gmt"
    with pytest.raises(RuntimeError, match="hsa00010"):
        dl.download_kegg_metabolite_gmt(str(out))
    assert not out.exists()


def test_pathway_list_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(dl.requests, "get", _fake_get({
        "/list/pathway/hsa": [403] * 100,
    }))
    out = tmp_path / "kegg.gmt"
    with pytest.raises(RuntimeError):
        dl.download_kegg_metabolite_gmt(str(out))
    assert not out.exists()
