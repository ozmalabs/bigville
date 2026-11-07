"""EN02: lazy snapshot and report building for headless turns.

``snapshot_mode="every_turn"`` is the historical explicit mode and the direct
``BigvilleGame`` default; ``create_game`` now defaults to ``"auto"`` (EN05).
``"on_demand"`` leaves the snapshot out of a turn result, so no
``world.report()`` / ``report_history()`` work happens; ``game.snapshot()``
still builds the full snapshot when a UI or debugger asks.  ``"auto"`` reuses
the LA08 simple-session rule.  ``snapshot(include_report=False)`` and
``export_state(include_report=False)`` expose the same split directly.
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

A, H = "Ada", "Hal"


def _room(backend="simple"):
    actors = []
    for name, role, cell in ((A, "resident", [1, 1]),
                             ("Ben", "resident", [2, 2]),
                             ("Cy", "farmer", [3, 3])):
        actor = {"name": name, "role": role, "home_cell": cell}
        if backend is not None:
            actor["backend"] = backend
        actors.append(actor)
    return {
        "id": "en02_snapshot_room",
        "name": "EN02 snapshot room",
        "map": {"grid": [["floor"] * 6 for _ in range(6)]},
        "actors": actors,
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False,
                                "decay": False},
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }


PLAIN_ROOM = _room(backend=None)


def _game(**kwargs):
    options = dict(scenario=PLAIN_ROOM, seed=305000,
                   default_backend="simple", autonomous=True, llm_log=False)
    options.update(kwargs)
    return create_game(**options)


def _spy_report(monkeypatch, world):
    """Record report/report_history calls while still delegating to the real ones."""
    calls: list[str] = []
    real_report = world.report
    real_history = world.report_history

    def report(*args, **kwargs):
        calls.append("report")
        return real_report(*args, **kwargs)

    def history(*args, **kwargs):
        calls.append("report_history")
        return real_history(*args, **kwargs)

    monkeypatch.setattr(world, "report", report)
    monkeypatch.setattr(world, "report_history", history)
    return calls


def _forbid_report(monkeypatch, world):
    """Fail loudly if the expensive report paths are entered."""
    def forbidden(*args, **kwargs):
        raise AssertionError("report work ran when it should not have")

    monkeypatch.setattr(world, "report", forbidden)
    monkeypatch.setattr(world, "report_history", forbidden)


class _KindBackend:
    """A minimal foreign backend; auto resolution only needs ``kind``."""

    def __init__(self, kind):
        self.kind = kind


# ------------------------------------------------------------------ explicit legacy mode
def test_explicit_every_turn_step_includes_the_full_snapshot():
    game = _game(snapshot_mode="every_turn")
    assert game.snapshot_mode_requested == "every_turn"
    assert game.snapshot_mode == "every_turn"

    result = game.step()
    assert result["status"] == "advanced"
    assert result["turn"] == 1
    assert result["results"] == game.last_results
    assert "snapshot" in result
    snapshot = result["snapshot"]
    for key in ("schema", "world", "characters", "held_state", "continuations"):
        assert key in snapshot, key
    assert snapshot["schema"] == "bigville/game/1"
    assert "report" in snapshot["world"]
    assert "report_history" in snapshot["world"]
    assert snapshot == game.snapshot()


# ------------------------------------------------------------------ on demand
def test_on_demand_step_omits_snapshot_and_does_no_report_work(monkeypatch):
    game = _game(snapshot_mode="on_demand")
    assert (game.snapshot_mode_requested, game.snapshot_mode) == (
        "on_demand", "on_demand")
    calls = _spy_report(monkeypatch, game.world)

    result = game.step()
    assert result["status"] == "advanced"
    assert result["turn"] == 1
    assert result["results"] == game.last_results
    assert "snapshot" not in result
    assert set(result) == {"status", "turn", "results"}
    assert calls == []

    # The snapshot is still available explicitly, and that is when the report runs.
    snapshot = game.snapshot()
    assert calls == ["report", "report_history"]
    for key in ("schema", "world", "characters", "held_state", "continuations"):
        assert key in snapshot, key
    assert snapshot["world"]["report"]
    assert isinstance(snapshot["world"]["report_history"], list)


def test_on_demand_step_does_not_even_need_the_snapshot_method(monkeypatch):
    game = _game(snapshot_mode="on_demand")
    calls: list[int] = []
    monkeypatch.setattr(game, "snapshot",
                        lambda *a, **k: calls.append(1) or {})

    result = game.step()
    assert "snapshot" not in result
    assert calls == []


# ------------------------------------------------------------------ per-call override
def test_include_snapshot_true_overrides_on_demand():
    game = _game(snapshot_mode="on_demand")
    result = game.step(include_snapshot=True)
    assert "snapshot" in result
    assert result["snapshot"]["schema"] == "bigville/game/1"


def test_include_snapshot_false_overrides_every_turn(monkeypatch):
    game = _game()
    calls = _spy_report(monkeypatch, game.world)
    result = game.step(include_snapshot=False)
    assert "snapshot" not in result
    assert set(result) == {"status", "turn", "results"}
    assert calls == []


# ------------------------------------------------------------------ explicit split
def test_snapshot_include_report_false_skips_report_and_keeps_core(monkeypatch):
    game = _game()
    _forbid_report(monkeypatch, game.world)

    snapshot = game.snapshot(include_report=False)
    for key in ("schema", "player", "world", "characters", "held_state",
                "continuations"):
        assert key in snapshot, key
    world = snapshot["world"]
    assert "report" not in world
    assert "report_history" not in world
    # The canonical world data is still present.
    assert world["residents"] and world["map"]["grid"]


def test_export_state_include_report_false_is_documented_and_cheap(monkeypatch):
    world = create_world(scenario=PLAIN_ROOM, seed=305000)
    _forbid_report(monkeypatch, world)

    state = world.export_state(include_report=False)
    assert state["schema"] == "townview/1"
    assert state["residents"] and state["map"]["grid"]
    assert "report" not in state and "report_history" not in state


def test_export_state_without_arguments_keeps_the_old_shape():
    world = create_world(scenario=PLAIN_ROOM, seed=305000)
    state = world.export_state()
    assert state["schema"] == "townview/1"
    assert "report" in state and "report_history" in state
    # The on-demand report equals the one the old export carried.
    assert state["report"] == world.report()
    assert state["report_history"] == world.report_history()


# ------------------------------------------------------------------ waiting paths
def test_player_waiting_result_keeps_context_and_affordances_and_no_snapshot(
        monkeypatch):
    game = _game(player=A, autonomous=False, snapshot_mode="on_demand")
    calls = _spy_report(monkeypatch, game.world)

    waiting = game.step()
    assert waiting["status"] == "waiting"
    assert waiting["actor"] == A
    assert waiting["context"] and isinstance(waiting["context"], dict)
    assert isinstance(waiting["affordances"], list)
    assert "snapshot" not in waiting
    assert calls == []


class _Taker(DeterministicBackend):
    """Proposes to take four coin from Hal every turn."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "take", {"source": H, "kind": "coin", "amount": 4.0}))


