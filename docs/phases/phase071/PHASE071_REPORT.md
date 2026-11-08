# Phase 071: attending and pressing

## Summary

A resident can now look into one felt signal (`attend`) and probe a region of its own body (`press`).
Attending is a major action. It holds the resident's one major action slot for its turn, and the attention then
runs `ATTEND.ticks` (3, APPROX) world ticks. During that time the attended signal gets one more depth step of
acuity and full attention, every other signal's attention is capped at 0.5, and the resident's other major
actions are refused with the reason `attending`. Pressing reacts with a sound that depends on how much of the
true sources lies under the pressed region, and pressing a hurt place raises it briefly.

Neither action is offered to the simple backends. The world's `actor_affordances` is unchanged. The attend rows
appear only in the agent view's `can`, built from the body. The simple village is unchanged: the 60-turn and
200-turn digests equal the base tree, with 0 deaths.

Self-test: 0 errors, 0 warnings. New tests: 21 in `tests/test_phase071_attend.py`, all pass. Full suite:
17 failed, 2347 passed, 6 skipped, 2 collection errors (see Validation). The Phase 054 snapshot failure is the
expected one, and the fixture was not edited.

## Changes

### Created

- `domains/attend_commands.py`: the terminal words for attend and press (`parse_line`). Not wired into the TUI (see
  Hand-off to the terminal interface).
- `tests/test_phase071_attend.py`: 21 tests (listed under Validation).
- `docs/phases/phase071/`: this report, the self-test and seeds outputs, the digests (base and new, 60 and 200
  turns), and `full_suite.log`.

### Changed, this session's own files (Phase 069 and 070 files, extended)

