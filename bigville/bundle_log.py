"""Append-only JSONL journal for bundle dispatch, results, acks and commits.

DR02 of the distributed-runtime plan.  The journal is the durable half of the
:mod:`bigville.bundle_checks` audit log: ``TickBundleLog`` remains the in-memory
authority for one tick, while :class:`BundleJournal` writes the same protocol
objects to a file that can be read, replayed and verified after the process that
produced it has gone.

Record format
-------------

One canonical JSON object per line, in append order::

    {"kind":"tick_start","run_id":...,"tick":...,"base_version":...,"revision":...}
    {"kind":"dispatch","bundle":{...}}
    {"kind":"result","result":{...}}
    {"kind":"ack","ack":{...}}
    {"kind":"commit","bundle_id":...,"committed_version":...}
    {"kind":"tick_end","run_id":...,"tick":...,"execution_sha":...,
     "payload_sha":...,"revision":...,"status":"ok"}

``tick`` is the tick log's identity (the bundle base/version used by the
existing partitioned executor).  ``base_version`` repeats the value for readers
that only have the start record; ``revision`` is the world graph revision
observed when the tick began.  ``tick_end`` carries the post-turn revision and
the two checksums, so a replay can prove it rebuilt the same tick.

An aborted tick (a bundle rejection or an exception during the turn) closes with
``"status":"aborted"``.  Its checksums may be partial and it is not required to
cover every dispatched bundle; :meth:`BundleJournal.verify` reports it but does
not claim a complete tick.

Durability and writers
----------------------

* One writer per journal.  ``append`` opens the file with ``O_APPEND`` on first
  use, writes one canonical line, flushes and ``fsync``s before returning.  If
  the write or fsync raises, the record is not considered appended.
* A process-local registry rejects a second :class:`BundleJournal` opening the
  same path for append.  Cross-process writers are not supported; a caller that
  needs them must put its own exclusive lock around the file.  Readers are
  unaffected.
* Parent directories are created only when the first record is appended, so a
  serial game configured with a path creates no file at all.

Corruption policy
-----------------

:meth:`read` yields every complete record.  A final line without its trailing
newline is a *truncated tail*: it is not yielded and is reported as
``BundleJournal.last_read_report.truncated_tail``.  A malformed line anywhere
else raises :class:`JournalCorruptionError` with its 1-based line number.
:meth:`replay` and :meth:`verify` refuse a truncated tail by default; pass
``allow_truncated=True`` to inspect the complete prefix.

This module imports only :mod:`bigville.bundles` and
:mod:`bigville.bundle_checks`.  It never imports ``bigville.game`` or
``worlds.bigville_world``, so the journal can be read in a verification tool or
test process without constructing a world.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .bundle_checks import (TickBundleLog, bundle_execution_sha,
                            bundle_output_sha)
from .bundles import (Bundle, BundleAck, BundleResult, canonical_json,
                      canonical_value)


__all__ = [
    "BundleJournal",
    "BundleJournalError",
    "DuplicateRecordError",
    "JournalCorruptionError",
    "JournalPathError",
    "JournalReadReport",
    "JournalTruncatedError",
    "JournalVerification",
    "JournalVerifyError",
    "RECORD_KINDS",
]


RECORD_KINDS = frozenset({
    "tick_start", "dispatch", "result", "ack", "commit", "tick_end",
})

_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "tick_start": ("run_id", "tick", "base_version", "revision"),
    "dispatch": ("bundle",),
    "result": ("result",),
    "ack": ("ack",),
    "commit": ("bundle_id", "committed_version"),
    "tick_end": ("tick", "execution_sha", "payload_sha", "revision"),
}


class BundleJournalError(RuntimeError):
    """Base class for journal path, corruption and verification errors."""


class JournalPathError(BundleJournalError, ValueError):
    """The journal path cannot be used as an append-only file."""


class JournalCorruptionError(BundleJournalError):
    """A complete line is not a valid journal record."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        if line is not None:
            message = f"line {line}: {message}"
        super().__init__(message)


class JournalTruncatedError(JournalCorruptionError):
    """The file ends in a partial line (usually a crash during append)."""


class JournalVerifyError(BundleJournalError):
    """Records are well formed but do not describe a valid tick sequence."""


