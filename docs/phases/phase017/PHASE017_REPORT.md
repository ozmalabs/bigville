# Phase 017: generated Ocelot seeds

## Summary

`tools/generate_seeds.py` writes Ocelot seed JSON from the bigville pack. It produces 21 files
(`gen_*.json`) for laws, policies, charters, offices, procedures, skills and clusters, metaskills,
trades and jobs, kin terms, recipes (as know-how), and shared concepts. The generator also replaces
one hand-written seed, `bigville_terrain_movement.json`, in place under the same id, because its whole
content was pack data. All generated files go to `bigville/seeds/`, the one canonical directory.

A staleness check runs in the self-test and in the tests. The self-test is 0 errors and 0 warnings,
and the hamlet check is 0 and 0. The 13 new tests pass. The full suite has 469 passing and 3 failing;
the 3 failures are the other session's Ocelot tests. Nothing was committed.

Decisions for the supervisor: `bigville_actor_decision.json` (not touched; see Reconciliation) and the
per-resident knowledge seeds that the Phase 019 follow-up asked for (not generated; see Open questions).

## Changes

New files:
- `domains/generated_seeds.py`: `plan`, `expected_files`, `render`, `write_seeds`, `check_seeds`. The
  logic lives under `domains/` so the self-test can call it without importing `tools/`.
- `tools/generate_seeds.py`: CLI. `--pack NAME_OR_DIR`, `--out DIR`, `--check`. A pack other than
  `bigville` needs `--out`.
- `tests/test_phase017_generated_seeds.py`: 13 tests (listed under Validation).
- `bigville/seeds/gen_*.json`: 21 generated files (list below).
- `bigville/seeds/bigville_dispositions_cast100.json`: copy of the root `seeds/` file (reconciliation).
- `docs/phases/phase017/`: this report and its logs.

Modified files (all hunks are mine):
- `domains/bigville_entities.py`: module imports (`_PACK as _WORLD_PACK`, `generated_seeds`); new function
  `_check_generated_seeds(errors)`; one new call, `_check_generated_seeds(errors)`, in `check_consistency`.
- `bigville/seeds/bigville_terrain_movement.json`: replaced in place (same id). See Replaced ids.
- `bigville/seeds/bigville_action_decide.json`: now byte-identical to the root `seeds/` copy (reconciliation).

Not touched: `bigville/seeds/bigville_actor_decision.json`, `seeds/bigville_actor_decision.json`, the
world, `game.py`, `runtime.py`, every existing test, and the other session's files.

## Generated seeds and schema mapping

Each file has the keys the Ocelot seed loader reads: `id`, `version` ("1.0.0"), `description`,
`depends_on` ([]), `nodes` ([]), `edges` ([]), `concepts`, `rules`. Each also has `self_load_only: true`
(as the Bigville resident seeds do) and a `generated_from` header:

```json
"generated_from": {"pack": "bigville", "generator": "tools/generate_seeds.py", "format": 1,
                   "tables": ["LAWS"], "record": "commons_and_land_law", "sha256": "..."}
```

Mapping:
- `concepts` entries are `{name, definition, category}`. Laws, policies, and charters use the pack's own
  concept list; `definition` is `subject predicate object` and `category` is the pack's `abstraction`.
  Offices, skills, clusters, metaskills, trades, jobs, and kin terms each get one concept. Its
  definition is the record's fields as `key: value` text, in key order.
- `rules` entries are declarative principles `{name, head, body}`. The Ocelot loader folds these into
  Principle nodes. A law, policy, or charter gets one identity principle (title, then kind, scope, origin,
  enforcement). A recipe gets one know-how principle (head: "X makes Y x N from a T"; body: its other
  fields).
- `knowledge` specs (Phase 019) are not carried. They describe who knows what, which is derived state,
  not seed content.

| File | Source table(s) | Records | Concepts | Principles |
|---|---|---|---|---|
| `gen_law_commons_and_land_law`, `gen_law_giantville_murder_law`, `gen_law_giantville_theft_law`, `gen_law_public_order_law` | LAWS | 1 each | 3 each | 1 each |
| `gen_policy_giantville_public_health_baseline`, `gen_policy_water_safety_policy`, `gen_policy_winter_food_reserve` | POLICIES | 1 each | 3 each | 1 each |
| `gen_charter_bigville_council_charter` | CHARTERS | 1 | 6 | 1 |
| `gen_office_clerk`, `_constable`, `_councillor`, `_doctor`, `_mayor`, `_midwife` | GOVERNANCE_OFFICES | 1 each | 1 each | 0 |
| `gen_procedure_lawmaking`, `gen_procedure_justice` | LAWMAKING / JUSTICE_PROCEDURES | 1 file each | 6 each (one per stage) | 0 |
| `gen_skills` | SKILLS, SKILL_CLUSTERS, METASKILLS | 46 + 14 + 7 | 67 | 0 |
| `gen_trades` | TRADES, JOBS | 51 + 28 | 79 | 0 |
| `gen_kinship` | KIN_TERMS | 20 | 20 | 0 |
| `gen_recipes` | RECIPES | 163 | 0 | 163 |
| `gen_shared_concepts` | SHARED_CONCEPTS | 25 | 25 | 0 |
| `bigville_terrain_movement` (replaces hand-written) | TERRAIN_MOVEMENT | 1 | 0 | 0 |

