# Phase 054b report: LLM handle normalisation

## Summary

An LLM resident now sees opaque tokens (`hxa`, `hxb`, ... letters only) for every handle in its prompt. The world's
names no longer reach the model: an object's id, an affordance row's `target:N` key, the action/recipe/kind handle of a
row, and a place's `cell:x,y`. The harness keeps the mapping per resident, in order of first appearance, and keeps each
token for the whole run. The model's reply is read back to the handle the view showed before the game sees it.

This closes the leak in docs/phases/phase065c/PHASE065C_REPORT.md (Limits): a wrong percept of an object whose id equals
its kind word now shows neither the id nor the true kind, because the id is a token and the kind is the percept.

The choke point is `LLMBackend._ask` (bigville/backends/llm.py). It is the only place the packet is built for a provider
(`prompt_builder.build` is called only there), and the only provider call that carries an agent view. The speech parser
(`bigville/backends/speech_parser.py`) also calls a provider, with the utterance, the speaker's name, a flag and topic
words; it sends no view and no handle, so it is not changed. The masked context goes to the packet builder, so the prompt, the thread and the log hold tokens. The agent view
(`domains/agent_view.py`) is unchanged, so the TUI, the human path and the tests that read the view keep their readable
handles. Masking in the view builder would have needed the per-resident state there, and the view is also built for the
TUI and Ocelot. The packet builder is the presentation layer for tools too, so the mask stays out of it.

The simple, human and TUI paths do not reach the new code. The 60-turn simple run is identical to HEAD (see Validation).

## Changes

New files:

- `bigville/backends/handle_map.py`: `HandleMap`, one per LLM backend (per resident). `mask_context` (the view with
  its handles replaced), `mask_choices` (reaction options in a consult), `translate` (a reply read back), `referee`
  (token -> world handle for the log), `to_dict` and `restore` (the checkpoint). Constants: `UNKNOWN_HANDLE` (the fixed
  error text), `HANDLE_PARAM_KEYS` (the reply fields that hold a handle), `IDENTITY_FIELDS` (the affordance row fields
  that name what a row acts on).
- `tests/test_phase054b_handles.py`: 24 tests (see Validation).
- `docs/phases/phase054b/build_clean_tree.py`, `hunks.json`, this report, `logs/`.

Shared files, changed only by anchored hunks in `docs/phases/phase054b/hunks.json`. The build applies them to the HEAD text
(`709fde9`), and each `old` block must match exactly once or the build stops. Hunks: 21 in 9 files.

`bigville/backends/llm.py` (8 hunks):

1. import: `from .handle_map import HandleMap` (anchor: `from .prompt_packet import PACKET_SCHEMA`).
2. `LLMBackend.__init__`: `self.handles = HandleMap()` (anchor: `self.log = log` and the `threads` line).
3. `_check`: the reply is read back by `self.handles.translate` before the checks; a `reaction` flag reads the choice too.
   Returns the reply as the provider sent it, as before.
4. `_ask`: `context = self.handles.mask_context(context)` and `choices = self.handles.mask_choices(choices)` before the
   packet is built (anchor: the `record = self.prompt_builder.build(...)` line).
5. `_ask`: `_check(..., reaction=choices is not None)` (anchor: the `self._check(raw, fields, affordances)` line).
6. `_log_attempt`: the record gets `referee.handles`, token -> world handle for the tokens in the call (anchor: the
   `thread_hash` line). The `messages` in the record are unchanged.
7. `to_dict`: `"handles": self.handles.to_dict()` (anchor: the `gate, autopilot, budget` line).
8. `restore_state`: `self.handles.restore(data.get("handles"))` (anchor: the `bucket_day` line).

`bigville/backends/prompt_packet.py` (3 hunks):

9. `PACKET_SCHEMA` = `bigville/prompt/6` (anchor: the `PACKET_SCHEMA` line).
10. Lazy contract, walk: "copy a place handle from public.around.things into major_action.target." The text no longer offers
    `params.destination` as a pair of cell numbers (a coordinate in the prompt).
11. Lazy contract, names: a person by name, a thing by its handle from public.around.things (not "the stable name or id").

Tests whose expectation changed (each listed with its reason):

12. `tests/test_phase031_llm_backend.py::test_callable_provider_is_accepted`: the schema assertion `prompt/5` -> `prompt/6`.
13. `tests/test_bigville_backends.py::test_llm_backend_accepts_provider_json_and_exposes_backend_state`: two schema assertions, `prompt/5` -> `prompt/6`.
14. `tests/test_phase054_llm_prompt.py::test_the_packet_uses_the_packet_schema_and_the_pack_hash`: schema `prompt/5` -> `prompt/6`.
15. `tests/fixtures/phase054_packet_snapshot.json` (used by `test_the_packet_matches_the_snapshot_for_a_fixed_view`): the
    `schema` field `prompt/5` -> `prompt/6`. Nothing else in the snapshot changed: the fixture is a menu-mode packet built
    from a raw view through `PromptBuilder`, which the mask does not touch.
