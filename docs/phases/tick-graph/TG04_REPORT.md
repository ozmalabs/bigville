# TG04 — Effect intents and the tick graph

Base commit: `939180f` (TG03: frozen decision snapshot and pooled context
construction)

## Scope

TG04 makes the turn's claimed effects explicit. A new pure module,
`worlds/tick_graph.py`, declares each response as an `Operation` with a read
set, a write set and a deterministic tie-break. `BigvilleGame` builds and
stores the graph for every advanced turn immediately before joint resolution
and response enactment. The executor is unchanged: responses are still applied
serially in `last_order`.

Files changed:

- `worlds/tick_graph.py` (new)
- `bigville/game.py` (build and store the graph; no executor change)
- `tests/test_tick_graph.py` (new)
- `docs/phases/tick-graph/TG04_REPORT.md` (this report)

No file was staged or committed. The untracked `.opencode/` directory was
pre-existing and was not touched.

## Model

`worlds/tick_graph.py` imports only the standard library. It does not import
`bigville` or `worlds.bigville_world`; `build_tick_graph` duck-types the few
world members it needs (`_actors`, `actor_position`, `_physical_objects`,
`_actor_targets`, optional `_physical_location_cell`, optional `_job_of`,
`holding_of`/`holder_of`, `_turn`).

### `Resource`

A frozen, hashable `Resource(kind, key)` with a stable text form:

- `Resource("actor", "Ada")` → `actor:Ada`
- `Resource("cell", (1, 2))` → `cell:(1, 2)`

Keys are normalised to hashable values (lists become tuples, dicts become
sorted key/value tuples). `to_dict()` produces JSON-friendly diagnostics.

### `Operation`

A frozen operation with `op_id`, `actor`, `kind`, `reads`, `writes`, `tiebreak`
and a read-only `payload`. The tie-break is `(order_index, actor or "", op_id)`,
so it can reproduce `turn_order`. `to_dict()` serialises the operation for
later phases and checkpoints.

### `TickGraph`

- `add_operation` computes a conflict edge for every pair that shares a
  write-write, write-read or read-write resource. The edge runs from the
  smaller tie-break to the larger one.
- `conflicts(op_id)`, `predecessors(op_id)`, `successors(op_id)` and `edges`
  expose the result.
- `topological_order()` uses a ready set ordered by tie-break and raises
  `TickGraphCycle` when the graph cannot be linearised.
- `to_dict()` includes operations, edges, the actor-facing order and the full
  linearisation (including speech/memory).
- `describe_conflicts(graph)` is a small human-readable diagnostic.

`topological_order()` defaults to **actor-facing** operations: every order
entry has exactly one major/contest/joint/idle operation, so the result equals
`last_order`. Speech and memory operations are real graph nodes, but are only
included with `include_auxiliary=True`; otherwise an actor's speech would
appear as an extra entry in the turn order. A joint group is one compound
operation, so it appears once at its earliest member's order index.

### Verb table

The table `_VERB_RESOURCES` is an explicit `verb -> (reads, writes)` mapping
expressed as resource roles. It is the readable contract for the graph and is
expanded from the proposal's params and the current world:

| Verb(s) | Reads | Writes |
|---|---|---|
| `move` | actor, source cell, destination cell | actor, source cell, destination cell |
| `rest`, `sleep` | actor | actor |
| `eat` | actor, stock kind, item, container | actor, stock kind |
| `give`, `transfer` | actor, target, stock kind | actor, target, stock kind |
| `pick_up`, `drop` | actor, item | actor, item (+ cell for `drop`) |
| `put`, `fetch` | actor, stock kind, container | actor, stock kind, container |
| `work`, `make`, `start` | actor, job/recipe, stock | actor, job/recipe, stock |
| `build` | actor, building/project, stock | same |
| `maintain` | actor, building | actor, building |
| `care` | actor, target | actor, target |
| `tend_animals` | actor, animal, stock | actor, animal, stock |
| `harvest`, `water` | actor, crop/item, stock | actor, crop/item, stock |
| `sow` | actor, crop item, land, stock | same |
| `fertilise` | actor, land, stock | same |
| `light`, `douse` | actor, item | actor, item, world/light |
| `lock`, `unlock` | actor, container | actor, container |
| `move_object` | actor, object, source cell, destination cell | same |
| `release`, `struggle` | actor, target, relationship | same |
| `attempt` | actor, item, target cell | actor, item, target cell |
| anything else | actor | actor, **`world/global`** |

Rationale for the minimum conflicts the tests rely on:

- `move` writes the actor and both endpoint cells, so two moves into the same
  cell conflict even when the actors are otherwise independent.
- `rest` and `sleep` write only the actor, so two unrelated rests do not
  conflict.
- Transfers write `Resource("stock", kind)` as well as both inventories'
  actor/target resources, so two transfers of the same stock conflict even
  between different pairs of residents.
- Unknown verbs write `Resource("world", "global")`, so two unknown verbs (or
  any future global writer) are conservatively serialised.

The table deliberately over-declares rather than under-declares: a false
conflict costs parallelism, a missed conflict would make a future concurrent
executor observable. Names that cannot be resolved are still included as
`""`/raw keys so a malformed proposal does not escape serialisation.

### Contests

`take`, `strike`, `restrain` and `throw` are compound operations owning the
actor, the target, the target's cell and the relationship. They also write the
world's contest slot and event state (`world/contest`, `world/events`). For a
`take` the target comes from `params["source"]`; the other contests use
`params["target"]`. The target is included in both `reads` and `writes` even
when it is missing or not an actor, because refusal is only known during
enactment.

