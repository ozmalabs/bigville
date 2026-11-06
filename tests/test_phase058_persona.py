"""Phase 058: persona. Traits in words (not engine numbers), a life sketch from the founding history, a usual
day per job, founding ties (household, kin, workmates, neighbours, friends, rivals), and the persona card.

Founding ties are seeded explicitly (enabled=True) in these tests, whatever the bigville pack's default is.
The simple backend's behaviour is compared with the recorded before-change run (docs/phases/phase058).
"""
from __future__ import annotations

import collections
import copy
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import unittest.mock as mock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from domains import persona as P                          # noqa: E402
from domains import relationship_seeding as RS            # noqa: E402
from domains.lexicon import bands                         # noqa: E402
from domains.pack import load_pack                        # noqa: E402
from domains.persona_check import check_persona           # noqa: E402
from bigville.backends.cheap import DeterministicBackend  # noqa: E402
from worlds.bigville_world import BigvilleWorld           # noqa: E402

SEED = 305000
DIGIT = re.compile(r"\d")
PHASE_DIR = os.path.join(_ROOT, "docs", "phases", "phase058")
PERSONA_CLOSE = {"spouse", "blood_kin", "household", "friend", "feud"}


def _town(seed=SEED, enabled=True):
    """A founding town whose ties are seeded with `enabled` given explicitly, whatever the pack says."""
    real = RS.seed_founding_relationships

    def pinned(world, s, **kw):
        kw["enabled"] = enabled
        return real(world, s, **kw)

    with mock.patch.object(RS, "seed_founding_relationships", pinned):
        return BigvilleWorld.from_town100(seed=seed)


@pytest.fixture(scope="module")
def town():
    return _town(enabled=True)


@pytest.fixture(scope="module")
def unseeded():
    return _town(enabled=False)


@pytest.fixture(scope="module")
def game():
    from bigville.api import create_game
    real = RS.seed_founding_relationships

    def pinned(world, s, **kw):
        kw["enabled"] = True
        return real(world, s, **kw)

    with mock.patch.object(RS, "seed_founding_relationships", pinned):
        return create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                           ticks_per_period="world")


def _ties(world):
    """(holder, target) -> (kind, strength, history) for every held tie in the world."""
    out = {}
    for (holder, target), bond in world._relationships.items():
        attrs = world.eng.node(bond)["attrs"]
        out[(holder, target)] = (attrs.get("kind"), float(attrs.get("strength", 0.0)), attrs.get("history"))
    return out


def _cast(world):
    return world._cast100["residents"]


# ---------------------------------------------------------------------------------- traits in words

def test_traits_are_words_and_no_engine_parameter_is_among_them(town):
    engine = set(P.engine_parameter_names())
    record = _cast(town)[0]
    personality = dict(record["params"]) | {"role_identity": record["role_identity"]}
    own = P.traits(personality, {"role": record["role"]})
    assert set(own["self"]) <= set(P.trait_keys())
    assert not (set(own["self"]) & engine)
    assert set(own["self"]) == set(P.trait_keys()), "every trait with its source present has self words"
    for phrase in own["self"].values():
        assert not DIGIT.search(phrase), phrase


def test_every_personality_number_is_a_trait_or_an_engine_parameter():
    pack = load_pack("bigville")
    sources = {spec["source"] for k, spec in pack["PERSONA_TRAITS"].items()}
    engine = set(P.engine_parameter_names())
    for name in pack["FOUNDING_PERSONALITY"]:
        assert name in sources or name in engine, name
    for name in ("role_identity", "carried_weight", "emotional_core_enabled", "resolution_bins"):
        assert name in sources or name in engine, name
    assert not (sources & engine)


def test_others_see_only_what_an_observer_could_tell(town):
    seen_by_others = set()
    for record in _cast(town)[:20]:
        personality = dict(record["params"]) | {"role_identity": record["role_identity"]}
        seen_by_others |= set(P.traits(personality, {})["other"])
    assert seen_by_others <= {"charm", "temperament", "hostility", "arousal"}
    for key in ("trust", "spite", "outlook", "self_worth", "mood_bias", "role_identity"):
        spec = load_pack("bigville")["PERSONA_TRAITS"][key]
        assert bands(spec["quantity"], "other") == [], key


