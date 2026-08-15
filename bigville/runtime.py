"""Bigville's small, dependency-free graph data runtime.

The village uses a typed graph as its durable state boundary. Cognition
providers may generate graph data; world code remains responsible for
admissibility and physical effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class NodeRef(int):
    """An integer node identifier with the compatibility ``.value`` view."""

    @property
    def value(self) -> int:
        return int(self)


@dataclass
class _Node:
    type: str
    attrs: dict[str, Any]


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
        node = NodeRef(self._next_id)
        self._next_id += 1
        self._nodes[node] = _Node(str(type_name), dict(attrs or {}))
        return node

    def has_node(self, node: NodeRef | int) -> bool:
        return NodeRef(int(node)) in self._nodes

    def node(self, node: NodeRef | int) -> dict[str, Any]:
        ref = NodeRef(int(node))
        record = self._nodes[ref]
        return {"type": record.type, "attrs": record.attrs}

    def nodes(self, type_name: str | None = None) -> list[NodeRef]:
        return [ref for ref, record in self._nodes.items()
                if type_name is None or record.type == type_name]

    def set_attr(self, node: NodeRef | int, key: str, value: Any) -> None:
        self._nodes[NodeRef(int(node))].attrs[str(key)] = value

    def add_edge_unchecked(self, source: NodeRef | int, edge: str,
                           target: NodeRef | int, attrs: dict | None = None) -> None:
        src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
        if src not in self._nodes or dst not in self._nodes:
            raise KeyError("cannot connect a missing Bigville graph node")
        self._edges.setdefault((src, kind), set()).add(dst)
        self._reverse.setdefault((dst, kind), set()).add(src)

    def add_edge(self, source, edge, target, attrs=None):
        self.add_edge_unchecked(source, edge, target, attrs)

    def remove_edge_unchecked(self, source, edge, target) -> None:
        src, dst, kind = NodeRef(int(source)), NodeRef(int(target)), str(edge)
        self._edges.get((src, kind), set()).discard(dst)
        self._reverse.get((dst, kind), set()).discard(src)

    def has_edge(self, source, edge, target) -> bool:
        return NodeRef(int(target)) in self._edges.get((NodeRef(int(source)), str(edge)), set())

    def neighbours(self, source, edge) -> list[NodeRef]:
        return sorted(self._edges.get((NodeRef(int(source)), str(edge)), set()))

    def in_neighbours(self, target, edge) -> list[NodeRef]:
        return sorted(self._reverse.get((NodeRef(int(target)), str(edge)), set()))

    def remove_node(self, node) -> None:
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


def _realize_meaning(value):
    """Small dependency-free lexical realization for common goal meanings."""
    if not isinstance(value, dict) or not value:
        return str(value)
    if len(value) != 1:
        return " ".join(_realize_meaning({key: child}) for key, child in value.items())

    key, child = next(iter(value.items()))
    key = str(key)
    if key == "news":
        payload = child.get("of") if isinstance(child, dict) else child
        if isinstance(payload, dict):
            kind = str(payload.get("kind", ""))
            subject = str(payload.get("subject", ""))
            detail = str(payload.get("detail", "")).strip()
            if kind and subject:
                if detail:
                    detail = detail.rstrip(".")
                    return f"I heard that {detail}."
                verb = {"injury": "was injured", "death": "died"}.get(kind, f"was involved in {kind}")
                return f"I heard that {subject} {verb}."
            if "village" in payload:
                return f"I heard that {_realize_meaning(payload['village'])}"
        return f"I heard about {_natural_value(payload)}."
    if key == "weather":
        payload = child.get("of") if isinstance(child, dict) else child
        weather = str(payload).lower()
        phrases = {
            "rain": "It is raining today.", "storm": "There is a storm coming.",
            "dry": "It is dry today.", "clear": "The sky is clear today.",
            "frost": "There is a frost this morning.",
        }
        return phrases.get(weather, f"The weather is {weather} today.")
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
