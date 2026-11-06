"""lexicon_check.py -- self-test checks for the words in a pack's LEXICON_* tables (Phase 051).

    check_lexicon(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It reads the pack
directly with domains/pack.load_pack, so it does not depend on the entity modules. It checks:
- every numeric band table covers its range with no gaps or overlaps (the first band starts at the
  range's low end, the thresholds strictly rise and stay inside the range), and its labels are unique
  within a perspective, and its phrases are words (no digits, no empty strings);
- every status table has an 'unknown' fallback, its keys equal the source table's keys (keys_from),
  and its other-perspective keys are a subset of its self keys;
- every edge or top the pack or the world names equals that source (EXHAUSTION, CARE, CARRYING, TIME,
  LIFE_STAGES, FOUNDING_MAP, ACTOR_DEFAULTS), checked for the bigville pack only (SOURCE_REFS; a test
  pack states its own edges); a table with published false says so in its _doc;
- every reverse word maps to a number or to a canonical verb, and a canonical verb is in VERBS if the
  pack has a VERBS table (otherwise that check is skipped and reported as info);
- every perceivable payload field in LEXICON_PAYLOAD names a table, and in the bigville pack every
  quantity the observation publishes as a number or a status has a table.
Edges the world holds in code (the bond bands, the simple backend's rest threshold) are documented
in the table _doc and are not checked here, because this module does not import world code.
"""
from __future__ import annotations

import math
import re

from domains.pack import PackError, load_pack

_DIGIT = re.compile(r"\d")
_TEMPLATE = "{what}"

# Edges and tops that must equal a value named elsewhere in the pack. Each entry is
# (quantity, perspective, "edge" | "top", [(table, key, ...), ...], scale). The value to match is the
# product of the paths' values times scale. An "edge" must be the min of a band; a "top" must be the
# range's high end.
SOURCE_REFS = [
    ("energy", "self", "edge", [("EXHAUSTION", "e_collapse")], 100.0),
    ("energy", "self", "edge", [("EXHAUSTION", "e_low")], 100.0),
    ("energy", "self", "edge", [("EXHAUSTION", "e_mid")], 100.0),
    ("energy", "self", "edge", [("EXHAUSTION", "e_high")], 100.0),
    ("hunger", "self", "edge", [("CARE", "care_hunger_need")], 1.0),
    ("hunger", "self", "edge", [("CARE", "malnourished_hunger")], 1.0),
    ("hunger", "other", "edge", [("CARE", "malnourished_hunger")], 1.0),
    ("hunger", "self", "top", [("CARE", "starve_limit")], 1.0),
    ("health", "self", "edge", [("CARE", "treat_health_base")], 1.0),
    ("load", "self", "edge", [("CARRYING", "overload_ratio")], 1.0),
    ("load", "self", "edge", [("CARRYING", "drop_ratio")], 1.0),
    ("load", "other", "edge", [("CARRYING", "overload_ratio")], 1.0),
    ("load", "other", "edge", [("CARRYING", "drop_ratio")], 1.0),
    ("hour", "self", "edge", [("EXHAUSTION", "night_end_hour")], 1.0),
    ("hour", "self", "edge", [("EXHAUSTION", "night_start_hour")], 1.0),
    ("duration", "self", "edge", [("TIME", "minutes_per_tick")], 1.0),
    ("duration", "self", "top", [("TIME", "ticks_per_day"), ("TIME", "minutes_per_tick")], 1.0),
    ("distance", "self", "top", [("FOUNDING_MAP", "width")], 1.0),
    ("mood", "self", "edge", [("ACTOR_DEFAULTS", "body", "mood")], 1.0),
    ("age", "self", "edge", [("LIFE_STAGES", "child", "age_min")], 1.0),
    ("age", "self", "edge", [("LIFE_STAGES", "youth", "age_min")], 1.0),
    ("age", "self", "edge", [("LIFE_STAGES", "adult", "age_min")], 1.0),
    ("age", "self", "edge", [("LIFE_STAGES", "elder", "age_min")], 1.0),
]

# Status quantities whose keys must equal the keys of a pack table (the value 'unknown' excluded).
STATUS_KEYS_FROM = {
    "health_status": "HEALTH_CONDITIONS",
    "season": "SEASONS",
    "weather": "WEATHER",
    "life_stage": "LIFE_STAGES",
}

