"""Phase 055 measurements: concurrency timings, and a sample transcript from the loopback stub.

    PYTHONHASHSEED=0 python3 docs/phases/phase055/measure_phase055.py

Writes docs/phases/phase055/concurrency.json and docs/phases/phase055/sample_transcript.jsonl, and prints the
3 LLM plus 97 simple town run (the mixed-town test's configuration) with its call counts. Uses a fake key
and the loopback stub only; no network. The sample is written with the key redacted by the provider.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bigville.concurrency import decide_pooled  # noqa: E402
from bigville.llm_scenario import RunDigest, build_llm_town  # noqa: E402
from llm_stub import FakeProvider, StubServer, completion, varied_reply  # noqa: E402

DELAY = 0.3
RESIDENTS = 8


class SlowBackend:
    concurrency = 4

    def decide(self, context):
        time.sleep(DELAY)
        return context


def pool_only():
    out = {}
    for workers in (1, 2, 4, 8):
        backends = {f"r{i}": (type("B", (SlowBackend,), {"concurrency": workers})(), i) for i in range(RESIDENTS)}
        started = time.perf_counter()
        decide_pooled(backends)
        out[f"pool_workers_{workers}_seconds"] = round(time.perf_counter() - started, 3)
    out["sequential_floor_seconds"] = round(DELAY * RESIDENTS, 3)
    return out


def whole_town(turns=2):
    out = {}
    for label, concurrent_flag, workers in (("sequential", False, 4), ("concurrent_4", True, 4),
                                            ("concurrent_8", True, 8)):
        provider = FakeProvider(varied_reply, delay=DELAY)
        game = build_llm_town(provider, llm_residents=RESIDENTS, concurrency=workers)
        for name in game.llm_residents:
            game.backends[name].concurrent = concurrent_flag
        digest = RunDigest()
        started = time.perf_counter()
        for _ in range(turns):
            assert game.step()["status"] == "advanced"
            digest.add(game)
        out[label] = {"seconds": round(time.perf_counter() - started, 3), "calls": len(provider.calls),
                      "digest": digest.hexdigest()}
    out["digests_equal"] = len({out[k]["digest"] for k in ("sequential", "concurrent_4", "concurrent_8")}) == 1
    return out


def mixed_town(turns=100, llm=3):
    """The test's configuration (3 LLM and 97 simple residents, 100 turns) with the call count and the report."""
    from bigville.reporting import llm_report
    provider = FakeProvider(varied_reply)
    game = build_llm_town(provider, llm_residents=llm)
    started = time.perf_counter()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
    report = llm_report(game.backends)
    consults = {}
    for call in provider.calls:
        consults[call["meta"]["actor"]] = consults.get(call["meta"]["actor"], 0) + 1
    return {"residents": len(game.characters), "llm_residents": list(game.llm_residents), "turns": turns,
            "seconds": round(time.perf_counter() - started, 2), "calls": len(provider.calls),
            "calls_per_llm_resident": consults, "llm_total": {k: report["total"][k] for k in (
                "calls", "repairs_used", "successes", "failures", "autopilot_turns", "carry_ons", "waits",
                "deviations", "decisions", "turns")},
            "fallbacks_by_cause": report["total"]["fallbacks_by_cause"],
            "consults_by_reason": report["total"]["consults_by_reason"]}


def sample_transcript():
    from bigville.providers import build_provider, build_transport, from_environment
    path = HERE / "sample_transcript.jsonl"
    if path.exists():
        path.unlink()
    key = "sk-fake-phase055-0123456789abcdef"

    def script(index, body, headers):
        return 200, {}, completion(json.dumps({"major_action": {"action": "rest", "params": {}},
                                               "utterances": []}), cost=0.0021)

    with StubServer(script) as stub:
        settings = from_environment({"OPENCODE_GO_API_KEY": key, "OPENCODE_GO_BASE_URL": stub.base_url,
                                     "BIGVILLE_LLM_TRANSCRIPT": str(path), "BIGVILLE_LLM_RUN_ID": "sample55",
                                     "BIGVILLE_LLM_MIN_INTERVAL": "0"})
        provider = build_provider(settings, sleep=lambda s: None)
        game = build_llm_town(build_transport(settings, provider), llm_residents=1)
        game.step()
    line = path.read_text(encoding="utf-8").splitlines()[0]
    record = json.loads(line)
    record["prompt"] = f"<{len(json.dumps(record['prompt']))} characters, omitted here>"
    return {"line": json.dumps(record, sort_keys=True), "key_in_file": key in path.read_text(encoding="utf-8"),
            "key_in_stub_request_headers": key in json.dumps(stub.requests[0]["headers"]) if stub.requests else None}


if __name__ == "__main__":
    result = {"delay_seconds": DELAY, "residents": RESIDENTS, "pool_only": pool_only(),
              "whole_town_two_turns": whole_town(), "env_pythonhashseed": os.environ.get("PYTHONHASHSEED")}
    (HERE / "concurrency.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sample = sample_transcript()
    mixed = mixed_town()
    print(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(sample, indent=2, sort_keys=True))
    print(json.dumps(mixed, indent=2, sort_keys=True))
