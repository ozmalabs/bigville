"""Provider-neutral LLM backend, with an autopilot (Phases 031, 059) and continued sessions (Phase 066).

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

Phase 066 (the continued session and the log):

* Each resident has a thread (bigville/backends/thread.py). The system text is sent once. A consult sends a user
  message (the full packet first, then the changes since the last consult, with the full packet again every
  ``full_every`` consults), and the reply's content is kept as the assistant message. A repaired reply keeps the
  failed reply and the repair request in the thread, so the thread shows what was asked.
* When the thread would pass ``thread_chars``, a new thread starts with the full packet (persona, usual day,
  lessons and notes), and a new session id. A failed consult changes nothing.
* The payload carries ``messages`` (what is sent), ``thread`` (the id, index, mode and session) and, for a
  repair, ``repair``. The Phase 031 keys (``schema``, ``context``, ``system``) are still there for the current
  packet. The replay key is the messages (llm_transcript.thread_key).
* Every provider call attempt, and every budget refusal, is written to ``self.log`` when one is attached
  (bigville/llm_log.py), with the whole response: thinking included. Thinking is never put in a message, the
  packet, the response, the backend state or the held state.
* ``to_dict`` and ``from_dict`` hold the backend's state (threads, counts, gate, autopilot, budget), so a run can
  stop and resume. The character (memories and held frames) is not in this state: the game checkpoint holds it.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from typing import Any, Protocol

from domains.autopilot import DEFAULT_PACK, table
from ..character import CharacterDefinition, HeldState
from ..concurrency import DEFAULT_WORKERS
from ..llm_transcript import call_provider, thread_hash
from .autopilot import FALLBACK_CAUSES, CallBudget, ConsultGate
from .cheap import DeterministicBackend, NPCGoal, simple_policy_for
from .prompt_packet import PACKET_SCHEMA
from .prompts import PromptBuilder
from .protocol import ActorContext, ActorResponse, ProposedAction
from .reply_schema import check as check_reply, to_wire
from .thread import (DEFAULT_FULL_EVERY, DEFAULT_THREAD_CHARS, REPLY_RESERVE_CHARS, ConsultThread, canonical,
                     message_text, state_changes)


MAX_REPAIRS = 1
ERROR_LIMIT = 160
ERRORS_PER_RESPONSE = 5
STATE_SCHEMA = "bigville/llm-backend-state/1"
# Error text that looks like a credential is dropped rather than stored or reported.
_SECRET_PATTERN = re.compile(
    r"authorization|bearer|api[_\- ]?key|secret|passw|token|\bsk-|[?&]key=|[A-Za-z0-9_\-]{28,}",
    re.IGNORECASE,
)
_COUNT_KEYS = ("calls", "repairs_used", "repaired_successes", "successes", "failures",
               "provider_errors", "invalid_outputs", "autopilot_turns", "carry_ons", "waits", "deviations")
_THREAD_COUNTS = ("threads", "compactions", "full_consults", "delta_consults", "thread_chars_max")


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


def _check_reply(parsed: dict[str, Any], fields, pack: str, lesson_limit: int | None) -> list[str]:
    """Structural checks, then the pack's reply schema (words for intensity and amounts, memory kinds)."""
    errors = validate_response(parsed, fields)
    if errors:
        return errors
    return check_reply(parsed, pack, lesson_limit=lesson_limit)


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


def _redactor(provider: Any):
    redact = getattr(provider, "redact", None)
    return redact if callable(redact) else None


