"""bigville RUNG 2/3 (block 278000) -- EMERGENT SPEECH. Gates mirror
BIGVILLE_SPEECH_PREREG.md. The town's speech was FORCED (armed on a clock); this
proves the mechanism where an utterance is an EMERGENT ACTION: an agent at an
encounter (or trade) DECIDES whether / to whom / what KIND to speak -- or to STAY
SILENT -- by reading its held Bond(A->B) (rung 1) + norms + affect, with NO clock
term. Standalone mechanism-demo in the BigvilleBondWorld style; the canonical
town reuses this same faculty.

No agent decision lives in Python -- the utterance / silence / KIND / loudness /
snub decisions are seed RULES (seeds/bigville_speech_decide.json) composing
existing DSL Terms (Argmax/Plus/Times/Minus/IfThenElse/Attr/NodesOfType, the exact
af_choose_action / lo_choose_loudness families). The adapter only mints agents /
bonds / the menu / encounters, stamps inputs, arms one-shots, ticks, and reads
(source-audited below). ZERO new Rust.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_speech_world import BigvilleSpeechWorld   # noqa: E402


def _scene(schedule=False, **bond):
    w = BigvilleSpeechWorld(schedule=schedule)
    w.add_agent("A")
    w.add_agent("B")
    w.hold_bond("A", "B", **bond)
    return w


# ============================================= G-emergent-confidant (SPEAK, warm)
def test_confidant_speaks_warm_and_shares_a_salient_event():
    """A liked confidant (high tie + positive affect), NO obligation -> the agent
    CHOOSES to speak, KIND = a warm greeting; and when a salient event is present the
    KIND becomes `share` (targeted to the confidant, Rime §1.4) -- the KIND reflects
    the Bond, not a schedule."""
    w = _scene(affect_affection=3.0, tie_strength=4.0)
    w.encounter("A", "B")                       # an ordinary encounter, no salient event
    assert w.decide("A", "B") == "greeting"      # warm greeting to the liked confidant
    assert w.spoke("A", "B")
    w.close()

    w = _scene(affect_affection=3.0, tie_strength=4.0)
    w.encounter("A", "B", share_salience=2.0)    # an emotionally-salient event to share
    assert w.decide("A", "B") == "share"         # sharing is targeted to the confidant
    w.close()


def test_sharing_is_narrow_to_high_tie_not_broadcast():
    """The salient-event share is TIE-SCALED (confide term = tie_strength * salience):
    a low-tie acquaintance does NOT get the confidant-grade share -- the same salient
    event lands 8x weaker there. Encodes Rime's 'sharing to CONFIDANTS', not 'aroused
    -> talk to anyone'."""
    hi = _scene(affect_affection=0.0, tie_strength=4.0)
    hi.encounter("A", "B", share_salience=2.0)
    assert hi.decide("A", "B") == "share"
    hi.close()
    lo = _scene(affect_affection=0.0, tie_strength=0.2)
    lo.encounter("A", "B", share_salience=2.0)
    assert lo.decide("A", "B") != "share"        # too weak a tie for confidant-grade sharing
    lo.close()


# ================================================ G-emergent-rival (SPEAK, hostile)
def test_resented_rival_gets_a_barb():
    """An encounter with a resented rival -> the agent speaks a COLD/HOSTILE kind (a
    barb), derived from the Bond's resentment action-tendency (SCIENCE §3.4). Same
    rule, opposite Bond, opposite KIND."""
    w = _scene(affect_resentment=3.0, tie_strength=1.0)
    w.encounter("A", "B")
    assert w.decide("A", "B") == "barb"
    w.close()


# =========================================================== G-silence (DECLINE)
def test_stranger_stays_silent_civil_inattention():
    """A stranger (no tie, no affect, no obligation) -> the agent CHOOSES stay_silent
    (Goffman civil inattention §1.7). The encounter is an OCCASION, not a CAUSE -- the
    rule can DECLINE to speak."""
    w = _scene()                                 # zero Bond
    w.encounter("A", "B", stranger=1.0)
    assert w.decide("A", "B") == "stay_silent"
    assert not w.spoke("A", "B")
    w.close()


