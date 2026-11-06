# Phase 054: the LLM prompt packet and the response schema

## Summary

An LLM resident's prompt is now built from its agent view (Phase 052), not from the raw observations. The
packet carries words only: no lexicon number, and no key outside the view whitelist, which a test checks over a
fixed view and over a live town resident. The private part leads with a line that says who the resident is, what
they would usually do now, and the persona card. The reply is checked against a schema in the pack. Intensity and
amounts accept lexicon words, `attempt` verbs resolve by alias, and one repair call receives the errors in words.
Other residents' speech is delivered as quoted data under a standing rule. Lessons persist, and over the cap the
next call asks for a merge. Each section is capped, and the record reports its sizes.

Simple backends are unchanged. A 60-turn town100 run (seed 305000) is identical to a clean HEAD run on every field
except wall-clock time.

Self-tests: bigville ERRORS (0), WARNINGS (0); test_hamlet ERRORS (0), WARNINGS (0). Full suite: 1508 passed,
2 skipped, 3 failed. The 3 failures are the Ocelot adapter tests, which also fail on a clean HEAD copy (see
Validation).

## Changes

### Created

- `bigville/backends/prompt_packet.py`: `build_packet(context, pack=..., consult_reason=..., choices=...)` returns
  the packet's context and a meta dict (lesson ids, merge flag). `packet_system(pack)` builds the packet's system
  text from the pack. Caps are applied per section. A list over its cap drops its newest items and the count is
  reported as `omitted`. Lessons are never dropped, because a merge must see every lesson it replaces.
- `bigville/backends/reply_schema.py`: `check(parsed, pack, lesson_limit=None)` returns the schema errors in words.
  `to_wire(parsed, pack)` folds `target`, `with` (as `tool` for `work`) and `intensity` into `params`, resolves a
  verb alias, turns an utterance `to` into `target`, and turns each memory update into `{kind, content: {text}}`.
  An unknown verb is left as the resident wrote it, so the world refuses it as unsupported.
- `domains/prompt_packet_check.py`: self-test checks for the packet tables (caps, structural keys, labels, merge
  text, interface placeholders, the words the interface names, reply keys and memory kinds, and the view whitelist
  keys the packet reads). Wired from `domains/bigville_entities.py`.
- `packs/bigville/world/prompt_packet.json` and `packs/test_hamlet/world/prompt_packet.json` (identical). Tables:
  `PROMPT_PACKET` (caps, limits, the texts the model reads) and `PROMPT_REPLY` (the reply schema).
  Both match `tools/export_pack.py` output byte for byte.
- `tests/test_phase054_llm_prompt.py`: 36 tests. Fake providers only.
- `tests/fixtures/phase054_packet_snapshot.json`: the packet for a fixed view (the snapshot test).
- `docs/phases/phase054/`: this report, the self-test outputs, the full suite log, the behaviour JSON and logs for
  three trees, and `example_prompt_resident.json`.

### Rewritten (owned by the LLM backend tract, not in Tract A's edit list)

- `bigville/backends/llm.py`:
  - `LLMBackend.wants_agent_view = True`. The game gives the context its view.
  - `_ask` builds the packet, sends it, and checks the reply with `validate_response` and then the schema. It
    returns the reply in wire form and keeps the reply as sent, which the response hash covers (Phase 031's
    `response_hash` is unchanged in meaning).
  - A context with no agent view is never sent. It is counted as `internal_error` and the autopilot acts (or the
    resident idles without one).
  - The consult reason and choices go into `public.consult` in the packet. The Phase 059 `autopilot` key is gone
    from the payload.
  - `CONSULT_RULES` moved to the pack (`PROMPT_PACKET.consult_rules`).
  - A merge reply that carries lesson updates removes the lesson memories the prompt listed, then the game adds the
    reply's lessons. Counted in `lessons_merged`.
  - `last_backend_state` gains `prompt_chars`.

### Own files, changed

- `domains/agent_view.py`: `self.lessons` (every lesson, oldest first). `self.notes` now excludes lessons.
  `around.things`: containers on the resident's own cell (an attempt needs the resident there) and the physical
  objects the resident can see, as `{handle, what}`.
