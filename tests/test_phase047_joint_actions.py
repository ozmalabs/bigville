"""Phase 047: joint actions, people acting together.

A joint act is one act of several residents, resolved by the world for all of them at once. Two kinds: a heavy load
carried along a step (the core's team term: the summed force times coordination(n)), and a crewed recipe worked by
more people (progress multiplied by the crew). The world publishes a joint option with `present`, the count of the
others who can join now. Nobody leads. With the joint_actions switch off, nothing changes.
"""
from __future__ import annotations

import pytest

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds import joint as J
from worlds.bigville_world import BigvilleWorld as World

A, B, C = "Ada", "Ben", "Cy"
CRATE = "crate"


# ------------------------------------------------------------------ helpers

def _open_cell(w):
    """A map cell with five walkable cells eastward, so a load can be pushed east along them (the pace cap is 3)."""
    for cell in sorted(w._map_cells):
        line = [(cell[0] + k, cell[1]) for k in range(5)]
        if all(c in w._map_cells and w.terrain_state(c)["speed"] > 0 for c in line):
            return cell
    raise AssertionError("no open ground")


def _crate_world(*, people=(A, B), mass=80.0, switch=True):
    """Residents on one cell, and a crate of `mass` on the next cell east (within one cell of each of them)."""
    w = World(autonomous_actors=False, physical_subsystems={"joint_actions": switch})
    cell = _open_cell(w)
    for name in people:
        w.add_actor(name, role="hand", home_cell=cell)
        w._move_actor_to(name, cell)
    node = w.eng.add_node("PhysicalObject", {"object_id": CRATE, "name": CRATE, "kind": "crate", "location": "world",
                                              "mass": float(mass), "cell": [cell[0] + 1, cell[1]]})
    w._physical_objects[CRATE] = node
    w._physical_object_locations[CRATE] = "world"
    w.tick()
    return w, cell


def _crate_cell(w):
    return w._physical_location_cell(CRATE)


def _carry(w, names, toward=(1, 0)):
    return w.enact_joint({"task": "carry", "object": CRATE, "toward": list(toward)}, list(names))


def _fresh(w, *names):
    """Put the residents' stamina back to full, so a test isolates one act from exhaustion."""
    for name in names:
        w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
        w.eng.set_attr(w._actors[name], "major_action_used", 0.0)


def _saw_world(helpers=()):
    """A sawyer at the sawpit, working saw_planks (a crewed recipe, Phase 047), with helpers on the same cell."""
    w = World(autonomous_actors=False, physical_subsystems={"joint_actions": True})
    w.add_tradesperson("Sawyer", "sawyer")
    for name in helpers:
        w.add_tradesperson(name, "labourer")
    w.set_stock("lumber", 20)
    x, y, _fw, _fh = w._building_sites["sawpit"]
    w._move_actor_to("Sawyer", (x, y))
    for name in helpers:
        w._move_actor_to(name, (x, y))
    w.tick()
    assert w.major_action("Sawyer", "start", action_name="saw_planks") is True
    job = w._job_of("Sawyer")
    if helpers:
        assert w.enact_joint({"task": "crew", "worker": "Sawyer"}, list(helpers)) == {h: True for h in helpers}
    return w, job


def _progress_per_tick(w, job, ticks=2):
    rates, prev = [], w.eng.node(job)["attrs"]["remaining"]
    for _ in range(ticks):
        w.tick()
        cur = w.eng.node(job)["attrs"]["remaining"]
        rates.append(prev - cur)
        prev = cur
    return rates


# ------------------------------------------------------------------ the pure terms

def test_coordination_is_one_for_one_and_falls_as_a_group_grows():
    assert J.coordination(1, 0.0, 0.1, 0.5) == 1.0
    steps = [n * J.coordination(n, 0.0, 0.1, 0.5) for n in range(1, 5)]
    gains = [b - a for a, b in zip(steps, steps[1:])]
    assert all(g > 0 for g in gains)
    assert all(later < earlier for earlier, later in zip(gains, gains[1:]))


def test_skill_at_the_task_lowers_coordination_loss():
    assert J.coordination(3, 1.0, 0.1, 0.5) > J.coordination(3, 0.0, 0.1, 0.5)


def test_members_needed_counts_one_when_one_is_enough_and_none_when_the_largest_group_falls_short():
    assert J.members_needed(1.0, 0.5, 4, 0.1) == 1
    assert J.members_needed(1.0, 1.6, 4, 0.1) == 2
    assert J.members_needed(1.0, 9.0, 4, 0.1) is None


