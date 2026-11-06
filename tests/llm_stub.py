"""Test helpers for the Phase 055 LLM tests. Not a test module (no ``test_`` prefix).

``StubServer`` is a loopback HTTP server on 127.0.0.1 with port 0. It imitates the OpenAI-compatible
chat-completions endpoint. A ``script`` callable decides each response from the request, so tests can send
429 with Retry-After, 5xx, malformed JSON, a usage block with ``usage.opencode.allowance``, or a rejection of
``response_format``. The server records every request (path, headers, parsed body). No real network is used.

``FakeProvider`` is an in-process provider for game-level tests. It is thread-safe and can be slowed down.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

REST_REPLY = json.dumps({"major_action": {"action": "rest", "params": {}}, "utterances": []})
VARIED_REPLIES = (
    REST_REPLY,
    json.dumps({"major_action": {"action": "wait", "params": {}}, "utterances": []}),
    json.dumps({"major_action": None, "utterances": [{"text": "Good morning, neighbour."}]}),
)


def varied_reply(payload) -> str:
    """A reply that depends only on the prompt, so the same prompts get the same replies in any order."""
    from bigville.llm_transcript import prompt_hash
    return VARIED_REPLIES[int(prompt_hash(payload)[:8], 16) % len(VARIED_REPLIES)]


def completion(content: str, *, model: str = "glm-5.3-flash", cost: float | None = 0.002,
               reasoning: int = 3) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": 120, "completion_tokens": 40,
                             "completion_tokens_details": {"reasoning_tokens": reasoning}}
    if cost is not None:
        usage["opencode"] = {"allowance": cost, "list_cost": cost}
    return {"id": "stub-1", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": usage}


class StubServer:
    """Use as a context manager. ``base_url`` is the chat endpoint's base (``.../openai/v1``).

    ``script(index, body, headers)`` returns ``(status, headers, body)``: body is bytes or a dict (sent as JSON),
    and headers is a dict. The default answers 200 with a valid completion of ``REST_REPLY``."""

    def __init__(self, script: Callable[[int, dict, dict], tuple] | None = None):
        self.script = script or self._default
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @staticmethod
    def _default(index, body, headers):
        return 200, {}, completion(REST_REPLY, model=body.get("model", "glm-5.3-flash"))

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/openai/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
        return False

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # keep test output quiet
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except ValueError:
                    body = {"_raw": raw.decode("utf-8", "replace")}
                headers = {key: value for key, value in self.headers.items()}
                with server._lock:
                    index = len(server.requests)
                    server.requests.append({"path": self.path, "headers": headers, "body": body})
                status, extra, payload = server.script(index, body, headers)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (extra or {}).items():
                    self.send_header(key, str(value))
                self.end_headers()
                self.wfile.write(data)

        return Handler


class FakeProvider:
    """A thread-safe in-process provider. ``reply`` is a string (or a callable of the payload) that every call
    returns. ``delay`` sleeps each call, to imitate a slow service. ``cost`` is the cost each call reports
    through ``last_cost`` (per thread, as the real provider does). It receives the call metadata."""

    wants_meta = True

    def __init__(self, reply: Any = REST_REPLY, *, delay: float = 0.0, cost: float | None = None,
                 error: BaseException | None = None):
        self.reply = reply
        self.delay = float(delay)
        self.cost = cost
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._local = threading.local()

    @property
    def last_cost(self):
        return getattr(self._local, "cost", None)

    def complete(self, payload, meta=None):
        with self._lock:
            self.calls.append({"payload": payload, "meta": dict(meta or {})})
        if self.delay:
            time.sleep(self.delay)
        self._local.cost = self.cost
        if self.error is not None:
            raise self.error
        return self.reply(payload) if callable(self.reply) else self.reply
