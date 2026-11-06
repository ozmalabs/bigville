# Phase 030: the town store has a lock and key

## Summary

Keys are discrete items. A key is a `ToolItem` of kind `key` with an `opens` value (the lock id it fits), held
like a tool, so it can be given, accepted, dropped, picked up and taken through the Phase 029 contest. The
`holds_key` edge is gone.

`lock` and `unlock` are major actions on a named container or on the town store (`"store"`). The actor must hold a
fitting key and stand on the lock's cell. A lock with `keys_required` above 1 opens once that many distinct
keyholders have each turned a key at the cell. The argument-less `lock()` and `unlock()` are removed.

The town store has its own `Lock` node (`has_lock` edge from the store). The founding state comes from pack data
(`STORE_LOCK`) and is unlocked, so the default town is unchanged. The store node keeps only `name`, as the existing
commodity test requires.

Every resident-initiated path that reads or writes town stock asks `_store_open(actor)` first. A job whose worker
has no access stays pending and keeps its worker busy (Phase 023). The 100-resident town run is byte-identical
before and after (see Validation).

Self-test: 0 errors, 0 warnings (bigville and test_hamlet). New test file: 22 passed. Full suite in the working
tree: 1016 passed, 2 skipped, 3 failed. The three failures are the Ocelot adapter tests that fail at baseline with
`ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.

## Changes

Files created:
- `packs/bigville/world/locks.json`, `packs/test_hamlet/world/locks.json`: `KEY_KIND` ("key"), `KEY_WEIGHT` (0.05, APPROX),
  `STORE_LOCK` (`lock_id` 1, `locked` false, `keys_required` 1).
- `tests/test_phase030_store_lock.py` (22 tests).
- `docs/phases/phase030/` (this report, `digest_check.py`, digest logs, self-test, hamlet check, seed check, full suite log).

Files edited:
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: three table entries each, bound to `world/locks.json`.
- `packs/bigville/world/major_actions.json`, `packs/test_hamlet/world/major_actions.json`: `lock` and `unlock`
  (kind `security`, each with a description).
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json`: six codes:
  `no_lock`, `no_key`, `already_locked`, `already_unlocked`, `already_authorised`, `store_locked`.
  Existing `container_locked` is reused for containers.
- `domains/world_affordances.py`: binds `KEY_KIND`, `KEY_WEIGHT`, `STORE_LOCK`.
- `domains/bigville_entities.py`: `_check_locks` (called from `check_consistency`).
- `bigville/backends/cheap.py`: `DeterministicBackend.decide` returns an `unlock` for a keyholder at the lock, before
  the PSI/CAN weighting. Food and sleep still come first.
- `tests/test_bigville_world_migrated.py`: one call changed (see Changed existing tests).
- `worlds/bigville_world.py`, my hunks only (the other session's hunks are its `"food"` flag in the container fetch
  options and `resident_plan_from_context`; the nearest of mine is about 20 lines from the food flag):
  - `__init__`: the store's `Lock` node and `has_lock` edge; `self._store_bypass = False`.
  - `add_actor`: the `lock_armed` and `unlock_armed` attributes are removed.
  - `_resolve_actor_events`: the armed lock and unlock branches are removed. The armed fill and empty check
    `_store_open` as well.
  - `_bulk_sources`: the store tier is offered only when `_store_open(actor)` holds.
  - `give_key` (rewritten), new `_holds_key`, `_node_accessible`, `_container_accessible` (rewritten on `_node_accessible`),
    `_store_open`, `_store_lock_node`, `_lockable`, `_clear_authorisations`, `lock`, `unlock`. The old `lock` and `unlock`
    one-liners are deleted.
  - `_wire_container`: `keys_required` (default 1); the name `"store"` is reserved. `add_container` and `use_as_store`
    take `keys_required`.
  - `add_store`: optional `locked` and `keys_required` overrides.
  - Store guards (see table below): `fetch`, `sow`, `water_crop`, `fertilise`, `harvest_crop`, `butcher`,
    `_husbandry_yield`, `treat`, `care_for`, `maintain_infrastructure`, `advance_building`, `dye_garment`,
    `give_newspaper`, `stock_person`, `process_waste`, `fill`, `empty`, `_resolve_jobs` (completion), `_bulk_sources`.
  - `_village_work_tick`: now a wrapper that sets `_store_bypass` for its step and calls `_village_policy_pass`
    (the old body, renamed).
  - `_major_action_attempt`: `lock` and `unlock` branch. `_enact_plan`: `lock` and `unlock` branch.
  - `_actor_options`: the two store fetch blocks require `_store_open(actor)`. New block publishes `lock` or
    `unlock` only with a fitting key at the lock's cell, and not an unlock again for a keyholder who has already
    turned a key in a dual-key lock.

## Design

