"""Bounded, representative mixed-backend village run with real Ocelot minds.

Run from the Ocelot checkout (or set its root as the current directory) with
both repositories and the DSL bindings on ``PYTHONPATH``. The fixture uses the
four-resident resource/social scenario, replacing two simple backends with
real Ocelot residents while retaining two ordinary simple residents.
"""
from __future__ import annotations

import time
from typing import Any

from .api import create_game
from .backends import ActorResponse, ProposedAction
from .scenarios import load_scenario


ACTORS = ("Ada", "Ben", "Cy", "Dee")
OCELOT_ACTORS = ("Ada", "Ben")
MAX_TURNS = 8
MAX_RUNTIME_SECONDS = 5.0
SEED = 305000


def _snapshot(world) -> dict[str, Any]:
    return {
        "turn": int(world._turn),
        "pantry_bread": float(world.contents("phase6_pantry", "bread")),
        "residents": {
            name: {
                "hunger": float(world.eng.node(world._actors[name])["attrs"].get("hunger", 0.0)),
                "energy": float(world.energy(name)),
                "position": list(world.actor_position(name) or ()),
                "inventory": dict(world.inventory(name)),
            }
            for name in ACTORS
        },
    }


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed = {}
    if before["pantry_bread"] != after["pantry_bread"]:
        changed["pantry_bread"] = {
            "before": before["pantry_bread"], "after": after["pantry_bread"]}
    residents = {}
    for actor in ACTORS:
        fields = {
            key: {"before": before["residents"][actor][key],
                  "after": after["residents"][actor][key]}
            for key in before["residents"][actor]
            if before["residents"][actor][key] != after["residents"][actor][key]
        }
        if fields:
            residents[actor] = fields
    changed["residents"] = residents
    return changed


