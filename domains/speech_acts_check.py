"""speech_acts_check.py -- self-test checks for the SPEECH_ACTS table and SPEECH_UNDERSTANDING (Phase 060).

Called from bigville_entities.check_consistency with the pack path. The acts are checked against three
sources of wording and emission:
  * conversation.DEFAULT_TEMPLATES: every template key is claimed by exactly one act, and every act that
    names a template has that key. An act with no template and no realised meaning is an error, and so is
    a template with no act.
  * the kinds the simple speakers emit: DeterministicSpeechBackend._meaning (the Ocelot mind's seam) and
    the `act, slots = "..."` assignments of cheap.py _speech. Each emitted kind must be a row, and each row
    marked as emitted must be emitted.
  * the grammar: every pattern compiles, and every template that can be a pattern places back as its own
    act when it is rendered with sample slot values.
"""
from __future__ import annotations

import inspect
import os
import re

from domains import speech_grammar as G
from domains.pack import load_pack

ROW_KEYS = ("act", "slots", "description", "understood_by", "emitted_by", "template", "meaning", "patterns",
            "lexicon", "lexicon_slot")
EMITTERS = ("simple_meaning", "simple_message", "message")
REALISED = ("greeting", "topic", "weather", "warning", "uncertainty", "acknowledgement", "request", "offer",
            "question", "thanks", "apology", "farewell", "complaint", "promise", "news", "inform", "purchase")
EFFECT_RANGES = {   # name: (low, high, is_int)
    "tie_min": (0.0, 1.0, False), "raw_confidence": (0.0, 1.0, False), "grammar_confidence": (0.0, 1.0, False),
    "stranger_factor": (0.0, 1.0, False), "caution_min_confidence": (0.0, 1.0, False),
    "caution_ticks": (0, 10000, True), "goal_ticks": (0, 10000, True), "goal_priority": (0.0, 1000.0, False),
    "goal_bonus": (0.0, 1000.0, False), "reply_ticks": (0, 10000, True), "greet_gap_ticks": (0, 10000, True),
    "need_hunger": (0.0, 1.0, False), "memory_salience": (0.0, 1.0, False),
}
WORD_KEYS = ("managing", "stranger", "cannot")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLE = {"name": "bram", "text": "the ale", "word": "ale", "question": "how is it"}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _emitted_by_simple_meaning():
    """The kinds DeterministicSpeechBackend._meaning composes, read from its source."""
    from bigville.backends.speech import DeterministicSpeechBackend
    return set(re.findall(r'kind == "(\w+)"', inspect.getsource(DeterministicSpeechBackend._meaning)))


def _emitted_by_cheap():
    """The acts DeterministicBackend._speech sends, read from cheap.py's `act, slots = "..."` assignments."""
    with open(os.path.join(_ROOT, "bigville", "backends", "cheap.py"), encoding="utf-8") as fh:
        return set(re.findall(r'act, slots = "(\w+)"', fh.read()))


def _sample_render(template, row):
    """The template rendered with sample slot values, so its wording can be placed back."""
    values = {name: _SAMPLE.get(kind, "the ale") for name, kind in row.get("slots", {}).items()}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), "the ale"), template).rstrip(".?!")