16. `tests/test_phase054_actionable.py::test_every_can_row_of_a_sample_resident_becomes_the_simple_backends_proposal_for_that_row`:
    the scripted reply names each row by the token the consult shows for it (it used to copy the world's handle). The world
    row lookup still uses the world's handle. A reply that copies a world handle is now an error by design.
17. `tests/test_phase054_actionable.py::test_an_llm_resident_replying_with_a_work_row_is_enacted_by_the_world_in_one_turn`:
    the same change: the reply names the work row by its token.

18. `tests/test_phase059_autopilot.py::test_a_reaction_consults_the_model_over_the_offered_options`: the scripted reaction
    names the option by the token the consult shows for it (it used to name the option by its word). A raw option word is
    now refused, so the autopilot's fallback answered instead.
19. `tests/test_phase071c_free_actions.py::test_an_llm_glance_reply_is_enacted_and_shows_the_sound_and_place_in_last`: the
    glance reply names the `signal:1` row by its token (the new helper `_shown_token`, beside `_llm`, reads it from the view
    the consult builds). With the raw handle the reply was refused and repaired, so the provider was called twice, not once.

No other existing test was edited, and no assertion was weakened or deleted.

### How it works

Tokens. A token is `hx` plus letters (`hxa`, `hxb`, ... `hxz`, `hxaa`), numbered per resident in order of first
appearance. Letters, not digits, because the Phase 052 leak guard (`bigville/learning_eval.py`) reports a digit in a
phrase, and handles are checked by that guard. The example `h1` in the brief would carry a digit.

Identity (what a token stands for, kept for the run):

- a thing (`around.things`, including a container and a perceived thing) and a place cell: the world's handle
  (`knife`, `cell:2,1`). Both are stable across turns.
- an affordance row (menu mode, `can`): the row's identity fields (action, object_id, kind, recipe, trade, sow_kind,
  with, container, source, destination, recipient, patient, project, name, animal, land, crop_node, joint), without the
  per-turn `target:N` key. A row keeps its token when its index changes. Rows with the same identity in one view get
  `|2`, `|3` ... (the same rule as `affordance_handles`). Volatile fields (score, legal, reason) are not in the identity.
- a reaction choice (`reaction`): the choice's name. A private row (`self.giveable_notes`, `self.requests`, the Phase
  071d lists): its handle.

Reply. `translate` reads back the fields in `HANDLE_PARAM_KEYS` (`target`, `object_id`, `container`, `source`, `animal`,
`crop_node`, `land`, `project`, `patient`, `destination`, `recipient`, `name`, `joint`, `item`, `note`, and `option` in a
reaction), in `major_action` and in each `free_actions` item. Rules:

- a token this view offered becomes the world handle the view showed (for example `move_object:apple#2`, `cell:2,1`).
  The downstream code (`bind_row`, the lazy cell handling, the world) then sees what it always saw.
- a token that this view did not offer is an error, with the fixed text `UNKNOWN_HANDLE`. The error goes to the repair
  path, which sends only the fixed errors (no id, no token echoed).
