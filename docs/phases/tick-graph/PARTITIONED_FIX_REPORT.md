# Partitioned executor divergence: diagnosis and fix

Status: fixed in the `engine-speedups` worktree, 8 November 2026.
Related: `docs/design/TICK_GRAPH.md` (TG07), `docs/design/ENGINE_SPEEDUPS.md`.

## Symptom

`tools/verify_tick_equivalence.py --turns 8 --affordance-mode menu` matched
serial and threaded but the partitioned executor first diverged at turn 6 in
`world_sha256`. Proposals, results, order, errors and continuations were
identical. Lazy + partitioned diverged earlier. The four-turn TG07 test never
reached the first divergence.

## Root causes

The divergence was not one bug. Reproducing with seed 305000 identified swapped
terrain/energy/hunger on two same-cell movers; further seeds exposed three more
ordering/declaration gaps.

1. **Within-shard lexical order.**
   `PartitionedExecutor.commit` used `plan.by_shard[shard]` directly. That tuple
   is sorted by actor name, not by `turn_order`. Two same-cell movers could
   therefore wear/step in the opposite order even inside one shard.
   Seed 305002: Cask Kindle and Erasmus Codling shared step cell `(10,22)`.

2. **Coordinator-first reordered spatial units.**
   Coordinator units ran before every spatial shard. A coordinator unit and a
   spatial unit that shared a resource were not merged into one component, so
   the coordinator unit could act before a spatial unit that preceded it in
   `turn_order`. Seed 305002: Cask Kindle ran before Erasmus Codling in
   partitioned mode, after him in serial.

3. **Moves under-declared their step cell.**
   The tick graph declared a move's source and final destination cells, but
   `move_actor` actually moves one step and wears that step cell. Two walkers
   with different final destinations could share a step cell without a
   conflict. Fixed by adding a `step_cell` resource to the `move` verb and
   resolving it through `world._movement_step`.

4. **Co-location witnesses were not declared.**
   Sleep/collapse, wake, contests, throws and attempts can record a witness
   event only if someone is still on the cell. A move/action pair could change
   who is present without sharing a declared resource. Seed 305004: Wat
   Haywain's sleep event was witnessed in serial but not partitioned because
   nearby actors had already moved. Fixed by adding a spatial
   `Resource("witness", cell)` to every major-action unit, plus destination
   cells for moves. The shard map maps cell witnesses to the cell's shard and
   observer-name witnesses to the observer's actor shard.

5. **Event ids are allocation order, not semantics.**
   After the ordering fixes, seed 305001 still differed only in `event:1` /
   `event:2` assignment: the same two events were minted in the opposite order.
   Event keys are internal allocation ids. `semantic_world_state` now drops the
   `id` from allocation-keyed logs (`events`, `articles`, `editions`,
   `handovers`, `proposals`, `cases`) and sorts by content, as it already did
   for utterances.

## Fixes

- `bigville/sharding.py`
  - Each shard's component is sorted by `turn_order` index before commit.
  - `partition_units` now runs a union-find over shared resources. Units that
    share a resource are one component; a component goes to the coordinator
    when it touches a coordinator resource or spans shards.
  - `witness` resources map to a cell shard (cell key) or actor shard
    (observer-name key), not always to the coordinator.
- `bigville/game.py`
  - Every major-action unit declares its current cell as a `witness` resource;
    a move also declares its destination cell. Object-move observer-name
    witnesses remain for one-cell-away observers.
- `worlds/tick_graph.py`
  - `move` reads and writes `step_cell`; `_BuildContext` resolves it via
    `world._movement_step`.
- `bigville/tick_trace.py`
  - Semantic equality ignores allocation-order log ids.
- `tests/test_tick_sharding.py`, `tests/test_tick_graph.py`
  - Regression coverage for step-cell conflicts, shared-resource merging,
    witness shard mapping, same-cell mover order (seed 305002), and event-id
    normalisation.

## Verification

Menu mode, serial vs partitioned, semantic state every turn:

| seeds | turns | result |
|---|---|---|
| 305000, 305001, 305002 | 24 | equal |
| 305003–305006 | 16 | equal |
| 305010–305015 | 12 | equal |
| 305000, 305002 | 32 | equal |

Lazy mode (default turn batching/on-demand snapshots), serial vs partitioned:

| seeds | turns | result |
|---|---|---|
| 305000, 305002 | 24 | equal |

Targeted tests:

```bash
python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py tests/test_tick_occupancy.py \
  -p no:cacheprovider
# 50 passed

python3 -m pytest -q tests/test_engine_rule_batching.py tests/test_engine_reads.py \
  tests/test_engine_defaults.py tests/test_lazy_*.py -p no:cacheprovider
# 156 passed, 1 skipped
```

`eng.node`/`_run` counts and the engine speedups are unaffected. The strict
`step_trace` `world_sha256` still differs between concurrent executors because
it intentionally includes raw node ids; the semantic oracle is the equivalence
contract for concurrent commit. Partitioned remains opt-in; serial is the
default executor.

## Remaining scope

- The partitioned executor is still in-process and shares one world object.
  Real process/worker distribution needs message transport, versioned shard
  snapshots and a durable tick log, as recorded in TG07.
- The witness declaration is conservative: co-located actors serialize even
  when their actions do not emit a witness event. Correctness first; a later
  pass can narrow the resource to event-emitting verbs if the parallelism is
  worth it.
