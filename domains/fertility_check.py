"""Phase 044: the arithmetic behind the births self-test. Pure functions over the BIRTHS table.

No world is built here. A woman in a recorded union conceives at her age band's rate (a per-year
rate, turned into a monthly chance). A pregnancy lasts gestation_days and is followed by a
postpartum block, during which she does not conceive. `completed_family` runs this as an exact
monthly Markov chain, so the expected number of births is a number, not a sample.
"""
from __future__ import annotations

import math


def rate_at(bands, age):
    """The per-year conception rate of the band that holds `age` (0 outside every band)."""
    for band in bands:
        if float(band["age_min"]) <= age < float(band["age_max"]) + 1.0:
            return float(band["rate"])
    return 0.0


def completed_family(bands, *, gestation_days, postpartum_days, entry_age, end_age, days_per_year):
    """Expected births to a woman who enters a union at `entry_age` and stays in it until `end_age`.

    States: free (may conceive), pregnant (k months to birth), and postpartum (k months of block).
    A month is days_per_year / 12 days. Ages advance by one month per step."""
    month_days = float(days_per_year) / 12.0
    preg_months = max(1, int(round(float(gestation_days) / month_days)))
    post_months = max(1, int(round(float(postpartum_days) / month_days)))
    states = {"free": 1.0}
    births = 0.0
    age = float(entry_age)
    steps = int(round((float(end_age) - float(entry_age)) * 12.0))
    for _ in range(steps):
        p = 1.0 - math.exp(-rate_at(bands, age) / 12.0)
        nxt: dict = {}

        def put(key, mass):
            if mass > 0.0:
                nxt[key] = nxt.get(key, 0.0) + mass

        for key, mass in states.items():
            if key == "free":
                put("free", mass * (1.0 - p))
                put(("pregnant", preg_months), mass * p)
            elif key[0] == "pregnant":
                if key[1] == 1:
                    births += mass
                    put(("postpartum", post_months), mass)
                else:
                    put(("pregnant", key[1] - 1), mass)
            else:
                if key[1] == 1:
                    put("free", mass)
                else:
                    put(("postpartum", key[1] - 1), mass)
        states = nxt
        age += 1.0 / 12.0
    return births


def births_per_union_year(bands, *, age, days_per_year, gestation_days, postpartum_days):
    """The long-run births a union woman at `age` has in a year, with the same pregnancy and block as
    completed_family (a renewal rate: the conception rate divided by the cycle it starts)."""
    rate = rate_at(bands, age)
    cycle_years = (float(gestation_days) + float(postpartum_days)) / float(days_per_year)
    return rate / (1.0 + rate * cycle_years)
