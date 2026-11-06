"""Phase 059: the autopilot carries an LLM resident between consults. Fake providers only; no network.

Each test names one acceptance item of the brief. The contexts are built by hand, so each trigger can be
set exactly. Two tests run a game (norms_property_sharing, autonomous) to check the plan and the call count.
"""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest

from bigville.api import create_game
from bigville.backends import ActorContext, DeterministicBackend, LLMBackend
from bigville.backends.autopilot import CallBudget, ConsultGate
from bigville.backends.llm import validate_response
from bigville.character import CharacterDefinition
from bigville.reporting import llm_report
from domains.autopilot import (boundary_consult_chance, habit_roll, max_quiet_ticks, routine_strength,
                               usual_block, usual_words)
from domains.autopilot_check import check_autopilot


# -- fixtures ----------------------------------------------------------------

LOW = {"role_identity": 0.0, "arousal": 1.0, "prior_world_safe": 0.0}    # routine_strength 0: consulted often
HIGH = {"role_identity": 1.0, "arousal": 0.0, "prior_world_safe": 1.0}   # routine_strength 1: a creature of habit
MOVE = {"action": "move", "destination": (4, 4), "score": 10.0, "target": "north"}

CARRY = '{"utterances": []}'                              # no major_action: carry on as usual
WAIT = '{"major_action": {"action": "wait"}}'
REST = '{"major_action": {"action": "rest", "params": {}}}'
NOT_JSON = "I think you should rest."
WAITING_TRUE = '{"major_action": {"action": "rest"}, "waiting": true}'


class Fake:
    """Returns the scripted outputs in order, then repeats the last one. An exception instance is raised.
    ``last_cost`` is what the provider reports for its last call (the spend cap reads it)."""

    def __init__(self, *script, cost=None):
        self.script = list(script)
        self.prompts: list[dict] = []
        self.last_cost = cost

    def complete(self, prompt):
        self.prompts.append(copy.deepcopy(prompt))
        item = self.script[min(len(self.prompts), len(self.script)) - 1]
        if isinstance(item, BaseException):
            raise item
        return item


def _char(name="Ada", *, role="farmer", personality=LOW):
    return CharacterDefinition(character_id=name, name=name,
                               identity={"role": role, "life_stage": "adult"}, personality=dict(personality))


def _obs(*, hour=10.0, day=0.0, hunger=0.0, energy=80.0, nearby=(), heard=(), outcome=None, events=()):
    return {"calendar": {"hour": hour, "day": day, "season": "spring", "weather": "clear"},
            "hunger": hunger, "energy": energy, "nearby_residents": list(nearby),
            "heard_utterances": list(heard), "last_outcome": outcome, "physical_events": list(events)}


def _view(name="Ada"):
    """A minimal agent view (Phase 054: an LLM resident's prompt is built from the view, never the raw context)."""
    return {"mode": "agent", "actor": name,
            "self": {"name": name, "job": "farmer", "life_stage": "an adult", "age": "grown"},
            "now": {"time": "at mid-morning"}, "around": {"people": [], "heard": [], "seen": [], "things": []},
            "can": [], "last": {}}


def _ctx(turn, *, character=None, affordances=(MOVE,), backend_state=None, **obs):
    context = ActorContext(character or _char(), turn, _obs(**obs), [dict(a) for a in affordances],
                           agent_view=_view())
    if backend_state:
        context.backend_state.update(backend_state)
    return context


def _autopilot_move(character=None):
    """What the autopilot does with MOVE as the only affordance, at the first turn."""
    return DeterministicBackend(character or _char()).decide(_ctx(1)).major_action


# -- the autopilot's action replaces idle ------------------------------------

def test_a_provider_error_gives_the_autopilots_action_and_is_counted():
    expected = _autopilot_move()
    backend = LLMBackend(_char(), Fake(TimeoutError("read timed out")))
    response = backend.decide(_ctx(1))
    assert response.major_action is not None
    assert response.major_action.action == expected.action == "move"
    assert response.major_action.params["destination"] == (4, 4)
    assert response.continuation is not None
    assert response.backend_state["llm_fallback"] == "provider_error"
    counts = backend.llm_counts
    assert counts["failures"] == 1 and counts["provider_errors"] == 1
    assert counts["fallbacks_by_cause"]["provider_error"] == 1
    assert counts["autopilot_turns"] == 0
    assert backend.last_backend_state["outcome"] == "fallback"
    assert backend.last_backend_state["reason"] == "provider_error"


