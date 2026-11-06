"""Transcripts, recording and replay of LLM calls (Phase 055).

A transcript is an append-only JSON Lines file, one line per provider call:

    {"schema", "run_id", "turn", "actor", "attempt", "prompt_hash", "prompt"?, "reply", "error"?,
     "latency_ms", "model"?, "tokens"?, "cost"?}

``RecordingProvider`` wraps any provider and writes these lines. ``ReplayProvider`` serves the recorded
replies back, keyed by (turn, actor, prompt hash). A prompt that differs from the recording has no key,
so the replay raises ``ReplayMismatch``. The backend counts that as a provider error and falls back
to its autopilot, as it does for any failed call.

Every line passes through a ``redact`` function (the provider's, when it has one) before it is written, so
a provider key cannot reach a transcript by way of an error message or a model reply.

Providers may receive call metadata: a provider with ``wants_meta = True`` is called as
``complete(payload, meta=...)`` where ``meta`` has ``turn``, ``actor`` and ``attempt``. Other providers
keep the Phase 031 call ``complete(payload)`` or ``payload(...)``.

Thread safety: transcripts take a lock per line. ``last_cost`` and ``last_usage`` are per thread, so a
backend that reads them right after its own call gets the figures for that call, even when residents call
the provider in parallel.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

TRANSCRIPT_SCHEMA = "bigville/llm-transcript/1"


class ReplayMismatch(RuntimeError):
    """A replayed call has no recording with this turn, actor and prompt hash (the prompt or the run changed)."""


class RecordedError(RuntimeError):
    """A call that failed in the recorded run fails the same way on replay."""


def prompt_hash(payload: Any) -> str:
    """SHA-256 of the canonical JSON of a prompt payload. The key the replay matches on."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_provider(provider: Any, payload: Any, meta: dict[str, Any] | None = None) -> Any:
    """Call a provider in whichever form it has: ``complete(payload, meta=...)``, ``complete(payload)``,
    or a plain callable."""
    if getattr(provider, "wants_meta", False):
        return provider.complete(payload, meta=dict(meta or {}))
    complete = getattr(provider, "complete", None)
    if callable(complete):
        return complete(payload)
    if callable(provider):
        return provider(payload)
    raise TypeError("LLM provider must have complete(prompt) or be callable")


def _reply_value(reply: Any) -> Any:
    if isinstance(reply, (str, dict)):
        return reply
    if hasattr(reply, "output_text"):
        return str(reply.output_text)
    if hasattr(reply, "text"):
        return str(reply.text)
    return str(reply)


class Transcript:
    """An append-only JSONL file. Lines from concurrent calls never interleave."""

    def __init__(self, path: str | Path, *, run_id: str, include_prompts: bool = True,
                 redact: Callable[[str], str] | None = None):
        self.path = Path(path)
        self.run_id = str(run_id)
        self.include_prompts = bool(include_prompts)
        self._redact = redact or (lambda text: text)
        self._lock = threading.Lock()
        self.lines = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        text = self._redact(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str))
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")
            self.lines += 1


class RecordingProvider:
    """Wraps a provider and writes one transcript line per call (failed calls too)."""

    wants_meta = True

    def __init__(self, inner: Any, transcript: Transcript):
        self.inner = inner
        self.transcript = transcript
        self._local = threading.local()

    @property
    def last_cost(self):
        return getattr(self._local, "cost", None)

    @property
    def last_usage(self):
        return getattr(self._local, "usage", None)

    def redact(self, text: str) -> str:
        redact = getattr(self.inner, "redact", None)
        return redact(text) if callable(redact) else text

    def complete(self, payload: Any, meta: dict[str, Any] | None = None) -> Any:
        meta = dict(meta or {})
        digest = prompt_hash(payload)
        started = time.perf_counter()
        base = {"schema": TRANSCRIPT_SCHEMA, "run_id": self.transcript.run_id,
                "turn": meta.get("turn"), "actor": meta.get("actor"),
                "attempt": meta.get("attempt", 0), "prompt_hash": digest}
        if self.transcript.include_prompts:
            base["prompt"] = payload
        try:
            reply = call_provider(self.inner, payload, meta)
        except Exception as exc:
            self._local.cost = getattr(self.inner, "last_cost", None)
            self._local.usage = getattr(self.inner, "last_usage", None)
            self.transcript.append({**base, "error": f"{type(exc).__name__}: {exc}",
                                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
                                    **_extras(self.inner)})
            raise
        self._local.cost = getattr(self.inner, "last_cost", None)
        self._local.usage = getattr(self.inner, "last_usage", None)
        self.transcript.append({**base, "reply": _reply_value(reply),
                                "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
                                **_extras(self.inner)})
        return reply


def _extras(provider: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    model = getattr(provider, "last_model", None)
    if model:
        out["model"] = str(model)
    usage = getattr(provider, "last_usage", None)
    if usage:
        out["tokens"] = dict(usage)
    cost = getattr(provider, "last_cost", None)
    if cost is not None:
        out["cost"] = cost
    return out


def read_transcript(path: str | Path) -> list[dict[str, Any]]:
    """The records of a transcript, in file order."""
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


class ReplayProvider:
    """Serves recorded replies. A call matches a recording by turn, actor and prompt hash; repeated identical
    calls in one turn replay in the order they were recorded."""

    wants_meta = True

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._index: dict[tuple, list[dict[str, Any]]] = {}
        for record in read_transcript(self.path):
            key = (record.get("turn"), record.get("actor"), record.get("prompt_hash"))
            self._index.setdefault(key, []).append(record)
        self._cursor: dict[tuple, int] = {}
        self._lock = threading.Lock()
        self._local = threading.local()
        self.calls = 0
        self.mismatches: list[str] = []

    @property
    def last_cost(self):
        return getattr(self._local, "cost", None)

    @property
    def last_usage(self):
        return getattr(self._local, "usage", None)

    def _mismatch(self, message: str):
        self.mismatches.append(message)
        return ReplayMismatch(message)

    def complete(self, payload: Any, meta: dict[str, Any] | None = None) -> Any:
        meta = dict(meta or {})
        turn, actor = meta.get("turn"), meta.get("actor")
        digest = prompt_hash(payload)
        key = (turn, actor, digest)
        with self._lock:
            self.calls += 1
            records = self._index.get(key)
            if not records:
                same_slot = [k for k in self._index if k[0] == turn and k[1] == actor]
                if same_slot:
                    detail = "the prompt differs from the recorded one for this turn and actor"
                else:
                    detail = "the run has no recorded call for this turn and actor"
                raise self._mismatch(f"replay mismatch at turn {turn} for {actor}: {detail} "
                                     f"(prompt hash {digest[:12]})")
            position = self._cursor.get(key, 0)
            if position >= len(records):
                raise self._mismatch(f"replay mismatch at turn {turn} for {actor}: more calls with this prompt "
                                     f"than were recorded ({len(records)})")
            self._cursor[key] = position + 1
            record = records[position]
        self._local.cost = record.get("cost")
        self._local.usage = record.get("tokens")
        if "error" in record:
            raise RecordedError(str(record["error"]))
        return record.get("reply")
