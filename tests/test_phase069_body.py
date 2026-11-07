"""Phase 069: the body as a unit. Afferents (what a mind may feel), sounds with a rough place, the background feeling,
the felt agent view and its leak rule, the stub embodiment, and the checkpoint round trip.

Pure rules (resolve, the depth rule, the renderer) are tested on the pack's own tables through domains/interoception.
Views are built from a real founding town (scenario town100, seed 305000)."""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                  # noqa: E402
from domains import interoception as I                                # noqa: E402
from domains import interoception_check as IC                        # noqa: E402
from domains.agent_view_check import check_agent_view, felt_body_problems  # noqa: E402
from domains.pack import load_pack                                    # noqa: E402
from worlds import body as B                                          # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = "bigville"
TABLES = B.pack_tables(PACK)
RECORD = {"acuity": 1.0, "attention": 1.0, "impairment": 0.0}
NO_READS = {name: 0.0 for name in I.READS}


def _reads(**values):
    return {**NO_READS, **values}


def _derive(reads, record=None, tables=TABLES, turn=3, actor="Tester", previous=None):
    return I.derive(tables, reads, dict(RECORD if record is None else record), SEED, actor, turn, previous=previous)


def _row(derived, name):
    return next(row for row in derived["sources"] if row["source"] == name)


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


# ------------------------------------------------------------------ trees, resolve and the depth rule
def test_resolve_gives_the_ancestor_at_a_depth_and_the_node_when_deeper():
    anatomy = TABLES["anatomy"]
    assert I.depth_of(anatomy, "upper_belly") == 3
    assert I.resolve(anatomy, "upper_belly", 0) == "body"
    assert I.resolve(anatomy, "upper_belly", 1) == "torso"
    assert I.resolve(anatomy, "upper_belly", 2) == "front_torso"
    assert I.resolve(anatomy, "upper_belly", 9) == "upper_belly"
    assert I.resolve(anatomy, "upper_belly", -4) == "body"
    assert I.max_depth(anatomy) == 3 and I.max_depth(TABLES["quality_tree"]) == 2


def test_the_depth_rule_is_monotone_in_intensity_acuity_and_attention_and_falls_with_impairment():
    base = dict(intensity=0.4, acuity=1.0, attention=1.0, impairment=0.2)
    rules = TABLES["rules"]

    def raw(**change):
        args = {**base, **change}
        return I.raw_depth(rules, args["intensity"], args["acuity"], args["attention"], args["impairment"], 0.0)

    assert raw(intensity=0.9) >= raw(intensity=0.4)
    assert raw(acuity=1.3) >= raw(acuity=0.7)
    assert raw(attention=1.0) >= raw(attention=0.0)
    assert raw(impairment=0.8) <= raw(impairment=0.0)
    for low, high in ((0.0, 1.0), (0.2, 0.9)):
        assert I.chosen_depth(raw(intensity=high), 9, 9) >= I.chosen_depth(raw(intensity=low), 9, 9)


def test_a_resolution_is_never_shallower_when_only_its_strength_rises():
    for intensity in (0.0, 0.3, 0.6, 1.0):
        for acuity in (0.7, 1.0, 1.3):
            for attention in (0.0, 0.5, 1.0):
                weak = _derive(_reads(hunger=0.5 + 2.0 * intensity), {"acuity": acuity, "attention": attention,
                                                                       "impairment": 0.0})
                stronger = _derive(_reads(hunger=0.5 + 2.0 * min(1.0, intensity + 0.2)),
                                   {"acuity": acuity + 0.3, "attention": attention, "impairment": 0.0})
                a, b = _row(weak, "hunger"), _row(stronger, "hunger")
                assert b["quality_depth"] >= a["quality_depth"]
                assert b["locus_depth"] >= a["locus_depth"]


