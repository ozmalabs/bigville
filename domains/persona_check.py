"""persona_check.py -- self-test checks for a pack's persona tables (Phase 058).

    check_persona(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency), like the lexicon checks. It
reads the pack directly with domains/pack.load_pack. It checks:
- the persona tables exist; every job in JOBS has a ROUTINE row whose blocks are the six day blocks in order,
  whose places are the job's JOB_ROUTINE places or common places, and whose places have PLACE_WORDS;
- the routine agrees with the simple backend's bands: ROUTINE_BANDS are the boundaries 9, 17 and 21 that
  cheap.py used, and every row starts its work at morning_until, its evening at workday_until and its
  sleep at evening_until;
- every LIFE_STAGES stage has a ROUTINE_STAGE entry with the stage's work_fraction, and a row it names exists;
- every personality number of FOUNDING_PERSONALITY is a trait (its quantity has self words) or an engine
  parameter, and no name is both;
- the biography templates have their placeholders, and the band tables rise from zero;
- the relationship seeding: every kind it writes has a lexicon phrase, strengths sit on the lexicon scale,
  close kinds and close kin terms exist, counts are whole and non-negative, and the stream is its own.
"""
from __future__ import annotations

import re

from domains.lexicon import bands
from domains.pack import PackError, load_pack

_DIGIT = re.compile(r"\d")
DAY_BLOCKS = ("morning", "work", "midday", "afternoon", "evening", "sleep")
COMMON_PLACES = ("home", "church", "school", "market")
OLD_BANDS = {"morning_until": 9.0, "workday_until": 17.0, "evening_until": 21.0}   # cheap.py before Phase 058
REQUIRED = ("PERSONA_TRAITS", "PERSONA_ENGINE_PARAMS", "ROUTINE_BANDS", "ROUTINE", "ROUTINE_STAGE",
            "ROUTINE_WEEK", "ROUTINE_SEASON", "PLACE_WORDS", "YEARS_WORDS", "SPAN_WORDS", "SCHOOLING_WORDS",
            "TIE_DURATION_WORDS", "OFFICE_WORDS", "BIOGRAPHY_TEMPLATES", "RELATIONSHIP_SEEDING")
TEMPLATE_HOLES = {"stage": "{stage}", "job": "{job}", "incomer": "{when}", "schooling": "{schooling}",
                  "apprenticed": "{trade}", "former_trade": "{span}", "past_office": "{office}"}
BIOGRAPHY_ORDER = ("stage", "job", "birth", "schooling", "apprenticed", "former_trade", "past_office",
                   "married", "widowed", "household")
HOUSEHOLD_ROLES = ("head", "spouse", "child", "sibling")
SEEDING_HISTORY = ("spouse", "kin", "household", "friend", "workmate", "neighbour", "rival")


def _public(table):
    """The keys of a table that are not documentation (keys starting with an underscore)."""
    return [k for k in table if not str(k).startswith("_")]


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_words(name, value, sink):
    if not (isinstance(value, str) and value.strip()):
        sink.append(f"{name}: must be a non-empty string")
    elif _DIGIT.search(value):
        sink.append(f"{name}: a word must not carry a digit ({value!r})")


def _check_band_rows(name, rows, errors):
    if not isinstance(rows, list) or not rows:
        errors.append(f"{name}: needs a non-empty list of bands")
        return
    if float(rows[0]["min"]) != 0.0:
        errors.append(f"{name}: the first band must start at 0")
    mins = [float(r["min"]) for r in rows]
    if mins != sorted(mins) or len(set(mins)) != len(mins):
        errors.append(f"{name}: the band minimums must rise strictly")
    for r in rows:
        _check_words(f"{name}[{r.get('min')}]", r.get("phrase"), errors)


