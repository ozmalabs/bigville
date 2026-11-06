# Phase 058: persona (traits, life sketch, usual day, founding ties, persona card)

## Summary

Each resident now has a derived persona: traits in words, a life sketch from the founding history, a usual
day for their job and life stage, and close ties seeded at founding. A `persona()` card (plain dict of strings)
is built from the resident's own character and records, and `BigvilleGame.persona(actor)` exposes it.

The simple backend's hour bands now come from the pack (`ROUTINE_BANDS`), and the bands are unchanged. Over a
pinned 200-turn town100 run (seed 305000) the action sequences, utterances, handovers, deaths and hunger trace
match the pre-change run exactly, for all 100 residents, with seeding off and with seeding on.

Founding ties are seeded by `plan_ties`, which writes 845 directed bond records. The bigville pack switch
`RELATIONSHIP_SEEDING.enabled` is **false** by default, as the brief's rule requires: four existing tests assert
a town with no held ties and fail when seeding is on. Seeding is tested with `enabled=True` set explicitly.
The supervisor decides whether to turn it on (see Open questions).

Self-test: bigville ERRORS (0) WARNINGS (0); `python3 -m domains.check --pack test_hamlet` ERRORS (0) WARNINGS (0).

## Changes

### Created

- `domains/persona.py`: `traits`, `engine_parameter_names`, `simple_band`, `routine_blocks`, `block_now`,
  `usual_day`, `life_sketch`, `persona` (the card, `CARD_KEYS`).
- `domains/persona_check.py`: `check_persona(pack, errors, warnings, info)`, the self-test checks.
- `domains/relationship_seeding.py`: `plan_ties` (pure planner), `seed_founding_relationships(world, seed,
  enabled=None)`.
- `packs/bigville/world/persona.json`: tables `PERSONA_TRAITS`, `PERSONA_ENGINE_PARAMS`, `ROUTINE_BANDS`, `ROUTINE`
  (28 job rows, `_child`, `_infant`), `ROUTINE_STAGE`, `ROUTINE_WEEK`, `ROUTINE_SEASON`, `PLACE_WORDS`,
  `YEARS_WORDS`, `SPAN_WORDS`, `SCHOOLING_WORDS`, `TIE_DURATION_WORDS`, `OFFICE_WORDS`, `BIOGRAPHY_TEMPLATES`,
  `RELATIONSHIP_SEEDING`.
- `packs/test_hamlet/world/persona.json`: the same tables, smaller: one job row (baker), a market on weekday 2,
  its own wording, and seeding off.
- `tests/test_phase058_persona.py`: 42 tests (41 fast, 1 that runs the simulation in a subprocess).
- `docs/phases/phase058/measure_behaviour.py` and the JSON and log outputs (`behaviour_*.json`, `log_*.txt`).

### Shared-file hunks (all additive)

1. `bigville/backends/cheap.py`: one import line after `from .psi_can import CANWeightModel`
   (`from domains.persona import simple_band`); `_time_band` now returns `simple_band(hour)`. The four bands and
   their order are unchanged.
2. `worlds/bigville_world.py`, `populate_town100`: two lines after `self._found_kinship(cast["residents"], seed)`,
   a local import of `seed_founding_relationships` and the call `seed_founding_relationships(self, seed)`.
   **Deviation:** the brief named `bigville/game.py` for the seeding call. The founding path is
   `populate_town100` (called by `from_town100`), which runs before any game exists, so the call sits there.
3. `bigville/game.py`: new method `BigvilleGame.persona(self, actor)`, inserted before `_context`.
4. `domains/bigville_entities.py`, `check_consistency`: two lines after `check_lexicon(...)`:
   `from domains.persona_check import check_persona` and `check_persona(_WORLD_PACK.path, errors, warnings, info)`.
   The file also holds another session's Phase 050b hunks, which I did not touch.
5. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: 15 `tables` entries appended after `LEXICON_PAYLOAD`.
6. `packs/bigville/world/lexicon.json`: new quantities `hostility`, `mood_bias`, `self_worth`, `arousal`,
   `role_identity` (numeric, with self and other words where an observer could tell); `relationship_kind` self
   phrases `spouse`, `household`, `workmate`, `neighbour`; `published` set to true and the `_doc` sentence updated
   for `charm`, `spite`, `trust`, `outlook`, `temperament`, `day_block`. The file round-trips byte-for-byte through
   `json.dumps(indent=2, ensure_ascii=False)`, so the diff is my additions only.
