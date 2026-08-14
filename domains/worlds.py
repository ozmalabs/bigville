"""World adapters for the curious agent — the body the mind lives in.

A "world" is a tiny dict of callables that the agent's loop calls:

- ``reset()`` — start a fresh episode, return ``(substrate, ctx)``.
- ``legal_actions(substrate, ctx)`` — actions available now. Empty list = terminal.
- ``apply_action(substrate, ctx, action)`` — execute the action; return new state.
- ``interpret_acts_on(substrate, ctx, action)`` — body-type names this action
  *touches*, registered as ``acts_on`` boundary edges. Empty list = spectator.

This is the boundary between the agent's mind (domain-agnostic) and the
domain's specifics. Two worlds shipped here: chess (full agency) and Conway
(spectator — the agent watches the world evolve but can't intervene).
"""
from __future__ import annotations

import random
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import chess as pc

from domains import chess as cg
from domains import conway as cv


World = dict  # {"reset": fn, "legal_actions": fn, "apply_action": fn, "interpret_acts_on": fn}


# --- Chess: agent has full agency ---


def _chess_piece_type_name(piece) -> str:
    color = "White" if piece.color else "Black"
    kind = {
        pc.PAWN: "Pawn", pc.KNIGHT: "Knight", pc.BISHOP: "Bishop",
        pc.ROOK: "Rook", pc.QUEEN: "Queen", pc.KING: "King",
    }[piece.piece_type]
    return f"{color}{kind}"


def chess_world() -> World:
    """The chess body. Agent picks legal moves; acts_on the pieces it moves
    (and captures). Squares are sensed and modeled but never acted on."""

    def reset():
        s = cg.make_substrate()
        ctx = cg.encode_fen(s, pc.STARTING_FEN)
        return s, ctx

    def legal_actions(substrate, ctx):
        return list(ctx["board"].legal_moves)

    def apply_action(substrate, ctx, action):
        return cg.apply_move(substrate, ctx, action)

    def interpret_acts_on(substrate, ctx, action):
        board = ctx["board"]
        types: list[str] = []
        moved = board.piece_at(action.from_square)
        if moved is not None:
            types.append(_chess_piece_type_name(moved))
        if board.is_capture(action):
            if board.is_en_passant(action):
                cap_sq = pc.square(pc.square_file(action.to_square),
                                   pc.square_rank(action.from_square))
                captured = board.piece_at(cap_sq)
            else:
                captured = board.piece_at(action.to_square)
            if captured is not None:
                types.append(_chess_piece_type_name(captured))
        return types

    return {
        "name": "chess",
        "reset": reset,
        "legal_actions": legal_actions,
        "apply_action": apply_action,
        "interpret_acts_on": interpret_acts_on,
    }


# --- Conway: spectator world. The agent watches; it cannot intervene ---


def conway_world(rows: int = 12, cols: int = 12, density: float = 0.35,
                 seed: int = 42, grammar_fn=cv.conway_grammar) -> World:
    """Conway's Game of Life. The agent observes Cell-type transitions but
    has no admissible actions other than letting the world step.

    Designed deliberately as a spectator world to demonstrate that the
    boundary texture differs across worlds without changing agent code:
    chess has rich ``acts_on``; Conway has none.
    """
    state = {"seed_counter": seed}

    def reset():
        rng = random.Random(state["seed_counter"])
        state["seed_counter"] += 1
        board = [[1 if rng.random() < density else 0 for _ in range(cols)]
                 for _ in range(rows)]
        s = cv.make_substrate(grammar_fn)
        cv.encode_board(s, board)
        return s, {"step_count": 0, "rows": rows, "cols": cols}

    def legal_actions(substrate, ctx):
        # The only action the agent can take is "let the world advance one step."
        # The agent has no choice — but the loop still passes through it so the
        # observation cycle runs.
        return ["step"]

    def apply_action(substrate, ctx, action):
        cv.step(substrate)
        ctx["step_count"] += 1
        return substrate, ctx

    def interpret_acts_on(substrate, ctx, action):
        # Conway's evolution is not the agent's doing — it's the world's own
        # dynamics. Nothing registers as acts_on. The boundary's acts_on set
        # stays empty across Conway lifetimes.
        return []

    return {
        "name": "conway",
        "reset": reset,
        "legal_actions": legal_actions,
        "apply_action": apply_action,
        "interpret_acts_on": interpret_acts_on,
    }


