"""agent_view.py -- the one limited interface (Phase 052).

`build_agent_view(game, actor, mode)` returns everything a resident may know, in words, built only from
the whitelist and the words in `world/agent_view.json` of the pack. The LLM prompt, the character sheet,
the terminal interface and any player client use this payload. The simple backends keep their raw
ActorContext, so this module is read-only for them.

    mode "agent"   words only. Every number is a lexicon phrase, and no referee-only field appears.
    mode "referee" the agent view plus a `referee` block with the raw numbers and the true state.

Sections (keys listed in AGENT_VIEW_WHITELIST): `self` (the persona card, the body in words, skills, what
is carried, what the resident knows and where, kin, notes), `now` (hour, season, weather), `around`
(people the resident can see, speech heard, moves seen), `map` (a patch of the ground within the sight
range, terrain only, for a simple resident; for a fogged resident, its own three-level map from
domains/map_memory.py: cells where it has seen them, labels for the places it holds, nothing for what it does
not know), `can` (the affordances the resident may use, by handle, verb and words, with moves only to places
the resident knows) and `last` (the outcome of the last major action).

The builder reads the world through its query methods only. It does not call `game._context`, because
that call advances the practice records a backend receives on its next context.
"""
from __future__ import annotations

import math
import re

from domains import impairment, map_memory, perceiver, reading
from domains.affordance_handles import handle_pairs
from domains.data_view import entities
from domains.lexicon import describe, quantities
from domains.pack import load_pack
from domains.persona import CARD_KEYS, traits as persona_traits

MODES = ("agent", "referee")
# Phase 069: how the body is shown. "felt" (the default in agent mode): the background feeling and the felt signals,
# sounds and places only. "labelled": the Phase 052 body words, kept for comparison. Referee mode shows "labelled"
# in `self.body` and carries the felt view and the truth in `referee.interoception`.
INTEROCEPTION_MODES = ("felt", "labelled")
# Phase 057: the detail levels a map can carry (Phase 053 supplies hidden and vague; the patch is full).
MAP_LEVEL_HIDDEN, MAP_LEVEL_VAGUE, MAP_LEVEL_FULL = "hidden", "vague", "full"
MAP_LEVELS = (MAP_LEVEL_HIDDEN, MAP_LEVEL_VAGUE, MAP_LEVEL_FULL)
NOTE_KINDS = ("note", "plan", "place_belief")
LESSON_KIND = "lesson"
NOTES_SHOWN = 10
_SPECIES_TAIL = re.compile(r"_\d+$")


def _words(name):
    """A machine name read as words: 'cold_store' -> 'cold store'."""
    return " ".join(str(name or "").replace("_", " ").split())


def _clean(mapping):
    """Drop the keys with no value (None or empty string). Lists and dicts stay, even when empty."""
    return {key: value for key, value in mapping.items() if value is not None and value != ""}


def _phrase(quantity, value, perspective, pack, what=None):
    """The words for a value, or None when the pack has no lexicon table for the quantity. A field with no words
    is left out of the view, so a number is never shown in its place."""
    if quantity not in quantities(pack):
        return None
    out = describe(quantity, value, perspective, pack=pack, what=what)
    return out["phrase"] if out else None


def _check_keys(section, mapping, pack):
    """Return `mapping` if each of its keys is whitelisted for `section`; otherwise raise. The builder is
    the only producer of the view, so a key outside the whitelist is a bug that must not reach a reader."""
    allowed = set(load_pack(pack)["AGENT_VIEW_WHITELIST"][section])
    extra = sorted(set(mapping) - allowed)
    if extra:
        raise ValueError(f"agent view section '{section}' has keys outside its whitelist: {extra}")
    return mapping