def test_impairment_and_distraction_never_resolve_deeper():
    fine = _row(_derive(_reads(hunger=2.0), {"acuity": 1.0, "attention": 1.0, "impairment": 0.0}), "hunger")
    drunk = _row(_derive(_reads(hunger=2.0), {"acuity": 1.0, "attention": 1.0, "impairment": 1.0}), "hunger")
    distracted = _row(_derive(_reads(hunger=2.0), {"acuity": 1.0, "attention": 0.0, "impairment": 0.0}), "hunger")
    for row in (drunk, distracted):
        assert row["quality_depth"] <= fine["quality_depth"]
        assert row["locus_depth"] <= fine["locus_depth"]


def test_a_visceral_place_is_capped_and_a_surface_place_is_not():
    rows = {name: dict(row) for name, row in TABLES["sources"].items() if not name.startswith("_")}
    rows["probe"] = dict(rows["chill"], locus="upper_belly", read="chill", channel="visceral")
    surface = copy.deepcopy(TABLES)
    surface["sources"] = {**rows, "probe": dict(rows["probe"], channel="surface")}
    deep = _derive(_reads(chill=1.0), {"acuity": 1.3, "attention": 1.0, "impairment": 0.0}, tables=surface)
    assert _row(deep, "probe")["locus_depth"] == 3                       # surface: fully resolved place
    visceral = copy.deepcopy(surface)
    visceral["sources"]["probe"]["channel"] = "visceral"
    shallow = _derive(_reads(chill=1.0), {"acuity": 1.3, "attention": 1.0, "impairment": 0.0}, tables=visceral)
    assert _row(shallow, "probe")["locus_depth"] == TABLES["channels"]["visceral"]["locus_cap"]
    assert _row(shallow, "probe")["locus_shown"] == "torso"


def test_a_hungry_and_an_exhausted_resident_share_a_shallow_sound_and_place_but_differ_in_truth():
    hungry = _derive(_reads(hunger=2.0))
    tired = _derive(_reads(exhaustion=1.0))
    h, t = _row(hungry, "hunger"), _row(tired, "exhaustion")
    assert h["quality_shown"] == t["quality_shown"] == "drained"
    assert h["locus_shown"] == t["locus_shown"] == "torso"
    assert I.normal_letters(h["sound"].split()[0]) == I.normal_letters(t["sound"].split()[0]) == "hn"
    assert h["quality_true"] != t["quality_true"] and h["locus_true"] != t["locus_true"]
    assert h["quality_depth"] == 1 and h["locus_depth"] == 1
    assert [s["where"] for s in hungry["signals"]] == ["torso"] == [s["where"] for s in tired["signals"]]


def test_a_sub_threshold_signal_is_absent_but_still_in_the_background_feeling():
    derived = _derive(_reads(hunger=0.6))                                  # intensity 0.05, awareness 0.15
    row = _row(derived, "hunger")
    assert row["intensity"] == pytest.approx(0.05) and row["felt"] is False
    assert derived["signals"] == []
    assert derived["feeling"] is not None and derived["feeling"]["level"] == "faint"


def test_no_signal_and_no_feeling_for_a_well_resident():
    derived = _derive(_reads())
    assert derived["signals"] == [] and derived["feeling"] is None
    assert all(row["intensity"] == 0.0 for row in derived["sources"])


def test_the_background_feeling_sums_every_source_and_is_capped():
    derived = _derive(_reads(hunger=2.5, harm=0.5, illness=1.0, intoxication=1.0))
    assert derived["total"] == 1.0
    assert I.normal_letters(derived["feeling"]["sound"]) in {"ugh", "urgh"}
    assert derived["feeling"]["level"] == "strong"


def test_the_same_inputs_give_the_same_sounds_and_a_different_pack_gives_different_ones(tmp_path):
    reads = _reads(hunger=2.0, harm=0.3, exhaustion=0.6)
    a, b = _derive(reads), _derive(reads)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    other = tmp_path / "other"
    shutil.copytree(os.path.join(_ROOT, "packs", PACK), other)
    path = other / "world" / "interoception.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tables"]["VOCALISATIONS"]["drained"]["forms"] = ["zorp"]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    alt = load_pack(str(other))
    tables = {"anatomy": alt["ANATOMY"], "quality_tree": alt["QUALITY_TREE"], "vocalisations": alt["VOCALISATIONS"],
              "channels": alt["CHANNELS"], "sources": alt["SIGNAL_SOURCES"], "patterns": alt["PATTERNS"],
              "feeling": alt["FEELING"], "rules": alt["INTEROCEPTION"]}
    shown = _row(_derive(reads, tables=tables), "exhaustion")["sound"].split()[0]
    assert I.normal_letters(shown) == "zorp"
    assert "zorp" not in _row(a, "exhaustion")["sound"]