def run_mixed_ocelot_village(*, seed: int = SEED, turns: int = MAX_TURNS,
                             runtime_budget_seconds: float = MAX_RUNTIME_SECONDS,
                             rejection_probe: bool = True) -> dict[str, Any]:
    """Run a fixed-seed mixed village and return a JSON-safe trace.

    The hard limits are eight world turns and five seconds. The probe is one
    deliberate invalid proposal after the normal run; it measures rejection
    and Ocelot feedback without changing the village's world state.
    """
    if seed != SEED:
        raise ValueError(f"the representative run is fixed at seed {SEED}")
    if isinstance(turns, bool) or not isinstance(turns, int) or not 1 <= turns <= MAX_TURNS:
        raise ValueError(f"turns must be in [1, {MAX_TURNS}]")
    if (not isinstance(runtime_budget_seconds, (int, float))
            or isinstance(runtime_budget_seconds, bool)
            or not 0 < float(runtime_budget_seconds) <= MAX_RUNTIME_SECONDS):
        raise ValueError(f"runtime budget must be in (0, {MAX_RUNTIME_SECONDS:g}] seconds")

    started = time.perf_counter()
    scenario = load_scenario("resource_social_stress").to_dict()
    for actor in scenario["actors"]:
        actor["backend"] = "ocelot" if actor["name"] in OCELOT_ACTORS else "simple"
        # This harness uses the stock simple backend for its two simple actors.
        actor.pop("simple_profile", None)
    scenario["physical_subsystems"] = {
        "metabolism": False, "ecology": False, "decay": False}
    game = create_game(scenario=scenario, seed=seed, autonomous=True,
                       default_backend="simple", ticks_per_period=2)
    world = game.world
    for actor in ACTORS:
        expected = "ocelot" if actor in OCELOT_ACTORS else "cheap"
        actual = game.backends[actor].kind
        if actual != expected:
            raise RuntimeError(f"{actor}: expected backend {expected}, got {actual}")

    world.add_container("phase6_pantry", kind="larder", holds=(), cell=(2, 2))
    pantry, inners = world._containers["phase6_pantry"]
    bread = inners.get("bread") or world._new_inner_stock(pantry, "larder", "bread")
    inners["bread"] = bread
    world.eng.set_attr(bread, "qty", 12.0)
    for actor in ACTORS:
        world.eng.set_attr(world._actors[actor], "hunger", 0.65)

    # Explicitly enable each Ocelot resident's existing emotional appraisal
    # so action outcome receipts are inspectable in its graph.
    for actor in OCELOT_ACTORS:
        world.actor_mind(actor).seed_character(
            personality={"emotional_core_enabled": 1.0})

    setup_seconds = time.perf_counter() - started
    initial = _snapshot(world)
    steps = []
    run_started = time.perf_counter()
    for _ in range(turns):
        elapsed = time.perf_counter() - started
        if elapsed >= runtime_budget_seconds:
            raise TimeoutError(
                f"mixed Ocelot village exceeded {runtime_budget_seconds:g}s budget")
        before = _snapshot(world)
        contexts = {actor: game._context(actor) for actor in ACTORS if world.is_alive(actor)}
        turn_started = time.perf_counter()
        result = game.step()
        turn_seconds = time.perf_counter() - turn_started
        if time.perf_counter() - started >= runtime_budget_seconds:
            raise TimeoutError(
                f"mixed Ocelot village exceeded {runtime_budget_seconds:g}s budget")
        if result["status"] != "advanced":
            raise RuntimeError(f"unattended run stopped: {result}")
        after = _snapshot(world)
        actions = {}
        for actor in ACTORS:
            response = game.last_responses.get(actor)
            proposal = response.major_action if response else None
            actions[actor] = {
                "backend": game.backends[actor].kind,
                "observation": {
                    "hunger": contexts.get(actor).observations.get("hunger")
                    if actor in contexts else None,
                    "energy": contexts.get(actor).observations.get("energy")
                    if actor in contexts else None,
                    "affordance_count": len(contexts[actor].affordances)
                    if actor in contexts else 0,
                },
                "proposal": ({"action": proposal.action,
                              "params": dict(proposal.params),
                              "reason": proposal.reason} if proposal else None),
                "applied": game.last_results.get(actor),
            }
        steps.append({"turn": after["turn"], "seconds": turn_seconds,
                      "actions": actions, "state_delta": _delta(before, after),
                      "state": after})

    rejection = None
    if rejection_probe:
        actor = OCELOT_ACTORS[0]
        response = ActorResponse(major_action=ProposedAction(
            "phase6_invalid_probe", {}, "deliberate invalid-action rejection probe"))
        rejected = game._apply_response(actor, response) is False
        rejection = {"actor": actor, "action": "phase6_invalid_probe",
                     "rejected": rejected}

    minds = {}
    for actor in OCELOT_ACTORS:
        mind = world.actor_mind(actor)
        app = (dict(mind.s.node(mind._emotion_appraisal)["attrs"])
               if getattr(mind, "_emotion_appraisal", None) is not None else {})
        minds[actor] = {
            "cognitive_observations": len(list(mind.s.nodes("CognitiveObservation"))),
            "memory_nodes": len(list(mind.s.nodes("Memory"))),
            "held_memories": len(game.characters[actor].memories),
            "selected_action": dict(world._actor_decisions[actor]),
            "appraisal": {key: app.get(key) for key in (
                "individual_benefit", "individual_cost", "step", "goal_blocked",
                "collective_success") if key in app},
            "emotional_state": mind.emotional_state(),
        }
    total_seconds = time.perf_counter() - started
    if total_seconds >= runtime_budget_seconds:
        raise TimeoutError(
            f"mixed Ocelot village exceeded {runtime_budget_seconds:g}s budget")
    return {
        "schema": "bigville/mixed-ocelot-village/1",
        "scenario": "resource_social_stress",
        "seed": seed,
        "turn_budget": turns,
        "hard_runtime_budget_seconds": float(runtime_budget_seconds),
        "timing": {
            "setup_seconds": setup_seconds,
            "run_seconds": time.perf_counter() - run_started,
            "total_seconds": total_seconds,
            "mean_turn_seconds": sum(step["seconds"] for step in steps) / len(steps),
        },
        "backend_assignment": {actor: game.backends[actor].kind for actor in ACTORS},
        "initial_state": initial,
        "steps": steps,
        "final_state": _snapshot(world),
        "ocelot_minds": minds,
        "rejection_probe": rejection,
    }
