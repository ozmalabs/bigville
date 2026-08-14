"""Analogical thinking — Jabberwock's cross-domain SHAPE finder.

Per user: 'part of jabberwock allows it to look for similar shapes -
make this accessible when thinking like this. Thinking needs to be
n-abstractable (eg think harder and more abstractly if you aren't
happy with the answer)'.

Jabberwock already has analogy.py for Term-tree skeletonization and
order_n_concepts.py for finite-difference abstraction. Those work
on perceptual Term-trees. What this module adds: analogical-shape
matching across CONCEPT-LEVEL vocabulary, with a DIAL for abstraction
order n.

The thinking process:
  · Given a directive (a Directive node, or just two Mts to bridge)
  · For each concept in source Mt, scan target Mt for structural match
  · Dial of abstraction order n:
      n=0  exact name overlap
      n=1  category match + definition keyword overlap
      n=2  functional-role match (input/output/regulator/storage/etc.)
      n=3  abstract-principle match (homeostatic, predictive,
           pattern-completing, integrative, gating, selecting)
      n=4  meta-shape match (the principle of how it operates
           regardless of what it operates on)
  · If the agent isn't satisfied with answers at one n, it raises
    n and tries again — abstracting further.

When a match is found, an Analogy graph node is created with the
order_n attr + source + target + rationale. Jabberwock's graph
gains the bridge.
"""
from __future__ import annotations

import itertools
import re
import weakref
from typing import Any


#: DIRECTIONAL_CORRESPONDENCE_RESULTS.md Sec "a real new failure appeared":
#: `_CONCEPT_READING_CACHE`/`_METASHAPE_COUNT_CACHE`/`_VOCAB_KEYS_CACHE`
#: (below) are module-level performance caches keyed in part by `id(sub)` --
#: a real, PRE-EXISTING hazard (present since this module's first shape-math
#: landing, unrelated to any one rung's own additions) that this rung's own
#: regression suite tripped over live: CPython reuses a garbage-collected
#: object's memory address, and a test suite that boots many `Substrate`/
#: `WorldAdapter` instances in one process (every `tests/test_*.py` file
#: that uses the `agent`/`boot_core()` fixtures does exactly this) can
#: therefore get a STALE cache hit keyed against a completely different,
#: already-freed graph -- silently returning another substrate's vocabulary
#: reading for the CURRENT one. Measured live: combining this rung's own
#: `tests/test_directional_correspondence.py` with
#: `tests/test_blob_edge_analogy_extension.py` (which populates these
#: caches heavily on the real large-corpus boot) and the deduction test
#: files in one `pytest` invocation made a richness comparison that is
#: deterministic in isolation come back corrupted (`_vocabulary_keys`
#: silently serving a stale axis list). `id(sub)` is necessary in the key
#: (a `NodeID`'s own integer recurs across every substrate by construction,
#: so `id(sub)` is the only thing disambiguating them today) but not
#: SUFFICIENT once ids can be recycled. The fix does not touch what is
#: cached or the caching pattern itself (CLAUDE.md permits caching) -- only
#: the identity key, via a `WeakKeyDictionary` token whose lifetime is tied
#: to the object it names, so no two live-or-dead substrates can ever share
#: one, regardless of address reuse.
_SUB_TOKEN_COUNTER = itertools.count()
_SUB_TOKENS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _sub_token(sub) -> int:
    """A stable per-substrate identity token, safe against `id()` reuse --
    see the module comment above. Falls back to `id(sub)` (the OLD,
    collision-prone behaviour) only when `sub` cannot be weakly referenced
    (defensive; every real `Substrate`/`WorldAdapter` observed can be)."""
    try:
        tok = _SUB_TOKENS.get(sub)
        if tok is None:
            tok = next(_SUB_TOKEN_COUNTER)
            _SUB_TOKENS[sub] = tok
        return tok
    except TypeError:
        return id(sub)


# The order-2/3/4 classifier vocabulary (FunctionalRole / ShapePrinciple /
# MetaShape) was here as three Python dicts. It is now GRAPH DATA, seeded in
# seeds/shape_vocabulary.json and read via the helpers below (keyword matching
# is a Term run by Rust). Adding a shape = adding a node to that seed, not
# editing this file.


#: The wild marker the shape-math Terms use. It is WRAPPED in a 1-element
#: sequence inside a pattern (`["y", ["·?·"]]`) — verified against the live
#: engine, which returns witnesses in exactly that form and refuses `Covers`
#: on a bare marker.
WILD = "·?·"


def _tokens(text: str) -> set[str]:
    """Tokenize text + name. Strip casing + non-letters."""
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def _is_wild(v) -> bool:
    """Is this witness leaf the wild marker (bare or in its wrapped form)?
    Pure form test on a held Term's own output — no judgement."""
    if v == WILD:
        return True
    return (isinstance(v, (list, tuple)) and len(v) == 1 and v[0] == WILD)


def _concept_text(substrate, concept_node) -> tuple[str, str, str]:
    a = substrate.node(concept_node)["attrs"]
    return (
        str(a.get("name", "")).lower(),
        str(a.get("category", "")).lower(),
        str(a.get("definition", "")).lower(),
    )


# ---------------------------------------------------------------------------
# The classifier vocabulary is GRAPH DATA (seeds/shape_vocabulary.json):
# FunctionalRole / ShapePrinciple nodes (each with a `keywords` list) and
# MetaShape nodes wired -has_principle-> their constituent principles. The
# "which keyword is in this text" decision is a Term run by the Rust evaluator
# (substring test), not a Python keyword loop. These helpers are mechanical
# adapter glue: read the vocabulary nodes, hand each to the Term, collect hits.
# ---------------------------------------------------------------------------
def _native_eval(substrate):
    s = getattr(substrate, "s", substrate)
    return getattr(s, "_inner", s)


_TOKEN_START = re.compile(r"(?:^|(?<=[^a-z0-9]))[a-z0-9]")


def _token_starts(text: str) -> list[str]:
    """Every suffix of `text` that begins at a TOKEN START. Purely mechanical
    string destructuring — no decision, no graph read.

    This is the argument change that anchors the vocabulary match. The keyword
    test below is `StringIndexOf(h, kw) == 0` over these suffixes, so a keyword
    matches only where a WORD begins:

      * `"io"` no longer matches `"operat|io|n"` (index 6 in the only suffix
        that contains it) — 39.6% of every vocabulary hit in the booted graph
        (`ANALOGICAL_THINKING_SHAPE_MATH_PREREG.md` §2.2);
      * `"gate"` no longer matches `"ag|gregate|s"`;
      * stems still work — `"regulat"` matches `"regulation"`, `"communicat"`
        matches `"communicates"` — because the test is a PREFIX test, which is
        what a stem keyword means;
      * multi-word keywords (`"align by role"`, `"anti-unif"`) still work,
        because a suffix runs to the end of the text.

    No new Rust: this is a different ARGUMENT to `StringIndexOf`, not a new
    Term. `_` is a separator, so `typographic_hierarchy` matches `hierarch`.
    """
    text = (text or "").lower()
    return [text[m.start():] for m in _TOKEN_START.finditer(text)]


