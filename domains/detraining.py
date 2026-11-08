"""Phase 046: pure arithmetic for detraining and ageing of the body.

No world state here. worlds/detraining.py applies these functions to residents, and the self-test in
domains/detraining_check.py calls them on the pack's tables to report what the figures do.

Detraining acts on the TRAINED part of a stat (str_train, sta_train: Phase 032), never on the base. Ageing acts on
the base (str_base, sta_base) and only above BODY_AGE.peak_until, which is at or past the adult age, so Phase 045's
growth (below the adult age) and this ageing never write the same base for the same age.
"""
from __future__ import annotations

ZERO = 1e-9   # a trained part below this is taken as gone (exactly 0), so the decay ends in a finite number of days


def detrained(trained: float, idle_days: float, grace_days: float, rate: float) -> float:
    """The trained part after one day with no effort of that kind.

    While the resident has been idle for `grace_days` whole days or fewer, the trained part is held. Past the grace,
    it falls by `rate` of itself each day. It never goes below 0, so effective strength never falls below the base.
    `idle_days` may be infinite (no recorded effort of this kind)."""
    if float(idle_days) <= float(grace_days):
        return float(trained)
    value = float(trained) * (1.0 - float(rate))
    return value if value > ZERO else 0.0


def trained_share_left(idle_days: float, grace_days: float, rate: float) -> float:
    """The share of the trained part left after `idle_days` idle days, from the same rule as `detrained`
    applied day by day: (1 - rate) ** max(0, idle_days - grace_days). Used by the self-test's report lines."""
    return float((1.0 - float(rate)) ** max(0.0, float(idle_days) - float(grace_days)))


def aged_base(peak_base: float, age: float, peak_until: float, decline_per_year: float, floor: float) -> float:
    """A body base (strength or stamina) at `age`.

    `peak_base` is the base the resident had when ageing first applied (founders draw their own base, so it is not
    the pack default). It holds up to `peak_until` years. After that it falls by `decline_per_year` of the peak base
    for each year past it, and never below `floor` of the peak base."""
    years_past = float(age) - float(peak_until)
    if years_past <= 0.0:
        return float(peak_base)
    return float(peak_base) * max(float(floor), 1.0 - float(decline_per_year) * years_past)
