"""reply_schema.py -- the reply a model must send back, checked against the pack (Phase 054).

The shape is the pack's PROMPT_REPLY table. A major action has the keys action, target, with, intensity and
params. Utterances are {to, text}. Memory updates are {kind, text} with a kind from the pack. Two functions:

* ``check(parsed, pack, lesson_limit=None)`` returns the errors in words (short fixed messages, no echo of
  the reply). Intensity and amounts take a number or a word from the lexicon. A word the lexicon does not know
  is an error that the repair call can fix. A verb the pack does not know is not an error: the world refuses
  it as unsupported, and that refusal is the consequence the resident learns from.
* ``to_wire(parsed, pack, affordances=...)`` returns the reply in the shape ActorResponse.from_dict reads: the
  major action's target, with and intensity folded into params (with a verb by its alias resolved, a word intensity
  turned into its value), utterance ``to`` read as ``target``, and each memory update as {kind, content: {text}}.
  A target that is a handle of a row in ``affordances`` (domains/affordance_handles.py) makes the proposal that row's
  full params, as the simple backend sends them, with the model's own fields laid over (``bind_row``).

Nothing here decides anything. It only reads words into the world's own vocabulary.
"""
from __future__ import annotations

from domains.affordance_handles import handle_pairs
from domains.lexicon import amount_value, intensity_value, resolve_verb
from domains.pack import load_pack

ERRORS_PER_RESPONSE = 5


def schema(pack: str) -> dict:
    """The PROMPT_REPLY table of the pack."""
    return load_pack(pack)["PROMPT_REPLY"]


def _is_text(value) -> bool:
    return isinstance(value, str)


def _words_list(words, limit=4) -> str:
    return ", ".join(sorted(str(w) for w in words)[:limit])


def _check_major_action(action, pack, errors) -> None:
    keys = set(schema(pack)["major_action_keys"])
    for key in sorted(action, key=str):
        if key not in keys:
            errors.append(f"major_action has no field '{str(key)[:24]}'")
    for name in ("target", "with"):
        if action.get(name) is not None and not _is_text(action.get(name)):
            errors.append(f"major_action.{name} must be a handle (text) or null")
    if action.get("intensity") is not None:
        try:
            intensity_value(action["intensity"], pack)
        except (TypeError, ValueError):
            words = list(load_pack(pack)["INTENSITY_WORDS"])
            errors.append("intensity must be a number or one of these words: " + _words_list(words, 6))
    params = action.get("params")
    if isinstance(params, dict):
        if params.get("verb") is not None and not _is_text(params["verb"]):
            errors.append("params.verb must be a verb name (text)")
        if params.get("amount") is not None:
            try:
                amount_value(params["amount"], pack)
            except (TypeError, ValueError):
                words = list(load_pack(pack)["AMOUNT_WORDS"])
                errors.append("params.amount must be a number or one of these words: " + _words_list(words, 6))


def check(parsed: dict, pack: str, *, lesson_limit: int | None = None) -> list[str]:
    """Schema errors for a reply that has already passed the structural checks. ``lesson_limit`` (set during a
    merge) is the most lesson updates the reply may carry."""
    spec = schema(pack)
    errors: list[str] = []
    action = parsed.get("major_action")
    if isinstance(action, dict):
        _check_major_action(action, pack, errors)
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
        if not _is_text(item.get("text", "")) or not str(item.get("text", "")).strip():
            errors.append("utterances need a text")
            break
    kinds = set(spec["memory_kinds"])
    lessons = 0
    for item in parsed.get("memory_updates", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") not in kinds:
            errors.append("memory_updates kind must be " + ", ".join(spec["memory_kinds"]))
            break
        if item.get("kind") == "lesson":
            lessons += 1
        if not _is_text(item.get("text")) or not str(item.get("text")).strip():
            errors.append("memory_updates need a text")
            break
    if lesson_limit is not None and lessons > lesson_limit:
        errors.append(f"at most {int(lesson_limit)} lessons can be kept; restate them in fewer memory_updates")
    return errors[:ERRORS_PER_RESPONSE]


_NOT_PARAMS = ("action", "score", "legal", "reason")


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


def _fold_action(action, pack, affordances=None) -> dict:
    name = str(action["action"])
    handle = action.get("target") if isinstance(action.get("target"), str) else ""
    params = dict(action.get("params") or {})
    if name == "attempt" and _is_text(params.get("verb")):
        params["verb"] = resolve_verb(params["verb"], pack) or params["verb"]
    row = bind_row(name, handle, affordances, pack)
    if row is not None:
        # The proposal takes the full affordance, as the simple backend sends it, and the world's action name
        # (a view word such as walk becomes move). The model's own fields are laid over it, except the handle.
        name = str(row["action"])
        params = {**{key: value for key, value in row.items() if key not in _NOT_PARAMS},
                  **{key: value for key, value in params.items() if key != "target"}}
    elif handle:
        params["target"] = handle
    held = action.get("with")
    if held is not None and held not in ("", "none"):
        params["tool" if name == "work" else "with"] = held
    if action.get("intensity") is not None:
        params["intensity"] = intensity_value(action["intensity"], pack)
    if params.get("amount") is not None:
        params["amount"] = amount_value(params["amount"], pack)
    return {"action": name, "params": params, "reason": action.get("reason") or ""}


def to_wire(parsed: dict, pack: str, *, text_limit: int | None = None,
            affordances: list[dict] | None = None) -> dict:
    """The reply in the shape ActorResponse.from_dict reads. Assumes ``check`` returned no errors.

    ``affordances`` (the context's rows, as the world published them) lets a handle in major_action.target name
    a row, whose full params the proposal then takes (see ``bind_row``). Without it, a target is kept as the
    model wrote it."""
    out = dict(parsed)
    action = parsed.get("major_action")
    if isinstance(action, dict) and action.get("action"):
        out["major_action"] = _fold_action(action, pack, affordances)
    if parsed.get("utterances") is not None:
        out["utterances"] = [_utterance(item) for item in parsed["utterances"]]
    if parsed.get("memory_updates") is not None:
        limit = text_limit if text_limit is not None else int(schema(pack)["memory_text_chars"])
        out["memory_updates"] = [{"kind": item["kind"], "content": {"text": str(item["text"])[:limit]}}
                                 for item in parsed["memory_updates"]]
    return out


def _utterance(item):
    if not isinstance(item, dict):
        return item
    row = {key: value for key, value in item.items() if key != "to"}
    row["target"] = item.get("to", item.get("target"))
    return row
