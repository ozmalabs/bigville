"""render.py -- draws an agent view as lines of text (Phase 057). Pure: no terminal, no game, no clock.

    render(view, width=80, height=24, tab="body", log=(), bottom=None, prompt="", pack="bigville") -> list[str]

The screen, top to bottom:
  row 0          the title and the status bar (time, season, weather)
  rows 1..n      left: the map. right: the character sheet, with a tab header (Body, Skills, Knows, Carrying,
                 People; the active tab in brackets)
  row n+1        the map's legend (glyph and words)
  row n+2        the bottom header ("Your move" while the world waits for you, or the menu or a reaction)
  rows n+3..     the bottom lines: the newest log lines, or the menu or the reaction answers
  last row       the prompt

The map is drawn by its `level` key (domains/agent_view.py MAP_LEVELS):
  full    the cells of the view's `rows`, with the legend
  vague   the rows the view gives (none yet), and the landmarks it names in `labels` (Phase 053)
  hidden  blank, with the words for ground you have not seen
A map with no level (the view has none) is drawn as hidden. Nothing here invents a cell or a label.

Every text comes from the pack's NARRATION table (bigville/tui/narrate.py). A line is cut to the width.
"""
from __future__ import annotations

import textwrap

from bigville.tui import art as tui_art
from bigville.tui import narrate

TABS = ("body", "skills", "knows", "carrying", "people")
TAB_KEYS = {"body": "tab_body", "skills": "tab_skills", "knows": "tab_knows", "carrying": "tab_carrying",
            "people": "tab_people"}
MAP_GAP = 2
# The map panel's width when the view has no rows: the patch is 15 cells for the sight range of 7 (HEARING).
MAP_PANEL = 15
MIN_WIDTH = 40
MIN_HEIGHT = 12
BOTTOM_LINES = 5


def _fit(text, width):
    text = str(text)
    if len(text) <= width:
        return text.ljust(width)
    if width <= 3:
        return text[:width]
    return text[:width - 3] + "..."


def _labelled(label, value):
    return f"{label}: {value}"


def _body_tab(view, pack):
    words = narrate.words(pack)
    me = view.get("self") or {}
    body = me.get("body") or {}
    lines = []
    if me.get("job"):
        lines.append(_labelled(words["label_work"], me["job"]))
    life = ", ".join(str(part) for part in (me.get("life_stage"), me.get("age")) if part)
    if life:
        lines.append(_labelled(words["label_life"], life))
    for key in ("health", "energy", "hunger", "strength", "stamina", "mood"):
        if body.get(key):
            lines.append(_labelled(words[f"label_{key}"], body[key]))
    for key in ("asleep", "collapsed", "ill"):
        if body.get(key):
            lines.append(body[key][:1].upper() + body[key][1:])
    persona = me.get("persona") or {}
    if persona.get("traits"):
        lines.append(_labelled(words["label_traits"], persona["traits"]))
    if persona.get("as_others_see"):
        lines.append(_labelled(words["label_others"], persona["as_others_see"]))
    return lines


def _skills_tab(view, pack):
    skills = (view.get("self") or {}).get("skills") or []
    return list(skills) or [narrate.words(pack)["label_nothing"]]


def _knows_tab(view, pack):
    knows = (view.get("self") or {}).get("knows") or []
    return [f"{row['name']} ({row['gist']})" for row in knows] or [narrate.words(pack)["label_nothing"]]


def _carrying_tab(view, pack):
    words = narrate.words(pack)
    me = view.get("self") or {}
    carrying = me.get("carrying") or {}
    lines = []
    if carrying.get("inventory"):
        lines.append(_labelled(words["label_inventory"], "; ".join(carrying["inventory"])))
    if carrying.get("held"):
        lines.append(_labelled(words["label_held"], "; ".join(carrying["held"])))
    if carrying.get("worn"):
        lines.append(_labelled(words["label_worn"], "; ".join(carrying["worn"])))
    if carrying.get("load"):
        lines.append(_labelled(words["label_load"], carrying["load"]))
    return lines or [words["label_nothing"]]


def _people_tab(view, pack):
    words = narrate.words(pack)
    me = view.get("self") or {}
    lines = [narrate._cap(narrate.person_line(person, pack))
             for person in (view.get("around") or {}).get("people") or []]
    if not lines:
        lines = [words["label_nobody"]]
    if me.get("kin"):
        lines.append(_labelled(words["label_kin"], "; ".join(me["kin"])))
    ties = (me.get("persona") or {}).get("ties")
    if ties:
        lines.append(_labelled(words["label_ties"], ties))
    return lines


