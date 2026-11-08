# Phase 065b report: mishearing, shifted counts and written prices

## Summary

Phase 065 left three parts of its brief out. This phase builds two of them and shows that the third is not built:

- **Speech mishearing (brief item 6).** A distorted listener hears a sentence with one word changed. The changes are a
  word swapped for a near word (`mishear_word`), a name in earshot swapped for another name in earshot (`mishear_word`),
  or a spelled number moved one word up or down (`shift_quantity`). The wrong sentence is worded like a true one. The
  truth goes only to the referee block. Two listeners use it: the listeners that get the full agent view (`around.heard`,
  built by `build_agent_view`, which the TUI and the referee use), and the simple listener in `speech_in.py`, which models
  its own impairment (see Design). LLM residents do not get the full view (see Limits).
- **Shifted quantities.** A written price (Phase 064's `ALE {price} a pint`) is read one unit off by an impaired reader.
  The shift is one unit of the mark's trade (one loaf), up or down, never below one. A spelled number in heard speech
  is shifted the same way.
- **Not built: fear and rage.** The world has no fear or rage state. Body `mood` is the only emotion number, and it is
  not a source.

The switch `IMPAIRMENT.enabled` stays off by default. With it off, the 60-turn simple-backend run matches HEAD on every
field except the label and elapsed time, and the agent views for 13 actors (in `agent` and `referee` mode, so 26 views
per perceiver setting) match HEAD byte for byte.

**Main limit.** LLM residents receive the lazy agent view (`build_lazy_agent_view`, used when a backend sets
`wants_agent_view`, which only `llm.py` does). That view is built from `world.observe` and never calls the perceiver.
So neither the Phase 065 percept distortions nor the mishearing added here reach an LLM resident. See Limits.

## Changes

Whole files (this phase's own; edited in the working tree at their real paths):

- `domains/impairment.py` (Phase 065 module, extended): kinds `utterance` and `quantity`; mechanisms `mishear_word` and
  `shift_quantity`; `APPLIES` (the kinds each mechanism may apply to); `mishear`, `mishear_simple`, `utterance_referee`,
  `quantity_shift`, `quantity_referee`; the ledger gains `by_kind`. The percept functions (`distort`, `referee_extra`,
  `_candidates`) are unchanged in behaviour.
- `domains/impairment_check.py` (Phase 065 self-test, extended): checks each row's mechanisms against `APPLIES`, accepts
  one or more of the four kinds, and checks `IMPAIRMENT.mishearing` and the `NUMERAL_WORDS` order.
- `packs/bigville/world/impairment.json` and `packs/test_hamlet/world/impairment.json` (identical): new `utterance` and
  `quantity` kinds in the DISTORTION rows; `IMPAIRMENT.mishearing` (20 pairs); a new `_doc` paragraph on the mechanisms.
  Both are exporter-canonical. No manifest (`pack.json`) change was needed, because the table is nested in `IMPAIRMENT`.
- `tests/test_phase065b_impairment.py` (new): 19 tests.
- `docs/phases/phase065b/`: this report, `build_clean_tree.py`, `hunks.json`, `logs/`.

Shared files (hunks in `docs/phases/phase065b/hunks.json`, anchored on HEAD `a50406c`; not applied to the working tree,
because `domains/agent_view.py` is being edited by another session and the other two are the same kind of shared file):

1. `domains/reading.py`: import line `from domains import numeracy` gains `impairment`.
2. `domains/reading.py`: `_fill` takes `shift=0` and adds `shift` units of the mark's unit to the price.
3. `domains/reading.py`: `percept` signature gains `shift=0`.
4. `domains/reading.py`: `percept` passes `shift` to both `_fill` calls.
5. `domains/reading.py`: `writing_rows` calls `impairment.quantity_shift` for each mark, passes the shift to the percept
   (the truth is not shifted), and adds `impairment.quantity_referee(shift)` to the referee row.
6. `domains/agent_view.py`, `_around`, the `heard` loop: each heard record's text is `impairment.mishear(...)` when the
   perceiver is on; the referee row (`utterance_referee`) is appended. Off, the text is the record's text.
7. `bigville/backends/speech_in.py`: import `from domains import impairment`.
8. `bigville/backends/speech_in.py`: new function `_heard_as` before `def hear`.
9. `bigville/backends/speech_in.py`, `hear`: the record is passed through `_heard_as` before `understand`.

`build_clean_tree.py` builds `/tmp/t065b` from `git archive HEAD` plus the five whole files and the nine hunks. Each
hunk's old text must occur once, or the build stops. Built: 5 whole files, 9 hunks in 3 files, all anchors matched.

## Design

- **Where a sentence is misheard.** `impairment.mishear` runs on each heard record in `_around` when the perceiver is
  on (`rec` is not None). The listener's sources are the same as for percepts: intoxication, fatigue, illness, darkness.
  A `represented` impairment gets no distortion (the simple backend does not read the agent view).
- **Simple listener (`speech_in.py`).** The simple backend declares impairment `represented`, so the agent-view rule does
  not reach it. Its own impairment is this: when `IMPAIRMENT.enabled` is on and `SPEECH_UNDERSTANDING` is on, `_heard_as`
  applies the same table with the intoxication band from its observations as the only measure. This phase does not read
  the other three measures for it, although its observations carry `energy` and `health`. A misheard record keeps the wrong
  text and drops `raw_data`, so the grammar places the wrong words. Stats: `mishear_checked`, `mishear_distorted`,
  `mishear_<mechanism>`.
- **Draws.** `sha256` of the parts, as in Phase 065. For an agent-view listener the parts are the world seed, the turn,
  the listener, `speech:<speaker>:<record turn>`, and a label (`fire` or `pick`). A simple listener has no world
  reference, so its parts use the fixed seed `simple` in place of the world seed.
- **Which words change.** For a heard text, the candidates are: each name in earshot (whole name, letters and spaces)
  replaced by each other name in earshot; each word in `IMPAIRMENT.mishearing` replaced by each of its near words (case
  kept); each spelled number word from `zero` to `twenty` replaced by the word one step up and one step down. The
  candidates that the active sources' mechanisms allow are listed in order, and one is picked by the draw.
- **Quantities.** `quantity_shift` takes the price in units of the mark's unit (2.0 coins a loaf, so one loaf). The
  draw picks +1 or -1 from the candidates that keep the count at one or more. The reader's percept is the same tier
  template with the shifted price. The referee row keeps `truth` (the figure in coins, as Phase 064 writes it).
- **Ledger.** `note_view` counts each wrong subject once per turn under its kind: `person`, `thing`, `utterance`, or
  `quantity` (a written row's `distortion_kind`). `report_block` adds `by_kind`. `percepts_shown_wrong` is the sum over kinds.
- **Scenario.** The game's `impairment_scenario` controls the agent-view path, as in 065. The simple listener reads the
  pack switch only, because it has no game reference.

## Validation

Commands run from the scratch tree `/tmp/t065b` unless noted. Real-tree checks ran read-only from the repository root.

Build and self-test:
- `python3 docs/phases/phase065b/build_clean_tree.py --out /tmp/t065b`: built, 9 hunks, all anchors matched once.
- `python3 domains/bigville_entities.py` (scratch): exit 0, **ERRORS (0), WARNINGS (0)**. The IMPAIRMENT line: "4 sources
  (intoxication, fatigue, illness, darkness), 4 rows, 5 mechanisms, 20 mishearing pairs, the impairment is off in this pack".
- `python3 domains/bigville_entities.py` (shared working tree, read-only): exit 0, **ERRORS (0), WARNINGS (0)**.
- `python3 -m domains.check --pack bigville` and `--pack test_hamlet` (scratch): exit 0, ERRORS (0), WARNINGS (0) each.
- `tools/export_pack.py --pack bigville --out DIR` and `--pack test_hamlet --out DIR`: both `world/impairment.json`
  files are byte-identical to the scratch tree's copies (and so to the working tree's).

Tests:
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase065b_impairment.py tests/test_phase065_impairment.py`
  (scratch): **37 passed** (19 new, 18 from 065).
- The same new file on the shared working tree, where the hunks are not applied: **5 failed, 14 passed**. The five are
  the price shift, the written-price reading, the ledger, the agent-view heard path, and the simple listener hook.
  They need hunks 2 to 9. The 14 that pass do not depend on them.
- Focused run (`logs/focused.txt`, scratch, before the message fix below): tests 052, 053, 054 (both), 060, 061, 062,
  062b, 064, 065, 065b, and `test_bigville_backends.py`: **284 passed, 3 skipped, 2 failed**. The failures:
  - `test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears`: fails on
    pristine HEAD too (`tests/test_phase060_speech_in.py:377`, `assert 0 > 0` where `totals` is `{}`). Run alone on
    `/tmp/h065b` (`git archive HEAD`): **1 failed**. Not caused by this phase; not investigated further.
  - `test_phase065_impairment.py::test_self_test_finds_a_neighbour_stage_for_a_thing`: my first wording of the new
    self-test error dropped the phrase "applies to a person, not a thing" that this test asserts. Fixed in
    `impairment_check.py` by keeping that phrase. No test was changed. The 065 file was rerun: 18 passed.
- Full bare suite, `python3 -m pytest -q -p no:cacheprovider -rfE` in `/tmp/t065b` (log `logs/full_suite_scratch.log`, exit
  status `logs/status_full.txt`): **5 failed, 2926 passed, 6 skipped** in 2050 s. The five failures all reproduce on
  pristine HEAD (`/tmp/h065b`, `git archive HEAD`), and none is in the switch-off path of this phase:
  - `test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears`: HEAD, 1 failed,
    same assertion (`assert 0 > 0`, `totals` is `{}`).
  - `test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns`: HEAD, same message
    (hunger means differ at index 7: `0.116 != 0.1159`).
  - `test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds`: HEAD,
    same message (`sharing["transfers"]` is 0, expected 1).
  - `test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]`: HEAD, same digest mismatch.
  - `tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world`: HEAD, fails too, with a
    different value (`[5, 1] == [2, 2]` on HEAD, `[2, 2] == [4, 2]` in the scratch run). A timing-dependent browser check,
    in the class the brief lists as flaky under load.
  The Ocelot files are untracked, so the scratch tree does not collect them; the TUI and asset-manifest tests passed, and the
  `test_phase055_concurrency.py` speed test passed in this run.

Behaviour (Phase 058 harness, 100 residents, simple backend, seed 305000, `PYTHONHASHSEED=0`, 60 turns):

| Run | Tree | Switch | Utterances | Action counts | Hunger mean (end) | Compared with HEAD |
|---|---|---|---|---|---|---|
| head60 | `git archive HEAD` (`/tmp/h065b`) | none | 285 | eat 5, move 3536, none 1056, rest 1333, sleep 55, work 15 | 0.4452 | reference |
| t065b_off60 | `/tmp/t065b` | pack defaults (off) | 285 | same | 0.4452 | identical on every field except `label` and `elapsed_seconds` |

Files: `logs/behaviour_head60.json`, `logs/behaviour_t065b_off60.json`. The simple listener does not run speech with the
switch on in this harness, so the mishearing path is not exercised by this run.

Agent views (switches off, and perceiver on): 12 residents plus the player, in `agent` and `referee` mode, at turn 0 of
seed 305000. The md5 of each view (sorted JSON) is identical between `/tmp/h065b` and `/tmp/t065b`, with the
perceiver off and with it on (26 lines each). The check script is in `/tmp` and not in the repository.

Not run: an LLM or human village with the switch on; any run with speech and impairment both on in a village; the
100-resident run beyond 60 turns; any timing.

## Limits

- **LLM residents do not get any of it.** `build_lazy_agent_view` (the view for backends with `wants_agent_view`, only
  `llm.py`) reads `world.observe(actor)`, which has no perceiver record. The heard loop in the lazy view, and its people
  and things, are not changed. Phase 065's percept distortion has the same gap, which that phase's report did not state.
  A hunk in the lazy `heard` loop (with a perceiver record built as in `build_agent_view`) would cover the sentence part.
  The people and things part needs the lazy people and things builders to use the perceiver.
- **The simple listener models only intoxication.** This phase reads only the band for it. Fatigue, illness and darkness are
  not applied to its speech, although its observations carry `energy` and `health`. Its draws are not keyed to the world seed
  (no world reference), only to the listener, the turn and the utterance.
- **A count shifts one unit.** The brief's example "one loaf read as a few loaves" is not what a unit shift gives: for the
  tally tier 'one loaf' becomes 'two loaves'. 'A few' appears only when the shifted count passes `exact_max` (3 for the
  tally tier). Written counts are not in the pack; the only written count is the ale price. Carried goods keep their
  amount words.
- **Names.** A name in earshot is matched as a whole name of letters and single spaces. Ids with digits or underscores
  are not names, so they are never swapped.
- **Ledger coverage.** The simple listener's mishearing counts sit in its speech stats (`speech_in.stats`), not in the
  game report's impairment ledger. The ledger matches an action to a subject by `params["target"]`, as in Phase 065.
- **Rates and pairs are APPROX or authored.** The rates are those of Phase 065. The 20 `IMPAIRMENT.mishearing` pairs are
  homophones or near-sounding words chosen by hand, not counted from a corpus.
- **Fear and rage** are not built (no state in the world).
- **Hunks are not in the working tree.** The shared-tree working copies of `reading.py`, `agent_view.py` and
  `speech_in.py` are unchanged. The supervisor applies `hunks.json` to HEAD to land them. Until then five tests in
  `tests/test_phase065b_impairment.py` fail on the shared tree (see Validation).
- **Pre-existing failures.** The full suite has five failures, all reproduced on pristine HEAD (see Validation). Their
  cause is not this phase's. One of them, the Phase 060 village-run test, is the same test that fails on HEAD alone.

## Open questions

1. Should the LLM's lazy view get the impairment? That decides whether impairment reaches LLM residents at all. The hunk is
   small for speech, larger for people and things.
2. Should the simple listener's draws use the world seed? That needs the seed on the decision context (a `game.py` hunk),
   or a seed passed to the backend.
3. Is a unit shift right, or should a shift cross a tier boundary (for example one loaf to "a few" for the tally tier)?
4. Should the simple listener's mishearing count in the game report ledger?
5. Should `IMPAIRMENT.mishearing` move to its own table in `pack.json` once the manifests are clean? That would add a
   manifest hunk for both packs.
6. Is it acceptable that a misheard simple-listener record loses its raw payload? The grammar then places the words, which
   is the realistic result of mishearing, but it is a choice.
