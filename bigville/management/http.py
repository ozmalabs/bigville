"""Small loopback-only HTTP surface for management discovery."""
from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .catalog import build_capability_catalog
from .drafts import MAX_PREVIEW_BYTES, PreviewTooLarge, preview_draft, resolve_draft
from .runs import (InvalidRunRequest, InvalidTransition, RegistryError,
                   RunConflict, RunNotFound, RunRegistry)

API_PREFIX = "/api/management/v1"
STATIC_ROOT = Path(__file__).with_name("static").resolve()
MAX_REQUEST_BYTES = 65_536


def default_data_dir() -> Path:
    configured = os.environ.get("BIGVILLE_MANAGEMENT_DATA_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".local/share/bigville-management"


def error_payload(code: str, message: str,
                  fields: dict[str, Any] | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


class ManagementHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _IPv6ManagementHTTPServer(ManagementHTTPServer):
    address_family = 10  # socket.AF_INET6


class _Handler(BaseHTTPRequestHandler):
    server_version = "BigvilleManagement/1"

    def log_message(self, fmt, *args):
        # Local service avoids writing request data to stdout by default.
        return

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self._static(STATIC_ROOT / "index.html")
        if path.startswith("/management/"):
            relative = unquote(path.removeprefix("/management/"))
            candidate = (STATIC_ROOT / relative).resolve()
            if not candidate.is_relative_to(STATIC_ROOT):
                return self._json(404, error_payload("not_found", "Unknown management path."))
            return self._static(candidate)
        if path == f"{API_PREFIX}/health":
            return self._json(200, {"ready": True, "service": "bigville-management",
                                    "schema_version": 1})
        if path == f"{API_PREFIX}/capabilities":
            try:
                return self._json(200, build_capability_catalog())
            except Exception:
                return self._json(500, error_payload(
                    "catalog_unavailable", "Capability catalog could not be built."))
        if path == f"{API_PREFIX}/runs":
            return self._json(200, {"runs": self.server.run_registry.list_runs()})
        if path.startswith(f"{API_PREFIX}/runs/"):
            run_id = path.removeprefix(f"{API_PREFIX}/runs/")
            if not run_id or "/" in run_id:
                return self._json(404, error_payload("not_found", "Unknown management API path."))
            try:
                return self._json(200, self.server.run_registry.get_run(run_id))
            except RunNotFound as exc:
                return self._json(404, error_payload(exc.code, str(exc)))
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def _static(self, path: Path):
        try:
            encoded = path.read_bytes()
        except (OSError, ValueError):
            return self._json(404, error_payload("not_found", "Unknown management asset."))
        self.send_response(200)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type += "; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {f"{API_PREFIX}/run-drafts/validate",
                        f"{API_PREFIX}/run-drafts/preview",
                        f"{API_PREFIX}/runs"} and not (
                            path.startswith(f"{API_PREFIX}/runs/") and
                            path.endswith("/commands") and
                            path.count("/") == len(API_PREFIX.strip("/").split("/")) + 3):
            return self._json(404, error_payload("not_found", "Unknown management API path."))
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self._json(400, error_payload("invalid_request", "Invalid Content-Length."))
        if length < 0:
            return self._json(411, error_payload("length_required", "Content-Length is required."))
        if length > MAX_REQUEST_BYTES:
            return self._json(413, error_payload("request_too_large", "Draft request exceeds 64 KB."))
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, error_payload("invalid_json", "Request body must be valid JSON."))

        if path == f"{API_PREFIX}/runs":
            try:
                record, created = self.server.run_registry.create_run(payload)
            except InvalidRunRequest as exc:
                return self._json(422, error_payload(
                    exc.code, str(exc), getattr(exc, "fields", None)))
            except RunConflict as exc:
                return self._json(409, error_payload(
                    exc.code, str(exc), getattr(exc, "fields", None)))
            except Exception:
                return self._json(500, error_payload(
                    "run_creation_failed", "Run creation could not be completed."))
            status = 201 if created else 200
            return self._json(status, record)

        if path.startswith(f"{API_PREFIX}/runs/") and path.endswith("/commands"):
            run_id = path.removeprefix(f"{API_PREFIX}/runs/").removesuffix("/commands")
            if not run_id or "/" in run_id:
                return self._json(404, error_payload("not_found", "Unknown management API path."))
            if not isinstance(payload, dict) or set(payload) != {"command"} or not isinstance(payload.get("command"), str):
                return self._json(400, error_payload("invalid_request", "Command body must contain only a string 'command'."))
            try:
                return self._json(200, self.server.run_registry.command(run_id, payload["command"]))
            except RunNotFound as exc:
                return self._json(404, error_payload(exc.code, str(exc)))
            except InvalidTransition as exc:
                return self._json(409, error_payload(exc.code, str(exc)))
            except InvalidRunRequest as exc:
                return self._json(400, error_payload(exc.code, str(exc)))
            except RegistryError as exc:
                return self._json(409, error_payload(exc.code, str(exc)))

        if path.endswith("/validate"):
            try:
                resolution = resolve_draft(payload)
            except Exception:
                return self._json(500, error_payload(
                    "validation_failed", "Draft validation could not be completed."))
            return self._json(200, resolution)

        try:
            preview, resolution = preview_draft(payload)
        except PreviewTooLarge as exc:
            return self._json(413, error_payload("preview_too_large", str(exc)))
        except Exception:
            return self._json(422, {
                **error_payload("preview_failed", "The selected scenario could not be previewed.",
                                {"scenario_id": "Check that the scenario is supported and well formed."}),
            })
        if preview is None:
            return self._json(422, {
                **error_payload("invalid_draft", "Draft validation failed.", resolution["errors"]),
            })
        encoded_size = len(json.dumps(preview, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8"))
        if encoded_size > MAX_PREVIEW_BYTES:
            return self._json(413, error_payload("preview_too_large", "Preview response exceeds 1 MB."))
        return self._json(200, preview)

    def do_PUT(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_DELETE(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_PATCH(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))


def create_server(host: str = "127.0.0.1", port: int = 8766,
                  data_dir: str | Path | None = None) -> ManagementHTTPServer:
    """Create a service bound to a loopback address only."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Management service host must be a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("Management service host must be a loopback IP address")
    server_type = _IPv6ManagementHTTPServer if address.version == 6 else ManagementHTTPServer
    registry = RunRegistry(data_dir if data_dir is not None else default_data_dir())
    server = server_type((str(address), int(port)), _Handler)
    server.run_registry = registry
    return server


def serve(host: str = "127.0.0.1", port: int = 8766,
          data_dir: str | Path | None = None) -> None:
    server = create_server(host, port, data_dir)
    print(f"Bigville management ready at http://{server.server_address[0]}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Bigville management discovery service")
    parser.add_argument("--host", default="127.0.0.1", help="loopback bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data-dir", help="local registry directory (default: BIGVILLE_MANAGEMENT_DATA_DIR or ~/.local/share/bigville-management)")
    args = parser.parse_args(argv)
    try:
        serve(args.host, args.port, args.data_dir)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
