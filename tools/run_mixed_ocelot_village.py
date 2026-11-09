#!/usr/bin/env python3
"""Run the fixed-budget real-Ocelot mixed village and print its JSON trace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bigville.mixed_ocelot_scenario import (
    MAX_TURNS, SEED, run_mixed_ocelot_village,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--turns", type=int, default=MAX_TURNS,
                        help=f"world turns, 1 through {MAX_TURNS}")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-rejection-probe", action="store_true")
    args = parser.parse_args(argv)
    trace = run_mixed_ocelot_village(
        seed=args.seed, turns=args.turns,
        rejection_probe=not args.no_rejection_probe)
    rendered = json.dumps(trace, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
