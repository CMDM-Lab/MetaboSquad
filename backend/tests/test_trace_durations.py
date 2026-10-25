"""Per-step timing for the SSE `status` event contract (Task 6).

The trace step table answers "where did the user wait?". Without per-step timing
the table shows identical rows and a 22-second statistical test is
indistinguishable from a 0.3-second intent classification.

The contract is additive: a `status` event's `prev_ms` closes step
`seq - 1`, the `saved` event's `last_ms` closes the final step. A client
that ignores both fields sees exactly the payload shape it saw before this
change — `chat.py` is the only file touched (the API layer, not
`backend/src/graph_agent/`, which is frozen).
"""

import json
import time

import pytest
from langchain_core.messages import AIMessage
from sqlmodel import select

from api.routers.chat import Chat, ChatMessage


class StatusOnlyAgent:
    """Fake `main_agent`: emits a caller-chosen sequence of status events
    via the LangGraph `writer`, then returns a plain text reply. Mirrors
    `FakeAgent` in test_sse_events.py, parameterised on the statuses so each
    test can control exactly how many steps (and thus how many `prev_ms`
    boundaries) are produced.
    """

    def __init__(self, statuses: list[str]):
        self.statuses = statuses

    def invoke(self, payload, config=None):
        writer = config["configurable"]["writer"]
        for status in self.statuses:
            writer({"status": status})
        return {"messages": [AIMessage(content="done")]}


