"""bigville_social_seed -- generates a resident's REASONABLE pre-existing
disposition backstory: who they already know (a small, homophily-biased
slice of the same 100-cast, reusing bigville_bond_world's own PRIORS/kind
vocabulary VERBATIM -- not reinvented) and a handful of self/group priors
(self-efficacy, deservingness, in-group/out-group affinity).

Dependency-free (numpy only), matching every other seed builder in this
repo. Pure DATA generation: no agent decision logic. Deterministic in
`seed`, own RNG streams throughout (never reuses generate_cast100's own
streams -- so re-running write_cast_seed() is unaffected by anything here,
and vice versa).

Downstream: an external cognition provider (e.g. Ocelot) reads the
exported JSON and applies it into its OWN belief representation -- this
module and this repo make no assumption about, and have no dependency on,
what that representation is (`docs/features/bigville.md`'s adapter
boundary: Bigville does not own a second cognition engine).
"""
from __future__ import annotations

import json
import os

import numpy as np

from worlds.bigville_bond_world import BigvilleBondWorld, PRIORS
from worlds.bigville_town100_world import (
    SEED_DEFAULT, _ROOT, build_town_100, generate_cast100,
)

# self/group prior params: key -> (mean, sd, lo, hi), the SAME _draw_clip
# convention _PARAM_SPEC uses, kept in a SEPARATE table (and drawn from a
# SEPARATE rng stream below) so the committed bigville_cast100.json stays
# byte-unchanged -- this is purely additive.
_SELF_PARAM_SPEC = {
    # Bandura 1977/1997: task-specific capability belief. Domain = the
    # resident's own role (their actual occupation), applied downstream.
    "self_efficacy_prior":  (0.00, 0.50, -2.0, 2.0),
    # Smith & Kim 2007 / Van de Ven, Zeelenberg & Pieters 2009: prior belief
    # that OTHERS' relative advantage is fair (deservingness).
    "deservingness_prior":  (0.00, 0.50, -2.0, 2.0),
    # Tajfel, Billig, Bundy & Flament 1971 (minimal group paradigm): a mild
    # positive default toward one's OWN class/group/role/workplace bucket.
    "ingroup_affinity":     (0.40, 0.30, -1.0, 2.0),
    # ...and a mild negative default toward the socially-salient OUT group
    # (bigville's own PREREG already treats the low/high SES tier as the
    # two gate-relevant poles -- reused here, not invented).
    "outgroup_suspicion":   (-0.20, 0.40, -2.0, 1.0),
}

# relationship-kind sample weights: acquaintance is the common case; kin and
# feud are the rare extremes (mirrors real social-network degree structure,
# McPherson, Smith-Lovin & Cook 2001's "most ties are weak ties").
_KIND_WEIGHTS = {"acquaintance": 0.55, "chosen": 0.25,
                 "blood_kin": 0.10, "feud": 0.10}
_KINDS = list(_KIND_WEIGHTS.keys())
_KIND_P = [_KIND_WEIGHTS[k] for k in _KINDS]

_N_LO, _N_HI = 3, 8   # people-in-life count range, inclusive


def _draw_clip(rng, mean, sd, lo, hi):
    v = float(rng.normal(mean, sd))
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return round(v, 4)


def sample_self_priors(cast, seed):
    """{resident_name: {param: value}} for every _SELF_PARAM_SPEC entry --
    own rng stream (seed+31), isolated from every other draw in this repo."""
    rng = np.random.default_rng(seed + 31)
    out = {}
    for resident in cast:
        out[resident["name"]] = {
            k: _draw_clip(rng, m, s, lo, hi)
            for k, (m, s, lo, hi) in _SELF_PARAM_SPEC.items()}
    return out


def _homophily_weight(a, b):
    """Higher weight for a same-role / same-workplace / same-group other
    resident (McPherson, Smith-Lovin & Cook 2001's homophily finding: people
    you know tend to share your occupation/neighbourhood/tier). Base weight
    1.0 so no resident is ever unreachable."""
    w = 1.0
    if a["role"] == b["role"]:
        w += 2.0
    if a["workplace_kind"] == b["workplace_kind"]:
        w += 1.0
    if a["group"] == b["group"]:
        w += 1.0
    return w


def sample_people_in_life(cast, seed, n_lo=_N_LO, n_hi=_N_HI):
    """[(holder_name, toward_name, kind), ...] -- one directed slice per
    resident (who THEY consider part of their life), homophily-biased
    partner selection, kind drawn from bigville_bond_world's own PRIORS
    vocabulary. Two independent rng streams (partner count/selection vs.
    kind), isolated from sample_self_priors and generate_cast100."""
    nrng = np.random.default_rng(seed + 37)   # partner count + selection
    krng = np.random.default_rng(seed + 41)   # relationship kind

    triples = []
    for i, resident in enumerate(cast):
        others = [r for j, r in enumerate(cast) if j != i]
        weights = np.array([_homophily_weight(resident, o) for o in others],
                           dtype=float)
        weights /= weights.sum()
        n = int(nrng.integers(n_lo, n_hi + 1))
        n = min(n, len(others))
        chosen_idx = nrng.choice(len(others), size=n, replace=False, p=weights)
        for oi in chosen_idx:
            other = others[int(oi)]
            kind = str(krng.choice(_KINDS, p=_KIND_P))
            triples.append((resident["name"], other["name"], kind))
    return triples


