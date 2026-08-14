"""fetch_dispatch — the web-FETCH dispatch MECHANISM (host I/O only, CLAUDE.md).

The DECISION to fetch a URL is the agent's: it mints a `FetchRequest` node
(`status="requested"`) via its own rules when it wants a resource from the
web. This module does not decide THAT, does not decide WHICH url, and does
not interpret the fetched content — it only:

  1. **sees** a requested `FetchRequest` node,
  2. **fetches** the URL over HTTP(S) GET — the agent-authored `http_get`
     effector (`domains.runtime_design.agent_specify_http_get` +
     `emit_external_io_binding`, the SAME materialization
     `scripts/prose_to_operation_pipeline.py._author_http_get` uses),
     materialized once and cached; falls back to a plain urllib GET with the
     same UA/timeout discipline if the effector can't be materialized or its
     call fails, and
  3. **ingests** the result as graph data.

Node vocabulary (fixed contract — do not deviate):
    FetchRequest{url, status, purpose?, error?}
      -fetched-> WebDocument{url, title, text, status, byte_length}
                   -has_mention-> Mention{text}   (next_mention/prev_mention chained)

This module ALSO hosts the topic-SEARCH mechanism (`scan_and_search`), the
background twin of `domains/topic_grounding.ground_topic`. Same shape as fetch:
the agent mints the request node, this module performs the I/O and persists the
result. Vocabulary:
    SearchRequest{query, status, purpose?, source?, answer?, error?}
The DECISION to search is the agent's (`seeds/topic_search.json`'s rule);
`scan_and_search` resolves query→Wikipedia title→REST summary over HTTPS and
grounds it via `learn_from_teacher` (phrase-level), so `answer_about(query)`
answers offline thereafter. Mechanical I/O only.

Ingestion choice — MINIMAL, not `domains.worlds.web_world`'s DOM-as-graph:
`web_world`'s `_DomGraphParser` mints one `DomElement` node per HTML tag into
a THROWAWAY per-episode substrate (a fresh `srs.Substrate()` every
`reset()`), for an act/respond/observe RL-style loop that is dropped at
episode end. A `FetchRequest` lands in the PERSISTENT daemon graph,
checkpointed forever; mirroring every tag of every fetched page would bloat
every future checkpoint with markup structure nobody reads, for a one-shot
fetch that isn't navigating a DOM. Instead this module extracts plain TEXT
(+ the `<title>`) and tokenises it into `Mention` nodes exactly the way
`WorldAdapter._tokenise_mentions` tokenises an inbound chat Message
(has_mention / next_mention / prev_mention) — so fetched text is groundable
by the agent's EXISTING lexical / referent-resolution faculties, the same
shape as anything else it reads, at bounded per-fetch cost.

Refuses non-HTTP(S) schemes (`file://`, etc.) before any I/O — a security
boundary, not a content decision: GET is meant to be a side-effect-free,
remote-only read: crossing into the local filesystem is not "fetching the
web."

Node-id caution (CLAUDE.md): ids recycle from a freelist with no generation
counter — every raw id held across a call boundary is `has_node`-guarded.
"""
from __future__ import annotations

import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})
# Same UA the agent-authored effector's emitted source uses (see
# domains.runtime_design.emit_external_io_binding) — kept identical so the
# fallback path is honestly "the same discipline," not a different identity.
_FALLBACK_USER_AGENT = "gamma-substrate-agent/0.1 (research; agent-authored world-adapter)"
_MENTION_STRIP = ".,?!;:()[]\"'"   # same punctuation set as WorldAdapter._tokenise_mentions

# The materialized agent-authored http_get effector, cached module-level:
# exec'ing the emitted source on every scan_and_fetch call would be wasteful,
# and the effector is stateless host plumbing (a urllib wrapper), not agent
# state — safe to share across every WorldAdapter instance in this process.
_materialized: dict = {"fn": None, "tried": False}


def _materialize_http_get():
    """Materialize the agent-authored `http_get` effector once (cached).
    Returns the callable, or None if materialization fails (any reason —
    import error, exec error, missing symbol)."""
    if _materialized["tried"]:
        return _materialized["fn"]
    _materialized["tried"] = True
    try:
        from domains import runtime_design as _rd
        # substrate=None: this is mechanical I/O plumbing (materializing an
        # already-authored effector), not new agent reasoning, so it must
        # not write a fresh PrimitiveSpec provenance node into the live
        # graph on every daemon restart.
        spec = _rd.agent_specify_http_get(None)
        emitted = _rd.emit_external_io_binding(spec)
        ns: dict = {}
        exec(compile(emitted["world_adapter.py (binding)"],
                     "<agent_authored_http_get>", "exec"), ns)
        _materialized["fn"] = ns["http_get"]
    except Exception:  # noqa: BLE001 -- any materialization failure -> fall back
        _materialized["fn"] = None
    return _materialized["fn"]


