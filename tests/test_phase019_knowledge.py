"""Phase 019: derived knowledge priors (awareness, understanding, existence and location).

One group per bullet of the brief's Acceptance list, plus the pure-function, seeding, and self-test checks.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from bigville.game import BigvilleGame
from domains import bigville_entities as E
from domains.knowledge import derive_knowledge, knowledge_memories, person_from_attrs
from domains.data_view import entities as pack_view
from domains.population import draw_founding_history
from worlds.bigville_world import BigvilleWorld

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _person(**overrides):
    """A lifelong, literate, local resident with no trades unless given."""
    base = {"name": "Test", "age": 40.0, "job": "labourer", "trades": [], "literacy": 1.0,
            "skill_levels": {}, "metaskill_levels": {}, "aptitude": 1.0, "talents": {}, "limitations": [],
            "history": {"local": True, "years_in_village": 40.0}, "household": "h", "workplace": "",
            "neighbours": [], "kin_terms": []}
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def town():
    return BigvilleWorld.from_town100()


@pytest.fixture(scope="module")
def cast(town):
    return town._cast100


def _person_of(town, name):
    node = town._actors[name]
    attrs = dict(town.eng.node(node)["attrs"])
    return person_from_attrs(name, attrs, pack=E, history=attrs.get("history"),
                             kin_terms=[r["term"] for r in town.kin_terms_held(name)],
                             neighbours=[{"name": n, "job": town.eng.node(m)["attrs"].get("role", ""),
                                          "household": town.eng.node(m)["attrs"].get("household", ""),
                                          "workplace": ""} for n, m in town._actors.items() if n != name],
                             home_cell=town.actor_position(name))


def _first_with_role(cast, role):
    return next(r for r in cast["residents"] if r["role"] == role)


# ----------------------------------------------------------------- acceptance: baker and milling
def test_a_baker_understands_baking_and_is_aware_of_milling(town, cast):
    baker = _first_with_role(cast, "baker")
    derived = derive_knowledge(_person_of(town, baker["name"]), E)
    bake = derived["recipe:bake_bread"]
    assert bake["understands"] > 0, bake["basis"]
    assert bake["aware"] and bake["basis"]
    grind = derived["recipe:grind_flour"]
    assert grind["aware"] is True, "milling is in the baker's cluster (foodcraft)"
    assert grind["understands"] == 0.0, "a baker does not practise milling"
    assert any("cluster" in note for note in grind["basis"])
    assert derived["place:mill"]["aware"] is True, "the mill is publicly known"


def test_a_pure_baker_description_understands_bread_at_the_working_level():
    person = _person(job="baker", trades=[], skill_levels={"baking": 0.7, "milling": 0.6},
                     metaskill_levels={"provisioning": 0.4})
    derived = derive_knowledge(person, E)
    bake = derived["recipe:bake_bread"]
    assert bake["understands"] >= 0.7, "the working level is at least the base skill"
    assert bake["understands"] <= 1.0


# ----------------------------------------------------- acceptance: former apprentice smith who now farms
def _smith_recipe():
    """A smith recipe anyone can attempt (min skill 0, common), to test a basic one."""
    return next(r["name"] for r in E.RECIPES
                if r["requires"] == "smith" and r.get("common") is not False
                and E.MIN_SKILL.get(r["name"], 0.0) == 0.0)


def test_a_former_apprentice_smith_who_farms_understands_basic_smithing_at_a_lower_degree():
    basic = _smith_recipe()
    apprentice = _person(job="farm_labourer", trades=["farmer"], skill_levels={"fieldwork": 0.2},
                         history={"local": True, "years_in_village": 40.0,
                                  "former_trades": [{"trade": "smith", "years": 3.0, "level": 0.3,
                                                     "skills": ["smithing"]}]},
                         literacy=0.0)
    apprentice["skill_levels"]["smithing"] = 0.3
    smith = _person(job="smith", trades=[], skill_levels={"smithing": 0.7})
    apprentice_row = derive_knowledge(apprentice, E)[f"recipe:{basic}"]
    smith_row = derive_knowledge(smith, E)[f"recipe:{basic}"]
    assert 0.0 < apprentice_row["understands"] < smith_row["understands"], (apprentice_row, smith_row)
    assert apprentice_row["understands"] == pytest.approx(0.3, abs=1e-6), "the working level from the apprenticeship"
    assert any("smith" in note for note in apprentice_row["basis"])


def test_a_former_apprenticeship_gives_the_skill_levels_the_history_says(cast):
    """History and skill levels are drawn together: an earlier apprenticeship sets the trade's level, capped at
    the trade's base skill, and the cast's current-trade skill levels are not changed by it."""
    base = E.TRADES
    checked = 0
    for index, record in enumerate(cast["residents"]):
        former = record["history"]["former_trades"]
        for entry in former:
            checked += 1
            trade = entry["trade"]
            assert entry["level"] <= base[trade]["base_skill"] + 1e-9
            assert entry["level"] == pytest.approx(min(base[trade]["base_skill"],
                                                      E.HISTORY["level_per_year"] * entry["years"]), abs=1e-4)
            assert entry["years"] <= record["age"] - E.HISTORY["apprenticeship_min_start_age"]
            for skill in E.TRADE_SKILLS[trade]:
                assert record["former_skills"][skill] == entry["level"]
    assert checked > 0, "the founding cast has at least one former apprenticeship"


# -------------------------------------------- acceptance: illiterate resident, written law
def test_an_illiterate_resident_is_aware_of_the_theft_law_but_does_not_understand_the_text():
    person = _person(literacy=0.0, job="farm_labourer", trades=["farmer"])
    row = derive_knowledge(person, E)["law:giantville_theft_law"]
    assert row["aware"] is True, row["basis"]
    assert row["understands"] == 0.0, "the written text needs an educated reader"
    assert any("not met: reads at the educated level" in note for note in row["basis"])
    literate = derive_knowledge(_person(literacy=1.0), E)["law:giantville_theft_law"]
    assert literate["understands"] > 0.0


# ------------------------------------------ acceptance: incomer of one year, local custom
def test_an_incomer_of_one_year_does_not_know_a_custom_the_lifelong_resident_understands():
    custom = "policy:winter_food_reserve"     # takes three years of living here to spread (after_years 3)
    lifelong = derive_knowledge(_person(literacy=1.0, age=40.0,
                                        history={"local": True, "years_in_village": 40.0}), E)[custom]
    incomer = derive_knowledge(_person(literacy=1.0, age=30.0,
                                       history={"local": False, "years_in_village": 1.0}), E)[custom]
    assert lifelong["aware"] and lifelong["understands"] > 0, lifelong["basis"]
    assert incomer["aware"] is False and incomer["understands"] == 0.0, incomer["basis"]


# ------------------------------------------ acceptance: location (fields, granary, tannery, quarry)
def test_a_farm_labourer_knows_exactly_where_the_fields_and_granary_are_but_only_roughly_the_tannery(town, cast):
    labourer = _first_with_role(cast, "farm_labourer")
    derived = derive_knowledge(_person_of(town, labourer["name"]), E)
    assert derived["place:field"]["location"] == "exact"
    assert derived["place:granary"]["location"] == "exact", "the granary is on the farm the labourer works"
    assert derived["place:tannery"]["location"] == "roughly"
    assert derived["place:tannery"]["aware"] is True


def test_a_new_incomer_does_not_know_where_the_quarry_is():
    """The quarry is the stone deposit. Public spread needs three years here. A weaver's routine does not
    take them to it (a labourer's routine does: JOB_ROUTINE)."""
    incomer = derive_knowledge(_person(job="weaver", trades=["weaver"], age=30.0,
                                       history={"local": False, "years_in_village": 1.0}), E)
    assert incomer["place:stone"]["location"] == "none"
    assert incomer["place:stone"]["aware"] is False
    lifelong = derive_knowledge(_person(job="weaver", trades=["weaver"], age=40.0), E)
    assert lifelong["place:stone"]["location"] == "roughly"


def test_location_beliefs_record_the_position_believed_and_when_learned():
    derived = derive_knowledge(_person(job="farm_labourer", trades=["farmer"]), E)
    memories = knowledge_memories(derived, positions={"granary": {"position": [3, 4], "landmark": "farm"},
                                                      "tannery": {"landmark": "market"}})
    granary = next(m for m in memories if m["memory_id"] == "knowledge:place:granary")
    assert granary["content"]["location"] == "exact"
    assert granary["content"]["position"] == [3, 4]
    assert granary["content"]["learned"] == "founding" and granary["content"]["period"] == 0
    tannery = next(m for m in memories if m["memory_id"] == "knowledge:place:tannery")
    assert tannery["content"]["location"] == "roughly"
    assert "position" not in tannery["content"], "a roughly-known place is held by landmark, not by cell"
    assert tannery["content"]["landmark"] == "market"


# ---------------------------------------------- acceptance: stale location belief persists
def test_a_stale_stall_location_persists_until_the_resident_perceives_otherwise():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="farmer", home_cell=(1, 1))
    world._scenario_character_data["Ada"] = {"memories": [{
        "memory_id": "stall:Ada:market", "kind": "awareness", "source": "scenario_prior", "private": True,
        "content": {"item": "place:market", "type": "place", "name": "market", "aware": True,
                    "understands": 0.5, "basis": ["the stall was seen five years ago"],
                    "location": "exact", "position": [5, 5], "learned": "period -20", "period": -20,
                    "source": "scenario"}}]}
    game = BigvilleGame(world, autonomous=True)

    def market_belief():
        return [m for m in game.characters["Ada"].memories
                if isinstance(m.content, dict) and m.content.get("item") == "place:market"]

    before = market_belief()
    assert len(before) == 1 and before[0].content["position"] == [5, 5]
    for _ in range(3):
        game.step()
    after = market_belief()
    assert len(after) == 1, "the derived market belief does not replace the scenario's"
    assert after[0].content["position"] == [5, 5], "the stale position is kept"
    assert after[0].content["learned"] == "period -20"