- `packs/bigville/world/agent_view.json` and `packs/test_hamlet/world/agent_view.json` (identical): whitelist
  `self` gains `lessons`, `around` gains `things`, and a new section `thing` with `handle` and `what`.

### Shared-file hunks (additive; anchors are unchanged lines of HEAD, or the nearest unchanged line)

1. `bigville/game.py`, `BigvilleGame._context`. Replaces the final `return ActorContext(...)`, two lines, with a
   guarded view, then `return ActorContext(..., recipient_interfaces=recipient_interfaces, agent_view=view)`.
   Anchor: the line `            for name, backend in self.backends.items() if name != actor` followed by `        }`.
   The view is built only when `getattr(self.backends.get(actor), "wants_agent_view", False)` is true. A failure
   in `agent_view` leaves `view = None` and does not raise.
2. `bigville/backends/prompts.py` (five hunks):
   a. Import `from .prompt_packet import PACKET_SCHEMA, build_packet, packet_system` after
      `from .protocol import ActorContext`.
   b. `PromptRecord`: field `meta: dict[str, Any] | None = None` (with a comment) after `    pack_hash: str = ""`.
   c. `PromptBuilder.__init__`: `self.packet_system: str | None = None` after `        self.system = build_system_text(self.pack)`.
   d. `PromptBuilder.build`: the signature `def build(self, context, consult_reason=None, choices=None)` and the
      dispatch `if getattr(context, "agent_view", None) is not None: return self._packet(...)`. It replaces
      `    def build(self, context: ActorContext) -> PromptRecord:`. The Phase 018 body is unchanged.
   e. New method `PromptBuilder._packet`, inserted before `    def _outcome_entry(self, outcome) -> dict[str, Any]:`.
3. `domains/bigville_entities.py`, `check_consistency`: two lines after
   `    check_lexicon(_WORLD_PACK.path, errors, warnings, info)`: the import of `check_prompt_packet` (with a
   comment) and its call on `_WORLD_PACK.path`.
4. `domains/agent_view_check.py`, `SECTIONS`: `"thing"` inserted after `"seen"`. Anchor:
   `            "heard", "seen", "map", "can", "last", "referee")`. Needed because the whitelist gained a section.
5. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: the last table entry
   `    {"name": "ACTION_WORDS", "file": "world/agent_view.json"}` gains a trailing comma and is followed by
   `    {"name": "PROMPT_PACKET", "file": "world/prompt_packet.json"},` and
   `    {"name": "PROMPT_REPLY", "file": "world/prompt_packet.json"}`. Both forms are the one-line objects Tract A
   already uses in these files.

Other files I edited are the three existing test files listed below.

## Edits to existing tests

Every edit below keeps the test's intent. No assertion was removed or weakened.

- `tests/test_phase031_llm_backend.py`
  1. `_context()` passes `agent_view=_view(name)`, and a `_view()` helper was added. Reason: the LLM backend refuses a
     context with no view.
  2. `test_callable_provider_is_accepted`: `seen == ["bigville/prompt/2"]` becomes `["bigville/prompt/3"]`. Reason:
     the packet has its own schema version.
  3. `test_first_good_reply_is_unchanged_and_counted_once`: the expected record is built with
     `state["consult_reason"]`, the reason the backend recorded. Reason: the default backend has an autopilot, so the
     consult is part of the packet. The hash test still compares the backend's hash with a record built the same way.
- `tests/test_phase059_autopilot.py`
  1. A `_view()` helper, and `_ctx()` passes it. Reason: no view, no prompt.
  2. The reaction helper passes `agent_view=_view()`. Same reason.
  3. Three assertions `prompts[i]["autopilot"]["why_consulted"]` became
     `prompts[i]["context"]["public"]["consult"]["why_consulted"]`. Reason: the consult section moved into the packet.
  4. `test_the_prompt_carries_what_the_resident_would_usually_do_now` reads the usual-now line from the packet's
     `private.lead` and matches `"Usually now:"` anywhere in the line. Reason: the line is now in the lead, and
     `usual_words` prefixes `Today is spring.` on day 0.
