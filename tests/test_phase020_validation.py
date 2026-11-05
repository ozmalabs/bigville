"""Phase 020: validate before claiming the action slot; refuse malformed proposals.

A refused major action costs the actor nothing: the slot is released and the turn record removed, so
the same actor can act again in the same turn. A proposal with a missing, mistyped or nonexistent
value returns False without an exception. A failure while one actor's response is applied is
contained to that actor.
"""
from __future__ import annotations

import pytest

from bigville.backends import ActorResponse, DeterministicBackend, ProposedAction
from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld

CELL = (0, 8)
FAR_CELL = (5, 12)
NOBODY = 999999


def _town(ticks=1):
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    for _ in range(ticks):
        world.tick()
    names = sorted(world._actors)
    return world, names[0], names[1]


def _turn_snapshot(world, actor):
    state = world.actor_turn_state(actor)
    return state, len(world._turn_actions.get(actor, []))


def _other_cell(world, actor):
    here = world.actor_position(actor)
    return next(cell for cell in sorted(world._map_cells) if cell != here)


def _refused_then_acts(world, actor, action, kwargs):
    """A refused attempt returns False, leaves the slot and its record as they were, and the same
    actor can then spend the slot on a valid action in the same turn."""
    before = _turn_snapshot(world, actor)
    assert world.major_action(actor, action, **kwargs) is False
    assert _turn_snapshot(world, actor) == before, f"{action} refusal changed the turn state"
    assert world.major_action(actor, "rest", amount=1.0) is True
    assert world.actor_turn_state(actor)["major_action_kind"] == "rest"


# ------------------------------------------------------------------ refusals that cost nothing
def _scenario_move(world, actor, other):
    return "move", {"destination": NOBODY}


def _scenario_move_object(world, actor, other):
    return "move_object", {"object_id": NOBODY, "destination": "table"}


def _scenario_give(world, actor, other):
    return "give", {"recipient": other, "kind": "bread", "amount": 1.0}


def _scenario_transfer(world, actor, other):
    world._move_actor_to(other, FAR_CELL)
    return "transfer", {"source": actor, "recipient": other, "kind": "bread", "amount": 1.0}


def _scenario_put(world, actor, other):
    return "put", {"container": f"inventory:{other}", "kind": "bread", "amount": 1.0}


def _scenario_pick_up(world, actor, other):
    item = world.give_tool(other, "hoe")
    return "pick_up", {"item": item}


def _scenario_drop(world, actor, other):
    item = world.give_tool(other, "hoe")
    return "drop", {"item": item}


def _scenario_eat(world, actor, other):
    return "eat", {"kind": "bread"}


def _scenario_fetch(world, actor, other):
    return "fetch", {"kind": "unobtainium", "amount": 1.0}


def _scenario_maintain(world, actor, other):
    world._move_actor_to(actor, _other_cell(world, actor))
    return "maintain", {"name": "village_granary", "labour": 1.0}


def _scenario_care(world, actor, other):
    return "care", {"patient": other}


def _scenario_tend_animals(world, actor, other):
    world._move_actor_to(actor, _other_cell(world, actor))
    return "tend_animals", {"animal": "cow_0", "task": "milk"}


def _scenario_work(world, actor, other):
    return "work", {"action_name": "no_such_recipe"}


def _scenario_water(world, actor, other):
    crop = next(iter(world._crops.values()))
    return "water", {"target": crop}


def _scenario_harvest(world, actor, other):
    crop = next(iter(world._crops.values()))
    return "harvest", {"target": crop}


def _scenario_sow(world, actor, other):
    crop = next(name for name in E.CROPS)
    return "sow", {"target": (crop, "farm_plot_00")}


def _scenario_fertilise(world, actor, other):
    world._move_actor_to(actor, _other_cell(world, actor))
    return "fertilise", {"target": "farm_plot_00"}


def _scenario_complete_request(world, actor, other):
    return "complete_request", {"request": "no_such_request"}


