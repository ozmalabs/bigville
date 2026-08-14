"""Apply a captured seed manifest to a live agent.

The capture tool (``tools/capture_seed.py``) walks each Python
``install_X`` and writes its graph delta as JSON under ``seeds/<id>.json``.
This loader is the inverse: given that JSON, it adds the seed's nodes
/ edges / productions to a live agent. Pure mechanical translation —
no decision logic, no agent reasoning. Same shape as a world adapter:
"convert external (JSON) form into substrate mutations."

This Python applier is intended as a stepping stone. The Rust runtime
will have its own loader reading the same JSON format; once that's
wired this module is deletable.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from .graph import NodeID, TypedGraph
from .grammar import NodePattern, Production
from .persistence import decode


def _seed_directory() -> pathlib.Path:
    """Locate manifests both from a source checkout and an installed wheel."""
    configured = pathlib.Path(os.environ["BIGVILLE_SEED_DIR"] \
        ) if "BIGVILLE_SEED_DIR" in os.environ else None
    candidates = [configured] if configured is not None else []
    package_root = pathlib.Path(__file__).resolve().parent.parent
    candidates.extend((package_root / "seeds", package_root / "bigville" / "seeds"))
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    return package_root / "seeds"


SEED_DIR = _seed_directory()

# Declarative encyclopedia prose (if/then/why or head/body) — NOT executable engine rules.
_DECL_KEYS = ("if", "then", "why", "head", "body")


def declarative_principles(rules: list) -> list:
    """Rules written as held knowledge, not tick-time graph rewrites."""
    return [r for r in (rules or [])
            if isinstance(r, dict) and "match" not in r
            and any(k in r for k in _DECL_KEYS)]


def engine_rules_only(manifest: dict) -> dict:
    """Return a shallow copy whose ``rules`` lists only executable engine rules.

    Declarative if/then/head/body principles remain in the source manifest for
    boot_all's encyclopedic materialisation (Mt -has_rule-> Rule). The Rust
    ``load_seed_manifest`` path should always receive this form so it never
    warns on missing ``match`` arrays."""
    if not isinstance(manifest, dict):
        return manifest
    rules = manifest.get("rules") or []
    principles = declarative_principles(rules)
    if not principles:
        return manifest
    m = dict(manifest)
    m["rules"] = [r for r in rules if r not in principles]
    return m


def apply_manifest(agent, manifest: dict) -> dict:
    """Add a seed's nodes + edges + productions to `agent`. Returns
    a summary of what was added.

    Delegates to ``substrate_rs.Substrate.load_seed_manifest`` for the
    graph mutation half — node allocation, cross-ref resolution
    (`{"role": "agent_root"}`, `{"type": "Concept", "name": "X"}`),
    edge insertion, and production registration all happen in Rust.

    The Python side does only two things:
      1. The cross-grammar production mirror — the Rust loader writes
         to the Rust grammar; we also write to the Python checker's
         grammar so the existing Python admissibility path keeps
         working (until the Python checker is retired).
      2. Refresh the agent's name → NodeID caches (`_concept_nodes`
         / `_microtheory_nodes` / `_frame_nodes`) — these caches are
         Python state, not graph state, so the rebuild is an
         adapter-layer concern.
    """
    rust = agent.mind_substrate.graph._inner
    summary = rust.load_seed_manifest(manifest, agent.agent_root)

    # Mirror productions to the Python checker too. The Rust loader
    # has already registered them on the Rust grammar; the Python
    # checker is a separate object whose grammar the chat/intent
    # admissibility paths still consult.
    py_grammar = agent.mind_substrate.checker.grammar
    for p in manifest.get("productions", []):
        prod = Production(
            src=NodePattern(type=p["src"]["type"],
                              var=p["src"].get("var", "src")),
            edge_type=p["edge_type"],
            tgt=NodePattern(type=p["tgt"]["type"],
                              var=p["tgt"].get("var", "tgt")),
            provenance=p.get("provenance", ""),
        )
        try:
            py_grammar.add(prod)
        except Exception:
            pass

    _refresh_agent_indexes(agent)
    return dict(summary)


def _refresh_agent_indexes(agent) -> None:
    """Walk the graph and repopulate the agent's name → NodeID caches
    that the seed installers used to populate as a side effect. The
    graph IS the source of truth; these dicts are read-through
    indexes for code that does ``agent._concept_nodes["statement"]``.

    Idempotent: existing entries are preserved if their NodeID is
    still in the graph; otherwise they get refreshed. Unknown entries
    in the cache are left alone (the caller may have added Python-
    only state)."""
    for n in agent.mind_graph.nodes("Concept"):
        name = n.attrs.get("name")
        if isinstance(name, str) and name:
            agent._concept_nodes.setdefault(name, n.id)
    for n in agent.mind_graph.nodes("Microtheory"):
        name = n.attrs.get("name")
        if isinstance(name, str) and name:
            agent._microtheory_nodes.setdefault(name, n.id)
    for n in agent.mind_graph.nodes("Frame"):
        name = n.attrs.get("name")
        if isinstance(name, str) and name:
            agent._frame_nodes.setdefault(name, n.id)


def _resolve_ref(agent, ref: dict, local_to_global: dict[int, NodeID]) -> NodeID:
    """Resolve one node ref. `local` → mapped seed-internal id.
    `role: agent_root` → the agent's well-known self node. Otherwise
    a {type, <attr>: <value>} cross-ref → find an existing graph
    node matching."""
    if "local" in ref:
        local_id = ref["local"]
        nid = local_to_global.get(local_id)
        if nid is None:
            raise ValueError(
                f"seed_loader: local ref {local_id} unresolved "
                "(out-of-order edge or capture bug)")
        return nid
    if ref.get("role") == "agent_root":
        if agent.agent_root is None:
            raise ValueError("seed_loader: ref is agent_root but "
                              "agent has no agent_root node")
        return agent.agent_root
    if "type" in ref:
        return _find_by_type_and_attr(agent.mind_graph, ref)
    raise ValueError(f"seed_loader: unrecognised node ref {ref!r}")


def _find_by_type_and_attr(graph: TypedGraph, ref: dict) -> NodeID:
    """Walk nodes of the named type, return the first whose extra
    attrs (everything other than `type`) all match. Raises if none."""
    kind = ref["type"]
    expected = {k: v for k, v in ref.items() if k != "type"}
    for n in graph.nodes(kind):
        if all(n.attrs.get(k) == v for k, v in expected.items()):
            return n.id
    raise KeyError(
        f"seed_loader: no {kind!r} node matching {expected!r} — "
        "dep seed not installed?")


def _production_to_dict(p: Production) -> dict:
    """Encode a Production for `Substrate.add_production`. Matches
    the format the Rust pyclass expects."""
    return {
        "src": {"type": p.src.type, "var": p.src.var},
        "edge_type": p.edge_type,
        "tgt": {"type": p.tgt.type, "var": p.tgt.var},
        "provenance": p.provenance,
        "where": None,
        "weight": None,
    }


def _as_text(v) -> str:
    """A list of clauses -> one '; '-joined string (node attrs are scalars)."""
    return "; ".join(str(x) for x in v) if isinstance(v, list) else ("" if v is None else str(v))


def normalize_declarative(manifest: dict) -> dict:
    """Fold a LEGACY declarative manifest into the nodes/edges form the Rust
    `load_seed_manifest` reads.

    The captured (migrated) seeds carry `nodes`/`edges`/`productions`/`rules`
    (each rule with a `match` array). The hand-authored knowledge seeds carry
    `concepts` (which the Rust loader ignores) and `rules` written as `if/then/why`
    PRINCIPLES (which have no `match`, so the loader rejects them). This boundary
    step — the seed_loader's stated job, 'convert external JSON form into substrate
    mutations' — turns each into a graph node so those seeds load through the one
    universal loader:
      • every `concepts` entry -> a `Concept` node (name/definition/category);
      • every `if/then/why` rule -> a `Principle` node (the declarative knowledge,
        held as graph data, not an engine Rule);
      • only genuine `match` rules stay in `rules`.
    Migrated seeds (no `concepts`, no if/then rules) pass through UNCHANGED."""
    if not isinstance(manifest, dict):
        return manifest
    concepts = manifest.get("concepts") or []
    rules = manifest.get("rules") or []
    # A declarative PRINCIPLE is any rule that is NOT a genuine engine `match`
    # rule but carries hand-authored knowledge — written either as `if/then/why`
    # or as `head/body` (premise/consequence). Both fold to a Principle node.
    principles = declarative_principles(rules)
    if not concepts and not principles:
        return manifest                       # already in the loadable form
    m = dict(manifest)
    nodes = list(m.get("nodes") or [])
    used = [n.get("local_id") for n in nodes if isinstance(n.get("local_id"), int)]
    nid = (max(used) + 1) if used else 1
    for c in concepts:
        if not isinstance(c, dict):
            continue
        nodes.append({"local_id": nid, "type": "Concept",
                      "attrs": {k: v for k, v in c.items() if k != "local_id"}})
        nid += 1
    for r in principles:
        attrs = {"name": r.get("name", "")}
        for k in _DECL_KEYS:                   # keep whichever declarative keys it carries
            if k in r:
                attrs[k] = _as_text(r.get(k)) if k != "why" else r.get("why", "")
        nodes.append({"local_id": nid, "type": "Principle", "attrs": attrs})
        nid += 1
    m["nodes"] = nodes
    m["rules"] = [r for r in rules if r not in principles]
    m.pop("concepts", None)
    return m


def load_manifest_file(path: pathlib.Path | str) -> dict:
    """Read a seed JSON manifest from disk (normalised to the loadable form)."""
    return normalize_declarative(json.loads(pathlib.Path(path).read_text()))


def manifest_for(seed_id: str) -> dict:
    """Read the captured manifest for `seed_id` from the default
    seeds/ directory (normalised to the loadable form)."""
    return load_manifest_file(SEED_DIR / f"{seed_id}.json")


__all__ = [
    "apply_manifest",
    "declarative_principles",
    "engine_rules_only",
    "load_manifest_file",
    "manifest_for",
    "normalize_declarative",
    "SEED_DIR",
]
