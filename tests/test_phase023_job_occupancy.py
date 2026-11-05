"""Phase 023: timed jobs occupy the worker.

A worker with a timed job in progress cannot start another recipe (refusal `busy`). A job advances only on
ticks when its worker stands on the cell where the job started: walking away pauses it, and it resumes on
return. A paused job keeps its inputs and remaining ticks and spends no stamina. Eating stays allowed while
busy. The paused state is published on the actor (`job_paused`) and on the affordances.
"""
from __future__ import annotations

import math

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-9


def _ticks(name):
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
    w._move_actor_to("Smith", (x, y))
    return w


def _away_cell(w, name):
    """A map cell at least two steps from the worker's cell."""
    here = w.actor_position(name)
    for cell in sorted(w._map_cells):
        if w.distance(here, cell) is not None and w.distance(here, cell) >= 2:
            return cell
    raise AssertionError("no cell away from the worker")


def _job(w, name):
    return w.eng.neighbours(w._actor(name), "on_job")[0]


def _refusal_reason(w, name):
    return w.eng.node(w._actor(name))["attrs"]["last_outcome"]["reason"]


def test_busy_is_a_refusal_reason_in_the_pack():
    assert "busy" in E.REFUSAL_REASONS
    assert E.REFUSAL_REASONS["busy"]["description"].strip()


def test_a_second_start_while_busy_is_refused():
    w = _smith()
    assert w.start("Smith", "forge_plough")
    assert w.busy("Smith")
    assert not w.start("Smith", "forge_knife"), "one timed job at a time"
    assert not w.do("Smith", "forge_knife"), "an instant craft is refused too"


def test_a_refused_start_while_busy_publishes_the_busy_reason_and_uses_no_slot():
    w = _smith()
    assert w.major_action("Smith", "start", "forge_plough")
    assert w.busy("Smith")
    w.eng.set_attr(w._actor("Smith"), "major_action_used", 0.0)   # a fresh turn slot, no other attempt
    assert not w.major_action("Smith", "work", "forge_knife")
    assert _refusal_reason(w, "Smith") == "busy"
    assert w.actor_turn_state("Smith")["major_action_used"] is False, "the refused attempt used no slot"


def test_a_worker_who_is_busy_can_still_eat():
    w = _smith()
    w.set_stock("bread", 5)
    assert w.fetch("Smith", "bread", 1), "bread from the store into the worker's inventory"
    w.eng.set_attr(w._actor("Smith"), "hunger", 2.0)
    assert w.start("Smith", "forge_plough")
    assert w.eat("Smith", "bread"), "eating between work pulses stays allowed"
    assert w.hunger("Smith") == 0.0 and w.busy("Smith")


def test_walking_away_pauses_the_job_and_it_completes_after_return():
    w = _smith()
    assert _ticks("forge_plough") > 3
    home = w.actor_position("Smith")
    assert w.start("Smith", "forge_plough")
    w.tick(1)
    remaining_before = w.eng.node(_job(w, "Smith"))["attrs"]["remaining"]

    w._move_actor_to("Smith", _away_cell(w, "Smith"))
    assert w.job_paused("Smith")
    assert w.eng.node(w._actor("Smith"))["attrs"]["job_paused"] == 1.0
    iron, charcoal = w.qty("iron"), w.qty("charcoal")
    reserve = w.stamina_reserve("Smith")
    for _ in range(5):
        w.tick(1)
    assert w.eng.node(_job(w, "Smith"))["attrs"]["remaining"] == remaining_before, "a paused job does not advance"
    assert w.busy("Smith"), "the job is not cancelled"
    assert w.qty("iron") == iron and w.qty("charcoal") == charcoal, "its inputs are untouched"
    assert abs(w.stamina_reserve("Smith") - reserve) < TOL, "a paused job spends no stamina"
    assert w.newest_tool() is None

    w._move_actor_to("Smith", home)
    assert not w.job_paused("Smith")
    assert w.eng.node(w._actor("Smith"))["attrs"]["job_paused"] == 0.0
    for _ in range(int(remaining_before) + 1):
        w.tick(1)
    assert not w.busy("Smith") and w.newest_tool() is not None, "the plough is finished after the return"


def test_the_declared_stamina_is_spent_once_however_long_the_job_pauses():
    w = _smith()
    declared = E.recipe_exertion("forge_plough")[1]
    start = w.stamina_reserve("Smith")
    assert w.start("Smith", "forge_plough")
    home = w.actor_position("Smith")
    w.tick(1)
    w._move_actor_to("Smith", _away_cell(w, "Smith"))
    for _ in range(4):
        w.tick(1)
    w._move_actor_to("Smith", home)
    while w.busy("Smith"):
        w.eng.set_attr(w._actor("Smith"), "hunger", 0.0)
        w.tick(1)
    assert abs((start - w.stamina_reserve("Smith")) - declared) < TOL


def test_a_paused_job_shows_on_the_affordances_with_a_way_back():
    w = _smith()
    assert w.start("Smith", "forge_plough")
    w._move_actor_to("Smith", _away_cell(w, "Smith"))
    options = w.actor_affordances("Smith")
    assert options and all(option.get("job_paused") for option in options)
    back = [o for o in options if o.get("resumes_job")]
    assert len(back) == 1 and back[0]["action"] == "move"
    assert back[0]["destination"] == w.job_start_cell("Smith")


def test_a_job_short_of_its_tool_still_completes_when_the_tool_arrives():
    w = _smith()
    tool = w.workshop_tool("hammer")
    assert tool is not None
    assert w.start("Smith", "forge_plough")
    w.eng.set_attr(tool, "broken", 1.0)              # the hammer breaks while the job is underway
    for _ in range(_ticks("forge_plough") + 1):
        w.tick(1)
    assert w.busy("Smith") and w.newest_tool() is None, "the job waits for an unbroken hammer"
    w.eng.set_attr(tool, "broken", 0.0)
    w.eng.set_attr(tool, "condition", 1.0)
    w.tick(1)
    assert not w.busy("Smith") and w.newest_tool() is not None


def test_the_simple_backend_walks_back_to_a_paused_job():
    from bigville.backends import ActorContext, DeterministicBackend
    from bigville.character import CharacterDefinition

    character = CharacterDefinition(character_id="Smith", name="Smith", identity={"role": "smith"})
    backend = DeterministicBackend(character)
    context = ActorContext(character, 0, {"energy": 100, "hunger": 0}, [
        {"action": "move", "target": "target:elsewhere", "destination": (9, 9), "score": 10,
         "job_paused": True},
        {"action": "move", "target": "target:forge", "destination": (2, 2), "score": 0,
         "job_paused": True, "resumes_job": True},
    ])
    response = backend.decide(context)
    assert response.major_action.action == "move"
    assert response.major_action.params["target"] == "target:forge", "the paused job is resumed"
