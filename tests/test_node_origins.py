"""NB03: per-node execution-namespace provenance and qualified ids.

``NodeRef`` stays an integer.  Provenance is carried beside it in the strict
graph checkpoint, and legacy checkpoints migrate every node to the documented
``"unqualified"`` origin.
"""
from __future__ import annotations

import copy
import json
import threading

import pytest

from bigville.bundles import ExecutionNamespace, QualifiedId
from bigville.runtime import BigvilleGraph, NodeRef


def _namespace(run_id="origin-run", *, tick=1, bundle_seq=0):
    return ExecutionNamespace(run_id=run_id, executor="local", shard=0,
                              tick=tick, bundle_seq=bundle_seq)


def test_unqualified_default_and_qualified_id():
    graph = BigvilleGraph()
    node = graph.add_node("Agent", {"name": "Ada"})

    assert BigvilleGraph.default_origin == "unqualified"
    assert graph.default_origin == "unqualified"
    assert graph.current_origin == "unqualified"
    assert graph.node_origin(node) == "unqualified"
    assert graph.qualified_id(node) == QualifiedId("unqualified", int(node))
    assert isinstance(node, int)
    assert isinstance(node, NodeRef)


def test_explicit_execution_namespace_stamps_nodes():
    graph = BigvilleGraph()
    namespace = _namespace("explicit", tick=4, bundle_seq=2)

    with graph.execution_namespace(namespace):
        assert graph.current_origin == namespace.name
        node = graph.add_node("Agent", {"name": "Ben"})
        assert graph.node_origin(node) == namespace.name

    assert graph.current_origin == "unqualified"
    assert graph.node_origin(node) == namespace.name
    assert graph.qualified_id(node) == QualifiedId(namespace.name, int(node))
    # The public node projection is unchanged: no origin key leaks into it.
    assert graph.node(node) == {"type": "Agent", "attrs": {"name": "Ben"}}


def test_nested_and_reentrant_namespace_contexts_restore():
    graph = BigvilleGraph()
    outer = _namespace("outer", bundle_seq=1)
    inner = _namespace("inner", bundle_seq=2)

    before = graph.add_node("Agent", {"order": "before"})
    with graph.execution_namespace(outer):
        outer_node = graph.add_node("Agent", {"order": "outer"})
        with graph.execution_namespace(inner):
            inner_node = graph.add_node("Agent", {"order": "inner"})
            with graph.execution_namespace(outer):
                reentrant = graph.add_node("Agent", {"order": "reentrant"})
        after_inner = graph.add_node("Agent", {"order": "after-inner"})
    after = graph.add_node("Agent", {"order": "after"})

    assert graph.node_origin(before) == "unqualified"
    assert graph.node_origin(outer_node) == outer.name
    assert graph.node_origin(inner_node) == inner.name
    assert graph.node_origin(reentrant) == outer.name
    assert graph.node_origin(after_inner) == outer.name
    assert graph.node_origin(after) == "unqualified"
    assert graph.current_origin == "unqualified"


def test_nodes_by_origin_is_ascending_by_node_id():
    graph = BigvilleGraph()
    first = _namespace("first", bundle_seq=1)
    second = _namespace("second", bundle_seq=2)

    with graph.execution_namespace(first):
        a1 = graph.add_node("Mark", {"n": 1})
    with graph.execution_namespace(second):
        b1 = graph.add_node("Mark", {"n": 2})
    with graph.execution_namespace(first):
        a2 = graph.add_node("Mark", {"n": 3})
    with graph.execution_namespace(second):
        b2 = graph.add_node("Mark", {"n": 4})

    assert graph.nodes_by_origin(first.name) == (a1, a2)
    assert graph.nodes_by_origin(second.name) == (b1, b2)
    assert graph.nodes_by_origin("missing") == tuple()
    assert list(graph.nodes_by_origin(first.name)) == sorted(graph.nodes_by_origin(first.name))


def test_threads_get_isolated_origins():
    graph = BigvilleGraph()
    barrier = threading.Barrier(2)
    results: dict[str, tuple[str, list[NodeRef]]] = {}
    errors: list[BaseException] = []

    def worker(key: str) -> None:
        namespace = _namespace(key, bundle_seq=len(key))
        try:
            with graph.execution_namespace(namespace):
                barrier.wait(timeout=5)
                refs = [graph.add_node("Threaded", {"worker": key})
                        for _ in range(25)]
                results[key] = (namespace.name, refs)
                barrier.wait(timeout=5)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(key,), name=f"origin-{key}")
               for key in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert set(results) == {"left", "right"}
    for key, (namespace, refs) in results.items():
        assert [graph.node_origin(ref) for ref in refs] == [namespace] * 25
        assert set(graph.nodes_by_origin(namespace)) == set(refs)

    # The spawning thread never entered either namespace.
    main = graph.add_node("Main", {})
    assert graph.node_origin(main) == "unqualified"


