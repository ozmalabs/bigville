# Phase 046: detraining and ageing of the body

Base: HEAD `38bc602` (Phase 045 committed). Built and verified in a scratch tree from `git archive HEAD` plus this
phase's files and hunks. The shared checkout was not edited.

## Summary

- Two pack tables. `DETRAIN` gives the grace and the daily rate of loss for strength and stamina, with an `enabled`
  switch that is off by default. `BODY_AGE` gives the age at which the base starts to decline (30), and the decline and
  floor for each stat.
- Detraining acts only on the trained part (`str_train`, `sta_train`, Phase 032). It holds the trained part for
  `grace_days` after the last effort of that kind, then lowers it by `rate` each day, never below 0. The base is never
  touched. An effort is recorded on the body as `str_effort_day` (efforts that use strength) and `sta_effort_day` (every
  effort, since every effort uses stamina).
- Ageing acts only on the base, and only above `peak_until`. The base is the resident's own peak base times
  `max(floor, 1 - decline_per_year x years past 30)`. Phase 045 growth writes the base below age 18 and ageing writes it
  only above 30, so the two never write the same base at the same age.
- The switch is `DETRAIN.enabled` (false), not a `physical_subsystems` key. See Deviations.
- Training did not move. At HEAD, training is `BigvilleWorld._train_from_effort` in `worlds/bigville_world.py`, behind
  the `training` switch. Effective stats are `_effective_body_stat`, which reads base plus trained part times health.
  `worlds/body.py` (Phase 069) only reads these through `WorldBackedBody.capacities()`. It does not hold training.
- Switch off, the 60-turn simple-backend run matches HEAD in all 16 recorded fields except `label` and
  `elapsed_seconds`. Self-test: ERRORS 0, WARNINGS 0.
- Full suite on `tests/`: 2369 passed, 5 skipped, 1 failed. The failure is the known timing flake in
  `tests/test_phase055_concurrency.py`. It passes when run alone. No existing test was edited.

## Changes

### Created

| File | Purpose |
|---|---|
| `domains/detraining.py` | Pure arithmetic: `detrained`, `trained_share_left`, `aged_base`. |
| `domains/detraining_check.py` | Self-test checks for both tables (`check_detraining`). |
| `worlds/detraining.py` | `DetrainingMixin`: effort recording, the daily ageing and detraining step, and the per-stat rules. |
| `packs/bigville/world/detraining.json` | The `DETRAIN` and `BODY_AGE` tables, with the sources and APPROX marks in `_doc`. |
| `packs/test_hamlet/world/detraining.json` | The same file for the test pack (identical bytes). |
| `tests/test_phase046_detraining.py` | 16 focused tests (new file; no existing test changed). |
| `docs/phases/phase046/files/**` | The source copies of the files above (the builder copies them). |
| `docs/phases/phase046/hunks.json` | The 9 shared-file hunks (the single source of truth for them). |
| `docs/phases/phase046/build_clean_tree.py` | Builds a scratch tree: `git archive` of the base, `files/`, then the hunks. Each anchor must occur exactly once. |
| `docs/phases/phase046/run_all.sh` | The validation chain (builds, self-test, checks, exports, focused tests, 60-turn runs, full suite). |
| `docs/phases/phase046/logs/`, `measure/` | Logs and the two 60-turn measurement files. `logs/attempt1/` holds the first attempt's failing log and status. |

### Shared-file hunks (9, anchored on 38bc602; each anchor occurs exactly once in HEAD and in the live checkout)