def _cap_text(text: str, max_bytes: int) -> str:
    enc = text.encode("utf-8", "replace")
    if len(enc) <= max_bytes:
        return text
    return enc[:max_bytes].decode("utf-8", "replace")


def _plain_http_get(url: str, *, timeout: int, max_bytes: int) -> dict:
    """Fallback GET: same UA/timeout discipline as the agent-authored
    effector, but STREAMS a hard byte cap (`resp.read(max_bytes + 1)`) —
    unlike the materialized effector's emitted source, which has no cap
    parameter and always reads the whole body."""
    req = urllib.request.Request(url, headers={"User-Agent": _FALLBACK_USER_AGENT},
                                 method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(max_bytes + 1)
        status = resp.status
    text = body[:max_bytes].decode("utf-8", "replace")
    return {"status": status, "length": len(body), "text": text, "url": url}


def _fetch(url: str, *, timeout: int, max_bytes: int):
    """(fetched_dict, path_label). Tries the materialized agent-authored
    effector first (`path_label="agent_authored"`); its emitted source has
    no size cap, so its text is truncated to max_bytes HERE (best-effort —
    the full body is still read off the socket by the effector itself; only
    the fallback path streams a true cap). Falls back to `_plain_http_get`
    (`path_label="fallback_urllib"`, a real streamed cap) if materialization
    or the call itself fails."""
    fn = _materialize_http_get()
    if fn is not None:
        try:
            res = fn(url, timeout=timeout)
            return ({"status": res.get("status"), "length": res.get("length"),
                     "text": _cap_text(res.get("text", "") or "", max_bytes),
                     "url": res.get("url", url)}, "agent_authored")
        except Exception:  # noqa: BLE001 -- effector call failed -> fall back
            pass
    return _plain_http_get(url, timeout=timeout, max_bytes=max_bytes), "fallback_urllib"


def _refused_scheme(url: str):
    """None if `url` is admissible (http/https); else the refusal reason."""
    try:
        scheme = urlsplit(url).scheme.lower()
    except Exception:  # noqa: BLE001 -- unparseable url
        return "unparseable url"
    if scheme not in _ALLOWED_SCHEMES:
        return f"refused scheme {scheme!r} (HTTP(S) only)"
    return None


class _TextExtractor(HTMLParser):
    """Minimal HTML -> (title, text): strips tags, drops <script>/<style>
    content, collapses to whitespace-joined visible text. Mechanical markup
    removal only — no decisions over the content (the read-side counterpart
    to `domains.worlds._DomGraphParser`'s structural parse; this one keeps
    TEXT instead of a per-tag graph — see the module docstring)."""
    _SKIP = frozenset({"script", "style"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._chunks: list = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            if data.strip() and not self.title:
                self.title = data.strip()
            return
        if data.strip():
            self._chunks.append(data.strip())

    @property
    def text(self) -> str:
        return " ".join(self._chunks)


def _ingest_web_document(agent, request_node, url: str, fetched: dict):
    """Parse the fetched HTML -> (title, text); write a WebDocument node +
    the `fetched` edge + Mention tokenisation (the SAME shape
    `WorldAdapter._tokenise_mentions` gives an inbound Message). Mechanical
    translation only. Returns the WebDocument node id."""
    S, I = agent.s, agent.inner
    parser = _TextExtractor()
    try:
        parser.feed(fetched.get("text", "") or "")
        parser.close()
    except Exception:  # noqa: BLE001 -- malformed markup: keep whatever was parsed
        pass
    doc = S.add_node("WebDocument", {
        "url": str(fetched.get("url") or url), "title": parser.title,
        "text": parser.text, "status": fetched.get("status"),
        "byte_length": fetched.get("length") or 0,
    })
    I.add_edge_unchecked(request_node, "fetched", doc)

    prev = None
    for raw in parser.text.split():
        clean = raw.strip(_MENTION_STRIP).lower()
        if not clean:
            continue
        mn = S.add_node("Mention", {"text": clean})
        I.add_edge_unchecked(doc, "has_mention", mn)
        if prev is not None:
            I.add_edge_unchecked(prev, "next_mention", mn)
            I.add_edge_unchecked(mn, "prev_mention", prev)
        prev = mn
    return doc


def mint_fetch_request(agent, url: str, purpose: str = ""):
    """Hand-mint a FetchRequest node. A test/authoring helper — the agent
    will mint these itself via its own rules (not this function's concern);
    this exists so the fetch MECHANISM can be exercised/tested without that
    agent-authoring machinery (mirrors
    `domains.experiment_dispatch.mint_experiment`)."""
    return agent.s.add_node("FetchRequest", {
        "url": str(url), "status": "requested", "purpose": str(purpose or ""),
    })


def mint_search_request(agent, query: str, purpose: str = ""):
    """Hand-mint a SearchRequest node. A test/authoring helper — the agent mints
    these itself via its own rules (`seeds/topic_search.json`); this exists so the
    search MECHANISM can be exercised/tested without that rule machinery (mirrors
    `mint_fetch_request`)."""
    return agent.s.add_node("SearchRequest", {
        "query": str(query), "status": "requested", "purpose": str(purpose or ""),
    })


def scan_and_search(agent, *, http_get=None, timeout: int = 15,
                    log=lambda *a: None) -> list:
    """Find every REQUESTED SearchRequest, resolve query→title→summary and ground
    the TOPIC (phrase-level, via `domains.topic_grounding.resolve_and_ground`:
    local Wikipedia library first, then a live Wikipedia REST lookup over HTTPS),
    persist the answer through `learn_from_teacher` (so `answer_about(query)`
    returns it offline thereafter), and mark done/failed. Returns the node-id list
    of every SearchRequest touched this call. Mirrors `scan_and_fetch` — mechanical
    I/O only; the DECISION to search is the agent's (the `topic_search` seed rule
    mints the SearchRequest), and the SOURCE decides the meaning.

    `http_get(url, timeout=...) -> {status, length, text, url}`, if supplied, is
    threaded to the web path AS GIVEN (e.g. tests with a canned resolver);
    otherwise `topic_grounding`'s own http machinery is used."""
    from domains import topic_grounding as _tg
    S, I = agent.s, agent.inner
    touched: list = []
    for req in list(S.nodes("SearchRequest")):
        if not I.has_node(req):
            continue
        a = S.node(req)["attrs"]
        if a.get("status") != "requested":
            continue
        query = a.get("query") or ""
        I.set_attr(req, "status", "running")
        touched.append(req)

        if not str(query).strip():
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "empty query")
            log("search refused: empty query")
            continue

        try:
            count = _tg.ingest_search_candidates(agent, req, str(query), timeout=timeout,
                                                   http_get=http_get)
            if count <= 0:
                I.set_attr(req, "status", "failed")
                I.set_attr(req, "error", "no candidates")
                log(f"search miss: {query!r} (no candidates)")
                continue
            I.set_attr(req, "status", "candidates_ready")
            try:
                agent.comprehend()
            except Exception:  # noqa: BLE001
                pass
            ans = _tg.commit_selected_search(agent, req, str(query))
        except Exception as e:  # noqa: BLE001 -- network/host failure -> failed, not a crash
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"{type(e).__name__}: {e}")
            log(f"search failed ({query!r}): {type(e).__name__}: {e}")
            continue

        if not ans:
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "no verified candidate")
            log(f"search miss: {query!r} (no verified candidate)")
            continue

        I.set_attr(req, "answer", _cap_text(str(ans), 4000))
        I.set_attr(req, "status", "done")
        log(f"searched {query!r} -> grounded ({len(str(ans))} chars)")
    return touched


