# DS02 — State-derived runtime draws

Status: implemented, uncommitted (review/commit by the supervisor).
Base commit: `6a3768c` (`DS01: deterministic seed helper and removal of global runtime RNG`).
Worktree: `deterministic-seeds`.

## Delivered

- `worlds/bigville_world.py`: `_stable_draw` now delegates to
  `determinism.state_uniform`; animal births use the state-derived draw;
  `_burial_roll` and the meal-illness draw use the helper; `import random` is
  gone.
- `worlds/births.py`: conception, name, stillbirth, sex, infant and maternal
  draws pass an explicit purpose and include the involved resident(s).
- `worlds/body.py`: aimed-strike aim and the unaimed harm-locus draw both use
  `domains.determinism`; `interoception.draw` is no longer called for a
  physical outcome.
- `domains/determinism.py`: added `animal_state` and `entity_state`;
  `state_uniform`/`state_seed` now auto-include named animals as well as named
  residents.
- `domains/interoception.py`: documented the DS02 allowlist for its local
  `draw`.
- Pack table docs (`packs/*/world/interoception.json`): `HARM_LOCUS` and
  `STRIKE_AIM` now describe the state-derived draw.
- `tests/test_state_draws.py` (new), `tests/test_phase044_births.py` (midwife
  threshold read in the delivery state), `tests/test_phase037_health_routes.py`
  (ledger isolated in the sleep-capacity test),
  `tests/test_phase043_care.py` (comment).
- `docs/design/DETERMINISTIC_SEEDS.md`: DS02 status row only.

## Helper contract

`_stable_draw(self, purpose, *parts, actors=())` is exactly
`determinism.state_uniform(self, purpose, *parts, actors=actors)`. It hashes:

- the world seed (`_burial_seed` / map seed; the animal seed is the same map
  seed);
- the purpose string;
- every positional part;
- the canonical state of every explicit `actors` name and every string part
  that names a resident or an animal.

