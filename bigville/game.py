"""Turn-driven game orchestration over the canonical Bigville world."""
from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .backends import (ActorContext, ActorResponse, CheapBackend, ConversationMessage,
                       HumanBackend, OcelotBackend, TemplateConversationInterface)
from .backends.animal import AnimalNPCBackend
from .backends.cheap import simple_policy_for
from .backends.protocol import ActorContinuation, ProposedAction
from .backends.protocol import communication_capabilities
from .concurrency import decide_pooled
from .character import CharacterDefinition, FrameSeed, MemoryRecord
from worlds.bigville_bond_world import BigvilleBondWorld
from worlds.tick_graph import TickGraph, build_tick_graph
from domains.data_view import world_entities


_WAITING = object()   # a reaction that a human holder has not yet given
_MISSING = object()   # an absent per-actor entry, e.g. no published practice window


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


@dataclass
class _DecisionSnapshot:
    """The frozen, read-only inputs of one decision phase (TG03).

    Deliberately lightweight: the canonical world graph is not copied. The
    snapshot records the turn and a plain-dict copy of the actor positions at
    the moment the decision phase began, plus the practice window prepared for
    every actor that needs a context this turn. Its purpose is to prove that
    context construction is read-only and to give later tick-graph phases a
    seam; it is not a general-purpose world copy.
    """

    turn: int
    positions: dict[str, Any]
    practice_windows: dict[str, tuple[int, int, int]]