def test_a_lone_crew_worker_crawls_and_a_third_adds_less_than_a_full_worker():
    penalty = 0.25
    one, two, three = (J.crew_factor(n, penalty, 0.0, 0.1, 0.5) for n in (1, 2, 3))
    assert one == penalty
    assert two > one and three > two
    assert three - two < 1.0


def test_the_carry_pace_is_nothing_below_the_load_and_follows_the_ratio_up_to_the_cap():
    assert J.carry_pace(0.99, 3) == 0
    assert J.carry_pace(1.0, 3) == 1
    assert J.carry_pace(2.5, 3) == 2
    assert J.carry_pace(9.0, 3) == 3


# ------------------------------------------------------------------ the data

def test_the_pack_items_heavier_than_one_persons_capacity_are_only_the_oven():
    capacity = float(E.ACTOR_DEFAULTS["inventory_max_load"])
    heavy = sorted(kind for kind, spec in E.ITEMS.items() if float(spec.get("weight", 0.0)) > capacity)
    assert heavy == ["oven"]


def test_the_joint_tables_are_in_the_bigville_pack_with_the_carry_load_unit_of_one_person():
    assert E.JOINT_TASKS["carry"]["load_unit"] == float(E.ACTOR_DEFAULTS["inventory_max_load"])
    assert E.JOINT_TASKS["carry"]["max_members"] >= 2
    saw = next(row for row in E.RECIPES if row["name"] == "saw_planks")
    assert saw["crew"] == {"min": 2, "max": 3}


def test_the_switch_is_off_by_default():
    assert World(autonomous_actors=False).joint_actions_on() is False


# ------------------------------------------------------------------ carrying a load

def test_with_the_switch_off_no_joint_option_is_published_and_a_joint_proposal_is_unsupported():
    w, cell = _crate_world(switch=False)
    assert [o for o in w.actor_affordances(A) if o["action"] == "joint"] == []
    assert _carry(w, [A, B]) == {A: False, B: False}
    assert w.last_outcome(A)["reason"] == "unsupported"
    assert _crate_cell(w) == (cell[0] + 1, cell[1])


def test_a_load_one_resident_can_lift_is_offered_no_joint_option():
    w, _cell = _crate_world(mass=20.0)
    assert [o for o in w.actor_affordances(A) if o["action"] == "joint"] == []


def test_the_joint_option_says_how_many_are_needed_and_how_many_are_present():
    w, _cell = _crate_world(people=(A, B))
    (option,) = [o for o in w.actor_affordances(A) if o["action"] == "joint"]
    assert option["task"] == "carry" and option["object"] == CRATE
    assert option["needs"] == 2 and option["present"] == 1 and option["max"] == E.JOINT_TASKS["carry"]["max_members"]
    assert [1, 0] in option["toward"]
    w2, _ = _crate_world(people=(A,))
    (alone,) = [o for o in w2.actor_affordances(A) if o["action"] == "joint"]
    assert alone["present"] == 0


def test_one_resident_alone_strains_spends_effort_and_the_load_stays_put():
    w, cell = _crate_world(people=(A,))
    before = _crate_cell(w)
    assert _carry(w, [A]) == {A: True}          # the attempt is made; it fails physically
    assert _crate_cell(w) == before
    assert w.last_joint(A) == {"turn": w.last_joint(A)["turn"], "task": "carry", "target": CRATE, "joined": 1,
                               "needed": 2, "outcome": "stuck"}
    assert w.stamina_reserve(A) < 1.0
    assert float(w.eng.node(w._actors[A])["attrs"]["strain"]) > 0.0


def test_a_lone_carrier_is_hurt_when_the_strain_reaches_the_limit():
    w, _cell = _crate_world(people=(A,))
    health = w.health(A)
    for _ in range(3):
        _fresh(w, A)
        _carry(w, [A])
    assert w.health(A) < health
    assert w.eng.node(w._actors[A])["attrs"]["strain"] < E.RESOLUTION["strain_limit"]


def test_two_residents_carry_a_load_one_cannot_and_it_moves_a_cell():
    w, cell = _crate_world(people=(A, B))
    start = _crate_cell(w)
    assert _carry(w, [A, B]) == {A: True, B: True}
    assert _crate_cell(w) == (start[0] + 1, start[1])
    assert w.last_joint(A)["joined"] == 2 and w.last_joint(A)["outcome"] == "moved"
    assert w.last_outcome(A) == {"turn": w.last_outcome(A)["turn"], "action": "joint", "applied": True, "reason": ""}


