"""Γ: admissibility grammar.

A ``Production`` is `(src-pattern, edge-type, tgt-pattern, where-clause)`.
A ``Grammar`` is a finite list of productions; ``admits`` accepts an edge iff
some production matches it. Γ round-trips to/from a G-subgraph (Axiom 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .dsl import Term, term_from_subgraph, term_to_subgraph
from .graph import Node, NodeID, TypedGraph


@dataclass(frozen=True)
class NodePattern:
    """Matches a node by type and binds its NodeID to ``var`` in the evaluator env."""
    type: str
    var: str


@dataclass(frozen=True)
class Production:
    src: NodePattern
    edge_type: str
    tgt: NodePattern
    where: Term | None = None
    weight: Term | None = None  # Theorem D: numeric weight, evaluated in the same env as ``where``
    provenance: str = ""  # human-readable label; survives Γ-edits

    def admits(self, src_node: Node, tgt_node: Node, G: TypedGraph) -> bool:
        if src_node.type != self.src.type or tgt_node.type != self.tgt.type:
            return False
        env = {self.src.var: src_node.id, self.tgt.var: tgt_node.id}
        if self.where is None:
            return True
        return bool(self.where.evaluate(env, G))

    def evaluate_weight(self, src_node: Node, tgt_node: Node, G: TypedGraph) -> float:
        if self.weight is None:
            return 1.0
        env = {self.src.var: src_node.id, self.tgt.var: tgt_node.id}
        return float(self.weight.evaluate(env, G))


_GRAMMAR_NODE = "Grammar"
_PRODUCTION_NODE = "Production"
_NODEPATTERN_NODE = "NodePattern"


class Grammar:
    def __init__(self, productions: Iterable[Production] = ()) -> None:
        self.productions: list[Production] = list(productions)
        self._index: dict[tuple[str, str, str], list[Production]] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index = {}
        for p in self.productions:
            key = (p.src.type, p.edge_type, p.tgt.type)
            self._index.setdefault(key, []).append(p)

    def candidates(self, src_type: str, edge_type: str, tgt_type: str) -> list[Production]:
        return self._index.get((src_type, edge_type, tgt_type), [])

    def admits(self, src_node: Node, edge_type: str, tgt_node: Node, G: TypedGraph) -> bool:
        for p in self.candidates(src_node.type, edge_type, tgt_node.type):
            if p.admits(src_node, tgt_node, G):
                return True
        return False

    def matching(self, src_node: Node, edge_type: str, tgt_node: Node,
                 G: TypedGraph) -> list[Production]:
        return [p for p in self.candidates(src_node.type, edge_type, tgt_node.type)
                if p.admits(src_node, tgt_node, G)]

    def add(self, p: Production) -> None:
        self.productions.append(p)
        self._index.setdefault((p.src.type, p.edge_type, p.tgt.type), []).append(p)

    def remove(self, p: Production) -> None:
        self.productions.remove(p)
        self._rebuild_index()

    # --- Axiom 3: Γ ↔ G-subgraph ---

    def to_subgraph(self, G: TypedGraph) -> NodeID:
        root = G._insert_node(_GRAMMAR_NODE, {})
        for i, prod in enumerate(self.productions):
            pid = G._insert_node(_PRODUCTION_NODE, {
                "edge_type": prod.edge_type,
                "provenance": prod.provenance,
            })
            G._insert_edge(root, "production", pid, {"index": i})
            src_id = G._insert_node(_NODEPATTERN_NODE,
                                    {"type": prod.src.type, "var": prod.src.var})
            tgt_id = G._insert_node(_NODEPATTERN_NODE,
                                    {"type": prod.tgt.type, "var": prod.tgt.var})
            G._insert_edge(pid, "pattern.src", src_id)
            G._insert_edge(pid, "pattern.tgt", tgt_id)
            if prod.where is not None:
                where_id = term_to_subgraph(prod.where, G)
                G._insert_edge(pid, "pattern.where", where_id)
            if prod.weight is not None:
                weight_id = term_to_subgraph(prod.weight, G)
                G._insert_edge(pid, "pattern.weight", weight_id)
        return root

    @classmethod
    def from_subgraph(cls, G: TypedGraph, root_id: NodeID) -> "Grammar":
        root = G.node(root_id)
        if root.type != _GRAMMAR_NODE:
            raise ValueError(f"Not a Grammar root: {root.type}")
        prod_edges = sorted(G.out_edges(root_id, "production"),
                            key=lambda e: e.attrs.get("index", 0))
        prods: list[Production] = []
        for e in prod_edges:
            pid = e.key.tgt
            pnode = G.node(pid)
            src_edge = next(G.out_edges(pid, "pattern.src"))
            tgt_edge = next(G.out_edges(pid, "pattern.tgt"))
            src = _read_node_pattern(G, src_edge.key.tgt)
            tgt = _read_node_pattern(G, tgt_edge.key.tgt)
            where = None
            for we in G.out_edges(pid, "pattern.where"):
                where = term_from_subgraph(G, we.key.tgt)
                break
            weight = None
            for we in G.out_edges(pid, "pattern.weight"):
                weight = term_from_subgraph(G, we.key.tgt)
                break
            prods.append(Production(
                src=src,
                edge_type=pnode.attrs.get("edge_type", ""),
                tgt=tgt,
                where=where,
                weight=weight,
                provenance=pnode.attrs.get("provenance", ""),
            ))
        return cls(prods)


def _read_node_pattern(G: TypedGraph, nid: NodeID) -> NodePattern:
    n = G.node(nid)
    if n.type != _NODEPATTERN_NODE:
        raise ValueError(f"Expected NodePattern, got {n.type}")
    return NodePattern(type=n.attrs["type"], var=n.attrs["var"])
