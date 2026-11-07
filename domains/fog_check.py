"""fog_check.py -- self-test checks for a pack's fog tables (Phase 053).

    check_fog(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It reads the pack with
domains/pack.load_pack and checks:
- the four fog tables exist (FOG_RULES, FOG_PUBLIC_LANDMARKS, FOG_PLACE_WORDS, FOG_WORDS);
- the rules are whole numbers in range, and they agree with the sight range (HEARING.sight_range): the level-2
  radius each turn is the sight range, and a landmark is seen from at least that far;
- label_letters are distinct and enough for max_labels;
- every public landmark is a place of the founding layout (workplace, building site or the square), with no
  name listed twice; the hamlet has no founding layout, so its list is empty;
- every FOG_PLACE_WORDS key is a place of the founding layout or one of the standard ground names
  (home, field, pasture, and the deposit kinds), and each word is a phrase with no digit;
- the eight headings, the distance and age bands (in increasing order, phrases with no digit), and the
  sentence templates, each with exactly the fields the map code fills;
- the agent view's whitelist carries the map keys (level, caption, rows, legend, labels, paths) and the label
  keys (glyph, word) that domains/map_memory.py fills.
"""
from __future__ import annotations

import re
import string

from domains.pack import PackError, load_pack

REQUIRED = ("FOG_RULES", "FOG_PUBLIC_LANDMARKS", "FOG_PLACE_WORDS", "FOG_WORDS")
RULE_KEYS = ("exact_radius", "landmark_sight", "stale_ticks", "explore_steps", "near_landmark_cells",
             "max_labels", "label_letters")
HEADINGS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
STANDARD_NAMES = ("home", "field", "pasture", "stone", "lumber", "fish", "market", "church", "wellhouse")
TEMPLATES = {"label": {"word", "where"}, "label_rough": {"word", "where"}, "label_near": {"place"},
             "remembered": {"age"}, "path_between": {"a", "b"}, "spot": set()}
MAP_WHITELIST = ("level", "caption", "rows", "legend", "labels", "paths")
LABEL_WHITELIST = ("glyph", "word")
_DIGIT = re.compile(r"\d")


