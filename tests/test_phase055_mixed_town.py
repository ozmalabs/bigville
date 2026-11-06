"""Phase 055: a mixed town of 3 LLM residents and 97 simple residents, 100 turns, on a fake provider that records
its calls. The simple residents never reach the provider, and the model is consulted rarely."""
from __future__ import annotations

from bigville.llm_scenario import build_llm_town
from bigville.reporting import llm_report
from llm_stub import FakeProvider, varied_reply

TURNS = 100
LLM = 3


def test_three_llm_residents_among_ninety_seven_simple_ones_run_a_hundred_turns_on_few_calls():
    provider = FakeProvider(varied_reply)
    game = build_llm_town(provider, llm_residents=LLM)
    residents = len(game.characters)
    assert residents == 100
    assert len(game.llm_residents) == LLM
    for _ in range(TURNS):
        assert game.step()["status"] == "advanced"

    calls = len(provider.calls)
    assert {call["meta"]["actor"] for call in provider.calls} <= set(game.llm_residents)
    # One consult per LLM resident per turn would be TURNS * LLM calls. Momentum keeps the count well below that
    # and far below TURNS * residents (10,000 resident-turns).
    assert calls < TURNS * LLM
    assert calls * 10 < TURNS * residents
    report = llm_report(game.backends)
    assert report["residents_count"] == LLM
    assert report["total"]["calls"] == calls
    # A turn on a model plan never reaches decide(), so these are at most the LLM resident-turns.
    assert report["total"]["autopilot_turns"] + report["total"]["decisions"] <= TURNS * LLM
