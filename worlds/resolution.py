"""The resolution core (Phase 050): one rule for every attempt.

An attempt has a capability C (what the actor brings) and a demand D (what the thing asks for). The ratio
rho = C / D maps, deterministically, to progress, cost, strain, wear and noise. This module is pure: it
holds no world state and draws no random numbers. Every number is passed in from the pack's RESOLUTION
table (domains/bigville_entities.RESOLUTION), so the same inputs always give the same outputs.

Reference point. An average adult (effective strength 1.0, size 1.0, full reserve, health 1.0) at
intensity 1.0, with a skill of 1.0 in the verb's skill, a tool that fits (fit 1.0), no team (1.0) and
normal conditions (1.0), has C = 1.0. A demand of 1.0 is then "one average adult's push". Recipes keep the
Phase 022 and 023 mechanisms; their cost goes through `cost_ratio` with the recipe floor of 1, so a worker
who meets the strength gate (C >= D) pays the declared cost and the committed numbers do not move.
"""
from __future__ import annotations

import math


def clamp(value, low, high):
    return max(low, min(high, value))


def capability(force, technique, fit, team, conditions):
    """C: the product of the five capability terms. Each term is non-negative; a zero term zeroes C."""
    terms = (force, technique, fit, team, conditions)
    if any(float(t) < 0.0 for t in terms):
        raise ValueError(f"capability terms must not be negative: {terms}")
    value = 1.0
    for term in terms:
        value *= float(term)
    return value


def technique_term(skill, floor):
    """The technique factor for an effective skill in [0, 1]: `floor` at no skill, 1.0 at full skill."""
    s = clamp(float(skill), 0.0, 1.0)
    return float(floor) + (1.0 - float(floor)) * s


def rho(c, d):
    """C / D. A demand of zero or less is met by any capability, so rho is infinite; a zero capability gives 0."""
    if float(d) <= 0.0:
        return math.inf
    return max(0.0, float(c)) / float(d)


def progress_rate(r, cap_rate, exponent):
    """min(cap_rate, rho^exponent): 0 with no capability, cap_rate at or above the reference."""
    if r <= 0.0:
        return 0.0
    if math.isinf(r):
        return float(cap_rate)
    return min(float(cap_rate), r ** float(exponent))


def cost_ratio(d, c, floor, cap):
    """clamp(D / C, floor, cap). A zero capability pays the cap."""
    if float(c) <= 0.0:
        return float(cap)
    return clamp(float(d) / float(c), float(floor), float(cap))


def intensity_applied(requested, max_intensity, ceiling=None):
    """The intensity the world applies: the requested level clamped to [0, min(max_intensity, ceiling)].

    Returns (applied, clamped). A negative request is taken as 0. The ceiling is the body's current limit
    (exhaustion, health), and it never exceeds max_intensity."""
    top = float(max_intensity) if ceiling is None else min(float(max_intensity), float(ceiling))
    top = max(0.0, top)
    want = float(requested)
    if math.isnan(want):
        want = 1.0
    applied = clamp(want, 0.0, top)
    return applied, applied != want


def overexertion(intensity, i_safe, m):
    """max(0, i - i_safe)^m: the strain of forcing past the safe level, paid whether or not the attempt works."""
    over = max(0.0, float(intensity) - float(i_safe))
    return over ** float(m)


def strain(cost_share, r):
    """Strain per tick: cost share x (1 - min(1, rho)). A capable worker strains little; a hopeless one strains
    by the whole of the share."""
    return float(cost_share) * (1.0 - min(1.0, max(0.0, r)))


def tool_wear(base, intensity, fit, mismatch, hardness_gap=0.0):
    """Wear on a tool in one attempt: base x intensity x (1 + mismatch x (1 - fit)) x (1 + hardness_gap).
    A tool that fits takes base x intensity; a tool that does not fit takes more, up to (1 + mismatch) times."""
    return (float(base) * float(intensity) * (1.0 + float(mismatch) * (1.0 - float(fit)))
            * (1.0 + max(0.0, float(hardness_gap))))


def noise_radius(base, intensity, material_noise):
    """Loudness of one attempt: base x intensity x the material's noise factor. A gentle tap is quiet. The
    loudness is the hearing radius in cells (Phase 028); the world clamps it to HEARING.max_loudness."""
    return float(base) * float(intensity) * float(material_noise)


