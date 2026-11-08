"""handle_map.py -- the handles an LLM resident sees are the harness's own tokens (Phase 054b).

The world names things by their ids (``knife_1``), affordance rows by their action, recipe, kind or the per-turn
``target:N`` key (domains/affordance_handles.py), and places by their cell (``cell:x,y``). A resident that reads those
names learns the world's identity: a wrong percept of an object whose id is its kind word shows the true kind, and a
cell names a coordinate. So the LLM harness shows opaque tokens instead, and reads the model's reply back to the
world's own handles before the reply reaches the game.

What this module does, per resident:

* ``mask_context`` returns the context with its agent view copied, and each handle in ``around.things``, ``can`` and
  ``reaction.options`` replaced by a token. ``mask_choices`` does the same for the reaction options in a consult.
  The packet is built from the masked context, so the prompt, the thread and the log hold tokens only.
* A token is assigned in order of first appearance and kept for the run. Its identity is the world's name for the
  thing (an id, a cell) or, for an affordance row, the row's identity fields without the per-turn ``target:N`` key
  (the same row keeps its token when the index changes). Identical identities in one view get a ``#2`` suffix.
* ``translate`` reads a reply back. A token that the current view offered becomes the world's handle that view showed,
  so ``bind_row``, the lazy cell handling and the world see what they always saw. A reply that uses a token the view
  did not offer, or a world handle it was never shown, is an error (the repair path). The error text names no id.
* ``referee`` returns token -> world handle for the tokens of one call. The LLM log keeps it beside the call; the
  prompt the provider receives has no such field.

Tokens are ``hx`` followed by letters only (``hxa``, ``hxb``, ... ``hxaa``). Letters, not digits, because the Phase 052
leak guard (bigville/learning_eval.py) reports a number in a phrase. ``hx`` is not an English word and the packs' ids
do not use it.

The state (``to_dict`` / ``restore``) is in the LLM backend's state, so a saved game continues with the same tokens.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Iterable

from domains.affordance_handles import handle_pairs

PREFIX = "hx"
TOKEN = re.compile(r"^hx[a-z]+$")
TOKEN_IN_TEXT = re.compile(r"\bhx[a-z]+\b")
ERRORS_PER_RESPONSE = 5
UNKNOWN_HANDLE = ("a handle in the reply is not one of the handles in your view; "
                  "copy a handle exactly from public.can or public.around.things")
# The reply's fields that name a thing, a place or a row (their values are handles, not words). `target` is the major
# action's and each free action's target; `option` is a reaction choice (read only in a reaction).
HANDLE_PARAM_KEYS = ("target", "object_id", "container", "source", "animal", "crop_node", "land", "project", "patient",
                     "destination", "recipient", "name", "joint", "item", "note")
# The private rows that carry handles (a note a resident holds, a request made to it). Phase 071d lists them in the
# packet; they are masked like the public rows, and first, because the packet lists the private part first.
SELF_HANDLE_LISTS = ("giveable_notes", "requests")
# The fields of an affordance row that name what it acts on, without the per-turn ``target`` key.
IDENTITY_FIELDS = ("action", "object_id", "kind", "recipe", "trade", "sow_kind", "with", "container", "source",
                   "destination", "recipient", "patient", "project", "name", "animal", "land", "crop_node", "joint")


def letters(number: int) -> str:
    """Bijective base 26: 1 -> a, 26 -> z, 27 -> aa."""
    if number < 1:
        raise ValueError("a token number starts at 1")
    out = ""
    while number:
        number, rest = divmod(number - 1, 26)
        out = chr(ord("a") + rest) + out
    return out


def _unique(identity: str, seen: dict[str, int]) -> str:
    """The identity, with ``|2``, ``|3`` ... for the second and later occurrence within one view."""
    count = seen.get(identity, 0) + 1
    seen[identity] = count
    return identity if count == 1 else f"{identity}|{count}"


def _row_identity(raw: str, rows: dict[str, dict[str, Any]]) -> str:
    row = rows.get(raw)
    if row is None:
        return "raw|" + raw
    body = {key: row[key] for key in IDENTITY_FIELDS if key in row}
    return "row|" + json.dumps(body, sort_keys=True, default=str)


class HandleMap:
    """One resident's handles: identity -> token, token -> the world handle last shown, and the handles shown."""

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}          # identity -> token (kept for the run)
        self.labels: dict[str, str] = {}       # token -> the world's handle (the latest one shown)
        self.raw_seen: set[str] = set()        # every world handle ever shown: a reply may not copy one
        self.count = 0
        self.offered: dict[str, str] = {}      # this consult's tokens -> the world handle they stand for

    # -- assignment ----------------------------------------------------------------------------
    def _bind(self, identity: str, raw: str, offered: dict[str, str]) -> str:
        token = self.ids.get(identity)
        if token is None:
            self.count += 1
            token = PREFIX + letters(self.count)
            self.ids[identity] = token
        self.labels[token] = raw
        self.raw_seen.add(raw)
        offered[token] = raw
        return token

    def mask_context(self, context):
        """The context with its agent view masked. The rest of the context is the same object's values."""
        view = getattr(context, "agent_view", None)
        self.offered = {}
        if not isinstance(view, dict):
            return context
        rows = {handle: row for handle, row in handle_pairs(list(context.affordances or []))}
        return dataclasses.replace(context, agent_view=self._mask_view(view, rows))

    def mask_choices(self, options: Iterable[Any]) -> list[str]:
        """The reaction options of a consult, as tokens (the same tokens the masked view shows)."""
        seen: dict[str, int] = {}
        return [self._bind(_unique("reaction|" + str(option), seen), str(option), self.offered)
                for option in options]

    def _mask_view(self, view: dict[str, Any], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
        out = dict(view)
        seen: dict[str, int] = {}
        own = view.get("self")
        if isinstance(own, dict) and any(isinstance(own.get(key), list) for key in SELF_HANDLE_LISTS):
            fixed_self = dict(own)
            for key in SELF_HANDLE_LISTS:
                if isinstance(own.get(key), list):
                    fixed_self[key] = [self._masked_row(row, key + "|", seen) for row in own[key]]
            out["self"] = fixed_self
        around = view.get("around")
        if isinstance(around, dict) and isinstance(around.get("things"), list):
            things = []
            for row in around["things"]:
                if isinstance(row, dict) and row.get("handle"):
                    raw = str(row["handle"])
                    row = {**row, "handle": self._bind(_unique("thing|" + raw, seen), raw, self.offered)}
                things.append(row)
            out["around"] = {**around, "things": things}
        if isinstance(view.get("can"), list):
            can = []
            for row in view["can"]:
                if isinstance(row, dict) and row.get("handle"):
                    raw = str(row["handle"])
                    identity = _unique(_row_identity(raw, rows), seen)
                    row = {**row, "handle": self._bind(identity, raw, self.offered)}
                can.append(row)
            out["can"] = can
        reaction = view.get("reaction")
        if isinstance(reaction, dict) and isinstance(reaction.get("options"), list):
            options = []
            for option in reaction["options"]:
                if isinstance(option, dict) and option.get("choice") is not None:
                    raw = str(option["choice"])
                    option = {**option, "choice": self._bind(_unique("reaction|" + raw, seen), raw, self.offered)}
                options.append(option)
            out["reaction"] = {**reaction, "options": options}
        return out

    def _masked_row(self, row: Any, prefix: str, seen: dict[str, int]) -> Any:
        if isinstance(row, dict) and row.get("handle"):
            raw = str(row["handle"])
            return {**row, "handle": self._bind(_unique(prefix + raw, seen), raw, self.offered)}
        return row

    # -- reading a reply back -----------------------------------------------------------------
    def _resolve(self, value: Any, errors: list[str]) -> Any:
        if not isinstance(value, str):
            return value
        if TOKEN.match(value):
            if value in self.offered:
                return self.offered[value]
            errors.append(UNKNOWN_HANDLE)
            return value
        if value in self.raw_seen:
            # A world handle the resident was shown in some view: it must be copied as the token instead.
            errors.append(UNKNOWN_HANDLE)
        return value

    def _fields(self, fields: dict[str, Any], errors: list[str], reaction: bool) -> dict[str, Any]:
        out = dict(fields)
        for key in HANDLE_PARAM_KEYS:
            if key in out:
                out[key] = self._resolve(out[key], errors)
        if reaction and "option" in out:
            out["option"] = self._resolve(out["option"], errors)
        return out

    def translate(self, parsed: dict[str, Any], *, reaction: bool = False) -> tuple[dict[str, Any], list[str]]:
        """The reply with its handles read back to the world's (a copy), and the errors for a handle that is not one
        the view offered. ``reaction`` also reads ``major_action.action`` (a reaction names its choice there)."""
        errors: list[str] = []
        out = dict(parsed)
        action = parsed.get("major_action")
        if isinstance(action, dict):
            fixed = dict(action)
            if reaction and isinstance(fixed.get("action"), str):
                fixed["action"] = self._resolve(fixed["action"], errors)
            if "target" in fixed:
                fixed["target"] = self._resolve(fixed["target"], errors)
            if isinstance(fixed.get("params"), dict):
                fixed["params"] = self._fields(fixed["params"], errors, reaction)
            out["major_action"] = fixed
        free = parsed.get("free_actions")
        if isinstance(free, list):
            items = []
            for item in free:
                if isinstance(item, dict):
                    fixed = dict(item)
                    if "target" in fixed:
                        fixed["target"] = self._resolve(fixed["target"], errors)
                    if isinstance(fixed.get("params"), dict):
                        fixed["params"] = self._fields(fixed["params"], errors, False)
                    items.append(fixed)
                else:
                    items.append(item)
            out["free_actions"] = items
        return out, errors[:ERRORS_PER_RESPONSE]

    # -- the log's referee side -----------------------------------------------------------------
    def referee(self, *texts: str) -> dict[str, str]:
        """token -> the world's handle, for each token the texts carry (the log's referee field)."""
        found: set[str] = set()
        for text in texts:
            found.update(TOKEN_IN_TEXT.findall(text))
        return {token: self.labels[token] for token in sorted(found) if token in self.labels}

    # -- stop and resume ------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"ids": dict(sorted(self.ids.items())), "labels": dict(sorted(self.labels.items())),
                "raw_seen": sorted(self.raw_seen), "count": self.count}

    def restore(self, data: dict[str, Any] | None) -> None:
        """Load the state written by ``to_dict``. None (a state saved before Phase 054b) starts an empty map."""
        data = data or {}
        self.ids = {str(k): str(v) for k, v in dict(data.get("ids") or {}).items()}
        self.labels = {str(k): str(v) for k, v in dict(data.get("labels") or {}).items()}
        self.raw_seen = {str(v) for v in data.get("raw_seen") or []}
        self.count = int(data.get("count") or 0)
        self.offered = {}
