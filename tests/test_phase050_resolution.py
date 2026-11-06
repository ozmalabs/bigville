"""Phase 050: the resolution core in the world. An `attempt` is one rule for any verb, target and tool.

Covered: the refusals that cost nothing (unsupported verb, out of reach, no tool, no lock, broken target); damage
that accumulates until a container breaks; a locked container opened by strength and a tool that fits, and not by
a frail resident with a spoon; a half-worn lock opening sooner; intensity clamped to the ceiling, costing more
than twice at twice the level, and building strain past the safe level; noise heard within the radius only;
wood against iron breaking the tool sooner; the recipe cost term, unchanged at the gate and raised when strength
falls mid-job; native verbs routed to the world's own actions; and a backend's default intensity.
"""
from __future__ import annotations

import math

import pytest

from bigville.backends.cheap import SimplePolicy
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-9


def _cells(w):
    return sorted(w._map_cells)


def _world(*, strength=1.0, lock_id=0, locked=False, kind="chest", tool=None, actor="Ada"):
    w = World(autonomous_actors=False)
    cells = _cells(w)
    w.add_actor(actor, role="hand", home_cell=cells[len(cells) // 2])
    if strength != 1.0:
        w.eng.set_attr(w._bodies[actor], "str_base", float(strength))
    here = w.actor_position(actor)
    w.add_container("box", kind=kind, holds=["grain"], lock_id=lock_id, locked=locked, cell=here)
    if tool is not None:
        w.give_tool(actor, tool)
    return w


def _box(w):
    return w.eng.node(w._containers["box"][0])["attrs"]


def _reserve(w, name="Ada"):
    return w.stamina_reserve(name)


def _reason(w, name="Ada"):
    return w.last_outcome(name)["reason"]


def _turn(w, name="Ada"):
    w.actor_tick(name)


def _fresh_body(w, name="Ada"):
    """Set the reserve back to full and wake the resident. For tests that isolate one thing from exhaustion."""
    node = w._actors[name]
    w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
    w.eng.set_attr(node, "collapsed", 0.0)
    w.eng.set_attr(node, "asleep", 0.0)


# ------------------------------------------------------------------ refusals: the only "no" the world says

def test_a_verb_the_world_has_no_physics_for_is_unsupported_and_costs_nothing():
    w = _world(tool="hammer")
    before = _reserve(w)
    assert w.major_action("Ada", "attempt", verb="bind", target="box", with_kind="hammer") is False
    assert _reason(w) == "unsupported"
    assert _reserve(w) == before
    assert w.eng.node(w._actors["Ada"])["attrs"].get("major_action_used", 0.0) == 0.0


def test_a_physical_verb_without_an_implemented_primitive_is_unsupported():
    w = _world(tool="hammer")
    # Phase 050b: push is implemented now, so the unimplemented example is lift (still refused as unsupported).
    assert w.major_action("Ada", "attempt", verb="lift", target="box") is False
    assert _reason(w) == "unsupported"


def test_a_target_out_of_reach_is_refused():
    w = _world(tool="hammer")
    here = w.actor_position("Ada")
    far = next(c for c in _cells(w) if max(abs(c[0] - here[0]), abs(c[1] - here[1])) >= 3)
    w.container_position = lambda name: far
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is False
    assert _reason(w) == "not_in_reach"


def test_a_tool_the_actor_does_not_hold_is_refused_as_no_tool():
    w = _world()
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is False
    assert _reason(w) == "no_tool"


def test_opening_a_container_with_no_lock_is_refused():
    w = _world(tool="hammer")
    assert w.major_action("Ada", "attempt", verb="pry", target="box", with_kind="hammer") is False
    assert _reason(w) == "no_lock"


def test_a_malformed_intensity_is_refused():
    w = _world(tool="hammer")
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer",
                          intensity="hard") is False
    assert _reason(w) == "malformed"


def test_an_attempt_uses_the_action_slot_and_a_second_one_in_the_turn_is_refused():
    w = _world(tool="hammer")
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is False
    assert _reason(w) == "slot_used"


# ------------------------------------------------------------------ damage: smashing a chest

def test_smashing_a_wooden_chest_damages_it_each_attempt_until_it_breaks_and_then_it_is_refused():
    # Phase 048: a hammer's fitness is its quality x condition, and its wear rises as its fit falls. So a hammer
    # that has worn down stops progressing before it breaks; the attempts that follow do no damage and the hammer
    # still wears out. Attempts damage the chest while the hammer is sound.
    w = _world(tool="hammer")
    falls = []
    for _ in range(60):
        _turn(w)
        before = _box(w)["structure"]
        assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True
        falls.append(before - _box(w)["structure"])
        if _box(w)["destroyed"] == 1.0:
            break
    assert _box(w)["destroyed"] == 1.0, "the chest breaks"
    assert falls[0] > 0.0 and all(d > 0.0 for d in falls[:5]), "the first attempts damage it"
    assert any(d == 0.0 for d in falls), "a worn hammer makes no progress (Phase 048)"
    assert w.last_attempt("Ada")["outcome"] == "broke"
    _turn(w)
    _fresh_body(w)              # a worn hammer costs more stamina (Phase 048); rest, so the reason is the chest's
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is False
    assert _reason(w) == "destroyed"
    assert w._container_accessible("Ada", "box") is False, "a broken container is not opened"


def test_the_attempt_reports_what_the_actor_saw_and_not_the_capability_or_the_demand():
    w = _world(tool="hammer")
    _turn(w)
    w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=1.0)
    seen = w.last_attempt("Ada")
    assert {"progress", "damage", "applied_intensity", "clamped", "outcome", "tool"} <= set(seen)
    assert not {"capability", "demand", "rho", "fit", "force"} & set(seen)


