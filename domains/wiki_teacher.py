"""Wikipedia as a low-cost lookup teacher.

Same callable shape as the LLM self-teacher the agent already supports
(``set_self_teacher``): ``(question_text) -> payload``. The agent's existing
impasse-resolver reflex spawns this, drains the result, and runs the payload
through ``learn_from_teacher`` — every path the LLM teacher uses already
works.

What's different is the cost. The LLM teacher means an API round-trip:
seconds and cents. The wiki teacher means a sqlite point-lookup plus one
parquet row read: tens of milliseconds, zero marginal cost. It's the
right thing to consult first; the LLM is the fallback when wiki has no
article (proper nouns, obscure jargon, novel concepts).

The teacher returns ``None`` when no article is found — the agent then
falls through to whatever other teacher the caller chains in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .wiki_library import Article, WikipediaLibrary


# Common interrogative prefixes — strip these to recover the subject.
# Ordered longest-first so "what is the" matches before "what is".
_PREFIX_PATTERNS = [
    r"^what\s+(?:is|are|was|were)\s+(?:the|a|an)\s+",
    r"^what\s+(?:is|are|was|were)\s+",
    r"^tell\s+me\s+about\s+(?:the\s+)?",
    r"^who\s+(?:is|was|are|were)\s+",
    r"^describe\s+(?:the\s+)?",
    r"^explain\s+(?:the\s+)?",
    r"^define\s+(?:the\s+)?",
    r"^how\s+does\s+(?:a\s+|an\s+|the\s+)?",
]
_PREFIX_RE = re.compile("|".join(_PREFIX_PATTERNS), re.IGNORECASE)

# Trailing question marks, periods, "in (whatever)" tails the question may
# carry. Conservative — don't strip too aggressively, the title may need them.
_TRAILING_RE = re.compile(r"[\?\.!,;:]+\s*$")


def extract_subject(question: str) -> str:
    """Best-effort: the candidate article title implied by a question.

    Strips interrogative prefixes + trailing punctuation. The result is a
    SUBJECT phrase, not a guaranteed title — the library lookup handles
    case + the fallback variants.
    """
    q = question.strip()
    q = _PREFIX_RE.sub("", q)
    q = _TRAILING_RE.sub("", q)
    return q.strip()


# ----------------------------------------------------------------------------
# subject → article (with light variants)
# ----------------------------------------------------------------------------

def _candidate_titles(subject: str) -> list[str]:
    """Variants worth trying, ordered most-likely first.

    The dataset's title_norm is case-insensitive, so casing variants don't
    matter — what does matter is multi-word / Title Case / hyphen handling
    + naive plural→singular.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        k = t.lower()
        if t and k not in seen:
            seen.add(k)
            out.append(t)

    add(subject)
    add(subject.replace("-", " "))
    add(subject.replace("_", " "))
    # Title-case (the dataset's canonical form: "Photosynthesis", "Big Break")
    add(" ".join(w.capitalize() for w in subject.split()))
    # Singular fallback for ASCII -s / -es plurals (rough, intentionally)
    if subject.lower().endswith("ies") and len(subject) > 3:
        add(subject[:-3] + "y")
    elif subject.lower().endswith("es") and len(subject) > 2:
        add(subject[:-2])
    elif subject.lower().endswith("s") and len(subject) > 1:
        add(subject[:-1])
    return out


# ----------------------------------------------------------------------------
# article → teach payload
# ----------------------------------------------------------------------------

