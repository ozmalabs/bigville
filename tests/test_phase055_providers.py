"""Phase 055: the stdlib OpenAI-compatible provider, the OpenCode Go settings, and the .env reader.

Every HTTP call goes to the loopback stub (tests/llm_stub.py) on 127.0.0.1 with port 0. No test reads the
repository's .env: the .env tests write their own temporary files. Sleeps are recorded, never performed."""
from __future__ import annotations

import json
import logging
import socket
from pathlib import Path

import pytest

from bigville.providers import (ConfigError, OpenAICompatibleProvider, ProviderError, RateLimiter,
                                allowance_cost, build_provider, build_transport, from_environment,
                                load_dotenv, parse_dotenv, validate_base_url, validate_model)
from bigville.providers.openai_compatible import CLIENT_VERSION
from llm_stub import REST_REPLY, StubServer, completion

FAKE_KEY = "sk-test-0123456789abcdefghijklmnopqrstuvwxyz"
PAYLOAD = {"schema": "bigville/prompt/3", "system": "Reply with JSON.", "context": {"public": {"now": "dawn"}}}


def _provider(stub, *, sleep=None, **overrides):
    recorded = []
    options = dict(base_url=stub.base_url, api_key=FAKE_KEY, model="glm-5.3-flash", run_id="run55",
                   sleep=sleep or recorded.append, backoff=1.0)
    options.update(overrides)
    return OpenAICompatibleProvider(**options), recorded


def _headers(request):
    return {key.lower(): value for key, value in request["headers"].items()}


# -- the request ----------------------------------------------------------------------------------

def test_a_request_carries_the_user_agent_session_key_and_the_plan_defaults():
    with StubServer() as stub:
        provider, _ = _provider(stub)
        reply = provider.complete(PAYLOAD, meta={"actor": "Ada Lovelace", "turn": 3, "attempt": 0})
    assert json.loads(reply) == json.loads(REST_REPLY)
    request = stub.requests[0]
    headers = _headers(request)
    assert request["path"] == "/openai/v1/chat/completions"
    assert headers["user-agent"] == f"bigville/{CLIENT_VERSION}"
    assert headers["x-opencode-session"] == "run55-Ada Lovelace"
    assert headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = request["body"]
    assert body["model"] == "glm-5.3-flash"
    assert body["max_tokens"] == 4096
    assert body["messages"][0] == {"role": "system", "content": "Reply with JSON."}
    assert body["messages"][1]["role"] == "user"
    assert json.loads(body["messages"][1]["content"]) == {"context": {"public": {"now": "dawn"}}, "schema": "bigville/prompt/3"}
    assert body["response_format"] == {"type": "json_object"}


def test_the_json_mode_rejection_is_recorded_per_model_and_the_retry_drops_the_parameter():
    def script(index, body, headers):
        if "response_format" in body:
            return 400, {}, {"error": {"message": "response_format is not supported by this model"}}
        return 200, {}, completion(REST_REPLY)

    with StubServer(script) as stub:
        provider, sleeps = _provider(stub)
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert provider.json_mode_status == {"glm-5.3-flash": "unsupported"}
    sent = [("response_format" in request["body"]) for request in stub.requests]
    assert sent == [True, False, False]          # tried once, then not again for this model
    assert sleeps == []                          # the parameter's rejection is not a retry
    assert provider.capabilities()["json_mode"] == {"glm-5.3-flash": "unsupported"}


def test_a_429_waits_for_retry_after_then_succeeds():
    def script(index, body, headers):
        if index == 0:
            return 429, {"Retry-After": "2"}, {"error": "slow down"}
        return 200, {}, completion(REST_REPLY)

    with StubServer(script) as stub:
        provider, sleeps = _provider(stub)
        assert json.loads(provider.complete(PAYLOAD, meta={"actor": "Ada"}))
    assert sleeps == [2.0]
    assert provider.retries == 1
    assert len(stub.requests) == 2


def test_a_server_error_backs_off_exponentially_and_then_fails_without_the_key():
    with StubServer(lambda i, b, h: (503, {}, {"error": "overloaded"})) as stub:
        provider, sleeps = _provider(stub, max_retries=2)
        with pytest.raises(ProviderError) as info:
            provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert sleeps == [1.0, 2.0]
    assert len(stub.requests) == 3
    assert "503" in str(info.value) and FAKE_KEY not in str(info.value)


