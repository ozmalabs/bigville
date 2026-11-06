"""Phase 051: the words for numbers and statuses (packs' LEXICON_* tables read by domains/lexicon.py).

Covers: band tables are complete, monotone and unambiguous; labels round-trip through value_for; describe
never puts a number in its words; perspectives differ and hidden quantities have no other phrase; status
keys and the 'unknown' fallback; reverse words; a second pack changes the words with no code change; the
observation payload's numeric fields are each covered by the registry; the self-test checks pass, and
they reject a broken table.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from domains import lexicon as L                      # noqa: E402
from domains.lexicon_check import check_lexicon       # noqa: E402
from domains.pack import load_pack                    # noqa: E402

DIGIT = re.compile(r"\d")
NUMERIC = [q for q in L.quantities() if L._quantity(q, "bigville")["kind"] == "numeric"]
STATUS = [q for q in L.quantities() if L._quantity(q, "bigville")["kind"] == "status"]


def _numeric_tables():
    """(quantity, perspective) for each numeric band table of the default pack, aliases skipped."""
    out = []
    raw = load_pack("bigville")["LEXICON_QUANTITIES"]
    for name, spec in raw.items():
        if "alias" in spec or spec.get("kind") != "numeric":
            continue
        for persp in ("self", "other"):
            if persp in spec:
                out.append((name, persp))
    return out


def _grid(lo, hi, steps=400):
    return [lo + (hi - lo) * i / steps for i in range(steps + 1)]


# ------------------------------------------------------------------ band tables

@pytest.mark.parametrize("quantity,persp", _numeric_tables())
def test_band_table_is_complete_monotone_and_unambiguous(quantity, persp):
    bands = L.bands(quantity, persp)
    lo, hi = load_pack("bigville")["LEXICON_QUANTITIES"][quantity]["range"]
    assert bands[0]["min"] == float(lo)
    assert bands[-1]["max"] == float(hi)
    for a, b in zip(bands, bands[1:]):
        assert a["max"] == b["min"], (quantity, persp, a, b)      # contiguous: no gap, no overlap
        assert a["min"] < a["max"]
    labels = [b["label"] for b in bands]
    assert len(set(labels)) == len(labels), (quantity, persp)


@pytest.mark.parametrize("quantity,persp", _numeric_tables())
def test_every_band_is_reached_and_lookup_is_monotone(quantity, persp):
    bands = L.bands(quantity, persp)
    index = {b["label"]: i for i, b in enumerate(bands)}
    lo, hi = bands[0]["min"], bands[-1]["max"]
    seen_order = []
    for v in _grid(lo - 5.0, hi + 5.0):                       # includes values outside the range
        got = L.describe(quantity, v, persp, what="smithing")["label"]
        seen_order.append(index[got])
    assert seen_order == sorted(seen_order), "lookup must not step back as the value rises"
    assert set(seen_order) == set(range(len(bands))), "every band must be reachable"


@pytest.mark.parametrize("quantity,persp", _numeric_tables())
def test_label_round_trips_through_value_for(quantity, persp):
    for band in L.bands(quantity, persp):
        v = L.value_for(quantity, band["label"], persp)
        assert band["min"] <= v <= band["max"]
        assert L.describe(quantity, v, persp, what="smithing")["label"] == band["label"]


def test_describe_clamps_outside_the_range():
    lo = L.bands("energy")[0]
    hi = L.bands("energy")[-1]
    assert L.describe("energy", -50.0) == L.describe("energy", lo["min"])
    assert L.describe("energy", 500.0) == L.describe("energy", hi["max"])


def test_describe_rejects_non_numbers_and_nan():
    with pytest.raises(TypeError):
        L.describe("energy", True)
    with pytest.raises(TypeError):
        L.describe("energy", "lots")
    with pytest.raises(ValueError):
        L.describe("energy", float("nan"))


# ------------------------------------------------------------------ words

def test_no_digits_in_any_word_of_any_quantity():
    for quantity in L.quantities():
        for persp in ("self", "other"):
            for band in L.bands(quantity, persp):
                assert not DIGIT.search(band["label"]), (quantity, persp, band)
                assert not DIGIT.search(band["phrase"]), (quantity, persp, band)
    for quantity in NUMERIC:
        for persp in ("self", "other"):
            if not L.bands(quantity, persp):
                continue
            for band in L.bands(quantity, persp):
                out = L.describe(quantity, band["min"], persp, what="smithing")
                if out is not None:
                    assert not DIGIT.search(out["phrase"]), (quantity, persp, out)


def test_describe_returns_label_and_phrase_only():
    out = L.describe("hunger", 1.5)
    assert set(out) == {"label", "phrase"}
    assert out == {"label": "hungry", "phrase": "hungry"}


def test_a_template_phrase_needs_the_named_skill():
    assert L.describe("skill", 0.5, what="smithing") == {"label": "competent", "phrase": "competent at smithing"}
    assert L.describe("trade", 0.9, what="smithing") == {"label": "master", "phrase": "a master of smithing"}
    with pytest.raises(ValueError):
        L.describe("skill", 0.5)


# ------------------------------------------------------------------ perspectives

def test_hunger_is_felt_by_self_and_only_seen_as_gauntness_by_others():
    assert L.describe("hunger", 2.5, "self") == {"label": "famished", "phrase": "famished"}
    assert L.describe("hunger", 2.5, "other") == {"label": "gaunt", "phrase": "looks gaunt"}
    assert L.describe("hunger", 0.5, "other") == {"label": "well_fed", "phrase": "looks well fed"}
    assert L.describe("hunger", 0.5, "self")["phrase"] == "not hungry"


def test_a_hidden_quantity_has_no_other_phrase():
    for quantity in ("stamina", "skill", "trade", "deficiency", "trust", "spite", "outlook"):
        for value in (0.0, 0.5, 1.0):
            assert L.describe(quantity, value, "other", what="smithing") is None, quantity
    assert L.describe("relationship_kind", "friend", "other") is None


def test_a_visible_quantity_has_an_other_phrase():
    assert L.describe("strength", 1.5, "other") == {"label": "strong", "phrase": "looks strong"}
    assert L.describe("strength", 0.2, "other")["phrase"] == "looks slight"


def test_finery_is_only_seen_on_another():
    assert L.describe("finery", 4.0, "self") is None
    assert L.describe("finery", 4.0, "other")["phrase"] == "smartly dressed"


def test_self_and_other_words_differ_for_a_visible_quantity():
    assert L.describe("energy", 50.0, "self")["phrase"] == "tired"
    assert L.describe("energy", 50.0, "other")["phrase"] == "looks fresh"
    assert L.describe("energy", 10.0, "self")["phrase"] == "exhausted"
    assert L.describe("energy", 10.0, "other")["phrase"] == "looks exhausted"


# ------------------------------------------------------------------ statuses

def test_status_keys_match_their_source_tables_and_fall_back_to_unknown():
    pack = load_pack("bigville")
    for quantity, table in (("health_status", "HEALTH_CONDITIONS"), ("season", "SEASONS"),
                            ("weather", "WEATHER"), ("life_stage", "LIFE_STAGES")):
        keys = {b["label"] for b in L.bands(quantity, "self")} - {"unknown"}
        assert keys == set(pack[table]), quantity
        assert L.describe(quantity, "no_such_key")["label"] == "unknown", quantity


def test_health_status_words_and_observer_view():
    assert L.describe("health_status", "healthy") == {"label": "healthy", "phrase": "in good health"}
    assert L.describe("health_status", "injured", "other")["phrase"] == "looks hurt"
    assert L.describe("health_status", "malnourished", "other")["phrase"] == "looks gaunt"
    assert L.describe("health_status", "unknown", "other") is None


def test_season_and_weather_are_shared_by_both_perspectives():
    assert L.describe("season", "winter", "other") == L.describe("season", "winter", "self")
    assert L.describe("weather", "frost", "other")["phrase"] == "frosty"


def test_relationship_strength_bands_follow_the_bond_codes():
    assert L.describe("relationship_strength", 0.0)["label"] == "stranger"
    assert L.describe("relationship_strength", 0.5)["label"] == "acquaintance"
    assert L.describe("relationship_strength", 1.5)["label"] == "friend"
    assert L.describe("relationship_strength", 3.0)["label"] == "intimate"
    assert L.describe("relationship_strength", 5.0)["label"] == "family"


def test_energy_bands_use_the_exhaustion_steps():
    assert L.describe("energy", 4.9)["label"] == "spent"
    assert L.describe("energy", 5.0)["label"] == "exhausted"
    assert L.describe("energy", 15.0)["label"] == "worn_out"
    assert L.describe("energy", 40.0)["label"] == "tired"
    assert L.describe("energy", 70.0)["label"] == "fresh"


# ------------------------------------------------------------------ reverse words

def test_intensity_words_resolve_and_numbers_pass_through():
    assert L.intensity_value("hard") == 1.5
    assert L.intensity_value("Hard ") == 1.5
    assert L.intensity_value("normally") == 1.0
    assert L.intensity_value("with all your strength") == 2.0
    assert L.intensity_value(1.2) == 1.2
    assert L.intensity_value("0.8") == 0.8
    with pytest.raises(ValueError):
        L.intensity_value("sideways")
    with pytest.raises(TypeError):
        L.intensity_value(True)


def test_amount_words_resolve_to_bands_they_name():
    assert L.amount_value("a few") == 3.0
    assert L.amount_value(7) == 7.0
    pack = load_pack("bigville")
    for word in pack["AMOUNT_WORDS"]:
        out = L.describe("amount", L.amount_value(word))
        assert out["phrase"] == word, word


def test_verb_aliases_resolve_to_one_canonical_verb():
    assert L.resolve_verb("smash") == "smash"
    assert L.resolve_verb("bash") == "smash"
    assert L.resolve_verb("break") == "smash"
    assert L.resolve_verb("batter") == "smash"
    assert L.resolve_verb("Throw") == "throw"
    assert L.resolve_verb("toss") == "throw"
    assert L.resolve_verb("dance a jig") is None


def test_every_canonical_verb_maps_to_itself():
    pack = load_pack("bigville")
    for word, verb in pack["VERB_ALIASES"].items():
        assert pack["VERB_ALIASES"].get(verb, verb) == verb, (word, verb)


# ------------------------------------------------------------------ pack swap

def test_a_different_pack_gives_different_words_with_no_code_change():
    assert L.describe("energy", 50.0)["phrase"] == "tired"
    assert L.describe("energy", 50.0, pack="test_hamlet")["phrase"] == "weary"
    assert L.describe("hunger", 1.2)["label"] == "hungry"
    assert L.describe("hunger", 1.2, pack="test_hamlet")["label"] == "peckish"
    assert L.intensity_value("hard") == 1.5
    assert L.intensity_value("hard", pack="test_hamlet") == 1.8
    assert L.resolve_verb("bash", pack="test_hamlet") == "smash"
    assert L.resolve_verb("lug", pack="test_hamlet") == "carry"


def test_the_smaller_pack_lacks_quantities_it_does_not_name():
    # Phase 058 changed this: test_hamlet now names the persona quantities too (traits, the day blocks, life
    # stage, season, tie kinds and strengths), so its persona card can be built. It still lacks the rest.
    assert set(L.quantities(pack="test_hamlet")) == {
        "energy", "hunger", "hour", "arousal", "charm", "day_block", "hostility", "life_stage", "mood_bias",
        "outlook", "relationship_kind", "relationship_strength", "role_identity", "season", "self_worth",
        "spite", "temperament", "trust"}
    with pytest.raises(KeyError):
        L.describe("health_status", "healthy", pack="test_hamlet")


def test_default_pack_is_bigville():
    assert L.describe("hour", 6.0) == L.describe("hour", 6.0, pack="bigville")
    assert L.DEFAULT_PACK == "bigville"


def test_value_for_rejects_an_unknown_label():
    with pytest.raises(KeyError):
        L.value_for("energy", "no_such_band")
    with pytest.raises(KeyError):
        L.value_for("stamina", "winded_easily", "other")


# ------------------------------------------------------------------ payload coverage

def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        if value:
            yield from _leaves(value[0], f"{path}[0]")
    else:
        yield path, value


def _matches(pattern, path):
    p, q = pattern.split("."), path.split(".")
    return len(p) == len(q) and all(a == "*" or a == b for a, b in zip(p, q))


def test_every_numeric_field_of_a_resident_observation_is_in_the_payload_registry():
    from bigville import create_game
    game = create_game(scenario="town100", default_backend="simple")
    payload = load_pack("bigville")["LEXICON_PAYLOAD"]
    names = list(game.characters)[:5]
    missing = set()
    for name in names:
        observations = game._context(name).observations
        for path, value in _leaves(observations):
            norm = re.sub(r"\[\d+\]", "[]", path)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if not any(_matches(pattern, norm) for pattern in payload):
                missing.add(norm)
    assert not missing, sorted(missing)
    for field in ("health", "calendar.season", "calendar.weather", "energy", "hunger", "calendar.hour"):
        assert field in payload, field


# ------------------------------------------------------------------ self-test checks

@pytest.mark.parametrize("pack", ["bigville", "test_hamlet"])
def test_lexicon_self_checks_pass_for_each_pack(pack):
    errors, warnings, info = [], [], []
    check_lexicon(pack, errors, warnings, info)
    assert errors == [] and warnings == [], (errors, warnings)
    assert any("all checks pass" in line for line in info), info


def _copy_pack(tmp_path):
    dest = os.path.join(str(tmp_path), "broken_pack")
    shutil.copytree(os.path.join(_ROOT, "packs", "bigville"), dest)
    return dest


def _edit_lexicon(pack_dir, edit):
    path = os.path.join(pack_dir, "world", "lexicon.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    edit(data["tables"])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def test_the_checks_reject_a_band_table_that_does_not_start_at_the_range_low(tmp_path):
    pack_dir = _copy_pack(tmp_path)

    def edit(tables):
        tables["LEXICON_QUANTITIES"]["energy"]["self"][0]["min"] = 1.0

    _edit_lexicon(pack_dir, edit)
    errors, warnings = [], []
    check_lexicon(pack_dir, errors, warnings, [])
    assert any("first band starts at 1.0" in e for e in errors), errors


def test_the_checks_reject_a_repeated_label_a_missing_unknown_and_a_digit_in_a_phrase(tmp_path):
    pack_dir = _copy_pack(tmp_path)

    def edit(tables):
        q = tables["LEXICON_QUANTITIES"]
        q["hunger"]["self"][1]["label"] = "not_hungry"
        del q["health_status"]["self"]["unknown"]
        q["stamina"]["self"][0]["phrase"] = "you have 2 breaths"

    _edit_lexicon(pack_dir, edit)
    errors = []
    check_lexicon(pack_dir, errors, [], [])
    text = "\n".join(errors)
    assert "label 'not_hungry' appears twice" in text, text
    assert "needs the 'unknown' fallback" in text, text
    assert "must not contain a number" in text, text


def test_the_checks_reject_a_threshold_that_drifts_from_its_source(tmp_path):
    pack_dir = _copy_pack(tmp_path)

    def edit(tables):
        bands = tables["LEXICON_QUANTITIES"]["energy"]["self"]
        for band in bands:
            if band["label"] == "exhausted":
                band["min"] = 6.0

    _edit_lexicon(pack_dir, edit)
    errors = []
    check_lexicon(pack_dir, errors, [], [])
    assert any("no band starts at 5.0 (EXHAUSTION.e_collapse" in e for e in errors), errors


def test_the_checks_reject_a_reverse_word_that_names_nothing(tmp_path):
    pack_dir = _copy_pack(tmp_path)

    def edit(tables):
        tables["VERB_ALIASES"]["smash"] = "bash"
        tables["INTENSITY_WORDS"]["hard"] = "very"

    _edit_lexicon(pack_dir, edit)
    errors = []
    check_lexicon(pack_dir, errors, [], [])
    text = "\n".join(errors)
    assert "'smash' is a canonical verb, but it maps to 'bash'" in text, text
    assert "INTENSITY_WORDS[hard]: must map to a finite number" in text, text


def test_a_child_pack_that_moves_a_source_edge_gets_a_warning_not_an_error(tmp_path):
    child = os.path.join(str(tmp_path), "lex_child")
    os.makedirs(os.path.join(child, "world"))
    time = dict(load_pack("bigville")["TIME"])
    time["minutes_per_tick"] = 7.5
    with open(os.path.join(child, "world", "time_child.json"), "w", encoding="utf-8") as fh:
        json.dump({"_doc": "", "_types": {}, "tables": {"TIME": time}}, fh)
    with open(os.path.join(child, "pack.json"), "w", encoding="utf-8") as fh:
        json.dump({"format": 1, "name": "lex_child", "version": 1, "extends": "bigville",
                   "tables": [{"name": "TIME", "file": "world/time_child.json"}]}, fh)
    errors, warnings = [], []
    check_lexicon(child, errors, warnings, [])
    assert errors == [], errors
    assert any("no band starts at 7.5 (TIME.minutes_per_tick)" in w for w in warnings), warnings


def test_the_entity_self_test_runs_the_lexicon_checks_and_is_clean():
    from domains import bigville_entities as E
    report = E.check_consistency()
    assert report["errors"] == [], report["errors"]
    assert report["warnings"] == [], report["warnings"]
    assert any("LEXICON (bigville)" in line for line in report["info"])