### Joint acts

Joint responses with the same key as `_resolve_joint_groups` — `(task,
object/worker, repr(toward))` — become one compound operation per group. It
owns every member actor, its cell, and the task's shared resources:

- `carry`: the object, its current cell, the destination cell and the members'
  cells.
- `crew`: the worker, the worker's job, and the members' cells.
- malformed/unsupported tasks: the members plus `world/global` and
  `world/events`.

Members of a joint group do not also get an individual major-action operation.
Their speech and memory operations are still emitted.

### Engine wiring

`BigvilleGame` now has:

```python
tick_graph_enabled = True
last_tick_graph: TickGraph | None = None
```

The constructor also accepts `tick_graph_enabled=False`. In both
`_step_inline` and `_step_deferred`, after `world.tick()`, `animal_turn()` and
`world.mark_turn_start()`, and before `_resolve_joint_groups`, the engine does:

```python
self.last_tick_graph = (build_tick_graph(order, responses, self.world)
                        if self.tick_graph_enabled else None)
```

No result, error, continuation, contest or joint path was changed. Graph
building is read-only; if it raises, the error propagates as a programming
error.

## Tests

`tests/test_tick_graph.py` (14 tests):

1. `Resource` is hashable, frozen and has a stable string form; `Operation` is
   read-only and serialises.
2. Two moves into the same cell conflict; the move operation reads and writes
   actor, source cell and destination cell.
3. Two transfers of the same stock conflict.
4. A `take` conflicts with the target's `rest`.
5. A malformed `take` still names its target in reads and writes.
6. Two independent rests (and a sleep) do not conflict.
7. Unknown verbs write `world/global` and conflict with each other.
8. Graph order equals the supplied order, including when utterances add
   auxiliary operations.
9. A forced cycle raises `TickGraphCycle`.
10. Two joint members with the same key become one compound operation, a
    member's speech remains its own operation, and the carry cell/item
    resources are present.
11. A joint crew reads and writes the worker and job.
12. A joint crew reads and writes the worker and job.
13–14. Three-turn integration on `town100` seed 305000 and the small TG01
    room with the flag on and off: identical `TurnTrace` records and digest,
    identical per-turn world checkpoints, identical `last_order`,
    `last_results` and `last_errors`; with the flag on,
    `last_tick_graph.topological_order() == last_order`.

## Commands and results

```bash
python3 -m pytest -q tests/test_tick_graph.py -p no:cacheprovider
# 14 passed in 19.60s

python3 -m pytest -q tests/test_tick_graph.py tests/test_tick_snapshot.py \
  tests/test_tick_trace.py -p no:cacheprovider
# 28 passed in 92.74s (0:01:32)

python3 -m pytest -q tests/test_phase055_concurrency.py \
  tests/test_phase029_contest.py tests/test_phase038_strikes.py \
  tests/test_phase047_joint_actions.py -p no:cacheprovider
# 81 passed in 50.21s
```

One earlier run of `test_phase055_concurrency.py` had the timing-only
`test_a_slow_provider_is_faster_when_decided_concurrently...` fail at a
speed-up ratio of 0.82 against its 0.75 threshold; the test passed when run
alone and the whole group passed on re-run. No determinism assertion failed.

## Known limitations

- The verb table is metadata, not a proof. It over-declares some conflicts
  (for example all actions on the same stock kind) and cannot see future verbs;
  those fall back to `world/global`.
- Resource names are resolved from the proposal and `_actor_targets` at graph
  build time. A backend that uses a private naming scheme without populating
  `_actor_targets` gets conservative but coarse keys.
- `topological_order()` without `include_auxiliary=True` is the actor-facing
  order, not every operation. Speech and memory are deliberately auxiliary.
- A joint group collapses several order entries into one operation at its
  earliest member's index. In this phase the executor ignores the graph, so
  this only matters to a future scheduler; TG05 must expand or handle group
  members explicitly.
- The graph is built after `animal_turn()` and `mark_turn_start()`, matching
  the point where responses become immutable, but before joint resolution.
  Joint operations therefore describe reads/writes of the world as it stands
  before joints run, not the joint result.
- No graph is checkpointed or restored; `last_tick_graph` is session state,
  like `last_order`. Turning the flag off leaves it `None`.

## Handoff to TG05

TG05 can rely on:

- `build_tick_graph(order, responses, world)` is deterministic, read-only and
  gives one actor-facing operation per order entry, plus auxiliary speech and
  memory operations, plus one compound operation per joint group.
- `graph.topological_order()` is the supplied `turn_order` for the ordering
  tests; `include_auxiliary=True` is the full operation linearisation for an
  executor.
- `conflicts(op_id)`, `predecessors(op_id)` and `successors(op_id)` expose the
  precedence relation. Edges run from smaller tie-break to larger tie-break,
  so a ready-set scheduler with the same comparator is sequentially
  equivalent.
- `to_dict()` is stable enough for a tick log or debug checkpoint. It contains
  operation payloads and edges, not the live world.
- Contests and joint acts are already compound and own all participants, so a
  threaded executor can treat each as one indivisible operation.
- The engine still applies responses serially; TG05 must move per-attempt state
  (`_outcome_open`, `_refusal_code`, `_major_dispatch`) before committing
  independent operations concurrently.
