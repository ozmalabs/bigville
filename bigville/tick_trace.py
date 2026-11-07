"""Pure equivalence oracle and provenance trace for the tick-graph work (TG01).

The trace layer is deliberately read-only. ``step_trace(game)`` is called after
``game.step()`` has advanced a turn and records only values the engine already
exposes: the turn number, the deterministic application order, every actor's
proposal, the per-actor result and error, active continuation requests, and a
SHA-256 of the canonical world checkpoint.

Two runs are considered equivalent for a phase when their ``TurnTrace``
digests match. Later tick-graph phases reuse this oracle unchanged.

The canonical encoder keeps container and reference types explicit. It handles
``NodeRef`` (which subclasses ``int``), tuples, sets and frozensets, and
stringifies dictionary keys before sorting, so the digest does not depend on
dictionary insertion order or Python's set iteration order. Unknown values fail
loudly instead of silently falling back to ``repr``/``str``.

TG05 semantic oracle
--------------------
``step_trace`` hashes the canonical graph checkpoint byte-for-byte, including
node ids.  The threaded executor commits independent actor units concurrently,
so node ids (and the insertion order of a few logs) may differ from a serial
run even when every observable fact matches.  ``semantic_world_state`` and
``step_semantic_trace`` therefore hash a normalised ``world.export_state``
projection instead:

- the volatile ``id`` is dropped from ``utterances`` entries (it is the raw
  graph node id);
- ``events``, ``articles``, ``editions``, ``handovers``, ``proposals``,
  ``cases``, ``animals``, ``fences`` and ``enclosures`` are sorted by their
  canonical JSON, so log insertion order is irrelevant;
- every other field of the export is kept intact.

This proves *semantic* equivalence: proposals, results, errors, continuations,
actor/world observable state and counters match.  It deliberately does not
claim byte-identical graph node ids or internal list insertion order.  The
default ``step_trace``/``TurnTrace`` behaviour and digests are unchanged.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from typing import Any, Iterable

from .runtime import NodeRef


class TraceValueError(TypeError):
    """A value in the trace cannot be encoded deterministically."""


def _compact(value: Any) -> str:
    """A stable, compact JSON string for ordering sets and dictionary keys."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _key_text(key: Any) -> str:
    """Stringify a dictionary key without losing its type where possible."""
    if isinstance(key, str):
        return key
    return _compact(canonical(key, path=f"key:{key!r}"))


