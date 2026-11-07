# TG03 — Frozen decision snapshot and parallel context construction

Base commit: `d0d0484` (TG02: occupancy index for proximity and witness scans)

## Scope

TG03 separates "build every decision context" from "ask every backend to
decide". All contexts for a turn are built from one observed turn/position
snapshot before the first `decide()` call. Context construction can use a
thread pool, but contexts and futures are consumed in backend registration
order, and the default output is unchanged.

Files changed:

- `bigville/game.py`
- `worlds/bigville_world.py` (distance-cache guard only)
- `tests/test_tick_snapshot.py` (new)
- `docs/phases/tick-graph/TG03_REPORT.md` (this report)

No commit or stage was performed.

## Design

### `_DecisionSnapshot`

A lightweight dataclass, not a graph copy:

- `turn`: the world turn at the start of the decision phase.
- `positions`: `dict(world._actor_positions)` taken before the practice
  pre-pass.
- `practice_windows`: `actor -> (turn, start, end)` for every actor that needs
  a context this turn.

The snapshot is created by `_build_contexts`, returned to the caller, and used
as a turn-consistency guard while contexts are built. It deliberately does not
copy the canonical graph. Widening it into a full frozen world remains a later
phase's job.

### Two pipelines

- `BigvilleGame.step()` dispatches on `_defer_decisions`.
- `_step_deferred()` (default) computes every interrupt reason, decides which
  actors need a context, prepares practice windows, builds all contexts, then
  asks backends in registration order.
- `_step_inline()` is the previous build-then-decide loop, retained verbatim
  under `_defer_decisions = False` as the in-commit equivalence oracle.

New settable defaults:

```python
BigvilleGame.context_workers = 1        # 1 builds contexts serially
BigvilleGame._defer_decisions = True    # False keeps the inline oracle
BigvilleGame._verify_context_purity = False
```

### Context construction

`_context(actor, *, practice_window=None, snapshot=None)`:

- With no window (external/legacy callers), it keeps the old behaviour: the
  first context of a turn advances `_published_practice`.
- With a prepared window it only slices the practice records and does not
  read or write `_published_practice`.
- A supplied snapshot must match the current world turn; a stale snapshot
  fails loudly.

`_build_contexts(actors)`:

1. records the turn and position snapshot before the pre-pass;
2. calls `_prepare_practice(actors)`;
3. builds contexts serially or with `ThreadPoolExecutor`, consuming futures in
   registration order;
4. checks that the world turn did not change and asserts the snapshot
   positions are unchanged;
5. optionally hashes `eng.to_checkpoint_dict()` before and after construction
   (`_verify_context_purity`, or call `_assert_decision_snapshot_unchanged`
   directly from a test).

`world.distance()` now holds a module-level `threading.RLock` around its lazy
`_distance_fields` cache and BFS. The BFS result is unchanged and the lock is
never checkpointed. Pooled context builds therefore cannot race on the cache.

## Practice-window subtlety

The inline loop did **not** build a context for every actor:

- an actor with an active continuation and no interrupt got a context only if
  its backend has a callable `note_turn`;
- a dead actor got no context;
- an actor after a human `waiting` step was never reached.

`_prepare_practice` therefore runs over exactly the actors the inline loop
would have built contexts for, in registration order, and leaves every other
actor's `_published_practice` entry untouched. The pre-pass copies the old
formula exactly: `start` is the previous `end`, and `end` is the current
practice length. Because practice records are only appended during enactment,
the length is stable throughout the decision phase.

## Waiting subtleties

The deferred path builds contexts that the inline path may never have reached.
When a backend returns `waiting` at actor *k*, actors after *k* would have
kept their old practice windows in the inline path, so
`_restore_practice_after` puts them back exactly as they were before the
pre-pass (including deleting entries that did not exist). The waiting payload
keeps today's shape and uses the prebuilt context for actor *k*:

```python
{"status": "waiting", "actor": actor,
 "context": context.observations,
 "affordances": world.actor_affordances(actor)}
```

If a **concurrent** backend returns `waiting`, the old path had already visited
every actor before `decide_pooled`, so no practice restore is done; only the
serial/early waiting branch restores later windows.

## Tests

`tests/test_tick_snapshot.py` (8 tests):

1. `context_workers=1` vs `4` on `town100` seed 305000 and the small TG01 room:
   identical canonically-encoded `ActorContext.observations`/`.affordances`,
   identical trace records and trace digests over four turns.
