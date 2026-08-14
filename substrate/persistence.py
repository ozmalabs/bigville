"""Graph persistence — the agent's mind as a durable, inspectable artifact.

The substrate's whole stance is that the GRAPH is the memory (concepts, the
map, laws, grounded words are all nodes). Persistence therefore stores the
graph itself as JSON — human-readable, portable, and independent of the Python
class layout, so accumulated knowledge survives the code changes the substrate
keeps undergoing (a pickle of the agent object would not).

Two layers:
  * a type-aware value codec (``encode``/``decode``) that round-trips the value
    types the substrate uses — ``NodeID``, tuples, sets, ``Counter`` — through
    JSON, raising on anything it does not recognise so a mis-serialised field
    fails loudly rather than silently corrupting state; and
  * ``graph_to_dict``/``graph_from_dict``, which serialise a ``TypedGraph``
    faithfully, PRESERVING node ids — so every NodeID held in the agent's index
    dicts remains valid after a load, with no re-keying.
"""
from __future__ import annotations

from collections import Counter

from .graph import Edge, EdgeKey, Node, NodeID, TypedGraph


def encode(v):
    """JSON-safe encoding of a substrate value. Primitives pass through; the
    substrate's structural types get a dunder-tagged form. Raises on types it
    does not know (Term objects, dataclasses, threads) — those must be excluded
    by the caller, and the loud failure is how a mistake is caught."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, NodeID):
        return {"__nid__": v.value}
    if isinstance(v, Counter):
        return {"__counter__": encode(dict(v))}
    if isinstance(v, dict):
        if all(isinstance(k, str) for k in v):
            return {k: encode(val) for k, val in v.items()}
        return {"__dict__": [[encode(k), encode(val)] for k, val in v.items()]}
    if isinstance(v, tuple):
        return {"__tuple__": [encode(x) for x in v]}
    if isinstance(v, set):
        return {"__set__": [encode(x) for x in v]}
    if isinstance(v, frozenset):
        return {"__fset__": [encode(x) for x in v]}
    if isinstance(v, list):
        return [encode(x) for x in v]
    raise TypeError(f"persistence: cannot encode value of type {type(v).__name__}: {v!r}")


def decode(v):
    """Inverse of :func:`encode`."""
    if isinstance(v, dict):
        if "__nid__" in v:
            return NodeID(v["__nid__"])
        if "__counter__" in v:
            return Counter(decode(v["__counter__"]))
        if "__dict__" in v:
            return {decode(k): decode(val) for k, val in v["__dict__"]}
        if "__tuple__" in v:
            return tuple(decode(x) for x in v["__tuple__"])
        if "__set__" in v:
            return {decode(x) for x in v["__set__"]}
        if "__fset__" in v:
            return frozenset(decode(x) for x in v["__fset__"])
        return {k: decode(val) for k, val in v.items()}
    if isinstance(v, list):
        return [decode(x) for x in v]
    return v


def _native_substrate(g: TypedGraph):
    """The underlying `_native.Substrate` behind a substrate_rs-backed TypedGraph."""
    return g._inner._inner if hasattr(g._inner, "_inner") else g._inner


def graph_to_dict(g: TypedGraph) -> dict:
    """Serialise via the native `substrate_rs` round-trip — preserves node ids,
    node attrs, AND edge attrs ({nodes, edges, next_id}). The substrate_rs-backed
    TypedGraph no longer has the old pure-Python `_nodes`/`_edges`/`_next_id`."""
    return _native_substrate(g).graph_to_dict()


def graph_from_dict(d: dict) -> TypedGraph:
    """Rebuild a TypedGraph from :func:`graph_to_dict`, PRESERVING node ids (the
    native `graph_from_dict` does) so NodeIDs stored elsewhere (the agent's index
    dicts, agent_root/gamma_root) stay valid. Also rebuilds the Python edge-attr
    index — substrate_rs stores edge attrs but exposes them only via this dict,
    so `out_edges`/`edge()` read them from `_index_edges`."""
    g = TypedGraph()
    _native_substrate(g).graph_from_dict(d)
    for ed in d.get("edges", []):
        key = EdgeKey(NodeID(ed["src"]), ed["type"], NodeID(ed["tgt"]))
        g._index_edges[key] = Edge(key=key, attrs=dict(ed.get("attrs", {})))
        g._index_by_type.setdefault(ed["type"], set()).add(key)
    return g
