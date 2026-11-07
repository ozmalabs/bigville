# TG02 — Occupancy index

Base commit: `c72fcb6935f1c21e259afb3f0f1240d1bbbd2242` (TG01)

## Scope

TG02 replaces repeated full-resident proximity scans in the nearby-resident and
object-witness paths with a derived cell index over `_actor_positions`. The
canonical world state, `world.distance`, `_map_cells`, the checkpoint schema and
all observable turn output stay the same.

Files changed:

- `worlds/bigville_world.py`
- `bigville/game.py`
- `tests/test_tick_occupancy.py` (new)
- `docs/phases/tick-graph/TG02_REPORT.md` (this report)

## Design

### `_ActorPositions(dict)`

`_actor_positions` is still the canonical `name -> cell` mapping and still
checkpoints as a plain dictionary. The new `_ActorPositions` subclass adds a
derived `cell -> set(names)` bucket map on the instance. Because the bucket map
is an attribute of the mapping object rather than a key, the existing checkpoint
encoder (`_checkpoint_encode`, which iterates `dict.items()`) never sees it.

Overridden mutation paths keep the index coherent:

- `__setitem__`, `__delitem__`
- `pop`, `popitem`
- `update`, `clear`, `setdefault`

`rebuild()` recomputes the index from the current contents. `near(cell, radius)`
returns sorted names in the Chebyshev bounding square (radius in cells).

`BigvilleWorld.__init__` now creates `self._actor_positions = _ActorPositions()`.

### Restore safety

World checkpoints decode `_actor_positions` as a plain dict.
`BigvilleWorld._ensure_position_index()` rewraps a plain mapping into
`_ActorPositions` and rebuilds the bucket map in one pass. It is called at the
entry of the movement and proximity helpers:

- `actor_position`
- `_move_actor_to`
- `move_actor`
- `actors_near` / `_actor_candidates`
- `mark_turn_start`

`add_actor` writes through `_ensure_position_index()` as well. There is no
persistence-specific hook in this phase; the first movement or query after a
restore performs the rewrap.

### `actors_near(position, radius, *, alive_only=True, exclude=None)`

- Returns `[]` for `None`, a non-2-tuple, or any malformed position.
- Reads candidates from `_ActorPositions.near`, a Chebyshev square that is a
  strict superset of the walkable-distance ball.
- Filters candidates with the existing `world.distance(...)`, so the result is
  exactly `{other | distance(position, other) <= radius}`.
- Drops names that are not current `_actors` (some tests keep extra
  `_actor_positions` entries), optionally drops `exclude`, and drops dead actors
  when `alive_only=True`.
- Returns sorted names.

### Debug switch

`world._force_linear_proximity` is a property backed by a module-level
`weakref.WeakSet`. Enabling it makes `_actor_candidates` return every positioned
resident, so `actors_near` and the changed call sites use the old brute-force
scan. It is off by default and is never written to `world.__dict__`, so it cannot
enter a checkpoint.

## Call sites changed

- `BigvilleGame._nearby_resident_ids`: radius 8 via `actors_near`.
- `BigvilleGame._context` nearby-resident loop: radius 8 via `actors_near`; the
  final `(distance, id)` sort is unchanged. `distance` is recomputed from the
  distance cache for the observation record.
- `BigvilleGame._apply_turn` object-witness snapshot: radius 1 via
  `actors_near(..., alive_only=False, exclude=actor)`, then intersected with
  `self.backends` in registration order. The acting backend is always included,
  exactly as before. `alive_only=False` preserves the old loop, which did not
  test `is_alive` for witnesses.
- `BigvilleGame._record_physical_changes` still consumes the already-narrowed
  `before`/`after` witness maps; it no longer sits behind a full-resident scan.

No other repeated full-actor walkable-distance scan exists in the changed game
paths. `last_rejections` still iterates actors but performs no proximity test.

## Tests

`tests/test_tick_occupancy.py` covers:

1. `actors_near` equals a full scan over `world._actors` with
   `distance <= radius` on the founding `town100` map and on an authored map
   with walls and occluded pockets, over several cells and radii 0, 1, 2, 4, 8,
   including a non-walkable wall cell and the `exclude` filter.
