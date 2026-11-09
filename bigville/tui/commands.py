"""commands.py -- turns a typed line into a proposal, in the reply shape the LLM backend uses (Phase 057).

    parse(text, view, pack) -> Parsed

The result is a Parsed value:
  kind "propose"  a reply dict (major_action and/or utterances), ready for reply_schema.check and to_wire
  kind "ask"      the words could mean more than one thing: `choices` lists (handle, what, reply) to pick from
  kind "select"   a menu number: `index` (1-based) into the view's `can` rows
  kind "ui"       a screen command: `name` is look, sheet, map, inventory, help, menu or quit
  kind "pass"     wait or stop: the major action wait (Phase 071f), recorded as done
  kind "empty"    a blank line
  kind "unparsed" no letters at all

The parser never refuses a verb. An unknown verb becomes an `attempt` with the verb as written, and the
world refuses or accepts it. A name the view does not show is passed as written. Only a line with no
letters is unparsed.

Words come from the lexicon (domains/lexicon.py): INTENSITY_WORDS ("hard"), AMOUNT_WORDS ("a few") and
VERB_ALIASES ("bash" is "smash"). A handle in the reply (a `can` row's handle, or a `things` handle) is bound
to the world's full affordance by reply_schema.to_wire, not here.

Names and handles match on words: "the chest" matches "chest_1 (a wooden chest)". When more than one thing
matches, the result is "ask" and the choices carry the handles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domains.attend_commands import parse_line as attend_line, region_of
from domains.lexicon import resolve_verb
from domains.pack import load_pack

STOP = frozenset({"the", "a", "an", "some", "your", "to", "toward", "towards", "at", "on", "in", "of"})
UI = {"look": "look", "l": "look", "sheet": "sheet", "s": "sheet", "map": "map", "inventory": "inventory",
      "inv": "inventory", "i": "inventory", "help": "help", "?": "help", "menu": "menu", "can": "menu",
      "quit": "quit", "q": "quit", "exit": "quit"}
PASS = frozenset({"wait", ".", "stop", "z"})
WALK_VERBS = frozenset({"walk", "go", "head", "stroll", "march"})
TAKE_VERBS = frozenset({"take", "grab", "steal", "pick"})
GIVE_VERBS = frozenset({"give", "hand"})
SAY_VERBS = frozenset({"say", "tell", "shout", "whisper"})
WORK_VERBS = frozenset({"work", "make", "brew", "cook", "bake", "grind"})
EAT_VERBS = frozenset({"eat"})
SIMPLE_VERBS = {"sleep": "sleep", "rest": "rest"}


@dataclass
class Parsed:
    kind: str
    name: str = ""
    reply: dict | None = None
    choices: list = field(default_factory=list)
    index: int = 0


def _tokens(text):
    return [t for t in str(text).lower().replace("_", " ").replace(":", " ").split() if t not in STOP]


def _subset(needle, haystack):
    return bool(needle) and set(needle) <= set(haystack)


def _intensity_key(text, pack):
    """Split a trailing intensity word (or number) off the text: (rest, word or None). The longest word wins."""
    table = load_pack(pack)["INTENSITY_WORDS"]
    low = text.lower()
    for key in sorted((k for k in table if not k.startswith("_")), key=len, reverse=True):
        if low == key:
            return "", key
        if low.endswith(" " + key):
            return text[:-len(key)].rstrip(), key
    head, sep, tail = text.rpartition(" ")
    if sep and _is_number(tail) and head.strip():
        return head.strip(), tail
    return text, None


def _is_number(token):
    try:
        return float(token) == float(token)
    except ValueError:
        return False


def _amount_key(text, pack):
    """A leading amount: a number, or an amount word ('a few'). (amount, rest) with the amount as a number or word."""
    table = load_pack(pack)["AMOUNT_WORDS"]
    low = text.lower()
    for key in sorted((k for k in table if not k.startswith("_")), key=len, reverse=True):
        if low == key or low.startswith(key + " "):
            return key, text[len(key):].strip()
    head, _, tail = text.partition(" ")
    try:
        float(head)
        return float(head), tail.strip()
    except ValueError:
        return None, text


def _names(view):
    """The residents the view names: people seen by name, and kin the resident knows by name."""
    names = []
    for person in (view.get("around") or {}).get("people") or []:
        if person.get("name"):
            names.append(person["name"])
    for line in (view.get("self") or {}).get("kin") or []:
        who = line.split(": ", 1)[-1]
        if who and "relative" not in who:
            names.append(who)
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def _match_names(query, names):
    """Names whose words contain every word of the query (case does not matter)."""
    want = _tokens(query)
    if not want:
        return []
    return [name for name in names if _subset(want, _tokens(name))]


def _can_rows(view):
    return [row for row in (view.get("can") or []) if _tokens(row.get("what", ""))]


def _thing_tokens(row):
    return set(_tokens(str(row.get("handle", "")))) | set(_tokens(row.get("what", "")))


def _ask(choices):
    return Parsed("ask", choices=choices)


def _attend_reply(found):
    """Phase 071c: attend.parse_line's reply as the reply shape the terminal sends. A glance is a free action (it
    takes no slot), so it goes in free_actions; attend and press are major actions."""
    if "free_action" in found:
        return {"free_actions": [found["free_action"]]}
    return found


def _parse_strike(text, view, pack, intensity):
    """`strike NAME [at REGION]`: the major action strike on a person the view names, aimed at a region of the body
    when a region is named (params region; an unknown region is refused by the world). None when no person matches,
    so the line goes on to the physical verbs."""
    body = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    who_text, _, where_text = body.partition(" at ")
    if not who_text.strip():
        return None
    found = _match_names(who_text, _names(view))
    if not found:
        return None
    where = where_text.strip()
    params = {}
    if where:
        params["region"] = region_of(where, pack) or "_".join(_tokens(where))

    def build(name):
        action = {"action": "strike", "target": name}
        if params:
            action["params"] = dict(params)
        if intensity:
            action["intensity"] = intensity
        return {"major_action": action}

    if len(found) > 1:
        return _ask([(name, "", build(name)) for name in found])
    return Parsed("propose", reply=build(found[0]))


def _parse_say(text, view):
    rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    addressee, body = None, rest
    if ":" in rest:
        head, _, tail = rest.partition(":")
        addressee, body = head.strip(), tail.strip()
    elif rest.lower().startswith("to "):
        parts = rest[3:].split(None, 1)
        if parts:
            addressee, body = parts[0], (parts[1] if len(parts) > 1 else "")
    if not body.strip():
        return Parsed("unparsed")
    if addressee:
        found = _match_names(addressee, _names(view)) or [addressee]
        if len(found) > 1:
            return _ask([(name, "", {"utterances": [{"to": name, "text": body}]}) for name in found])
        return Parsed("propose", reply={"utterances": [{"to": found[0], "text": body}]})
    return Parsed("propose", reply={"utterances": [{"to": None, "text": body}]})


FILLER = ("toward", "towards", "to", "the", "a", "an")


def _parse_walk(text, view):
    rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    words = rest.split()
    while words and words[0].lower() in FILLER:
        words.pop(0)
    rest = " ".join(words)
    want = _tokens(rest)
    rows = [row for row in _can_rows(view) if row.get("action") in ("walk", "move")
            and _subset(want, _tokens(row.get("what", "")))]
    if len(rows) > 1:
        return _ask([(row["handle"], row.get("what", ""), {"major_action": {"action": "walk",
                                                              "target": row["handle"]}}) for row in rows])
    if rows:
        return Parsed("propose", reply={"major_action": {"action": "walk", "target": rows[0]["handle"]}})
    return Parsed("propose", reply={"major_action": {"action": "move", "params": {"toward": rest.strip()}}})


def _parse_take(text, view, pack):
    rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    left, _, source = rest.partition(" from ")
    amount, kind_text = _amount_key(left.strip(), pack)
    kind = "_".join(_tokens(kind_text)) if kind_text else ""
    params = {}
    if kind:
        params["kind"] = kind
    if amount is not None:
        params["amount"] = amount  # a word or a number; reply_schema.to_wire turns it into the count
    if source.strip():
        found = _match_names(source, _names(view)) or [source.strip()]
        if len(found) > 1:
            return _ask([(name, "", {"major_action": {"action": "take", "params": {**params, "source": name}}})
                         for name in found])
        params["source"] = found[0]
    return Parsed("propose", reply={"major_action": {"action": "take", "params": params}})


def _parse_give(text, view, pack):
    rest = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    left, _, to = rest.partition(" to ")
    params = {}
    kind = "_".join(_tokens(left))
    if kind:
        params["kind"] = kind
    if to.strip():
        found = _match_names(to, _names(view)) or [to.strip()]
        if len(found) > 1:
            return _ask([(name, "", {"major_action": {"action": "transfer", "params": {**params,
                                                                                     "recipient": name}}})
                         for name in found])
        params["recipient"] = found[0]
    return Parsed("propose", reply={"major_action": {"action": "transfer", "params": params}})


def _attempt(text, view, pack, verb, intensity):
    """Any other verb: an attempt on a thing, with a tool and an intensity when the words name them."""
    body = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
    target_text, _, tool_text = body.partition(" with ")
    tool = "_".join(_tokens(tool_text)) if tool_text.strip() else None
    tokens = _tokens(target_text)
    things = (view.get("around") or {}).get("things") or []
    found = [row for row in things if tokens and set(tokens) <= _thing_tokens(row)]
    base = {"verb": resolve_verb(verb, pack) or verb}

    def build(handle):
        action = {"action": "attempt", "params": dict(base)}
        if handle:
            action["target"] = handle
        if tool:
            action["with"] = tool
        if intensity:
            action["intensity"] = intensity
        return {"major_action": action}

    if len(found) > 1:
        return _ask([(row["handle"], row.get("what", ""), build(row["handle"])) for row in found])
    if found:
        return Parsed("propose", reply=build(found[0]["handle"]))
    return Parsed("propose", reply=build("_".join(tokens) if tokens else None))


def menu_pick(index, view):
    """The proposal for a menu number: the `can` row at that place, bound by its handle."""
    rows = view.get("can") or []
    if not 1 <= index <= len(rows):
        return Parsed("unparsed")
    row = rows[index - 1]
    return Parsed("propose", reply={"major_action": {"action": row["action"], "target": row["handle"]}})


def parse(text, view, pack="bigville"):
    """Parse one typed line against the agent view. See the module doc for the result kinds."""
    raw = " ".join(str(text or "").split())
    if raw.startswith(":"):
        raw = raw[1:].strip()
    if not raw:
        return Parsed("empty")
    if raw.isdigit():
        return Parsed("select", index=int(raw))
    low = raw.lower()
    if low in UI:
        return Parsed("ui", name=UI[low])
    if low in PASS:
        return Parsed("pass")
    if not any(ch.isalpha() for ch in raw):
        return Parsed("unparsed")
    attended = attend_line(raw, pack)   # Phase 071c: attend, press <region> and glance, before the physical verbs
    if attended is not None:
        return Parsed("propose", reply=_attend_reply(attended))
    head = low.split(None, 1)[0]
    if head in SAY_VERBS:
        return _parse_say(raw, view)
    text_rest, intensity = _intensity_key(raw, pack)
    text_rest = text_rest or raw
    if head in TAKE_VERBS:
        return _parse_take(text_rest, view, pack)
    if head in GIVE_VERBS:
        return _parse_give(text_rest, view, pack)
    if head in WALK_VERBS:
        return _parse_walk(text_rest, view)
    if resolve_verb(head, pack) == "hit":
        struck = _parse_strike(text_rest, view, pack, intensity)
        if struck is not None:
            return struck
    phrase = _tokens(text_rest)
    rows = [row for row in _can_rows(view) if _subset(_tokens(row["what"]), phrase)]
    if len(rows) > 1:
        return _ask([(row["handle"], row["what"], {"major_action": {"action": row["action"],
                                                                      "target": row["handle"]}})
                     for row in rows])
    if rows:
        reply = {"major_action": {"action": rows[0]["action"], "target": rows[0]["handle"]}}
        if intensity:
            reply["major_action"]["intensity"] = intensity
        return Parsed("propose", reply=reply)
    if head in EAT_VERBS or head in WORK_VERBS:
        rest = text_rest.split(None, 1)[1] if len(text_rest.split(None, 1)) > 1 else ""
        kind = "_".join(_tokens(rest))
        action = "eat" if head in EAT_VERBS else "work"
        params = {"kind": kind} if action == "eat" else {"recipe": kind}
        reply = {"major_action": {"action": action, "params": {k: v for k, v in params.items() if v}}}
        if intensity:
            reply["major_action"]["intensity"] = intensity
        return Parsed("propose", reply=reply)
    if head in SIMPLE_VERBS:
        return Parsed("propose", reply={"major_action": {"action": SIMPLE_VERBS[head]}})
    return _attempt(text_rest, view, pack, head, intensity)


def placed(text, pack="bigville"):
    """True when the grammar can place a line: a blank line, a number, a screen word, a wait, a command verb of this
    module, or a verb the lexicon knows. Text mode asks again for any other line (Phase 067). It does not judge
    whether the world will allow the action; that is the world's answer, as for the map."""
    raw = " ".join(str(text or "").lower().split())
    if raw.startswith(":"):
        raw = raw[1:].strip()
    if not raw or raw.isdigit() or raw in UI or raw in PASS:
        return True
    if attend_line(raw, pack) is not None:   # Phase 071c
        return True
    head = raw.split(None, 1)[0]
    if head in SAY_VERBS or head in TAKE_VERBS or head in GIVE_VERBS or head in WALK_VERBS:
        return True
    if head in WORK_VERBS or head in EAT_VERBS or head in SIMPLE_VERBS or head == "tab":
        return True
    return resolve_verb(head, pack) is not None


def parse_reaction(text, view):
    """A reaction answer: a menu number, a choice name, or the words of one answer. Returns the choice
    name (the world's option name) or None when the words name no answer offered."""
    reaction = view.get("reaction") or {}
    options = reaction.get("options") or []
    raw = " ".join(str(text or "").lower().split())
    if raw.isdigit():
        index = int(raw)
        return options[index - 1]["choice"] if 1 <= index <= len(options) else None
    for option in options:
        if raw in (option["choice"], option["words"].lower()):
            return option["choice"]
    return None