Totals: 236 concepts and 171 principles in the 21 `gen_*` files. The 22 files total 96,732 bytes.

Jobs are in `gen_trades`. The brief names "skills and trades" and `shared_frames.py` groups jobs with
trades. The bigville pack has no fiscal table, so no fiscal seed is generated. A search of `packs/` and
`domains/` for fiscal, tax, treasur, tithe, and mortgage found nothing.

Generated concept names use these prefixes: `skill_`, `skill_cluster_`, `metaskill_`, `trade_`, `job_`,
`kin_`, `office_`, `lawmaking_`, `justice_`. Laws, policies, charters, and shared concepts keep the
pack's own names. `plan` raises if two generated seeds produce the same name. A test also checks
generated names against every concept name in the hand-written seeds of both directories (none overlap).

## Canonical directory: `bigville/seeds/`

Reasons:
1. The real Ocelot adapter loads Bigville seeds from `bigville/seeds/`. `worlds/bigville_ocelot_adapter.py`
   `_bigville_seed` (lines 123-137) reads `<BIGVILLE_ROOT or sys.path entry>/bigville/seeds/<name>.json`.
   It does not read the root `seeds/`.
2. `pyproject.toml` ships `bigville/seeds/*.json` as package data. The root `seeds/` is not shipped.
3. `bigville/seeds/` holds every id in ENGINE_SEEDS, RESIDENT_SEEDS, and RESIDENT_CONCEPT_SEEDS.
   `bigville_terrain_movement` exists only there.

Correction to the brief: the Ocelot checkout's `seeds/` holds three Bigville files
(`bigville_can_beliefs`, `bigville_cast100`, `bigville_dispositions_cast100`), not a copy of the
Bigville directory.

The root `seeds/` directory stays in place. Its code readers and writers are listed under Open questions.

## Reconciliation of `seeds/` and `bigville/seeds/`

Before this phase the two directories had 184 files each. They differed in four ways.

| Seed | Before | Decision | Applied |
|---|---|---|---|
| `bigville_action_decide` | Identical rules. Only `description` differs. Root (commit 58d15c1, 2026-11-05): "Retired legacy ... The world no longer loads these rules". Canonical (last changed 4cf070a, 2026-08-14): "R77 ... port". Nothing loads either. | Root wins. It is the later edit and matches the code. | Copied root bytes to `bigville/seeds/`. Both copies are now identical. |
| `bigville_dispositions_cast100` | Root only. Written by `worlds/bigville_social_seed.py` into root `seeds/`. No reader in this repo. Ocelot's `seeds/` has the same bytes. | Canonical holds every hand-written seed. | Copied into `bigville/seeds/`. The writer still targets root (Open questions). |
| `bigville_terrain_movement` | Canonical only. Listed in ENGINE_SEEDS. Its content is pack data (see Replaced ids). | Replace in place with the generated file, same id. | Regenerated. Root gets no copy: nothing reads the root copy. |
| `bigville_actor_decision` | Differs (below). Owned by the other session. | Not decided here. | Nothing. |

### `bigville_actor_decision`: recommendation

There are three versions:
- HEAD `bigville/seeds/` copy: version 1.0.0, one rule (`oa_choose_option`).
- Root `seeds/` copy: version 1.1.0 (commit a7da178, 2026-11-05), one rule. Its `oa_choose_option` body has a
  nested -6.0 term that HEAD's copy lacks.
- Working-tree `bigville/seeds/` copy: version 1.3.0, uncommitted (other session). It adds
  `o0_score_hungry_eat` and `o1_score_hungry_food_fetch`. Its `oa_choose_option` matches neither of the
  other two.