def resolve_step(p):
    """One resolution step. `p` is a dict of plain numbers:

    force, technique, fit, team, conditions (the capability terms, intensity excluded);
    intensity (already applied, see intensity_applied); demand; cap_rate; exponent; base_cost; floor; effort_cap;
    k (intensity cost exponent); i_safe; m (overexertion exponent).

    Returns the step's outputs as a dict. Intensity multiplies the force term. Stamina cost uses the capability
    without intensity, so the cost ratio is the worker's ability to do the job at all, and i^k scales it on top.
    """
    i = float(p["intensity"])
    c0 = capability(p["force"], p["technique"], p["fit"], p["team"], p["conditions"])
    c = c0 * i
    r = rho(c, p["demand"])
    rate = progress_rate(r, p["cap_rate"], p["exponent"])
    share = cost_ratio(p["demand"], c0, p["floor"], p["effort_cap"])
    stamina = float(p["base_cost"]) * share * (i ** float(p["k"]))
    over = overexertion(i, p["i_safe"], p["m"])
    return {
        "capability": c,
        "progress": rate,
        "stamina": stamina,
        "cost_share": share,
        "strain": strain(share, r) + over,
        "overexertion": over,
    }


# ---------------------------------------------------------------- Phase 050b: pace, displacement, thresholds

def pace_clamp(requested, care_cap, haste_cap):
    """The pace a recipe job runs at: the requested intensity clamped to [1 / care_cap, haste_cap].

    Returns (applied, clamped). A slower job (below 1) takes at most care_cap times the reference time; a faster
    one (above 1) runs at most haste_cap times the reference rate. NaN is taken as the normal pace, 1.0."""
    low, high = 1.0 / float(care_cap), float(haste_cap)
    want = float(requested)
    if math.isnan(want):
        want = 1.0
    applied = clamp(want, low, high)
    return applied, applied != want


def pace_defect(pace, haste_penalty):
    """How much a batch's defect grows at a pace. At the reference (1.0) it is 1. Below 1 it falls in step with
    the pace (careful work leaves fewer defects). Above 1 each unit of haste adds haste_penalty to it."""
    p = float(pace)
    if p <= 1.0:
        return max(0.0, p)
    return 1.0 + float(haste_penalty) * (p - 1.0)


def pace_quality(quality, pace, haste_penalty):
    """A batch's quality at a pace: the reference quality with its defect share (1 - quality) scaled by
    pace_defect. At pace 1 the quality is unchanged, so committed recipe numbers do not move."""
    if float(pace) == 1.0:
        return float(quality)          # the reference pace leaves the quality exactly as it was
    q = clamp(float(quality), 0.0, 1.0)
    return clamp(1.0 - (1.0 - q) * pace_defect(pace, haste_penalty), 0.0, 1.0)


def pace_yield(pace, haste_yield_loss):
    """The share of a batch's output that a pace keeps. Haste above the reference loses haste_yield_loss of the
    output per unit of haste (waste from rushing); careful work keeps all of it."""
    p = float(pace)
    return clamp(1.0 - float(haste_yield_loss) * max(0.0, p - 1.0), 0.0, 1.0)


def ruined(quality_after, quality_before, ruin_below):
    """A batch is spoiled when the pace pushes its quality below ruin_below. A batch that was already below the line
    at the reference pace is not spoiled by the pace, so this only bites on work done faster than normal."""
    return float(quality_after) < float(ruin_below) and float(quality_after) < float(quality_before)


def push_cells(surplus, cells_per_surplus, max_cells):
    """Cells a load moves in one attempt: floor(surplus x cells_per_surplus), at most max_cells. A surplus of zero
    or less moves nothing."""
    s = float(surplus)
    if s <= 0.0:
        return 0
    return int(min(int(max_cells), math.floor(s * float(cells_per_surplus))))


def friction_demand(mass, mass_unit, friction):
    """Demand of a ground displacement: the load's mass in units of the reference push (mass_unit kg, the average
    adult's push at normal intensity), times the ground's friction (terrain move time, grass 1.0)."""
    return max(0.0, float(mass)) / float(mass_unit) * max(0.0, float(friction))
