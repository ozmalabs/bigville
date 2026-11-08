# DS03 — Turn order, reporting, generation audit and source audit

Status: implemented, uncommitted (review/commit by the supervisor).
Base commit: `f34a7dc` (`DS02: state-derived runtime chance draws`).
Worktree: `deterministic-seeds`.

## Delivered

- `bigville/game.py`: `turn_order` now uses
  `determinism.shuffle(sorted(actors), map_seed, "turn_order", turn)`; the
  stdlib `random` import and `random.Random(f"{seed}:{turn}")` are gone.
- `bigville/reporting.py`: `SimulationReporter._sample` now uses
  `determinism.sample(rows, size, seed, "report_sample")`; the stdlib `random`
  import is gone. The sample schema, finite-population correction and estimate
  math are unchanged.
- `bigville/management/cast_generation.py`: generated traits now come from
  `determinism.uniform(_generated_seed(...), "cast_trait")` instead of
  `random.Random(...).uniform(min, max)`. The generator version, scenario hash,
  group id, ordinal, trait name and `_generated_seed` inputs are unchanged; only
  the RNG source changed.
- `domains/autopilot.py`: `habit_roll` now uses
  `determinism.uniform(0, "autopilot-habit", *parts)`; the local `hashlib`
  draw is gone. It remains a deterministic decision gate for consults and
  consumes no shared RNG.
- `tests/test_random_audit.py` (new): the production source audit plus
  reporting-sample and habit-roll stability tests.
- `docs/design/DETERMINISTIC_SEEDS.md`: DS03 status row only.

## Turn order contract

`BigvilleGame.turn_order` keeps the Phase 025 contract:

- the same map seed and turn give the same permutation on replay;
- the input list is sorted first, so backend registration order does not
  matter;
- the permutation changes between turns with high probability;
- the draw uses the map node's `seed` only, so it holds no world RNG state and
  checkpoints need nothing new;
- the helper returns a new list and does not mutate its input.

The exact permutation for a seed/turn changes because the chance source changed
from Mersenne Twister to the BLAKE2b helper. No test pinned a literal
permutation; the existing determinism, permutation, seed-dependence,
input-order and fairness tests pass unchanged.

## Reporting sample

`_sample` selects rows with the helper and keeps the original frame size,
sample size, seed field, finite-population factor, proportion/mean standard
errors and class/role shares. Rows are already built in sorted actor order by
`_actor_rows`, so the helper sees a stable sequence. No exact sample fixture
existed to update.

## Cast generation

The previous generator was:

```python
generator = random.Random(_generated_seed(seed, scenario_hash, group["id"], ordinal, trait))
actor[trait] = round(generator.uniform(bounds["min"], bounds["max"]), 6)
```

The replacement keeps the same generated seed and the same linear uniform
mapping:

```python
drawn = determinism.uniform(
    _generated_seed(seed, scenario_hash, group["id"], ordinal, trait), "cast_trait")
actor[trait] = round(bounds["min"] + (bounds["max"] - bounds["min"]) * drawn, 6)
```

The generator hash/version/inputs and the generated actor home allocation are
unchanged. Trait values for an existing configuration change because the RNG
source changed, which is the intended DS03 migration; no test asserted literal
trait values. Determinism for a `(seed, scenario_hash, group, ordinal, trait)`
input remains.

## Autopilot habit roll

`habit_roll` was already a deterministic SHA-256 helper, but the plan asks for
one central source. It now delegates to `determinism.uniform` with a fixed
autopilot domain:

```python
return determinism.uniform(0, "autopilot-habit", *parts)
```

This is consult gating, not a world outcome, and it still uses no shared or
module RNG. The exact roll values change; the existing consult-pattern tests
assert ranges, stability and the relative low/high-habit counts, not literal
rolls, and pass unchanged.

## Creation-time allowlist

These sites are deterministic creation-time generation and are allowlisted in
`tests/test_random_audit.py`. Each derives from an explicit run/map seed; none
uses wall time, UUID, `id()` or an unseeded stream.

| Site | Source | Rationale |
|---|---|---|
| `worlds/bigville_town100_world.py` | `np.random.default_rng(seed)`, `seed+7`, `seed+13` | town cast, names and trait streams |
| `worlds/bigville_social_seed.py` | `np.random.default_rng(seed+31/+37/+41)` | self priors, partner count/selection, relationship kind |
| `domains/population.py` | `np.random.default_rng(seed + stream)` | founding ages, households, kinship and history |
| `domains/knowledge.py` | `np.random.default_rng(seed * 1_000_003 ^ crc32(name))` | per-record knowledge/talent draws |
| `domains/relationship_seeding.py` | `np.random.default_rng(seed + cfg["stream"])` | founding relationship ties |
| `worlds/bigville_world.py` | `np.random.default_rng(seed + KINSHIP_STREAM)`, `(seed * 1_000_003) ^ crc32(actor)` | founding kinship and `draw_capacities`; the `hash()` uses are TypeError probes in the position/location bucket indexes, not seed inputs |
| `domains/interoception.py` | local SHA-256 `draw` | presentation/creation draw only: body acuity, sound form, felt-signal jitter; no physical outcome |
| `bigville/llm_log.py` | `time.strftime` + `uuid.uuid4` | log filename only (`new_run_id`), never a simulation outcome |