| # | File | Anchor (where it goes) | Change |
|---|---|---|---|
| 0 | `packs/bigville/pack.json` | after the `DEPENDANTS` manifest entry (last entry) | adds `DETRAIN` and `BODY_AGE`, both in `world/detraining.json` |
| 1 | `packs/test_hamlet/pack.json` | same | same |
| 2 | `domains/world_affordances.py` | after `DEPENDANTS = _PACK["DEPENDANTS"]` | `DETRAIN`, `BODY_AGE` imports |
| 3 | `domains/bigville_entities.py` | after the `_check_dependants(...)` call in `check_consistency` | calls `check_detraining(_WORLD_PACK.path, ...)` |
| 4 | `worlds/bigville_world.py` | after `from worlds.dependants import DependantsMixin` | imports `DetrainingMixin` |
| 5 | `worlds/bigville_world.py` | the class line | `BigvilleWorld(BirthsMixin, DependantsMixin, DetrainingMixin, BodyMixin)` |
| 6 | `worlds/bigville_world.py` | exerted branch in `_resolve_actor_events`, after `_train_from_effort` | `self._detraining_note_effort(actor, body, event)` (no-op when off) |
| 7 | `worlds/bigville_world.py` | the dawn tick, after `self._dependants_day()` | `self._detraining_day()` (no-op when off) |
| 8 | `bigville/reporting.py` | before `def game_report(game)` | adds `body_by_age(world)`, a read-only report by decade |

Hunk 6 runs whether or not the training switch is on, so the effort day is recorded for every exerted effort. Hunk 7
runs with the other dawn-tick steps. That tick returns early when metabolism is off, so ageing and detraining also do
not run then.

### Tests

No existing test was changed. The 16 new tests are in `tests/test_phase046_detraining.py`. One assertion's bound was
wrong while writing (a trained strength of 0.3 after 20 batches; the correct figure is about 0.12), and it was fixed in
the source before the first full run. That was a test-authoring error, not a change to behaviour.

## Validation

All commands ran in `/tmp/p046` (the scratch tree built from HEAD plus this phase), except where stated. Logs are in
`docs/phases/phase046/logs/`.

| Check | Command | Result |
|---|---|---|
| Build | `python3 docs/phases/phase046/build_clean_tree.py --dest /tmp/p046` | 6 new files, 9 hunks, each anchor occurs once. |
| Anchors in the live tree (read-only) | a count of each `old` text in the shared checkout | 9 of 9 occur once (the live tree is dirty, but the anchors are intact). |
| Self-test | `python3 domains/bigville_entities.py` | exit 0; ERRORS (0); WARNINGS (0); INFO (120). |
| Pack check, bigville | `python3 -m domains.check` | exit 0; ERRORS (0); WARNINGS (0). |
| Pack check, test_hamlet | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0); WARNINGS (0). |
| Export-canonical, bigville | `tools/export_pack.py --pack bigville --out DIR`, then `diff -r DIR packs/bigville` | exit 0; no differences (all exported files identical). |
| Export-canonical, test_hamlet | same, for test_hamlet | exit 0; no differences. |
| Focused, new | `pytest tests/test_phase046_detraining.py` | 16 passed. |
| Focused, common | `pytest` on `test_phase032_training`, `044_births`, `045_dependants`, `043_care`, `069_body`, `070_locus`, `071_attend`, `test_simple_life`, `test_scenario_runner`, both `*_persistence` files | 175 passed, 1 skipped. |
| 60-turn run, HEAD | `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label head60 --turns 60 --out measure/behaviour_head60.json` in a HEAD-only tree | exit 0. |
| 60-turn run, phase | same, `--label p046_60`, in the phase tree | exit 0. |
| 60-turn comparison | a field-by-field comparison of the two JSON files | All 16 fields are equal except `label` and `elapsed_seconds` (113.9 s and 114.0 s). Same deaths (0), alive at end (100), utterances (285), and action counts. The raw files are not byte-identical, only for those two fields. |
| Full suite | `timeout 5400 python3 -m pytest -q -p no:cacheprovider tests` (nohup, one run, started 13:25, 3286 s) | **2369 passed, 1 failed, 5 skipped** (2375 collected; `logs/full_p046.log`). The one failure is `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`, the known speed flake named in the brief: sequential 13.47 s, concurrent 10.45 s, ratio 0.78 against a limit of 0.75. The same file run alone passes: 6 passed in 38.9 s. No other failure. |

Note on the full-suite target: `tests/` is the target, not the repository root. A no-path run also collects the
`docs/phases/*/files/tests/` copies. At HEAD that already fails collection with a basename clash (`test_phase044_births.py`
and `test_phase045_dependants.py`, verified in the HEAD-only tree). This phase adds a third copy,
`docs/phases/phase046/files/tests/test_phase046_detraining.py`, which would clash the same way.

### Attempt 1 (superseded)

