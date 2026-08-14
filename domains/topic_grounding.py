"""topic_grounding — PHRASE-level topic grounding (host I/O only, CLAUDE.md).

`answer_about(concept)` answers "what do you know about X" only for topics the
agent already HOLDS. On a miss the existing self-heal grounds per-WORD via
`ground_unknowns(text)` (the dictionary/wiki teacher, one bare word at a time).
That fails for multi-word / named topics: "three body problem" grounds only the
word "problem" (a generic dictionary sense), and "arc agi v3 ls20" grounds
nothing. This module grounds the WHOLE PHRASE as one topic.

`ground_topic(agent, phrase)` is mechanical teacher/fetch plumbing — the SOURCE
decides the meaning, this module is only the loop:

  1. **local Wikipedia** — the on-disk library/teacher (`WikiTeacher.lookup`),
     a sqlite point-lookup + one parquet row read (tens of ms, zero marginal
     cost). Reuses an already-attached wiki self-teacher when present; else
     builds its own over `WIKI_DATA`.
  2. **live Wikipedia REST** (only if the local library misses and
     `allow_web`) — opensearch to canonicalise the phrase → a title, then the
     REST summary API's `extract`. HTTPS only; bounded timeout; any
     network/parse failure → None (never raises). Uses the SAME http machinery
     as `domains/fetch_dispatch.py` (its materialized agent-authored effector,
     falling back to the plain urllib GET with the same UA discipline) — no new
     user-agent invented.

Either way the result is PERSISTED through `agent.learn_from_teacher(phrase,
payload)`, which memoises the answer under the concept
`"taught_" + phrase.lower().replace("-","_").replace(" ","_")` and installs the
Frame/sign — EXACTLY what `agent.answer_about(phrase)` reads back. So after a
successful `ground_topic`, `agent.answer_about(phrase)` returns the answer,
offline, thereafter.

No decision over graph state lives here: WHETHER to ground a topic is the
agent's (a chat turn routes to it, or the `topic_search` seed rule mints a
`SearchRequest`); this module only performs the lookup/fetch and writes the
result back as graph data — the same admissible teacher-I/O loop as
`ground_unknowns`, at phrase grain instead of word grain.
"""
from __future__ import annotations

import json
from urllib.parse import quote

# --- web endpoints (HTTPS only — constructed here, never taken from input) ----
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
# Bounded read for the small JSON responses these endpoints return.
_MAX_BYTES = 200_000
# Keep a memoised answer to a few sentences (the summary API's `extract` is
# already 1-3 sentences; this only guards a pathological over-long one).
_MAX_ANSWER_CHARS = 800


# ----------------------------------------------------------------------------
# local Wikipedia library / teacher
# ----------------------------------------------------------------------------

def _wiki_teacher(agent):
    """The wiki teacher to consult. Prefers one already attached to the agent's
    self-teacher fallback chain (the daemon wires grammar→dictionary→wiki→
    tropes); else builds its own `WikiTeacher` over the on-disk `WIKI_DATA`
    snapshot. Returns None when no wiki snapshot is available on disk."""
    from domains.wiki_teacher import WikiTeacher
    t = getattr(agent, "_self_teacher", None)
    seen: set[int] = set()
    while t is not None and id(t) not in seen:
        seen.add(id(t))
        if isinstance(t, WikiTeacher):
            return t
        t = getattr(t, "fallback", None)
    # No attached wiki teacher — build one from disk.
    try:
        from domains.libraries import WIKI_DATA
        from domains.wiki_library import WikipediaLibrary
        lib = WikipediaLibrary(data_dir=WIKI_DATA)
        if lib.index_size() == 0:
            return None
        return WikiTeacher(library=lib, include_related=0)
    except Exception:  # noqa: BLE001 -- no snapshot / index locked -> no local teacher
        return None


