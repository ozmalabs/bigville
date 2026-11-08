# Deterministic chance: state-derived seeds for every stochastic outcome

Status: phases complete, 8 November 2026 (DS04 awaiting review/commit). This program removes shared/global RNG
consumption from the simulation and makes every runtime chance outcome derive
from a deterministic seed of the involved parties' state, the world seed and
the turn/period. A shard therefore produces the same outcome regardless of
scheduling, executor or action order.

## Why

The distributed runtime can now dispatch bundles, but a shared `world._rng`
still makes outcomes order-dependent: two shards that draw in a different order
receive different values. `random.Random(str)` seeding is deterministic within
one Python version but is still an implicit, uncentralised contract. The goal
is an explicit, auditable rule:

> Given the same world seed, turn and involved-entity state, a stochastic
> outcome is the same value, regardless of executor, shard, action order or
> process.

## Invariants

1. **No shared mutable RNG at runtime.** No `world._rng` consumption for
   simulation outcomes; no module/global `random` state.
2. **State-derived seeds.** Each draw is keyed on the world seed, a stable
   purpose/stream name, the turn/period, and the canonical state of every
   involved party/entity.
3. **Order independence.** Drawing for A then B, or B then A, gives each its
   same value. Parallel shards see the same outcomes.
4. **Checkpoint continuity.** Restoring a world at the same turn/state yields
   the same future draws; no hidden RNG state is required.
5. **Explicit exceptions.** Creation-time generation (cast, population, kinship,
   initial relations) may use seeded `numpy` streams because it runs once
   before the shard simulation and is deterministic from the run seed. Those
   sites are allowlisted and audited.
6. **No wall-clock or process-salted input.** No `id()`, Python `hash()`,
   `time`, UUID or unseeded random in simulation outcomes.
7. **No behaviour change beyond replacing the chance source.** Probabilities,
   tables and decision rules stay the same; only the value source changes.

## Determinism helper

`domains/determinism.py`:

- `canonical_bytes(*parts)`: canonical JSON/bytes for primitives, mappings,
  sequences, `NodeRef`-like ints; sorted keys, stable numbers.
- `derive_seed(world_seed, *parts) -> int`: BLAKE2b (or SHA-256) digest of the
  canonical input, domain-separated by purpose.
- `uniform(world_seed, *parts) -> float`: seed integer mapped to `[0, 1)`.
- `choice(seq, world_seed, *parts)`, `shuffle(seq, world_seed, *parts)`,
  `sample(seq, k, world_seed, *parts)`: deterministic equivalents.
- `world_seed(world)`: the map/seed value already used for deterministic
  generation; no process identity.
- `actor_state(world, name)`: canonical stable snapshot of the involved actor:
  attrs, body attrs, alive/position, and other state that affects the outcome.
- `state_uniform(world, purpose, *parts, actors=())`: includes the canonical
  state of every named involved actor/entity; this is the runtime default.
- `state_seed(world, purpose, *parts, actors=())` for non-uniform uses.

The helper must be importable without constructing a world and must not use
Python's salted `hash()`.

## Phases

Each phase is implemented by one agent, reviewed and committed by the
supervisor, with a report in `docs/phases/deterministic-seeds/DSxx_REPORT.md`.

### DS01 — Determinism helper and remove the global runtime RNG

**Scope:** Add the helper, replace the two global `world._rng` outcomes, and
retire the runtime RNG state from persistence.

**Files:** `domains/determinism.py` (new), `worlds/bigville_world.py`,
`bigville/world_persistence.py`, tests, report.

**Deliverables:**
- `domains/determinism.py` as above, with tests for canonicalisation, stable
  values, actor-state inclusion, and no salted-hash use.
- Weather selection (`_set_daily_weather`) uses a state/world-seed draw keyed on
  day, season and the option set; it no longer consumes `world._rng`.
- Infrastructure failure (`_advance_infrastructure`) uses a state/world-seed
  draw keyed on infrastructure identity, period/day and condition; no
  `world._rng`.
- Remove `world._rng` and its checkpoint state. Old checkpoints carrying
  `_rng_state` load cleanly (the field is ignored/migrated); new checkpoints
  do not write it. Document the schema change.
- Audit: no `_rng` remains in production runtime code.
- Tests: weather/failure same across repeated runs and action orders; no
  `_rng` attribute; legacy checkpoint loads; a state change changes the draw
  where the helper includes that state.
- Existing tests that asserted the old RNG state or exact weather sequences are
  updated for the new deterministic source; probabilities/tables unchanged.

**Gate:** targeted tests including persistence and world migrations.

### DS02 — State-derived runtime draws

**Scope:** Migrate every runtime stateless draw to the helper with involved
party state.

**Files:** `worlds/bigville_world.py`, `worlds/births.py`, `worlds/body.py`,
`domains/interoception.py` (if a draw belongs there), tests, report.

**Deliverables:**
- `_stable_draw` becomes `state_uniform(world, purpose, *parts, actors=...)`.
  It automatically includes every named actor in `parts` (illness, meal,
  birth, burial, aim) and accepts explicit `actors` for multi-party draws.