def test_the_persona_leaves_character_personality_as_it_was(game):
    name = next(iter(game.characters))
    character = game.characters[name]
    before = copy.deepcopy(character.personality)
    P.persona(character, game)
    game.persona(name)
    assert character.personality == before
    assert "w_supergraph" in character.personality and "charm_weight" in character.personality


# ---------------------------------------------------------------------------------- life sketch

def test_the_life_sketch_follows_the_founding_history(town):
    for record in _cast(town):
        history = record["history"]
        facts = P._facts_for(record["name"], town)
        sketch = " ".join(P.life_sketch(facts))
        assert ("were born in Bigville" in sketch) == bool(history["local"]), record["name"]
        assert ("came to Bigville" in sketch) == (not history["local"]), record["name"]
        assert ("were widowed" in sketch) == bool(history["widowed"]), record["name"]
        assert ("on the council" in sketch) == ("councillor" in history["past_offices"]), record["name"]
        assert ("at the trade of " + record["role"].replace("_", " ")) in sketch, record["name"]
        assert not DIGIT.search(sketch)


def test_the_life_sketch_is_the_same_for_the_same_seed():
    first, second = _town(), _town()
    for a, b in zip(_cast(first)[:25], _cast(second)[:25]):
        assert P.life_sketch(P._facts_for(a["name"], first)) == P.life_sketch(P._facts_for(b["name"], second))


def test_the_life_sketch_names_no_other_resident(town):
    names = [r["name"] for r in _cast(town)]
    for record in _cast(town)[:30]:
        sketch = " ".join(P.life_sketch(P._facts_for(record["name"], town)))
        others = [n for n in names if n != record["name"] and n in sketch]
        assert others == [], (record["name"], others)


def test_life_sketch_words_from_pure_facts():
    facts = {"stage": "adult", "job": "tailor", "local": False, "years_in_village": 4.0,
             "schooling_years": 6, "apprenticed": ["tailor"], "former_trades": [{"trade": "weaver", "years": 2.0}],
             "past_offices": ["mayor"], "married": True, "widowed": False, "household_role": "head"}
    sketch = P.life_sketch(facts)
    assert sketch[0] == "You are an adult."
    assert "You work at the trade of tailor." in sketch
    assert "You came to Bigville a few years ago." in sketch
    assert "You had a fair schooling." in sketch
    assert "You trained at the trade of tailor as an apprentice." in sketch
    assert "You also worked at the trade of weaver for a short while." in sketch
    assert "You have served as mayor." in sketch
    assert "You are married." in sketch and "You head your own household." in sketch


# ---------------------------------------------------------------------------------- usual day

def test_every_job_has_a_routine_and_the_day_is_six_blocks():
    pack = load_pack("bigville")
    for job in pack["JOBS"]:
        blocks = P.routine_blocks(job, "adult", pack="bigville")
        assert [b["block"] for b in sorted(blocks, key=lambda b: b["start"])] == \
            ["morning", "work", "midday", "afternoon", "evening", "sleep"], job
        for block in blocks:
            assert block["place"] in set(pack["JOB_ROUTINE"][job]) | {"home", "church", "school", "market"}, job


def test_the_routine_reproduces_the_simple_backends_four_bands_for_every_job():
    pack = load_pack("bigville")
    for job in pack["JOBS"]:
        by = {b["block"]: float(b["start"]) for b in P.routine_blocks(job, "adult", pack="bigville")}
        assert by["morning"] < 9.0 and by["work"] == 9.0 and by["evening"] == 17.0 and by["sleep"] == 21.0, job


def _old_band(hour):
    """cheap.py's _time_band before Phase 058 (kept here as the reference)."""
    if hour < 9:
        return "morning"
    if hour < 17:
        return "workday"
    if hour < 21:
        return "evening"
    return "night"


def test_the_simple_bands_equal_the_old_hour_bands_at_every_boundary_and_between():
    hours = [h / 8.0 for h in range(0, 24 * 8 + 1)] + [8.999, 9.0, 16.999, 17.0, 20.999, 21.0, 0.0, 23.999]
    for hour in hours:
        assert P.simple_band(hour) == _old_band(hour), hour
        assert DeterministicBackend._time_band(hour) == _old_band(hour), hour


def test_market_day_takes_a_market_job_to_the_market():
    market = P.routine_blocks("baker", "adult", weekday=5, pack="bigville")
    ordinary = P.routine_blocks("baker", "adult", weekday=0, pack="bigville")
    assert next(b for b in market if b["block"] == "afternoon")["place"] == "market"
    assert next(b for b in ordinary if b["block"] == "afternoon")["place"] == "bakery"


