"""Strict game-session checkpoints built on Bigville world checkpoints."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .backends import (ActorContinuation, ActorResponse, DeterministicBackend,
                       HumanBackend, OcelotBackend, ProposedAction, SpeechProposal)
from .backends.animal import AnimalNPCBackend
from .backends.cheap import NPCGoal, SimplePolicy
from .character import CharacterDefinition, FrameSeed, MemoryRecord
from .backends.conversation import TemplateConversationInterface
from .runtime import _checkpoint_decode, _checkpoint_encode
from .world_persistence import load_world_checkpoint, save_world_checkpoint


_SCHEMA = "bigville/game-checkpoint/1"


def _character_to_checkpoint(character):
    if type(character) is not CharacterDefinition:
        raise TypeError(f"unsupported character class: {type(character).__name__}")
    if any(type(memory) is not MemoryRecord for memory in character.memories):
        raise TypeError(f"unsupported memory record class for {character.name!r}")
    if any(type(frame) is not FrameSeed for frame in character.held_frames):
        raise TypeError(f"unsupported held-frame class for {character.name!r}")
    return {
        "character_id": character.character_id,
        "name": character.name,
        "identity": character.identity,
        "personality": character.personality,
        "memories": [asdict(memory) for memory in character.memories],
        "held_frames": [asdict(frame) for frame in character.held_frames],
        "backend": character.backend,
    }


def _character_from_checkpoint(data):
    return CharacterDefinition(
        character_id=str(data["character_id"]), name=str(data["name"]),
        identity=data["identity"], personality=data["personality"],
        memories=[MemoryRecord(**memory) for memory in data["memories"]],
        held_frames=[FrameSeed(**frame) for frame in data["held_frames"]],
        backend=data["backend"],
    )


def _action_to_checkpoint(action):
    return None if action is None else {
        "action": action.action, "params": action.params, "reason": action.reason,
    }


def _continuation_to_checkpoint(request):
    if request is None:
        return None
    return {
        "destination": request.destination,
        "task": _action_to_checkpoint(request.task),
        "interrupt_on": request.interrupt_on,
        "expected_events": request.expected_events,
        "hunger_threshold": request.hunger_threshold,
        "energy_threshold": request.energy_threshold,
        "poll_each_turn": request.poll_each_turn,
    }


def _response_to_checkpoint(response):
    if response is None:
        return None
    utterances = []
    for utterance in response.utterances:
        if isinstance(utterance, SpeechProposal):
            utterances.append({"kind": "speech_proposal", "data": utterance.to_dict()})
        else:
            utterances.append({"kind": "value", "data": utterance})
    return {
        "major_action": _action_to_checkpoint(response.major_action),
        "utterances": utterances,
        "memory_updates": response.memory_updates,
        "backend_state": response.backend_state,
        "waiting": response.waiting,
        "continuation": _continuation_to_checkpoint(response.continuation),
    }


def _response_from_checkpoint(data):
    if data is None:
        return None
    action = data["major_action"]
    major_action = (ProposedAction(action["action"], action["params"], action["reason"])
                    if action else None)
    utterances = []
    for utterance in data["utterances"]:
        if utterance["kind"] == "speech_proposal":
            utterances.append(SpeechProposal.from_value(utterance["data"]))
        else:
            utterances.append(utterance["data"])
    continuation = data["continuation"]
    return ActorResponse(
        major_action=major_action, utterances=utterances,
        memory_updates=data["memory_updates"], backend_state=data["backend_state"],
        waiting=data["waiting"], continuation=ActorContinuation.from_value(continuation),
    )


def _backend_checkpoint(backend):
    if type(backend) is OcelotBackend:
        return {"kind": "ocelot"}
    if type(backend) is HumanBackend:
        if backend.chooser is not None:
            raise TypeError("HumanBackend chooser callbacks cannot be checkpointed")
        return {"kind": "human", "responses": [
            _response_to_checkpoint(response) for response in backend._responses]}
    if type(backend) is DeterministicBackend:
        policy = backend.policy
        if not isinstance(policy, SimplePolicy):
            raise TypeError("custom simple backend policy type cannot be checkpointed")
        if policy.hook is not None:
            raise TypeError("SimplePolicy hook callbacks cannot be checkpointed")
        return {
            "kind": "cheap", "policy": asdict(policy),
            "last_choice": backend.last_choice,
            "rest_energy_threshold": backend.rest_energy_threshold,
            "goals": [asdict(goal) for goal in backend.goals],
            "current_goal": asdict(backend.current_goal) if backend.current_goal else None,
            "last_speech_turn": backend.last_speech_turn,
            "time_band": backend.time_band,
        }
    raise TypeError(
        f"unsupported backend {type(backend).__name__}; supply an explicit backend checkpoint adapter"
    )


def _build_backend(kind_state, world, character):
    kind = kind_state["kind"]
    if kind == "ocelot":
        return OcelotBackend(world, character)
    if kind == "human":
        backend = HumanBackend(character)
        for response in kind_state["responses"]:
            backend.submit(_response_from_checkpoint(response))
        return backend
    if kind == "cheap":
        policy_data = dict(kind_state["policy"])
        policy_data["stock_fetch_kinds"] = tuple(policy_data["stock_fetch_kinds"])
        policy = SimplePolicy(**policy_data)
        backend = DeterministicBackend(character, policy=policy)
        backend.last_choice = kind_state["last_choice"]
        backend.rest_energy_threshold = float(kind_state["rest_energy_threshold"])
        backend.goals = [NPCGoal(**goal) for goal in kind_state["goals"]]
        backend.current_goal = (NPCGoal(**kind_state["current_goal"])
                                if kind_state["current_goal"] else None)
        backend.last_speech_turn = int(kind_state["last_speech_turn"])
        backend.time_band = str(kind_state["time_band"])
        return backend
    raise ValueError(f"unknown checkpoint backend kind: {kind!r}")


def _continuation_state(active):
    return {
        "request": _continuation_to_checkpoint(active.request),
        "started_turn": active.started_turn,
        "baseline_hunger": active.baseline_hunger,
        "baseline_energy": active.baseline_energy,
        "baseline_nearby": active.baseline_nearby,
        "baseline_position": active.baseline_position,
        "baseline_events": active.baseline_events,
        "last_action_ok": active.last_action_ok,
        "destination_complete": active.destination_complete,
    }


def save_game_checkpoint(game, path: str | Path) -> None:
    """Save world and game state at a quiescent point between game steps."""
    if getattr(game.world, "_actor_tick_in_progress", False) or getattr(game.world, "_major_dispatch", False):
        raise ValueError("cannot checkpoint Bigville during an active world dispatch")
    backend_state = {name: _backend_checkpoint(backend)
                     for name, backend in game.backends.items()}
    animal_state = {}
    for name, backend in game._animal_backends.items():
        if type(backend) is not AnimalNPCBackend:
            raise TypeError(f"unsupported animal backend for {name!r}")
        animal_state[name] = {
            "species": backend.species, "setup": backend.setup,
            "last_choice": backend.last_choice,
        }
    if type(game.conversation_interface) is not TemplateConversationInterface:
        raise TypeError("custom conversation interfaces cannot be checkpointed")
    state = {
        "player": game.player, "ticks_per_period": game.ticks_per_period,
        "continuations_enabled": game.continuations_enabled,
        "characters": {name: _character_to_checkpoint(character)
                       for name, character in game.characters.items()},
        "backends": backend_state,
        "continuations": {name: _continuation_state(active)
                           for name, active in game._continuations.items()},
        "physical_events": game._physical_events,
        "animal_backends": animal_state,
        "animal_decisions": game._animal_decisions,
        "last_responses": {name: _response_to_checkpoint(response)
                           for name, response in game.last_responses.items()},
        "last_results": game.last_results,
        "conversation_templates": game.conversation_interface.templates,
    }
    encoded = json.dumps(_checkpoint_encode(state, "game"), sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    generation = "generation-" + uuid.uuid4().hex
    staging = root / ("." + generation)
    staging.mkdir()
    try:
        save_world_checkpoint(game.world, staging / "world")
        (staging / "game.json").write_bytes(encoded)
        committed = root / generation
        os.replace(staging, committed)
        manifest = {"schema": _SCHEMA, "generation": generation,
                    "sha256": __import__("hashlib").sha256(encoded).hexdigest()}
        fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, root / "manifest.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def load_game_checkpoint(path: str | Path, *, resident_loader: Callable | None = None,
                         physical_subsystem_extensions: dict | None = None,
                         cognition_factory=None):
    """Restore a supported game session and rebind world/resident backends."""
    from .game import BigvilleGame, _ActiveContinuation

    root = Path(path)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != _SCHEMA:
            raise ValueError(f"unsupported game checkpoint schema: {manifest.get('schema')!r}")
        generation = manifest.get("generation")
        if not isinstance(generation, str) or not generation.startswith("generation-") or Path(generation).name != generation:
            raise ValueError("invalid game checkpoint generation")
        directory = root / generation
        payload = (directory / "game.json").read_bytes()
        if __import__("hashlib").sha256(payload).hexdigest() != manifest.get("sha256"):
            raise ValueError("game checkpoint checksum mismatch")
        state = _checkpoint_decode(json.loads(payload), "game")
        world = load_world_checkpoint(
            directory / "world", resident_loader=resident_loader,
            physical_subsystem_extensions=physical_subsystem_extensions,
            cognition_factory=cognition_factory,
        )
        characters = {name: _character_from_checkpoint(data)
                      for name, data in state["characters"].items()}
        backend_states = state["backends"]
        if set(backend_states) != set(characters):
            raise ValueError("backend and character names do not match")
        backends = {name: _build_backend(backend_states[name], world, character)
                    for name, character in characters.items()}
        game = BigvilleGame(
            world, player=state["player"], characters=characters, backends=backends,
            continuations=state["continuations_enabled"], autonomous=state["player"] is None,
            ticks_per_period=state["ticks_per_period"],
        )
        game.conversation_interface = TemplateConversationInterface(
            state["conversation_templates"])
        game._continuations = {}
        for name, active in state["continuations"].items():
            request = ActorContinuation.from_value(active["request"])
            game._continuations[name] = _ActiveContinuation(
                request=request, started_turn=int(active["started_turn"]),
                baseline_hunger=float(active["baseline_hunger"]),
                baseline_energy=float(active["baseline_energy"]),
                baseline_nearby=frozenset(active["baseline_nearby"]),
                baseline_position=active["baseline_position"],
                baseline_events=frozenset(active["baseline_events"]),
                last_action_ok=bool(active["last_action_ok"]),
                destination_complete=bool(active["destination_complete"]),
            )
        game._physical_events = state["physical_events"]
        game._animal_backends = {}
        for name, animal in state["animal_backends"].items():
            backend = AnimalNPCBackend(name, animal["species"], animal["setup"])
            backend.last_choice = animal["last_choice"]
            game._animal_backends[name] = backend
        game._animal_decisions = state["animal_decisions"]
        game.last_responses = {name: _response_from_checkpoint(response)
                               for name, response in state["last_responses"].items()}
        game.last_results = state["last_results"]
        game._sync_backend_metadata()
        return game
    except Exception as exc:
        raise ValueError(f"could not restore Bigville game checkpoint at {root}: {exc}") from exc
