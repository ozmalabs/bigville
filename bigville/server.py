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
from urllib.parse import parse_qs, unquote, urlparse

from .api import create_game
from .backends import ActorResponse


GAME_ROOT = Path(__file__).with_name("game")


class GameService:
    """Own one game session and expose JSON-safe snapshots to a client."""

    def __init__(self, *, scenario: str = "town100", seed: int = 305000,
                 player: str | None = None, mode: str = "referee"):
        if mode not in ("agent", "referee"):
            raise ValueError(f"mode must be 'agent' or 'referee', not {mode!r}")
        if mode == "agent" and player is None:
            raise ValueError("agent mode needs a player: the view is one resident's")
        self.scenario = scenario
        self.seed = seed
        self.player_name = player
        # Phase 052. "agent": /api/state is refused and /api/turn answers with the player's agent view.
        # "referee": the omniscient snapshot, as before.
        self.mode = mode
        self.game = create_game(scenario=scenario, seed=seed, player=player)

    def view(self, actor: str | None = None) -> dict[str, Any]:
        """The agent view (words only) of `actor`, or of the player when no actor is named."""
        name = actor or self.game.player
        if name is None:
            raise ValueError("no player: name an actor")
        return self.game.agent_view(name, mode="agent")

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
        from .reporting import game_report
        return game_report(self.game)

    def _bind_reply(self, reply: Any) -> dict[str, Any]:
        """Phase 057 (agent mode): a reply in the LLM shape, checked against the pack's reply schema and bound to the
        player's own affordance rows by handle, so a client sends words and handles, never the world's params."""
        from .backends import reply_schema
        if not isinstance(reply, dict):
            raise TypeError("reply must be a JSON object")
        pack = self.game.world.data_pack
        errors = reply_schema.check(reply, pack)
        if errors:
            raise ValueError("; ".join(errors))
        return reply_schema.to_wire(reply, pack, affordances=self.game.world.actor_affordances(self.game.player))

    def turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit one human response and advance the shared turn."""
        if self.mode == "agent" and "reaction" in payload:
            # Phase 057: the player's answer to a contested take (Phase 029), delivered to the human backend.
            if self.game._suspended is None:
                raise ValueError("no reaction is pending")
            self.game.backends[self.game.player].submit_reaction(
                ActorResponse(backend_state={"reaction": str(payload["reaction"])}))
        else:
            if self.mode == "agent" and "reply" in payload:
                payload = self._bind_reply(payload["reply"])
            response = ActorResponse.from_dict(payload)
            self.game.submit_player_response(response)
        result = self.game.step()
        if self.mode == "agent":
            result["view"] = self.view()
        else:
            result["state"] = self.state()
        return result

    def free(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Phase 071d: free actions alone (a glance, a note, an answer to a request). They run now, with no slot, no
        tick and no step, so the turn does not advance. The reply may carry only free_actions; a major action or an
        utterance needs /api/turn. Returns the player's agent view after the actions."""
        from . import free_replies
        from .backends import reply_schema
        if self.game.player is None:
            raise ValueError("no player: free actions are the player's")
        extra = sorted(str(key) for key in payload if key != "free_actions")
        if extra:
            raise ValueError(f"a free reply carries only free_actions; {extra[0][:24]!r} needs /api/turn")
        items = payload.get("free_actions")
        if not isinstance(items, list):
            raise ValueError("free_actions must be a list")
        pack = self.game.world.data_pack
        errors = reply_schema.check({"free_actions": items}, pack)
        if errors:
            raise ValueError("; ".join(errors))
        wire = reply_schema.to_wire({"free_actions": items}, pack)
        free_replies.apply_all(self.game, self.game.player, wire["free_actions"])
        return {"status": "free", "view": self.view()}


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
            if self.service.mode == "agent":
                self._json(HTTPStatus.FORBIDDEN, {
                    "error": "the omniscient state is not served in agent mode; use /api/view"})
            else:
                self._json(HTTPStatus.OK, self.service.state())
        elif parsed.path == "/api/view":
            query = parse_qs(parsed.query)
            actor = query.get("actor", [None])[0]
            try:
                self._json(HTTPStatus.OK, self.service.view(actor))
            except KeyError as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
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
            elif parsed.path == "/api/free":
                self._json(HTTPStatus.OK, self.service.free(payload))
            elif parsed.path == "/api/reset":
                type(self).service = GameService(scenario=self.service.scenario,
                                                 seed=self.service.seed,
                                                 player=self.service.player_name,
                                                 mode=self.service.mode)
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
          seed: int = 305000, player: str | None = None, mode: str = "referee"):
    service = GameService(scenario=scenario, seed=seed, player=player, mode=mode)

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
    parser.add_argument("--referee", action="store_true",
                        help="serve the omniscient /api/state even when a player is named")
    args = parser.parse_args(argv)
    # Agent mode is the default when a player is named: the page sees only that resident's view.
    # Without --player the server keeps the omniscient state the Phaser client draws from.
    mode = "agent" if args.player is not None and not args.referee else "referee"
    serve(args.host, args.port, scenario=args.scenario, seed=args.seed, player=args.player, mode=mode)


if __name__ == "__main__":
    main()
