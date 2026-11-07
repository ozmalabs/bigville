"""Gate for worlds/bigville_social_seed.py -- reasonable, deterministic,
homophily-biased pre-existing dispositions (people-in-life bonds +
self/group priors) for the 100-resident cast."""
from __future__ import annotations

import numpy as np

# Import the bigville package FIRST (fully initializes bigville.game's own
# import of worlds.bigville_bond_world) -- otherwise importing
# worlds.bigville_bond_world directly, as the very first touch of the
# bigville package, hits a pre-existing circular-import bootstrap order
# (worlds.bigville_bond_world -> bigville.runtime -> bigville/__init__.py ->
# bigville.game -> worlds.bigville_bond_world, mid-init). Same avoidance
# pattern tests/test_bigville_game_api.py already uses.
import bigville.game  # noqa: F401

from worlds.bigville_social_seed import (
    _N_HI, _N_LO, _SELF_PARAM_SPEC, build_town_100, generate_cast100,
    generate_disposition_seed, sample_people_in_life, sample_self_priors,
    seed_generated_relationships,
)
from worlds.bigville_world import BigvilleWorld

SEED = 305000


def _cast():
    _, _, layout = build_town_100(SEED)
    return generate_cast100(layout, SEED)["residents"]


def test_deterministic_same_seed_byte_identical():
    a = generate_disposition_seed(SEED)
    b = generate_disposition_seed(SEED)
    assert a == b


def test_every_resident_has_people_in_life_within_range():
    cast = _cast()
    triples = sample_people_in_life(cast, SEED)
    counts = {}
    for holder, _toward, _kind in triples:
        counts[holder] = counts.get(holder, 0) + 1
    assert set(counts) == {r["name"] for r in cast}
    for name, n in counts.items():
        assert _N_LO <= n <= _N_HI, (name, n)


def test_no_self_bonds():
    cast = _cast()
    triples = sample_people_in_life(cast, SEED)
    for holder, toward, _kind in triples:
        assert holder != toward


def test_homophily_same_role_overrepresented():
    """Same-role others should be chosen at a higher rate than their share
    of the population would predict under uniform random selection."""
    cast = _cast()
    by_name = {r["name"]: r for r in cast}
    triples = sample_people_in_life(cast, SEED)

    same_role = sum(1 for h, t, _k in triples if by_name[h]["role"] == by_name[t]["role"])
    rate = same_role / len(triples)

    # uniform-random baseline: expected same-role rate if partners were
    # picked with NO homophily bias, i.e. (role_count-1)/(N-1) averaged.
    from collections import Counter
    role_counts = Counter(r["role"] for r in cast)
    n = len(cast)
    baseline = sum((c - 1) / (n - 1) * c for c in role_counts.values()) / n

    # Compare odds, not rates: a rate ratio is capped at 1/baseline, so it shrinks as one role
    # dominates the cast (Phase 016b: 60 of 100 founders are labourers) even when the bias is
    # unchanged. The odds ratio does not depend on the role mix. HEAD cast: 2.96; 016b cast: 1.92.
    odds_ratio = (rate / (1.0 - rate)) / (baseline / (1.0 - baseline))
    assert odds_ratio > 1.5, (rate, baseline, odds_ratio)


def test_kind_distribution_acquaintance_is_plurality():
    cast = _cast()
    triples = sample_people_in_life(cast, SEED)
    from collections import Counter
    kinds = Counter(k for _h, _t, k in triples)
    assert kinds["acquaintance"] == max(kinds.values())
    assert set(kinds) <= {"acquaintance", "chosen", "blood_kin", "feud"}


def test_self_priors_not_cloned():
    cast = _cast()
    priors = sample_self_priors(cast, SEED)
    assert set(priors) == {r["name"] for r in cast}
    for param in _SELF_PARAM_SPEC:
        values = [p[param] for p in priors.values()]
        assert np.var(values) > 0.0, param


def test_bonds_carry_prior_kind_slots():
    data = generate_disposition_seed(SEED)
    assert data["bonds"], "expected at least one bond"
    for slot in data["bonds"][:5]:
        assert "prior" in slot
        assert "belief_trust" in slot
        assert "affect_resentment" in slot
        assert "tie_strength" in slot


def test_streams_isolated_from_cast100_and_each_other():
    """Regenerating the disposition seed must not perturb generate_cast100's
    own output (separate rng streams, seed+31/+37/+41 vs the cast's own)."""
    _, _, layout = build_town_100(SEED)
    cast_before = generate_cast100(layout, SEED)
    generate_disposition_seed(SEED)
    cast_after = generate_cast100(layout, SEED)
    assert cast_before == cast_after


# ---------------------------------------------------------------------
# Backend-agnostic visibility: the SAME generated backstory must reach
# ActorContext via world.set_relationship, not only the exported bond
# JSON an Ocelot-specific consumer reads -- so an LLM backend (or any
# other) sees it too (BigvilleGame._relationship_signal / PromptBuilder).
# ---------------------------------------------------------------------
def test_seed_generated_relationships_reaches_actor_context():
    cast = _cast()
    world = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    minted = seed_generated_relationships(world, cast, SEED)
    assert minted == len(sample_people_in_life(cast, SEED))

    triples = sample_people_in_life(cast, SEED)
    holder, toward, kind = triples[0]
    rel = world.relationship(holder, toward)
    assert rel is not None
    attrs = world.eng.node(rel)["attrs"]
    assert attrs["kind"] == kind
    if kind == "feud":
        assert attrs["strength"] <= 0.0
    else:
        assert attrs["strength"] >= 0.0


def test_seed_generated_relationships_feud_strength_is_negative():
    cast = _cast()
    world = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    seed_generated_relationships(world, cast, SEED)

    triples = sample_people_in_life(cast, SEED)
    feud_triples = [t for t in triples if t[2] == "feud"]
    assert feud_triples, "expected at least one feud triple at this seed"
    holder, toward, _kind = feud_triples[0]
    rel = world.relationship(holder, toward)
    strength = world.eng.node(rel)["attrs"]["strength"]
    assert strength < 0.0


def test_seed_generated_relationships_not_auto_wired_into_from_town100():
    """A bare from_town100() town holds the founding ties (Phase 058, switch on in the bigville pack), and
    nothing else: every bond on record is a founding tie (`seeded`), so the workplace ring stays opt-in."""
    world = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    assert len(world._relationships) == 845
    assert all(world.eng.node(bond)["attrs"].get("seeded") == 1.0 for bond in world._relationships.values())
