"""Phase 066: the continued session, the complete LLM log (thinking included), replay of threads, and stop and resume.

Every provider here is either the loopback stub (tests/llm_stub.py, 127.0.0.1 only) or an in-process fake. No
network is used and no .env is read. The API key in these tests is a fake value.
"""
from __future__ import annotations

import dataclasses
import gzip
import json

import pytest

from bigville.backends.llm import LLMBackend
from bigville.backends.thread import state_changes
from bigville.llm_log import LLMLog, LogCorrupt, attach, head_path, read_log, verify_log
from bigville.llm_scenario import RunDigest, build_llm_town
from bigville.llm_transcript import (RecordingProvider, ReplayProvider, Transcript, first_message_difference,
                                     prompt_hash, thread_key)
from bigville.providers import OpenAICompatibleProvider, ProviderResult
from bigville.reporting import game_report
from llm_stub import REST_REPLY, FakeProvider, StubServer, completion, varied_reply

FAKE_KEY = "sk-fake-phase066-0123456789abcdefghijklmnopqrstuvwxyz"
MARKER = "THINKING_MARKER_066"
THINKING = ("I weigh the bread against the hunger and the dry field. " * 80) + f"Note the key {FAKE_KEY} here."
THINKING_WITH_MARKER = THINKING + MARKER
# What the log holds: the thinking whole, with the API key (and nothing else) replaced.
THINKING_LOGGED = THINKING_WITH_MARKER.replace(FAKE_KEY, "[redacted key]")


def _thinking_completion(content: str) -> dict:
    body = completion(content, cost=0.002, reasoning=321)
    message = body["choices"][0]["message"]
    message["reasoning_content"] = THINKING_WITH_MARKER
    message["reasoning_details"] = [{"type": "reasoning.text", "text": THINKING_WITH_MARKER}]
    body["choices"][0]["finish_reason"] = "stop"
    return body


def _rest_with_key() -> str:
    return json.dumps({"major_action": {"action": "rest", "params": {}},
                       "utterances": [{"text": f"my key is {FAKE_KEY}"}]})


def _provider(stub: StubServer, **kwargs) -> OpenAICompatibleProvider:
    options = dict(base_url=stub.base_url, api_key=FAKE_KEY, model="glm-5.3-flash", run_id="p66",
                   min_interval=0.0, sleep=lambda seconds: None)
    options.update(kwargs)
    return OpenAICompatibleProvider(**options)


def _llm_backend(game, name=None):
    name = name or game.llm_residents[0]
    return name, game.backends[name]


def _consult(game, backend, name):
    """Force a consult this turn (the check-in rule is due when the last consult is forgotten)."""
    backend.gate.last_consult_turn = None
    return backend.decide(game._context(name))


def _header(headers: dict, name: str):
    """The stub records request headers as urllib sends them (capitalised), so match them case-insensitively."""
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def _text(backend, key: str) -> str:
    return str(backend.prompt_builder.pack["PROMPT_PACKET"]["thread"][key])


# -- the provider keeps the whole reply -------------------------------------------------------

def test_the_provider_returns_the_whole_reply_and_callers_still_get_its_text():
    seen = {}

    def script(index, body, headers):
        seen["session"] = _header(headers, "x-opencode-session")
        seen["body"] = body
        return 200, {"x-request-id": "req-066"}, _thinking_completion(REST_REPLY)

    with StubServer(script) as stub:
        provider = _provider(stub)
        reply = provider.complete({"system": "You are a test.", "packet": 1}, meta={"actor": "Ada"})
    assert isinstance(reply, ProviderResult) and isinstance(reply, str)
    assert reply == REST_REPLY
    call = reply.result
    assert call.reasoning_content == THINKING_LOGGED               # whole, never truncated
    assert call.reasoning_details == [{"type": "reasoning.text", "text": THINKING_LOGGED}]
    assert call.finish_reason == "stop"
    assert call.response_id == "stub-1" and call.request_id == "req-066"
    assert call.usage["completion_tokens_details"]["reasoning_tokens"] == 321
    assert call.cost == pytest.approx(0.002)
    assert call.attempts[0]["status"] == 200
    assert call.body["choices"][0]["message"]["reasoning_content"] == THINKING_LOGGED
    assert seen["session"] == "p66-Ada"
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert provider.last_call["ok"] is True


