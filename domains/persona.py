"""persona.py -- a resident's persona: traits in words, a life sketch, a usual day, and close ties (Phase 058).

Every table is read from the pack (`world/persona.json`, plus the lexicon for the words about numbers).
Nothing here changes a resident's `character.personality`: the traits are a derived view of it.

    traits(personality, identity)     -> {"self": {key: phrase}, "other": {key: phrase}}
    engine_parameter_names()          -> the raw numbers that stay engine configuration, not traits
    simple_band(hour)                 -> "morning" | "workday" | "evening" | "night" (cheap.py's bands)
    usual_day(job, stage, hour, ...)  -> the day's blocks, the block now, and the sentences for the card
    life_sketch(facts)                -> the biography sentences from a resident's own history
    persona(character_or_name, world_or_game) -> a plain dict of strings (the persona card)

The card is built from what the resident holds: the traits in their personality, their founding history,
their own kin terms and their own ties (the bond records they hold). It holds no lexicon number (every
phrase comes from a band table and has no digit) and no record another resident holds.
"""
from __future__ import annotations

import functools

from domains.lexicon import describe
from domains.pack import load_pack

DEFAULT_PACK = "bigville"
CARD_KEYS = ("name", "traits", "as_others_see", "life", "usual_day", "ties")


def _table(name, pack):
    return load_pack(pack)[name]


def _words(key):
    return str(key).replace("_", " ")


def _band_phrase(rows, value):
    """The phrase of the last band whose min is at or below `value` (rows ascending by min)."""
    phrase = rows[0]["phrase"]
    for row in rows:
        if float(value) >= float(row["min"]):
            phrase = row["phrase"]
    return phrase


def _office_phrase(pk, office):
    """An office's words from OFFICE_WORDS, or, for an office the pack words no better, its key read as words
    ('as reeve' for a pack that renamed the office)."""
    return pk["OFFICE_WORDS"].get(office) or f"as {_words(office)}"


def _lexicon_phrase(quantity, key, perspective, pack):
    out = describe(quantity, key, perspective, pack=pack)
    return out["phrase"] if out else ""


# ------------------------------------------------------------------ traits
def engine_parameter_names(pack=DEFAULT_PACK):
    """The personality numbers that stay engine configuration (PERSONA_ENGINE_PARAMS), sorted."""
    return sorted(_table("PERSONA_ENGINE_PARAMS", pack))


def trait_keys(pack=DEFAULT_PACK):
    return list(_table("PERSONA_TRAITS", pack))


def _source_value(source, personality, identity):
    if source in personality and personality[source] is not None:
        return float(personality[source])
    if source in identity and identity[source] is not None:
        return float(identity[source])
    return None


def traits(personality, identity=None, pack=DEFAULT_PACK):
    """Each trait in words, as the resident sees it (`self`) and as an observer could (`other`).

    A trait whose source is missing from the personality is left out, not defaulted. A quantity with no
    'other' words is absent from `other`, because no observer can tell it."""
    identity = dict(identity or {})
    personality = dict(personality or {})
    own, seen = {}, {}
    for key, spec in _table("PERSONA_TRAITS", pack).items():
        value = _source_value(spec["source"], personality, identity)
        if value is None:
            continue
        phrase = _lexicon_phrase(spec["quantity"], value, "self", pack)
        if phrase:
            own[key] = phrase
        phrase = _lexicon_phrase(spec["quantity"], value, "other", pack)
        if phrase:
            seen[key] = phrase
    return {"self": own, "other": seen}


# ------------------------------------------------------------------ the simple backend's bands
@functools.lru_cache(maxsize=16)
def _band_edges(pack):
    rows = _table("ROUTINE_BANDS", pack)
    return float(rows["morning_until"]), float(rows["workday_until"]), float(rows["evening_until"])


