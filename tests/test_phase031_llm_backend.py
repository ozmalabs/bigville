"""Phase 031: the LLM backend is registered in create_game, validates output, repairs once,
and falls back to an idle response with counted failures. Fake providers only; no network."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from bigville.api import create_game, llm_backend_factory
from bigville.backends import ActorContext, ActorResponse, HumanBackend, LLMBackend, PromptBuilder
from bigville.backends.llm import MAX_REPAIRS, safe_error, validate_response
from bigville.character import CharacterDefinition
from bigville.game import BigvilleGame
from bigville.reporting import game_report, llm_report
from worlds.bigville_world import BigvilleWorld


SCENARIO_ROOT = Path(__file__).resolve().parent.parent / "scenarios"


class ScriptedProvider:
    """Returns the scripted outputs in order, then repeats the last one.

    An item that is an exception instance is raised instead of returned.
    Every prompt it receives is kept (copied) for inspection."""

    def __init__(self, *script):
        self.script = list(script)
        self.prompts: list[dict] = []

    def complete(self, prompt):
        self.prompts.append(copy.deepcopy(prompt))
        item = self.script[min(len(self.prompts), len(self.script)) - 1]
        if isinstance(item, BaseException):
            raise item
        return item


VALID = '{"major_action": {"action": "rest", "params": {}}, "waiting": false}'
NOT_JSON = "I think you should rest now."


def _character(name="Ada"):
    return CharacterDefinition(character_id=name, name=name)


def _view(name="Ada"):
    """A minimal agent view (Phase 054: the LLM backend sends only what the view gives)."""
    return {"mode": "agent", "actor": name,
            "self": {"name": name, "job": "hand", "life_stage": "an adult", "age": "grown"},
            "now": {"time": "at dawn"}, "around": {"people": [], "heard": [], "seen": [], "things": []},
            "can": [{"handle": "", "action": "rest", "what": ""}], "last": {}}


def _context(name="Ada"):
    return ActorContext(_character(name), 3, {"energy": 50}, [{"action": "rest", "score": 1}],
                        agent_view=_view(name))


def _world_game():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    return world, BigvilleGame(world, player="Ada")


def _idle(response: ActorResponse) -> bool:
    return response.major_action is None and response.waiting is False


# -- registration ------------------------------------------------------------

def test_create_game_builds_llm_residents_from_llm_provider():
    provider = ScriptedProvider(VALID)
    game = create_game(scenario="town100", default_backend="llm", llm_provider=provider)
    npcs = [name for name in game.characters if name != game.player]
    assert npcs
    assert all(isinstance(game.backends[name], LLMBackend) for name in npcs)
    assert all(game.backends[name].kind == "llm" for name in npcs)
    assert all(game.characters[name].backend["kind"] == "llm" for name in npcs)


def test_create_game_builds_llm_residents_from_backend_factories():
    provider = ScriptedProvider(VALID)
    game = create_game(scenario="town100", default_backend="llm",
                       backend_factories={"llm": llm_backend_factory(provider)})
    npcs = [name for name in game.characters if name != game.player]
    assert all(isinstance(game.backends[name], LLMBackend) for name in npcs)
    assert all(game.backends[name].provider is provider for name in npcs)


def test_llm_backend_without_a_provider_is_refused():
    with pytest.raises(ValueError, match="llm_provider"):
        create_game(scenario="town100", default_backend="llm")


def test_llm_provider_and_llm_factory_together_are_refused():
    provider = ScriptedProvider(VALID)
    with pytest.raises(ValueError, match="not both"):
        create_game(scenario="town100", default_backend="llm", llm_provider=provider,
                    backend_factories={"llm": llm_backend_factory(provider)})


def test_scenario_authored_llm_backend_is_built_from_the_provider():
    data = json.loads((SCENARIO_ROOT / "norms_property_sharing.json").read_text())
    for actor in data["actors"]:
        if actor["name"] == "Ben":
            actor["backend"] = "llm"
    provider = ScriptedProvider(VALID)
    game = create_game(scenario=data, default_backend="simple", llm_provider=provider)
    assert isinstance(game.backends["Ben"], LLMBackend)
    assert not isinstance(game.backends["Ada"], LLMBackend)


def test_callable_provider_is_accepted():
    seen = []

    def provider(prompt):
        seen.append(prompt["schema"])
        return VALID

    backend = LLMBackend(_character(), provider)
    assert backend.decide(_context()).major_action.action == "rest"
    assert seen == ["bigville/prompt/3"]


# -- good output, first call -------------------------------------------------

def test_first_good_reply_is_unchanged_and_counted_once():
    provider = ScriptedProvider(VALID)
    backend = LLMBackend(_character(), provider)
    response = backend.decide(_context())
    assert response.major_action.action == "rest"
    assert len(provider.prompts) == 1
    state = backend.last_backend_state
    record = PromptBuilder().build(_context(), state["consult_reason"])
    assert state["prompt_hash"] == hashlib.sha256(record.as_json().encode()).hexdigest()
    parsed = json.loads(VALID)
    assert state["response_hash"] == hashlib.sha256(
        json.dumps(parsed, sort_keys=True, default=repr).encode()).hexdigest()
    assert state["attempts"] == 1 and state["outcome"] == "ok"
    assert (state["calls"], state["repairs_used"], state["successes"], state["failures"]) == (1, 0, 1, 0)


# -- repair ------------------------------------------------------------------

def test_invalid_json_then_valid_json_succeeds_on_the_repair():
    provider = ScriptedProvider(NOT_JSON, VALID)
    backend = LLMBackend(_character(), provider)
    response = backend.decide(_context())
    assert response.major_action.action == "rest"
    assert len(provider.prompts) == 2
    assert "repair" not in provider.prompts[0]
    assert provider.prompts[1]["repair"] == {"errors": ["output is not a JSON object"]}
    state = backend.last_backend_state
    assert state["outcome"] == "repaired" and state["attempts"] == 2
    assert (state["calls"], state["repairs_used"], state["repaired_successes"]) == (2, 1, 1)
    assert (state["successes"], state["failures"]) == (1, 0)


def test_repair_request_carries_the_original_prompt_and_only_the_error_messages():
    marker = "SECRET_MARKER_NOT_TO_ECHO"
    bad = '{"major_action": {"action": "%s", "params": "bad"}}' % marker
    provider = ScriptedProvider(bad, VALID)
    LLMBackend(_character(), provider).decide(_context())
    first, repair = provider.prompts
    # Phase 066: the repair is one extra message in the thread (the errors); everything else is the original call.
    assert {k: v for k, v in repair.items() if k not in ("repair", "messages", "thread")} == \
        {k: v for k, v in first.items() if k not in ("messages", "thread")}
    assert repair["messages"][:len(first["messages"])] == first["messages"]
    assert len(repair["messages"]) == len(first["messages"]) + 1
    assert set(repair["repair"]) == {"errors"}
    assert repair["repair"]["errors"] == ["major_action.params must be an object"]
    assert marker not in json.dumps(repair)


def test_schema_violation_is_repaired_with_a_fixed_message():
    wrong = '{"utterances": "hello there"}'
    provider = ScriptedProvider(wrong, VALID)
    backend = LLMBackend(_character(), provider)
    assert backend.decide(_context()).major_action.action == "rest"
    assert provider.prompts[1]["repair"]["errors"] == ["utterances must be a list of objects"]


def test_unknown_response_field_is_a_validation_error():
    errors = validate_response({"major_action": None, "backend_state": {}},
                               ("major_action", "continuation", "utterances", "memory_updates", "waiting"))
    assert errors == ["unknown field: backend_state"]


def test_validate_response_accepts_the_fields_the_existing_providers_send():
    fields = ("major_action", "continuation", "utterances", "memory_updates", "waiting")
    good = {
        "major_action": {"action": "move", "params": {"target": "north"}, "reason": "hungry"},
        "continuation": {"destination": None, "task": {"action": "move", "params": {}},
                         "interrupt_on": ["encounter"], "hunger_threshold": 2.0,
                         "energy_threshold": 35, "poll_each_turn": False},
        "utterances": [{"target": "Ben", "text": "Hello.", "raw": {"topic": "greeting"}}],
        "memory_updates": [{"content": "Ben was kind."}],
        "waiting": False,
    }
    assert validate_response(good, fields) == []
    assert validate_response({"major_action": None, "continuation": None}, fields) == []


@pytest.mark.parametrize("bad, message", [
    ({"major_action": {"action": ""}}, "major_action.action must be a non-empty string"),
    ({"major_action": "rest"}, "major_action must be an object or null"),
    ({"waiting": "no"}, "waiting must be true or false"),
    ({"memory_updates": [1]}, "memory_updates must be a list of objects"),
    ({"continuation": {"interrupt_on": "encounter"}}, "continuation.interrupt_on must be a list of strings"),
    ({"utterances": [{"text": 5}]}, "utterances.text must be a string"),
])
def test_each_structural_rule_reports_a_fixed_message(bad, message):
    fields = ("major_action", "continuation", "utterances", "memory_updates", "waiting")
    assert message in validate_response(bad, fields)


# -- repeated invalid output and provider failures ----------------------------

def test_repeated_invalid_output_returns_an_idle_response_and_counts_a_failure():
    provider = ScriptedProvider(NOT_JSON)
    backend = LLMBackend(_character(), provider, autopilot=False)
    response = backend.decide(_context())
    assert _idle(response)
    assert response.backend_state == {"llm_outcome": "idle_fallback", "llm_reason": "invalid_output"}
    assert len(provider.prompts) == 1 + MAX_REPAIRS
    state = backend.last_backend_state
    assert state["outcome"] == "idle_fallback" and state["reason"] == "invalid_output"
    assert (state["calls"], state["repairs_used"]) == (2, 1)
    assert (state["failures"], state["invalid_outputs"], state["successes"]) == (1, 1, 0)
    assert state["last_error"] == "output is not a JSON object"
    held = backend.dump_held_state().to_dict()["backend_state"]
    assert held["failures"] == 1 and held["calls"] == 2


def test_idle_fallback_in_a_game_turn_advances_the_world_and_never_raises():
    world, game = _world_game()
    provider = ScriptedProvider(NOT_JSON)
    game.set_backend("Ben", LLMBackend(game.characters["Ben"], provider, autopilot=False))
    game.submit_player_response(ActorResponse())
    turn = world._turn
    result = game.step()
    assert result["status"] == "advanced"
    assert world._turn == turn + 1
    assert _idle(game.last_responses["Ben"])
    assert game.backends["Ben"].counts["failures"] == 1


def test_provider_exception_is_not_repaired_counted_and_does_not_reach_the_world():
    provider = ScriptedProvider(TimeoutError("read timed out"))
    backend = LLMBackend(_character(), provider, autopilot=False)
    response = backend.decide(_context())
    assert _idle(response)
    assert len(provider.prompts) == 1
    state = backend.last_backend_state
    assert (state["calls"], state["repairs_used"], state["failures"], state["provider_errors"]) == (1, 0, 1, 1)
    assert state["reason"] == "provider_error"
    assert state["last_error"] == "TimeoutError: read timed out"


def test_provider_error_text_that_looks_like_a_credential_is_dropped():
    key = "sk-live-0123456789abcdef0123456789"
    provider = ScriptedProvider(RuntimeError(f"Authorization: Bearer {key} rejected"))
    backend = LLMBackend(_character(), provider, autopilot=False)
    assert _idle(backend.decide(_context()))
    stored = backend.last_backend_state["last_error"]
    assert key not in stored and "Bearer" not in stored
    assert stored.startswith("[redacted")
    assert key not in json.dumps(backend.dump_held_state().to_dict())


def test_safe_error_truncates_and_redacts():
    spaced = "word " * 100
    assert safe_error(spaced) == " ".join(spaced.split())[:160]
    assert safe_error("x" * 500).startswith("[redacted")
    assert safe_error("name  with\n\n spaces") == "name with spaces"
    assert safe_error("GET https://host/v1?key=abc failed").startswith("[redacted")
    assert safe_error("api_key=abc") .startswith("[redacted")
    assert safe_error("a" * 40).startswith("[redacted")


def test_a_bug_in_the_prompt_path_is_counted_not_raised():
    class BrokenBuilder(PromptBuilder):
        def build(self, context):
            raise KeyError("broken")

    backend = LLMBackend(_character(), ScriptedProvider(VALID), prompt_builder=BrokenBuilder(), autopilot=False)
    assert _idle(backend.decide(_context()))
    assert backend.counts["failures"] == 1
    assert backend.last_backend_state["reason"] == "internal_error"


# -- reports -----------------------------------------------------------------

def test_llm_report_and_game_report_count_residents_and_totals_beside_refusals():
    world = BigvilleWorld(autonomous_actors=False)
    for name in ("Ada", "Ben", "Cy"):
        world.add_actor(name, role="hand", home_cell=(1, 1))
    game = BigvilleGame(world, player="Ada")
    good = ScriptedProvider(VALID)
    bad = ScriptedProvider(TimeoutError("boom"))
    game.set_backend("Ben", LLMBackend(game.characters["Ben"], good))
    game.set_backend("Cy", LLMBackend(game.characters["Cy"], bad))
    game.submit_player_response(ActorResponse())
    assert game.step()["status"] == "advanced"
    report = game_report(game)
    assert "refusals" in report
    llm = report["llm"]
    assert llm["residents_count"] == 2
    assert llm["residents"]["Ben"]["successes"] == 1
    assert llm["residents"]["Cy"]["failures"] == 1
    assert llm["residents"]["Cy"]["last_error"] == "TimeoutError: boom"
    assert llm["total"]["calls"] == 2 and llm["total"]["failures"] == 1
    assert llm["total"]["decisions"] == 2
    assert llm["total"]["mean_latency_ms"] is not None


def test_llm_report_ignores_backends_without_llm_counts():
    world, game = _world_game()
    assert llm_report(game.backends) == {
        "residents_count": 0,
        "total": {"calls": 0, "repairs_used": 0, "repaired_successes": 0, "successes": 0,
                  "failures": 0, "provider_errors": 0, "invalid_outputs": 0, "decisions": 0,
                  "autopilot_turns": 0, "carry_ons": 0, "waits": 0, "deviations": 0, "turns": 0,
                  "fallbacks_by_cause": {}, "consults_by_reason": {}, "share_consulted": None,
                  "share_autopilot": None, "latency_ms_total": 0.0, "mean_latency_ms": None,
                  "call_latency_ms_total": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0,
                  "tokens_reasoning": 0, "per_day": {}, "threads": 0, "compactions": 0,
                  "full_consults": 0, "delta_consults": 0, "thread_chars_max": 0},
        "residents": {},
    }
