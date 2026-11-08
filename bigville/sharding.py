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
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping

from worlds.tick_graph import Resource

from .bundle_checks import (TickBundleLog, bundle_execution_sha,
                            bundle_output_sha)
from .bundles import (Bundle, BundleAck, BundleOperation, BundleResult,
                      ExecutionNamespace, LocalBundleTransport, QualifiedId)


class BundleDispatchError(RuntimeError):
    """A bundle result could not be validated or committed."""


class BundleResultError(BundleDispatchError):
    """A dispatched bundle returned a stale, mismatched or failed result."""


def _base_version(world: Any) -> int:
    """The monotonic plan version for a turn.

    The world has no general revision counter in this phase, so the contract is
    the world turn number (``world._turn``), which ``BigvilleGame`` advances
    before it builds the tick graph.  It is deterministic and never depends on
    wall time.  A world without ``_turn`` uses version 0.
    """
    turn = getattr(world, "_turn", None)
    if turn is None:
        return 0
    try:
        return max(0, int(turn))
    except (TypeError, ValueError):
        return 0


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

    def __init__(self, shard_map: ShardMap | None = None, workers: int | None = None,
                 *, transport: Any = None,
                 bundle_executor: Callable[[Bundle], BundleResult] | None = None) -> None:
        if workers is not None and (not isinstance(workers, int)
                                    or isinstance(workers, bool) or workers < 1):
            raise ValueError("workers must be a positive integer or None")
        if transport is not None and not (
                callable(getattr(transport, "dispatch", None))
                and callable(getattr(transport, "acknowledge", None))):
            raise ValueError("transport must implement dispatch/acknowledge")
        if bundle_executor is not None and not callable(bundle_executor):
            raise ValueError("bundle_executor must be callable or None")
        self.shard_map = shard_map or ShardMap()
        self.workers = workers
        # NB04: an injected transport (or executor) is the test/transport seam.
        # With neither, ``commit`` creates a fresh ``LocalBundleTransport``.
        self.transport = transport
        self.bundle_executor = bundle_executor
        self.last_transport = None
        self.last_log: TickBundleLog | None = None

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

    # -- bundle plan -----------------------------------------------------

    def component_groups(self, order: Iterable[str], plan: ShardPlan) -> tuple[tuple[int, ...], ...]:
        """The deterministic commit groups, as index tuples into ``order``.

        The coordinator group runs first as one serial bundle; every spatial
        shard is then one bundle.  Inside a group indices are in turn order,
        matching the EN04 fix for same-cell movers.  Every non-joint actor
        appears exactly once and the group order is the plan/commit order.
        """
        order = list(order)
        index_of = {actor: index for index, actor in enumerate(order)}
        coordinator = set(plan.coordinator_units)
        groups: list[tuple[int, ...]] = []
        coordinator_indices = tuple(
            index for index, actor in enumerate(order) if actor in coordinator)
        if coordinator_indices:
            groups.append(coordinator_indices)
        for shard in sorted(shard for shard in plan.by_shard
                            if shard != self.shard_map.coordinator):
            indices = tuple(sorted(index_of[actor]
                                   for actor in plan.by_shard[shard]))
            if indices:
                groups.append(indices)
        return tuple(groups)

    def plan_bundles(self, game: Any, order: Iterable[str],
                     responses: Mapping[str, Any], plan: ShardPlan | None = None,
                     *, base_version: int | None = None
                     ) -> tuple[tuple[Bundle, tuple[int, ...]], ...]:
        """Build one deterministic bundle per coordinator/shard group.

        Operations come from ``game.last_tick_graph`` and include every
        operation owned by the group's actors (major action, speech, memory),
        including an actor's ``idle`` operation when it has no major action.
        The bundle read/write sets are the union of its operations' resources.
        """
        order = list(order)
        if plan is None:
            plan = self.plan(self.units(game, order, responses), game.world)
        graph = getattr(game, "last_tick_graph", None)
        version = _base_version(game.world) if base_version is None else int(base_version)
        run_id = game.run_id
        coordinator_shard = self.shard_map.coordinator
        coordinator = set(plan.coordinator_units)

        entries: list[tuple[Bundle, tuple[int, ...]]] = []
        for seq, indices in enumerate(self.component_groups(order, plan)):
            actors = [order[index] for index in indices]
            shard = (coordinator_shard if any(actor in coordinator for actor in actors)
                     else plan.shard_of(actors[0]))
            namespace = ExecutionNamespace(
                run_id=run_id, executor="partitioned", shard=int(shard),
                tick=version, bundle_seq=seq)
            operations: list[BundleOperation] = []
            reads: list[Resource] = []
            writes: list[Resource] = []
            seen_reads: set[Resource] = set()
            seen_writes: set[Resource] = set()
            for actor in actors:
                for operation in (graph.operations if graph is not None else ()):
                    if operation.kind == "joint" or operation.actor != actor:
                        continue
                    operations.append(BundleOperation(
                        op_id=operation.op_id,
                        actor=operation.actor,
                        kind=operation.kind,
                        params=dict(operation.payload),
                        reads=operation.reads,
                        writes=operation.writes,
                        tiebreak=operation.tiebreak,
                    ))
                    for resource in operation.reads:
                        if resource not in seen_reads:
                            seen_reads.add(resource)
                            reads.append(resource)
                    for resource in operation.writes:
                        if resource not in seen_writes:
                            seen_writes.add(resource)
                            writes.append(resource)
            bundle = Bundle(
                bundle_id=namespace.name,
                namespace=namespace,
                run_id=run_id,
                tick=version,
                shard=int(shard),
                base_version=version,
                operations=tuple(operations),
                reads=tuple(reads),
                writes=tuple(writes),
                tiebreak=tuple(indices),
            )
            entries.append((bundle, tuple(indices)))
        return tuple(entries)

    def build_bundles(self, game: Any, order: Iterable[str],
                      responses: Mapping[str, Any], plan: ShardPlan | None = None,
                      *, base_version: int | None = None) -> tuple[Bundle, ...]:
        """The bundles of :meth:`plan_bundles`, without their index tuples."""
        return tuple(bundle for bundle, _indices in
                     self.plan_bundles(game, order, responses, plan,
                                       base_version=base_version))

    # -- bundle execution -------------------------------------------------

    def make_bundle_executor(self, game: Any, order: Iterable[str],
                             responses: Mapping[str, Any],
                             suppressed: Mapping[str, str] | None,
                             indices_by_id: Mapping[str, tuple[int, ...]]
                             ) -> Callable[[Bundle], BundleResult]:
        """Build the in-process reference callback for one commit.

        The callback applies the group's actors through ``game._run_component``
        inside ``world.eng.execution_namespace(bundle.namespace)``, then records
        the nodes that namespace created and returns a checksummed
        ``BundleResult``.  A per-actor contained error remains a row error and
        the result is still ``ok`` (the historical serial semantics); only an
        unexpected callback exception becomes ``status="error"``.
        """
        order = list(order)
        suppressed = suppressed or {}
        graph = getattr(getattr(game, "world", None), "eng", None)

        def nodes_for(namespace: ExecutionNamespace) -> set[Any]:
            finder = getattr(graph, "nodes_by_origin", None)
            if not callable(finder):
                return set()
            return set(finder(namespace.name))

        def execute(bundle: Bundle) -> BundleResult:
            indices = indices_by_id.get(bundle.bundle_id)
            if indices is None:
                raise BundleDispatchError(
                    f"no component for bundle {bundle.bundle_id!r}")
            before = nodes_for(bundle.namespace)
            status, reason = "ok", ""
            try:
                scoped = getattr(graph, "execution_namespace", None)
                if callable(scoped):
                    with scoped(bundle.namespace):
                        rows = game._run_component(
                            order, responses, indices, suppressed)
                else:
                    rows = game._run_component(
                        order, responses, indices, suppressed)
            except Exception as exc:  # a transport-level failure, not a unit error
                status = "error"
                reason = f"{type(exc).__name__}: {exc}"
                rows = ()
            created = sorted(nodes_for(bundle.namespace) - before)
            created_ids = tuple(
                QualifiedId(bundle.namespace.name, int(node)) for node in created)
            provisional = BundleResult(
                bundle_id=bundle.bundle_id,
                namespace=bundle.namespace,
                base_version=bundle.base_version,
                status=status,
                effects=(),
                created_ids=created_ids,
                result=tuple(tuple(row) for row in rows),
                output_sha="pending",
                execution_sha="pending",
                reason=reason,
            )
            output_sha = bundle_output_sha(provisional)
            provisional = replace(provisional, output_sha=output_sha)
            execution_sha = bundle_execution_sha(bundle, provisional)
            return replace(provisional, execution_sha=execution_sha)

        return execute

    # -- dispatch and acknowledgement ------------------------------------

    @staticmethod
    def validate_result(bundle: Bundle, result: BundleResult) -> None:
        """Reject a result that does not belong to this exact dispatch."""
        if not isinstance(result, BundleResult):
            raise BundleResultError(
                f"bundle {bundle.bundle_id!r} returned "
                f"{type(result).__name__}, not a BundleResult")
        if result.bundle_id != bundle.bundle_id:
            raise BundleResultError(
                f"result bundle_id {result.bundle_id!r} does not match "
                f"{bundle.bundle_id!r}")
        if result.namespace != bundle.namespace:
            raise BundleResultError(
                f"result namespace {result.namespace.name!r} does not match "
                f"{bundle.namespace.name!r}")
        if result.base_version != bundle.base_version:
            raise BundleResultError(
                f"stale result for {bundle.bundle_id!r}: base_version "
                f"{result.base_version} != {bundle.base_version}")

    @staticmethod
    def ack_for(bundle: Bundle, result: BundleResult) -> BundleAck:
        """The coordinator's ack for one validated result.

        ``ok`` and ``refused`` commit; per-actor row errors are contained and do
        not change that (they are the existing serial outcome).  ``retry`` and
        ``error`` are non-committed.  No separate revision is written per
        bundle, so ``committed_version`` is the turn's plan base version.
        """
        if result.status in ("ok", "refused"):
            return BundleAck(
                bundle_id=bundle.bundle_id,
                base_version=bundle.base_version,
                outcome="committed",
                committed_version=bundle.base_version,
                execution_sha=result.execution_sha,
                reason=result.reason,
            )
        outcome = "retry" if result.status == "retry" else "rejected"
        return BundleAck(
            bundle_id=bundle.bundle_id,
            base_version=bundle.base_version,
            outcome=outcome,
            committed_version=None,
            execution_sha=result.execution_sha,
            reason=result.reason or f"result status {result.status}",
        )

    def dispatch_bundles(self, bundles: Iterable[Bundle], transport: Any) -> tuple[BundleResult, ...]:
        """Dispatch bundles in order through ``transport`` (test seam)."""
        return tuple(transport.dispatch(bundle) for bundle in bundles)

    # -- commit ----------------------------------------------------------

    def commit(self, game: Any, order: Iterable[str], responses: Mapping[str, Any],
               suppressed: Mapping[str, str] | None = None,
               plan: ShardPlan | None = None, *,
               base_version: int | None = None,
               transport: Any = None,
               bundle_executor: Callable[[Bundle], BundleResult] | None = None
               ) -> dict[str, tuple[str, Any, Any]]:
        """Apply one turn's units as acknowledged bundles.

        The coordinator group runs first, serially; independent spatial shards
        then run in a bounded pool, exactly as before.  Results are validated,
        recorded, acknowledged and committed in plan order, never completion
        order.  The returned dictionary is rebuilt in turn order and carries
        only ``(actor, result, error)`` triples.  Result/error dictionaries on
        the game are written by the caller, never here.
        """
        order = list(order)
        suppressed = suppressed or {}
        if plan is None:
            plan = self.plan(self.units(game, order, responses), game.world)
        entries = self.plan_bundles(game, order, responses, plan,
                                    base_version=base_version)
        version = (entries[0][0].base_version if entries
                   else (_base_version(game.world) if base_version is None
                         else int(base_version)))
        log = TickBundleLog(game.run_id, version)
        self.last_log = log
        if hasattr(game, "last_bundle_log"):
            game.last_bundle_log = log

        for bundle, _indices in entries:
            log.dispatch(bundle)
        if not entries:
            return {}

        indices_by_id = {bundle.bundle_id: indices
                         for bundle, indices in entries}
        chosen_transport = transport or self.transport
        chosen_executor = bundle_executor or self.bundle_executor
        if chosen_executor is None:
            chosen_executor = self.make_bundle_executor(
                game, order, responses, suppressed, indices_by_id)
        if chosen_transport is None:
            chosen_transport = LocalBundleTransport(chosen_executor)
        self.last_transport = chosen_transport

        results: list[BundleResult] = []
        coordinator_shard = self.shard_map.coordinator
        first = entries[0][0]
        if first.shard == coordinator_shard and len(entries) > 1:
            results.append(chosen_transport.dispatch(first))
            remaining = [bundle for bundle, _indices in entries[1:]]
            results.extend(self._dispatch_ordered(remaining, chosen_transport))
        else:
            results.extend(self._dispatch_ordered(
                [bundle for bundle, _indices in entries], chosen_transport))

        completed: dict[str, tuple[str, Any, Any]] = {}
        for (bundle, _indices), result in zip(entries, results):
            try:
                self.validate_result(bundle, result)
            except BundleResultError as exc:
                # A malformed/stale result is rejected, never merged.  Only a
                # real BundleResult can contribute the checksum an ack needs.
                if isinstance(result, BundleResult):
                    ack = BundleAck(
                        bundle_id=bundle.bundle_id,
                        base_version=bundle.base_version,
                        outcome="rejected",
                        committed_version=None,
                        execution_sha=result.execution_sha,
                        reason=str(exc),
                    )
                    try:
                        chosen_transport.acknowledge(ack)
                    except Exception:
                        pass
                    try:
                        log.acknowledge(ack)
                    except Exception:
                        pass
                raise
            log.result(result)
            ack = self.ack_for(bundle, result)
            chosen_transport.acknowledge(ack)
            log.acknowledge(ack)
            if ack.outcome != "committed":
                raise BundleResultError(
                    f"bundle {bundle.bundle_id!r} was not committed: "
                    f"{ack.outcome} ({result.status}: {result.reason or 'no reason'})")
            log.commit(bundle.bundle_id)
            for row in result.result:
                actor, applied, error = row
                if actor is None:
                    continue
                completed[actor] = (actor, bool(applied), error)

        return {actor: completed[actor] for actor in order if actor in completed}

    def _dispatch_ordered(self, bundles: list[Bundle],
                          transport: Any) -> list[BundleResult]:
        """Dispatch independent shard bundles in a pool, results in plan order."""
        if not bundles:
            return []
        limit = self.workers if self.workers is not None else len(bundles)
        if limit <= 1 or len(bundles) <= 1:
            return [transport.dispatch(bundle) for bundle in bundles]
        with ThreadPoolExecutor(max_workers=min(limit, len(bundles)),
                                thread_name_prefix="bigville-bundle") as pool:
            futures = [pool.submit(transport.dispatch, bundle)
                       for bundle in bundles]
            return [future.result() for future in futures]
