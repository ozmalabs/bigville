"""The consult gate and the call budget of the LLM backend (Phase 059).

The gate decides, turn by turn, whether a model is consulted. It never calls a provider. Its rules
(which events prompt a consult, how often a routine boundary does, the quiet span) come from the pack
through domains/autopilot.py.

    gate = ConsultGate(character)
    reasons = gate.fired(context, game_reason=...)   # the triggers that fired, most specific first
    gate.note(context, consulted=bool)               # remember what this turn showed

Between consults the LLM backend's autopilot (a DeterministicBackend) acts. A consult is wanted when a
trigger fires. A consult that cannot be made (a cap, a provider error) falls back to the autopilot.

CallBudget caps the provider calls: per resident per day, and total spend when the provider reports a
cost (its ``last_cost`` attribute, in whatever unit the caller chooses).
"""
from __future__ import annotations

import threading

from domains.autopilot import (DEFAULT_PACK, TRIGGERS, boundary_consult_chance, habit_roll,
                               max_quiet_ticks, routine_strength, table, usual_block, usual_words)

# The causes a consult can fall back on, in the order the report lists them.
FALLBACK_CAUSES = ("provider_error", "invalid_output", "invalid_reaction", "call_cap", "spend_cap",
                   "internal_error")


class CallBudget:
    """Caps on provider calls. ``max_calls_per_day`` applies to each resident separately; ``max_spend``
    applies to the sum of the provider's reported costs. Either cap is None for no limit.

    The budget is checked before each provider call (a repair counts as a call), so a cap is never exceeded.
    One budget object may be shared by several LLM residents, and by residents decided in parallel: every
    read and update of the counts happens under one lock. ``reserve`` checks and records a call in one step."""

    def __init__(self, *, max_calls_per_day=None, max_spend=None):
        self.max_calls_per_day = None if max_calls_per_day is None else int(max_calls_per_day)
        self.max_spend = None if max_spend is None else float(max_spend)
        self.calls_by_day: dict[tuple[str, int | None], int] = {}
        self.spent = 0.0
        self._lock = threading.Lock()

    def _refusal(self, resident: str, day) -> str | None:
        if self.max_spend is not None and self.spent >= self.max_spend:
            return "spend_cap"
        if (self.max_calls_per_day is not None
                and self.calls_by_day.get((resident, day), 0) >= self.max_calls_per_day):
            return "call_cap"
        return None

    def refusal(self, resident: str, day) -> str | None:
        """The cause that stops a call now (``spend_cap`` or ``call_cap``), or None."""
        with self._lock:
            return self._refusal(resident, day)

    def reserve(self, resident: str, day) -> str | None:
        """Check and, when allowed, record one call in a single locked step. Returns the refusing cause, or None
        when the call was recorded and may be made."""
        with self._lock:
            cause = self._refusal(resident, day)
            if cause is None:
                key = (resident, day)
                self.calls_by_day[key] = self.calls_by_day.get(key, 0) + 1
            return cause

    def record_call(self, resident: str, day) -> None:
        with self._lock:
            key = (resident, day)
            self.calls_by_day[key] = self.calls_by_day.get(key, 0) + 1

    def record_cost(self, cost) -> None:
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            with self._lock:
                self.spent += float(cost)


