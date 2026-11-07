"""EN05: combined speedup defaults for autonomous simple/cheap sessions.

``create_game`` defaults to ``"auto"`` for affordance, snapshot and rule
batching.  Auto resolves to the cheap/headless path (lazy, on_demand, turn)
only for an autonomous session whose resident backends are all built-in
simple/cheap.  A player, LLM, Ocelot or other backend keeps the historical
paths (menu, every_turn, action).  Explicit values always win, and a direct
``BigvilleGame`` constructor still defaults to menu/every_turn/action.
"""
from __future__ import annotations

import pytest

from bigville.api import create_game, create_world
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.human import HumanBackend
from bigville.game import BigvilleGame
from tests.llm_stub import FakeProvider
from worlds.bigville_world import BigvilleWorld


def _room(backend="simple"):
    actors = []
    for name, role, cell in (("Ada", "resident", [1, 1]),
                             ("Ben", "resident", [2, 2]),
                             ("Cy", "farmer", [3, 3])):
        actor = {"name": name, "role": role, "home_cell": cell}
        if backend is not None:
            actor["backend"] = backend
        actors.append(actor)
    return {
        "id": "en05_defaults_room",
        "name": "EN05 defaults room",
        "map": {"grid": [["floor"] * 6 for _ in range(6)]},
        "actors": actors,
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False,
                                "decay": False},
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }


SIMPLE_ROOM = _room()
PLAIN_ROOM = _room(backend=None)


def _game(**kwargs):
    options = dict(scenario=SIMPLE_ROOM, seed=305000,
                   default_backend="simple", autonomous=True, llm_log=False)
    options.update(kwargs)
    return create_game(**options)


class _KindBackend:
    """A minimal foreign backend; auto resolution only needs ``kind``."""

    def __init__(self, kind):
        self.kind = kind


class _MoveBackend(DeterministicBackend):
    """Always propose one move so the legacy per-action sweep is observable."""

    def decide(self, context):
        return ActorResponse(
            major_action=ProposedAction("move", {"destination": (4, 4)}))


def _modes(game):
    return (game.affordance_mode_requested, game.affordance_mode,
            game.snapshot_mode_requested, game.snapshot_mode,
            game.rule_batching_requested, game.rule_batching)


def _spy_menu(monkeypatch):
    calls: list[tuple[str, str]] = []
    real_affordances = BigvilleWorld.actor_affordances
    real_options = BigvilleWorld._actor_options

    def actor_affordances(world, actor):
        calls.append(("actor_affordances", actor))
        return real_affordances(world, actor)

    def actor_options(world, actor):
        calls.append(("_actor_options", actor))
        return real_options(world, actor)

    monkeypatch.setattr(BigvilleWorld, "actor_affordances", actor_affordances)
    monkeypatch.setattr(BigvilleWorld, "_actor_options", actor_options)
    return calls