def test_a_sound_is_a_form_with_stretched_vowels_and_a_pattern_and_never_a_cause():
    tail = I.stretch("ugh", 1.0, TABLES["rules"])
    assert tail == "uuuugh"
    assert I.normal_letters(I.sound(TABLES, "bad", 0.0, "steady", SEED)) in {"ugh", "urgh"}
    rendered = I.sound(TABLES, "visceral", 0.9, "waves", SEED)
    assert rendered.endswith("...") and rendered.count(" ") == 1
    assert I.normal_letters(rendered.split()[0]) in {I.normal_letters(f) for f in ("gurgle", "blech")}


def test_render_felt_body_words_only_the_sounds_and_places():
    felt = {"feeling": {"sound": "uugh", "level": "clear"}, "signals": [{"sound": "hnnn", "where": "torso"}]}
    assert I.render_felt_body(felt) == ["feeling: uugh (clear)", "  hnnn -- torso"]
    assert I.render_felt_body({"signals": []}) == []


# ------------------------------------------------------------------ the body object and the world
def test_a_body_is_built_for_every_resident_and_its_acuity_is_drawn_once(town):
    world = town.world
    for name in list(world._actors)[:5]:
        body = world.body_of(name)
        assert isinstance(body, B.WorldBackedBody)
        assert body.state["acuity"] == world.embodiment[name]["acuity"]
        assert body.state["embodiment"] == "human"
    again = create_game(scenario="town100", seed=SEED, player=PLAYER)
    assert again.world.embodiment[PLAYER]["acuity"] == world.embodiment[PLAYER]["acuity"]


def test_the_body_reads_the_world_and_moves_no_state(town):
    world = town.world
    before = json.dumps(world.embodiment, sort_keys=True)
    attrs_before = json.dumps(dict(world.eng.node(world._actors[PLAYER])["attrs"]), sort_keys=True, default=str)
    body = world.body_of(PLAYER)
    reads = body.reads()
    assert set(reads) == set(I.READS)
    assert body.capacities()["alive"] == 1.0
    assert json.dumps(dict(world.eng.node(world._actors[PLAYER])["attrs"]), sort_keys=True, default=str) == attrs_before
    assert json.dumps(world.embodiment, sort_keys=True) == before


def test_capacities_and_facts_are_the_world_values(town):
    world = town.world
    body = world.body_of(PLAYER)
    caps = body.capacities()
    assert caps["strength"] == round(float(world.effective_strength(PLAYER)), 4)
    assert caps["stamina"] == round(float(world.effective_stamina(PLAYER)), 4)
    assert body.facts() == {"asleep": world.asleep(PLAYER), "collapsed": world.collapsed(PLAYER)}


def test_the_felt_view_is_the_body_and_names_no_cause(town):
    world = town.world
    world.eng.set_attr(world._actors[PLAYER], "hunger", 2.2)
    view = town.agent_view(PLAYER)
    body = view["self"]["body"]
    assert set(body) <= set(load_pack(PACK)["INTEROCEPTION"]["felt_body_keys"])
    assert "hunger" not in body and "energy" not in body and "health" not in body and "ill" not in body
    assert body["signals"] and body["signals"][0]["where"] == "torso"
    assert felt_body_problems(body, PACK) == []
    labelled = town.agent_view(PLAYER, interoception="labelled")["self"]["body"]
    assert "hunger" in labelled and "signals" not in labelled