2. `_defer_decisions=True` vs `False`: identical records, digests and captured
   contexts over four turns on both scenarios.
3. Context building is read-only: the canonical world checkpoint digest and
   snapshot positions are unchanged across `_build_contexts`, and the snapshot
   records every actor's practice window.
4. Serial and pooled builds of one snapshot produce identical context values.
5. Mixed continuations: an uninterrupted continuation with no `note_turn` gets
   no context and no practice window (matching the inline loop), while one with
   `note_turn` gets a context every turn. `_published_practice` matches the
   inline path after every turn.
6. A human `waiting` step returns the same status/actor/context/affordances and
   leaves the same `_published_practice` as the inline path, including no
   window for the actor after the waiting resident.

## Commands and results

```bash
python3 -m pytest -q tests/test_tick_snapshot.py -p no:cacheprovider
# 8 passed in 34.20s

python3 -m pytest -q tests/test_tick_snapshot.py tests/test_tick_trace.py \
  tests/test_tick_occupancy.py -p no:cacheprovider
# 21 passed in 107.99s (0:01:47)

python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_simple_life.py \
  tests/test_scenario_runner.py -p no:cacheprovider
# 29 passed in 43.75s

python3 -m pytest -q tests/test_phase029_contest.py tests/test_phase038_strikes.py \
  tests/test_phase047_joint_actions.py -p no:cacheprovider
# 75 passed in 8.32s
```

Additional checks run because this phase touches continuations and waiting:

```bash
python3 -m pytest -q tests/test_bigville_game_api.py tests/test_fix_simple_village.py \
  tests/test_phase059_autopilot.py -p no:cacheprovider
# 69 passed in 160.01s (0:02:40)

python3 -m pytest -q tests/test_phase033_restraint.py \
  tests/test_bigville_world_persistence.py -p no:cacheprovider
# 29 passed in 3.09s
```

## Known limitations

- The snapshot is intentionally partial: turn, positions and practice windows.
  It proves the decision phase did not move actors or advance the world, but it
  does not yet supply observations themselves. Making `_context` read a fully
  frozen world is deferred.
- On `town100` most residents acquire long uninterrupted continuations after
  the first turn, so a four-turn run rebuilds a context for 15 of 100 residents
  on the second turn and for none on the next two. The small three-resident
  scenario rebuilds every context every turn. Pooling is therefore not a
  measurable speedup on `town100` today; the value is the seam and the
  ordering guarantee, not throughput.
- `_context` still populates derived, non-checkpointed world caches such as
  `_actor_targets` through `actor_affordances`. Those writes are per-actor and
  are not part of the canonical graph; the purity check covers the graph and
  positions, not every derived cache.
- `world.distance` is serialised by one module-level lock. A pooled build does
  not add distance parallelism; it removes the race and preserves the exact BFS
  field.
- Actors after an early `waiting` return have their practice windows restored,
  but their prebuilt contexts were still constructed and may have populated
  derived per-actor caches. No canonical state changes, and the next step
  rebuilds them.
- The pool size is a game attribute, not a constructor/kwarg validated option;
  it defaults to 1 and is not checkpointed.
- Interrupt reasons are computed for the whole turn before the first decision.
  This is equivalent only because decisions are assumed read-only with respect
  to the world. A custom backend that mutates world state inside `decide()`
  would observe a different reason-evaluation order than the inline loop; the
  engine's own backends do not do this.

## Handoff to TG04

TG04 can assume:

- By the time any backend `decide()` runs, every deciding actor's context has
  already been built from one turn and one position map.
- Backend decisions are read-only with respect to the canonical world graph:
  the checkpoint digest and actor positions are unchanged from the first
  context build to the last decision. Backend-owned state and derived caches
  may change.
- `ActorResponse` objects exist for every deciding actor before
  `world.tick()`/enactment, in registration order; concurrent backends return
  through `decide_pooled` in that same order.
- Interrupt reasons (`continuation_interrupted`) are already attached to the
  context/response before enactment.
- Practice windows are published before decisions and are not advanced by
  context construction; an early `waiting` return restores the windows of
  actors an inline run would not have reached.
- Operation metadata may therefore describe reads/writes of enactment without
  modelling decision-phase world writes: there are none in the canonical graph.