SCENARIOS = {
    "move": _scenario_move, "move_object": _scenario_move_object, "give": _scenario_give,
    "transfer": _scenario_transfer, "put": _scenario_put, "pick_up": _scenario_pick_up,
    "drop": _scenario_drop, "eat": _scenario_eat, "fetch": _scenario_fetch,
    "maintain": _scenario_maintain, "care": _scenario_care, "tend_animals": _scenario_tend_animals,
    "work": _scenario_work, "water": _scenario_water, "harvest": _scenario_harvest,
    "sow": _scenario_sow, "fertilise": _scenario_fertilise,
    "complete_request": _scenario_complete_request,
}


@pytest.mark.parametrize("branch", sorted(SCENARIOS))
def test_a_refused_attempt_leaves_the_turn_slot_free_for_the_same_actor(branch):
    world, actor, other = _town()
    action, kwargs = SCENARIOS[branch](world, actor, other)
    _refused_then_acts(world, actor, action, kwargs)


def _fiscal_world():
    world = BigvilleWorld()
    for name in ("Ada", "Lord", "Ivy"):
        world.add_actor(name, role="resident" if name != "Ivy" else "clerk", home_cell=CELL)
        world.set_coin(name, 0)
    world.found_purse("treasury", "Ivy")
    world.tick()
    return world


def test_a_short_payer_still_uses_the_slot_because_arrears_are_recorded():
    world = _fiscal_world()
    tax = world.assess_obligation("council_tax", "Ada", "treasury", amount=10)
    world.set_coin("Ada", 0)
    assert world.major_action("Ada", "pay_obligation", obligation=tax) is False
    assert world.actor_turn_state("Ada")["major_action_used"] is True, "arrears are a consequence"
    assert world.eng.node(tax)["attrs"]["arrears"] == 1.0


def test_a_payment_across_the_room_is_refused_and_the_slot_stays_free():
    world = _fiscal_world()
    tax = world.assess_obligation("council_tax", "Ada", "treasury", amount=10)
    world.set_coin("Ada", 100)
    world._move_actor_to("Ivy", FAR_CELL)
    _refused_then_acts(world, "Ada", "pay_obligation", {"obligation": tax})
    assert world.eng.node(tax)["attrs"]["arrears"] == 0.0


def test_collecting_from_a_debtor_on_another_cell_is_refused_and_the_slot_stays_free():
    world = _fiscal_world()
    tax = world.assess_obligation("council_tax", "Ada", "treasury", amount=10)
    world.set_coin("Ada", 100)
    world._move_actor_to("Ada", FAR_CELL)
    _refused_then_acts(world, "Ivy", "collect", {"obligation": tax})
    assert world.coin("Ada") == 100


def test_delivering_nothing_held_is_refused_and_the_slot_stays_free():
    world = _fiscal_world()
    tax = world.assess_obligation("council_tax", "Ada", "treasury", amount=10)
    _refused_then_acts(world, "Ivy", "deliver_collected", {"obligation": tax})


def test_a_refused_attempt_releases_the_turn_record_it_created():
    world, actor, other = _town()
    action, kwargs = SCENARIOS["eat"](world, actor, other)
    count = len(world._turn_actions.get(actor, []))
    nodes = len(world.eng.nodes("MajorAction"))
    assert world.major_action(actor, action, **kwargs) is False
    assert len(world._turn_actions.get(actor, [])) == count
    assert len(world.eng.nodes("MajorAction")) == nodes


def test_an_accepted_attempt_still_spends_the_slot_and_keeps_its_record():
    world, actor, other = _town()
    assert world.major_action(actor, "rest", amount=1.0) is True
    assert world.major_action(actor, "rest", amount=1.0) is False, "the slot is already used"
    assert world.actor_turn_state(actor)["major_action_kind"] == "rest"
    assert len(world._turn_actions[actor]) == 1


