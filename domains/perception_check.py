"""perception_check.py -- self-test checks for the PERCEPTION and PERCEIVER_TIERS tables (Phase 062).

    check_perception(pack_path, errors, warnings, info, *, tiers=None)

Called from bigville_entities.check_consistency with the pack path. `tiers` replaces the pack's PERCEIVER_TIERS,
so a test can plant a kind with no tier 0, or a tier with an unknown gate, and see the error. It checks:
  * the switch and the faculties: PERCEPTION.enabled is a boolean, and the faculties are the five the perceiver
    declares; the fallback mode is a mode the perceiver knows;
  * the gate vocabulary: PERCEPTION.gates names exactly the gates the perceiver reads, each on the side the perceiver
    reads it from;
  * the numbers: the distance bands, the light the view takes when day and night is off, and the two thresholds;
  * the light levels (Phase 062B): dark is below every MARKS see_light and each other light is at or above all of
    them, so the perceiver's light gate and the world's visibility rule agree (checked when the pack has marks);
  * the stage words cover every LIFE_STAGES stage, carry no digit, and start with a consonant (the tier words say
    'a {stage}');
  * each mark gate names a MARKS kind (checked when the pack has marks);
  * each kind (PERCEIVER_TIERS) has tiers numbered 0, 1, 2, ... with tier 0 unconditional; each gate names a known
    condition with a value of the right kind; each words template has no digit, and names only the fields its kind
    fills (a person: stage and job; a thing: kind).
"""
from __future__ import annotations

import re

from domains import perceiver as P
from domains.pack import load_pack
from domains.world_affordances import INTOXICATION_BANDS

DIGIT = re.compile(r"\d")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
FIELDS = {"person": {"stage", "job"}, "thing": {"kind"}}
TABLES = ("PERCEPTION", "PERCEIVER_TIERS")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_perception(pack_path, errors, warnings, info, *, tiers=None):
    pack = load_pack(pack_path)
    missing = [name for name in TABLES if name not in pack.names()]
    if missing:
        errors.append(f"PERCEPTION: the pack has no {', '.join(missing)} table (world/perception.json)")
        return
    pk = pack["PERCEPTION"]
    rows_by_kind = pack["PERCEIVER_TIERS"] if tiers is None else tiers
    _check_switch_and_faculties(pk, errors)
    _check_gates(pk, errors)
    _check_numbers(pk, errors)
    _check_light_levels(pk, pack, errors)
    _check_stages(pk, pack, errors)
    _check_tiers(pk, rows_by_kind, errors)
    _check_marks_named(rows_by_kind, pack, errors)
    if not errors:
        state = "on" if pk["enabled"] else "off"
        info.append(f"PERCEPTION: {len(rows_by_kind)} kinds ({', '.join(sorted(rows_by_kind))}), "
                    f"{sum(len(rows) for rows in rows_by_kind.values())} tiers, the perceiver is {state} in this pack")


def _check_switch_and_faculties(pk, errors):
    if not isinstance(pk.get("enabled"), bool):
        errors.append(f"PERCEPTION.enabled must be true or false, not {pk.get('enabled')!r}")
    faculties = pk.get("faculties")
    if not isinstance(faculties, list) or set(faculties) != set(P.FACULTIES) or len(faculties) != len(P.FACULTIES):
        errors.append(f"PERCEPTION.faculties must be exactly {list(P.FACULTIES)}, not {faculties!r}")
    if pk.get("fallback") not in P.MODES:
        errors.append(f"PERCEPTION.fallback must be one of {list(P.MODES)}, not {pk.get('fallback')!r}")


def _check_gates(pk, errors):
    gates = pk.get("gates")
    if not isinstance(gates, dict):
        errors.append("PERCEPTION.gates must be a table of gate name to side")
        return
    if set(gates) != set(P.GATE_SIDES):
        errors.append(f"PERCEPTION.gates names {sorted(gates)}, but the perceiver reads {sorted(P.GATE_SIDES)}")
    for name, side in gates.items():
        if name in P.GATE_SIDES and side != P.GATE_SIDES[name]:
            errors.append(f"PERCEPTION.gates[{name}] is '{side}', but the perceiver reads it from "
                          f"'{P.GATE_SIDES[name]}'")


def _check_numbers(pk, errors):
    bands_ = pk.get("distance_bands")
    if not isinstance(bands_, dict) or not bands_:
        errors.append("PERCEPTION.distance_bands must name at least one band")
    else:
        for name, cells in bands_.items():
            if not _is_int(cells) or cells < 1:
                errors.append(f"PERCEPTION.distance_bands[{name}] must be a whole number of cells of at least 1, "
                              f"not {cells!r}")
    if pk.get("light_when_off") not in P.LIGHTS:
        errors.append(f"PERCEPTION.light_when_off must be one of {list(P.LIGHTS)}, not {pk.get('light_when_off')!r}")
    for key in ("mark_min_level", "trade_min_level", "notice_min_level"):
        value = pk.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 < float(value) <= 1.0:
            errors.append(f"PERCEPTION.{key} must be a level above 0 and at most 1, not {value!r}")


