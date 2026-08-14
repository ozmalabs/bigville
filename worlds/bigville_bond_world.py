"""Dependency-free held relationship graph for Bigville."""
from __future__ import annotations

from bigville.runtime import BigvilleGraph, GraphEye

KNOBS = dict(update_gain=1.0, pos_weight=1.0, neg_weight=3.0,
             reappraise_factor=0.5, gossip_weight=0.5, sim_weight=1.0,
             dissim_weight=1.5, exposure_weight=0.2, tie_erode=0.5)

SLOT_DEFAULTS = dict(
    belief_disp_code=0.0, belief_trust=0.0, observed_harm_rate=0.0,
    affect_trust=0.0, affect_gratitude=0.0, affect_resentment=0.0,
    affect_contempt=0.0, affect_affection=0.0, affect_fear=0.0,
    attraction=0.0, romantic=0.0, tie_strength=0.0, band_code=0.0,
    altruism_bias=0.0, genetic_kin=0.0, similarity=0.0, enc_delta=0.0,
    obs_armed=0.0, sim_armed=0.0, prox_armed=0.0,
)

PRIORS = {
    "blood_kin": dict(genetic_kin=1.0, altruism_bias=0.3, tie_strength=1.0),
    "chosen": {}, "acquaintance": dict(tie_strength=0.5),
    "feud": dict(affect_resentment=2.0, attraction=-2.0,
                  belief_trust=-1.0, tie_strength=1.0),
}
DISP_NAME = {1: "trustworthy", -1: "hostile", 0: "unknown"}