2. Direct mutations (`__setitem__`, `update`, `pop`, `setdefault`, `clear`) keep
   the index coherent, including after replacing `_actor_positions` with a
   plain dict to simulate a restore.
3. Dead actors are excluded with `alive_only=True` and retained with
   `alive_only=False`.
4. Four-turn `TurnTrace` runs on `town100` seed 305000 and on the small
   three-resident scenario used by TG01:
   - two ordinary runs have the same digest and the same per-turn `last_order`,
     `last_results`, `last_errors`, proposals and continuations;
   - a third run with `world._force_linear_proximity = True` has the same digest,
     records and per-turn engine state.

## Commands and results

```bash
python3 -m pytest -q tests/test_tick_occupancy.py tests/test_tick_trace.py -p no:cacheprovider
# 13 passed in 70.39s

python3 -m pytest -q tests/test_phase028_hearing.py tests/test_bigville_world_migrated.py -p no:cacheprovider
# 124 passed in 17.67s

python3 -m pytest -q tests/test_phase055_concurrency.py -p no:cacheprovider
# 6 passed in 39.44s
```

Additional checks run because this phase touches positions and witness state:

```bash
python3 -m pytest -q tests/test_bigville_world_persistence.py -p no:cacheprovider
# 7 passed in 0.87s

python3 -m pytest -q tests/test_phase029_contest.py tests/test_phase038_strikes.py \
  tests/test_phase047_joint_actions.py tests/test_phase040_objects_as_arms.py -p no:cacheprovider
# 97 passed in 11.05s
```

## Timing observation (not an assertion)

One-off measurement on the development machine: `town100` plus 100 extra
residents (200 total), then time `BigvilleGame._context` for every resident.

```
cold index:  residents=200 total=4.0157s mean=20.078ms
warm index:  residents=200 total=2.4362s mean=12.181ms
cold linear: residents=200 total=3.9271s mean=19.635ms
warm linear: residents=200 total=2.3868s mean=11.934ms
```

At 200 residents the full turn context is dominated by the other observations,
so the index does not visibly change context-build time in this micro-run. A
narrower probe of 3,000 `actors_near` calls over the same 200-resident world
measured `indexed=0.0805s`, `linear=0.1210s` (about 1.5x), showing that the scan
itself is removed while the overall turn remains dominated elsewhere.

## Known limitations

- The index is maintained only while `_actor_positions` is an
  `_ActorPositions`. A caller that reaches through `dict.__setitem__` or
  replaces the mapping without a subsequent movement/query would need
  `rebuild()`. No production path does this; the restore case is handled by
  `_ensure_position_index`.
- The bucket map is process-local derived state. It is intentionally excluded
  from checkpoints and rebuilt on restore.
- World-level event/witness publishers (`_publish_noise`, `_strike_witnesses`,
  `_joint_event`, `_witnesses`) still scan `_actors`. They were not in this
  phase's listed call sites and combine per-observer predicates (sleep, line of
  sight, per-observer night sight range) that need their own equivalence tests.
  They are a candidate for a later phase, not a TG02 regression.
- `_ActorPositions.near` enumerates the `(2r+1)^2` bounding square rather than
  the occupied buckets. At the radii here (0, 1, 8) that is cheaper than a
  resident scan and independent of town size.

## Handoff to TG03

- `actors_near` is the single proximity query for decision-context construction.
  TG03 can build contexts from a frozen snapshot and call it against snapshot
  positions without changing the query contract.
- Keep `world._force_linear_proximity` available as the debug oracle for any
  later phase that changes context construction; the occupancy tests already
  prove index and brute-force paths agree.
- If TG03 or TG05 parallelises context building, do not share the lazy
  `_distance_fields` cache across threads without a guard. It is existing derived
  state, unchanged by TG02.
- If a later phase adds actor creation/removal paths outside `add_actor` or
  `_move_actor_to`, route them through `_ActorPositions` mutations or call
  `rebuild()`.
