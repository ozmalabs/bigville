"""Seed registry + loader — the agent's modular boot.

CLAUDE.md, "Seeds are modular with dependencies": the agent's
prior knowledge — every Concept, Production, Rule, Reflex,
Microtheory, Frame it boots with — is shipped as a graph of
named, versioned units called Seeds. An agent declares the seeds
it wants; the loader resolves the dependency closure and installs
them in topological order. A chat agent doesn't carry chess
rules; a chess agent doesn't carry the speech bridge. Same
runtime, different graph-resident knowledge sets.

Current shape vs target shape
-----------------------------
The target end-state is: each seed is a JSON blob (graph_to_dict
format) the Rust runtime loads additively. Today, every domain
ships an imperative `install_X(agent)` Python function that
mutates the graph; converting those to static manifests is a
follow-up. This module is the bridge: a registry that records
each seed's id + version + deps + installer callable, plus a
loader that runs them in dependency order and writes a graph-
resident `Seed` node for each installed seed.

This matches the rule from CLAUDE.md that Python is the world-
adapter layer: the registry decides nothing — it walks the
declared deps mechanically and calls each installer. The
DECISIONS about what's in each seed live in the installers
themselves (and ultimately in the JSON blobs they'll become).

Boot-time persistence
---------------------
Loading a seed writes a `Seed{id, version}` node into the agent's
mind_graph with `depends_on` edges to its dependency Seed nodes
and `installed_at` ticks. A reload sees those nodes and skips
re-installation, so the seed system is idempotent across save /
load cycles and across multiple worlds attaching to the same
agent.

Conflicts
---------
If two seed registrations declare the same id with divergent
versions, registration raises. If a seed's installer fails
partway, the partial state is left in the graph for inspection —
no rollback; the agent's graph is more useful with diagnostic
remnants than with a clean failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .graph import NodeID

# A seed's installer takes the agent and mutates its mind_substrate /
# mind_graph in whatever way the seed's graph data demands. Today
# the installers are the existing domains.install_X functions; in
# the target end-state they'll be `graph_from_dict(seed_json,
# additive=True)` calls reading static manifests.
Installer = Callable[[Any], Any]


# Graph constants for the persistent seed bookkeeping.
_SEED_TYPE = "Seed"
_SEED_DEP_EDGE = "depends_on"


@dataclass(frozen=True)
class Seed:
    """A named, versioned unit of agent prior knowledge.

    `id` is the stable, human-readable handle other seeds and world
    adapters reference. `version` lets a seed evolve without breaking
    seeds that pinned a prior version (today: warning on mismatch;
    target: per-seed namespacing on the productions). `depends_on`
    names other Seeds that must be installed first. `installer` is
    the callable that does the work — for meta-seeds (a seed that's
    only a bundle of other seeds, e.g. `chat`) the installer may be
    None.
    """
    id: str
    version: str = "1.0.0"
    depends_on: tuple[str, ...] = ()
    installer: Installer | None = None
    description: str = ""


class SeedRegistry:
    """Module-level catalogue of available seeds. Populated at import
    time by each domain's seed declaration; consulted by
    :func:`load_seeds` at boot."""

    def __init__(self) -> None:
        self._by_id: dict[str, Seed] = {}

    def register(self, seed: Seed, *, replace: bool = False) -> None:
        """Add a Seed to the registry. Raises ValueError if an
        incompatible version is already registered under the same id."""
        existing = self._by_id.get(seed.id)
        if existing is not None and not replace:
            if existing.version != seed.version:
                raise ValueError(
                    f"seed conflict: {seed.id} is registered as "
                    f"version {existing.version}, but {seed.version} "
                    f"was just declared")
            if existing.installer is not seed.installer:
                raise ValueError(
                    f"seed conflict: {seed.id} already has a "
                    f"different installer registered")
            return  # exact-match re-registration is a no-op
        self._by_id[seed.id] = seed

    def get(self, seed_id: str) -> Seed:
        seed = self._by_id.get(seed_id)
        if seed is None:
            raise KeyError(
                f"unknown seed {seed_id!r}; registered: "
                f"{sorted(self._by_id)}")
        return seed

    def known(self) -> list[str]:
        return sorted(self._by_id)

    def resolve(self, requested: Iterable[str]) -> list[Seed]:
        """Return the dependency closure of `requested` in
        topological order (deps before dependents). Raises on
        cycles or unknown seed ids."""
        order: list[Seed] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def visit(sid: str) -> None:
            if sid in seen:
                return
            if sid in visiting:
                raise ValueError(
                    f"seed dependency cycle through {sid!r}")
            visiting.add(sid)
            seed = self.get(sid)
            for dep in seed.depends_on:
                visit(dep)
            visiting.discard(sid)
            seen.add(sid)
            order.append(seed)

        for sid in requested:
            visit(sid)
        return order


# Module-singleton registry. Each domain calls
# `REGISTRY.register(Seed(...))` at import time.
REGISTRY = SeedRegistry()


def register_seed(seed: Seed) -> None:
    """Convenience for module-level registration."""
    REGISTRY.register(seed)


# ----------------------------------------------------------------------
# Loader
# ----------------------------------------------------------------------


def installed_seeds(agent) -> dict[str, NodeID]:
    """Map of seed id → Seed NodeID for every seed currently installed
    in the agent's mind_graph."""
    out: dict[str, NodeID] = {}
    for n in agent.mind_graph.nodes(_SEED_TYPE):
        sid = n.attrs.get("id")
        if isinstance(sid, str):
            out[sid] = n.id
    return out


