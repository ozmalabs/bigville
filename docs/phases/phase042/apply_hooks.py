"""apply_hooks.py -- Phase 042's shared-file hooks, by content anchor (idempotent).

    python3 docs/phases/phase042/apply_hooks.py <tree_root>

Each HUNK is (file, old, new): `old` must occur exactly once in the file (else the script stops), and is replaced by
`new`. A hunk whose `new` text is already present is skipped, so the script can run on a tree that already has it.
JSON edits are made by key (round-trip checked: the files were byte-identical after a json round trip at HEAD).
New files (domains/daynight*.py, worlds/daynight.py, bigville/backends/lamplighter.py, and the packs'
world/daynight.json) are not written here; copy them from the working tree.
"""
from __future__ import annotations

import copy
import json
import os
import sys

HUNKS = [
    ("domains/world_affordances.py",
     'MAJOR_ACTIONS = _PACK["MAJOR_ACTIONS"]\n',
     'MAJOR_ACTIONS = _PACK["MAJOR_ACTIONS"]\n'
     'MAJOR_ACTIONS = {**MAJOR_ACTIONS, **_PACK["DAYNIGHT_MAJOR_ACTIONS"]}   # Phase 042: light and douse\n'
     'DAYNIGHT = _PACK["DAYNIGHT"]               # Phase 042: day, night and lamps\n'
     'DAYNIGHT_LAMPS = _PACK["DAYNIGHT_LAMPS"]\n'),
    ("domains/world_affordances.py",
     '    return flows, notes, work\n',
     '    if DAYNIGHT["enabled"]:   # Phase 042: lamp oil, stock against one period\'s burn\n'
     '        from domains.daynight import lamp_oil_per_period\n'
     '        flows["lamp oil (stock vs one period)"] = (float(DAYNIGHT["starting_oil"]), lamp_oil_per_period(\n'
     '            len(DAYNIGHT_LAMPS), DAYNIGHT["lamp_burn_per_tick"], TIME, DAYNIGHT))\n'
     '    return flows, notes, work\n'),
    ("domains/bigville_entities.py",
     'from domains.world_affordances import _PACK as _WORLD_PACK   # noqa: E402  which pack this view reads\n',
     'from domains.world_affordances import _PACK as _WORLD_PACK   # noqa: E402  which pack this view reads\n'
     'from domains import daynight_check as _daynight_check   # noqa: E402  Phase 042\n'),
    ("domains/bigville_entities.py",
     '    known_places = set(BUILDINGS)\n',
     '    known_places = set(BUILDINGS)\n'
     '    _daynight_check.check(errors, warnings, info, daynight=DAYNIGHT, lamps=DAYNIGHT_LAMPS, weather=WEATHER,\n'
     '                          jobs=JOBS, labour_tasks=LABOUR_TASKS, items=ITEMS, major_actions=MAJOR_ACTIONS,\n'
     '                          founding_map=FOUNDING_MAP, time=TIME)   # Phase 042\n'),
    ("worlds/bigville_world.py",
     'from domains.world_affordances import round_bp  # noqa: E402\n',
     'from domains.world_affordances import round_bp  # noqa: E402\n'
     'from worlds import daynight as _dn  # noqa: E402  Phase 042: day, night and lamps\n'),
    ("worlds/bigville_world.py",
     '        self._install_square_fixtures()\n',
     '        self._install_square_fixtures()\n'
     '        _dn.install(self)   # Phase 042: lamps and the lamplighter, when the pack switch is on\n'),
    ("worlds/bigville_world.py",
     '            self._advance_calendar()\n',
     '            self._advance_calendar()\n'
     '            _dn.tick(self)   # Phase 042: the sky, lamp oil and candles, once day and night is on\n'),
    ("worlds/bigville_world.py",
     '        if actor not in self._actors:\n'
     '            return self._refuse("unknown_target")\n'
     '        if action == "move":\n',
     '        if actor not in self._actors:\n'
     '            return self._refuse("unknown_target")\n'
     '        if action in _dn.ACTIONS:   # Phase 042: light and douse, at a lamp or with a held candle\n'
     '            return self._claimed_attempt(actor, action, lambda: _dn.act(self, actor, action, kwargs, args))\n'
     '        if action == "move":\n'),
    ("worlds/bigville_world.py",
     '            seen = dist <= sight_range and not self._line_blocked(speaker_pos, pos, sight_codes)\n',
     '            seen = dist <= _dn.sight_range(self, name, sight_range) and not self._line_blocked(\n'
     '                speaker_pos, pos, sight_codes)   # Phase 042: shorter sight in the dark\n'),
    ("worlds/bigville_world.py",
     '            if dist <= sight_range and not self._line_blocked(here, pos, codes):\n',
     '            if dist <= _dn.sight_range(self, other, sight_range) and not self._line_blocked(here, pos, codes):\n'),
    ("worlds/bigville_world.py",
     '        interval = terrain_interval * band["interval"] / self.stagger_speed(actor)\n',
     '        interval = terrain_interval * band["interval"] / self.stagger_speed(actor) * _dn.travel_factor(self, actor)\n'),
    ("worlds/bigville_world.py",
     '        fit_now = min(fits) if fits else 1.0\n',
     '        fit_now = (min(fits) if fits else 1.0) * _dn.work_visibility(self, actor)   # Phase 042: dark work\n'),
    ("worlds/bigville_world.py",
     '        return {"lateness": round(lateness, 4), "safe": bool(safe)}\n',
     '        lateness = _dn.lateness(self, lateness)   # Phase 042: from the real sunset when day and night is on\n'
     '        return {"lateness": round(lateness, 4), "safe": bool(safe)}\n'),
    ("worlds/bigville_world.py",
     '        return [dict(option) for option in self._actor_options(actor)]\n',
     '        return [dict(option) for option in self._actor_options(actor)] + _dn.lamp_options(self, actor)   # Phase 042\n'),
    ("bigville/backends/cheap.py",
     'from .protocol import ActorContext, ActorContinuation, ActorResponse, ProposedAction\n',
     'from .protocol import ActorContext, ActorContinuation, ActorResponse, ProposedAction\n'
     'from .lamplighter import lamplighter_choice  # Phase 042: the lamplighter\'s round\n'),
    ("bigville/backends/cheap.py",
     '    def decide(self, context: ActorContext) -> ActorResponse:\n'
     '        self._update_goals(context)\n',
     '    def decide(self, context: ActorContext) -> ActorResponse:\n'
     '        self._update_goals(context)\n'
     '        lamp = lamplighter_choice(context)   # Phase 042: a lamplighter\'s round (offered to a lamplighter only)\n'
     '        if lamp is not None:\n'
     '            action, params, continuation = lamp\n'
     '            self.last_choice = {"action": action, "goal": "lamplighter", "time_band": self.time_band,\n'
     '                                "reason": "lamplighter"}\n'
     '            return ActorResponse(major_action=ProposedAction(action, params, "cheap_psi_can"),\n'
     '                                 continuation=continuation)\n'),
    ("domains/agent_view.py",
     'def _now(world, pack):\n    clock = world.calendar()\n',
     'def _daylight(world, actor, pack):\n'
     '    """The light the resident sees, in words (Phase 042). None when day and night is off."""\n'
     '    from worlds import daynight as _dn\n'
     '    key = _dn.view_light(world, actor)\n'
     '    return _phrase("daylight", key, "self", pack) if key else None\n\n\n'
     'def _now(world, pack, actor=None):\n    clock = world.calendar()\n'),
    ("domains/agent_view.py",
     '        "weather": _phrase("weather", clock["weather"], "self", pack) if clock.get("weather") else None,\n',
     '        "weather": _phrase("weather", clock["weather"], "self", pack) if clock.get("weather") else None,\n'
     '        "light": _daylight(world, actor, pack),\n'),
    ("domains/agent_view.py",
     '        "now": _now(world, pack),\n',
     '        "now": _now(world, pack, actor),\n'),
]

