"""numeracy.py -- how a count or a price is put into words for a resident's numeracy tier (Phase 064).

    level(game, actor, mode)            the numeracy level: the world's `capability` attribute (reckoning and
                                        comprehension), or the full level when the faculty is 'represented'
    tier_row(level, pack)               the NUMERACY_TIERS row the level falls in
    spell(n, pack)                      a whole number from 0 to 999 in words (no digit)
    quantity_words(n, row, pack, unit)  a count in the tier's words: 'two loaves', 'a few loaves', 'many loaves'
    price_words(price, unit, row, pack) a price in the tier's words: in the mark's unit when the tier says 'units'
                                        ('one loaf'), else as a figure in coins ('two coins')

The tiers and the units are data (world/literacy.json). The level thresholds are authored (APPROX).
"""
from __future__ import annotations

import math

from domains.pack import load_pack

REPRESENTED_LEVEL = 1.0
MAX_SPELLED = 999


def table(pack):
    """The NUMERACY_TIERS rows, lowest level first."""
    return sorted(load_pack(pack)["NUMERACY_TIERS"], key=lambda row: float(row["min_level"]))


def units(pack):
    """The NUMERACY_UNITS table: unit name to {coin, singular, plural}."""
    return load_pack(pack)["NUMERACY_UNITS"]


def level(game, actor, mode):
    """The numeracy level of a resident. A 'represented' faculty is the full level; otherwise the world's capability."""
    if mode == "represented":
        return REPRESENTED_LEVEL
    world = game.world
    return float(world.eng.node(world._actors[actor])["attrs"].get("capability", 0.0))


def tier_row(lvl, pack):
    """The highest row whose minimum level the level meets (the first row when it meets none)."""
    rows = table(pack)
    chosen = rows[0]
    for row in rows:
        if float(lvl) >= float(row["min_level"]):
            chosen = row
    return chosen


def _round(x):
    return int(math.floor(float(x) + 0.5))


def spell(n, pack):
    """A whole number from 0 to 999 in words, from the NUMERAL_WORDS table: 42 is 'forty-two'."""
    n = int(n)
    if n < 0 or n > MAX_SPELLED:
        raise ValueError(f"spell takes a whole number from 0 to {MAX_SPELLED}, not {n}")
    words = load_pack(pack)["NUMERAL_WORDS"]
    small = words["words"]
    if n <= 20:
        return small[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        tail = f"-{small[ones]}" if ones else ""
        return f"{words['tens'][tens]}{tail}"
    hundreds, rest = divmod(n, 100)
    if rest == 0:
        return f"{small[hundreds]} {words['hundred']}"
    return f"{small[hundreds]} {words['hundred']} {words['and']} {spell(rest, pack)}"


def quantity_words(n, row, pack, unit):
    """A count in the tier's words. Zero is 'none'. Up to exact_max it is spelled with the unit; up to few_max it is
    'a few' and above that 'many', each with the plural of the unit."""
    n = int(n)
    spec = units(pack)[unit]
    if n <= 0:
        return "none"
    if n <= int(row["exact_max"]):
        noun = spec["singular"] if n == 1 else spec["plural"]
        return f"{spell(n, pack)} {noun}"
    if n <= int(row["few_max"]):
        return f"a few {spec['plural']}"
    return f"many {spec['plural']}"


def price_words(price, unit, row, pack):
    """A price in the tier's words. A 'units' tier counts the price in the mark's unit (a loaf is worth its coin value);
    a 'figure' tier says the price in coins."""
    if row["prices"] == "figure":
        return quantity_words(_round(price), row, pack, "coin")
    spec = units(pack)[unit]
    return quantity_words(_round(float(price) / float(spec["coin"])), row, pack, unit)
