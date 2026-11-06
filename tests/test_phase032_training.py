"""Phase 032: use trains the body.

Each stat-using effort raises the trained strength or stamina it uses (seeds bd_train_strength and
bd_train_stamina): intensity x TRAIN_RATE x (base x TRAIN_HEADROOM - trained), so gains diminish toward the
ceiling. Effective strength and stamina are (base + trained) x health (bd_effective_stats), the reserve is
clamped to the effective stamina, and a heavy recipe's strength requirement gates it. The `training` switch
turns the training off and nothing else.
"""
from __future__ import annotations

import pytest

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-9
KNIFE_COST = E.recipe_exertion("forge_knife")[1]      # 0.15 stamina per batch, strength 0.9
PLOUGH_STRENGTH, PLOUGH_COST = E.recipe_exertion("forge_plough")


def _smith(**world_kwargs):
    # The Phase 024 slowdown is off: these tests look at training, not at timing.
    w = World(exhaustion_slow_on=False, **world_kwargs)
    w.add_tradesperson("Smith", "smith")
    w.set_stock("iron", 2000)
    w.set_stock("charcoal", 2000)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))             # the forge's hammer and bellows are used at the forge
    return w


def _body(w, name):
    return w.eng.node(w._bodies[name])["attrs"]


def _mend_hammers(w):
    """Test scaffolding: a forge hammer wears by 0.02 a use and breaks at zero. Each batch here is the knife's
    declared cost, not a test of wear, so the hammers are restored before each batch."""
    for item in list(w.eng.nodes("ToolItem")):
        if w.eng.node(item)["attrs"].get("kind") == "hammer":
            w.eng.set_attr(item, "condition", 1.0)
            w.eng.set_attr(item, "broken", 0.0)


def _rest_and_forge_knife(w, name="Smith"):
    """One knife batch with the reserve and hunger held, so every batch is the declared cost, not a tired one."""
    w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors[name], "hunger", 0.0)
    _mend_hammers(w)
    assert w.do(name, "forge_knife")


def test_repeated_forging_raises_strength_with_diminishing_gains_toward_the_ceiling():
    w = _smith()
    ceiling = float(E.TRAIN_HEADROOM) * 1.0      # base 1.0 x TRAIN_HEADROOM, the trained component's ceiling
    gains, trained = [], 0.0
    for _ in range(200):
        _rest_and_forge_knife(w)
        now = float(_body(w, "Smith")["str_train"])
        assert now == pytest.approx(trained + E.train_gain(1.0, trained, KNIFE_COST), abs=TOL)
        gains.append(now - trained)
        trained = now
    assert all(later < earlier for earlier, later in zip(gains, gains[1:])), "each gain is smaller than the last"
    assert trained < ceiling and trained > 0.9 * ceiling, "after 200 batches the trained part is near the ceiling"
    assert w.strength("Smith") == pytest.approx(1.0 + trained, abs=1e-4), "effective strength is base + trained"
    assert float(_body(w, "Smith")["stats_dirty"]) == 0.0, "the stats rule clears its dirty flag"


def test_a_resident_trained_by_forging_can_attempt_a_recipe_that_was_above_them_at_the_start():
    w = _smith()
    assert not w.can_make("Smith", "forge_plough"), "a founding body (strength 1.0) is below the plough's 1.2"
    # Phase 049: the attempt itself is no refusal; a weak worker works slower and strains. The offer still withholds it.
    assert w.start("Smith", "forge_plough")
    assert w.strength("Smith") < PLOUGH_STRENGTH
    w.stop_job("Smith")
    needed = E.efforts_to_train(1.0, PLOUGH_STRENGTH, KNIFE_COST)   # knife batches to reach strength 1.2
    assert needed is not None and needed > 0
    for count in range(1, 200):
        _rest_and_forge_knife(w)
        if w.can_make("Smith", "forge_plough"):
            break
    assert count == needed, "the world's training matches the time-to-train count"
    assert w.strength("Smith") + 1e-9 >= PLOUGH_STRENGTH
    assert w.start("Smith", "forge_plough"), "the trained smith may now start the plough"


def test_a_low_health_body_has_lower_effective_strength_and_stamina():
    w = World(autonomous_actors=False)
    w.add_actor("Ada", role="hand")
    body = w._bodies["Ada"]
    w.eng.set_attr(body, "str_train", 0.2)
    w.eng.set_attr(body, "sta_train", 0.1)
    w.eng.set_attr(w._actors["Ada"], "health_value", 0.5)   # Phase 037: health is the actor's health_value
    w._run()
    assert w.strength("Ada") == pytest.approx((1.0 + 0.2) * 0.5, abs=TOL)
    assert w.effective_stamina("Ada") == pytest.approx((1.0 + 0.1) * 0.5, abs=TOL)
    assert w.body_state("Ada")["stamina"] == pytest.approx(0.55, abs=1e-4)
    assert w.stamina_reserve("Ada") <= w.effective_stamina("Ada") + TOL, "the reserve cannot exceed the capacity"
    w.eng.set_attr(w._actors["Ada"], "health_value", 1.0)
    w._run()
    assert w.strength("Ada") == pytest.approx(1.2, abs=TOL), "health back to full restores the potential"


