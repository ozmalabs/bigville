"""Build isolated trees for Phase 064 from `git archive HEAD`.

    python3 docs/phases/phase064/build_clean_tree.py --out /tmp/t064                 # HEAD + 062 + 064
    python3 docs/phases/phase064/build_clean_tree.py --out /tmp/t062 --without-064   # HEAD + 062 only

The working tree is shared, so its other edits are not used. The Phase 062 files and backend hunks come from
docs/phases/phase062/build_clean_tree.py. That builder's two manifest and self-test anchors predate Phase 061 (it
expects the manifest to end at speech_acts.json, and the self-test hook after check_speech_acts), so this builder
overrides those two hunks with the anchors at HEAD 6b6822d. agent_view.py is copied from the working tree: with 064
it is copied whole, without 064 its 064 hunks are reversed. Each hunk is asserted to match exactly once.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

NEW_064 = [
    "domains/reading.py",
    "domains/numeracy.py",
    "domains/reading_check.py",
    "packs/bigville/world/literacy.json",
    "packs/test_hamlet/world/literacy.json",
    "tests/test_phase064_reading.py",
]

# Phase 062 manifest and self-test anchors at HEAD 6b6822d (after SPEECH_PARSER).
SP_PACK_OLD = '      "file": "world/speech_parser.json"\n    }\n  ]'
SP_PACK_NEW = ('      "file": "world/speech_parser.json"\n    },\n'
               '    {\n      "name": "PERCEPTION",\n      "file": "world/perception.json"\n    },\n'
               '    {\n      "name": "PERCEIVER_TIERS",\n      "file": "world/perception.json"\n    }\n  ]')
SP_ENT_OLD = "    check_speech_parser(_WORLD_PACK.path, errors, warnings, info)\n"
SP_ENT_NEW = (SP_ENT_OLD
              + "    from domains.perception_check import check_perception  # Phase 062: the perceiver's tiers, gates and switch\n"
              + "    check_perception(_WORLD_PACK.path, errors, warnings, info)\n")

# Phase 064 manifest anchor: the 062 layout of the last entry (the working tree's form, one per block).
PACK_062_END = '    {\n      "name": "PERCEIVER_TIERS",\n      "file": "world/perception.json"\n    }\n  ]'
PACK_064_END = (PACK_062_END[:-len("\n  ]")] + ",\n"
                + ",\n".join(
                    f'    {{\n      "name": "{name}",\n      "file": "world/literacy.json"\n    }}'
                    for name in ("READING", "LITERACY_TIERS", "NUMERACY_TIERS", "NUMERACY_UNITS", "NUMERAL_WORDS",
                                 "WRITTEN_KINDS", "WRITTEN_MARKS", "RECOGNISED_SEED"))
                + "\n  ]")

WHITELIST_OLD = '        "seen",\n        "things"\n      ],\n      "thing": [\n        "handle",\n        "what"\n      ],\n'
WHITELIST_NEW = ('        "seen",\n        "things",\n        "writing"\n      ],\n      "thing": [\n        "handle",\n'
                 '        "what"\n      ],\n      "writing": [\n        "percept"\n      ],\n')

HUNKS_064 = {
    "packs/bigville/pack.json": [(PACK_062_END, PACK_064_END)],
    "packs/test_hamlet/pack.json": [(PACK_062_END, PACK_064_END)],
    "packs/bigville/world/agent_view.json": [(WHITELIST_OLD, WHITELIST_NEW)],
    "packs/test_hamlet/world/agent_view.json": [(WHITELIST_OLD, WHITELIST_NEW)],
    "domains/agent_view_check.py": [(
        '"heard", "seen", "thing", "map", "label", "can", "last", "reaction", "option", "referee")',
        '"heard", "seen", "thing", "map", "label", "can", "last", "reaction", "option", "referee", "writing")')],
    "domains/bigville_entities.py": [(
        "    check_perception(_WORLD_PACK.path, errors, warnings, info)\n",
        "    check_perception(_WORLD_PACK.path, errors, warnings, info)\n"
        "    from domains.reading_check import check_reading  # Phase 064: the reading and numeracy tables\n"
        "    check_reading(_WORLD_PACK.path, errors, warnings, info)\n")],
}

# agent_view.py, the 064 hunks (old text, new text).
AGENT_HUNKS = [
    ("from domains import map_memory, perceiver\n",
     "from domains import map_memory, perceiver, reading\n"),
    ("    things = _things(world, actor, pack, rec, log)\n"
     "    return _check_keys(\"around\", {\"people\": people, \"heard\": heard, \"seen\": seen, \"things\": things}, pack)\n",
     "    things = _things(world, actor, pack, rec, log)\n"
     "    around = {\"people\": people, \"heard\": heard, \"seen\": seen, \"things\": things}\n"
     "    # Phase 064: written marks in sight, read at the resident's literacy (off unless READING.enabled).\n"
     "    writing = reading.writing_rows(game, actor, rec, pack, log) if rec is not None else None\n"
     "    if writing:\n"
     "        around[\"writing\"] = writing\n"
     "    return _check_keys(\"around\", around, pack)\n"),
]


def _load_062():
    path = os.path.join(ROOT, "docs", "phases", "phase062", "build_clean_tree.py")
    spec = importlib.util.spec_from_file_location("build062", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch(text, pairs, rel):
    for old, new in pairs:
        found = text.count(old)
        if found != 1:
            raise SystemExit(f"{rel}: anchor found {found} times, expected 1")
        text = text.replace(old, new)
    return text


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--without-064", action="store_true", help="build HEAD plus Phase 062 only")
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; remove it first")
    os.makedirs(out)
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", out], input=archive, check=True)

    b62 = _load_062()
    for rel in b62.NEW_FILES:
        if rel == "domains/agent_view.py":
            continue
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dest)
    hunks = {rel: list(pairs) for rel, pairs in b62.HUNKS.items()}
    hunks["packs/bigville/pack.json"] = [(SP_PACK_OLD, SP_PACK_NEW)]
    hunks["packs/test_hamlet/pack.json"] = [(SP_PACK_OLD, SP_PACK_NEW)]
    hunks["domains/bigville_entities.py"] = [(SP_ENT_OLD, SP_ENT_NEW)]
    for rel, pairs in hunks.items():
        path = os.path.join(out, rel)
        _write(path, _patch(_read(path), pairs, rel))

    working_agent = _read(os.path.join(ROOT, "domains", "agent_view.py"))
    if args.without_064:
        _write(os.path.join(out, "domains", "agent_view.py"),
               _patch(working_agent, [(new, old) for old, new in AGENT_HUNKS], "domains/agent_view.py"))
        print(f"built {out}: HEAD plus Phase 062")
        return 0

    for rel in NEW_064:
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dest)
    _write(os.path.join(out, "domains", "agent_view.py"), working_agent)
    for rel, pairs in HUNKS_064.items():
        path = os.path.join(out, rel)
        _write(path, _patch(_read(path), pairs, rel))
    print(f"built {out}: HEAD plus Phase 062 and Phase 064")
    return 0


if __name__ == "__main__":
    sys.exit(main())
