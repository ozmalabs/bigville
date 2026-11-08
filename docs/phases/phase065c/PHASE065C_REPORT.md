# Phase 065c report: perception effects reach an LLM resident's prompt

## Summary

An LLM resident's prompt is built from the lazy agent view (`build_lazy_agent_view`, used because the LLM backend sets
`wants_agent_view`). That view reads `world.observe` and never called the perceiver. So with PERCEPTION on, the person and
thing percepts (062), written marks (064), wrong percepts (065) and mishearing (065b) did not reach the prompt.

With PERCEPTION on, the lazy view now takes its `people`, `things`, `heard` and `writing` from the same helpers the full
view uses (`agent_view._around`: `perceiver.percept`, `impairment.distort`, `impairment.mishear`, `reading.writing_rows`).
The lazy view keeps its place handles (`cell:x,y`, which a move needs), its `seen` rows and its capabilities. With
PERCEPTION off, the lazy view and the prompt are unchanged: the switch-off prompt is byte-identical to HEAD over 12 turns.

The truth stays out of the prompt. The referee block of the lazy view (mode `referee`) carries the perceiver rows with the
truth. The leak test checks the prompt the provider receives, the LLM log record, and the agent view.

## Changes

New files:

- `domains/lazy_perception.py`: `perceived(game, actor, obs, around, known, pack)` returns the lazy around with the
  perceived parts and the perceiver record and referee rows. `referee_perception(game, rec, log, pack)` builds the referee
  entry in the same shape `build_agent_view` writes it.
- `tests/test_phase065c_llm_perception.py`: 7 tests (see Validation).
- `docs/phases/phase065c/`: this report, `build_clean_tree.py`, `hunks.json`, `prompt_bytes.py`, `logs/`.

Shared file, changed only by the hunks in `docs/phases/phase065c/hunks.json` (anchored on HEAD, not applied to the working
tree, because `domains/agent_view.py` is modified there by another session):

1. `domains/agent_view.py`, `build_lazy_agent_view`: after the lazy `around` is built, with `perceiver.enabled(pack)` the
   around is replaced by `lazy_perception.perceived(...)`. Off, nothing changes.
2. `domains/agent_view.py`, `build_lazy_agent_view`, referee branch: adds `referee["perception"]` when a perceiver record
   exists.

No change to `game.py`, the prompt packet, the LLM backend, the packs or the self-test. The packet reads the same view keys.

Behaviour with PERCEPTION on (the LLM only; the simple and human paths use the full view as before):

- `around.people`: the full view's people, nearest first, capped at `LAZY_PEOPLE_CAP` (8).
- `around.heard`: the full view's heard sentences (with mishearing when IMPAIRMENT is on), last 10.
- `around.things`: the full view's perceived things (containers on the resident's cell and the physical objects it can
  see), capped at `LAZY_THINGS_CAP` (12). A tier-0 thing has no handle, as in the full view. Then the lazy place handles
  follow, as before (up to 8 more).
- `around.writing`: the full view's written marks, when READING is on and rows exist.
- The ledger (`impairment.note_view`) counts wrong subjects for lazy views too.

## Design

- The lazy view calls `_around`, which does not call the exhaustive menu (`actor_affordances` or `_actor_options`), so the
  lazy contract holds. A test checks that no menu call happens with PERCEPTION on.
- The helper is imported only inside the perception branch, so the module graph and the switch-off path are unchanged.
- The perceiver record is built from the backend's declared faculties (`perceiver.declared`), as in `build_agent_view`.
  The LLM declares all five faculties as `enforced`.

## Validation

Commands run in the scratch tree `/tmp/t065c`, built by
`python3 docs/phases/phase065c/build_clean_tree.py --out /tmp/t065c` (HEAD `48c84ff` plus 2 new files and 2 hunks in
1 file; every anchor matched once). HEAD baseline: `/tmp/h065c` (`git archive HEAD`, `--stage head`).

