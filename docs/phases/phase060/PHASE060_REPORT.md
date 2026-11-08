# Phase 060 report: structured speech in

## Summary

A simple resident now places what it hears. Its listener (`bigville/backends/speech_in.py`) reads a speaker's
well-formed `raw` payload first, then runs a deterministic grammar (`domains/speech_grammar.py`) over the text,
then gives up. A placed act can change what the resident does: a greeting or a question gets a reply, a request
from a tied neighbour becomes a give goal, an offer is accepted or declined by hunger, a warning raises caution
for 12 ticks, and news is stored as a `place_belief` memory that the Phase 053 fog reader can act on.

All of it sits behind `SPEECH_UNDERSTANDING.enabled`, which is `false` in both packs.

Measured on the 100-resident town, 60 turns, seed 305000:
- Switch off: identical to a fresh `git archive HEAD` run. 0 of 100 residents have a different action sequence,
  and the utterance count (285), hunger mean at the end (0.4442) and deaths (0) match.
- Switch on: 0 of 100 action sequences change. Utterances rise from 285 to 360. The listener heard 341
  utterances, placed all 341 by grammar (0 by raw), and sent 90 replies.

A village with the simple backend sends only greetings and questions in these 60 turns. So the request, offer,
warning and news effects are exercised by tests, not by a village run.

## Changes

New files:
- `domains/speech_grammar.py`: pure grammar (normalise, compile patterns, `rules_for`, `place`). Phase 061's
  stage one reuses it.
- `domains/speech_acts_check.py`: the self-test for the speech table (`check_speech_acts`).
- `bigville/backends/speech_in.py`: `understand(utterance, listener_context)` and the simple backend's hooks
  (`hear`, `next_reply`, `add_goals`, `goal_bonus`, `allows_transfer`, `stats`, `switched`).
- `packs/bigville/world/speech_acts.json`: `SPEECH_ACTS` (20 rows) and `SPEECH_UNDERSTANDING` (`enabled: false`,
  `effects`, `words`).
- `packs/test_hamlet/world/speech_acts.json`: the same file for the test pack.
- `tests/test_phase060_speech_in.py`: 65 tests (62 pass, 3 skip).
- `docs/phases/phase060/`: this report, `measure_speech.py` (wraps the Phase 058 run and forces the switch),
  `compare_arms.py`, `behaviour_head60.json`, `behaviour_t1_off60.json`, `behaviour_t1_on60.json`,
  `behaviour_t0_off60.json` (from the earlier run), and `logs/`.

Shared files (each hunk is a few lines; the anchor is the unchanged line next to it):
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: two entries appended after
  `{"name": "DAYNIGHT_MAJOR_ACTIONS", "file": "world/daynight.json"}` at the end of `tables`:
  `SPEECH_ACTS` and `SPEECH_UNDERSTANDING`, both in `world/speech_acts.json`.
- `domains/bigville_entities.py`: two lines in `check_consistency`, after the `check_fog(_WORLD_PACK.path, ...)`
  call and before `stats = {`: a lazy import of `check_speech_acts` and its call.
- `bigville/backends/cheap.py`, six hunks:
  1. Import, after `from .psi_can import CANWeightModel`: `from . import speech_in as _speech_in`.
  2. `decide`, the option filter. After `o.get("action") not in {"rest", "", "sleep", "joint", "release"}`, the
     transfer clause gains `or _speech_in.allows_transfer(self, o)`. With the switch off this returns False.
  3. `_update_goals`, after `observations = context.observations`: `_speech_in.hear(self, context)`.
  4. `_update_goals`, after `candidates.append(("observe", 5.0, ...))` and before the first `candidates.sort(`:
     `_speech_in.add_goals(self, context, candidates)`.
  5. `_goal_bonus`, after `if self.current_goal is None: return 0.0`: a `speech_` goal returns
     `_speech_in.goal_bonus(self, option)`.
  6. `_speech`, after its docstring and before `nearby = context.observations.get("nearby_residents", [])`: a
     queued reply, if any, is returned first.

Not touched by this phase: `bigville/backends/ocelot.py`, `worlds/bigville_world.py`, `bigville/game.py`,
`bigville/backends/conversation.py`, `tools/export_pack.py`, and the other sessions' dirty files.

### The table

`SPEECH_ACTS` has 20 rows, in the grammar's priority order. Fourteen are kinds that
`DeterministicSpeechBackend._meaning` emits. Six are message-only: `inform`, `purchase`, `give` and `put` are
not understood (no patterns), and `accept` and `decline` are sent as replies and are understood.

Each row names a `template` (a key of `DEFAULT_TEMPLATES`) or `meaning` keys (of `_realize_meaning`), or both.
Smalltalk and hedged have no template key, so they are realised only as meanings. The self-test accepts a row
with either one. Under the strict reading of "an act with no template", those two would need new
`DEFAULT_TEMPLATES` entries, and `conversation.py` is outside this phase's write scope.

