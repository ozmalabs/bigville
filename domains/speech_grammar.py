"""speech_grammar.py -- a deterministic grammar that places free text as a speech act (Phase 060).

This is stage one of the speech parser (Phase 061 adds a model behind it). It is a pure module: it
reads no pack and no world. A caller passes the rows of the pack's SPEECH_ACTS table and the lexicon
phrases, and gets rules back. `place` returns the first rule whose pattern matches the whole text.

Normalisation. Text is lower-cased, punctuation is dropped (commas, full stops, question marks), and
runs of spaces are collapsed. Patterns are normalised the same way, so "Hello, {target}." and
"hello {target}" are one pattern.

Pattern syntax. Literal words match exactly. `{slot}` is a slot, and the act row's `slots` table gives
its kind:
    name       one or more words (a resident's name)
    text       one or more words (anything)
    word       one word
    question   words that open a question (how, what, is, can ...), then any words

A pattern needs a literal word, or a question slot. A pattern of slots alone would match every text, so
it is refused.

Rules come in row order. The pack orders the rows by priority: a rule earlier in the table wins when two
rules match the same text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SLOT_KINDS = ("name", "text", "word", "question")
QUESTION_OPENERS = ("how", "what", "where", "who", "whom", "whose", "when", "why", "which", "is", "are",
                    "was", "were", "do", "does", "did", "can", "could", "will", "would", "have", "has",
                    "any", "should", "shall")

_PUNCT = re.compile(r"[^\w\s'\-]+")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_WORD = r"[\w'\-]+"
_SLOT_RE = {
    "name": rf"{_WORD}(?:\s+{_WORD})*?",
    "text": rf"{_WORD}(?:\s+{_WORD})*",
    "word": _WORD,
    "question": rf"(?:{'|'.join(QUESTION_OPENERS)})(?:\s+{_WORD})*",
}


def normalise(text) -> str:
    """Lower case, punctuation dropped, spaces collapsed. The same for every caller."""
    return " ".join(_PUNCT.sub(" ", str(text).lower()).split())


@dataclass(frozen=True)
class Rule:
    act: str
    pattern: str
    regex: re.Pattern
    slot_names: tuple = field(default=())


def compile_pattern(act: str, pattern: str, slot_kinds: dict) -> Rule:
    """Compile one pattern of `act`. Raises ValueError for an unknown slot, an unknown kind, or a generic pattern."""
    pieces, names, literal_words, has_question = [], [], 0, False
    for index, part in enumerate(_PLACEHOLDER.split(pattern)):
        if index % 2:
            kind = slot_kinds.get(part)
            if kind not in SLOT_KINDS:
                raise ValueError(f"{act}: pattern {pattern!r} uses slot {{{part}}} with no valid kind")
            has_question = has_question or kind == "question"
            pieces.append(f"(?P<s{len(names)}>{_SLOT_RE[kind]})")
            names.append(part)
        else:
            for word in normalise(part).split():
                literal_words += 1
                pieces.append(re.escape(word))
    if not literal_words and not has_question:
        raise ValueError(f"{act}: pattern {pattern!r} has no literal word and would match any text")
    if not pieces:
        raise ValueError(f"{act}: empty pattern")
    return Rule(act, pattern, re.compile(r"\s+".join(pieces)), tuple(names))


def template_pattern(template: str):
    """A pattern from a surface template ("Could you {request}?" -> "Could you {request}"), or None.

    None when the template is only a slot ("{answer}"): such a template fits every text, so the act needs
    an explicit pattern or none at all."""
    text = str(template).strip().rstrip(".!?").strip()
    if not normalise(_PLACEHOLDER.sub(" ", text)):
        return None
    return text


def lexicon_patterns(tables: dict, names, slot: str) -> list:
    """Patterns from lexicon tables: every string value (not a key starting with `_`) is a phrase, and its
    placeholders become `slot`. A phrase keyed by trade or weather is therefore a pattern too."""
    found = []

    def walk(value):
        if isinstance(value, str):
            text = _PLACEHOLDER.sub("{" + slot + "}", value.strip().rstrip(".!?").strip())
            if normalise(_PLACEHOLDER.sub(" ", text)):
                found.append(text)
        elif isinstance(value, dict):
            for key, child in value.items():
                if not str(key).startswith("_"):
                    walk(child)

    for name in names:
        walk(tables[name])
    return found


def expanded_patterns(row: dict, templates: dict, tables: dict) -> list:
    """Every pattern of one SPEECH_ACTS row, in order: the pattern its surface template gives (if any), the
    row's explicit `patterns`, and the phrases of its `lexicon` tables. Duplicates are dropped."""
    found = []
    template_key = row.get("template")
    if template_key:
        if template_key not in templates:
            raise KeyError(f"{row['act']}: template {template_key!r} is not in the templates")
        derived = template_pattern(templates[template_key])
        if derived:
            found.append(derived)
    found.extend(row.get("patterns", []))
    if row.get("lexicon"):
        found.extend(lexicon_patterns(tables, row["lexicon"], row.get("lexicon_slot") or "text"))
    # More literal words first, so "goodbye for now" is tried before "goodbye {target}" (a name slot would
    # otherwise take "for now"). The sort is stable: equal patterns keep the order above.
    unique = list(dict.fromkeys(found))
    return sorted(unique, key=lambda p: -_literal_count(p))


def _literal_count(pattern: str) -> int:
    return len(normalise(_PLACEHOLDER.sub(" ", pattern)).split())


def rules_for(rows, templates: dict, tables: dict) -> list:
    """Compile the understood rows (understood_by not "none") of the SPEECH_ACTS table, in row order.

    `templates` is the surface template table (conversation.DEFAULT_TEMPLATES) and `tables` the pack's
    lexicon tables, keyed by name. A row's patterns come from `expanded_patterns`."""
    rules = []
    for row in rows:
        if row.get("understood_by") == "none":
            continue
        kinds = dict(row.get("slots", {}))
        for pattern in expanded_patterns(row, templates, tables):
            rules.append(compile_pattern(row["act"], pattern, kinds))
    return rules


def place(text, rules):
    """The first rule that matches the whole text: {act, slots, pattern}, or None."""
    norm = normalise(text)
    if not norm:
        return None
    for rule in rules:
        match = rule.regex.fullmatch(norm)
        if match is None:
            continue
        slots = {name: match.group(f"s{index}") for index, name in enumerate(rule.slot_names)}
        return {"act": rule.act, "slots": slots, "pattern": rule.pattern}
    return None
