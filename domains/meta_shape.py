"""meta_shape — MECHANICAL host glue for the meta-shape grain.

ARCHITECTURE (CLAUDE.md's rule, and the point of this whole rung): every
DECISION here lives in Rust or in graph rules. This module does exactly two
mechanical things:

  1. `item_signature(type_, attrs)` — translate a taught item into the sd
     loop's own relation-set format. Pure destructuring: no conditionals over
     graph state, no ranking, no choice.
  2. `observe(agent, type_, attrs)` — write that signature into the graph as a
     `ShapeObservation` and hand off to `seeds/meta_shape_growth.json`'s rules.
     Pure ingest, exactly as `induce_concern` writes an `Observation` for the
     `sd_*` loop.

The recognise / transform / infer / mint decisions are
`shape_decode.rs::{ms_score_shapes, ms_pick, eval_meta_shape_mint}` and the
`msg_*` rules. Nothing in this file decides anything.

WHY THE SIGNATURE LOOKS LIKE IT DOES
------------------------------------
`SHAPE_AUDIT.md` §2.5 defect 1: `teach.py:93` built the scored text as
`" ".join(str(v) for v in attrs.values() if isinstance(v, str)).lower()` —
discarding every attribute KEY, every non-string VALUE, and the node TYPE.
An item `Concept{name:"quintuple", definition:"multiply a number by five",
multiplier_factor:5.0}` was scored as `"quintuple multiply a number by five"`.

Here nothing is discarded. Each relation is EXACTLY TWO elements —
`[predicate, value]` — because that is what makes the whole existing sd ladder
apply unchanged:

  * `anti_unify_values` generalises element-wise only over EQUAL-LENGTH tuples,
    so fixed-arity relations keep the predicate FIXED and wild only the value;
    variable-length relations would wild the predicate away too;
  * `covers_value` requires equal relation counts in the same ORDER, so the
    relations are sorted by predicate — which also makes the representation
    order-independent, the defect `SHAPE_AUDIT.md` §3.1 documents in the
    `CapabilityAxis` key ("order-dependent and truncated at three").

Lowercasing happens HERE and only here: `recognise_meta_shape`'s standing
contract is that the caller supplies final-form text.
"""
from __future__ import annotations

from typing import Any, Optional

#: The node type the `msg_*` rules match on, and the edge that hangs it off the
#: agent hub — mirroring `induce_concern`'s `Observation` / `observed` pair.
OBSERVATION_TYPE = "ShapeObservation"
OBSERVED_EDGE = "observed_shape"
#: The meta-shape grain's OWN codebook epoch. Deliberately not the sd loop's
#: `codebook_epoch`: minting a MetaShape does not grow the `ShapeSignature`
#: codebook, so re-arming the other grain's observations would be churn.
EPOCH_ATTR = "meta_codebook_epoch"


def item_signature(type_: str, attrs: dict) -> list:
    """`(type_, attrs)` → a relation set. Mechanical destructuring, no decision.

    ``Concept{name:"quintuple", definition:"multiply a number by five",
    multiplier_factor:5.0}`` becomes::

        [["definition", "multiply a number by five"],
         ["is_a", "concept"],
         ["multiplier_factor", "5.0"],
         ["name", "quintuple"]]

    The node TYPE becomes an explicit `is_a` relation; every attribute KEY
    becomes a relation PREDICATE; every VALUE (string or not) becomes its
    argument. Sorted by predicate so the representation is order-independent.
    """
    rels = [["is_a", str(type_).lower()]]
    for k, v in (attrs or {}).items():
        rels.append([str(k).lower(), str(v).lower()])
    rels.sort(key=lambda r: r[0])
    return rels


def _agent_node(agent):
    """The agent hub node, however the caller's object exposes it."""
    for name in ("agent", "agent_node", "_agent"):
        n = getattr(agent, name, None)
        if n is not None:
            return n
    return None


def observe(agent, type_: str, attrs: dict, *, run: bool = True) -> Optional[Any]:
    """Write one `ShapeObservation` and let the rules decide about it.

    Mechanical ingest only. Returns the observation node id, or None when the
    caller has no live graph (so `teach()` degrades to exactly its old
    behaviour rather than raising).
    """
    s = getattr(agent, "s", None)
    if s is None:
        return None
    ag = _agent_node(agent)
    try:
        if ag is not None and not s.node(ag)["attrs"].get(EPOCH_ATTR):
            s.set_attr(ag, EPOCH_ATTR, 0)
        oid = s.add_node(OBSERVATION_TYPE, {
            "signature": item_signature(type_, attrs),
            "status": "pending",
            "item_type": str(type_),
        })
        if ag is not None:
            s.add_edge(ag, OBSERVED_EDGE, oid)
        if run:
            native = getattr(s, "_inner", s)
            native.run_rules()
        return oid
    except Exception:
        return None
