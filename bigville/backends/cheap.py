"""A deterministic, inexpensive backend for standalone game NPCs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorContinuation, ActorResponse, ProposedAction
from .psi_can import CANWeightModel
from domains.persona import simple_band   # Phase 058: the hour bands are the pack's ROUTINE_BANDS

# Score added to the walk back to a paused timed job (Phase 023). A modest bias: the job
# resumes unless a need (food, rest) scores higher. It is a valuation, not a world rule.
RESUME_JOB_BONUS = 40.0


@dataclass
class NPCGoal:
    """A small durable goal record held by the simple NPC backend."""

    kind: str
    priority: float
    reason: str
    started_turn: int
    status: str = "active"


@dataclass(frozen=True)
class SimplePolicy:
    """Scenario-specific preferences applied only to published affordances."""

    rest_energy_threshold: float = 35.0
    action_bonuses: dict[str, float] = field(default_factory=dict)
    goal_priorities: dict[str, float] = field(default_factory=dict)
    hook: object | None = None
    # Moving carried goods to another resident is a social choice.  Keep it
    # opt-in so physical affordances alone do not cause unsolicited gifts.
    allow_transfers: bool = False
    # Town stock fetches are cognition choices that need a task or scenario
    # preference; publishing the physical option alone does not create desire.
    allow_stock_fetches: bool = False
    stock_fetch_kinds: tuple[str, ...] = ()
    # Moving arbitrary room objects is also a scenario-specific social choice;
    # the bounded default policy leaves newly published object actions alone.
    allow_object_moves: bool = False
    # Movement is an explicit scenario choice for actors that should remain
    # at their authored station or home while other actors navigate to them.
    allow_travel: bool = True
    # Recipe affordances stay physically published; a resident's policy may
    # still decline work that is irrelevant to its scenario task.
    allow_work: bool = True
    # Sleep (Phase 024). An awake resident whose energy (0-100, the world's read-off) is below this
    # sleeps when the spot is safe and it is night. A valuation: the seed's sleep_threshold is not set
    # anywhere in this repository.
    sleep_energy_threshold: float = 40.0
    # Below this energy a resident on a safe spot sleeps by day as well, before the body collapses
    # (collapse is at energy 5, the seed's e_collapse). A valuation, not sourced.
    collapse_guard_energy: float = 20.0
    # Escalation (Phase 050, NEW DESIGN, off by default): after this many ticks with no observed progress on its
    # own attempt, a resident raises the intensity of its next attempt by escalate_step. The world clamps the
    # result (RESOLUTION max_intensity). 0 turns escalation off, so the default intensity is always 1.0.
    escalate_after_ticks: int = 0
    escalate_step: float = 0.5

    def escalated_intensity(self, current: float, ticks_without_progress: int) -> float:
        """The intensity for the next attempt (Phase 050). Unchanged while escalation is off, or before the span
        without progress is reached; then raised by escalate_step. A separate hook: it does not decide when to act."""
        if self.escalate_after_ticks <= 0 or int(ticks_without_progress) < self.escalate_after_ticks:
            return float(current)
        return float(current) + float(self.escalate_step)

    # Phase 048 (off by default): when the right tool is missing, reach for a held tool. The choice method does not
    # call this yet, so the default policy never improvises. Only visible properties are judged: the tool's verb and
    # its condition, never the world's fitness number.
    improvise: bool = False

    def improvised_tool(self, held_tools, verb: str):
        """The kind of the held tool to use for `verb` when the right tool is missing, or None (off, or nothing held).
        Each entry of held_tools is a dict with `kind`, `verb` and `condition`. A tool whose verb is the work's verb
        scores its condition; any other scores a third of it. Ties go to the first held."""
        if not self.improvise or not held_tools:
            return None
        best, best_score = None, -1.0
        for tool in held_tools:
            score = float(tool.get("condition", 0.0)) * (1.0 if tool.get("verb") == verb else 1.0 / 3.0)
            if score > best_score:
                best, best_score = tool.get("kind"), score
        return best


# Scenario actors may name an explicitly registered backend profile. These
# profiles affect choice only; they do not add affordances or change world rules.
_SIMPLE_PROFILES: dict[str, SimplePolicy | Callable[[], SimplePolicy]] = {
    "default": SimplePolicy(),
}


def register_simple_profile(name: str, policy: SimplePolicy | Callable[[], SimplePolicy], *, replace=False):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("simple profile name must be a non-empty string")
    if not isinstance(policy, SimplePolicy) and not callable(policy):
        raise TypeError("simple profile must be a SimplePolicy or zero-argument factory")
    if name in _SIMPLE_PROFILES and not replace:
        raise ValueError(f"Simple profile already registered: {name}")
    _SIMPLE_PROFILES[name] = policy


def simple_profile_names() -> set[str]:
    return set(_SIMPLE_PROFILES)


def simple_policy_for(profile: str | None = None) -> SimplePolicy:
    name = profile or "default"
    try:
        configured = _SIMPLE_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown simple policy profile: {name}") from exc
    policy = configured() if callable(configured) and not isinstance(configured, SimplePolicy) else configured
    if not isinstance(policy, SimplePolicy):
        raise TypeError(f"Simple profile factory {name!r} did not return SimplePolicy")
    return policy


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
    understands_raw_speech = False
    requires_conversational_interface = True

    def __init__(self, character: CharacterDefinition, *, policy: SimplePolicy | None = None):
        self.character = character
        self.policy = policy or SimplePolicy()
        self.last_choice: dict = {}
        self.rest_energy_threshold = self.policy.rest_energy_threshold
        self.goals: list[NPCGoal] = []
        self.current_goal: NPCGoal | None = None
        self.last_speech_turn = -100
        self.time_band = "morning"
        self.model = CANWeightModel()

    def decide(self, context: ActorContext) -> ActorResponse:
        self._update_goals(context)
        hunger = float(context.observations.get("hunger", 0.0))
        energy = float(context.observations.get("energy", 100.0))
        known_recipes = {
            str(memory.content.get("recipe"))
            for memory in self.character.memories
            if memory.kind == "recipe_knowledge" and isinstance(memory.content, dict)
            and memory.content.get("recipe")
        }
        # Phase 027: held food that would relieve no hunger (a spoiled pile) is not a meal, so it
        # neither counts as carried food nor blocks fetching a fresh one.
        def _feeds(option):
            return "meal_value" not in option or float(option.get("meal_value", 0.0)) > 0.0
        carried_food_kinds = {
            str(option.get("kind")) for option in context.affordances
            if option.get("action") == "eat" and option.get("kind") and _feeds(option)
        }
        options = [o for o in context.affordances
                   if o.get("action") not in {"rest", "", "sleep"}
                   and (self.policy.allow_transfers or o.get("action") != "transfer")
                   and (o.get("stock_source") != "town" or
                        (self.policy.allow_stock_fetches and
                         (not self.policy.stock_fetch_kinds or
                          o.get("kind") in self.policy.stock_fetch_kinds)) or
                        (self.policy.hook is None and hunger > 0 and not carried_food_kinds
                         and bool(o.get("food"))))
                   and (self.policy.allow_travel or o.get("action") != "move")
                   and (self.policy.allow_work or o.get("action") != "work")
                   and (o.get("action") != "work" or str(o.get("recipe", "")) in known_recipes)
                   and (self.policy.allow_object_moves or o.get("action") != "move_object")
                   # A reachable pantry is only useful to this resident when
                   # they have a food goal. The world publishes the physical
                   # stock source; hunger supplies the backend's motivation.
                   and not (o.get("physical_source") == "container"
                            and o.get("action") in {"fetch", "move"} and hunger <= 0)
                   and not (o.get("physical_source") == "container"
                            and ((o.get("action") == "fetch"
                                  and str(o.get("kind", "")) in carried_food_kinds)
                                 or (o.get("action") == "move"
                                     and str(o.get("fetch_kind", "")) in carried_food_kinds)))
                   and not (o.get("action") == "eat" and (hunger <= 0 or not _feeds(o)))]
        # Professional identity guides the cheap resident's task selection.
        # These remain visible physical affordances for every cognition
        # backend; simple actors favor the tasks matching their seeded work.
        role = str(self.character.identity.get("role", "resident"))
        preferred_tasks = {
            "farmer": {"tend_animals", "water", "harvest", "sow", "fertilise"},
            "farm_labourer": {"tend_animals", "water", "harvest", "sow", "fertilise", "build", "maintain"},
            "mason": {"build", "maintain"}, "carpenter": {"build", "maintain"},
            "woodworker": {"build", "maintain"}, "labourer": {"build", "maintain"},
            "doctor": {"care"}, "midwife": {"care"},
        }
        task_actions = {"tend_animals", "water", "harvest", "sow", "fertilise", "build", "maintain", "care"}
        preferred = preferred_tasks.get(role, set())
        # Recovery must compete with ordinary work and travel. Immediate food
        # takes precedence when hungry; otherwise an exhausted body rests.
        # Sleep (Phase 024) comes first when the spot is safe and the body is low: at night, or when
        # energy is close to collapse. Otherwise a short awake rest, as before.
        sleep_reason = None
        sleep = next((o for o in context.affordances if o.get("action") == "sleep"), None)
        fed_first = hunger > 0 and any(o.get("action") == "eat" for o in options)
        if sleep is not None and not fed_first and energy < self.policy.sleep_energy_threshold and bool(sleep.get("safe")):
            if float(sleep.get("lateness", 0.0)) >= 1.0:
                sleep_reason = "sleep_at_night"
            elif energy < self.policy.collapse_guard_energy:
                sleep_reason = "sleep_before_collapse"
        if sleep_reason is not None:
            options = [sleep]
        elif energy < self.rest_energy_threshold and not fed_first:
            rest = next((o for o in context.affordances if o.get("action") == "rest"), None)
            if rest is not None:
                options = [rest]
        # Phase 030: a resident who holds the key to a locked container or the town store, and stands at it,
        # unlocks it. The world publishes an unlock only when the key fits and the resident is at the lock, so
        # this is the cheap resident's whole lock policy. Food and sleep still come first.
        unlock = next((o for o in options if o.get("action") == "unlock"), None)
        if unlock is not None and sleep_reason is None and not fed_first:
            self.last_choice = {**dict(unlock), "goal": self.current_goal.kind if self.current_goal else "observe",
                                "time_band": self.time_band, "reason": "unlock_with_key"}
            params = {k: value for k, value in unlock.items() if k not in {"action", "score", "legal", "reason"}}
            return ActorResponse(major_action=ProposedAction("unlock", params, "cheap_psi_can"),
                                 utterances=self._speech(context))
        # PSI/CAN weights the already-admissible options.  The durable goal
        # state remains useful as a modest task salience bonus, but it never
        # bypasses world legality.
        weighted_options = []
        hungry_without_food = hunger > 0 and not any(
            option.get("action") == "eat" for option in options
        )
        for option in options:
            candidate = dict(option)
            # Seeded occupation is a preference held by this cognition policy,
            # not a restriction on what bodies can physically do.
            effective_task = option.get("action")
            if effective_task == "move":
                if option.get("animal"):
                    effective_task = "tend_animals"
                elif option.get("crop_node") is not None:
                    effective_task = "harvest"
                elif option.get("sow_kind"):
                    effective_task = "sow"
                elif option.get("fertilise_land"):
                    effective_task = "fertilise"
                elif option.get("project"):
                    effective_task = "build"
                elif option.get("name"):
                    effective_task = "maintain"
                elif option.get("patient"):
                    effective_task = "care"
            role_bonus = 24.0 if effective_task in preferred else 0.0
            if effective_task in task_actions and effective_task not in preferred:
                role_bonus = -24.0
            if option.get("action") in {"fetch", "move"} and option.get("trade"):
                trade = str(option.get("trade"))
                role_bonus = (24.0 if role in {trade, "baker" if trade == "bakery" else trade}
                              else -24.0)
            # Hunger changes the resident's valuation of a physically
            # published household food source. The world only labels the
            # observed container/source and its contents; it does not decide
            # that the resident should eat or fetch. A held edible option wins
            # through the ordinary eat goal, avoiding duplicate stockpiling.
            food_response_bonus = 0.0
            if hungry_without_food and option.get("physical_source") == "container":
                if option.get("action") == "fetch" or (
                    option.get("action") == "move" and option.get("fetch_kind")
                ):
                    food_response_bonus = 100.0
            elif hungry_without_food and self.policy.hook is None and bool(option.get("food")):
                if option.get("action") in {"fetch", "move"}:
                    food_response_bonus = 100.0
            # Among held meals the one that relieves more hunger wins (Phase 027: a fresh loaf over a
            # spoiled one, a loaf over an apple). It reads the world's meal_value and never adds an eat.
            meal_bonus = (10.0 * float(option.get("meal_value", 0.0))
                          if option.get("action") == "eat" else 0.0)
            candidate["score"] = (float(candidate.get("score", 0.0))
                                   + self._goal_bonus(candidate)
                                   + (RESUME_JOB_BONUS if candidate.get("resumes_job") else 0.0)
                                   + food_response_bonus
                                   + meal_bonus
                                   + role_bonus
                                   + float(self.policy.action_bonuses.get(candidate.get("action"), 0.0))
                                   + self._hook_bonus(context, candidate)
                                   + (3.0 if candidate.get("path_preferred") else 0.0))
            weighted_options.append(candidate)
        choice = self.model.choose(context, weighted_options)
        if choice is None:
            rest = next((o for o in context.affordances
                         if o.get("action") == "rest"), None)
            energy = float(context.observations.get("energy", 100.0))
            if rest is not None and energy < self.rest_energy_threshold:
                choice = self.model.choose(context, [rest])
        if choice is None:
            # A blank response is a valid NPC observation turn.  In particular,
            # do not submit a rest plan that the world will correctly reject
            # for a healthy resident with no other legal work.
            self.last_choice = {}
            return ActorResponse(utterances=self._speech(context))
        self.last_choice = {**dict(choice), "goal": self.current_goal.kind if self.current_goal else "observe",
                            "time_band": self.time_band}
        if sleep_reason is not None:
            self.last_choice["reason"] = sleep_reason
        # Preserve the complete concrete proposal.  Room-scale scenarios may
        # expose arbitrary physical object ids and destinations; reducing a
        # choice to the village vocabulary would make the backend unable to
        # interact with them.
        params = {k: value for k, value in choice.items()
                  if k not in {"action", "score", "legal", "reason"}}
        continuation = None
        if choice.get("action") == "move" and choice.get("destination") is not None:
            # Keep walking to the physical cell without asking the cognition
            # layer to rediscover the same route on every turn.  Arrival,
            # encounters, needs thresholds, and failed movement interrupt it.
            continuation = ActorContinuation(destination=choice["destination"])
        return ActorResponse(
            major_action=ProposedAction(str(choice["action"]), params,
                            "cheap_psi_can"),
            utterances=self._speech(context),
            continuation=continuation,
        )

    def _hook_bonus(self, context, option):
        hook = self.policy.hook
        if hook is None:
            return 0.0
        return float(hook.score_adjustment(self, context, dict(option)))

    def _update_goals(self, context: ActorContext):
        observations = context.observations
        calendar = observations.get("calendar", {}) or {}
        hour = float(calendar.get("hour", 6.0))
        self.time_band = self._time_band(hour)
        hunger = float(observations.get("hunger", 0.0))
        energy = float(observations.get("energy", 100.0))
        actions = {str(option.get("action")) for option in context.affordances}
        role = str(self.character.identity.get("role", "resident"))
        preferred_tasks = {
            "farmer": {"tend_animals", "water", "harvest", "sow", "fertilise"},
            "farm_labourer": {"tend_animals", "water", "harvest", "sow", "fertilise", "build", "maintain"},
            "mason": {"build", "maintain"}, "carpenter": {"build", "maintain"},
            "woodworker": {"build", "maintain"}, "labourer": {"build", "maintain"},
            "doctor": {"care"}, "midwife": {"care"},
        }
        preferred = preferred_tasks.get(role, set())
        known_recipes = {
            str(memory.content.get("recipe"))
            for memory in self.character.memories
            if memory.kind == "recipe_knowledge" and isinstance(memory.content, dict)
            and memory.content.get("recipe")
        }
        has_known_work = self.policy.allow_work and any(
            option.get("action") == "work" and str(option.get("recipe", "")) in known_recipes
            for option in context.affordances
        )
        candidates: list[tuple[str, float, str]] = []
        if "eat" in actions and hunger > 0.25:
            candidates.append(("eat", 100.0 + hunger * 20, "hunger is rising"))
        if "rest" in actions and energy < self.rest_energy_threshold:
            candidates.append(("recover", 95.0 + (self.rest_energy_threshold - energy), "energy is low"))
        if self.time_band in {"morning", "workday"}:
            if (actions & {"tend_animals", "milk", "shear"}) and (
                "tend_animals" in preferred or "care_for_animals" in self.policy.goal_priorities
            ):
                candidates.append(("care_for_animals", 78.0, "morning care is due"))
            if (actions & {"harvest", "sow", "water", "fertilise"}) and (
                bool(preferred & {"harvest", "sow", "water", "fertilise"})
                or "tend_farm" in self.policy.goal_priorities
            ):
                candidates.append(("tend_farm", 76.0, "the farm needs attention"))
            if has_known_work or "sell_labor" in actions:
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
        candidates.sort(key=lambda item: (-float(self.policy.goal_priorities.get(item[0], 0.0)), -item[1], item[0]))
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
        """The simple backend's band for an hour. The boundaries are the pack's ROUTINE_BANDS (Phase 058)."""
        return simple_band(hour)

    def _choice_key(self, option, context):
        """Prefer actions matching the active goal, then world score."""
        priority = {
            "eat": 6, "tend_animals": 5, "harvest": 5, "sow": 4, "fertilise": 4,
            "work": 3, "give": 2, "move": 1,
        }
        action = str(option.get("action", ""))
        goal_actions = {
            "eat": {"eat"}, "recover": {"rest"}, "care_for_animals": {"tend_animals", "milk", "shear"},
            "tend_farm": {"harvest", "sow", "water", "fertilise"}, "work": {"work", "sell_labor"},
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

    def _goal_bonus(self, option):
        if self.current_goal is None:
            return 0.0
        actions = {
            "eat": {"eat"}, "recover": {"rest"},
            "care_for_animals": {"tend_animals", "milk", "shear"},
            "tend_farm": {"harvest", "sow", "water", "fertilise"},
            "work": {"work", "sell_labor"}, "travel": {"move"},
            "rest": {"rest"},
        }
        return 30.0 if option.get("action") in actions.get(self.current_goal.kind, set()) else 0.0

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

    def react(self, context: ActorContext) -> ActorResponse:
        """Phase 029: a fixed reaction to a contested take. Resist when offered, else brace, else yield.
        Deterministic: the same offer always gets the same reaction."""
        offer = context.observations.get("reaction", {})
        options = list(offer.get("options", []))
        choice = next((option for option in ("resist", "brace", "yield") if option in options), "")
        return ActorResponse(backend_state={"reaction": choice, "reason": "fixed_reaction_policy"})

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
                "understands_raw_speech": self.understands_raw_speech,
                "requires_conversational_interface": self.requires_conversational_interface,
            }, "time_band": self.time_band,
                      "last_speech_turn": self.last_speech_turn,
                      "decision_model": "psi_can_weighted"},
        )


# Compatibility name used by the first standalone API release.
CheapBackend = DeterministicBackend
