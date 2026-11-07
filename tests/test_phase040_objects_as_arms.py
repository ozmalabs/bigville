"""Phase 040: objects as arms. Hitting and throwing with what a resident holds in a hand.

Any discrete object in a hand can be swung (strike, with `with`) or thrown (the throw action). What it does comes from
its physical data: ITEMS weight, MATERIALS hardness and fragility, the container flag, and TOOL_FIT's edge data. The
pack's OBJECT_FORCE table holds the numbers (all APPROX). The switch physical_subsystems.object_force is off by default.
Nothing here is random, and the world records no assault: a throw or a blow is a physical event.

Bulk goods (a stone, a loaf) are not discrete items in the pack, so this slice does not throw them. The tests use the
hammer (metal), the wooden mug (wood, a container) and the pot (metal, a heavy container).
"""
from __future__ import annotations

import types

import pytest

from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds import resolution as R
from worlds.bigville_world import BigvilleWorld as World

A, H = "Ada", "Hal"


def _world(object_force=True):
    switches = {"object_force": True} if object_force else None
    return World(autonomous_actors=False, physical_subsystems=switches)


def _pair(object_force=True, distance=0):
    """Ada and Hal on one cell (distance 0), or Hal `distance` cells east of Ada, a tick in, turn-start cells recorded."""
    w = _world(object_force)
    cell = sorted(w._map_cells)[len(w._map_cells) // 2]
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w._move_actor_to(A, cell)
    w._move_actor_to(H, cell)
    if distance:
        target = (cell[0] + distance, cell[1])
        assert target in w._map_cells, "the founding map has the cells these tests use"
        w._move_actor_to(H, target)
    w.tick()
    w.mark_turn_start()
    return w


def _hold(w, name, kind):
    """Put a new item of `kind` into one of the resident's hands (not a pack)."""
    item = w._new_tool_item(kind)
    assert w._accept_discrete_item(name, item) is True
    return item


def _body(w, name, **attrs):
    for key, value in attrs.items():
        w.eng.set_attr(w._bodies[name], key, float(value))


def _throw(w, kind, target=H, intensity=1.0, reaction=None, actor=A):
    pending, code = w.throw_begin(actor, {"target": target, "with": kind, "intensity": intensity})
    if pending is None:
        return None, code
    ok, _ = w.throw_resolve(pending, reaction)
    return pending, ok


def _wall_grid(w, cell, code):
    """Make `cell` an occluder of sight (a wall in the map grid). The grid rows are lists of codes."""
    x, y = cell
    row = w._map_grid[y]
    if isinstance(row, list):
        row[x] = code
    else:
        w._map_grid[y] = row[:x] + code + row[x + 1:]


def _wall_code(w):
    return sorted(w._occluder_codes(E.HEARING["sight_occluders"]))[0]


# ------------------------------------------------------------------ pack and wiring


def test_pack_binds_object_force_and_the_throw_verb_routes_to_the_action():
    assert E.OBJECT_FORCE["range_max"] >= 1
    assert E.VERBS["throw"]["implemented"] is True
    assert E.VERBS["throw"]["route"] == "throw"
    assert "throw" in E.MAJOR_ACTIONS and E.MAJOR_ACTIONS["throw"]["description"]
    assert "object_force" in World.PHYSICAL_SUBSYSTEM_DEFAULTS
    assert World.PHYSICAL_SUBSYSTEM_DEFAULTS["object_force"] is False
    assert E.OBJECT_FORCE["harm_scale"] > 1.0


def test_switch_off_refuses_a_throw_and_ignores_with_in_a_blow():
    w = _pair(object_force=False)
    _hold(w, A, "hammer")
    pending, code = w.throw_begin(A, {"target": H, "with": "hammer"})
    assert pending is None and code == "unsupported"
    # A blow ignores `with` with the switch off: the same harm and cost as a bare-hand blow.
    bare = _pair(object_force=False)
    p_bare, _ = bare.strike_begin(A, {"target": H, "intensity": 1.0})
    bare.strike_resolve(p_bare, None)
    p_with, _ = w.strike_begin(A, {"target": H, "intensity": 1.0, "with": "hammer"})
    assert p_with["weapon"] is None
    w.strike_resolve(p_with, None)
    assert p_with["result"]["harm"] == pytest.approx(p_bare["result"]["harm"])
    assert p_with["result"]["attacker_cost"] == pytest.approx(p_bare["result"]["attacker_cost"])


def test_throw_needs_the_object_in_a_hand_not_in_a_pack():
    w = _pair()
    w.give_tool(A, "hammer")                       # carried in the pack, not in a hand
    pending, code = w.throw_begin(A, {"target": H, "with": "hammer"})
    assert pending is None and code == "not_held"
    assert _throw(w, "hammer", actor=A) == (None, "not_held")


def test_throw_and_blow_are_observable_through_the_game_contest_path():
    response = types.SimpleNamespace(major_action=types.SimpleNamespace(action="throw"))
    assert BigvilleGame._is_contest(response) is True
    assert BigvilleGame._is_contest(types.SimpleNamespace(major_action=None)) is False


# ------------------------------------------------------------------ hitting


def test_a_hammer_blow_harms_more_than_a_bare_blow_at_the_same_cost():
    bare = _pair()
    p0, _ = bare.strike_begin(A, {"target": H, "intensity": 1.0})
    bare.strike_resolve(p0, None)
    armed = _pair()
    _hold(armed, A, "hammer")
    p1, _ = armed.strike_begin(A, {"target": H, "intensity": 1.0, "with": "hammer"})
    armed.strike_resolve(p1, None)
    assert p1["result"]["harm"] == pytest.approx(2.0 * p0["result"]["harm"])
    assert p1["result"]["attacker_cost"] == pytest.approx(p0["result"]["attacker_cost"])


def test_a_heavy_object_is_clumsy_and_costly_for_a_weak_swinger_and_effective_for_a_strong_one():
    weak = _pair()
    _body(weak, A, str_base=0.3)
    _hold(weak, A, "pot")
    strong = _pair()
    _body(strong, A, str_base=3.0)
    _hold(strong, A, "pot")
    pw, _ = weak.strike_begin(A, {"target": H, "with": "pot"})
    ps, _ = strong.strike_begin(A, {"target": H, "with": "pot"})
    assert pw["weapon"]["effort"] > 1.0 and ps["weapon"]["effort"] == pytest.approx(1.0)
    assert pw["weapon"]["mult"] < ps["weapon"]["mult"]
    weak.strike_resolve(pw, None)
    strong.strike_resolve(ps, None)
    assert pw["result"]["attacker_cost"] > ps["result"]["attacker_cost"]
    assert pw["result"]["harm"] < ps["result"]["harm"]


def test_a_blow_with_a_wooden_mug_breaks_it_and_the_hammer_only_wears():
    w = _pair()
    mug = _hold(w, A, "wooden_mug")
    w.strike_resolve(w.strike_begin(A, {"target": H, "with": "wooden_mug"})[0], None)
    assert float(w.eng.node(mug)["attrs"]["broken"]) == 1.0
    assert w._hand_held_item(A, "wooden_mug") is None
    hammer = _hold(w, A, "hammer")
    before = float(w.eng.node(hammer)["attrs"]["condition"])
    w.actor_tick(A)                                   # a new turn: the blow claims the slot again
    w.strike_resolve(w.strike_begin(A, {"target": H, "with": "hammer"})[0], None)
    assert float(w.eng.node(hammer)["attrs"]["condition"]) < before
    assert float(w.eng.node(hammer)["attrs"].get("broken", 0.0)) != 1.0


# ------------------------------------------------------------------ throwing


def test_a_thrown_hammer_harms_more_than_a_thrown_mug_at_the_same_range():
    harm_hammer = _harm_of_throw(distance=1, kind="hammer")
    harm_mug = _harm_of_throw(distance=1, kind="wooden_mug")
    assert harm_hammer > harm_mug > 0.0


def _harm_of_throw(distance, kind, intensity=1.0):
    w = _pair(distance=distance)
    _hold(w, A, kind)
    pending, ok = _throw(w, kind, intensity=intensity)
    assert pending is not None
    return float(pending["result"]["harm"])


def test_a_thrown_objects_harm_falls_with_distance():
    near = _harm_of_throw(distance=1, kind="hammer")
    far = _harm_of_throw(distance=3, kind="hammer")
    assert near > far > 0.0


def test_range_falls_with_weight_and_rises_with_strength():
    w = _pair()
    light = w._throw_range(A, "wooden_mug", 1.0)
    heavy = w._throw_range(A, "pot", 1.0)
    assert heavy < light
    _body(w, A, str_base=3.0)
    assert w._throw_range(A, "pot", 1.0) > heavy
    assert w._throw_range(A, "pot", 2.0) >= w._throw_range(A, "pot", 1.0)


def test_a_throw_beyond_range_lands_short_and_is_not_refused():
    w = _pair(distance=4)
    _body(w, A, str_base=0.05)         # so little strength that the range is 0 cells
    _hold(w, A, "hammer")
    pending, ok = _throw(w, "hammer")
    assert pending is not None and ok is True
    assert pending["result"]["outcome"] == "short"
    assert pending["result"]["landed_at"] == list(pending["here"])
    assert w._hand_held_item(A, "hammer") is None


def test_a_throw_with_no_clear_line_stops_before_the_obstacle_and_a_mug_breaks_on_the_wall():
    w = _pair(distance=3)
    cell = sorted(w._map_cells)[len(w._map_cells) // 2]
    wall = (cell[0] + 2, cell[1])
    _wall_grid(w, wall, _wall_code(w))
    mug = _hold(w, A, "wooden_mug")
    pending, ok = _throw(w, "wooden_mug")
    assert ok is True
    assert pending["result"]["outcome"] == "stopped"
    assert pending["result"]["broken"] is True
    assert float(w.eng.node(mug)["attrs"]["broken"]) == 1.0
    assert w._hand_held_item(A, "wooden_mug") is None


def test_a_hammer_thrown_at_a_wall_stops_on_the_open_cell_before_it_and_survives():
    w = _pair(distance=3)
    cell = sorted(w._map_cells)[len(w._map_cells) // 2]
    wall = (cell[0] + 2, cell[1])
    _wall_grid(w, wall, _wall_code(w))
    hammer = _hold(w, A, "hammer")
    pending, ok = _throw(w, "hammer")
    assert pending["result"]["outcome"] == "stopped" and pending["result"]["broken"] is False
    assert tuple(pending["result"]["landed_at"]) == (cell[0] + 1, cell[1])
    assert float(w.eng.node(hammer)["attrs"].get("broken", 0.0)) != 1.0
    assert w.eng.has_edge(hammer, "at_cell", w._map_cells[(cell[0] + 1, cell[1])])


def test_a_miss_lands_on_a_neighbouring_cell_and_the_object_can_be_picked_up_again():
    w = _pair(distance=2)
    _body(w, H, str_base=3.0)
    w.set_skill_level(H, "fighting", 1.0)
    hammer = _hold(w, A, "hammer")
    w.set_skill_level(A, "fighting", 0.0)
    pending, _ = w.throw_begin(A, {"target": H, "with": "hammer", "intensity": 1.0})
    assert pending is not None and "evade" in pending["offer"]["options"]
    w.throw_resolve(pending, "evade")
    assert pending["result"]["outcome"] == "evaded"
    landed = tuple(pending["result"]["landed_at"])
    assert landed != tuple(pending["cell"]) and max(abs(landed[0] - pending["cell"][0]),
                                                      abs(landed[1] - pending["cell"][1])) == 1
    assert w._hand_held_item(A, "hammer") is None
    # Walk to it and pick it up again (a new turn: the throw spent the slot).
    w._move_actor_to(A, landed)
    w.actor_tick(A)
    assert w.pick_up(A, hammer) is True
    assert w._hand_held_item(A, "hammer") is hammer or w._hand_held_item(A, "hammer") == hammer


def test_a_skilled_thrower_hits_an_unskilled_target_that_does_not_step_aside():
    near = _pair(distance=1)
    near.set_skill_level(A, "fighting", 1.0)
    _hold(near, A, "hammer")
    pending, _ = _throw(near, "hammer")
    assert pending["result"]["hit"] is True and pending["result"]["harm"] > 0.0


def test_a_skilled_defender_steps_aside_from_an_unskilled_thrower():
    w = _pair(distance=3)
    w.set_skill_level(H, "fighting", 1.0)
    w.set_skill_level(A, "fighting", 0.0)
    _hold(w, A, "hammer")
    pending, _ = w.throw_begin(A, {"target": H, "with": "hammer", "intensity": 1.0})
    assert "evade" in pending["offer"]["options"]
    w.throw_resolve(pending, "evade")
    assert pending["result"]["outcome"] == "evaded" and pending["result"]["harm"] == 0.0
    assert w.health(H) == pytest.approx(1.0)


def test_a_disarm_drops_the_attackers_hand_object_on_a_redirected_grab():
    w = _pair(distance=0)
    _body(w, A, str_base=0.2)
    _body(w, H, str_base=3.0)
    w.set_skill_level(H, "fighting", 1.0)
    held_by_attacker = _hold(w, A, "wooden_mug")
    prize = _hold(w, H, "hammer")
    pending, reason = w.take_begin(A, {"source": H, "kind": prize, "amount": 1.0})
    assert pending is not None, reason
    applied, code = w.take_resolve(pending, "resist")
    assert pending["result"]["outcome"] == "redirected"
    assert w._hand_held_item(A, "wooden_mug") is None
    assert w.eng.has_edge(w._town, "has_tool_item", held_by_attacker)


def test_object_count_is_conserved_except_by_breakage():
    w = _pair(distance=1)
    _hold(w, A, "wooden_mug")
    _hold(w, A, "hammer")

    def live():
        return sum(1 for n in w.eng.nodes("ToolItem") if float(w.eng.node(n)["attrs"].get("broken", 0.0)) != 1.0)

    before = live()
    _throw(w, "hammer")
    assert live() == before                       # a hammer that hits a person is conserved
    w.actor_tick(A)
    _throw(w, "wooden_mug")                       # a mug that hits a person breaks: one fewer live object
    assert live() == before - 1


def test_throw_and_blow_are_physical_events_seen_only_by_witnesses():
    w = _pair(distance=1)
    _hold(w, A, "hammer")
    _throw(w, "hammer")
    seen = [w.eng.node(e)["attrs"].get("kind") for e in w.eng.neighbours(w._actors[H], "observed_event")]
    assert "throw" in seen
    # The world records no assault, offence or threat.
    kinds = {w.eng.node(e)["attrs"].get("kind") for e in w.eng.neighbours(w._actors[H], "observed_event")}
    assert not kinds & {"assault", "offence", "crime", "threat"}


def test_the_same_throw_gives_the_same_result():
    results = []
    for _ in range(2):
        w = _pair(distance=2)
        _hold(w, A, "hammer")
        pending, _ = _throw(w, "hammer")
        results.append((pending["result"]["outcome"], round(pending["result"]["harm"], 12),
                        tuple(pending["result"]["landed_at"])))
    assert results[0] == results[1]


def test_enact_plan_routes_a_throw_proposal_through_the_world():
    w = _pair(distance=1)
    _hold(w, A, "hammer")
    assert w.enact_plan(A, {"action": "throw", "target": H, "with": "hammer", "intensity": 1.0}) is True
    assert w._hand_held_item(A, "hammer") is None


def test_the_attempt_verb_throw_is_the_throw_action():
    w = _pair(distance=1)
    _hold(w, A, "hammer")
    assert w.enact_plan(A, {"action": "attempt", "verb": "throw", "target": H, "with": "hammer",
                            "intensity": 1.0}) is True
    assert w._hand_held_item(A, "hammer") is None
    off = _pair(object_force=False)
    _hold(off, A, "hammer")
    assert off.enact_plan(A, {"action": "attempt", "verb": "throw", "target": H, "with": "hammer"}) is False
    assert off._hand_held_item(A, "hammer") is not None      # refused: the object stays in hand
