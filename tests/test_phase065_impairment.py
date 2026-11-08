"""Phase 065: impairment. An impaired resident is given a confidently wrong percept; the truth goes only to the
referee block. Each test names one acceptance item of the brief.

The switches (PERCEPTION.enabled, IMPAIRMENT.enabled) are forced on inside fixtures and restored afterwards. The
intoxication of one resident is set on the body node and restored. The town is the module's shared game, so each test
puts back the turn and the body values it changes.
"""
from __future__ import annotations

import copy
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                            # noqa: E402
from bigville.backends.protocol import ActorResponse, ProposedAction  # noqa: E402
from domains import impairment as I                            # noqa: E402
from domains import perceiver as P                             # noqa: E402
from domains.impairment_check import check_impairment          # noqa: E402
from domains.pack import load_pack                             # noqa: E402
from worlds import daynight as dn                              # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = load_pack("bigville")
PATH_BIGVILLE = os.path.join(_ROOT, "packs", "bigville")
HEDGE = re.compile(r"\b(maybe|perhaps|seems?|might|possibly|apparently|appears?|looks? like|probably)\b", re.I)


@pytest.fixture(scope="module")
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


@pytest.fixture
def switches():
    """Perception and impairment forced on for one test, then restored (the pack tables are cached per process)."""
    saved = {name: dict(PACK[name]) for name in ("PERCEPTION", "IMPAIRMENT")}
    PACK["PERCEPTION"]["enabled"] = True
    PACK["IMPAIRMENT"]["enabled"] = True
    try:
        yield
    finally:
        for name, values in saved.items():
            PACK[name].clear()
            PACK[name].update(values)


def _body(game, actor):
    return game.world._bodies[actor]


@pytest.fixture
def drunk(town):
    """Sets the intoxication of a resident who has a neighbour in sight, to a drunk level, and gives it the enforced
    faculties of an LLM or human resident (a simple resident holds impairment itself, so it is not distorted). Restores
    both afterwards."""
    world = town.world
    actor = _resident_with_neighbour(town)
    body = _body(town, actor)
    old_level = world.eng.node(body)["attrs"].get("intoxication", 0.0)
    old_turn = world._turn
    world.eng.set_attr(body, "intoxication", 0.5)
    backend = town.backends[actor]
    had = "faculties" in vars(backend)
    old_faculties = vars(backend).get("faculties")
    backend.faculties = {faculty: "enforced" for faculty in P.FACULTIES}
    try:
        yield actor
    finally:
        if had:
            backend.faculties = old_faculties
        else:
            del backend.faculties
        world.eng.set_attr(body, "intoxication", old_level)
        world._turn = old_turn


def _neighbour(game, actor):
    world = game.world
    pos = world.actor_position(actor)
    for other in world._actors:
        if other == actor or not world.is_alive(other):
            continue
        p = world.actor_position(other)
        if p is not None and max(abs(p[0] - pos[0]), abs(p[1] - pos[1])) <= 1:
            return other
    return None


def _resident_with_neighbour(game):
    for name in sorted(game.characters):
        if game.world.is_alive(name) and _neighbour(game, name):
            return name
    raise AssertionError("the town has no resident with a neighbour")


def _people(view):
    return view["around"]["people"]


def _rows(view, kind="person"):
    return [row for row in view["referee"]["perception"]["subjects"] if row["kind"] == kind]


# ------------------------------------------------------------------ the pack, the switch, the self-test
def test_the_pack_is_clean_in_both_packs_and_the_switch_is_off():
    for name in ("bigville", "test_hamlet"):
        pack = load_pack(name)
        assert pack["IMPAIRMENT"]["enabled"] is False
        errors, warnings, info = [], [], []
        check_impairment(os.path.join(_ROOT, "packs", name), errors, warnings, info)
        assert errors == [] and warnings == []


