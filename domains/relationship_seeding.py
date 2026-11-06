"""relationship_seeding.py -- the founding ties between residents (Phase 058).

The world held no relationship records at founding. This module writes them from what the founding
town already records: spouses and kin (the held genealogical terms, Phase 009), household members,
workmates (same workplace cell), neighbours (home cells near each other), then friends and rivals drawn by
trait compatibility and class. Each tie is a directed record (`World.set_relationship`) with a kind, a
strength (the lexicon's relationship_strength scale) and a one-line history.

The counts, strengths, pools and history lines are the pack's RELATIONSHIP_SEEDING table. The draws use
their own generator, seeded from the world seed plus RELATIONSHIP_SEEDING.stream, so the world's own
random streams are not touched. The seeding records a fact of the founding. What a resident thinks of a
tie stays in that resident's backend.

    plan_ties(people, cfg, seed)             -> the ties, as plain dicts (pure; no world)
    seed_founding_relationships(world, seed) -> the number of ties written (0 when disabled)
"""
from __future__ import annotations

import numpy as np

from domains.pack import load_pack

DEFAULT_PACK = "bigville"


def _distance(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _compatibility(a, b):
    """How well two residents' traits fit, 1 at the closest. Uses charm, trust and temperament, and
    adds a small bonus for sharing a class."""
    gap = (abs(a["traits"]["charm"] - b["traits"]["charm"])
           + abs(a["traits"]["trust"] - b["traits"]["trust"])
           + abs(a["traits"]["valence"] - b["traits"]["valence"]) / 2.0)
    same_class = 0.2 if a["class"] == b["class"] else 0.0
    return 1.0 - gap / 3.0 + same_class


def plan_ties(people, cfg, seed):
    """The founding ties for `people` (a list in cast order), as dicts with holder, target, kind, strength,
    term, history and years_known.

    Each person is a dict: name, household (int or None), home (x, y), work (x, y), class, age,
    years_in_village, traits {charm, trust, valence, spite}, kin [(target name, term)] (held genealogical
    terms for residents). A tie is written at most once per (holder, target) pair, in this order: spouse
    and kin, household, then for each resident in cast order: workmates, neighbours, friends, and a rival
    when spite is high enough."""
    rng = np.random.default_rng(int(seed) + int(cfg["stream"]))
    close_terms = set(cfg["close_kin_terms"])
    order = {p["name"]: i for i, p in enumerate(people)}
    by_name = {p["name"]: p for p in people}
    ties, recorded = [], set()

    def years_between(a, b):
        return min(float(a["years_in_village"]), float(b["years_in_village"]))

    def close_count(name):
        """How many close ties the holder already has (kinds in RELATIONSHIP_SEEDING.close_kinds)."""
        return sum(1 for t in ties if t["holder"] == name and t["kind"] in set(cfg["close_kinds"]))

    def add(holder, target, strength_key, history, years, term=""):
        if holder["name"] == target["name"] or (holder["name"], target["name"]) in recorded:
            return
        recorded.add((holder["name"], target["name"]))
        ties.append({"holder": holder["name"], "target": target["name"],
                     "kind": cfg["kind_of"][strength_key],
                     "strength": float(cfg["strength"][strength_key]), "term": term,
                     "history": history, "years_known": float(years), "household": False})

    # 1. Spouses and kin, from the held genealogical terms. Each held term is one directed tie.
    for p in people:
        for target_name, term in p["kin"]:
            target = by_name[target_name]
            if term == "spouse":
                add(p, target, "spouse", cfg["history"]["spouse"], years_between(p, target), term)
            elif term in close_terms:
                add(p, target, "close_kin", cfg["history"]["kin"].replace("{term}", term), p["age"], term)
            else:
                add(p, target, "kin", cfg["history"]["kin"].replace("{term}", term), p["age"], term)

    # 2. Household members: every other member of the same household, both ways. A pair already tied as kin
    # keeps the kin kind and gets the household flag; a housemate who is not kin gets the kind household.
    households = {}
    for p in people:
        if p["household"] is not None:
            households.setdefault(p["household"], []).append(p)
    for members in households.values():
        for a in members:
            for b in members:
                if a["name"] == b["name"]:
                    continue
                if (a["name"], b["name"]) in recorded:
                    for tie in ties:
                        if tie["holder"] == a["name"] and tie["target"] == b["name"]:
                            tie["household"] = True
                else:
                    add(a, b, "household", cfg["history"]["household"], years_between(a, b))
                    ties[-1]["household"] = True

    # 3. Social ties, per resident in cast order.
    for p in people:
        pool = [q for q in people if q["work"] == p["work"] and q["name"] != p["name"]
                and (p["name"], q["name"]) not in recorded]
        if pool and int(cfg["colleague_count"]) > 0:
            for index in rng.permutation(len(pool))[:int(cfg["colleague_count"])]:
                q = pool[int(index)]
                add(p, q, "workmate", cfg["history"]["workmate"], years_between(p, q))

        near = [q for q in people if q["name"] != p["name"] and q["household"] != p["household"]
                and (p["name"], q["name"]) not in recorded
                and _distance(p["home"], q["home"]) <= int(cfg["neighbour_radius"])]
        near.sort(key=lambda q: (_distance(p["home"], q["home"]), order[q["name"]]))
        for q in near[:int(cfg["neighbour_count"])]:
            add(p, q, "neighbour", cfg["history"]["neighbour"], years_between(p, q))

        candidates = [q for q in people if q["name"] != p["name"] and (p["name"], q["name"]) not in recorded]
        room = int(cfg["max_close_ties"]) - close_count(p["name"])
        if candidates and int(cfg["friend_count"]) > 0 and room > 0:
            noise = rng.random(len(candidates))
            ranked = sorted(range(len(candidates)),
                            key=lambda i: (-_compatibility(p, candidates[i]), noise[i],
                                           order[candidates[i]["name"]]))
            for i in ranked[:min(int(cfg["friend_count"]), room)]:
                q = candidates[i]
                add(p, q, "friend", cfg["history"]["friend"], years_between(p, q))
                room -= 1

        if float(p["traits"]["spite"]) >= float(cfg["rival_spite_min"]) and room > 0:
            rivals = [q for q in people if q["name"] != p["name"] and q["class"] != p["class"]
                      and (p["name"], q["name"]) not in recorded]
            rivals.sort(key=lambda q: (_compatibility(p, q), order[q["name"]]))
            for q in rivals[:min(int(cfg["rival_count"]), room)]:
                add(p, q, "feud", cfg["history"]["rival"], years_between(p, q))
    return ties


def _people(world):
    """The founding residents as plain dicts, from the world's cast record and the kin terms each holds."""
    cast = world._cast100["residents"]
    names = {r["name"] for r in cast}
    out = []
    for record in cast:
        history = record.get("history") or {}
        kin = [(row["target"], row["term"]) for row in world.kin_terms_held(record["name"])
               if row["target"] in names and row["target"] != record["name"]
               and row.get("attribution") == "genealogy"]
        params = record["params"]
        out.append({
            "name": record["name"], "household": record.get("household"),
            "home": tuple(record["home_cell"]), "work": tuple(record["workplace_cell"]),
            "class": record["class"], "age": float(record["age"]),
            "years_in_village": float(history.get("years_in_village", record["age"])),
            "traits": {"charm": float(params["charm_weight"]), "trust": float(params["prior_others_trust"]),
                       "valence": float(params["valence"]), "spite": float(params["w_spite"])},
            "kin": sorted(kin)})
    return out


def seed_founding_relationships(world, seed, *, enabled=None, pack=DEFAULT_PACK):
    """Write the founding ties on `world` and return how many were written.

    `enabled` overrides RELATIONSHIP_SEEDING.enabled; None reads the pack's switch. A world with no cast
    (a scenario world) has no founding ties and returns 0."""
    cfg = load_pack(pack)["RELATIONSHIP_SEEDING"]
    if enabled is None:
        enabled = bool(cfg["enabled"])
    if not enabled or not getattr(world, "_cast100", None):
        return 0
    ties = plan_ties(_people(world), cfg, seed)
    for tie in ties:
        bond = world.set_relationship(tie["holder"], tie["target"], kind=tie["kind"], strength=tie["strength"])
        world.eng.set_attr(bond, "history", tie["history"])
        world.eng.set_attr(bond, "years_known", tie["years_known"])
        world.eng.set_attr(bond, "term", tie["term"])
        world.eng.set_attr(bond, "seeded", 1.0)
        world.eng.set_attr(bond, "household", 1.0 if tie["household"] else 0.0)
    return len(ties)
