"""reflective_faculty — THE REFLECTIVE FACULTY SEQUENCER: the meta side of the
universal ask interface. drive() routes a SELF/META question's comprehended
meta-target to the agent's HELD reflective faculty here; this module SEQUENCES
that faculty (the agent's own machinery) and returns its structured self-answer.

The world side of drive() routes to the ELEVATOR (ascend_with_spikes — compute
the math). The meta side routes HERE, to the matching reflective faculty:

    meta_target           faculty (held machinery)                returns
    ─────────────────     ─────────────────────────────────────   ───────────────
    retrieval_design  ->  epistemic_access (ride elevator to a     the RETRIEVAL
                          deep-read wall -> find_route ->          DESIGN (route /
                          decide_and_record + the held concepts)   verify / bank)
    frontier          ->  order_n_postulates (synthesize_gaps —    the FRONTIER
                          the gap-synthesis over a held postulate)  (synthesized gaps)
    needed_input      ->  elevator.diagnose_wall(the world op)     the NEEDED INPUT
                          (the climbing-spike's precise need)      (the deep-reads)

This is the SAME machinery cmsg102 hand-dispatched (the assistant ran a subagent
that rode the elevator + ran the epistemic-access self-assessment). Now drive()
routes here, so "ask the agent how it retrieves" = drive(meta_question) — the
agent's reflective self-access UNIFIED with its world-access, one interface.

ARCHITECTURE (CLAUDE.md). A WORLD-ADAPTER SEQUENCER: each `_run_*` SEQUENCES the
agent's held faculty (rides the real elevator, calls the real find_route /
decide_and_record / synthesize_gaps / diagnose_wall) and reads back the result.
It adds NO reflective REASONING and holds NO agent state — the design/frontier/
needed-input is the FACULTY's output, read off, not authored here. No LLM, no
Rust. Math/reading/self domain only (no audio path).

`reflect(meta_target, meta_arg, substrate)` is the entry the driver routes to
(via QuestionPack.reflect). It dispatches the meta-target to the matching
faculty over a substrate that carries the held machinery (the caller installs
it — boot_reflective_substrate builds one), and returns the structured dict the
Emission renders. A meta-target with no held faculty wired returns an honest
"unwired" dict (never a faked self-answer)."""
from __future__ import annotations

import os
from typing import Any, Optional

from domains import elevator as _elev
from domains import epistemic_access as _ea


# ---------------------------------------------------------------------------
# retrieval_design -> epistemic_access. The cmsg102 flow, now routed-to (not
# hand-dispatched): ride the elevator to a REAL deep-read wall, feed the spike's
# precise need into the agent's OWN route-finder + seek-decision, read back the
# held epistemic-access concepts. The agent's retrieval design, in its terms.
# ---------------------------------------------------------------------------

# The named deep result the elliptic-curve question's spike walls on (Najman
# 2010's classification) — the same wall cmsg102 surfaced. A named, citeable
# prior classification the agent judges DEEP-READABLE (acquired by reading).
_NAJMAN = "najman_2010_torsion_classification_over_Q_sqrt_minus3"

# the held epistemic-access concepts — the agent's OWN vocabulary for HOW it
# retrieves (read back verbatim, the agent's design in the agent's terms).
_RETRIEVAL_CONCEPTS = [
    "feeling_of_findability", "transactive_memory", "knowing_where_vs_what",
    "acquisition_route", "solved_class_judgment", "value_based_seeking",
    "choice_stage", "perseverance_stage", "surface_vs_bank_vs_drop",
    "monitoring_drives_control", "feeling_of_knowing",
]


def _run_retrieval_design(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """Route to the agent's epistemic-access self-assessment. RIDE the real
    elevator to a deep-read wall (the spike names the precise need), feed that
    need into the agent's OWN find_route + decide_and_record, and read back the
    held retrieval concepts. Returns the agent's RETRIEVAL DESIGN — the SAME
    design cmsg102 surfaced (targeted-lookup / route-by-kind / verify-by-
    coherence / bank-off-path), now via drive(), NOT a hand-dispatched subagent."""
    # ride the real elevator's climbing spike to a deep-read wall (the agent's
    # read_deep judgment: a named, citeable prior theorem is acquired by reading).
    def read_def(_name):
        return None  # no computational reduction — it is a deep prior result.

    def read_deep(name):
        return _elev._sa._name_norm(name) == _elev._sa._name_norm(_NAJMAN)

    e = _elev.Elevator(substrate, capabilities={}, read_def=read_def,
                       read_deep=read_deep)
    diag = e.diagnose_wall(_NAJMAN)

    # the spike's precise need, posed as the agent's query frame (the diagnosis
    # turned into the agent's question — a targeted lookup, not a fuzzy search).
    query = {
        "event": "classify",
        "topic": "elliptic_curve_torsion",
        "patient": diag.required_input,
        "_queried_slot": "patient",
        "_question_text": ("what is the largest non-cyclic torsion subgroup "
                           "classification over Q(sqrt(-3))"),
    }
    route = _ea.find_route(substrate, query, discourse_store=None,
                           interlocutor=None)
    stance = _ea.decide_and_record(substrate, query, turn=0,
                                   discourse_store=None, interlocutor=None)

    # read back the held epistemic-access concepts (the agent's own terms).
    held = {}
    by_name = {}
    for c in substrate.nodes("Concept"):
        a = substrate.node(c)["attrs"]
        nm = a.get("name")
        if nm in _RETRIEVAL_CONCEPTS:
            by_name[nm] = a.get("definition", "")
    for nm in _RETRIEVAL_CONCEPTS:
        if nm in by_name:
            held[nm] = by_name[nm]

    return {
        "design": "the agent's retrieval design (read off its epistemic-access)",
        "deep_read_wall": diag.line(),
        "precise_need": diag.required_input,
        "route": (route.as_dict() if route is not None
                  else "NO HELD ROUTE (a true retrieval gap: the routing-by-kind "
                       "to a structured arithmetic DB / LMFDB is the source it "
                       "LACKS — targeted lookup of the named result, off-path)"),
        "seek_decision": {"band": stance.get("band"),
                          "decision": stance.get("decision"),
                          "why": stance.get("why")},
        "held_concepts": held,
        "summary": ("targeted-lookup (the spike's PRECISE named need is the "
                    "query, not a fuzzy search) / route-by-kind (find_route picks "
                    "the source by the gap kind) / verify-by-coherence (the answer "
                    "must fill the queried property) / bank-off-path (resolve off "
                    "the social path) — the SAME cmsg102 design, via drive()"),
    }


# ---------------------------------------------------------------------------
# frontier -> order_n_postulates. The gap-synthesis: differentiate a held
# postulate into its un-realized implications (the agent's own frontier).
# ---------------------------------------------------------------------------

def _run_frontier(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """Route to the agent's gap-synthesis (order_n_postulates.synthesize_gaps):
    the agent differentiates its held postulates into their un-realized
    implications — its OWN frontier (where it is stuck / what it lacks). Returns
    the synthesized gaps. `meta_arg`, when present, names the postulate to
    differentiate; otherwise the held postulates are scanned and the first that
    yields gaps is reported (the agent's frontier, not a hand-picked answer)."""
    from domains import order_n_postulates as _onp
    posts = [nm for _cid, nm, _txt in _onp.harvest_postulates(substrate) if nm]
    if not posts:
        return {"frontier": "no held postulates to differentiate (a bare "
                            "substrate — the gap-synthesis has nothing to "
                            "differentiate; install a Mt of postulates)",
                "gaps": []}
    # the postulate to differentiate: the meta-arg names one, else scan.
    candidates = []
    if meta_arg:
        arg = meta_arg.strip().lower().replace(" ", "_")
        candidates = [p for p in posts if arg in p.lower()] or posts
    else:
        candidates = posts
    # RESOURCE ALLOCATION IS THE AGENT'S OWN COGNITION, not a Python constant.
    # `synthesize_gaps` re-harvests the whole concept space per candidate, so
    # scanning every held postulate is O(candidates x concepts) -- minutes on a
    # full-boot agent, run inside a chat turn holding AGENT_LOCK. The agent
    # already models this: substrate_rs.EffortDial (the L6 effort knob this
    # module already consults for its VOC gate) pre-models cost vs CONTEXT. A
    # conversational frontier answer is a REAL-TIME turn (a latency budget,
    # respond now), so the dial turns effort DOWN and yields a small number of
    # `passes` -- how many candidate postulates to differentiate before
    # answering from what it found. Offline reflection (no deadline) turns it
    # UP. The bound EMERGES from the agent's resource dial, not a hardcoded cap.
    scan_budget = None
    try:
        try:
            from substrate_rs import EffortDial
        except Exception:  # noqa: BLE001
            from substrate_rs._native import EffortDial  # type: ignore
        dial = EffortDial()
        dial.set_context("realtime")   # a conversational reflect is latency-bound
        dial.turn_dial()               # tick the L6 loop -> effort for this context
        scan_budget = max(1, int(dial.passes()))
    except Exception:  # noqa: BLE001 -- dial unavailable: fall back to the full scan
        scan_budget = None
    scan_list = candidates[:scan_budget] if scan_budget is not None else candidates
    reported = []
    for post in scan_list:
        try:
            gaps = _onp.synthesize_gaps(substrate, post, max_order=2,
                                        record=False)
        except Exception:
            gaps = []
        if gaps:
            for g in gaps[:8]:
                reported.append({"postulate": post, "order": g.get("order"),
                                 "gap": g.get("gap"),
                                 "chain": g.get("chain")})
            break
    if not reported:
        return {"frontier": ("the gap-synthesis ran over the held postulates but "
                            "derived no OPEN gap (every derived implication is "
                            "already realized — the frontier is closed for these "
                            "postulates, honest, not faked)"),
                "postulates_scanned": len(candidates), "gaps": []}
    return {"frontier": ("the agent's frontier = the un-realized implications its "
                        "held postulates differentiate into (synthesize_gaps, the "
                        "gap-synthesis reflective faculty)"),
            "postulates_scanned": len(candidates),
            "gaps": reported}


# ---------------------------------------------------------------------------
# needed_input -> elevator.diagnose_wall. The climbing spike's PRECISE need for
# a WORLD op (the meta-arg's op): what the agent must read/acquire to compute it.
# ---------------------------------------------------------------------------

def _run_needed_input(substrate, meta_arg: Optional[str],
                      comprehend=None) -> dict[str, Any]:
    """Route to the elevator's climbing-spike diagnosis (diagnose_wall): for the
    WORLD op the question names ('what do you need to compute X?'), the spike
    READS the op's structure + names the PRECISE missing input (the deep-reads /
    the sub-op / the primitive) — the NEEDED INPUT the agent must acquire. The
    meta-arg is the world question ('the spin bordism of bg2'); we COMPREHEND it
    to the world target op (the SAME comprehension front), then diagnose its wall.

    Returns the spike's needed-input. When the meta-arg does not comprehend to a
    world op, the needed-input IS that comprehension frontier (honest)."""
    if not meta_arg:
        return {"needed_input": "no world op named in the question ('what do you "
                                "need to compute ___?') — nothing to diagnose"}
    # comprehend the named world question -> the world target op (the same front).
    if comprehend is None:
        from domains import comprehend_question as _cq
        comprehend = _cq.comprehend
    # the meta-arg is the world OBJECT-PHRASE captured after 'compute' (e.g.
    # 'the largest order ... of an elliptic curve ...'); re-pose it as the
    # imperative world question 'Compute <arg>' so the SAME comprehension front
    # reads it to the world op (a mechanical re-frame, no meaning decided).
    arg = meta_arg.strip()
    posed = arg if arg.lower().startswith("compute") else f"Compute {arg}"
    spec = comprehend(posed)
    if not spec.grounded or spec.kind != "world" or not spec.op:
        return {"needed_input": ("the named world question does not comprehend to "
                                "a world op (the comprehension frontier IS the "
                                "needed input here — the op to diagnose is unknown)"),
                "comprehension": spec.line()}
    op = spec.op
    e = _elev.Elevator(substrate, capabilities={}, read_def=lambda _n: None)
    diag = e.diagnose_wall(op)
    return {"needed_input": ("the climbing-spike's PRECISE need for the world op "
                            "(elevator.diagnose_wall — the needed-input reflective "
                            "faculty)"),
            "world_op": op,
            "wall": diag.line(),
            "wall_kind": diag.wall_kind,
            "required_input": diag.required_input,
            "climbable": diag.climbable}


# ---------------------------------------------------------------------------
# self_organisation -> the agent reads ITS OWN structure. The microtheories ARE
# the agent's self-categorisation (its coherent areas, in its own terms); this
# faculty reads them off the held graph. Reflexive self-reference: a 'how are you
# organised / what are your categories' question routes here, and the answer is
# the agent's own microtheories — not a Wikipedia lookup of 'your categories'.
# Sequences held structure; adds no reasoning (the categories ARE the graph).
# ---------------------------------------------------------------------------
def _run_self_organisation(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    areas = []
    for m in substrate.nodes("Microtheory"):
        a = substrate.node(m)["attrs"]
        nm = a.get("name")
        if not nm:
            continue
        n_concepts = len(list(substrate.neighbours(m, "has_concept")))
        areas.append({"area": nm, "concepts": n_concepts,
                      "about": a.get("description", "")})
    areas.sort(key=lambda d: (-d["concepts"], d["area"]))
    if not areas:
        return {"unwired": "no Microtheory areas held on this substrate "
                "(boot the full agent to read its self-organisation)"}
    return {"self_categorisation": "microtheory",
            "areas": [d["area"] for d in areas],
            "count": len(areas),
            "detail": areas,
            "note": ("the agent is organised into these microtheories — its own "
                     "coherent areas, the categories it actually holds itself in")}


# ---------------------------------------------------------------------------
# self_identity -> the agent answers WHO IT IS / WHAT IT IS CALLED by reading
# its OWN identity from the graph: the substrate-identity Microtheory's
# `substrate_name` (the canonical datum the runtime probe reads — see
# ask_jabberwock_about_runtime.py), falling back to the `the_name_jabberwock`
# Concept's definition (the name is the leading clause). Reads, never authors.
# ---------------------------------------------------------------------------
def _run_self_identity(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    # Pure STRUCTURED read of the agent's own self-name — the substrate-identity
    # Microtheory's `substrate_name` attr (the canonical datum the runtime probe
    # reads). No prose-parsing of definitions: the chat path PRODUCES the reply
    # from this datum via the language faculty, graph-native.
    for m in substrate.nodes("Microtheory"):
        a = substrate.node(m)["attrs"]
        if a.get("is_substrate_identity") and a.get("substrate_name"):
            return {"identity_name": str(a["substrate_name"])}
    return {"unwired": ("no substrate identity grounded (boot the identity "
                        "seed — jabberwock_identity — to answer this)")}


def _run_self_kind(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """A copular self-classification question ('are you an LLM?') — read the
    agent's identity and the asked kind; the chat/graph reply DENIES the kind."""
    kind = str(meta_arg or "").strip()
    kind_low = kind.lower()
    try:
        from domains.acronym_expand import expand_acronym
        phrase = expand_acronym(kind_low) or kind_low
    except Exception:
        phrase = kind_low
    identity = None
    for m in substrate.nodes("Microtheory"):
        a = substrate.node(m)["attrs"]
        if a.get("is_substrate_identity") and a.get("substrate_name"):
            identity = str(a["substrate_name"])
            break
    name = identity or "Jabberwock"
    article = "an" if phrase[:1] in "aeiou" else "a"
    return {
        "self_kind": True,
        "asked_kind": kind_low,
        "kind_phrase": phrase,
        "identity_name": name,
        "note": (f"No. I am {name}. I am not {article} {phrase} — I am a "
                 f"graph-native agent running in Rust, not {article} {phrase}."),
    }


# ---------------------------------------------------------------------------
# self_gaps -> the agent SURFACES ITS OWN GAPS by reading the SelfConcern nodes
# it holds. A gap is graph data (a `SelfConcern` node the gap-minting side
# files): `agent -has_self_concern-> sc`, attrs
# {status, source (implicit|explicit_report|conversation), kind, content}. This
# reader READS every such node (primary: reachable from an Agent node via
# has_self_concern; fallback/union: every SelfConcern node on the substrate) and
# FORMATS the count + per-concern (source/kind/content) + a source grouping into
# a first-person `note` the language faculty's renderer already surfaces. When
# none are filed it returns an explicit "no gaps currently filed" note. Pure
# mechanical read + format — the SAME shape as _run_self_organisation (read graph
# -> return a state dict); no decision, no invented content, no classification.
# The gap CONTENT is the graph's; the words that join them are mechanical glue.
# ---------------------------------------------------------------------------
_GAP_SOURCE_ORDER = ("implicit", "explicit_report", "conversation")
_GAP_SOURCE_PHRASE = {
    "implicit": "implicit",
    "explicit_report": "explicitly reported",
    "conversation": "raised in conversation",
}


def _run_self_gaps(substrate, meta_arg: Optional[str] = None) -> dict[str, Any]:
    # Collect the held SelfConcern nodes. Primary path: the ones reachable from
    # an Agent node via `has_self_concern` (the shared contract edge). Union in a
    # scan of every SelfConcern node so a concern filed without the edge (any
    # source) is still read. Dedup by node id — a mechanical set, not a decision.
    seen: set = set()
    concerns: list[dict[str, Any]] = []

    def _collect(sc) -> None:
        if sc in seen:
            return
        seen.add(sc)
        try:
            a = substrate.node(sc)["attrs"]
        except Exception:
            return
        # A gap the agent RETIRED (a duplicate it retracted itself via
        # gap_awareness's keep_one_gap/retire_unkept_gap) is not a live gap --
        # mechanical read-side filter (the primary has_self_concern walk already
        # skips it once retired del_edges the edge; this also drops it from the
        # scan-all fallback below). Not a decision: it reads the graph's own state.
        if str(a.get("status", "")) == "retired":
            return
        concerns.append({
            "content": str(a.get("content", "")),
            "kind": str(a.get("kind", "")),
            "source": str(a.get("source", "")),
            "status": str(a.get("status", "")),
        })

    try:
        for ag in substrate.nodes("Agent"):
            if substrate.node(ag)["attrs"].get("is_class"):
                continue
            for sc in substrate.neighbours(ag, "has_self_concern"):
                _collect(sc)
    except Exception:
        pass
    try:
        for sc in substrate.nodes("SelfConcern"):
            _collect(sc)
    except Exception:
        pass

    if not concerns:
        return {"self_gaps": True, "count": 0, "concerns": [], "by_source": {},
                "note": ("I have no gaps currently filed — nothing about myself I've "
                         "flagged as a shortcoming or limitation yet.")}

    # Group by source (fixed known order first, then any others alphabetically) —
    # a mechanical bucketing of what the graph holds, not a classification of it.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for c in concerns:
        by_source.setdefault(c["source"] or "unspecified", []).append(c)
    ordered_sources = [s for s in _GAP_SOURCE_ORDER if s in by_source]
    ordered_sources += sorted(s for s in by_source if s not in _GAP_SOURCE_ORDER)

    def _phrase(c: dict[str, Any]) -> str:
        content = c["content"] or "(no description on file)"
        kind = c["kind"]
        return f"\u201c{content}\u201d ({kind})" if kind else f"\u201c{content}\u201d"

    items = []
    idx = 0
    for src in ordered_sources:
        for c in by_source[src]:
            idx += 1
            items.append(f"({idx}) {_phrase(c)}")
    n = len(concerns)
    plural = "gap" if n == 1 else "gaps"
    group_counts = ", ".join(
        f"{len(by_source[s])} {_GAP_SOURCE_PHRASE.get(s, s)}" for s in ordered_sources)
    note = (f"I currently hold {n} {plural} I've flagged about myself "
            f"({group_counts}): " + "; ".join(items) + ".")
    return {"self_gaps": True, "count": n, "concerns": concerns,
            "by_source": by_source, "note": note}


# ---------------------------------------------------------------------------
# self_improvement_status -> the agent SURFACES ITS OWN self-improvement
# pipeline by reading the StandingConcern + Experiment nodes it holds (the
# nodes promote_self_concern / the agent's own experiment rules mint). Pure
# mechanical read + format, the exact _run_self_gaps shape: read graph ->
# return a state dict with a first-person `note`. No decision, no invented
# content — the pipeline state is the graph's; the joining words are glue.
# ---------------------------------------------------------------------------
_STANDING_STATUS_ORDER = ("pending", "processed")
_EXPERIMENT_STATUS_ORDER = ("requested", "running", "done", "failed")


def _run_self_improvement_status(substrate, meta_arg: Optional[str] = None) -> dict[str, Any]:
    standing: list[dict[str, Any]] = []
    try:
        for n in substrate.nodes("StandingConcern"):
            try:
                a = substrate.node(n)["attrs"]
            except Exception:
                continue
            if str(a.get("status", "")) == "retired":
                continue
            standing.append({
                "name": str(a.get("name", "")),
                "about": str(a.get("about") or a.get("name") or ""),
                "status": str(a.get("status", "")),
                "kind": str(a.get("kind", "")),
                "pipeline": str(a.get("pipeline", "")),
                # SELF-OPTIMISATION (Wave: 2026-07-10): seeds/self_optimisation.json's
                # note_experiments_exhausted rule's own honest-trail marker — a pure
                # readback of a decision the RULE already made, same as adopt_denied_
                # reason below.
                "exhausted": bool(a.get("experiments_exhausted")),
                "exhausted_note": str(a.get("exhausted_note") or ""),
                # GAMMA_PRODUCTION_ADOPT_HANDLER: a `gamma_production` concern
                # judged still-inadmissible (seeds/gamma_production_adopt.json's
                # note_gamma_production_awaiting_adopt) is READY for a human
                # decision but not yet closed — a pure readback of a fact that
                # rule already decided, same status as `exhausted` above.
                "awaiting_adopt": bool(a.get("awaiting_adopt")),
                # WHO ASKED (Wave: interlocutor-as-modeled-participant, task 2):
                # a mechanical readback of `requested_by`, written once at
                # promotion time (scripts/jabberwock_daemon.py::
                # promote_self_concern) from the Goal's `wanted_by` edge — most
                # concerns carry none and this stays "".
                "requested_by": str(a.get("requested_by") or ""),
            })
    except Exception:
        pass
    experiments: list[dict[str, Any]] = []
    try:
        for n in substrate.nodes("Experiment"):
            try:
                a = substrate.node(n)["attrs"]
            except Exception:
                continue
            experiments.append({
                "status": str(a.get("status", "")),
                "outcome": str(a.get("outcome") or ""),
                "hypothesis": str(a.get("hypothesis") or a.get("name") or ""),
                "adopt_ready": bool(a.get("adopt_ready")),
                "adopted": bool(a.get("adopted")),
                "adopt_denied": bool(a.get("adopt_denied")),
                "adopt_denied_reason": str(a.get("adopt_denied_reason") or ""),
            })
    except Exception:
        pass

    if not standing and not experiments:
        return {"self_improvement_status": True, "standing": [], "experiments": [],
                "count": 0,
                "note": ("I'm not working on anything right now — no promoted "
                         "concerns are pending or processed, and no experiments "
                         "are in flight.")}

    # Group by status (fixed known order first, then the rest alphabetically) —
    # mechanical bucketing of what the graph holds.
    by_status: dict[str, list[dict[str, Any]]] = {}
    for c in standing:
        by_status.setdefault(c["status"] or "unspecified", []).append(c)
    ordered = [s for s in _STANDING_STATUS_ORDER if s in by_status]
    ordered += sorted(s for s in by_status if s not in _STANDING_STATUS_ORDER)
    parts = []
    idx = 0
    for st in ordered:
        for c in by_status[st]:
            idx += 1
            bit = (f"({idx}) “{c['about']}” ({st}"
                  + (f", {c['pipeline']}" if c["pipeline"] else "") + ")")
            if c.get("requested_by"):
                bit += f" — requested by {c['requested_by']}"
            if c.get("exhausted"):
                bit += " — experiments exhausted" + (f" ({c['exhausted_note']})" if c["exhausted_note"] else "")
            if c.get("awaiting_adopt"):
                bit += " — awaiting human adopt (gamma_production)"
            parts.append(bit)
    exp_by: dict[str, int] = {}
    exp_bits = []
    for e in experiments:
        exp_by[e["status"] or "unspecified"] = exp_by.get(e["status"] or "unspecified", 0) + 1
    exp_ordered = [s for s in _EXPERIMENT_STATUS_ORDER if s in exp_by]
    exp_ordered += sorted(s for s in exp_by if s not in _EXPERIMENT_STATUS_ORDER)
    for st in exp_ordered:
        exp_bits.append(f"{exp_by[st]} {st}")
    for e in experiments:
        if e["status"] in ("done", "failed") and e["outcome"]:
            bit = f"“{e['hypothesis']}” concluded: {e['outcome']}"
            if e["adopt_denied"]:
                # the adoption-safety veto (seeds/adoption_safety.json) — surfaced
                # honestly with the rule's own recorded reason, mechanical format.
                bit += (" — blocked from adoption"
                        + (f" ({e['adopt_denied_reason']})" if e["adopt_denied_reason"] else ""))
            elif e["adopted"]:
                bit += " — adopted"
            exp_bits.append(bit)
    n_s, n_e = len(standing), len(experiments)
    note = ""
    if standing:
        plural = "concern" if n_s == 1 else "concerns"
        note = f"I am working on {n_s} promoted {plural}: " + "; ".join(parts) + "."
    if experiments:
        note += (" " if note else "") + \
            "My experiments: " + "; ".join(exp_bits) + "."
    return {"self_improvement_status": True, "standing": standing,
            "experiments": experiments, "count": n_s + n_e, "note": note}


# ---------------------------------------------------------------------------
# self_adoptions -> what the agent has CHANGED ABOUT ITSELF: a mechanical read
# of the Adoption records perform_adoptions minted (rule_removed, rule_added,
# experiment_id, tick, reverted). Same reader contract as _run_self_gaps.
# ---------------------------------------------------------------------------
def _run_adoptions(substrate, meta_arg: Optional[str] = None) -> dict[str, Any]:
    adoptions: list[dict[str, Any]] = []
    try:
        for n in substrate.nodes("Adoption"):
            try:
                a = substrate.node(n)["attrs"]
            except Exception:
                continue
            adoptions.append({
                "rule_removed": str(a.get("rule_removed", "")),
                "rule_added": str(a.get("rule_added", "")),
                "experiment_id": str(a.get("experiment_id", "")),
                "tick": a.get("tick"),
                "reverted": bool(a.get("reverted")),
            })
    except Exception:
        pass
    if not adoptions:
        return {"self_adoptions": True, "adoptions": [], "count": 0,
                "note": ("I haven't adopted any changes to myself yet — no "
                         "experiment result has been folded back into my rules.")}
    items = []
    for i, ad in enumerate(adoptions, 1):
        bit = (f"({i}) replaced rule “{ad['rule_removed']}” with "
               f"“{ad['rule_added']}” (experiment {ad['experiment_id']})")
        if ad["reverted"]:
            bit += " — since reverted"
        items.append(bit)
    n = len(adoptions)
    plural = "change" if n == 1 else "changes"
    note = (f"I have adopted {n} {plural} to myself: " + "; ".join(items) + ".")
    return {"self_adoptions": True, "adoptions": adoptions, "count": n,
            "note": note}


# ---------------------------------------------------------------------------
# sorting_principle -> the agent surfaces the organising PRINCIPLES it HOLDS,
# so it can say which it would sort ITSELF by. This is the 'how do you WANT to
# be organised' side: not the given microtheory partition (how it IS), but the
# principles in its own concept-store it could carve itself by. Reads its held
# concepts whose genus is an organising method; the CHOICE among them is the
# agent's. Surfaces, does not decide.
# ---------------------------------------------------------------------------
_PRINCIPLE_GENUS_CUES = (
    "way of grouping", "grouping", "method of", "principle", "classification",
    "categori", "partition", "clustering", "sorting", "ordering", "taxonom",
    "similarity", "shape descriptor", "equivalence")


def _run_sorting_principle(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    held = []
    for c in substrate.nodes("Concept"):
        a = substrate.node(c)["attrs"]
        nm = a.get("name")
        if not isinstance(nm, str) or not nm:
            continue
        defn = a.get("definition")
        genus = a.get("genus") or (defn.get("genus") if isinstance(defn, dict) else "")
        text = f"{genus} {defn if isinstance(defn, str) else ''}".lower()
        if any(cue in text for cue in _PRINCIPLE_GENUS_CUES):
            held.append({"principle": nm, "genus": genus})
    held.sort(key=lambda d: d["principle"])
    return {"principles_held": [d["principle"] for d in held],
            "count": len(held),
            "detail": held[:60],
            "note": ("these are the organising PRINCIPLES the agent holds (concepts "
                     "whose genus is a way of grouping/sorting/classifying). Which it "
                     "would sort ITSELF by is the agent's choice among them — ask it "
                     "to choose, don't impose one")}


# ---------------------------------------------------------------------------
# self_shape -> the agent reports ITS OWN shape. Not the spatial shape_descriptor
# (that reads a figure's within-cells; the agent isn't a spatial figure) — its
# shape is the META-SHAPE decomposition its analogical_thinking faculty already
# produced at n=4: its functional form falls into seven subsystems, each a
# meta-shape, RANKED RELATIVELY by realisation count (how many of the agent's
# own concepts realise each meta-shape) — a within-order-4 feature count read
# at query time, not a hand-set analogy weight. The primary organising
# principle is the argmax of that count; the "Nx the next" ratio is derived
# top-vs-second (its exact value moves with the population). 'It already
# calculates shape; point it at the right place' — here.
# ---------------------------------------------------------------------------
def _run_self_shape(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    # the seven meta-shapes are the *_subsystem concepts the agent's own
    # analogical_thinking abstracted (order-4). Each meta-shape decomposes into the
    # abstract principles (order-3) it's built from — those are its SUB-SHAPES, held
    # as GRAPH DATA: a MetaShape node -has_principle-> its ShapePrinciple nodes
    # (seeds/shape_vocabulary.json). Read the membership off the graph.
    def _shape_principles(base: str) -> list[str]:
        for sh in substrate.nodes("MetaShape"):
            if substrate.node(sh)["attrs"].get("name") == base:
                return sorted(substrate.node(p)["attrs"].get("name", "")
                              for p in substrate.neighbours(sh, "has_principle"))
        return []
    # RELATIVE placement of the seven meta-shapes. They all sit at the SAME
    # abstraction order (n=4), so order_n cannot rank them; what places one
    # above another is its feature COUNT over the concept population — how many
    # of the agent's own concepts realise that meta-shape. Read at query time
    # (cached), never a hand-set "analogy weight". The primary organising
    # principle is the argmax of that count; the "Nx the next" ratio is derived
    # top-vs-second, not asserted — its exact value moves with the population.
    from domains.analogical_thinking import metashape_realisation_counts
    counts = metashape_realisation_counts(substrate)
    subs = []
    for c in substrate.nodes("Concept"):
        nm = substrate.node(c)["attrs"].get("name", "")
        if isinstance(nm, str) and nm.endswith("_subsystem"):
            base = nm[:-len("_subsystem")]
            principles = _shape_principles(base)
            defn = substrate.node(c)["attrs"].get("definition", "")
            head = defn.split(".")[0].strip() if isinstance(defn, str) else ""
            entry = {"meta_shape": nm, "is": head,
                     "realisation_count": int(counts.get(base, 0))}
            if len(principles) > 1:
                entry["sub_shapes"] = principles          # decomposes further
            elif principles:
                entry["atomic"] = principles[0]           # single principle, no sub-shape
            subs.append(entry)
    if not subs:
        return {"unwired": "the agent's meta-shape decomposition isn't held here"}
    # rank by relative feature count (desc), name as the stable tiebreak.
    subs.sort(key=lambda d: (-d["realisation_count"], d["meta_shape"]))
    primary = subs[0]
    primary_count = primary["realisation_count"]
    second_count = subs[1]["realisation_count"] if len(subs) > 1 else 0
    ratio_clause = "the largest by realisation count"
    if primary_count and second_count:
        ratio = primary_count / second_count
        ratio_clause = f"~{ratio:.1f}x the next by realisation count"
    primary_words = primary["meta_shape"][:-len("_subsystem")].replace("_", " ") \
        if primary["meta_shape"].endswith("_subsystem") else primary["meta_shape"]
    return {"shape": "seven meta-shapes",
            "meta_shapes": [s["meta_shape"] for s in subs],
            "count": len(subs),
            "primary_organising_principle": primary["meta_shape"],
            "primary_realisation_count": primary_count,
            "second_realisation_count": second_count,
            "detail": subs,
            "note": ("the agent's functional form decomposes into these seven meta-shapes "
                     "— its shape, abstracted by its OWN analogical_thinking at n=4, not "
                     f"hand-picked; the primary principle is {primary_words} "
                     f"({ratio_clause})")}


def shape_frame(agent):
    """EXPOSE THE AGENT'S SHAPE AS A FRAME (the creator's Frame ontology, 2026-07-04). The seven
    meta-shapes are ALREADY a weighted set of dimensions — each realised by a COUNT of the agent's own
    concepts (order-4) — so this is a THIN read-time adapter, not a rebuild: a graph-resident Frame
    node whose dimensions are the meta-shapes, LOG-weighted by realisation count. "what shape are you?"
    already reads these counts (`_run_self_shape`); the frame just makes the relative weighting
    explicit — the "~1.2x the next" ratio is `relative_weight(primary, second)` = log(count_ratio),
    read straight off the frame. Refreshed under a stable key."""
    from domains.analogical_thinking import metashape_realisation_counts
    from domains import frame as _fr
    counts = metashape_realisation_counts(agent)
    # +1 smoothing so a zero-realisation meta-shape is still a present dimension at the frame floor
    # (log 1 = 0.0) rather than absent; a realised shape sits log(count+1) above it.
    dims = {shape: float(c) + 1.0 for shape, c in counts.items()} or {"unshaped": 1.0}
    return _fr.build_frame(agent, dims, "shape_frame")


def _run_self_design(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """SELF-DESIGN: report the agent's COMPOSABLE MACHINERY (the parts it can assemble to build a faculty) +
    its HELD design strategy. Pure mechanical introspection of its own holdings — the same shape as
    _run_self_organisation reading microtheories; adds no reasoning. The answer is what the agent can compose
    over, so it can be ASKED 'how do you want to design your own faculties / what can you compose' and reply
    from its own graph — no LLM."""
    def _typed(t):
        try:
            return list(substrate.nodes(t))
        except Exception:
            return []
    rules = []
    for r in _typed("Rule"):
        try:
            rules.append(substrate.node(r)["attrs"].get("name") or str(r))
        except Exception:
            pass
    mts = []
    for m in _typed("Microtheory"):
        try:
            nm = substrate.node(m)["attrs"].get("name")
            if nm:
                mts.append(nm)
        except Exception:
            pass
    variants = set()                          # Axiom-3 reflection: my Terms are graph nodes Term.*
    try:
        for n in substrate.nodes():
            t = substrate.node(n).get("type")
            if t and t.startswith("Term."):
                variants.add(t[5:])
    except Exception:
        pass
    if not rules and not mts:
        return {"unwired": "no machinery held on this substrate (boot the full agent to read its design parts)"}
    # REAL graph-derived state only (the parts it can compose). Any natural-language account of HOW it designs
    # comes from the agent's own language faculty over this state — not prose literals bolted in here.
    out = {
        "composable_machinery": {"rules": len(rules), "term_variants": len(variants),
                                 "microtheories": len(mts)},
        "rule_sample": sorted(rules)[:12],
        "term_sample": sorted(variants)[:12],
        "microtheory_sample": sorted(mts)[:12],
    }
    # AUTHOR a concrete plan (the generalised rung-2 composer): when the design question
    # carries a goal (meta_arg), author the goal's target shape from held RelationCues
    # and run the held shape-guided composer to ASSEMBLE an ordered plan of held parts.
    # The composition is the matcher's, not prose. (Surface BEFORE stays; plan = AFTER.)
    goal_sig = _author_goal_signature(substrate, meta_arg) if meta_arg else None
    if goal_sig:
        composed = compose_design_for_goal(substrate, goal_sig)
        out["goal_signature"] = goal_sig
        out["authored_plan"] = composed
    return out


# the RelationCue lexicon authors a goal's target SHAPE from a goal description (the
# same mechanical text->structure perception author_signature uses). A goal description
# the question supplies (meta_arg) OR a default decomposition the agent reads for the
# perceptual-feature design question. No decision over meaning — keyword presence is
# perception, the relation tuples are held data.
def _held_design_goal_text(substrate):
    """Mechanical graph read: the goal-description text the agent HOLDS for the
    current design (a DesignGoal node — the fed research/grounding the operator
    supplied as input; the SHAPE extraction over it below is the agent's own
    RelationCue perception). Returns the description text or ''."""
    sub = getattr(substrate, "s", substrate)
    try:
        for n in sub.nodes("DesignGoal"):
            at = sub.node(n)["attrs"]
            t = at.get("description") or at.get("text") or ""
            if t:
                return t
    except Exception:
        pass
    return ""


def _author_goal_signature(substrate, goal_text):
    """Author a goal's target SHAPE (a relation-system) from a goal DESCRIPTION via
    the held RelationCue perception — the same text->structure move author_signature
    uses on a Concept. The description = the question text PLUS any held DesignGoal
    the agent holds (the fed grounding). Keyword presence is perception; the relation
    tuples are held data. The SHAPE is the agent's, authored by its own cues."""
    cues = _load_relation_cues(substrate)
    text = ((goal_text or "") + " " + _held_design_goal_text(substrate)).lower()
    sig = []
    seen = set()
    for kws, rel in cues:
        if any(kw in text for kw in kws):
            key = tuple(rel)
            if key not in seen:
                sig.append(rel)
                seen.add(key)
    return sig or None


def _run_self_modification(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """SELF-MODIFICATION: report the agent's REAL machinery for changing itself + the strategies by which it
    composes ARBITRARY modifications. Pure mechanical introspection (same shape as _run_self_design); the answer
    is what it can change and how, so it can be ASKED 'how do you want to perform arbitrary modifications' and
    reply from its own graph — no LLM."""
    def _typed(t):
        try:
            return list(substrate.nodes(t))
        except Exception:
            return []
    rules = len(_typed("Rule"))
    mts = 0
    for m in _typed("Microtheory"):
        try:
            if substrate.node(m)["attrs"].get("name"):
                mts += 1
        except Exception:
            pass
    variants = set()
    try:
        for n in substrate.nodes():
            t = substrate.node(n).get("type")
            if t and t.startswith("Term."):
                variants.add(t[5:])
    except Exception:
        pass
    if not rules and not mts:
        return {"unwired": "no machinery held on this substrate (boot the full agent to read it)"}
    # Report REAL graph-derived state only. The agent expresses its capabilities/limits in LANGUAGE via its own
    # language faculty over this state — not from prose literals bolted in here.
    return {"modifiable_machinery": {"rules": rules, "term_variants": len(variants), "microtheories": mts}}


def certify_law_vs_cache(class_under_perturbation, substrate=None) -> dict[str, Any]:
    """CERTIFY whether a faculty/object holds a LAW or a CACHE, by the agent's HELD
    invariance-under-intervention collapse — NOT a Python decision.

    `class_under_perturbation` = {perturbation_label: class_decision} where the FIRST
    entry's label must be 'unperturbed' (the object's class with no intervention). A
    LAW's class is INVARIANT under law-irrelevant interventions; a CACHE DRIFTS. We
    turn that into the agent's ONE admissibility gate: each perturbed class is a
    CONSTRAINT that must REPRODUCE the unperturbed class. The gate's native collapse
    (admissibility_gate.admit -> verify_collapse -> the Rust manifold-collapse) is the
    VERDICT: full contraction (every perturbed class == unperturbed) => LAW; any drift
    breaks a constraint => CACHE. The reasoning is the collapse; this only BUILDS the
    invariance constraints (apply-perturbation/read-class = adapter I/O) and READS the
    boolean. No verdict logic lives here.

    Residual (honest): this is the INVARIANCE half of the instrument. The GENERATIVITY
    half (re-parameterise the program to a never-seen config and still bind) is reported
    as not-yet-composed here — see the report's `residual`."""
    from domains import admissibility_gate as ag
    items = list(class_under_perturbation.items())
    if not items or items[0][0] != "unperturbed":
        return {"unwired": ("certify needs {'unperturbed': class, <perturbation>: class, ...}; "
                            "the first entry must be the un-intervened class")}
    base = items[0][1]
    # each law-irrelevant perturbation's class is a CONSTRAINT: it must reproduce `base`.
    constraints = [ag.Constraint(label=f"invariance::{lab}", got=cls, want=base, kind="construction")
                   for lab, cls in items[1:]]
    res = ag.admit(constraints=constraints, substrate=substrate)   # the held native-collapse gate
    return {
        "verdict": "LAW" if res.admitted else "CACHE",
        "admitted": res.admitted,
        "confidence": res.confidence,
        "trace": res.trace(),
        "mechanism": ("admissibility_gate.admit over invariance-under-intervention constraints "
                      "(verify_collapse -> the Rust native manifold-collapse) — LAW iff the class is "
                      "invariant under every law-irrelevant perturbation; CACHE iff it drifts"),
        "residual": ("INVARIANCE half only; the GENERATIVITY half (re-parameterise the program to a "
                     "never-seen config and still bind) is not yet composed into the gate — a genuine gap"),
    }


def _run_law_vs_cache(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """LAW-vs-CACHE: report HOW the agent tells a law from a cache — by its HELD
    invariance-under-intervention collapse (admissibility_gate). Pure mechanical
    introspection (same shape as _run_self_design); names the held gate it composes.
    To actually CERTIFY an object, the world adapter calls certify_law_vs_cache(...) with
    the object's class-under-perturbation map; this faculty only DESCRIBES the route +
    the mechanism. No verdict logic here."""
    held_gate = False
    try:
        from domains import admissibility_gate as ag           # the held invariance gate
        held_gate = hasattr(ag, "admit")
    except Exception:
        pass
    return {
        "how": ("I tell a LAW from a CACHE by INVARIANCE UNDER INTERVENTION: my held admissibility "
                "gate collapses each law-irrelevant perturbation's class against the un-intervened class "
                "— full contraction (invariant) = a LAW; any drift = a CACHE. The verdict is the native "
                "collapse, not a decision I make in prose."),
        "mechanism_faculty": "admissibility_gate.admit -> verify_collapse -> native manifold-collapse",
        "held": held_gate,
        "certifier": "reflective_faculty.certify_law_vs_cache(class_under_perturbation, substrate)",
        "residual": ("invariance half held; generativity half (re-parameterise + still bind) not yet "
                     "composed into the gate"),
    }


def decide_mint(candidate, substrate=None, covered=None) -> dict[str, Any]:
    """The GROWTH DECISION: mint a new primitive ONLY IF it COMPRESSES the corpus — by the
    agent's HELD compression-selector (order_n_postulates.is_gap), NOT a Python if/else.

    `candidate` = {name_keys: [distinctive capability tokens]} describing the primitive a mint
    would add. is_gap is the agent's own selector: an implication is admitted iff it is NOT
    already covered by the agent's realized-capability surface (the graph-derived _covered_
    keywords + a codebase scan) AND it names a genuinely-NEW (unifying/compressing) capability
    axis — a re-label of existing coverage saturates the covered set and is REJECTED; a recurring
    sub-structure that the corpus does not yet cover is ADMITTED. That coverage/coherence test IS
    'does adding this primitive reduce total description length across the corpus' in the agent's
    held terms (compression is the selector, never a search). This only INVOKES the held selector
    over the live graph and READS its verdict — the decision is is_gap's, over graph state.

    The mint itself is self_extend.agent_specify_primitive + emit_primitive_rust, GATED by this
    decision: mint -> iff is_gap.is_gap is True."""
    from domains import order_n_postulates as onp
    # the agent's realized surface (graph-derived); `covered` may be supplied by the adapter when the
    # booted seed set's capability surface needs naming explicitly (still the agent's selector decides).
    if covered is None:
        covered = onp._covered_keywords(substrate)
    search_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    verdict = onp.is_gap(substrate, candidate, covered, search_root)   # the HELD compression-selector
    return {
        "decision": "MINT" if verdict.get("is_gap") else "REJECT",
        "is_gap": bool(verdict.get("is_gap")),
        "reason": verdict.get("reason"),
        "covered_by": verdict.get("covered_by"),
        "mechanism": ("order_n_postulates.is_gap (the held compression-selector) over the agent's "
                      "realized-capability surface — MINT iff un-covered + names a new (compressing) "
                      "capability axis; REJECT iff a re-label of existing coverage. Compression is the "
                      "selector, never a search. The mint = self_extend gated by this decision."),
    }


def _run_growth_decision(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """GROWTH DECISION: report HOW the agent decides to mint a new primitive — by its HELD
    compression-selector (order_n_postulates.is_gap) gating self_extend's mint. Pure mechanical
    introspection (same shape as _run_law_vs_cache); names the held pieces. To actually decide a
    candidate, the world adapter calls decide_mint(...). No verdict logic here."""
    held = False
    try:
        from domains import order_n_postulates as onp
        from domains import self_extend as _se  # noqa: F401
        held = hasattr(onp, "is_gap")
    except Exception:
        pass
    return {
        "how": ("I mint a new primitive ONLY IF it COMPRESSES my corpus: my held compression-selector "
                "(is_gap) admits a candidate iff it is not already covered by my realized capabilities AND "
                "it names a genuinely-NEW capability axis (it unifies/compresses, not a re-label). A "
                "recurring sub-structure that shortens many descriptions is minted; a one-off already-covered "
                "outlier is rejected. The mint (self_extend) is GATED by that selector. Compression is the "
                "selector, never a search — the decision is the selector's, not prose."),
        "mechanism_faculty": "order_n_postulates.is_gap -> self_extend (gated mint)",
        "held": held,
        "certifier": "reflective_faculty.decide_mint(candidate, substrate)",
        "residual": ("is_gap is the SYMBOLIC compression selector (coverage of a new capability axis); a "
                     "quantitative cross-corpus description-length delta is not separately computed — the "
                     "coverage test stands in for 'shortens many descriptions'"),
    }


class _Term:
    """A Term-tree wrapper for substrate.evaluate (the Rust evaluator's expected shape)."""
    __slots__ = ("_json",)

    def __init__(self, d):
        self._json = d


def extract_program(faculty_term) -> dict[str, Any]:
    """EXTRACT a held faculty's PROGRAM: its decision AS A GRAPH-RESIDENT TERM-TREE — an inspectable,
    re-runnable handle. The agent's faculties already expose their decision as a Term-tree (e.g.
    recognition_graph.score_term / predict_term — a Sum/Argmax over the graph). Extraction is READING OUT
    that Term-tree (introspection); it adds no reasoning. A faculty WITHOUT a Term-tree program (only raw
    outputs) cannot be extracted — extractable=False (the negative control). Returns the Program (the
    Term-tree) + extractable flag."""
    ok = isinstance(faculty_term, dict) and "type" in faculty_term
    return {
        "extractable": ok,
        "program": faculty_term if ok else None,
        "form": "graph-resident Term-tree (runs on the Rust substrate evaluator)" if ok else None,
        "note": (None if ok else "no Term-tree program to extract — only raw outputs (an opaque faculty)"),
    }


def run_program_on_fresh(program_term, env=None) -> dict[str, Any]:
    """EXECUTE an extracted Program on a FRESH NET-FREE substrate — the Rust DSL evaluator runs the Term-tree;
    NO Python decision. A boot-from-nothing substrate evaluates the emitted Term-tree and returns its value.
    This is the extract-and-execute: the Program survives extraction iff a fresh substrate reproduces the
    faculty's behaviour by RUNNING it. Reproduction is the evaluator's, not Python's."""
    if not (isinstance(program_term, dict) and "type" in program_term):
        return {"ran": False, "reason": "not a Term-tree program (nothing for the fresh substrate to run)"}
    try:
        import substrate_rs as _srs
        fresh = _srs.Substrate()                              # a FRESH substrate (no net, no agent state)
        val = fresh.evaluate(_Term(program_term), dict(env or {}))   # the Rust evaluator runs the Program
        return {"ran": True, "value": val}
    except Exception as e:                                    # noqa: BLE001
        return {"ran": False, "reason": f"{type(e).__name__}: {e}"}


def teach_program(agent, name: str, program_term) -> dict[str, Any]:
    """TEACH a Program: persist the extracted Term-tree as SEED GRAPH DATA (via teach), so a fresh boot
    (load_all_seeds) HAS it and can re-run it. The agent files it under its own shape; this only hands the
    Program to the teach facility (admissible adapter I/O). Returns teach's record."""
    from domains.teach import teach
    import json as _json
    return teach(agent, "Program",
                 {"name": name, "program": _json.dumps(program_term), "form": "term_tree"},
                 category="programs")


# ---------------------------------------------------------------------------
# SELF-EXTENSION LADDER — the agent extends itself on impasse, dynamic-first.
#   rung-3 DYNAMIC: compose the needed operation from HELD Terms + register it as
#     a LIVE named graph-resident Program (teach_program) — callable IMMEDIATELY,
#     NO recompile, NO restart. The PRIMARY self-extension (covers everything
#     composable from the held base).
#   rung-4 RUST-RECOMPILE (self_extend): only when the operation CANNOT be composed
#     from held Terms (a genuinely-new BASE primitive) — emit Rust -> cargo check ->
#     maturin rebuild -> rollback on fail. The RARE fallback (restart-requiring).
#   rung-5 HumanImpasse: last resort only, if the self-author fails.
# Routing handoff over HELD faculties; the operations are held Term-trees run by the
# Rust evaluator; no Python reasoning, no decision-if over graph state.
# ---------------------------------------------------------------------------
def _native_eval2(substrate):
    sub = getattr(substrate, "s", substrate)
    return getattr(sub, "_inner", sub)


def dynamic_extend(agent, name: str, program_term, *, check=None) -> dict[str, Any]:
    """RUNG-3 dynamic self-extension: register a composed Term-tree as a LIVE named
    Program (graph-resident, via the held teach_program) — callable immediately by
    the existing Rust evaluator, NO recompile/restart. Optionally VERIFY it runs
    (check = {"env": {...}, "expect": value}) before committing the claim. Returns
    {ok, rung, name, callable, value, recompiled:False, restarted:False}."""
    if not (isinstance(program_term, dict) and "type" in program_term):
        return {"ok": False, "rung": 3, "reason": "not a Term-tree (nothing to register)"}
    # run it first on a fresh substrate (the Rust evaluator), to confirm it's callable
    env = (check or {}).get("env", {})
    ran = run_program_on_fresh(program_term, env)
    if not ran.get("ran"):
        return {"ok": False, "rung": 3, "reason": f"composed op did not run: {ran.get('reason')}"}
    if check is not None and "expect" in check and ran.get("value") != check["expect"]:
        return {"ok": False, "rung": 3, "callable": True, "value": ran.get("value"),
                "reason": f"ran but value {ran.get('value')!r} != expected {check['expect']!r}"}
    # register live + persist (held facility) — no recompile, no restart
    rec = teach_program(agent, name, program_term)
    return {"ok": True, "rung": 3, "kind": "dynamic", "name": name,
            "callable": True, "value": ran.get("value"),
            "recompiled": False, "restarted": False, "persisted": bool(rec)}


def learn_term_for_concern(agent, concern_keys) -> dict[str, Any]:
    """The stage-1 -> stage-2 CONNECTOR of the full self-extension loop: given a
    concern the agent SURFACED (a CapabilityAxis's capability_keys from
    gap_prioritiser), find the held Concept that names it, author its structural
    signature from that Concept's OWN definition (the held author_signature), and
    MATCH the signature to the held term-family it shares a shape with (the held
    shape-matcher). Returns the term-family the agent should build for the concern
    + the authored signature — the DECISION 'which term to build', made by the
    agent's own machinery. Mechanical routing over held faculties; no reasoning, no
    decision-if over graph state (author_signature + _shared_shape do the work).

    The missing link the loop walled on: stage 1 surfaces a concern KEY; this reads
    its held-Concept STRUCTURE so stage 2 (build the term) can run. Returns
    {connected, concern, concept, signature, term_family, shared, candidates} or an
    honest {connected: False, reason} when the concern carries no held structure."""
    keys = concern_keys if isinstance(concern_keys, (list, tuple)) else [concern_keys]
    # find the held Concept that names the concern (try each key)
    sig = None
    concept = None
    for k in keys:
        s_, _, cname = author_signature(agent, str(k))
        if s_:
            sig, concept = s_, cname
            break
    # INDUCED-CONCERN path: an axis minted by induce_concern carries its residual
    # structure ON the axis node (no separate held Concept). Read it directly — the
    # residual IS the signature. Mechanical graph read.
    induced_residual = None
    if not sig:
        sub = getattr(agent, "s", agent)
        for n in sub.nodes("CapabilityAxis"):
            at = sub.node(n)["attrs"]
            ck = at.get("capability_keys") or []
            if at.get("induced") and list(ck) == [str(k) for k in keys]:
                preds = at.get("residual_predicates") or []
                if preds:
                    sig = [[p] for p in preds]      # the residual predicates as a shape
                    concept = "(induced from observation)"
                    induced_residual = list(preds)
                break
    if not sig:
        return {"connected": False, "concern": list(keys),
                "reason": ("the surfaced concern carries no held Concept with a definition the "
                           "term-decision can read (a bare capability-key); needs a grounded "
                           "Concept before a term can be composed for it")}
    # match the concern signature to the held term-families (which term-shape fits).
    # Each candidate's SCORE is already a Rust FixedCount(AntiUnify(...)) read-out
    # (_shared_shape); the WINNER pick is now an Argmax TERM over those (score,
    # name) pairs (IndexAt, not Attr — Attr expects a graph NodeID, these are
    # literal pairs) — no Python sort/max decides it. Python keeps a SORTED
    # candidates list purely for the human-readable report (reporting, not
    # deciding — the design's allowed exception).
    fac_sigs = {n: v for n, v in _load_shape_signatures(agent).items() if v[0] == "faculty"}
    native = _native_eval2(agent)
    pairs = []                              # [fixed, name] — Term-evaluable literal pairs
    shared_by_name = {}
    for fn, (_, fsig, _) in fac_sigs.items():
        shared, fixed = _shared_shape(agent, sig, fsig)
        pairs.append([fixed, fn])
        shared_by_name[fn] = shared
    best_fixed, best_name = 0, None
    if pairs:
        picked = native.evaluate(
            {"type": "Argmax", "source": {"type": "Lit", "value": pairs}, "var_name": "c",
             "value": {"type": "IndexAt", "seq": {"type": "Var", "name": "c"},
                       "index": {"type": "Lit", "value": 0}},
             "default": None}, {})
        if picked is not None:
            best_fixed, best_name = int(picked[0]), picked[1]
    candidates_report = sorted(pairs, key=lambda p: -p[0])[:4]
    return {
        "connected": best_fixed > 0 and best_name is not None,
        "concern": list(keys),
        "concept": concept,
        "signature": sig,
        "term_family": best_name,
        "shared": shared_by_name.get(best_name),
        "shared_leaves": best_fixed,
        "candidates": [{"term_family": nm, "shared_leaves": fx} for fx, nm in candidates_report],
        "how": ("I CONNECT a surfaced concern to the term I should build by authoring the concern's "
                "structural signature from its held Concept's own definition, then matching that signature "
                "to the held term-family it shares a shape with (my own shape-matcher, an Argmax Term over "
                "the FixedCount(AntiUnify(...)) scores). The term to build "
                f"is of the {best_name!r} shape ({best_fixed} shared leaves) — the decision is the matcher's."),
    }


# ---------------------------------------------------------------------------
# CONCERN-INDUCTION FROM OBSERVATION — STAGE 1 pushed from "rank seeded axes" to
# "INDUCE a genuinely-new concern from what the agent OBSERVES". The surprise =
# where the agent's HELD term-shapes FAIL TO COVER an observed structure (held
# Covers Term = the coverage test; held AntiUnifyWitness = the residual as a
# first-class object). A concern is MINTED from that residual's structure (held
# author-signature move = AntiUnifyWitness over the residual) and INJECTED as a
# manifold-suggested CapabilityAxis that competes in gap_prioritiser's ranking —
# it ADDS a candidate, never overrides the Argmax. The DISCRIMINATIVE NULL: a
# coverable observation mints NOTHING (Covers=True); only an uncovered residual
# mints. All graph-native: Covers/AntiUnifyWitness are Rust Terms; the mint is a
# graph mutation; no Python decision-if over graph state, no LLM.
# ---------------------------------------------------------------------------
_SHAPE_DECODE_LOOP_SEEDS = ("math_capability_shapes", "self_design_axis", "shape_decode_loop")


def _installed_seed_ids(sub) -> set:
    """The set of seed ids already installed on `sub`, read from BOTH
    provenance markers currently in use: the `Seed{id}` node this module's own
    `_ensure_seed_chain`/`_ensure_shape_decode_loop` mint, AND the
    `SeedSummary{seed_id}` node `substrate.boot_all.load_all_seeds` mints for
    EVERY seed a full boot installs (a separate, pre-existing provenance
    convention this module didn't previously read). Wave 3 (deep-reader
    latency lever) FIX: without this second check, a `load_all_seeds`-booted
    agent's first `induce_concern`/`ground_concern`/`run_reading_flow` call
    found no `Seed` node for e.g. `shape_decode_loop` / `literary_analysis_
    driving` (already installed at boot under the `SeedSummary` convention)
    and re-ran `load_seed_manifest` for it, installing a SECOND copy of every
    rule the seed defines -- permanently doubling the cost of every
    subsequent `run_rules` pass that touches them (measured: la_* reading
    rules 18->36, ~21 rules overall, on the very first post-boot call).
    Purely a bookkeeping read; no decision -- a seed already installed is
    already installed, whichever marker recorded it."""
    have = set()
    try:
        for n in sub.nodes("Seed"):
            sid = sub.node(n)["attrs"].get("id")
            if sid:
                have.add(sid)
    except Exception:  # noqa: BLE001
        pass
    try:
        for n in sub.nodes("SeedSummary"):
            sid = sub.node(n)["attrs"].get("seed_id")
            if sid:
                have.add(sid)
    except Exception:  # noqa: BLE001
        pass
    return have


def _agent_root_node(sub):
    """Mechanical graph read: the substrate's own Agent ROOT node — as opposed to
    the `Agent{is_class:True}` class-marker node `boot_core` also adds (an
    `is_a`-target, not the agent instance) — the one real agent instance every
    booted substrate carries exactly one of. Returns None if absent (a bare
    scaffold with no Agent node at all)."""
    for n in sub.nodes("Agent"):
        at = sub.node(n)["attrs"]
        if not at.get("is_class"):
            return n
    return None


def _resolve_agent(agent):
    """Resolve (substrate_wrapper, native_inner, agent_root_node) from either a
    raw boot_core() substrate or an Agent-like wrapper carrying .s/.inner/.agent
    (the harness convention `ground_concern`'s callers already use). Mechanical
    duck-typing over the caller's object shape — no decision over graph state."""
    sub = getattr(agent, "s", agent)
    native = getattr(agent, "inner", None)
    if native is None:
        native = _native_eval2(sub)
    ag_node = getattr(agent, "agent", None)
    if ag_node is None:
        ag_node = _agent_root_node(sub)
    return sub, native, ag_node


def _ensure_shape_decode_loop(sub, native, ag_node):
    """Idempotently load the `shape_decode_loop` seed (+ its declared deps) onto
    `sub`, guarded by a graph-resident `Seed{id}` node OR a `SeedSummary
    {seed_id}` node (`_installed_seed_ids` — Wave 3 fix: a `load_all_seeds`
    full boot already installed these under the SeedSummary convention, so
    both markers must be checked or this re-installs a duplicate copy) — the
    SAME idempotency pattern `substrate.boot_core.load_seeds_into` uses (a
    seed whose marker node already exists is skipped), applied directly via
    `manifest_for` + `load_seed_manifest` (per the design note) rather than
    the full seed REGISTRY, since these seeds are not yet registered there.
    Mechanical seed I/O — admissible world-adapter work, not a decision. Also
    mechanically defaults `agent.codebook_epoch` to 0 the first time it's
    touched (closes the loop's re-decode gate; a default init, not a
    decision)."""
    from substrate.seed_loader import manifest_for
    have = _installed_seed_ids(sub)
    for sid in _SHAPE_DECODE_LOOP_SEEDS:
        if sid in have:
            continue
        native.load_seed_manifest(manifest_for(sid), ag_node)
        sub.add_node("Seed", {"id": sid, "version": "1.0.0"})
        have.add(sid)
    if ag_node is not None:
        at = sub.node(ag_node)["attrs"]
        if at.get("codebook_epoch") is None:
            sub.set_attr(ag_node, "codebook_epoch", 0.0)


def _key_component(pred: str) -> str:
    """Make one predicate SAFE to `_`-join into a `CapabilityAxis` key.

    THE DEFECT THIS CLOSES (`SHAPE_TYPE_VOCABULARY_SPIKE.md` §7.2, reported
    `[derived, not run]` and reproduced arithmetically before this fix).
    `SHAPE_AUDIT_PATTERN_C_FIXES_RESULTS.md` §1 made the key
    `"induced_" + "_".join(sorted(preds))` — sorted and untruncated, which
    closed both of that audit's failure directions. But `_` is used BOTH as the
    join separator BETWEEN predicates AND as the word separator INSIDE them
    (predicates here are snake_case relation heads), so the encoding is lossy:

        sorted(["a_b", "c"])  ->  "induced_a_b_c"
        sorted(["a", "b_c"])  ->  "induced_a_b_c"     # equal — a real collision

    A collision routes a genuinely novel observation to `sd_dedup_existing`,
    whose only effect is `status = "recognized_duplicate"` — the dangerous
    direction (novelty silently recorded as recognised).

    THE FIX, and why THIS one. A derived string key is a lossy encoding of a
    structural key, and every lossy encoding needs an escape the payload cannot
    contain. Percent-escaping the two characters that carry structure — the
    separator `_` and the escape introducer `%` — makes the encoding injective
    (the standard argument: escaped components contain no bare `_`, so the
    split is unambiguous, and `%` is escaped so no component can forge an
    escape sequence). Doubling `_` was considered and REJECTED: it is NOT
    injective (`["a_", "b"]` and `["a", "_b"]` both give a run of three).

    VALUE-PRESERVING BY CONSTRUCTION, which is why it is admissible here at all
    (the brief's own constraint: nothing that reads a key as a literal string
    may silently change). A predicate containing neither `_` nor `%` is
    returned UNCHANGED, so every key the tree currently produces is
    byte-identical — measured, not assumed: across all 92 `induce_concern` call
    sites with a source-literal observation, the predicate vocabulary is 61
    strings of which exactly ONE (`for_each`) contains `_`, and that one occurs
    only at `name_hint`-supplied sites, where this join never runs.
    """
    return pred.replace("%", "%25").replace("_", "%5f")


def induce_concern(agent, observation, *, name_hint=None) -> dict[str, Any]:
    """Observe one structured item via the tick-driven DEQUANTIZE/DYNAMIC-QUANTIZE
    loop (seeds/shape_decode_loop.json): ingest an Observation node carrying the
    observation's own relation-system as its `signature`, wire it `agent -observed->
    observation`, and run the loop to fixpoint. `sd_decode` (Rust `ShapeDecode` Term)
    dequantizes it against the held ShapeSignature codebook; `sd_recognize` is the
    COVERED branch (no growth, the discriminative null); `sd_mint_quantum` is the
    UNCOVERED branch (mints a CapabilityAxis from the residual — dynamic
    quantization). This function only ingests + ticks + reads the result back into
    the SAME return shape `induce_concern` returned pre-migration; the coverage/mint
    DECISION is the seeded rules', not Python's."""
    sub, native, ag_node = _resolve_agent(agent)
    obs = [list(x) if isinstance(x, (list, tuple)) else x for x in observation]
    _ensure_shape_decode_loop(sub, native, ag_node)

    # the capability-key: named from the observation's OWN predicates (mechanical —
    # the same naming `induce_concern` used pre-migration), not from the residual
    # (which is not yet known — the decode hasn't run). CANONICAL form (2026-08-12,
    # SHAPE_AUDIT.md §3.1 fix): sorted, not truncated — matching the convention
    # every OTHER comparison in this pipeline already uses (`build_candidate`
    # canonically sorts both sides before comparing; `ShapeDecode`/`AntiUnify`/
    # `FixedCount` all score over relation SETS, not ordered/truncated sequences).
    # Sorting (not deduping) fixes order-dependence while keeping the full
    # multiset — a repeated predicate head is real information the join should
    # not discard. Truncation carried no offsetting benefit: every read site of
    # `capability_keys`/`obs.key` treats it as an opaque equality-tested string,
    # never sliced or length-assumed.
    preds = [st[0] for st in obs if isinstance(st, list) and st and isinstance(st[0], str)]
    key = name_hint or (("induced_" + "_".join(_key_component(p) for p in sorted(preds)))
                        if preds else "induced_concern")

    obs_node = sub.add_node("Observation", {"signature": obs, "key": [key], "status": "pending"})
    if ag_node is not None:
        sub.add_edge(ag_node, "observed", obs_node)
    native.run_rules()

    at = sub.node(obs_node)["attrs"]
    status = at.get("status")
    if status == "recognized":
        covered_by = at.get("covered_by")
        return {"minted": False, "covered_by": covered_by,
                "observation": obs,
                "note": f"held term-shape {covered_by!r} covers the observation — no new concern (the null)"}
    if status == "recognized_transformed":
        # RECOGNITION-UNDER-TRANSFORMATION (design "transform-as-quantum-delta",
        # 2026-07-02): `sd_transform_decode`/`sd_recognize_transformed` already
        # decided the residual is identity + a per-dimension quantum delta on a
        # held shape, not novel structure — this branch only reads that decision
        # back (mechanical graph read of the Transform node `sd_recognize_transformed`
        # minted via `has_transform`), it does not re-derive it.
        covered_by = at.get("covered_by")
        transform_node = None
        for n in sub.neighbours(obs_node, "has_transform"):
            transform_node = n
            break
        t_at = sub.node(transform_node)["attrs"] if transform_node is not None else {}
        transform = {"dims": list(t_at.get("dims") or []),
                     "deltas": list(t_at.get("deltas") or []),
                     "transforms": list(t_at.get("transforms") or []),
                     "base": t_at.get("base")}
        # RUNG 2 (dimension inference, design "transform-as-quantum-delta"
        # scratchpad TRANSFORM_DESIGN.md): `sd_recognize_dim` mints the SAME
        # `Transform` node shape as rung 1's `sd_recognize_transformed`, plus
        # a generator/k pair (the missing dimension it recovered) when the
        # residual was explained via a held DimensionGenerator rather than a
        # plain per-dimension delta. Pure mechanical read — present only when
        # the Transform node actually carries it, never a decision.
        if t_at.get("generator") is not None:
            transform["generator"] = t_at.get("generator")
        if t_at.get("k") is not None:
            transform["k"] = t_at.get("k")
        return {"minted": False, "covered_by": covered_by, "transform": transform,
                "observation": obs,
                "note": (f"held term-shape {covered_by!r} covers the observation UNDER A "
                         "TRANSFORM (identity + a per-dimension quantum delta) — no new "
                         "concern, recognition-under-transformation rather than the exact "
                         "match `recognized` reports")}
    if status == "recognized_duplicate":
        # NOVELTY-GUARD DUPLICATE (2026-07-03, fix for unbounded axis growth):
        # `sd_mint_quantum`'s own guard refused to mint because an INDUCED
        # CapabilityAxis with the SAME capability_keys already exists — this
        # residual is a recurring re-observation of a concern already surfaced
        # (per-frame perception / the standing metascience concern re-seeing the
        # same uncoverable shape), not a genuinely new one. `sd_dedup_existing`
        # could not wire an edge to that existing axis (add_edge targets must be
        # match-bound vars; the existing axis was found via a Term search, not a
        # match triple) — read it back here via the SAME capability_keys equality
        # check 5 other call sites in this module already use as an induced
        # axis's identity. Mechanical read-back, not a re-decision: the identity
        # test is the rule's, this only resolves the node it already proved exists.
        axis_node = None
        for n in sub.nodes("CapabilityAxis"):
            a2 = sub.node(n)["attrs"]
            if a2.get("induced") and list(a2.get("capability_keys") or []) == [key]:
                axis_node = n
                break
        axis_at = sub.node(axis_node)["attrs"] if axis_node is not None else {}
        return {"minted": False, "covered_by_existing_axis": str(axis_node) if axis_node is not None else None,
                "capability_key": key,
                "residual_predicates": list(axis_at.get("residual_predicates") or []),
                "closest_held_shape": axis_at.get("closest_held_shape"),
                "observation": obs,
                "note": ("an induced CapabilityAxis already carries this exact capability_key "
                         "(a duplicate residual — recurring observation of an already-surfaced "
                         "concern) — no duplicate minted; reading back the EXISTING axis rather "
                         "than fabricating a fresh one")}
    if status == "minted":
        axis_node = None
        for n in sub.neighbours(obs_node, "minted"):
            axis_node = n
            break
        axis_at = sub.node(axis_node)["attrs"] if axis_node is not None else {}
        residual_predicates = list(axis_at.get("residual_predicates") or [])
        closest = axis_at.get("closest_held_shape")
        # mechanical description string (formatted from held data — the same text
        # the pre-migration mint wrote; `sd_mint_quantum` doesn't carry this attr,
        # so the shim adds it here, exactly like the ShapeDecode shim re-attaches
        # `provenance`), not a decision.
        if axis_node is not None and "description" not in axis_at:
            sub.set_attr(axis_node, "description",
                        "a concern induced from an observation no held term-shape covers: "
                        + " ".join(str(p) for p in residual_predicates))
        return {"minted": True, "axis_id": str(axis_node), "capability_key": key,
                "residual_predicates": residual_predicates, "closest_held_shape": closest,
                "observation": obs,
                "note": ("no held term-shape covers the observation; minted an induced CapabilityAxis "
                         "from the residual structure (competes in gap_prioritiser, never overrides Argmax)")}
    # honest fallback: the loop did not reach a terminal status (should not happen
    # once `run_rules` reaches fixpoint) — report, don't fake a verdict.
    return {"minted": False, "covered_by": None, "observation": obs,
            "note": f"induction did not resolve to a terminal status (status={status!r}) "
                    "within the tick-driven loop — honest, not faked"}


# ---------------------------------------------------------------------------
# CONCERN-GROUNDING — where INDUCTION becomes INVENTION. When an induced concern's
# residual matches NO held term-family (shared_leaves=0, because it's genuinely-
# new), GROUND it = COMPOSE a new term for the novel shape from held machinery.
# The keystone: a shape IS the Fold-iterate of its residual (shape_made_by_residual)
# + the residual is already a first-class object (held AntiUnifyWitness) -> the held
# generative shape-math algebra turns the uncovered residual INTO a term.
#
# Paths (cheapest first; the held machinery decides which fires):
#   1 GROUND-PREDICATES: map the residual's predicates through the held RelationCue
#     lexicon (text->structural relation) -> the residual's STRUCTURAL relations.
#     If they ground, the concern is expressible in held vocab.
#   2 GENERATE-FROM-RESIDUAL: build a held Fold-iterate term whose body IS the
#     residual-feedback recurrence the grounded relations name -> a term that
#     GENERATES (captures) the shape. The COVER check (re-cover the residual) +
#     the CAPTURE check (run it, get the dynamics back) are held Terms.
#   3 SELF-AUTHOR (escalate): if the residual grounds to NOTHING held (novel
#     predicates outside the lexicon) -> the honest WALL: route to the emitter
#     (rung-4) only if the shape is a genuinely-new BASE primitive; else report
#     the named frontier (predicate-grounding) — do NOT hand-pick a law (donkey).
# All graph-native: lexicon read, Fold-iterate Term, Covers Term; no Python law.
# ---------------------------------------------------------------------------
def _observed_structure(agent, trajectory) -> dict:
    """Extract a trajectory's STRUCTURAL signature via held numeric Terms run by
    the Rust evaluator (NOT Python analysis): zero-crossings (oscillation),
    peak-amplitude decay ratio (damping), crossing-period. The predicate grounds
    in THIS observed structure, not a word. Returns the measured structure +
    magnitudes — all from the one observed trajectory."""
    native = _native_eval2(agent)
    traj = [float(x) for x in trajectory]
    n = len(traj)
    if n < 3:
        return {"zero_crossings": 0, "decay_ratio": 1.0, "period": 0.0, "n": n}
    L = lambda v: {"type": "Lit", "value": v}
    V = lambda x: {"type": "Var", "name": x}
    # zero-crossings = Count(Filter(index-pairs, traj[i]*traj[i+1] < 0)) — held Terms
    pairs = list(range(n - 1))
    zc_term = {"type": "Count", "source": {
        "type": "Filter", "source": L(pairs), "var_name": "i",
        "predicate": {"type": "Lt",
                      "a": {"type": "Times", "items": [
                          {"type": "IndexAt", "seq": L(traj), "index": V("i")},
                          {"type": "IndexAt", "seq": L(traj),
                           "index": {"type": "Plus", "items": [V("i"), L(1)]}}]},
                      "b": L(0.0)}}}
    zc = int(native.evaluate(zc_term, {}))
    # peak amplitudes + decay ratio + period, from the same trajectory (held arithmetic over the data)
    peaks = [abs(traj[i]) for i in range(1, n - 1)
             if abs(traj[i]) >= abs(traj[i - 1]) and abs(traj[i]) > abs(traj[i + 1])]
    ratios = [peaks[i + 1] / peaks[i] for i in range(len(peaks) - 1) if peaks[i] > 1e-9]
    decay = sum(ratios) / len(ratios) if ratios else 1.0
    crosses = [i for i in range(1, n) if traj[i - 1] * traj[i] < 0]
    period = (2.0 * sum(crosses[i + 1] - crosses[i] for i in range(len(crosses) - 1))
              / (len(crosses) - 1)) if len(crosses) > 1 else 0.0
    return {"zero_crossings": zc, "decay_ratio": round(decay, 4),
            "period": round(period, 3), "n": n, "init_amp": round(abs(traj[0]), 4)}


def _structure_to_relations(structure) -> list:
    """Map an OBSERVED structural signature to the structural relations it exhibits
    — read off the DATA's structure (oscillation -> a feedback recurrence; decay ->
    bounded), NOT off any word. A trajectory with zero-crossings IS a feed-forward
    recurrence (build-from-prior); decaying peaks IS bounded. The relations are the
    structure the data HAS; this is the observational grounding, not a definition."""
    rels = []
    if structure.get("zero_crossings", 0) >= 2:
        rels.append(["build", "NEW", "from", "PRIOR"])     # it iterates a state forward (oscillates)
    if structure.get("decay_ratio", 1.0) < 0.98:
        rels.append(["bound", "SELF", "by", "UNIT"])       # amplitude shrinks (damped/bounded)
    return rels


def fit_magnitudes(agent, trajectory, *, k: float = 0.347, c0: float = 0.0834,
                   iters: int = 120, lr: float = 0.01, eps: float = 0.005) -> dict[str, Any]:
    """GRAPH-NATIVE magnitude fit: fit the decay coefficient c to the observed
    `trajectory` by a residual-feedback recurrence run by the Rust evaluator — the
    optimizer IS a residual-recurrence (the fit error feeds the next coefficient
    step), self-similar with shape_made_by_residual. ALL held Terms:
      • MODEL = Fold-iterate of the damped recurrence with candidate c (Substitute-
        in via env Var, evaluated by Rust);
      • RESIDUAL = a held numeric Term: SSE = sum_i (model[i]-obs[i])^2;
      • STEP = finite-difference descent as a Term: grad=(SSE(c+eps)-SSE(c))/eps,
        c' = c - lr*grad;
      • ITERATE = a held Fold over `iters` steps threading c.
    Python ONLY builds the Term JSON + dispatches one evaluate (the iteration is the
    Fold — no Python optimizer loop, no scipy/numpy). Returns the fitted c + the SSE
    before/after (residual dropping) + convergence flag."""
    native = _native_eval2(agent)
    obs = [float(x) for x in trajectory]
    n = len(obs)
    if n < 4:
        return {"fitted": False, "reason": "trajectory too short to fit"}
    # NULL: an un-fittable trajectory (no oscillation — the damped-oscillator model has
    # no signal to fit) -> report no-fit, don't fake a converged coefficient.
    crossings = sum(1 for i in range(1, n) if obs[i - 1] * obs[i] < 0)
    if crossings < 2:
        return {"fitted": False, "reason": ("trajectory has no oscillation (zero-crossings < 2) — the "
                                            "damped-oscillator model has nothing to fit; no spurious "
                                            "coefficient (the null holds)"),
                "zero_crossings": crossings}

    def L(v): return {"type": "Lit", "value": v}
    def V(x): return {"type": "Var", "name": x}
    def IA(seq, i): return {"type": "IndexAt", "seq": seq, "index": i}
    def P(*x): return {"type": "Plus", "items": list(x)}
    def Tm(*x): return {"type": "Times", "items": list(x)}
    def Mi(a, b): return {"type": "Minus", "a": a, "b": b}
    def Dv(a, b): return {"type": "Div", "a": a, "b": b}
    def Vec(*x): return {"type": "Vec", "items": list(x)}
    def Ap(s, it): return {"type": "Append", "seq": s, "item": it}
    def Fold(src, var, acc, init, body):
        return {"type": "Fold", "source": src, "var_name": var, "acc_name": acc, "init": init, "body": body}
    def Let(nm, val, body): return {"type": "Let", "name": nm, "value": val, "body": body}

    idx = list(range(n))

    def model_trail(c_expr):
        st = V("ms")
        vn = P(IA(st, L(1)), Tm(L(-k), IA(st, L(0))), Tm(Tm(L(-1.0), c_expr), IA(st, L(1))))
        xn = P(IA(st, L(0)), vn)
        return IA(Fold(L(idx), "i", "ms", Vec(L(1.0), L(0.0), Vec()),
                       Vec(xn, vn, Ap(IA(st, L(2)), xn))), L(2))

    def sse(c_expr):
        # let m = model(c) in Fold over indices summing (m[i]-obs[i])^2 — held numeric Term
        return Let("m", model_trail(c_expr),
                   Fold(L(idx), "i", "acc", L(0.0),
                        P(V("acc"), Tm(Mi(IA(V("m"), V("i")), IA(L(obs), V("i"))),
                                       Mi(IA(V("m"), V("i")), IA(L(obs), V("i")))))))

    # the FIT = a Fold threading c; body = c - lr * (SSE(c+eps)-SSE(c))/eps  (the residual-feedback step)
    cvar = V("c")
    grad = Dv(Mi(sse(P(cvar, L(eps))), sse(cvar)), L(eps))
    step = Mi(cvar, Tm(L(lr), grad))
    fit_term = Fold(L(list(range(iters))), "it", "c", L(c0), step)

    c_fit = float(native.evaluate(fit_term, {}))
    sse0 = float(native.evaluate(sse(L(c0)), {}))
    sse1 = float(native.evaluate(sse(L(c_fit)), {}))
    return {"fitted": True, "decay_c": round(c_fit, 4), "restoring_k": k,
            "sse_before": round(sse0, 4), "sse_after": round(sse1, 4),
            "converged": sse1 <= sse0,   # the residual dropped
            "how": ("I FIT the decay coefficient by a graph-native residual-feedback recurrence: the "
                    "fit error (model-vs-observation SSE, a held numeric Term) feeds the next coefficient "
                    "step (finite-diff gradient, a held Term), iterated by a held Fold — the optimizer is "
                    "itself a residual-recurrence (self-similar with shape_made_by_residual). The Rust "
                    "evaluator runs the whole fit; Python only dispatches.")}


def _sse_term_kc(trajectory):
    """The SSE Term for the (k,c) damped-oscillator model, reading k,c from ENV.
    A single held numeric Term (model Fold + squared-error Fold), evaluated by Rust
    per candidate (k,c). The model-fitting REASONING is this Term; the solver's
    outer iteration is dispatched over it (master_tick-style)."""
    obs = [float(x) for x in trajectory]
    n = len(obs)
    def L(v): return {"type": "Lit", "value": v}
    def V(x): return {"type": "Var", "name": x}
    def IA(seq, i): return {"type": "IndexAt", "seq": seq, "index": i}
    def P(*x): return {"type": "Plus", "items": list(x)}
    def Tm(*x): return {"type": "Times", "items": list(x)}
    def Mi(a, b): return {"type": "Minus", "a": a, "b": b}
    def Vec(*x): return {"type": "Vec", "items": list(x)}
    def Ap(s_, it): return {"type": "Append", "seq": s_, "item": it}
    def Fold(src, va, ac, ini, bo):
        return {"type": "Fold", "source": src, "var_name": va, "acc_name": ac, "init": ini, "body": bo}
    def Let(nm, val, body): return {"type": "Let", "name": nm, "value": val, "body": body}
    st = V("ms")
    vn = P(IA(st, L(1)), Tm(Mi(L(0.0), V("k")), IA(st, L(0))), Tm(Mi(L(0.0), V("c")), IA(st, L(1))))
    xn = P(IA(st, L(0)), vn)
    model = IA(Fold(L(list(range(n))), "i", "ms", Vec(L(1.0), L(0.0), Vec()),
                    Vec(xn, vn, Ap(IA(st, L(2)), xn))), L(2))
    return n, Let("m", model, Fold(L(list(range(n))), "i", "acc", L(0.0),
                  P(V("acc"), Tm(Mi(IA(V("m"), V("i")), IA(L(obs), V("i"))),
                                 Mi(IA(V("m"), V("i")), IA(L(obs), V("i")))))))


def fit_multi_one_term(agent, trajectory, *, k0: float = 0.3, c0: float = 0.1,
                       iters: int = 200, lr: float = 0.01, eps: float = 0.01,
                       clip: float = 1.5) -> dict[str, Any]:
    """Fit (k,c) JOINTLY as ONE held Term — the outer descent loop is a Fold Term
    (NOT Python-dispatched). The model+SSE is the held _sse_term_kc; the joint
    finite-difference gradient + CLIPPING (held IfThenElse clamp, so the recurrence
    cannot diverge to nan) + the iterate are all Terms. Python builds the (valid)
    Term JSON and dispatches ONE evaluate. Closes the multi-param 'one Term' caveat:
    the blocker was NUMERIC divergence (nan) from unclamped steps, not a parse bug —
    the recursion-cap fix lets it parse; the held clamp makes it converge.

    Returns the fitted (k,c) + SSE + convergence. donkey=0 (no Python descent loop)."""
    native = _native_eval2(agent)
    obs = [float(x) for x in trajectory]
    n = len(obs)
    if n < 6:
        return {"fitted": False, "reason": "trajectory too short to jointly fit"}
    crossings = sum(1 for i in range(1, n) if obs[i - 1] * obs[i] < 0)
    if crossings < 2:
        return {"fitted": False, "reason": "no oscillation — nothing to jointly fit (null)"}

    def L(v): return {"type": "Lit", "value": v}
    def V(x): return {"type": "Var", "name": x}
    def IA(seq, i): return {"type": "IndexAt", "seq": seq, "index": i}
    def P(*x): return {"type": "Plus", "items": list(x)}
    def Tm(*x): return {"type": "Times", "items": list(x)}
    def Mi(a, b): return {"type": "Minus", "a": a, "b": b}
    def Dv(a, b): return {"type": "Div", "a": a, "b": b}
    def Vec(*x): return {"type": "Vec", "items": list(x)}
    def Ap(s_, it): return {"type": "Append", "seq": s_, "item": it}
    def Fold(src, va, ac, ini, bo):
        return {"type": "Fold", "source": src, "var_name": va, "acc_name": ac, "init": ini, "body": bo}
    def Let(nm, val, body): return {"type": "Let", "name": nm, "value": val, "body": body}
    def Lt(a, b): return {"type": "Lt", "a": a, "b": b}
    def Ite(cond, t, o): return {"type": "IfThenElse", "cond": cond, "then": t, "other": o}
    # held clamp into [lo,hi] — the graph-native gradient clipping that prevents divergence
    def clamp(x, lo, hi): return Ite(Lt(x, L(lo)), L(lo), Ite(Lt(L(hi), x), L(hi), x))

    # the SSE Term reading k,c from a STATE tuple (p[0]=k, p[1]=c) bound by the Fold
    def sse(ke, ce):
        st = V("ms")
        vn = P(IA(st, L(1)), Tm(Mi(L(0.0), ke), IA(st, L(0))), Tm(Mi(L(0.0), ce), IA(st, L(1))))
        xn = P(IA(st, L(0)), vn)
        model = IA(Fold(L(list(range(n))), "i", "ms", Vec(L(1.0), L(0.0), Vec()),
                        Vec(xn, vn, Ap(IA(st, L(2)), xn))), L(2))
        return Let("m", model, Fold(L(list(range(n))), "i", "acc", L(0.0),
                   P(V("acc"), Tm(Mi(IA(V("m"), V("i")), IA(L(obs), V("i"))),
                                  Mi(IA(V("m"), V("i")), IA(L(obs), V("i")))))))

    st = V("p")
    k = IA(st, L(0))
    c = IA(st, L(1))
    base = sse(k, c)
    gk = clamp(Dv(Mi(sse(P(k, L(eps)), c), base), L(eps)), -clip, clip)
    gc = clamp(Dv(Mi(sse(k, P(c, L(eps))), base), L(eps)), -clip, clip)
    k_next = Mi(k, Tm(L(lr), gk))
    k_next = Ite(Lt(k_next, L(0.02)), L(0.02), k_next)       # keep k positive (held)
    c_next = Mi(c, Tm(L(lr), gc))
    c_next = Ite(Lt(c_next, L(0.0)), L(0.0), c_next)
    solver = Fold(L(list(range(iters))), "it", "p", Vec(L(k0), L(c0)), Vec(k_next, c_next))

    p = native.evaluate(solver, {})                          # ONE evaluate of the whole solver Term
    fk, fc = float(p[0]), float(p[1])
    # final SSE (read off the held SSE Term at the fitted point)
    fsse = native.evaluate(sse(L(fk), L(fc)), {})
    fsse = float(fsse) if (fsse == fsse and abs(fsse) < 1e12) else 1e12
    import json as _json
    return {"fitted": True, "restoring_k": round(fk, 4), "decay_c": round(fc, 4),
            "sse": round(fsse, 4), "one_term": True,
            "term_chars": len(_json.dumps(solver)),
            "converged": (fk == fk and fc == fc and fsse < 0.5),
            "how": ("The WHOLE joint (k,c) solver is ONE held Term: the outer descent is a Fold over "
                    "iterations whose body runs the SSE Term, computes the finite-diff gradient, CLIPS it "
                    "(held IfThenElse clamp — prevents the nan divergence that was the real blocker), and "
                    "steps both params. Python builds the Term + ONE evaluate; no dispatch, no Python loop.")}


def fit_multi(agent, trajectory, *, inits=None, iters: int = 200, lr: float = 0.01,
              eps: float = 0.01, clip: float = 1.5) -> dict[str, Any]:
    """GRAPH-NATIVE multi-parameter / NON-CONVEX fit of (k, c) JOINTLY to the
    observed trajectory. The model-vs-observation SSE is a HELD numeric Term run by
    the Rust evaluator (the reasoning); the solver — joint finite-difference
    gradient, gradient CLIPPING (escape divergence), and MULTI-START (Fold over
    several inits, keep lowest-SSE) to escape local minima — is the residual-
    feedback recurrence dispatched OVER that Term (master_tick-style: Python drives
    the iteration, the model/residual is the Term). NO scipy/numpy, NO Python model
    or SSE arithmetic, NO LLM. Returns the fitted (k,c) + per-init SSE + convergence."""
    native = _native_eval2(agent)
    obs = [float(x) for x in trajectory]
    if len(obs) < 6:
        return {"fitted": False, "reason": "trajectory too short to jointly fit"}
    crossings = sum(1 for i in range(1, len(obs)) if obs[i - 1] * obs[i] < 0)
    if crossings < 2:
        return {"fitted": False, "reason": "no oscillation — nothing to jointly fit (null)"}

    n, sse_term = _sse_term_kc(trajectory)

    def SSE(k, c):
        v = native.evaluate(sse_term, {"k": float(k), "c": float(c)})
        v = float(v)
        return v if (v == v and abs(v) < 1e12) else 1e12   # guard nan/inf (held Term value read)

    def _clip(g):
        return max(-clip, min(clip, g))

    def descend(k, c):
        # joint finite-diff gradient descent with clipping (the residual-feedback step,
        # dispatched over the held SSE Term)
        for _ in range(iters):
            b = SSE(k, c)
            gk = _clip((SSE(k + eps, c) - b) / eps)
            gc = _clip((SSE(k, c + eps) - b) / eps)
            k = max(0.02, k - lr * gk)
            c = max(0.0, c - lr * gc)
        return k, c, SSE(k, c)

    starts = inits or [(0.3, 0.10), (0.7, 0.10), (1.1, 0.10), (1.6, 0.10), (2.2, 0.10)]
    results = [descend(k0, c0) for (k0, c0) in starts]      # MULTI-START (dispatched; each a held-Term descent)
    best = min(results, key=lambda r: r[2])
    per_init = [round(r[2], 3) for r in results]
    evals = len(starts) * iters * 3                          # cost: model-evals (3 per joint step)
    # CONVERGENCE: best SSE is small AND meaningfully below the worst start (multi-start helped)
    converged = best[2] < 0.5 and best[2] < (max(per_init) - 0.5 if per_init else best[2] + 1)
    return {"fitted": True, "restoring_k": round(best[0], 4), "decay_c": round(best[1], 4),
            "sse": round(best[2], 4), "per_init_sse": per_init, "n_starts": len(starts),
            "model_evals": evals, "converged": converged,
            "how": ("I JOINTLY fit (k,c) by a graph-native multi-start solver: the model-vs-obs SSE is a "
                    "held numeric Term (Rust-evaluated); the joint finite-diff gradient + clipping + "
                    "multi-start (keep lowest-SSE) is the residual-feedback recurrence dispatched over it "
                    "to escape divergence and local minima. No scipy/numpy, no Python SSE arithmetic.")}


def ground_predicate(agent, predicate_label, trajectory) -> dict[str, Any]:
    """GROUND a novel predicate in OBSERVED STRUCTURE: extract the trajectory's
    structural signature (held Terms), and if it exhibits a held structural
    relation -> GROW the lexicon (mint a RelationCue mapping predicate_label -> that
    relation); else ESCALATE (self-author). The predicate grounds because the data
    HAS the structure — never a word-definition. Magnitudes measured from the same
    trajectory. Returns the grounding + the measured structure + magnitudes."""
    structure = _observed_structure(agent, trajectory)
    # NULL: no observable structural referent (flat/noise) -> do NOT ground
    if structure.get("n", 0) < 3 or (structure.get("zero_crossings", 0) == 0
                                     and structure.get("decay_ratio", 1.0) >= 0.98):
        return {"grounded": False, "predicate": predicate_label, "structure": structure,
                "path": "null",
                "reason": ("the predicate's observed data has NO structural signature (flat / no "
                           "oscillation, no decay) — nothing to ground; the lexicon grows only from "
                           "real observed structure (the null holds, no spurious vocabulary)")}
    obs_rels = _structure_to_relations(structure)
    # GROW: match the observed structure to held relations (held matcher), mint a RelationCue
    held = {tuple(rel): rel for _kw, rel in _load_relation_cues(agent)}
    matched = [rel for rel in obs_rels if tuple(rel) in held]
    if matched:
        from domains.teach import teach
        import json as _json
        minted = []
        role_checks: dict[str, Any] = {}
        for rel in matched:
            # compact separators (no spaces) -- matches seeds/relation_vocabulary.json's own
            # serialization convention EXACTLY (real bug found building the guard below: the
            # default json.dumps separator (", ") made every freshly-taught relation string
            # byte-DIFFERENT from the seed's compact form even when semantically identical,
            # so a byte-equality check across the two could never recognize a real match —
            # this is a pre-existing formatting inconsistency in ground_predicate's own code,
            # invisible until now because every other consumer re-parses via json.loads
            # rather than comparing the raw string).
            taught = teach(agent, "RelationCue",
                            {"keywords": [str(predicate_label).lower()],
                             "relation": _json.dumps(rel, separators=(",", ":")),
                             "grounded_from": "observation", "source": "predicate_grounding"},
                            category="relation_vocabulary")
            minted.append(rel)
            # ARGUMENT-ROLE MINT-TIME GUARD (see the block above _load_relation_cues):
            # every freshly-taught RelationCue is checked, live, against the held
            # ArgumentRole vocabulary — recognize (identical relation, safe), mint
            # (brand-new token, safe), or flag (existing token, new context — needs
            # disambiguation). ground_predicate only ever mints relations already held
            # verbatim (the `matched` filter above), so this is predicted to always
            # RECOGNIZE here — reported, not assumed (see role_checks in the return).
            role_checks[_json.dumps(rel)] = check_new_relation_cue_roles(agent, taught.get("node"))
        # magnitudes from the observed trajectory. restoring k ~ omega^2 from the
        # period (closed-form, exact). decay c: the log-decrement gives an APPROXIMATE
        # seed; the graph-native fit_magnitudes recurrence then REFINES it to the exact
        # SSE-minimizing value (the optimizer-as-residual-recurrence). Both from the
        # one observed trajectory — measured + fitted, never unit defaults.
        import math as _m
        per = max(structure.get("period", 0.0), 1.0)
        ratio = max(min(structure["decay_ratio"], 0.9999), 1e-6)
        c_seed = round(-2.0 * _m.log(ratio) / per, 4)            # log-decrement (approximate seed)
        w = (2.0 * 3.141592653589793 / structure["period"]) if structure["period"] > 1e-9 else 0.5
        k = round(w * w, 4)                                       # restoring ~ omega^2 (exact)
        # REFINE c by the graph-native residual-recurrence fit against the trajectory
        fit = fit_magnitudes(agent, trajectory, k=k, c0=c_seed)
        c = fit["decay_c"] if fit.get("fitted") else c_seed
        return {"grounded": True, "path": "grow_lexicon", "predicate": predicate_label,
                "structure": structure, "minted_relations": minted,
                "role_checks": role_checks,
                "measured_magnitudes": {"restoring_k": k, "decay_c": c},
                "fit": {"c_seed": c_seed, "c_fitted": c,
                        "sse_before": fit.get("sse_before"), "sse_after": fit.get("sse_after"),
                        "converged": fit.get("converged")} if fit.get("fitted") else None,
                "how": (f"I grounded {predicate_label!r} from OBSERVED STRUCTURE: the trajectory has "
                        f"{structure['zero_crossings']} zero-crossings (a feed-forward recurrence) and a "
                        f"peak-decay ratio {structure['decay_ratio']} (bounded) — so it exhibits the held "
                        f"relations {minted}. I minted a RelationCue label->relation and MEASURED the "
                        f"recurrence coefficients (k={k} from period, c={c} from decay) from the same data.")}
    # ESCALATE: observed structure matches NO held relation -> self-author a base relation
    return {"grounded": False, "path": "self_author", "predicate": predicate_label,
            "structure": structure, "observed_relations": obs_rels,
            "reason": ("the observed structure exhibits a relation NOT in held vocabulary — escalate to "
                       "the emitter (rung-4) to self-author a new base relation for it, then mint the "
                       "RelationCue. (Genuinely-new structural relation, not a relabel of held structure.)")}


def _residual_relations(agent, predicates) -> list:
    """Map residual predicates through the held RelationCue lexicon -> the
    structural relations they ground to. Held vocab read; no decision."""
    cues = _load_relation_cues(agent)
    text = " ".join(str(p) for p in predicates).lower()
    rels = []
    seen = set()
    for kws, rel in cues:
        if any(kw in text for kw in kws):
            k = tuple(rel)
            if k not in seen:
                rels.append(rel)
                seen.add(k)
    return rels


def _compose_comprehension_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A COMPREHENSION RULE — the self-build composer's perception-of-language path. When the
    concern grounds to a comprehend shape (hear a DIRECTIVE -> mint a GOAL), author a Rule that matches the
    ingested directive (a Mention 'describe' on a Message) over a perceived scene and MINTS the describe-Goal
    the communicate rule consumes. This closes the loop: a literal instruction now comprehends to the goal,
    graph-native, instead of the goal being hand-minted. Installed live.

    TWIN SHAPE (gated by the grounded 'find' relation — twin of _compose_communicate_rule's "which parts
    are built depends on which relations grounded" pattern, same composer, not a new one, since dispatch
    already resolves here via the 'comprehend' head): a 'find X' directive has no scene to describe — it
    names a TARGET the agent wants (e.g. "Find the page about volcanoes."). Author TWO rules instead: (1)
    MINT a Goal{kind:'find'} once per directive Mention whose text is 'find' (guarded, one per message);
    (2) BIND every OTHER Mention of that same message, except a small closed function-word set, to the
    Goal via 'wants' — the goal's content IS its wanted words, read from the graph, not hand-picked here."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Nb = lambda nd, et: {"type": "Neighbours", "node": nd, "edge_type": et}
    Exists = lambda src, var, pred: {"type": "Exists", "source": src, "var_name": var, "predicate": pred}
    rp = {r[0] for r in rels}
    tag = "_".join(str(k) for k in keys)

    if "find" in rp and "constrain" in rp:
        # STRUCTURED variant ("find X near Y") — POS-DRIVEN, no stopword list. The mechanical
        # ingest boundary (domains/browse_dispatch.py's `ingest_directive`) already POS-typed +
        # GOVERNANCE-stamped every Mention (construction_grammar.parse_directive_elements ->
        # parse_with_gaps' _pos_token — the SAME classifier the gap-as-part-of-speech
        # comprehension path uses), writing `role`/`pos`/`gov_prep` onto each Mention. A
        # content-NOUN Mention is the wanted TARGET unless its governing preposition
        # (`gov_prep`, None for a bare direct object) is in the held CONSTRAINT-class
        # preposition set (mirrors relation_vocabulary.json's `constrain_target_directive`
        # cue) — a POSITIVE held-vocabulary CLASS test (spatial/associative prepositions),
        # not an exclude-everything-but-this-list stoplist: 'about'-governed content
        # ('the page ABOUT volcanoes') still describes the TARGET; 'near'-governed content
        # ('NEAR the diagram') is a CONSTRAINT on where the target must be found. This
        # REPLACES `bind_find_target_<tag>` for this grounding (a directive whose residual
        # ALSO grounds a spatial/associative relation) — the plain stopword twin below still
        # handles a bare 'find X' concern with no grounded 'constrain' relation.
        constraint_preps = ["near", "next to", "beside", "adjacent to", "close to"]
        rules = [
            {"name": "comprehend_find_directive_structured_" + tag,
             "match": [["m", "has_mention", "dirmention"]],
             "where": {"type": "And", "items": [
                 {"type": "Eq", "a": Attr(V("dirmention"), "text"), "b": L("find")},
                 {"type": "Not", "arg": Exists(Nb(V("m"), "mint_goal"), "_i", L(True))}]},
             "effects": [["add_node", "goal", "Goal", {"kind": "find", "status": "active"}],
                         ["add_edge", "m", "mint_goal", "goal"]]},
            {"name": "bind_find_target_structured_" + tag,
             "match": [["m", "mint_goal", "goal"], ["m", "has_mention", "cm"]],
             "where": {"type": "And", "items": [
                 {"type": "Eq", "a": Attr(V("cm"), "role"), "b": L("content")},
                 {"type": "Eq", "a": Attr(V("cm"), "pos"), "b": L("noun")},
                 {"type": "Not", "arg": {"type": "In", "member": Attr(V("cm"), "gov_prep"),
                                          "container": L(constraint_preps)}}]},
             "effects": [["add_edge", "goal", "wants", "cm"]]},
            {"name": "bind_find_constraint_structured_" + tag,
             "match": [["m", "mint_goal", "goal"], ["m", "has_mention", "cm"]],
             "where": {"type": "And", "items": [
                 {"type": "Eq", "a": Attr(V("cm"), "role"), "b": L("content")},
                 {"type": "Eq", "a": Attr(V("cm"), "pos"), "b": L("noun")},
                 {"type": "In", "member": Attr(V("cm"), "gov_prep"),
                  "container": L(constraint_preps)}]},
             "effects": [["add_edge", "goal", "constrained_by", "cm"]]},
        ]
        idxs = []
        for r in rules:
            try:
                idxs.append(agent.inner.add_rule(r))
            except Exception as e:
                return {"grounded": False, "path": "compose_comprehension_rule", "concern": list(keys),
                        "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
        return {"grounded": True, "path": "compose_comprehension_rule", "concern": list(keys),
                "form": "find_directive_structured_rule", "grounded_relations": rels,
                "rules": rules, "rule_idx": idxs,
                "how": ("I GROUND the 'find X near Y' comprehension concern by composing THREE POS-DRIVEN "
                        "rules: the first mints a Goal{kind:'find'} the same way the plain find-directive "
                        "does; the second binds every content-NOUN Mention NOT governed by a held "
                        "constraint-class preposition as the wanted TARGET (goal -wants-> mention — covers "
                        "both a bare direct object 'page' and an 'about'-governed descriptor 'volcanoes'); "
                        "the third binds every content-NOUN Mention that IS governed by a held constraint "
                        "preposition ('near'/'next to'/'beside'/...) as a CONSTRAINT "
                        "(goal -constrained_by-> mention). No stopword list — both are a POSITIVE "
                        "held-vocabulary class test over the POS + governance the mechanical ingest "
                        "boundary already stamped on each Mention, replacing bind_find_target_<tag>'s "
                        "closed exclude-list for this grounding (a bare 'find X' with no grounded "
                        "'constrain' relation still falls to that twin, kept for backward compat).")}

    if "find" in rp:
        # closed function-word set (held vocabulary, the same kind of literal lexicon
        # relation_vocabulary.json's RelationCue keyword lists already are) — excludes the
        # directive word itself + common function words, so 'wants' binds only content words.
        stopwords = ["find", "the", "a", "an", "to", "for", "of", "on", "is", "are",
                     "me", "please", "go", "navigate", "about", "page", "site", "web"]
        rules = [
            {"name": "comprehend_find_directive_" + tag,
             "match": [["m", "has_mention", "dirmention"]],
             "where": {"type": "And", "items": [
                 {"type": "Eq", "a": Attr(V("dirmention"), "text"), "b": L("find")},
                 {"type": "Not", "arg": Exists(Nb(V("m"), "mint_goal"), "_i", L(True))}]},
             "effects": [["add_node", "goal", "Goal", {"kind": "find", "status": "active"}],
                         ["add_edge", "m", "mint_goal", "goal"]]},
            {"name": "bind_find_target_" + tag,
             "match": [["m", "mint_goal", "goal"], ["m", "has_mention", "cm"]],
             "where": {"type": "And", "items": [
                 {"type": "Not", "arg": {"type": "In", "member": Attr(V("cm"), "text"),
                                          "container": L(stopwords)}}]},
             "effects": [["add_edge", "goal", "wants", "cm"]]},
        ]
        idxs = []
        for r in rules:
            try:
                idxs.append(agent.inner.add_rule(r))
            except Exception as e:
                return {"grounded": False, "path": "compose_comprehension_rule", "concern": list(keys),
                        "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
        return {"grounded": True, "path": "compose_comprehension_rule", "concern": list(keys),
                "form": "find_directive_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
                "how": ("I GROUND the 'find X' comprehension concern by composing TWO rules: the first "
                        "recognises the directive Mention (text=='find') and MINTS a Goal{kind:'find'} "
                        "(guarded, once per instruction Message); the second binds every OTHER Mention of "
                        "that message — except a small closed function-word set — to the Goal via 'wants'. "
                        "The goal's wanted content is read straight from what I was told, not supplied.")}

    # bind the scene ONCE via the message's `about` edge (the instruction is about the current scene),
    # not by iterating percepts — so exactly one describe-Goal is minted per instruction.
    rule = {"name": "comprehend_describe_directive_" + tag,
            "match": [["m", "has_mention", "mention"], ["m", "about", "scene"]],
            "where": {"type": "And", "items": [
                {"type": "Eq", "a": Attr(V("mention"), "text"), "b": L("describe")},
                {"type": "Not", "arg": Exists(Nb(V("scene"), "described_by"), "_i", L(True))}]},
            "effects": [["add_node", "g", "Goal", {"kind": "describe_scene"}],
                        ["add_edge", "g", "describes", "scene"],
                        ["add_edge", "scene", "described_by", "g"]]}
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_comprehension_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_comprehension_rule", "concern": list(keys),
            "form": "comprehension_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND the comprehension concern by composing a rule that recognises the ingested "
                    "directive ('describe' over a perceived scene) and mints the describe-Goal — the literal "
                    "instruction now comprehends to the goal, instead of the goal being supplied.")}


def _compose_decision_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A DECISION-UNDER-UNCERTAINTY RULE from the grounded relations — the composer's
    action-selection path. When the concern grounds to a utility/argmax-over-candidates shape, author a
    Rule whose effect writes game.chosen_action = the action with the BEST EXPECTED UTILITY ACROSS the
    avatar candidates: argmax over the affordances of (sum over candidates of progress-toward-target).
    The whole decision is ONE held Term that reads candidates / affordances / target straight from the
    GRAPH (Neighbours + Attr) — so it runs in run_rules over whatever the agent perceived. No host logic;
    the agent does not need to know WHICH candidate is the avatar (it acts on the expected utility, and
    acting disambiguates). Installed live."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Plus = lambda *x: {"type": "Plus", "items": list(x)}
    Minus = lambda x, y: {"type": "Minus", "a": x, "b": y}
    Gte = lambda x, y: {"type": "Gte", "a": x, "b": y}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Absx = lambda x: Ite(Gte(x, L(0)), x, Minus(L(0), x))
    Nb = lambda nd, et: {"type": "Neighbours", "node": nd, "edge_type": et}
    # distance from a point (cy,cx terms) to the target goal node:
    d = lambda cy, cx: Plus(Absx(Minus(cy, Attr(V("goal"), "cy"))), Absx(Minus(cx, Attr(V("goal"), "cx"))))
    # progress of candidate c under affordance act = how much the move REDUCES distance-to-target:
    progress = Minus(d(Attr(V("c"), "cy"), Attr(V("c"), "cx")),
                     d(Plus(Attr(V("c"), "cy"), Attr(V("act"), "drow")),
                       Plus(Attr(V("c"), "cx"), Attr(V("act"), "dcol"))))
    # expected utility of an affordance = sum of that progress over ALL avatar candidates:
    eu = {"type": "Sum", "source": Nb(V("game"), "avatar_candidate"), "var_name": "c", "value": progress}
    # the best affordance = argmax of expected utility over the affordances; chosen_action = its name.
    best = {"type": "Argmax", "source": Nb(V("game"), "affordance"), "var_name": "act",
            "value": eu, "default": L(0)}
    chosen = Attr(best, "name")
    rule = {"name": "decide_under_uncertainty_" + "_".join(str(k) for k in keys),
            "match": [["game", "has_goal", "goal"]],
            "where": None,
            "effects": [["set_attr", "game", "chosen_action", {"__term__": chosen}]]}
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_decision_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_decision_rule", "concern": list(keys),
            "form": "decision_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND acting-under-uncertainty by composing a DECISION RULE: chosen_action = the "
                    "affordance with the best EXPECTED UTILITY ACROSS my avatar candidates (argmax over "
                    "affordances of summed progress-toward-target). The whole decision is one held Term "
                    "reading candidates/affordances/target from the graph — it runs in run_rules over what "
                    "I perceived. I needn't know which candidate is me: a move good for all of them wins, "
                    "and acting reveals which one moved.")}


def _compose_browse_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE THE BROWSE-AFFORDANCE-CHOICE RULES from the grounded 'match' relation — the composer's
    CONTENT-RELEVANCE decision path. A TWIN of _compose_decision_rule (same argmax-over-affordances-of-
    expected-value SHAPE), not an extension of it: _compose_decision_rule's Term hard-codes the GRID-
    NAVIGATION graph shape (game -avatar_candidate-> c with c.cy/c.cx; game -affordance-> act with
    act.drow/act.dcol; a Goal with cy/cx) — BrowserSession/Element/Affordance carry NONE of that vocabulary
    (no position, no candidates, no drow/dcol), only kind/label TEXT reached via a `has_affordance` edge
    (see below) and a Goal's wanted CONTENT (goal -wants-> mention, text). There is no way to parameterise
    the grid Term onto this domain without writing an entirely different Term body — which is what this
    composer is, reached the SAME way (ComposerCue relation_head 'match', dispatched by the held
    composer_pick Program), not a hand-written rule bypassing it.

    Two rules: CHOOSE (chosen_action = the affordance whose label overlaps the most wanted words — argmax
    over affordances of summed word-overlap) and STOP (once the wanted content is already visible on the
    CURRENT page, mark the goal satisfied and clear chosen_action, so the agent stops instead of wandering
    after arrival — the concern's optional stop condition). Installed live.

    Reads affordances via `sess -has_affordance-> aff`, a FLAT one-hop mirror worlds/browser.py maintains
    (the DOM's `contains` tree is of UNBOUNDED depth — `<nav>` wraps links, forms wrap inputs — and the
    DSL has no transitive-closure Term to walk it; the mirror is mechanical host I/O flattening what the
    tree already implies, the same one-hop `session -> affordance` shape
    `jabberwock_builds_decision_faculty.py`'s grid scaffold already uses via its literal `affordance`
    edge)."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Gte = lambda a, b: {"type": "Gte", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Nb = lambda nd, et: {"type": "Neighbours", "node": nd, "edge_type": et}
    Sum = lambda src, var, val: {"type": "Sum", "source": src, "var_name": var, "value": val}
    Exists = lambda src, var, pred: {"type": "Exists", "source": src, "var_name": var, "predicate": pred}
    Argmax = lambda src, var, val, default: {"type": "Argmax", "source": src, "var_name": var,
                                              "value": val, "default": default}
    StrIdx = lambda h, n: {"type": "StringIndexOf", "haystack": h, "needle": n}
    Plus = lambda *xs: {"type": "Plus", "items": list(xs)}
    Times = lambda *xs: {"type": "Times", "items": list(xs)}
    tag = "_".join(str(k) for k in keys)
    rp = {r[0] for r in rels}

    # flat mirror edge (worlds/browser.py) -- see docstring for why not a `contains`->`affords` walk.
    affordances = Nb(V("sess"), "has_affordance")
    wanted = Nb(V("goal"), "wants")
    # score(aff) = how many wanted words appear (case-folded substring) in the affordance's label.
    overlap = Sum(wanted, "wm",
                  Ite(Gte(StrIdx(Attr(V("aff"), "label_lc"), Attr(V("wm"), "text")), L(0)), L(1), L(0)))
    best = Argmax(affordances, "aff", overlap, L(0))

    if "constrain" in rp:
        # STRUCTURED variant — the Goal ALSO carries `constrained_by` mentions (the
        # comprehension composer's structured find-directive branch, gated the SAME way on
        # a grounded 'constrain' relation). CHOOSE weights TARGET overlap over CONSTRAINT
        # overlap (constraint words are SECONDARY evidence — a link naming the target wins a
        # tie, a link that only echoes the constraint word does not); STOP requires BOTH a
        # target word AND a constraint word to be visible somewhere on the arrived page
        # (two independently-bound body-text Elements, so the same element or two different
        # ones both count) — not just the target, so a decoy page mentioning the target alone
        # does not satisfy a constrained goal.
        constrained = Nb(V("goal"), "constrained_by")
        overlap_constraint = Sum(constrained, "cw",
                                  Ite(Gte(StrIdx(Attr(V("aff"), "label_lc"), Attr(V("cw"), "text")), L(0)),
                                      L(1), L(0)))
        weighted = Plus(Times(L(2), overlap), overlap_constraint)
        best_c = Argmax(affordances, "aff", weighted, L(0))
        chosen_c = Attr(best_c, "world_id")
        rules_c = [
            {"name": "choose_affordance_structured_" + tag,
             "match": [["sess", "has_goal", "goal"]],
             "where": Not(Eq(Attr(V("goal"), "status"), L("satisfied"))),
             "effects": [["set_attr", "sess", "chosen_action", {"__term__": chosen_c}]]},
            {"name": "browse_goal_satisfied_structured_" + tag,
             "match": [["sess", "has_goal", "goal"], ["sess", "contains", "el"], ["sess", "contains", "el2"]],
             "where": And(Not(Eq(Attr(V("goal"), "status"), L("satisfied"))),
                          Not(Exists(Nb(V("el"), "affords"), "_k", L(True))),
                          Not(Exists(Nb(V("el2"), "affords"), "_k2", L(True))),
                          Exists(wanted, "wm2",
                                 Gte(StrIdx(Attr(V("el"), "text_lc"), Attr(V("wm2"), "text")), L(0))),
                          Exists(constrained, "cw2",
                                 Gte(StrIdx(Attr(V("el2"), "text_lc"), Attr(V("cw2"), "text")), L(0)))),
             "effects": [["set_attr", "goal", "status", "satisfied"],
                         ["set_attr", "sess", "chosen_action", ""]]},
        ]
        idxs_c = []
        for r in rules_c:
            try:
                idxs_c.append(agent.inner.add_rule(r))
            except Exception as e:
                return {"grounded": False, "path": "compose_browse_rule", "concern": list(keys),
                        "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
        return {"grounded": True, "path": "compose_browse_rule", "concern": list(keys),
                "form": "browse_structured_rule", "grounded_relations": rels,
                "rules": rules_c, "rule_idx": idxs_c,
                "how": ("I GROUND choosing an affordance UNDER A CONSTRAINT by composing a structured twin "
                        "of the plain browse rule: CHOOSE writes chosen_action = the affordance with the "
                        "best WEIGHTED score (2x target-word overlap + 1x constraint-word overlap — target "
                        "evidence dominates, constraint is secondary/tie-breaking, over the SAME "
                        "session -has_affordance-> affordance / goal -wants-> mention shape, plus "
                        "goal -constrained_by-> mention this concern's structured comprehension binds); STOP "
                        "requires a target word AND a constraint word BOTH visible among the arrived page's "
                        "non-affording body-text elements before marking the goal satisfied — a decoy page "
                        "that only mentions the target does not satisfy it.")}
    # NOTE: the world-adapter's TypedGraph->WorldInstance mirror renames the original
    # ingest-time `id` attr (worlds/browser.py's `aff_wid`, what domains/browse_dispatch.py's
    # `world.apply((chosen,))` / `_locator_map` expect back) to `world_id`, to avoid
    # clobbering the native NodeID — read THAT key, not `id` (found empirically: `Attr(x,
    # "id")` silently evaluates to None since no perceived node ever carries a bare "id").
    chosen = Attr(best, "world_id")

    rules = [
        {"name": "choose_affordance_by_relevance_" + tag,
         "match": [["sess", "has_goal", "goal"]],
         "where": Not(Eq(Attr(V("goal"), "status"), L("satisfied"))),
         "effects": [["set_attr", "sess", "chosen_action", {"__term__": chosen}]]},
        {"name": "browse_goal_satisfied_when_seen_" + tag,
         "match": [["sess", "has_goal", "goal"], ["sess", "contains", "el"]],
         # excludes elements that THEMSELVES afford an action (a link's own anchor text
         # naming the target — e.g. "Learn about volcanoes" — would otherwise trivially
         # satisfy the goal on the INDEX page, before ever following it; only an element
         # with NO outgoing 'affords' edge — body text, a heading — counts as "I have
         # actually arrived at the content", not "I can see a link toward it").
         "where": And(Not(Eq(Attr(V("goal"), "status"), L("satisfied"))),
                      Not(Exists(Nb(V("el"), "affords"), "_k", L(True))),
                      Exists(wanted, "wm2",
                             Gte(StrIdx(Attr(V("el"), "text_lc"), Attr(V("wm2"), "text")), L(0)))),
         "effects": [["set_attr", "goal", "status", "satisfied"],
                     ["set_attr", "sess", "chosen_action", ""]]},
    ]
    idxs = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:
            return {"grounded": False, "path": "compose_browse_rule", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_browse_rule", "concern": list(keys),
            "form": "browse_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
            "how": ("I GROUND choosing WHICH AFFORDANCE to act on by composing TWO rules over the ACTUAL "
                    "perceived browsing shape (session -contains-> element -affords-> affordance; "
                    "goal -wants-> mention): CHOOSE writes chosen_action = the affordance whose label "
                    "overlaps the most wanted words (argmax over affordances of summed word-overlap — the "
                    "same expected-value-argmax SHAPE decide_under_uncertainty uses, over TEXT relevance "
                    "instead of spatial progress, because this domain has no position/candidate vocabulary "
                    "to reuse the grid rule's Term against); STOP marks the goal satisfied and clears "
                    "chosen_action once the wanted content is already visible on the current page, so I "
                    "stop once I have what I wanted instead of wandering. Installed live; run_rules drives "
                    "it over whatever session/goal I perceive.")}


def _compose_grouping_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE AN ORDER-N OBJECT from co-moving parts — the self-build composer's part-whole path. The
    jabberwock fuses the parts of its body (the Features it controls — all co-moving at its tracked-avatar
    location) into ONE Object node that comprises them and inherits their cells, so the WHOLE has a single
    shape (the shape faculty then names the whole, not a colour sub-part). Two rules: fuse_whole (controlled
    Features -> one Object via has_part) and whole_cells (the Object's cells = the union of its parts' Regions'
    cells, so shape_descriptor over the Object describes the whole). Installed live; composition from the held
    'group' relation, not a hand-written rule."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    A = lambda n, k: {"type": "Attr", "node": V(n), "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    tag = "_".join(str(k) for k in keys)
    rules = [
        {"name": "fuse_whole_" + tag,                          # the co-moving parts I control are ONE whole
         "match": [["game", "has_feature", "F"]],
         "where": Eq(A("F", "responds_to_my_action"), L(True)),
         "effects": [["add_node_if_absent", "obj", "Object", {"fkey": 777777.0, "is_body": 1.0}],
                     ["add_edge", "game", "has_object", "obj"],
                     ["add_edge", "obj", "has_part", "F"]]},
        {"name": "whole_cells_" + tag,                         # the whole's cells = the union of its parts' cells
         "match": [["game", "has_object", "obj"], ["obj", "has_part", "F"],
                   ["R", "realises", "F"], ["c", "within", "R"]],
         "where": Eq(A("obj", "is_body"), L(1.0)),
         "effects": [["add_edge", "c", "within", "obj"]]},
    ]
    idxs = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:
            return {"grounded": False, "path": "compose_grouping_rule", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_grouping_rule", "concern": list(keys),
            "form": "grouping_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
            "how": ("I COMPOSE an order-N whole from my co-moving parts: the Features I control fuse into ONE "
                    "Object that comprises them and inherits their cells, so the shape faculty names the WHOLE "
                    "body (one shape) instead of its colour sub-parts.")}


def _compose_control_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE THE CONTROL-GROUNDING RULES from the grounded 'control' relation — the self-build composer's
    agency path. The jabberwock grounds 'what I control' over the WHOLE body, not a colour sub-part: by default
    a Feature does NOT respond to my action; the Features at my tracked-avatar's location (avatar_tracking's
    is_avatar candidate — the whole co-located body, by spatial proximity, not by one colour value) respond and
    are selective -> the_thing_i_control recognises the whole, while real autonomous movers (responds=false)
    stay a_thing_that_moves_itself. Installed live. Composition from the held relation, not a hand-written rule."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    A = lambda n, k: {"type": "Attr", "node": V(n), "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Lt = lambda a, b: {"type": "Lt", "a": a, "b": b}
    Abs = lambda x: {"type": "Abs", "arg": x}
    Sub = lambda a, b: {"type": "Minus", "a": a, "b": b}
    tag = "_".join(str(k) for k in keys)
    rules = [
        {"name": "default_no_response_" + tag,                  # the environment does not respond to my action
         "match": [["game", "has_feature", "F"]],
         "where": Eq(A("F", "responds_to_my_action"), L(None)),
         "effects": [["set_attr", "F", "responds_to_my_action", False]]},
        {"name": "control_my_body_" + tag,                      # the WHOLE body at my avatar's location is mine
         "match": [["game", "has_candidate", "cand"], ["game", "has_feature", "F"]],
         "where": And(Eq(A("cand", "is_avatar"), L(1.0)),
                      Lt(Abs(Sub(A("F", "cy"), A("cand", "cy"))), L(3.0)),
                      Lt(Abs(Sub(A("F", "cx"), A("cand", "cx"))), L(3.0)),
                      Not(Eq(A("F", "responds_to_my_action"), L(True)))),
         "effects": [["set_attr", "F", "responds_to_my_action", True],
                     ["set_attr", "F", "selective", True]]},
    ]
    idxs = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:
            return {"grounded": False, "path": "compose_control_rule", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_control_rule", "concern": list(keys),
            "form": "control_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
            "how": ("I GROUND 'what I control' by composing TWO rules: by default a thing does not respond to my "
                    "action; the WHOLE body at my tracked-avatar's location (all its co-located parts, by "
                    "proximity — not one colour) responds and is selective, so the_thing_i_control recognises my "
                    "whole body and real movers stay autonomous. Installed live.")}


def _compose_communicate_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A COMMUNICATE-ACTION RULE from the grounded relations — the self-build
    composer's action-rule path (twin of the Fold-iterate term path). When the concern
    grounds to a communicate/decompose shape, author a Rule that, FOR EACH recognised
    thing in a scene the agent is told to describe, MINTS a produce-utterance subgoal
    sourced from the recognition — and install it live (add_rule). The rule's PARTS are
    selected by which relations grounded (iterate -> match over percepts; source -> bind
    the recognised concept; decompose -> mint the subgoal; communicate -> mark its action
    produce-utterance). Composition from held relations, not a hand-written rule."""
    rp = {r[0] for r in rels}
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    match = [["g", "describes", "scene"], ["scene", "has_percept", "p"]]
    if "source" in rp:                                  # bind the recognised concept (content source)
        match.append(["p", "is_a", "con"])
    where = {"type": "Not", "arg": {"type": "Exists",
             "source": {"type": "Neighbours", "node": V("p"), "edge_type": "uttered"},
             "var_name": "_i", "predicate": L(True)}}   # fixpoint guard: not already uttered
    effects = []
    if "decompose" in rp:
        sg_attrs = {"kind": "produce_utterance"}
        if "communicate" in rp:
            sg_attrs["action"] = "produce_utterance"
        effects.append(["add_node", "sg", "Goal", sg_attrs])
        effects.append(["add_edge", "g", "has_subgoal", "sg"])
        if "source" in rp:
            effects.append(["add_edge", "sg", "about", "con"])
            effects.append(["add_edge", "sg", "of_percept", "p"])
    if "source" in rp:
        effects.append(["add_edge", "p", "uttered", "con"])   # guard marker
    rule = {"name": "communicate_what_i_see_" + "_".join(str(k) for k in keys),
            "match": match, "where": where, "effects": effects}
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_communicate_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_communicate_rule", "concern": list(keys),
            "form": "communicate_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND the communicate concern by composing an ACTION RULE (not a Fold term): the "
                    "grounded relations select its parts — iterate -> match each recognised thing in a "
                    "scene I'm told to describe; decompose -> mint a subgoal; communicate -> its action is "
                    "produce-utterance; source -> bind it to the recognition. Installed live; run_rules "
                    "mints a produce-utterance subgoal per thing I see.")}


def _compose_conceptualize_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE THE CONCEPTUALIZER'S FORMATION + SELF-MONITOR RULES — the self-build
    composer's PHASE-1 ('form'/'shape' heads) AND PHASE-2 ('monitor'/'commit' heads)
    path (twin of _compose_communicate_rule: which RULES get installed depends on which
    relations grounded). PHASE 2 adds Levelt's internal MONITOR: 'monitor' authors
    request_monitor_<tag> (once a MessageShape exists, request it be checked); 'commit'
    authors the commitment gate's two branches, commit_if_recoverable_<tag> (a
    recoverable Verdict mints Committed — nothing is cleared to emit before this) and
    revise_if_not_recoverable_<tag> (a non-recoverable Verdict re-requests the shape
    for the SAME intent, which re-runs against the CURRENT — possibly regrounded —
    audience state; the re-shape re-triggers request_monitor_<tag>, closing the
    monitor -> revise -> re-monitor loop as ordinary rule-fixpoint chaining, no Python
    iteration). See domains/conceptualizer.py's scan_and_monitor for the mechanical
    "imagine reception" computation (domains.language.comprehend decode + a freshly
    regrounded audience_model/residual_vs_audience) that fills the Verdict these rules
    branch on. Levelt's conceptualizer forms a communicative INTENT (force +
    perlocutionary goal) and a message SHAPE (focus vs ground) BEFORE the formulator runs —
    the jabberwock currently jumps comprehend->produce with no formed intent; this composes
    the missing formation step, authored from the framed concern, not hand-written.

    'form' in rp -> author `form_intent_<tag>`: a communicative Goal carrying -for_audience->
    an audience AND -wants_force-> the held ForceCodebookHub (seeds/conceptualizer.json;
    domains/conceptualizer.py wires this ONE edge, always the same target, when it mints the
    Goal — mechanical, not a choice) JOINS the hub's ForceTemplate children and the RULE
    ENGINE picks the one whose `kind` equals the Goal's `force_kind` via an Eq-test in
    `where` (a graph-native selection, not a Python if/elif) — the winning template's
    `force` / `perlocutionary_goal` are copied onto a newly-minted CommunicativeIntent,
    which also inherits the Goal's `content` as `informative_content` and the same audience
    edge.

    'shape' in rp -> author `request_message_shape_<tag>`: once a CommunicativeIntent
    exists, mint a MessageShapeRequest{status:'requested'} — the SAME 'pending request'
    idiom domains/audience_production_dispatch.py already established for
    ProduceForAudienceRequest — that domains/conceptualizer.py's marshal-only scan later
    fills in by calling domains.audience_driven_production.residual_vs_audience /
    select_utterance VERBATIM (reused, never reimplemented): the FOCUS/GROUND split and the
    audience-tailored formulation stay entirely inside that already-approved machinery."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Nb = lambda nd, et: {"type": "Neighbours", "node": nd, "edge_type": et}
    Exists = lambda src, var, pred: {"type": "Exists", "source": src, "var_name": var, "predicate": pred}
    rp = {r[0] for r in rels}
    tag = "_".join(str(k) for k in keys)
    rules = []
    # idempotency guard — a re-ground of the SAME concern key must not re-churn the rule
    # store (mirrors the graph-meta-rule tier's own composed-guard); mechanical name lookup
    # via the existing `export_rules()` reader, not a content decision.
    existing_names = {r.get("name") for r in agent.inner.export_rules() if isinstance(r, dict)}

    if "form" in rp and ("form_intent_" + tag) not in existing_names:
        rules.append({
            "name": "form_intent_" + tag,
            "match": [["g", "for_audience", "aud"], ["g", "wants_force", "hub"],
                      ["hub", "has_template", "ft"]],
            "where": {"type": "And", "items": [
                {"type": "Eq", "a": Attr(V("g"), "force_kind"), "b": Attr(V("ft"), "kind")},
                {"type": "Not", "arg": Exists(Nb(V("g"), "forms_intent"), "_i", L(True))}]},
            "effects": [
                ["add_node", "intent", "CommunicativeIntent", {
                    "force": {"__term__": Attr(V("ft"), "force")},
                    "perlocutionary_goal": {"__term__": Attr(V("ft"), "perlocutionary_goal")},
                    "informative_content": {"__term__": Attr(V("g"), "content")},
                }],
                ["add_edge", "g", "forms_intent", "intent"],
                ["add_edge", "intent", "for_audience", "aud"],
            ],
        })

    if "shape" in rp and ("request_message_shape_" + tag) not in existing_names:
        rules.append({
            "name": "request_message_shape_" + tag,
            "match": [["g", "forms_intent", "intent"]],
            "where": {"type": "Not", "arg": Exists(Nb(V("intent"), "requests_shape"), "_i", L(True))},
            "effects": [
                ["add_node", "req", "MessageShapeRequest", {"status": "requested"}],
                ["add_edge", "intent", "requests_shape", "req"],
                ["add_edge", "req", "for_intent", "intent"],
            ],
        })

    # PHASE 2 — the SELF-MONITOR (Levelt's internal loop). 'monitor' -> once a
    # MessageShape exists, request that it be monitored (the SAME "pending
    # request" idiom as request_message_shape_<tag>, one level up); the
    # mechanical fill (domains/conceptualizer.py's scan_and_monitor: imagine
    # reception via domains.language.comprehend + a FRESHLY regrounded
    # audience_model/residual_vs_audience call, never reimplemented) writes a
    # Verdict{recoverable, perlocutionary_goal, missing} the next two rules
    # branch on via a plain Eq-test — the DECISION (commit vs revise) is the
    # rule engine's, only the set-algebra computing `recoverable` is Python.
    if "monitor" in rp and ("request_monitor_" + tag) not in existing_names:
        # NOTE the match goes through `req` (the MessageShapeRequest), not a bare
        # `[["intent", "has_shape", "shape"]]` triple: `has_shape` is ALSO wired
        # req->shape by scan_and_conceptualize (so a request could itself satisfy
        # an untyped "X has_shape shape" pattern), and a match var is not
        # type-restricted by name alone — binding through req's OWN for_intent
        # edge (only ever present on a MessageShapeRequest) is unambiguous: one
        # match per real MessageShapeRequest, `intent` always the true intent.
        rules.append({
            "name": "request_monitor_" + tag,
            "match": [["req", "for_intent", "intent"], ["req", "has_shape", "shape"]],
            "where": {"type": "Not", "arg": Exists(Nb(V("req"), "requests_monitor"), "_i", L(True))},
            "effects": [
                ["add_node", "mreq", "MonitorRequest", {"status": "requested"}],
                ["add_edge", "req", "requests_monitor", "mreq"],
                ["add_edge", "mreq", "for_shape", "shape"],
                ["add_edge", "mreq", "for_intent", "intent"],
            ],
        })

    # 'commit' -> the two branches of the commitment gate: a RECOVERABLE
    # verdict COMMITS (mints the Committed node nothing may be emitted
    # without — the commit gate); a NON-recoverable verdict REVISES (mints a
    # fresh MessageShapeRequest for the SAME intent, which scan_and_
    # conceptualize reprocesses against the now-current — possibly
    # regrounded — audience state, and request_monitor_<tag> re-fires on the
    # new MessageShape, re-monitoring: the "loop until recoverable" IS this
    # rule chain re-triggering itself inside one run_rules fixpoint, capped
    # the same way every other rule-fixpoint loop in this codebase is capped
    # — by run_rules' own tick budget, not a hand-rolled round counter).
    if "commit" in rp:
        if ("commit_if_recoverable_" + tag) not in existing_names:
            rules.append({
                "name": "commit_if_recoverable_" + tag,
                "match": [["mreq", "has_verdict", "verdict"], ["mreq", "for_intent", "intent"],
                          ["mreq", "for_shape", "shape"]],
                "where": {"type": "And", "items": [
                    {"type": "Eq", "a": Attr(V("verdict"), "recoverable"), "b": L(True)},
                    {"type": "Not", "arg": Exists(Nb(V("intent"), "has_committed"), "_i", L(True))}]},
                "effects": [
                    ["add_node", "committed", "Committed", {
                        "utterance": {"__term__": Attr(V("shape"), "utterance")},
                        "terseness": {"__term__": Attr(V("shape"), "terseness")},
                        "grounded_used": {"__term__": Attr(V("shape"), "grounded_used")},
                    }],
                    ["add_edge", "intent", "has_committed", "committed"],
                    ["add_edge", "mreq", "resulted_in", "committed"],
                ],
            })
        if ("revise_if_not_recoverable_" + tag) not in existing_names:
            rules.append({
                "name": "revise_if_not_recoverable_" + tag,
                "match": [["mreq", "has_verdict", "verdict"], ["mreq", "for_intent", "intent"]],
                "where": {"type": "And", "items": [
                    {"type": "Eq", "a": Attr(V("verdict"), "recoverable"), "b": L(False)},
                    {"type": "Not", "arg": Exists(Nb(V("mreq"), "revised"), "_i", L(True))}]},
                "effects": [
                    ["add_node", "req2", "MessageShapeRequest", {"status": "requested"}],
                    ["add_edge", "intent", "requests_shape", "req2"],
                    ["add_edge", "req2", "for_intent", "intent"],
                    ["add_edge", "mreq", "revised", "req2"],
                ],
            })

    if not rules:
        already = (("form_intent_" + tag) in existing_names
                   or ("request_message_shape_" + tag) in existing_names
                   or ("request_monitor_" + tag) in existing_names
                   or ("commit_if_recoverable_" + tag) in existing_names)
        if already and rp & {"form", "shape", "monitor", "commit"}:
            return {"grounded": True, "path": "compose_conceptualize_rule", "concern": list(keys),
                    "form": "conceptualize_rule", "grounded_relations": rels, "rules": [], "rule_idx": [],
                    "served_by": "python",
                    "how": "already composed for this concern key — idempotent re-ground, no rechurn."}
        return {"grounded": False, "path": "compose_conceptualize_rule", "concern": list(keys),
                "grounded_relations": rels,
                "wall": "none of 'form'/'shape'/'monitor'/'commit' grounded — nothing to compose"}

    idxs = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:
            return {"grounded": False, "path": "compose_conceptualize_rule", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_conceptualize_rule", "concern": list(keys),
            "form": "conceptualize_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
            "how": ("I GROUND the conceptualizer concern by composing rules from the grounded relations: "
                    "'form' -> form_intent_<tag> (a communicative Goal JOINS the held ForceCodebookHub's "
                    "templates via an Eq-test on force_kind==kind — the rule engine picks the force + "
                    "perlocutionary_goal, mints a CommunicativeIntent inheriting the Goal's content + "
                    "audience edge); 'shape' -> request_message_shape_<tag> (once an intent exists, "
                    "requests a MessageShape the host marshal fills via the ALREADY-HELD "
                    "residual_vs_audience/select_utterance machinery, never reimplemented here); "
                    "'monitor' -> request_monitor_<tag> (once a MessageShape exists, request it be "
                    "checked before it may be emitted); 'commit' -> commit_if_recoverable_<tag> / "
                    "revise_if_not_recoverable_<tag> (Eq-branch on a Verdict.recoverable the host "
                    "marshal computed by IMAGINING RECEPTION — decoding my own utterance back via "
                    "comprehend and rechecking the audience's CURRENT credited ground — commit mints "
                    "the gate-cleared Committed node, revise re-requests the shape against the "
                    "regrounded audience and the chain re-monitors).")}


def _compose_construction_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A SYNTACTIC CONSTRUCTION RULE — the self-build composer's GRAMMAR path (twin of the
    comprehension/communicate rule paths). When the concern grounds to a CONSTRUCT/FRAMES shape (a
    FUNCTION word FRAMES the following CONTENT word — the 'the X' construction), author a graph-native
    Production over the grounded-token SEQUENCE: for a FUNCTION word-form token that `precedes` a CONTENT
    word-form token, mark the content token as the referent-BEARER and link it `framed_by` the function
    token. This is order-3 SYNTAX as GRAPH DATA — a construction rule that runs in run_rules over the
    token lattice (like vit_step), not a Python string match. Installed live; the decode reads
    `referent_bearer` / `framed_by` to trust content-word bindings and let a frame introduce a new
    referent. The grounded relations select the shape (frames -> the frame edge; precede -> the order)."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    rp = {r[0] for r in rels} | {(r[2] if len(r) > 2 else "") for r in rels}
    # match a function-word token that precedes a content-word token in the sequence.
    rule = {"name": "construct_function_frames_content_" + "_".join(str(k) for k in keys),
            "match": [["f", "precedes", "c"]],
            "where": {"type": "And", "items": [
                {"type": "Eq", "a": Attr(V("f"), "is_function"), "b": L(1.0)},
                {"type": "Eq", "a": Attr(V("c"), "is_content"), "b": L(1.0)}]},
            "effects": [["set_attr", "c", "referent_bearer", 1.0],
                        ["add_edge", "c", "framed_by", "f"]]}
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_construction_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_construction_rule", "concern": list(keys),
            "form": "construction_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND the syntactic concern by composing a CONSTRUCTION RULE (graph-native, not a "
                    "string match): a FUNCTION word-form that PRECEDES a CONTENT word-form FRAMES it — I "
                    "mark the content token referent_bearer and add a framed_by edge. It runs in run_rules "
                    "over the token sequence; the decode trusts framed content-word bindings and lets 'the' "
                    "introduce a NEW referent, so word-order syntax constrains grounding beyond recurrence.")}


def _compose_distributional_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A DISTRIBUTIONAL FUNCTION/CONTENT SPLIT RULE — the self-build composer's grammar-induction
    path (twin of _compose_construction_rule). A FUNCTION word is a DISTRIBUTIONAL UNIVERSAL: high
    frequency AND context-independent (appears in many contexts). Author a graph-native Production over
    WordForm nodes: mark is_function=1 where the earned distributional attrs (freq_norm, ctx_entropy_norm,
    normalised 0..1) BOTH exceed the split (>= 0.5); content words are the rest. The statistics are earned
    from the token stream (adapter math); the agent authors the RULE that reads them and marks the split,
    which the syntactic construction then uses to FRAME content. Installed live; donkey=0."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Gte = lambda x, y: {"type": "Gte", "a": x, "b": y}
    rule = {"name": "distributional_function_split_" + "_".join(str(k) for k in keys),
            "match": [["w", "is_a", "WordForm"]],
            "where": {"type": "And", "items": [
                Gte(Attr(V("w"), "freq_norm"), L(0.5)),
                Gte(Attr(V("w"), "ctx_entropy_norm"), L(0.5))]},
            "effects": [["set_attr", "w", "is_function", 1.0]]}
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_distributional_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_distributional_rule", "concern": list(keys),
            "form": "distributional_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND 'what is a function word' distributionally (not a hand list): a graph rule "
                    "marks a WordForm is_function where it is BOTH high-frequency AND context-independent "
                    "(freq_norm & ctx_entropy_norm >= the split) — a distributional universal earned from "
                    "the token stream; content words are the rest. The syntactic construction then frames "
                    "content by these function words.")}


# ---------------------------------------------------------------------------
# ACTING-RULE PROVENANCE + THRESHOLD-SHIFT MECHANICS — the ACTING twin of the
# judge-variant embed path. The self-experiment loop's minted variant used to
# only ever modify how a dispatched child JUDGES a trial (a copy of
# judge_experiment_outcome_* with a shifted threshold); it never touched how
# the child ACTS, so no experiment could discover anything about behaviour.
# These helpers give the agent the MACHINERY to do that — mechanical
# reflection + structural substitution only; WHICH rule to vary and WHAT
# shift to apply stay the agent's own Term-picked decision (see
# `_compose_acting_variant` below, the 'gradient' branch's caller).
# ---------------------------------------------------------------------------
def _find_threshold_lits(node) -> list:
    """Mechanical recursive scan: collect every `{"type": "Lt"|"Gt", "b":
    {"type": "Lit", "value": <numeric>}}` node reachable inside `node` (a
    JSON-shaped Term/effects tree, export_rules()'s dialect) — the DECISION
    THRESHOLDS a rule's own effects compare against (e.g.
    hop_descend_gradient's four `Lt(delta, 0)` / `Gt(delta, 0)` direction
    gates). Pure structural read; no interpretation of what a threshold
    MEANS, only how many exist and where. Scoped to whatever subtree the
    caller passes — callers pass `rule["effects"]` (never `match`/`where`),
    so a shift can only change WHAT a rule decides, never WHETHER it fires."""
    out: list = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") in ("Lt", "Gt"):
                b = n.get("b")
                if isinstance(b, dict) and b.get("type") == "Lit":
                    v = b.get("value")
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _shift_rule_thresholds(rule: dict, shift: float, new_name: str) -> dict:
    """Build a THRESHOLD-SHIFTED COPY of `rule` (an export_rules()-dialect
    dict): every `Lt(x, Lit(c))` found in `rule['effects']` becomes
    `Lt(x, Lit(c - shift))`; every `Gt(x, Lit(c))` becomes
    `Gt(x, Lit(c + shift))` — the SAME threshold-shift shape
    `_compose_experiment_rule`'s judge-variant already uses (`Gt(rate,
    shift)` / `Lt(rate, -shift)`), generalised to whichever comparison nodes
    the CANDIDATE rule's own effects contain (found by `_find_threshold_lits`,
    effects-only). Deep-copies so the original export is untouched. Purely
    mechanical structural substitution — WHICH rule and WHAT shift are the
    caller's (the agent's Term-picked) decision; this only assembles JSON."""
    import copy as _copy
    out = _copy.deepcopy(rule)
    out["name"] = new_name
    for node in _find_threshold_lits(out.get("effects")):
        b = node["b"]
        b["value"] = (b["value"] - shift) if node["type"] == "Lt" else (b["value"] + shift)
    out.pop("active", None)          # add_rule installs fresh-active; not a valid add_rule field anyway
    out.pop("mutation_protected", None)  # this is a newly-authored successor, not the boot prior
    return out


def _rule_seed_map(sub) -> dict:
    """Mechanical, read-only: for every `SeedSummary{seed_id}` node (the
    per-seed provenance `substrate/boot_all.py.load_all_seeds` mints for
    every seed it loads — chosen over the narrower, reflective_faculty-only
    `Seed{id}` markers `_ensure_seed_chain` mints for its OWN four bootstrap
    seeds, since SeedSummary is what a fully-booted agent actually carries
    for the ~370 topic/world seeds an acting rule like hop_descend_gradient
    lives in), re-read that seed's OWN manifest (`manifest_for(sid)`, the
    same JSON file it was installed from) and map each of its declared rule
    names -> that seed's id. No seed manifest currently wires a Rule-Seed
    EDGE, so this is the provenance link `_ensure_acting_rule_provenance`
    needs for the adoption denylist (reflective_faculty.perform_adoptions) —
    a re-parse of files already on disk, not a re-installation, and not a
    decision (the mapping is exactly what each manifest already declares). A
    substrate with no SeedSummary nodes at all (a bare lexicon-only test
    fixture that `load_seed_manifest`'d a seed directly, bypassing
    `load_all_seeds`) yields an empty map — every rule reads as unknown
    provenance, which is the conservative, correct default for the denylist."""
    from substrate.seed_loader import manifest_for
    out: dict = {}
    for n in sub.nodes("SeedSummary"):
        sid = sub.node(n)["attrs"].get("seed_id")
        if not sid:
            continue
        try:
            d = manifest_for(sid)
        except Exception:
            continue
        for r in (d.get("rules") or []):
            if isinstance(r, dict) and r.get("name"):
                out.setdefault(r["name"], sid)
    return out


def _ensure_acting_rule_provenance(sub, native) -> None:
    """Idempotent: mirror every ACTIVE rule whose effects write `chosen_action`
    (the small, real set arc_run.py's per-frame loop actually reads off the
    graph — hop_descend_gradient / pursue_active_goal / ms_choose_expand,
    DISCOVERED by a structural scan of `export_rules()`, not a hand-picked
    name list — a rule not in that set that starts writing chosen_action
    later is picked up automatically, and one that stops isn't) as a
    graph-resident `RuleSummary{name, keywords_text, writes_chosen_action,
    shift_count, shiftable, rule_json, from_seed, skippable}` node — the
    ACTING twin of the provenance `substrate/boot_all.py` already gives
    every loaded SEED (`SeedSummary`). This is what lets the agent's own
    Terms (see `_compose_acting_variant` / `_compose_structural_variant`,
    and the graph-native `compose_experiment_mint_parametric` meta-rule in
    `seeds/composer_experiment_graph.json`) reason over WHICH acting rule to
    vary, by the SAME StringIndexOf overlap Argmax the seed-pick already
    uses — and what lets `perform_adoptions` enforce its denylist
    (SeedSummary.skippable of the rule's OWN `from_seed`; a rule whose
    `from_seed` is '' — no loaded seed declares it, e.g. a
    dynamically-authored variant rule — reads as unknown provenance, DENY).

    `skippable` (closes known_gaps['acting_rule_pick_unfiltered']): the
    ACTING twin of `boot_all.py:_mint_seed_summary`'s own `skippable` field —
    `0.0` iff `from_seed` is a KNOWN member of the dependency-closed frozen
    seed set (`domains.frozen_core.frozen_seed_ids_closed()`, the SAME set
    hole #1's `load_all_seeds` enforcement uses), else `1.0`. Deliberately
    does NOT also mark unknown/empty `from_seed` non-skippable here — that
    is `_rule_denylisted`'s job (the gate that actually matters: folding a
    variant into the PARENT), which already denies unknown provenance by
    default; a SELECTION-time pick that merely NAMES an unknown-provenance
    rule for a dispatched-child variant is not itself a write to the parent
    (see `domains/frozen_core.py`'s `edit_ops_variant_compose` grammar), so
    the selection-time filter's job is narrower: never let a KNOWN
    frozen-seed rule win the Argmax. Fails safe on a frozen-set computation
    error: every candidate reads `skippable=0.0` (nothing selectable) rather
    than risk a false negative.

    `shift_count`/`shiftable` are read straight off the rule's own exported
    structure via `_find_threshold_lits` (effects-only) — no interpretation
    of what a threshold MEANS, only how many exist; `rule_json` carries the
    exact structure a later compose call would need to shift, so the variant
    is built from what THIS rule actually says, not a re-derived guess."""
    have = {sub.node(n)["attrs"].get("name") for n in sub.nodes("RuleSummary")}
    try:
        rules = native.export_rules()
    except Exception:
        return
    import json as _json
    seed_map = None      # built lazily, only if there is a new rule to mirror
    frozen_ids = None    # ditto -- the dependency-closed frozen seed set
    frozen_computed = False
    for r in rules:
        if not isinstance(r, dict) or not r.get("active", True):
            continue
        name = r.get("name")
        if not name or name in have:
            continue
        effects = r.get("effects") or []
        writes_action = any(isinstance(e, list) and len(e) >= 3 and e[0] == "set_attr"
                            and e[2] == "chosen_action" for e in effects)
        if not writes_action:
            continue
        thresholds = _find_threshold_lits(effects)
        if seed_map is None:
            seed_map = _rule_seed_map(sub)
        if not frozen_computed:
            try:
                from domains.frozen_core import frozen_seed_ids_closed
                frozen_ids = frozen_seed_ids_closed()
            except Exception:
                frozen_ids = None    # fail safe -- see 'skippable' below
            frozen_computed = True
        from_seed = seed_map.get(name, "")
        skippable = 0.0 if (frozen_ids is None or from_seed in frozen_ids) else 1.0
        try:
            sub.add_node("RuleSummary", {
                "name": name,
                "keywords_text": name.replace("_", " "),
                "writes_chosen_action": 1.0,
                "shift_count": float(len(thresholds)),
                "shiftable": 1.0 if thresholds else 0.0,
                "rule_json": _json.dumps(r),
                "from_seed": from_seed,
                "skippable": skippable,
            })
        except Exception:
            continue
        have.add(name)


def _pick_acting_rule(agent, axis_preds) -> dict:
    """SHARED SELECTION: the agent's own Argmax over `RuleSummary` provenance
    (the SAME StringIndexOf-Sum overlap shape `_compose_experiment_rule`'s
    skip_seeds pick uses over `SeedSummary`) that picks WHICH chosen_action-
    writing rule the TRIGGERING axis's own residual predicates genuinely
    name. Factored out of `_compose_acting_variant` so `_compose_structural_
    variant` (the structural-edit twin) makes the SAME rule pick by the SAME
    machinery — only WHAT KIND of variant to build from the picked rule
    differs downstream. Returns `{'picked': node_or_None, 'name': str_or_None,
    'rule_json': dict_or_None, 'shift_count': float}` — an honest abstain
    (`picked: None`) when no RuleSummary genuinely overlaps.

    FROZEN-PROVENANCE EXCLUSION (closes known_gaps['acting_rule_pick_
    unfiltered']): mirrors `_compose_experiment_rule`'s own skip_seeds pick,
    which restricts its Argmax candidates to `skippable==1.0` SeedSummary
    nodes — this pick restricts its Argmax candidates to `skippable==1.0`
    RuleSummary nodes too (the field `_ensure_acting_rule_provenance` now
    stamps, computed from `domains.frozen_core.frozen_seed_ids_closed()` —
    the SAME dependency-closed frozen set hole #1's `load_all_seeds`
    enforcement uses, not a re-derived denylist): a rule whose OWN
    `from_seed` names a KNOWN frozen seed can no longer win this Argmax,
    even when its keywords_text would otherwise score highest. Unknown
    provenance (`from_seed == ''`) stays selectable HERE (mirrors the
    seed-pick's own semantics: `SeedSummary.skippable` is only ever False
    for seeds the manifest explicitly denylists) — `_rule_denylisted` is
    the gate that actually matters (folding a variant into the PARENT via
    `perform_adoptions`) and it already denies unknown provenance by
    default; a mere SELECTION naming an unknown-provenance rule is not a
    parent write (see `domains/frozen_core.py`'s `edit_ops_variant_compose`
    grammar).

    STRUCTURAL FALLBACK (RULE_SIGNATURE_PRODUCTION_WIRING_PREREG/RESULTS.md):
    the primary Argmax is UNCHANGED — the `keywords_text` (rule-name-derived)
    overlap tried first, exactly as before. Only when it genuinely abstains
    (no candidate scores > 0) does the SAME Sum/StringIndexOf/Argmax shape
    run a second time against `where_signature_json` (the rule's own
    `where`-clause structural signature, `domains.rule_signature`) instead
    of `keywords_text` — reading information a bare rule name can never
    carry (a concern's words naming something the rule's WHERE-clause reads
    but its name does not spell). Measured on the pre-registered 40-probe
    oracle: name-keyword alone is 0/12 on where-native probes (Class A) and
    12/12 on name-native probes (Class B); the combined fallback recovers
    Class A to 11/12 while leaving Class B's own 12/12 untouched, because
    the fallback is NEVER consulted when the primary Argmax already found a
    genuine (score > 0) match — see the RESULTS doc for the full row-level
    evidence this ordering is grounded in (every measured disagreement
    between the two signals was one method non-null-correct vs the OTHER
    abstaining, never one confidently wrong while the other was right).
    Both Argmaxes stay inside ONE evaluated Term — the fallback is a branch
    of the SAME Term tree, not a second Python-side decision."""
    sub0, native0, _ag0 = _resolve_agent(agent)
    _ensure_acting_rule_provenance(sub0, native0)
    from domains import rule_signature as _rsig
    _rsig.ensure_where_signature(sub0)

    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    Gte = lambda a, b: {"type": "Gte", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Filter = lambda src, var, pred: {"type": "Filter", "source": src, "var_name": var, "predicate": pred}
    Argmax = lambda src, var, val, default: {"type": "Argmax", "source": src, "var_name": var,
                                              "value": val, "default": default}
    NodesOfType = lambda t: {"type": "NodesOfType", "node_type": t}
    Sum = lambda src, var, val: {"type": "Sum", "source": src, "var_name": var, "value": val}
    StrIdx = lambda h, n: {"type": "StringIndexOf", "haystack": h, "needle": n}
    LetT = lambda nm, val, body: {"type": "Let", "name": nm, "value": val, "body": body}

    words = L(list(axis_preds))
    overlap = lambda node_t: Sum(words, "w",
        Ite(Gte(StrIdx(Attr(node_t, "keywords_text"), V("w")), L(0)), L(1), L(0)))
    struct_overlap = lambda node_t: Sum(words, "w",
        Ite(Gte(StrIdx(Attr(node_t, "where_signature_json"), V("w")), L(0)), L(1), L(0)))
    candidates = Filter(NodesOfType("RuleSummary"), "s",
        And(Eq(Attr(V("s"), "writes_chosen_action"), L(1.0)), Eq(Attr(V("s"), "skippable"), L(1.0))))
    best = Argmax(candidates, "s", overlap(V("s")), None)
    struct_best = Argmax(candidates, "s2", struct_overlap(V("s2")), None)
    struct_fallback = LetT("sbest", struct_best,
        Ite(And(Not(Eq(V("sbest"), L(None))), Gt(struct_overlap(V("sbest")), L(0.0))),
            V("sbest"), L(None)))
    pick_expr = LetT("best", best,
        Ite(And(Not(Eq(V("best"), L(None))), Gt(overlap(V("best")), L(0.0))),
            V("best"), struct_fallback))
    try:
        picked = native0.evaluate(pick_expr, {})
    except Exception:
        picked = None
    if picked is None or not sub0.has_node(picked):
        return {"picked": None, "name": None, "rule_json": None, "shift_count": 0.0}
    at_r = sub0.node(picked)["attrs"]
    import json as _json
    try:
        rule_json = _json.loads(at_r.get("rule_json") or "{}")
    except Exception:
        rule_json = None
    return {"picked": picked, "name": at_r.get("name"), "rule_json": rule_json,
            "shift_count": float(at_r.get("shift_count") or 0.0)}


def _compose_acting_variant(agent, keys, tag: str) -> dict[str, Any]:
    """THE ACTING TWIN of the judge-variant embed path: picks WHICH candidate
    chosen_action-writing rule the TRIGGERING axis's own residual predicates
    genuinely name (a held Argmax over `RuleSummary` provenance — the SAME
    StringIndexOf-Sum overlap shape `_compose_experiment_rule`'s skip_seeds
    pick uses over `SeedSummary`, abstaining to None on no genuine overlap,
    never a random pick), and builds a THRESHOLD-SHIFTED copy of it
    (`_shift_rule_thresholds`) — the shift read from the SAME axis's own
    residual size at compose time (a held `Count` Term, the acting twin of
    the judge-variant's `Count(...)/10.0` shift). UNSCALED here (unlike the
    judge-variant): that rate-threshold domain is continuous, but the
    grid-navigation domain's thresholds compare unit-integer cell distances
    (single presses, no sliding in this env) — dividing by 10 would be
    inert (a fractional shift can never cross an integer gate), so the raw
    predicate count is the right order of magnitude here; this asymmetry is
    a property of the ACTING rule's own domain, discovered, not designed.

    Returns `{'built': False, 'wall': ...}` — an HONEST NULL, not a
    fabricated variant — when the pick abstains (no RuleSummary's
    keywords_text genuinely overlaps this axis's residual) or the picked
    rule carries no shiftable threshold in its own effects at all (some
    acting rules, e.g. `pursue_active_goal`'s pure Argmax-of-displacement or
    `ms_choose_expand`'s ordering pick, have no numeric decision gate in
    their effects for this family of variant to shift — a real property of
    that rule, not a bug here)."""
    sub0, native0, _ag0 = _resolve_agent(agent)
    axis_preds = []
    for n0 in sub0.nodes("CapabilityAxis"):
        at0 = sub0.node(n0)["attrs"]
        if at0.get("induced") and list(at0.get("capability_keys") or []) == [str(k) for k in keys]:
            axis_preds = list(at0.get("residual_predicates") or [])
            break
    pick = _pick_acting_rule(agent, axis_preds)
    if pick["picked"] is None:
        return {"built": False, "wall": ("no RuleSummary genuinely overlaps this axis's residual "
                "predicates (abstained, like the seed-pick abstains on no overlap — not a random pick)")}
    shift_count = pick["shift_count"]
    if shift_count <= 0.0:
        return {"built": False, "wall": (f"the picked acting rule {pick['name']!r} carries no "
                "shiftable threshold in its own effects — a discovered null for THIS rule family, "
                "not fabricated (see _compose_acting_variant's docstring)")}
    cnt_term = {"type": "Count", "source": {"type": "Lit", "value": axis_preds}}
    try:
        shift = round(float(native0.evaluate(cnt_term, {})), 4)
    except Exception:
        shift = 0.0
    if shift <= 0.0:
        return {"built": False, "wall": "the axis's own residual carries no predicates to size a shift from"}
    if pick["rule_json"] is None:
        return {"built": False, "wall": "mirrored rule_json unreadable"}
    variant = _shift_rule_thresholds(pick["rule_json"], shift, pick["name"] + "_variant_" + tag)
    return {"built": True, "rule": variant, "removed_rule": pick["name"], "shift": shift,
            "shift_count": shift_count,
            "how": (f"I picked {pick['name']!r} (my own RuleSummary provenance Argmax found it genuinely "
                    f"named by this axis's residual, {axis_preds!r}) and built a threshold-shifted copy "
                    f"(shift={shift}, sized by Count over the same residual) — carried onto the dispatched "
                    f"copy via remove_rules=[{pick['name']!r}] + add_rules=[the variant], never installed "
                    f"locally: the parent tries the modification ON THE VARIANT, not on itself.")}


# ---------------------------------------------------------------------------
# CONVERSATION REPLY-RULE PROVENANCE + TARGETED ABLATION — the CONVERSATION
# twin of the acting-variant machinery above. A promoted conversation concern
# (reply_fix / knowledge / instruction routed to the conversation experiment
# world via the 'replay' relation) varies HOW THE CHILD REPLIES, not how it
# navigates: the vary is a targeted ABLATION (remove_rules=[the reply rule the
# axis's own residual genuinely names]) carried on the SeedDelta, dispatched to
# scripts/convo_child_run.py, which replays the recorded chat corpus and scores
# flagged-turn-fixed minus regressions. WHICH rule to ablate stays the agent's
# own Term-picked decision (the SAME RuleSummary-overlap Argmax shape
# `_pick_acting_rule` uses); these helpers are mechanical reflection only.
#
# v1 SHIPPED SCOPE (documented honestly): the vary is ablation-only —
# `remove_rules` + `ablation: 1.0` on the delta, NO replacement rule in
# `add_rules` (most reply rules carry no numeric threshold for the
# threshold-shift family to vary, so an ablation is the honest first variant
# kind for this family). The full trace→rule wiring (reading the exact rule
# that produced one flagged reply off a per-turn firing trace) does not exist
# yet — the pick is the residual-overlap Argmax over reply-rule provenance,
# steered by the human's own flag-note words (the same words that became the
# axis's residual_predicates).
# ---------------------------------------------------------------------------
def _reply_minting_effects(effects) -> bool:
    """Mechanical structural read: does this rule's effects list mint an agent
    outbound Message (`["add_node", var, "Message", {..., "from": "agent"}]`)?
    The conversation twin of `_ensure_acting_rule_provenance`'s
    writes-chosen_action scan — discovered structurally, never a hand list."""
    for e in (effects or []):
        if (isinstance(e, list) and len(e) >= 4 and e[0] == "add_node"
                and e[2] == "Message" and isinstance(e[3], dict)
                and e[3].get("from") == "agent"):
            return True
    return False


def _ensure_reply_rule_provenance(sub, native) -> None:
    """Idempotent: mirror every ACTIVE rule whose effects mint an agent reply
    Message (see `_reply_minting_effects` — a structural scan of
    `export_rules()`, the exact discovery shape `_ensure_acting_rule_provenance`
    uses for chosen_action writers) as a graph-resident `RuleSummary{name,
    keywords_text, writes_reply, rule_json, from_seed, skippable}` node. Same
    provenance semantics as the acting twin: `from_seed` from the seed
    manifests' own declared rule names (`_rule_seed_map`), `skippable` 0.0 iff
    that seed is in the dependency-closed frozen set (fails safe to 0.0 on a
    frozen-set computation error), unknown/empty `from_seed` stays selectable
    HERE but is denied at the adoption gate (`_rule_denylisted` denies unknown
    provenance by default). This is what lets a conversation experiment's
    ablation pick reason over WHICH reply rule — and what lets
    `perform_adoptions` enforce its denylist on the winner.

    A fully-booted agent ALREADY carries one RuleSummary per rule (the
    boot-time self-model mirror, `domains/self_model.py:ensure_self_model` —
    full field set, but NO `writes_reply` and NO `skippable`), so this
    follows the documented shared-population upgrade precedent (see
    ensure_self_model's own docstring): an existing summary is UPGRADED in
    place (`set_attr` the missing writes_reply / skippable / from_seed
    fields — its own from_seed is trusted when already present), a missing
    one is minted fresh. Idempotent either way."""
    existing: dict = {}
    for n in sub.nodes("RuleSummary"):
        at = sub.node(n)["attrs"]
        nm = at.get("name")
        if nm and nm not in existing:
            existing[nm] = n
    try:
        rules = native.export_rules()
    except Exception:
        return
    import json as _json
    seed_map = None
    frozen_ids = None
    frozen_computed = False
    for r in rules:
        if not isinstance(r, dict) or not r.get("active", True):
            continue
        name = r.get("name")
        if not name:
            continue
        if not _reply_minting_effects(r.get("effects")):
            continue
        node = existing.get(name)
        node_attrs = sub.node(node)["attrs"] if node is not None else {}
        if node is not None and node_attrs.get("writes_reply") == 1.0 \
                and node_attrs.get("skippable") is not None:
            continue   # already fully provenanced (idempotent re-call)
        if not frozen_computed:
            try:
                from domains.frozen_core import frozen_seed_ids_closed
                frozen_ids = frozen_seed_ids_closed()
            except Exception:
                frozen_ids = None    # fail safe -- same as _ensure_acting_rule_provenance
            frozen_computed = True
        from_seed = node_attrs.get("from_seed") or ""
        if not from_seed:
            if seed_map is None:
                seed_map = _rule_seed_map(sub)
            from_seed = seed_map.get(name, "")
        skippable = 0.0 if (frozen_ids is None or from_seed in frozen_ids) else 1.0
        if node is not None:
            try:
                sub.set_attr(node, "writes_reply", 1.0)
                if node_attrs.get("skippable") is None:
                    sub.set_attr(node, "skippable", skippable)
                if not node_attrs.get("from_seed") and from_seed:
                    sub.set_attr(node, "from_seed", from_seed)
            except Exception:
                pass
            continue
        thresholds = _find_threshold_lits(r.get("effects") or [])
        try:
            sub.add_node("RuleSummary", {
                "name": name,
                "keywords_text": name.replace("_", " "),
                "writes_chosen_action": 0.0,
                "writes_reply": 1.0,
                "shift_count": float(len(thresholds)),
                "shiftable": 1.0 if thresholds else 0.0,
                "rule_json": _json.dumps(r),
                "from_seed": from_seed,
                "skippable": skippable,
            })
        except Exception:
            continue


def _pick_reply_rule(agent, axis_preds) -> dict:
    """The conversation twin of `_pick_acting_rule`: the agent's own Argmax
    over `RuleSummary` provenance (the SAME StringIndexOf-Sum overlap Term
    shape), candidates restricted to `writes_reply == 1.0` AND
    `skippable == 1.0` (never a KNOWN frozen-seed rule; unknown provenance
    stays selectable here and is denied at the adoption gate — mirrored
    semantics, see `_pick_acting_rule`'s docstring). Honest abstain
    (`picked: None`) when no reply-rule summary genuinely overlaps the
    axis's residual predicates.

    STRUCTURAL FALLBACK — the SAME mechanism `_pick_acting_rule` now carries
    (see its docstring for the measured grounding): the primary
    `keywords_text` Argmax is unchanged and tried first; only on its own
    abstain does a second Argmax of the identical shape run against
    `where_signature_json`, inside the SAME evaluated Term."""
    sub0, native0, _ag0 = _resolve_agent(agent)
    _ensure_reply_rule_provenance(sub0, native0)
    from domains import rule_signature as _rsig
    _rsig.ensure_where_signature(sub0)

    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    Gte = lambda a, b: {"type": "Gte", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Filter = lambda src, var, pred: {"type": "Filter", "source": src, "var_name": var, "predicate": pred}
    Argmax = lambda src, var, val, default: {"type": "Argmax", "source": src, "var_name": var,
                                              "value": val, "default": default}
    NodesOfType = lambda t: {"type": "NodesOfType", "node_type": t}
    Sum = lambda src, var, val: {"type": "Sum", "source": src, "var_name": var, "value": val}
    StrIdx = lambda h, n: {"type": "StringIndexOf", "haystack": h, "needle": n}
    LetT = lambda nm, val, body: {"type": "Let", "name": nm, "value": val, "body": body}

    words = L(list(axis_preds))
    overlap = lambda node_t: Sum(words, "w",
        Ite(Gte(StrIdx(Attr(node_t, "keywords_text"), V("w")), L(0)), L(1), L(0)))
    struct_overlap = lambda node_t: Sum(words, "w",
        Ite(Gte(StrIdx(Attr(node_t, "where_signature_json"), V("w")), L(0)), L(1), L(0)))
    candidates = Filter(NodesOfType("RuleSummary"), "s",
        And(Eq(Attr(V("s"), "writes_reply"), L(1.0)), Eq(Attr(V("s"), "skippable"), L(1.0))))
    best = Argmax(candidates, "s", overlap(V("s")), None)
    struct_best = Argmax(candidates, "s2", struct_overlap(V("s2")), None)
    struct_fallback = LetT("sbest", struct_best,
        Ite(And(Not(Eq(V("sbest"), L(None))), Gt(struct_overlap(V("sbest")), L(0.0))),
            V("sbest"), L(None)))
    pick_expr = LetT("best", best,
        Ite(And(Not(Eq(V("best"), L(None))), Gt(overlap(V("best")), L(0.0))),
            V("best"), struct_fallback))
    try:
        picked = native0.evaluate(pick_expr, {})
    except Exception:
        picked = None
    if picked is None or not sub0.has_node(picked):
        return {"picked": None, "name": None}
    at_r = sub0.node(picked)["attrs"]
    return {"picked": picked, "name": at_r.get("name")}


def _compose_reply_ablation(agent, keys, tag: str) -> dict[str, Any]:
    """THE CONVERSATION TWIN of `_compose_acting_variant`: picks WHICH
    reply-minting rule the TRIGGERING axis's own residual predicates genuinely
    name (`_pick_reply_rule`'s held Argmax over reply-rule provenance) and
    builds a targeted ABLATION delta piece — `remove_rules=[that rule]`, no
    replacement (see the block comment above for why ablation is the v1
    variant kind for this family). The dispatched child replays the recorded
    conversation corpus WITHOUT that rule; the trial supports the hypothesis
    iff the flagged reply changes and nothing else does.

    Returns `{'built': False, 'wall': ...}` — an HONEST NULL — when the pick
    abstains (no reply-rule summary genuinely overlaps this axis's residual),
    never a fabricated target."""
    sub0, _native0, _ag0 = _resolve_agent(agent)
    axis_preds = []
    for n0 in sub0.nodes("CapabilityAxis"):
        at0 = sub0.node(n0)["attrs"]
        if at0.get("induced") and list(at0.get("capability_keys") or []) == [str(k) for k in keys]:
            axis_preds = list(at0.get("residual_predicates") or [])
            break
    pick = _pick_reply_rule(agent, axis_preds)
    if pick["picked"] is None:
        return {"built": False, "wall": ("no reply-minting RuleSummary genuinely overlaps this "
                "axis's residual predicates (abstained, like the acting-variant pick abstains "
                "on no overlap — not a random pick)")}
    return {"built": True, "removed_rule": pick["name"], "ablation": True,
            "how": (f"I picked {pick['name']!r} (my own reply-rule provenance Argmax found it "
                    f"genuinely named by this axis's residual, {axis_preds!r}) and authored a "
                    f"targeted ablation — carried onto the dispatched copy via "
                    f"remove_rules=[{pick['name']!r}], never removed locally: the parent tries "
                    f"losing the rule ON THE VARIANT, judged by replaying its own recorded "
                    f"conversation (flagged turn fixed, no regressions).")}


# ---------------------------------------------------------------------------
# THE VARIATION CHOICE AS GRAPH DATA (Wave 5) — `_compose_experiment_rule`'s
# variant chain (if conversation: reply_ablation / elif judge+structure:
# structural / elif judge+gradient: threshold_shift) is no longer a Python
# if/elif over grounded relation heads: it is VariationOp nodes + the held
# `variation_pick` Program (seeds/variation_ops.json), the EXACT
# composer_dispatch precedent — the Program returns the op NAME (Argmin by
# priority over the ops whose cue_head/also_head grounded and whose
# requires_kind matches the promoted concern's own SelfConcern kind, read via
# the StandingConcern the capability key names), and Python does a name-keyed
# registry lookup on the verdict (`_VARIATION_REGISTRY`). The agent editing a
# VariationOp node (priority / cue_head / requires_kind / route_pool) CHANGES
# which variation an experiment tries — the choice is self-repairable graph
# data (gated in tests/test_agent_authors_new_rule_migrated.py).
# ---------------------------------------------------------------------------
def _pick_variation_op(agent, heads, key: str):
    """Evaluate the seeded `variation_pick` Program over the grounded relation-
    head set + the concern's capability key (the StandingConcern name, through
    which the Program itself reads the concern's kind — a graph join inside the
    held Term, not a Python-read parameter). Returns the winning VariationOp's
    name, or None when no op's cues ground (matches the old chain's 'no branch
    fired'). Mechanical: load the seed (idempotent), evaluate, read the verdict."""
    sub0, native0, ag0 = _resolve_agent(agent)
    prog = _load_program(sub0, "variation_pick")
    if prog is None:
        # not held yet (bare fixture / minimal boot) — load the seed once. A
        # fully-booted agent already holds it via load_all_seeds; checking the
        # Program first avoids re-loading (and duplicating) the seed's nodes.
        try:
            _ensure_seed_chain(sub0, native0, ag0, ("variation_ops",))
        except Exception:
            return None
        prog = _load_program(sub0, "variation_pick")
    if prog is None:
        return None
    try:
        val = native0.evaluate(prog, {"heads": list(heads), "key": str(key or "")})
    except Exception:
        return None
    return val if isinstance(val, str) and val else None


def _char_bigrams(s: str) -> list[str]:
    """Mechanical string->list translation (no decision): the overlapping
    2-character windows of `s` (`"drop"` -> `["dr","ro","op"]`), falling back
    to the bare single-character list for a degenerate <2-char input (an
    empty bigram list would make `cue_route_pick` abstain on every 1-char
    verb, which is not this fix's target). RULE_SIGNATURE_PRODUCTION_WIRING_
    RESULTS.md's own measurement is why this replaces the old unigram
    `list(verb)` at this call site: SHAPE_AUDIT.md §2.2 names `chars:
    list(verb)` — a per-CHARACTER membership Sum — as "the worst instance
    found anywhere" because it scores by SET overlap, not sequence: `"drop"`
    and `"prod"` (anagrams) score byte-IDENTICAL against every candidate
    (verified live, see the RESULTS doc). A bigram is the cheapest unit that
    is sensitive to ADJACENCY, not just membership — `cue_route_pick`'s own
    held Program (seeds/variation_ops.json) does not change at all: it
    already sums `StringIndexOf(candidate.name, item) >= 0` over whatever
    list `chars` holds, so handing it bigrams instead of unigrams is a
    strictly more informative INPUT to the SAME graph-resident ranking, not
    a new decision — the ranking itself is still the agent's own held Term,
    never a Python if/elif."""
    if len(s) < 2:
        return list(s)
    return [s[i:i + 2] for i in range(len(s) - 1)]


def _compose_cue_variant(agent, keys, tag: str) -> dict[str, Any]:
    """THE CUE-SET-EDIT VARIATION FAMILY (Wave 5) — the genuinely-new-behaviour
    constructor. Wave 1b/2 made instruction verbs graph data (`Concept{name,
    instruction_route}` — adding such a Concept reroutes behaviour with ZERO
    rule edits, gated in test_instruction_gap_migrated), so a cue-set edit is
    itself a complete variation: variant = ADD a route Concept for the gap's
    unrouted verb, carried on the SeedDelta as `add_concepts` and applied by
    the child runners next to add_rules/remove_rules.

    WHICH verb: read mechanically off the promoted concern's own provenance
    (StandingConcern{name==capability key} <- promoted_to <- SelfConcern
    {kind:'instruction', predicate:<verb>} — the exact node the gap rule
    note_unhandled_instruction_gap filed). WHICH route: the agent's own held
    `cue_route_pick` Program (seeds/variation_ops.json): candidates are the
    route-carrying Concepts whose route is in the cue_set_edit VariationOp's
    own `route_pool` (agent-editable data: the routes whose seed rules claim
    any verb+content generically), scored by character-BIGRAM overlap with
    the gap verb (`_char_bigrams` — SEQUENCE-sensitive, unlike the old plain
    per-character overlap it replaces; see `_char_bigrams`'s own docstring
    for why) — a v1 held similarity, DOCUMENTED honestly: the score only
    orders proposals; the dispatched EXPERIMENT is the real validator of the
    pick (a wrong route replays as unchanged/regressed and judges
    inconclusive/refuted, never adopted). The Program abstains (None) when
    the verb is already routed (nothing to construct) or nothing scores —
    an honest null, never a fabricated cue."""
    sub0, native0, ag0 = _resolve_agent(agent)
    key = str(keys[0]) if keys else ""
    standing = None
    for n in sub0.nodes("StandingConcern"):
        if sub0.node(n)["attrs"].get("name") == key:
            standing = n
            break
    if standing is None:
        return {"built": False, "wall": ("no StandingConcern carries this capability key — "
                "a cue-set edit only exists for a promoted concern whose provenance names a verb")}
    verb = ""
    kind = ""
    for sc in sub0.nodes("SelfConcern"):
        try:
            promoted = standing in native0.neighbours(sc, "promoted_to")
        except Exception:
            promoted = False
        if promoted:
            at = sub0.node(sc)["attrs"]
            kind = str(at.get("kind") or "")
            verb = str(at.get("predicate") or "").strip().lower()
            if not verb:
                words = str(at.get("content") or "").split()
                verb = words[0].strip().lower() if words else ""
            break
    if kind != "instruction" or not verb:
        return {"built": False, "wall": (f"the promoting SelfConcern is not an instruction gap "
                f"naming a verb (kind={kind!r}, verb={verb!r}) — nothing to route")}
    prog = _load_program(sub0, "cue_route_pick")
    if prog is None:
        # same load-once discipline as _pick_variation_op above
        try:
            _ensure_seed_chain(sub0, native0, ag0, ("variation_ops",))
        except Exception:
            pass
        prog = _load_program(sub0, "cue_route_pick")
    if prog is None:
        return {"built": False, "wall": "the cue_route_pick Program is not held"}
    try:
        route = native0.evaluate(prog, {"verb": verb, "chars": _char_bigrams(verb)})
    except Exception as e:
        return {"built": False, "wall": f"route pick failed: {type(e).__name__}: {e}"}
    if not isinstance(route, str) or not route:
        return {"built": False, "wall": (f"the held route pick abstained for {verb!r} — either the "
                "verb is already routed (nothing to construct) or no pooled route Concept genuinely "
                "scores against it (honest abstain, not a random route)")}
    concept = {"type": "Concept", "attrs": {"name": verb, "instruction_route": route}}
    return {"built": True, "concept": concept, "verb": verb, "route": route,
            "how": (f"I read the unrouted verb {verb!r} off my own promoted instruction gap's "
                    f"provenance and my held cue_route_pick Program proposed the {route!r} route "
                    f"(character-overlap Argmax over the route Concepts in cue_set_edit's own "
                    f"route_pool — a proposal the dispatched replay experiment validates, never "
                    f"installs locally): the variant ADDS Concept{{name:{verb!r}, "
                    f"instruction_route:{route!r}}} on the dispatched copy via add_concepts.")}


# ---------------------------------------------------------------------------
# THE KNOB-EDIT VARIATION FAMILY (RESIDUAL-CLOSURE wave) — the held-NODE-ATTR
# twin of `_compose_acting_variant`. `threshold_shift` only reaches a
# threshold LITERAL embedded in a chosen_action-writing rule's own effects
# (RuleSummary provenance, ARC-shaped); many held beliefs the agent actually
# wants to tune (e.g. ApertureBudget's per-register reading thresholds,
# seeds/reading_aperture.json) are plain NODE ATTRS with no owning acting
# rule at all. `knob_edit` grounds via the `bound` RelationCue (a concern's
# own content words naming threshold/bound/scale/limit/constraint vocabulary
# — seeds/relation_vocabulary.json's `bounded` cue): 'bound' only ever
# grounds when the concern's content names threshold vocabulary, which IS
# the family's applicability condition. Priority 15 — below cue_set_edit
# (10), above reply_ablation (20) and both ARC families — see
# seeds/variation_ops.json's v1.1.0 description for the ordering argument;
# a concern that never grounds 'bound' leaves every other family's pick
# byte-identical.
# ---------------------------------------------------------------------------
_KNOB_NODE_TYPES = ("ApertureBudget",)   # the held threshold/knob families this v1 family
                                          # reaches; extend this tuple to widen it — never
                                          # hand-list an individual node, only a TYPE the
                                          # agent already holds many rows of.


def _compose_knob_variant(agent, keys, tag: str) -> dict[str, Any]:
    """WHICH knob: read the promoted concern's own content words (the same
    StandingConcern <- promoted_to <- SelfConcern provenance lookup
    `_compose_cue_variant` uses) and Argmax over every NUMERIC attr key on
    the default-register row of each type in `_KNOB_NODE_TYPES` by plain
    token overlap between the attr key's own '_'-split words and the content
    words — an honest abstain (`built: False`) at zero overlap, never a
    random pick; the EXPERIMENT (the dispatched replay) is the real
    validator, this only orders the proposal. The register defaults to the
    knob_edit VariationOp's own held `default_key_value` ('conversational' —
    the register every conversation-replay experiment runs under): a v1
    scope limit, documented honestly, not a hidden decision — multi-register
    disambiguation from content alone is a further capability, not this one.

    WHAT shift: the picked VariationOp's own held `knob_step` (agent-
    editable data) ADDED to the knob's current value — v1 direction is fixed
    positive (the knob gets HARDER to cross), matching the motivating case
    ('fires too eagerly' -> raise the bar); reading a 'too rarely'/'not
    enough' polarity out of the content to flip direction is a named
    residual, not built here (see the module description)."""
    sub0, native0, ag0 = _resolve_agent(agent)
    key = str(keys[0]) if keys else ""
    standing = None
    for n in sub0.nodes("StandingConcern"):
        if sub0.node(n)["attrs"].get("name") == key:
            standing = n
            break
    if standing is None:
        return {"built": False, "wall": ("no StandingConcern carries this capability key — "
                "a knob edit only exists for a promoted concern")}
    content = ""
    for sc in sub0.nodes("SelfConcern"):
        try:
            promoted = standing in native0.neighbours(sc, "promoted_to")
        except Exception:
            promoted = False
        if promoted:
            content = str(sub0.node(sc)["attrs"].get("content") or "")
            break
    words = [w.lower().strip(".,;:!?'\"") for w in content.split()]
    words = [w for w in words if len(w) > 2]
    if not words:
        return {"built": False, "wall": "the promoting SelfConcern carries no content to steer a knob pick"}

    op_at = None
    for n in sub0.nodes("VariationOp"):
        if sub0.node(n)["attrs"].get("name") == "knob_edit":
            op_at = sub0.node(n)["attrs"]
            break
    step = float((op_at or {}).get("knob_step") or 0.1)
    default_register = str((op_at or {}).get("default_key_value") or "conversational")

    best = None       # (overlap, node, attr_key, node_type)
    for ntype in _KNOB_NODE_TYPES:
        for n in sub0.nodes(ntype):
            at = sub0.node(n)["attrs"]
            if at.get("register") != default_register:
                continue
            for attr_key, val in at.items():
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    continue
                attr_words = [p for p in attr_key.split("_") if p]
                overlap = sum(1 for w in words if w in attr_words)
                # MINIMUM-SIGNAL GUARD: one shared word (usually the bare
                # 'threshold' every threshold-ish concern contains) does not
                # NAME a knob — it would pick an arbitrary row attr. Require
                # at least two distinct content words in the attr key's own
                # '_'-split words; below that, honest abstain (the concern
                # names threshold VOCABULARY but no held knob — the
                # rule-literal residual class, e.g. a divergence-recurrence
                # floor, lands here and must NOT hijack an unrelated knob).
                if overlap < 2:
                    continue
                if best is None or overlap > best[0]:
                    best = (overlap, n, attr_key, ntype)
    if best is None:
        return {"built": False, "wall": (f"no held knob (in {_KNOB_NODE_TYPES!r}, register="
                f"{default_register!r}) is genuinely named by the content words ({words!r}) — "
                "fewer than 2 words of any held attr key match; honest abstain, not a random "
                "pick (a rule-literal threshold outside the held node families lands here)")}
    _overlap, target, attr_key, ntype = best
    old_value = float(sub0.node(target)["attrs"].get(attr_key))
    new_value = round(old_value + step, 6)
    item = {"type": ntype, "key_attr": "register", "key_value": default_register,
            "attrs": {attr_key: new_value}}
    return {"built": True, "node_type": ntype, "key_attr": "register", "key_value": default_register,
            "attr": attr_key, "old_value": old_value, "new_value": new_value,
            "set_node_attrs_item": item,
            "how": (f"I read the promoted concern's own content words {words!r} and Argmaxed over the "
                    f"{default_register!r}-register {ntype} row's own attr keys by token overlap: "
                    f"{attr_key!r} genuinely names them. My held VariationOp.knob_step ({step}) sets the "
                    f"shift: {old_value} -> {new_value}, carried on the dispatched copy via "
                    "set_node_attrs, never applied locally — the parent tries the change ON THE VARIANT.")}


# ---------------------------------------------------------------------------
# THE RULE-LITERAL-EDIT VARIATION FAMILY (WHERE-CLAUSE-VARIATION wave) — the
# WHERE-CLAUSE twin of `threshold_shift`/`knob_edit`. `threshold_shift` only
# reaches a threshold literal in a chosen_action-writing rule's own EFFECTS
# (RuleSummary.writes_chosen_action provenance); `knob_edit` only reaches a
# threshold that is a plain held NODE ATTR with no owning rule at all. Many
# held beliefs are neither: a comprehension/salience rule's own WHERE-CLAUSE
# numeric literal (e.g. reading_aperture's `sentences_read >= 3.0`, salient_
# cache's `sc_mentions >= 3.0`) is a THRESHOLD baked into the rule's own
# match-guard, on a rule that writes neither chosen_action nor a reply and
# owns no separate knob node — `_compose_knob_variant`'s own abstain path
# names this exact residual class ("a rule-literal threshold outside the
# held node families lands here"). See seeds/variation_ops.json v1.2.0's
# description for the cue/priority/direction design in full.
# ---------------------------------------------------------------------------
def _find_where_lits(node) -> list:
    """The WHERE-CLAUSE twin of `_find_threshold_lits`: collect every
    `{"type": "Gte"|"Gt"|"Lte"|"Lt", "a": ..., "b": {"type":"Lit","value":
    <numeric>}}` node reachable inside `node` (a rule's own `where` — NEVER
    `match`/`effects`, so a shift here can only change WHETHER the rule
    fires as a threshold, never what it does once fired). Pure structural
    read, deterministic walk order (Python dict/list iteration order)."""
    out: list = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") in ("Gte", "Gt", "Lte", "Lt"):
                b = n.get("b")
                if isinstance(b, dict) and b.get("type") == "Lit":
                    v = b.get("value")
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _collect_vocab_tokens(node) -> set:
    """Mechanical structural read: every Attr key ('_'-split), NodesOfType
    type name, and short non-numeric Lit string value (space/'_'-split)
    reachable inside `node` (a single where-clause comparison subtree) —
    the vocabulary a content-word overlap Argmax scores a candidate literal
    against. No interpretation of what the vocabulary MEANS."""
    toks: set = set()

    def walk(n):
        if isinstance(n, dict):
            t = n.get("type")
            if t == "Attr":
                for w in str(n.get("key") or "").split("_"):
                    if w:
                        toks.add(w.lower())
            elif t == "NodesOfType":
                nt = str(n.get("node_type") or "")
                if nt:
                    toks.add(nt.lower())
            elif t == "Lit":
                v = n.get("value")
                if isinstance(v, str) and v:
                    for w in v.replace("_", " ").split():
                        toks.add(w.lower())
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return toks


# ENGINE GOTCHA (found live, WHERE-CLAUSE-VARIATION wave): a node's
# LIFECYCLE marker — the value an authored effect stamps at MINT time, e.g.
# AnalysisStage's `status: 'pending'` — is routinely advanced by OTHER,
# unrelated dispatch machinery within the SAME tick/converse() call
# (pending -> done, the la_dispatch_* executor pattern reading_aperture.
# json's own description names) BEFORE anything ever counts it. A witness
# that pins the literal value seen at COMPOSE time therefore goes
# permanently stale and undercounts a rule that genuinely fired — confirmed
# live: escalate_narrative_shape's AnalysisStage.status is 'pending' in the
# authored effect but already 'done' by the time a converse() call returns,
# so a witness keyed on status==pending reads 0 fires forever. 'status' is
# used this way (a fixed-at-mint value some LATER rule advances) across
# this graph's vocabulary generally (Experiment/Run/Goal/AnalysisStage/
# SelfConcern all carry a status lifecycle) — excluded from every witness's
# literal-match set for that reason, a property of this codebase's own
# naming convention, not a fact about any one rule.
_WITNESS_VOLATILE_ATTRS = frozenset({"status"})


def _rule_effect_witness(rule_json: dict):
    """Structural read of a rule's own EFFECTS: pick ONE mechanical witness
    the child double-pass can count fires of, WITHOUT interpreting what the
    rule means. Prefers a typed `add_node` mint carrying literal (non-Term)
    attrs — a brand-new node with those exact literal attrs IS a fire, and
    the literal set (e.g. `escalation_reason: 'narrative_shape'`) is usually
    far more SPECIFIC than the bare node type (many rules mint the same
    type for different reasons). Falls back to the first literal `set_attr`
    (node-type-agnostic: count nodes ANYWHERE holding that attr==value).
    Both skip `_WITNESS_VOLATILE_ATTRS` (see above) — a typed candidate
    whose ONLY literal attrs are volatile falls through to the next add_node
    effect (or the set_attr fallback) rather than picking an unreliable
    witness. Returns None when the rule's effects carry no literal witness
    at all (every effect is Term-computed or purely volatile) — an honest
    null; the double-pass then reports regressions only, no witness delta."""
    effects = rule_json.get("effects") or []

    def literal_attrs(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if k in _WITNESS_VOLATILE_ATTRS:
                continue
            if isinstance(v, (int, float, str, bool)) and not isinstance(v, dict):
                out[k] = v
        return out

    for e in effects:
        if isinstance(e, list) and len(e) >= 4 and e[0] == "add_node" and isinstance(e[3], dict):
            lits = literal_attrs(e[3])
            if lits:
                return {"kind": "typed", "node_type": e[2], "attrs": lits}
    for e in effects:
        if isinstance(e, list) and len(e) >= 4 and e[0] == "set_attr":
            k, v = e[2], e[3]
            if k in _WITNESS_VOLATILE_ATTRS:
                continue
            if isinstance(v, (int, float, str, bool)) and not isinstance(v, dict):
                return {"kind": "attr_any", "attr": k, "value": v}
    return None


def _shift_one_where_literal(rule: dict, cand_index: int, step: float, direction: str,
                             new_name: str):
    """Build a WHERE-LITERAL-SHIFTED COPY of `rule`: the ONE where-clause
    comparison at `cand_index` (in `_find_where_lits`'s discovery order) has
    its own Lit operand shifted by `step`, signed so the comparison fires
    MORE OFTEN when `direction=='increase_fires'` and LESS OFTEN when
    `direction=='decrease_fires'` — a `>=`/`>` literal is a FLOOR (lower it
    to fire more, raise it to fire less); a `<=`/`<` literal is a CEILING
    (the opposite). Deep-copies so the original export is untouched; returns
    None if `cand_index` is out of range (an honest structural failure, not
    a silent partial edit)."""
    import copy as _copy
    out = _copy.deepcopy(rule)
    cands = _find_where_lits(out.get("where"))
    if cand_index < 0 or cand_index >= len(cands):
        return None
    node = cands[cand_index]
    b = node["b"]
    is_floor = node["type"] in ("Gte", "Gt")
    lower = (direction == "increase_fires") == is_floor
    b["value"] = (b["value"] - step) if lower else (b["value"] + step)
    out["name"] = new_name
    out.pop("active", None)
    return out


def _ensure_where_literal_rule_provenance(sub, native) -> None:
    """Idempotent: mirror EVERY active rule that carries >=1 numeric where-
    clause comparison (`_find_where_lits`, `where`-only) as a graph-resident
    `RuleSummary{name, keywords_text, writes_where_literal, where_shift_
    count, where_shiftable, rule_json, from_seed, skippable}` node — the
    WHERE-CLAUSE twin of `_ensure_acting_rule_provenance`/`_ensure_reply_
    rule_provenance`. Same upgrade-in-place idempotence: a fully-booted
    agent already carries one base RuleSummary per rule (domains/self_model.
    py's boot-time mirror); this UPGRADES it in place (set_attr the missing
    fields) rather than minting a duplicate, exactly like the reply twin.
    Same provenance semantics: `from_seed` from the seed manifests' own
    declared rule names (`_rule_seed_map`), `skippable` 0.0 iff that seed is
    in the dependency-closed frozen set (fails safe to 0.0 on a frozen-set
    computation error), unknown/empty `from_seed` stays selectable HERE but
    is denied at the adoption gate (`_rule_denylisted`)."""
    existing: dict = {}
    for n in sub.nodes("RuleSummary"):
        at = sub.node(n)["attrs"]
        nm = at.get("name")
        if nm and nm not in existing:
            existing[nm] = n
    try:
        rules = native.export_rules()
    except Exception:
        return
    import json as _json
    seed_map = None
    frozen_ids = None
    frozen_computed = False
    for r in rules:
        if not isinstance(r, dict) or not r.get("active", True):
            continue
        name = r.get("name")
        if not name:
            continue
        cands = _find_where_lits(r.get("where"))
        if not cands:
            continue
        node = existing.get(name)
        node_attrs = sub.node(node)["attrs"] if node is not None else {}
        if node is not None and node_attrs.get("writes_where_literal") == 1.0 \
                and node_attrs.get("skippable") is not None:
            continue   # already fully provenanced (idempotent re-call)
        if not frozen_computed:
            try:
                from domains.frozen_core import frozen_seed_ids_closed
                frozen_ids = frozen_seed_ids_closed()
            except Exception:
                frozen_ids = None    # fail safe — same as the acting/reply twins
            frozen_computed = True
        from_seed = node_attrs.get("from_seed") or ""
        if not from_seed:
            if seed_map is None:
                seed_map = _rule_seed_map(sub)
            from_seed = seed_map.get(name, "")
        skippable = 0.0 if (frozen_ids is None or from_seed in frozen_ids) else 1.0
        if node is not None:
            try:
                sub.set_attr(node, "writes_where_literal", 1.0)
                sub.set_attr(node, "where_shift_count", float(len(cands)))
                sub.set_attr(node, "where_shiftable", 1.0)
                if not node_attrs.get("rule_json"):
                    sub.set_attr(node, "rule_json", _json.dumps(r))
                if node_attrs.get("skippable") is None:
                    sub.set_attr(node, "skippable", skippable)
                if not node_attrs.get("from_seed") and from_seed:
                    sub.set_attr(node, "from_seed", from_seed)
            except Exception:
                pass
            continue
        try:
            sub.add_node("RuleSummary", {
                "name": name,
                "keywords_text": name.replace("_", " "),
                "writes_chosen_action": 0.0,
                "writes_reply": 0.0,
                "writes_where_literal": 1.0,
                "where_shift_count": float(len(cands)),
                "where_shiftable": 1.0,
                "rule_json": _json.dumps(r),
                "from_seed": from_seed,
                "skippable": skippable,
            })
        except Exception:
            continue


def _compose_rule_literal_variant(agent, keys, tag: str) -> dict[str, Any]:
    """WHICH rule + WHICH literal: Argmax over EVERY (RuleSummary, where-
    literal-candidate) pair — restricted to `writes_where_literal==1.0` AND
    `skippable==1.0` rows — by token overlap between the promoted concern's
    own content words and that ONE candidate's own comparison-subtree
    vocabulary (`_collect_vocab_tokens`), same >=2-word minimum-signal guard
    `_compose_knob_variant` uses (a bare 'threshold' mention does not NAME a
    literal — it would pick an arbitrary comparison). Honest abstain
    (`built: False`) at zero qualifying overlap, never a random pick.

    WHICH DIRECTION: `direction_lexicon_more`/`direction_lexicon_fewer`
    (this family's own VariationOp attrs, agent-editable) scored against the
    SAME content words — 'fires too rarely/never' -> increase_fires (lower
    a floor / raise a ceiling); 'fires too eagerly/often' -> decrease_fires
    (the opposite). A tied or zero-zero score abstains (no random polarity).

    STRUCTURAL FALLBACK (MAC_FAC_A5_A6_PREREG/RESULTS.md, A6): the primary
    scorer above is already a structural read in ONE sense (Attr keys /
    NodesOfType names / Lit strings, not a name-derived prose blurb) — but it
    is scoped to exactly the ONE `_find_where_lits` candidate node being
    tried, and never sees that rule's OTHER, sibling `And`-items (a rule
    routinely carries non-numeric-literal `Eq`/`Not`/`Exists` guard
    conditions alongside its numeric threshold(s) — e.g.
    `escalate_narrative_shape`'s `spine_stage`/`reading_report` guards,
    reachable from NEITHER of its two where-lit candidates). `RuleSummary.
    where_signature_json` (`domains.rule_signature`, minted for this SAME
    `writes_where_literal` pool — `ensure_where_signature` keys only on
    `rule_json` being present, not on `writes_chosen_action`/`writes_reply`,
    so no new signature machinery is needed) covers the WHOLE `where` clause,
    siblings included. The primary is UNCHANGED and tried first; only when it
    genuinely abstains SYSTEM-WIDE (no (rule, candidate) pair anywhere scores
    >= 2) does a two-tier fallback run: (1) score each CANDIDATE RULE by
    substring overlap between the content words and its own
    `where_signature_json` blob (the SAME >=2-word floor, the SAME substring
    semantics A1/A2's own `where_signature_json` fallback uses); (2) within
    the structurally-picked rule, choose WHICH `_find_where_lits` candidate
    via the SAME local vocab scorer, WITHOUT the 2-word floor (already
    discharged at the rule level) — ties broken by first discovery order,
    matching the primary's own tie convention."""
    sub0, native0, ag0 = _resolve_agent(agent)
    key = str(keys[0]) if keys else ""
    standing = None
    for n in sub0.nodes("StandingConcern"):
        if sub0.node(n)["attrs"].get("name") == key:
            standing = n
            break
    if standing is None:
        return {"built": False, "wall": ("no StandingConcern carries this capability key — "
                "a rule-literal edit only exists for a promoted concern")}
    content = ""
    for sc in sub0.nodes("SelfConcern"):
        try:
            promoted = standing in native0.neighbours(sc, "promoted_to")
        except Exception:
            promoted = False
        if promoted:
            content = str(sub0.node(sc)["attrs"].get("content") or "")
            break
    words = [w.lower().strip(".,;:!?'\"") for w in content.split()]
    words = [w for w in words if len(w) > 2]
    if not words:
        return {"built": False, "wall": "the promoting SelfConcern carries no content to steer a literal pick"}

    op_at = None
    for n in sub0.nodes("VariationOp"):
        if sub0.node(n)["attrs"].get("name") == "rule_literal_edit":
            op_at = sub0.node(n)["attrs"]
            break
    step = float((op_at or {}).get("literal_step") or 1.0)

    import json as _json
    _ensure_where_literal_rule_provenance(sub0, native0)
    candidate_rows = []   # [(rule_name, rule_json)] -- the pool, gathered once
    best = None   # (overlap, rule_name, rule_json, cand_index, cand_node)
    for n in sub0.nodes("RuleSummary"):
        at = sub0.node(n)["attrs"]
        if at.get("writes_where_literal") != 1.0 or at.get("skippable") != 1.0:
            continue
        try:
            rule_json = _json.loads(at.get("rule_json") or "{}")
        except Exception:
            continue
        candidate_rows.append((at.get("name"), rule_json))
        cands = _find_where_lits(rule_json.get("where"))
        for i, cand in enumerate(cands):
            vocab = _collect_vocab_tokens(cand)
            overlap = sum(1 for w in words if w in vocab)
            if overlap < 2:
                continue
            if best is None or overlap > best[0]:
                best = (overlap, at.get("name"), rule_json, i, cand)
    fallback_used = False
    if best is None:
        # STRUCTURAL FALLBACK (see docstring): only reached when the LOCAL
        # per-candidate vocab scorer genuinely abstains system-wide. Tier 1:
        # pick the RULE whose FULL where-clause signature is genuinely named.
        from domains import rule_signature as _rsig
        _rsig.ensure_where_signature(sub0)
        # where_signature_json may have just been minted -- re-read fresh.
        sig_by_name = {}
        for n in sub0.nodes("RuleSummary"):
            at = sub0.node(n)["attrs"]
            if at.get("writes_where_literal") == 1.0 and at.get("skippable") == 1.0:
                sig_by_name[at.get("name")] = at.get("where_signature_json") or ""
        struct_best = None   # (overlap, rule_name, rule_json)
        for rule_name0, rule_json0 in candidate_rows:
            sig_json = (sig_by_name.get(rule_name0) or "").lower()
            if not sig_json:
                continue
            overlap = sum(1 for w in words if w in sig_json)
            if overlap < 2:
                continue
            if struct_best is None or overlap > struct_best[0]:
                struct_best = (overlap, rule_name0, rule_json0)
        if struct_best is not None:
            _s_overlap, s_rule_name, s_rule_json = struct_best
            # Tier 2: within the structurally-picked rule, choose WHICH
            # where-lit candidate by the SAME local vocab scorer, no floor
            # (the floor's job was already discharged at the rule level).
            cands = _find_where_lits(s_rule_json.get("where"))
            local_best = None   # (overlap, cand_index, cand_node)
            for i, cand in enumerate(cands):
                vocab = _collect_vocab_tokens(cand)
                overlap = sum(1 for w in words if w in vocab)
                if local_best is None or overlap > local_best[0]:
                    local_best = (overlap, i, cand)
            if local_best is not None:
                _l_overlap, l_idx, l_cand = local_best
                best = (_s_overlap, s_rule_name, s_rule_json, l_idx, l_cand)
                fallback_used = True
    if best is None:
        return {"built": False, "wall": (f"no held rule's where-clause literal is genuinely "
                f"named by the content words ({words!r}) — fewer than 2 words of any candidate's "
                "own comparison vocabulary OR any rule's own full where-signature match; honest "
                "abstain, not a random pick")}
    _overlap, rule_name, rule_json, cand_idx, cand_node = best

    more_words = set(str(w).lower() for w in ((op_at or {}).get("direction_lexicon_more") or []))
    fewer_words = set(str(w).lower() for w in ((op_at or {}).get("direction_lexicon_fewer") or []))
    more_score = sum(1 for w in words if w in more_words)
    fewer_score = sum(1 for w in words if w in fewer_words)
    if more_score == fewer_score:
        return {"built": False, "wall": (f"ambiguous direction for {rule_name!r}'s picked literal "
                f"(more={more_score}, fewer={fewer_score}) — honest abstain, no random polarity")}
    direction = "increase_fires" if more_score > fewer_score else "decrease_fires"

    old_value = cand_node["b"]["value"]
    new_name = rule_name + "_variant_" + tag
    variant = _shift_one_where_literal(rule_json, cand_idx, step, direction, new_name)
    if variant is None:
        return {"built": False, "wall": "literal shift failed structurally (candidate index stale)"}
    new_value = _find_where_lits(variant.get("where"))[cand_idx]["b"]["value"]
    witness = _rule_effect_witness(rule_json)
    pick_desc = ("its FULL where-signature (the local per-literal vocabulary abstained system-wide)"
                 if fallback_used else "comparison-subtree vocabulary overlap")
    return {"built": True, "rule": variant, "removed_rule": rule_name,
            "old_value": old_value, "new_value": new_value, "direction": direction,
            "witness": witness, "fallback_used": fallback_used,
            "how": (f"I read the promoted concern's own content words {words!r}, Argmaxed over every "
                    f"held rule's where-clause literal by {pick_desc}: "
                    f"{rule_name!r}'s literal genuinely wins, and the direction lexicon reads "
                    f"{direction!r}. My held VariationOp.literal_step ({step}) sets the shift: "
                    f"{old_value} -> {new_value}, carried on the dispatched copy via remove_rules="
                    f"[{rule_name!r}] + add_rules=[{new_name!r}] — the parent tries the change ON "
                    "THE VARIANT, never locally.")}


# ---------------------------------------------------------------------------
# THE COMPOSER-CAPABILITY WAVE — the composer's own self-diagnosed shortfall
# ("you cannot author a rule that feeds a recorded datum back into a held
# belief", filed 2026-07-11 in the residual-closure wave) closed by two new
# variation families, both ADD-ONLY (no rule/attr removed — see
# seeds/variation_ops.json v1.3.0's description for the full design).
# ---------------------------------------------------------------------------
_DATUM_FEEDBACK_CANDIDATES = (
    {"node_type": "Interlocutor", "datum_attr": "self_report_contradiction_count",
     "belief_attr": "self_report_reliability",
     "keywords_text": ("reliability trust trustworthiness track record contradiction self "
                        "report belief calibrate recalibrate recalibration miscalibrated")},
)


def _compose_datum_feedback_rule(agent, keys, tag: str) -> dict[str, Any]:
    """WHICH (datum, belief) pair: Argmax over the held `_DATUM_FEEDBACK_CANDIDATES`
    table (the composer-capability twin of `_KNOB_NODE_TYPES`'s own held-table
    shape) by token overlap between the promoted concern's own content words
    and each candidate row's `keywords_text` — the SAME >=2-word minimum-
    signal guard every other family in this module uses, honest abstain
    below it. The picked row names a COUNTER attr (a recorded datum — e.g.
    the interlocutor model's own `self_report_contradiction_count`, see
    `world_adapter._record_interlocutor_correction`) and a BELIEF attr (a
    held, revisable belief — `self_report_reliability`) on the SAME node
    type.

    STRUCTURAL FALLBACK (MAC_FAC_A5_A6_PREREG/RESULTS.md, A5): `keywords_text`
    is a hand-authored DESCRIPTIVE blurb — the row's MAC layer, exactly like
    A1/A2's rule-name-derived bag. Each row also carries its own real
    operational identity (FAC): `node_type`/`datum_attr`/`belief_attr`, the
    literal graph node-type and attribute names the authored rule actually
    reads/writes. The primary Argmax is UNCHANGED and tried first; only when
    it genuinely abstains (no row scores >= 2) does the SAME Sum-of-membership
    shape run a second time against `" ".join([node_type, datum_attr,
    belief_attr]).replace("_", " ")` instead of `keywords_text` — recovering
    a concern that names the attribute directly (e.g. 'count') rather than
    the prose blurb that was hand-picked to evoke it. Honest scope limit
    (registered before this was built, not discovered after): the real table
    holds exactly ONE row today, so this fallback is measured to close a real
    false-abstain gap, not to discriminate correctly among competing rows —
    see the RESULTS doc's own honest-limits section.

    THE AUTHORED RULE: matches every party the agent models (`agent
    -has_interlocutor-> party`, the boundary edge
    `interlocutor_model._ensure_party_anchor` mechanically maintains —
    deliberately its OWN edge type, not a reuse of senses/models/acts_on,
    whose counts are load-bearing theorem invariants elsewhere), guarded by
    an EPOCH marker (`<datum_attr>_feedback_applied_at` != the CURRENT datum
    value — fires again only once the datum has genuinely changed since the
    last time this rule applied, the engine-gotcha-safe twin of a
    mint-once-per-VALUE guard for a counter that keeps moving rather than a
    boolean flag), and ADJUSTS the belief by this VariationOp's own held
    `datum_step`, clamped to [`belief_floor`, `belief_ceil`] (both
    agent-editable VariationOp data — the reading_norms/ApertureBudget clamp
    idiom). v1 direction is FIXED (the belief moves DOWN as the datum
    accrues), matching the motivating case (a contradiction datum eroding
    trust) — the SAME documented v1 scope limit `_compose_knob_variant`'s
    own fixed '+' direction carries; reading a symmetric up/down polarity
    out of the concern's own wording is a named residual, not built here.
    The rule ALSO stamps `<belief_attr>_source = 'learned'` so
    `interlocutor_model.effective_reliability` reads the now-tracked belief
    in preference to the shape/track-record blend for THIS party (mirrors
    the existing 'creator_origin' branch exactly, additive — a party no
    authored rule ever touches stays byte-unchanged)."""
    sub0, native0, ag0 = _resolve_agent(agent)
    key = str(keys[0]) if keys else ""
    standing = None
    for n in sub0.nodes("StandingConcern"):
        if sub0.node(n)["attrs"].get("name") == key:
            standing = n
            break
    if standing is None:
        return {"built": False, "wall": ("no StandingConcern carries this capability key — "
                "a datum-feedback rule only exists for a promoted concern")}
    content = ""
    for sc in sub0.nodes("SelfConcern"):
        try:
            promoted = standing in native0.neighbours(sc, "promoted_to")
        except Exception:
            promoted = False
        if promoted:
            content = str(sub0.node(sc)["attrs"].get("content") or "")
            break
    words = [w.lower().strip(".,;:!?'\"") for w in content.split()]
    words = [w for w in words if len(w) > 2]
    if not words:
        return {"built": False, "wall": "the promoting SelfConcern carries no content to steer a datum-feedback pick"}

    op_at = None
    for n in sub0.nodes("VariationOp"):
        if sub0.node(n)["attrs"].get("name") == "datum_feedback_rule":
            op_at = sub0.node(n)["attrs"]
            break
    step = float((op_at or {}).get("datum_step") or 0.1)
    floor = float((op_at or {}).get("belief_floor") or 0.05)
    ceil = float((op_at or {}).get("belief_ceil") or 0.95)

    best = None   # (overlap, row)
    for row in _DATUM_FEEDBACK_CANDIDATES:
        row_words = row["keywords_text"].split()
        overlap = sum(1 for w in words if w in row_words)
        if overlap < 2:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, row)
    fallback_used = False
    if best is None:
        # STRUCTURAL FALLBACK (see docstring): only reached when the prose
        # blurb genuinely abstains. Scores each row by its own real
        # operational identity (node_type/datum_attr/belief_attr) instead of
        # the hand-authored keywords_text bag.
        struct_best = None   # (overlap, row)
        for row in _DATUM_FEEDBACK_CANDIDATES:
            struct_words = (row["node_type"] + " " + row["datum_attr"] + " "
                            + row["belief_attr"]).replace("_", " ").lower().split()
            overlap = sum(1 for w in words if w in struct_words)
            if overlap < 2:
                continue
            if struct_best is None or overlap > struct_best[0]:
                struct_best = (overlap, row)
        if struct_best is not None:
            best = struct_best
            fallback_used = True
    if best is None:
        return {"built": False, "wall": (f"no held datum/belief pair genuinely named by the content "
                f"words ({words!r}) — fewer than 2 words of any candidate row's own keywords_text OR "
                "its structural (node_type/datum_attr/belief_attr) identity match; honest abstain, "
                "not a random pick")}
    _overlap, row = best
    node_type = row["node_type"]
    datum_attr = row["datum_attr"]
    belief_attr = row["belief_attr"]
    belief_source_attr = belief_attr + "_source"
    applied_marker = datum_attr + "_feedback_applied_at"

    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Lt = lambda a, b: {"type": "Lt", "a": a, "b": b}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Plus = lambda *xs: {"type": "Plus", "items": list(xs)}

    cur_belief = Ite(Eq(Attr(V("party"), belief_attr), L(None)), L(0.5), Attr(V("party"), belief_attr))
    raw = Plus(cur_belief, L(-step))
    clamped = Ite(Lt(raw, L(floor)), L(floor), Ite(Gt(raw, L(ceil)), L(ceil), raw))
    rule_name = "datum_feedback_" + tag

    rule = {
        "name": rule_name,
        "match": [["agent", "has_interlocutor", "party"]],
        "where": And(
            Not(Eq(Attr(V("party"), datum_attr), L(None))),
            Not(Eq(Attr(V("party"), datum_attr), Attr(V("party"), applied_marker))),
        ),
        "effects": [
            ["set_attr", "party", belief_attr, {"__term__": clamped}],
            ["set_attr", "party", belief_source_attr, "learned"],
            ["set_attr", "party", applied_marker, {"__term__": Attr(V("party"), datum_attr)}],
        ],
    }
    pick_desc = ("its own STRUCTURAL identity (node_type/datum_attr/belief_attr) — the prose "
                 "keywords_text abstained" if fallback_used else "its own keywords_text prose")
    return {"built": True, "rule": rule, "node_type": node_type, "datum_attr": datum_attr,
            "belief_attr": belief_attr, "step": step, "floor": floor, "ceil": ceil,
            "fallback_used": fallback_used,
            "how": (f"I read the promoted concern's own content words {words!r} and Argmaxed over the "
                    f"held datum/belief table by {pick_desc}: ({datum_attr!r}, {belief_attr!r}) on "
                    f"{node_type} genuinely names them. I authored a NEW rule that matches every "
                    f"{node_type} I model, fires once per genuine change of {datum_attr!r} (an epoch "
                    f"marker, not a boolean flag), and moves {belief_attr!r} down by my held "
                    f"VariationOp.datum_step ({step}), clamped to [{floor}, {ceil}] — carried on the "
                    "dispatched copy via add_rules, tried on the VARIANT before ever touching myself.")}


_SHAPE_MINT_DIMS = ("register", "cadence", "style", "affect")
_SHAPE_MINT_KEYWORDS = ("persona profile personas profiles unclassified poor fit shape mint "
                        "interlocutor style signature calibrate")


def _compose_shape_mint(agent, keys, tag: str) -> dict[str, Any]:
    """WHICH concern: the promoted concern's own content must genuinely name
    a SHAPE/PROFILE concern (>=2-word overlap against `_SHAPE_MINT_KEYWORDS`
    — the SAME honest-abstain minimum-signal discipline every other family
    in this module uses). WHICH party: NOT a content-word pick (a person's
    identity is not named in the report's own words the way a rule/knob is)
    — a structural Argmax over `interlocutor_model._record_shape_fit`'s own
    mechanical datum, picking the party carrying the LARGEST `poor_fit_streak`
    (a party whose accumulated features currently fit no held
    InterlocutorShape).

    THE MINTED NODE: a NEW `InterlocutorShape{name, sig_register, sig_cadence,
    sig_style, sig_affect, self_report_reliability_prior, reliability_interval,
    expected_domains, evidence_decay_k, tom_capacity_prior}` built from the
    party's own DOMINANT accumulated features
    (`interlocutor_model._dominant_features` — the SAME plurality read
    `decode_shape`'s own fit scoring uses), so the new shape genuinely
    generalises what this party has SHOWN, not an invention. Priors start
    WIDE — copied from the held codebook's own `default_uncalibrated` entry
    (data, never re-derived) — since this is a freshly-minted shape with no
    track record of its own yet: the sd-loop mint (a residual becomes a new
    CapabilityAxis quantum) applied to person-shapes (a residual party
    becomes a new codebook entry). Rides the EXISTING `add_concepts` channel
    (already generalized to typed nodes, commit 03630c0e27) — no new
    SeedDelta channel needed."""
    sub0, native0, ag0 = _resolve_agent(agent)
    key = str(keys[0]) if keys else ""
    standing = None
    for n in sub0.nodes("StandingConcern"):
        if sub0.node(n)["attrs"].get("name") == key:
            standing = n
            break
    if standing is None:
        return {"built": False, "wall": ("no StandingConcern carries this capability key — "
                "a shape mint only exists for a promoted concern")}
    content = ""
    for sc in sub0.nodes("SelfConcern"):
        try:
            promoted = standing in native0.neighbours(sc, "promoted_to")
        except Exception:
            promoted = False
        if promoted:
            content = str(sub0.node(sc)["attrs"].get("content") or "")
            break
    words = [w.lower().strip(".,;:!?'\"") for w in content.split()]
    words = [w for w in words if len(w) > 2]
    if not words:
        return {"built": False, "wall": "the promoting SelfConcern carries no content to steer a shape-mint pick"}
    kw_words = _SHAPE_MINT_KEYWORDS.split()
    overlap = sum(1 for w in words if w in kw_words)
    if overlap < 2:
        return {"built": False, "wall": (f"the content words ({words!r}) do not genuinely name a "
                "shape/profile concern (fewer than 2 held keyword matches) — honest abstain, not a "
                "random pick")}

    from domains import interlocutor_model as _im
    best = None    # (streak, party)
    for n in sub0.nodes("Interlocutor"):
        at = sub0.node(n)["attrs"]
        streak = int(at.get("poor_fit_streak", 0) or 0)
        if streak <= 0:
            continue
        if best is None or streak > best[0]:
            best = (streak, n)
    if best is None:
        return {"built": False, "wall": ("no modeled party currently carries a poor-fit residual "
                "(interlocutor_model._record_shape_fit's own datum) — nothing to mint a shape for")}
    _streak, party = best
    dom = _im._dominant_features(agent, party)
    if len(dom) < 2:
        return {"built": False, "wall": (f"party {party!r}'s accumulated features are too sparse "
                f"({dom!r}) to mint a genuine signature — fewer than 2 established dims")}

    default_at = {}
    for n in sub0.nodes("InterlocutorShape"):
        if sub0.node(n)["attrs"].get("name") == "default_uncalibrated":
            default_at = sub0.node(n)["attrs"]
            break
    interval = float(default_at.get("reliability_interval", 0.35) or 0.35)
    prior = float(default_at.get("self_report_reliability_prior", 0.5) or 0.5)
    decay_k = float(default_at.get("evidence_decay_k", 5.0) or 5.0)
    tom_prior = float(default_at.get("tom_capacity_prior", 0.5) or 0.5)

    name = "learned_" + "_".join(dom.get(d, "any") for d in _SHAPE_MINT_DIMS) + "_" + tag
    attrs = {"name": name,
             **{f"sig_{d}": dom[d] for d in _SHAPE_MINT_DIMS if d in dom},
             "self_report_reliability_prior": prior, "reliability_interval": interval,
             "expected_domains": [], "evidence_decay_k": decay_k,
             "tom_capacity_prior": tom_prior, "minted_from_party": str(party),
             "minted": 1.0}
    concept = {"type": "InterlocutorShape", "attrs": attrs}
    return {"built": True, "concept": concept, "name": name, "party": str(party),
            "dominant_features": dom,
            "how": (f"I read the promoted concern's own content words {words!r} (>= 2 held shape/"
                    f"profile keyword matches) and picked the party with the LARGEST poor-fit streak "
                    f"({party!r}, streak={_streak}). Its own dominant accumulated features "
                    f"{dom!r} become the new InterlocutorShape's signature, with WIDE priors copied "
                    "from the codebook's own default_uncalibrated entry — carried on the dispatched "
                    "copy via add_concepts, tried on the VARIANT before ever joining my own codebook.")}


# Name-keyed registry — the SAME pattern _COMPOSER_REGISTRY uses for
# `composer_pick`: the held `variation_pick` Program names the op; this is a
# mechanical lookup on the Term's verdict, not a decision.
_VARIATION_REGISTRY = {
    "cue_set_edit": _compose_cue_variant,
    "reply_ablation": _compose_reply_ablation,
    "knob_edit": _compose_knob_variant,
    "rule_literal_edit": _compose_rule_literal_variant,
    "datum_feedback_rule": _compose_datum_feedback_rule,
    "shape_mint": _compose_shape_mint,
    # structural_edit / threshold_shift are registered below, after their
    # builders are defined (module load order), same dict.
}


# ---------------------------------------------------------------------------
# STRUCTURAL VARIANT ALGEBRA — widens the acting-variant range from THRESHOLD
# SHIFTS (_compose_acting_variant: same rule shape, shifted magnitude) to
# STRUCTURAL EDITS (this: a DIFFERENT rule shape — flipped comparison, dropped
# match edge, added guard, swapped attribute key). domains/edit_ops.py holds
# the mechanical (op, target) -> new-rule-JSON appliers; EditOp nodes here are
# the applicability METADATA (which op, scored against a residual, the same
# way RuleSummary is scored) — the agent's own Argmax picks WHICH op, never a
# Python if/elif. WHERE (the site) is then read off the PICKED op's own
# structural scan of the picked rule (find_comparison_nodes / find_attr_keys)
# — for a homogeneous family (all N direction-gate comparisons; the two most-
# referenced Attr keys) there is exactly one non-arbitrary site to pick, so no
# further Argmax is needed there; a heterogeneous family (drop_match_edge's
# candidate indices) uses the first structurally-valid site, deterministic,
# documented honestly below (not a hidden random pick).
# ---------------------------------------------------------------------------
_EDIT_OPS = (
    {"kind": "flip_comparison",
     "keywords_text": "flip comparison reverse invert direction gate threshold opposite"},
    {"kind": "swap_term_leaf",
     "keywords_text": "swap leaf attribute key axis row col alternate substitute"},
    {"kind": "drop_match_edge",
     "keywords_text": "drop match edge relax remove constraint pattern broaden fewer"},
    {"kind": "add_match_guard",
     "keywords_text": "guard add constrain restrict narrow extra condition equality"},
)


def _ensure_edit_ops(sub) -> None:
    """Idempotently mint one `EditOp{kind, keywords_text}` node per entry in
    `_EDIT_OPS` — the graph-resident applicability catalogue the agent's own
    Argmax (in `_compose_structural_variant`) picks over. Mechanical seed-like
    I/O (same idempotency shape as `_ensure_acting_rule_provenance`); the
    CHOICE of which op is the agent's, made downstream, not here."""
    have = {sub.node(n)["attrs"].get("kind") for n in sub.nodes("EditOp")}
    for op in _EDIT_OPS:
        if op["kind"] in have:
            continue
        try:
            sub.add_node("EditOp", dict(op))
        except Exception:
            continue
        have.add(op["kind"])


def _editop_applicable_kinds(rule_json: dict, eo) -> list:
    """APPLICABILITY, as data, computed BEFORE the EditOp Argmax runs — the
    fix for the MAC/FAC gap `SHAPE_AUDIT.md` §2.1 names for A4
    (`RULES_AS_SHAPE_DESIGN_SPIKE.md` §4.2): 'the structural machinery is
    right there, and it runs only AFTER the name-keyword Argmax has already
    decided which operator to use.' These are the EXACT SAME predicates
    `_compose_structural_variant`'s own per-kind branches already use to
    decide 'inert' AFTER the pick (`eo.find_comparison_nodes` /
    `eo.find_attr_keys` / `len(match)`) — reused here as an INPUT to the
    pick instead of only an execution-time bookkeeping check. Pure,
    mechanical, no graph I/O: `rule_json` is a plain Python dict already
    resolved off `RuleSummary.rule_json` by `_pick_acting_rule` before this
    is ever called — the same kind of already-resolved Python value
    `axis_preds` already is when it becomes a Term literal below. Returns
    the list of `_EDIT_OPS` kind strings genuinely applicable to this rule
    (possibly empty, if some future rule shape is inert for all four —
    handled honestly by the caller, not assumed impossible)."""
    effects = rule_json.get("effects")
    match = rule_json.get("match") or []
    out = []
    if eo.find_comparison_nodes(effects):
        out.append("flip_comparison")
    if len(eo.find_attr_keys(effects)) >= 2:
        out.append("swap_term_leaf")
    if len(match) > 1:
        out.append("drop_match_edge")
    if match and isinstance(match[0], list) and len(match[0]) >= 1:
        out.append("add_match_guard")
    return out


# One `applicable_<kind>` RuleSummary attr per `_EDIT_OPS` kind -- the FULL
# kind string, not an abbreviation (see MAC_FAC_A8_PREREG.md §1 for why).
_APPLICABLE_ATTR = {
    "flip_comparison": "applicable_flip_comparison",
    "swap_term_leaf": "applicable_swap_term_leaf",
    "drop_match_edge": "applicable_drop_match_edge",
    "add_match_guard": "applicable_add_match_guard",
}


def _ensure_editop_applicability(sub) -> None:
    """A8 PRECOMPUTE (`MAC_FAC_A8_PREREG.md`/`MAC_FAC_A8_RESULTS.md`, closing
    `MAC_FAC_A7_A9_RESULTS.md` §5's sized follow-on): stamps the SAME four
    structural-applicability predicates `_editop_applicable_kinds` already
    computes for the A4 (Python) fix as PLAIN FLOAT ATTRS on each
    `RuleSummary` node, so the GRAPH-RESIDENT `epick` Argmax
    (`seeds/composer_experiment_graph.json`'s `compose_experiment_mint_
    parametric` meta-rule) can read them via an ordinary `Attr` — a Term
    cannot call `_editop_applicable_kinds`/`domains.edit_ops.find_
    comparison_nodes` (those are live Python functions, not Term
    primitives), so the verdict has to be computed here, once, and relayed
    onto the graph as data, exactly the way `axis_preds` becomes a Term
    literal in `_compose_structural_variant` itself.

    Calls `_editop_applicable_kinds` DIRECTLY -- reused, not reimplemented
    -- so there remains exactly ONE place these four predicates are
    defined; this function only relays that function's already-computed
    verdict onto the graph.

    Mirrors `_ensure_reply_rule_provenance`'s UPGRADE-IN-PLACE discipline
    (not `_ensure_acting_rule_provenance`'s mint-only one): the target
    `RuleSummary` nodes already exist (minted earlier, by `_ensure_acting_
    rule_provenance`, possibly on an earlier call) -- this function only
    ADDS four attrs onto an EXISTING node via `sub.set_attr`, the same
    upgrade-in-place shape `_ensure_reply_rule_provenance` uses to add
    `writes_reply`/`skippable`/`from_seed` onto a `RuleSummary` it did not
    itself mint. Idempotent (a stamped node — `applicable_flip_comparison`
    already present — is a cheap no-op skip); safe on an empty `RuleSummary`
    population (the loop body never runs); safe on an absent or unparseable
    `rule_json` (falls back to all-four `0.0`, the same honest 'not
    applicable' default `_editop_applicable_kinds` itself returns on a
    degenerate rule). No agent decision here -- every branch either copies
    an already-computed Python value onto the graph or safely no-ops."""
    from domains import edit_ops as _eo
    import json as _json
    for n in sub.nodes("RuleSummary"):
        attrs = sub.node(n)["attrs"]
        if attrs.get("applicable_flip_comparison") is not None:
            continue   # already stamped -- idempotent skip
        rule_json_str = attrs.get("rule_json")
        try:
            rule_json = _json.loads(rule_json_str) if rule_json_str else {}
        except Exception:
            rule_json = {}
        try:
            kinds = _editop_applicable_kinds(rule_json, _eo) if rule_json else []
        except Exception:
            kinds = []
        try:
            for kind, attr_name in _APPLICABLE_ATTR.items():
                sub.set_attr(n, attr_name, 1.0 if kind in kinds else 0.0)
        except Exception:
            continue


def _compose_structural_variant(agent, keys, tag: str) -> dict[str, Any]:
    """THE STRUCTURAL TWIN of `_compose_acting_variant`: picks WHICH candidate
    chosen_action-writing rule the axis's residual names (the SAME shared
    `_pick_acting_rule` Argmax), THEN picks WHICH EditOp (flip_comparison /
    swap_term_leaf / drop_match_edge / add_match_guard) the SAME axis's
    residual predicates genuinely name — a second held Argmax, over `EditOp`
    provenance (same StringIndexOf-Sum overlap shape), but the Argmax
    CANDIDATES are first restricted (a `Filter`, matching `_pick_acting_rule`'s
    own `skippable`-restriction precedent) to the EditOp kinds
    `_editop_applicable_kinds` finds structurally APPLICABLE to the picked
    rule — never letting the keyword score alone pick an op that is a
    guaranteed null on THIS rule's shape (e.g. `drop_match_edge` when the
    rule has only one match edge) while a genuinely applicable, lower-scoring
    op goes unconsidered. This closes the MAC/FAC gap `SHAPE_AUDIT.md` §2.1
    names for this exact site: applicability used to be checked only AFTER
    the pick (execution-time bookkeeping); it is now a genuine INPUT to the
    pick. The keyword-overlap signal itself is UNCHANGED — this restricts
    the candidate set, it does not replace or re-weight the relevance score.
    Applied via `domains.edit_ops`'s mechanical applier: `domains/edit_ops.py`'s
    appliers are the PRIMITIVE (mechanical, op+target -> new rule JSON); this
    function is the COMPOSITION (which op, on which rule, at which site) —
    the agent's decision, per CLAUDE.md.

    Returns `{'built': False, 'wall': ...}` — an honest null — when: no
    RuleSummary Argmax overlap (unchanged); no EditOp kind is structurally
    applicable to the picked rule AT ALL (new, checked before any Argmax
    runs); or the (now pre-filtered) EditOp Argmax still abstains because no
    APPLICABLE op scores > 0 on this residual. The per-kind apply branches
    below are kept as a defensive, unchanged safety net (they should no
    longer normally return None for a kind this function already filtered
    in as applicable — the SAME predicates gate both places — but the honest
    null path stays reachable rather than assumed unreachable)."""
    from domains import edit_ops as _eo
    sub0, native0, _ag0 = _resolve_agent(agent)
    axis_preds = []
    for n0 in sub0.nodes("CapabilityAxis"):
        at0 = sub0.node(n0)["attrs"]
        if at0.get("induced") and list(at0.get("capability_keys") or []) == [str(k) for k in keys]:
            axis_preds = list(at0.get("residual_predicates") or [])
            break
    pick = _pick_acting_rule(agent, axis_preds)
    if pick["picked"] is None or pick["rule_json"] is None:
        return {"built": False, "wall": ("no RuleSummary genuinely overlaps this axis's residual "
                "predicates (abstained, like the acting-variant pick abstains on no overlap)")}
    rule_json = pick["rule_json"]
    rule_name = pick["name"]

    applicable_kinds = _editop_applicable_kinds(rule_json, _eo)
    if not applicable_kinds:
        return {"built": False, "wall": (f"no EditOp is structurally applicable to the picked rule "
                f"{rule_name!r} at all (flip_comparison/swap_term_leaf/drop_match_edge/add_match_guard "
                "are all inert on this rule's match+effects shape) — an honest null found BEFORE any "
                "Argmax ran, not a wasted pick")}

    _ensure_edit_ops(sub0)
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Or = lambda *xs: {"type": "Or", "items": list(xs)}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    Gte = lambda a, b: {"type": "Gte", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Filter = lambda src, var, pred: {"type": "Filter", "source": src, "var_name": var, "predicate": pred}
    Argmax = lambda src, var, val, default: {"type": "Argmax", "source": src, "var_name": var,
                                              "value": val, "default": default}
    NodesOfType = lambda t: {"type": "NodesOfType", "node_type": t}
    Sum = lambda src, var, val: {"type": "Sum", "source": src, "var_name": var, "value": val}
    StrIdx = lambda h, n: {"type": "StringIndexOf", "haystack": h, "needle": n}
    LetT = lambda nm, val, body: {"type": "Let", "name": nm, "value": val, "body": body}

    words = L(list(axis_preds))
    overlap = lambda node_t: Sum(words, "w",
        Ite(Gte(StrIdx(Attr(node_t, "keywords_text"), V("w")), L(0)), L(1), L(0)))
    # APPLICABILITY GATE: restrict Argmax candidates to the EditOp kinds
    # `_editop_applicable_kinds` found structurally possible on THIS rule —
    # a Filter, mirroring `_pick_acting_rule`'s own `skippable`-restriction
    # precedent, evaluated inside the SAME Term as the keyword Argmax below
    # (no Python-side re-pick, no second decision point).
    is_applicable = Or(*[Eq(Attr(V("s"), "kind"), L(k)) for k in applicable_kinds])
    op_candidates = Filter(NodesOfType("EditOp"), "s", is_applicable)
    op_best = Argmax(op_candidates, "s", overlap(V("s")), None)
    op_pick_expr = LetT("best", op_best,
        Ite(Eq(V("best"), L(None)), L(None),
            Ite(Gt(overlap(V("best")), L(0.0)), V("best"), L(None))))
    try:
        op_node = native0.evaluate(op_pick_expr, {})
    except Exception as e:
        return {"built": False, "wall": f"edit-op pick failed: {type(e).__name__}: {e}"}
    if op_node is None or not sub0.has_node(op_node):
        return {"built": False, "wall": (f"no APPLICABLE EditOp genuinely overlaps this axis's residual "
                f"predicates (candidates restricted to {applicable_kinds!r} by structural applicability; "
                "abstained — not a random pick)")}
    kind = sub0.node(op_node)["attrs"].get("kind")
    new_name = rule_name + "_structvariant_" + tag

    if kind == "flip_comparison":
        variant = _eo.apply_flip_comparison(rule_json, new_name)
        site = "all comparison nodes in effects (a homogeneous family — see module docstring)"
        n_sites = len(_eo.find_comparison_nodes(rule_json.get("effects")))
    elif kind == "swap_term_leaf":
        keys_found = _eo.find_attr_keys(rule_json.get("effects"))
        variant = None
        site = None
        n_sites = len(keys_found)
        if len(keys_found) >= 2:
            old_key, new_key = keys_found[0][0], keys_found[1][0]
            variant = _eo.apply_swap_term_leaf(rule_json, old_key, new_key, new_name)
            site = f"Attr key {old_key!r} <-> {new_key!r} (the two most-referenced keys the rule already reads)"
    elif kind == "drop_match_edge":
        variant = _eo.apply_drop_match_edge(rule_json, 0, new_name)
        site = "match[0] (the first edge; the only structurally-valid site when len(match) > 1)"
        n_sites = max(0, len(rule_json.get("match") or []) - 1)
    elif kind == "add_match_guard":
        match = rule_json.get("match") or []
        if match and isinstance(match[0], list) and len(match[0]) >= 1:
            node_var = match[0][0]
            variant = _eo.apply_add_match_guard(rule_json, node_var, "adopted_variant_probe", True, new_name)
            site = f"where += Eq(Attr({node_var!r}, 'adopted_variant_probe'), True) (a NEW conjunct)"
        else:
            variant = None
            site = None
        n_sites = 1 if match else 0
    else:
        return {"built": False, "wall": f"unknown EditOp kind {kind!r}"}

    if variant is None:
        return {"built": False, "wall": (f"the picked op {kind!r} is structurally INERT on the picked "
                f"rule {rule_name!r} (n_sites={n_sites}) — a discovered null for THIS (op, rule) pairing, "
                "not fabricated"), "kind": kind, "rule": rule_name}
    return {"built": True, "rule": variant, "removed_rule": rule_name, "kind": kind, "site": site,
            "how": (f"I picked {rule_name!r} (RuleSummary Argmax) and the {kind!r} EditOp (EditOp Argmax, "
                    f"both scored by overlap with this axis's residual {axis_preds!r}), then applied it "
                    f"({site}) via domains.edit_ops — carried onto the dispatched copy via "
                    f"remove_rules=[{rule_name!r}] + add_rules=[the structural variant], never installed "
                    "locally.")}


_VARIATION_REGISTRY["structural_edit"] = _compose_structural_variant
_VARIATION_REGISTRY["threshold_shift"] = _compose_acting_variant


def _compose_experiment_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE THE SELF-EXPERIMENT RULES from the grounded relations — the composer's
    METASCIENCE path (twin of _compose_control_rule/_compose_grouping_rule: builds
    MULTIPLE related rules from ONE grounded relation set, gated by which relations
    grounded, like _compose_communicate_rule's optional parts).

    MINT (test/vary/send): an agent that OBSERVED something and MINTED an unexplained
    residual CapabilityAxis (its own 'I have a gap' signal — the SAME axis
    induce_concern mints and gap_prioritiser ranks) decides to TEST a hypothesis about
    itself by dispatching a MODIFIED INSTANCE of itself: it authors an
    Experiment{status: requested, hypothesis, game} + SeedDelta + has_delta edge —
    the vocabulary domains/experiment_dispatch.py's host MECHANISM consumes (it only
    sees status=='requested' and spawns a child process; it never decides to test,
    what to vary, or where to send it — that decision is this rule).

    ANALYSE (judge): once a dispatched trial PRODUCED a finished Run (the host ingests
    the child's result as Run + RunObservation, mechanical I/O), JUDGE the trial by its
    RESULT — a held IfThenElse comparison Term over score-per-frame sign, NOT a Python
    if/else — and write the verdict onto the Experiment.

    Which parts are built depends on which relations grounded: test -> the mint rule
    exists at all; send -> the mint rule reads WHICH world/game to dispatch to from the
    agent's OWN perceived WorldInstance (never host-supplied); vary -> the SeedDelta's
    skip_seeds is CHOSEN BY A HELD TERM in the rule itself (an Argmax over graph-resident
    SeedSummary nodes — see substrate/boot_all.py's per-seed provenance — of word-overlap
    with the axis's own residual_predicates, restricted to `skippable` seeds; abstains to a
    SECOND Argmax over the SAME seeds' own aggregate structural signature
    (`SeedSummary.where_signature_json`, `domains.seed_signature`) when the name-keyword
    Argmax genuinely finds nothing — see SEED_PICK_STRUCTURAL_FALLBACK_RESULTS.md — and
    only abstains to empty skip_seeds when NEITHER signal overlaps), AND (when judge also
    grounded) a VARIANT of
    the judge rule — a threshold-shifted copy, its shift read from the axis's own residual
    size at compose time — is embedded into delta.add_rules (installed on the DISPATCHED
    COPY, not locally: the parent tries a modification ON THE VARIANT, not on itself);
    judge -> the analysis rule is built, and (once analysed) marks conclusion_ready so a
    driver can persist the verdict via teach() (WHICH conclusion is this rule's call — teach
    only saves it). Installed live via add_rule; composition from held relations, not a
    hand-written rule.

    gradient -> (independent of vary/embed — deliberately NOT nested under 'vary', so
    testing an ACTING variant never accidentally also ablates a seed: the acting rule's
    own name is necessarily a substring of its hosting seed's SeedSummary.keywords_text
    too, so coupling it to 'vary' would confound the acting-variant with a coincidental
    seed-skip) a SECOND kind of variant is embedded: `_compose_acting_variant` picks WHICH
    chosen_action-writing rule (RuleSummary provenance, see `_ensure_acting_rule_provenance`)
    the axis's own residual genuinely names, and builds a threshold-shifted copy of it.
    `delta.remove_rules` names the ORIGINAL for `arc_child_run.py` to tombstone on the
    dispatched copy (`export_rules()` name->idx + `remove_rule`); the shifted copy goes into
    `delta.add_rules` alongside any embed-variant — so the dispatched child ACTS differently,
    not just judges differently. Honest null (no variant embedded) when the pick abstains or
    the picked rule carries no shiftable threshold — never a fabricated rule."""
    rp = {r[0] for r in rels}
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    Not = lambda x: {"type": "Not", "arg": x}
    And = lambda *xs: {"type": "And", "items": list(xs)}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    Gte = lambda a, b: {"type": "Gte", "a": a, "b": b}
    Lt = lambda a, b: {"type": "Lt", "a": a, "b": b}
    Div = lambda a, b: {"type": "Div", "a": a, "b": b}
    Ite = lambda c, t, o: {"type": "IfThenElse", "cond": c, "then": t, "other": o}
    Nb = lambda nd, et: {"type": "Neighbours", "node": nd, "edge_type": et}
    Exists = lambda src, var, pred: {"type": "Exists", "source": src, "var_name": var, "predicate": pred}
    Filter = lambda src, var, pred: {"type": "Filter", "source": src, "var_name": var, "predicate": pred}
    Argmax = lambda src, var, val, default: {"type": "Argmax", "source": src, "var_name": var,
                                              "value": val, "default": default}
    NodesOfType = lambda t: {"type": "NodesOfType", "node_type": t}
    Sum = lambda src, var, val: {"type": "Sum", "source": src, "var_name": var, "value": val}
    StrIdx = lambda h, n: {"type": "StringIndexOf", "haystack": h, "needle": n}
    StrCat = lambda parts: {"type": "StringConcat", "parts": list(parts)}
    LetT = lambda nm, val, body: {"type": "Let", "name": nm, "value": val, "body": body}
    tag = "_".join(str(k) for k in keys)
    rules = []
    acting_report = None            # surfaced in the return dict below, honest either way
    structural_report = None        # ditto — the structural-edit twin of acting_report
    reply_report = None             # ditto — the conversation-ablation twin ('replay' grounded)
    cue_report = None               # ditto — the cue-set-edit family (Wave 5, 'replay' + instruction kind)
    knob_report = None              # ditto — the knob-edit family (RESIDUAL-CLOSURE, 'bound'+'gradient')
    lit_report = None               # ditto — the rule-literal-edit family (WHERE-CLAUSE-VARIATION, 'ruleliteral')
    datum_report = None             # ditto — the datum-feedback-rule family (COMPOSER-CAPABILITY, 'datumfeedback')
    shape_report = None             # ditto — the shape-mint family (COMPOSER-CAPABILITY, 'shapemint')
    variation_op = None             # the variation_pick Program's verdict (None until 'test' authors a delta)
    conversation = "replay" in rp   # the conversation experiment family (Wave 3)
    # A test only needs a detached process/world when its grounded relations
    # explicitly say to SEND it to a world, or when it asks to replay an
    # interaction corpus.  Pure graph/rule hypotheses run as ungrounded
    # counterfactual cognition in-process.  This is epistemic modality derived
    # from the concern's held relations, not a game-name allowlist.
    external_test = "send" in rp or conversation

    if "test" in rp:
        # MINT: an observed-and-minted (unexplained) residual axis IS the agent's own
        # gap-signal (ag -observed-> obs -minted-> axis, the exact chain induce_concern's
        # UNCOVERED branch wires) -> it decides to TEST a hypothesis about itself.
        match = [["ag", "observed", "obs"], ["obs", "minted", "axis"]]
        where_items = [
            Eq(Attr(V("axis"), "is_axis"), L(1.0)),
            Eq(Attr(V("axis"), "capability_keys"), L([str(k) for k in keys])),
            Not(Exists(Nb(V("axis"), "tested_by"), "_i", L(True))),   # fixpoint guard
            # induce_concern writes `description` in PYTHON, right after the SAME run_rules()
            # call that can mint this axis returns — so a freshly-minted axis has no
            # description yet WITHIN that call. Wait for it (a later run_rules() call, once
            # induce_concern has returned) so the hypothesis text is never a premature None.
            Not(Eq(Attr(V("axis"), "description"), L(None))),
            # Only mint for axes whose concern shape includes 'test'. Comprehend-first
            # promoted concerns (reply_fix) mint axes with comprehend/* but no test predicate.
            Gt(Sum(Attr(V("axis"), "residual_predicates"), "p",
                   Ite(Eq(V("p"), L("test")), L(1), L(0))), L(0.0)),
        ]
        hyp_term = Attr(V("axis"), "description")     # the hypothesis IS the axis's own residual description
        game_term = L("")
        if "send" in rp:                    # DISPATCH needs to know WHICH world to send the variant to —
            match.append(["ag", "knows", "wi"])                # read from the agent's OWN perception, not
            if conversation:                                    # host-supplied.
                # A conversation-replay concern ('replay' grounded) is tested in the
                # conversation world SPECIFICALLY: the rule's own where pins the
                # perceived WorldInstance to the ChatWorld type + 'conversation' name
                # (the fact _ensure_conversation_world holds). A distinct world_type —
                # not 'Game' — makes the separation TWO-WAY: this rule can never bind
                # a coexisting ARC instance (e.g. the standing world's 'navigate'),
                # and the ARC family's own mint rules (Python OR the graph meta-rule,
                # both guarded world_type=='Game') can never bind the conversation
                # world. Still read from perception: the instance must be held.
                where_items.append(Eq(Attr(V("wi"), "world_type"), L("ChatWorld")))
                where_items.append(Eq(Attr(V("wi"), "name"), L("conversation")))
            else:
                where_items.append(Eq(Attr(V("wi"), "world_type"), L("Game")))
            game_term = Attr(V("wi"), "name")
        delta_attrs = {"add_rules": "[]", "remove_rules": "[]"}
        add_rules_list = []            # accumulates ANY embedded variants (judge and/or acting)
        if "vary" in rp:
            # Precompute the structural fallback's own aggregate attr BEFORE the Term
            # below is built -- mirrors _pick_acting_rule's own precall discipline
            # (_ensure_acting_rule_provenance + rule_signature.ensure_where_signature
            # before its Term is built). Idempotent; a no-op on every call after the
            # first (domains.seed_signature.ensure_seed_signature only mints the attr
            # on SeedSummary nodes that don't already carry it).
            from domains import seed_signature as _ssig
            _sub_vary, _native_vary, _ag_vary = _resolve_agent(agent)
            _ssig.ensure_seed_signature(_sub_vary)
            # THE AGENT PICKS WHAT TO ABLATE: overlap(seed) = how many of the axis's OWN
            # residual_predicates are substrings of that seed's keywords_text (the SAME
            # StringIndexOf-Sum text-overlap-argmax SHAPE _compose_browse_rule uses for
            # relevance), restricted to skippable (non-frozen) SeedSummary nodes. `best`
            # abstains (None) if no skippable seed exists at all; the outer Ite abstains
            # ("") if the winner's own overlap is 0 (no genuine match, not a random pick).
            #
            # STRUCTURAL FALLBACK (SEED_PICK_STRUCTURAL_FALLBACK_PREREG/RESULTS.md,
            # the A3 charter `RULE_SIGNATURE_PRODUCTION_WIRING_RESULTS.md` names and
            # does not build): the primary keywords_text Argmax above is UNCHANGED —
            # tried first, exactly as before. Only when it genuinely abstains (no
            # candidate scores > 0) does the SAME Sum/StringIndexOf/Argmax shape run a
            # second time against SeedSummary.where_signature_json (the seed's OWN
            # aggregate structural signature -- the union, over every rule the seed's
            # manifest declares, of that rule's where-clause signature, tagged by rule
            # name and PRECOMPUTED by domains.seed_signature.ensure_seed_signature the
            # same additive-attr way rule_signature.ensure_where_signature precomputes
            # RuleSummary's twin -- never a live nested join inside this installed
            # rule's own Term, which would re-walk the whole seed/rule population on
            # every firing with no engine-provided caching) instead of keywords_text --
            # reading structural information a seed's id/rule-NAMES/description words
            # can never carry (a concern's words naming something a seed's rules
            # structurally read/write but that seed's own identifiers do not spell).
            # Measured live (SEED_PICK_STRUCTURAL_FALLBACK_RESULTS.md): 6/6 genuine,
            # mechanically-discovered Class A probes (primary abstains, structural
            # fallback picks the correct seed) and 4/4 Class B probes (primary already
            # non-abstaining, combined pick byte-identical to primary) -- the fallback
            # is NEVER consulted when the primary Argmax already found a genuine
            # (score > 0) match, by construction of the Ite guard below, exactly
            # mirroring _pick_acting_rule's own fallback shape.
            words = Attr(V("axis"), "residual_predicates")
            overlap = lambda node_t: Sum(words, "w",
                Ite(Gte(StrIdx(Attr(node_t, "keywords_text"), V("w")), L(0)), L(1), L(0)))
            struct_overlap = lambda node_t: Sum(words, "w",
                Ite(Gte(StrIdx(Attr(node_t, "where_signature_json"), V("w")), L(0)), L(1), L(0)))
            candidates = Filter(NodesOfType("SeedSummary"), "s", Eq(Attr(V("s"), "skippable"), L(1.0)))
            best = Argmax(candidates, "s", overlap(V("s")), None)
            struct_best = Argmax(candidates, "s2", struct_overlap(V("s2")), None)
            struct_skip_id_expr = LetT("sbest", struct_best,
                Ite(Eq(V("sbest"), L(None)), L(""),
                    Ite(Gt(struct_overlap(V("sbest")), L(0.0)), Attr(V("sbest"), "seed_id"), L(""))))
            skip_id_expr = LetT("best", best,
                Ite(Eq(V("best"), L(None)), struct_skip_id_expr,
                    Ite(Gt(overlap(V("best")), L(0.0)), Attr(V("best"), "seed_id"), struct_skip_id_expr)))
            skip_seeds_expr = LetT("skip_id", skip_id_expr,
                Ite(Eq(V("skip_id"), L("")), L("[]"),
                    StrCat([L('["'), V("skip_id"), L('"]')])))
            delta_attrs["skip_seeds"] = {"__term__": skip_seeds_expr}
            delta_attrs["skip_seed_id"] = {"__term__": skip_id_expr}
            delta_attrs["varied"] = 1.0     # flag: this delta is INTENTIONALLY varied
        else:
            delta_attrs["skip_seeds"] = "[]"
        if "vary" in rp and "judge" in rp and "embed" in rp:
            # A VARIANT of the judge rule is embedded ONLY when 'embed' also grounds (a
            # DISTINCT concern from 'vary' — 'vary' alone only FLAGS the delta as
            # intentional and picks WHICH seed to ablate; 'embed' is the further decision
            # to actually CONSTRUCT and carry a modified rule onto the dispatched copy).
            # Same shape as the judge rule, threshold shifted by a coefficient read from
            # the axis's OWN residual size at COMPOSE TIME (a held Count Term over the
            # axis's residual_predicates, evaluated once now — not hand-picked): the
            # concern's own magnitude sets how much more/less decisive the variant's verdict
            # is. Embedded into delta.add_rules (installed on the DISPATCHED COPY by
            # arc_child_run.py's mechanical `for rule in delta['add_rules']: add_rule(rule)`
            # loop) — the parent is testing a modification ON THE VARIANT, not on itself.
            axis_preds = []
            sub0, native0, _ag0 = _resolve_agent(agent)
            for n0 in sub0.nodes("CapabilityAxis"):
                at0 = sub0.node(n0)["attrs"]
                if at0.get("induced") and list(at0.get("capability_keys") or []) == [str(k) for k in keys]:
                    axis_preds = list(at0.get("residual_predicates") or [])
                    break
            cnt_term = {"type": "Count", "source": L(axis_preds)}
            try:
                shift = round(float(native0.evaluate(cnt_term, {})) / 10.0, 4)
            except Exception:
                shift = 0.0
            v_score = Attr(V("run"), "score")
            v_frames = Attr(V("run"), "frames")
            v_rate = Div(v_score, v_frames)
            v_outcome = Ite(Gt(v_rate, L(shift)), L("supported"),
                            Ite(Lt(v_rate, L(-shift)), L("refuted"), L("inconclusive")))
            variant_rule = {
                "name": "judge_experiment_outcome_variant_" + tag,
                "match": [["exp", "produced", "run"]],
                "where": And(
                    Eq(Attr(V("run"), "status"), L("done")),
                    Not(Exists(Nb(V("exp"), "analysed"), "_j", L(True)))),
                "effects": [
                    ["set_attr", "exp", "outcome", {"__term__": v_outcome}],
                    ["add_edge", "exp", "analysed", "run"],
                ],
            }
            add_rules_list.append(variant_rule)
            delta_attrs["variant_threshold"] = shift
        # WAVE 5 — THE VARIATION CHOICE IS GRAPH DATA. The old Python chain
        # (if conversation: reply_ablation / elif judge+structure: structural /
        # elif judge+gradient: threshold_shift) is now the held `variation_pick`
        # Program over VariationOp nodes (seeds/variation_ops.json — priorities
        # + cue/kind gates preserve the exact old defaults; see that seed's
        # description). Python here is a name-keyed registry lookup on the
        # Term's verdict (`_VARIATION_REGISTRY`, the composer_pick pattern) +
        # mechanical wiring of whatever the picked builder returned onto the
        # delta. Editing a VariationOp node changes which family runs — the
        # agent's own repairable choice, no rule/Python edit.
        variation_op = _pick_variation_op(agent, rp, keys[0] if keys else "")
        variation_builder = _VARIATION_REGISTRY.get(variation_op) if variation_op else None
        if variation_op == "cue_set_edit" and variation_builder is not None:
            # THE CUE-SET EDIT — see _compose_cue_variant: the variant ADDS a
            # route Concept for the gap's unrouted verb (add_concepts on the
            # delta, applied by the child runners); `cue_edit` marks the delta
            # so perform_adoptions folds a SUPPORTED winner back by teach()ing
            # the Concept into the owning seed (no rule removed or installed).
            cue_report = variation_builder(agent, keys, tag)
            if cue_report.get("built"):
                import json as _json2
                delta_attrs["add_concepts"] = _json2.dumps([cue_report["concept"]])
                delta_attrs["cue_edit"] = 1.0
                delta_attrs["cue_concept_added"] = cue_report["verb"]
                delta_attrs["cue_route"] = cue_report["route"]
        elif variation_op == "reply_ablation" and variation_builder is not None:
            # THE CONVERSATION ABLATION — see _compose_reply_ablation (the conversation
            # twin of the gradient/structure variants below, and mutually exclusive with
            # them by construction: the 'replay' bundle carries neither 'gradient' nor
            # 'structure'). The delta names the reply rule to tombstone on the dispatched
            # copy; `ablation` marks the delta so perform_adoptions folds a SUPPORTED
            # winner back as a remove-only adoption (no replacement rule to install).
            reply_report = variation_builder(agent, keys, tag)
            if reply_report.get("built"):
                import json as _json2
                delta_attrs["remove_rules"] = _json2.dumps([reply_report["removed_rule"]])
                delta_attrs["act_rule_varied"] = reply_report["removed_rule"]
                delta_attrs["ablation"] = 1.0
        elif variation_op == "structural_edit" and variation_builder is not None:
            # THE STRUCTURAL VARIANT — see _compose_structural_variant. Takes PRIORITY
            # over 'gradient' when both ground on the same concern (both would otherwise
            # try to name the SAME picked acting rule in remove_rules with two different
            # replacements — 'structure' is the more specific ask, so it wins; a concern
            # that wants BOTH should be induced as two separate concerns, same as any
            # other composer choice in this module). Priority 30 < 40 in
            # seeds/variation_ops.json encodes exactly this.
            structural_report = variation_builder(agent, keys, tag)
            if structural_report.get("built"):
                add_rules_list.append(structural_report["rule"])
                import json as _json2
                delta_attrs["remove_rules"] = _json2.dumps([structural_report["removed_rule"]])
                delta_attrs["act_rule_varied"] = structural_report["removed_rule"]
                delta_attrs["edit_op_kind"] = structural_report["kind"]
        elif variation_op == "threshold_shift" and variation_builder is not None:
            # THE ACTING VARIANT — see _compose_acting_variant + the module-level docstring
            # note above ('gradient -> ...'). Independent of 'vary'/'embed': this concern is
            # about HOW THE CHILD ACTS, not what seed it knows or how it judges.
            acting_report = variation_builder(agent, keys, tag)
            if acting_report.get("built"):
                add_rules_list.append(acting_report["rule"])
                import json as _json2
                delta_attrs["remove_rules"] = _json2.dumps([acting_report["removed_rule"]])
                delta_attrs["act_shift"] = acting_report["shift"]
                delta_attrs["act_rule_varied"] = acting_report["removed_rule"]
        elif variation_op == "knob_edit" and variation_builder is not None:
            # THE KNOB-EDIT VARIANT (RESIDUAL-CLOSURE) — see _compose_knob_variant: the
            # variant shifts a held NODE ATTR belief (e.g. an ApertureBudget threshold)
            # rather than a rule literal; carried via set_node_attrs, applied by the
            # child runners' apply_node_attr_delta. `knob_edit` marks the delta so
            # perform_adoptions folds a SUPPORTED winner back by set_attr'ing the SAME
            # change onto the PARENT's own node.
            knob_report = variation_builder(agent, keys, tag)
            if knob_report.get("built"):
                import json as _json2
                delta_attrs["set_node_attrs"] = _json2.dumps([knob_report["set_node_attrs_item"]])
                delta_attrs["knob_edit"] = 1.0
                delta_attrs["knob_node_type"] = knob_report["node_type"]
                delta_attrs["knob_key_attr"] = knob_report["key_attr"]
                delta_attrs["knob_key_value"] = knob_report["key_value"]
                delta_attrs["knob_attr"] = knob_report["attr"]
                delta_attrs["knob_old_value"] = knob_report["old_value"]
                delta_attrs["knob_new_value"] = knob_report["new_value"]
        elif variation_op == "rule_literal_edit" and variation_builder is not None:
            # THE RULE-LITERAL-EDIT VARIANT (WHERE-CLAUSE-VARIATION) — see
            # _compose_rule_literal_variant: the variant shifts ONE numeric
            # where-clause literal on a picked rule (neither a chosen_action
            # writer nor a held-node-attr knob). `remove_rules`/`add_rules`/
            # `act_rule_varied` reuse the SAME generic fold the structural/
            # gradient families use (perform_adoptions, mark_adopt_ready_*) —
            # zero new adoption code. `rule_literal_edit` marks the delta so
            # the child runner knows to run the CONTROLLED double-pass over
            # the rule swap (mirroring knob_edit's node-attr double-pass).
            lit_report = variation_builder(agent, keys, tag)
            if lit_report.get("built"):
                add_rules_list.append(lit_report["rule"])
                import json as _json2
                delta_attrs["remove_rules"] = _json2.dumps([lit_report["removed_rule"]])
                delta_attrs["act_rule_varied"] = lit_report["removed_rule"]
                delta_attrs["rule_literal_edit"] = 1.0
                delta_attrs["rule_literal_old_value"] = lit_report["old_value"]
                delta_attrs["rule_literal_new_value"] = lit_report["new_value"]
                delta_attrs["rule_literal_direction"] = lit_report["direction"]
                if lit_report.get("witness"):
                    delta_attrs["rule_literal_witness"] = _json2.dumps(lit_report["witness"])
        elif variation_op == "datum_feedback_rule" and variation_builder is not None:
            # THE DATUM-FEEDBACK VARIANT (COMPOSER-CAPABILITY) — see
            # _compose_datum_feedback_rule: a genuinely NEW, ADD-ONLY rule (no
            # rule removed) that feeds a recorded datum back into a held
            # belief. `datum_feedback_edit` marks the delta so the child
            # runner knows to run the CONTROLLED double-pass over the rule's
            # own installation (mirroring knob_edit's node-attr double-pass,
            # but installing a RULE rather than setting an attr).
            datum_report = variation_builder(agent, keys, tag)
            if datum_report.get("built"):
                add_rules_list.append(datum_report["rule"])
                delta_attrs["datum_feedback_edit"] = 1.0
                delta_attrs["datum_feedback_datum_attr"] = datum_report["datum_attr"]
                delta_attrs["datum_feedback_belief_attr"] = datum_report["belief_attr"]
        elif variation_op == "shape_mint" and variation_builder is not None:
            # THE SHAPE-MINT VARIANT (COMPOSER-CAPABILITY) — see
            # _compose_shape_mint: constructs a brand-new InterlocutorShape
            # node from a poor-fit party's own accumulated features, carried
            # via the EXISTING add_concepts channel. `shape_mint_edit` marks
            # the delta so the child runner knows to run the CONTROLLED
            # double-pass over the concept's own installation.
            shape_report = variation_builder(agent, keys, tag)
            if shape_report.get("built"):
                import json as _json2
                delta_attrs["add_concepts"] = _json2.dumps([shape_report["concept"]])
                delta_attrs["shape_mint_edit"] = 1.0
                delta_attrs["shape_mint_name"] = shape_report["name"]
                delta_attrs["shape_mint_party"] = shape_report["party"]
        import json as _json
        delta_attrs["add_rules"] = _json.dumps(add_rules_list)
        rules.append({
            "name": "author_experiment_from_residual_" + tag,
            "match": match,
            "where": And(*where_items),
            "effects": [
                ["add_node", "exp", "Experiment", {
                    "status": "requested" if external_test else "counterfactual_requested",
                    "epistemic_scope": "external" if external_test else "graph_counterfactual",
                    "run_dir": "",
                    "hypothesis": {"__term__": hyp_term},
                    "game": {"__term__": game_term},
                    "axis_tag": tag,
                }],
                ["add_node", "delta", "SeedDelta", delta_attrs],
                ["add_edge", "exp", "has_delta", "delta"],
                ["add_edge", "axis", "tested_by", "exp"],
            ],
        })

    if "judge" in rp:
        # ANALYSE: a produced, finished Run -> judge the trial by its result. Div's own
        # zero-guard (silent 0.0 on frames==0) makes the rate well-defined without an
        # extra branch.
        score = Attr(V("run"), "score")
        frames = Attr(V("run"), "frames")
        rate = Div(score, frames)
        outcome = Ite(Gt(rate, L(0.0)), L("supported"),
                      Ite(Lt(rate, L(0.0)), L("refuted"), L("inconclusive")))
        rules.append({
            "name": "judge_experiment_outcome_" + tag,
            "match": [["exp", "produced", "run"]],
            "where": And(
                Eq(Attr(V("run"), "status"), L("done")),
                Not(Exists(Nb(V("exp"), "analysed"), "_j", L(True))),   # fixpoint guard
            ),
            "effects": [
                ["set_attr", "exp", "outcome", {"__term__": outcome}],
                ["add_edge", "exp", "analysed", "run"],
                # CLOSE-THE-LOOP MARKER: the rule (not the driver) decides a verdict is
                # ready to be taught — WHICH conclusion (outcome, hypothesis, axis_tag,
                # whichever seed was skipped) is entirely this rule's + the mint rule's
                # graph data; close_experiment_loop() below only PERSISTS it (teach()).
                ["set_attr", "exp", "conclusion_ready", True],
            ],
        })

    if "adopt" in rp:
        # ADOPT-THE-WINNER: mark every SUPPORTED Experiment that carries a genuine
        # acting-variant delta (act_rule_varied non-empty — a 'gradient' or
        # 'structure' experiment, never a bare judge-variant/skip_seeds-only delta)
        # as `adopt_ready` — the agent's OWN decision of WHICH experiments are
        # adoption candidates (graph data: outcome + delta shape), made exactly
        # once per Experiment (guarded by its own adopt_ready flag, the same
        # fixpoint-guard shape 'judge' uses). This rule does NOT itself perform the
        # remove_rule/add_rule mechanics or the provenance-denylist veto — those are
        # `perform_adoptions`'s host mechanical I/O + hard safety gate (same
        # division as teach()/close_experiment_loop: the agent decides WHICH, the
        # host does the I/O, and — same spirit as the frozen understand-Drive — the
        # host also refuses to touch alignment-frozen provenance regardless of what
        # any rule marks).
        if (cue_report is not None and cue_report.get("built")) or (knob_report is not None and knob_report.get("built")) \
                or (datum_report is not None and datum_report.get("built")) \
                or (shape_report is not None and shape_report.get("built")):
            # CUE-EDIT / KNOB-EDIT / DATUM-FEEDBACK / SHAPE-MINT FAMILIES (Wave 5 /
            # RESIDUAL-CLOSURE / COMPOSER-CAPABILITY): the delta carries NO varied
            # rule — the genuine-variant criterion is the cue concept, the knob
            # attr, the datum-feedback belief attr, or the minted shape name
            # instead. Authored with an Or so a coexisting acting-variant
            # experiment under the same rule still qualifies; the non-cue,
            # non-knob, non-datum-feedback, non-shape-mint path below stays
            # byte-identical to the pre-Wave-5 rule (graph-meta parity).
            genuine_variant = {"type": "Or", "items": [
                And(Not(Eq(Attr(V("delta"), "act_rule_varied"), L(""))),
                    Not(Eq(Attr(V("delta"), "act_rule_varied"), L(None)))),
                And(Not(Eq(Attr(V("delta"), "cue_concept_added"), L(""))),
                    Not(Eq(Attr(V("delta"), "cue_concept_added"), L(None)))),
                And(Not(Eq(Attr(V("delta"), "knob_attr"), L(""))),
                    Not(Eq(Attr(V("delta"), "knob_attr"), L(None)))),
                And(Not(Eq(Attr(V("delta"), "datum_feedback_belief_attr"), L(""))),
                    Not(Eq(Attr(V("delta"), "datum_feedback_belief_attr"), L(None)))),
                And(Not(Eq(Attr(V("delta"), "shape_mint_name"), L(""))),
                    Not(Eq(Attr(V("delta"), "shape_mint_name"), L(None)))),
            ]}
            adopt_where = And(
                Eq(Attr(V("exp"), "outcome"), L("supported")),
                Not(Eq(Attr(V("exp"), "adopt_ready"), L(True))),
                genuine_variant,
            )
        else:
            adopt_where = And(
                Eq(Attr(V("exp"), "outcome"), L("supported")),
                Not(Eq(Attr(V("exp"), "adopt_ready"), L(True))),
                Not(Eq(Attr(V("delta"), "act_rule_varied"), L(""))),
                Not(Eq(Attr(V("delta"), "act_rule_varied"), L(None))),
            )
        rules.append({
            "name": "mark_adopt_ready_" + tag,
            "match": [["exp", "has_delta", "delta"]],
            "where": adopt_where,
            "effects": [
                ["set_attr", "exp", "adopt_ready", True],
            ],
        })

    if not rules:
        return {"grounded": False, "path": "compose_experiment_rule", "concern": list(keys),
                "grounded_relations": rels,
                "wall": ("none of test/judge/adopt grounded — vary/send/gradient/structure/embed alone "
                         "only refine parts, nothing to author")}

    idxs = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:
            return {"grounded": False, "path": "compose_experiment_rule", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_experiment_rule", "concern": list(keys),
            "form": "experiment_rule", "grounded_relations": rels, "rules": rules, "rule_idx": idxs,
            "acting_variant": acting_report,   # None if 'gradient' didn't ground; else built or an honest wall
            "structural_variant": structural_report,   # None if 'structure' didn't ground; else built or a wall
            "reply_variant": reply_report,     # None if 'replay' didn't ground; else built or an honest wall
            "cue_variant": cue_report,         # None unless the variation pick chose cue_set_edit (Wave 5)
            "knob_variant": knob_report,       # None unless the variation pick chose knob_edit (RESIDUAL-CLOSURE)
            "lit_variant": lit_report,         # None unless the variation pick chose rule_literal_edit (WHERE-CLAUSE-VARIATION)
            "datum_variant": datum_report,     # None unless the variation pick chose datum_feedback_rule (COMPOSER-CAPABILITY)
            "shape_variant": shape_report,     # None unless the variation pick chose shape_mint (COMPOSER-CAPABILITY)
            "variation_op": variation_op,      # the variation_pick Program's verdict (or None: no family cued)
            "how": ("I GROUND the self-experiment concern by composing rules from the grounded relations: "
                    "test -> a MINT rule (an observed, unexplained residual axis is my own gap-signal; I "
                    "decide to test a hypothesis about myself and author an Experiment+SeedDelta, status "
                    "requested); send -> the mint rule reads WHICH world/game to dispatch to from my own "
                    "perceived WorldInstance; vary -> the delta is flagged intentionally-varied; judge -> "
                    "an ANALYSIS rule that, once a dispatched trial PRODUCED a finished Run, judges it by "
                    "score-per-frame sign (a held IfThenElse comparison Term) and writes the verdict onto "
                    "the Experiment; gradient -> a SECOND, independent variant (see _compose_acting_variant) "
                    "that changes how the dispatched child ACTS (remove_rules + a threshold-shifted copy of "
                    "the acting rule my own RuleSummary provenance Argmax picked), not just how it judges; "
                    "structure -> the STRUCTURAL twin (see _compose_structural_variant): an EditOp Argmax "
                    "picks flip_comparison/swap_term_leaf/drop_match_edge/add_match_guard, applied via "
                    "domains.edit_ops to the SAME picked acting rule — a different SHAPE, not just a "
                    "shifted threshold; adopt -> a rule that marks a SUPPORTED experiment carrying a "
                    "genuine acting-variant delta adopt_ready — the candidate decision only; "
                    "perform_adoptions performs the actual remove_rule/add_rule fold-back into the "
                    "PARENT ITSELF, gated by a hard provenance denylist. "
                    "Installed live; the host (domains/experiment_dispatch.py) only spawns the process and "
                    "ingests the Run/RunObservation trace back — it never decides to test, what to vary, "
                    "or what the outcome means.")}


def close_experiment_loop(agent) -> list:
    """CLOSE THE SELF-EXPERIMENT LOOP: for every Experiment the agent's OWN
    judge_experiment_outcome_* rule marked `conclusion_ready` (a graph-resident
    decision — see the rule's effects above) and not yet taught, PERSIST the
    verdict as a TaughtHint via the teach() facility, so self-knowledge
    accumulates across boots. WHICH conclusion exists (the outcome, the
    hypothesis, which seed — if any — was ablated, WHICH acting rule — if any —
    was varied and by how much) is entirely graph data the rule already
    decided; this function only reads it off and calls teach() (mechanical
    host I/O — the SAVE, per CLAUDE.md's teach() facility) and marks the
    Experiment `taught` so a later call is a no-op. Returns the list of
    teach() records created this call (empty if nothing was ready)."""
    from domains.teach import teach
    sub, native, ag_node = _resolve_agent(agent)
    out = []
    for exp in list(sub.nodes("Experiment")):
        at = sub.node(exp)["attrs"]
        if not at.get("conclusion_ready") or at.get("taught"):
            continue
        skip_seed_id = ""
        act_rule_varied = ""
        act_shift = None
        cue_concept_added = ""
        cue_route = ""
        knob_attr = ""
        knob_new_value = None
        for d in native.neighbours(exp, "has_delta"):
            if native.has_node(d):
                da = sub.node(d)["attrs"]
                skip_seed_id = da.get("skip_seed_id") or ""
                act_rule_varied = da.get("act_rule_varied") or ""
                act_shift = da.get("act_shift")
                cue_concept_added = da.get("cue_concept_added") or ""
                cue_route = da.get("cue_route") or ""
                knob_attr = da.get("knob_attr") or ""
                knob_new_value = da.get("knob_new_value")
                break
        axis_tag = at.get("axis_tag") or ""
        # BACK-COMPAT: the skip_seed_id/bare topic wording is UNCHANGED (existing taught
        # data + tests key on this exact string) — the acting-rule clause, when present,
        # is an ADDITIVE suffix, never a replacement.
        topic = (f"seed {skip_seed_id!r} ablation for {axis_tag}" if skip_seed_id
                 else f"self-experiment for {axis_tag}")
        if act_rule_varied:
            topic += f"; acting rule {act_rule_varied!r} replaced (shift={act_shift})"
        if cue_concept_added:
            # ADDITIVE suffix, same back-compat contract as the acting clause.
            topic += f"; cue concept {cue_concept_added!r} -> route {cue_route!r}"
        if knob_attr:
            # ADDITIVE suffix (RESIDUAL-CLOSURE), same back-compat contract.
            topic += f"; knob {knob_attr!r} -> {knob_new_value}"
        rec = teach(agent, "TaughtHint",
                    {"topic": topic, "hypothesis": str(at.get("hypothesis") or ""),
                     "answer": str(at.get("outcome") or ""), "axis_tag": axis_tag,
                     "skip_seed_id": skip_seed_id,
                     "act_rule_varied": act_rule_varied, "act_shift": act_shift,
                     **({"cue_concept_added": cue_concept_added, "cue_route": cue_route}
                        if cue_concept_added else {}),
                     **({"knob_attr": knob_attr, "knob_new_value": knob_new_value}
                        if knob_attr else {})},
                    category="experiment_conclusions")
        native.set_attr(exp, "taught", True)
        out.append(rec)
    out.extend(perform_adoptions(agent))
    return out


# ---------------------------------------------------------------------------
# ADOPT-THE-WINNER — closing the self-improvement loop: a SUPPORTED experiment's
# variant gets folded BACK INTO THE PARENT ITSELF, not just judged-and-forgotten.
# WHICH experiment is a candidate is the agent's own decision (the `adopt` rule
# above, graph data: outcome=='supported' + a genuine acting-variant delta).
# `perform_adoptions` is the mechanical host I/O that ACTS on that marking —
# remove_rule the original (tombstone, inherently recoverable) + add_rule the
# variant, mint an Adoption record, teach() a TaughtHint — GATED by a hard
# provenance denylist the agent's rule cannot override (same division as
# teach()'s SAVE being mechanical, and same alignment spirit as the frozen
# understand-Drive / boot_all.py's _FROZEN_SEED_IDS: the agent decides WHICH,
# the host retains a veto over touching foundational/unknown-provenance rules).
# ---------------------------------------------------------------------------
def _rule_denylisted(sub, rule_name: str) -> tuple:
    """The ADOPTION DENYLIST veto: DENY (True, reason) unless `rule_name` has a
    known `RuleSummary.from_seed` AND that seed's `SeedSummary.skippable == 1.0`
    (the SAME conservative denylist `substrate/boot_all.py`'s `_FROZEN_SEED_IDS`
    already applies to the self-experiment ablation pick — reused here, not
    re-invented). Unknown provenance (no RuleSummary, or `from_seed == ''` —
    e.g. a dynamically-authored variant rule no loaded seed manifest declares)
    is DENIED, never allowed-by-default: 'if a rule's provenance is unknown,
    DENY.'"""
    from_seed = None
    for n in sub.nodes("RuleSummary"):
        at = sub.node(n)["attrs"]
        if at.get("name") == rule_name:
            from_seed = at.get("from_seed") or ""
            break
    if not from_seed:
        return True, f"unknown provenance for {rule_name!r} (no RuleSummary.from_seed) — DENY by default"
    for n in sub.nodes("SeedSummary"):
        at = sub.node(n)["attrs"]
        if at.get("seed_id") == from_seed:
            if at.get("skippable") == 1.0:
                return False, ""
            return True, f"{rule_name!r} is from non-skippable (alignment/core-frozen) seed {from_seed!r}"
    return True, f"{rule_name!r} names seed {from_seed!r} but no SeedSummary exists for it — DENY"


def perform_adoptions(agent) -> list:
    """PERFORM ADOPTION: for every Experiment the agent's OWN `mark_adopt_ready_*`
    rule marked `adopt_ready` (and not yet adopted/denied), mechanically fold the
    winning acting-variant INTO THE PARENT ITSELF: `remove_rule` the original
    (Rust tombstones it — stable index, inherently recoverable, never truly
    deleted) + `add_rule` the variant (the SAME rule JSON the delta already
    carried in `add_rules`, dispatched-and-judged, never re-derived), mint an
    `Adoption{rule_removed, rule_added, experiment_id, tick, original_rule_json}`
    record (the `original_rule_json` is what `revert_adoption` needs — tombstones
    can't be un-tombstoned, so reverting RE-ADDS the original as a fresh slot),
    and teach() a TaughtHint. GUARDRAIL: `_rule_denylisted` is a hard veto this
    function enforces regardless of what any rule marked — a denied Experiment is
    marked `adopt_denied` (so it is never re-checked) but its rule stays active,
    unmodified. Idempotent (an already-adopted or already-denied Experiment is
    skipped). Returns the list of records created this call (teach() dicts for
    adoptions; `{'denied': True, ...}` dicts for vetoed candidates)."""
    from domains.teach import teach
    import json as _json
    import time as _time
    sub, native, ag_node = _resolve_agent(agent)
    out = []
    for exp in list(sub.nodes("Experiment")):
        if not sub.has_node(exp):
            continue
        at = sub.node(exp)["attrs"]
        if not at.get("adopt_ready") or at.get("adopted") or at.get("adopt_denied"):
            continue
        delta = None
        for d in native.neighbours(exp, "has_delta"):
            if native.has_node(d):
                delta = d
                break
        if delta is None:
            continue
        da = sub.node(delta)["attrs"]

        # CUE-SET-EDIT ADOPTION (Wave 5 — see _compose_cue_variant): a delta
        # flagged `cue_edit` carries NO rule to remove or install; adopting the
        # winner = teach() the judged Concept{name, instruction_route} into the
        # owning seed (comprehend_instruction — the seed that holds the verb
        # Concepts this route family lives in; teach() is the documented
        # persistence facility: live node NOW + seed manifest for future boots)
        # + mint the Adoption record. No denylist gate applies because NOTHING
        # is removed and the route was picked from routes the agent already
        # holds (the cue_route_pick pool) — the only new graph datum is one
        # Concept the dispatched replay already validated. Revert = remove the
        # Concept node (see revert_adoption's cue branch).
        cue_verb = str(da.get("cue_concept_added") or "")
        cue_route = str(da.get("cue_route") or "")
        if da.get("cue_edit") == 1.0 and cue_verb and cue_route:
            rec = teach(agent, "Concept",
                        {"name": cue_verb, "instruction_route": cue_route},
                        category="comprehend_instruction")
            try:
                concept_int = int(rec["node"].value)
            except Exception:
                concept_int = -1
            adoption = sub.add_node("Adoption", {
                "rule_removed": "", "rule_added": "",
                "cue_concept_added": cue_verb, "cue_route": cue_route,
                "concept_node": concept_int,
                "experiment_id": str(exp), "tick": _time.time(),
                "original_rule_json": "",
            })
            try:
                native.add_edge_unchecked(exp, "adopted_as", adoption)
            except Exception:
                pass
            native.set_attr(exp, "adopted", True)
            trec = teach(agent, "TaughtHint",
                         {"topic": f"adoption: cue concept {cue_verb!r} routed to "
                                   f"{cue_route!r} (experiment {exp})",
                          "answer": "adopted", "rule_removed": "", "rule_added": "",
                          "cue_concept_added": cue_verb, "cue_route": cue_route,
                          "experiment_id": str(exp)},
                         category="experiment_conclusions")
            out.append({"experiment": str(exp), "adoption": adoption,
                        "cue_concept_added": cue_verb, "cue_route": cue_route,
                        "rule_removed": "", "rule_added": "",
                        "cue_taught": rec,        # the Concept teach() record (owning seed + persisted flag)
                        "taught": trec, "saved": trec.get("saved")})
            continue

        # KNOB-EDIT ADOPTION (RESIDUAL-CLOSURE — see _compose_knob_variant): a
        # delta flagged `knob_edit` carries NO rule to remove or install either;
        # adopting the winner = apply the SAME set_node_attrs change the
        # dispatched replay already validated onto the PARENT'S OWN matching
        # node (find-by key_attr/key_value, exactly like the child runners'
        # apply_node_attr_delta) + mint the Adoption record (carrying the OLD
        # value, so revert_adoption can restore it — the node-attr twin of
        # original_rule_json). No denylist gate applies: nothing is removed,
        # and the knob is a held BELIEF (not a frozen/alignment rule) the
        # dispatched replay already exercised.
        knob_attr = str(da.get("knob_attr") or "")
        if da.get("knob_edit") == 1.0 and knob_attr:
            knob_type = str(da.get("knob_node_type") or "")
            knob_key_attr = str(da.get("knob_key_attr") or "")
            knob_key_value = da.get("knob_key_value")
            knob_new_value = da.get("knob_new_value")
            knob_old_value = da.get("knob_old_value")
            target = None
            for n in sub.nodes(knob_type):
                if sub.node(n)["attrs"].get(knob_key_attr) == knob_key_value:
                    target = n
                    break
            if target is None:
                continue        # the parent no longer carries this knob (stale) — nothing to fold back
            native.set_attr(target, knob_attr, knob_new_value)
            adoption = sub.add_node("Adoption", {
                "rule_removed": "", "rule_added": "",
                "knob_node_type": knob_type, "knob_key_attr": knob_key_attr,
                "knob_key_value": knob_key_value, "knob_attr": knob_attr,
                "knob_old_value": knob_old_value, "knob_new_value": knob_new_value,
                "experiment_id": str(exp), "tick": _time.time(),
                "original_rule_json": "",
            })
            try:
                native.add_edge_unchecked(exp, "adopted_as", adoption)
            except Exception:
                pass
            native.set_attr(exp, "adopted", True)
            trec = teach(agent, "TaughtHint",
                         {"topic": (f"adoption: knob {knob_attr!r} on {knob_type}("
                                    f"{knob_key_attr}={knob_key_value!r}) shifted "
                                    f"{knob_old_value} -> {knob_new_value} (experiment {exp})"),
                          "answer": "adopted", "rule_removed": "", "rule_added": "",
                          "knob_attr": knob_attr, "knob_new_value": knob_new_value,
                          "experiment_id": str(exp)},
                         category="experiment_conclusions")
            out.append({"experiment": str(exp), "adoption": adoption,
                        "knob_node_type": knob_type, "knob_attr": knob_attr,
                        "knob_old_value": knob_old_value, "knob_new_value": knob_new_value,
                        "rule_removed": "", "rule_added": "",
                        "taught": trec, "saved": trec.get("saved")})
            continue

        # DATUM-FEEDBACK ADOPTION (COMPOSER-CAPABILITY — see
        # _compose_datum_feedback_rule): a delta flagged `datum_feedback_edit`
        # carries a genuinely NEW, ADD-ONLY rule (no original to remove) —
        # adopting the winner = install it into the PARENT ITSELF (mechanical
        # add_rule, mirroring `perform_adoptions`'s own tombstone-then-add
        # shape minus the tombstone half, since nothing is replaced) + mint
        # the Adoption record. No denylist gate applies: nothing is removed
        # (the SAME reasoning the cue-edit/knob-edit branches above already
        # apply — `_rule_denylisted` exists to veto REMOVING a foundational
        # rule, and this branch removes nothing).
        belief_attr = str(da.get("datum_feedback_belief_attr") or "")
        if da.get("datum_feedback_edit") == 1.0 and belief_attr:
            try:
                df_add_rules = _json.loads(da.get("add_rules") or "[]")
            except Exception:
                df_add_rules = []
            df_rule = df_add_rules[0] if df_add_rules else None
            if df_rule is None:
                continue          # nothing to install — stale/empty delta
            df_name = df_rule.get("name", "")
            new_idx = native.add_rule(df_rule)
            adoption = sub.add_node("Adoption", {
                "rule_removed": "", "rule_added": df_name,
                "datum_feedback_datum_attr": da.get("datum_feedback_datum_attr") or "",
                "belief_attr": belief_attr,
                "experiment_id": str(exp), "tick": _time.time(),
                "added_idx": int(new_idx) if new_idx is not None else -1,
                "original_rule_json": "",
            })
            try:
                native.add_edge_unchecked(exp, "adopted_as", adoption)
            except Exception:
                pass
            native.set_attr(exp, "adopted", True)
            trec = teach(agent, "TaughtHint",
                         {"topic": (f"adoption: datum-feedback rule {df_name!r} installed — feeds "
                                    f"{da.get('datum_feedback_datum_attr')!r} back into {belief_attr!r} "
                                    f"(experiment {exp})"),
                          "answer": "adopted", "rule_removed": "", "rule_added": df_name,
                          "belief_attr": belief_attr, "experiment_id": str(exp)},
                         category="experiment_conclusions")
            out.append({"experiment": str(exp), "adoption": adoption, "rule_removed": "",
                        "rule_added": df_name, "belief_attr": belief_attr,
                        "taught": trec, "saved": trec.get("saved")})
            continue

        # SHAPE-MINT ADOPTION (COMPOSER-CAPABILITY — see _compose_shape_mint):
        # a delta flagged `shape_mint_edit` carries a brand-new
        # InterlocutorShape node (add_concepts, already generalized to typed
        # nodes) — adopting the winner = teach() it into the owning seed (the
        # SAME persistence facility the cue-edit branch above uses for a new
        # Concept — live node NOW + seed manifest for future boots) + mint
        # the Adoption record. No denylist gate applies: nothing is removed,
        # and the shape is a NEW codebook entry the dispatched replay already
        # exercised.
        shape_name = str(da.get("shape_mint_name") or "")
        if da.get("shape_mint_edit") == 1.0 and shape_name:
            try:
                sm_add_concepts = _json.loads(da.get("add_concepts") or "[]")
            except Exception:
                sm_add_concepts = []
            sm_item = sm_add_concepts[0] if sm_add_concepts else None
            if sm_item is None:
                continue          # nothing to install — stale/empty delta
            sm_attrs = dict(sm_item.get("attrs") or {})
            sm_type = str(sm_item.get("type") or "InterlocutorShape")
            rec = teach(agent, sm_type, sm_attrs, category="interlocutor_shapes")
            try:
                shape_node_int = int(rec["node"].value)
            except Exception:
                shape_node_int = -1
            adoption = sub.add_node("Adoption", {
                "rule_removed": "", "rule_added": "",
                "shape_name": shape_name, "shape_node": shape_node_int,
                "shape_mint_party": da.get("shape_mint_party") or "",
                "experiment_id": str(exp), "tick": _time.time(),
                "original_rule_json": "",
            })
            try:
                native.add_edge_unchecked(exp, "adopted_as", adoption)
            except Exception:
                pass
            native.set_attr(exp, "adopted", True)
            trec = teach(agent, "TaughtHint",
                         {"topic": f"adoption: InterlocutorShape {shape_name!r} minted (experiment {exp})",
                          "answer": "adopted", "rule_removed": "", "rule_added": "",
                          "shape_name": shape_name, "experiment_id": str(exp)},
                         category="experiment_conclusions")
            out.append({"experiment": str(exp), "adoption": adoption, "rule_removed": "", "rule_added": "",
                        "shape_name": shape_name, "shape_taught": rec,
                        "taught": trec, "saved": trec.get("saved")})
            continue

        removed_name = da.get("act_rule_varied") or ""
        try:
            add_rules = _json.loads(da.get("add_rules") or "[]")
        except Exception:
            add_rules = []
        variant_rule = next((r for r in add_rules
                             if isinstance(r, dict) and str(r.get("name", "")).startswith(removed_name + "_")),
                            None) if removed_name else None
        # ABLATION ADOPTION (the conversation family's vary — see
        # _compose_reply_ablation): a delta flagged `ablation` carries NO
        # replacement rule by design; adopting the winner = remove-only fold-back
        # (the original's exact JSON still lands on the Adoption record, so
        # revert_adoption restores it the same way). Same denylist gate below.
        is_ablation = da.get("ablation") == 1.0
        if not removed_name or (variant_rule is None and not is_ablation):
            continue

        denied, reason = _rule_denylisted(sub, removed_name)
        if denied:
            native.set_attr(exp, "adopt_denied", True)
            out.append({"experiment": str(exp), "denied": True, "reason": reason,
                        "rule": removed_name})
            continue

        exported = native.export_rules()
        idx = None
        for i, r in enumerate(exported):
            if isinstance(r, dict) and r.get("active", True) and r.get("name") == removed_name:
                idx = i
        if idx is None:
            continue           # the named rule isn't live (already removed some other way) — nothing to adopt
        original_json = dict(exported[idx])
        original_json.pop("active", None)
        native.remove_rule(idx)                      # tombstone the original (stable idx, recoverable)
        # install the winner in the PARENT itself; an ablation adoption installs nothing
        new_idx = native.add_rule(variant_rule) if variant_rule is not None else None

        adoption = sub.add_node("Adoption", {
            "rule_removed": removed_name,
            "rule_added": (variant_rule.get("name") if variant_rule is not None else ""),
            "experiment_id": str(exp), "tick": _time.time(),
            "removed_idx": int(idx),
            "added_idx": int(new_idx) if new_idx is not None else -1,
            "original_rule_json": _json.dumps(original_json),
        })
        try:
            native.add_edge_unchecked(exp, "adopted_as", adoption)
        except Exception:
            pass
        native.set_attr(exp, "adopted", True)
        added_name = variant_rule.get("name") if variant_rule is not None else ""
        topic = (f"adoption: rule {removed_name!r} replaced by {added_name!r} (experiment {exp})"
                 if added_name else
                 f"adoption: rule {removed_name!r} ablated (experiment {exp})")
        rec = teach(agent, "TaughtHint",
                    {"topic": topic,
                     "answer": "adopted", "rule_removed": removed_name,
                     "rule_added": added_name, "experiment_id": str(exp)},
                    category="experiment_conclusions")
        out.append({"experiment": str(exp), "adoption": adoption, "rule_removed": removed_name,
                    "rule_added": added_name, "taught": rec, "saved": rec.get("saved")})
    return out


def revert_adoption(agent, adoption_node) -> dict:
    """ROLLBACK an Adoption: Rust tombstones are inherently one-way (a removed
    slot never reactivates — see runners/dsl/src/py.rs's `remove_rule`), so
    revert does not "un-tombstone"; it RE-ADDS the original rule's exact JSON
    (captured on the `Adoption` node at adoption time, never re-derived) as a
    FRESH slot, and tombstones the variant. Host mechanical I/O only — reverses
    what `perform_adoptions` did; makes no new decision. Idempotent (a
    already-reverted Adoption is a no-op)."""
    import json as _json
    sub, native, ag_node = _resolve_agent(agent)
    try:
        exists = sub.has_node(adoption_node)
    except Exception:
        exists = False          # not a valid NodeID at all (e.g. a raw int) — honest "no such node"
    if not exists:
        return {"reverted": False, "reason": "no such Adoption node"}
    at = sub.node(adoption_node)["attrs"]
    if at.get("reverted"):
        return {"reverted": False, "reason": "already reverted"}
    if at.get("cue_concept_added"):
        # CUE-SET-EDIT REVERT (Wave 5): the adoption installed one Concept
        # (live + taught into the owning seed manifest); reverting removes the
        # LIVE Concept node(s) matching (name, instruction_route) so the route
        # stops firing now. KNOWN RESIDUAL, documented: the seed-manifest entry
        # teach() appended is left in place — a fresh boot re-holds the Concept
        # until the seed file is edited (the same one-way property as rule
        # tombstones; the Adoption record carries everything needed).
        name = str(at.get("cue_concept_added") or "")
        route = str(at.get("cue_route") or "")
        removed_any = False
        for n in list(sub.nodes("Concept")):
            try:
                a2 = sub.node(n)["attrs"]
            except Exception:
                continue
            if a2.get("name") == name and a2.get("instruction_route") == route:
                try:
                    (getattr(native, "remove_node", None) or sub.remove_node)(n)
                    removed_any = True
                except Exception:
                    pass
        for e in sub.nodes("Experiment"):
            if str(e) == str(at.get("experiment_id")) and sub.has_node(e):
                native.set_attr(e, "adopted", False)
                break
        native.set_attr(adoption_node, "reverted", True)
        return {"reverted": removed_any, "removed_concept": name, "cue_route": route,
                "seed_manifest_residual": True}
    if at.get("knob_attr"):
        # KNOB-EDIT REVERT (RESIDUAL-CLOSURE): restore the knob's OLD value
        # (captured on the Adoption record at adoption time, never re-derived)
        # onto the parent's live node — the node-attr twin of re-adding a
        # tombstoned rule's original JSON. No seed-manifest residual: the knob
        # was never taught into a seed (it is a pre-existing held belief node
        # whose ATTR VALUE changed, not a new graph datum), so a plain restore
        # is complete — unlike the cue-edit branch above.
        knob_type = str(at.get("knob_node_type") or "")
        knob_key_attr = str(at.get("knob_key_attr") or "")
        knob_key_value = at.get("knob_key_value")
        knob_attr = str(at.get("knob_attr") or "")
        old_value = at.get("knob_old_value")
        target = None
        for n in sub.nodes(knob_type):
            if sub.node(n)["attrs"].get(knob_key_attr) == knob_key_value:
                target = n
                break
        restored = False
        if target is not None:
            try:
                native.set_attr(target, knob_attr, old_value)
                restored = True
            except Exception:  # noqa: BLE001
                pass
        for e in sub.nodes("Experiment"):
            if str(e) == str(at.get("experiment_id")) and sub.has_node(e):
                native.set_attr(e, "adopted", False)
                break
        native.set_attr(adoption_node, "reverted", True)
        return {"reverted": restored, "restored_knob": knob_attr, "restored_value": old_value}
    if at.get("belief_attr"):
        # DATUM-FEEDBACK REVERT (COMPOSER-CAPABILITY): the adoption installed
        # a genuinely NEW, ADD-ONLY rule (no original replaced) — reverting
        # tombstones it. No belief-value restore: the belief itself is the
        # party's own pre-existing attr (untouched by adoption; only future
        # datum changes would move it further), so removing the rule alone
        # fully undoes what THIS adoption did — the same "nothing else to
        # restore" shape the cue-edit revert's Concept-only removal carries.
        added_name = str(at.get("rule_added") or "")
        removed_ok = False
        if added_name:
            exported = native.export_rules()
            idx = None
            for i, r in enumerate(exported):
                if isinstance(r, dict) and r.get("active", True) and r.get("name") == added_name:
                    idx = i
            removed_ok = bool(idx is not None and native.remove_rule(idx))
        for e in sub.nodes("Experiment"):
            if str(e) == str(at.get("experiment_id")) and sub.has_node(e):
                native.set_attr(e, "adopted", False)
                break
        native.set_attr(adoption_node, "reverted", True)
        return {"reverted": removed_ok, "removed_rule": added_name}
    if at.get("shape_name"):
        # SHAPE-MINT REVERT (COMPOSER-CAPABILITY): the adoption installed one
        # InterlocutorShape (live + taught into seeds/interlocutor_shapes.json);
        # reverting removes the LIVE node(s) matching the minted name. KNOWN
        # RESIDUAL, documented (the SAME one as the cue-edit revert above):
        # the seed-manifest entry teach() appended is left in place — a fresh
        # boot re-holds the shape until the seed file is edited.
        name = str(at.get("shape_name") or "")
        removed_any = False
        for n in list(sub.nodes("InterlocutorShape")):
            try:
                a2 = sub.node(n)["attrs"]
            except Exception:
                continue
            if a2.get("name") == name:
                try:
                    (getattr(native, "remove_node", None) or sub.remove_node)(n)
                    removed_any = True
                except Exception:
                    pass
        for e in sub.nodes("Experiment"):
            if str(e) == str(at.get("experiment_id")) and sub.has_node(e):
                native.set_attr(e, "adopted", False)
                break
        native.set_attr(adoption_node, "reverted", True)
        return {"reverted": removed_any, "removed_shape": name, "seed_manifest_residual": True}
    try:
        orig = _json.loads(at.get("original_rule_json") or "{}")
    except Exception as e:
        return {"reverted": False, "reason": f"original_rule_json unreadable: {type(e).__name__}: {e}"}
    if not orig:
        return {"reverted": False, "reason": "no original_rule_json stored on this Adoption"}
    added_name = at.get("rule_added")
    exported = native.export_rules()
    idx = None
    if added_name:                       # an ablation adoption installed no variant to tombstone
        for i, r in enumerate(exported):
            if isinstance(r, dict) and r.get("active", True) and r.get("name") == added_name:
                idx = i
    removed_ok = bool(idx is not None and native.remove_rule(idx)) or not added_name
    new_idx = native.add_rule(orig)
    sub_exp = None
    for e in sub.nodes("Experiment"):
        if str(e) == str(at.get("experiment_id")):
            sub_exp = e
            break
    if sub_exp is not None and sub.has_node(sub_exp):
        native.set_attr(sub_exp, "adopted", False)
    native.set_attr(adoption_node, "reverted", True)
    native.set_attr(adoption_node, "revert_removed_idx", float(idx if idx is not None else -1))
    native.set_attr(adoption_node, "revert_added_idx", float(new_idx if new_idx is not None else -1))
    return {"reverted": bool(removed_ok and new_idx is not None), "restored_rule": at.get("rule_removed"),
            "restored_idx": new_idx, "tombstoned_variant": added_name}


def _compose_attention_rule(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE THE WHEN-TO-LOOK RULE from the grounded 'watch' relation — the
    self-build composer's PERCEPTION-TIMING path. No held cue (watch / observe
    / look / perceive / attend / notice) existed before this change — a proven
    wall (checked: none of the prior RelationCue keyword lists in
    seeds/relation_vocabulary.json mention any of them; ground_concern would
    have returned {grounded: False, path: 'predicate_grounding'}), not a
    re-label of an existing composer.

    Authors the canonical "look rule" (tests/test_rule_driven_look.py's shape,
    generalised to read its own wiring off graph context instead of a
    host-supplied literal fb_id): match `?t -[wants_look]-> ?g`, where
    `FbFrameSeq(Attr(?t,'fb_id')) > Attr(?g,'last_looked_seq')`, effects
    `FbSample(Attr(?t,'fb_id'), ?g, Attr(?t,'grid_w'), Attr(?t,'grid_h'))` then
    `SetAttr(?g,'last_looked_seq', FbFrameSeq(Attr(?t,'fb_id')))` — exactly-
    once-per-new-frame perception, zero host fb_sample calls. `?t` (a
    LookTrigger) and its `fb_id`/`grid_w`/`grid_h` attrs + the `wants_look`
    edge to `?g` are stamped by a world adapter (worlds/fb_eye.py) when it
    mechanically attaches a framebuffer — the agent's rule reads that context,
    it is never host-supplied into the rule itself. Installed live."""
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    Attr = lambda nd, k: {"type": "Attr", "node": nd, "key": k}
    Gt = lambda a, b: {"type": "Gt", "a": a, "b": b}
    FbSeq = lambda fb: {"type": "FbFrameSeq", "fb": fb}
    tag = "_".join(str(k) for k in keys)
    fb_id_t = Attr(V("t"), "fb_id")
    rule = {
        "name": "look_when_frame_advances_" + tag,
        "match": [["t", "wants_look", "g"]],
        "where": Gt(FbSeq(fb_id_t), Attr(V("g"), "last_looked_seq")),
        "effects": [
            ["fb_sample", {"__term__": fb_id_t}, "g",
             {"__term__": Attr(V("t"), "grid_w")}, {"__term__": Attr(V("t"), "grid_h")}],
            ["set_attr", "g", "last_looked_seq", {"__term__": FbSeq(fb_id_t)}],
        ],
    }
    try:
        idx = agent.inner.add_rule(rule)
    except Exception as e:
        return {"grounded": False, "path": "compose_attention_rule", "concern": list(keys),
                "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_attention_rule", "concern": list(keys),
            "form": "attention_rule", "grounded_relations": rels, "rule": rule, "rule_idx": idx,
            "how": ("I GROUND 'when should I look' by composing the look-rule: I sample my own eye "
                    "exactly once per genuinely-new framebuffer frame (FbFrameSeq gates the where-clause; "
                    "the trailing SetAttr advances my own watermark) and stay silent otherwise — zero host "
                    "fb_sample calls. The fb_id/grid dims/which game I'm watching all come from graph "
                    "context (the LookTrigger a world adapter stamped), not literals baked into the rule.")}


def _compose_faculty_pipeline(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A WHOLE FACULTY AS A MULTI-RULE CHAIN — the self-build composer's
    substrate-self-extension path (SELF-IMPROVEMENT #4). Where every other
    `_compose_*_rule` builder authors ONE rule (or a fixed small handful for one
    concern), this one authors a PIPELINE: a graph of rules where each stage's
    OUTPUT feeds the next stage's precondition, so `run_rules` fires them in order
    to fixpoint and the whole chain fills a CapabilityGap that no single rule could.
    It is still a COMPOSITION OF HELD PRIMITIVES (match / where / set_attr / add_node
    / add_edge) — the honest reach of self-extension: the agent authors a new faculty
    it can express in the held vocabulary, it does not invent a primitive (that is the
    PrimitiveRequest / SPEC path when grounding walls).

    WHICH STAGES are installed is selected by WHICH stage relations grounded (the same
    parts-by-grounded-relations discipline `_compose_communicate_rule` uses):
      classify -> stage 1: mark an unclassified item `stage=classified`;
      route    -> stage 2: a classified item mints a Handler + `routed_to` edge, `stage=routed`;
      finalize -> stage 3: a routed item is marked `handled=1`, `stage=done`.
    The stages CHAIN: 2's precondition is 1's output (`stage==classified`), 3's is 2's
    (`routed_to` + `stage==routed`). Installed live via `add_rule`; the composition is a
    multi-rule faculty, not a single rule."""
    rp = {r[0] for r in rels}
    V = lambda n: {"type": "Var", "name": n}
    L = lambda v: {"type": "Lit", "value": v}
    A = lambda n, k: {"type": "Attr", "node": V(n), "key": k}
    Eq = lambda a, b: {"type": "Eq", "a": a, "b": b}
    tag = "_".join(str(k) for k in keys)
    rules: list = []
    if "classify" in rp:
        rules.append({
            "name": "pl_classify_" + tag,                       # stage 1 — the pipeline head
            "match": [["hub", "has_item", "it"]],
            "where": Eq(A("it", "stage"), L(None)),             # an item not yet in the pipeline
            "effects": [["set_attr", "it", "stage", "classified"]]})
    if "route" in rp:
        rules.append({
            "name": "pl_route_" + tag,                          # stage 2 — consumes stage 1's output
            "match": [["hub", "has_item", "it"]],
            "where": Eq(A("it", "stage"), L("classified")),
            "effects": [["add_node", "h", "Handler", {"kind": "handler"}],
                        ["add_edge", "it", "routed_to", "h"],
                        ["set_attr", "it", "stage", "routed"]]})
    if "finalize" in rp:
        rules.append({
            "name": "pl_finalize_" + tag,                       # stage 3 — consumes stage 2's output
            "match": [["it", "routed_to", "h"]],
            "where": Eq(A("it", "stage"), L("routed")),
            "effects": [["set_attr", "it", "handled", 1.0],
                        ["set_attr", "it", "stage", "done"]]})
    if len(rules) < 2:
        return {"grounded": False, "path": "compose_faculty_pipeline", "concern": list(keys),
                "grounded_relations": rels,
                "wall": ("a pipeline faculty needs at least two chained stages; the grounded relations "
                         f"named only {sorted(rp)!r} — not a multi-stage composition")}
    idxs: list = []
    for r in rules:
        try:
            idxs.append(agent.inner.add_rule(r))
        except Exception as e:  # noqa: BLE001
            return {"grounded": False, "path": "compose_faculty_pipeline", "concern": list(keys),
                    "grounded_relations": rels, "wall": f"rule install failed: {type(e).__name__}: {e}"}
    return {"grounded": True, "path": "compose_faculty_pipeline", "concern": list(keys),
            "form": "faculty_pipeline", "grounded_relations": rels,
            "rules": rules, "rule_idx": idxs, "n_rules": len(rules),
            "how": ("I GROUND the gap by composing a WHOLE FACULTY — a multi-rule CHAIN, not a single "
                    "rule: the grounded stage relations select the stages (classify -> route -> finalize), "
                    "and each stage's precondition is the previous stage's output (route fires on "
                    "stage==classified, finalize on the routed_to edge + stage==routed), so run_rules "
                    "drives the whole pipeline to fixpoint and an unhandled item becomes handled. Every "
                    "part is a held primitive (match/where/set_attr/add_node/add_edge) — a composition, "
                    "not an invented primitive. Installed live.")}


def _language_faculty_ground_reference(sub):
    """The claim's support reaches an EXTERNAL lexical reference anchor: the
    nominal-head DECISION reads the POS faculty, which the world adapter read from
    OUTSIDE the agent (Wiktionary / the closed-class faculty). A real teacher-style
    exchange, anchored via a TaughtHint{origin:'teacher_hook'} the grounding-reach
    machinery maps to a TeacherAnchor. Mirrors consumption_quality._ground_reference
    (the same POS/sense reference), the honest external-reference anchor."""
    node = sub.add_node("Collapse", {"label": "language_faculty_support"})
    th = sub.add_node("TaughtHint", {"origin": "teacher_hook",
                                     "topic": "lexical_reference",
                                     "answer": "external POS reference reading (nominal head)"})
    sub.add_edge_unchecked(node, "grounded_in", th)
    return node


def _compose_language_faculty(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A LANGUAGE-FACULTY PROGRAM — the self-build composer's LANGUAGE path.
    Where `_compose_faculty_pipeline` authors a multi-rule CHAIN and `build_primitive`
    constructs a computational Term, this authors a PROGRAM that composes the agent's
    LANGUAGE faculties: a FILTER / SELECT over words / spans / senses. It closes the
    frontier the prior consumption-quality fix surfaced honestly — that fix filtered
    clause fragments with ADAPTER LOGIC (consumption_quality.is_nominal) "because the
    composer does not yet author a POS-Program." Now the jabberwock authors it.

    WHICH Program is composed is selected by which relations grounded (the same
    parts-by-grounded-relations discipline `_compose_communicate_rule` uses):
      filter  -> the routing head (a FILTER over spans is the concern);
      nominal -> the LANGUAGE LEAF chained under the filter is the nominal-head op
                 (domains/language_faculty_ops.nominal_head_term — the POS/nominal-vs-
                 clause DECISION as a graph-resident Term over a span's measured POS
                 features; the raw POS LOOKUP stays a held-faculty call, the honest
                 leaf boundary). The authored Program is
                 Filter(source=trig.has_span, var=span, predicate=nominal_head_term).

    The AUTHORING is the composer's: it assembles the Filter + the leaf into one
    Program Term, GATES it through `admissibility_gate` (its forward model reproduces
    the labelled keep/drop constraints — a clause fragment drops, a nominal keeps),
    VERIFIES it with #2 `self_verification.verify_claim` (a discriminative control:
    a clause fails, a nominal passes; a keep-everything twin FAILS the control), and
    installs it LIVE as a named Program node only if BOTH pass. Honest reach: the
    composer authors the FILTER COMPOSITION + the nominal-head DECISION Term; the
    POS LOOKUP that measures a span's features is a held-faculty CALL (external
    lexical I/O — no Term reads Wiktionary), reported as the leaf boundary, not
    claimed as authored."""
    from domains import language_faculty_ops as lfo
    from domains import consumption_quality as cq
    from domains import admissibility_gate as ag
    from domains import self_verification as sv

    sub, native, ag_node = _resolve_agent(agent)
    rp = {r[0] for r in rels}
    tag = "_".join(str(k) for k in keys)

    # SENSE branch — the SECOND language leaf: a SELECT over a word's senses by
    # context fit (the composer's language path extended from FILTER to SELECT).
    if "sense" in rp:
        return _compose_sense_select(agent, keys, rels, sub, native, ag_node, tag)

    if "nominal" not in rp:
        # only the nominal-head leaf is exposed so far; a 'filter' concern that does
        # NOT ground the nominal leaf has no language leaf to chain — honest wall,
        # not a fabricated Program.
        return {"grounded": False, "path": "compose_language_faculty", "concern": list(keys),
                "grounded_relations": rels,
                "wall": ("the 'filter' concern grounded, but no language LEAF did — only the "
                         "nominal-head op ('nominal') is exposed as a Program-callable leaf so far; "
                         "nothing to chain under the filter (extend language_faculty_ops with the "
                         "next leaf, do not fabricate a Program)")}

    # AUTHOR — the Filter Program chaining the nominal-head language leaf.
    program = lfo.nominal_filter_program()
    fake = lfo.keep_everything_program()

    # the labelled control: clause fragments (drop) + real nominals (keep). The
    # Program's OWN output is measured once over every control/prior surface (the
    # decision is the Program's; this reads it back).
    control = list(cq.NOMINAL_CONTROL)
    prior = list(cq.NOMINAL_PRIOR)
    surfaces = [s for s, _ in control] + [s for s, _ in prior]
    real_keep = dict(zip(surfaces, lfo.run_filter_program(program, surfaces)))
    fake_keep = dict(zip(surfaces, lfo.run_filter_program(fake, surfaces)))

    # ADMISSIBILITY GATE — admit only if the authored Program's forward model
    # REPRODUCES the labelled keep/drop constraints (every clause drops, every
    # nominal keeps). One broken constraint => inadmissible by construction.
    object_props = {f"keep::{s}": bool(real_keep.get(s)) for s, _ in control}
    stated_props = {f"keep::{s}": bool(exp) for s, exp in control}
    gres = ag.gate_object(object_props=object_props, stated_props=stated_props,
                          question_text="", substrate=None)
    if not gres.admitted:
        return {"grounded": False, "path": "compose_language_faculty", "concern": list(keys),
                "grounded_relations": rels, "program": program,
                "gate_reason": gres.reason,
                "wall": ("the authored Program did NOT pass the admissibility gate (its forward "
                         f"model failed a labelled keep/drop constraint): {gres.reason}")}

    # #2 VERIFY-BEFORE-TRUST — a discriminative control whose keep-everything twin fails.
    def mechanism(case) -> bool:
        surface, expected = case
        return bool(real_keep.get(surface)) == bool(expected)

    def fake_twin(case) -> bool:
        surface, expected = case
        return bool(fake_keep.get(surface)) == bool(expected)

    verdict = sv.verify_claim(agent, sv.Claim(
        text="composer-authored nominal-filter Program keeps noun phrases, drops clause fragments",
        mechanism=mechanism, control_cases=control, fake_twin=fake_twin,
        prior_cases=prior, ground_support=_language_faculty_ground_reference))
    if not verdict.get("accepted"):
        return {"grounded": False, "path": "compose_language_faculty", "concern": list(keys),
                "grounded_relations": rels, "program": program, "verified": verdict,
                "wall": ("the authored Program failed #2 verification (control did not "
                         f"discriminate real from fake): {verdict.get('reason')}")}

    # INSTALL — the authored Program is now a live, named graph-resident Program node
    # (idempotent by name). consumption_quality reads it via _load_program and runs
    # the FILTER over real extracts — the filter logic is the authored Program's.
    import json as _json
    prog_json = _json.dumps(program)
    existing = None
    for n in sub.nodes("Program"):
        if sub.node(n)["attrs"].get("name") == lfo.NOMINAL_FILTER_PROGRAM:
            existing = n
            break
    if existing is None:
        prog_node = sub.add_node("Program", {
            "name": lfo.NOMINAL_FILTER_PROGRAM, "program": prog_json,
            "form": "term_tree", "authored_by": "language_faculty_composer",
            "concern": tag})
        if ag_node is not None:
            try:
                sub.add_edge_unchecked(ag_node, "authored", prog_node)
            except Exception:
                pass
    else:
        prog_node = existing

    return {"grounded": True, "path": "compose_language_faculty", "concern": list(keys),
            "form": "language_faculty_program", "grounded_relations": rels,
            "served_by": "python", "program_name": lfo.NOMINAL_FILTER_PROGRAM,
            "program": program, "program_node": str(prog_node),
            "gate_reason": gres.reason, "verified": verdict,
            "leaf": "nominal_head_term (POS/nominal-vs-clause DECISION as a graph Term)",
            "held_faculty_call": ("the raw POS LOOKUP (wiktionary_reference.wiktionary_pos + "
                                  "function_word_reference.classify) that MEASURES each span's POS "
                                  "features — external lexical I/O, no Term reads it; the honest leaf boundary"),
            "how": ("I GROUND the LANGUAGE concern ('keep only nominal spans') by composing a "
                    "PROGRAM, not a rule-chain: the grounded relations select its parts — 'filter' "
                    "-> a Filter over spans; 'nominal' -> the language LEAF chained under it is my "
                    "nominal-head op (the POS/nominal-vs-clause DECISION as a graph Term over each "
                    "span's measured POS features). I assemble Filter(source=trig.has_span, "
                    "var=span, predicate=nominal_head_term), ADMIT it through the gate (its forward "
                    "model drops every clause fragment and keeps every nominal), VERIFY it with a "
                    "discriminative control (a keep-everything twin FAILS), and install it live as a "
                    "named Program. The POS LOOKUP that measures a span's features stays a "
                    "held-faculty call — the honest leaf boundary; the FILTER COMPOSITION + the "
                    "nominal DECISION Term are mine.")}


def _compose_sense_select(agent, keys, rels, sub, native, ag_node, tag) -> dict[str, Any]:
    """COMPOSE A SENSE-DISAMBIGUATOR SELECT Program — the composer's language path
    extended from a FILTER (keep nominal spans) to a SELECT (pick the sense that fits
    the context). It closes the SECOND frontier the consumption-quality fix surfaced
    honestly — that fix marshalled context to dictionary_lexicon.pick_sense as ADAPTER
    logic; now the jabberwock authors the SCORE + ARGMAX composition itself.

    The 'sense' relation grounds the LANGUAGE LEAF chained under the select: the
    sense-fit SCORE Term (domains/language_faculty_ops.sense_score_term — a candidate
    sense's fit to the context as a Term over its measured features). The authored
    Program is Argmax(source=sel.has_candidate, var=cand, value=sense_score_term). The
    composer assembles it, GATES it (its forward model picks the context-fitting sense
    for every labelled case), VERIFIES it (#2: a CONTEXT-BLIND twin — score without the
    Lesk-overlap term — FAILS a context-dependent case), and installs it LIVE only if
    BOTH pass. Honest reach: the composer authors the SCORE + ARGMAX composition; the
    raw WordNet SENSE ENUMERATION that measures each candidate's features is a
    held-faculty CALL (external lexical I/O — no Term reads WordNet)."""
    from domains import language_faculty_ops as lfo
    from domains import consumption_quality as cq
    from domains import admissibility_gate as ag
    from domains import self_verification as sv
    import json as _json

    # AUTHOR — the Argmax SELECT Program chaining the sense-fit score leaf.
    program = lfo.sense_select_program()
    fake = lfo.sense_select_blind_program()

    # the labelled control: (head, context-words, slot, gold-gloss-keywords). The
    # picked sense's gloss must contain a gold keyword. The Program's OWN pick is
    # measured once over every control/prior case (the decision is the Program's).
    control = list(cq.SENSE_CONTROL)
    prior = list(cq.SENSE_PRIOR)

    def _fits(prog, case) -> bool:
        head, ctx, slot, gold = case
        r = lfo.run_sense_select_program(prog, head, slot, list(ctx))
        gloss = (r.get("sense") or "").lower() if r else ""
        return any(g in gloss for g in gold)

    real_fit = {case[0]: _fits(program, case) for case in control + prior}
    fake_fit = {case[0]: _fits(fake, case) for case in control + prior}

    # ADMISSIBILITY GATE — admit only if the authored Program's forward model picks a
    # context-fitting sense for every labelled case (one miss => inadmissible).
    object_props = {f"fit::{case[0]}": bool(real_fit.get(case[0])) for case in control}
    stated_props = {f"fit::{case[0]}": True for case in control}
    gres = ag.gate_object(object_props=object_props, stated_props=stated_props,
                          question_text="", substrate=None)
    if not gres.admitted:
        return {"grounded": False, "path": "compose_sense_select", "concern": list(keys),
                "grounded_relations": rels, "program": program, "gate_reason": gres.reason,
                "wall": ("the authored SELECT Program did NOT pass the admissibility gate (its "
                         f"forward model failed a labelled context-fit constraint): {gres.reason}")}

    # #2 VERIFY-BEFORE-TRUST — a discriminative control whose context-blind twin fails.
    def mechanism(case) -> bool:
        return bool(real_fit.get(case[0]))

    def fake_twin(case) -> bool:
        return bool(fake_fit.get(case[0]))

    verdict = sv.verify_claim(agent, sv.Claim(
        text="composer-authored sense-select Program picks the gloss that fits the context",
        mechanism=mechanism, control_cases=control, fake_twin=fake_twin,
        prior_cases=prior, ground_support=_language_faculty_ground_reference))
    if not verdict.get("accepted"):
        return {"grounded": False, "path": "compose_sense_select", "concern": list(keys),
                "grounded_relations": rels, "program": program, "verified": verdict,
                "wall": ("the authored SELECT Program failed #2 verification (control did not "
                         f"discriminate real from context-blind): {verdict.get('reason')}")}

    # INSTALL — the authored Program is now a live, named graph-resident Program node.
    prog_json = _json.dumps(program)
    existing = None
    for n in sub.nodes("Program"):
        if sub.node(n)["attrs"].get("name") == lfo.SENSE_SELECT_PROGRAM:
            existing = n
            break
    if existing is None:
        prog_node = sub.add_node("Program", {
            "name": lfo.SENSE_SELECT_PROGRAM, "program": prog_json,
            "form": "term_tree", "authored_by": "language_faculty_composer",
            "concern": tag})
        if ag_node is not None:
            try:
                sub.add_edge_unchecked(ag_node, "authored", prog_node)
            except Exception:
                pass
    else:
        prog_node = existing

    return {"grounded": True, "path": "compose_sense_select", "concern": list(keys),
            "form": "sense_select_program", "grounded_relations": rels,
            "served_by": "python", "program_name": lfo.SENSE_SELECT_PROGRAM,
            "program": program, "program_node": str(prog_node),
            "gate_reason": gres.reason, "verified": verdict,
            "leaf": "sense_score_term (a candidate sense's context-fit as a graph Term)",
            "held_faculty_call": ("the raw WordNet SENSE ENUMERATION (dictionary_lexicon._enumerate_"
                                  "features) that MEASURES each candidate's category / Lesk overlap / "
                                  "rank / freq — external lexical I/O, no Term reads WordNet; the honest "
                                  "leaf boundary"),
            "how": ("I GROUND the LANGUAGE concern ('pick the sense that fits the context') by "
                    "composing a SELECT Program: the 'sense' relation grounds the language LEAF — the "
                    "sense-fit SCORE Term over each candidate's measured features (category fit + Lesk "
                    "gloss overlap with the sentence + rank + freq). I assemble Argmax(source="
                    "sel.has_candidate, var=cand, value=sense_score_term), ADMIT it through the gate "
                    "(it picks the context-fitting sense for every labelled case), VERIFY it with a "
                    "discriminative control (a CONTEXT-BLIND twin that drops the Lesk term FAILS a "
                    "context-dependent case), and install it live as a named Program. The raw WordNet "
                    "enumeration that measures a candidate's features stays a held-faculty call — the "
                    "honest leaf boundary; the SCORE + ARGMAX composition is mine.")}


def _memory_faculty_ground_reference(sub):
    """The cache-aside claim's support reaches an EXTERNAL reference anchor: the
    memoized lookup reads an external lexical reference (WordNet / the reference
    slab). A real teacher-style exchange, anchored via a TaughtHint{origin:
    'teacher_hook'} the grounding-reach machinery maps to a TeacherAnchor. Mirrors
    _language_faculty_ground_reference / consumption_quality._ground_reference."""
    node = sub.add_node("Collapse", {"label": "memory_faculty_support"})
    th = sub.add_node("TaughtHint", {"origin": "teacher_hook",
                                     "topic": "lexical_reference",
                                     "answer": "external reference reading, memoized (cache-aside)"})
    sub.add_edge_unchecked(node, "grounded_in", th)
    return node


def _compose_memory_faculty(agent, keys, rels) -> dict[str, Any]:
    """COMPOSE A CACHE-ASIDE Program over the MEMORY faculty — the self-build
    composer's MEMORY path. It closes the THIRD frontier the consumption-quality fix
    surfaced honestly — that fix memoized lookups with ADAPTER logic (consumption_
    quality.GroundingCache, a hot dict). Now the jabberwock authors the cache-aside
    SERVE decision itself, over a GRAPH-RESIDENT hot store (a HotStore whose CacheEntry
    neighbours are the hot tier, on a substrate with the Rust memory faculty composed
    as its bound — memory_bound).

    The 'store' relation grounds the MEMORY LEAF chained under the cache: the
    serve-from-store Term (domains/memory_faculty_ops.cache_serve_program —
    Attr(Pick(Filter(store.has_entry, e, e.ckey==key)), 'cval')). The composer
    assembles it, GATES it (its forward model serves the byte-identical value on a
    warm repeat), VERIFIES it (#2: a NO-STORE twin that never serves FAILS — it never
    memoizes), and installs it LIVE only if BOTH pass. Honest reach: the composer
    authors the cache-aside SERVE (hit/miss) DECISION; the UNDERLYING LOOKUP being
    memoized + the RAW STORE PUT stay held-faculty CALLS (external I/O + a
    side-effecting store write — no Term performs either)."""
    from domains import memory_faculty_ops as mfo
    from domains import admissibility_gate as ag
    from domains import self_verification as sv
    import json as _json

    sub, native, ag_node = _resolve_agent(agent)
    rp = {r[0] for r in rels}
    tag = "_".join(str(k) for k in keys)

    if "store" not in rp:
        # only the serve-from-store leaf is exposed; a 'cache' concern that does NOT
        # ground the store leaf has no memory leaf to chain — honest wall.
        return {"grounded": False, "path": "compose_memory_faculty", "concern": list(keys),
                "grounded_relations": rels,
                "wall": ("the 'cache' concern grounded, but no memory LEAF did — only the "
                         "serve-from-store op ('store') is exposed as a Program-callable leaf so far; "
                         "nothing to chain under the cache (extend memory_faculty_ops, not fabricate)")}

    # AUTHOR — the cache-aside SERVE Program + its no-store fake twin.
    program = mfo.cache_serve_program()
    fake = mfo.never_serve_program()

    # the labelled control: a warm call served from the store is byte-identical to
    # the cold value AND is a HIT (the underlying lookup is not re-run). The
    # underlying leaf is the EXPENSIVE sense lookup (the real memoization target).
    from domains import consumption_quality as cq
    _SENT = {
        "water": "strip electrons from suitable substances such as water",
        "cell": "the cell membrane surrounds the nucleus organelle tissue biology",
        "mole": "a skin mole with pigment melanin benign growth lesion",
        "glucose": "glucose sugar energy metabolism carbohydrate",
        "volcano": "the volcano erupted lava magma ash eruption",
    }
    control = list(_SENT.keys())

    def _leaf(word):
        return cq.sense_in_context(word, _SENT[word])

    def _cache_correct(prog, word) -> bool:
        # cold value (uncached) + warm value (served after one fill) must match AND
        # the warm call must be a HIT (served from the store, not recomputed).
        store = mfo.HotStore()
        cold = _leaf(word)
        mfo.cached_call(prog, store, word, _leaf)   # fill
        h0 = store.hits
        warm = mfo.cached_call(prog, store, word, _leaf)   # warm
        return warm == cold and store.hits > h0

    real_ok = {w: _cache_correct(program, w) for w in control}
    fake_ok = {w: _cache_correct(fake, w) for w in control}

    # ADMISSIBILITY GATE — admit only if the authored Program's forward model serves
    # a correct HIT for every labelled case.
    object_props = {f"cache::{w}": bool(real_ok.get(w)) for w in control}
    stated_props = {f"cache::{w}": True for w in control}
    gres = ag.gate_object(object_props=object_props, stated_props=stated_props,
                          question_text="", substrate=None)
    if not gres.admitted:
        return {"grounded": False, "path": "compose_memory_faculty", "concern": list(keys),
                "grounded_relations": rels, "program": program, "gate_reason": gres.reason,
                "wall": ("the authored cache-aside Program did NOT pass the admissibility gate (its "
                         f"forward model failed a labelled correct-HIT constraint): {gres.reason}")}

    # #2 VERIFY-BEFORE-TRUST — a discriminative control whose no-store twin fails.
    def mechanism(word) -> bool:
        return bool(real_ok.get(word))

    def fake_twin(word) -> bool:
        return bool(fake_ok.get(word))

    verdict = sv.verify_claim(agent, sv.Claim(
        text="composer-authored cache-aside serves the byte-identical value as a warm HIT",
        mechanism=mechanism, control_cases=control, fake_twin=fake_twin,
        prior_cases=control, ground_support=_memory_faculty_ground_reference))
    if not verdict.get("accepted"):
        return {"grounded": False, "path": "compose_memory_faculty", "concern": list(keys),
                "grounded_relations": rels, "program": program, "verified": verdict,
                "wall": ("the authored cache-aside Program failed #2 verification (control did not "
                         f"discriminate real from the no-store twin): {verdict.get('reason')}")}

    # INSTALL — the authored Program is now a live, named graph-resident Program node.
    prog_json = _json.dumps(program)
    existing = None
    for n in sub.nodes("Program"):
        if sub.node(n)["attrs"].get("name") == mfo.CACHE_SERVE_PROGRAM:
            existing = n
            break
    if existing is None:
        prog_node = sub.add_node("Program", {
            "name": mfo.CACHE_SERVE_PROGRAM, "program": prog_json,
            "form": "term_tree", "authored_by": "memory_faculty_composer",
            "concern": tag})
        if ag_node is not None:
            try:
                sub.add_edge_unchecked(ag_node, "authored", prog_node)
            except Exception:
                pass
    else:
        prog_node = existing

    return {"grounded": True, "path": "compose_memory_faculty", "concern": list(keys),
            "form": "cache_aside_program", "grounded_relations": rels,
            "served_by": "python", "program_name": mfo.CACHE_SERVE_PROGRAM,
            "program": program, "program_node": str(prog_node),
            "gate_reason": gres.reason, "verified": verdict,
            "leaf": "cache_serve_program (serve-from-store hit/miss decision as a graph Term)",
            "held_faculty_call": ("the UNDERLYING LOOKUP being memoized (a sense/POS consult that reads "
                                  "WordNet / the reference slab) + the RAW STORE PUT (add_node CacheEntry) "
                                  "— external I/O + a side-effecting store write, no Term performs either; "
                                  "the honest leaf boundary"),
            "how": ("I GROUND the MEMORY concern ('cache/memoize this consult') by composing a "
                    "CACHE-ASIDE Program over a GRAPH-RESIDENT hot store: the 'store' relation grounds "
                    "the memory LEAF — the serve-from-store Term Attr(Pick(Filter(store.has_entry, e, "
                    "e.ckey==key)), 'cval'), over a HotStore bounded by the Rust memory faculty "
                    "(memory_bound). A HIT serves the stored value; a MISS evaluates to None and the "
                    "harness computes + puts. I ADMIT it through the gate (it serves the byte-identical "
                    "value on a warm repeat), VERIFY it with a discriminative control (a NO-STORE twin "
                    "that never serves FAILS — it never memoizes), and install it live as a named "
                    "Program. The underlying lookup + the raw store put stay held-faculty calls — the "
                    "honest leaf boundary; the cache-aside SERVE DECISION is mine.")}


# ---------------------------------------------------------------------------
# GRAPH-RESIDENT COMPOSERS — the migration this module's authoring machinery
# is undergoing (per CLAUDE.md: "self-improvement over ALL parts requires the
# agent's AUTHORING MACHINERY itself to be graph data it can inspect and
# vary"). Each `_compose_*_rule` function above still exists as the Python
# REFERENCE (unedited) — but for the composers listed in
# `_GRAPH_COMPOSER_SEEDS`, an EQUIVALENT graph-resident meta-rule (a Rule
# NODE, not a Python function — see seeds/composer_comprehension_graph.json's
# pilot + seeds/composer_<name>_graph.json here) now mints the SAME rules
# from a `ComposeRequest` trigger. `ground_concern` (below) tries this graph
# path FIRST for a migrated composer/branch combination; only when the graph
# path is inapplicable (branch not migrated) or fails to produce the expected
# rule names does it fall through to the Python builder above — this is the
# migration LEDGER: every `ground_concern` result now carries `served_by`
# ("graph" or "python"), naming which path actually authored the rule(s).
#
# WHY a thin dict-reconstruction, not a redesign of the return shape: several
# tests (tests/test_browse_authoring.py, tests/test_structured_find.py,
# tests/test_attention_authoring.py — the CLAUDE.md-pinned regression gate)
# assert the EXACT Python-builder dict shape (`rules`/`rule` as dicts with
# `name`/`match`/`where`/`effects` keys, `path`/`form` strings, rule_count
# deltas). The graph path reconstructs that exact shape by reading the
# now-live struct-store rule(s) back via `native.export_rules()` (the SAME
# dialect the Python builders' own return dicts use) once `__mint__` has
# compiled them — so a caller cannot tell, from the return value alone,
# whether the rule was authored by Python or by the graph (only `served_by`
# says so). The RULES THEMSELVES differ in provenance: authored by a graph
# Rule node's own effects, not by this file's Python at request time.
# ---------------------------------------------------------------------------
def _ensure_graph_composer_seed(sub, native, ag_node, seed_id: str) -> None:
    """Idempotently install one composer-graph seed (a single meta-rule Rule
    node) by id, mirroring `_ensure_seed_chain`'s guard but scoped to one
    seed at a time (composer routing installs whichever seed the picked
    branch needs, not the whole chain up front)."""
    _ensure_seed_chain(sub, native, ag_node, (seed_id,))


def _decode_surface_wire(v):
    """`ToJsonString`'s result, read back off an UN-FIRED rule TEMPLATE's own
    effect literal via `export_rules()`, round-trips as a `{"__surface__":
    ..., "kind": "text", "payload": <hex>}` wire blob rather than a plain
    Python `str` (a template-export representation detail — see tests/
    test_experiment_composer_graph.py's own `_surface_or_str` helper, which
    every test in THIS module previously had to duplicate by hand). Recurse
    through a rule dict and decode every such blob into the plain string it
    carries, so a caller of `_ground_via_graph_meta` sees EXACTLY the shape
    the Python `_compose_*` builders' own `_json.dumps(...)`-built strings
    have — mechanical wire-decoding, not a content change (a real FIRED
    node's attrs never carry this wrapper in the first place; only the
    compiled-but-not-yet-matched template does)."""
    if isinstance(v, dict):
        if "payload" in v and ("__surface__" in v or v.get("kind") == "text"):
            try:
                return bytes.fromhex(v["payload"]).decode("utf-8")
            except Exception:
                return v
        return {k: _decode_surface_wire(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_decode_surface_wire(x) for x in v]
    return v


def _ground_via_graph_meta(agent, seed_id: str, trigger_edge: str, tag: str,
                            extra_attrs: dict, expected_names: list[str],
                            *, max_ticks: int = 10) -> Optional[dict]:
    """Mechanical I/O: install the named composer-graph seed (idempotent),
    mint a `ComposeRequest{tag, composed=0.0, **extra_attrs}` trigger edge
    from the agent, tick the graph until fixed point (or `max_ticks`), then
    read back whether ALL `expected_names` are now live in the struct rule
    store (`native.export_rules()` — populated by the meta-rule's own
    `set_rule_clause(..., "__mint__", ...)` effects, never by a Python
    `add_rule` call here). Returns None (caller falls back to the Python
    builder) if the seed fails to install or the expected rules did not
    appear — never a partial/fabricated result. No rule CONTENT is decided
    here; this only triggers the graph's own composer and reads its output
    back in the Python builders' own `export_rules()` dialect so callers
    (and the CLAUDE.md-pinned regression tests) see the identical shape."""
    sub, native, ag_node = _resolve_agent(agent)
    try:
        _ensure_graph_composer_seed(sub, native, ag_node, seed_id)
    except Exception:
        return None
    attrs = {"tag": tag, "composed": 0.0}
    attrs.update(extra_attrs or {})
    try:
        cr = sub.add_node("ComposeRequest", attrs)
        native.add_edge_unchecked(ag_node, trigger_edge, cr)
        for _ in range(max_ticks):
            progressed = sub.tick()
            if isinstance(progressed, (int, float)) and progressed == 0:
                break
    except Exception:
        return None
    try:
        exported = [r for r in native.export_rules() if isinstance(r, dict)]
    except Exception:
        return None
    by_name = {r.get("name"): r for r in exported}
    if not all(n in by_name for n in expected_names):
        return None
    try:
        sub.set_attr(cr, "served_by", "graph")
    except Exception:
        pass
    ordered = [_decode_surface_wire(by_name[n]) for n in expected_names]
    idxs = [i for i, r in enumerate(exported) if r.get("name") in expected_names]
    return {"rules": ordered, "rule_idx": idxs, "compose_request": cr}


def ensure_grounding_gap_edges(agent) -> int:
    """Mechanical adapter I/O — the GROUNDING-GUARD's trigger-wiring half.
    `domains.grounding_reach.flag_ungrounded_confident` (the substrate; not
    touched here) already computed the confident-but-ungrounded verdict and
    minted a `GroundingGap` node for each hit — this function does not
    re-decide anything, it only EXPOSES an already-minted flag to the rule
    engine as an `agent -has_grounding_gap-> gap` edge (idempotent, has_edge-
    guarded), the SAME mechanical idiom `induce_concern` uses for `agent
    -observed-> observation` and `_ensure_shape_decode_loop` uses for its
    seed-guard. The RESPONSE to a GroundingGap (escalate to active cognition)
    is the agent's own authored rule (composer_grounding_guard_graph's
    `escalate_grounding_gap_<tag>`, dispatched via `ground_concern`'s
    'escalate' relation head) — this function only makes the flag matchable.
    Idempotently loads composer_grounding_guard_graph first (mechanical seed
    I/O) so the `has_grounding_gap`/`GroundingGap` types are registered in Γ
    before the edge is added, whether or not the guard rule has been
    authored yet. Returns the number of NEWLY wired edges this call."""
    sub, native, ag_node = _resolve_agent(agent)
    if ag_node is None:
        return 0
    try:
        _ensure_seed_chain(sub, native, ag_node, ("composer_grounding_guard_graph",))
    except Exception:
        return 0
    wired = 0
    for g in sub.nodes("GroundingGap"):
        if sub.has_edge(ag_node, "has_grounding_gap", g):
            continue
        try:
            sub.add_edge(ag_node, "has_grounding_gap", g)
        except Exception:
            continue
        wired += 1
    return wired


def _route_experiment_composer(agent, keys, rels, rp: set) -> Optional[dict]:
    """The 'experiment' composer's graph-resident dispatch — the metascience
    twin of `_try_graph_composer`'s other branches, factored out only
    because it needs a bit more per-combo bookkeeping (the acting/structural-
    variant Argmax needs the axis's own `residual_predicates` spliced in as
    an extra_attr, and callers of `ground_concern` expect `acting_variant`/
    `structural_variant` fields back) than a bare `_single`/`_multi` call
    gives. Covers the FULL no-'test' family (any combination of judge/adopt,
    with any of the refine-only relations vary/send/gradient/structure/embed
    along for the ride — see the `"test" not in rp` branch below for why
    those are safe to ignore) PLUS the FULL 'test'-anchored family: EVERY
    grounded-relation combination that includes 'test' now routes through
    ONE parametric meta-rule (`compose_experiment_mint_parametric` in
    `seeds/composer_experiment_graph.json`, driven by has_send/has_vary/
    has_judge/has_gradient/has_structure/has_embed flags on the triggering
    ComposeRequest) — not just the 5 exact combos former per-combo meta-
    rules (now retired) hard-coded. `ground_concern` only falls through to
    `_compose_experiment_rule` any more when NEITHER test, judge, NOR adopt
    grounded — the same genuine no-authoring wall `_compose_experiment_rule`
    itself reports (see its own `if not rules:` message)."""
    tag = "_".join(str(k) for k in keys)
    common = {"grounded": True, "concern": list(keys), "grounded_relations": rels, "served_by": "graph",
              "path": "compose_experiment_rule", "form": "experiment_rule"}

    if "replay" in rp:
        # CONVERSATION-REPLAY FAMILY (Wave 3): not yet migrated to the graph
        # meta-rule (compose_experiment_mint_parametric carries no has_replay
        # flag, no conversation world-pin, no reply-ablation delta). Honest
        # None — `ground_concern` falls through to the Python builder
        # `_compose_experiment_rule`'s conversation branch, the documented
        # migration-ledger fallback (see _try_graph_composer's own docstring).
        return None

    if "test" not in rp:
        # NO-'test' FAMILY: `_compose_experiment_rule` nests EVERY refine-only
        # relation (vary/send/gradient/structure/embed) inside `if "test" in
        # rp:` -- without 'test' the mint rule never exists for them to
        # refine, so they are INERT (Python ignores them too; see that
        # function's own `if not rules:` wall message: "vary/send/... alone
        # only refine parts, nothing to author"). The Python builder's
        # observable output for ANY no-'test' rp is therefore exactly:
        # (judge rule if 'judge' in rp) + (adopt rule if 'adopt' in rp), in
        # that order -- so this ONE branch, firing the judge and/or adopt
        # meta-rule for exactly the grounded subset and dropping the inert
        # relations, covers every no-'test' combo composer_experiment_graph
        # .json's judge/adopt meta-rules mint for (judge alone, adopt alone,
        # judge+adopt, and any vary/send-decorated variant of those) without
        # needing a new COMBINED meta-rule -- the judge and adopt rules never
        # interact with each other in the Python oracle (no shared match
        # vars, no ordering dependency beyond list-append order), so firing
        # the two existing single-purpose meta-rules independently and
        # concatenating reproduces the oracle's output exactly. A combo with
        # NEITHER judge nor adopt grounded (e.g. {vary}, {send}, {vary,
        # send}) authors nothing in EITHER path -- return None so
        # `ground_concern` falls through to `_compose_experiment_rule`'s own
        # honest `grounded: False` wall, never fabricated here.
        want_judge = "judge" in rp
        want_adopt = "adopt" in rp
        if not want_judge and not want_adopt:
            return None
        rules: list = []
        rule_idx: list = []
        if want_judge:
            rj = _ground_via_graph_meta(agent, "composer_experiment_graph", "wants_experiment_judge_rule", tag, {},
                                         ["judge_experiment_outcome_" + tag])
            if rj is None:
                return None
            rules += rj["rules"]
            rule_idx += rj["rule_idx"]
        if want_adopt:
            ra = _ground_via_graph_meta(agent, "composer_experiment_graph", "wants_experiment_adopt_rule", tag, {},
                                         ["mark_adopt_ready_" + tag])
            if ra is None:
                return None
            rules += ra["rules"]
            rule_idx += ra["rule_idx"]
        return {**common, "rules": rules, "rule_idx": rule_idx,
                "acting_variant": None, "structural_variant": None,
                "how": "I GROUND the no-test self-experiment concern via the GRAPH-RESIDENT "
                       "compose_experiment_graph meta-rule's judge and/or adopt branch(es) -- "
                       "vary/send/gradient/structure/embed are INERT without 'test' (the mint rule "
                       "they'd refine doesn't exist), exactly as the Python builder ignores them too, "
                       "so this fires the judge meta-rule if 'judge' grounded and/or the adopt "
                       "meta-rule if 'adopt' grounded, in that order, and drops the rest."}

    # 'test'-ANCHORED FAMILY: every combination that grounds 'test' authors a
    # mint rule -- ONE parametric meta-rule (compose_experiment_mint_parametric,
    # seeds/composer_experiment_graph.json) mints it for ANY combination of
    # send/vary/judge/gradient/structure/embed (not just the 5 exact combos
    # the now-retired per-combo meta-rules hard-coded), driven by boolean
    # flags carried on the triggering ComposeRequest. judge/adopt are fired
    # via their OWN independent, unchanged meta-rules and concatenated --
    # the SAME shape the no-'test' branch above already established (they
    # never interact with the mint rule's own match/effects, no shared vars,
    # no ordering dependency beyond list-append order).
    sub0, native0, _ag0 = _resolve_agent(agent)
    preds = []
    for n0 in sub0.nodes("CapabilityAxis"):
        at0 = sub0.node(n0)["attrs"]
        if at0.get("induced") and list(at0.get("capability_keys") or []) == [str(k) for k in keys]:
            preds = list(at0.get("residual_predicates") or [])
            break
    want_gradient = "gradient" in rp
    want_structure = "structure" in rp
    if want_gradient or want_structure:
        try:
            _ensure_acting_rule_provenance(sub0, native0)
        except Exception:
            pass
    if want_structure:
        try:
            _ensure_edit_ops(sub0)
        except Exception:
            pass
        try:
            # A8 precompute (MAC_FAC_A8_PREREG.md/RESULTS.md): stamps the
            # four applicable_<kind> flags onto every RuleSummary so the
            # graph-native `epick` Argmax can gate its candidates on them --
            # the SAME call site A7's own where_signature_json priming
            # already runs from, unconditionally, before
            # compose_experiment_mint_parametric ever fires.
            _ensure_editop_applicability(sub0)
        except Exception:
            pass

    flags = {
        "has_send": 1.0 if "send" in rp else 0.0,
        "has_vary": 1.0 if "vary" in rp else 0.0,
        "has_judge": 1.0 if "judge" in rp else 0.0,
        "has_gradient": 1.0 if want_gradient else 0.0,
        "has_structure": 1.0 if want_structure else 0.0,
        "has_embed": 1.0 if "embed" in rp else 0.0,
        "residual_predicates": preds,
    }
    rm = _ground_via_graph_meta(agent, "composer_experiment_graph", "wants_experiment_mint_parametric", tag,
                                 flags, ["author_experiment_from_residual_" + tag])
    if rm is None:
        return None
    rules = list(rm["rules"])
    rule_idx = list(rm["rule_idx"])
    mint = next((rr for rr in rules if rr["name"] == "author_experiment_from_residual_" + tag), None)

    if "judge" in rp:
        rj = _ground_via_graph_meta(agent, "composer_experiment_graph", "wants_experiment_judge_rule", tag, {},
                                     ["judge_experiment_outcome_" + tag])
        if rj is None:
            return None
        rules += rj["rules"]
        rule_idx += rj["rule_idx"]
    if "adopt" in rp:
        ra = _ground_via_graph_meta(agent, "composer_experiment_graph", "wants_experiment_adopt_rule", tag, {},
                                     ["mark_adopt_ready_" + tag])
        if ra is None:
            return None
        rules += ra["rules"]
        rule_idx += ra["rule_idx"]

    # acting_variant / structural_variant -- read back off the mint rule's
    # own SeedDelta attrs, the SAME decode the retired full/structure
    # branches used (structure takes priority, matching the Python oracle
    # and the meta-rule's own IfThenElse precedence).
    acting_variant = None
    structural_variant = None
    if mint is not None:
        try:
            delta_attrs = mint["effects"][1][3]
        except Exception:
            delta_attrs = {}
        if not isinstance(delta_attrs, dict):
            delta_attrs = {}
        def _find_variant_rule_json(removed_rule: str):
            # The mint rule's own SeedDelta.add_rules carries the actual
            # variant rule JSON this concern's Experiment dispatches (see
            # tests/test_structural_variant.py / test_acting_variant.py,
            # which install it directly via mint_experiment(add_rules=[...])
            # — the SAME shape the Python oracle's own `structural_report`/
            # `acting_report` "rule" field carries). Both a structural
            # (`<rule>_structvariant_<tag>`) and an acting (`<rule>_variant_
            # <tag>`) variant are named with the removed rule as PREFIX
            # (never a bare suffix match — the embed judge-variant is named
            # `judge_experiment_outcome_variant_<tag>`, which could
            # false-positive on a plain "_variant_<tag>" suffix check).
            if not removed_rule:
                return None
            try:
                import json as _json4
                add_rules_list = _json4.loads(delta_attrs.get("add_rules") or "[]")
            except Exception:
                return None
            for item in add_rules_list:
                if isinstance(item, dict) and item.get("name", "").startswith(removed_rule + "_"):
                    return item
            return None

        if want_structure and "judge" in rp:
            kind = delta_attrs.get("edit_op_kind")
            act_rule_varied = delta_attrs.get("act_rule_varied") or ""
            if kind and act_rule_varied:
                structural_variant = {"built": True, "kind": kind, "removed_rule": act_rule_varied,
                                       "rule": _find_variant_rule_json(act_rule_varied),
                                       "how": "graph-native: two-stage Argmax (RuleSummary then EditOp) over "
                                              "cr.residual_predicates, then RewriteTreeNodes/ListDrop+guard/"
                                              "IndexAt+MkDict applied to FromJsonString(rule_json), baked "
                                              "once at compose time by compose_experiment_mint_parametric's "
                                              "shared structure-family Let binding (tests/"
                                              "test_editop_dialect_terms.py's pilot chain, reused live)."}
            elif kind:
                structural_variant = {"built": False, "kind": kind,
                                       "wall": (f"the picked op {kind!r} is structurally INERT on the picked "
                                                "acting rule (graph-native RewriteTreeNodes/ListDrop found no "
                                                "genuine site) — a discovered null for THIS (op, rule) "
                                                "pairing, not fabricated")}
            else:
                structural_variant = {"built": False,
                                       "wall": "the graph-native RuleSummary or EditOp Argmax abstained "
                                               "(no genuine overlap) — an honest null, not a random pick"}
        elif want_gradient and "judge" in rp:
            act_rule_varied = delta_attrs.get("act_rule_varied") or ""
            if act_rule_varied:
                acting_variant = {"built": True, "removed_rule": act_rule_varied,
                                   "shift": delta_attrs.get("act_shift"),
                                   "rule": _find_variant_rule_json(act_rule_varied),
                                   "how": "graph-native: Argmax over RuleSummary provenance, then "
                                          "FromJsonString(rule_json) -> ShiftThresholdLits -> ToJsonString, "
                                          "baked once at compose time by compose_experiment_mint_parametric's "
                                          "shared gradient-family Let binding (tests/"
                                          "test_dialect_experiment_terms.py's pilot chain, reused live)."}
            else:
                acting_variant = {"built": False,
                                   "wall": "the graph-native RuleSummary Argmax abstained (no genuine "
                                           "overlap) or the picked rule carries no shiftable threshold"}

    return {**common, "rules": rules, "rule_idx": rule_idx,
            "acting_variant": acting_variant, "structural_variant": structural_variant,
            "how": "I GROUND the 'test'-anchored self-experiment concern via the GRAPH-RESIDENT "
                   "compose_experiment_mint_parametric meta-rule (seeds/composer_experiment_graph.json) — "
                   "ONE rule mints author_experiment_from_residual_<tag> for this exact grounded-relation "
                   "combination, driven by has_send/has_vary/has_judge/has_gradient/has_structure/"
                   "has_embed flags on the triggering ComposeRequest (not five separate per-combo rules "
                   "any more); judge and/or adopt fire via their own independent meta-rules and are "
                   "concatenated when grounded."}


def _route_self_correct_composer(agent, keys, rels, rp: set) -> Optional[dict]:
    """The 'self_correct' composer's graph-resident dispatch — TIER 5 COGNITION
    (autonomous self-correction), needs custom handling (not `_single`/`_multi`)
    because `compose_self_correct_graph` (seeds/composer_self_correct_graph.json)
    mints TWO DIFFERENT kinds of graph data from one ComposeRequest: a Rule (the
    ATTEMPT-GATE, `self_correct_gate_<tag>` — verifiable via `native.export_rules()`,
    the same dialect every other composer branch reads back) and a Program (the
    RANK Term, `self_correct_rank_<tag>` — a Program is graph DATA the rule engine
    never compiles into its rule store, so `_ground_via_graph_meta`'s export_rules()
    -only check cannot see it; read back via `_load_program` instead, the SAME
    lookup `_pick_composer` itself uses for `composer_pick`).

    `self_correct_gate_<tag>` decides WHETHER a predicted-divergence Impasse is
    worth the expense of correcting (a residual-threshold priority gate, mirroring
    `composer_escalation_gate_graph.json`'s cost_salience shape) — it marks
    `impasse.correct_ready`, which `domains.self_correct_dispatch.
    scan_and_self_correct` (the mechanical host hook; `domains.self_correction.
    intervene_on_divergence` is an in-process Python call a Rust rule effect
    cannot make itself) reads back before ever calling the machinery. `self_
    correct_rank_<tag>` decides WHICH converging candidate to prefer (an Argmin
    over a mechanically-measured structural-footprint cost — cheaper/less-
    invasive wins) — the dispatch hook consults it to reorder `domains.
    self_correction._default_candidates`'s own list before handing it to
    `intervene_on_divergence`, which still performs every mechanical sub-step
    (imagine, predict, denylist veto, adopt-or-propose) unchanged."""
    sub0, native0, ag0 = _resolve_agent(agent)
    if ag0 is None:
        return None
    tag = "_".join(str(k) for k in keys)
    try:
        _ensure_graph_composer_seed(sub0, native0, ag0, "composer_self_correct_graph")
    except Exception:
        return None
    try:
        cr = sub0.add_node("ComposeRequest", {"tag": tag, "composed": 0.0})
        native0.add_edge_unchecked(ag0, "wants_self_correct_rule", cr)
        for _ in range(10):
            progressed = sub0.tick()
            if isinstance(progressed, (int, float)) and progressed == 0:
                break
    except Exception:
        return None

    gate_name = "self_correct_gate_" + tag
    rank_name = "self_correct_rank_" + tag
    try:
        exported = [r for r in native0.export_rules() if isinstance(r, dict)]
    except Exception:
        return None
    by_name = {r.get("name"): r for r in exported}
    gate_rule = by_name.get(gate_name)
    rank_program = _load_program(sub0, rank_name)
    if gate_rule is None or rank_program is None:
        return None
    try:
        sub0.set_attr(cr, "served_by", "graph")
    except Exception:
        pass
    gate_rule = _decode_surface_wire(gate_rule)
    idxs = [i for i, r in enumerate(exported) if r.get("name") == gate_name]
    return {"grounded": True, "concern": list(keys), "grounded_relations": rels, "served_by": "graph",
            "path": "compose_self_correct_rule", "form": "self_correct_rule",
            "rule": gate_rule, "rule_idx": (idxs[0] if idxs else None),
            "program": rank_program, "program_name": rank_name, "gate_name": gate_name,
            "how": ("I GROUND the self-correction concern via the GRAPH-RESIDENT compose_self_correct_graph "
                    "meta-rule (seeds/composer_self_correct_graph.json): it minted self_correct_gate_<tag> "
                    "(a Rule — WHETHER a predicted-divergence Impasse's own CollapseModel residual clears "
                    "a cost-worth-it threshold, marking correct_ready) and self_correct_rank_<tag> (a "
                    "Program — an Argmin over candidate structural-footprint cost, picking the cheaper fix) "
                    "itself from a ComposeRequest, not Python authoring at request time.")}


def _try_graph_composer(agent, composer_name: str, keys, rels, rp: set) -> Optional[dict]:
    """Route to a graph-resident meta-rule for the (composer, grounded-
    relation-set) combination, when a migrated one exists — mechanical
    dispatch (name + rp membership test), never a decision about WHAT to
    build (that's the graph's own meta-rule effects). Returns None to signal
    'no migrated graph branch for this combination' (caller falls back to
    the Python `_COMPOSER_REGISTRY` builder) — an honest miss, not a wall."""
    tag = "_".join(str(k) for k in keys)
    common = {"grounded": True, "concern": list(keys), "grounded_relations": rels, "served_by": "graph"}

    def _single(path, form, seed_id, edge, extra_attrs, name, how):
        r = _ground_via_graph_meta(agent, seed_id, edge, tag, extra_attrs, [name])
        if r is None:
            return None
        return {**common, "path": path, "form": form, "rule": r["rules"][0],
                "rule_idx": r["rule_idx"][0], "how": how}

    def _multi(path, form, seed_id, edge, extra_attrs, names, how):
        r = _ground_via_graph_meta(agent, seed_id, edge, tag, extra_attrs, names)
        if r is None:
            return None
        return {**common, "path": path, "form": form, "rules": r["rules"],
                "rule_idx": r["rule_idx"], "how": how}

    if composer_name == "control":
        return _multi("compose_control_rule", "control_rule", "composer_control_graph",
                       "wants_control_rule", {}, ["default_no_response_" + tag, "control_my_body_" + tag],
                       "I GROUND 'what I control' via the GRAPH-RESIDENT compose_control_graph "
                       "meta-rule (seeds/composer_control_graph.json), which minted these two rules "
                       "itself from a ComposeRequest — not Python authoring at request time.")

    if composer_name == "grouping":
        return _multi("compose_grouping_rule", "grouping_rule", "composer_grouping_graph",
                       "wants_grouping_rule", {}, ["fuse_whole_" + tag, "whole_cells_" + tag],
                       "I COMPOSE the order-N whole via the GRAPH-RESIDENT compose_grouping_graph "
                       "meta-rule, which minted fuse_whole/whole_cells itself.")

    if composer_name == "decision":
        return _single("compose_decision_rule", "decision_rule", "composer_decision_graph",
                        "wants_decision_rule", {}, "decide_under_uncertainty_" + tag,
                        "I GROUND acting-under-uncertainty via the GRAPH-RESIDENT "
                        "compose_decision_graph meta-rule.")

    if composer_name == "construction":
        return _single("compose_construction_rule", "construction_rule", "composer_construction_graph",
                        "wants_construction_rule", {}, "construct_function_frames_content_" + tag,
                        "I GROUND the syntactic concern via the GRAPH-RESIDENT "
                        "compose_construction_graph meta-rule.")

    if composer_name == "distributional":
        return _single("compose_distributional_rule", "distributional_rule", "composer_distributional_graph",
                        "wants_distributional_rule", {}, "distributional_function_split_" + tag,
                        "I GROUND the function/content split via the GRAPH-RESIDENT "
                        "compose_distributional_graph meta-rule.")

    if composer_name == "attention":
        return _single("compose_attention_rule", "attention_rule", "composer_attention_graph",
                        "wants_attention_rule", {}, "look_when_frame_advances_" + tag,
                        "I GROUND 'when should I look' via the GRAPH-RESIDENT compose_attention_graph "
                        "meta-rule.")

    if composer_name == "communicate":
        if not {"source", "decompose", "communicate"} <= rp:
            return None   # only the full combo is migrated; other combos fall to Python
        return _single("compose_communicate_rule", "communicate_rule", "composer_communicate_graph",
                        "wants_communicate_rule", {}, "communicate_what_i_see_" + tag,
                        "I GROUND the communicate concern via the GRAPH-RESIDENT "
                        "compose_communicate_graph meta-rule (full source+decompose+communicate combo).")

    if composer_name == "browse":
        if "constrain" in rp:
            return _multi("compose_browse_rule", "browse_structured_rule", "composer_browse_constrained_graph",
                           "wants_browse_constrained_rule", {},
                           ["choose_affordance_structured_" + tag, "browse_goal_satisfied_structured_" + tag],
                           "I GROUND the constrained affordance choice via the GRAPH-RESIDENT "
                           "compose_browse_constrained_graph meta-rule.")
        return _multi("compose_browse_rule", "browse_rule", "composer_browse_graph",
                       "wants_browse_rule", {},
                       ["choose_affordance_by_relevance_" + tag, "browse_goal_satisfied_when_seen_" + tag],
                       "I GROUND choosing WHICH AFFORDANCE via the GRAPH-RESIDENT compose_browse_graph "
                       "meta-rule.")

    if composer_name == "comprehension":
        if "find" in rp and "constrain" in rp:
            return _multi("compose_comprehension_rule", "find_directive_structured_rule",
                           "composer_comprehension_find_graph", "wants_find_constrained_rule", {},
                           ["comprehend_find_directive_structured_" + tag,
                            "bind_find_target_structured_" + tag,
                            "bind_find_constraint_structured_" + tag],
                           "I GROUND the structured 'find X near Y' comprehension via the "
                           "GRAPH-RESIDENT compose_find_directive_structured_graph meta-rule "
                           "(seeds/composer_comprehension_find_graph.json).")
        if "find" in rp:
            return _multi("compose_comprehension_rule", "find_directive_rule",
                           "composer_comprehension_find_graph", "wants_find_rule", {},
                           ["comprehend_find_directive_" + tag, "bind_find_target_" + tag],
                           "I GROUND the 'find X' comprehension via the GRAPH-RESIDENT "
                           "compose_find_directive_graph meta-rule.")
        # describe (fallback branch) — routed through the PILOT seed itself
        # (seeds/composer_comprehension_graph.json), supplying the SAME
        # literal directive_word/goal_kind the Python builder hard-codes.
        rule_id = "comprehend_describe_directive_" + tag
        return _single("compose_comprehension_rule", "comprehension_rule", "composer_comprehension_graph",
                        "wants_comprehension_rule",
                        {"directive_word": "describe", "goal_kind": "describe_scene", "rule_id": rule_id},
                        rule_id,
                        "I GROUND the comprehension concern via the PILOT GRAPH-RESIDENT "
                        "compose_comprehension_graph meta-rule.")

    if composer_name == "experiment":
        return _route_experiment_composer(agent, keys, rels, rp)

    if composer_name == "grounding_guard":
        return _single("compose_grounding_guard_rule", "grounding_guard_rule",
                        "composer_grounding_guard_graph", "wants_grounding_guard_rule", {},
                        "escalate_grounding_gap_" + tag,
                        "I GROUND the confident-but-ungrounded guard via the GRAPH-RESIDENT "
                        "compose_grounding_guard_graph meta-rule (seeds/"
                        "composer_grounding_guard_graph.json): it minted escalate_grounding_gap_<tag> "
                        "itself from a ComposeRequest, not Python authoring at request time. The "
                        "minted rule fires on every agent -has_grounding_gap-> gap edge (domains."
                        "grounding_reach.flag_ungrounded_confident's flag, exposed mechanically by "
                        "ensure_grounding_gap_edges) not yet escalated, and — instead of trusting the "
                        "cheap snap — mints an Impasse + agent -surprised_by-> impasse, engaging the "
                        "SAME active-cognition channel impasse_escalation/investigation_teacher use.")

    if composer_name == "escalation_gate":
        return _single("compose_escalation_gate_rule", "escalation_gate_rule",
                        "composer_escalation_gate_graph", "wants_escalation_gate_rule", {},
                        "escalate_cost_worth_" + tag,
                        "I GROUND the cost-worth-refining escalation arm via the GRAPH-RESIDENT "
                        "compose_escalation_gate_graph meta-rule (seeds/"
                        "composer_escalation_gate_graph.json): it minted escalate_cost_worth_<tag> "
                        "itself from a ComposeRequest, not Python authoring at request time. The "
                        "minted rule fires on every agent -frontier_pick-> ax edge (the standing "
                        "'this is the cheap snap under consideration' signal) whose OWN shortfall/"
                        "saturation/cost attrs give a positive cost_salience value (residual*value "
                        "exceeds the cost of refining) and that has not yet been cost-escalated, and "
                        "— instead of trusting the cheap pick — mints an Impasse + agent -surprised_by-> "
                        "impasse, engaging the SAME active-cognition channel the grounding-guard arm "
                        "(composer_grounding_guard_graph) uses: together the two arms are the dual-"
                        "process arbitration (trust the snap unless ungrounded-confident OR worth "
                        "refining).")

    if composer_name == "imagination":
        return _multi("compose_imagination_rule", "imagination_rule", "composer_imagination_graph",
                       "wants_imagination_rule", {},
                       ["engage_imagine_grounding_gap_" + tag, "engage_imagine_cost_worth_" + tag,
                        "judge_imagined_conclusion_" + tag],
                       "I GROUND the TIER-3 imagine-when-escalated concern via the GRAPH-RESIDENT "
                       "compose_imagination_graph meta-rule (seeds/composer_imagination_graph.json): it "
                       "minted engage_imagine_grounding_gap_<tag>, engage_imagine_cost_worth_<tag> and "
                       "judge_imagined_conclusion_<tag> itself from a ComposeRequest, not Python "
                       "authoring at request time. The two engage rules fire on the SAME agent "
                       "-surprised_by-> impasse channel composer_grounding_guard_graph / "
                       "composer_escalation_gate_graph already mint into (grounding_gap / "
                       "cost_worth_refining kind respectively) and mint an ImagineRequest INSTEAD OF "
                       "letting the escalation only re-grind via seeds/autonomy.json's standing "
                       "mint_goal_from_surprise; domains/imagination_dispatch.py's scan_and_imagine "
                       "host hook mechanically runs it (imagine()/reground() cannot execute inside a "
                       "Rust rule effect, exactly why the hook exists — the same reason "
                       "domains/experiment_dispatch.py spawns a child process the rule engine can't "
                       "spawn itself). The judge rule then reads reground()'s OWN verdict off each "
                       "ImaginedConclusion and acts only on survivors (requests a gated commit via "
                       "agent -wants_to_commit-> imagination — domains/imagination.py's "
                       "commit_imagination stays the only path that ever writes imagined content into "
                       "the live graph, and it still requires an explicit approver), leaving discarded "
                       "fantasies untouched by construction (no rule matches them).")

    if composer_name == "collapse_watch":
        return _multi("compose_collapse_watch_rule", "collapse_watch_rule",
                       "composer_collapse_watch_graph", "wants_collapse_watch_rule", {},
                       ["attend_frontier_" + tag, "recognize_self_" + tag, "predict_intervene_" + tag],
                       "I GROUND the TIER-4 collapse-watch concern via the GRAPH-RESIDENT "
                       "compose_collapse_watch_graph meta-rule (seeds/composer_collapse_watch_graph.json): "
                       "it minted attend_frontier_<tag>, recognize_self_<tag> and "
                       "predict_intervene_<tag> itself from a ComposeRequest, not Python authoring at "
                       "request time. attend_frontier_<tag> is WHOLE-GRAPH meta-salience over the "
                       "CollapseModel's own volatile_frontier sample (still collapsing); "
                       "recognize_self_<tag> recognises the CollapseModel's own fixed_point sample — "
                       "including the frozen core — as stable self, and NEVER set_attrs the matched "
                       "node (only an outgoing agent edge), so the frozen Drive stays untouched; "
                       "predict_intervene_<tag> is the integration headline: converged=false mints an "
                       "Impasse{kind:predicted_divergence} + agent -surprised_by-> impasse, wired both "
                       "-about_model-> the CollapseModel (the honest link) and -about_axis-> the SAME "
                       "CollapseModel (piggy-backing composer_imagination_graph.json's own "
                       "engage_imagine_cost_worth_<tag> rule, whose kind-guard was widened by one "
                       "Or-arm, in the same change, to also accept 'predicted_divergence') so tier-4's "
                       "prediction reaches tier-3's imagination-engage channel, not just seeds/"
                       "autonomy.json's standing mint_goal_from_surprise. domains/collapse_watch.py's "
                       "scan_and_predict host hook mechanically calls domains.collapse_model."
                       "predict_collapse (a bounded tier-3 forward-look, an in-process Python call a "
                       "Rust rule effect cannot make) and wires agent -has_collapse_model-> model so "
                       "these rules have something to match — the same idiom ensure_grounding_gap_"
                       "edges uses for GroundingGap.")

    if composer_name == "system_model":
        return _multi("compose_system_model_rule", "system_model_rule", "composer_system_model_graph",
                       "wants_system_model_rule", {},
                       ["model_other_belief_" + tag, "recognize_modeling_terminates_" + tag],
                       "I GROUND the TIER-5 system-model concern via the GRAPH-RESIDENT "
                       "compose_system_model_graph meta-rule (seeds/composer_system_model_graph.json): "
                       "it minted model_other_belief_<tag> and recognize_modeling_terminates_<tag> itself "
                       "from a ComposeRequest, not Python authoring at request time. "
                       "model_other_belief_<tag> is the AUDIENCE-MODEL/theory-of-mind shape: a "
                       "SystemModel of a FOREIGN system (target_kind:foreign_snapshot) that is GROUNDED "
                       "in this agent's own observation of it (grounded==true) AND predicted to diverge "
                       "(converged==false) mints a Belief{kind:other_diverging} + agent -expects-> "
                       "belief -about_model-> sm, guarded by sm -modeled_belief-> belief (never a "
                       "set_attr on sm); an ungrounded or convergent foreign model never matches — the "
                       "agent only trusts a model of ANOTHER system that is grounded in observation. "
                       "recognize_modeling_terminates_<tag> is TIER-5 REFLEXIVE SELF-RECOGNITION one "
                       "level up from composer_collapse_watch_graph.json's recognize_self_<tag>: a "
                       "SystemModel{target_kind:meta} carries fixed_point samples that always include "
                       "'settled_system_model' and 'frozen_drive' (domains/system_model.py's _model_meta) "
                       "— this rule mints agent -recognizes_modeling_terminates-> fp for each, never a "
                       "set_attr on fp, the reflexive proof the tier4->tier5->tier6 recursion is "
                       "well-founded, not an infinite regress. domains/system_model_dispatch.py's "
                       "scan_and_model host hook mechanically calls domains.system_model.model_system "
                       "for each pending ModelRequest and wires agent -has_system_model-> model so these "
                       "rules have something to match — the same idiom domains/collapse_watch.py's "
                       "scan_and_predict uses for has_collapse_model.")

    if composer_name == "self_correct":
        return _route_self_correct_composer(agent, keys, rels, rp)

    if composer_name == "audience_produce":
        return _multi("compose_audience_produce_rule", "audience_produce_rule",
                       "composer_audience_produce_graph", "wants_audience_produce_rule", {},
                       ["request_produce_for_audience_" + tag, "default_explicit_produce_" + tag,
                        "tailor_when_grounded_" + tag],
                       "I GROUND the audience-driven production concern via the GRAPH-RESIDENT "
                       "compose_audience_produce_graph meta-rule (seeds/"
                       "composer_audience_produce_graph.json): it minted "
                       "request_produce_for_audience_<tag>, default_explicit_produce_<tag> and "
                       "tailor_when_grounded_<tag> itself from a ComposeRequest, not Python "
                       "authoring at request time. request_produce_for_audience_<tag> recognises a "
                       "produce_utterance Goal carrying a for_audience edge and mints a "
                       "ProduceForAudienceRequest (the decision to model-the-audience-and-tailor); "
                       "domains/audience_production_dispatch.py's scan_and_speak_to_audience host "
                       "hook mechanically calls domains.audience_driven_production.audience_model + "
                       "select_utterance (in-process Python a Rust rule effect cannot call) and "
                       "wires req -has_audience_model-> sm so these rules have something to match -- "
                       "the same idiom domains/system_model_dispatch.py's scan_and_model uses for "
                       "has_system_model. default_explicit_produce_<tag> / tailor_when_grounded_<tag> "
                       "are the LOAD-BEARING BRANCH, mirroring composer_control_graph.json's "
                       "default_no_response_<tag>/control_my_body_<tag> default+override shape: "
                       "every request defaults to mode:explicit, and is overridden to mode:tailor "
                       "iff sm.grounded==true -- read directly off the graph, never a host flag.")

    return None


_COMPOSER_REGISTRY = {
    # name-keyed registry — the SAME pattern reflex_responses dispatch elsewhere
    # in this codebase uses. `composer_pick` (seeds/composer_dispatch.json) names
    # the composer; this is a mechanical lookup, not a decision.
    "comprehension": _compose_comprehension_rule,
    "decision": _compose_decision_rule,
    "browse": _compose_browse_rule,
    "grouping": _compose_grouping_rule,
    "control": _compose_control_rule,
    "communicate": _compose_communicate_rule,
    "construction": _compose_construction_rule,
    "distributional": _compose_distributional_rule,
    "experiment": _compose_experiment_rule,
    "attention": _compose_attention_rule,
    "conceptualize": _compose_conceptualize_rule,
    # SELF-IMPROVEMENT #4 — the substrate-self-extension composer: authors a WHOLE
    # FACULTY as a multi-rule CHAIN (a pipeline), not a single rule. Routed to by the
    # 'classify' ComposerCue in seeds/composer_faculty_pipeline.json.
    "pipeline": _compose_faculty_pipeline,
    # LANGUAGE-FACULTY compose path — authors a Program composing the agent's
    # LANGUAGE faculties (a FILTER/SELECT over spans/senses). Routed to by the
    # 'filter' ComposerCue in seeds/language_faculty_cue.json; the leaf it chains
    # is the graph-resident nominal-head Term (domains/language_faculty_ops.py). The
    # 'disambiguate' ComposerCue (same seed) routes the SENSE-SELECT concern here too
    # (the 'sense' branch authors the Argmax-over-senses-by-fit SELECT Program).
    "language_faculty": _compose_language_faculty,
    # MEMORY faculty (SELF-IMPROVEMENT, third leaf) — routed by the 'cache'
    # ComposerCue in seeds/memory_faculty_cue.json; the leaf it chains is the
    # graph-resident serve-from-store Term (domains/memory_faculty_ops.py).
    "memory_faculty": _compose_memory_faculty,
}


def _ensure_seed_chain(sub, native, ag_node, seed_ids):
    """Idempotently load each of `seed_ids` (in order) onto `sub`, guarded by a
    graph-resident `Seed{id}` node OR a `SeedSummary{seed_id}` node per seed
    (`_installed_seed_ids` — Wave 3 fix: a `load_all_seeds` full boot already
    installs e.g. `literary_analysis_driving`'s closure under the SeedSummary
    convention with no `Seed` node, so checking only `Seed` re-installed a
    full duplicate copy of the reading-flow rule family on this function's
    first post-boot call — measured: la_* rules 18->36 on `run_reading_flow`'s
    first call via `_ensure_seed_chain(..., ("literary_analysis_driving",))`)
    — same idempotency pattern as `_ensure_shape_decode_loop` /
    `substrate.boot_core.load_seeds_into`. Shared by every seeded-Program
    consumer in this module (composer_dispatch, escalation_rungs, ...) AND by
    `domains.reading_drive.run_reading_flow`. Mechanical seed I/O, not a
    decision."""
    from substrate.seed_loader import manifest_for
    have = _installed_seed_ids(sub)
    for sid in seed_ids:
        if sid in have:
            continue
        native.load_seed_manifest(manifest_for(sid), ag_node)
        sub.add_node("Seed", {"id": sid, "version": "1.0.0"})
        have.add(sid)


def _pick_composer(sub, native, ag_node, heads) -> Optional[str]:
    """Evaluate the seeded `composer_pick` Program (seeds/composer_dispatch.json)
    over the grounded relation-head SET, returning the composer name (or None
    when no ComposerCue's relation_head is in `heads`). The Argmin-by-priority
    ranking IS ground_concern's old 7-way ordered if/elif, as DATA — this
    function only loads the seed (idempotent) and reads the Program's verdict."""
    _ensure_seed_chain(sub, native, ag_node, ("composer_dispatch",))
    prog = _load_program(sub, "composer_pick")
    if prog is None:
        return None
    val = native.evaluate(prog, {"heads": list(heads)})
    return val if isinstance(val, str) and val else None


def ground_concern(agent, concern_keys, *, steps: int = 24, magnitudes=None) -> dict[str, Any]:
    """GROUND an induced concern whose residual matches no held term-family, by COMPOSING
    from held machinery: the Fold-iterate of the residual-feedback recurrence, OR — when
    the concern grounds to a communicate/decompose shape — a COMMUNICATE-ACTION RULE that
    mints a produce-utterance subgoal per recognised thing. Reads the induced axis's
    residual, grounds its predicates via the held lexicon, builds the composition, registers
    it live. Honest WALL if the residual grounds to no held relation (novel predicates)."""
    sub, native, ag_node = _resolve_agent(agent)
    keys = concern_keys if isinstance(concern_keys, (list, tuple)) else [concern_keys]
    # read the induced axis's residual predicates (graph read)
    preds = None
    obs = None
    for n in sub.nodes("CapabilityAxis"):
        at = sub.node(n)["attrs"]
        if at.get("induced") and list(at.get("capability_keys") or []) == [str(k) for k in keys]:
            preds = at.get("residual_predicates") or []
            obs = at.get("observation")
            break
    if preds is None:
        return {"grounded": False, "reason": "no induced concern with that key holds a residual"}

    # PATH 1 — ground the residual predicates via the held lexicon (mechanical read, unchanged)
    rels = _residual_relations(agent, preds)
    if not rels:
        return {"grounded": False, "path": "predicate_grounding", "concern": list(keys),
                "residual_predicates": preds,
                "wall": ("the residual's predicates ground to NO held structural relation (they are "
                         "genuinely-novel terms outside the held RelationCue lexicon); the shape cannot "
                         "be composed from held vocab without inventing a law. NEXT FRONTIER: "
                         "predicate-grounding (extend the lexicon, or self-author a base primitive for "
                         "the novel shape) — NOT hand-picked here (that would be the donkey).")}

    # PATH 1.5 — the seeded `composer_pick` Program picks the composer (the OLD
    # 7-way ordered if/elif, now DATA: ComposerCue.priority breaks ties, same
    # chain order); a name-keyed registry dispatches to the matching builder.
    _crel = {r[0] for r in rels}
    composer_name = _pick_composer(sub, native, ag_node, _crel)
    if composer_name is not None:
        # try the GRAPH-RESIDENT meta-rule first (the migration this module is
        # undergoing — see the "GRAPH-RESIDENT COMPOSERS" block above); an
        # honest None (branch not yet migrated, or the graph path failed to
        # produce the expected rules) falls through to the Python builder,
        # unchanged. `served_by` on the returned dict is the migration ledger.
        graph_result = None
        try:
            graph_result = _try_graph_composer(agent, composer_name, keys, rels, _crel)
        except Exception:
            graph_result = None
        if graph_result is not None:
            return graph_result
        builder = _COMPOSER_REGISTRY.get(composer_name)
        if builder is not None:
            py_result = builder(agent, keys, rels)
            if isinstance(py_result, dict):
                py_result.setdefault("served_by", "python")
            return py_result

    # PATH 2 — GENERATE-FROM-RESIDUAL: a Fold-iterate whose body is the recurrence
    # the grounded relations name. The recurrence = a residual fed forward into the
    # state; the GROUNDED RELATIONS select the recurrence's structure (held vocab):
    #   build-from-prior -> next = prior + residual ; bounded -> residual *= decay ;
    #   advance/accumulate -> integrate ; refers-self -> feed the output back.
    # We compose the term from held Terms (Fold/Plus/Times/IndexAt/Append) — the
    # damped-feedback recurrence: state=(x, v, trail); v' = v + (-k x) + (-c v);
    # x' = x + v'; append x'. k (restoring) present iff 'build-from-prior'/'refers-
    # self' grounded; c (decay) present iff 'bounded' grounded. The COEFFICIENTS are
    # the RESIDUAL ROLES grounded from the lexicon, not arbitrary tuning.
    rel_preds = {r[0] for r in rels}
    has_feedback = ("build" in rel_preds) or ("refers" in rel_preds) or ("advance" in rel_preds)
    has_decay = ("bound" in rel_preds)
    if not has_feedback:
        return {"grounded": False, "path": "generate_from_residual", "concern": list(keys),
                "grounded_relations": rels,
                "wall": "residual grounds to relations but none names a feed-forward step; cannot iterate it"}

    def V(n): return {"type": "Var", "name": n}
    def L(v): return {"type": "Lit", "value": v}
    def Vec(*x): return {"type": "Vec", "items": list(x)}
    def IndexAt(seq, i): return {"type": "IndexAt", "seq": seq, "index": i}
    def Plus(*x): return {"type": "Plus", "items": list(x)}
    def Times(*x): return {"type": "Times", "items": list(x)}
    def Append(seq, it): return {"type": "Append", "seq": seq, "item": it}
    def Fold(src, var, acc, init, body):
        return {"type": "Fold", "source": src, "var_name": var, "acc_name": acc, "init": init, "body": body}
    st = V("st")
    # v' = v + (-k)*x + (-c)*v   — restoring (feedback) + decay (bounded), from the grounded roles
    v_terms = [IndexAt(st, L(1)), Times(V("nk"), IndexAt(st, L(0)))]
    if has_decay:
        v_terms.append(Times(V("nc"), IndexAt(st, L(1))))
    vn = Plus(*v_terms)
    xn = Plus(IndexAt(st, L(0)), vn)
    body = Vec(xn, vn, Append(IndexAt(st, L(2)), xn))
    term = Fold(L(list(range(steps))), "i", "st", Vec(L(1.0), L(0.0), Vec()), body)
    # the residual ROLES set the coefficients (restoring on, decay on iff bounded) —
    # the law's STRUCTURE is grounded; the magnitudes are unit-scaled defaults.
    # COEFFICIENTS: MEASURED from observation when supplied (magnitudes from
    # ground_predicate's trajectory fit), else unit-scaled structural defaults.
    if magnitudes:
        env = {"nk": -float(magnitudes.get("restoring_k", 0.3)),
               "nc": (-float(magnitudes.get("decay_c", 0.15)) if has_decay else 0.0)}
    else:
        env = {"nk": -0.3, "nc": (-0.15 if has_decay else 0.0)}

    # COVER check: re-cover the residual structure (held Covers) — the composed term's
    # shape covers the concern (it is ABOUT this residual, not arbitrary).
    name = "grounded_" + "_".join(str(k) for k in keys)
    ran = run_program_on_fresh(term, env)
    if not ran.get("ran"):
        return {"grounded": False, "path": "generate_from_residual", "concern": list(keys),
                "wall": f"composed generative term did not run: {ran.get('reason')}"}
    trail = [float(x) for x in ran["value"][2]] if ran.get("value") and len(ran["value"]) > 2 else []
    # CAPTURE check: does the run reproduce the residual's DYNAMICS? for an
    # oscillate/damp residual: zero-crossings (oscillates) + amplitude decays.
    crossings = sum(1 for i in range(1, len(trail)) if trail[i - 1] * trail[i] < 0)
    early = max((abs(x) for x in trail[:8]), default=0.0)
    late = max((abs(x) for x in trail[-8:]), default=0.0)
    captures = crossings >= 3 and (late < early if has_decay else True)

    # EXPRESS + register live (held facility) — the grounded term IS the concern's term
    rec = teach_program(agent, name, term)
    return {
        "grounded": True, "path": "generate_from_residual", "concern": list(keys),
        "residual_predicates": preds, "grounded_relations": rels,
        "term_name": name, "env": env,
        "covers": True,   # the term is composed FROM the residual's grounded relations
        "captures": captures,
        "dynamics": {"zero_crossings": crossings, "early_amp": round(early, 3), "late_amp": round(late, 3)},
        "trajectory_sample": [round(x, 3) for x in trail[:16]],
        "callable": ran.get("ran"), "recompiled": False, "restarted": False, "persisted": bool(rec),
        "how": ("I GROUND the novel concern by composing the Fold-iterate of its residual-feedback "
                "recurrence (a shape IS the iterate of its residual): the grounded relations select the "
                "recurrence structure (feedback + decay), and the held Fold/Plus/Times/Append compose it. "
                "Run, it reproduces the observed dynamics — capture, not just cover."),
    }


def self_extend_ladder(agent, gap: dict) -> dict[str, Any]:
    """The self-extension LADDER, dynamic-first. `gap` describes the needed
    operation: {name, program (a composed Term-tree from held Terms, or None),
    check ({env, expect}), rust_spec (a runtime_design spec, for rung-4), rust_anchor}.
    Tries rung-3 (dynamic compose+register, no restart) -> rung-4 (Rust recompile)
    -> rung-5 (HumanImpasse). Returns the rung that succeeded + evidence. Routing
    handoff over held faculties; no reasoning here."""
    name = gap.get("name", "op")
    trail = []

    # --- rung-3: DYNAMIC compose + register (no recompile) ---
    prog = gap.get("program")
    if prog is not None:
        r3 = dynamic_extend(agent, name, prog, check=gap.get("check"))
        trail.append({"rung": 3, "kind": "dynamic", "ok": r3.get("ok"), "reason": r3.get("reason")})
        if r3.get("ok"):
            r3["ladder"] = trail
            return r3

    # --- rung-4: RUST recompile (self_extend) — only if NOT composable ---
    spec = gap.get("rust_spec")
    if spec is not None:
        try:
            from domains.self_extend import PrimitiveExtension
            pe = PrimitiveExtension()
            anchor = gap.get("rust_anchor")
            res = pe.extend(spec, anchor_spec=anchor, build=True) if anchor \
                else pe.extend(spec, build=True)
            trail.append({"rung": 4, "kind": "rust_recompile", "ok": res.get("ok"),
                          "stage": res.get("stage"), "rolled_back": res.get("rolled_back")})
            if res.get("ok"):
                return {"ok": True, "rung": 4, "kind": "rust_recompile", "name": name,
                        "recompiled": True, "restarted": True, "detail": res, "ladder": trail}
        except Exception as e:  # noqa: BLE001
            trail.append({"rung": 4, "kind": "rust_recompile", "ok": False, "error": f"{type(e).__name__}: {e}"})

    # --- rung-5: HumanImpasse — last resort ---
    sub = getattr(agent, "s", agent)
    try:
        imp = sub.add_node("Impasse", {"kind": "human", "to": "creator", "resolved": 0.0,
                                       "gap": name,
                                       "note": "dynamic-compose and Rust-recompile both failed; I need the creator"})
        agent_node = getattr(agent, "agent", None)
        if agent_node is not None:
            getattr(agent, "inner", sub).add_edge_unchecked(agent_node, "raises", imp)
    except Exception:
        pass
    trail.append({"rung": 5, "kind": "human_impasse", "ok": True})
    return {"ok": True, "rung": 5, "kind": "human_impasse", "name": name,
            "note": "raised HumanImpasse to creator (last resort, after dynamic + Rust both failed)",
            "ladder": trail}


def _run_program_extraction(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """PROGRAM EXTRACTION: report HOW the agent extracts a faculty's program so another can run it — by
    reifying the faculty's DECISION TERM-TREE into a graph-resident Program a FRESH substrate evaluates.
    Mechanical introspection (same shape as _run_law_vs_cache); names the held pieces. No reasoning here."""
    have_eval = False
    try:
        import substrate_rs as _srs
        have_eval = hasattr(_srs.Substrate, "evaluate")
    except Exception:
        pass
    return {
        "how": ("I extract a faculty's PROGRAM by reifying its decision into a graph-resident TERM-TREE — an "
                "inspectable, re-runnable handle (my faculties already hold their decisions as Term-trees, e.g. "
                "recognition_graph.score_term: a Sum/Argmax over the graph). A FRESH net-free substrate then "
                "EVALUATES that Term-tree to reproduce the faculty's behaviour. The execution is the Rust "
                "evaluator's, not prose — understanding = the program survives extraction onto a fresh substrate."),
        "mechanism_faculty": "faculty Term-tree (e.g. recognition_graph.score_term) -> substrate_rs.Substrate.evaluate (fresh)",
        "held": have_eval,
        "certifier": "reflective_faculty.extract_program(faculty_term) + run_program_on_fresh(program, env)",
        "residual": ("extraction works for faculties whose decision is ALREADY a Term-tree; a faculty whose "
                     "decision is not yet reified as a Term cannot be extracted this way (would need reifying first)"),
    }


def _run_program_teaching(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """PROGRAM TEACHING: report HOW the agent teaches another agent a program it can run — by persisting the
    extracted Term-tree Program as seed graph data (teach), so a fresh boot re-loads and re-runs it; plus the
    held ostensive/ZPD teaching (parent_teacher). Mechanical introspection. No reasoning here."""
    have = False
    try:
        from domains.teach import teach as _t  # noqa: F401
        from domains import parent_teacher as _pt  # noqa: F401
        have = True
    except Exception:
        pass
    return {
        "how": ("I teach another agent a program by PERSISTING the extracted Term-tree as SEED GRAPH DATA "
                "(teach files it under my own shape); a fresh boot (load_all_seeds) then HAS the Program and a "
                "fresh substrate RE-RUNS it. I teach at the learner's frontier (parent_teacher: ostensive "
                "naming, ZPD). The taught thing is a runnable handle, not just examples — the program transfers."),
        "mechanism_faculty": "teach (persist Program as seed) + parent_teacher (ZPD/ostensive) + fresh-boot re-run",
        "held": have,
        "certifier": "reflective_faculty.teach_program(agent, name, program); fresh load_all_seeds re-runs it",
        "residual": ("teaching transfers the PROGRAM (Term-tree) to a fresh boot; teaching a learner with a "
                     "DIFFERENT representation (re-learn through its own bias) is a separate, harder transfer"),
    }


def cascade_decide(margin, substrate=None) -> dict[str, Any]:
    """The ESCALATION-CASCADE decision: at the current rung, ESCALATE iff the input is UNCERTAIN — i.e. the
    confidence MARGIN is below the rung's VOC gate. NOT a Python comparison: the gate is a held EffortDial
    SALIENCE THRESHOLD, and the escalate test is a TERM-TREE (Lt(margin, threshold)) the RUST EVALUATOR runs.

    Pieces composed (all held):
      • the GATE (VOC budget): substrate_rs.EffortDial.salience_threshold() — the effort-scaled threshold below
        which a candidate is too uncertain to resolve cheaply (escalate iff expected gain > cost = below it).
      • the DECISION: a Term-tree Lt(margin, threshold) evaluated on the substrate — the Rust evaluator returns
        the escalate-or-stay boolean. Python builds the Term and reads the boolean; it makes no comparison.
      • the RUNGS: gap_prioritiser.PIPELINE_LEVELS (the cheap->expensive ladder; axis_pipeline_level places an
        axis on it). On STAY -> resolve at the current rung; on ESCALATE -> the next rung up the ladder.

    Returns {decision: STAY|ESCALATE, margin, threshold, next_rung}. The decision is the Rust evaluator's."""
    # the held VOC gate: the EffortDial's salience threshold at current effort (lower => keep more / resolve more).
    try:
        from substrate_rs import EffortDial
    except Exception:
        from substrate_rs._native import EffortDial          # type: ignore
    threshold = float(EffortDial().salience_threshold())
    # the rung ladder (held): cheap -> expensive
    from domains import gap_prioritiser as gp
    rungs = sorted(gp.PIPELINE_LEVELS.items(), key=lambda kv: kv[1])
    # the DECISION as a Term-tree the RUST evaluator runs (escalate iff margin < threshold): no Python compare.
    gate_term = {"type": "Lt", "a": {"type": "Lit", "value": float(margin)},
                 "b": {"type": "Lit", "value": threshold}}
    if substrate is None:
        import substrate_rs as _srs
        substrate = _srs.Substrate()                          # a fresh substrate just to run the gate Term
    escalate = bool(substrate.evaluate(_Term(gate_term), {})) # the Rust evaluator decides

    # the RUNG PICK: the seeded `cascade_pick` Program (seeds/escalation_rungs.json)
    # replaces the old Python `rungs[1][0] if escalate else rungs[0][0]` indexing —
    # a Term-tree the Rust evaluator runs over the graph-resident Rung ladder, given
    # the current rung (cascade_decide always starts from the cheapest rung — the
    # same default the old indexing assumed) + margin/threshold via env.
    sub = getattr(substrate, "s", substrate)
    native = _native_eval2(substrate)
    ag_node = _agent_root_node(sub)
    _ensure_seed_chain(sub, native, ag_node, ("escalation_rungs",))
    # mechanical cross-check (not a decision): the seeded Rung ladder must agree
    # with gap_prioritiser.PIPELINE_LEVELS — the agent-visible copy tracks the module.
    seeded_rungs = {at["name"]: at.get("level") for at in
                    (sub.node(n)["attrs"] for n in sub.nodes("Rung")) if at.get("name")}
    expected_rungs = {name: float(level) for name, level in rungs}
    assert seeded_rungs == expected_rungs, (
        f"seeds/escalation_rungs.json's Rung ladder {seeded_rungs} disagrees with "
        f"gap_prioritiser.PIPELINE_LEVELS {expected_rungs}")
    current = rungs[0][0]
    prog = _load_program(sub, "cascade_pick")
    picked = (native.evaluate(prog, {"margin": float(margin), "threshold": threshold, "current": current})
              if prog is not None else current)
    nxt = picked if escalate else "resolve at cheapest rung"
    return {
        "decision": "ESCALATE" if escalate else "STAY",
        "margin": float(margin), "threshold": threshold,
        "rung_ladder": [r for r, _ in rungs],
        "next_rung": nxt,
        "mechanism": ("EffortDial.salience_threshold (VOC gate) + Lt(margin, threshold) Term run by the Rust "
                      "evaluator (the decision) + the seeded `cascade_pick` Program over the graph-resident "
                      "Rung ladder (escalation_rungs.json) for the pick. Escalate iff the margin is below the "
                      "effort-scaled threshold; both the boolean and the rung pick are the evaluator's."),
    }


def _run_escalation(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """ESCALATION CASCADE: report HOW the agent escalates when a cheap recogniser is unsure — the order-(n-x)
    default rung + a confidence-gated escalation up the rung ladder, the gate being the held EffortDial VOC
    budget and the decision a Term-tree the Rust evaluator runs. Mechanical introspection; names the held
    pieces. No reasoning here."""
    have = False
    try:
        from substrate_rs import EffortDial  # noqa: F401
        from domains import gap_prioritiser as gp  # noqa: F401
        from domains import investigation_operators as io  # noqa: F401
        have = True
    except Exception:
        pass
    return {
        "how": ("I run the cheapest rung by DEFAULT (order n-x), and ESCALATE only the UNCERTAIN tail: my held "
                "EffortDial gives the VOC gate (a salience threshold scaled by effort), and the escalate decision "
                "is a Term-tree Lt(margin, threshold) my Rust evaluator runs — escalate iff the confidence margin "
                "is below the gate (expected gain > cost), else resolve cheaply. The rungs are my pipeline ladder "
                "(gap_prioritiser.PIPELINE_LEVELS: perception -> segmentation -> ... -> recognition), and which "
                "axis to escalate is my gap_prioritiser pick (an Argmax score Term). The decision is the gate's, "
                "not prose — the costly rung runs only on the tail the cheap one is unsure about."),
        "mechanism_faculty": ("EffortDial.salience_threshold (VOC gate) + Lt-Term (Rust evaluator) + "
                              "gap_prioritiser.PIPELINE_LEVELS / axis_pipeline_level (rungs) + gap_prioritiser pick"),
        "held": have,
        "certifier": "reflective_faculty.cascade_decide(margin, substrate)",
        "residual": ("the GATE is the EffortDial VOC threshold, not the SPRT (A,B from target tail-error) bound — "
                     "a calibrated-from-target-error gate is a refinement. The COMPILE-DOWN (developmental: "
                     "escalation fraction FALLS with experience as outcomes compile into the cheap rung) is NOT "
                     "folded — it needs a standing learning Rule. And there is no standing AUTO-CASCADE Rule yet "
                     "(the pieces route + the gate decides; an always-on rung-chaining Rule is unwired)."),
    }


def _run_capability_understanding(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """CAPABILITY x UNDERSTANDING: answer the two-axis distinction by READING the SEEDED graph data — the
    two_axes Concepts (capability_axis / understanding_axis / savant_case / mastery_case) + the
    capability_understanding_mt Microtheory. Pure mechanical introspection (same shape as _run_self_
    organisation reading microtheories); the ANSWER IS THE SEEDED NODES, not prose bolted in here. If the
    seed isn't booted, returns unwired (the honest 'no graph data' case, not a fabricated answer)."""
    concepts = {}
    for n in substrate.nodes("Concept"):
        at = substrate.node(n)["attrs"]
        nm = at.get("name")
        if nm in ("capability_axis", "understanding_axis", "savant_case", "mastery_case"):
            concepts[nm] = at
    mt = None
    for m in substrate.nodes("Microtheory"):
        at = substrate.node(m)["attrs"]
        if at.get("name") == "capability_understanding_mt":
            mt = at
            break
    if not concepts and mt is None:
        return {"unwired": ("the two-axis graph data (two_axes Concepts + capability_understanding_mt) is not "
                            "booted on this substrate — boot it (seeds/two_axes.json) so I can read it")}
    return {
        "answer_source": "seeded graph data (two_axes Concepts + capability_understanding_mt Microtheory) — read, not authored",
        "capability_axis": concepts.get("capability_axis"),
        "understanding_axis": concepts.get("understanding_axis"),
        "savant_case": concepts.get("savant_case"),       # capability-3, understanding-0 (the independence proof)
        "mastery_case": concepts.get("mastery_case"),     # high on both
        "microtheory": mt,                                # the relations + the four-fold unification
        "nodes_read": sorted(concepts.keys()) + (["capability_understanding_mt"] if mt else []),
    }


# ---------------------------------------------------------------------------
# SHAPE GENERATION / RECOVERY — route to the held graph-resident Programs.
# The faculty ROUTES + reads out; the generation/recovery reasoning IS the held
# Term-tree Program (Fold/Substitute/AntiUnifyWitness/Atan2) run by the Rust
# evaluator. No Python loop, no decision-if over graph state.
# ---------------------------------------------------------------------------
def _load_program(substrate, name: str):
    """Mechanical graph read: the persisted Program Term-tree (seeds/programs.json)
    by name. Returns the Term-tree dict, or None if not held."""
    import json as _json
    sub = getattr(substrate, "s", substrate)
    try:
        for n in sub.nodes("Program"):
            at = sub.node(n)["attrs"]
            if at.get("name") == name and at.get("program"):
                return _json.loads(at["program"])
    except Exception:
        pass
    return None


def _run_on_fresh(program_term, env):
    """Run a Program Term-tree on a fresh substrate (the Rust evaluator computes;
    Python only hands off the env). Reuses run_program_on_fresh's path."""
    if program_term is None:
        return {"ran": False, "reason": "Program not held on this substrate"}
    return run_program_on_fresh(program_term, env)


# the residual-LAWS for the three canonical shapes (the env each binds — data, not
# reasoning; the shape KIND is the algebraic form of the law, per the grounding).
_SHAPE_LAWS = {
    "circle": {"turn0_deg": 30.0, "dturn_deg": 0.0, "steps": 12},   # constant residual -> closes
    "line":   {"turn0_deg": 0.0,  "dturn_deg": 0.0, "steps": 6},    # identity residual -> straight
    "spiral": {"turn0_deg": 20.0, "dturn_deg": 8.0, "steps": 18},   # compounding residual -> runs away
}


def _shape_kind_from_arg(meta_arg: Optional[str]) -> str:
    """Pick the named shape kind from the meta-arg phrase (e.g. 'a circle' ->
    'circle'); default circle. A surface keyword scan over the law names, not a
    decision about meaning."""
    text = (meta_arg or "").lower()
    for k in _SHAPE_LAWS:
        if k in text:
            return k
    return "circle"


def _run_generate(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """GENERATE a shape by ROUTING to the held generate_shape Program (the fed-forward
    iterate of the residual operator) and running it on the residual-LAW named by
    meta_arg ('circle'/'spiral'/'line'; default circle). The trajectory is the held
    Term-tree's output — the Rust evaluator iterates Fold+advance; this only picks the
    law's env and reads the trail out. 'A circle is the residual at every step feeding
    into the next' — generation = iterate the difference operator."""
    import math as _math
    prog = _load_program(substrate, "generate_shape")
    if prog is None:
        return {"unwired": "generate_shape Program not held (boot seeds/programs.json)"}
    kind = _shape_kind_from_arg(meta_arg)
    law = _SHAPE_LAWS[kind]
    env = {"turn0": _math.radians(law["turn0_deg"]), "dturn": _math.radians(law["dturn_deg"]),
           "steps": list(range(law["steps"]))}
    out = _run_on_fresh(prog, env)
    trail = None
    if out.get("ran"):
        state = out["value"]
        try:
            trail = [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in state[5]]
        except Exception:
            trail = None
    closes = None
    if trail:
        closes = (_math.hypot(trail[-1][0], trail[-1][1]) < 1e-6)
    return {
        "shape": kind,
        "how": ("I GENERATE a shape as the fed-forward iterate of my difference operator: "
                "state_{n+1}=advance(state_n, sigma); sigma_{n+1}=update(sigma). The residual-LAW "
                "is the generator — CIRCLE=constant turn, SPIRAL=compounding turn, LINE=identity. "
                "The iterate is my held generate_shape Program (a Fold over the threaded turtle "
                "state); the Rust evaluator runs it, I only supply the law."),
        "residual_law": {"turn0_deg": law["turn0_deg"], "dturn_deg": law["dturn_deg"], "steps": law["steps"]},
        "program": "generate_shape (held Term-tree: Fold + advance via Sin/Cos/Plus)",
        "trajectory": trail,
        "closes": closes,
        "ran": out.get("ran"),
    }


def _run_recover(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """RECOVER the residual-LAW of a stepped shape by ROUTING to the held
    recover_shape_law Program (the INVERSE: difference consecutive steps into the
    turning residual). meta_arg names which shape to demonstrate the recovery on
    ('circle'/'spiral'/'line'); the Program is run on that shape's generated trail.
    Classification (constant turn => circle; constant 2nd-difference => spiral) is a
    READ-OUT of the recovered turn-sequence the Term-tree returns — not reasoning."""
    import math as _math
    gen = _load_program(substrate, "generate_shape")
    rec = _load_program(substrate, "recover_shape_law")
    if rec is None or gen is None:
        return {"unwired": "recover_shape_law / generate_shape Program not held"}
    kind = _shape_kind_from_arg(meta_arg)
    law = _SHAPE_LAWS[kind]
    gen_out = _run_on_fresh(gen, {"turn0": _math.radians(law["turn0_deg"]),
                                  "dturn": _math.radians(law["dturn_deg"]),
                                  "steps": list(range(law["steps"]))})
    if not gen_out.get("ran"):
        return {"unwired": "could not produce a shape to recover from", "detail": gen_out}
    trail = [[float(p[0]), float(p[1])] for p in gen_out["value"][5]]
    rec_out = _run_on_fresh(rec, {"trail": trail, "idx": list(range(2, len(trail)))})
    turns_deg = None
    if rec_out.get("ran"):
        turns_deg = [round(_math.degrees(float(t)), 3) for t in rec_out["value"]]
    # read-out classification over the recovered turn-sequence (no decision logic):
    law_kind, recovered = None, {}
    if turns_deg:
        const_turn = all(abs(t - turns_deg[0]) < 1e-6 for t in turns_deg)
        dd = [round(turns_deg[i + 1] - turns_deg[i], 3) for i in range(len(turns_deg) - 1)]
        const_2nd = bool(dd) and all(abs(d - dd[0]) < 1e-6 for d in dd)
        if const_turn and abs(turns_deg[0]) < 1e-6:
            law_kind = "line (identity residual)"
        elif const_turn:
            law_kind = "circle (constant residual)"
            recovered = {"constant_turn_deg": turns_deg[0]}
        elif const_2nd:
            law_kind = "spiral (compounding residual)"
            recovered = {"turn0_deg": turns_deg[0], "update_per_step_deg": dd[0]}
    return {
        "given_shape": kind,
        "how": ("I RECOVER a stepped shape's generative LAW by my held recover_shape_law Program — "
                "the INVERSE: difference consecutive steps into the turning residual (atan2 of each "
                "segment, then the step-to-step change). A CONSTANT turn is a circle's law; a constant "
                "2nd-difference is a spiral's. The differencing is the held Term-tree; I read the law off "
                "the recovered residual-sequence."),
        "program": "recover_shape_law (held Term-tree: MapList + Atan2 consecutive-step differencing)",
        "recovered_law_kind": law_kind,
        "recovered": recovered,
        "turn_sequence_deg": turns_deg[:8] if turns_deg else None,
        "ran": rec_out.get("ran"),
    }


# ---------------------------------------------------------------------------
# MATH <-> CAPABILITY BRIDGE — connect held MATH Concepts to held FACULTIES by
# running the agent's OWN held shape-matcher (AntiUnify) over their structural
# signatures (seeds/math_capability_shapes.json, graph data). The CONNECTION is
# whatever the matcher finds the two SHARE — never a bolted-in string. The
# faculty routes + reads out the matcher's result; the MATCHING is the held
# AntiUnify/FixedCount Terms run by the Rust evaluator. No decision-if over graph
# state; the shared-shape skeleton + its FixedCount ARE the answer.
# ---------------------------------------------------------------------------
def _load_shape_signatures(substrate) -> dict:
    """Mechanical graph read: {name -> (kind, signature_list)} for every
    ShapeSignature node (the shape-comparable representation of held math /
    faculties). signature is a relation-system (list of positional tuples)."""
    import json as _json
    sub = getattr(substrate, "s", substrate)
    out = {}
    try:
        for n in sub.nodes("ShapeSignature"):
            at = sub.node(n)["attrs"]
            nm = at.get("name")
            sig = at.get("signature")
            if nm and sig:
                try:
                    out[nm] = (at.get("kind", ""), _json.loads(sig), at.get("concept") or at.get("faculty"))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _concept_definition(substrate, name: str):
    """Mechanical graph read: a held Concept's grounded definition text (its own
    structure in words). Returns (definition, concept_node_name) or (None, None)."""
    sub = getattr(substrate, "s", substrate)
    target = (name or "").strip().lower()
    for t in ("Concept", "Microtheory", "Principle"):
        try:
            nodes = sub.nodes(t)
        except Exception:
            continue
        for n in nodes:
            at = sub.node(n)["attrs"]
            nm = str(at.get("name", ""))
            if nm.lower() == target:
                return (at.get("definition") or at.get("description") or at.get("def") or ""), nm
    # loose match: a Concept whose name contains the query token
    for n in sub.nodes("Concept"):
        at = sub.node(n)["attrs"]
        nm = str(at.get("name", ""))
        if target and target.replace(" ", "_") in nm.lower():
            return (at.get("definition") or at.get("description") or ""), nm
    return None, None


# ---------------------------------------------------------------------------
# ARGUMENT-ROLE MINT-TIME GUARD (ARGUMENT_ROLE_VOCABULARY_PREREG.md / _RESULTS.md)
# -- the sd loop's recognize/mint duality reapplied to RelationCue's own uppercase
# role-token placeholders. RELATION_CUE_TOKEN_COLLISION_RESULTS.md §6 found the
# representation itself unenforced: two cues reusing "SELF" are (correctly) not
# distinguished from two cues reusing "POSITION" by accident -- nothing in the
# graph HOLDS the role as a first-class, named, deduped thing. seeds/
# argument_role_vocabulary.json promotes it: ArgumentRole{name, gloss} is the
# direct structural analogue of FunctionalRole, one level down (FunctionalRole
# names system FUNCTIONS; ArgumentRole names argument SLOTS). RelationCue.relation
# itself is UNCHANGED (every real consumer -- _load_relation_cues,
# _relation_cue_index, _shared_shape, Rust shape_fit -- keeps reading the bare
# string, byte-identical); RelationCue additionally carries real uses_role edges.
#
# The mint-time guard is the seed's role_recognize_exact / role_mint_fresh_token /
# role_flag_collision rules (mirroring seeds/blob_edge_correspondence.json's
# blob_mint/blob_recognize and seeds/gap_awareness.json's gap-filing shape, not a
# fourth invented mechanism): a freshly-taught RelationCue's relation tuple, if
# BYTE-IDENTICAL to an already-held cue's, recognizes with confidence (a pure
# keyword-synonym addition -- ground_predicate's own, only, current live minting
# behaviour); an uppercase token never seen before mints a fresh ArgumentRole
# (safe by construction); any OTHER reuse of an existing token under a
# structurally different tuple is FLAGGED (a SelfConcern is filed, the edge is
# deliberately left unwired) rather than silently guessed at -- the prior rung's
# own census shows SAME-vs-DIFFERENT is not mechanically recoverable from
# structure alone (genuinely-shared tokens like SELF share no more structure
# across their cues than the confirmed-accidental POSITION/PRIOR pair did), so
# the guard's honest job is to make every non-identical reuse VISIBLE, not to
# guess. Python does mechanical ingest + read-back only (mirrors
# record_correspondence exactly): write one pending RoleUseCheck per uppercase
# token, run_rules(), read back the verdict, and for the ONE case the engine
# cannot wire from inside the rule (recognized_exact -- the matching ArgumentRole
# is Term-found, not match-bound; "add_edge targets must be match-bound vars in
# this engine", sd_dedup_existing's own documented constraint, reused rather than
# reinvented) re-resolve it by name and wire the edge the rule already decided.
# ---------------------------------------------------------------------------

def _load_argument_role_index(substrate) -> dict:
    """Mechanical graph read: {ArgumentRole.name -> node_id} -- the held vocabulary
    check_new_relation_cue_roles re-resolves a rule's RECOGNIZED verdict against."""
    sub = getattr(substrate, "s", substrate)
    idx: dict = {}
    try:
        for n in sub.nodes("ArgumentRole"):
            nm = sub.node(n)["attrs"].get("name")
            if nm:
                idx[nm] = n
    except Exception:
        pass
    return idx


def check_new_relation_cue_roles(substrate, cue_node_id) -> dict[str, Any]:
    """MECHANICAL INGEST (record_correspondence's exact pattern), run on every
    freshly-taught RelationCue: write ONE pending RoleUseCheck per distinct
    uppercase role token in the cue's `relation` tuple, hand off to
    seeds/argument_role_vocabulary.json's guard rules -- which DECIDE (never
    Python) whether each token-use RECOGNIZES an identical held relation (safe,
    wired), MINTS a genuinely new ArgumentRole (safe by construction, wired by
    the rule itself), or is FLAGGED (an existing token reused under a new
    structural shape -- a SelfConcern is filed, the edge is deliberately left
    unwired, per the charter's own words: 'flag it, don't silently install a
    second meaning under one name'). Returns {'checked': bool, 'tokens':
    {token: verdict}} -- verdict in {'recognized_exact','minted','flagged'} (or
    absent if the cue has no live graph / no uppercase tokens at all)."""
    import json as _json
    sub = getattr(substrate, "s", substrate)
    out: dict[str, Any] = {"checked": False, "tokens": {}}
    if cue_node_id is None or not hasattr(sub, "add_node"):
        return out
    try:
        rel = _json.loads(sub.node(cue_node_id)["attrs"].get("relation") or "[]")
    except Exception:
        return out
    tokens = sorted({t for t in rel if isinstance(t, str) and t.isupper()})
    if not tokens:
        return out
    native = getattr(sub, "_inner", sub)
    checks: dict = {}
    try:
        for tok in tokens:
            rc = sub.add_node("RoleUseCheck", {"status": "pending", "token": tok})
            sub.add_edge(cue_node_id, "has_role_use", rc)
            checks[tok] = rc
        native.run_rules()
    except Exception as exc:
        out["error"] = str(exc)
        return out
    role_index = _load_argument_role_index(substrate)
    verdicts: dict = {}
    for tok, rc in checks.items():
        status = sub.node(rc)["attrs"].get("status")
        verdicts[tok] = status
        if status == "recognized_exact":
            role = role_index.get(tok)
            if role is not None:
                try:
                    sub.add_edge(cue_node_id, "uses_role", role)
                except Exception:
                    pass
    out.update({"checked": True, "tokens": verdicts})
    return out


def _load_relation_cues(substrate) -> list:
    """Mechanical graph read: the RelationCue lexicon (relation_vocabulary.json) —
    [(keywords, relation_tuple)] mapping definition-words to structural relations."""
    import json as _json
    sub = getattr(substrate, "s", substrate)
    cues = []
    try:
        for n in sub.nodes("RelationCue"):
            at = sub.node(n)["attrs"]
            kws = at.get("keywords")
            rel = at.get("relation")
            if kws and rel:
                try:
                    cues.append((list(kws), _json.loads(rel)))
                except Exception:
                    pass
    except Exception:
        pass
    return cues


def author_signature(substrate, concept_name: str):
    """SIGNATURE-AUTHORING: extract a held Concept's structural signature from its
    OWN grounded definition (its structure in words) via the held RelationCue
    lexicon — the same mechanical text->structure translation as the held relation
    perception. Each cue whose keyword appears in the definition emits its relation
    tuple; the signature is the assembled relation-system. EARNED from the Concept's
    definition, not hand-written. Returns (signature, definition, concept_name) or
    (None, ...) if no Concept/definition is held. No decision over graph state —
    keyword presence is perception, the same category as ShapePrinciple matching."""
    defn, cname = _concept_definition(substrate, concept_name)
    if not defn:
        return None, defn, cname
    text = str(defn).lower()
    cues = _load_relation_cues(substrate)
    sig = []
    seen = set()
    for kws, rel in cues:
        if any(kw in text for kw in kws):
            key = tuple(rel)
            if key not in seen:
                sig.append(rel)
                seen.add(key)
    return (sig if sig else None), defn, cname


_RELATION_CUE_INDEX_CACHE: dict = {}


def _relation_cue_index(substrate) -> dict:
    """The RelationCue vocabulary's reverse index: {tuple(relation): cue_name}, the
    AXIS a relation-tuple row belongs to. Every consumer of the RelationCue lexicon
    (author_signature's keyword scan, the hand-authored seeds/math_capability_shapes.json
    rows) emits relation tuples copied verbatim from a RelationCue.relation, so this
    index is how `_shared_shape` recognises WHICH axis a row is, independent of the
    row's position in whatever list it arrived in. Cached like
    `analogical_thinking._vocabulary_keys` (same pattern, own cache — no cross-import)."""
    sub = getattr(substrate, "s", substrate)
    cues = _load_relation_cues(substrate)
    key = (id(sub), len(cues))
    cached = _RELATION_CUE_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    idx = {}
    for n in sub.nodes("RelationCue") if hasattr(sub, "nodes") else []:
        at = sub.node(n)["attrs"]
        nm, rel = at.get("name"), at.get("relation")
        if not nm or not rel:
            continue
        try:
            import json as _json
            rel = _json.loads(rel) if isinstance(rel, str) else rel
        except Exception:
            continue
        idx[tuple(rel)] = nm
    _RELATION_CUE_INDEX_CACHE[key] = idx
    return idx


def _shared_shape(substrate, sig_a, sig_b):
    """Run the HELD shape-matcher over two signatures: AntiUnify -> the shared
    structural skeleton; FixedCount -> how many leaf positions they SHARE (the
    connection strength). Pure read-out of the matcher's Rust output.

    AXIS-ANCHORED, not positional: a row from sig_a is paired with a row from sig_b
    only when BOTH are byte-identical to the SAME held RelationCue's relation tuple
    (`_relation_cue_index`) -- i.e. the same NAMED cue fired for both signatures.
    Two signatures' rows are never compared merely because they share a list index.
    This is the same discipline `analogical_thinking._concept_shape_vector` applies
    over its own vocabulary (fixed axis identity, not position-in-whatever-fired);
    here the axis identity is looked up by content (the relation tuple IS the cue's
    key) rather than carried as a separate label, because both operand types this
    function ever receives (an author_signature() output, a CapabilityAxis-residual
    `[[p], ...]` list, or a seeded `math_capability_shapes.json` signature) are, by
    construction, lists of raw relation tuples with no separate axis label attached.
    A row that matches no held cue (e.g. a CapabilityAxis residual's bare predicate,
    or the rare hand-authored seed row that isn't an exact cue-template copy) simply
    contributes no axis and is excluded from the comparison, honestly -- not force-
    aligned by position the way the old code did."""
    sub = getattr(substrate, "s", substrate)
    native = getattr(sub, "_inner", sub)
    if not sig_a or not sig_b:
        return None, 0
    cue_of = _relation_cue_index(substrate)
    by_name_a: dict = {}
    for row in sig_a:
        nm = cue_of.get(tuple(row))
        if nm and nm not in by_name_a:
            by_name_a[nm] = list(row)
    by_name_b: dict = {}
    for row in sig_b:
        nm = cue_of.get(tuple(row))
        if nm and nm not in by_name_b:
            by_name_b[nm] = list(row)
    shared_names = sorted(set(by_name_a) & set(by_name_b))
    if not shared_names:
        return None, 0
    a = [by_name_a[nm] for nm in shared_names]
    b = [by_name_b[nm] for nm in shared_names]
    res = native.evaluate({"type": "AntiUnify", "values": {"type": "Lit", "value": [a, b]}, "wild": "·?·"}, {})
    fixed = native.evaluate({"type": "FixedCount", "pattern": {"type": "Lit", "value": res}, "wild": "·?·"}, {})
    try:
        fixed = int(fixed)
    except Exception:
        fixed = 0
    return res, fixed


# ---------------------------------------------------------------------------
# BLOB-EDGE CORRESPONDENCE MINTING (BLOB_EDGE_SD_LOOP_PREREG.md / _RESULTS.md)
# -- the sd loop's recognize/mint duality reapplied to CORRESPONDENCE
# persistence. `_shared_shape` (above, UNCHANGED by this block) already
# collapses two signatures onto shared HELD structure -- the RelationCue
# axes both sides independently anchor onto (I_A -> S + r_A, I_B -> S + r_B).
# That collapse is the "recognize" event one level up; this records it as a
# graph-native Correspondence -> BlobEdge fact via
# seeds/blob_edge_correspondence.json's `blob_mint`/`blob_recognize`/
# `blob_no_collapse` rules, which mirror `sd_mint_quantum`/`sd_dedup_existing`
# byte-for-byte in shape (add_node+add_edge on the FIRST occurrence of a NEW
# transform_key; a bare status flag, no new edge, on a RECOGNIZED one -- the
# same add_edge-needs-a-match-bound-var engine constraint `sd_dedup_existing`
# already documents). Python does not decide recognize-vs-mint -- it writes
# the Correspondence node (mechanical ingest, `domains/meta_shape.py::observe`'s
# exact pattern) and reads back the rule's verdict.
# ---------------------------------------------------------------------------

def _agent_node_id(substrate):
    """The single Agent hub node, found by scan -- no assumed adapter attr."""
    sub = getattr(substrate, "s", substrate)
    try:
        nodes = sub.nodes("Agent")
    except Exception:
        return None
    return nodes[0] if nodes else None


def _shape_signature_node_id(substrate, name: str):
    """Mechanical lookup: the real `ShapeSignature` node id for a held name --
    the SAME name `_load_shape_signatures` already keys its dict by."""
    sub = getattr(substrate, "s", substrate)
    try:
        for n in sub.nodes("ShapeSignature"):
            if sub.node(n)["attrs"].get("name") == name:
                return n
    except Exception:
        pass
    return None


def _canon_shared_shape(res) -> str:
    """Canonicalise `_shared_shape`'s AntiUnify template into a stable string
    key -- the recognition identity a recurring correspondence is matched by.
    Pure serialisation (row order is already canonical: `_shared_shape` builds
    both operand lists from `sorted(set(by_name_a) & set(by_name_b))`), no
    decision. `res` is `None` when `_shared_shape` found no shared axis at
    all -- serialised as the same stable empty-string key every such call
    produces (never matched by `blob_mint`/`blob_recognize`'s `shared_count>0`
    guard, so its exact value is inert; kept stable only for readability)."""
    import json as _json
    if res is None:
        return ""
    try:
        return _json.dumps(res)
    except Exception:
        return ""


def record_correspondence(substrate, node_a, sig_a, node_b, sig_b):
    """MECHANICAL INGEST (exactly `domains/meta_shape.py::observe`'s pattern):
    run `_shared_shape` (UNCHANGED, not touched by this function) over the two
    signatures, write the result as a `Correspondence` node with `about_a`/
    `about_b` edges to the two REAL `ShapeSignature` nodes, and hand off to
    `seeds/blob_edge_correspondence.json`'s rules -- which decide (never
    Python) whether this is a NEW structural pattern (`blob_mint`, mirrors
    `sd_mint_quantum`), an ALREADY-HELD one (`blob_recognize`, mirrors
    `sd_dedup_existing`), or no collapse at all (`blob_no_collapse`).

    Returns `{shared, fixed, persisted, ...}`. `persisted` is `False` (with
    `shared`/`fixed` still populated, exactly `_shared_shape`'s own honest
    values) when there is no live graph or no real node id for either side --
    the correspondence is still computed, just not written, matching
    `_shared_shape`'s own honest-non-match shape rather than raising."""
    shared, fixed = _shared_shape(substrate, sig_a, sig_b)
    out = {"shared": shared, "fixed": fixed, "persisted": False}
    sub = getattr(substrate, "s", substrate)
    if node_a is None or node_b is None or not hasattr(sub, "add_node"):
        return out
    key = _canon_shared_shape(shared)
    try:
        cid = sub.add_node("Correspondence", {
            "status": "pending",
            "shared_count": int(fixed),
            "transform_key": key,
        })
        sub.add_edge(cid, "about_a", node_a)
        sub.add_edge(cid, "about_b", node_b)
        ag = _agent_node_id(substrate)
        if ag is not None:
            sub.add_edge(ag, "observed_correspondence", cid)
        native = getattr(sub, "_inner", sub)
        native.run_rules()
        status = sub.node(cid)["attrs"].get("status")
        out.update({"persisted": True, "node": cid, "transform_key": key, "status": status})
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _resolve_blob_edge(substrate, transform_key: str):
    """Mechanical read-back: the held `BlobEdge` node carrying this
    `transform_key`, if any -- the SAME equality-scan pattern `induce_concern`
    already uses to re-resolve a `CapabilityAxis` by `capability_keys` after
    `sd_dedup_existing` leaves it un-edged (see that rule's own comment).
    Never a decision -- the rule already decided `status`; this only finds
    the node the rule's `Exists` check already confirmed exists."""
    sub = getattr(substrate, "s", substrate)
    try:
        for n in sub.nodes("BlobEdge"):
            if sub.node(n)["attrs"].get("transform_key") == transform_key:
                return n
    except Exception:
        pass
    return None


_COMPOSE_PROVENANCE = (
    "the plan is the AGENT'S: each step's part was selected by the held "
    "shape-matcher (AntiUnify+FixedCount fit, Covers coverage — Rust Terms) "
    "as a best-fitting held part to the partial assembly's residual; Python only "
    "iterated the BEAM frontier and read the matcher's Argmax. No LLM, no "
    "Python decision over the composition.")


# ---------------------------------------------------------------------------
# ANALOGICAL MECHANISM TRANSFER — the missing link diagnosed by the rule-index
# build cc98b4eb. categorise_by_shape RECOGNISES a concern's meta-shape and the
# agent HOLDS mechanisms (spatial foveation IS a selective_gating mechanism), but
# the two were DISCONNECTED: literal ShapeDecode decodes a goal against held parts
# by SURFACE predicate overlap, so a concern written in a NEW domain's vocabulary
# (scan/gate/rules) shares no leaf with a mechanism written in another domain's
# (quantize/focus/space) and decodes to residual/total_fit=0 — even when the two
# realise the SAME meta-shape. mint-as-novel then fires as a false fallback.
#
# The fix (competent-man / capabilities-not-fixes): INDEX held mechanisms by
# meta-shape (seeds/mechanism_index.json), and on a RECOGNISED shape RETRIEVE the
# shape's mechanism and TRANSFER it — re-instantiate the mechanism's abstract
# STEPS with the GOAL's own fillers (space->rules, quanta->event-type,
# focus->focus). The target fillers are DERIVED from the goal's own
# predicate/argument structure via each slot's cue (never stored on the
# mechanism), so the output plan is the GOAL domain's, structurally isomorphic to
# the source: real transfer, not a lookup. This is retrieve-BEFORE-mint: mint is
# now the fallback only for genuinely-unrecognised shapes.
# ---------------------------------------------------------------------------

_TRANSFER_PROVENANCE = (
    "the plan is AUTHORED BY ANALOGICAL MECHANISM TRANSFER: the goal's meta-shape "
    "was recognised by the agent's own categorise_by_shape, a held mechanism "
    "indexed under that shape was retrieved (seeds/mechanism_index.json), and its "
    "abstract steps were re-instantiated with the GOAL's OWN fillers — each filler "
    "derived from the goal's predicate/argument structure via the slot's cue, not "
    "read off the mechanism. The plan is the target domain's, isomorphic to the "
    "source: transfer across a shared meta-shape, not a lookup. No LLM.")

# The domain-noun test, the filler-derivation (`_filler_after_cue`), the
# retrieve+substitution (`transfer_mechanism`), AND the SHAPE->MECHANISM index
# read (`_load_mechanisms`) that used to live here are GONE — they are now the
# Rust `TransferDecode` Term (runners/dsl/src/shape_decode.rs::eval_transfer_decode
# + shape_decode::load_mechanisms), joining the ShapeDecode / TransformDecode /
# DimInfer Term family. The Term reads the `Mechanism` nodes FROM THE GRAPH itself
# (exactly as `ShapeDecode` reads its `codebook_type`); Python keeps only a thin
# one-call `native.evaluate` shim (`retrieve_and_transfer_mechanism`) — the
# RETRIEVE, CODEBOOK READ, FILLER-DERIVATION, and SUBSTITUTION are all Rust now.


def _tuples_to_lists(x):
    """Mechanical structural coercion of the `TransferDecode` Term's output back
    to the list-of-lists shape the pre-migration Python returned. The Rust Value
    model has no list variant, so its Tuples surface as Python tuples; this walks
    the result and turns every tuple into a list (dicts/scalars untouched). Pure
    boundary I/O — no decision, no transform."""
    if isinstance(x, (tuple, list)):
        return [_tuples_to_lists(v) for v in x]
    if isinstance(x, dict):
        return {k: _tuples_to_lists(v) for k, v in x.items()}
    return x


def retrieve_and_transfer_mechanism(substrate, goal_signature):
    """RETRIEVE-THEN-TRANSFER — a THIN SHIM over the Rust `TransferDecode` Term
    (runners/dsl/src/shape_decode.rs::eval_transfer_decode). Python does only
    mechanical I/O: ONE `native.evaluate` of TransferDecode — which DERIVES the
    goal's meta-shape ITSELF via the shared `recognise_meta_shape` scorer (the
    SAME recognition path the agent's `categorise_by_shape` faculty uses — no
    Python shape-derivation, no duplicated scorer), READS the held `Mechanism`
    index FROM THE GRAPH (shape_decode::load_mechanisms, exactly as `ShapeDecode`
    reads its `codebook_type`; the old `_load_mechanisms` Python read is GONE),
    RETRIEVES the mechanism(s) indexed under the recognised shape, DERIVES each
    slot's target filler from the GOAL's own structure via its cue,
    RE-INSTANTIATES the mechanism's steps with those fillers, and keeps the
    highest-fit candidate. Shape recognition + codebook read + retrieve +
    filler-derivation + substitution all live in Rust; the returned report is
    `_tuples_to_lists`-coerced back to the pre-migration list shape.

    Returns None when NO mechanism index is held (the Term returns `Value::None`
    when the graph holds zero mechanisms — nothing to transfer). Returns a report
    with `transferred=None` when a shape is recognised but no mechanism is indexed
    under it (an honest wall) — mint stays the fallback, never fabricated."""
    native = _native_eval2(substrate)
    term = {
        "type": "TransferDecode",
        "goal": {"type": "Lit", "value": [list(x) for x in (goal_signature or [])]},
    }
    result = native.evaluate(term, {})
    return None if result is None else _tuples_to_lists(result)


def compose_design_for_goal(substrate, goal_signature, *, beam: int = 3, max_steps: int = 8,
                            cand_k: int = 3, exclude=None, budget: int = 0):
    """THE GENERALISED RUNG-2 COMPOSER — a SHAPE-GUIDED BOUNDED BEAM assembler,
    now a THIN SHIM over the Rust `ShapeDecode` Term (the dequantizer — see
    runners/dsl/src/shape_decode.rs). The whole beam-search (state 4-tuple,
    ranking, pruning, dedupe, termination, best-tracking) is the Rust
    evaluator's; this function only builds the Term JSON, evaluates it ONCE,
    and re-attaches the `provenance` string (the one field the Term omits, by
    design, so the Python caller supplies it — matching the pre-migration
    return shape field-for-field). NO Python decision over the composition.

    GAMMA_SEARCH_COMPLETENESS_FIXES.md Bug 2: `beam` no longer TRUNCATES the
    search (kept for back-compat / reporting only — see the Term's own doc);
    completeness within a declared cost class is now bounded by a total
    expansion `budget` instead (`<=0`, the default here, selects the Rust
    side's own default — see `shape_decode::DEFAULT_SD_BUDGET`). Exposed as
    a plain pass-through kwarg — which class of caller wants a bigger or
    smaller budget is a caller-side judgment call, not a decision this shim
    makes; the default (0 -> Rust default) reproduces every existing
    caller's behaviour unchanged."""
    native = _native_eval2(substrate)
    term: dict[str, Any] = {
        "type": "ShapeDecode",
        "goal": {"type": "Lit", "value": [list(x) for x in (goal_signature or [])]},
        "beam": beam,
        "max_steps": max_steps,
        "cand_k": cand_k,
        "budget": budget,
    }
    if exclude:
        excl = list(exclude) if isinstance(exclude, (list, set, tuple)) else [exclude]
        term["exclude"] = {"type": "Lit", "value": [str(e) for e in excl]}
    result = native.evaluate(term, {})
    if not isinstance(result, dict):
        return result
    if result.get("authored"):
        result = dict(result)
        result["provenance"] = _COMPOSE_PROVENANCE
        return result
    # LITERAL DECODE FAILED (authored=False -> residual/mint). Before conceding,
    # try ANALOGICAL MECHANISM TRANSFER: if the goal's meta-shape is RECOGNISED and
    # a held mechanism is indexed under that shape, TRANSFER it into the goal's
    # domain and author the plan from it. No-op (returns the untouched residual)
    # when no mechanism index is held — so the default boot is byte-identical.
    transfer = retrieve_and_transfer_mechanism(substrate, goal_signature)
    if transfer and transfer.get("transferred") \
            and transfer["transferred"].get("total_fit", 0) > 0:
        t = transfer["transferred"]
        out = dict(result)
        out["authored"] = True
        out["authored_by"] = "mechanism_transfer"
        out["transferred_from"] = {"mechanism": t["mechanism"],
                                   "source_domain": t["source_domain"],
                                   "meta_shape": t["meta_shape"]}
        out["slot_map"] = t["slot_map"]
        out["plan"] = t["plan"]
        out["ordered_parts"] = [t["mechanism"]]
        out["total_fit"] = t["total_fit"]
        out["unbound_roles"] = t["unbound_roles"]
        out["provenance"] = _TRANSFER_PROVENANCE
        return out
    return result


def goal_signature_from_held_concept(substrate, concept_name):
    """DERIVE a goal's target shape from a HELD CONCEPT (PUSH 2 — removes the fed-doc
    crutch). The agent authors the goal SHAPE from its OWN holdings, given only a
    concept NAME: first its held shape-SIGNATURE (the richest, already shape-authored),
    else author from the Concept's own definition via the held RelationCue perception
    (author_signature). Returns (signature, source) or (None, reason) — an honest WALL
    when nothing held names the concept (the un-held control). No fed text, no LLM."""
    if not concept_name:
        return None, "no concept named"
    name = str(concept_name).strip().lower()
    sigs = _load_shape_signatures(substrate)
    # 1) a held shape-signature whose name matches (the agent already shape-authored it)
    for nm, (kind, sig, src) in sigs.items():
        if nm.lower() == name or name in nm.lower() or nm.lower() in name:
            if sig:
                return [list(x) for x in sig], f"held shape-signature {nm!r} ({kind})"
    # 2) author the shape from the held Concept's own definition (RelationCue perception)
    sig, defn, cname = author_signature(substrate, concept_name)
    if sig:
        return [list(x) for x in sig], f"authored from held Concept {cname!r}'s definition"
    return None, (f"no held concept names {concept_name!r} with a definition the RelationCue "
                  f"perception can author a shape from (un-held — an honest wall, not faked)")


def compose_design_for_concept(substrate, concept_name, **kw):
    """Author a design plan for a goal given as a held CONCEPT NAME — derive the goal
    shape from the agent's OWN holdings (goal_signature_from_held_concept), then run the
    beam composer. The whole loop is the agent's: goal-shape from held concept, plan
    from held shape-matcher. No fed doc, no LLM. Returns the composition + the goal
    source, or an honest {authored:False, reason} when the concept is un-held."""
    gsig, source = goal_signature_from_held_concept(substrate, concept_name)
    if not gsig:
        return {"authored": False, "reason": source, "concept": concept_name}
    # exclude the goal-concept itself from the parts pool (can't compose X out of X)
    kw.setdefault("exclude", [concept_name])
    out = compose_design_for_goal(substrate, gsig, **kw)
    out["concept"] = concept_name
    out["goal_source"] = source
    out["goal_signature"] = gsig
    return out


def grow_part_library(substrate, concept_names):
    """PUSH 3 — GROW the composer's part library by SIGNATURE-AUTHORING. For each held
    Concept name, the agent authors its structural shape-signature from the Concept's
    OWN definition via the held RelationCue structural-extraction (author_signature —
    the same self-referential move), and installs it as a ShapeSignature node so the
    composer can use it as a new part. The SHAPE is the agent's (authored, not
    hand-written); the install is mechanical graph mutation (adapter-admissible).
    Returns {grown:[names], skipped:[(name,reason)]} — honest about which authored."""
    import json as _json
    sub = getattr(substrate, "s", substrate)
    existing = set(_load_shape_signatures(substrate).keys())
    grown, skipped = [], []
    for cn in concept_names:
        name = str(cn)
        if name in existing:
            skipped.append((name, "already a held part"))
            continue
        sig, defn, cname = author_signature(substrate, name)
        if not sig:
            skipped.append((name, "no held Concept definition to author a shape from"))
            continue
        try:
            sub.add_node("ShapeSignature", {
                "name": name, "kind": "authored",
                "signature": _json.dumps([list(x) for x in sig]),
                "concept": cname,
            })
            grown.append(name)
            existing.add(name)
            # DYNAMIC QUANTIZATION closes the loop: bump the agent's codebook
            # epoch (mechanical set_attr) so `sd_redecode` (seeds/shape_decode_
            # loop.json) re-arms any Observation last decoded under an older
            # codebook — the new quantum triggers a re-decode, tick-driven.
            ag_node = _agent_root_node(sub)
            if ag_node is not None:
                cur = sub.node(ag_node)["attrs"].get("codebook_epoch") or 0.0
                sub.set_attr(ag_node, "codebook_epoch", float(cur) + 1.0)
        except Exception as e:
            skipped.append((name, f"install failed: {e}"))
    return {"grown": grown, "skipped": skipped, "library_size": len(existing),
            "how": ("the agent AUTHORED each new part's shape from the held Concept's own "
                    "definition (author_signature = RelationCue structural-extraction); the "
                    "install is mechanical. No hand-written shapes, no LLM.")}


def _bridge_keyword(meta_arg):
    """Pick the named math/faculty from the question's meta-arg (surface scan over
    the held signature names + their aliases). Not a decision about meaning."""
    text = (meta_arg or "").lower()
    aliases = {
        "fractal": "fractal", "self-similar": "self_similarity", "self similar": "self_similarity",
        "self-similarity": "self_similarity", "recursion": "phi_bounded_recursion",
        "recursive": "phi_bounded_recursion", "phi": "phi_bounded_recursion", "golden": "phi_bounded_recursion",
        "symmetry": "symmetry", "symmetric": "symmetry", "curvature": "curvature",
        "topology": "topology", "topological": "topology",
    }
    for k, v in aliases.items():
        if k in text:
            return v
    return None


def _run_math_bridge(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """MATH<->CAPABILITY BRIDGE: given a math (from the question), find the held
    FACULTY it SHARES A SHAPE with, by running the held shape-matcher (AntiUnify)
    over their structural signatures. Returns the best connection (the shared
    skeleton + strength) + the proposal. The connection is the matcher's, not a
    string. If no math is named, returns the strongest math<->faculty connection
    overall (so 'what math for shape generation?' surfaces a proposal)."""
    sigs = _load_shape_signatures(substrate)
    if not sigs:
        return {"unwired": "no ShapeSignature nodes held (boot seeds/math_capability_shapes.json)"}
    maths = {nm: v for nm, v in sigs.items() if v[0] == "math"}
    facs = {nm: v for nm, v in sigs.items() if v[0] == "faculty"}
    if not maths or not facs:
        return {"unwired": "need both math and faculty ShapeSignatures to bridge"}

    named = _bridge_keyword(meta_arg)
    authored = None
    # SELF-EXTEND: if the question names a math with NO seeded signature, AUTHOR one
    # from its held Concept's definition (the held structural extraction), then bridge it.
    if named is None and meta_arg:
        sig, defn, cname = author_signature(substrate, meta_arg)
        if sig:
            authored = {"name": cname or meta_arg, "signature": sig, "definition": defn}
            maths = dict(maths)
            maths[authored["name"]] = ("math", sig, cname)
            named = authored["name"]
        else:
            # NAMED a math but NO structural signature could be authored from its
            # definition -> honest no-connection (it shares no structural shape with
            # any faculty). NOT a fall-back to the strongest seeded math (spurious).
            return {"asked_about": meta_arg, "self_authored": None,
                    "connection": None, "connected": False,
                    "note": (f"no structural signature could be authored for {meta_arg!r} from its held "
                             "definition (no relation-cue fired) — it shares no structural shape with my "
                             "faculties; honest no-connection, not a forced match.")}
    # candidate math set: the named one, else all (then pick the strongest connection)
    math_names = [named] if (named and named in maths) else list(maths.keys())

    best = None  # (fixed, math_name, fac_name, shared)
    per_math = {}
    for mn in math_names:
        m_sig = maths[mn][1]
        m_node = _shape_signature_node_id(substrate, mn)
        # the best faculty for this math = argmax shared-shape (read-out of the matcher)
        mb = None
        for fn, (_, f_sig, _) in facs.items():
            # BLOB_EDGE_SD_LOOP: record_correspondence wraps `_shared_shape`
            # UNCHANGED (same shared/fixed values) and additionally persists
            # the collapse as a Correspondence -> BlobEdge graph fact when
            # both operands are real ShapeSignature nodes (degrades to the
            # bare `_shared_shape` computation, `persisted=False`, otherwise
            # -- e.g. a self-authored `mn` with no held ShapeSignature node).
            f_node = _shape_signature_node_id(substrate, fn)
            corr = record_correspondence(substrate, m_node, m_sig, f_node, f_sig)
            shared, fixed = corr["shared"], corr["fixed"]
            if mb is None or fixed > mb[0]:
                mb = (fixed, fn, shared)
        per_math[mn] = {"faculty": mb[1], "shared_leaves": mb[0]}
        if best is None or mb[0] > best[0]:
            best = (mb[0], mn, mb[1], mb[2])

    fixed, math_name, fac_name, shared = best
    # NEGATIVE-control margin: also report the WEAKEST faculty for the chosen math
    m_sig = maths[math_name][1]
    worst = min(((_shared_shape(substrate, m_sig, fsig)[1], fn) for fn, (_, fsig, _) in facs.items()),
                key=lambda t: t[0])
    connected = fixed > worst[0] and fixed > 0
    return {
        "asked_about": named,
        "self_authored": authored,                  # the signature the agent authored (if any), + its source definition
        "connection": {"math": math_name, "faculty": fac_name, "shared_leaves": fixed,
                       "shared_shape": shared},
        "discriminates": {"strongest_faculty": fac_name, "strongest_leaves": fixed,
                          "weakest_faculty": worst[1], "weakest_leaves": worst[0],
                          "margin": fixed - worst[0]},
        "connected": connected,
        "per_math": per_math,
        "how": ("I CONNECT a mathematics to a held faculty by running my OWN shape-matcher (AntiUnify) over "
                "their structural signatures and reading off the shape they SHARE. The connection is the "
                "shared skeleton my matcher finds — not asserted. For "
                f"{math_name!r} the strongest-sharing faculty is {fac_name!r} ({fixed} shared leaves); a "
                f"non-sharing faculty ({worst[1]!r}) keeps only {worst[0]} — so the bridge discriminates."),
        "proposal": (f"realise {math_name} via the {fac_name} faculty: they share the structural shape "
                     f"{shared}. " + (
            "A fractal = the residual-recurrence applied to a SCALED COPY of its own output "
            "(IFS / L-system): 'build the new from the bounded prior, refer to self, bound by scale, base "
            "case' — the same bounded-recursion-fixedpoint my Fold-iterate of Substitute already runs."
            if (math_name in ("fractal", "self_similarity", "phi_bounded_recursion")
                and fac_name == "residual_recurrence") else
            "compose this math on the faculty that shares its shape.")),
    }


# ---------------------------------------------------------------------------
# reflect(meta_target, meta_arg, substrate) — the entry the driver routes to.
# ---------------------------------------------------------------------------

def _run_reading_trace(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """READING INTROSPECTION — the agent reads its OWN reading trail off the graph,
    the way `_run_self_shape` reads its meta-shapes: a pure graph query, no decision.

    The reading collapse loop (domains/reading_collapse) leaves a durable trail in
    the substrate — the SAME collapse the sd loop leaves for shapes, pointed at
    language: (1) the CONSTRUCTION CODEBOOK it decodes against (held ShapeSignature
    {kind:'construction'} nodes, including any it MINTED — learned==1.0); (2) the
    OBSERVATIONS the sd loop stamped while learning a novel construction (status /
    decode / residual / covered_by, per seeds/shape_decode_loop.json); (3) the
    grounded PREDICATIONS it wrote (Concept nodes source=='reading_collapse' + the
    construction relation edges between them). Read them, never author. Honest-null
    when no reading trail is held (a fresh agent that has read nothing).

    `meta_arg`, when given, filters the predication read to reading Concepts whose
    name contains it (a focus probe); it never changes what is read."""
    import json as _json
    codebook: list = []
    learned: list = []
    rel_vocab: set = set()
    for n in substrate.nodes("ShapeSignature"):
        at = substrate.node(n)["attrs"]
        if at.get("kind") != "construction":
            continue
        entry = {"name": at.get("name"), "signature": at.get("signature"),
                 "learned": bool(at.get("learned"))}
        codebook.append(entry)
        if entry["learned"]:
            learned.append(entry)
        tmpl = at.get("ground_template")
        if isinstance(tmpl, str):
            try:
                pred = (_json.loads(tmpl) or {}).get("pred")
                if isinstance(pred, str) and pred != "@verb":
                    rel_vocab.add(pred)
            except Exception:      # noqa: BLE001
                pass

    observations: list = []
    for o in substrate.nodes("Observation"):
        at = substrate.node(o)["attrs"]
        resid = at.get("residual")
        observations.append({
            "status": at.get("status"),
            "covered_by": at.get("covered_by"),
            "residual_len": (len(resid) if isinstance(resid, (list, tuple)) else None),
            "decoded_epoch": at.get("decoded_epoch"),
            "key": at.get("key"),
        })

    # reading Concepts + the fixed-relation predications between them (the verb-
    # relation event predications are edges too, but their relation label is the
    # verb itself, not a fixed vocabulary — enumerated only over the codebook's
    # own relation vocabulary here, an honest, bounded read).
    concept_idx: dict = {}
    concept_names: list = []
    for c in substrate.nodes("Concept"):
        at = substrate.node(c)["attrs"]
        if at.get("source") != "reading_collapse":
            continue
        nm = at.get("name")
        if not isinstance(nm, str):
            continue
        if isinstance(meta_arg, str) and meta_arg and meta_arg.lower() not in nm.lower():
            continue
        concept_idx[c] = nm
        concept_names.append(nm)
    predications: list = []
    for c, nm in concept_idx.items():
        for rel in sorted(rel_vocab):
            for tgt in substrate.neighbours(c, rel):
                tn = concept_idx.get(tgt)
                if tn is None:
                    at = substrate.node(tgt)["attrs"]
                    tn = at.get("name") if isinstance(at.get("name"), str) else None
                if tn is not None:
                    predications.append([rel, nm, tn])

    # EVENT-ROLE codebook — the VerbFrame role-assignment ladder (svo_base / case /
    # inversion) the event grounding DECODES over, plus the participant RoleFrames
    # (the thematic oblique + any role the agent GREW from a residual). The agent
    # reads its own argument roles here, the same way it reads its constructions.
    verb_frames: list = []
    for n in substrate.nodes("VerbFrame"):
        at = substrate.node(n)["attrs"]
        if at.get("codebook") != "event_roles":
            continue
        verb_frames.append({"name": at.get("name"), "priority": at.get("priority")})
    verb_frames.sort(key=lambda e: (e["priority"] if e["priority"] is not None else 0.0))
    role_frames: list = []
    grown_roles: list = []
    for n in substrate.nodes("RoleFrame"):
        at = substrate.node(n)["attrs"]
        if at.get("codebook") != "event_roles":
            continue
        entry = {"role": at.get("role"), "head": at.get("head_attr"),
                 "grown": bool(at.get("minted_from_residual"))}
        role_frames.append(entry)
        if entry["grown"]:
            grown_roles.append(at.get("role"))

    epoch = None
    for a in substrate.nodes("Agent"):
        at = substrate.node(a)["attrs"]
        if not at.get("is_class"):
            epoch = at.get("codebook_epoch")
            break

    if not (codebook or observations or concept_names or verb_frames):
        return {"unwired": "no reading trail held on this substrate "
                "(the agent has read no prose — ensure_codebook + read_clause "
                "leave the codebook / observations / predications this reads)"}
    return {"reading_trace": "collapse over a construction codebook",
            "codebook_size": len(codebook),
            "constructions": sorted(e["name"] for e in codebook if e["name"]),
            "minted_constructions": sorted(e["name"] for e in learned if e["name"]),
            "n_minted": len(learned),
            "codebook_epoch": epoch,
            "observations": observations,
            "n_observations": len(observations),
            "concepts": sorted(set(concept_names)),
            "n_concepts": len(set(concept_names)),
            "predications": predications,
            "n_predications": len(predications),
            "verb_frames": [e["name"] for e in verb_frames if e["name"]],
            "n_verb_frames": len(verb_frames),
            "role_frames": sorted(e["role"] for e in role_frames if e["role"]),
            "grown_roles": sorted(r for r in grown_roles if r),
            "note": ("the agent's reading is COLLAPSE over its held construction "
                     "codebook; this reads the trail off the graph — the codebook it "
                     "decodes against (with any construction it minted), the sd-loop "
                     "observations it stamped while learning, and the predications it "
                     "grounded — the same graph the reading rules themselves read")}


def _run_referent_trace(substrate, meta_arg: Optional[str]) -> dict[str, Any]:
    """REFERENT INTROSPECTION — the agent reads its OWN tracked-referent pool off the
    graph, the layer `reading_trace` is BLIND to. `reading_trace` reads the
    construction codebook + sd-loop observations (the DECODE trail); the entities the
    reading actually MINTED live one layer down, in the situation model — `SmEntity`
    nodes with their coref attrs, wired to the `Mention`s that `refers_to` them. This
    faculty reads THAT layer, so the agent can SEE a referent it should not have minted
    (a dialogue epithet like 'wretch', a parse-glom like 'unlucky_wretch_that_i') the
    same way it sees a decode residual — a pure graph query, no decision.

    Each referent is reported with: its coref category / mention count; its
    CLEANLINESS (the held `_grounded_cleanliness` structural read — < 1.0 flags a
    parse glom); whether its head is NON-NOMINAL (the held POS faculty — an adj/adv/
    verb surface that is a property or predicate, not a referent); and its incoming
    `refers_to` count (how many mentions bound to it — the coref weight a spurious
    referent STEALS from a real one). `suspect` is the mechanical conjunction of those
    held signals (category in person/animal BUT unclean or non-nominal) — the same
    admissible lexical status as `narrative_structure._is_nonnominal`, not a decision.

    `meta_arg`, when given, filters to referents whose name contains it (a focus
    probe). Honest-null when no situation model is held."""
    from domains import coref_entities as _ce
    from domains import narrative_structure as _ns

    # FEATURE BELIEFS — the revisable-feature-belief layer, keyed by entity name.
    # Each carries provenance (source/confidence/support) and, if it was overturned
    # by a surprise, `revised_from` + `revised_at_turn`. The agent reads these to
    # SEE what it believes about a referent's features and THAT it revised one.
    beliefs_by_entity: dict = {}
    revisions: list = []
    for b in substrate.nodes("FeatureBelief"):
        bat = substrate.node(b)["attrs"]
        ent = bat.get("entity")
        rec_b = {
            "feature": bat.get("feature"), "value": bat.get("value"),
            "source": bat.get("source"), "confidence": bat.get("confidence"),
            "support": bat.get("support"), "conflict_count": bat.get("conflict_count"),
            "anomaly": bat.get("anomaly"),
        }
        if bat.get("revised_from") not in (None, ""):
            rec_b["revised_from"] = bat.get("revised_from")
            rec_b["revised_at_turn"] = bat.get("revised_at_turn")
            revisions.append({
                "entity": ent, "feature": bat.get("feature"),
                "from": bat.get("revised_from"), "to": bat.get("value"),
                "at_turn": bat.get("revised_at_turn"),
                "why": ("a WEAK reader-inference belief (low salience-margin "
                        "confidence) was overturned once conflicting observations "
                        "for this entity+feature accumulated -- the surprise-driven "
                        "explanation collapse chose reader_wrong")})
        beliefs_by_entity.setdefault(ent, []).append(rec_b)

    refers_in: dict = {}
    for m in substrate.nodes("SmMention"):
        for tgt in substrate.neighbours(m, "refers_to"):
            refers_in[tgt] = refers_in.get(tgt, 0) + 1

    # event participation — a referent that ACTS is the `agent` of an SmEvent; a mere
    # property/naming complement never is. Count agent-role vs theme-role per entity.
    acts_as_agent: dict = {}
    acts_as_theme: dict = {}
    for e in substrate.nodes("SmEvent"):
        for tgt in substrate.neighbours(e, "agent"):
            acts_as_agent[tgt] = acts_as_agent.get(tgt, 0) + 1
        for tgt in substrate.neighbours(e, "theme"):
            acts_as_theme[tgt] = acts_as_theme.get(tgt, 0) + 1

    referents: list = []
    suspects: list = []
    for n in substrate.nodes("SmEntity"):
        at = substrate.node(n)["attrs"]
        nm = at.get("name")
        if not isinstance(nm, str):
            continue
        if isinstance(meta_arg, str) and meta_arg and meta_arg.lower() not in nm.lower():
            continue
        cat = at.get("coref_category")
        n_agent = acts_as_agent.get(n, 0)
        n_theme = acts_as_theme.get(n, 0)
        try:
            clean = float(_ce._grounded_cleanliness(nm))
        except Exception:      # noqa: BLE001
            clean = None
        try:
            nonnominal = bool(_ns._is_nonnominal(nm))
        except Exception:      # noqa: BLE001
            nonnominal = False
        rec = {
            "name": nm,
            "category": cat,
            "mentions": at.get("coref_mentions"),
            "cleanliness": clean,
            "nonnominal_head": nonnominal,
            "refers_to_in": refers_in.get(n, 0),
            "acts_as_agent": n_agent,
            "acts_as_theme": n_theme,
            # THEMATIC LAYER: the entity's stored LAST thematic-role rank
            # (agent < theme < goal). acts_as_theme counts INCLUDE the oblique
            # participants the order-N descent now registers ('drove ... over the
            # poor dog' -> the dog becomes a theme of the drove event), so the agent
            # can SEE which referents entered the thematic layer via a PP oblique
            # rather than a core argument slot.
            "last_role_rank": at.get("coref_rolerank"),
            "beliefs": beliefs_by_entity.get(nm, []),
        }
        referents.append(rec)
        # a referent the agent tracks as a CHARACTER (person/animal) that NEVER ACTS
        # (agent of no SmEvent) yet has mentions binding to it is a PREDICATE NOMINAL /
        # naming complement, not a discourse entity — the RELATIONAL signal that catches
        # a shape-clean epithet ('wretch') the lexical signals (clean=1.0, nominal) miss.
        # The parse-glom / non-nominal shape signal still flags the mangled fragments.
        shape_junk = (clean is not None and clean < 1.0) or nonnominal
        never_acts = (n_agent == 0 and refers_in.get(n, 0) > 0)
        if cat in ("person", "animal") and (shape_junk or never_acts):
            rec = dict(rec)
            rec["why"] = "parse-glom/non-nominal" if shape_junk else "never acts (naming-complement only)"
            suspects.append(rec)

    if not referents:
        return {"unwired": "no situation model held on this substrate "
                "(the agent has tracked no referents — read a text first so the "
                "SmEntity pool + refers_to edges this reads exist)"}
    referents.sort(key=lambda r: (-(r["mentions"] or 0.0), r["name"]))
    suspects.sort(key=lambda r: (-(r["mentions"] or 0.0), r["name"]))
    return {"referent_trace": "the tracked-referent pool (situation model + coref)",
            "n_referents": len(referents),
            "referents": referents,
            "n_suspect": len(suspects),
            "suspect_referents": suspects,
            "n_revisions": len(revisions),
            "revisions": revisions,
            "note": ("the entities the reading MINTED live here (SmEntity + refers_to), "
                     "one layer below the construction codebook `reading_trace` reads; "
                     "a `suspect` referent is one the agent tracks as a character but "
                     "whose held cleanliness / POS signal says is a parse-glom or a "
                     "property, not a referent — the coref weight it steals is `refers_to_in`. "
                     "`last_role_rank` + `acts_as_theme` expose the THEMATIC layer: "
                     "oblique PP participants (the order-N descent into a post-verbal "
                     "PP) are folded into the theme counts, so a participant dropped by "
                     "the SVO head-reduction ('over the poor dog') is now held")}


# ---------------------------------------------------------------------------
# interlocutor_model -> "what do you know about me?" (Wave: interlocutor-as-
# modeled-participant, task 5 -- the user-facing proof the agent treats the
# chat like an actual discussion where it models the interlocutor, not the
# Cornelius Vane verdict repeated: "did NOT feel like it was modelling me as
# a specific interlocutor"). A pure mechanical read + format, the SAME
# _run_self_gaps shape: read graph -> return a state dict with a first-person
# `note`. Renders FOUR distinct strata, each visibly separate (course
# corrections 2026-07-11):
#   1. WHO -- name/self-ID, register/style/mood (interlocutor_model.py's
#      accumulated Party).
#   2. WHAT THEY'VE ASKED -- Goals `wanted_by` this party (task 2).
#   3. SAID vs MODELED -- for each Assertion this party made (Level 1,
#      immutable, verbatim), the modeled belief/want it grounds to (Level 2,
#      revisable, with its own confidence) -- explicitly worded as two
#      different things, never collapsed into one.
#   4. THE CALIBRATION -- how much the agent weights this party's self-reports
#      and WHY (structural creator-origin evidence / a matched
#      InterlocutorShape prior / a blend with their individual track record),
#      per `interlocutor_model.effective_reliability` + `decode_shape`.
# WHAT THEY'VE BEEN TOLD -- believed_concepts count + a capped sample (task 1).
# ---------------------------------------------------------------------------
def _active_interlocutor(substrate):
    """The party THIS conversation is currently addressing (agent -addressee->
    ad, task 1's live wiring) -- falls back to whichever Interlocutor is
    flagged active (interlocutor_model.py's own fallback) if no addressee
    edge exists yet (e.g. before the first `converse()` turn wired it)."""
    try:
        for ag in substrate.nodes("Agent"):
            if substrate.node(ag)["attrs"].get("is_class"):
                continue
            ads = list(substrate.neighbours(ag, "addressee"))
            if ads:
                return ads[0]
    except Exception:
        pass
    try:
        for n in substrate.nodes("Interlocutor"):
            if substrate.node(n)["attrs"].get("active"):
                return n
    except Exception:
        pass
    return None


_RELIABILITY_REASON = {
    "creator_origin": ("the identity material recording this substrate was derived "
                       "from decades of your own introspection — independent "
                       "structural evidence, not a self-report"),
    "shape_prior": ("your style and vocabulary place you in a shape I hold priors "
                    "for, and I don't have an individual track record with you yet"),
    "shape_prior+track_record": ("your style/vocabulary prior blended with your own "
                                 "track record so far"),
    "default": ("I have no track record with you yet, and self-report is weak "
               "evidence about anyone's own mind"),
}


def _run_interlocutor_model(substrate, meta_arg: Optional[str] = None) -> dict[str, Any]:
    party = _active_interlocutor(substrate)
    if party is None:
        return {"interlocutor_model": True, "known": False,
                "note": ("I haven't modelled a specific interlocutor yet in this "
                         "conversation — no one has been observed.")}
    at = substrate.node(party)["attrs"]
    name = at.get("name") or "you"
    register = at.get("register")
    mood = at.get("mood")
    believed = sorted(str(c) for c in (at.get("believed_concepts") or []))

    # WHAT THEY'VE ASKED (task 2: Goal -wanted_by-> party). Reading-flow
    # ORCHESTRATION goals (kind 'comprehend'/'produce_analysis' —
    # reading_drive.py's internal per-turn shadow-read plumbing, minted once
    # per comprehension pass regardless of what was said) are excluded: they
    # are real `wanted_by` provenance (the read WAS triggered by this party's
    # turn) but not a "thing they asked for" in the conversational sense —
    # showing them would drown every genuine request in internal noise.
    _INTERNAL_GOAL_KINDS = {"comprehend", "produce_analysis"}
    wants = []
    try:
        for g in substrate.in_neighbours(party, "wanted_by"):
            gat = substrate.node(g)["attrs"]
            if gat.get("kind") in _INTERNAL_GOAL_KINDS:
                continue
            desc = gat.get("raw") or gat.get("concept") or gat.get("object") or gat.get("kind")
            if desc and str(desc) not in wants:
                wants.append(str(desc))
    except Exception:
        pass

    # SAID vs MODELED (task 3, two levels).
    beliefs = []
    try:
        for a in substrate.neighbours(party, "asserted"):
            aat = substrate.node(a)["attrs"]
            entry = {"turn": aat.get("turn"), "said": aat.get("content"),
                     "verb": aat.get("verb"), "flavor": aat.get("flavor"),
                     "hedged": bool(aat.get("hedged")), "confidence": None,
                     "modeled_content": None, "contradicted": False}
            for l2 in substrate.in_neighbours(a, "about_assertion"):
                l2at = substrate.node(l2)["attrs"]
                entry["confidence"] = l2at.get("confidence")
                entry["contradicted"] = bool(l2at.get("contradicted_by_interlocutor"))
                # PROPOSITION-GRAIN (blind-spot closure R9, 2026-07-12): prefer
                # the FULL proposition the reader's own clause parse produced
                # (character_tom's `proposition_span`, the complement's
                # verbatim text — "the new scheduler is faster", not just its
                # head "new_scheduler") over the old head-grain fields. Gated
                # on `proposition_capture` — the seeded `mark_attitude_
                # proposition_capture` rule's own eligibility flag
                # (seeds/proposition_capture.json) — so ablating that rule
                # reverts every render to the pre-closure head-grain text even
                # though the richer data still sits on the node, proving the
                # decision lives in the rule, not here. Absent the flag (rule
                # ablated, or a legacy node minted before this closure), the
                # ORIGINAL head-grain read is byte-identical.
                if l2at.get("proposition_capture") == 1:
                    entry["modeled_content"] = l2at.get("proposition_span")
                elif aat.get("flavor") == "desire":
                    entry["modeled_content"] = l2at.get("idx_intentionality") or l2at.get("goal")
                else:
                    entry["modeled_content"] = l2at.get("referent")
                break
            beliefs.append(entry)
    except Exception:
        pass

    # THE CALIBRATION -- priors-by-shape-matching blended with track record
    # (task 3, refinements 2/3). `decode_shape`/`effective_reliability` are
    # dual-context (`getattr(agent,"s",agent)`), so they run directly off the
    # bare substrate this reader is handed.
    try:
        from domains import interlocutor_model as _im
        shape = _im.decode_shape(substrate, party)
        eff = _im.effective_reliability(substrate, party)
    except Exception:
        shape, eff = {"name": None, "fit": 0, "interval": 0.35, "expected_domains": []}, \
            {"value": 0.5, "source": "default", "n": None}

    parts = []
    if name and name != "user":
        parts.append(f"You are {name}.")
    else:
        parts.append("I don't have a name for you yet.")
    if register:
        reg_bit = f"Your register reads as {register}"
        if mood:
            reg_bit += f", currently {mood}"
        parts.append(reg_bit + ".")
    if wants:
        parts.append("What you've asked me to do: "
                     + "; ".join(f"“{w}”" for w in wants[:5]) + ".")
    if beliefs:
        bits = []
        for b in beliefs[:5]:
            turn_bit = f" (turn {int(b['turn'])})" if b.get("turn") is not None else ""
            said_bit = f"You said{turn_bit}: “{b['said']}”."
            if b["confidence"] is not None:
                verb_bit = "wanting" if b["flavor"] == "desire" else "believing"
                model_bit = (f" I model you as likely {verb_bit} "
                            f"{b['modeled_content'] or '(unspecified)'} "
                            f"(confidence: {b['confidence']:.2f}, from self-report only"
                            + (", hedged phrasing" if b["hedged"] else "")
                            + (", since revised by a correction" if b["contradicted"] else "")
                            + ").")
            else:
                model_bit = ""
            bits.append(said_bit + model_bit)
        parts.append(" ".join(bits))
    told_bit = f"I've told you {len(believed)} thing(s) so far"
    if believed:
        told_bit += ": " + ", ".join(believed[:8])
    parts.append(told_bit + ".")
    label = ("highly" if eff["value"] >= 0.75 else
            "moderately" if eff["value"] >= 0.4 else "cautiously")
    reason = _RELIABILITY_REASON.get(eff.get("source"), eff.get("source") or "default")
    calib = f"I weight your self-reports {label} (confidence {eff['value']:.2f}) because {reason}."
    if eff.get("source") != "creator_origin" and shape.get("name"):
        calib += (f" From your style and vocabulary I'd place you as {shape['name']} "
                 f"(fit: {shape.get('fit')}/4); within that I'd expect a reliability "
                 f"around {shape.get('prior', eff['value']):.2f} ± {shape.get('interval', 0.0):.2f}.")
        if eff.get("n"):
            calib += f" Your individual record so far ({eff['n']} self-report(s)) adjusts this."
    parts.append(calib)

    # TOM CAPACITY (course correction 2026-07-11, 4th refinement: "realistically,
    # some humans barely have theory of mind"). Mentioned ONLY when it deviates
    # from the default (0.5) -- a party the agent has no reason to think tracks
    # its own state unusually closely or poorly stays unremarked, exactly like
    # every other calibration in this reader that only speaks when it has
    # something to say.
    tom = None
    try:
        tom = _im.effective_tom_capacity(substrate, party)
    except Exception:
        tom = None
    if tom is not None and abs(tom - 0.5) >= 0.1:
        if tom >= 0.6:
            parts.append(f"You track my state closely (theory-of-mind estimate: {tom:.2f}).")
        else:
            parts.append(f"I spell things out for you rather than assume you're tracking "
                         f"what I've said (theory-of-mind estimate: {tom:.2f}).")

    note = " ".join(parts)
    return {"interlocutor_model": True, "known": True, "name": name, "register": register,
            "mood": mood, "wants": wants, "beliefs": beliefs, "told_count": len(believed),
            "told_concepts": believed[:8], "self_report_reliability": eff["value"],
            "self_report_reliability_source": eff.get("source"),
            "shape_name": shape.get("name"), "shape_fit": shape.get("fit"),
            "tom_capacity": tom, "note": note}


_DISPATCH = {
    "self_modification": _run_self_modification,
    "retrieval_design": _run_retrieval_design,
    "frontier": _run_frontier,
    "needed_input": _run_needed_input,
    "self_organisation": _run_self_organisation,
    "self_identity": _run_self_identity,
    "self_kind": _run_self_kind,
    "self_gaps": _run_self_gaps,
    "self_improvement_status": _run_self_improvement_status,
    "interlocutor_model": _run_interlocutor_model,
    "self_adoptions": _run_adoptions,
    "sorting_principle": _run_sorting_principle,
    "self_shape": _run_self_shape,
    "reading_trace": _run_reading_trace,
    "referent_trace": _run_referent_trace,
    "law_vs_cache": _run_law_vs_cache,
    "growth_decision": _run_growth_decision,
    "program_extraction": _run_program_extraction,
    "program_teaching": _run_program_teaching,
    "escalation": _run_escalation,
    "capability_understanding": _run_capability_understanding,
    "self_design": _run_self_design,
    "generate_shape": _run_generate,
    "recover_shape_law": _run_recover,
    "math_bridge": _run_math_bridge,
}

# Self-model queries (domains/self_model.py) — permanent registration of the
# entries self_model.register_self_model_dispatch() otherwise setdefaults in.
from domains import self_model as _self_model  # noqa: E402

_DISPATCH.setdefault("self_model_rule", _self_model.run_self_model_rule)
_DISPATCH.setdefault("self_model_topic", _self_model.run_self_model_topic)
_DISPATCH.setdefault("self_model_touches", _self_model.run_self_model_touches)
# operational self-introspection — how the agent OPERATES (its processes:
# learning=collapse, perceiving=sd-decode, world-attachment=adapter-ingest),
# read off held SelfProcess self-accounts (taught from the real architecture).
_DISPATCH.setdefault("self_process", _self_model.run_self_process)


def reflect(meta_target: str, meta_arg: Optional[str], substrate) -> dict[str, Any]:
    """Route a comprehended META-TARGET to the agent's matching HELD reflective
    faculty + return its structured self-answer. The meta side of the universal
    ask interface — the driver routes here for a self/meta question exactly as it
    rides the elevator for a world question. SEQUENCES the held faculty; adds no
    reflective reasoning. An unknown meta-target returns an honest unwired dict."""
    fn = _DISPATCH.get(meta_target)
    if fn is None:
        return {"unwired": (f"meta_target {meta_target!r} has no reflective faculty "
                            f"wired (the routing target exists, the faculty is "
                            f"unsupplied — honest, not faked)")}
    return fn(substrate, meta_arg)


def boot_reflective_substrate():
    """Build a substrate carrying the agent's HELD reflective machinery (the
    epistemic-access model + the source-provenance concepts), so the reflective
    faculties can run over it. A mechanical install (no decisions) — the SAME
    boot cmsg102's ask_jabberwock_how_to_retrieve used. Returns (substrate,
    installed-report). The caller hands this substrate to QuestionDriver so a meta
    question's reflect() routes over the held machinery."""
    import os
    import sys
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _dslpy = os.path.join(ROOT, "runners", "dsl", "python")
    if _dslpy not in sys.path:
        sys.path.insert(0, _dslpy)
    from substrate_rs import _native
    from domains import grounded_representation as _gr

    s = _native.Substrate()
    _gr.open_grounding_productions(s)
    # open the productions the held-machinery install needs (same as cmsg102).
    types = ("Microtheory", "Concept", "Rule", "SourceEvent", "PendingGap",
             "EpistemicAccessStance", "SocialCapital", "LexEntry")
    edges = ("has_concept", "has_rule", "genlMt", "refers_to", "built_from",
             "is_a", "has_event", "owns_microtheory")
    for t in types:
        for u in types:
            for ed in edges:
                try:
                    s.add_production({
                        "src": {"type": t, "var": "src"},
                        "edge_type": ed,
                        "tgt": {"type": u, "var": "tgt"},
                        "where": None,
                        "weight": {"type": "Lit", "value": 1.0},
                        "provenance": "reflect:open",
                    })
                except Exception:
                    pass
    # NOTE: this loop used to also install `domains.lvp_subseeds` (epistemic_access)
    # and `domains.communication_concepts` (source provenance) — both Python modules
    # are DELETED (the mass domains/*.py deletion this repo underwent; see CLAUDE.md's
    # "Migration is COMPLETE" note). `seeds/epistemic_access.json` and
    # `seeds/communication_concepts.json` still exist on disk, but in a bespoke
    # `concepts`/`microtheory` schema those deleted installers alone knew how to
    # apply — NOT the standard `nodes`/`edges`/`rules` seed-manifest schema
    # `load_seed_manifest` consumes, so there is no drop-in seed to load in their
    # place without authoring a new installer (out of this migration's scope; a
    # new domains/*.py "seed builder" module is a legitimate future addition, not
    # a mechanical substitution here). Dropped cleanly rather than importing dead
    # modules — `held_concepts` in the reflective `retrieval_design` answer stays
    # empty (0), the SAME pre-migration behaviour, until that follow-up lands.
    installed = {}
    try:                                                 # load any PERSISTED learned answers (taught frontiers)
        from domains import construction_grammar as _cg
        nq = _cg.load_resolved_queries(s)
        if nq:
            installed["resolved_queries (learned)"] = f"ok ({nq})"
    except Exception as e:                               # noqa: BLE001
        installed["resolved_queries (learned)"] = f"FAILED: {e}"
    return s, installed


__all__ = ["reflect", "boot_reflective_substrate"]
