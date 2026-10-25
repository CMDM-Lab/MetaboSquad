"""`sig_all` must actually propagate through `from_analysis_state`, not just
be declared on `MainState`.

`tests/test_structured_keys_declared.py` only asserts the *declaration* half
of the silent-drop hazard: that every key in `STRUCTURED_KEYS` exists in
`MainState.__annotations__`. It says nothing about the mapping layer
(`supervisor.py`'s `from_analysis_state`) that turns the analysis subgraph's
raw result dict into the dict merged back into `MainState`. A key can be
declared on `MainState` and still never reach `chat.py`, if the function that
builds the merge dict simply forgets to read it off the subgraph state —
exactly the gap this test closes for `sig_all`.

This needs no OpenAI API key and no graph run: `from_analysis_state` is a
plain dict-in, dict-out function, called directly with a fixture dict that
stands in for the analysis subgraph's final state.
"""

from src.graph_agent.supervisor import from_analysis_state


def test_from_analysis_state_propagates_sig_all():
    result = from_analysis_state({
        "sig_all": ["120.0812_5.32", "Citric acid"],
        "significant_metabolites": ["Citric acid"],
    })
    assert result["sig_all"] == ["120.0812_5.32", "Citric acid"]


def test_from_analysis_state_defaults_sig_all_to_empty_list_when_absent():
    """A subgraph state that never set `sig_all` (e.g. the early return in
    `extract_significant_node` before the CSV is found) must still produce a
    `[]`, not a `KeyError` or `None` — `chat.py`'s payload filter treats an
    absent/`None` value as "drop the key" but an empty list as a real,
    meaningful result (see `STRUCTURED_KEYS`'s comment in
    `api/routers/chat.py`), so the two must not be conflated here.
    """
    result = from_analysis_state({})
    assert result["sig_all"] == []
