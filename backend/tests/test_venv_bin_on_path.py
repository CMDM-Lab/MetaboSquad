"""The venv's bin directory must be on PATH, otherwise the graph cannot find CLI tools.

`mummichog_analysis` in `use_tool/pathway_analysis.py` calls an external CLI via
`subprocess.run(["mummichog", ...])`. That executable is installed by pip into
`venv/bin/`, but the production start command is

    venv/bin/python -m uvicorn main:app ...

-- specifying the interpreter directly does **not** activate the venv, so `venv/bin` is
not on PATH (measured 2026-08-04: the backend process's PATH did not contain it at all).
The result: the package is installed and `venv/bin/mummichog` exists, yet `subprocess`
still raises FileNotFoundError, and the report only says the 'mummichog' command was not
detected on the system.

Writing it into the deployment docs gives zero signal (nothing tells you when nobody
does it), so `main.py` now fixes it up itself at startup, guarded by this test.
"""

import os
import shutil
import sys
from pathlib import Path


def test_interpreter_bin_dir_is_prepended_to_path():
    """After import main, the directory of the running interpreter must be on PATH.

    Use the directory of `sys.executable` rather than hard-coding `venv/bin`: whether
    venv, conda or system python, "console scripts installed with this interpreter" are
    always there.

    **Do not `.resolve()`**: `venv/bin/python` is a symlink to `/usr/bin/python3.13`, and
    resolving it gives `/usr/bin` -- which is on PATH anyway, so this test would pass
    without any fix (this actually happened). Console scripts are installed in the
    directory containing the symlink, not where it points.
    """
    import main  # noqa: F401  -- PATH should be fixed up at import time

    bin_dir = str(Path(sys.executable).parent)
    assert bin_dir.endswith("venv/bin") or "venv" in bin_dir, (
        f"這個測試假設跑在 venv 裡（bin_dir={bin_dir}）；若改用其他環境，"
        f"請重新確認它還有偵測能力"
    )
    assert bin_dir in os.environ.get("PATH", "").split(os.pathsep), (
        f"{bin_dir} 不在 PATH 上，subprocess 找不到 pip 裝的 CLI 工具"
    )


def test_mummichog_cli_is_resolvable():
    """The real acceptance criterion: `shutil.which` finds it -- exactly how subprocess resolves it.

    This goes red if either "the package is not installed" or "PATH was not fixed up";
    both are real failures, and both used to show up only as a one-line message in the report.
    """
    import main  # noqa: F401

    assert shutil.which("mummichog"), (
        "找不到 mummichog CLI。要嘛 `venv/bin/pip install mummichog` 沒跑過，"
        "要嘛 main.py 補 PATH 的那段壞了。"
    )