def test_church_day_turns_the_work_block_into_a_service():
    church = P.routine_blocks("smith", "adult", weekday=6, pack="bigville")
    work = next(b for b in church if b["start"] == 9.0)
    assert work["block"] == "midday" and work["place"] == "church"


def test_a_farm_season_changes_the_field_work():
    spring = next(b for b in P.routine_blocks("farmer", "adult", season="spring", pack="bigville")
                  if b["block"] == "work")
    winter = next(b for b in P.routine_blocks("farmer", "adult", season="winter", pack="bigville")
                  if b["block"] == "work")
    assert spring["task"] != winter["task"]
    smith = next(b for b in P.routine_blocks("smith", "adult", season="spring", pack="bigville")
                 if b["block"] == "work")
    assert smith["task"] == "shoeing horses and making iron tools"


def test_a_life_stage_has_its_own_day():
    elder = {b["block"]: b for b in P.routine_blocks("carpenter", "elder", pack="bigville")}
    assert elder["afternoon"]["place"] == "home"
    child = {b["block"]: b for b in P.routine_blocks("carpenter", "child", pack="bigville")}
    assert child["work"]["place"] == "school"


def test_the_usual_day_marks_the_block_for_the_hour():
    day = P.usual_day("farmer", "adult", hour=10.0, season="summer", weekday=1, pack="bigville")
    assert day["blocks"][day["now"]]["block"] == "work"
    assert day["sentences"][day["now"]].endswith("(at work)")
    night = P.usual_day("farmer", "adult", hour=23.0, pack="bigville")
    assert night["blocks"][night["now"]]["block"] == "sleep"


def test_nothing_in_the_world_reads_the_routine():
    for path in glob.glob(os.path.join(_ROOT, "worlds", "*.py")):
        text = open(path, encoding="utf-8").read()
        assert "domains.persona" not in text, path
        assert not re.search(r"(?<![A-Za-z_])ROUTINE(?![A-Za-z_])", text), path


# ---------------------------------------------------------------------------------- founding ties

def test_household_members_are_tied_to_each_other(town):
    ties = _ties(town)
    structural = {"spouse", "blood_kin"}
    for household in town._cast100["households"]:
        members = household["members"]
        for a in members:
            for b in members:
                if a == b:
                    continue
                assert (a, b) in ties, (a, b)
                kind = ties[(a, b)][0]
                assert kind == "household" or kind in structural, (a, b, kind)
                assert town.eng.node(town._relationships[(a, b)])["attrs"]["household"] == 1.0, (a, b)


def test_a_housemate_who_is_not_kin_is_tied_as_household():
    cfg = load_pack("bigville")["RELATIONSHIP_SEEDING"]
    trait = {"charm": 0.5, "trust": 0.5, "valence": 0.0, "spite": 0.0}
    people = [
        {"name": "Ada", "household": 1, "home": (1, 1), "work": (5, 5), "class": "middle", "age": 40.0,
         "years_in_village": 40.0, "traits": trait, "kin": []},
        {"name": "Ben", "household": 1, "home": (1, 1), "work": (9, 9), "class": "middle", "age": 30.0,
         "years_in_village": 30.0, "traits": trait, "kin": []},
    ]
    ties = {(t["holder"], t["target"]): t for t in RS.plan_ties(people, cfg, SEED)}
    assert ties[("Ada", "Ben")]["kind"] == "household" and ties[("Ada", "Ben")]["household"] is True
    assert ties[("Ben", "Ada")]["kind"] == "household"


def test_spouses_are_tied_as_spouses_both_ways(town):
    ties = _ties(town)
    spouse_pairs = 0
    for record in _cast(town):
        for row in town.kin_terms_held(record["name"]):
            if row["term"] == "spouse" and row["target"] in town._actors:
                spouse_pairs += 1
                assert ties[(record["name"], row["target"])][0] == "spouse"
                assert ties[(row["target"], record["name"])][0] == "spouse"
    assert spouse_pairs > 0


def test_parents_and_children_are_kin_both_ways(town):
    ties = _ties(town)
    checked = 0
    for record in _cast(town):
        for row in town.kin_terms_held(record["name"]):
            if row["term"] == "parent" and row["target"] in town._actors:
                checked += 1
                assert ties[(record["name"], row["target"])][0] == "blood_kin"
                assert ties[(row["target"], record["name"])][0] == "blood_kin"
    assert checked > 0