def _ground_local(agent, phrase: str):
    """Ground `phrase` from the local Wikipedia library. Returns the memoised
    answer string, or None on a miss (no teacher / no article)."""
    from domains.wiki_teacher import article_to_payload
    teacher = _wiki_teacher(agent)
    if teacher is None:
        return None
    try:
        article = teacher.lookup(phrase)
    except Exception:  # noqa: BLE001 -- library read failure -> treat as a miss
        return None
    if article is None:
        return None
    payload = article_to_payload(
        article, subject=phrase,
        include_related=getattr(teacher, "include_related", 0))
    # A disambiguation page ("X may refer to:") is the source saying the
    # phrase is ambiguous, not a grounding -- treat it as a miss (the same
    # classification `ingest_search_candidates` measures), and never memoise
    # it as a taught answer.
    if _is_disambiguation_extract(str(payload.get("answer") or "")):
        return None
    try:
        return agent.learn_from_teacher(phrase, payload)
    except Exception:  # noqa: BLE001 -- ingestion failure -> honest miss
        return None


# ----------------------------------------------------------------------------
# live Wikipedia REST (web fallback)
# ----------------------------------------------------------------------------

def _http_get(url: str, timeout: int) -> dict:
    """The http GET this module uses (the single indirection tests monkeypatch).
    Reuses `fetch_dispatch`'s machinery: the materialized agent-authored
    effector first, falling back to its plain urllib GET (same UA/timeout
    discipline) — no new user-agent invented here."""
    from domains import fetch_dispatch as _fd
    fn = _fd._materialize_http_get()
    if fn is not None:
        try:
            return fn(url, timeout=timeout)
        except Exception:  # noqa: BLE001 -- effector call failed -> plain GET
            pass
    return _fd._plain_http_get(url, timeout=timeout, max_bytes=_MAX_BYTES)


def _opensearch_title(phrase: str, timeout: int, getter) -> str | None:
    """Canonicalise `phrase` to a Wikipedia article title via the opensearch
    API. Returns the first RELEVANT title after verification, or None."""
    titles = _opensearch_titles(phrase, timeout, getter, limit=5)
    for title in titles:
        if _title_relevant(phrase, title):
            return title
    return None


def _opensearch_titles(phrase: str, timeout: int, getter, *, limit: int = 5) -> list[str]:
    """Return up to `limit` opensearch titles (mechanical fetch, no selection)."""
    url = _WIKI_API + "?action=opensearch&limit=" + str(int(limit)) \
        + "&namespace=0&format=json&search=" + quote(phrase)
    if not url.lower().startswith("https://"):
        return []
    res = getter(url, timeout=timeout)
    data = json.loads(res.get("text") or "")
    if isinstance(data, list) and len(data) >= 2 and data[1]:
        return [str(t).strip() for t in data[1] if str(t).strip()]
    return []


def _tokens(text: str) -> list[str]:
    import re
    return [w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 1]


def _title_relevant(phrase: str, title: str) -> bool:
    """Mechanical overlap measure — every significant query token must appear in
    the title as a whole token (plural-insensitive), and military-unit false
    positives are rejected when the query names no military term."""
    import re
    q = _tokens(phrase)
    if not q:
        return False
    t_tokens = set(_tokens(title))
    t_text = " " + str(title).lower().replace("-", " ") + " "
    for qt in q:
        stem = qt[:-1] if len(qt) > 3 and qt.endswith("s") else qt
        if qt in t_tokens or stem in t_tokens:
            continue
        if f" {qt} " in t_text or f" {stem} " in t_text:
            continue
        # Token-boundary only — reject bare substrings (e.g. llm inside llm01).
        if re.search(rf"(?<![a-z0-9]){re.escape(qt)}(?![a-z0-9])", t_text):
            continue
        return False
    military = frozenset({"squadron", "wing", "battalion", "regiment", "corps", "force", "army"})
    q_set = set(q)
    t_set = set(_tokens(title))
    if not (q_set & military) and (t_set & military):
        return False
    return True


