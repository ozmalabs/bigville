"""affordance_handles.py -- a stable, unique, readable handle for each affordance row (Phase 054 follow-up).

The world publishes each legal option as a row (``actor_affordances``). The agent view shows the row to a
model as ``{handle, action, what}``. The model copies the handle back into its reply, and the LLM backend
looks the row up by the same function. Both sides call ``affordance_handles`` on the same list, so a handle
in the view is exactly the key the backend resolves.

A handle is built from fields a resident may see:

* the world's own ``target`` key when the row has one (for example ``target:3``, an index the world assigns
  to a place, a container or a person for that turn; it is not a quantity);
* otherwise the action with the recipe (``work:burn_charcoal``), the sown crop and land (``sow:wheat:north``),
  the kind (``eat:bread``) or the animal (``tend_animals:chicken_1``);
* otherwise the action alone (``rest``).

No coordinate and no referee number is used. When two rows would get the same handle, the later row gets a
``#2``, ``#3`` ... suffix. The rows are in the world's order, so the suffix is deterministic for a given list.
"""
from __future__ import annotations

from typing import Any, Iterable

# The keys a handle is built from, in the order they are read. ``target`` is the world's own key.
_NAMED_KEYS = ("recipe", "kind", "animal")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def base_handle(row: dict[str, Any]) -> str:
    """The handle before collisions are resolved. Empty only for a row with no action and no target."""
    target = _text(row.get("target"))
    if target:
        return target
    action = _text(row.get("action"))
    if _text(row.get("sow_kind")):
        land = _text(row.get("land"))
        parts = [action, _text(row.get("sow_kind"))] + ([land] if land else [])
        return ":".join(part for part in parts if part)
    for key in _NAMED_KEYS:
        named = _text(row.get(key))
        if named:
            return f"{action}:{named}"
    return action


def affordance_handles(affordances: Iterable[dict[str, Any]]) -> list[str]:
    """One handle per row, in the same order as the rows. Two rows never share a handle."""
    used: set[str] = set()
    handles: list[str] = []
    for row in affordances:
        base = base_handle(dict(row)) or "option"
        handle, number = base, 1
        while handle in used:
            number += 1
            handle = f"{base}#{number}"
        used.add(handle)
        handles.append(handle)
    return handles


def handle_pairs(affordances: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """(handle, row) for each row, in order."""
    return list(zip(affordance_handles(affordances), affordances))
