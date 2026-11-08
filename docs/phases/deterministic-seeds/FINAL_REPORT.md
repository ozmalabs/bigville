# Deterministic chance — final report (DS01-DS04)

Status: complete, 8 November 2026
review/commit. Dates: 7-8 November 2026.

## The rule

> Given the same world seed, turn/period and involved-entity state, a
> stochastic outcome is the same value regardless of executor, shard, action
> order or process.

The single source is `domains/determinism.py`:

- `canonical_bytes(*parts)` canonicalises primitives, mappings, sequences and
  sets (sorted keys/members, tuple/list equivalence, `NodeRef` as an int,
  non-finite floats rejected);
- `derive_seed(world_seed, *parts)` is BLAKE2b-128 over a fixed domain and the
  canonical bytes; `uniform` maps it to `[0, 1)`;
- `choice`, `shuffle` and `sample` are deterministic equivalents that do not
  mutate their input;
- `world_seed(world)` reads the map/body seed, never process identity;
- `actor_state`/`animal_state`/`entity_state` give a canonical stable snapshot;
- `state_seed`/`state_uniform` include the world seed, purpose, parts and the
  canonical state of every named resident/animal automatically.

## Phases

| Phase | Commit | Delivered |
|---|---|---|
| DS01 | `6a3768c` | Helper; weather and infrastructure draws moved off `world._rng`; runtime RNG removed from persistence; legacy `_rng_state` ignored on load; audit/test support. |
| DS02 | `f34a7dc` | Every runtime stateless draw migrated to `state_uniform`/`state_seed` with involved party state: illness, meal, burial, birth conception/name/stillbirth/sex/infant/maternal, strike aim, harm locus, animal birth sex. |
| DS03 | `4c82dfe` | `turn_order` uses `determinism.shuffle`; reporting sample uses `determinism.sample`; cast generation uses `determinism.uniform`; autopilot habit roll centralised; creation-time numpy streams allowlisted; production source-audit matcher. |
| DS04 | `7b31559` | Interoception runtime seed made state-derived; full serial/partitioned/replay/reorder/restore verification tool; shard determinism tests; overhead and final docs. |

## What is deterministic now

For a fixed environment (Python and data pack) and the same seed/state:

- **Executor-independent outcomes.** Serial, threaded and partitioned commits
  produce the same semantic world state and revisions. DS04 checks serial vs
  partitioned and two partitioned replays for seeds 305000, 305002, 305004
  and 305006 over 8 turns: semantic state, `tick_payload_sha`,
  `tick_execution_sha`, committed order and `run_execution_sha` all match.
- **Order-independent draws.** A-then-B and B-then-A give each actor the same
  value. DS04 evaluates weather, infrastructure, birth, illness, meal and
  strike draws in a fixed ascending order and the fixed reverse order; every
  per-key outcome matches.
- **Checkpoint continuity.** Restoring at a turn and continuing gives the same
  remaining semantic state and revisions as an uninterrupted run. No hidden
  RNG state is needed; new checkpoints write none. DS04 checks this for every
  seed (turn 4 + 4) and in the test suite at turn 3 + 2.
- **Turn order and reporting.** `turn_order` is a seeded shuffle of the sorted
  actor list; the report sample is a seeded `sample`; both depend only on the
  map seed, turn/purpose and the sorted input.
- **Interoception presentation.** A world-backed body's jitter and sound-form
  draw now use a state-derived runtime seed
  (`state_seed(world, "interoception", actor, turn)`); the draw itself is still
  a stateless SHA-256 hash. Creation-time acuity keeps the fixed body seed.
- **No shared RNG.** No production runtime module consumes a shared/module
  RNG. `tests/test_random_audit.py` reports 0 findings over `bigville/`,
  `worlds/` and `domains/`, and no world has `_rng` or persisted RNG state.

## Creation-time allowlist

These are deterministic generation streams, not runtime outcomes. Each derives
from an explicit run/map/configuration seed; none uses wall time, UUID,
`id()` or an unseeded stream. They are allowlisted per file and per rule in
`tests/test_random_audit.py`.

| Site | Source | Rationale |
|---|---|---|
| `worlds/bigville_town100_world.py` | `np.random.default_rng(seed)`, `seed+7`, `seed+13` | founding town cast, names, traits |
| `worlds/bigville_social_seed.py` | `np.random.default_rng(seed+31/+37/+41)` | self priors, partner count/selection, relationship kind |
| `domains/population.py` | `np.random.default_rng(seed + stream)` | founding ages, households, kinship, history |
| `domains/knowledge.py` | `np.random.default_rng(seed * 1_000_003 ^ crc32(name))` | per-record knowledge/talent draws |
| `domains/relationship_seeding.py` | `np.random.default_rng(seed + cfg["stream"])` | founding relationship ties |
| `worlds/bigville_world.py` | `np.random.default_rng(seed + KINSHIP_STREAM)`, `(seed * 1_000_003) ^ crc32(actor)` | founding kinship and capacity draws; the `hash()` uses are TypeError probes in bucket indexes, not seed inputs |
| `domains/interoception.py` | local SHA-256 `draw` | presentation/creation only (acuity, sound form, per-tick jitter); its runtime seed is state-derived |
| `bigville/llm_log.py` | `time.strftime` + `uuid.uuid4` | log filename only (`new_run_id`), never a simulation outcome |

