"""Provider-neutral LLM backend.

No vendor SDK is imported here.  Applications provide a callable or an object
with ``complete(prompt)`` and can add their preferred transport separately.

Phase 031 hardening:

* Provider output must be a JSON object (a dict, or JSON text, optionally in
  a ``` fence) whose fields match the pack's ``PROMPT_RESPONSE_FIELDS``.
* A parse or validation failure gets exactly one repair call. The repair
  request is the original prompt plus ``repair: {"errors": [...]}``, where each
  error is a short fixed message. No model output is echoed back.
* A provider exception is not repaired. It counts as a failure at once.
* After a failed decision the backend returns an idle ``ActorResponse`` (no
  major action, not waiting). ``decide`` never raises for provider, parse, or
  validation errors. ``waiting`` would stop the whole turn for every resident.
* Cumulative counts live in ``last_backend_state`` and ``dump_held_state``.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Protocol

from ..character import CharacterDefinition, HeldState
from .prompts import PromptBuilder
from .protocol import ActorContext, ActorResponse


MAX_REPAIRS = 1
ERROR_LIMIT = 160
ERRORS_PER_RESPONSE = 5
# Error text that looks like a credential is dropped rather than stored or reported.
_SECRET_PATTERN = re.compile(
    r"authorization|bearer|api[_\- ]?key|secret|passw|token|\bsk-|[?&]key=|[A-Za-z0-9_\-]{28,}",
    re.IGNORECASE,
)
_COUNT_KEYS = ("calls", "repairs_used", "repaired_successes", "successes", "failures",
               "provider_errors", "invalid_outputs")


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

    Legality of an action is not checked here. The world validates every action."""
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
    if "waiting" in parsed and not isinstance(parsed["waiting"], bool):
        errors.append("waiting must be true or false")
    return errors[:ERRORS_PER_RESPONSE]


def safe_error(text: str) -> str:
    """Short error text for backend state. Text that looks like a credential is dropped."""
    text = " ".join(str(text).split())
    if _SECRET_PATTERN.search(text):
        return "[redacted: error text looked like a credential]"
    return text[:ERROR_LIMIT]


class LLMBackend:
    kind = "llm"
    communication_mode = "free_text"
    supports_free_text = True
    understands_raw_speech = True
    requires_conversational_interface = False

    def __init__(self, character: CharacterDefinition, provider: LLMProvider,
                 *, prompt_builder: PromptBuilder | None = None):
        self.character = character
        self.provider = provider
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.counts: dict[str, Any] = {key: 0 for key in _COUNT_KEYS}
        self.counts["latency_ms_total"] = 0.0
        self.counts["last_error"] = ""
        self.last_backend_state: dict[str, Any] = self._state({})

    @property
    def llm_counts(self) -> dict[str, Any]:
        """Cumulative counts for the game report (a copy)."""
        return dict(self.counts)

    def _state(self, extra: dict[str, Any]) -> dict[str, Any]:
        return {**extra, **{key: self.counts[key] for key in _COUNT_KEYS},
                "latency_ms_total": round(float(self.counts["latency_ms_total"]), 3),
                "last_error": self.counts["last_error"]}

    def _call(self, payload: dict[str, Any]) -> Any:
        complete = getattr(self.provider, "complete", None)
        if callable(complete):
            return complete(payload)
        if callable(self.provider):
            return self.provider(payload)
        raise TypeError("LLM provider must have complete(prompt) or be callable")

    def _check(self, raw: Any, fields) -> tuple[dict[str, Any] | None, ActorResponse | None, list[str]]:
        try:
            parsed = _payload(raw)
        except (TypeError, ValueError):
            return None, None, ["output is not a JSON object"]
        errors = validate_response(parsed, fields)
        if errors:
            return parsed, None, errors
        try:
            return parsed, ActorResponse.from_dict(parsed), []
        except (TypeError, ValueError, KeyError):
            return parsed, None, ["response fields could not be read"]

    def decide(self, context: ActorContext) -> ActorResponse:
        """Return the provider's response, or an idle response after a counted failure.

        This method never raises for provider, parse, or validation errors."""
        started = time.perf_counter()
        try:
            return self._decide(context, started)
        except Exception as exc:  # last resort: a bug here must not reach the world
            return self._fail("internal_error", exc, started, prompt=None)

    def _decide(self, context: ActorContext, started: float) -> ActorResponse:
        record = self.prompt_builder.build(context)
        base = record.as_dict()
        fields = tuple(self.prompt_builder.pack["PROMPT_RESPONSE_FIELDS"])
        prompt_hash = hashlib.sha256(record.as_json().encode()).hexdigest()
        errors: list[str] = []
        for attempt in range(MAX_REPAIRS + 1):
            payload = base if attempt == 0 else {**base, "repair": {"errors": list(errors)}}
            if attempt:
                self.counts["repairs_used"] += 1
            self.counts["calls"] += 1
            try:
                raw = self._call(payload)
            except Exception as exc:
                return self._fail("provider_error", exc, started, prompt=record,
                                  prompt_hash=prompt_hash)
            parsed, response, errors = self._check(raw, fields)
            if response is not None:
                elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
                raw_text = json.dumps(parsed, sort_keys=True, default=repr)
                self.counts["successes"] += 1
                if attempt:
                    self.counts["repaired_successes"] += 1
                self.counts["latency_ms_total"] += elapsed_ms
                self.last_backend_state = self._state({
                    "prompt_schema": record.schema,
                    "prompt_hash": prompt_hash,
                    "response_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
                    "latency_ms": elapsed_ms,
                    "outcome": "repaired" if attempt else "ok",
                    "attempts": attempt + 1,
                })
                return response
        return self._fail("invalid_output", "; ".join(errors), started, prompt=record,
                          prompt_hash=prompt_hash)

    def _fail(self, reason: str, error: Any, started: float, *, prompt,
              prompt_hash: str | None = None) -> ActorResponse:
        """Count an idle fallback, store the bounded error, and return an idle response."""
        self.counts["failures"] += 1
        if reason == "provider_error":
            self.counts["provider_errors"] += 1
            text = f"{type(error).__name__}: {error}"
        elif reason == "invalid_output":
            self.counts["invalid_outputs"] += 1
            text = str(error)
        else:
            text = f"{type(error).__name__}: {error}"
        self.counts["last_error"] = safe_error(text)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        self.counts["latency_ms_total"] += elapsed_ms
        extra = {"outcome": "idle_fallback", "reason": reason, "latency_ms": elapsed_ms}
        if prompt is not None:
            extra.update({"prompt_schema": prompt.schema, "prompt_hash": prompt_hash})
        self.last_backend_state = self._state(extra)
        return ActorResponse(backend_state={"llm_outcome": "idle_fallback", "llm_reason": reason})

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            backend_state={**self.last_backend_state, "communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "understands_raw_speech": self.understands_raw_speech,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
