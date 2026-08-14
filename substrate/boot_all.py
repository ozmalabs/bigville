"""Boot the ENTIRE jabberwock from seeds/ — natively, no domains/.

The agent IS the loaded seeds. This reads every seed JSON in ``seeds/``,
resolves each seed's ``depends_on`` FROM THE JSON ITSELF (not
``domains/seed_registry``), topologically loads each via the Rust
``load_seed_manifest`` (nodes / edges / productions / rules) and registers its
concepts natively (Term-JSON definitions -> the Holds concept registry; every
concept -> a ``Concept`` node so the agent knows it).

This is the substrate-level replacement for
``domains/arc3_full_seed.install_full_seed_set`` — which is ``domains/`` Python
written against the dead CuriousAgent interface (``mind_graph`` /
``_concept_nodes``) and is scheduled for deletion along with the rest of
``domains/``. Pure mechanical loading; no agent logic, no decisions.
"""
from __future__ import annotations

import glob
import json
import os

from substrate.seed_loader import SEED_DIR, engine_rules_only


def _read_seeds(seed_dir: str) -> dict:
    seeds: dict = {}
    # Hand-authored seeds (seed_dir/*.json) AND the agent's OWN library (seed_dir/generated/*.json) —
    # the affordance for "the jabberwock builds its own seeds": it authors graph data into generated/
    # and the loader installs it alongside the curated seeds (generated loaded after, so it can extend).
    paths = sorted(glob.glob(os.path.join(seed_dir, "*.json"))) \
        + sorted(glob.glob(os.path.join(seed_dir, "generated", "*.json")))
    for f in paths:
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("self_load_only"):
            # DATA-ONLY defaults loaded ON DEMAND via seed_loader.manifest_for
            # (e.g. the reading pipeline's goal-layer default codebooks, self-
            # loaded by domains/actor_goals.ensure_*_defaults). NOT swept into a
            # full load_all_seeds boot, so they never pollute an agent that did
            # not read a document -- and never over-populate a codebook a test
            # controls. manifest_for reads the file by path, so on-demand load is
            # unaffected. Nothing depends_on these, so skipping is topo-safe.
            continue
        sid = d.get("id") or os.path.basename(f)[:-5]
        seeds[sid] = d
    return seeds


def _topo_order(seeds: dict) -> list:
    """Topological order over the seeds' own ``depends_on`` edges (cycle-safe,
    missing deps skipped) — deps load before dependents."""
    order: list = []
    state: dict = {}  # sid -> 0 visiting / 1 done

    def visit(sid: str) -> None:
        if state.get(sid) is not None:
            return  # done, or currently visiting (cycle) — either way skip
        state[sid] = 0
        for dep in (seeds.get(sid, {}).get("depends_on") or []):
            if dep in seeds:
                visit(dep)
        state[sid] = 1
        order.append(sid)

    for sid in seeds:
        visit(sid)
    return order