def test_a_smash_is_heard_by_a_resident_within_the_radius_and_not_by_one_far_away():
    w = _world(tool="hammer")
    here = w.actor_position("Ada")
    near = next(c for c in _cells(w) if max(abs(c[0] - here[0]), abs(c[1] - here[1])) == 2)
    far = next(c for c in _cells(w) if max(abs(c[0] - here[0]), abs(c[1] - here[1])) >= 10)
    w.add_actor("Bob", role="hand", home_cell=near)
    w.add_actor("Cy", role="hand", home_cell=far)
    w._move_actor_to("Bob", near)
    w._move_actor_to("Cy", far)
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=1.0)
    heard = {name: any(w.eng.node(e)["attrs"].get("kind") == "noise"
                       for e in w.eng.neighbours(w._actors[name], "observed_event"))
             for name in ("Bob", "Cy")}
    assert heard == {"Bob": True, "Cy": False}


# ------------------------------------------------------------------ open: forcing a locked container

def test_a_strong_resident_with_a_hammer_forces_a_locked_chest_without_a_key():
    w = _world(strength=1.3, lock_id=7, locked=True, tool="hammer")
    opened_on = None
    for attempt in range(1, 6):
        _turn(w)
        assert w.major_action("Ada", "attempt", verb="force", target="box", with_kind="hammer") is True
        if _box(w)["locked"] == 0.0:
            opened_on = attempt
            break
    assert opened_on is not None and opened_on <= 3
    assert w.last_attempt("Ada")["outcome"] == "opened"


def test_a_frail_resident_with_a_spoon_makes_no_progress_and_breaks_the_spoon():
    w = _world(strength=0.5, lock_id=7, locked=True, tool="wooden_serving_spoon")
    for _ in range(6):
        _turn(w)
        _fresh_body(w)
        w.major_action("Ada", "attempt", verb="pry", target="box", with_kind="wooden_serving_spoon")
        if _box(w)["locked"] == 0.0:
            break
    assert _box(w)["locked"] == 1.0, "the lock holds"
    assert w.last_attempt("Ada")["progress"] == 0.0
    spoon = w.eng.neighbours(w._actors["Ada"], "holds")[0]
    assert w.eng.node(spoon)["attrs"]["broken"] == 1.0, "the spoon breaks"


def test_a_half_worn_lock_opens_in_fewer_attempts_than_a_fresh_one():
    counts = []
    for worn in (1.0, 0.5):
        w = _world(strength=0.9, lock_id=7, locked=True, tool="hammer")
        w.eng.set_attr(w._containers["box"][0], "lock_condition", worn)
        n = 0
        for _ in range(20):
            _turn(w)
            w.major_action("Ada", "attempt", verb="force", target="box", with_kind="hammer")
            n += 1
            if _box(w)["locked"] == 0.0:
                break
        counts.append(n)
    assert counts[1] < counts[0], counts


