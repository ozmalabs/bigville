"""Phase 071f: one way to wait. The reply contract has `major_action: {"action": "wait"}` and no `waiting` field.

The packet names only `wait`; a wait reply makes one provider call and is a no-op at the game (no outcome, no refusal);
a stray top-level `waiting` key is ignored, noted, and the major action stands; the human backend's internal
`ActorResponse.waiting` still works.
"""
from __future__ import annotations

import copy
import json

from bigville.backends.human import HumanBackend
from bigville.backends.llm import LLMBackend
from bigville.backends.llm import validate_response
from bigville.backends.prompt_packet import PACKET_SCHEMA
from bigville.backends.prompts import PromptBuilder
from bigville.backends.protocol import ActorContext, ActorResponse, ProposedAction
from bigville.backends.reply_schema import STRAY_WAITING, to_wire
from bigville.character import CharacterDefinition
from bigville.free_replies import last_free
from bigville.game import BigvilleGame
from domains.pack import load_pack
from worlds.bigville_world import BigvilleWorld


PACKS = ("bigville", "test_hamlet")


class Fake:
    """Returns the scripted replies in order, then repeats the last one. Keeps a copy of every payload."""

    def __init__(self, *script):
        self.script = list(script)
        self.prompts: list[dict] = []

    def complete(self, prompt):
        self.prompts.append(copy.deepcopy(prompt))
        index = min(len(self.prompts) - 1, len(self.script) - 1)
        return self.script[index]


def _reply(major=None, **extra):
    body = {"major_action": major, "utterances": [], "memory_updates": [], "continuation": None}
    body.update(extra)
    return json.dumps(body)


CARRY = _reply()
WAIT = _reply({"action": "wait", "params": {}})


def _game(provider):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world)
    game.set_backend("Ben", LLMBackend(game.characters["Ben"], provider, autopilot=False))
    return game


def _decide(game):
    response = game.backends["Ben"].decide(game._context("Ben"))
    game._apply_response("Ben", response)
    return response


# -- the packet names only wait ----------------------------------------------------------------

def test_the_response_fields_have_no_waiting_in_either_pack():
    for pack in PACKS:
        fields = load_pack(pack)["PROMPT_RESPONSE_FIELDS"]
        assert "waiting" not in fields and "major_action" in fields, pack


def test_the_packet_tells_the_model_to_wait_by_major_action_and_never_by_a_flag():
    for pack in PACKS:
        table = load_pack(pack)["PROMPT_PACKET"]
        assert "set action to wait" in " ".join(table["interface"]), pack
        assert "whose action is wait" in table["consult_rules"], pack
        text = json.dumps(table, ensure_ascii=False)
        assert "waiting" not in text, pack


def test_the_packet_the_model_is_sent_names_wait_and_no_waiting_flag():
    game = _game(Fake(CARRY))
    record = PromptBuilder().build(game._context("Ben"), "check_in")
    assert record.schema == PACKET_SCHEMA == "bigville/prompt/8"
    assert "To do nothing on purpose, set action to wait." in record.system
    # "Waiting, or saying nothing, is a valid choice." is a rule about acting, not a reply field. The field form is gone.
    for flag in ('"waiting"', "waiting:", "waiting true", "set waiting", "waiting: true"):
        assert flag not in record.system.lower(), flag


# -- one way to wait: the wait reply ----------------------------------------------------------------

def test_a_wait_reply_waits_in_one_call_and_wait_is_its_major_action():
    provider = Fake(WAIT, CARRY)
    game = _game(provider)
    response = _decide(game)
    backend = game.backends["Ben"]
    assert len(provider.prompts) == 1
    assert backend.counts["repairs_used"] == 0 and backend.counts["waits"] == 1
    assert response.major_action.action == "wait" and response.waiting is False
    assert backend.last_backend_state["turn_kind"] == "wait"
    assert backend.last_backend_state.get("reply_notes") is None


def test_a_wait_is_recorded_as_the_turns_action_done_with_no_refusal():
    game = _game(Fake(WAIT))
    _decide(game)
    outcome = game.world.last_outcome("Ben")
    assert outcome["action"] == "wait" and outcome["applied"] is True and outcome["reason"] == ""
    assert game.world.refusals("Ben") == []
    assert last_free(game, "Ben") is None


def test_a_wait_proposed_by_another_backend_is_recorded_the_same_way():
    game = _game(Fake(CARRY))
    applied = game._apply_response("Ben", ActorResponse(major_action=ProposedAction("wait", {}, "")))
    assert applied is True
    assert game.world.last_outcome("Ben")["action"] == "wait"
    assert game.world.refusals("Ben") == []


def test_a_null_major_action_still_carries_on():
    provider = Fake(CARRY)
    game = _game(provider)
    _decide(game)
    backend = game.backends["Ben"]
    assert backend.last_backend_state["turn_kind"] == "carry_on"
    assert backend.counts["waits"] == 0 and backend.counts["carry_ons"] == 1


# -- a stray waiting key ------------------------------------------------------------------------

def test_a_stray_waiting_key_is_accepted_noted_and_the_major_action_stands():
    provider = Fake(_reply({"action": "rest", "params": {}}, waiting=True), CARRY)
    game = _game(provider)
    response = _decide(game)
    backend = game.backends["Ben"]
    assert len(provider.prompts) == 1
    assert response.major_action.action == "rest"
    assert backend.last_backend_state["turn_kind"] == "act"
    assert backend.last_backend_state["reply_notes"] == {"waiting_ignored": 1}


def test_the_wire_form_drops_the_stray_key_so_it_cannot_set_the_internal_flag():
    wire = to_wire({"major_action": None, STRAY_WAITING: True}, "bigville")
    assert STRAY_WAITING not in wire
    assert wire["reply_notes"] == {"waiting_ignored": 1}
    assert ActorResponse.from_dict(wire).waiting is False


def test_a_stray_key_is_not_a_shape_error_whatever_its_value():
    fields = ("major_action", "continuation", "utterances", "memory_updates")
    for value in (True, False, "no", 3):
        assert validate_response({STRAY_WAITING: value}, fields) == []


def test_a_stray_key_does_not_hide_a_real_shape_error():
    fields = ("major_action", "continuation", "utterances", "memory_updates")
    errors = validate_response({STRAY_WAITING: True, "bogus": 1}, fields)
    assert errors == ["unknown field: bogus"]


# -- the human backend's internal waiting is unchanged ----------------------------------------

def test_the_human_backend_still_returns_waiting_until_it_is_given_an_answer():
    backend = HumanBackend(_character())
    assert backend.decide(_context()).waiting is True
    assert backend.react(_context()).waiting is True
    backend.submit(ActorResponse(major_action=ProposedAction("rest", {}, "")))
    assert backend.decide(_context()).major_action.action == "rest"


def _character():
    return CharacterDefinition(character_id="Ada", name="Ada")


def _context():
    return ActorContext(_character(), 0, {}, [])
