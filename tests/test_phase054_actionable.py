"""Phase 054 follow-up: an LLM reply names a row of public.can by its handle, and the proposal is the one the
simple backend would send for that row. Fake providers only; no network.

The rules held here:
* every handle is unique, stable across two builds of the same seed, and free of coordinates and referee
  numbers (the one number allowed is the world's own `target:N` key, which is an index, not a quantity);
* over a sample of town100 residents, every row of the view's `can` list, sent back as {action, target},
  becomes a proposal with the same action and the same params as the simple backend's proposal for that row;
* a `work` reply from an LLM resident is enacted by the world in a real game turn;
* a handle that names no row, or an action that names no row, is passed on unchanged for the world to refuse;
* attempt never binds to an affordance, and the model's own intensity, tool are laid over the row.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                              # noqa: E402
from bigville.backends import ActorContext, LLMBackend            # noqa: E402
from bigville.backends.prompt_packet import packet_system         # noqa: E402
from bigville.backends import reply_schema                        # noqa: E402
from bigville.character import CharacterDefinition                # noqa: E402
from domains.affordance_handles import affordance_handles, handle_pairs  # noqa: E402
from domains.lexicon import intensity_value, resolve_verb        # noqa: E402
from domains.pack import load_pack                                # noqa: E402

SEED = 305000
SAMPLE_EVERY = 5                       # 100 residents, every fifth one: a sample of 20
REFUSALS = set(load_pack("bigville")["REFUSAL_REASONS"])
# What cheap.py's decide() sends as params for a chosen affordance: every key but these four.
NOT_PARAMS = {"action", "score", "legal", "reason"}
HANDLE = re.compile(r"^[a-z_]+(:[a-z0-9_]+)*(#[0-9]+)?$")


class Script:
    """A fake provider. It returns `text` on every call and counts the calls."""

    def __init__(self, text="{}"):
        self.text = text
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return self.text


def _reply(major):
    return json.dumps({"major_action": major, "utterances": [], "memory_updates": [], "continuation": None})


def _simple_params(row):
    """The params the simple backend sends for an affordance (cheap.py): every key but these four."""
    return {key: value for key, value in row.items() if key not in NOT_PARAMS}


# The keys the simple backend's CAN policy adds to a chosen option (bigville/backends/psi_can.py). They are
# its own scores, not world facts, and the world ignores them. The LLM proposal does not carry them.
POLICY_KEYS = {"psi", "can", "can_concepts", "weighted_score", "decision_model"}


def _town():
    return create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                       ticks_per_period="world")


def _sample(game):
    return sorted(game.backends)[::SAMPLE_EVERY]


def _rows_by_handle(affordances):
    return {handle: row for handle, row in handle_pairs(affordances)}


def _baker(name="Mabel Cobb"):
    return CharacterDefinition(character_id=name, name=name, identity={"role": "baker", "life_stage": "adult"},
                               personality={})


def _ctx(affordances, view=None, character=None):
    observations = {"calendar": {"hour": 9.0, "day": 0.0, "season": "spring", "weather": "clear skies"},
                    "heard_utterances": [], "physical_events": []}
    return ActorContext(character or _baker(), 9, observations, affordances,
                        agent_view=view if view is not None else {"self": {"name": "Mabel Cobb"}})


# -- the handle function --------------------------------------------------------------------------
def test_two_rows_never_share_a_handle_and_a_collision_gets_a_numbered_suffix():
    rows = [{"action": "work", "recipe": "burn_charcoal"},
            {"action": "work", "recipe": "burn_charcoal"},
            {"action": "work", "recipe": "burn_charcoal"},
            {"action": "rest"},
            {"action": "rest", "target": "rest"},
            {"action": "move", "target": "target:1"},
            {"action": "move", "target": "target:1"}]
    handles = affordance_handles(rows)
    assert len(set(handles)) == len(handles)
    assert handles == ["work:burn_charcoal", "work:burn_charcoal#2", "work:burn_charcoal#3", "rest",
                       "rest#2", "target:1", "target:1#2"]


def test_a_suffix_never_collides_with_a_later_row_that_already_has_that_name():
    rows = [{"action": "eat", "kind": "bread"}, {"action": "eat", "kind": "bread#2"},
            {"action": "eat", "kind": "bread"}]
    assert affordance_handles(rows) == ["eat:bread", "eat:bread#2", "eat:bread#3"]


def test_the_handle_is_the_world_target_when_there_is_one_and_the_recipe_or_kind_otherwise():
    assert affordance_handles([{"action": "fetch", "kind": "bread", "target": "target:4"}]) == ["target:4"]
    assert affordance_handles([{"action": "work", "recipe": "grind_flour", "kind": "flour", "target": ""}]) == [
        "work:grind_flour"]
    assert affordance_handles([{"action": "eat", "kind": "bread", "target": ""}]) == ["eat:bread"]
    assert affordance_handles([{"action": "sleep", "target": ""}]) == ["sleep"]


def test_the_handle_function_is_deterministic_and_reads_no_coordinates():
    rows = [{"action": "move", "target": "target:2", "destination": (36, 29), "trade": "bakery"},
            {"action": "work", "recipe": "brew_ale", "destination": (3, 4)}]
    first = affordance_handles(rows)
    assert first == affordance_handles([dict(row) for row in rows]) == ["target:2", "work:brew_ale"]
    moved = [dict(rows[1], destination=(99, 99)), dict(rows[0], destination=(1, 1))]
    assert affordance_handles(moved) == ["work:brew_ale", "target:2"]


# -- the world's rows: determinism, handle shape, and the sample ----------------------------------
@pytest.fixture(scope="module")
def town():
    return _town()


def test_handles_are_unique_and_identical_across_two_builds_of_the_same_seed(town):
    other = _town()
    for name in sorted(town.backends):
        here = affordance_handles(town.world.actor_affordances(name))
        there = affordance_handles(other.world.actor_affordances(name))
        assert len(set(here)) == len(here), name
        assert here == there, name


def test_every_sampled_handle_is_a_plain_name_with_no_coordinate_or_referee_number(town):
    seen = 0
    for name in _sample(town):
        view = town.agent_view(name)
        for row in view["can"]:
            seen += 1
            assert set(row) == {"handle", "action", "what"}, row
            assert HANDLE.match(row["handle"]), row
            assert "(" not in row["handle"] and "," not in row["handle"], row
            if not row["handle"].startswith("target:"):
                assert not re.search(r"\d", row["handle"].split("#")[0]), row
    assert seen > 100


@pytest.fixture(scope="module")
def simple_choices():
    """Each sampled resident's simple-backend decision, from a game of its own: the proposal cheap.py makes."""
    game = _town()
    sampled = {}
    for name in _sample(game):
        context = game._context(name)           # a simple resident: no view in the context
        response = game.backends[name].decide(context)
        sampled[name] = (context, response)
    return sampled


