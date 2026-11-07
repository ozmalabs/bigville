# Phase 069: the body as a unit (afferents, sounds and a background feeling)

## Summary

The body is now an object with two outputs. `worlds/body.py` holds the `Body` interface and
`WorldBackedBody` (the human embodiment), which reads the world's existing accessors and moves no state.
A mind now sees its body as a background feeling and a short list of felt signals. Each signal is a sound
and a rough place (for example "hnnnnn hnnnnn..." in the torso), with no cause. The referee block shows the
true source, quality and locus beside each signal.

`interoception` is `felt` by default in agent mode and `labelled` (the Phase 052 words) in referee mode and
when asked. The self-test passes with 0 errors and 0 warnings. The 60-turn and 200-turn simple-backend
village runs give the same digest as the snapshot of the tree before this phase, with 0 deaths in both.
The full suite has 2294 passed and 10 failed. Four failures are the baseline HTTP/TUI tests in
`test_phase057_tui.py`, one is a browser test that also fails at baseline, three are Ocelot import failures
from the other session's files, one is the Phase 031 schema literal, and one is the Phase 054 snapshot.

## Changes

### Created

- `worlds/body.py`: `Body` (interface: `reads`, `afferents`, `referee`, `capacities`, `facts`,
  `observable`, `apply`, `tick`, `dump`/`load`), `WorldBackedBody`, `EMBODIMENTS` (registry, key `human`),
  `NO_BODY = "none"`, `BodyMixin` (the world hooks `_body_init`, `body_of`, `_body_tick`, `_body_event`).
- `domains/interoception.py`: pure functions. `draw` (sha256 keyed draw), `depth_of`, `resolve`, `max_depth`,
  `intensity_of`, `acuity_of`, `raw_depth`, `chosen_depth`, `stretch`, `trend_of`, `sound`, `level_of`,
  `derive`, `felt_body`, `referee_block`, `render_felt_body`, `normal_letters`, `intensities`.
  `READS` lists the body reads.
- `domains/interoception_check.py`: self-test checks (trees, vocalisations, channel caps, sources, patterns,
  depth rule, acuity, attention, feeling levels, felt keys).
- `packs/bigville/world/interoception.json` and `packs/test_hamlet/world/interoception.json` (identical).
  Tables: `ANATOMY`, `QUALITY_TREE`, `VOCALISATIONS`, `CHANNELS`, `SIGNAL_SOURCES`, `PATTERNS`, `FEELING`,
  `INTEROCEPTION`. Written in the exporter's layout (checked by `export_pack.py` in a temp copy).
- `tests/test_phase069_body.py`: 31 tests.
- `docs/phases/phase069/`: this report, self-test outputs, digests, the suite log, the seeds check.

### Changed (new data and rows)

- `packs/bigville/world/agent_view.json` and the hamlet copy: body whitelist gains `feeling` and `signals`;
  new sections `feeling` (sound, level) and `signal` (sound, where); referee whitelist gains `interoception`.
- `packs/*/world/actor_defaults.json`: `embodiment: "human"` on ACTOR_DEFAULTS (one line, before `body`).
- `packs/bigville/world/animals.json`: `embodiment: "none"` on the 8 ANIMALS rows (see Deviations).
- `packs/*/pack.json`: 8 manifest rows for the new tables, inserted at the top of `tables` (lines 9 to 16),
  well away from the other session's rewritten block near line 868.

### Changed (shared files; my hunks only)

- `worlds/bigville_world.py`:
  1. import `from worlds.body import BodyMixin`, after `DEFAULT_DATA_PACK`.
  2. class line: `class BigvilleWorld(BirthsMixin, BodyMixin):`. This shares a line with an uncommitted
     `BirthsMixin` edit that is not mine (Phase 044). The two edits are on one line, so they cannot be
     committed as separate hunks.
  3. `add_actor`, after `self._bodies[name] = body`: `self._body_init(...)`.
  4. `_drop_health`, after `last_cause`: `self._body_event(...)` with kind `harm`. It validates the event and
     changes nothing.
  5. `tick`, after `self._holds_tick()`: `self._body_tick()`. It stores each body's last intensities.
- `domains/world_affordances.py`: 8 bindings (`ANATOMY`, `QUALITY_TREE`, `VOCALISATIONS`, `CHANNELS`,
  `SIGNAL_SOURCES`, `PATTERNS`, `FEELING`, `INTEROCEPTION`), after `RESIDENT_CONCEPT_SEEDS`.