def test_an_invalid_reply_is_repaired_once_and_then_falls_back_to_the_autopilot():
    backend = LLMBackend(_char(), Fake(NOT_JSON, NOT_JSON))
    response = backend.decide(_ctx(1))
    assert response.major_action.action == "move"
    counts = backend.llm_counts
    assert counts["calls"] == 2 and counts["repairs_used"] == 1
    assert counts["invalid_outputs"] == 1 and counts["failures"] == 1
    assert counts["fallbacks_by_cause"]["invalid_output"] == 1


def test_an_invalid_reply_repaired_on_the_second_call_is_accepted():
    provider = Fake(NOT_JSON, REST)
    backend = LLMBackend(_char(), provider)
    response = backend.decide(_ctx(1))
    assert response.major_action.action == "rest"
    assert provider.prompts[1]["repair"] == {"errors": ["output is not a JSON object"]}
    counts = backend.llm_counts
    assert (counts["successes"], counts["failures"], counts["repaired_successes"]) == (1, 0, 1)
    assert backend.last_backend_state["outcome"] == "repaired"


def test_waiting_true_is_never_accepted_and_the_repair_says_why():
    provider = Fake(WAITING_TRUE, WAITING_TRUE)
    backend = LLMBackend(_char(), provider)
    response = backend.decide(_ctx(1))
    assert response.waiting is False
    assert response.major_action.action == "move"
    assert provider.prompts[1]["repair"]["errors"] == [
        "waiting: true is not accepted; to do nothing, use major_action with action wait"]
    assert backend.llm_counts["fallbacks_by_cause"]["invalid_output"] == 1
    assert validate_response({"waiting": True}, ("waiting",)) != []


def test_the_validator_still_accepts_waiting_false():
    assert validate_response({"waiting": False}, ("waiting",)) == []


# -- caps -------------------------------------------------------------------

def test_a_call_cap_falls_back_without_calling_the_provider_and_resets_by_day():
    provider = Fake(REST)
    backend = LLMBackend(_char(), provider, budget=CallBudget(max_calls_per_day=1))
    backend.decide(_ctx(1))                                           # check-in: the one call of day 0
    assert len(provider.prompts) == 1
    capped = backend.decide(_ctx(2, hunger=2.5))                      # a hunger crossing wants a second call
    assert len(provider.prompts) == 1
    assert capped.major_action.action == "move"
    assert backend.llm_counts["fallbacks_by_cause"]["call_cap"] == 1
    backend.decide(_ctx(3, day=1.0, hunger=2.5, energy=30.0))        # day 1: the budget is fresh
    assert len(provider.prompts) == 2


def test_a_spend_cap_falls_back_once_the_reported_cost_reaches_it():
    provider = Fake(REST, cost=1.5)
    backend = LLMBackend(_char(), provider, budget=CallBudget(max_spend=1.0))
    backend.decide(_ctx(1))
    assert len(provider.prompts) == 1
    response = backend.decide(_ctx(2, hunger=2.5))
    assert len(provider.prompts) == 1
    assert response.major_action.action == "move"
    assert backend.llm_counts["fallbacks_by_cause"]["spend_cap"] == 1


# -- ordinary turns and triggers --------------------------------------------

def test_an_ordinary_routine_turn_does_not_call_the_provider_and_a_check_in_does():
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    quiet = backend.gate.quiet_ticks
    assert quiet == 24                                                # the least habitual resident
    backend.decide(_ctx(1))                                           # the first turn is a check-in
    for turn in range(2, quiet + 1):
        backend.decide(_ctx(turn))
    assert len(provider.prompts) == 1
    assert backend.llm_counts["autopilot_turns"] == quiet - 1
    backend.decide(_ctx(quiet + 1))                                   # quiet ticks after the last consult
    assert len(provider.prompts) == 2
    assert backend.llm_counts["consults_by_reason"]["check_in"] == 2


