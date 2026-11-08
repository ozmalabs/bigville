"""Phase 061 live run: the speech parser against a real model (OpenCode Go, glm-5.3-flash), on the 200 labelled utterances.

    python3 docs/phases/phase061/live_run.py --out docs/phases/phase061/live --limit 0 [--workers 6] [--max-spend 2.0]

The key is read by bigville.providers.opencode_go.from_environment from the environment or .env. It is never printed or
written. The run writes the placements, the cache, the scores and the parser summary under --out (the model's replies
are in the cache; the thinking is in the provider's own result and is not kept here). --limit N runs the first N items
only (0 is all of them). Items the grammar places make no call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_phase061_speech_parser as T                      # noqa: E402  (the grading helpers and the fixtures)
from bigville.backends.speech_parser import SpeechParser     # noqa: E402
from bigville.providers.opencode_go import build_provider, from_environment  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-spend", type=float, default=2.0)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--intro-extra", default="", help="text appended to the pack's intro, for a prompt experiment")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    settings = from_environment({}, dotenv_path=os.path.join(ROOT, ".env"))
    settings = type(settings)(**{**settings.__dict__, "model": "glm-5.3-flash", "max_tokens": args.max_tokens,
                                 "max_retries": 1, "run_id": "phase061-live"})
    provider = build_provider(settings)
    print("model", settings.model, "base", settings.base_url, "key set:", bool(settings.api_key))
    items = T.ITEMS[:args.limit] if args.limit else T.ITEMS
    cache_name = "cache.jsonl"
    cache = os.path.join(args.out, cache_name)
    parser = SpeechParser(provider, cache_path=cache, max_spend=args.max_spend, timeout_s=args.timeout,
                          max_calls=len(items) + 50)
    if args.intro_extra:
        from domains.pack import load_pack
        intro = load_pack("bigville")["SPEECH_PARSER"]["prefix"]["intro"]
        assert intro in parser.prefix
        parser.prefix = parser.prefix.replace(intro, intro + " " + args.intro_extra)

    def place(pair):
        turn, item = pair
        return parser.parse(item["text"], item["speaker"], T._listener(item["listener"]),
                            T._context(names=item["names"], listener_name=item["listener"], turn=turn))

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        placed = list(pool.map(place, enumerate(items)))
    first = time.perf_counter() - started
    calls_first = parser.calls
    second = [place(pair) for pair in enumerate(items)]       # the cache pass: no call should be made
    result = {"model": settings.model, "items": len(items), "elapsed_s": round(first, 1),
              "grade": T._grade(items, placed), "grammar_only": T._grade(items, T.grammar_arm(items)),
              "calls_first_pass": calls_first, "calls_second_pass": parser.calls - calls_first,
              "second_pass_same": [a == b for a, b in zip(placed, second)].count(True) == len(items),
              "summary": parser.summary()}
    rows = [{"id": it["id"], "text": it["text"], "label": it["label"], "got": got} for it, got in zip(items, placed)]
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, sort_keys=True, default=str)
    with open(os.path.join(args.out, "placements.json"), "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=1, default=str)
    print(json.dumps({k: result[k] for k in ("items", "elapsed_s", "grade", "grammar_only", "calls_first_pass",
                                              "calls_second_pass", "second_pass_same")}, sort_keys=True))
    print("summary", json.dumps(result["summary"], sort_keys=True, default=str)[:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
