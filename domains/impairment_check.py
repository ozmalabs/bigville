"""impairment_check.py -- self-test checks for the IMPAIRMENT, DISTORTION and IMPAIRMENT_NEIGHBOURS tables (Phase 065).

    check_impairment(pack_path, errors, warnings, info, *, rows=None, sources=None)

Called from bigville_entities.check_consistency with the pack path. `rows` replaces the DISTORTION rows and `sources`
replaces IMPAIRMENT.sources, so a test can plant a source with no row and see the error. It checks:
  * the switch, the strength and the cap: IMPAIRMENT.enabled is a boolean, strength is between 0 and 1, max_rate is
    above 0 and at most 1;
  * the sources: every source IMPAIRMENT names has exactly one DISTORTION row (an error otherwise), and every row names
    a source IMPAIRMENT lists (a warning otherwise, since the row then never applies);
  * each row: a measure the impairment reads, with either `levels` (for intoxication_band and light) or `steps` (for
    fatigue and illness, thresholds ascending, each rate between 0 and 1); the level keys are the world's bands or the
    lights; the kinds are person and thing, with at least one mechanism each, and each mechanism is one the code knows,
    and only a person takes neighbour_stage;
  * the light levels: each key is a light the perceiver reads and each value is a rate between 0 and 1;
  * IMPAIRMENT_NEIGHBOURS: it has one entry for each life stage, and each neighbour is a life stage other than itself.
"""
from __future__ import annotations

from domains import impairment as I
from domains.pack import load_pack
from domains.world_affordances import INTOXICATION_BANDS

NUMERIC_MEASURES = ("fatigue", "illness")
CATEGORY_MEASURES = {"intoxication_band": INTOXICATION_BANDS, "light": I.LIGHTS}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_impairment(pack_path, errors, warnings, info, *, rows=None, sources=None):
    pack = load_pack(pack_path)
    missing = [name for name in ("IMPAIRMENT", "DISTORTION", "IMPAIRMENT_NEIGHBOURS", "PERCEPTION") if name not in pack.names()]
    if missing:
        errors.append(f"IMPAIRMENT: the pack has no {', '.join(missing)} table (world/impairment.json)")
        return
    table = pack["IMPAIRMENT"]
    rows = pack["DISTORTION"] if rows is None else rows
    listed = list(table["sources"]) if sources is None else list(sources)
    stages = set(pack["PERCEPTION"]["stage_nouns"])
    before = len(errors)
    _check_switch(table, errors)
    _check_sources(listed, rows, errors, warnings)
    for row in rows:
        _check_row(row, errors)
    _check_light_levels(table, errors)
    _check_neighbours(pack["IMPAIRMENT_NEIGHBOURS"], stages, errors)
    if len(errors) == before:
        state = "on" if table["enabled"] else "off"
        info.append(f"IMPAIRMENT: {len(listed)} sources ({', '.join(listed)}), {len(rows)} rows, {len(I.MECHANISMS)} "
                    f"mechanisms, the impairment is {state} in this pack")


def _check_switch(table, errors):
    if not isinstance(table.get("enabled"), bool):
        errors.append(f"IMPAIRMENT.enabled must be true or false, not {table.get('enabled')!r}")
    strength = table.get("strength")
    if not _is_number(strength) or not 0.0 <= float(strength) <= 1.0:
        errors.append(f"IMPAIRMENT.strength must be a number from 0 to 1, not {strength!r}")
    cap = table.get("max_rate")
    if not _is_number(cap) or not 0.0 < float(cap) <= 1.0:
        errors.append(f"IMPAIRMENT.max_rate must be a number above 0 and at most 1, not {cap!r}")


def _check_sources(listed, rows, errors, warnings):
    if not listed:
        errors.append("IMPAIRMENT.sources is empty: no impairment is active in any pack")
    if len(set(listed)) != len(listed):
        errors.append(f"IMPAIRMENT.sources repeats a source: {listed}")
    names = [row.get("source") for row in rows]
    for source in sorted(set(listed)):
        count = names.count(source)
        if count != 1:
            errors.append(f"IMPAIRMENT source {source!r} has {count} DISTORTION rows, expected exactly 1")
    for name in sorted(set(names) - set(listed)):
        warnings.append(f"DISTORTION row {name!r} names a source IMPAIRMENT.sources does not list: it never applies")


