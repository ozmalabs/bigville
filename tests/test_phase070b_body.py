"""Phase 070b: aimed strikes, injury that lowers capacity, disease loci, and the free glance.

Views and the sleep rule use a real founding town (scenario town100, seed 305000); the strike and walking tests use a
small world, as the Phase 038 and 024 tests do. The sleep-debt rule itself is tested in tests/test_phase070_locus.py.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                     # noqa: E402
from domains import attend_commands as AC                                # noqa: E402
from domains import interoception as I                                   # noqa: E402
from worlds import body as B                                             # noqa: E402
from worlds.bigville_world import BigvilleWorld as World                 # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
TABLES = B.pack_tables("bigville")
A, H = "Ada", "Hal"


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _pair():
    """Two residents on one cell (Ada attacks Hal), a tick in, turn-start recorded (as Phase 038's tests)."""
    w = World(autonomous_actors=False)
    cells = sorted(w._map_cells)
    cell = cells[len(cells) // 2]
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w._move_actor_to(A, cell)
    w._move_actor_to(H, cell)
    w.tick()
    w.mark_turn_start()
    return w


# ------------------------------------------------------------------ 2: injury lowers capacity
def test_an_empty_ledger_gives_every_capacity_factor_exactly_one(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    assert body.state["ledger"] == {}
    for capacity in ("speed", "strength", "stamina"):
        assert world._body_capacity_factor(name, capacity) == 1.0


def test_an_arm_injury_lowers_effective_strength_by_its_weight(town):
    world = town.world
    name = _adult(world)
    before = world.effective_strength(name)
    world.body_of(name).state["ledger"]["arm"] = 0.25
    weight = float(TABLES["injury_effects"]["weights"]["arm"]["strength"])
    assert world._body_capacity_factor(name, "strength") == pytest.approx(1.0 - weight * 0.25, abs=1e-6)
    assert world.effective_strength(name) == pytest.approx(before * (1.0 - weight * 0.25), rel=1e-4)
    assert world._body_capacity_factor(name, "speed") == 1.0      # an arm does not slow walking


def test_a_leg_injury_slows_walking_and_the_slowdown_heals_back(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    assert world._body_capacity_factor(name, "speed") == 1.0
    body.state["ledger"]["leg"] = 0.2
    assert world._body_capacity_factor(name, "speed") == pytest.approx(0.8, abs=1e-6)
    # Healing: the ledger falls at located_heal_per_tick, and the factor returns to exactly 1.0.
    rate = float(TABLES["rates"]["located_heal_per_tick"])
    for _ in range(int(0.2 / rate) + 2):
        body.tick()
    assert body.state["ledger"] == {}
    assert world._body_capacity_factor(name, "speed") == 1.0


def test_a_leg_injury_lengthens_the_walking_interval(town):
    """A step's cooldown is the interval less one tick (world._walk_cooldown). The leg factor divides the interval, so
    an injured walker waits longer on a step than an uninjured one on the same ground."""
    world = town.world
    name = _adult(world)
    here = world.actor_position(name)
    nxt = next((cell for cell in sorted(world._map_cells)
                if abs(cell[0] - here[0]) + abs(cell[1] - here[1]) == 1
                and world.terrain_state(cell)["speed"] > 0.0), None)
    assert nxt is not None
    node = world._actors[name]

    def step_cooldown(ledger_leg):
        world.embodiment[name]["ledger"] = {"leg": ledger_leg} if ledger_leg else {}
        world.eng.set_attr(node, "carry_move_cooldown", 0.0)
        world._move_actor_to(name, here)
        world.move_actor(name, nxt)
        cooldown = float(world.eng.node(node)["attrs"].get("carry_move_cooldown", 0.0))
        world._move_actor_to(name, here)
        return cooldown

    assert step_cooldown(0.4) > step_cooldown(0.0)


# ------------------------------------------------------------------ 1: aimed strikes
def test_an_unknown_region_is_refused_before_any_action_is_used():
    w = _pair()
    pending, reason = w.strike_begin(A, {"target": H, "intensity": 1.0, "region": "tail"})
    assert pending is None and reason == "unknown_region"
    from domains.pack import load_pack
    assert "unknown_region" in load_pack("bigville")["REFUSAL_REASONS"]
    assert w.eng.node(w._actors[A])["attrs"].get("major_action_used", 0.0) == 0.0


def test_an_unaimed_blow_passes_no_locus_to_harm():
    w = _pair()
    pending, _ = w.strike_begin(A, {"target": H, "intensity": 1.0})
    assert pending is not None and pending["region"] is None
    assert w._strike_locus(pending, None) is None


def test_an_aimed_blow_lands_on_its_region_only_by_the_stateless_draw():
    w = _pair()
    pending = {"region": "head", "attacker": A, "target": H, "attacker_side": {"skill": 0.0}}
    hits = 0
    for turn in range(2000):
        w._turn = turn
        landed = w._strike_locus(pending, None)
        assert landed in ("head", None)
        hits += landed == "head"
        assert w._strike_locus(pending, None) == landed          # same state, same answer: no random stream
    chance = TABLES["strike_aim"]["base"]                        # skill 0 gives the base chance
    assert abs(hits / 2000.0 - chance) < 0.05
    # A brace keeps the blow off its aim: the chance falls by brace_factor.
    braced = 0
    for turn in range(2000):
        w._turn = turn
        braced += w._strike_locus(pending, "brace") == "head"
    assert abs(braced / 2000.0 - chance * TABLES["strike_aim"]["brace_factor"]) < 0.05


# ------------------------------------------------------------------ 3: disease loci
def test_a_disease_with_a_locus_feels_and_harms_from_that_place(town, monkeypatch):
    world = town.world
    name = _adult(world)
    row = dict(world.E.DISEASE.get("fever", {"severity": 0.03}), locus="chest")
    monkeypatch.setitem(world.E.DISEASE, "fever", row)
    world.eng.set_attr(world._actors[name], "disease", "fever")
    body = world.body_of(name)
    assert world._disease_locus(name) == "chest"
    assert body.locus_for() == {"illness": "chest"}
    illness = next(r for r in body.referee()["sources"] if r["source"] == "illness")
    assert illness["locus_true"] == "chest"
    before = dict(body.state["ledger"])
    world.harm(name, 0.02, "illness", locus=world._disease_locus(name))
    assert body.state["ledger"].get("chest", 0.0) > before.get("chest", 0.0)


def test_a_disease_without_a_locus_stays_whole_body(town):
    world = town.world
    name = _adult(world)
    world.eng.set_attr(world._actors[name], "disease", "fever")
    assert world._disease_locus(name) is None                     # the pack's fever row has no locus
    assert world.body_of(name).locus_for() == {}


# ------------------------------------------------------------------ 4: the free glance
def test_a_glance_is_free_and_gives_one_step_for_this_view_only(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    body.state["ledger"]["arm"] = 0.3                              # a felt sharp signal at the arm
    handles = [o["target"] for o in body.attend_options()]
    assert handles, "an injury above awareness must be a felt signal"
    handle = handles[0]
    source = body.signal_named(handle)
    slot_before = world.eng.node(world._actors[name])["attrs"].get("major_action_used", 0.0)
    before = body._derive(use_focus=True)
    plain = next(r for r in before["sources"] if r["source"] == source)
    assert world.free_action(name, "glance", target=handle) is True
    assert world.eng.node(world._actors[name])["attrs"].get("major_action_used", 0.0) == slot_before
    after = next(r for r in body._derive(use_focus=True)["sources"] if r["source"] == source)
    assert after["quality_depth"] + after["locus_depth"] >= plain["quality_depth"] + plain["locus_depth"]
    assert body.referee()["sources"] and body.state["glance"] == {"source": source}
    body.tick()                                                    # the next tick ends the glance
    assert body.state["glance"] is None


def test_a_glance_is_refused_asleep_and_for_no_such_signal(town):
    world = town.world
    name = _adult(world)
    assert world.free_action(name, "glance", target="signal:99") is False
    world.eng.set_attr(world._actors[name], "asleep", 1.0)
    assert world.free_action(name, "glance", target="signal:1") is False
    world.eng.set_attr(world._actors[name], "asleep", 0.0)


def test_the_glance_words_parse_to_a_free_action_and_not_a_major_one():
    assert AC.parse_line("glance") == {"free_action": {"action": "glance", "target": "signal:1"}}
    assert AC.parse_line("glance 2") == {"free_action": {"action": "glance", "target": "signal:2"}}
    assert AC.parse_line("attend 2") == {"major_action": {"action": "attend", "target": "signal:2"}}


def test_the_glance_is_a_free_action_with_a_description_in_the_pack():
    from domains import bigville_entities as E
    assert "glance" in E.FREE_ACTIONS and E.FREE_ACTIONS["glance"]["description"].strip()
    assert E.ATTEND["glance_stamina_cost"] == 0.0
    assert "glance" not in E.MAJOR_ACTIONS


def test_the_strike_description_names_the_region_param():
    from domains import bigville_entities as E
    assert "params region" in E.MAJOR_ACTIONS["strike"]["description"]


def _view(**replace):
    """A plain dict of the bigville tables the Phase 070b checks read, with some replaced."""
    from domains.pack import load_pack
    pack = load_pack("bigville")
    view = {name: pack[name] for name in ("BODY_RATES", "LIFE_STAGES", "STRIKE_AIM", "INJURY_EFFECTS", "ATTEND",
                                          "FREE_ACTIONS", "REFUSAL_REASONS", "DISEASE") if name in pack}
    view.update(replace)
    return view


def test_the_self_test_finds_a_bad_injury_locus_and_a_bad_disease_locus():
    from domains import interoception_check as IC
    anatomy = {"body": {"parent": None, "label": "all over"}, "chest": {"parent": "body", "label": "chest"}}
    effects = dict(B.pack_tables("bigville")["injury_effects"])
    errors = []
    IC._check_phase070b(_view(INJURY_EFFECTS=dict(effects, weights={"tail": {"speed": 1.0}})), anatomy, errors)
    assert any("tail" in e for e in errors)
    errors = []
    IC._check_phase070b(_view(DISEASE={"fever": {"locus": "nowhere"}}), anatomy, errors)
    assert any("nowhere" in e for e in errors)
    errors = []
    from domains.pack import load_pack
    real = {name: row for name, row in load_pack("bigville")["ANATOMY"].items() if not name.startswith("_")}
    IC._check_phase070b(_view(DISEASE={"fever": {"locus": "chest"}}), real, errors)
    assert errors == []
