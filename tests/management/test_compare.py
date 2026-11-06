import json

import pytest

from bigville.management.runs import InvalidRunRequest, RunRegistry, RunViewUnavailable


def _record(registry, name):
    # Comparison behaviour is deliberately exercised with durable registry data;
    # no report values are invented by the comparison layer.
    run_id = "run_" + ("a" if name == "A" else "b") * 32
    record = {"schema_version": 1, "id": run_id, "name": name,
              "scenario_id": "small", "created_at": "now", "updated_at": "now",
              "status": "completed", "turn": 1, "checkpoints": [],
              "config_hash": "cfg-" + name, "capability_revision": "cap-1",
              "config": {"seed": 3, "default_profile_id": "simple.default",
                         "scenario_source": "authored", "scenario_content_hash": "scenario-sha",
                         "engine_build": {"engine_source_hash": "engine-sha"}},
              "resolved_actor_profiles": [], "report_snapshots": []}
    registry._state["runs"][run_id] = record
    registry._persist()
    return run_id


def _snapshot(run_id, schema="bigville/report/1", alive=2):
    name = "A" if run_id[4] == "a" else "B"
    return {"id": "report_" + "c" * 32, "schema_version": 1,
            "captured_at": "2026-01-01T00:00:00Z",
            "run": {"id": run_id, "name": name, "scenario_id": "small", "turn": 1,
                    "status": "completed"},
            "provenance": {"configuration_hash": "cfg-A" if run_id[4] == "a" else "cfg-B",
                           "capability_revision": "cap-1", "seed": 3, "scenario_id": "small",
                           "scenario_source": "authored", "scenario_content_hash": "scenario-sha",
                           "engine_build": {"engine_source_hash": "engine-sha"}},
            "report": {"schema": schema,
                       "population": {"alive": alive, "total": 4},
                       "economy": {"food_quantity": 12, "stock_reference_value": 8},
                       "social": {"relationships": {"directed_bonds": 2},
                                  "conversation": {"utterances": 1}}}}


def test_compare_only_recorded_reports_and_include_provenance(tmp_path):
    registry = RunRegistry(tmp_path)
    first, second = _record(registry, "A"), _record(registry, "B")
    registry._state["runs"][first]["report_snapshots"] = [_snapshot(first, alive=2)]
    registry._state["runs"][second]["report_snapshots"] = [_snapshot(second, alive=3)]
    registry._persist()
    result = registry.compare_recorded_reports([first, second])
    assert result["compatible"] is True
    assert result["metrics"]["population.alive"] == {
        "unit": "residents", "values": [
            {"run_id": first, "value": 2, "missing_reason": None},
            {"run_id": second, "value": 3, "missing_reason": None}]}
    assert result["runs"][0]["snapshot"]["provenance"]["configuration_hash"] == "cfg-A"


def test_missing_and_incompatible_schema_are_never_fabricated(tmp_path):
    registry = RunRegistry(tmp_path)
    first, second = _record(registry, "A"), _record(registry, "B")
    registry._state["runs"][first]["report_snapshots"] = [_snapshot(first)]
    result = registry.compare_recorded_reports([first, second])
    assert not result["compatible"]
    assert result["runs"][1]["missing_reason"] == "No report has been recorded."
    assert all(metric["values"][0]["value"] is None for metric in result["metrics"].values())
    registry._state["runs"][second]["report_snapshots"] = [_snapshot(second, schema="future/2")]
    result = registry.compare_recorded_reports([first, second])
    assert not result["compatible"]
    assert all(item["value"] is None for metric in result["metrics"].values() for item in metric["values"])


def test_missing_or_non_numeric_metrics_are_reported_explicitly(tmp_path):
    registry = RunRegistry(tmp_path)
    first, second = _record(registry, "A"), _record(registry, "B")
    one = _snapshot(first)
    two = _snapshot(second)
    del one["report"]["population"]["alive"]
    two["report"]["population"]["total"] = True
    registry._state["runs"][first]["report_snapshots"] = [one]
    registry._state["runs"][second]["report_snapshots"] = [two]
    result = registry.compare_recorded_reports([first, second])
    assert result["compatible"] is True
    assert result["metrics"]["population.alive"]["values"][0]["missing_reason"]
    assert result["metrics"]["population.total"]["values"][1]["value"] is None
    assert result["metrics"]["population.total"]["values"][1]["missing_reason"]


