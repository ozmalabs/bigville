"""Build /tmp/p053_mine = git archive HEAD + this phase's files and hunks (no other session's edits)."""
import os
import shutil
import subprocess

ROOT = "/home/matt/ozmadev/bigville"
DEST = "/tmp/p053_mine"

shutil.rmtree(DEST, ignore_errors=True)
os.makedirs(DEST)
archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
subprocess.run(["tar", "-x", "-C", DEST], input=archive, check=True)

# Files this phase owns outright (clean in the shared tree at session start).
WHOLE = [
    "domains/map_memory.py", "domains/fog_check.py", "domains/agent_view.py", "domains/agent_view_check.py",
    "bigville/backends/llm.py", "bigville/backends/human.py", "bigville/backends/prompts.py",
    "packs/bigville/world/fog.json", "packs/test_hamlet/world/fog.json",
    "packs/bigville/world/agent_view.json", "packs/test_hamlet/world/agent_view.json",
    "tests/test_phase053_fog.py", "tests/test_phase052_agent_view.py",
]
for rel in WHOLE:
    target = os.path.join(DEST, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, rel), target)

# Shared files: apply this phase's hunks to the HEAD text, each anchor must occur exactly once.
MANIFEST_HUNK = (
    '    {\n      "name": "NARRATION",\n      "file": "world/narration.json"\n    }\n  ]',
    '    {\n      "name": "NARRATION",\n      "file": "world/narration.json"\n    },\n'
    '    {\n      "name": "FOG_RULES",\n      "file": "world/fog.json"\n    },\n'
    '    {\n      "name": "FOG_PUBLIC_LANDMARKS",\n      "file": "world/fog.json"\n    },\n'
    '    {\n      "name": "FOG_PLACE_WORDS",\n      "file": "world/fog.json"\n    },\n'
    '    {\n      "name": "FOG_WORDS",\n      "file": "world/fog.json"\n    }\n  ]',
)
HUNKS = {
    "tests/test_bigville_game_api.py": [
        ("    assert refused.dump_held_state(\"Ben\")[\"memories\"] == []",
         "    # Phase 053: Ben is a fogged (human) resident, so the held state carries its map record. No lesson is learned.\n"
         "    held = [m for m in refused.dump_held_state(\"Ben\")[\"memories\"] if m[\"kind\"] != \"map_memory\"]\n"
         "    assert held == []"),
    ],
    "bigville/game.py": [
        ('        """The end of a turn: world turn bookkeeping, event expiry, periods and continuations."""\n'
         '        self.world.resolve_actor_turn()\n',
         '        """The end of a turn: world turn bookkeeping, event expiry, periods and continuations."""\n'
         '        self.world.resolve_actor_turn()\n'
         '        # Phase 053: each fogged resident (the LLM and human backends) learns the ground in sight this turn.\n'
         '        from domains.map_memory import learn_all\n'
         '        learn_all(self)\n'),
        ('            plan = {"action": proposal.action, **proposal.params}\n'
         '            ok = bool(self.world.enact_plan(actor, plan))\n',
         '            plan = {"action": proposal.action, **proposal.params}\n'
         '            # Phase 053: a fogged resident\'s move is checked against its own map, and `toward` becomes a destination.\n'
         '            from domains.map_memory import route_plan\n'
         '            plan = route_plan(self, actor, plan)\n'
         '            ok = bool(self.world.enact_plan(actor, plan))\n'),
    ],
    "domains/bigville_entities.py": [
        ('    check_narration(_WORLD_PACK.path, errors, warnings, info)\n',
         '    check_narration(_WORLD_PACK.path, errors, warnings, info)\n'
         '    from domains.fog_check import check_fog  # Phase 053: the fog levels, their words and the map\'s whitelist\n'
         '    check_fog(_WORLD_PACK.path, errors, warnings, info)\n'),
    ],
    "packs/bigville/pack.json": [MANIFEST_HUNK],
    "packs/test_hamlet/pack.json": [MANIFEST_HUNK],
}
for rel, pairs in HUNKS.items():
    path = os.path.join(DEST, rel)
    text = open(path, encoding="utf-8").read()
    for old, new in pairs:
        count = text.count(old)
        assert count == 1, (rel, count, old[:60])
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8").write(text)
print("built", DEST)
