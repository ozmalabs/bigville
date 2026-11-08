# DS01 — Determinism helper and removal of the global runtime RNG

Status: implemented, uncommitted (review/commit by the supervisor).
Base commit: `07f6106` (`Deterministic chance: state-derived seeds plan`).
Worktree: `deterministic-seeds`.

## Delivered

- `domains/determinism.py` (new): the canonical seed/draw helper.
- `worlds/bigville_world.py`: weather and infrastructure no longer consume a
  shared RNG; `world._rng` is gone.
- `bigville/world_persistence.py`: new checkpoints carry no RNG state; legacy
  `_rng_state` is ignored on restore.
- `tests/test_determinism.py` (new): canonicalisation, stable draws, actor
  state, weather, infrastructure, legacy/new checkpoint tests.
- Existing tests that asserted the removed `_rng` attribute were updated to
  assert its absence (Phase 008, 025, 044, 070).

## Helper contract

`domains/determinism.py` is import-safe and never constructs a world.

- `canonical_bytes(*parts)` builds one canonical JSON byte string:
  - primitives (`None`, bool, int, finite float, str) are kept as JSON values;
  - `NodeRef` (an `int` subclass) canonicalises as its integer value;
  - mappings are emitted as key/value pairs sorted by canonical key bytes;
  - lists and tuples share one sequence form, so a checkpoint that decodes a
    tuple as a list yields the same draw;
  - sets/frozensets emit members sorted by their canonical JSON;
  - bytes are tagged as hex;
  - non-finite floats raise `ValueError`; arbitrary objects raise `TypeError`
    naming the unsupported type;
  - cyclic containers raise `ValueError`.
- `derive_seed(world_seed, *parts) -> int` hashes the domain prefix
  `bigville.determinism.v1` plus the canonical input with BLAKE2b-128 and
  returns a 128-bit integer. No Python `hash()`, `id()`, process salt, UUID or
  wall clock is used.
- `uniform(world_seed, *parts) -> float` takes the top 53 bits of the derived
  seed and returns a value in `[0, 1)`.
- `choice`, `shuffle`, `sample` use the same derived stream. `shuffle`/`sample`
  return new lists and never mutate the input. Unordered inputs (sets) are
  sorted by canonical member bytes before drawing.
- `world_seed(world) -> int` reads `_burial_seed`, then `_animal_life_seed`,
  then the map node's `seed` attribute, then `world.map_seed`; it raises a
  clear error rather than inventing process identity or time.
- `actor_state(world, name)` returns a stable snapshot of:
  - the actor's node attributes (sorted keys),
  - body-node attributes (sorted keys),
  - `alive`, position, and `present`.
  A missing actor returns `{"name": ..., "present": False}` instead of raising.
- `state_uniform(world, purpose, *parts, actors=())` includes the world seed,
  the purpose, the parts and the state of:
  - every explicit name in `actors`, and
  - every string in `parts` that names an actor in the world.
  `state_seed(...)` is the corresponding 128-bit seed. This is the runtime
  default for later phases.

## Weather source

`_set_daily_weather(day, season)` now uses:

```python
determinism.choice(options, determinism.world_seed(self),
                   "weather", day, season, options)
```

The option set is part of the identity, so a table change changes the draw.
There is no `world._rng` read. The existing season tables and weather
probabilities/weights are unchanged; only the chance source changed.

## Infrastructure source

`_advance_infrastructure` now uses:

```python
determinism.uniform(determinism.world_seed(self), "infrastructure", name,
                    attrs.get("kind", ""), self._town_period(),
                    condition, risk)
```

and fails when the draw is below `failure_risk`. The draw includes the
infrastructure identity, kind, period, condition and risk, so the same state
and period give the same decision and a changed condition/risk is visible in
the identity. The 0.25 condition loss and all existing thresholds are
unchanged.

## Persistence migration

- New checkpoints do not write `_rng_state` and no longer read `world._rng`.
- `_rng` was removed from `_EXTERNAL_FIELDS` because the attribute no longer
  exists.