# Manifest entries (both packs): appended after the last FOG table.
MANIFEST_OLD = '    {"name": "FOG_WORDS", "file": "world/fog.json"}\n  ]'
MANIFEST_NEW = ('    {"name": "FOG_WORDS", "file": "world/fog.json"},\n'
                '    {"name": "DAYNIGHT", "file": "world/daynight.json"},\n'
                '    {"name": "DAYNIGHT_LAMPS", "file": "world/daynight.json"},\n'
                '    {"name": "DAYNIGHT_MAJOR_ACTIONS", "file": "world/daynight.json"}\n  ]')

PACKS = ("bigville", "test_hamlet")

WEATHER_CLOUD = {"clear": 0.1, "dry": 0.1, "hot": 0.1, "frost": 0.1, "mild": 0.3, "wind": 0.3,
                 "cool": 0.4, "cold": 0.5, "rain": 0.7, "wet": 0.75, "storm": 0.9}
LAMPLIGHTER_JOB = {"trades": ["labourer"], "tools": [], "fixed": 0.0, "per_100": 0.0}
LAMPLIGHTING_TASK = {"seasonal": False, "skills": ["labourer"], "inputs": ["oil"], "outputs": []}
DAYLIGHT_WORDS = {"unknown": "hard to tell", "day": "in daylight", "dim": "dim, in the moonlight",
                  "dark": "it is dark", "lamplight": "by lamplight"}