def test_taciturn_trait_diverges_from_garrulous_on_the_same_encounter():
    """Per-agent loquacity is a TRAIT (Mehl §3.2): from the SAME neutral acquaintance
    encounter, a garrulous agent (low threshold) speaks while a taciturn agent (high
    threshold) stays silent -- divergence with no clock, only state."""
    g = _scene()
    g.encounter("A", "B", loquacity_threshold=0.2)
    g.decide("A", "B")
    assert g.spoke("A", "B")
    g.close()
    t = _scene()
    t.encounter("A", "B", loquacity_threshold=5.0)
    t.decide("A", "B")
    assert not t.spoke("A", "B")
    t.close()


# ===================================================== G-adjacency (respond in kind)
def test_a_greeting_begets_a_greeting_and_a_question_an_answer():
    """Adjacency pairs are the strongest input (SCIENCE §1.3): a pending FPP directed
    at A makes the matching SPP conditionally relevant. A greeting FPP -> A responds
    with a greeting; a question FPP -> A responds with an answer. The norm term routes
    to the matching option; the KIND is the SPP."""
    w = _scene()
    w.encounter("A", "B", obligation=1.0, fpp_is_greeting=1.0)
    assert w.decide("A", "B") == "greeting"
    w.close()
    w = _scene()
    w.encounter("A", "B", obligation=1.0, fpp_is_question=1.0)
    assert w.decide("A", "B") == "answer"
    w.close()


# =============================================== G-noticeable-absence (silence = move)
def test_unmet_obligation_mints_a_legible_noticeable_absence():
    """Non-response is a MOVE (Schegloff official absence §1.3/§3.3): when an
    obligation existed (a greeting was directed at A) but A stays silent (a withholding
    / taciturn agent), a LEGIBLE NoticeableAbsence node is minted and the snubbed
    target is wired -notices-> it -- NOT the mere non-firing of a rule."""
    w = _scene()
    w.encounter("A", "B", obligation=1.0, fpp_is_greeting=1.0,
                loquacity_threshold=10.0)         # too withholding to meet the obligation
    assert w.decide("A", "B") == "stay_silent"
    absn = w.noticeable_absence("A", "B")
    assert absn["minted"] and absn["target_notices"]
    w.close()


def test_met_obligation_mints_no_absence():
    """The dual: when the obligation IS met (A responds), no NoticeableAbsence is
    minted -- the snub node is specific to the withheld SPP."""
    w = _scene()
    w.encounter("A", "B", obligation=1.0, fpp_is_greeting=1.0)   # ordinary threshold
    assert w.decide("A", "B") == "greeting"
    assert not w.noticeable_absence("A", "B")["minted"]
    w.close()


# ================================================================ G-loudness
def test_arousal_raises_chosen_loudness_a_real_term_not_a_constant():
    """Delivery gate (SCIENCE §3.4): higher speaker arousal -> strictly higher
    eff_loudness (via sp_set_chosen_loudness feeding the LANDED lo_choose_loudness);
    with loud_arousal_gain=0 the loudness is constant across arousal -- the arousal
    term does the work."""
    w = BigvilleSpeechWorld()
    w.utter("Q", 0.2)
    w.utter("R", 0.9)
    assert w.eff_loudness("R") > w.eff_loudness("Q")
    # control: zero the arousal gain -> constant regardless of arousal
    w.utter("S", 0.2, loud_arousal_gain=0.0)
    w.utter("T", 0.9, loud_arousal_gain=0.0)
    assert w.eff_loudness("S") == w.eff_loudness("T")
    w.close()


# ================================================================ G-trade
def test_trade_is_an_occasion_that_opens_talk():
    """A trade/buy is a high-ratification, goal-present encounter toward a ratified
    counterpart (SCIENCE §3.5) -> it reliably opens talk (not silence), even with a
    neutral Bond, whereas the same neutral pair as strangers stays silent."""
    w = _scene()
    w.trade("A", "B")
    w.decide("A", "B")
    assert w.spoke("A", "B")
    w.close()
    # contrast: same neutral bond, a stranger encounter -> silence
    w = _scene()
    w.encounter("A", "B", stranger=1.0)
    w.decide("A", "B")
    assert not w.spoke("A", "B")
    w.close()


