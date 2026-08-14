"""BigvilleBondWorld -- bigville RUNG 1/3 (block 277000): THE HELD BOND.

A MECHANICAL world adapter that moves the relationship representation OUT of the
sim (bare, symmetric, static `A -kin/hates-> B` world edges) and INTO the agent
graph as a per-agent, DIRECTED, subjective, updatable `Bond(A->B)` with three
dissociable slots (belief / relational-affect / attraction) + an EARNED
tie_strength/band. The old kin/hates edge is read ONCE as a PRIOR; the held Bond
is the representation, and its update DYNAMICS are seed RULES.

ARCHITECTURE-RULE COMPLIANCE (experiments/gamma-substrate/CLAUDE.md): this is a
WORLD ADAPTER. It holds NO agent decision. It does exactly mechanical I/O:
  * mint agents + the bare kin/hates PRIOR edges (the old world representation);
  * ELABORATE each prior into a directed Bond node (ingest -- minting a node from a
    world edge, exactly as other bigville adapters mint Sources/Promise/owe nodes),
    seeding the slots from the prior CONFIG table (genetic relatedness = a SMALL
    prior only; NO positive feeling forced onto kin);
  * ingest an appraised event (a kindness / gift / loan-default / eviction) as an
    AppraisedEvent node on the relevant directed Bond;
  * ingest third-party gossip as a Gossip node, stamping source_trust by READING
    Bond(A->C) off the graph (a pure read, not a decision);
  * stamp similarity / co-presence (proximity) inputs and arm the one-shot flags;
  * run the Rust run_rules() fixpoint;
  * read the slot values back for the glass-box.
EVERY decision -- how an event / gossip / similarity / proximity moves a bond, the
ToM belief decode, the band assignment -- is a seed RULE (seeds/bigville_bond_update.json).
It invokes no Python rule engine and holds no if/else over an agent's graph valuation
that selects a bond update; conditionals here are over WORLD/config state only. ZERO
new Rust.
"""
from __future__ import annotations
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from domains.photon_eye import GraphEye              # noqa: E402
from substrate.seed_loader import manifest_for       # noqa: E402

# ---- Tunable knobs (declared config -- the DIRECTION is the science, the
# MAGNITUDE is soft; every one is a graph attr the rules read). ----
KNOBS = dict(
    update_gain=1.0,        # the FALSIFIER coupling knob (0 -> bonds frozen at prior)
    pos_weight=1.0,         # reciprocity gain
    neg_weight=3.0,         # negativity bias: bad is stronger than good (CONTESTED magnitude)
    reappraise_factor=0.5,  # betrayal scales standing warm affect wholesale (<1)
    gossip_weight=0.5,      # third-party evidence weight
    sim_weight=1.0,         # homophily gain
    dissim_weight=1.5,      # dissimilarity weighs slightly more (C2 residue)
    exposure_weight=0.2,    # mere-exposure / cohabitation drift
    tie_erode=0.5,          # how much a betrayal erodes the earned tie
)

# Slot defaults for a fresh Bond (all three slots present, all at zero -- NO feeling
# is assigned by construction; feelings are EARNED from experience).
SLOT_DEFAULTS = dict(
    belief_disp_code=0.0, belief_trust=0.0, observed_harm_rate=0.0,
    affect_trust=0.0, affect_gratitude=0.0, affect_resentment=0.0,
    affect_contempt=0.0, affect_affection=0.0, affect_fear=0.0,
    attraction=0.0, romantic=0.0,
    tie_strength=0.0, band_code=0.0, altruism_bias=0.0,
    genetic_kin=0.0, similarity=0.0, enc_delta=0.0,
    obs_armed=0.0, sim_armed=0.0, prox_armed=0.0,
)

# Prior CONFIG per relationship kind. A GENETIC (blood) tie contributes ONLY a
# small altruism bias + a small tie_strength head-start -- NEVER positive affect or
# attraction ("you do not need to like your kin"; kinship is EARNED, genetics is a
# weak overridable prior). A recorded feud seeds negative affect/attraction (the
# feud is a record of past negative experience). A chosen/adopted tie gets NOTHING
# extra -- its band is earned entirely from care/cohabitation.
PRIORS = {
    "blood_kin":   dict(genetic_kin=1.0, altruism_bias=0.3, tie_strength=1.0),
    "chosen":      dict(),                       # earned from history alone
    "acquaintance": dict(tie_strength=0.5),
    "feud":        dict(affect_resentment=2.0, attraction=-2.0, belief_trust=-1.0,
                        tie_strength=1.0),
}

