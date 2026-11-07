# Phase 062 report: the perceiver (faculties, tiers, adapter)

## Summary

The agent view now describes each person and thing in sight by the highest tier the resident's perception meets.
A tier is a template over lexicon words with a gate: the light the resident sees by, the distance band, the
intoxication band, the resident's skill in the subject's trade, and a visible mark on the subject. With
`PERCEPTION.enabled` off (the pack default), the view is what it was at HEAD and the simple backend's 60-turn run
is identical to HEAD. With the switch on, the LLM, the TUI and human residents get the tiered descriptions. The
simple backend never reads the agent view, so its run does not change either way.

Two limits shape what the phase delivers:
- Visible marks come from Phase 063, which is not built. In the real world no mark is visible, so the two mark
  tiers (a dirty person, a person covered in coal dust) are reached only in tests, with marks scripted through
  `world.visible_marks(actor)`.
- Residents have no sex fact, so the brief's "a man" tier is "a child", "a youth", "a grown person" or "an elder",
  chosen from the life stage the world holds.

## Changes

New files:
- `domains/perceiver.py`: the perceiver record (`record`), the faculty declaration (`declared`), the subject facts
  (`person_subject`, `thing_subject`, `visible_marks`), the tier choice (`percept`, `_passes`, `_pick`), and the
  referee row helpers (`referee_row`, `summary`).
- `domains/perception_check.py`: the self-test for the two tables (`check_perception`).
- `packs/bigville/world/perception.json` and `packs/test_hamlet/world/perception.json` (identical; the exporter's
  canonical form, checked with `tools/export_pack.py`): tables `PERCEPTION` (switch, faculties, fallback, light
  when day and night is off, distance bands, mark and trade thresholds, stage words, gate vocabulary with the side
  each gate reads) and `PERCEIVER_TIERS` (tiers for `person` and `thing`).
- `tests/test_phase062_perceiver.py`: 25 tests.
- `docs/phases/phase062/`: this report; `build_clean_tree.py` (builds `git archive HEAD` plus this phase's files
  and hunks, for measurement); `measure_perception.py` (Phase 058 run with the switch forced on or off);
  `behaviour_head60.json`, `behaviour_t2_off60.json`, `behaviour_t2_on60.json`; `logs/`.

