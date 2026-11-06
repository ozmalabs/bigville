"""Versioned prompt construction for external cognition providers.

Prompt construction is deliberately outside the world.  A provider receives
the character's durable identity and private held state plus the public world
context and legal affordances supplied by :class:`ActorContext`.

Phase 018: the system text comes from the data pack (premise, action vocabulary
with descriptions, boundary and continuation rules, response fields).  The
private part carries what the resident holds and a bounded selection of it,
chosen by the rule in the pack's PROMPT_SELECTION table:

* standing understood knowledge (laws, policies, concepts, kin terms, offices,
  procedures) up to ``max_standing_understood``;
* understood knowledge the situation touches, and aware-only items the
  situation touches given as name and gist only (never content or basis);
* the most recent non-derived memories, each text truncated;
* held frames, up to ``max_held_frames``.

Every record carries the prompt schema, the pack name, and a hash of the pack.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from domains.pack import canonical, load_pack

from .protocol import ActorContext


PROMPT_SCHEMA = "bigville/prompt/2"
DEFAULT_PACK = "bigville"

# Memory kinds that the derived knowledge priors (domains/knowledge.py) write.
_DERIVED_KINDS = ("awareness", "understanding", "recipe_knowledge")
# Memory kinds that hold a resident's own reading of a written law, policy, or reference.
_STANDING_KINDS = ("law_knowledge", "policy_knowledge", "reference_knowledge")
# Affordance and observation fields whose values name the things a turn touches.
_TOUCH_AFFORDANCE_KEYS = ("kind", "recipe", "trade", "item", "good", "target")

_HASHES: dict[str, str] = {}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def pack_hash(pack) -> str:
    """sha256 of the pack's base data, in domains.pack's canonical form. Cached per pack directory."""
    if pack.path not in _HASHES:
        _HASHES[pack.path] = hashlib.sha256(canonical(pack.base).encode("utf-8")).hexdigest()
    return _HASHES[pack.path]


def build_system_text(pack) -> str:
    """The system instructions for `pack`: premise, vocabulary, rules, and response fields."""
    premise = pack["WORLD_PREMISE"]
    lines = [
        f"You are one resident of {premise['name']}. {premise['premise']}",
        "",
        "Major actions: choose at most one, and only one listed in legal_affordances.",
    ]
    for name, spec in pack["MAJOR_ACTIONS"].items():
        lines.append(f"- {name}: {spec.get('description', spec.get('kind', ''))}")
    # Phase 050: the verbs an attempt may name (VERBS in the pack).
    lines.append("- attempt verbs: " + ", ".join(sorted(pack["VERBS"])) + ". A verb not listed is refused as unsupported.")
    lines += ["", "Free actions (communication; they use no major action):"]
    for name, spec in pack["FREE_ACTIONS"].items():
        lines.append(f"- {name}: {spec.get('description', spec.get('kind', ''))}")
    lines += ["", "Rules:"]
    lines += [f"- {rule}" for rule in pack["PROMPT_BOUNDARY_RULES"]]
    lines += [f"- {rule}" for rule in pack["PROMPT_CONTINUATION_RULES"]]
    lines += ["", "Return JSON with these fields: " + ", ".join(pack["PROMPT_RESPONSE_FIELDS"]) + "."]
    return "\n".join(lines)


@dataclass(frozen=True)
class PromptRecord:
    schema: str
    system: str
    context: dict[str, Any]
    pack: str = ""
    pack_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "pack": self.pack, "pack_hash": self.pack_hash,
                "system": self.system, "context": _plain(self.context)}

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def _bounded(content: Any, limit: int) -> Any:
    """Content as sent: a plain value within `limit` characters, else its text cut to `limit`."""
    text = content if isinstance(content, str) else json.dumps(_plain(content), sort_keys=True,
                                                               ensure_ascii=False)
    if len(text) <= limit:
        return _plain(content)
    return text[:limit] + "..."


def _is_derived(memory) -> bool:
    content = memory.content
    return (isinstance(content, dict) and "item" in content and "type" in content
            and "name" in content and memory.kind in _DERIVED_KINDS)


def _touched(context: ActorContext) -> tuple[set[str], list[tuple[int, int]]]:
    """Names of the things the turn touches, and the cells it points at (affordance destinations)."""
    names: set[str] = set()
    cells: list[tuple[int, int]] = []
    for action in context.affordances:
        if not isinstance(action, dict):
            continue
        for key in _TOUCH_AFFORDANCE_KEYS:
            value = action.get(key)
            if isinstance(value, str) and value:
                names.add(value)
        destination = action.get("destination")
        if isinstance(destination, (list, tuple)) and len(destination) == 2:
            cells.append((int(destination[0]), int(destination[1])))
    observations = context.observations
    for item in observations.get("held_items", []) or []:
        if isinstance(item, dict) and item.get("kind"):
            names.add(str(item["kind"]))
    names.update(str(key) for key in (observations.get("inventory") or {}))
    for item in observations.get("physical_objects", []) or []:
        if isinstance(item, dict) and item.get("kind"):
            names.add(str(item["kind"]))
    for resident in observations.get("nearby_residents", []) or []:
        if isinstance(resident, dict) and resident.get("name"):
            names.add(str(resident["name"]))
    return names, cells


def _near(cell, cells, radius: int) -> bool:
    """Chebyshev distance in cells to the actor's position or an affordance destination."""
    if cell is None:
        return False
    x, y = int(cell[0]), int(cell[1])
    return any(max(abs(x - cx), abs(y - cy)) <= radius for cx, cy in cells)


def _content_dict(memory) -> dict[str, Any]:
    return memory.content if isinstance(memory.content, dict) else {}