def _overlap_ratio(phrase: str, title: str) -> float:
    """Mechanical overlap ratio in [0,1] for graph verification rules."""
    q = [t for t in _tokens(phrase) if len(t) > 1]
    if not q:
        return 0.0
    hits = sum(1 for qt in q if _title_relevant(qt, title) or qt in title.lower())
    return hits / len(q)


def _is_disambiguation_extract(extract: str, summary: dict | None = None) -> bool:
    if summary and str(summary.get("type") or "").lower() == "disambiguation":
        return True
    low = str(extract or "").lower().strip()
    return low.endswith("may refer to:") or low == "may refer to:"


def _summary_data(title: str, timeout: int, getter) -> dict | None:
    url = _WIKI_SUMMARY + quote(title.replace(" ", "_"), safe="")
    if not url.lower().startswith("https://"):
        return None
    res = getter(url, timeout=timeout)
    data = json.loads(res.get("text") or "")
    return data if isinstance(data, dict) else None


def ingest_search_candidates(agent, req, query: str, *, timeout: int = 8,
                             http_get=None, min_overlap: float = 0.8) -> int:
    """Mechanical ingest: mint SearchCandidate nodes for each opensearch hit with
    measured overlap_ratio and is_disambiguation — no selection. Returns count."""
    getter = http_get or _http_get
    sub, native = agent.s, agent.inner
    titles = _opensearch_titles(query, timeout, getter, limit=5)
    count = 0
    native.set_attr(req, "min_overlap", float(min_overlap))
    for title in titles:
        summary = _summary_data(title, timeout, getter)
        extract = (summary or {}).get("extract")
        if not extract or not str(extract).strip():
            continue
        ratio = _overlap_ratio(query, title)
        disamb = 1.0 if _is_disambiguation_extract(str(extract), summary) else 0.0
        cn = sub.add_node("SearchCandidate", {
            "title": str(title),
            "extract": _cap_answer(str(extract).strip()),
            "overlap_ratio": float(ratio),
            "is_disambiguation": disamb,
        })
        native.add_edge_unchecked(req, "has_candidate", cn)
        count += 1
    return count


def commit_selected_search(agent, req, query: str) -> str | None:
    """Mechanical read-back: persist the graph-selected candidate only."""
    sub, native = agent.s, agent.inner
    chosen = sub.node(req)["attrs"].get("chosen_extract")
    if chosen:
        answer = _cap_answer(str(chosen))
        try:
            agent.learn_from_teacher(
                query, {"answer": answer,
                         "learn": [{"phrase": query, "answer": answer}]})
        except Exception:  # noqa: BLE001
            return None
        return answer
    for c in native.neighbours(req, "has_candidate"):
        if not sub.has_node(c):
            continue
        ca = sub.node(c)["attrs"]
        if ca.get("selected") == 1.0 and ca.get("extract"):
            answer = _cap_answer(str(ca["extract"]))
            try:
                agent.learn_from_teacher(
                    query, {"answer": answer,
                             "learn": [{"phrase": query, "answer": answer}]})
            except Exception:  # noqa: BLE001
                return None
            return answer
    return None


def _summary_extract(title: str, timeout: int, getter) -> str | None:
    """Fetch the plain-text `extract` for `title` from the REST summary API.
    Returns the extract, or None."""
    data = _summary_data(title, timeout, getter)
    if data:
        extract = data.get("extract")
        if extract and str(extract).strip():
            return str(extract).strip()
    return None


def _cap_answer(text: str) -> str:
    """Cap a memoised answer to a few sentences (see `_MAX_ANSWER_CHARS`)."""
    text = text.strip()
    if len(text) <= _MAX_ANSWER_CHARS:
        return text
    cut = text.rfind(". ", 0, _MAX_ANSWER_CHARS)
    if cut < _MAX_ANSWER_CHARS // 2:
        cut = _MAX_ANSWER_CHARS
    return text[:cut].rstrip() + "…"


