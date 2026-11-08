# Phase 070: located harm and silent detail

## Summary

The body now keeps a per-locus ledger of acute harm. `harm()` takes an optional `locus`. When the caller
gives none, the body draws one from the pack table `HARM_LOCUS` by a stateless seeded draw. The health
scalar is still lowered once per harm, with the same numbers as before. The ledger falls with time and with
care, and it feeds two new signal sources (sharp and dull, at the place). Four silent or slow states are
readable as signal sources: deficiency, incubating illness, hangover and withdrawal, and a chronic short-sleep
debt the body keeps. Each steady signal habituates. A checkup records the silent conditions from the referee
state. Injuries show as observable signs. Everything in this phase is descriptive or additive. No existing
health, starvation or strike number changed.

Validation: entity self-test 0 errors, 0 warnings. The 60-turn and 200-turn simple-backend village digests
equal the pre-phase tree, with 0 deaths in both. New tests: 22 in `tests/test_phase070_locus.py`, all pass.
The full suite gives 15 failed, 2328 passed, 6 skipped, 2 collection errors. Every failure is either present
at baseline or is one of the other session's known failures (details under Validation).

## Changes

### Created

- `tests/test_phase070_locus.py` (22 tests).
- `docs/phases/phase070/`: this report, the digest script (`compare_digest.py`, a copy of the Phase 063
  `compare60.py`), the base and new 60- and 200-turn digests, the self-test and seeds outputs, the full suite log.

### Changed (Tract A files from Phase 069, this session's)

- `worlds/body.py`:
  - `EVENT_KINDS` gains `heal`.
  - `pack_tables` loads `HARM_LOCUS`, `BODY_RATES` and `OBSERVABLE_SIGNS`.
  - `initial_state` adds `ledger`, `habituation`, `sleep_debt`, `findings` (plain values).
  - `Body.located()`, `Body.apply()` (harm with locus adds to the ledger; heal lowers it by `care_share`),
    `Body.tick()` (habituation step, sleep-debt step, time decay of the ledger), `Body.screen()` (silent
    conditions from the referee block, kept in `state["findings"]`), `referee()` adds `located`, `habituation`.
  - `WorldBackedBody.reads()` adds `deficiency`, `hangover`, `withdrawal`, `sleep_debt`, and `illness` now
    reads an incubation ramp. `observable()` adds signs after the Phase 063 marks.
  - `BodyMixin`: `_body_harm_locus`, `_body_locus_ok`, `_body_screen`, `screening_findings`,
    `injuries_by_locus`.
- `domains/interoception.py`: `READS` extended, `LOCATED_READS = ("injury",)`, `pick_locus`, `source_rows`
  (one row per locus for a located source), `derive(..., located=, habituation=)`, `intensities(..., located=)`.
  The trend uses the raw intensity; the felt intensity is habituated. Each referee row adds `raw_intensity`.
- `domains/interoception_check.py`: the three new tables are required; `_check_phase070` (HARM_LOCUS covers
  every HEALTH cause and names ANATOMY loci other than the root, BODY_RATES in range, OBSERVABLE_SIGNS read a
  real read or `injury` and name real loci); located source rows must name a located read with a null locus.
- `packs/bigville/world/interoception.json` and `packs/test_hamlet/world/interoception.json` (identical copies):
  - `SIGNAL_SOURCES`: `injury_sharp`, `injury_dull` (located), `deficiency`, `hangover`, `withdrawal`, `sleep_debt`.
  - New tables `HARM_LOCUS`, `BODY_RATES`, `OBSERVABLE_SIGNS`.
  - `INTEROCEPTION.forbidden_words` gains `bruise`, `bruised`, `limp`, `pallor`, `deficiency`, `deficient`,
    `withdrawal`, `hangover`, `incubating`, `incubation`, `debt`, `sleepless`.
  - `_doc` strings updated.

### Changed (shared files; my hunks only)

- `worlds/bigville_world.py` (Phase 070 hunks; the Phase 069 hunks stay in the same file):
  - `harm(actor, amount, cause, locus=None, *, fragility=True)`: validates a given locus, draws one when none
    is given, passes it to `_drop_health`. Function `harm`.
  - `_drop_health(actor, drop, cause, locus=None)`: the Phase 069 `_body_event` call now carries `locus`. Function `_drop_health`.
  - `_heal`: records the actual health rise as a `heal` body event. Function `_heal`.
  - `checkup`: one line, `self._body_screen(patient)`, after the `screened` flag is set. Function `checkup`.
  - No hunk in the strike code (see Deviations).
- `domains/world_affordances.py`: after the Phase 069 `INTEROCEPTION` binding, a comment line and three
  bindings (`HARM_LOCUS`, `BODY_RATES`, `OBSERVABLE_SIGNS`). Module level.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: three manifest rows after the `INTEROCEPTION`
  row (lines 16 to 18). Both files are checked against the exporter's output in a temp directory: byte-identical.
