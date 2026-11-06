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
    assert w.major_action("Ada", "attempt", verb="push", target="box") is False
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
    assert all(d > 0.0 for d in falls), "each attempt damages it"
    assert w.last_attempt("Ada")["outcome"] == "broke"
    _turn(w)
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
