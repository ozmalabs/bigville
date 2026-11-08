"""Bigville's small, dependency-free graph data runtime.

The village uses a typed graph as its durable state boundary. Cognition
providers may generate graph data; world code remains responsible for
admissibility and physical effects.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import math
import threading
from typing import Any, Iterable, Iterator, Mapping


# TG05: one process-wide re-entrant lock guards the canonical graph's internal
# containers.  It is module level (not per graph) so the lock is never written
# into a checkpoint or copied with a world; every BigvilleGraph in process
# shares it.  RLock is required because public helpers call one another (for
# example ``load_seed_manifest`` calls ``nodes`` and ``add_node``).
_GRAPH_LOCK = threading.RLock()

# NB03: the execution namespace that is creating graph nodes right now.
#
# A ``ContextVar`` (rather than a plain module global) keeps concurrent context
# workers, threads and nested graphs isolated: each thread/task gets its own
# binding and ``execution_namespace`` restores the previous token on exit.  A
# resident mind's graph shares this variable with the world graph on purpose --
# anything a bundle creates while its namespace is active is attributed to that
# bundle, whichever graph receives the node.
DEFAULT_ORIGIN = "unqualified"
_CURRENT_ORIGIN: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bigville_graph_origin", default=None)


class NodeRef(int):
    """An integer node identifier with the compatibility ``.value`` view."""

    @property
    def value(self) -> int:
        return int(self)


@dataclass
class _Node:
    type: str
    attrs: dict[str, Any]
    origin: str = DEFAULT_ORIGIN


def _checkpoint_encode(value: Any, path: str) -> Any:
    """Encode supported graph values with explicit container/type tags."""
    # NodeRef subclasses int, so its identity tag must precede primitive ints.
    if isinstance(value, NodeRef):
        return {"$type": "node_ref", "value": int(value)}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"non-finite graph value at {path}")
        return value
    if isinstance(value, dict):
        items = [[_checkpoint_encode(key, path + ".key"),
                  _checkpoint_encode(item, path + ".value")]
                 for key, item in value.items()]
        return {"$type": "dict", "items": items}
    if isinstance(value, list):
        return {"$type": "list", "items": [
            _checkpoint_encode(item, f"{path}[{index}]")
            for index, item in enumerate(value)]}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [
            _checkpoint_encode(item, f"{path}[{index}]")
            for index, item in enumerate(value)]}
    if isinstance(value, (set, frozenset)):
        items = [_checkpoint_encode(item, path + "{member}") for item in value]
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return {"$type": "frozenset" if isinstance(value, frozenset) else "set",
                "items": items}
    raise TypeError(f"unsupported graph value at {path}: {type(value).__name__}")


def _checkpoint_decode(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite checkpoint number at {path}")
        return value
    if not isinstance(value, dict) or set(value) != {"$type", "items"} and set(value) != {"$type", "value"}:
        raise ValueError(f"invalid typed graph value at {path}")
    tag = value["$type"]
    if tag == "node_ref" and set(value) == {"$type", "value"}:
        node_id = value["value"]
        if type(node_id) is not int:
            raise ValueError(f"invalid NodeRef at {path}")
        return NodeRef(node_id)
    if "items" not in value or not isinstance(value["items"], list):
        raise ValueError(f"invalid {tag!r} graph container at {path}")
    items = value["items"]
    if tag == "list":
        return [_checkpoint_decode(item, f"{path}[{index}]")
                for index, item in enumerate(items)]
    if tag == "tuple":
        return tuple(_checkpoint_decode(item, f"{path}[{index}]")
                     for index, item in enumerate(items))
    if tag in {"set", "frozenset"}:
        decoded = [_checkpoint_decode(item, path + "{member}") for item in items]
        try:
            return frozenset(decoded) if tag == "frozenset" else set(decoded)
        except TypeError as exc:
            raise ValueError(f"unhashable member in {tag} at {path}") from exc
    if tag == "dict":
        result = {}
        for index, pair in enumerate(items):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"invalid dict entry at {path}[{index}]")
            key = _checkpoint_decode(pair[0], path + ".key")
            item = _checkpoint_decode(pair[1], path + ".value")
            try:
                if key in result:
                    raise ValueError(f"duplicate dictionary key at {path}")
                result[key] = item
            except TypeError as exc:
                raise ValueError(f"unhashable dictionary key at {path}") from exc
        return result
    raise ValueError(f"unknown typed graph value {tag!r} at {path}")


def _copy_graph_value(value: Any, path: str) -> Any:
    """Snapshot a supported graph value through the checkpoint encoding.

    The round trip both validates that the value is replayable and detaches it
    from a caller-owned mutable container.  ``NodeRef`` identity is preserved.
    """
    return _checkpoint_decode(_checkpoint_encode(value, path), path)


def _require_plain_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _require_plain_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


@dataclass
class GraphDelta:
    """The replayable graph mutations produced by one execution scope.

    DR03: a bundle executor records the mutations it makes into a
    ``GraphDelta``.  The delta is a strict, JSON-safe value (every non-primitive
    graph value uses the checkpoint's typed encoding) with two views:

    * the categorised lists (``nodes_added``, ``nodes_removed``, ...) for
      inspection, checksums and stable summaries;
    * ``operations``, the exact mutation order used by :meth:`apply_to` and
      :meth:`to_effects` so a remove/re-add of the same edge or attr replays
      correctly.

    ``operations`` is populated by :meth:`BigvilleGraph.record_changes` and is
    also serialized by :meth:`to_dict`.  A delta constructed by hand from only
    the categorised lists is applied in the documented canonical phase order:
    added nodes, added edges, attr writes, removed edges, removed nodes.
    """

    base_revision: int = 0
    end_revision: int = 0
    nodes_added: list[tuple[int, str, dict[str, Any], str]] = field(
        default_factory=list)
    nodes_removed: list[int] = field(default_factory=list)
    edges_added: list[tuple[int, str, int]] = field(default_factory=list)
    edges_removed: list[tuple[int, str, int]] = field(default_factory=list)
    attrs: list[tuple[int, str, Any, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)

    # -- recording -------------------------------------------------------

    def _note_add_node(self, node: int, type_name: str,
                       attrs: dict[str, Any], origin: str) -> None:
        self.nodes_added.append((int(node), str(type_name), attrs, str(origin)))
        self.operations.append({
            "op": "add_node", "node": int(node), "type": str(type_name),
            "attrs": attrs, "origin": str(origin),
        })

    def _note_remove_node(self, node: int) -> None:
        self.nodes_removed.append(int(node))
        self.operations.append({"op": "remove_node", "node": int(node)})

    def _note_add_edge(self, source: int, kind: str, target: int) -> None:
        self.edges_added.append((int(source), str(kind), int(target)))
        self.operations.append({
            "op": "add_edge", "source": int(source), "kind": str(kind),
            "target": int(target),
        })

    def _note_remove_edge(self, source: int, kind: str, target: int) -> None:
        self.edges_removed.append((int(source), str(kind), int(target)))
        self.operations.append({
            "op": "remove_edge", "source": int(source), "kind": str(kind),
            "target": int(target),
        })

    def _note_set_attr(self, node: int, key: str,
                       old_value: Any, new_value: Any) -> None:
        self.attrs.append((int(node), str(key), old_value, new_value))
        self.operations.append({
            "op": "set_attr", "node": int(node), "key": str(key),
            "old": old_value, "new": new_value,
        })

    def _ordered_operations(self) -> list[dict[str, Any]]:
        if self.operations:
            return list(self.operations)
        operations: list[dict[str, Any]] = []
        for node, type_name, attrs, origin in self.nodes_added:
            operations.append({
                "op": "add_node", "node": int(node), "type": str(type_name),
                "attrs": attrs, "origin": str(origin),
            })
        for source, kind, target in self.edges_added:
            operations.append({
                "op": "add_edge", "source": int(source), "kind": str(kind),
                "target": int(target),
            })
        for node, key, old_value, new_value in self.attrs:
            operations.append({
                "op": "set_attr", "node": int(node), "key": str(key),
                "old": old_value, "new": new_value,
            })
        for source, kind, target in self.edges_removed:
            operations.append({
                "op": "remove_edge", "source": int(source), "kind": str(kind),
                "target": int(target),
            })
        for node in self.nodes_removed:
            operations.append({"op": "remove_node", "node": int(node)})
        return operations

    # -- serialization ---------------------------------------------------

    @staticmethod
    def _encode_operation(operation: Mapping[str, Any], path: str) -> dict[str, Any]:
        op = operation.get("op")
        if op == "add_node":
            return {
                "op": "add_node",
                "node": int(operation["node"]),
                "type": str(operation["type"]),
                "attrs": _checkpoint_encode(operation["attrs"], path + ".attrs"),
                "origin": str(operation["origin"]),
            }
        if op == "remove_node":
            return {"op": "remove_node", "node": int(operation["node"])}
        if op in ("add_edge", "remove_edge"):
            return {
                "op": op,
                "source": int(operation["source"]),
                "kind": str(operation["kind"]),
                "target": int(operation["target"]),
            }
        if op == "set_attr":
            return {
                "op": "set_attr",
                "node": int(operation["node"]),
                "key": str(operation["key"]),
                "old": _checkpoint_encode(operation["old"], path + ".old"),
                "new": _checkpoint_encode(operation["new"], path + ".new"),
            }
        raise ValueError(f"unknown graph delta operation at {path}: {op!r}")

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic, JSON-safe delta (including exact order)."""
        base = _require_plain_int(self.base_revision, "base_revision")
        end = _require_plain_int(self.end_revision, "end_revision")
        if end < base:
            raise ValueError("end_revision must be >= base_revision")
        return {
            "schema": "bigville/graph_delta/1",
            "base_revision": base,
            "end_revision": end,
            "nodes_added": [
                [int(node), str(type_name), _checkpoint_encode(attrs, f"nodes_added[{index}].attrs"),
                 str(origin)]
                for index, (node, type_name, attrs, origin) in enumerate(self.nodes_added)
            ],
            "nodes_removed": [int(node) for node in self.nodes_removed],
            "edges_added": [
                [int(source), str(kind), int(target)]
                for source, kind, target in self.edges_added
            ],
            "edges_removed": [
                [int(source), str(kind), int(target)]
                for source, kind, target in self.edges_removed
            ],
            "attrs": [
                [int(node), str(key), _checkpoint_encode(old_value, f"attrs[{index}].old"),
                 _checkpoint_encode(new_value, f"attrs[{index}].new")]
                for index, (node, key, old_value, new_value) in enumerate(self.attrs)
            ],
            "operations": [
                self._encode_operation(operation, f"operations[{index}]")
                for index, operation in enumerate(self._ordered_operations())
            ],
        }

    @staticmethod
    def _parse_operation(value: Any, path: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{path} must be a mapping")
        op = value.get("op")
        if op == "add_node":
            node = _require_plain_int(value.get("node"), path + ".node", minimum=1)
            type_name = _require_plain_str(value.get("type"), path + ".type")
            origin = _require_plain_str(value.get("origin"), path + ".origin")
            attrs = _checkpoint_decode(value.get("attrs"), path + ".attrs")
            if not isinstance(attrs, dict):
                raise ValueError(f"{path}.attrs must decode to a dict")
            return {"op": op, "node": node, "type": type_name,
                    "attrs": attrs, "origin": origin}
        if op == "remove_node":
            node = _require_plain_int(value.get("node"), path + ".node", minimum=1)
            return {"op": op, "node": node}
        if op in ("add_edge", "remove_edge"):
            source = _require_plain_int(value.get("source"),
                                        path + ".source", minimum=1)
            target = _require_plain_int(value.get("target"),
                                        path + ".target", minimum=1)
            kind = _require_plain_str(value.get("kind"), path + ".kind")
            return {"op": op, "source": source, "kind": kind, "target": target}
        if op == "set_attr":
            node = _require_plain_int(value.get("node"), path + ".node", minimum=1)
            key = value.get("key")
            if not isinstance(key, str):
                raise ValueError(f"{path}.key must be a string")
            old_value = _checkpoint_decode(value.get("old"), path + ".old")
            new_value = _checkpoint_decode(value.get("new"), path + ".new")
            return {"op": op, "node": node, "key": key,
                    "old": old_value, "new": new_value}
        raise ValueError(f"unknown graph delta operation at {path}: {op!r}")

    def _note_parsed_operation(self, operation: Mapping[str, Any]) -> None:
        op = operation["op"]
        if op == "add_node":
            self._note_add_node(operation["node"], operation["type"],
                                operation["attrs"], operation["origin"])
        elif op == "remove_node":
            self._note_remove_node(operation["node"])
        elif op == "add_edge":
            self._note_add_edge(operation["source"], operation["kind"],
                                operation["target"])
        elif op == "remove_edge":
            self._note_remove_edge(operation["source"], operation["kind"],
                                   operation["target"])
        elif op == "set_attr":
            self._note_set_attr(operation["node"], operation["key"],
                                operation["old"], operation["new"])
        else:  # pragma: no cover - _parse_operation rejects unknown ops
            raise ValueError(f"unknown graph delta operation: {op!r}")

    @classmethod
    def from_dict(cls, value: Any) -> "GraphDelta":
        """Rebuild and validate a delta from :meth:`to_dict` output."""
        if not isinstance(value, Mapping):
            raise ValueError("graph delta must be a mapping")
        allowed = {"schema", "base_revision", "end_revision", "nodes_added",
                   "nodes_removed", "edges_added", "edges_removed", "attrs",
                   "operations"}
        extra = sorted(str(key) for key in value if key not in allowed)
        if extra:
            raise ValueError(f"graph delta has unknown keys: {', '.join(extra)}")
        if value.get("schema") != "bigville/graph_delta/1":
            raise ValueError("unsupported graph delta schema")
        base = _require_plain_int(value.get("base_revision"), "base_revision")
        end = _require_plain_int(value.get("end_revision"), "end_revision")
        if end < base:
            raise ValueError("end_revision must be >= base_revision")

        nodes_added_data = value.get("nodes_added")
        nodes_removed_data = value.get("nodes_removed")
        edges_added_data = value.get("edges_added")
        edges_removed_data = value.get("edges_removed")
        attrs_data = value.get("attrs")
        for name, data in (("nodes_added", nodes_added_data),
                           ("nodes_removed", nodes_removed_data),
                           ("edges_added", edges_added_data),
                           ("edges_removed", edges_removed_data),
                           ("attrs", attrs_data)):
            if not isinstance(data, list):
                raise ValueError(f"graph delta {name} must be a list")

        delta = cls(base_revision=base, end_revision=end)
        for index, item in enumerate(nodes_added_data):
            path = f"nodes_added[{index}]"
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                raise ValueError(f"{path} must be [id, type, attrs, origin]")
            node = _require_plain_int(item[0], path + ".id", minimum=1)
            type_name = _require_plain_str(item[1], path + ".type")
            attrs = _checkpoint_decode(item[2], path + ".attrs")
            if not isinstance(attrs, dict):
                raise ValueError(f"{path}.attrs must decode to a dict")
            origin = _require_plain_str(item[3], path + ".origin")
            delta.nodes_added.append((node, type_name, attrs, origin))
        for index, item in enumerate(nodes_removed_data):
            delta.nodes_removed.append(
                _require_plain_int(item, f"nodes_removed[{index}]", minimum=1))
        for name, data, target in (
                ("edges_added", edges_added_data, delta.edges_added),
                ("edges_removed", edges_removed_data, delta.edges_removed)):
            for index, item in enumerate(data):
                path = f"{name}[{index}]"
                if not isinstance(item, (list, tuple)) or len(item) != 3:
                    raise ValueError(f"{path} must be [source, kind, target]")
                source = _require_plain_int(item[0], path + ".source", minimum=1)
                kind = _require_plain_str(item[1], path + ".kind")
                target_node = _require_plain_int(item[2], path + ".target",
                                                 minimum=1)
                target.append((source, kind, target_node))
        for index, item in enumerate(attrs_data):
            path = f"attrs[{index}]"
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                raise ValueError(f"{path} must be [node, key, old, new]")
            node = _require_plain_int(item[0], path + ".node", minimum=1)
            key = item[1]
            if not isinstance(key, str):
                raise ValueError(f"{path}.key must be a string")
            old_value = _checkpoint_decode(item[2], path + ".old")
            new_value = _checkpoint_decode(item[3], path + ".new")
            delta.attrs.append((node, key, old_value, new_value))

        operations_data = value.get("operations")
        if operations_data is not None:
            if not isinstance(operations_data, list):
                raise ValueError("graph delta operations must be a list")
            delta.operations = [
                cls._parse_operation(operation, f"operations[{index}]")
                for index, operation in enumerate(operations_data)
            ]
        return delta

    # -- effects ---------------------------------------------------------

    def to_effects(self) -> tuple[dict[str, Any], ...]:
        """Return the delta as plain JSON-safe effect mappings.

        Effect order is the recorded mutation order.  Values use the same
        typed checkpoint encoding as the delta, so ``BundleResult.effects``
        can carry tuples, sets, dicts and ``NodeRef`` exactly.
        """
        return tuple(
            self._encode_operation(operation, f"operations[{index}]")
            for index, operation in enumerate(self._ordered_operations())
        )

    @classmethod
    def from_effects(cls, effects: Iterable[Mapping[str, Any]], *,
                     base_revision: int = 0,
                     end_revision: int | None = None) -> "GraphDelta":
        """Rebuild a delta from :meth:`to_effects` output.

        Effects do not carry the revision envelope (the bundle result already
        names its base), so callers supply ``base_revision`` and may supply the
        authoritative ``end_revision``.  Without one, ``end_revision`` is the
        base and only graph state, not the revision counter, is replayed.
        """
        base = _require_plain_int(base_revision, "base_revision")
        end = base if end_revision is None else _require_plain_int(
            end_revision, "end_revision")
        if end < base:
            raise ValueError("end_revision must be >= base_revision")
        delta = cls(base_revision=base, end_revision=end)
        for index, effect in enumerate(effects):
            parsed = cls._parse_operation(effect, f"effects[{index}]")
            delta._note_parsed_operation(parsed)
        return delta

    # -- application -----------------------------------------------------

    @staticmethod
    def _validate_node_type(node: Any, path: str) -> int:
        return _require_plain_int(node, path, minimum=1)

    def _validate_against(self, graph: "BigvilleGraph") -> list[dict[str, Any]]:
        """Validate every operation against a shadow before any real mutation."""
        if self.end_revision < self.base_revision:
            raise ValueError("end_revision must be >= base_revision")
        operations = self._ordered_operations()
        nodes = {int(ref) for ref in graph._nodes}
        edges = {(int(source), kind, int(target))
                 for (source, kind), targets in graph._edges.items()
                 for target in targets}
        for index, operation in enumerate(operations):
            path = f"operations[{index}]"
            if not isinstance(operation, Mapping):
                raise ValueError(f"{path} must be a mapping")
            op = operation.get("op")
            if op == "add_node":
                node = self._validate_node_type(operation.get("node"), path + ".node")
                type_name = operation.get("type")
                if not isinstance(type_name, str) or not type_name:
                    raise ValueError(f"{path}.type must be a non-empty string")
                attrs = operation.get("attrs")
                if not isinstance(attrs, dict):
                    raise ValueError(f"{path}.attrs must be a dict")
                origin = operation.get("origin")
                if not isinstance(origin, str) or not origin:
                    raise ValueError(f"{path}.origin must be a non-empty string")
                if node in nodes:
                    raise ValueError(f"{path} adds duplicate node {node}")
                nodes.add(node)
            elif op == "remove_node":
                node = self._validate_node_type(operation.get("node"), path + ".node")
                if node not in nodes:
                    raise ValueError(f"{path} removes missing node {node}")
                nodes.discard(node)
                edges = {edge for edge in edges
                         if edge[0] != node and edge[2] != node}
            elif op in ("add_edge", "remove_edge"):
                source = self._validate_node_type(
                    operation.get("source"), path + ".source")
                target = self._validate_node_type(
                    operation.get("target"), path + ".target")
                kind = operation.get("kind")
                if not isinstance(kind, str) or not kind:
                    raise ValueError(f"{path}.kind must be a non-empty string")
                if source not in nodes or target not in nodes:
                    raise ValueError(
                        f"{path} references a missing node endpoint")
                if op == "add_edge":
                    edges.add((source, kind, target))
                else:
                    edges.discard((source, kind, target))
            elif op == "set_attr":
                node = self._validate_node_type(operation.get("node"), path + ".node")
                key = operation.get("key")
                if not isinstance(key, str):
                    raise ValueError(f"{path}.key must be a string")
                if node not in nodes:
                    raise ValueError(f"{path} sets an attr on missing node {node}")
            else:
                raise ValueError(f"{path} has unknown operation {op!r}")
        return operations

    def apply_to(self, graph: "BigvilleGraph", *,
                 validate_base: bool = True) -> "BigvilleGraph":
        """Apply the delta to a same-base graph and return that graph.

        Validation (base revision, node/edge endpoints, duplicate node adds and
        operation shape) completes against a shadow before the first mutation,
        so a rejected delta leaves the graph untouched.  Application itself is
        performed under the process-wide graph lock; it is not rolled back if
        an internal invariant fails after validation.
        """
        if not isinstance(graph, BigvilleGraph):
            raise TypeError("apply_to expects a BigvilleGraph")
        with _GRAPH_LOCK:
            if validate_base and graph.revision != self.base_revision:
                raise ValueError(
                    f"graph delta base revision {self.base_revision} does not "
                    f"match graph revision {graph.revision}")
            operations = self._validate_against(graph)
            # Replay is not itself a recorded execution: hide any surrounding
            # recording scope so the applied mutations cannot pollute it.
            token = _CURRENT_DELTA.set(None)
            try:
                for operation in operations:
                    op = operation["op"]
                    if op == "add_node":
                        graph._install_node(operation["node"], operation["type"],
                                            operation["attrs"], operation["origin"])
                    elif op == "remove_node":
                        graph.remove_node(operation["node"])
                    elif op == "add_edge":
                        graph.add_edge_unchecked(
                            operation["source"], operation["kind"], operation["target"])
                    elif op == "remove_edge":
                        graph.remove_edge_unchecked(
                            operation["source"], operation["kind"], operation["target"])
                    elif op == "set_attr":
                        graph.set_attr(operation["node"], operation["key"],
                                       operation["new"])
                    else:  # pragma: no cover - _validate_against rejects unknown ops
                        raise ValueError(f"unknown graph delta operation: {op!r}")
                graph.revision = self.end_revision
            finally:
                _CURRENT_DELTA.reset(token)
        return graph


# NB03-style isolation for DR03: a recording scope is context-local, so two
# worker threads (or two copied async contexts) never share a delta.  Nested
# scopes on the same graph share the outer delta; a nested scope on a different
# graph gets its own delta and restores the outer one on exit.
_CURRENT_DELTA: contextvars.ContextVar[
    tuple["BigvilleGraph", GraphDelta] | None] = contextvars.ContextVar(
        "bigville_graph_delta", default=None)


class BigvilleGraph:
    """A deterministic, JSON-friendly directed typed graph.

    EN04: reads use the process-wide ``_GRAPH_LOCK`` only while ``lock_reads``
    is true.  A serial game session turns it off for its world graph because
    the only mutating thread is the caller: context workers read a world that
    the turn's decision snapshot asserts unchanged.  Every constructor path
    (including checkpoint restore) defaults to the locked, safe form; a caller
    may only disable it when it can guarantee no concurrent writer exists.

    Writes always take ``_GRAPH_LOCK``.  Read fast paths intentionally keep the
    public result shapes (``node`` still returns ``{"type", "attrs"}``).  An
    ``int``/``NodeRef`` identifier is used directly as a dictionary key --
    ``NodeRef`` equals its ``int`` value and hashes the same -- so no per-read
    ``NodeRef`` allocation is needed; other identifiers keep the historical
    ``int()`` coercion.
    """

    def __init__(self, *, lock_reads: bool = True):
        self._next_id = 1
        self._nodes: dict[NodeRef, _Node] = {}
        self._edges: dict[tuple[NodeRef, str], set[NodeRef]] = {}
        self._reverse: dict[tuple[NodeRef, str], set[NodeRef]] = {}
        self.seed_manifests: dict[str, dict[str, Any] | None] = {}
        # DR01: monotonic count of successful graph mutations.  It is the
        # bundle base version: a read never changes it, and one public mutation
        # call increments it exactly once even when it touches several edges
        # (for example ``remove_node``).  ``load_seed_manifest`` increments
        # through the ``add_node``/``add_edge_unchecked`` calls it makes.
        self.revision = 0
        self._inner = self
        # EN04: explicit read-lock policy.  True is the safe default; the game
        # disables it only for serial executors.
        self.lock_reads = bool(lock_reads)

    # NB03: fallback provenance for nodes created outside an execution
    # namespace.  This is a class default rather than instance state so it is
    # not written into a world checkpoint and old checkpoints stay valid.
    default_origin = DEFAULT_ORIGIN

    def set_read_locking(self, enabled: bool) -> None:
        """Set whether reads take the global lock (see ``lock_reads``)."""
        self.lock_reads = bool(enabled)

    # -- DR03 change recording -------------------------------------------

    def _recording_delta(self) -> GraphDelta | None:
        """The delta currently recording this graph in this context, if any."""
        entry = _CURRENT_DELTA.get()
        if entry is None or entry[0] is not self:
            return None
        return entry[1]

    @contextmanager
    def record_changes(self, *,
                       base_revision: int | None = None) -> Iterator[GraphDelta]:
        """Record this graph's successful mutations into a ``GraphDelta``.

        The context is ``ContextVar``-backed, matching node origins: concurrent
        threads/contexts each get their own delta.  A nested scope on the same
        graph shares the outer delta (it does not reset the base revision); a
        nested scope on a different graph gets its own delta and restores the
        outer one on exit.  Failed mutation attempts are not recorded because
        each mutation records only after it has succeeded.

        ``base_revision`` defaults to the graph revision at entry.  On exit
        ``end_revision`` is the graph revision observed then, including any
        successful mutation made through this graph in the scope.
        """
        entry = _CURRENT_DELTA.get()
        if entry is not None and entry[0] is self:
            yield entry[1]
            return
        base = self.revision if base_revision is None else int(base_revision)
        delta = GraphDelta(base_revision=base, end_revision=base)
        token = _CURRENT_DELTA.set((self, delta))
        try:
            yield delta
        finally:
            delta.end_revision = self.revision
            _CURRENT_DELTA.reset(token)

    def _install_node(self, node: int, type_name: str,
                      attrs: dict[str, Any], origin: str) -> NodeRef:
        """Install a node with an exact id, for delta replay only.

        Public ``add_node`` always allocates the next id; replay must recreate
        the ids the original execution allocated.  This is deliberately
        private and does not run change recording.
        """
        with _GRAPH_LOCK:
            ref = NodeRef(int(node))
            if ref in self._nodes:
                raise KeyError(f"Bigville graph node already exists: {int(ref)}")
            self._nodes[ref] = _Node(str(type_name), dict(attrs), str(origin))
            if int(ref) >= self._next_id:
                self._next_id = int(ref) + 1
            return ref

    @property
    def current_origin(self) -> str:
        """The namespace currently stamping newly created nodes."""
        origin = _CURRENT_ORIGIN.get()
        return origin if origin else self.default_origin

    @contextmanager
    def execution_namespace(self, namespace) -> Iterator["BigvilleGraph"]:
        """Attribute nodes created in this block to ``namespace``.

        ``namespace`` is an execution namespace string or an
        ``ExecutionNamespace`` (its canonical ``.name`` is used).  The binding
        is a ``ContextVar`` token, so the manager is re-entrant and restores the
        previous origin on exit, including on exception.  Threads and async
        tasks that do not explicitly copy the context start from the graph's
        ``default_origin``.  Nested graphs (for example a resident mind's graph)
        observe the same binding because the context var is module-wide.
        """
        from .bundles import ExecutionNamespace

        if isinstance(namespace, ExecutionNamespace):
            name = namespace.name
        elif isinstance(namespace, str):
            name = namespace
        else:
            raise TypeError("execution namespace must be a string or ExecutionNamespace")
        if not name:
            raise ValueError("execution namespace must not be empty")
        token = _CURRENT_ORIGIN.set(name)
        try:
            yield self
        finally:
            _CURRENT_ORIGIN.reset(token)

    def add_node(self, type_name: str, attrs: dict[str, Any] | None = None) -> NodeRef:
        origin = self.current_origin
        delta = self._recording_delta()
        attrs_value = dict(attrs or {})
        attrs_snapshot = (_copy_graph_value(attrs_value, "add_node.attrs")
                          if delta is not None else None)
        with _GRAPH_LOCK:
            node = NodeRef(self._next_id)
            self._next_id += 1
            self._nodes[node] = _Node(str(type_name), attrs_value, origin)
            self.revision += 1
            if delta is not None:
                delta._note_add_node(int(node), str(type_name),
                                     attrs_snapshot, origin)
            return node

    def has_node(self, node: NodeRef | int) -> bool:
        ref = node if isinstance(node, int) else NodeRef(int(node))
        if not self.lock_reads:
            return ref in self._nodes
        with _GRAPH_LOCK:
            return ref in self._nodes

    def node(self, node: NodeRef | int) -> dict[str, Any]:
        ref = node if isinstance(node, int) else NodeRef(int(node))
        if not self.lock_reads:
            record = self._nodes[ref]
            return {"type": record.type, "attrs": record.attrs}
        with _GRAPH_LOCK:
            record = self._nodes[ref]
            return {"type": record.type, "attrs": record.attrs}

    def node_attrs(self, node: NodeRef | int) -> dict[str, Any]:
        """Return a node's attribute mapping without building the public wrapper.

        EN04: hot rule and observation paths only need ``["attrs"]``.  The
        returned mapping is the canonical mutable mapping (the same object
        ``node()["attrs"]`` exposes); callers must not replace it.
        """
        ref = node if isinstance(node, int) else NodeRef(int(node))
        if not self.lock_reads:
            return self._nodes[ref].attrs
        with _GRAPH_LOCK:
            return self._nodes[ref].attrs

    def node_origin(self, node: NodeRef | int) -> str:
        """Return the execution namespace that created ``node``.

        Nodes restored from a legacy checkpoint without provenance report the
        documented ``"unqualified"`` fallback.
        """
        ref = node if isinstance(node, int) else NodeRef(int(node))
        if not self.lock_reads:
            return self._nodes[ref].origin
        with _GRAPH_LOCK:
            return self._nodes[ref].origin

    def qualified_id(self, node: NodeRef | int):
        """Return the ``(namespace, local_id)`` provenance form of ``node``.

        The graph itself keeps ``NodeRef`` as an integer; ``QualifiedId`` is
        only the serialization/wire identity.
        """
        from .bundles import QualifiedId

        return QualifiedId(namespace=self.node_origin(node), local_id=int(node))

    def nodes_by_origin(self, origin: str) -> tuple[NodeRef, ...]:
        """Return the nodes created by ``origin`` in ascending id order."""
        if not isinstance(origin, str):
            raise TypeError("origin must be a string")
        if not self.lock_reads:
            return tuple(ref for ref in sorted(self._nodes)
                         if self._nodes[ref].origin == origin)
        with _GRAPH_LOCK:
            return tuple(ref for ref in sorted(self._nodes)
                         if self._nodes[ref].origin == origin)

    def nodes(self, type_name: str | None = None) -> list[NodeRef]:
        if not self.lock_reads:
            return [ref for ref, record in self._nodes.items()
                    if type_name is None or record.type == type_name]
        with _GRAPH_LOCK:
            return [ref for ref, record in self._nodes.items()
                    if type_name is None or record.type == type_name]

    def set_attr(self, node: NodeRef | int, key: str, value: Any) -> None:
        delta = self._recording_delta()
        ref = NodeRef(int(node))
        key = str(key)
        value_snapshot = (_copy_graph_value(value, "set_attr.value")
                          if delta is not None else None)
        with _GRAPH_LOCK:
            record = self._nodes[ref]
            old_value = record.attrs.get(key)
            old_snapshot = (_copy_graph_value(old_value, "set_attr.old")
                            if delta is not None else None)
            record.attrs[key] = value
            self.revision += 1
            if delta is not None:
                delta._note_set_attr(int(ref), key, old_snapshot, value_snapshot)

    def add_edge_unchecked(self, source: NodeRef | int, edge: str,
                           target: NodeRef | int, attrs: dict | None = None) -> None:
        with _GRAPH_LOCK:
            src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
            if src not in self._nodes or dst not in self._nodes:
                raise KeyError("cannot connect a missing Bigville graph node")
            self._edges.setdefault((src, kind), set()).add(dst)
            self._reverse.setdefault((dst, kind), set()).add(src)
            self.revision += 1
            delta = self._recording_delta()
            if delta is not None:
                delta._note_add_edge(int(src), kind, int(dst))

    def add_edge(self, source, edge, target, attrs=None):
        # The unchecked form is the one real mutation; delegating keeps the
        # revision increment to exactly one per logical ``add_edge`` call.
        self.add_edge_unchecked(source, edge, target, attrs)

    def remove_edge_unchecked(self, source, edge, target) -> None:
        with _GRAPH_LOCK:
            src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
            self._edges.get((src, kind), set()).discard(dst)
            self._reverse.get((dst, kind), set()).discard(src)
            self.revision += 1
            delta = self._recording_delta()
            if delta is not None:
                delta._note_remove_edge(int(src), kind, int(dst))

    def has_edge(self, source, edge, target) -> bool:
        src = source if isinstance(source, int) else NodeRef(int(source))
        dst = target if isinstance(target, int) else NodeRef(int(target))
        key = (src, str(edge))
        if not self.lock_reads:
            return dst in self._edges.get(key, ())
        with _GRAPH_LOCK:
            return dst in self._edges.get(key, set())

    def neighbours(self, source, edge) -> list[NodeRef]:
        src = source if isinstance(source, int) else NodeRef(int(source))
        key = (src, str(edge))
        if not self.lock_reads:
            return sorted(self._edges.get(key, ()))
        with _GRAPH_LOCK:
            return sorted(self._edges.get(key, set()))

    def in_neighbours(self, target, edge) -> list[NodeRef]:
        dst = target if isinstance(target, int) else NodeRef(int(target))
        key = (dst, str(edge))
        if not self.lock_reads:
            return sorted(self._reverse.get(key, ()))
        with _GRAPH_LOCK:
            return sorted(self._reverse.get(key, set()))

    def remove_node(self, node) -> None:
        delta = self._recording_delta()
        with _GRAPH_LOCK:
            ref = NodeRef(int(node))
            if ref not in self._nodes:
                return
            incident: list[tuple[int, str, int]] = []
            if delta is not None:
                # One removed node is one revision increment, but replay needs
                # the incident edges it took with it.  ``_edges`` is the
                # authoritative forward adjacency (``_reverse`` mirrors it), so
                # collecting there gives each incident edge exactly once.
                for (src, edge), targets in self._edges.items():
                    for dst in targets:
                        if src == ref or dst == ref:
                            incident.append((int(src), str(edge), int(dst)))
                incident.sort()
            for (src, edge), targets in list(self._edges.items()):
                if src == ref or ref in targets:
                    targets.discard(ref)
                    if src == ref:
                        self._edges.pop((src, edge), None)
            for (dst, edge), sources in list(self._reverse.items()):
                if dst == ref or ref in sources:
                    sources.discard(ref)
                    if dst == ref:
                        self._reverse.pop((dst, edge), None)
            self._nodes.pop(ref, None)
            # Nested edge cleanup above is internal: one removed node is one
            # logical mutation, not one per incident edge.
            self.revision += 1
            if delta is not None:
                for source, edge, target in incident:
                    delta._note_remove_edge(source, edge, target)
                delta._note_remove_node(int(ref))

    def load_seed_manifest(self, manifest, agent=None) -> None:
        """Retain seeded graph data without executing an external rule engine."""
        if isinstance(manifest, str):
            seed_id, payload = manifest, None
        else:
            payload = dict(manifest or {})
            seed_id = str(payload.get("id", payload.get("name", "anonymous")))
        self.seed_manifests[seed_id] = payload
        seed = next((n for n in self.nodes("Seed")
                     if self.node(n)["attrs"].get("id") == seed_id), None)
        if seed is None:
            seed = self.add_node("Seed", {"id": seed_id, "version": "1.0.0"})
        if agent is not None and self.has_node(agent):
            self.add_edge_unchecked(agent, "holds_seed", seed)

    def settle(self, *_args, **_kwargs) -> int:
        """Compatibility no-op: Bigville mechanics are explicit world code."""
        return 0

    def force_all_dirty(self) -> None:
        return None

    def graph_to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [{"id": int(ref), "type": record.type,
                       "attrs": _json_value(record.attrs)}
                      for ref, record in self._nodes.items()],
            "edges": [{"source": int(src), "kind": edge, "target": int(dst)}
                      for (src, edge), targets in self._edges.items()
                      for dst in sorted(targets)],
            "seeds": sorted(self.seed_manifests),
        }

    def to_checkpoint_dict(self) -> dict[str, Any]:
        """Return a strict, typed, JSON-safe representation for durable storage.

        This is deliberately distinct from ``graph_to_dict()``, which is a
        lossy inspection projection used by reports and held-state APIs.
        Unknown values fail rather than being replaced with ``repr(value)``.
        """
        return {
            "schema": "bigville/graph/1",
            "next_id": self._next_id,
            "revision": self.revision,
            "nodes": [
                {"id": int(ref), "type": record.type,
                 "attrs": _checkpoint_encode(record.attrs, f"nodes[{int(ref)}].attrs")}
                for ref, record in self._nodes.items()
            ],
            "edges": [
                {"source": int(src), "kind": edge, "target": int(dst)}
                for (src, edge), targets in self._edges.items()
                for dst in sorted(targets)
            ],
            "origins": [
                [int(ref), self._nodes[ref].origin]
                for ref in sorted(self._nodes)
            ],
            "seed_manifests": [
                [seed_id, _checkpoint_encode(payload, f"seed_manifests[{seed_id!r}]")]
                for seed_id, payload in self.seed_manifests.items()
            ],
        }

    @classmethod
    def from_checkpoint_dict(cls, data: dict[str, Any]) -> "BigvilleGraph":
        """Rebuild a graph checkpoint, validating IDs and every edge endpoint."""
        if not isinstance(data, dict) or data.get("schema") != "bigville/graph/1":
            raise ValueError("unsupported Bigville graph checkpoint schema")
        next_id = data.get("next_id")
        if type(next_id) is not int or next_id < 1:
            raise ValueError("Bigville graph checkpoint has invalid next_id")
        # DR01: ``revision`` is optional for legacy checkpoints.  A checkpoint
        # written before revisions existed loads as revision 0.  If present it
        # must be a non-negative int (an explicit null is malformed, not legacy).
        revision = data.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise ValueError("Bigville graph checkpoint has invalid revision")
        nodes_data = data.get("nodes")
        edges_data = data.get("edges")
        manifests_data = data.get("seed_manifests")
        if not isinstance(nodes_data, list) or not isinstance(edges_data, list):
            raise ValueError("Bigville graph checkpoint nodes and edges must be lists")
        if not isinstance(manifests_data, list):
            raise ValueError("Bigville graph checkpoint seed_manifests must be a list")

        # NB03: ``origins`` is optional.  A checkpoint written before provenance
        # existed has no key at all and every node migrates to "unqualified".
        # If the key is present it must be a list covering every node exactly
        # once; an explicit null is malformed rather than legacy.
        has_origins = "origins" in data
        origins_data = data.get("origins")
        origins: dict[int, str] = {}
        if has_origins:
            if not isinstance(origins_data, list):
                raise ValueError("Bigville graph checkpoint origins must be a list")
            for index, pair in enumerate(origins_data):
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError(f"invalid Bigville graph origin at index {index}")
                node_id, origin = pair
                if type(node_id) is not int or node_id < 1:
                    raise ValueError(
                        f"invalid Bigville graph origin node ID at index {index}")
                if not isinstance(origin, str) or not origin:
                    raise ValueError(
                        f"invalid Bigville graph origin name at ID {node_id}")
                if node_id in origins:
                    raise ValueError(f"duplicate Bigville graph origin ID: {node_id}")
                origins[node_id] = origin

        graph = cls()
        max_id = 0
        for index, item in enumerate(nodes_data):
            if not isinstance(item, dict):
                raise ValueError(f"invalid Bigville graph node at index {index}")
            node_id, type_name = item.get("id"), item.get("type")
            if type(node_id) is not int or node_id < 1:
                raise ValueError(f"invalid Bigville graph node ID at index {index}")
            if node_id in graph._nodes:
                raise ValueError(f"duplicate Bigville graph node ID: {node_id}")
            if not isinstance(type_name, str) or not type_name:
                raise ValueError(f"invalid Bigville graph node type at ID {node_id}")
            attrs = _checkpoint_decode(item.get("attrs"), f"nodes[{node_id}].attrs")
            if not isinstance(attrs, dict):
                raise ValueError(f"Bigville graph node attrs at ID {node_id} must be a dict")
            graph._nodes[NodeRef(node_id)] = _Node(
                type_name, attrs, origins.get(node_id, DEFAULT_ORIGIN))
            max_id = max(max_id, node_id)

        if has_origins:
            node_ids = {int(ref) for ref in graph._nodes}
            missing = sorted(node_ids - set(origins))
            if missing:
                raise ValueError(
                    f"missing Bigville graph origin for node ID: {missing[0]}")
            unknown = sorted(set(origins) - node_ids)
            if unknown:
                raise ValueError(
                    f"Bigville graph origin references a missing node ID: {unknown[0]}")

        if next_id <= max_id:
            raise ValueError("Bigville graph checkpoint next_id must exceed all node IDs")
        graph._next_id = next_id
        for index, item in enumerate(edges_data):
            if not isinstance(item, dict):
                raise ValueError(f"invalid Bigville graph edge at index {index}")
            src, kind, dst = item.get("source"), item.get("kind"), item.get("target")
            if type(src) is not int or type(dst) is not int:
                raise ValueError(f"invalid Bigville graph edge endpoint at index {index}")
            if not isinstance(kind, str) or not kind:
                raise ValueError(f"invalid Bigville graph edge kind at index {index}")
            if NodeRef(src) not in graph._nodes or NodeRef(dst) not in graph._nodes:
                raise ValueError(f"Bigville graph edge at index {index} references a missing node")
            graph.add_edge_unchecked(NodeRef(src), kind, NodeRef(dst))

        for index, pair in enumerate(manifests_data):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"invalid seed manifest entry at index {index}")
            seed_id, encoded = pair
            if not isinstance(seed_id, str) or not seed_id:
                raise ValueError(f"invalid seed manifest ID at index {index}")
            if seed_id in graph.seed_manifests:
                raise ValueError(f"duplicate seed manifest ID: {seed_id}")
            payload = _checkpoint_decode(encoded, f"seed_manifests[{seed_id!r}]")
            if payload is not None and not isinstance(payload, dict):
                raise ValueError(f"seed manifest {seed_id!r} payload must be a dict or None")
            graph.seed_manifests[seed_id] = payload
        # Restoring edges uses ``add_edge_unchecked``, which advances the
        # revision; the checkpoint's saved count is authoritative after load.
        graph.revision = revision
        return graph