def test_the_two_packs_carry_the_same_impairment_tables():
    for table in ("IMPAIRMENT", "DISTORTION", "IMPAIRMENT_NEIGHBOURS"):
        assert load_pack("bigville")[table] == load_pack("test_hamlet")[table]


def test_self_test_finds_a_source_with_no_row():
    errors, warnings, info = [], [], []
    sources = list(PACK["IMPAIRMENT"]["sources"]) + ["fear"]
    check_impairment(PATH_BIGVILLE, errors, warnings, info, sources=sources)
    assert any("'fear' has 0 DISTORTION rows" in message for message in errors)


def test_self_test_finds_a_row_with_no_listed_source_and_a_bad_rate():
    errors, warnings, info = [], [], []
    rows = copy.deepcopy(PACK["DISTORTION"])
    rows.append({"source": "grief", "measure": "fatigue", "steps": [[0.5, 1.5]],
                 "kinds": {"person": ["neighbour_stage"], "thing": ["lower_tier"]}})
    check_impairment(PATH_BIGVILLE, errors, warnings, info, rows=rows)
    assert any("'grief' names a source" in message for message in warnings)
    assert any("rate must be a number from 0 to 1" in message for message in errors)


def test_self_test_finds_a_neighbour_stage_for_a_thing():
    errors, warnings, info = [], [], []
    rows = copy.deepcopy(PACK["DISTORTION"])
    rows[1]["kinds"]["thing"].append("neighbour_stage")
    check_impairment(PATH_BIGVILLE, errors, warnings, info, rows=rows)
    assert any("applies to a person, not a thing" in message for message in errors)


# ------------------------------------------------------------------ the mechanisms, on their own
def test_each_mechanism_gives_a_plausible_wrong_percept(town, switches):
    actor = _resident_with_neighbour(town)
    other = _neighbour(town, actor)
    subject = P.person_subject(town, other, "bigville")
    seen = {"tier": 1, "words": f"a {subject['stage']}"}
    lower = I._candidates("lower_tier", "person", other, subject, seen, town, "bigville", [], set())
    assert lower == [{"tier": 0, "words": "a person"}]
    stage_words = {c["words"] for c in I._candidates("neighbour_stage", "person", other, subject, seen, town,
                                                     "bigville", [], set())}
    assert stage_words and all(words.startswith("a ") and subject["stage"] not in words for words in stage_words)
    thing = {"kind": "knife", "marks": {}, "trade_skills": []}
    kinds = I._candidates("nearby_entity", "thing", "knife_1", thing, {"tier": 1, "words": "knife"}, town,
                          "bigville", [("spade_2", "spade"), ("knife_1", "knife")], set())
    assert kinds == [{"tier": 1, "words": "spade"}]


# ------------------------------------------------------------------ the switches
def test_with_the_switch_off_no_percept_is_marked_and_the_view_has_no_impairment_block(town):
    PACK["PERCEPTION"]["enabled"] = True
    try:
        actor = _resident_with_neighbour(town)
        view = town.agent_view(actor, mode="referee")
        assert all("distorted" not in row for row in view["referee"]["perception"]["subjects"])
        assert "impairment" not in view["referee"]["perception"]
    finally:
        PACK["PERCEPTION"]["enabled"] = False


def test_a_sober_resident_is_given_the_percept_it_would_have_without_impairment(town, switches):
    """The truth is the referee's. The Phase 062 percept can differ from it by the observer's own gates (its light,
    distance and skill), so the check is that impairment adds nothing: a sober view equals the view with it off."""
    actor = _resident_with_neighbour(town)
    body = _body(town, actor)
    old = town.world.eng.node(body)["attrs"].get("intoxication", 0.0)
    town.world.eng.set_attr(body, "intoxication", 0.0)
    backend = town.backends[actor]
    backend.faculties = {faculty: "enforced" for faculty in P.FACULTIES}
    try:
        on = town.agent_view(actor, mode="referee")
        rows = on["referee"]["perception"]["subjects"]
        assert rows and all(row["distorted"] is False for row in rows)
        PACK["IMPAIRMENT"]["enabled"] = False
        off = town.agent_view(actor, mode="referee")
        assert on["around"] == off["around"]
        assert [(r["subject"], r["percept"], r["truth"]) for r in rows] == \
            [(r["subject"], r["percept"], r["truth"]) for r in off["referee"]["perception"]["subjects"]]
    finally:
        PACK["IMPAIRMENT"]["enabled"] = True
        del backend.faculties
        town.world.eng.set_attr(body, "intoxication", old)