- `worlds/body.py`:
  - `pack_tables` loads `ATTEND`. `initial_state` adds `attending`, `pressed`, `probe`, `pending` and `counts` (plain
    values).
  - `located()` reads a pressed locus higher by `press_boost` while `pressed` holds it.
  - `focus()` and `_derive(use_focus=)`: the attention focus that `derive` uses.
  - `attend_options()`, `signal_named(handle)`, `start_attend(source)`, `press(region)`, `note_action()`,
    `_attend_tick()` (called from `tick()`), and `referee()['attending']`.
  - `BodyMixin`: `_attending_refusal`, `_body_attend` (stamina cost through the body node's `stamina_reserve`),
    `_body_press`, `_body_note_outcome`, `attention_report()`.
- `domains/interoception.py`: `derive(..., focus=None)` (the acuity bonus and attention budget; rows gain
  `focused`), `within(tree, node, region)`, `press_sound(tables, total)`.
- `domains/interoception_check.py`: `ATTEND` is required; `_check_phase071` checks the numbers, the press ladder
  (starts at min 0, rises, sounds letters-only or null), `verb_aliases`, the remedies (each names a source), and the
  `attending` refusal code.
- `packs/bigville/world/interoception.json` and `packs/test_hamlet/world/interoception.json` (identical): new
  `ATTEND` table (`ticks`, `acuity_bonus`, `focus_attention`, `other_attention`, `stamina_cost`, `press_boost`,
  `press_ticks`, `remedy_window`, `verb_aliases`, `press_sounds`, `remedies`). All numbers APPROX.

### Changed, shared files (my hunks only)

- `worlds/bigville_world.py`, four hunks, none adjacent to another session's hunk:
  - `_attempt`: the `sleep_code` expression also reads `_attending_refusal(actor, action)`.
  - `_major_action_attempt`: `attend` and `press` branches after the `sleep` branch.
  - `_enact_plan`: `attend` and `press` pass `target` to `major_action`, after the `sleep` branch.
  - `_publish_outcome`: one call, `_body_note_outcome(actor, action, applied)`.
  Phase 069 and 070 hunks are unchanged.
- `bigville/reporting.py`: `game_report()`, one line: `report["attention"] = game.world.attention_report()`.
  `world.report()` is not changed, so `export_state()` and the digest are unchanged.
- `domains/world_affordances.py`: `ATTEND = _PACK["ATTEND"]` after the Phase 070 bindings.
- `domains/agent_view.py`: new `_attend_can` (before `_last`); `_last` adds `sound` and `place` for an applied attend
  or press; `build_agent_view`, the `can` line, appends `_attend_can`.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: one manifest row each, `ATTEND`, after `OBSERVABLE_SIGNS`.
- `packs/bigville/world/major_actions.json`: `attend` and `press` (kind `perception`, with descriptions).
- `packs/bigville/world/refusal_reasons.json` and `packs/test_hamlet/world/refusal_reasons.json`: `attending`, before
  `exhausted`.
- `packs/bigville/world/agent_view.json` and `packs/test_hamlet/world/agent_view.json`: `last` whitelist gains
  `sound` and `place`; a `silence` word in `VIEW_WORDS`; bigville `ACTION_WORDS` gains `attend` and `press`.

### Not changed

- `domains/affordance_handles.py`: not needed. Attend rows use the `target` key (`signal:N`), which the handle function
  already reads.
- `packs/bigville/world/lexicon.json`: the `press` verb alias stays `push` (see Decisions).
- `bigville/tui/*`, `bigville/backends/*`, `bigville/game.py`, `game_persistence.py`, `world_persistence.py`.
- `tests/fixtures/phase054_packet_snapshot.json`.
- No existing test was edited.

## Design

- **Attend.** `attend` takes a handle `signal:N` (N counts the felt signals from 1 in view order). The
  focused signal's acuity is raised by `acuity_bonus` (1.0, one depth step at `acuity_weight` 1), so its depth is
  bounded by the acuity plus the bonus, and by the channel cap and the true node's depth. Full attention applies to it.
  Every other signal's attention is min(own, `other_attention`). The attend costs `stamina_cost` (0.02) of
  `stamina_reserve`, which the world writes on the body node. It is refused with the reasons `asleep`, `collapsed`,
  `attending` or `unknown_target`, and nothing else.
- **Press.** `press <region>` takes an ANATOMY node. The reaction is the highest `press_sounds` row at or below
  the summed raw intensity of the true sources whose locus lies in that region's subtree. A null sound is silence.
  Pressing a region with a located injury raises that locus by `press_boost` (0.3) for `press_ticks` (4) ticks.
- **Timers.** The attention and the press boost count down in `tick()`. Falling asleep ends the attention.
- **Visibility.** `last` for an applied attend or press carries `sound` and `place` (for silence, the word `nothing`).
  It names no cause. The felt body (`self.body`) shows the focused depth while attending, because the body derives
  the view with the focus. The leak rule passes.
- **Referee measure.** `counts` (attends, presses, depth gained, remedied) are in the body. An attend opens a pending
  record for `remedy_window` (6) turns. A successful major action in the attended source's `ATTEND.remedies` row
  counts once as acting on the true source. Remedies are a referee table only. The world never reads them to choose
  or to name a cause. A located source is matched on its base name (`injury_sharp@arm` is `injury_sharp`).
- **State.** Everything is plain values in `world.embodiment[actor]`. `dump()`/`load()` round-trip with attention
  and presses in place (tested).

## Data and sources

All numbers in the `ATTEND` table are APPROX: the ticks, the bonus, the attention budget, the stamina cost, the press
boost and ladder, the remedy window and the remedies table. No source was consulted for them. `remedies` is a
model choice (for example, hunger is remedied by `eat`, and a sleep debt by `sleep`).

## Changed numbers

None of the existing numbers changed. No existing assertion was edited.

## Validation

Commands (live tree, after all edits; each command's output is in this directory):

- `python3 domains/bigville_entities.py`: ERRORS (0), WARNINGS (0), exit 0. Output: `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: ERRORS (1), exit 1. The one error is
  `DEPENDANTS: 'infant' is not a REFUSAL_REASONS code`, from the other session's untracked
  `packs/test_hamlet/world/dependants.json`. The same error is present on the base copy (`/tmp/base071`). Output:
  `selftest_test_hamlet.txt`.
- `python3 tools/generate_seeds.py --check`: exit 0, 31 files match. Output: `generate_seeds_check.txt`. No
  regeneration was needed.
- Exporter layout: `tools/export_pack.py --pack bigville --out /tmp/exp071` and `--pack test_hamlet --out /tmp/exp071h`.
  The files I changed are byte-identical to the exporter's output in both packs (`pack.json`, `interoception.json`,
  `refusal_reasons.json`, `major_actions.json`, `agent_view.json`, `lexicon.json` in bigville).
- Digests (`docs/phases/phase070/compare_digest.py`, simple backend, town100, seed 305017):
  - 60 turns: base and new both `f334f71ecf7088d39001f5343cbcbbd32f9ae01a6e184c776bd69bbbe97b6f9b`, 0 deaths.
  - 200 turns: base and new both `eadc65c66dcb26623e2de301ce54b026e8419f6e5585d6142982cb6561043e78`, 0 deaths,
    marks identical (100 residents with marks; `mark_dirt` 2.08, `mark_wetness` 50.0).
  - The base is a copy of the working tree before any Phase 071 edit (`/tmp/base071`).
- New tests: `python3 -m pytest -q -p no:cacheprovider tests/test_phase071_attend.py`: 21 passed.
  Covered: the gut-signal cap and bonus bound; a surface signal resolving deeper than a visceral one; other signals
  shallower or equal while attending; refusal asleep and collapsed with a recorded reason; a second attend and eating
  refused while attending; the stamina cost; `unknown_target`; three presses narrowing to upper belly with chest and
  arm silent; a pressed injury raised by `press_boost` and back after `press_ticks`; press refused asleep; attend and
  press not in the simple backends' affordances; no cause in `last` or the view, and the leak rule; attend rows as
  `signal:N` in `can`; a reply that names a handle enacts the attend; the same seed repeats; dump/load round-trip;
  the report counts and the remedy count; the report stays out of `world.report()`; the terminal words; the
  self-test catches a bad remedy source, a bad press ladder, a missing `attending` code and a bad sound.
- Related tests, run before the suite: `tests/test_phase069_body.py`, `tests/test_phase070_locus.py`,
  `tests/test_phase052_agent_view.py`: 79 passed.
- Full suite: `timeout 1800 python3 -m pytest -q -p no:cacheprovider -n 6 --continue-on-collection-errors`
  (xdist, as in Phase 069 and 070), log `full_suite.log`: **17 failed, 2347 passed, 6 skipped, 2 errors** (935 s).
  - Failures present in the Phase 070 report (15): `test_phase004_located_gathering` (hamlet self-test,
    DEPENDANTS), `test_phase013a_packs::test_export_rerun_is_byte_identical` (other session's `dependants.json`),
    `test_phase013b_data_pack` (hamlet check), `test_phase014_parameters` (hamlet), `test_phase016a_founding_town`
    (hamlet), `test_phase009_kinship` and `test_phase011_fiscal` (hamlet), four in `test_phase057_tui.py`
    (baseline HTTP/TUI), `test_phase055_concurrency` (a timing test; it passes alone), and three Ocelot import
    failures (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`, from the other session's files):
    `test_bigville_ocelot_communication`, `test_mixed_ocelot_checkpoint_parity`, `test_mixed_ocelot_village`.
  - New in this run, from this phase: `test_phase054_llm_prompt::test_the_packet_matches_the_snapshot_for_a_fixed_view`.
    The `system` section of the packet grows from 5688 to 5954 characters, which is the two new MAJOR_ACTIONS entries.
    The fixture is not edited; the supervisor regenerates it.
  - One more failure appeared that passes alone: `tests/management/test_reports_browser.py` (a Playwright check of
    `#report-provenance` text, which was empty under the 6-worker load). `pytest tests/management/test_reports_browser.py`
    gives 1 passed.
  - 2 collection errors: `test_phase044_births` and `test_phase045_dependants` (the same import-name mismatch as Phase 070).

## Hand-off to the terminal interface (bigville/tui/commands.py, not edited)

- `domains.attend_commands.parse_line(text, pack)` returns `{"major_action": {"action": "attend", "target": "signal:N"}}`
  or `{"major_action": {"action": "press", "target": "<anatomy node>"}}`, or `None` for any other line.
- In `commands.parse`, call it before the `_can_rows` path and before the physical `_attempt` route, and return
  `Parsed("propose", reply=...)` when it is not `None`. `press` must be tried first, because `press` is an alias
  of `push` in VERB_ALIASES.
- `commands.placed` must also return `True` when `parse_line` is not `None`. Otherwise text mode asks again for
  `attend` and `press`.
- The reply then goes through the terminal's usual `reply_schema.to_wire(reply, pack, affordances=...)` and
  `submit`. The world receives `{"action", "target"}` through `enact_plan`.
- `last` carries `sound` and `place` for an applied attend or press. A terminal that shows `last` can print them
  beside `action` and `outcome`. For the felt body, `self.body` already carries the focused signals.

## Decisions

1. **Publication.** The attend rows are in the agent view's `can` only (handles `signal:N`), and the actions are in
   `MAJOR_ACTIONS` (bigville). They are not in `world.actor_affordances`, so the simple backends see nothing new.
   The LLM reply path binds no row for `signal:N` and passes the target through, so no change to
   `reply_schema.py` or `llm.py` was needed.
2. **Major, not free.** Attend and press use the slot. While attention runs, every other major action is refused
   with `attending`, including eat, rest, sleep and walking. A resident can still speak (a free action). This was
   chosen to give attend the timed-occupation semantics of the brief. If the other actions should stay open, the
   refusal in `_attempt` is one line to remove.
3. **Verb aliases.** The brief asked for the lexicon's verb aliases. `VERB_ALIASES` maps to the physical attempt verbs,
   and the lexicon check requires each canonical verb to be in `VERBS`. Adding `attend` or `press` there would make
   them attemptable physics. `press` already means `push`. The aliases are in `ATTEND.verb_aliases` instead, and
   the lexicon is unchanged.
4. **Visceral signals do not deepen.** Hunger, illness and intoxication are visceral (caps 1 and 1), so attending
   to them changes no sound. Surface and deep signals (injury, chill, exertion, deficiency) can deepen. This follows
   the channel rule in the brief; it limits what attend can show.

## Limits

- No village run with attend or press was made. The effects are checked only in unit and world tests.
- The attend bonus, the attention budget, the stamina cost, the press ladder and boost, and the remedies are
  unmeasured (APPROX).
- The "acted on the true source" count depends on the referee remedies table. It is a measure, not an attribution.
- Persistence: `world.embodiment` now holds the attend and press state. `game_persistence.py` and
  `world_persistence.py` are not wired (the other session's files).
- A resident is not told that it is attending (no fact in `facts()`).

## Open questions

1. Should the attending block cover eat, rest and sleep, or only other attends and presses?
2. Should `press` also raise a non-injured place? Currently it only probes.
3. Is the visceral cap right for an attend to hunger? Attend can never clarify it in the current pack.

## Follow-ups

- The supervisor regenerates `tests/fixtures/phase054_packet_snapshot.json` (the `system` section changed).
- The terminal hand-off (above).
- A village run with attend and press enabled, to measure how often they are used and whether the remedy count moves.