Modified or shared files. `domains/agent_view.py` had no other session's edits, so it is my whole change. The
others are anchored hunks:
1. `domains/agent_view.py` (whole file, mine): `build_agent_view` builds the perceiver record when the switch is on,
   passes it to `_around` (people) and `_things`, withholds the options that act on a tier-0 thing (`_can`), and adds
   `referee.perception` (faculties, perceiver numbers, and every subject's percept beside its truth) in referee mode.
   Off, the record is `None` and no output changes. The whitelist (`AGENT_VIEW_WHITELIST`) is not changed: the new
   keys are the existing `person` and `thing` keys, and the referee block is a `referee` key the whitelist already has.
2. `packs/bigville/pack.json`: at the end of `tables`, after the `SPEECH_PARSER` entry (working-tree form, one entry
   per line): add a comma, then `{"name": "PERCEPTION", "file": "world/perception.json"}` and
   `{"name": "PERCEIVER_TIERS", "file": "world/perception.json"}`.
3. `packs/test_hamlet/pack.json`: the same two entries at the same place.
4. `domains/bigville_entities.py`, in `check_consistency`: after the `check_speech_parser(_WORLD_PACK.path, errors,
   warnings, info)` call, two lines: `from domains.perception_check import check_perception` and
   `check_perception(_WORLD_PACK.path, errors, warnings, info)`. In a HEAD tree, `build_clean_tree.py` anchors after
   `check_speech_acts(...)` instead, because HEAD has no `check_speech_parser`.
5. `bigville/backends/cheap.py`, class `DeterministicBackend`, after `requires_conversational_interface = True`: a
   comment and the class attribute `faculties` (all five faculties `represented`).
6. `bigville/backends/llm.py`, class `LLMBackend`, after `wants_agent_view = True`: a comment and `faculties` (all
   `enforced`).
7. `bigville/backends/human.py`, class `HumanBackend`, after `fogged = True`: a comment and `faculties` (all
   `enforced`).

The clean tree (`build_clean_tree.py`) reproduces the phase on HEAD (71e446a): the same six patched files with
hunks 2 to 7 applied to the HEAD text, and `agent_view.py` and the new files copied whole.

## Design

- **Perceiver record.** `light` from `worlds.daynight.view_light` (`day`, `dim`, `dark`, `lamplight`); when day and
  night is off it is `PERCEPTION.light_when_off` (`day`) and `light_known` is false. `sight` is `HEARING.sight_range`
  narrowed by `daynight.sight_range` in the dark. `band` is the intoxication band. `skills` are the resident's skill
  levels. `literacy` is the reading tier (recorded for Phase 064).
- **Tiers.** Person: 0 "a person" (no gate); 1 "a {stage}" (some light); 2 "a dirty {stage}" (mark `dirt`, near);
  3 "a {stage} covered in coal dust" (mark `soot`, near, some light); 4 "{job}, judging by the work" (some light,
  band no higher than tipsy, and skill at least 0.5 in a main skill of the subject's trades). Thing: 0 "something"
  (no handle, so it cannot be named in a reply); 1 "{kind}" (some light).
- **Gates.** `light_not`, `distance`, `band_max`, `trade_skill` read the observer. `mark` reads the subject. The
  highest tier whose gates all pass is the percept.
- **Truth.** The highest tier whose subject-side facts hold: the mark, and whether the subject has a trade. The light,
  distance and intoxication are ignored, so the truth is what is there for an observer with every faculty.
- **Faculties.** A `represented` faculty is replaced by its full value in the record (full light, sober, all trades
  recognised, the sight range without the dark). An `enforced` or `both` faculty keeps the observer's own value. The
  simple backend declares all `represented`, the LLM and human backends all `enforced`. Literacy and numeracy are
  recorded and declared but nothing reads them yet (Phases 064 and 065).
- **Known people.** A known resident keeps its name, job and tie only at tier 1 or above. At tier 0 it is "a person".
  Looks are shown only at tier 1 or above. A stranger is described by its percept; the old "a stranger (job)" wording
  is not used when the switch is on, and a stranger's job appears only at tier 4.

## Validation

Commands run in the working tree unless noted. The tree is shared, so the isolated `/tmp/t062` tree (HEAD plus this
phase, from `build_clean_tree.py`) is the reference for the phase's own result.

- `python3 domains/bigville_entities.py` (working tree): exit 0, ERRORS (0), WARNINGS (0). The info line:
  "PERCEPTION: 2 kinds (person, thing), 7 tiers, the perceiver is off in this pack".
- `python3 domains/bigville_entities.py` on the clean tree `/tmp/t062`: exit 0, ERRORS (0), WARNINGS (0).
- `check_perception` on `packs/bigville` and `packs/test_hamlet`: 0 errors, 0 warnings.
- `tools/export_pack.py --pack bigville` and `--pack test_hamlet`: both `world/perception.json` files byte-identical
  to the copies in the tree.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase062_perceiver.py`: 25 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase052_agent_view.py tests/test_phase053_fog.py
  tests/test_phase054_llm_prompt.py tests/test_phase054_actionable.py tests/test_phase042_daynight.py
  tests/test_phase060_speech_in.py tests/test_phase062_perceiver.py tests/test_bigville_backends.py
  tests/test_phase031_llm_backend.py tests/test_phase059_autopilot.py`: 282 passed, 3 skipped (159 s). This ran
  before the last two small edits (the thing-distance guard and the `referee_row` signature); the full suite below covers the final code.
- The same two perceiver and agent-view test files on `/tmp/t062`: 51 passed.
- Full suite (working tree): 8 failed, 2151 passed, 6 skipped; see "Full suite" below.
- Behaviour, Phase 058 harness, 100 residents, 60 turns, seed 305000, `PYTHONHASHSEED=0`, simple backend for all:

| Run | Tree | Switch | Utterances | Action counts | Hunger mean (end) | Residents with a different action sequence vs HEAD |
|---|---|---|---|---|---|---|
| head60 | `git archive HEAD` (71e446a) | none | 285 | eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15 | 0.4442 | reference |
| t2_off60 | `/tmp/t062` | off (pack default) | 285 | same | 0.4442 | 0 of 100 |
| t2_on60 | `/tmp/t062` | on (forced) | 285 | same | 0.4442 | 0 of 100 |

  The per-turn hunger trace and the five sampled sequences match too. The off run's digests and counts are the
  same as HEAD's; the trace comparison was made in Python from the JSON files.

Not run: an LLM or TUI village with the switch on (no provider, and the brief does not ask for one), and the
100-resident run with the switch on for longer than 60 turns.

### Full suite

Working tree, `timeout 6000 python3 -m pytest -q -p no:cacheprovider -rfE` (log: `logs/full_suite_working_tree.log`):
**8 failed, 2151 passed, 6 skipped** in 3073 s.

The 8 failures, with attribution:
- Three Ocelot tests (`test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`) fail with
  `No module named 'worlds.bigville_ocelot_adapter'`. Those test files are untracked in the working tree, so they are not
  in HEAD or in the clean tree. Not this phase.
- Four `tests/test_phase057_tui.py` HTTP tests. On `git archive HEAD` (`/tmp/headonly062`) all 49 tests of that file pass
  with the concurrency file's speed test failing (below). On the clean phase tree `/tmp/t062` the file passes (49 passed,
  including the concurrency test). The failures come from other sessions' uncommitted edits in the working tree
  (e.g. `bigville/server.py`), not this phase.
- `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`:
  a timing check that asserts concurrent time under 0.75 of sequential time (ratio 0.79 on HEAD
  under load, 10.16 s sequential and 8.00 s concurrent). It passes on `/tmp/t062`. Flaky under load, not related to this phase.

The asset-manifest test (`test_bigville_server.py`) passed in this run; the brief listed it as a known failure.

A first run in the working tree was stopped by my own 50-minute `timeout` at about 95%, with no summary
(`logs/full_suite_working_tree_killed_at_50min.log`). The run above replaces it.

## Limits

- **No marks in the world.** Phase 063 supplies them. Until then, the tiers 2 and 3 and their truths are tested only
  with scripted `visible_marks`.
- **No sex fact.** The brief's "a man" tier is not possible; the tier uses life stage words.
- **Map occupants.** The agent map (`_map`) shows terrain only, and the fogged map of Phase 053 is in `map_memory`
  (outside this phase's write scope). Occupants of the map are not perceived, so nothing changes there.
- **Literacy and numeracy.** Declared and recorded; no percept reads them. Phase 064 does that.
- **Impairment.** Only the intoxication band gate on the trade tier. There is no distortion, which Phase 065 covers.
- **`can` filter.** An affordance is dropped when its `target` names a thing the resident cannot see. The sampled town
  has no affordance with an object target, so this path is exercised only by a test that adds an option.
- **Thing distance.** Physical objects take their distance from `world._physical_location_cell` (a private method),
  so the view reads one more world helper. Objects with no cell count as at hand (distance 0).
- **Light.** With day and night off, the light is `day` by default and `now.light` stays absent, as before. The
  record says `light_known: false`.
- **Distance band.** `near` = 2 cells is APPROX: an authored conversational distance, not measured.
- **Thresholds.** `mark_min_level` and `trade_min_level` (0.5) are authored, on the 0..1 scales the world uses.
- **Simple backend.** Its faculties are declared `represented`, but the perceiver never runs for it, since it reads
  its own `ActorContext`. Its byte-identity is shown by the runs above, not by a separate code path.
- **Speed.** The perceiver adds one `percept` call per person in sight and per object in view. Not timed.

## Open questions

1. A sex or gender fact for residents, to allow "a man" and "a woman" as in the brief. Is it in scope for Phase 063?
2. Should a stranger's job show at tier 1 (as a known resident's does) or only at tier 4 (as built)?
3. The `can` filter assumes an affordance's `target` is the thing's id. Phase 063 or 064 should confirm that when
   objects get options.
4. Should `thing distance` come from a public world method rather than `_physical_location_cell`?
5. The brief's order runs 062 before 064. Literacy and numeracy are recorded here; should Phase 064 read the record
   or add its own?
