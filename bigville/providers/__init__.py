"""Optional LLM providers (Phase 055). Standard library only; the core does not import this package.

    from bigville.providers import from_environment, build_provider, build_transport

Modules: ``openai_compatible`` (the HTTP client), ``opencode_go`` (settings from the environment, the
Contributor check, the transport), and ``dotenv`` (the ``.env`` reader).
"""
from .dotenv import load_dotenv, parse_dotenv
from .openai_compatible import OpenAICompatibleProvider, ProviderError, RateLimiter, allowance_cost
from .opencode_go import (ConfigError, OpenCodeGoSettings, build_budget, build_provider, build_transport,
                          from_environment, validate_base_url, validate_model)
from .result import CallResult, ProviderResult

__all__ = [
    "CallResult", "ConfigError", "OpenAICompatibleProvider", "OpenCodeGoSettings", "ProviderError",
    "ProviderResult", "RateLimiter", "allowance_cost", "build_budget", "build_provider", "build_transport",
    "from_environment", "load_dotenv", "parse_dotenv", "validate_base_url", "validate_model",
]
