"""Phase 065c: an LLM resident's prompt gets the perception effects (the perceiver, the impairment, the written marks
and the heard sentences) through the lazy agent view.

The lazy view is the view of a backend with `wants_agent_view` (the LLM). With PERCEPTION off it is built exactly as
before. With PERCEPTION on, its people, things, heard sentences and written marks are the full view's (the same helpers),
and the referee block of the lazy view carries the perceiver's rows. These tests hold:

* switch off: no perception key in the lazy view and no perceiver call;
* switch on: the lazy people, heard sentences and things are the full view's, and the place handles stay;
* switch on: the written marks reach the lazy view;
* switch on: the lazy path still builds no legal menu;
* leak: a drunk LLM resident is given a wrong thing; the prompt the provider receives (and the LLM log) carries the wrong
  percept and not the truth, and the referee block carries both.

The provider is the in-process FakeProvider (tests/llm_stub.py). No network is used.
"""
from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                              # noqa: E402
from bigville.backends import LLMBackend                          # noqa: E402
from bigville.llm_log import LLMLog, read_log                     # noqa: E402
from domains import agent_view, perceiver as P                    # noqa: E402
from domains import reading                                       # noqa: E402
from domains.agent_view import build_lazy_agent_view              # noqa: E402
from domains.pack import load_pack                                # noqa: E402
from tests.llm_stub import FakeProvider                           # noqa: E402
from worlds import daynight as dn                                 # noqa: E402
from worlds.bigville_world import BigvilleWorld                   # noqa: E402

PACK = load_pack("bigville")

# Two residents in one room. Ben is the simple resident; Ada is the LLM whose prompt is under test.
SCENARIO = {
    "id": "p065c_llm_perception",
    "name": "Phase 065c LLM perception room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "llm", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "apple", "name": "apple", "kind": "apple", "location": "table"},
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": True},
    ],
}

# Two objects of different kinds, with ids that do not contain the kind words (the handle is the world's name for the
# thing; the leak test checks the kind words).
KNIFE_SPADE = [{"id": "obj_a", "kind": "knife", "location": "world"},
               {"id": "obj_b", "kind": "spade", "location": "world"}]


def _reply(action=None, **params):
    major = None if action is None else {"action": action, "params": params}
    return json.dumps({"major_action": major, "utterances": [], "memory_updates": [],
                       "continuation": None})


def _game(reply=None):
    """The small room with Ada on the LLM backend and the lazy affordance mode (the path the LLM uses in a game)."""
    provider = FakeProvider(reply if reply is not None else _reply("rest"))
    factory = lambda world, character: LLMBackend(character, provider, autopilot=False)
    game = create_game(scenario=SCENARIO, seed=305165, player=None, default_backend="simple",
                       backend_factories={"llm": factory}, autonomous=True, llm_log=False,
                       affordance_mode="lazy")
    game._test_provider = provider
    return game


@pytest.fixture
def switches():
    """PERCEPTION and IMPAIRMENT forced on for one test, then restored (the pack tables are cached per process)."""
    saved = {name: dict(PACK[name]) for name in ("PERCEPTION", "IMPAIRMENT")}
    PACK["PERCEPTION"]["enabled"] = True
    PACK["IMPAIRMENT"]["enabled"] = True
    try:
        yield
    finally:
        for name, values in saved.items():
            PACK[name].clear()
            PACK[name].update(values)


@pytest.fixture
def perception_off():
    saved = dict(PACK["PERCEPTION"])
    PACK["PERCEPTION"]["enabled"] = False
    try:
        yield
    finally:
        PACK["PERCEPTION"].clear()
        PACK["PERCEPTION"].update(saved)


def _spy_menu_calls():
    calls = []
    real_affordances = BigvilleWorld.actor_affordances
    real_options = BigvilleWorld._actor_options

    def actor_affordances(self, actor):
        calls.append(("actor_affordances", actor))
        return real_affordances(self, actor)

    def actor_options(self, actor):
        calls.append(("_actor_options", actor))
        return real_options(self, actor)

    return calls, mock.patch.object(BigvilleWorld, "actor_affordances", actor_affordances), \
        mock.patch.object(BigvilleWorld, "_actor_options", actor_options)


def _drunk(game, actor, level=0.5):
    """Sets the intoxication of the actor's body and gives the view daylight, so a thing in sight is seen."""
    world = game.world
    body = world._bodies[actor]
    old = world.eng.node(body)["attrs"].get("intoxication", 0.0)
    world.eng.set_attr(body, "intoxication", level)
    return old


# ------------------------------------------------------------------ switch off
def test_switch_off_the_lazy_view_has_no_perception_parts(perception_off):
    game = _game()
    view = build_lazy_agent_view(game, "Ada", mode="referee")
    assert set(view["around"]) == {"people", "heard", "seen", "things"}
    assert "perception" not in view["referee"]
    assert any(thing.get("handle") == "apple" for thing in view["around"]["things"]), \
        "with the switch off the lazy things are the observation's, as before"


# ------------------------------------------------------------------ switch on: the same parts as the full view
def test_switch_on_the_lazy_people_heard_and_things_are_the_full_views_percepts(switches):
    game = _game()
    lazy = build_lazy_agent_view(game, "Ada")
    full = game.agent_view("Ada")
    assert lazy["around"]["people"] == full["around"]["people"][:agent_view.LAZY_PEOPLE_CAP]
    assert lazy["around"]["heard"] == full["around"]["heard"][-10:]
    full_things = full["around"]["things"]
    assert lazy["around"]["things"][:len(full_things)] == full_things[:agent_view.LAZY_THINGS_CAP]