def test_the_referee_block_names_each_true_source_beside_the_felt_view(town):
    world = town.world
    world.eng.set_attr(world._actors[PLAYER], "hunger", 2.2)
    view = town.agent_view(PLAYER, mode="referee")
    inter = view["referee"]["interoception"]
    hunger = next(row for row in inter["sources"] if row["source"] == "hunger")
    assert hunger["felt"] and hunger["quality_true"] == "hunger" and hunger["locus_true"] == "upper_belly"
    assert hunger["quality_depth"] <= 1 and hunger["locus_depth"] <= 1
    assert "hunger" in view["self"]["body"] and "signals" not in view["self"]["body"]   # referee self.body is labelled


def test_the_leak_rule_holds_for_residents_in_many_states(town):
    world = town.world
    names = list(world._actors)[:12]
    states = [("hunger", 2.5), ("hunger", 0.9), ("disease", "fever"), ("hunger", 0.0)]
    for name in names:
        for attr, value in states:
            world.eng.set_attr(world._actors[name], attr, value)
            view = town.agent_view(name)
            assert felt_body_problems(view["self"]["body"], PACK) == [], name
            world.eng.set_attr(world._actors[name], attr, 0.0 if attr == "hunger" else "")


def test_the_felt_check_catches_a_cause_a_sound_and_a_place():
    good = {"feeling": {"sound": "uugh", "level": "clear"}, "signals": [{"sound": "hnnn", "where": "torso"}]}
    assert felt_body_problems(good, PACK) == []
    assert felt_body_problems({"hunger": "not hungry", "signals": []}, PACK)
    assert felt_body_problems({"signals": [{"sound": "I am hungry", "where": "torso"}]}, PACK)
    assert felt_body_problems({"signals": [{"sound": "hnnn", "where": "left elbow"}]}, PACK)
    assert felt_body_problems({"signals": [{"sound": "hnnn", "where": "torso"}], "energy": "fresh"}, PACK)
    assert felt_body_problems({"feeling": {"sound": "ugh 3", "level": "faint"}, "signals": []}, PACK)


def test_the_labelled_mode_keeps_the_old_words(town):
    body = town.agent_view(PLAYER, interoception="labelled")["self"]["body"]
    assert "energy" in body and "strength" in body and "signals" not in body


def test_the_stub_embodiment_works_with_no_change_outside_the_body(town, monkeypatch):
    stub_tables = {
        "anatomy": {"root": {"parent": None, "label": "everywhere"}, "hand": {"parent": "root", "label": "hand"},
                    "finger": {"parent": "hand", "label": "finger"}},
        "quality_tree": {"ok": {"parent": None}, "itch": {"parent": "ok"}, "sting": {"parent": "itch"}},
        "vocalisations": {"ok": {"forms": ["mmm"]}, "itch": {"forms": ["tsk"]}, "sting": {"forms": ["ouch"]}},
        "channels": {"skin": {"quality_cap": 2, "locus_cap": 2}},
        "sources": {"midge": {"read": "itch", "floor": 0.0, "ceiling": 1.0, "channel": "skin", "quality": "sting",
                              "locus": "finger", "pattern": "steady", "awareness": 0.1},
                    "bruise": {"read": "harm", "floor": 0.0, "ceiling": 1.0, "channel": "skin", "quality": "itch",
                               "locus": "hand", "pattern": "steady", "awareness": 0.1}},
        "patterns": TABLES["patterns"], "feeling": TABLES["feeling"], "rules": TABLES["rules"],
    }

    class StubBody(B.Body):
        kind = "stub"

        def __init__(self, state, *, world, actor):
            super().__init__(state, tables=stub_tables, world=world, actor=actor)

        def reads(self):
            return {"itch": 1.0, "harm": 0.5}

    monkeypatch.setitem(B.EMBODIMENTS, "stub", StubBody)
    world = town.world
    name = PLAYER
    world.embodiment[name] = StubBody.initial_state(world, name, "adult")
    world.embodiment[name]["embodiment"] = "stub"
    body = world.body_of(name)
    assert isinstance(body, StubBody)
    felt = body.afferents()
    assert felt["signals"] and {s["where"] for s in felt["signals"]} <= {"everywhere", "hand", "finger"}
    view = town.agent_view(name)
    stub_view = dict(felt)
    assert felt_body_problems(stub_view, PACK, anatomy=stub_tables["anatomy"],
                              vocalisations=stub_tables["vocalisations"]) == []
    assert "strength" not in view["self"]["body"]                       # the stub has no capacities
    world.embodiment[name] = B.WorldBackedBody.initial_state(world, name, "adult")
    assert world.body_of(name).kind == "human"