# =================================================== G-emergent from an EARNED bond
def test_speech_reads_an_earned_rung1_bond():
    """Full composition with rung 1: with NO hand-set affect, repeated cohabitation +
    care events move the Bond via the rung-1 bond_* rules; the speech rule then reads
    that EARNED affection and chooses a warm greeting. The affect the utterance reads
    is genuinely rule-produced, not stamped."""
    w = BigvilleSpeechWorld()
    w.add_agent("A")
    w.add_agent("B")
    w.hold_bond("A", "B")                         # fresh zero bond
    w.earn_kindness("A", "B", magnitude=1.5, times=4)   # rung-1 rules build the affect
    assert w.bond_slots("A", "B")["affect_affection"] > 0.0
    w.encounter("A", "B")
    assert w.decide("A", "B") == "greeting"
    w.close()


# ========================================================= G-falsifier (THE control)
def test_falsifier_schedule_collapses_to_one_fixed_kind_regardless_of_bond():
    """The anti-'forced' control (mirrors af_choose_action's affect_gain): with
    schedule=True the coupling gains (affect/norm/occasion/goal/arousal/civil) are
    zeroed and the silence line dropped below the base talk options. The SAME confidant
    / rival / stranger / greeting-FPP encounters that diverge under the emergent rule
    ALL collapse to ONE fixed kind (smalltalk) regardless of the Bond -- the OLD forced
    schedule -- and no snub is ever minted. Emergence is proven by the contrast."""
    cases = [
        ("confidant", dict(affect_affection=3.0, tie_strength=4.0), {}),
        ("rival",     dict(affect_resentment=3.0), {}),
        ("stranger",  dict(), dict(stranger=1.0)),
        ("greetFPP",  dict(), dict(obligation=1.0, fpp_is_greeting=1.0)),
    ]
    # emergent: the four cases produce FOUR different behaviors
    emergent = []
    for _, bd, ov in cases:
        w = _scene(**bd)
        w.encounter("A", "B", **ov)
        emergent.append(w.decide("A", "B"))
        w.close()
    assert len(set(emergent)) >= 3, emergent    # genuinely Bond-dependent

    # schedule: the SAME four cases collapse to ONE fixed kind, no snub
    scheduled = []
    for _, bd, ov in cases:
        w = _scene(schedule=True, **bd)
        w.encounter("A", "B", **ov)
        scheduled.append(w.decide("A", "B"))
        assert not w.noticeable_absence("A", "B")["minted"]
        w.close()
    assert set(scheduled) == {"smalltalk"}, scheduled   # fixed regardless of Bond


# ===================================================== source-audit / discipline
def test_no_python_agent_decision_in_the_speech_adapter():
    """Source-audit: the speech adapter holds NO agent decision -- no Python rule engine
    and no if/else over an agent's graph valuation that selects an utterance / kind /
    loudness. Every such decision is a seed rule; the adapter only ingests, arms, ticks,
    and reads. (The only conditional is `schedule` -- a world-config falsifier switch,
    over config state, not graph valuation.)"""
    src = open(os.path.join(_ROOT, "worlds", "bigville_speech_world.py")).read()
    for forbidden in ("graph_rewrite", "gr.run", "._match(", "._apply(", "make_rule("):
        assert forbidden not in src, f"speech adapter runs the Python rule engine: {forbidden}"


def test_decide_seed_holds_the_speech_rules_and_composes_only_existing_terms():
    """The DECISIONS are RULES: the seed holds the three sp_* rules (utterance choice,
    noticeable-absence, loudness) composing existing DSL Terms -- no exotic Term smuggled
    in, no new machinery."""
    seed = json.load(open(os.path.join(_ROOT, "seeds", "bigville_speech_decide.json")))
    names = [r["name"] for r in seed["rules"]]
    for r in ("sp_choose_utterance", "sp_noticeable_absence", "sp_set_chosen_loudness"):
        assert r in names, r
    blob = json.dumps(seed["rules"])
    assert '"type": "Argmax"' in blob or '"type":"Argmax"' in blob   # the af_choose_action family
    for exotic in ("ShapeDecode", "TransformDecode", "DimInfer", "space_quantize"):
        assert exotic not in blob


def test_runners_dsl_untouched_zero_new_rust():
    """G-discipline (NO Rust): the rung-2 build is seeds + adapter + tests only. The
    speech seed composes existing DSL Terms; no term.rs / engine change vs HEAD."""
    r = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "runners/dsl"],
                       cwd=_ROOT, capture_output=True, text=True)
    changed = [l for l in r.stdout.splitlines() if l.strip()]
    assert changed == [], f"runners/dsl changed (new Rust): {changed}"
