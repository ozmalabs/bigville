"""Pure bundle, result and acknowledgement protocol for distributed ticks.

This is NB01 of the distributed-bundles plan: the *shape* of the work a future
worker would receive, not a scheduler and not a distribution system.  Nothing
here imports the game or the world module, and importing this module changes no
existing behaviour.  The only Bigville type it uses is the frozen ``Resource``
pair from :mod:`worlds.tick_graph`.

The protocol is transport-neutral:

```text
Bundle -> BundleResult -> BundleAck
```

``LocalBundleTransport`` runs a caller-supplied executor in-process and is the
reference implementation.  A process/socket transport implements the same
``dispatch``/``acknowledge``/``replay`` methods without changing the game.

Determinism
-----------

All protocol objects are frozen dataclasses with JSON ``to_dict``/``from_dict``
round trips.  ``to_dict`` preserves list order because bundle and effect order
are meaningful.  ``canonical_dict`` sorts operations, resources and effects so
checksums and deduplication do not depend on construction order.  Parameter
mappings are normalised through a JSON-safe encoder at construction time and
stored read-only, so a tuple becomes a list exactly once and a
``MappingProxyType`` can never be mutated after the bundle was checksummed.
"""
from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from worlds.tick_graph import Resource


__all__ = [
    "Bundle",
    "BundleAck",
    "BundleOperation",
    "BundleResult",
    "BundleTransport",
    "BundleValueError",
    "ExecutionNamespace",
    "LocalBundleTransport",
    "QualifiedId",
    "canonical_json",
    "canonical_value",
]

RESULT_STATUSES = frozenset({"ok", "refused", "retry", "error"})
ACK_OUTCOMES = frozenset({"committed", "retry", "rejected"})


class BundleValueError(TypeError):
    """A value cannot be represented deterministically in the protocol."""