def build_bond_seed(cast, seed):
    """A populated BigvilleBondWorld -- every resident an agent, every
    sampled (holder, toward, kind) triple an elaborated Bond carrying
    PRIORS' own kind-appropriate defaults (kin/feud/etc -- reused
    verbatim, not reinvented). Returns (bond_world, triples)."""
    bw = BigvilleBondWorld(freeze=True)
    for resident in cast:
        bw.add_agent(resident["name"])
    triples = sample_people_in_life(cast, seed)
    for holder, toward, kind in triples:
        bw.elaborate(holder, toward, kind=kind)
    return bw, triples


def export_bond_slots(bond_world, triples):
    return [bond_world.slots(holder, toward) for holder, toward, _kind in triples]


def _world_strength(bond_world, holder, toward, kind):
    """Project one rich Bond slot down to `set_relationship`'s single
    signed `strength` scalar -- matching `TOWNSPEOPLE_50_RELATIONSHIP_
    KIND`'s own convention (worlds/bigville_world.py) EXACTLY: `feud` is
    negative, everything else is the (non-negative) tie_strength."""
    slots = bond_world.slots(holder, toward)
    if kind == "feud":
        return -slots["affect_resentment"]
    return slots["tie_strength"]


def seed_generated_relationships(world, cast, seed=SEED_DEFAULT):
    """Bridges the SAME generated people-in-life backstory into
    `world.set_relationship` -- the pre-existing, BACKEND-AGNOSTIC channel
    `BigvilleGame._relationship_signal` already exposes on every actor's
    `ActorContext` (`nearby_residents[i].tie_strength`/`band_code`, and
    `_speech_relationship`'s full attrs dict). This is what makes the
    generated backstory usable by an LLM backend (or any other), not only
    by an Ocelot backend reading the richer exported bond slots directly
    -- one generation (`sample_people_in_life`), two projections: this
    coarse `(kind, strength)` pair for universal ActorContext visibility,
    and the full multi-slot Bond (`export_bond_slots`) for Ocelot's own
    deeper psychological modeling.

    `kind` is passed through UNCHANGED (blood_kin/chosen/acquaintance/
    feud) -- `_speech_relationship` exposes the full attrs dict to any
    downstream consumer, so nothing is lost narrowing it to "friend".

    Opt-in only, matching `seed_workplace_relationships`'s own documented
    convention -- NOT called from `populate_town100`/`from_town100`, so
    `test_bigville_reporting.py`'s exact `directed_bonds` baseline against
    a bare `from_town100()` town is unaffected. Requires `world` to
    already have every cast resident as an actor (e.g. after
    `world.populate_town100(seed=seed)`). Returns the number of
    relationships minted."""
    bond_world, triples = build_bond_seed(cast, seed)
    minted = 0
    for holder, toward, kind in triples:
        strength = _world_strength(bond_world, holder, toward, kind)
        world.set_relationship(holder, toward, kind=kind, strength=strength)
        minted += 1
    return minted


def generate_disposition_seed(seed=SEED_DEFAULT):
    """The full, pure-data disposition backstory for the seed=305000 cast:
    {"self_priors": {...}, "bonds": [...]}. Deterministic in `seed`."""
    _, _, layout = build_town_100(seed)
    cast = generate_cast100(layout, seed)["residents"]
    self_priors = sample_self_priors(cast, seed)
    bond_world, triples = build_bond_seed(cast, seed)
    bonds = export_bond_slots(bond_world, triples)
    return {
        "id": "bigville_dispositions_cast100", "version": "1.0.0",
        "seed": seed,
        "description": ("Generated pre-existing disposition backstory for the "
                        "100-resident cast (blocks 305000-309000): self/group "
                        "priors (self-efficacy, deservingness, in-group/"
                        "out-group affinity) + a homophily-biased slice of "
                        "%d-%d people-in-life bonds per resident, reusing "
                        "bigville_bond_world's own PRIORS kind vocabulary "
                        "verbatim. Deterministic in seed=%d." % (_N_LO, _N_HI, seed)),
        "self_priors": self_priors,
        "bonds": bonds,
    }


def write_disposition_seed(path=None, seed=SEED_DEFAULT):
    """Emit the committed disposition seed JSON. Deterministic -- regenerating
    and re-writing produces a byte-identical file."""
    if path is None:
        path = os.path.join(_ROOT, "seeds", "bigville_dispositions_cast100.json")
    data = generate_disposition_seed(seed)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
    return path


__all__ = [
    "sample_self_priors", "sample_people_in_life", "build_bond_seed",
    "export_bond_slots", "generate_disposition_seed", "write_disposition_seed",
    "seed_generated_relationships",
]