def test_wood_against_iron_at_intensity_three_breaks_the_spoon_sooner_and_changes_nothing_else():
    attempts = []
    for level in (1.0, 3.0):
        w = _world(strength=1.0, lock_id=7, locked=True, tool="wooden_serving_spoon")
        spoon = w.eng.neighbours(w._actors["Ada"], "holds")[0]
        n = 0
        for _ in range(20):
            _turn(w)
            _fresh_body(w)   # isolate the tool's wear from exhaustion
            w.major_action("Ada", "attempt", verb="pry", target="box", with_kind="wooden_serving_spoon",
                           intensity=level)
            n += 1
            if w.eng.node(spoon)["attrs"]["broken"] == 1.0:
                break
        assert _box(w)["locked"] == 1.0
        attempts.append(n)
    assert attempts[1] < attempts[0], attempts


# ------------------------------------------------------------------ intensity (conviction)

def test_an_intensity_above_the_ceiling_is_clamped_and_the_applied_value_is_reported():
    w = _world(tool="hammer")
    _turn(w)
    w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=5.0)
    seen = w.last_attempt("Ada")
    assert seen["clamped"] is True
    assert seen["applied_intensity"] == float(E.RESOLUTION["max_intensity"])
    assert seen["requested_intensity"] == 5.0


def test_a_spent_reserve_lowers_the_ceiling_to_nothing():
    w = _world(tool="hammer")
    w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 0.1)
    _turn(w)
    w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=2.0)
    seen = w.last_attempt("Ada")
    assert seen["applied_intensity"] == 0.0 and seen["clamped"] is True
    assert seen["progress"] == 0.0


def test_twice_the_intensity_costs_more_than_twice_the_stamina():
    spent = {}
    for level in (1.0, 2.0):
        w = _world(tool="hammer")
        _turn(w)
        start = _reserve(w)
        w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=level)
        spent[level] = start - _reserve(w)
    assert spent[1.0] > 0.0
    assert spent[2.0] > 2.0 * spent[1.0]


def test_twice_the_intensity_damages_more_per_attempt_and_is_louder():
    drop, loudness = {}, {}
    for level in (1.0, 2.0):
        w = _world(tool="hammer")
        _turn(w)
        before = _box(w)["structure"]
        w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=level)
        drop[level] = before - _box(w)["structure"]
        noise = [w.eng.node(e)["attrs"] for e in w._events.values() if w.eng.node(e)["attrs"].get("kind") == "noise"]
        loudness[level] = noise[-1]["severity"]
    assert drop[2.0] > drop[1.0] > 0.0
    assert loudness[2.0] > loudness[1.0]


def test_an_intensity_above_the_safe_level_strains_and_a_full_strain_is_an_accident():
    w = _world(tool="hammer")
    _turn(w)
    w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=3.0)
    assert w.eng.node(w._actors["Ada"])["attrs"].get("last_cause") == "accident"
    assert w.health("Ada") < 1.0
    assert w.eng.node(w._actors["Ada"])["attrs"]["strain"] == 0.0, "the accident resets the strain"


def test_a_gentle_attempt_is_not_overexertion_and_does_not_hurt_the_resident():
    w = _world(strength=1.3, tool="hammer")
    _turn(w)
    w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=0.5)
    strain = w.eng.node(w._actors["Ada"])["attrs"].get("strain", 0.0)
    assert strain < float(E.RESOLUTION["strain_limit"])
    assert w.health("Ada") == 1.0


def test_the_same_attempts_in_two_worlds_give_the_same_result():
    results = []
    for _ in range(2):
        w = _world(tool="hammer")
        for _ in range(4):
            _turn(w)
            w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=1.2)
        results.append((_box(w)["structure"], _reserve(w), w.last_attempt("Ada")))
    assert results[0] == results[1]


# ------------------------------------------------------------------ the recipe term (Phase 022/023 adopted)

def _smith_job():
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    return w


def test_a_worker_whose_strength_falls_mid_job_pays_more_than_the_declared_cost():
    declared = E.recipe_exertion("forge_plough")[1]
    spent = {}
    ratio = 1.2 / (1.3 * 0.8)   # the plough's strength demand over the smith's strength at health 0.8
    for drop in (False, True):
        w = _smith_job()
        # Stamina capacity is raised so that the drop in health does not also clamp the reserve (Phase 032).
        w.eng.set_attr(w._bodies["Smith"], "sta_base", 3.0)
        w.start("Smith", "forge_plough")
        start = w.stamina_reserve("Smith")
        for tick in range(40):
            if drop and tick == 1:
                w.eng.set_attr(w._actors["Smith"], "health_value", 0.8)   # strength 1.3 x 0.8 < the plough's 1.2
            w.eng.set_attr(w._actors["Smith"], "hunger", 0.0)
            w.tick(1)
            if not w.busy("Smith"):
                break
        spent[drop] = start - w.stamina_reserve("Smith")
    assert abs(spent[False] - declared) < TOL
    assert spent[True] > declared + 0.03, spent
    assert spent[True] < declared * ratio + 0.01, spent