The allowlist is per file and per rule, not per directory: a new
`random.Random` in an allowlisted file still fails. `domains/determinism.py`
alone may use `id()` for reference-cycle detection in canonicalisation.

## Source audit

`tests/test_random_audit.py` scans production Python under `bigville/`,
`worlds/` and `domains/`, excluding `tests/`, `tools/` and
`bigville/game/assets/`.

Matcher behaviour:

- comments and string literals are blanked with `tokenize` first, so prose or
  docstrings that mention `hash()`, `random.Random` or `uuid.uuid4` do not
  fail; line numbers stay stable;
- hard rules: `_rng*` state, stdlib `random` imports, `random.*` calls,
  `np.random`/`numpy.random`, generator-variable methods, bare `.random(`,
  bare `randrange`/`randint`, bare `shuffle`/`sample`, builtin `hash(` and
  `id(`;
- wall-clock and UUID rules fire only on a line that also names a stochastic
  seed path (`seed`, `rng`, `random`, `draw`, `roll`, `jitter`, `chance`, ...),
  so ordinary infrastructure timing/log ids are not false positives;
- the finding names `path:line: rule: source`, and the test fails with a
  migration/allowlist instruction.

Production scan result on the current tree: **0 findings**. The only remaining
`_rng` text is the legacy `_rng_state` compatibility comment/string in
`bigville/world_persistence.py`; the writer emits no RNG state and the tokenizer
blanks that prose, so it is not a code site. A real attribute assignment or read
would be flagged.

## Tests and exact results

```text
python3 -m pytest -q tests/test_random_audit.py \
  tests/test_phase025_turn_order.py tests/test_bigville_reporting.py -p no:cacheprovider
22 passed in 67.43s

python3 -m pytest -q tests/management/ \
  --ignore=tests/management/test_cast_browser.py -p no:cacheprovider
164 passed in 77.94s

python3 -m pytest -q tests/test_determinism.py tests/test_state_draws.py \
  tests/test_phase059_autopilot.py -p no:cacheprovider
77 passed in 14.39s

python3 domains/bigville_entities.py
ERRORS (0), WARNINGS (0), INFO (120); production graph 481 nodes / 864 edges.
```

The requested combined management command was also run:

```text
python3 -m pytest -q tests/test_random_audit.py tests/test_phase025_turn_order.py \
  tests/test_bigville_reporting.py tests/management/ -p no:cacheprovider
186 passed, 1 failed in 150.40s
```

The one failure is
`tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world`,
which compares a live simulation position with the preview's initial position
after an asynchronous run has already started. It is a pre-existing timing
flake, not a DS03 regression: on the unmodified DS02 base commit (`f34a7dc`)
the same browser test failed 3 of 5 solo runs with the same live-position
mismatch, and the base batch run failed a different Playwright test
(`test_reports_browser`). The non-browser management suite passes cleanly
(164/164) and the cast-browser test passes on some runs; no test assertion was
weakened or changed.

The audit matcher is tested directly with synthetic source for every rule
class, including a synthetic `random.Random`/`_rng` violation, a numpy/bare
shuffle violation, a per-file allowlist miss (`random.Random` in the town
file), builtin `hash`/`id`, seed-path-only clock/UUID rejection and
code-vs-docstring handling. It never writes a temporary file into the repo.

## Limitations / notes

- Turn-order permutations, report samples, generated trait values and habit
  rolls change when compared with DS02 because only the chance source changed.
  There were no literal fixtures for those values; the contracts and probability
  tables are unchanged.
- Creation-time `numpy` streams remain deterministic for a fixed Python/numpy
  environment and seed; cross-numpy-version equivalence is explicitly out of
  scope.
- The audit is lexical after masking comments/strings, not a full data-flow
  analysis. An RNG reached through an unusual alias or `getattr` could evade
  it; the common reintroduction paths (direct module calls, local generator
  variables, `_rng` state) are covered.
- The Playwright browser tests are flaky in this environment under batch load;
  see the exact base-commit evidence above.

## Handoff to DS04

- Run the deterministic-shard matrix with the new turn order and reporting
  sample; the helper values are stable across serial, threaded, partitioned
  and process runs for the same seed/turn/state.
- Measure the per-draw/per-turn cost of the BLAKE2b helper, including the new
  turn-order shuffle and cast/report paths.
- Keep `tests/test_random_audit.py` in the integration gate so a new shared RNG
  or process-salted seed fails with file/line.
- Decide whether `domains/interoception.pick_locus` (unused by host code after
  DS02) is retired or moved to `domains.determinism`; it is still allowlisted as
  a presentation/creation draw.
