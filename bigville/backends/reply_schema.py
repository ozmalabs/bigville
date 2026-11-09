"""reply_schema.py -- the reply a model must send back, checked against the pack (Phase 054).

The shape is the pack's PROMPT_REPLY table. A major action has the keys action, target, with, intensity and
params. Free actions (Phase 071c) are a list of {action, target, params}, checked against FREE_ACTIONS; the world
applies them (bigville/free_replies.py). Utterances are {to, text}. Memory updates are {kind, text} with a kind from
the pack. Two functions:

* ``check(parsed, pack)`` returns the errors in words (short fixed messages, no echo of
  the reply). Only shape and type are errors (Phase 071d/071e). Intensity and amounts take a number or a word; a
  word the lexicon does not know folds to a normal effort. A verb the pack does not know is not an error: the world
  refuses it as unsupported, and that refusal is the consequence the resident learns from.
* ``to_wire(parsed, pack, affordances=...)`` returns the reply in the shape ActorResponse.from_dict reads: the
  major action's target, with and intensity folded into params (with a verb by its alias resolved, a word intensity
  turned into its value), utterance ``to`` read as ``target``, and each memory update as {kind, content: {text}}.
  A target that is a handle of a row in ``affordances`` (domains/affordance_handles.py) makes the proposal that row's
  full params, as the simple backend sends them, with the model's own fields laid over (``bind_row``).

Nothing here decides anything. It only reads words into the world's own vocabulary.
"""
from __future__ import annotations

import re

from domains.affordance_handles import handle_pairs
from domains.lexicon import amount_value, intensity_value, resolve_verb
from domains.pack import load_pack

ERRORS_PER_RESPONSE = 5
# LA05: a lazy view's place handle is a stable cell ("cell:x,y"). It is a direct param, not a menu row.
_CELL_HANDLE = re.compile(r"^(?:cell:)?(-?\d+),(-?\d+)$")


def schema(pack: str) -> dict:
    """The PROMPT_REPLY table of the pack."""
    return load_pack(pack)["PROMPT_REPLY"]


def _is_text(value) -> bool:
    return isinstance(value, str)


def _is_number_or_word(value) -> bool:
    """A number, or a word the lexicon may or may not know (an unknown word is the world's to refuse or fold)."""
    return isinstance(value, str) or (isinstance(value, (int, float)) and not isinstance(value, bool))


# Phase 071d: a word the lexicon does not know, in intensity or amount, folds to a normal effort: 1.0 is the value the
# world uses when the field is left out.
_NORMAL = 1.0


def _weight(value, reader, pack) -> float:
    try:
        return reader(value, pack)
    except (TypeError, ValueError):
        return _NORMAL


def _check_major_action(action, pack, errors) -> None:
    keys = set(schema(pack)["major_action_keys"])
    for key in sorted(action, key=str):
        if key not in keys:
            errors.append(f"major_action has no field '{str(key)[:24]}'")
    for name in ("target", "with"):
        if action.get(name) is not None and not _is_text(action.get(name)):
            errors.append(f"major_action.{name} must be a handle (text) or null")
    if action.get("intensity") is not None and not _is_number_or_word(action["intensity"]):
        errors.append("intensity must be a number or a word")
    params = action.get("params")
    if isinstance(params, dict):
        if params.get("verb") is not None and not _is_text(params["verb"]):
            errors.append("params.verb must be a verb name (text)")
        if params.get("amount") is not None and not _is_number_or_word(params["amount"]):
            errors.append("params.amount must be a number or a word")


def _check_free_action(item, pack, errors) -> None:
    """Phase 071c: one free action of a reply. The name is checked by the world (an unknown name is refused as
    unsupported and that refusal is recorded), so only the shape, the words and a required target are checked here."""
    keys = set(schema(pack)["free_action_keys"])
    for key in sorted(item, key=str):
        if key not in keys:
            errors.append(f"free_actions has no field '{str(key)[:24]}'")
            return
    name = item.get("action")
    if not isinstance(name, str):
        errors.append("free_actions need an action (text)")
        return
    if item.get("target") is not None and not _is_text(item.get("target")):
        errors.append("free_actions.target must be a handle or a name (text) or null")
    params = item.get("params")
    if params is not None and not isinstance(params, dict):
        errors.append("free_actions.params must be an object")
        return
    params = params or {}
    for key in _FREE_TEXT_PARAMS:
        if params.get(key) is not None and not _is_text(params.get(key)):
            errors.append(f"free_actions.params.{key} must be text")
            return
    if params.get("intensity") is not None and not _is_number_or_word(params["intensity"]):
        errors.append("free_actions.params.intensity must be a number or a word")
    # A missing target the action needs is the world's refusal (no_target), not a malformed reply.


