"""Theorem D weighted-traversal sampler over G.

Weights live in a separate map (not attrs) so that the same G can carry
multiple weight functions simultaneously (e.g., for ensemble sampling).
Transitions are restricted to Γ-admissible outgoing edges via C.

GAMMA_SEARCH_COMPLETENESS_CEILING.md Bug 1 (see
docs/research/engine_substrate/GAMMA_SEARCH_COMPLETENESS_FIXES.md for the
fix writeup): Gamma's ``weight`` field is a LOG-domain quantity — selection
is ``proportional to exp(w)`` (grammar.rs header; ``checker.rs``'s
``evaluate_weight``/``admissible_moves`` sum raw, un-normalized ``w``
additively across co-admitting productions for ONE choice point, never
normalizing). ``domains/fovea_bridge.py``'s ``fovea_resolve`` composes
exactly this way for a single decision (``ArgminUnique`` over
``Neg(Log(salience)+goal_logweight)`` — an additive sum of raw log
quantities). The valid way to compose a raw Gamma-shaped weight across
MULTIPLE hops is the same standard log/tropical-semiring identity
(Carre 1971; Mohri 2002): sum the RAW per-hop log-weights, never chain
locally-renormalized per-step probabilities and multiply those (that is
the CRF "label bias" problem — Lafferty, McCallum & Pereira 2001 — a
per-step categorical draw is forced to sum to 1 at every hop regardless of
branching factor, so a path through a high-branching node looks
"cheaper"/more probable than an equal-raw-weight path through a
low-branching node purely as an artefact of local normalization, not of
the raw weights actually taken).

The per-step ``rng.choices(...)`` draw below is NOT itself the bug — a
stochastic random-walk sampler genuinely needs a valid local distribution
to draw from at each fork, and per-step-proportional sampling is exactly
correct for that job (this file's actual purpose: an honest
coverage/visitation sampler, not a best-path search). The bug was that
this was the ONLY precedent anywhere in the repo for "composing Gamma
weight across hops", and copying its shape for a best-path/comparable-
path-score purpose would silently reproduce label bias. The fix: track a
SEPARATE, correctly-composed quantity alongside the (unchanged) stochastic
walk — ``WalkResult.path_logweights``, one entry per walk, the RAW
un-normalized log-weight sum of the hops actually taken
(``sum(log(w_i))`` over the realised path, exactly the Carre/Mohri
composition) — so a caller wanting a path score comparable across walks of
different branching factor has a correct quantity to read, instead of
being tempted to reconstruct one from the local per-step probabilities.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .graph import EdgeKey, NodeID
from .primitives import Substrate


WeightFn = Callable[[Substrate, NodeID, EdgeKey], float]
"""Non-negative scalar weight for traversing ``edge`` from ``src``.

This is the LINEAR (exp-domain) weight — what ``rng.choices`` needs for a
categorical draw, and what Gamma's raw log-weight ``w`` exponentiates to
(``uniform_weight``'s constant ``1.0`` is ``exp(0)``, a flat log-weight of
0). ``path_logweights`` below takes ``log`` of this value per hop to
recover the raw, additively-composable Gamma log-weight.
"""


def uniform_weight(s: Substrate, src: NodeID, edge: EdgeKey) -> float:
    return 1.0


@dataclass
class WalkResult:
    visits: dict[NodeID, int] = field(default_factory=dict)
    terminated_at: list[NodeID] = field(default_factory=list)
    path_logweights: list[float] = field(default_factory=list)
    """One entry per walk: ``sum(log(w_i))`` over the RAW (un-normalized)
    ``weight_fn`` values of the hops actually taken on that walk — the
    Carre/Mohri semiring-valid multi-hop composition (module docstring,
    Bug 1). Independent of branching factor at any node visited: unlike a
    product of locally-renormalized step probabilities, this quantity only
    depends on the weights of the edges actually traversed, not on how
    many sibling edges existed at each fork. NOT used to choose the walk's
    steps (that remains the unchanged, correctly-local-for-sampling
    ``rng.choices`` draw below) — this is a read-only score recorded
    alongside it.
    """


def weighted_walk(
    substrate: Substrate,
    start: NodeID,
    n_walks: int,
    walk_length: int,
    weight_fn: WeightFn = uniform_weight,
    edge_types: Iterable[str] | None = None,
    seed: int | None = None,
) -> WalkResult:
    """Run ``n_walks`` weighted random walks from ``start``.

    Only existing edges (already admitted by C at insertion) are followed —
    no admissibility check needed at traversal time. ``edge_types`` restricts
    which outgoing edge-types are eligible.
    """
    rng = random.Random(seed)
    visits: dict[NodeID, int] = {}
    terminated: list[NodeID] = []
    path_logweights: list[float] = []
    edge_types_set = set(edge_types) if edge_types is not None else None

    for _ in range(n_walks):
        cur = start
        logweight = 0.0
        for _ in range(walk_length):
            candidates: list[tuple[EdgeKey, float]] = []
            for edge in substrate.out_edges(cur):
                if edge_types_set is not None and edge.key.edge_type not in edge_types_set:
                    continue
                w = weight_fn(substrate, cur, edge.key)
                if w > 0:
                    candidates.append((edge.key, w))
            if not candidates:
                terminated.append(cur)
                break
            # The categorical draw is LOCALLY normalized by rng.choices — that
            # normalization is required for sampling, and is NOT what gets
            # composed across hops (see module docstring). We recover the
            # RAW weight of the hop actually chosen by index, not by
            # re-deriving it from the (normalized) draw.
            idx = rng.choices(range(len(candidates)), weights=[w for _, w in candidates], k=1)[0]
            chosen_key, chosen_w = candidates[idx]
            logweight += math.log(chosen_w)
            cur = chosen_key.tgt
            visits[cur] = visits.get(cur, 0) + 1
        path_logweights.append(logweight)
    return WalkResult(visits=visits, terminated_at=terminated, path_logweights=path_logweights)
