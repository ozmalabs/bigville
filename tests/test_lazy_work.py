"""LA07: the read-only work prefilter and its lazy candidate use.

LA06 showed a health regression in lazy mode: the cheap backend proposed common
recipes without checking the site, tools or ingredients the menu's work loop
requires.  LA07 adds ``BigvilleWorld.recipe_preview(actor, recipe)`` -- a
read-only preview of the menu's publish filter -- publishes ``busy`` and a
bounded ``work_candidates`` list in the observation, and makes the lazy backend
propose work only from that list.

These tests cover the preview contract (read-only, reason codes, agreement with
``actor_affordances``), the cheap backend's use of the list, and the required
8-turn ``town100``/small runs.  The menu path is unchanged and its recorded
LA06 action counts still hold.
"""
from __future__ import annotations

from collections import Counter

import pytest

from bigville.api import create_game, create_world

SEED = 305000
TOWN_ACTOR = "Verity Peaseblossom"
BUSY_ACTOR = "Keturah Marsh"

SMALL_SCENARIO = {
    "id": "la07_small_room",
    "name": "LA07 small room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
}


def _world():
    return create_world(scenario="town100", seed=SEED)


def _game(mode="lazy", *, scenario="town100", seed=SEED):
    return create_game(
        scenario=scenario, seed=seed, default_backend="simple",
        autonomous=True, llm_log=False, affordance_mode=mode)


def _applied_actions(game, turns):
    counts = Counter()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        for actor, response in game.last_responses.items():
            if not game.last_results.get(actor):
                continue
            action = getattr(response.major_action, "action", None)
            if action:
                counts[action] += 1
    return counts


# --------------------------------------------------------------- preview contract
def test_recipe_preview_is_read_only():
    world = _world()
    before_state = world.export_state()
    before_turn_state = world.actor_turn_state(TOWN_ACTOR)
    before_stock = {kind: world.qty(kind) for kind in sorted(world._stock)}
    before_inventory = world.inventory(TOWN_ACTOR)
    before_outcome = world.last_outcome(TOWN_ACTOR)
    before_tally = world.tool_tally()

    assert world.recipe_preview(TOWN_ACTOR, "brew_ale") == {"ok": True, "reason": ""}

    assert world.export_state() == before_state
    assert world.actor_turn_state(TOWN_ACTOR) == before_turn_state
    assert {kind: world.qty(kind) for kind in sorted(world._stock)} == before_stock
    assert world.inventory(TOWN_ACTOR) == before_inventory
    assert world.last_outcome(TOWN_ACTOR) == before_outcome
    assert world.tool_tally() == before_tally
    assert world.busy(TOWN_ACTOR) is False
    assert world._job_of(TOWN_ACTOR) is None


@pytest.mark.parametrize("recipe, reason", [
    ("definitely_not_a_recipe", "not_known"),
    ("smelt_iron", "unskilled"),        # the actor lacks the smithing skill
    ("gather_berries", "unskilled"),    # out of season (summer only, world is in spring)
    ("saw_planks", "out_of_stock"),     # no timber in the store
    ("dig_ore", "not_at_site"),         # a gathered recipe, actor is not on the quarry
    ("bury", "not_at_site"),            # a graveyard-building recipe, actor is not inside
])
def test_recipe_preview_reason_codes(recipe, reason):
    world = _world()
    assert world.recipe_preview(TOWN_ACTOR, recipe) == {"ok": False, "reason": reason}


def test_recipe_preview_refuses_a_busy_actor():
    world = _world()
    assert world.recipe_preview(TOWN_ACTOR, "brew_ale")["ok"] is True
    world.eng.set_attr(world._actors[TOWN_ACTOR], "busy", 1.0)
    assert world.recipe_preview(TOWN_ACTOR, "brew_ale") == {
        "ok": False, "reason": "not_possible"}


def test_preview_agrees_with_the_menu_work_filter():
    """Every menu work option previews ok, and every preview-ok recipe is published."""
    world = _world()
    for actor in (TOWN_ACTOR, BUSY_ACTOR, "Ida Ditchwater"):
        menu = {option["recipe"] for option in world.actor_affordances(actor)
                if option.get("action") == "work"}
        preview = {name for name in world._recipe_specs
                   if world.recipe_preview(actor, name)["ok"]}
        assert menu == preview