def test_malformed_snapshots_fail_closed_on_list_and_compare(tmp_path):
    registry = RunRegistry(tmp_path)
    first, second = _record(registry, "A"), _record(registry, "B")
    registry._state["runs"][first]["report_snapshots"] = [{"schema_version": 1, "report": "not a report"}]
    with pytest.raises(RunViewUnavailable):
        registry.compare_recorded_reports([first, second])
    with pytest.raises(RunViewUnavailable):
        registry.list_report_snapshots(first)


def test_public_run_reads_reject_malformed_in_memory_snapshots(tmp_path):
    registry = RunRegistry(tmp_path)
    run_id = _record(registry, "A")
    registry._state["runs"][run_id]["report_snapshots"] = [{"schema_version": 1}]
    with pytest.raises(RunViewUnavailable):
        registry.get_run(run_id)
    with pytest.raises(RunViewUnavailable):
        registry.list_runs()


def test_restart_rejects_snapshot_provenance_that_does_not_match_run(tmp_path):
    registry = RunRegistry(tmp_path)
    run_id = _record(registry, "A")
    snapshot = _snapshot(run_id)
    snapshot["provenance"]["scenario_content_hash"] = "other-scenario"
    registry._state["runs"][run_id]["report_snapshots"] = [snapshot]
    registry._persist()
    with pytest.raises(ValueError, match="invalid report snapshot metadata"):
        RunRegistry(tmp_path)


@pytest.mark.parametrize("schema_version,snapshot_turn", [(True, 1), (1, 2)])
def test_restart_rejects_boolean_schema_version_and_future_snapshot_turn(
        tmp_path, schema_version, snapshot_turn):
    registry = RunRegistry(tmp_path)
    run_id = _record(registry, "A")
    snapshot = _snapshot(run_id)
    snapshot["schema_version"] = schema_version
    snapshot["run"]["turn"] = snapshot_turn
    registry._state["runs"][run_id]["report_snapshots"] = [snapshot]
    registry._persist()
    with pytest.raises(ValueError, match="invalid report snapshot metadata"):
        RunRegistry(tmp_path)


def test_economic_comparison_requires_matching_known_scenario_and_pack_build(tmp_path):
    registry = RunRegistry(tmp_path)
    first, second = _record(registry, "A"), _record(registry, "B")
    registry._state["runs"][second]["config"]["engine_build"]["engine_source_hash"] = "other-pack-build"
    one, two = _snapshot(first), _snapshot(second)
    two["provenance"]["engine_build"] = {"engine_source_hash": "other-pack-build"}
    registry._state["runs"][first]["report_snapshots"] = [one]
    registry._state["runs"][second]["report_snapshots"] = [two]
    result = registry.compare_recorded_reports([first, second])
    value = result["metrics"]["economy.stock_reference_value"]["values"][0]
    assert value["value"] is None
    assert "Scenario content differs" in value["missing_reason"]
    registry._state["runs"][second]["config"]["engine_build"] = {"engine_source_hash": "engine-sha"}
    two["provenance"]["engine_build"] = {"engine_source_hash": "engine-sha"}
    registry._state["runs"][first]["report_snapshots"][0]["report"]["economy"]["food_quantity"] = float("nan")
    result = registry.compare_recorded_reports([first, second])
    value = result["metrics"]["economy.food_quantity"]["values"][0]
    assert value["value"] is None and value["missing_reason"]


def test_compare_validates_run_selection(tmp_path):
    registry = RunRegistry(tmp_path)
    with pytest.raises(InvalidRunRequest):
        registry.compare_recorded_reports(["same", "same"])


def test_reproducibility_export_contains_identity_and_no_secrets(tmp_path):
    registry = RunRegistry(tmp_path)
    run_id = _record(registry, "A")
    registry._state["runs"][run_id]["config"]["api_key"] = "SECRET_SENTINEL"
    exported = registry.reproducibility_metadata(run_id)
    encoded = json.dumps(exported)
    assert exported["configuration_hash"] == "cfg-A"
    assert "SECRET_SENTINEL" not in encoded
    assert "api_key" not in encoded
