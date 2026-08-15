"""Small standard-library host for the standalone Bigville game.

The browser is only a client.  Every turn is submitted to :class:`BigvilleGame`,
so the same API can later be hosted behind another web framework or a native
client without duplicating simulation rules.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .api import create_game
from .backends import ActorResponse


GAME_ROOT = Path(__file__).with_name("game")


class GameService:
    """Own one game session and expose JSON-safe snapshots to a client."""

    def __init__(self, *, scenario: str = "town100", seed: int = 305000,
                 player: str | None = None):
        self.scenario = scenario
        self.seed = seed
        self.player_name = player
        self.game = create_game(scenario=scenario, seed=seed, player=player)

    def state(self) -> dict[str, Any]:
        snapshot = self.game.snapshot()
        actor = self.game.player
        if actor is not None:
            snapshot["player_context"] = {
                "actor": actor,
                "affordances": self.game.world.actor_affordances(actor),
                "turn_state": self.game.world.actor_turn_state(actor),
                "position": self.game.world.actor_position(actor),
                "inventory": self.game.world.inventory(actor),
                "held_items": self.game.world.held_items(actor),
                "worn": self.game.world.worn(actor),
            }
        return snapshot

    def report(self) -> dict[str, Any]:
        """Return the simulation report without requiring a game turn."""
        return self.game.world.report()

    def turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit one human response and advance the shared turn."""
        response = ActorResponse.from_dict(payload)
        self.game.submit_player_response(response)
        result = self.game.step()
        result["state"] = self.state()
        return result


class BigvilleHandler(BaseHTTPRequestHandler):
    service: GameService

    def _json(self, status: int, value: Any):
        body = json.dumps(value, default=str, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str):
        relative = unquote(path.lstrip("/"))
        if relative in {"", "index.html"}:
            relative = "index.html"
        elif relative.startswith("game/"):
            relative = relative[5:]
        candidate = (GAME_ROOT / relative).resolve()
        if GAME_ROOT not in candidate.parents and candidate != GAME_ROOT:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "schema": "bigville/api/1"})
        elif parsed.path == "/api/state":
            self._json(HTTPStatus.OK, self.service.state())
        elif parsed.path == "/api/report":
            self._json(HTTPStatus.OK, self.service.report())
        else:
            self._static(parsed.path)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise TypeError("request body must be a JSON object")
            if parsed.path == "/api/turn":
                self._json(HTTPStatus.OK, self.service.turn(payload))
            elif parsed.path == "/api/reset":
                type(self).service = GameService(scenario=self.service.scenario,
                                                 seed=self.service.seed,
                                                 player=self.service.player_name)
                self._json(HTTPStatus.OK, self.service.state())
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, TypeError, KeyError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # keep the HTTP process alive for a bad turn
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})

    def log_message(self, format, *args):
        # Keep the game console readable; callers can replace this handler to log.
        return


def serve(host: str = "127.0.0.1", port: int = 8765, *, scenario: str = "town100",
          seed: int = 305000, player: str | None = None):
    service = GameService(scenario=scenario, seed=seed, player=player)

    class Handler(BigvilleHandler):
        pass

    Handler.service = service
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Bigville game running at http://{host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Run the standalone Bigville game")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scenario", default="town100")
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--player", default=None)
    args = parser.parse_args(argv)
    serve(args.host, args.port, scenario=args.scenario, seed=args.seed, player=args.player)


if __name__ == "__main__":
    main()
