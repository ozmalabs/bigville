"""Phase 016b: the founding cast is seeded from JOBS, with drawn ages, households, and a genealogy that
follows them.

The counts are the primary jobs of E.seed_jobs(100). check_job_seed(100) agrees with the cast that is built.
Ages are drawn from FOUNDING_AGE on their own stream. Households group the founders (spouses who share a
home, adult children, siblings), each with one home. The genealogy is drawn from those households.
"""
from __future__ import annotations

import collections
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains import bigville_entities as E      # noqa: E402
from domains import population as POP          # noqa: E402
from worlds.bigville_town100_world import build_town_100, generate_cast100  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402

SEED = 305000


@pytest.fixture(scope="module")
def town():
    return BigvilleWorld.from_town100(seed=SEED)


def _cast(town):
    return town._cast100["residents"]


def _attrs(town, name):
    return town.eng.node(town._actors[name])["attrs"]


# ---------------------------------------------------------------- counts and jobs

def test_the_counts_are_seed_jobs_and_check_job_seed_agrees_with_the_cast_built(town):
    seed = E.seed_jobs(100)
    check = E.check_job_seed(100)
    assert check["ok"], check["issues"]
    assert seed["short"] == 0
    cast = _cast(town)
    assert len(cast) == len(seed["residents"]) == 100
    # every resident holds the jobs the seed gave them, first job first
    assert [r["jobs"] for r in cast] == [s["jobs"] for s in seed["residents"]]
    # each built resident's role is the primary job the seed gave them
    assert sorted(_attrs(town, r["name"])["role"] for r in cast) == sorted(s["jobs"][0] for s in seed["residents"])
    # the holders check_job_seed reports are the holders in the cast built
    holders = collections.Counter(job for r in cast for job in r["jobs"])
    for job, n in check["seed"]["holders"].items():
        assert holders.get(job, 0) == n, job


def test_every_job_has_a_workplace_and_a_group_and_each_resident_works_there(town):
    workplaces = set(E.FOUNDING_WORKPLACES) | set(E.FOUNDING_DEPOSITS) | {"farm"}
    for job in E.JOBS:
        row = E.FOUNDING_JOBS[job]
        assert row["group"] in E.FOUNDING_CLASS["by_group"], job
        assert row["workplace"] in workplaces, job
    for r in _cast(town):
        assert r["workplace_kind"] == E.FOUNDING_JOBS[r["role"]]["workplace"]
        if r["workplace_kind"] == "farm":
            assert tuple(r["workplace_cell"]) in set(map(tuple, town._map_layout["farms"]))
        else:
            assert tuple(r["workplace_cell"]) == tuple(town._map_layout["work"][r["workplace_kind"]])


def test_the_self_test_is_clean():
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []


# ---------------------------------------------------------------- ages

def test_founders_have_drawn_ages_of_working_age_and_the_world_carries_them(town):
    cast = _cast(town)
    ages = [r["age"] for r in cast]
    adult = E.LIFE_STAGES["adult"]
    assert all(adult["age_min"] <= a <= adult["age_max"] for a in ages)
    assert len(set(ages)) > 20 and any(a != 30 for a in ages)     # drawn, not the 30 default
    assert ages == POP.draw_founding_ages(100, SEED)
    assert [_attrs(town, r["name"])["age"] for r in cast] == [float(a) for a in ages]
    assert abs(sum(ages) / len(ages) - E.FOUNDING_AGE["mean"]) < 4.0


# ---------------------------------------------------------------- households

def test_each_resident_is_in_one_household_and_each_household_has_one_home(town):
    cast = _cast(town)
    households = town._cast100["households"]
    seen = []
    for h in households:
        for member in h["members"]:
            seen.append(member)
            assert town._t100_households[member] == f"household_{h['index']:03d}"
    assert sorted(seen) == sorted(r["name"] for r in cast)
    homes = [tuple(h["home_cell"]) for h in households]
    assert len(set(homes)) == len(households) == len(town._households)
    by_name = {r["name"]: r for r in cast}
    for h in households:
        for member in h["members"]:
            assert tuple(by_name[member]["home_cell"]) == tuple(h["home_cell"])


def test_a_household_kind_follows_its_head_and_its_members_share_a_home(town):
    by_name = {r["name"]: r for r in _cast(town)}
    for h in town._cast100["households"]:
        head = by_name[h["head"]]
        node = town._households[f"household_{h['index']:03d}"]
        assert town.eng.node(node)["attrs"]["kind"] == town.household_kind_for(head["role"], head["group"])
        assert by_name[h["head"]]["household_role"] == "head"


