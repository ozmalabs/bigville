# Ocelot snapshot merge note

Source: branch `wip/worktree-snapshot-20261109` (c202474). Target: HEAD d8f6fca. The snapshot's versions of shared
files are stale (they revert Phases 046, 071d/e, 062, 065, 054b, 042c, DS03 and the pack manifests), so each file was
three-way merged from its own base: `git merge-file HEAD-file BASE-file SNAPSHOT-file`, never `git diff HEAD SNAPSHOT`.
Nothing was committed or staged. The change set was built and verified in a scratch copy of HEAD.

## Ported

| Piece | Files | Base used | Result |
|---|---|---|---|
| Adapter import reports the real failure; communication capability detected from the resident; `understands_raw_speech` stays False | `bigville/backends/ocelot.py` | 58d15c1 | clean merge |
| Outcome feedback for ordinary major actions (`record_action_outcome(action, applied)` on the actor mind after enact) | `bigville/game.py` | 1cf9864 | clean. HEAD's `_report_take_outcome` (contested take) and `held_board_games` are separate paths; only the main path was missing |
| `resident_plan_from_context`; `"food"` key on container fetch options | `worlds/bigville_world.py` | 1cf9864 | hand-picked two hunks (see not ported) |
| `visual_actions` in the advance result | `bigville/server.py` | 387f46b | clean; HEAD's `_bind_reply`, reaction route and `/api/free` are kept. Only set when `status == "advanced"` |
| Client animates succeeded actions; all living residents are drawn | `bigville/game/game.js` | 2fdfbbb | HEAD's file equals 2fdfbbb, so the snapshot file applies as is. `node --check` passes |
| Decision seed 1.3.0 (hunger utility rules `o0_score_hungry_eat`, `o1_score_hungry_food_fetch`) | `bigville/seeds/bigville_actor_decision.json` | 4cf070a | copied from the snapshot (see seed) |
| Tests | `tests/test_bigville_game_api.py` (+3), `tests/test_bigville_scenarios.py` (+2), `tests/test_bigville_server.py` (visual_actions assert) | 62fd5a6, 58d15c1, e7cbf65 | clean merges; two adjustments below |
| Docs | `README.md`, `docs/AGENT_BACKENDS_PLAN.md` | 7b31559, a7da178 | clean; still accurate against HEAD |
| Untracked Ocelot-stream files (already in the working tree, identical to the snapshot) | `bigville/mixed_ocelot_scenario.py`, `tools/run_mixed_ocelot_{village,scale}.py`, `docs/ocelot-integration-baseline.md`, `docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md`, `tests/test_bigville_ocelot_communication.py`, `tests/test_bigville_ocelot_fresh_process.py`, `tests/test_mixed_ocelot_checkpoint_parity.py`, `tests/test_mixed_ocelot_village.py` | n/a | included; three of the tests were edited (below) |

README links to `docs/ocelot-integration-baseline.md`, so those two must go in together.

### Seed decision
`bigville/seeds/bigville_actor_decision.json` is hand-written (not produced by `tools/generate_seeds.py`; the generated
seed tests exclude it through `PENDING_DECISION`). `docs/FEATURE_PHASES.md` (Phase 017) says it "stays as is until the
other session commits its 1.3.0 work", which is this change. It is not covered by the DS03/DS04 determinism work (DS04
touched `domains/interoception.py` and reports, not seeds). It is not executed in this repo (`settle()` is a no-op), so
it was not run here. The hunger rules read `observed_hunger`, `hunger_eat_weight`, `hunger_fetch_weight`,
`hunger_scored`, which only the external Ocelot adapter publishes; the mixed-village test asserts these never leak into
proposal params. It was ported because it is the pending intended work and `test_phase017_generated_seeds` /
`test_phase014_parameters` pass with it.
Open item for the Ocelot stream: the root copy `seeds/bigville_actor_decision.json` (1.1.0) still has the `-6.0` terrain
stamina term in `oa_choose_option` that the Python mirror `_option_value` implements. Neither `bigville/seeds/` copy
(HEAD 1.0.0 or this 1.3.0) has it, and the Phase 017 note asks for that check. Not changed here.

## Not ported (stale, revert committed work)
- `worlds/bigville_world.py`: removal of `DetrainingMixin` and its hooks (046); `_dn.ACTIONS` check moved after the
  `MAJOR_ACTIONS` check (reverts 042b); `_attending_refusal`/`_dependant_refusal` order (reverts 045/071).
