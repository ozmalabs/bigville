"""Phase 071: attending to a feeling (attend) and probing one's own body (press).

The depth rule, the attention budget and the press reaction are pure functions of the pack's ATTEND table and the
interoception tables (domains/interoception.py); the body (worlds/body.py) and the world's enactment decide the
refusals, the stamina cost and the timers. Views are built from a real founding town (scenario town100, seed 305000).
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                     # noqa: E402
from bigville.backends.protocol import ActorResponse                     # noqa: E402
from bigville.backends import reply_schema                               # noqa: E402
from bigville.reporting import game_report                               # noqa: E402
from domains import attend_commands as AC                                # noqa: E402
from domains import interoception as I                                   # noqa: E402
from domains import interoception_check as IC                           # noqa: E402
from domains.agent_view_check import felt_body_problems                 # noqa: E402
from domains.pack import load_pack                                       # noqa: E402
from worlds import body as B                                             # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = "bigville"
TABLES = B.pack_tables(PACK)
ATTEND = TABLES["attend"]
CHANNELS = TABLES["channels"]
RULES = TABLES["rules"]
RECORD = {"acuity": 1.0, "attention": 1.0, "impairment": 0.0}
NO_READS = {name: 0.0 for name in I.READS}
FORBIDDEN = [word.lower() for word in RULES["forbidden_words"]]


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _focus(source):
    return {"source": source, "acuity_bonus": float(ATTEND["acuity_bonus"]),
            "focus_attention": float(ATTEND["focus_attention"]), "other_attention": float(ATTEND["other_attention"])}


def _derive(reads, record=None, focus=None, located=None):
    return I.derive(TABLES, {**NO_READS, **reads}, dict(RECORD if record is None else record), SEED, "Tester", 3,
                    located=located, focus=focus)


def _row(derived, name):
    return next(row for row in derived["sources"] if row["source"] == name)


def _depths(row):
    return int(row["quality_depth"]), int(row["locus_depth"])


def _attend(world, name, handle="signal:1"):
    return world.major_action(name, "attend", target=handle)


def _next_turn(world):
    world.tick()


# ------------------------------------------------------------------ the resolver under attention
def test_attending_a_gut_signal_stays_within_its_channel_cap_and_the_bonus():
    derived = _derive({"hunger": 1.0}, record={"acuity": 1.3, "attention": 1.0, "impairment": 0.0},
                      focus=_focus("hunger"))
    row = _row(derived, "hunger")
    quality_cap = int(CHANNELS["visceral"]["quality_cap"])
    locus_cap = int(CHANNELS["visceral"]["locus_cap"])
    assert row["quality_depth"] <= quality_cap and row["locus_depth"] <= locus_cap
    # The most the rule can give: acuity plus the bonus, full attention, the top of the jitter.
    best = I.raw_depth(RULES, row["intensity"], 1.3 + float(ATTEND["acuity_bonus"]), 1.0, 0.0, 1.0)
    assert row["quality_depth"] <= int(best) and row["locus_depth"] <= int(best)


def test_a_surface_signal_resolves_further_than_a_visceral_one():
    located = {"injury": {"upper_belly": 0.5}}
    derived = _derive({"hunger": 1.0}, record={"acuity": 1.3, "attention": 1.0, "impairment": 0.0},
                      focus=_focus("injury_sharp@upper_belly"), located=located)
    surface = _row(derived, "injury_sharp@upper_belly")
    visceral = _row(derived, "hunger")
    assert int(CHANNELS["surface"]["locus_cap"]) > int(CHANNELS["visceral"]["locus_cap"])
    assert surface["locus_depth"] == 3                       # the true place is upper_belly, depth 3
    assert visceral["locus_depth"] <= int(CHANNELS["visceral"]["locus_cap"])
    assert surface["locus_depth"] > visceral["locus_depth"]


def test_while_attending_the_other_signals_resolve_shallower_or_equal():
    located = {"injury": {"upper_belly": 0.5}}
    reads = {"hunger": 1.0, "chill": 0.8}
    record = {"acuity": 1.3, "attention": 1.0, "impairment": 0.0}
    plain = _derive(reads, record=record, located=located)
    focused = _derive(reads, record=record, located=located, focus=_focus("injury_sharp@upper_belly"))
    for name in ("hunger", "chill"):
        assert _depths(_row(focused, name))[0] <= _depths(_row(plain, name))[0]
        assert _depths(_row(focused, name))[1] <= _depths(_row(plain, name))[1]
    attended = _row(focused, "injury_sharp@upper_belly")
    assert attended["locus_depth"] >= _row(plain, "injury_sharp@upper_belly")["locus_depth"]
    assert attended["focused"] is True and _row(focused, "hunger")["focused"] is False


# ------------------------------------------------------------------ the world: refusals, cost, timer
def test_attending_asleep_or_collapsed_is_refused_with_a_recorded_reason(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    world.eng.set_attr(world._actors[name], "asleep", 1.0)
    assert _attend(world, name) is False
    assert world.last_outcome(name)["reason"] == "asleep"
    assert world.refusals(name)[-1]["reason"] == "asleep"
    world.eng.set_attr(world._actors[name], "asleep", 0.0)
    world.eng.set_attr(world._actors[name], "collapsed", 1.0)
    world.eng.set_attr(world._actors[name], "asleep", 1.0)
    assert _attend(world, name) is False
    assert world.last_outcome(name)["reason"] == "collapsed"


def test_a_second_attend_is_refused_while_attending_and_other_major_actions_wait(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    assert _attend(world, name) is True
    _next_turn(world)
    assert _attend(world, name) is False
    assert world.last_outcome(name)["reason"] == "attending"
    assert world.major_action(name, "eat", kind="bread") is False
    assert world.last_outcome(name)["reason"] == "attending"
    for _ in range(int(ATTEND["ticks"])):
        _next_turn(world)
    assert world.embodiment[name]["attending"] is None


def test_an_attend_costs_the_stamina_reserve_it_states_and_the_attention_runs_its_ticks(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    node = world._bodies[name]
    world.eng.set_attr(node, "stamina_reserve", 0.9)
    assert _attend(world, name) is True
    assert world.eng.node(node)["attrs"]["stamina_reserve"] == pytest.approx(0.9 - float(ATTEND["stamina_cost"]))
    assert world.embodiment[name]["attending"]["ticks"] == int(ATTEND["ticks"])


def test_an_attend_with_no_such_signal_is_refused_and_names_no_cause(town):
    world = town.world
    name = _adult(world)
    assert _attend(world, name, handle="signal:9") is False
    assert world.last_outcome(name)["reason"] == "unknown_target"
    assert _attend(world, name, handle="hunger") is False
    assert world.last_outcome(name)["reason"] == "unknown_target"


# ------------------------------------------------------------------ press
def test_three_presses_narrow_a_torso_feeling_to_its_true_place(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    body.state["ledger"]["upper_belly"] = 0.1          # the true place: upper_belly, under front_torso, under torso
    torso = body.press("torso")
    front = body.press("front_torso")
    deep = body.press("upper_belly")
    chest = body.press("chest")
    arm = body.press("arm")
    assert torso["sound"] is not None and front["sound"] is not None and deep["sound"] is not None
    assert chest["sound"] is None and arm["sound"] is None
    assert deep["where"] == "upper belly"


def test_pressing_an_injured_place_raises_it_briefly_then_it_settles(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    body.state["ledger"]["upper_belly"] = 0.1
    assert body.located()["injury"]["upper_belly"] == pytest.approx(0.1)
    body.press("upper_belly")
    assert body.located()["injury"]["upper_belly"] == pytest.approx(0.1 + float(ATTEND["press_boost"]))
    for _ in range(int(ATTEND["press_ticks"])):
        body.tick()
    assert "upper_belly" not in body.state["pressed"]
    assert body.located()["injury"]["upper_belly"] == pytest.approx(0.1, abs=0.01)


def test_a_press_is_refused_asleep_and_an_unknown_region_is_unknown_target(town):
    world = town.world
    name = _adult(world)
    assert world.major_action(name, "press", target="arm") is True
    _next_turn(world)
    assert world.major_action(name, "press", target="nowhere") is False
    assert world.last_outcome(name)["reason"] == "unknown_target"
    _next_turn(world)
    world.eng.set_attr(world._actors[name], "asleep", 1.0)
    assert world.major_action(name, "press", target="arm") is False
    assert world.last_outcome(name)["reason"] == "asleep"


def test_press_and_attend_are_not_offered_to_the_simple_backends(town):
    world = town.world
    name = _adult(world)
    actions = {row.get("action") for row in world.actor_affordances(name)}
    assert "attend" not in actions and "press" not in actions
    major = load_pack(PACK)["MAJOR_ACTIONS"]
    assert "attend" in major and "press" in major
    assert "attending" in load_pack(PACK)["REFUSAL_REASONS"]


# ------------------------------------------------------------------ views, leak rule and the reply path
def test_nothing_in_last_or_the_view_names_a_cause(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["upper_belly"] = 0.2
    assert _attend(world, name) is True
    _next_turn(world)
    assert world.major_action(name, "press", target="front_torso") is True
    view = town.agent_view(name, "agent")
    assert set(view["last"]) <= {"action", "outcome", "reason", "sound", "place"}
    assert view["last"]["action"] == "press"
    assert view["last"]["place"] == "front of the torso" and "sound" in view["last"]
    text = json.dumps({"last": view["last"], "can": view["can"], "self_body": view["self"]["body"]}).lower()
    assert not [word for word in FORBIDDEN if word in text]
    assert felt_body_problems(world.body_of(name).afferents(), PACK) == []


def test_the_attend_rows_in_can_name_the_place_by_handle_only(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    rows = [row for row in town.agent_view(name, "agent")["can"] if row["action"] == "attend"]
    assert rows and rows[0]["handle"] == "signal:1"
    assert set(rows[0]) == {"handle", "action", "what"}
    assert rows[0]["what"] == "arm"


def test_a_reply_that_names_a_handle_runs_the_attend(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    wire = reply_schema.to_wire({"major_action": {"action": "attend", "target": "signal:1"}}, PACK, affordances=[])
    response = ActorResponse.from_dict(wire)
    plan = {"action": response.major_action.action, **response.major_action.params}
    assert plan == {"action": "attend", "target": "signal:1"}
    assert world.enact_plan(name, plan) is True


def test_the_same_seed_gives_the_same_feeling_and_probe():
    results = []
    for _ in range(2):
        game = create_game(scenario="town100", seed=SEED, player=PLAYER)
        world = game.world
        name = _adult(world)
        world.body_of(name).state["ledger"]["upper_belly"] = 0.2
        _attend(world, name)
        _next_turn(world)
        world.major_action(name, "press", target="upper_belly")
        results.append((world.embodiment[name]["probe"], world.body_of(name).afferents(),
                        world.body_of(name).referee()["sources"]))
    assert results[0] == results[1]


def test_the_body_round_trips_through_dump_and_load_with_attention_and_presses(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["upper_belly"] = 0.2
    _attend(world, name)
    _next_turn(world)
    world.major_action(name, "press", target="upper_belly")
    body = world.body_of(name)
    copy_body = B.WorldBackedBody.load(body.dump(), world=world, actor=name)
    assert copy_body.dump() == body.dump()
    assert copy_body.afferents() == body.afferents()


# ------------------------------------------------------------------ the report
def test_the_report_counts_attends_presses_and_remedies_from_the_referee_table(town):
    world = town.world
    name = _adult(world)
    world.body_of(name).state["ledger"]["arm"] = 0.4
    assert _attend(world, name) is True
    report = game_report(town)["attention"]
    assert report["attends"] == 1 and report["attending_now"] == 1 and report["presses"] == 0
    assert report["depth_gained"] >= 0
    # The attended source is an injury, whose remedy is care. A care action after the attend counts once.
    world._body_note_outcome(name, "care", True)
    assert game_report(town)["attention"]["acted_on_true_source"] == 1
    world._body_note_outcome(name, "care", True)
    assert game_report(town)["attention"]["acted_on_true_source"] == 1


def test_the_report_is_not_part_of_the_world_state_export(town):
    world = town.world
    assert "attention" not in world.report()
    assert all("attend" not in key for key in world.export_state())


# ------------------------------------------------------------------ the terminal words (hand-off)
def test_the_attend_and_press_words_parse_to_their_replies():
    assert AC.parse_line("attend", PACK) == {"major_action": {"action": "attend", "target": "signal:1"}}
    assert AC.parse_line("attend 2", PACK) == {"major_action": {"action": "attend", "target": "signal:2"}}
    assert AC.parse_line("focus signal 3", PACK) == {"major_action": {"action": "attend", "target": "signal:3"}}
    assert AC.parse_line("press upper belly", PACK) == {"major_action": {"action": "press", "target": "upper_belly"}}
    assert AC.parse_line("press upper_belly", PACK) == {"major_action": {"action": "press", "target": "upper_belly"}}
    assert AC.parse_line("press nowhere", PACK) is None
    assert AC.parse_line("press", PACK) is None
    assert AC.parse_line("walk home", PACK) is None
    assert AC.parse_line("attend 0", PACK) is None


# ------------------------------------------------------------------ self-test checks for the table
class _Pack(dict):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


def _checked(mutate):
    base = load_pack(PACK)
    data = {name: copy.deepcopy(base[name]) for name in IC.REQUIRED + ("LIFE_STAGES", "REFUSAL_REASONS")}
    mutate(data)
    errors = []
    original = IC.load_pack
    IC.load_pack = lambda name: _Pack(data, name)
    try:
        IC.check_interoception(PACK, errors, [], [])
    finally:
        IC.load_pack = original
    return errors


def test_the_self_test_passes_on_both_packs_with_the_attend_table():
    for pack in (PACK, "test_hamlet"):
        errors, info = [], []
        IC.check_interoception(pack, errors, [], info)
        assert errors == [], (pack, errors)


def test_the_self_test_finds_a_remedy_for_an_unknown_source_and_a_bad_press_ladder():
    def bad_remedy(data):
        data["ATTEND"]["remedies"]["no_such_source"] = ["eat"]
    def bad_ladder(data):
        data["ATTEND"]["press_sounds"][0]["min"] = 0.1
    def no_refusal(data):
        del data["REFUSAL_REASONS"]["attending"]
    def bad_sound(data):
        data["ATTEND"]["press_sounds"][1]["sound"] = "ow!"
    assert any("no_such_source" in e for e in _checked(bad_remedy))
    assert any("press_sounds" in e and "min 0" in e for e in _checked(bad_ladder))
    assert any("attending" in e for e in _checked(no_refusal))
    assert any("letters only" in e for e in _checked(bad_sound))