def test_checkpoint_round_trip_preserves_origins_and_node_refs():
    graph = BigvilleGraph()
    unqualified = graph.add_node("Agent", {"name": "Ada"})
    first = _namespace("checkpoint-a", bundle_seq=1)
    second = _namespace("checkpoint-b", bundle_seq=2)
    with graph.execution_namespace(first):
        a_node = graph.add_node("Item", {"name": "bell"})
    with graph.execution_namespace(second):
        b_node = graph.add_node("Item", {"name": "rope"})

    before = graph.to_checkpoint_dict()
    assert before["schema"] == "bigville/graph/1"
    assert before["origins"] == [
        [int(unqualified), "unqualified"],
        [int(a_node), first.name],
        [int(b_node), second.name],
    ]

    restored = BigvilleGraph.from_checkpoint_dict(json.loads(json.dumps(before)))

    assert restored.to_checkpoint_dict() == before
    assert restored.nodes() == [unqualified, a_node, b_node]
    assert all(isinstance(ref, int) for ref in restored.nodes())
    assert all(isinstance(ref, NodeRef) for ref in restored.nodes())
    assert restored.node_origin(unqualified) == "unqualified"
    assert restored.node_origin(a_node) == first.name
    assert restored.node_origin(b_node) == second.name
    assert restored.qualified_id(b_node) == QualifiedId(second.name, int(b_node))

    # New nodes use the live context, not any origin remembered from the save.
    next_node = restored.add_node("After", {})
    assert restored.node_origin(next_node) == "unqualified"


def test_legacy_checkpoint_without_origins_migrates_to_unqualified():
    graph = BigvilleGraph()
    namespace = _namespace("legacy-save")
    with graph.execution_namespace(namespace):
        node = graph.add_node("Agent", {"name": "Cy"})
    checkpoint = graph.to_checkpoint_dict()
    checkpoint.pop("origins")

    restored = BigvilleGraph.from_checkpoint_dict(checkpoint)

    assert restored.node_origin(node) == "unqualified"
    assert restored.qualified_id(node) == QualifiedId("unqualified", int(node))
    assert restored.to_checkpoint_dict()["origins"] == [[int(node), "unqualified"]]


def _valid_checkpoint():
    graph = BigvilleGraph()
    graph.add_node("Agent", {})
    graph.add_node("Item", {})
    return graph.to_checkpoint_dict()


@pytest.mark.parametrize("mutate, message", [
    (lambda data: data.update(origins={}), "origins must be a list"),
    (lambda data: data.update(origins=None), "origins must be a list"),
    (lambda data: data["origins"].append(copy.deepcopy(data["origins"][0])),
     "duplicate"),
    (lambda data: data["origins"].append([999, "ghost"]), "missing node ID"),
    (lambda data: data["origins"][0].__setitem__(1, 5), "origin name"),
    (lambda data: data["origins"][0].__setitem__(1, ""), "origin name"),
    (lambda data: data["origins"].pop(), "missing .* origin for node ID"),
    (lambda data: data["origins"].append(["one", "x"]), "origin node ID"),
    (lambda data: data["origins"].append(["bad"]), "invalid .* origin"),
])
def test_checkpoint_rejects_invalid_origins(mutate, message):
    checkpoint = _valid_checkpoint()
    mutate(checkpoint)

    with pytest.raises(ValueError, match=message):
        BigvilleGraph.from_checkpoint_dict(checkpoint)


def test_node_projection_shape_is_unchanged():
    graph = BigvilleGraph()
    namespace = _namespace("shape")
    with graph.execution_namespace(namespace):
        node = graph.add_node("Agent", {"name": "Ada"})

    assert graph.node(node) == {"type": "Agent", "attrs": {"name": "Ada"}}
    assert set(graph.node(node)) == {"type", "attrs"}
    assert "origin" not in graph.node(node)
    assert "origin" not in graph.graph_to_dict()["nodes"][0]


def test_execution_namespace_rejects_invalid_values():
    graph = BigvilleGraph()

    with pytest.raises(TypeError, match="string or ExecutionNamespace"):
        with graph.execution_namespace(42):
            pass
    with pytest.raises(ValueError, match="must not be empty"):
        with graph.execution_namespace(""):
            pass
    assert graph.current_origin == "unqualified"


def test_world_checkpoint_preserves_node_origins(tmp_path):
    from bigville.api import create_world
    from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint

    world = create_world(scenario="house_argument", seed=71)
    namespace = _namespace("world-checkpoint")
    with world.eng.execution_namespace(namespace):
        marker = world.eng.add_node("OriginMarker", {"value": 1})

    checkpoint = tmp_path / "world"
    save_world_checkpoint(world, checkpoint)
    restored = load_world_checkpoint(checkpoint)

    assert restored.eng.node_origin(marker) == namespace.name
    assert restored.eng.qualified_id(marker) == QualifiedId(namespace.name, int(marker))
    assert restored.eng.to_checkpoint_dict()["origins"] == [
        [int(ref), restored.eng.node_origin(ref)]
        for ref in sorted(restored.eng.nodes())
    ]
