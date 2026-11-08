"""tui_check.py -- self-test checks for the terminal modes' tables (Phase 067).

    check_tui(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It checks the two tables of
world/tui_modes.json:

* TUI_ART (the map mode's art): every glyph the agent view draws (MAP_GLYPHS) has a two-character tile; each tile,
  person glyph and thing glyph is one character, not a digit, and its colour is in the table's colours list.
* TUI_PROSE (the text mode's sentences): every key the code fills exists, is a non-empty text, names exactly the
  fields TEXT_FIELDS lists for it (a brace the code does not fill would print), and carries no digit outside a field.
  The help lines are a non-empty list of texts with no digit.
"""
from __future__ import annotations

import re
import string

from domains.pack import PackError, load_pack

ART_KEYS = ("tiles", "people", "things", "colours")
PERSON_KEYS = ("known", "stranger")
PROSE_KEYS = {
    "banner": {"name"},
    "exits": {"ways"},
    "exits_none": set(),
    "things": {"things"},
    "things_none": set(),
    "nobody": set(),
    "ground": {"ground"},
    "options": set(),
    "options_none": set(),
    "writing": {"text"},
    "unplaced": set(),
    "packet": set(),
    "legend_known": set(),
    "legend_stranger": set(),
    "legend_thing": set(),
}
DIGIT = re.compile(r"\d")


def _fields(template):
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(template) if name}


def _one_char(value):
    return isinstance(value, str) and len(value) == 1 and not value.isdigit() and not value.isspace()


def _check_art(pack, errors):
    art = pack["TUI_ART"]
    missing = [key for key in ART_KEYS if key not in art]
    if missing:
        errors.append(f"TUI_ART: missing {', '.join(missing)}")
        return
    colours = art["colours"]
    if not isinstance(colours, list) or not colours or not all(isinstance(c, str) and c for c in colours):
        errors.append("TUI_ART: colours must be a non-empty list of colour names")
        colours = []
    glyphs = {row["glyph"] for row in pack["MAP_GLYPHS"].values() if isinstance(row, dict)}
    for glyph in sorted(glyphs):
        if glyph not in art["tiles"]:
            errors.append(f"TUI_ART: the map glyph {glyph!r} (MAP_GLYPHS) has no tile")
    for glyph, row in art["tiles"].items():
        if glyph not in glyphs:
            errors.append(f"TUI_ART: tile {glyph!r} is not a map glyph of MAP_GLYPHS")
        tile = row.get("tile") if isinstance(row, dict) else None
        if not isinstance(tile, str) or len(tile) != 2 or DIGIT.search(tile):
            errors.append(f"TUI_ART: tile for {glyph!r} must be two characters with no digit")
        if isinstance(row, dict) and row.get("colour") not in colours:
            errors.append(f"TUI_ART: tile for {glyph!r} has a colour that is not in colours")
    for name in PERSON_KEYS:
        row = art["people"].get(name) if isinstance(art["people"], dict) else None
        if not isinstance(row, dict) or not _one_char(row.get("glyph")):
            errors.append(f"TUI_ART: people.{name} needs a one-character glyph")
        elif row.get("colour") not in colours:
            errors.append(f"TUI_ART: people.{name} has a colour that is not in colours")
    thing = art["things"]
    if not isinstance(thing, dict) or not _one_char(thing.get("glyph")):
        errors.append("TUI_ART: things needs a one-character glyph")
    elif thing.get("colour") not in colours:
        errors.append("TUI_ART: things has a colour that is not in colours")


def _check_prose(pack, errors):
    prose = pack["TUI_PROSE"]
    for key, fields in PROSE_KEYS.items():
        text = prose.get(key)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"TUI_PROSE: {key} is missing or empty")
            continue
        if _fields(text) != fields:
            errors.append(f"TUI_PROSE: {key} names fields {sorted(_fields(text))}, expected {sorted(fields)}")
        if DIGIT.search(re.sub(r"\{\w+\}", "", text)):
            errors.append(f"TUI_PROSE: {key} carries a digit outside a field")
    help_lines = prose.get("help")
    if not isinstance(help_lines, list) or not help_lines:
        errors.append("TUI_PROSE: help must be a non-empty list of lines")
    else:
        for index, line in enumerate(help_lines):
            if not isinstance(line, str) or not line.strip() or DIGIT.search(line):
                errors.append(f"TUI_PROSE: help line {index + 1} must be text with no digit")


def check_tui(pack_name, errors, warnings, info):
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"TUI: cannot load the pack: {exc}")
        return
    for table in ("TUI_ART", "TUI_PROSE"):
        if table not in pack.names():
            errors.append(f"TUI: the pack has no {table} table (world/tui_modes.json)")
            return
    _check_art(pack, errors)
    _check_prose(pack, errors)
    if not errors:
        info.append(f"TERMINAL MODES: {len(pack['TUI_ART']['tiles'])} map tiles, {len(PROSE_KEYS)} text sentences "
                    f"and {len(pack['TUI_PROSE']['help'])} help lines; all terminal mode checks pass")