## Verification results

Default DS04 tool run:

```text
python3 tools/verify_deterministic_chance.py \
  --seeds 305000,305002,305004,305006 --turns 8 --json
exit 0, ok true, 125.3 s, source audit 0 findings
4/4 seeds: semantic/payload/revision equality, stable replay execution,
reorder pass, checkpoint/restore pass, no _rng
```

The chance-heavy setup reports the expected exercise: weather changed at dawn,
the injected well failed (condition 0.75), the gestating dam gave birth, and
the `_stable_draw` counter recorded birth, illness and meal draws. See
[`DS04_REPORT.md`](DS04_REPORT.md) for the per-seed matrix and exact counts.

Targeted tests:

```text
tests/test_deterministic_shards.py tests/test_random_audit.py
tests/test_determinism.py tests/test_state_draws.py
tests/test_phase069_body.py tests/test_phase070_locus.py
114 passed in 34.46s

tests/test_tick_sharding.py tests/test_bundle_dispatch.py
tests/test_engine_defaults.py tests/test_lazy_*.py
3 failed, 158 passed, 1 skipped in 104.43s

python3 domains/bigville_entities.py
ERRORS (0), WARNINGS (0), INFO (120); graph 481 nodes / 864 edges.
```

The three failures are the menu-mode trace-digest tests in
`tests/test_lazy_cheap.py`, `tests/test_lazy_observation.py` and
`tests/test_lazy_target_resolution.py`. They are pre-existing at DS03 base
`4c82dfe` (the same three fail there with the same actual digest); they pin an
LA01-era digest and are outside this program's scope. No assertion was
weakened.

**Full-suite status:** a complete `tests/` run was not executed for this
report, so no full-suite pass is claimed. The commands above are the exact
targeted suites and self-test that were run; an active/concurrent full suite
was not relied on as evidence.

## Performance

On the development host under load 5.26, the profile harness (2 turns,
its own lazy/every-turn/action defaults) measured:

| Executor | 50 residents | 100 residents |
|---|---|---|
| serial | 178.25 ms/turn | 507.25 ms/turn |
| partitioned | 945.60 ms/turn | 3,075.86 ms/turn |

A leaner headless town100 run (lazy, on-demand snapshot, turn batching) was
244.7 ms/turn with 17.4 `_stable_draw` calls/turn. One state-derived draw is
about 466-469 µs on this host versus about 6.3 µs for a plain world-seed
uniform, so state hashing is roughly 8 ms/turn, about 3% of that lean turn; it
is a smaller share in the profile figures. This is an absolute measurement,
not a controlled pre-DS benchmark, and no speedup is claimed. Interoception
derivation is not called in headless runs (0 calls/turn), so the runtime seed
change has no measurable headless cost.

## Remaining risks and limits

- **Cross-version numpy.** Creation-time streams are deterministic for a fixed
  Python/numpy environment and seed. numpy's distribution algorithms may
  change between releases; cross-numpy-version equivalence is explicitly out
  of scope. Runtime draws use only the standard-library BLAKE2b/JSON path, so
  they are not affected by numpy version.
- **Canonical JSON float formatting.** Runtime seed equivalence assumes the
  same Python/data-pack JSON float formatting. Cross-Python-version
  equivalence is not separately guaranteed or tested.
- **External providers.** LLM/Ocelot cognition and any external provider are
  outside the rule. Their decisions are inputs, not seeded world outcomes; a
  replay with a non-deterministic provider can diverge even though every
  world-chance draw is deterministic.
- **Wall-clock/run ids.** `bigville/llm_log.py::new_run_id` uses wall time and
  `uuid.uuid4` for log filenames only. It must never feed a simulation
  outcome; the source audit's seed-path rule guards the common cases but is a
  lexical matcher, not data-flow analysis.
- **Audit reach.** The DS03/DS04 source audit masks comments/strings and
  covers direct module calls, local generator variables, `_rng` state, builtin
  `hash`/`id` and seed-path clock/UUID. An unusual alias or `getattr` could
  still evade it.
- **State included in draws.** `actor_state` covers attrs, body attrs,
  alive/position but not inventories, relationships or cognition. A draw that
  needs those must pass them explicitly; the rule is same state + same
  purpose/turn/parts → same value, not state-blind independence.
- **Ordering scope.** The DS04 reorder check exercises the exact draw calls,
  not a physically reshuffled actor registration in a full scenario. The
  serial/partitioned end-to-end comparison covers executor ordering.
- **Performance under load.** Measurements were taken under a non-idle host;
  absolute ms/turn is indicative, and the hashing share should be re-measured
  if it becomes a performance concern.
- **Pre-existing lazy digest tests.** Three menu-mode trace-digest tests fail
  at the DS03 base and remain failing; they are not caused by this program and
  were not edited.