def _kw_hit_term(haystacks: list) -> dict:
    """Term: does ANY keyword of the node bound to Var 'v' begin ANY of
    `haystacks`? Two nested `Exists` over one `Eq(StringIndexOf(...), 0)`.

    The decision ("does this vocabulary entry apply to this text") is made by
    the Rust evaluator, exactly as before; only the anchoring changed.
    """
    V = lambda n: {"type": "Var", "name": n}
    L = lambda x: {"type": "Lit", "value": x}
    return {"type": "Exists",
            "source": {"type": "Attr", "node": V("v"), "key": "keywords"},
            "var_name": "kw",
            "predicate": {"type": "Exists",
                          "source": L(list(haystacks)),
                          "var_name": "h",
                          "predicate": {"type": "Eq",
                                        "a": {"type": "StringIndexOf",
                                              "haystack": V("h"), "needle": V("kw")},
                                        "b": L(0)}}}


def _vocab_nodes(substrate, voc_type: str) -> list:
    sub = getattr(substrate, "s", substrate)
    try:
        return list(sub.nodes(voc_type))
    except Exception:
        return []


def _vocab_hits(substrate, voc_type: str, text: str) -> set[str]:
    """Names of vocabulary nodes of `voc_type` whose keywords hit `text`.

    Unchanged interface, unchanged flat-set return. The MATCH is now anchored
    at token starts (`_token_starts`) — the same Term shape, a different
    haystack.
    """
    sub = getattr(substrate, "s", substrate)
    native = _native_eval(substrate)
    term = _kw_hit_term(_token_starts(text))
    hits = set()
    for n in _vocab_nodes(substrate, voc_type):
        if native.evaluate(term, {"v": n}):
            nm = sub.node(n)["attrs"].get("name")
            if nm:
                hits.add(nm)
    return hits


def _vocab_hits_by_slot(substrate, voc_type: str, slots: dict) -> dict:
    """`{vocabulary name -> frozenset(slot names it was hit in)}`.

    The information `SHAPE_AUDIT.md` §2.5 found destroyed one grain up and
    `META_SHAPE_FIRST_CLASS_RESULTS.md` §2 restored there: WHICH TYPED SLOT the
    evidence came from. A concept NAMED `gate` and a concept whose definition
    happens to mention gating are not the same evidence, and the flat
    `name + " " + definition` concatenation could not tell them apart.

    Mechanical: run the same held Term once per slot, collect.
    """
    sub = getattr(substrate, "s", substrate)
    native = _native_eval(substrate)
    out: dict = {}
    nodes = _vocab_nodes(substrate, voc_type)
    for slot, text in slots.items():
        if not text:
            continue
        term = _kw_hit_term(_token_starts(text))
        for n in nodes:
            if native.evaluate(term, {"v": n}):
                nm = sub.node(n)["attrs"].get("name")
                if nm:
                    out.setdefault(nm, set()).add(slot)
    return {k: frozenset(v) for k, v in out.items()}


#: Per-concept memo of the slot-addressed vocabulary reading. A pure
#: performance cache over an unchanging read (CLAUDE.md permits caching; the
#: substrate stays the source of truth). Keyed by (graph identity, node).
_CONCEPT_READING_CACHE: dict = {}


def _concept_slots(substrate, concept_node) -> dict:
    """The concept's TYPED SLOTS, kept apart instead of concatenated."""
    name, _, defn = _concept_text(substrate, concept_node)
    return {"name": name, "definition": defn}


def _concept_reading(substrate, concept_node) -> dict:
    """`{"role": {..}, "principle": {..}, "shape": {..}}`, each mapping a
    vocabulary name to the frozenset of slots that evidenced it."""
    sub = getattr(substrate, "s", substrate)
    key = (_sub_token(sub), concept_node)
    cached = _CONCEPT_READING_CACHE.get(key)
    if cached is not None:
        return cached
    slots = _concept_slots(substrate, concept_node)
    roles = _vocab_hits_by_slot(substrate, "FunctionalRole", slots)
    prins = _vocab_hits_by_slot(substrate, "ShapePrinciple", slots)
    shapes: dict = {}
    if prins:
        for sh in _vocab_nodes(substrate, "MetaShape"):
            nm = sub.node(sh)["attrs"].get("name")
            if not nm:
                continue
            ev: set = set()
            for p in sub.neighbours(sh, "has_principle"):
                pn = sub.node(p)["attrs"].get("name")
                if pn in prins:
                    ev |= set(prins[pn])
            if ev:
                shapes[nm] = frozenset(ev)
    out = {"role": roles, "principle": prins, "shape": shapes}
    _CONCEPT_READING_CACHE[key] = out
    return out


def _concept_functional_roles(substrate, concept_node) -> set[str]:
    """Order-2 abstraction: which functional roles does this concept
    play? Vocabulary + keyword-match are graph data / a Term in Rust."""
    return set(_concept_reading(substrate, concept_node)["role"])


def _concept_abstract_principles(substrate, concept_node) -> set[str]:
    """Order-3 abstraction: which abstract principles does this concept
    embody? Read off the seeded ShapePrinciple vocabulary via a Term."""
    return set(_concept_reading(substrate, concept_node)["principle"])


def _concept_meta_shapes(substrate, concept_node) -> set[str]:
    """Order-4 abstraction: meta-shapes of operation. A MetaShape is hit when
    any of its has_principle neighbours is among the concept's principles —
    membership read from the graph (has_principle edges), not a Python dict.

    (The 1-of-N disjunction is UNCHANGED and deliberately so: it is
    `shape_hits`' documented MAC-recall-set semantics, and narrowing it was not
    registered by this rung's prereg. Recorded in §2.3 of the prereg as a
    separate finding, not repaired here.)
    """
    return set(_concept_reading(substrate, concept_node)["shape"])


def _list_concepts(substrate, mt_node) -> list:
    return list(substrate.neighbours(mt_node, "has_concept"))


def _find_mt(substrate, name: str):
    for mt in substrate.nodes("Microtheory"):
        if str(substrate.node(mt)["attrs"].get("name", "")) == name:
            return mt
    return None


def shape_hits(substrate, text: str) -> set[str]:
    """The set of MetaShapes whose constituent principles (has_principle edges)
    have a keyword that is a substring of `text`. Vocabulary = graph data;
    keyword match = a Term run by Rust. Public helper for analysis tooling that
    wants the agent's own shape reading of an arbitrary string."""
    text = (text or "").lower()
    if not text:
        return set()
    principles = _vocab_hits(substrate, "ShapePrinciple", text)
    if not principles:
        return set()
    sub = getattr(substrate, "s", substrate)
    shapes = set()
    for sh in sub.nodes("MetaShape"):
        prins = {sub.node(p)["attrs"].get("name") for p in sub.neighbours(sh, "has_principle")}
        if principles & prins:
            shapes.add(sub.node(sh)["attrs"].get("name"))
    return shapes


