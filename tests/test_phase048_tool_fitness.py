"""Phase 048: tools by fitness. The right tool at full quality and condition does today's job in today's time; any other
object, or none, gives what it physically gives, and the world charges for the difference (time, stamina, strain,
wear, yield). A missing tool is never a refusal of its own. `stop` abandons a hopeless job. Nothing here is random."""
from __future__ import annotations

import math
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains import bigville_entities as E  # noqa: E402
from worlds import resolution as R  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402
from bigville.backends.cheap import SimplePolicy  # noqa: E402
from bigville.reporting import SimulationReporter  # noqa: E402

TICK_CAP = 400


def _inside(w, key):
    x, y, fw, fh = w._building_sites[key]
    return next((x + dx, y + dy) for dy in range(fh) for dx in range(fw) if (x + dx, y + dy) in w._map_cells)


def _smith(skill=0.9):
    w = World()
    w.add_actor("Smith", role="smith", skill=skill)
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)      # forge_plough needs strength 1.2 (Phase 032)
    w.set_stock("iron", 20)
    w.set_stock("charcoal", 20)
    w._move_actor_to("Smith", _inside(w, "forge"))
    return w


def _carver(skill=0.9):
    w = World()
    w.add_actor("Carver", role="woodworker", skill=skill)
    w.set_stock("timber", 10)
    w._move_actor_to("Carver", _inside(w, "woodshop"))
    return w


def _rest(w, name):
    """Give the resident its full reserve and wake it, so a test isolates the tool from exhaustion."""
    w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors[name], "collapsed", 0.0)
    w.eng.set_attr(w._actors[name], "asleep", 0.0)


def _job(w, name):
    return w._job_of(name)


def _remaining(w, name):
    return float(w.eng.node(_job(w, name))["attrs"]["remaining"])


def _ticks_to_finish(w, name, cap=TICK_CAP):
    """Tick until the worker is no longer busy, resting the worker between ticks. Returns the ticks taken."""
    ticks = 0
    while w.busy(name) and ticks < cap:
        _rest(w, name)
        w.tick(1)
        ticks += 1
    return ticks


# ----------------------------------------------------------------- the pure rules

def test_a_fine_tool_fits_at_one_and_its_effort_is_the_declared_cost():
    assert R.fitness(1.0, 1.0, 1.0) == 1.0
    assert R.effort_multiplier(1.0, 3.0) == 1.0
    assert R.fit_quality(0.8, 1.0, 0.5) == 0.8, "a fit of 1 leaves the quality exactly as it was"
    assert R.tool_wear_excess(0.02, 1.0, 1.0, 4.0, 1.0) == 0.0, "a fitting tool has no excess wear"


def test_fitness_never_rises_with_quality_or_condition_and_effort_never_rises_with_fit():
    grid = [i / 10.0 for i in range(0, 11)]
    for physical in (0.3, 1.0):
        by_quality = [R.fitness(physical, q, 1.0) for q in grid]
        by_condition = [R.fitness(physical, 1.0, c) for c in grid]
        assert by_quality == sorted(by_quality) and by_condition == sorted(by_condition)
    efforts = [R.effort_multiplier(f, 3.0) for f in grid[1:]]
    assert efforts == sorted(efforts, reverse=True)
    assert R.effort_multiplier(0.05, 3.0) == 3.0, "bare hands cost the cap (the seed's effort about 3)"


def test_hardness_and_edge_and_weight_terms_are_zero_or_reduced_for_the_wrong_material_or_shape():
    zero_gap = float(E.TOOL_FIT["hardness_zero_gap"])
    assert R.hardness_term(0.3, 0.6, zero_gap) == 0.0, "wood against iron gives no fit"
    assert R.hardness_term(0.6, 0.3, zero_gap) == 1.0, "iron against wood is no softer than the work"
    assert R.edge_term("cut", E.TOOL_FIT["edge_verbs"], False, E.TOOL_FIT["no_edge"]) == E.TOOL_FIT["no_edge"]
    assert R.edge_term("strike", E.TOOL_FIT["edge_verbs"], False, E.TOOL_FIT["no_edge"]) == 1.0
    assert R.weight_term("strike", E.TOOL_FIT["weight_verbs"], 0.1, E.TOOL_FIT["min_weight"]) == 0.2


