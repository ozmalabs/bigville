"""Pure checksum layer for bundles, ticks and runs (NB02).

This module is the audit/equivalence half of the distributed-bundles program.
It contains no scheduler, transport or world mutation: every function is a
digest over already-built protocol objects or over a canonical world payload.
``TickBundleLog`` is an in-memory, JSON-safe record of one tick's dispatch,
result, acknowledgement and commit order; it is deliberately not checkpointed.

Two checksum scopes
-------------------

* **Execution** checksums identify a *path* through the work: the namespace,
  executor, attempt, dispatch input, result output and the acknowledged tick
  order.  Two executors that produce the same world will still differ here.
* **Payload** checksums identify the *world facts* after a tick.  They use the
  semantic projection from :mod:`bigville.tick_trace` (allocation ids and
  log insertion order removed) and are the cross-executor equivalence hash.

The canonical encoders are the ones in :mod:`bigville.bundles`
(``canonical_value``/``canonical_json``); this module does not re-implement
JSON normalisation.  Importing it does not import ``bigville.game`` or
``worlds.bigville_world``.  ``bigville.tick_trace`` is dependency-light (it only
imports the graph runtime) and its ``semantic_world_state`` is reused directly so
the payload definition stays single-sourced.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from .bundles import (
    Bundle,
    BundleAck,
    BundleResult,
    canonical_json,
    canonical_value,
)


__all__ = [
    "TickBundleLog",
    "bundle_execution_sha",
    "bundle_input_sha",
    "bundle_output_sha",
    "run_execution_sha",
    "tick_execution_sha",
    "tick_payload_sha",
]


_UNSET = object()


def _sha256(value: Any) -> str:
    """SHA-256 of the canonical JSON encoding of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class _CallableHash(str):
    """A hash string that also supports the no-argument method spelling.

    ``execution_sha`` is documented as a property; accepting ``log.execution_sha``
    and ``log.execution_sha()`` keeps both natural spellings valid without
    changing the JSON value (a ``str`` subclass serialises normally).
    """

    def __call__(self) -> str:
        return str(self)


def _check_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _check_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return int(value)


def _sorted_canonical(values: Iterable[Any]) -> list[Any]:
    """Canonicalise a sequence and sort it by its canonical JSON text."""
    return sorted((canonical_value(value) for value in values),
                  key=canonical_json)


def _check_result_matches(bundle: Bundle, result: BundleResult) -> None:
    if result.bundle_id != bundle.bundle_id:
        raise ValueError("result bundle_id does not match the bundle")
    if result.namespace != bundle.namespace:
        raise ValueError("result namespace does not match the bundle")
    if result.base_version != bundle.base_version:
        raise ValueError("result base_version does not match the bundle")


# --------------------------------------------------------------------------- bundle hashes


def bundle_input_sha(bundle: Bundle) -> str:
    """Hash the deterministic dispatch input of ``bundle``.

    ``Bundle.input_dict`` already orders operations by ``sort_key`` and sorts
    both resource sets; it intentionally omits ``bundle_id`` (the same work
    under the same namespace is the same input even if the coordinator labels it
    differently).  The namespace, and therefore executor/attempt, is included.
    """
    if not isinstance(bundle, Bundle):
        raise TypeError("bundle_input_sha expects a Bundle")
    return _sha256(bundle.input_dict())


def bundle_output_sha(result: BundleResult) -> str:
    """Hash the deterministic output of a bundle result.

    Effects, created ids and actor-result rows are sorted, so worker completion
    order inside a result cannot change the digest.  The result's own
    ``output_sha`` and ``execution_sha`` fields are excluded: both are
    checksums produced by this layer (``execution_sha`` would be a
    self-reference, and ``output_sha`` is this function's return value).
    ``reason`` *is* included because it is part of the deterministic result.
    """
    if not isinstance(result, BundleResult):
        raise TypeError("bundle_output_sha expects a BundleResult")
    return _sha256({
        "bundle_id": result.bundle_id,
        "namespace": result.namespace.to_dict(),
        "base_version": result.base_version,
        "status": result.status,
        "effects": _sorted_canonical(result.effects),
        "created_ids": _sorted_canonical(result.created_ids),
        "result": _sorted_canonical(result.result),
        "reason": result.reason,
    })


