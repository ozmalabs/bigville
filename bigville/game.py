"""Turn-driven game orchestration over the canonical Bigville world."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import (ActorContext, ActorResponse, CheapBackend, ConversationMessage,
                       HumanBackend, OcelotBackend, TemplateConversationInterface)
from .backends.animal import AnimalNPCBackend
from .backends.cheap import simple_policy_for
from .backends.protocol import ActorContinuation, ProposedAction
from .backends.protocol import communication_capabilities
from .character import CharacterDefinition, FrameSeed, MemoryRecord
from worlds.bigville_bond_world import BigvilleBondWorld
from domains.data_view import world_entities


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
                 continuations: bool = True, autonomous: bool = False,
                 ticks_per_period: int | str | None = "world"):
        if ticks_per_period == "world":
            # Read the period length from the world's data pack (TIME); worlds
            # without a pack keep the historical 96-tick day.
            time = getattr(getattr(world, "E", None), "TIME", None) or {}
            ticks_per_period = int(time.get("ticks_per_period", 96))
        if ticks_per_period is not None and (not isinstance(ticks_per_period, int) or isinstance(ticks_per_period, bool) or ticks_per_period < 1):
            raise ValueError("ticks_per_period must be a positive integer or None")
        if autonomous and player is not None:
            raise ValueError("autonomous sessions cannot have a player")
        self.world = world
        self.ticks_per_period = ticks_per_period
        self.world._autonomous_actors = False
        self.conversation_interface = TemplateConversationInterface()
        self.world.set_conversation_adapter(self._adapt_speech)
        self.characters = characters or self._characters_from_world()
        self.backends = backends or {}
        # This is deliberately a game-session option.  A debugger, test, or
        # highly reactive world can retain the older decide-every-turn mode.
        self.continuations_enabled = bool(continuations)
        self._continuations: dict[str, _ActiveContinuation] = {}
        # One-turn, observer-specific records of directly visible object
        # movement. These describe physical evidence, not the actor's intent.
        self._physical_events: dict[str, list[dict[str, Any]]] = {}
        # Per actor: (turn, start, end) of the practice observations that turn's contexts carry.
        self._published_practice: dict[str, tuple[int | None, int, int]] = {}
        self._animal_backends: dict[str, AnimalNPCBackend] = {}
        self._animal_decisions: dict[str, dict[str, Any]] = {}
        for name, character in self.characters.items():
            profile = getattr(self.world, "_scenario_simple_profiles", {}).get(name, "default")
            self.backends.setdefault(name, CheapBackend(character, policy=simple_policy_for(profile)))
        self.player = None if autonomous else (player or next(iter(self.characters), None))
        if self.player is not None and not isinstance(self.backends[self.player], HumanBackend):
            self.backends[self.player] = HumanBackend(self.characters[self.player])
        self._sync_backend_metadata()
        self._sync_animal_backends()
        self.last_responses: dict[str, ActorResponse] = {}
        self.last_results: dict[str, bool] = {}

    def _sync_animal_backends(self):
        """Create session-owned animal NPC backends for newly added animals."""
        entities = world_entities(self.world)
        setups = getattr(entities, "ANIMAL_NPC_SETUP", {})
        for name in self.world._animals:
            if name in self._animal_backends:
                continue
            species = self.world.eng.node(self.world._animals[name])["attrs"].get("species", "")
            self._animal_backends[name] = AnimalNPCBackend(
                name, species, dict(setups.get(species, {})))
            self._animal_decisions[name] = {}

    def animal_turn(self) -> dict[str, dict[str, Any]]:
        """Invoke animal cognition and submit each chosen action to the world."""
        self._sync_animal_backends()
        for name, backend in self._animal_backends.items():
            if not self.world.animal_alive(name):
                continue
            node = self.world._animals[name]
            attrs = self.world.eng.node(node)["attrs"]
            enclosure = self.world.animal_enclosure(name)
            position = self.world.animal_position(name)
            context = ActorContext(
                backend.character, int(self.world._turn),
                {"hunger": float(attrs.get("hunger", 0.0)),
                 "insecurity": 1.0 if not self.world._animal_allowed_cell(name, position) else 0.0,
                 "position": position,
                 "enclosure_cells": sorted(self.world._enclosure_cells.get(enclosure, ())),
                 "enclosure_intact": bool(enclosure and self.world.enclosure_intact(enclosure)),
                 "social_pressure": 0.0, "arousal": 0.4},
                self.world.animal_affordances(name))
            response = backend.decide(context)
            choice = dict(backend.last_choice)
            self._animal_decisions[name] = choice
            action = response.major_action
            self.world.apply_animal_action(
                name, action.action if action else "stay",
                action.params if action else {})
        return {name: dict(choice) for name, choice in self._animal_decisions.items()}

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

    def _nearby_resident_ids(self, actor: str, position) -> set[str]:
        if position is None:
            return set()
        nearby = set()
        for name in self.world._actors:
            if name == actor or not self.world.is_alive(name):
                continue
            other_position = self.world.actor_position(name)
            distance = self.world.distance(position, other_position) if other_position else None
            if distance is not None and distance <= 8:
                nearby.add(str(name))
        return nearby

    def _activate_continuation(self, actor: str, request: ActorContinuation,
                               *, action_ok: bool):
        request = ActorContinuation.from_value(request.to_dict())
        request.destination = self._normalise_destination(request.destination)
        attrs = self.world.eng.node(self.world._actors[actor])["attrs"]
        position = self.world.actor_position(actor)
        self._continuations[actor] = _ActiveContinuation(
            request=request,
            started_turn=int(self.world._turn),
            baseline_hunger=float(attrs.get("hunger", 0.0)),
            baseline_energy=float(self.world.energy(actor)),
            baseline_nearby=frozenset(self._nearby_resident_ids(actor, position)),
            baseline_position=position,
            baseline_events=frozenset(self._event_snapshot()),
            last_action_ok=bool(action_ok),
            destination_complete=(request.destination is not None
                                  and position == request.destination),
        )

    def _continuation_interrupt(self, actor: str, active: _ActiveContinuation,
                                context: ActorContext | None = None) -> str | None:
        request = active.request
        if request.poll_each_turn:
            return "poll_each_turn"
        interrupt_on = set(request.interrupt_on)
        expected = set(request.expected_events)
        if context is not None:
            observations = context.observations
            position = observations.get("position")
            nearby = {
                str(resident.get("id"))
                for resident in observations.get("nearby_residents", [])
                if resident.get("id") is not None
            }
            hunger = float(observations.get("hunger", 0.0))
            energy = float(observations.get("energy", 100.0))
        else:
            attrs = self.world.eng.node(self.world._actors[actor])["attrs"]
            position = self.world.actor_position(actor)
            nearby = (self._nearby_resident_ids(actor, position)
                      if "encounter" in interrupt_on else set())
            hunger = float(attrs.get("hunger", 0.0))
            energy = float(self.world.energy(actor))

        destination = self._normalise_destination(request.destination)
        if (destination is not None and active.destination_complete
                and position == destination):
            # Completion is not an unexpected event, but it is the natural
            # point at which a backend gets to choose the next task.
            return "destination_reached"
        if "encounter" in interrupt_on and nearby - active.baseline_nearby:
            return "encounter"

        if ("hunger_threshold" in interrupt_on
                and active.baseline_hunger < request.hunger_threshold
                <= hunger):
            return "hunger_threshold"
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
        entities = world_entities(self.world)
        characters = {}
        scenario_characters = getattr(self.world, "_scenario_character_data", {})
        for name, node in self.world._actors.items():
            attrs = dict(self.world.eng.node(node)["attrs"])
            identity = {k: attrs.get(k) for k in ("name", "role", "klass", "group", "age", "life_stage")}
            personality = {k: attrs[k] for k in attrs
                           if k.endswith("_weight") or k.startswith("prior_")
                           or k in {"mood_bias", "arousal", "w_spite", "w_supergraph",
                                    "role_identity", "cred_on", "valence", "resolution_bins"}}
            preset = dict(scenario_characters.get(name, {}))
            identity.update(dict(preset.get("identity", {})))
            personality.update(dict(preset.get("personality", {})))
            memories = [MemoryRecord(**memory) if isinstance(memory, dict)
                        else MemoryRecord(f"memory:{name}:{index + 1}", memory)
                        for index, memory in enumerate(preset.get("memories", []))]
            # Authored reference priors are resident-held cognition inputs.
            # The physical world stores reference templates, never inferred beliefs.
            known_reference_priors = set()
            for index, prior in enumerate(preset.get("reference_priors", [])):
                if isinstance(prior, str):
                    reference_name, content = prior, {"name": prior}
                elif isinstance(prior, dict):
                    reference_name = str(prior.get("name", ""))
                    content = dict(prior)
                else:
                    continue
                if reference_name and reference_name not in known_reference_priors:
                    memories.append(MemoryRecord(
                        memory_id=f"reference:{name}:{reference_name}:{index + 1}",
                        content=content, kind="reference_knowledge",
                        source="character_prior", private=True))
                    known_reference_priors.add(reference_name)
            # Recipe knowledge is a private backend prior. Scenario-authored
            # priors take precedence; the default cheap-backend profession
            # catalog supplies conventional craft knowledge for legacy casts.
            explicit_priors = preset.get("recipe_priors")
            if explicit_priors is None:
                roles = {str(attrs.get("role", ""))}
                roles.update(filter(None, str(attrs.get("trades", "")).split(",")))
                known_recipe_names = sorted(
                    recipe["name"] for recipe in entities.RECIPES
                    if recipe.get("requires") in roles and recipe.get("common") is not False)
            else:
                known_recipe_names = [
                    str(prior.get("recipe", prior.get("name", "")))
                    if isinstance(prior, dict) else str(prior)
                    for prior in explicit_priors]
            existing_recipe_beliefs = {
                str(memory.content.get("recipe")) for memory in memories
                if memory.kind == "recipe_knowledge" and isinstance(memory.content, dict)
                and memory.content.get("recipe")
            }
            for recipe in known_recipe_names:
                if recipe and recipe not in existing_recipe_beliefs:
                    memories.append(MemoryRecord(
                        memory_id=f"recipe:{name}:{recipe}",
                        content={"recipe": recipe, "belief": "can_attempt"},
                        kind="recipe_knowledge", source="scenario_prior", private=True))
            held_frames = []
            for frame in preset.get("held_frames", []):
                if isinstance(frame, str):
                    held_frames.append(FrameSeed(frame))
                elif isinstance(frame, dict):
                    held_frames.append(FrameSeed(**frame))
            characters[name] = CharacterDefinition(
                character_id=name,
                name=name,
                identity={k: v for k, v in identity.items() if v not in (None, "")},
                personality=personality,
                memories=memories,
                held_frames=held_frames,
                backend={"kind": getattr(self.world, "_scenario_actor_backends", {}).get(name, "cheap")},
            )
        return characters

    def _relationship_signal(self, actor: str, other: str) -> dict[str, float]:
        """Mechanical exposure of held relationship state, nothing decided.

        Bigville does not bundle cognition (``backends/ocelot.py``'s own
        docstring); a real Ocelot-side backend deciding HOW to speak to this
        interlocutor -- register, style, anything downstream of "how close is
        this tie" -- needs to know that from bigville, since bigville is the
        only side holding it.  ``band_code`` is the already-correct,
        already-tested discrete banding (``BigvilleBondWorld._band_code``,
        reused verbatim, not reimplemented) an external backend's own
        quantized-codebook decision can key on directly, matching the
        "quantised codebook over a quantised set of interlocutors" shape.
        Absent any ``set_relationship`` call for this pair, both fields read
        as the honest zero/floor default -- not a fabricated stranger label.
        """
        relationship = self.world.relationship(actor, other)
        if relationship is None:
            return {"tie_strength": 0.0, "band_code": 0.0}
        attrs = self.world.eng.node(relationship)["attrs"]
        strength = float(attrs.get("strength", 0.0))
        tie_strength = max(0.0, strength)
        resentment = max(0.0, -strength) if attrs.get("kind") == "feud" else 0.0
        band_code = BigvilleBondWorld._band_code(
            {"tie_strength": tie_strength, "affect_resentment": resentment})
        return {"tie_strength": tie_strength, "band_code": band_code}

    @staticmethod
    def _shared_bucket_count(actor_attrs, other_attrs) -> int:
        """Mechanical attr comparison, nothing decided (same boundary as
        ``_relationship_signal``): how many of role/klass/group this pair
        already shares. Bigville only counts matches; an external backend
        decides what a shared bucket is WORTH (mere-exposure/familiarity
        warmth, Zajonc 1968 -- Tajfel, Billig, Bundy & Flament 1971's
        minimal-group point that bucket membership alone, no real content,
        is enough to matter)."""
        count = 0
        for key in ("role", "klass", "group"):
            a, b = actor_attrs.get(key), other_attrs.get(key)
            if a and b and a == b:
                count += 1
        return count

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
                        "klass": other_attrs.get("klass", ""),
                        "group": other_attrs.get("group", ""),
                        "position": other_position, "distance": distance,
                        "shared_bucket_count": self._shared_bucket_count(attrs, other_attrs),
                        **self._relationship_signal(actor, name),
                    })
        nearby_residents.sort(key=lambda resident: (resident["distance"], resident["id"]))
        # Semantic interpretations live in this resident's backend-owned
        # memory. The town's master tables are not universal beliefs.
        held_laws = {str(memory.content.get("name")) for memory in character.memories
                     if memory.kind == "law_knowledge" and isinstance(memory.content, dict)}
        held_policies = {str(memory.content.get("name")) for memory in character.memories
                         if memory.kind == "policy_knowledge" and isinstance(memory.content, dict)}
        known_references = {str(memory.content.get("name")) for memory in character.memories
                            if memory.kind == "reference_knowledge" and isinstance(memory.content, dict)}
        known_laws = [dict(spec) for name, spec in self.world._law_specs.items()
                      if name in held_laws]
        known_policies = [dict(spec) for name, spec in self.world._policy_specs.items()
                          if name in held_policies]
        read_documents = []
        for (kind, name), document in self.world._documents.items():
            if self.world.eng.has_edge(self.world._actors[actor], "read_document", document):
                doc_attrs = self.world.eng.node(document)["attrs"]
                read_documents.append({key: doc_attrs[key] for key in
                                       ("kind", "name", "title", "scope", "version")
                                       if key in doc_attrs})
        observations = {
            "turn": int(self.world._turn),
            "calendar": self.world.calendar(),
            "position": position,
            "terrain": self.world.terrain_state(position),
            "terrain_movement": self.world.terrain_movement_rules(),
            "health": attrs.get("health", "healthy"),
            "hunger": attrs.get("hunger", 0.0),
            "energy": self.world.energy(actor),
            "inventory": self.world.inventory(actor),
            "held_items": self.world.held_items(actor),
            "physical_objects": self.world.physical_object_observations(actor),
            "physical_events": [dict(event) for event in self._physical_events.get(actor, [])],
            "worn": self.world.worn(actor),
            "known_references": sorted(known_references),
            "turn_state": self.world.actor_turn_state(actor),
            "nearby_residents": nearby_residents,
            # Communication is delivered as records.  Cognition may inspect
            # both the provider's raw payload and the human-facing text; the
            # world does not interpret either one into an action.
            "heard_utterances": self.world.heard_utterances(actor),
            "world_frames": {
                "laws": known_laws,
                "policies": known_policies,
                "documents": read_documents,
            },
        }
        # The actor's own practice records (Phase 012): cognitive work the world does not turn
        # into skill, each carried by the contexts of one turn so the backend decides what was
        # learned. Every _context call within a turn returns the same records.
        practice = self.world.actor_observations(actor, "practice")
        turn = int(self.world._turn)
        last_turn, start, end = self._published_practice.get(actor, (None, 0, 0))
        if last_turn != turn:
            start, end = end, len(practice)
            self._published_practice[actor] = (turn, start, end)
        observations["practice"] = [dict(record) for record in practice[start:end]]
        active = self._continuations.get(actor)
        if active is not None:
            observations["continuation"] = active.request.to_dict()
        recipient_interfaces = {
            name: communication_capabilities(backend)
            for name, backend in self.backends.items() if name != actor
        }
        return ActorContext(character, int(self.world._turn), observations, affordances,
                            recipient_interfaces=recipient_interfaces)

    def _visible_object_snapshot(self, actor):
        return {item["id"]: str(item.get("location", "world"))
                for item in self.world.physical_object_observations(actor)}

    def _record_physical_changes(self, actor, before, after, turn):
        """Record changed locations only for residents who could see the object.

        Event wording stays deliberately mechanical: a witness can see an
        object move and who performed the move, but Bigville does not infer
        taking, theft, permission, or ownership from that movement.
        """
        changed = []
        for object_id in set(before[actor]) | set(after[actor]):
            old = before[actor].get(object_id)
            new = after[actor].get(object_id)
            if old != new and (old is not None or new is not None):
                changed.append((object_id, old, new))
        for object_id, old, new in changed:
            for observer in before:
                # Visibility at either endpoint is evidence of a visible
                # physical change; hidden container contents never enter it.
                if (object_id not in before[observer] and object_id not in after[observer]):
                    continue
                # The acting resident necessarily perceives their own
                # physical movement. Other residents need to be close enough
                # to witness the action at that moment, not merely encounter
                # its result later.
                if observer != actor:
                    actor_pos = self.world.actor_position(actor)
                    observer_pos = self.world.actor_position(observer)
                    if (actor_pos is None or observer_pos is None
                            or self.world.distance(actor_pos, observer_pos) is None
                            or self.world.distance(actor_pos, observer_pos) > 1):
                        continue
                self._physical_events.setdefault(observer, []).append({
                    "actor": actor, "action": "moved_object", "object": object_id,
                    "from": old, "to": new,
                    "turn": turn,
                    # Available to the next decision pass, then dropped when
                    # the world turn advances again.
                    "expires_turn": turn,
                })

    def _adapt_speech(self, speaker, target, content, message=None, raw_data=None,
                      backend_owned=False):
        """Mediate delivery without rewriting backend-owned speech.

        A proposal carrying ``raw_data`` is already a complete utterance from
        cognition.  Keep its text and payload intact even when the recipient
        is a legacy structured-interface backend.  The old template adapter is
        retained only for pre-envelope callers that submit ``act``/``slots``
        without backend-owned text.
        """
        if backend_owned or raw_data is not None:
            return {
                "content": str(content),
                "raw_data": raw_data,
                "communication_mode": "free_text",
                "speech_origin": "backend",
            }
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

    def _raw_delivery_metadata(self, target):
        """Describe recipient comprehension without inspecting provider data."""
        if target is None:
            return {"raw_understanding": {
                "status": "not_applicable",
                "note": "Broadcast speech has no single recipient backend to assess.",
            }}
        recipient = self.backends.get(target)
        if recipient is None:
            return {"raw_understanding": {
                "status": "not_assessed",
                "note": "The recipient backend is not registered with this game session.",
            }}
        capabilities = communication_capabilities(recipient)
        if capabilities.get("understands_raw_speech", False):
            return {"raw_understanding": {
                "status": "understood",
                "note": "The recipient backend declares support for the raw speech payload.",
            }}
        return {"raw_understanding": {
            "status": "not_understood",
            "note": "The recipient received the exact text but cannot interpret the backend raw payload.",
        }}

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
            if hasattr(utterance, "to_dict"):
                utterance = utterance.to_dict()
            if not isinstance(utterance, dict):
                raise TypeError("utterance proposals must be objects")
            target = utterance.get("target")
            # New backends return their own surface text and opaque raw data.
            # Presence of the key matters: an empty object is still a valid
            # provider payload and must not fall through to legacy templating.
            owns_speech = "text" in utterance or "raw" in utterance or "raw_data" in utterance
            content = utterance.get("text", utterance.get("content", ""))
            message = utterance.get("message")
            raw_data = utterance.get("raw", utterance.get("raw_data"))
            if owns_speech:
                message = None
            elif message is None and any(key in utterance for key in ("act", "slots", "template", "template_id")):
                message = utterance
            self.world.free_action(actor, "speak", target=target, content=content,
                                   loudness=utterance.get("loudness", 1.0), message=message,
                                   raw_data=raw_data, backend_owned=owns_speech,
                                   delivery_metadata=(self._raw_delivery_metadata(target)
                                                      if owns_speech else None))
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
        # Period changes happen only after a successful turn, below. Publish
        # them on the next decision rather than changing the world while a
        # human is still deciding.
        responses = {}
        for actor, backend in self.backends.items():
            if not self.world.is_alive(actor):
                continue
            active = self._continuations.get(actor) if self.continuations_enabled else None
            reason = (self._continuation_interrupt(actor, active)
                      if active is not None else None)
            if active is not None and reason is None:
                response = self._continuation_response(active)
            else:
                context = self._context(actor)
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
        self.animal_turn()
        self.last_responses = responses
        self.last_results = {}
        for actor, response in responses.items():
            # Avoid actor-by-actor world scans in the common object-free
            # town. With objects present, only the actor and residents
            # close enough to witness this action need endpoint snapshots.
            before = {}
            if response.major_action is not None and self.world._physical_objects:
                actor_pos = self.world.actor_position(actor)
                for name in self.backends:
                    other_pos = self.world.actor_position(name)
                    if (name == actor or (actor_pos is not None and other_pos is not None
                            and self.world.distance(actor_pos, other_pos) is not None
                            and self.world.distance(actor_pos, other_pos) <= 1)):
                        before[name] = self._visible_object_snapshot(name)
            result = self._apply_response(actor, response)
            self.last_results[actor] = result
            if result and before:
                after = {name: self._visible_object_snapshot(name) for name in before}
                self._record_physical_changes(actor, before, after, int(self.world._turn))
        self.world.resolve_actor_turn()
        # Context construction is observational (trace/UI callers may ask for
        # it repeatedly). Expire records once the successful step has advanced
        # beyond their lifetime; every living actor has had its decision pass.
        for observer, events in self._physical_events.items():
            self._physical_events[observer] = [
                event for event in events
                if event.get("expires_turn", -1) >= int(self.world._turn)
            ]
        if self.ticks_per_period is not None and self.world._turn % self.ticks_per_period == 0:
            self.world.pass_period()
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
