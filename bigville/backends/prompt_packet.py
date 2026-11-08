"""prompt_packet.py -- the LLM prompt packet, built from the agent view only (Phase 054).

`build_packet(context, ...)` returns the packet's context (private and public parts) and a meta dict for the
backend. Every value comes from `context.agent_view` (domains/agent_view.py), so the model sees words and
the whitelisted keys. Two things come from the resident's own memory and routine: the list of lesson memories
(their texts are in the view; their ids are kept in the meta for a merge) and the "usual now" sentence (the
routine's words, from domains/autopilot.py). Neither carries a number.

The packet has these parts, in this order:

* private.lead: who the resident is, what they would usually do now, the persona card (traits, past, usual
  day, close ties). The usual-now line comes first, so any departure from it is a choice.
* private: body, skills, carrying, knows, places, kin, lessons (every lesson held, with a merge request once
  the count is above the pack's lessons_max) and the most recent notes.
* public: now, around (people, seen, things), map, can, last, heard (other people's speech, as quotes under a
  standing rule), and consult (why the model was asked, when it was asked).

Caps are per section (PROMPT_PACKET.caps, characters of JSON). A list section over its cap drops its last items
and the count is reported in `omitted`. Lessons are never dropped: a merge must see every lesson it replaces. A
dict section is measured, not cut. `sizes` reports the characters of every section.
"""
from __future__ import annotations

import json
import re
from typing import Any

from domains.autopilot import usual_words
from domains.pack import load_pack

PACKET_SCHEMA = "bigville/prompt/6"   # Phase 054b: handles are the harness's tokens; the lazy text names no id or cell (071c: prompt/5)
LESSON_KIND = "lesson"


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _cut(text: Any, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:max(limit - 3, 0)] + "..."


def _interface_lines(pk: dict) -> list[str]:
    intensity = ", ".join(sorted(str(word) for word in pk["INTENSITY_WORDS"]))
    amounts = ", ".join(sorted(str(word) for word in pk["AMOUNT_WORDS"]))
    verbs = ", ".join(sorted(name for name, spec in pk["VERBS"].items() if spec.get("implemented") is not False))
    free = ", ".join(sorted(str(name) for name in pk["FREE_ACTIONS"]))
    lines = []
    for line in pk["PROMPT_PACKET"]["interface"]:
        lines.append(line.replace("{intensity}", intensity).replace("{verbs}", verbs).replace("{amounts}", amounts)
                     .replace("{free_actions}", free))
    return lines


def packet_system(pack: str, *, lazy: bool = False) -> str:
    """The system text of the packet: the premise, the actions, the rules and the reply interface, from the pack.

    ``lazy`` (LA05) keeps every pack rule unchanged and adds the proposal contract of the lazy path: public.can
    lists capabilities, not the legal menu, and the resident names the direct params the world will validate.
    Menu mode gets exactly the text it had before."""
    pk = load_pack(pack)
    tbl = pk["PROMPT_PACKET"]
    premise = pk["WORLD_PREMISE"]
    intro = ("Major actions: choose at most one. public.can lists the capabilities you may use; they are not "
             "an exhaustive list of legal actions, and the world may refuse a proposal."
             if lazy else
             "Major actions: choose at most one. The actions you can take are listed in public.can.")
    lines = [f"You are one resident of {premise['name']}. {premise['premise']}", "", intro]
    for name, spec in pk["MAJOR_ACTIONS"].items():
        description = str(spec.get("description", spec.get("kind", "")))
        if description.startswith("Retired"):
            continue
        # A description with a digit in it is a number the model is not told: such an action is named, and the
        # reply interface below says how to use it (attempt is the case).
        lines.append(f"- {name}: {description}" if description and not re.search(r"\d", description) else f"- {name}")
    lines += ["", "Speech is free: it uses no major action."]
    # Phase 071c: the free actions a reply may carry (reply interface below). Names with a digit in the
    # description are named only, as the major actions are.
    lines += ["", "Free actions (they use no major action):"]
    for name, spec in pk["FREE_ACTIONS"].items():
        description = str(spec.get("description", spec.get("kind", "")))
        lines.append(f"- {name}: {description}" if description and not re.search(r"\d", description) else f"- {name}")
    lines += ["", "Rules:"] + [f"- {rule}" for rule in tbl["system_rules"]]
    lines += ["", "Reply interface:"] + [f"- {line}" for line in _interface_lines(pk)]
    if lazy:
        lines += ["", "Proposing in this mode:",
                  "- A public.can row names a capability. Its handle may be empty; do not copy a handle from it.",
                  "- Put the direct details in major_action.params: kind, recipe, object_id, destination, "
                  "recipient, container, source, animal, crop_node, land, project, patient, name.",
                  "- For walk, copy a place handle from public.around.things into major_action.target.",
                  "- Name a recipe from public.self.knows, a carried kind from public.self.carrying, a person by "
                  "name from public.around, and a thing by its handle from public.around.things.",
                  "- The world checks the proposal against what exists. A refusal is ordinary: it is shown in "
                  "public.last on the next turn."]
    return "\n".join(lines)


def _labels(tbl: dict, key: str, **fields) -> str:
    text = tbl["labels"][key]
    for name, value in fields.items():
        text = text.replace("{" + name + "}", str(value or ""))
    return text


def _lesson_ids(character) -> list[str]:
    """The ids of the lesson memories, in the order the view lists their texts (the same filter)."""
    return [memory.memory_id for memory in character.memories
            if memory.kind == LESSON_KIND and isinstance(memory.content, dict)
            and isinstance(memory.content.get("text"), str)]