# ---------------------------------------------------------------------------
# Meta-shape realisation counts — the RELATIVE within-order-4 quantity.
# The seven organising meta-shapes all sit at the SAME abstraction order (n=4);
# order_n cannot separate them. What places one above another is the COUNT of
# concepts that realise it (its feature count over the population) — a relative
# quantity, not a hand-set weight. Read at query time (cached per population
# size, since it scans every Concept) so the agent's self-shape ratio is
# derived, never asserted.
# ---------------------------------------------------------------------------
_METASHAPE_COUNT_CACHE: dict[tuple, dict[str, int]] = {}


def metashape_realisation_counts(substrate) -> dict[str, int]:
    """For each MetaShape, how many of the agent's Concepts realise it
    (has_principle → ShapePrinciple keyword hit). The relative feature count
    that places the meta-shapes against one another at order 4."""
    sub = getattr(substrate, "s", substrate)
    try:
        concepts = list(sub.nodes("Concept"))
    except Exception:
        return {}
    key = (_sub_token(sub), len(concepts))
    cached = _METASHAPE_COUNT_CACHE.get(key)
    if cached is not None:
        return cached
    tally: dict[str, int] = {}
    for c in concepts:
        for ms in _concept_meta_shapes(sub, c):
            tally[ms] = tally.get(ms, 0) + 1
    _METASHAPE_COUNT_CACHE[key] = tally
    return tally


# ---------------------------------------------------------------------------
# THE FAC STAGE — structural alignment by HELD shape-math Terms.
#
# `RULES_AS_SHAPE_DESIGN_SPIKE.md` §4.2 imports the creator's June 2026
# diagnosis of THIS faculty: "the agent's bucket IS the MAC stage treated as
# the verdict — with no FAC stage", prescription "make the bucket a FILTER, not
# a verdict — escalate every surface survivor into an explicit
# structural-alignment pass". Everything above this line is the MAC stage.
# Everything below is the FAC stage, and every judgement in it is made by a
# Rust Term (`AntiUnifyWitness`, `FixedCount`, `Covers`), never by Python.
#
# WHAT IS AND IS NOT COMPUTABLE ON THIS POPULATION — measured, not assumed
# (`ANALOGICAL_THINKING_SHAPE_MATH_PREREG.md` §2.1, §3.3):
#
#   * A `Concept` here has essentially NO relational edges — 114 of 10,775
#     carry any outgoing edge at all. Relational alignment, the thing
#     structure-mapping is normally about, HAS NO INPUT here. Saying so is the
#     honest result; building it would be a no-op dressed as a fix.
#   * `AntiUnifyWitness` over a SINGLE pair's signature adds nothing over the
#     set intersection already present: aligning two concept signatures by
#     predicate makes the predicate correspondence the identity map, so the
#     template's fixed leaves are exactly "the attributes that are equal".
#     Registered as a NO-GO before building.
#   * What the operator uniquely provides is the WITNESS — the difference. Two
#     pairs whose witnesses AGREE realise the same transform, and are therefore
#     the two corner-pairs of one parallelogram. That is
#     `RULE_REFERENCE_LAYER_SIZING_RESULTS.md` §4's operation at the concept
#     grain, it is Gentner's systematicity computed rather than asserted, and
#     it needs no concept edges.
# ---------------------------------------------------------------------------
#: Marker for "this vocabulary entry is not evidenced in this concept". Shared
#: ABSENCE is not shared structure, so a leaf fixed at this marker is projected
#: out of the template before the structure is counted.
_ABSENT = "-"

_VOCAB_KEYS_CACHE: dict = {}


def _lit(x) -> dict:
    return {"type": "Lit", "value": x}


def _vocabulary_keys(substrate) -> list:
    """The canonical, sorted axis list every concept vector is laid out on.

    Fixed arity and fixed position is what makes `AntiUnifyWitness` applicable
    at all: it generalises element-wise over EQUAL-LENGTH tuples. Two concepts
    laid out on the same axes are positionally aligned by construction.
    """
    sub = getattr(substrate, "s", substrate)
    key = (_sub_token(sub), sum(len(_vocab_nodes(substrate, t))
                        for t in ("FunctionalRole", "ShapePrinciple", "MetaShape")))
    cached = _VOCAB_KEYS_CACHE.get(key)
    if cached is not None:
        return cached
    keys = []
    for axis, voc_type in (("role", "FunctionalRole"),
                           ("principle", "ShapePrinciple"),
                           ("shape", "MetaShape")):
        for n in _vocab_nodes(substrate, voc_type):
            nm = sub.node(n)["attrs"].get("name")
            if nm:
                keys.append((axis, str(nm)))
    keys.sort()
    _VOCAB_KEYS_CACHE[key] = keys
    return keys


def _concept_shape_vector(substrate, concept_node) -> list:
    """A concept as a fixed-arity relation vector over the held vocabulary.

    `[[axis:name, slots-or-absent], ..., ["category", cat-or-absent]]`, sorted
    and identical in length and position for every concept in the graph. Each
    relation is EXACTLY TWO elements for the reason `domains/meta_shape.py`
    documents: `anti_unify_values` generalises element-wise over equal-length
    tuples, so a 2-element relation keeps the PREDICATE fixed and wilds only
    the value.

    The value is the sorted slot list the evidence came from — so two concepts
    are structurally aligned on an axis only when they are evidenced THE SAME
    WAY, not merely when a set intersection is non-empty. Mechanical
    destructuring; nothing here judges.
    """
    reading = _concept_reading(substrate, concept_node)
    _, cat, _ = _concept_text(substrate, concept_node)
    vec = []
    for axis, nm in _vocabulary_keys(substrate):
        slots = reading.get(axis, {}).get(nm)
        vec.append(["%s:%s" % (axis, nm),
                    "|".join(sorted(slots)) if slots else _ABSENT])
    vec.append(["category", cat or _ABSENT])
    return vec