7. `packs/test_hamlet/world/lexicon.json`: 15 quantities with test-pack wording (the bigville specs with
   different phrases): `charm`, `spite`, `hostility`, `mood_bias`, `trust`, `outlook`, `self_worth`,
   `temperament`, `arousal`, `role_identity`, `day_block`, `life_stage`, `season`, `relationship_strength`,
   `relationship_kind`. No `source` keys, because this pack has no founding town.
8. `tests/test_phase051_lexicon.py::test_the_smaller_pack_lacks_quantities_it_does_not_name`: the expected set of
   test_hamlet quantities changed from `{energy, hunger, hour}` to those plus the 15 above. Reason: test_hamlet now
   names the persona quantities, so its persona card can be built. The `health_status` assertion is unchanged.

No change to `bigville/character.py` (the `CharacterDefinition` shape and `character.personality` are unchanged;
a test checks this), to `domains/population.py`, or to `domains/world_affordances.py`.

### Where the tables come from

- **ROUTINE (hours and tasks):** APPROX. The day runs from the sun and a midday break, the pattern E. P. Thompson
  describes in "Time, Work-Discipline, and Industrial Capitalism" (Past and Present 38, 1967). The hour values are
  not taken from that article. Each job's places come from `JOB_ROUTINE` (checked by the self-test).
- **ROUTINE_BANDS (9, 17, 21):** the boundaries `cheap.py` used before Phase 058, carried over unchanged. Every row
  starts its work at 9, its evening at 17 and its sleep at 21, which the self-test checks.
- **Life stage fractions:** `ROUTINE_STAGE.work_fraction` must equal `LIFE_STAGES[stage].work_fraction` (checked).
- **Market day (5) and church day (6), seasonal farm tasks:** APPROX model choices.
- **RELATIONSHIP_SEEDING counts:** APPROX, within Dunbar's layers: the sympathy group of about 15 (Dunbar 1993,
  Behavioral and Brain Sciences 16(4)) and the close circle (Hill and Dunbar 2003, Human Nature 14). I recalled
  these citations and did not check them against the text (no network access). The cap of 12 close ties is a model
  choice. Strengths are on the lexicon scale; the feud strength of -0.8 is `RELATIONSHIP_KINDS.rival_of`. The rival
  threshold (spite at or above 0.3) is the authored spite mean 0.15 plus one sd (APPROX).
- **Trait edges:** the lexicon's (APPROX, existing).

### Trait classification (the 16 raw numbers)

- Traits in words (10): `charm` (charm_weight), `spite` (w_spite), `hostility` (hostile_weight), `mood_bias`,
  `trust` (prior_others_trust), `outlook` (prior_world_safe), `self_worth` (prior_self_worth), `temperament` (valence),
  `arousal`, `role_identity`.
- Engine parameters, not traits (6): `w_supergraph`, `cred_on`, `claim_weight`, `carried_weight`,
  `resolution_bins`, `emotional_core_enabled`. `claim_weight` is read by the Ocelot cognition engine, not by any
  word a resident would use.

## Validation

Commands and results (in the shared tree, with other sessions' uncommitted edits present):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Info includes
  `PERSONA (bigville): all persona checks pass`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0).
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (final run, `log_full_suite_final3.txt`):
  **1351 passed, 2 skipped, 3 failed** (about 8.8 minutes). The 3 failures are the Ocelot baseline (below).
- `pytest tests/test_phase058_persona.py`: 42 tests, all pass (the 50-turn comparison included).

### Existing tests that failed with seeding on by default, and were fixed by the default-off switch

Seeding was first on by default. These four existing tests failed because they assert a town with no held ties.
I did not edit them. With the bigville default off they pass.

- `tests/test_bigville_disposition_seed.py::test_seed_generated_relationships_not_auto_wired_into_from_town100`
  (845 records, expected 0)
- `tests/test_bigville_reporting.py::test_report_covers_physical_economy_and_recorded_social_activity` (846, expected 1)
- `tests/test_bigville_topic_style_migrated.py::test_a_bare_from_town100_still_seeds_zero_relationships` (845, expected 0)
- `tests/test_bigville_topic_style_migrated.py::test_town100_workplace_relationships_are_sparse_not_all_pairs`
  (17 outgoing ties on one resident, expected at most 2; the opt-in workplace seeding counts all records)

