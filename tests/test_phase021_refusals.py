"""Phase 021: refusal records and result feedback.

A refused major action names a physical reason from the pack's REFUSAL_REASONS table. The world logs
the refusal for the acting resident (bounded) and counts it by action and reason. The resident's own
last outcome reaches its next context and prompt. No other resident sees it. A successful action
records no refusal.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.prompts import PromptBuilder
from bigville.game import BigvilleGame
from bigville.scenarios import load_scenario
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld

NOBODY = 999999
WORLD_SOURCE = Path(__file__).resolve().parents[1] / "worlds" / "bigville_world.py"


def _town():
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    world.tick()
    names = sorted(world._actors)
    return world, names[0], names[1]


def _counts(world):
    return world.refusal_counts()


def _at_store(world, actor):
    world._move_actor_to(actor, world.map_position_node(world._store))


class _FixedBackend(DeterministicBackend):
    """Proposes one plan every turn; keeps DeterministicBackend's held-state API."""

    def __init__(self, character, plan):
        super().__init__(character)
        self.plan = plan

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(self.plan["action"], {
            key: value for key, value in self.plan.items() if key != "action"}))


# ------------------------------------------------------------------ the empty store
def test_refused_fetch_at_an_empty_store_records_out_of_stock_for_that_resident():
    world, actor, _ = _town()
    _at_store(world, actor)
    assert world.qty("unobtainium") == 0.0
    before = _counts(world)

    assert world.major_action(actor, "fetch", kind="unobtainium", amount=1.0) is False

    assert world.last_outcome(actor) == {"turn": int(world._turn), "action": "fetch",
                                         "applied": False, "reason": "out_of_stock"}
    assert world.refusals(actor)[-1]["reason"] == "out_of_stock"
    assert world.refusals(actor)[-1]["action"] == "fetch"
    after = _counts(world)
    assert after["total"] == before["total"] + 1
    assert after["by_reason"]["out_of_stock"] == before["by_reason"].get("out_of_stock", 0) + 1
    assert after["by_action"]["fetch"]["out_of_stock"] == before["by_action"].get("fetch", {}).get(
        "out_of_stock", 0) + 1


def test_refused_fetch_appears_in_the_next_context_for_that_actor_and_not_for_a_neighbour():
    world, actor, neighbour = _town()
    game = BigvilleGame(world, autonomous=True)
    _at_store(world, actor)
    world.major_action(actor, "fetch", kind="unobtainium", amount=1.0)

    own = game._context(actor).observations["last_outcome"]
    assert own["reason"] == "out_of_stock" and own["applied"] is False
    assert game._context(neighbour).observations["last_outcome"] is None
    assert world.refusals(neighbour) == []


def test_a_successful_action_records_no_refusal():
    world, actor, _ = _town()
    counts = _counts(world)
    refusals = world.refusals(actor)

    assert world.major_action(actor, "rest", amount=1.0) is True

    assert world.last_outcome(actor)["applied"] is True
    assert world.last_outcome(actor)["reason"] == ""
    assert world.refusals(actor) == refusals
    assert _counts(world) == counts


def test_the_prompt_for_a_resident_with_a_refusal_contains_the_reason_and_its_meaning():
    world, actor, neighbour = _town()
    game = BigvilleGame(world, autonomous=True)
    _at_store(world, actor)
    world.major_action(actor, "fetch", kind="unobtainium", amount=1.0)

    prompt = PromptBuilder().build(game._context(actor))
    public = prompt.context["public"]
    assert public["last_outcome"]["reason"] == "out_of_stock"
    assert public["last_outcome"]["applied"] is False
    assert public["last_outcome"]["meaning"] == E.REFUSAL_REASONS["out_of_stock"]["description"]
    assert "out_of_stock" in prompt.as_json()
    assert "last_outcome" not in PromptBuilder().build(game._context(neighbour)).context["public"]


def test_the_report_shows_refusal_counts_by_action_and_reason():
    world, actor, _ = _town()
    _at_store(world, actor)
    world.major_action(actor, "fetch", kind="unobtainium", amount=1.0)

    refusals = world.report()["refusals"]

    assert refusals["total"] >= 1
    assert refusals["by_reason"]["out_of_stock"] >= 1
    assert refusals["by_action"]["fetch"]["out_of_stock"] >= 1


# ------------------------------------------------------------------ the game and checkpoints
def test_last_rejections_lists_this_turns_refusals_and_empties_on_the_next_turn():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world)
    game.set_backend("Ada", _FixedBackend(game.characters["Ada"],
                                          {"action": "move", "destination": NOBODY}))
    game.set_backend("Ben", _FixedBackend(game.characters["Ben"],
                                          {"action": "move", "destination": (2, 1)}))

    game.step()

    assert game.last_results == {"Ada": False, "Ben": True}
    turn = int(world._turn)
    assert game.last_rejections == {"Ada": {"actor": "Ada", "action": "move",
                                            "reason": "unknown_target", "turn": turn}}
    assert world.refusals("Ben") == []
    world.tick()
    assert game.last_rejections == {}


