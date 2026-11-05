from bigville import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario


class MoveCupToSelf:
    def score_adjustment(self, backend, context, option):
        return 100.0 if (option.get("action") == "move_object"
                         and option.get("object_id") == "water_cup"
                         and option.get("destination") == "Ruth") else 0.0


def _register_profiles():
    register_simple_profile("room_move_cup", SimplePolicy(
        allow_object_moves=True, hook=MoveCupToSelf()), replace=True)
    register_simple_profile("room_refuse", SimplePolicy(), replace=True)


def _game(profile):
    _register_profiles()
    scenario = load_scenario("restaurant_room_policy").to_dict()
    scenario["actors"] = [dict(actor, simple_profile=profile)
                          if actor["name"] == "Ruth" else actor
                          for actor in scenario["actors"]]
    return create_game(scenario=scenario, autonomous=True,
                       ticks_per_period=None)


def test_restaurant_room_policy_moves_same_physical_cup_or_refuses():
    moving = _game("room_move_cup")
    refusing = _game("room_refuse")
    for game in (moving, refusing):
        assert game.world.physical_objects() == moving.world.physical_objects()
        assert next(o for o in game.world.physical_objects() if o["id"] == "water_cup")["location"] == "table"

    # One real game turn. Ruth chooses the authored physical movement under
    # her profile; the default profile leaves the same cup on the same table.
    moving.step()
    refusing.step()
    assert next(o for o in moving.world.physical_objects() if o["id"] == "water_cup")["location"] == "Ruth"
    assert next(o for o in refusing.world.physical_objects() if o["id"] == "water_cup")["location"] == "table"

    assert moving.last_results["Ruth"] is True
    assert moving.backends["Ruth"].last_choice["object_id"] == "water_cup"
    assert moving.backends["Ruth"].last_choice["destination"] == "Ruth"
    assert refusing.backends["Ruth"].last_choice == {}
    assert moving.world.physical_object_observations("Ruth")


def test_room_policy_scenario_has_no_world_side_service_rules():
    data = load_scenario("restaurant_room_policy").to_dict()
    assert data["laws"] == data["policies"] == data["charters"] == []
    assert {item["id"] for item in data["physical_objects"]} == {"water_cup", "menu_card"}