- `domains/bigville_entities.py`: two lines, the call to `check_interoception`, after `_check_health`.
- `domains/agent_view.py`: `INTEROCEPTION_MODES`; `_felt_body`; `_self(..., interoception)`;
  `build_agent_view(..., interoception=None)`; `_referee` adds `interoception` (`body.referee()`).
- `domains/agent_view_check.py`: `SECTIONS` gains `feeling` and `signal`; new `felt_body_problems(body,
  pack, *, anatomy, vocalisations)`, the leak rule.
- `bigville/game.py`: `agent_view(actor, mode, interoception=None)` passes the switch through (one method).
- `bigville/backends/prompt_packet.py`: `PACKET_SCHEMA` is `bigville/prompt/4` (line 31).

### Tests changed (old -> new, reason)

- `tests/test_phase052_agent_view.py`, three call sites now pass `interoception="labelled"`:
  - `test_numbers_are_in_the_words_and_never_as_numbers`: the test reads `body["energy"]` and `body["hunger"]`,
    which are labelled keys. Its assertions are unchanged.
  - `test_the_referee_mode_adds_numbers_and_the_agent_mode_does_not`: `agent = agent_view(mode="agent",
    interoception="labelled")`, so the comparison with the labelled referee `self` still holds.
  - `test_the_hamlet_pack_gives_a_view_with_its_own_words`: the hamlet body's `energy` key is labelled.
- `tests/test_phase054_llm_prompt.py::test_the_packet_uses_the_packet_schema_and_the_pack_hash`:
  `"bigville/prompt/3"` -> `"bigville/prompt/4"`. Reason: the schema rises for the felt body.
- `tests/test_bigville_backends.py`: two literals `bigville/prompt/3` -> `bigville/prompt/4` (lines 28 and 38).
  Same reason.

Not edited: `tests/test_phase031_llm_backend.py` (line 127 pins `bigville/prompt/3`, and the file belongs to the
other session); `tests/fixtures/phase054_packet_snapshot.json` (the supervisor regenerates it).

## Design

- **Outputs.** `capacities()` is exact: strength, stamina, speed factor and `alive`, all from the world.
  `afferents()` is what the mind may feel. `observable()` returns `observable_marks` (Phase 063).
  `referee()` is the truth. `facts()` gives asleep and collapsed.
- **Reads.** Hunger, exertion (stamina less reserve, over stamina), exhaustion (band step / 3), chill,
  wetness (mark level), illness (disease flag), intoxication, and harm (1 - health). Every value comes from an
  existing accessor. No world state is duplicated.
- **Depth rule.** `raw = base + 2 x intensity + (acuity - 1) + attention - 1.5 x impairment + jitter`, with
  jitter in [-0.25, 0.25] from a sha256 draw keyed on (seed, resident, turn, source). Depth on each tree is
  `floor(raw)`, clamped to 0 .. min(channel cap, true node depth). Raising intensity, acuity or attention
  never resolves shallower; impairment never resolves deeper.
- **Channels.** visceral: quality 1, place 1. general: 1, 1. deep: 2, 2. surface: 2, 3. A visceral place can
  never be deeper than "torso".
- **Sounds.** The form is chosen by a draw keyed on (seed, quality node), so residents who feel one node say
  one sound. The first vowel stretches by 1 + round(3 x intensity). Patterns add a repeat and a tail.
  Trend (rising or fading against the last tick) overrides the source's pattern.
- **Background feeling.** Sum of all intensities (felt or not), capped at 1. Sounded from the root "bad",
  with a level word (faint, clear, strong).
- **Acuity.** Drawn once per resident from [0.7, 1.3] (sha256 keyed on seed and name), times the life-stage
  factor. Stored in the body's state.
- **Attention.** Asleep 0, absorbed in a timed job (`busy`) 0.5, idle 1.
- **Shared sounds on purpose.** Hunger (visceral, quality `hunger`) and exhaustion (quality `drained`, place
  `torso`) both resolve to the sound "hnn" at place "torso". The referee block shows the two true sources.
- **Storage.** World state for a body is a plain dict, `world.embodiment[actor]` (`embodiment`, `seed`,
  `acuity`, `previous`). The body objects are built from it on demand (`body_of`), so the world never holds an
  object of an unknown class.

## Data and sources