def test_a_malformed_json_body_is_a_provider_error_and_is_not_retried():
    with StubServer(lambda i, b, h: (200, {}, b"{not json")) as stub:
        provider, sleeps = _provider(stub)
        with pytest.raises(ProviderError, match="malformed JSON"):
            provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert len(stub.requests) == 1 and sleeps == []


def test_a_client_error_is_not_retried_and_an_echoed_key_is_redacted():
    def script(index, body, headers):
        return 401, {}, {"error": f"bad token: Bearer {FAKE_KEY}"}

    with StubServer(script) as stub:
        provider, sleeps = _provider(stub)
        with pytest.raises(ProviderError) as info:
            provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert len(stub.requests) == 1 and sleeps == []
    text = str(info.value)
    assert "HTTP 401" in text and FAKE_KEY not in text and "[redacted" in text


def test_a_timeout_is_a_retryable_failure():
    import time as _time

    def script(index, body, headers):
        _time.sleep(0.4)
        return 200, {}, completion(REST_REPLY)

    with StubServer(script) as stub:
        provider, sleeps = _provider(stub, timeout=0.05, max_retries=1)
        with pytest.raises(ProviderError, match="2 attempts"):
            provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert len(sleeps) == 1


def test_a_refused_connection_is_retried_and_redacted():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()                                  # nothing listens on this port now
    provider = OpenAICompatibleProvider(base_url=f"http://127.0.0.1:{port}/openai/v1", api_key=FAKE_KEY,
                                        model="glm-5.3-flash", max_retries=1, sleep=lambda s: None)
    with pytest.raises(ProviderError) as info:
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert FAKE_KEY not in str(info.value)
    assert provider.errors_by_status == {"network": 2}


def test_the_allowance_is_the_cost_of_each_call_and_the_spend_is_summed():
    replies = iter([completion(REST_REPLY, cost=0.002), completion(REST_REPLY, cost=0.003)])
    with StubServer(lambda i, b, h: (200, {}, next(replies))) as stub:
        provider, _ = _provider(stub)
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
        assert provider.last_cost == pytest.approx(0.002)
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
        assert provider.last_cost == pytest.approx(0.003)
        assert provider.total_cost == pytest.approx(0.005)
        assert provider.last_usage == {"input": 120, "output": 40, "reasoning": 3}


def test_a_reply_without_an_allowance_has_no_cost_and_is_counted():
    with StubServer(lambda i, b, h: (200, {}, completion(REST_REPLY, cost=None))) as stub:
        provider, _ = _provider(stub)
        provider.complete(PAYLOAD, meta={"actor": "Ada"})
    assert provider.last_cost is None
    assert provider.cost_unreported == 1 and provider.cost_reported == 0


def test_allowance_shapes_that_are_read_and_those_that_are_not():
    assert allowance_cost(0.25) == 0.25
    assert allowance_cost({"cost": 0.4}) == 0.4
    assert allowance_cost({"remaining": 9}) is None
    assert allowance_cost(True) is None
    assert allowance_cost(None) is None


def test_the_rate_limiter_spaces_request_starts_on_an_injected_clock():
    waits = []
    now = [100.0]
    limiter = RateLimiter(0.5, clock=lambda: now[0], sleep=waits.append)
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert waits == [0.5, 1.0]


# -- secrets -----------------------------------------------------------------------------------

def test_the_key_is_not_in_the_repr_of_the_settings_or_the_provider():
    settings = from_environment({"OPENCODE_GO_API_KEY": FAKE_KEY})
    assert FAKE_KEY not in repr(settings)
    provider = OpenAICompatibleProvider(base_url="http://127.0.0.1:9/openai/v1", api_key=FAKE_KEY, model="m")
    assert FAKE_KEY not in repr(provider)


# -- the .env reader ----------------------------------------------------------------------------

def test_parse_dotenv_reads_plain_quoted_exported_and_commented_lines():
    text = "\n".join([
        "# a comment",
        "",
        "OPENCODE_GO_API_KEY=\"sk-quoted\"",
        "export OPENCODE_GO_MODEL=glm-5.3-flash  # the cheap one",
        "BIGVILLE_LLM_BUDGET='2.5'",
        "not a setting line",
        "1BAD=value",
    ])
    assert parse_dotenv(text) == {"OPENCODE_GO_API_KEY": "sk-quoted", "OPENCODE_GO_MODEL": "glm-5.3-flash",
                                  "BIGVILLE_LLM_BUDGET": "2.5"}


