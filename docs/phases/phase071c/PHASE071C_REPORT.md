# Phase 071c: LLM residents get the same affordances; the terminal shows the body

## Summary

Two decisions from the supervisor's brief are implemented.

1. **LLM residents have the player's affordances.** A reply may carry `free_actions` (a list of `{action, target, params}`).
   Each item is checked against FREE_ACTIONS, routed to `world.free_action`, and its outcome is shown in `last`. Every
   FREE_ACTIONS name has a route, and every MAJOR_ACTIONS name passes the reply path (table below). The packet's reply
   interface describes the field and the free actions. The prompt schema is now `bigville/prompt/5`.
2. **The terminal shows the felt body and takes the attend words.** `glance`, `attend`, `press <region>` and
   `strike NAME [at REGION]` are typed words. A glance is sent as a free action, with no turn and no tick. The sheet and the
   text-mode room draw the felt body with `domains.interoception.render_felt_body`, and the labelled body when the view is
   labelled. `last` shows the sound and place of an attend, press or glance.

Results: entity self-test 0 errors, 0 warnings (bigville); `domains.check --pack test_hamlet` 0 errors, 0 warnings;
`tools/generate_seeds.py --check` matches 31 files. The 60-turn and 200-turn simple village digests equal the base
(the working tree before this phase's edits), with 0 deaths. New tests: 36, all passing. Full suite: 22 failed, 2979 passed,
7 skipped. Every failure is listed under Validation; one (the packet snapshot) is expected, and one (a Phase 031 test that
pins the prompt schema) needs a decision.

## Decision 1: free actions in a reply

### Design

- **Reply field.** `free_actions: [{action, target, params}]`. The pack's `PROMPT_RESPONSE_FIELDS` gains `free_actions`,
  and `PROMPT_REPLY.free_action_keys` is `["action", "target", "params"]`.
- **Checked against FREE_ACTIONS** (`bigville/backends/reply_schema.py`, `_check_free_action`). The reply's keys, the types of
  `target` and of the text params (`text`, `note`, `item`, `giver`), and the intensity word or number are checked. A row with
  `requires_target` needs a target, unless its `target_or_param` (accept: `item`) is given. An unknown name is not a
  schema error: the world refuses it as `unsupported`, and that refusal is recorded (see below). The brief asks for a
  recorded refusal for an unknown free action, so the schema cannot reject the name first.
- **Routing** (`bigville/free_replies.py`). `ROUTES` maps each FREE_ACTIONS name to one `world.free_action` call. The
  arguments are positional where the world's dispatcher reads `args[0]` or `args[1]` eagerly (reply, give_note, accept by
  request, decline). See Hand-offs.
- **Outcome in `last`.** `free_replies.apply_one` stores `{turn, action, applied, reason, seen_major}` per resident on the
  game object (lazy attribute `free_outcomes`). An applied glance adds `sound` and `place`. `domains/agent_view.py` shows this
  outcome as `last` when no major outcome has been published since it ran (`seen_major` equals the current
  `world.last_outcome`). A refusal's reason is a REFUSAL_REASONS code with its description, as for a major action. A
  free outcome is not written to the world's refusal log, so `game.last_rejections` (major actions only) is unchanged.
- **Where it is applied.** `game._apply_response` calls `free_replies.apply_all` before the major action (the import is
  inline, one hunk). The TUI's free-only reply (a glance on its own) calls `apply_all` directly with no step, because a
  step ends the turn for every resident.
- **Simple backends.** `ActorResponse.free_actions` is filled only by `ActorResponse.from_dict` and `LLMBackend._accept`
  (both from a reply). No simple backend and no `actor_affordances` row carries a free action. A test runs three village
  turns and checks that no simple resident sends one.
- **The packet.** `packet_system` lists the free actions with their descriptions (a description with a digit is named only,
  as the major actions are). The reply interface gains one line, and the first interface line names the new field. A
  glance description no longer carries the digit: it refers to the attend rows in `public.can` (`signal:N`).
  Felt signals reach the LLM as `public.can` rows (`attend`, `signal:N`), which are the handles a glance names. Test:
  `test_the_glance_row_of_each_felt_signal_is_in_the_packet_public_can`.
