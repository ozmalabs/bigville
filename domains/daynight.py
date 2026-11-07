"""daynight.py -- the sky and the light (Phase 042): pure functions of the pack's numbers.

Nothing here reads or writes the world. `worlds/daynight.py` calls these with the clock, the weather
and the DAYNIGHT table, and the world's own state (lamps, residents, buildings) decides what anybody sees.

Model (seed `seeds/bigville_daynight.json`, rules dn_sky and dn_perceive):
* Day length is the astronomical one for `latitude_deg` and the day of the year. The sun's declination
  is Cooper's (1969) formula, delta = 23.45 deg x sin(360/365 x (284 + n)); the day length follows from
  cos(H0) = -tan(lat) x tan(delta), with H0 the hour angle at sunrise (day length = 2 H0 / 15 hours).
  The equation of time is left out (APPROX), so sunrise and sunset are centred on `noon_hour`.
* The calendar's year is 360 days (TIME.days_per_year), so the day of the year n is the calendar's
  year day shifted so the calendar's summer midpoint (`summer_solstice_day`, APPROX) falls on the June
  solstice, day 172 of a non-leap year.
* `moon_illum` is the illuminated fraction (1 - cos(2 pi age / P)) / 2 over the synodic month P, with
  P = 29.530588853 sim-days, the mean synodic month (Meeus, Astronomical Algorithms, ch. 49). Ages are in
  the simulation's own days, as the seed says.
* `light_level` is moonlight x (1 - cloud) at night and sun_light x (1 - cloud) by day (the seed's rule).
  `cloud` is per weather type (world/weather.json).
"""
from __future__ import annotations

import math

# Cooper (1969) declination and the June solstice's day of the year (172, non-leap year).
JUNE_SOLSTICE_DOY = 172


def _clock_day(clock, ticks_per_day):
    return float(clock) / float(ticks_per_day)


def year_day(clock, time):
    """The calendar's day within the year (0 to days_per_year - 1), from the clock."""
    return int(float(clock) // float(time["ticks_per_day"])) % int(time["days_per_year"])


def hour_of_day(clock, time):
    """The clock's hour of day (0 to 24), as world.calendar()['hour'] reads it."""
    tpd = float(time["ticks_per_day"])
    hours = float(time["hours_per_day"])
    return (float(time["start_hour"]) + (float(clock) % tpd) * (hours / tpd)) % hours


def day_of_year(year_day_value, dn):
    """The solar day of the year n (1 to 365) for a calendar year day."""
    return float(year_day_value) - float(dn["summer_solstice_day"]) + JUNE_SOLSTICE_DOY


def declination_deg(n):
    """The sun's declination in degrees on day n (Cooper 1969)."""
    return 23.45 * math.sin(math.radians(360.0 / 365.0 * (284.0 + float(n))))


def day_length_hours(latitude_deg, declination):
    """The hours of daylight at a latitude with the sun at `declination` degrees. 0 in polar night, 24 in midnight sun."""
    x = -math.tan(math.radians(float(latitude_deg))) * math.tan(math.radians(float(declination)))
    if x >= 1.0:
        return 0.0
    if x <= -1.0:
        return 24.0
    return 2.0 * math.degrees(math.acos(x)) / 15.0


def sunrise_sunset(year_day_value, dn):
    """(sunrise, sunset, daylength) in clock hours for a calendar year day."""
    n = day_of_year(year_day_value, dn)
    length = day_length_hours(dn["latitude_deg"], declination_deg(n))
    noon = float(dn["noon_hour"])
    return noon - length / 2.0, noon + length / 2.0, length


def moon_illum(clock, time, dn):
    """The illuminated fraction of the moon, 0 (new) to 1 (full), at the clock."""
    days = _clock_day(clock, time["ticks_per_day"])
    period = float(dn["synodic_month_days"])
    age = (days - float(dn["new_moon_day"])) % period
    return (1.0 - math.cos(2.0 * math.pi * age / period)) / 2.0


def sky(clock, weather, weather_table, time, dn):
    """The sky at the clock: sunrise, sunset, is_night, moon_illum, cloud and light_level (seed dn_sky)."""
    yd = year_day(clock, time)
    sunrise, sunset, length = sunrise_sunset(yd, dn)
    hour = hour_of_day(clock, time)
    is_night = hour < sunrise or hour > sunset
    illum = moon_illum(clock, time, dn)
    cloud = float(weather_table.get(weather, {}).get("cloud", 0.0))
    if is_night:
        light = illum * (1.0 - cloud)
    else:
        light = float(dn["sun_light"]) * (1.0 - cloud)
    return {"hour": hour, "sunrise": sunrise, "sunset": sunset, "daylength": length, "is_night": bool(is_night),
            "moon_illum": illum, "cloud": cloud, "light_level": light}


def sees_dark_level(light_level, see_threshold):
    """True when a light level is below what a resident needs to see (seed dn_perceive)."""
    return float(light_level) < float(see_threshold)


def visibility_factor(sees_dark, dark_work_fit):
    """The share of normal progress a worker makes on the fitness path: 1.0 with light, dark_work_fit in the dark."""
    return float(dark_work_fit) if sees_dark else 1.0


def mean_night_fraction(time, dn, samples=None):
    """The average share of a day that is night over the calendar year (a fixed sample of the 360 days)."""
    days = int(time["days_per_year"]) if samples is None else int(samples)
    total = 0.0
    for yd in range(days):
        sunrise, sunset, _ = sunrise_sunset(yd, dn)
        total += (24.0 - (sunset - sunrise)) / 24.0
    return total / float(days)


def lamp_oil_per_period(lamp_count, burn_per_tick, time, dn):
    """The oil a period's lit lamps burn, on average over the year: lamps x burn per tick x night ticks per period."""
    night_ticks = mean_night_fraction(time, dn) * float(time["ticks_per_period"])
    return float(lamp_count) * float(burn_per_tick) * night_ticks
