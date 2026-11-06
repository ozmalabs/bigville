"""lexicon.py -- the words for numbers and statuses, read from a data pack (Phase 051).

Every consumer that turns a world number into words (the agent view, the LLM prompt, the character
sheet, the terminal interface) calls this module, so they share one set of words. The words live in
the pack: `LEXICON_QUANTITIES`, `INTENSITY_WORDS`, `AMOUNT_WORDS`, `VERB_ALIASES` and `LEXICON_PAYLOAD`
in `world/lexicon.json`. A different pack gives different words with no code change.

    describe("energy", 12.0)                       -> {"label": "exhausted", "phrase": "exhausted"}
    describe("energy", 12.0, perspective="other")  -> {"label": "exhausted", "phrase": "looks exhausted"}
    describe("hunger", 0.0, perspective="other")   -> {"label": "well_fed", "phrase": "looks well fed"}
    describe("stamina", 1.0, perspective="other")  -> None   (a capacity no observer can see)
    describe("skill", 0.5, what="smithing")        -> {"label": "competent", "phrase": "competent at smithing"}
    value_for("energy", "worn_out")                -> a number inside that band (energy 15 to 35)
    intensity_value("hard")                        -> the pack's value for "hard"
    resolve_verb("bash")                           -> "smash"

Rules: lookup is by thresholds, so it is monotone and total. A numeric value outside the quantity's
range is clamped to the nearest end. A status value that is not a known key gets the 'unknown'
phrase. `describe` never returns a number in its words. A perspective that cannot see the quantity
returns None. The self-test (domains/lexicon_check.py) checks every table.
"""
from __future__ import annotations

import bisect
import math

from domains.pack import load_pack

DEFAULT_PACK = "bigville"
PERSPECTIVES = ("self", "other")
FALLBACK = "unknown"
_TEMPLATE = "{what}"

_INDEX: dict = {}


def _norm(word):
    """Case and spacing do not matter in a reverse word: 'Hard ' and 'hard' are the same word."""
    return " ".join(str(word).strip().lower().split())


def _check_perspective(perspective):
    if perspective not in PERSPECTIVES:
        raise ValueError(f"perspective must be one of {PERSPECTIVES}, not {perspective!r}")


def _build_numeric(name, spec):
    lo, hi = (float(x) for x in spec["range"])
    perspectives = {}
    for persp in PERSPECTIVES:
        rows = spec.get(persp)
        if rows is None:
            continue
        bands = []
        for i, row in enumerate(rows):
            top = float(rows[i + 1]["min"]) if i + 1 < len(rows) else hi
            bands.append({"min": float(row["min"]), "max": top,
                          "label": row["label"], "phrase": row["phrase"]})
        perspectives[persp] = {"bands": bands, "mins": [b["min"] for b in bands]}
    return {"name": name, "kind": "numeric", "lo": lo, "hi": hi, "perspectives": perspectives,
            "published": bool(spec.get("published", True))}


def _build_status(name, spec):
    perspectives = {persp: dict(spec[persp]) for persp in PERSPECTIVES if persp in spec}
    return {"name": name, "kind": "status", "keys": set(spec["self"]), "perspectives": perspectives,
            "published": bool(spec.get("published", True))}


def _index(pack_name):
    if pack_name in _INDEX:
        return _INDEX[pack_name]
    pack = load_pack(pack_name)
    raw = pack["LEXICON_QUANTITIES"]
    quantities = {}
    for name, spec in raw.items():
        if name.startswith("_") or "alias" in spec:
            continue
        if spec.get("kind") == "status":
            quantities[name] = _build_status(name, spec)
        else:
            quantities[name] = _build_numeric(name, spec)
    for name, spec in raw.items():
        if "alias" in spec:
            target = spec["alias"]
            if target not in quantities:
                raise KeyError(f"pack '{pack_name}': quantity '{name}' aliases unknown '{target}'")
            quantities[name] = quantities[target]
    index = {
        "quantities": quantities,
        "intensity": {_norm(k): float(v) for k, v in pack["INTENSITY_WORDS"].items()},
        "amount": {_norm(k): float(v) for k, v in pack["AMOUNT_WORDS"].items()},
        "verbs": {_norm(k): str(v) for k, v in pack["VERB_ALIASES"].items()},
    }
    _INDEX[pack_name] = index
    return index


def _quantity(quantity, pack):
    quantities = _index(pack)["quantities"]
    if quantity not in quantities:
        raise KeyError(f"pack '{pack}' has no lexicon quantity '{quantity}'")
    return quantities[quantity]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"a numeric quantity needs a number, not {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"a numeric quantity needs a finite number, not {value!r}")
    return value