def scan_and_sync_ground(agent, *, log=lambda *a: None) -> list:
    """Fulfil every REQUESTED GroundRequest via the synchronous phrase grounder
    (domains.topic_grounding.ground_topic / ground_topic_aspect). The graph's
    topic_sync_ground seed mints these; this is mechanical I/O only."""
    from domains import topic_grounding as _tg
    S, I = agent.s, agent.inner
    touched: list = []
    for req in list(S.nodes("GroundRequest")):
        if not I.has_node(req):
            continue
        a = S.node(req)["attrs"]
        if a.get("status") != "requested":
            continue
        query = str(a.get("query") or "").strip()
        aspect = a.get("aspect")
        I.set_attr(req, "status", "running")
        touched.append(req)
        if not query:
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "empty query")
            log("sync ground refused: empty query")
            continue
        try:
            if aspect and str(aspect).strip():
                ans = _tg.ground_topic_aspect(agent, query, str(aspect).strip())
            else:
                ans = _tg.ground_topic(agent, query)
        except Exception as e:  # noqa: BLE001
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"{type(e).__name__}: {e}")
            log(f"sync ground failed ({query!r}): {type(e).__name__}: {e}")
            continue
        if not ans:
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "no answer")
            log(f"sync ground miss: {query!r}")
            continue
        I.set_attr(req, "answer", _cap_text(str(ans), 4000))
        I.set_attr(req, "status", "done")
        log(f"sync grounded {query!r} ({len(str(ans))} chars)")
    return touched


