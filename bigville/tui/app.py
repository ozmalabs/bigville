"""app.py -- the session and the two front ends of the terminal interface (Phase 057).

Session holds one resident's view and turns typed lines into turns. It is the same for both front ends:

* run_plain(session, inp, out): a text adventure over any text stream (sys.stdin, or StringIO in tests).
* run_curses(session, screen): the 80 by 24 screen, drawn by bigville.tui.render. Its key loop takes a
  `getch` and a `screen` object, so a test can drive it with a fake screen.

choose_front_end() picks curses only when it can be imported and stdout is a terminal; otherwise plain.
"""
from __future__ import annotations

import sys

from bigville.tui import narrate
from bigville.tui.client import ClientError, UnsupportedOverHttp
from bigville.tui.commands import menu_pick, parse, parse_reaction
from bigville.tui.render import TABS, render, sheet_lines
from bigville.backends import reply_schema

KEY_WEST, KEY_SOUTH, KEY_NORTH, KEY_EAST = "west", "south", "north", "east"
STEP_KEYS = {"h": KEY_WEST, "j": KEY_SOUTH, "k": KEY_NORTH, "l": KEY_EAST}


class Session:
    """One resident's play: the view, the open menu or question, and the log of what has happened."""

    def __init__(self, client, pack=None):
        self.client = client
        self.pack = pack or client.pack
        self.view = client.view()
        self.log = []
        self.menu_open = False
        self.ask = None
        self.tab = "body"
        self.done = False
        self.log = self.arrival()

    # ------------------------------------------------------------------ screens
    def words(self):
        return narrate.words(self.pack)

    def arrival(self):
        return narrate.arrival_lines(self.view, self.pack)

    def _bottom(self):
        """The bottom area's title and lines: the reaction answers, the question, the menu, or the log."""
        if self.view.get("reaction"):
            choices = [f"{number}. {words}" for number, _, words in narrate.reaction_choices(self.view, self.pack)]
            return self.words()["label_answer"], narrate.reaction_lines(self.view, self.pack)[:1] + choices
        if self.ask is not None:
            return self.words()["label_can"], [f"{i}. {handle} ({what})"
                                               for i, (handle, what, _) in enumerate(self.ask, 1)]
        if self.menu_open:
            return self.words()["label_can"], narrate.menu_lines(self.view, self.pack)
        return None, None

    def screen(self, width=80, height=24, prompt=""):
        title, bottom = self._bottom()
        return render(self.view, width, height, tab=self.tab, log=self.log, bottom=bottom,
                      bottom_title=title, prompt=prompt, pack=self.pack)

    # ------------------------------------------------------------------ input
    def line(self, text):
        """One typed line. Returns the lines to show. Updates the view and the log. A client error (the server
        is down, or it has no route for the action) is shown as its message, and the session goes on."""
        try:
            return self._line(text)
        except (ClientError, UnsupportedOverHttp) as exc:
            return [str(exc)]

    def _line(self, text):
        if self.view.get("reaction"):
            choice = parse_reaction(text, self.view)
            if choice is None:
                return [self.words()["reaction_pick"]]
            answer = next((option["words"] for option in self.view["reaction"]["options"]
                           if option["choice"] == choice), choice)
            return [self.words()["answered"].format(answer=answer)] + self._after(self.client.react(choice))
        if self.ask is not None:
            if str(text).strip().isdigit():
                index = int(str(text).strip())
                choices = self.ask
                self.ask = None
                if 1 <= index <= len(choices):
                    return self._propose(choices[index - 1][2])
                return []
            self.ask = None
        low = " ".join(str(text).lower().split())
        if low.startswith("tab "):
            return self._tab(low[4:].strip())
        parsed = parse(text, self.view, self.pack)
        if parsed.kind == "empty":
            return []
        if parsed.kind == "ui":
            return self._ui(parsed.name)
        if parsed.kind == "pass":
            return self._turn({})
        if parsed.kind == "select":
            if not self.view.get("can"):
                return [self.words()["empty_log"]]
            picked = menu_pick(parsed.index, self.view)
            if picked.kind != "propose":
                return [self.words()["unparsed"]]
            return self._propose(picked.reply)
        if parsed.kind == "propose":
            return self._propose(parsed.reply)
        if parsed.kind == "ask":
            self.ask = parsed.choices
            return [self.words()["ask"].format(choices="; ".join(
                f"{i}. {handle} ({what})" for i, (handle, what, _) in enumerate(parsed.choices, 1)))]
        return [self.words()["unparsed"]]

    def _ui(self, name):
        if name == "quit":
            self.done = True
            return []
        if name == "look":
            self.menu_open = True
            return self.arrival() + [self.words()["label_can"]] + narrate.menu_lines(self.view, self.pack)
        if name == "sheet":
            return sheet_lines(self.view, self.tab, self.pack) or [self.words()["label_nothing"]]
        if name == "inventory":
            self.tab = "carrying"
            return sheet_lines(self.view, "carrying", self.pack)
        if name == "map":
            game_map = self.view.get("map") or {}
            rows = list(game_map.get("rows") or [])
            return [narrate.map_caption(self.view, self.pack)] + rows + narrate.legend_items(self.view, self.pack)
        if name == "menu":
            self.menu_open = True
            return [self.words()["label_can"]] + narrate.menu_lines(self.view, self.pack)
        if name == "help":
            return narrate.help_lines(self.pack)
        return []

    def _tab(self, name):
        if name not in TABS:
            return [self.words()["unparsed"]]
        self.tab = name
        return sheet_lines(self.view, name, self.pack)

    def _propose(self, reply):
        errors = reply_schema.check(reply, self.pack)
        if errors:
            return errors
        said = []
        for item in reply.get("utterances") or []:
            if item.get("text"):
                said.append(self.words()["said_to"].format(who=item["to"], text=item["text"]) if item.get("to")
                            else self.words()["said"].format(text=item["text"]))
        return self._after(self.client.send_reply(reply), said=said, acted=bool(reply.get("major_action")))

    def _turn(self, wire, *, said=(), acted=False):
        return self._after(self.client.submit(wire), said=said, acted=acted)

    def _after(self, result, *, said=(), acted=False):
        previous = self.view
        self.view = result.get("view") or self.client.view()
        status = result.get("status")
        out = list(said)
        if status == "advanced":
            # The last action's outcome is shown only for a turn that proposed one; the view keeps the last
            # major action's outcome until the next one.
            if acted:
                out += narrate.outcome_lines(self.view, self.pack)
            out += narrate.new_events(previous, self.view, self.pack)
            if not out:
                out.append(self.words()["pass"])
            self.menu_open = False
        elif status == "waiting" and self.view.get("reaction"):
            out += narrate.reaction_lines(self.view, self.pack)
        elif status == "waiting":
            who = result.get("actor") or ""
            out.append(self.words()["still_waiting"] if who == self.client.player
                       else self.words()["waiting"].format(who=who))
        return out