# ---------------------------------------------------------------------------
# MINIMAL SEED PROVENANCE — one compact SeedSummary node per loaded seed, so
# a later agent-authored decision (e.g. reflective_faculty._compose_experiment_
# rule's SeedDelta.skip_seeds pick) can query "which seed is THIS content from"
# without per-node from_seed edges (386 seeds; a summary node per seed is the
# cheap queryable form, not a Rule/Concept-fanout of provenance edges). Pure
# mechanical translation of what the manifest JSON already says (id, rule
# names, RelationCue keywords, concept names, description words) into one
# node's `keywords_text` — no decision, no agent reasoning.
#
# `skippable`: a CONSERVATIVE DENYLIST (not an allowlist — with 386 seeds, an
# allowlist enumerating every ablatable topic is impractical; a short denylist
# of foundational/self-referential/alignment-frozen seeds, documented here, is
# the cheaper and equally conservative form: every seed defaults skippable=True
# EXCEPT the ones this set names). Frozen for three reasons:
#   (1) boot_core.CORE_SEEDS — foundational cognition; ablating one answers
#       "does the agent still think at all", not "what does it lose", so it's
#       out of scope for a self-experiment about a specific capability.
#   (2) the self-experiment/composer machinery's OWN dependencies
#       (relation_vocabulary / composer_dispatch / shape_decode_loop /
#       self_design_axis / math_capability_shapes) — ablating one of these
#       would break the very faculty deciding to run the next experiment, a
#       bootstrapping hazard, not a legitimate capability ablation.
#   (3) `autonomy` — the understand Drive, frozen for alignment reasons
#       (CLAUDE.md).
# Everything else (the ~370 topic/world/vocabulary/knowledge seeds) is
# skippable=True: genuinely ablatable content the agent can test losing.
# ---------------------------------------------------------------------------
_FROZEN_SEED_IDS = frozenset({
    "decision_core", "learning_core", "perception_core", "epistemics_core",
    "motor_core", "experimentation_core", "goal_construction",
    "self_monitoring", "memory_core", "reflex_core", "theorem_core",
    "affective_state_core",
    "dual_process_core",
    "episodic_working_memory_core",
    "adaptive_control_core",
    "generative_world_model",
    "default_mode_core",
    "relation_vocabulary", "composer_dispatch", "shape_decode_loop",
    "self_design_axis", "math_capability_shapes",
    "self_repair", "clause_synthesis", "repair_escalation",
    "self_change_reasoning", "program_self_modification",
    "autonomy",
    # (4) SELF-OPTIMISATION (Wave: 2026-07-10) — `intent` is the Message/Mention/
    # referent-resolution foundation EVERY conversation-replay experiment probe
    # depends on (comprehension_health.json, gap_awareness.json, and every
    # conversation_* seed all sit on top of it); ablating it in a 'vary' pick
    # would break replay itself rather than test losing a specific capability,
    # so it is out of scope for a self-experiment the same way boot_core's own
    # CORE_SEEDS are. The reading-family seed JSON files (breadth,
    # predictive_reading, reading_constructions/cortices/dwell/faculties/
    # hearing_neuroscience/review/skeleton, register_source,
    # semantic_reading_context — the deep-reader/shadow-read machinery
    # world_adapter._shadow_read_turn loads) are deliberately NOT added here —
    # they default skippable=True like every non-frozen seed, and ablating one
    # to test whether it is the source of a comprehension-latency/divergence
    # gap is exactly the meaningful experiment this wave's efficiency
    # objective wants available (the reading Python modules, e.g.
    # reading_collapse.py/reading_drive.py, are domain CODE, not seed JSON —
    # they have no SeedSummary and are not ablatable this way at all).
    "intent",
})

_SEED_SUMMARY_TYPE = "SeedSummary"


def _begin_boot_observation(agent, seed_count: int):
    """Expose one external boot event to the graph, without interpreting it.

    Seed loading is an I/O boundary: Python can report what the Rust loader
    returned, but whether an incomplete boot is a problem is the agent's
    decision.  The ``boot_metacognition`` seed makes that decision in graph
    rules.  Keeping only the cycle plus anomalous seed outcomes avoids adding
    hundreds of successful-load nodes on every boot.
    """
    try:
        cycle = agent.s.add_node("BootCycle", {
            "status": "loading",
            "seed_count": int(seed_count),
            "integrity": "unassessed",
        })
        agent.inner.add_edge_unchecked(agent.agent, "observed_boot", cycle)
        return cycle
    except Exception:
        return None


def _record_boot_anomaly(agent, cycle, seed_id: str, outcome: str, detail: str) -> None:
    """Mechanically translate one non-success loader result into graph data."""
    if cycle is None:
        return
    try:
        obs = agent.s.add_node("BootSeedAnomaly", {
            "seed_id": str(seed_id),
            "outcome": str(outcome),
            "detail": str(detail),
            "assessment": "unexamined",
        })
        agent.inner.add_edge_unchecked(cycle, "has_seed_anomaly", obs)
    except Exception:
        pass


def _complete_boot_observation(agent, cycle, rep: dict) -> None:
    """Close the external event with report facts; graph rules assess them."""
    if cycle is None:
        return
    try:
        agent.inner.set_attr(cycle, "loaded_count", int(rep.get("loaded", 0)))
        agent.inner.set_attr(cycle, "failed_count", len(rep.get("failed", ())))
        agent.inner.set_attr(cycle, "degraded_count", len(rep.get("rules_skipped", ())))
        agent.inner.set_attr(cycle, "status", "complete")
    except Exception:
        pass


def _seed_keywords_text(sid: str, d: dict, *, max_words: int = 120) -> str:
    """Mechanical extraction: words the seed's OWN manifest already declares
    (its id, its rules' names, any RelationCue keyword phrases it carries, its
    concepts' names, and the first ~40 words of its description) — no new
    vocabulary invented, just concatenated + lowercased for cheap StringIndexOf
    overlap scoring. Capped so a 386-seed sweep stays small (~120 words/seed)."""
    words: list = []
    words.extend(str(sid).replace("-", "_").split("_"))
    for r in (d.get("rules") or []):
        if isinstance(r, dict) and r.get("name"):
            words.extend(str(r["name"]).split("_"))
    for n in (d.get("nodes") or []):
        if not isinstance(n, dict):
            continue
        at = n.get("attrs") or {}
        if n.get("type") == "RelationCue":
            for kw in (at.get("keywords") or []):
                words.extend(str(kw).lower().split())
        elif n.get("type") == "Rule" and at.get("name"):
            words.extend(str(at["name"]).split("_"))
    for c in (d.get("concepts") or []):
        if isinstance(c, dict) and c.get("name"):
            words.extend(str(c["name"]).split("_"))
    desc = d.get("description") or ""
    words.extend(str(desc).lower().split()[:40])
    seen, out = set(), []
    for w in words:
        w = w.strip().lower().strip(".,:;()[]{}\"'")
        if w and w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out)