- **Speech.** `speak` is reachable both as `utterances` (the existing path, unchanged) and as a free action (same world
  call: `free_action(actor, "speak", target, content)`). A test checks that both are one call.
- **Schema version.** `PACKET_SCHEMA` is `bigville/prompt/5` (the reply shape changed).

### Parity table

Source: `load_pack("bigville")` (31 MAJOR_ACTIONS, 9 FREE_ACTIONS). "Reply" is the test that the key survives
`reply_schema.to_wire` into `ActorResponse` (`test_every_major_action_key_is_reachable_from_a_reply`) or the route and
world call of `free_replies` (`test_every_free_action_key_has_a_route_and_is_reachable_from_a_reply`,
`test_every_free_action_key_reaches_the_world_with_its_params`).

| Kind | Key | Reachable from a reply | How |
|---|---|---|---|
| major | move, give, attempt, take, strike, throw, restrain, release, struggle, put, pick_up, drop, sell, sell_labor, work, eat, water, rest, sleep, fetch, build, harvest, sow, fertilise, tend_animals, maintain, care, lock, unlock, attend, press | yes | `major_action` with `params` (strike: `params.region`; attempt: `params.verb`; intensity, with) |
| free | speak | yes | `free_actions` (text) and `utterances` (same world call) |
| free | reply | yes | `free_actions`, target = person, `params.text` |
| free | write_note | yes | `free_actions`, `params.text` |
| free | give_note | yes | `free_actions`, target = recipient, `params.note` (a note id; see Limits) |
| free | accept | yes | `free_actions`, target = request id, or `params.item` (and `params.giver`) |
| free | decline | yes | `free_actions`, target = request id (see Limits) |
| free | set_intensity | yes | `free_actions`, `params.intensity` (a word or number) |
| free | stop | yes | `free_actions` |
| free | glance | yes | `free_actions`, target = `signal:N` from `public.can` |

### Test results for the decision

`tests/test_phase071c_free_actions.py` (19 tests): the parity tests above; the schema checks (missing target, text, intensity
word); the intensity word folded to its value; an unknown name passed to the world and refused `unsupported` with its reason
in `last`; a glance enacted from an LLM reply (`applied`, `sound`, `place` in `last`); an aimed strike whose `region` reaches the
world (and an unknown region refused as `unknown_region`); `set_intensity` reaching the world with the value of the word
(refused `not_possible`, since there is no timed job); no slot and no tick; a glance after an attend on the same turn
(the glance is `last`); refusals for a glance on an unknown feeling and while asleep; the leak rule on a free outcome;
the packet's glance rows and system text; the simple backends never offer or send a free action.

## Decision 2: the terminal

- **Words** (`bigville/tui/commands.py`). `parse` calls `domains.attend_commands.parse_line` before the physical verbs.
  `glance [N]` gives `{"free_actions": [...]}`. `attend [N]` and `press <region>` give the major actions. `placed` accepts
  the same lines. `strike NAME [at REGION]` (a head whose lexicon verb is `hit`, when a person the view names matches) gives
  the major action `strike` with `target` = the name, `params.region` when a region is named, and the intensity word.
  An unknown region is passed as words for the world to refuse. Without a person, `hit the lock` is still the physical
  attempt.
- **Free-only replies** (`bigville/tui/app.py` `_propose`, `bigville/tui/client.py` `EmbeddedClient.apply_free`). The
  free actions run now, with no step. The lines printed are the outcome lines (sound and place included).
  `HttpClient.apply_free` raises `UnsupportedOverHttp` with a message. A reply with a major action keeps the normal path.
