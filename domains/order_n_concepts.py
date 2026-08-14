"""Meta-ability: the agent assesses N-ORDER dimensional concepts.

A quantity sampled along a dimension has finite differences of every order —
  order 0 = the value, 1 = slope / velocity, 2 = curvature / acceleration, …
The agent COMPOSES the order-N concept as a graph Term-tree (recursive `Minus` over
the dimension's sample `Attr`s) and ASSESSES it via the native evaluator. One
mechanism subsumes every feature we hand-built:

  • order-2 over FREQUENCY  = spectral curvature   ⇒  a formant PEAK (curvature < 0)
  • order-1 over FREQUENCY  = spectral tilt
  • order-1 over TIME       = velocity             ⇒  a formant TRANSITION
  • order-2 over TIME       = acceleration

No Python computes the value — the Term-tree is the agent's program and it runs on
the substrate's own evaluator. This is the dimension-and-order-general form of
formant_features (a single order-2-freq case) and dynamics_features (order-1-time).
See [[ozma_concepts_in_gamma]] / [[ozma_meta_abilities_are_leverage]] /
[[ozma_agent_writes_its_own_code]].
"""
from __future__ import annotations

from substrate_rs import Attr, Minus, Var, Plus, Abs


class _Pred:
    __slots__ = ("_json",)

    def __init__(self, d):
        self._json = d


def _as_dict(x):
    return x.to_dict() if hasattr(x, "to_dict") else x


def _minus(a, b):
    """order-1 difference, tolerant of Term objects OR predicate dicts — so the
    samples can themselves be composed terms (e.g. an ArgMax formant frequency)."""
    if hasattr(a, "to_dict") and hasattr(b, "to_dict"):
        return Minus(a=a, b=b)
    return {"type": "Minus", "a": _as_dict(a), "b": _as_dict(b)}


def nth_order_terms(samples: list, order: int) -> list:
    """The order-N finite differences (Term-trees) of an ordered sample list.
    order 0 returns the samples themselves; each order drops one element. Samples
    may be Term objects or predicate dicts (so any composed quantity can be
    differenced over a dimension)."""
    t = list(samples)
    for _ in range(order):
        t = [_minus(t[i + 1], t[i]) for i in range(len(t) - 1)]
    return t


def total_variation_term(samples: list, order: int):
    """A scalar Term: the total order-N variation = Σ |order-N differences| — the
    agent's assessment of HOW MUCH order-N structure a quantity has over a
    dimension (order-1-time total = total formant movement; order-2-freq total =
    total spectral peakiness)."""
    d = nth_order_terms(samples, order)
    if not d:
        return None
    return d[0] if len(d) == 1 else Plus(items=tuple(Abs(x) for x in d))


def _samples(sample_attrs):
    s = Var("s")
    return [Attr(s, a) for a in sample_attrs]


def compose_order_n_features(substrate, sample_attrs: list, order: int,
                             dimension: str, prefix: str) -> list:
    """The agent composes one order-N concept PER POSITION over the dimension — the
    local order-N finite difference there (a peak is a local order-2-freq extreme; a
    transition a local order-1-time value). Each becomes a feature_kind=order_n
    Concept carrying the composed Term-tree. Returns [(concept_id, name)]."""
    diffs = nth_order_terms(_samples(sample_attrs), order)
    existing = {substrate.node(c)["attrs"].get("name")
                for c in substrate.nodes("Concept")
                if substrate.node(c)["attrs"].get("feature_kind") == "order_n"}
    created = []
    for i, d in enumerate(diffs):
        name = f"{prefix}_o{order}_{i}"
        if name in existing:
            continue
        c = substrate.add_node("Concept", {
            "name": name, "feature_kind": "order_n", "order": order,
            "dimension": dimension, "position": i,
            "sample_attrs": list(sample_attrs),
            "predicate": _as_dict(d), "origin": "phonology",
            "composed_by": "agent"})
        created.append((c, name))
    return created


def assess(substrate, sign, concept):
    """Assess (evaluate) an order-N concept on a sign via the native evaluator —
    the agent's order-N program executes in Rust, no Python arithmetic."""
    a = substrate.node(concept)["attrs"]
    try:
        return substrate.evaluate(_Pred(a["predicate"]), {"s": sign})
    except Exception:
        return None


__all__ = ["nth_order_terms", "total_variation_term",
           "compose_order_n_features", "assess"]
