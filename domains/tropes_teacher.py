"""TV Tropes as a lookup teacher — narrative conventions on demand.

Same callable shape as ``WikiTeacher`` / the LLM self-teacher:
``(question_text) -> payload | None``. Slots into the agent's teacher
chain (grammar -> dictionary -> wiki -> **tropes** -> LLM). When the
agent hits a convention it cannot ground (an impasse), it asks this
teacher, gets ``{definition, examples}`` from the TV Tropes corpus, and
grounds it through the SAME machinery it uses for a dictionary word.

Tropes are not media trivia — they are the comprehension scripts/frames
that make narrative and speech predictable enough to understand. New
phrases land in the ``tropes`` Mt, genl ``narrative_convention`` (the
scaffold installed by domains/comprehension.py).

The corpus is a 1.9 GB CSV bundle, so we DON'T parse it per lookup.
``build_tropes_index`` streams it ONCE into a compact JSON cache
(name -> definition + a few example snippets + example count); the
teacher loads the cache (fast) and answers from memory. Ingestion is
therefore impasse/curiosity-driven by construction — the agent pulls the
conventions it actually meets, not a linear march through the corpus.

One-time build:  ``python -m domains.tropes_teacher --build``
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .wiki_teacher import extract_subject  # share interrogative-stripping


# ---------------------------------------------------------------------------
# locations
# ---------------------------------------------------------------------------

def _default_zip() -> Path:
    return Path(os.environ.get(
        "TVTROPES_ZIP", str(Path.home() / "Downloads" / "TVTropesData.zip")))


def _default_cache() -> Path:
    return Path(os.environ.get(
        "TVTROPES_INDEX",
        str(Path.home() / ".cache" / "ozma" / "tvtropes_index.json")))


# Members inside the zip, and the medium each tropes-file represents.
_DEFS_MEMBER = "TVTropesData/tropes.csv"
_EXAMPLE_MEMBERS = {
    "TVTropesData/film_tropes.csv": "film",
    "TVTropesData/tv_tropes.csv": "tv",
    "TVTropesData/lit_tropes.csv": "lit",
}

_DEF_CAP = 700        # chars kept of a trope Description
_SNIPPET_CAP = 240    # chars kept of one Example
_MAX_EXAMPLES = 3     # example snippets cached per trope


# ---------------------------------------------------------------------------
# name normalisation
# ---------------------------------------------------------------------------

# A leading article only matters as a lookup-recall fallback (see
# TropesTeacher.lookup) — we never strip it from the primary key, so a
# work/trope whose name genuinely starts with 'A'/'An'/'The' is unharmed.
_ARTICLE_RE = re.compile(r"^(?:a|an|the)\s+", re.IGNORECASE)


def normalize(name: str) -> str:
    """Collapse a trope name / question subject to a match key:
    lowercase, alphanumerics only. 'Chekhov's Gun' and 'ChekhovsGun'
    both -> 'chekhovsgun'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def de_camel(name: str) -> str:
    """'ChekhovsGun' -> 'chekhovs gun' — a readable phrase to ground."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", spaced)
    return spaced.replace("_", " ").strip().lower()


def _snippet(text: str, cap: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= cap:
        return t
    cut = t.rfind(". ", 0, cap)
    if cut < cap // 2:
        cut = cap
    return t[:cut].rstrip() + "…"


# ---------------------------------------------------------------------------
# one-time index build (stream the zip -> compact cache)
# ---------------------------------------------------------------------------

def _raise_field_limit() -> None:
    lim = sys.maxsize
    while True:
        try:
            csv.field_size_limit(lim)
            return
        except OverflowError:
            lim = int(lim // 10)


def _open_member(zf: zipfile.ZipFile, member: str):
    raw = zf.open(member, "r")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")


def build_tropes_index(zip_path: Path | str | None = None,
                       cache_path: Path | str | None = None,
                       *, max_examples: int = _MAX_EXAMPLES,
                       progress: Callable[[str], None] | None = None) -> dict:
    """Stream the corpus ONCE into a compact dict and write it to
    ``cache_path``. Returns the index. ~1-3 min, one-time."""
    zip_path = Path(zip_path) if zip_path else _default_zip()
    cache_path = Path(cache_path) if cache_path else _default_cache()
    if not zip_path.exists():
        raise FileNotFoundError(f"TV Tropes zip not found: {zip_path}")
    _raise_field_limit()

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    index: dict[str, dict] = {}

    with zipfile.ZipFile(zip_path) as zf:
        # 1) definitions (tropes.csv)
        say(f"reading {_DEFS_MEMBER} …")
        with _open_member(zf, _DEFS_MEMBER) as fh:
            for row in csv.DictReader(fh):
                name = (row.get("Trope") or "").strip()
                if not name:
                    continue
                key = normalize(name)
                if not key:
                    continue
                index.setdefault(key, {
                    "name": name,
                    "phrase": de_camel(name),
                    "definition": _snippet(row.get("Description") or "", _DEF_CAP),
                    "n_examples": 0,
                    "examples": [],
                })

        # 2) examples (stream; count + keep a few snippets per trope)
        for member, medium in _EXAMPLE_MEMBERS.items():
            say(f"streaming {member} ({medium}) …")
            try:
                fh = _open_member(zf, member)
            except KeyError:
                continue
            with fh:
                for row in csv.DictReader(fh):
                    name = (row.get("Trope") or "").strip()
                    if not name:
                        continue
                    key = normalize(name)
                    rec = index.get(key)
                    if rec is None:
                        # trope appears in examples but not in tropes.csv —
                        # mint a definition-less stub so it is still groundable
                        rec = {"name": name, "phrase": de_camel(name),
                               "definition": "", "n_examples": 0, "examples": []}
                        index[key] = rec
                    rec["n_examples"] += 1
                    if len(rec["examples"]) < max_examples:
                        ex = _snippet(row.get("Example") or "", _SNIPPET_CAP)
                        if ex:
                            rec["examples"].append({
                                "work": (row.get("Title") or "").strip(),
                                "medium": medium,
                                "text": ex,
                            })

    say(f"writing cache -> {cache_path}  ({len(index)} tropes)")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(index))
    return index


def load_tropes_index(cache_path: Path | str | None = None) -> dict | None:
    """Load a previously built index, or None if absent."""
    cache_path = Path(cache_path) if cache_path else _default_cache()
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------------

def record_to_payload(rec: dict,
                      microtheory: str = "tropes",
                      genl_mt: str = "narrative_convention") -> dict:
    """Build a ``learn_from_teacher`` payload for one trope record. The
    learn entry installs the trope's readable phrase as a predicate Frame
    held_in the ``tropes`` Mt (genl narrative_convention); the answer is
    the definition, optionally tailed with a concrete example so the
    grounding has an instance to bind to."""
    phrase = rec.get("phrase") or de_camel(rec.get("name", ""))
    answer = rec.get("definition") or f"a narrative convention: {rec.get('name', phrase)}"
    exs = rec.get("examples") or []
    if exs:
        e = exs[0]
        answer = f"{answer}  e.g. in {e.get('work', '?')} ({e.get('medium', '?')}): {e.get('text', '')}"
    return {
        "answer": _snippet(answer, _DEF_CAP + _SNIPPET_CAP + 80),
        "learn": [{
            "phrase": phrase,
            "microtheory": microtheory,
            "genl_mt": genl_mt,
            "description": f"TV Tropes: {rec.get('name', phrase)}",
            "binding_pattern": "predicate_of_subject",
            "slot_name": "of",
            "source": "tvtropes",
        }],
    }


# ---------------------------------------------------------------------------
# the callable
# ---------------------------------------------------------------------------

@dataclass
class TropesTeacher:
    """TV-Tropes-backed lookup teacher. Pass to
    ``agent.set_self_teacher(...)`` or chain via ``fallback``."""
    index: dict
    microtheory: str = "tropes"
    genl_mt: str = "narrative_convention"
    fallback: Callable[[str], Any] | None = None
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)
    last_subject: str | None = field(default=None, init=False)
    last_name: str | None = field(default=None, init=False)

    @classmethod
    def from_cache(cls, cache_path: Path | str | None = None,
                   fallback: Callable[[str], Any] | None = None,
                   **kw) -> "TropesTeacher | None":
        idx = load_tropes_index(cache_path)
        if not idx:
            return None
        return cls(index=idx, fallback=fallback, **kw)

    def lookup(self, subject: str) -> dict | None:
        rec = self.index.get(normalize(subject))
        if rec is None:
            # recall fallback: 'a Red Shirt' / 'the Big Bad' -> drop the
            # leading article and retry (primary key is never altered).
            stripped = _ARTICLE_RE.sub("", subject).strip()
            if stripped and stripped != subject:
                rec = self.index.get(normalize(stripped))
        return rec

    def __call__(self, question_text: str) -> Any:
        subject = extract_subject(question_text)
        self.last_subject = subject
        rec = self.lookup(subject)
        if rec is None:
            self.misses += 1
            self.last_name = None
            if self.fallback is not None:
                return self.fallback(question_text)
            return None
        self.hits += 1
        self.last_name = rec.get("name")
        return record_to_payload(rec, self.microtheory, self.genl_mt)


# ---------------------------------------------------------------------------
# proactive primer (opt-in) — prime the most-exemplified conventions
# ---------------------------------------------------------------------------

def prime_top_tropes(agent, teacher: TropesTeacher, n: int = 500,
                     progress: Callable[[str], None] | None = None) -> int:
    """Ground the top-N most-exemplified tropes up front (the common
    scripts), without waiting for an impasse. Returns how many were fed.
    example-count is the salience signal."""
    ranked = sorted(teacher.index.values(),
                    key=lambda r: r.get("n_examples", 0), reverse=True)[:n]
    fed = 0
    for rec in ranked:
        payload = record_to_payload(rec, teacher.microtheory, teacher.genl_mt)
        try:
            agent.learn_from_teacher(rec.get("phrase", ""), payload)
            fed += 1
        except Exception:
            pass
        if progress and fed % 50 == 0:
            progress(f"primed {fed}/{len(ranked)} tropes")
    return fed


__all__ = [
    "TropesTeacher", "build_tropes_index", "load_tropes_index",
    "record_to_payload", "prime_top_tropes", "normalize", "de_camel",
]


if __name__ == "__main__":  # one-time index build
    build = "--build" in sys.argv
    if not build:
        print(__doc__)
        print("\nRun with --build to construct the index cache.")
        sys.exit(0)
    idx = build_tropes_index(progress=lambda m: print(f"[tropes] {m}"))
    counts = sorted((r["n_examples"] for r in idx.values()), reverse=True)
    print(f"[tropes] {len(idx)} tropes indexed; "
          f"top example-counts: {counts[:10]}")