def simple_band(hour, pack=DEFAULT_PACK):
    """The simple backend's band for an hour: the same four bands and boundaries as before Phase 058.
    The boundaries are read from ROUTINE_BANDS, not hard-coded."""
    morning, workday, evening = _band_edges(pack)
    if hour < morning:
        return "morning"
    if hour < workday:
        return "workday"
    if hour < evening:
        return "evening"
    return "night"


# ------------------------------------------------------------------ the usual day
def routine_blocks(job, stage="adult", *, weekday=None, season=None, pack=DEFAULT_PACK):
    """The day's blocks for a job at a life stage, in order from the morning.

    Each block: {block, start, place, place_words, task}. The life stage picks a row (a dependant row for a
    child or infant) and overrides some blocks. A market day moves a market job's afternoon to the market;
    a church day turns the work block into a midday block at the church; in a farm season a farm job's
    field work takes that season's task. A resident may depart from all of this; nothing enforces it."""
    pk = load_pack(pack)
    routine, stages = pk["ROUTINE"], pk["ROUTINE_STAGE"]
    stage = stage if stage in stages else "adult"
    spec = stages[stage]
    row_name = spec.get("row") or job
    if row_name not in routine:
        raise KeyError(f"pack '{pack}' has no ROUTINE row for '{row_name}'")
    blocks = []
    for raw in routine[row_name]["blocks"]:
        block = dict(raw)
        block.update(spec.get("override", {}).get(block["block"], {}))
        blocks.append(block)
    week, seasons = pk["ROUTINE_WEEK"], pk["ROUTINE_SEASON"]
    if season in seasons and row_name == job and job in seasons["farm_jobs"]:
        for block in blocks:
            if block["block"] in ("work", "afternoon") and block["place"] in seasons["farm_places"]:
                block["task"] = seasons[season]["farm_task"]
    if weekday is not None:
        days = int(pk["TIME"]["days_per_week"])
        day = int(weekday) % days
        if day == int(week["market_day"]) and job in pk["JOB_ROUTINE"] and "market" in pk["JOB_ROUTINE"][job]:
            for block in blocks:
                if block["block"] == week["market"]["block"]:
                    block.update(place=week["market"]["place"], task=week["market"]["task"])
        if day == int(week["church_day"]):
            for block in blocks:
                if block["block"] == week["church"]["block"]:
                    block.update(week["church"]["set"])
    places = pk["PLACE_WORDS"]
    for block in blocks:
        if block["place"] not in places:
            raise KeyError(f"pack '{pack}' has no PLACE_WORDS entry for '{block['place']}'")
        block["place_words"] = places[block["place"]]
    return blocks


def block_now(blocks, hour):
    """The index of the block that covers `hour`. Hours before the first block belong to the last (sleep)."""
    current = len(blocks) - 1
    h = float(hour) % 24.0
    for index, block in enumerate(blocks):
        if h >= float(block["start"]):
            current = index
    return current


def usual_day(job, stage="adult", *, hour=6.0, weekday=None, season=None, pack=DEFAULT_PACK):
    """The usual day, with the block for `hour` marked and each block's words.

    Returns {"blocks": [...], "now": index, "today": "...", "sentences": ["..."]}. Each block gets a `phrase`
    (the lexicon's day_block words) and a `sentence` ("working the fields (at work)")."""
    blocks = routine_blocks(job, stage, weekday=weekday, season=season, pack=pack)
    pk = load_pack(pack)
    week = pk["ROUTINE_WEEK"]
    for block in blocks:
        block["phrase"] = _lexicon_phrase("day_block", block["block"], "self", pack)
        block["sentence"] = f"{block['task']} ({block['phrase']})"
    today = []
    if season is not None:
        today.append(_lexicon_phrase("season", season, "self", pack))
    if weekday is not None:
        day = int(weekday) % int(pk["TIME"]["days_per_week"])
        if day == int(week["market_day"]):
            today.append("market day")
        if day == int(week["church_day"]):
            today.append("church day")
    now = block_now(blocks, hour)
    return {"blocks": blocks, "now": now, "today": ", ".join(t for t in today if t),
            "sentences": [b["sentence"] for b in blocks]}


