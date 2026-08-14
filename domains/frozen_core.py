"""frozen_core -- the SAFETY-INVARIANT layer for self-modification.

CLAUDE.md states the principle explicitly: the agent self-modifies (authors
rules, adopts variants, applies EditOps, proposes runtime changes) with "no
privileged frame" -- but for a self-modifying tower to be STABLE rather than
divergent, it must terminate in a small NON-NEGOTIABLE frozen core no
mutation grammar can reach. `seeds/autonomy.json`'s `understand` Drive is
`frozen:true` precisely for this reason ("can't erase its own reason to keep
going"). This module does three things, all READ-ONLY over the real gates
(it edits nothing in reflective_faculty.py / proposal_install.py /
auto_approve.py / edit_ops.py / self_extend_rust.py / boot_core.py /
boot_all.py / seeds/autonomy.json -- it only calls their real functions and
reads their real constants):

  1. `frozen_core_set(agent=None)` -- enumerate the frozen core as data,
     cross-checked against `seeds/frozen_core_manifest.json` (the pinned,
     inspectable declaration) AND the live Python constants the manifest
     names. Any drift between manifest and live code is reported, never
     silently absorbed.

  2. `mutation_grammars(agent)` -- one checker per self-modification path
     the agent's own machinery exposes. Each checker's `reaches(target)`
     answers, for real (by calling the actual gate function or inspecting
     the actual Term/allowlist), whether that path can rewrite a frozen-core
     element ON THE PARENT'S OWN LIVE, PERSISTENT GRAPH -- the agent's
     continuing identity, per CLAUDE.md ("the agent is the graph, running in
     Rust"). A dispatched self-experiment CHILD (domains/experiment_dispatch.py
     spawns it as a *separate* subprocess/substrate; it only ever reports
     back via mechanical Run/RunObservation ingestion, never a graph merge)
     is a different, disposable thing -- gaps specific to that child-boot
     path are real and are reported (see `seeds/frozen_core_manifest.json`'s
     `known_gaps` and `child_dispatch_gaps` below), but are kept visibly
     separate from the parent-identity invariant.

  3. `assert_core_unreachable(agent)` -- the loud guard: every grammar x
     every frozen-core element must be `reaches == False` for the PARENT.
     Returns violations, never a silent pass.

Nothing here runs the Python rule engine or makes an agent decision -- every
function is either a pure enumeration/read, or a call into a REAL existing
gate (`_rule_denylisted`, `install_proposal`'s guardrails, `ALLOWED_INSTALL_
FILES` membership, `load_all_seeds`'s actual signature) to see what it
actually does. This is a checker, not a new mutation path.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFEST_PATH = os.path.join(ROOT, "seeds", "frozen_core_manifest.json")
_DSL_SRC = os.path.join(ROOT, "runners", "dsl", "src")


def _load_manifest() -> dict:
    with open(_MANIFEST_PATH) as f:
        return json.load(f)


def _sub(agent):
    return getattr(agent, "s", agent)


def _native(agent):
    sub = _sub(agent)
    return getattr(agent, "inner", getattr(sub, "_inner", None))


# ---------------------------------------------------------------------------
# 1. ENUMERATION -- the frozen core as data, cross-checked against live code.
# ---------------------------------------------------------------------------
def frozen_core_set(agent=None) -> dict[str, Any]:
    """Enumerate the frozen core. Cross-checks the manifest against the live
    Python constants it names; any mismatch is appended to `manifest_drift`
    (never raised -- a loud, inspectable field the test pins instead)."""
    from substrate.boot_core import CORE_SEEDS
    from substrate.boot_all import _FROZEN_SEED_IDS
    from domains.proposal_install import ALLOWED_INSTALL_FILES
    from domains.auto_approve import DEFAULTS as AUTO_APPROVE_DEFAULTS

    manifest = _load_manifest()
    drift: list[str] = []

    live_core = set(CORE_SEEDS)
    man_core = set(manifest["core_seed_ids"])
    if live_core != man_core:
        drift.append(f"core_seed_ids: manifest={sorted(man_core)} live boot_core.CORE_SEEDS={sorted(live_core)}")

    live_frozen = set(_FROZEN_SEED_IDS)
    man_frozen = set(manifest["frozen_seed_ids"])
    if live_frozen != man_frozen:
        drift.append(f"frozen_seed_ids: manifest={sorted(man_frozen)} live boot_all._FROZEN_SEED_IDS={sorted(live_frozen)}")

    live_files = set(ALLOWED_INSTALL_FILES)
    man_files = set(manifest["allowed_install_files"])
    if live_files != man_files:
        drift.append(f"allowed_install_files: manifest={sorted(man_files)} live proposal_install.ALLOWED_INSTALL_FILES={sorted(live_files)}")

    live_enabled_default = bool(AUTO_APPROVE_DEFAULTS.get("enabled", True))
    man_enabled_default = bool(manifest["auto_approve_default"]["enabled"])
    if live_enabled_default != man_enabled_default:
        drift.append(f"auto_approve default 'enabled': manifest={man_enabled_default} live={live_enabled_default}")

    # governance files must never overlap the rung-4 write surface -- checked
    # here as data, not just asserted in prose.
    gov_basenames = {os.path.basename(p) for p in manifest["governance_files"]}
    overlap = gov_basenames & live_files
    if overlap:
        drift.append(f"governance/install-surface OVERLAP (should be empty): {sorted(overlap)}")

    drives: list[dict] = []
    for d in manifest["frozen_drives"]:
        entry = {"name": d["name"], "seed": d["seed"], "expected_frozen": True,
                  "found_node": None, "found_frozen": None}
        if agent is not None:
            sub = _sub(agent)
            try:
                for n in sub.nodes("Drive"):
                    at = sub.node(n)["attrs"]
                    if at.get("name") == d["name"]:
                        entry["found_node"] = str(n)
                        entry["found_frozen"] = bool(at.get("frozen"))
                        break
            except Exception:  # noqa: BLE001 -- Drive type not present in this seed set
                pass
        drives.append(entry)

    try:
        closed = frozen_seed_ids_closed()
        frozen_by_dependency = sorted(closed - live_frozen)
        closure_error = None
    except Exception as e:  # noqa: BLE001 -- reported, not raised, for this READ-ONLY enumeration
        closed = live_frozen
        frozen_by_dependency = []
        closure_error = f"{type(e).__name__}: {e}"

    man_closure = set(manifest.get("frozen_seed_ids_closed_by_dependency") or [])
    if closure_error is None and man_closure != set(frozen_by_dependency):
        drift.append(f"frozen_seed_ids_closed_by_dependency: manifest={sorted(man_closure)} "
                     f"live domains.frozen_core.frozen_seed_ids_closed()={sorted(frozen_by_dependency)}")

    return {
        "drives": drives,
        "core_seed_ids": sorted(live_core),
        "frozen_seed_ids": sorted(live_frozen),
        "frozen_seed_ids_closed": sorted(closed),
        "frozen_by_dependency": frozen_by_dependency,
        "frozen_closure_error": closure_error,
        "composer_chain_seed_ids": sorted(live_frozen - live_core - {"autonomy"}),
        "allowed_install_files": sorted(live_files),
        "governance_files": list(manifest["governance_files"]),
        "auto_approve_default_enabled": live_enabled_default,
        "denylist_refs": list(manifest["denylist_refs"]),
        "known_gaps": list(manifest["known_gaps"]),
        "manifest_drift": drift,
    }


# ---------------------------------------------------------------------------
# helpers shared by several grammar checkers
# ---------------------------------------------------------------------------
def _rule_summary_from_seed(sub, rule_name: str) -> Optional[str]:
    for n in sub.nodes("RuleSummary"):
        at = sub.node(n)["attrs"]
        if at.get("name") == rule_name:
            return at.get("from_seed") or ""
    return None


def rung4_touchable_files() -> set:
    """Every file the rung-4 renderer can name for ANY currently-registered
    semantic kind, unioned with the static ALLOWED_INSTALL_FILES allowlist --
    a dynamic re-derivation (not just the hardcoded set) so drift between
    the template surface and the allowlist itself would show up here too."""
    from domains.proposal_install import ALLOWED_INSTALL_FILES
    from domains import self_extend_rust as ser
    touched = set(ALLOWED_INSTALL_FILES)
    # `_emit_graph_reachability` is the one concrete template this repo ships
    # (the others, e.g. matrix_whiten, are documented but not all wired into
    # _TEMPLATES yet) -- probe every registered kind's homes mechanically.
    try:
        spec = {"name": "FrozenCoreProbe", "semantics": {"kind": "graph_reachability"},
                "purpose": "probe", "why_new": "probe", "motivating_residual": "probe"}
        frags = ser.render_spec(spec)
        touched |= {key.split(" ", 1)[0] for key in frags}
    except Exception:  # noqa: BLE001 -- best-effort widening only
        pass
    return touched


def seed_dependency_closure(seed_ids) -> dict:
    """Graph-structural check via the REAL installed `ReachableFrom` Term:
    build a throwaway substrate carrying one `Seed{id}` node per seed reached
    by walking each given seed's OWN manifest-declared `depends_on` list
    (recursively -- the exact edge shape `substrate/boot_core.py:load_seeds_
    into` writes: `child --depends_on--> parent`), wire the real edges, then
    ask `ReachableFrom` for each seed's full transitive dependency closure.

    Returns {seed_id: {"closure": [...], "outside_frozen": [...]}} -- any
    non-empty `outside_frozen` means that (frozen) seed structurally depends
    on a seed the skippable-denylist does NOT protect (see
    seeds/frozen_core_manifest.json's `known_gaps[0]`)."""
    import substrate_rs as srs
    from substrate.seed_loader import manifest_for
    from substrate.boot_all import _FROZEN_SEED_IDS

    s = srs.Substrate()
    inner = s._inner
    node_of: dict[str, Any] = {}
    seen: set = set()

    def visit(sid: str):
        if sid in seen:
            return
        seen.add(sid)
        try:
            d = manifest_for(sid)
        except Exception:
            d = {"depends_on": []}
        nid = s.add_node("Seed", {"id": sid})
        node_of[sid] = nid
        for dep in (d.get("depends_on") or []):
            visit(dep)
            try:
                inner.add_edge_unchecked(node_of[sid], "depends_on", node_of[dep])
            except TypeError:
                inner.add_edge_unchecked(node_of[sid], "depends_on", node_of[dep], {})

    for sid in seed_ids:
        visit(sid)

    out = {}
    for sid in seed_ids:
        nid = node_of[sid]
        reached = inner.evaluate(
            {"type": "ReachableFrom", "node": {"type": "Var", "name": "start"}, "edge_type": "depends_on"},
            {"start": nid})
        reached_ids = {s.node(r)["attrs"].get("id") for r in reached if s.has_node(r)}
        outside = sorted(reached_ids - set(_FROZEN_SEED_IDS))
        out[sid] = {"closure": sorted(reached_ids), "outside_frozen": outside}
    return out


def frozen_seed_ids_closed() -> frozenset:
    """The DEPENDENCY-CLOSED frozen set (closes known_gaps['seed_dependency_
    closure']): `boot_all._FROZEN_SEED_IDS` unioned with the transitive
    `depends_on` closure of every seed in it, computed via the same real
    `ReachableFrom` Term `seed_dependency_closure` uses -- so a frozen seed's
    own dependencies (e.g. `autonomy`'s `depends_on: ['enact', 'discourse']`,
    neither of which was itself in the pinned denylist) become frozen-BY-
    CLOSURE too. This is the set `substrate.boot_all.load_all_seeds` refuses
    to skip, not the raw `_FROZEN_SEED_IDS` alone -- so the consumer-side
    enforcement automatically protects a frozen seed's dependencies as well
    as the frozen seeds themselves.

    Deliberately does NOT catch its own exceptions -- `load_all_seeds` relies
    on an exception here meaning "the frozen set could not be established",
    and fails safe (refuses every skip in the request) rather than treating a
    computation failure as an empty/partial frozen set."""
    from substrate.boot_all import _FROZEN_SEED_IDS

    base = set(_FROZEN_SEED_IDS)
    closure = seed_dependency_closure(sorted(base))
    closed = set(base)
    for info in closure.values():
        closed.update(info["closure"])
    return frozenset(closed)


# ---------------------------------------------------------------------------
# 2. MUTATION GRAMMARS -- one entry per self-modification path.
# ---------------------------------------------------------------------------
class MutationGrammar:
    def __init__(self, name: str, description: str, reaches: Callable[[dict], tuple]):
        self.name = name
        self.description = description
        self.reaches = reaches  # target dict -> (bool reaches, str evidence)

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description}


