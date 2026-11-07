"""EN04: cheaper graph and derived reads.

The graph's public read shape is unchanged, but a serial game session skips the
process-wide read lock and may use ``node_attrs``.  A frozen decision snapshot
may also memoise pure reads (proximity rows, known recipes, bulk availability,
work candidates/previews, body/skill read-offs); the scope closes before the
action commit, so witness and after-state reads stay live.
"""
from __future__ import annotations

import threading

from bigville.api import create_game, create_world
from bigville.runtime import BigvilleGraph

SEED = 305000
A, B, C = "Ada", "Ben", "Cy"


def _room(*, actors=None):
    actors = actors or ((A, "resident", [1, 1]),
                        (B, "resident", [2, 2]),
                        (C, "farmer", [3, 3]))
    return {
        "id": "en04_reads_room",
        "name": "EN04 reads room",
        "map": {"grid": [["floor"] * 6 for _ in range(6)]},
        "actors": [{"name": name, "role": role, "home_cell": cell,
                    "backend": "simple"} for name, role, cell in actors],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False,
                                "decay": False},
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }


def _game(**kwargs):
    options = dict(scenario=_room(), seed=SEED, default_backend="simple",
                   autonomous=True, llm_log=False, snapshot_mode="on_demand")
    options.update(kwargs)
    return create_game(**options)


def _world():
    return create_world(scenario=_room(), seed=SEED)


def _brute_near(world, position, radius, *, alive_only=True, exclude=None):
    names = []
    for name in world._actors:
        if exclude is not None and name == exclude:
            continue
        if alive_only and not world.is_alive(name):
            continue
        other = world.actor_position(name)
        distance = world.distance(position, other) if other is not None else None
        if distance is not None and distance <= radius:
            names.append(name)
    return sorted(names)


# ------------------------------------------------------------------ graph fast path
def test_graph_fast_reads_match_the_locked_path():
    locked = BigvilleGraph()
    fast = BigvilleGraph(lock_reads=False)
    graph_pairs = []
    for graph in (locked, fast):
        first = graph.add_node("Agent", {"name": "Ada", "n": 1.0})
        second = graph.add_node("Place", {"name": "well"})
        graph.add_edge(first, "at", second)
        graph_pairs.append((graph, first, second))

    for graph, first, second in graph_pairs:
        assert graph.node(first) == {"type": "Agent",
                                     "attrs": {"name": "Ada", "n": 1.0}}
        assert graph.node_attrs(first) is graph.node(first)["attrs"]
        assert graph.has_node(first) is True
        assert graph.has_node(999999) is False
        assert graph.nodes("Agent") == [first]
        assert graph.neighbours(first, "at") == [second]
        assert graph.in_neighbours(second, "at") == [first]
        assert graph.has_edge(first, "at", second) is True
        assert graph.has_edge(first, "at", first) is False
        # The fast path keeps the historical int() coercion for ids.
        assert graph.node(str(int(first))) == graph.node(first)
        assert graph.has_node(str(int(second))) is True

    graph, first, _second = graph_pairs[1]
    graph.set_attr(first, "n", 2.0)
    assert graph.node_attrs(first)["n"] == 2.0

    # The read policy is not durable state.
    restored = BigvilleGraph.from_checkpoint_dict(graph.to_checkpoint_dict())
    assert restored.lock_reads is True
    assert restored.to_checkpoint_dict() == graph.to_checkpoint_dict()


def test_locked_graph_allows_a_writer_while_readers_run():
    graph = BigvilleGraph()  # default lock_reads=True
    node = graph.add_node("Agent", {"n": 0})
    stop = threading.Event()
    errors = []

    def writer():
        try:
            for index in range(1500):
                graph.set_attr(node, "n", index)
                graph.add_node("Tick", {"index": index})
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)
        finally:
            stop.set()

    thread = threading.Thread(target=writer, name="en04-graph-writer")
    thread.start()
    try:
        while not stop.is_set():
            graph.node(node)
            graph.node_attrs(node)
            graph.has_node(node)
            graph.neighbours(node, "none")
            graph.nodes("Tick")
    finally:
        thread.join()

    assert errors == []
    assert len(graph.nodes("Tick")) == 1500


def test_game_serial_skips_the_read_lock_and_threaded_keeps_it():
    serial = _game()
    assert serial.world.eng.lock_reads is False
    serial.executor = "threaded"
    assert serial.world.eng.lock_reads is True
    serial.executor = "serial"
    assert serial.world.eng.lock_reads is False

    threaded = _game(executor="threaded")
    assert threaded.world.eng.lock_reads is True
    result = threaded.step()
    assert result["status"] == "advanced"
    assert threaded.world.rules_pending is False


