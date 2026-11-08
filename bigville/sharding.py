"""In-process shard assignment for the tick graph (TG07).

This module is deliberately a *seam*, not a distribution system.  It assigns
each actor unit of a turn to a shard derived from the spatial resource it
touches, detects units whose declared resources span more than one shard, and
commits independent shards through the same ``BigvilleGame._run_component``
seam that the TG05 threaded executor uses.  The world stays a single in-process
object: every worker thread reads and writes the same canonical graph, protected
by the locks added in TG05.  Nothing here starts a process, opens a socket or
claims durability.

Design
------

``ShardMap`` maps resource kinds to owners:

- ``actor`` resources follow the actor's current cell;
- ``cell`` resources follow their own grid block;
- every other resource (``stock``, ``container``, ``item``, ``building``,
  ``job``, ``relationship``, ``utterance``, ``memory``, ``world``, ``witness``,
  ...) belongs to the coordinator.

The coordinator is also the fallback for actors without a position and for
units with no declared resources at all.  A unit that touches more than one
shard is a *cross-shard* unit: it must run at the coordinator barrier, before
the independent shards, so no worker observes a half-applied operation.

The mapping is intentionally conservative.  Any resource the pure TG04 graph
cannot place spatially sends its unit to the coordinator, which serialises it.
The failure mode is therefore lost parallelism, never an unarbitrated race.

Everything in this module is plain stdlib and importing it changes no existing
behaviour.  ``BigvilleGame`` imports it lazily inside the partitioned path, so a
serial or threaded game never pays for the import.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from worlds.tick_graph import Resource


def _cell(value: Any) -> tuple[int, int] | None:
    """Return ``(x, y)`` for a cell-like value, or ``None`` when it is not one."""
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def _actor_position(actor: Any, world: Any) -> tuple[int, int] | None:
    """Read one actor's position without importing or mutating the world."""
    reader = getattr(world, "actor_position", None)
    if callable(reader):
        try:
            return _cell(reader(actor))
        except Exception:
            return None
    positions = getattr(world, "_actor_positions", None)
    if isinstance(positions, Mapping):
        return _cell(positions.get(actor))
    return None


@dataclass(frozen=True)
class ShardPlan:
    """The deterministic shard assignment of one turn's actor units.

    ``by_shard`` contains every actor exactly once.  Units that execute at the
    coordinator barrier (cross-shard units and units owning a coordinator
    resource) are listed under ``shard_map.coordinator``.  ``cross_shard`` names
    only the subset whose declared resources span more than one shard;
    ``coordinator_units`` is the full set executed serially before the shards.
    """

    by_shard: dict[int, tuple[str, ...]]
    cross_shard: tuple[str, ...]
    coordinator_units: tuple[str, ...]

    def shard_of(self, actor: str) -> int | None:
        for shard, actors in self.by_shard.items():
            if actor in actors:
                return shard
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_shard": {str(shard): list(actors)
                         for shard, actors in sorted(self.by_shard.items())},
            "cross_shard": list(self.cross_shard),
            "coordinator_units": list(self.coordinator_units),
        }


