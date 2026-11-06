"""autopilot_check.py -- self-test checks for a pack's AUTOPILOT table (Phase 059).

    check_autopilot(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency), like the persona checks. It
reads the pack with domains/pack.load_pack. It checks:
- the AUTOPILOT table has every key the gate and the backend read;
- routine_strength terms name traits in PERSONA_TRAITS, with a positive weight and a boolean invert, and
  when_no_terms lies in 0..1;
- max_quiet_ticks is whole and at least 1, and least <= most;
- boundary_consult_share lies in 0..1;
- consult_triggers names only known triggers, each once, and includes check_in and nothing_to_do (without
  check_in a resident is never checked on; without nothing_to_do an idle autopilot never asks the model);
- the thresholds are numbers, refusal_repeats and max_calls_per_resident_per_day are whole and at least 1.
"""
from __future__ import annotations

from domains.autopilot import TRIGGERS
from domains.pack import PackError, load_pack

REQUIRED = ("routine_strength", "max_quiet_ticks", "boundary_consult_share", "consult_triggers",
            "hunger_threshold", "energy_threshold", "refusal_repeats", "max_calls_per_resident_per_day")
ALWAYS_TRIGGERS = ("check_in", "nothing_to_do")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_autopilot(pack_name, errors, warnings, info):
    """Run every autopilot check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"AUTOPILOT: cannot load pack '{pack_name}': {exc}")
        return
    if "AUTOPILOT" not in pack or "PERSONA_TRAITS" not in pack:
        errors.append(f"AUTOPILOT: pack '{pack_name}' has no AUTOPILOT or PERSONA_TRAITS table")
        return
    spec = pack["AUTOPILOT"]
    missing = [key for key in REQUIRED if key not in spec]
    if missing:
        errors.append(f"AUTOPILOT ({pack_name}): missing {', '.join(missing)}")
        return
    before = len(errors)
    traits = pack["PERSONA_TRAITS"]
    strength = spec["routine_strength"]
    terms = strength.get("terms") if isinstance(strength, dict) else None
    if not isinstance(terms, list) or not terms:
        errors.append(f"AUTOPILOT ({pack_name}): routine_strength needs a non-empty terms list")
    else:
        for term in terms:
            if not isinstance(term, dict) or term.get("trait") not in traits:
                errors.append(f"AUTOPILOT ({pack_name}): a routine_strength term names no PERSONA_TRAITS trait")
                continue
            if not _number(term.get("weight")) or term["weight"] <= 0:
                errors.append(f"AUTOPILOT ({pack_name}): {term['trait']} needs a positive weight")
            if not isinstance(term.get("invert"), bool):
                errors.append(f"AUTOPILOT ({pack_name}): {term['trait']} needs invert true or false")
    if not _number(strength.get("when_no_terms")) or not 0 <= strength["when_no_terms"] <= 1:
        errors.append(f"AUTOPILOT ({pack_name}): when_no_terms must lie in 0..1")
    quiet = spec["max_quiet_ticks"]
    if not (isinstance(quiet, dict) and _whole(quiet.get("least")) and _whole(quiet.get("most"))
            and quiet["least"] >= 1 and quiet["least"] <= quiet["most"]):
        errors.append(f"AUTOPILOT ({pack_name}): max_quiet_ticks needs whole least and most, 1 <= least <= most")
    share = spec["boundary_consult_share"]
    if not _number(share) or not 0 <= share <= 1:
        errors.append(f"AUTOPILOT ({pack_name}): boundary_consult_share must lie in 0..1")
    triggers = spec["consult_triggers"]
    if not isinstance(triggers, list) or not all(isinstance(name, str) for name in triggers):
        errors.append(f"AUTOPILOT ({pack_name}): consult_triggers must be a list of names")
    else:
        unknown = sorted(set(triggers) - set(TRIGGERS))
        if unknown:
            errors.append(f"AUTOPILOT ({pack_name}): unknown consult triggers {', '.join(unknown)}")
        if len(set(triggers)) != len(triggers):
            errors.append(f"AUTOPILOT ({pack_name}): consult_triggers repeats a name")
        for name in ALWAYS_TRIGGERS:
            if name not in triggers:
                errors.append(f"AUTOPILOT ({pack_name}): consult_triggers must include {name}")
    for key in ("hunger_threshold", "energy_threshold"):
        if not _number(spec[key]):
            errors.append(f"AUTOPILOT ({pack_name}): {key} must be a number")
    for key in ("refusal_repeats", "max_calls_per_resident_per_day"):
        if not _whole(spec[key]) or spec[key] < 1:
            errors.append(f"AUTOPILOT ({pack_name}): {key} must be a whole number of at least 1")
    if len(errors) == before:
        info.append(f"AUTOPILOT ({pack_name}): all autopilot checks pass "
                    f"({len(triggers)} consult triggers, quiet ticks {quiet['least']} to {quiet['most']})")
