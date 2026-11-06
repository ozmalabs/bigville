import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bigville.management import drafts, http
from bigville.management.drafts import preview_draft, resolve_draft
from bigville.management.http import API_PREFIX, create_server


@pytest.fixture
def authored_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    scenario_root = tmp_path / "scenarios"
    scenario_root.mkdir()
    definition = {
        "id": "draft_fixture", "name": "Draft Fixture",
        "map": {
            "grid": [
                ["wall", "wall", "wall", "wall", "wall"],
                ["wall", "floor", "floor", "floor", "wall"],
                ["wall", "floor", "floor", "floor", "wall"],
                ["wall", "floor", "floor", "floor", "wall"],
                ["wall", "wall", "wall", "wall", "wall"],
            ],
            "layout": {"w": 5, "h": 5, "homes": [[2, 2]]},
        },
        "actors": [{"name": "Ada", "role": "hand", "backend": "cheap",
                    "home_cell": [2, 2]}],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False},
    }
    (scenario_root / "draft_fixture.json").write_text(json.dumps(definition))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", scenario_root)
    return definition


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


def draft(**updates):
    value = {
        "scenario_id": "draft_fixture", "name": "Morning test", "seed": 27,
        "autonomous": True, "default_backend": "simple",
        "ticks_per_period": "world", "turn_limit": 12,
    }
    value.update(updates)
    return value


def post(base, route, payload):
    request = Request(
        base + API_PREFIX + route,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlopen(request) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_validation_rejects_unknown_fields_and_invalid_choices_field_by_field(authored_scenario):
    result = resolve_draft(draft(extra_option=True, seed=True, autonomous=False,
                                 default_backend="llm", ticks_per_period=True))
    assert result["valid"] is False
    assert set(result["errors"]) == {
        "extra_option", "seed", "autonomous", "default_backend", "ticks_per_period",
    }
    assert result["normalized"] is None
    assert result["configuration_hash"] is None


@pytest.mark.parametrize("cadence", [False, 0, -2, 1.5, "fast", []])
def test_validation_rejects_invalid_cadence(authored_scenario, cadence):
    result = resolve_draft(draft(ticks_per_period=cadence))
    assert result["errors"]["ticks_per_period"]


@pytest.mark.parametrize("cadence", ["world", None, 1, 24])
def test_validation_accepts_supported_cadence_forms(authored_scenario, cadence):
    result = resolve_draft(draft(ticks_per_period=cadence))
    assert result["valid"] is True
    assert result["normalized"]["ticks_per_period"] == cadence


def test_validation_resolves_authored_override_and_warns_about_precedence(authored_scenario):
    result = resolve_draft(draft(default_backend="cheap"))
    assert result["valid"] is True
    assert result["normalized"]["default_backend"] == "simple"
    assert result["normalized"]["actor_backend_overrides"] == [
        {"actor": "Ada", "backend": "simple", "source": "scenario_override"}
    ]
    assert result["warnings"]
    assert result["normalized"]["physical_subsystems"]["ecology"] is False
    assert len(result["configuration_hash"]) == 64


@pytest.mark.parametrize("backend", ["human", "llm", "ocelot", "unknown"])
def test_authored_scenario_with_unsupported_actor_backend_is_rejected(
        authored_scenario, backend):
    authored_scenario["actors"][0]["backend"] = backend
    # Mutate the fixture's JSON source too, so scenario loading sees the unsupported choice.
    from bigville.scenarios import SCENARIO_ROOT
    path = SCENARIO_ROOT / "draft_fixture.json"
    path.write_text(json.dumps(authored_scenario))
    result = resolve_draft(draft())
    assert result["valid"] is False
    assert "Ada" in result["errors"]["scenario_id"]
    assert backend in result["errors"]["scenario_id"]


def test_validation_rejects_unknown_scenario_and_bad_turn_limit(authored_scenario):
    result = resolve_draft(draft(scenario_id="../../etc/passwd", turn_limit=True))
    assert "scenario_id" in result["errors"]
    assert "turn_limit" in result["errors"]
    absolute_path = resolve_draft(draft(scenario_id="/etc/passwd"))
    assert "scenario_id" in absolute_path["errors"]


def test_validation_rejects_negative_seed_before_town100_preview():
    result = resolve_draft(draft(scenario_id="town100", seed=-1))
    assert result["valid"] is False
    assert "nonnegative" in result["errors"]["seed"]


def test_validation_reports_unsupported_authored_subsystems(authored_scenario):
    authored_scenario["physical_subsystems"]["not_a_gate"] = True
    from bigville.scenarios import SCENARIO_ROOT
    (SCENARIO_ROOT / "draft_fixture.json").write_text(json.dumps(authored_scenario))
    result = resolve_draft(draft())
    assert result["valid"] is False
    assert "not_a_gate" in result["errors"]["scenario_id"]


def test_preview_is_deterministic_and_reflects_authored_cast_and_override(authored_scenario):
    first, resolution = preview_draft(draft())
    second, _ = preview_draft(draft())
    assert first == second
    assert first["configuration_hash"] == resolution["configuration_hash"]
    assert first["map"]["width"] == 5
    assert first["map"]["height"] == 5
    assert first["cast"]["count"] == 1
    assert first["cast"]["actors"] == [{
        "name": "Ada", "role": "hand", "backend": "simple",
        "backend_source": "scenario_override", "position": [2, 2],
    }]


def test_town100_seed_changes_generated_preview_data():
    base = draft(scenario_id="town100", seed=31)
    first, _ = preview_draft(base)
    second, _ = preview_draft({**base, "seed": 32})
    assert first["configuration_hash"] != second["configuration_hash"]
    assert (first["map"]["grid"], first["cast"]["actors"]) != \
        (second["map"]["grid"], second["cast"]["actors"])


def test_preview_uses_world_only_and_never_creates_runs_or_calls_providers(
        authored_scenario, monkeypatch):
    import bigville.api

    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not create a game or call a provider")

    monkeypatch.setattr(bigville.api, "create_game", forbidden)
    monkeypatch.setattr(bigville.api, "create_run", forbidden, raising=False)
    preview, _ = preview_draft(draft())
    assert preview["cast"]["count"] == 1


def test_http_validate_and_preview_endpoints_return_field_errors_and_preview(
        authored_scenario, management_server):
    status, validation = post(management_server, "/run-drafts/validate", draft())
    assert status == 200
    assert validation["valid"] is True
    assert validation["normalized"]["seed"] == 27

    status, preview = post(management_server, "/run-drafts/preview", draft(seed=True))
    assert status == 422
    assert preview["error"]["code"] == "invalid_draft"
    assert "seed" in preview["error"]["fields"]

    status, preview = post(management_server, "/run-drafts/preview", draft())
    assert status == 200
    assert preview["cast"]["actors"][0]["name"] == "Ada"


def test_http_rejects_oversized_draft_body(management_server):
    request = Request(
        management_server + API_PREFIX + "/run-drafts/validate",
        data=b" " * (http.MAX_REQUEST_BYTES + 1),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(request)
    assert caught.value.code == 413
    assert json.load(caught.value)["error"]["code"] == "request_too_large"


def test_http_preview_world_construction_error_is_field_addressed(
        authored_scenario, management_server):
    authored_scenario["map"]["grid"] = []
    from bigville.scenarios import SCENARIO_ROOT
    (SCENARIO_ROOT / "draft_fixture.json").write_text(json.dumps(authored_scenario))
    status, body = post(management_server, "/run-drafts/preview", draft())
    assert status == 422
    assert body["error"]["code"] == "preview_failed"
    assert body["error"]["fields"]["scenario_id"]
