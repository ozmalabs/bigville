"""Build an isolated tree for Phase 062: `git archive HEAD` plus this phase's files and anchored hunks only.

    python3 docs/phases/phase062/build_clean_tree.py --out /tmp/t062

The working tree is shared with other sessions, so measuring it would mix their edits into this phase's result. The
new files are copied whole. agent_view.py had no other session's edits, so it is copied whole too. Shared files
(pack manifests, bigville_entities.py, and the three backend classes) get only the hunks below, applied to the HEAD
text. Each hunk is asserted to match exactly once, so a changed anchor stops the build.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

NEW_FILES = [
    "domains/perceiver.py",
    "domains/perception_check.py",
    "packs/bigville/world/perception.json",
    "packs/test_hamlet/world/perception.json",
    "tests/test_phase062_perceiver.py",
    "domains/agent_view.py",
]

PACK_OLD = '      "file": "world/speech_acts.json"\n    }\n  ]'
PACK_NEW = ('      "file": "world/speech_acts.json"\n    },\n'
            '    {\n      "name": "PERCEPTION",\n      "file": "world/perception.json"\n    },\n'
            '    {\n      "name": "PERCEIVER_TIERS",\n      "file": "world/perception.json"\n    }\n  ]')

HUNKS = {
    "packs/bigville/pack.json": [(PACK_OLD, PACK_NEW)],
    "packs/test_hamlet/pack.json": [(PACK_OLD, PACK_NEW)],
    "domains/bigville_entities.py": [(
        "    check_speech_acts(_WORLD_PACK.path, errors, warnings, info)\n",
        "    check_speech_acts(_WORLD_PACK.path, errors, warnings, info)\n"
        "    from domains.perception_check import check_perception  # Phase 062: the perceiver's tiers, gates and switch\n"
        "    check_perception(_WORLD_PACK.path, errors, warnings, info)\n")],
    "bigville/backends/cheap.py": [(
        "    requires_conversational_interface = True\n",
        "    requires_conversational_interface = True\n"
        "    # Phase 062: the simple backend models its own senses, impairment, skills, and literacy (its raw context is the\n"
        "    # truth it decides on), so the agent view, which it never reads, does not degrade them for it.\n"
        '    faculties = {"senses": "represented", "skill": "represented", "impairment": "represented",\n'
        '                 "literacy": "represented", "numeracy": "represented"}\n')],
    "bigville/backends/llm.py": [(
        "    wants_agent_view = True\n",
        "    wants_agent_view = True\n"
        "    # Phase 062: the agent view is degraded by this resident's faculties (domains/perceiver.py); the LLM is not a\n"
        "    # model of them.\n"
        '    faculties = {"senses": "enforced", "skill": "enforced", "impairment": "enforced",\n'
        '                 "literacy": "enforced", "numeracy": "enforced"}\n')],
    "bigville/backends/human.py": [(
        "    fogged = True\n",
        "    fogged = True\n"
        "    # Phase 062: a human player reads the agent view, so the view degrades for each faculty (domains/perceiver.py).\n"
        '    faculties = {"senses": "enforced", "skill": "enforced", "impairment": "enforced",\n'
        '                 "literacy": "enforced", "numeracy": "enforced"}\n')],
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; remove it first")
    os.makedirs(out)
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", out], input=archive, check=True)
    for rel in NEW_FILES:
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dest)
    for rel, pairs in HUNKS.items():
        path = os.path.join(out, rel)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for old, new in pairs:
            found = text.count(old)
            if found != 1:
                raise SystemExit(f"{rel}: anchor found {found} times, expected 1")
            text = text.replace(old, new)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"built {out} from HEAD with {len(NEW_FILES)} new or whole files and {len(HUNKS)} patched files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
