"""OpenCode Go settings from the environment, and the provider and budget they build (Phase 055).

Configuration is operational (a key, a URL, a model, limits), not world data, so it lives in the
environment and in this module rather than in the pack. The variables:

    OPENCODE_GO_API_KEY         the key (required to call the service; never printed)
    OPENCODE_GO_BASE_URL        default https://opencode.ai/inference/go/openai/v1
    OPENCODE_GO_MODEL           default glm-5.3-flash
    BIGVILLE_LLM_BUDGET         a spend cap, in the allowance's unit (default: none, see the report)
    BIGVILLE_LLM_CONCURRENCY    simultaneous decisions (default 4)
    BIGVILLE_LLM_MAX_TOKENS     default 4096, which covers reasoning tokens plus a JSON reply
    BIGVILLE_LLM_TIMEOUT        seconds per request (default 60)
    BIGVILLE_LLM_MAX_RETRIES    default 3
    BIGVILLE_LLM_MIN_INTERVAL   seconds between request starts (default 0.25)
    BIGVILLE_LLM_RUN_ID         the session prefix (default: random per process)
    BIGVILLE_LLM_TRANSCRIPT     a JSONL path to append every call to
    BIGVILLE_LLM_REPLAY         a JSONL path to replay instead of calling the service

A ``.env`` file is read only when a caller names one (``dotenv_path``); it fills unset variables only.

Model choice: a model whose name contains "contributor" is refused. The plan (Programme D's development
note) says these models are trained on prompts, and the plan asks to avoid them and never default to one.
The check is by name because that is the only marker the plan records.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from ..backends.autopilot import CallBudget
from domains.autopilot import DEFAULT_PACK, table
from .dotenv import load_dotenv
from .openai_compatible import (DEFAULT_BACKOFF, DEFAULT_MAX_RETRIES, DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT,
                                OpenAICompatibleProvider)

DEFAULT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"
DEFAULT_MODEL = "glm-5.3-flash"
DEFAULT_CONCURRENCY = 4
DEFAULT_MIN_INTERVAL = 0.25
CONTRIBUTOR = re.compile(r"contributor", re.IGNORECASE)
MODEL_NAME = re.compile(r"[A-Za-z0-9._:/\-]+")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ConfigError(ValueError):
    """Configuration that cannot be used. The message never contains the key."""


def validate_model(model: str) -> str:
    if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
        raise ConfigError("the model name is empty or has characters a model name does not use")
    if CONTRIBUTOR.search(model):
        raise ConfigError(f"model {model!r} is a Contributor model, which is trained on prompts; "
                          "choose another model (the plan asks to avoid these)")
    return model


def validate_base_url(url: str) -> str:
    """HTTPS, or plain HTTP to a loopback host (the tests' stub server and a local server). Anything else is
    refused, so a key is never sent in clear text to another host."""
    parts = urlsplit(url)
    if not parts.hostname:
        raise ConfigError("the base URL has no host")
    if parts.scheme == "https":
        return url
    if parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS:
        return url
    raise ConfigError("the base URL must use https (plain http is allowed for loopback hosts only)")


def _int(environ: dict[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number") from None
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def _float(environ: dict[str, str], name: str, default: float | None, low: float) -> float | None:
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if value < low:
        raise ConfigError(f"{name} must be at least {low}")
    return value


@dataclass(frozen=True)
class OpenCodeGoSettings:
    api_key: str = field(repr=False)
    base_url: str
    model: str
    run_id: str
    max_tokens: int
    timeout: float
    max_retries: int
    min_interval: float
    concurrency: int
    budget: float | None
    transcript: str | None
    replay: str | None


def from_environment(environ: dict[str, str] | None = None, *, dotenv_path: str | os.PathLike | None = None
                     ) -> OpenCodeGoSettings:
    """Settings from ``environ`` (a copy of ``os.environ`` by default), after an optional ``.env`` file has filled
    the variables it sets. Nothing is read from disk unless ``dotenv_path`` is given."""
    env = dict(os.environ if environ is None else environ)
    if dotenv_path is not None:
        load_dotenv(dotenv_path, env)
    base_url = validate_base_url(env.get("OPENCODE_GO_BASE_URL") or DEFAULT_BASE_URL)
    model = validate_model(env.get("OPENCODE_GO_MODEL") or DEFAULT_MODEL)
    budget = _float(env, "BIGVILLE_LLM_BUDGET", None, 0.0)
    return OpenCodeGoSettings(
        api_key=env.get("OPENCODE_GO_API_KEY", ""),
        base_url=base_url,
        model=model,
        run_id=env.get("BIGVILLE_LLM_RUN_ID") or uuid.uuid4().hex[:12],
        max_tokens=_int(env, "BIGVILLE_LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS, 256, 65536),
        timeout=_float(env, "BIGVILLE_LLM_TIMEOUT", DEFAULT_TIMEOUT, 0.1) or DEFAULT_TIMEOUT,
        max_retries=_int(env, "BIGVILLE_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES, 0, 10),
        min_interval=_float(env, "BIGVILLE_LLM_MIN_INTERVAL", DEFAULT_MIN_INTERVAL, 0.0) or 0.0,
        concurrency=_int(env, "BIGVILLE_LLM_CONCURRENCY", DEFAULT_CONCURRENCY, 1, 16),
        budget=budget,
        transcript=env.get("BIGVILLE_LLM_TRANSCRIPT") or None,
        replay=env.get("BIGVILLE_LLM_REPLAY") or None,
    )


def build_provider(settings: OpenCodeGoSettings, *, sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic) -> OpenAICompatibleProvider:
    """The HTTP provider for these settings. Refuses to build without a key."""
    if not settings.api_key:
        raise ConfigError("OPENCODE_GO_API_KEY is not set (in the environment, or in the .env file that was named)")
    return OpenAICompatibleProvider(
        base_url=settings.base_url, api_key=settings.api_key, model=settings.model, run_id=settings.run_id,
        max_tokens=settings.max_tokens, timeout=settings.timeout, max_retries=settings.max_retries,
        backoff=DEFAULT_BACKOFF, min_interval=settings.min_interval, sleep=sleep, clock=clock)


def build_budget(settings: OpenCodeGoSettings, pack: str = DEFAULT_PACK) -> CallBudget:
    """The call budget: the pack's calls per resident per day, and the spend cap from BIGVILLE_LLM_BUDGET."""
    return CallBudget(max_calls_per_day=table(pack)["max_calls_per_resident_per_day"],
                      max_spend=settings.budget)


def build_transport(settings: OpenCodeGoSettings, provider: Any) -> Any:
    """The provider the backends call: the replay of a recorded run, the HTTP provider wrapped so that every call
    is written to the transcript, or the HTTP provider alone. A replay needs no key."""
    from ..llm_transcript import RecordingProvider, ReplayProvider, Transcript
    if settings.replay:
        return ReplayProvider(settings.replay)
    if settings.transcript:
        transcript = Transcript(settings.transcript, run_id=settings.run_id, redact=provider.redact)
        return RecordingProvider(provider, transcript)
    return provider