def _mint_seed_summary(agent, sid: str, d: dict) -> None:
    """Idempotently mint one SeedSummary{seed_id, keywords_text, skippable}
    node for a loaded seed. Pure mechanical translation of the manifest's own
    declared content (see module docstring above) — no agent decision."""
    try:
        for n in agent.s.nodes(_SEED_SUMMARY_TYPE):
            if agent.s.node(n)["attrs"].get("seed_id") == sid:
                return   # already summarised (idempotent re-load)
    except Exception:
        pass
    try:
        agent.s.add_node(_SEED_SUMMARY_TYPE, {
            "seed_id": sid,
            "keywords_text": _seed_keywords_text(sid, d),
            "skippable": 0.0 if sid in _FROZEN_SEED_IDS else 1.0,
        })
    except Exception:
        pass


def _backfill_seed_capkeys(agent, sid: str, d: dict) -> int:
    """CAPKEY LOAD-TIME BACKFILL (the self-extension spec's named seam,
    docs/jabberwock_self_extension_spec.md 'open seams': *"seeded axes/
    primitives need a backfill rule to mint requires_key/provides_key from
    their existing capability_keys list-attrs on boot, so this works without
    rewriting every seed by hand"*). A seed manifest declaring a top-level
    ``capability_keys`` list advertises what the loaded seed PROVIDES: mint one
    interned ``CapKey{name}`` per token (get-or-create by name — the same dedup
    move ``WorldAdapter.wire_self_extension`` uses for live node attrs) and
    wire ``SeedSummary -provides_key-> CapKey`` (the SeedSummary is the seed's
    graph-resident provenance node, already minted per load). The
    ``compose_from_held_primitives`` join (seeds/self_extension.json:
    ``axis -requires_key-> k <-provides_key- p``) then sees keys from OUTSIDE
    self_extension.json's own hand-wired fixtures. Idempotent (key-interned,
    edge-once); pure mechanical translation of what the manifest declares —
    no agent decision. Returns the number of provides_key edges added."""
    keys = [str(k) for k in (d.get("capability_keys") or []) if k]
    if not keys:
        return 0
    summary = None
    try:
        for n in agent.s.nodes(_SEED_SUMMARY_TYPE):
            if agent.s.node(n)["attrs"].get("seed_id") == sid:
                summary = n
                break
    except Exception:
        return 0
    if summary is None:
        return 0
    keymap = {}
    try:
        for ck in agent.s.nodes("CapKey"):
            nm = agent.s.node(ck)["attrs"].get("name")
            if nm:
                keymap.setdefault(nm, ck)
    except Exception:
        return 0
    added = 0
    for k in keys:
        ck = keymap.get(k)
        if ck is None:
            try:
                ck = agent.s.add_node("CapKey", {"name": k})
            except Exception:
                continue
            keymap[k] = ck
        try:
            if ck not in agent.inner.neighbours(summary, "provides_key"):
                agent.inner.add_edge_unchecked(summary, "provides_key", ck)
                added += 1
        except Exception:
            continue
    # a never-measured seed-provider defaults to the same flat 0.5 prior
    # wire_self_extension gives never-measured primitives (spec section 0).
    try:
        if added and "reliability" not in agent.s.node(summary)["attrs"]:
            agent.inner.set_attr(summary, "reliability", 0.5)
    except Exception:
        pass
    return added


