"""Phase 055: transcripts, replay, the changed-prompt mismatch, and the key never reaching a log or transcript.

The recorded runs use a fake provider (or the loopback stub for the key test). The replay game is rebuilt from the
same seed, so a replay repeats the recorded run turn for turn."""
from __future__ import annotations

import json
import logging

import pytest

from bigville.character import MemoryRecord
from bigville.llm_scenario import RunDigest, build_llm_town
from bigville.llm_transcript import (RecordedError, RecordingProvider, ReplayMismatch, ReplayProvider,
                                     Transcript, prompt_hash, read_transcript)
from bigville.providers import build_provider, build_transport, from_environment
from llm_stub import REST_REPLY, VARIED_REPLIES, FakeProvider, StubServer, completion, varied_reply

FAKE_KEY = "sk-test-0123456789abcdefghijklmnopqrstuvwxyz"
def _record(path, *, turns=6, residents=3, run_id="rec55", error=None):
    recorder = RecordingProvider(FakeProvider(varied_reply, error=error), Transcript(path, run_id=run_id))
    game = build_llm_town(recorder, llm_residents=residents)
    digest = RunDigest()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        digest.add(game)
    return game, digest.hexdigest()


def test_a_recorded_run_replays_with_the_same_digest_and_no_mismatch(tmp_path):
    path = tmp_path / "run.jsonl"
    _, recorded = _record(path)
    replay = ReplayProvider(path)
    game = build_llm_town(replay, llm_residents=3)
    digest = RunDigest()
    for _ in range(6):
        assert game.step()["status"] == "advanced"
        digest.add(game)
    assert digest.hexdigest() == recorded
    assert replay.mismatches == []
    assert replay.calls == len(read_transcript(path))


def test_a_changed_prompt_is_reported_as_a_mismatch_and_falls_back_counted(tmp_path):
    path = tmp_path / "run.jsonl"
    _record(path)
    replay = ReplayProvider(path)
    game = build_llm_town(replay, llm_residents=3)
    changed = game.llm_residents[0]
    game.characters[changed].memories.append(MemoryRecord(
        memory_id="changed-55", kind="lesson", content={"text": "Bread keeps better in the cold pantry."}, turn=0))
    for _ in range(6):
        assert game.step()["status"] == "advanced"
    assert replay.mismatches, "the changed prompt should be reported"
    assert all(message.startswith("replay mismatch at turn") for message in replay.mismatches)
    counts = game.backends[changed].llm_counts
    assert counts["fallbacks_by_cause"]["provider_error"] >= 1
    assert counts["last_error"].startswith("ReplayMismatch: replay mismatch at turn")
    assert issubclass(ReplayMismatch, RuntimeError)


def test_a_recorded_failure_replays_as_the_same_failure(tmp_path):
    path = tmp_path / "failed.jsonl"
    recorder = RecordingProvider(FakeProvider(VARIED_REPLIES[0], error=TimeoutError("boom")), Transcript(path, run_id="f"))
    game = build_llm_town(recorder, llm_residents=1)
    game.step()
    record = read_transcript(path)[0]
    assert record["error"] == "TimeoutError: boom" and "reply" not in record
    with pytest.raises(RecordedError, match="TimeoutError: boom"):
        ReplayProvider(path).complete(record["prompt"], meta={"turn": record["turn"], "actor": record["actor"]})


def test_the_transcript_is_append_only_with_one_line_per_call(tmp_path):
    path = tmp_path / "append.jsonl"
    first_game, _ = _record(path, turns=2, residents=2, run_id="one")
    before = path.read_text(encoding="utf-8").splitlines()
    _record(path, turns=2, residents=2, run_id="two")
    after = path.read_text(encoding="utf-8").splitlines()
    assert after[:len(before)] == before
    assert len(after) > len(before)
    records = [json.loads(line) for line in after]
    for record in records:
        assert {"schema", "run_id", "turn", "actor", "attempt", "prompt_hash", "prompt", "latency_ms"} <= set(record)
        assert ("reply" in record) != ("error" in record)
        assert prompt_hash(record["prompt"]) == record["prompt_hash"]
    assert {record["run_id"] for record in records} == {"one", "two"}


def test_a_full_run_through_the_stub_leaks_no_key_into_logs_output_or_transcript(tmp_path, capsys, caplog):
    transcript = tmp_path / "live-like.jsonl"

    def script(index, body, headers):
        if index == 1:
            return 500, {}, {"error": f"upstream failure for Bearer {FAKE_KEY}"}
        if index == 2:
            # A model that echoes the key inside its reply: the transcript must hold it redacted.
            echo = json.dumps({"major_action": None, "utterances": [{"text": f"my key is {FAKE_KEY}"}]})
            return 200, {}, completion(echo)
        return 200, {}, completion(REST_REPLY)

    caplog.set_level(logging.INFO, logger="bigville.providers")
    with StubServer(script) as stub:
        settings = from_environment({"OPENCODE_GO_API_KEY": FAKE_KEY, "OPENCODE_GO_BASE_URL": stub.base_url,
                                     "BIGVILLE_LLM_TRANSCRIPT": str(transcript), "BIGVILLE_LLM_RUN_ID": "leak55",
                                     "BIGVILLE_LLM_MIN_INTERVAL": "0", "BIGVILLE_LLM_MAX_RETRIES": "1"})
        provider = build_provider(settings, sleep=lambda seconds: None)
        game = build_llm_town(build_transport(settings, provider), llm_residents=2)
        for _ in range(3):
            game.step()
    assert len(stub.requests) >= 3
    captured = capsys.readouterr()
    text = transcript.read_text(encoding="utf-8")
    logs = "\n".join(record.getMessage() for record in caplog.records)
    for surface in (text, logs, captured.out, captured.err):
        assert FAKE_KEY not in surface
    assert "[redacted key]" in text
    assert '"run_id": "leak55"' in text
    assert "x-opencode-session" not in text       # request headers are not written to the transcript