class BigvilleBondWorld:
    """A held directed Bond model backed by ordinary Bigville graph data."""

    def __init__(self, freeze=False):
        self.freeze = bool(freeze)
        self.eye = GraphEye()
        self.s = self.eye.graph
        self.inner = self.s
        self.agents, self.bonds, self.events = {}, {}, {}
        self.gossips, self.bond_gens = {}, {}

    def add_agent(self, name, **attrs):
        node = self.s.add_node("Townsperson", {"name": str(name), **attrs})
        self.agents[str(name)] = node
        return node

    def add_prior_edge(self, a_name, b_name, kind):
        self.inner.add_edge_unchecked(self.agents[a_name],
                                      {"blood_kin": "kin", "feud": "hates"}.get(kind, "knows"),
                                      self.agents[b_name])

    def elaborate(self, a_name, b_name, kind="chosen"):
        attrs = dict(SLOT_DEFAULTS)
        attrs.update(KNOBS)
        attrs.update(PRIORS.get(kind, {}))
        attrs.update({"holder_name": a_name, "toward_name": b_name,
                      "prior_kind": kind})
        bond = self.s.add_node("Bond", attrs)
        self.inner.add_edge_unchecked(self.agents[a_name], "holds_bond", bond)
        self.inner.add_edge_unchecked(bond, "toward", self.agents[b_name])
        self.bonds[(a_name, b_name)] = bond
        self.bond_gens[(a_name, b_name)] = []
        return bond

    def observe_disposition(self, a_name, b_name, harm_rate):
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "observed_harm_rate", float(harm_rate))
        self.s.set_attr(bond, "belief_disp_code", 1.0 if harm_rate < 50 else -1.0)

    def experience_event(self, a_name, b_name, kind, valence, magnitude):
        bond = self.bonds[(a_name, b_name)]
        event = self.s.add_node("AppraisedEvent", {
            "kind": kind, "valence": float(valence), "magnitude": float(magnitude),
            "applied": 0.0})
        self.inner.add_edge_unchecked(bond, "has_event", event)
        self.events.setdefault((a_name, b_name), []).append(event)
        return event

    def hear_gossip(self, a_name, about_b, from_c, content_valence):
        bond = self.bonds[(a_name, about_b)]
        source = self.bonds.get((a_name, from_c))
        trust = float(self.s.node(source)["attrs"].get("belief_trust", 0.0)) if source else 0.0
        gossip = self.s.add_node("Gossip", {"from_c": from_c, "about_b": about_b,
                                             "content_valence": float(content_valence),
                                             "source_trust": trust, "applied": 0.0})
        self.inner.add_edge_unchecked(bond, "has_gossip", gossip)
        self.gossips.setdefault((a_name, about_b), []).append(gossip)
        return gossip

    def set_similarity(self, a_name, b_name, similarity):
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "similarity", float(similarity))
        self.s.set_attr(bond, "sim_armed", 1.0)

    def cohabit(self, a_name, b_name, encounters):
        bond = self.bonds[(a_name, b_name)]
        self.s.set_attr(bond, "enc_delta", float(encounters))
        self.s.set_attr(bond, "prox_armed", 1.0)

    def tick(self):
        if self.freeze:
            return
        for key, bond in self.bonds.items():
            attrs = self.s.node(bond)["attrs"]
            enc = float(attrs.get("enc_delta", 0.0))
            if enc and attrs.get("prox_armed", 0.0):
                attrs["tie_strength"] = max(0.0, float(attrs.get("tie_strength", 0.0))
                                             + enc * KNOBS["exposure_weight"])
                attrs["enc_delta"] = 0.0
                attrs["prox_armed"] = 0.0
            sim = float(attrs.get("similarity", 0.0))
            if attrs.get("sim_armed", 0.0):
                attrs["affect_affection"] += max(0.0, sim) * KNOBS["sim_weight"]
                attrs["affect_resentment"] += max(0.0, -sim) * KNOBS["dissim_weight"]
                attrs["sim_armed"] = 0.0
            for event in self.events.get(key, ()):
                ea = self.s.node(event)["attrs"]
                if ea.get("applied", 0.0):
                    continue
                delta = float(ea.get("valence", 0.0)) * float(ea.get("magnitude", 0.0))
                if delta >= 0:
                    attrs["affect_affection"] += delta * KNOBS["pos_weight"]
                    attrs["affect_gratitude"] += delta
                    attrs["belief_trust"] += delta
                else:
                    attrs["affect_resentment"] += -delta * KNOBS["neg_weight"]
                    attrs["affect_contempt"] += -delta
                    attrs["belief_trust"] += delta
                    attrs["tie_strength"] = max(0.0, attrs.get("tie_strength", 0.0) + delta * KNOBS["tie_erode"])
                ea["applied"] = 1.0
            for gossip in self.gossips.get(key, ()):
                ga = self.s.node(gossip)["attrs"]
                if ga.get("applied", 0.0):
                    continue
                weight = KNOBS["gossip_weight"] * float(ga.get("source_trust", 0.0))
                attrs["belief_trust"] += float(ga.get("content_valence", 0.0)) * weight
                ga["applied"] = 1.0
            attrs["band_code"] = self._band_code(attrs)

    @staticmethod
    def _band_code(attrs):
        tie = float(attrs.get("tie_strength", 0.0))
        resentment = float(attrs.get("affect_resentment", 0.0))
        if resentment >= 2.0: return -1.0
        if tie >= 5.0: return 5.0
        if tie >= 3.0: return 4.0
        if tie >= 1.5: return 3.0
        if tie >= 0.5: return 2.0
        if tie > 0.0: return 1.0
        return 0.0

    def bond_id(self, a_name, b_name):
        return self.bonds[(a_name, b_name)]

    def slots(self, a_name, b_name):
        at = self.s.node(self.bonds[(a_name, b_name)])["attrs"]
        code = int(round(float(at.get("band_code", self._band_code(at)))))
        return dict(holder=a_name, toward=b_name, prior=at.get("prior_kind"),
                    update_gain=at.get("update_gain"),
                    belief_trust=round(float(at.get("belief_trust", 0.0)), 4),
                    belief_disposition=DISP_NAME.get(int(at.get("belief_disp_code", 0)), "unknown"),
                    affect_trust=round(float(at.get("affect_trust", 0.0)), 4),
                    affect_gratitude=round(float(at.get("affect_gratitude", 0.0)), 4),
                    affect_resentment=round(float(at.get("affect_resentment", 0.0)), 4),
                    affect_contempt=round(float(at.get("affect_contempt", 0.0)), 4),
                    affect_affection=round(float(at.get("affect_affection", 0.0)), 4),
                    affect_fear=round(float(at.get("affect_fear", 0.0)), 4),
                    attraction=round(float(at.get("attraction", 0.0)), 4),
                    romantic=round(float(at.get("romantic", 0.0)), 4),
                    tie_strength=round(float(at.get("tie_strength", 0.0)), 4),
                    band=self.band_name(code), band_code=code,
                    altruism_bias=round(float(at.get("altruism_bias", 0.0)), 4))

    @staticmethod
    def band_name(code):
        return {5: "family", 4: "intimate", 3: "friend", 2: "acquaintance",
                1: "consequential_stranger", 0: "stranger", -1: "rival"}.get(code, "?")

    def close(self):
        return None