def _ground_web(agent, phrase: str, *, timeout: int, http_get=None) -> str | None:
    """Ground `phrase` from the live Wikipedia REST API (opensearch → summary).
    Persists the extract via `learn_from_teacher` and returns it, or None on any
    miss/failure. Never raises."""
    getter = http_get or _http_get
    try:
        title = _opensearch_title(phrase, timeout, getter)
        if not title:
            return None
        extract = _summary_extract(title, timeout, getter)
        if not extract:
            return None
    except Exception:  # noqa: BLE001 -- network / parse failure -> honest miss
        return None
    # A disambiguation page is the source saying the phrase is ambiguous, not
    # a grounding -- honest miss, never memoised (same rule as _ground_local).
    if _is_disambiguation_extract(extract):
        return None
    answer = _cap_answer(extract)
    try:
        agent.learn_from_teacher(
            phrase, {"answer": answer,
                     "learn": [{"phrase": phrase, "answer": answer}]})
    except Exception:  # noqa: BLE001 -- ingestion failure -> honest miss
        return None
    return answer


# ----------------------------------------------------------------------------
# public entry points
# ----------------------------------------------------------------------------

def _clear_stale_acronym_answer(agent, phrase: str, expanded: str) -> None:
    """Drop a poisoned HeldAnswer when an acronym's stored text matches none of
    the canonical expansion's content words (e.g. llm -> LLM01 military hardware)."""
    phrase = str(phrase or "").strip()
    expanded = str(expanded or "").strip().lower()
    if not phrase or not expanded:
        return
    markers = [w for w in expanded.split() if len(w) > 3]
    if not markers:
        return
    try:
        S, I = agent.s, agent.inner
        for n in list(S.nodes("HeldAnswer")):
            a = S.node(n)["attrs"]
            if (a.get("topic") or "").strip().lower() != phrase.lower():
                continue
            text = str(a.get("text") or "").lower()
            if any(m in text for m in markers):
                continue
            I.remove_node(n)
        concept = "taught_" + phrase.lower().replace("-", "_").replace(" ", "_")
        if concept in getattr(agent, "_taught_lookup", {}):
            agent._taught_lookup.pop(concept, None)
    except Exception:  # noqa: BLE001
        pass


def resolve_and_ground(agent, phrase: str, *, allow_web: bool = True,
                       timeout: int = 8, http_get=None) -> str | None:
    """`ground_topic` with an injectable `http_get` (used by
    `fetch_dispatch.scan_and_search`, which passes its own/tested getter through
    to the web path). Local library first, then the web fallback."""
    if not phrase or not str(phrase).strip():
        return None
    phrase = str(phrase).strip()
    from domains.acronym_expand import expand_acronym
    expanded = expand_acronym(phrase)
    if expanded:
        _clear_stale_acronym_answer(agent, phrase, expanded)
        ans = _ground_local(agent, expanded)
        if ans is not None:
            try:
                agent.learn_from_teacher(
                    phrase, {"answer": ans,
                             "learn": [{"phrase": phrase, "answer": ans}]})
            except Exception:  # noqa: BLE001
                pass
            return ans
        if allow_web:
            ans = _ground_web(agent, expanded, timeout=timeout, http_get=http_get)
            if ans is not None:
                try:
                    agent.learn_from_teacher(
                        phrase, {"answer": ans,
                                 "learn": [{"phrase": phrase, "answer": ans}]})
                except Exception:  # noqa: BLE001
                    pass
                return ans
    ans = _ground_local(agent, phrase)
    if ans is not None:
        return ans
    if allow_web:
        return _ground_web(agent, phrase, timeout=timeout, http_get=http_get)
    return None