def _check_routine(pack, errors):
    jobs, job_routine = pack["JOBS"], pack["JOB_ROUTINE"]
    routine, places = pack["ROUTINE"], pack["PLACE_WORDS"]
    day_block_keys = set(pack["LEXICON_QUANTITIES"]["day_block"]["self"])
    raw = pack["ROUTINE_BANDS"]
    edges = {key: float(raw[key]) for key in OLD_BANDS if key in raw}
    for job in sorted(jobs):
        if job not in routine:
            errors.append(f"ROUTINE: job '{job}' has no row (every JOBS key needs one)")
        if job not in job_routine:
            errors.append(f"ROUTINE: JOB_ROUTINE has no places for the job '{job}'")
    for name in [k for k in routine if k != "_doc"]:
        row = routine[name]
        where = f"ROUTINE[{name}]"
        blocks = row.get("blocks", []) if isinstance(row, dict) else []
        kinds = [b.get("block") for b in blocks]
        if sorted(kinds) != sorted(DAY_BLOCKS):
            errors.append(f"{where}: blocks must be the six day blocks {list(DAY_BLOCKS)}, not {kinds}")
            continue
        starts = [float(b["start"]) for b in blocks]
        if starts != sorted(starts) or not all(0.0 <= s < 24.0 for s in starts):
            errors.append(f"{where}: block starts must rise within the day (0 to 24)")
        if name in jobs:
            allowed = set(job_routine.get(name, [])) | set(COMMON_PLACES)
        else:
            allowed = set(COMMON_PLACES) | {p for places_of in job_routine.values() for p in places_of}
        for b in blocks:
            if b["block"] not in day_block_keys:
                errors.append(f"{where}: block '{b['block']}' is not a day_block key")
            if b["place"] not in places:
                errors.append(f"{where}: place '{b['place']}' has no PLACE_WORDS entry")
            elif b["place"] not in allowed:
                errors.append(f"{where}: place '{b['place']}' is not in JOB_ROUTINE['{name}'] or a common place")
            _check_words(f"{where}.{b['block']}.task", b.get("task"), errors)
        by_kind = {b["block"]: float(b["start"]) for b in blocks}
        if "morning_until" in edges:
            if not by_kind["morning"] < edges["morning_until"]:
                errors.append(f"{where}: the morning block must start before morning_until")
            if by_kind["work"] != edges["morning_until"]:
                errors.append(f"{where}: the work block must start at morning_until ({edges['morning_until']})")
        if "workday_until" in edges and by_kind["evening"] != edges["workday_until"]:
            errors.append(f"{where}: the evening block must start at workday_until ({edges['workday_until']})")
        if "evening_until" in edges and by_kind["sleep"] != edges["evening_until"]:
            errors.append(f"{where}: the sleep block must start at evening_until ({edges['evening_until']})")


def _check_bands_and_stages(pack, errors, info):
    raw = pack["ROUTINE_BANDS"]
    for key, old in OLD_BANDS.items():
        if key not in raw or float(raw[key]) != old:
            errors.append(f"ROUTINE_BANDS.{key}: must be {old} (the boundary cheap.py used), not {raw.get(key)}")
    stages, life = pack["ROUTINE_STAGE"], pack["LIFE_STAGES"]
    for stage in life:
        if stage not in stages:
            errors.append(f"ROUTINE_STAGE: life stage '{stage}' has no entry")
            continue
        spec = stages[stage]
        if spec.get("row") is not None and spec["row"] not in pack["ROUTINE"]:
            errors.append(f"ROUTINE_STAGE[{stage}].row: '{spec['row']}' is not a ROUTINE row")
        if abs(float(spec.get("work_fraction", -1.0)) - float(life[stage]["work_fraction"])) > 1e-9:
            errors.append(f"ROUTINE_STAGE[{stage}].work_fraction must equal LIFE_STAGES[{stage}].work_fraction "
                          f"({life[stage]['work_fraction']})")
    for stage in _public(stages):
        if stage not in life:
            errors.append(f"ROUTINE_STAGE: '{stage}' is not a LIFE_STAGES key")
    week = pack["ROUTINE_WEEK"]
    days = int(pack["TIME"]["days_per_week"])
    for key in ("market_day", "church_day"):
        if not 0 <= int(week[key]) < days:
            errors.append(f"ROUTINE_WEEK.{key}: must be a weekday from 0 to {days - 1}")
    if week["market"]["block"] not in DAY_BLOCKS or week["church"]["block"] not in DAY_BLOCKS:
        errors.append("ROUTINE_WEEK: the market and church blocks must be day blocks")
    if week["market"]["place"] not in pack["PLACE_WORDS"]:
        errors.append("ROUTINE_WEEK.market.place: has no PLACE_WORDS entry")
    seasons = pack["ROUTINE_SEASON"]
    season_names = list(pack["TIME"]["season_start_day"])
    for season in season_names:
        if season not in seasons:
            errors.append(f"ROUTINE_SEASON: season '{season}' has no entry")
        else:
            _check_words(f"ROUTINE_SEASON[{season}].farm_task", seasons[season].get("farm_task"), errors)
    for job in seasons["farm_jobs"]:
        if job not in pack["JOBS"]:
            errors.append(f"ROUTINE_SEASON.farm_jobs: '{job}' is not a JOBS key")
    for place in seasons["farm_places"]:
        if place not in pack["PLACE_WORDS"]:
            errors.append(f"ROUTINE_SEASON.farm_places: '{place}' has no PLACE_WORDS entry")
    for place in _public(pack["PLACE_WORDS"]):
        _check_words(f"PLACE_WORDS[{place}]", pack["PLACE_WORDS"][place], errors)
    info.append(f"ROUTINE: {len(_public(stages))} life stages, {len(_public(pack['PLACE_WORDS']))} place words, "
                f"market day {week['market_day']} and church day {week['church_day']}, "
                f"{len(season_names)} seasons")


