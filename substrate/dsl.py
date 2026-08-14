"""Reflective expression language for Γ-productions.

Every Term is a dataclass; every Term round-trips losslessly to a G-subgraph via
``term_to_subgraph`` / ``term_from_subgraph``. This satisfies Axiom 3 by
construction — Γ is representable as a subgraph of G.
"""
from __future__ import annotations

import dataclasses
import functools
import math
from dataclasses import dataclass, field
from typing import Any


_TERM_REGISTRY: dict[str, type[Term]] = {}


def _register(cls: type[Term]) -> type[Term]:
    _TERM_REGISTRY[cls.__name__] = cls
    return cls


class Term:
    """Base. Subclasses are frozen dataclasses with an ``evaluate`` method."""

    def evaluate(self, env: dict[str, Any], G) -> Any:  # noqa: N803
        raise NotImplementedError(type(self).__name__)


@_register
@dataclass(frozen=True)
class Var(Term):
    name: str

    def evaluate(self, env, G):
        return env[self.name]


@_register
@dataclass(frozen=True)
class Lit(Term):
    # scalar: str | int | float | bool | None | fractions.Fraction.
    # Fraction mirrors the Rust engine's `Value::Rational` (PROGRAM_
    # SYNTHESIS_ARC5_RATIONAL.md) -- the PROGRAM value domain's exact,
    # in-frame numeric type. No special-casing is needed below:
    # Python's own `+`/`-`/`*`/`/` on a Fraction are ALREADY exact
    # (Fraction(1,3)+Fraction(1,3)+Fraction(1,3) == 1, Fraction/Fraction
    # stays a Fraction) -- this Python-side mirror gets exactness for
    # free from the stdlib, the same way the Rust engine's Value enum
    # gets it from `runners/dsl/src/value.rs`'s `rational_*` helpers.
    # The wire tag `{"__rational__": [num, den]}` (`persist::encode_value`
    # / `decode_value`) is a JSON-transport concern for `add_term_
    # subgraph`/`SynthEnumerate`/`ProgEval` callers building Term-JSON
    # dicts directly (e.g. `domains/prog_exact.py`); this Python-object
    # -level Term tree never needs it -- a `Lit(value=Fraction(4, 3))`
    # here already carries the exact value.
    value: Any

    def evaluate(self, env, G):
        return self.value


@_register
@dataclass(frozen=True)
class TypeOf(Term):
    node: Term

    def evaluate(self, env, G):
        nid = self.node.evaluate(env, G)
        return G.node(nid).type


@_register
@dataclass(frozen=True)
class Attr(Term):
    node: Term
    key: str

    def evaluate(self, env, G):
        nid = self.node.evaluate(env, G)
        return G.node(nid).attrs.get(self.key)


@_register
@dataclass(frozen=True)
class AttrByName(Term):
    """Dynamic attribute access: read ``node``'s attr whose key is the string
    ``name`` evaluates to (vs ``Attr``, whose key is a static literal). Enables
    parameterized goals — one generic satisfaction Term reads the target's attr
    named by the goal's own ``target_attr``."""
    node: Term
    name: Term

    def evaluate(self, env, G):
        nid = self.node.evaluate(env, G)
        key = self.name.evaluate(env, G)
        return G.node(nid).attrs.get(key)


@_register
@dataclass(frozen=True)
class SetT(Term):
    """Set literal / set-construction. Field is a tuple of child terms."""
    items: tuple = ()

    def evaluate(self, env, G):
        return frozenset(t.evaluate(env, G) for t in self.items)


@_register
@dataclass(frozen=True)
class In(Term):
    member: Term
    container: Term

    def evaluate(self, env, G):
        return self.member.evaluate(env, G) in self.container.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Eq(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) == self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Lt(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) < self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Lte(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) <= self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Gt(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) > self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Gte(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) >= self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Neighbours(Term):
    """Set of neighbour NodeIDs reachable via outgoing edges of ``edge_type``.

    If ``edge_type`` is None, all outgoing neighbours.
    """
    node: Term
    edge_type: str | None = None

    def evaluate(self, env, G):
        nid = self.node.evaluate(env, G)
        cache = G._eval_cache
        if cache is not None:
            key = (nid, self.edge_type)
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = frozenset(G.neighbours(nid, edge_type=self.edge_type))
            cache[key] = result
            return result
        return frozenset(G.neighbours(nid, edge_type=self.edge_type))


@_register
@dataclass(frozen=True)
class InNeighbours(Term):
    """Set of NodeIDs that have an outgoing edge of ``edge_type`` to ``node``.

    "Who points at me with this edge type" — e.g., from a Square, which Pieces
    have a ``piece_at`` edge to me.
    """
    node: Term
    edge_type: str | None = None

    def evaluate(self, env, G):
        nid = self.node.evaluate(env, G)
        cache = G._eval_cache
        if cache is not None:
            key = (nid, self.edge_type, "in")
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = frozenset(e.key.src for e in G.in_edges(nid, edge_type=self.edge_type))
            cache[key] = result
            return result
        return frozenset(e.key.src for e in G.in_edges(nid, edge_type=self.edge_type))


@_register
@dataclass(frozen=True)
class Count(Term):
    source: Term

    def evaluate(self, env, G):
        return len(self.source.evaluate(env, G))


@_register
@dataclass(frozen=True)
class Filter(Term):
    """For each item in ``source``, bind ``var_name`` and keep if ``predicate`` holds.

    Memoizes results under the step cache, keyed by ``(id(self), free-var bindings)``
    — two productions sharing the same Filter instance hit the cache on the second
    probe of a cell.
    """
    source: Term
    var_name: str
    predicate: Term

    def evaluate(self, env, G):
        cache = G._eval_cache
        key = None
        if cache is not None:
            fv = free_vars(self)
            if fv.issubset(env):
                key = (id(self), tuple((k, env[k]) for k in sorted(fv)))
                hit = cache.get(key)
                if hit is not None:
                    return hit
        items = self.source.evaluate(env, G)
        out = set()
        for it in items:
            new_env = {**env, self.var_name: it}
            if self.predicate.evaluate(new_env, G):
                out.add(it)
        result = frozenset(out)
        if key is not None:
            cache[key] = result
        return result