def mint_detail_request(agent, topic: str):
    """Hand-mint a DetailRequest node. A test/authoring helper -- the agent mints
    these itself via its own rule (seeds/conversation_elaborate.json's
    request_detail_for_current_topic); this exists so the detail MECHANISM can be
    exercised/tested without that rule machinery (mirrors `mint_search_request`)."""
    return agent.s.add_node("DetailRequest", {
        "topic": str(topic), "status": "requested",
    })


def _topic_node(agent, name: str):
    """Find-or-create the persistent `Topic{name}` node the detail chain hangs
    off (name-guarded -> idempotent). Mechanical graph write, no decision."""
    S, I = agent.s, agent.inner
    for t in S.nodes("Topic"):
        if not I.has_node(t):
            continue
        if S.node(t)["attrs"].get("name") == name:
            return t
    return S.add_node("Topic", {"name": str(name)})


def _ingest_detail_chain(agent, topic_name: str, chunks: list) -> int:
    """Ingest an ORDERED list of detail chunk strings as a graph CHAIN hung off
    `Topic{name:topic_name}` -- exactly the mechanical translation
    `_ingest_web_document` does for a Mention chain, at paragraph grain:
        Topic -detail_head-> c0
        Topic -has_detail-> c      (every chunk)
        c -next_detail-> c_next    (reading order)
    Skips chunks already ingested for this topic (by text) so a re-run appends
    only NEW detail rather than duplicating. Returns the count of chunks added.
    Pure translation -- no decisions over graph state."""
    S, I = agent.s, agent.inner
    topic = _topic_node(agent, topic_name)
    # Existing chunk texts for this topic (dedup on re-ingest).
    have = set()
    tail = None
    for c in list(I.neighbours(topic, "has_detail")):
        if not I.has_node(c):
            continue
        ca = S.node(c)["attrs"]
        have.add(ca.get("text"))
    # Locate the current tail of the chain (the chunk with no next_detail out).
    existing = [c for c in I.neighbours(topic, "has_detail") if I.has_node(c)]
    for c in existing:
        if not list(I.neighbours(c, "next_detail")):
            tail = c
    has_head = bool(list(I.neighbours(topic, "detail_head")))
    added = 0
    prev = tail
    for raw in chunks:
        text = str(raw or "").strip()
        if not text or text in have:
            continue
        cn = S.add_node("DetailChunk", {"text": text, "topic": str(topic_name)})
        I.add_edge_unchecked(topic, "has_detail", cn)
        have.add(text)
        if prev is None and not has_head:
            I.add_edge_unchecked(topic, "detail_head", cn)
            has_head = True
        if prev is not None:
            I.add_edge_unchecked(prev, "next_detail", cn)
        prev = cn
        added += 1
    return added


def scan_and_ingest_detail(agent, *, http_get=None, timeout: int = 8,
                           allow_web: bool = True, log=lambda *a: None) -> list:
    """Find every REQUESTED DetailRequest, fetch its topic's progressive-detail
    chunks (`domains.topic_grounding.topic_detail`: local wiki sections, else the
    live Wikipedia extracts API over HTTPS), ingest them as a graph CHAIN, and
    mark done/failed. Returns the node-id list of every DetailRequest touched
    this call. Mirrors `scan_and_search` -- mechanical I/O only; the DECISION to
    prefetch detail for the current topic is the agent's (the
    `request_detail_for_current_topic` seed rule mints the DetailRequest), and the
    progressive-disclosure DECISION is the `conversation_elaborate` serve rules;
    this module only performs the fetch + ingest.

    `http_get(url, timeout=...) -> {status, length, text, url}`, if supplied, is
    threaded to `topic_detail`'s web path AS GIVEN (e.g. tests with a canned
    resolver)."""
    from domains import topic_grounding as _tg
    S, I = agent.s, agent.inner
    touched: list = []
    for req in list(S.nodes("DetailRequest")):
        if not I.has_node(req):
            continue
        a = S.node(req)["attrs"]
        if a.get("status") != "requested":
            continue
        topic = a.get("topic") or ""
        I.set_attr(req, "status", "running")
        touched.append(req)

        if not str(topic).strip():
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "empty topic")
            log("detail refused: empty topic")
            continue

        try:
            chunks = _tg.topic_detail(agent, str(topic), allow_web=allow_web,
                                      timeout=timeout, http_get=http_get)
        except Exception as e:  # noqa: BLE001 -- network/host failure -> failed, not a crash
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"{type(e).__name__}: {e}")
            log(f"detail failed ({topic!r}): {type(e).__name__}: {e}")
            continue

        if not chunks:
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", "no detail")
            log(f"detail miss: {topic!r}")
            continue

        try:
            added = _ingest_detail_chain(agent, str(topic), chunks)
        except Exception as e:  # noqa: BLE001 -- ingestion failure -> failed, not a crash
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"ingest {type(e).__name__}: {e}")
            log(f"detail ingest failed ({topic}): {type(e).__name__}: {e}")
            continue
        I.set_attr(req, "status", "done")
        log(f"detail {topic!r} -> ingested {added} chunk(s)")
    return touched