def run_plain(session, inp, out, echo=True):
    """The text-adventure front end. Reads lines from `inp` and writes to `out` until quit or end of input."""
    for line in session.arrival():
        out.write(line + "\n")
    while not session.done:
        raw = inp.readline()
        if raw == "":
            break
        text = raw.rstrip("\r\n")
        if echo:
            out.write(session.words()["prompt"] + text + "\n")
        for line in session.line(text):
            out.write(line + "\n")
    return session


def _draw(screen, lines):
    height, width = screen.getmaxyx()
    screen.erase()
    for y, line in enumerate(lines[:height]):
        screen.addnstr(y, 0, line, max(width - 1, 1))
    screen.refresh()


def run_curses(session, screen, getch):
    """The curses front end's key loop. `screen` needs getmaxyx, erase, addnstr and refresh; `getch` returns a
    key code (a character, or a curses key number for the arrows and Tab). Keys:

    hjkl or the arrows step (walk west, south, north, east), . waits, Tab turns the sheet, : starts a
    command, ? shows the help, q quits. Typing any other character starts a line, which Enter sends."""
    import curses  # imported here so the plain front end does not need it
    buffer, typing = "", False
    arrows = {curses.KEY_LEFT: "west", curses.KEY_DOWN: "south", curses.KEY_UP: "north",
              curses.KEY_RIGHT: "east"}
    while not session.done:
        height, width = screen.getmaxyx()
        _draw(screen, session.screen(width=max(width, 40), height=max(height, 12),
                                     prompt=buffer if typing else ""))
        key = getch()
        if typing:
            if key in (10, 13, "\n", "\r"):
                text, buffer, typing = buffer, "", False
                session.log.append(session.words()["prompt"] + text)
                session.log += session.line(text)
            elif key in (27, "\x1b"):
                buffer, typing = "", False
            elif key in (127, 8, curses.KEY_BACKSPACE, "\x7f", "\b"):
                buffer = buffer[:-1]
            elif isinstance(key, str) and key.isprintable():
                buffer += key
            continue
        if key in arrows:
            session.log += session.line(f"walk {arrows[key]}")
        elif isinstance(key, str) and key in STEP_KEYS:
            session.log += session.line(f"walk {STEP_KEYS[key]}")
        elif key == ".":
            session.log += session.line(".")
        elif key in ("\t", 9):
            names = list(TABS)
            session.tab = names[(names.index(session.tab) + 1) % len(names)]
        elif key == "?":
            session.log += narrate.help_lines(session.pack)
        elif key == "q" and not typing:
            session.done = True
        elif key == ":":
            typing, buffer = True, ""
        elif isinstance(key, str) and key.isprintable() and key.strip():
            typing, buffer = True, key


def choose_front_end(*, plain=False, stdout=None):
    """'curses' when the flag does not ask for plain, curses imports, and stdout is a terminal; else 'plain'."""
    if plain:
        return "plain"
    stream = stdout if stdout is not None else sys.stdout
    try:
        import curses  # noqa: F401
    except ImportError:
        return "plain"
    isatty = getattr(stream, "isatty", None)
    return "curses" if callable(isatty) and isatty() else "plain"