- `bigville/reporting.py`: one line in `game_report()`, `report["injuries"] = game.world.injuries_by_locus()`.
  It is outside `world.report()`, because `export_state()` includes `world.report()`, and a key there changed the
  digest (see Validation).

Not changed: `domains/bigville_entities.py` (it already calls `check_interoception`), `domains/agent_view*.py`,
the prompt packet, the TUI, `game_persistence.py`, `world_persistence.py`, and any test other than the new file.
No existing test was edited.

## Design

- **Two outputs stay separate.** `harm()` still lowers `health_value` once. The ledger is `body.state["ledger"]`
  (`{locus: amount}`), descriptive only.
- **Locus draw.** `pick_locus(weights, seed, "locus", actor, cause, turn)` in `domains/interoception.py`. It is a
  sha256 draw over the sorted weights. It does not use `random.Random` and does not touch `world._rng` (a test
  checks the RNG state is unchanged). Whole-body causes (an empty row: starvation, exhaustion, age, intoxication,
  illness, childbirth, neglect) draw no locus and leave no ledger entry.
- **Ledger rules.** A harm adds its drop (after fragility) to its locus. Each health gain from `_heal` (rest, care,
  treatment) lowers the ledger by `care_share` times the gain, largest locus first. Each clock tick lowers every
  locus by `located_heal_per_tick`. The scalar's own recovery is unchanged.
- **Located signals.** A source row with `"located": "injury"` yields one row per locus with a value,
  named `injury_sharp@arm` and so on. Its locus is the ledger's locus. The sharp and dull rows use the surface
  channel, so the place can resolve to the leaf (arm, leg).
- **Silent and slow states.**
  - Deficiency: the `deficiency` attribute on the body node (Phase 035), floor 0.1, awareness 0.3.
  - Incubating illness: the existing `illness` row. Its read is now `min(1, (illness_days + 1) / incubation_days)`
    while the disease is present, so day 0 is 0.2 of full strength (below the awareness of 0.3). The read is 0 when
    there is no disease.
  - Hangover: `hangover_ticks / INTOXICATION.hangover_ticks` when `_hangover_on` (Phase 036), else 0.
  - Withdrawal: `_withdrawal_share` (Phase 036), floor 0.3.
  - Sleep debt: the body's own store. `tick()` adds `sleep_debt_rise` on an awake tick and subtracts
    `sleep_debt_fall` on an asleep tick (floor 0). It reads as debt / `sleep_debt_full`.
- **Habituation.** `state["habituation"]` per source. A rise larger than `trend_delta` resets it to 0. A steady
  signal (change within `trend_delta`, value above 0) moves toward 1 by `habituation_rate` of the remainder. A
  stopped or eased signal decays by `habituation_recover`. The felt intensity is raw times (1 - habituation).
  The trend and habituation both compare with the previous tick's raw intensities.
- **Observable signs.** `OBSERVABLE_SIGNS` rows (bruise, limp from a leg injury, pallor from deficiency) show when
  their level, the distance and the light pass the row's thresholds. They are appended to the Phase 063 marks in
  `observable()` and are not in any felt view.
- **Screening.** `checkup` calls `body.screen()`, which records each source with a raw intensity above 0 that the
  resident does not feel. The record is in `body.state["findings"]` (the last 10), and
  `world.screening_findings(actor)` reads it. The resident's view is unchanged.

## Data and sources

All new numbers are APPROX. The only source cited is the sleep-need basis for `sleep_debt_*`: Hirshkowitz and
others (2015), National Sleep Foundation sleep duration recommendations, Sleep Health 1(1). I cited it from memory
and did not re-check it, so it is marked as such in `BODY_RATES._doc`. The anatomy weights, the rates, the
floors and the sign thresholds are model choices of the right order.

## Changed numbers

None of the existing numbers changed. The new numbers are the pack rows above and `HARM_LOCUS` weights.
No test assertion was changed or removed.

## Validation

Commands and results (live tree, after all edits):

