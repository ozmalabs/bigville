"""Turn-driven game orchestration over the canonical Bigville world."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backends import (ActorContext, ActorResponse, CheapBackend, ConversationMessage,
                       HumanBackend, OcelotBackend, TemplateConversationInterface)
from .backends.protocol import communication_capabilities
from .character import CharacterDefinition, MemoryRecord


class BigvilleGame:
    """A playable session where human and autonomous actors share one API."""

    def __init__(self, world, *, player: str | None = None,
                 characters: dict[str, CharacterDefinition] | None = None,
                 backends: dict[str, Any] | None = None):
        self.world = world
        self.world._autonomous_actors = False
        self.conversation_interface = TemplateConversationInterface()
        self.world.set_conversation_adapter(self._adapt_speech)
        self.characters = characters or self._characters_from_world()
        self.backends = backends or {}
        for name, character in self.characters.items():
            self.backends.setdefault(name, CheapBackend(character))
        self.player = player or next(iter(self.characters), None)
        if self.player is not None and not isinstance(self.backends[self.player], HumanBackend):
            self.backends[self.player] = HumanBackend(self.characters[self.player])
        self._sync_backend_metadata()
        self.last_responses: dict[str, ActorResponse] = {}
        self.last_results: dict[str, bool] = {}

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
        observations = {
            "turn": int(self.world._turn),
            "calendar": self.world.calendar(),
            "position": self.world.actor_position(actor),
            "health": attrs.get("health", "healthy"),
            "hunger": attrs.get("hunger", 0.0),
            "energy": self.world.energy(actor),
            "inventory": self.world.inventory(actor),
            "known_references": sorted(self.world.known_references(actor)),
            "turn_state": self.world.actor_turn_state(actor),
            "world_frames": {
                "laws": [dict(v) for v in self.world._law_specs.values()],
                "policies": [dict(v) for v in self.world._policy_specs.values()],
                "documents": [{"kind": k, "name": n} for k, n in self.world._documents],
            },
        }
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
            response = backend.decide(self._context(actor))
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
        }

    def save_characters(self, path: str | Path):
        Path(path).write_text(json.dumps({name: c.to_dict() for name, c in self.characters.items()}, indent=2))
