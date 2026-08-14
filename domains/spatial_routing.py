"""spatial_routing — the agent's PASSABILITY-AWARE distance routing, expressed as
GRAPH-RESIDENT Term-trees the Rust DSL evaluates (NOT Python BFS).

WHY THIS EXISTS. The agent's spatial routing used to be Python BFS
(``_bfs_distances_to_goal`` / ``_compute_path_to`` / ``_plan_to_goal``) that
walked EVERY registered instance-instance edge — *including straight through
known walls*, because it ignored the ``passable`` attribute the agent perceives
on its Boundary nodes. That is agent decision-logic in Python (CLAUDE.md: the
agent is a graph in Rust; routing is reasoning, so it must be graph data).

THE MOVE (the task: "provide the AST to jabberwock and have it move it graph
native and fix it"). The imperative BFS's *meaning* is a fixed-point distance
recurrence:

    distance(goal) = 0
    distance(cell) = 1 + min over PASSABLE neighbours n of distance(n)

A Python ``while``/``deque`` loop can't be a single DSL Term (Term-trees are
pure expressions, no iteration), so the natural graph-native form is the
ONE-STEP RELAXATION as a Term-tree, evaluated to a fixed point. This module
authors that Term-tree as graph data and runs the relaxation to fixpoint by
EVALUATING the graph-resident term (the engine doing the work) — no Python
graph-search decision.

THE FIX (passability). ``passable_neighbours(cell)`` traverses only passable
adjacency:

    passable_neighbours(cell) =
        Filter(Neighbours(cell, <any>), "n",
            And( n is a SpatialLocation cell,
                 NOT (n is blocked by an impassable boundary of cell) ))

An impassable boundary ``blocks`` the neighbour it walls off (the mirror of a
passable boundary's ``leads_to``); a cell with no learned boundaries (e.g. the
plain ``adjacent_to`` test maps, an untested side) blocks nothing, so its
adjacency is all passable — identical to the old behaviour. A learned wall
removes exactly that one neighbour from the relaxation, so distance routes
AROUND it (unreachable-through-the-wall = +inf).

GENERAL, not ARC-keyed: any SpatialLocation+Boundary domain (doom / walker /
ARC) routes the same way — the only thing read is ``world_type`` ==
"SpatialLocation", ``bounded_by`` boundaries with a ``passable`` attr, and their
``blocks`` edges.

The Term-tree is stored on ``agent_root`` via ``passable_distance_relax`` so it
is introspectable/editable graph data, exactly like ``exploration_value`` /
``motor_value``. Python here is a thin world-adapter: it initialises the
per-cell ``_dist`` register, fires the relaxation Term, and reads the result.
"""
from __future__ import annotations

from substrate import (
    And,
    Argmax,
    Attr,
    Eq,
    Filter,
    IfThenElse,
    In,
    Lit,
    Lt,
    MapNeighbours,
    Minus,
    MinOver,
    Neighbours,
    Not,
    Plus,
    Term,
    Var,
)

# The "unreachable" sentinel the relaxation propagates: a cell whose only routes
# to the goal cross known walls keeps this value (effectively +inf). Large enough
# that 1 + UNREACHABLE never beats a real finite distance within any sane horizon.
UNREACHABLE: float = 1e9


def passable_neighbours_term(cell: Term) -> Term:
    """Term over ``cell`` → the set of its PASSABLE adjacent cells.

    A neighbour ``n`` counts iff (a) it is a SpatialLocation cell (excludes the
    cell's BodyType / Boundary / Term neighbours reached by other edge types)
    and (b) it is NOT walled off — i.e. no impassable ``bounded_by`` boundary of
    ``cell`` ``blocks`` it. Pure graph query; no edge type is privileged, so it
    works for ``adjacent_to`` / ``adjacent_location`` / any spatial map."""
    # The impassable boundaries of the cell (a bounded_by boundary whose
    # ``passable`` attr is false). ``Not(Attr(b, "passable"))`` is true when the
    # attr is False/absent-and-falsey; we only mark a side blocked when the
    # boundary additionally has a ``blocks`` edge (set only for known walls),
    # so an unlabeled/neutral boundary blocks nothing.
    impassable = Filter(
        Neighbours(cell, "bounded_by"), "b",
        Not(Attr(Var("b"), "passable")),
    )
    blocked = MapNeighbours(impassable, "blocks")
    return Filter(
        Neighbours(cell, None), "n",
        And(items=(
            Eq(Attr(Var("n"), "world_type"), Lit("SpatialLocation")),
            Not(In(member=Var("n"), container=blocked)),
        )),
    )