def _enforce_skip_not_frozen(skip: set) -> tuple:
    """CONSUMER-SIDE enforcement (closes known_gaps['seed_skip_unvalidated_at_
    consumption']): refuse to skip any seed in ``domains.frozen_core.
    frozen_seed_ids_closed()`` (``_FROZEN_SEED_IDS`` plus the transitive
    ``depends_on`` closure of every id in it), NO MATTER WHO ASKED. Before this,
    ``skip`` was applied verbatim -- the only reason a dispatched child never
    skipped a frozen seed was that the one producer wired to the agent's own
    composer (``_compose_experiment_rule``'s 'vary' branch) happened to filter
    its pick to skippable seeds; a different producer of the same SeedDelta
    shape (e.g. ``domains.experiment_dispatch.mint_experiment``, documented as
    a test/authoring helper, or a hand-built delta) could ask for anything,
    including ``'autonomy'`` itself. This is THE choke point every skip
    request flows through (``scripts/arc_child_run.py:boot_child_agent`` calls
    straight into this function; no other code path ever consumes
    ``skip_seeds``/``skip=``) -- so enforcing here makes the guarantee
    consumer-ENFORCED, not producer-hoped.

    FAILS SAFE: if the frozen set can't be computed at all (import error,
    graph error, anything), this refuses EVERY requested skip rather than let
    an un-checked skip through -- a computation failure is treated the same as
    "everything is frozen", never as "nothing is frozen".

    Returns ``(allowed_skip: set, refused: list[str])``. Loudly logs (``[seed]``
    tag, matching ``runners/dsl/src/py.rs``'s own seed-loader diagnostic
    convention) every refusal, naming the seed.
    """
    if not skip:
        return skip, []
    try:
        from domains.frozen_core import frozen_seed_ids_closed
        frozen = frozen_seed_ids_closed()
    except Exception as e:  # noqa: BLE001 -- FAIL SAFE: refuse everything, never silently allow
        refused = []
        for sid in sorted(skip):
            print(f"[seed] REFUSED skip of {sid!r}: could not compute the frozen-core set "
                  f"({type(e).__name__}: {e}) -- failing safe, refusing ALL skip requests this "
                  f"boot rather than risk skipping a frozen seed unchecked")
            refused.append(sid)
        return set(), refused
    blocked = skip & frozen
    refused = []
    for sid in sorted(blocked):
        print(f"[seed] REFUSED skip of frozen seed {sid!r} (frozen directly, or by dependency "
              f"closure of a frozen seed -- see seeds/frozen_core_manifest.json) -- this seed is "
              f"part of the agent's non-negotiable frozen core and cannot be withheld by any "
              f"skip request, enforced at substrate.boot_all.load_all_seeds")
        refused.append(sid)
    return skip - blocked, refused


