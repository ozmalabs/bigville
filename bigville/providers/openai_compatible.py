"""An OpenAI-compatible chat-completions provider on the standard library (Phase 055, extended in Phase 066).

It sends ``POST {base_url}/chat/completions`` with ``urllib``. It works with any server that speaks the
same protocol, including a local one. No SDK is imported.

What it does, per call:

* Sends the messages it is given (a ``messages`` list in the payload, or the Phase 055 single payload split
  into a system and a user message), ``User-Agent: bigville/<version>``, ``x-opencode-session:
  <run id>-<session>`` (the session is the thread's id from ``meta["session"]``, or the actor's name), and the
  API key as a bearer token. The key never appears in an exception, a log line, or a transcript (``redact``).
* Tries the JSON-mode parameter (``response_format``) first, for each model. A server that rejects it
  gets a retry without it, and the answer is recorded in ``json_mode_status[model]``. Replies are parsed
  by the backend, which also accepts fenced JSON.
* Retries HTTP 429 (honouring ``Retry-After``), HTTP 5xx and network errors with exponential backoff, up to
  ``max_retries``. Other 4xx responses are not retried. ``sleep`` is injectable, so tests do not wait.
* Spaces the start of requests by ``min_interval`` seconds (a simple rate limit, shared by every thread).
* Reads ``usage.opencode.allowance`` as the cost of the call: a number, or a dict with a numeric ``cost``,
  ``used`` or ``spent``.

Phase 066: ``complete`` returns a ``ProviderResult`` (a ``str`` of the reply content). Its ``.result`` is the
whole call: the reasoning fields wherever the response puts them, finish reason, model, response and request
ids, the usage (including reasoning tokens), the cost, the response headers and body (redacted), the retry
history, and the timings. ``last_call`` (per thread) holds the same record for a call that failed.

The provider is thread-safe: the counters are locked, and the per-call figures are thread-local.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .result import CallResult, ProviderResult

CLIENT_VERSION = "0.55.0"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF = 1.0
RETRY_AFTER_CAP = 60.0
SNIPPET_LIMIT = 200
# Response header names that carry a provider's request id (the first one present is used).
REQUEST_ID_HEADERS = ("x-request-id", "request-id", "x-opencode-request-id", "cf-ray")
# Message fields a response may carry its reasoning in, on the message or on the choice.
REASONING_KEYS = ("reasoning_content", "reasoning", "reasoning_details")

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]+", re.IGNORECASE)
_JSON_MODE_REJECTED = re.compile(r"response_format|json_object|json_mode", re.IGNORECASE)
log = logging.getLogger("bigville.providers")


class ProviderError(RuntimeError):
    """A call failed for a reason the backend should count. The message is already redacted."""


class RateLimiter:
    """Spaces request starts at least ``min_interval`` seconds apart. Thread-safe."""

    def __init__(self, min_interval: float = 0.0, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval = max(0.0, float(min_interval))
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> float:
        """Reserve the next start and sleep until it. Returns the delay used."""
        if self.min_interval <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.min_interval
        delay = start - now
        if delay > 0:
            self._sleep(delay)
        return max(0.0, delay)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def allowance_cost(allowance: Any) -> float | None:
    """The cost of one call from ``usage.opencode.allowance``, or None when the response does not say.

    The plan does not document the field's shape, so both a number and a small dict are read. See the
    report's open questions."""
    number = _number(allowance)
    if number is not None:
        return number
    if isinstance(allowance, dict):
        for key in ("cost", "used", "spent"):
            number = _number(allowance.get(key))
            if number is not None:
                return number
    return None


def _split(payload: Any) -> tuple[str | None, str]:
    """(system text, user text). A packet with a ``system`` string is split; anything else is the user text."""
    if isinstance(payload, str):
        return None, payload
    if isinstance(payload, dict) and isinstance(payload.get("system"), str):
        rest = {key: value for key, value in payload.items() if key != "system"}
        return payload["system"], json.dumps(rest, sort_keys=True, ensure_ascii=False, default=str)
    return None, json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def messages_of(payload: Any) -> list[dict[str, str]]:
    """The chat messages for a payload. A payload with a ``messages`` list (a continued thread, Phase 066) is
    sent as given. Any other payload is the Phase 055 form, split into a system and a user message."""
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return [{"role": str(item["role"]), "content": str(item["content"])} for item in payload["messages"]]
    system, user = _split(payload)
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]


def _retry_after(headers: dict[str, str]) -> float | None:
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                return min(max(0.0, float(value)), RETRY_AFTER_CAP)
            except (TypeError, ValueError):
                return None
    return None


def _first(*sources: Any, key: str) -> Any:
    for source in sources:
        if isinstance(source, dict) and source.get(key) not in (None, "", [], {}):
            return source[key]
    return None