def test_the_strength_switch_and_the_scenario_turn_the_distortion_off(town, switches, drunk):
    actor = drunk
    town.impairment_scenario = {"strength": 0.0}
    try:
        for turn in range(40):
            town.world._turn = turn
            assert not any(row.get("distorted") for row in _rows(town.agent_view(actor, mode="referee")))
    finally:
        del town.impairment_scenario
    town.impairment_scenario = {"enabled": False}
    try:
        town.world._turn = 0
        assert all("distorted" not in row for row in _rows(town.agent_view(actor, mode="referee")))
    finally:
        del town.impairment_scenario


def test_a_scenario_with_an_unknown_source_is_refused(town, switches):
    town.impairment_scenario = {"sources": ["fear"]}
    try:
        with pytest.raises(ValueError):
            town.agent_view(PLAYER)
    finally:
        del town.impairment_scenario


def test_a_backend_that_holds_impairment_itself_gets_no_distortion(town, switches, drunk):
    rec = P.record(town, drunk, {**P.declared(None, "bigville"), "impairment": "represented"}, "bigville")
    seen = {"tier": 1, "words": "a grown person", "truth_tier": 1, "truth": "a grown person"}
    assert I.distort(town, drunk, "person", "x", {}, seen, rec, "bigville", others=[], known=()) is seen


# ------------------------------------------------------------------ the drunk resident
def _drunk_views(game, actor, turns):
    """(turn, referee view) for each turn; the world turn is set and left at the last value."""
    out = []
    for turn in turns:
        game.world._turn = turn
        out.append((turn, game.agent_view(actor, mode="referee")))
    return out


def test_a_drunk_resident_is_shown_confidently_wrong_percepts(town, switches, drunk):
    views = _drunk_views(town, drunk, range(60))
    distorted = [(turn, row) for turn, view in views for row in _rows(view) if row["distorted"]]
    assert distorted, "a drunk resident with neighbours in sight should be shown a wrong percept in 60 turns"
    for _turn, row in distorted:
        assert row["percept"] != row["truth"] or "as" in row
        assert "intoxication" in row["sources"]
        assert not HEDGE.search(row["percept"]), "a wrong percept is worded as sure as a true one"


def test_a_wrong_percept_reaches_the_agent_view_and_the_truth_does_not(town, switches, drunk):
    for turn in range(60):
        town.world._turn = turn
        referee = town.agent_view(drunk, mode="referee")
        pairs = list(zip(_rows(referee), _people(town.agent_view(drunk))))
        shown = [(row, entry) for row, entry in pairs if row["distorted"] and "description" in entry]
        if shown:
            agent = town.agent_view(drunk)
            assert "referee" not in agent and "distorted" not in repr(agent)
            for row, entry in shown:
                assert entry["description"] == row["percept"], "the agent view shows the percept, not the truth"
                assert row["truth"] not in repr(entry) or row["truth"] == row["percept"]
            return
    raise AssertionError("no distorted, unrecognised percept in 60 turns to check the agent view against")


