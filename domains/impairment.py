"""impairment.py -- confidently wrong percepts for an impaired resident (Phase 065), and wrong heard words and counts (065b).

An impaired resident (drunk, tired, ill, in dim or dark light) is given a percept that is wrong and worded as sure
as a true one. The truth stays in the referee block. The sources, the rate by level, and the mechanisms are data in
world/impairment.json (IMPAIRMENT, with its `mishearing` pairs; DISTORTION; IMPAIRMENT_NEIGHBOURS). Off (IMPAIRMENT.enabled false, the
pack default), every function here returns its input unchanged, or None, and the agent view is what it was before.

    settings(game, pack)                      the effective switch, strength and active sources. A scenario sets them
                                              on the game as `game.impairment_scenario` (a dict with any of
                                              enabled, strength, sources); the pack gives the defaults.
    distort(game, actor, kind, name, subject, seen, rec, pack, others, known)
                                              the percept the resident is given: `seen` itself when nothing is
                                              impaired, otherwise a copy with the wrong tier and words
    referee_extra(seen)                       the distortion fields for a referee row ({} when there is no record)
    mishear(game, actor, rec, record, earshot, pack)
                                              the heard sentence an agent-view listener is given: None when off, else
                                              {text, distorted, sources, subject, mechanism?}; the truth stays in `record`
    utterance_referee(record, heard)          the referee row of a heard sentence
    mishear_simple(cfg, pack, band, listener, turn, record, earshot)
                                              the same for a simple listener, which holds no world (its own represented
                                              impairment; see bigville/backends/speech_in.py)
    quantity_shift(game, actor, rec, name, mark, pack)
                                              the shift of a written price (in the mark's unit) a reader is taken to
                                              misread by: None when off, else {distorted, delta, sources, mechanism?}
    quantity_referee(shift)                   the distortion fields for a written-price referee row ({} when None)
    note_view(game, actor, rec, log, pack)    records the subjects shown wrongly this turn
    note_action(game, actor, params, applied, pack)
                                              counts a major action taken on a subject shown wrongly this turn
    referee_block(game, log, pack)            the impairment block of the referee's perception ({} when off)
    report_block(game, pack)                  the impairment ledger for the game report ({} when off)

The draws are a function of (world seed, turn, resident, subject, kind, and a fixed label), read through hashlib, so
a run repeats and a recorded run replays. Nothing here uses the random module.

Faculty. A backend that declares impairment 'represented' models its own impairment, so no distortion is applied to
it by the agent view. 'enforced' and 'both' get the distortion. The rate is a function of measures the world already
reports: the intoxication band (the perceiver record), fatigue (1 minus the stamina reserve), the illness flag, and the
light. The simple listener reads only the intoxication band (its observations carry no other measure).
"""
from __future__ import annotations

import hashlib
import re

from domains import numeracy, perceiver
from domains.pack import load_pack

KINDS = ("person", "thing", "utterance", "quantity")
MECHANISMS = ("lower_tier", "neighbour_stage", "nearby_entity", "mishear_word", "shift_quantity")
# The kinds each mechanism may apply to. The self-test (impairment_check) checks every DISTORTION row against this.
APPLIES = {"lower_tier": ("person", "thing"), "neighbour_stage": ("person",), "nearby_entity": ("person", "thing"),
           "mishear_word": ("utterance",), "shift_quantity": ("utterance", "quantity")}
MEASURES = ("intoxication_band", "fatigue", "illness", "light")
LIGHTS = ("day", "dim", "dark", "lamplight")
SIMPLE_SEED = "simple"          # the draw seed of a simple listener, which holds no world reference
WORD = re.compile(r"[A-Za-z]+")
NAME = re.compile(r"[A-Za-z]+(?: [A-Za-z]+)*")


def table(pack):
    """The IMPAIRMENT table: the switch, the strength, the active sources, and the cap on the rate."""
    return load_pack(pack)["IMPAIRMENT"]


def _rows(pack):
    return load_pack(pack)["DISTORTION"]


def _source_names(pack):
    return [row["source"] for row in _rows(pack)]