@pytest.mark.parametrize("name, first, second, reason", [
    ("hunger_threshold", {"hunger": 0.0}, {"hunger": 2.5}, "hunger_threshold"),
    ("energy_threshold", {"energy": 80.0}, {"energy": 30.0}, "energy_threshold"),
    ("tie_in_view", {"nearby": []},
     {"nearby": [{"id": "Ben", "tie_strength": 0.5, "band_code": 0.0}]}, "tie_in_view"),
    ("spoken_to", {}, {"heard": [{"target": "Ada", "speaker": "Ben", "text": "hi", "turn": 2.0}]}, "spoken_to"),
    ("task_failed", {}, {"outcome": {"turn": 2, "action": "move", "applied": False, "reason": "blocked"}},
     "task_failed"),
    ("world_event", {}, {"events": [{"target": "Ada", "action": "take", "outcome": "taken"}]}, "world_event"),
    ("routine_boundary", {"hour": 8.0}, {"hour": 9.5}, "routine_boundary"),
])
def test_each_interrupt_and_routine_boundary_calls_the_provider(name, first, second, reason):
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1, **first))
    backend.decide(_ctx(2, **second))
    assert backend.llm_counts["consults_by_reason"].get(reason) == 1, name
    assert provider.prompts[-1]["context"]["public"]["consult"]["why_consulted"] == reason


def test_an_idle_autopilot_asks_the_model_once_per_quiet_span():
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1))                                           # the check-in
    for turn in range(2, 25):
        backend.decide(_ctx(turn, affordances=()))                    # idle, inside the quiet span: not asked
    assert len(provider.prompts) == 1
    backend.decide(_ctx(25, affordances=()))                          # the span is over: asked, and idle
    assert len(provider.prompts) == 2
    assert backend.llm_counts["consults_by_reason"] == {"check_in": 1, "nothing_to_do": 1}


def test_a_second_failure_with_the_same_reason_is_a_repeated_refusal():
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1))
    backend.decide(_ctx(2, outcome={"turn": 2, "action": "move", "applied": False, "reason": "blocked"}))
    backend.decide(_ctx(3, outcome={"turn": 3, "action": "move", "applied": False, "reason": "blocked"}))
    assert backend.llm_counts["consults_by_reason"].get("task_failed") == 1
    assert backend.llm_counts["consults_by_reason"].get("refusal_repeats") == 1


def test_a_routine_boundary_does_not_prompt_a_habitual_resident_when_the_roll_says_so():
    habit = _char(personality=HIGH)
    assert boundary_consult_chance(routine_strength(HIGH, {"role": "farmer"})) == pytest.approx(0.0)
    backend = LLMBackend(habit, Fake(CARRY))
    backend.decide(_ctx(1, character=habit, hour=8.0))
    backend.decide(_ctx(2, character=habit, hour=9.5))
    assert "routine_boundary" not in backend.llm_counts["consults_by_reason"]


# -- plans, carry-on and wait -----------------------------------------------

def test_a_reply_with_no_action_carries_on_as_usual_and_wait_idles():
    expected = _autopilot_move()
    carry = LLMBackend(_char(), Fake(CARRY))
    response = carry.decide(_ctx(1))
    assert response.major_action == expected
    assert response.continuation is not None and response.continuation.destination == (4, 4)
    assert carry.llm_counts["carry_ons"] == 1 and carry.llm_counts["deviations"] == 0

    idle = LLMBackend(_char(), Fake(WAIT))
    response = idle.decide(_ctx(1))
    assert response.major_action is None and response.continuation is None
    assert response.waiting is False
    assert idle.llm_counts["waits"] == 1
    assert idle.llm_counts["deviations"] == 1                         # waiting departs from the habit


def test_a_model_plan_holds_until_it_is_interrupted_and_then_the_model_is_asked_again():
    game = create_game(scenario="norms_property_sharing", default_backend="simple", autonomous=True)
    provider = Fake({"major_action": {"action": "rest", "params": {}},
                     "continuation": {"interrupt_on": ["hunger_threshold"]}}, CARRY)
    game.set_backend("Ben", LLMBackend(game.characters["Ben"], provider))
    game.step()
    assert len(provider.prompts) == 1
    assert game._continuations["Ben"].request.interrupt_on == ("hunger_threshold",)
    for _ in range(5):
        game.step()
    assert len(provider.prompts) == 1                                 # the plan holds: no call
    node = game.world._actors["Ben"]
    game.world.eng.set_attr(node, "hunger", 2.5)                      # the interrupt
    game.step()
    assert len(provider.prompts) == 2
    assert provider.prompts[1]["context"]["public"]["consult"]["why_consulted"] == "hunger_threshold"


