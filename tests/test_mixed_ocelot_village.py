from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


_BIGVILLE_ROOT = Path(__file__).resolve().parents[1]
_OCELOT_ROOT = _BIGVILLE_ROOT.parent / "ocelot"


def test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action(
        monkeypatch):
    if not (_OCELOT_ROOT / "worlds" / "bigville_ocelot_adapter.py").is_file():
        pytest.skip("Ocelot source checkout is not present")
    if not (_BIGVILLE_ROOT / "seeds" / "bigville_actor_decision.json").is_file():
        pytest.skip("standalone Bigville seed checkout is not present")
    for entry in (_OCELOT_ROOT, _OCELOT_ROOT / "runners" / "dsl" / "python"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    pytest.importorskip("substrate_rs")
    try:
        importlib.import_module("worlds.bigville_ocelot_adapter")
    except ImportError as exc:
        # Bigville's `worlds` namespace package may already be imported in this
        # process and shadow Ocelot's; run from the Ocelot checkout (see
        # docs/ocelot-integration-baseline.md) to exercise this test.
        pytest.skip(f"Ocelot's worlds.bigville_ocelot_adapter is not importable here: {exc}")
    monkeypatch.setenv("BIGVILLE_ROOT", str(_BIGVILLE_ROOT))
    monkeypatch.chdir(_OCELOT_ROOT)

    from bigville.mixed_ocelot_scenario import run_mixed_ocelot_village

    trace = run_mixed_ocelot_village(turns=8)

    assert trace["backend_assignment"] == {
        "Ada": "ocelot", "Ben": "ocelot", "Cy": "cheap", "Dee": "cheap"}
    assert len(trace["steps"]) == 8
    assert all(len(step["actions"]) == 4 for step in trace["steps"])
    assert all(trace["ocelot_minds"][name]["cognitive_observations"] == 8
               for name in ("Ada", "Ben"))
    assert all(trace["ocelot_minds"][name]["emotional_state"]["enabled"]
               for name in ("Ada", "Ben"))
    assert trace["rejection_probe"]["rejected"] is True
    assert trace["ocelot_minds"]["Ada"]["appraisal"]["individual_cost"] == 1.0
    assert trace["timing"]["total_seconds"] < trace["hard_runtime_budget_seconds"]
    for actor in ("Ada", "Ben"):
        assert trace["steps"][0]["actions"][actor]["proposal"]["action"] == "fetch"
        assert trace["steps"][1]["actions"][actor]["proposal"]["action"] == "eat"
        assert all(not ({"hunger_eat_weight", "hunger_fetch_weight", "hunger_scored"}
                        & set(step["actions"][actor]["proposal"]["params"])
                        if step["actions"][actor]["proposal"] else False)
                   for step in trace["steps"])
        assert all(step["actions"][actor]["proposal"] is None
                   or step["actions"][actor]["proposal"]["action"] != "rest"
                   for step in trace["steps"][2:])
        assert all(step["actions"][actor]["applied"] is not False
                   for step in trace["steps"])
        assert all(trace["steps"][turn]["actions"][actor]["proposal"] is None
                   or trace["steps"][turn]["actions"][actor]["proposal"]["action"] != "fetch"
                   for turn in range(2, 8))
        assert trace["final_state"]["residents"][actor]["hunger"] == 0.0
