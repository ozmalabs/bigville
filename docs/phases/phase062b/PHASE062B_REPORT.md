# Phase 062B: the perceiver reads the Phase 063 marks; "a elder" fixed

## Summary

The perceiver's mark gate now reads Phase 063's marks. Before this phase, `domains/perceiver.py` looked for a world method
`visible_marks(actor)` that does not exist, so the dirt tier and the coal-dust tier could not be reached in a real run.
The mark gate now reads what the world shows the observer: `world.observable_marks(actor, distance, light)`, which
applies each mark's see_range, see_light and visible_level. The observer's `notice_skill` check and the perceiver's own
threshold (`mark_min_level`, 0.5) are applied on top. The truth (referee block only) reads the subject's true marks
from `world.marks(actor)`.

The stage noun `elder` is now `senior`, so the tier words read "a senior". The self-test now refuses a stage noun that
starts with a vowel.

With `PERCEPTION.enabled` off (the pack default), the simple backend's 60-turn run and the agent views match HEAD.

Reachability, from real world actions (not scripted marks):
- A smith who smelts iron twice carries soot 0.6 and is described as "a grown person covered in coal dust" when
  the observer is one cell away in daylight.
- One smelt leaves soot 0.3. The world shows it, but the perceiver's 0.5 threshold does not describe it.
- The founding town has no collier. The "collier" role exists only in the burn recipe; a test resident with that role
  burns charcoal (soot 0.5, exactly the threshold), and the coal-dust tier is reached right after the burn.

## Changes