def _abstract_snippet(article: Article, max_chars: int = 320) -> str:
    """First sentence-ish of the abstract — short answer the agent memoises."""
    text = (article.abstract or article.description or "").strip()
    if not text:
        return article.title
    if len(text) <= max_chars:
        return text
    # cut on sentence boundary near the limit
    cut = text.rfind(". ", 0, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return text[:cut].rstrip() + "…"


def article_to_payload(article: Article,
                       subject: str,
                       microtheory: str = "wikipedia",
                       genl_mt: str = "general_knowledge",
                       include_related: int = 0) -> dict:
    """Build a ``learn_from_teacher`` payload from a fetched article.

    The principal ``learn`` entry installs the looked-up subject as a
    predicate Frame held_in the named Mt; the realised concept's answer is
    the abstract snippet. Optional ``include_related`` installs that many
    cross-referenced article titles as sibling phrases in the same Mt
    (cheap reachability — the agent gains lookup-points for related topics
    without fetching the full articles).
    """
    answer = _abstract_snippet(article)
    phrase = subject.lower().strip()
    learn: list[dict] = [{
        "phrase": phrase,
        "microtheory": microtheory,
        "genl_mt": genl_mt,
        "description": f"wikipedia: {article.title}",
        "binding_pattern": "predicate_of_subject",
        "slot_name": "of",
        # Tag the source so learn_from_teacher writes it onto the
        # Concept attrs; pointer_from_grounded_concept Rule reads it to
        # author a Wegner-directory Pointer addressing the wiki store.
        "source": "wiki",
    }]
    if include_related > 0:
        for related in article.links[:include_related]:
            rp = related.lower().strip()
            if rp == phrase:
                continue
            learn.append({
                "phrase": rp,
                "microtheory": microtheory,
                "genl_mt": genl_mt,
                "description": f"wikipedia: related to {article.title}",
                "binding_pattern": "predicate_of_subject",
                "slot_name": "of",
                "source": "wiki",
            })
    return {"answer": answer, "learn": learn}


# ----------------------------------------------------------------------------
# the callable
# ----------------------------------------------------------------------------

@dataclass
class WikiTeacher:
    """Wikipedia-backed lookup teacher.

    Bind a ``WikipediaLibrary`` once at construction; the teacher is then a
    callable the agent invokes per impasse. Pass to
    ``agent.set_self_teacher(wiki_teacher)``.

    Knobs:
      - ``microtheory`` — which Mt newly-taught phrases land in (default
        ``wikipedia``, a sibling of ``general_knowledge``).
      - ``include_related`` — install N related article titles as sibling
        phrases per teach call (default 0; tune up for a more aggressive
        scope expansion).
      - ``fallback`` — optional second callable invoked when wiki has no
        article. Lets you chain wiki → LLM cleanly.
    """
    library: WikipediaLibrary
    microtheory: str = "wikipedia"
    genl_mt: str = "general_knowledge"
    include_related: int = 0
    fallback: Callable[[str], Any] | None = None
    # diagnostics
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)
    last_subject: str | None = field(default=None, init=False)
    last_title: str | None = field(default=None, init=False)

    def lookup(self, subject: str) -> Article | None:
        """Direct article lookup with title variants. No interrogative
        stripping — exposes the raw library to callers who already know
        the subject."""
        for cand in _candidate_titles(subject):
            art = self.library.article(cand)
            if art is not None:
                return art
        return None

    def __call__(self, question_text: str) -> Any:
        subject = extract_subject(question_text)
        self.last_subject = subject
        article = self.lookup(subject)
        if article is None:
            self.misses += 1
            self.last_title = None
            if self.fallback is not None:
                return self.fallback(question_text)
            return None
        self.hits += 1
        self.last_title = article.title
        return article_to_payload(
            article, subject=subject,
            microtheory=self.microtheory,
            genl_mt=self.genl_mt,
            include_related=self.include_related)


def wire_wikipedia_teacher(agent, data_dir=None) -> bool:
    """Wire the local Wikipedia as the agent's SELF-TEACHER: on a knowledge/render impasse it consults
    Wikipedia (sqlite + parquet lookup, zero marginal cost) and grounds the answer through the agent's own
    learn_from_teacher — the same path the LLM teacher uses. Enables the impasse-resolution loop and the
    order-4 self-extension climb, so the jabberwock can learn the concept it is missing (e.g. the parts of a
    visual cortex) and author the faculty it needs. Returns True if the snapshot was found and wired.

    Host wiring only — the runner hands the agent a knowledge source, the same as attaching a world. No
    decision over graph state lives here; the agent decides WHEN it is at an impasse and WHAT to ask."""
    from .wiki_library import WikipediaLibrary, DEFAULT_DATA_DIR
    lib = WikipediaLibrary(data_dir) if data_dir is not None else WikipediaLibrary()
    if not lib.parquet_files():
        return False                                  # no snapshot present — leave the agent teacher-less
    if hasattr(agent, "wire_teacher_resolution"):
        agent.wire_teacher_resolution()
    if hasattr(agent, "wire_escalation_faculties"):
        agent.wire_escalation_faculties()
    agent.set_self_teacher(WikiTeacher(lib))
    return True


__all__ = [
    "WikiTeacher",
    "extract_subject",
    "article_to_payload",
    "wire_wikipedia_teacher",
]