# ------------------------------------------------------------------ the life sketch
def life_sketch(facts, pack=DEFAULT_PACK):
    """The biography sentences, from the resident's own history (BIOGRAPHY_TEMPLATES.order).

    `facts` keys (all optional): stage (a LIFE_STAGES key), job, local (bool), years_in_village (number),
    schooling_years (number), apprenticed (trade keys), former_trades ([{trade, years}]), past_offices
    (office keys), married (bool), widowed (bool), household_role (head | spouse | child | sibling)."""
    pk = load_pack(pack)
    tpl = pk["BIOGRAPHY_TEMPLATES"]
    out = []
    for key in tpl["order"]:
        if key == "stage" and facts.get("stage"):
            phrase = _lexicon_phrase("life_stage", facts["stage"], "self", pack)
            if phrase:
                out.append(tpl["stage"].replace("{stage}", phrase))
        elif key == "job" and facts.get("job"):
            out.append(tpl["job"].replace("{job}", _words(facts["job"])))
        elif key == "birth":
            if facts.get("local", True):
                out.append(tpl["birth"])
            elif facts.get("years_in_village") is not None:
                when = _band_phrase(pk["YEARS_WORDS"], facts["years_in_village"])
                out.append(tpl["incomer"].replace("{when}", when))
        elif key == "schooling" and facts.get("schooling_years") is not None:
            out.append(tpl["schooling"].replace(
                "{schooling}", _band_phrase(pk["SCHOOLING_WORDS"], facts["schooling_years"])))
        elif key == "apprenticed":
            for trade in facts.get("apprenticed", []) or []:
                out.append(tpl["apprenticed"].replace("{trade}", _words(trade)))
        elif key == "former_trade":
            for row in facts.get("former_trades", []) or []:
                span = _band_phrase(pk["SPAN_WORDS"], row.get("years", 0.0))
                out.append(tpl["former_trade"].replace("{trade}", _words(row["trade"])).replace("{span}", span))
        elif key == "past_office":
            for office in facts.get("past_offices", []) or []:
                out.append(tpl["past_office"].replace("{office}", _office_phrase(pk, office)))
        elif key == "married" and facts.get("married"):
            out.append(tpl["married"])
        elif key == "widowed" and facts.get("widowed"):
            out.append(tpl["widowed"])
        elif key == "household":
            role = facts.get("household_role")
            if role and role in tpl["household"]:
                out.append(tpl["household"][role])
    return out


# ------------------------------------------------------------------ the persona card
def _tie_words(kind, strength, years, pack, housemate=False):
    kind_phrase = _lexicon_phrase("relationship_kind", kind, "self", pack) or "a tie of unclear kind"
    parts = [kind_phrase]
    if kind != "feud":
        warmth = _lexicon_phrase("relationship_strength", max(0.0, float(strength)), "self", pack)
        if warmth and warmth != kind_phrase:
            parts.append(warmth)
    if housemate and kind != "household":
        parts.append(_table("RELATIONSHIP_SEEDING", pack)["history"]["household"])
    parts.append(_band_phrase(_table("TIE_DURATION_WORDS", pack), years or 0.0))
    return ", ".join(parts)


def _held_ties(name, world, pack):
    """The ties name holds: (target, kind, strength, years_known, housemate) from its own bond records, by target."""
    rows = []
    for (holder, target), bond in getattr(world, "_relationships", {}).items():
        if holder != name:
            continue
        attrs = world.eng.node(bond)["attrs"]
        rows.append((str(target), str(attrs.get("kind", "unknown")), float(attrs.get("strength", 0.0)),
                     float(attrs.get("years_known", 0.0)), bool(attrs.get("household", 0.0))))
    return sorted(rows)