class ShardMap:
    """Assign resources to in-process shard ids.

    ``cell_size`` is the side of one spatial shard in cells.  ``coordinator``
    is the shard id reserved for cross-shard and non-spatial work; the default
    ``0`` means spatial shards are always positive, so a spatial shard can never
    be mistaken for the coordinator.
    """

    def __init__(self, cell_size: int = 8, coordinator: int = 0) -> None:
        if not isinstance(cell_size, int) or isinstance(cell_size, bool) or cell_size < 1:
            raise ValueError("cell_size must be a positive integer")
        if not isinstance(coordinator, int) or isinstance(coordinator, bool):
            raise ValueError("coordinator must be an integer shard id")
        self.cell_size = int(cell_size)
        self.coordinator = int(coordinator)

    # -- resource owners -------------------------------------------------

    def cell_shard(self, cell: Any) -> int:
        """A stable shard id for the grid block containing ``cell``.

        Uses ``floor(x / cell_size)`` and ``floor(y / cell_size)`` so negative
        coordinates fall in the correct (non-zero) block.  The mixing constants
        are fixed integers rather than ``hash()``, which is salted per process.
        """
        point = _cell(cell)
        if point is None:
            return self.coordinator
        block_x = math.floor(point[0] / self.cell_size)
        block_y = math.floor(point[1] / self.cell_size)
        mixed = (block_x * 73856093) ^ (block_y * 19349663)
        shard = 1 + (mixed & 0x7FFFFFFF)
        if shard == self.coordinator:
            shard += 1
        return shard

    def actor_shard(self, actor: Any, world: Any) -> int:
        """The shard owning ``actor``'s current cell, or the coordinator."""
        position = _actor_position(actor, world)
        if position is None:
            return self.coordinator
        return self.cell_shard(position)

    def resource_shard(self, resource: Resource, world: Any) -> int:
        """The owner of one declared resource."""
        kind = str(getattr(resource, "kind", ""))
        if kind == "actor":
            return self.actor_shard(getattr(resource, "key", None), world)
        if kind == "cell":
            return self.cell_shard(getattr(resource, "key", None))
        if kind == "witness":
            key = getattr(resource, "key", None)
            # A cell witness belongs to the cell's shard; an observer-name
            # witness follows that observer's actor shard.
            if isinstance(key, (tuple, list)) and len(key) == 2:
                return self.cell_shard(key)
            return self.actor_shard(key, world)
        return self.coordinator

    def unit_shards(self, resources: Iterable[Resource], world: Any) -> frozenset[int]:
        """Every shard touched by one unit's declared read/write set."""
        return frozenset(self.resource_shard(resource, world)
                         for resource in resources)

    def is_cross_shard(self, resources: Iterable[Resource], world: Any) -> bool:
        """Whether one unit's declared resources span more than one shard."""
        return len(self.unit_shards(resources, world)) > 1

    def to_dict(self) -> dict[str, Any]:
        return {"cell_size": self.cell_size, "coordinator": self.coordinator}


def partition_units(units: Mapping[str, Iterable[Resource]], world: Any,
                    shard_map: ShardMap | None = None) -> ShardPlan:
    """Assign every actor unit to exactly one shard.

    ``units`` is ``{actor: resources}``.  Actors are emitted in lexicographic
    order inside each shard, so a plain dictionary's insertion order cannot
    change the plan.  A unit is placed at the coordinator when its resources
    span shards, when it owns a coordinator resource, or when it declares
    nothing (the same conservative fallback as the TG05 scheduler).
    """
    shard_map = shard_map or ShardMap()
    actors = sorted((str(actor) for actor in units), key=str)
    resources = {actor: tuple(units[actor]) for actor in actors}
    shards_by_actor = {
        actor: shard_map.unit_shards(resources[actor], world)
        for actor in actors
    }

    # EN04 follow-up: units that share a resource must land in the same
    # component, even when each unit's own resources fit one shard.  Without
    # this, two actors in different shards could write the same cell/witness
    # resource concurrently.  A component is placed at the coordinator when any
    # member touches a coordinator resource or the component spans shards.
    parent = {actor: actor for actor in actors}

    def find(actor: str) -> str:
        while parent[actor] != actor:
            parent[actor] = parent[parent[actor]]
            actor = parent[actor]
        return actor

    def union(left: str, right: str) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    by_resource: dict[Resource, list[str]] = {}
    for actor in actors:
        for resource in resources[actor]:
            by_resource.setdefault(resource, []).append(actor)
    for claimants in by_resource.values():
        first = claimants[0]
        for other in claimants[1:]:
            union(first, other)

    components: dict[str, list[str]] = {}
    for actor in actors:
        components.setdefault(find(actor), []).append(actor)

    grouped: dict[int, list[str]] = {}
    cross_shard: list[str] = []
    coordinator_units: list[str] = []
    for root in sorted(components):
        members = sorted(components[root], key=str)
        component_resources = {
            resource for member in members for resource in resources[member]
        }
        component_shards = shard_map.unit_shards(component_resources, world)
        own_cross = any(len(shards_by_actor[member]) > 1 for member in members)
        if (not component_shards or len(component_shards) > 1
                or shard_map.coordinator in component_shards):
            shard = shard_map.coordinator
        else:
            shard = next(iter(component_shards))
        grouped.setdefault(shard, []).extend(members)
        if own_cross or len(component_shards) > 1:
            cross_shard.extend(members)
        if shard == shard_map.coordinator:
            coordinator_units.extend(members)
    return ShardPlan(
        by_shard={shard: tuple(sorted(actors_in_shard))
                  for shard, actors_in_shard in grouped.items()},
        cross_shard=tuple(sorted(set(cross_shard))),
        coordinator_units=tuple(sorted(set(coordinator_units))),
    )