- **The felt body** (`bigville/tui/narrate.py` `body_lines`, `bigville/tui/render.py` `_body_tab`). A body with `feeling` or
  `signals` is drawn by `domains.interoception.render_felt_body`, and the states (asleep, collapsed, ill) follow. A labelled
  body keeps the one line each for energy, hunger, health and mood. Text mode gets the same lines through `prose.room_lines`,
  which calls `body_lines`.
- **`last` probes** (`narrate.outcome_lines`). A `place` in `last` prints `From your PLACE: SOUND.`. A silent probe prints
  `Nothing answers from your PLACE.` Templates `probe` and `probe_silent` are in `packs/*/world/narration.json`
  (APPROX words; `domains/narration_check.py` names their fields).
- **Help.** `NARRATION.help` (map mode) and `TUI_PROSE.help` (text mode) gain lines for glance, attend, press and strike.
  Neither line has a digit.

`tests/test_phase071c_terminal.py` (17 tests): the parse of each word, `placed`, the help, the sheet and the room with
the felt body, the labelled body, the sound and place lines, a glance from a session with no turn (`world._turn`
unchanged), an attend and a press from a session (`last` names the action and the place), a strike whose region reaches
the world, text mode writing the glance outcome, and the HTTP refusal.

## Shared-file hunks

Files that other sessions had uncommitted at the start (the first two are dirty, the rest were mine only):

- `bigville/game.py`, `_apply_response`: three lines (the comment, the import and the `apply_all` call) before
  `if response.major_action is not None:`. The other session's `record_action_outcome` hunk (about 9 lines below) is separate.
- `domains/bigville_entities.py`, `_check_prompt_instructions`: the `_RESPONSE_FIELDS` set gains `free_actions`, and a block
  after the `PROMPT_RESPONSE_FIELDS` check (free action params, `target_or_param`, `free_action_keys`). The other session's hunks
  in this file are at lines about 1292, 1328, 2376 and later.

Files that were clean at the start, edited by me: `bigville/backends/protocol.py` (field `free_actions`, read in `from_dict`),
`bigville/backends/reply_schema.py` (`_check_free_action`, `_fold_free`, the `check` and `to_wire` hunks, docstring),
`bigville/backends/llm.py` (`validate_response`, three `ActorResponse` constructions in `_accept`),
`bigville/backends/prompt_packet.py` (`PACKET_SCHEMA`, `_interface_lines`, `packet_system`), `domains/agent_view.py`
(`_free_last`, `_last_free`, `_last` and its two call sites), `domains/narration_check.py` (two keys),
`domains/prompt_packet_check.py` (one placeholder), `bigville/tui/app.py`, `client.py`, `commands.py`, `narrate.py`,
`render.py`.

Pack data (all mine; no other session's hunk is in these files): `packs/{bigville,test_hamlet}/world/free_actions.json`
(`params`, `target_or_param` on accept, the glance and set_intensity wording), `llm_instructions.json`
(`PROMPT_RESPONSE_FIELDS`), `prompt_packet.json` (`PROMPT_REPLY.free_action_keys`, two interface lines),
`narration.json` (`probe`, `probe_silent`, help), `tui_modes.json` (`TUI_PROSE.help`). Each file is written in the
exporter's layout (`json.dumps(indent=2, ensure_ascii=False)`); `tools/export_pack.py` output for these files is identical
to the file bytes. `packs/*/pack.json` is unchanged by this phase.

New files: `bigville/free_replies.py`, `tests/test_phase071c_free_actions.py`, `tests/test_phase071c_terminal.py`,
`docs/phases/phase071c/` (this report, the digests and the full-suite log).

## Changed tests (old -> new)

- `tests/test_phase054_llm_prompt.py`, line 153: `"bigville/prompt/4"` -> `"bigville/prompt/5"`. The reply shape changed.
- `tests/test_bigville_backends.py`, lines 28 and 38: `"bigville/prompt/4"` -> `"bigville/prompt/5"`. Same reason.
- Not edited, and failing: `tests/test_phase031_llm_backend.py`, line 127 pins `["bigville/prompt/4"]`. That file is the other
  session's (Phase 031). The one-line change is `"bigville/prompt/4"` -> `"bigville/prompt/5"`. See Open questions.
- Not edited, and failing as expected: `tests/fixtures/phase054_packet_snapshot.json` (the packet's `system` text changed:
  the free action list, the interface lines and the schema). The supervisor regenerates it.

No assertion was weakened or removed.

## Validation

Commands run on the live tree (after all edits), with other sessions' uncommitted work present:

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)". No regeneration needed.
- Village digests (`docs/phases/phase070/compare_digest.py`, simple backend, town100, seed 305017). The base was a copy of the
  tree taken before the first edit (`/tmp/base071c`).
  - 60 turns: base `3a8c1d8cc7b9e84acef84c4c1adb504038f914b6598acc234f6495ae311c695d`, new the same, deaths 0.
  - 200 turns: base `8d5d176fe20169ba83edcb8b6433d9085034facc228073c86d3c8f545bb3bc97`, new the same, deaths 0, 100 residents
    with marks (`mark_wetness` 50.0), the same in both.
  - Output: `digest_60_base.json`, `digest_60_new.json`, `digest_200_base.json`, `digest_200_new.json`.
