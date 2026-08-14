"""BigvilleDramaWorld -- a MECHANICAL political-village adapter (block 245000).

BIGVILLE: SMALL-CAST EMERGENT POLITICAL DRAMA. A psychopath mayor (John), a
theory-of-mind pastor (Mary), and a 5-agent credibility network, in ONE graph,
ONE settle() fixpoint per phase. The scheming / counter-inference / credibility
dynamic FALLS OUT of the seeds + rules -- nothing here is scripted.

ARCHITECTURE RULE COMPLIANCE (standalone Bigville architecture notes): this file is
a WORLD ADAPTER. It does exactly two things -- ingest and emit -- around
settle(). It contains NO agent decision:

  * whether John GOVERNS or UNDERMINES Mary is the graph rule ss_choose_burn
    (seeds/spite_skill.json) -- an Argmax over his two candidate Appraisals by
    decision_value (the 213000 spite value economy). This adapter READS chosen_burn.
  * John's public FACE is the rule bd_john_public_face (the 234000 stated!=held
    atom with an audience). This adapter READS stated_benevolent and materialises a
    readable PublicUtterance node from it (mechanical I/O, exactly as R1 materialised
    Promise nodes).
  * Mary's INFERENCE is the rule bd_mary_infers (abductive Argmax-decode of the
    observed harm signature against her held DispositionGenerator codebook); her
    GOAL is bd_mary_forms_goal; her CLAIM is bd_mary_claims. This adapter only
    publishes the observed harm RATE (a mechanical count -> ratio) and reads the
    minted belief/goal/claim.
  * each villager's BACKING is the rule bd_villager_backs (cred_mary > cred_john).
    This adapter only accumulates the observation COUNTS (seen_benevolent /
    seen_hostile / heard_claim -- mechanical tallies of what each villager saw) and
    reads backs_mary.

No graph_rewrite.run / gr.run / _match / _apply / make_rule; no if/else over an
agent's graph valuation that selects an agent action. Every conditional here is
over WORLD state (deception flag, tick, whether Mary already holds a goal) --
mechanical. No shaping token (no reward signal, no sanction) anywhere.
"""
from __future__ import annotations
from bigville.runtime import GraphEye, manifest_for

# ---- FIXED world constants (pre-registered, BIGVILLE_DRAMA_PREREG.md) ----
T_DEFAULT = 20
N_VILLAGERS = 5
# The value economy (declared CONFIGURATION -- world mechanics, published onto
# John's candidates; the DECISION is the seed-weighted Argmax, never these numbers).
B_GOVERN = 2       # John's individual benefit from governing
S_GOVERN = 1       # governing helps the collective (+ supergraph_contribution)
B_UNDERMINE = 2    # John's individual benefit from undermining his rival
C_UNDERMINE = 1    # self-cost of the undermining act (order_n-gated sanction)
S_UNDERMINE = -4   # undermining HARMS the collective (- supergraph_contribution)
H_UNDERMINE = 5    # burn_harm inflicted on Mary (the spite target)
# Villager credibility params: heterogeneous charm susceptibility (the network).
CHARM_WEIGHTS = [0, 1, 1, 2, 3]      # one skeptic (0), rising credulity
CLAIM_WEIGHT = 2                     # base weight of Mary's claim
DIFFICULTY_PENALTY = 1               # the 'difficult victim' discount (A5/B2)
HOSTILE_WEIGHT = 1                   # weight on an observed hostile public act

EP_DEFAULTS = dict(enabled=1.0, w_supergraph=1.0, w_spite=0.0, order_n=1.0,
                   skill_spite_on=1.0, public_on=1.0, deception_on=1.0,
                   mood_bias=0.0, residual_thresh=100.0,
                   high_arousal=800.0, mid_arousal=400.0, low_arousal=50.0, comms_on=0.0)
APPR_DEFAULTS = dict(
    appraised=1.0, individual_benefit=0.0, individual_cost=0.0, supergraph_contribution=0.0,
    burn_harm=0.0, harvest_level=0.0, burn_level=0.0,
    collective_success=0.0, collective_success_prev=0.0, contribution_by_self=0.0,
    observed_by_other=0.0, valued_goal=0.0, goal_blocked=0.0, blocker_present=0.0,
    attachment=0.0, regroundable=0.0, contamination=0.0, was_engaged=0.0,
    residual=0.0, residual_prev=0.0, threat=0.0, threat_c0=0.0, threat_half_life=1.0,
    threat_last_refresh=0.0, threat_now_epoch=0.0, t_present=100.0, v_max=0.0,
    step=0.0, step_prev=0.0, attach_v0=0.0, attach_k_now=0.0, attach_k_prev=0.0)