def ground_topic(agent, phrase: str, *, allow_web: bool = True,
                 timeout: int = 8) -> str | None:
    """Ground a (possibly multi-word) topic phrase so `agent.answer_about(phrase)`
    returns an answer thereafter. Tries: (1) the local Wikipedia library/teacher;
    (2) if `allow_web` and local misses, a live Wikipedia REST lookup over HTTPS.
    Persists the grounding as a taught concept (via `agent.learn_from_teacher`,
    which memoises under `taught_<normalised phrase>` — exactly what
    `answer_about` reads). Returns the answer string (a 1-3 sentence summary), or
    None if ungroundable. Mechanical I/O only — the source decides the meaning."""
    return resolve_and_ground(agent, phrase, allow_web=allow_web,
                              timeout=timeout, http_get=None)


# ----------------------------------------------------------------------------
# progressive detail (ordered paragraph chunks) -- fuel for the elaboration
# ('tell me more') seed rules. Fetch-only, like `ground_topic`: the source
# decides the content; this is a mechanical read that returns an ORDERED list of
# ~paragraph chunk strings. The elaboration DECISION (whether/what to serve) is
# a graph rule (seeds/conversation_elaborate.json); this only supplies the raw
# chunks the fetch dispatch (domains.fetch_dispatch.scan_and_ingest_detail)
# ingests into the detail chain. No decision over graph state lives here.
# ----------------------------------------------------------------------------

# How many detail chunks to hand back at most (bounds ingestion cost, like the
# fetch dispatch's byte cap) and the smallest chunk worth keeping.
_MAX_DETAIL_CHUNKS = 12
_MIN_CHUNK_CHARS = 40
# extracts API: full plain-text article (paragraphs separated by blank lines).
_WIKI_EXTRACTS = _WIKI_API + \
    "?action=query&prop=extracts&explaintext=1&redirects=1&format=json&titles="


def _chunk_paragraphs(text: str) -> list:
    """Split a block of plain text into paragraph-ish chunks (blank-line
    separated, then newline), dropping tiny fragments. Mechanical text split."""
    out: list = []
    for block in str(text or "").replace("\r", "").split("\n\n"):
        for para in block.split("\n"):
            p = para.strip()
            if len(p) >= _MIN_CHUNK_CHARS:
                out.append(p)
    return out


def _detail_local(agent, phrase: str) -> list:
    """Ordered detail chunks for `phrase` from the local Wikipedia library:
    the abstract, then each section's free text, split into paragraphs.
    Returns [] on a miss (no teacher / no article). Pure read, no decisions."""
    teacher = _wiki_teacher(agent)
    if teacher is None:
        return []
    try:
        article = teacher.lookup(phrase)
    except Exception:  # noqa: BLE001 -- library read failure -> treat as a miss
        return []
    if article is None:
        return []
    chunks: list = []
    chunks.extend(_chunk_paragraphs(getattr(article, "abstract", "") or ""))
    try:
        for idx in range(len(getattr(article, "sections", []) or [])):
            chunks.extend(_chunk_paragraphs(article.section_text(idx)))
    except Exception:  # noqa: BLE001 -- malformed section tree -> keep what we have
        pass
    return chunks


def _detail_web(agent, phrase: str, *, timeout: int, http_get=None) -> list:
    """Ordered detail chunks for `phrase` from the live Wikipedia extracts API
    (opensearch -> title -> full plain-text extract, paragraph-split). HTTPS
    only; any network/parse failure -> []. Never raises."""
    getter = http_get or _http_get
    try:
        title = _opensearch_title(phrase, timeout, getter)
        if not title:
            return []
        url = _WIKI_EXTRACTS + quote(title.replace(" ", "_"), safe="")
        if not url.lower().startswith("https://"):   # security boundary: HTTPS only
            return []
        res = getter(url, timeout=timeout)
        data = json.loads(res.get("text") or "")
        pages = ((data or {}).get("query") or {}).get("pages") or {}
        for page in pages.values():
            extract = (page or {}).get("extract")
            if extract and str(extract).strip():
                return _chunk_paragraphs(extract)
    except Exception:  # noqa: BLE001 -- network / parse failure -> honest empty
        return []
    return []