# ------------------------------------------------------------------ malformed major-action arguments
MALFORMED = [
    ("move", {}), ("move", {"destination": ["x"]}), ("move", {"destination": NOBODY}),
    ("move_object", {}), ("move_object", {"object_id": ["x"], "destination": "table"}),
    ("move_object", {"object_id": NOBODY, "destination": "table"}),
    ("give", {}), ("give", {"recipient": ["x"], "kind": "bread"}),
    ("give", {"recipient": "Nobody", "kind": "bread"}), ("give", {"recipient": "other", "kind": ["bread"]}),
    ("give", {"recipient": "other", "kind": "bread", "amount": "two"}),
    ("give", {"recipient": "other", "kind": "bread", "amount": float("nan")}),
    ("transfer", {}), ("transfer", {"source": "Nobody", "recipient": "other", "kind": "bread"}),
    ("transfer", {"source": "self", "recipient": "other", "kind": {"x": 1}}),
    ("transfer", {"source": "self", "recipient": "other", "kind": "bread", "amount": None}),
    ("take", {"source": "other", "kind": "bread"}),
    ("put", {}), ("put", {"container": "nope", "kind": "bread"}), ("put", {"container": ["x"], "kind": "bread"}),
    ("put", {"container": "inventory:other", "kind": None}),
    ("pick_up", {}), ("pick_up", {"item": NOBODY}), ("pick_up", {"item": "x"}),
    ("drop", {}), ("drop", {"item": NOBODY}), ("drop", {"item": ["x"]}),
    ("eat", {"kind": 5}), ("eat", {"kind": "unobtainium"}), ("eat", {"kind": "bread", "source": ["x"]}),
    ("rest", {"amount": "lots"}), ("rest", {"amount": -1.0}),
    ("fetch", {}), ("fetch", {"kind": "bread", "amount": "x"}), ("fetch", {"kind": "bread", "source": "nope"}),
    ("build", {}), ("build", {"project": "nope"}), ("build", {"project": ["x"]}),
    ("build", {"project": "nope", "labour": None}),
    ("maintain", {}), ("maintain", {"name": "nope"}), ("maintain", {"name": ["x"]}),
    ("care", {}), ("care", {"patient": "nope"}), ("care", {"patient": None}),
    ("tend_animals", {}), ("tend_animals", {"animal": "nope", "task": "milk"}),
    ("tend_animals", {"animal": ["x"]}), ("tend_animals", {"animal": "cow_0", "task": ["milk"]}),
    ("tend_animals", {"animal": "sheep_3", "task": "milk"}),
    ("work", {}), ("work", {"action_name": ["x"]}), ("work", {"action_name": "unknown_recipe"}),
    ("water", {}), ("water", {"target": "x"}), ("water", {"target": NOBODY}), ("water", {"target": ["x"]}),
    ("harvest", {}), ("harvest", {"target": NOBODY}), ("harvest", {"target": None}),
    ("sow", {}), ("sow", {"target": None}), ("sow", {"target": ("nope", "nope")}), ("sow", {"target": "wheat"}),
    ("sow", {"target": ("wheat", ["x"])}),
    ("fertilise", {}), ("fertilise", {"target": "nope"}), ("fertilise", {"target": ["x"]}),
    ("fertilise", {"target": "farm_plot_00", "amount": "lots"}),
    ("pay_obligation", {}), ("pay_obligation", {"obligation": "5"}), ("pay_obligation", {"obligation": NOBODY}),
    ("collect", {}), ("collect", {"obligation": NOBODY}),
    ("deliver_collected", {}), ("deliver_collected", {"obligation": NOBODY}),
    ("deliver_collected", {"obligation": NOBODY, "share_bp": "all"}),
    ("complete_request", {}), ("complete_request", {"request": "nope"}),
    ("complete_request", {"request": NOBODY}), ("complete_request", {"request": ["x"]}),
]


@pytest.mark.parametrize("action,kwargs", MALFORMED, ids=[f"{a}-{i}" for i, (a, _) in enumerate(MALFORMED)])
def test_a_malformed_major_action_is_refused_without_an_exception(action, kwargs):
    world, actor, other = _town()
    kwargs = {key: (other if value == "other" else actor if value == "self" else value)
              for key, value in kwargs.items()}
    before = _turn_snapshot(world, actor)
    assert world.major_action(actor, action, **kwargs) is False
    assert _turn_snapshot(world, actor) == before


def test_the_retired_sell_branches_are_gone():
    world, actor, other = _town()
    with pytest.raises(ValueError):
        world.major_action(actor, "sell", trade="bakery", kind="bread", amount=1.0)
    with pytest.raises(ValueError):
        world.major_action(actor, "sell_labor", trade="bakery", amount=2.0)
    assert not world.actor_turn_state(actor)["major_action_used"]