def _cell(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (int(value[0]), int(value[1]))
    return None


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _known_positions(character, pack):
    """Cells of places the resident knows exactly, mapped to the place's name. Only these are offered as moves."""
    out = {}
    for memory in character.memories:
        content = memory.content
        if (isinstance(content, dict) and content.get("type") == "place" and content.get("aware")
                and content.get("location") == "exact" and _cell(content.get("position"))):
            out[_cell(content["position"])] = _words(content.get("name"))
    return out


def _known_names(game, actor):
    """The residents this resident knows by name: an awareness record of them, a held tie, or a kin term."""
    world = game.world
    character = game.characters[actor]
    names = set()
    for memory in character.memories:
        content = memory.content
        if isinstance(content, dict) and content.get("type") == "resident" and content.get("aware"):
            names.add(str(content.get("name", "")))
    for holder, target in world._relationships:
        if holder == actor:
            names.add(str(target))
    for row in world.kin_terms_held(actor):
        if row["target"] in world._actors:
            names.add(str(row["target"]))
    names.discard("")
    return names


def _body(world, actor, pack):
    state = world.body_state(actor)
    attrs = world.eng.node(world._actors[actor])["attrs"]
    words = load_pack(pack)["VIEW_WORDS"]
    out = _clean({
        "health": _phrase("health", world.health(actor), "self", pack),
        "health_status": _phrase("health_status", str(attrs.get("health", "healthy")), "self", pack),
        "energy": _phrase("energy", world.energy(actor), "self", pack),
        "hunger": _phrase("hunger", float(attrs.get("hunger", 0.0)), "self", pack),
        "strength": _phrase("strength", state["strength"], "self", pack),
        "stamina": _phrase("stamina", state["stamina"], "self", pack),
        "mood": _phrase("mood", state["mood"], "self", pack),
        "asleep": words["asleep"] if state["asleep"] else None,
        "collapsed": words["collapsed"] if state["collapsed"] else None,
        "ill": words["ill"] if state["illness"] else None,
    })
    return _check_keys("body", out, pack)


def _felt_body(world, actor, pack):
    """The body as the resident feels it (Phase 069): the background feeling and the felt signals, from the body
    object (worlds/body.py), plus the plain capacities and facts the body reports. No cause, no number."""
    body = world.body_of(actor)
    if body is None:
        return _check_keys("body", {"signals": []}, pack)
    felt = body.afferents()
    words = load_pack(pack)["VIEW_WORDS"]
    capacities = body.capacities()
    facts = body.facts()
    out = {}
    if "feeling" in felt:
        out["feeling"] = _check_keys("feeling", dict(felt["feeling"]), pack)
    out["signals"] = [_check_keys("signal", dict(row), pack) for row in felt["signals"]]
    if "strength" in capacities:
        out["strength"] = _phrase("strength", capacities["strength"], "self", pack)
    if "stamina" in capacities:
        out["stamina"] = _phrase("stamina", capacities["stamina"], "self", pack)
    if facts.get("asleep"):
        out["asleep"] = words["asleep"]
    if facts.get("collapsed"):
        out["collapsed"] = words["collapsed"]
    return _check_keys("body", _clean(out), pack)


def _skills(world, actor, pack):
    out = []
    for skill, level in world.skill_levels(actor).items():
        phrase = _phrase("skill", float(level), "self", pack, what=_words(skill))
        if phrase:
            out.append(phrase)
    return sorted(out)


def _carrying(world, actor, pack):
    words = load_pack(pack)["VIEW_WORDS"]
    inventory = []
    for kind, qty in sorted(world.inventory(actor).items()):
        amount = _phrase("amount", float(qty), "self", pack) or ""
        inventory.append(words["carried_line"].format(item=_words(kind), amount=amount))
    held = []
    for item in world.held_items(actor):
        condition = _phrase("condition", float(item.get("condition", 1.0)), "self", pack) or ""
        held.append(words["held_line"].format(item=_words(item.get("kind")), condition=condition))
    ratio = world.carry_state(actor)["ratio"]
    load = _phrase("load", float(ratio), "self", pack) if math.isfinite(float(ratio)) else None
    out = _clean({"inventory": inventory, "held": sorted(held),
                  "worn": sorted(_words(kind) for kind in world.worn(actor)), "load": load})
    return _check_keys("carrying", out, pack)


def _knows(character, pack, gist_table):
    """What the resident is aware of or understands, with a gist and without the basis (the derived records
    carry a 'basis' of numbers and conditions, which the resident does not see)."""
    words = load_pack(pack)["VIEW_WORDS"]
    limit = int(load_pack(pack)["AGENT_VIEW_KNOWS_LIMIT"])
    rows = []
    for memory in character.memories:
        content = memory.content
        if not isinstance(content, dict) or not content.get("aware"):
            continue
        kind = str(content.get("type", ""))
        if not kind or kind == "place":
            continue
        name = str(content.get("name", ""))
        if not name:
            continue
        understood = float(content.get("understands", 0.0)) > 0.0
        shown = name if kind == "resident" else _words(name)
        rows.append((0 if understood else 1, kind, shown, {
            "name": shown,
            "understood": words["understood"] if understood else words["aware"],
            "gist": gist_table.get(kind, gist_table["default"]),
        }))
    rows.sort(key=lambda row: row[:3])
    seen, out = set(), []
    for row in rows:
        key = (row[1], row[2])
        if key in seen:
            continue
        seen.add(key)
        out.append(_check_keys("knows", row[3], pack))
        if len(out) >= limit:
            break
    return out


def _places(character, pack):
    precision = load_pack(pack)["PRECISION_WORDS"]
    rows = set()
    for memory in character.memories:
        content = memory.content
        if isinstance(content, dict) and content.get("type") == "place" and content.get("aware"):
            phrase = precision.get(str(content.get("location", "none")))
            if phrase:
                rows.add((_words(content.get("name")), phrase))
    return [_check_keys("places", {"name": name, "precision": phrase}, pack)
            for name, phrase in sorted(rows)]


def _kin(world, actor, pack):
    words = load_pack(pack)["VIEW_WORDS"]
    rows = set()
    for row in world.kin_terms_held(actor):
        target = str(row["target"])
        who = target if target in world._actors else words["unknown_kin"]
        rows.add(words["kin_line"].format(term=_words(row["term"]), who=who))
    return sorted(rows)


def _texts(character, kinds):
    return [memory.content["text"] for memory in character.memories
            if memory.kind in kinds and isinstance(memory.content, dict)
            and isinstance(memory.content.get("text"), str)]


def _notes(character):
    """The most recent notes, plans and place beliefs the resident wrote (Phase 054: lessons are listed apart)."""
    return _texts(character, NOTE_KINDS)[-NOTES_SHOWN:]


def _lessons(character):
    """Every lesson the resident has written down, oldest first. The prompt packet applies the cap (Phase 054)."""
    return _texts(character, (LESSON_KIND,))


def _self(game, actor, pack, gist_table, interoception="labelled"):
    world = game.world
    character = game.characters[actor]
    attrs = world.eng.node(world._actors[actor])["attrs"]
    age = float(attrs.get("age", character.identity.get("age") or 0.0))
    stage = str(attrs.get("life_stage") or character.identity.get("life_stage") or "adult")
    out = _clean({
        "name": actor,
        "job": _words(attrs.get("role")),
        "life_stage": _phrase("life_stage", stage, "self", pack),
        "age": _phrase("age", age, "self", pack),
        "persona": _check_keys("persona", {key: value for key, value in game.persona(actor).items()
                                           if key in CARD_KEYS}, pack),
        "body": _body(world, actor, pack) if interoception == "labelled" else _felt_body(world, actor, pack),
        "skills": _skills(world, actor, pack),
        "carrying": _carrying(world, actor, pack),
        "knows": _knows(character, pack, gist_table),
        "places": _places(character, pack),
        "kin": _kin(world, actor, pack),
        "notes": _notes(character),
        "lessons": _lessons(character),
    })
    return _check_keys("self", out, pack)


def _daylight(world, actor, pack):
    """The light the resident sees, in words (Phase 042). None when day and night is off."""
    from worlds import daynight as _dn
    key = _dn.view_light(world, actor)
    return _phrase("daylight", key, "self", pack) if key else None


def _now(world, pack, actor=None):
    clock = world.calendar()
    out = _clean({
        "time": _phrase("hour", float(clock["hour"]), "self", pack) if clock.get("hour") is not None else None,
        "season": _phrase("season", clock["season"], "self", pack) if clock.get("season") else None,
        "weather": _phrase("weather", clock["weather"], "self", pack) if clock.get("weather") else None,
        "light": _daylight(world, actor, pack),
    })
    return _check_keys("now", out, pack)


def _looks(game, other, pack):
    """What an observer can see of `other`: the other-perspective traits and body words."""
    world = game.world
    attrs = world.eng.node(world._actors[other])["attrs"]
    character = game.characters.get(other)
    looks = []
    if character is not None:
        looks += sorted(persona_traits(character.personality, character.identity, pack)["other"].values())
    state = world.body_state(other)
    for phrase in (_phrase("health_status", str(attrs.get("health", "healthy")), "other", pack),
                   _phrase("hunger", float(attrs.get("hunger", 0.0)), "other", pack),
                   _phrase("energy", world.energy(other), "other", pack),
                   _phrase("mood", state["mood"], "other", pack)):
        if phrase:
            looks.append(phrase)
    return looks


def _around(game, actor, pack, known, rec=None, log=None):
    """The people, speech, moves and things around the resident. `rec` is the perceiver record (Phase 062); given,
    people and things are described by their percept, and each percept is appended to `log` (the referee block)."""
    world = game.world
    words = load_pack(pack)["VIEW_WORDS"]
    log = [] if log is None else log
    sight = int(load_pack(pack)["HEARING"]["sight_range"]) if rec is None else int(rec["sight"])
    position = world.actor_position(actor)
    ties = {str(target): world.eng.node(bond)["attrs"].get("kind")
            for (holder, target), bond in world._relationships.items() if holder == actor}
    nearby = []
    if position is not None:
        for other in world._actors:
            if other == actor or not world.is_alive(other):
                continue
            other_position = world.actor_position(other)
            if other_position is None:
                continue
            distance = _chebyshev(position, other_position)
            if distance <= sight:
                nearby.append((distance, other))
    people = []
    for distance, other in sorted(nearby):
        role = _words(world.eng.node(world._actors[other])["attrs"].get("role"))
        if rec is not None:
            # Phase 062: the percept decides what is seen. Looks need a tier of 1 or more (some light to see by), and a
            # resident is known by name only at that tier too; otherwise it is described by the percept's words.
            subject = perceiver.person_subject(game, other, pack)
            seen = perceiver.percept("person", subject, distance, rec, pack)
            # Phase 065: an impaired resident may be given a wrong percept; the truth stays in the referee row.
            seen = impairment.distort(game, actor, "person", other, subject, seen, rec, pack,
                                      others=[name for _d, name in nearby if name != other], known=known)
            log.append({**perceiver.referee_row(other, "person", distance, seen), **impairment.referee_extra(seen)})
            identity = seen.get("as", other)
            recognised = identity in known and seen["tier"] >= 1
            entry = {"distance": _phrase("distance", distance, "self", pack)}
            if seen["tier"] >= 1:
                entry["looks"] = _looks(game, other, pack)
            if recognised:
                entry["name"] = identity
                entry["job"] = seen.get("as_job", role)
            else:
                entry["description"] = seen["words"]
            if recognised and ties.get(other) and "as" not in seen:
                entry["tie"] = _phrase("relationship_kind", str(ties[other]), "self", pack)
            people.append(_check_keys("person", _clean(entry), pack))
            continue
        entry = {"distance": _phrase("distance", distance, "self", pack), "looks": _looks(game, other, pack)}
        if other in known:
            entry["name"] = other
            entry["job"] = role
        else:
            entry["description"] = words["stranger"].format(job=role)
        if ties.get(other):
            entry["tie"] = _phrase("relationship_kind", str(ties[other]), "self", pack)
        people.append(_check_keys("person", _clean(entry), pack))
    heard = []
    for record in world.heard_utterances(actor):
        speaker = str(record.get("speaker", ""))
        heard.append(_check_keys("heard", {"from": speaker if speaker in known else words["someone"],
                                           "text": str(record.get("text", ""))}, pack))
    seen = []
    for event in game._physical_events.get(actor, []):
        if event.get("action") != "moved_object":
            continue
        who = str(event.get("actor", ""))
        who = words["you"] if who == actor else (who if who in known else words["someone"])
        seen.append(_check_keys("seen", {"who": who, "did": words["moved"]}, pack))
    things = _things(world, actor, pack, rec, log, game)
    around = {"people": people, "heard": heard, "seen": seen, "things": things}
    # Phase 064: written marks in sight, read at the resident's literacy (off unless READING.enabled).
    writing = reading.writing_rows(game, actor, rec, pack, log) if rec is not None else None
    if writing:
        around["writing"] = writing
    return _check_keys("around", around, pack)


def _things(world, actor, pack, rec=None, log=None, game=None):
    """What the resident can act on: containers on the resident's own cell (an attempt needs the resident
    there), and the physical objects the resident can see. A handle is the name the world uses for the thing,
    copied into a reply; `what` is its kind in words (Phase 054).

    With a perceiver record (Phase 062) a thing is described by its percept. A thing seen at tier 0 is 'something'
    with no handle, so the resident cannot name it in a reply."""
    position = world.actor_position(actor)
    rows = []
    if position is not None:
        for name in sorted(world._containers, key=str):
            node = world._containers[name][0]
            if world.container_position(name) != position:
                continue
            if float(world.eng.node(node)["attrs"].get("destroyed", 0.0)) == 1.0:
                continue
            rows.append((str(name), _words(world.eng.node(node)["attrs"].get("kind") or name), 0))
    for item in world.physical_object_observations(actor):
        distance = 0
        if rec is not None and position is not None:
            cell = world._physical_location_cell(item.get("id"))
            distance = _chebyshev(position, cell) if cell is not None else 0
        rows.append((str(item.get("id", "")), _words(item.get("kind") or item.get("id")), distance))
    if rec is None:
        return [_check_keys("thing", {"handle": handle, "what": what}, pack)
                for handle, what, _distance in rows if handle]
    out = []
    for handle, what, distance in rows:
        if not handle:
            continue
        subject = perceiver.thing_subject(what)
        seen = perceiver.percept("thing", subject, distance, rec, pack)
        # Phase 065: an impaired resident may be given a wrong percept; the truth stays in the referee row.
        seen = impairment.distort(game, actor, "thing", handle, subject, seen, rec, pack,
                                  others=[(h, w) for h, w, _d in rows if h and h != handle])
        log.append({**perceiver.referee_row(handle, "thing", distance, seen), **impairment.referee_extra(seen)})
        if seen["tier"] == 0:
            out.append(_check_keys("thing", {"what": seen["words"]}, pack))
        else:
            out.append(_check_keys("thing", {"handle": handle, "what": seen["words"]}, pack))
    return out


def _map(world, actor, pack):
    glyphs = load_pack(pack)["MAP_GLYPHS"]
    sight = int(load_pack(pack)["HEARING"]["sight_range"])
    position = world.actor_position(actor)
    if position is None:
        return None
    rows, used = [], {}
    for dy in range(-sight, sight + 1):
        line = []
        for dx in range(-sight, sight + 1):
            if dx == 0 and dy == 0:
                key = "player"
            else:
                terrain = str(world.terrain_state((position[0] + dx, position[1] + dy))["terrain"])
                key = terrain if terrain in glyphs and not terrain.startswith("_") else "unknown"
            used[glyphs[key]["glyph"]] = glyphs[key]["word"]
            line.append(glyphs[key]["glyph"])
        rows.append("".join(line))
    # Phase 057: `level` is the word key of the map's detail (MAP_LEVELS); the renderer dispatches on it. The
    # patch is cell detail, so it is "full". `caption` is the phrase the view shows above it.
    return _check_keys("map", {"level": MAP_LEVEL_FULL, "caption": load_pack(pack)["VIEW_WORDS"]["map_level"],
                               "rows": rows, "legend": dict(sorted(used.items()))}, pack)


def _fogged_map(game, actor, pack):
    """The map section of a fogged resident (Phase 053): its three levels, from the resident's own map."""
    section = map_memory.map_section(game, actor)
    if section is None:
        return None
    labels = [_check_keys("label", label, pack) for label in section["labels"]]
    return _check_keys("map", {**section, "labels": labels}, pack)


def _species(world, animal):
    if not animal or animal not in world._animals:
        return ""
    return str(world.eng.node(world._animals[animal])["attrs"].get("species", ""))


def _can(world, actor, character, pack, game=None, withheld=()):
    """The options the resident may use. Each row's handle comes from domains/affordance_handles.py, computed
    over the full list of the world's options, so the backend resolves the same handle to the same row (Phase
    054 follow-up). A move is listed only to a place the resident knows.

    A fogged resident (`game` given, Phase 053) gets only the rows whose cell it knows: a place it holds exactly
    is named ('walk to the mill'), one it holds roughly is offered as 'walk toward the mill', and a cell it has
    seen is 'a spot you know'. A row to ground it does not know is not listed.

    `withheld` (Phase 062) names the things the resident cannot see at all; a row that acts on one of them is left out."""
    pk = load_pack(pack)
    actions, words = pk["ACTION_WORDS"], pk["VIEW_WORDS"]
    fogged = game is not None and map_memory.is_fogged(game, actor)
    places = {} if fogged else _known_positions(character, pack)
    out = []
    offered_moves = set()
    for handle, option in handle_pairs(world.actor_affordances(actor)):
        action = str(option.get("action", ""))
        if withheld and str(option.get("target", "")) in withheld:
            continue
        verb = actions.get(action) or _words(action)
        destination = _cell(option.get("destination"))
        wording = None
        if fogged and destination is not None:
            wording = map_memory.can_words(game, actor, destination, trade=option.get("trade"))
            if wording is None:
                continue
        if action == "move":
            if fogged:
                if wording is None:
                    continue
                kind, place = wording
                if kind == "to":
                    what = words["walk_to"].format(place=place)
                elif kind == "toward":
                    what = words["walk_toward"].format(place=place)
                else:
                    what = pk["FOG_WORDS"]["spot"]
                # Several cells of one vague place (every field) are one way to walk there: the first row stands for
                # them. An exact place keeps each of its rows, as before Phase 053.
                if kind != "to" and what in offered_moves:
                    continue
                offered_moves.add(what)
            else:
                if destination not in places:
                    continue
                name = _words(option.get("trade")) or places[destination]
                what = words["walk_to"].format(place=name)
        else:
            what = _words(option.get("recipe") or option.get("kind") or option.get("sow_kind")
                          or _species(world, option.get("animal")))
        out.append(_check_keys("can", {"handle": handle, "action": verb, "what": what}, pack))
    return out


def _attend_can(world, actor, pack):
    """Phase 071: one `can` row per felt signal the resident may attend to (handle signal:N, see worlds/body.py).
    The row names the place the feeling is in, never its cause. Only a human body offers these rows."""
    body = world.body_of(actor)
    if body is None:
        return []
    verb = load_pack(pack)["ACTION_WORDS"].get("attend", "attend")
    return [_check_keys("can", {"handle": row["target"], "action": verb, "what": str(row["where"])}, pack)
            for row in body.attend_options()]


def _last(world, actor, pack):
    outcome = world.last_outcome(actor)
    if not outcome:
        return {}
    pk = load_pack(pack)
    code = str(outcome.get("reason", ""))
    reason = ""
    if not outcome.get("applied"):
        described = pk["REFUSAL_REASONS"].get(code)
        reason = described["description"] if described else _words(code)
    action = str(outcome.get("action", ""))
    out = _clean({"action": pk["ACTION_WORDS"].get(action) or _words(action),
                  "outcome": pk["VIEW_WORDS"]["done" if outcome.get("applied") else "not_done"],
                  "reason": reason})
    # Phase 071: an attend or press that was done shows the sound and the place it gave, and nothing about a cause.
    body = world.body_of(actor) if action in ("attend", "press") and outcome.get("applied") else None
    probe = None if body is None else body.state.get("probe")
    if probe and probe.get("action") == action and probe.get("turn") == outcome.get("turn"):
        out["sound"] = probe.get("sound") or pk["VIEW_WORDS"]["silence"]
        out["place"] = str(probe.get("where", ""))
    return _check_keys("last", out, pack)


def _referee(game, actor):
    """The raw numbers and the true state. Only the referee mode carries this block."""
    world = game.world
    body = world.body_of(actor)
    nearby = []
    position = world.actor_position(actor)
    for other in world._actors:
        if other == actor or position is None or world.actor_position(other) is None:
            continue
        attrs = world.eng.node(world._actors[other])["attrs"]
        nearby.append({"name": other, "position": list(world.actor_position(other)),
                       "distance": _chebyshev(position, world.actor_position(other)),
                       "klass": attrs.get("klass", ""), "group": attrs.get("group", "")})
    skills = world.skill_levels(actor)
    return {"body": world.body_state(actor), "calendar": world.calendar(),
            "carry": world.carry_state(actor), "skills": skills,
            "affordances": [dict(option) for option in world.actor_affordances(actor)],
            "nearby": sorted(nearby, key=lambda row: (row["distance"], row["name"])),
            # Phase 069: the body's truth beside the felt view (each signal's true source, locus and depths).
            "interoception": None if body is None else body.referee()}


def _reaction(game, actor, pack, known):
    """The contest the resident must answer (Phase 029): who takes what, and the reactions the world offers.
    Present only while the resident is the holder of a pending take whose offer is eligible, so the prompt
    carries the same options the world will accept (a reply outside them is treated as no reaction)."""
    world = game.world
    pending = world.contest_pending()
    if not pending or str(pending.get("target")) != actor:
        return None
    offer = pending["offer"]
    if not offer.get("eligible"):
        return None
    words = load_pack(pack)["VIEW_WORDS"]
    if pending.get("kind_is_item"):
        what = _words(world.eng.node(pending["kind"])["attrs"].get("kind"))
    else:
        what = _words(pending["kind"])
    options = []
    for option in offer["options"]:
        if f"react_{option}" not in words:
            raise KeyError(f"VIEW_WORDS has no react_{option}: the reaction '{option}' has no words")
        options.append(_check_keys("option", {"choice": str(option), "words": words[f"react_{option}"]}, pack))
    attacker = str(pending["attacker"])
    return _check_keys("reaction", _clean({
        "from": attacker if attacker in known else words["someone"],
        "what": what,
        "amount": _phrase("amount", float(pending["amount"]), "self", pack),
        "late": words["reaction_late"] if offer.get("late") else None,
        "options": options,
    }), pack)


# ---------------------------------------------------------------- lazy view (LA05)
# The lazy view publishes entities and capabilities, never the world's exhaustive legal menu. It is built
# from `world.observe(actor)` and the helpers above that do not call `actor_affordances()`. The explicit menu
# remains the agent view (`build_agent_view`) for the UI, debugging and Ocelot; the LLM context in lazy mode
# uses this view instead.

LAZY_THINGS_CAP = 12
LAZY_PLACES_CAP = 8
LAZY_PEOPLE_CAP = 8
LAZY_SEEN_CAP = 20
LAZY_CAN_CAP = 28
LAZY_KNOWS_CAP = 24


def _capability(pack, action, what):
    """One bounded capability row in the existing `can` shape. The handle is empty: the resident acts by
    naming direct params, not by copying a per-option handle. `action` is the view word where the pack has one."""
    verb = load_pack(pack)["ACTION_WORDS"].get(action) or _words(action)
    return _check_keys("can", {"handle": "", "action": verb, "what": what}, pack)


def _open_container(container):
    return bool(container.get("open")) and not bool(container.get("locked"))


def _lazy_destinations(obs):
    """A bounded set of stable place handles: named places, nearby building/site/farm cells and the adjacent
    ground. The handle is a cell (`cell:x,y`), not an ephemeral target key; `_fold_action` in reply_schema turns
    a move's cell handle into `params.destination`."""
    position = _cell(obs.get("position"))
    places = obs.get("places") or {}
    cell = obs.get("cell") or {}
    candidates = []

    def add(cell_value, label, priority):
        destination = _cell(cell_value)
        if destination is None or (position is not None and destination == position):
            return
        distance = _chebyshev(position, destination) if position is not None else 0
        candidates.append((priority, distance, _words(label), destination))

    add(places.get("home"), "home", 0)
    add(places.get("work"), "work", 0)
    add(places.get("market"), "the market", 0)
    for building in places.get("buildings") or []:
        add(building.get("cell"), building.get("name") or building.get("kind") or "a building", 1)
    for site in places.get("gathering_sites") or []:
        add(site.get("cell"), site.get("kind") or "a gathering site", 1)
    for farm in places.get("farms") or []:
        add(farm.get("cell"), farm.get("use") or "a field", 2)
    if position is not None:
        for exit_cell in cell.get("exits") or []:
            destination = _cell(exit_cell)
            if destination is None:
                continue
            dx, dy = destination[0] - position[0], destination[1] - position[1]
            direction = ("north" if dy < 0 else "south") if dx == 0 else ("west" if dx < 0 else "east")
            add(destination, "the ground to the " + direction, 3)
    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    rows, used = [], set()
    for _, _, label, destination in candidates:
        handle = f"cell:{destination[0]},{destination[1]}"
        if handle in used:
            continue
        used.add(handle)
        rows.append((handle, label))
        if len(rows) >= LAZY_PLACES_CAP:
            break
    return rows


def _lazy_things(obs, pack):
    """Visible objects, reachable containers and a bounded set of place handles, with stable ids."""
    rows, used = [], set()
    for item in list(obs.get("visible_objects") or []) + list(obs.get("containers_in_reach") or []):
        handle = str(item.get("id") or "")
        if not handle or handle in used:
            continue
        used.add(handle)
        what = _words(item.get("kind") or item.get("name") or handle)
        if item.get("container"):
            what += " (open)" if item.get("open") and not item.get("locked") else " (closed)"
        rows.append(_check_keys("thing", {"handle": handle, "what": what}, pack))
        if len(rows) >= LAZY_THINGS_CAP:
            break
    for handle, label in _lazy_destinations(obs):
        if handle in used or len(rows) >= LAZY_THINGS_CAP + LAZY_PLACES_CAP:
            continue
        used.add(handle)
        rows.append(_check_keys("thing", {"handle": handle, "what": label}, pack))
    return rows


def _lazy_people(game, actor, obs, pack):
    """Nearby residents from the observation: stable names, distance words, role and cheap looks. A stranger
    keeps the view's stranger wording; a resident the actor knows is named."""
    world = game.world
    words = load_pack(pack)["VIEW_WORDS"]
    known = _known_names(game, actor)
    rows = []
    nearby = sorted((obs.get("nearby_actors") or []),
                    key=lambda row: (row.get("distance", 1_000), str(row.get("id") or "")))
    for row in nearby[:LAZY_PEOPLE_CAP]:
        other = str(row.get("id") or "")
        if not other or other not in world._actors:
            continue
        role = _words(row.get("role"))
        entry = {"distance": _phrase("distance", float(row.get("distance") or 0), "self", pack),
                 "looks": _looks(game, other, pack)}
        if other in known:
            entry["name"] = other
            entry["job"] = role
        else:
            entry["description"] = words["stranger"].format(job=role or words["someone"])
        rows.append(_check_keys("person", _clean(entry), pack))
    return rows


def _lazy_seen(game, actor, obs, pack, known=None):
    """What is here and what places the resident knows: cell features, named places and witnessed moves. The
    `seen` whitelist has only `who` and `did`, so a feature reads as its name and the short phrase that says
    how it stands to the resident ("is here", "you know where it is")."""
    words = load_pack(pack)["VIEW_WORDS"]
    precision = load_pack(pack)["PRECISION_WORDS"]
    known = _known_names(game, actor) if known is None else known
    cell = obs.get("cell") or {}
    places = obs.get("places") or {}
    rows = []

    def add(who, did):
        name = _words(who)
        if name:
            rows.append(_check_keys("seen", {"who": name, "did": did}, pack))

    for building in cell.get("buildings") or []:
        add(building.get("name") or building.get("kind"), "is here")
    for land in cell.get("land") or []:
        add(land.get("use") or land.get("kind") or "a field", "is here")
    for site in cell.get("gathering_sites") or []:
        add(site.get("kind") or "a gathering site", "is here")
    for fixture in cell.get("fixtures") or []:
        add(fixture.get("kind") or fixture.get("name") or "a fixture", "is here")
    for shop in cell.get("shops") or []:
        add(shop.get("trade") or "a shop", "trades here")
    for project in cell.get("building_projects") or []:
        add(project.get("name") or project.get("project") or "a building project", "is being built here")
    for work in cell.get("infrastructure") or []:
        add(work.get("kind") or "the town works", "stands here")
    for animal in cell.get("animals") or []:
        if animal.get("alive", True):
            add(animal.get("species") or animal.get("name") or "an animal", "is here")
    for crop in cell.get("crops") or []:
        add(crop.get("kind") or "a crop", "grows here")
    for building in places.get("buildings") or []:
        add(building.get("name") or building.get("kind"), precision.get("exact"))
    for site in places.get("gathering_sites") or []:
        add(site.get("kind"), precision.get("exact"))
    for place, label in (("home", "home"), ("work", "work"), ("market", "the market")):
        if places.get(place):
            add(label, precision.get("exact"))
    for farm in places.get("farms") or []:
        add(farm.get("use") or "a field", precision.get("exact"))
    # Physical moves the resident witnessed, as before Phase 052.
    for event in game._physical_events.get(actor, []):
        if event.get("action") != "moved_object":
            continue
        who = str(event.get("actor", ""))
        who = words["you"] if who == actor else (who if who in known else words["someone"])
        rows.append(_check_keys("seen", {"who": who, "did": words["moved"]}, pack))
    return rows[:LAZY_SEEN_CAP]


def _lazy_self(game, actor, pack, gist_table, obs):
    """The persona/self card plus the bounded recipe knowledge the observation publishes. Recipes go in
    `self.knows` in the existing (name, understood, gist) shape, so the model can name a recipe in params."""
    out = dict(_self(game, actor, pack, gist_table))
    words = load_pack(pack)["VIEW_WORDS"]
    rows = list(out.get("knows") or [])
    names = {str(row.get("name", "")) for row in rows}
    job_recipe = str((obs.get("job") or {}).get("recipe") or "")
    recipes = [job_recipe] if job_recipe else []
    recipes += [str(name) for name in (obs.get("known_recipes") or []) if str(name) != job_recipe]
    added = 0
    for recipe in recipes:
        label = _words(recipe)
        if not label or label in names:
            continue
        rows.append(_check_keys("knows", {"name": label, "understood": words["understood"],
                                          "gist": "a recipe you can attempt"}, pack))
        names.add(label)
        added += 1
        if added >= LAZY_KNOWS_CAP:
            break
    out["knows"] = rows
    return _check_keys("self", out, pack)


def _lazy_can(game, actor, obs, pack):
    """A bounded capability list derived from the observation. It says what the resident is able to do now,
    not every legal target: the entities those capabilities act on are in `around.things` and the resident's
    own carrying. The world still validates every proposal."""
    cell = obs.get("cell") or {}
    inventory = list(obs.get("inventory_details") or [])
    nearby = list(obs.get("nearby_actors") or [])
    visible = list(obs.get("visible_objects") or [])
    containers = list(obs.get("containers_in_reach") or [])
    open_containers = [item for item in containers if _open_container(item)]
    has_food = any(item.get("edible") for item in inventory) or \
        any(item.get("edible") and item.get("reachable") for item in visible)
    co_located = [row for row in nearby if float(row.get("distance") or 0) == 0]
    patients = [row for row in nearby
                if str(row.get("health") or "") not in {"", "healthy"} or float(row.get("injury") or 0) > 0]
    rows = []

    def add(action, what):
        rows.append(_capability(pack, action, what))

    if has_food:
        add("eat", "food you can reach")
    add("rest", "rest a while")
    add("sleep", "lie down and sleep")
    add("move", "walk to a place you know" if _lazy_destinations(obs) else "walk to the ground nearby")
    if obs.get("known_recipes") or obs.get("job"):
        add("work", "work at a recipe you know")
    if inventory and co_located:
        add("give", "hand something you carry to someone here")
    if any(_open_container(item) and item.get("contents") for item in containers):
        add("fetch", "fetch goods from a container in reach")
    if inventory and open_containers:
        add("put", "put something you carry into a container in reach")
    if any(item.get("grabbable") for item in visible):
        add("move_object", "move something you can see")
    if visible:
        add("attempt", "try a physical verb on something in reach")
    if any(animal.get("alive", True) for animal in cell.get("animals") or []):
        add("tend_animals", "tend an animal here")
    if any(crop.get("thirst") for crop in cell.get("crops") or []):
        add("water", "water a crop here")
    if any(crop.get("mature") for crop in cell.get("crops") or []):
        add("harvest", "harvest a crop here")
    if cell.get("land"):
        add("sow", "sow a crop on the land here")
        add("fertilise", "fertilise the land here")
    if cell.get("building_projects"):
        add("build", "work on a building project here")
    if cell.get("infrastructure"):
        add("maintain", "maintain the town works here")
    if patients:
        add("care", "care for someone ill or hurt here")
    if obs.get("held"):
        add("struggle", "struggle free")
    if obs.get("holding"):
        add("release", "let go of the person you hold")
    if any(item.get("container") and item.get("locked") for item in visible + containers):
        add("unlock", "unlock a container in reach")
    if any(item.get("container") and not item.get("locked") for item in visible + containers):
        add("lock", "lock a container in reach")
    if co_located:
        add("take", "take something from someone here")
        add("strike", "strike someone here")
        add("restrain", "take hold of someone here")
    if visible or any(item.get("edible") for item in inventory):
        add("throw", "throw something you hold")
    # A stable order, deduplicated by action and what; needs and local features come first.
    seen, out = set(), []
    for row in rows:
        key = (row["action"], row["what"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:LAZY_CAN_CAP]


def _lazy_referee(game, actor, obs):
    """The referee block for the lazy view: numbers and true state, but no `affordances` field. Asking for the
    menu here would put the exhaustive list back on the lazy path; callers that need it use `build_agent_view`."""
    world = game.world
    nearby = []
    position = world.actor_position(actor)
    for other in world._actors:
        if other == actor or position is None or world.actor_position(other) is None:
            continue
        attrs = world.eng.node(world._actors[other])["attrs"]
        nearby.append({"name": other, "position": list(world.actor_position(other)),
                       "distance": _chebyshev(position, world.actor_position(other)),
                       "klass": attrs.get("klass", ""), "group": attrs.get("group", "")})
    return {"body": world.body_state(actor), "calendar": world.calendar(),
            "carry": world.carry_state(actor), "skills": world.skill_levels(actor),
            "nearby": sorted(nearby, key=lambda row: (row["distance"], row["name"]))}


def build_lazy_agent_view(game, actor, mode="agent"):
    """The lazy agent view: entities and bounded capabilities from `world.observe(actor)`.

    It NEVER calls `actor_affordances()` / `_actor_options()`. `can` rows are capabilities in the existing
    (handle, action, what) shape with an empty handle; the model proposes direct params, and the world validates
    them. `mode="referee"` adds the raw numbers but deliberately leaves out the menu's `affordances` field."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    if actor not in game.characters:
        raise KeyError(f"no resident named {actor!r}")
    world = game.world
    pack = world.data_pack
    gist = entities(pack).MEMORY_GIST
    obs = world.observe(actor)
    cell = obs.get("cell") or {}
    heard = []
    known = _known_names(game, actor)
    words = load_pack(pack)["VIEW_WORDS"]
    for record in (obs.get("heard") or [])[-10:]:
        speaker = str(record.get("speaker", ""))
        heard.append(_check_keys("heard", {"from": speaker if speaker in known else words["someone"],
                                           "text": str(record.get("text", ""))}, pack))
    around = _check_keys("around", {
        "people": _lazy_people(game, actor, obs, pack),
        "heard": heard,
        "seen": _lazy_seen(game, actor, obs, pack, known),
        "things": _lazy_things(obs, pack),
    }, pack)
    fogged = map_memory.is_fogged(game, actor)
    view = {
        "mode": mode,
        "actor": actor,
        "self": _lazy_self(game, actor, pack, gist, obs),
        "now": _now(world, pack, actor),
        "around": around,
        # Phase 053: a fogged resident's map is its own; a simple resident keeps the patch.
        "map": _fogged_map(game, actor, pack) if fogged else _map(world, actor, pack),
        "can": _lazy_can(game, actor, obs, pack),
        "last": _last(world, actor, pack),
        "reaction": _reaction(game, actor, pack, known),
    }
    if mode == "referee":
        view["referee"] = _lazy_referee(game, actor, obs)
        if fogged:
            view["referee"]["true_map"] = map_memory.true_patch(game, actor)
    return _check_keys("top", _clean(view), pack)


def build_agent_view(game, actor, mode="agent", interoception=None):
    """The agent view of one resident. `mode` is "agent" (words only) or "referee" (adds the numbers).
    `interoception` is "felt" or "labelled" (Phase 069); None means felt in agent mode and labelled in referee mode."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    if interoception is None:
        interoception = "felt" if mode == "agent" else "labelled"
    if interoception not in INTEROCEPTION_MODES:
        raise ValueError(f"interoception must be one of {INTEROCEPTION_MODES}, not {interoception!r}")
    if actor not in game.characters:
        raise KeyError(f"no resident named {actor!r}")
    world = game.world
    pack = world.data_pack
    gist = entities(pack).MEMORY_GIST
    known = _known_names(game, actor)
    fogged = map_memory.is_fogged(game, actor)
    # Phase 062: the perceiver record, when PERCEPTION.enabled is on. Off, nothing below changes.
    rec = None
    if perceiver.enabled(pack):
        rec = perceiver.record(game, actor, perceiver.declared(getattr(game, "backends", {}).get(actor), pack), pack)
    log = []
    around = _around(game, actor, pack, known, rec, log)
    # Phase 065: remember the subjects shown wrongly this turn (the ledger of actions on a wrong percept).
    impairment.note_view(game, actor, rec, log, pack)
    # Phase 062: a thing the resident cannot see at all (tier 0) is not offered as an option either.
    withheld = {row["subject"] for row in log if row["kind"] == "thing" and row["tier"] == 0}
    view = {
        "mode": mode,
        "actor": actor,
        "self": _self(game, actor, pack, gist, interoception),
        "now": _now(world, pack, actor),
        "around": around,
        # Phase 053: a fogged resident's map is its own three-level map; a simple resident keeps the patch.
        "map": _fogged_map(game, actor, pack) if fogged else _map(world, actor, pack),
        "can": _can(world, actor, game.characters[actor], pack, game if fogged else None, withheld)
        + _attend_can(world, actor, pack),   # Phase 071
        "last": _last(world, actor, pack),
        "reaction": _reaction(game, actor, pack, known),
    }
    if mode == "referee":
        view["referee"] = _referee(game, actor)
        if fogged:
            view["referee"]["true_map"] = map_memory.true_patch(game, actor)
        if rec is not None:
            view["referee"]["perception"] = {"faculties": dict(rec["modes"]), "perceiver": perceiver.summary(rec),
                                             "subjects": log, **impairment.referee_block(game, log, pack)}
    return _check_keys("top", _clean(view), pack)
