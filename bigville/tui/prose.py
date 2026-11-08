"""prose.py -- the text mode's room, written from the prompt packet (Phase 067).

    room_lines(record, view, pack)   the room as sentences: the packet's now, body, people, things, writing, heard
                                     speech, moves seen, the ground, the ways on, the options (numbered as the view
                                     numbers them), the last outcome, and a contest prompt the view carries

`record` is PromptBuilder's packet for the resident (EmbeddedClient.packet()). Every sentence is filled from that
packet, or from the view for the contest prompt (the packet has no contest section). Nothing reads the world.
The packet's `sizes` and `omitted` counts are measures for the model and are never written here.

Option numbers are the view's `can` order, so a typed number picks the same row the menu does (commands.menu_pick).
"""
from __future__ import annotations

import json

from bigville.tui import narrate
from domains.pack import load_pack

DEFAULT_PACK = "bigville"
GROUND_SKIP = ("you", "unknown ground")


def words(pack=DEFAULT_PACK):
    """The TUI_PROSE table of the pack."""
    return load_pack(pack)["TUI_PROSE"]


def packet_text(record):
    """The packet as the mode printed it: indented JSON, sorted keys, UTF-8 text."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2)


def _cap(text):
    return narrate._cap(text)


def _walk_verb(pack):
    return load_pack(pack)["ACTION_WORDS"]["move"]


def room_lines(record, view, pack=DEFAULT_PACK):
    """The room as lines of text, from the packet in `record` (see the module doc)."""
    context = record["context"]
    public, private = context["public"], context["private"]
    text = words(pack)
    around = public.get("around") or {}
    lines = []
    status = narrate.status_line({"now": public.get("now") or {}}, pack)
    if status:
        lines.append(_cap(status) + ".")
    lines += narrate.body_lines({"self": {"body": private.get("body") or {}}}, pack)
    people = around.get("people") or []
    if people:
        lines += [_cap(narrate.person_line(person, pack)) for person in people]
        if (context.get("omitted") or {}).get("people"):
            lines.append(narrate.words(pack)["more_people"])
    else:
        lines.append(text["nobody"])
    named = [row["what"] for row in around.get("things") or [] if row.get("what")]
    lines.append(text["things"].format(things="; ".join(named)) if named else text["things_none"])
    for row in around.get("writing") or []:
        lines.append(_cap(text["writing"].format(text=row["percept"])))
    for item in around.get("seen") or []:
        lines.append(_cap(narrate.fill("seen", pack, who=item.get("who", ""), did=item.get("did", ""))))
    for item in (public.get("heard") or {}).get("quotes") or []:
        lines.append(narrate.fill("heard", pack, **{"from": item.get("from", ""), "text": item.get("quote", "")}))
    legend = (public.get("map") or {}).get("legend") or {}
    ground = [word for word in legend.values() if word not in GROUND_SKIP]
    if ground:
        lines.append(text["ground"].format(ground="; ".join(ground)))
    can = list(view.get("can") or [])
    walk = _walk_verb(pack)
    ways = [row["what"] for row in can if row.get("action") == walk and row.get("what")]
    lines.append(text["exits"].format(ways="; ".join(ways)) if ways else text["exits_none"])
    options = [(number, row) for number, row in enumerate(can, 1) if row.get("action") != walk]
    if options:
        lines.append(text["options"])
        lines += [f"{number}. {_cap(row.get('what', ''))}" for number, row in options]
    else:
        lines.append(text["options_none"])
    lines += narrate.outcome_lines({"last": public.get("last") or {}}, pack)
    lines += narrate.reaction_lines(view, pack)
    return [line for line in lines if line]