def settings(game, pack):
    """{enabled, strength, sources}: the pack's values, overridden by the game's scenario when it has one. `game` may be
    None (the simple listener): then the pack's values are the settings."""
    base = table(pack)
    cfg = {"enabled": bool(base["enabled"]), "strength": float(base["strength"]),
           "sources": [str(source) for source in base["sources"]]}
    override = getattr(game, "impairment_scenario", None)
    if override:
        unknown = sorted(set(override) - set(cfg))
        if unknown:
            raise ValueError(f"impairment_scenario has unknown keys {unknown}")
        cfg.update(override)
        cfg["enabled"] = bool(cfg["enabled"])
        cfg["strength"] = float(cfg["strength"])
        cfg["sources"] = [str(source) for source in cfg["sources"]]
        bad = sorted(set(cfg["sources"]) - set(_source_names(pack)))
        if bad:
            raise ValueError(f"impairment_scenario names sources with no DISTORTION row: {bad}")
        if not 0.0 <= cfg["strength"] <= 1.0:
            raise ValueError(f"impairment_scenario strength must be between 0 and 1, not {cfg['strength']}")
    return cfg


def _seed(game):
    world = game.world
    node = getattr(world, "_map_node", None)
    return int(world.eng.node(node)["attrs"]["seed"]) if node is not None else 0


def _unit(*parts):
    """A number in [0, 1) from the parts, through sha256. The same parts always give the same number."""
    text = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "big") / float(1 << 64)


def _measures(game, actor, rec):
    """The measures the sources read, for one resident. Intoxication and light come from the perceiver record."""
    body = game.world.body_state(actor)
    return {"intoxication_band": rec["band"], "light": rec["light"],
            "fatigue": round(1.0 - float(body["stamina_reserve"]), 4), "illness": float(body["illness"])}


def _source_rates(measures, cfg, pack, kind):
    """{source: {rate, mechanisms}} for each active source whose measure qualifies, and the mechanisms it names for
    `kind`. A row with `levels` reads a category; a row with `steps` takes the last step whose threshold the measure
    reaches (thresholds ascend)."""
    out = {}
    for row in _rows(pack):
        source = row["source"]
        if source not in cfg["sources"]:
            continue
        value = measures[row["measure"]]
        if "levels" in row:
            rate = float(row["levels"].get(value, 0.0))
        else:
            rate = 0.0
            for threshold, step_rate in row["steps"]:
                if float(value) >= float(threshold):
                    rate = float(step_rate)
        if rate > 0.0:
            out[source] = {"rate": rate, "mechanisms": tuple(row["kinds"].get(kind, ()))}
    return out


def _probability(rates, cfg, pack):
    """The chance that one percept is distorted: 1 minus the product of the sources' chances, capped at max_rate."""
    keep = 1.0
    for item in rates.values():
        keep *= 1.0 - cfg["strength"] * item["rate"]
    return min(float(table(pack)["max_rate"]), 1.0 - keep)


def _mechanisms(rates):
    """The mechanisms the active sources name, sorted."""
    return sorted({m for item in rates.values() for m in item["mechanisms"]})


def _fill(template, facts):
    out = template
    for key in ("stage", "job", "kind"):
        if "{" + key + "}" in out:
            out = out.replace("{" + key + "}", str(facts.get(key, "")))
    return out


def _template(tiers, tier):
    for row in tiers:
        if row["tier"] == tier:
            return row["words"]
    raise KeyError(f"no perceiver tier {tier}")


def _noun_key(noun, pack):
    for key, word in perceiver.table(pack)["stage_nouns"].items():
        if word == noun:
            return key
    raise KeyError(f"no life stage has the words {noun!r}")


