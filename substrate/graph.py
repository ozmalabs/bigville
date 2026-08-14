"""Typed-graph G — now backed by `substrate_rs.Substrate` (the
Rust-bound graph store the audio / speech / video facilities also
target). The Python `TypedGraph` class stays as the API the agent
code expects (Node, Edge, EdgeKey, NodeID dataclasses; out_edges /
in_edges / _insert_node / _delete_edge / _edges etc.), but its
state lives in the Rust substrate. Same graph, two views.

The `NodeID` exported here IS the substrate_rs `NodeID` class — the
two were previously different Python types with identical `.value`
attrs but inequal under `==`; unification means agent code and
audio/speech facilities now mint NodeIDs from the same class and
can compare freely.

Node, Edge, EdgeKey remain Python dataclasses — they're built on
demand from the underlying store's query results and exposed to
callers exactly as the previous Python TypedGraph did.

Mutation API (`_insert_node`, `_insert_edge`, `_delete_*`) bypasses
admissibility — those are the reflection / engine-internal paths
the agent's existing code uses to construct graph data without
going through the Γ-checker. They map to the substrate_rs
`add_edge_unchecked` / `remove_edge_unchecked` primitives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from substrate_rs import Substrate as _RustSubstrate
from substrate_rs._native import NodeID as NodeID


@dataclass
class Node:
    id: NodeID
    type: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeKey:
    src: NodeID
    edge_type: str
    tgt: NodeID

    def __hash__(self) -> int:
        # NodeID is a Rust PyClass with its own __hash__ returning
        # the underlying u32 value. Combine src + tgt values with
        # the edge_type to keep collisions rare.
        return hash((self.src.value, self.edge_type, self.tgt.value))


@dataclass
class Edge:
    key: EdgeKey
    attrs: dict[str, Any] = field(default_factory=dict)


class _WriteThroughAttrs(dict):
    """A node's attrs that persist in-place mutations back to the substrate via
    ``set_attr``. The agent pervasively does ``node(x).attrs[k] = v`` and expects
    it to stick — which it did when the backend was a live Python graph. The
    Rust-backed ``node()`` returns a FRESH dict each call from the immutable node
    record, so without write-through every such mutation was silently lost."""

    def __init__(self, inner, nid, initial, py_store):
        super().__init__(initial)
        self._inner = inner
        self._nid = nid
        self._py = py_store  # per-node shadow for non-serializable attr values

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        try:
            self._inner.set_attr(self._nid, k, v)
            self._py.pop(k, None)            # serializable → substrate-backed
        except Exception:
            # Not substrate-serializable (a Python function/closure/object the
            # agent keeps as in-memory state, e.g. a thread's `step` callable).
            # Hold it in the Python shadow so it survives node() re-reads, as it
            # did when the backend was a live Python dict.
            self._py[k] = v

    def setdefault(self, k, default=None):
        if k not in self:
            self[k] = default
        return self[k]

    def update(self, *args, **kw):
        for k, v in dict(*args, **kw).items():
            self[k] = v

    def __delitem__(self, k):
        super().__delitem__(k)
        self._py.pop(k, None)
        try:
            self._inner.set_attr(self._nid, k, None)  # ≈ remove (reads as None)
        except Exception:
            pass

    def pop(self, k, *default):
        had = k in self
        v = super().pop(k, *default)
        if had:
            self._py.pop(k, None)
            try:
                self._inner.set_attr(self._nid, k, None)
            except Exception:
                pass
        return v


class TypedGraph:
    """View onto a `substrate_rs.Substrate` shaped as the Python
    TypedGraph the agent's code expects.

    The state — every node and edge — lives in the inner Rust
    substrate. The Python wrappers (Node / Edge / EdgeKey
    dataclasses) are built on demand from the inner substrate's
    query results.
    """

    def __init__(self, inner: _RustSubstrate | None = None) -> None:
        # The Rust-bound substrate that holds the actual graph state.
        # When `inner is None`, we mint a fresh one (the common case
        # for tests + the standalone agent constructor). Callers that
        # need to SHARE state across multiple facilities (audio +
        # speech + agent) pass the same `inner` to every TypedGraph
        # they construct — same underlying store, multiple Python
        # views.
        self._inner = inner if inner is not None else _RustSubstrate()
        # Python-side index of edges written via THIS TypedGraph
        # (i.e. via `_insert_edge` / `_delete_edge`). The graph-
        # rewrite engine uses `_edges.values()` for the no-endpoint-
        # bound match path; the Rust store doesn't expose an "all
        # edges with their types" iterator, so we mirror writes here.
        # Edges written directly to the Rust store by audio / speech
        # / video facilities (e.g. AcousticSign.denotes) are NOT in
        # this index, but they ARE visible via `neighbours(...)` /
        # `out_edges(..., edge_type)` queries when one endpoint is
        # known — which covers every other Rule match path.
        self._index_edges: dict[EdgeKey, Edge] = {}
        self._index_by_type: dict[str, set[EdgeKey]] = {}
        # Per-endpoint edge-type indices: source/target NodeID value ->
        # {edge_type: count}. Maintained alongside `_index_by_type` on every
        # `_insert_edge` / `_delete_edge` / `_delete_node`. Lets the
        # `edge_type=None` slow path of out_edges/in_edges enumerate the
        # edge types incident to ONE node in O(distinct_types_on_node)
        # instead of scanning every edge of every type (the previous
        # `any(k.src == nid for k in keys)` per type was O(all_edges) per
        # node — quadratic when every node is walked, e.g. ARC's dense grid).
        # Counts (not a bare set) so a type drops only when its LAST edge on
        # that node is removed — behaviour-identical to the membership scan.
        self._out_types_by_node: dict[int, dict[str, int]] = {}
        self._in_types_by_node: dict[int, dict[str, int]] = {}
        # Per-node shadow (keyed by id value) for attr values substrate_rs can't
        # serialise — Python functions/closures the agent stores in node.attrs.
        self._py_attrs: dict[int, dict] = {}
        # Optional cache populated by Substrate.step_cache() — used by
        # DSL evaluators to memoize neighbour-set lookups across
        # multiple admissibility probes that share an immutable G
        # snapshot (e.g., during a Conway step).
        self._eval_cache: dict | None = None

    # --- queries ---

    def node(self, nid: NodeID) -> Node:
        """Wrap the inner substrate's dict-shaped node record in the
        Node dataclass the agent code uses.

        Transparent page-in: if the node isn't resident (paged out to the disk
        tier), a recall-on-miss hook (installed by the daemon's paged memory)
        pages its cluster back — recall_by_shape restores the SAME node ids — and
        we retry once. Without the hook, behaviour is unchanged (KeyError)."""
        try:
            n = self._inner.node(nid)
        except KeyError:
            n = None
        if n is None:
            hook = getattr(self, "_recall_on_miss", None)
            if hook is not None:
                try:
                    hook(nid)
                except Exception:  # noqa: BLE001 — recall is best-effort
                    pass
                try:
                    n = self._inner.node(nid)
                except KeyError:
                    n = None
        if n is None:
            raise KeyError(nid)
        py = self._py_attrs.setdefault(nid.value, {})
        merged = dict(n.get("attrs", {}))
        merged.update(py)  # Python-only attrs (functions/closures) shadow the substrate
        return Node(id=nid, type=n["type"],
                    attrs=_WriteThroughAttrs(self._inner, nid, merged, py))

    def edge(self, key: EdgeKey) -> Edge:
        """The inner substrate doesn't expose per-edge attrs as a
        first-class object yet — we build the Edge wrapper from the
        EdgeKey alone. Edge attrs are not used by the agent today;
        if they become load-bearing later, this returns an empty
        dict that callers can extend."""
        if not self._inner.has_edge(key.src, key.edge_type, key.tgt):
            raise KeyError(key)
        # Edge attrs live ONLY in the Python `_index_edges` (substrate_rs stores
        # but doesn't expose per-edge attrs). Return the LIVE attrs dict so the
        # agent's `edge(k).attrs[x] = v` (e.g. production-index renumbering)
        # persists — and is then visible to out_edges' `_edge_attrs`.
        indexed = self._index_edges.get(key)
        if indexed is not None:
            return Edge(key=key, attrs=indexed.attrs)
        return Edge(key=key, attrs={})

    def has_node(self, nid: NodeID) -> bool:
        return self._inner.has_node(nid)

    def has_edge(self, src: NodeID, edge_type: str, tgt: NodeID) -> bool:
        return self._inner.has_edge(src, edge_type, tgt)

    # Iterators below snapshot the underlying index set before yielding,
    # mirroring the Python TypedGraph's tuple-then-yield pattern so the
    # graph stays REAL-TIME EDITABLE under iteration (an `add_edge`
    # during a walk doesn't disturb the in-flight iterator). The Rust
    # substrate is internally consistent under mutation; this layer
    # adds the snapshot semantics callers depend on.

    def nodes(self, type: str | None = None) -> Iterator[Node]:
        for nid in tuple(self._inner.nodes(type)):
            n = self._inner.node(nid)
            if n is not None:
                yield Node(id=nid, type=n["type"],
                           attrs=dict(n.get("attrs", {})))

    def out_edges(self, nid: NodeID,
                  edge_type: str | None = None) -> Iterator[Edge]:
        # The Rust substrate's `neighbours` returns NodeIDs. To
        # reconstruct Edge objects with EdgeKey.edge_type, we either
        # need the edge type (passed in) or we walk every edge type
        # used in the graph. The all-types case is rare on the agent
        # hot path — falls back to enumerating known edge types per
        # node via the diagnostic helper.
        if edge_type is not None:
            for tgt in tuple(self._inner.neighbours(nid, edge_type)):
                key = EdgeKey(nid, edge_type, tgt)
                yield Edge(key=key, attrs=self._edge_attrs(key))
            return
        # All-types: enumerate every type the inner store reports for
        # this source node. The cost is O(distinct_edge_types) per
        # call; callers that want a hot-path iteration pass an
        # edge_type filter.
        seen: set[str] = set()
        for et in self._all_out_edge_types(nid):
            if et in seen:
                continue
            seen.add(et)
            for tgt in tuple(self._inner.neighbours(nid, et)):
                key = EdgeKey(nid, et, tgt)
                yield Edge(key=key, attrs=self._edge_attrs(key))

    def in_edges(self, nid: NodeID,
                 edge_type: str | None = None) -> Iterator[Edge]:
        if edge_type is not None:
            for src in tuple(self._inner.in_neighbours(nid, edge_type)):
                key = EdgeKey(src, edge_type, nid)
                yield Edge(key=key, attrs=self._edge_attrs(key))
            return
        seen: set[str] = set()
        for et in self._all_in_edge_types(nid):
            if et in seen:
                continue
            seen.add(et)
            for src in tuple(self._inner.in_neighbours(nid, et)):
                key = EdgeKey(src, et, nid)
                yield Edge(key=key, attrs=self._edge_attrs(key))

    def _edge_attrs(self, key: "EdgeKey") -> dict:
        """The LIVE edge attrs from the per-edge index `_insert_edge` maintains
        (substrate_rs stores but doesn't expose edge attrs, so this is the sole
        source of truth). Returned by reference so the agent's
        `for e in out_edges(...): e.attrs[x] = v` (e.g. goal-priority update)
        persists, matching the old live-Python-graph semantics. `{}` (throwaway)
        for edges not tracked in the index."""
        indexed = self._index_edges.get(key)
        return indexed.attrs if indexed is not None else {}

    def neighbours(self, nid: NodeID,
                   edge_type: str | None = None) -> Iterator[NodeID]:
        for tgt in tuple(self._inner.neighbours(nid, edge_type)):
            yield tgt

    def _all_out_edge_types(self, nid: NodeID) -> Iterator[str]:
        """Best-effort enumeration of every edge type leaving `nid`.
        Used only by the `edge_type=None` slow path of out_edges /
        in_edges. The inner substrate doesn't expose this directly,
        so we read the per-node edge-type set from the grammar's
        productions (Γ tells us every admissible edge type out of
        a given node-type, which is a superset of what's present).
        Callers that need exact behaviour should pass an edge_type."""
        try:
            inner = self._inner._inner if hasattr(self._inner, "_inner") \
                else self._inner
            grammar = inner.grammar_to_json() if hasattr(
                inner, "grammar_to_json") else {}
            n = self._inner.node(nid)
            if n is None:
                return
            ntype = n["type"]
            seen: set[str] = set()
            for prod in grammar.get("productions", []):
                if prod.get("src", {}).get("type") == ntype:
                    et = prod.get("edge_type")
                    if et and et not in seen:
                        seen.add(et)
                        yield et
        except Exception:
            seen = locals().get("seen", set())
        # Edges inserted via `_insert_edge` (unchecked) may have NO grammar
        # production — notably the `child.*` term-structure edges from
        # term_to_subgraph. The grammar enumeration misses those, so also yield
        # every inserted out-edge type for THIS node from the per-source
        # edge-type index (O(distinct_types_on_node), not O(all_edges)). The
        # index is the same source of truth `_insert_edge` maintains; the
        # set of types yielded is identical to the previous
        # `any(k.src == nid for k in keys)` membership scan.
        for et in self._out_types_by_node.get(nid.value, ()):
            if et not in seen:
                seen.add(et)
                yield et

    def _all_in_edge_types(self, nid: NodeID) -> Iterator[str]:
        try:
            inner = self._inner._inner if hasattr(self._inner, "_inner") \
                else self._inner
            grammar = inner.grammar_to_json() if hasattr(
                inner, "grammar_to_json") else {}
            n = self._inner.node(nid)
            if n is None:
                return
            ntype = n["type"]
            seen: set[str] = set()
            for prod in grammar.get("productions", []):
                if prod.get("tgt", {}).get("type") == ntype:
                    et = prod.get("edge_type")
                    if et and et not in seen:
                        seen.add(et)
                        yield et
        except Exception:
            seen = locals().get("seen", set())
        # Mirror of _all_out_edge_types: include inserted in-edge types the
        # grammar enumeration misses (unchecked edges with no production),
        # read from the per-target edge-type index (O(distinct_types_on_node)).
        for et in self._in_types_by_node.get(nid.value, ()):
            if et not in seen:
                seen.add(et)
                yield et

    # --- internal mutation (callers: Π in primitives.py, reflection
    # in dsl.py — both bypass admissibility, gated externally) ---

    def _alloc_id(self) -> NodeID:
        """Kept for parity with the old API; the inner substrate now
        owns ID allocation. Callers that imported this method were
        all wrappers around `_insert_node` — left here as a stub that
        mints + immediately deletes a sentinel node to mimic
        "I want a fresh NodeID without committing data" semantics
        is more confusing than just using _insert_node directly,
        so we raise to force callers to do the right thing."""
        raise NotImplementedError(
            "_alloc_id is no longer separately exposed — call _insert_node "
            "with a real type and attrs instead.")

    def _insert_node(self, type: str,
                     attrs: dict[str, Any] | None = None) -> NodeID:
        return self._inner.add_node(type, attrs)

    def _insert_edge(self, src: NodeID, edge_type: str, tgt: NodeID,
                     attrs: dict[str, Any] | None = None) -> EdgeKey:
        # The agent code uses `_insert_edge` to bypass admissibility —
        # it's the reflection / engine-internal write path. The Rust
        # substrate's `add_edge` is admissibility-checked; the bypass
        # is `add_edge_unchecked` on the inner ._inner.
        inner = self._inner._inner if hasattr(self._inner, "_inner") \
            else self._inner
        inner.add_edge_unchecked(src, edge_type, tgt, attrs)
        key = EdgeKey(src, edge_type, tgt)
        is_new = key not in self._index_edges
        self._index_edges[key] = Edge(key=key, attrs=dict(attrs or {}))
        self._index_by_type.setdefault(edge_type, set()).add(key)
        if is_new:
            self._endpoint_index_add(key)
        return key

    def _endpoint_index_add(self, key: "EdgeKey") -> None:
        ob = self._out_types_by_node.setdefault(key.src.value, {})
        ob[key.edge_type] = ob.get(key.edge_type, 0) + 1
        ib = self._in_types_by_node.setdefault(key.tgt.value, {})
        ib[key.edge_type] = ib.get(key.edge_type, 0) + 1

    def _endpoint_index_remove(self, key: "EdgeKey") -> None:
        ob = self._out_types_by_node.get(key.src.value)
        if ob is not None:
            n = ob.get(key.edge_type, 0) - 1
            if n <= 0:
                ob.pop(key.edge_type, None)
                if not ob:
                    self._out_types_by_node.pop(key.src.value, None)
            else:
                ob[key.edge_type] = n
        ib = self._in_types_by_node.get(key.tgt.value)
        if ib is not None:
            n = ib.get(key.edge_type, 0) - 1
            if n <= 0:
                ib.pop(key.edge_type, None)
                if not ib:
                    self._in_types_by_node.pop(key.tgt.value, None)
            else:
                ib[key.edge_type] = n

    def _delete_edge(self, key: EdgeKey) -> None:
        self._inner.remove_edge(key.src, key.edge_type, key.tgt)
        existed = self._index_edges.pop(key, None) is not None
        bucket = self._index_by_type.get(key.edge_type)
        if bucket is not None:
            bucket.discard(key)
        if existed:
            self._endpoint_index_remove(key)

    def _delete_node(self, nid: NodeID) -> None:
        # The inner substrate's remove_node also drops incident edges
        # from the Rust store; mirror that on the Python index so we
        # don't leak EdgeKeys whose endpoints are gone.
        stale: list[EdgeKey] = [k for k in self._index_edges
                                if k.src == nid or k.tgt == nid]
        for key in stale:
            if self._index_edges.pop(key, None) is not None:
                self._endpoint_index_remove(key)
            bucket = self._index_by_type.get(key.edge_type)
            if bucket is not None:
                bucket.discard(key)
        self._inner.remove_node(nid)

    def _set_attr(self, nid: NodeID, key: str, value: Any) -> None:
        self._inner.set_attr(nid, key, value)

    def _set_type(self, nid: NodeID, new_type: str) -> None:
        self._inner.set_type(nid, new_type)

    # --- diagnostics ---

    def node_count(self) -> int:
        return self._inner.node_count()

    def edge_count(self) -> int:
        return self._inner.edge_count()

    # --- compat hooks for code that pokes at internals -----------------

    @property
    def _nodes(self) -> dict[NodeID, Node]:
        """Materialised dict of every node, built on demand. The Rust
        substrate stores nodes internally; agent code that iterates
        `self._nodes.items()` gets a live snapshot. Don't mutate via
        this dict — go through `_insert_node` / `_delete_node`."""
        out: dict[NodeID, Node] = {}
        for nid in tuple(self._inner.nodes(None)):
            n = self._inner.node(nid)
            if n is not None:
                out[nid] = Node(id=nid, type=n["type"],
                                attrs=dict(n.get("attrs", {})))
        return out

    @property
    def _edges(self) -> dict[EdgeKey, Edge]:
        """Edges written via THIS TypedGraph's `_insert_edge`. Used by
        graph_rewrite.py's no-endpoint-bound match path. Does not
        include edges written directly to the underlying Rust store
        by other facilities (audio / speech / video); those are
        visible via `neighbours(...)` queries when one endpoint is
        known, which the matcher reaches for whenever it can."""
        return self._index_edges

    def edges_of_type(self, edge_type: str) -> Iterator[Edge]:
        """Iterate every edge of `edge_type` from the agent's index.
        Faster than `_edges.values() if e.key.edge_type == et` —
        avoids the predicate filter."""
        for key in tuple(self._index_by_type.get(edge_type, ())):
            edge = self._index_edges.get(key)
            if edge is not None:
                yield edge