Keys. `give_key(actor, opens)` (setup) creates a `ToolItem`, kind `key`, `opens` = lock id, `weight` = `KEY_WEIGHT`,
on the actor's `holds` edge. A key is handed over by `give`, `accept` or the contest `take`, as any tool is.

Access. An unlocked thing is open to everyone. A locked thing opens to a holder of its key, when `keys_required` is 1.
A locked thing with `keys_required` above 1 is shut to everyone until it opens. This keeps the existing container
behaviour (a keyholder opens and fills a locked safe) and makes a dual-key lock require the joint act.

Lock. Locking needs a fitting key and the actor on the lock's cell. A container with no mapped cell has no position
requirement (the old rule). A locked thing cannot be locked again. A lock clears its turns of the key.

Unlock. With `keys_required` 1, unlock opens the lock. With N above 1, each distinct keyholder's turn is an
`authorised_by` edge from the lock node to that actor. The Nth distinct turn opens the lock and clears the edges.
One person cannot turn two keys.

Store paths. The table lists each path that reads or writes town stock on behalf of a resident, and its treatment:

| Path | Treatment | Tested |
|---|---|---|
| `fetch`, store source | refused `store_locked` | yes |
| Recipe inputs (`_bulk_sources`): job start availability, job completion plan, `type_available(type, actor)` | store tier not offered; the job waits | yes (`_bulk_sources`, Smith job) |
| Job completion that writes to the store (bulk output, byproducts, type byproducts) | job waits as `missing` | no direct test (Smith job covers input only) |
| `sow` (seed draw) | refused `store_locked` | yes |
| `water_crop` (water draw) | refused `store_locked` | yes |
| `fertilise` (fertiliser from the store) | refused `store_locked` | yes |
| `harvest_crop` with a harvester (deposit) | refused `store_locked` | yes |
| `butcher` (deposit) | refused `store_locked` | no |
| `_husbandry_yield` (product deposit) | refused `store_locked` | no |
| `treat` with medicine | refused `store_locked` | yes |
| `care_for` | ordinary care when the caregiver has no access (no refusal) | yes |
| `maintain_infrastructure` (materials, when any are needed) | refused `store_locked` | no |
| `advance_building` (materials) | refused `store_locked` | no |
| `dye_garment` (dye draw) | refused `store_locked` | no |
| `give_newspaper` | refused (returns None) | yes |
| `stock_person` | refused (returns False) | yes |
| `process_waste` (deposit) | refused (returns False) | yes |
| `fill` (store to container) | refused `store_locked` | yes |
| `empty` (container to store) | refused `store_locked` | yes |
| `_resolve_actor_events` armed fill and empty | same check | via `fill` and `empty` |

Not guarded, and why. Non-residents and period processes act on the store directly: `deliver` (merchant),
`_burn_household_heat` (the household's fuel draw from the store), `_collect_night_soil`, `_draw_village_water` and
`_draw_village_pasture`, `_consume_feed` (animal feed, period), `_daily_life_tick`, `_regrow_gathering_sites`, the
founding setup (`populate_town100`, the founding baker's bread), and `give_product` (no caller in the package).
`_bulk_sources(None, kind)` still lists the store. The founding village policy (`_village_work_tick`) bypasses the
guard while it runs. `run_village` does not call that policy (only the phase 015/016 digest scripts do).

Refusal reasons. The lock and unlock refusals name their check (`no_lock`, `not_in_reach`, `no_key`,
`already_locked`, `already_unlocked`, `already_authorised`, `unknown_target`). The store paths name `store_locked`.

Cheap resident. `decide` returns an `unlock` when a published `unlock` option exists, sleep is not needed, and
food is not first. This is the only lock policy. The CAN model has no concept for lock or unlock, so the choice is
explicit rather than weighted. A cheap resident never locks.

Handover kinds. No new kind. A key moves through `give`, `accept` and `take`, which already exist in
`HANDOVER_KINDS`; its handover `good` is `key`.

Data and sources. `KEY_WEIGHT` 0.05 kg is APPROX: a design choice, no source consulted. `STORE_LOCK.lock_id` 1 is an
identifier, not a figure, and differs from the scenario container lock ids (7, 27, 5, 9, 10), so one key does not open
both. Two new refusal codes, the lock descriptions and the key description are text, not figures.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0); WARNINGS (0) (`selftest.log`) |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0); WARNINGS (0) (`check_hamlet.log`) |
| `python3 tools/generate_seeds.py --check` | exit 0; "match pack 'bigville' (31 files)" (`seeds_check.log`). No seed changed, so none was regenerated. |
| `python3 tools/export_pack.py` (bigville and test_hamlet) | normalised 197 tables each; only the files listed above changed |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase030_store_lock.py` | 22 passed |
| `python3 -m pytest -q -p no:cacheprovider tests/test_bigville_world_migrated.py tests/test_simple_storage_decay_construction.py tests/test_phase029_contest.py tests/test_phase026_handovers.py tests/test_phase021_refusals.py` | 173 passed (before the full run) |
| Full suite, working tree: `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 1016 passed, 2 skipped, 3 failed (`full_pytest.log`). The failures are the three Ocelot adapter tests (below). |
| Same suite on a copy of this tree, after the edits (`copy_pytest_after.log`) | 1013 passed, 8 skipped, 0 failed |
| Same suite on the clean baseline copy (`copy_pytest_baseline.log`) | 991 passed, 8 skipped, 0 failed (1013 - 991 = the 22 new tests) |