def _manifest(path):
    """Append the three DAYNIGHT entries after the last FOG entry, in the file's own layout (one line or three)."""
    text = open(path, encoding="utf-8").read()
    if '"name": "DAYNIGHT"' in text:
        return False
    one_line = '    {"name": "FOG_WORDS", "file": "world/fog.json"}\n  ]'
    three_line = '    {\n      "name": "FOG_WORDS",\n      "file": "world/fog.json"\n    }\n  ]'
    if text.count(one_line) == 1:
        new = ('    {"name": "FOG_WORDS", "file": "world/fog.json"},\n'
               '    {"name": "DAYNIGHT", "file": "world/daynight.json"},\n'
               '    {"name": "DAYNIGHT_LAMPS", "file": "world/daynight.json"},\n'
               '    {"name": "DAYNIGHT_MAJOR_ACTIONS", "file": "world/daynight.json"}\n  ]')
        old = one_line
    elif text.count(three_line) == 1:
        def entry(name):
            return f'    {{\n      "name": "{name}",\n      "file": "world/daynight.json"\n    }}'
        new = ('    {\n      "name": "FOG_WORDS",\n      "file": "world/fog.json"\n    },\n'
               + ",\n".join(entry(n) for n in ("DAYNIGHT", "DAYNIGHT_LAMPS", "DAYNIGHT_MAJOR_ACTIONS"))
               + "\n  ]")
        old = three_line
    else:
        raise SystemExit(f"{path}: no unique FOG_WORDS tail to anchor the DAYNIGHT entries on")
    open(path, "w", encoding="utf-8").write(text.replace(old, new))
    return True


def _json_edit(path, edit):
    raw = open(path, encoding="utf-8").read()
    obj = json.loads(raw)
    if json.dumps(obj, indent=2, ensure_ascii=False) + "\n" != raw:
        raise SystemExit(f"{path}: not canonical JSON; refusing to rewrite it")
    if edit(obj):
        open(path, "w", encoding="utf-8").write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
        return True
    return False


def _text_hunk(path, old, new):
    text = open(path, encoding="utf-8").read()
    if new in text:
        return False
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: anchor occurs {count} times, expected 1:\n{old}")
    open(path, "w", encoding="utf-8").write(text.replace(old, new))
    return True