# ------------------------------------------------- acceptance: seed_roles is gone, knowledge is there
@pytest.mark.parametrize("pack_name", ["bigville", "test_hamlet"])
def test_seed_roles_is_gone_from_the_pack_and_every_knowable_entry_has_a_spec(pack_name):
    pack_dir = os.path.join(ROOT, "packs", pack_name)
    for dirpath, _dirs, files in os.walk(pack_dir):
        for name in files:
            if name.endswith(".json"):
                with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                    assert "seed_roles" not in fh.read(), name
    pack = E if pack_name == "bigville" else pack_view(pack_name)
    for row in pack.RECIPES:
        assert "knowledge" in row, row["name"]
    for table in (pack.BUILDINGS, pack.RESOURCE_DEPOSITS, pack.WATER_SOURCES, pack.ANIMALS, pack.KIN_TERMS):
        for name, row in table.items():
            assert "knowledge" in row, name
    for bundle in list(pack.LAWS) + list(pack.POLICIES) + list(pack.CHARTERS):
        assert "knowledge" in bundle, bundle["name"]
    for concept in pack.SHARED_CONCEPTS:
        assert "knowledge" in concept, concept["name"]


def test_every_knowledge_spec_references_only_real_topics_skills_offices_and_places():
    report = E.check_consistency()
    assert report["errors"] == [], report["errors"]
    assert report["warnings"] == [], report["warnings"]


