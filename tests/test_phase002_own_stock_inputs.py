"""Phase 002: recipe inputs are drawn from the worker's own stock, then accessible containers at
the worker's cell, then the town store. The affordance check uses the same plan the job runs."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld as World      # noqa: E402

FUEL_KINDS = ("wood", "straw", "dung", "peat", "charcoal")


def _baker(w, *, flour_own=0.0, flour_store=0.0, water_store=20.0, wood_store=6.0):
    w.add_actor("Baker", role="baker", skill=1.0)
    if flour_own:
        w.set_stock("flour", flour_own)
        assert w.fetch("Baker", "flour", flour_own)          # store -> her own inventory
    w.set_stock("flour", flour_store)
    w.set_stock("water", water_store)
    w.set_stock("wood", wood_store)
    return w


def _bin_with(w, name, kind, amount, cell, *, locked=False, holds=("flour",), actor="Baker"):
    """A container holding `amount` of `kind` at `cell`. `fill` draws on the town store and only
    fills a container the actor stands on, so the helper stocks the store, stands the actor at the
    cell, fills, then locks it and returns the actor to where they were. The bin holds the units."""
    before = w.actor_position(actor)
    w.set_stock(kind, amount)
    w.add_container(name, kind="barrel", holds=list(holds), cell=cell)
    w._move_actor_to(actor, cell)
    assert w.fill(actor, name, kind, amount)
    w.set_stock(kind, 0.0)
    if locked:
        w.eng.set_attr(w._containers[name][0], "locked", 1.0)
    if before is not None:
        w._move_actor_to(actor, before)
    assert w.contents(name, kind) == amount


def _last_job(w):
    return list(w.eng.nodes("Job"))[-1]


def _need(w, job, kind):
    for need in w.eng.neighbours(job, "need"):
        attrs = w.eng.node(need)["attrs"]
        if attrs.get("kind") == kind:
            return attrs
    raise AssertionError(f"no need for {kind}")


def test_baker_bakes_from_her_own_flour_and_the_store_flour_is_untouched():
    w = _baker(World(), flour_own=40.0, flour_store=100.0)
    assert w.inventory_qty("Baker", "flour") == 40.0 and w.qty("flour") == 100.0
    bread = w.qty("bread")

    assert w.do("Baker", "bake_bread")

    assert w.qty("bread") == bread + 60.0, "the bake completed"
    assert w.inventory_qty("Baker", "flour") == 0.0, "her own 40 flour went into the bread"
    assert w.qty("flour") == 100.0, "the store's flour was not drawn on"
    job = _last_job(w)
    assert _need(w, job, "flour")["drawn_from"] == "flour:own=40.0"
    assert _need(w, job, "water")["drawn_from"] == "water:store=20.0"


def test_baker_with_no_flour_held_bakes_from_the_store():
    w = _baker(World(), flour_store=100.0)
    assert w.do("Baker", "bake_bread")
    assert w.qty("flour") == 60.0
    assert _need(w, _last_job(w), "flour")["drawn_from"] == "flour:store=40.0"


def test_own_flour_is_used_before_the_store_and_the_remainder_comes_from_the_store():
    w = _baker(World(), flour_own=15.0, flour_store=100.0)
    assert w.do("Baker", "bake_bread")
    assert w.inventory_qty("Baker", "flour") == 0.0
    assert w.qty("flour") == 75.0
    assert _need(w, _last_job(w), "flour")["drawn_from"] == "flour:own=15.0;flour:store=25.0"


def test_bought_firewood_held_by_a_cook_is_burnt_by_their_own_cooking():
    w = World()
    w.add_actor("Cook", role="cook", skill=1.0)
    w.set_stock("grain", 1.0)
    w.set_stock("water", 2.0)
    for kind in FUEL_KINDS:                       # the store holds no fuel, only what the cook carries
        w.set_stock(kind, 0.0)
    w.set_stock("wood", 5.0)
    assert w.fetch("Cook", "wood", 5.0)
    assert w.inventory_qty("Cook", "wood") == 5.0 and w.qty("wood") == 0.0

    assert w.do("Cook", "make_gruel")

    assert w.inventory_qty("Cook", "wood") == 4.0, "one unit of the cook's own firewood was burnt"
    assert w.qty("wood") == 0.0
    fuel = _need(w, _last_job(w), "fuel")
    assert fuel["drawn_from"] == "wood:own=1.0"
    assert fuel["filled_with"] == "wood:1.0"


def test_a_container_at_the_workers_cell_supplies_flour_when_the_inventory_lacks_it():
    w = _baker(World(), flour_store=0.0)
    cell = (0, 0)
    w._move_actor_to("Baker", cell)
    _bin_with(w, "bin_by_oven", "flour", 40.0, cell)
    assert w._recipe_inputs_available("bake_bread", "Baker")

    assert w.do("Baker", "bake_bread")

    assert w.contents("bin_by_oven", "flour") == 0.0
    assert _need(w, _last_job(w), "flour")["drawn_from"] == "flour:box:bin_by_oven=40.0"


def test_an_inaccessible_container_at_the_cell_does_not_supply_input():
    w = _baker(World(), flour_store=0.0)
    cell = (0, 0)
    w._move_actor_to("Baker", cell)
    _bin_with(w, "locked_bin", "flour", 40.0, cell, locked=True)
    assert not w._recipe_inputs_available("bake_bread", "Baker")

    bread = w.qty("bread")
    w.do("Baker", "bake_bread")

    assert w.qty("bread") == bread, "the bake did not complete"
    assert w.contents("locked_bin", "flour") == 40.0, "the locked container was not drawn on"


def test_a_container_elsewhere_does_not_supply_input_even_if_unlocked():
    w = _baker(World(), flour_store=0.0)
    w._move_actor_to("Baker", (0, 0))
    _bin_with(w, "far_bin", "flour", 40.0, (1, 0))
    assert not w._recipe_inputs_available("bake_bread", "Baker")
    bread = w.qty("bread")
    w.do("Baker", "bake_bread")
    assert w.qty("bread") == bread and w.contents("far_bin", "flour") == 40.0


def test_the_affordance_check_agrees_with_what_the_job_draws():
    scenarios = {
        "own flour covers the recipe": dict(flour_own=40.0),
        "own flour falls one short": dict(flour_own=39.0),
        "store flour covers the recipe": dict(flour_store=40.0),
        "no flour anywhere": dict(),
        "water short by one": dict(flour_own=40.0, water_store=19.0),
        "water from the store, flour in a bin at the cell": dict(bin_flour=40.0),
        "flour in a locked bin at the cell": dict(locked_bin_flour=40.0),
        "flour in a bin on another cell": dict(far_bin_flour=40.0),
    }
    for label, spec in scenarios.items():
        w = _baker(World(), flour_own=spec.get("flour_own", 0.0), flour_store=spec.get("flour_store", 0.0),
                   water_store=spec.get("water_store", 20.0))
        w._move_actor_to("Baker", (0, 0))
        if "bin_flour" in spec:
            _bin_with(w, "bin", "flour", spec["bin_flour"], (0, 0))
        if "locked_bin_flour" in spec:
            _bin_with(w, "bin", "flour", spec["locked_bin_flour"], (0, 0), locked=True)
        if "far_bin_flour" in spec:
            _bin_with(w, "bin", "flour", spec["far_bin_flour"], (1, 0))
        affordable = w._recipe_inputs_available("bake_bread", "Baker")
        bread = w.qty("bread")
        w.do("Baker", "bake_bread")
        ran = w.qty("bread") == bread + 60.0
        assert affordable == ran, f"{label}: affordance {affordable} but the job ran {ran}"


def test_two_timed_jobs_cannot_both_count_the_same_units():
    w = World()
    cell = (0, 0)
    for name in ("Ana", "Ben"):
        w.add_actor(name, role="baker", skill=1.0)
        w._move_actor_to(name, cell)
    _bin_with(w, "shared_bin", "flour", 40.0, cell, actor="Ana")
    w.set_stock("water", 40.0)
    w.set_stock("wood", 12.0)

    # Both see the 40 flour as available, so both jobs open against it.
    assert w._recipe_inputs_available("bake_bread", "Ana")
    assert w._recipe_inputs_available("bake_bread", "Ben")
    assert w.start("Ana", "bake_bread") and w.start("Ben", "bake_bread")

    w.tick(12)                                   # 120 minutes at 15 minutes a tick, with margin
    assert w.qty("bread") == 60.0, "only one bake can draw the 40 flour"
    assert w.contents("shared_bin", "flour") == 0.0
    jobs = list(w.eng.nodes("Job"))
    complete = [j for j in jobs if w.eng.node(j)["attrs"].get("complete") == 1.0]
    assert len(complete) == 1
    assert w.busy("Ana") != w.busy("Ben"), "the second baker still waits for flour"