- `python3 domains/bigville_entities.py`: ERRORS (0), WARNINGS (0), exit 0. Output in `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: ERRORS (1), exit 1. The one error is
  `DEPENDANTS: 'infant' is not a REFUSAL_REASONS code`, from the other session's untracked
  `packs/*/world/dependants.json`. The same error is present on the baseline copy. Output in `selftest_test_hamlet.txt`.
- `python3 tools/generate_seeds.py --check`: exit 0, 31 files match. Output in `generate_seeds_check.txt`.
- Exporter layout: `tools/export_pack.py` run into a temp directory for both packs. My files (`interoception.json`,
  `pack.json`, `actor_defaults.json`, `animals.json`, `agent_view.json`) are byte-identical to the live copies.
- Digests (`docs/phases/phase070/compare_digest.py`, simple backend, town100, seed 305017):
  - 60 turns: base and new both `f334f71ecf7088d39001f5343cbcbbd32f9ae01a6e184c776bd69bbbe97b6f9b`, 0 deaths.
  - 200 turns: base and new both `eadc65c66dcb26623e2de301ce54b026e8419f6e5585d6142982cb6561043e78`, 0 deaths.
  - The base is a copy of the tree taken before any Phase 070 edit (`/tmp/base070`).
  - The first 60-turn run after adding `injuries` to `world.report()` gave a different digest. The cause was that
    `export_state()` includes `world.report()`. I moved the key to `game_report()`, and the digest then matched.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase070_locus.py tests/test_phase069_body.py`: 53 passed
  (22 new, 31 from Phase 069).
- Related tests (phases 052, 054, 063, 037, 038, 043, 035, 036, 065, the reporting test): 249 passed in the
  run before the reporting move. The full suite below ran after all edits.
- Full suite, after all edits: `python3 -m pytest -q -p no:cacheprovider -n 6 --continue-on-collection-errors`
  (xdist as in Phase 069; log in `full_suite.log`): **15 failed, 2328 passed, 6 skipped, 2 errors** (781 s).
  - 11 of the failures are the same tests that fail on the baseline copy (`/tmp/base070`, same files):
    `test_phase004_located_gathering` (hamlet self-test, the DEPENDANTS error), `test_phase013a_packs::test_export_rerun_is_byte_identical`
    (other session's `world/dependants.json`), `test_phase013b_data_pack` (hamlet check), `test_phase014_parameters`,
    `test_phase016a_founding_town`, `test_phase009_kinship` and `test_phase011_fiscal` (hamlet pack),
    and four in `test_phase057_tui.py` (HTTP and TUI).
  - 3 are the Ocelot import failures the brief names: `test_bigville_ocelot_communication`,
    `test_mixed_ocelot_checkpoint_parity`, `test_mixed_ocelot_village`. They raise
    `ModuleNotFoundError: worlds.bigville_ocelot_adapter`. The baseline copy skips the first one, because its
    sibling `../ocelot` checkout is absent from `/tmp`, so the copy does not show the failure. On the live tree these
    fail the same way the brief describes.
  - 1 is `test_phase055_concurrency`, a timing test. It fails under the 6-worker load, and it passes alone (6 passed).
  - 2 are collection errors, `test_phase044_births` and `test_phase045_dependants` (import file mismatch between
    same-named files under `docs/phases/phase044` and `phase045` and the test directory). Both files pass when run
    alone (18 and 17 passed). I did not compare this collection error against the baseline in a full run.

## Limits

- The incubation read is a ramp on the existing illness flag, not a separate incubation state. Phase 043 has no
  incubation stage: onset diagnoses the illness at once. Here, the early days are the ramp.
- Silent states are not tuned. No village run was made to see how often a deficiency, a debt or a hangover is felt.
- Located injury has no effect on capacities (a broken leg does not slow walking). Out of scope per the brief.
- The depth rule is monotone, so a growing condition is felt first as a shallow sound and then a deeper one. There is
  no separate "shallow then deep" curve.
- Checkpoints: body state is plain values and is covered by a dump/load test. Wiring the body into
  `game_persistence.py` and `world_persistence.py` is not done (owned by the other session).
- Strike harm: not changed. See Deviations.

## Deviations

- **Strike locus.** The strike proposal does not name a locus. `strike_harm` calls `harm(..., "violence")`
  unchanged, so no strike call site passes a locus. A proposal field would be needed to use the path.
- **Illness locus.** The brief says an illness takes its place from its disease row. The disease table has no
  locus, and fever is systemic. I gave `illness` an empty `HARM_LOCUS` row (whole-body). A locus per disease
  would need a field in `DISEASE`.
- **Incubation.** See Limits. The brief's "incubating illness" needs a state the world does not have.
- **Mood.** Not a source, as in Phase 069.

## Open questions

1. Should a located injury lower a capacity (strength, speed) for as long as it is open? The brief defers it.
2. Should `illness` get a locus per disease, or stay whole-body?
3. Should the strike proposal name a locus (for example "arm" for a grab)? That would change the Phase 038 proposal shape.
4. The sleep-debt rates assume one tick is 15 minutes (TIME). Check the adult sleep basis before relying on the balance.
5. The other session's `world/dependants.json` causes the hamlet DEPENDANTS error and the export test failure.

## Follow-ups

- Wire `worlds/body.py` state (`embodiment`, which now holds the ledger, habituation, sleep debt and findings) into the
  checkpoint code, if the Ocelot persistence stream does not already carry `world.embodiment`.
- A village run with illness and aftereffects switched on, to see how often the silent states are felt.
- Phase 071 (attending and pressing) reads the ledger and the habituation state.

## Hunks in shared files, by function

- `worlds/bigville_world.py`: `harm` (signature, locus check, draw, pass-through), `_drop_health` (locus parameter and body
  event), `_heal` (heal body event), `checkup` (one `_body_screen` line). Phase 069 hunks in this file are unchanged.
- `domains/world_affordances.py`: module level, after the `INTEROCEPTION` binding (three bindings and a comment).
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: three manifest rows after `INTEROCEPTION`.
- `bigville/reporting.py`: `game_report()`, one line.