def _candidates(mechanism, kind, name, subject, seen, game, pack, others, known):
    """The wrong percepts one mechanism can give for this subject: each {tier, words} (and `as`, `as_job` for a
    swapped identity). The caller drops any that equal the true percept's words."""
    tiers = load_pack(pack)["PERCEIVER_TIERS"][kind]
    chosen = int(seen["tier"])
    if mechanism == "lower_tier":
        below = [row for row in tiers if row["tier"] < chosen]
        if not below:
            return []
        row = max(below, key=lambda item: item["tier"])
        return [{"tier": row["tier"], "words": _fill(row["words"], subject)}]
    if mechanism == "neighbour_stage":
        if kind != "person" or chosen == 0:
            return []
        template = _template(tiers, chosen)
        if "{stage}" not in template:
            return []
        neighbours = load_pack(pack)["IMPAIRMENT_NEIGHBOURS"][_noun_key(subject["stage"], pack)]
        stage_nouns = perceiver.table(pack)["stage_nouns"]
        return [{"tier": chosen, "words": _fill(template, {**subject, "stage": stage_nouns[key]})}
                for key in neighbours]
    if mechanism == "nearby_entity":
        if chosen == 0:
            return []
        template = _template(tiers, chosen)
        if kind == "thing":
            return [{"tier": chosen, "words": _fill(template, {**subject, "kind": what})}
                    for _handle, what in others if what and what != subject["kind"]]
        if name in known:
            # A resident known by name: the observer takes it to be another resident it knows.
            out = []
            for other in others:
                if other in known and other != name:
                    other_job = perceiver.person_subject(game, other, pack)["job"]
                    out.append({"tier": chosen, "words": other, "as": other, "as_job": other_job})
            return out
        found = [perceiver.person_subject(game, other, pack) for other in others]
        out = []
        if "{stage}" in template:
            out += [{"tier": chosen, "words": _fill(template, {**subject, "stage": facts["stage"]})}
                    for facts in found if facts["stage"] != subject["stage"]]
        if "{job}" in template:
            out += [{"tier": chosen, "words": _fill(template, {**subject, "job": facts["job"]})}
                    for facts in found if facts["job"] and facts["job"] != subject["job"]]
        return out
    raise KeyError(f"no impairment mechanism named {mechanism!r}")


def distort(game, actor, kind, name, subject, seen, rec, pack, others=(), known=()):
    """The percept the resident is given. `subject` is the true subject facts (perceiver.person_subject or
    thing_subject), `seen` the perceiver's percept, `others` the other residents (names) or things ((handle, kind words))
    in sight, `known` the names the resident knows. Returns `seen` itself when the switch is off or the backend holds
    the faculty itself; otherwise a copy with `distorted` (bool), `sources` (the active sources), and, when the percept
    was wrong, `tier`, `words`, `mechanism`, and for a swapped identity `as` and `as_job`."""
    cfg = settings(game, pack)
    if not cfg["enabled"] or rec["modes"]["impairment"] == "represented":
        return seen
    if kind not in ("person", "thing"):
        raise KeyError(f"no perceived kind named {kind!r}")
    rates = _source_rates(_measures(game, actor, rec), cfg, pack, kind)
    out = dict(seen, distorted=False, sources=sorted(rates))
    if not rates:
        return out
    seed, turn = _seed(game), int(game.world._turn)
    if _unit(seed, turn, actor, name, kind, "fire") >= _probability(rates, cfg, pack):
        return out
    found = []
    for mechanism in sorted({m for item in rates.values() for m in item["mechanisms"]}):
        for cand in _candidates(mechanism, kind, name, subject, seen, game, pack, others, set(known)):
            if cand["words"] != seen["words"] or "as" in cand:
                found.append({"mechanism": mechanism, **cand})
    if not found:
        return out
    pick = found[int(_unit(seed, turn, actor, name, kind, "pick") * len(found))]
    out.update(tier=pick["tier"], words=pick["words"], distorted=True, mechanism=pick["mechanism"])
    if "as" in pick:
        out["as"] = pick["as"]
        out["as_job"] = pick["as_job"]
    return out


def referee_extra(seen):
    """The distortion fields of a referee row. Empty when the percept has no impairment record (switch off)."""
    if "distorted" not in seen:
        return {}
    extra = {"distorted": bool(seen["distorted"]), "sources": list(seen["sources"])}
    if seen["distorted"]:
        extra["mechanism"] = seen["mechanism"]
        if "as" in seen:
            extra["as"] = seen["as"]
    return extra


# ----------------------------------------------------------------- Phase 065b: heard words

def _names(earshot):
    """The names in earshot that are plain words or word sequences (letters and single spaces), sorted."""
    return sorted({str(name) for name in earshot if NAME.fullmatch(str(name))})


def _match_case(model, word):
    return word[:1].upper() + word[1:] if model[:1].isupper() else word


def _bounded(text):
    return r"(?<![A-Za-z])" + re.escape(text) + r"(?![A-Za-z])"