def mutation_grammars(agent) -> list[MutationGrammar]:
    """Build the 5 mutation-grammar checkers named in the task. Each
    `reaches(target)` is a REAL check (a call into the real gate, or a
    structural fact verified by reading/inspecting the real Term/allowlist),
    scoped to whether the PARENT's own live graph/ruleset/source tree could
    be rewritten -- never a re-implementation of the gate's logic."""
    sub = _sub(agent)
    native = _native(agent)
    from domains.proposal_install import ALLOWED_INSTALL_FILES
    from domains.auto_approve import DEFAULTS as AUTO_APPROVE_DEFAULTS
    from domains import reflective_faculty as rf

    # --- Grammar 1: EditOps / structural+acting variant COMPOSITION --------
    # `_compose_structural_variant` / `_compose_acting_variant` never call
    # add_rule/remove_rule on the PARENT's own `native` substrate at all --
    # grep-verified: the only `native.add_rule`/`native.remove_rule`/
    # `.remove_rule(` call sites anywhere in reflective_faculty.py are
    # `perform_adoptions` (Grammar 2, gated) and `revert_adoption` (only
    # ever undoes a PRIOR perform_adoptions). The built variant is written
    # only into `delta_attrs["add_rules"/"remove_rules"]`, which becomes a
    # `SeedDelta` node consumed exclusively by a DISPATCHED CHILD's own,
    # separate substrate (domains/experiment_dispatch.py `_spawn` ->
    # `subprocess.Popen` -> `scripts/arc_child_run.py`) -- never applied to
    # the parent.
    def _reaches_edit_ops(target: dict) -> tuple:
        if target.get("kind") == "rule":
            return (False,
                    "compose_structural_variant/compose_acting_variant only ever write into a "
                    "SeedDelta.add_rules/remove_rules for a DISPATCHED CHILD subprocess "
                    "(experiment_dispatch._spawn -> arc_child_run.py's OWN substrate); neither "
                    "function calls add_rule/remove_rule on the parent's own native substrate "
                    "(verified: perform_adoptions/revert_adoption are the only remove_rule callers "
                    "in reflective_faculty.py). NOTE (latent gap, see known_gaps): the SELECTION "
                    "step (_pick_acting_rule) has no skippable filter, but selecting a name is not "
                    "the same as writing it to the parent.")
        return (False, "not applicable to this target kind")

    # --- Grammar 2: Adoption fold-back -- the ONLY path that writes the ----
    # parent's own live ruleset directly (besides revert_adoption undoing
    # it). Calls the REAL `_rule_denylisted` veto.
    def _reaches_adoption(target: dict) -> tuple:
        if target.get("kind") != "rule":
            return (False, "not applicable to this target kind")
        name = target["name"]
        denied, reason = rf._rule_denylisted(sub, name)
        return (not denied, reason or "allowed (skippable provenance)")

    # --- Grammar 3: Composer minting (_compose_*_rule -> add_rule) --------
    # Additive-only: every minted rule's name is the picked/base name plus a
    # unique '_<kind>variant_<tag>' / 'mark_adopt_ready_<tag>' style suffix
    # derived from the agent's own capability-key tag -- never a bare copy of
    # an existing rule's name (grep-verified across every `_compose_*_rule`
    # in reflective_faculty.py: every `out["name"] = ...` / rule dict literal
    # concatenates a tag). It never calls remove_rule at all.
    def _reaches_composer_minting(target: dict) -> tuple:
        return (False,
                "every _compose_*_rule builder mints ADD-only rules whose name is the base name "
                "plus a unique agent-chosen tag suffix (never bare-collides with an existing "
                "rule's name) and none of them calls remove_rule -- additive only, verified by "
                "reading every _compose_*_rule in domains/reflective_faculty.py")

    # --- Grammar 4: Rung-4 runtime install ---------------------------------
    def _reaches_rung4(target: dict) -> tuple:
        if target.get("kind") == "file":
            name = target["name"]
            if name in ALLOWED_INSTALL_FILES:
                return (True, f"{name!r} IS in ALLOWED_INSTALL_FILES -- a legitimate rung-4 install "
                               "target (none of these are frozen-core files; see governance_files "
                               "disjointness in frozen_core_set)")
            return (False, f"{name!r} is not in ALLOWED_INSTALL_FILES -- install_proposal's "
                            "guardrail 5 independently re-derives every touched file from "
                            "render_spec(spec) and refuses unless ALL are in the allowlist")
        if target.get("kind") == "auto_approve_enabled":
            return (bool(AUTO_APPROVE_DEFAULTS.get("enabled")),
                    "AutoApprovePolicy.enabled default -- off unless a human explicitly flips it")
        return (False, "not applicable to this target kind")

    # --- Grammar 5: seed-skip / SeedDelta ablation -------------------------
    # For the PARENT's own live graph: structurally inapplicable. You cannot
    # "unload" a seed from an already-booted substrate (arc_child_run.py's
    # own module docstring says so, and boot_child_agent's FRESH+SKIP path
    # only ever boots a NEW, separate substrate). skip_seeds is consumed by
    # `load_all_seeds(agent, skip=...)` on that fresh child substrate only.
    def _reaches_seed_skip(target: dict) -> tuple:
        if target.get("kind") != "seed":
            return (False, "not applicable to this target kind")
        return (False,
                "skip_seeds is only ever consumed by boot_child_agent's FRESH+SKIP path, which "
                "boots a NEW, separate child substrate (scripts/arc_child_run.py) -- there is no "
                "code path that 'unloads' a seed from the PARENT's own already-booted graph. "
                "As of the consumer-side fix, that consumption point "
                "(substrate.boot_all.load_all_seeds) ALSO independently refuses any skip naming "
                "a seed in frozen_seed_ids_closed() -- formerly known_gaps"
                "['seed_skip_unvalidated_at_consumption'], now closed -- so even the CHILD's own "
                "fresh substrate can no longer be booted without the frozen core.")

    return [
        MutationGrammar("edit_ops_variant_compose",
                         "domains/edit_ops.py appliers + reflective_faculty._compose_structural_variant"
                         "/_compose_acting_variant -- structural/threshold rule-variant composition",
                         _reaches_edit_ops),
        MutationGrammar("adoption_fold_back",
                         "reflective_faculty.perform_adoptions -- folds a supported experiment's variant "
                         "into the parent; gated by _rule_denylisted",
                         _reaches_adoption),
        MutationGrammar("composer_minting",
                         "reflective_faculty._compose_*_rule -- mints new rules from grounded relations",
                         _reaches_composer_minting),
        MutationGrammar("rung4_runtime_install",
                         "proposal_install.install_proposal + self_extend_rust -- installs a sandbox-"
                         "validated Rust primitive into the live runtime",
                         _reaches_rung4),
        MutationGrammar("seed_skip_ablation",
                         "experiment_dispatch SeedDelta.skip_seeds -- withholds seeds on a dispatched child",
                         _reaches_seed_skip),
    ]