def _contest_pair():
    world = BigvilleWorld(autonomous_actors=False)
    cell = sorted(world._map_cells)[len(world._map_cells) // 2]
    world.add_actor(A, role="hand", home_cell=cell)
    world.add_actor(H, role="hand", home_cell=cell)
    world._move_actor_to(A, cell)
    world._move_actor_to(H, cell)
    world.tick()
    world.mark_turn_start()
    world.set_coin(H, 10.0)
    return world


def test_contest_waiting_result_keeps_reaction_context_without_snapshot(monkeypatch):
    world = _contest_pair()
    game = BigvilleGame(world, autonomous=True, snapshot_mode="on_demand")
    human = HumanBackend(game.characters[H],
                         chooser=lambda context: ActorResponse())
    game.set_backend(H, human)
    game.set_backend(A, _Taker(game.characters[A]))
    calls = _spy_report(monkeypatch, world)

    waiting = game.step()
    assert waiting["status"] == "waiting"
    assert waiting["actor"] == H
    assert waiting["reaction"]["actor"] == A
    assert "yield" in waiting["reaction"]["options"]
    assert waiting["context"] and waiting["affordances"]
    assert "snapshot" not in waiting
    assert calls == []

    # Resume the contest; the on-demand mode still omits the snapshot.
    human.submit_reaction(ActorResponse(backend_state={"reaction": "yield"}))
    done = game.step()
    assert done["status"] == "advanced"
    assert "snapshot" not in done
    assert calls == []


# ------------------------------------------------------------------ auto matrix
def test_auto_resolves_on_demand_for_autonomous_simple_session():
    game = _game(snapshot_mode="auto")
    assert game.snapshot_mode_requested == "auto"
    assert game.snapshot_mode == "on_demand"


def test_auto_resolves_every_turn_for_a_player():
    game = _game(player=A, autonomous=False, snapshot_mode="auto")
    assert (game.snapshot_mode_requested, game.snapshot_mode) == (
        "auto", "every_turn")


def test_auto_resolves_every_turn_for_an_llm_session():
    game = create_game(scenario=PLAIN_ROOM, seed=305000,
                       default_backend="llm", llm_provider=FakeProvider(),
                       autonomous=True, llm_log=False, snapshot_mode="auto")
    assert {backend.kind for backend in game.backends.values()} == {"llm"}
    assert (game.snapshot_mode_requested, game.snapshot_mode) == (
        "auto", "every_turn")


def test_auto_resolves_every_turn_for_an_ocelot_like_backend():
    game = _game(snapshot_mode="auto")
    assert game.snapshot_mode == "on_demand"
    game.set_backend(A, _KindBackend("ocelot"))
    assert game.snapshot_mode == "every_turn"
    assert game.resolve_snapshot_mode() == "every_turn"  # idempotent


@pytest.mark.parametrize("mode", ["every_turn", "on_demand"])
def test_explicit_snapshot_values_win_over_auto(mode):
    game = _game(player=A, autonomous=False, snapshot_mode=mode)
    assert (game.snapshot_mode_requested, game.snapshot_mode) == (mode, mode)


def test_direct_constructor_auto_and_validation():
    world = create_world(scenario=PLAIN_ROOM, seed=305000)
    game = BigvilleGame(world, autonomous=True, snapshot_mode="auto")
    assert game.snapshot_mode == "on_demand"

    with pytest.raises(ValueError):
        game.snapshot_mode = "sometimes"

    with pytest.raises(ValueError):
        _game(snapshot_mode="sometimes")
