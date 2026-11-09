"""Phase 074: tools/balance_run.py writes one row per day with the documented keys (a 20-tick smoke run)."""
from __future__ import annotations

import importlib.util
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location("balance_run", os.path.join(_ROOT, "tools", "balance_run.py"))
balance_run = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(balance_run)

ROW_KEYS = {
    "day", "partial_day", "alive", "deaths_day", "deaths_cum", "hunger_mean", "hunger_p10", "hunger_p90",
    "store_food", "food_held", "meals_eaten", "fetches", "work_starts", "work_completions", "food_produced",
    "energy_1700_mean", "energy_1700_p10", "energy_1700_share_lt35", "share_lt35_eod",
    "cells_walked_per_resident", "walk_attempts", "walk_moved", "walk_moved_share", "walk_energy_per_cell",
    "effort_energy_walk_share", "move_refused",
}


def test_balance_run_writes_one_row_per_day_with_the_documented_keys(tmp_path):
    out = tmp_path / "smoke.json"
    result = balance_run.main(["--seed", "305000", "--ticks", "20", "--out", str(out), "--label", "smoke"])
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["label"] == "smoke" and written["ticks"] == 20
    assert result["runs"][0]["seed"] == 305000
    rows = written["runs"][0]["rows"]
    assert len(rows) == 1 and rows[0]["partial_day"] is True
    assert ROW_KEYS <= set(rows[0]), sorted(ROW_KEYS - set(rows[0]))
    assert rows[0]["alive"] == 100
    assert {"person_days", "alive_end", "first_death_day", "extinct_day"} <= set(written["runs"][0]["summary"])


def test_balance_run_refuses_an_unknown_override_key():
    try:
        balance_run.main(["--seed", "305000", "--ticks", "1", "--set", "CARRYING.no_such_key=1"])
    except SystemExit as error:
        assert "no_such_key" in str(error)
    else:
        raise AssertionError("an unknown --set key must stop the run")