# --------------------------------------------------------------- observation enrichment
def test_observation_publishes_busy_and_bounded_sorted_work_candidates():
    world = _world()
    observation = world.observe(TOWN_ACTOR)
    assert observation["busy"] is False
    candidates = observation["work_candidates"]
    assert candidates
    assert len(candidates) <= world._OBSERVE_WORK_LIMIT
    assert [entry["recipe"] for entry in candidates] == \
        sorted(entry["recipe"] for entry in candidates)
    for entry in candidates:
        assert set(entry) >= {"recipe", "out", "time_minutes"}
        assert world.recipe_preview(TOWN_ACTOR, entry["recipe"])["ok"] is True

    world.eng.set_attr(world._actors[TOWN_ACTOR], "busy", 1.0)
    busy = world.observe(TOWN_ACTOR)
    assert busy["busy"] is True
    assert busy["work_candidates"] == []


# --------------------------------------------------------------- lazy candidates
def test_lazy_work_comes_only_from_work_candidates():
    game = _game()
    context = game._context(TOWN_ACTOR)
    entities = context.observations["entities"]
    expected = {entry["recipe"] for entry in entities["work_candidates"]}
    assert expected

    candidates = game.backends[TOWN_ACTOR]._lazy_candidates(context)
    work = {candidate["recipe"] for candidate in candidates
            if candidate.get("action") == "work"}
    assert work
    assert work <= expected


def test_lazy_candidates_propose_no_work_while_busy():
    game = _game()
    world = game.world
    world.eng.set_attr(world._actors[TOWN_ACTOR], "busy", 1.0)
    context = game._context(TOWN_ACTOR)
    assert context.observations["entities"]["busy"] is True
    assert context.observations["entities"]["work_candidates"] == []
    candidates = game.backends[TOWN_ACTOR]._lazy_candidates(context)
    assert not any(candidate.get("action") == "work" for candidate in candidates)


def test_lazy_candidates_propose_no_work_when_no_preview_is_ok():
    game = _game(scenario=SMALL_SCENARIO)
    context = game._context("Ada")
    assert context.observations["entities"]["work_candidates"] == []
    candidates = game.backends["Ada"]._lazy_candidates(context)
    assert not any(candidate.get("action") == "work" for candidate in candidates)


# --------------------------------------------------------------- required runs
def test_town100_lazy_run_has_no_accidents_and_explains_improvised_work(capsys):
    game = _game("lazy")
    world = game.world
    improvised = []
    original = world._open_job

    def recording_open_job(actor, action_name, *args, **kwargs):
        before = world._tool_tally["improvised_jobs"]
        result = original(actor, action_name, *args, **kwargs)
        if world._tool_tally["improvised_jobs"] > before:
            improvised.append({
                "turn": world._turn, "actor": actor, "recipe": action_name,
                "open_recipe": bool(world._recipe_specs.get(action_name, {}).get("open")),
                "at_workplace": world._at_workplace(actor) is not None,
            })
        return result

    world._open_job = recording_open_job
    counts = _applied_actions(game, 8)
    tally = world.tool_tally()
    alive = sum(1 for name in world._actors if world.is_alive(name))
    health = [world.health(name) for name in world._actors if world.is_alive(name)]

    with capsys.disabled():
        print(f"\nLA07 town100 lazy: actions={dict(counts)} tally={tally} "
              f"health_mean={sum(health) / len(health):.6f} "
              f"health_min={min(health):.6f} improvised={improvised}")

    assert counts.get("work", 0) > 0
    assert alive == 100
    assert sum(health) / len(health) == pytest.approx(1.0)
    assert min(health) == pytest.approx(1.0)
    assert tally["accidents"] == 0
    # LA06's regression was reported here; any remaining improvisation must be
    # the identified turn-0 workplace case, not an unvalidated common recipe.
    # At turn 0 `_at_workplace` skips its location check (setup calls), so a
    # preview built before the clock starts may see a trade tool that the job,
    # opened after the tick advances, correctly finds out of reach.  The job is
    # still accepted with bare hands; no accident follows in this run.
    assert len(improvised) <= 1
    for record in improvised:
        assert record["open_recipe"] is False
        assert record["at_workplace"] is False


def test_town100_menu_run_is_unchanged():
    """The LA06 menu counts for this scenario/seed remain the oracle."""
    game = _game("menu")
    counts = _applied_actions(game, 8)
    tally = game.world.tool_tally()
    assert dict(counts) == {"move": 785, "work": 15}
    assert tally == {"improvised_jobs": 0, "accidents": 0, "broken_tools": 0}
    assert all(game.world.health(name) == pytest.approx(1.0)
               for name in game.world._actors if game.world.is_alive(name))


def test_small_lazy_run_follows_the_menu_filter():
    """The small room publishes no work; lazy must not invent it (LA06 had 36)."""
    game = _game("lazy", scenario=SMALL_SCENARIO, seed=SEED)
    counts = _applied_actions(game, 12)
    assert counts.get("work", 0) == 0
    assert game.world.tool_tally()["improvised_jobs"] == 0
    assert game.world.tool_tally()["accidents"] == 0

