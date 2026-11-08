"""A pure, dependency-free tick graph for one Bigville turn (TG04).

The engine still applies responses in ``turn_order``.  This module separately
states what each response reads and writes, so a later phase can schedule the
same operations without changing the result.  Nothing here imports ``bigville``
or ``worlds.bigville_world``: ``build_tick_graph`` only duck-types the small
slice of the world it needs (``_actors``, ``actor_position``,
``_physical_objects`` and the parameter names a backend already supplies).

Resource conventions
--------------------
``Resource(kind, key)`` is a frozen, hashable pair.  The kinds used by this
module and their keys are::

    Resource("actor", name)
    Resource("cell", (x, y))
    Resource("item", name)
    Resource("stock", kind)
    Resource("container", name)
    Resource("building", name)
    Resource("job", name)
    Resource("animal", name)
    Resource("relationship", tuple(sorted((a, b))))
    Resource("utterance", turn)
    Resource("memory", actor)
    Resource("world", ...)

The verb table below is deliberately conservative.  A verb not in the table
writes ``Resource("world", "global")``, which serialises it behind every other
unknown verb.  Over-declaring a conflict only costs parallelism; under-declaring
one would make a future concurrent executor observable.

TG06 claim resolution
---------------------
``Claim`` and ``resolve_claims`` are the pure, world-free half of opt-in
simultaneous semantics.  A claim names one actor's exclusive write to a
resource (in this phase only ``Resource("item", ...)``).  ``resolve_claims``
picks one deterministic winner per contested resource and reports every other
claimant as a loser.  It never reads or mutates a world; the game supplies the
priority values and decides what suppression means for enactment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping


# --------------------------------------------------------------------------- resources


def _render_key(value: Any) -> str:
    """Stable text for a resource key (no object reprs in the common case)."""
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return "(" + ", ".join(_render_key(item) for item in value) + ")"
    if isinstance(value, list):
        return "(" + ", ".join(_render_key(item) for item in value) + ")"
    if value is None:
        return "null"
    return repr(value)


def _hashable_key(value: Any) -> Any:
    """Make a caller-supplied key hashable without changing ordinary keys."""
    if isinstance(value, list):
        return tuple(_hashable_key(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _hashable_key(item)) for key, item in value.items()))
    if isinstance(value, set):
        return tuple(sorted((_hashable_key(item) for item in value), key=repr))
    return value


def _plain(value: Any) -> Any:
    """A JSON-friendly view for diagnostics and checkpoint dictionaries."""
    if isinstance(value, Resource):
        return value.to_dict()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(item) for item in value), key=repr)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _plain(to_dict())
    return str(value)


@dataclass(frozen=True)
class Resource:
    """One resource a turn operation may read or write."""

    kind: str
    key: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _hashable_key(self.key))

    def __str__(self) -> str:
        return f"{self.kind}:{_render_key(self.key)}"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": str(self.kind), "key": _plain(self.key)}


@dataclass(frozen=True)
class Operation:
    """One claimed effect of a turn, with its read and write sets.

    ``tiebreak`` is ordered the same way as ``BigvilleGame.turn_order``: the
    first element is the actor's position in that order.  Operations that share
    an order index (an actor's major action, speech and memory) are additionally
    ordered by actor id and op id.
    """

    op_id: str
    actor: str | None
    kind: str
    reads: tuple[Resource, ...]
    writes: tuple[Resource, ...]
    tiebreak: tuple
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reads", tuple(self.reads))
        object.__setattr__(self, "writes", tuple(self.writes))
        object.__setattr__(self, "tiebreak", tuple(self.tiebreak))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "actor": self.actor,
            "kind": self.kind,
            "reads": [resource.to_dict() for resource in self.reads],
            "writes": [resource.to_dict() for resource in self.writes],
            "tiebreak": _plain(self.tiebreak),
            "payload": _plain(self.payload),
        }


# --------------------------------------------------------------------------- claims


@dataclass(frozen=True)
class Claim:
    """One actor's exclusive claim on a resource in a simultaneous turn.

    ``priority`` is any sortable value supplied by the caller.  Higher values
    win.  ``index`` is the actor's position in ``turn_order`` and breaks a
    priority tie in favour of the earlier position; the actor id is the final
    tie-break.  The class is deliberately inert: it holds no world reference
    and cannot mutate one.
    """

    resource: Resource
    actor: str
    index: int
    priority: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", int(self.index))

    def sort_key(self) -> tuple:
        """The documented total order: priority, earlier index, actor id."""
        return (self.priority, -self.index, str(self.actor))

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource.to_dict(),
            "actor": str(self.actor),
            "index": int(self.index),
            "priority": _plain(self.priority),
        }


def resolve_claims(claims: Iterable[Claim]) -> tuple[dict[Resource, Claim],
                                                     dict[Resource, tuple[Claim, ...]]]:
    """Resolve exclusive claims deterministically, without touching a world.

    Returns ``(winners, losers)``:

    - ``winners`` maps every claimed resource to its winning ``Claim``;
    - ``losers`` maps only contested resources to a priority-ordered tuple of
      the other claimants (empty absent for an uncontested resource).

    The winner is the maximum by ``(priority, -index, actor)``.  Because the
    actor id is unique within a turn, even fully tied priorities are resolved
    without depending on input order.  Resource iteration is sorted by the
    stable textual form for the same reason.
    """
    grouped: dict[Resource, list[Claim]] = {}
    for claim in claims:
        grouped.setdefault(claim.resource, []).append(claim)

    winners: dict[Resource, Claim] = {}
    losers: dict[Resource, tuple[Claim, ...]] = {}
    for resource in sorted(grouped, key=str):
        group = grouped[resource]
        winner = max(group, key=Claim.sort_key)
        winners[resource] = winner
        defeated = tuple(sorted((claim for claim in group if claim is not winner),
                                key=Claim.sort_key, reverse=True))
        if defeated:
            losers[resource] = defeated
    return winners, losers


# --------------------------------------------------------------------------- graph


# Speech and memory are real operations but not actor-order entries: a later
# executor applies them alongside their actor.  ``topological_order`` therefore
# lists the actor-facing enactments by default, which is exactly ``turn_order``.
AUXILIARY_KINDS = frozenset({"speak", "memory"})


class TickGraphCycle(RuntimeError):
    """Raised when a tick graph's conflict edges contain a cycle."""


def _conflict(left: Operation, right: Operation) -> bool:
    """Whether two operations share a write-write or write-read resource."""
    left_reads, left_writes = set(left.reads), set(left.writes)
    right_reads, right_writes = set(right.reads), set(right.writes)
    return bool((left_writes & right_writes)
                or (left_writes & right_reads)
                or (left_reads & right_writes))


class TickGraph:
    """Operations plus the deterministic conflict edges between them."""

    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}
        self._edges: set[tuple[str, str]] = set()
        self._conflicts: dict[str, set[str]] = {}

    # ---- construction

    def add_operation(self, operation: Operation) -> Operation:
        """Add one operation, computing its conflict edges with every earlier one."""
        if operation.op_id in self._operations:
            raise ValueError(f"duplicate operation id: {operation.op_id}")
        self._operations[operation.op_id] = operation
        try:
            for existing in list(self._operations.values()):
                if existing is operation:
                    continue
                if not _conflict(operation, existing):
                    continue
                self._conflicts.setdefault(operation.op_id, set()).add(existing.op_id)
                self._conflicts.setdefault(existing.op_id, set()).add(operation.op_id)
                if operation.tiebreak < existing.tiebreak:
                    self.add_edge(operation.op_id, existing.op_id)
                elif existing.tiebreak < operation.tiebreak:
                    self.add_edge(existing.op_id, operation.op_id)
                else:
                    # Equal tiebreaks cannot happen for operations this module
                    # builds (op_id is part of the tiebreak), but keep the graph
                    # acyclic if a caller supplies one: op id is the last resort.
                    if operation.op_id < existing.op_id:
                        self.add_edge(operation.op_id, existing.op_id)
                    else:
                        self.add_edge(existing.op_id, operation.op_id)
        except Exception:
            self._operations.pop(operation.op_id, None)
            self._edges = {edge for edge in self._edges
                           if operation.op_id not in edge}
            self._conflicts.pop(operation.op_id, None)
            for others in self._conflicts.values():
                others.discard(operation.op_id)
            raise
        return operation

    add = add_operation

    def add_edge(self, before: str, after: str) -> None:
        """Add a precedence edge.  Public so tests and TG05 can force a cycle."""
        if before not in self._operations or after not in self._operations:
            raise KeyError("both operations must be in the graph before an edge")
        if before == after:
            raise ValueError("a tick-graph edge cannot be a self-loop")
        self._edges.add((before, after))

    # ---- inspection

    @property
    def operations(self) -> tuple[Operation, ...]:
        return tuple(sorted(self._operations.values(), key=lambda op: op.tiebreak))

    def operation(self, op_id: str) -> Operation:
        return self._operations[op_id]

    @property
    def edges(self) -> tuple[tuple[str, str], ...]:
        order = {op.op_id: op.tiebreak for op in self._operations.values()}
        return tuple(sorted(self._edges, key=lambda edge: (order[edge[0]], order[edge[1]])))

    def conflicts(self, op_id: str) -> tuple[str, ...]:
        if op_id not in self._operations:
            raise KeyError(op_id)
        order = {op.op_id: op.tiebreak for op in self._operations.values()}
        return tuple(sorted(self._conflicts.get(op_id, ()), key=order.__getitem__))

    def predecessors(self, op_id: str) -> tuple[str, ...]:
        if op_id not in self._operations:
            raise KeyError(op_id)
        order = {op.op_id: op.tiebreak for op in self._operations.values()}
        names = (before for before, after in self._edges if after == op_id)
        return tuple(sorted(names, key=order.__getitem__))

    def successors(self, op_id: str) -> tuple[str, ...]:
        if op_id not in self._operations:
            raise KeyError(op_id)
        order = {op.op_id: op.tiebreak for op in self._operations.values()}
        names = (after for before, after in self._edges if before == op_id)
        return tuple(sorted(names, key=order.__getitem__))

    # ---- ordering

    def topological_order(self, *, include_auxiliary: bool = False) -> tuple[str, ...]:
        """Linearise the graph, smallest tiebreak first among ready operations.

        With the default ``include_auxiliary=False`` the result is the
        actor-facing enactment order (major, contest, joint and idle operations),
        which equals the supplied ``order``.  ``include_auxiliary=True`` adds the
        speech and memory operations for an executor such as TG05's.
        """
        operations = [op for op in self.operations
                      if include_auxiliary or op.kind not in AUXILIARY_KINDS]
        ids = {op.op_id for op in operations}
        index = {op.op_id: op.tiebreak for op in operations}
        successors: dict[str, list[str]] = {op.op_id: [] for op in operations}
        indegree = {op.op_id: 0 for op in operations}
        for before, after in self._edges:
            if before in ids and after in ids:
                successors[before].append(after)
                indegree[after] += 1

        ready = [op_id for op_id, degree in indegree.items() if degree == 0]
        ready.sort(key=index.__getitem__)
        ordered: list[str] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for after in successors[current]:
                indegree[after] -= 1
                if indegree[after] == 0:
                    ready.append(after)
            ready.sort(key=index.__getitem__)
        if len(ordered) != len(operations):
            remaining = tuple(sorted((op_id for op_id, degree in indegree.items()
                                      if degree > 0), key=index.__getitem__))
            raise TickGraphCycle(f"tick graph has a conflict cycle among {remaining!r}")
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operations": [op.to_dict() for op in self.operations],
            "edges": [list(edge) for edge in self.edges],
            "order": list(self.topological_order()),
            "linearisation": list(self.topological_order(include_auxiliary=True)),
        }