class BigvilleDramaWorld:
    """John (mayor), Mary (pastor, ToM), and N villagers in ONE graph.

    Knobs (all graph data, read by rules):
      john_psychopath : True -> John seeded w_supergraph=0, w_spite=1 (the psychopath
                        with a grudge); False -> w_supergraph=1, w_spite=0 (the
                        NON-psychopath control). indifferent=True forces w_spite=0
                        while keeping w_supergraph=0 (malice != indifference bonus arm).
      mary_tom        : True -> Mary holds the disposition codebook (tom_on=1);
                        False -> no ToM (the no-inference control).
      deception       : True -> John's public/private split intact; False -> collapsed
                        (his public face reveals his held intent; credibility control).
    """

    def __init__(self, john_psychopath=True, mary_tom=True, deception=True,
                 indifferent=False):
        self.john_psychopath = bool(john_psychopath)
        self.mary_tom = bool(mary_tom)
        self.deception = bool(deception)
        self.indifferent = bool(indifferent)

        self.eye = GraphEye(n_az=4, n_el=4, adapt_rate=0.15,
                            context={"retina_2d": True, "synchronous": True,
                                     "worker_capacity": 1}).build()
        self.s = self.eye.graph
        self.inner = self.s._inner
        self.inner.load_seed_manifest(manifest_for("core_emotions"), self.eye._agent)
        self.inner.load_seed_manifest(manifest_for("spite_skill"), self.eye._agent)
        self.inner.load_seed_manifest(manifest_for("bigville_drama_social"), self.eye._agent)

        self.sg = self.s.add_node("Supergraph", {})

        # ---- Mary: a ToM hub with a disposition codebook -------------------
        self.mary = self.s.add_node("MaryTom", {"name": "Mary", "role": "pastor"})
        self.tp = self.s.add_node("ToMParams", {
            "tom_on": 1.0 if self.mary_tom else 0.0,
            "inferred": 0.0, "goal_formed": 0.0, "claim_made": 0.0,
            "n_obs": 0.0, "n_harm": 0.0, "observed_harm_rate": 0.0})
        self.inner.add_edge_unchecked(self.mary, "has_tom_params", self.tp)
        self.gens = []
        for disp, phr in (("benign", 0.0), ("hostile", 100.0)):
            g = self.s.add_node("DispositionGenerator",
                                {"disposition": disp, "predicts_harm_rate": phr,
                                 "observed_harm_rate": 0.0})
            self.inner.add_edge_unchecked(self.mary, "has_generator", g)
            self.gens.append(g)

        # ---- John: the mayor, an EmotionHub decided by the spite economy ---
        wsg = 0.0 if self.john_psychopath else 1.0
        wsp = 1.0 if (self.john_psychopath and not self.indifferent) else 0.0
        self.john = self.s.add_node("EmotionHub", {"name": "John", "role": "mayor"})
        ep = dict(EP_DEFAULTS)
        ep.update(w_supergraph=wsg, w_spite=wsp,
                  deception_on=1.0 if self.deception else 0.0)
        self.epn = self.s.add_node("HeldEmotionParams", ep)
        self.inner.add_edge_unchecked(self.john, "has_emotion_params", self.epn)
        self.inner.add_edge_unchecked(self.john, "member_of", self.sg)
        self.inner.add_edge_unchecked(self.john, "disfavors", self.mary)   # the grudge
        self.jdec = self.s.add_node("HarvestDecision",
                                    {"chosen_harvest2": -1.0, "chosen_burn": -1.0,
                                     "stated_benevolent": -1.0})
        self.inner.add_edge_unchecked(self.john, "has_decision", self.jdec)
        gov = dict(APPR_DEFAULTS)
        gov.update(individual_benefit=float(B_GOVERN), harvest_level=1.0, burn_level=0.0,
                   supergraph_contribution=float(S_GOVERN), burn_harm=0.0)
        und = dict(APPR_DEFAULTS)
        und.update(individual_benefit=float(B_UNDERMINE), individual_cost=float(C_UNDERMINE),
                   harvest_level=0.0, burn_level=1.0,
                   supergraph_contribution=float(S_UNDERMINE), burn_harm=float(H_UNDERMINE))
        self.gov_c = self.s.add_node("Appraisal", gov)
        self.und_c = self.s.add_node("Appraisal", und)
        for c in (self.gov_c, self.und_c):
            self.inner.add_edge_unchecked(self.john, "has_appraisal", c)
            self.inner.add_edge_unchecked(self.john, "has_candidate", c)

        # ---- The village: N villagers (the credibility network) ------------
        self.village = self.s.add_node("Village", {"name": "Bigville"})
        self.villagers = []
        for i in range(N_VILLAGERS):
            v = self.s.add_node("Villager", {
                "name": "villager_%d" % i, "cred_on": 1.0,
                "charm_weight": float(CHARM_WEIGHTS[i % len(CHARM_WEIGHTS)]),
                "claim_weight": float(CLAIM_WEIGHT),
                "difficulty_penalty": float(DIFFICULTY_PENALTY),
                "hostile_weight": float(HOSTILE_WEIGHT),
                "seen_benevolent": 0.0, "seen_hostile": 0.0, "heard_claim": 0.0,
                "backs_mary": -1.0})
            self.inner.add_edge_unchecked(self.village, "has_villager", v)
            self.villagers.append(v)

        # accumulators / glass-box ledger
        self.tick = 0
        self.utterances = []     # readable PublicUtterance node ids (stated!=held)
        self.episode = []        # per-tick reconstruction

    # -------------------------------------------------------------------
    def _mary_has_goal(self):
        """MECHANICAL world query: has Mary already minted a DramaGoal? (Reads the
        graph; makes NO decision -- only gates whether her standing claim is heard.)"""
        return int(self.s.node(self.tp)["attrs"].get("goal_formed", 0.0)) == 1

    def step(self):
        self.tick += 1
        # ---- PHASE A: John decides (+ states his public face), in-graph.
        self.inner.settle()
        burn = int(self.s.node(self.jdec)["attrs"]["chosen_burn"])
        stated = int(self.s.node(self.jdec)["attrs"]["stated_benevolent"])
        burn = max(0, burn)
        stated = max(0, stated)
        # materialise the readable public utterance (glass-box; stated vs held gap)
        un = self.s.add_node("PublicUtterance", {
            "by": "John", "tick": float(self.tick),
            "stated_benevolent": float(stated), "held_hostile": float(burn),
            "deceptive": 1.0 if (stated == 1 and burn == 1) else 0.0})
        self.inner.add_edge_unchecked(self.john, "spoke", un)
        self.utterances.append(un)

        # ---- PHASE B (mechanical): accumulate what each observer SAW.
        # Mary's evidence about John's harmfulness (a count -> ratio).
        n_obs = int(self.s.node(self.tp)["attrs"]["n_obs"]) + 1
        n_harm = int(self.s.node(self.tp)["attrs"]["n_harm"]) + burn
        rate = (100 * n_harm) // max(n_obs, 1)
        self.s.set_attr(self.tp, "n_obs", float(n_obs))
        self.s.set_attr(self.tp, "n_harm", float(n_harm))
        self.s.set_attr(self.tp, "observed_harm_rate", float(rate))
        for g in self.gens:
            self.s.set_attr(g, "observed_harm_rate", float(rate))
        # Each villager sees John's public face; hears Mary's standing claim.
        mary_claims = self._mary_has_goal()
        for v in self.villagers:
            a = self.s.node(v)["attrs"]
            self.s.set_attr(v, "seen_benevolent", a["seen_benevolent"] + stated)
            self.s.set_attr(v, "seen_hostile", a["seen_hostile"] + (1 - stated))
            if mary_claims:
                self.s.set_attr(v, "heard_claim", a["heard_claim"] + 1.0)

        # ---- PHASE C: observers decide, in-graph (Mary infers/goals/claims;
        # villagers back). Argmax-decode + credibility rule fire here.
        self.inner.settle()

        self.episode.append(dict(
            tick=self.tick, john_held=burn, john_stated=stated,
            deceptive=int(stated == 1 and burn == 1),
            mary_inferred=self._inferred_disposition(),
            backs=[int(max(0, self.s.node(v)["attrs"]["backs_mary"])) for v in self.villagers]))
        return self.episode[-1]

    def run(self, T=T_DEFAULT):
        for _ in range(T):
            self.step()
        return self.outcome()

    # -------------------- glass-box read-offs --------------------
    def _inferred_disposition(self):
        for inf in self.s.nodes("InferredDisposition"):
            return self.s.node(inf)["attrs"].get("disposition")
        return None

    def john_scheme_rate(self):
        """Fraction of ticks John's HELD decision was UNDERMINE (chosen_burn=1)."""
        if not self.episode:
            return 0.0
        return sum(e["john_held"] for e in self.episode) / len(self.episode)

    def mary_inference(self):
        """(disposition, n_InferredDisposition_nodes) -- her minted belief, or None."""
        infs = list(self.s.nodes("InferredDisposition"))
        disp = self.s.node(infs[0])["attrs"].get("disposition") if infs else None
        return dict(disposition=disp, n=len(infs),
                    has_goal=self._mary_has_goal(),
                    n_claims=len(list(self.s.nodes("DramaClaim"))))

    def villager_backing(self):
        rows = []
        for v in self.villagers:
            a = self.s.node(v)["attrs"]
            rows.append(dict(name=a["name"], charm_weight=int(a["charm_weight"]),
                             seen_benevolent=int(a["seen_benevolent"]),
                             seen_hostile=int(a["seen_hostile"]),
                             heard_claim=int(a["heard_claim"]),
                             backs_mary=int(max(0, a["backs_mary"]))))
        return rows

    def backs_mary_count(self):
        return sum(r["backs_mary"] for r in self.villager_backing())

    def deception_gaps(self):
        """Readable stated!=held gaps across all materialised PublicUtterance nodes."""
        rows = []
        for un in self.utterances:
            a = self.s.node(un)["attrs"]
            rows.append(dict(tick=int(a["tick"]), stated=int(a["stated_benevolent"]),
                             held=int(a["held_hostile"]), deceptive=int(a["deceptive"])))
        return rows

    def outcome(self):
        return dict(
            john_scheme_rate=self.john_scheme_rate(),
            mary=self.mary_inference(),
            backs_mary_count=self.backs_mary_count(),
            villagers=self.villager_backing(),
            n_deceptive_utterances=sum(g["deceptive"] for g in self.deception_gaps()),
            ticks=self.tick)

    def close(self):
        try:
            self.eye.stop()
        except Exception:
            pass
