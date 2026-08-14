"""Turn-driven game orchestration over the canonical Bigville world."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import (ActorContext, ActorResponse, CheapBackend, ConversationMessage,
                       HumanBackend, OcelotBackend, TemplateConversationInterface)
from .backends.protocol import ActorContinuation, ProposedAction
from .backends.protocol import communication_capabilities
from .character import CharacterDefinition, MemoryRecord


@dataclass
class _ActiveContinuation:
    request: ActorContinuation
    started_turn: int
    baseline_hunger: float
    baseline_energy: float
    baseline_nearby: frozenset[str]
    baseline_position: Any
    baseline_events: frozenset[str]
    last_action_ok: bool = True
    destination_complete: bool = False


class BigvilleGame:
    """A playable session where human and autonomous actors share one API."""

    def __init__(self, world, *, player: str | None = None,
                 characters: dict[str, CharacterDefinition] | None = None,
                 backends: dict[str, Any] | None = None,
                 continuations: bool = True):
        self.world = world
        self.world._autonomous_actors = False
        self.conversation_interface = TemplateConversationInterface()
        self.world.set_conversation_adapter(self._adapt_speech)
        self.characters = characters or self._characters_from_world()
        self.backends = backends or {}
        # This is deliberately a game-session option.  A debugger, test, or
        # highly reactive world can retain the older decide-every-turn mode.
        self.continuations_enabled = bool(continuations)
        self._continuations: dict[str, _ActiveContinuation] = {}
        for name, character in self.characters.items():
            self.backends.setdefault(name, CheapBackend(character))
        self.player = player or next(iter(self.characters), None)
        if self.player is not None and not isinstance(self.backends[self.player], HumanBackend):
            self.backends[self.player] = HumanBackend(self.characters[self.player])
        self._sync_backend_metadata()
        self.last_responses: dict[str, ActorResponse] = {}
        self.last_results: dict[str, bool] = {}

    @staticmethod
    def _normalise_destination(value):
        """Turn JSON coordinate arrays back into the world's tuple cells."""
        if isinstance(value, list) and len(value) == 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                return value
        return value

    def _event_snapshot(self) -> dict[str, dict]:
        # Do not call export_state here.  A continuation is checked for every
        # resident, and the public snapshot also serialises inventories,
        # maps, and sanity data.  The world event index is the only information
        # needed for this interrupt gate.
        event_index = getattr(self.world, "_events", {})
        return {
            str(event_id): dict(self.world.eng.node(node)["attrs"])
            for event_id, node in event_index.items()
            if self.world.eng.has_node(node)
        }

    def _activate_continuation(self, actor: str, request: ActorContinuation,
                               *, action_ok: bool):
        request = ActorContinuation.from_value(request.to_dict())
        request.destination = self._normalise_destination(request.destination)
        context = self._context(actor)
        observations = context.observations
        self._continuations[actor] = _ActiveContinuation(
            request=request,
            started_turn=context.turn,
            baseline_hunger=float(observations.get("hunger", 0.0)),
            baseline_energy=float(observations.get("energy", 100.0)),
            baseline_nearby=frozenset(
                str(resident.get("id"))
                for resident in observations.get("nearby_residents", [])
                if resident.get("id") is not None),
            baseline_position=observations.get("position"),
            baseline_events=frozenset(self._event_snapshot()),
            last_action_ok=bool(action_ok),
            destination_complete=(request.destination is not None
                                  and observations.get("position") == request.destination),
        )

    def _continuation_interrupt(self, actor: str, active: _ActiveContinuation,
                                context: ActorContext) -> str | None:
        request = active.request
        if request.poll_each_turn:
            return "poll_each_turn"
        observations = context.observations
        interrupt_on = set(request.interrupt_on)
        expected = set(request.expected_events)

        destination = self._normalise_destination(request.destination)
        if (destination is not None and active.destination_complete
                and observations.get("position") == destination):
            # Completion is not an unexpected event, but it is the natural
            # point at which a backend gets to choose the next task.
            return "destination_reached"
        nearby = {
            str(resident.get("id"))
            for resident in observations.get("nearby_residents", [])
            if resident.get("id") is not None
        }
        if "encounter" in interrupt_on and nearby - active.baseline_nearby:
            return "encounter"

        hunger = float(observations.get("hunger", 0.0))
        if ("hunger_threshold" in interrupt_on
                and active.baseline_hunger < request.hunger_threshold
                <= hunger):
            return "hunger_threshold"
        energy = float(observations.get("energy", 100.0))
        if ("energy_threshold" in interrupt_on
                and active.baseline_energy > request.energy_threshold
                >= energy):
            return "energy_threshold"
        if "task_failed" in interrupt_on and not active.last_action_ok:
            return "task_failed"

        if "world_event" in interrupt_on:
            new_events = self._event_snapshot()
            for event_id in set(new_events) - active.baseline_events:
                if str(new_events[event_id].get("kind", "")) not in expected:
                    return "world_event"
        return None

    def _continuation_response(self, active: _ActiveContinuation) -> ActorResponse:
        task = active.request.task
        if task is None and active.request.destination is not None:
            task = ProposedAction("move", {
                "destination": self._normalise_destination(active.request.destination)},
                "continue_to_destination")
        if task is None:
            return ActorResponse(continuation=active.request,
                                 backend_state={"continued": True})
        return ActorResponse(
            major_action=ProposedAction(task.action, dict(task.params), task.reason),
            continuation=active.request,
            backend_state={"continued": True},
        )

    def _sync_backend_metadata(self):
        for name, backend in self.backends.items():
            self.characters[name].backend = {
                "kind": str(getattr(backend, "kind", "unknown")),
                **communication_capabilities(backend),
            }

    def set_backend(self, actor: str, backend):
        self.backends[actor] = backend
        self._sync_backend_metadata()

    def _characters_from_world(self):
        characters = {}
        for name, node in self.world._actors.items():
            attrs = dict(self.world.eng.node(node)["attrs"])
            identity = {k: attrs.get(k) for k in ("name", "role", "klass", "group", "age", "life_stage")}
            personality = {k: attrs[k] for k in attrs
                           if k.endswith("_weight") or k.startswith("prior_")
                           or k in {"mood_bias", "arousal", "w_spite", "w_supergraph", "role_identity"}}
            characters[name] = CharacterDefinition(
                character_id=name,
                name=name,
                identity={k: v for k, v in identity.items() if v not in (None, "")},
                personality=personality,
                backend={"kind": "cheap"},
            )
        return characters

    def _context(self, actor: str) -> ActorContext:
        character = self.characters[actor]
        attrs = self.world.eng.node(self.world._actors[actor])["attrs"]
        affordances = self.world.actor_affordances(actor)
        position = self.world.actor_position(actor)
        nearby_residents = []
        if position is not None:
            for name in self.world._actors:
                if name == actor or not self.world.is_alive(name):
                    continue
                other_position = self.world.actor_position(name)
                distance = self.world.distance(position, other_position) if other_position else None
                if distance is not None and distance <= 8:
                    other_attrs = self.world.eng.node(self.world._actors[name])["attrs"]
                    nearby_residents.append({
                        "id": name, "name": name,
                        "role": other_attrs.get("role", ""),
                        "position": other_position, "distance": distance,
                    })
        nearby_residents.sort(key=lambda resident: (resident["distance"], resident["id"]))
        observations = {
            "turn": int(self.world._turn),
            "calendar": self.world.calendar(),
            "position": position,
            "health": attrs.get("health", "healthy"),
            "hunger": attrs.get("hunger", 0.0),
            "energy": self.world.energy(actor),
            "inventory": self.world.inventory(actor),
            "held_items": self.world.held_items(actor),
            "worn": self.world.worn(actor),
            "known_references": sorted(self.world.known_references(actor)),
            "turn_state": self.world.actor_turn_state(actor),
            "nearby_residents": nearby_residents,
            "world_frames": {
                "laws": [dict(v) for v in self.world._law_specs.values()],
                "policies": [dict(v) for v in self.world._policy_specs.values()],
                "documents": [{"kind": k, "name": n} for k, n in self.world._documents],
            },
        }
        active = self._continuations.get(actor)
        if active is not None:
            observations["continuation"] = active.request.to_dict()
        recipient_interfaces = {
            name: communication_capabilities(backend)
            for name, backend in self.backends.items() if name != actor
        }
        return ActorContext(character, int(self.world._turn), observations, affordances,
                            recipient_interfaces=recipient_interfaces)

    def _adapt_speech(self, speaker, target, content, message=None):
        """Choose free text or the structured interface per conversation pair."""
        source = self.backends.get(speaker)
        recipient = self.backends.get(target) if target is not None else None
        source_caps = communication_capabilities(source) if source is not None else {
            "mode": "free_text", "supports_free_text": True,
            "requires_conversational_interface": False}
        target_caps = communication_capabilities(recipient) if recipient is not None else source_caps
        structured = ConversationMessage.from_value(message, fallback_content=str(content))
        if (source_caps["requires_conversational_interface"]
                or target_caps["requires_conversational_interface"]):
            return self.conversation_interface.envelope(structured, original_content=content)
        return {"content": str(content), "communication_mode": "free_text",
                "conversation": structured.to_dict()}

    def submit_player_response(self, response: ActorResponse):
        backend = self.backends[self.player]
        if not isinstance(backend, HumanBackend):
            raise TypeError("the selected player backend is not human")
        backend.submit(response)

    def _apply_response(self, actor: str, response: ActorResponse) -> bool:
        ok = True
        if response.major_action is not None:
            proposal = response.major_action
            plan = {"action": proposal.action, **proposal.params}
            ok = bool(self.world.enact_plan(actor, plan))
        for utterance in response.utterances:
            target = utterance.get("target")
            content = utterance.get("content", "")
            message = utterance.get("message")
            if message is None and any(key in utterance for key in ("act", "slots", "template", "template_id")):
                message = utterance
            self.world.free_action(actor, "speak", target=target, content=content,
                                   loudness=utterance.get("loudness", 1.0), message=message)
        for update in response.memory_updates:
            self.add_memory(actor, update)
        return ok

    def add_memory(self, actor: str, data: dict[str, Any]) -> MemoryRecord:
        character = self.characters[actor]
        record = MemoryRecord(
            memory_id=str(data.get("memory_id", f"memory:{actor}:{len(character.memories) + 1}")),
            content=data.get("content", data.get("text", "")),
            kind=str(data.get("kind", "episodic")),
            source=str(data.get("source", actor)),
            confidence=float(data.get("confidence", 1.0)),
            salience=float(data.get("salience", 0.5)),
            turn=int(data.get("turn", self.world._turn)),
            private=bool(data.get("private", True)),
        )
        character.memories.append(record)
        return record

    def step(self) -> dict:
        """Advance one shared turn, or return waiting for human input."""
        responses = {}
        for actor, backend in self.backends.items():
            if not self.world.is_alive(actor):
                continue
            context = self._context(actor)
            active = self._continuations.get(actor) if self.continuations_enabled else None
            reason = (self._continuation_interrupt(actor, active, context)
                      if active is not None else None)
            if active is not None and reason is None:
                response = self._continuation_response(active)
            else:
                response = backend.decide(context)
                if reason is not None:
                    response.backend_state.setdefault("continuation_interrupted", reason)
            responses[actor] = response
            if response.waiting:
                return {"status": "waiting", "actor": actor,
                        "context": self._context(actor).observations,
                        "affordances": self.world.actor_affordances(actor)}

        # This opens the turn and advances the physical environment, but does
        # not let the embedded Ocelot loop act behind the backends.
        self.world.tick()
        self.last_responses = responses
        self.last_results = {actor: self._apply_response(actor, response)
                             for actor, response in responses.items()}
        self.world.resolve_actor_turn()
        for actor, response in responses.items():
            request = response.continuation if self.continuations_enabled else None
            if request is not None and self.world.is_alive(actor):
                self._activate_continuation(actor, request,
                                            action_ok=self.last_results.get(actor, True))
            else:
                self._continuations.pop(actor, None)
        return {"status": "advanced", "turn": int(self.world._turn),
                "results": dict(self.last_results), "snapshot": self.snapshot()}

    def dump_held_state(self, actor: str) -> dict:
        """Reverse API exposed to UI/debuggers for one cognition provider."""
        return self.backends[actor].dump_held_state().to_dict()

    def dump_all_held_state(self) -> dict[str, dict]:
        return {actor: self.dump_held_state(actor) for actor in self.backends}

    def snapshot(self) -> dict:
        return {
            "schema": "bigville/game/1",
            "player": self.player,
            "world": self.world.export_state(event_tail=100),
            "characters": {name: c.to_dict() for name, c in self.characters.items()},
            "held_state": self.dump_all_held_state(),
            "continuations": {
                actor: active.request.to_dict()
                for actor, active in self._continuations.items()
            },
        }

    def save_characters(self, path: str | Path):
        Path(path).write_text(json.dumps({name: c.to_dict() for name, c in self.characters.items()}, indent=2))
