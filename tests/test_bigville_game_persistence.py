from __future__ import annotations

import pytest

from bigville.api import create_game
from bigville.backends import ActorContinuation, ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.game_persistence import load_game_checkpoint, save_game_checkpoint
from bigville.scenarios import load_scenario


def test_simple_game_round_trip_keeps_continuation_and_next_turn(tmp_path):
    scenario = load_scenario("house_argument").to_dict()
    scenario["actors"] = [dict(actor, backend="simple") for actor in scenario["actors"]]
    uninterrupted = create_game(scenario=scenario, player="Mara", seed=913)
    saved = create_game(scenario=scenario, player="Mara", seed=913)
    request = ActorContinuation(
        task=ProposedAction("rest", {}, "resume-rest"),
        interrupt_on=("task_failed",),
    )
    uninterrupted._activate_continuation("Jon", request, action_ok=True)
    saved._activate_continuation("Jon", request, action_ok=True)
    for game in (uninterrupted, saved):
        game.backends["Mara"].submit(ActorResponse())

    checkpoint = tmp_path / "game"
    save_game_checkpoint(saved, checkpoint)
    restored = load_game_checkpoint(checkpoint)

    assert restored.world.eng.to_checkpoint_dict() == saved.world.eng.to_checkpoint_dict()
    assert restored._continuations["Jon"].request.to_dict() == request.to_dict()
    assert isinstance(restored.backends["Jon"], DeterministicBackend)
    result_restored = restored.step()
    result_control = uninterrupted.step()
    assert result_restored["status"] == result_control["status"] == "advanced"
    assert restored.world.eng.to_checkpoint_dict() == uninterrupted.world.eng.to_checkpoint_dict()
    assert restored._continuations["Jon"].started_turn == uninterrupted._continuations["Jon"].started_turn


def test_game_checkpoint_rejects_custom_backend_without_adapter(tmp_path):
    scenario = load_scenario("house_argument").to_dict()
    scenario["actors"] = [dict(actor, backend="simple") for actor in scenario["actors"]]
    game = create_game(scenario=scenario, player="Mara", default_backend="simple")

    class CustomBackend:
        kind = "custom"
        def decide(self, _context):
            return ActorResponse()

    game.set_backend("Jon", CustomBackend())
    with pytest.raises(TypeError, match="unsupported backend CustomBackend"):
        save_game_checkpoint(game, tmp_path / "game")


def test_mixed_real_ocelot_simple_game_checkpoint_continues(tmp_path):
    adapter = pytest.importorskip("worlds.bigville_ocelot_adapter")
    Resident = adapter.BigvilleOcelotResident
    scenario = {
        "id": "mixed_checkpoint",
        "name": "Mixed checkpoint",
        "map": {"grid": [["floor", "floor", "floor"],
                         ["floor", "floor", "floor"]]},
        "actors": [
            {"name": "Ada", "role": "hand", "home_cell": [0, 0]},
            {"name": "Ben", "role": "hand", "home_cell": [1, 0], "backend": "ocelot",
             "personality": {"emotional_core_enabled": 1.0}},
            {"name": "Cora", "role": "hand", "home_cell": [2, 1], "backend": "simple"},
        ],
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }
    game = create_game(scenario=scenario, player="Ada", default_backend="simple",
                       cognition_factory=Resident, seed=221)
    assert game.backends["Ben"].kind == "ocelot"
    assert game.backends["Cora"].kind == "cheap"
    game._activate_continuation("Cora", ActorContinuation(
        task=ProposedAction("rest", {}, "saved-continuation"),
        interrupt_on=("task_failed",)), action_ok=True)
    game.backends["Ada"].submit(ActorResponse())

    checkpoint = tmp_path / "mixed-game"
    save_game_checkpoint(game, checkpoint)
    restored = load_game_checkpoint(
        checkpoint,
        resident_loader=lambda _name, path: Resident.load(path),
    )
    assert restored.backends["Ben"].kind == "ocelot"
    assert restored.backends["Cora"].kind == "cheap"
    assert restored.world.actor_mind("Ben").name == "Ben"
    assert restored._continuations["Cora"].request.task.reason == "saved-continuation"
    assert restored.backends["Ada"]._responses

    control_result = game.step()
    result = restored.step()
    assert result["status"] == control_result["status"] == "advanced"
    assert restored.world._turn == 1
    assert restored.world.eng.to_checkpoint_dict() == game.world.eng.to_checkpoint_dict()
    assert restored._continuations["Cora"].request.to_dict() == \
        game._continuations["Cora"].request.to_dict()