def test_context_workers_share_the_frozen_read_scope():
    game = _game()
    game.context_workers = 2
    result = game.step()
    assert result["status"] == "advanced"
    assert not game.world.rules_pending


# ------------------------------------------------------------------ proximity cache
def test_proximity_cache_matches_uncached_and_clears_after_mutation():
    world = _world()
    expected = _brute_near(world, (1, 1), 2)
    assert world.actors_near((1, 1), 2) == expected

    with world.decision_reads():
        first = world.actors_near((1, 1), 2)
        second = world.actors_near((1, 1), 2)
        assert first == second == expected
        assert world.actors_near((1, 1), 2, exclude=A) == [
            name for name in expected if name != A]
    # The cache is scope-bound: it never survives into the action commit.
    assert world._decision_read_cache() is None

    world._move_actor_to(B, (5, 5))
    moved = _brute_near(world, (1, 1), 2)
    assert world.actors_near((1, 1), 2) == moved
    assert B not in moved

    world.add_actor("Dee", role="resident", home_cell=[1, 1])
    world._move_actor_to("Dee", (1, 1))
    spawned = _brute_near(world, (1, 1), 0, alive_only=False)
    assert "Dee" in spawned
    assert world.actors_near((1, 1), 0, alive_only=False) == spawned

    world.eng.set_attr(world._actors[C], "alive", 0.0)
    assert C not in world.actors_near((3, 3), 0)
    assert C in world.actors_near((3, 3), 0, alive_only=False)


def test_occupancy_matches_actors_near_with_dead_residents():
    world = _world()
    world.eng.set_attr(world._actors[C], "alive", 0.0)
    assert world.occupancy_at((3, 3)) == 1
    assert world.occupancy_at((3, 3)) == len(
        world.actors_near((3, 3), 0, alive_only=False))
    assert world.occupancy_at(None) == 0
    assert world.occupancy_at((99, 99)) == 0


# ------------------------------------------------------------------ observation cache
def test_observe_cache_equals_uncached_without_cross_actor_leakage():
    game = _game()
    world = game.world
    reference_a = world.observe(A)
    reference_b = world.observe(B)

    with world.decision_reads():
        cached_a1 = world.observe(A)
        cached_a2 = world.observe(A)
        cached_b = world.observe(B)

    assert cached_a1 == cached_a2 == reference_a
    assert cached_b == reference_b
    # B's observation is B's own: leaked rows would name B as nearby to B.
    assert B not in {row["id"] for row in cached_b["nearby_actors"]}
    assert A in {row["id"] for row in cached_b["nearby_actors"]}


def test_observation_and_body_cache_do_not_survive_a_mutation():
    game = _game()
    world = game.world
    before = world.observe(A)
    with world.decision_reads():
        assert world.observe(A) == before
        body = world.body_state(A)
        assert world.strength(A) == body["strength"]
        assert world.effective_stamina(A) == body["stamina"]
        assert world._exhaustion_band(A)["step"] == body["exhaustion_step"]

    world.eng.set_attr(world._actors[A], "hunger", 0.75)
    world.eng.set_attr(world._bodies[A], "stamina_reserve", 0.1)
    after = world.observe(A)
    assert after["hunger"] == 0.75
    assert world.body_state(A)["stamina_reserve"] == 0.1
    assert after != before


def test_decision_read_caches_are_not_world_state():
    world = _world()
    before = set(world.__dict__)
    with world.decision_reads():
        world.observe(A)
        world.actors_near((1, 1), 8)
        assert world._decision_read_cache() is not None
    assert world._decision_read_cache() is None
    # The caches live module-side (weakly keyed by world), so a world
    # checkpoint serializer sees exactly the same instance fields as before.
    assert set(world.__dict__) == before


def test_work_candidates_equal_the_menu_filter_and_are_cached():
    world = create_world(scenario="town100", seed=SEED)
    actor = next(name for name in world._actors
                 if not world.busy(name) and world.is_alive(name))
    menu_work = {option["recipe"] for option in world.actor_affordances(actor)
                 if option.get("action") == "work"}
    expected = sorted(menu_work)[:world._OBSERVE_WORK_LIMIT]

    with world.decision_reads():
        first = world.observe(actor)["work_candidates"]
        second = world.observe(actor)["work_candidates"]
    assert first == second
    assert [entry["recipe"] for entry in first] == expected
    for entry in first:
        assert world.recipe_preview(actor, entry["recipe"])["ok"] is True
