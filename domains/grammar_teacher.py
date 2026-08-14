"""Mini grammar lexicon — function words wordnet doesn't ship.

WordNet covers content words: nouns, verbs, adjectives, adverbs with
semantic content. It deliberately doesn't include pronouns,
auxiliaries, determiners, prepositions, conjunctions, or grammatical
markers. So the dictionary teacher misses on every "your", "is", "the".

This module provides a small in-memory lexicon of the common English
function words with their grammatical category + a brief role
description. Same callable shape as DictionaryTeacher and WikiTeacher
— it plugs into the same impasse-resolver chain via the ``fallback``
knob and the agent's existing ``learn_from_teacher`` payload format.

Order in the chain: grammar → dictionary → wiki. Grammar is the
fastest (in-memory dict lookup), only matches a small finite set of
function words, and falls through on every content word. Dictionary
catches everything wordnet ships. Wiki catches proper nouns and named
topics.

The lexicon is intentionally compact and editable. Extend it for
non-English use or domain-specific terms by adding to ``_LEXICON`` or
constructing a GrammarTeacher with a different ``lexicon`` dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .wiki_teacher import extract_subject


# Each entry: word → (category, definition).
# Definitions are deliberately brief — the agent will ground these as
# Concepts with the description attribute set, and the answer string
# becomes the memoised answer for any future "what is X?" ask.
_LEXICON: dict[str, tuple[str, str]] = {
    # --- pronouns + possessives + reflexives ---------------------
    "i":      ("pronoun", "first-person singular, the speaker"),
    "me":     ("pronoun", "first-person singular object form"),
    "my":     ("pronoun", "first-person singular possessive determiner"),
    "mine":   ("pronoun", "first-person singular possessive pronoun"),
    "myself": ("pronoun", "first-person singular reflexive"),
    "you":    ("pronoun", "second-person, the addressee"),
    "your":   ("pronoun", "second-person possessive determiner"),
    "yours":  ("pronoun", "second-person possessive pronoun"),
    "yourself":   ("pronoun", "second-person singular reflexive"),
    "yourselves": ("pronoun", "second-person plural reflexive"),
    "he":     ("pronoun", "third-person singular masculine"),
    "him":    ("pronoun", "third-person singular masculine object"),
    "his":    ("pronoun", "third-person singular masculine possessive"),
    "himself":("pronoun", "third-person singular masculine reflexive"),
    "she":    ("pronoun", "third-person singular feminine"),
    "her":    ("pronoun", "third-person singular feminine object/possessive"),
    "hers":   ("pronoun", "third-person singular feminine possessive"),
    "herself":("pronoun", "third-person singular feminine reflexive"),
    "it":     ("pronoun", "third-person singular neuter"),
    "its":    ("pronoun", "third-person singular neuter possessive"),
    "itself": ("pronoun", "third-person singular neuter reflexive"),
    "we":     ("pronoun", "first-person plural"),
    "us":     ("pronoun", "first-person plural object"),
    "our":    ("pronoun", "first-person plural possessive determiner"),
    "ours":   ("pronoun", "first-person plural possessive pronoun"),
    "ourselves": ("pronoun", "first-person plural reflexive"),
    "they":   ("pronoun", "third-person plural"),
    "them":   ("pronoun", "third-person plural object"),
    "their":  ("pronoun", "third-person plural possessive determiner"),
    "theirs": ("pronoun", "third-person plural possessive pronoun"),
    "themselves": ("pronoun", "third-person plural reflexive"),
    "this":   ("pronoun", "near demonstrative"),
    "that":   ("pronoun", "far demonstrative"),
    "these":  ("pronoun", "near plural demonstrative"),
    "those":  ("pronoun", "far plural demonstrative"),
    "who":    ("pronoun", "interrogative or relative pronoun for persons"),
    "whom":   ("pronoun", "object form of 'who'"),
    "whose":  ("pronoun", "possessive of 'who'"),
    "which":  ("pronoun", "interrogative or relative for things"),
    # --- auxiliary + copular verbs ------------------------------
    "am":     ("verb", "first-person singular present of 'to be'"),
    "is":     ("verb", "third-person singular present of 'to be'"),
    "are":    ("verb", "plural present of 'to be'"),
    "was":    ("verb", "first/third-person singular past of 'to be'"),
    "were":   ("verb", "plural past of 'to be'"),
    "be":     ("verb", "infinitive of 'to be'"),
    "been":   ("verb", "past participle of 'to be'"),
    "being":  ("verb", "present participle of 'to be'"),
    "have":   ("verb", "to possess; auxiliary for perfect tenses"),
    "has":    ("verb", "third-person singular present of 'have'"),
    "had":    ("verb", "past tense of 'have'"),
    "having": ("verb", "present participle of 'have'"),
    "do":     ("verb", "to perform; auxiliary for questions and emphasis"),
    "does":   ("verb", "third-person singular present of 'do'"),
    "did":    ("verb", "past tense of 'do'"),
    "doing":  ("verb", "present participle of 'do'"),
    "done":   ("verb", "past participle of 'do'"),
    "will":   ("verb", "modal indicating futurity or volition"),
    "would":  ("verb", "conditional modal; past form of 'will'"),
    "shall":  ("verb", "modal of obligation or future (archaic)"),
    "should": ("verb", "modal indicating obligation or expectation"),
    "may":    ("verb", "modal indicating permission or possibility"),
    "might":  ("verb", "modal indicating possibility"),
    "can":    ("verb", "modal indicating ability or permission"),
    "could":  ("verb", "modal indicating possibility; past of 'can'"),
    "must":   ("verb", "modal indicating necessity"),
    "ought":  ("verb", "modal indicating obligation"),
    # --- determiners + quantifiers ------------------------------
    "the":   ("determiner", "definite article"),
    "a":     ("determiner", "indefinite article"),
    "an":    ("determiner", "indefinite article before vowel sounds"),
    "some":  ("determiner", "indefinite quantifier; partial amount"),
    "any":   ("determiner", "polarity-sensitive quantifier"),
    "all":   ("determiner", "universal quantifier"),
    "no":    ("determiner", "negative quantifier"),
    "every": ("determiner", "universal distributive quantifier"),
    "each":  ("determiner", "distributive quantifier"),
    "both":  ("determiner", "quantifier for two entities"),
    "many":  ("determiner", "quantifier indicating a large count"),
    "few":   ("determiner", "quantifier indicating a small count"),
    "several":("determiner", "quantifier for a moderate count"),
    "much":  ("determiner", "quantifier for a large uncountable amount"),
    "more":  ("determiner", "comparative quantifier"),
    "most":  ("determiner", "superlative quantifier"),
    "less":  ("determiner", "comparative diminisher quantifier"),
    # --- prepositions -------------------------------------------
    "in":     ("preposition", "spatial: contained within"),
    "on":     ("preposition", "spatial: positioned upon a surface"),
    "at":     ("preposition", "spatial: at a specific point"),
    "by":     ("preposition", "agent, means, or location near"),
    "for":    ("preposition", "purpose, beneficiary, or duration"),
    "with":   ("preposition", "accompaniment or means"),
    "from":   ("preposition", "source or origin"),
    "of":     ("preposition", "possession, composition, or part-whole"),
    "to":     ("preposition", "destination, recipient, or infinitive marker"),
    "into":   ("preposition", "directed movement inward"),
    "onto":   ("preposition", "directed movement onto a surface"),
    "out":    ("preposition", "directed movement outward"),
    "about":  ("preposition", "concerning; approximately"),
    "as":     ("preposition", "in the role or capacity of"),
    "between":("preposition", "spatial: among exactly two things"),
    "among":  ("preposition", "spatial: surrounded by; in the midst of"),
    "during": ("preposition", "temporal: throughout"),
    "since":  ("preposition", "temporal: from a past time"),
    "until":  ("preposition", "temporal: up to a future time"),
    "through":("preposition", "passage from one side to the other"),
    "under":  ("preposition", "spatial: below"),
    "over":   ("preposition", "spatial: above; movement across"),
    "above":  ("preposition", "spatial: higher than"),
    "below":  ("preposition", "spatial: lower than"),
    "via":    ("preposition", "by way of"),
    # --- conjunctions -------------------------------------------
    "and":    ("conjunction", "additive coordinator"),
    "or":     ("conjunction", "alternative coordinator"),
    "but":    ("conjunction", "contrast coordinator"),
    "so":     ("conjunction", "consequence coordinator"),
    "if":     ("conjunction", "conditional subordinator"),
    "then":   ("conjunction", "consequent of a conditional"),
    "else":   ("conjunction", "alternative branch"),
    "because":("conjunction", "causal subordinator"),
    "when":   ("conjunction", "temporal subordinator"),
    "while":  ("conjunction", "simultaneous-temporal subordinator"),
    "though": ("conjunction", "concessive subordinator"),
    "although":("conjunction", "concessive subordinator"),
    "whether":("conjunction", "polar conditional subordinator"),
    "either": ("conjunction", "first-of-two coordinator"),
    "neither":("conjunction", "negative first-of-two coordinator"),
    "nor":    ("conjunction", "negative coordinator"),
    # --- negation / discourse / common adverbs -----------------
    "not":   ("adverb", "negation"),
    "yes":   ("interjection", "affirmation"),
    "okay":  ("interjection", "agreement or acknowledgment"),
    "very":  ("adverb", "intensifier"),
    "just":  ("adverb", "exactly, recently, or only"),
    "only":  ("adverb", "restrictive; nothing more than"),
    "also":  ("adverb", "additive"),
    "too":   ("adverb", "also; or to an excessive degree"),
    "even":  ("adverb", "scalar focus"),
    "still": ("adverb", "continuation"),
    "yet":   ("adverb", "up to now; nevertheless"),
    "ever":  ("adverb", "at any time"),
    "never": ("adverb", "at no time"),
    "now":   ("adverb", "at this time"),
    "here":  ("adverb", "at this place"),
    "there": ("adverb", "at that place"),
    "well":  ("adverb", "in a good manner; discourse opener"),
}


def lookup(word: str) -> tuple[str, str] | None:
    """Return (category, definition) or None for ``word`` (case-insensitive)."""
    return _LEXICON.get(word.lower())


def is_function_word(word: str) -> bool:
    """Cheap probe — useful as a check from callers that want to know
    whether the grammar teacher would handle a token."""
    return word.lower() in _LEXICON


def entry_to_answer(word: str, category: str, definition: str) -> str:
    """The plain-text answer for one entry — what the agent memoises
    and the user sees if they ask 'what is X?' on a function word."""
    return f"({category}) {definition}"


def entry_to_payload(word: str, category: str, definition: str,
                      microtheory: str = "grammar",
                      genl_mt: str = "general_knowledge") -> dict:
    """``learn_from_teacher``-shaped payload installing the word as a
    predicate Frame in the grammar Mt. The ``source`` field tags the
    grounded Concept with which ExternalStore answered — the
    pointer_from_grounded_concept Rule reads it to author the Wegner
    directory entry."""
    return {
        "answer": entry_to_answer(word, category, definition),
        "learn": [{
            "phrase": word.lower(),
            "microtheory": microtheory,
            "genl_mt": genl_mt,
            "description": f"grammar [{category}]",
            "binding_pattern": "predicate_of_subject",
            "slot_name": "of",
            "source": "grammar",
        }],
    }


@dataclass
class GrammarTeacher:
    """In-memory dictionary of English function words.

    Same callable shape as DictionaryTeacher / WikiTeacher. Cheapest
    link in the impasse-resolver chain (a single hash lookup). Plug it
    in front of the dictionary teacher:

        grammar = GrammarTeacher(fallback=DictionaryTeacher(
            fallback=WikiTeacher(library=lib)))
        agent.set_self_teacher(grammar)

    Knobs:
      - ``lexicon`` — override the default ``_LEXICON`` (alternative
        languages, domain-specific function-word sets).
      - ``microtheory`` / ``genl_mt`` — where grounded function words
        land in the agent's microtheory hierarchy.
      - ``fallback`` — next teacher in the chain on miss.
    """
    lexicon: dict = field(default_factory=lambda: _LEXICON)
    microtheory: str = "grammar"
    genl_mt: str = "general_knowledge"
    fallback: Callable[[str], Any] | None = None
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)
    last_subject: str | None = field(default=None, init=False)
    last_category: str | None = field(default=None, init=False)

    def lookup(self, word: str) -> tuple[str, str] | None:
        return self.lexicon.get(word.lower())

    def __call__(self, question_text: str) -> Any:
        subject = extract_subject(question_text)
        self.last_subject = subject
        entry = self.lookup(subject)
        if entry is None:
            self.misses += 1
            self.last_category = None
            if self.fallback is not None:
                return self.fallback(question_text)
            return None
        self.hits += 1
        category, definition = entry
        self.last_category = category
        return entry_to_payload(subject, category, definition,
                                 microtheory=self.microtheory,
                                 genl_mt=self.genl_mt)


__all__ = [
    "GrammarTeacher",
    "entry_to_answer",
    "entry_to_payload",
    "is_function_word",
    "lookup",
]