# The quantities the observation publishes as numbers or status words (the bigville payload, as
# printed by a resident's observations at turn 0). Each must have a table and a LEXICON_PAYLOAD entry.
BIGVILLE_PAYLOAD_QUANTITIES = (
    "energy", "hunger", "health_status", "hour", "season", "weather", "condition", "amount",
    "distance", "relationship_strength",
)

def _walk(pack, path):
    """The value at path in the pack: the first key is a pack table, the rest are keys inside it."""
    if path[0] not in pack:
        return None
    value = pack[path[0]]
    for key in path[1:]:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_numeric(name, spec, errors):
    where = f"LEXICON_QUANTITIES[{name}]"
    rng = spec.get("range")
    if not (isinstance(rng, list) and len(rng) == 2 and all(_is_number(x) for x in rng) and rng[0] < rng[1]):
        errors.append(f"{where}.range: needs two finite numbers, low below high")
        return None
    lo, hi = float(rng[0]), float(rng[1])
    perspectives = [p for p in ("self", "other") if p in spec]
    if not perspectives:
        errors.append(f"{where}: has neither a 'self' nor an 'other' band table")
    for persp in perspectives:
        rows = spec[persp]
        here = f"{where}.{persp}"
        if not isinstance(rows, list) or not rows:
            errors.append(f"{here}: must be a non-empty list of bands")
            continue
        mins = []
        labels = set()
        for i, row in enumerate(rows):
            if not (isinstance(row, dict) and {"min", "label", "phrase"} <= set(row)):
                errors.append(f"{here}[{i}]: each band needs min, label and phrase")
                break
            m = row["min"]
            if not _is_number(m):
                errors.append(f"{here}[{i}].min: must be a finite number")
                break
            mins.append(float(m))
            label, phrase = row["label"], row["phrase"]
            if not (isinstance(label, str) and label.strip()):
                errors.append(f"{here}[{i}].label: must be a non-empty string")
            if not (isinstance(phrase, str) and phrase.strip()):
                errors.append(f"{here}[{i}].phrase: must be a non-empty string")
            elif _DIGIT.search(phrase):
                errors.append(f"{here}[{i}].phrase {phrase!r}: a phrase must not contain a number")
            if isinstance(label, str) and _DIGIT.search(label):
                errors.append(f"{here}[{i}].label {label!r}: a label must not contain a number")
            if isinstance(phrase, str) and _TEMPLATE not in phrase and "{" in phrase:
                errors.append(f"{here}[{i}].phrase {phrase!r}: the only template is {_TEMPLATE}")
            if label in labels:
                errors.append(f"{here}: label '{label}' appears twice")
            labels.add(label)
        if len(mins) != len(rows):
            continue
        if mins[0] != lo:
            errors.append(f"{here}: the first band starts at {mins[0]}, not at the range's low end {lo}; "
                          f"a gap below it")
        for i in range(1, len(mins)):
            if mins[i] <= mins[i - 1]:
                errors.append(f"{here}: thresholds must strictly rise, but {mins[i]} follows {mins[i - 1]} "
                              f"(overlap or repeat)")
        if mins and mins[-1] >= hi:
            errors.append(f"{here}: a band starts at {mins[-1]}, at or above the range's high end {hi}")
    return {"lo": lo, "hi": hi, "perspectives": perspectives}


def _check_status(name, spec, keys_source, errors):
    where = f"LEXICON_QUANTITIES[{name}]"
    if not isinstance(spec.get("self"), dict):
        errors.append(f"{where}.self: a status table needs a 'self' phrase for each key")
        return
    self_keys = set(spec["self"])
    if "unknown" not in self_keys:
        errors.append(f"{where}.self: needs the 'unknown' fallback key")
    for key, phrase in spec["self"].items():
        if not (isinstance(phrase, str) and phrase.strip()):
            errors.append(f"{where}.self[{key}]: the phrase must be a non-empty string")
        elif _DIGIT.search(phrase):
            errors.append(f"{where}.self[{key}] {phrase!r}: a phrase must not contain a number")
    if "other" in spec:
        if not isinstance(spec["other"], dict):
            errors.append(f"{where}.other: must be a mapping of key to phrase")
        else:
            for key, phrase in spec["other"].items():
                if key not in self_keys:
                    errors.append(f"{where}.other[{key}]: not a key of the self table")
                if not (isinstance(phrase, str) and phrase.strip()) or _DIGIT.search(phrase):
                    errors.append(f"{where}.other[{key}]: must be a phrase with no number")
    if keys_source is not None:
        expected = set(keys_source) | {"unknown"}
        missing = sorted(expected - self_keys)
        extra = sorted(self_keys - expected)
        if missing:
            errors.append(f"{where}: no phrase for {missing} (keys of the source table are complete)")
        if extra:
            errors.append(f"{where}: keys {extra} are not in the source table")


