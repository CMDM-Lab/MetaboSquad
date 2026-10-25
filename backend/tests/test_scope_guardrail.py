"""Small-talk guardrail: this tool only does metabolomics-related work.

Requested explicitly on 2026-08-04: the `/chat` landing page's line offering to "just
chat with you" had to go, and a guardrail had to block small talk -- there are enough
chat bots already; this tool should focus on metabolomics, metabolic pathways,
statistical methods, and helping check the correctness/plausibility of figures.

The guardrail lives in the system prompt of `direct_response_node` (supervisor.py).
That is where every message not routed to a tool ends up: `_correct_misclassification`
downgrades analysis/plot_review without files to direct, and `INTENT_SYSTEM` explicitly
classifies "small talk, greetings" as direct. So catching it here is complete, with no
need for another classification call in the API layer.

What is tested here is the prompt's **content**, not LLM behaviour -- LLM responses
cannot be asserted reliably in unit tests. Real behaviour was confirmed by manual
acceptance (send a small-talk message, check that it declines and steers back to scope),
with results recorded in the commit message. This trade-off must be stated: these tests
guard against "someone deleting or rewriting the whole guardrail", not against "the
prompt says it but the LLM does not obey".
"""

import pytest

from src.graph_agent.supervisor import DIRECT_RESPONSE_SYSTEM

# Look at the prompt only. The first version used `inspect.getsource(direct_response_node)`,
# which also matched the docstring and comments -- a mention of "small talk" in the
# explanatory text made `test_prompt_no_longer_invites_small_talk` wrongly conclude that
# "the prompt still invites small talk". The prompt was therefore lifted into a module
# constant (supervisor.py) so the tests test the right thing.
PROMPT_SOURCE = DIRECT_RESPONSE_SYSTEM


IN_SCOPE_TOPICS = [
    "metabolom",      # metabolomics / metabolomic
    "pathway",        # metabolic pathways
    "statistic",      # statistical methods
    "figure",         # figure correctness/plausibility
]


@pytest.mark.parametrize("topic", IN_SCOPE_TOPICS)
def test_prompt_states_the_in_scope_topics(topic):
    """All four areas must be stated. With one missing, the LLM may decline work it should do."""
    assert topic in PROMPT_SOURCE.lower(), f"prompt 沒有提到 {topic}"


def test_prompt_instructs_refusal_of_out_of_scope_requests():
    """There must be an instruction to "decline out-of-scope requests", not just a description of capabilities.

    The original prompt only said "You are a Metabolomics Research Assistant" and then
    listed four functions -- that is a self-introduction, not a boundary. The LLM would
    still answer questions about the weather and moods.
    """
    low = PROMPT_SOURCE.lower()
    assert "decline" in low or "refuse" in low, "沒有指示要婉拒範圍外的請求"
    assert "out of scope" in low or "outside" in low or "unrelated" in low


def test_prompt_tells_the_model_to_redirect_not_just_refuse():
    """After declining, steer back to what it can do; otherwise physicians just get a "no" and are stuck."""
    low = PROMPT_SOURCE.lower()
    assert "redirect" in low or "instead" in low or "guide" in low


def test_prompt_no_longer_invites_small_talk():
    """Negative assertion: no wording inviting small talk may remain.

    This is necessary -- if "please decline out-of-scope requests" were added without
    removing "I can also just chat with you", the prompt would contradict itself and the
    LLM's behaviour would become a coin toss.
    """
    low = PROMPT_SOURCE.lower()
    for phrase in ["small talk", "chat about anything", "casual conversation"]:
        assert phrase not in low, f"prompt 還在邀請閒聊：{phrase}"


def test_capabilities_introduction_is_kept():
    """When "the user asks what you can do", introduce the four functions -- this was already
    there, and adding the guardrail must not remove it, otherwise physicians arriving for
    the first time have no idea what is possible."""
    low = PROMPT_SOURCE.lower()
    for feature in ["pubmed", "metaboanalystr", "pubchem"]:
        assert feature in low, f"功能介紹掉了 {feature}"
