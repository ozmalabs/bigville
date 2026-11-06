# Phase 052: the agent view, the one limited interface

## Summary

`BigvilleGame.agent_view(actor, mode)` builds the payload a resident may know: the character sheet, the
time and weather, the people and speech the resident can perceive, a terrain patch of the map, the
affordances the resident can use, and the outcome of the last action. Every section is built from a
whitelist kept in the pack, so a key outside its whitelist raises instead of reaching a reader. In agent
mode no number appears, only lexicon phrases, and no referee-only field appears. Referee mode adds a
`referee` block with the raw numbers.

The server gets `GET /api/view?actor=NAME`. In agent mode `/api/state` returns 403 and `/api/turn` returns
the view instead of the snapshot. The simple backends still receive their raw `ActorContext`.

Status: built and tested. Self-tests pass for both packs with 0 errors and 0 warnings. The full suite
passes on a frozen copy of the final tree (1414 passed, 8 skipped). The live working tree also contains
three Ocelot tests that fail on an import problem outside this phase (see Validation).

## Changes

### Created

- `domains/agent_view.py`: the builder, `build_agent_view(game, actor, mode)`. It reads the world through
  its query methods and does not call `game._context`, because that call advances the practice-record
  window a backend reads on its next context (a test checks this).
- `domains/agent_view_check.py`: the self-test checks (whitelist sections, referee-only names disjoint
  from the agent whitelist, every lexicon quantity a field uses, glyph coverage of `TERRAIN_MOVEMENT`,
  no digit in a fixed phrase, template fields, the knows cap, the sight range, `REFUSAL_REASONS`).
- `packs/bigville/world/agent_view.json` and `packs/test_hamlet/world/agent_view.json` (identical). Tables:
  `AGENT_VIEW_WHITELIST`, `AGENT_VIEW_REFEREE_ONLY`, `AGENT_VIEW_QUANTITIES`, `AGENT_VIEW_KNOWS_LIMIT`,
  `MAP_GLYPHS`, `VIEW_WORDS`, `PRECISION_WORDS`, `ACTION_WORDS`.
- `tests/test_phase052_agent_view.py`: 26 tests.
- `docs/phases/phase052/`: this report, the self-test outputs, the full-suite log, and the snapshot hashes.

### Shared or other-owned files (every hunk I added)

Anchors are the unchanged line directly before each hunk.

1. `bigville/game.py`, after the `persona` method. Anchor: `        return persona_card(self.characters[actor], self)`.
   Adds the method `agent_view(self, actor, mode="agent")`, with a docstring, that calls
   `domains.agent_view.build_agent_view`.
2. `bigville/backends/protocol.py`, in `ActorContext`. Anchor:
   `    recipient_interfaces: dict[str, dict[str, Any]] = field(default_factory=dict)`.
   Adds a comment and the field `agent_view: dict[str, Any] | None = None`. Nothing populates it yet
   (054 will).
3. `domains/bigville_entities.py`, the self-test. Anchor: `    check_persona(_WORLD_PACK.path, errors, warnings, info)`.
   Adds two lines: the import of `check_agent_view` and its call on `_WORLD_PACK.path`.
   Another session changed the comment on the `check_persona` import line in the same block. I did not
   touch that line.
4. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`. Anchor:
   `    {"name": "RELATIONSHIP_SEEDING", "file": "world/persona.json"}`. That line gains a trailing comma,
   and eight entries follow it, each naming `world/agent_view.json`: `AGENT_VIEW_WHITELIST`,
   `AGENT_VIEW_REFEREE_ONLY`, `AGENT_VIEW_QUANTITIES`, `AGENT_VIEW_KNOWS_LIMIT`, `MAP_GLYPHS`, `VIEW_WORDS`,
   `PRECISION_WORDS`, `ACTION_WORDS`.
5. `bigville/server.py` (this phase's own server file; another session also has one hunk here):
   - import: `from urllib.parse import unquote, urlparse` becomes `... parse_qs, unquote, urlparse`.
   - `GameService.__init__`: adds `mode: str = "referee"`, validation, and `self.mode`. Agent mode needs a
     player. Anchor: `        self.player_name = player`.
   - new method `view(self, actor=None)`, placed after `__init__`. Anchor: `        self.game = create_game(scenario=scenario, seed=seed, player=player)`.
   - `turn`: the line `        result["state"] = self.state()` followed by `        return result` becomes a
     mode check. Agent mode sets `result["view"]`; referee mode keeps `result["state"]`. The other
     session's `visual_actions` block sits just above and is unchanged.
   - `do_GET`: `/api/state` returns 403 in agent mode. New `/api/view` route with `actor` from the query;
     unknown actor gives 404, a missing player gives 400. Anchor: `        elif parsed.path == "/api/state":`.
   - `do_POST` `/api/reset` passes `mode=self.service.mode`. Anchor: `                                                 player=self.service.player_name)`.
   - `serve(...)` takes `mode`. `main(...)` adds `--referee` and sets the mode: agent when `--player` is
     given and `--referee` is not, referee otherwise.

No existing test was edited, and no existing assertion changed.

## Validation

Exact commands and results:

- `python3 domains/bigville_entities.py` gives `ERRORS (0)`, `WARNINGS (0)`, exit 0. Output saved to
  `docs/phases/phase052/selftest_bigville.txt`. The info line reads: 16 sections whitelisted, 30
  referee-only names, all agent view checks pass.
- `python3 -m domains.check --pack test_hamlet` gives `ERRORS (0)`, `WARNINGS (0)`, exit 0. Info: the
  test pack's lexicon has 18 of bigville's 40 quantities, so 12 view fields are omitted in that pack
  (health, health_status, strength, stamina, mood, age, skill, load, condition, amount, distance, weather).
  Output saved to `docs/phases/phase052/selftest_test_hamlet.txt`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase052_agent_view.py tests/test_phase013a_packs.py`:
  34 passed (26 new, 8 existing export tests). The export test needs canonical JSON; see below.
- Full suite on a frozen copy of the final tree (copy taken after the last edit; hashes in
  `docs/phases/phase052/snapshot_sha256.txt`): `1414 passed, 8 skipped`, exit 0. Log:
  `docs/phases/phase052/full_suite.log`. The 8 skips include the Ocelot tests, which skip when the sibling
  `../ocelot` checkout is missing from the copy.
- Full suite on the live working tree, run before the final edits: 4 failures, 1400 passed.
  Three were Ocelot tests (below). The fourth, `test_export_rerun_is_byte_identical`, failed because my
  `agent_view.json` was hand-formatted. I regenerated both files with `tools/export_pack.py`, and that
  test then passed.
- A second live-tree run started while Tract A was mid-edit in `worlds/bigville_world.py`, which called
  a `_refresh_job_fit` method that the file did not yet define. It produced 132 failures, mostly
  `AttributeError` from that file, and one of them was my leak test. The log is kept as
  `docs/phases/phase052/full_suite_live_tree_midedit.log`. It does not measure this phase.

Ocelot failures (live tree only): `test_bigville_ocelot_communication`, `test_mixed_ocelot_village` and
`test_mixed_ocelot_checkpoint_parity` fail with `ModuleNotFoundError: worlds.bigville_ocelot_adapter`.
The adapter exists at `/home/matt/ozmadev/ocelot/worlds/bigville_ocelot_adapter.py`. The tests put that
checkout on `sys.path`, but bigville's own `worlds` package is already imported, so the name is not
found. I ran the same three tests (and `test_bigville_ocelot_fresh_process`) on two copies, both with the
sibling checkout present: one with my hunks and one with them removed. Both gave 3 failed and 3 passed
with the same error, so these failures do not come from this phase. The three test files are untracked,
so there is no committed baseline to compare against.

Tract A's uncommitted work: a snapshot taken earlier, before the final copy, failed four tests in
`tests/test_bigville_world_migrated.py` (tool fitness and quality, stave counts, a `TypeError` in
`bigville/runtime.py`). Removing my hunks from that copy left the same four failures. The later snapshot
passes them, and it differs from the earlier one in that test file and in Tract A's phase 048 logs. So
the failures came from Tract A's in-progress edits, not from this phase.

The leak test catches what it should. A meta-test injects a float, a digit, and a `score` key into a real
view and expects `assert_agent_safe` to fail each time.

Behaviour checked by the 26 tests:
- every key is whitelisted for its section; no float or int leaves; no digit in a phrase (handles
  excepted); no referee-only key
