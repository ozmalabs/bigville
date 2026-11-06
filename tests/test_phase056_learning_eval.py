"""Phase 056: learning evaluation. Fake providers only; no network; no key is read."""
import json

import pytest

from bigville.backends.prompts import pack_hash
from bigville.learning_eval import (PACKET_SCHEMA, ScriptedLearner, ScriptedNonLearner, compare_controls,
                                    guard_log, guard_message, render_markdown, run_arm, run_controls)
from bigville.llm_log import LLMLog
from domains.pack import load_pack

NOT_DONE = load_pack("bigville")["VIEW_WORDS"]["not_done"]
TURNS = 8


def _user_message(public, *, delta=False):
    body = {"changes": {"public": public}} if delta else {"context": {"public": public}, "schema": PACKET_SCHEMA}
    return {"role": "user", "content": "Prose before the packet. " + json.dumps(body, sort_keys=True)}


def _payload(*messages):
    return {"messages": [{"role": "system", "content": "system text"}, *messages]}


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    return run_controls(turns=TURNS, log_dir=tmp_path_factory.mktemp("controls"))


def test_the_learner_stops_repeating_a_refused_action_and_the_non_learner_does_not(controls):
    cmp_ = controls["comparison"]
    learner, non = cmp_["learner"], cmp_["nonlearner"]
    assert learner["failures"] > 0 and non["failures"] > 0
    assert learner["repeat_mistake_rate"] == 0.0
    assert non["repeat_mistake_rate"] > 0.5
    assert learner["repeat_mistake_rate"] < non["repeat_mistake_rate"]
    assert learner["tries_before_switch_mean"] == 1.0
    assert non["tries_before_switch_mean"] is None and non["censored_episodes"] > 0
    assert learner["lessons_recorded"] > 0 and learner["lessons_used"] > 0
    assert non["lessons_recorded"] == 0
    assert not learner["void"] and not non["void"]


def test_the_control_metrics_are_deterministic(controls):
    again = run_arm("control_nonlearner", kind="llm", provider="nonlearner", turns=TURNS, autopilot=False,
                    budget=False)
    assert again["digest"] == controls["arms"]["nonlearner"]["digest"]
    assert again["residents"] == controls["arms"]["nonlearner"]["residents"]


def test_a_simple_run_is_deterministic_and_carries_no_lessons():
    first = run_arm("simple", kind="simple", turns=5)
    second = run_arm("simple", kind="simple", turns=5)
    assert first["digest"] == second["digest"]
    assert first["residents"] == second["residents"]
    assert all(row["summary"]["lessons_recorded"] == 0 for row in first["residents"].values())


def test_the_learner_reacts_to_a_refusal_in_public_last_and_writes_a_lesson():
    learner = ScriptedLearner("bigville")
    refused = {"action": "lift", "outcome": NOT_DONE, "reason": "malformed"}
    first = json.loads(learner.complete(_payload(_user_message({})), {"actor": "A"}))
    assert first["major_action"]["params"]["target"] == "1"
    second = json.loads(learner.complete(_payload(_user_message({"last": refused})), {"actor": "A"}))
    assert second["major_action"]["params"]["target"] == "2"
    assert second["memory_updates"][0]["kind"] == "lesson"
    # A delta packet lists only the changes. The refused outcome is still the last one shown, so a second
    # refusal of the same action leads to a switch to a listed option, with another lesson.
    options = [{"handle": "rest", "action": "rest", "what": "rest"}]
    third = json.loads(learner.complete(_payload(_user_message({"can": options}, delta=True)), {"actor": "A"}))
    assert third["major_action"]["target"] == "rest"
    assert third["major_action"]["action"] == "rest"
    assert third["memory_updates"][0]["kind"] == "lesson"


def test_the_non_learner_sends_the_same_action_whatever_it_is_told():
    non = ScriptedNonLearner("bigville")
    replies = [json.loads(non.complete(_payload(_user_message({"last": {"outcome": NOT_DONE}})), {"actor": "B"}))
               for _ in range(3)]
    assert all(reply["major_action"] == replies[0]["major_action"] for reply in replies)
    assert "memory_updates" not in replies[0]


def test_the_guard_voids_a_run_with_a_leak_and_passes_a_clean_one(tmp_path):
    clean = tmp_path / "clean.jsonl"
    leaky = tmp_path / "leaky.jsonl"
    ok_message = _user_message({"now": {"day": "market day"}, "last": {}})
    # The model's own reply is not a prompt: a number in it is not a leak.
    reply = {"role": "assistant", "content": '{"major_action": {"params": {"target": "1"}}}'}
    for path, message in ((clean, ok_message),
                          (leaky, _user_message({"now": {"day": "market day"}, "score": 0.4}))):
        log = LLMLog(path, run_id="t", head=False)
        log.append({"kind": "call", "resident": "A", "turn": 1, "messages": [
            {"role": "system", "content": "You are one resident."}, message, reply]})
    assert guard_log(clean)["void"] is False
    assert guard_log(clean)["prompts_checked"] == 2
    verdict = guard_log(leaky)
    assert verdict["void"] is True
    assert any("referee-only key" in v["problem"] for v in verdict["violations"])


def test_the_guard_catches_a_raw_number_and_allows_the_packets_own_counts():
    assert guard_message(json.dumps({"context": {"public": {"now": {"hour": 9}}}}), "bigville")
    assert not guard_message(json.dumps({"context": {"omitted": {"knows": 38}, "public": {
        "can": [{"handle": "target:0", "action": "walk", "what": "walk to the mill"}]}}}), "bigville")


def test_the_report_names_the_scenario_seed_pack_hash_and_prompt_schema(controls):
    record = {"scenario": "town100", "seed": 305000, "pack": "bigville",
              "pack_hash": pack_hash(load_pack("bigville")),
              "prompt_schema": PACKET_SCHEMA, "digest": "x", "void_arms": [],
              "controls": {"arms": controls["arms"], "comparison": compare_controls(controls["arms"])},
              "arms": {}, "marginal": None}
    text = render_markdown(record)
    assert "Scenario `town100`" in text and "seed `305000`" in text
    assert f"pack hash `{record['pack_hash']}`" in text and f"prompt schema `{PACKET_SCHEMA}`" in text
    assert "| repeat-mistake rate | 0.000 |" in text