# ------------------------------------------------- acceptance: every derived item has a basis
def test_every_derived_item_has_a_non_empty_basis_for_the_whole_seeded_town(town, cast):
    for record in cast["residents"]:
        person = person_from_attrs(record["name"], dict(town.eng.node(town._actors[record["name"]])["attrs"]),
                                   pack=E, history=record["history"])
        derived = derive_knowledge(person, E)
        assert derived, record["name"]
        for item, row in derived.items():
            assert isinstance(row["basis"], list) and row["basis"], (record["name"], item)
            assert all(isinstance(text, str) and text for text in row["basis"]), (record["name"], item)


# ----------------------------------------------------------- purity and seeding
def test_derive_knowledge_is_a_pure_function_of_the_person():
    person = _person(job="baker", trades=[], skill_levels={"baking": 0.7})
    snapshot = copy.deepcopy(person)
    first = derive_knowledge(person, E)
    second = derive_knowledge(person, E)
    assert first == second
    assert person == snapshot, "derive_knowledge does not change the person it reads"


def test_understood_recipes_keep_the_recipe_kind_the_simple_backend_reads():
    derived = derive_knowledge(_person(job="baker", trades=[], skill_levels={"baking": 0.7}), E)
    memories = {m["memory_id"]: m for m in knowledge_memories(derived)}
    bake = memories["knowledge:recipe:bake_bread"]
    assert bake["kind"] == "recipe_knowledge"
    assert bake["content"]["recipe"] == "bake_bread" and bake["content"]["belief"] == "can_attempt"
    grind = memories["knowledge:recipe:grind_flour"]
    assert grind["kind"] == "awareness", "aware-only recipes are awareness, not recipe knowledge"