def test_a_worn_or_poor_fit_gives_less_quality_and_wastes_below_the_line():
    assert R.fit_quality(0.8, 0.5, 0.5) == 0.8 * (1.0 - 0.5 * 0.5)
    assert R.fit_yield(0.1, 0.25) == 0.0 and R.fit_wasted(0.1, 0.25)
    assert R.fit_yield(0.5, 0.25) == 0.5 and not R.fit_wasted(0.5, 0.25)


def test_every_verb_in_a_recipe_tool_slot_has_a_closeness_row():
    verbs = set(E.TOOL_FIT["verbs"])
    for recipe in E.RECIPES:
        for kind in recipe.get("tools", []):
            assert E.ITEMS[kind]["verb"] in verbs, (recipe["name"], kind)


def test_the_simple_backend_does_not_improvise_by_default():
    assert SimplePolicy().improvise is False


# ----------------------------------------------------------------- the right tool and poorer ones

def test_the_right_tool_at_full_quality_and_condition_takes_the_committed_time():
    w = _carver()
    w.give_tool("Carver", "knife")
    assert w._tool_fit(w._held_tool("Carver", "knife"), "cut", 0.6, "knife") == (1.0, 1.0)
    minutes = float(next(r for r in E.RECIPES if r["name"] == "carve_wooden_mug")["time_minutes"])
    assert w.start("Carver", "carve_wooden_mug", tool="knife")
    assert _ticks_to_finish(w, "Carver") == math.ceil(minutes / float(E.TIME["minutes_per_tick"]))


def test_a_poor_or_worn_hammer_is_slower_than_a_fine_one():
    times = {}
    for label, quality, condition in (("fine", 1.0, 1.0), ("poor", 0.5, 1.0), ("worn", 1.0, 0.5)):
        w = _smith()
        hammer = w.give_tool("Smith", "hammer", quality=quality)
        w.eng.set_attr(hammer, "condition", condition)
        assert w.start("Smith", "forge_plough", tool="hammer")
        times[label] = _ticks_to_finish(w, "Smith")
    assert times["fine"] < times["poor"] and times["fine"] < times["worn"]
    assert times["poor"] >= 2 * times["fine"] - 1, "half the fitness takes about twice the ticks"


def test_a_cleaver_is_faster_than_bare_hands_and_slower_than_a_knife_for_knife_work():
    times = {}
    for label, held in (("knife", "knife"), ("cleaver", "cleaver")):
        w = _carver()
        w.give_tool("Carver", held)
        assert w.start("Carver", "carve_wooden_mug", tool=held)
        times[label] = _ticks_to_finish(w, "Carver")
    assert times["knife"] < times["cleaver"]
    w = _carver()
    assert w.start("Carver", "carve_wooden_mug", tool="none")
    before = _remaining(w, "Carver")
    w.tick(1)
    per_tick_hands = before - _remaining(w, "Carver")
    assert per_tick_hands == pytest.approx(float(E.RESOLUTION["hands_fit"])), "bare hands: 0.05 of a tick's work"
    assert per_tick_hands < 0.7, "the cleaver's 0.7 of a tick is faster than bare hands"


# ----------------------------------------------------------------- bare hands and the wrong tool

def test_no_tool_at_all_is_allowed_and_progresses_at_the_bare_hand_fitness_at_triple_effort():
    w = _carver()
    assert w.start("Carver", "carve_wooden_mug", tool="none")
    job = _job(w, "Carver")
    before = _remaining(w, "Carver")
    w.tick(1)
    assert before - _remaining(w, "Carver") == pytest.approx(float(E.RESOLUTION["hands_fit"]))
    assert float(w.eng.node(job)["attrs"]["effort_mult"]) == 3.0, "bare hands pay the effort cap"