def bundle_execution_sha(bundle: Bundle, result: BundleResult) -> str:
    """Hash one execution path: input + output + namespace/attempt.

    The namespace already contains the executor name, so no separate executor
    field is needed.  A result that does not belong to ``bundle`` is rejected
    rather than hashed into a misleading path identity.
    """
    if not isinstance(bundle, Bundle):
        raise TypeError("bundle_execution_sha expects a Bundle")
    if not isinstance(result, BundleResult):
        raise TypeError("bundle_execution_sha expects a BundleResult")
    _check_result_matches(bundle, result)
    namespace = result.namespace
    return _sha256({
        "input_sha": bundle_input_sha(bundle),
        "output_sha": bundle_output_sha(result),
        "namespace": namespace.to_dict(),
        "attempt": namespace.attempt,
    })


# --------------------------------------------------------------------------- tick and run hashes


def tick_execution_sha(log: "TickBundleLog") -> str:
    """Hash the acknowledged execution of one tick.

    The digest is sorted by bundle id, so result/ack *arrival order* does not
    matter.  Every dispatched bundle contributes an entry: an unacknowledged
    bundle has a ``null`` outcome and digest, so a missing ack changes the hash.
    ``committed_order`` is included separately and is order-sensitive.
    Duplicate acks cannot be stored by :class:`TickBundleLog`; a conflicting
    repeat is rejected there rather than folded into this hash.
    """
    if not isinstance(log, TickBundleLog):
        raise TypeError("tick_execution_sha expects a TickBundleLog")
    entries = []
    for bundle_id in sorted(log.dispatched):
        ack = log.acks.get(bundle_id)
        entries.append({
            "bundle_id": bundle_id,
            "outcome": None if ack is None else ack.outcome,
            "execution_sha": None if ack is None else ack.execution_sha,
        })
    return _sha256({
        "acks": entries,
        "committed_order": list(log.committed_order),
    })


def tick_payload_sha(state: Any) -> str:
    """Hash the semantic world payload after a tick.

    A world-like object (anything with a callable ``export_state``) goes through
    :func:`bigville.tick_trace.semantic_world_state`, which removes allocation
    ids and sorts the log-like export lists.  A mapping is treated as an
    already-normalised payload and canonicalised as-is.  The caller should not
    add execution namespace/origin fields to a mapping; those belong to the
    execution scope, not the payload scope.
    """
    export_state = getattr(state, "export_state", None)
    if callable(export_state):
        # Imported lazily so this module stays cheap to import and a future
        # tick_trace consumer cannot create an import cycle at module load.
        from .tick_trace import semantic_world_state
        payload = semantic_world_state(state)
    elif isinstance(state, Mapping):
        payload = canonical_value(dict(state), path="payload")
    else:
        raise TypeError(
            "tick_payload_sha expects a mapping or a world with export_state")
    return _sha256(payload)


def run_execution_sha(tick_hashes: Iterable[str]) -> str:
    """Hash an ordered run of per-tick execution hashes.

    Tick order is significant (it is the executor path), but the function is
    otherwise a pure function of its inputs.  A bare string is rejected because
    iterating it would silently hash characters instead of tick hashes.
    """
    if isinstance(tick_hashes, (str, bytes, bytearray)):
        raise TypeError("run_execution_sha expects an iterable of tick hashes")
    hashes = []
    for index, value in enumerate(tick_hashes):
        hashes.append(_check_text(value, f"tick_hashes[{index}]"))
    return _sha256({"tick_execution_shas": hashes})


# --------------------------------------------------------------------------- tick log


