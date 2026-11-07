"""attend_commands.py -- the typed words for attend and press (Phase 071), for the terminal interface.

The terminal interface (bigville/tui/commands.py) is another session's file and is not edited in Phase 071. This
module holds the parsing it needs. The verb words are the pack's ATTEND.verb_aliases (worlds/body.py,
world/interoception.json), not VERB_ALIASES: VERB_ALIASES maps words to the physical attempt verbs in VERBS, and
press already names push there.

    parse_line(text, pack)   -> {"major_action": {"action": ..., "target": ...}} or None

A line that is not attend or press (or names no region for press) gives None, so the caller falls through to its
own parsing. The reply has the shape the terminal already sends (reply_schema.to_wire turns it into a proposal, and
the world's enact_plan receives {"action", "target"}).

    attend            -> signal:1 (the first felt signal); "attend 2" or "attend signal 2" -> signal:2
    press <region>    -> the ANATOMY node whose key or label is the region ("press upper belly" -> upper_belly)
"""
from __future__ import annotations

from domains.pack import load_pack


def _words(text):
    return " ".join(str(text or "").lower().replace("_", " ").split())


def aliases(pack="bigville"):
    """The words that name attend or press, from the pack's ATTEND table."""
    return dict(load_pack(pack)["ATTEND"]["verb_aliases"])


def region_of(text, pack="bigville"):
    """The ANATOMY node a typed region names (its key or its label, any case, underscores read as spaces), or None."""
    wanted = _words(text)
    if not wanted:
        return None
    for node, row in sorted(load_pack(pack)["ANATOMY"].items()):
        if str(node).startswith("_") or not isinstance(row, dict):
            continue
        if wanted in (_words(node), _words(row.get("label", ""))):
            return str(node)
    return None


def parse_line(text, pack="bigville"):
    """The reply for an attend or press line, or None for any other line."""
    raw = _words(text)
    if raw.startswith(":"):
        raw = raw[1:].strip()
    if not raw:
        return None
    head, _sep, rest = raw.partition(" ")
    verb = aliases(pack).get(head)
    if verb == "attend":
        number = rest.strip()
        if number.startswith("signal"):
            number = number[len("signal"):].strip(" :")
        number = number or "1"
        if not number.isdigit() or int(number) < 1:
            return None
        return {"major_action": {"action": "attend", "target": f"signal:{int(number)}"}}
    if verb == "press":
        region = region_of(rest, pack)
        if region is None:
            return None
        return {"major_action": {"action": "press", "target": region}}
    return None