# --- Web: the GET-only web-WORLD (cmsg105b re-design realized) ---
#
# The web-WORLD ADAPTER. cmsg105b: the agent recognized the web is a WORLD (act/
# respond/observe via the World contract), not a dispenser. cmsg106: it authored
# the http_get external-IO effector (a real GET fetch worked). This realizes the
# re-design: the worlds.py World contract OVER http_get, with the DOM parsed as a
# typed GRAPH (the agent's "X is a graph" move) and navigation (following an
# <a href> link) as the actions.
#
# GET ONLY — the consequence-aware SAFE subset. legal_actions/apply_action are
# NAVIGATE-A-LINK (follow an <a href>), the safe idempotent action. NO POST /
# forms / login / side-effects — those are the CONSEQUENTIAL actions the cmsg105b
# not-preview-safe model GATES (out of scope; the safe subset is GET-navigation).
#
# The DOM-as-graph is admissible substrate vocabulary (DomElement nodes + child /
# links_to edges), opened as Γ productions — the same move open_grounding_
# productions makes for grounding edges. The fetch is the cmsg106 http_get
# binding (urllib, descriptive UA, timeout). No content is read into meaning here
# (that is the read-side grounding, separate) — the world OBSERVES the STRUCTURE.


# The DOM vocabulary the web-world admits into Γ (the agent's "X is a graph").
_DOM_NODE_TYPE = "DomElement"
_DOM_LINK_TYPE = "DomLink"
_DOM_CHILD_EDGE = "dom_child"      # DomElement -> DomElement (parent/child tree)
_DOM_LINK_EDGE = "dom_link"        # DomElement -> DomLink (a navigable <a href>)
_WEB_USER_AGENT = ("gamma-substrate-agent/0.1 "
                   "(research; agent-authored web-world adapter; GET-only)")
# Elements that carry no structural meaning for navigation — skipped as DOM nodes
# so the graph counts the page STRUCTURE, not boilerplate void elements' noise.
_VOID_SKIP = frozenset()


def _open_dom_productions(substrate) -> int:
    """Open the Γ productions that admit the DOM-as-typed-graph vocabulary —
    DomElement nodes, parent/child tree edges, and the navigable <a href> link
    edges. Without this the substrate's admissibility grammar rejects the DOM
    nodes (Type-2: not in vocabulary). The SAME move open_grounding_productions
    makes for grounding edges: the agent's 'X is a graph' requires admitting X's
    vocabulary. Idempotent (add_production is additive)."""
    n = 0
    prods = [
        ({"type": _DOM_NODE_TYPE, "var": "p"}, _DOM_CHILD_EDGE,
         {"type": _DOM_NODE_TYPE, "var": "c"}),
        ({"type": _DOM_NODE_TYPE, "var": "e"}, _DOM_LINK_EDGE,
         {"type": _DOM_LINK_TYPE, "var": "l"}),
    ]
    for src, et, tgt in prods:
        try:
            substrate.add_production({
                "src": src, "edge_type": et, "tgt": tgt,
                "where": None, "provenance": "web_world:dom"})
            n += 1
        except Exception:
            pass
    return n


