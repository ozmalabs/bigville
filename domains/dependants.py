"""Phase 045: pure arithmetic for dependants (infants, children and youths).

No world state here. worlds/dependants.py applies these functions to residents, and the self-test in
domains/bigville_entities.py calls them on the pack's table to report the growth curve.
"""
from __future__ import annotations


def growth_fraction(age: float, start: float, adult_age: float, exponent: float = 1.0) -> float:
    """Body strength or stamina at `age` as a fraction of the adult value.

    It starts at `start` at birth, rises to 1.0 at `adult_age`, and holds at 1.0 after it. The rise is
    start + (1 - start) x (age / adult_age) ** exponent, so exponent 1 is linear."""
    if adult_age <= 0.0:
        return 1.0
    share = min(1.0, max(0.0, float(age)) / float(adult_age))
    return float(start) + (1.0 - float(start)) * share ** float(exponent)


def neglect_harm(care_need: float, days_unattended: float, after_days: float, harm_per_day: float) -> float:
    """Acute harm (before HEALTH.fragility) for one day of neglect: zero until `days_unattended` passes
    `after_days`, then harm_per_day times the stage's care need."""
    if float(days_unattended) <= float(after_days):
        return 0.0
    return max(0.0, float(harm_per_day)) * max(0.0, float(care_need))