# --------------------------------------------------------------------------- helpers


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _require_str(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if value < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return int(value)


def _require_mapping(value: Any, field: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return value


def _read_mapping(value: Any, field: str, keys: tuple[str, ...]) -> Mapping[str, Any]:
    """Validate a serialized protocol object, rejecting missing/extra keys."""
    mapping = _require_mapping(value, field)
    missing = [key for key in keys if key not in mapping]
    extra = [key for key in mapping if key not in keys]
    if missing:
        raise ValueError(f"{field} missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"{field} has unknown keys: {', '.join(sorted(map(str, extra)))}")
    return mapping


def canonical_value(value: Any, *, path: str = "value") -> Any:
    """Return a deterministic, JSON-safe value.

    Plain JSON primitives are copied, ``Resource`` and protocol objects use
    their ``to_dict``, tuples become lists, and mapping keys must be strings.
    Sets, arbitrary objects and non-finite floats are rejected: an effect or
    parameter must not depend on hash order or on a live Python object.

    ``NodeRef`` is an ``int`` subclass, so it is deliberately normalised to a
    plain ``int`` here rather than leaking a runtime type into the wire form.
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BundleValueError(f"non-finite float at {path}")
        return float(value)
    if isinstance(value, Resource):
        return canonical_value(value.to_dict(), path=path)
    if isinstance(value, (QualifiedId, ExecutionNamespace)):
        return canonical_value(value.to_dict(), path=path)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise BundleValueError(
                    f"mapping key at {path} must be a string, got {type(key).__name__}")
            if key in result:
                raise BundleValueError(f"duplicate mapping key at {path}: {key!r}")
            result[key] = canonical_value(item, path=f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [canonical_value(item, path=f"{path}[{index}]")
                for index, item in enumerate(value)]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict) and not isinstance(value, type):
        return canonical_value(to_dict(), path=path)
    raise BundleValueError(
        f"unsupported protocol value at {path}: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Compact canonical JSON text for checksums and deduplication."""
    return _compact(canonical_value(value))


def _resource_tuple(value: Any, field: str) -> tuple[Resource, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be a sequence of Resource values")
    result = tuple(value)
    for resource in result:
        if not isinstance(resource, Resource):
            raise ValueError(f"{field} contains a non-Resource value")
    return result


def _sequence_tuple(value: Any, field: str) -> tuple:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be a tuple or list")
    normalised = canonical_value(list(value), path=field)
    if not isinstance(normalised, list):
        raise ValueError(f"{field} must be a sequence")
    return tuple(normalised)


def _resource_sort_key(resource: Resource) -> str:
    return canonical_json(resource.to_dict())


def _sorted_resources(resources: tuple[Resource, ...]) -> list[dict[str, Any]]:
    return [resource.to_dict()
            for resource in sorted(resources, key=_resource_sort_key)]


def _sort_component(value: Any) -> tuple[int, Any]:
    """A total-order wrapper for tie-break components of mixed types."""
    if isinstance(value, bool) or isinstance(value, int):
        return (0, int(value))
    if isinstance(value, float):
        return (0, value)
    if isinstance(value, str):
        return (1, value)
    return (2, canonical_json(value))


# --------------------------------------------------------------------------- namespace


_NAME_RE = re.compile(
    r"^r(?P<run_id>[^/#]+)/t(?P<tick>0|[1-9][0-9]*)/"
    r"(?P<executor>[^/#]+)/s(?P<shard>0|[1-9][0-9]*)/"
    r"b(?P<bundle_seq>0|[1-9][0-9]*)/a(?P<attempt>[1-9][0-9]*)$")


@dataclass(frozen=True)
class ExecutionNamespace:
    """The identity of one bundle execution, including its retry attempt.

    The canonical text form is
    ``r<run_id>/t<tick>/<executor>/s<shard>/b<bundle_seq>/a<attempt>``.
    A retry keeps the same namespace (and therefore the same node-allocation
    identity); ``attempt`` above one is an explicit branch, not an implicit
    retry.
    """

    run_id: str
    executor: str
    shard: int
    tick: int
    bundle_seq: int
    attempt: int = 1

    def __post_init__(self) -> None:
        run_id = _require_str(self.run_id, "run_id")
        executor = _require_str(self.executor, "executor")
        if "/" in run_id:
            raise ValueError("run_id must not contain '/'")
        if "/" in executor:
            raise ValueError("executor must not contain '/'")
        if "#" in run_id:
            raise ValueError("run_id must not contain '#'")
        if "#" in executor:
            raise ValueError("executor must not contain '#'")
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "executor", executor)
        object.__setattr__(self, "shard", _require_int(self.shard, "shard"))
        object.__setattr__(self, "tick", _require_int(self.tick, "tick"))
        object.__setattr__(self, "bundle_seq",
                           _require_int(self.bundle_seq, "bundle_seq"))
        object.__setattr__(self, "attempt",
                           _require_int(self.attempt, "attempt", minimum=1))

    @property
    def name(self) -> str:
        """The stable qualified namespace string."""
        return (f"r{self.run_id}/t{self.tick}/{self.executor}/"
                f"s{self.shard}/b{self.bundle_seq}/a{self.attempt}")

    @classmethod
    def parse(cls, name: Any) -> "ExecutionNamespace":
        """Parse and strictly validate a namespace name.

        A non-canonical spelling (for example ``t042`` or a trailing slash) is
        rejected rather than silently normalised.
        """
        name = _require_str(name, "namespace name")
        match = _NAME_RE.match(name)
        if match is None:
            raise ValueError(f"invalid execution namespace: {name!r}")
        namespace = cls(
            run_id=match.group("run_id"),
            executor=match.group("executor"),
            shard=int(match.group("shard")),
            tick=int(match.group("tick")),
            bundle_seq=int(match.group("bundle_seq")),
            attempt=int(match.group("attempt")),
        )
        if namespace.name != name:
            raise ValueError(f"non-canonical execution namespace: {name!r}")
        return namespace

    @classmethod
    def is_valid_name(cls, name: Any) -> bool:
        try:
            cls.parse(name)
        except (TypeError, ValueError):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "executor": self.executor,
            "shard": self.shard,
            "tick": self.tick,
            "bundle_seq": self.bundle_seq,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ExecutionNamespace":
        keys = ("run_id", "executor", "shard", "tick", "bundle_seq", "attempt")
        data = _read_mapping(value, "namespace", keys)
        return cls(
            run_id=data["run_id"],
            executor=data["executor"],
            shard=data["shard"],
            tick=data["tick"],
            bundle_seq=data["bundle_seq"],
            attempt=data["attempt"],
        )


@dataclass(frozen=True)
class QualifiedId:
    """A local integer id qualified by the namespace that allocated it.

    ``NodeRef`` stays a plain int in the graph.  This pair is only the wire and
    provenance form, never a replacement for the graph's integer id type.
    """

    namespace: str
    local_id: int

    def __post_init__(self) -> None:
        namespace = _require_str(self.namespace, "namespace")
        if "#" in namespace:
            raise ValueError("namespace must not contain '#'")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "local_id",
                           _require_int(self.local_id, "local_id"))

    def __str__(self) -> str:
        return f"{self.namespace}#{self.local_id}"

    @classmethod
    def parse(cls, value: Any) -> "QualifiedId":
        value = _require_str(value, "qualified id")
        if "#" not in value:
            raise ValueError(f"invalid qualified id: {value!r}")
        namespace, _, local_id = value.rpartition("#")
        if not namespace or not local_id.isdigit():
            raise ValueError(f"invalid qualified id: {value!r}")
        return cls(namespace=namespace, local_id=int(local_id))

    def to_dict(self) -> dict[str, Any]:
        return {"namespace": self.namespace, "local_id": self.local_id}

    @classmethod
    def from_dict(cls, value: Any) -> "QualifiedId":
        data = _read_mapping(value, "qualified_id", ("namespace", "local_id"))
        return cls(namespace=data["namespace"], local_id=data["local_id"])


# --------------------------------------------------------------------------- operation


@dataclass(frozen=True)
class BundleOperation:
    """One operation inside a bundle, with its declared read/write sets.

    ``params`` is normalised to JSON-safe values and stored read-only.
    ``tiebreak`` is the deterministic order hint copied from the tick graph.
    """

    op_id: str
    actor: str | None
    kind: str
    params: Mapping[str, Any]
    reads: tuple[Resource, ...]
    writes: tuple[Resource, ...]
    tiebreak: tuple

    def __post_init__(self) -> None:
        object.__setattr__(self, "op_id", _require_str(self.op_id, "op_id"))
        if self.actor is not None:
            object.__setattr__(self, "actor",
                               _require_str(self.actor, "actor"))
        object.__setattr__(self, "kind", _require_str(self.kind, "kind"))
        params = _require_mapping(self.params, "params")
        normalised = canonical_value(dict(params), path="params")
        if not isinstance(normalised, dict):
            raise ValueError("params must normalise to a mapping")
        object.__setattr__(self, "params", MappingProxyType(normalised))
        object.__setattr__(self, "reads",
                           _resource_tuple(self.reads, "reads"))
        object.__setattr__(self, "writes",
                           _resource_tuple(self.writes, "writes"))
        object.__setattr__(self, "tiebreak",
                           _sequence_tuple(self.tiebreak, "tiebreak"))

    def sort_key(self) -> tuple:
        """The deterministic intra-bundle operation order."""
        return (
            tuple(_sort_component(item) for item in self.tiebreak),
            str(self.actor or ""),
            self.op_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "actor": self.actor,
            "kind": self.kind,
            "params": canonical_value(dict(self.params), path="params"),
            "reads": [resource.to_dict() for resource in self.reads],
            "writes": [resource.to_dict() for resource in self.writes],
            "tiebreak": canonical_value(list(self.tiebreak), path="tiebreak"),
        }

    def canonical_dict(self) -> dict[str, Any]:
        """Order-insensitive operation form for checksums."""
        return {
            "op_id": self.op_id,
            "actor": self.actor,
            "kind": self.kind,
            "params": canonical_value(dict(self.params), path="params"),
            "reads": _sorted_resources(self.reads),
            "writes": _sorted_resources(self.writes),
            "tiebreak": canonical_value(list(self.tiebreak), path="tiebreak"),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BundleOperation":
        keys = ("op_id", "actor", "kind", "params", "reads", "writes",
                "tiebreak")
        data = _read_mapping(value, "operation", keys)
        reads = data["reads"]
        writes = data["writes"]
        if not isinstance(reads, (list, tuple)):
            raise ValueError("operation reads must be a list")
        if not isinstance(writes, (list, tuple)):
            raise ValueError("operation writes must be a list")
        return cls(
            op_id=data["op_id"],
            actor=data["actor"],
            kind=data["kind"],
            params=data["params"],
            reads=tuple(_resource_from_dict(item, "operation read")
                        for item in reads),
            writes=tuple(_resource_from_dict(item, "operation write")
                         for item in writes),
            tiebreak=data["tiebreak"],
        )


def _resource_from_dict(value: Any, field: str) -> Resource:
    data = _read_mapping(value, field, ("kind", "key"))
    return Resource(kind=data["kind"], key=data["key"])


# --------------------------------------------------------------------------- bundle


@dataclass(frozen=True)
class Bundle:
    """One dispatchable unit of work.

    ``reads`` and ``writes`` are the bundle-level declared sets; every
    operation's own sets must be subsets of them.  They may be a strict
    superset because a shard group carries the union of its components.
    """

    bundle_id: str
    namespace: ExecutionNamespace
    run_id: str
    tick: int
    shard: int
    base_version: int
    operations: tuple[BundleOperation, ...]
    reads: tuple[Resource, ...]
    writes: tuple[Resource, ...]
    tiebreak: tuple

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id",
                           _require_str(self.bundle_id, "bundle_id"))
        if not isinstance(self.namespace, ExecutionNamespace):
            raise ValueError("namespace must be an ExecutionNamespace")
        run_id = _require_str(self.run_id, "run_id")
        if run_id != self.namespace.run_id:
            raise ValueError("run_id does not match namespace.run_id")
        tick = _require_int(self.tick, "tick")
        shard = _require_int(self.shard, "shard")
        if tick != self.namespace.tick:
            raise ValueError("tick does not match namespace.tick")
        if shard != self.namespace.shard:
            raise ValueError("shard does not match namespace.shard")
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "shard", shard)
        object.__setattr__(self, "base_version",
                           _require_int(self.base_version, "base_version"))
        if not isinstance(self.operations, (tuple, list)):
            raise ValueError("operations must be a sequence")
        operations = tuple(self.operations)
        op_ids: set[str] = set()
        for operation in operations:
            if not isinstance(operation, BundleOperation):
                raise ValueError("operations contains a non-BundleOperation")
            if operation.op_id in op_ids:
                raise ValueError(f"duplicate operation id: {operation.op_id!r}")
            op_ids.add(operation.op_id)
        object.__setattr__(self, "operations", operations)
        reads = _resource_tuple(self.reads, "reads")
        writes = _resource_tuple(self.writes, "writes")
        read_set, write_set = set(reads), set(writes)
        for operation in operations:
            if not set(operation.reads) <= read_set:
                raise ValueError(
                    f"operation {operation.op_id!r} reads outside bundle reads")
            if not set(operation.writes) <= write_set:
                raise ValueError(
                    f"operation {operation.op_id!r} writes outside bundle writes")
        object.__setattr__(self, "reads", reads)
        object.__setattr__(self, "writes", writes)
        object.__setattr__(self, "tiebreak",
                           _sequence_tuple(self.tiebreak, "tiebreak"))

    @property
    def dedupe_key(self) -> str:
        """The idempotence key: a bundle id is unique within a run."""
        return self.bundle_id

    def ordered_operations(self) -> tuple[BundleOperation, ...]:
        """Operations in deterministic intra-bundle order."""
        return tuple(sorted(self.operations,
                            key=lambda operation: operation.sort_key()))

    def input_dict(self) -> dict[str, Any]:
        """The checksum input: no executor-local allocation provenance."""
        return {
            "namespace": self.namespace.to_dict(),
            "base_version": self.base_version,
            "operations": [operation.canonical_dict()
                           for operation in self.ordered_operations()],
            "reads": _sorted_resources(self.reads),
            "writes": _sorted_resources(self.writes),
        }

    def canonical_dict(self) -> dict[str, Any]:
        """The full bundle in deterministic, order-insensitive form."""
        return {"bundle_id": self.bundle_id, **self.input_dict()}

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "namespace": self.namespace.to_dict(),
            "run_id": self.run_id,
            "tick": self.tick,
            "shard": self.shard,
            "base_version": self.base_version,
            "operations": [operation.to_dict()
                           for operation in self.operations],
            "reads": [resource.to_dict() for resource in self.reads],
            "writes": [resource.to_dict() for resource in self.writes],
            "tiebreak": canonical_value(list(self.tiebreak), path="tiebreak"),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Bundle":
        keys = ("bundle_id", "namespace", "run_id", "tick", "shard",
                "base_version", "operations", "reads", "writes", "tiebreak")
        data = _read_mapping(value, "bundle", keys)
        operations = data["operations"]
        reads = data["reads"]
        writes = data["writes"]
        if not isinstance(operations, (list, tuple)):
            raise ValueError("bundle operations must be a list")
        if not isinstance(reads, (list, tuple)):
            raise ValueError("bundle reads must be a list")
        if not isinstance(writes, (list, tuple)):
            raise ValueError("bundle writes must be a list")
        return cls(
            bundle_id=data["bundle_id"],
            namespace=ExecutionNamespace.from_dict(data["namespace"]),
            run_id=data["run_id"],
            tick=data["tick"],
            shard=data["shard"],
            base_version=data["base_version"],
            operations=tuple(BundleOperation.from_dict(item)
                             for item in operations),
            reads=tuple(_resource_from_dict(item, "bundle read")
                        for item in reads),
            writes=tuple(_resource_from_dict(item, "bundle write")
                         for item in writes),
            tiebreak=data["tiebreak"],
        )


# --------------------------------------------------------------------------- result


@dataclass(frozen=True)
class BundleResult:
    """The worker's reply to one bundle dispatch.

    ``effects`` are plain JSON-safe deltas in this phase; NB04 may replace them
    with the existing actor-result tuples while the world is still shared.
    ``created_ids`` must carry this result's namespace.  The two checksums are
    supplied by the checksum layer (NB02); the protocol only requires them to be
    non-empty stable strings.
    """

    bundle_id: str
    namespace: ExecutionNamespace
    base_version: int
    status: str
    effects: tuple[Mapping[str, Any], ...]
    created_ids: tuple[QualifiedId, ...]
    result: tuple[tuple[Any, ...], ...]
    output_sha: str
    execution_sha: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id",
                           _require_str(self.bundle_id, "bundle_id"))
        if not isinstance(self.namespace, ExecutionNamespace):
            raise ValueError("namespace must be an ExecutionNamespace")
        object.__setattr__(self, "base_version",
                           _require_int(self.base_version, "base_version"))
        status = _require_str(self.status, "status")
        if status not in RESULT_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(RESULT_STATUSES)}, got {status!r}")
        object.__setattr__(self, "status", status)

        if not isinstance(self.effects, (tuple, list)):
            raise ValueError("effects must be a sequence of mappings")
        effects: list[Mapping[str, Any]] = []
        for index, effect in enumerate(self.effects):
            mapping = _require_mapping(effect, f"effects[{index}]")
            normalised = canonical_value(dict(mapping),
                                         path=f"effects[{index}]")
            if not isinstance(normalised, dict):
                raise ValueError(f"effects[{index}] must be a mapping")
            effects.append(MappingProxyType(normalised))
        object.__setattr__(self, "effects", tuple(effects))

        if not isinstance(self.created_ids, (tuple, list)):
            raise ValueError("created_ids must be a sequence")
        created_ids = tuple(self.created_ids)
        for qualified in created_ids:
            if not isinstance(qualified, QualifiedId):
                raise ValueError("created_ids contains a non-QualifiedId")
            if qualified.namespace != self.namespace.name:
                raise ValueError(
                    "created id namespace does not match result namespace")
        object.__setattr__(self, "created_ids", created_ids)

        if not isinstance(self.result, (tuple, list)):
            raise ValueError("result must be a sequence of rows")
        rows: list[tuple[Any, ...]] = []
        for index, row in enumerate(self.result):
            if not isinstance(row, (tuple, list)) or len(row) != 3:
                raise ValueError(
                    f"result[{index}] must be an (actor, applied, error) row")
            actor, applied, error = row
            if actor is not None:
                actor = _require_str(actor, f"result[{index}].actor")
            if not isinstance(applied, bool):
                raise ValueError(f"result[{index}].applied must be a bool")
            if error is not None:
                error = _require_str(error, f"result[{index}].error")
            rows.append((actor, bool(applied), error))
        object.__setattr__(self, "result", tuple(rows))

        object.__setattr__(self, "output_sha",
                           _require_str(self.output_sha, "output_sha"))
        object.__setattr__(self, "execution_sha",
                           _require_str(self.execution_sha, "execution_sha"))
        object.__setattr__(self, "reason",
                           _require_str(self.reason, "reason", allow_empty=True))

    @property
    def succeeded(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "namespace": self.namespace.to_dict(),
            "base_version": self.base_version,
            "status": self.status,
            "effects": [canonical_value(dict(effect),
                                        path=f"effects[{index}]")
                        for index, effect in enumerate(self.effects)],
            "created_ids": [qualified.to_dict()
                            for qualified in self.created_ids],
            "result": [list(row) for row in self.result],
            "output_sha": self.output_sha,
            "execution_sha": self.execution_sha,
            "reason": self.reason,
        }

    def canonical_dict(self) -> dict[str, Any]:
        """Order-insensitive result form for output checksums."""
        effects = sorted((canonical_value(dict(effect),
                                          path=f"effects[{index}]")
                          for index, effect in enumerate(self.effects)),
                         key=canonical_json)
        created_ids = sorted((qualified.to_dict()
                              for qualified in self.created_ids),
                             key=canonical_json)
        rows = sorted((list(row) for row in self.result), key=canonical_json)
        return {
            "bundle_id": self.bundle_id,
            "namespace": self.namespace.to_dict(),
            "base_version": self.base_version,
            "status": self.status,
            "effects": effects,
            "created_ids": created_ids,
            "result": rows,
            "output_sha": self.output_sha,
            "execution_sha": self.execution_sha,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BundleResult":
        keys = ("bundle_id", "namespace", "base_version", "status", "effects",
                "created_ids", "result", "output_sha", "execution_sha",
                "reason")
        data = _read_mapping(value, "result", keys)
        effects = data["effects"]
        created_ids = data["created_ids"]
        rows = data["result"]
        if not isinstance(effects, (list, tuple)):
            raise ValueError("result effects must be a list")
        if not isinstance(created_ids, (list, tuple)):
            raise ValueError("result created_ids must be a list")
        if not isinstance(rows, (list, tuple)):
            raise ValueError("result rows must be a list")
        return cls(
            bundle_id=data["bundle_id"],
            namespace=ExecutionNamespace.from_dict(data["namespace"]),
            base_version=data["base_version"],
            status=data["status"],
            effects=tuple(effects),
            created_ids=tuple(QualifiedId.from_dict(item)
                              for item in created_ids),
            result=tuple(tuple(row) if isinstance(row, (list, tuple)) else row
                         for row in rows),
            output_sha=data["output_sha"],
            execution_sha=data["execution_sha"],
            reason=data["reason"],
        )


# --------------------------------------------------------------------------- ack


@dataclass(frozen=True)
class BundleAck:
    """The coordinator's confirmation that a result was committed or rejected.

    A result is invisible until acked.  ``committed_version`` is the version the
    coordinator wrote; it must be ``None`` for retry/rejected outcomes and at
    least ``base_version`` for a committed outcome.
    """

    bundle_id: str
    base_version: int
    outcome: str
    committed_version: int | None
    execution_sha: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id",
                           _require_str(self.bundle_id, "bundle_id"))
        object.__setattr__(self, "base_version",
                           _require_int(self.base_version, "base_version"))
        outcome = _require_str(self.outcome, "outcome")
        if outcome not in ACK_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(ACK_OUTCOMES)}, got {outcome!r}")
        object.__setattr__(self, "outcome", outcome)
        if outcome == "committed":
            if self.committed_version is None:
                raise ValueError("committed ack requires committed_version")
            committed = _require_int(self.committed_version,
                                     "committed_version")
            if committed < self.base_version:
                raise ValueError(
                    "committed_version must be >= base_version")
        else:
            if self.committed_version is not None:
                raise ValueError(
                    "committed_version must be None for a non-committed ack")
            committed = None
        object.__setattr__(self, "committed_version", committed)
        object.__setattr__(self, "execution_sha",
                           _require_str(self.execution_sha, "execution_sha"))
        object.__setattr__(self, "reason",
                           _require_str(self.reason, "reason", allow_empty=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "base_version": self.base_version,
            "outcome": self.outcome,
            "committed_version": self.committed_version,
            "execution_sha": self.execution_sha,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "BundleAck":
        keys = ("bundle_id", "base_version", "outcome", "committed_version",
                "execution_sha", "reason")
        data = _read_mapping(value, "ack", keys)
        return cls(
            bundle_id=data["bundle_id"],
            base_version=data["base_version"],
            outcome=data["outcome"],
            committed_version=data["committed_version"],
            execution_sha=data["execution_sha"],
            reason=data["reason"],
        )


# --------------------------------------------------------------------------- transport


@runtime_checkable
class BundleTransport(Protocol):
    """The transport seam; no game or world type appears in the signatures."""

    def dispatch(self, bundle: Bundle) -> BundleResult:
        ...

    def acknowledge(self, ack: BundleAck) -> None:
        ...

    def replay(self, bundle_id: str) -> BundleResult | None:
        ...


class LocalBundleTransport:
    """In-process reference transport with an idempotent replay cache.

    ``executor`` is any callable ``(Bundle) -> BundleResult``.  The transport
    calls it at most once per ``bundle_id``: a duplicate dispatch returns the
    exact cached object.  A per-bundle in-flight event lets distinct bundle ids
    execute concurrently while a duplicate of one id waits for its leader.

    If the executor raises, the exception reaches the caller and **nothing** is
    cached.  That is intentional: an infrastructural failure is not a
    deterministic bundle result, and the coordinator/user must decide whether
    to retry.  A subsequent dispatch of the same bundle calls the executor
    again.

    ``results`` preloads the replay cache, mainly for a coordinator replaying a
    durable log or for tests.  Preloaded entries are not counted in
    ``dispatch_order`` and never call the executor.
    """

    def __init__(self, executor: Callable[[Bundle], BundleResult], *,
                 results: Mapping[str, BundleResult] | None = None) -> None:
        if not callable(executor):
            raise ValueError("executor must be callable")
        self._executor = executor
        self._lock = threading.RLock()
        self._results: dict[str, BundleResult] = {}
        self._acks: dict[str, BundleAck] = {}
        self._dispatch_order: list[str] = []
        self._inflight: dict[str, tuple[threading.Event, int]] = {}
        for bundle_id, result in (results or {}).items():
            if not isinstance(bundle_id, str) or not bundle_id:
                raise ValueError("preloaded results need non-empty bundle ids")
            if not isinstance(result, BundleResult):
                raise ValueError("preloaded results must be BundleResult values")
            if result.bundle_id != bundle_id:
                raise ValueError(
                    "preloaded result key does not match result.bundle_id")
            self._results[bundle_id] = result

    # -- protocol --------------------------------------------------------

    def dispatch(self, bundle: Bundle) -> BundleResult:
        if not isinstance(bundle, Bundle):
            raise TypeError("dispatch expects a Bundle")
        with self._lock:
            cached = self._results.get(bundle.bundle_id)
            if cached is not None:
                self._check_result(bundle, cached)
                return cached
            entry = self._inflight.get(bundle.bundle_id)
            leader = entry is None
            if leader:
                pending = threading.Event()
                self._inflight[bundle.bundle_id] = (
                    pending, threading.get_ident())
                self._dispatch_order.append(bundle.bundle_id)
            else:
                pending, owner = entry

        if not leader:
            if owner == threading.get_ident():
                raise RuntimeError(
                    "re-entrant dispatch of the same bundle id")
            # Another thread is executing this exact bundle.  Wait for it, then
            # return the cached result; if that attempt failed, retry as leader.
            pending.wait()
            with self._lock:
                cached = self._results.get(bundle.bundle_id)
                if cached is not None:
                    self._check_result(bundle, cached)
                    return cached
            return self.dispatch(bundle)

        try:
            result = self._executor(bundle)
            if not isinstance(result, BundleResult):
                raise ValueError("executor must return a BundleResult")
            self._check_result(bundle, result)
        except BaseException:
            with self._lock:
                self._inflight.pop(bundle.bundle_id, None)
                try:
                    self._dispatch_order.remove(bundle.bundle_id)
                except ValueError:
                    pass
            pending.set()
            raise

        with self._lock:
            self._results[bundle.bundle_id] = result
            self._inflight.pop(bundle.bundle_id, None)
        pending.set()
        return result

    def acknowledge(self, ack: BundleAck) -> None:
        if not isinstance(ack, BundleAck):
            raise TypeError("acknowledge expects a BundleAck")
        with self._lock:
            result = self._results.get(ack.bundle_id)
            if result is None:
                raise ValueError(
                    f"cannot acknowledge unknown bundle: {ack.bundle_id!r}")
            if ack.base_version != result.base_version:
                raise ValueError(
                    "ack base_version does not match the dispatched result")
            if ack.execution_sha != result.execution_sha:
                raise ValueError(
                    "ack execution_sha does not match the dispatched result")
            existing = self._acks.get(ack.bundle_id)
            if existing is not None and existing != ack:
                raise ValueError(
                    f"conflicting ack for bundle: {ack.bundle_id!r}")
            self._acks[ack.bundle_id] = ack

    def replay(self, bundle_id: str) -> BundleResult | None:
        with self._lock:
            return self._results.get(bundle_id)

    # -- inspection ------------------------------------------------------

    @staticmethod
    def _check_result(bundle: Bundle, result: BundleResult) -> None:
        if result.bundle_id != bundle.bundle_id:
            raise ValueError("result bundle_id does not match the bundle")
        if result.namespace != bundle.namespace:
            raise ValueError("result namespace does not match the bundle")
        if result.base_version != bundle.base_version:
            raise ValueError("result base_version does not match the bundle")

    @property
    def dispatch_order(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._dispatch_order)

    def acknowledgement(self, bundle_id: str) -> BundleAck | None:
        with self._lock:
            return self._acks.get(bundle_id)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic audit form: dispatch order plus sorted result/ack maps."""
        with self._lock:
            return {
                "dispatch_order": list(self._dispatch_order),
                "results": {
                    bundle_id: self._results[bundle_id].to_dict()
                    for bundle_id in sorted(self._results)
                },
                "acks": {
                    bundle_id: self._acks[bundle_id].to_dict()
                    for bundle_id in sorted(self._acks)
                },
            }