- New tests: `python3 -m pytest -q -p no:cacheprovider tests/test_phase071c_free_actions.py tests/test_phase071c_terminal.py`:
  36 passed.
- Related files: `tests/test_phase057_tui.py`, `test_phase067_tui_modes.py`, `test_phase054_actionable.py`,
  `test_phase052_agent_view.py`, `test_phase069_body.py`, `test_phase070b_body.py`, `test_phase070_locus.py`,
  `test_phase071_attend.py`, `test_bigville_backends.py`, `test_phase018_llm_instructions.py`, `test_phase050_resolution.py`,
  `test_phase059_autopilot.py`, `test_lazy_llm.py`, `test_phase013b_data_pack.py`: all pass except the four
  `test_phase057_tui.py` over-HTTP tests (below) and the snapshot.
- Full suite: `python3 -m pytest -q -p no:cacheprovider -rf` (log: `docs/phases/phase071c/full_suite.log`): **22 failed,
  2979 passed, 7 skipped** (2045 s). The failures:
  - Expected from this phase: `test_phase054_llm_prompt::test_the_packet_matches_the_snapshot_for_a_fixed_view` (fixture not
    edited); `test_phase031_llm_backend::test_callable_provider_is_accepted` (the schema literal; see Open questions).
  - The four `test_phase057_tui.py` over-HTTP tests (`test_over_http_a_menu_row...`, `test_over_http_walking_to...`,
    `test_over_http_a_reaction...`, `test_the_server_refuses_a_bad_reply...`). They also fail on the base copy with the same
    assertion (for example `assert deque([]) == ...` on `contest_log`). The server and the reaction path are the other
    session's live changes (`bigville/server.py`). Not caused by this phase.
  - Five that also fail on the base copy: `test_phase058_persona` (50-turn simple run), `test_phase060_speech_in` (village
    run), `test_package15_resource_social_stress` (policy pair), `management/test_cast_browser`,
    `test_fix_llm_checkpoint[0]`.
  - Three Ocelot import failures (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`): `test_mixed_ocelot_checkpoint_parity`,
    `test_mixed_ocelot_village`, `test_bigville_ocelot_communication`. The brief lists these as known. The third passes on the
    base copy and fails on the live tree; the cause is the missing module on the live tree.
  - Two in `test_phase042b_lamplighter.py` and five in `test_phase065b_impairment.py`. Both files are the other session's
    untracked work (absent from the base copy). They fail on `percept() got an unexpected keyword argument 'shift'`,
    `enact_plan('Bob', {'action': 'light'})` and similar. Not this phase's code.
  - One in `test_phase013a_packs::test_exported_files_compile_back_to_the_same_tables`. The exporter output for files
    this phase did not touch (`life_stages.json`, `persona.json`, `health.json`, `contest.json`, `dependants.json` and others)
    differs from the live files, because the other session's `life_stages`, `impairment` and `interoception` edits are
    in progress. The same test passes on the base copy. The rerun test `test_export_rerun_is_byte_identical` failed on the live
    tree at one moment with the same cause and passed in the later run. The exporter output for this phase's own pack files
    matches their bytes.
- While the other session was editing `worlds/bigville_world.py` (around line 10422), the file did not parse. The self-test and
  the phase 069, 070, 070b and 071 self-test tests failed for that interval. They passed on rerun.

## Limits

- **The LLM cannot yet name some targets.** `give_note` needs a note id and `decline` and `accept` need a request id. The
  packet does not list note or request ids, so an LLM can route these but cannot know them. The affordance is there; the
  visibility is not.
- **`last` shows the newer of the free and the major outcome.** A refusal of a free action on the same turn as an applied
  major action is not shown when the major action was applied after it. On the TUI path the free outcome is newer.
- **Free outcomes are not checkpointed.** They live on the game object. `bigville/game_persistence.py` (other session) does not
  save them, so a resumed game shows no free outcome in `last` until the next free action. Persistence is not wired.
- **Glance sound and place come from the body's own rows.** `bigville/game.py` does not call this; `bigville/free_replies.py`
  calls `body._derive()` (a private method of `worlds/body.py`) after an applied glance. A public `Body` accessor would replace
  it. `worlds/body.py` is the parallel session's file, so the change is not made here.
- **Over HTTP a reply with only free actions ends the turn.** `POST /api/turn` applies a reply and steps the world, as for any
  reply, so a server client that sends `free_actions` alone gives its resident a carry-on turn. The terminal never does this
  (it uses `apply_free`, and over HTTP that raises). The server is the other session's file.
- `set_intensity` in the TUI is not typed (no word maps to it). It is reachable from the reply path only.
- The APPROX words of the probe and help templates were chosen here. No source was consulted.
- No village run with a live LLM resident sending free actions was made. The LLM path is covered by fake providers only.
- No village run with a typed attend, press or glance was made.

## Hand-offs

- **Positional arguments in `world.free_action`.** `worlds/bigville_world.py` `free_action` evaluates `args[0]` in the default
  of `kwargs.pop("target", args[0])` (reply), `kwargs.pop("recipient", args[0])` (give_note),
  `kwargs.pop("request", args[0])` (accept, decline). A keyword-only call raises `IndexError`. `free_replies.ROUTES` passes
  positional arguments, so the call works. The world's dispatcher should use `args[0] if args else None`. This is the parallel
  session's file; not edited.
- **`Body` probe accessor.** A public method that returns the sound and place of a signal handle (instead of
  `body._derive()` in `free_replies._glance_probe`).
- **Checkpoint.** `game_persistence.py` (other session) should save `free_outcomes` (a plain dict per resident) with the
  game, or the free outcome is lost on resume.
- **Packet ids.** If LLM residents should give notes or answer requests, the packet needs the note and request ids in
  `private.notes` or `public.around`. This is a packet change, not made here.

## Open questions

1. **`tests/test_phase031_llm_backend.py` line 127** pins `bigville/prompt/4`. The schema is now 5, so this test fails. The file is
   the other session's, so it was not edited. The one-line change is to `bigville/prompt/5`. Should it be made here?
2. **Snapshot.** Regenerate `tests/fixtures/phase054_packet_snapshot.json` (the packet's `system` text changed: the free action
   list, the interface lines, the glance description, and the schema).
3. **Free-only replies over HTTP.** Should the server accept a reply with only free actions and apply it without a step, as the
   terminal does in process? That is a server route change (other session's file).
4. **Unknown free action name in the schema.** This phase lets the world refuse it (as the brief's test requires). A stricter
   reading would make the reply fail the check and go to the repair call. Which is wanted?
5. **`strike` without a person.** `strike` with no matching person falls through to the physical verb `hit`. Should the TUI
   ask instead?