def _swaps(text, earshot, pack):
    """(mechanism, new text) for each one-word change the heard text can take. A name in earshot (mishear_word) becomes
    another name in earshot; a word in MISHEARING becomes one of its near words; a spelled number word (shift_quantity)
    becomes the word one step up or down the NUMERAL_WORDS list. Only the mechanisms the caller names are used."""
    pk = load_pack(pack)
    out = []
    names = _names(earshot)
    spans = []
    for name in names:
        for match in re.finditer(_bounded(name), text):
            spans.append((match.start(), match.end()))
            out += [("mishear_word", text[:match.start()] + other + text[match.end():])
                    for other in names if other != name]
    near = table(pack)["mishearing"]
    numerals = pk["NUMERAL_WORDS"]["words"]
    for match in WORD.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        word = match.group(0)
        out += [("mishear_word", text[:match.start()] + _match_case(word, option) + text[match.end():])
                for option in near.get(word.lower(), [])]
        if word.lower() in numerals:
            index = numerals.index(word.lower())
            for step in (-1, 1):
                if 0 <= index + step < len(numerals):
                    out.append(("shift_quantity", text[:match.start()]
                                + _match_case(word, numerals[index + step]) + text[match.end():]))
    return out


def _mishear(cfg, pack, measures, seed, turn, listener, record, earshot):
    """The heard sentence as the listener takes it. The draw is keyed to the listener, the turn, the speaker and the
    record's own turn. Returns {text, distorted, sources, subject} and, when distorted, mechanism."""
    speaker = str(record.get("speaker", ""))
    text = str(record.get("text", "") or "")
    name = f"speech:{speaker}:{float(record.get('turn', 0.0))}"
    rates = _source_rates(measures, cfg, pack, "utterance")
    out = {"text": text, "distorted": False, "sources": sorted(rates), "subject": name}
    mechanisms = _mechanisms(rates)
    if not rates or not text or not mechanisms:
        return out
    if _unit(seed, turn, listener, name, "utterance", "fire") >= _probability(rates, cfg, pack):
        return out
    found = [item for item in _swaps(text, earshot, pack) if item[0] in mechanisms and item[1] != text]
    if not found:
        return out
    mechanism, wrong = found[int(_unit(seed, turn, listener, name, "utterance", "pick") * len(found))]
    out.update(text=wrong, distorted=True, mechanism=mechanism)
    return out


def mishear(game, actor, rec, record, earshot, pack):
    """The heard sentence an agent-view listener is given (Phase 065b). `record` is one heard_utterances record and
    `earshot` the names of the residents in sight. None when the switch is off or the backend holds the faculty itself;
    otherwise the result of _mishear (the truth is record['text'])."""
    cfg = settings(game, pack)
    if not cfg["enabled"] or rec["modes"]["impairment"] == "represented":
        return None
    return _mishear(cfg, pack, _measures(game, actor, rec), _seed(game), int(game.world._turn), actor, record,
                    earshot)


def mishear_simple(cfg, pack, band, listener, turn, record, earshot):
    """The heard sentence a simple listener takes (Phase 065b): the same table, with the intoxication band the listener's
    observations carry as the only measure. None when the switch is off (cfg['enabled'] false)."""
    if not cfg["enabled"]:
        return None
    measures = {"intoxication_band": band, "light": "day", "fatigue": 0.0, "illness": 0.0}
    return _mishear(cfg, pack, measures, SIMPLE_SEED, int(turn), listener, record, earshot)


def utterance_referee(record, heard):
    """The referee row of a heard sentence: what the listener took beside what was said."""
    row = {"subject": heard["subject"], "kind": "utterance", "speaker": str(record.get("speaker", "")),
           "percept": heard["text"], "truth": str(record.get("text", "") or ""), "distorted": bool(heard["distorted"]),
           "sources": list(heard["sources"])}
    if heard["distorted"]:
        row["mechanism"] = heard["mechanism"]
    return row


# ----------------------------------------------------------------- Phase 065b: counts and written prices

def _shift(game, actor, rec, name, count, pack):
    """The shift of a count by one unit, for one reader: None when impairment does not apply (switch off, or a
    'represented' backend); otherwise {distorted, delta, sources, mechanism?}. A count below one is not shifted, and a
    shift down from one is not taken (it would read as none)."""
    cfg = settings(game, pack)
    if not cfg["enabled"] or rec["modes"]["impairment"] == "represented":
        return None
    rates = _source_rates(_measures(game, actor, rec), cfg, pack, "quantity")
    out = {"distorted": False, "delta": 0, "sources": sorted(rates)}
    if not rates or int(count) < 1 or "shift_quantity" not in _mechanisms(rates):
        return out
    steps = [step for step in (-1, 1) if int(count) + step >= 1]
    seed, turn = _seed(game), int(game.world._turn)
    if not steps or _unit(seed, turn, actor, name, "quantity", "fire") >= _probability(rates, cfg, pack):
        return out
    delta = steps[int(_unit(seed, turn, actor, name, "quantity", "pick") * len(steps))]
    out.update(distorted=True, delta=delta, mechanism="shift_quantity")
    return out


