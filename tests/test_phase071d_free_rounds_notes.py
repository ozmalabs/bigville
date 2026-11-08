"""Phase 071d, decisions 2 to 5.

2. A reply with free actions and no major action is asked again in the same turn, after its free actions are applied,
   up to PROMPT_REPLY.free_rounds_max times. The server's /api/free route applies free actions with no step.
3. An LLM resident gives a note it holds, accepts a request and declines another, by the handles its view lists.
4. Free outcomes survive a game checkpoint: the restored `last` equals the saved one.
5. world.free_action takes keyword arguments (reply, give_note, accept, decline), and Body.probe reads a felt signal.

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
from bigville.game_persistence import load_game_checkpoint, save_game_checkpoint  # noqa: E402
from domains.pack import load_pack                                 # noqa: E402

PACK = "bigville"
SEED = 305000
LIMIT = int(load_pack(PACK)["PROMPT_REPLY"]["free_rounds_max"])


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


def _other(world, name):
    return next(other for other in world._actors if other != name)


def _llm(game, name, *texts):
    """Install an LLM backend for ``name`` with a fake provider (its texts may be set later on the returned Seq)."""
    script = Seq(*texts)
    game.set_backend(name, LLMBackend(game.characters[name], script, autopilot=False))
    return script


def _felt(world, name, locus="arm", amount=0.4):
    world.body_of(name).state["ledger"][locus] = amount


def _walk(view, path):
    for key in path:
        view = view[key]
    return view


def _shown(game, name, path, raw):
    """The handle the LLM sees and copies for a world handle (Phase 054b: opaque tokens). ``path`` is the agent view's key
    path to the list that holds it. Without a handle map (a game before Phase 054b) the world handle is shown as it is."""
    handles = getattr(game.backends[name], "handles", None)
    if handles is None:
        return raw
    context = game._context(name)
    rows = [row["handle"] for row in _walk(context.agent_view, path)]
    return _walk(handles.mask_context(context).agent_view, path)[rows.index(raw)]["handle"]


def _request(world, name, sender, key, task):
    """A request addressed to `name` from `sender`, registered the way the world's request tests register one."""
    req = world.eng.add_node("Request", {"name": key, "kind": "task", "task": task, "good": "", "requirement": 0.0,
                                         "incentive": 0.0, "status": 0.0, "created_turn": 1.0,
                                         "response_turn": -1.0, "source_utterance": 0})
    world.eng.add_edge_unchecked(world._actors[sender], "requests", req)
    world.eng.add_edge_unchecked(req, "from", world._actors[sender])
    world.eng.add_edge_unchecked(req, "to", world._actors[name])
    world.eng.add_edge_unchecked(world._actors[name], "received_request", req)
    world._requests[key] = req
    return req


