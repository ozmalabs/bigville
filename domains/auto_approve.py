"""auto_approve — the HUMAN'S OWN SETTING for the rung-4 self-extension
install path, plus the mechanical policy evaluation that acts on it.

`domains/proposal_install.py` already carries the load-bearing safety logic:
`install_proposal(agent, id, approver=...)` re-runs its five guardrails
(status, idempotence, fresh sandbox re-validation, file denylist) on EVERY
call, regardless of who the approver is. That module's own docstring invites
this file to exist: "an auto-approve policy ... calls
`install_proposal(agent, proposal_id, approver='auto')` — same contract,
same guardrails". This module is that caller, plus the graph-resident
setting a human toggles to turn it on.

Per CLAUDE.md this is HOST/POLICY work, not agent cognition: `scan_and_
auto_approve` reads two kinds of graph data (the human's `AutoApprovePolicy`
thresholds, and the agent's own `ExtensionProposal` verdicts) and applies a
fixed, mechanical comparison — it never decides WHAT to build (the agent
already decided that) or WHETHER a proposal is a good idea in some open
sense (the sandbox already decided compileability; this only decides
whether it fits inside a human-configured SCOPE). Nothing here is a Rule
authored by the agent, and nothing here bypasses a guardrail
`install_proposal` already owns — it can only make its call MORE
conservative (skip), never less (it has no path that skips a hard
guardrail).

------------------------------------------------------------------------
WHY A MINTED NODE, NOT A SEED (design choice, see CLAUDE.md's seed policy)
------------------------------------------------------------------------
CLAUDE.md's seed facility (`domains/teach.py`) is for the AGENT's own
learned content: append-only, versioned, filed under the agent's own
categories. `AutoApprovePolicy` is the opposite shape — a single mutable
knob a HUMAN flips through the web UI, with no "which seed does this
belong to" question (it isn't a taught fact, it's host config living on
the graph because CLAUDE.md's rule is "state lives in the substrate").
Modeling it as a seed would mean every UI toggle rewrites a seed JSON file
on disk on every request, conflating "the agent's boot manifest" with "a
runtime knob a human just clicked" — and would fight the checkpoint model
that already exists for exactly this shape: `WorldAdapter.save`/`.load`
(scripts/jabberwock_daemon.py's checkpoint/resume loop) serialises the
WHOLE graph, so a minted node's current value survives every ordinary
daemon restart for free. The only case a minted node does NOT survive is a
FRESH boot with no checkpoint at all (first boot ever, or a checkpoint
directory wipe) — and there the safe answer is exactly what `ensure_
policy_node` gives you: re-mint with `enabled: False`. Off-by-default is
therefore a genuine invariant of this design, not just a convention: there
is no code path that boots the agent with auto-approve already on unless a
human has flipped it via the running daemon at least once and a checkpoint
since then has captured it.

------------------------------------------------------------------------
THE AutoApprovePolicy NODE (singleton; `ensure_policy_node` mints if absent)
------------------------------------------------------------------------
    enabled                  bool   default False  -- the master switch. The
        safe posture rung-4 established (web-only approval) stays the
        default; a human must explicitly opt in.
    max_installs_per_hour    int    default 2       -- rate cap. Counted
        against successful (`ok: True`) `Install` records with
        `approver == "auto"` and `ts` within the trailing hour of the scan.
        Only auto-approve's OWN throughput is capped (a human clicking
        "approve & install" in the web UI is a separate, deliberate action
        per proposal and isn't rate-limited by this policy). In practice
        this cap mostly matters ACROSS restarts within the same hour,
        because `paused_until_restart` (below) already limits a single
        daemon lifetime to at most one auto-install before a human restarts
        it — see that field's note.
    require_additive         bool   default True    -- only install a
        proposal whose RENDERED fragments are pure inserts (spliced
        before/after an anchor line, anchor text itself preserved) with no
        home that would overwrite or remove existing source. This reuses
        the SAME `self_extend_rust.render_spec` pipeline `install_proposal`
        itself calls (guardrail 5) — see `_is_additive` below — so the
        policy's notion of "additive" can never drift from what actually
        gets spliced into the sandbox.
    allowed_semantics_kinds  list[str]  default ["graph_reachability"] --
        an allowlist of `RustExtensionSpec.semantics.kind` values the
        policy will ever auto-approve. Deliberately narrow: today
        "graph_reachability" is the one kind this module's sibling
        (`self_extend_rust.py`) owns AND the one that has actually shipped
        (`ReachableFrom`, commit 54bbecf4) — so it's the one kind with a
        real track record. Every OTHER semantic kind this repo's rung-4
        pipeline can render (matrix_whiten, trajectory_distance, ...) is
        real and can compile, but widening the auto-approve allowlist to
        cover them is a deliberate human decision, not this module's
        default.
    paused_until_restart     bool   default False    -- set to True by
        `scan_and_auto_approve` the moment ANY auto-install succeeds.
        `install_proposal` always returns `requires_restart: True` on a
        real install (see that module's RESTART SEMANTICS note: the
        running process keeps its already-mapped `.so` until it restarts)
        — so in practice EVERY successful auto-install sets this. While
        paused, `scan_and_auto_approve` is a no-op, so a long-running
        daemon can never silently stack N rebuilds the running process
        will never activate. Only a daemon BOOT clears it
        (`clear_pause_on_boot`) — a restart is the thing that actually
        activates the pending install, so that's the only event allowed to
        un-pause. The web `/api/auto_approve` route intentionally does NOT
        accept `paused_until_restart` as a settable field (see the daemon
        module) — a human toggling the master switch back on must not be
        able to force another install before restarting.

------------------------------------------------------------------------
HONESTY / AUDIT TRAIL
------------------------------------------------------------------------
`scan_and_auto_approve` takes a `log` callable and calls it for EVERY
proposal it looks at, approved or skipped, with the concrete reason
(exact semantics_kind mismatch, exact additive-check failure, exact rate
numbers). This is a safety-sensitive automation (it can trigger a real
compiler run + hot-swap of the agent's own runtime with no human in the
loop) — the log is the audit trail a human reviews after the fact, not an
optional nicety.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from domains import proposal_install as pinstall
from domains import self_extend_rust as ser

# ---------------------------------------------------------------------------
# policy node: mint-if-absent, read, write, boot-clear
# ---------------------------------------------------------------------------

NODE_TYPE = "AutoApprovePolicy"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "max_installs_per_hour": 2,
    "require_additive": True,
    "allowed_semantics_kinds": ["graph_reachability"],
    "paused_until_restart": False,
}

# fields a human (the web route) is allowed to set directly. Deliberately
# excludes `paused_until_restart` -- see the module docstring's note on why
# only a daemon boot may clear that flag.
HUMAN_SETTABLE_FIELDS = ("enabled", "max_installs_per_hour", "require_additive",
                          "allowed_semantics_kinds")

_ADDITIVE_POSITIONS = {"before", "after", "append", "arm_after", "group"}

_RATE_WINDOW_S = 3600.0


def _sub(agent):
    return getattr(agent, "s", agent)


def _nid_value(nid: Any) -> Any:
    return nid.value if hasattr(nid, "value") else nid


def _policy_nodes(agent) -> list:
    sub = _sub(agent)
    try:
        return [n for n in sub.nodes(NODE_TYPE) if sub.has_node(n)]
    except Exception:  # noqa: BLE001 -- type not present in this seed set yet
        return []


def ensure_policy_node(agent):
    """Idempotent: returns the single `AutoApprovePolicy` node, minting it
    (all defaults, `enabled: False`) if this graph doesn't have one yet.
    Safe to call on every daemon boot and every scan -- never mints a
    second node once one exists."""
    sub = _sub(agent)
    existing = _policy_nodes(agent)
    if existing:
        return existing[0]
    return sub.add_node(NODE_TYPE, dict(DEFAULTS))


def get_policy(agent) -> Optional[dict]:
    """The policy node's attrs, or None if it hasn't been minted yet (a
    caller that wants a guaranteed node should call `ensure_policy_node`
    first; `scan_and_auto_approve` treats a missing node the same as
    `enabled: False`, so a fresh unminted graph is safe by construction).
    `allowed_semantics_kinds` is normalised to a plain `list` -- the native
    substrate round-trips a JSON-array attr as a `tuple`, and every caller
    of this function (the scan, the HTTP routes, the web UI's JSON) wants a
    list, not a tuple leaking an implementation detail."""
    sub = _sub(agent)
    existing = _policy_nodes(agent)
    if not existing:
        return None
    attrs = dict(sub.node(existing[0])["attrs"])
    if "allowed_semantics_kinds" in attrs:
        attrs["allowed_semantics_kinds"] = list(attrs["allowed_semantics_kinds"])
    return attrs


def set_policy(agent, **fields) -> dict:
    """Mint-if-absent, then apply the given fields (unknown keys and `None`
    values are ignored -- a caller passes only what it wants to change).
    Mechanical host-config write: this is the human's own toggle, reaching
    the graph the same way any other adapter write does, never a decision
    made ON the human's behalf. Returns the resulting attrs dict."""
    sub = _sub(agent)
    pid = ensure_policy_node(agent)
    for k, v in fields.items():
        if k not in HUMAN_SETTABLE_FIELDS or v is None:
            continue
        sub.set_attr(pid, k, v)
    return dict(sub.node(pid)["attrs"])


def clear_pause_on_boot(agent) -> None:
    """Called once at daemon boot (after `ensure_policy_node`): a process
    restart is the event that activates whatever the previous process
    auto-installed, so any pause carried in from a resumed checkpoint is
    stale the moment this new process is up. No-op if no policy node
    exists yet (nothing to clear)."""
    sub = _sub(agent)
    for pid in _policy_nodes(agent):
        sub.set_attr(pid, "paused_until_restart", False)


def policy_status(agent, *, now_ts: Optional[float] = None) -> dict:
    """The `/api/status` + `/api/auto_approve` payload: the policy's current
    scope config plus the live `installs_this_hour` counter. Reads a
    missing policy node as all-defaults (`enabled: False`) rather than
    erroring, so a fresh graph the daemon hasn't minted a node for yet
    still reports something sane."""
    now_ts = time.time() if now_ts is None else now_ts
    policy = get_policy(agent) or dict(DEFAULTS)
    return {
        "enabled": bool(policy.get("enabled", DEFAULTS["enabled"])),
        "paused_until_restart": bool(policy.get("paused_until_restart", DEFAULTS["paused_until_restart"])),
        "max_installs_per_hour": policy.get("max_installs_per_hour", DEFAULTS["max_installs_per_hour"]),
        "require_additive": bool(policy.get("require_additive", DEFAULTS["require_additive"])),
        "allowed_semantics_kinds": list(policy.get("allowed_semantics_kinds", DEFAULTS["allowed_semantics_kinds"])),
        "installs_this_hour": _count_recent_auto_installs(agent, now_ts),
    }


# ---------------------------------------------------------------------------
# scope guardrails (mechanical checks the scan applies ON TOP OF, never
# instead of, install_proposal's own five hard guardrails)
# ---------------------------------------------------------------------------

def _count_recent_auto_installs(agent, now_ts: float) -> int:
    """Successful (`ok: True`) `Install` records with `approver == "auto"`
    whose `ts` falls in the trailing hour ending at `now_ts`. Deterministic
    against a caller-supplied `now_ts` (never `time.time()` internally, so
    the rate cap is testable without real wall-clock waits)."""
    sub = _sub(agent)
    try:
        installs = list(sub.nodes("Install"))
    except Exception:  # noqa: BLE001 -- type not present in this seed set yet
        return 0
    cutoff = now_ts - _RATE_WINDOW_S
    count = 0
    for iid in installs:
        if not sub.has_node(iid):
            continue
        a = sub.node(iid)["attrs"]
        if a.get("approver") == "auto" and bool(a.get("ok")) and (a.get("ts") or 0) >= cutoff:
            count += 1
    return count


def _is_additive(spec: dict) -> tuple[bool, str]:
    """Re-derive the insert plan for `spec` via the EXACT same rendering
    pipeline `install_proposal`'s guardrail 5 uses
    (`self_extend_rust.render_spec` + `plan_inserts`/`_composition_inserts`)
    and check that every insert's `position` is one of the splice-only
    shapes `self_extend_rust.apply_to_sandbox` actually implements
    (`before`/`after`, and the composition-path's `append`/`arm_after`/
    `group`, all of which preserve the anchor text and only ADD lines
    around it -- see that module's `apply_to_sandbox`). There is currently
    no "replace" or "overwrite" position anywhere in this codebase; this
    check exists so that if a FUTURE codegen template ever introduces one,
    it fails closed here rather than silently qualifying for auto-install.

    Fails closed (returns False) on any planning error too -- if this
    module cannot even PROVE the fragments are pure inserts, it does not
    call the something-might-be-destructive path additive."""
    try:
        frags = ser.render_spec(spec)
    except Exception as e:  # noqa: BLE001
        return False, f"render_spec failed: {type(e).__name__}: {e}"
    kind = (spec.get("semantics") or {}).get("kind")
    try:
        if kind in ser._TEMPLATES:
            inserts, errors = ser.plan_inserts(frags)
        else:
            inserts, errors = ser._composition_inserts(frags), []
    except Exception as e:  # noqa: BLE001
        return False, f"insert planning failed: {type(e).__name__}: {e}"
    if errors:
        return False, f"insert planning could not place every fragment: {errors}"
    if not inserts:
        return False, "no inserts derived -- cannot prove additive"
    bad = sorted({str(i.get("home", "?")) for i in inserts
                  if i.get("position") not in _ADDITIVE_POSITIONS})
    if bad:
        return False, f"non-additive position at home(s) {bad}"
    return True, "every insert is a splice (anchor text preserved, only new lines added)"


# ---------------------------------------------------------------------------
# the scan
# ---------------------------------------------------------------------------

def scan_and_auto_approve(agent, *, now_ts: float,
                           log: Optional[Callable[[str], None]] = None) -> list[dict]:
    """Mechanical policy evaluation, NO agent decisions: reads the human's
    `AutoApprovePolicy` thresholds and every `ExtensionProposal` the agent's
    own rung-4 pipeline has already sandbox-validated, and installs the
    ones that fit inside the configured scope by calling
    `proposal_install.install_proposal(agent, id, approver="auto")` --
    which re-runs its own five hard guardrails regardless (this function's
    checks are an ADDITIONAL, more conservative gate on top, never a way
    around them).

    Returns a list of per-proposal decision dicts, one per candidate this
    scan looked at (never one for a proposal that isn't `validated` and
    `installed: False` -- those are simply not candidates):

        {"id", "name", "action": "approved"|"failed"|"skipped", "reason", ...}

    `log` (if given) is called once per decision -- see the module
    docstring's HONESTY note; this is a safety-sensitive automation and
    every decision, approved or skipped, is part of the audit trail."""
    _log = log or (lambda _msg: None)
    sub = _sub(agent)

    policy = get_policy(agent)
    if policy is None or not policy.get("enabled"):
        _log("auto-approve: policy absent or disabled -- no action")
        return []
    if policy.get("paused_until_restart"):
        _log("auto-approve: paused_until_restart -- no action until the daemon restarts")
        return []

    max_per_hour = int(policy.get("max_installs_per_hour", DEFAULTS["max_installs_per_hour"]))
    require_additive = bool(policy.get("require_additive", DEFAULTS["require_additive"]))
    allowed_kinds = set(policy.get("allowed_semantics_kinds") or DEFAULTS["allowed_semantics_kinds"])

    try:
        proposals = list(sub.nodes("ExtensionProposal"))
    except Exception:  # noqa: BLE001 -- type not present in this seed set yet
        proposals = []

    installs_this_hour = _count_recent_auto_installs(agent, now_ts)
    results: list[dict] = []

    for pid in proposals:
        if not sub.has_node(pid):
            continue
        pattrs = sub.node(pid)["attrs"]
        if pattrs.get("status") != "validated" or bool(pattrs.get("installed")):
            continue  # not a candidate at all -- no decision to log

        pid_val = _nid_value(pid)
        name = pattrs.get("of")

        found = pinstall._find_proposal(agent, pid)
        if found is None:
            entry = {"id": pid_val, "name": name, "action": "skipped",
                      "reason": "no linked RustExtensionSpec found"}
            results.append(entry)
            _log(f"auto-approve SKIP {name} (id={pid_val}): {entry['reason']}")
            continue
        _, _, _spec_id, spec_attrs = found

        kind = spec_attrs.get("semantics_kind")
        if kind not in allowed_kinds:
            entry = {"id": pid_val, "name": name, "action": "skipped",
                      "reason": f"semantics_kind {kind!r} not in allowed_semantics_kinds "
                                f"{sorted(allowed_kinds)}"}
            results.append(entry)
            _log(f"auto-approve SKIP {name} (id={pid_val}): {entry['reason']}")
            continue

        if require_additive:
            spec = pinstall._spec_dict_from_node(spec_attrs)
            ok, why = _is_additive(spec)
            if not ok:
                entry = {"id": pid_val, "name": name, "action": "skipped",
                          "reason": f"not additive: {why}"}
                results.append(entry)
                _log(f"auto-approve SKIP {name} (id={pid_val}): {entry['reason']}")
                continue

        if installs_this_hour >= max_per_hour:
            entry = {"id": pid_val, "name": name, "action": "skipped",
                      "reason": f"rate cap reached ({installs_this_hour}/{max_per_hour} "
                                f"auto-installs in the last hour)"}
            results.append(entry)
            _log(f"auto-approve SKIP {name} (id={pid_val}): {entry['reason']}")
            continue

        # Every scope guardrail passed -- hand off to install_proposal, which
        # re-runs ITS OWN five hard guardrails fresh, right now, regardless
        # of anything decided above.
        _log(f"auto-approve APPROVING {name} (id={pid_val}) -- policy scope checks passed")
        result = pinstall.install_proposal(agent, pid, approver="auto")
        if result.get("ok"):
            installs_this_hour += 1
            entry = {"id": pid_val, "name": name, "action": "approved",
                      "reason": result.get("reason"), "installed": True,
                      "requires_restart": bool(result.get("requires_restart"))}
            results.append(entry)
            _log(f"auto-approve INSTALLED {name} (id={pid_val}): {entry['reason']}")
            if result.get("requires_restart"):
                pid_policy = ensure_policy_node(agent)
                sub.set_attr(pid_policy, "paused_until_restart", True)
                _log("auto-approve: install requires a daemon restart -- "
                     "pausing further auto-installs until the next restart")
                break
        else:
            entry = {"id": pid_val, "name": name, "action": "failed",
                      "reason": result.get("reason"), "installed": False}
            results.append(entry)
            _log(f"auto-approve FAILED {name} (id={pid_val}): {entry['reason']}")

    return results