# --------------------------------------------------------------------------- action table


# Each entry is ``(reads, writes)`` as whitespace-separated resource roles.
# The roles are expanded by ``_BuildContext.resource`` below.  This is the
# readable contract for what each verb touches; keep new verbs here rather than
# guessing in the builder, and leave an unknown verb to the world/global write.
_VERB_RESOURCES: dict[str, tuple[str, str]] = {
    # movement: the actor and both cells; two moves into one cell conflict
    # EN04 follow-up: a walk moves one *step* toward its destination and wears
    # that step cell.  Two walkers whose step cells coincide must conflict even
    # when their final destinations differ.
    "move": ("actor cell dest_cell step_cell",
             "actor cell dest_cell step_cell"),
    # rest/sleep touch only the actor
    "rest": ("actor", "actor"),
    "sleep": ("actor", "actor"),
    # consumption and handling
    "eat": ("actor stock item container", "actor stock"),
    "give": ("actor target stock", "actor target stock"),
    "transfer": ("actor target stock", "actor target stock"),
    "pick_up": ("actor item", "actor item"),
    "drop": ("actor item", "actor item cell"),
    "put": ("actor stock container", "actor stock container"),
    "fetch": ("actor stock container", "actor stock container"),
    "sell": ("actor target stock", "actor target stock"),
    # work and production
    "work": ("actor job stock", "actor job stock"),
    "make": ("actor job stock", "actor job stock"),
    "start": ("actor job stock", "actor job stock"),
    "build": ("actor building stock", "actor building stock"),
    "maintain": ("actor building", "actor building"),
    "care": ("actor target", "actor target"),
    "tend_animals": ("actor animal stock", "actor animal stock"),
    # land
    "harvest": ("actor item stock", "actor item stock"),
    "water": ("actor item", "actor item"),
    "sow": ("actor item land stock", "actor item land stock"),
    "fertilise": ("actor land stock", "actor land stock"),
    # light, locks and handling large objects
    "light": ("actor item", "actor item world_light"),
    "douse": ("actor item", "actor item world_light"),
    "lock": ("actor container", "actor container"),
    "unlock": ("actor container", "actor container"),
    "move_object": ("actor object source_cell dest_cell",
                    "actor object source_cell dest_cell"),
    # bodily control
    "release": ("actor target relationship", "actor target relationship"),
    "struggle": ("actor target relationship", "actor target relationship"),
    # a generic physical attempt: the thing in reach, never a global write
    "attempt": ("actor item target_cell", "actor item target_cell"),
}

