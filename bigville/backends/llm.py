"""Provider-neutral LLM backend, with an autopilot (Phases 031 and 059).

No vendor SDK is imported here. Applications provide a callable or an object with ``complete(prompt)``.

Phase 031 (the provider call):

* Provider output must be a JSON object (a dict, or JSON text, optionally in a ``` fence) whose fields
  match the pack's ``PROMPT_RESPONSE_FIELDS``.
* A parse or validation failure gets exactly one repair call. The repair request is the original prompt
  plus ``repair: {"errors": [...]}``, where each error is a short fixed message. No model output is echoed.
* A provider exception is not repaired.
* ``decide`` never raises for provider, parse, or validation errors.

Phase 059 (the autopilot):

* The backend owns a ``DeterministicBackend`` for the same character (the autopilot). Every turn the
  autopilot decides, so its goals follow the resident's situation.
* The model is consulted only when the consult gate (bigville/backends/autopilot.py) fires a trigger: an
  interrupt, a routine boundary, a check-in, or an autopilot with nothing to do. Otherwise the autopilot acts.
* A consult that cannot finish (a provider error, an invalid reply after the repair, a call or spend cap)
  falls back to the autopilot's action, counted by cause. With ``autopilot=False`` the backend is the
  Phase 031 backend: it consults every turn and an unfinished consult is an idle turn.
* A reply with no ``major_action`` carries on as usual: the autopilot's action and continuation are kept,
  and the reply's utterances and memory updates are used. The explicit action ``wait`` does nothing.
  A reply with ``waiting: true`` is an invalid output (it stops the whole turn for every resident).
* A model plan (a continuation) is held by the game until it completes or is interrupted.
* Counts: consults, autopilot turns, carry-ons, waits, fallbacks by cause, and deviations (an accepted
  reply that names a different action from the autopilot's would-be choice, which is computed on every
  turn).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Protocol

from domains.autopilot import DEFAULT_PACK, table
from ..character import CharacterDefinition, HeldState
from .autopilot import FALLBACK_CAUSES, CallBudget, ConsultGate
from .cheap import DeterministicBackend, simple_policy_for
from .prompts import PromptBuilder
from .protocol import ActorContext, ActorResponse, ProposedAction


MAX_REPAIRS = 1
ERROR_LIMIT = 160
ERRORS_PER_RESPONSE = 5
# Error text that looks like a credential is dropped rather than stored or reported.
_SECRET_PATTERN = re.compile(
    r"authorization|bearer|api[_\- ]?key|secret|passw|token|\bsk-|[?&]key=|[A-Za-z0-9_\-]{28,}",
    re.IGNORECASE,
)
_COUNT_KEYS = ("calls", "repairs_used", "repaired_successes", "successes", "failures",
               "provider_errors", "invalid_outputs", "autopilot_turns", "carry_ons", "waits", "deviations")
# What the model is told about the autopilot, once per consult (in the payload, not in the hashed record).
CONSULT_RULES = (
    "You are consulted now because your usual routine would otherwise carry on. Reply with a major_action "
    "only to depart from the usual routine on purpose. A reply with no major_action carries on as usual. "
    "To do nothing at all, reply with a major_action whose action is wait. Do not set waiting."
)


class LLMProvider(Protocol):
    def complete(self, prompt: dict[str, Any] | str) -> Any:
        ...


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "output_text"):
        value = value.output_text
    if hasattr(value, "text"):
        value = value.text
    if not isinstance(value, str):
        raise TypeError("LLM provider must return a dict or JSON text")
    value = value.strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.startswith("json"):
            value = value[4:]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("LLM response JSON must be an object")
    return parsed


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _continuation_errors(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["continuation must be an object or null"]
    errors = []
    task = value.get("task")
    if task is not None:
        if not isinstance(task, dict) or not isinstance(task.get("action"), str) or not task.get("action"):
            errors.append("continuation.task must be an object with a non-empty action")
        elif "params" in task and task["params"] is not None and not isinstance(task["params"], dict):
            errors.append("continuation.task.params must be an object")
    interrupt = value.get("interrupt_on")
    if interrupt is not None and (not isinstance(interrupt, list)
                                  or not all(isinstance(item, str) for item in interrupt)):
        errors.append("continuation.interrupt_on must be a list of strings")
    for key in ("hunger_threshold", "energy_threshold"):
        if key in value and not _is_number(value[key]):
            errors.append(f"continuation.{key} must be a number")
    if "poll_each_turn" in value and not isinstance(value["poll_each_turn"], bool):
        errors.append("continuation.poll_each_turn must be true or false")
    return errors


def validate_response(parsed: dict[str, Any], fields: tuple[str, ...] | list[str]) -> list[str]:
    """Structural checks against the response fields. Returns fixed, short messages.

    Legality of an action is not checked here. The world checks every action. ``waiting: true`` is refused:
    a model that wants to do nothing names the action ``wait``."""
    errors = []
    for key in sorted(parsed):
        if key not in fields:
            errors.append(f"unknown field: {str(key)[:32]}")
    action = parsed.get("major_action")
    if action is not None:
        if not isinstance(action, dict):
            errors.append("major_action must be an object or null")
        else:
            if not isinstance(action.get("action"), str) or not action.get("action"):
                errors.append("major_action.action must be a non-empty string")
            if action.get("params") is not None and not isinstance(action.get("params"), dict):
                errors.append("major_action.params must be an object")
            if action.get("reason") is not None and not isinstance(action.get("reason"), str):
                errors.append("major_action.reason must be a string")
    errors += _continuation_errors(parsed.get("continuation"))
    utterances = parsed.get("utterances", [])
    if not isinstance(utterances, list) or not all(isinstance(item, dict) for item in utterances):
        errors.append("utterances must be a list of objects")
    else:
        for item in utterances:
            if "text" in item and not isinstance(item["text"], str):
                errors.append("utterances.text must be a string")
                break
            if item.get("target") is not None and not isinstance(item.get("target"), str):
                errors.append("utterances.target must be a string or null")
                break
    memory_updates = parsed.get("memory_updates", [])
    if not isinstance(memory_updates, list) or not all(isinstance(item, dict) for item in memory_updates):
        errors.append("memory_updates must be a list of objects")
    if "waiting" in parsed:
        if parsed["waiting"] is True:
            errors.append("waiting: true is not accepted; to do nothing, use major_action with action wait")
        elif not isinstance(parsed["waiting"], bool):
            errors.append("waiting must be true or false")
    return errors[:ERRORS_PER_RESPONSE]


def safe_error(text: str) -> str:
    """Short error text for backend state. Text that looks like a credential is dropped."""
    text = " ".join(str(text).split())
    if _SECRET_PATTERN.search(text):
        return "[redacted: error text looked like a credential]"
    return text[:ERROR_LIMIT]


def _key(action: ProposedAction | None) -> tuple | None:
    """What a deviation compares: the action name and its target, if it has one."""
    if action is None:
        return None
    target = action.params.get("target") if isinstance(action.params, dict) else None
    return (action.action, None if target is None else str(target))


def _day(calendar) -> int | None:
    value = (calendar or {}).get("day")
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class LLMBackend:
    kind = "llm"
    communication_mode = "free_text"
    supports_free_text = True
    understands_raw_speech = True
    requires_conversational_interface = False

    def __init__(self, character: CharacterDefinition, provider: LLMProvider,
                 *, prompt_builder: PromptBuilder | None = None, autopilot=True, policy=None,
                 budget: CallBudget | None = None, pack: str = DEFAULT_PACK):
        """``autopilot``: True builds a DeterministicBackend for this character (with ``policy``, by default
        the "default" simple profile); a DeterministicBackend is used as given; False or None turns the
        autopilot off, which is the Phase 031 behaviour. ``budget`` caps the provider calls; with an
        autopilot and no budget, the pack's per-resident daily cap applies."""
        self.character = character
        self.provider = provider
        self.prompt_builder = prompt_builder or PromptBuilder()
        if autopilot is True:
            self.autopilot = DeterministicBackend(character, policy=policy or simple_policy_for("default"))
        elif isinstance(autopilot, DeterministicBackend):
            self.autopilot = autopilot
        elif autopilot is False or autopilot is None:
            self.autopilot = None
        else:
            raise TypeError("autopilot must be True, False, or a DeterministicBackend")
        self.gate = ConsultGate(character, pack=pack) if self.autopilot is not None else None
        if budget is None and self.autopilot is not None:
            budget = CallBudget(max_calls_per_day=table(pack)["max_calls_per_resident_per_day"])
        self.budget = budget
        self.counts: dict[str, Any] = {key: 0 for key in _COUNT_KEYS}
        self.counts["latency_ms_total"] = 0.0
        self.counts["last_error"] = ""
        self.fallbacks: dict[str, int] = {cause: 0 for cause in FALLBACK_CAUSES}
        self.consults_by_reason: dict[str, int] = {}
        self.last_backend_state: dict[str, Any] = self._state({})

    @property
    def llm_counts(self) -> dict[str, Any]:
        """Cumulative counts for the game report (a copy). ``failures`` are the fallbacks of every cause;
        ``successes`` are the accepted replies; the two together are the consults that were attempted."""
        return {**self.counts, "fallbacks_by_cause": dict(self.fallbacks),
                "consults_by_reason": dict(self.consults_by_reason)}

    def _state(self, extra: dict[str, Any]) -> dict[str, Any]:
        return {**extra, **{key: self.counts[key] for key in _COUNT_KEYS},
                "latency_ms_total": round(float(self.counts["latency_ms_total"]), 3),
                "last_error": self.counts["last_error"],
                "fallbacks_by_cause": dict(self.fallbacks)}

    def _call(self, payload: dict[str, Any]) -> Any:
        complete = getattr(self.provider, "complete", None)
        if callable(complete):
            return complete(payload)
        if callable(self.provider):
            return self.provider(payload)
        raise TypeError("LLM provider must have complete(prompt) or be callable")

    def _resident(self) -> str:
        return str(self.character.character_id)

    def _check(self, raw: Any, fields) -> tuple[dict[str, Any] | None, list[str]]:
        try:
            parsed = _payload(raw)
        except (TypeError, ValueError):
            return None, ["output is not a JSON object"]
        errors = validate_response(parsed, fields)
        if errors:
            return None, errors
        return parsed, []

    def _ask(self, context: ActorContext, extra: dict[str, Any]):
        """One consult: the provider call and at most one repair, within the budget.

        Returns ("reply", parsed, attempts, prompt_record, prompt_hash) or
        ("fallback", cause, error, prompt_record, prompt_hash)."""
        record = self.prompt_builder.build(context)
        base = {**record.as_dict(), **extra}
        prompt_hash = hashlib.sha256(record.as_json().encode()).hexdigest()
        fields = tuple(self.prompt_builder.pack["PROMPT_RESPONSE_FIELDS"])
        resident, day = self._resident(), _day(context.observations.get("calendar"))
        errors: list[str] = []
        for attempt in range(MAX_REPAIRS + 1):
            if self.budget is not None:
                cause = self.budget.refusal(resident, day)
                if cause is not None:
                    return ("fallback", cause, f"{cause}: the call budget for this resident is spent",
                            record, prompt_hash)
            payload = base if attempt == 0 else {**base, "repair": {"errors": list(errors)}}
            if attempt:
                self.counts["repairs_used"] += 1
            self.counts["calls"] += 1
            if self.budget is not None:
                self.budget.record_call(resident, day)
            try:
                raw = self._call(payload)
            except Exception as exc:
                self._record_cost()
                return ("fallback", "provider_error", exc, record, prompt_hash)
            self._record_cost()
            parsed, errors = self._check(raw, fields)
            if parsed is not None:
                return ("reply", parsed, attempt + 1, record, prompt_hash)
        return ("fallback", "invalid_output", "; ".join(errors), record, prompt_hash)

    def _record_cost(self) -> None:
        if self.budget is not None:
            self.budget.record_cost(getattr(self.provider, "last_cost", None))

    # -- decisions -----------------------------------------------------------------------
    def decide(self, context: ActorContext) -> ActorResponse:
        """Return the autopilot's action, or the model's, or an idle response after a counted failure.

        This method never raises for provider, parse, or validation errors."""
        started = time.perf_counter()
        holder: dict[str, Any] = {}
        try:
            return self._decide(context, started, holder)
        except Exception as exc:  # last resort: a bug here must not reach the world
            return self._fallback("internal_error", exc, started, auto=holder.get("auto"))

    def _decide(self, context: ActorContext, started: float, holder: dict) -> ActorResponse:
        auto = None
        if self.autopilot is not None:
            auto = self.autopilot.decide(context)
            holder["auto"] = auto
        if self.gate is None:
            return self._consult(context, None, "every_turn", started, holder)
        game_reason = context.backend_state.get("continuation_interrupted")
        fired = self.gate.fired(context, game_reason=game_reason,
                                autopilot_idle=auto.major_action is None)
        if not fired:
            self.gate.note(context)
            return self._autopilot_turn(auto, started)
        return self._consult(context, auto, fired[0], started, holder)

    def _autopilot_turn(self, auto: ActorResponse, started: float) -> ActorResponse:
        self.counts["autopilot_turns"] += 1
        self.last_backend_state = self._state({"outcome": "autopilot", "turn_kind": "autopilot",
                                               "latency_ms": round((time.perf_counter() - started) * 1000.0, 3)})
        return auto

    def _consult(self, context: ActorContext, auto: ActorResponse | None, reason: str,
                 started: float, holder: dict) -> ActorResponse:
        self.consults_by_reason[reason] = self.consults_by_reason.get(reason, 0) + 1
        extra: dict[str, Any] = {}
        if self.gate is not None:
            extra = {"autopilot": {"why_consulted": reason, "usual_now": self.gate.usual(context),
                                   "rules": CONSULT_RULES}}
        outcome = self._ask(context, extra)
        if outcome[0] == "fallback":
            _, cause, error, record, prompt_hash = outcome
            response = self._fallback(cause, error, started, auto=auto, record=record,
                                      prompt_hash=prompt_hash, reason=reason)
        else:
            _, parsed, attempts, record, prompt_hash = outcome
            response = self._accept(parsed, auto, reason, attempts, started, record, prompt_hash)
        if self.gate is not None:
            self.gate.note(context, consulted=True)
        return response

    def _accept(self, parsed: dict[str, Any], auto: ActorResponse | None, reason: str, attempts: int,
                started: float, record, prompt_hash: str) -> ActorResponse:
        """Turn an accepted reply into this turn's response: an action, a carry-on, or a wait."""
        model = ActorResponse.from_dict(parsed)
        action = parsed.get("major_action")
        would_be = auto.major_action if auto is not None else None
        if isinstance(action, dict) and action.get("action") == "wait":
            kind = "wait"
            response = ActorResponse(utterances=model.utterances, memory_updates=model.memory_updates)
            self.counts["waits"] += 1
            departs = would_be is not None
        elif action is None:
            kind = "carry_on"
            base = auto if auto is not None else ActorResponse()
            response = ActorResponse(major_action=base.major_action, utterances=model.utterances,
                                     memory_updates=model.memory_updates, continuation=base.continuation)
            self.counts["carry_ons"] += 1
            departs = False
        else:
            kind = "act"
            response = ActorResponse(major_action=model.major_action, utterances=model.utterances,
                                     memory_updates=model.memory_updates, continuation=model.continuation)
            departs = would_be is not None and _key(model.major_action) != _key(would_be)
        if departs:
            self.counts["deviations"] += 1
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self.counts["successes"] += 1
        if attempts > 1:
            self.counts["repaired_successes"] += 1
        self.counts["latency_ms_total"] += elapsed_ms
        raw_text = json.dumps(parsed, sort_keys=True, default=repr)
        self.last_backend_state = self._state({
            "prompt_schema": record.schema,
            "prompt_hash": prompt_hash,
            "response_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
            "latency_ms": elapsed_ms,
            "outcome": "repaired" if attempts > 1 else "ok",
            "attempts": attempts,
            "turn_kind": kind,
            "consult_reason": reason,
            "would_be": None if would_be is None else {"action": would_be.action},
            "departs": departs,
        })
        response.backend_state = {"llm_turn": kind}
        return response

    def _fallback(self, cause: str, error: Any, started: float, *, auto: ActorResponse | None,
                  record=None, prompt_hash: str | None = None, reason: str | None = None) -> ActorResponse:
        """Count a fallback, store the bounded error, and return the autopilot's response (or idle, with no
        autopilot)."""
        self.counts["failures"] += 1
        self.fallbacks[cause] = self.fallbacks.get(cause, 0) + 1
        if cause == "provider_error":
            self.counts["provider_errors"] += 1
            text = f"{type(error).__name__}: {error}"
        elif cause == "invalid_output":
            self.counts["invalid_outputs"] += 1
            text = str(error)
        elif isinstance(error, BaseException):
            text = f"{type(error).__name__}: {error}"
        else:
            text = str(error)
        self.counts["last_error"] = safe_error(text)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self.counts["latency_ms_total"] += elapsed_ms
        extra = {"outcome": "fallback" if auto is not None else "idle_fallback", "reason": cause,
                 "turn_kind": "fallback", "consult_reason": reason, "latency_ms": elapsed_ms}
        if record is not None:
            extra.update({"prompt_schema": record.schema, "prompt_hash": prompt_hash})
        self.last_backend_state = self._state(extra)
        if auto is not None:
            auto.backend_state = {**auto.backend_state, "llm_fallback": cause}
            return auto
        return ActorResponse(backend_state={"llm_outcome": "idle_fallback", "llm_reason": cause})

    def react(self, context: ActorContext) -> ActorResponse:
        """Phase 029 reaction. With an autopilot whose triggers include ``reaction``, the model names one of
        the offered options (``major_action.params.option``, or ``major_action.action``). Otherwise, or on any
        failure, the autopilot's fixed reaction policy answers."""
        started = time.perf_counter()
        fallback = (self.autopilot.react(context) if self.autopilot is not None
                    else ActorResponse(backend_state={"reaction": "", "reason": "no_autopilot"}))
        if self.gate is None or "reaction" not in self.gate.triggers:
            return fallback
        self.consults_by_reason["reaction"] = self.consults_by_reason.get("reaction", 0) + 1
        options = list((context.observations.get("reaction") or {}).get("options", []))
        outcome = self._ask(context, {"autopilot": {"why_consulted": "reaction",
                                                    "usual_now": self.gate.usual(context),
                                                    "rules": CONSULT_RULES}})
        if outcome[0] == "fallback":
            _, cause, error, record, prompt_hash = outcome
            return self._fallback(cause, error, started, auto=fallback, record=record,
                                  prompt_hash=prompt_hash, reason="reaction")
        _, parsed, attempts, record, prompt_hash = outcome
        action = parsed.get("major_action") or {}
        choice = str((action.get("params") or {}).get("option") or action.get("action") or "")
        if choice not in options:
            return self._fallback("invalid_reaction", "the reaction is not one of the offered options",
                                  started, auto=fallback, record=record, prompt_hash=prompt_hash,
                                  reason="reaction")
        self.counts["successes"] += 1
        if attempts > 1:
            self.counts["repaired_successes"] += 1
        self.last_backend_state = self._state({"outcome": "repaired" if attempts > 1 else "ok",
                                               "turn_kind": "reaction", "consult_reason": "reaction",
                                               "prompt_schema": record.schema, "prompt_hash": prompt_hash,
                                               "attempts": attempts})
        return ActorResponse(backend_state={"reaction": choice, "reason": "model"})

    def note_turn(self, context: ActorContext) -> None:
        """Called by the game on a turn a model plan holds (no decide call), so the autopilot and the gate
        still see the resident's situation. Does not decide and does not call the provider."""
        if self.autopilot is None:
            return
        self.autopilot._update_goals(context)
        self.gate.note(context)

    def dump_held_state(self) -> HeldState:
        autopilot = self.gate.describe() if self.gate is not None else None
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            backend_state={**self.last_backend_state, "autopilot": autopilot, "communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "understands_raw_speech": self.understands_raw_speech,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