Files changed or created (all in this phase's write scope):

1. `domains/perceiver.py` (clean on HEAD; the whole file is this phase's version):
   - Module docstring: the mark paragraph now says what the gate reads.
   - `visible_marks(game, subject)` is renamed `subject_marks`. It reads the world's `visible_marks(actor)` when a test
     has scripted one (the hook the Phase 062 test uses), otherwise `world.marks(actor)`. No other caller exists.
   - New `_seen_marks(subject, ctx, pack)`: calls `subject["observe"](distance, light)` (the world's visibility rule) and
     drops any row whose `notice_skill` the observer lacks (level below `notice_min_level`, unless the observer's skills
     are represented). A subject without `observe` (built by hand in tests) shows its `marks` as given.
   - `person_subject`: adds `"observe"` (a closure over `world.observable_marks(other, ...)`) and takes `marks` from
     `subject_marks`.
   - `_passes`, the `mark` branch: the perceived side reads `_seen_marks`; the truth side reads `subject["marks"]`.
2. `packs/bigville/world/perception.json` and `packs/test_hamlet/world/perception.json` (identical; both match
   `tools/export_pack.py` output byte for byte):
   - `PERCEPTION.light_level` (new): `{day: 1.0, dim: 0.5, lamplight: 0.5, dark: 0.0}`. APPROX (see Design).
   - `PERCEPTION.notice_min_level` (new): 0.5, APPROX, the same authored level as `trade_min_level`.
   - `PERCEPTION.stage_nouns.elder`: `"elder"` becomes `"senior"`.
   - `_doc`: the mark gate, the APPROX note, and the hand-off text.
3. `domains/perception_check.py`:
   - `_check_light_levels` (new, called from `check_perception`): the keys are the LIGHTS; `dark` is below every MARKS
     `see_light`; each other light is at or above all of them. Checked only when the pack has marks.
   - `notice_min_level` joins the threshold check.
   - `_check_articles` (new, called from `_check_stages`): no stage noun starts with a vowel.
   - `_check_marks_named` (new, called from `check_perception`): each mark gate names a MARKS kind (only when the pack has
     marks).
   - Module docstring lists the new checks.
4. `tests/test_phase062b_perceiver_marks.py` (new, 14 tests). Real world actions: a smith smelting twice, a smith
   smelting once, a collier burning charcoal (the decay case). Also: the world's distance and light rules, the
   notice_skill gate, hand-built subjects, every stage noun, `elder` as "a senior", and the new self-test checks.
5. `docs/phases/phase062b/`: this report; `build_clean_tree.py` (builds `git archive HEAD` with this phase's five files
   and lists the hunks by anchor with `--list`); `behaviour_head60.json` and `behaviour_t62b_off60.json`; `logs/`.

Not changed: `domains/agent_view.py`, `worlds/bigville_world.py`, the MARKS table, the recipes and shocks, the
`pack.json` manifests (the `PERCEPTION` and `PERCEIVER_TIERS` entries from Phase 062 already name `world/perception.json`),
`domains/impairment.py` and the other Phase 065 files, the backends.

### Existing tests

No assertion was edited and no number was changed. `tests/test_phase062_perceiver.py` and `tests/test_phase063_marks.py`
pass unmodified (25 and 18 tests). The Phase 062 test that scripts `world.visible_marks` still passes because the hook is
still read (for the truth).

## Design

### Which marks the mark gate reads

The two gate sets could disagree, so I chose one source. The perceiver's own gates are the observer's distance band
(`near`, 2 cells), the light, the intoxication band, and the notice skill. The world's gates are each mark's see_range,
see_light and visible_level. I used `world.observable_marks` for what is seen, and I kept the perceiver's
`mark_min_level` on top of it. I rejected the other two options:

- Reading `world.marks` and applying only the perceiver's gates would describe a dirt mark at 2 cells. The world says
  dirt is seen only within 1 cell (see_range 1), so the perceiver would describe what the world hides.
- Reading `observable_marks` for the truth would make the truth depend on the observer. The truth is what is there, so it
  reads `world.marks`.

The effective result: a mark is described only when the world shows it to this observer (distance, light, visible_level,
notice_skill) and its level is at least `mark_min_level`. `mark_min_level` is stricter than visible_level for dirt
(0.2) and soot (0.3). The perceiver therefore describes fewer marks than are visible, but never one the world hides.

### Light

`observable_marks` takes a light number and the perceiver takes a light key. `PERCEPTION.light_level` maps the key to a
number. `dark` is 0 and `day` is 1, the scale the MARKS table uses. `dim` and `lamplight` are 0.5 (APPROX, authored, not
measured). The self-test checks that dark is below every see_light and the other lights are at or above all of them, so
the two gates agree about darkness.

### Stage noun

`elder` became `senior`. The tier words are `"a {stage}"`, so a noun that starts with a vowel reads "a elder". Options:
an article rule in `_fill` (a code change), or a different noun. I chose the data fix. The self-test now refuses a vowel
noun. The noun must stay unique because `domains/impairment.py::_noun_key` maps a noun back to its stage. `senior` is
unique, and the impairment keys are the stage names, so nothing else changes.

## Validation

All commands run from the repository root unless noted. The shared working tree has other sessions' edits, so the
results marked "clean" were measured on `/tmp/t062b`, built by `docs/phases/phase062b/build_clean_tree.py --out /tmp/t062b`
(`git archive HEAD` plus this phase's five files). HEAD is `fa47c57`.

- `python3 domains/bigville_entities.py` (shared tree, exit 0): ERRORS (0), WARNINGS (0). The PERCEPTION line:
  "2 kinds (person, thing), 7 tiers, the perceiver is off in this pack". Log: `logs/selftest_shared.log`.
- `python3 domains/bigville_entities.py` (clean tree, `/tmp/t062b`, exit 0): ERRORS (0), WARNINGS (0). Log:
  `logs/selftest_clean.log`.
- `export_pack.py --pack bigville` and `--pack test_hamlet` to `/tmp`: both `world/perception.json` files byte-identical to
  the tree's copies.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase062_perceiver.py tests/test_phase062b_perceiver_marks.py tests/test_phase063_marks.py`
  (shared tree): 57 passed (25 + 14 + 18).
- Focused set on the clean tree (`logs/focused_clean.log`):
  `tests/test_phase052_agent_view.py tests/test_phase054_llm_prompt.py tests/test_phase054_actionable.py
  tests/test_phase062_perceiver.py tests/test_phase062b_perceiver_marks.py tests/test_phase063_marks.py
  tests/test_phase064_reading.py tests/test_phase053_fog.py`: 175 passed (164 s).
- Behaviour, `docs/phases/phase058/measure_behaviour.py --turns 60` (seed 305000, `PYTHONHASHSEED=0`, simple backend for
  all residents, switch off):
  - HEAD (`/tmp/t062b_head`, `git archive HEAD`) and the clean tree (`/tmp/t062b`): action counts
    `{eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15}`, utterances 285, hunger mean at the end 0.4442,
    deaths 0, relationships on record 845, and per-resident digests, sample sequences and the hunger-by-turn trace all
    equal. Compared in Python over every key except `label` and `elapsed_seconds`.
- Agent views, switch off: `agent_view_compare.py` (run from each tree root; it prints one hash over 10 views of the
  player and four residents, agent and referee modes). HEAD and the clean tree print the same hash
  `2f658fcc5cfbaccac5be359e1065a836ea83bbcf72096ec2ef45999ee75f6d8d`.
- Reachability, from world actions: the smith test (`smelt_iron`, 2 completions, ore and charcoal in stock) and the
  collier test (`burn_charcoal`) in `tests/test_phase062b_perceiver_marks.py`. These run the world's own ticks.
- Full suite on the clean tree: see "Full suite" below.

### Full suite

`timeout 5400 python3 -m pytest -q -p no:cacheprovider -rfE` on the clean tree (`logs/full_suite_clean.log`, 3997 s):
**2 failed, 2205 passed, 5 skipped.**

- `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`:
  the known timing flake. Concurrent time 15.02 s against sequential 17.97 s (ratio 0.84; the test needs under 0.75).
- `tests/management/test_backends_browser.py::test_ui_previews_launches_and_reports_server_profile_assignments_without_secrets`:
  not on the known-flake list, and it is not caused by this phase. It fails on HEAD (`git archive HEAD`) too, and it is
  not deterministic. Standalone, it failed on HEAD in 5 of 6 runs and on the clean tree in 4 of 6 (the clean tree's
  failure in the suite was `assert {'Ben'} == {'Ada', 'Ben'}`; HEAD's standalone failures were `assert set() == {'Ada', 'Ben'}`).
  The test checks server profile assignments in the management UI. This phase touches no code on that path.
- Phase 065 (`tests/test_phase065_impairment.py`, shared tree, read only): 18 passed, after this phase's stage-noun change.

The run covered 2212 tests (2 failed, 2205 passed, 5 skipped). The shared tree was not used for the suite.

## Limits

- Values are APPROX, copied from the existing tables: `light_level` (dim and lamplight 0.5), `notice_min_level` (0.5),
  `mark_min_level` (0.5), and every MARKS number. None is measured.
- The founding town has no collier (the role counts in the town100 cast: 2 smiths, no collier). The collier test uses a
  role the town does not have. A collier role also has no `JOBS` entry, so the trade tier ("collier, judging by the
  work") can never be reached for it.
- Coal-dust tier timing, from the MARKS numbers (arithmetic, not run in a village): the burn leaves 0.5, one period of decay
  (0.03) takes it under 0.5, so the tier lasts only until the next period tick. Two smelts (0.6) keep the smith above 0.5
  for about three periods without rain.
- Dirt (tier 2) needs 0.5, and the single jobs that leave dirt leave 0.3 (dig_ore) or 0.1 to 0.3 (grave, compost). It needs
  several jobs to show. Not tested.
- Only the mark tiers and the notice gate were changed. Literacy, impairment and the other Phase 064 and 065 readings are
  untouched.
- The world's `observable_marks` hides a mark by distance and light; the perceiver's `near` band (2 cells) is wider than
  the soot and dirt see_range (1 cell). The effect is that soot is seen only within 1 cell, not 2.
- The 100-resident village was not run with the switch on. The switch-on probe at turn 0 showed no marks, because no
  resident has worked yet.

## Open questions

1. `senior` or another consonant noun for elder? The lexicon's self-description uses "an elder" (`lexicon.json`,
   `LIFE_STAGES` self words). An article rule in the perceiver would allow "an elder" in the tiers. That is a code change.
2. Should `mark_min_level` be lower for dirt and soot, so one job shows them? I kept the authored 0.5.
3. Should a collier role get a `JOBS` entry, so the trade tier can be reached for the charcoal burner? That touches
   `domains/shared_frames.py` and the population, not this phase.
