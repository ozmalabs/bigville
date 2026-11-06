"""narration_check.py -- self-test checks for a pack's NARRATION table (Phase 057).

    check_narration(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). The terminal interface
(bigville/tui/narrate.py) fills each template with the fields listed in EXPECTED_FIELDS, so the checks are:
- every key the interface reads exists, and no key is unexpected;
- each template names exactly the fields its key expects (a template that names a missing field would
  print a brace; a field the code does not fill would print as an error);
- no template carries a digit outside a {field}: a digit on screen is a raw number, and the only digits the
  interface prints are a menu number (the {number} field) and a handle the world published;
- every label and tab name is a non-empty phrase, and the help lines are non-empty lists of phrases.
"""
from __future__ import annotations

import re
import string

from domains.pack import PackError, load_pack

EXPECTED_FIELDS = {
    "title": set(),
    "status": {"time", "season", "weather"},
    "now_time": {"time"},
    "now_season": {"season"},
    "now_weather": {"weather"},
    "energy": {"energy"},
    "hunger": {"hunger"},
    "health": {"health"},
    "mood": {"mood"},
    "person": {"who", "distance", "looks"},
    "person_plain": {"who", "distance"},
    "heard": {"from", "text"},
    "seen": {"who", "did"},
    "last": {"action", "outcome"},
    "reason": {"reason"},
    "reaction_intro": {"from", "what"},
    "reaction_amount": {"from", "what", "amount"},
    "reaction_pick": set(),
    "answered": {"answer"},
    "waiting": {"who"},
    "unparsed": set(),
    "ask": {"choices"},
    "ask_choice": {"number", "handle", "what"},
    "menu_item": {"number", "what"},
    "map_hidden": set(),
    "map_vague": {"labels"},
    "legend_item": {"glyph", "word"},
    "empty_log": set(),
    "pass": set(),
    "still_waiting": set(),
    "said_to": {"who", "text"},
    "said": {"text"},
    "more_people": set(),
    "prompt": set(),
}
NAMED_PREFIXES = ("tab_", "label_")
TAB_KEYS = ("tab_body", "tab_skills", "tab_knows", "tab_carrying", "tab_people")
LIST_KEYS = ("help",)
_DIGIT = re.compile(r"\d")


def _fields(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def _literal(template):
    """The template with each {field} removed, so only its fixed text is left."""
    return re.sub(r"\{[^{}]*\}", "", template)


def check_narration(pack_name, errors, warnings, info):
    """Run every narration check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"NARRATION: cannot load pack '{pack_name}': {exc}")
        return
    if "NARRATION" not in pack:
        errors.append(f"NARRATION: pack '{pack_name}' has no NARRATION table")
        return
    table = pack["NARRATION"]
    before = len(errors)
    for key in EXPECTED_FIELDS:
        if key not in table:
            errors.append(f"NARRATION: '{key}' is missing")
            continue
        text = table[key]
        if not isinstance(text, str):
            errors.append(f"NARRATION: '{key}' must be a template (text)")
            continue
        if _fields(text) != EXPECTED_FIELDS[key]:
            errors.append(f"NARRATION: '{key}' fills {sorted(_fields(text))}, "
                          f"expected {sorted(EXPECTED_FIELDS[key])}")
        if _DIGIT.search(_literal(text)):
            errors.append(f"NARRATION: '{key}' has a digit outside its fields; a digit is a raw number")
    for key in TAB_KEYS:
        if key not in table or not str(table[key]).strip():
            errors.append(f"NARRATION: tab name '{key}' is missing or empty")
    for key in LIST_KEYS:
        lines = table.get(key)
        if not isinstance(lines, list) or not lines:
            errors.append(f"NARRATION: '{key}' must be a non-empty list of lines")
            continue
        for line in lines:
            if not isinstance(line, str) or _DIGIT.search(line):
                errors.append(f"NARRATION: a '{key}' line is not text or carries a digit")
    for key, text in table.items():
        if key.startswith("_"):
            continue
        if key.startswith(NAMED_PREFIXES) and (not isinstance(text, str) or not text.strip()):
            errors.append(f"NARRATION: '{key}' must be a non-empty phrase")
        if key not in EXPECTED_FIELDS and key not in LIST_KEYS and not key.startswith(NAMED_PREFIXES):
            errors.append(f"NARRATION: '{key}' is not a key the interface reads")
    if len(errors) == before:
        info.append(f"NARRATION ({pack.name}): {len(EXPECTED_FIELDS)} templates, {len(TAB_KEYS)} tab names and "
                    f"the help lines; all narration checks pass")