- `bigville/reporting.py` (reverts DS03 `determinism.sample`), `domains/bigville_entities.py`,
  `domains/world_affordances.py`, `domains/detraining*.py`, `worlds/detraining.py`, `tests/test_phase046_detraining.py`,
  `packs/*/pack.json`, `packs/*/world/detraining.json`, the mode changes on `docs/phases/phase045/rebase/run_all.sh` and
  `phase046/run_all.sh`.
- `docs/phases/phase052/full_suite_live_tree_midedit.log` and `.opencode/` (as instructed).

## Conflicts and adjustments
No textual merge conflicts. Adjustments:
1. `tests/test_bigville_game_api.py::test_real_ocelot_village_round_records_perception_choice_and_outcome`: set
   `stamina_reserve` to 0.5 before the step. A rested resident chooses `none`, which sends no major action and so no
   outcome, and the assertion `individual_benefit == 1.0` failed. It fails the same way on the unmodified snapshot
   against the current sibling Ocelot checkout; with the tweak it passes there.
2. `tests/test_mixed_ocelot_village.py`, `tests/test_mixed_ocelot_checkpoint_parity.py`,
   `tests/test_bigville_ocelot_communication.py`: after the existing skip checks they now skip if
   `worlds.bigville_ocelot_adapter` cannot be imported. Bigville's `worlds` is a namespace package; once imported it
   shadows Ocelot's regular `worlds` package inside a bare `pytest` process, so with the sibling `../ocelot` checkout
   present the three tests failed (`ModuleNotFoundError`). Run as the Ocelot doc says (from the Ocelot checkout, Ocelot
   first on `PYTHONPATH`) they execute: 46 passed.

`worlds.bigville_ocelot_adapter` is not in this repo and not in any Bigville git history
(`git log --all -- worlds/bigville_ocelot_adapter.py` is empty). It exists in the sibling checkout
`/home/matt/ozmadev/ocelot/worlds/bigville_ocelot_adapter.py` (its working tree has uncommitted edits) and in several
Ocelot worktrees.

## Verification (scratch copy of HEAD + change set)
- `python3 domains/bigville_entities.py`: ERRORS 0, WARNINGS 0. Packs, seeds-by-generator and exporter output are
  untouched, so `domains.check` and the pack exporter were not rerun.
- `node --check bigville/game/game.js`: ok.
- Focused set (backends, game api, persistence x3, scenarios, server, lazy_llm, 018/031/054/054b/054-prompt/065c/066/
  071/071c x2/071d x2/071e, scenario runner, phase017 seeds, phase014 parameters, the four Ocelot test files): 339 passed
  before the test-skip edit, all green after (bare, no Ocelot: skips clean).
- Against real Ocelot (sibling checkout, run from the Ocelot checkout, Bigville scratch as `BIGVILLE_ROOT`): 46 passed
  for the four Ocelot files, game api, scenarios and server. This exercises the new capability detection, the outcome
  hook, `resident_plan_from_context` and the 1.3.0 seed together.
- 60-turn simple run `PYTHONHASHSEED=0 measure_behaviour.py --label x --turns 60`: identical to HEAD apart from
  `elapsed_seconds` (no behaviour change: no simple mind implements `record_action_outcome`, and the `food` key sits
  after the container branch the cheap policy already takes).
- Full bare suite in the scratch tree (no sibling Ocelot, so the Ocelot tests skip): 5 failed, 3086 passed, 13 skipped
  (34 min). The 5 failures are the known HEAD failures: `test_phase058_persona` 50-turn reference,
  `test_fix_llm_checkpoint` digest[0], `test_package15_resource_social_stress` policy pair, `test_phase060_speech_in`
  village run, and the flaky `management/test_cast_browser` (also fails alone on a HEAD copy). The first four were
  re-run on a HEAD copy and fail identically. None is touched by this change set. HEAD's 3082 passed becomes 3086
  passed (4 new passing tests: 2 game api, 2 scenarios), plus 13 skips from the Ocelot tests.
- In the real working tree the sibling `../ocelot` exists, so `test_bigville_ocelot_fresh_process.py` will run its
  subprocess checks there (they passed in a trial run) and the in-process Ocelot tests skip as described.

## Left for the Ocelot stream
- Implement the speech-ingestion route (`understands_raw_speech` stays False until a resident method is called by the
  ordinary game loop and covered end to end) and a resident `propose_free_text`/`speech_provider` if free text is wanted.
- Resolve the `-6.0` stamina term between `seeds/` and `bigville/seeds/` and decide the root `seeds/` copy.
- Update the Phase 017 text in `docs/FEATURE_PHASES.md` (it still lists the 1.3.0 seed as pending) and
  `PENDING_DECISION` in `tests/test_phase017_generated_seeds.py`; not edited here.
- The upstream Ocelot checkout is dirty; the real-Ocelot results above depend on that state.
