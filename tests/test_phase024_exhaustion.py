"""Phase 024: exhaustion, collapse and sleep.

The reserve sets a movement band (the seed's mv_energy_budget): full speed, x1.5 and x3 intervals, and no
walking below e_low. A resident who falls below e_collapse collapses where they stand, is refused other
major actions (`collapsed`), and wakes at collapse_cap. `sleep` is a major action that restores the reserve
to rest_cap. Sleeping or collapsed residents are refused (`asleep`), and their timed jobs pause (Phase 023).
The backend decides whether to sleep; the world publishes `lateness` and `safe`.
"""
from __future__ import annotations

import math

import pytest

from bigville.backends import ActorContext, DeterministicBackend
from bigville.character import CharacterDefinition
from domains import bigville_entities as E
from domains import world_affordances as WA
from worlds.bigville_world import BigvilleWorld as World


def _resident(name="Ada", **world_kwargs):
    w = World(autonomous_actors=False, **world_kwargs)
    cells = sorted(w._map_cells)
    w.add_actor(name, role="hand", home_cell=cells[len(cells) // 2])
    return w


def _set_reserve(w, name, value):
    w.eng.set_attr(w._bodies[name], "stamina_reserve", float(value))


def _reason(w, name):
    return w.last_outcome(name)["reason"]


def _flat_ground(w):
    """Every cell is flat grass with a move time of 1, so only the exhaustion band changes the interval.
    Traversal wear is switched off: after enough crossings it reshapes the route, which is not under test."""
    flat = {**dict(E.TERRAIN_MOVEMENT["grass"]), "terrain": "grass", "move_time": 1.0,
            "stamina_multiplier": 1.0}
    w.terrain_state = lambda cell: dict(flat)
    w._wear_cell_by_traversal = lambda actor, cell: None


def _neighbour(w, name):
    here = w.actor_position(name)
    for cell in sorted(w._map_cells):
        if cell != here and w.distance(here, cell) == 1:
            return cell
    raise AssertionError("no neighbouring cell")


def _walk_turns(w, name, reserve, turns=60):
    """Walk back and forth between two neighbouring cells, one move attempt per turn. The reserve and hunger
    are held (hunger raises the stamina a walk costs, Phase 022). Returns how many turns moved the walker."""
    home = w.actor_position(name)
    other = _neighbour(w, name)
    moved = 0
    for _ in range(turns):
        _set_reserve(w, name, reserve)
        w.eng.set_attr(w._actors[name], "hunger", 0.0)
        w.actor_tick(name)
        destination = other if w.actor_position(name) == home else home
        before = w.actor_position(name)
        assert w.major_action(name, "move", destination=destination)
        moved += w.actor_position(name) != before
    return moved


def _smith_at_forge():
    w = World()
    w.add_tradesperson("Smith", "smith")
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)   # Phase 032: the plough needs strength 1.2
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    return w


def _job(w, name):
    return w.eng.neighbours(w._actor(name), "on_job")[0]


# ------------------------------------------------------------------ the pack table and refusal codes

def test_the_exhaustion_codes_are_refusal_reasons_in_the_pack():
    for code in ("asleep", "collapsed"):
        assert code in E.REFUSAL_REASONS
        assert E.REFUSAL_REASONS[code]["description"].strip()
    # Phase 049: too_tired is retired. Walking below e_low is slower, not refused.
    assert "too_tired" not in E.REFUSAL_REASONS
    assert "sleep" in E.MAJOR_ACTIONS and E.MAJOR_ACTIONS["sleep"]["description"].strip()


def test_the_rest_rate_is_read_from_the_exhaustion_table():
    assert E.EXHAUSTION["rest_recovery_per_unit"] == 0.1
    assert WA.REST_RECOVERY_PER_UNIT == E.EXHAUSTION["rest_recovery_per_unit"]


def test_the_seeded_fractions_and_hop_budget_are_the_table_values():
    ex = E.EXHAUSTION
    assert (ex["e_high"], ex["e_mid"], ex["e_low"]) == (0.7, 0.4, 0.15)
    assert list(ex["moves_per_tick"]) == [3, 2, 1, 0.5]     # Phase 049: 0 (no walking below e_low) -> 0.5 (slowest)


# ------------------------------------------------------------------ slowing

@pytest.mark.parametrize("reserve, interval", [(0.9, 1), (0.5, 1.5), (0.2, 3)])
def test_a_walk_takes_x1_x1_5_and_x3_the_turns_by_reserve_band(reserve, interval):
    w = _resident()
    _flat_ground(w)
    turns = 60
    moved = _walk_turns(w, "Ada", reserve, turns)
    assert moved == pytest.approx(turns / interval)


def test_a_resident_below_e_low_still_walks_until_the_collapse():
    # Phase 049: below e_low a resident walks at the slowest rate (speed 1/6, moves_per_tick 0.5 of 3) until the
    # reserve falls below e_collapse and they fall down. The walk is not refused; the collapse stops it. The simple
    # backend is still offered no travel below e_low (the offers are unchanged).
    w = _resident()
    _flat_ground(w)
    _set_reserve(w, "Ada", 0.1)
    assert w.exhaustion_step("Ada") == 3 and w.speed_factor("Ada") == pytest.approx(1 / 6, abs=1e-4)
    other = _neighbour(w, "Ada")
    home = w.actor_position("Ada")
    moved = 0
    for _ in range(60):
        if w.asleep("Ada"):
            break
        w.eng.set_attr(w._actors["Ada"], "hunger", 0.0)
        w.actor_tick("Ada")
        destination = other if w.actor_position("Ada") == home else home
        before = w.actor_position("Ada")
        if not w.major_action("Ada", "move", destination=destination):
            break
        moved += w.actor_position("Ada") != before
    assert moved >= 1, "the first step below e_low is taken"
    assert w.collapsed("Ada"), "the collapse stops the walk, not a refusal"
    assert all(o["action"] != "move" for o in w.actor_affordances("Ada"))


def test_the_slowdown_publishes_the_step_and_speed_on_the_body_and_the_move_options():
    w = _resident()
    _set_reserve(w, "Ada", 0.5)
    body = w.body_state("Ada")
    assert body["exhaustion_step"] == 1
    assert body["speed_factor"] == pytest.approx(2 / 3, abs=1e-4)
    # Bread in the town store gives this resident a walk to the store.
    w.set_stock("bread", 5)
    moves = [o for o in w.actor_affordances("Ada") if o["action"] == "move"]
    assert moves, "a walk to the store is offered at this reserve"
    assert all(o["exhaustion_step"] == 1.0 for o in moves)
    assert all(o["speed_factor"] == pytest.approx(2 / 3, abs=1e-4) for o in moves)


def test_with_slow_on_off_there_is_no_slowdown():
    w = World(autonomous_actors=False, exhaustion_slow_on=False)
    cells = sorted(w._map_cells)
    w.add_actor("Ada", role="hand", home_cell=cells[len(cells) // 2])
    _flat_ground(w)
    assert w.body_state("Ada")["exhaustion_step"] == 0
    assert _walk_turns(w, "Ada", 0.3, 60) == 60


def test_the_scenario_can_switch_the_slowdown_off():
    scenario = {"id": "no_slow", "name": "No slowdown", "metadata": {"domain": "village"},
                "exhaustion": {"slow_on": False}}
    w = World(scenario=scenario, autonomous_actors=False)
    cells = sorted(w._map_cells)
    w.add_actor("Ada", role="hand", home_cell=cells[len(cells) // 2])
    assert w.eng.node(w._actors["Ada"])["attrs"]["slow_on"] == 0.0


# ------------------------------------------------------------------ collapse

def test_a_resident_below_e_collapse_collapses_where_they_stand():
    w = _resident()
    _set_reserve(w, "Ada", E.EXHAUSTION["e_collapse"] - 0.01)
    w._run()
    assert w.collapsed("Ada") and w.asleep("Ada")
    assert w.body_state("Ada")["collapsed"] is True


def test_a_collapsed_resident_is_refused_other_actions_with_the_reason():
    w = _resident()
    other = _neighbour(w, "Ada")
    _set_reserve(w, "Ada", 0.01)
    w._run()
    assert not w.major_action("Ada", "move", destination=other)
    assert _reason(w, "Ada") == "collapsed"
    assert not w.major_action("Ada", "rest")
    assert _reason(w, "Ada") == "collapsed"


def test_a_collapse_wakes_without_input_at_collapse_cap():
    w = _resident()
    _set_reserve(w, "Ada", 0.04)
    w._run()
    ticks = 0
    while w.asleep("Ada") and ticks < 100:
        w.tick()
        ticks += 1
    assert not w.asleep("Ada") and not w.collapsed("Ada")
    assert w.stamina_reserve("Ada") == pytest.approx(E.EXHAUSTION["collapse_cap"])
    gap = E.EXHAUSTION["collapse_cap"] - 0.04
    assert ticks == math.ceil(gap / E.EXHAUSTION["collapse_gain"])


def test_a_resident_who_keeps_working_after_a_collapse_falls_again():
    # Training off: a walking step trains stamina (Phase 032), which would move the e_low band boundary
    # this test walks across. The test is about exhaustion, so the capacity stays at its founding value.
    w = _resident(physical_subsystems={"training": False})
    _flat_ground(w)
    home = w.actor_position("Ada")
    other = _neighbour(w, "Ada")
    _set_reserve(w, "Ada", 0.04)
    w._run()
    while w.asleep("Ada"):
        w.tick()
    assert w.stamina_reserve("Ada") == pytest.approx(E.EXHAUSTION["collapse_cap"])
    for _ in range(40):
        if w.collapsed("Ada"):
            break
        w.actor_tick("Ada")
        destination = other if w.actor_position("Ada") != other else home
        w.major_action("Ada", "move", destination=destination)
    assert w.collapsed("Ada"), "walking at the collapse-cap reserve spends it below e_collapse"


def test_a_collapse_is_seen_by_residents_on_the_same_cell():
    w = _resident("Ada")
    w.add_actor("Bo", role="hand", home_cell=_neighbour(w, "Ada"))
    w._move_actor_to("Bo", w.actor_position("Ada"))
    _set_reserve(w, "Ada", 0.04)
    w._run()
    seen = [w.event_data(e)["kind"] for e in w.eng.neighbours(w._actors["Bo"], "observed_event")]
    assert seen == ["collapse"]
    assert not w.eng.neighbours(w._actors["Ada"], "observed_event")


# ------------------------------------------------------------------ sleep

def test_sleep_restores_to_rest_cap_and_wakes():
    w = _resident()
    _set_reserve(w, "Ada", 0.5)
    assert w.major_action("Ada", "sleep")
    assert w.asleep("Ada") and not w.collapsed("Ada")
    ticks = 0
    while w.asleep("Ada") and ticks < 100:
        w.tick()
        ticks += 1
    assert not w.asleep("Ada")
    assert w.stamina_reserve("Ada") == pytest.approx(E.EXHAUSTION["rest_cap"])
    assert ticks == math.ceil((E.EXHAUSTION["rest_cap"] - 0.5) / E.EXHAUSTION["rest_gain"])


def test_a_sleep_at_a_full_reserve_is_allowed_and_other_actions_are_refused_while_asleep():
    w = _resident()
    _set_reserve(w, "Ada", 1.0)
    # Phase 049: a sleep at a full reserve is no longer refused; it uses the slot and the time.
    assert w.major_action("Ada", "sleep")
    assert w.asleep("Ada")
    other = _neighbour(w, "Ada")
    assert not w.major_action("Ada", "move", destination=other)
    assert _reason(w, "Ada") == "asleep"
    assert not w.major_action("Ada", "rest")
    assert _reason(w, "Ada") == "asleep"
    assert not w.major_action("Ada", "sleep")
    assert _reason(w, "Ada") == "asleep"


def test_a_sleeping_resident_has_no_major_affordances():
    w = _resident()
    _set_reserve(w, "Ada", 0.5)
    w.major_action("Ada", "sleep")
    assert w.actor_affordances("Ada") == []


def test_sleep_facts_publish_lateness_from_the_clock_and_safe_at_home():
    w = _resident()
    w.eng.set_attr(w._town, "hour", 12.0)
    assert w.sleep_facts("Ada") == {"lateness": 0.0, "safe": True}
    w.eng.set_attr(w._town, "hour", 23.5)
    assert w.sleep_facts("Ada")["lateness"] == pytest.approx(2.5)
    w.eng.set_attr(w._town, "hour", 2.0)
    assert w.sleep_facts("Ada")["lateness"] == pytest.approx(5.0)
    w.eng.set_attr(w._town, "hour", 5.0)
    assert w.sleep_facts("Ada")["lateness"] == 0.0


def test_sleep_facts_are_not_safe_away_from_home_or_shelter():
    w = _resident()
    home = w.actor_position("Ada")
    far = max((c for c in w._map_cells if w.distance(home, c) is not None),
              key=lambda c: w.distance(home, c))
    w._move_actor_to("Ada", far)
    assert w.sleep_facts("Ada")["safe"] is False


def test_the_sleep_option_carries_the_facts_below_the_rested_level():
    w = _resident()
    _set_reserve(w, "Ada", 0.5)
    sleep = [o for o in w.actor_affordances("Ada") if o["action"] == "sleep"]
    assert len(sleep) == 1
    assert sleep[0]["safe"] is True and sleep[0]["lateness"] == w.sleep_facts("Ada")["lateness"]
    _set_reserve(w, "Ada", 1.0)
    assert all(o["action"] != "sleep" for o in w.actor_affordances("Ada"))


# ------------------------------------------------------------------ jobs and the backend

def test_a_sleeping_workers_job_pauses_and_resumes_after_waking():
    w = _smith_at_forge()
    assert w.start("Smith", "forge_plough")
    job = _job(w, "Smith")
    before = w.eng.node(job)["attrs"]["remaining"]
    _set_reserve(w, "Smith", 0.5)
    assert w.major_action("Smith", "sleep")
    for _ in range(3):
        w.tick()
    assert w.job_paused("Smith")
    assert w.eng.node(job)["attrs"]["remaining"] == before
    while w.asleep("Smith"):
        w.tick()
    assert not w.job_paused("Smith")
    w.tick()
    assert w.eng.node(job)["attrs"]["remaining"] == pytest.approx(before - 1.0)


def test_a_collapsed_workers_job_is_paused():
    w = _smith_at_forge()
    assert w.start("Smith", "forge_plough")
    job = _job(w, "Smith")
    before = w.eng.node(job)["attrs"]["remaining"]
    _set_reserve(w, "Smith", 0.01)
    w._run()
    assert w.collapsed("Smith") and w.job_paused("Smith")
    w.tick()
    assert w.eng.node(job)["attrs"]["remaining"] == before


def test_a_tired_worker_advances_a_timed_job_at_the_movement_speed():
    w = _smith_at_forge()
    assert w.start("Smith", "forge_plough")
    job = _job(w, "Smith")
    before = w.eng.node(job)["attrs"]["remaining"]
    _set_reserve(w, "Smith", 0.5)
    w.tick()
    assert before - w.eng.node(job)["attrs"]["remaining"] == pytest.approx(2 / 3, abs=1e-6)


def test_a_worker_below_e_low_advances_a_timed_job_at_the_slowest_rate():
    # Phase 049: a worker below e_low is not stopped; the job advances at the slowest rate (1/6 of a tick).
    w = _smith_at_forge()
    assert w.start("Smith", "forge_plough")
    job = _job(w, "Smith")
    before = w.eng.node(job)["attrs"]["remaining"]
    _set_reserve(w, "Smith", 0.1)
    w.tick()
    assert before - w.eng.node(job)["attrs"]["remaining"] == pytest.approx(1 / 6, abs=1e-6)


def test_the_simple_backend_sleeps_at_night_on_a_safe_spot():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character)
    affordances = [{"action": "sleep", "lateness": 2.0, "safe": True, "score": 0.0},
                   {"action": "rest", "score": 0.0}, {"action": "work", "score": 30}]
    context = ActorContext(character, 0, {"energy": 30, "hunger": 0}, affordances)
    assert backend.decide(context).major_action.action == "sleep"
    assert backend.last_choice["reason"] == "sleep_at_night"


def test_the_simple_backend_sleeps_before_collapse_by_day_when_safe():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character)
    affordances = [{"action": "sleep", "lateness": 0.0, "safe": True, "score": 0.0},
                   {"action": "rest", "score": 0.0}]
    context = ActorContext(character, 0, {"energy": 10, "hunger": 0}, affordances)
    assert backend.decide(context).major_action.action == "sleep"
    assert backend.last_choice["reason"] == "sleep_before_collapse"


def test_the_simple_backend_rests_when_the_spot_is_not_safe_or_energy_is_fine():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character)
    unsafe = [{"action": "sleep", "lateness": 2.0, "safe": False, "score": 0.0},
              {"action": "rest", "score": 0.0}]
    context = ActorContext(character, 0, {"energy": 30, "hunger": 0}, unsafe)
    assert backend.decide(context).major_action.action == "rest"
    assert "reason" not in backend.last_choice
    working = [{"action": "sleep", "lateness": 2.0, "safe": True, "score": 0.0},
               {"action": "move", "destination": (1, 1), "score": 30}]
    context = ActorContext(character, 1, {"energy": 60, "hunger": 0}, working)
    assert backend.decide(context).major_action.action == "move"