def _fields(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def _whole(value, low=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= low


def check_fog(pack_name, errors, warnings, info):
    """Run every fog check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"FOG: cannot load pack '{pack_name}': {exc}")
        return
    missing = [name for name in REQUIRED if name not in pack]
    if missing:
        errors.append(f"FOG: pack '{pack_name}' has no {', '.join(missing)} table")
        return
    before = len(errors)
    _check_rules(pack, errors)
    _check_landmarks(pack, errors)
    _check_place_words(pack, errors)
    _check_words(pack, errors)
    _check_whitelist(pack, errors)
    if len(errors) == before:
        landmarks = len(pack["FOG_PUBLIC_LANDMARKS"])
        info.append(f"FOG ({pack.name}): 3 levels; {landmarks} public landmarks, "
                    f"{len(pack['FOG_PLACE_WORDS'])} place words; all fog checks pass")


def _check_rules(pack, errors):
    rules = pack["FOG_RULES"]
    for key in RULE_KEYS:
        if key not in rules:
            errors.append(f"FOG: FOG_RULES has no '{key}'")
    if any(key not in rules for key in RULE_KEYS):
        return
    for key in ("exact_radius", "landmark_sight", "explore_steps", "near_landmark_cells", "max_labels"):
        if not _whole(rules[key], 1 if key != "exact_radius" else 0):
            errors.append(f"FOG: FOG_RULES.{key} must be a whole number of cells, not {rules[key]!r}")
    if not _whole(rules["stale_ticks"], 1):
        errors.append(f"FOG: FOG_RULES.stale_ticks must be a whole number of ticks of at least 1")
    hearing = pack["HEARING"] if "HEARING" in pack else {}
    sight = hearing.get("sight_range") if isinstance(hearing, dict) else None
    if not _whole(sight, 1):
        errors.append("FOG: HEARING.sight_range (the level-2 radius each turn) must be a whole number of at least 1")
        return
    if _whole(rules["exact_radius"]) and rules["exact_radius"] > sight:
        errors.append(f"FOG: FOG_RULES.exact_radius ({rules['exact_radius']}) is larger than the sight range ({sight})")
    if _whole(rules["landmark_sight"], 1) and rules["landmark_sight"] < sight:
        errors.append(f"FOG: FOG_RULES.landmark_sight ({rules['landmark_sight']}) is less than the sight range "
                      f"({sight}); a landmark would be seen from closer than a cell is")
    letters = rules["label_letters"]
    if not isinstance(letters, str) or len(set(letters)) != len(letters) or not letters.isalpha():
        errors.append("FOG: FOG_RULES.label_letters must be distinct letters")
    elif _whole(rules["max_labels"], 1) and len(letters) < rules["max_labels"]:
        errors.append(f"FOG: FOG_RULES.label_letters has {len(letters)} letters for max_labels "
                      f"{rules['max_labels']}")


def _founding_names(pack):
    names = set()
    for table in ("FOUNDING_WORKPLACES", "FOUNDING_BUILDING_SITES", "FOUNDING_PLACE_LABELS"):
        names |= set((pack[table] if table in pack else {}) or {})
    return names


def _check_landmarks(pack, errors):
    names = list(pack["FOG_PUBLIC_LANDMARKS"])
    if len(set(names)) != len(names):
        errors.append("FOG: FOG_PUBLIC_LANDMARKS lists a name twice")
    known = _founding_names(pack)
    for name in names:
        if not isinstance(name, str) or name not in known:
            errors.append(f"FOG: public landmark {name!r} is not a place of the founding layout")


def _check_place_words(pack, errors):
    words = pack["FOG_PLACE_WORDS"]
    known = _founding_names(pack) | set(STANDARD_NAMES)
    if isinstance(words, dict):
        for name, phrase in words.items():
            if name.startswith("_"):
                continue
            if name not in known:
                errors.append(f"FOG: FOG_PLACE_WORDS names {name!r}, which is not a place of the founding layout "
                              f"or a standard ground name")
            if not isinstance(phrase, str) or not phrase.strip() or _DIGIT.search(phrase):
                errors.append(f"FOG: FOG_PLACE_WORDS[{name}] must be a phrase with no digit")


def _check_words(pack, errors):
    words = pack["FOG_WORDS"]
    for key in ("directions", "distances", "ages"):
        if key not in words:
            errors.append(f"FOG: FOG_WORDS has no '{key}'")
    if any(key not in words for key in ("directions", "distances", "ages")):
        return
    codes = [entry.get("code") for entry in words["directions"]]
    if sorted(codes) != sorted(HEADINGS) or any(not isinstance(entry.get("word"), str) or _DIGIT.search(entry["word"])
                                                for entry in words["directions"]):
        errors.append("FOG: FOG_WORDS.directions must be the eight headings, each with a word and no digit")
    previous = -1
    for entry in words["distances"]:
        if not _whole(entry.get("max_cells"), 1) or entry["max_cells"] <= previous or not isinstance(
                entry.get("phrase"), str) or _DIGIT.search(entry["phrase"]) or not isinstance(entry.get("direction"), bool):
            errors.append("FOG: FOG_WORDS.distances must be bands with rising max_cells, a phrase with no digit, "
                          "and a direction flag")
            break
        previous = entry["max_cells"]
    previous = -1
    for entry in words["ages"]:
        if not _whole(entry.get("max_ticks"), 1) or entry["max_ticks"] <= previous or not isinstance(
                entry.get("phrase"), str) or _DIGIT.search(entry["phrase"]):
            errors.append("FOG: FOG_WORDS.ages must be bands with rising max_ticks and a phrase with no digit")
            break
        previous = entry["max_ticks"]
    for key, fields in TEMPLATES.items():
        text = words.get(key)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"FOG: FOG_WORDS has no template '{key}'")
            continue
        if _fields(text) != fields:
            errors.append(f"FOG: FOG_WORDS[{key}] fills {sorted(_fields(text))}, expected {sorted(fields)}")
        if key != "spot" and _DIGIT.search(text):
            errors.append(f"FOG: FOG_WORDS[{key}] has a digit")
    if "spot" in words and _DIGIT.search(str(words["spot"])):
        errors.append("FOG: FOG_WORDS[spot] has a digit")


def _check_whitelist(pack, errors):
    whitelist = pack["AGENT_VIEW_WHITELIST"] if "AGENT_VIEW_WHITELIST" in pack else {}
    if not isinstance(whitelist, dict):
        return
    for section, expected in (("map", MAP_WHITELIST), ("label", LABEL_WHITELIST)):
        keys = set(whitelist.get(section, []))
        if not set(expected) <= keys:
            errors.append(f"FOG: the agent view whitelist's '{section}' section lacks "
                          f"{sorted(set(expected) - keys)}, which the fog map fills")