class GraphEye:
    """Small graph-data replacement for the old visual adapter boundary."""

    def __init__(self, *args, graph=None, **_kwargs):
        self.graph = graph or BigvilleGraph()
        self._agent = self.graph.add_node("Agent", {})

    @property
    def s(self):
        return self.graph

    @property
    def inner(self):
        return self.graph

    def build(self):
        return self

    def close(self):
        return None


def manifest_for(seed_id: str) -> str:
    """Return a stable seed identifier for graph-data provenance."""
    return str(seed_id)


def boot_core(seeds=()):
    graph = BigvilleGraph()
    agent = graph.add_node("Agent", {})
    for seed in seeds:
        graph.load_seed_manifest(str(seed), agent)
    return graph, agent


def load_seeds_into(graph, agent, seed_ids: Iterable[str]):
    for seed_id in seed_ids:
        graph.load_seed_manifest(str(seed_id), agent)
    return {str(seed_id): next(
        n for n in graph.nodes("Seed")
        if graph.node(n)["attrs"].get("id") == str(seed_id)) for seed_id in seed_ids}


class WorldAdapter:
    """Graph-backed communicative goal adapter with a small surface realizer.

    Bigville cannot bundle Ocelot's substrate, but it must still turn the
    structured meanings produced by its cognition boundary into speech.  The
    old implementation used ``key of key of value`` as a debug dump.  This
    adapter keeps the meaning graph-friendly while using a deterministic
    lexical/grammatical realization for the common village speech acts.
    """

    def __init__(self, seeds=()):
        self.s = BigvilleGraph()
        self._addressee = None
        self._goals: list[tuple[Any, dict]] = []
        for seed in seeds:
            self.s.load_seed_manifest(str(seed))

    def set_addressee(self, node):
        self._addressee = node

    def add_communicative_goal(self, meaning, priority=1.0):
        self._goals.append((meaning, {"priority": float(priority)}))

    def _communicative_action(self):
        if not self._goals:
            return []
        meaning, _meta = self._goals.pop(0)
        return [self.utterance_for(meaning)]

    def utterance_for(self, meaning):
        """Render a held communicative meaning as ordinary resident speech.

        This is deliberately meaning-driven rather than a world-level speech
        template: the world supplies a semantic goal, and this layer chooses
        a natural surface form without exposing graph field names to the
        listener.  Unknown meanings retain a readable semantic fallback so a
        new concept does not regress to a structural debug string.
        """
        return _realize_meaning(meaning)