def quantity_shift(game, actor, rec, name, mark, pack):
    """The shift of a written price for one reader (Phase 065b). `mark` is a WRITTEN_MARKS entry with a price and a unit;
    the count is the price in units of the mark's unit (a loaf is its coin value). None when the mark has no price, or
    impairment does not apply; otherwise as _shift, with delta in units of the mark's unit."""
    if "price" not in mark:
        return None
    coin = float(numeracy.units(pack)[mark["unit"]]["coin"])
    count = int(float(mark["price"]) / coin + 0.5)
    return _shift(game, actor, rec, name, count, pack)


def quantity_referee(shift):
    """The distortion fields of a written-price referee row ({} when impairment does not apply)."""
    if shift is None:
        return {}
    extra = {"distorted": bool(shift["distorted"]), "sources": list(shift["sources"]), "distortion_kind": "quantity"}
    if shift["distorted"]:
        extra["mechanism"] = shift["mechanism"]
        extra["shift"] = int(shift["delta"])
    return extra


# ----------------------------------------------------------------- the ledger

def _ledger(game):
    led = getattr(game, "_impairment_ledger", None)
    if led is None:
        led = {"percepts": set(), "actions": 0, "on_wrong": 0, "on_wrong_applied": 0, "on_wrong_refused": 0,
               "sources": {}, "by_kind": {}}
        setattr(game, "_impairment_ledger", led)
    return led


def note_view(game, actor, rec, log, pack):
    """Remembers which subjects this resident was shown wrongly this turn, for note_action. Counts each once per turn,
    under the kind of the referee row (person, thing, utterance, or the distortion kind of a written row)."""
    if rec is None or not settings(game, pack)["enabled"]:
        return
    turn = int(game.world._turn)
    shown = {row["subject"]: list(row.get("sources", [])) for row in log if row.get("distorted")}
    kinds = {row["subject"]: row.get("distortion_kind", row.get("kind", "")) for row in log if row.get("distorted")}
    views = getattr(game, "_impairment_views", None)
    if views is None:
        views = {}
        setattr(game, "_impairment_views", views)
    views[actor] = {"turn": turn, "shown": shown}
    led = _ledger(game)
    for subject in shown:
        key = (turn, actor, subject)
        if key not in led["percepts"]:
            led["percepts"].add(key)
            led["by_kind"][kinds[subject]] = led["by_kind"].get(kinds[subject], 0) + 1


def note_action(game, actor, params, applied, pack):
    """Counts a major action by a resident who was shown a view this turn. The action is on a wrong percept when its
    target (params['target']) is a subject shown wrongly this turn: a thing's handle, or a resident's name."""
    if not settings(game, pack)["enabled"]:
        return
    view = (getattr(game, "_impairment_views", None) or {}).get(actor)
    if view is None or view["turn"] != int(game.world._turn):
        return
    led = _ledger(game)
    led["actions"] += 1
    target = str((params or {}).get("target", ""))
    if target not in view["shown"]:
        return
    led["on_wrong"] += 1
    led["on_wrong_applied" if applied else "on_wrong_refused"] += 1
    for source in view["shown"][target]:
        led["sources"][source] = led["sources"].get(source, 0) + 1


def referee_block(game, log, pack):
    """The impairment block of the referee's perception: the switch as it stands and how many percepts were wrong."""
    cfg = settings(game, pack)
    if not cfg["enabled"]:
        return {}
    return {"impairment": {"settings": cfg, "rows": len(log),
                           "distorted": sum(1 for row in log if row.get("distorted"))}}


def report_block(game, pack):
    """The impairment ledger for the game report. Empty when the switch is off. `percepts_shown_wrong` counts the
    subjects shown wrongly (persons, things, heard sentences, written prices), once per turn and resident; `by_kind`
    splits that count by kind."""
    if not settings(game, pack)["enabled"]:
        return {}
    led = _ledger(game)
    return {"impairment": {"percepts_shown_wrong": len(led["percepts"]), "actions": led["actions"],
                           "on_wrong_percept": led["on_wrong"], "on_wrong_applied": led["on_wrong_applied"],
                           "on_wrong_refused": led["on_wrong_refused"], "by_source": dict(sorted(led["sources"].items())),
                           "by_kind": dict(sorted(led["by_kind"].items()))}}
