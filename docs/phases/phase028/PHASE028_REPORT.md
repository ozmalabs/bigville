# Phase 028: Loudness is hearing range; hearing is not witnessing

## Summary

Speech now follows the seed `seeds/bigville_loud_comm.json`. The speaker's loudness, clamped to a pack
maximum, is a Chebyshev radius in cells. Content reaches the target of a targeted utterance, or every living
resident for a broadcast, when they are within that radius and no hear occluder lies on the grid line. Any
living resident within sight range with a clear sight line witnesses that a speech act happened, and the
target too if in view. The witness gets no content. The witness record goes through the existing
`physical_events` list in `BigvilleGame`, as movement events do.

Targeted speech no longer needs speaker and target on the same cell. Ordinary speech (loudness 1.0) carries one
cell. The `loudness` physical subsystem (default on) replaces the chosen loudness with a flat radius when off.

Two decisions need the user: how a wall can stop sound but not sight (see Limits), and whether the cheap
village's targeting should change now that its targets are often two or more cells away.

## Changes

Files created or changed (other session's hunks are not touched):

- `packs/bigville/world/hearing.json` (new): table `HEARING`. Figures in the file's `_doc`.
- `packs/test_hamlet/world/hearing.json` (new): the same table, for the standalone pack.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: one manifest entry each for `HEARING`.
  `tools/export_pack.py` was run for both packs; it touched no other file.
- `domains/world_affordances.py`: binds `HEARING = _PACK["HEARING"]` (2 added lines).
- `domains/bigville_entities.py`: `_check_hearing` (new function, called from `check_consistency`).
- `worlds/bigville_world.py`, my hunks only:
  - `PHYSICAL_SUBSYSTEM_DEFAULTS`: `"loudness": True`.
  - `speak`: computes `radius` and `deliveries`; stores `eff_loudness` and `deliveries` on the Utterance node;
    `heard` becomes a derived summary (any listener heard); `heard` edges go to each listener who heard.
  - New methods after `speak`: `speech_radius`, `_occluder_codes`, `_line_blocked`, `speech_occlusion_status`,
    `_speech_deliveries`.
  - `heard_utterances`: reads the actor's own delivery record.
  - `resident_speech_proposal` and `enact_speech_proposal`: the same-cell check is removed; the target's
    alive check stays.
- `bigville/game.py`, my hunks only:
  - new method `_record_speech_witnesses` (placed between `_record_physical_changes` and `_adapt_speech`);
  - `step()`: `utterances_before = len(self.world._utterances)` before each actor's response is applied, and a
    call to `_record_speech_witnesses` after `_apply_response_contained`.
  The other session's `record_action_outcome` hunk in `_apply_response` is untouched, and my hunks are 15+ lines
  away from it.
- `tests/test_phase028_hearing.py` (new, 14 tests).
- Existing tests changed (see Validation, "Test changes").
- `docs/phases/phase028/`: this report, the logs, and two probe scripts.

### Design

- Radius: `speech_radius(loudness)` = `min(max(chosen, 0), max_loudness)`. NaN is taken as `normal_loudness`.
  Switch off: `flat_radius`.
- Delivery (per listener): `heard` if (target is None or the listener is the target), distance <= radius, and
  no hear occluder on the line (endpoints excluded). `seen` if distance <= `sight_range` and no sight occluder on
  the line. `target_seen` (only for seen listeners who are not the target) if the target is within sight of that
  listener by the same rule. Only heard or seen listeners get an entry: `{"heard", "seen", "target_seen"}` as
  0.0/1.0 floats, keyed by name.
- Speaker: gets no physical event. Listeners' records are not published to the speaker.
- Occlusion data: `_map_grid` cells named by the table's occluder lists (via `TILE_NAME` from
  `worlds/bigville_sim_world.py`). No map, or no occluder cells: distance alone.
- Physical event published to a witness: `{"actor", "action": "spoke", "turn", "expires_turn"}`, plus
  `"target"` when that witness sees the target. No content key. It expires after one decision pass, like the
  existing movement events.
- Distances are Chebyshev, as in the seed and the sim world. The old `distance()` (walkable path length) is not
  used for speech.

## Data and sources

