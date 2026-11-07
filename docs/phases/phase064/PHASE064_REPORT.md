# Phase 064 report: reading, writing and numbers at the agent view

## Summary

A written mark in the agent view now reads at the resident's literacy, and a price or a count is put into the words of
the resident's numeracy. A resident sees the words it knows amid squiggles, the short text, or the whole text, according
to its literacy tier. Each resident's numeracy tier chooses between a count of loaves and a figure in coins. A word is
learned when its referent is carried or in view. Both sides are behind `READING.enabled`, which defaults to off.

The example from the brief works in tests: a sign that says "ALE sold here" reads as "a sign: marks you cannot read" for
a smith with no word on it, as "a sign: ALE ~~~ ~~~" for a labourer who knows ALE from his trade, as "a sign: ALE, sold
here" at functional literacy, and as the full text at educated literacy. A price reads as "one loaf" for a tally
resident and as "two coins" for a commercial one.

Limits that shape what this phase delivers (detail under Limits):
- The town has no written marks. Marks attach to physical objects whose id is in `WRITTEN_MARKS`, and the 100-resident
  town declares none. In a real run the writing section is absent until a scenario declares such objects.
- The LLM prompt packet and the TUI narrator pick named keys from `around`, so neither shows `writing` yet.
- The world has no numeracy attribute. The numeracy level is the existing `capability` attribute.

## Changes

### New files

- `domains/reading.py`: the reading percept (`known_words`, `percept`, `writing_rows`). `writing_rows` is the one entry
  point the agent view calls. It returns None when reading is off, so the view has no section.
- `domains/numeracy.py`: numeracy levels and tiers (`level`, `tier_row`), spelled numbers (`spell`), counts
  (`quantity_words`) and prices (`price_words`).
- `domains/reading_check.py`: the self-test for the reading and numeracy tables (`check_reading`).
- `packs/bigville/world/literacy.json`: tables `READING`, `LITERACY_TIERS`, `NUMERACY_TIERS`, `NUMERACY_UNITS`,
  `NUMERAL_WORDS`, `WRITTEN_KINDS`, `WRITTEN_MARKS`, `RECOGNISED_SEED`. Exporter-canonical (`tools/export_pack.py
  --pack bigville` output is byte-identical).
- `packs/test_hamlet/world/literacy.json`: the same file, except `RECOGNISED_SEED`. The hamlet pack has only the
  `baker` and `constable` trades, so its seed names only `baker`. Exporter-canonical.
- `tests/test_phase064_reading.py`: 16 tests.
- `docs/phases/phase064/build_clean_tree.py`: builds HEAD plus 062 plus 064 (or HEAD plus 062 only, with
  `--without-064`) for measurement.
- `docs/phases/phase064/dump_views.py`: dumps the agent and referee views of 31 residents, for comparing trees.
- `docs/phases/phase064/behaviour_head60.json`, `behaviour_t064_off60.json`, `logs/`, and this report.

Names: the supervisor's list used `domains/literacy.py`, `literacy_check.py` and `tests/test_phase064_literacy.py`
as examples. I used the names in the brief (`reading.py`, `numeracy.py`, `reading_check.py`,
`test_phase064_reading.py`).

### Shared files (anchored hunks)

Each hunk is asserted to match once in `build_clean_tree.py`. Line numbers are not given because other sessions edit
these files.

1. `packs/bigville/pack.json`, in `tables`: after the last entry
   `{"name": "PERCEIVER_TIERS", "file": "world/perception.json"}`, eight entries follow, one per table of
   `world/literacy.json` (READING, LITERACY_TIERS, NUMERACY_TIERS, NUMERACY_UNITS, NUMERAL_WORDS, WRITTEN_KINDS,
   WRITTEN_MARKS, RECOGNISED_SEED), each `{"name": ..., "file": "world/literacy.json"}`.
2. `packs/test_hamlet/pack.json`: the same eight entries at the same anchor.
3. `packs/bigville/world/agent_view.json`, `AGENT_VIEW_WHITELIST`: `around` gains `"writing"` after `"things"`, and a new
   section `"writing": ["percept"]` follows the `thing` section. Anchor: the `"seen", "things" ], "thing": [...] ],` block.
