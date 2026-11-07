from __future__ import annotations

import json
import copy

import pytest

from bigville.runtime import BigvilleGraph, NodeRef


def test_checkpoint_round_trip_preserves_graph_identity_types_and_allocator():
    graph = BigvilleGraph()
    agent = graph.add_node("Agent", {
        "tuple": ("north", 2),
        "set": {"x", "y"},
        "frozen": frozenset({1, 3}),
        "nested": {("key", 1): [NodeRef(3), {"a", "b"}]},
        "node_ref": NodeRef(2),
    })
    item = graph.add_node("Item", {"name": "bell"})
    graph.add_node("Removed", {})
    graph.remove_node(3)
    graph.load_seed_manifest("seed-name", agent)
    graph.load_seed_manifest({"id": "seed-payload", "spec": {"levels": (1, 2)}}, agent)
    before = graph.to_checkpoint_dict()

    restored = BigvilleGraph.from_checkpoint_dict(json.loads(json.dumps(before)))

    assert restored._inner is restored
    assert restored._next_id == graph._next_id
    assert restored.nodes() == graph.nodes()
    assert restored.node(agent)["attrs"] == graph.node(agent)["attrs"]
    assert isinstance(restored.node(agent)["attrs"]["node_ref"], NodeRef)
    assert isinstance(restored.node(agent)["attrs"]["tuple"], tuple)
    assert isinstance(restored.node(agent)["attrs"]["set"], set)
    assert isinstance(restored.node(agent)["attrs"]["frozen"], frozenset)
    assert restored.node(agent)["attrs"]["nested"] == graph.node(agent)["attrs"]["nested"]
    assert restored.seed_manifests == graph.seed_manifests
    assert restored.has_edge(agent, "holds_seed", next(
        node for node in restored.nodes("Seed")
        if restored.node(node)["attrs"]["id"] == "seed-payload"))
    assert restored.to_checkpoint_dict() == before

    next_node = restored.add_node("Next", {})
    assert next_node == NodeRef(graph._next_id)


def test_checkpoint_rejects_unsupported_graph_values():
    graph = BigvilleGraph()
    graph.add_node("Bad", {"value": object()})

    with pytest.raises(TypeError, match="unsupported graph value"):
        graph.to_checkpoint_dict()


@pytest.mark.parametrize("mutate, message", [
    (lambda data: data.update(schema="unknown"), "schema"),
    (lambda data: data.update(next_id=1), "next_id"),
    (lambda data: data["edges"].append({"source": 90, "kind": "x", "target": 1}),
     "missing node"),
    (lambda data: data["nodes"].append(copy.deepcopy(data["nodes"][0])), "duplicate"),
])
def test_checkpoint_loader_rejects_invalid_graphs(mutate, message):
    graph = BigvilleGraph()
    graph.add_node("Agent", {})
    checkpoint = graph.to_checkpoint_dict()
    mutate(checkpoint)

    with pytest.raises(ValueError, match=message):
        BigvilleGraph.from_checkpoint_dict(checkpoint)
