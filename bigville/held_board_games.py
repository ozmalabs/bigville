"""Held board-game experiments.

This module deliberately does not implement a board game.  It creates a room
whose participants can observe and manipulate neutral physical objects. Any
interpretation of those objects, including Monopoly, belongs to a participant
or an external held-frame experiment.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .backends import ActorContext, DeterministicBackend, OcelotBackend
from .character import CharacterDefinition, FrameSeed, MemoryRecord
from .scenarios import ScenarioDefinition, load_scenario


@dataclass
class HeldMonopolyParticipant:
    """One participant in the physical room."""

    name: str
    identity: dict[str, Any]
    personality: dict[str, Any]
    memories: list[Any]
    held_frames: list[str]
    state: dict[str, Any]
    backend_kind: str = "cheap"
    backend: Any = None


class HeldTabletopSetup:
    """Marker for an unstarted physical tabletop scene.

    Setup is not a protocol run by the harness. Participants may perform
    setup actions through their cognition backends after observing the room.
    """

    def __init__(self, experiment, spec):
        self.experiment = experiment
        self.spec = dict(spec or {})

    def run(self, state):
        """Compatibility no-op: an authored room starts exactly as authored."""
        return None


class HeldTabletopExperiment:
    """Generic physical-tabletop setup with no game-specific rule engine.

    A caller can use this for chess, cards, miniatures, or an entirely new
    game. It creates participant-held setup state and interprets only the
    scenario's neutral setup hints; playing the resulting game is left to a
    separate held-frame implementation.
    """

    def __init__(self, participants, game_spec, *, physical_world=None):
        self.participants = list(participants)
        self._game_spec = dict(game_spec or {})
        self.physical_world = physical_world
        self._backends = {}
        names = [participant.name for participant in self.participants]
        self._state = {
            "rules": self._game_spec.get("type", "tabletop"),
            "turn": 0, "players": {name: {} for name in names},
            "setup": {"phase": "boxed", "ready": False, "opened_by": None,
                       "unpacked": [], "tokens": {}, "banker": None,
                       "dealt_money": {}, "dealt_money_value": {}, "box_object": None,
                       "rulebook": None, "rules_text": "", "rulebook_read_by": [],
                       "rules_understood_by": []},
            "game_started": False, "event_log": [], "utterances": [],
        }
        self._setup = HeldTabletopSetup(self, self._game_spec)

    @classmethod
    def from_scenario(cls, scenario, *, physical_world=None):
        definition = load_scenario(scenario)
        spec = definition.data.get("board_game", {})
        participants = [HeldMonopolyParticipant(
            name=str(actor["name"]),
            identity=dict(actor.get("identity", {}), name=str(actor["name"]),
                          role=actor.get("role", "player")),
            personality=dict(actor.get("personality", {})),
            memories=list(actor.get("memories", [])),
            held_frames=list(actor.get("held_frames", [])),
            state={}, backend_kind=str(actor.get("backend", "cheap")))
            for actor in definition.actors]
        return cls(participants, spec, physical_world=physical_world)

    @property
    def state(self):
        return self._state

    @property
    def backends(self):
        return dict(self._backends)

    def _record(self, state, kind, actor=None, **data):
        event = {"turn": state["turn"], "kind": kind, "actor": actor, **data}
        state["event_log"].append(event)
        return event

    def _say(self, state, actor, text, *, raw, target=None):
        state["utterances"].append({"speaker": actor, "target": target,
                                     "text": str(text), "raw": raw})

    def setup(self):
        for participant in self.participants:
            participant.state = copy.deepcopy(self._state)
        return self._state

    def held_state(self):
        return {participant.name: copy.deepcopy(participant.state)
                for participant in self.participants}


class _HeldMonopolyWorldAdapter:
    """World-facing adapter for the room's Ocelot cognition.

    The adapter exposes only observations, generic physical affordances, and
    provider-owned speech. It does not expose a Monopoly state machine.
    """

    def __init__(self, experiment, physical_world=None):
        self.experiment = experiment
        self.physical_world = physical_world
        self._speech_ticks = {}

    def resident_plan_from_context(self, actor, context):
        """Publish the room's observed physical choices to the Ocelot mind.

        The world provides ordinary object affordances. Ocelot chooses one;
        no tabletop interpretation is inserted into the option set.
        """
        if self.physical_world is None:
            return {"action": "observe_room"}
        mind = self.physical_world.actor_mind(actor)
        if context.observations.get("phase") == "rulebook_read":
            mind.ingest_rulebook(str(context.observations.get("rulebook_text", "")))
        # A cognition provider may maintain a resident-held rule faculty. Feed
        # it the room's ordinary physical observations before action selection;
        # the world supplies no game vocabulary, turn state, legality, or
        # outcome. Cheap/legacy minds simply do not implement this hook.
        observe = getattr(mind, "observe_situation", None)
        if callable(observe):
            cues = []
            for item in context.observations.get("physical_objects", []):
                for field in ("kind", "name"):
                    value = item.get(field)
                    if value:
                        cues.extend(str(value).lower().split())
            for option in context.affordances:
                action = option.get("action")
                if action:
                    cues.append(str(action).lower())
            observe(
                kind="room_observation",
                cues=list(dict.fromkeys(cues)),
                attributes={
                    "phase": context.observations.get("phase", ""),
                    "physical_objects": context.observations.get("physical_objects", []),
                    "affordances": context.affordances,
                },
            )
        mind.replace_options(context.affordances)
        return mind.decide()

    def ingest_document(self, actor, text, *, name="physically_read_document"):
        if self.physical_world is None:
            return None
        mind = self.physical_world.actor_mind(actor)
        provider = getattr(mind, "ingest_document", None)
        if callable(provider):
            return provider(text, name=name)
        return None

    def resident_free_text_proposal(self, speaker, context):
        """Ask Ocelot's existing goal-driven speech faculty for an utterance.

        The world supplies the possible person; Ocelot chooses whether and
        how to speak, creates the meaning, and renders the surface text in its
        private voice graph. Nothing here templates or paraphrases it.
        """
        if self.physical_world is None:
            return None
        provider = getattr(self.physical_world, "resident_speech_proposal", None)
        nearby = context.observations.get("nearby_residents", [])
        target = nearby[0].get("id") if nearby else None
        if callable(provider) and target is not None:
            return provider(speaker, target)
        mind = self.physical_world.actor_mind(speaker)
        provider = getattr(mind, "free_text_proposal", None)
        if callable(provider):
            return provider(context)
        return None

    def actor_mind(self, actor):
        if self.physical_world is None:
            return None
        return self.physical_world.actor_mind(actor)


class HeldMonopolyExperiment:
    """A room session whose participants may interpret a Monopoly box.

    The historical Monopoly ledger methods remain private compatibility code
    for callers that own a separate held frame, but this session never calls
    them.  Its public tick path contains only cognition, speech, and generic
    physical-object interaction.
    """

    def __init__(self, participants: list[HeldMonopolyParticipant], *, seed=305000,
                 max_turns=20000, physical_world=None, game_spec=None):
        if len(participants) != 4:
            raise ValueError("Monopoly scenario requires exactly four participants")
        self.participants = participants
        self.max_turns = int(max_turns)
        self.physical_world = physical_world
        self._game_spec = dict(game_spec or {})
        self._backend_world = _HeldMonopolyWorldAdapter(self, physical_world)
        self._configure_backends()
        self._setup = HeldTabletopSetup(self, self.game_spec)

    @classmethod
    def from_scenario(cls, scenario: str | dict | ScenarioDefinition, *, seed=305000,
                      backend_override=None, physical_world=None):
        definition = load_scenario(scenario)
        spec = definition.data.get("board_game", {})
        if spec.get("type") != "monopoly":
            raise ValueError("scenario does not declare a Monopoly board game")
        participants = []
        names = [str(actor.get("name")) for actor in definition.actors]
        if len(names) != 4:
            raise ValueError("Monopoly scenario must contain four actors")
        initial_state = cls._initial_state(names, spec)
        for actor in definition.actors:
            name = str(actor["name"])
            participants.append(HeldMonopolyParticipant(
                name=name,
                identity=dict(actor.get("identity", {}), name=name, role=actor.get("role", "player")),
                personality=dict(actor.get("personality", {})),
                memories=list(actor.get("memories", [])),
                held_frames=list(actor.get("held_frames", [])),
                state=copy.deepcopy(initial_state),
                backend_kind=(str(backend_override) if backend_override is not None
                              else str(actor.get("backend", "cheap"))),
            ))
        return cls(participants, seed=seed, max_turns=int(spec.get("max_turns", 20000)),
                   physical_world=physical_world, game_spec=spec)

    def _configure_backends(self):
        """Attach cognition providers without giving them ownership of rules."""
        for participant in self.participants:
            character = CharacterDefinition(
                character_id=participant.name,
                name=participant.name,
                identity=dict(participant.identity),
                personality=dict(participant.personality),
                memories=[self._memory_record(memory, participant.name, index)
                          for index, memory in enumerate(participant.memories)],
                held_frames=[FrameSeed(frame) for frame in participant.held_frames],
                backend={"kind": participant.backend_kind},
            )
            if participant.backend_kind == "ocelot":
                participant.backend = OcelotBackend(self._backend_world, character)
            elif participant.backend_kind in {"cheap", "simple"}:
                participant.backend = DeterministicBackend(character)
            else:
                raise ValueError(f"Unknown backend: {participant.backend_kind}")

    @property
    def backends(self):
        return {participant.name: participant.backend
                for participant in self.participants if participant.backend is not None}

    @staticmethod
    def _initial_state(names, spec=None):
        return {
            "rules": None,
            "turn": 0,
            "current_actor": names[0] if names else None,
            "participants": {name: {"identity": {}, "backend": None} for name in names},
            "event_log": [],
            "utterances": [],
            "finished": False,
            "winner": None,
            "termination": None,
            "room_only": True,
            "physical_objects": [],
            "setup": {
                "phase": "boxed", "ready": False, "opened_by": None,
                "unpacked": [], "tokens": {}, "banker": None,
                "dealt_money": {}, "dealt_money_value": {}, "log": [],
                "box_object": "game_box",
                "rulebook": None, "rules_text": "", "rulebook_read_by": [],
                "rules_understood_by": [],
            },
        }

    @property
    def game_spec(self):
        return getattr(self, "_game_spec", {})

    @property
    def state(self) -> dict[str, Any]:
        """Read the latest public frame held by the first participant."""
        return self.participants[0].state

    def _record(self, state, kind, actor=None, **data):
        event = {"turn": state["turn"], "kind": kind, "actor": actor, **data}
        state["event_log"].append(event)
        return event

    def _say(self, state, actor, text, *, raw, target=None):
        state["utterances"].append({"speaker": actor, "target": target,
                                     "text": text, "raw": raw})

    def _publish(self, state):
        """Publish each participant's own visible room observation."""
        if self.physical_world is not None:
            state["physical_objects"] = copy.deepcopy(self.physical_world.physical_objects())
        for participant in self.participants:
            view = dict(state)
            view["participants"] = copy.deepcopy(state["participants"])
            observer = getattr(self.physical_world, "physical_object_observations", None)
            view["physical_objects"] = copy.deepcopy(
                observer(participant.name) if callable(observer)
                else state["physical_objects"])
            view["event_log"] = list(state["event_log"])
            view["utterances"] = list(state["utterances"])
            participant.state = view

    def _backend_context(self, name, *, affordances=None, phase="turn_start",
                         rulebook_text=None):
        state = self.state
        character = next(participant for participant in self.participants
                         if participant.name == name)
        physical_objects = []
        physical_affordances = []
        if self.physical_world is not None:
            observer = getattr(self.physical_world, "physical_object_observations", None)
            physical_objects = (observer(name) if callable(observer)
                                else self.physical_world.physical_objects())
            physical_affordances = self.physical_world.physical_object_affordances(name)
        # Reading is a cognition choice over an observed physical document;
        # it is not a world fact and does not imply that anybody must read it.
        read_options = []
        mind = (self.physical_world.actor_mind(name)
                if self.physical_world is not None else None)
        already_read = getattr(mind, "has_read_document", None)
        for item in physical_objects:
            if not item.get("text"):
                continue
            doc_name = str(item.get("name", "document"))
            if callable(already_read) and already_read(item["text"], name=doc_name):
                continue
            read_options.append({"action": "read_object", "object_id": item["id"],
                                 "object": item.get("name", item["id"]),
                                 "text": item["text"], "score": 1.0})
        affordances = list(affordances or physical_affordances + read_options + [
            {"action": "observe_room", "score": 0.0},
        ])
        return ActorContext(
            CharacterDefinition(
                character_id=character.name,
                name=character.name,
                identity=dict(character.identity),
                personality=dict(character.personality),
                memories=[self._memory_record(memory, character.name, index)
                          for index, memory in enumerate(character.memories)],
                held_frames=[FrameSeed(frame) for frame in character.held_frames],
                backend={"kind": character.backend_kind},
            ),
            int(state["turn"]),
            {
                "scene": "room",
                "phase": phase,
                "nearby_residents": [{"id": other.name, "name": other.name}
                                      for other in self.participants if other.name != name],
                "recent_events": list(state["event_log"][-12:]),
                "physical_objects": physical_objects,
                "physical_object_affordances": physical_affordances,
                "text_observations": [item for item in physical_objects if item.get("text")],
            },
            affordances,
        )

    @staticmethod
    def _memory_record(memory, owner, index):
        if isinstance(memory, MemoryRecord):
            return memory
        if isinstance(memory, dict):
            data = dict(memory)
        else:
            data = {"content": memory}
        data.setdefault("memory_id", f"{owner}:memory:{index + 1}")
        return MemoryRecord(
            memory_id=str(data["memory_id"]), content=data.get("content", ""),
            kind=str(data.get("kind", "episodic")),
            source=str(data.get("source", "self")),
            confidence=float(data.get("confidence", 1.0)),
            salience=float(data.get("salience", 0.5)),
            turn=int(data.get("turn", 0)),
            private=bool(data.get("private", True)),
        )

    def _backend_decision(self, name, *, affordances=None, phase="turn_start",
                          rulebook_text=None):
        backend = self.backends.get(name)
        if backend is None:
            return {}, []
        response = backend.decide(self._backend_context(
            name, affordances=affordances, phase=phase,
            rulebook_text=rulebook_text))
        decision = {}
        if response.major_action is not None:
            decision = dict(response.major_action.params)
            decision["action"] = response.major_action.action
            self._record(self.state, "backend_decision", name,
                         backend=getattr(backend, "kind", "unknown"),
                         action=response.major_action.action, decision=copy.deepcopy(decision))
        for utterance in response.utterances:
            if hasattr(utterance, "to_dict"):
                utterance = utterance.to_dict()
            if not isinstance(utterance, dict):
                continue
            self._say(self.state, name, str(utterance.get("text", utterance.get("content", ""))),
                      raw=utterance.get("raw", utterance.get("raw_data")),
                      target=utterance.get("target"))
        return decision, response.utterances

    def _room_tick(self, name):
        """Tick one participant in the room; no tabletop rule is advanced."""
        state = self.state
        decision, _ = self._backend_decision(name, phase="room_observation")
        action = str(decision.get("action", ""))
        applied = False

        # PUBLIC MECHANICS, full information (same contract
        # domains/harvest_world.py's future_yield already documents for its
        # own commons): the actual, already-computed reach of every OTHER
        # participant's own physical_object_observations, before and after
        # this action -- e.g. opening a closed container newly reaches
        # everything inside it for everyone in the room; moving an object
        # into one's own name can remove it from others' reach. This is not
        # an invented score -- it is the same accessible-object count
        # bigville_world.py's own physical_object_observations already
        # computes, read twice.
        observer = (getattr(self.physical_world, "physical_object_observations", None)
                   if self.physical_world is not None else None)
        all_names = [participant.name for participant in self.participants]
        other_names = [n for n in all_names if n != name]
        before_others = ({n: len(observer(n)) for n in other_names}
                        if callable(observer) else {})

        if action == "move_object" and self.physical_world is not None:
            object_id = decision.get("object_id", decision.get("item"))
            destination = decision.get("destination", decision.get("target"))
            applied = bool(object_id is not None and destination is not None
                           and self.physical_world.move_physical_object_as_actor(
                               name, object_id, destination))
        elif action == "open_object" and self.physical_world is not None:
            object_id = decision.get("object_id", decision.get("item"))
            opener = getattr(self.physical_world, "open_physical_object_as_actor", None)
            applied = bool(object_id is not None and callable(opener)
                           and opener(name, object_id))
        elif action == "read_object" and self.physical_world is not None:
            object_id = self.physical_world.resolve_physical_object_id(
                decision.get("object_id", ""))
            observer = getattr(self.physical_world, "physical_object_observations", None)
            visible = (observer(name) if callable(observer)
                       else self.physical_world.physical_objects())
            item = next((item for item in visible
                         if item["id"] == object_id and item.get("text")), None)
            if item is not None:
                self.physical_world.move_physical_object_as_actor(name, object_id, name)
                self._backend_world.ingest_document(
                    name, str(item["text"]), name=str(item.get("name", "document")))
                applied = True
        # Generic outcome publication is optional and provider-owned.  The
        # room reports only whether its ordinary physical affordance was
        # enacted; a cognition backend may feed that observation into its own
        # emotional/learning graph.  No tabletop meaning is inferred here.
        # supergraph_contribution: the signed change in OTHERS' own reach
        # this action caused (excludes self by construction -- no
        # applied-specific branch, a failed action or observe_room leaves
        # every reach count unchanged and so publishes exactly 0).
        # collective_success: the room's total reach right now (ALL
        # participants, self included) -- the ledger em_fulfilment's own
        # Gt(collective_success, collective_success_prev) guard reads.
        if callable(observer):
            after_others = {n: len(observer(n)) for n in other_names}
            supergraph_contribution = sum(
                after_others.get(n, 0) - before_others.get(n, 0) for n in other_names)
            collective_success = sum(len(observer(n)) for n in all_names)
        else:
            supergraph_contribution = 0.0
            collective_success = 0.0

        mind = (self.physical_world.actor_mind(name)
                if self.physical_world is not None else None)
        record_outcome = getattr(mind, "record_action_outcome", None)
        if callable(record_outcome):
            record_outcome(action=action or "observe_room", applied=applied,
                           supergraph_contribution=float(supergraph_contribution),
                           collective_success=float(collective_success))
        self._record(state, "actor_tick", name, action=action or "observe_room",
                     applied=applied)
        names = [participant.name for participant in self.participants]
        if names:
            state["current_actor"] = names[(names.index(name) + 1) % len(names)]
        state["turn"] += 1
        self._publish(state)
        return state["event_log"][-1]

    def step(self, actor=None):
        """Advance one cognition tick in the shared room.

        This is deliberately not a Monopoly turn.  Nothing opens the box,
        chooses a token, elects a banker, deals money, rolls dice, or settles
        a transaction unless an agent proposes an observable physical action.
        """
        names = [participant.name for participant in self.participants]
        if not names:
            return None
        state = self.state
        name = str(actor or state.get("current_actor") or names[0])
        if name not in names:
            raise KeyError(name)
        return self._room_tick(name)

    def run(self, ticks=None):
        """Run room cognition ticks without assuming that anyone plays."""
        limit = self.max_turns if ticks is None else int(ticks)
        for _ in range(max(0, limit)):
            self.step()
        return self.state

    def held_state(self) -> dict[str, dict[str, Any]]:
        return {participant.name: copy.deepcopy(participant.state)
                for participant in self.participants}

    def summary(self) -> dict[str, Any]:
        state = self.state
        return {"rules": state["rules"], "ticks": state["turn"],
                "setup_ready": state["setup"]["ready"],
                "banker": state["setup"]["banker"],
                "tokens": dict(state["setup"]["tokens"]),
                "finished": False, "winner": None,
                "termination": "room_observation_only",
                "participants": [participant.name for participant in self.participants],
                "events": len(state["event_log"]),
                "utterances": len(state["utterances"])}
