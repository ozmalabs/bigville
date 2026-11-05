"""Phase 018: the LLM prompt is built from the data pack, carries only what the resident holds (bounded),
routes derived law and policy understanding into world_frames, and reads the speech lexicon from the pack."""
import dataclasses
import hashlib
import json
import os

import pytest

from bigville.backends import ActorContext, PromptBuilder
from bigville.backends.prompts import PROMPT_SCHEMA, pack_hash
from bigville.character import CharacterDefinition, FrameSeed, MemoryRecord
from bigville.game import BigvilleGame
from bigville.runtime import _realize_meaning
from domains.pack import canonical, load_pack
from worlds.bigville_world import BigvilleWorld

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = os.path.join(ROOT, "packs")
FOUNDERS_INDEX = (0, 50, 99)


@pytest.fixture(scope="module")
def town():
    world = BigvilleWorld.from_town100(seed=305000, autonomous_actors=False)
    game = BigvilleGame(world, autonomous=True)
    return world, game, sorted(game.characters)


def _child_pack(tmp_path, name, *, major=None, premise=None, merge=True):
    """A child pack of bigville in tmp_path: an optional MAJOR_ACTIONS table and an optional premise."""
    directory = tmp_path / name
    (directory / "world").mkdir(parents=True)
    tables = []
    if major is not None:
        with open(directory / "world" / "major_actions.json", "w", encoding="utf-8") as fh:
            json.dump({"_doc": "", "_types": {}, "tables": {"MAJOR_ACTIONS": major}}, fh)
        tables.append({"name": "MAJOR_ACTIONS", "file": "world/major_actions.json", "merge": merge})
    if premise is not None:
        with open(directory / "world" / "premise.json", "w", encoding="utf-8") as fh:
            json.dump({"_doc": "", "_types": {}, "tables": {"WORLD_PREMISE": premise}}, fh)
        tables.append({"name": "WORLD_PREMISE", "file": "world/premise.json"})
    manifest = {"format": 1, "name": name, "version": 1, "description": "test child",
                "extends": os.path.join(PACKS, "bigville"), "tables": tables}
    with open(directory / "pack.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    return str(directory)


def _context_with(game, name, memories):
    """The context of `name` as if the resident held only `memories`. The game's own copy is restored after."""
    real = game.characters[name]
    game.characters[name] = dataclasses.replace(real, memories=list(memories))
    try:
        return game._context(name)
    finally:
        game.characters[name] = real


def _private_bytes(record):
    return len(json.dumps(record.as_dict()["context"]["private"], sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))


# ------------------------------------------------------------------ the system prompt comes from the pack

def test_system_prompt_lists_every_pack_action_with_its_description():
    builder = PromptBuilder()
    pack = load_pack("bigville")
    for name, spec in pack["MAJOR_ACTIONS"].items():
        assert f"- {name}: {spec['description']}" in builder.system
    for name, spec in pack["FREE_ACTIONS"].items():
        assert f"- {name}: {spec['description']}" in builder.system
    assert pack["WORLD_PREMISE"]["premise"] in builder.system
    for rule in pack["PROMPT_BOUNDARY_RULES"]:
        assert rule in builder.system


def test_system_prompt_changes_when_the_packs_actions_change(tmp_path):
    base = PromptBuilder().system
    added = PromptBuilder(pack=_child_pack(tmp_path, "forager", major={
        "forage": {"kind": "gathering", "description": "Gather wild food from the hedgerow in reach."}}))
    assert "- forage: Gather wild food from the hedgerow in reach." in added.system
    assert "- move: " in added.system
    assert added.system != base

    replaced = PromptBuilder(pack=_child_pack(tmp_path, "resting", merge=False, major={
        "rest": {"kind": "recovery", "description": "Rest to recover energy."}}))
    assert "- move:" not in replaced.system
    assert "- rest: Rest to recover energy." in replaced.system
    assert replaced.system != base and replaced.system != added.system


def test_a_different_pack_gives_a_different_premise_with_no_code_change(tmp_path):
    hamlet = PromptBuilder(pack="test_hamlet")
    assert hamlet.system.startswith("You are one resident of Test hamlet.")
    assert "Bigville is a village" not in hamlet.system
    premise = {"name": "Saltmarsh", "premise": "A salt-pan village where the tide sets the working day."}
    child = PromptBuilder(pack=_child_pack(tmp_path, "saltmarsh", premise=premise))
    assert child.system.startswith("You are one resident of Saltmarsh. A salt-pan village")
    assert "Bigville" not in child.system


# ------------------------------------------------------------------ provenance of each record

def test_prompt_record_carries_schema_version_and_pack_hash(town):
    _, game, names = town
    record = PromptBuilder().build(game._context(names[0]))
    payload = record.as_dict()
    assert payload["schema"] == PROMPT_SCHEMA == "bigville/prompt/2"
    assert payload["pack"] == "bigville"
    pack = load_pack("bigville")
    expected = hashlib.sha256(canonical(pack.base).encode("utf-8")).hexdigest()
    assert payload["pack_hash"] == expected == pack_hash(pack)
    assert len(payload["pack_hash"]) == 64


def test_pack_hash_changes_with_the_pack_and_not_with_the_resident(tmp_path, town):
    _, game, names = town
    default = PromptBuilder().pack_hash
    child = PromptBuilder(pack=_child_pack(tmp_path, "forager2", major={
        "forage": {"kind": "gathering", "description": "Gather wild food."}})).pack_hash
    assert child != default
    builder = PromptBuilder()
    first = builder.build(game._context(names[0])).as_dict()["pack_hash"]
    second = builder.build(game._context(names[1])).as_dict()["pack_hash"]
    assert first == second == default


# ------------------------------------------------------------------ what the resident holds

def test_a_resident_not_seeded_a_law_does_not_see_it(town):
    _, game, names = town
    name = names[0]
    held = game.characters[name].memories
    without_laws = [m for m in held if not (isinstance(m.content, dict)
                                            and m.content.get("type") in ("law", "policy"))]
    assert len(without_laws) < len(held), "the founder should hold derived law knowledge to start with"
    frames = _context_with(game, name, without_laws).observations["world_frames"]
    assert frames["laws"] == []
    assert frames["policies"] == []


def test_understood_and_aware_laws_reach_world_frames_at_the_level_held(town):
    _, game, names = town
    name = names[0]
    frames = game._context(name).observations["world_frames"]
    understood = [law for law in frames["laws"] if law.get("understands", 0) > 0]
    assert understood, "a founder understands at least one law"
    for law in understood:
        assert law["aware"] is True
        assert "concepts" in law and "title" in law, "an understood law carries its spec"
        assert "knowledge" not in law, "the world's rule for who understands a law stays out of the context"

    # Aware-only laws, given a memory of awareness only, appear as name and gist with no spec.
    law_name = "public_order_law"
    from_pack = load_pack("bigville")["LAWS"]
    assert any(rec["name"] == law_name for rec in from_pack)
    aware_only = MemoryRecord(
        memory_id=f"knowledge:law:{law_name}", kind="awareness", source="derived_prior",
        content={"item": f"law:{law_name}", "type": "law", "name": law_name, "aware": True,
                 "understands": 0.0, "basis": ["public spread"], "source": "derived"})
    context = _context_with(game, name, [aware_only])
    laws = context.observations["world_frames"]["laws"]
    assert [law["name"] for law in laws] == [law_name]
    assert set(laws[0]) == {"name", "aware", "understands", "gist"}
    assert laws[0]["understands"] == 0.0 and laws[0]["aware"] is True


def test_explicit_law_knowledge_still_reaches_world_frames(town):
    world, game, names = town
    name = names[-1]
    memory = MemoryRecord(memory_id="law:explicit", kind="law_knowledge", source="scenario",
                          content={"name": "public_order_law", "interpretation": "explicit"})
    frames = _context_with(game, name, [memory]).observations["world_frames"]
    assert [law["name"] for law in frames["laws"]] == ["public_order_law"]
    assert frames["laws"][0]["title"] == world._law_specs["public_order_law"]["title"]


# ------------------------------------------------------------------ bounded, relevant selection

def test_the_private_part_is_bounded_for_founders(town):
    _, game, names = town
    builder = PromptBuilder()
    caps = builder.selection
    for index in FOUNDERS_INDEX:
        name = names[index]
        record = builder.build(game._context(name))
        private = record.as_dict()["context"]["private"]
        counts = private["selection"]
        assert counts["held_memories"] > 150, "a founder holds the derived priors"
        assert len(private["knowledge"]["understood"]) <= caps["max_standing_understood"] + caps["max_relevant_understood"]
        assert len(private["knowledge"]["aware"]) <= caps["max_relevant_aware"]
        assert len(private["memories"]) <= caps["max_recent_episodic"] + caps["max_relevant_understood"]
        assert _private_bytes(record) < 15_000, f"{name}: private part {_private_bytes(record)} bytes"


def test_the_private_part_does_not_grow_with_more_episodic_memories(town):
    _, game, names = town
    name = names[0]
    builder = PromptBuilder()
    base = _private_bytes(builder.build(game._context(name)))
    episodic = [MemoryRecord(memory_id=f"episode:{i}", content="A long remembered event. " * 40,
                             kind="episodic", turn=i) for i in range(400)]
    context = _context_with(game, name, game.characters[name].memories + episodic)
    record = builder.build(context)
    private = record.as_dict()["context"]["private"]
    assert private["selection"]["shown_memories"] <= builder.selection["max_recent_episodic"] + \
        builder.selection["max_relevant_understood"]
    assert [m["memory_id"] for m in private["memories"] if m["kind"] == "episodic"][0] == "episode:399"
    assert _private_bytes(record) <= base + 12 * (builder.selection["max_memory_text"] + 200)


def test_aware_only_items_are_name_and_gist_never_basis_or_content(town):
    _, game, names = town
    name = names[0]
    record = PromptBuilder().build(game._context(name))
    private = record.as_dict()["context"]["private"]
    aware = private["knowledge"]["aware"]
    assert aware, "a founder is aware of goods they do not understand"
    held = {m.content["item"]: m.content for m in game.characters[name].memories
            if isinstance(m.content, dict) and "item" in m.content}
    for entry in aware:
        assert set(entry) == {"item", "type", "name", "gist"}
        source = held[entry["item"]]
        assert source["understands"] == 0.0
        assert source["basis"], "the held item has a basis that must stay out of the prompt"
        for reason in source["basis"]:
            assert reason not in json.dumps(private)
    assert "basis" not in json.dumps(private)


def test_understood_entries_keep_their_place_precision_and_no_map(town):
    _, game, names = town
    private = PromptBuilder().build(game._context(names[0])).as_dict()["context"]["private"]
    places = [entry for entry in private["knowledge"]["understood"] if entry["type"] == "place"]
    for place in places:
        assert place["location"] in ("exact", "roughly")
        assert set(place) <= {"item", "type", "name", "understands", "location", "position", "landmark"}
        if place["location"] == "roughly":
            assert "position" not in place
    text = json.dumps(private)
    assert "terrain_movement" not in text and "FOUNDING_MAP" not in text


def test_relevant_items_follow_the_affordances(town):
    _, game, names = town
    name = names[0]
    context = game._context(name)
    context.affordances = [{"action": "work", "kind": "flour", "recipe": "", "trade": "", "target": ""}]
    private = PromptBuilder().build(context).as_dict()["context"]["private"]
    aware_names = {entry["name"] for entry in private["knowledge"]["aware"]}
    assert "flour" in aware_names


# ------------------------------------------------------------------ speech lexicon from the pack

def test_chatter_and_weather_come_from_the_pack_not_the_runtime():
    pack = load_pack("bigville")
    chatter = pack["SPEECH_CHATTER"]
    weather = pack["SPEECH_WEATHER"]
    assert _realize_meaning({"topic": {"of": "baker"}}) == chatter["phrases"]["baker"]
    assert _realize_meaning({"topic": {"of": "miller"}}) == chatter["work_template"].format(trade="miller")
    assert _realize_meaning({"topic": {"of": ""}}) == chatter["empty"]
    assert _realize_meaning({"weather": {"of": "rain"}}) == weather["phrases"]["rain"]
    assert _realize_meaning({"weather": {"of": "hail"}}) == weather["template"].format(weather="hail")

    with open(os.path.join(ROOT, "bigville", "runtime.py"), encoding="utf-8") as fh:
        source = fh.read()
    for phrase in chatter["phrases"].values():
        assert phrase not in source
    for phrase in weather["phrases"].values():
        assert phrase not in source


def test_chatter_and_weather_use_the_lexicon_they_are_given():
    lexicon = {
        "chatter": {"phrases": {"baker": "Bread is dear this week."},
                    "work_template": "Work at {trade} is steady.", "empty": "Quiet."},
        "weather": {"phrases": {"rain": "Wet again."}, "template": "Weather: {weather}."},
    }
    assert _realize_meaning({"topic": {"of": "baker"}}, lexicon=lexicon) == "Bread is dear this week."
    assert _realize_meaning({"topic": {"of": "smith"}}, lexicon=lexicon) == "Work at smith is steady."
    assert _realize_meaning({"weather": {"of": "rain"}}, lexicon=lexicon) == "Wet again."
    assert _realize_meaning({"weather": {"of": "hot"}}, lexicon=lexicon) == "Weather: hot."


def test_prompt_record_is_replayable_as_json(town):
    _, game, names = town
    record = PromptBuilder().build(game._context(names[0]))
    decoded = json.loads(record.as_json())
    assert decoded["schema"] == PROMPT_SCHEMA
    assert decoded["pack_hash"] == pack_hash(load_pack("bigville"))
    assert record.as_json() == PromptBuilder().build(game._context(names[0])).as_json()


def test_a_scenario_character_prompt_keeps_its_memories_and_frames():
    character = CharacterDefinition(
        character_id="Ada", name="Ada", identity={"role": "farmer"},
        memories=[MemoryRecord("m1", "The north field is dry.")],
        held_frames=[FrameSeed("grain_goes_in_granary")],
    )
    record = PromptBuilder().build(ActorContext(character, 2, {}, [{"action": "move"}]))
    private = record.as_dict()["context"]["private"]
    assert private["memories"][0]["content"] == "The north field is dry."
    assert private["held_frames"][0]["seed"] == "grain_goes_in_granary"
    assert private["knowledge"] == {"understood": [], "aware": []}