- `tests/test_bigville_backends.py`, `test_llm_backend_accepts_provider_json_and_exposes_backend_state`: the context
  passes a minimal `agent_view`. The schema assertions moved from `bigville/prompt/2` to `/3` (two lines).

## Validation

Run from `/home/matt/ozmadev/bigville`, on the live tree (Tract A's work-in-progress present).

- `python3 domains/bigville_entities.py`: exit 0. `ERRORS (0)`, `WARNINGS (0)`. Output:
  `docs/phases/phase054/selftest_bigville.txt`. Info lines: `PROMPT_PACKET (bigville): all prompt packet checks pass
  (5 intensity words, 20 verbs, lessons kept to 12)` and `AGENT VIEW (bigville): 17 sections whitelisted ... all
  agent view checks pass`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. `ERRORS (0)`, `WARNINGS (0)`. Output:
  `docs/phases/phase054/selftest_test_hamlet.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase054_llm_prompt.py`: 36 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_bigville_game_api.py tests/test_phase054_llm_prompt.py tests/test_phase031_llm_backend.py tests/test_phase059_autopilot.py tests/test_bigville_backends.py`: 130 passed, 1 skipped (the skip is an Ocelot test, which needs the sibling checkout).
- Full suite: `timeout 1500 python3 -m pytest -q -p no:cacheprovider`: **1508 passed, 2 skipped, 3 failed**, 546 s.
  Log: `docs/phases/phase054/full_suite.log`. The failures:
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
  - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

  All three raise `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. The same failure appears in
  the Phase 031, 052 and 059 reports. Check on clean HEAD: I copied the three untracked test files into
  `git archive HEAD` (with a symlink to the sibling `ocelot` checkout). They fail there too: two on
  `bigville.game_persistence` and `bigville.mixed_ocelot_scenario`, which HEAD does not contain, and one with the same
  `worlds.bigville_ocelot_adapter` error. These failures do not depend on this phase.
- Earlier in the phase, one full run had 4 failures: a fourth was `test_llm_backend_speech_is_not_rewritten_for_a_legacy_npc_recipient`.
  The reply schema rejected the `raw` key on an utterance. I added `raw` as an optional, unchecked utterance key and
  reran it (passes).
- Behaviour, simple backends (`PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label L --turns 60 --out ...`,
  town100, seed 305000, default seeding). Three trees:
  - `head`: `git archive HEAD` (commit 17bdc37).
  - `hunk_off`: a copy of the live tree with only hunk 1 (the `game.py` `_context` change) reverted to HEAD's return.
  - `mine`: the live tree as it is now.

  All three give identical results, except `elapsed_seconds` and `label`: action counts `eat` 5, `move` 3333,
  `none` 1050, `rest` 1549, `sleep` 48, `work` 15; same utterances, deaths, handovers, hunger trace and per-resident
  digests. Files: `docs/phases/phase054/behaviour_{head,hunk_off,mine}.json` and the matching `log_measure_*.txt`.
  The 200-turn run was not repeated. The 100-resident LLM town was not run.

### Example prompt (words only)

Resident Bryony Turnbull (doctor) at dawn in spring, town100 seed 305000, fake provider. The full payload is in
`docs/phases/phase054/example_prompt_resident.json`. The sizes come from the record: 6,988 characters of packet and
4,872 of system text.

```
private.lead:
  "You are Bryony Turnbull, doctor, an adult, grown."
  "Today is spring. Usually now: answering a call from the sick (seeing to the morning chores)."
  "Your temperament: pleasant enough; forgiving; slow to anger; ... wedded to your trade."
  "Your past: You work at the trade of doctor. You were born in Bigville. ..."
  "Your usual day: ..."
private.body: {"health": "in good health", "energy": "fresh", "hunger": "not hungry", ...}
private.knows: [{"name": "cat", "understood": "you understand it", "gist": "an animal you know of"}, ...]   (38 dropped by cap)
public.now: {"time": "at dawn", "season": "spring", "weather": "clear skies"}
public.around.people: [{"distance": "right beside you", "looks": ["looks even-tempered", ...], "description": "a stranger (labourer)"}, ...]   (24 dropped by cap)
public.can: [{"handle": "", "action": "work", "what": "burn charcoal"}, ...]
```

The reply interface (system text, excerpt): `intensity is a number, or one of these words: carefully, gently,
hard, normally, with all your strength.`, and `params.verb` takes one of the pack's verbs, with aliases understood.
The system text no longer quotes the `1.0` in the `attempt` action description. Descriptions with digits are
replaced by the name, and the interface lines explain the action instead.

## Limits

- No live provider. Reply quality, repair rate, latency and token counts with a real model are not measured. The
  caps are APPROX design choices (`PROMPT_PACKET.caps`), not measured against a tokenizer.
- The 200-turn caps check ran on a two-actor world with a fake provider (`tests/test_phase054_llm_prompt.py`). No
  town-scale run was made.
- The Phase 034 intoxication line (`felt_body`) is not in the packet. Only the Phase 018 record has it. The view has
  no published intoxication words, so an LLM resident is not told it is drunk.
- Phase 018 `held_frames` are not in the packet. Knowledge comes from the view's `knows`, which is capped.
- A context with no view goes to the Phase 018 record path. Only tests and tools build one. The LLM backend refuses it.
- `can` gives a handle only for moves and transfers. `work` and `eat` options have an empty handle and a words label.
  The world may need the internal recipe or kind key to act on those options, so a model cannot name them exactly
  yet (see Open questions). Fixed in the follow-up below: every row has a handle, and a reply that names one runs.
- The repair request keeps the Phase 031 shape: the original packet plus `repair: {errors}`. The brief said the
  repair carries only the errors. The shape is kept because the Phase 031 test pins it. See Open questions.
- Lesson merge: a merge reply replaces every held lesson when it carries at least one lesson update. A reply with
  one lesson therefore drops the others. The merge is only requested over the cap (12 lessons).
- Interface line and cap texts are the author's English. They are data in the pack. No translation was attempted.

## Open questions

1. **Handles for actions that are not attempts.** Resolved in the follow-up. Every `can` row has a handle built from
   the world's own fields (`work:burn_charcoal`, `eat:bread`, `rest`, or the world's `target:N` for moves and
   transfers). A reply that copies the handle into `major_action.target` now runs the row, as the simple backend
   would send it. The `can` whitelist did not change; the handle is the value of the existing `handle` key.