# ------------------------------------------------------------------ native verbs, counts, and the backend default

def test_a_native_verb_routes_to_the_world_action_it_names():
    w = _world()
    w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 0.3)
    before = _reserve(w)
    assert w.enact_plan("Ada", {"action": "attempt", "verb": "rest"}) is True
    assert _reserve(w) > before


def test_a_native_verb_with_no_route_is_unsupported():
    w = _world()
    assert w.enact_plan("Ada", {"action": "attempt", "verb": "cook"}) is False
    assert _reason(w) == "unsupported"


def test_attempts_are_counted_by_verb_and_outcome_and_reported():
    from bigville.reporting import SimulationReporter
    w = _world(tool="hammer")
    for _ in range(2):
        _turn(w)
        w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer")
    counts = SimulationReporter(w).attempts_by_verb()
    assert sum(counts["smash"].values()) == 2


def test_the_simple_backend_defaults_to_intensity_one_and_escalates_only_after_its_span():
    policy = SimplePolicy()
    assert policy.escalated_intensity(1.0, 1000) == 1.0, "escalation is off by default"
    on = SimplePolicy(escalate_after_ticks=3, escalate_step=0.5)
    assert on.escalated_intensity(1.0, 2) == 1.0
    assert on.escalated_intensity(1.0, 3) == 1.5


def test_the_resolution_tables_name_the_lock_strength_and_the_accident_cause():
    assert E.CONTAINERS["chest"]["lock_strength"] > 0.0
    assert E.STORE_LOCK["lock_strength"] > 0.0
    assert "accident" in E.HEALTH["causes"]
    assert math.isfinite(E.RESOLUTION["max_intensity"])


# ---------------------------------------------------------------- Phase 050b: displace, spill, pace, slot, strain

def _ground_world(strength=1.0, mass=100.0, gap=1, tool=None):
    """A resident on a map cell with a physical object (a cart of `mass` weight units) `gap` cells east of them,
    on ground that lets a cell through. Returns (world, resident's cell). `tool` is a kind the resident holds
    (Phase 048: bare hands fit a push at 0.05, so the cart tests hold a wagon, whose haul fits a push at 0.6)."""
    w = World(autonomous_actors=False)
    cell = next(c for c in _cells(w) if (c[0] + 1, c[1]) in w._map_cells and (c[0] + 2, c[1]) in w._map_cells
                and w.terrain_state(c)["speed"] > 0 and w.terrain_state((c[0] + 1, c[1]))["speed"] > 0
                and w.terrain_state((c[0] + 2, c[1]))["speed"] > 0)
    w.add_actor("Ada", role="hand", home_cell=cell)
    w.eng.set_attr(w._bodies["Ada"], "str_base", float(strength))
    w._move_actor_to("Ada", cell)
    node = w.eng.add_node("PhysicalObject", {"object_id": "cart", "name": "cart", "kind": "cart", "location": "world",
                                              "mass": float(mass), "cell": [cell[0] + gap, cell[1]]})
    w._physical_objects["cart"] = node
    w._physical_object_locations["cart"] = "world"
    if tool is not None:
        w.give_tool("Ada", tool)
    return w, cell


def _cart_cell(w):
    return w._physical_location_cell("cart")


def test_a_strong_resident_pushes_a_cart_by_the_surplus_force():
    # Demand: 100 weight units over a push unit of 50, on grass (move time 1.0) = 2.0. Capability at intensity 3:
    # strength 4.0 x technique 0.5 (no labour skill) x intensity 3 x fit 0.6 (a wagon's haul against a push, Phase 048)
    # = 3.6. Surplus 1.6, so floor(1.6 x 2) = 3 cells, the most a push moves. The cart starts one cell east, so it
    # ends at cell + 4.
    w, cell = _ground_world(strength=4.0, tool="wagon")
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="push", target="cart", with_kind="wagon", intensity=3.0) is True
    assert _cart_cell(w) == (cell[0] + 4, cell[1])
    assert w.last_attempt("Ada")["cells_moved"] == 3
    assert w.last_attempt("Ada")["outcome"] == "moved"