def test_the_same_seed_and_turn_give_the_same_percepts(switches, drunk):
    """Two fresh games with the same seed, turn and intoxication give the same percepts (the shared town has moved on,
    so the comparison is between two new games)."""
    first_game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    second_game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    views = []
    for game in (first_game, second_game):
        game.world._turn = 7
        game.world.eng.set_attr(_body(game, drunk), "intoxication", 0.5)
        game.backends[drunk].faculties = {faculty: "enforced" for faculty in P.FACULTIES}
        views.append(game.agent_view(drunk, mode="referee")["referee"]["perception"])
    assert views[0] == views[1]
    first_game.world._turn = 7
    again = first_game.agent_view(drunk, mode="referee")["referee"]["perception"]
    assert again == views[0]


def test_a_resident_known_by_name_can_be_taken_for_another_known_resident(town, switches):
    actor = _resident_with_neighbour(town)
    other = _neighbour(town, actor)
    spare = next(name for name in town.world._actors if name not in (actor, other))
    subject = P.person_subject(town, other, "bigville")
    seen = {"tier": 1, "words": f"a {subject['stage']}", "truth_tier": 1, "truth": f"a {subject['stage']}"}
    found = I._candidates("nearby_entity", "person", other, subject, seen, town, "bigville", [spare],
                          {other, spare})
    assert found == [{"tier": 1, "words": spare, "as": spare,
                      "as_job": P.person_subject(town, spare, "bigville")["job"]}]


# ------------------------------------------------------------------ the ledger
def test_an_action_on_a_wrong_percept_is_counted_with_its_outcome(town, switches, drunk):
    shown = None
    for turn in range(60):
        town.world._turn = turn
        view = town.agent_view(drunk, mode="referee")
        rows = [row for row in _rows(view, "thing") + _rows(view) if row.get("distorted")]
        if rows:
            shown = rows[0]
            break
    assert shown is not None, "a drunk resident should be shown a wrong percept in 60 turns"
    before = dict(I.report_block(town, "bigville")["impairment"])
    target = shown["subject"]
    town._apply_response(drunk, ActorResponse(major_action=ProposedAction("rest", {"target": target})))
    after = I.report_block(town, "bigville")["impairment"]
    assert after["actions"] == before["actions"] + 1
    assert after["on_wrong_percept"] == before["on_wrong_percept"] + 1
    assert after["on_wrong_applied"] + after["on_wrong_refused"] == before["on_wrong_applied"] + before["on_wrong_refused"] + 1
    assert after["by_source"].get("intoxication", 0) >= 1


def test_the_report_has_no_impairment_block_while_the_switch_is_off(town):
    assert I.report_block(town, "bigville") == {}
    assert I.referee_block(town, [], "bigville") == {}


def test_a_drunk_resident_is_shown_a_nearby_thing_for_the_thing_in_sight(town, switches, drunk, monkeypatch):
    """Two objects in view: a knife and a spade. A drunk resident is sometimes shown the spade for the knife (its handle
    still names the knife, so an action on it is an action on a wrong percept). The truth is in the referee row only."""
    world = town.world
    objects = [{"id": "knife_1", "kind": "knife", "location": "world"},
               {"id": "spade_2", "kind": "spade", "location": "world"}]
    monkeypatch.setattr(world, "physical_object_observations", lambda actor: objects)
    monkeypatch.setattr(world, "_physical_location_cell", lambda *a, **k: None)
    monkeypatch.setattr(dn, "view_light", lambda w, a: "day")
    seen_wrong = None
    for turn in range(80):
        world._turn = turn
        referee = town.agent_view(drunk, mode="referee")
        for row in _rows(referee, "thing"):
            if row["distorted"]:
                seen_wrong = row
                break
        if seen_wrong:
            break
    assert seen_wrong is not None, "a drunk resident should be shown a wrong thing in 80 turns"
    assert seen_wrong["truth"] in {"knife", "spade"} and seen_wrong["percept"] != seen_wrong["truth"]
    agent = town.agent_view(drunk)
    shown = [thing for thing in agent["around"]["things"] if thing.get("handle") == seen_wrong["subject"]]
    assert shown and shown[0]["what"] == seen_wrong["percept"]
    assert all(thing.get("what") != seen_wrong["truth"] for thing in shown)