def distance_relax_term() -> Term:
    """The one-step Bellman relaxation as a Term over ``{cell, goal}``:

        relax(cell) = 0                                  if cell is the goal
                    = 1 + min_{n in passable_neighbours(cell)} n._dist   else
                    = UNREACHABLE                        if no passable neighbour

    Evaluated repeatedly (init all _dist = UNREACHABLE, goal _dist = 0) it
    converges to the passability-aware shortest-path distance to the goal —
    the graph-resident replacement for the Python BFS."""
    cell, goal = Var("cell"), Var("goal")
    nbr_min = MinOver(
        passable_neighbours_term(cell), "n",
        Attr(Var("n"), "_dist"),
        default=Lit(UNREACHABLE),
    )
    return IfThenElse(
        Eq(cell, goal),
        Lit(0),
        Plus(items=(Lit(1), nbr_min)),
    )


def relax_step_term() -> Term:
    """The monotone Bellman step as a Term over ``{cell}``, for the native
    ``relax_to_fixpoint`` driver (Rust does the iteration; this Term IS the
    routing decision):

        step(cell) = min( cell._dist , 1 + min_{n in passable_neighbours} n._dist )

    Goal-FREE — no ``goal`` var, so ONE Term routes to any goal: the adapter
    pins the goal by initialising its ``_dist`` to 0, and ``min`` keeps it there
    (1 + anything never beats 0). Every other cell's ``_dist`` only ever
    decreases, so sweeping to a fixed point yields the passability-aware
    shortest-path distance — the graph-resident replacement for the Python BFS
    loop, with the loop itself moved into the Rust ``relax_to_fixpoint``
    primitive."""
    cell = Var("cell")
    relax = Plus(items=(
        Lit(1),
        MinOver(passable_neighbours_term(cell), "n",
                Attr(Var("n"), "_dist"), default=Lit(UNREACHABLE)),
    ))
    cur = Attr(cell, "_dist")
    return IfThenElse(Lt(a=relax, b=cur), relax, cur)


def passable_hop_term() -> Term:
    """The first hop from ``cell`` toward the goal: the PASSABLE neighbour with
    the smallest ``_dist`` (descend the relaxed gradient). Walled-off neighbours
    are excluded by ``passable_neighbours``, so the agent never steps into a
    known wall. An ``Argmax`` over ``-_dist`` — the hop DECISION as graph data,
    evaluated in Rust. Run AFTER ``relax_to_fixpoint`` has filled ``_dist``."""
    cell = Var("cell")
    return Argmax(
        source=passable_neighbours_term(cell), var_name="n",
        value=Minus(a=Lit(0), b=Attr(Var("n"), "_dist")),
    )


def passable_distances(mind_graph, cells, goal_wi, horizon: int,
                       relax_term: Term) -> dict:
    """Run the graph-resident relaxation Term to a fixed point and return
    ``{cell_wi: distance_to_goal}`` over PASSABLE adjacency only. Cells whose
    every route to the goal crosses a known wall stay UNREACHABLE and are
    dropped from the returned map (matching the old BFS's "not present ⇒
    unreachable" contract that the scorer relies on).

    Mechanical: initialise each cell's ``_dist`` register, then fire the
    Term-tree over every cell until no register changes (or ``horizon``+1
    sweeps — the longest finite shortest path is bounded by the cell count).
    The DECISION (what a distance is, which neighbour is passable) lives wholly
    in ``relax_term``; this loop only evaluates it."""
    cells = list(cells)
    if goal_wi not in cells:
        cells.append(goal_wi)
    # Snapshot any pre-existing _dist so routing is non-destructive.
    saved = {c: mind_graph.node(c).attrs.get("_dist") for c in cells}
    for c in cells:
        mind_graph.node(c).attrs["_dist"] = 0.0 if c == goal_wi else UNREACHABLE
    # Fixed-point sweeps. Bounded by the number of cells (no shortest path is
    # longer) and by ``horizon`` so a huge map can't stall a tick.
    max_sweeps = min(len(cells), horizon + 1) if horizon > 0 else len(cells)
    for _ in range(max(1, max_sweeps)):
        changed = False
        for c in cells:
            v = float(relax_term.evaluate({"cell": c, "goal": goal_wi},
                                          mind_graph))
            if v != mind_graph.node(c).attrs.get("_dist"):
                mind_graph.node(c).attrs["_dist"] = v
                changed = True
        if not changed:
            break
    dists = {c: mind_graph.node(c).attrs["_dist"] for c in cells
             if mind_graph.node(c).attrs["_dist"] < UNREACHABLE}
    # Restore the register (it is scratch, not durable map state).
    for c, old in saved.items():
        if old is None:
            mind_graph.node(c).attrs.pop("_dist", None)
        else:
            mind_graph.node(c).attrs["_dist"] = old
    return dists


__all__ = [
    "UNREACHABLE",
    "passable_neighbours_term",
    "distance_relax_term",
    "relax_step_term",
    "passable_hop_term",
    "passable_distances",
]
