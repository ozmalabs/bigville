"""narrate.py -- turns an agent view into sentences, with the pack's NARRATION templates (Phase 057).

Every line here is a template from `packs/<pack>/world/narration.json` filled with a phrase the view already
holds. Nothing reads the world, the game or a number. The functions take the view and return text lines, so
the renderer, the plain-mode transcript and the tests share one wording.
"""
from __future__ import annotations

from domains.interoception import render_felt_body
from domains.pack import load_pack

DEFAULT_PACK = "bigville"
LOOKS_PREFIX = "looks "
LOOKING_PREFIX = "looking "


def words(pack=DEFAULT_PACK):
    """The NARRATION table of the pack (plain dict; labels, templates and help lines)."""
    return load_pack(pack)["NARRATION"]


def _cap(text):
    text = str(text)
    return text[:1].upper() + text[1:]


def fill(key, pack=DEFAULT_PACK, **fields):
    """One template, filled. A missing field raises KeyError: the self-test keeps templates and fields aligned."""
    return words(pack)[key].format(**fields)


def status_line(view, pack=DEFAULT_PACK):
    """The status bar: time, season and weather, in words. Fields the view leaves out are left out."""
    now = view.get("now") or {}
    parts = [now[key] for key in ("time", "season", "weather") if now.get(key)]
    if len(parts) == 3:
        return fill("status", pack, time=now["time"], season=now["season"], weather=now["weather"])
    return ", ".join(parts)


def body_lines(view, pack=DEFAULT_PACK):
    """The body as the view carries it. The felt body (Phase 069: a background feeling and the signals, each a sound
    and a place) is rendered by domains/interoception; the labelled body (the Phase 052 words) keeps its one line each
    for energy, hunger, health and mood. Both give the states (asleep, collapsed, ill)."""
    body = (view.get("self") or {}).get("body") or {}
    lines = render_felt_body(body) if ("feeling" in body or "signals" in body) else []
    for key, template in (("energy", "energy"), ("hunger", "hunger"), ("health", "health"), ("mood", "mood")):
        if body.get(key):
            lines.append(fill(template, pack, **{key: body[key]}))
    for key in ("asleep", "collapsed", "ill"):
        if body.get(key):
            lines.append(_cap(body[key]) + ".")
    return lines


def looks_phrase(looks):
    """The other-perspective phrases of a person, joined: 'looks tired', 'looks gaunt' -> 'looking tired and gaunt'."""
    picked = [str(item) for item in looks][:2]
    out = []
    for index, phrase in enumerate(picked):
        if phrase.startswith(LOOKS_PREFIX):
            phrase = (LOOKING_PREFIX if index == 0 else "") + phrase[len(LOOKS_PREFIX):]
        out.append(phrase)
    return " and ".join(item for item in out if item)


def person_line(person, pack=DEFAULT_PACK):
    """One resident or stranger, in a sentence: 'Bram is right beside you, looking tired.'"""
    who = person.get("name") or person.get("description") or ""
    distance = person.get("distance") or ""
    looks = looks_phrase(person.get("looks") or [])
    if looks:
        return fill("person", pack, who=who, distance=distance, looks=looks)
    return fill("person_plain", pack, who=who, distance=distance)


def around_lines(view, pack=DEFAULT_PACK):
    """What the resident perceives: people, speech heard and moves seen, in sentences."""
    around = view.get("around") or {}
    lines = [_cap(person_line(person, pack)) for person in around.get("people") or []]
    for item in around.get("heard") or []:
        lines.append(fill("heard", pack, **{"from": item.get("from", ""), "text": item.get("text", "")}))
    for item in around.get("seen") or []:
        lines.append(_cap(fill("seen", pack, who=item.get("who", ""), did=item.get("did", ""))))
    # Phase 067: a written mark in sight, as the resident reads it (the view has the key only with reading on).
    for row in around.get("writing") or []:
        lines.append(_cap(load_pack(pack)["TUI_PROSE"]["writing"].format(text=row.get("percept", ""))))
    return lines