def canonical(value: Any, *, path: str = "value") -> Any:
    """Return a deterministic, JSON-safe representation of ``value``.

    Dict keys are stringified, dicts are left for ``json.dumps(sort_keys=True)``
    to order, and typed containers get explicit tags so a tuple never collides
    with a list and a set never depends on hash order.
    """
    # NodeRef subclasses int, so test it before the primitive integer branch.
    if isinstance(value, NodeRef):
        return {"$node_ref": int(value)}
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TraceValueError(f"non-finite float at {path}")
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = _key_text(key)
            if name in result:
                raise TraceValueError(
                    f"dictionary key collision after stringification at {path}: {name!r}")
            result[name] = canonical(item, path=f"{path}.{name}")
        return result
    if isinstance(value, list):
        return [canonical(item, path=f"{path}[{index}]")
                for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return {"$tuple": [canonical(item, path=f"{path}[{index}]")
                           for index, item in enumerate(value)]}
    if isinstance(value, (set, frozenset)):
        items = [canonical(item, path=f"{path}{{member}}") for item in value]
        items.sort(key=_compact)
        return {"$frozenset" if isinstance(value, frozenset) else "$set": items}
    if isinstance(value, (bytes, bytearray)):
        return {"$bytes": bytes(value).hex()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return canonical(to_dict(), path=path)
    if dataclasses.is_dataclass(value):
        return canonical(dataclasses.asdict(value), path=path)
    raise TraceValueError(f"unsupported trace value at {path}: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """The canonical JSON text used by every trace digest."""
    return _compact(canonical(value))


def value_digest(value: Any) -> str:
    """SHA-256 of the canonical encoding of one value."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utterance(value: Any) -> Any:
    """Normalise the two accepted utterance shapes to a canonical value."""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return canonical(to_dict())
    if isinstance(value, dict):
        return canonical(value)
    return canonical(str(value))


def _trace_fields(game) -> dict[str, Any]:
    """The turn fields common to the strict and semantic traces."""
    responses: dict[str, Any] = {}
    for actor, response in sorted(getattr(game, "last_responses", {}).items()):
        action = getattr(response, "major_action", None)
        responses[str(actor)] = {
            "action": None if action is None else str(action.action),
            "params": None if action is None else canonical(dict(action.params or {})),
            "reason": None if action is None else str(getattr(action, "reason", "")),
            "utterances": [_utterance(item)
                           for item in getattr(response, "utterances", []) or []],
            "waiting": bool(getattr(response, "waiting", False)),
        }

    continuations: dict[str, Any] = {}
    for actor, active in sorted(getattr(game, "_continuations", {}).items()):
        request = getattr(active, "request", None)
        continuations[str(actor)] = (
            None if request is None else canonical(request.to_dict()))

    return {
        "turn": int(game.world._turn),
        "order": [str(actor) for actor in getattr(game, "last_order", [])],
        "responses": responses,
        "results": {str(actor): bool(ok)
                    for actor, ok in sorted(getattr(game, "last_results", {}).items())},
        "errors": {str(actor): str(error)
                   for actor, error in sorted(getattr(game, "last_errors", {}).items())},
        "continuations": continuations,
    }


def step_trace(game) -> dict[str, Any]:
    """Record everything the equivalence oracle needs about the last turn.

    Call this after a successful ``game.step()``. It reads the game and the
    canonical world graph only; it never mutates either.  This is the strict
    oracle: its ``world_sha256`` covers the raw graph checkpoint, including
    node ids.
    """
    record = _trace_fields(game)
    record["world_sha256"] = value_digest(game.world.eng.to_checkpoint_dict())
    return record


# Projection lists whose internal insertion order is not part of the observable
# world.  Each is sorted by canonical JSON in ``semantic_world_state``.
_SORTED_EXPORT_LISTS = (
    "events", "articles", "editions", "handovers", "proposals", "cases",
    "animals", "fences", "enclosures",
)


def semantic_world_state(world) -> dict[str, Any]:
    """A normalised, node-id-free projection of ``world.export_state``.

    Node ids are an internal allocation detail: a threaded commit may mint the
    same logical nodes in a different order.  The projection removes only the
    utterance node id and sorts the log-like lists whose insertion order is not
    an observable fact.  Everything else in the export is preserved.
    """
    state = world.export_state(event_tail=None)
    utterances = state.get("utterances")
    if isinstance(utterances, list):
        state["utterances"] = [
            {key: value for key, value in entry.items() if key != "id"}
            if isinstance(entry, dict) else entry
            for entry in utterances
        ]
    for key in _SORTED_EXPORT_LISTS:
        entries = state.get(key)
        if isinstance(entries, list):
            state[key] = sorted(entries, key=canonical_json)
    return state


def semantic_step_trace(game) -> dict[str, Any]:
    """Record the last turn with the semantic (node-id-free) world digest."""
    record = _trace_fields(game)
    record["world_sha256"] = value_digest(semantic_world_state(game.world))
    return record


# A clearer alias used by the TG05 executor tests.
step_semantic_trace = semantic_step_trace


class TurnTrace:
    """An append-only sequence of turn records with a running SHA-256 digest."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self._hash = hashlib.sha256()

    def add(self, game) -> dict[str, Any]:
        """Record the turn just completed by ``game.step()``."""
        return self.add_record(step_trace(game))

    def add_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append an already-built record (used by tests and trace replay)."""
        normalised = canonical(record)
        self.records.append(normalised)
        self._hash.update(canonical_json(normalised).encode("utf-8"))
        self._hash.update(b"\n")
        return normalised

    @property
    def turns(self) -> int:
        return len(self.records)

    @property
    def digest(self) -> str:
        return self._hash.hexdigest()

    def hexdigest(self) -> str:
        return self.digest


def _join(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _first_diff_path(left: Any, right: Any, prefix: str = "") -> str:
    """The dotted/indexed path of the first differing value, or ``prefix``."""
    if type(left) is not type(right):
        return prefix or "value"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            path = _join(prefix, str(key))
            if key not in left or key not in right:
                return path
            if left[key] != right[key]:
                return _first_diff_path(left[key], right[key], path)
        return prefix or "value"
    if isinstance(left, list):
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            if left_item != right_item:
                return _first_diff_path(left_item, right_item, f"{prefix}[{index}]")
        if len(left) != len(right):
            return f"{prefix}[{min(len(left), len(right))}]"
        return prefix or "value"
    return prefix or "value"


def _records(trace: TurnTrace | Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(trace.records if isinstance(trace, TurnTrace) else trace)


def first_divergence(
        left: TurnTrace | Iterable[dict[str, Any]],
        right: TurnTrace | Iterable[dict[str, Any]],
) -> tuple[int, str] | None:
    """Return ``(turn, field_path)`` for the first difference, or ``None``.

    When one trace is a strict prefix of the other, the turn is the first extra
    record's turn and the path is ``"<missing>"``.
    """
    left_records, right_records = _records(left), _records(right)
    for index, (left_record, right_record) in enumerate(zip(left_records, right_records)):
        if left_record != right_record:
            turn = int(left_record.get("turn", right_record.get("turn", index + 1)))
            return turn, _first_diff_path(left_record, right_record)
    if len(left_records) != len(right_records):
        extra = (right_records[len(left_records)] if len(left_records) < len(right_records)
                 else left_records[len(right_records)])
        return int(extra.get("turn", min(len(left_records), len(right_records)) + 1)), "<missing>"
    return None