The three failures, verbatim from `full_pytest.log`:
`tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
`tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
`tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
Each raises `OcelotUnavailableError: ... Adapter import failed (ModuleNotFoundError: No module named
'worlds.bigville_ocelot_adapter')`. The sibling `../ocelot` checkout exists but has no `worlds/bigville_ocelot_adapter.py`.

Validation note. A copy of the tree at the same state, outside `/home/matt/ozmadev`, has no sibling `ocelot` directory.
In that copy the three Ocelot tests skip (`Ocelot source checkout is not present`) rather than fail. The clean
baseline copy (before any edit of this phase, with the working tree's other session changes) gave 991 passed, 8
skipped, 0 failed. The same copy after the edits gave 1013 passed, 8 skipped, 0 failed: the 22 new tests and nothing else.

Town digest (`digest_check.py`: `village_eval.run_evaluation`, town100, seed 305017, 24 turns, arms `baseline` and
`sharing`, `replay=False`). `digest_before.log` came from the clean baseline copy, and `digest_after.log` from the
copy with this phase's edits. The two JSON outputs are byte-identical. The `measurements_digest` is
`c7374e9a15f8...` in both arms, and 100 residents are alive at the end. Both arms produce the same digest in this
span, so the check cannot separate them. The town has no keys and an unlocked store, so no lock path runs.
Runtime: about 90 seconds for both arms.

## Changed existing tests

- `tests/test_bigville_world_migrated.py::test_a_locked_safe_needs_the_key`: `w.unlock("Clerk")` became
  `w.unlock("Clerk", "safe")`. Reason: `unlock` now names its container and takes no argument-less first match. The
  assertions are unchanged.
- No other existing test was edited. Every existing container-lock test passes unchanged: `test_bigville_world_migrated`
  (the safe and the made chest), `test_simple_storage_decay_construction` (the locked pantry), and the store-attribute test.
- No test number and no balance number changed.

## Limits

- Lock and unlock need the key holder on the lock's cell. A container with no mapped cell accepts a keyholder from
  anywhere (the old rule). In a mapped town the store has a cell, so it always needs presence.
- A dual-key authorisation stays until the lock opens or is locked again. A keyholder who gives the key away after
  turning it still counts.
- Authorisations are `authorised_by` edges and the store lock is a `Lock` node. Both are graph data. I did not check
  the untracked persistence layer (`bigville/world_persistence.py`); it has to keep these nodes and edges across a
  checkpoint.
- The founding policy's bypass covers only its own step. A job that policy starts completes in `_resolve_jobs`, which
  is guarded. In a locked store, such a job waits. `run_village` does not run the policy, so no run path is affected.
- Untested guards (code only): `butcher`, `_husbandry_yield`, `maintain_infrastructure`, `advance_building`,
  `dye_garment`, and job completion that writes to the store.
- The cheap resident unlocks only. It never locks, and it does not weigh whether a lock should be closed.
- Keys are given by setup (`give_key`) or by `give`/`take`. No job is tied to a key. The brief's "name the job that
  holds the key" is not implemented. The pack founds the store unlocked, and `add_store(locked=...)` can found it locked.
- The LLM and Ocelot prompts list `MAJOR_ACTIONS`, so two more actions appear in them (and `pack_hash` changes). I did not
  render a prompt to check the text.

## Open questions

1. `seeds/bigville_container.json` and `bigville/seeds/bigville_container.json` (`ck_lock`, `ck_unlock`) and
   `bigville/seeds/bigville_action_container.json` still describe `holds_key` edges and `lock_armed`/`unlock_armed`
   attributes. These seed records are not executed (`packs/bigville/world/engine_seeds.json` says so), and they
   are outside this phase's write scope. Should they be rewritten to the key item and the new actions?
2. Should a dual-key lock accept any `keys_required` keyholders, or should it name them (for example the storekeeper and the
   treasurer)? The brief asked for a count.
3. Should a keyholder's turn of a dual key expire if the holder leaves the cell?

## Follow-ups

- The persistence owner (`bigville/world_persistence.py`, `bigville/game_persistence.py`): keep `Lock` nodes, `has_lock`
  and `authorised_by` edges, and `ToolItem` keys across checkpoints. Keys and locks are plain values.
- Ocelot and LLM adapters: the new `lock` and `unlock` options reach them through `_actor_options`. Those adapters are
  not changed here.