def test_a_weak_resident_does_not_move_the_cart_even_at_full_force():
    # Capability 0.5 x 0.5 x 3 x 0.6 (the wagon's fit) = 0.45, below the demand of 2.0: no surplus, no movement.
    w, cell = _ground_world(strength=0.5, tool="wagon")
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="push", target="cart", with_kind="wagon", intensity=3.0) is True
    assert _cart_cell(w) == (cell[0] + 1, cell[1])
    assert w.last_attempt("Ada")["outcome"] == "stuck"
    assert w.last_attempt("Ada")["cells_moved"] == 0


def test_a_push_needs_the_object_next_to_the_resident():
    w, cell = _ground_world(strength=2.0)
    w.eng.set_attr(w._physical_objects["cart"], "cell", [cell[0] + 3, cell[1]])
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="push", target="cart", intensity=3.0) is False
    assert _reason(w) == "not_in_reach"


def test_a_pull_draws_the_cart_toward_the_resident_and_stops_short_of_them():
    # Two cells east, pulled west: the first cell is free, the second is the resident's own, so it stops there.
    w, cell = _ground_world(strength=4.0, gap=2, tool="wagon")
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="pull", target="cart", with_kind="wagon", intensity=3.0) is True
    assert _cart_cell(w) == (cell[0] + 1, cell[1])
    assert w.last_attempt("Ada")["cells_moved"] == 1


def test_a_verb_still_without_physics_is_refused_on_an_object():
    w, _cell = _ground_world(strength=2.0)
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="lift", target="cart") is False
    assert _reason(w) == "unsupported"


def test_a_trivial_attempt_costs_no_stamina_and_leaves_the_action_slot_unspent():
    # Strength 5: capability 5 x 0.5 = 2.5 against a wood chest's demand 0.5, a cost share of 0.2 (below 0.25).
    w = _world(strength=5.0, tool="hammer")
    _fresh_body(w)
    _turn(w)
    before = _reserve(w)
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True
    assert _reserve(w) == before
    assert w.actor_turn_state("Ada")["major_action_used"] is False
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True


def test_a_middling_attempt_spends_stamina_but_leaves_the_slot_unspent():
    # Strength 3: a cost share of 0.33, between trivial_below (0.25) and slot_above (0.5).
    w = _world(strength=3.0, tool="hammer")
    _fresh_body(w)
    _turn(w)
    before = _reserve(w)
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True
    assert _reserve(w) < before
    assert w.actor_turn_state("Ada")["major_action_used"] is False


def test_a_costly_attempt_claims_the_slot_and_a_second_is_refused():
    w = _world(strength=1.0, tool="hammer")
    _fresh_body(w)
    _turn(w)
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is True
    assert w.actor_turn_state("Ada")["major_action_used"] is True
    assert w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer") is False
    assert _reason(w) == "slot_used"


def test_a_broken_chest_spills_its_contents_on_its_cell():
    w = _world(strength=3.0, tool="hammer")
    _fresh_body(w)
    w.eng.set_attr(w._containers["box"][1]["grain"], "qty", 5.0)
    cell = w.container_position("box")
    for _ in range(80):
        _turn(w)
        w.major_action("Ada", "attempt", verb="smash", target="box", with_kind="hammer", intensity=3.0)
        if _box(w).get("destroyed") == 1.0:
            break
    assert _box(w)["destroyed"] == 1.0
    assert w.eng.node(w._containers["box"][1]["grain"])["attrs"]["qty"] == 0.0
    piles = [n for n in w.eng.neighbours(w._town, "has_dropped_stock")
             if w.eng.node(n)["attrs"]["kind"] == "grain"]
    assert len(piles) == 1
    assert w.eng.node(piles[0])["attrs"]["qty"] == 5.0
    assert w.eng.neighbours(piles[0], "at_cell") == [w._map_cells[cell]]


def _table_world(skill=None):
    """A woodworker at the workshop with the inputs for make_table (150 minutes: 10 ticks)."""
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Wil", "woodworker")
    if skill is not None:
        w.set_skill_level("Wil", "carpentry", skill)
    recipe = next(r for r in E.RECIPES if r["name"] == "make_table")
    for kind, qty in recipe["in"]:
        w.set_stock(kind, float(qty) * 10)
    key = next(k for k, v in E.BUILDINGS.items() if v.get("provides") == "woodworker")
    x, y, _fw, _fh = w._building_sites[key]
    w._move_actor_to("Wil", (x, y))
    return w


