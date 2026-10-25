"""Every key in `STRUCTURED_KEYS` must be declared in `MainState`.

LangGraph **silently drops** a channel that a subgraph writes but the parent State does
not declare -- no error, no warning, the data just disappears. So if a field `chat.py`
wants to send to the frontend is missing from `MainState`, `result.get(key)` is always
None and the frontend never receives it.

Measured with plot_review on 2026-08-04: the graph finished and the report was written to
`uploads/output/plot_review/2026-08-04-21-13-58/`, but SSE emitted **no result event**.
The knock-on effect was far worse than "one panel missing": `folder` hangs off the result
block, and the result block is only created when there is a structured_payload
(`chat.py`), so the folder in the DB was NULL -- after a refresh, the physician's "files"
and "full report" tabs were both empty, and the report, though on disk, was unreachable.

This test is not only about review_result: it applies the rule "anything sent to the
frontend must be declared" to all five keys at once, so anyone who later adds to
STRUCTURED_KEYS but forgets state.py gets a red test immediately.
"""

import pytest

from api.routers.chat import STRUCTURED_KEYS
from src.graph_agent.state import MainState


@pytest.mark.parametrize("key", STRUCTURED_KEYS)
def test_structured_key_is_declared_in_main_state(key):
    declared = set(MainState.__annotations__)
    assert key in declared, (
        f"chat.py 的 STRUCTURED_KEYS 有 {key!r}，但 MainState 沒宣告它。"
        f"LangGraph 會靜默丟棄未宣告的 channel，所以這個欄位永遠到不了前端，"
        f"而且會連帶讓 result block（含 folder）整個不被建立。"
        f"請在 src/graph_agent/state.py 的 MainState 加上它。"
    )


def test_main_state_annotations_is_the_right_introspection_target():
    """The assertion above relies entirely on `MainState.__annotations__`.

    `MainState` is a `TypedDict`; if it ever changes to another form (dataclass, pydantic
    model), `__annotations__` may no longer reflect the set of channels, and those
    assertions would "always pass because nothing can be read". A channel known to exist
    serves as a sentinel here.
    """
    assert "messages" in MainState.__annotations__
    assert "files" in MainState.__annotations__