def _pair_witness(substrate, vec_a: list, vec_b: list) -> dict:
    """The held `AntiUnifyWitness` + `FixedCount` over one candidate pair.

    Returns `{shared, name_shared, fixed_count, transform}` where

      * `shared`   — the axes the TEMPLATE fixes at real evidence (shared
                     absence projected out: absence is not structure);
      * `name_shared` — how many of those were evidenced in the concept's own
                     NAME slot. The `pred_principles` tier
                     `META_SHAPE_FIRST_CLASS_RESULTS.md` §2 landed one grain
                     up: an item whose slot IS the shape beats an item that
                     merely talks about it. A COUNT, not a weight.
      * `transform` — the canonicalised WITNESS pair: the residue
                     `AntiUnify` discards. Two pairs with equal `transform`
                     realise the same delta — the parallelogram.

    Every judgement (what generalises, what stays fixed, how many leaves are
    fixed) is made by the Rust evaluator. This function assembles arguments and
    destructures results.
    """
    native = _native_eval(substrate)
    out = {"shared": [], "name_shared": 0, "fixed_count": 0, "transform": ()}
    if not vec_a or len(vec_a) != len(vec_b):
        return out
    try:
        template, sigmas = native.evaluate(
            {"type": "AntiUnifyWitness", "values": _lit([vec_a, vec_b]), "wild": WILD}, {})
        fixed = native.evaluate(
            {"type": "FixedCount", "pattern": _lit(list(template)), "wild": WILD}, {})
    except Exception:
        return out
    shared = []
    for rel in template:
        if not isinstance(rel, (list, tuple)) or len(rel) != 2:
            continue
        pred, val = rel[0], rel[1]
        if _is_wild(pred) or _is_wild(val) or val == _ABSENT:
            continue
        shared.append((str(pred), str(val)))
    try:
        fixed = int(fixed)
    except Exception:
        fixed = 0
    out["shared"] = shared
    out["name_shared"] = sum(1 for _, v in shared if "name" in v.split("|"))
    out["fixed_count"] = fixed
    out["transform"] = _canon_transform(sigmas)
    return out


# ---------------------------------------------------------------------------
# BLOB-EDGE CORRESPONDENCE, this site (BLOB_EDGE_ANALOGY_EXTENSION_PREREG.md /
# _RESULTS.md) -- extends the SAME `seeds/blob_edge_correspondence.json`
# recognize/mint rules (`blob_mint`/`blob_recognize`/`blob_no_collapse`,
# reused VERBATIM, unedited) the predecessor rung built for
# `reflective_faculty.py::_run_math_bridge`, to `_pair_witness`'s real
# operands here: two `Concept` graph nodes, not two `ShapeSignature` nodes.
# `seeds/blob_edge_concept_correspondence.json` (Gamma-only, additive) admits
# the Concept-typed about_a/about_b/links_a/links_b edges the merged seed's
# own productions do not. `_pair_witness` itself, above, is UNCHANGED.
#
# Deliberately NOT importing `reflective_faculty.record_correspondence` /
# `_agent_node_id` / `_resolve_blob_edge` -- `_relation_cue_index`'s own
# docstring already states the house convention this file follows:
# "same pattern, own cache -- no cross-import." `reflective_faculty.py`
# lazily imports FROM this module; this module imports nothing back.
#
# BATCHING WAS TRIED AND MEASURED UNSAFE, reverted to the merged site's own
# per-write shape -- recorded here because the PREREG named this exact risk
# and it is what was actually found, not a hypothetical. First attempt:
# `record_pair_correspondence` wrote every pending `Correspondence` with NO
# `run_rules()` call, and `find_analogies` called `run_rules()` ONCE after
# PASS 1's whole loop (batch of up to 7970 pending nodes on the real
# `computer_architecture` corpus). Measured result: `blob_mint`'s guard
# (`Not(Exists(BlobEdge with matching transform_key)))` does NOT see
# same-pass sibling mints -- the engine's matcher is semi-naive (matches are
# found against a graph snapshot, effects applied after), so of the 7970
# pending Correspondences sharing only 139 distinct transform_keys, ALL 7970
# minted (7970 BlobEdge nodes, 7831 of them exact-duplicate transform_keys)
# instead of 139. This is a genuine multi-write race the merged site's own
# call sites (<=66 pending nodes/call, run_rules() per write) never
# exercised. BLOB_EDGE_ANALOGY_EXTENSION_RESULTS.md Sec4 has the numbers.
#
# Fix: `record_pair_correspondence` calls `run_rules()` per write, exactly
# `record_correspondence`'s own shape -- re-measured on the same corpus:
# 139 BlobEdge nodes, zero duplicates, matching the pre-wiring instrumented
# count exactly. Real, measured cost of correctness at this site's scale:
# ~40s for `computer_architecture` x itself (7970 writes, ~5ms/write
# overhead, vs ~2.5s unmodified -- ~16x) against ~1.3x at the smaller real
# Mts (`mathematics`/`communication`, ~100 writes) -- reported honestly in
# RESULTS, not hidden. No caller in the standing tree exercises the large
# corpus today (`reframing_proposer.py`'s only live caller compares its own
# 4-faculty Mt); the cost is real only if/when a future caller requests a
# self-comparison over one of the large domain Mts. `find_analogies` still
# calls `run_rules()` once after PASS 1 as a harmless idempotent safety net
# (nothing is left pending by the time it runs).
# ---------------------------------------------------------------------------

def _agent_node_id(substrate):
    """The single Agent hub node, found by scan -- local copy of
    `reflective_faculty._agent_node_id`'s exact body (no cross-import, see
    above)."""
    sub = getattr(substrate, "s", substrate)
    try:
        nodes = sub.nodes("Agent")
    except Exception:
        return None
    return nodes[0] if nodes else None


def _canon_pair_shared(shared) -> str:
    """Canonicalise `_pair_witness`'s own `out["shared"]` -- already a
    filtered (non-wild, non-absent), deterministically-ordered list of
    `(pred, val)` pairs (order follows `_vocabulary_keys`'s global sort) --
    into a stable transform_key string. `sorted()` first for defence-in-depth
    even though the input order is already canonical; `_shared_shape`'s own
    `_canon_shared_shape` (reflective_faculty.py) serialises a differently-
    shaped input (the raw AntiUnify template, wild rows included) and is not
    reused here for that reason (Sec1.2 of the PREREG)."""
    import json as _json
    try:
        return _json.dumps(sorted(tuple(x) for x in shared))
    except Exception:
        return ""


def record_pair_correspondence(substrate, node_a, node_b, witness):
    """MECHANICAL INGEST: write a `Correspondence` node from an ALREADY-
    COMPUTED `_pair_witness` result plus `about_a`/`about_b`/
    `observed_correspondence` edges to the two REAL `Concept` nodes, then run
    the engine so `blob_mint`/`blob_recognize`/`blob_no_collapse` (UNEDITED)
    decide -- never Python. `run_rules()` is called PER WRITE, exactly
    `record_correspondence`'s own shape -- see the batching note above for
    why an earlier once-per-batch attempt was measured unsafe (a genuine
    duplicate-BlobEdge race) and reverted.

    Returns the node id written, or `None` (honest no-op, no exception) when
    either node id is missing or the substrate has no live `add_node` -- the
    same non-match shape `record_correspondence` returns for its own
    unwritable case."""
    sub = getattr(substrate, "s", substrate)
    if node_a is None or node_b is None or not hasattr(sub, "add_node"):
        return None
    key = _canon_pair_shared(witness.get("shared") or [])
    try:
        cid = sub.add_node("Correspondence", {
            "status": "pending",
            "shared_count": int(witness.get("fixed_count") or 0),
            "transform_key": key,
        })
        sub.add_edge(cid, "about_a", node_a)
        sub.add_edge(cid, "about_b", node_b)
        ag = _agent_node_id(substrate)
        if ag is not None:
            sub.add_edge(ag, "observed_correspondence", cid)
        native = getattr(sub, "_inner", sub)
        native.run_rules()
        return cid
    except Exception:
        return None