- a world handle that the resident was shown in any earlier view is an error too: it must be copied as its token.
- a name (a person's name, a word) is not read back and is not an error. `utterances.to` is a name and is not read.

Log and checkpoint. The call record has `referee.handles` (token -> world handle for the tokens in that call), beside
`messages` (the prompt as sent). `to_dict` and `restore_state` hold the mapping in the LLM backend state, so
`checkpoint_llm_backend` and the game's save and load keep the tokens.

## Validation

All commands ran in the scratch tree `/tmp/t054b`, built by
`python3 docs/phases/phase054b/build_clean_tree.py --out /tmp/t054b` (HEAD `709fde9` plus 2 new files and 21 hunks in 9
files; every anchor matched once). The HEAD baseline is `/tmp/t054b_head` (`--stage head`). Nothing was committed.

- `python3 domains/bigville_entities.py` (in the scratch tree): exit 0, **ERRORS (0), WARNINGS (0)**. Log:
  `logs/selftest.log`.
- `python3 -m domains.check --pack bigville` and `--pack test_hamlet`: exit 0 each. Logs: `logs/check_bigville.log`,
  `logs/check_hamlet.log`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase054b_handles.py`: **24 passed**. With the two test hunks of
  items 18 and 19, the two changed tests also pass (26 passed across the three files).
- Mutation check, to show the leak tests bite: the same tree with the `mask_context` line removed in `llm.py`:
  **10 failed, 14 passed**. The failures are the four prompt-opacity cases, the view-API test, the wrong-percept leak test,
  the stable-token test, the lazy place read-back, the stale-token test and the log test. The test file cannot be collected on
  HEAD (no `handle_map` module).
- Focused LLM set, scratch tree, run before the private-list masking (new code that runs only when a view carries
  `self.giveable_notes` or `self.requests`) and before two later tests were added. Log: `logs/focused_llm_set.log`.
  The full suite below supersedes it. Command:
  `tests/test_phase031*.py tests/test_phase052*.py tests/test_phase054*.py tests/test_phase062*.py tests/test_phase064*.py
  tests/test_phase065*.py tests/test_phase066*.py tests/test_lazy_llm.py tests/test_bigville_backends.py
  tests/test_fix_llm_checkpoint.py tests/test_phase018_llm_instructions.py`: **290 passed, 1 failed**
  (`test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]`, a known HEAD failure).
- The known HEAD failure `[0]` on HEAD: the same assertion fails with the same digests (`c592d878...` and `718060fe...`).
  That case has zero LLM residents, so no prompt is involved. The change does not affect it.
- 60-turn simple run, `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label final60 --turns 60 --out ...`,
  HEAD (`/tmp/t054b_head`) and the final scratch tree: the two JSON files are identical after removing `label` and
  `elapsed_seconds`. Logs: `logs/measure_head60.json` and `logs/measure_final60.json`. The run on the final tree also
  reported 100 residents alive, 0 deaths, 285 utterances and the same action counts as HEAD.
- Phase 052 guard: `bigville/learning_eval.guard_log` over a 6-turn lazy log with PERCEPTION and IMPAIRMENT on:
  27 prompts checked, 0 violations, not void (`logs/guard_log_check.txt`).
- The masked prompt of one lazy consult: `logs/example_masked_prompt.txt` (its first line is the packet's
  `around.things`, and the last line is the referee-side label map, which is not sent).

- Full bare suite, scratch tree: `python3 -m pytest -q -p no:cacheprovider -rfE` (log `logs/full_suite_final.log`):
  **5 failed, 3033 passed, 6 skipped** in 1991 s. The five failures are the known HEAD failures, and each one has the same
  assertion message on HEAD (`/tmp/t054b_head`, the same five tests: `logs/head_known_failures_on_head.log`):

  | test | on HEAD | on the 054b tree |
  |---|---|---|
  | `tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world` (flaky, per the brief) | fails, `assert [1, 2] == [2, 2]` | fails, same |
  | `tests/test_fix_llm_checkpoint.py::...continues_to_the_same_run_digest[0]` (zero LLM residents) | fails, digest `c592d878...` vs `718060fe...` | fails, same |
  | `tests/test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds` | fails, `assert 0 == 1` | fails, same |
  | `tests/test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns` | fails, hunger list at index 7 | fails, same |
  | `tests/test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears` | fails, `assert 0 > 0` (`heard`) | fails, same |

- The first full run (`logs/full_suite_first_run.log`) had 7 failures: those five, plus two expectation failures that
  were caused by this change: `test_phase059_autopilot::test_a_reaction_consults_the_model_over_the_offered_options` and
  `test_phase071c_free_actions::test_an_llm_glance_reply_is_enacted_and_shows_the_sound_and_place_in_last`. Both replies
  named a world handle the view had shown. They are now the listed test changes 18 and 19, and the run above is the one
  after those changes.

## Limits

- Masked: things, cells, affordance rows (menu mode), reaction choices, and the private note and request rows of
  Phase 071d. Not masked: kind and recipe words in `what` and in `self.knows`, memory text, and any text the world writes
  into a note. A note written by the world that carries a world id would reach the prompt.
- `_lazy_things` takes an object's words from `kind`, then `name`, then its id. An object with neither a kind nor a
  name would show its id as words. The test packs' objects have kinds; I did not audit every pack.
- A menu row's identity uses its identity fields. A row whose only key is a `target:N` index has no stable field and
  falls back to the `|N` order. Its token can then change when the list order changes. I did not audit each of the world's
  target-key sites.
- The mapping grows with every thing, cell and row the resident is shown, and it is never pruned. The checkpoint grows
  with it. Not measured on the 100-resident town.
- A saved game from before Phase 054b has no mapping: its threads hold the world's handles, and the restored backend
  starts an empty map. Those old handles in a reply are then unknown and go to the world, as they did before.
- A reply may still give a coordinate pair as `params.destination` (the lazy move path accepts it). The prompt no longer
  offers it.
- The pack's interface line still names the format `signal:N` (the attend rows, Phase 071). That is a format, not a
  value, and the rows are human-only. Changing it means editing `packs/*/world/prompt_packet.json`, so I left it.
- Not run: an LLM village with PERCEPTION on, the 100-resident run, any timing or prompt size with the switch on.

## Open questions

1. **Phase 071d overlap (uncommitted, same shared files).** The working tree has Phase 071d changes to
   `bigville/backends/prompt_packet.py`, `llm.py`, `reply_schema.py`, the two `prompt_packet.json` packs and the
   same test lines I hunk (`test_phase031`, `test_bigville_backends`, `test_phase054_llm_prompt`). 071d also sets
   `PACKET_SCHEMA` to `bigville/prompt/6`. Both phases cannot use `/6`. If 071d lands first, this phase must take `/7`, and
   its hunks must be re-anchored on that HEAD. The build stops on a mismatch, so a stale anchor cannot slip through. The
   masking of `giveable_notes` and `requests` is in place, but it was checked only on a synthetic view, not on 071d's packet.
2. Should the pack's `signal:N` format line be rewritten so the prompt never shows a handle format?
3. Should the mapping be pruned (a token unused for N turns) to bound the checkpoint, or kept for the run as the brief asks?
   This phase keeps it for the run.
