"""A deterministic, inexpensive backend for standalone game NPCs."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorContinuation, ActorResponse, ProposedAction


@dataclass
class NPCGoal:
    """A small durable goal record held by the simple NPC backend."""

    kind: str
    priority: float
    reason: str
    started_turn: int
    status: str = "active"


class DeterministicBackend:
    """A small NPC policy over the world's already-derived affordances.

    The world still owns all of the detailed rules. This backend does the
    inexpensive game-AI part: maintain a few needs-driven goals, interpret the
    current time of day, prefer the highest-scoring legal affordance for the
    active goal, and occasionally speak to a nearby person. It never schedules
    work behind the world's action boundary.
    """
    kind = "cheap"
    communication_mode = "templated"
    supports_free_text = False
    requires_conversational_interface = True

    def __init__(self, character: CharacterDefinition):
        self.character = character
        self.last_choice: dict = {}
        self.rest_energy_threshold = 35.0
        self.goals: list[NPCGoal] = []
        self.current_goal: NPCGoal | None = None
        self.last_speech_turn = -100
        self.time_band = "morning"

    def decide(self, context: ActorContext) -> ActorResponse:
        self._update_goals(context)
        options = [o for o in context.affordances
                   if o.get("action") not in {"rest", ""}]
        choice = max(options, key=lambda option: self._choice_key(option, context), default=None)
        if choice is None:
            rest = next((o for o in context.affordances
                         if o.get("action") == "rest"), None)
            energy = float(context.observations.get("energy", 100.0))
            if rest is not None and energy < self.rest_energy_threshold:
                choice = rest
        if choice is None:
            # A blank response is a valid NPC observation turn.  In particular,
            # do not submit a rest plan that the world will correctly reject
            # for a healthy resident with no other legal work.
            self.last_choice = {}
            return ActorResponse(utterances=self._speech(context))
        self.last_choice = {**dict(choice), "goal": self.current_goal.kind if self.current_goal else "observe",
                            "time_band": self.time_band}
        params = {k: choice[k] for k in ("kind", "trade", "recipe", "target") if k in choice}
        continuation = None
        if choice.get("action") == "move" and choice.get("destination") is not None:
            # Keep walking to the physical cell without asking the cognition
            # layer to rediscover the same route on every turn.  Arrival,
            # encounters, needs thresholds, and failed movement interrupt it.
            continuation = ActorContinuation(destination=choice["destination"])
        return ActorResponse(
            major_action=ProposedAction(str(choice["action"]), params,
                                        f"npc_goal:{self.current_goal.kind if self.current_goal else 'observe'}"),
            utterances=self._speech(context),
            continuation=continuation,
        )

    def _update_goals(self, context: ActorContext):
        observations = context.observations
        calendar = observations.get("calendar", {}) or {}
        hour = float(calendar.get("hour", 6.0))
        self.time_band = self._time_band(hour)
        hunger = float(observations.get("hunger", 0.0))
        energy = float(observations.get("energy", 100.0))
        actions = {str(option.get("action")) for option in context.affordances}
        candidates: list[tuple[str, float, str]] = []
        if "eat" in actions and hunger > 0.25:
            candidates.append(("eat", 100.0 + hunger * 20, "hunger is rising"))
        if "rest" in actions and energy < self.rest_energy_threshold:
            candidates.append(("recover", 95.0 + (self.rest_energy_threshold - energy), "energy is low"))
        if self.time_band in {"morning", "workday"}:
            if actions & {"tend_animals", "milk", "shear"}:
                candidates.append(("care_for_animals", 78.0, "morning care is due"))
            if actions & {"harvest", "sow", "water"}:
                candidates.append(("tend_farm", 76.0, "the farm needs attention"))
            if "work" in actions or "sell_labor" in actions:
                candidates.append(("work", 64.0, "the workday is open"))
        elif self.time_band == "evening":
            candidates.append(("socialize", 48.0, "the workday is ending"))
        else:
            candidates.append(("rest", 60.0, "it is late"))
        if "move" in actions:
            candidates.append(("travel", 25.0, "a nearby task is elsewhere"))
        if not candidates:
            candidates.append(("observe", 5.0, "no urgent affordance is available"))
        candidates.sort(key=lambda item: (-item[1], item[0]))
        kind, priority, reason = candidates[0]
        if self.current_goal is None or self.current_goal.kind != kind:
            self.current_goal = NPCGoal(kind, priority, reason, context.turn)
        else:
            self.current_goal.priority = priority
            self.current_goal.reason = reason
            self.current_goal.status = "active"
        self.goals = [self.current_goal] + [
            NPCGoal(name, score, why, context.turn, status="queued")
            for name, score, why in candidates[1:4]
        ]

    @staticmethod
    def _time_band(hour: float) -> str:
        if hour < 9:
            return "morning"
        if hour < 17:
            return "workday"
        if hour < 21:
            return "evening"
        return "night"

    def _choice_key(self, option, context):
        """Prefer actions matching the active goal, then world score."""
        priority = {
            "eat": 6, "tend_animals": 5, "harvest": 5, "sow": 4,
            "work": 3, "give": 2, "move": 1,
        }
        action = str(option.get("action", ""))
        goal_actions = {
            "eat": {"eat"}, "recover": {"rest"}, "care_for_animals": {"tend_animals", "milk", "shear"},
            "tend_farm": {"harvest", "sow", "water"}, "work": {"work", "sell_labor"},
            "travel": {"move"}, "rest": {"rest"}, "socialize": {"move"}, "observe": set(),
        }
        goal_bonus = 30 if self.current_goal and action in goal_actions.get(self.current_goal.kind, set()) else 0
        # Path preference is a seeded resident concept surfaced by the world as an affordance
        # read-off.  It only nudges movement choices; it cannot outrank urgent eating, care, or
        # work goals, but it wins between otherwise comparable routes.
        path_bonus = 3.0 if action == "move" and bool(option.get("path_preferred")) else 0.0
        return (float(option.get("score", 0.0)) + path_bonus,
                goal_bonus,
                priority.get(str(option.get("action", "")), 0),
                str(option.get("target", "")),
                str(option.get("kind", "")))

    def _speech(self, context: ActorContext) -> list[dict]:
        """Choose occasional structured speech to a person in the observation."""
        nearby = context.observations.get("nearby_residents", []) or []
        if not nearby or context.turn - self.last_speech_turn < 5:
            return []
        # A stable per-character offset gives different villagers different
        # conversational rhythms without introducing a hidden scheduler.
        offset = sum(ord(char) for char in self.character.character_id) % 11
        if (context.turn + offset) % 11 != 0:
            return []
        target = nearby[0]
        role = self.character.identity.get("role", "resident")
        if self.time_band == "morning":
            act, slots = "greeting", {"target": target["name"]}
        elif self.current_goal and self.current_goal.kind in {"care_for_animals", "tend_farm", "work"}:
            act, slots = "share", {"news": f"{role} work is underway"}
        elif self.time_band == "evening":
            act, slots = "question", {"question": "how was your day"}
        else:
            act, slots = "inform", {"content": f"the weather is {context.observations.get('calendar', {}).get('weather', 'clear')}"}
        self.last_speech_turn = context.turn
        return [{"target": target["id"], "act": act, "slots": slots, "content": ""}]

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            goals=[asdict(goal) for goal in self.goals],
            decision=dict(self.last_choice),
            backend_state={"communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }, "time_band": self.time_band,
                      "last_speech_turn": self.last_speech_turn},
        )


# Compatibility name used by the first standalone API release.
CheapBackend = DeterministicBackend