Recommendation: after the other session commits its 1.3.0 work, keep `bigville/seeds/bigville_actor_decision.json`
as the one copy. Reasons: the Ocelot adapter loads only that path for RESIDENT_SEEDS, and it holds the newest
work. Before deleting the root copy, check whether the root `oa_choose_option` term (-6.0) is behaviour that
1.3.0 dropped. If it is, port it first. Deleting the root copy would also change two skip gates:
`tests/test_mixed_ocelot_village.py:17` and `tests/test_mixed_ocelot_checkpoint_parity.py:81` skip when root
`seeds/bigville_actor_decision.json` is missing. They would then skip instead of run. The docstring at
`worlds/bigville_world.py:124` also names the root path.

## Replaced hand-written ids

- `bigville_terrain_movement` (`bigville/seeds/`).
  - Before: a `terrain` table equal to the pack's `TERRAIN_MOVEMENT`, two concepts equal to two entries of
    `SHARED_CONCEPTS`, a `seed_roles` key on each concept (a key Phase 019 removed from the pack), and no nodes
    or rules.
  - After: same id and `version`. The `terrain` table is generated from the pack. `concepts` is empty, because
    the two concepts are in `gen_shared_concepts`. Header added.
  - Readers checked: ENGINE_SEEDS lists the id; the self-test's file check uses the id;
    `tests/test_bigville_world_migrated.py:1305` checks the id is in `seed_manifests`, and the runtime records
    ids only; `tests/test_phase014_parameters.py:87` checks the list. The world's
    `terrain_movement_rules()` reads `E.TERRAIN_MOVEMENT`, not the seed. No reader breaks.
  - The old text is in git (HEAD). Its two concepts also caused a name collision with `gen_shared_concepts`.
    The replacement removes that collision.

Not replaced, on purpose:
- Hand-written seeds with executable `match` rules keep them. Examples: `bigville_trades` (2 rules),
  `bigville_office` (13). Replacing them would drop rules that Ocelot runs.
- `bigville_cast100` and `bigville_dispositions_cast100` have no executable rules. The town builder and the
  social seed writer produce them from draws, not from pack tables, so they are not pack data in the sense of
  this phase.
- `bigville_townspeople_30` and `bigville_townspeople_50` are hand-authored registers and relationships. The
  pack does not hold them.

## Staleness check

`domains/generated_seeds.py`:
- `check_seeds(pack, dir)` regenerates every expected file in memory and reports:
  - `missing`: an expected file is absent.
  - `stale`: the file's bytes differ from the regenerated bytes. This catches a pack edit that was not
    regenerated, and a hand edit of a seed.
  - `orphaned`: a file with this pack's header that the pack no longer produces.
  - `in the way`: a hand-written file where a generated file belongs (ids in `REPLACED_HAND_WRITTEN` excepted).
- `write_seeds(pack, dir)` writes the expected files, removes this pack's orphans, and refuses to overwrite a
  hand-written seed.
- The `generated_from.sha256` value is the SHA-256 of `domains.pack.canonical` over the source rows: the record
  for a per-record file, or `{table: value}` for a table file. Editing one law changes that law's file and no
  other.

Enforcement:
- Self-test: `check_consistency` calls `_check_generated_seeds`. Problems appear as errors named
  `generated seeds: <file>: ...`. The check runs for the `bigville` pack only; child and hamlet packs skip it.
- CLI: `python3 tools/generate_seeds.py --check` exits 1 on any problem.
- Tests: the staleness tests in `tests/test_phase017_generated_seeds.py`.

## Validation

| Check | Command | Result |
|---|---|---|
| Self-test | `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0). `selftest_final.txt` |
| Hamlet check | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0), WARNINGS (0). `hamlet_check.txt` |
| Staleness CLI | `python3 tools/generate_seeds.py --check` | exit 0; 22 files match the pack |
| Regeneration | `python3 tools/generate_seeds.py --pack bigville --out /tmp/x` twice, compared to the committed files | byte-identical; test `test_regenerating_is_byte_identical` also passes |
| Ocelot loader (not in the test suite) | Ran `normalize_declarative` from `/home/matt/ozmadev/ocelot/substrate/seed_loader.py` on the 22 files. Its Rust-backed imports were stubbed, and no bytecode was written into the Ocelot checkout. | All 22 normalise. 236 Concept nodes and 171 Principle nodes, equal to each file's `concepts` and `rules` counts. This is a schema check only; no agent was booted. |
| New tests | `python3 -m pytest -q -p no:cacheprovider tests/test_phase017_generated_seeds.py` | 13 passed |
| Full suite | `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 3 failed, 469 passed, 2 skipped. `pytest_full.txt` |
| Full suite, other session's Ocelot files ignored | same, with `--ignore` on `tests/test_bigville_ocelot_communication.py`, `tests/test_mixed_ocelot_checkpoint_parity.py`, `tests/test_mixed_ocelot_village.py` | 469 passed, 2 skipped. `pytest_ignoring_other_session_ocelot.txt` |

