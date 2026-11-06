"""Bounded parallel decisions for backends marked ``concurrent`` (Phase 055).

``BigvilleGame.step()`` builds the context of every concurrent resident before any of them decides, then
calls their ``decide`` through one thread pool. The results come back keyed by resident, in the order the
residents were registered, so the game applies them in a fixed order however the threads finish.

A backend opts in with ``concurrent = True``. Its ``concurrency`` attribute is the number of threads it wants
(default ``DEFAULT_WORKERS``); the pool uses the largest such number among the backends in the step.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

DEFAULT_WORKERS = 4


def pool_workers(backends) -> int:
    """The pool size for these backends: the largest ``concurrency`` asked for, at least 1."""
    sizes = [int(getattr(backend, "concurrency", DEFAULT_WORKERS)) for backend in backends]
    return max(1, max(sizes, default=1))


def decide_pooled(deferred: dict[str, tuple[Any, Any]]) -> dict[str, Any]:
    """Call ``backend.decide(context)`` for each ``actor -> (backend, context)`` in a thread pool.

    Returns ``actor -> response`` in the order of ``deferred``. An exception raised by a decision is raised here,
    for the first actor (in that order) whose decision failed. A call with nothing deferred returns at once."""
    if not deferred:
        return {}
    workers = min(pool_workers(backend for backend, _ in deferred.values()), len(deferred))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bigville-decide") as pool:
        futures = {actor: pool.submit(backend.decide, context)
                   for actor, (backend, context) in deferred.items()}
        return {actor: futures[actor].result() for actor in deferred}
