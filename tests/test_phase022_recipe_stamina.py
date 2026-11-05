"""Phase 022: recipe stamina is spent.

A recipe's declared stamina cost (RECIPE_EXERTION) is charged through the same Effort mechanism movement
uses: spread evenly over the ticks of a timed job, or charged at completion for an instant `do`. The
reserve never falls below 0. Exertion raises hunger by HUNGER_PER_STAMINA per unit spent, and a hungrier
resident spends more (declared cost x (1 + hunger / starve_limit)). The balance model carries a stamina
line for the founding town.
"""
from __future__ import annotations

import math

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-9


def _recipe_ticks(name):
    minutes = float(next(r for r in E.RECIPES if r["name"] == name)["time_minutes"])
    return int(math.ceil(minutes / float(E.TIME["minutes_per_tick"])))


def _smith():
    # Built with the Phase 024 slowdown off: these tests predate it and assert full-speed job timing.
    # The slowdown itself is tested in tests/test_phase024_exhaustion.py.
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))            # the forge's tools are used at the forge
    return w


def _set_hunger(w, name, value):
    w.eng.set_attr(w._actor(name), "hunger", float(value))


def _reserve(w, name):
    return w.stamina_reserve(name)


def test_forging_a_plough_spends_its_declared_stamina_evenly_over_the_job():
    w = _smith()
    declared = E.recipe_exertion("forge_plough")[1]
    ticks = _recipe_ticks("forge_plough")
    assert declared > 0 and ticks > 1
    start = _reserve(w, "Smith")
    w.start("Smith", "forge_plough")
    drops = []
    for _ in range(ticks):
        before = _reserve(w, "Smith")
        _set_hunger(w, "Smith", 0.0)             # hold hunger at zero so each tick is the declared share
        w.tick(1)
        drops.append(before - _reserve(w, "Smith"))
    assert not w.busy("Smith") and w.newest_tool() is not None, "the plough is finished"
    assert all(abs(d - declared / ticks) < TOL for d in drops), drops
    assert abs((start - _reserve(w, "Smith")) - declared) < TOL, "the reserve fell by the declared cost"


def test_an_instant_craft_charges_its_stamina_at_completion_and_raises_hunger():
    w = _smith()
    declared = E.recipe_exertion("forge_plough")[1]
    start = _reserve(w, "Smith")
    w.do("Smith", "forge_plough")
    assert w.newest_tool() is not None
    assert abs((start - _reserve(w, "Smith")) - declared) < TOL
    assert abs(w.hunger("Smith") - declared * float(E.HUNGER_PER_STAMINA)) < TOL, "exertion makes you hungrier"
    assert abs(w.fatigue("Smith") - declared) < TOL, "fatigue is the stamina spent (a read-off)"


def test_a_light_recipe_leaves_the_reserve_unchanged():
    w = World()
    w.add_tradesperson("Baker", "baker")
    w.set_stock("flour", 50)
    w.set_stock("water", 30)
    w.set_stock("wood", 10)
    assert E.recipe_exertion("bake_bread") == (0.0, 0.0)
    start = _reserve(w, "Baker")
    w.do("Baker", "bake_bread")
    assert w.qty("bread") == 60.0
    assert _reserve(w, "Baker") == start and w.hunger("Baker") == 0.0


def test_the_reserve_never_goes_below_zero():
    w = _smith()
    w.eng.set_attr(w._bodies["Smith"], "stamina_reserve", 0.1)     # less than the plough's 0.4
    w.start("Smith", "forge_plough")
    collapsed_during_job = False
    for _ in range(_recipe_ticks("forge_plough") + 2):
        _set_hunger(w, "Smith", 0.0)
        w.tick(1)
        assert _reserve(w, "Smith") >= 0.0
        collapsed_during_job = collapsed_during_job or w.collapsed("Smith")
    # Phase 024: below e_collapse (0.05) the worker collapses and sleeps, so a timed job does not drive the
    # reserve to zero. The job waits while the worker is down. The floor at zero held in the loop above.
    assert collapsed_during_job

    v = _smith()
    v.eng.set_attr(v._bodies["Smith"], "stamina_reserve", 0.1)
    v.do("Smith", "forge_plough")
    assert _reserve(v, "Smith") == 0.0


def test_a_hungry_worker_spends_more_stamina_for_the_same_work():
    w = _smith()
    declared = E.recipe_exertion("forge_plough")[1]
    starve = float(w.eng.node(w._actor("Smith"))["attrs"]["starve_limit"])
    assert starve == float(E.CARE["starve_limit"])
    _set_hunger(w, "Smith", starve / 2.0)         # half way to starving: cost x 1.5
    start = _reserve(w, "Smith")
    w.do("Smith", "forge_plough")
    spent = start - _reserve(w, "Smith")
    assert abs(spent - declared * 1.5) < TOL, spent
    assert abs(w.hunger("Smith") - (starve / 2.0 + spent * float(E.HUNGER_PER_STAMINA))) < TOL


def test_movement_is_scaled_by_hunger_and_raises_hunger_too():
    def walk(hunger):
        w = World(autonomous_actors=False)
        w.add_actor("Walker", role="hand", home_cell=(1, 1))
        _set_hunger(w, "Walker", hunger)
        start = _reserve(w, "Walker")
        w.move_actor("Walker", (3, 1))
        return start - _reserve(w, "Walker"), w.hunger("Walker")

    fed_spent, fed_hunger = walk(0.0)
    hungry_spent, hungry_hunger = walk(2.0)
    assert fed_spent > 0.0
    assert abs(hungry_spent - fed_spent * 1.5) < TOL, (fed_spent, hungry_spent)
    assert abs(fed_hunger - fed_spent * float(E.HUNGER_PER_STAMINA)) < TOL
    assert abs(hungry_hunger - (2.0 + hungry_spent * float(E.HUNGER_PER_STAMINA))) < TOL


def test_the_balance_model_has_a_stamina_line_and_flags_a_town_that_overworks_its_rest():
    flows, notes, _work = E._balance_flows(E.BALANCE_SCENARIO)
    supply, demand = flows["stamina (per resident)"]
    assert 0.0 <= demand < supply, "the founding town's labour spends less stamina than its rest can restore"
    assert any(note.startswith("stamina:") for note in notes)
    assert "stamina (per resident)" in E.format_systems_report(E.analyse_systems())

    # 300 food per resident gives more labour per resident than the day holds, so no rest is left.
    overworked = dict(E.BALANCE_SCENARIO, food_per_resident=300.0)
    flows, _notes, _work = E._balance_flows(overworked)
    supply, demand = flows["stamina (per resident)"]
    assert demand > 0.0 and supply < demand, "a labour demand the day cannot hold is flagged"
