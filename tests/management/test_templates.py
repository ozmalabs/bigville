import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.management.templates import (TemplateInvalid, TemplateRegistry,
                                          TemplateUnavailable)


@pytest.fixture
def template_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "template_fixture.json").write_text(json.dumps({
        "id": "template_fixture", "name": "Template Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return root


def draft(**changes):
    value = {"scenario_id": "template_fixture", "name": "Template run", "seed": 12,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 3}
    value.update(changes)
    return value


def make_run_request(registry, draft_value, *, template=None, key="template-run"):
    resolution = resolve_draft(draft_value)
    result = {"draft": draft_value, "idempotency_key": key,
              "expected_config_hash": resolution["configuration_hash"],
              "expected_capability_revision": resolution["capability_revision"]}
    if template:
        result["template"] = {"id": template["id"], "version": template["version"]}
    return result


def test_versions_are_immutable_and_round_trip_after_reload(tmp_path, template_scenario):
    path = tmp_path / "templates.json"
    registry = TemplateRegistry(path)
    first = registry.save(name="Morning", draft=draft())
    changed = registry.save(name="Morning", draft=draft(seed=99), template_id=first["id"])
    reloaded = TemplateRegistry(path)
    old = reloaded.load(first["id"], 1)
    latest = reloaded.load(first["id"], 2)
    assert first["version"] == 1 and changed["version"] == 2
    assert old["draft"]["seed"] == 12
    assert latest["draft"]["seed"] == 99
    assert reloaded.inspect(first["id"])["versions"][0]["configuration_hash"] == first["configuration_hash"]


def test_stale_capabilities_fail_load_without_normalizing_template(tmp_path, template_scenario, monkeypatch):
    import bigville.management.drafts as drafts

    registry = TemplateRegistry(tmp_path / "templates.json")
    saved = registry.save(name="Stale", draft=draft())
    original = drafts.build_capability_catalog

    def changed_catalog():
        catalog = original()
        catalog["revision"] = "changed-capability-revision"
        return catalog

    monkeypatch.setattr(drafts, "build_capability_catalog", changed_catalog)
    with pytest.raises(TemplateUnavailable, match="changed"):
        registry.load(saved["id"], saved["version"])
    assert registry.get_version(saved["id"], 1)["configuration_hash"] == saved["configuration_hash"]


def test_load_rejects_schema_or_noncanonical_draft_without_normalizing(tmp_path, template_scenario):
    registry = TemplateRegistry(tmp_path / "templates.json")
    saved = registry.save(name="Exact", draft=draft())
    stored = registry._templates["templates"][saved["id"]]["versions"][0]["draft"]
    stored["default_backend"] = "cheap"  # resolves to simple, but is not the stored canonical draft
    with pytest.raises(TemplateUnavailable, match="exact canonical form"):
        registry.load(saved["id"], 1)
    stored["default_backend"] = "simple"
    stored["unexpected"] = "value"
    with pytest.raises(TemplateUnavailable, match="draft schema is incompatible"):
        registry.load(saved["id"], 1)


def test_secret_or_unknown_fields_are_rejected_and_never_written(tmp_path, template_scenario):
    path = tmp_path / "templates.json"
    registry = TemplateRegistry(path)
    with pytest.raises(TemplateInvalid):
        registry.save(name="No secrets", draft={**draft(), "api_key": "DO_NOT_STORE_SECRET"})
    assert not path.exists()
    saved = registry.save(name="Clean", draft=draft())
    raw = path.read_text()
    assert "api_key" not in raw and "DO_NOT_STORE_SECRET" not in raw
    assert set(registry.load(saved["id"], 1)["draft"]) == {
        "scenario_id", "name", "seed", "autonomous", "default_backend",
        "ticks_per_period", "turn_limit",
    }


def test_failed_atomic_save_rolls_back_memory_and_preserves_prior_version(tmp_path, template_scenario, monkeypatch):
    path = tmp_path / "templates.json"
    registry = TemplateRegistry(path)
    original = registry.save(name="Stable", draft=draft())
    persisted_before = path.read_text()
    monkeypatch.setattr(registry, "_persist", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        registry.save(name="Stable", draft=draft(seed=44), template_id=original["id"])
    assert path.read_text() == persisted_before
    assert len(registry.inspect(original["id"])["versions"]) == 1
    assert registry.load(original["id"], 1)["draft"]["seed"] == 12


def test_run_keeps_template_version_provenance_after_newer_version(tmp_path, template_scenario):
    server = create_server(port=0, data_dir=tmp_path / "managed")
    templates = server.template_registry
    first = templates.save(name="Run template", draft=draft())
    run, _ = server.run_registry.create_run(make_run_request(
        server.run_registry, first["draft"], template=first))
    second = templates.save(name="Run template", draft=draft(seed=77), template_id=first["id"])
    assert second["version"] == 2
    persisted = server.run_registry.get_run(run["id"])
    assert persisted["template"] == {
        "id": first["id"], "version": 1,
        "configuration_hash": first["configuration_hash"],
        "capability_revision": first["capability_revision"],
        "run_configuration_hash": run["config_hash"],
    }
    server.server_close()


def test_template_http_list_inspect_load_and_stale_capability_error(
        tmp_path, template_scenario, monkeypatch):
    server = create_server(port=0, data_dir=tmp_path / "http-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}/templates"
    value = {"name": "HTTP template", "draft": draft()}
    try:
        request = Request(base, data=json.dumps(value).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        saved = json.load(urlopen(request))
        listed = json.load(urlopen(base))["templates"]
        inspected = json.load(urlopen(f"{base}/{saved['id']}"))
        loaded = json.load(urlopen(f"{base}/{saved['id']}/versions/1/load"))
        assert listed[0]["latest_version"] == 1
        assert inspected["versions"][0]["version"] == 1
        assert loaded["draft"] == saved["draft"]
        import bigville.management.drafts as drafts_module
        original_catalog = drafts_module.build_capability_catalog

        def changed_catalog():
            catalog = original_catalog()
            catalog["revision"] = "stale-api-revision"
            return catalog

        monkeypatch.setattr(drafts_module, "build_capability_catalog", changed_catalog)
        with pytest.raises(HTTPError) as stale:
            urlopen(f"{base}/{saved['id']}/versions/1/load")
        assert stale.value.code == 409
        assert json.load(stale.value)["error"]["code"] == "template_unavailable"
        monkeypatch.setattr(drafts_module, "build_capability_catalog", original_catalog)
        bad_request = Request(base, data=json.dumps({"name": "Leaky", "draft": {**draft(), "token": "secret"}}).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as caught:
            urlopen(bad_request)
        assert caught.value.code == 422
        assert json.load(caught.value)["error"]["fields"]["token"] == "Unknown field."
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
