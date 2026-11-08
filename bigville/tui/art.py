"""art.py -- the map mode's art (Phase 067). Presentation only: every glyph and tile comes from TUI_ART in the pack,
and every word from TUI_PROSE. The map itself is the agent view's map (terrain only, by the view's rule), so the art
never places a person or a thing on the map: a person is a glyph beside its one-line label in the People tab and the
legend, and a thing is listed the same way.

    tiled(view, pack)           the view with each map row drawn as two-character tiles (the view is not changed)
    mark_people(view, pack, lines)  the People tab's lines with a person glyph in front of each person's line
    legend_items(view, pack)    'glyph words' items for the people and things the view names, for the legend line

The colours in TUI_ART are not drawn by the plain screen (a limit of Phase 067, see the report).
"""
from __future__ import annotations

from domains.pack import load_pack


def _art(pack):
    return load_pack(pack)["TUI_ART"]


def tile(glyph, pack="bigville"):
    """The two-character tile for a map glyph. A glyph with no tile is drawn doubled (the self-test finds it)."""
    row = _art(pack)["tiles"].get(glyph)
    return row["tile"] if row else str(glyph) * 2


def tiled(view, pack="bigville"):
    """A copy of the view whose map rows are tiles. A view with no map (or no rows) is returned as it is."""
    game_map = view.get("map")
    if not game_map or not game_map.get("rows"):
        return view
    rows = ["".join(tile(glyph, pack) for glyph in str(row)) for row in game_map["rows"]]
    return {**view, "map": {**game_map, "rows": rows}}


def _glyph(person, pack):
    key = "known" if person.get("name") else "stranger"
    return _art(pack)["people"][key]["glyph"]


def mark_people(view, pack, lines):
    """The People tab's lines, with the glyph of each person in front of that person's line. The people come first in
    the tab, so the first lines are the people's; the rest (kin, ties) are left as they are."""
    people = (view.get("around") or {}).get("people") or []
    if not people:
        return list(lines)
    marked = [f"{_glyph(person, pack)} {line}" for person, line in zip(people, lines)]
    return marked + list(lines[len(people):])


def legend_items(view, pack="bigville"):
    """The legend words for the glyphs drawn beside the map: a person you know, a stranger, a thing you can act on.
    Only the kinds the view names are listed."""
    words = load_pack(pack)["TUI_PROSE"]
    art = _art(pack)
    people = (view.get("around") or {}).get("people") or []
    items = []
    if any(person.get("name") for person in people):
        items.append(f"{art['people']['known']['glyph']} {words['legend_known']}")
    if any(not person.get("name") for person in people):
        items.append(f"{art['people']['stranger']['glyph']} {words['legend_stranger']}")
    if (view.get("around") or {}).get("things"):
        items.append(f"{art['things']['glyph']} {words['legend_thing']}")
    return items
