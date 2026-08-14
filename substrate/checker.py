"""Consistency checker C: gates every Γ-mediated write to G.

C.check is the only path through which the application learns whether a
prospective edge is admissible. Π in ``primitives.py`` consults C before any
mutation — there is no bypass.
"""
from __future__ import annotations

from .grammar import Grammar
from .graph import NodeID, TypedGraph


class ConsistencyChecker:
    def __init__(self, grammar: Grammar) -> None:
        self.grammar = grammar

    def check_edge(self, G: TypedGraph, src: NodeID, edge_type: str, tgt: NodeID) -> bool:
        return self.grammar.admits(G.node(src), edge_type, G.node(tgt), G)

    def explain(self, G: TypedGraph, src: NodeID, edge_type: str, tgt: NodeID) -> list[str]:
        """Return provenance strings for productions that admit this edge, or [] if none."""
        return [p.provenance for p in self.grammar.matching(G.node(src), edge_type, G.node(tgt), G)]