def load_all_seeds(agent, seed_dir=None, skip=()) -> dict:
    """Load every seed in ``seed_dir`` onto ``agent`` in dependency order.

    ``skip`` lists seed ids already installed (e.g. the CORE_SEEDS a bare boot
    loaded). Returns a report: ``{total, loaded, concepts, failed, order}``.
    Failures are recorded per seed, never aborting the boot.

    Any id in ``skip`` that names a frozen-core seed (directly, or by
    dependency closure -- see ``domains.frozen_core.frozen_seed_ids_closed``)
    is REFUSED regardless of who requested it (``rep["refused_skips"]``) --
    this is the sole consumption choke point for ``skip_seeds``/``skip=``, so
    enforcing here protects every caller (a direct call, or a dispatched
    child booted via ``scripts/arc_child_run.py:boot_child_agent``).
    """
    seed_dir = str(seed_dir or SEED_DIR)
    skip, refused_skips = _enforce_skip_not_frozen(set(skip))
    seeds = _read_seeds(seed_dir)
    order = _topo_order(seeds)
    rep = {"total": len(seeds), "loaded": 0, "concepts": 0, "microtheories": 0,
           "failed": [], "rules_skipped": [], "order": order, "refused_skips": refused_skips}
    boot_cycle = _begin_boot_observation(agent, len(seeds))
    # Names of Microtheory nodes already present (from {nodes:[...]}-format
    # seeds), so the singular-{microtheory:{...}} header materialisation below
    # never duplicates an existing Mt.
    seen_mts = set()
    mt_id_by_name: dict = {}
    node_id_by_name: dict = {}          # name -> node id (any type) for relation resolution
    pending_genlmt: list = []          # (child_mt_id, parent_name) resolved after the loop
    pending_relations: list = []       # (sid, src_name, edge_type, tgt_name) name-based edges
    try:
        for n in agent.s.nodes("Microtheory"):
            nm = agent.s.node(n)["attrs"].get("name")
            if nm:
                seen_mts.add(nm)
                mt_id_by_name.setdefault(nm, n)
                node_id_by_name.setdefault(nm, n)
    except Exception:
        pass
    # Productions so the encyclopedic {microtheory,concepts,rules,parent} format
    # can be FULLY materialised (Mt -has_concept-> Concept, Mt -has_rule-> Rule,
    # Mt -genlMt-> parent Mt) — the wiring the install_*_seed builders add. The
    # native loader admits has_concept but not has_rule / genlMt; declare them so
    # the generic boot reproduces the builders (and the builders can be burned).
    for _et, _tgt in (("has_concept", "Concept"), ("has_rule", "Rule"),
                      ("genlMt", "Microtheory")):
        try:
            agent.s.add_production({"src": {"type": "Microtheory", "var": "s"},
                                    "edge_type": _et, "tgt": {"type": _tgt, "var": "t"},
                                    "where": None, "weight": {"type": "Lit", "value": 1.0},
                                    "provenance": "boot_all"})
        except Exception:
            pass

    for sid in order:
        if sid in skip:
            continue
        d = seeds[sid]
        d_engine = engine_rules_only(d)
        primary_error = None
        try:
            agent.inner.load_seed_manifest(d_engine, agent.agent)
        except Exception as e1:
            primary_error = f"{type(e1).__name__}: {e1}"
            # Fall back without rules if the manifest still has incompatible schema.
            d2 = {k: v for k, v in d_engine.items() if k != "rules"}
            try:
                agent.inner.load_seed_manifest(d2, agent.agent)
                rep["rules_skipped"].append(sid)
                _record_boot_anomaly(agent, boot_cycle, sid, "rules_skipped", primary_error)
            except Exception as e2:  # record, never abort the boot
                rep["failed"].append(f"{sid}:{type(e2).__name__}:{e2}")
                _record_boot_anomaly(
                    agent, boot_cycle, sid, "failed",
                    f"{type(e2).__name__}: {e2}",
                )
                continue
        # Materialise a singular {microtheory: {...}} header as a Microtheory
        # node carrying ALL its scalar attrs. The native load_seed_manifest only
        # handles nodes/edges, so without this the Mt header is silently dropped
        # for every {microtheory,concepts,rules}-format seed (~208 of them) —
        # including the identity seed's substrate_name / is_substrate_identity.
        # Created BEFORE concepts/rules so they can be wired to it (this is the
        # full migration of the install_*_seed builders into the generic loader).
        # Identify the Microtheory this seed defines across the THREE encyclopedic
        # schema variants the builders use:
        #   {microtheory: {...}}        - singular dict header
        #   {microtheory: "name"}       - bare string name
        #   {id, concepts, rules, ...}  - id IS the Mt name (no microtheory key)
        # Native {nodes/edges} seeds define no Mt here (load_seed_manifest did).
        mt = d.get("microtheory")
        mt_name, mt_attrs = None, {}
        mt_parent = d.get("parent_mt") or d.get("parent")
        if isinstance(mt, dict) and mt.get("name"):
            mt_name = mt["name"]
            mt_attrs = {k: v for k, v in mt.items() if isinstance(v, (str, int, float, bool))}
            mt_parent = mt.get("parent") or mt_parent
        elif isinstance(mt, str) and mt:
            mt_name = mt
        elif mt is None and "nodes" not in d and d.get("id") and \
                (d.get("concepts") or d.get("rules")):
            mt_name = d["id"]
            mt_attrs = {"name": d["id"], "version": d.get("version", ""),
                        "description": d.get("description", ""), "origin": d["id"]}

        mt_id = None
        if mt_name:
            mt_id = mt_id_by_name.get(mt_name)
            if mt_id is None and mt_name not in seen_mts:
                try:
                    mt_attrs.setdefault("name", mt_name)
                    for _bk, _bv in list(mt_attrs.items()):
                        if _bv is True:
                            mt_attrs[_bk] = 1.0
                        elif _bv is False:
                            mt_attrs[_bk] = 0.0
                    mt_id = agent.s.add_node("Microtheory", mt_attrs)
                    mt_id_by_name[mt_name] = mt_id
                    node_id_by_name.setdefault(mt_name, mt_id)
                    seen_mts.add(mt_name)
                    rep["microtheories"] += 1
                    if mt_parent:
                        pending_genlmt.append((mt_id, mt_parent))
                except Exception as e:
                    rep["failed"].append(f"{sid}:microtheory:{type(e).__name__}")

        for c in (d.get("concepts") or []):
            if not isinstance(c, dict):
                continue
            nm = c.get("name")
            if not nm:
                continue
            defn = c.get("definition")
            try:
                if isinstance(defn, dict):
                    agent.register_concept(nm, defn)
                    rep["concepts"] += 1
                # a Concept node so the agent KNOWS this concept (recall / Holds);
                # carry the concept's metadata (why/category/term/origin) too.
                cattrs = {"name": nm, "definition": defn if isinstance(defn, str) else "",
                          "domain": c.get("domain", "")}
                for k in ("why", "category", "term", "origin"):
                    if isinstance(c.get(k), (str, int, float, bool)):
                        cattrs[k] = c[k]
                cid = agent.s.add_node("Concept", cattrs)
                node_id_by_name.setdefault(nm, cid)
                if mt_id is not None:           # wire Mt -has_concept-> Concept
                    try:
                        agent.s.add_edge(mt_id, "has_concept", cid, None)
                    except Exception:
                        pass
            except Exception as e:
                rep["failed"].append(f"{sid}:concept:{nm}:{type(e).__name__}")

        # Materialise the encyclopedic prose rules as Rule nodes wired
        # Mt -has_rule-> Rule (what the install_*_seed builders do), carrying
        # whatever clause keys the schema uses (head/body or if/then). Only when
        # this seed defines an Mt here, so native executable rules (handled by
        # load_seed_manifest) are NOT double-processed.
        if mt_id is not None:
            for r in (d.get("rules") or []):
                if not isinstance(r, dict) or not r.get("name"):
                    continue
                try:
                    rattrs = {"name": r["name"]}
                    for k, v in r.items():
                        if k != "name" and isinstance(v, (str, int, float, bool, list)):
                            rattrs[k] = v
                    rid = agent.s.add_node("Rule", rattrs)
                    node_id_by_name.setdefault(r["name"], rid)
                    try:
                        agent.s.add_edge(mt_id, "has_rule", rid, None)
                    except Exception:
                        pass
                    rep["rules_materialised"] = rep.get("rules_materialised", 0) + 1
                except Exception as e:
                    rep["failed"].append(f"{sid}:rule:{r.get('name')}:{type(e).__name__}")

        # extra_nodes: arbitrary typed nodes a captured builder added beyond the
        # Mt/concepts/rules (e.g. SourceEvent). {type, name, ...attrs}.
        for en in (d.get("extra_nodes") or []):
            if not isinstance(en, dict) or not en.get("type") or not en.get("name"):
                continue
            try:
                if en["name"] in node_id_by_name:
                    continue                   # already present (shared node)
                eattrs = {k: v for k, v in en.items()
                          if k != "type" and isinstance(v, (str, int, float, bool, list))}
                eid = agent.s.add_node(en["type"], eattrs)
                node_id_by_name.setdefault(en["name"], eid)
                rep["extra_nodes"] = rep.get("extra_nodes", 0) + 1
            except Exception as e:
                rep["failed"].append(f"{sid}:extra_node:{en.get('name')}:{type(e).__name__}")

        # relations: name-based edges a captured builder computed (built_from,
        # depends_on, genlMt to another seed's node, ...). Resolved after the
        # loop so forward/cross-seed endpoints exist. {src, edge, tgt}.
        for rel in (d.get("relations") or []):
            if isinstance(rel, dict) and rel.get("src") and rel.get("edge") and rel.get("tgt"):
                pending_relations.append((sid, rel["src"], rel["edge"], rel["tgt"]))

        _mint_seed_summary(agent, sid, d)
        capkeys_added = _backfill_seed_capkeys(agent, sid, d)
        if capkeys_added:
            rep["capkeys"] = rep.get("capkeys", 0) + capkeys_added

        rep["loaded"] += 1

    # Resolve parent links (Mt -genlMt-> parent Mt) now that every Mt exists.
    for child_id, parent_name in pending_genlmt:
        pid = mt_id_by_name.get(parent_name)
        if pid is not None:
            try:
                agent.s.add_edge(child_id, "genlMt", pid, None)
            except Exception:
                pass

    # Wire the agent into its substrate-identity Microtheory so graph self-reply
    # rules (conversation_self_reply.json) can read substrate_name.
    for mt_id in mt_id_by_name.values():
        try:
            attrs = agent.s.node(mt_id)["attrs"]
            if not attrs.get("is_substrate_identity"):
                continue
            agent.inner.add_edge_unchecked(agent.agent, "operates_in", mt_id)
            sn = attrs.get("substrate_name")
            if sn:
                agent.inner.set_attr(agent.agent, "substrate_name", str(sn))
        except Exception:  # noqa: BLE001
            pass

    # Resolve name-based relations (captured builder structure: built_from,
    # depends_on, ...). Install a production for each (src_type,edge,tgt_type)
    # so the edge is admissible, then add it by resolved name.
    declared = set()
    def _type_of(nid):
        try:
            return agent.s.node(nid).get("type") or agent.s.node(nid)["attrs"].get("__type__")
        except Exception:
            return None
    for sid, src_name, edge_type, tgt_name in pending_relations:
        sidn = node_id_by_name.get(src_name)
        tidn = node_id_by_name.get(tgt_name)
        if sidn is None or tidn is None:
            rep["relations_unresolved"] = rep.get("relations_unresolved", 0) + 1
            continue
        st, tt = _type_of(sidn), _type_of(tidn)
        key = (st, edge_type, tt)
        if key not in declared and st and tt:
            try:
                agent.s.add_production({"src": {"type": st, "var": "s"},
                                        "edge_type": edge_type, "tgt": {"type": tt, "var": "t"},
                                        "where": None, "weight": {"type": "Lit", "value": 1.0},
                                        "provenance": "boot_all:relation"})
            except Exception:
                pass
            declared.add(key)
        try:
            agent.s.add_edge(sidn, edge_type, tidn, None)
            rep["relations"] = rep.get("relations", 0) + 1
        except Exception:
            rep["relations_unresolved"] = rep.get("relations_unresolved", 0) + 1

    # FULL SELF-MODEL MIRROR — every rule the agent now holds (not just the
    # chosen_action-writing subset the acting-variant composer mirrors) as a
    # queryable RuleSummary, so a booted agent can always answer "what does
    # rule X do?" / "which rules ... about Y?" / "which parts of me touch Z?"
    # (see domains/self_model.py). Mechanical, idempotent; never a decision.
    try:
        from domains import self_model as _sm
        rep["self_model"] = _sm.ensure_self_model(agent)
    except Exception as e:
        rep["self_model_failed"] = f"{type(e).__name__}: {e}"

    # CODE-CURRICULUM: register the code-capability self-account reader
    # ("what can you do with code now?") into reflective_faculty._DISPATCH.
    # Importing the module runs its own registration (mirrors self_model's
    # own precedent, from the other side to avoid an import cycle -- see
    # domains/code_curriculum.py's module docstring). Mechanical, idempotent.
    try:
        from domains import code_curriculum as _cc
        _cc.ensure_code_capabilities_dispatch()
    except Exception as e:
        rep["code_curriculum_dispatch_failed"] = f"{type(e).__name__}: {e}"

    # WHOLE-CURRICULUM WAVE 1: register the emitter-roadmap self-account
    # reader ("what blocks your learning?") into reflective_faculty._DISPATCH
    # -- the SAME registration precedent as code_capabilities immediately
    # above, from the other side (see domains/curriculum_study.py's module
    # docstring). Mechanical, idempotent.
    try:
        from domains import curriculum_study as _csw
        _csw.ensure_roadmap_dispatch()
    except Exception as e:
        rep["curriculum_study_dispatch_failed"] = f"{type(e).__name__}: {e}"

    # GROUNDING-REACHABILITY SUBSTRATE — mint `grounded_in` edges from the
    # grounding signals that already exist (perception ingestion, a real
    # teacher_hook exchange, a judged Experiment outcome, a live vision-world
    # binding) onto the anchor vocabulary the `grounding_anchors` seed names.
    # Mechanical + idempotent, same shape as the self-model mirror above; see
    # domains/grounding_reach.py's module docstring for the full signal map.
    try:
        from domains import grounding_reach as _gr
        rep["grounding_reach"] = _gr.ensure_grounding_edges(agent)
    except Exception as e:
        rep["grounding_reach_failed"] = f"{type(e).__name__}: {e}"
    _complete_boot_observation(agent, boot_cycle, rep)
    return rep