_CONTEST_VERBS = frozenset({"take", "strike", "restrain", "throw"})


def _cell(value: Any) -> tuple[int, int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


class _BuildContext:
    """The read-only view ``build_tick_graph`` has of one actor's proposal."""

    def __init__(self, world: Any, actor: str, response: Any, action: str,
                 params: Mapping[str, Any], order_index: int, turn: int) -> None:
        self.world = world
        self.actor = actor
        self.response = response
        self.action = action
        self.params = params
        self.order_index = order_index
        self.turn = turn
        self._cache: dict[str, Any] = {}

    # ---- name resolution

    def param(self, *names: str) -> Any:
        for name in names:
            value = self.params.get(name)
            if value is not None:
                return value
        return None

    def alias(self, value: Any) -> Any:
        """Resolve an affordance key (``target:0``) through the actor's target map."""
        if not isinstance(value, str):
            return value
        actors = getattr(self.world, "_actors", {})
        if value and value in actors:
            return value
        targets = getattr(self.world, "_actor_targets", {})
        if isinstance(targets, Mapping):
            resolved = targets.get(self.actor, {})
            if isinstance(resolved, Mapping) and value in resolved:
                return resolved[value]
        return value

    def actor_cell(self, name: Any) -> tuple[int, int] | None:
        actors = getattr(self.world, "_actors", {})
        if isinstance(name, str) and name in actors:
            try:
                return _cell(self.world.actor_position(name))
            except Exception:
                return None
        return None

    def object_cell(self, name: Any) -> tuple[int, int] | None:
        if not isinstance(name, str) or name not in getattr(self.world, "_physical_objects", {}):
            return None
        location = getattr(self.world, "_physical_location_cell", None)
        if callable(location):
            try:
                return _cell(location(name))
            except Exception:
                return None
        attrs = getattr(getattr(self.world, "eng", None), "node", None)
        if callable(attrs):
            try:
                return _cell(attrs(self.world._physical_objects[name])["attrs"].get("cell"))
            except Exception:
                return None
        return None

    # ---- roles

    def target_name(self) -> Any:
        if "target_name" not in self._cache:
            if self.action in ("release", "struggle"):
                reader = getattr(self.world, "holding_of" if self.action == "release" else "holder_of", None)
                value = reader(self.actor) if callable(reader) else None
                if value is None:
                    value = self.param("target", "source")
            else:
                value = self.param("recipient", "patient", "target", "source")
            self._cache["target_name"] = self.alias(value)
        return self._cache["target_name"]

    def item_name(self) -> Any:
        if "item_name" not in self._cache:
            self._cache["item_name"] = self.alias(
                self.param("item", "object_id", "object", "target"))
        return self._cache["item_name"]

    def object_name(self) -> Any:
        if "object_name" not in self._cache:
            self._cache["object_name"] = self.alias(
                self.param("object_id", "object", "item", "target"))
        return self._cache["object_name"]

    def stock_kind(self) -> Any:
        return self.param("kind")

    def container_name(self) -> Any:
        return self.alias(self.param("container", "source", "target"))

    def building_name(self) -> Any:
        return self.alias(self.param("project", "name", "target"))

    def job_name(self) -> Any:
        return self.alias(self.param("recipe", "action_name", "target"))

    def animal_name(self) -> Any:
        return self.alias(self.param("animal", "target"))

    def land_name(self) -> Any:
        value = self.param("land", "target")
        if self.action == "sow" and isinstance(value, (list, tuple)) and len(value) == 2:
            value = value[1]
        return self.alias(value)

    def destination(self) -> tuple[int, int] | None:
        return _cell(self.alias(self.param("destination", "target")))

    # ---- resource expansion

    def resource(self, role: str) -> Resource | None:
        if role == "actor":
            return Resource("actor", self.actor)
        if role == "cell":
            return self._cell_resource(self.actor_cell(self.actor))
        if role == "dest_cell":
            return self._cell_resource(self.destination())
        if role == "step_cell":
            current = self.actor_cell(self.actor)
            destination = self.destination()
            if current is None or destination is None:
                return None
            stepper = getattr(self.world, "_movement_step", None)
            if not callable(stepper):
                return None
            try:
                return self._cell_resource(stepper(current, destination))
            except Exception:
                return None
        if role == "source_cell":
            return self._cell_resource(self.object_cell(self.object_name()))
        if role == "target_cell":
            return self._cell_resource(self.actor_cell(self.target_name()))
        if role == "target":
            target = self.target_name()
            return Resource("actor", target if target is not None else "")
        if role == "relationship":
            target = self.target_name()
            return Resource("relationship",
                            tuple(sorted((str(self.actor), str(target if target is not None else "")))))
        if role == "item":
            item = self.item_name()
            return Resource("item", item if item is not None else "")
        if role == "object":
            obj = self.object_name()
            return Resource("item", obj if obj is not None else "")
        if role == "stock":
            return Resource("stock", self.stock_kind() if self.stock_kind() is not None else "")
        if role == "container":
            name = self.container_name()
            return Resource("container", name if name is not None else "")
        if role == "building":
            name = self.building_name()
            return Resource("building", name if name is not None else "")
        if role == "job":
            name = self.job_name()
            return Resource("job", name if name is not None else "")
        if role == "animal":
            name = self.animal_name()
            return Resource("animal", name if name is not None else "")
        if role == "land":
            name = self.land_name()
            return Resource("item", name if name is not None else "")
        if role == "world_global":
            return Resource("world", "global")
        if role == "world_contest":
            return Resource("world", "contest")
        if role == "world_events":
            return Resource("world", "events")
        if role == "world_light":
            return Resource("world", "light")
        if role == "utterance":
            return Resource("utterance", self.turn)
        if role == "memory":
            return Resource("memory", self.actor)
        raise KeyError(f"unknown tick-graph resource role: {role}")

    @staticmethod
    def _cell_resource(cell: tuple[int, int] | None) -> Resource | None:
        return None if cell is None else Resource("cell", cell)


def _expand(context: _BuildContext, roles: str) -> tuple[Resource, ...]:
    resources: list[Resource] = []
    seen: set[Resource] = set()
    for role in roles.split():
        resource = context.resource(role)
        if resource is not None and resource not in seen:
            seen.add(resource)
            resources.append(resource)
    return tuple(resources)


# --------------------------------------------------------------------------- builder


def _proposal(response: Any) -> Any:
    return getattr(response, "major_action", None)


def _is_joint(response: Any) -> bool:
    proposal = _proposal(response)
    return (proposal is not None and getattr(proposal, "action", None) == "joint"
            and isinstance(getattr(proposal, "params", {}).get("joint"), dict))


def _joint_key(response: Any) -> tuple[str, str, str]:
    task = dict(_proposal(response).params["joint"])
    return (str(task.get("task")), str(task.get("object", task.get("worker", ""))),
            repr(task.get("toward")))


def _contest_target(response: Any, params: Mapping[str, Any]) -> Any:
    action = getattr(_proposal(response), "action", "")
    if action == "take":
        value = params.get("source")
        return params.get("target") if value is None else value
    return params.get("target")


def _contest_operation(world: Any, actor: str, response: Any, order_index: int,
                       turn: int) -> Operation:
    """A contest owns the actor, the target and their shared relationship/state.

    The target is included even when the proposal is malformed: refusal is not
    known until enactment, so the conservative graph must still serialise any
    other action on that resident.
    """
    proposal = _proposal(response)
    params = dict(getattr(proposal, "params", {}) or {})
    context = _BuildContext(world, actor, response, str(getattr(proposal, "action", "")),
                            params, order_index, turn)
    target = context.alias(_contest_target(response, params))
    target_name = target if target is not None else ""
    target_cell = context.actor_cell(target) if isinstance(target, str) else None

    reads = [Resource("actor", actor),
             Resource("actor", target_name),
             Resource("relationship", tuple(sorted((str(actor), str(target_name)))))]
    writes = list(reads)
    actor_cell = context.actor_cell(actor)
    if actor_cell is not None:
        reads.append(Resource("cell", actor_cell))
    if target_cell is not None:
        reads.append(Resource("cell", target_cell))
        writes.append(Resource("cell", target_cell))
    writes.extend((Resource("world", "contest"), Resource("world", "events")))
    return Operation(
        op_id=str(actor),
        actor=str(actor),
        kind=str(getattr(proposal, "action", "")),
        reads=tuple(_unique(reads)),
        writes=tuple(_unique(writes)),
        tiebreak=(order_index, str(actor), str(actor)),
        payload={"params": params, "target": target_name},
    )


def _joint_operation(world: Any, key: tuple[str, str, str],
                     members: list[str], responses: Mapping[str, Any],
                     first_index: int, turn: int) -> Operation:
    """One compound operation for every member of a joint act."""
    proposal = _proposal(responses[members[0]])
    task = dict(proposal.params["joint"])
    kind = str(task.get("task"))
    actors = tuple(sorted(members))
    reads: list[Resource] = []
    writes: list[Resource] = []
    for member in actors:
        reads.append(Resource("actor", member))
        writes.append(Resource("actor", member))
        cell = _BuildContext(world, member, responses[member], "joint", task,
                             first_index, turn).actor_cell(member)
        if cell is not None:
            reads.append(Resource("cell", cell))
            writes.append(Resource("cell", cell))

    if kind == "carry":
        obj = task.get("object")
        if obj is not None:
            reads.append(Resource("item", obj))
            writes.append(Resource("item", obj))
        ctx = _BuildContext(world, actors[0], responses[actors[0]], "joint", task,
                            first_index, turn)
        source = ctx.object_cell(obj)
        toward = task.get("toward")
        destination = None
        if source is not None and isinstance(toward, (list, tuple)) and len(toward) == 2:
            try:
                destination = (source[0] + int(toward[0]), source[1] + int(toward[1]))
            except (TypeError, ValueError):
                destination = None
        if source is not None:
            reads.append(Resource("cell", source))
            writes.append(Resource("cell", source))
        if destination is not None:
            reads.append(Resource("cell", destination))
            writes.append(Resource("cell", destination))
        writes.extend((Resource("world", "events"),))
    elif kind == "crew":
        worker = task.get("worker")
        worker_key = str(worker) if worker is not None else ""
        if worker is not None:
            reads.append(Resource("actor", worker_key))
            writes.append(Resource("actor", worker_key))
        reads.append(Resource("job", worker_key))
        writes.append(Resource("job", worker_key))
        writes.append(Resource("world", "events"))
    else:
        # An unsupported joint task still owns its members and the global state
        # it may touch while failing.
        reads.append(Resource("world", "global"))
        writes.extend((Resource("world", "global"), Resource("world", "events")))

    op_id = "joint:" + "|".join((str(kind), str(key[1]), str(key[2])))
    return Operation(
        op_id=op_id,
        actor=actors[0],
        kind="joint",
        reads=tuple(_unique(reads)),
        writes=tuple(_unique(writes)),
        tiebreak=(first_index, actors[0], op_id),
        payload={"task": task, "members": list(actors),
                 "actors": list(actors), "participants": list(actors)},
    )


def _unique(resources: Iterable[Resource]) -> list[Resource]:
    seen: set[Resource] = set()
    result: list[Resource] = []
    for resource in resources:
        if resource not in seen:
            seen.add(resource)
            result.append(resource)
    return result


def _idle_operation(actor: str, order_index: int) -> Operation:
    """Every order entry has an actor-facing operation, even with no proposal."""
    return Operation(
        op_id=str(actor),
        actor=str(actor),
        kind="idle",
        reads=(Resource("actor", str(actor)),),
        writes=(),
        tiebreak=(order_index, str(actor), str(actor)),
        payload={"reason": "no major action"},
    )


def _regular_operation(world: Any, actor: str, response: Any, order_index: int,
                       turn: int) -> Operation:
    proposal = _proposal(response)
    action = str(getattr(proposal, "action", ""))
    params = dict(getattr(proposal, "params", {}) or {})
    if action in _CONTEST_VERBS:
        return _contest_operation(world, actor, response, order_index, turn)
    context = _BuildContext(world, actor, response, action, params, order_index, turn)
    spec = _VERB_RESOURCES.get(action)
    if spec is None:
        reads = _expand(context, "actor")
        writes = _expand(context, "actor world_global")
    else:
        reads = _expand(context, spec[0])
        writes = _expand(context, spec[1])
    # A routed walk may carry only `toward` and acquire its destination during
    # enactment.  If this graph cannot name the endpoint, serialise it globally
    # rather than under-declaring the cell write.
    if action in ("move", "move_object") and context.destination() is None:
        writes = tuple(_unique((*writes, Resource("world", "global"))))
    return Operation(
        op_id=str(actor),
        actor=str(actor),
        kind=action or "idle",
        reads=reads,
        writes=writes,
        tiebreak=(order_index, str(actor), str(actor)),
        payload={"action": action, "params": params},
    )


def _speech_operation(actor: str, response: Any, order_index: int, turn: int) -> Operation | None:
    utterances = list(getattr(response, "utterances", ()) or ())
    if not utterances:
        return None
    return Operation(
        op_id=f"{actor}#speak",
        actor=str(actor),
        kind="speak",
        reads=(Resource("actor", str(actor)), Resource("utterance", turn)),
        writes=(Resource("utterance", turn),),
        tiebreak=(order_index, str(actor), f"{actor}#speak"),
        payload={"utterances": utterances},
    )


def _memory_operation(actor: str, response: Any, order_index: int) -> Operation | None:
    updates = list(getattr(response, "memory_updates", ()) or ())
    if not updates:
        return None
    return Operation(
        op_id=f"{actor}#memory",
        actor=str(actor),
        kind="memory",
        reads=(Resource("actor", str(actor)), Resource("memory", str(actor))),
        writes=(Resource("memory", str(actor)),),
        tiebreak=(order_index, str(actor), f"{actor}#memory"),
        payload={"memory_updates": updates},
    )


def build_tick_graph(order: Iterable[str], responses: Mapping[str, Any],
                     world: Any) -> TickGraph:
    """Build the turn's graph without applying, mutating or ordering any effect.

    ``order`` is ``BigvilleGame.last_order``.  ``responses`` is duck-typed:
    each value needs ``major_action`` (with ``action``/``params``),
    ``utterances`` and ``memory_updates``.  Actors absent from ``order`` are
    ignored, matching enactment.
    """
    order = list(order)
    turn = int(getattr(world, "_turn", 0) or 0)
    graph = TickGraph()

    groups: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for index, actor in enumerate(order):
        response = responses.get(actor)
        if response is None:
            continue
        if _is_joint(response):
            groups.setdefault(_joint_key(response), []).append((index, str(actor)))

    joint_members = {actor for members in groups.values() for _, actor in members}

    for index, actor in enumerate(order):
        response = responses.get(actor)
        if response is None:
            continue
        if actor not in joint_members:
            proposal = _proposal(response)
            if proposal is None:
                graph.add_operation(_idle_operation(str(actor), index))
            else:
                graph.add_operation(_regular_operation(world, str(actor), response, index, turn))
        speech = _speech_operation(str(actor), response, index, turn)
        if speech is not None:
            graph.add_operation(speech)
        memory = _memory_operation(str(actor), response, index)
        if memory is not None:
            graph.add_operation(memory)

    # Joint acts are resolved as groups before the turn's own responses.  The
    # graph gives each group the earliest member's order index; members still
    # own every read/write the group performs.
    for key in sorted(groups):
        members = sorted(actor for _, actor in groups[key])
        first_index = min(index for index, _ in groups[key])
        graph.add_operation(_joint_operation(world, key, members, responses,
                                             first_index, turn))
    return graph


def describe_conflicts(graph: TickGraph) -> list[str]:
    """A short diagnostic: one line per conflicting operation pair."""
    lines = []
    for op_id in graph.topological_order(include_auxiliary=True):
        conflicts = graph.conflicts(op_id)
        if conflicts:
            lines.append(f"{op_id} conflicts with {', '.join(conflicts)}")
    return lines
