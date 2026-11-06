"""Phase 055 live check: one tiny call to OpenCode Go. Never part of the default suite.

It runs only when BIGVILLE_LIVE_LLM=1 and a key is present (in the environment, or in the repository's .env
file, which is read only when the switch is on). The default model is used, which the settings validate.
The test prints nothing of the key and sends one short prompt. Run it with:

    BIGVILLE_LIVE_LLM=1 python3 -m pytest -q -p no:cacheprovider tests/live
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _settings():
    if os.environ.get("BIGVILLE_LIVE_LLM") != "1":
        return None
    from bigville.providers import from_environment
    settings = from_environment(dotenv_path=REPO / ".env")
    return settings if settings.api_key else None


SETTINGS = _settings()


@pytest.mark.skipif(SETTINGS is None,
                    reason="live LLM test: set BIGVILLE_LIVE_LLM=1 and provide OPENCODE_GO_API_KEY")
def test_one_tiny_call_returns_json_from_the_configured_model():
    from bigville.providers import build_provider
    provider = build_provider(SETTINGS)
    reply = provider.complete({"system": 'Reply with exactly the JSON object {"ok": true} and nothing else.',
                               "context": {}}, meta={"actor": "live-check", "turn": 0})
    assert "ok" in reply
    assert provider.calls == 1
    assert provider.cost_reported + provider.cost_unreported == 1
