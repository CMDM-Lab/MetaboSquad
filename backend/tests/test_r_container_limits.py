"""Resource limits of the R container: pin the measured numbers.

`use_tool/code.py` is in the frozen zone (`src/graph_agent/`). This file does not change
it; it only turns "why this number" into an assertion that can go red, so the next
person who wants to lower it sees the measurements first.

Measured on 2026-08-04 (`lcms_table.csv`, 12 samples x 410 features, preprocessing +
fold-change + t-test + volcano + PCA, all at 300 dpi):

    mem_limit=512m -> exit=137 (SIGKILL/OOM), 14 files, died after the t-test
    mem_limit=768m -> exit=0, 22 files
    mem_limit=1g   -> exit=0, 22 files
    mem_limit=2g   -> exit=0, 22 files

The original value of 512m got every analysis killed before the report was produced.
The R statistics actually finished (the log says "A total of 31 significant features
were found."); it died in the later plotting modules, so the symptom was
"analysis_result.success=False, result_files=[]" rather than an obvious error -- from
the user's point of view it was just "Analysis results CSV not found.".

The threshold lies between 512m and 768m; 2g leaves headroom, because users upload
their own data, which may be much larger than this demo file.
"""

import re
import inspect

# Measured floor: below this value, the demo data runs out of memory (OOM).
MEASURED_OOM_FLOOR_BYTES = 768 * 1024 * 1024

_UNITS = {"b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def _parse_docker_mem(value: str) -> int:
    m = re.fullmatch(r"(\d+)([bkmg]?)", value.strip().lower())
    assert m, f"無法解析的 docker 記憶體字串：{value!r}"
    return int(m.group(1)) * _UNITS[m.group(2) or "b"]


def _mem_limit_from_source() -> str:
    from src.graph_agent.use_tool.code import run_r_code

    # run_r_code is wrapped by @tool; get the source of the underlying function.
    fn = getattr(run_r_code, "func", None) or run_r_code
    src = inspect.getsource(fn)
    m = re.search(r'mem_limit\s*=\s*"([^"]+)"', src)
    assert m, "run_r_code 裡找不到 mem_limit —— 容器設定被改寫了，請重新量測"
    return m.group(1)


def test_r_container_memory_is_above_measured_oom_floor():
    """Go red below the measured floor, and include the measurements in the message."""
    raw = _mem_limit_from_source()
    actual = _parse_docker_mem(raw)
    assert actual >= MEASURED_OOM_FLOOR_BYTES, (
        f"mem_limit={raw} 低於實測下限 768m。2026-08-04 實測：512m 會讓示範資料的"
        f" analysis 以 exit 137（OOM）失敗，且失敗方式是靜默的"
        f"（success=False、result_files=[]，使用者只看到 "
        f"'Analysis results CSV not found.'）。要調低請先重跑量測。"
    )


def test_parse_docker_mem_handles_the_units_we_actually_use():
    """The assertion above relies entirely on this parser. If it read '512m' as 512 bytes,
    the floor check would instead always pass -- so the three notations are pinned explicitly here."""
    assert _parse_docker_mem("512m") == 512 * 1024 ** 2
    assert _parse_docker_mem("2g") == 2 * 1024 ** 3
    assert _parse_docker_mem("768M") == 768 * 1024 ** 2
