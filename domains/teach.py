"""teach — the recurring TEACH -> SAVE-TO-SEED facility.

Teach the jabberwock one thing; it holds it live AND it is persisted to a seed,
so a future boot holds it too. No per-item scripts: every taught fact / lesson /
concept / rule goes through here, instead of someone hand-authoring a seed JSON
each time (as rule_authoring_lessons.json was, by hand).

ARCHITECTURE: the SAVE is mechanical host I/O (write a seed manifest). WHICH
category (which seed) it belongs to is the jabberwock's OWN call — its categories
are its microtheories / meta-shapes (see the self_organisation / self_shape
reflective faculties). This facility takes the category explicitly, or derives it
from the item's own `category` / `domain` / `topic`, or falls back to 'taught'.
A `categorise` hook lets the agent file the item itself.

    from domains.teach import teach
    teach(agent, "TaughtHint",
          {"topic": "rule_fixpoint_idempotence", "question": "...", "answer": "..."},
          category="rule_authoring_lessons")

Re-teaching the same (type, attrs) is a no-op (deduped), so the loop is idempotent.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "seeds"

# ---------------------------------------------------------------------------
# DURABLE SAFETY GUARD — the bench must never mutate the real boot seed files
# (twice-bitten: runs 47/48 clobbered a parallel session's seeds/*.json via
# tests that called teach()-backed helpers without the tmp-redirect fixture).
# When OZMA_SEED_PERSIST_DISABLED is truthy in the environment AND the
# resolved write target is the REAL `SEEDS` dir, skip the file write entirely
# (the in-graph add + category decision are unaffected). An EXPLICIT tmp
# seeds_dir (the test isolation idiom: `teach(..., seeds_dir=tmp_path)`)
# resolves elsewhere and is never blocked — isolation tests still write.
# Default (env unset) is byte-identical to prior behaviour.
# ---------------------------------------------------------------------------
OZMA_SEED_PERSIST_DISABLED_ENV = "OZMA_SEED_PERSIST_DISABLED"


def _persist_blocked(seeds_dir) -> bool:
    """True iff the env guard is armed AND `seeds_dir` resolves to the real
    boot SEEDS dir. Never blocks an explicit non-SEEDS (e.g. tmp_path) dir."""
    if not os.environ.get(OZMA_SEED_PERSIST_DISABLED_ENV):
        return False
    try:
        return Path(seeds_dir).resolve() == SEEDS.resolve()
    except OSError:
        return False


def _slug(s: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(s).strip().lower()).strip("_") or "taught"


# ---------------------------------------------------------------------------
# The meta-shape classifier — GRAPH-NATIVE, and now a THIN SHIM over the SHARED
# `RecogniseShape` Term (runners/dsl/src/shape_decode.rs::recognise_meta_shape).
# The vocabulary (FunctionalRole / Principle{keywords} / MetaShape
# -has_principle-> principle) is graph data (seeds/shape_vocabulary.json). The
# WHOLE SCORING DECISION — iterate MetaShapes, count each shape's has_principle
# neighbours whose `keywords` contains a substring of the item's text, argmax by
# (-score, name) — lives in ONE Rust helper, used by BOTH this faculty AND the
# `TransferDecode` Term (which derives its own goal shape). No duplicated scorer,
# no Python matching loop. Python here is mechanical glue: build the item's text
# (the same join+lower as before, so byte-identity holds) and hand it to the Term.
# ---------------------------------------------------------------------------
def _native(agent):
    """Resolve the native Rust substrate (the thing with _inner.evaluate) from
    whatever the caller passed (WorldAdapter | Substrate | _NativeSubstrate)."""
    s = getattr(agent, "s", agent)            # WorldAdapter.s, else agent itself
    return getattr(s, "_inner", s)            # Substrate._inner, else native already


def categorise_by_shape(agent, type_: str, attrs: dict) -> Optional[str]:
    """The jabberwock files a taught item under one of ITS OWN shapes. Scores the
    item's text against every MetaShape via the SHARED `RecogniseShape` Term (run
    by Rust over the seeded shape vocabulary — the exact recognition path
    `TransferDecode` uses) and returns the meta-shape it most belongs under — or
    None if it matches no shape (then teach() falls back to its domain/topic). This
    is the agent's call, in its own terms: the shape it sees the thing as.

    STRUCTURE, NOT A NAME-BAG (SHAPE_AUDIT.md §2.5, fixed 2026-08-12). This
    used to hand the Term
    `" ".join(str(v) for v in attrs.values() if isinstance(v, str)).lower()` —
    every attribute KEY discarded, every non-string VALUE discarded, the node
    TYPE discarded. It now hands the Term the item's SIGNATURE
    (`domains.meta_shape.item_signature`: the type as an `is_a` relation, every
    attribute as a `[key, value]` relation, sorted by key). `RecogniseShape` is
    input-polymorphic — a collection takes the structural path, where a keyword
    matching a relation PREDICATE outranks any amount of prose evidence, and a
    genuine tie returns None (the honest residual) instead of the shape whose
    name happens to sort first.

    Python here is still mechanical glue: build the signature, hand it to the
    Term. The whole scoring decision remains in ONE Rust helper shared with
    `TransferDecode`."""
    from domains.meta_shape import item_signature
    sig = item_signature(type_, attrs)
    if not sig:
        return None
    native = _native(agent)
    try:
        return native.evaluate(
            {"type": "RecogniseShape", "text": {"type": "Lit", "value": sig}}, {})
    except Exception:
        return None


def _blank_manifest(cat: str, depends_on: Optional[list]) -> dict:
    return {
        "id": cat,
        "version": "1.0.0",
        "depends_on": depends_on or [],
        "description": f"Things the jabberwock was taught, filed under '{cat}'. "
                       "Written by the teach() facility (one node per taught item).",
        "microtheory": {"name": cat, "description": f"taught knowledge: {cat}"},
        "nodes": [],
        "edges": [],
        "productions": [],
    }


def teach(agent, type_: str, attrs: dict, *,
          category: Optional[str] = None,
          categorise: Optional[Callable[[str, dict], str]] = None,
          depends_on: Optional[list] = None,
          seeds_dir: Path = SEEDS) -> dict:
    """Teach one item and persist it to its category's seed.

    agent      — the booted WorldAdapter (its `.s` is the live graph).
    type_      — the node type (TaughtHint / Concept / Rule / ...).
    attrs      — the node's attributes (the taught content).
    category   — the seed to file under; if None, `categorise(type_, attrs)` is
                 used, else the item's own category/domain/topic attr, else 'taught'.
    categorise — optional hook so the AGENT files the item (its own call).

    Returns {node, seed, category, saved, local_id}. `saved=False` => already held.
    """
    attrs = dict(attrs)

    # 1) LIVE — the agent holds it now.
    nid = agent.s.add_node(type_, attrs)

    # 2) CATEGORY — the agent's filing. Order: an explicit category overrides;
    # else a caller-supplied hook; else the jabberwock files it under one of ITS
    # OWN shapes (categorise_by_shape — teaching and self-categorising in one
    # motion); else the item's own domain/topic; else 'taught'.
    # 2a) OBSERVE — mechanical ingest of the item's shape observation so the
    # meta-shape grain's own growth ladder (seeds/meta_shape_growth.json) can
    # decode it, and mint a new MetaShape when a residual RECURS. Before this,
    # a taught item that matched no shape simply fell through to the
    # domain/topic fallback below and the codebook never grew — SHAPE_AUDIT.md
    # finding #1. Inert (a node nobody matches) when the seed is not loaded.
    from domains.meta_shape import observe as _observe_shape
    _observe_shape(agent, type_, attrs)

    cat = category
    if cat is None and categorise is not None:
        cat = categorise(type_, attrs)
    if cat is None:
        cat = categorise_by_shape(agent, type_, attrs)
    if cat is None:
        cat = attrs.get("category") or attrs.get("domain") or attrs.get("topic")
    cat = _slug(cat or "taught")

    # 3) PERSIST — append to the category's seed manifest (create if absent).
    path = Path(seeds_dir) / f"{cat}.json"

    # SAFETY GUARD — see `_persist_blocked` above. The live graph add (step 1)
    # and the category decision (step 2) already happened; only the disk
    # write to the REAL seed dir is skipped.
    if _persist_blocked(seeds_dir):
        return {"node": nid, "seed": str(path), "category": cat,
                "saved": False, "persisted": False}

    if path.exists():
        m = json.loads(path.read_text())
        m.setdefault("nodes", [])
        m.setdefault("edges", [])
        m.setdefault("productions", [])
    else:
        m = _blank_manifest(cat, depends_on)

    # idempotent: the same (type, attrs) already saved -> no-op.
    for n in m["nodes"]:
        if n.get("type") == type_ and n.get("attrs") == attrs:
            return {"node": nid, "seed": str(path), "category": cat,
                    "saved": False, "persisted": True}

    local_id = 1 + max([n.get("local_id", -1) for n in m["nodes"]], default=-1)
    m["nodes"].append({"local_id": local_id, "type": type_, "attrs": attrs})
    from domains.information_commitment import assess
    gate = assess(
        agent,
        commit={
            "name": "teach_to_disk", "expected_goal_work": 2.0,
            "expected_information_gain": 1.0,
            "footprint": {
                "deleted_facts": 0.0, "overwritten_facts": 1.0,
                "recoverability": 0.5, "externality": 0.0,
            },
        },
        wait={"delay_cost": 0.1},
        refine={"refinement_cost": 1.0},
        retain_trace=False,
    )
    if gate["decision"] != "commit" or not gate["authorized"]:
        return {
            "node": nid, "seed": str(path), "category": cat,
            "saved": False, "persisted": False,
            "commit_decision": gate["record"],
        }
    path.write_text(json.dumps(m, indent=1))
    return {"node": nid, "seed": str(path), "category": cat,
            "saved": True, "persisted": True, "local_id": local_id}
