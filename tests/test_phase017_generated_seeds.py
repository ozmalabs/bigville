"""Phase 017: Ocelot seeds generated from the data pack (tools/generate_seeds.py, domains/generated_seeds.py)."""
import importlib.util
import json
import os
import shutil

import pytest

from domains import bigville_entities as E
from domains import generated_seeds as G
from domains.pack import PackError, load_pack

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_SEEDS = os.path.join(ROOT, "seeds")
CANONICAL = G.CANONICAL_SEED_DIR
GENERATED_KEYS = {"id", "version", "description", "depends_on", "nodes", "edges", "concepts", "rules",
                  "generated_from", "self_load_only"}
LAW = "commons_and_land_law"
LAW_FILE = f"gen_law_{LAW}.json"
# bigville_actor_decision.json differs between seeds/ and bigville/seeds/; the supervisor decides it.
PENDING_DECISION = {"bigville_actor_decision.json"}


def _child(tmp_path, tables, name="phase017_child"):
    """A child pack that extends bigville. `tables` maps a table name to its replacement value."""
    root = tmp_path / name
    (root / "world").mkdir(parents=True)
    entries = []
    for table, value in tables.items():
        rel = f"world/{table.lower()}.json"
        (root / rel).write_text(json.dumps({"_doc": "phase 017 test child", "_types": {},
                                            "tables": {table: value}}), encoding="utf-8")
        entries.append({"name": table, "file": rel})
    (root / "pack.json").write_text(json.dumps({
        "format": 1, "name": name, "version": 1, "description": "phase 017 test child of bigville",
        "extends": "bigville", "tables": entries}), encoding="utf-8")
    return str(root)


def _read_dir(path):
    return {name: open(os.path.join(path, name), "rb").read() for name in sorted(os.listdir(path))}


def _base(table):
    return json.loads(json.dumps(load_pack("bigville")[table]))


def _edited_local_laws():
    laws = _base("LOCAL_LAWS")
    law = next(entry for entry in laws if entry["name"] == LAW)
    law["title"] = "Commons and Land Ordinance (amended)"
    law["concepts"][0]["reference"]["object"] = "village_common_land"
    return laws


