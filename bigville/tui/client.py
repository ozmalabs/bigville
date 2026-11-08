"""client.py -- how the terminal interface reaches a game (Phase 057).

Two clients, one interface. Both read the agent view and send replies in the shape the world reads
(`ActorResponse.from_dict`). Neither has a method that fetches `/api/state`, and neither has a referee option:

* EmbeddedClient(game, player): an in-process BigvilleGame. The view is `game.agent_view(player)`.
* HttpClient(url, player): `GET /api/view?actor=NAME` and `POST /api/turn`, against a server in agent mode.

Over HTTP the server (agent mode) binds a reply's handles to the player's own affordance rows and delivers a
reaction (Phase 029); the client sends `{"reply": ...}` and `{"reaction": ...}`.
"""
from __future__ import annotations

import json
from urllib import error, parse, request

from bigville.backends import reply_schema
from bigville.backends.protocol import ActorResponse

DEFAULT_TIMEOUT = 10.0


class UnsupportedOverHttp(RuntimeError):
    """The server has no route for this action yet."""


class ClientError(RuntimeError):
    """The server answered with an error; the message is its text."""


class EmbeddedClient:
    """An in-process game. The player is one of its residents, and its backend is human."""

    def __init__(self, game, player):
        if player not in game.characters:
            raise KeyError(f"no resident named {player!r}")
        self._game = game
        self.player = player
        self.pack = game.world.data_pack
        self._builder = None

    def view(self):
        return self._game.agent_view(self.player, mode="agent")

    def packet(self):
        """The prompt packet an LLM resident gets now (Phase 054): the same PromptBuilder, the same context and the
        agent view attached, as LLMBackend._ask builds it for a consult with no reason. Text mode shows it, and
        --show-packet prints it."""
        from bigville.backends.prompts import PromptBuilder
        if self._builder is None:
            self._builder = PromptBuilder(pack=self.pack)
        context = self._game._context(self.player)
        if context.agent_view is None:
            context.agent_view = self._game.agent_view(self.player, mode="agent")
        return self._builder.build(context).as_dict()

    def affordances(self):
        """The world's full affordance rows, which reply_schema.to_wire binds a handle to. In process only."""
        return list(self._game.world.actor_affordances(self.player))

    def submit(self, wire):
        self._game.submit_player_response(ActorResponse.from_dict(wire))
        return self._game.step()

    def send_reply(self, reply):
        """A reply in the LLM shape (handles and words): bound to the world's rows here, then submitted."""
        return self.submit(reply_schema.to_wire(reply, self.pack, affordances=self.affordances()))

    def react(self, choice):
        backend = self._game.backends[self.player]
        backend.submit_reaction(ActorResponse(backend_state={"reaction": choice}))
        return self._game.step()

    def apply_free(self, reply):
        """Phase 071c: a reply with free actions and no major action (a glance, a look at a feeling). The free actions
        are applied now, with no tick and no turn: the world does not wait for this resident. Returns the view."""
        from bigville import free_replies
        wire = reply_schema.to_wire(reply, self.pack, affordances=self.affordances())
        free_replies.apply_all(self._game, self.player, wire.get("free_actions") or [])
        return {"status": "free", "view": self.view()}


class HttpClient:
    """A server in agent mode: /api/view for the view, /api/turn for a reply."""

    def __init__(self, url, player, pack="bigville", timeout=DEFAULT_TIMEOUT):
        self.base = str(url).rstrip("/")
        self.player = player
        self.pack = pack
        self.timeout = timeout

    def _open(self, req):
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except (ValueError, AttributeError):
                message = str(exc)
            raise ClientError(f"server answered {exc.code}: {message}") from None
        except error.URLError as exc:
            raise ClientError(f"cannot reach {self.base}: {exc.reason}") from None

    def view(self):
        query = parse.urlencode({"actor": self.player})
        return self._open(request.Request(f"{self.base}/api/view?{query}", method="GET"))

    def packet(self):
        """Text mode needs the game in process: the packet is built from the resident's context, which the
        server does not publish."""
        raise UnsupportedOverHttp("text mode runs in process; the packet is built from the game, not the server")

    def affordances(self):
        """Over HTTP the client has no world rows. The server binds a handle to its row (send_reply)."""
        return []

    def send_reply(self, reply):
        """A reply in the LLM shape (handles and words). The server checks it and binds the handles."""
        return self.submit({"reply": reply})

    def submit(self, wire):
        body = json.dumps(wire).encode("utf-8")
        req = request.Request(f"{self.base}/api/turn", data=body, method="POST",
                              headers={"Content-Type": "application/json"})
        return self._open(req)

    def react(self, choice):
        return self.submit({"reaction": choice})

    def apply_free(self, reply):
        """Phase 071d: free actions alone, sent to /api/free. They run with no step, so the turn does not advance; the
        server returns the view. The reply is in the LLM shape; the server checks and folds it."""
        body = json.dumps({"free_actions": list(reply.get("free_actions") or [])}).encode("utf-8")
        req = request.Request(f"{self.base}/api/free", data=body, method="POST",
                              headers={"Content-Type": "application/json"})
        return self._open(req)