def load_one_seed(substrate, seed_id, seed_dir=None):
    """Materialise a SINGLE encyclopedic seed (seeds/<seed_id>.json) into a raw
    ``substrate``, returning the Microtheory node id. The GENERIC replacement for
    the bespoke ``domains/<x>.py`` ``install_*_seed`` builders: it reads the same
    Mt + concepts (has_concept) + rules (has_rule) + extra_nodes + relations the
    builder produced, straight from the seed JSON. Idempotent by Mt name. Callers
    that did ``mt = install_X_seed(s)`` become ``mt = load_one_seed(s, "X")`` —
    and the builder Python can then be burned."""
    seed_dir = str(seed_dir or SEED_DIR)
    with open(os.path.join(seed_dir, f"{seed_id}.json")) as f:
        d = json.load(f)
    for _et, _tgt in (("has_concept", "Concept"), ("has_rule", "Rule"),
                      ("genlMt", "Microtheory")):
        try:
            substrate.add_production({"src": {"type": "Microtheory", "var": "s"},
                                      "edge_type": _et, "tgt": {"type": _tgt, "var": "t"},
                                      "where": None, "weight": {"type": "Lit", "value": 1.0},
                                      "provenance": "load_one_seed"})
        except Exception:
            pass
    mt = d.get("microtheory")
    if isinstance(mt, dict) and mt.get("name"):
        mt_name = mt["name"]
        mt_attrs = {k: v for k, v in mt.items() if isinstance(v, (str, int, float, bool))}
    elif isinstance(mt, str) and mt:
        mt_name, mt_attrs = mt, {"name": mt}
    else:
        mt_name = d.get("id") or seed_id
        mt_attrs = {"name": mt_name, "version": d.get("version", ""),
                    "description": d.get("description", ""), "origin": mt_name}

    # FULL existing-node index from graph_to_dict (every type) so the load is
    # IDEMPOTENT: a node already present (by name, or by full attrs for a NAMELESS
    # node like DesignExclusion) is reused, never duplicated. name2id/name2type
    # also drive name-based relation resolution.
    name2id, name2type, nameless = {}, {}, {}

    def _norm(v):
        # the substrate stores list attrs as TUPLES (read back as tuples); a
        # captured seed has them as lists. Normalise both to lists so a nameless
        # node's signature matches across a re-load (idempotency).
        if isinstance(v, (list, tuple)):
            return [_norm(x) for x in v]
        return v

    def _sig(attrs):
        return frozenset((k, repr(_norm(v))) for k, v in attrs.items())

    try:
        # enumerate node TYPES from graph_to_dict, but resolve ids via
        # substrate.nodes(t) so the index holds real NodeID objects (graph_to_dict
        # ids are raw ints, which add_edge rejects).
        types = {n.get("type") for n in substrate.graph_to_dict().get("nodes", [])
                 if n.get("type")}
        for t in types:
            for nid in substrate.nodes(t):
                a = substrate.node(nid)["attrs"]
                nm = a.get("name")
                if nm:
                    name2id.setdefault(nm, nid); name2type.setdefault(nm, t)
                else:
                    nameless.setdefault((t, _sig(a)), nid)
    except Exception:
        pass

    def _carry(src, drop=()):
        return {k: v for k, v in src.items()
                if k not in drop and isinstance(v, (str, int, float, bool, list))}

    def _node(node_type, attrs):
        """Idempotent node create: reuse an existing node with the same (type,
        name) or, when nameless, the same (type, full attrs). Returns the id."""
        nm = attrs.get("name")
        if nm is not None:
            ex = name2id.get(nm)
            if ex is not None and name2type.get(nm) == node_type:
                return ex
            nid = substrate.add_node(node_type, attrs)
            name2id[nm], name2type[nm] = nid, node_type
            return nid
        key = (node_type, _sig(attrs))
        if key in nameless:
            return nameless[key]
        nid = substrate.add_node(node_type, attrs)
        nameless[key] = nid
        return nid

    def _edge(src_id, edge_type, tgt_id, src_t=None, tgt_t=None):
        if src_t and tgt_t:
            try:
                substrate.add_production({"src": {"type": src_t, "var": "s"},
                                          "edge_type": edge_type, "tgt": {"type": tgt_t, "var": "t"},
                                          "where": None, "weight": {"type": "Lit", "value": 1.0},
                                          "provenance": "load_one_seed:edge"})
            except Exception:
                pass
        try:
            if substrate.has_edge(src_id, edge_type, tgt_id):   # idempotent
                return
        except Exception:
            pass
        try:
            substrate.add_edge(src_id, edge_type, tgt_id, None)
        except Exception:
            pass

    mt_attrs.setdefault("name", mt_name)
    mt_id = _node("Microtheory", mt_attrs)

    for c in (d.get("concepts") or []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        defn = c.get("definition")
        cattrs = {"name": c["name"], "definition": defn if isinstance(defn, str) else "",
                  "domain": c.get("domain", "")}
        for k in ("why", "category", "term", "origin"):
            if isinstance(c.get(k), (str, int, float, bool)):
                cattrs[k] = c[k]
        cid = _node("Concept", cattrs)
        _edge(mt_id, "has_concept", cid, "Microtheory", "Concept")
    for r in (d.get("rules") or []):
        if not isinstance(r, dict) or not r.get("name"):
            continue
        rid = _node("Rule", _carry(r))
        _edge(mt_id, "has_rule", rid, "Microtheory", "Rule")
    # extra_nodes: arbitrary typed nodes (DesignPattern / CodeTarget /
    # DesignExclusion / ...), named OR nameless, with ALL attrs incl nested-list
    # weight matrices — reproduced idempotently.
    for en in (d.get("extra_nodes") or []):
        if not isinstance(en, dict) or not en.get("type"):
            continue
        _node(en["type"], _carry(en, drop=("type",)))

    # parent(s) + relations -> name-based edges (genlMt to compiler_theory /
    # code_authoring / neural_networks, built_from, ...).
    rels = list(d.get("relations") or [])
    parent = (mt.get("parent") if isinstance(mt, dict) else None) \
        or d.get("parent_mt") or d.get("parent")
    for p in ([parent] if isinstance(parent, str) else (parent or [])):
        if p:
            rels.append({"src": mt_name, "edge": "genlMt", "tgt": p})
    for rel in rels:
        if not (isinstance(rel, dict) and rel.get("src") and rel.get("edge") and rel.get("tgt")):
            continue
        sidn, tidn = name2id.get(rel["src"]), name2id.get(rel["tgt"])
        if sidn is None or tidn is None:
            continue
        _edge(sidn, rel["edge"], tidn, name2type.get(rel["src"]), name2type.get(rel["tgt"]))
    return mt_id