def scan_and_fetch(agent, *, http_get=None, max_bytes: int = 2_000_000,
                    timeout: int = 15, log=lambda *a: None) -> list:
    """Find every REQUESTED FetchRequest, fetch it synchronously (fetches
    are seconds — no subprocess/async machinery needed, unlike
    `experiment_dispatch`'s episode runs), ingest the result, and mark
    done/failed. Returns the node-id list of every FetchRequest touched this
    call. Safe to call repeatedly; does nothing when there is nothing to do.

    `http_get(url, timeout=...) -> {status, length, text, url}`, if
    supplied, is used AS GIVEN (no fallback on its failure — the caller
    picked it, e.g. tests pointing at a local server); otherwise the
    agent-authored effector is materialized (falling back to a plain urllib
    GET only in THAT path, see `_fetch`). HTTP(S) only; other schemes are
    refused before any I/O (a security boundary, not a decision about
    content) and land `status="failed"`."""
    S, I = agent.s, agent.inner
    touched: list = []
    for req in list(S.nodes("FetchRequest")):
        if not I.has_node(req):
            continue
        a = S.node(req)["attrs"]
        if a.get("status") != "requested":
            continue
        url = a.get("url") or ""
        I.set_attr(req, "status", "running")
        touched.append(req)

        refused = _refused_scheme(url)
        if refused is not None:
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", refused)
            log(f"fetch refused: {url!r} ({refused})")
            continue

        from domains.information_commitment import assess
        gate = assess(
            agent,
            commit={
                "name": "http_get",
                "expected_information_gain": float(
                    a.get("expected_information_gain", 1.0)),
                "expected_goal_work": float(a.get("expected_goal_work", 0.0)),
                "uncertainty": float(a.get("consequence_uncertainty", 0.0)),
                "footprint": {
                    "deleted_facts": 0.0, "overwritten_facts": 0.0,
                    "recoverability": 1.0,
                    "externality": float(a.get("externality_cost", 0.0)),
                },
            },
            wait={
                "preservation_value": 0.0,
                "delay_cost": float(a.get("delay_cost", 0.1)),
            },
            refine={"refinement_cost": 1.0},
        )
        I.set_attr(req, "commit_decision", gate["decision"] or "undetermined")
        if gate["decision"] != "commit" or not gate["authorized"]:
            I.set_attr(req, "status", "deferred")
            continue

        try:
            if http_get is not None:
                res = http_get(url, timeout=timeout)
                fetched = {"status": res.get("status"), "length": res.get("length"),
                          "text": _cap_text(res.get("text", "") or "", max_bytes),
                          "url": res.get("url", url)}
                path = "supplied"
            else:
                fetched, path = _fetch(url, timeout=timeout, max_bytes=max_bytes)
        except Exception as e:  # noqa: BLE001 -- network/host failure -> failed, not a crash
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"{type(e).__name__}: {e}")
            log(f"fetch failed ({url}): {type(e).__name__}: {e}")
            continue

        log(f"fetched {url!r} via {path} ({fetched.get('length')} bytes)")
        try:
            _ingest_web_document(agent, req, url, fetched)
        except Exception as e:  # noqa: BLE001 -- ingestion failure -> failed, not a crash
            I.set_attr(req, "status", "failed")
            I.set_attr(req, "error", f"ingest {type(e).__name__}: {e}")
            log(f"ingest failed ({url}): {type(e).__name__}: {e}")
            continue
        I.set_attr(req, "status", "done")
    return touched
