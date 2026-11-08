"""detraining_check.py -- self-test checks for the DETRAIN and BODY_AGE tables (Phase 046).

    check_detraining(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It reads the pack with
domains/pack.load_pack and checks:
- DETRAIN has a strength and a stamina entry, each with grace_days a whole number >= 0 and rate in (0, 1]; stamina
  has the shorter grace and the larger rate (strength is lost more slowly than stamina).
- BODY_AGE has peak_until at or past the adult age (LIFE_STAGES.adult.age_min), so ageing never writes a base that
  growth (Phase 045) writes; each stat has decline_per_year >= 0 and a floor in (0, 1].
- The figures the tables imply, as info lines: the share of a trained part left after a year idle, the age at
  which each base reaches its floor, and a working adult's effective band (base to base x (1 + TRAIN_HEADROOM)).
"""
from __future__ import annotations

from domains.detraining import aged_base, trained_share_left
from domains.pack import load_pack

KINDS = ("strength", "stamina")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_detraining(pack_name, errors, warnings, info):
    tables = load_pack(pack_name)
    detrain = tables["DETRAIN"]
    age = tables["BODY_AGE"]
    adult_min = float(tables["LIFE_STAGES"]["adult"]["age_min"])
    headroom = float(tables["TRAIN_HEADROOM"])

    if not isinstance(detrain.get("enabled"), bool):
        errors.append(f"DETRAIN[enabled]: a boolean, not {detrain.get('enabled')!r}")
    for kind in KINDS:
        if kind not in detrain:
            errors.append(f"DETRAIN[{kind}]: missing")
            continue
        row = detrain[kind]
        if not _whole(row.get("grace_days")) or row["grace_days"] < 0:
            errors.append(f"DETRAIN[{kind}][grace_days]: a whole number of days >= 0, not {row.get('grace_days')!r}")
        if not _number(row.get("rate")) or not 0.0 < float(row["rate"]) <= 1.0:
            errors.append(f"DETRAIN[{kind}][rate]: a fraction in (0, 1], not {row.get('rate')!r}")
    if not errors and all(k in detrain for k in KINDS):
        if detrain["stamina"]["grace_days"] > detrain["strength"]["grace_days"]:
            errors.append("DETRAIN: stamina's grace must not be longer than strength's (stamina is lost faster)")
        if float(detrain["stamina"]["rate"]) < float(detrain["strength"]["rate"]):
            errors.append("DETRAIN: stamina's rate must not be below strength's (stamina is lost faster)")

    peak = age.get("peak_until")
    if not _number(peak) or float(peak) < adult_min:
        errors.append(f"BODY_AGE[peak_until]: a number at or past the adult age ({adult_min:g}), not {peak!r}")
    for kind in KINDS:
        if kind not in age:
            errors.append(f"BODY_AGE[{kind}]: missing")
            continue
        row = age[kind]
        if not _number(row.get("decline_per_year")) or float(row["decline_per_year"]) < 0.0:
            errors.append(f"BODY_AGE[{kind}][decline_per_year]: a number >= 0, not {row.get('decline_per_year')!r}")
        if not _number(row.get("floor")) or not 0.0 < float(row["floor"]) <= 1.0:
            errors.append(f"BODY_AGE[{kind}][floor]: a fraction in (0, 1], not {row.get('floor')!r}")
    if errors or not _number(peak):
        return

    info.append(f"DETRAIN: the switch DETRAIN.enabled is {'on' if detrain.get('enabled') is True else 'off'} (HEAD and "
                "the default run are unchanged while it is off)")
    for kind in KINDS:
        row = detrain[kind]
        left = trained_share_left(365.0, row["grace_days"], row["rate"])
        info.append(f"DETRAIN: a {kind} trained part is held {row['grace_days']} days idle, then falls {row['rate']:g} "
                    f"a day; after a year idle {left:.3f} of it is left (APPROX)")
    for kind in KINDS:
        row = age[kind]
        floor = float(row["floor"])
        rate = float(row["decline_per_year"])
        reached = (float(peak) + (1.0 - floor) / rate) if rate > 0.0 else float("inf")
        at_65 = aged_base(1.0, 65.0, float(peak), rate, floor)
        info.append(f"BODY_AGE: the {kind} base holds to age {float(peak):g}, is {at_65:.3f} of peak at 65, and reaches "
                    f"its floor {floor:g} at age {reached:.0f} (APPROX)")
    info.append(f"TRAINING band: a resident who keeps working holds a trained part up to TRAIN_HEADROOM {headroom:g}, so "
                f"effective strength stays between base and base x {1.0 + headroom:g} (analytic; the long-run town "
                "mean is not a static check)")
