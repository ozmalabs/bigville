"""proposal_install — the ONE reusable HOST helper that turns a validated,
sandbox-proven `ExtensionProposal` into an installed runtime primitive.

Approval is a HUMAN decision surfaced through I/O (a web click, or — a
follow-up feature — an auto-approve policy) — not agent cognition, so this
module is host/adapter work per CLAUDE.md: it never decides WHAT to build
(the agent already decided that, as a RustExtensionSpec) and never decides
WHETHER the primitive is good (a human, or a policy, decided that by calling
this function at all). What it owns is making that decision SAFE: guardrails
that refuse anything the sandbox hasn't just re-proven, anything that would
touch a file outside the tiny installer surface, and anything already done.

Two callers use this, both by calling `install_proposal` directly — neither
re-implements the guardrails:
  1. `scripts/jabberwock_daemon.py`'s `POST /api/proposals/<id>/approve`
     route (this task).
  2. An auto-approve policy (a follow-up task) — see the note at the bottom
     of this docstring for exactly how it should call in.

------------------------------------------------------------------------
GUARDRAIL POLICY (read before touching this file — refuse-first, in order)
------------------------------------------------------------------------
 0. The proposal must exist and be linked (`validates` edge) to a
    RustExtensionSpec node. has_node-guarded throughout (node ids recycle
    in this substrate — a stale id can silently name a DIFFERENT node).
 1. `installed: true` already -> refuse (no double-install; the record is
    the single source of truth for "has this run once").
 2. `status == "already_present"` -> NOT a failure: the primitive is
    already live in `runners/dsl/src` (someone else's proposal for the
    same name landed, or an earlier approval already ran the real
    installer). Idempotent no-op: mark `installed: true` and return
    ok=True, but never call the real installer (no cargo, no maturin —
    there is nothing to build).
 3. Anything else that isn't `status == "validated"` (i.e. "failed", or an
    unrecognised value) -> refuse outright. A failed sandbox check is never
    a green light.
 4. Sandbox re-validation, FRESH, right now: `self_extend_rust.validate_spec`
    is re-run in DRY mode (substrate=None, so it mints no graph nodes) even
    though the proposal already says "validated" — the live tree may have
    drifted since that proposal was minted (another spec landed in the
    meantime, a manual edit, …). If the fresh check does not pass, refuse.
    (If the fresh check itself now reports "already_present" — the tree
    moved out from under us between mint and approval — that's the same
    idempotent no-op as guardrail 2, not a failure.)
 5. Denylist: independently derive, from `render_spec(spec)`, every file
    the installer would touch, and refuse unless EVERY one is in
    `ALLOWED_INSTALL_FILES` (the small, real set of homes every existing
    rung-4 template writes into: term.rs / jsonio.rs / reflect.rs / py.rs /
    shape.rs — see domains/runtime_design.py's `emit_primitive_rust` and
    domains/self_extend_rust.py's `_emit_graph_reachability`). This is
    deliberately conservative: a legitimate FUTURE primitive that needs a
    new home is refused here until a human extends the allowlist on
    purpose, not silently allowed through.

Only once ALL five guardrails pass does this module call the ONE sanctioned
live-source installer, `domains.self_extend.PrimitiveExtension.extend` — the
same real, working, self-snapshotting/all-or-nothing/auto-rollback pipeline
that landed ArgMax, DtwTo, Whiten, WithinScatter, BetweenScatter, WhitenMany,
and the structural-recursion family. This module NEVER writes to
`runners/dsl/src` or calls maturin itself; it only calls into that pipeline
and reports what it said.

------------------------------------------------------------------------
RESTART SEMANTICS
------------------------------------------------------------------------
`PrimitiveExtension.extend(..., build=True)` runs `maturin develop --release`
on success, which hot-swaps the on-disk `_native*.so`. That swap is only
visible to Python processes that `import substrate_rs` AFTER the swap — a
process already running (e.g. the very daemon that called this function)
keeps its already-mapped `.so` until it restarts. So a successful install
here ALWAYS returns `requires_restart: True`, and this function NEVER
restarts anything — it only surfaces the flag. The new Term is live
immediately for any fresh process (a new test run, a new script invocation);
for the currently-running daemon, it activates on that daemon's next
restart (daemon self-restart is a follow-up feature, not built here).

------------------------------------------------------------------------
FOR THE NEXT AGENT (auto-approve)
------------------------------------------------------------------------
Call `install_proposal(agent, proposal_id, approver="auto")` — same
contract, same guardrails, no special-casing needed. Your policy decides
WHICH proposal ids to approve and WHEN (e.g. only ones whose spec is
`grounded_in_science`, or only below some risk threshold); this function
still independently re-validates and re-derives the denylist every single
call, so a stale or malicious decision on your end cannot skip guardrail 4
or 5. Don't reach into `domains.self_extend.PrimitiveExtension` directly —
if you find yourself wanting to bypass a guardrail here, extend a guardrail
here (so both callers get the fix), not around it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional

from domains import self_extend_rust as ser
from domains.self_extend import PrimitiveExtension
from domains.teach import teach

# The only files the sanctioned installer is ever allowed to touch. Derived
# from every semantic_kind template that exists today (runtime_design.py's
# emit_primitive_rust + self_extend_rust.py's own graph_reachability
# template): term.rs / jsonio.rs / reflect.rs cover every existing kind,
# py.rs covers the external-IO family (agent_specify_http_get et al.), and
# shape.rs is touched by a couple of the matrix-shaped kinds (Whiten et al.).
# Anything outside this set is treated as suspect. See GUARDRAIL POLICY #5.
ALLOWED_INSTALL_FILES = {"term.rs", "jsonio.rs", "reflect.rs", "py.rs", "shape.rs"}

SCRATCH_DEFAULT = os.environ.get(
    "SELF_EXTEND_SCRATCH",
    os.path.join(os.path.expanduser("~"), ".cache", "gamma_substrate_self_extend"))


def _nid_value(nid: Any) -> Any:
    return nid.value if hasattr(nid, "value") else nid


def _sub(agent):
    return getattr(agent, "s", agent)


def _inner(agent):
    sub = _sub(agent)
    return getattr(agent, "inner", sub)


def _resolve_nid(sub, raw):
    import substrate_rs as srs
    if isinstance(raw, srs.NodeID):
        return raw
    try:
        return srs.NodeID(int(raw))
    except (TypeError, ValueError):
        return None


def _find_proposal(agent, proposal_id):
    """(prop_id, prop_attrs, spec_id, spec_attrs) for a live ExtensionProposal
    linked to its RustExtensionSpec via a `validates` edge, or None if the id
    is unknown, the node isn't an ExtensionProposal, or it isn't linked.
    has_node-guarded throughout (node ids recycle)."""
    sub = _sub(agent)
    inner = _inner(agent)
    pid = _resolve_nid(sub, proposal_id)
    if pid is None or not sub.has_node(pid):
        return None
    pnode = sub.node(pid)
    if pnode.get("type") != "ExtensionProposal":
        return None
    prop_attrs = pnode["attrs"]
    try:
        spec_ids = list(inner.neighbours(pid, "validates"))
    except Exception:  # noqa: BLE001
        spec_ids = []
    spec_id = next((sid for sid in spec_ids if sub.has_node(sid)), None)
    if spec_id is None:
        return None
    return pid, prop_attrs, spec_id, sub.node(spec_id)["attrs"]


def _spec_dict_from_node(spec_attrs: dict) -> dict:
    """Recover and authenticate the complete durable RustExtensionSpec.

    Old checkpoints only contain the historical summary.  That summary is
    sufficient for ``graph_reachability`` and remains readable for migration,
    but every richer semantic kind is refused rather than guessed.
    """
    raw = spec_attrs.get("spec_json")
    if raw:
        expected = spec_attrs.get("spec_sha256")
        actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if not expected or actual != expected:
            raise ValueError("persisted RustExtensionSpec hash mismatch")
        try:
            spec = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("persisted RustExtensionSpec is not valid JSON") from exc
        if not isinstance(spec, dict) or not isinstance(spec.get("semantics"), dict):
            raise ValueError("persisted RustExtensionSpec has no semantics object")
        if spec.get("name") != spec_attrs.get("name"):
            raise ValueError("persisted RustExtensionSpec name mismatch")
        if spec["semantics"].get("kind") != spec_attrs.get("semantics_kind"):
            raise ValueError("persisted RustExtensionSpec semantics mismatch")
        return spec

    if spec_attrs.get("semantics_kind") != "graph_reachability":
        raise ValueError(
            "legacy RustExtensionSpec is incomplete for this semantic kind; "
            "re-author and re-validate it"
        )
    return {
        "name": spec_attrs.get("name"),
        "semantics": {"kind": spec_attrs.get("semantics_kind")},
        "purpose": spec_attrs.get("purpose", ""),
        "why_new": spec_attrs.get("why_new", ""),
        "motivating_residual": spec_attrs.get("motivating_residual", ""),
    }


def _mint_install_record(agent, proposal_nid, approver: str, *, ok: bool, note: str = "") -> None:
    sub = _sub(agent)
    inner = _inner(agent)
    iid = sub.add_node("Install", {
        "proposal": _nid_value(proposal_nid), "approver": approver,
        "ts": time.time(), "ok": bool(ok), "note": note[:1500],
    })
    try:
        inner.add_edge_unchecked(iid, "installs", proposal_nid)
    except Exception:  # noqa: BLE001 -- bookkeeping edge, never fatal
        pass


def _mark_installed(agent, pid, approver: str, *, status: Optional[str] = None) -> None:
    sub = _sub(agent)
    sub.set_attr(pid, "installed", True)
    sub.set_attr(pid, "approved_by", approver)
    sub.set_attr(pid, "approved_ts", time.time())
    sub.set_attr(pid, "requires_restart", True)
    if status is not None:
        sub.set_attr(pid, "status", status)


def install_proposal(agent, proposal_id, *, approver: str = "web",
                      spec: Optional[dict] = None,
                      scratch_dir: Optional[str] = None) -> dict:
    """Install one ExtensionProposal, guardrails-first. See the module
    docstring for the full policy. Returns:

        {"ok": True,  "installed": True, "requires_restart": True,
         "rebuilt": bool, "reason": str}                        -- success
        {"ok": False, "reason": str, "diagnostics": str | None}  -- refused

    `rebuilt=False` means the idempotent already-present path was taken (no
    cargo/maturin call at all); `rebuilt=True` means the real installer ran.
    """
    sub = _sub(agent)
    found = _find_proposal(agent, proposal_id)
    if found is None:
        return {"ok": False, "reason": "proposal not found (or not linked to a spec)"}
    pid, prop_attrs, spec_id, spec_attrs = found

    # guardrail 1: no double-install.
    if bool(prop_attrs.get("installed")):
        return {"ok": False, "reason": "already installed",
                "installed": True,
                "requires_restart": bool(prop_attrs.get("requires_restart", True))}

    status = prop_attrs.get("status")

    # guardrail 2: already_present -> idempotent no-op, never rebuild.
    if status == "already_present":
        _mark_installed(agent, pid, approver)
        _mint_install_record(agent, pid, approver, ok=True, note="already in runtime")
        return {"ok": True, "installed": True, "requires_restart": True,
                "rebuilt": False, "reason": "already in runtime"}

    # guardrail 3: only a currently-validated proposal is a green light.
    if status != "validated":
        return {"ok": False, "reason": f"status is {status!r}, not 'validated'"}

    if spec is None:
        try:
            spec = _spec_dict_from_node(spec_attrs)
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}
    if spec.get("name") != spec_attrs.get("name"):
        return {"ok": False, "reason": "spec name does not match the proposal's RustExtensionSpec"}

    # guardrail 4: re-run the sandbox check FRESH, dry (substrate=None -> no
    # graph mutation) -- the live tree may have moved since this proposal
    # was minted.
    scratch = scratch_dir or SCRATCH_DEFAULT
    fresh = ser.validate_spec(None, spec, scratch_dir=scratch)
    if fresh.get("stage") == "already_present" and fresh.get("ok"):
        # the tree moved out from under us between mint and approval --
        # same idempotent no-op as guardrail 2, not a failure.
        _mark_installed(agent, pid, approver, status="already_present")
        _mint_install_record(agent, pid, approver, ok=True,
                              note="already in runtime (detected at approval time)")
        return {"ok": True, "installed": True, "requires_restart": True,
                "rebuilt": False,
                "reason": "already in runtime (detected at approval time)"}
    if not fresh.get("ok"):
        return {"ok": False, "reason": "fresh sandbox re-validation failed",
                "diagnostics": fresh.get("diagnostics") or fresh.get("errors")}

    # guardrail 5: denylist -- every file the render would touch must be in
    # the small allowed set. Derived independently of the fresh check above
    # (which already rendered internally) so this is a real, standalone gate
    # a caller can't route around by pre-validating elsewhere.
    try:
        frags = ser.render_spec(spec)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"render_spec failed: {type(e).__name__}: {e}"}
    touched_files = {key.split(" ", 1)[0] for key in frags}
    disallowed = touched_files - ALLOWED_INSTALL_FILES
    if disallowed:
        return {"ok": False,
                "reason": f"refusing: spec would touch disallowed file(s) {sorted(disallowed)} "
                          f"(allowed: {sorted(ALLOWED_INSTALL_FILES)})"}

    # Cognitive commitment is distinct from the hard guardrails above: those
    # cannot be traded away. Only after they pass does the graph compare
    # commit against waiting/refinement using the concrete touched-file
    # footprint; the supplied approver remains a hard host authorization.
    from domains.information_commitment import assess
    commitment = assess(
        agent,
        commit={
            "name": "runtime_install",
            "expected_goal_work": float(prop_attrs.get("expected_goal_work", 10.0)),
            "expected_information_gain": float(
                prop_attrs.get("expected_information_gain", 1.0)),
            "uncertainty": float(prop_attrs.get("consequence_uncertainty", 0.0)),
            "requires_approval": 1.0,
            "footprint": {
                "deleted_facts": 0.0,
                "overwritten_facts": float(len(touched_files)),
                "recoverability": 0.5,
                "externality": 1.0,
            },
        },
        wait={"delay_cost": 1.0, "opportunity_cost": 1.0},
        refine={"refinement_cost": 2.0},
        approver=approver,
    )
    if commitment["decision"] != "commit" or not commitment["authorized"]:
        return {
            "ok": False,
            "reason": "information commitment selected "
                      f"{commitment['decision']!r}: {commitment['reason']}",
            "commit_decision": commitment["record"],
        }

    # All guardrails passed -- hand off to the ONE sanctioned live-source
    # installer. Never reached by any refused/idempotent path above.
    ext_spec = dict(spec)
    ext_spec.setdefault("semantic_kind", spec.get("semantics", {}).get("kind"))
    pe = PrimitiveExtension()
    try:
        result = pe.extend(ext_spec, build=True)
    except Exception as e:  # noqa: BLE001 -- report, never crash the caller
        _mint_install_record(agent, pid, approver, ok=False,
                              note=f"{type(e).__name__}: {e}")
        return {"ok": False, "reason": f"install raised: {type(e).__name__}: {e}",
                "diagnostics": str(e)}

    if not result.get("ok"):
        sub.set_attr(pid, "installed", False)
        diag = str(result.get("detail") or result.get("errors") or "")[:1500]
        sub.set_attr(pid, "last_error", diag)
        _mint_install_record(agent, pid, approver, ok=False, note=diag)
        return {"ok": False, "reason": f"install failed at stage {result.get('stage')!r}",
                "diagnostics": result.get("detail") or result.get("errors")}

    _mark_installed(agent, pid, approver)
    _mint_install_record(agent, pid, approver, ok=True, note="installed")

    name = spec.get("name")
    teach(agent, "TaughtHint", {
        "topic": f"runtime_extension_{name}",
        "answer": (f"{name} was authored as a RustExtensionSpec, sandbox-validated, "
                   f"approved by {approver}, and installed into my runtime. "
                   "Requires a restart to take effect for any already-running process "
                   "(the new Term is live immediately for fresh processes)."),
    }, category="runtime_extensions")

    return {"ok": True, "installed": True, "requires_restart": True,
            "rebuilt": True, "reason": "installed"}
