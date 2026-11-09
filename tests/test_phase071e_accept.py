"""Phase 071e: a reply is accepted unless it is malformed (shape and types only).

Each of the five cases from the brief is checked twice. The accepted variant makes one provider call and its outcome
is recorded (a free outcome in the resident's `last`, a backend note, or the reply's effect). Each malformed variant
still goes to the repair call.
"""
from __future__ import annotations

import copy
import json

from bigville.backends import reply_schema
from bigville.backends.llm import LLMBackend
from bigville.free_replies import last_free
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld
from domains.pack import load_pack


PACKET = load_pack("bigville")["PROMPT_PACKET"]
CAP = int(PACKET["lessons_max"])


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


def _game(provider):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world)
    game.set_backend("Ben", LLMBackend(game.characters["Ben"], provider, autopilot=False))
    return game


def _decide(game, provider):
    response = game.backends["Ben"].decide(game._context("Ben"))
    game._apply_response("Ben", response)
    return response


def _accepted(reply):
    """One provider call, no repair, and the reply was accepted."""
    provider = Fake(reply, CARRY)
    game = _game(provider)
    response = _decide(game, provider)
    backend = game.backends["Ben"]
    assert len(provider.prompts) == 1
    assert backend.counts["repairs_used"] == 0 and backend.counts["successes"] == 1
    assert backend.last_backend_state["outcome"] == "ok"
    return game, response, backend


def _repaired_once(reply):
    """A malformed reply: the repair call runs (two calls in all)."""
    provider = Fake(reply, reply)
    game = _game(provider)
    _decide(game, provider)
    assert len(provider.prompts) == 2
    assert "repair" in provider.prompts[1]
    assert game.backends["Ben"].counts["repairs_used"] == 1
    return provider


# -- 1. waiting: true ----------------------------------------------------------------------------
# Phase 071f: waiting is no longer a field. A stray top-level key is ignored and noted; major_action decides.

def test_a_stray_waiting_key_is_ignored_and_noted_and_the_turn_carries_on():
    game, response, backend = _accepted(_reply(None, waiting=True))
    assert response.major_action is None
    assert backend.last_backend_state["turn_kind"] == "carry_on"
    assert backend.last_backend_state["reply_notes"] == {"waiting_ignored": 1}
    assert backend.counts["waits"] == 0


def test_a_stray_waiting_key_with_a_major_action_leaves_the_major_action_standing():
    game, response, backend = _accepted(_reply({"action": "rest", "params": {}}, waiting=True))
    assert response.major_action.action == "rest"
    assert backend.last_backend_state["turn_kind"] == "act"
    assert backend.last_backend_state["reply_notes"] == {"waiting_ignored": 1}


def test_a_stray_waiting_key_is_accepted_whatever_its_value():
    _accepted(_reply(None, waiting="yes"))


# -- 2. an utterance with blank text -------------------------------------------------------------

def test_blank_speech_is_accepted_nothing_is_said_and_the_refusal_is_recorded():
    game, _, _ = _accepted(_reply(None, utterances=[{"to": "Ada", "text": "   "}]))
    assert len(game.world._utterances) == 0
    outcome = last_free(game, "Ben")
    assert outcome["action"] == "speak" and outcome["applied"] is False
    assert outcome["reason"] == "nothing_said"


def test_speech_that_is_not_text_is_still_malformed():
    _repaired_once(_reply(None, utterances=[{"to": "Ada", "text": 5}]))


def test_speech_with_no_text_field_is_still_malformed():
    _repaired_once(_reply(None, utterances=[{"to": "Ada"}]))


# -- 3. a memory update with a kind outside the pack's list, or empty text -----------------------

def test_an_unknown_memory_kind_is_kept_as_a_note_with_the_kind_it_named():
    game, _, _ = _accepted(_reply(None, memory_updates=[{"kind": "gossip", "text": "Ada is kind"}]))
    notes = [m for m in game.characters["Ben"].memories if m.kind == "note"]
    assert [m.content for m in notes] == [{"text": "Ada is kind", "named_kind": "gossip"}]


def test_a_memory_kind_that_is_not_text_is_still_malformed():
    _repaired_once(_reply(None, memory_updates=[{"kind": 5, "text": "x"}]))


def test_empty_memory_text_is_accepted_dropped_and_recorded():
    game, _, backend = _accepted(_reply(None, memory_updates=[{"kind": "note", "text": "  "}]))
    assert [m for m in game.characters["Ben"].memories if m.kind == "note"] == []
    assert backend.last_backend_state["reply_notes"] == {"memory_dropped": 1}


def test_memory_text_that_is_not_text_is_still_malformed():
    _repaired_once(_reply(None, memory_updates=[{"kind": "note", "text": 5}]))


# -- 4. a continuation whose task action is empty -----------------------------------------------

def test_a_continuation_with_an_empty_task_action_starts_nothing_and_is_refused():
    reply = _reply({"action": "rest", "params": {}},
                   continuation={"task": {"action": "", "params": {}}, "interrupt_on": []})
    game, response, _ = _accepted(reply)
    assert response.continuation is None
    outcome = last_free(game, "Ben")
    assert outcome["action"] == "continuation" and outcome["reason"] == "no_task"


def test_a_continuation_task_with_no_action_text_is_still_malformed():
    _repaired_once(_reply(None, continuation={"task": {"params": {}}}))


def test_a_continuation_task_action_that_is_not_text_is_still_malformed():
    _repaired_once(_reply(None, continuation={"task": {"action": 5}}))


# -- 5. more lesson updates than lessons_max -----------------------------------------------------

def test_more_lessons_than_the_cap_are_accepted_and_the_newest_are_kept():
    texts = [f"lesson {index}" for index in range(CAP + 3)]
    reply = _reply(None, memory_updates=[{"kind": "lesson", "text": text} for text in texts])
    game, _, backend = _accepted(reply)
    kept = [m.content["text"] for m in game.characters["Ben"].memories if m.kind == "lesson"]
    assert kept == texts[-CAP:]
    assert backend.last_backend_state["reply_notes"] == {"lessons_dropped": 3}


def test_a_lesson_that_is_not_text_is_still_malformed_even_over_the_cap():
    lessons = [{"kind": "lesson", "text": f"lesson {index}"} for index in range(CAP)]
    lessons.append({"kind": "lesson", "text": None})
    _repaired_once(_reply(None, memory_updates=lessons))


# -- the reply check itself, in words ------------------------------------------------------------

def test_the_schema_check_accepts_each_case_and_still_names_the_malformed_ones():
    assert reply_schema.check(json.loads(_reply(None, utterances=[{"to": "Ada", "text": " "}])), "bigville") == []
    assert reply_schema.check(json.loads(_reply(None, memory_updates=[{"kind": "x", "text": ""}])), "bigville") == []
    assert reply_schema.check(json.loads(_reply(None, continuation={"task": {"action": ""}})), "bigville") == []
    too_many = [{"kind": "lesson", "text": str(index)} for index in range(CAP + 1)]
    assert reply_schema.check(json.loads(_reply(None, memory_updates=too_many)), "bigville") == []
    assert reply_schema.check(json.loads(_reply(None, memory_updates=[{"kind": 5, "text": "x"}])), "bigville")
