import json

import pytest

from bigville.backends.llm import LLMBackend
from bigville.management.drafts import resolve_draft
from bigville.management.http import create_server
from bigville.management.profiles import BackendProfileRegistry, ProfileError
from bigville.management.templates import TemplateUnavailable


@pytest.fixture
def profile_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "profile_fixture.json").write_text(json.dumps({
        "id": "profile_fixture", "name": "Profile Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 4, "homes": [[1, 1], [3, 1]]}},
        "actors": [
            {"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]},
            {"name": "Ben", "role": "hand", "home_cell": [3, 1]},
        ],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return root


def write_profiles(data_dir, profiles):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "backend_profiles.json").write_text(json.dumps({"schema_version": 1, "profiles": profiles}))


def draft(**changes):
    value = {"scenario_id": "profile_fixture", "name": "Profile run", "seed": 17,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 2}
    value.update(changes)
    return value


def create_profiled_run(server, draft_value, template=None):
    resolved = resolve_draft(draft_value, profile_registry=server.profile_registry)
    assert resolved["valid"], resolved["errors"]
    request = {"draft": draft_value, "idempotency_key": "profile-run",
               "expected_config_hash": resolved["configuration_hash"],
               "expected_capability_revision": resolved["capability_revision"]}
    if template:
        request["template"] = {"id": template["id"], "version": template["version"]}
    return server.run_registry.create_run(request)[0]


def test_profile_catalog_readiness_never_exposes_local_secret_reference(tmp_path, profile_scenario):
    data_dir = tmp_path / "managed"
    write_profiles(data_dir, [{"id": "llm.local", "name": "Local LLM", "kind": "llm",
                               "revision": "r7", "adapter": "missing.adapter",
                               "secret_ref": "env:DO_NOT_LEAK", "enabled": True}])
    server = create_server(port=0, data_dir=data_dir)
    try:
        profile = next(item for item in server.profile_registry.public_profiles()["profiles"]
                       if item["id"] == "llm.local")
        public_json = json.dumps(server.profile_registry.public_profiles())
        assert profile["available"] is False
        assert "adapter" in profile["reason"]
        assert "missing.adapter" not in public_json
        assert "DO_NOT_LEAK" not in public_json
        assert "secret_ref" not in public_json
        original_revision = server.profile_registry.public_profiles()["revision"]
        server.profile_registry._configured[0]["secret_ref"] = "env:CHANGED_REFERENCE"
        assert server.profile_registry.public_profiles()["revision"] != original_revision
        assert "CHANGED_REFERENCE" not in json.dumps(server.profile_registry.public_profiles())
        bad_default = resolve_draft(draft(default_backend="llm", default_profile_id="llm.local"),
                                    profile_registry=server.profile_registry)
        assert bad_default["errors"]["default_profile_id"]
        bad_actor = resolve_draft(draft(actor_backend_profiles={"Ada": "llm.local"}),
                                  profile_registry=server.profile_registry)
        assert bad_actor["errors"]["actor_backend_profiles.Ada"]
        invalid = resolve_draft(draft(default_profile_id="does.not.exist"),
                                profile_registry=server.profile_registry)
        assert invalid["errors"]["default_profile_id"]
        unknown_actor = resolve_draft(draft(actor_backend_profiles={"Not Ada": "simple.default"}),
                                      profile_registry=server.profile_registry)
        assert unknown_actor["errors"]["actor_backend_profiles.Not Ada"]
        town100 = resolve_draft({**draft(scenario_id="town100"),
                                 "actor_backend_profiles": {"Ada": "simple.default"}},
                                profile_registry=server.profile_registry)
        assert "town100" in town100["errors"]["actor_backend_profiles"]
    finally:
        server.server_close()


def test_authored_actor_overrides_preview_and_launch_exact_profiles(tmp_path, profile_scenario):
    data_dir = tmp_path / "managed"
    profiles = [
        {"id": "llm.alpha", "name": "Alpha", "kind": "llm", "revision": "a1",
         "adapter": "adapter.alpha", "secret_ref": "env:ALPHA_SECRET"},
        {"id": "llm.beta", "name": "Beta", "kind": "llm", "revision": "b1",
         "adapter": "adapter.beta", "secret_ref": "env:BETA_SECRET"},
    ]
    write_profiles(data_dir, profiles)
    server = create_server(port=0, data_dir=data_dir)
    factory_calls = []
    provider_calls = []

    class FakeProvider:
        def __init__(self, actor, secret_ref):
            self.actor = actor
            self.secret_ref = secret_ref

        def complete(self, payload):
            provider_calls.append((self.actor, self.secret_ref))
            # Confirm that provider exception text is redacted before it reaches game reports.
            raise RuntimeError(f"failure containing {self.secret_ref}")

    def register(adapter_id):
        def factory(world, character, profile):
            factory_calls.append((character.character_id, profile["id"], profile.get("secret_ref")))
            return LLMBackend(character, FakeProvider(character.character_id, profile.get("secret_ref")),
                              autopilot=False)
        server.profile_registry.adapters.register(adapter_id, factory)

    try:
        register("adapter.alpha")
        register("adapter.beta")
        value = draft(actor_backend_profiles={"Ada": "llm.alpha", "Ben": "llm.beta"})
        resolved = resolve_draft(value, profile_registry=server.profile_registry)
        assert resolved["valid"], resolved["errors"]
        preview, _ = __import__("bigville.management.drafts", fromlist=["preview_draft"]).preview_draft(
            value, profile_registry=server.profile_registry)
        by_actor = {item["actor"]: item for item in preview["profile_assignments"]}
        assert by_actor["Ada"]["profile_id"] == "llm.alpha"
        assert by_actor["Ben"]["profile_id"] == "llm.beta"
        assert by_actor["Ada"]["source"] == by_actor["Ben"]["source"] == "user_override"

        # The authenticated profile references are kept in the server adapter config only.
        public = json.dumps(server.profile_registry.public_profiles())
        assert "ALPHA_SECRET" not in public and "BETA_SECRET" not in public
        template = server.template_registry.save(name="LLM assignments", draft=value)
        persisted_template = server.template_registry.path.read_text()
        assert "ALPHA_SECRET" not in persisted_template and "BETA_SECRET" not in persisted_template
        loaded_template = server.template_registry.load(template["id"], template["version"])
        assert "ALPHA_SECRET" not in json.dumps(loaded_template)
        run = create_profiled_run(server, value, template)
        serialized_run = json.dumps(run)
        assert "ALPHA_SECRET" not in serialized_run and "BETA_SECRET" not in serialized_run
        assert run["resolved_actor_profiles"] == preview["profile_assignments"]
        stepped = server.run_registry.command(run["id"], "step")
        assert stepped["turn"] == 1
        assert set(factory_calls) == {("Ada", "llm.alpha", "env:ALPHA_SECRET"),
                                      ("Ben", "llm.beta", "env:BETA_SECRET")}
        assert {actor for actor, _ in provider_calls} == {"Ada", "Ben"}
        assert "ALPHA_SECRET" not in json.dumps(stepped) and "BETA_SECRET" not in json.dumps(stepped)
        report = server.run_registry.get_run_report(run["id"])
        report_json = json.dumps(report)
        assert "ALPHA_SECRET" not in report_json and "BETA_SECRET" not in report_json
        assert "configured provider request failed" in report_json
        snapshot = server.run_registry.get_run_view(run["id"], perspective="referee")
        assert "ALPHA_SECRET" not in json.dumps(snapshot) and "BETA_SECRET" not in json.dumps(snapshot)
    finally:
        server.server_close()


def test_authored_scenario_override_and_default_profile_precedence(tmp_path, profile_scenario):
    profiles = [{"id": "llm.default", "name": "Default LLM", "kind": "llm",
                 "revision": "r1", "adapter": "fake.provider"}]
    write_profiles(tmp_path / "managed", profiles)
    server = create_server(port=0, data_dir=tmp_path / "managed")
    server.profile_registry.adapters.register(
        "fake.provider", lambda world, character, profile: LLMBackend(character, lambda prompt: "{}"))
    try:
        resolved = resolve_draft(draft(default_backend="llm", default_profile_id="llm.default"),
                                 profile_registry=server.profile_registry)
        assert resolved["valid"], resolved["errors"]
        assignments = {item["actor"]: item for item in resolved["normalized"]["resolved_actor_profiles"]}
        assert assignments["Ada"]["backend"] == "simple"
        assert assignments["Ada"]["source"] == "scenario_override"
        assert assignments["Ben"]["backend"] == "llm"
        assert assignments["Ben"]["source"] == "default"
    finally:
        server.server_close()


def test_explicit_actor_override_precedes_unavailable_scenario_backend(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "profile_fixture.json").write_text(json.dumps({
        "id": "profile_fixture", "actors": [
            {"name": "Ada", "backend": "ocelot"},
            {"name": "Ben", "backend": "simple"},
        ],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    resolution = resolve_draft({**draft(), "scenario_id": "profile_fixture",
                                "actor_backend_profiles": {"Ada": "simple.default"}})
    assert resolution["valid"], resolution["errors"]
    assignments = {item["actor"]: item for item in resolution["normalized"]["resolved_actor_profiles"]}
    assert assignments["Ada"]["source"] == "user_override"
    assert assignments["Ada"]["backend"] == "simple"
    assert assignments["Ben"]["source"] == "scenario_override"


@pytest.mark.parametrize("field,value", [("default_backend", []), ("default_backend", {}),
                                          ("default_profile_id", []), ("default_profile_id", {})])
def test_malformed_profile_fields_return_validation_errors(profile_scenario, field, value):
    resolution = resolve_draft(draft(**{field: value}))
    assert resolution["valid"] is False
    assert field in resolution["errors"]


@pytest.mark.parametrize("kind", ["simple", "ocelot"])
def test_custom_simple_or_ocelot_profiles_are_rejected_as_unroutable(tmp_path, kind):
    config = tmp_path / "backend_profiles.json"
    config.write_text(json.dumps({"schema_version": 1, "profiles": [
        {"id": f"custom.{kind}", "name": "Custom", "kind": kind,
         "revision": "1", "adapter": "custom.adapter"},
    ]}))
    with pytest.raises(ValueError, match="unsupported custom kind"):
        BackendProfileRegistry(config)


def test_pre_m10_template_is_inspectable_but_not_silently_migrated(tmp_path, profile_scenario):
    server = create_server(port=0, data_dir=tmp_path / "templates")
    try:
        saved = server.template_registry.save(name="Legacy shape", draft=draft())
        version = server.template_registry._templates["templates"][saved["id"]]["versions"][0]
        # Simulate an M09 persisted template: it has only the legacy draft fields and old capability revision.
        version.pop("default_profile_id", None)
        version.pop("actor_backend_profiles", None)
        version["capability_revision"] = "pre-m10-capability-revision"
        server.template_registry._persist()
        restarted = type(server.template_registry)(
            server.template_registry.path, profile_registry=server.profile_registry)
        assert restarted.inspect(saved["id"])["versions"][0]["version"] == 1
        with pytest.raises(TemplateUnavailable, match="remains inspectable but cannot be loaded"):
            restarted.load(saved["id"], 1)
    finally:
        server.server_close()


def test_profile_config_rejects_secret_values_and_adapter_errors_are_sanitized(tmp_path):
    write_profiles(tmp_path / "bad", [{"id": "llm.bad", "kind": "llm", "revision": "1",
                                        "adapter": "fake", "api_key": "RAW_SECRET"}])
    with pytest.raises(ValueError, match="unsupported fields"):
        BackendProfileRegistry(tmp_path / "bad" / "backend_profiles.json")

    adapters = __import__("bigville.management.profiles", fromlist=["BackendAdapterRegistry"]).BackendAdapterRegistry()
    adapters.register("bad.factory", lambda *_: (_ for _ in ()).throw(RuntimeError("secret-ref-value")))
    with pytest.raises(ProfileError, match="could not initialize") as caught:
        adapters.build({"adapter": "bad.factory", "secret_ref": "secret-ref-value"}, None, None)
    assert "secret-ref-value" not in str(caught.value)
