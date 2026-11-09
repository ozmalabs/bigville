from __future__ import annotations

import json
import importlib
import sys
import time
from collections import Counter
from pathlib import Path

import pytest


_BIGVILLE_ROOT = Path(__file__).resolve().parents[1]
_OCELOT_ROOT = _BIGVILLE_ROOT.parent / "ocelot"


def _resource_state(world):
    actors = ("Ada", "Ben", "Cy", "Dee")
    return {
        "turn": int(world._turn),
        "pantry_bread": float(world.contents("phase6_pantry", "bread")),
        "residents": {
            actor: {
                "hunger": float(world.eng.node(world._actors[actor])["attrs"].get("hunger", 0.0)),
                "energy": float(world.energy(actor)),
                "position": list(world.actor_position(actor) or ()),
                "inventory": dict(world.inventory(actor)),
            }
            for actor in actors
        },
    }


def _actions(game):
    from bigville.game_persistence import _response_to_checkpoint

    return {actor: _response_to_checkpoint(response)
            for actor, response in game.last_responses.items()}


def _assert_same_live_state(left, right):
    assert left.world.eng.to_checkpoint_dict() == right.world.eng.to_checkpoint_dict()
    assert left.world.export_state() == right.world.export_state()
    assert _actions(left) == _actions(right)
    assert left.last_results == right.last_results
    assert set(left._continuations) == set(right._continuations)
    for actor in left._continuations:
        assert left._continuations[actor].request.to_dict() == \
            right._continuations[actor].request.to_dict()
        assert left._continuations[actor].baseline_events == \
            right._continuations[actor].baseline_events
    for actor in ("Ada", "Ben"):
        left_mind = left.world.actor_mind(actor)
        right_mind = right.world.actor_mind(actor)
        left_graph = left_mind.s.graph_to_dict()
        right_graph = right_mind.s.graph_to_dict()
        def graph_inventory(graph):
            labels = {node["id"]: json.dumps(
                [node["type"], node["attrs"]], sort_keys=True, separators=(",", ":"))
                for node in graph["nodes"]}
            nodes = Counter(labels.values())
            edges = Counter((labels[edge["src"]], edge["type"], labels[edge["tgt"]],
                             json.dumps(edge.get("attrs", {}), sort_keys=True))
                            for edge in graph["edges"])
            return nodes, edges

        # Ocelot's native graph can allocate different IDs for new transient
        # cognition receipts after reload. Compare typed/attributed node and edge
        # inventories (including multiplicity); continuation behavior and the
        # village's canonical graph are compared exactly above.
        assert graph_inventory(left_graph) == graph_inventory(right_graph)
        left_state, right_state = left_mind.dump_held_state(), right_mind.dump_held_state()
        assert left_state["decision"] == right_state["decision"]
        assert left_state["identity"] == right_state["identity"]
        assert left_state["personality"] == right_state["personality"]


def test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control(
        monkeypatch, tmp_path):
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

    from bigville.api import create_game
    from bigville.game_persistence import load_game_checkpoint, save_game_checkpoint
    from bigville.scenarios import load_scenario
    from worlds.bigville_ocelot_adapter import BigvilleOcelotResident

    seed = 305000
    actors = ("Ada", "Ben", "Cy", "Dee")
    ocelot_actors = ("Ada", "Ben")
    scenario = load_scenario("resource_social_stress").to_dict()
    for actor in scenario["actors"]:
        actor["backend"] = "ocelot" if actor["name"] in ocelot_actors else "simple"
        actor.pop("simple_profile", None)
    scenario["physical_subsystems"] = {
        "metabolism": False, "ecology": False, "decay": False}

    started = time.perf_counter()
    game = create_game(scenario=scenario, seed=seed, autonomous=True,
                       default_backend="simple", ticks_per_period=2)
    world = game.world
    world.add_container("phase6_pantry", kind="larder", holds=(), cell=(2, 2))
    pantry, inners = world._containers["phase6_pantry"]
    bread = inners.get("bread") or world._new_inner_stock(pantry, "larder", "bread")
    inners["bread"] = bread
    world.eng.set_attr(bread, "qty", 12.0)
    for actor in actors:
        world.eng.set_attr(world._actors[actor], "hunger", 0.65)
    for actor in ocelot_actors:
        world.actor_mind(actor).seed_character(personality={"emotional_core_enabled": 1.0})
    setup_seconds = time.perf_counter() - started

    # Advance to the checkpoint boundary with two real mixed-backend turns.
    for _ in range(2):
        result = game.step()
        assert result["status"] == "advanced"
    checkpoint_state = _resource_state(world)

    checkpoint = tmp_path / "phase6-midpoint"
    checkpoint_started = time.perf_counter()
    save_game_checkpoint(game, checkpoint)
    checkpoint_seconds = time.perf_counter() - checkpoint_started
    restored = load_game_checkpoint(
        checkpoint,
        resident_loader=lambda _name, path: BigvilleOcelotResident.load(path),
    )
    restore_seconds = time.perf_counter() - checkpoint_started - checkpoint_seconds
    _assert_same_live_state(game, restored)

    continuation_started = time.perf_counter()
    for _ in range(2):
        control_result = game.step()
        restored_result = restored.step()
        assert control_result["status"] == restored_result["status"] == "advanced"
        _assert_same_live_state(game, restored)
    continuation_seconds = time.perf_counter() - continuation_started
    total_seconds = time.perf_counter() - started
    final_state = _resource_state(restored.world)
    checkpoint_bytes = sum(file.stat().st_size for file in checkpoint.rglob("*")
                           if file.is_file())
    metrics = {
        "seed": seed, "checkpoint_turn": checkpoint_state["turn"],
        "final_turn": final_state["turn"], "setup_seconds": setup_seconds,
        "checkpoint_save_seconds": checkpoint_seconds,
        "checkpoint_restore_seconds": restore_seconds,
        "continued_branch_seconds": continuation_seconds,
        "total_seconds": total_seconds, "checkpoint_bytes": checkpoint_bytes,
        "checkpoint_resources": checkpoint_state,
        "final_resources": final_state,
        "world_node_count": len(restored.world.eng.nodes()),
        "world_edge_count": sum(len(targets) for targets in restored.world.eng._edges.values()),
        "ocelot_graph_nodes": {
            actor: len(restored.world.actor_mind(actor).s.nodes()) for actor in ocelot_actors},
    }
    print("PHASE6_MIDPOINT_CHECKPOINT_METRICS=" + json.dumps(metrics, sort_keys=True))
    assert metrics["final_turn"] == 4
    assert metrics["total_seconds"] < 30.0