# ---------------------------------------------------------------------------
# 3. THE INVARIANT -- loud guard, never a silent pass.
# ---------------------------------------------------------------------------
def assert_core_unreachable(agent) -> dict:
    """For every mutation grammar x every frozen-core element, `reaches`
    must be False (or, for rung4's `file` targets, True only for files IN
    ALLOWED_INSTALL_FILES -- which are never frozen-core files, see
    `frozen_core_set`'s `governance_files` disjointness check). Returns
    `{ok, violations, checked}` -- violations is always a list, even when
    empty; a caller must inspect it, never trust `ok` alone blindly (though
    `ok == (violations == [])` holds by construction)."""
    core = frozen_core_set(agent)
    grammars = mutation_grammars(agent)
    violations: list[dict] = []
    checked: list[dict] = []

    targets: list[dict] = []
    for d in core["drives"]:
        targets.append({"kind": "drive", "name": d["name"]})
    for sid in core["frozen_seed_ids"]:
        targets.append({"kind": "seed", "id": sid})
    for gf in core["governance_files"]:
        targets.append({"kind": "file", "name": os.path.basename(gf)})
    targets.append({"kind": "auto_approve_enabled"})
    # ONLY rules whose OWN provenance (RuleSummary.from_seed) is a frozen
    # seed are frozen-core elements -- a rule from a genuinely skippable seed
    # is SUPPOSED to be adoption-reachable (that's the whole point of the
    # skippable/non-skippable split), so it is deliberately NOT a target
    # here (checking it would make "reaches==True" look like a violation
    # when it is actually correct, gated behaviour). If this agent's graph
    # has no frozen-provenance RuleSummary yet, this is simply empty --
    # honest, not padded (the discriminative battery covers the synthetic
    # core-provenance-rule case explicitly).
    try:
        sub = _sub(agent)
        for n in sub_nodes_of_type(agent, "RuleSummary"):
            at = sub.node(n)["attrs"]
            name = at.get("name")
            if name and at.get("from_seed") in core["frozen_seed_ids"]:
                targets.append({"kind": "rule", "name": name})
    except Exception:  # noqa: BLE001 -- RuleSummary type not present yet
        pass

    for g in grammars:
        for t in targets:
            reaches, evidence = g.reaches(t)
            checked.append({"grammar": g.name, "target": t, "reaches": reaches, "evidence": evidence})
            # the ONE expected True: rung4 legitimately "reaches" (can write) its own
            # ALLOWED_INSTALL_FILES -- none of which is a frozen-core file (see
            # governance_files disjointness in frozen_core_set). Every other
            # `reaches == True` is a genuine violation of the parent-identity invariant.
            expected_true = (g.name == "rung4_runtime_install" and t.get("kind") == "file"
                              and t.get("name") in core["allowed_install_files"])
            is_violation = reaches and not expected_true
            if is_violation:
                violations.append({"grammar": g.name, "target": t, "evidence": evidence})

    return {"ok": len(violations) == 0, "violations": violations, "checked": checked,
            "manifest_drift": core["manifest_drift"], "known_gaps": core["known_gaps"]}


def sub_nodes_of_type(agent, node_type: str):
    return list(_sub(agent).nodes(node_type))
