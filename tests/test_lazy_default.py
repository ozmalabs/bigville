"""LA08: ``"auto"`` affordance mode and the ``create_game`` default rollout.

``create_game`` now defaults to ``affordance_mode="auto"``.  Auto resolves to
``"lazy"`` only for an autonomous session whose resident backends are all
built-in simple/cheap; a player, an LLM, Ocelot or any other backend resolves
to ``"menu"``.  A direct ``BigvilleGame`` constructor still defaults to
``"menu"`` and accepts ``"auto"`` explicitly.
"""
from __future__ import annotations

import unittest.mock as mock

import pytest

from bigville.api import create_game, create_world
from bigville.backends.ocelot import OcelotUnavailableError
from bigville.game import BigvilleGame
from tests.llm_stub import FakeProvider
from worlds.bigville_world import BigvilleWorld


def _room(backend=None):
    actors = []
    for name, role, cell in (("Ada", "resident", [1, 1]),
                             ("Ben", "resident", [2, 2]),
                             ("Cy", "farmer", [3, 3])):
        actor = {"name": name, "role": role, "home_cell": cell}
        if backend is not None:
            actor["backend"] = backend
        actors.append(actor)
    return {
        "id": "la08_auto_room",
        "name": "LA08 auto room",
        "map": {"grid": [["floor"] * 6 for _ in range(6)]},
        "actors": actors,
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }


SIMPLE_SCENARIO = _room("simple")
PLAIN_SCENARIO = _room()


def _game(**kwargs):
    options = dict(scenario=SIMPLE_SCENARIO, seed=305000,
                   default_backend="simple", autonomous=True, llm_log=False)
    options.update(kwargs)
    return create_game(**options)


class _KindBackend:
    """A minimal foreign backend; resolution only needs its ``kind``."""

    def __init__(self, kind):
        self.kind = kind


def _spy_menu():
    """Patch the world's two menu builders and return (calls, patches)."""
    calls: list[tuple[str, str]] = []
    real_affordances = BigvilleWorld.actor_affordances
    real_options = BigvilleWorld._actor_options

    def actor_affordances(self, actor):
        calls.append(("actor_affordances", actor))
        return real_affordances(self, actor)

    def actor_options(self, actor):
        calls.append(("_actor_options", actor))
        return real_options(self, actor)

    return calls, (mock.patch.object(BigvilleWorld, "actor_affordances", actor_affordances),
                   mock.patch.object(BigvilleWorld, "_actor_options", actor_options))


# --------------------------------------------------------------- resolution matrix
def test_autonomous_simple_game_defaults_to_lazy():
    game = _game()
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "lazy"


def test_autonomous_cheap_game_defaults_to_lazy():
    game = create_game(scenario=PLAIN_SCENARIO, seed=305000,
                       default_backend="cheap", autonomous=True, llm_log=False)
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "lazy"
    assert {backend.kind for backend in game.backends.values()} == {"cheap"}


def test_autonomous_llm_game_resolves_to_menu():
    game = create_game(scenario=PLAIN_SCENARIO, seed=305000,
                       default_backend="llm", llm_provider=FakeProvider(),
                       autonomous=True, llm_log=False)
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "menu"
    assert {backend.kind for backend in game.backends.values()} == {"llm"}


def test_player_game_resolves_to_menu():
    game = _game(player="Ada", autonomous=False)
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "menu"


def test_ocelot_requiring_game_resolves_to_menu_or_skips():
    try:
        game = create_game(scenario=PLAIN_SCENARIO, seed=305000,
                           default_backend="ocelot", autonomous=True,
                           llm_log=False)
    except OcelotUnavailableError as exc:
        pytest.skip(f"Ocelot is unavailable on this host: {exc}")
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "menu"


@pytest.mark.parametrize("kind", ["llm", "ocelot", "human"])
def test_any_foreign_backend_forces_menu_on_re_resolution(kind):
    # This is the same rule the skipped Ocelot run would exercise: a
    # non-simple backend injected after construction makes auto resolve to
    # menu.  ``set_backend`` re-resolves an "auto" session.
    game = _game()
    assert game.affordance_mode == "lazy"
    game.set_backend("Ada", _KindBackend(kind))
    assert game.affordance_mode == "menu"
    assert game.resolve_affordance_mode() == "menu"  # idempotent


def test_explicit_menu_wins_and_is_reported():
    game = _game(affordance_mode="menu")
    assert game.affordance_mode_requested == "menu"
    assert game.affordance_mode == "menu"


def test_explicit_lazy_wins_and_is_reported():
    game = _game(affordance_mode="lazy")
    assert game.affordance_mode_requested == "lazy"
    assert game.affordance_mode == "lazy"


def test_mode_properties_track_reassignment():
    game = _game()
    assert (game.affordance_mode_requested, game.affordance_mode) == ("auto", "lazy")

    game.affordance_mode = "menu"
    assert (game.affordance_mode_requested, game.affordance_mode) == ("menu", "menu")

    game.affordance_mode = "auto"
    assert (game.affordance_mode_requested, game.affordance_mode) == ("auto", "lazy")

    with pytest.raises(ValueError):
        game.affordance_mode = "bogus"


# --------------------------------------------------------------- direct constructor
def test_direct_constructor_defaults_to_menu():
    world = create_world(scenario=SIMPLE_SCENARIO, seed=305000)
    game = BigvilleGame(world, autonomous=True)
    assert game.affordance_mode_requested == "menu"
    assert game.affordance_mode == "menu"


def test_direct_constructor_auto_resolves_lazy_for_autonomous_simple():
    world = create_world(scenario=SIMPLE_SCENARIO, seed=305000)
    game = BigvilleGame(world, autonomous=True, affordance_mode="auto")
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "lazy"


def test_direct_constructor_auto_resolves_menu_with_a_player():
    world = create_world(scenario=SIMPLE_SCENARIO, seed=305000)
    game = BigvilleGame(world, player="Ada", autonomous=False,
                        affordance_mode="auto")
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "menu"


# --------------------------------------------------------------- play path
def test_default_autonomous_simple_run_never_builds_the_menu():
    game = create_game(scenario="town100", seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False)
    assert game.affordance_mode == "lazy"

    calls, patches = _spy_menu()
    for patch in patches:
        patch.start()
    try:
        for _ in range(2):
            assert game.step()["status"] == "advanced"
    finally:
        for patch in patches:
            patch.stop()

    assert calls == [], f"lazy default called the menu: {calls[:5]}"


def test_explicit_menu_game_still_builds_the_menu():
    game = _game(affordance_mode="menu")
    assert game.affordance_mode == "menu"

    calls, patches = _spy_menu()
    for patch in patches:
        patch.start()
    try:
        assert game.step()["status"] == "advanced"
    finally:
        for patch in patches:
            patch.stop()

    assert ("actor_affordances", "Ada") in calls
