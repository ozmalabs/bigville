"""BigvilleSpeechWorld -- bigville RUNG 2/3 (block 278000): EMERGENT SPEECH.

The town's speech was FORCED (armed on a clock). This adapter proves the
mechanism where an utterance is an EMERGENT ACTION: an agent, at an ENCOUNTER
(or a trade), DECIDES whether / to whom / what KIND to speak -- or to STAY
SILENT -- by reading its held `Bond(A->B)` (rung 1, `BigvilleBondWorld`) +
conversational norms + affect, with **NO clock term**. It is a STANDALONE
mechanism-demo in the exact style of `BigvilleBondWorld`: rung 1 proved the Bond
in isolation; this proves speech-initiation in isolation READING a Bond.
The canonical ``BigvilleWorld`` now reuses this same seed-driven mechanism for
resident encounters; this module remains the small standalone proof harness.

ARCHITECTURE-RULE COMPLIANCE (experiments/gamma-substrate/CLAUDE.md): a WORLD
ADAPTER. It holds NO agent decision. Mechanical I/O only:
  * compose `BigvilleBondWorld` to mint agents + held directed Bonds (the affect
    is either stamped as an input or EARNED through rung-1 events, both are the
    Bond the speech rule reads);
  * mint the GLOBAL SpeechOption menu ONCE (a world fact -- the OPTIONS + their
    parameters, exactly as `BigvilleAffectWorld` mints the Action menu; the CHOICE
    is the rule `sp_choose_utterance`, not this table);
  * mint an Encounter node wired `-at_bond-> Bond(A->B)`, stamping the situation
    inputs (occasion / obligation / pending-FPP kind / share-salience / goal /
    arousal / stranger / face_weight) + the speaker's loquacity_threshold, and the
    coupling gains (the falsifier: zeroed under `schedule=True`);
  * arm the one-shot, run the Rust `run_rules()` fixpoint, read the chosen kind /
    the minted NoticeableAbsence / eff_loudness back for the glass-box.
EVERY decision -- which utterance / silence, which KIND, which loudness, whether a
snub is legible -- is a seed RULE (seeds/bigville_speech_decide.json), composing
existing DSL Terms (Argmax/Plus/Times/Minus/IfThenElse/Attr/NodesOfType, the exact
`af_choose_action` / `lo_choose_loudness` families). It invokes no Python rule
engine and holds no if/else over an agent's graph valuation that selects an
utterance; conditionals here are over WORLD/config state only. ZERO new Rust.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from substrate.seed_loader import manifest_for            # noqa: E402
from worlds.bigville_bond_world import BigvilleBondWorld   # noqa: E402

# ---- The SpeechOption MENU (a world fact -- the OPTIONS + their parameters,
# exactly like BigvilleAffectWorld's ACTION_MENU). The CHOICE is the rule.
#   kind_code       : the KIND read back  (0..6)
#   is_silence      : the stay-silent option (its value is the loquacity threshold)
#   talk_aff        : 1 for talk options (civil-inattention suppresses these; 0 for silence)
#   *_aff           : affinity of this option to each Bond-affect / adjacency channel
#   face_cost       : Brown&Levinson imposition weight (scaled by the target's face_weight)
#   base_value      : baseline appeal (the schedule-collapse fallback ranking)
SPEECH_MENU = [
    dict(name="stay_silent", kind_code=0.0, is_silence=1.0, talk_aff=0.0, base_value=0.0),
    dict(name="greeting",    kind_code=1.0, is_silence=0.0, talk_aff=1.0, base_value=0.3,
         warm_aff=1.0, greet_answer_aff=1.0, face_cost=0.3),
    dict(name="smalltalk",   kind_code=2.0, is_silence=0.0, talk_aff=1.0, base_value=0.5,
         warm_aff=0.3, face_cost=0.2),
    dict(name="barb",        kind_code=3.0, is_silence=0.0, talk_aff=1.0, base_value=0.2,
         hostile_aff=1.0, face_cost=2.0),
    dict(name="hedged",      kind_code=4.0, is_silence=0.0, talk_aff=1.0, base_value=0.2,
         hedge_aff=1.0, face_cost=0.5),
    dict(name="share",       kind_code=5.0, is_silence=0.0, talk_aff=1.0, base_value=0.2,
         confide_aff=1.0, face_cost=1.0),
    dict(name="answer",      kind_code=6.0, is_silence=0.0, talk_aff=1.0, base_value=0.3,
         q_answer_aff=1.0, face_cost=0.3),
]
# every affinity key an option may omit -> defaulted to 0 so a rule never reads a
# missing key (the seed also wraps each Attr in Plus[Attr,0], belt-and-braces).
_OPT_KEYS = ("kind_code", "is_silence", "talk_aff", "base_value", "warm_aff",
             "hostile_aff", "hedge_aff", "confide_aff", "greet_answer_aff",
             "q_answer_aff", "goal_aff", "face_cost")
KIND_LABEL = {0: "stay_silent", 1: "greeting", 2: "smalltalk", 3: "barb",
              4: "hedged", 5: "share", 6: "answer"}

# ---- Encounter default knobs. The DIRECTION is the science (SCIENCE_DOC §2/§3);
# the MAGNITUDE is soft; every one is a graph attr the rule reads. ----
ENCOUNTER_DEFAULTS = dict(
    # coupling gains (the FALSIFIER set -- zeroed under schedule=True)
    occasion_gain=1.0, norm_gain=3.0, affect_gain=1.0, goal_gain=1.0,
    arousal_gain=1.0, civil_gain=1.0,
    # situation inputs
    occasion=1.0,            # an encounter IS the occasion (never sufficient alone)
    obligation=0.0,          # a pending FPP addressed to me (conditional relevance)
    fpp_is_greeting=0.0, fpp_is_question=0.0,
    share_salience=0.0,      # an emotionally-salient event to share (Rime)
    goal_pressure=0.0,       # an active need this act would serve
    speaker_arousal=0.0,     # raises loudness + lowers the hostile threshold
    stranger=0.0,            # non-ratified other -> civil-inattention suppressor
    face_weight=0.3,         # D+P proxy the face_cost is scaled by
    loquacity_threshold=1.0, # per-agent trait (the stay-silent option's value)
    decide_armed=0.0, chosen_speech_code=-1.0, absence_minted=0.0,
)


class BigvilleSpeechWorld:
    """Agents + held directed Bonds + the emergent-speech decision in ONE
    substrate, ONE run_rules() per tick. Composes BigvilleBondWorld (rung 1)."""

    def __init__(self, schedule=False):
        # schedule=True is the FALSIFIER control: zero the coupling gains so the
        # decision collapses to a fixed kind regardless of the Bond (the OLD forced
        # behavior). Default False = emergent.
        self.schedule = bool(schedule)
        self.bw = BigvilleBondWorld()
        self.s = self.bw.s
        self.inner = self.bw.inner
        # load the rung-2 speech rules + COMPOSE the landed loudness rule
        self.inner.load_seed_manifest(manifest_for("bigville_speech_decide"),
                                      self.bw.eye._agent)
        self.inner.load_seed_manifest(manifest_for("bigville_loud_comm"),
                                      self.bw.eye._agent)
        self.options = {}     # name -> SpeechOption nid (the shared global menu)
        self.encs = {}        # (speaker,target) -> Encounter nid
        self.utts = {}        # name -> Utterance nid
        self._mint_menu()

    # ================================================================ INGEST
    def _mint_menu(self):
        """Mint the shared SpeechOption menu ONCE (a world fact). Mechanical graph
        data -- the parameters are the menu, the CHOICE is sp_choose_utterance."""
        for o in SPEECH_MENU:
            attrs = {k: 0.0 for k in _OPT_KEYS}
            attrs.update(o)
            nid = self.s.add_node("SpeechOption", attrs)
            self.options[o["name"]] = nid

    # ---- bonds (delegate to rung 1; the affect is the Bond the speech rule reads)
    def add_agent(self, name, **attrs):
        return self.bw.add_agent(name, **attrs)

    def hold_bond(self, speaker, target, prior="chosen", **slots):
        """Give SPEAKER a held directed Bond toward TARGET. The affect slots are
        stamped as INPUTS here (the speech rule reads a real held Bond); for an
        EARNED bond drive rung-1 events via `earn_*` instead. Mechanical write."""
        for nm in (speaker, target):
            if nm not in self.bw.agents:
                self.bw.add_agent(nm)
        bond = self.bw.elaborate(speaker, target, prior)
        for k, v in slots.items():
            self.s.set_attr(bond, k, float(v))
        return bond

    def earn_kindness(self, speaker, target, magnitude=1.5, times=1):
        """Build a POSITIVE bond the RUNG-1 way: repeated cohabitation + care events
        move affection/tie via the bond_* rules (no hand-set affect). Mechanical
        delivery; the UPDATE is rung 1's rule."""
        for _ in range(times):
            self.bw.cohabit(speaker, target, 6.0)
            self.bw.experience_event(speaker, target, "care", +1.0, magnitude)
            self.bw.tick()

    def encounter(self, speaker, target, **overrides):
        """Mint an Encounter of SPEAKER with TARGET, wired -at_bond-> Bond(speaker,
        target), stamping the situation inputs + coupling gains. Under schedule=True
        the coupling gains are zeroed and the silence line dropped below the base
        talk options (the falsifier). Mechanical -- the DECISION is the rule."""
        bond = self.bw.bonds[(speaker, target)]
        attrs = dict(ENCOUNTER_DEFAULTS)
        attrs.update(overrides)
        if self.schedule:
            # FALSIFIER: remove the whole affect/norm/occasion/goal/arousal/civil
            # layer, and force a talk option (fixed schedule -- speaks the same
            # regardless of Bond). No number here is a decision; it is the control.
            for g in ("occasion_gain", "norm_gain", "affect_gain", "goal_gain",
                      "arousal_gain", "civil_gain"):
                attrs[g] = 0.0
            attrs["loquacity_threshold"] = -1.0
        enc = self.s.add_node("Encounter", attrs)
        self.inner.add_edge_unchecked(enc, "at_bond", bond)
        self.encs[(speaker, target)] = enc
        return enc

    def trade(self, buyer, shopkeeper, **overrides):
        """A TRADE/buy encounter (SCIENCE §3.5): high-ratification, goal-present,
        toward a ratified counterpart -> reliably opens talk. Sugar over encounter."""
        o = dict(goal_pressure=1.0, stranger=0.0)
        o.update(overrides)
        return self.encounter(buyer, shopkeeper, **o)

    # -------------------------------------------------------------------- tick
    def decide(self, speaker, target):
        """Arm the choice; sp_choose_utterance picks chosen_speech_code = the value
        Argmax over the SpeechOption menu (the Bond, norms, affect, occasion are
        TERMS in that Argmax; NO clock term). The rule decides."""
        enc = self.encs[(speaker, target)]
        self.s.set_attr(enc, "decide_armed", 1.0)
        self.inner.run_rules()
        return self.chosen_kind(speaker, target)

    def utter(self, name, arousal, *, base_loudness=1.0, loud_arousal_gain=0.6,
              max_loudness=100.0):
        """Mint an Utterance by NAME with a given arousal; sp_set_chosen_loudness
        sets chosen_loudness = base + loud_arousal_gain*arousal, then the LANDED
        lo_choose_loudness turns it into eff_loudness (the delivery gate)."""
        if name not in self.bw.agents:
            self.bw.add_agent(name)
        u = self.s.add_node("Utterance", dict(
            speaker_arousal=float(arousal), base_loudness=float(base_loudness),
            loud_arousal_gain=float(loud_arousal_gain), max_loudness=float(max_loudness),
            loudness_on=1.0, choice_on=1.0, loud_armed=1.0,
            chosen_loudness=0.0, eff_loudness=0.0))
        self.inner.add_edge_unchecked(u, "spoken_by", self.bw.agents[name])
        self.utts[name] = u
        self.inner.run_rules()
        return u

    def tick(self):
        self.inner.run_rules()

    # -------------------------------------------------------------------- read
    def chosen_code(self, speaker, target):
        at = self.s.node(self.encs[(speaker, target)])["attrs"]
        return int(round(float(at.get("chosen_speech_code", -1.0))))

    def chosen_kind(self, speaker, target):
        return KIND_LABEL.get(self.chosen_code(speaker, target), "undecided")

    def spoke(self, speaker, target):
        """True iff a talk option (not stay_silent, not undecided) was chosen."""
        return self.chosen_code(speaker, target) not in (-1, 0)

    def noticeable_absence(self, speaker, target):
        """The legible snub: (minted?, target-notices?) read off the graph."""
        enc = self.encs[(speaker, target)]
        absn = self.inner.neighbours(enc, "has_absence")
        if not absn:
            return dict(minted=False, target_notices=False)
        a = absn[0]
        tgt = self.bw.agents[target]
        notices = self.inner.has_edge(tgt, "notices", a)
        return dict(minted=True, target_notices=notices)

    def eff_loudness(self, name):
        return round(float(self.s.node(self.utts[name])["attrs"].get("eff_loudness", 0.0)), 4)

    def bond_slots(self, speaker, target):
        return self.bw.slots(speaker, target)

    def close(self):
        self.bw.close()