def test_regenerating_is_byte_identical(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    G.write_seeds(load_pack("bigville"), str(first))
    G.write_seeds(load_pack("bigville"), str(second))
    assert _read_dir(first) == _read_dir(second)
    assert len(os.listdir(first)) == len(G.expected_files(load_pack("bigville"))) == 31


def test_the_committed_seeds_are_what_the_pack_produces():
    assert G.check_seeds(load_pack("bigville"), CANONICAL) == []
    for name, text in G.expected_files(load_pack("bigville")).items():
        assert open(os.path.join(CANONICAL, name), encoding="utf-8").read() == text, name


def test_editing_one_law_in_a_child_pack_changes_only_that_law_seed(tmp_path):
    unedited, edited = tmp_path / "unedited", tmp_path / "edited"
    G.write_seeds(load_pack(_child(tmp_path / "a", {"LOCAL_LAWS": _base("LOCAL_LAWS")})), str(unedited))
    G.write_seeds(load_pack(_child(tmp_path / "b", {"LOCAL_LAWS": _edited_local_laws()})), str(edited))
    before, after = _read_dir(unedited), _read_dir(edited)
    assert sorted(before) == sorted(after)
    assert sorted(name for name in before if before[name] != after[name]) == [LAW_FILE]
    seed = json.loads(after[LAW_FILE])
    assert seed["description"].startswith("Commons and Land Ordinance (amended) (law")
    assert seed["concepts"][0]["definition"] == "commons belongs_to village_common_land"
    assert seed["generated_from"]["pack"] == "phase017_child"


def test_the_staleness_check_catches_an_unregenerated_edit(tmp_path, monkeypatch):
    out = tmp_path / "out"
    unedited = load_pack(_child(tmp_path / "a", {"LOCAL_LAWS": _base("LOCAL_LAWS")}))
    edited = load_pack(_child(tmp_path / "b", {"LOCAL_LAWS": _edited_local_laws()}))
    G.write_seeds(unedited, str(out))
    assert G.check_seeds(unedited, str(out)) == []

    problems = G.check_seeds(edited, str(out))
    assert len(problems) == 1 and problems[0].startswith(f"{LAW_FILE}: stale"), problems

    G.write_seeds(edited, str(out))
    assert G.check_seeds(edited, str(out)) == []

    # A seed file edited by hand, with the pack unchanged, is stale too.
    path = out / LAW_FILE
    path.write_text(path.read_text(encoding="utf-8").replace("village", "hamlet", 1), encoding="utf-8")
    assert [p.split(":")[0] for p in G.check_seeds(edited, str(out))] == [LAW_FILE]

    # The self-test reports the same kind of edit in the canonical directory.
    copied = tmp_path / "canonical_copy"
    shutil.copytree(CANONICAL, copied)
    target = copied / "gen_office_mayor.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    monkeypatch.setattr(G, "CANONICAL_SEED_DIR", str(copied))
    errors = E.check_consistency()["errors"]
    assert any(e.startswith("generated seeds: gen_office_mayor.json: stale") for e in errors), errors


def _header_names(path):
    """Seed files in `path` that carry a generated_from header (generated, not hand-written)."""
    names = []
    for name in sorted(os.listdir(path)):
        if name.endswith(".json") and G._header(os.path.join(path, name)) is not None:
            names.append(name)
    return names


def test_every_generated_seed_parses_and_has_the_header():
    expected = G.expected_files(load_pack("bigville"))
    generated = _header_names(CANONICAL)
    assert sorted(generated) == sorted(expected)
    for name in generated:
        seed = json.loads(open(os.path.join(CANONICAL, name), encoding="utf-8").read())
        assert seed["id"] == name[:-len(".json")]
        assert set(seed) - {"terrain"} == GENERATED_KEYS, name
        header = seed["generated_from"]
        assert header["pack"] == "bigville" and header["generator"] == G.GENERATOR
        assert len(header["sha256"]) == 64 and all(c in "0123456789abcdef" for c in header["sha256"])
        for concept in seed["concepts"]:
            assert set(concept) == {"name", "definition", "category"}, name
        for rule in seed["rules"]:
            assert set(rule) == {"name", "head", "body"} and "match" not in rule, name


def test_ids_the_pack_loads_exist_in_the_canonical_or_hand_written_directory():
    ids = list(E.ENGINE_SEEDS) + list(E.RESIDENT_SEEDS) + list(E.RESIDENT_CONCEPT_SEEDS)
    missing = [sid for sid in ids
               if not (os.path.isfile(os.path.join(CANONICAL, f"{sid}.json"))
                       or os.path.isfile(os.path.join(ROOT_SEEDS, f"{sid}.json")))]
    assert missing == []


def test_the_two_seed_directories_agree_except_the_pending_decision():
    hand_canonical = set(os.listdir(CANONICAL)) - set(_header_names(CANONICAL))
    in_root = set(os.listdir(ROOT_SEEDS))
    assert hand_canonical - in_root == set()
    assert in_root - hand_canonical == set()
    drift = [name for name in sorted(in_root & hand_canonical) if name not in PENDING_DECISION
             and open(os.path.join(CANONICAL, name), "rb").read() != open(os.path.join(ROOT_SEEDS, name), "rb").read()]
    assert drift == []


def test_the_replaced_terrain_seed_keeps_its_id_and_its_table():
    seed = json.loads(open(os.path.join(CANONICAL, "bigville_terrain_movement.json"), encoding="utf-8").read())
    assert seed["id"] == "bigville_terrain_movement"
    assert seed["terrain"] == load_pack("bigville")["TERRAIN_MOVEMENT"]
    assert seed["terrain"]["path"]["speed"] == 1.35          # the value the hand-written seed held
    assert seed["generated_from"]["tables"] == ["TERRAIN_MOVEMENT"]
    assert seed["concepts"] == []                             # its two concepts are in gen_shared_concepts
    assert "bigville_terrain_movement" in E.ENGINE_SEEDS


def test_generated_concept_names_do_not_collide_with_hand_written_concepts():
    generated = {c["name"] for seed in G.plan(load_pack("bigville")).values() for c in seed["concepts"]}
    hand = set()
    for directory in (CANONICAL, ROOT_SEEDS):
        for name in os.listdir(directory):
            if not name.endswith(".json") or name in _header_names(directory):
                continue
            seed = json.loads(open(os.path.join(directory, name), encoding="utf-8").read())
            hand.update(c["name"] for c in seed.get("concepts") or [] if isinstance(c, dict) and "name" in c)
            hand.update(n["attrs"]["name"] for n in seed.get("nodes") or []
                        if isinstance(n, dict) and n.get("type") == "Concept" and "name" in n.get("attrs", {}))
    assert sorted(generated & hand) == []



def test_the_hamlet_pack_generates_into_a_temp_directory(tmp_path):
    hamlet = load_pack("test_hamlet")
    out = tmp_path / "hamlet_seeds"
    written = G.write_seeds(hamlet, str(out))
    assert written == sorted(G.expected_files(hamlet))
    assert "gen_law_hamlet_common_law.json" in written
    assert G.check_seeds(hamlet, str(out)) == []
    for name in written:
        assert json.loads((out / name).read_text(encoding="utf-8"))["generated_from"]["pack"] == "test_hamlet"


def test_a_policy_removed_from_the_pack_is_removed_from_the_output(tmp_path):
    out = tmp_path / "out"
    G.write_seeds(load_pack(_child(tmp_path / "a", {"LOCAL_POLICIES": _base("LOCAL_POLICIES")})), str(out))
    assert "gen_policy_winter_food_reserve.json" in os.listdir(out)
    shrunk = load_pack(_child(tmp_path / "b", {"LOCAL_POLICIES": []}))
    problems = G.check_seeds(shrunk, str(out))
    assert any("gen_policy_winter_food_reserve.json" in p and "no longer produces" in p for p in problems), problems
    G.write_seeds(shrunk, str(out))
    assert "gen_policy_winter_food_reserve.json" not in os.listdir(out)
    assert G.check_seeds(shrunk, str(out)) == []


def test_a_hand_written_seed_is_never_overwritten(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    hand = out / "gen_kinship.json"
    hand.write_text('{"id": "gen_kinship", "hand": true}', encoding="utf-8")
    with pytest.raises(PackError, match="hand-written"):
        G.write_seeds(load_pack("bigville"), str(out))
    assert hand.read_text(encoding="utf-8") == '{"id": "gen_kinship", "hand": true}'
    assert any("hand-written seed" in p for p in G.check_seeds(load_pack("bigville"), str(out)))


def test_the_cli_checks_the_canonical_directory_and_requires_out_for_other_packs(capsys):
    spec = importlib.util.spec_from_file_location("generate_seeds", os.path.join(ROOT, "tools", "generate_seeds.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--check"]) == 0
    assert cli.main(["--pack", "test_hamlet"]) == 2
    assert "needs --out" in capsys.readouterr().err