_TAB_BUILDERS = {"body": _body_tab, "skills": _skills_tab, "knows": _knows_tab,
                 "carrying": _carrying_tab, "people": _people_tab}


def sheet_lines(view, tab="body", pack="bigville"):
    """The lines of one character sheet tab (no width cut). Unknown tabs raise KeyError."""
    if tab not in _TAB_BUILDERS:
        raise KeyError(f"no sheet tab {tab!r}; the tabs are {', '.join(TABS)}")
    return _TAB_BUILDERS[tab](view, pack)


def _tab_header(tab, pack, width):
    words = narrate.words(pack)
    names = [f"[{words[TAB_KEYS[name]]}]" if name == tab else words[TAB_KEYS[name]] for name in TABS]
    return _fit(" ".join(names), width)


def _wrapped(text, width, height):
    """The words of a sentence, wrapped to the map's width and set in the middle of its height."""
    lines = textwrap.wrap(text, width=width) or [""]
    top = max(0, (height - len(lines)) // 2)
    block = [" " * width for _ in range(height)]
    for offset, line in enumerate(lines[:height]):
        block[top + offset] = _fit(line, width)
    return block


def _map_rows(view, pack, height, width):
    """The map's rows (height x width text cells), drawn by its level key."""
    blank = [" " * width for _ in range(height)]
    game_map = view.get("map") or {}
    level = game_map.get("level")
    if level == "full":
        rows = [str(row)[:width].ljust(width) for row in game_map.get("rows") or []]
        return (rows + blank)[:height]
    if level == "vague":
        rows = [str(row)[:width].ljust(width) for row in game_map.get("rows") or []]
        labels = game_map.get("labels") or []
        if not labels:
            return (rows + blank)[:height]
        text = narrate.fill("map_vague", pack, labels="; ".join(
            f"{item.get('glyph', '')} {item.get('word', '')}".strip() for item in labels))
        return (rows + blank)[:height - 4] + _wrapped(text, width, 4)
    return _wrapped(narrate.words(pack)["map_hidden"], width, height)


def render(view, width=80, height=24, *, tab="body", log=(), bottom=None, bottom_title=None,
           prompt="", pack="bigville", art=False):
    """The screen as `height` lines, each `width` characters (see the module doc for the layout).

    `log` is the list of lines shown in the bottom area (the newest last). `bottom` replaces the log with
    other lines (the menu, or the reaction answers) and `bottom_title` names them. `art` draws the map mode
    (Phase 067): two-character tiles, and a glyph for each person and thing; the default is the screen of Phase 057."""
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise ValueError(f"the screen needs at least {MIN_WIDTH} by {MIN_HEIGHT}, not {width} by {height}")
    if art:
        view = tui_art.tiled(view, pack)
    words = narrate.words(pack)
    body_h = height - (BOTTOM_LINES + 4)
    map_rows = (view.get("map") or {}).get("rows") or []
    map_w = max([len(str(row)) for row in map_rows] or [MAP_PANEL])
    left = map_w + MAP_GAP
    right_w = width - left
    screen = [_fit(f"{words['title']}   {narrate.status_line(view, pack)}", width)]
    map_block = _map_rows(view, pack, body_h, map_w)
    sheet = [_tab_header(tab, pack, right_w)]
    content = _TAB_BUILDERS[tab](view, pack)
    if art and tab == "people":
        content = tui_art.mark_people(view, pack, content)
    room = body_h - 1
    if len(content) > room:
        content = content[:room - 1] + ["..."]
    sheet += content
    sheet += [""] * (body_h - len(sheet))
    for row in range(body_h):
        screen.append(_fit(map_block[row], left) + _fit(sheet[row], right_w))
    legend_words = narrate.legend_items(view, pack) + (tui_art.legend_items(view, pack) if art else [])
    legend = ("  " if art else "   ").join(legend_words)
    screen.append(_fit(legend, width))
    title = bottom_title if bottom_title is not None else words["label_your_move"]
    screen.append(_fit(title, width))
    if bottom is not None:
        shown = list(bottom)
    else:
        shown = list(log)[-BOTTOM_LINES:]
    shown = shown[-BOTTOM_LINES:]
    shown = [""] * (BOTTOM_LINES - len(shown)) + shown
    screen += [_fit(line, width) for line in shown]
    screen.append(_fit(words["prompt"] + prompt, width))
    return screen[:height]