def _fold_free(item, pack) -> dict:
    """A free action as the world reads it: the intensity word folded to its value; the rest as written."""
    params = dict(item.get("params") or {})
    if params.get("intensity") is not None:
        params["intensity"] = _weight(params["intensity"], intensity_value, pack)
    target = item.get("target")
    return {"action": str(item["action"]), "target": target if _is_text(target) else None, "params": params}


def check(parsed: dict, pack: str) -> list[str]:
    """Schema errors for a reply that has already passed the structural checks. Only shape and type are errors
    (Phase 071e): empty speech, an unknown memory kind, empty memory text, a lesson count over the cap and an empty
    continuation action are accepted, and ``to_wire`` records what became of each."""
    spec = schema(pack)
    errors: list[str] = []
    action = parsed.get("major_action")
    if isinstance(action, dict):
        _check_major_action(action, pack, errors)
    free = parsed.get("free_actions")
    if free is not None and not isinstance(free, list):
        errors.append("free_actions must be a list")
    for item in (free if isinstance(free, list) else []):
        if isinstance(item, dict):
            _check_free_action(item, pack, errors)
        if errors:
            break
    utterance_keys = set(spec["utterance_keys"])
    for item in parsed.get("utterances", []) or []:
        if not isinstance(item, dict):
            continue
        extra = [key for key in item if key not in utterance_keys and key != "target"]
        if extra:
            errors.append(f"utterances has no field '{str(extra[0])[:24]}'")
            break
        if item.get("to") is not None and not _is_text(item.get("to")):
            errors.append("utterances.to must be a person's name (text) or null")
            break
        if not _is_text(item.get("text")):
            errors.append("utterances need a text")
            break
    for item in parsed.get("memory_updates", []) or []:
        if not isinstance(item, dict):
            continue
        if not _is_text(item.get("kind")):
            errors.append("memory_updates kind must be text")
            break
        if not _is_text(item.get("text")):
            errors.append("memory_updates need a text")
            break
    return errors[:ERRORS_PER_RESPONSE]


_NOT_PARAMS = ("action", "score", "legal", "reason")
_FREE_TEXT_PARAMS = ("text", "note", "item", "giver")


def _names_action(row: dict, name: str, pack: str) -> bool:
    """The reply's action names this row: the world's action name, or the view's word for it (ACTION_WORDS,
    for example walk for move)."""
    action = str(row.get("action", ""))
    return name == action or name == load_pack(pack)["ACTION_WORDS"].get(action)


def bind_row(name: str, handle: str, affordances, pack: str) -> dict | None:
    """The affordance row a major action names, or None.

    With a handle, the row is the one whose handle (domains/affordance_handles.py) equals it, and that names the
    same action. Without a handle, the row is the only row with that action; with several, there is no row.
    ``attempt`` never binds: its target is a thing handle (public.things), not an affordance. None means the
    proposal is passed on as the model wrote it, and the world refuses what it does not offer."""
    if affordances is None or name == "attempt":
        return None
    pairs = handle_pairs(list(affordances))
    if handle:
        rows = [row for key, row in pairs if key == handle]
        return rows[0] if len(rows) == 1 and _names_action(rows[0], name, pack) else None
    rows = [row for _, row in pairs if _names_action(row, name, pack)]
    return rows[0] if len(rows) == 1 else None