def test_a_finished_plan_resumes_the_autopilot_without_a_consult_for_its_completion():
    game = create_game(scenario="norms_property_sharing", default_backend="simple", autonomous=True)
    here = game.world.actor_position("Ben")
    provider = Fake({"major_action": {"action": "move", "params": {"destination": here}},
                     "continuation": {"destination": here, "interrupt_on": ["hunger_threshold"]}}, CARRY)
    backend = LLMBackend(game.characters["Ben"], provider)
    game.set_backend("Ben", backend)
    game.step()                                                       # the model's plan
    assert len(provider.prompts) == 1
    game.step()                                                       # destination reached
    # The move to the cell the resident already stands on is refused, so the plan ends with a failed task.
    # That failure is the consult, not the completion: the completion itself prompts nothing.
    assert backend.llm_counts["consults_by_reason"] == {"nothing_to_do": 1, "task_failed": 1}
    assert game.last_responses["Ben"].backend_state.get("continuation_interrupted") == "destination_reached"


def test_a_completed_plan_with_a_successful_task_prompts_nothing_and_the_autopilot_acts():
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1))                                           # the check-in
    ctx = _ctx(2, backend_state={"continuation_interrupted": "destination_reached"},
               outcome={"turn": 2, "action": "move", "applied": True, "reason": ""})
    response = backend.decide(ctx)
    assert len(provider.prompts) == 1
    assert response.major_action.action == "move"
    assert backend.llm_counts["autopilot_turns"] == 1


def test_the_autopilot_still_sees_the_turns_a_plan_carries():
    game = create_game(scenario="norms_property_sharing", default_backend="simple", autonomous=True)
    provider = Fake({"major_action": {"action": "rest", "params": {}},
                     "continuation": {"interrupt_on": []}})
    backend = LLMBackend(game.characters["Ben"], provider)
    game.set_backend("Ben", backend)
    game.step()
    game.world.eng.set_attr(game.world._actors["Ben"], "hunger", 1.5)
    for _ in range(3):
        game.step()
    assert len(provider.prompts) == 1
    assert backend.gate.last_hunger == pytest.approx(1.5)


def test_a_run_of_200_turns_makes_far_fewer_calls_than_turns():
    game = create_game(scenario="norms_property_sharing", default_backend="simple", autonomous=True)
    provider = Fake(CARRY)
    backend = LLMBackend(game.characters["Ben"], provider)
    game.set_backend("Ben", backend)
    for _ in range(200):
        game.step()
    # A turn a plan holds does not reach decide(), so the decisions are counted, not the ticks.
    decisions = backend.llm_counts["successes"] + backend.llm_counts["failures"] + backend.llm_counts["autopilot_turns"]
    assert 0 < decisions <= 200
    assert len(provider.prompts) < 200 / 4                            # fewer calls than ticks, by a wide margin
    assert len(provider.prompts) <= 12 * 3                            # 12 a day for the three days 200 ticks span
    assert backend.llm_counts["autopilot_turns"] > 0


# -- routine strength and the counterfactual --------------------------------