def test_each_resident_has_a_plausible_number_of_ties(town):
    counts = collections.Counter(h for h, _ in _ties(town))
    close = collections.Counter(h for (h, _), (kind, _, _) in _ties(town).items() if kind in PERSONA_CLOSE)
    totals = [counts.get(r["name"], 0) for r in _cast(town)]
    assert min(totals) >= 1
    assert 3 <= statistics.median(totals) <= 15
    assert max(totals) <= 25
    assert max(close.get(r["name"], 0) for r in _cast(town)) <= load_pack("bigville")["RELATIONSHIP_SEEDING"]["max_close_ties"]


def test_every_tie_kind_has_a_lexicon_phrase_and_strength_on_the_scale(town):
    kinds = {kind for kind, _, _ in _ties(town).values()}
    lexicon = {b["label"] for b in bands("relationship_kind", "self")}
    assert kinds <= lexicon, kinds - lexicon
    for kind, strength, history in _ties(town).values():
        assert history and not DIGIT.search(history) and "{term}" not in history
        if kind == "feud":
            assert -1.0 <= strength < 0.0
        else:
            assert 0.0 <= strength <= 10.0


def test_ties_are_directed_and_not_always_reciprocal(town):
    ties = _ties(town)
    one_way = [key for key in ties if (key[1], key[0]) not in ties]
    assert one_way, "a friend or rival can be named by one side only"


def test_seeding_is_reproducible_from_the_seed_and_changes_with_it():
    a, b = _ties(_town(seed=SEED)), _ties(_town(seed=SEED))
    assert sorted(a.items()) == sorted(b.items())
    c = _ties(_town(seed=SEED + 1))
    assert {k for k, v in a.items() if v[0] == "friend"} != {k for k, v in c.items() if v[0] == "friend"}


def test_seeding_leaves_the_founding_cast_and_the_residents_as_they_were(town, unseeded):
    assert town._cast100 == unseeded._cast100
    for name in town._actors:
        left = dict(town.eng.node(town._actors[name])["attrs"])
        right = dict(unseeded.eng.node(unseeded._actors[name])["attrs"])
        assert left == right, name


def test_disabled_seeding_writes_nothing(unseeded):
    assert unseeded._relationships == {}


def test_a_seeded_tie_carries_kind_strength_history_and_years(town):
    holder, target = next(iter(town._relationships))
    bond = town._relationships[(holder, target)]
    attrs = town.eng.node(bond)["attrs"]
    assert attrs["seeded"] == 1.0
    assert isinstance(attrs["history"], str) and attrs["history"]
    assert isinstance(attrs["years_known"], float)
    assert town.relationship(holder, target) == bond


# ---------------------------------------------------------------------------------- the persona card

def test_the_card_is_plain_strings_with_no_digits(game):
    for name in list(game.characters)[:100]:
        card = game.persona(name)
        assert tuple(card) == P.CARD_KEYS
        for key, value in card.items():
            assert isinstance(value, str), key
            assert not DIGIT.search(value), (name, key, value)


def test_the_card_lists_only_the_residents_own_ties(game):
    world = game.world
    for name in list(game.characters)[:40]:
        card = game.persona(name)
        held = [t for (h, t) in world._relationships if h == name]
        listed = [item.split(":")[0] for item in card["ties"].split("; ") if item]
        assert sorted(listed) == sorted(held), name


def test_the_game_method_equals_the_function(game):
    name = next(iter(game.characters))
    assert game.persona(name) == P.persona(game.characters[name], game)


def test_the_card_without_a_world_has_no_life_or_ties(game):
    character = game.characters[next(iter(game.characters))]
    card = P.persona(character, None)
    assert card["life"] == "" and card["ties"] == ""
    assert card["traits"] and card["usual_day"]


def test_the_card_for_the_same_seed_is_the_same():
    from bigville.api import create_game
    real = RS.seed_founding_relationships

    def pinned(world, s, **kw):
        kw["enabled"] = True
        return real(world, s, **kw)
    with mock.patch.object(RS, "seed_founding_relationships", pinned):
        g1 = create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                         ticks_per_period="world")
        g2 = create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                         ticks_per_period="world")
    for name in list(g1.characters)[:20]:
        assert g1.persona(name) == g2.persona(name), name


