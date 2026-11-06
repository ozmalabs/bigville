"""Small loopback-only HTTP surface for management discovery."""
from __future__ import annotations

import argparse
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .catalog import build_capability_catalog

API_PREFIX = "/api/management/v1"


def error_payload(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


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
        if path == f"{API_PREFIX}/health":
            return self._json(200, {"ready": True, "service": "bigville-management",
                                    "schema_version": 1})
        if path == f"{API_PREFIX}/capabilities":
            try:
                return self._json(200, build_capability_catalog())
            except Exception:
                return self._json(500, error_payload(
                    "catalog_unavailable", "Capability catalog could not be built."))
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_POST(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_PUT(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_DELETE(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))

    def do_PATCH(self):
        return self._json(404, error_payload("not_found", "Unknown management API path."))


def create_server(host: str = "127.0.0.1", port: int = 8766) -> ManagementHTTPServer:
    """Create a service bound to a loopback address only."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Management service host must be a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("Management service host must be a loopback IP address")
    server_type = _IPv6ManagementHTTPServer if address.version == 6 else ManagementHTTPServer
    return server_type((str(address), int(port)), _Handler)


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    server = create_server(host, port)
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
    args = parser.parse_args(argv)
    try:
        serve(args.host, args.port)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
