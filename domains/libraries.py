"""Pluggable grounding libraries for the always-on daemon.

On-disk libraries (grammar, dictionary/WordNet, wiki, tropes) load by DEFAULT and form the
agent's self-teacher chain — cheapest-first, fallback-linked (grammar → dictionary → wiki →
tropes). Terra is an optional final structured teacher, never a conversational peer and never
a fallback callable: its evidence cannot become a HeldAnswer or an outbound Message directly.

Pluggable: a library is one `LibrarySpec` in `LIBRARIES` — `build()` returns the instance or
`None` if its data isn't on disk (best-effort; a missing library just drops out of the chain).
"Others come later" = append a spec.

Teachers aren't graph data (they're Python callables over on-disk corpora), so they're NOT in
the checkpoint — `attach_libraries` must run on every boot AND every resume.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

WIKI_DATA = Path(os.environ.get("WIKI_DATA_DIR", "/home/matt/ozma/data/wikipedia"))


@dataclass
class LibrarySpec:
    name: str
    build: Callable[[], Optional[object]]   # -> instance, or None if unavailable on disk
    default_on: bool = True
    kind: str = "teacher"                   # "teacher" chain | "structured_teacher" evidence transport


# --- on-disk teacher libraries (cheapest first) ----------------------------

def _grammar():
    from domains.grammar_teacher import GrammarTeacher
    return GrammarTeacher()                 # built-in; always available


def _dictionary():
    from domains.dict_teacher import DictionaryTeacher, is_available
    return DictionaryTeacher() if is_available() else None


def _wiki():
    if not WIKI_DATA.exists():
        return None
    from domains.wiki_library import WikipediaLibrary
    from domains.wiki_teacher import WikiTeacher
    lib = WikipediaLibrary(data_dir=WIKI_DATA)
    # Availability must stay constant-time: COUNT(*) over the 7M-row title
    # index can stall daemon boot for more than a minute.  The library itself
    # remains lazy and an incomplete/invalid index becomes an honest lookup
    # miss when the graph actually selects Wikipedia work.
    if not lib.index_path.is_file() or not lib.parquet_files():
        return None
    return WikiTeacher(library=lib, include_related=2)


def _tropes():
    from domains.tropes_teacher import TropesTeacher
    return TropesTeacher.from_cache()       # None if the cache isn't built


# --- gated structured teacher ---------------------------------------------

def _llm():
    from domains.no_llm import no_llm
    if no_llm():
        return None                         # OZMA_NO_LLM: the remote link is skipped
    from domains.openai_teacher import OpenAITeacher
    p = OpenAITeacher()
    return p if p.is_available() else None


LIBRARIES = [
    LibrarySpec("grammar",    _grammar,    True,  "teacher"),
    LibrarySpec("dictionary", _dictionary, True,  "teacher"),
    LibrarySpec("wiki",       _wiki,       True,  "teacher"),
    LibrarySpec("tropes",     _tropes,     True,  "teacher"),
    LibrarySpec("llm",        _llm,        False, "structured_teacher"),  # optional final tier
]


def attach_libraries(agent, enable_llm: bool = False, log=print) -> dict:
    """Attach local grounding first and Terra as a separate evidence transport.

    ``_self_teacher`` remains safe for local lookup payloads. The optional
    ``_teacher_transport`` is deliberately not linked into that chain: a
    graph-selected TeacherRequest must call its ``ask`` method later. ``partner``
    remains as a null compatibility field while the conversational route retires.
    """
    report = {"teachers": [], "teacher": None, "teacher_order": [],
              "partner": None, "skipped": []}
    teachers: list[tuple[str, object]] = []

    from domains.no_llm import no_llm

    for spec in LIBRARIES:
        wanted = spec.default_on or (spec.name == "llm" and enable_llm)
        if spec.kind == "structured_teacher" and no_llm():
            report["skipped"].append(f"{spec.name} (OZMA_NO_LLM)")
            continue
        if spec.kind == "structured_teacher" and not (spec.name == "llm" and enable_llm):
            report["skipped"].append("llm (toggle off)")
            continue
        if not wanted:
            continue
        try:
            inst = spec.build()
        except Exception as e:  # noqa: BLE001 — a library never blocks the boot
            report["skipped"].append(f"{spec.name} ({type(e).__name__})")
            log(f"library {spec.name!r} failed to load: {e}")
            continue
        if inst is None:
            report["skipped"].append(f"{spec.name} (no data on disk)")
            continue
        if spec.kind == "teacher":
            teachers.append((spec.name, inst))
        else:
            agent._teacher_transport = inst
            agent._llm_teacher = inst
            report["teacher"] = spec.name

    for i in range(len(teachers) - 1):       # cheapest-first fallback links
        teachers[i][1].fallback = teachers[i + 1][1]
    if teachers:
        agent.set_self_teacher(teachers[0][1])
        report["teachers"] = [n for n, _ in teachers]
        # Explicit named handles let the mechanical graph dispatcher select the
        # tier already chosen by the graph without walking a fallback chain.
        agent._teacher_libraries = {name: teacher for name, teacher in teachers}
        # ``wiki`` is the library implementation name; the instruction seed's
        # graph vocabulary uses the explicit teacher tier ``wikipedia``.
        # Keep both handles so selected work reaches the on-disk teacher rather
        # than appearing unavailable due to a host-side naming mismatch.
        if "wiki" in agent._teacher_libraries:
            agent._teacher_libraries["wikipedia"] = agent._teacher_libraries["wiki"]
    report["teacher_order"] = report["teachers"] + ([report["teacher"]] if report["teacher"] else [])
    return report
