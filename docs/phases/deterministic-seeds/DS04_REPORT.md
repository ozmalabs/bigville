# DS04 — Shard/executor determinism verification and final report

Status: implemented, uncommitted (review/commit by the supervisor).
Base commit: `4c82dfe` (`DS03: deterministic ordering, sampling and source audit`).
Worktree: `deterministic-seeds`.

## Delivered

- `worlds/body.py`: `Body.clock()` now returns a **state-derived runtime
  seed** when the body is attached to a world:
  `determinism.state_seed(world, "interoception", actor, turn)`. It no longer
  hands the fixed creation-time body seed to `interoception.derive`. A body
  built from tables alone (`world is None`) keeps its fixed body seed, and
  `initial_state`/`acuity_of` creation-time behaviour is unchanged.
- `domains/interoception.py`: documented that `draw` is a stateless SHA-256
  hash (never Python's salted `hash()`), that its runtime seed is now
  state-derived for a world-backed body, and that only creation-time acuity
  keeps the fixed body seed.
- `tools/verify_deterministic_chance.py` (new): the DS04 verification matrix
  (serial vs partitioned, partitioned replay, reordered draws,
  checkpoint/restore, shared-RNG/source audit, chance-heavy evidence).
- `tests/test_deterministic_shards.py` (new): fast small-scenario coverage of
  the same rule (reordering, serial/partitioned, two partitioned replays,
  checkpoint at turn 3 + 2 turns, no `_rng`, clean source audit).
- `docs/phases/deterministic-seeds/FINAL_REPORT.md` (new).
- `README.md`: short "Deterministic chance" section.
- `docs/design/DETERMINISTIC_SEEDS.md`: DS01-DS04 status rows.
- No probability table, threshold or balance value changed.

## Interoception runtime seed

Before DS04, `Body._derive` called `I.derive(..., seed, ...)` with
`self.state["seed"]`, the fixed seed stored when the body was created. That
made per-tick jitter (and the sound form chosen inside `derive`) stable for a
body, but not derived from actor state. DS04 changes `clock()` to:

```python
turn = int(getattr(self.world, "_turn", 0)) if self.world is not None else 0
if self.world is not None:
    return int(determinism.state_seed(
        self.world, "interoception", self.actor, turn)), turn
return int(self.state["seed"]), turn
```

The draw is still `I.draw`'s stateless SHA-256 hash; there is no shared RNG.
The creation-time acuity remains `I.acuity_of(rules["acuity"], body_seed,
actor, life_stage)` in `initial_state`, so an existing body keeps exactly the
acuity it was created with. `I.derive` remains a pure function.

## Verification matrix

`tools/verify_deterministic_chance.py` default matrix:

```text
python3 tools/verify_deterministic_chance.py \
  --seeds 305000,305002,305004,305006 --turns 8 --json
```

Exit code **0**, `"ok": true`, 125.3 s wall clock (2 m 5.3 s), host load
average 5.26 at the time of measurement.

| Seed | Semantic state | Payload hash | Revision | Execution (two partitioned replays) | Reorder | Checkpoint | `_rng` absent |
|---|---|---|---|---|---|---|---|
| 305000 | equal | equal | equal | stable | pass | pass | yes |
| 305002 | equal | equal | equal | stable | pass | pass | yes |
| 305004 | equal | equal | equal | stable | pass | pass | yes |
| 305006 | equal | equal | equal | stable | pass | pass | yes |

Each seed ran a serial game, a partitioned game and a second partitioned
replay for 8 turns. Every turn compared `semantic_world_state` (dict equality),
`tick_payload_sha`, and `world.revision`; the two partitioned replays also
compared `tick_execution_sha`, committed order and `run_execution_sha`.
No first divergence was reported for any scope.

The matrix uses a documented chance-heavy setup applied identically to every
game: births and illness switches on, the clock one tick before dawn (so the
daily weather and illness/birth draws fire), a well with `failure_risk = 1.0`,
a gestating dam, and one explicit `pass_period(1)` so the infrastructure and
animal-birth draws fire without waiting 96 turns. Evidence from the default
run:

| Seed | Weather observed | Infrastructure failed | Animal birth drawn | `_stable_draw` counts across compared games |
|---|---|---|---|---|
| 305000 | cool | yes (condition 0.75) | yes | births 111, illness 300, meal_illness 3 |
| 305002 | rain | yes (condition 0.75) | yes | births 99, illness 300, meal_illness 3 |
| 305004 | cool | yes (condition 0.75) | yes | births 108, illness 300, meal_illness 3 |
| 305006 | mild | yes (condition 0.75) | yes | births 96, illness 300, meal_illness 3 |

Weather and infrastructure are `determinism.choice`/`uniform` calls inside the
world (not `_stable_draw`), so they are evidenced by the changed weather and
condition rather than the `_stable_draw` counter. The counts are totals across
the games compared for a seed, not per single game.

## Reordering

`reorder_check` evaluates the same controlled draws twice on one world:

- ascending: sorted actor names, weather days 100/101/102 forward,
  infrastructure names forward;
- descending: the fixed reversal of the actor list, the weather days and the
  infrastructure names. This is a documented deterministic reversal, not a
  random shuffle.

Each actor's day and strike target are fixed from the sorted name set, so the
reversal changes only evaluation order, not which draw belongs to which actor.
The event families compared are weather, infrastructure, birth conception,
illness onset, meal illness and strike aim. All 17 events (3 actors, small
scenario) matched per key for every seed; the default town100 matrix reports
`"reorder": {"ok": true, "mismatches": {}}` per seed.

## Checkpoint / restore

For each seed the tool runs a fresh serial game to turn `turns // 2` (turn 4
for the default 8), saves a **game checkpoint**, restores it with
`load_game_checkpoint`, reapplies the same deterministic session options
(serial executor, menu affordances, on-demand snapshots, turn rule batching),
and continues the remaining turns. Every restored turn's semantic payload
checksum and revision equals the uninterrupted baseline trajectory; the prefix
before the checkpoint also equals it. The small-scenario test uses the
required turn 3 + 2-turn case.

Why the session options are reapplied: a game checkpoint stores world, characters, backends and
continuation state, not the executor/affordance/snapshot/rule-batching
configuration. The verification tool restores the same settings explicitly so
the continuation is compared on the same session contract.

## Audit

- `tests/test_random_audit.py`'s matcher is loaded by the tool and run over
  every production file under `bigville/`, `worlds/` and `domains/`:
  **0 findings** in the default matrix.
- No game world has an `_rng` attribute. New checkpoints still write no RNG
  state (DS01).
- `domains/interoception.draw` remains a documented presentation/creation
  allowlist entry; its runtime seed is now state-derived but it is still a
  stateless hash, not a shared RNG.
- The source audit finds no new `random.Random`, `np.random`, `_rng`, builtin
  `hash` or `id` seed site.

## Overhead

Measured on the development host (load average 5.26 4.61 4.86). The profile
harness uses its own defaults (`affordance_mode=lazy`,
`snapshot_mode=every_turn`, `rule_batching=action`) and 2 turns:

| Executor | 50 residents | 100 residents |
|---|---|---|
| serial | 178.25 ms/turn | 507.25 ms/turn |
| partitioned | 945.60 ms/turn | 3,075.86 ms/turn |

The partitioned figures are dominated by bundle construction/dispatch, not
hashing. A leaner headless run (lazy affordances, on-demand snapshot, turn
rule batching) on town100 seed 305000 took 244.7 ms/turn and made 17.4
`_stable_draw` calls per turn. On the same world:

- one `state_seed` (full actor-state canonicalisation + BLAKE2b) ≈ 466 µs;
- one plain `determinism.uniform` (no actor state) ≈ 6.3 µs;
- one state-derived `_stable_draw` ≈ 469 µs.

So the state hashing at that draw rate is roughly 8 ms/turn, about 3% of the
lean 245 ms/turn, and a smaller share of the profile-harness figures. This is
a small but not zero cost; it is the price of keying a draw on involved state.
The new interoception runtime seed made **0** `Body._derive` calls in headless
runs (no agent view requested), so it had no measurable headless cost; an
agent view pays one `state_seed` per derivation (about 0.47 ms on this host).
These are absolute measurements under load, not a controlled pre-DS
side-by-side benchmark; no speedup is claimed.

## Tests and exact results

```text
python3 -m pytest -q tests/test_deterministic_shards.py tests/test_random_audit.py \
  tests/test_determinism.py tests/test_state_draws.py tests/test_phase069_body.py \
  tests/test_phase070_locus.py -p no:cacheprovider
114 passed in 34.46s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_bundle_dispatch.py \
  tests/test_engine_defaults.py tests/test_lazy_*.py -p no:cacheprovider
3 failed, 158 passed, 1 skipped in 104.43s

python3 domains/bigville_entities.py
ERRORS (0), WARNINGS (0), INFO (120); production graph 481 nodes / 864 edges.

python3 tools/verify_deterministic_chance.py \
  --seeds 305000,305002,305004,305006 --turns 8 --json
exit 0, "ok": true; 4/4 seeds pass every scope; source audit 0 findings.

python3 -m pytest -q tests/test_deterministic_shards.py -p no:cacheprovider
8 passed in 7.34s

python3 -m pytest -q tests/test_phase070b_body.py tests/test_phase071_attend.py \
  tests/test_phase038_strikes.py tests/test_phase044_births.py -p no:cacheprovider
73 passed in 39.52s
```

The three failures are the three menu-mode trace-digest assertions in
`tests/test_lazy_cheap.py`, `tests/test_lazy_observation.py` and
`tests/test_lazy_target_resolution.py`. They are **pre-existing at the DS03
base commit** `4c82dfe`: running exactly those three tests in a detached
worktree at `4c82dfe` fails with the same actual digest
`a89d51d0…d3b6282f` against the LA01 fixture `8a49c09b…84ee3b`. They pin a
pre-DS03 trace digest and are outside the DS04 scope; no assertion was
weakened. All other tests in that command passed (158 passed, 1 skipped).

`tests/test_deterministic_shards.py` covers:

- the same weather/infrastructure/birth/illness/meal/strike draws under the
  fixed ascending vs descending evaluation order;
- serial vs partitioned semantic state/payload/revision equality for seeds
  305000 and 305002 over 8 turns, plus a non-zero illness draw count;
- two partitioned replays with equal execution/payload hashes and revisions;
- checkpoint at turn 3, restore, continue 2 turns, equal to the uninterrupted
  run (prefix and continuation);
- no `world._rng` and a clean production source audit.

Runtime of the new test file is 7.34 s, well under the ~120 s budget.

## Limitations

- The reordering check is a controlled draw-level test (the exact helper
  calls), not a full scenario with physically reshuffled actor registration.
  The executor comparison is the end-to-end order test for the simulation.
- `_stable_draw` includes actor attrs/body/position/alive, not inventories,
  relationships or cognition; a draw that needs one of those must pass it as
  an explicit part.
- Weather and infrastructure use `determinism.choice`/`uniform` keyed on the
  world seed and the event identity/state, not the actor-state wrapper; that
  is intentional and unchanged.
- Cross-numpy-version creation streams remain out of scope (see the final
  report).
- Overhead was measured under host load, not in an isolated benchmark.
- The `--executor partitioned` mode verifies two partitioned replays instead
  of a serial baseline by design; the default (`both`) runs the complete
  matrix.

## Handoff / remaining work

Supervisor review and commit. The status table records DS04 as complete
(uncommitted) so the commit hash can be filled in after review.