def _check_light_levels(pk, pack, errors):
    """The light the mark gate reads (PERCEPTION.light_level) must agree with the perceiver's light gate: dark is
    below every MARKS see_light, and each other light is at or above all of them. Checked when the pack has marks."""
    levels = pk.get("light_level")
    if not isinstance(levels, dict) or set(levels) != set(P.LIGHTS):
        errors.append(f"PERCEPTION.light_level must give a level for each of {list(P.LIGHTS)}, not {levels!r}")
        return
    for light, value in levels.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"PERCEPTION.light_level[{light}] must be a level from 0 to 1, not {value!r}")
    marks = pack["MARKS"] if "MARKS" in pack.names() else {}
    if not marks:
        return
    see = [float(spec["see_light"]) for spec in marks.values()]
    if float(levels["dark"]) >= min(see):
        errors.append(f"PERCEPTION.light_level[dark] ({levels['dark']}) is not below every MARKS see_light "
                      f"(lowest {min(see)}), so a mark could be seen in the dark that the perceiver calls dark")
    for light in P.LIGHTS:
        if light != "dark" and float(levels[light]) < max(see):
            errors.append(f"PERCEPTION.light_level[{light}] ({levels[light]}) is below the highest MARKS see_light "
                          f"({max(see)}), so the perceiver would call a light a mark is hidden in 'not dark'")


def _check_stages(pk, pack, errors):
    nouns = pk.get("stage_nouns")
    stages = set(pack["LIFE_STAGES"]) if "LIFE_STAGES" in pack.names() else set()
    if not isinstance(nouns, dict):
        errors.append("PERCEPTION.stage_nouns must be a table of life stage to words")
        return
    if set(nouns) != stages:
        errors.append(f"PERCEPTION.stage_nouns covers {sorted(nouns)}, but LIFE_STAGES has {sorted(stages)}")
    for stage, noun in nouns.items():
        if not isinstance(noun, str) or not noun.strip() or DIGIT.search(noun):
            errors.append(f"PERCEPTION.stage_nouns[{stage}] must be words with no digit, not {noun!r}")
    _check_articles(nouns, errors)


def _check_articles(nouns, errors):
    """A tier template puts 'a' before {stage} ('a {stage}', 'a dirty {stage}'), so no stage noun may start with a
    vowel: 'a elder' is wrong. The templates are the perceiver's (world/perception.json PERCEIVER_TIERS)."""
    for stage, noun in nouns.items():
        if isinstance(noun, str) and noun.strip()[:1].lower() in "aeiou":
            errors.append(f"PERCEPTION.stage_nouns[{stage}] is {noun!r}, which starts with a vowel; the tier words "
                          f"say 'a {{stage}}', so the noun needs a consonant to read correctly")


def _check_marks_named(rows_by_kind, pack, errors):
    """A mark gate names a mark of MARKS (Phase 063). Checked when the pack has marks."""
    marks = pack["MARKS"] if "MARKS" in pack.names() else {}
    if not marks:
        return
    for kind, rows in rows_by_kind.items():
        for row in rows if isinstance(rows, list) else []:
            name = (row.get("gate") or {}).get("mark") if isinstance(row, dict) else None
            if name is not None and name not in marks:
                errors.append(f"PERCEIVER_TIERS[{kind}] tier {row.get('tier')}: mark '{name}' is not a MARKS kind "
                              f"({sorted(marks)})")


def _check_tiers(pk, rows_by_kind, errors):
    if set(rows_by_kind) != set(P.KINDS):
        errors.append(f"PERCEIVER_TIERS has kinds {sorted(rows_by_kind)}, but the perceiver reads {sorted(P.KINDS)}")
    bands_ = pk.get("distance_bands") if isinstance(pk.get("distance_bands"), dict) else {}
    for kind in P.KINDS:
        rows = rows_by_kind.get(kind)
        if not isinstance(rows, list) or not rows:
            errors.append(f"PERCEIVER_TIERS[{kind}] has no tiers")
            continue
        numbers = [row.get("tier") if isinstance(row, dict) else None for row in rows]
        if 0 not in numbers:
            errors.append(f"PERCEIVER_TIERS[{kind}] has no tier 0, so a {kind} with no gate met has no percept")
            continue
        if numbers != list(range(len(rows))):
            errors.append(f"PERCEIVER_TIERS[{kind}] tiers are numbered {numbers}, expected 0 to {len(rows) - 1} in order")
            continue
        if rows[0].get("gate") != {}:
            errors.append(f"PERCEIVER_TIERS[{kind}] tier 0 must have no gate, so every {kind} has a percept")
        for row in rows:
            where = f"PERCEIVER_TIERS[{kind}] tier {row.get('tier')}"
            _check_row(row, where, kind, bands_, errors)


def _check_row(row, where, kind, bands_, errors):
    words = row.get("words")
    if not isinstance(words, str) or not words.strip():
        errors.append(f"{where}: words must be a non-empty string")
    else:
        if DIGIT.search(words):
            errors.append(f"{where}: words {words!r} carry a digit")
        fields = set(PLACEHOLDER.findall(words))
        if not fields <= FIELDS[kind]:
            errors.append(f"{where}: words {words!r} name {sorted(fields - FIELDS[kind])}, which a {kind} does not fill")
    gate = row.get("gate")
    if not isinstance(gate, dict):
        errors.append(f"{where}: gate must be a table")
        return
    for name, value in gate.items():
        if name not in P.GATE_SIDES:
            errors.append(f"{where}: gate '{name}' is unknown (the gates are {sorted(P.GATE_SIDES)})")
        elif name == "light_not":
            if not isinstance(value, list) or not value or not set(value) <= set(P.LIGHTS):
                errors.append(f"{where}: light_not must name lights from {list(P.LIGHTS)}, not {value!r}")
        elif name == "distance":
            if value not in bands_:
                errors.append(f"{where}: distance '{value}' is not a band of PERCEPTION.distance_bands")
        elif name == "band_max":
            if value not in INTOXICATION_BANDS:
                errors.append(f"{where}: band_max '{value}' is not an intoxication band {list(INTOXICATION_BANDS)}")
        elif name == "trade_skill":
            if value is not True:
                errors.append(f"{where}: trade_skill is true (the resident's level in the subject's trade), not {value!r}")
        elif name == "mark":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_]+", value):
                errors.append(f"{where}: mark must be a mark name (lower-case letters), not {value!r}")