Every number in `interoception.json` is APPROX. No source was checked, because the phase had no literature
to cite. The figures are model choices of the right order. The anatomy and the sound forms are authored
for this model. The acuity range, the depth weights, the floors, ceilings, awareness levels, channel caps,
pattern tails and feeling levels are all APPROX. `strength` and `stamina` in the felt view use the existing
lexicon phrases. Mood is not a source (see Open questions).

## Validation

Commands and results (live tree, after all edits):

- `python3 domains/bigville_entities.py`: ERRORS (0), WARNINGS (0), exit 0. Output in
  `docs/phases/phase069/selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: ERRORS (0), WARNINGS (0), exit 0. Output in
  `selftest_test_hamlet.txt`.
- `python3 tools/generate_seeds.py --check`: exit 0, output in `generate_seeds_check.txt`.
- Exporter layout: `tools/export_pack.py` run in a temp copy (`/tmp/exp069`). Its `interoception.json` output
  was copied back, and the `agent_view.json`, `actor_defaults.json`, `animals.json` and `pack.json` files were
  byte-identical to the exporter's output. `tests/test_phase013a_packs.py` passes.
- `tests/test_phase069_body.py`: 31 passed.
- `tests/test_phase052_agent_view.py`: 26 passed (after the three call-site changes).
- Digest, 60 turns (`docs/phases/phase063/compare60.py` run on the snapshot and on the live tree; the snapshot is
  the live tree before this phase's edits): both `f334f71ecf7088d39001f5343cbcbbd32f9ae01a6e184c776bd69bbbe97b6f9b`,
  0 deaths. Files: `village_60_digest_{base,new}.json`.
- Digest, 200 turns: both `eadc65c66dcb26623e2de301ce54b026e8419f6e5585d6142982cb6561043e78`, 0 deaths.
  Files: `village_200_digest_{base,new}.json`. The digest runs were started before the `tables` rename and the
  `_body_apply` to `_body_event` rename. Neither changes behaviour, and the full-suite run after them passed the
  static test.
- Full suite on the live tree, `python3 -m pytest -q -p no:cacheprovider -n 6 --continue-on-collection-errors`
  (pytest-xdist is installed; I used it for time): **10 failed, 2294 passed, 6 skipped, 1 error** (760 s).
  Log: `docs/phases/phase069/full_suite.log`. Failures:
  - Ocelot, `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` (the other session's files):
    `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `tests/test_mixed_ocelot_checkpoint_parity.py::...midpoint_checkpoint_matches_uninterrupted_control`,
    `tests/test_mixed_ocelot_village.py::...runs_multiple_turns_and_rejects_invalid_action`. These are the three
    named in the brief.
  - Schema literal (my bump): `tests/test_phase031_llm_backend.py::test_callable_provider_is_accepted`
    (`assert ['bigville/prompt/4'] == ['bigville/prompt/3']`). Flagged, not edited (see Decisions).
  - Snapshot (my bump): `tests/test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`.
    The fixed view is hand-built, so the only difference is the schema string. The supervisor regenerates the
    fixture.
  - Baseline (the snapshot run fails the same ones): four `tests/test_phase057_tui.py` HTTP tests
    (`over_http_*`, `the_server_refuses_a_bad_reply...`) and `tests/management/test_reports_browser.py::
    test_reports_events_pagination_and_json_download_without_advancing`.
  - Collection error at baseline too: `tests/test_phase044_births.py` shadows
    `docs/phases/phase044/files/tests/test_phase044_births.py` (import file mismatch).
  - Baseline snapshot, same command: 7 failed, 2260 passed, 12 skipped, 1 error. Its `test_compare_browser`
    failed in that run only and passed in the live run, so it is timing-sensitive under `-n 6`.
    `tests/test_phase055_concurrency.py` also varies under load and passed in the rerun.
- `test_bigville_world_migrated.py::test_no_python_decides_the_world` failed on the first live run because my
  method name `_body_apply` contains `_apply`, a forbidden substring. Renamed to `_body_event`; it passes now.
- Checkpoint probe (not a test): `world_persistence.save_world_checkpoint` then `load_world_checkpoint` on the
  town100 world restores `embodiment` (100 residents, identical dict for the player).

## Limits

- The sound, depth and interoceptor numbers are APPROX and untested against any physiology.
- The felt view was checked on the founding town at a few states (hunger 0.9 to 2.5, fever, a clean resident).
  No 100-resident run with the felt view was done, and none was asked for.