def load_seeds(agent, requested: Iterable[str]) -> dict[str, NodeID]:
    """Install the named seeds + their dependency closure on `agent`.

    Idempotent: a seed already installed (a `Seed{id}` node exists)
    is skipped — its installer does not run again. Returns the
    full id → NodeID map for every installed seed (including those
    that were already there).
    """
    plan = REGISTRY.resolve(list(requested))
    _ensure_seed_grammar(agent)
    already = installed_seeds(agent)
    result: dict[str, NodeID] = dict(already)

    for seed in plan:
        if seed.id in already:
            continue  # already installed in a prior boot or attach
        # Run the installer first so the seed's graph data lands
        # before we record the Seed node — that way save/load sees
        # a consistent state even if the installer is interrupted.
        if seed.installer is not None:
            seed.installer(agent)
        seed_node = _record_seed_node(agent, seed, result)
        result[seed.id] = seed_node

    return result


def _ensure_seed_grammar(agent) -> None:
    """Add the Seed → depends_on → Seed production to the Python
    checker's grammar if absent. Idempotent — the grammar's add()
    raises on duplicates; we swallow that. Lets `_record_seed_node`
    write the bookkeeping edges through the checked path."""
    from .grammar import NodePattern, Production
    grammar = agent.mind_substrate.checker.grammar
    try:
        grammar.add(Production(
            src=NodePattern(_SEED_TYPE, "src"),
            edge_type=_SEED_DEP_EDGE,
            tgt=NodePattern(_SEED_TYPE, "tgt"),
            provenance="seeds:depends_on",
        ))
    except Exception:
        pass


def _record_seed_node(agent, seed: Seed,
                        already_installed: dict[str, NodeID]) -> NodeID:
    """Write a graph-resident Seed node for this seed + depends_on
    edges to the Seed nodes of its declared dependencies."""
    sub = agent.mind_substrate
    nid = sub.add_node(_SEED_TYPE, {
        "id": seed.id,
        "version": seed.version,
        "installed_at": int(getattr(agent, "_activity_tick", 0)),
        "description": seed.description,
    })
    for dep_id in seed.depends_on:
        dep_nid = already_installed.get(dep_id)
        if dep_nid is None:
            continue  # should never happen — topo order guarantees it
        sub.add_edge(nid, _SEED_DEP_EDGE, dep_nid)
    return nid


__all__ = [
    "Seed",
    "SeedRegistry",
    "REGISTRY",
    "register_seed",
    "load_seeds",
    "installed_seeds",
]