def check_speech_acts(pack_path, errors, warnings, info, *, acts=None, templates=None):
    """Check SPEECH_ACTS and SPEECH_UNDERSTANDING of the pack at `pack_path`. `acts` and `templates` replace the
    pack's rows and DEFAULT_TEMPLATES, so a test can plant a template with no act and see the error."""
    from bigville.backends.conversation import DEFAULT_TEMPLATES
    templates = DEFAULT_TEMPLATES if templates is None else templates
    pack = load_pack(pack_path)
    where = "SPEECH_ACTS"
    if acts is None:
        if "SPEECH_ACTS" not in pack.names() or "SPEECH_UNDERSTANDING" not in pack.names():
            errors.append("SPEECH_ACTS: the pack has no speech_acts table (world/speech_acts.json)")
            return
        acts = pack["SPEECH_ACTS"]
    rows = list(acts)
    understanding = pack["SPEECH_UNDERSTANDING"]
    names = [row.get("act") for row in rows]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        errors.append(f"{where}: act {name!r} is listed more than once")

    for index, row in enumerate(rows):
        label = f"{where}[{row.get('act', index)}]"
        missing = [key for key in ROW_KEYS if key not in row]
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
            continue
        for slot, kind in row["slots"].items():
            if kind not in G.SLOT_KINDS:
                errors.append(f"{label}.slots[{slot}]: kind {kind!r} is not one of {', '.join(G.SLOT_KINDS)}")
        if not str(row["description"]).strip():
            errors.append(f"{label}.description: empty")
        if row["understood_by"] not in ("simple", "none"):
            errors.append(f"{label}.understood_by: must be simple or none, not {row['understood_by']!r}")
        if not row["emitted_by"] or any(e not in EMITTERS for e in row["emitted_by"]):
            errors.append(f"{label}.emitted_by: must name one or more of {', '.join(EMITTERS)}")
        if row["template"] is not None and row["template"] not in templates:
            errors.append(f"{label}.template: {row['template']!r} is not a template")
        for meaning in row["meaning"]:
            if meaning not in REALISED:
                errors.append(f"{label}.meaning: {meaning!r} is not a realised meaning")
        if row["template"] is None and not row["meaning"]:
            errors.append(f"{label}: has no template and no realised meaning, so nothing says this act")
        for table in row["lexicon"]:
            if table not in pack.names():
                errors.append(f"{label}.lexicon: {table!r} is not a pack table")
        if row["lexicon"] and row["lexicon_slot"] not in row["slots"]:
            errors.append(f"{label}.lexicon_slot: {row['lexicon_slot']!r} is not a slot of the act")
        if row["understood_by"] == "none" and (row["patterns"] or row["lexicon"]):
            errors.append(f"{label}: understood_by none, but it has patterns or a lexicon")
        if row["template"] is not None and row["template"] in templates:
            for placeholder in set(re.findall(r"\{(\w+)\}", templates[row["template"]])):
                if placeholder not in row["slots"]:
                    errors.append(f"{label}: template {row['template']!r} needs slot {{{placeholder}}}")

    claimed = {}
    for row in rows:
        if row.get("template") is not None:
            claimed.setdefault(row["template"], []).append(row.get("act"))
    for key in sorted(templates):
        owners = claimed.get(key, [])
        if not owners:
            errors.append(f"DEFAULT_TEMPLATES[{key}]: a template with no act (no SPEECH_ACTS row names it)")
        elif len(owners) > 1:
            errors.append(f"DEFAULT_TEMPLATES[{key}]: claimed by more than one act: {', '.join(map(str, owners))}")

    simple = _emitted_by_simple_meaning()
    meant = {row.get("act") for row in rows if "simple_meaning" in row.get("emitted_by", [])}
    for kind in sorted(simple - meant):
        errors.append(f"{where}: DeterministicSpeechBackend emits {kind!r}, which no row marks simple_meaning")
    for kind in sorted(meant - simple):
        errors.append(f"{where}: {kind!r} is marked simple_meaning, but DeterministicSpeechBackend does not emit it")
    cheap = _emitted_by_cheap()
    sent = {row.get("act") for row in rows if "simple_message" in row.get("emitted_by", [])}
    for kind in sorted(cheap - sent):
        errors.append(f"{where}: the simple backend sends {kind!r}, which no row marks simple_message")

    tables = {name: pack[name] for name in pack.names() if name in ("SPEECH_CHATTER", "SPEECH_WEATHER")}
    try:
        rules = G.rules_for(rows, templates, tables)
    except (ValueError, KeyError) as exc:
        errors.append(f"{where}: a pattern does not compile: {exc}")
        return
    for row in rows:
        if row.get("understood_by") != "simple" or not isinstance(row.get("slots"), dict):
            continue
        if not any(rule.act == row["act"] for rule in rules):
            errors.append(f"{where}[{row['act']}]: understood by the simple backend, but no pattern places it")
        template = templates.get(row.get("template")) if row.get("template") else None
        if template is None or G.template_pattern(template) is None:
            continue
        text = _sample_render(template, row)
        placed = G.place(text, rules)
        if placed is None or placed["act"] != row["act"]:
            got = None if placed is None else placed["act"]
            errors.append(f"{where}[{row['act']}]: its template {row['template']!r} rendered as {text!r} "
                          f"places as {got!r}")

    _check_understanding(understanding, rows, rules, errors, warnings, info)
    info.append(f"SPEECH_ACTS: {len(rows)} acts, {sum(1 for r in rows if r.get('understood_by') == 'simple')} "
                f"understood by the simple backend, {len(rules)} grammar patterns, {len(templates)} templates")


def _check_understanding(understanding, rows, rules, errors, warnings, info):
    where = "SPEECH_UNDERSTANDING"
    if not isinstance(understanding, dict) or not isinstance(understanding.get("enabled"), bool):
        errors.append(f"{where}.enabled: must be true or false")
        return
    effects = understanding.get("effects", {})
    for name, (low, high, is_int) in EFFECT_RANGES.items():
        value = effects.get(name)
        if not _is_number(value) or (is_int and not isinstance(value, int)):
            errors.append(f"{where}.effects.{name}: must be a {'whole' if is_int else 'finite'} number")
        elif not low <= value <= high:
            errors.append(f"{where}.effects.{name}: must lie in [{low}, {high}], not {value}")
    unknown = sorted(set(effects) - set(EFFECT_RANGES))
    if unknown:
        errors.append(f"{where}.effects: unknown keys {', '.join(unknown)}")
    words = understanding.get("words", {})
    for key in WORD_KEYS:
        if not str(words.get(key, "")).strip():
            errors.append(f"{where}.words.{key}: needs a sentence")
            continue
        placed = G.place(words[key], rules)
        if placed is None or placed["act"] != "answer":
            errors.append(f"{where}.words.{key}: {words[key]!r} is not placed as an answer by the grammar")
    if not errors and isinstance(effects, dict) and effects.get("grammar_confidence", 0) > effects.get(
            "raw_confidence", 1):
        warnings.append(f"{where}: grammar_confidence is above raw_confidence (a raw payload is the stronger evidence)")
    state = "on" if understanding["enabled"] else "off"
    info.append(f"SPEECH_UNDERSTANDING: the simple listener is {state} (the default is off)")