def _fill(phrase, what):
    if _TEMPLATE not in phrase:
        return phrase
    if not what:
        raise ValueError(f"the phrase {phrase!r} needs what=... (the skill or trade named)")
    return phrase.replace(_TEMPLATE, str(what))


def _numeric_band(q, value, perspective):
    table = q["perspectives"].get(perspective)
    if table is None:
        return None
    v = min(max(_number(value), q["lo"]), q["hi"])
    i = max(bisect.bisect_right(table["mins"], v) - 1, 0)
    return table["bands"][i]


def _status_band(q, key, perspective):
    table = q["perspectives"].get(perspective)
    if table is None:
        return None
    if key in q["keys"]:
        # A known key with no phrase for this perspective is hidden from it.
        return {"label": key, "phrase": table[key]} if key in table else None
    if FALLBACK in table:
        return {"label": FALLBACK, "phrase": table[FALLBACK]}
    return None


def describe(quantity, value, perspective="self", pack=DEFAULT_PACK, what=None):
    """The words for `value` of `quantity`, as `perspective` puts them.

    Returns {"label": ..., "phrase": ...}, or None when that perspective cannot see the quantity.
    Numeric quantities take a number; status quantities take a key (an unknown key reads 'unknown').
    `what` names the skill or trade for a phrase that has {what} in it.
    """
    _check_perspective(perspective)
    q = _quantity(quantity, pack)
    if q["kind"] == "status":
        if not isinstance(value, str):
            raise TypeError(f"the status quantity '{quantity}' takes a key string, not {value!r}")
        band = _status_band(q, value, perspective)
    else:
        band = _numeric_band(q, value, perspective)
    if band is None:
        return None
    return {"label": band["label"], "phrase": _fill(band["phrase"], what)}


def value_for(quantity, label, perspective="self", pack=DEFAULT_PACK):
    """A representative value for a band label: the middle of a numeric band, or the key of a status.

    The middle of a band lies inside that band, so describe(quantity, value_for(quantity, label))
    returns the same label. Raises KeyError when the perspective has no band with that label.
    """
    _check_perspective(perspective)
    q = _quantity(quantity, pack)
    table = q["perspectives"].get(perspective)
    if table is None:
        raise KeyError(f"'{quantity}' has no '{perspective}' words")
    if q["kind"] == "status":
        if label not in table:
            raise KeyError(f"'{quantity}' ({perspective}) has no status '{label}'")
        return label
    for band in table["bands"]:
        if band["label"] == label:
            return (band["min"] + band["max"]) / 2.0
    raise KeyError(f"'{quantity}' ({perspective}) has no band '{label}'")


def quantities(pack=DEFAULT_PACK):
    """The names of every lexicon quantity in the pack, sorted (aliases included)."""
    return sorted(_index(pack)["quantities"])


def bands(quantity, perspective="self", pack=DEFAULT_PACK):
    """The bands of a quantity for one perspective, as a list of plain dicts (empty when the perspective
    cannot see it). Numeric bands carry min and max; status bands carry label and phrase only."""
    _check_perspective(perspective)
    q = _quantity(quantity, pack)
    table = q["perspectives"].get(perspective)
    if table is None:
        return []
    if q["kind"] == "status":
        return [{"label": k, "phrase": v} for k, v in table.items()]
    return [dict(b) for b in table["bands"]]


def _reverse(word, table, label):
    if isinstance(word, bool):
        raise TypeError(f"{label} takes a word or a number, not {word!r}")
    if isinstance(word, (int, float)):
        return float(word)
    text = _norm(word)
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        if not math.isfinite(number):
            raise ValueError(f"{label} must be a finite number, not {word!r}")
        return number
    if text in table:
        return table[text]
    raise ValueError(f"unknown {label} word {word!r}")


def intensity_value(word_or_number, pack=DEFAULT_PACK):
    """The intensity a word stands for (1.0 is normal). A number passes through unchanged."""
    return _reverse(word_or_number, _index(pack)["intensity"], "intensity")


def amount_value(word_or_number, pack=DEFAULT_PACK):
    """The count an amount word stands for ('a few' is 3). A number passes through unchanged."""
    return _reverse(word_or_number, _index(pack)["amount"], "amount")


def resolve_verb(word, pack=DEFAULT_PACK):
    """The canonical verb for a word ('bash' gives 'smash'), or None when the pack does not know it."""
    return _index(pack)["verbs"].get(_norm(word))
