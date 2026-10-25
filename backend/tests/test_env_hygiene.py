"""Environment-variable tripwire: catches settings where "an empty string is worse than no line at all".

`conftest.py` already calls `load_dotenv()`, so what is seen here is the content of `backend/.env`.

Why this file exists: on 2026-08-04 literature search always returned 0 papers, and it
took a long time to find that `.env` contained `NCBI_KEY = ` (line present, no value).
`os.getenv` reads `''` rather than `None`, so Biopython put `api_key=` into the Entrez
URL and NCBI answered HTTP 400. Both paths in `src/graph_agent/use_tool/search.py`
swallow that failure and only print to stdout:

- `search_pubmed` (search.py:125): outermost `except Exception: return []`
- `search_abstract` (search.py:281): the except for each batch only prints, and
  finally returns the accumulated `results` (`[]` if all failed)

The result is that "the key is broken" and "this topic really has no literature" look
identical to the user -- the system produces a fully formatted report saying "0 papers
in total". Those two excepts are in the frozen zone (`src/graph_agent/`, whose behaviour
the 100-question benchmark depends on) and cannot be changed, so the guard lives here:
it goes red as soon as the setting is wrong, instead of when a user receives a fake
empty report.
"""

import os

import pytest

# For these variables, "line present but empty" causes silent failure, worse than no line at all.
# Each value is the actual consequence of the variable being empty; the failure message prints it.
EMPTY_IS_WORSE_THAN_ABSENT = {
    "NCBI_KEY": (
        "Biopython 會把 api_key= 塞進 Entrez URL，NCBI 回 HTTP 400，"
        "search_pubmed/search_abstract 靜默回空 list → 文獻搜尋固定 0 篇。"
        "要嘛填真 key，要嘛把整行註解掉（見 .env.sample）。"
    ),
    "EMAIL": (
        "NCBI 要求 Entrez.email 有值才不會限流／封鎖；空字串等於沒設。"
    ),
}


@pytest.mark.parametrize("name", sorted(EMPTY_IS_WORSE_THAN_ABSENT))
def test_env_var_is_absent_or_non_empty(name):
    raw = os.environ.get(name)
    if raw is None:
        pytest.skip(f"{name} 未設定——這是允許的（程式碼會走 api_key=None 的路徑）")
    assert raw.strip(), f"{name} 設成空值：{EMPTY_IS_WORSE_THAN_ABSENT[name]}"