def _facts_for(name, world):
    """The life-sketch facts a resident holds about themselves: the founding history and their own kin terms."""
    cast = getattr(world, "_cast100", None) or {}
    record = next((r for r in cast.get("residents", []) if r["name"] == name), None)
    if record is None:
        return {}
    history = dict(record.get("history") or {})
    kin = world.kin_terms_held(name) if hasattr(world, "kin_terms_held") else []
    married = any(row["term"] == "spouse" for row in kin)
    return {"job": record["role"], "local": bool(history.get("local", True)),
            "years_in_village": float(history.get("years_in_village", record.get("age", 0))),
            "schooling_years": history.get("schooling_years"),
            "apprenticed": list(history.get("apprenticed", [])),
            "former_trades": [dict(f) for f in history.get("former_trades", [])],
            "past_offices": list(history.get("past_offices", [])),
            "married": married, "widowed": bool(history.get("widowed", False)),
            "household_role": str(history.get("household_role", ""))}


def _as_world(obj):
    return obj if hasattr(obj, "_actors") else getattr(obj, "world", None)


def persona(character_or_name, world_or_game=None, *, pack=None):
    """The persona card for one resident: a plain dict of strings (keys in CARD_KEYS).

    `character_or_name` is a CharacterDefinition or a resident's name. `world_or_game` is a BigvilleGame,
    a world, or None. Without a world the card still has the traits and the usual day for the character's
    job, but no life sketch, no ties and no time of day (hour 6, no season)."""
    game = world_or_game if hasattr(world_or_game, "characters") else None
    world = _as_world(world_or_game) if world_or_game is not None else None
    pack = pack or getattr(world, "data_pack", None) or DEFAULT_PACK
    if isinstance(character_or_name, str):
        name = character_or_name
        character = (game.characters.get(name) if game is not None else None)
    else:
        character = character_or_name
        name = str(character.character_id)
    if character is not None:
        personality, identity = dict(character.personality), dict(character.identity)
    elif world is not None and name in world._actors:
        attrs = world.eng.node(world._actors[name])["attrs"]
        personality = {k: attrs[k] for k in attrs if k in
                       {v["source"] for v in _table("PERSONA_TRAITS", pack).values()}}
        identity = {k: attrs.get(k) for k in ("role", "life_stage", "klass", "group", "age")}
    else:
        raise KeyError(f"no resident named {name!r}")
    job = str(identity.get("role", ""))
    stage = str(identity.get("life_stage") or "adult")
    hour, weekday, season = 6.0, None, None
    ties, facts = [], {}
    if world is not None:
        clock = world.calendar()
        hour_now = clock.get("hour")
        hour = float(hour_now) if hour_now is not None else 6.0
        weekday = int(float(clock.get("day") or 0))
        season = clock.get("season")
        facts = _facts_for(name, world)
        for target, kind, strength, years, housemate in _held_ties(name, world, pack):
            ties.append(f"{target}: {_tie_words(kind, strength, years, pack, housemate)}")
    own = traits(personality, identity, pack)
    day = usual_day(job, stage, hour=hour, weekday=weekday, season=season, pack=pack) if job in \
        _table("JOB_ROUTINE", pack) else None
    if day is not None:
        now = day["blocks"][day["now"]]
        now_text = f"{now['task']} ({now['phrase']})"
        usual = f"Right now: {now_text}."
        if day["today"]:
            usual = f"Today is {day['today']}. " + usual
        usual += " Your usual day: " + "; ".join(day["sentences"]) + "."
    else:
        usual = ""
    card = {
        "name": name,
        "traits": "; ".join(own["self"].values()),
        "as_others_see": "; ".join(own["other"].values()),
        "life": " ".join(life_sketch(facts, pack)) if facts else "",
        "usual_day": usual,
        "ties": "; ".join(ties),
    }
    return {key: str(card[key]) for key in CARD_KEYS}