def test_switch_on_the_lazy_things_keep_their_place_handles_after_the_perceived_things(switches):
    game = _game()
    things = build_lazy_agent_view(game, "Ada")["around"]["things"]
    handles = [thing.get("handle", "") for thing in things]
    places = [i for i, handle in enumerate(handles) if handle.startswith("cell:")]
    perceived = [i for i, handle in enumerate(handles) if handle and not handle.startswith("cell:")]
    assert places, "the lazy view lost its place handles, which a move needs"
    assert not perceived or max(perceived) < min(places)


def test_switch_on_the_written_marks_reach_the_lazy_view(switches, monkeypatch):
    rows = [{"percept": "a loaf for two coins"}]
    monkeypatch.setattr(reading, "writing_rows", lambda game, actor, rec, pack, log: list(rows))
    game = _game()
    lazy = build_lazy_agent_view(game, "Ada")
    assert lazy["around"]["writing"] == rows
    assert lazy["around"]["writing"] == game.agent_view("Ada")["around"]["writing"]


def test_switch_on_the_lazy_path_still_builds_no_legal_menu(switches):
    game = _game()
    calls, patch_affordances, patch_options = _spy_menu_calls()
    with patch_affordances, patch_options:
        context = game._context("Ada")
        game.backends["Ada"].prompt_builder.build(context)
    assert calls == []
    assert context.agent_view is not None and context.affordances == []


def test_switch_on_the_referee_block_of_the_lazy_view_carries_the_perception_rows(switches):
    game = _game()
    view = build_lazy_agent_view(game, "Ada", mode="referee")
    perception = view["referee"]["perception"]
    assert perception["faculties"] == {"senses": "enforced", "skill": "enforced", "impairment": "enforced",
                                       "literacy": "enforced", "numeracy": "enforced"}
    assert "subjects" in perception and "perceiver" in perception
    assert "referee" not in build_lazy_agent_view(game, "Ada")


# ------------------------------------------------------------------ the leak test
def test_the_truth_never_enters_the_prompt_and_the_referee_and_the_log_carry_both(switches, monkeypatch, tmp_path):
    """A drunk LLM resident, every switch on. The world shows it a knife for a spade or the reverse (a wrong thing).
    The prompt the provider receives and the LLM log hold the wrong words, not the true ones. The referee block holds both."""
    game = _game(_reply("rest"))
    world = game.world
    monkeypatch.setattr(world, "physical_object_observations", lambda actor: KNIFE_SPADE)
    monkeypatch.setattr(world, "_physical_location_cell", lambda *a, **k: None)
    monkeypatch.setattr(dn, "view_light", lambda w, a: "day")
    old_level = _drunk(game, "Ada", 0.5)
    old_turn = world._turn
    backend = game.backends["Ada"]
    log = LLMLog(tmp_path / "llm.jsonl", run_id="p065c")
    backend.log = log
    try:
        wrong = None
        for turn in range(200):
            world._turn = turn
            referee = build_lazy_agent_view(game, "Ada", mode="referee")
            rows = [row for row in referee["referee"]["perception"]["subjects"]
                    if row["kind"] == "thing" and row.get("distorted") and row["percept"] != row["truth"]
                    and row["tier"] >= 1]
            if rows:
                wrong = rows[0]
                break
        assert wrong is not None, "a drunk resident should be shown a wrong thing in 200 turns"
        truth, percept = wrong["truth"], wrong["percept"]
        assert truth in {"knife", "spade"}

        # The turn of the wrong percept stays set for the rest of the test: the view and the prompt are that turn's.
        context = game._context("Ada")
        response = backend.decide(context)
        assert response is not None
        _check_leak(game, backend, wrong, truth, percept, tmp_path)
    finally:
        world._turn = old_turn
        world.eng.set_attr(world._bodies["Ada"], "intoxication", old_level)


def _check_leak(game, backend, wrong, truth, percept, tmp_path):
    sent = game._test_provider.calls[-1]["payload"]
    prompt = json.dumps(sent["messages"], ensure_ascii=False)
    assert percept in prompt
    assert truth not in prompt, "the true kind of the thing reached the prompt"
    shown = [thing for thing in agent_view.build_lazy_agent_view(game, "Ada")["around"]["things"]
             if thing.get("handle") == wrong["subject"]]
    assert shown and shown[0]["what"] == percept

    # The agent view never names the referee, the distortion or the true kind.
    agent = repr(build_lazy_agent_view(game, "Ada"))
    assert "referee" not in agent and "distorted" not in agent and truth not in agent

    # The LLM log records the prompt as it was sent: the same messages, the wrong percept and no truth.
    records = [record for record in read_log(tmp_path / "llm.jsonl") if record.get("kind") == "call"]
    assert records, "the LLM log has no call record"
    logged = json.dumps(records[-1]["messages"], ensure_ascii=False)
    assert records[-1]["messages"] == sent["messages"]
    assert percept in logged and truth not in logged

    # The referee block carries both the truth and the percept of the wrong row.
    referee_rows = [row for row in build_lazy_agent_view(game, "Ada", mode="referee")["referee"]["perception"]
                    ["subjects"] if row["subject"] == wrong["subject"]]
    assert any(row["truth"] == truth and row["percept"] == percept for row in referee_rows)
