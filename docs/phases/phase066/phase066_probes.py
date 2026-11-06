"""Phase 066 probes, run by hand and cited in the report. Not a test.

    python3 docs/phases/phase066/phase066_probes.py sample-log
    python3 docs/phases/phase066/phase066_probes.py checkpoint

sample-log: two consults of one LLM resident against the loopback stub, with a fake key and a thinking text that
contains the key. Writes docs/phases/phase066/sample_llm_log.jsonl and prints the first record and the chain check.
checkpoint: asks the other stream's game checkpoint to save a town with one LLM resident, and a town with none.
Only the public save function is called; the checkpoint code is read, not changed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

FAKE_KEY = "sk-fake-probe-0123456789abcdefghijklmnopqrstuvwxyz"
HERE = os.path.dirname(os.path.abspath(__file__))


def thinking_body(content: str) -> dict:
    from llm_stub import completion
    body = completion(content, cost=0.002, reasoning=214)
    thinking = ("The bread is nearly gone and the mill is closed, so I rest and think about the flour. " * 6
                + f"My key is {FAKE_KEY}; I must not write it down.")
    message = body["choices"][0]["message"]
    message["reasoning_content"] = thinking
    body["choices"][0]["finish_reason"] = "stop"
    return body


def sample_log() -> None:
    from bigville.llm_log import LLMLog, read_log, verify_log
    from bigville.llm_scenario import build_llm_town
    from bigville.providers import OpenAICompatibleProvider
    from llm_stub import StubServer, REST_REPLY
    import json as _json

    out = os.path.join(HERE, "sample_llm_log.jsonl")
    if os.path.exists(out):
        os.remove(out)
    reply = _json.dumps({"major_action": {"action": "rest", "params": {}},
                         "utterances": [{"text": f"key {FAKE_KEY}"}]})
    with StubServer(lambda i, b, h: (200, {"x-request-id": f"probe-{i}"}, thinking_body(reply))) as stub:
        provider = OpenAICompatibleProvider(base_url=stub.base_url, api_key=FAKE_KEY, model="glm-5.3-flash",
                                            run_id="probe66", min_interval=0.0, sleep=lambda s: None)
        game = build_llm_town(provider, llm_residents=1)
        name = game.llm_residents[0]
        backend = game.backends[name]
        backend.log = LLMLog(out, run_id="probe66", redact=provider.redact)
        for _ in range(2):
            backend.gate.last_consult_turn = None
            backend.decide(game._context(name))
    text = open(out, encoding="utf-8").read()
    assert FAKE_KEY not in text
    records = read_log(out)
    check = verify_log(out)
    first = records[0]
    print("records:", len(records), "chain ok:", check.ok, "problems:", check.problems)
    print("key present in file:", FAKE_KEY in text, "| redaction marker present:", "[redacted key]" in text)
    print("thinking chars in record:", len(first["response"]["reasoning_content"]))
    print("first record keys:", sorted(first))
    print("first record response keys:", sorted(first["response"]))


def checkpoint() -> None:
    from bigville.game_persistence import save_game_checkpoint
    from bigville.llm_scenario import build_llm_town
    from bigville.api import create_game
    from llm_stub import FakeProvider, varied_reply

    with tempfile.TemporaryDirectory() as tmp:
        plain = create_game(scenario="norms_property_sharing", seed=7, default_backend="cheap", autonomous=True)
        try:
            save_game_checkpoint(plain, os.path.join(tmp, "plain"))
            print("cheap-only town: saved")
        except Exception as exc:  # report what the checkpoint refuses
            print("cheap-only town:", type(exc).__name__, exc)
        game = build_llm_town(FakeProvider(varied_reply), llm_residents=1)
        try:
            save_game_checkpoint(game, os.path.join(tmp, "llm"))
            print("one LLM resident: saved")
        except Exception as exc:
            print("one LLM resident:", type(exc).__name__, exc)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "sample-log":
        sample_log()
    elif command == "checkpoint":
        checkpoint()
    else:
        raise SystemExit(__doc__)
