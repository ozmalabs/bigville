"""prompt_packet_check.py -- self-test checks for the LLM prompt packet and reply schema (Phase 054).

    check_prompt_packet(pack, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It reads the pack with
domains/pack.load_pack, and checks:
- PROMPT_PACKET has a positive cap for every section the packet builder measures, and positive item and
  character limits;
- the packet's own structural keys (packet_keys) cover every key the builder writes;
- the labels, merge text and consult rules are present, and the merge text names its {max};
- the interface lines use only the placeholders the builder fills (intensity, verbs, amounts), and the words
  they name resolve in the lexicon (every intensity and amount word is a number in words, and every named verb
  is a verb the world runs);
- PROMPT_REPLY names the keys and memory kinds the reply checker reads, and includes the lesson kind;
- the agent view whitelist carries the keys the packet reads: self.lessons, around.things and the thing rows.
"""
from __future__ import annotations

import re

from domains.lexicon import amount_value, intensity_value
from domains.pack import PackError, load_pack

SECTIONS = ("lead", "body", "skills", "carrying", "knows", "places", "kin", "lessons", "notes", "now",
            "people", "seen", "things", "heard", "map", "can", "last", "consult")
STRUCTURAL = ("private", "public", "lead", "lessons", "kept", "merge", "notes", "heard", "quotes", "rule",
              "quote", "from", "consult", "why_consulted", "rules", "choices", "sizes", "omitted")
LABELS = ("who", "traits", "life", "usual_day", "ties")
PLACEHOLDERS = ("intensity", "verbs", "amounts")
MEMORY_KINDS = ("note", "lesson", "place_belief", "plan")
REPLY_KEYS = ("action", "target", "with", "intensity", "params", "reason")


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def check_prompt_packet(pack, errors, warnings, info):
    try:
        pk = load_pack(pack)
    except PackError as exc:
        errors.append(f"PROMPT_PACKET: cannot load the pack: {exc}")
        return
    tbl = pk["PROMPT_PACKET"]
    reply = pk["PROMPT_REPLY"]
    caps = tbl["caps"]
    for section in SECTIONS:
        if not _whole(caps.get(section)):
            errors.append(f"PROMPT_PACKET: caps.{section} must be a whole number of at least 1")
    for key in ("lessons_max", "lesson_chars", "notes_max", "note_chars", "speech_max", "speech_chars"):
        if not _whole(tbl.get(key)):
            errors.append(f"PROMPT_PACKET: {key} must be a whole number of at least 1")
    for key in STRUCTURAL:
        if key not in tbl["packet_keys"]:
            errors.append(f"PROMPT_PACKET: packet_keys lacks the structural key '{key}'")
    for key in LABELS:
        if not str(tbl["labels"].get(key, "")).strip():
            errors.append(f"PROMPT_PACKET: labels.{key} is missing or empty")
    if "{max}" not in tbl.get("merge_text", ""):
        errors.append("PROMPT_PACKET: merge_text must name the limit as {max}")
    if "carries on as usual" not in tbl.get("consult_rules", "") or "wait" not in tbl.get("consult_rules", ""):
        errors.append("PROMPT_PACKET: consult_rules must say that a reply with no major_action carries on, and how to wait")
    if not str(tbl.get("speech_rule", "")).strip():
        errors.append("PROMPT_PACKET: speech_rule is missing")
    for line in tbl["interface"]:
        for name in re.findall(r"\{([a-z_]+)\}", line):
            if name not in PLACEHOLDERS:
                errors.append(f"PROMPT_PACKET: interface line uses an unknown placeholder {{{name}}}")
    intensity_words = list(pk["INTENSITY_WORDS"])
    amount_words = list(pk["AMOUNT_WORDS"])
    if not intensity_words or not amount_words:
        errors.append("PROMPT_PACKET: the lexicon has no intensity or amount words for the reply to name")
    for word in intensity_words:
        try:
            intensity_value(word, pack)
        except (TypeError, ValueError) as exc:
            errors.append(f"PROMPT_PACKET: intensity word '{word}' does not resolve: {exc}")
    for word in amount_words:
        try:
            amount_value(word, pack)
        except (TypeError, ValueError) as exc:
            errors.append(f"PROMPT_PACKET: amount word '{word}' does not resolve: {exc}")
    running = {name for name, spec in pk["VERBS"].items() if spec.get("implemented") is not False}
    if not running:
        errors.append("PROMPT_PACKET: the pack runs no verbs for an attempt to name")
    for key in REPLY_KEYS:
        if key not in reply["major_action_keys"]:
            errors.append(f"PROMPT_REPLY: major_action_keys lacks '{key}'")
    for key in ("to", "text"):
        if key not in reply["utterance_keys"]:
            errors.append(f"PROMPT_REPLY: utterance_keys lacks '{key}'")
    unknown = [kind for kind in reply["memory_kinds"] if kind not in MEMORY_KINDS]
    if unknown or "lesson" not in reply["memory_kinds"]:
        errors.append("PROMPT_REPLY: memory_kinds must be note, lesson, place_belief and plan, with lesson among them")
    if not _whole(reply.get("memory_text_chars")):
        errors.append("PROMPT_REPLY: memory_text_chars must be a whole number of at least 1")
    whitelist = pk["AGENT_VIEW_WHITELIST"]
    for section, key in (("self", "lessons"), ("around", "things"), ("thing", "handle"), ("thing", "what")):
        if key not in whitelist.get(section, []):
            errors.append(f"PROMPT_PACKET: the agent view whitelist lacks {section}.{key}, which the packet reads")
    if not errors:
        info.append(f"PROMPT_PACKET ({pk.name}): all prompt packet checks pass ({len(intensity_words)} intensity "
                    f"words, {len(running)} verbs, lessons kept to {tbl['lessons_max']})")
