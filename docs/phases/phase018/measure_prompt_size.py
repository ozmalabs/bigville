"""Prompt size for three founders of the 100-resident town (Phase 018 before/after measurement).

Run from the repository root:  python3 docs/phases/phase018/measure_prompt_size.py
Prints, per founder: memories held, the byte length of the full prompt record (as_json, UTF-8),
the system text, and the private part. Byte counts are of the JSON the LLM backend sends.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from bigville.backends import PromptBuilder  # noqa: E402
from bigville.game import BigvilleGame  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402


def main():
    world = BigvilleWorld.from_town100(seed=305000, autonomous_actors=False)
    game = BigvilleGame(world, autonomous=True)
    names = sorted(game.characters)
    total_memories = sum(len(c.memories) for c in game.characters.values())
    print(f"town residents={len(names)} memories_total={total_memories}")
    builder = PromptBuilder()
    for index in (0, 50, 99):
        name = names[index]
        character = game.characters[name]
        record = builder.build(game._context(name))
        full = len(record.as_json().encode("utf-8"))
        system = len(record.system.encode("utf-8"))
        private = len(json.dumps(record.as_dict()["context"]["private"], sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))
        public = len(json.dumps(record.as_dict()["context"]["public"], sort_keys=True,
                                separators=(",", ":")).encode("utf-8"))
        print(f"{name}: memories={len(character.memories)} prompt_bytes={full} "
              f"system_bytes={system} private_bytes={private} public_bytes={public}")


if __name__ == "__main__":
    main()