class OpenAICompatibleProvider:
    """``complete(payload, meta=None)`` returns a ``ProviderResult``. See the module docstring."""

    wants_meta = True

    def __init__(self, *, base_url: str, api_key: str, model: str, run_id: str = "run",
                 user_agent: str | None = None, max_tokens: int = DEFAULT_MAX_TOKENS,
                 timeout: float = DEFAULT_TIMEOUT, max_retries: int = DEFAULT_MAX_RETRIES,
                 backoff: float = DEFAULT_BACKOFF, min_interval: float = 0.0, json_mode: bool = True,
                 temperature: float | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, logger: logging.Logger | None = None):
        if not model or not isinstance(model, str):
            raise ValueError("model must be a non-empty string")
        self.base_url = str(base_url).rstrip("/")
        self._api_key = str(api_key or "")
        self.model = model
        self.run_id = str(run_id)
        self.user_agent = user_agent or f"bigville/{CLIENT_VERSION}"
        self.max_tokens = int(max_tokens)
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.backoff = max(0.0, float(backoff))
        self.json_mode = bool(json_mode)
        self.temperature = temperature
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, clock=clock, sleep=sleep)
        self._lock = threading.Lock()
        self._local = threading.local()
        self.log = logger or log
        self.json_mode_status: dict[str, str] = {}
        self.calls = 0
        self.retries = 0
        self.total_cost = 0.0
        self.cost_reported = 0
        self.cost_unreported = 0
        self.errors_by_status: dict[str, int] = {}

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(model={self.model!r}, base_url={self.base_url!r})"

    # -- what the caller reads back -------------------------------------------------------
    @property
    def last_cost(self) -> float | None:
        return getattr(self._local, "cost", None)

    @property
    def last_usage(self) -> dict[str, int] | None:
        return getattr(self._local, "usage", None)

    @property
    def last_model(self) -> str | None:
        return getattr(self._local, "model", None)

    @property
    def last_call(self) -> dict[str, Any] | None:
        """The whole record of this thread's last call, redacted: ``ok``, and either the result's fields or
        ``error``, with the retry ``attempts``. None before the first call on this thread."""
        return getattr(self._local, "call", None)

    def capabilities(self) -> dict[str, Any]:
        """Per-model JSON-mode status and the call counters, for the report."""
        with self._lock:
            return {"model": self.model, "json_mode": dict(self.json_mode_status), "calls": self.calls,
                    "retries": self.retries, "total_cost": round(self.total_cost, 6),
                    "cost_reported": self.cost_reported, "cost_unreported": self.cost_unreported,
                    "errors_by_status": dict(self.errors_by_status)}

    def redact(self, text: Any) -> str:
        """Text with the API key and any bearer token removed. Applied to every message this class produces."""
        out = str(text)
        if self._api_key:
            out = out.replace(self._api_key, "[redacted key]")
        return _BEARER.sub("Bearer [redacted]", out)

    def _scrub(self, value: Any) -> Any:
        """A JSON-like value with every string redacted. Nothing else is changed: the log keeps the whole value."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {str(key): self._scrub(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._scrub(item) for item in value]
        return value

    # -- the call -----------------------------------------------------------------------------
    def complete(self, payload: Any, meta: dict[str, Any] | None = None) -> ProviderResult:
        meta = dict(meta or {})
        self._local.cost = None
        self._local.usage = None
        self._local.model = None
        self._local.call = None
        actor = str(meta.get("actor") or "unknown")
        session = f"{self.run_id}-{meta.get('session') or actor}"
        body: dict[str, Any] = {"model": self.model, "messages": messages_of(payload), "max_tokens": self.max_tokens}
        if self.temperature is not None:
            body["temperature"] = float(self.temperature)
        if self.json_mode and self.json_mode_status.get(self.model) != "unsupported":
            body["response_format"] = {"type": "json_object"}
        history: list[dict[str, Any]] = []
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
        started = time.perf_counter()
        request = {"model": self.model, "session": session, "max_tokens": self.max_tokens,
                   "temperature": body.get("temperature"), "response_format": "response_format" in body,
                   "messages": len(body["messages"])}
        try:
            raw, headers = self._request(body, session, actor=actor, history=history)
            return self._parse(raw, headers=headers, request=request, attempts=history, started_at=started_at,
                               latency_ms=(time.perf_counter() - started) * 1000.0)
        except ProviderError as exc:
            self._local.call = {"ok": False, "error": self.redact(exc), "request": self._scrub(request),
                                "attempts": self._scrub(history), "started_at": started_at,
                                "latency_ms": round((time.perf_counter() - started) * 1000.0, 3)}
            raise

    def _send(self, body: dict[str, Any], session: str) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": self.user_agent,
                "x-opencode-session": session,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except OSError:
                raw = b""
            headers = dict(exc.headers.items()) if exc.headers is not None else {}
            return exc.code, headers, raw

    def _request(self, body: dict[str, Any], session: str, *, actor: str,
                 history: list[dict[str, Any]]) -> tuple[bytes, dict[str, str]]:
        """The HTTP exchange with its retries. Each try is appended to ``history`` (status, latency, the delay
        before the next try, and the redacted error text if any)."""
        attempt = 0
        while True:
            self._limiter.wait()
            started = time.perf_counter()
            status: int | None = None
            headers: dict[str, str] = {}
            raw = b""
            network = None
            try:
                status, headers, raw = self._send(body, session)
            except (urllib.error.URLError, OSError) as exc:
                network = f"{type(exc).__name__}: {exc}"
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            with self._lock:
                self.calls += 1
                key = "network" if status is None else str(status)
                if status != 200:
                    self.errors_by_status[key] = self.errors_by_status.get(key, 0) + 1
            entry: dict[str, Any] = {"attempt": attempt, "status": status, "latency_ms": round(elapsed_ms, 3)}
            if network is not None:
                entry["error"] = self.redact(network)
            self.log.info("llm call model=%s session=%s status=%s attempt=%d latency_ms=%.1f",
                          self.model, session, key if status is not None else "network", attempt,
                          elapsed_ms)
            if status == 200 and network is None:
                history.append(entry)
                return raw, headers
            if (status == 400 and "response_format" in body
                    and _JSON_MODE_REJECTED.search(raw.decode("utf-8", "replace"))):
                # Recorded per model: this model does not take the parameter. Not a retry.
                self.json_mode_status[self.model] = "unsupported"
                entry["note"] = "response_format rejected; sent again without it"
                entry["error"] = self.redact(raw.decode("utf-8", "replace"))[:SNIPPET_LIMIT]
                history.append(entry)
                body = {key: value for key, value in body.items() if key != "response_format"}
                continue
            if status is not None and 400 <= status < 500 and status != 429:
                entry["error"] = self._snippet(raw)
                history.append(entry)
                raise ProviderError(self.redact(f"HTTP {status} from the provider: {self._snippet(raw)}"))
            retryable = network is not None or status == 429 or (status is not None and status >= 500)
            if not retryable:
                history.append(entry)
                raise ProviderError(self.redact(f"unexpected HTTP status {status}"))
            if attempt >= self.max_retries:
                history.append(entry)
                what = f"HTTP {status}" if status is not None else self.redact(network or "network error")
                raise ProviderError(self.redact(f"provider failed after {attempt + 1} attempts: {what}"))
            delay = _retry_after(headers) if status == 429 else None
            if delay is None:
                delay = self.backoff * (2 ** attempt)
            entry["delay_s"] = round(float(delay), 3)
            history.append(entry)
            attempt += 1
            with self._lock:
                self.retries += 1
            self._sleep(delay)

    def _snippet(self, raw: bytes) -> str:
        return self.redact(raw.decode("utf-8", "replace").strip())[:SNIPPET_LIMIT]

    def _parse(self, raw: bytes, *, headers: dict[str, str] | None = None, request: dict[str, Any] | None = None,
               attempts: list[dict[str, Any]] | None = None, started_at: str | None = None,
               latency_ms: float = 0.0) -> ProviderResult:
        """The reply as a ProviderResult. Raises ProviderError when the response has no reply text."""
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderError("malformed JSON in the provider's response") from None
        if not isinstance(data, dict):
            raise ProviderError("the provider's response is not a JSON object")
        try:
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("the provider's response has no message content") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("the provider returned an empty reply")
        if self.json_mode and self.json_mode_status.get(self.model) != "unsupported":
            self.json_mode_status[self.model] = "accepted"
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        opencode = usage.get("opencode") if isinstance(usage.get("opencode"), dict) else {}
        cost = allowance_cost(opencode.get("allowance"))
        details = usage.get("completion_tokens_details")
        reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
        if reasoning_tokens is None:
            reasoning_tokens = usage.get("reasoning_tokens")
        tokens = {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens"),
                  "reasoning": reasoning_tokens}
        counts = {key: int(value) for key, value in tokens.items()
                  if isinstance(value, int) and not isinstance(value, bool)}
        header_map = {str(key): self.redact(value) for key, value in (headers or {}).items()}
        lowered = {key.lower(): value for key, value in header_map.items()}
        request_id = next((lowered[name] for name in REQUEST_ID_HEADERS if name in lowered), None)
        model = str(data.get("model") or self.model)
        result = CallResult(
            content=content,
            reasoning_content=self._scrub(_first(message, choice, key="reasoning_content")),
            reasoning=self._scrub(_first(message, choice, key="reasoning")),
            reasoning_details=self._scrub(_first(message, choice, key="reasoning_details")),
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
            model=model,
            response_id=data.get("id") if isinstance(data.get("id"), str) else None,
            request_id=request_id,
            usage=self._scrub(usage),
            cost=cost,
            headers=header_map,
            body=self._scrub(data),
            request=self._scrub(dict(request or {})),
            attempts=self._scrub(list(attempts or [])),
            started_at=started_at,
            latency_ms=round(float(latency_ms), 3),
            json_mode=self.json_mode_status.get(self.model),
        )
        self._local.cost = cost
        self._local.usage = counts
        self._local.model = model
        self._local.call = {"ok": True, **result.to_dict()}
        with self._lock:
            if cost is None:
                self.cost_unreported += 1
            else:
                self.cost_reported += 1
                self.total_cost += cost
        return ProviderResult(result)