def test_load_dotenv_fills_only_unset_variables_from_a_temporary_file(tmp_path):
    file = tmp_path / "test.env"
    file.write_text("OPENCODE_GO_API_KEY=sk-from-file\nBIGVILLE_LLM_CONCURRENCY=2\n", encoding="utf-8")
    env = {"OPENCODE_GO_API_KEY": "sk-already-set"}
    applied = load_dotenv(file, env)
    assert env == {"OPENCODE_GO_API_KEY": "sk-already-set", "BIGVILLE_LLM_CONCURRENCY": "2"}
    assert applied == ["BIGVILLE_LLM_CONCURRENCY"]
    assert load_dotenv(tmp_path / "missing.env", env) == []


def test_from_environment_reads_a_named_env_file_and_only_then(tmp_path):
    file = tmp_path / "named.env"
    file.write_text('OPENCODE_GO_API_KEY="sk-named-file"\nOPENCODE_GO_MODEL=glm-5.3-flash\n', encoding="utf-8")
    assert from_environment({}).api_key == ""                      # no file named, nothing read
    settings = from_environment({}, dotenv_path=file)
    assert settings.api_key == "sk-named-file" and settings.model == "glm-5.3-flash"


def test_the_providers_do_not_import_python_dotenv():
    root = Path(__file__).resolve().parent.parent / "bigville" / "providers"
    for source in root.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "import dotenv" not in text and "from dotenv" not in text


# -- settings and refusals ------------------------------------------------------------------------

def test_the_defaults_are_the_plans_values():
    settings = from_environment({"OPENCODE_GO_API_KEY": FAKE_KEY})
    assert settings.base_url == "https://opencode.ai/inference/go/openai/v1"
    assert settings.model == "glm-5.3-flash"
    assert settings.max_tokens == 4096
    assert settings.concurrency == 4
    assert settings.budget is None and settings.transcript is None and settings.replay is None


def test_contributor_models_are_refused_by_name_whatever_the_case():
    for name in ("some-Contributor-model", "iceman-contributor-free", "CONTRIBUTOR"):
        with pytest.raises(ConfigError, match="trained on prompts"):
            validate_model(name)
        with pytest.raises(ConfigError):
            from_environment({"OPENCODE_GO_MODEL": name})
    assert validate_model("glm-5.3-flash") == "glm-5.3-flash"


def test_the_base_url_must_be_https_or_a_loopback_http_address():
    assert validate_base_url("https://opencode.ai/inference/go/openai/v1")
    assert validate_base_url("http://127.0.0.1:8000/v1")
    for bad in ("http://example.com/v1", "ftp://127.0.0.1/v1", "https:///v1"):
        with pytest.raises(ConfigError):
            validate_base_url(bad)


def test_numbers_from_the_environment_are_checked():
    with pytest.raises(ConfigError):
        from_environment({"BIGVILLE_LLM_BUDGET": "lots"})
    with pytest.raises(ConfigError):
        from_environment({"BIGVILLE_LLM_CONCURRENCY": "0"})
    assert from_environment({"BIGVILLE_LLM_BUDGET": "3"}).budget == 3.0


def test_a_provider_is_not_built_without_a_key_but_a_replay_needs_none(tmp_path):
    settings = from_environment({})
    with pytest.raises(ConfigError, match="OPENCODE_GO_API_KEY is not set"):
        build_provider(settings)
    recorded = tmp_path / "run.jsonl"
    recorded.write_text("", encoding="utf-8")
    replay = build_transport(from_environment({"BIGVILLE_LLM_REPLAY": str(recorded)}), None)
    assert replay.__class__.__name__ == "ReplayProvider"


def test_the_environment_budget_and_concurrency_reach_the_town():
    from bigville.llm_scenario import build_llm_town
    from domains.autopilot import table
    settings = from_environment({"OPENCODE_GO_API_KEY": FAKE_KEY, "BIGVILLE_LLM_BUDGET": "0.5",
                                 "BIGVILLE_LLM_CONCURRENCY": "2"})
    game = build_llm_town(object(), llm_residents=2, settings=settings)
    for name in game.llm_residents:
        assert game.backends[name].budget.max_spend == 0.5
        assert game.backends[name].budget.max_calls_per_day == table()["max_calls_per_resident_per_day"]
        assert game.backends[name].concurrency == 2