def test_the_body_round_trips_through_dump_and_load_with_history(town):
    world = town.world
    body = world.body_of(PLAYER)
    world.eng.set_attr(world._actors[PLAYER], "hunger", 1.6)
    body.tick()
    world.eng.set_attr(world._actors[PLAYER], "hunger", 2.1)
    body.tick()
    state = body.dump()
    assert state["previous"] is not None
    encoded = json.dumps(state, sort_keys=True, allow_nan=False)
    restored = B.WorldBackedBody.load(json.loads(encoded), world=world, actor=PLAYER)
    assert restored.dump() == state
    assert restored.afferents() == body.afferents()
    assert restored.referee() == body.referee()


def test_body_events_are_validated():
    body = B.Body({"seed": 1, "acuity": 1.0, "previous": None, "embodiment": "x"}, tables=TABLES)
    assert body.apply({"kind": "harm", "amount": 0.1, "cause": "injury"}) is None
    with pytest.raises(ValueError):
        body.apply({"kind": "teleport"})


# ------------------------------------------------------------------ the self-test
class _Pack(dict):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name


def _checked(mutate):
    base = load_pack(PACK)
    data = {name: copy.deepcopy(base[name]) for name in IC.REQUIRED + ("LIFE_STAGES",)}
    mutate(data)
    errors = []
    original = IC.load_pack
    IC.load_pack = lambda name: _Pack(data, name)
    try:
        IC.check_interoception(PACK, errors, [], [])
    finally:
        IC.load_pack = original
    return errors


def test_the_self_test_passes_on_both_packs():
    for pack in (PACK, "test_hamlet"):
        errors, info = [], []
        IC.check_interoception(pack, errors, [], info)
        assert errors == [] and info


def test_the_self_test_finds_an_unreachable_node():
    def orphan(data):
        data["ANATOMY"]["lost"] = {"parent": "nowhere", "label": "lost"}
    assert any("nowhere" in e for e in _checked(orphan))


def test_the_self_test_finds_a_source_with_a_missing_quality_or_locus():
    def missing_quality(data):
        data["SIGNAL_SOURCES"]["hunger"]["quality"] = "no_such_feeling"
    def missing_locus(data):
        data["SIGNAL_SOURCES"]["hunger"]["locus"] = "no_such_place"
    assert any("no_such_feeling" in e for e in _checked(missing_quality))
    assert any("no_such_place" in e for e in _checked(missing_locus))


def test_the_self_test_finds_a_quality_with_no_vocalisation():
    def silent(data):
        del data["VOCALISATIONS"]["queasy"]
    assert any("queasy" in e and "VOCALISATIONS" in e for e in _checked(silent))


def test_the_self_test_finds_a_depth_cap_deeper_than_its_tree():
    def deep(data):
        data["CHANNELS"]["visceral"]["quality_cap"] = 5
    assert any("deeper than QUALITY_TREE" in e for e in _checked(deep))


def test_the_self_test_finds_a_read_the_body_does_not_compute():
    def unknown_read(data):
        data["SIGNAL_SOURCES"]["hunger"]["read"] = "mood"
    assert any("mood" in e for e in _checked(unknown_read))


def test_the_agent_view_self_test_passes_with_the_felt_sections():
    errors, info = [], []
    check_agent_view(PACK, errors, [], info)
    assert errors == []


def test_the_felt_keys_are_whitelisted_in_the_agent_view():
    whitelist = set(load_pack(PACK)["AGENT_VIEW_WHITELIST"]["body"])
    assert set(load_pack(PACK)["INTEROCEPTION"]["felt_body_keys"]) <= whitelist
