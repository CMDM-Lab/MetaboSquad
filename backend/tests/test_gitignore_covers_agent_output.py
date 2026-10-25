"""Agent output must not go into git.

It happened twice on a single day, 2026-08-04:

1. `run_r_code` creates `temp_<uuid>/` under `backend/` (removed with rmtree only after
   the run), so one `git add -A` while an analysis was running swept in all the
   `.qs`/`.png`/`script.R` files.
2. `plot_review` additionally creates `uploads/colorblind/` for colour-blindness
   simulation images, and `.gitignore` at the time only listed `output/`, `csv/*` and
   `image/*` one by one, missing it -- 8 generated images were committed (by the
   developer; removed afterwards with git rm --cached).

The second incident proved that "list each one" is inherently leaky. `.gitignore` is now
an allowlist (everything under uploads is ignored by default, with only the two demo
data files let through), and this test guards it: it checks that "any subdirectory
added in future is also covered", not just the known names.

User-uploaded data also lands under uploads, so this rule is a privacy safeguard as
well, not just repo hygiene.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _is_ignored(rel_path: str) -> bool:
    """Exit code of `git check-ignore`: 0 = ignored, 1 = not ignored.

    Use real git rather than parsing .gitignore ourselves -- the interaction between
    negation rules (`!`) and directory re-inclusion is easy to get wrong by hand, and
    what actually decides behaviour is git itself.
    """
    r = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=REPO_ROOT, capture_output=True,
    )
    return r.returncode == 0


AGENT_OUTPUT_PATHS = [
    # known ones
    "backend/uploads/output/analysis/x/report.md",
    "backend/uploads/output/literature/x/result.md",
    "backend/uploads/colorblind/fig_PROTAN_20260804.png",
    "backend/temp_deadbeef/script.R",
    # user-uploaded data, must never go into git
    "backend/uploads/csv/patient_cohort.csv",
    "backend/uploads/image/patient_scan.png",
    # subdirectories that only appear in future: the point of the allowlist is to cover these too
    "backend/uploads/some_future_tool_output/a.txt",
    "backend/uploads/deeply/nested/new/dir/b.json",
]


@pytest.mark.parametrize("rel", AGENT_OUTPUT_PATHS)
def test_agent_output_path_is_gitignored(rel):
    assert _is_ignored(rel), (
        f"{rel} 沒有被 .gitignore 蓋到。agent 產物或醫師資料會被一個 "
        f"`git add -A` 提交進版控。"
    )


DEMO_ASSETS = [
    "backend/uploads/csv/lcms_table.csv",
    "backend/uploads/image/benchmark_semantic_pca_01.png",
]


@pytest.mark.parametrize("rel", DEMO_ASSETS)
def test_demo_assets_are_still_tracked(rel):
    """The other half of the allowlist: these two demo data files must **stay** under version control.

    Without this half, "add all of uploads to .gitignore" would also make the tests
    above pass, but a fresh clone would have no demo files, so neither analysis nor
    figure review could be tried out directly.
    """
    assert not _is_ignored(rel), f"{rel} 被 .gitignore 蓋掉了，新環境會缺示範資料"
    assert (REPO_ROOT / rel).is_file()
