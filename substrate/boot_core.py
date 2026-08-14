"""Boot the agent's core cognition from seeds onto a bare Rust substrate.

This is a world-adapter-layer helper, NOT agent logic. It makes no decisions:
it creates a substrate, adds the agent root, and loads the migrated seeds
(decision_core + learning_core + perception_core) through the Rust seed loader.
The agent's reasoning IS the loaded graph data — the construction Rule, the
decision Terms, the causal predicates, the induction pipeline, the perception
recognitions — all parity-verified (see docs/migration_ledger.md). This module
only assembles them; `tick()` / `run_rules()` runs them.

No `CuriousAgent` Python class is involved: the agent is the graph, running in
Rust. That is the whole point of the migration.
"""
from __future__ import annotations

import substrate_rs as srs
from substrate.seed_loader import manifest_for

# The migrated genuine-cognition seeds — the curiosity agent's decision core.
CORE_SEEDS = ("decision_core", "learning_core", "perception_core",
              "epistemics_core", "motor_core", "experimentation_core",
              "goal_construction", "self_monitoring", "memory_core",
              "reflex_core", "theorem_core", "affective_state_core",
              "dual_process_core", "episodic_working_memory_core",
              "adaptive_control_core", "generative_world_model",
              "default_mode_core")


def _add_edge(inner, src, edge_type, tgt):
    """Insert an edge, tolerating both add_edge_unchecked arities."""
    try:
        inner.add_edge_unchecked(src, edge_type, tgt)
    except TypeError:
        inner.add_edge_unchecked(src, edge_type, tgt, {})


def boot_core(seeds=CORE_SEEDS):
    """Create a bare substrate, add the agent root, load the core seeds.

    Returns (substrate, agent_root). The agent root carries the named decision
    Terms (goal_weight_term / action_score_term / quality_term / the causal
    predicates / induction pipeline / perception recognitions) as graph data,
    and the seeded Rules are registered. Mechanical assembly only.
    """
    s = srs.Substrate()
    inner = s._inner
    agent = s.add_node("Agent", {})
    # agent --is_a--> Agent, so Rules matching [agent, is_a, Agent] can fire.
    cls = s.add_node("Agent", {"is_class": True})
    _add_edge(inner, agent, "is_a", cls)
    ordered_manifests = []
    installed = set()
    resolving = set()

    def resolve(seed_id):
        if seed_id in installed:
            return
        if seed_id in resolving:
            raise ValueError(f"cyclic seed dependency involving {seed_id!r}")
        resolving.add(seed_id)
        manifest = manifest_for(seed_id)
        for dependency in manifest.get("depends_on", ()):
            resolve(str(dependency))
        resolving.remove(seed_id)
        installed.add(seed_id)
        ordered_manifests.append(manifest)

    for sid in seeds:
        resolve(sid)
    for manifest in ordered_manifests:
        inner.load_seed_manifest(manifest, agent)
    return s, agent


def register_seed_concepts(agent, seed_id: str) -> list:
    """Register a seed's `concepts` (name + definition Term-JSON) into the
    substrate's concept registry so the Rust `Holds` arm resolves them.

    This is the NATIVE concept-seed loader: the old `arc3_seed`/`astronomy_seed`
    installers grounded a seed's concepts via `CuriousAgent.learn_word`; the
    native equivalent is `WorldAdapter.register_concept` → `inner.define_concept`.
    Mechanical seed loading only — the concept's Term decides; this installs it.
    Atoms are listed before the composites that `Holds`-reference them, though
    resolution is at eval time so order is not load-bearing. Returns the names.
    """
    from substrate.seed_loader import manifest_for
    seed = manifest_for(seed_id)
    names = []
    for c in seed.get("concepts", []):
        agent.register_concept(c["name"], c["definition"])
        names.append(c["name"])
    return names


def installed_seeds(s) -> dict:
    """Map seed-id -> Seed NodeID for every graph-resident Seed node.

    Pure query over the graph (no decisions): the seed system is graph
    modularity, so "which seeds are installed" is read straight off the
    Seed{id,version} nodes that `load_seeds_into` records.
    """
    out = {}
    for n in s.nodes():
        node = s.node(n)
        if node["type"] == "Seed":
            out[node["attrs"]["id"]] = n
    return out


def load_seeds_into(s, agent, seed_ids):
    """Load `seed_ids` (+ their dependency closure) onto an existing substrate
    and record each as a graph-resident Seed{id,version} node with depends_on
    edges — the architecture's "a seed is a graph-resident manifest".

    Mechanical only: the registry walks declared deps (graph data) to a topo
    order, the Rust loader installs each manifest, and this records WHAT was
    loaded. Idempotent — a seed whose Seed node already exists is skipped, so
    re-loading or extending the set never duplicates. Returns {id: NodeID}.

    Wave 3 (deep-reader latency lever) FIX: a seed already installed by
    `substrate.boot_all.load_all_seeds` (a full boot) is recorded under the
    `SeedSummary{seed_id}` provenance convention, NOT as a `Seed{id}` node —
    so this function's Seed-only check re-installed the whole requested
    closure on such an agent. Measured on a full-seed conversation turn:
    `receive_utterance._ensure_intent_seeds` → `load_seeds_into(["intent"])`
    re-installed intent + conversation + psychology + relations on the FIRST
    turn (+16 duplicate rules, including a second copy of
    `rule_mention_resolves_to_concept` — the single most expensive rule in
    the tick profile, so every subsequent rule pass paid it twice). The
    SeedSummary ids are honoured as install evidence for the SKIP check only;
    `present`/depends_on wiring still uses real Seed nodes exclusively (a
    summary-installed dep simply records no depends_on edge — same as any
    other absent dep node, and purely provenance either way). Mechanical
    bookkeeping, no decision.
    """
    from substrate.seeds import REGISTRY  # the live seed registry (graph data)
    import domains.seed_registry  # noqa: F401  -- populates REGISTRY on import
    inner = s._inner
    present = installed_seeds(s)
    summary_installed = set()
    for n in s.nodes():
        node = s.node(n)
        if node["type"] == "SeedSummary":
            sid = node["attrs"].get("seed_id")
            if sid:
                summary_installed.add(sid)
    for seed in REGISTRY.resolve(list(seed_ids)):  # dependency-closure, topo
        if seed.id in present or seed.id in summary_installed:
            continue
        inner.load_seed_manifest(manifest_for(seed.id), agent)
        nid = s.add_node("Seed", {"id": seed.id, "version": seed.version})
        present[seed.id] = nid
        for dep in seed.depends_on:
            if dep in present:
                _add_edge(inner, nid, "depends_on", present[dep])
    return present