DISP_NAME = {1: "trustworthy", -1: "hostile", 0: "unknown"}


class BigvilleBondWorld:
    """Agents + directed held Bonds in ONE substrate, ONE run_rules() per tick."""

    def __init__(self, freeze=False):
        self.freeze = bool(freeze)
        self.eye = GraphEye(n_az=4, n_el=4, adapt_rate=0.15,
                            context={"retina_2d": True, "synchronous": True,
                                     "worker_capacity": 1}).build()
        self.s = self.eye.substrate
        self.inner = self.s._inner
        self.inner.load_seed_manifest(manifest_for("bigville_bond_update"), self.eye._agent)
        self.agents = {}     # name -> node id
        self.bonds = {}      # (a_name, b_name) -> bond id
        self.bond_gens = {}  # (a_name, b_name) -> [generator ids]

    # ------------------------------------------------------------------ ingest
    def add_agent(self, name, **attrs):
        """Mint a townsperson node (with any homophily attributes)."""
        a = dict(attrs); a["name"] = name
        nid = self.s.add_node("Townsperson", a)
        self.agents[name] = nid
        return nid

    def add_prior_edge(self, a_name, b_name, kind):
        """Add the BARE, OLD-STYLE world relationship edge A -kind-> B (kin/hates/
        ...). This is the legacy representation the Bond ELABORATES from. Mechanical."""
        edge = {"blood_kin": "kin", "feud": "hates"}.get(kind, "knows")
        self.inner.add_edge_unchecked(self.agents[a_name], edge, self.agents[b_name])

    def elaborate(self, a_name, b_name, kind="chosen"):
        """ELABORATE the prior into a directed held Bond(A->B): mint the Bond node,
        seed all three slots from the prior CONFIG (a fresh feeling of zero unless the
        prior is a recorded feud; genetics contributes only a small bias/head-start),
        mint the per-bond ToM DispositionGenerator codebook, and link the grounding
        edges. The DECISIONS (belief decode, band) are rules run on tick()."""
        attrs = dict(SLOT_DEFAULTS)
        attrs.update(KNOBS)
        attrs.update(PRIORS.get(kind, {}))
        attrs["holder_name"] = a_name
        attrs["toward_name"] = b_name
        attrs["prior_kind"] = kind
        if self.freeze:
            attrs["update_gain"] = 0.0
        bond = self.s.add_node("Bond", attrs)
        self.inner.add_edge_unchecked(self.agents[a_name], "holds_bond", bond)
        self.inner.add_edge_unchecked(bond, "toward", self.agents[b_name])
        # per-bond held ToM codebook (generalizes bd_mary_infers' held generators)
        gens = []
        for disp, phr, tl, dc in (("benign", 0.0, 1.0, 1.0), ("hostile", 100.0, -1.0, -1.0)):
            g = self.s.add_node("DispositionGenerator",
                                {"disposition": disp, "predicts_harm_rate": phr,
                                 "trust_level": tl, "disp_code": dc,
                                 "observed_harm_rate": 0.0})
            self.inner.add_edge_unchecked(bond, "has_gen", g)
            gens.append(g)
        self.bonds[(a_name, b_name)] = bond
        self.bond_gens[(a_name, b_name)] = gens
        return bond

    def observe_disposition(self, a_name, b_name, harm_rate):
        """Publish B's observed harm rate onto A->B's ToM codebook + arm the decode
        (mechanical evidence, exactly as the drama adapter publishes observed_harm_rate)."""
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "observed_harm_rate", float(harm_rate))
        for g in self.bond_gens[(a_name, b_name)]:
            self.s.set_attr(g, "observed_harm_rate", float(harm_rate))
        self.s.set_attr(bond, "obs_armed", 1.0)

    def experience_event(self, a_name, b_name, kind, valence, magnitude):
        """Ingest a DIRECT dyadic appraised event by B toward A (a kindness/gift =
        valence>0; a loan-default/eviction = valence<0) onto the directed Bond(A->B).
        The has_event edge is the grounding trace. The UPDATE is the rule."""
        bond = self.bonds[(a_name, b_name)]
        ev = self.s.add_node("AppraisedEvent", {
            "kind": kind, "valence": float(valence),
            "magnitude": float(magnitude), "applied": 0.0})
        self.inner.add_edge_unchecked(bond, "has_event", ev)
        return ev

    def hear_gossip(self, a_name, about_b, from_c, content_valence):
        """Ingest INDIRECT third-party gossip: C tells A about B. source_trust is A's
        trust in C, READ off Bond(A->C) belief_trust (a pure graph read -- no decision;
        0 if A holds no bond about C). The revision is the rule (weighted by source)."""
        bond = self.bonds[(a_name, about_b)]
        src_bond = self.bonds.get((a_name, from_c))
        source_trust = 0.0
        if src_bond is not None:
            source_trust = float(self.s.node(src_bond)["attrs"].get("belief_trust", 0.0))
        g = self.s.add_node("Gossip", {
            "from_c": from_c, "about_b": about_b,
            "content_valence": float(content_valence),
            "source_trust": source_trust,
            "gossip_weight": KNOBS["gossip_weight"], "applied": 0.0})
        self.inner.add_edge_unchecked(bond, "has_gossip", g)
        return g

    def set_similarity(self, a_name, b_name, similarity):
        """Stamp attribute-overlap similarity (signed) on Bond(A->B) + arm the rule."""
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "similarity", float(similarity))
        self.s.set_attr(bond, "sim_armed", 1.0)

    def cohabit(self, a_name, b_name, encounters):
        """Stamp accumulated co-presence / cohabitation (mere-exposure) on Bond(A->B)
        + arm the proximity rule. This is how a chosen/adopted tie EARNS its band."""
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "enc_delta", float(encounters))
        self.s.set_attr(bond, "prox_armed", 1.0)

    # -------------------------------------------------------------------- tick
    def tick(self):
        """Run the Rust rule fixpoint -- the bonds update themselves."""
        self.inner.run_rules()

    # -------------------------------------------------------------------- read
    def bond_id(self, a_name, b_name):
        return self.bonds[(a_name, b_name)]

    def slots(self, a_name, b_name):
        """Glass-box read-off of a directed Bond's three slots + structure."""
        at = self.s.node(self.bonds[(a_name, b_name)])["attrs"]
        return dict(
            holder=a_name, toward=b_name, prior=at.get("prior_kind"),
            update_gain=at.get("update_gain"),
            # belief slot
            belief_trust=round(float(at.get("belief_trust", 0.0)), 4),
            belief_disposition=DISP_NAME.get(int(at.get("belief_disp_code", 0.0)), "unknown"),
            # relational-affect slot (six signed emotions)
            affect_trust=round(float(at.get("affect_trust", 0.0)), 4),
            affect_gratitude=round(float(at.get("affect_gratitude", 0.0)), 4),
            affect_resentment=round(float(at.get("affect_resentment", 0.0)), 4),
            affect_contempt=round(float(at.get("affect_contempt", 0.0)), 4),
            affect_affection=round(float(at.get("affect_affection", 0.0)), 4),
            affect_fear=round(float(at.get("affect_fear", 0.0)), 4),
            # attraction slot
            attraction=round(float(at.get("attraction", 0.0)), 4),
            romantic=round(float(at.get("romantic", 0.0)), 4),
            # structure
            tie_strength=round(float(at.get("tie_strength", 0.0)), 4),
            band=self.band_name(int(round(float(at.get("band_code", 0.0))))),
            band_code=int(round(float(at.get("band_code", 0.0)))),
            altruism_bias=round(float(at.get("altruism_bias", 0.0)), 4),
        )

    @staticmethod
    def band_name(code):
        return {5: "family", 4: "intimate", 3: "friend", 2: "acquaintance",
                1: "consequential_stranger", 0: "stranger", -1: "rival"}.get(code, "?")

    def close(self):
        try:
            self.eye.stop()
        except Exception:
            pass
