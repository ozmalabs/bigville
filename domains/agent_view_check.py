"""agent_view_check.py -- self-test checks for a pack's agent view tables (Phase 052).

    check_agent_view(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency), like the lexicon and persona
checks. It reads the pack directly with domains/pack.load_pack. It checks:
- the agent view tables exist, and AGENT_VIEW_WHITELIST has exactly the sections the builder checks;
- every whitelist entry is a plain name, and no name is listed twice in a section;
- no referee-only name is whitelisted in an agent section (the 'referee' section holds the referee block,
  which is allowed the numbers);
- every view field that carries a number or a status in words names a lexicon table with bands;
- the map glyphs cover every terrain in TERRAIN_MOVEMENT, plus 'unknown' and 'player'; glyphs are single,
  distinct characters, and the words have no digit;
- the fixed phrases (VIEW_WORDS, PRECISION_WORDS, ACTION_WORDS) have no digit, and each template names
  exactly the fields the builder fills;
- the 'knows' cap is a whole number of at least 1, and the sight range the map patch uses is a whole number of
  cells of at least 1 (HEARING.sight_range); REFUSAL_REASONS, which the 'last' section quotes, exists.
"""
from __future__ import annotations

import re
import string

from domains.lexicon import bands
from domains.pack import PackError, load_pack

SECTIONS = ("top", "self", "persona", "body", "carrying", "knows", "places", "now", "around", "person",
            "heard", "seen", "thing", "map", "label", "can", "last", "reaction", "option", "referee")
REQUIRED = ("AGENT_VIEW_WHITELIST", "AGENT_VIEW_REFEREE_ONLY", "AGENT_VIEW_QUANTITIES", "AGENT_VIEW_KNOWS_LIMIT",
            "MAP_GLYPHS", "VIEW_WORDS", "PRECISION_WORDS", "ACTION_WORDS")
VIEW_WORD_KEYS = ("asleep", "collapsed", "ill", "carried_line", "held_line", "kin_line", "unknown_kin",
                  "stranger", "someone", "you", "walk_to", "moved", "done", "not_done", "map_level",
                  "understood", "aware", "react_resist", "react_brace", "react_evade", "react_yield",
                  "reaction_late", "map_full", "map_vague", "map_hidden", "walk_toward")
# Phase 057: the reaction options the world offers (Phase 029) each need words in VIEW_WORDS as react_<option>;
# the list in VIEW_WORD_KEYS above names them.
TEMPLATE_FIELDS = {"carried_line": {"item", "amount"}, "held_line": {"item", "condition"},
                   "kin_line": {"term", "who"}, "stranger": {"job"}, "walk_to": {"place"},
                   "walk_toward": {"place"}}
PLAIN_NAME = re.compile(r"^[a-z][a-z_]*$")
_DIGIT = re.compile(r"\d")