- `_burial_roll` uses the same helper.
- Birth conception/name/stillbirth/sex/infant/maternal draws include the
  mother/child state and day.
- Meal illness, disease onset, buried-body onset, and any other chance draw
  include the involved actor/body state.
- Strike aim (`worlds/body.py`) uses the helper with attacker and target state,
  replacing the direct `interoception.draw` for this outcome.
- Animal birth sex/litter draws use the helper with dam/litter/state (not a
  local `random.Random` string).
- Tests:
  - same state/turn/actor -> same value;
  - changing the involved actor/body state changes the value (where the draw
    is meant to depend on state);
  - draw order A-then-B vs B-then-A is equal per actor;
  - birth/illness/meal/burial/aim distributions still use the same tables and
    probabilities (statistical tests use fixed seeds and tolerances only where
    existing tests already do);
  - serial vs partitioned produces the same outcome on a chance-heavy seed.
- Update hardcoded digest/oracle tests that legitimately change because the
  chance source changed; do not change probability tables.

**Gate:** targeted tests and a serial-vs-partitioned determinism check.

### DS03 — Turn order, reporting, generation audit and source audit

**Scope:** Centralise the remaining deterministic shuffles/samples and make the
rule auditable.

**Files:** `bigville/game.py`, `bigville/reporting.py`,
`bigville/management/cast_generation.py`, `worlds/bigville_world.py` generation
seed sites if needed, tests, report.

**Deliverables:**
- `turn_order` uses `determinism.shuffle` with the world seed and turn, not
  `random.Random(f"{seed}:{turn}")`. Same output contract, no stdlib RNG.
- Reporting sample uses `determinism.sample` with its explicit seed.
- Cast generation uses the helper or a clearly documented seeded stream for
  its deterministic traits.
- Creation-time `numpy` streams (`population`, `kinship`, `town100`,
  `social_seed`, `knowledge`, `relationship_seeding`) are audited and
  allowlisted as deterministic generation. Each must derive from an explicit
  run/config seed, never wall clock/process identity.
- Add a source-audit test:
  - production runtime modules contain no `random.Random`, `.random()`,
    `randrange`, `shuffle`, `sample`, `np.random` outside the determinism
    helper and the documented generation allowlist;
  - no `_rng` attribute or persistence state;
  - no `hash()`, `id()`, `time`, `uuid` in a stochastic seed path.
- Tests: turn order unchanged for known seeds; reporting sample stable;
  source audit passes with the allowlist.
- Update any hardcoded ordering/reporting expectations only where the source
  changed, not the semantics.

**Gate:** source audit + targeted suites.

### DS04 — Shard/executor determinism verification and final report

**Scope:** Prove the outcome rule under serial, threaded, partitioned and
process transports, including checkpoint restore.

**Files:** `tools/verify_deterministic_chance.py` (new),
`tests/test_deterministic_shards.py` (new), `FINAL_REPORT.md`, README, plan
status.

**Deliverables:**
- Tool:
  - run the same scenario/seed under serial and partitioned (bundle) orders;
  - compare semantic world state, revisions and per-actor chance outcomes;
  - run two partitioned replays; compare execution/payload checksums;
  - checkpoint/restore at a turn and continue; compare the remaining run;
  - optionally run a shuffled or synthetic multi-shard chance scenario.
- Seed matrix: 305000, 305002, 305004, 305006, 8-16 turns; include a
  chance-heavy scenario (births/illness/weather/infrastructure) where the
  switches are on if available.
- Tests: same draw values under reordered actors and shards; checkpoint
  continuity; no shared RNG; partitioned semantic equality.
- Measure any performance effect of the helper (draws/turn, ms/turn) and
  record it; hashing is expected to be small compared with the rule passes.
- README/docs: the determinism rule, the generation allowlist, what is
  guaranteed and what is not (e.g. numpy version/distribution caveat for
  creation-time streams).
- Final report: what changed, the audit result, the seed matrix, remaining
  risks and exact full-suite status. Do not claim a full-suite pass that did
  not complete.

**Gate:** targeted suites, self-test, and the determinism tool.

## Status

| Phase | Status | Commit |
|---|---|---|
| DS01 | complete | `6a3768c` |
| DS02 | complete | `f34a7dc` |
| DS03 | complete | `4c82dfe` |
| DS04 | complete (uncommitted) | pending review/commit |

## Integration gates

```bash
python3 -m pytest -q tests/test_determinism.py tests/test_deterministic_shards.py \
  tests/test_births.py tests/test_illness.py tests/test_phase044_births.py \
  tests/test_phase046_detraining.py -p no:cacheprovider
python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph_executor.py \
  tests/test_engine_defaults.py tests/test_lazy_*.py -p no:cacheprovider
python3 domains/bigville_entities.py
```

## Non-goals

- No change to probability tables, thresholds or game balance.
- No attempt to make creation-time numpy sampling version-independent across
  numpy releases; it is deterministic for a fixed environment and seed.
- No Ocelot dependency.
