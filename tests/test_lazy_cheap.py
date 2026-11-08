"""LA04: lazy cognition for the deterministic simple backend.

In ``affordance_mode="lazy"`` the cheap backend proposes from needs and the
LA03 observation instead of receiving the exhaustive menu.  The world still
validates every proposal; a refusal is ordinary feedback and the next lazy
turn makes a fresh, safer proposal.

The tests here exercise the local candidate list, the direct stable params it
uses, the refusal fallback, and the unchanged menu path.  A short town100 run
reports refusal counts without asserting a fixed number.
"""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends.cheap import SimplePolicy
from bigville.tick_trace import TurnTrace, semantic_step_trace
from domains import bigville_entities as E


SMALL_SCENARIO = {
    "id": "la04_lazy_room",
    "name": "LA04 lazy room",
    "map": {"grid": [["floor"] * 8 for _ in range(8)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "apple", "name": "apple", "kind": "apple", "location": "table"},
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": True},
        {"id": "coin", "name": "coin", "kind": "coin", "location": "box"},
    ],
}

MENU_SCENARIO = {
    "id": "la01_mode_room",
    "name": "LA01 mode room",
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

# Recorded at LA01 and still the menu oracle after LA03.
MENU_DIGEST_AT_LA01 = "86eec11eb25be8d61856211eea76bcb7ce19da358303505bb3a1a4e045fe9291"


def _game(policy: SimplePolicy | None = None, *, scenario=None, seed=305001,
          mode="lazy"):
    game = create_game(
        scenario=scenario or SMALL_SCENARIO, seed=seed,
        default_backend="simple", autonomous=True, llm_log=False,
        affordance_mode=mode)
    if policy is not None:
        for backend in game.backends.values():
            if getattr(backend, "kind", "") == "cheap":
                backend.policy = policy
    return game


def _seed_inventory(world, actor, kind, qty=1.0):
    stock = world._inventory_stock(actor, kind, create=True)
    world.eng.set_attr(stock, "qty", float(qty))


def _candidates(game, actor="Ada"):
    backend = game.backends[actor]
    return backend, backend._lazy_candidates(game._context(actor))


def _actions(candidates):
    return {str(candidate.get("action")) for candidate in candidates}


# ------------------------------------------------------------------ needs
def test_hungry_resident_proposes_the_carried_edible():
    game = _game()
    _seed_inventory(game.world, "Ada", "bread", 2.0)
    game.world.eng.set_attr(game.world._actors["Ada"], "hunger", 2.0)

    backend, candidates = _candidates(game)
    eat = next(item for item in candidates
               if item["action"] == "eat" and item["kind"] == "bread")
    assert eat["meal_value"] > 0.0
    response = backend.decide(game._context("Ada"))
    assert response.major_action is not None
    assert response.major_action.action == "eat"
    assert response.major_action.params["kind"] == "bread"


def test_tired_resident_rests_by_day_and_sleeps_at_night():
    day = _game()
    day.world.eng.set_attr(day.world._bodies["Ada"], "stamina_reserve", 0.30)
    _, candidates = _candidates(day)
    assert "rest" in _actions(candidates)
    assert "sleep" not in _actions(candidates)
    response = day.backends["Ada"].decide(day._context("Ada"))
    assert response.major_action.action == "rest"

    night = _game()
    night.world.eng.set_attr(night.world._town, "hour", 22.0)
    night.world.eng.set_attr(night.world._bodies["Ada"], "stamina_reserve", 0.35)
    _, candidates = _candidates(night)
    assert "sleep" in _actions(candidates)
    response = night.backends["Ada"].decide(night._context("Ada"))
    assert response.major_action.action == "sleep"

    collapsed = _game()
    collapsed.world.eng.set_attr(collapsed.world._bodies["Ada"],
                                 "stamina_reserve", 0.0)
    _, candidates = _candidates(collapsed)
    assert "sleep" in _actions(candidates)


# ------------------------------------------------------------------ local entities
def test_visible_object_proposes_move_object_to_self():
    game = _game(SimplePolicy(allow_object_moves=True))
    _, candidates = _candidates(game)
    move = next(item for item in candidates
                if item["action"] == "move_object" and item["object_id"] == "apple")
    assert move["destination"] == "Ada"
    # The same object can also be moved to the shared world or a nearby actor.
    destinations = {item["destination"] for item in candidates
                    if item["action"] == "move_object" and item["object_id"] == "apple"}
    assert {"Ada", "world"} <= destinations


def test_co_located_actor_proposes_give_or_transfer():
    game = _game()
    _seed_inventory(game.world, "Ada", "bread", 2.0)
    game.world._move_actor_to("Ben", game.world.actor_position("Ada"))
    _, candidates = _candidates(game)
    social = [item for item in candidates
              if item["action"] in {"give", "transfer"}
              and item.get("recipient") == "Ben"
              and item.get("kind") == "bread"]
    assert social


def test_world_container_proposes_fetch_and_put():
    game = _game()
    world = game.world
    world.add_container("la04_barrel", kind="barrel", holds="bread",
                        cell=world.actor_position("Ada"))
    world.eng.set_attr(world._containers["la04_barrel"][1]["bread"], "qty", 3.0)
    _seed_inventory(world, "Ada", "apple", 2.0)

    _, candidates = _candidates(game)
    fetch = next(item for item in candidates
                 if item["action"] == "fetch" and item["kind"] == "bread")
    assert fetch["source"] == "la04_barrel"
    assert fetch["physical_source"] == "container"
    put = next(item for item in candidates
               if item["action"] == "put" and item["kind"] == "apple")
    assert put["container"] == "la04_barrel"
    # Hunger consumes a container's food through a fetch, never an invented
    # direct eat-from-container action.
    assert not any(item["action"] == "eat" and item.get("container")
                   for item in candidates)


def test_cell_work_candidates_use_stable_ids():
    game = _game(scenario="town100", seed=305000)
    world = game.world
    actor = sorted(world._actors)[0]
    animal = next(iter(world._animals))
    world._move_actor_to(actor, world.map_position_node(world._animals[animal]))
    backend, candidates = _candidates(game, actor)
    tend = next(item for item in candidates if item["action"] == "tend_animals")
    assert tend["animal"] in world._animals
    assert world.map_position_node(world._animals[tend["animal"]]) == \
        world.actor_position(actor)
    assert str(tend["kind"])

    crop = next(iter(world._living_crops()))
    world._move_actor_to(actor, world.map_position_node(crop))
    world.eng.set_attr(crop, "thirst", 1.0)
    backend, candidates = _candidates(game, actor)
    assert any(item["action"] == "water" and item["crop_node"] == int(crop)
               for item in candidates)


# ------------------------------------------------------------------ direct params / bounds
def test_candidates_use_direct_params_and_never_target_keys():
    game = _game(SimplePolicy(allow_object_moves=True))
    world = game.world
    _seed_inventory(world, "Ada", "bread", 1.0)
    world.add_container("la04_barrel", kind="barrel", holds="bread",
                        cell=world.actor_position("Ada"))
    world._move_actor_to("Ben", world.actor_position("Ada"))
    _, candidates = _candidates(game)
    assert candidates
    for candidate in candidates:
        for key, value in candidate.items():
            assert not (isinstance(value, str) and value.startswith("target:")), \
                f"{key}={value!r} is an ephemeral menu key"
        assert "action" in candidate


def test_candidate_list_is_bounded_and_deterministic():
    game = _game(SimplePolicy(allow_object_moves=True))
    backend = game.backends["Ada"]
    context = game._context("Ada")
    first = backend._lazy_candidates(context)
    second = backend._lazy_candidates(context)
    assert first == second
    assert len(first) <= backend._LAZY_MAX_CANDIDATES
    assert len({backend._candidate_sort_key(item) for item in first}) == len(first)


# ------------------------------------------------------------------ refusal fallback
def test_refused_proposal_does_not_advance_into_the_next_turn():
    game = _game()
    backend = game.backends["Ada"]
    invalid = {
        "action": "move", "kind": "", "trade": "", "recipe": "",
        "target": "cell:99,99", "destination": (99, 99), "score": 1000.0,
    }

    def _always_invalid(context):
        return [dict(invalid)]

    backend._lazy_candidates = _always_invalid
    first = game.step()
    assert first["status"] == "advanced"
    assert game.last_results["Ada"] is False
    outcome = game.world.last_outcome("Ada")
    assert outcome["applied"] is False
    assert outcome["reason"] in E.REFUSAL_REASONS

    second = game.step()
    assert second["status"] == "advanced"
    # The exact refused move is filtered from the second candidate list; the
    # lazy fallback makes a fresh proposal (here an adjacent cell).
    assert backend.last_choice["action"] != "move" or \
        backend.last_choice.get("destination") != (99, 99)
    assert backend.last_choice.get("destination") != (99, 99)


# ------------------------------------------------------------------ menu path unchanged
def test_menu_mode_never_builds_lazy_candidates():
    game = _game(scenario=SMALL_SCENARIO, mode="menu")
    backend = game.backends["Ada"]

    def _forbidden(context):
        raise AssertionError("menu mode called the lazy candidate generator")

    backend._lazy_candidates = _forbidden
    context = game._context("Ada")
    assert context.affordances
    backend.decide(context)  # must not call the forbidden lazy generator
    assert "entities" not in context.observations


def test_menu_mode_trace_digest_is_unchanged():
    game = create_game(scenario=MENU_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, affordance_mode="menu")
    trace = TurnTrace()
    for _ in range(2):
        assert game.step()["status"] == "advanced"
        trace.add_record(semantic_step_trace(game))
    assert trace.hexdigest() == MENU_DIGEST_AT_LA01


# ------------------------------------------------------------------ short lazy run
def test_short_lazy_town100_run_completes_without_unhandled_errors(capsys):
    game = create_game(scenario="town100", seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, affordance_mode="lazy")
    for _ in range(4):
        result = game.step()
        assert result["status"] == "advanced"
    assert game.last_errors == {}
    counts = game.world.refusal_counts()
    # Report, do not fix, the observed refusal rate for LA06.
    with capsys.disabled():
        print(f"\nLA04 town100 lazy refusals after 4 turns: {counts['total']} "
              f"{counts['by_reason']}")
    assert isinstance(counts["total"], int)
