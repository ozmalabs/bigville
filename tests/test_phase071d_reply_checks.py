"""Phase 071d, decision 1: a reply is accepted unless it is malformed.

An unknown major action, an unknown free action, a nonexistent target, an unknown region and a missing required target
reach the world, which refuses each with a REFUSAL_REASONS code shown in `last`. The repair call runs only for a
malformed reply (not JSON, not an object, a field of the wrong type).

Fake providers only; no network.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville import free_replies                                  # noqa: E402
from bigville.api import create_game                               # noqa: E402
from bigville.backends import LLMBackend                           # noqa: E402
from bigville.backends import reply_schema                         # noqa: E402
from bigville.backends.llm import validate_response                # noqa: E402
from domains.pack import load_pack                                 # noqa: E402

PACK = "bigville"
SEED = 305000
REFUSALS = load_pack(PACK)["REFUSAL_REASONS"]


class Seq:
    """A fake provider: the i-th call gets the i-th text (the last text repeats)."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self.texts[min(self.calls, len(self.texts)) - 1]


def _reply(major=None, free=None):
    return json.dumps({"major_action": major, "free_actions": free or [], "utterances": [], "memory_updates": [],
                       "continuation": None})


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                       ticks_per_period="world")


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _llm(game, name, *texts):
    script = Seq(*texts)
    game.set_backend(name, LLMBackend(game.characters[name], script, autopilot=False))
    return script


def test_an_unknown_major_action_is_refused_by_the_world_with_no_repair(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": "teleport", "params": {}}))
    town.step()
    assert script.calls == 1
    outcome = town.world.last_outcome(name)
    assert outcome["applied"] is False and outcome["reason"] == "unsupported"


def test_an_unknown_free_action_is_refused_by_the_world_with_no_repair(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": "rest"}, [{"action": "juggle", "target": None, "params": {}}]))
    town.step()
    assert script.calls == 1
    outcome = free_replies.last_free(town, name)
    assert outcome["action"] == "juggle" and outcome["applied"] is False and outcome["reason"] == "unsupported"


def test_a_nonexistent_target_is_refused_by_the_world_with_no_repair(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": "strike", "target": "Nobody Known", "params": {}}))
    town.step()
    assert script.calls == 1
    outcome = town.world.last_outcome(name)
    assert outcome["applied"] is False and outcome["reason"] in REFUSALS


def test_an_unknown_region_is_refused_by_the_world_with_no_repair(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": "press", "target": "nowhere at all", "params": {}}))
    town.step()
    assert script.calls == 1
    outcome = town.world.last_outcome(name)
    assert outcome["applied"] is False and outcome["reason"] in REFUSALS


def test_a_missing_required_target_is_refused_by_the_world_with_no_repair(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": "rest"}, [{"action": "reply", "params": {"text": "hello"}}]))
    town.step()
    assert script.calls == 1
    outcome = free_replies.last_free(town, name)
    assert outcome["applied"] is False and outcome["reason"] == "no_target"


def test_a_malformed_reply_goes_to_the_repair_call_and_a_repaired_one_is_accepted(town):
    name = _adult(town.world)
    script = _llm(town, name, _reply({"action": 5, "params": {}}), _reply(None))
    town.step()
    assert script.calls == 2
    assert town.backends[name].last_backend_state["outcome"] == "repaired"


def test_a_malformed_reply_is_an_error_and_a_name_the_world_does_not_know_is_not():
    fields = tuple(load_pack(PACK)["PROMPT_RESPONSE_FIELDS"])
    assert validate_response({"major_action": {"action": 5}}, fields)
    assert validate_response({"major_action": {"action": "teleport"}}, fields) == []
    assert validate_response({"major_action": {"action": ""}}, fields) == []
    assert validate_response({"free_actions": [{"action": None}]}, fields)
    assert validate_response({"free_actions": [{"action": "juggle"}]}, fields) == []
    assert reply_schema.check({"major_action": {"action": "teleport"}}, PACK) == []
    assert reply_schema.check({"major_action": {"action": ""}}, PACK) == []
    assert reply_schema.check({"free_actions": [{"action": "juggle"}]}, PACK) == []
    assert reply_schema.check({"free_actions": [{"action": "reply"}]}, PACK) == []
    assert reply_schema.check({"major_action": {"action": "attempt", "intensity": ["x"]}}, PACK)


def test_an_unknown_intensity_or_amount_word_folds_to_a_normal_effort():
    reply = {"major_action": {"action": "fetch", "params": {"amount": "sheaves"}, "intensity": "sideways"},
             "utterances": [], "memory_updates": [], "continuation": None}
    assert reply_schema.check(reply, PACK) == []
    wire = reply_schema.to_wire(reply, PACK)
    assert wire["major_action"]["params"]["amount"] == 1.0
    assert wire["major_action"]["params"]["intensity"] == 1.0
    free = {"free_actions": [{"action": "set_intensity", "params": {"intensity": "sideways"}}]}
    assert reply_schema.to_wire(free, PACK)["free_actions"][0]["params"]["intensity"] == 1.0