def _fields(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def check_agent_view(pack_name, errors, warnings, info):
    """Run every agent view check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"AGENT VIEW: cannot load pack '{pack_name}': {exc}")
        return
    missing = [name for name in REQUIRED if name not in pack]
    if missing:
        errors.append(f"AGENT VIEW: pack '{pack_name}' has no {', '.join(missing)} table")
        return
    before = len(errors)
    whitelist = pack["AGENT_VIEW_WHITELIST"]
    referee_only = list(pack["AGENT_VIEW_REFEREE_ONLY"])
    _check_whitelist(pack, whitelist, referee_only, errors)
    _check_quantities(pack, pack_name, errors, warnings, info)
    _check_glyphs(pack, errors)
    _check_words(pack, errors)
    limit = pack["AGENT_VIEW_KNOWS_LIMIT"]
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        errors.append(f"AGENT VIEW: AGENT_VIEW_KNOWS_LIMIT must be a whole number of at least 1, not {limit!r}")
    hearing = pack["HEARING"] if "HEARING" in pack else {}
    sight = hearing.get("sight_range") if isinstance(hearing, dict) else None
    if not isinstance(sight, int) or isinstance(sight, bool) or sight < 1:
        errors.append(f"AGENT VIEW: HEARING.sight_range (the map patch radius) must be a whole number of "
                      f"cells of at least 1, not {sight!r}")
    if "REFUSAL_REASONS" not in pack:
        errors.append("AGENT VIEW: pack has no REFUSAL_REASONS table, which the 'last' section quotes")
    if len(errors) == before:
        info.append(f"AGENT VIEW ({pack.name}): {len(whitelist) - 1} sections whitelisted, "
                    f"{len(referee_only)} referee-only names; all agent view checks pass")


def _check_whitelist(pack, whitelist, referee_only, errors):
    if not isinstance(whitelist, dict):
        errors.append("AGENT VIEW: AGENT_VIEW_WHITELIST must be a table of section name to key list")
        return
    names = {name for name in whitelist if not name.startswith("_")}
    if names != set(SECTIONS):
        errors.append(f"AGENT VIEW: AGENT_VIEW_WHITELIST sections are {sorted(names)}, "
                      f"the builder checks {sorted(SECTIONS)}")
    for section, keys in whitelist.items():
        if section.startswith("_"):
            continue
        if not isinstance(keys, list):
            errors.append(f"AGENT VIEW: whitelist '{section}' must be a list of key names")
            continue
        for key in keys:
            if not isinstance(key, str) or not PLAIN_NAME.match(key):
                errors.append(f"AGENT VIEW: whitelist '{section}' has a name that is not a plain key: {key!r}")
        if len(set(keys)) != len(keys):
            errors.append(f"AGENT VIEW: whitelist '{section}' lists a key twice")
        if section != "referee":
            clash = sorted(set(keys) & set(referee_only))
            if clash:
                errors.append(f"AGENT VIEW: whitelist '{section}' carries referee-only names {clash}")
    if len(set(referee_only)) != len(referee_only):
        errors.append("AGENT VIEW: AGENT_VIEW_REFEREE_ONLY lists a name twice")


def _check_quantities(pack, pack_name, errors, warnings, info):
    omitted = []
    for field, quantity in pack["AGENT_VIEW_QUANTITIES"].items():
        if field.startswith("_"):
            continue
        if quantity not in pack["LEXICON_QUANTITIES"]:
            # The pack words no such quantity, so the view leaves the field out (never a raw number).
            omitted.append(field)
            continue
        if not bands(quantity, "self", pack_name) and not bands(quantity, "other", pack_name):
            errors.append(f"AGENT VIEW: lexicon quantity '{quantity}' has no bands to read the field with")
        if not pack["LEXICON_QUANTITIES"][quantity].get("published", True):
            warnings.append(f"AGENT VIEW: field '{field}' reads lexicon quantity '{quantity}', which is not "
                            f"published yet")
    if omitted:
        info.append(f"AGENT VIEW ({pack.name}): the lexicon has no table for {len(omitted)} view fields, so the "
                    f"view omits them in this pack: {', '.join(omitted)}")


def _check_glyphs(pack, errors):
    glyphs = pack["MAP_GLYPHS"]
    needed = set(pack["TERRAIN_MOVEMENT"]) | {"unknown", "player"}
    have = {name for name in glyphs if not name.startswith("_")}
    if needed - have:
        errors.append(f"AGENT VIEW: MAP_GLYPHS has no glyph for {sorted(needed - have)}")
    seen = {}
    for name in sorted(have):
        spec = glyphs[name]
        if not isinstance(spec, dict) or set(spec) != {"glyph", "word"}:
            errors.append(f"AGENT VIEW: MAP_GLYPHS[{name}] must carry exactly glyph and word")
            continue
        if not isinstance(spec["glyph"], str) or len(spec["glyph"]) != 1:
            errors.append(f"AGENT VIEW: MAP_GLYPHS[{name}].glyph must be one character")
        elif spec["glyph"] in seen:
            errors.append(f"AGENT VIEW: glyph {spec['glyph']!r} is used by {seen[spec['glyph']]} and {name}")
        else:
            seen[spec["glyph"]] = name
        if not isinstance(spec["word"], str) or not spec["word"].strip() or _DIGIT.search(spec["word"]):
            errors.append(f"AGENT VIEW: MAP_GLYPHS[{name}].word must be words with no digit")


def _check_words(pack, errors):
    view = pack["VIEW_WORDS"]
    for key in VIEW_WORD_KEYS:
        if key not in view:
            errors.append(f"AGENT VIEW: VIEW_WORDS has no '{key}'")
    for key, text in view.items():
        if key.startswith("_"):
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"AGENT VIEW: VIEW_WORDS[{key}] must be a non-empty phrase")
            continue
        if key in TEMPLATE_FIELDS:
            if _fields(text) != TEMPLATE_FIELDS[key]:
                errors.append(f"AGENT VIEW: VIEW_WORDS[{key}] fills {sorted(_fields(text))}, "
                              f"expected {sorted(TEMPLATE_FIELDS[key])}")
        elif _fields(text):
            errors.append(f"AGENT VIEW: VIEW_WORDS[{key}] has a placeholder but is not a template")
        if _DIGIT.search(text):
            errors.append(f"AGENT VIEW: VIEW_WORDS[{key}] has a digit; a view phrase carries no number")
    for key, text in pack["PRECISION_WORDS"].items():
        if key.startswith("_"):
            continue
        if _DIGIT.search(text):
            errors.append(f"AGENT VIEW: PRECISION_WORDS[{key}] has a digit")
    if not {"exact", "rough"} <= set(pack["PRECISION_WORDS"]):
        errors.append("AGENT VIEW: PRECISION_WORDS needs 'exact' and 'rough'")
    for key, text in pack["ACTION_WORDS"].items():
        if key.startswith("_"):
            continue
        if not isinstance(text, str) or not text.strip() or _DIGIT.search(text):
            errors.append(f"AGENT VIEW: ACTION_WORDS[{key}] must be words with no digit")