def _check_traits(pack, errors, info):
    traits = pack["PERSONA_TRAITS"]
    engine = _public(pack["PERSONA_ENGINE_PARAMS"])
    founding = set(pack["FOUNDING_PERSONALITY"]) if "FOUNDING_PERSONALITY" in pack else set()
    sources = {}
    for key in _public(traits):
        spec = traits[key]
        source = spec.get("source")
        if founding and source != "role_identity" and source not in founding:
            errors.append(f"PERSONA_TRAITS[{key}].source: '{source}' is not a FOUNDING_PERSONALITY key")
        if source in sources:
            errors.append(f"PERSONA_TRAITS[{key}]: source '{source}' is also the trait '{sources[source]}'")
        sources[source] = key
        quantity = spec.get("quantity")
        if quantity not in pack["LEXICON_QUANTITIES"]:
            errors.append(f"PERSONA_TRAITS[{key}].quantity: '{quantity}' has no lexicon table")
        elif not bands(quantity, "self", pack=pack.path):
            errors.append(f"PERSONA_TRAITS[{key}]: lexicon quantity '{quantity}' has no self words")
    for name in engine:
        if name in sources:
            errors.append(f"PERSONA_ENGINE_PARAMS[{name}]: an engine parameter cannot also be a trait")
    for name in sorted(founding):
        if name not in sources and name not in engine:
            errors.append(f"FOUNDING_PERSONALITY[{name}]: is neither a PERSONA_TRAITS source nor an engine "
                          f"parameter (classify it)")
    info.append(f"PERSONA: {len(sources)} traits in words, {len(engine)} engine parameters, "
                f"{len(founding)} founding numbers classified")


def _check_biography(pack, errors, info):
    tpl = pack["BIOGRAPHY_TEMPLATES"]
    if sorted(tpl["order"]) != sorted(BIOGRAPHY_ORDER):
        errors.append(f"BIOGRAPHY_TEMPLATES.order must name {sorted(BIOGRAPHY_ORDER)}")
    for key, hole in TEMPLATE_HOLES.items():
        if hole not in tpl[key]:
            errors.append(f"BIOGRAPHY_TEMPLATES[{key}]: needs the placeholder {hole}")
    for key in ("job", "stage", "birth", "incomer", "schooling", "apprenticed", "former_trade", "past_office",
                "married", "widowed"):
        _check_words(f"BIOGRAPHY_TEMPLATES[{key}]", tpl[key], errors)
    if sorted(tpl["household"]) != sorted(HOUSEHOLD_ROLES):
        errors.append(f"BIOGRAPHY_TEMPLATES.household must have the roles {list(HOUSEHOLD_ROLES)}")
    for key in ("YEARS_WORDS", "SPAN_WORDS", "SCHOOLING_WORDS", "TIE_DURATION_WORDS"):
        _check_band_rows(key, pack[key], errors)
    for office in _public(pack["OFFICE_WORDS"]):
        _check_words(f"OFFICE_WORDS[{office}]", pack["OFFICE_WORDS"][office], errors)
    info.append(f"BIOGRAPHY: {len(BIOGRAPHY_ORDER)} sentence kinds, {len(_public(pack['OFFICE_WORDS']))} office words")