def _make_table(pace, skill=None):
    """Start make_table at a pace and tick it to completion. Returns (ticks, item quality, stamina spent, the
    recipe's reference quality before the job)."""
    w = _table_world(skill)
    reference = w.recipe_skill_level("Wil", w._recipe_specs.get("make_table", {}))
    before = w.stamina_reserve("Wil")
    assert w.major_action("Wil", "start", action_name="make_table", intensity=pace) is True
    ticks = 0
    while w.busy("Wil") and ticks < 100:
        w.tick(1)
        ticks += 1
    item = w.newest_tool()
    return ticks, float(w.eng.node(item)["attrs"]["quality"]), before - w.stamina_reserve("Wil"), reference


def test_a_recipe_at_pace_one_keeps_the_committed_time_and_quality():
    ticks, quality, _spent, reference = _make_table(1.0)
    assert ticks == 10
    assert quality == reference


def test_a_recipe_at_pace_one_and_a_half_finishes_sooner_with_lower_quality_and_more_stamina():
    base_ticks, base_quality, base_spent, _ = _make_table(1.0)
    ticks, quality, spent, _ = _make_table(1.5)
    assert ticks < base_ticks
    assert quality < base_quality
    assert spent > base_spent


def test_a_recipe_at_pace_one_half_is_slower_and_better():
    base_ticks, base_quality, base_spent, _ = _make_table(1.0)
    ticks, quality, spent, _ = _make_table(0.5)
    assert ticks > base_ticks
    assert quality > base_quality
    assert spent < base_spent


def test_a_pace_outside_the_caps_is_clamped_and_kept_on_the_job():
    w = _table_world()
    assert w.major_action("Wil", "start", action_name="make_table", intensity=99.0) is True
    job = w._job_of("Wil")
    assert w.eng.node(job)["attrs"]["pace"] == float(E.RESOLUTION["haste_cap"])


def test_a_rushed_batch_that_falls_below_the_ruin_line_is_spoiled():
    # A reference quality of about 0.12 sits just above ruin_below (0.1); pace 1.5 pushes it below the line.
    w = _table_world(skill=0.12)
    reference = w.recipe_skill_level("Wil", w._recipe_specs.get("make_table", {}))
    assert reference < 0.2
    items = len(list(w.eng.neighbours(w._town, "has_tool_item")))
    assert w.major_action("Wil", "start", action_name="make_table", intensity=1.5) is True
    job = w._job_of("Wil")
    while w.busy("Wil"):
        w.tick(1)
    assert len(list(w.eng.neighbours(w._town, "has_tool_item"))) == items
    assert w.eng.node(job)["attrs"]["ruined"] == 1.0


def test_set_intensity_changes_a_running_job_without_losing_progress():
    w = _table_world()
    assert w.major_action("Wil", "start", action_name="make_table") is True
    job = w._job_of("Wil")
    for _ in range(3):
        w.tick(1)
    remaining = w.eng.node(job)["attrs"]["remaining"]
    assert w.free_action("Wil", "set_intensity", intensity=1.5) is True
    assert w.eng.node(job)["attrs"]["pace"] == 1.5
    assert w.eng.node(job)["attrs"]["remaining"] == remaining
    ticks = 3
    while w.busy("Wil") and ticks < 100:
        w.tick(1)
        ticks += 1
    assert ticks < 10


def test_set_intensity_is_refused_without_a_running_job_or_a_number():
    w = _table_world()
    assert w.free_action("Wil", "set_intensity", intensity=1.5) is False
    assert w.major_action("Wil", "start", action_name="make_table") is True
    assert w.free_action("Wil", "set_intensity", intensity=True) is False
    assert w.free_action("Wil", "set_intensity", intensity=float("nan")) is False


def test_strain_falls_while_a_resident_sleeps():
    w = World(autonomous_actors=False)
    w.add_actor("Ada", role="hand", home_cell=_cells(w)[0])
    w.eng.set_attr(w._actors["Ada"], "strain", 0.5)
    w._lie_down("Ada", collapsed=False)
    w._job_tick_armed = True
    w._resolve_sleep()
    assert w.eng.node(w._actors["Ada"])["attrs"]["strain"] == pytest.approx(0.5 - float(E.RESOLUTION["strain_sleep_recovery"]))
