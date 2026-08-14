"""Mechanical bridge to graph-native thermodynamic commitment.

The graph scores and selects wait/refine/commit. This adapter only writes the
candidate facts, ticks rules, reads the resolved CommitDecision, and enforces a
non-tradeable external approval requirement.
"""
from __future__ import annotations


_METRICS = (
    "preservation_value", "expected_information_gain", "delay_cost",
    "opportunity_cost", "decision_relevance", "refinement_cost",
    "expected_goal_work", "information_destroyed", "option_volume_lost",
    "resource_cost", "uncertainty", "irreversibility",
)


def _resolve(agent):
    substrate = getattr(agent, "s", agent)
    native = getattr(agent, "inner", getattr(substrate, "_inner", substrate))
    return substrate, native


def _ensure_loaded(agent):
    """Idempotently install the two core manifests at the first effect gate."""
    substrate, native = _resolve(agent)
    try:
        names = {r.get("name") for r in native.export_rules()}
    except Exception:
        names = set()
    if "ic_score_commit" in names:
        return
    from substrate.seed_loader import manifest_for
    root = getattr(agent, "agent", None)
    if root is None:
        try:
            roots = list(substrate.nodes("Agent"))
        except Exception:
            roots = []
        root = roots[0] if roots else substrate.add_node(
            "Agent", {"role": "commitment_root"})
    for seed in ("cognitive_areas", "information_commitment"):
        native.load_seed_manifest(manifest_for(seed), root)


def _add_edge(native, src, edge_type, tgt):
    try:
        native.add_edge(src, edge_type, tgt)
    except (TypeError, AttributeError):
        native.add_edge_unchecked(src, edge_type, tgt)


def _candidate(substrate, native, context, kind, attrs):
    values = {key: float(attrs.get(key, 0.0)) for key in _METRICS}
    values.update({
        "name": str(attrs.get("name", kind)),
        "decision_kind": kind,
        "hard_veto": float(attrs.get("hard_veto", 0.0)),
        "requires_approval": float(attrs.get("requires_approval", 0.0)),
        "chosen": 0.0,
        "net_value": 0.0,
    })
    node = substrate.add_node("CommitOption", values)
    _add_edge(native, context, "has_candidate", node)
    return node


def assess(agent, *, commit, wait=None, refine=None, approver=None,
           retain_trace=True):
    """Return the graph's decision plus separate hard-host authorization.

    Callers must have loaded ``cognitive_areas`` + ``information_commitment``.
    ``commit`` contains a concrete ``footprint`` dict; omitting it fails closed
    in graph rules.
    """
    _ensure_loaded(agent)
    substrate, native = _resolve(agent)
    context = substrate.add_node("DecisionContext", {
        "status": "open", "decided": 0.0, "decision": "",
    })
    wait_node = _candidate(substrate, native, context, "wait", wait or {})
    refine_node = _candidate(substrate, native, context, "refine", refine or {})
    commit_node = _candidate(substrate, native, context, "commit", commit)
    footprint = commit.get("footprint")
    if footprint is not None:
        fp = substrate.add_node("EffectFootprint", {
            "deleted_facts": float(footprint.get("deleted_facts", 0.0)),
            "overwritten_facts": float(footprint.get("overwritten_facts", 0.0)),
            "recoverability": float(footprint.get("recoverability", 0.0)),
            "externality": float(footprint.get("externality", 0.0)),
        })
        _add_edge(native, commit_node, "has_effect_footprint", fp)
    native.run_rules()

    decisions = list(native.neighbours(context, "has_commit_decision"))
    if not decisions:
        return {
            "decision": None, "authorized": False, "reason": "no_unique_decision",
            "context": context, "candidate": None, "record": None,
        }
    record = decisions[0]
    selected = list(native.neighbours(record, "selected"))
    candidate = selected[0] if selected else None
    decision = substrate.node(record)["attrs"].get("decision_kind")
    requires_approval = bool(
        candidate is not None
        and substrate.node(candidate)["attrs"].get("requires_approval"))
    authorized = decision != "commit" or not requires_approval or bool(approver)
    native.set_attr(record, "status", "authorized" if authorized else "awaiting_approval")
    if approver:
        native.set_attr(record, "approver", str(approver))
    if candidate is not None:
        native.set_attr(candidate, "authorized", 1.0 if authorized else 0.0)
    result = {
        "decision": decision, "authorized": authorized,
        "reason": "graph_resolved" if authorized else "external_approval_required",
        "context": context, "candidate": candidate, "record": record,
        "alternatives": {"wait": wait_node, "refine": refine_node, "commit": commit_node},
    }
    if not retain_trace:
        # Runtime effectors keep the durable CommitDecision but retire the
        # transient option workspace so unrelated ActionCandidate-style
        # cognition cannot see stale alternatives.
        for node in (wait_node, refine_node, commit_node, context):
            if native.has_node(node):
                native.remove_node(node)
        result["context"] = None
        result["candidate"] = None
        result["alternatives"] = {}
    return result
