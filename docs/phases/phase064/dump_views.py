"""Dump the agent views of the 100-resident town to a JSON file, for comparing trees (Phase 064).

    cd <tree> && PYTHONHASHSEED=0 python3 <this file> --out views.json --perception on|off --reading on|off

Builds the town (scenario town100, seed 305000), sets the pack switches as asked (a switch the tree does not have is
skipped), and writes the agent and referee views of the first 30 living residents and the player. Run it in each tree
and compare the files byte for byte.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bigville.api import create_game   # noqa: E402
from domains.pack import load_pack      # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--perception", choices=("on", "off"), default="off")
    parser.add_argument("--reading", choices=("on", "off"), default="off")
    args = parser.parse_args()
    pack = load_pack("bigville")
    names = pack.names()
    if "PERCEPTION" in names:
        pack["PERCEPTION"]["enabled"] = args.perception == "on"
    if "READING" in names:
        pack["READING"]["enabled"] = args.reading == "on"
    game = create_game(scenario="town100", seed=305000, player="Verity Peaseblossom")
    world = game.world
    residents = sorted(n for n in game.characters if n != game.player and world.is_alive(n))[:30]
    out = {}
    for name in residents + [game.player]:
        out[name] = {mode: game.agent_view(name, mode=mode) for mode in ("agent", "referee")}
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(out, handle, sort_keys=True, indent=1, ensure_ascii=False, default=str)
    print(f"wrote {len(out)} views to {args.out}")


if __name__ == "__main__":
    main()
