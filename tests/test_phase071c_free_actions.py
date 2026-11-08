"""Phase 071c, decision 1: an LLM resident has the same affordances as a player.

Every MAJOR_ACTIONS key and every FREE_ACTIONS key is reachable from a reply (the parity test below), and the free
actions a reply carries are applied by the world the same way a player's are:

* a reply's free_actions go through reply_schema (checked against FREE_ACTIONS), to_wire and ActorResponse;
* each is routed to world.free_action (bigville/free_replies.ROUTES), and its outcome is kept as the resident's
  `last` when it is the newest outcome (refusals with their REFUSAL_REASONS code, a glance with its sound and place);
* an unknown free action is refused as unsupported and the refusal is shown in `last`;
* free actions take no slot and no tick, and the simple backends never choose them.

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
from bigville.backends import ActorResponse, LLMBackend            # noqa: E402
from bigville.backends import reply_schema                         # noqa: E402
from bigville.backends.prompt_packet import packet_system          # noqa: E402
from bigville.backends.prompts import PromptBuilder                # noqa: E402
from domains.agent_view_check import felt_body_problems            # noqa: E402
from domains.lexicon import intensity_value                        # noqa: E402
from domains.pack import load_pack                                 # noqa: E402

PACK = "bigville"
SEED = 305000
PLAYER = "Verity Peaseblossom"
FORBIDDEN = [word.lower() for word in load_pack(PACK)["INTEROCEPTION"]["forbidden_words"]]
MAJOR = load_pack(PACK)["MAJOR_ACTIONS"]
FREE = load_pack(PACK)["FREE_ACTIONS"]

# The parity table: how each key is reached from a reply. A major action is named in major_action; a free action is
# named in free_actions and routed by free_replies.ROUTES. Speech is also written as utterances (a speak free action
# and an utterance reach the same world call).
FREE_PARAMS = {"text": "hello", "note": "note:1", "item": "flour", "giver": "Bram Smith", "intensity": "hard"}


class Script:
    """A fake provider: returns the same text on every call."""

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self.text


def _reply(**fields):
    base = {"major_action": None, "utterances": [], "memory_updates": [], "continuation": None}
    base.update(fields)
    return json.dumps(base)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _other(world, name):
    return next(other for other in world._actors if other != name)


def _felt(world, name, locus="arm", amount=0.4):
    """Give a resident a located injury, so that it feels a sharp or dull signal at that place."""
    world.body_of(name).state["ledger"][locus] = amount


def _recorder(world):
    """Wrap world.free_action so each call is recorded with its result (the call still runs)."""
    calls = []
    original = world.free_action

    def record(actor, action, *args, **kwargs):
        calls.append((actor, action, args, dict(kwargs), None))
        return original(actor, action, *args, **kwargs)

    world.free_action = record
    return calls


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                       ticks_per_period="world")


def _llm(game, name, reply_text):
    script = Script(reply_text)
    game.set_backend(name, LLMBackend(game.characters[name], script, autopilot=False))
    return script


def _shown_token(game, name, raw):
    """Phase 054b: the token the LLM view shows for a world handle in its `can` list (a reply copies the token)."""
    context = game._context(name)
    shown = game.backends[name].handles.mask_context(context).agent_view["can"]
    return shown[[row["handle"] for row in context.agent_view["can"]].index(raw)]["handle"]


# ------------------------------------------------------------------ the parity table
def test_every_major_action_key_is_reachable_from_a_reply():
    for name in MAJOR:
        wire = reply_schema.to_wire({"major_action": {"action": name, "params": {}}}, PACK)
        response = ActorResponse.from_dict(wire)
        assert response.major_action is not None and response.major_action.action == name, name
        assert reply_schema.check({"major_action": {"action": name, "params": {}}}, PACK) == [], name


def test_every_free_action_key_has_a_route_and_is_reachable_from_a_reply():
    for name in FREE:
        assert name in free_replies.ROUTES, f"{name} has no route in bigville/free_replies.py"
        item = {"action": name, "target": "Bram Smith", "params": dict(FREE_PARAMS)}
        assert reply_schema.check({"free_actions": [item]}, PACK) == [], name
        response = ActorResponse.from_dict(reply_schema.to_wire({"free_actions": [item]}, PACK))
        assert [row["action"] for row in response.free_actions] == [name], name


def test_every_free_action_key_reaches_the_world_with_its_params(town):
    """The world is asked for each free action with the reply's params (a refusal by the world is not checked here:
    only the call is)."""
    world = town.world
    name, victim = _adult(world), _other(world, _adult(world))
    _felt(world, name)
    calls = _recorder(world)
    for action in FREE:
        target = "signal:1" if action == "glance" else victim
        free_replies.apply_one(town, name, {"action": action, "target": target, "params": dict(FREE_PARAMS)})
    routed = {call[1] for call in calls}
    assert routed == {"speak", "reply", "write_note", "give_note", "accept", "decline", "set_intensity", "stop",
                      "glance"}
    assert all(call[0] == name for call in calls)
    by_action = {call[1]: call for call in calls}
    assert by_action["give_note"][2] == (victim, "note:1")
    assert by_action["reply"][2] == (victim, "hello")
    assert by_action["accept"][3] == {"item": "flour", "giver": "Bram Smith"}   # the reply names the giver
    assert by_action["set_intensity"][3] == {"intensity": "hard"}
    assert by_action["glance"][3] == {"target": "signal:1"}


def test_the_speech_free_action_and_an_utterance_are_the_same_world_call(town):
    world = town.world
    name = _adult(world)
    calls = _recorder(world)
    free_replies.apply_one(town, name, {"action": "speak", "target": None, "params": {"text": "Good day."}})
    assert calls[-1][1] == "speak" and calls[-1][3]["content"] == "Good day."


# ------------------------------------------------------------------ the reply schema
def test_a_free_action_reply_is_checked_against_the_free_action_table():
    assert reply_schema.check({"free_actions": [{"action": "glance", "target": "signal:1"}]}, PACK) == []
    errors = reply_schema.check({"free_actions": [{"action": "glance"}]}, PACK)
    assert errors == ["free action glance needs a target"]
    assert reply_schema.check({"free_actions": [{"action": "accept", "params": {"item": "flour"}}]}, PACK) == []
    errors = reply_schema.check({"free_actions": [{"action": "write_note", "params": {"text": 3}}]}, PACK)
    assert errors == ["free_actions.params.text must be text"]
    errors = reply_schema.check({"free_actions": [{"action": "set_intensity", "params": {"intensity": "sideways"}}]},
                                PACK)
    assert errors and errors[0].startswith("free_actions.params.intensity")
    assert reply_schema.check({"free_actions": [{"action": "stop", "reason": "x"}]}, PACK)
    assert reply_schema.check({"free_actions": "stop"}, PACK) == ["free_actions must be a list"]


def test_a_free_action_intensity_word_is_folded_to_its_value():
    wire = reply_schema.to_wire({"free_actions": [{"action": "set_intensity", "params": {"intensity": "hard"}}]}, PACK)
    assert wire["free_actions"][0]["params"]["intensity"] == intensity_value("hard", PACK)


def test_an_unknown_free_action_name_passes_the_schema_for_the_world_to_refuse():
    assert reply_schema.check({"free_actions": [{"action": "fly", "params": {}}]}, PACK) == []


def test_the_packet_interface_names_the_free_actions_and_the_reply_field():
    system = packet_system(PACK)
    assert "Free actions (they use no major action):" in system
    for name in FREE:
        assert f"- {name}" in system, name
    interface = load_pack(PACK)["PROMPT_PACKET"]["interface"]
    assert any(line.startswith("free_actions is a list") for line in interface)
    assert "free_actions" in load_pack(PACK)["PROMPT_RESPONSE_FIELDS"]
    assert load_pack(PACK)["PROMPT_REPLY"]["free_action_keys"] == ["action", "target", "params"]


# ------------------------------------------------------------------ an LLM reply enacts free actions
def test_an_llm_glance_reply_is_enacted_and_shows_the_sound_and_place_in_last(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    turn = world._turn
    script = _llm(town, name, "")
    token = _shown_token(town, name, "signal:1")
    script.text = _reply(free_actions=[{"action": "glance", "target": token, "params": {}}])
    town.step()
    assert script.calls == 1
    outcome = free_replies.last_free(town, name)
    assert outcome["action"] == "glance" and outcome["applied"] is True, outcome
    assert outcome["place"] == "arm" and outcome["sound"]
    assert outcome["turn"] == world._turn
    view = town.agent_view(name, "agent")
    assert view["last"]["action"] == "glance" and view["last"]["outcome"]
    assert view["last"]["place"] == "arm" and view["last"]["sound"] == outcome["sound"]


def test_an_llm_aimed_strike_passes_its_region_to_the_world(town):
    world = town.world
    name = _adult(world)
    victim = _other(world, name)
    reply = _reply(major_action={"action": "strike", "target": victim, "params": {"region": "arm"}})
    _llm(town, name, reply)
    town.step()
    proposal = town.last_responses[name].major_action
    assert proposal.action == "strike" and proposal.params.get("region") == "arm"
    assert world.last_outcome(name)["reason"] != "unknown_region"


def test_an_llm_aimed_strike_to_an_unknown_region_is_refused_as_unknown_region(town):
    world = town.world
    name = _adult(world)
    victim = _other(world, name)
    _llm(town, name, _reply(major_action={"action": "strike", "target": victim, "params": {"region": "knee"}}))
    town.step()
    assert world.last_outcome(name)["reason"] == "unknown_region"
    view = town.agent_view(name, "agent")
    assert view["last"]["reason"]


def test_an_llm_set_intensity_reply_reaches_the_world_with_the_word_as_its_value(town):
    world = town.world
    name = _adult(world)
    calls = _recorder(world)
    _llm(town, name, _reply(free_actions=[{"action": "set_intensity", "params": {"intensity": "hard"}}]))
    town.step()
    routed = [call for call in calls if call[1] == "set_intensity"]
    assert routed and routed[0][3]["intensity"] == intensity_value("hard", PACK)
    outcome = free_replies.last_free(town, name)
    # The resident has no timed job, so the world says no: a refusal with a recorded reason.
    assert outcome["applied"] is False and outcome["reason"] == "not_possible"
    assert town.agent_view(name, "agent")["last"]["outcome"]


def test_an_unknown_free_action_is_refused_with_a_recorded_reason(town):
    world = town.world
    name = _adult(world)
    calls = _recorder(world)
    _llm(town, name, _reply(free_actions=[{"action": "fly", "params": {}}]))
    town.step()
    assert not [call for call in calls if call[1] == "fly"]
    outcome = free_replies.last_free(town, name)
    assert {key: outcome[key] for key in ("action", "applied", "reason")} == {"action": "fly", "applied": False,
                                                                           "reason": "unsupported"}
    last = town.agent_view(name, "agent")["last"]
    assert last["action"] == "fly" and last["outcome"] and last["reason"]


def test_a_free_action_takes_no_slot_and_no_tick(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    turn, major = world._turn, world.last_outcome(name)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:1", "params": {}}])
    assert world._turn == turn
    assert world.last_outcome(name) == major
    assert free_replies.last_free(town, name)["applied"] is True


def test_a_glance_after_an_attend_on_the_same_turn_is_the_last_and_the_attend_is_not(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    assert world.major_action(name, "press", target="arm") is True
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:1", "params": {}}])
    assert town.agent_view(name, "agent")["last"]["action"] == "glance"


def test_a_newer_major_outcome_replaces_an_older_free_outcome_in_last(town):
    world = town.world
    name = _adult(world)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:9", "params": {}}])
    assert free_replies.last_free(town, name)["reason"] == "unknown_target"
    world._turn += 1
    assert world.major_action(name, "press", target="arm") is True
    assert town.agent_view(name, "agent")["last"]["action"] == "press"


def test_a_glance_on_an_unknown_feeling_or_asleep_is_refused_with_its_reason(town):
    world = town.world
    name = _adult(world)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:9", "params": {}}])
    assert free_replies.last_free(town, name)["reason"] == "unknown_target"
    _felt(world, name)
    world.eng.set_attr(world._actors[name], "asleep", 1.0)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:1", "params": {}}])
    assert free_replies.last_free(town, name)["reason"] == "asleep"


def test_the_leak_rule_holds_for_a_free_outcome_in_last(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:1", "params": {}}])
    view = town.agent_view(name, "agent")
    assert set(view["last"]) <= {"action", "outcome", "reason", "sound", "place"}
    text = json.dumps({"last": view["last"]}).lower()
    assert not [word for word in FORBIDDEN if word in text]
    assert felt_body_problems(world.body_of(name).afferents(), PACK) == []


def test_the_glance_row_of_each_felt_signal_is_in_the_packet_public_can(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    context = town._context(name)
    context.agent_view = town.agent_view(name, mode="agent")
    record = PromptBuilder(pack=PACK).build(context).as_dict()
    rows = record["context"]["public"]["can"]
    assert {"handle": "signal:1", "action": "attend", "what": "arm"} in rows
    assert "glance" in record["system"]


# ------------------------------------------------------------------ the simple backends never choose them
def test_simple_backends_never_offer_or_send_a_free_action(town):
    world = town.world
    sample = sorted(town.backends)[::25]
    offered = set()
    for name in sample:
        offered |= {row.get("action") for row in world.actor_affordances(name)}
    assert not offered & set(FREE)
    for _ in range(3):
        town.step()
        for name in sample:
            response = town.last_responses.get(name)
            assert response is None or not response.free_actions, name