@_register
@dataclass(frozen=True)
class MapNeighbours(Term):
    """Flat-map: the union of out-neighbours (via ``edge_type``) over
    every node in ``source`` (a set-valued Term). Lets traversal chain
    across sets — e.g. the perpendiculars of the direction(s) a boundary
    faces. ``Neighbours`` hops from one node; ``MapNeighbours`` hops from
    a whole set, which is what multi-hop graph reasoning needs."""
    source: Term
    edge_type: str | None = None

    def evaluate(self, env, G):
        out: set = set()
        for nid in self.source.evaluate(env, G):
            out.update(G.neighbours(nid, edge_type=self.edge_type))
        return frozenset(out)


@_register
@dataclass(frozen=True)
class Exists(Term):
    """Existential over a set: True iff at least one item in ``source``
    satisfies ``predicate`` with ``var_name`` bound to it. A binder like
    ``Filter``; ``free_vars`` removes ``var_name`` from the predicate."""
    source: Term
    var_name: str
    predicate: Term

    def evaluate(self, env, G):
        for it in self.source.evaluate(env, G):
            if self.predicate.evaluate({**env, self.var_name: it}, G):
                return True
        return False


@_register
@dataclass(frozen=True)
class EvalSubgraph(Term):
    """Evaluate the Term-tree rooted at the NodeID ``node`` resolves to.

    ``node`` is a Term that evaluates to a NodeID; the engine walks
    that node as a Term subgraph root (per :func:`term_from_subgraph`),
    reconstructs the Term tree, and evaluates it under the CURRENT
    env. Lets graph-resident Terms reference other graph-resident
    Terms by NodeID — the substrate's "evaluate what this attr/edge
    points to" primitive. Phase 17b uses it to migrate the emotion
    EMA loop out of Python: a Rule's effect computes
    ``EvalSubgraph(Pick(Neighbours(emo, "sample_term")))`` to read
    whatever per-Emotion sample Term the agent has installed.

    Recursion bound: shares ``env['_holds_depth']`` with Holds (one
    budget for all subgraph re-eval — matches the Rust runner's
    behaviour). Returns 0 when no Node resolves, or when the depth
    guard trips, or when the subgraph fails to parse as a Term."""
    node: Term = None

    def evaluate(self, env, G):
        if self.node is None:
            return 0
        depth = env.get("_holds_depth", 0)
        if depth > 100:
            return 0
        nid = self.node.evaluate(env, G)
        # Resolve into a NodeID; node-typed Values come in two shapes.
        try:
            from substrate import NodeID
        except ImportError:
            NodeID = None
        # Accept raw NodeID, or graph node objects that have an .id.
        if NodeID is not None and isinstance(nid, NodeID):
            target = nid
        elif hasattr(nid, "id"):
            target = nid.id
        elif isinstance(nid, int):
            target = nid
        else:
            return 0
        try:
            sub_term = term_from_subgraph(G, target)
        except (ValueError, KeyError, AttributeError):
            return 0
        new_env = {**env, "_holds_depth": depth + 1}
        # Tolerate evaluator-internal exceptions the same way
        # _update_emotions did (try/except → 0). Per the new ISA's
        # None-propagation table this should be unnecessary once the
        # substrate's comparators / arithmetic handle None gracefully,
        # but until then the legacy DSL eval raises TypeError on
        # mixed-type ops. Tracked as ISA §3 work.
        try:
            result = sub_term.evaluate(new_env, G)
        except Exception:
            return 0
        # Narrow coercion: ONLY transform Bool → 0/1 (matches the
        # old _update_emotions shim for boolean sample_terms) and
        # None → 0 (so arithmetic Terms downstream don't crash on
        # missing attrs). Everything else — int / float / set /
        # frozenset / dict / NodeID / string — passes through raw.
        # The execute rule needs the raw set result from evaluating
        # a Filter subroutine query; the EMA rule needs numeric for
        # arithmetic. One primitive serves both.
        if result is None:
            return 0
        if isinstance(result, bool):
            return 1 if result else 0
        return result


@_register
@dataclass(frozen=True)
class Holds(Term):
    """Does the named concept hold of ``node``? Lets one concept be
    DEFINED in terms of others — composition. At eval it asks the
    resolver in ``env['_resolve_concept']`` (supplied by the agent) for
    the named concept's definition Term and evaluates it with ``node``
    bound (as both ``x`` and ``boundary``). A depth guard in
    ``env['_holds_depth']`` prevents cyclic definitions from looping."""
    concept: str = ""
    node: Term = None
    node2: Term = None       # optional 2nd arg, bound as ``y`` — binary recursion

    def evaluate(self, env, G):
        resolve = env.get("_resolve_concept")
        if resolve is None or self.node is None:
            return False
        depth = env.get("_holds_depth", 0)
        if depth > 100:          # runaway guard — a real recursion bottoms out
            return 0             # at its base case long before this
        term = resolve(self.concept)
        if term is None:
            return False
        n = self.node.evaluate(env, G)
        new_env = {**env, "x": n, "boundary": n, "_holds_depth": depth + 1}
        if self.node2 is not None:        # binary recursion: add / gcd / mod …
            new_env["y"] = self.node2.evaluate(env, G)
        # Return the definition's VALUE, not just a bool — so a concept can
        # recurse a QUANTITY (factorial, gcd), not only a predicate. A concept
        # whose definition references its OWN name is RECURSION; an IfThenElse
        # base case terminates it. This — a self-referential definition on a
        # graph the recursion walks — is how the finite expresses the infinite.
        return term.evaluate(new_env, G)