def test_a_thread_payload_is_sent_as_its_messages_under_the_threads_session():
    seen = {"bodies": [], "sessions": []}

    def script(index, body, headers):
        seen["bodies"].append(body)
        seen["sessions"].append(_header(headers, "x-opencode-session"))
        return 200, {}, completion(REST_REPLY)

    with StubServer(script) as stub:
        provider = _provider(stub)
        provider.complete({"messages": [{"role": "system", "content": "S"},
                                        {"role": "user", "content": "U"}]},
                          meta={"actor": "Ada", "session": "Ada-t3"})
    assert seen["sessions"] == ["p66-Ada-t3"]
    assert seen["bodies"][0]["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]


# -- the continued session ----------------------------------------------------------------------

def test_a_second_consult_sends_the_changes_and_the_reply_comes_back_as_the_assistant_message():
    with StubServer(lambda i, b, h: (200, {}, completion(REST_REPLY))) as stub:
        game = build_llm_town(_provider(stub), llm_residents=1)
        name, backend = _llm_backend(game)
        for _ in range(3):
            _consult(game, backend, name)
    rid = backend._resident()
    bodies = [request["body"] for request in stub.requests]
    assert len(bodies) == 3
    second = bodies[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[2]["content"] == REST_REPLY                       # the content of the first reply, nothing else
    assert len(second[3]["content"]) < len(second[1]["content"])    # a delta, not the whole packet
    assert '"changes"' in second[3]["content"]
    sessions = {_header(request["headers"], "x-opencode-session") for request in stub.requests}
    assert sessions == {"p66-" + rid}                               # one session for the thread's life
    counts = backend.llm_counts
    assert counts["threads"] == 1 and counts["full_consults"] == 1 and counts["delta_consults"] == 2
    assert counts["thread_length"][rid] == 3


def test_full_packets_come_every_interval_and_a_new_thread_starts_when_the_budget_is_passed():
    with StubServer(lambda i, b, h: (200, {}, completion(REST_REPLY))) as stub:
        game = build_llm_town(_provider(stub), llm_residents=1)
        name, backend = _llm_backend(game)
        rid = backend._resident()
        backend.full_every = 2
        _consult(game, backend, name)                               # full: the first message of the thread
        messages = backend.threads[rid].messages
        backend.thread_chars = len(messages[0]["content"]) + len(messages[1]["content"]) + 500
        _consult(game, backend, name)                               # the budget is passed: a new thread, full
        backend.thread_chars = 10 ** 9
        _consult(game, backend, name)                               # a delta (since_full is 0)
        _consult(game, backend, name)                               # a delta (since_full is 1)
        _consult(game, backend, name)                               # since_full has reached 2: full again
    bodies = [request["body"]["messages"] for request in stub.requests]
    headers = [_header(request["headers"], "x-opencode-session") for request in stub.requests]
    assert headers[0] == "p66-" + rid
    assert headers[1] == headers[2] == headers[3] == headers[4] == "p66-" + rid + "-t1"
    assert bodies[1][1]["content"].startswith(_text(backend, "start"))
    assert '"context"' in bodies[1][1]["content"]                   # the new thread's first message is the full packet
    assert '"changes"' in bodies[2][-1]["content"]
    assert '"changes"' in bodies[3][-1]["content"]
    assert bodies[4][-1]["content"].startswith(_text(backend, "full"))
    counts = backend.llm_counts
    assert counts["compactions"] == 1 and counts["threads"] == 2
    assert counts["full_consults"] == 3 and counts["delta_consults"] == 2


def test_the_new_thread_carries_the_persona_and_the_held_lessons():
    with StubServer(lambda i, b, h: (200, {}, completion(REST_REPLY))) as stub:
        game = build_llm_town(_provider(stub), llm_residents=1)
        name, backend = _llm_backend(game)
        backend.thread_chars = 1                                    # every consult after the first compacts
        _consult(game, backend, name)
        _consult(game, backend, name)
    start = stub.requests[1]["body"]["messages"][1]["content"]
    assert start.startswith(_text(backend, "start"))
    body = json.loads(start[len(_text(backend, "start")) + 1:])
    lead = body["context"]["private"]["lead"]
    assert lead[0].startswith("You are ")                          # the persona card leads the new thread
    assert any("Usually now:" in line for line in lead)            # and what the resident would usually do now
    assert "lessons" in body["context"]["private"]


def test_a_repaired_reply_is_one_extra_message_and_the_failed_text_is_not_echoed():
    with StubServer(lambda i, b, h: (200, {}, completion("this is not json") if i == 0
                                     else completion(REST_REPLY))) as stub:
        game = build_llm_town(_provider(stub), llm_residents=1)
        name, backend = _llm_backend(game)
        response = _consult(game, backend, name)
    assert response.major_action is not None
    first, repair = stub.requests[0]["body"]["messages"], stub.requests[1]["body"]["messages"]
    assert len(repair) == len(first) + 1
    assert repair[-1]["role"] == "user" and "errors" in repair[-1]["content"]
    assert "this is not json" not in json.dumps(repair)
    thread = backend.threads[backend._resident()].messages
    # The repair request is kept in the thread, with the reply it led to. The failed reply is not.
    assert [m["role"] for m in thread] == ["system", "user", "user", "assistant"]
    assert "this is not json" not in json.dumps(thread)
    assert backend.llm_counts["repaired_successes"] == 1


# -- the complete log -----------------------------------------------------------------------------

def test_the_log_keeps_the_whole_reply_thinking_included_and_redacts_only_the_key(tmp_path):
    log_path = tmp_path / "llm.jsonl"
    with StubServer(lambda i, b, h: (200, {}, _thinking_completion(_rest_with_key()))) as stub:
        provider = _provider(stub)
        game = build_llm_town(provider, llm_residents=1)
        name, backend = _llm_backend(game)
        assert attach(game.backends, LLMLog(log_path, run_id="p66", redact=provider.redact)) == 1
        _consult(game, backend, name)
        _consult(game, backend, name)
    rid = backend._resident()
    raw = log_path.read_bytes()
    assert FAKE_KEY.encode() not in raw
    assert b"[redacted key]" in raw
    records = read_log(log_path)
    assert [r["kind"] for r in records] == ["call", "call"]
    first = records[0]
    assert first["response"]["reasoning_content"] == THINKING_LOGGED
    assert first["response"]["reasoning_details"][0]["text"].endswith("[redacted key] here." + MARKER)
    assert first["response"]["usage"]["completion_tokens_details"]["reasoning_tokens"] == 321
    assert first["messages"][0]["role"] == "system" and first["messages"][1]["role"] == "user"
    assert first["resident"] == rid and first["thread"] == f"{rid}/t0" and first["turn"] == 0
    assert first["outcome"] == "accepted" and first["fallback_cause"] is None
    assert records[1]["mode"] == "delta" and records[1]["consult_no"] == 2
    assert verify_log(log_path).ok
    # The log is the only place the thinking goes: not the requests, the world's report, the backend's state, the
    # held state or the thread.
    for request in stub.requests:
        assert MARKER not in json.dumps(request["body"])
    assert MARKER not in json.dumps(game_report(game))
    assert MARKER not in json.dumps(backend.last_backend_state)
    assert MARKER not in json.dumps(dataclasses.asdict(backend.dump_held_state()), default=str)
    assert MARKER not in json.dumps(backend.to_dict())
    for line in backend.threads[rid].messages:
        assert MARKER not in line["content"]


def test_thinking_is_absent_from_the_replay_key_and_from_the_recorded_prompts(tmp_path):
    path = tmp_path / "run.jsonl"
    with StubServer(lambda i, b, h: (200, {}, _thinking_completion(REST_REPLY))) as stub:
        provider = _provider(stub)
        recorder = RecordingProvider(provider, Transcript(path, run_id="p66", redact=provider.redact))
        game = build_llm_town(recorder, llm_residents=1)
        name, backend = _llm_backend(game)
        _consult(game, backend, name)
        _consult(game, backend, name)
    text = path.read_text(encoding="utf-8")
    assert MARKER not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert len(records) == 2
    for record in records:
        assert MARKER not in json.dumps(thread_key(record["prompt"]))


def test_a_deleted_or_edited_record_fails_the_chain_check(tmp_path):
    path = tmp_path / "chain.jsonl"
    log = LLMLog(path, run_id="chain")
    for number in range(4):
        log.append({"kind": "call", "turn": number, "response": {"content": f"reply {number}"}})
    check = verify_log(path)
    assert check.ok and check.last_seq == 4 and check.head_checked
    lines = path.read_text(encoding="utf-8").splitlines()

    edited = list(lines)
    edited[1] = edited[1].replace("reply 1", "reply X")
    (tmp_path / "edited.jsonl").write_text("\n".join(edited) + "\n", encoding="utf-8")
    check = verify_log(tmp_path / "edited.jsonl")
    assert not check.ok and any("edited" in problem for problem in check.problems)

    removed_middle = [lines[0], lines[2], lines[3]]
    (tmp_path / "middle.jsonl").write_text("\n".join(removed_middle) + "\n", encoding="utf-8")
    check = verify_log(tmp_path / "middle.jsonl", head=head_path(path))
    assert not check.ok and any("sequence" in problem for problem in check.problems)

    cut_end = lines[:-1]
    (tmp_path / "cut.jsonl").write_text("\n".join(cut_end) + "\n", encoding="utf-8")
    check = verify_log(tmp_path / "cut.jsonl", head=head_path(path))
    assert not check.ok and any("head file" in problem for problem in check.problems)


def test_a_gzip_log_is_appendable_readable_and_verifiable(tmp_path):
    path = tmp_path / "llm.jsonl.gz"
    LLMLog(path, run_id="gz", gzip=True).append({"kind": "call", "response": {"reasoning_content": THINKING_WITH_MARKER}})
    reopened = LLMLog(path, run_id="gz", gzip=True)            # continues the chain after verifying it
    reopened.append({"kind": "refused", "fallback_cause": "call_cap"})
    assert path.read_bytes()[:2] == b"\x1f\x8b"
    assert verify_log(path).ok and verify_log(path).last_seq == 2
    records = read_log(path)
    assert [r["kind"] for r in records] == ["call", "refused"]
    assert records[0]["response"]["reasoning_content"] == THINKING_WITH_MARKER    # no redactor on this log


def test_a_log_that_fails_verification_is_not_appended_to(tmp_path):
    path = tmp_path / "bad.jsonl"
    LLMLog(path, run_id="x").append({"kind": "call"})
    path.write_text(path.read_text().replace('"call"', '"edit"'), encoding="utf-8")
    with pytest.raises(LogCorrupt):
        LLMLog(path, run_id="x")


# -- replay of a continued thread ----------------------------------------------------------------

def test_a_recorded_continued_session_replays_with_the_same_replies(tmp_path):
    path = tmp_path / "thread.jsonl"
    provider = FakeProvider(varied_reply)
    game = build_llm_town(RecordingProvider(provider, Transcript(path, run_id="p66")), llm_residents=1)
    name, backend = _llm_backend(game)
    recorded = [_consult(game, backend, name) for _ in range(3)]
    replay = ReplayProvider(path)
    replay_game = build_llm_town(replay, llm_residents=1)
    _, replay_backend = _llm_backend(replay_game)
    replayed = [_consult(replay_game, replay_backend, name) for _ in range(3)]
    assert [r.major_action for r in replayed] == [r.major_action for r in recorded]
    assert replay.mismatches == []
    assert replay_backend.llm_counts["successes"] == 3


def test_a_replay_whose_thread_differs_names_the_first_message_that_differs(tmp_path):
    path = tmp_path / "thread.jsonl"
    provider = FakeProvider(varied_reply)
    game = build_llm_town(RecordingProvider(provider, Transcript(path, run_id="p66")), llm_residents=1)
    name, backend = _llm_backend(game)
    for _ in range(2):
        _consult(game, backend, name)
    replay = ReplayProvider(path)
    changed_game = build_llm_town(replay, llm_residents=1)
    _, changed = _llm_backend(changed_game)
    changed.full_every = 0                                       # the second consult sends the full packet, not a delta
    _consult(changed_game, changed, name)
    _consult(changed_game, changed, name)
    assert len(replay.mismatches) == 1
    assert "message 3 (user) differs from the recording" in replay.mismatches[0]
    assert changed.llm_counts["fallbacks_by_cause"]["provider_error"] == 1


def test_the_replay_names_the_first_differing_message():
    recorded = [{"role": "system", "content": "S"}, {"role": "user", "content": "A"},
                {"role": "assistant", "content": "R"}, {"role": "user", "content": "B"}]
    requested = recorded[:3] + [{"role": "user", "content": "B2"}]
    assert first_message_difference(requested, recorded) == "message 3 (user) differs from the recording"
    assert first_message_difference(recorded, recorded) is None
    assert prompt_hash({"messages": requested}) != prompt_hash({"messages": recorded})


# -- stop and resume ----------------------------------------------------------------------------

def test_a_run_stopped_and_resumed_continues_the_thread_and_matches_the_uninterrupted_run():
    turns, stop_at = 6, 3

    def run(stop: bool):
        provider = FakeProvider(varied_reply)
        game = build_llm_town(provider, llm_residents=2)
        names = list(game.llm_residents)
        digest = RunDigest()
        for turn in range(turns):
            for n in names:                                  # a consult every turn, so threads grow across the stop
                game.backends[n].gate.last_consult_turn = None
            if stop and turn == stop_at:
                # Stop: write each backend's state as JSON, then resume each backend from it.
                states = {n: json.loads(json.dumps(game.backends[n].to_dict(), sort_keys=True)) for n in names}
                shared = game.backends[names[0]].budget
                for n in names:
                    old = game.backends[n]
                    game.set_backend(n, LLMBackend.from_dict(states[n], old.character, provider, budget=shared))
            assert game.step()["status"] == "advanced"
            digest.add(game)
        sent: dict[str, list] = {}
        for call in provider.calls:
            sent.setdefault(call["meta"]["actor"], []).append(call["payload"]["messages"])
        return digest.hexdigest(), sent, game

    control_digest, control_sent, _ = run(stop=False)
    resumed_digest, resumed_sent, game = run(stop=True)
    assert resumed_digest == control_digest
    assert resumed_sent == control_sent
    # Calls after the stop carry the replies made before it: the thread continued, it was not restarted.
    after_stop = [calls[stop_at:] for calls in resumed_sent.values() if len(calls) > stop_at]
    assert after_stop                                    # some resident consulted again after the stop
    assert all(any(m["role"] == "assistant" for m in calls[0]) for calls in after_stop)


def test_the_backend_state_round_trips_through_json_and_refuses_another_resident():
    provider = FakeProvider(varied_reply)
    game = build_llm_town(provider, llm_residents=2)
    name, backend = _llm_backend(game)
    for _ in range(3):
        _consult(game, backend, name)
    data = json.loads(json.dumps(backend.to_dict(), sort_keys=True))
    restored = LLMBackend.from_dict(data, backend.character, provider, budget=backend.budget)
    assert json.dumps(restored.to_dict(), sort_keys=True) == json.dumps(backend.to_dict(), sort_keys=True)
    stranger = [n for n in game.llm_residents if n != name][0]
    with pytest.raises(ValueError):
        LLMBackend.from_dict(data, game.characters[stranger], provider)
    with pytest.raises(ValueError):
        LLMBackend.from_dict(dict(data, schema="other"), backend.character, provider)


def test_state_changes_names_what_changed_and_what_went():
    before = {"private": {"lead": ["a"], "notes": ["x"]}, "public": {"now": {"time": "dawn"}, "can": []}}
    after = {"private": {"lead": ["a"], "notes": ["x", "y"]}, "public": {"now": {"time": "noon"}}}
    delta = state_changes(before, after)
    assert delta["changes"] == {"private": {"notes": ["x", "y"]}, "public": {"now": {"time": "noon"}}}
    assert delta["removed"] == ["public.can"]