2. **Repair request shape.** The brief says the repair carries only the errors in words. I kept the Phase 031 request
   (the original packet, plus `repair.errors`), because the Phase 031 test pins it and it lets the model see its own
   packet again. Should the repair drop the packet?
3. **`raw` on utterances.** I accept an optional `raw` object on each utterance (the Phase 018 speech contract, with
   `SpeechProposal.raw`). The brief's schema is `{to, text}`. Confirm.
4. **Intoxication in the packet.** Needs an intoxication band in the view's body (a published quantity, Phase 034).
   Do you want it in the view?
5. **Lesson cap.** `lessons_max` 12 and `lesson_chars` 240 are APPROX.

## Follow-up: actionable handles

Defect: a `can` row for an action other than move had an empty handle, and the reply schema put `target` into
`params["target"]`. The world takes the full affordance as params (the simple backend sends the affordance's keys
minus action, score, legal and reason), so a model reply such as `{"action":"work","target":"burn charcoal"}` could
not run. Now a reply that names a row by its handle runs that row.

### Files

Created:
- `domains/affordance_handles.py`: `base_handle(row)`, `affordance_handles(rows)` (one handle per row, in order, with
  `#2`, `#3` suffixes for collisions) and `handle_pairs(rows)`. Pure; no pack data.
- `tests/test_phase054_actionable.py`: 19 tests (fake providers; town100 seed 305000 for the world tests).
- `docs/phases/phase054/behaviour_followup.json`, `log_measure_followup.txt`, `full_suite_followup.log`,
  `selftest_bigville_followup.txt`, `selftest_test_hamlet_followup.txt`.