@_register
@dataclass(frozen=True)
class And(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        return all(t.evaluate(env, G) for t in self.items)


@_register
@dataclass(frozen=True)
class Or(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        return any(t.evaluate(env, G) for t in self.items)


@_register
@dataclass(frozen=True)
class Not(Term):
    arg: Term

    def evaluate(self, env, G):
        return not self.arg.evaluate(env, G)


# --- numeric / weight expressions (Theorem D) ---


@_register
@dataclass(frozen=True)
class Abs(Term):
    arg: Term

    def evaluate(self, env, G):
        return abs(self.arg.evaluate(env, G))


@_register
@dataclass(frozen=True)
class Plus(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        return sum(t.evaluate(env, G) for t in self.items)


@_register
@dataclass(frozen=True)
class Minus(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) - self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Times(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        out = 1
        for t in self.items:
            out *= t.evaluate(env, G)
        return out


@_register
@dataclass(frozen=True)
class Div(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) / self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class IfThenElse(Term):
    cond: Term
    then: Term
    other: Term

    def evaluate(self, env, G):
        return self.then.evaluate(env, G) if self.cond.evaluate(env, G) else self.other.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Sum(Term):
    """Numeric reduce: for each item in ``source``, bind ``var_name``, evaluate
    ``value``, return the sum. Analogous to :class:`Filter` over booleans."""
    source: Term
    var_name: str
    value: Term

    def evaluate(self, env, G):
        items = self.source.evaluate(env, G)
        total = 0
        for it in items:
            total += self.value.evaluate({**env, self.var_name: it}, G)
        return total


@_register
@dataclass(frozen=True)
class Prod(Term):
    """Numeric reduce by multiplication: bind ``var_name`` to each item in
    ``source``, evaluate ``value``, return the product (1 over an empty set).
    The multiplicative twin of :class:`Sum` — e.g. a determinant's per-
    permutation product of matrix entries."""
    source: Term
    var_name: str
    value: Term

    def evaluate(self, env, G):
        total = 1
        for it in self.source.evaluate(env, G):
            total *= self.value.evaluate({**env, self.var_name: it}, G)
        return total


@_register
@dataclass(frozen=True)
class Fold(Term):
    """General accumulate (CODE-2): for each item in ``source``, bind
    ``var_name`` to the item and ``acc_name`` to the running accumulator
    (seeded from ``init``), evaluate ``body``, and carry the result forward
    as the new accumulator. The non-additive generalisation of Sum/Prod --
    an accumulation LOOP (``acc = acc OP expr`` / ``acc OP= expr``) with an
    arbitrary combining ``body``, the native Term the accumulation-idiom
    code construction emits into (domains/ast_to_term.py::emit_accumulation).
    Mirrors the Rust ``TermNode::Fold`` (runners/dsl/src/term.rs) field for
    field so JSON round-trips identically; this dataclass only closes the
    Python-side render/jsonio gap -- the Rust evaluator already had Fold."""
    source: Term
    var_name: str
    acc_name: str
    init: Term
    body: Term

    def evaluate(self, env, G):
        acc = self.init.evaluate(env, G)
        for it in self.source.evaluate(env, G):
            acc = self.body.evaluate({**env, self.var_name: it, self.acc_name: acc}, G)
        return acc


@_register
@dataclass(frozen=True)
class MinOver(Term):
    """Numeric reduce to the MINIMUM of ``value`` over ``source`` (binding
    ``var_name`` per item). The set-valued analogue of :class:`Min` (which
    takes fixed items) — needed to reduce over a dynamic neighbourhood, e.g.
    the nearest surface across a receptive field of receptors. Returns
    ``default`` for an empty source."""
    source: Term
    var_name: str
    value: Term
    default: Term = None

    def evaluate(self, env, G):
        items = self.source.evaluate(env, G)
        best = None
        for it in items:
            v = self.value.evaluate({**env, self.var_name: it}, G)
            if best is None or v < best:
                best = v
        if best is None:
            return self.default.evaluate(env, G) if self.default is not None else 0
        return best


@_register
@dataclass(frozen=True)
class MaxOver(Term):
    """Numeric reduce to the MAXIMUM of ``value`` over ``source`` (binding
    ``var_name`` per item) — the mirror of :class:`MinOver`. Needed for
    largest-of-a-set reductions the agent forms over dynamic sets: the gcd is
    the greatest common divisor among the numbers it knows, the longest reach,
    the heaviest load. Returns ``default`` for an empty source."""
    source: Term
    var_name: str
    value: Term
    default: Term = None

    def evaluate(self, env, G):
        items = self.source.evaluate(env, G)
        best = None
        for it in items:
            v = self.value.evaluate({**env, self.var_name: it}, G)
            if best is None or v > best:
                best = v
        if best is None:
            return self.default.evaluate(env, G) if self.default is not None else 0
        return best


@_register
@dataclass(frozen=True)
class Pick(Term):
    """ONE element of a set-valued ``source`` — "the" successor, "the"
    predecessor: the unique element of a singleton (an arbitrary one if several,
    None if empty). Lets graph navigation produce a single NODE to recurse on,
    so a recursion can step along a relation (succ / pred) one node at a time."""
    source: Term

    def evaluate(self, env, G):
        for it in self.source.evaluate(env, G):
            return it
        return None


@_register
@dataclass(frozen=True)
class Argmax(Term):
    """Return the ELEMENT of ``source`` for which ``value`` (evaluated
    under ``var_name: element``) is maximum — distinct from
    :class:`MaxOver` which returns the maximum value itself. Tiebreaker:
    first encountered in iteration order over ``source``. Returns
    ``default`` (or None) for an empty source. Added Phase 17b.3c.4 —
    the missing primitive for "pick the top-salience event" without a
    recompute-after-max workaround."""
    source: Term
    var_name: str
    value: Term
    default: Term = None

    def evaluate(self, env, G):
        best_v = None
        best_e = None
        for it in self.source.evaluate(env, G):
            v = self.value.evaluate({**env, self.var_name: it}, G)
            if best_v is None or (v is not None and best_v is not None
                                   and v > best_v):
                best_v = v
                best_e = it
        if best_e is None:
            return self.default.evaluate(env, G) if self.default is not None else None
        return best_e


@_register
@dataclass(frozen=True)
class Argmin(Term):
    """Mirror of :class:`Argmax` — returns the element minimising ``value``."""
    source: Term
    var_name: str
    value: Term
    default: Term = None

    def evaluate(self, env, G):
        best_v = None
        best_e = None
        for it in self.source.evaluate(env, G):
            v = self.value.evaluate({**env, self.var_name: it}, G)
            if best_v is None or (v is not None and best_v is not None
                                   and v < best_v):
                best_v = v
                best_e = it
        if best_e is None:
            return self.default.evaluate(env, G) if self.default is not None else None
        return best_e


# --- core math (scalar) ---

@_register
@dataclass(frozen=True)
class Min(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        vals = [t.evaluate(env, G) for t in self.items]
        return min(vals) if vals else 0


@_register
@dataclass(frozen=True)
class Max(Term):
    items: tuple = ()

    def evaluate(self, env, G):
        vals = [t.evaluate(env, G) for t in self.items]
        return max(vals) if vals else 0


@_register
@dataclass(frozen=True)
class Mod(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        b = self.b.evaluate(env, G)
        return self.a.evaluate(env, G) % b if b else 0


@_register
@dataclass(frozen=True)
class Pow(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return self.a.evaluate(env, G) ** self.b.evaluate(env, G)


@_register
@dataclass(frozen=True)
class Sqrt(Term):
    arg: Term

    def evaluate(self, env, G):
        v = self.arg.evaluate(env, G)
        return math.sqrt(v) if v and v >= 0 else 0.0


# Bitwise integer ops on i64. Shift counts outside [0, 63] yield 0
# (or -1 for Ashr on negative `a`) — matches the Mod fallback.

def _as_i64(x) -> int:
    return int(x) & ((1 << 64) - 1) if isinstance(x, int) and x < 0 else int(x or 0)


@_register
@dataclass(frozen=True)
class BitAnd(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return int(self.a.evaluate(env, G) or 0) & int(self.b.evaluate(env, G) or 0)


@_register
@dataclass(frozen=True)
class BitOr(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return int(self.a.evaluate(env, G) or 0) | int(self.b.evaluate(env, G) or 0)


@_register
@dataclass(frozen=True)
class BitXor(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        return int(self.a.evaluate(env, G) or 0) ^ int(self.b.evaluate(env, G) or 0)


@_register
@dataclass(frozen=True)
class Shl(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        av = int(self.a.evaluate(env, G) or 0)
        bv = int(self.b.evaluate(env, G) or 0)
        if not (0 <= bv < 64):
            return 0
        mask = (1 << 64) - 1
        out = (av << bv) & mask
        return out - (1 << 64) if out & (1 << 63) else out


@_register
@dataclass(frozen=True)
class Lshr(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        av = int(self.a.evaluate(env, G) or 0)
        bv = int(self.b.evaluate(env, G) or 0)
        if not (0 <= bv < 64):
            return 0
        au = av & ((1 << 64) - 1)
        return au >> bv


@_register
@dataclass(frozen=True)
class Ashr(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        av = int(self.a.evaluate(env, G) or 0)
        bv = int(self.b.evaluate(env, G) or 0)
        if not (0 <= bv < 64):
            return 0 if av >= 0 else -1
        return av >> bv  # Python `>>` is arithmetic on signed ints


@_register
@dataclass(frozen=True)
class IDiv(Term):
    """Integer truncating division (signed). C-style: trunc toward zero.
    Divide by zero returns 0 (substrate's silent-zero convention)."""
    a: Term
    b: Term

    def evaluate(self, env, G):
        av = int(self.a.evaluate(env, G) or 0)
        bv = int(self.b.evaluate(env, G) or 0)
        if bv == 0:
            return 0
        # Python's `//` floors; we want truncation toward zero.
        return int(av / bv) if (av >= 0) == (bv >= 0) or av % bv == 0 \
               else int(av / bv)  # int(float) truncates toward zero


@_register
@dataclass(frozen=True)
class IRem(Term):
    """Integer remainder (signed). Matches Rust's `%` and LLVM's srem.
    Remainder of zero divisor returns 0."""
    a: Term
    b: Term

    def evaluate(self, env, G):
        av = int(self.a.evaluate(env, G) or 0)
        bv = int(self.b.evaluate(env, G) or 0)
        if bv == 0:
            return 0
        # Python `%` follows sign of divisor; LLVM srem follows sign of
        # dividend (matches Rust `%`). a - trunc(a/b)*b gives the right thing.
        quot = int(av / bv) if (av >= 0) == (bv >= 0) or av % bv == 0 \
               else int(av / bv)
        return av - quot * bv


@_register
@dataclass(frozen=True)
class Neg(Term):
    arg: Term

    def evaluate(self, env, G):
        return -self.arg.evaluate(env, G)


# --- core geometry (N-dimensional vectors as tuples) ---
# Vectors are tuples of scalars. ``Vec`` builds one from scalar Terms
# (e.g. a cell's coordinates); the rest operate on vector-valued Terms
# (including a node's ``vector`` attr read via ``Attr``). Distance =
# Magnitude(VecSub(a, b)); these ground the agent's space metrically.

@_register
@dataclass(frozen=True)
class Vec(Term):
    """Construct a vector from scalar child Terms — e.g. a cell's
    position Vec(Attr(c,'x_bin'), Attr(c,'y_bin'), Attr(c,'z_bin'))."""
    items: tuple = ()

    def evaluate(self, env, G):
        return tuple(t.evaluate(env, G) for t in self.items)


@_register
@dataclass(frozen=True)
class VecAdd(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        a = self.a.evaluate(env, G)
        b = self.b.evaluate(env, G)
        return tuple(x + y for x, y in zip(a, b))


@_register
@dataclass(frozen=True)
class VecSub(Term):
    a: Term
    b: Term

    def evaluate(self, env, G):
        a = self.a.evaluate(env, G)
        b = self.b.evaluate(env, G)
        return tuple(x - y for x, y in zip(a, b))


@_register
@dataclass(frozen=True)
class Dot(Term):
    """Dot product of two vectors — Σ aᵢbᵢ. Zero ⇒ perpendicular;
    sign/size ⇒ alignment. The metric heart of geometry."""
    a: Term
    b: Term

    def evaluate(self, env, G):
        a = self.a.evaluate(env, G)
        b = self.b.evaluate(env, G)
        return sum(x * y for x, y in zip(a, b))


@_register
@dataclass(frozen=True)
class Magnitude(Term):
    """Euclidean length of a vector — √(Σ aᵢ²). With VecSub gives
    distance between two points."""
    arg: Term

    def evaluate(self, env, G):
        v = self.arg.evaluate(env, G)
        return math.sqrt(sum(x * x for x in v))


# --- Rotation / angle primitives ---
# Fundamental geometry: heading, bearing, rotating a vector, the signed
# angle between two. Needed wherever a process reasons about direction as
# a continuous quantity (motor heading control, periodic phase, orientation
# of any kind) rather than forcing it into discrete cardinal buckets.

@_register
@dataclass(frozen=True)
class Sin(Term):
    """sin(arg), arg in radians."""
    arg: Term

    def evaluate(self, env, G):
        return math.sin(self.arg.evaluate(env, G))


@_register
@dataclass(frozen=True)
class Cos(Term):
    """cos(arg), arg in radians."""
    arg: Term

    def evaluate(self, env, G):
        return math.cos(self.arg.evaluate(env, G))


@_register
@dataclass(frozen=True)
class Atan2(Term):
    """atan2(y, x) — the angle (radians, −π..π) of the vector pointing
    from the origin to (x, y). The bearing of a heading/displacement."""
    y: Term
    x: Term

    def evaluate(self, env, G):
        return math.atan2(self.y.evaluate(env, G), self.x.evaluate(env, G))


@_register
@dataclass(frozen=True)
class Bearing(Term):
    """The angle (radians) of a 2-D vector — atan2(v[1], v[0]). The heading
    a displacement/velocity vector points along."""
    arg: Term

    def evaluate(self, env, G):
        v = self.arg.evaluate(env, G)
        return math.atan2(v[1], v[0])


@_register
@dataclass(frozen=True)
class Rotate(Term):
    """Rotate a 2-D vector by ``angle`` radians (counter-clockwise),
    returning the rotated vector. Lets a process PREDICT how a rotation
    changes a heading — e.g. a turn's effect on the body's facing."""
    vec: Term
    angle: Term

    def evaluate(self, env, G):
        v = self.vec.evaluate(env, G)
        th = self.angle.evaluate(env, G)
        c, s = math.cos(th), math.sin(th)
        x, y = v[0], v[1]
        return (x * c - y * s, x * s + y * c)


@_register
@dataclass(frozen=True)
class AngleBetween(Term):
    """Signed angle (radians, −π..π) FROM vector ``a`` TO vector ``b`` —
    atan2(cross, dot). Positive = b is counter-clockwise from a. The error
    a feedback controller drives to zero (how far, and which way, to turn)."""
    a: Term
    b: Term

    def evaluate(self, env, G):
        a = self.a.evaluate(env, G)
        b = self.b.evaluate(env, G)
        cross = a[0] * b[1] - a[1] * b[0]
        dot = a[0] * b[0] + a[1] * b[1]
        return math.atan2(cross, dot)


# --- Rendering: per-language Term-to-surface transforms ------------------
# A Renderer is a graph-resident transform: source Term → target-language
# Surface (text or bytes). The substrate proposed these heads (Phase 6.1)
# as the algebra rules are written in. Templates use Surface/Cat/Slot/Render
# to recursively assemble target syntax from a matched source Term's slots.

@_register
@dataclass(frozen=True)
class Surface(Term):
    """A LITERAL piece of target-language surface — a text fragment or a
    byte sequence. Leaf of a rendering template. ``kind`` is "text" or
    "bytes"; ``payload`` is the str / bytes literal."""
    kind: str = "text"
    payload: Any = ""

    def evaluate(self, env, G):
        return {"kind": self.kind, "payload": self.payload}


@_register
@dataclass(frozen=True)
class Cat(Term):
    """CONCATENATE Surfaces in order. Each ``items`` element evaluates to a
    Surface (or a value coerced to a text Surface). All items must share the
    same kind; mixing text and bytes is a render-time error caught here."""
    items: tuple = ()

    def evaluate(self, env, G):
        kind = None
        out_text = ""
        out_bytes = b""
        # Evaluate items LAZILY in order; SHORT-CIRCUIT on the first None so
        # we don't spawn parallel render-gap impasses for every sub-Term.
        # That lets the agent's impasse resolver take one rule at a time.
        for t in self.items:
            p = t.evaluate(env, G)
            if p is None:
                return None
            if isinstance(p, dict) and "kind" in p:
                k, payload = p["kind"], p["payload"]
            elif isinstance(p, (bytes, bytearray)):
                k, payload = "bytes", bytes(p)
            else:
                k, payload = "text", str(p)
            if kind is None:
                kind = k
            elif k != kind:
                raise ValueError(
                    f"Cat: cannot mix {kind!r} and {k!r} in same surface")
            if kind == "text":
                out_text += payload
            else:
                out_bytes += payload
        return {"kind": kind or "text",
                "payload": out_text if (kind or "text") == "text" else out_bytes}


@_register
@dataclass(frozen=True)
class Slot(Term):
    """Read a SLOT from the render context — the matched source Term's
    child bound under ``name``. Evaluation returns whatever the engine
    stored under that slot (usually a Term, sometimes a primitive)."""
    name: str = ""

    def evaluate(self, env, G):
        slots = env.get("__slots__")
        if slots is None:
            return None
        return slots.get(self.name)


@_register
@dataclass(frozen=True)
class Join(Term):
    """RENDER each item of an iterable + JOIN with a separator. ``items``
    evaluates to a tuple/list (typically a variadic source Term's
    ``items`` slot — Plus, Times, And, Or, …). Each member is rendered
    recursively via ``env["__render__"]`` and joined with ``separator``'s
    payload. Same kind-checking as Cat: all rendered items must share
    surface kind."""
    separator: Term = None
    items: Term = None

    def evaluate(self, env, G):
        if self.items is None or self.separator is None:
            return None
        seq = self.items.evaluate(env, G)
        sep = self.separator.evaluate(env, G)
        if isinstance(sep, dict):
            sep_kind, sep_payload = sep["kind"], sep["payload"]
        else:
            sep_kind, sep_payload = "text", str(sep)
        renderer = env.get("__render__")
        kind = None
        parts = []
        for item in (seq or ()):
            if isinstance(item, Term) and renderer is not None:
                rendered = renderer(item, env.get("__lang__"))
                # render-gap propagation: same as Cat — the whole Join
                # is a gap if any item couldn't be rendered
                if rendered is None:
                    return None
                if kind is None:
                    kind = rendered["kind"]
                elif rendered["kind"] != kind:
                    raise ValueError(
                        f"Join: cannot mix {kind!r} and {rendered['kind']!r}")
                parts.append(rendered["payload"])
            else:
                if kind is None:
                    kind = "text"
                parts.append(str(item) if item is not None else "")
        if kind is None:
            kind = sep_kind
        if kind == "text":
            return {"kind": "text", "payload": sep_payload.join(parts)}
        sep_b = sep_payload if isinstance(sep_payload, (bytes, bytearray)) \
            else str(sep_payload).encode()
        out = b""
        for i, p in enumerate(parts):
            if i > 0:
                out += sep_b
            out += p if isinstance(p, (bytes, bytearray)) else str(p).encode()
        return {"kind": "bytes", "payload": out}


@_register
@dataclass(frozen=True)
class Bytes(Term):
    """BYTE-typed concatenation — rejects text Surfaces (use Cat for text).
    The natural target for binary encoders: ELF headers, x86_64 machine
    code, WASM, DWARF. Same None-propagation as Cat."""
    items: tuple = ()

    def evaluate(self, env, G):
        out = b""
        for t in self.items:
            r = t.evaluate(env, G)
            if r is None:
                return None
            if isinstance(r, (bytes, bytearray)):
                out += bytes(r)
                continue
            if isinstance(r, dict):
                if r.get("kind") != "bytes":
                    raise ValueError(
                        f"Bytes: cannot include text Surface "
                        f"(use Cat for text concatenation)")
                out += r["payload"]
                continue
            raise ValueError(
                f"Bytes: cannot concatenate {type(r).__name__}")
        return {"kind": "bytes", "payload": out}


@_register
@dataclass(frozen=True)
class U8(Term):
    """Integer → one byte. Encodes the low 8 bits of the expr's value."""
    expr: "Term | None" = None

    def evaluate(self, env, G):
        if self.expr is None:
            return None
        v = self.expr.evaluate(env, G)
        if v is None:
            return None
        if isinstance(v, dict):
            v = v["payload"]
        return {"kind": "bytes", "payload": bytes([int(v) & 0xFF])}


@_register
@dataclass(frozen=True)
class U16LE(Term):
    """Integer → 2 bytes little-endian."""
    expr: "Term | None" = None

    def evaluate(self, env, G):
        if self.expr is None:
            return None
        v = self.expr.evaluate(env, G)
        if v is None:
            return None
        if isinstance(v, dict):
            v = v["payload"]
        return {"kind": "bytes",
                "payload": (int(v) & 0xFFFF).to_bytes(2, "little")}


@_register
@dataclass(frozen=True)
class U32LE(Term):
    """Integer → 4 bytes little-endian."""
    expr: "Term | None" = None

    def evaluate(self, env, G):
        if self.expr is None:
            return None
        v = self.expr.evaluate(env, G)
        if v is None:
            return None
        if isinstance(v, dict):
            v = v["payload"]
        return {"kind": "bytes",
                "payload": (int(v) & 0xFFFFFFFF).to_bytes(4, "little")}


@_register
@dataclass(frozen=True)
class U64LE(Term):
    """Integer → 8 bytes little-endian."""
    expr: "Term | None" = None

    def evaluate(self, env, G):
        if self.expr is None:
            return None
        v = self.expr.evaluate(env, G)
        if v is None:
            return None
        if isinstance(v, dict):
            v = v["payload"]
        return {"kind": "bytes",
                "payload": (int(v) & ((1 << 64) - 1)).to_bytes(8, "little")}


@_register
@dataclass(frozen=True)
class LEB128(Term):
    """Unsigned LEB128 (variable-length integer encoding — DWARF + WASM)."""
    expr: "Term | None" = None

    def evaluate(self, env, G):
        if self.expr is None:
            return None
        v = self.expr.evaluate(env, G)
        if v is None:
            return None
        if isinstance(v, dict):
            v = v["payload"]
        n = int(v)
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        return {"kind": "bytes", "payload": bytes(out)}


@_register
@dataclass(frozen=True)
class Lines(Term):
    """STATEMENT-LEVEL concatenation: render each item, join with newline.
    For multi-instruction emissions (assembly, multi-line source). Same
    None-propagation as Cat — any None subitem makes the whole Lines a
    render gap."""
    items: tuple = ()

    def evaluate(self, env, G):
        out_parts = []
        for t in self.items:
            r = t.evaluate(env, G)
            if r is None:
                return None
            if isinstance(r, dict) and "kind" in r:
                out_parts.append(str(r["payload"]))
            else:
                out_parts.append(str(r))
        return {"kind": "text", "payload": "\n".join(out_parts)}


@_register
@dataclass(frozen=True)
class Label(Term):
    """Generate a fresh assembly label string ``.L<prefix><N>`` where N is
    the per-render counter held in ``env["__label_counter__"]`` (a mutable
    one-element list so Let-bound copies of env share the same counter).
    Same label generator the substrate's static x86_64 renderer used."""
    prefix: str = ""

    def evaluate(self, env, G):
        ctr = env.get("__label_counter__")
        if ctr is None:
            ctr = [0]
            env["__label_counter__"] = ctr
        ctr[0] += 1
        return f".L{self.prefix}{ctr[0]}"


@_register
@dataclass(frozen=True)
class Let(Term):
    """Bind ``name`` to the evaluation of ``value`` and evaluate ``body``
    in a scope that sees the binding. The render-context analogue: when a
    template needs to refer to a single fresh label in MULTIPLE places
    (e.g. emit its colon-form once + jump to it twice), bind it once."""
    name: str = ""
    value: "Term | None" = None
    body: "Term | None" = None

    def evaluate(self, env, G):
        if self.value is None or self.body is None:
            return None
        v = self.value.evaluate(env, G)
        new_env = dict(env)
        new_env[self.name] = v
        return self.body.evaluate(new_env, G)


@_register
@dataclass(frozen=True)
class Nth(Term):
    """Index into a sequence slot — ``Nth(Slot("items"), 0)`` reads the
    first child of a variadic source Term. Used by ASM rules that need
    per-item placement (push between, popq+op after) rather than the
    pure separator-join Cat/Join give for text languages."""
    items: "Term | None" = None
    index: int = 0

    def evaluate(self, env, G):
        if self.items is None:
            return None
        seq = self.items.evaluate(env, G)
        try:
            return seq[self.index]
        except (TypeError, IndexError):
            return None


@_register
@dataclass(frozen=True)
class Render(Term):
    """RECURSIVELY render a sub-Term in the current language. ``term``
    evaluates to a source Term; the engine (provided via env["__render__"])
    looks up the matching RenderRule for it and emits a Surface. ``lang``
    is optional — defaults to the current ``env["__lang__"]`` so a template
    that recursively renders its slots doesn't have to thread the language."""
    term: Term = None
    lang: "Term | None" = None

    def evaluate(self, env, G):
        renderer = env.get("__render__")
        if renderer is None or self.term is None:
            return None
        source = self.term.evaluate(env, G)
        if self.lang is not None:
            lang_id = self.lang.evaluate(env, G)
        else:
            lang_id = env.get("__lang__")
        return renderer(source, lang_id)


@_register
@dataclass(frozen=True)
class LitRepr(Term):
    """CODE-3 (writing is reading reversed): a FAITHFUL Python literal
    representation of a scalar ``value`` Term — the type-aware quoting a
    bare ``Slot`` binding can't do (``str()`` leaves a string unquoted, a
    bool/None loses its Python spelling entirely). A RenderRule template
    composes ``LitRepr(value=Slot(name="value"))`` in place of the bare
    Slot for the ``Lit`` head. Mirrors the Rust ``TermNode::LitRepr``
    evaluator (``python_repr``, runners/dsl/src/term.rs) exactly — this
    Python arm exists for the pure-Python DSL fallback path (never the
    live agent, which always renders via the Rust engine); None/Bool/Int/
    Float/Str only, any other value is an honest render gap (``None``)."""
    value: Term = None

    def evaluate(self, env, G):
        v = self.value.evaluate(env, G) if self.value is not None else None
        if isinstance(v, bool):
            return "True" if v else "False"
        if v is None:
            return "None"
        if isinstance(v, str):
            quote = '"' if ("'" in v and '"' not in v) else "'"
            out = [quote]
            for ch in v:
                if ch == "\\":
                    out.append("\\\\")
                elif ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                elif ch == quote:
                    out.append("\\" + ch)
                else:
                    out.append(ch)
            out.append(quote)
            return "".join(out)
        if isinstance(v, float):
            if v != v:
                return "float('nan')"
            if v in (float("inf"), float("-inf")):
                return "float('inf')" if v > 0 else "float('-inf')"
            return repr(v)
        if isinstance(v, int):
            return str(v)
        return None


# --- Program IR (P1, PROGRAM_SYNTHESIS_PLAN.md §3.2) -----------------------
#
# Python MIRRORS of the Rust statement/expression IR variants
# (runners/dsl/src/term.rs, same section header). These exist so seed
# builders / world adapters can COMPOSE Program-IR Term-JSON with the
# same dataclass ergonomics as every other Term — field names and order
# match the Rust wire dialect exactly. They are DATA: the Python
# ``evaluate`` mirrors the Rust main-evaluator contract (structural
# variants are INERT → None). Execution semantics live ONLY in the Rust
# ``ProgEval`` interpreter (runners/dsl/src/prog_eval.rs); the Python
# ProgEval mirror refuses rather than fork the semantics.


class _ProgStructural(Term):
    """Base for Program-IR structural variants: inert under evaluate()."""

    def evaluate(self, env, G):  # noqa: ARG002 — mirrors the Rust inert contract
        return None


@_register
@dataclass(frozen=True)
class ProgSeq(_ProgStructural):
    stmts: tuple = ()


@_register
@dataclass(frozen=True)
class ProgAssignVar(_ProgStructural):
    name: str
    value: Term


@_register
@dataclass(frozen=True)
class ProgAugAssign(_ProgStructural):
    """``name OP= value``; op is the lowercased Python ast op name
    (add/sub/mult/div/floordiv/mod/pow/lshift/rshift/bitand/bitor/bitxor)."""
    name: str
    op: str
    value: Term


@_register
@dataclass(frozen=True)
class ProgTupleUnpack(_ProgStructural):
    """Flat ``a, b = value`` unpack; targets is a tuple of names."""
    targets: tuple
    value: Term


@_register
@dataclass(frozen=True)
class ProgIfStmt(_ProgStructural):
    cond: Term
    then: Term
    orelse: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgForEach(_ProgStructural):
    var: str
    iter: Term
    body: Term
    orelse: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgWhile(_ProgStructural):
    cond: Term
    body: Term
    orelse: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgLoopCtl(_ProgStructural):
    kind: str  # "break" | "continue"


@_register
@dataclass(frozen=True)
class ProgReturn(_ProgStructural):
    value: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgTryOr(_ProgStructural):
    """try/except: catches ProgEval TRAPS (never fuel). exc_var ""
    means unnamed; handler None means catch-and-continue."""
    body: Term
    exc_var: str = ""
    handler: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgRaise(_ProgStructural):
    exc: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgImportStmt(_ProgStructural):
    """Extern surface only — a ProgEval no-op; uses trap at use sites."""
    module: str
    alias: str = ""
    names: tuple = ()


@_register
@dataclass(frozen=True)
class ProgSubscriptSet(_ProgStructural):
    obj: Term
    index: Term
    value: Term


@_register
@dataclass(frozen=True)
class ProgAttrSet(_ProgStructural):
    obj: Term
    attr: str
    value: Term


@_register
@dataclass(frozen=True)
class ProgDefFnParam(_ProgStructural):
    """One def parameter: binds from env if present, else default,
    else traps param:<name>."""
    name: str
    default: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgCallExtern(_ProgStructural):
    """Extern call — ProgEval evaluates ONLY against declared oracles;
    undeclared traps extern:<name>. Native set: len/abs/min/max/range/
    sum/str/int/float/bool/sorted."""
    name: str
    recv: "Term | None" = None
    args: tuple = ()


@_register
@dataclass(frozen=True)
class ProgAttrGet(_ProgStructural):
    """Record-field read on a program VALUE (records are dicts) —
    distinct from Attr, which reads a GRAPH NODE's attr."""
    obj: Term
    attr: str


@_register
@dataclass(frozen=True)
class ProgSubscript(_ProgStructural):
    """Python subscript semantics (negative index, dict key, honest
    trap on miss) — distinct from IndexAt (DSL list primitive)."""
    obj: Term
    index: Term


@_register
@dataclass(frozen=True)
class ProgSlice(_ProgStructural):
    """Python slice read: obj[start:stop:step] (Q1 `slicing`) — Tuple or
    Str/Surface(Text) only; step==0 traps; never OOB (Python slicing
    clamps). Rust-only semantics (prog_eval.rs); this mirror is inert."""
    obj: Term
    start: "Term | None" = None
    stop: "Term | None" = None
    step: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgContainerLit(_ProgStructural):
    """Display literal; kind ∈ list/tuple/set/dict (dict items
    alternate key,value — the MkDict convention)."""
    kind: str
    items: tuple = ()


@_register
@dataclass(frozen=True)
class ProgComprehensionList(_ProgStructural):
    var: str
    source: Term
    expr: Term
    cond: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgComprehensionGen(_ProgStructural):
    var: str
    source: Term
    expr: Term
    cond: "Term | None" = None


@_register
@dataclass(frozen=True)
class ProgIsOp(_ProgStructural):
    """``a is b`` / ``a is not b`` — None/Node identity only; anything
    else traps rather than approximating identity with Eq."""
    a: Term
    b: Term
    negated: bool = False


@_register
@dataclass(frozen=True)
class ProgFString(_ProgStructural):
    parts: tuple = ()


@_register
@dataclass(frozen=True)
class ProgEval(Term):
    """The fueled Program-IR interpreter. Rust-only engine
    (runners/dsl/src/prog_eval.rs) — evaluate via the Rust substrate
    (``native.evaluate``); this mirror exists for composition only and
    REFUSES to run rather than fork the semantics."""
    prog: Term
    env: "Term | None" = None
    oracles: "Term | None" = None
    fuel: int = 0
    field: str = ""

    def evaluate(self, env, G):
        raise NotImplementedError(
            "ProgEval executes only on the Rust substrate (prog_eval.rs)")


@_register
@dataclass(frozen=True)
class SnakeCase(Term):
    """snake_case an identifier-ish string (naming primitive; the Rust
    twin returns Surface(Text) — plan §6.3 fallback path)."""
    text: Term

    def evaluate(self, env, G):
        s = self.text.evaluate(env, G)
        if not isinstance(s, str):
            return None
        out: list[str] = []
        prev_lower_or_digit = False
        pending_sep = False
        for ch in s:
            if ch.isalnum():
                if ch.isupper():
                    if prev_lower_or_digit and out:
                        pending_sep = True
                    if pending_sep and out:
                        out.append("_")
                    pending_sep = False
                    out.append(ch.lower())
                    prev_lower_or_digit = False
                else:
                    if pending_sep and out:
                        out.append("_")
                    pending_sep = False
                    out.append(ch)
                    prev_lower_or_digit = True
            else:
                if out:
                    pending_sep = True
                prev_lower_or_digit = False
        return "".join(out)


@_register
@dataclass(frozen=True)
class CaseFold(Term):
    """Lowercase fold (naming primitive)."""
    text: Term

    def evaluate(self, env, G):
        s = self.text.evaluate(env, G)
        return s.lower() if isinstance(s, str) else None


@_register
@dataclass(frozen=True)
class SynthEnumerate(Term):
    """The bottom-up enumerative synthesizer (the Rust port of
    domains/generator.py::synthesize, unguided path — size/MDL-ordered,
    observational-equivalence pruned, saturation-halted, COUNT-budgeted:
    ``max_candidates`` replaces ``timeout_s``). Q1 widened the value
    domain past int/float (str/bool/none/dict/tuple/set spec outputs
    now representable) and added ``exclude``: a list of Term-JSON
    strings for candidates already refuted by the caller, so
    equivalence pruning never re-proposes them (the P7-B repair lever).
    Rust-only engine (runners/dsl/src/synth_enumerate.rs) — evaluate
    via the Rust substrate (``native.evaluate``); this mirror exists
    for composition only and REFUSES to run rather than fork the
    semantics."""
    examples: Term
    ops: "Term | None" = None
    consts: "Term | None" = None
    exclude: "Term | None" = None
    max_size: int = 0
    max_candidates: int = 0
    saturate_k: int = 0
    field: str = ""

    def evaluate(self, env, G):
        raise NotImplementedError(
            "SynthEnumerate executes only on the Rust substrate "
            "(synth_enumerate.rs)")


# --- Reflection: Term ↔ G-subgraph (Axiom 3) ---

_TERM_NODE_PREFIX = "Term."


def _is_term_field(value: Any) -> bool:
    return isinstance(value, Term)


def _is_term_sequence(value: Any) -> bool:
    return isinstance(value, (tuple, list)) and len(value) > 0 and all(isinstance(x, Term) for x in value)


def term_to_subgraph(term: Term, G) -> "NodeID":  # noqa: F821
    """Insert ``term`` and its subterms into G; return the root NodeID."""
    attrs: dict[str, Any] = {}
    children: list[tuple[str, int | None, Any]] = []
    for f in dataclasses.fields(term):
        v = getattr(term, f.name)
        if _is_term_field(v):
            children.append((f.name, None, term_to_subgraph(v, G)))
        elif _is_term_sequence(v):
            for i, child in enumerate(v):
                children.append((f.name, i, term_to_subgraph(child, G)))
        else:
            attrs[f.name] = v
    node_id = G._insert_node(_TERM_NODE_PREFIX + type(term).__name__, attrs)
    for field_name, index, child_id in children:
        edge_attrs = {"index": index} if index is not None else {}
        G._insert_edge(node_id, "child." + field_name, child_id, edge_attrs)
    return node_id


@functools.lru_cache(maxsize=None)
def collect_vars(term: Term) -> frozenset[str]:
    """Return the set of Var names referenced anywhere in ``term`` (ignores binding).

    Used by ``Substrate.is_edge_admissible`` to skip scratch-node materialization
    when no production's where-clause actually references the tgt binding.
    """
    if isinstance(term, Var):
        return frozenset({term.name})
    out: set[str] = set()
    for f in dataclasses.fields(term):
        v = getattr(term, f.name)
        if isinstance(v, Term):
            out |= collect_vars(v)
        elif isinstance(v, (tuple, list)) and v and isinstance(v[0], Term):
            for x in v:
                out |= collect_vars(x)
    return frozenset(out)


@functools.lru_cache(maxsize=None)
def free_vars(term: Term) -> frozenset[str]:
    """Free Var names — i.e., references not shadowed by an enclosing binder.

    Currently ``Filter`` is the only binder; ``var_name`` is removed from the
    predicate's free set. Used by Filter's step-local memoization to key by
    just the externally-bound variables.
    """
    if isinstance(term, Var):
        return frozenset({term.name})
    if isinstance(term, (Filter, Exists)):
        return free_vars(term.source) | (free_vars(term.predicate) - {term.var_name})
    out: set[str] = set()
    for f in dataclasses.fields(term):
        v = getattr(term, f.name)
        if isinstance(v, Term):
            out |= free_vars(v)
        elif isinstance(v, (tuple, list)) and v and isinstance(v[0], Term):
            for x in v:
                out |= free_vars(x)
    return frozenset(out)


def term_from_subgraph(G, node_id) -> Term:
    node = G.node(node_id)
    if not node.type.startswith(_TERM_NODE_PREFIX):
        raise ValueError(f"Not a Term node: {node.type}")
    cls_name = node.type[len(_TERM_NODE_PREFIX):]
    cls = _TERM_REGISTRY[cls_name]
    kwargs: dict[str, Any] = dict(node.attrs)
    groups: dict[str, list[tuple[int | None, Term]]] = {}
    for edge in G.out_edges(node_id):
        if not edge.key.edge_type.startswith("child."):
            continue
        field_name = edge.key.edge_type[len("child."):]
        idx = edge.attrs.get("index")
        child_term = term_from_subgraph(G, edge.key.tgt)
        groups.setdefault(field_name, []).append((idx, child_term))
    for field_name, items in groups.items():
        if all(i is None for i, _ in items):
            assert len(items) == 1, f"Expected single child for {field_name}, got {len(items)}"
            kwargs[field_name] = items[0][1]
        else:
            items.sort(key=lambda x: x[0])
            kwargs[field_name] = tuple(t for _, t in items)
    expected = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in kwargs.items() if k in expected}
    return cls(**kwargs)