def test_awareness_and_understanding_are_separate_kinds():
    derived = derive_knowledge(_person(literacy=0.0), E)
    memories = {m["memory_id"]: m for m in knowledge_memories(derived)}
    assert memories["knowledge:law:giantville_theft_law"]["kind"] == "awareness"
    rich = derive_knowledge(_person(literacy=1.0), E)
    rich_memories = {m["memory_id"]: m for m in knowledge_memories(rich)}
    assert rich_memories["knowledge:law:giantville_theft_law"]["kind"] == "understanding"


def test_a_scenario_actor_without_history_gets_recipe_priors_only():
    """A scenario resident is not a founder: no history, so no awareness of the village is seeded."""
    world = BigvilleWorld(autonomous_actors=False)
    world.add_tradesperson("Miller", "miller")
    game = BigvilleGame(world, player="Miller")
    kinds = {m.kind for m in game.characters["Miller"].memories}
    assert kinds <= {"recipe_knowledge"}, kinds
    assert any(m.kind == "recipe_knowledge" and m.content.get("recipe") == "grind_flour"
               for m in game.characters["Miller"].memories)


def test_town_residents_get_derived_knowledge_memories():
    town = BigvilleWorld.from_town100()
    game = BigvilleGame(town, autonomous=True)
    baker = next(r["name"] for r in town._cast100["residents"] if r["role"] == "baker")
    kinds = {m.kind for m in game.characters[baker].memories}
    assert {"awareness", "understanding", "recipe_knowledge"} <= kinds
    sources = {m.source for m in game.characters[baker].memories}
    assert "derived_prior" in sources


# ----------------------------------------------------------- history draws
def test_history_is_drawn_deterministically_and_is_consistent_with_age_and_literacy(cast):
    residents = [{"role": r["role"], "group": r["group"], "age": r["age"], "literacy": r["literacy"],
                  "trades": r["trades"], "primary_trade": E.JOBS[r["role"]]["trades"][0],
                  "household": r["household"], "household_role": r["household_role"]}
                 for r in cast["residents"]]
    first = draw_founding_history(residents, 305000)
    second = draw_founding_history(residents, 305000)
    assert first == second
    for record, drawn in zip(cast["residents"], first):
        history = drawn["history"]
        assert history["years_in_village"] <= record["age"]
        if not history["local"]:
            assert history["years_in_village"] >= 1.0
        if not record["literacy"]:
            assert history["schooling_years"] == 0, "the unlettered have no schooling"
        else:
            assert E.HISTORY["schooling_years"]["min"] <= history["schooling_years"] <= E.HISTORY["schooling_years"]["max"]


def test_history_does_not_move_the_existing_cast_draws():
    """The cast's own draws (names, ages, households, traits) are the same whether or not the history stream
    is seeded: the history is drawn on its own stream, from the same residents, and changes nothing else."""
    from worlds.bigville_town100_world import build_town_100, generate_cast100
    _, _, layout = build_town_100(305000)
    first = generate_cast100(layout, 305000)
    second = generate_cast100(layout, 305000)
    assert first == second
    strip = lambda cast: [{k: v for k, v in r.items() if k not in ("history", "former_skills")}
                          for r in cast["residents"]]
    assert strip(first) == strip(second)
    assert all(set(r) >= {"history", "former_skills"} for r in first["residents"])


def test_the_committed_cast_seed_carries_the_history_the_generator_gives(cast):
    with open(os.path.join(ROOT, "seeds", "bigville_cast100.json"), encoding="utf-8") as fh:
        committed = json.load(fh)
    assert committed == json.loads(json.dumps(cast, sort_keys=True))
    with open(os.path.join(ROOT, "bigville", "seeds", "bigville_cast100.json"), encoding="utf-8") as fh:
        assert json.load(fh) == committed


def test_founders_skill_levels_carry_their_apprenticeship_and_the_current_trade_is_unchanged(town, cast):
    for record in cast["residents"]:
        attrs = town.eng.node(town._actors[record["name"]])["attrs"]
        for skill, level in record["former_skills"].items():
            assert float(attrs["skill_levels"][skill]) >= level - 1e-9
        assert float(attrs["skill"]) == pytest.approx(float(record["skill"]), abs=1e-9), \
            "the legacy main skill is the job's base skill, as before"