def _day(calendar) -> int | None:
    value = (calendar or {}).get("day")
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ConsultGate:
    """The per-resident state the consult rules need: last hunger and energy, who was tied and nearby,
    the last heard turn, the last outcome, the routine block and the last consult turn."""

    def __init__(self, character, *, pack: str = DEFAULT_PACK):
        spec = table(pack)
        self.character = character
        self.pack = pack
        self.spec = spec
        self.resident = str(character.character_id)
        self.strength = routine_strength(character.personality, character.identity, pack)
        self.quiet_ticks = max_quiet_ticks(self.strength, pack)
        self.boundary_chance = boundary_consult_chance(self.strength, pack)
        self.triggers = frozenset(spec["consult_triggers"])
        unknown = self.triggers - set(TRIGGERS)
        if unknown:
            raise ValueError(f"unknown consult triggers in pack '{pack}': {sorted(unknown)}")
        self.last_consult_turn: int | None = None
        self.last_block: str | None = None
        self.last_hunger: float | None = None
        self.last_energy: float | None = None
        self.tied_in_view: frozenset[str] = frozenset()
        self.heard_turn = -1
        self.outcome_turn: int | None = None
        self.fail_reason: str | None = None
        self.fail_streak = 0

    # -- what the turn shows -------------------------------------------------------------
    @staticmethod
    def _tied(context) -> frozenset[str]:
        """Nearby residents with whom this resident has a tie (a positive tie or a feud the band reads)."""
        found = set()
        for resident in context.observations.get("nearby_residents", []) or []:
            if float(resident.get("tie_strength", 0.0) or 0.0) > 0.0 or float(resident.get("band_code", 0.0) or 0.0) > 0.0:
                found.add(str(resident.get("id")))
        return frozenset(found)

    def _failure(self, context):
        """(turn, reason) of a new failed attempt in this turn's observations, or None."""
        outcome = context.observations.get("last_outcome")
        if not outcome or outcome.get("applied") or outcome.get("turn") is None:
            return None
        turn = int(outcome["turn"])
        if self.outcome_turn is not None and turn <= self.outcome_turn:
            return None
        return turn, str(outcome.get("reason", ""))

    def fired(self, context, *, game_reason: str | None = None, autopilot_idle: bool = False) -> list[str]:
        """The consult triggers that fired this turn, in TRIGGERS order, limited to the pack's list.

        ``game_reason`` is the continuation interrupt the game reports (bigville/game.py), if any. An
        ``encounter`` from the game counts only when a tied resident newly came into view. A game reason
        that names no trigger (destination_reached, poll_each_turn) prompts nothing."""
        observations = context.observations
        found: set[str] = set()
        if game_reason in ("hunger_threshold", "energy_threshold", "task_failed", "world_event"):
            found.add(game_reason)
        hunger = _float(observations.get("hunger"), 0.0)
        energy = _float(observations.get("energy"), 100.0)
        if self.last_hunger is not None and self.last_hunger < float(self.spec["hunger_threshold"]) <= hunger:
            found.add("hunger_threshold")
        if self.last_energy is not None and self.last_energy > float(self.spec["energy_threshold"]) >= energy:
            found.add("energy_threshold")
        tied = self._tied(context)
        if tied - self.tied_in_view:
            found.add("tie_in_view")
        if any(str(record.get("target", "")) == self.resident and _float(record.get("turn"), -1.0) > self.heard_turn
               for record in observations.get("heard_utterances", []) or []):
            found.add("spoken_to")
        failure = self._failure(context)
        if failure is not None:
            _, reason = failure
            streak = self.fail_streak + 1 if reason == self.fail_reason else 1
            found.add("refusal_repeats" if streak >= int(self.spec["refusal_repeats"]) else "task_failed")
        if any(str(event.get("target", "")) == self.resident
               for event in observations.get("physical_events", []) or []):
            found.add("world_event")
        calendar = observations.get("calendar")
        block = usual_block(self.character.identity, calendar, self.pack)
        if block is not None and self.last_block is not None and block != self.last_block:
            if habit_roll(self.resident, "boundary", _day(calendar), block) < self.boundary_chance:
                found.add("routine_boundary")
        due = self.last_consult_turn is None or int(context.turn) - self.last_consult_turn >= self.quiet_ticks
        if due:
            found.add("check_in")
            # An idle autopilot asks at most once per quiet span: asking again next tick would ask the same.
            if autopilot_idle:
                found.add("nothing_to_do")
        return [name for name in TRIGGERS if name in found and name in self.triggers]

    def note(self, context, *, consulted: bool = False) -> None:
        """Remember this turn: the values the next turn's rules compare with. Called on every turn the
        gate sees, whether or not a consult happened."""
        observations = context.observations
        self.last_hunger = _float(observations.get("hunger"), 0.0)
        self.last_energy = _float(observations.get("energy"), 100.0)
        self.tied_in_view = self._tied(context)
        for record in observations.get("heard_utterances", []) or []:
            self.heard_turn = max(self.heard_turn, int(_float(record.get("turn"), self.heard_turn)))
        outcome = observations.get("last_outcome")
        if outcome and outcome.get("turn") is not None:
            turn = int(outcome["turn"])
            if self.outcome_turn is None or turn > self.outcome_turn:
                # A newer outcome only: an old one must not reset or extend the failure streak.
                self.outcome_turn = turn
                if outcome.get("applied"):
                    self.fail_reason, self.fail_streak = None, 0
                else:
                    reason = str(outcome.get("reason", ""))
                    self.fail_streak = self.fail_streak + 1 if reason == self.fail_reason else 1
                    self.fail_reason = reason
        block = usual_block(self.character.identity, observations.get("calendar"), self.pack)
        if block is not None:
            self.last_block = block
        if consulted:
            self.last_consult_turn = int(context.turn)

    def usual(self, context) -> str:
        """What the resident would usually do now, in words (for the prompt). "" when there is no routine."""
        return usual_words(self.character.identity, context.observations.get("calendar"), self.pack)

    def describe(self) -> dict:
        """The gate's fixed numbers, for the held state and the report."""
        return {"routine_strength": round(self.strength, 4), "max_quiet_ticks": self.quiet_ticks,
                "boundary_consult_chance": round(self.boundary_chance, 4)}