# ------------------------------------------------------------------ decision 2: free rounds in one turn
def test_an_llm_glances_then_acts_in_a_second_round_and_both_apply(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    script = _llm(town, name)
    token = _shown(town, name, ("can",), "signal:1")
    script.texts = [_reply(None, [{"action": "glance", "target": token, "params": {}}]), _reply({"action": "rest"})]
    turn = world._turn
    town.step()
    assert script.calls == 2
    assert world._turn == turn + 1
    assert free_replies.last_free(town, name)["action"] == "glance"
    assert free_replies.last_free(town, name)["applied"] is True
    assert town.last_responses[name].major_action.action == "rest"


def test_the_round_cap_holds_when_every_reply_is_free_only(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    script = _llm(town, name)
    token = _shown(town, name, ("can",), "signal:1")
    script.texts = [_reply(None, [{"action": "glance", "target": token, "params": {}}])]
    turn = world._turn
    town.step()
    assert script.calls == 1 + LIMIT
    assert world._turn == turn + 1
    assert town.last_responses[name].major_action is None


def test_a_simple_resident_is_never_asked_again_and_has_no_free_actions(town):
    world = town.world
    turn = world._turn
    for _ in range(3):
        town.step()
    assert world._turn == turn + 3
    assert all(not response.free_actions for response in town.last_responses.values())


def test_the_server_free_route_applies_free_actions_and_refuses_a_major_action(town):
    from bigville.server import GameService
    service = GameService(scenario="town100", seed=SEED, player=_adult(town.world), mode="agent")
    turn = service.game.world._turn
    result = service.free({"free_actions": [{"action": "glance", "target": "signal:1"}]})
    assert result["status"] == "free" and "view" in result
    assert service.game.world._turn == turn
    with pytest.raises(ValueError):
        service.free({"free_actions": [], "major_action": {"action": "rest"}})
    with pytest.raises(ValueError):
        service.free({"free_actions": "glance"})


# ------------------------------------------------------------------ decision 3: notes and requests by handle
def test_the_view_lists_the_handles_of_held_notes_and_open_requests(town):
    world = town.world
    name = _adult(world)
    other = _other(world, name)
    world.write_note(name, "Bring the ledger on Monday", note_id="note:9")
    world.write_note(other, "Not mine", note_id="note:10")
    _request(world, name, other, "request:1", "carry the flour")
    _request(world, name, other, "request:2", "mind the goat")
    self_view = town.agent_view(name, "agent")["self"]
    assert {"handle": "note:9", "what": "Bring the ledger on Monday"} in self_view["giveable_notes"]
    assert all(row["handle"] != "note:10" for row in self_view["giveable_notes"])
    assert {row["handle"] for row in self_view["requests"]} == {"request:1", "request:2"}
    assert all(row["who"] == other for row in self_view["requests"])


def test_an_llm_gives_a_note_it_holds_and_accepts_and_declines_by_their_handles(town):
    world = town.world
    name = _adult(world)
    other = _other(world, name)
    world.write_note(name, "Bring the ledger on Monday", note_id="note:9")
    req_ok = _request(world, name, other, "request:1", "carry the flour")
    req_no = _request(world, name, other, "request:2", "mind the goat")
    script = _llm(town, name)
    free = [{"action": "give_note", "target": other,
             "params": {"note": _shown(town, name, ("self", "giveable_notes"), "note:9")}},
            {"action": "accept", "target": _shown(town, name, ("self", "requests"), "request:1"), "params": {}},
            {"action": "decline", "target": _shown(town, name, ("self", "requests"), "request:2"), "params": {}}]
    script.texts = [_reply({"action": "rest"}, free)]
    town.step()
    assert world.eng.has_edge(world._actors[other], "holds", world._notes["note:9"])
    assert not world.eng.has_edge(world._actors[name], "holds", world._notes["note:9"])
    assert world.request_status(req_ok) == 1
    assert world.request_status(req_no) == -1


def test_a_note_the_resident_does_not_hold_is_refused_as_not_held(town):
    """The model cannot name a note it does not hold (the handle map refuses an unseen handle), so the refusal is tested
    on the free action itself."""
    world = town.world
    name = _adult(world)
    other = _other(world, name)
    world.write_note(other, "Theirs", note_id="note:11")
    free_replies.apply_all(town, name, [{"action": "give_note", "target": other, "params": {"note": "note:11"}}])
    outcome = free_replies.last_free(town, name)
    assert outcome["applied"] is False and outcome["reason"] == "not_held"
    assert world.eng.has_edge(world._actors[other], "holds", world._notes["note:11"])


# ------------------------------------------------------------------ decision 4: the checkpoint keeps `last`
def test_free_outcomes_survive_a_checkpoint(town, tmp_path):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    free_replies.apply_all(town, name, [{"action": "glance", "target": "signal:1", "params": {}}])
    saved_last = town.agent_view(name, "agent")["last"]
    assert saved_last["action"] == "glance"
    save_game_checkpoint(town, tmp_path / "game")
    restored = load_game_checkpoint(tmp_path / "game", llm_log=False)
    assert restored.free_outcomes == town.free_outcomes
    assert restored.agent_view(name, "agent")["last"] == saved_last


# ------------------------------------------------------------------ decision 5: keyword calls and Body.probe
def test_free_action_takes_keyword_arguments(town):
    world = town.world
    name = _adult(world)
    other = _other(world, name)
    world.write_note(name, "Bring the ledger", note_id="note:9")
    _request(world, name, other, "request:1", "carry the flour")
    _request(world, name, other, "request:2", "mind the goat")
    world.free_action(name, "reply", target=other, content="hello")
    world.free_action(name, "give_note", recipient=other, note="note:9")
    assert world.eng.has_edge(world._actors[other], "holds", world._notes["note:9"])
    world.free_action(name, "accept", request="request:1")
    world.free_action(name, "decline", request="request:2")
    assert world.request_status("request:1") == 1 and world.request_status("request:2") == -1


def test_body_probe_gives_the_sound_and_place_of_a_felt_signal(town):
    world = town.world
    name = _adult(world)
    _felt(world, name)
    body = world.body_of(name)
    probe = body.probe("signal:1")
    assert probe["place"] == "arm" and probe["sound"]
    assert body.probe("signal:99") is None
    assert body.probe("nothing") is None
