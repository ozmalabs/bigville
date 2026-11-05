"""Package 15 controlled resource/social stress experiment.

This runner owns only the experimental protocol: world construction, a
predeclared exogenous stock shock, and trace/report collection. Policies make
choices over the ordinary affordances; the world continues to validate every
physical action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .api import create_game
from .backends import ActorResponse, DeterministicBackend, ProposedAction
from .backends import SimplePolicy, register_simple_profile
from .scenarios import load_scenario


ACTORS = ("Ada", "Ben", "Cy", "Dee")
SEEDS = (15001, 15002, 15003)


class StressPolicy(DeterministicBackend):
    """Simple backend policy with a declared sharing or self-priority rule."""
    kind = "simple"

    def __init__(self, character, mode: str):
        super().__init__(character)
        if mode not in {"sharing", "self_priority"}:
            raise ValueError(f"unknown stress policy: {mode}")
        self.mode = mode
        self.observation_log: list[dict[str, Any]] = []

    def decide(self, context):
        observations = context.observations
        self.observation_log.append({
            "turn": context.turn,
            "hunger": observations.get("hunger"),
            "inventory": dict(observations.get("inventory", {})),
            "nearby_residents": [dict(row) for row in observations.get("nearby_residents", [])],
            "heard_utterances": [dict(row) for row in observations.get("heard_utterances", [])],
        })
        options = list(context.affordances)
        hunger = float(observations.get("hunger", 0.0))
        bread = float(observations.get("inventory", {}).get("bread", 0.0))

        # A single declared donor offers one carried unit once. The recipient
        # is selected from the physically published transfer affordances; this
        # is a policy choice and is never inferred by the world.
        if (self.mode == "sharing" and self.character.name == "Ada"
                and context.turn == 1 and bread >= 1):
            transfer = next((o for o in options
                             if o.get("action") == "transfer"
                             and o.get("kind") == "bread"
                             and o.get("recipient") == "Ben"), None)
            if transfer:
                return ActorResponse(major_action=ProposedAction(
                    "transfer", {"kind": "bread", "target": transfer["target"],
                                 "recipient": "Ben", "amount": 1.0},
                    "sharing policy voluntarily offers one bread"))

        # The self-priority profile keeps transfer affordances unused and
        # chooses food actions for its own observed need.
        eat = next((o for o in options if o.get("action") == "eat"
                    and o.get("kind") == "bread"), None)
        if eat and hunger > 0:
            return ActorResponse(major_action=ProposedAction(
                "eat", {"kind": "bread"}, "respond to own observed hunger"))
        fetch = next((o for o in options if o.get("action") == "fetch"
                      and o.get("kind") == "bread"), None)
        if fetch and hunger > 0 and bread < 1:
            return ActorResponse(major_action=ProposedAction(
                "fetch", {"kind": "bread", "target": fetch["target"]},
                "obtain physically available bread"))
        return ActorResponse()


def _new_game(seed: int, mode: str, *, shock: bool):
    # Register names so scenario construction is valid and auditable. The
    # controlled StressPolicy instances are installed below for the run.
    for profile in ("pkg15.sharing", "pkg15.self_priority"):
        register_simple_profile(profile, SimplePolicy(), replace=True)
    scenario = load_scenario("resource_social_stress").to_dict()
    # Paired runs use exactly this actor order and physical setup. Only policy
    # selection and the explicitly toggled negative control can differ.
    scenario["physical_subsystems"] = {"metabolism": False,
                                      "ecology": False, "decay": False}
    scenario["metadata"] = dict(scenario.get("metadata", {}),
                                applied_policy=mode,
                                shock_enabled=bool(shock))
    game = create_game(scenario=scenario, seed=seed, autonomous=True,
                       ticks_per_period=2)
    world = game.world
    world.add_container("stress_pantry", kind="larder", holds=(), cell=(2, 2))
    # Install the declared initial quantity as a pantry pile. This is scenario
    # initialization, before any actor turn; no cognition or automatic claim
    # moves the resource.
    pantry_node, inners = world._containers["stress_pantry"]
    bread_pile = inners.get("bread") or world._new_inner_stock(
        pantry_node, "larder", "bread")
    inners["bread"] = bread_pile
    world.eng.set_attr(bread_pile, "qty", 12.0)
    for actor in ACTORS:
        world.eng.set_attr(world._actors[actor], "hunger", 0.65)
    for actor in ACTORS:
        selected_mode = mode if actor in {"Ada", "Ben"} else "self_priority"
        game.set_backend(actor, StressPolicy(game.characters[actor], selected_mode))
    return game


def _state(world):
    residents = world.export_state(event_tail=50).get("residents", [])
    by_name = {row["id"]: row for row in residents}
    return {
        "alive": {name: bool(by_name[name].get("alive")) for name in ACTORS},
        "hunger": {name: float(by_name[name].get("hunger", 0.0)) for name in ACTORS},
        "inventory": {name: dict(world.inventory(name)) for name in ACTORS},
        "pantry_bread": float(world.contents("stress_pantry", "bread")),
        "town_bread": float(world.qty("bread")),
        "total_bread": float(world.contents("stress_pantry", "bread")
                              + world.qty("bread")
                              + sum(world.inventory_qty(name, "bread") for name in ACTORS)),
    }


def run_stress_experiment(seed: int, mode: str, *, shock: bool = True,
                          turns: int = 16) -> dict[str, Any]:
    """Run one fixed-seed experiment and return traces and measured outcomes."""
    if seed not in SEEDS:
        raise ValueError(f"seed must be predeclared: {SEEDS}")
    if not isinstance(turns, int) or turns < 1 or turns > 16:
        raise ValueError("turns must be between 1 and the declared 16-turn budget")
    game = _new_game(seed, mode, shock=shock)
    world = game.world
    initial = _state(world)
    initial_total = initial["total_bread"]
    shock_loss = 0.0
    steps = []
    for turn in range(1, turns + 1):
        if shock and turn == 2:
            before = world.contents("stress_pantry", "bread")
            lost = min(4.0, before)
            pantry_inner = world._containers["stress_pantry"][1]["bread"]
            world.eng.set_attr(pantry_inner, "qty", before - lost)
            shock_loss = lost
        contexts = {name: game._context(name) for name in ACTORS if world.is_alive(name)}
        result = game.step()
        current = _state(world)
        selected = {}
        actions = {}
        for name, response in game.last_responses.items():
            proposal = response.major_action
            selected[name] = ({"action": proposal.action,
                               "params": dict(proposal.params),
                               "reason": proposal.reason} if proposal else None)
            actions[name] = game.last_results.get(name)
        steps.append({
            "turn": turn,
            "period": float(world.eng.node(world._town)["attrs"].get("period", 0.0)),
            "observations": {name: dict(ctx.observations) for name, ctx in contexts.items()},
            "affordances": {name: [dict(o) for o in ctx.affordances]
                            for name, ctx in contexts.items()},
            "selected_actions": selected,
            "action_results": actions,
            "status": result.get("status"),
            "state": current,
            "shock": ({"bread_removed": shock_loss,
                       "pantry_before": before,
                       "pantry_after": before - shock_loss}
                       if shock and turn == 2 else None),
        })
    final = _state(world)
    all_actions = [action for step in steps
                   for action in step["selected_actions"].values() if action]
    successful = sum(step["action_results"].get(actor) is True
                     for step in steps for actor in ACTORS)
    failed = sum(step["action_results"].get(actor) is False
                 for step in steps for actor in ACTORS)
    eaten = sum(action.get("action") == "eat"
                and step["action_results"].get(actor) is True
                for step in steps for actor, action in step["selected_actions"].items()
                if action)
    return {
        "schema": "bigville/package15-stress/1", "seed": seed,
        "policy": mode, "shock_enabled": shock, "turns": turns,
        "initial_state": initial, "final_state": final,
        "survivors": sum(final["alive"].values()),
        "hunger": final["hunger"],
        "resource_balance": {"initial": initial_total, "shock_loss": shock_loss,
                             "final": final["total_bread"],
                             "eaten": eaten,
                             "expected_final": initial_total - shock_loss - eaten,
                             "accounted_after_shock_and_eating": abs(final["total_bread"]
                                                           - (initial_total - shock_loss - eaten)) < 1e-8},
        "selected_action_counts": {action: sum(row["action"] == action for row in all_actions)
                                   for action in sorted({row["action"] for row in all_actions})},
        "failed_actions": failed, "successful_actions": successful,
        "transfers": sum(row["action"] == "transfer" for row in all_actions),
        "agent_observation_counts": {name: len(game.backends[name].observation_log)
                                     for name in ACTORS},
        "steps": steps,
    }


def run_package15(*, turns: int = 16) -> dict[str, Any]:
    """Run declared paired seeds plus a no-shock negative control."""
    paired = [run_stress_experiment(seed, policy, turns=turns)
              for seed in SEEDS for policy in ("sharing", "self_priority")]
    controls = [run_stress_experiment(seed, "sharing", shock=False, turns=turns)
                for seed in SEEDS]
    return {"schema": "bigville/package15-report/1", "seeds": list(SEEDS),
            "paired_runs": paired, "no_shock_controls": controls}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the package 15 stress experiment")
    parser.add_argument("--turns", type=int, default=16)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = json.dumps(run_package15(turns=args.turns), indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
