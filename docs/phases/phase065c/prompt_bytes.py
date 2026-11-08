"""Phase 065c check: the LLM prompt packet for a small lazy-mode game, one md5 per turn.

    python3 docs/phases/phase065c/prompt_bytes.py --root /tmp/h065c --perception off --turns 12
    python3 docs/phases/phase065c/prompt_bytes.py --root /tmp/t065c --perception off --turns 12

The same switch setting must give the same lines in HEAD and in the 065c tree (the switch-off prompt is unchanged).
A provider stub answers every call with a rest, so the game steps without a network. The script only reads
the packet; it writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SCENARIO = {
    "id": "p065c_prompt_bytes",
    "name": "Phase 065c prompt bytes",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "llm", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "apple", "name": "apple", "kind": "apple", "location": "table"},
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": True},
    ],
}
REST = json.dumps({"major_action": {"action": "rest", "params": {}}, "utterances": [],
                   "memory_updates": [], "continuation": None})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--perception", choices=("on", "off"), required=True)
    parser.add_argument("--turns", type=int, default=12)
    args = parser.parse_args(argv)
    sys.path.insert(0, os.path.abspath(args.root))
    os.chdir(os.path.abspath(args.root))
    from bigville.api import create_game
    from bigville.backends import LLMBackend
    from domains.pack import load_pack
    from tests.llm_stub import FakeProvider

    pack = load_pack("bigville")
    pack["PERCEPTION"]["enabled"] = args.perception == "on"
    provider = FakeProvider(REST)
    factory = lambda world, character: LLMBackend(character, provider, autopilot=False)
    game = create_game(scenario=SCENARIO, seed=305165, player=None, default_backend="simple",
                       backend_factories={"llm": factory}, autonomous=True, llm_log=False,
                       affordance_mode="lazy")
    backend = game.backends["Ada"]
    for turn in range(args.turns):
        context = game._context("Ada")
        record = backend.prompt_builder.build(context)
        text = record.as_json()
        print(f"turn {turn} {hashlib.md5(text.encode()).hexdigest()} {len(text)}")
        game.step()
    return 0


if __name__ == "__main__":
    sys.exit(main())
