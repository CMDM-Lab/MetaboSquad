"""CITATION.cff tripwire: the citation metadata must agree with the rest of the repository.

Why this file exists: the journal asks for software citation metadata (CITATION.cff) and
a DOI release of the code. The version, license and repository URL in CITATION.cff are
copies of values that live elsewhere (frontend/package.json, LICENSE, the manuscript).
A copy drifts silently; this test goes red when it does.
"""

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/CMDM-Lab/MetaboSquad"


def _cff() -> dict:
    return yaml.safe_load((REPO / "CITATION.cff").read_text(encoding="utf-8"))


def test_required_fields_present():
    cff = _cff()
    for key in ("cff-version", "message", "title", "authors", "version", "license"):
        assert cff.get(key), f"CITATION.cff has no '{key}'"
    assert cff["cff-version"] == "1.2.0"
    for a in cff["authors"]:
        assert a.get("family-names") and a.get("given-names"), a


def test_version_matches_package_json():
    pkg = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert str(_cff()["version"]) == pkg["version"]


def test_license_matches_license_file():
    first_line = (REPO / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "MIT License"
    assert _cff()["license"] == "MIT"


def test_repository_url():
    assert _cff()["repository-code"] == REPO_URL
