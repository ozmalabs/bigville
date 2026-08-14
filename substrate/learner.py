"""Γ-edit learner — Theorem C (reflective Γ-extension) at toy scale.

Observation domain (Life-like CAs):
    (src_type: str, alive_n: int, next_type: str)

The learner watches transitions, maintains per-(src_type, n) frequency counts
of observed next-types, and rebuilds Γ whenever the table changes. Each
disagreement between the current Γ's prediction and the observation triggers
a ``GammaEdit`` (add / refine / supersede).

Per Paper I §2.1, each Γ-edit is in principle a graph operation on the
Γ-subgraph of G governed by a meta-Γ. This Phase-1b implementation produces
the same edits as direct Python operations; Phase 3 builds the meta-Γ that
admits them as typed graph operations.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .dsl import Count, Eq, Filter, In, Lit, Neighbours, SetT, TypeOf, Var
from .grammar import Grammar, NodePattern, Production


@dataclass
class GammaEdit:
    op: str  # "add" | "refine" | "supersede"
    src_type: str
    tgt_type: str
    n_set: tuple[int, ...]
    reason: str
    superseded_provenance: str | None = None  # for "supersede"


def _alive_n_term(src_var: str = "src") -> Count:
    return Count(Filter(
        source=Neighbours(Var(src_var), edge_type="adjacent_to"),
        var_name="n",
        predicate=Eq(TypeOf(Var("n")), Lit("AliveCell")),
    ))


def _build_production(src_type: str, tgt_type: str, n_set: Iterable[int],
                      provenance: str) -> Production:
    nbrs = _alive_n_term("src")
    items = tuple(Lit(n) for n in sorted(n_set))
    return Production(
        src=NodePattern(src_type, "src"),
        edge_type="transitions_to",
        tgt=NodePattern(tgt_type, "tgt"),
        where=In(nbrs, SetT(items=items)),
        provenance=provenance,
    )


class GammaLearner:
    """Build Γ from observations of Life-like transitions.

    The substrate hypothesis here is narrow: src/tgt types are drawn from
    ``alphabet``, and the only feature considered is the count of
    ``AliveCell`` neighbours via ``adjacent_to`` edges. Generalising to richer
    features is straightforward but out of scope for Phase 1b.
    """

    def __init__(self, alphabet: tuple[str, ...] = ("AliveCell", "DeadCell")) -> None:
        self.alphabet = alphabet
        # (src_type, alive_n) -> Counter[next_type]
        self.observations: dict[tuple[str, int], Counter] = {}
        # (src_type, tgt_type) -> set of n-values where this transition dominates
        self._decision: dict[tuple[str, str], set[int]] = {}
        self.grammar = Grammar([])
        self.edit_log: list[GammaEdit] = []
        self.observation_count: int = 0

    # --- observation ---

    def observe(self, src_type: str, alive_n: int, next_type: str) -> list[GammaEdit]:
        self.observation_count += 1
        key = (src_type, alive_n)
        ctr = self.observations.setdefault(key, Counter())
        prev_top = ctr.most_common(1)[0][0] if ctr else None
        ctr[next_type] += 1
        new_top = ctr.most_common(1)[0][0]
        if new_top == prev_top:
            return []
        return self._reassign(src_type, alive_n, prev_top, new_top)

    def observe_transition(self, before: list[list[int]], after: list[list[int]]) -> list[GammaEdit]:
        """Feed all per-cell observations from a (before, after) board pair."""
        rows = len(before)
        cols = len(before[0])
        edits: list[GammaEdit] = []
        for r in range(rows):
            for c in range(cols):
                src_type = "AliveCell" if before[r][c] else "DeadCell"
                tgt_type = "AliveCell" if after[r][c] else "DeadCell"
                alive_n = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and before[nr][nc]:
                            alive_n += 1
                edits.extend(self.observe(src_type, alive_n, tgt_type))
        return edits

    # --- Γ-edit machinery ---

    def _reassign(self, src_type: str, n: int, old_top: str | None, new_top: str) -> list[GammaEdit]:
        """The dominant next-type for (src_type, n) just changed. Update the decision
        map and produce the GammaEdits that bring Γ into agreement.
        """
        edits: list[GammaEdit] = []
        if old_top is not None and old_top != new_top:
            old_set = self._decision.get((src_type, old_top))
            if old_set is not None and n in old_set:
                old_set.discard(n)
                superseded = f"learned:{src_type}->{old_top}"
                if old_set:
                    edits.append(GammaEdit(
                        op="refine",
                        src_type=src_type,
                        tgt_type=old_top,
                        n_set=tuple(sorted(old_set)),
                        reason=f"removed n={n} after observing {src_type} → {new_top}",
                    ))
                else:
                    edits.append(GammaEdit(
                        op="supersede",
                        src_type=src_type,
                        tgt_type=old_top,
                        n_set=(),
                        reason=f"no n-values remain for {src_type}->{old_top}",
                        superseded_provenance=superseded,
                    ))
                    self._decision.pop((src_type, old_top), None)
        new_set = self._decision.setdefault((src_type, new_top), set())
        if n not in new_set:
            new_set.add(n)
            edits.append(GammaEdit(
                op="add" if len(new_set) == 1 else "refine",
                src_type=src_type,
                tgt_type=new_top,
                n_set=tuple(sorted(new_set)),
                reason=f"observed {src_type} → {new_top} at alive_n={n}",
            ))
        self._rebuild_grammar()
        self.edit_log.extend(edits)
        return edits

    def _rebuild_grammar(self) -> None:
        prods: list[Production] = []
        for (src_type, tgt_type), n_set in self._decision.items():
            if not n_set:
                continue
            prods.append(_build_production(
                src_type, tgt_type, n_set,
                provenance=f"learned:{src_type}->{tgt_type}",
            ))
        self.grammar = Grammar(prods)

    # --- prediction / evaluation ---

    def predict(self, src_type: str, alive_n: int) -> str | None:
        """Return the learner's prediction for (src_type, n), or None if unknown."""
        for (s_t, t_t), n_set in self._decision.items():
            if s_t == src_type and alive_n in n_set:
                return t_t
        return None

    def accuracy(self, observations: Iterable[tuple[str, int, str]]) -> float:
        """Fraction of (src_type, n, next_type) observations the learner predicts correctly.

        Unknown (src_type, n) combinations count as wrong — the learner hasn't
        seen them, so it cannot answer.
        """
        correct = 0
        total = 0
        for src_type, n, next_type in observations:
            total += 1
            if self.predict(src_type, n) == next_type:
                correct += 1
        return correct / total if total else 0.0


def extract_observations(before: list[list[int]], after: list[list[int]]
                         ) -> list[tuple[str, int, str]]:
    """Convert a (before, after) board pair into per-cell observation tuples."""
    rows = len(before)
    cols = len(before[0])
    out: list[tuple[str, int, str]] = []
    for r in range(rows):
        for c in range(cols):
            src_type = "AliveCell" if before[r][c] else "DeadCell"
            tgt_type = "AliveCell" if after[r][c] else "DeadCell"
            alive_n = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and before[nr][nc]:
                        alive_n += 1
            out.append((src_type, alive_n, tgt_type))
    return out