def _resolve_blob_edge(substrate, transform_key: str):
    """Mechanical read-back: the held `BlobEdge` node carrying this
    `transform_key`, if any -- local copy of
    `reflective_faculty._resolve_blob_edge`'s exact pattern (no cross-import,
    see above). Never a decision -- the rule already decided `status`; this
    only finds the node the rule's `Exists` check already confirmed exists."""
    sub = getattr(substrate, "s", substrate)
    try:
        for n in sub.nodes("BlobEdge"):
            if sub.node(n)["attrs"].get("transform_key") == transform_key:
                return n
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# DIRECTIONAL CORRESPONDENCE (DIRECTIONAL_CORRESPONDENCE_PREREG.md /
# _RESULTS.md) -- `_pair_witness`'s own {shared, name_shared, fixed_count,
# transform} is SYMMETRIC by construction (REASONING_FACILITY_BRIDGE_
# RESULTS.md Sec3, confirmed there and not re-litigated here: source_concept/
# target_concept in a returned analogy record reflect SEARCH ORDER, never a
# causal or logical direction). This section adds a genuinely ASYMMETRIC
# signal -- structural-elaboration RICHNESS, how many axes of the SAME
# `_vocabulary_keys` vocabulary each concept in a pair is independently
# evidenced on -- and a NEW node type, `DirectionalCorrespondence`, to carry
# whatever direction verdict that signal (or its absence) supports.
#
# RICHNESS is a plain count of non-`_ABSENT` entries in one side's OWN
# `_concept_shape_vector` -- `sum(1 for _, v in vec if v != _ABSENT)`, the
# SAME arithmetic-reduction idiom `_pair_witness`'s own `name_shared` count
# already uses (line ~458 above), not a new judgement engine. AN EARLIER
# ATTEMPT tried to reuse the held `FixedCount` Rust Term directly on one
# side's vector (zero new Rust, maximal reuse) and was MEASURED, not
# assumed, to be wrong: `FixedCount`'s `wild` sentinel is wrapped in a
# 1-tuple at the call site (`term.rs`'s `TermNode::FixedCount` arm) because
# it is designed to recognise an ENTIRE wilded ROW from `AntiUnify`'s own
# output convention (a row replaced wholesale by the wild marker: a 1-tuple
# `(WILD,)`), not an `_ABSENT` string sitting as one of two elements INSIDE
# an intact 2-element row -- `is_wild`'s tuple-vs-bare-value comparison
# (`term.rs::is_wild`) never matches a bare string leaf against the
# 1-tuple-wrapped wild value, so BOTH leaves of every row (the axis name AND
# the possibly-absent value) count as "fixed" unconditionally. Measured
# live, not merely reasoned about: `FixedCount(vec, wild=_ABSENT)` returns
# EXACTLY `2*len(vec)` for every vector tried, regardless of how many
# entries are `_ABSENT` -- a CONSTANT, not even weakly correlated with axis
# richness. Reported here rather than silently corrected: the RIGHT tool
# was the plain Python count already used one scope up in this same file,
# not a Term whose contract does not cover this shape.
#
# `DirectionalCorrespondence` is DELIBERATELY NOT a `ShapeSignature` --
# `runners/dsl/src/shape_decode.rs::load_parts` loads EVERY `ShapeSignature`
# node carrying a `name`+`signature` attr into the live `ShapeDecode`
# codebook pool regardless of its `kind` attr (`kind` is read but never used
# to filter eligibility -- confirmed by reading `load_parts` before writing
# any code here), so tagging an unverified hypothesis `ShapeSignature
# {kind:"knowledge_logical_hypothesis"}` would NOT keep it out of
# `inference_generation.resolve_implication_gap`'s live decode pool: the
# moment its `signature` shape matched a real gap's goal, it would compete
# for a real modus-ponens mint on a real `SmEntity`, silently, regardless of
# `kind`. The only genuinely safe gate is a node-TYPE boundary, which is
# what `DirectionalCorrespondence` is. Promotion into a real
# `ShapeSignature{kind:"knowledge_logical"}` (where it DOES become live) is
# a separate, explicit, NEVER-automatic step --
# `domains/propositional_deduction.py::mint_logical_schema_from_analogy`.
# ---------------------------------------------------------------------------

def _axis_richness(vec: list) -> int:
    """How many axes of `vec` (a `_concept_shape_vector` output) are
    EVIDENCED (value != `_ABSENT`) -- pure arithmetic over an
    already-computed vector, the SAME reduction idiom `_pair_witness`'s own
    `name_shared` uses. See the module-level comment above for why this is
    NOT delegated to the held `FixedCount` Term (measured wrong for this
    shape, not merely judged unnecessary)."""
    return sum(1 for _, v in (vec or []) if v != _ABSENT)


def record_directional_correspondence(substrate, node_a, node_b,
                                       vec_a: list, vec_b: list, witness: dict):
    """MECHANICAL INGEST: write a `DirectionalCorrespondence` node from an
    ALREADY-COMPUTED `_pair_witness` result plus each side's own
    `_axis_richness`, then run the engine so `direction_a_source`/
    `direction_b_source`/`direction_symmetric`/`direction_no_correspondence`
    (`seeds/directional_correspondence.json`) DECIDE the direction --
    never Python. `run_rules()` is called PER WRITE, mirroring
    `record_pair_correspondence`'s own proven-safe shape -- though for a
    different reason here: `DirectionalCorrespondence` carries no novelty/
    dedup guard at all (every witness computation gets its OWN node, exactly
    like `Correspondence` itself), so there is no cross-write mint race to
    guard against the way `BlobEdge` minting needed one; per-write is simply
    the established convention at this call site, kept for consistency
    rather than because a batching hazard was found here too.

    Returns the node id written, or `None` (honest no-op, no exception) when
    either node id is missing or the substrate has no live `add_node`."""
    sub = getattr(substrate, "s", substrate)
    if node_a is None or node_b is None or not hasattr(sub, "add_node"):
        return None
    try:
        cid = sub.add_node("DirectionalCorrespondence", {
            "status": "pending",
            "shared_count": int(witness.get("fixed_count") or 0),
            "richness_a": _axis_richness(vec_a),
            "richness_b": _axis_richness(vec_b),
            "transform_key": _canon_pair_shared(witness.get("shared") or []),
        })
        sub.add_edge(cid, "about_a", node_a)
        sub.add_edge(cid, "about_b", node_b)
        ag = _agent_node_id(substrate)
        if ag is not None:
            sub.add_edge(ag, "observed_directional_correspondence", cid)
        native = getattr(sub, "_inner", sub)
        native.run_rules()
        return cid
    except Exception:
        return None