def _sort_name(memory) -> tuple[str, str]:
    content = _content_dict(memory)
    return (str(content.get("type", memory.kind)), str(content.get("name", memory.memory_id)))


def select_knowledge(character, context: ActorContext, selection: dict[str, Any]):
    """The bounded selection of a resident's held memories for one prompt (the rule is in the pack).

    Returns ``(knowledge, memories, counts, frames)``. ``knowledge`` has ``understood`` (the full held
    entries, without basis) and ``aware`` (name and gist only). ``memories`` are the non-derived memories
    chosen, ``frames`` the held frames chosen, and ``counts`` how many were held and how many were shown."""
    touched, cells = _touched(context)
    position = context.observations.get("position")
    anchors = list(cells) + ([(int(position[0]), int(position[1]))] if position else [])
    radius = int(selection["place_radius"])
    standing_types = set(selection["standing_types"])

    def touches(memory) -> bool:
        content = _content_dict(memory)
        if content.get("name") in touched or content.get("recipe") in touched:
            return True
        place = content.get("position")
        return content.get("type") == "place" and isinstance(place, (list, tuple)) and _near(
            place, anchors, radius)

    standing, relevant, aware, episodic = [], [], [], []
    for index, memory in enumerate(character.memories):
        if _is_derived(memory):
            content = memory.content
            understood = content.get("understands", 0) > 0
            if understood and content["type"] in standing_types:
                standing.append(memory)
            elif understood and touches(memory):
                relevant.append(memory)
            elif not understood and touches(memory):
                aware.append(memory)
        elif memory.kind in _STANDING_KINDS:
            standing.append(memory)
        elif memory.kind == "recipe_knowledge" and _content_dict(memory).get("recipe"):
            if touches(memory):
                relevant.append(memory)
        else:
            episodic.append((index, memory))

    standing.sort(key=_sort_name)
    relevant.sort(key=_sort_name)
    aware.sort(key=_sort_name)
    episodic.sort(key=lambda pair: (-int(pair[1].turn), -pair[0]))

    standing_shown = standing[:int(selection["max_standing_understood"])]
    relevant_shown = relevant[:int(selection["max_relevant_understood"])]
    aware_shown = aware[:int(selection["max_relevant_aware"])]
    episodic_shown = [memory for _, memory in episodic[:int(selection["max_recent_episodic"])]]
    frames_shown = list(character.held_frames[:int(selection["max_held_frames"])])
    limit = int(selection["max_memory_text"])
    gist = selection["gist"]

    understood, memories = [], []
    for memory in standing_shown + relevant_shown:
        if _is_derived(memory):
            content = memory.content
            entry = {"item": content["item"], "type": content["type"], "name": content["name"],
                     "understands": content["understands"]}
            for key in ("location", "position", "landmark"):
                if key in content:
                    entry[key] = content[key]
            understood.append(entry)
        else:
            memories.append(_memory_entry(memory, limit))
    aware_entries = []
    for memory in aware_shown:
        content = memory.content
        aware_entries.append({"item": content["item"], "type": content["type"], "name": content["name"],
                              "gist": gist.get(content["type"], gist.get("default", ""))})
    for memory in episodic_shown:
        memories.append(_memory_entry(memory, limit))
    counts = {
        "held_memories": len(character.memories),
        "shown_memories": len(memories),
        "shown_understood": len(understood),
        "shown_aware": len(aware_entries),
        "held_frames": len(character.held_frames),
        "shown_frames": len(frames_shown),
    }
    return {"understood": understood, "aware": aware_entries}, memories, counts, frames_shown


def _memory_entry(memory, limit: int) -> dict[str, Any]:
    return {"memory_id": memory.memory_id, "kind": memory.kind, "turn": int(memory.turn),
            "content": _bounded(memory.content, limit)}


class PromptBuilder:
    """Build stable, replayable prompts from an actor context and a data pack."""

    def __init__(self, *, schema: str = PROMPT_SCHEMA, pack: str = DEFAULT_PACK):
        self.schema = schema
        self.pack = load_pack(pack)
        self.pack_hash = pack_hash(self.pack)
        self.system = build_system_text(self.pack)
        selection = dict(self.pack["PROMPT_SELECTION"])
        selection["gist"] = dict(self.pack["MEMORY_GIST"])
        self.selection = selection

    def build(self, context: ActorContext) -> PromptRecord:
        character = context.character
        knowledge, memories, counts, frames = select_knowledge(character, context, self.selection)
        private = {
            "identity": _plain(character.identity),
            "personality": _plain(character.personality),
            "knowledge": knowledge,
            "memories": memories,
            "held_frames": [_plain(f.to_dict()) for f in frames],
            "selection": counts,
            "backend": _plain(character.backend),
        }
        public = {
            "turn": int(context.turn),
            "observations": _plain(context.observations),
            "legal_affordances": _plain(context.affordances),
            "recipient_interfaces": _plain(context.recipient_interfaces),
        }
        outcome = context.observations.get("last_outcome")
        if outcome:
            # Phase 021: the resident's own last major action, with what its refusal reason means.
            public["last_outcome"] = self._outcome_entry(outcome)
        return PromptRecord(self.schema, self.system, {"private": private, "public": public},
                            pack=self.pack.name, pack_hash=self.pack_hash)

    def _outcome_entry(self, outcome) -> dict[str, Any]:
        entry = _plain(outcome)
        reason = entry.get("reason")
        if reason:
            entry["meaning"] = self.pack["REFUSAL_REASONS"].get(reason, {}).get("description", "")
        return entry


def build_prompt(context: ActorContext) -> PromptRecord:
    return PromptBuilder().build(context)
