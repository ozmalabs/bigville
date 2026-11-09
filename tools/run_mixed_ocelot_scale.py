#!/usr/bin/env python3
"""Run a reproducible 20-resident mixed-backend scale smoke.

Run from the Ocelot checkout with its virtualenv and both repositories on
``PYTHONPATH``::

    cd /home/matt/ozmadev/ocelot
    BIGVILLE_ROOT=/home/matt/ozmadev/bigville \
      PYTHONPATH=/home/matt/ozmadev/ocelot:/home/matt/ozmadev/bigville \
      /home/matt/ozmadev/ocelot/.venv/bin/python \
      /home/matt/ozmadev/bigville/tools/run_mixed_ocelot_scale.py

This is a bounded smoke profile, not a town100 capacity claim. It uses the
resource/social scenario's physical rules with a synthetic 8x8 floor and ten
Ocelot plus ten simple residents, then runs eight autonomous turns.
"""
from __future__ import annotations

import copy
import json
import os
import resource
import time
from collections import Counter
from typing import Any

from bigville.api import create_game
from bigville.scenarios import load_scenario


SEED = 305000
TURNS = 8
OCELOT_COUNT = 10
SIMPLE_COUNT = 10
RUNTIME_BUDGET_SECONDS = 5.0
RSS_BUDGET_MIB = 1024.0


def _rss_mib() -> float:
    with open("/proc/self/statm", encoding="ascii") as stream:
        resident_pages = int(stream.read().split()[1])
    return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)


def _expanded_scenario() -> dict[str, Any]:
    scenario = load_scenario("resource_social_stress").to_dict()
    names = (["Ada", "Ben"] + [f"O{i:02}" for i in range(3, 11)]
             + ["Cy", "Dee"] + [f"S{i:02}" for i in range(3, 11)])
    actors = []
    for index, name in enumerate(names):
        actor = copy.deepcopy(scenario["actors"][index % 4])
        actor.update(name=name,
                     backend="ocelot" if index < OCELOT_COUNT else "simple",
                     home_cell=[1 + index % 6, 1 + index // 6])
        actor.pop("simple_profile", None)
        actors.append(actor)
    scenario["actors"] = actors
    scenario["map"] = {
        "grid": [["floor"] * 8 for _ in range(8)],
        "layout": {"w": 8, "h": 8,
                   "homes": [actor["home_cell"] for actor in actors]},
    }
    scenario["physical_subsystems"] = {
        "metabolism": False, "ecology": False, "decay": False,
    }
    return scenario


def run_scale_profile() -> dict[str, Any]:
    started = time.perf_counter()
    rss_start = _rss_mib()
    game = create_game(scenario=_expanded_scenario(), seed=SEED,
                       autonomous=True, default_backend="simple",
                       ticks_per_period=2)
    world = game.world
    names = list(game.characters)
    for name in names[:OCELOT_COUNT]:
        if game.backends[name].kind != "ocelot":
            raise RuntimeError(f"{name}: expected Ocelot backend")
    for name in names[OCELOT_COUNT:]:
        if game.backends[name].kind != "cheap":
            raise RuntimeError(f"{name}: expected simple backend")

    world.add_container("scale_pantry", kind="larder", holds=(), cell=(2, 2))
    pantry, inner_stocks = world._containers["scale_pantry"]
    bread = inner_stocks.get("bread") or world._new_inner_stock(
        pantry, "larder", "bread")
    inner_stocks["bread"] = bread
    world.eng.set_attr(bread, "qty", 100.0)
    for name in names:
        world.eng.set_attr(world._actors[name], "hunger", 0.65)
    for name in names[:OCELOT_COUNT]:
        world.actor_mind(name).seed_character(
            personality={"emotional_core_enabled": 1.0})

    setup_seconds = time.perf_counter() - started
    rss_after_setup = _rss_mib()
    actions: Counter[tuple[str, str, str]] = Counter()
    turn_seconds = []
    errors = []
    for turn in range(TURNS):
        if time.perf_counter() - started >= RUNTIME_BUDGET_SECONDS:
            raise TimeoutError("20-resident profile exceeded 5-second budget")
        turn_started = time.perf_counter()
        result = game.step()
        turn_seconds.append(time.perf_counter() - turn_started)
        if result.get("status") != "advanced":
            errors.append({"turn": turn + 1, "kind": "turn", "result": result})
        for name in names:
            response = game.last_responses.get(name)
            proposal = getattr(response, "major_action", None)
            action = getattr(proposal, "action", "<none>")
            applied = game.last_results.get(name)
            disposition = "no_proposal" if proposal is None else (
                "rejected" if applied is False else "applied")
            backend = game.backends[name].kind
            actions[(backend, action, disposition)] += 1
            if disposition == "rejected":
                errors.append({"turn": turn + 1, "kind": "rejected_action",
                               "actor": name, "action": action,
                               "backend": backend})

    total_seconds = time.perf_counter() - started
    rss_end = _rss_mib()
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    if total_seconds > RUNTIME_BUDGET_SECONDS:
        raise TimeoutError(f"profile took {total_seconds:.3f}s; budget is 5s")
    return {
        "profile": "mixed_ocelot_10_simple_10",
        "seed": SEED,
        "turns": TURNS,
        "resident_count": len(names),
        "backend_counts": {"ocelot": OCELOT_COUNT, "simple": SIMPLE_COUNT},
        "budgets": {"runtime_seconds": RUNTIME_BUDGET_SECONDS,
                    "peak_rss_mib": RSS_BUDGET_MIB},
        "budget_result": {"runtime_ok": total_seconds <= RUNTIME_BUDGET_SECONDS,
                          "peak_rss_ok": rss_peak <= RSS_BUDGET_MIB},
        "timing_seconds": {
            "setup": setup_seconds,
            "turns_total": sum(turn_seconds),
            "turn_mean": sum(turn_seconds) / len(turn_seconds),
            "turn_max": max(turn_seconds),
            "total": total_seconds,
        },
        "rss_mib": {"start": rss_start, "after_setup": rss_after_setup,
                    "end": rss_end, "peak": rss_peak,
                    "increase_after_setup": rss_after_setup - rss_start},
        "graph": {
            "world_nodes": len(list(world.eng.nodes())),
            "ocelot_nodes_by_resident": {
                name: len(list(world.actor_mind(name).s.nodes()))
                for name in names[:OCELOT_COUNT]
            },
        },
        "action_counts": [
            {"backend": backend, "action": action,
             "disposition": disposition, "count": count}
            for (backend, action, disposition), count in sorted(actions.items())
        ],
        "errors": errors,
    }


def main() -> None:
    print(json.dumps(run_scale_profile(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