# ------------------------------------------------------------------ malformed backend proposals
PLAN_ACTIONS = ["give", "transfer", "take", "rest", "eat", "work", "move", "move_object", "put", "fetch",
                "tend_animals", "build", "maintain", "care", "water", "harvest", "sow", "fertilise"]
PLAN_SHAPES = [
    {},
    {"kind": 5, "recipe": 3, "target": ["x"], "amount": "lots"},
    {"kind": None, "recipe": None, "target": "nobody", "destination": ["x"], "animal": {"a": 1}},
    {"target": "nobody", "crop_node": "7", "sow_kind": ["wheat"], "land": 4, "project": NOBODY},
    {"kind": "bread", "recipe": "no_such_recipe", "target": NOBODY, "patient": NOBODY, "name": NOBODY},
]


@pytest.mark.parametrize("shape", range(len(PLAN_SHAPES)))
@pytest.mark.parametrize("action", PLAN_ACTIONS)
def test_a_malformed_backend_plan_is_refused_without_an_exception(action, shape):
    world, actor, other = _town()
    before = _turn_snapshot(world, actor)
    plan = {"action": action, **PLAN_SHAPES[shape]}
    assert world.enact_plan(actor, plan) is False
    assert _turn_snapshot(world, actor) == before


def test_a_plan_without_an_action_key_is_refused():
    world, actor, other = _town()
    assert world.enact_plan(actor, {"kind": "bread"}) is False
    assert world.enact_plan(actor, {"action": None}) is False


# ------------------------------------------------------------------ animal care: wrong species
def test_milking_a_sheep_or_shearing_a_cow_is_refused_not_an_assertion():
    world, actor, other = _town()
    world._move_actor_to(actor, world.map_position_node(world._animals["sheep_3"]))
    assert world.milk(actor, "sheep_3") == 0.0
    assert world.major_action(actor, "tend_animals", animal="sheep_3", task="milk") is False
    assert not world.actor_turn_state(actor)["major_action_used"]
    world._move_actor_to(actor, world.map_position_node(world._animals["cow_0"]))
    assert world.shear(actor, "cow_0") == 0.0


# ------------------------------------------------------------------ parity: published options can be enacted
def test_every_published_option_of_a_seeded_village_actor_can_be_enacted_on_a_fresh_copy():
    """Each option from actor_affordances is enacted on a newly built town in the same state. The
    boundary audit says published options can succeed, so each must return True here."""
    base, _, _ = _town()
    failures = []
    for actor in sorted(base._actors)[:3]:
        base.actor_tick(actor)
        for option in base.actor_affordances(actor):
            fresh, _, _ = _town()
            fresh.actor_tick(actor)
            if fresh.enact_plan(actor, dict(option)) is not True:
                failures.append((actor, option["action"], option))
    assert failures == []


# ------------------------------------------------------------------ containment in BigvilleGame.step
class _FixedBackend(DeterministicBackend):
    """A backend that always proposes one move; it keeps DeterministicBackend's held-state API."""

    def __init__(self, character, destination):
        super().__init__(character)
        self.destination = destination

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("move", {"destination": self.destination}))


def test_one_actors_failure_is_contained_and_the_other_actor_and_turn_still_apply(monkeypatch):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world)
    game.set_backend("Ada", _FixedBackend(game.characters["Ada"], (2, 1)))
    game.set_backend("Ben", _FixedBackend(game.characters["Ben"], (2, 1)))
    original = world.enact_plan

    def failing_for_ben(actor, plan):
        if actor == "Ben":
            raise RuntimeError("boom")
        return original(actor, plan)

    monkeypatch.setattr(world, "enact_plan", failing_for_ben)
    turn = world._turn
    status = game.step()
    assert status["status"] == "advanced"
    assert world._turn == turn + 1
    assert game.last_results["Ben"] is False
    assert game.last_results["Ada"] is True
    assert "RuntimeError: boom" in game.last_errors["Ben"]
    assert "Ada" not in game.last_errors
    assert world.actor_position("Ada") == (2, 1)
    assert world.actor_position("Ben") == (1, 1)