class _DomGraphParser(HTMLParser):
    """The DOM-as-typed-GRAPH parser (stdlib html.parser — the agent's 'X is a
    graph' ingest). It walks the HTML token stream and writes the DOM into the
    substrate AS a typed graph: each start tag -> a DomElement node, parent/child
    nesting -> dom_child edges, each <a href> -> a DomLink node + a dom_link edge
    (the navigable out-edge, GET-only).

    Mechanical translation only (CLAUDE.md: Python translates external I/O into
    substrate mutations — no decisions over graph state). It does NOT read body
    TEXT into meaning (that is the read-side grounding, out of scope); it records
    the <title> text as a single structural marker (mechanism-confirmation)."""

    def __init__(self, substrate, base_url: str):
        super().__init__(convert_charrefs=True)
        self.s = substrate
        self.base_url = base_url
        self.root = substrate.add_node(_DOM_NODE_TYPE,
                                       {"tag": "#document", "url": base_url})
        self._stack = [self.root]
        self.links: list[dict[str, Any]] = []   # navigable <a href> out-edges
        self.n_nodes = 1
        self.n_links = 0
        self.title = ""
        self._in_title = False

    # void elements have no end tag — don't leave them on the nesting stack.
    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img",
                       "input", "link", "meta", "param", "source", "track",
                       "wbr"})

    def handle_starttag(self, tag, attrs):
        parent = self._stack[-1]
        node = self.s.add_node(_DOM_NODE_TYPE, {"tag": tag})
        self.s.add_edge(parent, _DOM_CHILD_EDGE, node)
        self.n_nodes += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                # Resolve to an absolute URL; keep ONLY http(s) (the GET-safe
                # navigable subset — no javascript:/mailto:/fragment-only).
                absu = urljoin(self.base_url, href)
                if urlsplit(absu).scheme in ("http", "https"):
                    link = self.s.add_node(_DOM_LINK_TYPE,
                                           {"href": absu, "tag": "a"})
                    self.s.add_edge(node, _DOM_LINK_EDGE, link)
                    self.links.append({"href": absu, "node": node,
                                       "link_node": link})
                    self.n_links += 1
        if tag == "title":
            self._in_title = True
        if tag not in self._VOID:
            self._stack.append(node)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag not in self._VOID and len(self._stack) > 1:
            # Pop to the matching tag if present (tolerant of malformed HTML).
            for i in range(len(self._stack) - 1, 0, -1):
                if self.s.node(self._stack[i])["attrs"].get("tag") == tag:
                    del self._stack[i:]
                    break

    def handle_data(self, data):
        if self._in_title and data.strip() and not self.title:
            self.title = data.strip()