class DuplicateRecordError(BundleJournalError):
    """An identical record was appended twice to the same open tick."""


@dataclass(frozen=True)
class JournalReadReport:
    """What :meth:`BundleJournal.read` saw, including a truncated tail flag."""

    path: str
    byte_size: int
    line_count: int
    record_count: int
    truncated_tail: bool = False
    truncated_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "byte_size": self.byte_size,
            "line_count": self.line_count,
            "record_count": self.record_count,
            "truncated_tail": self.truncated_tail,
            "truncated_bytes": self.truncated_bytes,
        }


@dataclass(frozen=True)
class JournalVerification:
    """The report returned by :meth:`BundleJournal.verify`."""

    path: str
    byte_size: int
    records: int
    ticks: int
    aborted_ticks: int
    bundles: int
    truncated_tail: bool
    revisions: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "byte_size": self.byte_size,
            "records": self.records,
            "ticks": self.ticks,
            "aborted_ticks": self.aborted_ticks,
            "bundles": self.bundles,
            "truncated_tail": self.truncated_tail,
            "revisions": list(self.revisions),
        }


_OPEN_PATHS: set[str] = set()
_OPEN_LOCK = threading.Lock()


def _path_key(path: Path) -> str:
    """A stable identity for the process-local single-writer registry."""
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise JournalVerifyError(f"{field} must be an integer >= {minimum}")
    return int(value)