def test_the_simple_backend_proposal_is_one_of_the_rows_params_as_the_tests_mirror_them(simple_choices):
    """The simple backend's proposal is its chosen row's params plus its CAN scores (POLICY_KEYS). Without those
    scores it equals the row's params, which is what the LLM path proposes for the same row."""
    chosen = 0
    for name, (context, response) in simple_choices.items():
        if response.major_action is None:
            continue
        chosen += 1
        params = response.major_action.params
        without_scores = {key: value for key, value in params.items() if key not in POLICY_KEYS}
        matches = [row for row in context.affordances
                   if row.get("action") == response.major_action.action
                   and _simple_params(row) == without_scores]
        assert matches, name
    assert chosen >= 5


# -- the LLM reply names a row: same proposal as the simple backend ----------------------------
def test_every_can_row_of_a_sample_resident_becomes_the_simple_backends_proposal_for_that_row():
    game = _town()
    script = Script()
    checked = 0
    for name in _sample(game):
        backend = LLMBackend(game.characters[name], script, autopilot=False)
        game.set_backend(name, backend)
        context = game._context(name)
        by_handle = _rows_by_handle(context.affordances)
        # Phase 054b: the model copies the token it was shown for the row (the same token the consult shows).
        shown = backend.handles.mask_context(context).agent_view["can"]
        for row, shown_row in zip(context.agent_view["can"], shown):
            script.text = _reply({"action": row["action"], "target": shown_row["handle"]})
            response = backend.decide(context)
            world_row = by_handle[row["handle"]]
            assert backend.last_backend_state["outcome"] == "ok", (name, row)
            assert response.major_action is not None, (name, row)
            assert response.major_action.action == world_row["action"], (name, row)
            assert response.major_action.params == _simple_params(world_row), (name, row)
            checked += 1
    assert checked >= 100


# -- a model's work reply enacted by the world ---------------------------------------------------
def _work_resident(game):
    for name in sorted(game.backends):
        works = [row for row in game.agent_view(name)["can"] if row["action"] == "work"]
        if works:
            return name, works[0]
    raise AssertionError("no resident of town100 has a work row at the start")


def test_an_llm_resident_replying_with_a_work_row_is_enacted_by_the_world_in_one_turn():
    game = _town()
    name, row = _work_resident(game)
    script = Script()
    backend = LLMBackend(game.characters[name], script, autopilot=False)
    game.set_backend(name, backend)
    # Phase 054b: the reply copies the token the view showed for this row.
    context = game._context(name)
    raw = [r["handle"] for r in context.agent_view["can"]]
    token = backend.handles.mask_context(context).agent_view["can"][raw.index(row["handle"])]["handle"]
    script.text = _reply({"action": "work", "target": token})
    world_row = _rows_by_handle(game.world.actor_affordances(name))[row["handle"]]
    game.step()
    proposal = game.last_responses[name].major_action
    assert proposal.action == "work" and proposal.params == _simple_params(world_row)
    assert script.calls == 1
    assert game.last_results[name] is True, game.last_rejections.get(name)