def _check_quantities(pack, errors, warnings, info, bigville):
    raw = pack["LEXICON_QUANTITIES"]
    names = {n for n in raw if not n.startswith("_")}
    for name in sorted(names):
        spec = raw[name]
        where = f"LEXICON_QUANTITIES[{name}]"
        if not isinstance(spec, dict):
            errors.append(f"{where}: must be a table")
            continue
        if "alias" in spec:
            if spec["alias"] not in names or "alias" in raw[spec["alias"]]:
                errors.append(f"{where}.alias: '{spec['alias']}' is not a quantity with its own bands")
            continue
        doc = spec.get("_doc", "")
        if not (isinstance(doc, str) and doc.strip()):
            errors.append(f"{where}: needs a _doc (sources, and whether the figures are APPROX)")
        published = spec.get("published", True)
        if published is False and "not yet published" not in doc:
            errors.append(f"{where}: published is false, so its _doc must say 'read-off not yet published'")
        if published is True and "not yet published" in doc:
            errors.append(f"{where}: published is true, but its _doc says 'not yet published'")
        kind = spec.get("kind")
        if kind == "numeric":
            _check_numeric(name, spec, errors)
        elif kind == "status":
            keys_source = None
            if name in STATUS_KEYS_FROM:
                table = STATUS_KEYS_FROM[name]
                if table in pack:
                    keys_source = pack[table]
                else:
                    info.append(f"{where}: pack has no {table} table, so its keys are not cross-checked")
            _check_status(name, spec, keys_source, errors)
        else:
            errors.append(f"{where}.kind: must be 'numeric' or 'status' (got {kind!r})")

    # A drifted edge is an error in the bigville pack itself, and a warning in a child pack that changes
    # its source (the child may have chosen a different tick or night on purpose; its lexicon should say so).
    sink = errors if pack.name == "bigville" else warnings
    for quantity, persp, kind, paths, scale in (SOURCE_REFS if bigville else []):
        spec = raw.get(quantity)
        if not isinstance(spec, dict) or spec.get("kind") != "numeric" or persp not in spec:
            continue
        values = []
        for path in paths:
            value = _walk(pack, path)
            if not _is_number(value):
                values = None
                errors.append(f"LEXICON_QUANTITIES[{quantity}]: source {'.'.join(path)} is not a number in the pack")
                break
            values.append(float(value))
        if values is None:
            continue
        target = scale
        for v in values:
            target *= v
        target = round(target, 9)
        label = " x ".join(".".join(p) for p in paths)
        if kind == "edge":
            mins = [float(r["min"]) for r in spec[persp]]
            if not any(abs(m - target) < 1e-9 for m in mins):
                sink.append(f"LEXICON_QUANTITIES[{quantity}].{persp}: no band starts at {target} ({label}); "
                              f"align the edge with the source or change the source")
        else:
            if not abs(float(spec["range"][1]) - target) < 1e-9:
                sink.append(f"LEXICON_QUANTITIES[{quantity}].range: the top is {spec['range'][1]}, not "
                              f"{target} ({label})")

    if "relationship_kind" in raw and "RELATIONSHIP_KINDS" in pack:
        kinds = {row["kind"] for row in pack["RELATIONSHIP_KINDS"].values()}
        if "RELATIONSHIP_DEFAULT" in pack:
            kinds.add(pack["RELATIONSHIP_DEFAULT"]["kind"])
        missing = sorted(kinds - set(raw["relationship_kind"].get("self", {})))
        if missing:
            errors.append(f"LEXICON_QUANTITIES[relationship_kind]: no phrase for the tie kinds {missing} "
                          f"of RELATIONSHIP_KINDS")

    for name in sorted(names):
        spec = raw[name]
        if isinstance(spec, dict) and "source" in spec:
            if "FOUNDING_PERSONALITY" not in pack or spec["source"] not in pack["FOUNDING_PERSONALITY"]:
                errors.append(f"LEXICON_QUANTITIES[{name}].source: '{spec['source']}' is not a FOUNDING_PERSONALITY key")

    if bigville:
        for name in BIGVILLE_PAYLOAD_QUANTITIES:
            if name not in raw:
                errors.append(f"LEXICON_QUANTITIES: the observation publishes '{name}', which has no table")


