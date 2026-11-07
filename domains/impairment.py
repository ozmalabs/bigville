"""impairment.py -- confidently wrong percepts for an impaired resident (Phase 065).

An impaired resident (drunk, tired, ill, in dim or dark light) is given a percept that is wrong and worded as sure
as a true one. The truth stays in the referee block. The sources, the rate by level, and the mechanisms are data in
world/impairment.json (IMPAIRMENT, DISTORTION, IMPAIRMENT_NEIGHBOURS). Off (IMPAIRMENT.enabled false, the pack
default), every function here returns its input unchanged, and the agent view is what it was before this phase.

    settings(game, pack)                      the effective switch, strength and active sources. A scenario sets them
                                              on the game as `game.impairment_scenario` (a dict with any of
                                              enabled, strength, sources); the pack gives the defaults.
    distort(game, actor, kind, name, subject, seen, rec, pack, others, known)
                                              the percept the resident is given: `seen` itself when nothing is
                                              impaired, otherwise a copy with the wrong tier and words
    referee_extra(seen)                       the distortion fields for a referee row ({} when there is no record)
    note_view(game, actor, rec, log, pack)    records the subjects shown wrongly this turn
    note_action(game, actor, params, applied, pack)
                                              counts a major action taken on a subject shown wrongly this turn
    referee_block(game, log, pack)            the impairment block of the referee's perception ({} when off)
    report_block(game, pack)                  the impairment ledger for the game report ({} when off)

The draws are a function of (world seed, turn, resident, subject, kind, and a fixed label), read through hashlib, so
a run repeats and a recorded run replays. Nothing here uses the random module.

Faculty. A backend that declares impairment 'represented' models its own impairment, so no distortion is applied to
it. 'enforced' and 'both' get the distortion. The rate is a function of measures the world already reports: the
intoxication band (the perceiver record), fatigue (1 minus the stamina reserve), the illness flag, and the light.
"""
from __future__ import annotations

import hashlib

from domains import perceiver
from domains.pack import load_pack

KINDS = ("person", "thing")
MECHANISMS = ("lower_tier", "neighbour_stage", "nearby_entity")
MEASURES = ("intoxication_band", "fatigue", "illness", "light")
LIGHTS = ("day", "dim", "dark", "lamplight")


def table(pack):
    """The IMPAIRMENT table: the switch, the strength, the active sources, and the cap on the rate."""
    return load_pack(pack)["IMPAIRMENT"]


def _rows(pack):
    return load_pack(pack)["DISTORTION"]


def _source_names(pack):
    return [row["source"] for row in _rows(pack)]


def settings(game, pack):
    """{enabled, strength, sources}: the pack's values, overridden by the game's scenario when it has one."""
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
    if kind not in KINDS:
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


def _ledger(game):
    led = getattr(game, "_impairment_ledger", None)
    if led is None:
        led = {"percepts": set(), "actions": 0, "on_wrong": 0, "on_wrong_applied": 0, "on_wrong_refused": 0,
               "sources": {}}
        setattr(game, "_impairment_ledger", led)
    return led


def note_view(game, actor, rec, log, pack):
    """Remembers which subjects this resident was shown wrongly this turn, for note_action. Counts each once per turn."""
    if rec is None or not settings(game, pack)["enabled"]:
        return
    turn = int(game.world._turn)
    shown = {row["subject"]: list(row.get("sources", [])) for row in log if row.get("distorted")}
    views = getattr(game, "_impairment_views", None)
    if views is None:
        views = {}
        setattr(game, "_impairment_views", views)
    views[actor] = {"turn": turn, "shown": shown}
    led = _ledger(game)
    for subject in shown:
        led["percepts"].add((turn, actor, subject))


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
    """The impairment ledger for the game report. Empty when the switch is off."""
    if not settings(game, pack)["enabled"]:
        return {}
    led = _ledger(game)
    return {"impairment": {"percepts_shown_wrong": len(led["percepts"]), "actions": led["actions"],
                           "on_wrong_percept": led["on_wrong"], "on_wrong_applied": led["on_wrong_applied"],
                           "on_wrong_refused": led["on_wrong_refused"], "by_source": dict(sorted(led["sources"].items()))}}
