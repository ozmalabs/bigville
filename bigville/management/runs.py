"""Durable local run records and serialized in-process game lifecycle."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..api import create_game
from ..reporting import game_report
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


class RunViewUnavailable(RegistryError):
    code = "snapshot_unavailable"


class CheckpointUnavailable(RegistryError):
    code = "checkpoint_unavailable"


class _Runtime:
    def __init__(self):
        self.lock = threading.RLock()
        self.game = None
        self.worker: threading.Thread | None = None
        self.pending_input: dict[str, Any] | None = None


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
            if (not isinstance(run_id, str) or not re.fullmatch(r"run_[0-9a-f]{32}", run_id) or
                    not isinstance(record, dict) or
                    record.get("schema_version") != 1 or record.get("id") != run_id or
                    record.get("status") not in VALID_STATES or
                    not isinstance(record.get("config"), dict)):
                raise ValueError(f"Run registry contains an invalid record; refusing to overwrite {self.path}")
            checkpoints = record.get("checkpoints", [])
            if not isinstance(checkpoints, list) or any(
                    not isinstance(item, dict) or item.get("schema_version") != 1 or
                    not isinstance(item.get("id"), str) or
                    not re.fullmatch(r"cp_[0-9a-f]{32}", item["id"]) or
                    isinstance(item.get("turn"), bool) or not isinstance(item.get("turn"), int) or
                    item["turn"] < 0 or not isinstance(item.get("config_hash"), str) or
                    not isinstance(item.get("created_at"), str) or
                    not isinstance(item.get("backend_profiles", []), list)
                    for item in checkpoints):
                raise ValueError(f"Run registry contains invalid checkpoint metadata; refusing to overwrite {self.path}")
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

    def get_run_view(self, run_id: str, *, perspective: str,
                     actor: str | None = None) -> dict[str, Any]:
        """Return only the selected server-built perspective for a run."""
        if perspective not in {"referee", "agent"}:
            raise InvalidRunRequest("Perspective must be 'referee' or 'agent'.")
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                game = runtime.game
                run_info = {
                    "id": record["id"], "name": record["name"],
                    "scenario_id": record["scenario_id"],
                    "status": record["status"], "turn": record["turn"],
                    "error": record["error"],
                }
            if game is None:
                raise RunViewUnavailable(
                    f"Run snapshot is unavailable while status is {run_info['status']}; start or step the run first.")
            if perspective == "agent":
                if not isinstance(actor, str) or not actor:
                    raise InvalidRunRequest("An actor is required for an agent view.")
                if (record["config"].get("autonomous") is False and
                        actor != record["config"].get("player")):
                    raise InvalidRunRequest("Only the selected player can receive an agent view for this run.")
                if actor not in game.characters:
                    raise RunNotFound(f"Resident {actor!r} was not found in this run.")
                # Do not call game.snapshot() or serialize world state on this path.
                view = game.agent_view(actor, mode="agent")
                return {"perspective": "agent", "actor": actor,
                        "run": run_info, "view": view}
            snapshot = game.snapshot()
            return {"perspective": "referee", "run": run_info,
                    "snapshot": snapshot}

    def _capture_player_wait(self, runtime: _Runtime, game, outcome: dict[str, Any], record):
        player = record["config"].get("player")
        if not player or outcome.get("actor") != player:
            raise InvalidRunRequest("The game is waiting for input from an actor other than the selected player.")
        reaction = outcome.get("reaction") if game._suspended is not None else None
        runtime.pending_input = {
            "token": uuid.uuid4().hex,
            "turn": int(game.world._turn),
            "actor": player,
            "kind": "reaction" if reaction else "action",
            "reaction": copy.deepcopy(reaction),
        }

    def get_player_prompt(self, run_id: str) -> dict[str, Any]:
        """Return only the selected player's agent view and currently advertised input handles."""
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                game = runtime.game
                if record["config"].get("autonomous") is not False:
                    raise InvalidRunRequest("This run has no human-controlled player.")
                if record["status"] != "waiting" or runtime.pending_input is None:
                    raise RunViewUnavailable("The player prompt is available only while input is waiting.")
                pending = copy.deepcopy(runtime.pending_input)
                run_info = {"id": record["id"], "status": record["status"],
                            "turn": record["turn"]}
            if game is None or pending["actor"] != game.player:
                raise RunViewUnavailable("The player session is unavailable.")
            view = game.agent_view(game.player, mode="agent")
            prompt = {"run": run_info, "actor": game.player,
                      "turn": pending["turn"], "token": pending["token"],
                      "mode": pending["kind"], "view": view}
            if pending["kind"] == "reaction":
                prompt["reactions"] = list((pending.get("reaction") or {}).get("options", []))
            else:
                # Only handles advertised by the filtered agent view are
                # eligible, then they are re-resolved from the current world
                # affordance set when a selection is submitted.
                prompt["actions"] = list(view.get("can", []))
            return prompt

    def submit_player_input(self, run_id: str, payload: Any) -> dict[str, Any]:
        """Submit one affordance handle or offered reaction for the selected player."""
        if (not isinstance(payload, dict) or set(payload) != {"token", "turn", "selection"} or
                not isinstance(payload.get("token"), str) or
                isinstance(payload.get("turn"), bool) or not isinstance(payload.get("turn"), int) or
                not isinstance(payload.get("selection"), str)):
            error = InvalidRunRequest("Player input must include the current token, turn, and selection.")
            error.fields = {"input": "Choose one currently advertised action or reaction."}
            raise error
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                if record["config"].get("autonomous") is not False:
                    raise InvalidRunRequest("This run has no human-controlled player.")
                if record["status"] != "waiting" or runtime.pending_input is None:
                    raise InvalidTransition("Player input is accepted only while the run is waiting.")
                pending = runtime.pending_input
                if (payload["token"] != pending["token"] or payload["turn"] != pending["turn"] or
                        payload["turn"] != record["turn"]):
                    raise RunConflict("Player input is stale; reload the current player prompt.")
                game = runtime.game
                player = record["config"]["player"]
                if game is None or game.player != player:
                    raise RunViewUnavailable("The player session is unavailable.")

            from ..backends.protocol import ActorResponse, ProposedAction
            if pending["kind"] == "reaction":
                options = list((pending.get("reaction") or {}).get("options", []))
                if payload["selection"] not in options:
                    error = InvalidRunRequest("Choose one of the currently offered reaction options.")
                    error.fields = {"selection": "This reaction was not offered for the pending contest."}
                    raise error
                game.backends[player].submit_reaction(
                    ActorResponse(backend_state={"reaction": payload["selection"]}))
            else:
                view = game.agent_view(player, mode="agent")
                advertised = {row["handle"] for row in view.get("can", [])
                              if isinstance(row, dict) and isinstance(row.get("handle"), str)}
                if payload["selection"] not in advertised:
                    error = InvalidRunRequest("Choose an action currently advertised in the player's agent view.")
                    error.fields = {"selection": "This action handle is unavailable or was not advertised."}
                    raise error
                from domains.affordance_handles import handle_pairs
                options = handle_pairs(game.world.actor_affordances(player))
                choice = next((option for handle, option in options
                               if handle == payload["selection"] and handle in advertised), None)
                if choice is None:
                    raise RunConflict("The selected action handle became stale; reload the player prompt.")
                params = {key: value for key, value in choice.items()
                          if key not in {"action", "score", "legal", "reason"}}
                game.submit_player_response(ActorResponse(major_action=ProposedAction(
                    str(choice["action"]), params, "management_human")))
            runtime.pending_input = None
            try:
                outcome = game.step()
                if outcome.get("status") == "advanced":
                    turn = int(game.world._turn)
                    turn_limit = record["config"].get("turn_limit")
                    if turn_limit is not None and turn >= turn_limit:
                        with self._lock:
                            self._update(record, status="completed", turn=turn, error=None)
                        return self.get_run(run_id)
                if outcome.get("status") == "advanced" and game.world.is_alive(player):
                    # The completed turn is now recorded. Ask once for the
                    # next player prompt; the human backend returns waiting
                    # before the world or period advances.
                    outcome = game.step()
                with self._lock:
                    turn = int(game.world._turn)
                    if outcome.get("status") == "waiting" and game.world.is_alive(player):
                        self._capture_player_wait(runtime, game, outcome, record)
                        self._update(record, status="waiting", turn=turn, error=None)
                    elif not game.world.is_alive(player):
                        self._update(record, status="completed", turn=turn,
                                     error="The selected player is no longer alive; the human session ended.")
                    elif outcome.get("status") == "advanced":
                        self._update(record, status="paused", turn=turn, error=None)
                    else:
                        self._update(record, status="failed", turn=turn,
                                     error="The game did not return to a valid human input boundary.")
            except Exception:
                runtime.pending_input = None
                with self._lock:
                    self._update(record, status="failed",
                                 error="Human input could not be applied by the game engine.")
                raise
            return self.get_run(run_id)

    def get_run_report(self, run_id: str) -> dict[str, Any]:
        """Compute a read-only report from the current in-memory run state."""
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                game = runtime.game
                run_info = {"id": record["id"], "name": record["name"],
                            "scenario_id": record["scenario_id"],
                            "status": record["status"], "turn": record["turn"],
                            "error": record["error"]}
            if game is None:
                raise RunViewUnavailable(
                    f"Report is unavailable while status is {run_info['status']}; start or step the run first.")
            report = game_report(game)
            return {"source": "live_snapshot", "captured_at": _utc_now(),
                    "run": run_info, "report": report}

    def get_run_events(self, run_id: str, *, offset: int = 0, limit: int = 50,
                       kind: str | None = None, actor: str | None = None) -> dict[str, Any]:
        """Read recorded world events without recording a report or advancing state."""
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise InvalidRunRequest("offset must be a nonnegative integer.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise InvalidRunRequest("limit must be an integer from 1 to 200.")
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                game = runtime.game
                run_info = {"id": record["id"], "name": record["name"],
                            "scenario_id": record["scenario_id"],
                            "status": record["status"], "turn": record["turn"],
                            "error": record["error"]}
            if game is None:
                raise RunViewUnavailable(
                    f"Events are unavailable while status is {run_info['status']}; start or step the run first.")
            events = [{"id": event_id, **dict(game.world.eng.node(node)["attrs"])}
                      for event_id, node in game.world._events.items()]
            if kind:
                events = [event for event in events
                          if str(event.get("kind", "")).casefold() == kind.casefold()]
            if actor:
                events = [event for event in events
                          if str(event.get("actor", event.get("subject", ""))).casefold() == actor.casefold()]
            total = len(events)
            page = events[offset:offset + limit]
            return {"source": "recorded_history", "run": run_info,
                    "events": page, "pagination": {"offset": offset, "limit": limit,
                        "total": total,
                        "next_offset": offset + len(page) if offset + len(page) < total else None}}

    def create_run(self, request: Any) -> tuple[dict[str, Any], bool]:
        """Return (record, created); key reuse is checked against canonical resolved config."""
        if not isinstance(request, dict):
            raise InvalidRunRequest("Request must be a JSON object.")
        allowed = {"draft", "idempotency_key", "expected_config_hash",
                   "expected_capability_revision", "template"}
        unknown = sorted(str(key) for key in set(request) - allowed)
        if unknown:
            raise InvalidRunRequest("Unknown request fields: " + ", ".join(unknown))
        draft = request.get("draft")
        resolution = resolve_draft(draft, profile_registry=getattr(self, "profile_registry", None))
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
        template_ref = request.get("template")
        template_provenance = None
        if template_ref is not None:
            if (not isinstance(template_ref, dict) or set(template_ref) != {"id", "version"} or
                    not isinstance(template_ref.get("id"), str) or
                    isinstance(template_ref.get("version"), bool) or
                    not isinstance(template_ref.get("version"), int)):
                error = InvalidRunRequest("Template provenance must contain a template ID and integer version.")
                error.fields = {"template": "Load a specific template version before creating this run."}
                raise error
            template_registry = getattr(self, "template_registry", None)
            if template_registry is None:
                raise InvalidRunRequest("Template provenance is unavailable in this service.")
            template_provenance = template_registry.verify_run_source(
                template_ref["id"], template_ref["version"])
        key_hash = _digest(key.strip())
        request_hash = _digest(json.dumps(canonical, sort_keys=True,
                                          separators=(",", ":"), ensure_ascii=False) +
                              json.dumps(template_ref, sort_keys=True,
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
            preview, preview_resolution = preview_draft(
                draft, profile_registry=getattr(self, "profile_registry", None))
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
                "checkpoints": [],
                "config_hash": config_hash,
                "capability_revision": revision,
                "config": copy.deepcopy(canonical),
                "resolved_actor_backends": actor_assignments,
                "resolved_actor_profiles": copy.deepcopy(canonical.get("resolved_actor_profiles", [])),
                "template": ({**template_provenance,
                              "run_configuration_hash": config_hash}
                             if template_provenance else None),
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

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._record(run_id).get("checkpoints", []))

    def create_checkpoint(self, run_id: str) -> dict[str, Any]:
        """Persist a full game checkpoint while holding the per-run turn lock."""
        runtime = self._runtime_for(run_id)
        with runtime.lock:
            with self._lock:
                record = self._record(run_id)
                game = runtime.game
                state = record["status"]
            if state in {"starting", "waiting"}:
                raise CheckpointUnavailable(
                    f"A checkpoint is unavailable while the run is {state}.")
            if game is None:
                raise CheckpointUnavailable(
                    "Step or start this run before creating a checkpoint.")
            from worlds.bigville_world import BigvilleOcelotActor
            provider_minds = [name for name, mind in game.world._actor_minds.items()
                              if type(mind) is not BigvilleOcelotActor]
            if provider_minds:
                raise CheckpointUnavailable(
                    "This run contains provider-owned resident cognition that this service cannot restore; "
                    "no checkpoint was created.")
            from ..backends import DeterministicBackend, HumanBackend, OcelotBackend
            supported_backends = {DeterministicBackend, HumanBackend, OcelotBackend}
            unsupported_backends = sorted({type(backend).__name__
                                           for backend in game.backends.values()
                                           if type(backend) not in supported_backends})
            if unsupported_backends:
                raise CheckpointUnavailable(
                    f"Unsupported backend {', '.join(unsupported_backends)} has no checkpoint adapter; "
                    "no checkpoint was created.")
            # Game persistence intentionally rejects provider-owned/custom cognition
            # state. Do not serialize just the world or imply that a fork is complete.
            checkpoint_id = "cp_" + uuid.uuid4().hex
            artifact_dir = self.data_dir / "checkpoints" / run_id / checkpoint_id
            from ..game_persistence import save_game_checkpoint
            try:
                save_game_checkpoint(game, artifact_dir)
            except Exception as exc:
                shutil.rmtree(artifact_dir, ignore_errors=True)
                raise CheckpointUnavailable(
                    "The game checkpoint adapter rejected or could not write this run's state "
                    f"({type(exc).__name__}); no checkpoint was created.") from exc
            metadata = {
                "schema_version": 1,
                "id": checkpoint_id,
                "created_at": _utc_now(),
                "turn": int(game.world._turn),
                "config_hash": record["config_hash"],
                "backend_profiles": [
                    {"actor": item["actor"], "profile_id": item["profile_id"],
                     "profile_revision": item["profile_revision"], "backend": item["backend"]}
                    for item in record.get("resolved_actor_profiles", [])
                ],
            }
            with self._lock:
                previous = copy.deepcopy(record.get("checkpoints", []))
                record.setdefault("checkpoints", []).append(metadata)
                record["updated_at"] = _utc_now()
                try:
                    self._persist()
                except Exception:
                    record["checkpoints"] = previous
                    shutil.rmtree(artifact_dir, ignore_errors=True)
                    raise
            return copy.deepcopy(metadata)

    def fork_checkpoint(self, run_id: str, checkpoint_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"cp_[0-9a-f]{32}", checkpoint_id or ""):
            raise RunNotFound("Checkpoint was not found.")
        with self._lock:
            parent = self._record(run_id)
            metadata = next((item for item in parent.get("checkpoints", [])
                             if item["id"] == checkpoint_id), None)
            if metadata is None:
                raise RunNotFound("Checkpoint was not found for this run.")
            parent_copy = copy.deepcopy(parent)
        artifact_dir = self.data_dir / "checkpoints" / run_id / checkpoint_id
        from ..game_persistence import load_game_checkpoint
        try:
            game = load_game_checkpoint(artifact_dir)
        except Exception as exc:
            raise CheckpointUnavailable(
                "Checkpoint restoration failed validation or requires an unsupported restore adapter "
                f"({type(exc).__name__}); no fork was created.") from exc
        if metadata["config_hash"] != parent_copy["config_hash"]:
            raise CheckpointUnavailable("Checkpoint configuration identity does not match its source run.")
        child_id = "run_" + uuid.uuid4().hex
        now = _utc_now()
        child = {
            "schema_version": 1, "id": child_id,
            "name": f"{parent_copy['name']} · fork", "scenario_id": parent_copy["scenario_id"],
            "created_at": now, "updated_at": now,
            "status": ("completed" if parent_copy["config"].get("turn_limit") is not None
                       and int(game.world._turn) >= parent_copy["config"]["turn_limit"]
                       else "paused"),
            "turn": int(game.world._turn), "config_hash": parent_copy["config_hash"],
            "capability_revision": parent_copy["capability_revision"],
            "config": copy.deepcopy(parent_copy["config"]),
            "resolved_actor_backends": copy.deepcopy(parent_copy["resolved_actor_backends"]),
            "resolved_actor_profiles": copy.deepcopy(parent_copy.get("resolved_actor_profiles", [])),
            "template": copy.deepcopy(parent_copy.get("template")),
            "warnings": copy.deepcopy(parent_copy.get("warnings", [])), "error": None,
            "checkpoints": [],
            "forked_from": {"run_id": run_id, "checkpoint_id": checkpoint_id,
                            "config_hash": parent_copy["config_hash"],
                            "turn": int(game.world._turn)},
        }
        with self._lock:
            self._state["runs"][child_id] = child
            try:
                self._persist()
            except Exception:
                del self._state["runs"][child_id]
                raise
            runtime = _Runtime()
            runtime.game = game
            self._runtime[child_id] = runtime
        return self._public(child)

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
        fields = (
            "scenario_id", "name", "seed", "autonomous", "default_backend",
            "ticks_per_period", "turn_limit", "default_profile_id", "actor_backend_profiles",
            "cast_generation", "player")
        draft = {key: config[key] for key in fields if key in config}
        draft["physical_subsystems"] = config.get("physical_subsystem_overrides", {})
        return draft

    def _assert_config_current(self, record: dict[str, Any]) -> None:
        resolution = resolve_draft(self._draft_from_config(record["config"]),
                                   profile_registry=getattr(self, "profile_registry", None))
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
            scenario = config["scenario_id"]
            from .cast_generation import materialize_scenario
            scenario = materialize_scenario(scenario, config,
                                            getattr(self, "profile_registry", None))
            profile_registry = getattr(self, "profile_registry", None)
            actor_profiles = {item["actor"]: item["profile_id"]
                              for item in config.get("resolved_actor_profiles", [])}
            has_llm = (config["default_backend"] == "llm" or
                       any(item.get("backend") == "llm"
                           for item in config.get("resolved_actor_profiles", [])))
            backend_factories = {}
            if has_llm:
                def llm_factory(world, character):
                    profile_id = actor_profiles.get(character.character_id,
                                                    config["default_profile_id"])
                    return profile_registry.build_backend(profile_id, world, character)
                backend_factories["llm"] = llm_factory
            runtime.game = create_game(
                scenario=scenario, seed=config["seed"],
                player=config.get("player"),
                default_backend=config["default_backend"],
                autonomous=config["autonomous"],
                ticks_per_period=config["ticks_per_period"],
                backend_factories=backend_factories,
                physical_subsystems=config.get("physical_subsystem_overrides", {}),
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
                    if next_state == "waiting" and record["config"].get("autonomous") is False:
                        self._capture_player_wait(runtime, game, outcome, record)
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
                            if record["config"].get("autonomous") is False:
                                self._capture_player_wait(runtime, game, outcome, record)
                                self._update(record, status="waiting", turn=turn, error=None)
                            else:
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
