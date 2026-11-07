"""Build isolated trees for Phase 065 from `git archive HEAD`, the current commit.

    python3 docs/phases/phase065/build_clean_tree.py --out /tmp/t065                 # HEAD + 064 + 065
    python3 docs/phases/phase065/build_clean_tree.py --out /tmp/t064 --stage 064     # HEAD + 064 only
    python3 docs/phases/phase065/build_clean_tree.py --out /tmp/head065 --stage head  # HEAD, untouched

The working tree is shared, so its other edits are not used. Each new file is copied from the working tree, and each
shared-file change is an anchored (old, new) text pair applied to the HEAD text. Every anchor must occur exactly once,
or the build stops. Stage 064 is Phase 064's own work (reading and numeracy, uncommitted when this was written); its
hunks are the ones in docs/phases/phase064/build_clean_tree.py, anchored on HEAD 9599c7e here. Stage 065 is this phase.

Phase 064's files and hunks must match the working tree's when this was written. If Phase 064 changes, update HUNKS_064
and NEW_064 here.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ----------------------------------------------------------------- new files (copied from the working tree)
NEW_064 = [
    "domains/reading.py",
    "domains/numeracy.py",
    "domains/reading_check.py",
    "packs/bigville/world/literacy.json",
    "packs/test_hamlet/world/literacy.json",
    "tests/test_phase064_reading.py",
]
NEW_065 = [
    "domains/impairment.py",
    "domains/impairment_check.py",
    "packs/bigville/world/impairment.json",
    "packs/test_hamlet/world/impairment.json",
    "tests/test_phase065_impairment.py",
]

# ----------------------------------------------------------------- Phase 064 hunks, anchored on HEAD 9599c7e
PACK_062_END = '    {\n      "name": "PERCEIVER_TIERS",\n      "file": "world/perception.json"\n    }\n  ]'
PACK_064_ENTRIES = ("READING", "LITERACY_TIERS", "NUMERACY_TIERS", "NUMERACY_UNITS", "NUMERAL_WORDS",
                    "WRITTEN_KINDS", "WRITTEN_MARKS", "RECOGNISED_SEED")
PACK_064_END = (PACK_062_END[:-len("\n  ]")] + ",\n"
                + ",\n".join(f'    {{\n      "name": "{name}",\n      "file": "world/literacy.json"\n    }}'
                             for name in PACK_064_ENTRIES)
                + "\n  ]")
WHITELIST_OLD = '        "seen",\n        "things"\n      ],\n      "thing": [\n        "handle",\n        "what"\n      ],\n'
WHITELIST_NEW = ('        "seen",\n        "things",\n        "writing"\n      ],\n      "thing": [\n        "handle",\n'
                 '        "what"\n      ],\n      "writing": [\n        "percept"\n      ],\n')
AGENT_VIEW_CHECK_OLD = ('"heard", "seen", "thing", "map", "label", "can", "last", "reaction", "option", "referee")')
AGENT_VIEW_CHECK_NEW = ('"heard", "seen", "thing", "map", "label", "can", "last", "reaction", "option", "referee", '
                        '"writing")')
ENTITIES_062_LINE = "    check_perception(_WORLD_PACK.path, errors, warnings, info)\n"
ENTITIES_064_NEW = (ENTITIES_062_LINE
                    + "    from domains.reading_check import check_reading  # Phase 064: the reading and numeracy tables\n"
                    + "    check_reading(_WORLD_PACK.path, errors, warnings, info)\n")
AGENT_064 = [
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
HUNKS_064 = [
    ("packs/bigville/pack.json", PACK_062_END, PACK_064_END),
    ("packs/test_hamlet/pack.json", PACK_062_END, PACK_064_END),
    ("packs/bigville/world/agent_view.json", WHITELIST_OLD, WHITELIST_NEW),
    ("packs/test_hamlet/world/agent_view.json", WHITELIST_OLD, WHITELIST_NEW),
    ("domains/agent_view_check.py", AGENT_VIEW_CHECK_OLD, AGENT_VIEW_CHECK_NEW),
    ("domains/bigville_entities.py", ENTITIES_062_LINE, ENTITIES_064_NEW),
] + [("domains/agent_view.py", old, new) for old, new in AGENT_064]

# ----------------------------------------------------------------- Phase 065 hunks, anchored on HEAD + 064
PACK_064_LAST = '    {\n      "name": "RECOGNISED_SEED",\n      "file": "world/literacy.json"\n    }\n  ]'
PACK_065_END = (PACK_064_LAST[:-len("\n  ]")] + ",\n"
                + ",\n".join(f'    {{\n      "name": "{name}",\n      "file": "world/impairment.json"\n    }}'
                             for name in ("IMPAIRMENT", "DISTORTION", "IMPAIRMENT_NEIGHBOURS"))
                + "\n  ]")
ENTITIES_064_LINE = "    check_reading(_WORLD_PACK.path, errors, warnings, info)\n"
ENTITIES_065_NEW = (ENTITIES_064_LINE
                    + "    from domains.impairment_check import check_impairment  # Phase 065: the impairment sources, rows and neighbours\n"
                    + "    check_impairment(_WORLD_PACK.path, errors, warnings, info)\n")
PEOPLE_OLD = (
    '            seen = perceiver.percept("person", perceiver.person_subject(game, other, pack), distance, rec, pack)\n'
    '            log.append(perceiver.referee_row(other, "person", distance, seen))\n'
    '            recognised = other in known and seen["tier"] >= 1\n'
    '            entry = {"distance": _phrase("distance", distance, "self", pack)}\n'
    '            if seen["tier"] >= 1:\n'
    '                entry["looks"] = _looks(game, other, pack)\n'
    '            if recognised:\n'
    '                entry["name"] = other\n'
    '                entry["job"] = role\n'
    '            else:\n'
    '                entry["description"] = seen["words"]\n'
    '            if recognised and ties.get(other):\n')
PEOPLE_NEW = (
    '            subject = perceiver.person_subject(game, other, pack)\n'
    '            seen = perceiver.percept("person", subject, distance, rec, pack)\n'
    '            # Phase 065: an impaired resident may be given a wrong percept; the truth stays in the referee row.\n'
    '            seen = impairment.distort(game, actor, "person", other, subject, seen, rec, pack,\n'
    '                                      others=[name for _d, name in nearby if name != other], known=known)\n'
    '            log.append({**perceiver.referee_row(other, "person", distance, seen), **impairment.referee_extra(seen)})\n'
    '            identity = seen.get("as", other)\n'
    '            recognised = identity in known and seen["tier"] >= 1\n'
    '            entry = {"distance": _phrase("distance", distance, "self", pack)}\n'
    '            if seen["tier"] >= 1:\n'
    '                entry["looks"] = _looks(game, other, pack)\n'
    '            if recognised:\n'
    '                entry["name"] = identity\n'
    '                entry["job"] = seen.get("as_job", role)\n'
    '            else:\n'
    '                entry["description"] = seen["words"]\n'
    '            if recognised and ties.get(other) and "as" not in seen:\n')
THING_OLD = (
    '        seen = perceiver.percept("thing", perceiver.thing_subject(what), distance, rec, pack)\n'
    '        log.append(perceiver.referee_row(handle, "thing", distance, seen))\n')
THING_NEW = (
    '        subject = perceiver.thing_subject(what)\n'
    '        seen = perceiver.percept("thing", subject, distance, rec, pack)\n'
    '        # Phase 065: an impaired resident may be given a wrong percept; the truth stays in the referee row.\n'
    '        seen = impairment.distort(game, actor, "thing", handle, subject, seen, rec, pack,\n'
    '                                  others=[(h, w) for h, w, _d in rows if h and h != handle])\n'
    '        log.append({**perceiver.referee_row(handle, "thing", distance, seen), **impairment.referee_extra(seen)})\n')
AGENT_065 = [
    ("from domains import map_memory, perceiver, reading\n",
     "from domains import impairment, map_memory, perceiver, reading\n"),
    (PEOPLE_OLD, PEOPLE_NEW),
    ("    things = _things(world, actor, pack, rec, log)\n",
     "    things = _things(world, actor, pack, rec, log, game)\n"),
    ("def _things(world, actor, pack, rec=None, log=None):",
     "def _things(world, actor, pack, rec=None, log=None, game=None):"),
    (THING_OLD, THING_NEW),
    ("    around = _around(game, actor, pack, known, rec, log)\n",
     "    around = _around(game, actor, pack, known, rec, log)\n"
     "    # Phase 065: remember the subjects shown wrongly this turn (the ledger of actions on a wrong percept).\n"
     "    impairment.note_view(game, actor, rec, log, pack)\n"),
    ('                                             "subjects": log}\n',
     '                                             "subjects": log, **impairment.referee_block(game, log, pack)}\n'),
]
HUNKS_065 = [
    ("packs/bigville/pack.json", PACK_064_LAST, PACK_065_END),
    ("packs/test_hamlet/pack.json", PACK_064_LAST, PACK_065_END),
    ("domains/bigville_entities.py", ENTITIES_064_LINE, ENTITIES_065_NEW),
    ("bigville/game.py",
     "            ok = bool(self.world.enact_plan(actor, plan))\n",
     "            ok = bool(self.world.enact_plan(actor, plan))\n"
     "            # Phase 065: counts a major action taken on a percept the impaired resident was shown wrongly (off by default).\n"
     "            from domains import impairment\n"
     "            impairment.note_action(self, actor, proposal.params, ok, self.world.data_pack)\n"),
    ("bigville/reporting.py",
     '    report["llm"] = llm_report(game.backends)\n',
     '    report["llm"] = llm_report(game.backends)\n'
     "    from domains import impairment   # Phase 065: the wrong-percept ledger (empty unless IMPAIRMENT.enabled)\n"
     "    report.update(impairment.report_block(game, game.world.data_pack))\n"),
] + [("domains/agent_view.py", old, new) for old, new in AGENT_065]


def _patch(text, old, new, rel):
    found = text.count(old)
    if found != 1:
        raise SystemExit(f"{rel}: anchor found {found} times, expected 1:\n{old[:200]!r}")
    return text.replace(old, new)


def _head_file(rel):
    return subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--stage", choices=("head", "064", "065"), default="065")
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; remove it first")
    os.makedirs(out)
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", out], input=archive, check=True)
    if args.stage == "head":
        print(f"built {out}: HEAD, untouched")
        return 0

    new_files = NEW_064 + (NEW_065 if args.stage == "065" else [])
    hunks = HUNKS_064 + (HUNKS_065 if args.stage == "065" else [])
    for rel in new_files:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            raise SystemExit(f"new file missing in the working tree: {rel}")
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)

    texts = {}
    for rel, old, new in hunks:
        if rel not in texts:
            texts[rel] = _head_file(rel)
        texts[rel] = _patch(texts[rel], old, new, rel)
    for rel, text in texts.items():
        _write(os.path.join(out, rel), text)
    print(f"built {out}: HEAD plus stage {args.stage} ({len(new_files)} new files, {len(texts)} patched files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