The self-test also checks that every `DEFAULT_TEMPLATES` key is claimed by exactly one row, that the kinds
`_meaning` emits and the acts `cheap.py` sends each have a row marked for them, and that each template placed back
through the grammar gives its own act.

## Validation

Working tree after the last code change. Commands and results:

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). The phase's info lines: "SPEECH_ACTS:
  20 acts, 16 understood by the simple backend, 69 grammar patterns, 18 templates" and "the simple listener is off".
- `check_speech_acts` on `packs/test_hamlet` and `packs/bigville` (called directly, since the entity self-test covers
  only the bigville pack): 0 errors, 0 warnings in both.
- `python3 tools/export_pack.py --pack bigville --out <scratch>` and `--pack test_hamlet --out <scratch>`: both
  `speech_acts.json` files and both `pack.json` files are byte-identical to the working tree.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase060_speech_in.py`: 62 passed, 3 skipped (21 s). The
  skips are the slot-only templates (answer, share, question), which the round-trip test skips by design.
- Full suite, `python3 -m pytest -q -p no:cacheprovider -rfE` (log: `logs/full_suite_working_tree.log`):
  **9 failed, 2100 passed, 6 skipped** in 2914 s. The first attempt was stopped by my 45-minute timeout at 88%,
  so its log has no summary and is not used.

Attribution of the 9 failures:
- Three Ocelot tests fail with `No module named 'worlds.bigville_ocelot_adapter'`, a module this environment does
  not have: `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
  The first two files are untracked.
- `test_bigville_server.py::test_asset_manifest_covers_entity_items_and_modular_buildings`: the building `jail` is
  in the world but not in the asset manifest. This phase adds no building or item.
- Four `test_phase057_tui.py` tests (`test_over_http_a_menu_row_is_bound...`, `test_over_http_walking_to_a_known_place...`,
  `test_over_http_a_reaction_is_delivered_to_the_holder`, `test_the_server_refuses_a_bad_reply...`): these fail
  on the working tree.
- `test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently...` failed once in the full
  run (13.3 s against 10.8 s, a timing check under load). It passed in the next run of its file, on the working
  tree and on HEAD.

Checks that separate this phase from the other sessions' work:
- The same 5 non-Ocelot tests (asset manifest and the 4 TUI tests) were run on a copy of the working tree with this
  phase removed: `tests/test_bigville_server.py::test_asset_manifest_covers_entity_items_and_modular_buildings`
  and `tests/test_phase057_tui.py` give 5 failed, 44 passed. The copy had `cheap.py`, `bigville_entities.py`, both
  `pack.json` files restored to HEAD, and the phase's new files removed. So these failures do not come from this phase.
- On a clean `git archive HEAD` copy (`/tmp`), the same tests (asset manifest, `test_phase055_concurrency.py`, and all of
  `test_phase057_tui.py`) give 55 passed.
- The asset manifest and TUI failures therefore come from other sessions' uncommitted changes in the working tree
  (`worlds/bigville_world.py` and `bigville/server.py`, `bigville/game.js` and the building table, among others).
  I did not isolate which file causes each.

Behaviour runs (`measure_speech.py`, which calls Phase 058's `measure_behaviour.run`, 100 residents, 60 turns, seed
305000, `PYTHONHASHSEED=0`, pack default seeding). The comparison is `compare_arms.py`:

| Arm | Tree | Switch | Utterances | Hunger mean (end) | Deaths | Residents with a different action sequence |
|---|---|---|---|---|---|---|
| head60 | fresh `git archive HEAD` | none | 285 | 0.4442 | 0 | reference |
| t1_off60 | working tree with this phase | off | 285 | 0.4442 | 0 | 0 of 100 vs head60 |
| t1_on60 | working tree with this phase | on | 360 | 0.4442 | 0 | 0 of 100 vs t1_off60 |

Also `behaviour_t0_off60.json` from the earlier run (the tree with this phase removed) gave 0 of 100 against
head60. Every run's action counts are the same as the reference's; the comparison prints any difference. Each run
took about 133 s.

Speech counters, switch on, summed over 100 residents (`speech_in_totals` in `behaviour_t1_on60.json`):

| Count | Value |
|---|---|
| utterances heard (each record once) | 341 |
| placed by raw | 0 |
| placed by grammar | 341 |
| not placed | 0 |
| placed acts: smalltalk / question / greeting / answer | 163 / 81 / 39 / 58 |
| greeting replies queued and sent | 25 |
| question replies queued and sent | 81 |
| replies sent in total | 90 (5 expired after 3 ticks) |
| request goals, declined requests, offers accepted or declined, cautions, news kept | 0, 0, 0, 0, 0, 0 |

Speech counters differ from the utterance count. The world received 360 speak calls in the switch-on run (counted
by wrapping `BigvilleWorld.free_action`), which equals the 360 utterances. The backend counted 90 replies sent, so 15
more replies left the backend than reached the world. See Open questions.