class PartitionedExecutor:
    """Commit one turn's actor units through in-process shards.

    This is a scaffold for real process/worker distribution, not a claim of it.
    All shards share the same ``BigvilleGame`` and world instance; the TG05
    locks and thread-local attempt state make that safe for the declared
    resource sets.  Coordination is a barrier in the calling thread: cross-shard
    and coordinator units run first, then independent shards run in a bounded
    ``ThreadPoolExecutor``.
    """

    def __init__(self, shard_map: ShardMap | None = None, workers: int | None = None) -> None:
        if workers is not None and (not isinstance(workers, int)
                                    or isinstance(workers, bool) or workers < 1):
            raise ValueError("workers must be a positive integer or None")
        self.shard_map = shard_map or ShardMap()
        self.workers = workers

    # -- planning --------------------------------------------------------

    def plan(self, units: Mapping[str, Iterable[Resource]], world: Any) -> ShardPlan:
        """Assign ``{actor: resources}`` to shards."""
        return partition_units(units, world, self.shard_map)

    @staticmethod
    def units(game: Any, order: Iterable[str], responses: Mapping[str, Any]) -> dict[str, set[Resource]]:
        """Build one resource set per non-joint actor, exactly like TG05.

        An actor with no declared operation, or a unit with a global write, is
        widened to ``Resource("world", "global")`` so the shard map places it at
        the coordinator rather than racing an undeclared effect.
        """
        graph = getattr(game, "last_tick_graph", None)
        units: dict[str, set[Resource]] = {}
        for actor in order:
            response = responses[actor]
            if game._is_joint(response):
                continue
            resources, global_write = game._unit_resources(graph, actor, response)
            resources = set(resources)
            if global_write or not resources:
                resources.add(Resource("world", "global"))
            units[actor] = resources
        return units

    # -- commit ----------------------------------------------------------

    def commit(self, game: Any, order: Iterable[str], responses: Mapping[str, Any],
               suppressed: Mapping[str, str] | None = None,
               plan: ShardPlan | None = None) -> dict[str, tuple[str, Any, Any]]:
        """Apply one turn's units and return the TG05 ``completed`` map.

        Cross-shard/coordinator units execute first, serially, in turn order.
        Every other shard is one component; independent shards run in a bounded
        pool.  The returned dictionary is rebuilt in turn order and carries only
        ``(actor, result, error)`` triples.  Result/error dictionaries on the
        game are written by the caller, never here.
        """
        order = list(order)
        suppressed = suppressed or {}
        if plan is None:
            plan = self.plan(self.units(game, order, responses), game.world)

        index_of = {actor: index for index, actor in enumerate(order)}
        completed: dict[str, tuple[str, Any, Any]] = {}

        coordinator = set(plan.coordinator_units)
        for actor in order:
            if actor not in coordinator:
                continue
            completed[actor] = game._apply_unit(
                actor, responses[actor], suppressed.get(actor))

        shards = [shard for shard in plan.by_shard
                  if shard != self.shard_map.coordinator]
        shards.sort()
        # EN04 follow-up: within a shard the actors must execute in the turn's
        # deterministic order, not the plan's lexicographic actor order.  Two
        # same-cell movers otherwise swap their terrain/exertion updates.
        components = [tuple(sorted(index_of[actor] for actor in plan.by_shard[shard]))
                      for shard in shards]
        components = [component for component in components if component]

        if not components:
            return {actor: completed[actor] for actor in order if actor in completed}

        limit = self.workers if self.workers is not None else len(components)
        if limit <= 1 or len(components) <= 1:
            for component in components:
                for actor, result, error in game._run_component(
                        order, responses, component, suppressed):
                    completed[actor] = (actor, result, error)
        else:
            with ThreadPoolExecutor(max_workers=min(limit, len(components)),
                                    thread_name_prefix="bigville-shard") as pool:
                futures = [pool.submit(game._run_component, order, responses,
                                       component, suppressed)
                           for component in components]
                results = [future.result() for future in futures]
            for rows in results:
                for actor, result, error in rows:
                    completed[actor] = (actor, result, error)

        return {actor: completed[actor] for actor in order if actor in completed}