def _meaning_text(value):
    """Compatibility name for callers of the old structural renderer."""
    return _realize_meaning(value)


def _speech_lexicon(lexicon=None):
    """The chatter and weather phrases (Phase 018: pack tables SPEECH_CHATTER and SPEECH_WEATHER).

    ``lexicon`` is a dict with ``chatter`` and ``weather`` keys, for a caller that holds another pack's
    phrases. Without it the default bigville pack is read."""
    if lexicon is not None:
        return lexicon
    from domains.pack import load_pack
    pack = load_pack("bigville")
    return {"chatter": pack["SPEECH_CHATTER"], "weather": pack["SPEECH_WEATHER"]}


def _realize_meaning(value, lexicon=None):
    """Small dependency-free lexical realization for common goal meanings."""
    if not isinstance(value, dict) or not value:
        return str(value)
    if len(value) != 1:
        return " ".join(_realize_meaning({key: child}, lexicon) for key, child in value.items())

    key, child = next(iter(value.items()))
    key = str(key)
    if key == "news":
        payload = child.get("of") if isinstance(child, dict) else child
        if isinstance(payload, dict):
            kind = str(payload.get("kind", ""))
            subject = str(payload.get("subject", ""))
            detail = str(payload.get("detail", "")).strip()
            # First-person self-experience (rung 1c) renders as "I ..."
            # instead of the third-party "I heard that ..." gossip form --
            # both draw on the same event content, only the person differs.
            is_self = bool(payload.get("self", False))
            if kind and subject:
                if detail:
                    detail = detail.rstrip(".")
                    if is_self and detail.startswith(subject):
                        return f"I{detail[len(subject):]}."
                    return f"I heard that {detail}."
                verb = {"injury": "was injured", "death": "died"}.get(kind, f"was involved in {kind}")
                if is_self:
                    return f"I {verb}."
                return f"I heard that {subject} {verb}."
            if "village" in payload:
                return f"I heard that {_realize_meaning(payload['village'])}"
        return f"I heard about {_natural_value(payload)}."
    if key == "topic":
        payload = child.get("of") if isinstance(child, dict) else child
        trade = str(payload).lower()
        chatter = _speech_lexicon(lexicon)["chatter"]
        if trade in chatter["phrases"]:
            return chatter["phrases"][trade]
        if trade:
            return chatter["work_template"].format(trade=trade)
        return chatter["empty"]
    if key == "weather":
        payload = child.get("of") if isinstance(child, dict) else child
        weather = str(payload).lower()
        forecast = _speech_lexicon(lexicon)["weather"]
        if weather in forecast["phrases"]:
            return forecast["phrases"][weather]
        return forecast["template"].format(weather=weather)
    if key == "greeting":
        return f"Hello, {_target(child)}."
    if key == "warning":
        return f"Be careful, {_target(child)}."
    if key == "uncertainty":
        payload = child.get("of") if isinstance(child, dict) else child
        return f"I am not sure about {_natural_value(payload)}."
    if key in {"acknowledgement", "answer"}:
        return "Yes, I understand."
    if key == "request":
        return "Could you help me with that?"
    if key == "offer":
        return "I can help with that."
    if key == "question":
        return "How are things?"
    if key == "thanks":
        return "Thank you."
    if key == "apology":
        return "I am sorry."
    if key == "farewell":
        return "Goodbye for now."
    if key == "complaint":
        return "I am worried about this."
    if key == "promise":
        return "I promise I will help."
    if key == "purchase":
        return _realize_purchase(child)
    if key == "inform":
        payload = child.get("of") if isinstance(child, dict) else child
        return f"I wanted to tell you that {_natural_value(payload)}."
    return f"I wanted to tell you about {_natural_value(child)}."


def _target(value):
    if isinstance(value, dict):
        value = value.get("of", value.get("to", value))
    return str(value)


def _natural_value(value):
    if isinstance(value, dict):
        if len(value) == 1:
            key, child = next(iter(value.items()))
            return f"{key} {_natural_value(child)}"
        return ", ".join(f"{key} {_natural_value(child)}" for key, child in value.items()
                          if key != "occasion")
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(_natural_value(item) for item in value)
    return str(value)


def _realize_purchase(value):
    payload = value.get("of", value) if isinstance(value, dict) else value
    if isinstance(payload, dict) and payload:
        item, item_data = next(iter(payload.items()))
        seller = item_data.get("from") if isinstance(item_data, dict) else None
        if seller:
            return f"Could I buy some {item} from {seller}?"
        return f"Could I buy some {item}?"
    return "Could I buy that?"


def _json_value(value):
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return value.value
    return repr(value)
