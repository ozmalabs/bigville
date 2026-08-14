"""Π: the only public-facing mutation surface over G.

All edge insertions consult C; an inadmissible insertion raises
``InadmissibleEdge``. Node insertions are free (Γ-admissibility is an
edge-triple property; node-type vocabulary extension goes through Theorem C
operations on the Γ-subgraph, not here). ``transform`` makes a sequence of
operations atomic.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from .checker import ConsistencyChecker
from .dsl import collect_vars
from .graph import Edge, EdgeKey, Node, NodeID, TypedGraph


class InadmissibleEdge(Exception):
    """Raised when C rejects a proposed edge insertion."""


@dataclass
class Substrate:
    """The (G, Γ, C) bundle. All Π primitives are methods here."""
    graph: TypedGraph
    checker: ConsistencyChecker

    # --- extend ---

    def add_node(self, type: str, attrs: dict[str, Any] | None = None) -> NodeID:
        return self.graph._insert_node(type, attrs)

    def add_edge(self, src: NodeID, edge_type: str, tgt: NodeID,
                 attrs: dict[str, Any] | None = None) -> EdgeKey:
        if not self.checker.check_edge(self.graph, src, edge_type, tgt):
            raise InadmissibleEdge(
                f"Γ rejects ({self.graph.node(src).type}) "
                f"-[{edge_type}]-> ({self.graph.node(tgt).type})"
            )
        return self.graph._insert_edge(src, edge_type, tgt, attrs)

    # --- transform (deletion is unconditional; admissibility governs additions) ---

    def remove_edge(self, key: EdgeKey) -> None:
        self.graph._delete_edge(key)

    def remove_node(self, nid: NodeID) -> None:
        self.graph._delete_node(nid)

    def set_attr(self, nid: NodeID, key: str, value: Any) -> None:
        self.graph._set_attr(nid, key, value)

    def set_type(self, nid: NodeID, new_type: str) -> None:
        """Mutate a node's type in place, preserving NodeID and edges. Used by
        domain step-operations whose Γ has already certified the type change."""
        self.graph._set_type(nid, new_type)

    @contextmanager
    def transform(self) -> Iterator["Transaction"]:
        """Buffered mutations; rollback if any add_edge is rejected."""
        tx = Transaction(self)
        try:
            yield tx
            tx._commit()
        except Exception:
            tx._rollback()
            raise

    # --- query ---

    def node(self, nid: NodeID) -> Node:
        return self.graph.node(nid)

    def nodes(self, type: str | None = None) -> Iterable[Node]:
        return self.graph.nodes(type)

    def out_edges(self, nid: NodeID, edge_type: str | None = None) -> Iterable[Edge]:
        return self.graph.out_edges(nid, edge_type)

    def neighbours(self, nid: NodeID, edge_type: str | None = None) -> Iterable[NodeID]:
        return self.graph.neighbours(nid, edge_type)

    # --- traverse: enumerate Γ-admissible candidate edges from src ---

    def admissible_edges_from(self, src: NodeID, edge_type: str,
                              candidates: Iterable[NodeID]) -> list[NodeID]:
        """Filter ``candidates`` to those tgt nodes for which (src, edge_type, tgt) is admissible."""
        out: list[NodeID] = []
        for tgt in candidates:
            if self.checker.check_edge(self.graph, src, edge_type, tgt):
                out.append(tgt)
        return out

    def admissible_moves(self, src: NodeID, edge_type: str,
                         candidates: Iterable[tuple[str, dict[str, Any] | None]]
                         ) -> list[tuple[str, dict[str, Any], float]]:
        """Enumerate admissible (tgt_type, tgt_attrs) candidates, returning each
        with its summed weight under Γ. Multiple matching productions contribute
        their weights additively; if no production matches, the candidate is
        omitted entirely.

        Materialises a scratch tgt for each candidate (the weight terms may
        reference tgt attrs). The scratch node is removed before returning.
        """
        src_node = self.graph.node(src)
        out: list[tuple[str, dict[str, Any], float]] = []
        for tgt_type, tgt_attrs in candidates:
            attrs = dict(tgt_attrs or {})
            scratch = self.graph._insert_node(tgt_type, attrs)
            try:
                tgt_node = self.graph.node(scratch)
                matching = self.checker.grammar.candidates(src_node.type, edge_type, tgt_type)
                weight_total = 0.0
                admitted = False
                for p in matching:
                    if not p.admits(src_node, tgt_node, self.graph):
                        continue
                    admitted = True
                    weight_total += p.evaluate_weight(src_node, tgt_node, self.graph)
                if admitted:
                    out.append((tgt_type, attrs, weight_total))
            finally:
                self.graph._delete_node(scratch)
        return out

    def is_edge_admissible(self, src: NodeID, edge_type: str,
                           candidate_tgt_type: str,
                           candidate_tgt_attrs: dict[str, Any] | None = None) -> bool:
        """Probe: would an edge to a (type, attrs) candidate be admissible?

        Fast path: if no matching production's where-clause references the tgt
        binding, evaluate where-clauses with only src bound — no node materialised.
        Slow path: insert a scratch tgt node, run C, remove it.
        """
        src_node = self.graph.node(src)
        matching = self.checker.grammar.candidates(
            src_node.type, edge_type, candidate_tgt_type)
        if not matching:
            return False
        if all(p.where is None or p.tgt.var not in collect_vars(p.where) for p in matching):
            for p in matching:
                env = {p.src.var: src}
                if p.where is None or p.where.evaluate(env, self.graph):
                    return True
            return False
        scratch = self.graph._insert_node(candidate_tgt_type, candidate_tgt_attrs or {})
        try:
            return self.checker.check_edge(self.graph, src, edge_type, scratch)
        finally:
            self.graph._delete_node(scratch)

    def tick(self, max_steps: int = 100_000, detect_cycles: bool = False) -> int:
        """One agent tick — run every graph-resident Rule node to
        fixed point. Delegates to the Rust runtime
        (`substrate_rs.Substrate.tick`). Single-shot path for tests
        and scripted use; long-running agents use `start_agent`.

        `detect_cycles` (default False, PROTOCOL §9) additionally
        terminates on a REPEATED GRAPH STATE — the honest fixpoint test
        for a float relaxation, whose fixed point is generically not
        representable in float64 and so dithers at one ULP forever under
        exact-equality termination. Mechanical pass-through."""
        return self.graph._inner.tick(max_steps, detect_cycles)

    # --- autonomous agent loop -----------------------------------------
    #
    # World adapters call start_agent on the substrate they share with
    # the agent's mind. After that, writes are fire-and-forget — the
    # Rust tick thread picks them up. quiesce() blocks until rule
    # propagation has settled, which is what tests want.

    def start_agent(self, tick_rate_hz: float = 100.0,
                    max_steps_per_tick: int = 100_000) -> None:
        """Start the agent's autonomous tick loop. Idempotent: if the
        agent is already running, this is a no-op."""
        if self.graph._inner.agent_running():
            return
        self.graph._inner.start_agent(
            tick_rate_hz, 1, 1, max_steps_per_tick)

    def stop_agent(self) -> None:
        """Stop the agent's tick loop. No-op if not running."""
        self.graph._inner.stop_agent()

    def agent_running(self) -> bool:
        return self.graph._inner.agent_running()

    def quiesce(self, timeout: float = 2.0,
                  stable_ticks: int = 2) -> bool:
        """Block until rule propagation appears to have settled.

        Polls the substrate's mutation counter: when `stable_ticks`
        consecutive sleeps see no edge/node insertions, the engine is
        assumed quiescent. Returns True on stable, False on timeout.

        For tests + interactive use only — production world adapters
        don't need this, they just keep writing and the agent picks
        up everything in its own time."""
        import time
        deadline = time.monotonic() + timeout
        prev = self._mutation_signature()
        stable = 0
        while time.monotonic() < deadline:
            time.sleep(0.005)
            curr = self._mutation_signature()
            if curr == prev:
                stable += 1
                if stable >= stable_ticks:
                    return True
            else:
                stable = 0
                prev = curr
        return False

    def _mutation_signature(self) -> tuple:
        return (self.graph._inner.node_count(),
                self.graph._inner.edge_count())

    @contextmanager
    def step_cache(self) -> Iterator[None]:
        """Enable a step-local cache for DSL evaluators (e.g. Neighbours).

        The graph must not be mutated inside the context — the cache assumes
        a frozen G snapshot. Conway's ``step`` collects all decisions before
        applying any mutations, satisfying this constraint.
        """
        self.graph._eval_cache = {}
        try:
            yield
        finally:
            self.graph._eval_cache = None


