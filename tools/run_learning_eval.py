"""run_learning_eval.py -- write a run's learning curves to JSON and a Markdown report (Phase 056).

    python3 tools/run_learning_eval.py [--scenario town100] [--seed 305000] [--turns 60]
        [--control-turns 30] [--llm-residents 3] [--out-dir DIR] [--no-logs]

The run uses scripted fake providers only: the learner and the non-learner control, the simple backend, and the
two scripted LLM arms (with the autopilot and the pack's call cap). The Ocelot arm is reported as skipped when its
adapter cannot be imported. No network is used and no key is read.

Output in DIR (default docs/phases/phase056/evaluation):
  learning_eval.json   the full record (curves per turn for each resident, summaries, guard results, digests)
  LEARNING_EVAL.md     the report
  logs/                the Phase 066 logs of the LLM arms (gzip), the guard reads these
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bigville.learning_eval import (CONTROL_TURNS, DEFAULT_LLM_RESIDENTS, DEFAULT_SCENARIO, DEFAULT_SEED,  # noqa: E402
                                    DEFAULT_TURNS, render_markdown, run_evaluation, write_json)

DEFAULT_OUT = os.path.join("docs", "phases", "phase056", "evaluation")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    parser.add_argument("--control-turns", type=int, default=CONTROL_TURNS)
    parser.add_argument("--llm-residents", type=int, default=DEFAULT_LLM_RESIDENTS)
    parser.add_argument("--out-dir", default=os.path.join(ROOT, DEFAULT_OUT))
    parser.add_argument("--no-logs", action="store_true", help="do not write the LLM logs (the guard is then not run)")
    parser.add_argument("--render-only", action="store_true",
                        help="rebuild LEARNING_EVAL.md from an existing learning_eval.json (no run)")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out_dir)
    if args.render_only:
        with open(os.path.join(out_dir, "learning_eval.json"), encoding="utf-8") as stream:
            record = json.load(stream)
        with open(os.path.join(out_dir, "LEARNING_EVAL.md"), "w", encoding="utf-8") as stream:
            stream.write(render_markdown(record))
        print(json.dumps({"digest": record["digest"], "void_arms": record["void_arms"]}, indent=1))
        return 1 if record["void_arms"] else 0
    log_dir = None if args.no_logs else os.path.join(out_dir, "logs")
    os.makedirs(out_dir, exist_ok=True)
    record = run_evaluation(scenario=args.scenario, seed=args.seed, turns=args.turns,
                            control_turns=args.control_turns, llm_residents=args.llm_residents,
                            log_dir=log_dir)
    write_json(record, os.path.join(out_dir, "learning_eval.json"))
    with open(os.path.join(out_dir, "LEARNING_EVAL.md"), "w", encoding="utf-8") as stream:
        stream.write(render_markdown(record))
    summary = {"digest": record["digest"], "void_arms": record["void_arms"],
               "comparison": record["controls"]["comparison"]}
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 1 if record["void_arms"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