def outcome_lines(view, pack=DEFAULT_PACK):
    """The outcome of the last action: what it was, whether it happened, and why not (the refusal's description)."""
    last = view.get("last") or {}
    if not last:
        return []
    lines = [fill("last", pack, action=last.get("action", ""), outcome=_cap(last.get("outcome", "")))]
    if last.get("reason"):
        lines.append(fill("reason", pack, reason=last["reason"]))
    # Phase 071c: an attend, press or glance answers with a sound and a place (never a cause).
    if last.get("place"):
        silent = last.get("sound") in (None, "", load_pack(pack)["VIEW_WORDS"]["silence"])
        lines.append(fill("probe_silent" if silent else "probe", pack, place=last["place"],
                          sound=last.get("sound", "")))
    return lines


def reaction_lines(view, pack=DEFAULT_PACK):
    """The prompt for a contest the resident must answer (Phase 029): who takes what, and the answers."""
    reaction = view.get("reaction")
    if not reaction:
        return []
    who = reaction.get("from", "")
    what = reaction.get("what", "")
    if reaction.get("amount"):
        lead = fill("reaction_amount", pack, **{"from": who, "what": what, "amount": reaction["amount"]})
    else:
        lead = fill("reaction_intro", pack, **{"from": who, "what": what})
    lines = [lead]
    if reaction.get("late"):
        lines.append(_cap(reaction["late"]) + ".")
    lines.append(fill("reaction_pick", pack))
    return lines


def reaction_choices(view, pack=DEFAULT_PACK):
    """The numbered answers to a reaction: (number, choice name, words)."""
    reaction = view.get("reaction") or {}
    return [(index + 1, option["choice"], option["words"])
            for index, option in enumerate(reaction.get("options") or [])]


def menu_lines(view, pack=DEFAULT_PACK):
    """The numbered affordances (the view's `can` rows, in the world's order)."""
    return [fill("menu_item", pack, number=index + 1, what=_cap(row.get("what", "")))
            for index, row in enumerate(view.get("can") or [])]


def map_caption(view, pack=DEFAULT_PACK):
    """The words above the map: the view's caption, or the 'hidden' words when the view has no map."""
    level = (view.get("map") or {}).get("level")
    if level is None:
        return fill("map_hidden", pack)
    return _cap((view.get("map") or {}).get("caption", ""))


def legend_items(view, pack=DEFAULT_PACK):
    legend = (view.get("map") or {}).get("legend") or {}
    return [fill("legend_item", pack, glyph=glyph, word=word) for glyph, word in legend.items()]


ARRIVAL_PEOPLE = 6


def arrival_lines(view, pack=DEFAULT_PACK):
    """Everything a resident sees when they first look: the status, body, what is around and the menu. The
    people are the nearest few; the sheet's People tab lists them all."""
    lines = [status_line(view, pack)]
    lines += body_lines(view, pack)
    around = dict(view.get("around") or {})
    people = list(around.get("people") or [])
    lines += [_cap(person_line(person, pack)) for person in people[:ARRIVAL_PEOPLE]]
    if len(people) > ARRIVAL_PEOPLE:
        lines.append(words(pack)["more_people"])
    lines += around_lines({"around": {key: value for key, value in around.items() if key != "people"}}, pack)
    lines += outcome_lines(view, pack)
    lines += reaction_lines(view, pack)
    return [line for line in lines if line]


def help_lines(pack=DEFAULT_PACK):
    return list(words(pack)["help"])


def new_events(previous, view, pack=DEFAULT_PACK):
    """The speech heard and moves seen since the previous view, as sentences. The view lists what is perceived
    now, so an item is new when the previous view did not list it. The outcome of the last action is not here:
    outcome_lines gives it each turn."""
    old = previous or {}
    old_around = old.get("around") or {}
    around = view.get("around") or {}
    lines = []
    for item in around.get("heard") or []:
        if item not in (old_around.get("heard") or []):
            lines.append(fill("heard", pack, **{"from": item.get("from", ""), "text": item.get("text", "")}))
    for item in around.get("seen") or []:
        if item not in (old_around.get("seen") or []):
            lines.append(_cap(fill("seen", pack, who=item.get("who", ""), did=item.get("did", ""))))
    return lines