- `apply()` validates events and changes nothing. Routing covers `harm` only, and only as an event. The
  world does not use body events for anything yet.
- Tests build their own pack copy for "a different pack gives different sounds". The pack copy is loaded
  from a directory in `tmp_path`, so the check runs through `load_pack`.
- The LLM packet body was built once (a felt view for a town resident): 330 characters, under the 600-character
  `body` cap. No live LLM run was made.

## Deviations

1. **`self.embodiment` holds plain dicts, not objects.** The brief says the attribute holds the body objects.
   The world checkpoint encodes every world attribute, and it rejects unknown object types. So the world holds
   the body state as plain dicts and builds the objects on demand (`body_of`). Checkpoint probe passes.
2. **Animals use `embodiment: "none"`, not `"human"`.** Animals have no body object in this phase. A `"human"`
   key would be false, so `none` is registered as "no body".
3. **`interoception` is a switch on `build_agent_view` and on `game.agent_view`, not a scenario JSON key.**
   Scenario definitions carry metadata only, and no scenario reader for the switch exists. Agent mode defaults
   to `felt`. Referee mode defaults to `labelled` in `self.body`, and carries the felt view and the truth in
   `referee.interoception`. The brief did not say what referee mode shows in `self.body`.
4. **Strength and stamina stay in the felt body** (as lexicon phrases, from the body's capacities), as the
   brief allowed.
5. **The schema bump touches two tests outside my brief's files** (`tests/test_bigville_backends.py`, updated;
   `tests/test_phase031_llm_backend.py`, not updated).
6. **Stub embodiment.** The test's stub reads `itch` and `harm`. `derive` does not check reads against
   `READS`; the self-test does, for the pack's sources. A new embodiment's reads are its own.

## Open questions

1. **Mood.** Mood stays a separate lexicon word and is not a source. Should it join the background feeling?
2. **Trend.** Trend uses the last tick's intensity. Should a view taken between ticks show it too?
3. **Referee `self.body`.** Should referee mode show the felt body in `self.body` too? I kept the labelled
   words, as the brief implies.
4. **Phase 031 test.** `tests/test_phase031_llm_backend.py:127` needs `bigville/prompt/4`, or the schema
   bump needs to go in a separate commit with that test.
5. **Animals.** Should ANIMALS get a `none` key permanently, or a real embodiment in Phase 070 or later?

## Hand-offs

- **TUI (`bigville/tui`, not edited).** `bigville/tui/narrate.py::body_lines` reads `energy`, `hunger`, `health`,
  `mood`, `asleep`, `collapsed` and `ill` from `self.body`. The felt body carries none of the first four or
  `ill`, so the TUI would show no feelings. The TUI needs to call
  `domains.interoception.render_felt_body(view["self"]["body"])` for the felt body, or pass
  `interoception="labelled"` to `game.agent_view` to keep its lines. `asleep` and `collapsed` are still keys.
  Its tests (`tests/test_phase057_tui.py`, `tests/test_phase067_tui_modes.py`) use fixtures, so they still pass.
- **Persistence (`game_persistence.py`, `world_persistence.py`, not edited).** The world holds a new attribute,
  `embodiment`, of plain dicts. `world_persistence` carries it (probe above). The game-level checkpoint has
  not been checked. The body's `dump()`/`load()` round-trips in a test.
- **Snapshot.** `tests/fixtures/phase054_packet_snapshot.json` needs regenerating: the schema string only.
- **Phase 065 and 070.** `derive` takes its inputs as data, so 065 can add a source row (numbness) and 070 a
  located-harm read.

## Files

Created: `worlds/body.py`, `domains/interoception.py`, `domains/interoception_check.py`,
`packs/bigville/world/interoception.json`, `packs/test_hamlet/world/interoception.json`,
`tests/test_phase069_body.py`, `docs/phases/phase069/*`.

Changed: `worlds/bigville_world.py`, `domains/world_affordances.py`, `domains/bigville_entities.py`,
`domains/agent_view.py`, `domains/agent_view_check.py`, `bigville/game.py`, `bigville/backends/prompt_packet.py`,
`packs/bigville/pack.json`, `packs/test_hamlet/pack.json`, `packs/*/world/actor_defaults.json`,
`packs/*/world/agent_view.json`, `packs/bigville/world/animals.json`, `tests/test_phase052_agent_view.py`,
`tests/test_phase054_llm_prompt.py`, `tests/test_bigville_backends.py`.

Not committed. Not staged.
