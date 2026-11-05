"""A simple resident needs an explicit social policy to give carried goods."""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario


class _ChooseTransfer:
    def score_adjustment(self, backend, context, option):
        return 1000.0 if option.get("action") == "transfer" else -1000.0


def _game(*, profile=None):
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["actors"].append({
        "name": "Ben", "role": "hand", "backend": "simple", "home_cell": [2, 2],
    })
    if profile:
        scenario["actors"][0]["simple_profile"] = profile
    game = create_game(scenario=scenario, seed=905, autonomous=True,
                       ticks_per_period=None)
    world = game.world
    world.set_stock("apple", 1)
    assert world._move_stock_to_inventory("Ada", "apple", 1)
    return game


def test_default_simple_resident_keeps_carried_food_without_social_intent():
    game = _game()
    assert any(option["action"] == "transfer" for option in game._context("Ada").affordances)

    result = game.step()

    response = game.last_responses["Ada"]
    assert response.major_action is None or response.major_action.action != "transfer"
    assert result["results"]["Ada"]
    assert game.world.inventory_qty("Ada", "apple") == 1.0
    assert game.world.inventory_qty("Ben", "apple") == 0.0


def test_configured_social_policy_can_choose_a_physical_transfer():
    register_simple_profile(
        "test.transfer_intent",
        SimplePolicy(hook=_ChooseTransfer(), allow_transfers=True),
        replace=True,
    )
    game = _game(profile="test.transfer_intent")

    result = game.step()

    response = game.last_responses["Ada"]
    assert response.major_action is not None
    assert response.major_action.action == "transfer"
    assert result["results"]["Ada"]
    assert game.world.inventory_qty("Ada", "apple") == 0.0
    assert game.world.inventory_qty("Ben", "apple") == 1.0