def test_a_work_reply_with_no_row_is_refused_by_the_world_as_a_known_reason():
    game = _town()
    name, _ = _work_resident(game)
    game.set_backend(name, LLMBackend(game.characters[name], Script(_reply({"action": "work",
                                                                            "target": "no_such_row"})),
                                      autopilot=False))
    game.step()
    assert game.last_results[name] is False
    refusal = game.last_rejections.get(name)
    assert refusal is not None and refusal["reason"] in REFUSALS, refusal
    assert refusal is not None and refusal["reason"] in REFUSALS, refusal


# -- the reply's own words: binding rules (unit level) -----------------------------------------------
PK = load_pack("bigville")
RECIPE_ROW = {"action": "work", "kind": "charcoal", "trade": "", "target": "", "recipe": "burn_charcoal"}
MOVE_ROW = {"action": "move", "kind": "", "trade": "bakery", "recipe": "", "target": "target:3",
            "destination": (36, 29), "animal": "chicken_1", "score": 0.0}


def _wire(major, rows, pack="bigville"):
    parsed = {"major_action": major, "utterances": [], "memory_updates": [], "continuation": None}
    assert reply_schema.check(parsed, pack) == []
    return reply_schema.to_wire(parsed, pack, affordances=rows)["major_action"]


def test_a_handle_in_the_reply_takes_the_full_row_and_the_model_fields_are_laid_over_it():
    wire = _wire({"action": "work", "target": "work:burn_charcoal", "with": "hammer", "intensity": "hard"},
                 [RECIPE_ROW, MOVE_ROW])
    assert wire["action"] == "work"
    assert wire["params"]["recipe"] == "burn_charcoal" and wire["params"]["kind"] == "charcoal"
    assert wire["params"]["tool"] == "hammer"
    assert wire["params"]["intensity"] == intensity_value("hard", "bigville")
    assert "score" not in wire["params"]


def test_a_move_handle_takes_the_full_row_including_its_destination():
    wire = _wire({"action": "move", "target": "target:3"}, [RECIPE_ROW, MOVE_ROW])
    assert wire["params"] == _simple_params(MOVE_ROW)


def test_the_view_word_for_an_action_also_names_the_row():
    wire = _wire({"action": "walk", "target": "target:3"}, [RECIPE_ROW, MOVE_ROW])
    assert wire["action"] == "move" and wire["params"]["destination"] == (36, 29)


def test_an_action_with_no_handle_takes_the_row_only_when_exactly_one_row_has_that_action():
    assert _wire({"action": "work"}, [RECIPE_ROW, MOVE_ROW])["params"] == _simple_params(RECIPE_ROW)
    two = [RECIPE_ROW, dict(RECIPE_ROW, recipe="grind_flour")]
    assert _wire({"action": "work"}, two)["params"] == {}      # several rows: the world refuses
    assert _wire({"action": "work", "params": {"recipe": "grind_flour"}}, two)["params"] == {"recipe": "grind_flour"}


def test_a_handle_that_names_no_row_passes_the_models_params_through_unchanged():
    wire = _wire({"action": "work", "target": "no_such_row", "params": {"recipe": "forged"}}, [RECIPE_ROW])
    assert wire["params"] == {"recipe": "forged", "target": "no_such_row"}


def test_a_handle_that_names_a_row_of_another_action_passes_through_unchanged():
    wire = _wire({"action": "eat", "target": "target:3"}, [RECIPE_ROW, MOVE_ROW])
    assert wire["params"] == {"target": "target:3"}


def test_attempt_never_binds_to_an_affordance_and_keeps_its_thing_handle():
    lock_row = {"action": "unlock", "target": "lock", "kind": "", "recipe": ""}
    wire = _wire({"action": "attempt", "target": "lock", "params": {"verb": "bash"}}, [lock_row])
    assert wire["action"] == "attempt"
    assert wire["params"] == {"verb": resolve_verb("bash", "bigville"), "target": "lock"}


def test_without_affordances_the_handle_is_kept_as_the_model_wrote_it_as_before():
    parsed = {"major_action": {"action": "work", "target": "work:burn_charcoal"}, "utterances": [],
              "memory_updates": []}
    assert reply_schema.to_wire(parsed, "bigville")["major_action"]["params"] == {"target": "work:burn_charcoal"}


# -- the packet tells the model how to name a row --------------------------------------------------
def test_the_packet_interface_says_to_copy_the_handle_and_the_action_of_a_can_row():
    system = packet_system("bigville")
    assert "handle of that same public.can row" in system
    assert "action of a row in public.can" in system