- founding residents (25 of them) and a player after 4 steps pass the leak test
- two residents within sight have different views
- a stranger appears as a description, and the same person appears by name after an awareness record
- the view is deterministic for a state and across two identical sessions
- knowledge entries carry only name, understood phrase and gist (no basis)
- moves are offered only to known exact places, with no `destination` key
- the map patch is 15 by 15 cells (sight range 7), centred on `@`, with terrain glyphs only
- `last` quotes the refusal description when the action did not happen
- building a view does not change the practice window a backend reads
- a simple backend's `ActorContext` still has `agent_view` set to None and keeps its raw observations
- `/api/state` returns 403 in agent mode, `/api/view` returns the view, `/api/turn` returns `view` and no
  `state`, and referee mode serves `/api/state` (run on a loopback server on port 0)
- the command line picks agent mode only when `--player` is given
- the hamlet pack builds a view with its own words and omits the 12 fields its lexicon cannot word

Counts of existing tests changed: none.

## Limits

- **Mode default (decision).** Agent mode applies only when `--player` is passed on the command line. The
  default server (no `--player`) keeps the omniscient `/api/state`, because the Phaser client in
  `bigville/game/game.js` reads it and an unconditional flip would break that page. `game.js` is
  unchanged. Running the server with `--player` makes the page's `/api/state` calls fail with 403, as
  designed.
- **Missing words.** A field whose lexicon table is absent is omitted, not shown as a number. This affects
  the test pack only. Its `lexicon.json` is Phase 051's data, outside this phase's scope.
- **Not in the view, and why.**
  - `tool` in `can`: the affordances carry no tool key.
  - `light`, `finery`, `intoxication`, `deficiency`, `strain`, `chill`, `soaked`: no published read-off.
  - Physical objects around the resident: not listed. The affordance list and held items are shown.
  - Damage and progress in `last`: the world does not publish them per action. Only `moved something`
    events appear in `around.seen`.
  - Sound: not listed.
- **Unknown places.** A move to a place the resident does not know is dropped from `can`, not kept
  without coordinates. Phase 053 adds `toward` for these.
- **Map.** Terrain only, no occupants or objects, within `HEARING.sight_range` (7). Phase 053 replaces it.
- **Distances.** Chebyshev distance in cells, matching the hearing and sight rule. Walkable path distance
  is not used.
- **Laws and policies.** `world_frames` is not passed through. At turn 0 for the sampled carpenter it
  carried about 5,160 characters, including spec fields with numbers (for example `understands`). The view
  shows each law or policy the resident holds, by name and gist, from the resident's own knowledge
  records.
- **Knowledge.** Built from the derived knowledge records (Phase 019). The `basis` strings carry numbers
  and conditions, so they are dropped. The list is capped at 60 (APPROX, a display choice). Each
  understood item reads with the generic gist for its kind, so a concept can read "an idea you have heard
  of" while understood.
- **Speech.** Heard text is passed verbatim as data. It is another resident's words, not instructions.
  Phase 054 handles the prompt side.
- **Fail closed.** The builder raises `ValueError` if it would emit a key outside the whitelist. The HTTP
  routes map that to 400 on `/api/view`. On `/api/turn` it reaches the generic handler (422).
- **Private access.** `around.seen` reads `game._physical_events`, a private attribute of the game. The
  builder is inside the same package.
- **Not benchmarked.** Build time was not measured apart from one run that took about 0.7 s, including game
  creation.
- **Placement of the whitelist (decision).** The brief named `domains/world_affordances.py`. I used the
  pack, as your instruction asked, so `world_affordances.py` is untouched.
- **Glyphs and cap.** The map glyphs and the knows cap are marked APPROX in the pack, as display choices.
  The view words are authored phrases with no source figures.

## Open questions

1. Should the test pack's `lexicon.json` be extended (Phase 051 owner), so the hamlet view shows health
   and the other 11 fields? Until then the hamlet view omits them.
2. Should the Phaser client move to agent mode (it would need the Phase 053 fogged map first)? Today it
   works only in the default referee server.
3. Should the default server be agent mode when no `--player` is given? I kept it referee so the existing
   client keeps working.
4. The three Ocelot tests need the sibling checkout importable as a package. That is an Ocelot session
   question, not this phase's.
5. Tract A's world WIP caused the mid-edit failures in the live tree. The supervisor should review the
   final commit against a frozen snapshot, as I did.