### Failures that are not caused by this phase

- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `tests/test_mixed_ocelot_checkpoint_parity.py::...midpoint...`, and
  `tests/test_mixed_ocelot_village.py::...rejects_invalid_action`: `ModuleNotFoundError: No module named
  'worlds.bigville_ocelot_adapter'`. The module exists only in the sibling Ocelot checkouts
  (`/home/matt/ozmadev/ocelot-*`), not in this repository. In a clean `git archive HEAD` copy with those three
  untracked test files added, they skip instead of failing. This is the baseline the brief names.
- During my run, `tests/test_phase013a_packs.py` (export byte-identity and compile-back) and
  `tests/test_phase013b_data_pack.py::test_a_fresh_view_of_the_bigville_pack_equals_the_default_modules` failed
  because another session edited `packs/bigville/world/resolution.json`, `free_actions.json`, `major_actions.json`
  and `worlds/resolution.py`. In a scratch HEAD copy with only my files added, all three pass. They passed in the
  final run.
- Two failures were my own, and are fixed: `test_phase013a_packs::test_export_rerun_is_byte_identical` (my
  `persona.json` was hand-formatted; I replaced it with the exporter's output, which is semantically identical) and
  `test_phase015_offices` (my check rejected an office word for a key the pack renamed; the card now falls back to
  the key as words, and the check is no longer strict on keys).

### Behaviour: the simple backend, before and after

Command: `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label ... --turns 200 [--seeding off|on]`.
Simple backend for all 100 residents, seed 305000, 200 `game.step()` turns. Each run takes about 5.5 minutes.

| arm | actions (eat, fetch, move, none, rest, sleep, work) | utterances | handovers | deaths | hunger mean at end | ties on record | per-resident action digests |
|---|---|---|---|---|---|---|---|
| before (no Phase 058 code) | 32, 30, 4904, 4263, 2288, 108, 15 | 713 | 0 | 97 | 0.8893 | 0 | (reference) |
| before, repeat | same | 713 | 0 | 97 | 0.8893 | 0 | identical |
| after, seeding off | same | 713 | 0 | 97 | 0.8893 | 0 | identical |
| after, seeding on (explicit) | same | 713 | 0 | 97 | 0.8893 | 845 | identical |
| after, default (off) | same | 713 | 0 | 97 | 0.8893 | 0 | identical |

All fields of the JSON (action counts, utterances, handovers, deaths, the hunger trace for all 200 turns, the
per-resident digests, and the full sequences of five named residents) match the before run in every arm. The
before run is deterministic: two runs with `PYTHONHASHSEED=0` agree.

The before run is deterministic: two runs with `PYTHONHASHSEED=0` agree. In this run the simple backend's choices did
not read the new tie strength: its decisions use the hour band, its own goals, and the nearest resident for speech
(`cheap.py`, `_speech`). Seeding does change the observation payload: with seeding on, 4 of 39 nearby residents of
a sampled resident carry a non-zero `tie_strength` (0 of 39 with seeding off).

Two findings from the measurement are not Phase 058's to fix. In the 200-turn run, 97 of 100 residents die
(hunger; mean hunger rises from 0.07 to 3.57 by turn 100), so the run covers a dying town. The simple backend's
behaviour, in both before and after, is the same as before this phase.

### Relationship records at founding (100 residents, seed 305000, enabled explicitly)

| kind | directed records | notes |
|---|---|---|
| blood_kin | 258 | 196 are also in the same household (flag `household`); 62 are kin outside the house |
| spouse | 10 | 5 couples, both ways |
| household | 0 | every household pair is also a kin pair, and kin keeps its kind; the flag marks them |
| friend | 200 | 2 per resident, by trait compatibility and class, with a seeded tie-break |
| neighbour | 200 | 2 per resident, nearest home cells within 6 steps (Manhattan) |
| workmate | 160 | up to 2 per resident from the same workplace cell |
| feud | 17 | from residents with spite at or above 0.3, the most distant in class and trait |
| **total** | **845** | 542 of them are reciprocated |

Per resident, total ties are 4 to 16 (median 8). Close ties (spouse, blood_kin, household, friend, feud) are 2 to 12
(median 5); no one has more than 12, and friends and rivals are capped to the room left under 12. No resident has
zero ties.

### Acceptance check

- Traits in words, no engine parameter among them: `test_traits_are_words_and_no_engine_parameter_is_among_them`,
  `test_every_personality_number_is_a_trait_or_an_engine_parameter`.
- Biography consistent with the history: `test_the_life_sketch_follows_the_founding_history` (for all 100 residents).
- Usual day for the job: `test_every_job_has_a_routine_and_the_day_is_six_blocks`, and the market, church and farm-season
  tests.
- Plausible relationships of the right kinds: the tie tests above.
- Household and kin ties match Phase 009: `test_household_members_are_tied_to_each_other`,
  `test_spouses_are_tied_as_spouses_both_ways`, `test_parents_and_children_are_kin_both_ways`.
- Same seed, same persona and relationships: `test_seeding_is_reproducible_from_the_seed_and_changes_with_it`,
  `test_the_life_sketch_is_the_same_for_the_same_seed`, `test_the_card_for_the_same_seed_is_the_same`.
- A different pack gives different words and a different day: `test_a_different_pack_gives_different_words_and_a_different_day`.
- The simple backend's behaviour matches the old hour bands: `test_the_simple_bands_equal_the_old_hour_bands_at_every_boundary_and_between`,
  and `test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns` (a subprocess run, compared with the
  recorded before run for five residents and the hunger trace over 50 turns).
- Self-test checks: `check_persona` (routine rows for every job, bands, life stages, trait classification, biography
  placeholders, seeding kinds, strengths, counts and stream). Rejection tests: `test_the_checks_reject_*` (3).
- Persona card: no digits (`test_the_card_is_plain_strings_with_no_digits`), only the resident's own ties
  (`test_the_card_lists_only_the_residents_own_ties`), the life sketch names no other resident.
- The world reads no routine: `test_nothing_in_the_world_reads_the_routine`.
- Midnight is the sleep block: `test_the_card_at_midnight_gives_the_sleep_block` (a bug I found and fixed: hour 0.0
  was treated as missing).

## Limits

- **Not verified:** the hours, the Dunbar counts, and the seasonal and weekly rhythm are model choices and APPROX. I
  did not check the cited articles' text (no network).
- **Simple backend and the routine:** `cheap.py` reads only the four bands. The meal times, market day and seasons are
  persona data. The simple backend does not use them, because the brief allows that only if every test and the
  measurement stay identical, and I chose not to add that risk. The routine is not enforced by the world.
- **Bands are the default pack's:** `cheap.py` reads the bigville pack's `ROUTINE_BANDS` (through the default pack name),
  so a test pack's bands would not affect it.
- **Years known:** a tie's `years_known` is the shorter of the two residents' years in the village (kin: the holder's
  age). This models how long they have known each other; no resident is shown another's history.
- **Persona card scope:** it is built from the character, the founding history, the held kin terms and the holder's own
  bond records. It is not yet the agent view's `self` (Phase 052) or a prompt section (Phase 054).
- **Not run:** the 100-resident town with Ocelot or LLM residents; any run longer than 200 turns; any seed other than
  305000; a save and reload of seeded bonds (persistence code is another session's and not exercised here).
- **Ocelot tests:** three fail in this tree for the environmental reason above. I did not verify them beyond that.

## Open questions

1. **Seeding default.** Off for bigville, because four existing tests assert zero or one held ties. Turning it on
   means editing those four tests (their assertions are about the old empty town), or keeping them as they are
   and accepting that they describe a town without ties. Decide which.
2. **Household kind.** Every household pair in the founding town is kin, so the kind `household` never appears there.
   The flag `household` carries the fact. Should the founding town contain non-kin housemates (lodgers, servants)?
   That is a population question for Phase 009's model.
3. **Seeding call site.** It is in `populate_town100` (world), not in `BigvilleGame`, as the brief's write scope
   suggested. The founding path is in the world, and the game is built after it.
4. **Routine detail for the simple backend.** Should a later phase let the simple backend use the meal and market
   times? It would change its behaviour, so it needs a new measurement.
5. **Trait `published` flags.** Six existing quantities and `day_block` are now published by Phase 058, which the
   lexicon's `_doc` says. If another phase needs them unpublished, the flags can go back.
