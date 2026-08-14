"""JSON encoders/decoders for Term and Grammar.

Mirrors the G-subgraph reflection in ``dsl.term_to_subgraph`` /
``grammar.Grammar.to_subgraph`` but uses JSON dicts so the frontend (or any
external tool) can read and write Γ as text. Round-trips are lossless for
all term types in the registry.

Term JSON shape: ``{"type": "Filter", "source": {...}, "var_name": "n", "predicate": {...}}``.
Grammar JSON shape: ``{"productions": [{"provenance": ..., "src": {...}, ...}]}``.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from .dsl import Term, _TERM_REGISTRY
from .grammar import Grammar, NodePattern, Production


def term_to_json(term: Term) -> dict[str, Any]:
    out: dict[str, Any] = {"type": type(term).__name__}
    for f in dataclasses.fields(term):
        v = getattr(term, f.name)
        if isinstance(v, Term):
            out[f.name] = term_to_json(v)
        elif isinstance(v, (tuple, list)) and v and isinstance(v[0], Term):
            out[f.name] = [term_to_json(x) for x in v]
        else:
            out[f.name] = v
    return out


def term_from_json(d: dict[str, Any]) -> Term:
    cls_name = d.get("type")
    if cls_name not in _TERM_REGISTRY:
        raise ValueError(f"unknown Term type: {cls_name}")
    cls = _TERM_REGISTRY[cls_name]
    kwargs: dict[str, Any] = {}
    expected = {f.name for f in dataclasses.fields(cls)}
    for k, v in d.items():
        if k == "type" or k not in expected:
            continue
        if isinstance(v, dict) and v.get("type") in _TERM_REGISTRY:
            kwargs[k] = term_from_json(v)
        elif isinstance(v, (list, tuple)) and v and isinstance(v[0], dict) and v[0].get("type") in _TERM_REGISTRY:
            # The Rust substrate stores Python lists as Value::Tuple,
            # so a roundtripped where-clause's `items=[t1, t2, ...]`
            # comes back as a tuple. Accept either shape.
            kwargs[k] = tuple(term_from_json(x) for x in v)
        else:
            kwargs[k] = v
    return cls(**kwargs)


def grammar_to_json(g: Grammar) -> dict[str, Any]:
    return {
        "productions": [
            {
                "provenance": p.provenance,
                "src": {"type": p.src.type, "var": p.src.var},
                "edge_type": p.edge_type,
                "tgt": {"type": p.tgt.type, "var": p.tgt.var},
                "where": term_to_json(p.where) if p.where is not None else None,
                "weight": term_to_json(p.weight) if p.weight is not None else None,
            }
            for p in g.productions
        ]
    }


def grammar_from_json(d: dict[str, Any]) -> Grammar:
    prods = []
    for pd in d.get("productions", []):
        prods.append(Production(
            src=NodePattern(pd["src"]["type"], pd["src"]["var"]),
            edge_type=pd["edge_type"],
            tgt=NodePattern(pd["tgt"]["type"], pd["tgt"]["var"]),
            where=term_from_json(pd["where"]) if pd.get("where") else None,
            weight=term_from_json(pd["weight"]) if pd.get("weight") else None,
            provenance=pd.get("provenance", ""),
        ))
    return Grammar(prods)