Changed (own files of this tract):
- `domains/agent_view.py`: `_can` takes each row's handle from `handle_pairs(world.actor_affordances(actor))`, computed
  over every option, not only the moves to known places. Removed the (handle, verb, what) dedupe, which can no longer
  drop a row because handles are unique. Import `from domains.affordance_handles import handle_pairs` added above
  `from domains.data_view import entities`.
- `bigville/backends/reply_schema.py`: `bind_row(name, handle, affordances, pack)`, `_names_action`, `_NOT_PARAMS`.
  `_fold_action(action, pack, affordances=None)`: when a row binds, the proposal's action is the row's world action
  and its params are the row's keys minus action, score, legal and reason, overlaid with the model's own params
  (except `target`). `to_wire(parsed, pack, *, text_limit=None, affordances=None)`: new keyword. Without
  `affordances`, the output is unchanged.
- `bigville/backends/llm.py`: `_check(raw, fields, affordances=None)` passes the rows to `to_wire`. `_ask` passes
  `context.affordances`.
- `packs/bigville/world/prompt_packet.json` and `packs/test_hamlet/world/prompt_packet.json` (identical): the
  `PROMPT_PACKET.interface` lines 3 and 4 now say: action is the action of a row in public.can, and target is the
  handle of that same row, copied exactly (or the handle of a thing from public.things for attempt). Both files
  match `tools/export_pack.py` output byte for byte (checked into a temp directory; no other file was rewritten).
- `tests/test_phase054_llm_prompt.py`: the fixed view's `can` row carries `"handle": "work:bake bread"` (was `""`),
  which is the handle the fixed context's affordance gets. The other 35 tests are unchanged.
- `tests/fixtures/phase054_packet_snapshot.json`: regenerated with the test's own serialisation. The diff is only:
  the `can` handle, the `can` size (56 to 71), the system size (4872 to 4921), the total (1802 to 1817), the pack
  hash (the pack JSON changed) and the two interface lines in `system`.

No shared file was touched. There are no shared-file hunks in this follow-up.

### Handle rule

1. The world's `target` when non-empty. For move, transfer, fetch, put, lock, unlock and tend rows this is `target:N`,
   the key the world assigns to a place, a container or a person in one query. It is an index, not a quantity, and
   it carries no coordinate. It was already in the view before this follow-up. A strict reading of "no referee
   numbers" would exclude it; I kept it because the brief names the world's `target` as the first choice.
2. Otherwise `action:recipe` (`work:burn_charcoal`), then `action:sow_kind:land`, then `action:kind` (`eat:bread`),
   then `action:animal`, then the action alone (`rest`, `sleep`).
3. A collision gets `#2`, `#3`, ... in the world's row order.

On the town100 seed 305000 world at turn 0, the first 100 residents have no duplicate handles and no empty handles
(checked directly). The handles are the same on two builds of the seed (a test).

### Binding (the LLM path only)

- Handle given: the row whose handle equals it, and that names the same action. The action may be the world's name
  (`move`) or the view's word for it (`walk`, from ACTION_WORDS). The proposal gets the world's action name.
- No handle: the row, if exactly one row has that action. Several rows: no binding, and the world decides.
- `attempt` never binds. Its target stays a thing handle from public.things.
- No match: the model's params pass through unchanged. The world refuses them.

### Results

- `python3 domains/bigville_entities.py`: exit 0. ERRORS (0), WARNINGS (0). Output `selftest_bigville_followup.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. ERRORS (0), WARNINGS (0). `selftest_test_hamlet_followup.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase054_actionable.py`: 19 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase054_llm_prompt.py`: 36 passed (after the fixture and
  snapshot change above).
- Full suite (`timeout 1500 python3 -m pytest -q -p no:cacheprovider`, 590 s): **1527 passed, 2 skipped, 3 failed**.
  Log: `full_suite_followup.log`. The 1508 of the phase is now 1527: the 19 new tests. The 3 failures are the same
  Ocelot adapter tests as before (`test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`). On a clean `git archive HEAD`
  copy with the three untracked test files added, all three fail too: two with `No module named
  'bigville.game_persistence'` and `'bigville.mixed_ocelot_scenario'`, one with `No module named
  'worlds.bigville_ocelot_adapter'`. They do not depend on this follow-up.