The first run put the switch in `physical_subsystems` (`"detraining": False`). Two existing tests pin that dictionary
exactly: `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration` and
`tests/test_scenario_runner.py::test_runner_replays_identically_and_records_seed_and_causal_trace`. Both failed on the
extra key (`logs/attempt1/focused_common_p046_attempt1_FAILED.log`). The switch was moved to `DETRAIN.enabled`, and the
two tests were not edited. Attempt 1 finished its HEAD 60-turn run (13:17, `logs/attempt1/status_attempt1.txt`) and was
stopped during the phase's 60-turn run. Attempt 2 overwrote its measurement files, so the measurements reported here
are attempt 2's.

### Later edit

After the full suite started, one comment string in `packs/*/world/detraining.json` (`_doc`) was corrected: strength's
half-life, 35 days became 34 (ln 2 / −ln 0.98 = 34.3). No code or table value changed. The corrected build was
re-verified with the self-test, both pack checks, the export comparison and the 16 new tests. The full suite ran on the
build before this edit. The edit changes no value that code reads.

`logs/status.txt` has one mis-recorded line: `full p046 exit 0`. It came from a manual launch that read `$?` after `date`
ran. pytest's own summary (`logs/full_p046.log`) shows 1 failed, and the correction line is in the status file.

## Limits

- Every number in `DETRAIN` and `BODY_AGE` is APPROX (a design figure). The sources are cited in the file's `_doc` for the
  shape of the curves only. No network access was available, so none of the papers' tables was read, and no figure is
  taken from a published table.
- The switch is a pack value. A scenario or the management UI cannot turn it on (see Deviations).
- Nothing was run with the switch on at town scale. The behaviour with detraining on is covered only by the 16 focused
  tests, on one or two residents.
- Ageing and detraining run only on the dawn tick, which returns early when metabolism is off.
- `body_by_age` is a function that the caller invokes. It is not added to `SimulationReporter.report()`, so no existing
  report output changes.
- The effort-day record is written when an effort's stamina cost is paid (the exerted edge). Efforts that never reach
  that edge are not recorded.
- A resident with a trained part and no recorded effort is treated as idle from the start. This cannot happen through
  normal play, because training with the switch on always records the effort.

## Open questions

1. The brief asks for a self-test check that a working town's mean effective strength stays in a plausible band over a
   long run. A static self-test cannot run a town. The self-test has an analytic band line instead (base to base x
   (1 + TRAIN_HEADROOM)), and the long-run check is not built. The 100-resident run with detraining on has not been run.
   Confirm whether that run is wanted, and in which phase.
2. The brief puts the switch in the `detraining` physical subsystem. The alternative needs `physical_subsystems` to list
   the key, which changes two pinned tests outside this phase's write scope. Confirm which is preferred. If the
   physical-subsystem form is wanted, those two expectations need the new key, as Phase 044 did for births.
3. Phase 045's growth gives a child the pack default base (`ACTOR_DEFAULTS` times the growth fraction), not the drawn
   physique. Founders are drawn (`draw_physique`), and growth never touches them. Ageing scales each resident's own peak
   base. This is not a conflict, but a child born in the simulation has a base of 1.0 at 18, and that is Phase 045's
   behaviour, unchanged here.
4. `docs/phases/phase046/files/**` mirrors the new files in the tree. The live checkout's `worlds/bigville_world.py` has
   uncommitted Tract A edits (Phase 070b), including `_body_capacity_factor` in `effective_strength` and
   `effective_stamina`. None of the nine anchors is on those lines, and each anchor is unique in the live file. The
   supervisor should still apply the hunks against the commit they land on.

## Deviations

- The switch is `DETRAIN.enabled`, a pack value like `DEPENDANTS.enabled`, not a `physical_subsystems` key (see Attempt 1
  and Open question 2).
- The full suite runs on `tests/`, not on the repository root (see Validation).
- The long-run self-test check is an analytic band line (see Open question 1).
- `hunks.json` was written by a one-off generator script kept outside the repository. The JSON is the source of truth,
  and the builder reads only the JSON and `files/`.
- The live checkout was not edited. The 43 pre-existing uncommitted entries (other sessions) are unchanged, and the
  only new entry is `?? docs/phases/phase046/`.
