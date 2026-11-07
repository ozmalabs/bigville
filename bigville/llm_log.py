"""The complete LLM log (Phase 066): every provider call attempt, thinking included, in a hash chain.

One line per record, append-only:

    {"seq": 7, "prev": "<hash of record 6>", "hash": "<sha256 of seq, prev and record>", "record": {...}}

``record`` holds what the backend writes for one call attempt: the run id, turn, actor, thread, attempt, the
messages exactly as sent, the whole response (``reasoning_content``, ``reasoning``, ``reasoning_details``
and any other field, untruncated), the parsed outcome, the timings and the retries. Every string in a record is
passed through a ``redact`` function (the provider's, which replaces its API key) before it is hashed and
written. No other change is made to a record.

Detection: ``verify_log`` recomputes every hash, checks each sequence number and each previous-hash link, and
compares the last record with a head file (``<log>.head.json``, rewritten after every append). An edited record
changes its hash. A deleted or moved record breaks the sequence or the link. A log cut short at the end is caught
by the head file, which is the one place the chain alone cannot see.

Gzip (optional, ``gzip=True``) writes each record as its own gzip member, so the file stays appendable and
``gzip.open`` reads it back as one stream.

The log is written only to its own file. Nothing in a record reaches the world, another resident, the agent view,
the packet or a replay key. The backend (bigville/backends/llm.py) is the only writer.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

LOG_SCHEMA = "bigville/llm-log/1"
GENESIS = "0" * 64
GZIP_MAGIC = b"\x1f\x8b"


class LogCorrupt(RuntimeError):
    """An existing log fails verification, so it cannot be appended to."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def scrub(value: Any, redact: Callable[[str], str] | None) -> Any:
    """A copy of a JSON-like value with every string passed through ``redact``. Nothing is truncated."""
    if redact is None:
        return copy.deepcopy(value)
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): scrub(item, redact) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item, redact) for item in value]
    return value


def digest(seq: int, prev: str, record: Any) -> str:
    return hashlib.sha256(canonical({"seq": seq, "prev": prev, "record": record}).encode("utf-8")).hexdigest()


def _open_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw[:2] == GZIP_MAGIC:
        raw = gzip.decompress(raw)
    return [line for line in raw.decode("utf-8").split("\n") if line.strip()]


def head_path(path: str | Path) -> Path:
    return Path(str(path) + ".head.json")


@dataclass
class LogCheck:
    ok: bool
    records: int
    problems: list[str] = field(default_factory=list)
    last_seq: int = 0
    last_hash: str = GENESIS
    head_checked: bool = False


def verify_log(path: str | Path, *, head: str | Path | None = None) -> LogCheck:
    """Check a log. ``head`` defaults to the head file next to the log, when it exists."""
    target = Path(path)
    if not target.exists():
        return LogCheck(ok=True, records=0)
    problems: list[str] = []
    prev, expected = GENESIS, 1
    last_seq, last_hash = 0, GENESIS
    lines = _open_lines(target)
    for number, line in enumerate(lines, start=1):
        try:
            item = json.loads(line)
            seq, link, stored, record = item["seq"], item["prev"], item["hash"], item["record"]
        except (ValueError, KeyError, TypeError):
            problems.append(f"line {number}: not a log record")
            break
        if seq != expected:
            problems.append(f"line {number}: sequence {seq} where {expected} was expected "
                            "(a record was removed, moved or added)")
            break
        if link != prev:
            problems.append(f"record {seq}: the previous hash does not match record {seq - 1} "
                            "(an earlier record was edited or removed)")
            break
        if digest(seq, link, record) != stored:
            problems.append(f"record {seq}: the content does not match its hash (the record was edited)")
            break
        prev, last_hash, last_seq = stored, stored, seq
        expected += 1
    head_file = Path(head) if head is not None else head_path(target)
    head_checked = False
    if head_file.exists():
        head_checked = True
        recorded = json.loads(head_file.read_text(encoding="utf-8"))
        if int(recorded.get("seq", 0)) != last_seq or recorded.get("hash") != last_hash:
            problems.append(f"the head file says record {recorded.get('seq')} but the log ends at {last_seq} "
                            "(records were removed from the end, or the log was replaced)")
    return LogCheck(ok=not problems, records=len(lines) if not problems else last_seq,
                    problems=problems, last_seq=last_seq, last_hash=last_hash, head_checked=head_checked)


