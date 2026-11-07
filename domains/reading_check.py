"""reading_check.py -- self-test checks for the reading and numeracy tables (Phase 064).

    check_reading(pack_path, errors, warnings, info, *, kinds=None, marks=None)

Called from bigville_entities.check_consistency with the pack path. `kinds` and `marks` replace WRITTEN_KINDS and
WRITTEN_MARKS, so a test can plant a written kind with no tier text, or a mark with an unknown kind, and see the error.
It checks:
  * the switch and the reading settings: READING.enabled is a boolean; the dark lights are perceiver light keys;
    the squiggle and the common numerals carry no digit; the learned-word cap is a count;
  * the literacy tiers: LITERACY_TIERS names the literacy tiers of domains/shared_frames.py in order, and each says
    what it reads ('words', 'short' or 'full');
  * the numeracy tiers: the minimum levels start at 0 and rise, the counts run exact_max <= few_max, and prices are
    'units' or 'figure'; the units include 'coin' (the figure unit); NUMERAL_WORDS covers 0 to 20 and the tens;
  * each written kind (WRITTEN_KINDS) has a label and a template for 'unreadable' and for every reading mode the
    literacy tiers use (words, short, full), and each
    template uses only the fields a reader fills (label, shown, short, text) and carries no digit;
  * each written mark (WRITTEN_MARKS, keyed by physical object id) names a written kind, its refers_to word appears in
    its text, its text and short carry no digit, {price} appears only with a price and a unit, and a price mark's
    unit is a NUMERACY_UNITS key;
  * RECOGNISED_SEED names trades of the pack (TRADES) and gives lowercase words.
"""
from __future__ import annotations

import re

from domains.pack import load_pack

DIGIT = re.compile(r"\d")
WORD = re.compile(r"[A-Za-z]+")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
TABLES = ("READING", "LITERACY_TIERS", "NUMERACY_TIERS", "NUMERACY_UNITS", "NUMERAL_WORDS", "WRITTEN_KINDS",
          "WRITTEN_MARKS", "RECOGNISED_SEED")
LITERACY_TIERS = ("labouring", "functional", "educated")   # domains/shared_frames.py literacy_tier, in order
READS = ("words", "short", "full")
FIELDS = {"label", "shown", "short", "text"}
LIGHTS = ("day", "dim", "dark", "lamplight")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_reading(pack_path, errors, warnings, info, *, kinds=None, marks=None):
    pack = load_pack(pack_path)
    missing = [name for name in TABLES if name not in pack.names()]
    if missing:
        errors.append(f"READING: the pack has no {', '.join(missing)} table (world/literacy.json)")
        return
    kinds = pack["WRITTEN_KINDS"] if kinds is None else kinds
    marks = pack["WRITTEN_MARKS"] if marks is None else marks
    _check_reading(pack, errors)
    _check_literacy(pack, errors)
    _check_numeracy(pack, errors)
    _check_kinds(pack, kinds, errors)
    _check_marks(pack, kinds, marks, errors)
    _check_seed(pack, errors)
    if not errors:
        info.append(f"READING: {len(kinds)} written kinds, {len(marks)} marks, "
                    f"{len(pack['LITERACY_TIERS'])} literacy tiers, {len(pack['NUMERACY_TIERS'])} numeracy tiers; "
                    f"reading is {'on' if pack['READING']['enabled'] else 'off'} in this pack")


def _check_reading(pack, errors):
    rd = pack["READING"]
    if not isinstance(rd["enabled"], bool):
        errors.append("READING.enabled must be true or false")
    for light in rd["dark_lights"]:
        if light not in LIGHTS:
            errors.append(f"READING.dark_lights: '{light}' is not a light the perceiver knows")
    if DIGIT.search(str(rd["squiggle"])) or not str(rd["squiggle"]).strip():
        errors.append("READING.squiggle must be non-empty and carry no digit")
    for word in rd["common_numerals"]:
        if not WORD.fullmatch(str(word)) or str(word) != str(word).lower():
            errors.append(f"READING.common_numerals: '{word}' must be a lowercase word")
    if not (_is_int(rd["learned_max"]) and rd["learned_max"] >= 0):
        errors.append("READING.learned_max must be a count of zero or more")
    if not str(rd["learned_kind"]).strip():
        errors.append("READING.learned_kind must name a memory kind")


def _check_literacy(pack, errors):
    rows = pack["LITERACY_TIERS"]
    names = [row["tier"] for row in rows]
    if names != list(LITERACY_TIERS):
        errors.append(f"LITERACY_TIERS: the tiers must be {', '.join(LITERACY_TIERS)} in order, not {names}")
    for row in rows:
        if row["reads"] not in READS:
            errors.append(f"LITERACY_TIERS[{row['tier']}]: reads '{row['reads']}' must be one of {READS}")


