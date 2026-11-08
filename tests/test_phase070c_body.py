"""Phase 070c: a located injury lowers the capacities of the actions that use its region (ACTION_BODY_USE), not every
action. The whole-body read (no action) keeps the Phase 070b meaning. Uses the real founding town (scenario town100,
seed 305000), as tests/test_phase070b_body.py does.
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game          # noqa: E402
from worlds import body as B                  # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
TABLES = B.pack_tables("bigville")
WEIGHTS = TABLES["injury_effects"]["weights"]
ROWS = TABLES["action_body_use"]


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _injure(world, name, locus, amount):
    world.body_of(name).state["ledger"][locus] = float(amount)


def _factor(world, name, action, capacity):
    return world._body_capacity_factor(name, capacity, action)


def test_an_empty_ledger_gives_every_action_and_capacity_exactly_one(town):
    world = town.world
    name = _adult(world)
    assert world.body_of(name).state["ledger"] == {}
    for action in ROWS:
        if action == "_doc":
            continue
        for capacity in ("speed", "strength", "stamina"):
            assert _factor(world, name, action, capacity) == 1.0, (action, capacity)


def test_a_leg_injury_slows_walking_and_lowers_a_push_but_not_a_chop(town):
    world = town.world
    name = _adult(world)
    _injure(world, name, "leg", 0.2)
    assert _factor(world, name, "walk", "speed") == pytest.approx(0.8, abs=1e-6)
    leg_strength = float(WEIGHTS["leg"]["strength"])
    assert _factor(world, name, "push", "strength") == pytest.approx(1.0 - leg_strength * 0.2, abs=1e-6)
    assert _factor(world, name, "chop", "strength") == 1.0
    assert _factor(world, name, "strike", "strength") == 1.0


def test_an_arm_injury_lowers_a_chop_and_a_strike_but_not_walking(town):
    world = town.world
    name = _adult(world)
    _injure(world, name, "arm", 0.25)
    arm = float(WEIGHTS["arm"]["strength"])
    assert _factor(world, name, "chop", "strength") == pytest.approx(1.0 - arm * 0.25, abs=1e-6)
    assert _factor(world, name, "strike", "strength") == pytest.approx(1.0 - arm * 0.25, abs=1e-6)
    assert _factor(world, name, "walk", "speed") == 1.0
    whole_body = world._effective_body_stat(name, "str_base", "str_train")
    assert world.effective_strength(name, "walk") == pytest.approx(whole_body, rel=1e-9)      # walking uses no arm
    assert world.effective_strength(name, "chop") == pytest.approx(whole_body * (1.0 - arm * 0.25), rel=1e-9)


def test_a_back_injury_lowers_carrying_and_not_walking(town):
    world = town.world
    name = _adult(world)
    _injure(world, name, "back", 0.2)
    back_strength = float(WEIGHTS["back"]["strength"])
    back_stamina = float(WEIGHTS["back"]["stamina"])
    assert _factor(world, name, "carry", "strength") == pytest.approx(1.0 - back_strength * 0.2, abs=1e-6)
    assert _factor(world, name, "carry", "stamina") == pytest.approx(1.0 - back_stamina * 0.2, abs=1e-6)
    assert _factor(world, name, "walk", "speed") == 1.0


def test_the_whole_body_read_keeps_every_region_and_an_action_read_keeps_only_its_own(town):
    world = town.world
    name = _adult(world)
    _injure(world, name, "arm", 0.25)
    _injure(world, name, "head", 0.5)
    whole = world._body_capacity_factor(name, "strength")
    expected = 1.0 - float(WEIGHTS["arm"]["strength"]) * 0.25 - float(WEIGHTS["head"]["strength"]) * 0.5
    assert whole == pytest.approx(max(0.5, expected), abs=1e-6)
    # The head is in no action row, so the chop (arm only) reads the arm alone.
    assert _factor(world, name, "chop", "strength") == pytest.approx(1.0 - float(WEIGHTS["arm"]["strength"]) * 0.25,
                                                                      abs=1e-6)


def test_an_action_with_no_row_reads_the_default_arm_row(town):
    world = town.world
    name = _adult(world)
    _injure(world, name, "leg", 0.3)
    assert _factor(world, name, "no_such_verb", "strength") == 1.0      # the default row is the arm only
    _injure(world, name, "arm", 0.1)
    assert _factor(world, name, "no_such_verb", "strength") == pytest.approx(
        1.0 - float(WEIGHTS["arm"]["strength"]) * 0.1, abs=1e-6)


def test_speech_and_rest_use_no_region(town):
    world = town.world
    name = _adult(world)
    for locus in ("leg", "arm", "back", "head", "chest"):
        _injure(world, name, locus, 0.4)
    for action in ("speak", "sleep", "rest", "eat", "drink"):
        assert ROWS[action] == {}
        for capacity in ("speed", "strength", "stamina"):
            assert _factor(world, name, action, capacity) == 1.0


def test_the_speed_factor_of_a_walk_is_the_exhaustion_speed_times_the_leg_factor(town):
    world = town.world
    name = _adult(world)
    band = float(world._exhaustion_band(name)["speed"])
    _injure(world, name, "leg", 0.2)
    assert world.speed_factor(name, "walk") == pytest.approx(round(band * 0.8, 4), abs=1e-4)
    assert world.speed_factor(name) == pytest.approx(round(band, 4), abs=1e-4)      # the general read is unchanged
    assert world.speed_factor(name, "chop") == pytest.approx(round(band, 4), abs=1e-4)


def test_a_stamina_cost_tagged_with_an_action_is_divided_by_that_actions_stamina_factor(town):
    """An Effort spent on a push (back stamina) costs more with a back injury; one spent on a chop does not."""
    world = town.world
    name = _adult(world)
    node = world._actors[name]
    body = world._bodies[name]

    def spend(action):
        # Hunger scales every effort's cost (Phase 022), so each spend starts from no hunger.
        world.eng.set_attr(node, "hunger", 0.0)
        # The reserve is clamped to the whole-body stamina cap (Phase 032), which a back injury lowers, so start each
        # spend at that cap and measure the drop.
        world.eng.set_attr(body, "stamina_reserve", float(world.effective_stamina(name)))
        start = float(world.eng.node(body)["attrs"].get("stamina_reserve", 0.0))
        world._queue_effort(name, 0.1, 0.1, action=action)
        world._run()
        return start - float(world.eng.node(body)["attrs"].get("stamina_reserve", 0.0))

    base_push = spend("push")
    base_chop = spend("chop")
    assert base_push == pytest.approx(base_chop, rel=1e-6)
    _injure(world, name, "back", 0.4)
    injured_push = spend("push")
    injured_chop = spend("chop")
    assert injured_push > base_push
    assert injured_chop == pytest.approx(base_chop, rel=1e-6)