def test_each_carrier_pays_its_share_of_the_force_and_the_pair_pays_less_each():
    w, _cell = _crate_world(people=(A, B))
    start = {n: w.stamina_reserve(n) for n in (A, B)}
    _carry(w, [A, B])
    spent = {n: start[n] - w.stamina_reserve(n) for n in (A, B)}
    assert spent[A] == pytest.approx(spent[B])
    lone, _ = _crate_world(people=(A,))
    solo_before = lone.stamina_reserve(A)
    _carry(lone, [A])
    assert spent[A] < solo_before - lone.stamina_reserve(A)


def test_more_people_or_a_lighter_load_moves_the_load_further_in_one_turn():
    two, _ = _crate_world(people=(A, B), mass=40.0)
    start = _crate_cell(two)
    _carry(two, [A, B])
    assert _crate_cell(two)[0] - start[0] == 2                 # rho 2.3: two cells
    four, _ = _crate_world(people=(A, B, C, "Dee"), mass=40.0)
    start = _crate_cell(four)
    _carry(four, [A, B, C, "Dee"])
    assert _crate_cell(four)[0] - start[0] == E.JOINT_TASKS["carry"]["pace_cap"]   # rho 3.8: the cap


def test_a_member_who_collapses_mid_carry_drops_the_load_where_it_lies():
    w, _cell = _crate_world(people=(A, B))
    _carry(w, [A, B])
    where = _crate_cell(w)
    w.eng.set_attr(w._bodies[B], "stamina_reserve", 0.0)      # no reserve: B collapses in the next tick
    w.tick()
    assert w._sleep_code(B) == "collapsed"
    assert _crate_cell(w) == where
    assert w.eng.node(w._physical_objects[CRATE])["attrs"]["carriers"] == []
    kinds = [w.event_data(e)["kind"] for e in w._events.values()]
    assert "load_dropped" in kinds


def test_a_load_that_is_carried_and_held_does_not_drop():
    w, _cell = _crate_world(people=(A, B))
    _carry(w, [A, B])
    w.tick()
    assert "load_dropped" not in [w.event_data(e)["kind"] for e in w._events.values()]


def test_a_resident_asleep_or_collapsed_is_left_out_and_the_rest_still_act_with_a_reason():
    w, _cell = _crate_world(people=(A, B))
    w.eng.set_attr(w._actors[B], "collapsed", 1.0)
    assert _carry(w, [A, B]) == {A: True, B: False}
    assert w.last_outcome(B)["reason"] == "collapsed"
    assert w.last_joint(A)["joined"] == 1


def test_a_resident_out_of_reach_is_left_out_with_not_in_reach():
    w, _cell = _crate_world(people=(A, B))
    far = next(c for c in sorted(w._map_cells) if w.distance(w.actor_position(A), c) is not None
               and w.distance(w.actor_position(A), c) >= 3)
    w._move_actor_to(B, far)
    assert _carry(w, [A, B]) == {A: True, B: False}
    assert w.last_outcome(B)["reason"] == "not_in_reach"


def test_the_order_of_the_participants_does_not_change_the_act():
    one, _ = _crate_world(people=(A, B))
    two, _ = _crate_world(people=(A, B))
    _carry(one, [A, B])
    _carry(two, [B, A])
    assert _crate_cell(one) == _crate_cell(two)
    assert one.stamina_reserve(A) == pytest.approx(two.stamina_reserve(A))


def test_a_solo_joint_proposal_through_the_plan_path_is_the_members_own_act():
    w, _cell = _crate_world(people=(A,))
    assert w.enact_plan(A, {"action": "joint", "joint": {"task": "carry", "object": CRATE, "toward": [1, 0]}}) is True
    assert w.last_outcome(A)["action"] == "joint" and w.last_outcome(A)["applied"] is True


def test_a_joint_act_is_seen_by_a_resident_with_sight_of_the_site():
    w, _cell = _crate_world(people=(A, B, C))
    _carry(w, [A, B])
    assert w.eng.neighbours(w._actors[C], "observed_event")


# ------------------------------------------------------------------ crewed recipes

def test_a_lone_worker_on_a_crewed_saw_starts_and_crawls():
    w, job = _saw_world()
    assert w._crew_factor(job) == E.JOINT_TASKS["crew"]["crew_penalty"]
    (rate,) = _progress_per_tick(w, job, ticks=1)
    assert rate == pytest.approx(E.JOINT_TASKS["crew"]["crew_penalty"])