- `python3 domains/bigville_entities.py`: exit 0, **ERRORS (0), WARNINGS (0)**.
- `python3 -m domains.check --pack bigville` and `--pack test_hamlet`: exit 0 each.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase065c_llm_perception.py`: **7 passed**.
  On HEAD with the new test file copied in: **4 failed, 3 passed** (the four switch-on tests fail, which shows the gap).
  On the shared working tree (hunks not applied): **4 failed, 3 passed**.
- Focused run, scratch tree: `tests/test_phase031*.py tests/test_phase052*.py tests/test_phase054*.py tests/test_phase062*.py
  tests/test_phase064*.py tests/test_phase065*.py tests/test_phase066*.py tests/test_phase065c_llm_perception.py
  tests/test_lazy_llm.py tests/test_bigville_backends.py`: **237 passed**.
- Prompt bytes (`docs/phases/phase065c/prompt_bytes.py`, small lazy room, one LLM and one simple resident, 12 turns, the
  packet's md5 per turn; logs in `logs/prompt_bytes_*.txt`):
  - Switch off, HEAD vs 065c: **identical** (`cmp` exit 0).
  - Switch on, HEAD vs 065c: differ. HEAD with the switch on equals HEAD with it off (the gap).
- 60-turn simple run (`docs/phases/phase058/measure_behaviour.py --turns 60`, `PYTHONHASHSEED=0`): HEAD and 065c switch off give
  the same JSON on every field except `label` and `elapsed_seconds` (utterances 285, hunger mean end 0.4452, actions eat 5,
  move 3536, none 1056, rest 1333, sleep 55, work 15). Files: `logs/behaviour_head60.json`, `logs/behaviour_t065c_off60.json`.
- Full bare suite, scratch tree, `python3 -m pytest -q -p no:cacheprovider -rfE` (log `logs/full_suite_scratch.log`, exit
  status 1 in `logs/status_full.txt`): **4 failed, 2951 passed, 6 skipped** in 2036 s. The four failures are the known
  pre-existing ones, and each one also fails on HEAD (`/tmp/h065c`, same selection, 4 failed, 1 passed):
  - `test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]`
  - `test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds`
  - `test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns`
  - `test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears`
  `test_cast_browser.py` passed in this run.

Tests changed: none. No existing test was edited or weakened.

## Limits

- **Handles carry the true identity.** A thing's handle is the world's name for the object (for example `knife_1`). A
  wrong percept of the kind (`spade` for a knife) keeps that handle, so the prompt holds the handle. If an object's id
  equals its kind word (the small test room's `apple` is one), the true kind reaches the prompt through the handle. The
  leak test uses ids `obj_a` and `obj_b` for that reason. Pack ids were not checked for this.
- **The things set changes with the switch on.** The lazy view used `visible_objects` and `containers_in_reach`. The
  perceiver path uses the full view's sources: containers on the resident's own cell and `physical_object_observations`.
  Containers in reach that are not on the own cell are therefore no longer listed when the switch is on.
- **Seen rows are not perceived.** `around.seen` (cell features, places, witnessed moves) is unchanged.
- **Ledger under threads.** `note_view` updates the impairment ledger from context-building threads when
  `context_workers > 1`. The full view already does this, and no lock was added.
- **Not run:** an LLM village with PERCEPTION on, the 100-resident run beyond the 60-turn simple run, any timing or prompt
  size with the switch on. The packet size with the switch on was not measured.
- **Shared tree.** Until the supervisor applies `hunks.json` to HEAD, the four switch-on tests fail on the shared working
  tree.

## Open questions

1. Should a distorted thing's handle be replaced by a handle that does not carry the kind, when the object id equals the
   kind word? Pack ids should be checked first.
2. Should the lazy view keep its own containers-in-reach list (not perceived), or should containers in reach also go
   through the perceiver?
3. Are the caps right (people 8, heard 10, things 12 plus 8 place handles)? They are the lazy view's own caps, kept as
   they were.
4. Should the ledger update take a lock, given that context building can run in threads?