| Field | Value | Source |
|---|---|---|
| `sight_range` | 7 cells | Literal `Gte 7.0 dist` in `seeds/bigville_loud_comm.json` `lo_observe_act`; same as `SIGHT_RANGE` in `worlds/bigville_sim_world.py` |
| `flat_radius` | 11 cells | `HEAR_RANGE` in `worlds/bigville_sim_world.py`. APPROX: a repository simulation value, not a measured figure |
| `normal_loudness` | 1.0 | `base_loudness` default in `worlds/bigville_speech_world.py` `utter()`; floor in `bigville/backends/speech.py` |
| `max_loudness` | 100.0 | Cap in `bigville/backends/speech.py` (`min(100.0, ...)`); default in `worlds/bigville_speech_world.py` |
| `sight_occluders` | wall, tree | `OCCLUDERS` in `worlds/bigville_sim_world.py` ("block line-of-sight AND muffle hearing") |
| `hear_occluders` | wall, tree | Same |

The seed's own occluder flags and its `flat_radius`/`max_loudness` values come from an adapter that is not in
the repository. Those values are therefore the repository's choices, as listed above. Distances are cells, not
metres: the seed gives no cell size, so no figure here is a decibel or metre value.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0); `HEARING (1)` info line |
| `python3 -m domains.check --pack test_hamlet` | exit 0 |
| `python3 -m domains.check` (bigville) | exit 0 |
| `python3 tools/export_pack.py` (bigville, then test_hamlet) | normalised 192 tables each; `git status` shows only the two pack.json files and the two new hearing.json files for packs |
| `python3 tools/generate_seeds.py --check` | exit 0; seeds match pack 'bigville' (31 files) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider --ignore=tests/test_bigville_ocelot_communication.py --ignore=tests/test_mixed_ocelot_checkpoint_parity.py --ignore=tests/test_mixed_ocelot_village.py` (after edits) | 944 passed, 2 skipped (log: `full_pytest.log`) |
| Same command, before any edit (baseline) | 930 passed, 2 skipped (log: `baseline_pytest.log`) |
| `tests/test_phase028_hearing.py` | 14 passed |
| The three Ocelot files, not ignored | 3 failed at import: `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` (same as baseline; not touched) |

The 944 is 930 baseline plus the 14 new tests. The brief's test list: the 14 tests cover radius 5 vs 6, louder
carrying farther, a targeted utterance at 3 cells with loudness 3 (and not 2), the broadcast radius, the clamp,
the switch off (flat 11), a wall that stops content (table split), the real map's tree stopping both content and
sight, the witness record without content, the target visible or not to a witness, speaker records, per-listener
delivery records, and the occlusion status with and without a map.

### Test changes (existing tests)

1. `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration`: expected
   default dict gains `"loudness": True`. The switch is now part of the default set.
2. `tests/test_scenario_runner.py::test_runner_replays_identically_and_records_seed_and_causal_trace`: expected
   `physical_subsystems` gains `"loudness": True`, for the same reason.
3. `tests/test_simple_observation_communication.py::test_simple_speech_is_range_gated_then_recipient_policy_responds`:
   Ben starts at (3, 1), two cells from Ada, instead of (2, 1). Old assertion: "adjacent residents are not heard"
   (speech gated on the same cell). New: ordinary speech carries one cell, so an adjacent target does hear. The
   assertion that a listener out of range hears nothing is kept by moving the listener to two cells away. The
   rest of the test is unchanged.

No assertion was weakened or deleted.

Conversation tests: `tests/test_simple_observation_communication.py` is the only conversation-style test whose
assertion changed. `bigville/backends/conversation.py` does not call `speak` or read `heard`; it renders text
only, so it is unaffected.

### Village effect (100 residents, seed 305000, 200 turns, cheap backends, `docs/phases/phase028/`)

Probes: `village_speech_probe.py` (loudness on and off), and `village_speech_probe_samecell.py`, which counts
targets by distance at the moment of each speak.

| Run | Targeted utterances | Content delivered | Mean witnesses per utterance |
|---|---|---|---|
| Loudness on (new rule) | 1350 | 1301 (96.4%) | 74.1 |
| Loudness off (flat 11) | 1350 | 1350 (100%) | 74.1 |

Target distance at speech time (same run as the first row): same cell 1168, adjacent 133, two or more cells 49.
The old same-cell rule would have delivered the 1168 same-cell utterances, so the new rule delivers 133 more
utterances and 49 fewer. Broadcasts: none in this run; the cheap backend only speaks to `nearby[0]`.

The old rule's count is computed on the new run's utterance schedule. The cheap backend picks speech by turn,
time and who is nearby, not by what was heard, so the schedule should match the old code. I did not run the old
code, so this is an inference, not a measurement. The "fewer deliveries" in the brief is not what happens here:
deliveries rise, because the cheap backend's targets are mostly on the same cell or adjacent.

Runs took about 320 seconds each. The 100-resident run here is 200 turns of `game.step()`, not `run_village`
(which has no resident decisions).

## Limits

- **Occlusion data.** The map has tree and wall cells (91 cells of the two, combined, in the founding map of
  seed 305000; `speech_occlusion_status()`). Building footprints are not occluders: a home or workplace is one
  FLOOR cell with no walls, so buildings block nothing. Water does not occlude. Walls here are quarry rock faces
  and trees are forest and scattered trees, not built walls.
- **The seed's wall case cannot be met with this map.** The brief says a wall stops content but not the
  witnessed act when there is sight. Hearing and sight use the same grid line, and the map has no tile that
  muffles sound but passes light. With one occluder list for both channels, a wall stops both. I implemented the
  separate lists the seed implies, and the table default uses the same two lists for both channels (sim world's
  OCCLUDERS). The "wall stops content, witness still sees" test sets the sight list empty for its duration
  (monkeypatch). The real-map test shows that a tree stops both. Decision needed: add a sound-only occluder
  (a window, a door, or a thin partition) to the map generator, or accept that walls block sight too.
- **The loudness choice is not ablated.** The seed's `lo_choose_loudness` also has a `choice` switch (base
  loudness when choice is off). Only the `loudness` switch is ported; there is no choice switch.
- **`heard` is kept as a derived summary.** `bigville/reporting.py` (not in this phase's write scope) reads the
  `heard` attribute for its `heard_rate`. It is now "any listener heard the content". Reporting should read
  `deliveries` instead. Follow-up.
- **Co-location gates were removed** from `resident_speech_proposal` and `enact_speech_proposal`. No test asserts
  the old refusal, but these are the paths the Ocelot seam uses; their owner should confirm the change.
- **Cognition feedback.** Whether a resident should learn from a witnessed act is backend-owned. Not done here.
- **Persistence.** `deliveries` is a dict of plain floats and strings on Utterance nodes. `_physical_events`
  entries are plain dicts. Both should serialise. I did not run the other session's persistence tests against
  the new event shape; their `game_persistence.py` copies `_physical_events` as-is.

## Open questions

1. Walls: add a sound-only occluder to the map, or accept that walls block sight too (see Limits)?
2. Cheap backend: its targets are `nearby[0]` (up to 8 cells away) with loudness 1.0, so about 4% of its speech
   reaches a target two cells or more away in this run. Should it raise loudness to reach its target? That is a
   backend choice (`bigville/backends/cheap.py`, out of this phase's scope).
3. The `heard` summary in `reporting.py`: move `heard_rate` to `deliveries` in a follow-up?

## Working tree

Start (recorded at session start, before any edit): modified `README.md`, `bigville/backends/ocelot.py`,
`bigville/game.py`, `bigville/runtime.py`, `bigville/seeds/bigville_actor_decision.json`,
`docs/AGENT_BACKENDS_PLAN.md`, `tests/test_bigville_game_api.py`, `tests/test_bigville_scenarios.py`,
`worlds/bigville_world.py`; untracked the other session's persistence, Ocelot, and run files.

End: the same entries, plus my changes listed above, plus `docs/FEATURE_PHASES.md` shown as modified. I did not
edit that file, and it was not modified at session start, so another session changed it during this run. No
commit, stash, or branch was made.

## Supervisor review

- Walls and sight: accepted as implemented. A wall or tree on the line blocks both content and
  sight, which is the physical default; the "content blocked but act witnessed" split is tested
  with a sound-only occluder list and becomes reachable on the map only if a sound-only tile
  (a window, a thin partition) is added later. Left as an open question for the user.
- `bigville/reporting.py` still reads the derived `heard` summary; moving it to `deliveries` is a
  follow-up.
