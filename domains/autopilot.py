"""autopilot.py -- the pack numbers and pure rules behind the autopilot (Phase 059).

An LLM resident is consulted only at some turns. Between them the autopilot, a DeterministicBackend
for the same character, carries the resident along its usual day. Every number is read from the pack
(`world/autopilot.json`, table AUTOPILOT); nothing here calls a provider or changes the world.

    routine_strength(personality, identity)   -> 0..1, how much the resident keeps to habit
    max_quiet_ticks(strength)                 -> the longest span between consults, in ticks
    boundary_consult_chance(strength)         -> the chance a routine boundary prompts a consult
    habit_roll(*parts)                        -> a fixed number in [0, 1) for a resident, day and block
    usual_block(identity, calendar)           -> the block name now, or None (no routine for the job)
    usual_words(identity, calendar)           -> "what you would usually do now", in words, or ""
    TRIGGERS                                  -> every event name the gate may use

The routine comes from domains/persona.py (Phase 058), so the words here are the words the persona
card uses. No routine is enforced: the resident may depart from it.
"""
from __future__ import annotations

import functools

from domains import determinism
from domains.pack import load_pack

DEFAULT_PACK = "bigville"

# Every event the gate knows. The pack's consult_triggers picks the ones that prompt a consult.
# A game reason (the continuation interrupts of bigville/game.py) maps to the same name where one exists.
TRIGGERS = ("hunger_threshold", "energy_threshold", "tie_in_view", "spoken_to", "task_failed",
            "refusal_repeats", "world_event", "routine_boundary", "nothing_to_do", "check_in", "reaction")


def table(pack=DEFAULT_PACK):
    """The AUTOPILOT table of the pack."""
    return load_pack(pack)["AUTOPILOT"]


def _clamp(value, low=0.0, high=1.0):
    return min(high, max(low, float(value)))


def _number(value):
    """A float, or None when the value is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def routine_strength(personality, identity=None, pack=DEFAULT_PACK):
    """How much the resident keeps to habit, 0 (none) to 1 (a creature of habit).

    A weighted mean of the traits named by the pack (`routine_strength.terms`). A term reads its trait's
    source number from the personality, then from the identity; a term whose number is missing is left
    out, not defaulted. If no term is present the pack's `when_no_terms` applies."""
    spec = table(pack)["routine_strength"]
    traits = load_pack(pack)["PERSONA_TRAITS"]
    personality, identity = dict(personality or {}), dict(identity or {})
    total = weight_total = 0.0
    for term in spec["terms"]:
        source = traits[term["trait"]]["source"]
        value = _number(personality.get(source))
        if value is None:
            value = _number(identity.get(source))
        if value is None:
            continue
        share = _clamp(value)
        if term["invert"]:
            share = 1.0 - share
        total += float(term["weight"]) * share
        weight_total += float(term["weight"])
    if weight_total == 0.0:
        return _clamp(spec["when_no_terms"])
    return _clamp(total / weight_total)


def max_quiet_ticks(strength, pack=DEFAULT_PACK):
    """The longest span between consults for a resident of this routine strength, in whole ticks (at least 1)."""
    spec = table(pack)["max_quiet_ticks"]
    least, most = float(spec["least"]), float(spec["most"])
    return max(1, int(round(least + (most - least) * _clamp(strength))))


def boundary_consult_chance(strength, pack=DEFAULT_PACK):
    """The chance that a routine boundary prompts a consult: share * (1 - strength), in [0, 1]."""
    return _clamp(float(table(pack)["boundary_consult_share"]) * (1.0 - _clamp(strength)))


def habit_roll(*parts):
    """A fixed number in [0, 1) for the given parts, from the determinism helper. The same parts always
    give the same number, so a consult pattern repeats from a seed. This is decision gating, not a world
    outcome, and it consumes no shared RNG."""
    return determinism.uniform(0, "autopilot-habit", *parts)


@functools.lru_cache(maxsize=512)
def _blocks(job, stage, weekday, season, pack):
    from domains.persona import routine_blocks
    return tuple(dict(block) for block in routine_blocks(job, stage, weekday=weekday, season=season, pack=pack))


def _clock(calendar):
    calendar = dict(calendar or {})
    hour = _number(calendar.get("hour"))
    day = _number(calendar.get("day"))
    return (6.0 if hour is None else hour), (None if day is None else int(day)), calendar.get("season")


def _routine(identity, calendar, pack):
    """(blocks, index of the block now, hour, weekday, season), or None when the job has no routine."""
    from domains.persona import block_now
    identity = dict(identity or {})
    job = str(identity.get("role", ""))
    pk = load_pack(pack)
    stage = str(identity.get("life_stage") or "adult")
    stages = pk["ROUTINE_STAGE"]
    stage = stage if stage in stages else "adult"
    # routine_blocks reads the stage's row (a dependant row) or the job's row; no row, no routine.
    if (stages[stage].get("row") or job) not in pk["ROUTINE"]:
        return None
    hour, weekday, season = _clock(calendar)
    blocks = _blocks(job, stage, weekday, season, pack)
    return blocks, block_now(blocks, hour), hour, weekday, season


def usual_block(identity, calendar, pack=DEFAULT_PACK):
    """The name of the usual-day block now (morning, work, midday, afternoon, evening or sleep), or None."""
    routine = _routine(identity, calendar, pack)
    if routine is None:
        return None
    blocks, index = routine[0], routine[1]
    return str(blocks[index]["block"])


def usual_words(identity, calendar, pack=DEFAULT_PACK):
    """What the resident would usually do now, in words, for the model's prompt. "" when there is no routine."""
    from domains.persona import usual_day
    identity = dict(identity or {})
    job = str(identity.get("role", ""))
    if _routine(identity, calendar, pack) is None:
        return ""
    hour, weekday, season = _clock(calendar)
    day = usual_day(job, str(identity.get("life_stage") or "adult"), hour=hour,
                    weekday=weekday, season=season, pack=pack)
    now = day["blocks"][day["now"]]
    text = f"Usually now: {now['task']} ({now['phrase']})."
    if day["today"]:
        text = f"Today is {day['today']}. " + text
    return text