def apply(root):
    changed = []
    os.chdir(root)
    for path, old, new in HUNKS:
        if _text_hunk(path, old, new):
            changed.append(f"hunk {path}")
    for pack in PACKS:
        def weather(obj):
            table = obj["tables"]["WEATHER"]
            done = False
            for key, spec in table.items():
                if spec.get("cloud") != WEATHER_CLOUD[key]:
                    spec["cloud"] = WEATHER_CLOUD[key]
                    done = True
            return done
        if _json_edit(f"packs/{pack}/world/weather.json", weather):
            changed.append(f"weather cloud {pack}")
        def agent(obj):
            wl = obj["tables"]["AGENT_VIEW_WHITELIST"]["now"]
            q = obj["tables"]["AGENT_VIEW_QUANTITIES"]
            done = False
            if "light" not in wl:
                wl.append("light")
                done = True
            if q.get("light") != "daylight":
                q["light"] = "daylight"
                done = True
            return done
        if pack == "bigville" and _json_edit("packs/bigville/world/agent_view.json", agent):
            changed.append("agent_view.json whitelist and quantity")
        manifest = f"packs/{pack}/pack.json"
        if _manifest(manifest):
            changed.append(f"manifest {pack}")
        if os.path.exists(f"packs/{pack}/world/daynight.json") is False:
            raise SystemExit(f"copy packs/{pack}/world/daynight.json from the working tree first")
    if _json_edit("packs/bigville/world/lexicon.json", lambda o: _lex(o)):
        changed.append("lexicon daylight quantity")
    if _json_edit("packs/bigville/frames/jobs.json", lambda o: _add(o["tables"]["JOBS"], "lamplighter",
                                                                     LAMPLIGHTER_JOB)):
        changed.append("jobs lamplighter")
    if _json_edit("packs/bigville/population/founding_cast.json",
                  lambda o: _add(o["tables"]["FOUNDING_JOBS"], "lamplighter", FOUNDING_JOB_ROW)):
        changed.append("founding cast lamplighter row")
    if _json_edit("packs/bigville/frames/knowledge.json", _knowledge_rows):
        changed.append("knowledge rows (public spread, routine places)")
    if _json_edit("packs/bigville/world/persona.json",
                  lambda o: _add(o["tables"]["ROUTINE"], "lamplighter", ROUTINE_ROW)):
        changed.append("routine row")
    if _json_edit("packs/bigville/frames/labour_tasks.json",
                  lambda o: _add(o["tables"]["LABOUR_TASKS"], "lamplighting", LAMPLIGHTING_TASK)):
        changed.append("labour lamplighting")
    return changed


FOUNDING_JOB_ROW = {"group": "low", "role_identity_mean": 0.3, "role_identity_sd": 0.07, "workplace": "market"}
ROUTINE_ROW = {"blocks": [
    {"block": "morning", "start": 6.0, "place": "market", "task": "putting out the square's lamps at dawn"},
    {"block": "work", "start": 9.0, "place": "market", "task": "trimming the lamps and filling their oil"},
    {"block": "midday", "start": 12.0, "place": "home", "task": "eating the midday meal"},
    {"block": "afternoon", "start": 13.0, "place": "market", "task": "mending the lamp glass"},
    {"block": "evening", "start": 17.0, "place": "market", "task": "lighting the square's lamps at dusk"},
    {"block": "sleep", "start": 21.0, "place": "home", "task": "in bed for the night"}]}


def _knowledge_rows(obj):
    public = obj["tables"]["JOB_PUBLIC"]
    routine = obj["tables"]["JOB_ROUTINE"]
    done = _add(public, "lamplighter", 0.4)
    return _add(routine, "lamplighter", ["market", "townhall"]) or done


def _add(table, key, value):
    if key in table:
        return False
    table[key] = copy.deepcopy(value)
    return True


def _lex(obj):
    q = obj["tables"]["LEXICON_QUANTITIES"]
    if "daylight" in q:
        return False
    q["daylight"] = {"_doc": LEXICON_DOC, "kind": "status", "published": True,
                     "self": dict(DAYLIGHT_WORDS), "other": dict(DAYLIGHT_WORDS)}
    return True


LEXICON_DOC = ("DAYLIGHT, the light a resident perceives where they stand (Phase 042): 'day' (sunlight through the "
               "cloud), 'dim' (night, with moonlight enough to see by), 'dark' (night, with nothing to see by: the "
               "resident sees_dark), 'lamplight' (a lit street lamp within DAYNIGHT.lamp_reach, a lit candle in hand, "
               "or indoors at night). Words only: no number is published, so a fogged resident reads 'it is dark' or "
               "'by lamplight'. Shown only when DAYNIGHT is on. Plain to everyone: both perspectives.")


if __name__ == "__main__":
    print("\n".join(apply(os.path.abspath(sys.argv[1]))) or "nothing to change")
