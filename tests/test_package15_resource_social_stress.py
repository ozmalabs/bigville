"""Package 15 controlled stress run and no-shock control."""
from bigville.stress_experiment import SEEDS, run_stress_experiment


def test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds():
    for seed in SEEDS:
        sharing = run_stress_experiment(seed, "sharing")
        self_priority = run_stress_experiment(seed, "self_priority")

        assert sharing["initial_state"] == self_priority["initial_state"]
        assert sharing["survivors"] == self_priority["survivors"] == 4
        assert sharing["resource_balance"]["shock_loss"] == 4.0
        assert self_priority["resource_balance"]["shock_loss"] == 4.0
        assert sharing["resource_balance"]["accounted_after_shock_and_eating"]
        assert self_priority["resource_balance"]["accounted_after_shock_and_eating"]
        assert sharing["failed_actions"] == self_priority["failed_actions"] == 0
        assert sharing["transfers"] == 1
        assert self_priority["transfers"] == 0
        # Ben receives Ada's voluntary transfer under the sharing policy and
        # retains one extra unit at the end. The measured hunger values happen
        # to converge; the trace does not treat that as evidence of fairness.
        assert sharing["final_state"]["inventory"]["Ben"].get("bread", 0.0) == 1.0
        assert self_priority["final_state"]["inventory"]["Ben"].get("bread", 0.0) == 0.0
        assert all(count == 16 for count in sharing["agent_observation_counts"].values())
        assert all(count == 16 for count in self_priority["agent_observation_counts"].values())

        shock_rows = [row for row in sharing["steps"] if row["shock"]]
        assert len(shock_rows) == 1
        assert shock_rows[0]["turn"] == 2
        assert shock_rows[0]["shock"]["bread_removed"] == 4.0
        # The backend receives only actor-scoped hunger/inventory and nearby
        # identity/position. Other residents' hunger is not included.
        for step in sharing["steps"]:
            for observation in step["observations"].values():
                assert "hunger" in observation
                assert all("hunger" not in resident
                           for resident in observation["nearby_residents"])


def test_no_shock_control_retains_four_more_bread_and_replays_deterministically():
    shocked = run_stress_experiment(SEEDS[0], "sharing", shock=True)
    control = run_stress_experiment(SEEDS[0], "sharing", shock=False)
    replay = run_stress_experiment(SEEDS[0], "sharing", shock=True)
    assert shocked["final_state"]["total_bread"] + 4.0 == control["final_state"]["total_bread"]
    assert shocked["resource_balance"]["shock_loss"] == 4.0
    assert control["resource_balance"]["shock_loss"] == 0.0
    assert shocked == replay