def test_refusals_survive_a_game_checkpoint_round_trip(tmp_path):
    # game_persistence is the parallel session's module (not yet committed); skip until it exists.
    persistence = pytest.importorskip("bigville.game_persistence")
    save_game_checkpoint, load_game_checkpoint = persistence.save_game_checkpoint, persistence.load_game_checkpoint
    scenario = load_scenario("house_argument").to_dict()
    scenario["actors"] = [dict(actor, backend="simple") for actor in scenario["actors"]]
    saved = create_game(scenario=scenario, player="Mara", seed=913)
    actor = sorted(saved.characters)[0]
    assert saved.world.major_action(actor, "move", destination=NOBODY) is False
    expected = saved.last_rejections
    assert expected and expected[actor]["reason"] == "unknown_target"

    checkpoint = tmp_path / "game"
    save_game_checkpoint(saved, checkpoint)
    restored = load_game_checkpoint(checkpoint)

    assert restored.world.refusals(actor) == saved.world.refusals(actor)
    assert restored.world.refusal_counts() == saved.world.refusal_counts()
    assert restored.world.last_outcome(actor) == saved.world.last_outcome(actor)
    assert restored.last_rejections == expected


def test_refusal_log_keeps_only_the_newest_entries_and_counts_every_refusal():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    total = E.REFUSAL_LOG_LIMIT + 5
    for _ in range(total):
        assert world.major_action("Ada", "move", destination=NOBODY) is False

    log = world.refusals("Ada")
    assert len(log) == E.REFUSAL_LOG_LIMIT
    assert world.refusal_counts()["total"] == total
    assert [record["turn"] for record in log] == sorted(record["turn"] for record in log)


# ------------------------------------------------------------------ reasons at the refusal points
@pytest.mark.parametrize("action, kwargs, reason", [
    ("fetch", {"kind": None}, "malformed"),
    ("move", {"destination": NOBODY}, "unknown_target"),
    ("care", {"patient": NOBODY}, "unknown_target"),
    ("eat", {"kind": "bread"}, "not_held"),
    ("work", {"action_name": "no_such_recipe"}, "not_known"),
    ("tend_animals", {"animal": NOBODY, "task": "milk"}, "unknown_target"),
    ("fertilise", {"target": NOBODY}, "unknown_target"),
])
def test_a_refused_major_action_names_its_physical_reason(action, kwargs, reason):
    world, actor, _ = _town()
    assert world.major_action(actor, action, **kwargs) is False
    assert world.last_outcome(actor)["reason"] == reason
    assert world.refusals(actor)[-1]["reason"] == reason


def test_a_second_major_action_in_the_same_turn_is_refused_slot_used():
    world, actor, _ = _town()
    assert world.major_action(actor, "rest", amount=1.0) is True
    assert world.major_action(actor, "rest", amount=1.0) is False
    assert world.last_outcome(actor)["reason"] == "slot_used"


def test_a_malformed_plan_is_logged_once_not_once_per_nested_attempt():
    world, actor, _ = _town()
    before = _counts(world)["total"]

    assert world.enact_plan(actor, {"action": "fetch"}) is False
    assert world.enact_plan(actor, {"action": "dance"}) is False

    assert _counts(world)["total"] == before + 2
    assert world.last_outcome(actor)["reason"] == "malformed"


def test_a_plan_to_rest_when_not_tired_is_refused_not_needed():
    world, actor, _ = _town()
    assert world.stamina_reserve(actor) >= 0.8
    assert world.enact_plan(actor, {"action": "rest"}) is False
    assert world.last_outcome(actor)["reason"] == "not_needed"


def test_every_reason_code_the_world_uses_is_in_the_pack_table():
    source = WORLD_SOURCE.read_text(encoding="utf-8")
    used = set()
    for call in re.findall(r"_refuse\(([^)]*)\)", source):
        used.update(re.findall(r'"([a-z_]+)"', call))
    recipe_body = source[source.index("    def _recipe_refusal("):source.index("    def _attempt(")]
    used.update(re.findall(r'return "([a-z_]+)"', recipe_body))
    used.add("not_possible")          # the catch-all in _attempt
    assert used, "no refusal codes found in the world source"
    assert used <= set(E.REFUSAL_REASONS), sorted(used - set(E.REFUSAL_REASONS))


def test_the_pack_reason_table_has_a_description_for_every_code():
    for code, spec in E.REFUSAL_REASONS.items():
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", code)
        assert spec["description"].strip(), code
    assert E.REFUSAL_LOG_LIMIT >= 1
    assert json.dumps(E.REFUSAL_REASONS)