def test_a_habitual_resident_is_consulted_less_than_a_resident_with_low_routine_strength():
    def consults(personality):
        provider = Fake(CARRY)
        backend = LLMBackend(_char(personality=personality), provider)
        for tick in range(1, 201):
            clock = tick % 96
            backend.decide(_ctx(tick, character=_char(personality=personality), hour=(6.0 + clock * 0.25) % 24.0,
                                day=float(tick // 96)))
        return len(provider.prompts)

    low, high = consults(LOW), consults(HIGH)
    assert high < low
    assert low < 200 and high >= 1


def test_deviations_are_counted_against_the_autopilots_would_be_choice():
    backend = LLMBackend(_char(), Fake(REST, '{"major_action": {"action": "move", '
                                          '"params": {"target": "north"}}}'))
    response = backend.decide(_ctx(1))                                # REST against a move: a departure
    assert response.major_action.action == "rest"
    assert backend.last_backend_state["departs"] is True
    assert backend.last_backend_state["would_be"] == {"action": "move"}
    assert backend.llm_counts["deviations"] == 1
    backend.decide(_ctx(2, hunger=2.5))                               # the same move as the autopilot
    assert backend.last_backend_state["departs"] is False
    assert backend.llm_counts["deviations"] == 1


def test_the_prompt_carries_what_the_resident_would_usually_do_now():
    provider = Fake(CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1, hour=10.0))
    context = provider.prompts[0]["context"]
    consult = context["public"]["consult"]
    usual_lines = [line for line in context["private"]["lead"] if "Usually now:" in line]
    assert consult["why_consulted"] == "check_in"
    assert len(usual_lines) == 1 and "(at work)" in usual_lines[0]
    assert "carries on as usual" in consult["rules"]


def test_a_reaction_consults_the_model_over_the_offered_options():
    options = ["resist", "brace", "yield"]

    def reaction_context():
        return ActorContext(_char(), 5, {**_obs(), "reaction": {"actor": "Ben", "on": "bread", "by": "hand",
                                                                "amount": 1.0, "late": False, "options": options}},
                            [{"action": "react", "option": option} for option in options], agent_view=_view())

    backend = LLMBackend(_char(), Fake('{"major_action": {"action": "react", "params": {"option": "brace"}}}'))
    assert backend.react(reaction_context()).backend_state["reaction"] == "brace"
    backend = LLMBackend(_char(), Fake(REST))
    response = backend.react(reaction_context())
    assert response.backend_state["reaction"] == "resist"             # the autopilot's fixed policy
    assert backend.llm_counts["fallbacks_by_cause"]["invalid_reaction"] == 1


# -- the numbers and the report ---------------------------------------------

def test_the_pack_numbers_order_habit_correctly():
    assert routine_strength(LOW, {"role": "farmer"}) == pytest.approx(0.0)
    assert routine_strength(HIGH, {"role": "farmer"}) == pytest.approx(1.0)
    assert max_quiet_ticks(1.0) > max_quiet_ticks(0.0) >= 1
    assert max_quiet_ticks(0.0) == 24 and max_quiet_ticks(1.0) == 192
    assert 0.0 <= habit_roll("Ada", "boundary", 3, "work") < 1.0
    assert habit_roll("Ada", "boundary", 3, "work") == habit_roll("Ada", "boundary", 3, "work")
    assert usual_block({"role": "no_such_job", "life_stage": "adult"}, {"hour": 10.0}) is None
    assert usual_words({"role": "no_such_job", "life_stage": "adult"}, {"hour": 10.0}) == ""


def test_the_gate_takes_the_triggers_the_pack_names_only():
    gate = ConsultGate(_char())
    assert "check_in" in gate.triggers and "nothing_to_do" in gate.triggers


@pytest.mark.parametrize("pack", ["bigville", "test_hamlet"])
def test_the_self_test_check_passes_for_both_packs(pack):
    errors, warnings, info = [], [], []
    check_autopilot(pack, errors, warnings, info)
    assert errors == [] and warnings == []
    assert any("all autopilot checks pass" in line for line in info)


def test_the_self_test_rejects_a_pack_whose_triggers_cannot_fire(tmp_path):
    source = Path(__file__).resolve().parent.parent / "packs" / "test_hamlet"
    copy_dir = tmp_path / "test_hamlet"
    shutil.copytree(source, copy_dir)
    path = copy_dir / "world" / "autopilot.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"check_in",', "", 1), encoding="utf-8")
    errors, warnings, info = [], [], []
    check_autopilot(str(copy_dir), errors, warnings, info)
    assert any("must include check_in" in message for message in errors)


def test_the_report_counts_consults_autopilot_turns_fallbacks_and_shares():
    provider = Fake(TimeoutError("boom"), CARRY)
    backend = LLMBackend(_char(), provider)
    backend.decide(_ctx(1))                                           # consult, provider error
    backend.decide(_ctx(2))                                           # no trigger: autopilot
    backend.decide(_ctx(3, hunger=2.5))                               # consult, carry on
    report = llm_report({"Ada": backend})
    total = report["total"]
    assert (total["successes"], total["failures"], total["autopilot_turns"]) == (1, 1, 1)
    assert total["turns"] == 3 and total["decisions"] == 2
    assert total["fallbacks_by_cause"]["provider_error"] == 1
    assert total["consults_by_reason"] == {"check_in": 1, "hunger_threshold": 1}
    assert total["share_consulted"] == pytest.approx(2 / 3, abs=1e-4)
    assert total["share_autopilot"] == pytest.approx(1 / 3, abs=1e-4)