def test_two_finish_faster_than_one_and_a_third_adds_less_than_a_full_worker():
    lone, job1 = _saw_world()
    pair, job2 = _saw_world(helpers=("Ben",))
    trio, job3 = _saw_world(helpers=("Ben", "Cy"))
    r1 = _progress_per_tick(lone, job1, ticks=1)[0]
    r2 = _progress_per_tick(pair, job2, ticks=1)[0]
    r3 = _progress_per_tick(trio, job3, ticks=1)[0]
    assert r1 < r2 < r3
    assert r3 - r2 < 1.0          # a third worker adds less than another whole worker's labour


def test_a_helper_joins_only_from_the_worker_cell_and_only_when_free():
    w, job = _saw_world()
    far = next(c for c in sorted(w._map_cells) if w.distance(w.actor_position("Sawyer"), c) is not None
               and w.distance(w.actor_position("Sawyer"), c) >= 2)
    w.add_tradesperson(B, "labourer")
    w._move_actor_to(B, far)
    assert w.enact_joint({"task": "crew", "worker": "Sawyer"}, [B]) == {B: False}
    assert w.last_outcome(B)["reason"] == "not_in_reach"


def test_a_crew_option_is_published_to_a_free_resident_at_the_site():
    w, _job = _saw_world()
    w.add_tradesperson(B, "labourer")
    w._move_actor_to(B, w.actor_position("Sawyer"))
    (option,) = [o for o in w.actor_affordances(B) if o["action"] == "joint"]
    assert option["task"] == "crew" and option["worker"] == "Sawyer" and option["needs"] == 1


def test_with_the_switch_off_a_crewed_recipe_runs_as_before():
    w = World(autonomous_actors=False, physical_subsystems={"joint_actions": False})
    w.add_tradesperson("Sawyer", "sawyer")
    w.set_stock("lumber", 20)
    x, y, _fw, _fh = w._building_sites["sawpit"]
    w._move_actor_to("Sawyer", (x, y))
    w.tick()
    assert w.major_action("Sawyer", "start", action_name="saw_planks") is True
    job = w._job_of("Sawyer")
    assert w._crew_factor(job) == 1.0
    assert _progress_per_tick(w, job, ticks=1)[0] == pytest.approx(1.0)


# ------------------------------------------------------------------ the game: one turn, simple residents

class _Carrier(DeterministicBackend):
    """A resident whose only policy is to propose a fixed joint act (for the game-level order test)."""

    def __init__(self, character, task):
        super().__init__(character)
        self._task = task

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("joint", {"joint": dict(self._task)}, "test"))


def test_two_simple_residents_coordinate_from_the_present_count_alone():
    w, cell = _crate_world(people=(A, B))
    game = BigvilleGame(w, autonomous=True)
    for name in (A, B):
        game.set_backend(name, DeterministicBackend(game.characters[name]))
    start = _crate_cell(w)
    game.step()
    moved = _crate_cell(w)
    assert moved != start
    assert max(abs(moved[0] - start[0]), abs(moved[1] - start[1])) == 1   # one cell, along a step the world offered
    assert game.last_results[A] is True and game.last_results[B] is True


def test_a_simple_resident_with_no_one_present_does_not_try_the_joint_act():
    w, _cell = _crate_world(people=(A,))
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(A, DeterministicBackend(game.characters[A]))
    start = _crate_cell(w)
    game.step()
    assert _crate_cell(w) == start
    assert w.last_joint(A) is None


def test_the_turns_joint_act_does_not_depend_on_the_order_of_the_responses():
    results = []
    for order_of_turn in ((A, B), (B, A)):
        w, _cell = _crate_world(people=(A, B))
        game = BigvilleGame(w, autonomous=True)
        task = {"task": "carry", "object": CRATE, "toward": [1, 0]}
        for name in (A, B):
            game.set_backend(name, _Carrier(game.characters[name], task))
        responses = {name: game.backends[name].decide(None) for name in (A, B)}
        game._resolve_joint_groups(list(order_of_turn), responses)
        results.append((_crate_cell(w), dict(game.last_results), w.stamina_reserve(A)))
    assert results[0][0] == results[1][0]
    assert results[0][1] == results[1][1]
    assert results[0][2] == pytest.approx(results[1][2])


def test_with_the_switch_off_a_game_turn_with_a_joint_proposal_changes_nothing_physical():
    w, cell = _crate_world(people=(A, B), switch=False)
    game = BigvilleGame(w, autonomous=True)
    task = {"task": "carry", "object": CRATE, "toward": [1, 0]}
    for name in (A, B):
        game.set_backend(name, _Carrier(game.characters[name], task))
    before = _crate_cell(w)
    game.step()
    assert _crate_cell(w) == before
    assert game.last_results == {A: False, B: False}
