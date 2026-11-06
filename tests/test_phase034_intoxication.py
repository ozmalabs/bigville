"""Phase 034: intoxication. Alcohol is a physical fact in the body (Widmark scale, INTOXICATION table).

A drink adds its grams of alcohol, more for a lighter body. The level falls each clock tick. A working skill loses
coordination (physical) or focus (cognitive) in proportion to the level, through effective_skill. Stagger slows
movement; pass_out sleeps the resident until the level falls below wake_below. The simple backend's policy and the
reporter read the level; the world never decides what a resident drinks.
"""
from __future__ import annotations

import math

import pytest

from bigville.backends import ActorContext
from bigville.backends.cheap import DeterministicBackend, SimplePolicy
from bigville.character import CharacterDefinition
from bigville.reporting import SimulationReporter
from domains import bigville_entities as E
from domains import shared_frames as SF
from domains import world_affordances as WA
from domains.pack import load_pack
from worlds.bigville_world import BigvilleWorld as World

PER_TICK = E.INTOXICATION["sober_per_hour"] * E.TIME["minutes_per_tick"] / 60.0


def _resident(name="Tom", *, size=None, metabolism=True):
    kwargs = {} if metabolism else {"physical_subsystems": {"metabolism": False}}
    w = World(autonomous_actors=False, **kwargs)
    cells = sorted(w._map_cells)
    w.add_actor(name, role="hand", home_cell=cells[len(cells) // 2])
    w.give_tableware(name, "wooden_mug")
    w.give_tableware(name, "wooden_ladle")
    w.give_tableware(name, "wooden_dipper")
    if size is not None:
        w.set_capacities(name, size=size)
    return w


def _pair():
    """Two residents, Ada the taker and Hal the holder, on one cell, a tick in, with the sight snapshot taken."""
    w = World(autonomous_actors=False)
    cell = sorted(w._map_cells)[len(w._map_cells) // 2]
    w.add_actor("Ada", role="hand", home_cell=cell)
    w.add_actor("Hal", role="hand", home_cell=cell)
    w._move_actor_to("Ada", cell)
    w._move_actor_to("Hal", cell)
    w.tick()
    w.mark_turn_start()
    return w


def _body(w, name, **attrs):
    for key, value in attrs.items():
        w.eng.set_attr(w._bodies[name], key, float(value))


def _take(w, attacker="Ada", holder="Hal", kind="coin", amount=4.0, reaction=None):
    pending, reason = w.take_begin(attacker, {"source": holder, "kind": kind, "amount": amount})
    if pending is None:
        return None, None, reason
    applied, code = w.take_resolve(pending, reaction)
    return pending, applied, code


def _drink(w, name, kind="ale", count=1):
    w.set_stock(kind, count + 1)
    w.fetch(name, kind, count)
    for _ in range(count):
        assert w.eat(name, kind, vessel="wooden_mug", utensil="wooden_dipper")


def _set_level(w, name, level):
    w.eng.set_attr(w._bodies[name], "intoxication", float(level))


def _level(w, name):
    return w.intoxication(name)


def _reason(w, name):
    return w.last_outcome(name)["reason"]


def _flat_ground(w):
    flat = {**dict(E.TERRAIN_MOVEMENT["grass"]), "terrain": "grass", "move_time": 1.0, "stamina_multiplier": 1.0}
    w.terrain_state = lambda cell: dict(flat)
    w._wear_cell_by_traversal = lambda actor, cell: None


def _neighbour(w, name):
    here = w.actor_position(name)
    for cell in sorted(w._map_cells):
        if cell != here and w.distance(here, cell) == 1:
            return cell
    raise AssertionError("no neighbouring cell")


# ------------------------------------------------------------------ data and the self-test

def test_the_table_and_its_cross_references_are_clean():
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []
    t = E.INTOXICATION
    assert t["sober_per_hour"] == pytest.approx(t["elimination_bac_per_hour"] / t["full_bac_percent"])
    assert PER_TICK == pytest.approx(WA.sober_per_tick())
    b = t["bands"]
    assert 0.0 < b["tipsy"] < b["drunk"] < b["stupefied"] < t["pass_out"] <= 1.0


def test_every_drink_with_alcohol_is_a_drink_and_every_brewed_drink_carries_it():
    drinks = {k: spec for k, spec in E.ITEMS.items() if spec.get("alcohol") is not None}
    assert {"ale", "cider", "mead", "beer"} <= set(drinks)
    for kind, spec in drinks.items():
        assert spec.get("food") and spec.get("food_group") == "drink" and spec["alcohol"] > 0
    for recipe in E.RECIPES:
        out = recipe["out"][0]
        if E.ITEMS.get(out, {}).get("food_group") == "drink":
            assert E.ITEMS[out].get("alcohol", 0) > 0, recipe["name"]


def test_the_grams_are_the_serving_strength_times_the_mug_and_the_ethanol_density():
    # ale 4 per cent, beer 5, cider 4.5, mead 10 (APPROX strengths); one 568 ml mug; 0.789 g/ml ethanol.
    for kind, percent in (("ale", 4.0), ("beer", 5.0), ("cider", 4.5), ("mead", 10.0)):
        assert E.alcohol(kind) == pytest.approx(568.0 * percent / 100.0 * 0.789, abs=1.0)


def test_the_lexicon_reads_the_intoxication_bands_the_world_uses():
    quantity = load_pack("bigville")["LEXICON_QUANTITIES"]["intoxication"]
    assert quantity["published"] is True
    mins = [band["min"] for band in quantity["self"]]
    assert mins == [0.0, E.INTOXICATION["bands"]["tipsy"], E.INTOXICATION["bands"]["drunk"],
                    E.INTOXICATION["bands"]["stupefied"]]


def test_the_pass_out_and_drink_refusal_codes_are_in_the_pack():
    assert E.REFUSAL_REASONS["passed_out"]["description"].strip()


# ------------------------------------------------------------------ drinking and sobering

def test_a_mug_of_ale_raises_intoxication_by_its_alcohol_on_the_widmark_scale():
    w = _resident()
    _drink(w, "Tom")
    assert _level(w, "Tom") == pytest.approx(WA.intoxication_gain(E.alcohol("ale")), abs=1e-4)
    assert _level(w, "Tom") == pytest.approx(0.0945, abs=1e-3)
    assert w.intoxication_band("Tom") == "sober", "one mug of ale stays under the tipsy edge (0.1)"


def test_a_lighter_body_is_affected_more_by_the_same_drink():
    light, heavy = _resident(size=0.7), _resident(size=1.0)
    _drink(light, "Tom")
    _drink(heavy, "Tom")
    assert _level(light, "Tom") == pytest.approx(_level(heavy, "Tom") / 0.7, rel=1e-3)


def test_a_stronger_drink_gives_more_than_a_weaker_one():
    mead, ale = _resident(), _resident()
    _drink(mead, "Tom", kind="mead")
    _drink(ale, "Tom", kind="ale")
    assert _level(mead, "Tom") > 2.0 * _level(ale, "Tom")


def test_intoxication_wears_off_by_the_tables_rate_over_the_clock_ticks():
    w = _resident()
    _drink(w, "Tom")
    start = _level(w, "Tom")
    ticks = 3
    for _ in range(3):
        w.tick()
    assert _level(w, "Tom") == pytest.approx(start - 3 * PER_TICK, abs=1e-3)
    while _level(w, "Tom") > 0.0 and ticks < 1000:
        w.tick()
        ticks += 1
    assert _level(w, "Tom") == 0.0
    assert w.intoxication_band("Tom") == "sober"
    assert ticks == pytest.approx(start / PER_TICK, abs=1.0), "about two and a half hours for a mug of ale"


def test_bread_and_water_leave_intoxication_unchanged():
    w = _resident()
    w.set_stock("bread", 2)
    w.fetch("Tom", "bread", 1)
    assert w.eat("Tom", "bread")
    assert _level(w, "Tom") == 0.0
    assert not w.eat("Tom", "water"), "water is not food and cannot be eaten"
    assert _level(w, "Tom") == 0.0


def test_with_metabolism_off_a_drink_changes_nothing():
    w = _resident(metabolism=False)
    _drink(w, "Tom", count=3)
    assert _level(w, "Tom") == 0.0 and w.intoxication_band("Tom") == "sober"
    w.tick(5)
    assert _level(w, "Tom") == 0.0 and not w.asleep("Tom")


def test_the_body_state_publishes_the_level_and_its_band():
    w = _resident()
    _set_level(w, "Tom", 0.5)
    state = w.body_state("Tom")
    assert state["intoxication"] == pytest.approx(0.5)
    assert state["intoxication_band"] == "drunk"


# ------------------------------------------------------------------ effects through effective_skill

def test_effective_skill_loses_coordination_for_physical_and_focus_for_cognitive_skills():
    physical = "smithing"
    cognitive = next(name for name, spec in E.SKILLS.items() if spec.get("learning") == "cognitive")
    assert SF.skill_learning(physical) == "physical" and SF.skill_learning(cognitive) == "cognitive"
    levels, metas = {physical: 0.8, cognitive: 0.8}, {}
    sober = E.effective_skill(levels, metas, physical, {"intoxication": 0.0})
    drunk = E.effective_skill(levels, metas, physical, {"intoxication": 0.5})
    assert sober - drunk == pytest.approx(E.INTOXICATION["coordination_rate"] * 0.5)
    sober_c = E.effective_skill(levels, metas, cognitive, {"intoxication": 0.0})
    drunk_c = E.effective_skill(levels, metas, cognitive, {"intoxication": 0.5})
    assert sober_c - drunk_c == pytest.approx(E.INTOXICATION["focus_rate"] * 0.5)


def test_a_smith_drunk_past_the_floor_fails_a_recipe_he_passes_sober():
    w = World(autonomous_actors=False)
    w.add_tradesperson("Smith", "smith")
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    floor = float(E.MIN_SKILL["forge_plough"])
    # Put the smith just above the floor with no other skill to lean on, so the drink decides the gate.
    w.eng.set_attr(w._actors["Smith"], "skill", floor + 0.05)
    levels = dict(w.eng.node(w._actors["Smith"])["attrs"].get("skill_levels", {}))
    levels["smithing"] = floor + 0.05
    w.eng.set_attr(w._actors["Smith"], "skill_levels", levels)
    assert w.effective_skill("Smith", "smithing") >= floor
    _set_level(w, "Smith", 0.5)
    assert w.effective_skill("Smith", "smithing") < floor
    assert not w.start("Smith", "forge_plough")
    assert w._refusal_code == "unskilled"
    _set_level(w, "Smith", 0.0)
    assert w.effective_skill("Smith", "smithing") >= floor
    assert w.start("Smith", "forge_plough"), "sober again, the gate is passed"


def test_a_drunk_unskilled_holder_loses_a_contest_he_wins_sober():
    # Both residents are unskilled in fighting (the baseline), so the drink's loss of skill decides the margin.
    sober = _pair()
    _body(sober, "Ada", str_base=0.9)
    _body(sober, "Hal", str_base=1.0)
    _pending, applied, code = _take(sober, reaction="resist")
    assert applied is False and code == "held", "the holder keeps his goods sober"
    drunk = _pair()
    _body(drunk, "Ada", str_base=0.9)
    _body(drunk, "Hal", str_base=1.0)
    _set_level(drunk, "Hal", 0.3)
    _pending, applied, code = _take(drunk, reaction="resist")
    assert applied is True, "drunk, the holder's reaction score falls below the taker's and he loses the goods"


def test_staggering_slows_the_walk_and_publishes_the_slower_speed():
    sober = _resident()
    _flat_ground(sober)
    drunk = _resident()
    _flat_ground(drunk)
    _set_level(drunk, "Tom", 0.5)
    assert sober.stagger_speed("Tom") == 1.0 and drunk.stagger_speed("Tom") == E.INTOXICATION["stagger_speed"]

    def moves(w, turns=24):
        home = w.actor_position("Tom")
        away = _neighbour(w, "Tom")
        count = 0
        for _ in range(turns):
            w.eng.set_attr(w._bodies["Tom"], "stamina_reserve", 1.0)
            w.eng.set_attr(w._actors["Tom"], "hunger", 0.0)
            w.actor_tick("Tom")
            destination = away if w.actor_position("Tom") == home else home
            before = w.actor_position("Tom")
            assert w.major_action("Tom", "move", destination=destination)
            count += w.actor_position("Tom") != before
        return count

    sober_steps = moves(sober)
    _set_level(drunk, "Tom", 0.5)
    drunk_steps = moves(drunk)
    assert drunk_steps < sober_steps, "the staggering walk takes more turns"
    assert drunk_steps == pytest.approx(sober_steps / 2, abs=2)


def test_passing_out_refuses_actions_with_the_reason_and_wakes_without_input():
    w = _resident()
    other = _neighbour(w, "Tom")
    _set_level(w, "Tom", 0.85)
    w._run()
    assert w.asleep("Tom") and not w.collapsed("Tom")
    assert w.body_state("Tom")["asleep"] is True
    assert not w.major_action("Tom", "move", destination=other)
    assert _reason(w, "Tom") == "passed_out"
    reserve = w.stamina_reserve("Tom")
    ticks = 0
    while w.asleep("Tom") and ticks < 2000:
        w.tick()
        ticks += 1
    assert not w.asleep("Tom")
    assert _level(w, "Tom") < E.INTOXICATION["wake_below"]
    assert w.stamina_reserve("Tom") == pytest.approx(reserve), "a drunk sleep restores no stamina"
    expected = math.ceil((0.85 - E.INTOXICATION["wake_below"]) / PER_TICK)
    assert abs(ticks - expected) <= 1


def test_a_resident_below_the_pass_out_line_stays_awake():
    w = _resident()
    _set_level(w, "Tom", E.INTOXICATION["pass_out"] - 0.01)
    w._run()
    assert not w.asleep("Tom")


# ------------------------------------------------------------------ the backends and the reporter

def _policy_context(level):
    character = CharacterDefinition(character_id="Tom", name="Tom", identity={"role": "mason"})
    affordances = [
        {"action": "build", "kind": "", "trade": "", "recipe": "", "target": "wall", "score": 0.0},
        {"action": "transfer", "kind": "ale", "trade": "", "recipe": "", "target": "hal", "recipient": "Hal",
         "score": 0.0},
    ]
    observations = {"calendar": {"hour": 9.0}, "hunger": 0.0, "energy": 100.0, "intoxication": level,
                    "intoxication_band": "drunk" if level >= E.INTOXICATION["bands"]["drunk"] else "sober"}
    return ActorContext(character, 1, observations, affordances)


def _mason():
    # allow_transfers lets the simple policy consider the social option (a transfer to a neighbour).
    return DeterministicBackend(CharacterDefinition(character_id="Tom", name="Tom", identity={"role": "mason"}),
                                policy=SimplePolicy(allow_transfers=True))


def test_a_sober_mason_builds_and_a_drunk_one_prefers_the_social_option():
    sober = _mason()
    assert sober.decide(_policy_context(0.0)).major_action.action == "build"
    assert sober.intoxication_trace == []

    drunk = _mason()
    response = drunk.decide(_policy_context(0.5))
    assert response.major_action.action == "transfer", "drunk, the social option outweighs the work"
    reasons = {entry["action"]: entry["bonus"] for entry in drunk.intoxication_trace}
    assert reasons["transfer"] == pytest.approx(E.INTOXICATION["social_bonus"])
    assert reasons["build"] == pytest.approx(-E.INTOXICATION["effortful_penalty"])


def test_a_tipsy_resident_gets_no_policy_bonus():
    backend = _mason()
    assert backend.decide(_policy_context(E.INTOXICATION["bands"]["tipsy"])).major_action.action == "build"
    assert backend.intoxication_trace == []


def test_the_reporter_counts_bands_resident_ticks_and_alcohol():
    w = _resident()
    _drink(w, "Tom", kind="mead")
    counts = SimulationReporter(w).intoxication()
    assert counts["now"]["stupefied"] + counts["now"]["drunk"] + counts["now"]["tipsy"] + counts["now"]["sober"] == 1
    assert counts["alcohol_grams"] == pytest.approx(E.alcohol("mead"))
    w.tick(2)
    counts = SimulationReporter(w).intoxication()
    assert sum(counts["resident_ticks"].values()) >= 2
    assert "intoxication" in SimulationReporter(w).report(sample_size=5)