def _check_seeding(pack, errors, warnings, info):
    cfg = pack["RELATIONSHIP_SEEDING"]
    if not isinstance(cfg["enabled"], bool):
        errors.append("RELATIONSHIP_SEEDING.enabled: must be true or false")
    if not isinstance(cfg["stream"], int) or isinstance(cfg["stream"], bool):
        errors.append("RELATIONSHIP_SEEDING.stream: must be a whole number")
    elif "KINSHIP_STREAM" in pack and int(pack["KINSHIP_STREAM"]) == int(cfg["stream"]):
        errors.append("RELATIONSHIP_SEEDING.stream equals KINSHIP_STREAM: the draws would share a stream")
    kinds_lex = set(pack["LEXICON_QUANTITIES"]["relationship_kind"]["self"])
    kind_of, strength = cfg["kind_of"], cfg["strength"]
    if set(kind_of) != set(strength):
        errors.append("RELATIONSHIP_SEEDING: kind_of and strength must name the same keys")
    for key, kind in kind_of.items():
        if kind not in kinds_lex:
            errors.append(f"RELATIONSHIP_SEEDING.kind_of[{key}]: kind '{kind}' has no relationship_kind phrase")
        value = strength.get(key)
        if not _is_number(value):
            errors.append(f"RELATIONSHIP_SEEDING.strength[{key}]: must be a number")
        elif kind == "feud":
            if not -1.0 <= float(value) < 0.0:
                errors.append(f"RELATIONSHIP_SEEDING.strength[{key}]: a feud is negative, from -1 to 0")
        elif not 0.0 <= float(value) <= 10.0:
            errors.append(f"RELATIONSHIP_SEEDING.strength[{key}]: must be on the 0 to 10 lexicon scale")
    for kind in cfg["close_kinds"]:
        if kind not in kinds_lex:
            errors.append(f"RELATIONSHIP_SEEDING.close_kinds: '{kind}' has no relationship_kind phrase")
    for term in cfg["close_kin_terms"]:
        if term not in pack["KIN_TERMS"]:
            errors.append(f"RELATIONSHIP_SEEDING.close_kin_terms: '{term}' is not a KIN_TERMS key")
    for key in ("max_close_ties", "colleague_count", "neighbour_radius", "neighbour_count", "friend_count",
                "rival_count"):
        value = cfg[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"RELATIONSHIP_SEEDING.{key}: must be a whole number of zero or more")
    if isinstance(cfg["max_close_ties"], int) and not 1 <= cfg["max_close_ties"] <= 15:
        errors.append("RELATIONSHIP_SEEDING.max_close_ties: must be from 1 to 15 (Dunbar's sympathy group)")
    if not 0.0 <= float(cfg["rival_spite_min"]) <= 1.0:
        errors.append("RELATIONSHIP_SEEDING.rival_spite_min: must be between 0 and 1")
    for key in SEEDING_HISTORY:
        _check_words(f"RELATIONSHIP_SEEDING.history[{key}]", cfg["history"].get(key), errors)
    if "{term}" not in cfg["history"].get("kin", ""):
        errors.append("RELATIONSHIP_SEEDING.history[kin]: needs the placeholder {term}")
    info.append(f"RELATIONSHIP_SEEDING: {len(kind_of)} tie kinds, close ties capped at {cfg['max_close_ties']}, "
                f"enabled={cfg['enabled']}")


def check_persona(pack_name, errors, warnings, info):
    """Run every persona check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"PERSONA: cannot load pack '{pack_name}': {exc}")
        return
    missing = [name for name in REQUIRED if name not in pack]
    if missing:
        errors.append(f"PERSONA: pack '{pack_name}' has no {', '.join(missing)} table")
        return
    before = len(errors)
    _check_routine(pack, errors)
    _check_bands_and_stages(pack, errors, info)
    _check_traits(pack, errors, info)
    _check_biography(pack, errors, info)
    _check_seeding(pack, errors, warnings, info)
    if len(errors) == before:
        info.append(f"PERSONA ({pack.name}): all persona checks pass")