def _check_numeracy(pack, errors):
    rows = pack["NUMERACY_TIERS"]
    names = [row["tier"] for row in rows]
    if len(set(names)) != len(names):
        errors.append("NUMERACY_TIERS: tier names must be unique")
    levels = [float(row["min_level"]) for row in rows]
    if not rows or levels[0] != 0.0 or levels != sorted(levels) or len(set(levels)) != len(levels):
        errors.append("NUMERACY_TIERS: the minimum levels must start at 0.0 and rise")
    for row in rows:
        where = f"NUMERACY_TIERS[{row['tier']}]"
        if not (_is_int(row["exact_max"]) and _is_int(row["few_max"]) and 0 <= row["exact_max"] <= row["few_max"]):
            errors.append(f"{where}: exact_max and few_max must be counts with exact_max <= few_max")
        if row["few_max"] > 999:
            errors.append(f"{where}: few_max above 999 cannot be spelled (NUMERAL_WORDS)")
        if row["prices"] not in ("units", "figure"):
            errors.append(f"{where}: prices must be 'units' or 'figure', not '{row['prices']}'")
    units = pack["NUMERACY_UNITS"]
    if "coin" not in units or float(units["coin"]["coin"]) != 1.0:
        errors.append("NUMERACY_UNITS: the unit 'coin' (worth 1.0 coin) is needed for figures")
    for name, spec in units.items():
        if float(spec["coin"]) <= 0 or not spec["singular"] or not spec["plural"]:
            errors.append(f"NUMERACY_UNITS[{name}]: coin must be above zero and both words given")
        for word in (spec["singular"], spec["plural"]):
            if DIGIT.search(word):
                errors.append(f"NUMERACY_UNITS[{name}]: '{word}' carries a digit")
    numerals = pack["NUMERAL_WORDS"]
    if len(numerals["words"]) != 21 or len(numerals["tens"]) != 10:
        errors.append("NUMERAL_WORDS: words must list 0 to 20 and tens must list 0 to 90 by ten (10 entries)")
    for word in numerals["words"][1:] + numerals["tens"][2:] + [numerals["hundred"], numerals["and"]]:
        if not WORD.fullmatch(str(word)):
            errors.append(f"NUMERAL_WORDS: '{word}' must be a plain word")


def _check_kinds(pack, kinds, errors):
    modes = sorted({row["reads"] for row in pack["LITERACY_TIERS"]})
    for name, spec in kinds.items():
        where = f"WRITTEN_KINDS[{name}]"
        if not str(spec.get("label", "")).strip() or DIGIT.search(str(spec.get("label", ""))):
            errors.append(f"{where}: needs a label with no digit")
        templates = spec.get("tiers", {})
        for key in ["unreadable"] + modes:
            if not str(templates.get(key, "")).strip():
                errors.append(f"{where} has no tier text for '{key}'")
        for key, template in templates.items():
            if key not in ("unreadable",) + READS:
                errors.append(f"{where}: template '{key}' is not a reading mode (unreadable, words, short, full)")
            if DIGIT.search(str(template)):
                errors.append(f"{where}: template for '{key}' carries a digit")
            for field in PLACEHOLDER.findall(str(template)):
                if field not in FIELDS:
                    errors.append(f"{where}: template for '{key}' names '{{{field}}}', which a reader does not fill")


def _check_marks(pack, kinds, marks, errors):
    units = pack["NUMERACY_UNITS"]
    for object_id, mark in marks.items():
        where = f"WRITTEN_MARKS[{object_id}]"
        if not str(object_id).strip():
            errors.append("WRITTEN_MARKS: a mark needs a physical object id")
        if mark.get("kind") not in kinds:
            errors.append(f"{where}: kind '{mark.get('kind')}' is not in WRITTEN_KINDS")
        refers = str(mark.get("refers_to", ""))
        if not WORD.fullmatch(refers) or refers != refers.lower():
            errors.append(f"{where}: refers_to must be one lowercase word")
        text, short = str(mark.get("text", "")), str(mark.get("short", ""))
        if refers.lower() not in {w.lower() for w in WORD.findall(text)}:
            errors.append(f"{where}: refers_to '{refers}' does not appear in the text")
        for label, value in (("text", text), ("short", short)):
            if DIGIT.search(PLACEHOLDER.sub("", value)):
                errors.append(f"{where}: {label} carries a digit (a figure is {{price}})")
            for field in PLACEHOLDER.findall(value):
                if field != "price":
                    errors.append(f"{where}: {label} names '{{{field}}}'; only {{price}} is filled")
        if "{price}" in text or "{price}" in short:
            if not isinstance(mark.get("price"), (int, float)) or float(mark["price"]) <= 0:
                errors.append(f"{where}: a {{price}} mark needs a price above zero")
            if mark.get("unit") not in units:
                errors.append(f"{where}: unit '{mark.get('unit')}' is not in NUMERACY_UNITS")
        elif "price" in mark:
            errors.append(f"{where}: has a price but its text does not show {{price}}")


def _check_seed(pack, errors):
    trades = set(pack["TRADES"])
    for trade, words in pack["RECOGNISED_SEED"].items():
        if trade not in trades:
            errors.append(f"RECOGNISED_SEED[{trade}]: not a trade in TRADES")
        for word in words:
            if not WORD.fullmatch(str(word)) or str(word) != str(word).lower():
                errors.append(f"RECOGNISED_SEED[{trade}]: '{word}' must be a lowercase word")