def test_a_low_health_smith_forges_a_knife_at_a_cost_until_healthy():
    # Phase 049: below the knife's strength demand the forging goes on at a cost (the stamina cost ratio); it is no refusal.
    w = _smith()
    w.eng.set_attr(w._actors["Smith"], "health_value", 0.5)     # effective strength 0.5 is below the knife's 0.9
    assert w.strength("Smith") < float(E.recipe_exertion("forge_knife")[0])
    before = w.stamina_reserve("Smith")
    assert w.do("Smith", "forge_knife"), "a weak smith may still forge"
    assert w.stamina_reserve("Smith") < before, "the weak forging spends stamina"
    w.eng.set_attr(w._actors["Smith"], "health_value", 1.0)
    assert w.do("Smith", "forge_knife")


def test_exertion_counts_the_capacity_a_training_effort_adds():
    w = _smith()
    for _ in range(3):                           # trained stamina is above zero, so the capacity is above 1.0
        _rest_and_forge_knife(w)
    trained = float(_body(w, "Smith")["sta_train"])
    assert trained > 0.0
    w.eng.set_attr(w._bodies["Smith"], "stamina_reserve", w.effective_stamina("Smith"))
    w.eng.set_attr(w._actors["Smith"], "hunger", 0.0)
    _mend_hammers(w)
    assert w.do("Smith", "forge_knife")
    gain = E.train_gain(1.0, trained, KNIFE_COST)
    assert w.exertion("Smith") == pytest.approx(KNIFE_COST + gain, abs=1e-4), \
        "the deficit below capacity: the spend, plus the capacity this same effort trains"


def test_training_off_changes_nothing_in_the_body():
    w = _smith(physical_subsystems={"training": False})
    for _ in range(30):
        _rest_and_forge_knife(w)
    body = _body(w, "Smith")
    assert float(body["str_train"]) == 0.0 and float(body["sta_train"]) == 0.0
    assert w.strength("Smith") == pytest.approx(1.0, abs=TOL)
    assert not w.can_make("Smith", "forge_plough"), "with no training the plough stays closed to a base-1.0 body"


def test_walking_trains_stamina_through_the_movement_effort_and_only_when_on():
    for on in (True, False):
        w = World(autonomous_actors=False, physical_subsystems={"training": on})
        cells = sorted(w._map_cells)
        w.add_actor("Ada", role="hand", home_cell=cells[len(cells) // 2])
        here = w.actor_position("Ada")
        dest = next(c for c in sorted(w._map_cells) if c != here and w.distance(here, c) == 1)
        w.actor_tick("Ada")
        assert w.major_action("Ada", "move", destination=dest)
        trained = float(_body(w, "Ada")["sta_train"])
        if on:
            assert trained > 0.0, "a step is an effort that uses stamina, so it trains stamina"
        else:
            assert trained == 0.0


def test_a_timed_plough_trains_strength_in_its_ticks():
    w = _smith()
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)   # strong enough for the plough from the start
    w.eng.set_attr(w._actors["Smith"], "hunger", 0.0)
    assert w.start("Smith", "forge_plough")
    for _ in range(40):
        if not w.busy("Smith"):
            break
        w.eng.set_attr(w._actors["Smith"], "hunger", 0.0)
        w.eng.set_attr(w._bodies["Smith"], "stamina_reserve", 1.0)
        w.tick(1)
    assert not w.busy("Smith") and w.newest_tool() is not None
    trained = float(_body(w, "Smith")["str_train"])
    assert 0.0 < trained < float(E.TRAIN_HEADROOM) * 1.3, "the plough's ticks trained strength below the ceiling"


def test_the_contest_force_reads_the_effective_strength():
    w = World(autonomous_actors=False)
    w.add_actor("Ada", role="hand")
    base = w._contest_side("Ada")["force"]
    w.eng.set_attr(w._bodies["Ada"], "str_train", 0.2)
    trained = w._contest_side("Ada")["force"]
    assert trained / base == pytest.approx(1.2, abs=1e-9), "the contest's force scales with (base + trained)"


def test_the_time_to_train_helper_gives_the_plough_count_and_refuses_the_unreachable():
    assert E.efforts_to_train(1.0, 1.0, 0.4) == 0, "no training is needed to reach what the body has"
    assert E.efforts_to_train(1.0, 1.2, PLOUGH_COST) == 15, "the plough's count from a founding body (see self-test)"
    assert E.efforts_to_train(1.0, 1.0 + float(E.TRAIN_HEADROOM) + 0.01, 0.4) is None, "above the ceiling"
    assert E.efforts_to_train(1.0, 1.2, 0.0) is None, "no intensity, no training"