def web_world(http_get: Callable[..., dict],
              start_url: str = "https://example.com/") -> World:
    """The GET-only web-WORLD adapter — the worlds.py World contract over the
    agent's own http_get effector (cmsg106), with the DOM parsed as a typed
    GRAPH and link-navigation as the actions.

    ``http_get`` is the agent-authored external-IO binding (runtime_design.
    emit_external_io_binding -> ``http_get(url, timeout=...) -> {status, length,
    text, url}``). The web-world is the act/respond/observe loop OVER it.

    The contract (mirrors chess/conway):

      * reset()                       -> (substrate, ctx) : http_get(start_url),
        parse the DOM into the substrate as a typed graph, return the initial
        STATE (ctx carries the current node-id/url + the page's DOM-graph handles).
      * legal_actions(substrate, ctx) -> [action, ...]    : the NAVIGABLE links
        (the dom_link out-edges of the current page) — NAVIGATE actions, GET-only
        (the safe subset). Empty = terminal (a leaf / unreachable page).
      * apply_action(substrate, ctx, a) -> (substrate, ctx): http_get the link's
        URL, parse its DOM-graph -> the NEW state. The world RESPONDS with a new
        page-state. GET-only; an action is a navigate-a-link dict.
      * interpret_acts_on(...)        -> [type, ...]      : a NAVIGATE touches the
        link target's host (the boundary the agent reaches across) — reported as
        the DomLink type (spectator-ish: the web responds, the agent only reads).

    SAFETY: GET ONLY. The actions are navigate-a-link (<a href>), the safe,
    idempotent subset. NO POST/forms/login/side-effects — those CONSEQUENTIAL
    actions are GATED (the cmsg105b not-preview-safe model; out of scope). This
    is the agent applying its consequence-awareness: the safe action set."""

    def _ingest(substrate, url: str, timeout: int = 15) -> dict:
        """http_get(url) -> parse the DOM into the substrate as a typed graph ->
        return the page-state handles. The act of OBSERVING: a page becomes a
        typed graph in the substrate (the 'X is a graph' move). GET-only."""
        res = http_get(url, timeout=timeout, user_agent=_WEB_USER_AGENT)
        parser = _DomGraphParser(substrate, url)
        parser.feed(res.get("text", ""))
        parser.close()
        return {
            "url": url,
            "status": res.get("status"),
            "byte_length": res.get("length"),
            "root": parser.root,
            "n_nodes": parser.n_nodes,
            "n_links": parser.n_links,
            "links": parser.links,        # [{href, node, link_node}, ...]
            "title": parser.title,        # the <title> structural marker only
        }

    def reset():
        # A fresh substrate with the DOM-as-graph vocabulary admitted into Γ.
        import substrate_rs as srs
        s = srs.Substrate()
        _open_dom_productions(s)
        page = _ingest(s, start_url)
        ctx = {"page": page, "url": page["url"], "visited": [page["url"]],
               "step": 0}
        return s, ctx

    def legal_actions(substrate, ctx):
        # The navigable links of the CURRENT page = the dom_link out-edges. Each
        # is a NAVIGATE action (GET-only, the safe subset). De-duplicate by URL
        # so the action set is the distinct navigable destinations.
        seen: set[str] = set()
        actions: list[dict[str, Any]] = []
        for lk in ctx["page"]["links"]:
            href = lk["href"]
            if href in seen:
                continue
            seen.add(href)
            actions.append({"kind": "navigate", "method": "GET",
                            "href": href, "from_node": lk["node"],
                            "link_node": lk["link_node"]})
        return actions

    def apply_action(substrate, ctx, action):
        # ACT: navigate the link (GET) -> the world RESPONDS with a new page-state
        # (the linked page's DOM-graph). GET-only — refuse anything else (the
        # consequence-aware safety rail, in the world itself).
        if not isinstance(action, dict) or action.get("kind") != "navigate" \
                or action.get("method", "GET").upper() != "GET":
            raise ValueError(
                "web_world admits only GET navigate-a-link actions (the safe, "
                f"idempotent subset); refused {action!r}")
        page = _ingest(substrate, action["href"])
        ctx = dict(ctx)
        ctx["page"] = page
        ctx["url"] = page["url"]
        ctx["visited"] = ctx.get("visited", []) + [page["url"]]
        ctx["step"] = ctx.get("step", 0) + 1
        return substrate, ctx

    def interpret_acts_on(substrate, ctx, action):
        # A navigate REACHES the link target across the world boundary. The agent
        # does not mutate the remote host (GET is side-effect-free) — it reads the
        # response. The boundary type touched is the DomLink (the navigable edge).
        if isinstance(action, dict) and action.get("kind") == "navigate":
            return [_DOM_LINK_TYPE]
        return []

    def observe(substrate, ctx):
        """OBSERVE the current state as the DOM-as-typed-GRAPH: the STRUCTURE
        (node count, navigable-link count, the <title> marker) + the live graph
        handles (root node-id; the dom_child tree + dom_link out-edges are in the
        substrate). Reports STRUCTURE, never page content."""
        page = ctx["page"]
        return {
            "url": page["url"],
            "status": page["status"],
            "byte_length": page["byte_length"],
            "dom_nodes": page["n_nodes"],
            "dom_links": page["n_links"],
            "root_node": page["root"],
            "title_marker": page["title"],   # structural marker only, no body
            "node_type": _DOM_NODE_TYPE,
            "child_edge": _DOM_CHILD_EDGE,
            "link_edge": _DOM_LINK_EDGE,
        }

    return {
        "name": "web",
        "method": "GET",                 # the safe subset; no POST/forms
        "start_url": start_url,
        "reset": reset,
        "legal_actions": legal_actions,
        "apply_action": apply_action,
        "interpret_acts_on": interpret_acts_on,
        "observe": observe,
    }