class TimedStatusAgent:
    """Like `StatusOnlyAgent`, but sleeps a caller-chosen real duration
    *after* emitting each status (including after the last one, before
    returning). This is what makes the durations recorded by `chat.py`
    unambiguous under test timing: `timed_statuses` pairs each status with
    the wall-clock gap that should follow it, so a test can assert not just
    that a duration exists, but that it reflects a specific, deliberately
    non-monotonic pattern (see `test_prev_ms_and_last_ms_reflect_actual_gaps`
    below for why non-monotonic gaps matter for catching a wrong baseline).
    """

    def __init__(self, timed_statuses: list[tuple[str, float]]):
        self.timed_statuses = timed_statuses

    def invoke(self, payload, config=None):
        writer = config["configurable"]["writer"]
        for status, gap_sec in self.timed_statuses:
            writer({"status": status})
            time.sleep(gap_sec)
        return {"messages": [AIMessage(content="done")]}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Same shape as test_sse_events.py's helper of the same name — kept as
    a local copy rather than a cross-test-module import, matching this
    test suite's existing convention (no test file imports from another).
    """
    events = []
    for chunk in text.split("\n\n"):
        if not chunk.strip():
            continue
        event_name, data = "message", None
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_name, data))
    return events


def _run_statuses(session, tid: str, statuses: list[str]):
    """Prepare a fresh thread, run a fake agent that emits exactly
    `statuses` as status events, and return the parsed SSE events.
    """
    from fastapi.testclient import TestClient

    from api.database import get_session
    from main import create_app

    session.commit()
    session.add(Chat(thread_id=tid, title="新對話"))
    session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        client.app.state.main_agent = StatusOnlyAgent(statuses)
        res = client.post(
            f"/api/chat/{tid}",
            json={"message": "分析這個"}
        )
    app.dependency_overrides.clear()
    return _parse_sse(res.text)


def _run_timed(session, tid: str, timed_statuses: list[tuple[str, float]]):
    """Same as `_run_statuses`, but drives `TimedStatusAgent` so the gaps
    between statuses are real, caller-controlled wall-clock durations.
    """
    from fastapi.testclient import TestClient

    from api.database import get_session
    from main import create_app

    session.commit()
    session.add(Chat(thread_id=tid, title="新對話"))
    session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        client.app.state.main_agent = TimedStatusAgent(timed_statuses)
        res = client.post(
            f"/api/chat/{tid}",
            json={"message": "分析這個"}
        )
    app.dependency_overrides.clear()
    return _parse_sse(res.text)


def _trace_block(session, tid: str) -> dict:
    msg = session.exec(
        select(ChatMessage)
        .where(ChatMessage.thread_id == tid)
        .where(ChatMessage.role == "assistant")
    ).one()
    return next(b for b in msg.content if b["type"] == "trace")


def test_status_event_closes_the_previous_step(session):
    # Two status events; the second must carry prev_ms closing the first.
    events = _run_statuses(session, "th-td-1", ["first step", "second step"])
    status = [d for name, d in events if name == "status"]
    assert len(status) == 2
    assert "prev_ms" not in status[0]  # nothing to close yet on step 1
    assert isinstance(status[1]["prev_ms"], int)
    assert status[1]["prev_ms"] >= 0


def test_saved_event_closes_the_final_step(session):
    events = _run_statuses(session, "th-td-2", ["only step"])
    saved = next(d for name, d in events if name == "saved")
    assert isinstance(saved["last_ms"], int)
    assert saved["last_ms"] >= 0


def test_persisted_trace_blocks_carry_ms(session):
    # A reloaded thread must show the same durations as the live run; the
    # frontend has no way to recompute them after the fact.
    _run_statuses(session, "th-td-3", ["a", "b"])
    block = _trace_block(session, "th-td-3")
    assert [s["seq"] for s in block["steps"]] == [1, 2]
    assert all("ms" in s for s in block["steps"])


def test_status_content_and_seq_still_present_with_prev_ms_added(session):
    """prev_ms is additive: the fields an old client already reads
    (`content`, `seq`) must be unchanged in shape and value."""
    events = _run_statuses(session, "th-td-4", ["step one", "step two"])
    status = [d for name, d in events if name == "status"]
    assert status[0] == {"content": "step one", "seq": 1}
    assert status[1]["content"] == "step two"
    assert status[1]["seq"] == 2


# Deliberately non-monotonic real gaps (seconds) for the value-aware test
# below: step 1's gap is the longest, step 2's the shortest, step 3's in
# between. "Non-monotonic" is the point — a baseline bug that measures
# elapsed time since the *stream started* (instead of since the previous
# status) can only ever produce cumulative, non-decreasing values across
# steps, so it cannot coincidentally reproduce this pattern. The pairwise
# gaps (400 vs 50 vs 200 ms) are also far enough apart that no plausible
# scheduling/asyncio-polling overhead on a loaded CI box confuses one for
# another.
_GAP_A_SEC = 0.40  # closes step 1 (via the status announcing step 2)
_GAP_B_SEC = 0.05  # closes step 2 (via the status announcing step 3)
_GAP_C_SEC = 0.20  # closes step 3, the final step (via `saved`'s last_ms)

# Generous absolute tolerance: wide enough to absorb real scheduling jitter
# (the SSE loop polls its queue every 10ms, plus thread/asyncio overhead),
# but tight enough that it cannot mask either mutation under test — the
# smallest pairwise difference between the three target gaps is 150ms
# (|_GAP_A_SEC - _GAP_C_SEC| = 200ms; |_GAP_B_SEC - _GAP_C_SEC| = 150ms),
# and a "measure from stream start" bug's cumulative values land at least
# 200ms past the correct per-step value (see the by-hand trace in the
# mutation-check section of task-6-report.md).
_TOL_MS = 120


def test_prev_ms_and_last_ms_reflect_actual_gaps(session):
    """Value-aware check. The other tests above only assert presence, type,
    or `>= 0` on the recorded durations — none asserts *which* step gets
    *which* value. A wrong baseline (measuring every interval from the
    stream's start instead of from the previous status) would still satisfy
    every one of those assertions: durations would exist, be non-negative
    integers, and even land on the "right" key — they would just grow
    monotonically instead of reflecting the true, per-step gap.

    This test drives three statuses with deliberately unequal, non-monotonic
    real gaps and asserts the *persisted* trace (not just the live SSE
    payload — see the mutation-check note on why the append-before-stamp
    bug only shows up there) carries the correct value on the correct step.
    """
    tid = "th-td-5"
    _run_timed(session, tid, [
        ("step one", _GAP_A_SEC),
        ("step two", _GAP_B_SEC),
        ("step three", _GAP_C_SEC),
    ])
    block = _trace_block(session, tid)
    ms_by_seq = {s["seq"]: s["ms"] for s in block["steps"]}

    assert ms_by_seq[1] == pytest.approx(_GAP_A_SEC * 1000, abs=_TOL_MS)
    assert ms_by_seq[2] == pytest.approx(_GAP_B_SEC * 1000, abs=_TOL_MS)
    assert ms_by_seq[3] == pytest.approx(_GAP_C_SEC * 1000, abs=_TOL_MS)

    # Structural guard on top of the absolute values: step 2's gap is the
    # shortest of the three by construction. A "measure since stream start"
    # bug can only produce non-decreasing values across steps (each later
    # closing event's elapsed-since-start is a superset of the previous
    # one's), so it can never satisfy `ms_by_seq[2] < ms_by_seq[1]` — this
    # holds regardless of how much absolute timing noise the test machine
    # adds, as long as that noise doesn't itself exceed ~150ms.
    assert ms_by_seq[2] < ms_by_seq[1]
    assert ms_by_seq[2] < ms_by_seq[3]
