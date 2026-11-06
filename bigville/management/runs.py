"""Durable local run records and serialized in-process game lifecycle."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..api import create_game
from .drafts import PreviewTooLarge, preview_draft, resolve_draft

REGISTRY_SCHEMA_VERSION = 1
VALID_STATES = {"created", "starting", "running", "paused", "waiting",
                "completed", "failed", "stopped"}
TERMINAL_STATES = {"completed", "failed", "stopped"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RegistryError(Exception):
    code = "registry_error"


class RunNotFound(RegistryError):
    code = "run_not_found"


class RunConflict(RegistryError):
    code = "run_conflict"


class InvalidTransition(RegistryError):
    code = "invalid_transition"


class InvalidRunRequest(RegistryError):
    code = "invalid_run_request"


class _Runtime:
    def __init__(self):
        self.lock = threading.RLock()
        self.game = None
        self.worker: threading.Thread | None = None


class RunRegistry:
    """Single-process registry; metadata survives restart, world state does not."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "registry.json"
        self._lock = threading.RLock()
        self._runtime: dict[str, _Runtime] = {}
        self._state = self._load_state()
        self._recover_interrupted()

    def _empty_state(self) -> dict[str, Any]:
        return {"schema_version": REGISTRY_SCHEMA_VERSION,
                "runs": {}, "idempotency": {}}

    def _load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            state = self._empty_state()
            self._write_state(state)
            return state
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Run registry is malformed; refusing to overwrite {self.path}") from exc
        if (not isinstance(state, dict) or
                state.get("schema_version") != REGISTRY_SCHEMA_VERSION or
                not isinstance(state.get("runs"), dict) or
                not isinstance(state.get("idempotency"), dict)):
            raise ValueError(f"Run registry schema is incompatible; refusing to overwrite {self.path}")
        for run_id, record in state["runs"].items():
            if (not isinstance(run_id, str) or not isinstance(record, dict) or
                    record.get("schema_version") != 1 or record.get("id") != run_id or
                    record.get("status") not in VALID_STATES or
                    not isinstance(record.get("config"), dict)):
                raise ValueError(f"Run registry contains an invalid record; refusing to overwrite {self.path}")
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=self.data_dir)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(encoded)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp_name, self.path)
            try:
                directory_fd = os.open(self.data_dir, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _persist(self) -> None:
        self._write_state(self._state)

    def _recover_interrupted(self) -> None:
        changed = False
        now = _utc_now()
        for record in self._state["runs"].values():
            unfinished = record["status"] not in TERMINAL_STATES
            progressed_created = record["status"] == "created" and int(record.get("turn", 0)) > 0
            if unfinished and (record["status"] != "created" or progressed_created):
                record["status"] = "failed"
                record["error"] = (
                    "interrupted by service restart; in-memory world state is not persisted")
                record["updated_at"] = now
                changed = True
        if changed:
            self._persist()

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(record)

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._state["runs"].values())
            return [self._public(record) for record in sorted(
                records, key=lambda item: (item["created_at"], item["id"]), reverse=True)]

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._state["runs"].get(run_id)
            if record is None:
                raise RunNotFound(f"Run {run_id!r} was not found.")
            return self._public(record)

    def create_run(self, request: Any) -> tuple[dict[str, Any], bool]:
        """Return (record, created); key reuse is checked against canonical resolved config."""
        if not isinstance(request, dict):
            raise InvalidRunRequest("Request must be a JSON object.")
        allowed = {"draft", "idempotency_key", "expected_config_hash",
                   "expected_capability_revision"}
        unknown = sorted(str(key) for key in set(request) - allowed)
        if unknown:
            raise InvalidRunRequest("Unknown request fields: " + ", ".join(unknown))
        draft = request.get("draft")
        resolution = resolve_draft(draft)
        if not resolution["valid"]:
            error = InvalidRunRequest("Draft validation failed.")
            error.fields = resolution["errors"]
            raise error
        key = request.get("idempotency_key")
        if not isinstance(key, str) or not key.strip() or len(key) > 200:
            error = InvalidRunRequest("A non-empty idempotency_key of at most 200 characters is required.")
            error.fields = {"idempotency_key": "Provide a non-empty key up to 200 characters."}
            raise error
        expected_hash = request.get("expected_config_hash")
        expected_revision = request.get("expected_capability_revision")
        if not isinstance(expected_hash, str) or not expected_hash:
            error = InvalidRunRequest("expected_config_hash is required.")
            error.fields = {"expected_config_hash": "Submit the validated configuration hash."}
            raise error
        if not isinstance(expected_revision, str) or not expected_revision:
            error = InvalidRunRequest("expected_capability_revision is required.")
            error.fields = {"expected_capability_revision": "Submit the current capability revision."}
            raise error

        canonical = resolution["canonical_config"]
        config_hash = resolution["configuration_hash"]
        revision = resolution["capability_revision"]
        key_hash = _digest(key.strip())
        request_hash = _digest(json.dumps(canonical, sort_keys=True,
                                          separators=(",", ":"), ensure_ascii=False))
        with self._lock:
            existing = self._state["idempotency"].get(key_hash)
            if existing:
                if existing["request_hash"] != request_hash:
                    raise RunConflict("Idempotency key was already used for a different configuration.")
                record = self._state["runs"].get(existing["run_id"])
                if record is None:
                    raise ValueError("Registry idempotency reference is invalid.")
                return self._public(record), False
            if expected_hash != config_hash:
                error = RunConflict("Expected configuration hash is stale.")
                error.fields = {"expected_config_hash": "Revalidate the draft before creating a run."}
                raise error
            if expected_revision != revision:
                error = RunConflict("Capability revision is stale.")
                error.fields = {"expected_capability_revision": "Reload capabilities and revalidate."}
                raise error

        try:
            preview, preview_resolution = preview_draft(draft)
        except PreviewTooLarge as exc:
            raise InvalidRunRequest(str(exc)) from exc
        except Exception as exc:
            error = InvalidRunRequest("The selected scenario could not be previewed.")
            error.fields = {"scenario_id": "Check that the scenario is supported and well formed."}
            raise error from exc
        if (preview is None or preview_resolution["configuration_hash"] != config_hash or
                preview_resolution["capability_revision"] != revision):
            raise RunConflict("Draft changed while it was being resolved; validate again before creating a run.")
        actor_assignments = [
            {"actor": actor["name"], "backend": actor["backend"],
             "source": actor["backend_source"]}
            for actor in preview["cast"]["actors"]
        ]
        if preview["cast"]["truncated"]:
            raise InvalidRunRequest("Resolved cast exceeds the durable assignment limit of 200 actors.")

        with self._lock:
            existing = self._state["idempotency"].get(key_hash)
            if existing:
                if existing["request_hash"] != request_hash:
                    raise RunConflict("Idempotency key was already used for a different configuration.")
                record = self._state["runs"].get(existing["run_id"])
                if record is None:
                    raise ValueError("Registry idempotency reference is invalid.")
                return self._public(record), False
            run_id = "run_" + uuid.uuid4().hex
            now = _utc_now()
            record = {
                "schema_version": 1,
                "id": run_id,
                "name": canonical["name"],
                "scenario_id": canonical["scenario_id"],
                "created_at": now,
                "updated_at": now,
                "status": "created",
                "turn": 0,
                "config_hash": config_hash,
                "capability_revision": revision,
                "config": copy.deepcopy(canonical),
                "resolved_actor_backends": actor_assignments,
                "warnings": list(resolution["warnings"]),
                "error": None,
            }
            self._state["runs"][run_id] = record
            self._state["idempotency"][key_hash] = {
                "request_hash": request_hash, "run_id": run_id,
            }
            try:
                self._persist()
            except Exception:
                del self._state["runs"][run_id]
                del self._state["idempotency"][key_hash]
                raise
            self._runtime[run_id] = _Runtime()
            return self._public(record), True

    def _record(self, run_id: str) -> dict[str, Any]:
        record = self._state["runs"].get(run_id)
        if record is None:
            raise RunNotFound(f"Run {run_id!r} was not found.")
        return record

    def _runtime_for(self, run_id: str) -> _Runtime:
        with self._lock:
            self._record(run_id)
            return self._runtime.setdefault(run_id, _Runtime())

    def _update(self, record: dict[str, Any], **values) -> None:
        previous = copy.deepcopy(record)
        record.update(values)
        record["updated_at"] = _utc_now()
        try:
            self._persist()
        except Exception:
            record.clear()
            record.update(previous)
            raise

    @staticmethod
    def _draft_from_config(config: dict[str, Any]) -> dict[str, Any]:
        return {key: config[key] for key in (
            "scenario_id", "name", "seed", "autonomous", "default_backend",
            "ticks_per_period", "turn_limit")}

    def _assert_config_current(self, record: dict[str, Any]) -> None:
        resolution = resolve_draft(self._draft_from_config(record["config"]))
        if not resolution["valid"]:
            raise RunConflict("Stored run configuration is no longer valid: " +
                              "; ".join(resolution["errors"].values()))
        if resolution["configuration_hash"] != record["config_hash"]:
            raise RunConflict(
                "Configuration identity changed after run creation; refusing to launch a different scenario or build.")
        if resolution["capability_revision"] != record["capability_revision"]:
            raise RunConflict(
                "Capability revision changed after run creation; re-create the run against current capabilities.")

    def _ensure_game(self, runtime: _Runtime, record: dict[str, Any]):
        if runtime.game is None:
            config = record["config"]
            runtime.game = create_game(
                scenario=config["scenario_id"], seed=config["seed"],
                default_backend=config["default_backend"], autonomous=True,
                ticks_per_period=config["ticks_per_period"],
            )
        return runtime.game

    def command(self, run_id: str, command: str) -> dict[str, Any]:
        if command not in {"start", "pause", "resume", "step", "stop"}:
            raise InvalidRunRequest(f"Unknown command {command!r}.")
        runtime = self._runtime_for(run_id)
        # The same lock covers each real game step and every lifecycle command.
        # Pause/stop therefore take effect only after the current turn finishes.
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                state = record["status"]
            if command == "start":
                if state != "created":
                    raise InvalidTransition("Start is accepted only from created.")
                try:
                    self._assert_config_current(record)
                except RunConflict as exc:
                    with self._lock:
                        self._update(record, status="failed", error=str(exc))
                    return self.get_run(run_id)
                with self._lock:
                    self._update(record, status="starting", error=None)
                self._spawn_worker(run_id, runtime)
            elif command == "resume":
                if state != "paused":
                    raise InvalidTransition("Resume is accepted only from paused; waiting runs need input support.")
                with self._lock:
                    self._update(record, status="starting")
                self._spawn_worker(run_id, runtime)
            elif command == "step":
                if state not in {"created", "paused"}:
                    raise InvalidTransition("Step is accepted only from created or paused.")
                if state == "created" and int(record.get("turn", 0)) == 0:
                    try:
                        self._assert_config_current(record)
                    except RunConflict as exc:
                        with self._lock:
                            self._update(record, status="failed", error=str(exc))
                        return self.get_run(run_id)
                try:
                    game = self._ensure_game(runtime, record)
                    outcome = game.step()
                except Exception as exc:
                    with self._lock:
                        self._update(record, status="failed",
                                     error=f"step failed: {type(exc).__name__}: {exc}")
                    return self.get_run(run_id)
                with self._lock:
                    turn = int(game.world._turn)
                    next_state = "waiting" if outcome.get("status") == "waiting" else state
                    if next_state != "waiting" and record["config"].get("turn_limit") is not None and turn >= record["config"]["turn_limit"]:
                        next_state = "completed"
                    self._update(record, status=next_state, turn=turn, error=None)
            elif command in {"pause", "stop"}:
                valid_states = {"running"} if command == "pause" else {"created", "running", "paused", "waiting"}
                if state not in valid_states:
                    raise InvalidTransition(f"{command.title()} is not accepted from {state}.")
                with self._lock:
                    self._update(record, status="paused" if command == "pause" else "stopped")
            return self.get_run(run_id)

    def _spawn_worker(self, run_id: str, runtime: _Runtime) -> None:
        thread = threading.Thread(target=self._worker, args=(run_id, runtime),
                                  name=f"bigville-{run_id}", daemon=True)
        runtime.worker = thread
        thread.start()

    def _worker(self, run_id: str, runtime: _Runtime) -> None:
        try:
            with runtime.lock:
                with self._lock:
                    record = self._record(run_id)
                    if record["status"] != "starting":
                        return
                game = self._ensure_game(runtime, record)
                with self._lock:
                    if record["status"] != "starting":
                        return
                    self._update(record, status="running")
            while True:
                with runtime.lock:
                    with self._lock:
                        record = self._record(run_id)
                        if record["status"] != "running":
                            return
                        game = self._ensure_game(runtime, record)
                    outcome = game.step()
                    with self._lock:
                        turn = int(game.world._turn)
                        if outcome.get("status") == "waiting":
                            self._update(record, status="waiting", turn=turn,
                                         error="Run is waiting for human input, which this phase does not support.")
                            return
                        turn_limit = record["config"].get("turn_limit")
                        next_state = "completed" if turn_limit is not None and turn >= turn_limit else "running"
                        self._update(record, status=next_state, turn=turn, error=None)
                        if next_state == "completed":
                            return
                # Allow commands to contend for the lock between turn boundaries.
                time.sleep(0.01)
        except Exception as exc:
            try:
                with runtime.lock, self._lock:
                    record = self._record(run_id)
                    if record["status"] not in TERMINAL_STATES:
                        self._update(record, status="failed",
                                     error=f"worker failed: {type(exc).__name__}: {exc}")
            except Exception:
                # Persistence failure cannot be repaired in memory; do not mask the worker error.
                return
