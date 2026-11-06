import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from bigville.management.http import API_PREFIX, create_server


@pytest.fixture
def management_server():
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{server.server_address[0]}:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_health_and_catalog_are_real_http_responses(management_server):
    with urlopen(management_server + API_PREFIX + "/health") as response:
        assert response.status == 200
        health = json.load(response)
    with urlopen(management_server + API_PREFIX + "/capabilities") as response:
        assert response.status == 200
        catalog = json.load(response)
    assert health["ready"] is True
    assert health["service"] == "bigville-management"
    assert any(item["id"] == "town100" for item in catalog["scenarios"])


def test_unknown_path_returns_shared_json_error_envelope(management_server):
    with pytest.raises(HTTPError) as caught:
        urlopen(management_server + API_PREFIX + "/unknown")
    assert caught.value.code == 404
    body = json.load(caught.value)
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "localhost"])
def test_server_rejects_non_loopback_or_ambiguous_bind_hosts(host):
    with pytest.raises(ValueError, match="loopback"):
        create_server(host, 0)


def test_server_can_bind_ipv4_or_ipv6_loopback():
    server = create_server("127.0.0.1", 0)
    server.server_close()
    try:
        server = create_server("::1", 0)
    except OSError:
        pytest.skip("IPv6 loopback is unavailable on this host")
    else:
        server.server_close()