def read_log(path: str | Path) -> list[dict[str, Any]]:
    """The records (the ``record`` field of each line), in order. Does not verify; call verify_log first."""
    return [json.loads(line)["record"] for line in _open_lines(Path(path))]


class LLMLog:
    """Appends records to one log file. Thread-safe. Reopening continues the chain, after verifying it."""

    def __init__(self, path: str | Path, *, run_id: str, gzip: bool = False,
                 redact: Callable[[str], str] | None = None, head: bool = True):
        self.path = Path(path)
        self.run_id = str(run_id)
        self.gzip = bool(gzip)
        self.redact = redact
        self.use_head = bool(head)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        check = verify_log(self.path)
        if not check.ok:
            raise LogCorrupt("; ".join(check.problems))
        self.seq = check.last_seq
        self.prev = check.last_hash

    @property
    def head_file(self) -> Path:
        return head_path(self.path)

    def append(self, record: dict[str, Any], *, redact: Callable[[str], str] | None = None) -> int:
        """Write one record and return its sequence number. ``redact`` (per call, or the log's own) is applied to
        every string first."""
        fn = redact or self.redact
        with self._lock:
            body = scrub({"run_id": self.run_id, **record}, fn)
            seq = self.seq + 1
            current = digest(seq, self.prev, body)
            line = canonical({"seq": seq, "prev": self.prev, "hash": current, "record": body}) + "\n"
            if self.gzip:
                with gzip.open(self.path, "ab") as stream:
                    stream.write(line.encode("utf-8"))
            else:
                with open(self.path, "ab") as stream:
                    stream.write(line.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
            self.seq, self.prev = seq, current
            if self.use_head:
                self._write_head()
            return seq

    def _write_head(self) -> None:
        tmp = self.head_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"schema": LOG_SCHEMA, "seq": self.seq, "hash": self.prev}, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, self.head_file)


def attach(backends: dict[str, Any], log: LLMLog | None) -> int:
    """Set ``log`` on every LLM backend in a name-to-backend mapping. Returns how many were set. Other backends are
    not touched."""
    count = 0
    for backend in backends.values():
        if hasattr(backend, "llm_counts") and hasattr(backend, "log"):
            backend.log = log
            count += 1
    return count


DEFAULT_LOG_DIR = "runs/llm_logs"
LOG_DIR_ENV = "BIGVILLE_LLM_LOG_DIR"


def new_run_id() -> str:
    """A run id: the UTC time to the second, and 8 random hex digits so two runs in one second differ."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]


def attach_default(backends: dict[str, Any], *, enabled: bool = True, log_dir: str | os.PathLike | None = None,
                   run_id: str | None = None) -> LLMLog | None:
    """The default complete log for a game (fix_llm_ops). Returns None, and creates no file or directory, when
    ``enabled`` is false or no LLM backend is in ``backends``. Otherwise one gzip log is created at
    ``<dir>/<run id>.jsonl.gz``, where ``dir`` is ``log_dir``, else the ``BIGVILLE_LLM_LOG_DIR`` environment
    variable, else ``runs/llm_logs`` relative to the working directory. The log is attached to every LLM backend.
    Its redaction is the first LLM provider's ``redact`` (each call also redacts with its own provider)."""
    if not enabled:
        return None
    llm = [backend for backend in backends.values() if hasattr(backend, "llm_counts") and hasattr(backend, "log")]
    if not llm:
        return None
    run = run_id or new_run_id()
    if not run or run in (".", "..") or "/" in run or "\\" in run:
        raise ValueError(f"run id {run!r} must be a plain name")
    directory = Path(log_dir or os.environ.get(LOG_DIR_ENV) or DEFAULT_LOG_DIR)
    redact = next((fn for fn in (getattr(getattr(b, "provider", None), "redact", None) for b in llm)
                   if callable(fn)), None)
    log = LLMLog(directory / f"{run}.jsonl.gz", run_id=run, gzip=True, redact=redact)
    attach(backends, log)
    return log