def directional_hypothesis_for(substrate, corr_node) -> dict:
    """MECHANICAL READ-BACK: the direction verdict the engine ALREADY
    decided for one `DirectionalCorrespondence` node -- destructures the
    node's own `status` + `source_concept`/`target_concept` edges (written
    by the rule, never by Python), decides nothing.

    Returns `{direction, node, source_concept, target_concept, source_node,
    target_node, confidence}` where `direction` is one of `"a_source"`/
    `"b_source"` (a real, resolved directional hypothesis --
    `source_concept`/`target_concept` are then populated by NAME, not by
    which side was visited first in the search loop), `"symmetric"` (real
    structural correspondence, tied richness -- direction genuinely
    underdetermined, never forced), `"no_correspondence"` (no shared
    structure), or `"pending"`/`None` (the write did not resolve -- should
    not happen via `record_directional_correspondence`'s own call shape,
    reported rather than assumed impossible). `confidence` carries the raw
    numbers the direction was decided from (`shared_count`, `richness_a`,
    `richness_b`, `transform_key`), so a caller can inspect the basis for
    the verdict rather than trust it blindly."""
    sub = getattr(substrate, "s", substrate)
    if corr_node is None:
        return {"direction": None}
    a = sub.node(corr_node)["attrs"]
    out = {
        "direction": a.get("status"),
        "node": corr_node,
        "confidence": {
            "shared_count": a.get("shared_count"),
            "richness_a": a.get("richness_a"),
            "richness_b": a.get("richness_b"),
            "transform_key": a.get("transform_key"),
        },
    }
    if out["direction"] in ("a_source", "b_source"):
        src = sub.neighbours(corr_node, "source_concept")
        tgt = sub.neighbours(corr_node, "target_concept")
        if src:
            out["source_node"] = src[0]
            out["source_concept"] = sub.node(src[0])["attrs"].get("name")
        if tgt:
            out["target_node"] = tgt[0]
            out["target_concept"] = sub.node(tgt[0])["attrs"].get("name")
    return out


def _canon_transform(sigmas) -> tuple:
    """The witness pair, canonicalised into a hashable key. Pure form.

    `AntiUnifyWitness` returns per-instance sigmas as dicts keyed by a PATH
    tuple. Two candidate pairs whose canonicalised sigmas are identical differ
    from one another in exactly the same places, by exactly the same amounts —
    the concept-grain reading of `RULE_REFERENCE_LAYER_SIZING_RESULTS.md` §4's
    `P (a->b)` path set.
    """
    try:
        return tuple(tuple(sorted((tuple(p), str(v)) for p, v in dict(sig).items()))
                     for sig in sigmas)
    except Exception:
        return ()


def _covered_shapes(substrate, vec: list) -> set:
    """Order 4's STRUCTURAL path: `MetaShape`s whose held `signature` COVERS
    this concept's vector, decided by the Rust `Covers` Term.

    `META_SHAPE_FIRST_CLASS_RESULTS.md` §3 made a minted `MetaShape` carry a
    real anti-unified lgg pattern; the eleven SEEDED shapes carry none, so on a
    stock boot this path is DORMANT by construction — wired for the same reason
    that rung wired its own rung 3, and reported as dormant rather than as a
    win.
    """
    sub = getattr(substrate, "s", substrate)
    native = _native_eval(substrate)
    out = set()
    for sh in _vocab_nodes(substrate, "MetaShape"):
        a = sub.node(sh)["attrs"]
        sig = a.get("signature")
        if not sig:
            continue
        try:
            if native.evaluate({"type": "Covers", "pattern": _lit(list(sig)),
                                "instance": _lit(list(vec)), "wild": WILD}, {}):
                nm = a.get("name")
                if nm:
                    out.add(nm)
        except Exception:
            continue
    return out


def find_analogies(substrate, source_mt_name: str,
                    target_mt_names: list[str], order_n: int = 2,
                    min_score: int = 1) -> list[dict]:
    """The core thinking primitive. For each concept in source Mt,
    find concepts in target Mts that match at abstraction order n.

    order_n controls how abstract the matching is:
      n=0  exact name overlap
      n=1  shared category + definition keyword overlap
      n=2  shared functional role (scheduler, memory, gate, etc.)
      n=3  shared abstract principle (homeostasis, prediction, ...)
      n=4  shared meta-shape (feedback control, associative recall, ...)

    Higher n = more abstract = more cross-domain analogies.

    RANKING IS RELATIVE, not a fixed cross-order exchange rate. An
    analogy is placed by its POSITION on the abstraction axis — the
    HIGHEST order at which the pair matches (`order_n`) — and, within
    that order, by the COUNT of shared features (`feature_count`, a
    relative within-axis quantity). There is no hand-set "a meta-shape
    match is worth exactly 5x a keyword match" magnitude; a higher-order
    match simply outranks a lower-order one, and same-order matches are
    ordered by how many features they share.

    `min_score` is a floor on the total number of shared features
    (default 1 ⇒ keep any pair that matches at all).

    Returns list of {source_concept, target_concept, source_mt,
    target_mt, order_n, feature_count, features_total, rationale}.
    """
    source_mt = _find_mt(substrate, source_mt_name)
    if source_mt is None:
        return []

    target_mts = []
    for nm in target_mt_names:
        mt = _find_mt(substrate, nm)
        if mt is not None:
            target_mts.append((nm, mt))

    if not target_mts:
        return []

    # PASS 1 — MAC: every surface survivor, with its held structural witness
    # attached. Nothing is a verdict yet.
    raw = []
    for sc in _list_concepts(substrate, source_mt):
        for tgt_mt_name, tgt_mt in target_mts:
            for tc in _list_concepts(substrate, tgt_mt):
                rec = _compute_analogy(
                    substrate, sc, tc, order_n,
                    source_mt_name, tgt_mt_name)
                if rec is not None:
                    raw.append(rec)

    # BLOB-EDGE PERSISTENCE: `_compute_analogy` (via `_pair_witness` and
    # `record_pair_correspondence`) already ran the engine per write during
    # PASS 1 above — see the batching note at `record_pair_correspondence`'s
    # definition for why per-write, not once-per-batch. Nothing is left
    # pending by this point; this call is a harmless idempotent safety net,
    # not load-bearing for correctness.
    sub = getattr(substrate, "s", substrate)
    native = getattr(sub, "_inner", sub)
    if hasattr(native, "run_rules"):
        try:
            native.run_rules()
        except Exception:
            pass

    # PASS 2 — FAC: SYSTEMATICITY. Two candidate pairs whose held witnesses are
    # identical differ in exactly the same places by exactly the same amounts:
    # they are the two corner-pairs of one parallelogram, and each corroborates
    # the other. This is the only quantity here that no per-pair scorer, however
    # sharp, can produce — and it needs no concept edges, which this population
    # does not have (prereg §2.1).
    by_transform: dict = {}
    for rec in raw:
        t = rec["_transform"]
        if t:
            by_transform.setdefault(t, []).append(rec)

    # PASS 3 — the verdict, and the honest non-answer.
    results = []
    for rec in raw:
        corr = len(by_transform.get(rec["_transform"], ())) - 1
        final = _finalise_analogy(rec, max(corr, 0))
        if final and final["features_total"] >= min_score:
            results.append(final)
    return results


