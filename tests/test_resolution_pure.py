"""Phase 050: the pure resolution function (worlds/resolution.py). No world, no pack: plain numbers in, numbers out.

The core's contract: monotone in every capability term, deterministic, the reference point is rho = 1, and the
recipe cost passes through the same clamp at the strength gate without changing it.
"""
from __future__ import annotations

import inspect
import math

import pytest

from worlds import resolution as R

GRID = [i / 20.0 for i in range(0, 61)]


def _step(**overrides):
    p = {"force": 1.0, "technique": 1.0, "fit": 1.0, "team": 1.0, "conditions": 1.0, "intensity": 1.0,
         "demand": 1.0, "cap_rate": 2.0, "exponent": 1.0, "base_cost": 0.1, "floor": 0.0, "effort_cap": 3.0,
         "k": 1.5, "i_safe": 1.5, "m": 2.0}
    p.update(overrides)
    return p


def test_the_module_draws_no_random_numbers():
    source = inspect.getsource(R)
    assert "import random" not in source and "random." not in source
    assert not any(name == "random" for name in vars(R))


def test_capability_is_the_product_of_its_five_terms():
    assert R.capability(1.2, 0.5, 0.8, 1.0, 1.0) == pytest.approx(0.48)
    assert R.capability(1.0, 1.0, 0.0, 1.0, 1.0) == 0.0          # a zero term zeroes the capability
    with pytest.raises(ValueError):
        R.capability(-1.0, 1.0, 1.0, 1.0, 1.0)


def test_the_reference_point_is_rho_one_and_demand_zero_is_infinite():
    assert R.rho(1.0, 1.0) == 1.0
    assert R.rho(0.0, 2.0) == 0.0
    assert math.isinf(R.rho(1.0, 0.0))


def test_progress_is_capped_zero_without_capability_and_monotone_in_capability():
    assert R.progress_rate(0.0, 2.0, 1.0) == 0.0
    assert R.progress_rate(1.0, 2.0, 1.0) == 1.0
    assert R.progress_rate(5.0, 2.0, 1.0) == 2.0               # cap_rate bounds the rate
    values = [R.progress_rate(R.rho(c, 1.0), 2.0, 1.0) for c in GRID]
    assert all(b >= a for a, b in zip(values, values[1:]))


def test_cost_ratio_is_clamped_and_a_zero_capability_pays_the_cap():
    assert R.cost_ratio(1.0, 0.0, 0.0, 3.0) == 3.0
    assert R.cost_ratio(10.0, 1.0, 0.0, 3.0) == 3.0
    assert R.cost_ratio(0.1, 1.0, 0.0, 3.0) == pytest.approx(0.1)
    assert R.cost_ratio(0.1, 1.0, 1.0, 3.0) == 1.0           # recipe floor: a strong worker pays the declared cost


def test_a_recipe_worker_who_meets_the_gate_pays_the_declared_cost_unchanged():
    # Phase 022/023 reference: strength meets the requirement (C >= D), so the floor-1 clamp is exactly 1.
    for strength, need in ((1.3, 1.2), (1.0, 1.0), (2.0, 0.5)):
        assert R.cost_ratio(need, strength, 1.0, 3.0) == 1.0


def test_intensity_is_clamped_to_the_ceiling_and_the_clamp_is_reported():
    assert R.intensity_applied(1.0, 3.0) == (1.0, False)
    assert R.intensity_applied(5.0, 3.0) == (3.0, True)
    assert R.intensity_applied(3.0, 3.0, ceiling=0.5) == (0.5, True)
    assert R.intensity_applied(-2.0, 3.0) == (0.0, True)
    assert R.intensity_applied(float("nan"), 3.0) == (1.0, False)


def test_overexertion_is_zero_at_or_below_the_safe_level_and_grows_past_it():
    assert R.overexertion(1.0, 1.5, 2.0) == 0.0
    assert R.overexertion(1.5, 1.5, 2.0) == 0.0
    assert R.overexertion(2.5, 1.5, 2.0) == pytest.approx(1.0)
    assert R.overexertion(3.0, 1.5, 2.0) > R.overexertion(2.5, 1.5, 2.0)


def test_strain_is_the_cost_share_of_the_part_the_worker_cannot_meet():
    assert R.strain(0.5, 1.0) == 0.0
    assert R.strain(0.5, 0.0) == 0.5
    assert R.strain(0.5, 5.0) == 0.0


def test_tool_wear_rises_when_the_tool_does_not_fit_and_against_harder_material():
    fitted = R.tool_wear(0.05, 1.0, 1.0, 4.0, 0.0)
    loose = R.tool_wear(0.05, 1.0, 0.5, 4.0, 0.0)
    hopeless = R.tool_wear(0.05, 1.0, 0.0, 4.0, 0.0)
    assert fitted < loose < hopeless
    assert R.tool_wear(0.05, 1.0, 1.0, 4.0, 0.3) > fitted
    assert R.tool_wear(0.05, 3.0, 1.0, 4.0, 0.0) == pytest.approx(3 * fitted)


def test_noise_grows_with_intensity_and_material_and_a_gentle_tap_is_quiet():
    assert R.noise_radius(4.0, 0.5, 1.0) < R.noise_radius(4.0, 1.0, 1.0) < R.noise_radius(4.0, 2.0, 1.0)
    assert R.noise_radius(4.0, 1.0, 2.0) > R.noise_radius(4.0, 1.0, 1.0)


def test_every_capability_term_is_monotone_for_progress_cost_and_strain():
    base = _step(force=0.6, technique=0.6, fit=0.6, team=0.6, conditions=0.6)
    for term in ("force", "technique", "fit", "team", "conditions"):
        previous = None
        for value in GRID:
            out = R.resolve_step({**base, term: value})
            if previous is not None:
                assert out["progress"] >= previous["progress"] - 1e-12, term
                assert out["cost_share"] <= previous["cost_share"] + 1e-12, term
                assert out["strain"] <= previous["strain"] + 1e-12, term
            previous = out


def test_intensity_scales_stamina_by_more_than_twice_at_twice_the_intensity():
    one = R.resolve_step(_step(intensity=1.0, floor=0.0))["stamina"]
    two = R.resolve_step(_step(intensity=2.0, floor=0.0))["stamina"]
    assert two > 2.0 * one


def test_intensity_above_the_safe_level_builds_strain_even_when_the_capability_is_enough():
    strong = R.resolve_step(_step(force=3.0, intensity=1.0))
    forced = R.resolve_step(_step(force=3.0, intensity=2.5))
    assert strong["strain"] == 0.0
    assert forced["strain"] > 0.0 and forced["overexertion"] > 0.0


def test_the_step_is_a_pure_function_of_its_inputs():
    p = _step(force=0.7, technique=0.55, fit=0.8, demand=0.9, intensity=1.5)
    assert R.resolve_step(p) == R.resolve_step(dict(p))


def test_hopeless_fit_makes_no_progress_and_still_costs_stamina():
    out = R.resolve_step(_step(fit=0.0))
    assert out["progress"] == 0.0
    assert out["stamina"] > 0.0 and out["strain"] > 0.0