class BundleJournal:
    """An append-only, replayable JSONL journal for bundle protocol traffic.

    Construction validates only the shape of ``path``.  Directories and the file
    itself are created on the first :meth:`append`, which keeps ``path`` purely
    opt-in: a game configured with a journal path but running serial/threaded
    leaves the filesystem untouched.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if isinstance(path, os.PathLike):
            path = os.fspath(path)
        if not isinstance(path, str) or not path.strip():
            raise JournalPathError("bundle journal path must be a non-empty string")
        target = Path(path)
        if target.exists() and not target.is_file():
            raise JournalPathError(
                f"bundle journal path is not a file: {target}")
        self.path = target
        self._fh: Any = None
        self._lock = threading.RLock()
        self._block_open = False
        self._block_run_id: str | None = None
        self._block_tick: int | None = None
        self._block_fingerprints: set[str] = set()
        self._records_appended = 0
        self._bytes_appended = 0
        self._path_key: str | None = None
        self.last_read_report: JournalReadReport | None = None

    # -- lifecycle -------------------------------------------------------

    @property
    def closed(self) -> bool:
        return self._fh is None

    def __enter__(self) -> "BundleJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_open(self) -> Any:
        if self._fh is not None:
            return self._fh
        key = _path_key(self.path)
        with _OPEN_LOCK:
            if key in _OPEN_PATHS:
                raise BundleJournalError(
                    f"bundle journal is already open for append: {self.path}")
            _OPEN_PATHS.add(key)
            self._path_key = key
        try:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and not self.path.is_file():
                    raise JournalPathError(
                        f"bundle journal path is not a file: {self.path}")
                # "ab" uses O_APPEND: each write is placed at the current end
                # even if a reader is active.  The single-writer rule keeps
                # records from interleaving.
                self._fh = open(self.path, "ab")
            except JournalPathError:
                raise
            except OSError as exc:
                raise JournalPathError(
                    f"cannot open bundle journal {self.path}: {exc}") from exc
        except BaseException:
            with _OPEN_LOCK:
                _OPEN_PATHS.discard(key)
            self._path_key = None
            raise
        return self._fh

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.flush()
                    os.fsync(self._fh.fileno())
                finally:
                    self._fh.close()
                    self._fh = None
            if self._path_key is not None:
                with _OPEN_LOCK:
                    _OPEN_PATHS.discard(self._path_key)
                self._path_key = None

    # -- record validation ----------------------------------------------

    @staticmethod
    def _normalise(record: Mapping[str, Any], *, error=ValueError) -> dict[str, Any]:
        if not isinstance(record, Mapping):
            raise error("journal record must be a mapping")
        try:
            data = canonical_value(dict(record), path="record")
        except Exception as exc:  # BundleValueError is a TypeError
            raise error(f"journal record is not JSON-safe: {exc}") from exc
        if not isinstance(data, dict):
            raise error("journal record must normalise to an object")
        kind = data.get("kind")
        if kind not in RECORD_KINDS:
            raise error(f"unknown journal record kind: {kind!r}")
        missing = [key for key in _REQUIRED_KEYS[kind] if key not in data]
        if missing:
            raise error(
                f"{kind} record missing keys: {', '.join(sorted(missing))}")
        return data

    def _decode(self, value: Any, *, line: int) -> dict[str, Any]:
        try:
            return self._normalise(value, error=JournalCorruptionError)
        except JournalCorruptionError as exc:
            raise JournalCorruptionError(str(exc), line=line) from exc

    # -- append ----------------------------------------------------------

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Append one record, fsync it and return its canonical form.

        The journal enforces a small state machine so a caller cannot interleave
        two ticks or duplicate a record without noticing:

        * ``tick_start`` opens a tick and is rejected while one is already open;
        * every other record requires an open tick;
        * an identical record inside the same open tick raises
          :class:`DuplicateRecordError`;
        * ``tick_end`` closes the tick.
        """
        with self._lock:
            data = self._normalise(record)
            text = canonical_json(data)
            kind = data["kind"]
            if kind == "tick_start":
                if self._block_open:
                    raise BundleJournalError(
                        "tick_start while another tick is open")
                next_open = True
                next_fingerprints = {text}
            else:
                if not self._block_open:
                    raise BundleJournalError(
                        f"{kind} record outside an open tick")
                if text in self._block_fingerprints:
                    raise DuplicateRecordError(
                        f"duplicate {kind} record in the open tick")
                next_open = kind != "tick_end"
                next_fingerprints = (set(self._block_fingerprints) | {text}
                                     if next_open else set())

            fh = self._ensure_open()
            payload = (text + "\n").encode("utf-8")
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())

            # Only advance the in-memory block state after the durable append
            # succeeded, so a failed write cannot leave a phantom open tick.
            self._records_appended += 1
            self._bytes_appended += len(payload)
            self._block_open = next_open
            self._block_fingerprints = next_fingerprints
            if kind == "tick_start":
                self._block_run_id = data["run_id"]
                self._block_tick = data["tick"]
            elif not next_open:
                self._block_run_id = None
                self._block_tick = None
            return data

    # -- high-level record helpers --------------------------------------

    def tick_start(self, run_id: str, tick: int, *,
                   base_version: int | None = None,
                   revision: int | None = None) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string")
        tick = int(tick)
        base = tick if base_version is None else int(base_version)
        observed = base if revision is None else int(revision)
        return self.append({
            "kind": "tick_start",
            "run_id": run_id,
            "tick": tick,
            "base_version": base,
            "revision": observed,
        })

    def dispatch(self, bundle: Bundle) -> dict[str, Any]:
        if not isinstance(bundle, Bundle):
            raise TypeError("dispatch expects a Bundle")
        return self.append({"kind": "dispatch", "bundle": bundle.to_dict()})

    def result(self, result: BundleResult) -> dict[str, Any]:
        if not isinstance(result, BundleResult):
            raise TypeError("result expects a BundleResult")
        return self.append({"kind": "result", "result": result.to_dict()})

    def ack(self, ack: BundleAck) -> dict[str, Any]:
        if not isinstance(ack, BundleAck):
            raise TypeError("ack expects a BundleAck")
        return self.append({"kind": "ack", "ack": ack.to_dict()})

    def commit(self, bundle_id: str, committed_version: int | None) -> dict[str, Any]:
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError("bundle_id must be a non-empty string")
        return self.append({
            "kind": "commit",
            "bundle_id": bundle_id,
            "committed_version": committed_version,
        })

    def tick_end(self, tick: int, *, execution_sha: str, payload_sha: str | None,
                 revision: int, run_id: str | None = None,
                 status: str = "ok", reason: str = "") -> dict[str, Any]:
        if status not in ("ok", "aborted"):
            raise ValueError("tick_end status must be 'ok' or 'aborted'")
        if not isinstance(execution_sha, str) or not execution_sha:
            if status == "ok":
                raise ValueError("execution_sha must be a non-empty string")
        if status == "ok" and (not isinstance(payload_sha, str) or not payload_sha):
            raise ValueError("payload_sha must be a non-empty string")
        record: dict[str, Any] = {
            "kind": "tick_end",
            "run_id": run_id if run_id is not None else self._block_run_id,
            "tick": int(tick),
            "execution_sha": execution_sha,
            "payload_sha": payload_sha,
            "revision": int(revision),
            "status": status,
        }
        if reason:
            record["reason"] = reason
        return self.append(record)

    def abort_tick(self, reason: str, *, execution_sha: str | None = None,
                   payload_sha: str | None = None,
                   revision: int | None = None) -> dict[str, Any] | None:
        """Close an open tick with ``status="aborted"``; no-op when closed."""
        with self._lock:
            if not self._block_open:
                return None
            tick = 0 if self._block_tick is None else self._block_tick
            return self.tick_end(
                tick,
                execution_sha=execution_sha or "",
                payload_sha=payload_sha,
                revision=0 if revision is None else revision,
                run_id=self._block_run_id,
                status="aborted",
                reason=reason,
            )

    # -- reading ---------------------------------------------------------

    def read(self) -> Iterator[dict[str, Any]]:
        """Yield every complete record; record a report on ``last_read_report``.

        A partial final line is not yielded.  A malformed *complete* line raises
        :class:`JournalCorruptionError`; it is never skipped silently.
        """
        if not self.path.exists():
            self.last_read_report = JournalReadReport(
                path=str(self.path), byte_size=0, line_count=0,
                record_count=0)
            return

        data = self.path.read_bytes()
        complete: list[bytes] = []
        truncated = False
        truncated_bytes = 0
        if data:
            parts = data.split(b"\n")
            if data.endswith(b"\n"):
                complete = parts[:-1]
            else:
                truncated = True
                truncated_bytes = len(parts[-1])
                complete = parts[:-1]

        records: list[dict[str, Any]] = []
        for index, raw in enumerate(complete, start=1):
            if not raw.strip():
                raise JournalCorruptionError("blank journal line", line=index)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise JournalCorruptionError(
                    f"journal line is not UTF-8: {exc}", line=index) from exc
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise JournalCorruptionError(
                    f"invalid JSON: {exc.msg}", line=index) from exc
            records.append(self._decode(value, line=index))

        self.last_read_report = JournalReadReport(
            path=str(self.path),
            byte_size=len(data),
            line_count=len(complete),
            record_count=len(records),
            truncated_tail=truncated,
            truncated_bytes=truncated_bytes,
        )
        yield from records

    # -- replay and verification ----------------------------------------

    def replay(self, *, allow_truncated: bool = False,
               allow_incomplete: bool = False) -> list[TickBundleLog]:
        """Rebuild one :class:`TickBundleLog` per complete tick, in order.

        Replay enforces the same identity rules as the live log and adds the
        durable-journal rules: no duplicate dispatch/result/ack/commit, every
        dispatched bundle covered by an ok tick, commit order and revisions
        coherent, and the tick checksums recomputed from the records.  An
        aborted tick is only accepted with ``allow_incomplete=True``.
        """
        logs, _aborted, _revisions = self._replay(
            allow_truncated=allow_truncated,
            allow_incomplete=allow_incomplete)
        return logs

    def verify(self, *, allow_truncated: bool = False,
               allow_incomplete: bool = False) -> JournalVerification:
        """Validate the whole journal and return a compact report.

        Raises :class:`JournalTruncatedError`, :class:`JournalCorruptionError`
        or :class:`JournalVerifyError` on any problem.
        """
        logs, aborted, revisions = self._replay(
            allow_truncated=allow_truncated,
            allow_incomplete=allow_incomplete)
        report = self.last_read_report
        assert report is not None
        return JournalVerification(
            path=str(self.path),
            byte_size=report.byte_size,
            records=report.record_count,
            ticks=len(logs),
            aborted_ticks=aborted,
            bundles=sum(len(log.dispatched) for log in logs),
            truncated_tail=report.truncated_tail,
            revisions=tuple(revisions),
        )

    def _replay(self, *, allow_truncated: bool,
                allow_incomplete: bool
                ) -> tuple[list[TickBundleLog], int, list[int]]:
        records = list(self.read())
        report = self.last_read_report
        assert report is not None
        if report.truncated_tail and not allow_truncated:
            raise JournalTruncatedError(
                f"journal ends in a truncated line "
                f"({report.truncated_bytes} bytes)",
                line=report.line_count + 1)

        logs: list[TickBundleLog] = []
        aborted = 0
        revisions: list[int] = []
        log: TickBundleLog | None = None
        state: dict[str, Any] | None = None

        def fail(message: str, index: int) -> JournalVerifyError:
            return JournalVerifyError(f"record {index + 1}: {message}")

        def mark(kind: str, bundle_id: str, index: int) -> None:
            assert state is not None
            positions = state["positions"].setdefault(bundle_id, {})
            if kind in positions:
                raise fail(
                    f"duplicate {kind} for bundle {bundle_id!r}", index)
            positions[kind] = index

        for index, record in enumerate(records):
            kind = record["kind"]
            if kind == "tick_start":
                if log is not None:
                    raise fail("tick_start before the previous tick_end", index)
                try:
                    tick = _require_int(record["tick"], "tick")
                    base = _require_int(record["base_version"], "base_version")
                    start_revision = _require_int(
                        record["revision"], "tick_start revision")
                    run_id = record["run_id"]
                    if not isinstance(run_id, str) or not run_id:
                        raise JournalVerifyError(
                            "tick_start run_id must be a non-empty string")
                    log = TickBundleLog(run_id, tick)
                except JournalVerifyError as exc:
                    raise fail(str(exc), index) from exc
                except (TypeError, ValueError) as exc:
                    raise fail(f"invalid tick_start: {exc}", index) from exc
                state = {
                    "run_id": run_id,
                    "tick": tick,
                    "base_version": base,
                    "start_revision": start_revision,
                    "positions": {},
                    "committed": {},
                    "last_committed": None,
                }
                continue

            if kind == "tick_end":
                if log is None or state is None:
                    raise fail("tick_end without a tick_start", index)
                try:
                    end_tick = _require_int(record["tick"], "tick_end tick")
                    revision = _require_int(
                        record["revision"], "tick_end revision")
                except JournalVerifyError as exc:
                    raise fail(str(exc), index) from exc
                if end_tick != state["tick"]:
                    raise fail("tick_end tick does not match tick_start", index)
                if record.get("run_id") not in (None, state["run_id"]):
                    raise fail("tick_end run_id does not match tick_start", index)
                status = record.get("status", "ok")
                if status not in ("ok", "aborted"):
                    raise fail(f"invalid tick_end status {status!r}", index)
                if status == "aborted":
                    aborted += 1
                    if not allow_incomplete:
                        raise fail(
                            "tick is aborted (pass allow_incomplete=True to "
                            "inspect it)", index)
                    if isinstance(record.get("payload_sha"), str):
                        log._payload_sha = record["payload_sha"]
                    logs.append(log)
                    log = None
                    state = None
                    continue

                # Coverage and per-bundle order come before the checksum so a
                # missing record reports precisely, rather than as a hash drift.
                positions = state["positions"]
                for bundle_id in sorted(log.dispatched):
                    bundle_positions = positions.get(bundle_id, {})
                    for required in ("result", "ack", "commit"):
                        if required not in bundle_positions:
                            raise fail(
                                f"bundle {bundle_id!r} is missing its "
                                f"{required} record", index)
                    ordered = (bundle_positions["dispatch"],
                               bundle_positions["result"],
                               bundle_positions["ack"],
                               bundle_positions["commit"])
                    if ordered != tuple(sorted(ordered)):
                        raise fail(
                            f"bundle {bundle_id!r} result/ack/commit order is "
                            f"not dispatch->result->ack->commit", index)

                try:
                    expected_execution = str(log.execution_sha)
                except Exception as exc:
                    raise fail(f"cannot compute execution hash: {exc}", index) from exc
                if record["execution_sha"] != expected_execution:
                    raise fail(
                        "tick_end execution_sha does not match the replayed "
                        "dispatch/ack/commit order", index)
                expected_payload = log.payload_sha()
                if (expected_payload is not None
                        and record["payload_sha"] != expected_payload):
                    raise fail(
                        "tick_end payload_sha does not match the replayed "
                        "payload hash", index)

                last_committed = state["last_committed"]
                if last_committed is not None and revision < last_committed:
                    raise fail(
                        f"tick_end revision {revision} is older than the last "
                        f"committed version {last_committed}", index)
                if revision < state["base_version"]:
                    raise fail(
                        f"tick_end revision {revision} is older than the "
                        f"tick base {state['base_version']}", index)
                if state["start_revision"] > revision:
                    raise fail(
                        "tick_end revision is older than tick_start revision",
                        index)

                if isinstance(record["payload_sha"], str):
                    log._payload_sha = record["payload_sha"]
                logs.append(log)
                revisions.append(revision)
                log = None
                state = None
                continue

            if log is None or state is None:
                raise fail(f"{kind} record outside an open tick", index)

            try:
                if kind == "dispatch":
                    bundle = Bundle.from_dict(record["bundle"])
                    bundle_id = bundle.bundle_id
                    mark("dispatch", bundle_id, index)
                    if bundle.run_id != state["run_id"]:
                        raise JournalVerifyError(
                            "bundle run_id does not match tick_start")
                    if bundle.tick != state["tick"]:
                        raise JournalVerifyError(
                            "bundle tick does not match tick_start")
                    if bundle.base_version != state["base_version"]:
                        raise JournalVerifyError(
                            "bundle base_version does not match tick_start")
                    log.dispatch(bundle)
                elif kind == "result":
                    result = BundleResult.from_dict(record["result"])
                    bundle_id = result.bundle_id
                    mark("result", bundle_id, index)
                    bundle = log.dispatched.get(bundle_id)
                    if bundle is None:
                        raise JournalVerifyError(
                            f"result for undispatched bundle {bundle_id!r}")
                    if bundle_output_sha(result) != result.output_sha:
                        raise JournalVerifyError(
                            f"result output_sha does not match its contents "
                            f"for {bundle_id!r}")
                    if bundle_execution_sha(bundle, result) != result.execution_sha:
                        raise JournalVerifyError(
                            f"result execution_sha does not match its "
                            f"dispatch for {bundle_id!r}")
                    log.result(result)
                elif kind == "ack":
                    ack = BundleAck.from_dict(record["ack"])
                    bundle_id = ack.bundle_id
                    mark("ack", bundle_id, index)
                    log.acknowledge(ack)
                elif kind == "commit":
                    bundle_id = record["bundle_id"]
                    if not isinstance(bundle_id, str) or not bundle_id:
                        raise JournalVerifyError(
                            "commit bundle_id must be a non-empty string")
                    committed_version = record["committed_version"]
                    if committed_version is not None:
                        committed_version = _require_int(
                            committed_version, "committed_version")
                    mark("commit", bundle_id, index)
                    ack = log.acks.get(bundle_id)
                    if ack is not None:
                        if ack.outcome != "committed":
                            raise JournalVerifyError(
                                f"commit for non-committed ack {bundle_id!r}")
                        if ack.committed_version != committed_version:
                            raise JournalVerifyError(
                                f"commit version does not match ack for "
                                f"{bundle_id!r}")
                    if committed_version is None:
                        raise JournalVerifyError(
                            f"committed bundle {bundle_id!r} has no version")
                    last = state["last_committed"]
                    if last is not None and committed_version < last:
                        raise JournalVerifyError(
                            f"commit order is not monotonic: "
                            f"{committed_version} < {last}")
                    state["last_committed"] = committed_version
                    state["committed"][bundle_id] = committed_version
                    log.commit(bundle_id)
                else:  # pragma: no cover - RECORD_KINDS already restricts kind
                    raise JournalVerifyError(f"unknown record kind {kind!r}")
            except JournalVerifyError as exc:
                message = str(exc)
                raise fail(message, index) from exc
            except (TypeError, ValueError) as exc:
                raise fail(f"invalid {kind} record: {exc}", index) from exc

        if log is not None:
            # A crash can truncate the tail in the middle of a tick.  When the
            # caller explicitly accepts a truncated tail, the complete records
            # of that final tick are still inspectable; an aborted/explicit
            # incompleteness still needs allow_incomplete.
            if not (allow_incomplete
                    or (allow_truncated and report.truncated_tail)):
                raise JournalVerifyError(
                    "journal ends with an open tick (no tick_end)")
            logs.append(log)
        return logs, aborted, revisions
