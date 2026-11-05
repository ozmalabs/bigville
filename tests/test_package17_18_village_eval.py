import pytest
from types import SimpleNamespace

from bigville.village_eval import (
    ARMS, MAX_TURNS, SEEDS, _hash_file_manifest, _resource_snapshot,
    _resource_deltas, main, run_arm, run_evaluation,
)


def test_deposit_and_stock_are_aggregated_as_the_same_item_for_conservation():
    # Moving one unit out of a deposit into town stock must not look like a
    # destruction of ``deposit:wood`` plus creation of a different item.
    town_stock = {"wood": 2.0}
    world = SimpleNamespace(
        _stock={"wood": "town-wood"},
        qty=lambda kind: town_stock[kind],
        _actors={},
        inventory=lambda _actor: {},
        _actor_inventories={},
        _containers={},
        _resource_deposits={"wood": "wood-deposit"},
        _dropped_stocks={},
        eng=SimpleNamespace(node=lambda node: {
            "town-wood": {"attrs": {"qty": 2.0}},
            "wood-deposit": {"attrs": {"stock": 3.0}},
        }[node]),
    )

    before = _resource_snapshot(world)
    town_stock["wood"] = 3.0
    world.eng.node = lambda node: {
        "town-wood": {"attrs": {"qty": 3.0}},
        "wood-deposit": {"attrs": {"stock": 2.0}},
    }[node]
    after = _resource_snapshot(world)

    assert before == {"wood": 5.0}
    assert _resource_deltas(before, after) == {}


def test_source_config_manifest_changes_when_a_hashed_file_changes(tmp_path):
    source = tmp_path / "runtime" / "scenario.json"
    source.parent.mkdir()
    source.write_text('{"initial": 1}', encoding="utf-8")
    before = _hash_file_manifest(tmp_path, ("runtime",))
    source.write_text('{"initial": 2}', encoding="utf-8")
    after = _hash_file_manifest(tmp_path, ("runtime",))

    assert before["runtime/scenario.json"] != after["runtime/scenario.json"]


def test_registered_protocol_is_bounded_before_starting_world(monkeypatch):
    def should_not_construct(*args, **kwargs):
        raise AssertionError("invalid protocol must be rejected before world construction")

    monkeypatch.setattr("bigville.village_eval.create_game", should_not_construct)
    with pytest.raises(ValueError, match="preregistered"):
        run_arm(99, "baseline", turns=1)
    with pytest.raises(ValueError, match="turns"):
        run_arm(SEEDS[0], "baseline", turns=MAX_TURNS + 1)
    with pytest.raises(ValueError, match="ticks_per_period"):
        run_arm(SEEDS[0], "baseline", turns=1, ticks_per_period=1)
    with pytest.raises(ValueError, match="arm must"):
        run_arm(SEEDS[0], "unknown", turns=1)
    with pytest.raises(ValueError, match="unique preregistered seeds"):
        run_evaluation(seeds=(SEEDS[0], SEEDS[0]), turns=1)
    with pytest.raises(ValueError, match="unique members"):
        run_evaluation(seeds=(SEEDS[0],), arms=(ARMS[0], ARMS[0]), turns=1)


def test_partial_cli_run_exits_nonzero_even_if_its_local_checks_pass(monkeypatch):
    monkeypatch.setattr("bigville.village_eval.run_evaluation", lambda **_kwargs: {
        "acceptance": {"evaluation_passed": False},
    })

    assert main(["--seed", str(SEEDS[0]), "--arm", ARMS[0], "--turns", "1"]) == 1


def test_short_factorial_smoke_checks_setup_chains_and_replay():
    report = run_evaluation(seeds=(SEEDS[0],), arms=ARMS, turns=1, replay=True,
                            max_run_seconds=60)
    assert report["schema"] == "bigville/package17-18-village-eval/1"
    assert report["protocol"]["scenario"] == "town100"
    assert report["protocol"]["backend"] == "simple"
    assert report["protocol"]["periods"] == 0
    assert len(report["runs"]) == 4
    assert report["acceptance"]["matched_initial_conditions"] is True
    assert report["acceptance"]["preregistered_protocol_complete"] is False
    assert report["acceptance"]["external_prerequisites_recorded"] is False
    assert report["acceptance"]["evaluation_passed"] is False
    assert report["acceptance"]["claim_gate_ready"] is False
    assert report["provenance"]["python_version"]
    assert report["provenance"]["platform"]
    assert report["provenance"]["source_config_hashes"]["bigville/village_eval.py"]
    assert report["provenance"]["source_config_hashes"]["pyproject.toml"]
    assert len(report["provenance"]["source_config_manifest_sha256"]) == 64
    baseline = next(row for row in report["runs"] if row["arm"] == "baseline")
    assert baseline["initial"]["population"] == 100
    assert 0 <= baseline["final"]["alive"] <= 100
    assert 0.0 <= baseline["actions"]["failure_rate"] <= 1.0
    assert len(baseline["causal_chains"]["period_trace"]) == 1
    assert "chains" in baseline["causal_chains"]["period_trace"][0]
    assert "failures" in baseline["invariants"]
    shock = next(row for row in report["runs"] if row["arm"] == "food_shock")
    assert shock["food_shock"]["applied"] is True
    assert shock["food_shock"]["fraction"] == .20
    assert all(row["measurements_match"] for row in report["replays"])