def _cell_handle(value) -> tuple[int, int] | None:
    """A stable place handle from the lazy view, read as a cell, or None."""
    if not _is_text(value):
        return None
    match = _CELL_HANDLE.match(value.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _lazy_action_name(name: str, pack: str) -> str:
    """The world's action name for a capability's view word (walk -> move), in the lazy interface only."""
    for action, word in load_pack(pack)["ACTION_WORDS"].items():
        if name == word:
            return action
    return name


def _fold_action(action, pack, affordances=None) -> dict:
    name = str(action["action"])
    handle = action.get("target") if isinstance(action.get("target"), str) else ""
    params = dict(action.get("params") or {})
    # An empty list is the lazy context's explicit "no menu": its capability rows carry no bindable handle, and
    # the reply's direct params are what the world validates. None keeps the old menu-mode pass-through.
    lazy = affordances is not None and not affordances
    if name == "attempt" and _is_text(params.get("verb")):
        params["verb"] = resolve_verb(params["verb"], pack) or params["verb"]
    row = bind_row(name, handle, affordances, pack)
    if row is not None:
        # The proposal takes the full affordance, as the simple backend sends it, and the world's action name
        # (a view word such as walk becomes move). The model's own fields are laid over it, except the handle.
        name = str(row["action"])
        params = {**{key: value for key, value in row.items() if key not in _NOT_PARAMS},
                  **{key: value for key, value in params.items() if key != "target"}}
    elif lazy:
        # No row to bind. Keep a thing id the model wrote as a direct param (never invent a row), and read a
        # place's stable cell handle as the move's destination. Capability rows use the view's action words.
        name = _lazy_action_name(name, pack)
        if handle:
            cell = _cell_handle(handle) if name == "move" else None
            if cell is not None:
                params["destination"] = cell
            else:
                params["target"] = handle
        if name == "move":
            destination = params.get("destination")
            if isinstance(destination, (list, tuple)) and len(destination) == 2:
                params["destination"] = (int(destination[0]), int(destination[1]))
            elif _is_text(destination):
                cell = _cell_handle(destination)
                if cell is not None:
                    params["destination"] = cell
    elif handle:
        params["target"] = handle
    held = action.get("with")
    if held is not None and held not in ("", "none"):
        params["tool" if name == "work" else "with"] = held
    if action.get("intensity") is not None:
        params["intensity"] = _weight(action["intensity"], intensity_value, pack)
    if params.get("amount") is not None:
        params["amount"] = _weight(params["amount"], amount_value, pack)
    return {"action": name, "params": params, "reason": action.get("reason") or ""}


def _count(notes: dict, key: str, n: int = 1) -> None:
    notes[key] = notes.get(key, 0) + n


def _memory(items, pack: str, text_limit: int, notes: dict) -> list[dict]:
    """The memory updates as the game reads them (Phase 071e). A kind the pack does not list is kept as a note, with
    the kind it named in the content (``named_kind``). Memory text that is blank is dropped and counted. Lessons over
    the packet's lessons_max are dropped oldest first (the reply's last lessons are the newest), and counted."""
    kinds = set(schema(pack)["memory_kinds"])
    lessons_max = int(load_pack(pack)["PROMPT_PACKET"]["lessons_max"])
    kept: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item["text"])
        if not text.strip():
            _count(notes, "memory_dropped")
            continue
        content = {"text": text[:text_limit]}
        kind = item["kind"]
        if kind not in kinds:
            content["named_kind"] = kind
            _count(notes, "memory_as_note")
            kind = "note"
        kept.append({"kind": kind, "content": content})
    lessons = [index for index, row in enumerate(kept) if row["kind"] == "lesson"]
    dropped = set(lessons[:max(0, len(lessons) - lessons_max)])
    if dropped:
        _count(notes, "lessons_dropped", len(dropped))
    return [row for index, row in enumerate(kept) if index not in dropped]


def to_wire(parsed: dict, pack: str, *, text_limit: int | None = None,
            affordances: list[dict] | None = None) -> dict:
    """The reply in the shape ActorResponse.from_dict reads. Assumes ``check`` returned no errors.

    ``affordances`` (the context's rows, as the world published them) lets a handle in major_action.target name
    a row, whose full params the proposal then takes (see ``bind_row``). Without it, a target is kept as the
    model wrote it.

    Phase 071e: the reply's accepted oddities are read as follows, and recorded in ``reply_notes`` (a dict that
    holds only the counts and flags that occurred). ``refusals`` lists the outcomes the game records as refusals
    ({action, reason}): blank speech is dropped with ``nothing_said``, and an empty continuation action starts nothing
    with ``no_task``. ``waiting: true`` is the explicit wait (any major action is dropped, ``major_action_ignored``)."""
    out = dict(parsed)
    notes: dict = {}
    refusals: list[dict] = []
    action = parsed.get("major_action")
    if isinstance(action, dict) and isinstance(action.get("action"), str):
        out["major_action"] = _fold_action(action, pack, affordances)
    if parsed.get("waiting") is True:
        if action is not None:
            _count(notes, "major_action_ignored")
        out["major_action"] = {"action": "wait", "params": {}, "reason": ""}
        _count(notes, "waiting")
    if parsed.get("utterances") is not None:
        spoken = []
        for item in parsed["utterances"]:
            if isinstance(item, dict) and isinstance(item.get("text"), str) and not item["text"].strip():
                refusals.append({"action": "speak", "reason": "nothing_said"})
                continue
            spoken.append(_utterance(item))
        out["utterances"] = spoken
    if isinstance(parsed.get("free_actions"), list):
        out["free_actions"] = [_fold_free(item, pack) for item in parsed["free_actions"] if isinstance(item, dict)]
    if parsed.get("memory_updates") is not None:
        limit = text_limit if text_limit is not None else int(schema(pack)["memory_text_chars"])
        out["memory_updates"] = _memory(parsed["memory_updates"], pack, limit, notes)
    continuation = parsed.get("continuation")
    if isinstance(continuation, dict) and isinstance(continuation.get("task"), dict) \
            and continuation["task"].get("action") == "":
        out["continuation"] = None
        refusals.append({"action": "continuation", "reason": "no_task"})
    if refusals:
        notes["refusals"] = refusals
    out["reply_notes"] = notes
    return out



def _utterance(item):
    if not isinstance(item, dict):
        return item
    row = {key: value for key, value in item.items() if key != "to"}
    row["target"] = item.get("to", item.get("target"))
    return row