def test_the_card_names_the_clock_it_is_read_at(game):
    name = next(iter(game.characters))
    card = game.persona(name)
    assert card["usual_day"].startswith("Today is ") or "Right now:" in card["usual_day"]


def test_the_card_at_midnight_gives_the_sleep_block(game):
    """Hour 0.0 is a real hour (midnight), not a missing one: the card reads the sleep block."""
    name = next(iter(game.characters))
    world = game.world
    world.eng.set_attr(world._town, "hour", 0.0)
    try:
        card = game.persona(name)
    finally:
        world.eng.set_attr(world._town, "hour", 6.0)
    assert card["usual_day"].split("Right now: ")[1].endswith("(asleep).")


# ---------------------------------------------------------------------------------- packs and the self-test

def test_a_different_pack_gives_different_words_and_a_different_day():
    traits_big = P.traits({"charm_weight": 0.5}, {}, pack="bigville")["self"]["charm"]
    traits_ham = P.traits({"charm_weight": 0.5}, {}, pack="test_hamlet")["self"]["charm"]
    assert traits_big != traits_ham
    big = P.usual_day("baker", "adult", hour=10.0, weekday=2, pack="bigville")
    ham = P.usual_day("baker", "adult", hour=10.0, weekday=2, pack="test_hamlet")
    assert [b["place"] for b in big["blocks"]] != [b["place"] for b in ham["blocks"]]
    assert big["sentences"] != ham["sentences"]


def test_both_packs_pass_the_persona_checks():
    for pack in ("bigville", "test_hamlet"):
        errors, warnings, info = [], [], []
        check_persona(pack, errors, warnings, info)
        assert errors == [] and warnings == [], (pack, errors, warnings)


def test_the_entity_self_test_is_clean_with_the_persona_checks():
    from domains import bigville_entities as E
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []
    assert any("PERSONA (bigville): all persona checks pass" in line for line in report["info"])


def _copy_pack(tmp_path):
    dest = tmp_path / "bigville_copy"
    shutil.copytree(os.path.join(_ROOT, "packs", "bigville"), dest)
    return dest


def test_the_checks_reject_a_job_with_no_routine_row(tmp_path):
    dest = _copy_pack(tmp_path)
    path = dest / "world" / "persona.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["tables"]["ROUTINE"]["farmer"]
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, warnings, info = [], [], []
    check_persona(str(dest), errors, warnings, info)
    assert any("farmer" in e and "no row" in e for e in errors), errors


def test_the_checks_reject_a_routine_that_drifts_from_the_simple_bands(tmp_path):
    dest = _copy_pack(tmp_path)
    path = dest / "world" / "persona.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tables"]["ROUTINE_BANDS"]["morning_until"] = 8.0
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, warnings, info = [], [], []
    check_persona(str(dest), errors, warnings, info)
    assert any("morning_until" in e for e in errors), errors


def test_the_checks_reject_a_trait_with_no_band(tmp_path):
    dest = _copy_pack(tmp_path)
    path = dest / "world" / "persona.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tables"]["PERSONA_TRAITS"]["charm"]["quantity"] = "no_such_quantity"
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, warnings, info = [], [], []
    check_persona(str(dest), errors, warnings, info)
    assert any("charm" in e and "no_such_quantity" in e for e in errors), errors


# ---------------------------------------------------------------------------------- the simple backend

def test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns(tmp_path):
    """The before-change run (behaviour_before.json) and this run both use seed 305000, the simple backend
    for all residents, and no founding ties (seeding off). Five residents' action sequences and the mean
    hunger for the first 50 turns must match exactly."""
    before = json.load(open(os.path.join(PHASE_DIR, "behaviour_before.json"), encoding="utf-8"))
    out = tmp_path / "behaviour_check.json"
    env = dict(os.environ, PYTHONHASHSEED="0")
    script = os.path.join(PHASE_DIR, "measure_behaviour.py")
    subprocess.run([sys.executable, script, "--label", "check", "--turns", "50", "--seeding", "off",
                    "--out", str(out)], check=True, env=env, cwd=_ROOT, timeout=900)
    after = json.loads(out.read_text(encoding="utf-8"))
    for name, sequence in before["sample_sequences"].items():
        assert after["sample_sequences"][name] == sequence[:50], name
    assert after["hunger_mean_by_turn"] == before["hunger_mean_by_turn"][:50]