- Simple-backend behaviour (`PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label followup
  --turns 60 --out docs/phases/phase054/behaviour_followup.json`): compared with `behaviour_head.json` on every field
  except `elapsed_seconds` and `label`. Identical on all 14 compared fields (action counts: eat 5, move 3333, none
  1050, rest 1549, sleep 48, work 15; 300 utterances; hunger mean 2.4309).

### Tests

- `test_every_can_row_of_a_sample_resident_becomes_the_simple_backends_proposal_for_that_row`: 20 residents (every
  fifth in sorted order), 139 `can` rows in all. Each row, sent as `{action, target: handle}`, gives an
  `ActorResponse` with the row's world action and params equal to the affordance's keys minus the four excluded.
- `test_the_simple_backend_proposal_is_one_of_the_rows_params_as_the_tests_mirror_them`: the simple backend's own
  choice for the same residents equals a row's params, once the CAN scores are removed (see below).
- `test_an_llm_resident_replying_with_a_work_row_is_enacted_by_the_world_in_one_turn`: town100, one LLM resident with
  a fake provider replies with a `work` row from its own `can`. `game.step()` runs. `last_results` is True.
- `test_a_work_reply_with_no_row_is_refused_by_the_world_as_a_known_reason`: an unknown handle reaches the world, which
  refuses it with `malformed` (a REFUSAL_REASONS code). It was not `unsupported` or `unknown_target`.
- Collision tests (suffixes, no clash with a later row), the handle rule, determinism of the function, and no
  coordinates in any sampled handle. A handle is a plain name (`[a-z_]+(:[a-z0-9_]+)*(#n)?`); a digit appears only in
  `target:N` and in a suffix.
- Binding unit tests: full row with the model's intensity and tool laid over; a move keeps its destination; a view
  word (`walk`) names the row; action-only binds only when exactly one row has the action; an unknown handle or a
  handle of another action passes through; `attempt` keeps its thing handle; without affordances, `to_wire` is as
  before.
- The packet interface names the rule (`handle of that same public.can row`).

### Deviations and observations

- **CAN scores are not in the LLM proposal.** The simple backend's proposal also carries `psi`, `can`, `can_concepts`,
  `weighted_score` and `decision_model`, which `bigville/backends/psi_can.py` adds to the chosen option. These are the
  resident's own scores, not world facts. The world does not read them, and the LLM path has no way to make them.
  The brief's "same dict" therefore means the affordance-derived keys, which the tests compare exactly.
- **The view's word for an action** (`walk`, `hand over`, `move something`) is accepted with the handle. The proposal
  takes the world's name (`move`). Without this, a model copying `action` from `can` would name `walk`, which the
  world does not know.
- A handle is the one thing the reply names. A model that gives a handle with a wrong action gets no binding, and
  the world refuses the wrong action or target.
- In the LLM path, a model's own params overlay the row's params, except `target`. A model can therefore change a
  row's `destination` or `recipe`. The world validates the result; it does not check against the row.
- The deviation count compares (action, target) with the autopilot's choice, as before. A `work` proposal has an
  empty target, so a reply that picks a different recipe is not counted as a deviation. Before and after the follow-up
  the count works the same way.

### Limits

- No live provider. Whether a real model writes the handle correctly is not measured.
- Handles for moves are `target:N`. The index is assigned per call to `actor_affordances`, so it can change when the
  option list changes. The model is asked with the handles of the turn in which it is asked, so a reply made in that
  turn names the right row. The `continuation` task of a reply is not bound to a handle by this follow-up. It keeps
  the action and params the model wrote.
- Human-readable names for moves (`walk to the bakery`) would need suffix rules and a collision check of their own.
  Not done.
- The 100-resident LLM town was not run.

### Open questions

1. `target:N` as a handle: it carries a number (an index, not a quantity). Keep it, or replace move handles with a
   name that uses only the place name, plus a suffix for repeats?
