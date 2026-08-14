"""Mechanical acronym → canonical phrase expansion for ambiguous lookups.

WordNet and some acquired Wikipedia extractions give the WRONG dominant sense
for short tech acronyms (e.g. LLM = Master of Laws, not large language model).
This table is host I/O data — the lookup sources consult it before answering;
no graph decision lives here.
"""
from __future__ import annotations

# lowercase acronym -> canonical Wikipedia / grounding phrase
_EXPANSIONS: dict[str, str] = {
    "llm": "large language model",
    "lrm": "large reasoning model",
    "rlm": "reasoning language model",
    "agi": "artificial general intelligence",
    "nlp": "natural language processing",
    "ml": "machine learning",
    "ai": "artificial intelligence",
}

# WordNet hits to SUPPRESS for acronyms we expand (dominant wrong sense).
_SUPPRESS_WORDNET: frozenset[str] = frozenset(_EXPANSIONS.keys())


def expand_acronym(phrase: str) -> str | None:
    """Return the canonical expansion for a bare acronym, or None."""
    key = str(phrase or "").strip().lower()
    if not key or " " in key:
        return None
    return _EXPANSIONS.get(key)


def suppress_wordnet(phrase: str) -> bool:
    """True when dictionary should miss so wiki/expansion can answer."""
    return str(phrase or "").strip().lower() in _SUPPRESS_WORDNET