class LLMBackend:
    kind = "llm"
    # Phase 054: the game gives this resident's context its agent view (words only), and nothing else.
    wants_agent_view = True
    # Phase 062: the agent view is degraded by this resident's faculties (domains/perceiver.py); the LLM is not a
    # model of them.
    faculties = {"senses": "enforced", "skill": "enforced", "impairment": "enforced",
                 "literacy": "enforced", "numeracy": "enforced"}
    # Phase 053: this resident's knowledge is fogged (domains/map_memory.py): it knows the map as words, and its
    # moves are checked against what it knows.
    fogged = True
    # Phase 055: decided through the game's thread pool, with one thread per resident at a time. The backend keeps
    # its state per resident; the shared CallBudget and the provider are the only shared objects, and both are
    # thread-safe (the provider's per-call cost and usage are per thread).
    concurrent = True
    concurrency = DEFAULT_WORKERS
    communication_mode = "free_text"
    supports_free_text = True
    understands_raw_speech = True
    requires_conversational_interface = False

    def __init__(self, character: CharacterDefinition, provider: LLMProvider,
                 *, prompt_builder: PromptBuilder | None = None, autopilot=True, policy=None,
                 budget: CallBudget | None = None, pack: str = DEFAULT_PACK,
                 thread_chars: int = DEFAULT_THREAD_CHARS, full_every: int = DEFAULT_FULL_EVERY, log=None):
        """``autopilot``: True builds a DeterministicBackend for this character (with ``policy``, by default
        the "default" simple profile); a DeterministicBackend is used as given; False or None turns the
        autopilot off, which is the Phase 031 behaviour. ``budget`` caps the provider calls; with an
        autopilot and no budget, the pack's per-resident daily cap applies.

        Phase 066: ``thread_chars`` is the thread size that starts a new thread, and ``full_every`` the number of
        consults between full packets. ``log`` is an ``LLMLog`` (bigville/llm_log.py), or None for no log."""
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
        if int(thread_chars) < 1 or int(full_every) < 1:
            raise ValueError("thread_chars and full_every must be at least 1")
        self.thread_chars = int(thread_chars)
        self.full_every = int(full_every)
        self.log = log
        self.threads: dict[str, ConsultThread] = {}
        self.counts: dict[str, Any] = {key: 0 for key in _COUNT_KEYS}
        self.counts["latency_ms_total"] = 0.0
        self.counts["last_error"] = ""
        # Phase 055: spend and tokens reported by the provider, and the time spent in provider calls.
        self.counts.update({"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "tokens_reasoning": 0,
                            "call_latency_ms_total": 0.0})
        # Phase 066: the thread counts (threads started, compactions, full and delta consults, largest thread).
        self.counts.update({key: 0 for key in _THREAD_COUNTS})
        self.fallbacks: dict[str, int] = {cause: 0 for cause in FALLBACK_CAUSES}
        self.consults_by_reason: dict[str, int] = {}
        # Phase 055: per calendar day (the period the call budget uses): calls, repairs, fallbacks, cost, latency.
        self.by_day: dict[str, dict[str, Any]] = {}
        self._bucket_day = None
        self.last_backend_state: dict[str, Any] = self._state({})

    @property
    def llm_counts(self) -> dict[str, Any]:
        """Cumulative counts for the game report (a copy). ``failures`` are the fallbacks of every cause;
        ``successes`` are the accepted replies; the two together are the consults that were attempted."""
        return {**self.counts, "fallbacks_by_cause": dict(self.fallbacks),
                "consults_by_reason": dict(self.consults_by_reason),
                "by_day": {day: dict(row) for day, row in self.by_day.items()},
                "thread_length": {r: t.consults for r, t in sorted(self.threads.items())},
                "thread_chars": {r: t.chars() for r, t in sorted(self.threads.items())}}

    def _bucket(self, day) -> dict[str, Any]:
        key = "none" if day is None else str(day)
        return self.by_day.setdefault(key, {"calls": 0, "repairs": 0, "fallbacks": 0, "cost": 0.0,
                                            "latency_ms": 0.0})

    def _state(self, extra: dict[str, Any]) -> dict[str, Any]:
        return {**extra, **{key: self.counts[key] for key in _COUNT_KEYS},
                "latency_ms_total": round(float(self.counts["latency_ms_total"]), 3),
                "last_error": self.counts["last_error"],
                "fallbacks_by_cause": dict(self.fallbacks)}

    def _call(self, payload: dict[str, Any], meta: dict[str, Any] | None = None) -> Any:
        return call_provider(self.provider, payload, meta)

    def _resident(self) -> str:
        return str(self.character.character_id)

    def _check(self, raw: Any, fields, affordances=None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
        """(wire reply, the reply as the provider sent it, errors). The wire reply is None when a check fails.
        ``affordances`` are the context's rows, so a handle in the reply names the full row (Phase 054 follow-up)."""
        try:
            parsed = _payload(raw)
        except (TypeError, ValueError):
            return None, None, ["output is not a JSON object"]
        errors = _check_reply(parsed, fields, self.prompt_builder.pack.name, self._lesson_limit())
        if errors:
            return None, None, errors
        wire = to_wire(parsed, self.prompt_builder.pack.name, affordances=affordances)
        return wire, parsed, []

    def _lesson_limit(self) -> int:
        return int(self.prompt_builder.pack["PROMPT_PACKET"]["lessons_max"])

    # -- the thread (Phase 066) -------------------------------------------------------------
    def _text(self, key: str) -> str:
        return str(self.prompt_builder.pack["PROMPT_PACKET"]["thread"][key])

    def _message(self, key: str, body: dict[str, Any]) -> str:
        """A user message: the pack's text for this kind, a newline, then the JSON body."""
        return self._text(key) + "\n" + json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)

    def _next_turn(self, resident: str, record, context: ActorContext):
        """The thread this consult will use, its user message, the mode (``full`` or ``delta``), the packet state
        (a JSON copy), and whether the thread was created and whether it was compacted. Nothing is stored here:
        ``_commit`` stores the thread once a reply is accepted."""
        state = json.loads(canonical(record.context))
        turn = int(context.turn)
        current = self.threads.get(resident)
        if current is None:
            thread = ConsultThread(resident=resident, index=0, messages=[{"role": "system", "content": record.system}],
                                   started_turn=turn)
            text = self._message("first", {"schema": PACKET_SCHEMA, "context": state})
            return thread, {"role": "user", "content": text}, "full", state, True, False
        if current.last_state is not None and current.since_full < self.full_every:
            mode = "delta"
            text = self._message("delta", {"schema": PACKET_SCHEMA, **state_changes(current.last_state, state)})
        else:
            mode = "full"
            text = self._message("full", {"schema": PACKET_SCHEMA, "context": state})
        if current.consults and current.chars() + len(text) + REPLY_RESERVE_CHARS > self.thread_chars:
            thread = ConsultThread(resident=resident, index=current.index + 1,
                                   messages=[{"role": "system", "content": record.system}], started_turn=turn)
            text = self._message("start", {"schema": PACKET_SCHEMA, "context": state})
            return thread, {"role": "user", "content": text}, "full", state, True, True
        return current.copy(), {"role": "user", "content": text}, mode, state, False, False

    def _commit(self, resident: str, thread: ConsultThread, messages: list[dict[str, str]], text: str,
                state: dict[str, Any], mode: str, created: bool, compacted: bool) -> None:
        """Store an accepted consult: the messages sent, and the reply's content as the assistant message."""
        thread.messages = list(messages) + [{"role": "assistant", "content": text}]
        thread.consults += 1
        thread.last_state = state
        if mode == "full":
            thread.since_full = 0
            thread.full_consults += 1
            self.counts["full_consults"] += 1
        else:
            thread.since_full += 1
            thread.delta_consults += 1
            self.counts["delta_consults"] += 1
        thread.chars_max = max(thread.chars_max, thread.chars())
        self.counts["thread_chars_max"] = max(self.counts["thread_chars_max"], thread.chars_max)
        if created:
            self.counts["threads"] += 1
        if compacted:
            self.counts["compactions"] += 1
        self.threads[resident] = thread

    def _repair_message(self, errors: list[str]) -> str:
        return self._message("repair", {"errors": list(errors)})

    # -- the consult ----------------------------------------------------------------------------
    def _ask(self, context: ActorContext, consult_reason: str | None, choices=None):
        """One consult: the provider call and at most one repair, within the budget.

        Returns ("reply", wire_reply, attempts, prompt_record, prompt_hash, as_sent) or
        ("fallback", cause, error, prompt_record, prompt_hash). A context without an agent view is never sent:
        the prompt path is the Phase 054 packet, which is built from the view."""
        if getattr(context, "agent_view", None) is None:
            return ("fallback", "internal_error", "no agent view was built for this resident", None, None)
        record = self.prompt_builder.build(context, consult_reason, choices)
        base = record.as_dict()
        prompt_hash = hashlib.sha256(record.as_json().encode()).hexdigest()
        fields = tuple(self.prompt_builder.pack["PROMPT_RESPONSE_FIELDS"])
        resident, day = self._resident(), _day(context.observations.get("calendar"))
        thread, user, mode, state, created, compacted = self._next_turn(resident, record, context)
        messages = thread.messages + [user]
        errors: list[str] = []
        last_text = ""
        for attempt in range(MAX_REPAIRS + 1):
            if attempt:
                # The repair is one extra message in the thread: the fixed errors. The failed reply is not echoed
                # (Phase 031: no model output goes back in a repair).
                messages = messages + [{"role": "user", "content": self._repair_message(errors)}]
            if self.budget is not None:
                # Checked and recorded in one locked step, so residents decided in parallel cannot overrun the cap.
                cause = self.budget.reserve(resident, day)
                if cause is not None:
                    self._log_refusal(context, consult_reason, thread, cause, attempt)
                    return ("fallback", cause, f"{cause}: the call budget for this resident is spent",
                            record, prompt_hash)
            if attempt:
                self.counts["repairs_used"] += 1
                self._bucket(day)["repairs"] += 1
            self.counts["calls"] += 1
            self._bucket(day)["calls"] += 1
            payload = {**base, "messages": messages,
                       "thread": {"id": thread.thread_id(), "index": thread.index, "mode": mode,
                                  "consult": thread.consults + 1, "session": thread.session(),
                                  "compacted": compacted}}
            if attempt:
                payload["repair"] = {"errors": list(errors)}
            meta = {"turn": int(context.turn), "actor": resident, "attempt": attempt, "period": day,
                    "session": thread.session(), "thread": thread.thread_id()}
            started = time.perf_counter()
            try:
                raw = self._call(payload, meta)
            except Exception as exc:
                self._record_cost(day, started)
                self._log_attempt(context, consult_reason, thread, mode, compacted, attempt, messages, None,
                                  exc, [], "provider_error", "provider_error", started)
                return ("fallback", "provider_error", exc, record, prompt_hash)
            self._record_cost(day, started)
            last_text = message_text(raw)
            # LA05: a lazy context's capability rows carry no bindable handle. The autopilot may have filled
            # context.affordances with its own candidate list before this consult; the model's direct params
            # must not be bound to those rows, so the lazy path passes the explicit empty menu.
            affordances = [] if isinstance(context.observations.get("entities"), dict) else context.affordances
            wire, as_sent, errors = self._check(raw, fields, affordances)
            if wire is not None:
                outcome = "repaired" if attempt else "accepted"
                self._log_attempt(context, consult_reason, thread, mode, compacted, attempt, messages, raw,
                                  None, [], outcome, None, started)
                self._commit(resident, thread, messages, last_text, state, mode, created, compacted)
                return ("reply", wire, attempt + 1, record, prompt_hash, as_sent)
            final = attempt == MAX_REPAIRS
            self._log_attempt(context, consult_reason, thread, mode, compacted, attempt, messages, raw,
                              None, errors, "invalid", "invalid_output" if final else None, started)
        return ("fallback", "invalid_output", "; ".join(errors), record, prompt_hash)

    # -- the log (Phase 066) -------------------------------------------------------------------
    def _log_attempt(self, context: ActorContext, reason: str | None, thread: ConsultThread, mode: str,
                     compacted: bool, attempt: int, messages: list[dict[str, str]], raw: Any,
                     exc: BaseException | None, errors: list[str], outcome: str, cause: str | None,
                     started: float) -> None:
        """Write one record for one provider call attempt. ``response`` is the whole response: for a provider that
        returns a ProviderResult, the call's ``.result`` (reasoning and every other field, untruncated)."""
        if self.log is None:
            return
        redact = _redactor(self.provider)
        call = getattr(self.provider, "last_call", None) if exc is not None or raw is None else None
        result = getattr(raw, "result", None) if raw is not None else None
        if result is not None:
            response = {"ok": True, **result.to_dict()}
        elif raw is not None:
            response = {"ok": True, "content": raw if isinstance(raw, (str, dict)) else str(raw)}
        else:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}" if exc is not None else None,
                        **({k: v for k, v in (call or {}).items() if k != "ok"} if isinstance(call, dict) else {})}
        day = _day(context.observations.get("calendar"))
        record = {
            "kind": "call",
            "resident": self._resident(),
            "turn": int(context.turn),
            "day": day,
            "thread": thread.thread_id(),
            "thread_index": thread.index,
            "session": thread.session(),
            "consult_no": thread.consults + 1,
            "mode": mode,
            "compacted": compacted,
            "consult_reason": reason,
            "attempt": attempt,
            "messages": messages,
            "thread_hash": thread_hash(messages),
            "response": response,
            "retries": list(response.get("attempts") or []) if isinstance(response, dict) else [],
            "outcome": outcome,
            "errors": list(errors),
            "fallback_cause": cause,
            "timings": {"latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
                        "provider_latency_ms": response.get("latency_ms") if isinstance(response, dict) else None,
                        "started_at": response.get("started_at") if isinstance(response, dict) else None},
        }
        self.log.append(record, redact=redact)

    def _log_refusal(self, context: ActorContext, reason: str | None, thread: ConsultThread, cause: str,
                     attempt: int) -> None:
        """A budget refusal: no call was made. Logged so the log shows every consult the cap stopped."""
        if self.log is None:
            return
        self.log.append({"kind": "refused", "resident": self._resident(), "turn": int(context.turn),
                          "day": _day(context.observations.get("calendar")), "thread": thread.thread_id(),
                          "thread_index": thread.index, "consult_reason": reason, "attempt": attempt,
                          "fallback_cause": cause}, redact=_redactor(self.provider))

    # -- budget spend ---------------------------------------------------------------------------
    def _record_cost(self, day, started: float) -> None:
        """Book the provider's figures for the call that just returned, on this thread: spend (for the cap),
        tokens, and the time the call took."""
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        cost = getattr(self.provider, "last_cost", None)
        if self.budget is not None:
            self.budget.record_cost(cost)
        self.counts["call_latency_ms_total"] += elapsed_ms
        bucket = self._bucket(day)
        bucket["latency_ms"] += elapsed_ms
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            self.counts["cost"] += float(cost)
            bucket["cost"] += float(cost)
        usage = getattr(self.provider, "last_usage", None) or {}
        self.counts["tokens_in"] += int(usage.get("input", 0) or 0)
        self.counts["tokens_out"] += int(usage.get("output", 0) or 0)
        self.counts["tokens_reasoning"] += int(usage.get("reasoning", 0) or 0)

    # -- decisions -----------------------------------------------------------------------------
    def decide(self, context: ActorContext) -> ActorResponse:
        """Return the autopilot's action, or the model's, or an idle response after a counted failure.

        This method never raises for provider, parse, or validation errors."""
        started = time.perf_counter()
        holder: dict[str, Any] = {}
        self._bucket_day = _day(context.observations.get("calendar"))
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
        outcome = self._ask(context, reason if self.gate is not None else None)
        if outcome[0] == "fallback":
            _, cause, error, record, prompt_hash = outcome
            response = self._fallback(cause, error, started, auto=auto, record=record,
                                      prompt_hash=prompt_hash, reason=reason)
        else:
            _, parsed, attempts, record, prompt_hash, as_sent = outcome
            response = self._accept(parsed, auto, reason, attempts, started, record, prompt_hash, as_sent)
        if self.gate is not None:
            self.gate.note(context, consulted=True)
        return response

    def _accept(self, parsed: dict[str, Any], auto: ActorResponse | None, reason: str, attempts: int,
                started: float, record, prompt_hash: str, as_sent: dict[str, Any] | None = None) -> ActorResponse:
        """Turn an accepted reply into this turn's response: an action, a carry-on, or a wait. ``parsed`` is the
        wire form; ``as_sent`` is the reply as the provider wrote it, which the response hash covers."""
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
        if record.meta is not None and record.meta.get("merge"):
            self._merge_lessons(record.meta.get("lesson_ids", []), parsed)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self.counts["successes"] += 1
        if attempts > 1:
            self.counts["repaired_successes"] += 1
        self.counts["latency_ms_total"] += elapsed_ms
        raw_text = json.dumps(as_sent if as_sent is not None else parsed, sort_keys=True, default=repr)
        self.last_backend_state = self._state({
            "prompt_schema": record.schema,
            "prompt_hash": prompt_hash,
            "prompt_chars": int((record.context.get("sizes") or {}).get("total", 0)),
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

    def _merge_lessons(self, lesson_ids, parsed: dict[str, Any]) -> None:
        """A merge replaces the lessons the prompt listed, once the reply carries lesson updates of its own. The
        reply's lessons are then added by the game as ordinary memory updates. A reply without lessons keeps the
        old ones, and the next consult asks again."""
        if not any(item.get("kind") == "lesson" for item in parsed.get("memory_updates", []) or []):
            return
        listed = set(lesson_ids)
        self.character.memories[:] = [memory for memory in self.character.memories
                                      if memory.memory_id not in listed]
        self.counts["lessons_merged"] = self.counts.get("lessons_merged", 0) + len(listed)

    def _fallback(self, cause: str, error: Any, started: float, *, auto: ActorResponse | None,
                  record=None, prompt_hash: str | None = None, reason: str | None = None) -> ActorResponse:
        """Count a fallback, store the bounded error, and return the autopilot's response (or idle, with no
        autopilot)."""
        self.counts["failures"] += 1
        self.fallbacks[cause] = self.fallbacks.get(cause, 0) + 1
        self._bucket(self._bucket_day)["fallbacks"] += 1
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
        self._bucket_day = _day(context.observations.get("calendar"))
        fallback = (self.autopilot.react(context) if self.autopilot is not None
                    else ActorResponse(backend_state={"reaction": "", "reason": "no_autopilot"}))
        if self.gate is None or "reaction" not in self.gate.triggers:
            return fallback
        self.consults_by_reason["reaction"] = self.consults_by_reason.get("reaction", 0) + 1
        options = list((context.observations.get("reaction") or {}).get("options", []))
        outcome = self._ask(context, "reaction", options)
        if outcome[0] == "fallback":
            _, cause, error, record, prompt_hash = outcome
            return self._fallback(cause, error, started, auto=fallback, record=record,
                                  prompt_hash=prompt_hash, reason="reaction")
        _, parsed, attempts, record, prompt_hash, _as_sent = outcome
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

    # -- stop and resume (Phase 066) -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """The backend's state as JSON-able data: threads, counts, the consult gate, the autopilot's goals and
        choices, and the call budget. Not the character (its memories and held frames are the game's)."""
        gate = None
        if self.gate is not None:
            g = self.gate
            gate = {"last_consult_turn": g.last_consult_turn, "last_block": g.last_block,
                    "last_hunger": g.last_hunger, "last_energy": g.last_energy,
                    "tied_in_view": sorted(g.tied_in_view), "heard_turn": g.heard_turn,
                    "outcome_turn": g.outcome_turn, "fail_reason": g.fail_reason, "fail_streak": g.fail_streak}
        autopilot = None
        if self.autopilot is not None:
            a = self.autopilot
            autopilot = {"last_choice": json.loads(canonical(a.last_choice)),
                         "rest_energy_threshold": a.rest_energy_threshold,
                         "goals": [asdict(goal) for goal in a.goals],
                         "current_goal": asdict(a.current_goal) if a.current_goal is not None else None,
                         "last_speech_turn": a.last_speech_turn, "time_band": a.time_band,
                         "intoxication_trace": json.loads(canonical(a.intoxication_trace)),
                         "grievances": dict(a.grievances)}
        budget = None
        if self.budget is not None:
            with self.budget._lock:
                budget = {"calls_by_day": [[r, d, n] for (r, d), n in sorted(
                              self.budget.calls_by_day.items(), key=lambda item: (item[0][0], str(item[0][1])))],
                          "spent": self.budget.spent}
        return {"schema": STATE_SCHEMA, "resident": self._resident(),
                "threads": {r: t.to_dict() for r, t in sorted(self.threads.items())},
                "counts": json.loads(canonical(self.counts)), "fallbacks": dict(self.fallbacks),
                "consults_by_reason": dict(self.consults_by_reason),
                "by_day": json.loads(canonical(self.by_day)),
                "last_backend_state": json.loads(canonical(self.last_backend_state)),
                "gate": gate, "autopilot": autopilot, "budget": budget,
                "bucket_day": self._bucket_day}

    def restore_state(self, data: dict[str, Any]) -> None:
        """Load the state written by ``to_dict`` into this backend (which was built for the same character)."""
        if data.get("schema") != STATE_SCHEMA:
            raise ValueError(f"unsupported LLM backend state: {data.get('schema')!r}")
        if data.get("resident") != self._resident():
            raise ValueError(f"state is for {data.get('resident')!r}, not {self._resident()!r}")
        self.threads = {r: ConsultThread.from_dict(t) for r, t in data["threads"].items()}
        self.counts.update(data["counts"])
        self.fallbacks = {cause: int(n) for cause, n in data["fallbacks"].items()}
        self.consults_by_reason = {k: int(v) for k, v in data["consults_by_reason"].items()}
        self.by_day = data["by_day"]
        self.last_backend_state = data["last_backend_state"]
        self._bucket_day = data.get("bucket_day")
        if data.get("gate") is not None:
            if self.gate is None:
                raise ValueError("state has a consult gate but this backend has no autopilot")
            g, s = self.gate, data["gate"]
            g.last_consult_turn, g.last_block = s["last_consult_turn"], s["last_block"]
            g.last_hunger, g.last_energy = s["last_hunger"], s["last_energy"]
            g.tied_in_view = frozenset(s["tied_in_view"])
            g.heard_turn, g.outcome_turn = s["heard_turn"], s["outcome_turn"]
            g.fail_reason, g.fail_streak = s["fail_reason"], s["fail_streak"]
        if data.get("autopilot") is not None:
            if self.autopilot is None:
                raise ValueError("state has an autopilot but this backend has none")
            a, s = self.autopilot, data["autopilot"]
            a.last_choice = s["last_choice"]
            a.rest_energy_threshold = float(s["rest_energy_threshold"])
            a.goals = [NPCGoal(**goal) for goal in s["goals"]]
            a.current_goal = NPCGoal(**s["current_goal"]) if s["current_goal"] is not None else None
            a.last_speech_turn, a.time_band = int(s["last_speech_turn"]), str(s["time_band"])
            a.intoxication_trace = s["intoxication_trace"]
            a.grievances = {str(k): int(v) for k, v in s["grievances"].items()}
        if data.get("budget") is not None and self.budget is not None:
            with self.budget._lock:
                self.budget.calls_by_day = {(r, d): int(n) for r, d, n in data["budget"]["calls_by_day"]}
                self.budget.spent = float(data["budget"]["spent"])

    @classmethod
    def from_dict(cls, data: dict[str, Any], character: CharacterDefinition, provider: LLMProvider,
                  **kwargs) -> "LLMBackend":
        """A backend for ``character`` with the state in ``data``. ``kwargs`` are the constructor's (the same ``autopilot``,
        ``pack``, ``policy``, ``thread_chars`` and ``full_every`` as the stopped backend, which the state does not hold)."""
        backend = cls(character, provider, **kwargs)
        backend.restore_state(data)
        return backend