def _check_reverse(pack, errors, warnings, info):
    for word, value in pack["INTENSITY_WORDS"].items():
        if not (isinstance(word, str) and word.strip()):
            errors.append("INTENSITY_WORDS: a word must be a non-empty string")
        if not _is_number(value):
            errors.append(f"INTENSITY_WORDS[{word}]: must map to a finite number, not {value!r}")
    if len({" ".join(w.lower().split()) for w in pack["INTENSITY_WORDS"]}) != len(pack["INTENSITY_WORDS"]):
        errors.append("INTENSITY_WORDS: two words differ only in case or spacing")
    if "normally" in pack["INTENSITY_WORDS"] and pack["INTENSITY_WORDS"]["normally"] != 1.0:
        errors.append("INTENSITY_WORDS: 'normally' must be 1.0 (the normal intensity)")
    for word, value in pack["AMOUNT_WORDS"].items():
        if not _is_number(value) or value < 0:
            errors.append(f"AMOUNT_WORDS[{word}]: must map to a number of zero or more, not {value!r}")
    if len({" ".join(w.lower().split()) for w in pack["AMOUNT_WORDS"]}) != len(pack["AMOUNT_WORDS"]):
        errors.append("AMOUNT_WORDS: two words differ only in case or spacing")
    aliases = pack["VERB_ALIASES"]
    canonical = set()
    for word, verb in aliases.items():
        if not (isinstance(verb, str) and verb.strip()):
            errors.append(f"VERB_ALIASES[{word}]: must map to a canonical verb name")
            continue
        canonical.add(verb)
    for verb in sorted(canonical):
        if aliases.get(verb, verb) != verb:
            errors.append(f"VERB_ALIASES: '{verb}' is a canonical verb, but it maps to '{aliases[verb]}'; "
                          f"a canonical verb must map to itself")
    if "VERBS" in pack:
        for verb in sorted(canonical):
            if verb not in pack["VERBS"]:
                errors.append(f"VERB_ALIASES: canonical verb '{verb}' is not in the pack's VERBS table")
    else:
        info.append("VERB_ALIASES: the pack has no VERBS table, so canonical verb names are not checked against it")


def _check_payload(pack, errors, bigville):
    raw = pack["LEXICON_QUANTITIES"]
    table = pack["LEXICON_PAYLOAD"]
    referenced = set()
    for path, entry in table.items():
        if not isinstance(entry, dict) or (("quantity" in entry) == ("hidden" in entry)):
            errors.append(f"LEXICON_PAYLOAD[{path}]: needs exactly one of 'quantity' or 'hidden'")
            continue
        if "quantity" in entry:
            name = entry["quantity"]
            if name not in raw:
                errors.append(f"LEXICON_PAYLOAD[{path}]: quantity '{name}' has no table")
            referenced.add(name)
        elif not (isinstance(entry["hidden"], str) and entry["hidden"].strip()):
            errors.append(f"LEXICON_PAYLOAD[{path}]: a hidden field needs the reason it is not perceivable")
    if bigville:
        for name in BIGVILLE_PAYLOAD_QUANTITIES:
            if name not in referenced:
                errors.append(f"LEXICON_PAYLOAD: no observation field maps to the quantity '{name}'")


def check_lexicon(pack_name, errors, warnings, info):
    """Run every lexicon check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"LEXICON: cannot load pack '{pack_name}': {exc}")
        return
    for table in ("LEXICON_QUANTITIES", "INTENSITY_WORDS", "AMOUNT_WORDS", "VERB_ALIASES", "LEXICON_PAYLOAD"):
        if table not in pack:
            errors.append(f"LEXICON: pack '{pack_name}' has no {table} table")
            return
    # The bigville family (bigville, and a child that extends it) gets the source-edge and payload checks.
    bigville = pack.name == "bigville" or pack.extends == "bigville"
    before = len(errors)
    _check_quantities(pack, errors, warnings, info, bigville)
    _check_reverse(pack, errors, warnings, info)
    _check_payload(pack, errors, bigville)
    if len(errors) == before:
        numeric = sum(1 for s in pack["LEXICON_QUANTITIES"].values()
                      if isinstance(s, dict) and s.get("kind") == "numeric")
        info.append(f"LEXICON ({pack.name}): {len(pack['LEXICON_QUANTITIES'])} quantities ({numeric} numeric), "
                    f"{len(pack['INTENSITY_WORDS'])} intensity words, {len(pack['AMOUNT_WORDS'])} amount words, "
                    f"{len(pack['VERB_ALIASES'])} verb words, {len(pack['LEXICON_PAYLOAD'])} payload fields; all checks pass")