`entity_state(world, name)` resolves a resident through `actor_state` (attrs,
body attrs, alive, position) and an animal through the new `animal_state`
(sorted attrs from the `Animal` node, alive). A missing name is
`{"name": ..., "present": False}`. Per-turn action bookkeeping remains excluded
through `_VOLATILE_ACTOR_KEYS` (including an animal's `last_npc_action`), so
another shard's claim/outcome cannot change a draw.

## Migrated streams

| Stream | Call | State included |
|---|---|---|
| Conception | `"births", "conceive", mother, day` | mother (`actors=(mother,)`, auto) |
| Newborn name | `"births", "name", mother, day` | mother |
| Stillbirth | `"births", "stillbirth", mother, day` | mother |
| Sex | `"births", "sex", mother, day` | mother |
| First-year infant death | `"births", "infant", child, day` | mother and child |
| Maternal death | `"births", "maternal", mother, day` | mother |
| Meal illness | `"meal_illness", eater, period, kind, meals` | eater |
| Disease onset | `"illness", resident, disease, day` | resident |
| Burial onset | `"burial", resident, day` | resident |
| Strike aim | `"strike_aim", attacker, target, turn, region` | attacker and target |
| Unaimed harm locus | `"harm_locus", actor, cause, turn` | actor |
| Animal birth sex | `"animal_birth", dam, litter_no, index` | dam/animal state |

Animal births keep the species table: `sex = male if draw < birth_male_share`.
The litter count (`births`) is incremented after the litter so the draw sees
the pre-birth dam state and the same state always gives the same sex.

## Allowlist for `interoception.draw`

The local hash draw is used by host code only for deterministic presentation/creation:

- `acuity_of`: a body's acuity, drawn once and stored on the body;
- `sound`: the form of a quality's sound;
- `derive` jitter: per-tick felt-signal jitter, keyed on actor/turn/source.

All of these already derive from the world seed and consume no shared RNG, and
none changes a physical world outcome. `pick_locus` remains as a pure helper
but host code no longer calls it; the world harm locus uses
`determinism.state_uniform`. DS03 should decide whether `pick_locus` is retired
or moved to the determinism helper.

## Tests and exact results

```text
python3 -m pytest -q tests/test_state_draws.py tests/test_determinism.py \
  tests/test_phase044_births.py tests/test_phase008_animal_lifecycle.py \
  tests/test_phase070_locus.py -p no:cacheprovider
109 passed in 41.68s

python3 -m pytest -q tests/test_phase025_turn_order.py tests/test_phase042_daynight.py \
  tests/test_engine_defaults.py tests/test_tick_sharding.py -p no:cacheprovider
71 passed in 96.12s

python3 -m pytest -q tests/test_phase043_care.py tests/test_phase037_health_routes.py \
  tests/test_phase010_burial.py tests/test_phase070b_body.py tests/test_phase038_strikes.py \
  -p no:cacheprovider
100 passed in 26.62s

python3 -m pytest -q tests/test_phase069_body.py tests/test_phase063_marks.py \
  tests/test_simple_animals.py tests/test_simple_body_food.py tests/test_phase005_heating.py \
  -p no:cacheprovider
77 passed in 14.01s

python3 domains/bigville_entities.py
ERRORS (0), WARNINGS (0), INFO (120); production graph 481 nodes / 864 edges.
```

`tests/test_state_draws.py` covers: same state/purpose/parts → same value;
actor, body and animal state changes; automatic named-entity inclusion;
explicit child/multi-party inclusion; A-then-B vs B-then-A; every birth draw;
meal illness; disease onset; burial; strike aim (including the unchanged base,
skill, brace and miss semantics); harm locus; animal sex; unchanged
probability tables; and a serial-vs-partitioned chance-heavy run.

## Serial vs partitioned

`test_serial_and_partitioned_chance_heavy_runs_match_semantically` builds a
two-resident scenario with metabolism, illness and births on, starts one tick
before a day boundary, adds a failing well and a gestating dam, then runs a
dawn tick, a period pass and another turn on both a serial and a partitioned
executor. The executor drives the dawn/turn steps; the period pass is the
world-level call that carries infrastructure and animal-life effects on both
worlds. It asserts the run exercised the failure and animal-birth draws and
that `semantic_world_state(serial) == semantic_world_state(partitioned)`.

The existing TG07 suite (`tests/test_tick_sharding.py`) also passes unchanged.

## Test updates caused by the chance source

- `tests/test_phase044_births.py::test_a_midwife_in_reach_halves_the_maternal_risk`
  now reads the maternal draw in the same state `_deliver_birth` uses
  (pregnant cleared, postpartum block set, day at term). The risk comparison
  and the midwife halving assertion are unchanged.
- `tests/test_phase037_health_routes.py::test_an_ordinary_sleep_restores_health...`
  clears the body ledger after `injure` so the test still isolates the
  health-scaled stamina capacity; the state-derived locus draw can now land on
  a back/chest/head locus that also lowers stamina through `INJURY_EFFECTS`.
  No probability or threshold was weakened.
- `tests/test_phase043_care.py` comment updated from "pure function of seed,
  name, disease, day" to include the resident's state.

No hardcoded layout/digest test changed: the Phase 004 layout digest is
unrelated to chance draws.

## Audit

`grep` over `worlds bigville domains` finds no runtime `random.Random`,
`randrange`, `randint`, `shuffle` or `sample` left in `worlds/`. Remaining
occurrences:

- `bigville/game.py` (turn order), `bigville/reporting.py` (report sample) and
  `bigville/management/cast_generation.py`: DS03 scope.
- `worlds/bigville_town100_world.py`, `worlds/bigville_social_seed.py`,
  `domains/population.py`: creation-time numpy streams, already allowlisted.
- `domains/interoception.py`: the documented presentation/creation allowlist
  above.

## Limitations / notes

- Draws now depend on the involved party's state at draw time, by design. Two
  actions that mutate that state before a later draw can legitimately change
  the later value; the invariant is same state + same turn/purpose/parts →
  same value, not "state-blind" independence.
- `actor_state` still omits inventories, relationships and cognition. When a
  draw needs one of those, it must be passed explicitly as a part.
- Cross-version determinism remains limited to a fixed Python/data-pack
  environment (JSON float formatting); the plan excludes cross-numpy creation
  stream equivalence.
- The `STRIKE_AIM` table's `_doc` was updated in both packs, but no probability
  value changed.

## Handoff to DS03

- Replace `random.Random` in `bigville/game.py::turn_order` with
  `determinism.shuffle`, and the reporting sample with `determinism.sample`.
- Audit/allowlist the creation-time numpy streams and cast generation.
- Add the source-audit test, including `domains/interoception.draw`'s
  presentation allowlist and the retired `pick_locus`.
- The state-derived draws add one BLAKE2b hash per draw; DS04 should measure
  the per-turn cost on the chance-heavy seed matrix.