class Transaction:
    """Buffered mutation; commits atomically. Reads see uncommitted state."""

    def __init__(self, substrate: Substrate) -> None:
        self._s = substrate
        self._inserted_nodes: list[NodeID] = []
        self._inserted_edges: list[EdgeKey] = []
        self._committed = False

    def add_node(self, type: str, attrs: dict[str, Any] | None = None) -> NodeID:
        nid = self._s.graph._insert_node(type, attrs)
        self._inserted_nodes.append(nid)
        return nid

    def add_edge(self, src: NodeID, edge_type: str, tgt: NodeID,
                 attrs: dict[str, Any] | None = None) -> EdgeKey:
        if not self._s.checker.check_edge(self._s.graph, src, edge_type, tgt):
            raise InadmissibleEdge(
                f"Γ rejects ({self._s.graph.node(src).type}) "
                f"-[{edge_type}]-> ({self._s.graph.node(tgt).type})"
            )
        key = self._s.graph._insert_edge(src, edge_type, tgt, attrs)
        self._inserted_edges.append(key)
        return key

    def _commit(self) -> None:
        self._committed = True

    def _rollback(self) -> None:
        if self._committed:
            return
        for key in reversed(self._inserted_edges):
            try:
                self._s.graph._delete_edge(key)
            except KeyError:
                pass
        for nid in reversed(self._inserted_nodes):
            try:
                self._s.graph._delete_node(nid)
            except KeyError:
                pass