def test_spouses_who_share_a_household_are_recorded_as_a_union(town):
    index = town._kin_index()
    by_name = {r["name"]: r for r in _cast(town)}
    for h in town._cast100["households"]:
        spouses = [m for m in h["members"] if by_name[m]["household_role"] == "spouse"]
        for s in spouses:
            head_node, spouse_node = town._actors[h["head"]], town._actors[s]
            unions = [u for u in index["partners"][int(head_node)] if {u["a"], u["b"]} == {int(head_node), int(spouse_node)}]
            assert unions, (h["head"], s)
            assert unions[0]["start"] <= 0.0


def test_realised_household_shares_are_reported_and_match_the_town(town):
    households = town._cast100["households"]
    shares = POP.describe_founding_kin(100, seed=SEED)
    sizes = [len(h["members"]) for h in households]
    assert shares["households"] == len(households) == 46
    assert shares["mean_members"] == round(sum(sizes) / len(households), 3)
    assert shares["mean_drawn_size"] == round(sum(h["size_drawn"] for h in households) / len(households), 3)
    assert shares["extended_share"] == round(sum(1 for h in households if h["extended"]) / len(households), 4)
    # a household never holds more founders than its drawn size
    assert all(len(h["members"]) <= h["size_drawn"] for h in households)


# ---------------------------------------------------------------- genealogy

def test_unions_between_founders_are_co_resident_spouses(town):
    index = town._kin_index()
    founders = {int(town._actors[r["name"]]) for r in _cast(town)}
    spouse_pairs = set()
    for h in town._cast100["households"]:
        for m in h["members"]:
            if by_name_role(town, m) == "spouse":
                spouse_pairs.add(frozenset((int(town._actors[h["head"]]), int(town._actors[m]))))
    unions = [u for lst in index["partners"].values() for u in lst]
    between_founders = [u for u in unions if u["a"] in founders and u["b"] in founders]
    assert between_founders, "the town has no union between two founders"
    for u in between_founders:
        assert frozenset((u["a"], u["b"])) in spouse_pairs


def by_name_role(town, name):
    return next(r["household_role"] for r in _cast(town) if r["name"] == name)


def test_children_and_siblings_in_a_household_share_their_parents(town):
    index = town._kin_index()
    for h in town._cast100["households"]:
        head = int(town._actors[h["head"]])
        head_parents = set(index["parents"][head])
        assert len(head_parents) >= 1
        for name in h["members"]:
            node = int(town._actors[name])
            role = by_name_role(town, name)
            if role == "child":
                # the head is a parent; the other parent is the head's spouse, co-resident or outside
                parents = set(index["parents"][node])
                assert head in parents and len(parents) <= 2, name
            elif role == "sibling":
                assert set(index["parents"][node]) == head_parents, name
    assert all(index["parents"][int(town._actors[r["name"]])] for r in _cast(town))


def test_every_founder_has_a_parent_on_record(town):
    index = town._kin_index()
    assert all(index["parents"][int(town._actors[r["name"]])] for r in _cast(town))


# ---------------------------------------------------------------- determinism and sources

def test_the_plan_is_the_same_for_the_same_seed_and_differs_for_another(town):
    first = E.plan_founding_town(SEED)
    again = E.plan_founding_town(SEED)
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(again, sort_keys=True, default=str)
    assert E.plan_founding_town(SEED + 1)["ages"] != first["ages"]
    again_town = BigvilleWorld.from_town100(seed=SEED)
    assert again_town._cast100 == town._cast100


def test_capability_and_skill_are_read_from_the_pack(town):
    capability = E.FOUNDING_CLASS["capability_by_literacy"]
    for r in _cast(town):
        attrs = _attrs(town, r["name"])
        assert attrs["capability"] == capability["literate" if r["literacy"] else "unlettered"]
        trade = E.JOBS[r["role"]]["trades"][0]
        assert attrs["skill"] == float(E.TRADES.get(trade, {}).get("base_skill", E.ACTOR_DEFAULTS["skill"]))


def test_the_committed_cast_seeds_are_the_generator_output():
    _, _, layout = build_town_100(SEED)
    cast = json.loads(json.dumps(generate_cast100(layout, SEED)))
    for path in (os.path.join(_ROOT, "seeds", "bigville_cast100.json"),
                 os.path.join(_ROOT, "bigville", "seeds", "bigville_cast100.json")):
        with open(path, encoding="utf-8") as fh:
            assert json.load(fh) == cast, path