def _spy_sweeps(world):
    """Count actual ``_run`` executions, not deferred requests."""
    calls: list[int] = []
    real = world._run

    def measured(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    world._run = measured
    return calls


# --------------------------------------------------------------- resolution matrix
def test_autonomous_simple_defaults_resolve_to_the_headless_path():
    game = _game()
    assert _modes(game) == ("auto", "lazy", "auto", "on_demand",
                            "auto", "turn")


def test_autonomous_cheap_defaults_resolve_to_the_headless_path():
    game = create_game(scenario=PLAIN_ROOM, seed=305000,
                       default_backend="cheap", autonomous=True, llm_log=False)
    assert {backend.kind for backend in game.backends.values()} == {"cheap"}
    assert _modes(game) == ("auto", "lazy", "auto", "on_demand",
                            "auto", "turn")


def test_player_defaults_resolve_to_the_historical_path():
    game = _game(player="Ada", autonomous=False)
    assert isinstance(game.backends["Ada"], HumanBackend)
    assert _modes(game) == ("auto", "menu", "auto", "every_turn",
                            "auto", "action")


def test_llm_defaults_resolve_to_the_historical_path():
    game = create_game(scenario=PLAIN_ROOM, seed=305000,
                       default_backend="llm", llm_provider=FakeProvider(),
                       autonomous=True, llm_log=False)
    assert {backend.kind for backend in game.backends.values()} == {"llm"}
    assert _modes(game) == ("auto", "menu", "auto", "every_turn",
                            "auto", "action")


@pytest.mark.parametrize("kind", ["llm", "ocelot", "human", "other", ""])
def test_any_foreign_backend_forces_all_three_modes_to_historical(kind):
    game = _game()
    assert game.rule_batching == "turn"

    game.set_backend("Ada", _KindBackend(kind))

    assert _modes(game) == ("auto", "menu", "auto", "every_turn",
                            "auto", "action")
    # Resolution is deterministic and idempotent.
    assert game.resolve_affordance_mode() == "menu"
    assert game.resolve_snapshot_mode() == "every_turn"
    assert game.resolve_rule_batching() == "action"


def test_set_backend_re_resolves_auto_back_to_the_headless_path():
    game = _game()
    game.set_backend("Ada", _KindBackend("llm"))
    assert game.rule_batching == "action"

    game.set_backend(
        "Ada", DeterministicBackend(game.characters["Ada"]))

    assert _modes(game) == ("auto", "lazy", "auto", "on_demand",
                            "auto", "turn")


def test_explicit_values_always_win_for_an_autonomous_simple_session():
    game = _game(affordance_mode="menu", snapshot_mode="every_turn",
                 rule_batching="action")
    assert _modes(game) == ("menu", "menu", "every_turn", "every_turn",
                            "action", "action")


def test_explicit_values_always_win_for_a_player_session():
    game = _game(player="Ada", autonomous=False, affordance_mode="lazy",
                 snapshot_mode="on_demand", rule_batching="turn")
    assert _modes(game) == ("lazy", "lazy", "on_demand", "on_demand",
                            "turn", "turn")


def test_direct_constructor_defaults_to_the_historical_modes():
    world = create_world(scenario=SIMPLE_ROOM, seed=305000)
    game = BigvilleGame(world, autonomous=True)
    assert _modes(game) == ("menu", "menu", "every_turn", "every_turn",
                            "action", "action")


def test_direct_constructor_auto_resolves_the_headless_path():
    world = create_world(scenario=SIMPLE_ROOM, seed=305000)
    game = BigvilleGame(world, autonomous=True, affordance_mode="auto",
                        snapshot_mode="auto", rule_batching="auto")
    assert _modes(game) == ("auto", "lazy", "auto", "on_demand",
                            "auto", "turn")


def test_rule_batching_rejects_invalid_values():
    world = create_world(scenario=SIMPLE_ROOM, seed=305000)
    game = BigvilleGame(world, autonomous=True)
    with pytest.raises(ValueError):
        game.rule_batching = "sometimes"
    with pytest.raises(ValueError):
        _game(rule_batching="sometimes")


# --------------------------------------------------------------- play paths
def test_new_defaults_two_turn_run_is_headless_and_turn_batched(monkeypatch):
    game = _game()
    assert _modes(game) == ("auto", "lazy", "auto", "on_demand",
                            "auto", "turn")
    menu_calls = _spy_menu(monkeypatch)

    def forbidden_report(*args, **kwargs):
        raise AssertionError("report work ran under the new defaults")

    monkeypatch.setattr(game.world, "report", forbidden_report)
    monkeypatch.setattr(game.world, "report_history", forbidden_report)

    snapshot_calls: list[int] = []

    def forbidden_snapshot(*args, **kwargs):
        snapshot_calls.append(1)
        raise AssertionError("snapshot ran under the new defaults")

    monkeypatch.setattr(game, "snapshot", forbidden_snapshot)
    sweeps = _spy_sweeps(game.world)

    per_turn_sweeps = []
    for _ in range(2):
        before = len(sweeps)
        result = game.step()
        per_turn_sweeps.append(len(sweeps) - before)
        assert result["status"] == "advanced"
        assert "snapshot" not in result
        assert set(result) == {"status", "turn", "results"}

    assert menu_calls == [], f"lazy default called the menu: {menu_calls[:5]}"
    assert snapshot_calls == []
    assert per_turn_sweeps == [3, 3]


def test_explicit_menu_every_turn_action_keeps_the_old_paths(monkeypatch):
    game = _game(affordance_mode="menu", snapshot_mode="every_turn",
                 rule_batching="action")
    for name in ("Ada", "Ben", "Cy"):
        game.set_backend(name, _MoveBackend(game.characters[name]))
    menu_calls = _spy_menu(monkeypatch)

    report_calls: list[str] = []
    real_report = game.world.report
    real_history = game.world.report_history

    def report(*args, **kwargs):
        report_calls.append("report")
        return real_report(*args, **kwargs)

    def history(*args, **kwargs):
        report_calls.append("report_history")
        return real_history(*args, **kwargs)

    monkeypatch.setattr(game.world, "report", report)
    monkeypatch.setattr(game.world, "report_history", history)
    snapshot_calls: list[int] = []
    real_snapshot = game.snapshot

    def snapshot(*args, **kwargs):
        snapshot_calls.append(1)
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(game, "snapshot", snapshot)
    sweeps = _spy_sweeps(game.world)

    result = game.step()

    assert result["status"] == "advanced"
    assert "snapshot" in result
    assert result["snapshot"]["schema"] == "bigville/game/1"
    assert menu_calls, "explicit menu mode did not build the menu"
    assert snapshot_calls == [1]
    assert report_calls == ["report", "report_history"]
    # The historical per-action sweep runs once per actor plus tick/finish.
    assert len(sweeps) >= 4