def _check_row(row, errors):
    source = row.get("source", "?")
    measure = row.get("measure")
    if measure not in I.MEASURES:
        errors.append(f"DISTORTION {source!r}: measure {measure!r} is not one the impairment reads ({list(I.MEASURES)})")
        return
    has_levels, has_steps = "levels" in row, "steps" in row
    if has_levels == has_steps:
        errors.append(f"DISTORTION {source!r} must have exactly one of levels or steps")
    if measure in CATEGORY_MEASURES and not has_levels:
        errors.append(f"DISTORTION {source!r}: measure {measure!r} is a category and needs levels")
    if measure in NUMERIC_MEASURES and not has_steps:
        errors.append(f"DISTORTION {source!r}: measure {measure!r} is a number and needs steps")
    if has_levels:
        allowed = CATEGORY_MEASURES.get(measure, ())
        for key, rate in dict(row["levels"]).items():
            if key not in allowed:
                errors.append(f"DISTORTION {source!r}: level {key!r} is not a {measure} value {list(allowed)}")
            _check_rate(f"DISTORTION {source!r} level {key!r}", rate, errors)
    if has_steps:
        thresholds = [step[0] for step in row["steps"]]
        if not row["steps"] or any(not _is_number(t) for t in thresholds) or thresholds != sorted(thresholds):
            errors.append(f"DISTORTION {source!r}: steps must be a non-empty list of [threshold, rate] with ascending thresholds")
        for step in row["steps"]:
            if len(step) != 2 or not _is_number(step[0]):
                errors.append(f"DISTORTION {source!r}: step {step!r} is not [threshold, rate]")
                continue
            _check_rate(f"DISTORTION {source!r} step {step!r}", step[1], errors)
    kinds = row.get("kinds", {})
    if set(kinds) != set(I.KINDS):
        errors.append(f"DISTORTION {source!r}: kinds must name exactly {list(I.KINDS)}, not {sorted(kinds)}")
    for kind, mechanisms in kinds.items():
        if not mechanisms:
            errors.append(f"DISTORTION {source!r}: kind {kind!r} names no mechanism")
        for mechanism in mechanisms:
            if mechanism not in I.MECHANISMS:
                errors.append(f"DISTORTION {source!r}: mechanism {mechanism!r} is not one the code knows {list(I.MECHANISMS)}")
            if mechanism == "neighbour_stage" and kind != "person":
                errors.append(f"DISTORTION {source!r}: neighbour_stage applies to a person, not a {kind}")


def _check_rate(where, rate, errors):
    if not _is_number(rate) or not 0.0 <= float(rate) <= 1.0:
        errors.append(f"{where}: a rate must be a number from 0 to 1, not {rate!r}")


def _check_light_levels(table, errors):
    levels = table.get("light_levels", {})
    for key, rate in dict(levels).items():
        if key not in I.LIGHTS:
            errors.append(f"IMPAIRMENT.light_levels has {key!r}, which is not a light {list(I.LIGHTS)}")
        _check_rate(f"IMPAIRMENT.light_levels {key!r}", rate, errors)
    if set(levels) != set(I.LIGHTS):
        errors.append(f"IMPAIRMENT.light_levels must name every light {list(I.LIGHTS)}")


def _check_neighbours(neighbours, stages, errors):
    if set(neighbours) != stages:
        errors.append(f"IMPAIRMENT_NEIGHBOURS must have one entry per life stage {sorted(stages)}, "
                      f"not {sorted(neighbours)}")
    for stage, others in neighbours.items():
        if not others:
            errors.append(f"IMPAIRMENT_NEIGHBOURS {stage!r} has no neighbour")
        for other in others:
            if other == stage or other not in stages:
                errors.append(f"IMPAIRMENT_NEIGHBOURS {stage!r}: {other!r} is not another life stage")
