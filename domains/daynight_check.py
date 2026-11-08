"""daynight_check.py -- self-test checks for the day, night and lamps tables (Phase 042).

Called from bigville_entities.check_consistency with the entity tables it needs. It checks the DAYNIGHT
numbers and the lamps against the square, the cloud of every weather type, the lamplighter's job and labour
task, the lamp oil and candle items, and two facts the seed relies on: a summer day is longer than a winter
one at the pack's latitude, and a clear full-moon night is brighter than the seeing threshold while a new-moon
or overcast night is not.
"""
from __future__ import annotations


from domains import daynight as D


def check(errors, warnings, info, *, daynight, lamps, weather, jobs, labour_tasks, items, major_actions,
          founding_map, time):
    where = "DAYNIGHT"
    dn = daynight
    if not isinstance(dn.get("enabled"), bool):
        errors.append(f"{where}.enabled: must be true or false")
    lat = float(dn["latitude_deg"])
    if not -90.0 <= lat <= 90.0:
        errors.append(f"{where}.latitude_deg: must be in [-90, 90], not {lat}")
    if not 0 <= int(dn["summer_solstice_day"]) < int(time["days_per_year"]):
        errors.append(f"{where}.summer_solstice_day: must be a calendar year day")
    if float(dn["synodic_month_days"]) <= 0.0:
        errors.append(f"{where}.synodic_month_days: must be positive")
    if not 0.0 < float(dn["noon_hour"]) < float(time["hours_per_day"]):
        errors.append(f"{where}.noon_hour: must be inside the day")
    if float(dn["sun_light"]) <= 0.0:
        errors.append(f"{where}.sun_light: must be positive")
    if not 0.0 < float(dn["see_threshold"]) < 1.0:
        errors.append(f"{where}.see_threshold: must be in (0, 1)")
    if int(dn["dark_sight_range"]) < 1:
        errors.append(f"{where}.dark_sight_range: must be at least 1 cell")
    if not 0.0 < float(dn["dark_work_fit"]) <= 1.0:
        errors.append(f"{where}.dark_work_fit: must be in (0, 1]")
    if float(dn["travel_dark_factor"]) <= 0.0:
        errors.append(f"{where}.travel_dark_factor: must be positive (1.0 is the seed)")
    if int(dn["lamp_reach"]) < 0:
        errors.append(f"{where}.lamp_reach: must be 0 or more cells")
    for key in ("lamp_fuel_capacity", "lamp_burn_per_tick", "candle_fuel", "candle_burn_per_tick"):
        if float(dn[key]) <= 0.0:
            errors.append(f"{where}.{key}: must be positive")
    if float(dn["starting_oil"]) < 0.0:
        errors.append(f"{where}.starting_oil: must be 0 or more")
    if int(dn["lamplighters"]) < 0:
        errors.append(f"{where}.lamplighters: must be 0 or more")
    # The lamplighter's pole reach, station and dusk lead (Phase 042b; the lead is also the duty's, DUTIES, Phase 042c).
    if int(dn["lamp_pole_reach"]) < 1:
        errors.append(f"{where}.lamp_pole_reach: must be at least 1 cell")
    if int(dn["lamplighter_station_reach"]) < 0:
        errors.append(f"{where}.lamplighter_station_reach: must be 0 or more cells")
    lead = float(dn["lamplighter_dusk_lead_hours"])
    if not 0.0 < lead < float(time["hours_per_day"]) / 2.0:
        errors.append(f"{where}.lamplighter_dusk_lead_hours: must be positive and under half a day")
    # A pack with day and night switched off may leave the cross-references empty (a minimal test pack has no
    # oil, candle or lamplighter). Switched on, every reference must resolve.
    enabled = bool(dn.get("enabled"))
    if enabled and not dn["oil_item"]:
        errors.append(f"{where}.oil_item: needed when day and night is on (the lamps burn it)")
    if dn["oil_item"] and dn["oil_item"] not in items:
        errors.append(f"{where}.oil_item: '{dn['oil_item']}' is not an item")
    for kind in dn["carried_lights"]:
        if kind not in items:
            errors.append(f"{where}.carried_lights: '{kind}' is not an item")
    job = dn["lamplighter_job"]
    if job and job not in jobs:
        errors.append(f"{where}.lamplighter_job: '{job}' is not a JOBS entry")
    if job and "lamplighting" not in labour_tasks:
        errors.append("LABOUR_TASKS: no 'lamplighting' task for the lamplighter")
    if enabled and not job:
        errors.append(f"{where}.lamplighter_job: needed when day and night is on")
    if not job and int(dn["lamplighters"]) > 0:
        errors.append(f"{where}.lamplighters: {dn['lamplighters']} lamplighters but no lamplighter_job")
    # Lamps: unique names, offsets inside the square (the founding square's half-extent).
    square = founding_map.get("square", {}) if founding_map else {}
    names = [lamp["name"] for lamp in lamps]
    for name in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"DAYNIGHT_LAMPS[{name}]: the name is used more than once")
    if not lamps:
        if enabled:
            warnings.append("DAYNIGHT_LAMPS: no lamps, so the square is dark when day and night are on")
        else:
            info.append("DAYNIGHT_LAMPS: none in this pack (day and night is off)")
    for lamp in lamps:
        ox, oy = lamp["offset"]
        if not (isinstance(ox, int) and isinstance(oy, int)):
            errors.append(f"DAYNIGHT_LAMPS[{lamp['name']}].offset: must be two whole cells")
            continue
        if square:
            half_w, half_h = int(square["w"]) // 2, int(square["h"]) // 2
            if abs(ox) > half_w or abs(oy) > half_h:
                errors.append(f"DAYNIGHT_LAMPS[{lamp['name']}]: offset {[ox, oy]} lies outside the square")
    # Pole reach (Phase 042b): from the square's centre every lamp is in reach. The station is the market store's
    # cell, which FOUNDING_MAP does not carry, so the self-test cannot check the station against the lamps.
    if square and lamps and enabled:
        far = max(max(abs(int(lamp["offset"][0])), abs(int(lamp["offset"][1]))) for lamp in lamps)
        if far > int(dn["lamp_pole_reach"]):
            warnings.append(f"{where}.lamp_pole_reach: {dn['lamp_pole_reach']} cells does not reach every lamp "
                            f"from the square's centre (furthest is {far})")
    # Weather: every type has a cloud in [0, 1].
    for name, spec in weather.items():
        cloud = spec.get("cloud")
        if cloud is None or not 0.0 <= float(cloud) <= 1.0:
            errors.append(f"WEATHER[{name}].cloud: needs a cloud in [0, 1] for day and night")
    for action in ("light", "douse"):
        if action not in major_actions or not str(major_actions[action].get("description", "")).strip():
            errors.append(f"MAJOR_ACTIONS: needs {action!r} with a description (Phase 042)")
    # The seed's facts, at the pack's latitude: a summer day is longer than a winter one, and the light rule holds.
    summer = dn["summer_solstice_day"]
    winter = (int(summer) + int(time["days_per_year"]) // 2) % int(time["days_per_year"])
    _, _, summer_len = D.sunrise_sunset(summer, dn)
    _, _, winter_len = D.sunrise_sunset(winter, dn)
    if not summer_len > winter_len:
        errors.append(f"{where}: a summer day ({summer_len:.2f} h) is not longer than a winter day "
                      f"({winter_len:.2f} h) at latitude {lat}")
    info.append(f"{where}: daylight {summer_len:.2f} h at midsummer, {winter_len:.2f} h at midwinter "
                f"(latitude {lat})")
    threshold = float(dn["see_threshold"])
    if D.sees_dark_level(1.0, threshold):
        errors.append(f"{where}: a clear full-moon night (light 1.0) is not bright enough to see by at "
                      f"see_threshold {threshold}")
    if not D.sees_dark_level(0.0, threshold):
        errors.append(f"{where}: a new-moon night (light 0.0) must be dark at see_threshold {threshold}")