4. `packs/test_hamlet/world/agent_view.json`: the same two edits at the same anchor.
5. `domains/agent_view.py` (062's file, whole; 064 hunks are two):
   a. import line `from domains import map_memory, perceiver` becomes `from domains import map_memory, perceiver, reading`.
   b. in `_around`, the line `things = _things(world, actor, pack, rec, log)` followed by the `return _check_keys("around",
      {"people": ..., "things": things}, pack)` line is replaced by: the same `things` line, a dict `around`, the
      `writing = reading.writing_rows(...) if rec is not None else None` line, `if writing: around["writing"] = writing`,
      and `return _check_keys("around", around, pack)`. With the perceiver off (`rec` None) the output is unchanged.
6. `domains/agent_view_check.py`: the `SECTIONS` tuple gains `"writing"` (the self-test checks the whitelist's sections
   against the builder's list). Needed for the self-test to stay at 0 errors.
7. `domains/bigville_entities.py`, in `check_consistency`: after the line `check_perception(_WORLD_PACK.path, errors,
   warnings, info)`, two lines: `from domains.reading_check import check_reading` (with a Phase 064 comment) and
   `check_reading(_WORLD_PACK.path, errors, warnings, info)`.

No backend file changed. The faculty declarations from Phase 062 cover literacy and numeracy already.

## Design

- **Reading tiers.** `LITERACY_TIERS` maps each literacy tier (labouring, functional, educated, named by
  `shared_frames.literacy_tier`) to a reading mode: `words` (known words amid squiggles), `short`, or `full`.
  `WRITTEN_KINDS` gives one template per mode, plus `unreadable`. A `words` reader whose known words do not occur in
  the text gets `unreadable`. This is the "none" tier of the brief: it is an outcome, not a literacy row.
- **Recognition.** A resident knows the words in `RECOGNISED_SEED` for its trade, its own name, the common numerals
  (`one`, `two`, `three`), and the words in its learned-word memories. Recognition does not depend on literacy.
- **Learning.** When a mark's `refers_to` word is carried, or is the kind of a physical object in view, and the mark is
  in sight in a light other than `dark`, the word is held as a memory (`kind: learned_word`) up to `learned_max`
  (40). The percept for that view uses the words known before the sighting; the next view shows the word.
- **Numeracy.** The level is `capability` (the world's general reckoning and comprehension, in `frames/constants.json`;
  founders: 0.55 unlettered, 0.9 literate). `NUMERACY_TIERS` maps a level to a tier: `exact_max` (spelled), `few_max`
  ("a few"), and above that "many". `prices: units` counts the price in the mark's unit ("one loaf", 2.0 coins per
  loaf); `prices: figure` says the price in coins ("two coins"). Numbers are spelled, so no view string has a digit.
- **Truth.** The referee block's `perception.subjects` gets one `kind: writing` row per mark in sight: the percept, the
  truth (full text, the figure in coins), and the tiers.
- **Represented faculties.** A `represented` literacy or numeracy gives the full text and the figure, as the simple
  backend's declaration says.
- **Data.** Thresholds, units, numerals, seeds and tiers are all in `literacy.json`. The self-test checks them.

## Validation

Working tree (shared, with other sessions' uncommitted edits):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Info: "READING: 3 written kinds, 3 marks,
  3 literacy tiers, 4 numeracy tiers; reading is off in this pack". Log: `logs/selftest_working_tree.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase064_reading.py`: 16 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase062_perceiver.py tests/test_phase052_agent_view.py
  tests/test_phase053_fog.py tests/test_phase054_llm_prompt.py tests/test_phase054_actionable.py
  tests/test_phase060_speech_in.py tests/test_phase064_reading.py`: 205 passed, 3 skipped (final code).
  The wider set (adds test_phase042, test_bigville_backends, test_phase031, test_phase059) gave 299 passed, 3 skipped,
  before the final one-line change described below.
- Full suite, `timeout 6000 python3 -m pytest -q -p no:cacheprovider -rfE` (log: `logs/full_suite_working_tree.log`):
  **29 failed, 2156 passed, 6 skipped** in 3051 s. It started before the final edit. That edit changes only the
  reading-on path, which the suite does not switch on. Attribution, below.

Clean tree (`docs/phases/phase064/build_clean_tree.py --out /tmp/t064`: HEAD 6b6822d plus 062 plus 064):

- `domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Log: `logs/selftest_clean_t064.txt`.
- `tests/test_phase064_reading.py` plus `tests/test_phase062_perceiver.py`: 41 passed.
- The 29 failed tests of the full run, rerun on this tree (excluding the 3 Ocelot files, which are absent from it):
  25 passed, 1 failed (`test_phase055_concurrency.py` speed test, a known timing check under load). Log:
  `logs/failed26_on_clean_t064.log`.
- `tools/export_pack.py --pack bigville` and `--pack test_hamlet` (to a scratch directory): both `world/literacy.json`
  files byte-identical to the tree's copies.

Attribution of the 29 failures in the working tree:
- 3 Ocelot tests (`test_bigville_ocelot_communication`, `test_mixed_ocelot_checkpoint_parity`,
  `test_mixed_ocelot_village`): `No module named worlds.bigville_ocelot_adapter`. Known; the files are untracked.
- 4 `tests/test_phase057_tui.py` HTTP tests: known.
- 1 `test_phase055_concurrency.py` speed test: known, timing-flaky under load.
- 21 self-test and pack tests (phases 004, 008, 009, 010, 011, 013a, 013b, 015, 016b, 017, 019, 026, 027, 034, 035,
  042, 051, 058). Their messages cite tables other sessions are editing in the working tree: `MARKS`, `MARK_RULES`,
  `MARK_EVENTS`, `MARK_HARM`, `SHOCKS`, `RECIPES`, and a stale `bigville/seeds/gen_recipes.json`. None mentions
  `READING`, `WRITTEN`, `LITERACY`, `NUMERACY`, `writing` or `reading`. All 21 pass on the clean tree.
- The human browser test and the asset-manifest test did not fail in this run.

Behaviour (Phase 058 harness, 100 residents, simple backend for all, seed 305000, `PYTHONHASHSEED=0`, 60 turns):

| Run | Tree | Switches | Utterances | Action counts | Hunger mean (end) | Result |
|---|---|---|---|---|---|---|
| head60 | `git archive HEAD` (6b6822d) | none | 285 | eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15 | 0.4442 | reference |
| t064_off60 | clean 064 tree | pack defaults (off) | 285 | same | 0.4442 | identical to HEAD: every field of the JSON except label and elapsed time (per-actor digests, per-turn hunger, sample sequences) |

The off run was repeated on the final code, after the one-line change; the first off run was identical too. Files:
`behaviour_head60.json`, `behaviour_t064_off60.json`.

Agent views (31 views each: 30 residents and the player, agent and referee modes, `dump_views.py`; md5s in
`logs/agent_view_md5.txt`):

- HEAD and 064 with both switches off: byte-identical.
- 062 with perception on and 064 with perception on and reading off: byte-identical.
- 064 with perception on and reading on: byte-identical to 062 with perception on, because the town has no written
  marks.

Not run: a village with an LLM or TUI client (no provider, not in the brief); the 100-resident run longer than 60 turns;
a run with reading on and written marks in the town (the tests script the marks instead).

## Limits

- **No written marks in the world.** `WRITTEN_MARKS` is keyed by physical object id, and the 100-resident town declares
  no such object. Physical objects in the view are the only source. A scenario that declares the objects gets the
  writing section. The marks, their text and prices are authored in the pack; prices do not follow the shop's price.
- **Learning writes in the view builder.** `reading.writing_rows` appends `learned_word` memories when it runs, so the
  agent view writes state when reading is on. Each word is learned once, and the view is otherwise read-only. A turn
  hook in `game.py` would be cleaner, and was out of scope.
- **"Used" is not modelled.** A word is learned when its referent is carried or in view, not when the resident uses it.
- **Learned words do not raise literacy.** The brief has learning raise literacy slowly. The `literacy` attribute is a
  world attribute (Tract A), so reading tiers do not move with learning.
- **Numeracy source.** The world has no `numeracy` attribute. The level is `capability` (frames/constants.json says it
  is the general reckoning and comprehension). The tier thresholds (0.6, 0.8, 0.95) are APPROX, authored.
- **Output channels.** The LLM prompt packet (`bigville/backends/prompt_packet.py`) and the TUI narrator
  (`bigville/tui/narrate.py`) pick named keys from `around`, so `writing` reaches neither yet. Both are outside this
  phase's write scope. The agent view itself carries the section.
- **Kinds.** Three written kinds (sign, price, notice). The brief also lists labels, ledgers, letters and laws. The
  notice's `refers_to` is the mill.
- **Quantities of carried goods.** Carried amounts still use the lexicon amount words. Numeracy changes only the counts
  and prices written on marks.
- **Coin value of a loaf.** 2.0 coins, the shop price default in `prices.json` (APPROX, a model default).
- **Numbers above 999.** Said as "many". Prices above 999 coins are not spelled.
- **Calculator action.** The brief's optional calculator action for a numerate backend is not built.
- **Dark.** Light comes from the perceiver record. Nothing is read or learned in the `dark` light.
- **Distance.** Mark distance uses `world._physical_location_cell`, the same private helper Phase 062 uses.
- **Simple backend.** It never reads the agent view, so reading does not change its runs.

## Open questions

1. Which sources of written marks should Tract A add: scenario physical objects, or a method on the square fixtures
   (the noticeboard is a fixture today, not in the view)?
2. Should `around.writing` reach the LLM prompt packet and the TUI narrator? Both need a small hunk outside this
   phase's scope (`prompt_packet.py` caps and `narrate.py`).
3. Should numeracy be its own world attribute, rather than `capability`?
4. Should learned words raise the literacy attribute slowly, as the brief says? That needs a world write.
5. Should learning move from the view builder to a turn hook in `game.py`?
6. `docs/phases/phase062/build_clean_tree.py` no longer builds on HEAD 6b6822d. Its manifest anchor expects
   `speech_acts.json` as the last entry, and Phase 061 added `SPEECH_PARSER` after it, so it stops with "anchor found 0
   times". This phase's builder carries the corrected anchors and does not change 062's script. The 062 report's clean
   tree needs the same fix to be rebuilt.