- On restore, legacy `_rng_state` (and a defensive legacy `_rng` key) is
  skipped before decoding; the checkpoint schema string is unchanged
  (`bigville/world-checkpoint/1`). Old checkpoints therefore load and then
  behave deterministically from their restored state.
- `random` is no longer imported by `bigville/world_persistence.py`.

## Tests and verification

Commands and exact results:

```text
python3 -m pytest -q tests/test_determinism.py -p no:cacheprovider
21 passed in 0.52s

python3 -m pytest -q tests/test_determinism.py \
  tests/test_bigville_world_persistence.py \
  tests/test_bigville_game_persistence.py -p no:cacheprovider
30 passed, 1 skipped in 1.50s

python3 -m pytest -q tests/test_phase042_daynight.py tests/test_engine_defaults.py \
  tests/test_tick_sharding.py -p no:cacheprovider
64 passed in 33.89s

python3 -m pytest -q tests/test_phase008_animal_lifecycle.py \
  tests/test_phase025_turn_order.py tests/test_phase044_births.py \
  tests/test_phase070_locus.py -p no:cacheprovider
73 passed in 96.39s

python3 domains/bigville_entities.py
ERRORS (0), WARNINGS (0), INFO (120); production graph 481 nodes / 864 edges.
```

The new tests pin canonical byte values and one derived seed, so they do not
depend on Python's salted `hash()`. They cover dict/set ordering, `NodeRef`,
tuple/list equivalence, rejection of non-finite/unsupported values, stable
choice/shuffle/sample, A-then-B vs B-then-A draws per actor, actor/body state
inclusion, automatic named-actor inclusion, weather parity and variation, and
infrastructure parity/variation. The legacy-checkpoint test injects an
`_rng_state` field into a fresh checkpoint, refreshes the manifest hash, loads
it, and checks that weather and infrastructure continue like an uninterrupted
control.

## Audit

`grep -rn "_rng" --include=*.py worlds bigville domains` finds no production
runtime attribute or read. Remaining hits are:

- `rng = np.random.default_rng(...)`: creation-time/generation streams
  explicitly allowlisted by the plan (population, kinship, town100, social
  seed, knowledge, relationship seeding) and `_stable_draw`/animal-birth code
  scheduled for DS02.
- `bigville/world_persistence.py`: comments plus the legacy-key skip.
- `docs/phases/phase016a/founding_town_digest.py:81`: a historical digest tool
  (not production runtime) still reads `world._rng.getstate()`. It will need
  updating if that historical digest is rerun; it is intentionally untouched
  here so the recorded Phase 016a digest surface is not silently redefined.

`worlds/bigville_world.py` still imports `random` and uses `random.Random` in
`_stable_draw`, `_burial_roll` and `_give_birth`; those are DS02 migrations,
not part of DS01's two global draws.

## Limitations / notes

- Determinism is guaranteed for a fixed Python/data-pack environment. JSON
  float formatting is a documented, version-stable serialisation here; the
  plan already excludes cross-numpy/creation-stream version independence.
- The helper snapshots actor and body attributes plus position; it does not
  include inventories, relationships or cognition state. DS02 can extend the
  snapshot if a specific draw is meant to depend on those.
- The `_rng_state` field is accepted only as an ignored legacy field; no
  migration rewrites old checkpoint files. Rewriting happens only when the
  world is saved again under the new writer.

## Handoff to DS02

Replace the remaining runtime stateless draws:

- `_stable_draw` -> `state_uniform(world, purpose, *parts, actors=...)`;
- `_burial_roll` -> the same helper;
- birth conception/name/stillbirth/sex/infant/maternal draws and animal
  litter/sex draws -> state-derived draws including the dam/mother/child state;
- strike aim in `worlds/body.py` -> attacker and target state.

`state_uniform` already auto-includes any part string that names an actor, so
call sites can migrate by switching the helper and adding explicit `actors`
only for multi-party draws. Do not change probability tables, thresholds or
the 0.25 infrastructure loss.
