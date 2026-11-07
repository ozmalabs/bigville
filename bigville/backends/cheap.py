"""A deterministic, inexpensive backend for standalone game NPCs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorContinuation, ActorResponse, ProposedAction
from .lamplighter import lamplighter_choice  # Phase 042: the lamplighter's round
from .psi_can import CANWeightModel
from domains.persona import simple_band   # Phase 058: the hour bands are the pack's ROUTINE_BANDS
from domains.world_affordances import INTOXICATION as _INTOXICATION   # Phase 034: the drink policy numbers
from domains.world_affordances import alcohol as _alcohol_grams   # Phase 036: grams of alcohol in a food (coping drink)
from domains.world_affordances import CONTEST as _CONTEST   # Phase 038: attack_cost, the strike gate

# Score added to the walk back to a paused timed job (Phase 023). A modest bias: the job
# resumes unless a need (food, rest) scores higher. It is a valuation, not a world rule.
RESUME_JOB_BONUS = 40.0

# Hunger at which a resident goes for food before sleeping or resting (fix024). It is on the world's hunger scale, where
# 1.0 is one unmet meal of one loaf, so a resident one meal short tends to eat before it sleeps. A valuation, not a rule.
HUNGER_BEFORE_SLEEP = 1.0


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
    # Strikes (Phase 038, OFF by default, so the simple village stays peaceful). The seeded trigger
    # (bigville_viol_act bv_trigger) as a valuation: a resident strikes a person on its cell it holds a grievance
    # against when snap_pressure + w_spite x spite_gain + hunger x desperation_gain reaches strike_threshold, and
    # only with stamina at least attack_cost (the seed's gate). snap_pressure is 0 (no frustration model here), and
    # spite_gain is 1 for a grievance (a contest this resident reacted to). Both gains and the threshold are APPROX.
    strike_trigger: bool = False
    strike_threshold: float = 1.0
    strike_desperation_gain: float = 1.0

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

    # Phase 036 (off by default): a coping drink. A drink option (eat, with a food that holds alcohol) gets
    # coping_bonus while the resident's mood is below distress_below or its craving is at withdrawal_above (the
    # world's read-offs in the observations `aftereffects`, which exist only with alcohol_aftereffects on). The numbers
    # are the INTOXICATION policy; the world is unchanged by the choice.
    coping_drink: bool = False

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
        # Phase 034: the last few intoxication bonuses given (the reason trace of a drunk resident's choices)
        self.intoxication_trace: list[dict] = []
        # Phase 038: residents this backend has reacted to in a contest (a grievance, for the optional strike trigger).
        self.grievances: dict[str, int] = {}

    def decide(self, context: ActorContext) -> ActorResponse:
        # LA04: in lazy mode the world publishes entities, not a legal menu.
        # Build a bounded local candidate list and reuse every later stage
        # (goals, valuation, selection, continuation) unchanged.
        lazy_candidates = False
        entities = context.observations.get("entities")
        if not context.affordances and isinstance(entities, dict):
            lazy_candidates = True
            # The valuation model reads the body and calendar from the
            # context root.  A lazy context carries them under `entities`;
            # copy the missing aliases without replacing anything menu mode
            # already publishes.
            for key in ("hunger", "energy", "health", "illness", "calendar",
                        "intoxication", "position", "terrain", "terrain_movement",
                        "inventory", "held_items", "worn", "job", "known_recipes",
                        "nearby_actors", "last_outcome", "heard"):
                if key not in context.observations and key in entities:
                    context.observations[key] = entities[key]
            candidates = self._lazy_candidates(context)
            refused = self._refused_signature(context)
            if refused is not None:
                candidates = [candidate for candidate in candidates
                              if self._proposal_signature(candidate) != refused]
            context.affordances = candidates
        self._update_goals(context)
        lamp = lamplighter_choice(context)   # Phase 042: a lamplighter's round (offered to a lamplighter only)
        if lamp is not None:
            action, params, continuation = lamp
            self.last_choice = {"action": action, "goal": "lamplighter", "time_band": self.time_band,
                                "reason": "lamplighter"}
            return ActorResponse(major_action=ProposedAction(action, params, "cheap_psi_can"),
                                 continuation=continuation)
        # Phase 033: a held resident's one way out is a struggle, so it struggles before anything else. The
        # cheap policy never restrains anyone, and it does not choose release (no release policy yet).
        if any(option.get("action") == "struggle" for option in context.affordances):
            self.last_choice = {"action": "struggle", "goal": self.current_goal.kind if self.current_goal else "observe",
                                "time_band": self.time_band, "reason": "held_struggle"}
            return ActorResponse(major_action=ProposedAction("struggle", {}, "cheap_psi_can"),
                                 utterances=self._speech(context))
        hunger = float(context.observations.get("hunger", 0.0))
        energy = float(context.observations.get("energy", 100.0))
        known_recipes = {
            str(memory.content.get("recipe"))
            for memory in self.character.memories
            if memory.kind == "recipe_knowledge" and isinstance(memory.content, dict)
            and memory.content.get("recipe")
        }
        # LA04: the observation's broad recipe knowledge supplements the
        # backend's private recipe memories in lazy mode only (menu contexts
        # have no `entities` key).
        if isinstance(context.observations.get("entities"), dict):
            known_recipes.update(
                str(name) for name in
                context.observations["entities"].get("known_recipes", []))
        # Phase 027: held food that would relieve no hunger (a spoiled pile) is not a meal, so it
        # neither counts as carried food nor blocks fetching a fresh one.
        def _feeds(option):
            return "meal_value" not in option or float(option.get("meal_value", 0.0)) > 0.0
        carried_food_kinds = {
            str(option.get("kind")) for option in context.affordances
            if option.get("action") == "eat" and option.get("kind") and _feeds(option)
        }
        options = [o for o in context.affordances
                   if o.get("action") not in {"rest", "", "sleep", "joint", "release"}
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
        # fix024: a resident at HUNGER_BEFORE_SLEEP with a food fetch in reach counts as fed first, so it goes for food
        # before it sleeps. The awake rest is not held back by food in reach (see held_meal_first below).
        food_in_reach = hunger >= HUNGER_BEFORE_SLEEP and any(
            o.get("action") in {"fetch", "move"}
            and (o.get("food") or o.get("fetch_kind") or o.get("physical_source") == "container")
            for o in options)
        held_meal_first = fed_first
        fed_first = fed_first or food_in_reach
        if sleep is not None and not fed_first and energy < self.policy.sleep_energy_threshold and bool(sleep.get("safe")):
            if float(sleep.get("lateness", 0.0)) >= 1.0:
                sleep_reason = "sleep_at_night"
            elif energy < self.policy.collapse_guard_energy:
                sleep_reason = "sleep_before_collapse"
        if sleep_reason is not None:
            options = [sleep]
        elif energy < self.rest_energy_threshold and not held_meal_first:
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
        # Phase 047: a joint option the people present can complete (`present` counts the others who can join now).
        # The rule reads only the published option, so each resident who sees the same option proposes the same act.
        joint = self._joint_proposal(context) if sleep_reason is None and not fed_first else None
        if joint is not None:
            self.last_choice = {"action": "joint", **joint, "goal": self.current_goal.kind if self.current_goal else "observe",
                                "time_band": self.time_band, "reason": "joint_present"}
            return ActorResponse(major_action=ProposedAction("joint", {"joint": joint}, "cheap_psi_can"),
                                 utterances=self._speech(context))
        # Phase 038: the optional strike trigger (off by default). Sleep and food still come first only through the
        # sleep block above; a resident that is asleep does not strike.
        strike = self._strike_proposal(context) if sleep_reason is None else None
        if strike is not None:
            self.last_choice = {"action": "strike", **strike, "goal": self.current_goal.kind if self.current_goal else "observe",
                                "time_band": self.time_band, "reason": "grievance_trigger"}
            return ActorResponse(major_action=ProposedAction("strike", dict(strike), "cheap_psi_can"),
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
        # LA04: a refusal is ordinary feedback.  If the chosen local proposal
        # repeats the previous refused proposal, or nothing scores, make a
        # fresh, safer proposal.  The world still validates it.
        if lazy_candidates and choice is not None and self._is_refused(context, choice):
            choice = None
        if lazy_candidates and choice is None:
            choice = self._refusal_fallback(context)
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
            # fix_simple_village: body_down ends the walk when the resident falls asleep, collapses or passes out.
            continuation = ActorContinuation(destination=choice["destination"],
                                             interrupt_on=ActorContinuation.interrupt_on + ("body_down",))
        return ActorResponse(
            major_action=ProposedAction(str(choice["action"]), params,
                            "cheap_psi_can"),
            utterances=self._speech(context),
            continuation=continuation,
        )

    # LA04: candidate bounds and the direct proposal keys used to recognise a
    # refused proposal.  Scores, labels and trace fields are not part of the
    # physical proposal.
    _LAZY_MAX_CANDIDATES = 64
    _LAZY_PRIORITY_ACTIONS = {"eat", "rest", "sleep", "struggle", "release"}
    _PROPOSAL_PARAM_KEYS = (
        "kind", "recipe", "target", "destination", "recipient", "container",
        "source", "object_id", "crop_node", "animal", "land", "sow_kind",
        "project", "name", "patient", "care_kind", "intensity", "amount",
    )

    def _lazy_candidates(self, context: ActorContext) -> list[dict]:
        """Menu-shaped proposals from needs and the local observation (LA04).

        The world still validates every proposal.  This method only reads the
        LA03 observation (`context.observations["entities"]`) and returns a
        bounded, deterministic, plain-dict list with direct params accepted by
        ``BigvilleWorld._enact_plan``.  No exhaustive menu is consulted.
        """
        entities = context.observations.get("entities")
        if not isinstance(entities, dict):
            return []
        observations = context.observations
        position = entities.get("position")
        if isinstance(position, (list, tuple)) and len(position) == 2:
            position = (int(position[0]), int(position[1]))
        else:
            position = None
        cell = entities.get("cell") or {}
        hunger = float(observations.get("hunger", entities.get("hunger", 0.0)) or 0.0)
        energy_value = observations.get("energy", entities.get("energy", 100.0))
        try:
            energy = float(energy_value)
        except (TypeError, ValueError):
            energy = 100.0
        calendar = observations.get("calendar", entities.get("calendar", {})) or {}
        try:
            hour = float(calendar.get("hour", 6.0))
        except (TypeError, ValueError):
            hour = 6.0
        night = self._time_band(hour) == "night"
        inventory = list(entities.get("inventory_details") or [])
        inventory.sort(key=lambda detail: str(detail.get("kind", "")))
        nearby = list(entities.get("nearby_actors") or [])
        nearby.sort(key=lambda actor: str(actor.get("id", "")))
        candidates: list[dict] = []

        def add(action, **params):
            option = {
                "action": action,
                "kind": params.pop("kind", ""),
                "trade": "",
                "recipe": params.pop("recipe", ""),
                "target": params.pop("target", ""),
                "score": 0.0,
            }
            option.update(params)
            candidates.append(option)

        # --- needs: a carried meal, rest, and sleep -------------------------
        for detail in inventory:
            kind = str(detail.get("kind", ""))
            if not kind or not detail.get("edible"):
                continue
            if hunger > 0.0:
                add("eat", kind=kind, target=f"item:{kind}",
                    meal_value=float(detail.get("meal_value", 0.0) or 0.0))
        if energy < self.policy.rest_energy_threshold:
            add("rest")
        # Sleep is proposed only at night or near collapse.  The world decides
        # whether the spot is actually safe; a refusal is ordinary feedback.
        if (energy < self.policy.sleep_energy_threshold
                and (night or energy < self.policy.collapse_guard_energy)):
            add("sleep", safe=True, lateness=1.0 if night else 0.0)

        # --- movement: named places, adjacent exits, nearby actors ----------
        seen_cells = set()
        if position is not None:
            seen_cells.add(position)

        def add_move(cell_value, label):
            if not isinstance(cell_value, (list, tuple)) or len(cell_value) != 2:
                return
            try:
                destination = (int(cell_value[0]), int(cell_value[1]))
            except (TypeError, ValueError):
                return
            if destination in seen_cells:
                return
            seen_cells.add(destination)
            add("move", destination=destination, target=label)

        places = entities.get("places") or {}
        for kind in ("home", "work", "market"):
            add_move(places.get(kind), f"place:{kind}")
        for building in places.get("buildings") or []:
            add_move(building.get("cell"), f"building:{building.get('id', '')}")
        for site in places.get("gathering_sites") or []:
            add_move(site.get("cell"), f"gathering:{site.get('kind', '')}")
        for farm in places.get("farms") or []:
            add_move(farm.get("cell"), f"farm:{farm.get('id', '')}")
        exits = sorted(
            (int(item[0]), int(item[1]))
            for item in (cell.get("exits") or [])
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        for exit_cell in exits:
            add_move(exit_cell, f"cell:{exit_cell[0]},{exit_cell[1]}")
        for actor in nearby:
            try:
                distance = float(actor.get("distance"))
            except (TypeError, ValueError):
                continue
            if distance <= 0.0:
                continue
            add_move(actor.get("position"), f"actor:{actor.get('id', '')}")

        # --- work: the world's read-only prefilter (LA07) --------------------
        # The observation publishes only recipes whose site/tool/ingredient
        # preview is ok.  This replaces the old guess at local buildings and
        # common recipes; the world still validates the proposal.
        if not entities.get("busy"):
            for entry in entities.get("work_candidates") or []:
                name = str(entry.get("recipe") or "")
                if not name:
                    continue
                output = str(entry.get("out") or "")
                add("work", recipe=name, kind=output, intensity=1.0,
                    target=f"recipe:{name}")

        # --- containers: fetch contents and put carried kinds ---------------
        containers = sorted(
            (item for item in (entities.get("containers_in_reach") or [])
             if item.get("world_container") and item.get("open")
             and not item.get("locked")),
            key=lambda item: str(item.get("id", "")))
        fetched = 0
        for container in containers:
            container_id = str(container.get("id", ""))
            if not container_id:
                continue
            contents = sorted(container.get("contents") or [],
                              key=lambda child: str(child.get("kind", "")))
            for child in contents:
                kind = str(child.get("kind", ""))
                if not kind:
                    continue
                add("fetch", kind=kind, source=container_id,
                    physical_source="container",
                    target=f"container:{container_id}")
                fetched += 1
                if fetched >= 8:
                    break
            if fetched >= 8:
                break
        for container in containers:
            container_id = str(container.get("id", ""))
            if not container_id:
                continue
            for detail in inventory:
                kind = str(detail.get("kind", ""))
                if kind:
                    add("put", kind=kind, container=container_id,
                        target=f"container:{container_id}")

        # --- social: give/transfer to a co-located actor --------------------
        for actor in nearby:
            try:
                distance = float(actor.get("distance"))
            except (TypeError, ValueError):
                continue
            if distance != 0.0:
                continue
            recipient = str(actor.get("id", ""))
            if not recipient:
                continue
            for detail in inventory:
                kind = str(detail.get("kind", ""))
                if not kind:
                    continue
                add("give", recipient=recipient, kind=kind, amount=1.0,
                    target=f"actor:{recipient}")
                if self.policy.allow_transfers:
                    add("transfer", recipient=recipient, kind=kind, amount=1.0,
                        target=f"actor:{recipient}")

        # --- objects: move a visible grabbable object to a local destination
        if self.policy.allow_object_moves:
            destinations = []
            self_id = str(entities.get("actor")
                          or getattr(self.character, "character_id", ""))
            nearby_destinations = []
            for actor in nearby:
                try:
                    distance = float(actor.get("distance"))
                except (TypeError, ValueError):
                    continue
                if distance <= 1.0:
                    nearby_destinations.append(str(actor.get("id", "")))
            container_destinations = [str(item.get("id", ""))
                                      for item in containers]
            for value in ([self_id] + nearby_destinations
                          + container_destinations + ["table", "world"]):
                if value and value not in destinations:
                    destinations.append(value)
            objects = sorted(
                (item for item in (entities.get("visible_objects") or [])
                 if item.get("grabbable")),
                key=lambda item: str(item.get("id", "")))
            for item in objects:
                object_id = str(item.get("id", ""))
                source = str(item.get("location", ""))
                if not object_id:
                    continue
                for destination in destinations:
                    if destination == source:
                        continue
                    add("move_object", object_id=object_id,
                        destination=destination, kind=str(item.get("kind", "")),
                        target=f"object:{object_id}")

        # --- local cell work: animals, crops, land, projects, infrastructure
        for animal in sorted(cell.get("animals") or [],
                             key=lambda item: str(item.get("id", ""))):
            if not animal.get("alive", True):
                continue
            animal_id = str(animal.get("id", ""))
            if animal_id:
                add("tend_animals", animal=animal_id,
                    kind=str(animal.get("task") or "tend"),
                    target=f"animal:{animal_id}")
        for crop in sorted(cell.get("crops") or [],
                           key=lambda item: int(item.get("id", 0))):
            crop_id = crop.get("id")
            if crop_id is None:
                continue
            if float(crop.get("thirst", 0.0) or 0.0) > 0.0:
                add("water", crop_node=int(crop_id), target=f"crop:{crop_id}")
            if crop.get("mature"):
                add("harvest", crop_node=int(crop_id), target=f"crop:{crop_id}")
        for land in sorted(cell.get("land") or [],
                           key=lambda item: str(item.get("id", ""))):
            land_id = str(land.get("id", ""))
            if not land_id:
                continue
            sow_kind = land.get("sow_kind")
            if sow_kind:
                add("sow", sow_kind=str(sow_kind), land=land_id, target=land_id)
            add("fertilise", target=land_id, land=land_id,
                fertilise_land=land_id)
        for project in sorted(cell.get("building_projects") or [],
                              key=lambda item: str(item.get("id", ""))):
            if project.get("status") == "complete":
                continue
            project_id = str(project.get("id", ""))
            if project_id:
                add("build", project=project_id,
                    recipe=str(project.get("project", "")),
                    target=f"project:{project_id}")
        for infrastructure in sorted(cell.get("infrastructure") or [],
                                     key=lambda item: str(item.get("id", ""))):
            if float(infrastructure.get("condition", 1.0) or 0.0) >= 0.8:
                continue
            name = str(infrastructure.get("id", ""))
            if name:
                add("maintain", name=name, target=f"infrastructure:{name}")
        for actor in nearby:
            try:
                distance = float(actor.get("distance"))
            except (TypeError, ValueError):
                continue
            if distance != 0.0:
                continue
            if (str(actor.get("health", "healthy")) != "healthy"
                    or float(actor.get("injury", 0.0) or 0.0) > 0.0):
                patient = str(actor.get("id", ""))
                if patient:
                    add("care", patient=patient, target=f"actor:{patient}")

        # --- restraint ------------------------------------------------------
        if entities.get("held"):
            add("struggle")
        if entities.get("holding"):
            add("release")

        candidates.sort(key=self._candidate_sort_key)
        if len(candidates) > self._LAZY_MAX_CANDIDATES:
            priority = [item for item in candidates
                        if item.get("action") in self._LAZY_PRIORITY_ACTIONS]
            others = [item for item in candidates
                      if item.get("action") not in self._LAZY_PRIORITY_ACTIONS]
            candidates = (priority + others)[:self._LAZY_MAX_CANDIDATES]
        return candidates

    @staticmethod
    def _candidate_sort_key(option):
        """A stable order for repeated candidate lists."""
        extra = sorted((str(key), repr(value)) for key, value in option.items()
                       if key not in {"action", "target", "kind", "recipe"})
        return (str(option.get("action", "")),
                str(option.get("target", "")),
                str(option.get("kind", "")),
                str(option.get("recipe", "")),
                tuple(extra))

    def _proposal_signature(self, option):
        """The physical action/params of a proposal, ignoring scores and labels."""
        if not isinstance(option, dict):
            return None
        values = []
        for key in self._PROPOSAL_PARAM_KEYS:
            if key not in option or option[key] is None:
                continue
            value = option[key]
            if isinstance(value, list):
                value = tuple(value)
            values.append((key, value))
        return (str(option.get("action", "")), tuple(sorted(values,
                                                           key=lambda item: item[0])))

    def _refused_signature(self, context):
        """The signature of this backend's previous refused proposal, if any."""
        observations = context.observations or {}
        entities = observations.get("entities")
        outcome = observations.get("last_outcome")
        if not isinstance(outcome, dict) and isinstance(entities, dict):
            outcome = entities.get("last_outcome")
        if not isinstance(outcome, dict) or outcome.get("applied", True):
            return None
        action = str(outcome.get("action", ""))
        if not action:
            return None
        previous = self.last_choice
        if isinstance(previous, dict) and str(previous.get("action", "")) == action:
            return self._proposal_signature(previous)
        # Without a retained parameter set only a parameterless repeat can be
        # recognised as the exact same proposal.
        return (action, ())

    def _is_refused(self, context, option):
        refused = self._refused_signature(context)
        return refused is not None and self._proposal_signature(option) == refused

    def _refusal_fallback(self, context):
        """A fresh safe proposal after a refusal, or when nothing scores (LA04)."""
        observations = context.observations or {}
        entities = observations.get("entities")
        entities = entities if isinstance(entities, dict) else {}
        energy = float(observations.get("energy", entities.get("energy", 100.0)) or 0.0)
        refused = self._refused_signature(context)
        rest = {"action": "rest", "kind": "", "trade": "", "recipe": "",
                "target": "", "score": 0.0}
        if energy < self.rest_energy_threshold and self._proposal_signature(rest) != refused:
            return rest
        exits = sorted(
            (int(item[0]), int(item[1]))
            for item in ((entities.get("cell") or {}).get("exits") or [])
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        for exit_cell in exits:
            candidate = {
                "action": "move", "kind": "", "trade": "", "recipe": "",
                "target": f"cell:{exit_cell[0]},{exit_cell[1]}",
                "destination": exit_cell, "score": 0.0,
            }
            if self._proposal_signature(candidate) != refused:
                return candidate
        return None

    def _hook_bonus(self, context, option):
        hook = self.policy.hook
        bonus = self._intoxication_bonus(context, option) + self._coping_bonus(context, option)
        if hook is None:
            return bonus
        return float(hook.score_adjustment(self, context, dict(option))) + bonus

    def _coping_bonus(self, context, option):
        """Phase 036: the optional coping drink (SimplePolicy.coping_drink, off by default). A drink option gets
        coping_bonus when the resident is in distress: mood below distress_below, or craving at withdrawal_above. The
        read-offs are the observations `aftereffects` (present only with alcohol_aftereffects on), so with the switch
        off this adds nothing. A resident already drunk (at drunk or above) does not take another drink for coping."""
        if not self.policy.coping_drink or str(option.get("action", "")) != "eat":
            return 0.0
        if float(_alcohol_grams(str(option.get("kind", "")))) <= 0.0:
            return 0.0
        state = context.observations.get("aftereffects") or {}
        if not state or float(context.observations.get("intoxication", 0.0) or 0.0) >= float(_INTOXICATION["bands"]["drunk"]):
            return 0.0
        distressed = (float(state.get("mood", 1.0)) < float(_INTOXICATION["distress_below"])
                      or float(state.get("craving", 0.0)) >= float(_INTOXICATION["withdrawal_above"]))
        return float(_INTOXICATION["coping_bonus"]) if distressed else 0.0

    def _intoxication_bonus(self, context, option):
        """Phase 034: a resident at drunk or above leans toward social options and away from effortful work. The
        numbers are the INTOXICATION policy (social_bonus, effortful_penalty), and the level is the body read-off
        `intoxication` in the observations. Each bonus given is kept in `intoxication_trace`, the reason trace. A
        sober or tipsy resident gets none, and the world's physics is unchanged."""
        level = float(context.observations.get("intoxication", 0.0) or 0.0)
        if level < float(_INTOXICATION["bands"]["drunk"]):
            return 0.0
        action = str(option.get("action", ""))
        social = action in _INTOXICATION["social_actions"] or any(
            option.get(key) for key in _INTOXICATION["social_keys"])
        effortful = action in _INTOXICATION["effortful_actions"] and not social
        if social:
            bonus = float(_INTOXICATION["social_bonus"])
        elif effortful:
            bonus = -float(_INTOXICATION["effortful_penalty"])
        else:
            return 0.0
        self.intoxication_trace.append({"action": action, "target": str(option.get("target", "")),
                                        "bonus": bonus, "intoxication": level})
        del self.intoxication_trace[:-20]
        return bonus

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
        if isinstance(observations.get("entities"), dict):
            known_recipes.update(
                str(name) for name in
                observations["entities"].get("known_recipes", []))
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
        Deterministic: the same offer always gets the same reaction. Phase 038: the contest's actor is recorded as a
        grievance (the strike trigger reads it), whatever the reaction."""
        offer = context.observations.get("reaction", {})
        if offer.get("actor"):
            self.grievances[str(offer["actor"])] = int(context.turn)
        options = list(offer.get("options", []))
        choice = next((option for option in ("resist", "brace", "yield") if option in options), "")
        return ActorResponse(backend_state={"reaction": choice, "reason": "fixed_reaction_policy"})

    def _joint_proposal(self, context: ActorContext) -> dict | None:
        """The `joint` object for the first published joint option this resident can complete, or None (Phase 047).

        A carry needs `needs` people in all, counting this one, so the option is taken when `present` plus one reaches
        it, along the first step the world listed (the same for everyone who sees it). A crew needs `needs` more workers
        at the site, so it is taken on the same count. Options come in the world's order, so the choice is deterministic."""
        for option in context.affordances:
            if option.get("action") != "joint":
                continue
            needs, present = int(option.get("needs", 0)), int(option.get("present", 0))
            if option.get("task") == "carry" and option.get("toward") and present + 1 >= needs:
                return {"task": "carry", "object": str(option["object"]), "toward": list(option["toward"][0])}
            if option.get("task") == "crew" and needs >= 1 and present + 1 >= needs:
                return {"task": "crew", "worker": str(option["worker"])}
        return None

    def _strike_proposal(self, context: ActorContext) -> dict | None:
        """Phase 038: the seeded strike trigger as an optional policy. Returns the proposal's params, or None.

        Off unless policy.strike_trigger is set. The trigger value is snap_pressure (0) + w_spite x spite_gain
        + hunger x desperation_gain, where spite_gain is 1 for a person on this cell this resident holds a grievance
        against. It must reach policy.strike_threshold, and the resident needs stamina of at least attack_cost (the
        seed's gate; energy is 0 to 100, the reserve x 100). The world itself never refuses a blow for stamina."""
        if not self.policy.strike_trigger or not self.grievances:
            return None
        if float(context.observations.get("energy", 0.0)) / 100.0 < float(_CONTEST["attack_cost"]):
            return None
        here = sorted(str(r.get("id")) for r in context.observations.get("nearby_residents", [])
                      if int(r.get("distance", 1)) == 0 and str(r.get("id")) in self.grievances)
        if not here:
            return None
        hunger = float(context.observations.get("hunger", 0.0))
        w_spite = float(self.character.personality.get("w_spite", 0.0))
        value = 0.0 + w_spite * 1.0 + hunger * float(self.policy.strike_desperation_gain)
        if value < float(self.policy.strike_threshold):
            return None
        return {"target": here[0], "intensity": 1.0}

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