The 13 tests:
- Regeneration is byte-identical.
- The committed files equal the pack's output.
- Editing one law in a child pack (extends bigville) changes only that law's file.
- The staleness check catches an unregenerated pack edit and a hand edit, and the self-test reports a stale file in the canonical directory.
- Every generated seed parses and has the header, and its concepts and rules have the Ocelot shape.
- Every id in ENGINE_SEEDS, RESIDENT_SEEDS, and RESIDENT_CONCEPT_SEEDS exists in `bigville/seeds/` or the root `seeds/`.
- The two directories agree, except for the pending actor-decision file.
- The terrain replacement keeps its id and table.
- Generated concept names do not collide with hand-written concept names.
- The hamlet pack generates into a temp directory.
- A policy removed from a child pack is removed from the output.
- A hand-written seed is never overwritten.
- The CLI checks the canonical directory and requires `--out` for other packs.

Failures in the full suite, verbatim. The other session owns these files:

```
FAILED tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities
FAILED tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control
FAILED tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action
E   bigville.backends.ocelot.OcelotUnavailableError: Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter and its dependencies on PYTHONPATH; select 'simple' for local NPCs. Adapter import failed (ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter')
```

The other two failures report `E   ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.

Test counts: 13 new tests. No existing test was edited, and no existing numbers changed. The Phase 019 baseline
was 456 passed and 3 failed; 456 + 13 = 469.

Git status, start: 10 modified and 15 untracked files, all the other session's (README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py,
and the untracked persistence, Ocelot, and mixed-run files). Git status, end: `git_status_end.txt`. My changes are
`domains/bigville_entities.py`, `bigville/seeds/bigville_action_decide.json`, `bigville/seeds/bigville_terrain_movement.json`,
and the new files listed under Changes.

## Limits

- Nothing in this repo reads generated seeds. `manifest_for` and `load_seed_manifest` (`bigville/runtime.py`)
  record ids only, so the output has no runtime effect here.
- The Ocelot normaliser check used stubs for three modules and ran no agent. The Rust loader
  (`load_seed_manifest`) was not exercised.
- Definitions are generated text from record fields (`key: value`), not authored prose.
- The `knowledge` specs, and the Phase 019 awareness and understanding data, are not in any seed.

## Open questions

1. **Actor decision.** Which copy wins (recommendation above). The supervisor applies it after the other session
   commits its 1.3.0 work.
2. **Per-resident knowledge seeds (Phase 019 follow-up).** The Phase 019 report asked for each resident's
   knowledge seed (about 295 records each, 29,455 in total, about 119 KB per founder), and suggested sending only
   awareness or understanding. This phase generates pack-level seeds only, because the brief is pack-level. Decide
   whether to generate per-resident seeds, and which subset.
3. **Writers still target the root `seeds/`.** `worlds/bigville_social_seed.py:212` writes the dispositions file, and
   `worlds/bigville_town100_world.py:529` writes the cast file. Both are outside this phase's scope. Retargeting them
   to `bigville/seeds/` means updating `tests/test_phase016b_founding_cast.py:213` and
   `tests/test_phase019_knowledge.py:331`, which compare both directories.
4. **Root `seeds/` readers, for any later removal:** `worlds/bigville_world.py` (~1937, reads
   `bigville_townspeople_50.json`), `worlds/bigville_social_seed.py`, `worlds/bigville_town100_world.py`,
   `tests/test_bigville_speech_migrated.py:254` (reads `bigville_speech_decide.json`),
   `tests/test_phase016b_founding_cast.py`, `tests/test_phase019_knowledge.py`, and the actor-decision skip gates
   named above. The brief forbids deleting either directory in this phase.
5. **Should generated ids join RESIDENT_CONCEPT_SEEDS or RESIDENT_SEEDS?** Not until a resident's loader loads them.
   I left the three lists unchanged.

## Deviations

- The brief has no explicit write scope. The generator logic is in `domains/` so the self-test can import it. The
  self-test hook is three hunks in `domains/bigville_entities.py`.
- The brief says the Ocelot checkout keeps its own `seeds/` copies. Only three Bigville files exist there (see
  Canonical directory).
- Jobs are generated with trades (not named in the brief). Fiscal institutions are not generated (none in the pack).
- `bigville_terrain_movement` is a replacement the brief allows ("replace in place, same id"), so it is listed under
  Replaced ids.
- Generated seeds are per record for laws, policies, charters, and offices, and per table for the rest. The brief's
  acceptance is per law, so the other tables are grouped.
