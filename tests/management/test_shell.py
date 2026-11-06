import json
import threading
from http.client import HTTPConnection
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from bigville.management import http
from bigville.management.http import API_PREFIX, create_server


@pytest.fixture
def shell_server(monkeypatch):
    fake = {
        "schema_version": 1,
        "engine_build": {"git_commit": "abc123"},
        "scenarios": [{
            "id": "fixture_world", "name": "Fixture World", "source": "authored",
            "type": "authored_world", "source_file": "fixture_world.json",
            "content_hash": "f00d", "physical_subsystems": {"metabolism": True},
        }],
        "backends": [
            {"kind": "simple", "available": True, "reason": None},
            {"kind": "llm", "available": False, "reason": "Provider is not configured."},
        ],
    }
    monkeypatch.setattr(http, "build_capability_catalog", lambda: fake)
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{server.server_address[0]}:{server.server_address[1]}", fake
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_root_serves_semantic_shell_and_existing_game_link(shell_server):
    base, _ = shell_server
    with urlopen(base + "/") as response:
        html = response.read().decode()
        assert response.status == 200
        assert "text/html" in response.headers["Content-Type"]
    assert '<main class="main">' in html
    assert '<nav class="nav" aria-label="Workspace">' in html
    assert 'aria-live="polite"' in html
    assert 'href="http://127.0.0.1:8765/"' in html
    assert 'id="new-run-button"' in html


def test_static_assets_serve_and_traversal_is_rejected(shell_server):
    base, _ = shell_server
    for asset, content_type, marker in [
        ("management.css", "text/css", ".scenario-card"),
        ("management.js", "javascript", "renderScenarios"),
    ]:
        with urlopen(base + "/management/" + asset) as response:
            payload = response.read().decode()
            assert content_type in response.headers["Content-Type"]
            assert marker in payload

    host, port = base.removeprefix("http://").split(":")
    connection = HTTPConnection(host, int(port))
    connection.request("GET", "/management/%2e%2e/%2e%2e/README.md")
    response = connection.getresponse()
    assert response.status == 404
    assert json.loads(response.read())["error"]["code"] == "not_found"
    connection.close()


def test_catalog_response_is_displayable_and_backend_readiness_is_real(shell_server):
    base, fake = shell_server
    with urlopen(base + API_PREFIX + "/capabilities") as response:
        catalog = json.load(response)
    assert catalog == fake
    assert catalog["scenarios"][0]["name"] == "Fixture World"
    unavailable = next(item for item in catalog["backends"] if item["kind"] == "llm")
    assert unavailable["available"] is False
    assert unavailable["reason"] == "Provider is not configured."


def test_old_game_and_unknown_api_routes_are_not_shadowed(shell_server):
    base, _ = shell_server
    with urlopen(base + API_PREFIX + "/runs") as response:
        assert isinstance(json.load(response)["runs"], list)
    with pytest.raises(HTTPError) as caught:
        urlopen(base + API_PREFIX + "/not-a-route")
    assert caught.value.code == 404
    assert json.load(caught.value)["error"]["code"] == "not_found"
