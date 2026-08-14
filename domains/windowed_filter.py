"""Windowed linear filter primitive — the shared core of insight,
anticipation, and identity-formation detection.

A windowed filter is:
  · samples — list of Term references over a sliding window
      · attr_sample("mt", key)  reads a stashed value from a Mt attr
      · var_sample("name")      binds at evaluation time
  · kernel  — a Term combining the samples; typically a finite-difference
              operator built by nth_order_terms (the user's order-N
              machinery from commit 479cad7)
  · env     — dict mapping Var names → values at evaluation time

The substrate's native evaluator runs the kernel Term. Python
orchestrates samples + env; the DSL engine computes.

Three detection systems share this primitive:
  · insight:      ΔF over [previous_frustration, current_F]
  · anticipation: ∂²F over [prev_prev_frustration, prev_frustration,
                            current_F]
  · formation:    Δh_id per concept over
                  [previous_identity_<cid>, current_h_id]

Each system supplies its own samples + order + gate + action; the
shared primitive handles the windowing + kernel composition + native
evaluation.

The view this makes clean: every detection here is a filter bank
running on the substrate's own metric vectors. Cross-correlation,
band-pass, and adaptive kernels are now one composition away.
"""
from __future__ import annotations

from typing import Any

from substrate_rs import Attr, Var

from domains.order_n_concepts import nth_order_terms


def attr_sample(mt_var: str, attr_key: str):
    """Sample = Attr(Var(mt_var), attr_key).

    Reads a stashed value from a Mt attr. Used for samples already
    written to the graph by a previous step's stash."""
    return Attr(Var(mt_var), attr_key)


def var_sample(var_name: str):
    """Sample = Var(var_name).

    Bound at evaluation time via the env dict. Used for the current
    step's value, which hasn't yet been stashed when filters run."""
    return Var(var_name)


def order_n_kernel(samples: list, order: int):
    """Compose a Term that computes the order-N finite difference of
    the given sample list. Uses the user's nth_order_terms machinery
    so the same kernel form serves phonology + cognitive metrics.

    For order=1 over [a, b]: returns Minus(b, a) (= b - a).
    For order=2 over [a, b, c]: returns Minus(Minus(c, b), Minus(b, a))
                                  (= c - 2b + a, second difference).
    Returns None if the window is too small for the requested order."""
    diffs = nth_order_terms(samples, order)
    if not diffs:
        return None
    # For order ≤ window-1 exactly one term remains; otherwise we take
    # the trailing one (the most-recent end of the difference window).
    return diffs[-1] if order < 2 else diffs[0]


def evaluate_filter(substrate, term, env: dict) -> float:
    """Run substrate.evaluate on a Term + env, return float.

    The substrate's DSL engine computes the value — Python doesn't
    do arithmetic on the sample values, it just binds them."""
    return float(substrate.evaluate(term.to_dict(), env))


def all_attrs_present(substrate, mt, attr_keys: list[str]) -> bool:
    """Check whether all required history attrs exist on the Mt.

    A filter shouldn't fire if its samples aren't all available — the
    substrate hasn't accumulated enough history yet."""
    mt_attrs = substrate.node(mt)["attrs"]
    return all(k in mt_attrs for k in attr_keys)


def compose_and_evaluate(
    substrate,
    mt,
    samples: list,
    order: int,
    env: dict[str, Any],
    required_attrs: list[str] | None = None,
) -> float | None:
    """One-shot: build the order-N kernel over the samples, evaluate
    via the substrate, return the scalar output.

    Returns None if `required_attrs` are not all present on the Mt
    (window not ready). Convenience for the common case where samples
    + env + window check are co-located."""
    if required_attrs is not None and not all_attrs_present(
        substrate, mt, required_attrs
    ):
        return None
    term = order_n_kernel(samples, order)
    if term is None:
        return None
    return evaluate_filter(substrate, term, env)


__all__ = [
    "attr_sample",
    "var_sample",
    "order_n_kernel",
    "evaluate_filter",
    "all_attrs_present",
    "compose_and_evaluate",
]
