# Phase 039: doors and confinement

## Summary

A building may carry one door: a `Lock` node on its Place, with Phase 030's lock fields and the `lock_strength` that Phase 050
reads. A building may also name one entrance cell on its footprint's perimeter. A walking step across the footprint boundary
is refused `door_locked` while that building's door is locked. While the door is unlocked and an entrance is named, a crossing
is allowed only at the entrance. Buildings without a door are untouched, and the founding town has no door, so the default
village is unchanged. The jail is a new BUILDINGS row (`founding: False`) whose door starts locked. Confinement is only the
locked door: no law, sentence, or custody record is attached.

This report replaces the survey report of the earlier, cancelled run. Its findings and the three options (A, B, C) are kept
in the "Survey" section. The supervisor chose option B, with the five decisions in the brief run.

## Changes

Files created by this phase:
- `tests/test_phase039_doors.py` (22 tests).
- `docs/phases/phase039/PHASE039_REPORT.md` (this report), and the logs listed in Validation.

Files changed, with each shared file's hunks by function. Other sessions' uncommitted hunks in these files are not listed
and were not edited.

- `worlds/bigville_world.py` (this phase's hunks):
  - `__init__`: `self._door_places = {}`, beside `_building_sites`.
  - `_install_building` (after `_attach_at_cell`): calls `_install_door` when the spec has a `door`.
  - `_movement_step`: with doors in the town, the route is ranked by a door-aware cost field and only admissible steps are
    candidates. A town without doors takes the unchanged branch.
  - New section "doors (Phase 039)": `_install_door`, `_door_lock`, `_entrance_cell`, `_inside_footprint`, `_door_allows`,
    `_door_travel_field`, `_door_stops_walk`, `_door_reach`.
  - `_lockable` (a door returns its lock and reach) and new `_reach_of`.
  - `lock` and `unlock`: reach is a set of cells (entrance and the cells beside it) instead of one cell.
  - `_actor_options`: the lock and unlock option loop includes door names.
  - `major_action`, `move` branch: refuses `door_locked` when `_door_stops_walk` is true.
  - `major_action`, lock and unlock dispatch: accepts a door name.
  - Attempt dispatch: an `open` attempt on a door name calls the new `_attempt_door`. `_attempt_door` is a new method.
  - `_container_plan`: new optional `node` argument (the door lock); default unchanged.
  - Displacement loop (`_run_displace`): a push stops at a door step that `_door_allows` refuses.
  - Joint carry loop (`_enact_carry`): a load step must pass `_door_allows`. Added after the survey: the carriers' step to the
    cell behind the load is also checked, and if any carrier's step is refused the load does not move ("stuck").
  - `_evade_cell`: an evasion cell must pass `_door_allows`.
- `domains/bigville_entities.py`: new `_check_doors` (after `_check_locks`), and its call in `check_consistency` after
  `_check_locks`.
- `packs/bigville/world/buildings.json`: `_doc` paragraph on doors; new `jail` row.
- `packs/bigville/world/building_projects.json`: `_doc` sentence; new `jail` project (one raises the jail).
- `packs/bigville/world/refusal_reasons.json` and `packs/test_hamlet/world/refusal_reasons.json`: `door_locked` code.
- `bigville/game/assets/` (regenerated): `buildings.png`, `building_badges.png`, `building_interiors.png`,
  `style_buildings.png`, `style_cutaways.png`, `manifest.json`, `style_manifest.json`. The jail adds sprite frame 37; alphabetical
  frame indices for mill, papermill, printshop and scriptorium move up by one. The manifest records the new indices.

Not changed: `domains/world_affordances.py`, `packs/*/pack.json`, the Phase 054 packet snapshot. No MAJOR or FREE action was
added (lock, unlock and attempt already exist), so the Phase 054 snapshot does not change.

## Design

- **Door.** `BUILDINGS[name].door` is `{lock_id, locked, keys_required, lock_strength, entrance?}`. `_install_door` makes a
  `Lock` node with `lock_id`, `locked`, `keys_required`, `lock_strength`, `lock_condition` (1.0) and `lock_progress` (0.0), and
  attaches it to the Place with `has_door`. An entrance becomes a `has_entrance` edge to the map cell at the footprint offset.
- **Crossing rule** (`_door_allows`). A step that crosses a footprint boundary is refused while the door is locked. While it
  is unlocked, a crossing is allowed only when the inside cell is the entrance. With no entrance named, an unlocked door allows
  every crossing.
- **Walks.** Routes are ranked only over steps the doors allow, so a walk to a building goes round to its open entrance. A
  walk with no admissible route because of a locked door is refused `door_locked` (`_door_stops_walk`). `move_actor` takes no
  step that the door refuses.
- **Lock and unlock.** A door is named by its building (`lock "jail"`). Reach is the entrance and the four cells around it. With
  no entrance, reach is the footprint and its neighbours. The key rules are Phase 030's: a key with the matching `lock_id`, and
  `keys_required` distinct keyholders.
- **Forcing.** `attempt` with verb `open`, `pry` or `force` on a door name runs Phase 050's open primitive on the door's lock,
  with the door's `lock_strength` as the demand. The actor must stand in the reach. A blow that does not break the lock records
  `progress`, and the lock stays shut. Blows wear the lock down across turns. A resident who tires can no longer swing (the
  Phase 050 slot and stamina rules apply).
- **Evasion and displacement.** Evasion cells (029) and push or pull cells (050) must pass `_door_allows`. Restraint (033)
  needs no change: a restrained or holding resident cannot walk at all.
- **Jail.** `BUILDINGS.jail`: `founding: false`, footprint 3x3, room `cell_block`, `door` with `lock_id` 41, `locked` true,
  `keys_required` 1, `lock_strength` 3.0, `entrance` [1, 2] (the bottom middle). Its project costs stone 10, timber 8, labour 12.

## Data and sources

- The jail's `lock_id` 41, `lock_strength` 3.0, the footprint, the room, the entrance offset and the project inputs and labour
  are design choices. They are marked APPROX in the pack `_doc` and have no source. The brief's `seeds/bigville_jail.json` is a
  custody spec with no physical figures, so it supplies none of them.
- The `door_locked` description is text, not a figure.

## Tests

`tests/test_phase039_doors.py` has 22 tests, all passing:
- Data and wiring: the jail is a catalogue row not standing at founding, starts locked and has a project; founding buildings
  have no door; `door_locked` is in both packs; the self-test rejects an off-perimeter entrance and a shared lock.
- Locked door: a resident inside cannot leave; a resident outside cannot enter without the key; unlocking with the key lets
  them out; a keyholder outside is refused until the door is unlocked.
- Lock and unlock: reach (the entrance and the cell beside it); no key refusal; a dual-key door needs two keyholders.
- Unlocked door: crossing only at the entrance; a walk round to the entrance; a locked door shuts the walk.
- Attempts: forcing needs reach; a blow records `progress` and leaves the lock shut; a door already open is refused
  (`already_unlocked`).
- Evasion never steps across a locked door.
- A town with no door is unaffected.
- The door state is plain graph data.
- Lock by name resolves the store and the door.

## Validation

Run in `/home/matt/ozmadev/bigville` on the live tree (with other sessions' uncommitted work present).

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Log: `selftest.log`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. Log: `check_hamlet.log`.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)". Log: `seeds_check.log`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase039_doors.py`: 22 passed.
- `PYTHONPATH=. python3 /tmp/death_probe.py 192`: 192 turns, 0 deaths, first death none. Log: `death_probe_192.log`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase058_persona.py`: 42 passed.
- Asset regeneration: `python3 bigville/game/assets/generate_assets.py` and `python3 tools/build_style_assets.py`, both exit 0.
  `test_asset_manifest_covers_entity_items_and_modular_buildings` failed before the regeneration (`'jail'` missing from the
  manifest) and passes after it.
- Full suite, final run on the live tree after the regeneration (`python3 -m pytest -q -p no:cacheprovider -rfE`, log
  `full_pytest.log`): **8 failed, 2126 passed, 6 skipped** in 2917 s.
  - Three ocelot tests (`test_bigville_ocelot_communication`, `test_mixed_ocelot_village`, `test_mixed_ocelot_checkpoint_parity`):
    `ModuleNotFoundError: worlds.bigville_ocelot_adapter`. These are the three known baseline failures.
  - Four `tests/test_phase057_tui.py` tests (`test_over_http_a_menu_row...`, `..._walking_to_a_known_place...`,
    `..._a_reaction_is_delivered...`, `test_the_server_refuses_a_bad_reply...`): `NoneType has no attribute 'action'`, an empty
    `contest_log`, and `200 == 400`. The same file passes on a clean `git archive HEAD` export (48 passed). I did not isolate
    them by reverting this phase's hunks. Without a door, every new branch here returns its old result, so I do not expect this
    phase to cause them. The likely cause is another session's uncommitted server or agent-view work. This is a reasoned
    conclusion, not a run.
  - `test_a_slow_provider_is_faster_when_decided_concurrently...` (timing): failed in the full runs and passed when run alone.
- Earlier verbose run, before the asset regeneration: 11 failed. Asset manifest failed (`'jail'` missing; fixed by the
  regeneration). `tests/test_phase013a_packs.py` (export byte identity and compile back) failed in that run and passed on rerun
  against the same live packs; the cause is not confirmed.

## Limits

- The joint-carry guard was added after the survey and is tested only by the code path reading, not by a test. It is a no-op
  with no doors.
- Carriers are checked for one step, from their current cell to the cell behind the load. A carrier who is not adjacent to
  that cell is not checked along a longer path.
- Evasion is tested through `_evade_cell`, not through a full contest.
- Breaking a locked door takes many blows across rests. The test covers only the first blows and the collapse refusal.
- A door shares the lock_id namespace with containers. The self-test checks only the store and the other doors. A scenario
  that gives a container `lock_id` 41 would share a key with the jail.
- The 100-resident village was not run for this phase, so its behaviour with doors is not shown.
- The death probe is the simple town100 at 192 turns, as the brief asks. It ran on the live tree, including other sessions'
  uncommitted day and night, speech, and fog changes.

## Open questions

1. Should the lock_id 41 for the jail be reserved in the lock namespace (for example in `locks.json`), so no container can share it?
2. Should the jail project's `affordance` ("locked_room") be given a meaning elsewhere? It is a label; nothing reads it.
3. Should a joint carry check every carrier's whole path rather than one step?

## Survey (from the cancelled run, kept for reference)

- The map is a grid of `MapCell` nodes. A building is a `Place` with a rectangular footprint `(x, y, w, h)`. Footprint cells are
  ordinary open ground, and no building had an entrance, a wall or a door.
- Rooms are `Room` nodes with no cell or position.
- Options: A (walls with one entrance per building, which changes the graph for every building), B (perimeter gate on the existing
  graph, chosen), C (door on the anchor cell, not a physical entrance).