def test_a_wooden_tool_on_a_locked_iron_lock_makes_no_progress_wears_snaps_and_hurts_the_worker():
    w = World(autonomous_actors=False)
    cells = sorted(w._map_cells)
    w.add_actor("Ada", role="hand", home_cell=cells[len(cells) // 2])
    here = w.actor_position("Ada")
    w.add_container("box", kind="chest", holds=["grain"], lock_id=1, locked=True, cell=here)
    board = w.give_tool("Ada", "board")                     # wood, a knead verb: no closeness to a pierce
    health = w.health("Ada")
    progress_seen = []
    for _ in range(12):
        if w.tool_broken(board):
            break
        _rest(w, "Ada")
        w.actor_tick("Ada")
        w.major_action("Ada", "attempt", verb="pry", target="box", with_kind="board", intensity=1.0)
        node = w._containers["box"][0]
        progress_seen.append(float(w.eng.node(node)["attrs"].get("lock_progress", 0.0)))
    assert progress_seen and all(p == 0.0 for p in progress_seen), "no progress against iron"
    assert w.eng.node(w._containers["box"][0])["attrs"]["locked"] == 1.0
    assert w.tool_broken(board), "the wooden tool snaps"
    assert w.health("Ada") < health, "the worker is hurt through strain"
    assert w.tool_tally()["accidents"] >= 1 and w.tool_tally()["broken_tools"] >= 1


def test_a_job_that_stalls_on_bare_hands_is_stopped_by_the_stop_action():
    w = _carver()
    assert w.start("Carver", "carve_wooden_mug", tool="none")
    w.tick(2)
    assert w.busy("Carver")
    assert w.free_action("Carver", "stop") is True
    assert not w.busy("Carver")
    assert w.qty("timber") == 10.0, "the inputs are taken at completion, so a stopped job keeps them"
    assert w.free_action("Carver", "stop") is False, "there is no job left to stop"


# ----------------------------------------------------------------- the proposal and the backend

def test_the_proposal_tool_names_the_held_tool_bare_hands_or_is_refused():
    w = _smith()
    shelf = w.workshop_tool("hammer", building="forge")
    held = w.give_tool("Smith", "hammer")
    assert w.start("Smith", "forge_nails", tool="hammer")
    assert _ticks_to_finish(w, "Smith") >= 1
    assert w.tool_condition(held) < 1.0 and w.tool_condition(shelf) == 1.0, "the held hammer was the one used"
    # Phase 049: a saw the smith does not hold is no refusal; that job runs on bare hands at hands_fit.
    assert w.start("Smith", "forge_nails", tool="saw")
    hands = [j for j in w.eng.neighbours(w._actor("Smith"), "on_job") if w.eng.node(j)["attrs"]["tool_mode"] == "hands"]
    assert len(hands) == 1 and float(w.eng.node(hands[0])["attrs"]["fit"]) == float(E.RESOLUTION["hands_fit"])
    assert not w.start("Smith", "forge_nails", tool=3)
    assert w._refusal_code == "malformed"


def test_the_work_proposal_passes_its_tool_through_enactment():
    w = _carver()
    assert w._enact_plan("Carver", {"action": "work", "recipe": "carve_wooden_mug", "tool": "none"})
    assert w.busy("Carver")
    assert float(w.eng.node(_job(w, "Carver"))["attrs"]["fit"]) == float(E.RESOLUTION["hands_fit"])


def test_a_recipe_offer_still_wants_a_usable_tool_so_the_default_backend_is_unchanged():
    w = _smith()
    for item in list(w.eng.neighbours(w._places["forge"], "has_tool_item")):
        w.eng.remove_edge_unchecked(w._places["forge"], "has_tool_item", item)
    offers = [o for o in w._actor_options("Smith") if o.get("recipe") == "forge_nails"]
    assert offers == [], "no hammer, no offer: the simple backend's choices do not change"


def test_improvised_work_and_accidents_are_counted_for_the_reporter():
    w = _carver()
    assert w.start("Carver", "carve_wooden_mug", tool="none")
    _ticks_to_finish(w, "Carver", cap=40)
    counts = SimulationReporter(w).improvised_work()
    assert counts["improvised_jobs"] == 1
    assert counts["accidents"] >= 1, "bare hands strain the worker into accidents"