def _finalise_analogy(rec: dict, corroboration: int) -> dict | None:
    """MAC → FAC: an ABSTRACT-order claim is retained only if the structural
    stage supports it. Otherwise the pair falls back to the surface orders it
    genuinely has, and if it has none, the answer is **`None`**.

    This is the prescription in `RULES_AS_SHAPE_DESIGN_SPIKE.md` §4.2 —
    *"make the bucket a FILTER, not a verdict"* — applied literally. Orders 0
    and 1 are honestly-labelled surface similarity and are always kept. Orders
    2, 3 and 4 assert something stronger (*"shared functional role"*, *"shared
    meta-shape"*), so they must be either

      * ALIGNED — the held `AntiUnifyWitness` template fixes at least one axis
        at real, identically-evidenced structure, or
      * CORROBORATED — another pair in the same bridge realises the same
        transform,

    and a claim that is neither is a surface coincidence being reported as an
    abstraction. `META_SHAPE_FIRST_CLASS_RESULTS.md`'s load-bearing lesson,
    one grain over: a verdict that always answers can never produce a residual.
    """
    aligned = rec["_aligned_orders"]
    per_order = {k: v for k, v in rec["_per_order"].items()
                 if k < 2 or k in aligned or corroboration > 0}
    filtered = sorted(set(rec["_per_order"]) - set(per_order))
    if not per_order:
        return None
    top_order = max(per_order)
    out = dict(rec["_public"])
    out["order_n"] = top_order
    out["feature_count"] = per_order[top_order]
    out["features_total"] = sum(per_order.values())
    out["corroboration"] = corroboration
    out["struct_shared"] = rec["_struct_shared"]
    out["name_shared"] = rec["_name_shared"]
    parts = [p for k, p in rec["_rationale"] if k in per_order]
    if rec["_struct_shared"]:
        parts.append("structurally aligned on %d axis/axes (%d in the name slot)"
                     % (rec["_struct_shared"], rec["_name_shared"]))
    if corroboration:
        parts.append("corroborated by %d pair(s) realising the same transform"
                     % corroboration)
    if filtered:
        parts.append("WITHHELD at order(s) %s: surface overlap with no aligned "
                     "structure and no corroboration"
                     % ", ".join(str(k) for k in filtered))
    out["rationale"] = "; ".join(parts)
    return out


def _compute_analogy(substrate, sc, tc, order_n: int,
                       src_mt_name: str, tgt_mt_name: str
                       ) -> dict | None:
    """Compute the RELATIVE placement of an analogy between two concepts,
    scanning up to abstraction order `order_n`.

    Instead of summing hand-set per-order weights into an absolute score,
    this records, at every order, the COUNT of shared features. The pair's
    placement is then two relative quantities read off that record:

      · order_n      — the HIGHEST order at which the pair matches (its
                        POSITION on the abstraction axis). A meta-shape
                        match sits higher than a name-token match because
                        it is further up the axis, not because it was
                        multiplied by 5.
      · feature_count — how many features are shared AT that highest order
                        (a relative within-axis quantity; the tiebreaker
                        between two analogies that reach the same order).

    `features_total` (sum of shared features over all orders) is kept only
    as the match/no-match floor for `find_analogies`' `min_score`.

    **This function is now the MAC stage only.** It returns an UNFINALISED
    record carrying the per-order surface counts AND the held structural
    witness; `find_analogies` computes corroboration across the whole bridge
    and `_finalise_analogy` turns the record into a verdict — or into `None`.
    """
    sn, scat, sdef = _concept_text(substrate, sc)
    tn, tcat, tdef = _concept_text(substrate, tc)

    if sn == tn:
        return None  # same concept; not an analogy

    # per_order[k] = number of features the pair shares at order k.
    per_order: dict[int, int] = {}
    rationale_parts: list = []

    def _say(k: int, text: str) -> None:
        """Record a rationale fragment AGAINST the order that earned it, so a
        withheld order's justification is withheld with it. The old code
        appended to one flat list, which is why a filtered claim could not have
        been retracted from the rationale even if it had been filtered."""
        rationale_parts.append((k, text))

    if order_n >= 0:
        # n=0: name token overlap
        st = _tokens(sn)
        tt = _tokens(tn)
        overlap = st & tt
        if overlap:
            per_order[0] = len(overlap)
            _say(0, f"shared name tokens: {sorted(overlap)[:3]}")

    if order_n >= 1:
        # n=1: category overlap + definition keyword overlap
        n1 = 0
        if scat and scat == tcat:
            n1 += 1
            _say(1, f"shared category '{scat}'")
        sdt = _tokens(sdef)
        tdt = _tokens(tdef)
        common = sdt & tdt
        if len(common) >= 3:
            n1 += len(common)
            _say(1, f"definition overlap ({len(common)} tokens)")
        if n1:
            per_order[1] = n1

    if order_n >= 2:
        # n=2: shared functional roles
        sroles = _concept_functional_roles(substrate, sc)
        troles = _concept_functional_roles(substrate, tc)
        shared_roles = sroles & troles
        if shared_roles:
            per_order[2] = len(shared_roles)
            _say(2, "shared functional role: %s" % ", ".join(sorted(shared_roles)))

    if order_n >= 3:
        # n=3: shared abstract principles
        sp = _concept_abstract_principles(substrate, sc)
        tp = _concept_abstract_principles(substrate, tc)
        shared_p = sp & tp
        if shared_p:
            per_order[3] = len(shared_p)
            _say(3, "shared abstract principle: %s" % ", ".join(sorted(shared_p)))

    vec_s = vec_t = None
    if order_n >= 4 or any(k >= 2 for k in per_order):
        vec_s = _concept_shape_vector(substrate, sc)
        vec_t = _concept_shape_vector(substrate, tc)

    if order_n >= 4:
        # n=4: shared meta-shapes. The keyword reading (the `has_principle`
        # disjunction) is the BOOTSTRAP; a MetaShape carrying a real
        # anti-unified `signature` — the ones `seeds/meta_shape_growth.json`
        # mints — is additionally read STRUCTURALLY via the held `Covers`.
        # On a stock boot no seeded shape carries one, so this half is dormant
        # by construction and reported as dormant, not as a win.
        sm = _concept_meta_shapes(substrate, sc) | _covered_shapes(substrate, vec_s)
        tm = _concept_meta_shapes(substrate, tc) | _covered_shapes(substrate, vec_t)
        shared_m = sm & tm
        if shared_m:
            per_order[4] = len(shared_m)
            _say(4, "shared meta-shape: %s" % ", ".join(sorted(shared_m)))

    if not per_order:
        return None

    # ---- FAC: the held structural witness over the two concepts' vectors ----
    # Only ever consulted for the abstract orders (2/3/4); orders 0 and 1 do not
    # claim structure and are not asked to prove any.
    witness = {"shared": [], "name_shared": 0, "transform": ()}
    if any(k >= 2 for k in per_order):
        if vec_s is None:
            vec_s = _concept_shape_vector(substrate, sc)
            vec_t = _concept_shape_vector(substrate, tc)
        witness = _pair_witness(substrate, vec_s, vec_t)
        record_pair_correspondence(substrate, sc, tc, witness)
        # DIRECTIONAL_CORRESPONDENCE_RESULTS.md: the SAME witness, plus each
        # side's own richness, additionally recorded as a directional
        # hypothesis candidate -- see the module comment above
        # `_axis_richness` for the full design rationale.
        record_directional_correspondence(substrate, sc, tc, vec_s, vec_t, witness)
    # An order is ALIGNED when the template fixes at least one axis of that
    # order at real, identically-evidenced structure. Reading the axis prefix
    # off a held Term's output is destructuring, not a decision.
    axis_order = {"role": 2, "principle": 3, "shape": 4}
    aligned_orders = {axis_order[p.split(":", 1)[0]]
                      for p, _ in witness["shared"]
                      if p.split(":", 1)[0] in axis_order}

    return {
        "_public": {
            "source_concept": sn,
            "target_concept": tn,
            "source_mt": src_mt_name,
            "target_mt": tgt_mt_name,
            "source_node": sc,
            "target_node": tc,
        },
        "_per_order": per_order,
        "_rationale": rationale_parts,
        "_aligned_orders": aligned_orders,
        "_struct_shared": len(witness["shared"]),
        "_name_shared": witness["name_shared"],
        "_transform": witness["transform"],
    }