def topic_detail(agent, phrase: str, *, allow_web: bool = True,
                 timeout: int = 8, http_get=None) -> list:
    """An ORDERED list of ~paragraph detail chunk strings for a (possibly
    multi-word) topic `phrase`, for progressive disclosure. Tries: (1) the local
    Wikipedia library/teacher (abstract + section free-text); (2) if `allow_web`
    and local misses, the live Wikipedia extracts API over HTTPS. Bounded to
    `_MAX_DETAIL_CHUNKS`. Returns [] if nothing is available. Mechanical I/O only
    -- the source decides the content; the elaboration seed rules decide what to
    do with the chunks."""
    if not phrase or not str(phrase).strip():
        return []
    phrase = str(phrase).strip()
    chunks = _detail_local(agent, phrase)
    if not chunks and allow_web:
        chunks = _detail_web(agent, phrase, timeout=timeout, http_get=http_get)
    return chunks[:_MAX_DETAIL_CHUNKS]


_COMPOSITION_REPLY_HINTS = frozenset({
    "composition", "composed", "consists of", "made of", "made up",
    "regolith", "basalt", "silicate", "lunar crust", "crust is",
    "mantle", "mineral", "oxygen", "silicon", "iron", "nickel",
})


def _looks_compositional(text: str) -> bool:
    low = str(text or "").lower()
    # Tight hints — avoid substring false positives ('consist' in 'consistency', etc.)
    strong = (
        "composition", "composed of", "made of", "made up of", "consists of",
        "mainly consists", "regolith", "basalt", "silicate", "lunar crust",
        "mantle", "mineral", "oxygen", "silicon", "iron-rich", "nickel",
    )
    if any(h in low for h in strong):
        return True
    weak = ("crust", "metal", "rock", "material")
    return sum(1 for h in weak if h in low) >= 2


def _extract_composition_sentences(text: str) -> str | None:
    """Pull composition-bearing sentences from a long wiki chunk."""
    import re
    sentences = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    hits = [s.strip() for s in sentences if s.strip() and _looks_compositional(s)]
    if not hits:
        return None
    return _cap_answer(" ".join(hits[:3]))


def _pick_composition_chunk(chunks: list) -> str | None:
    """Mechanical read: first detail chunk with composition-bearing sentences."""
    for ch in chunks:
        extracted = _extract_composition_sentences(str(ch))
        if extracted:
            return extracted
    return None


def ground_topic_aspect(agent, concept: str, aspect: str, *, allow_web: bool = True,
                        timeout: int = 8) -> str | None:
    """Ground a topic for a specific question aspect so `answer_about` can read it
    back. Mechanical I/O only — tries aspect-shaped queries against held sources."""
    concept = str(concept or "").strip()
    aspect = str(aspect or "").strip()
    if not concept:
        return None
    if aspect == "made_of":
        store = f"composition of {concept}"
        chunks = topic_detail(agent, concept, allow_web=allow_web, timeout=timeout)
        answer = _pick_composition_chunk(chunks)
        if answer is None and allow_web:
            answer = resolve_and_ground(agent, store, allow_web=False,
                                        timeout=timeout, http_get=None)
        if answer is None and allow_web:
            answer = resolve_and_ground(agent, store, allow_web=True,
                                        timeout=timeout, http_get=None)
        if answer is None or not _looks_compositional(answer):
            return None
        try:
            agent.learn_from_teacher(
                store, {"answer": answer,
                        "learn": [{"phrase": store, "answer": answer}]})
        except Exception:  # noqa: BLE001
            return None
        return answer
    return ground_topic(agent, concept, allow_web=allow_web, timeout=timeout)


__all__ = ["ground_topic", "resolve_and_ground", "topic_detail", "ground_topic_aspect",
           "ingest_search_candidates", "commit_selected_search"]
