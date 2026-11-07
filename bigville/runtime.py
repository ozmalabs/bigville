"""Bigville's small, dependency-free graph data runtime.

The village uses a typed graph as its durable state boundary. Cognition
providers may generate graph data; world code remains responsible for
admissibility and physical effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import threading
from typing import Any, Iterable


# TG05: one process-wide re-entrant lock guards the canonical graph's internal
# containers.  It is module level (not per graph) so the lock is never written
# into a checkpoint or copied with a world; every BigvilleGraph in process
# shares it.  RLock is required because public helpers call one another (for
# example ``load_seed_manifest`` calls ``nodes`` and ``add_node``).
_GRAPH_LOCK = threading.RLock()


class NodeRef(int):
    """An integer node identifier with the compatibility ``.value`` view."""

    @property
    def value(self) -> int:
        return int(self)


@dataclass
class _Node:
    type: str
    attrs: dict[str, Any]


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


class BigvilleGraph:
    """A deterministic, JSON-friendly directed typed graph."""

    def __init__(self):
        self._next_id = 1
        self._nodes: dict[NodeRef, _Node] = {}
        self._edges: dict[tuple[NodeRef, str], set[NodeRef]] = {}
        self._reverse: dict[tuple[NodeRef, str], set[NodeRef]] = {}
        self.seed_manifests: dict[str, dict[str, Any] | None] = {}
        self._inner = self

    def add_node(self, type_name: str, attrs: dict[str, Any] | None = None) -> NodeRef:
        with _GRAPH_LOCK:
            node = NodeRef(self._next_id)
            self._next_id += 1
            self._nodes[node] = _Node(str(type_name), dict(attrs or {}))
            return node

    def has_node(self, node: NodeRef | int) -> bool:
        with _GRAPH_LOCK:
            return NodeRef(int(node)) in self._nodes

    def node(self, node: NodeRef | int) -> dict[str, Any]:
        with _GRAPH_LOCK:
            ref = NodeRef(int(node))
            record = self._nodes[ref]
            return {"type": record.type, "attrs": record.attrs}

    def nodes(self, type_name: str | None = None) -> list[NodeRef]:
        with _GRAPH_LOCK:
            return [ref for ref, record in self._nodes.items()
                    if type_name is None or record.type == type_name]

    def set_attr(self, node: NodeRef | int, key: str, value: Any) -> None:
        with _GRAPH_LOCK:
            self._nodes[NodeRef(int(node))].attrs[str(key)] = value

    def add_edge_unchecked(self, source: NodeRef | int, edge: str,
                           target: NodeRef | int, attrs: dict | None = None) -> None:
        with _GRAPH_LOCK:
            src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
            if src not in self._nodes or dst not in self._nodes:
                raise KeyError("cannot connect a missing Bigville graph node")
            self._edges.setdefault((src, kind), set()).add(dst)
            self._reverse.setdefault((dst, kind), set()).add(src)

    def add_edge(self, source, edge, target, attrs=None):
        self.add_edge_unchecked(source, edge, target, attrs)

    def remove_edge_unchecked(self, source, edge, target) -> None:
        with _GRAPH_LOCK:
            src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
            self._edges.get((src, kind), set()).discard(dst)
            self._reverse.get((dst, kind), set()).discard(src)

    def has_edge(self, source, edge, target) -> bool:
        with _GRAPH_LOCK:
            return NodeRef(int(target)) in self._edges.get((NodeRef(int(source)), str(edge)), set())

    def neighbours(self, source, edge) -> list[NodeRef]:
        with _GRAPH_LOCK:
            return sorted(self._edges.get((NodeRef(int(source)), str(edge)), set()))

    def in_neighbours(self, target, edge) -> list[NodeRef]:
        with _GRAPH_LOCK:
            return sorted(self._reverse.get((NodeRef(int(target)), str(edge)), set()))

    def remove_node(self, node) -> None:
        with _GRAPH_LOCK:
            ref = NodeRef(int(node))
            if ref not in self._nodes:
                return
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
        nodes_data = data.get("nodes")
        edges_data = data.get("edges")
        manifests_data = data.get("seed_manifests")
        if not isinstance(nodes_data, list) or not isinstance(edges_data, list):
            raise ValueError("Bigville graph checkpoint nodes and edges must be lists")
        if not isinstance(manifests_data, list):
            raise ValueError("Bigville graph checkpoint seed_manifests must be a list")

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
            graph._nodes[NodeRef(node_id)] = _Node(type_name, attrs)
            max_id = max(max_id, node_id)

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