class _Caps:
    """Applies the per-section caps and records what was measured and what was dropped."""

    def __init__(self, caps: dict):
        self.caps = caps
        self.sizes: dict[str, int] = {}
        self.omitted: dict[str, int] = {}

    def items(self, section: str, rows: list) -> list:
        """A list section: the first items that fit its cap (the view lists the oldest first, so the
        newest are dropped last)."""
        kept = list(rows)
        dropped = 0
        while kept and _size(kept) > int(self.caps[section]):
            kept.pop()
            dropped += 1
        if dropped:
            self.omitted[section] = dropped
        self.sizes[section] = _size(kept)
        return kept

    def measure(self, section: str, value):
        self.sizes[section] = _size(value)
        return value


def build_packet(context, *, pack: str, consult_reason: str | None = None,
                 choices: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The packet's context and a meta dict ``{"lesson_ids", "merge", "lessons_held"}``.

    ``context.agent_view`` must be a view (the caller checks). ``consult_reason`` and ``choices`` are set when
    the model is consulted; a reaction (Phase 029) passes its offered options as ``choices``."""
    pk = load_pack(pack)
    tbl = pk["PROMPT_PACKET"]
    view = context.agent_view or {}
    character = context.character
    self_view = view.get("self") or {}
    around = view.get("around") or {}
    persona = self_view.get("persona") or {}
    caps = _Caps(tbl["caps"])

    usual = usual_words(dict(character.identity or {}), context.observations.get("calendar"), pack)
    lead = [_labels(tbl, "who", name=self_view.get("name"), job=self_view.get("job"),
                    life_stage=self_view.get("life_stage"), age=self_view.get("age")),
            usual]
    for key in ("traits", "life", "usual_day", "ties"):
        if key == "traits" and persona.get(key):
            lead.append(_labels(tbl, "traits", traits=persona[key]))
        elif key == "life" and persona.get(key):
            lead.append(_labels(tbl, "life", life=persona[key]))
        elif key == "usual_day" and persona.get(key):
            lead.append(_labels(tbl, "usual_day", usual_day=persona[key]))
        elif key == "ties" and persona.get(key):
            lead.append(_labels(tbl, "ties", ties=persona[key]))
    lead = [line for line in lead if line]

    lesson_texts = list(self_view.get("lessons") or [])
    lesson_chars = int(tbl["lesson_chars"])
    lessons_max = int(tbl["lessons_max"])
    kept = [_cut(text, lesson_chars) for text in lesson_texts]
    merge = tbl["merge_text"].replace("{max}", str(lessons_max)) if len(kept) > lessons_max else ""
    lessons = {"kept": caps.measure("lessons", kept)}
    if merge:
        lessons["merge"] = merge

    notes = [_cut(text, int(tbl["note_chars"])) for text in (self_view.get("notes") or [])][-int(tbl["notes_max"]):]
    private = {
        "lead": caps.measure("lead", lead),
        "body": caps.measure("body", self_view.get("body") or {}),
        "skills": caps.items("skills", self_view.get("skills") or []),
        "carrying": caps.measure("carrying", self_view.get("carrying") or {}),
        "knows": caps.items("knows", self_view.get("knows") or []),
        "places": caps.items("places", self_view.get("places") or []),
        "kin": caps.items("kin", self_view.get("kin") or []),
        "lessons": lessons,
        "notes": caps.items("notes", notes),
    }

    heard = [{"from": row.get("from", ""), "quote": _cut(row.get("text", ""), int(tbl["speech_chars"]))}
             for row in (around.get("heard") or [])][-int(tbl["speech_max"]):]
    rule = tbl["speech_rule"]
    budget = int(tbl["caps"]["heard"]) - _size({"rule": rule, "quotes": []})
    quotes = []
    for row in heard:
        if _size(quotes + [row]) > budget:
            caps.omitted["heard"] = caps.omitted.get("heard", 0) + 1
            continue
        quotes.append(row)
    public = {
        "now": caps.measure("now", view.get("now") or {}),
        "around": {
            "people": caps.items("people", around.get("people") or []),
            "seen": caps.items("seen", around.get("seen") or []),
            "things": caps.items("things", around.get("things") or []),
        },
        "map": caps.measure("map", view.get("map") or {}),
        "can": caps.items("can", view.get("can") or []),
        "last": caps.measure("last", view.get("last") or {}),
        "heard": caps.measure("heard", {"rule": rule, "quotes": quotes}),
    }
    # Phase 064: written marks in sight go in the packet only when the view carries them (reading on). Off, the
    # packet is byte-for-byte what it was before.
    if around.get("writing"):
        public["around"]["writing"] = caps.items("writing", around["writing"])
    if consult_reason is not None:
        consult = {"why_consulted": consult_reason, "rules": tbl["consult_rules"]}
        if choices:
            consult["choices"] = [str(choice) for choice in choices]
        public["consult"] = caps.measure("consult", consult)

    context_dict = {"private": private, "public": public}
    sizes = dict(caps.sizes)
    sizes["total"] = sum(sizes.values())
    context_dict["sizes"] = sizes
    if caps.omitted:
        context_dict["omitted"] = dict(sorted(caps.omitted.items()))
    meta = {"lesson_ids": _lesson_ids(character), "merge": bool(merge), "lessons_held": len(kept)}
    return context_dict, meta