Tests (62 pass, one file): the pack table is clean in both packs; the switch is off in both packs; the self-test
finds a template with no act and an act with no template, and a row whose emitter is missing; a round trip of each
meaning the simple backend emits (17 cases, 14 kinds) and of each template wording (11 acts); the village's own
wordings are placed; a `raw` payload is preferred, a malformed one falls back to the grammar, and an unknown slot
is malformed; a stranger's confidence is lower; a human `world.utter` of a plain sentence is placed by the grammar
(the TUI `say` command was not run); a tied neighbour's request makes a give goal that is met, and a stranger's is
declined in words; a tied neighbour without the item is declined; a greeting is answered once within the gap; a
question is answered; a hungry resident accepts food and a fed one declines; a warning from a tied speaker raises
caution and a warning from a stranger at grammar confidence does not; news is kept as `place_belief`, and a
`place_belief` naming the market raises `market` to level 1 in Phase 053's fog reader (`map_memory._tell`); each
record is read once; with the switch off the hooks never read the resident's state; a 12-turn village run with
the switch on places and counts speech.

## Limits

- **Effects in the village.** The simple village sends four acts: greeting, share, question and inform
  (`cheap.py._speech`). In these 60 turns it sent greetings and questions, so only those two effects ran in the
  village. The others are exercised by tests.
- **Fetch and tell are not implemented.** The brief lists give, tell and fetch as requests a resident can meet. Only
  give is implemented. A tied neighbour's request for an item the resident does not hold, or for anything else,
  is declined in words. This is a deviation from the brief.
- **Replies are fixed sentences.** A greeting gets a greeting; a question gets "I am managing, thank you". The brief
  said "the existing reply logic", but the simple backend has no reply logic beyond its speech.
- **Place detection.** Every heard `share` becomes a `place_belief`, as the brief asks. Phase 053's fog reader
  raises a place only when the text names a place in its registry, so news about a person changes nothing in the
  fog. The phase's own `_mentions_place`, which only feeds the `effect_news_stored_place` count, checks the 9
  FOG_PLACE_WORDS and 3 FOG_PUBLIC_LANDMARKS phrases. A place the fog registry knows but those lists lack is counted
  as a person, so the place count is a lower bound.
- **Tie.** The tie for a speaker is `tie_strength` from `nearby_residents` (within 8 cells). A neighbour who speaks
  from further away counts as a stranger.
- **State.** The listener's state (`backend._speech_in`) is not checkpointed and is not in `dump_held_state`. The news
  memories are, because they are `MemoryRecord`s on the character.
- **Memory growth.** Each news record heard adds one memory, with no cap. No village run here heard a share, so
  the growth is not measured.
- **Speaker side.** LLM and TUI speech were not run through a live provider or a live TUI. Their path to the listener
  is the `heard_utterances` text (the same as a world `utter`), which the human-utterance test covers.
- **Effect values are APPROX.** Every number in `SPEECH_UNDERSTANDING.effects` is an authored choice (marked in the
  table's `_doc`). `need_hunger` 0.25 is the cheap backend's own eat threshold. None has a measured effect in this
  run, because the village rarely sent the acts that use them.

## Open questions

1. **Reply count gap.** Switch on, 90 replies were counted at the backend, but the utterance count rose by 75 (285 to
   360), and the world received 360 speak calls. My guess is that some replies were computed in responses the world
   never applied (for example, a suspended action in `game.py`), but I did not trace it. Should the backend count
   only replies that reach `free_action`?
2. **Fetch and tell.** Do they belong in this phase or in Phase 061? Each needs a new kind of action or a knowledge
   action.
3. **Raw payloads from non-simple speakers.** `game.py` marks a payload `not_understood` for simple listeners, and this
   phase's listener uses a well-formed raw payload anyway, as the brief asks. Should it honour the declaration
   instead?
4. **News cap.** Should a resident's news memories have a cap? One line in `speech_in.py` would do it.
5. **Checkpoint.** Should `_speech_in` state be checkpointed with the simple residents? The checkpoint code is outside
   this phase.
6. **Transfer filter.** The `allows_transfer` hunk in `cheap.py` lets a live give goal bypass the policy's
   `allow_transfers` flag. Is that acceptable?
7. **Pack file history.** `packs/bigville/pack.json` and `packs/test_hamlet/pack.json` also differ from HEAD in about
   170 lines above my two entries (single-line reformatting of existing entries, and the fog and day-night entries).
   Those lines are another session's work, and I cannot tell from git which session wrote them. My two entries are
   the last two in each file's `tables`. The other dirty files in `packs/bigville/world/` are also another session's.
8. **Ocelot and TUI.** The Ocelot adapter module is absent here, so three Ocelot tests fail. The four TUI tests and the
   asset manifest test fail on the working tree because of other sessions' changes, not this phase's.