class TickBundleLog:
    """In-memory audit log for one tick's bundle protocol traffic.

    The log is a coordinator-side record, not a transport and not a
    checkpoint.  It enforces enough identity checking to make the audit
    trustworthy:

    * a dispatch must belong to the log's ``run_id``/``tick``;
    * a duplicate dispatch id is idempotent only for the identical bundle;
    * a result must name a dispatched bundle and match its namespace and base
      version;
    * an ack must name a dispatched bundle and match its base version (and the
      stored result's execution hash when a result is already present);
    * a commit must name a dispatched bundle and may appear only once.

    Results and acks are stored by bundle id, so their arrival order never
    changes :func:`tick_execution_sha`.  ``committed_order`` is a separate,
    order-sensitive tuple.
    """

    def __init__(self, run_id: str, tick: int) -> None:
        self.run_id = _check_text(run_id, "run_id")
        self.tick = _check_int(tick, "tick")
        self.dispatched: dict[str, Bundle] = {}
        self.results: dict[str, BundleResult] = {}
        self.acks: dict[str, BundleAck] = {}
        self.committed_order: tuple[str, ...] = ()
        self._payload_sha: str | None = None

    # -- recording -------------------------------------------------------

    def dispatch(self, bundle: Bundle) -> Bundle:
        if not isinstance(bundle, Bundle):
            raise TypeError("dispatch expects a Bundle")
        if bundle.run_id != self.run_id:
            raise ValueError("bundle run_id does not match the tick log")
        if bundle.tick != self.tick:
            raise ValueError("bundle tick does not match the tick log")
        existing = self.dispatched.get(bundle.bundle_id)
        if existing is not None:
            if existing == bundle:
                return existing
            raise ValueError(
                f"conflicting dispatch for bundle: {bundle.bundle_id!r}")
        self.dispatched[bundle.bundle_id] = bundle
        return bundle

    def result(self, result: BundleResult) -> BundleResult:
        if not isinstance(result, BundleResult):
            raise TypeError("result expects a BundleResult")
        bundle = self.dispatched.get(result.bundle_id)
        if bundle is None:
            raise ValueError(
                f"result for undispatched bundle: {result.bundle_id!r}")
        _check_result_matches(bundle, result)
        existing = self.results.get(result.bundle_id)
        if existing is not None:
            if existing == result:
                return existing
            raise ValueError(
                f"conflicting result for bundle: {result.bundle_id!r}")
        self.results[result.bundle_id] = result
        return result

    def acknowledge(self, ack: BundleAck) -> BundleAck:
        if not isinstance(ack, BundleAck):
            raise TypeError("acknowledge expects a BundleAck")
        bundle = self.dispatched.get(ack.bundle_id)
        if bundle is None:
            raise ValueError(
                f"ack for undispatched bundle: {ack.bundle_id!r}")
        if ack.base_version != bundle.base_version:
            raise ValueError("ack base_version does not match the bundle")
        result = self.results.get(ack.bundle_id)
        if result is not None and ack.execution_sha != result.execution_sha:
            raise ValueError(
                "ack execution_sha does not match the stored result")
        existing = self.acks.get(ack.bundle_id)
        if existing is not None:
            if existing == ack:
                return existing
            raise ValueError(
                f"conflicting ack for bundle: {ack.bundle_id!r}")
        self.acks[ack.bundle_id] = ack
        return ack

    def commit(self, bundle_id: str) -> str:
        bundle_id = _check_text(bundle_id, "bundle_id")
        if bundle_id not in self.dispatched:
            raise ValueError(f"commit for undispatched bundle: {bundle_id!r}")
        if bundle_id in self.committed_order:
            raise ValueError(f"duplicate commit for bundle: {bundle_id!r}")
        self.committed_order = self.committed_order + (bundle_id,)
        return bundle_id

    # -- hashes ----------------------------------------------------------

    @property
    def execution_sha(self) -> str:
        """The current :func:`tick_execution_sha` for this log."""
        return _CallableHash(tick_execution_sha(self))

    def payload_sha(self, state: Any = _UNSET) -> str | None:
        """Return the stored payload hash, or compute/store one.

        With no argument this is the getter (``None`` until a payload is
        recorded).  Passing a mapping or world-like object computes
        :func:`tick_payload_sha` and stores it.  Re-recording the same payload
        is idempotent; recording a different one raises, so an audit log cannot
        silently change the world it refers to.
        """
        if state is _UNSET:
            return self._payload_sha
        digest = tick_payload_sha(state)
        if self._payload_sha is not None and self._payload_sha != digest:
            raise ValueError(
                "payload already recorded with a different hash")
        self._payload_sha = digest
        return digest

    def set_payload(self, state: Any) -> str:
        """Alias for ``payload_sha(state)`` that always returns a string."""
        digest = self.payload_sha(state)
        assert digest is not None
        return digest

    # -- audit -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A deterministic, JSON-safe audit form.

        Bundle, result and ack maps are sorted by bundle id.  ``committed_order``
        preserves the coordinator's actual commit order.
        """
        return {
            "run_id": self.run_id,
            "tick": self.tick,
            "dispatched": {
                bundle_id: self.dispatched[bundle_id].to_dict()
                for bundle_id in sorted(self.dispatched)
            },
            "results": {
                bundle_id: self.results[bundle_id].to_dict()
                for bundle_id in sorted(self.results)
            },
            "acks": {
                bundle_id: self.acks[bundle_id].to_dict()
                for bundle_id in sorted(self.acks)
            },
            "committed_order": list(self.committed_order),
            "execution_sha": self.execution_sha,
            "payload_sha": self._payload_sha,
        }