class BigvilleGame:
    """A playable session where human and autonomous actors share one API."""

    # TG03: threads used to build one turn's decision contexts. 1 is serial.
    context_workers = 1
    # TG03 debug switch: True builds every context before deciding (the default
    # path); False keeps the old inline build-then-decide loop as an oracle.
    _defer_decisions = True
    # TG03 debug switch: hash the canonical world checkpoint before and after
    # context construction. Off by default; tests may enable it or call
    # _assert_decision_snapshot_unchanged directly.
    _verify_context_purity = False
    # TG04: build and store the turn's read/write graph before any response is
    # applied. The graph is observational in this phase; set to False to keep
    # the pre-TG04 path with no graph object at all.
    tick_graph_enabled = True
    # The graph built for the last advanced turn (None when disabled or waiting).
    last_tick_graph: TickGraph | None = None

    def __init__(self, world, *, player: str | None = None,
                 characters: dict[str, CharacterDefinition] | None = None,
                 backends: dict[str, Any] | None = None,
                 continuations: bool = True, autonomous: bool = False,
                 ticks_per_period: int | str | None = "world",
                 tick_graph_enabled: bool | None = None):
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
        if tick_graph_enabled is not None:
            self.tick_graph_enabled = bool(tick_graph_enabled)
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
        if self.player is not None:
            # Ask the waiting human backend before any NPC backend. A missing
            # human response must not discard already-computed NPC decisions.
            player_backend = self.backends.pop(self.player)
            self.backends = {self.player: player_backend, **self.backends}
        self._sync_backend_metadata()
        self._sync_animal_backends()
        self.last_responses: dict[str, ActorResponse] = {}
        self.last_results: dict[str, bool] = {}
        self.last_errors: dict[str, str] = {}
        # Actors in the order their responses were applied on the last advanced turn (Phase 025).
        self.last_order: list[str] = []
        # TG04: the read/write graph of the last advanced turn. Built but not
        # used as an executor in this phase.
        self.last_tick_graph: TickGraph | None = None
        # Phase 029: a turn waiting for a holder's reaction (None when no turn is waiting), and the newest
        # contested takes (turn, attacker, target, offer, reaction, outcome). Not checkpointed.
        self._suspended: dict[str, Any] | None = None
        self.contest_log: deque = deque(maxlen=int(world_entities(self.world).CONTEST["log_limit"]))

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
        return set(self.world.actors_near(position, 8, exclude=actor))

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
        # fix_simple_village: a continuation that names body_down stops once the resident is asleep, collapsed or
        # passed out. The backend then decides, and the world publishes no affordances to a down body.
        if "body_down" in interrupt_on and self.world._sleep_code(actor) is not None:
            return "body_down"
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

    def _derived_knowledge_memories(self, name, attrs, memories, *, explicit_recipes=False):
        """The derived knowledge priors of one resident as private memory records (Phase 019).

        Derived from the world's own facts about the resident (job, skills, capacities, history, household,
        genealogical kin terms, neighbours) by domains.knowledge. Positions are the world's at founding: a
        place's cell for an exact location, and its landmark otherwise. An item already set by the scenario
        (a memory with the same `item`) is not replaced, and neither is a recipe with explicit recipe_priors."""
        from domains.knowledge import derive_knowledge, knowledge_memories, person_from_attrs
        entities = world_entities(self.world)
        kin_terms = ([row["term"] for row in self.world.kin_terms_held(name)]
                     if hasattr(self.world, "kin_terms_held") else [])
        neighbours = []
        for other, node in self.world._actors.items():
            if other == name:
                continue
            other_attrs = self.world.eng.node(node)["attrs"]
            job = str(other_attrs.get("role", ""))
            workplace = str(entities.FOUNDING_JOBS.get(job, {}).get("workplace", "")) if entities.FOUNDING_JOBS else ""
            neighbours.append({"name": other, "job": job, "household": str(other_attrs.get("household", "")),
                               "workplace": workplace})
        home = self.world.actor_position(name)
        person = person_from_attrs(name, attrs, pack=entities, history=attrs.get("history"),
                                   kin_terms=kin_terms, neighbours=neighbours, home_cell=home)
        derived = derive_knowledge(person, entities)
        layout = getattr(self.world, "_map_layout", None) or {}
        aliases = entities.FOUNDING_ANCHOR_ALIASES or {}
        positions = {}
        for item in derived:
            kind, _, place_name = item.partition(":")
            if kind != "place":
                continue
            believed = {"landmark": str(aliases.get(place_name, place_name))}
            if place_name == "home" and home is not None:
                believed["position"] = list(home)
            elif place_name in self.world._building_sites:
                believed["position"] = list(self.world._building_sites[place_name])
            elif place_name in layout.get("deposits", {}):
                believed["position"] = list(layout["deposits"][place_name])
            elif place_name == "market" and layout.get("work", {}).get("market"):
                believed["position"] = list(layout["work"]["market"])
            elif place_name == "pasture" and layout.get("farms"):
                believed["position"] = list(layout["farms"][0])
            positions[place_name] = believed
        existing = {memory.content.get("item") for memory in memories
                    if isinstance(memory.content, dict) and memory.content.get("item")}
        # A resident with no recorded history (a scenario actor) gets only the recipe knowledge that
        # their trades give. The awareness of the village is drawn for the founders, who have histories.
        has_history = "history" in attrs
        out = []
        for record in knowledge_memories(derived, positions=positions):
            content = record["content"]
            if content["item"] in existing:
                continue
            if explicit_recipes and content["type"] == "recipe":
                continue
            if not has_history and not (content["type"] == "recipe" and content["understands"] > 0):
                continue
            out.append(MemoryRecord(memory_id=record["memory_id"], content=content,
                                    kind=record["kind"], source="derived_prior", private=True))
        return out

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
            # Recipe and other knowledge priors are the resident's private memories (backend-held, not world
            # facts). Explicit scenario recipe_priors take precedence over derived recipe knowledge. Phase 019:
            # the rest of the knowledge is derived from the resident's job, skills, history, and literacy.
            explicit_priors = preset.get("recipe_priors")
            if explicit_priors is not None:
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
            memories.extend(self._derived_knowledge_memories(
                name, attrs, memories, explicit_recipes=explicit_priors is not None))
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

    def _derived_document_frames(self, character, held_laws, held_policies):
        """The laws and policies a resident is aware of or understands, from their derived knowledge (Phase 019).

        An understood item carries the world's spec with `aware` and the degree `understands`. An aware-only
        item carries its name and gist, never its spec. A law or policy the explicit `law_knowledge` or
        `policy_knowledge` memory already carries is not repeated. The world's full law list is not used here:
        only the items this resident holds, from this resident's memories."""
        gist = world_entities(self.world).MEMORY_GIST
        laws, policies = [], []
        for memory in character.memories:
            content = memory.content
            if not isinstance(content, dict) or content.get("source") != "derived" or not content.get("aware"):
                continue
            if content.get("type") == "law":
                specs, held, out = self.world._law_specs, held_laws, laws
            elif content.get("type") == "policy":
                specs, held, out = self.world._policy_specs, held_policies, policies
            else:
                continue
            name = str(content.get("name"))
            if name in held:
                continue
            understands = float(content.get("understands", 0.0))
            if understands > 0 and name in specs:
                # The spec's `knowledge` block is the world's rule for who understands the law: not resident content.
                spec = {key: value for key, value in dict(specs[name]).items() if key != "knowledge"}
                out.append({**spec, "aware": True, "understands": understands})
            else:
                out.append({"name": name, "aware": True, "understands": understands,
                            "gist": gist.get(content["type"], gist["default"])})
        return laws, policies

    def persona(self, actor: str) -> dict:
        """The persona card for a resident (Phase 058): traits in words, life sketch, usual day, close ties.
        A plain dict of strings, built from the resident's own character and held records."""
        from domains.persona import persona as persona_card
        return persona_card(self.characters[actor], self)

    def agent_view(self, actor: str, mode: str = "agent") -> dict:
        """The one limited interface (Phase 052): what the resident may know, in words. Mode "agent" is words
        only; "referee" adds a `referee` block with the numbers. Built by domains/agent_view.py."""
        from domains.agent_view import build_agent_view
        return build_agent_view(self, actor, mode=mode)

    def _context(self, actor: str, *, practice_window=None,
                 snapshot: _DecisionSnapshot | None = None) -> ActorContext:
        character = self.characters[actor]
        attrs = self.world.eng.node(self.world._actors[actor])["attrs"]
        affordances = self.world.actor_affordances(actor)
        position = self.world.actor_position(actor)
        nearby_residents = []
        if position is not None:
            for name in self.world.actors_near(position, 8, exclude=actor):
                other_position = self.world.actor_position(name)
                distance = self.world.distance(position, other_position)
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
        # Phase 018: derived law and policy knowledge (Phase 019 priors) reaches the frames at the level held.
        derived_laws, derived_policies = self._derived_document_frames(character, held_laws, held_policies)
        known_laws += derived_laws
        known_policies += derived_policies
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
            "intoxication": self.world.intoxication(actor),
            "intoxication_band": self.world.intoxication_band(actor),
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
        # Phase 036: the alcohol aftereffects (tolerance, craving, hangover, withdrawal, mood), with the switch on only.
        aftereffects = self.world.aftereffects(actor)
        if aftereffects:
            observations["aftereffects"] = aftereffects
        # The actor's own practice records (Phase 012): cognitive work the world does not turn
        # into skill, each carried by the contexts of one turn so the backend decides what was
        # learned. Every _context call within a turn returns the same records.
        practice = self.world.actor_observations(actor, "practice")
        if practice_window is None and snapshot is not None:
            practice_window = snapshot.practice_windows.get(actor)
        if practice_window is None:
            # External/legacy callers keep the original side effect: the first
            # context of a turn advances this actor's published window.
            turn = int(self.world._turn)
            last_turn, start, end = self._published_practice.get(actor, (None, 0, 0))
            if last_turn != turn:
                start, end = end, len(practice)
                self._published_practice[actor] = (turn, start, end)
        else:
            # TG03: the decision pre-pass owns the window, so a pooled build
            # neither reads nor writes shared game state.
            if snapshot is not None:
                assert snapshot.turn == int(self.world._turn), (
                    "context built from a stale decision snapshot")
            _, start, end = practice_window
        observations["practice"] = [dict(record) for record in practice[start:end]]
        # Phase 021: the actor's own last major-action outcome (applied, reason). Only this resident
        # sees it; the world does not publish another resident's attempt.
        observations["last_outcome"] = self.world.last_outcome(actor)
        active = self._continuations.get(actor)
        if active is not None:
            observations["continuation"] = active.request.to_dict()
        recipient_interfaces = {
            name: communication_capabilities(backend)
            for name, backend in self.backends.items() if name != actor
        }
        # Phase 054: a resident whose backend reads words only (the LLM backend) gets the agent view. Others keep
        # the raw context they always had. A failure in the view is not raised into the world: the view is left
        # out, and the LLM backend refuses to decide without one (counted as internal_error).
        view = None
        if getattr(self.backends.get(actor), "wants_agent_view", False):
            try:
                view = self.agent_view(actor)
            except Exception:
                view = None
        return ActorContext(character, int(self.world._turn), observations, affordances,
                            recipient_interfaces=recipient_interfaces, agent_view=view)

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

    def _record_speech_witnesses(self, actor, first_utterance):
        """Publish one speech act to the residents who witnessed it (Phase 028).

        Utterances from `first_utterance` on (the position in the world's utterance log before this
        resident's response was applied) are this resident's speech. Each resident who saw the speaker gets
        a physical event naming the speaker and, if that resident could see the target, the target. No content
        goes into it. A resident who heard the speech but did not see the speaker gets no event. The speaker
        gets no event either: the speaker knows what was said, and the delivery records of others are not the
        speaker's to see.
        """
        turn = int(self.world._turn)
        for node in list(self.world._utterances.values())[first_utterance:]:
            attrs = self.world.eng.node(node)["attrs"]
            target = str(attrs.get("target", ""))
            for observer, delivery in dict(attrs.get("deliveries") or {}).items():
                if observer == actor or not float(delivery.get("seen", 0.0)):
                    continue
                event = {"actor": actor, "action": "spoke", "turn": turn, "expires_turn": turn}
                if target and float(delivery.get("target_seen", 0.0)):
                    event["target"] = target
                self._physical_events.setdefault(observer, []).append(event)

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
            # Phase 053: a fogged resident's move is checked against its own map, and `toward` becomes a destination.
            from domains.map_memory import route_plan
            plan = route_plan(self, actor, plan)
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

    def _apply_response_contained(self, actor: str, response: ActorResponse) -> bool:
        """Apply one actor's response. A failure makes only this actor's result False.

        The error is kept in ``last_errors`` so the turn report can show it; the
        other actors' responses still apply and the turn completes.
        """
        try:
            return self._apply_response(actor, response)
        except Exception as exc:  # one resident's failed proposal must not stop the turn
            self.last_errors[actor] = f"{type(exc).__name__}: {exc}"
            return False

    @property
    def last_rejections(self) -> dict[str, dict]:
        """Refused major actions at the current world turn, the newest per resident.

        Derived from the world's refusal log, which checkpoints with the world, so a restored game
        reports the same value with no saved copy here. Each entry names the actor, action, reason
        (a REFUSAL_REASONS code), and turn.
        """
        turn = int(self.world._turn)
        rejections = {}
        for name in self.world._actors:
            refused = [record for record in self.world.refusals(name) if int(record["turn"]) == turn]
            if refused:
                last = refused[-1]
                rejections[name] = {"actor": name, "action": last["action"],
                                    "reason": last["reason"], "turn": turn}
        return rejections

    def turn_order(self, actors: list[str], turn: int) -> list[str]:
        """A deterministic permutation of ``actors`` for one turn (Phase 025).

        The generator is built per call from the map seed and the turn number, so it holds no state
        and checkpoints need nothing new. It is independent of ``world._rng``, so weather and failure
        draws are unchanged. Names are sorted before shuffling so the result does not depend on the
        order the backends were registered.
        """
        node = getattr(self.world, "_map_node", None)
        seed = int(self.world.eng.node(node)["attrs"].get("seed", 0.0)) if node else 0
        order = sorted(actors)
        random.Random(f"{seed}:{int(turn)}").shuffle(order)
        return order

    def _prepare_practice(self, actors) -> dict[str, tuple[int, int, int]]:
        """Advance the practice window of every actor that will build a context (TG03).

        This mirrors the old side effect inside ``_context`` exactly: the first
        context of a turn publishes ``(turn, previous_end, len(practice))``. An
        actor that will not build a context is left untouched, so its window
        keeps accumulating the way the inline loop left it.
        """
        turn = int(self.world._turn)
        windows = {}
        for actor in actors:
            practice = self.world.actor_observations(actor, "practice")
            last_turn, start, end = self._published_practice.get(actor, (None, 0, 0))
            if last_turn != turn:
                start, end = end, len(practice)
                self._published_practice[actor] = (turn, start, end)
            windows[actor] = (turn, start, end)
        return windows

    def _world_checkpoint_digest(self) -> str:
        """A stable digest of the canonical world checkpoint, for purity checks."""
        payload = json.dumps(self.world.eng.to_checkpoint_dict(), sort_keys=True,
                             separators=(",", ":"), default=repr)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _assert_decision_snapshot_unchanged(self, snapshot: _DecisionSnapshot,
                                            before_digest: str | None = None) -> None:
        """Assert that context construction did not advance or mutate the world (TG03).

        The turn and actor positions are cheap and always checked. Passing the
        checkpoint digest from before ``_build_contexts`` additionally proves
        the canonical graph is byte-for-byte unchanged.
        """
        assert snapshot.turn == int(self.world._turn), (
            "context construction advanced the world turn")
        assert snapshot.positions == dict(self.world._actor_positions), (
            "context construction moved an actor")
        if before_digest is not None:
            assert before_digest == self._world_checkpoint_digest(), (
                "context construction changed the canonical world graph")

    def _build_contexts(self, actors):
        """Build one frozen decision snapshot and every requested context (TG03).

        Returns ``(snapshot, contexts)`` with contexts keyed by actor, in the
        supplied (registration) order. A pool may build them, but the futures
        are consumed in that same order. No backend decision is taken here.
        """
        turn = int(self.world._turn)
        snapshot = _DecisionSnapshot(turn=turn,
                                     positions=dict(self.world._actor_positions),
                                     practice_windows={})
        before_digest = self._world_checkpoint_digest() if self._verify_context_purity else None
        windows = self._prepare_practice(actors)
        snapshot.practice_windows.update(windows)
        workers = int(self.context_workers or 1)
        if workers > 1 and len(actors) > 1:
            with ThreadPoolExecutor(max_workers=min(workers, len(actors)),
                                    thread_name_prefix="bigville-context") as pool:
                futures = [(actor, pool.submit(self._context, actor,
                                               practice_window=windows[actor],
                                               snapshot=snapshot))
                           for actor in actors]
                contexts = {actor: future.result() for actor, future in futures}
        else:
            contexts = {actor: self._context(actor, practice_window=windows[actor],
                                             snapshot=snapshot)
                        for actor in actors}
        if int(self.world._turn) != turn:
            raise RuntimeError("world turn changed while building decision contexts")
        self._assert_decision_snapshot_unchanged(snapshot, before_digest)
        return snapshot, contexts

    def _restore_practice_after(self, order, actor, previous) -> None:
        """Undo a pre-pass window for actors an inline waiting step never reached."""
        try:
            cutoff = order.index(actor)
        except ValueError:
            return
        for name in order[cutoff + 1:]:
            old = previous.get(name, _MISSING)
            if old is _MISSING:
                self._published_practice.pop(name, None)
            else:
                self._published_practice[name] = old

    def step(self) -> dict:
        """Advance one shared turn, or return waiting for human input."""
        if self._defer_decisions:
            return self._step_deferred()
        return self._step_inline()

    def _step_inline(self) -> dict:
        """The pre-TG03 build-then-decide loop, kept as the equivalence oracle."""
        if self._suspended is not None:
            return self._resume_suspended()
        # Period changes happen only after a successful turn, below. Publish
        # them on the next decision rather than changing the world while a
        # human is still deciding.
        responses = {}
        deferred = {}  # Phase 055: concurrent backends' (backend, context), decided together after the loop
        for actor, backend in self.backends.items():
            if not self.world.is_alive(actor):
                continue
            active = self._continuations.get(actor) if self.continuations_enabled else None
            reason = (self._continuation_interrupt(actor, active)
                      if active is not None else None)
            if active is not None and reason is None:
                # Phase 059: a model plan holds this turn; an LLM resident's autopilot still sees it.
                note_turn = getattr(backend, "note_turn", None)
                if callable(note_turn):
                    note_turn(self._context(actor))
                response = self._continuation_response(active)
            else:
                context = self._context(actor)
                if reason is not None:
                    # Phase 059: the interrupt reason, so a backend can tell why it is asked again.
                    context.backend_state["continuation_interrupted"] = reason
                if getattr(backend, "concurrent", False):
                    # Phase 055: decided with the other concurrent residents, after every context is built.
                    deferred[actor] = (backend, context)
                    continue
                response = backend.decide(context)
                if reason is not None:
                    response.backend_state.setdefault("continuation_interrupted", reason)
            responses[actor] = response
            if response.waiting:
                return {"status": "waiting", "actor": actor,
                        "context": self._context(actor).observations,
                        "affordances": self.world.actor_affordances(actor)}

        # Phase 055: the concurrent residents decide in one pool; results apply in registration order.
        for actor, response in decide_pooled(deferred).items():
            if "continuation_interrupted" in deferred[actor][1].backend_state:
                response.backend_state.setdefault("continuation_interrupted",
                                                  deferred[actor][1].backend_state["continuation_interrupted"])
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
        self.last_errors = {}
        order = self.turn_order(list(responses), int(self.world._turn))
        self.last_order = order
        # Phase 029: the cells at the start of the turn, for whether a target could see a taker coming.
        self.world.mark_turn_start()
        self.last_tick_graph = (build_tick_graph(order, responses, self.world)
                                if self.tick_graph_enabled else None)
        self._resolve_joint_groups(order, responses)
        return self._apply_turn(order, responses, 0)

    def _step_deferred(self) -> dict:
        """Build every decision context from one snapshot, then ask backends (TG03)."""
        if self._suspended is not None:
            return self._resume_suspended()
        responses = {}
        deferred = {}
        deciding = [(actor, backend) for actor, backend in self.backends.items()
                    if self.world.is_alive(actor)]
        # The interrupt gate is read-only, so it can be evaluated for the whole
        # turn before any context is built. Old code evaluated it lazily.
        reasons = {}
        for actor, _backend in deciding:
            active = self._continuations.get(actor) if self.continuations_enabled else None
            if active is not None:
                reasons[actor] = self._continuation_interrupt(actor, active)
        # The inline loop only builds a context for an uninterrupted
        # continuation when its backend has a note_turn hook.
        context_actors = []
        for actor, backend in deciding:
            active = self._continuations.get(actor) if self.continuations_enabled else None
            reason = reasons.get(actor)
            if active is not None and reason is None:
                if callable(getattr(backend, "note_turn", None)):
                    context_actors.append(actor)
            else:
                context_actors.append(actor)
        previous_practice = {
            actor: self._published_practice[actor]
            if actor in self._published_practice else _MISSING
            for actor in context_actors
        }
        _snapshot, contexts = self._build_contexts(context_actors)
        for actor, backend in deciding:
            active = self._continuations.get(actor) if self.continuations_enabled else None
            reason = reasons.get(actor)
            if active is not None and reason is None:
                note_turn = getattr(backend, "note_turn", None)
                if callable(note_turn):
                    note_turn(contexts[actor])
                response = self._continuation_response(active)
            else:
                context = contexts[actor]
                if reason is not None:
                    context.backend_state["continuation_interrupted"] = reason
                if getattr(backend, "concurrent", False):
                    deferred[actor] = (backend, context)
                    continue
                response = backend.decide(context)
                if reason is not None:
                    response.backend_state.setdefault("continuation_interrupted", reason)
            responses[actor] = response
            if response.waiting:
                # The inline loop would never have built the contexts after this
                # actor, so put their practice windows back as it left them.
                self._restore_practice_after(context_actors, actor, previous_practice)
                context = contexts.get(actor)
                if context is None:
                    context = self._context(actor)
                return {"status": "waiting", "actor": actor,
                        "context": context.observations,
                        "affordances": self.world.actor_affordances(actor)}

        # Phase 055: the concurrent residents decide in one pool; results apply in registration order.
        for actor, response in decide_pooled(deferred).items():
            if "continuation_interrupted" in deferred[actor][1].backend_state:
                response.backend_state.setdefault("continuation_interrupted",
                                                  deferred[actor][1].backend_state["continuation_interrupted"])
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
        self.last_errors = {}
        order = self.turn_order(list(responses), int(self.world._turn))
        self.last_order = order
        # Phase 029: the cells at the start of the turn, for whether a target could see a taker coming.
        self.world.mark_turn_start()
        self.last_tick_graph = (build_tick_graph(order, responses, self.world)
                                if self.tick_graph_enabled else None)
        self._resolve_joint_groups(order, responses)
        return self._apply_turn(order, responses, 0)

    def _apply_turn(self, order, responses, start):
        """Apply each actor's response in ``order`` from position ``start``, then finish the turn.

        Returns waiting when a human target must react to a contested take. The turn then resumes on the
        next step (``_resume_suspended``)."""
        for index in range(start, len(order)):
            actor = order[index]
            response = responses[actor]
            if self._is_joint(response):
                continue        # Phase 047: joint acts were resolved before the turn's own responses
            utterances_before = len(self.world._utterances)
            if self._is_contest(response):
                pending, reason = self.world.contest_begin(actor, response.major_action.action,
                                                           dict(response.major_action.params))
                choice, note = None, ""
                if pending is not None:
                    choice, note = self._contest_choice(pending)
                    if choice is _WAITING:
                        self._suspended = {"order": order, "index": index, "responses": responses,
                                           "actor": actor, "response": response,
                                           "utterances_before": utterances_before}
                        return self._waiting_for_reaction(pending)
                result = self._settle_take(actor, response, pending, reason, choice, note)
                self.last_results[actor] = result
                self._record_speech_witnesses(actor, utterances_before)
                continue
            # Avoid actor-by-actor world scans in the common object-free
            # town. With objects present, only the actor and residents
            # close enough to witness this action need endpoint snapshots.
            before = {}
            if response.major_action is not None and self.world._physical_objects:
                actor_pos = self.world.actor_position(actor)
                witnesses = (set(self.world.actors_near(actor_pos, 1, alive_only=False,
                                                        exclude=actor))
                             if actor_pos is not None else set())
                for name in self.backends:
                    if name == actor or name in witnesses:
                        before[name] = self._visible_object_snapshot(name)
            result = self._apply_response_contained(actor, response)
            self.last_results[actor] = result
            self._record_speech_witnesses(actor, utterances_before)
            if result and before:
                after = {name: self._visible_object_snapshot(name) for name in before}
                self._record_physical_changes(actor, before, after, int(self.world._turn))
        return self._finish_turn(responses)

    def _resume_suspended(self) -> dict:
        """Continue a turn that waited for a human holder's reaction, or wait again."""
        suspended = self._suspended
        actor = suspended["actor"]
        pending = self.world.contest_pending()
        if pending is None:
            # The pending contest is gone, so the take cannot complete: it is void.
            self._suspended = None
            result = self._settle_take(actor, suspended["response"], None, "not_possible")
        else:
            choice, note = self._contest_choice(pending)
            if choice is _WAITING:
                return self._waiting_for_reaction(pending)
            self._suspended = None
            result = self._settle_take(actor, suspended["response"], pending, None, choice, note)
        self.last_results[actor] = result
        self._record_speech_witnesses(actor, suspended["utterances_before"])
        return self._apply_turn(suspended["order"], suspended["responses"], suspended["index"] + 1)

    def _finish_turn(self, responses) -> dict:
        """The end of a turn: world turn bookkeeping, event expiry, periods and continuations."""
        self.world.resolve_actor_turn()
        # Phase 053: each fogged resident (the LLM and human backends) learns the ground in sight this turn.
        from domains.map_memory import learn_all
        learn_all(self)
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

    # ---------------------------------------------------- contested take (Phase 029)
    @staticmethod
    def _is_take(response: ActorResponse) -> bool:
        return response.major_action is not None and response.major_action.action == "take"

    @staticmethod
    def _is_contest(response: ActorResponse) -> bool:
        """Phase 038: a take or a strike, each a contest that can wait for the target's reaction (Phase 033: or a restraint;
        Phase 040: or a throw at a person, whose only reaction is stepping aside)."""
        return response.major_action is not None and response.major_action.action in ("take", "strike", "restrain", "throw")

    @staticmethod
    def _is_joint(response: ActorResponse) -> bool:
        """Phase 047: a proposal to act with others, which carries a `joint` object in its params."""
        proposal = response.major_action
        return proposal is not None and proposal.action == "joint" and isinstance(proposal.params.get("joint"), dict)

    def _resolve_joint_groups(self, order, responses):
        """Resolve the turn's joint acts before its other responses (Phase 047).

        Proposals with the same task key (one carry load and step, or one crewed worker) form one act, which the world
        resolves for all of them at once. Groups are taken in sorted order, so the result does not depend on the order
        the responses were listed. A member's other parts of the response (speech, memory) still apply."""
        groups = {}
        for actor in order:
            if self._is_joint(responses[actor]):
                task = dict(responses[actor].major_action.params["joint"])
                key = (str(task.get("task")), str(task.get("object", task.get("worker", ""))),
                       repr(task.get("toward")))
                groups.setdefault(key, []).append(actor)
        for key in sorted(groups):
            members = sorted(groups[key])
            task = dict(responses[members[0]].major_action.params["joint"])
            results = self.world.enact_joint(task, members)
            for actor in members:
                applied = bool(results.get(actor, False))
                self.last_results[actor] = applied
                self._report_take_outcome(actor, applied, "joint")
                utterances_before = len(self.world._utterances)
                self._apply_response_contained(actor, replace(responses[actor], major_action=None))
                self._record_speech_witnesses(actor, utterances_before)

    def _reaction_context(self, pending) -> ActorContext:
        """The holder's reaction context: who takes, what, by hand, and the reaction options only."""
        context = self._context(pending["target"])
        offer = pending["offer"]
        context.observations["reaction"] = {
            "actor": pending["attacker"], "on": str(pending["kind"]), "by": pending.get("by", "hand"),
            "amount": float(pending["amount"]), "late": bool(offer["late"]),
            "options": list(offer["options"]),
        }
        context.affordances = [{"action": "react", "option": option} for option in offer["options"]]
        return context

    def _waiting_for_reaction(self, pending) -> dict:
        context = self._reaction_context(pending)
        return {"status": "waiting", "actor": pending["target"],
                "reaction": {"actor": pending["attacker"], "on": str(pending["kind"]),
                             "options": list(pending["offer"]["options"])},
                "context": context.observations, "affordances": context.affordances}

    def _contest_choice(self, pending):
        """The holder's reaction to a pending take: (option or None, note), or (_WAITING, note).

        None means no reaction: the holder is ineligible, its backend has no ``react`` method (noted,
        so a missing adapter shows in the log), or it declined. A reaction the offer did not name is None."""
        offer = pending["offer"]
        target = pending["target"]
        if not offer["eligible"]:
            return None, f"ineligible:{offer['reason']}"
        react = getattr(self.backends.get(target), "react", None)
        if not callable(react):
            return None, "no_react_method"
        response = react(self._reaction_context(pending))
        if response.waiting:
            return _WAITING, "waiting"
        choice = dict(response.backend_state or {}).get("reaction") or None
        if choice is None:
            return None, "declined"
        if choice not in offer["options"]:
            return None, "invalid"
        return choice, "chosen"

    def _settle_take(self, actor, response, pending, reason="", choice=None, note=""):
        """Resolve a take or strike (or record its refusal), report it to the actor, and apply the rest of the response."""
        action = response.major_action.action if response.major_action is not None else "take"
        if pending is None:
            self.world.take_outcome(actor, False, reason, action=action)
            applied = False
        else:
            applied, code = self.world.take_resolve(pending, choice)
            self.world.take_outcome(actor, applied, code, action=action)
            self._log_contest(pending, note)
            self._record_contest_witnesses(pending)
        self._report_take_outcome(actor, applied, action)
        self._apply_response_contained(actor, replace(response, major_action=None))
        return bool(applied)

    def _report_take_outcome(self, actor, applied, action="take"):
        """Give the actor's provider the take's outcome, as other major actions report theirs."""
        mind_getter = getattr(self.world, "actor_mind", None)
        mind = mind_getter(actor) if callable(mind_getter) else None
        record_outcome = getattr(mind, "record_action_outcome", None)
        if callable(record_outcome):
            record_outcome(action=action, applied=bool(applied))

    def _record_contest_witnesses(self, pending):
        """Everyone on the cell when the take was made sees its result. Nobody else is told."""
        result = pending.get("result") or {}
        turn = int(self.world._turn)
        for observer in pending["witnesses"]:
            if observer == pending["attacker"]:
                continue
            self._physical_events.setdefault(observer, []).append({
                "actor": pending["attacker"], "target": pending["target"],
                "action": "strike" if pending.get("action") == "strike" else "contest",
                "outcome": result.get("outcome", ""), "turn": turn, "expires_turn": turn})

    def _log_contest(self, pending, note):
        offer, result = pending["offer"], pending.get("result") or {}
        self.contest_log.append({
            "turn": pending["turn"], "attacker": pending["attacker"], "target": pending["target"],
            "kind": str(pending["kind"]), "amount": float(pending["amount"]),
            "eligible": bool(offer["eligible"]), "reason": offer["reason"], "late": bool(offer["late"]),
            "note": note, "reaction": result.get("reaction", ""), "outcome": result.get("outcome", ""),
            "applied": bool(result.get("applied", False)), "redirected": bool(result.get("redirected", False)),
            "attacker_cost": float(result.get("attacker_cost", 0.0)),
            "target_cost": float(result.get("target_cost", 0.0)),
        })

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