def emit_analogy_as_graph(substrate, analogy: dict) -> Any | None:
    """Create an Analogy graph node from a found analogy."""
    try:
        node = substrate.add_node("Analogy", {
            "source_concept": analogy["source_concept"],
            "target_concept": analogy["target_concept"],
            "source_mt": analogy["source_mt"],
            "target_mt": analogy["target_mt"],
            # RELATIVE placement: axis position + within-axis feature count.
            # No absolute exchange-rate score is stored.
            "order_n": int(analogy["order_n"]),
            "feature_count": int(analogy["feature_count"]),
            "features_total": int(analogy["features_total"]),
            # The STRUCTURAL evidence, stored so the assertion below is
            # inspectable in the graph rather than implied by an ordinal.
            "struct_shared": int(analogy.get("struct_shared") or 0),
            "name_shared": int(analogy.get("name_shared") or 0),
            "corroboration": int(analogy.get("corroboration") or 0),
            "rationale": analogy["rationale"],
        })
        # The `implements` edge asserts STRUCTURAL CORRESPONDENCE, so it is now
        # written only when structural correspondence was actually COMPUTED and
        # is positive.
        #
        # It used to be written on `order_n >= 2` with the comment "Lower-n
        # matches are coincidence; n >= 2 indicates genuine structural
        # correspondence" — a hand-set ordinal asserting a structure nothing had
        # computed (`SHAPE_AUDIT.md` §2.4, verbatim). Under the anchored matcher
        # that ordinal was reachable by, among other things, the substring `io`
        # inside the word `operation`.
        if (analogy["order_n"] >= 2
                and (int(analogy.get("struct_shared") or 0) > 0
                     or int(analogy.get("corroboration") or 0) > 0)):
            try:
                substrate.add_edge(analogy["source_node"], "implements",
                                   analogy["target_node"], {})
            except Exception:
                pass
        return node
    except Exception:
        return None


#: Ranking is TIERS, never a weighted sum.
#:   1. `order_n`       — position on the abstraction axis. PRIMARY, unchanged:
#:                        that is the previous rung's registered and gated
#:                        finding (`tests/test_analogical_relative_ranking.py`)
#:                        and this rung does not relitigate it.
#:   2. `corroboration` — how many other pairs realise the same transform. The
#:                        WITHIN-order discriminator, which is exactly where
#:                        MAC/FAC puts structure.
#:   3. `name_shared`   — shared axes evidenced in the concept's own NAME slot,
#:                        not in prose (`META_SHAPE_FIRST_CLASS_RESULTS.md` §2's
#:                        `pred_principles` tier, one grain over).
#:   4. `struct_shared` — total structurally aligned axes.
#:   5/6. the surface counts, unchanged.
RANK_KEY = (lambda a: (-a["order_n"], -a.get("corroboration", 0),
                       -a.get("name_shared", 0), -a.get("struct_shared", 0),
                       -a["feature_count"], -a["features_total"]))


def think_harder(substrate, source_mt_name: str,
                  target_mt_names: list[str], start_n: int = 1,
                  max_n: int = 4, want_at_least: int = 5
                  ) -> dict:
    """The n-abstractable thinking process. Start at order start_n;
    if fewer than want_at_least analogies found, dial up the order +
    try again. Continue until satisfied or max_n reached.

    This implements 'think harder and more abstractly if not happy
    with the answer'.

    Returns {order_used, analogies, satisfied, n_emitted}.
    """
    for n in range(start_n, max_n + 1):
        analogies = find_analogies(
            substrate, source_mt_name, target_mt_names, order_n=n)
        if len(analogies) >= want_at_least:
            # Emit the highest-placed analogies as graph data. Ranking is
            # RELATIVE and TIERED — see RANK_KEY.
            top = sorted(analogies, key=RANK_KEY)
            n_emitted = 0
            seen = set()
            for a in top[:50]:
                key = (a["source_concept"], a["target_concept"])
                if key in seen:
                    continue
                seen.add(key)
                if emit_analogy_as_graph(substrate, a) is not None:
                    n_emitted += 1
            return {
                "order_used": n,
                "analogies": top,
                "satisfied": True,
                "n_found": len(analogies),
                "n_emitted": n_emitted,
                "start_n": start_n,
                "rationale": (
                    f"Found {len(analogies)} analogies at order n={n}; "
                    f"started at n={start_n}. Satisfied."
                ),
            }
    # Reached max_n without enough analogies
    return {
        "order_used": max_n,
        "analogies": find_analogies(
            substrate, source_mt_name, target_mt_names, order_n=max_n),
        "satisfied": False,
        "n_found": 0,
        "n_emitted": 0,
        "start_n": start_n,
        "rationale": (
            f"Reached max_n={max_n} without finding {5} analogies. "
            f"Either domains are genuinely disjoint or matching "
            f"machinery needs richer keyword vocabulary."
        ),
    }


__all__ = [
    "find_analogies", "emit_analogy_as_graph", "think_harder",
    "metashape_realisation_counts", "shape_hits", "RANK_KEY",
]
