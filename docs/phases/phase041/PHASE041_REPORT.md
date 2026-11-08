# Phase 041: physical coin and safes

## Summary

Coin can now be stored. A resident's own coin (`coin`, their purse) moves into a lockable container with `put(..., "coin", n)` and back with `fetch(..., "coin", n, source=...)`. Both moves are conserved and happen on the resident's cell. A container opens through its lock (Phase 030): a closed safe refuses with `container_locked`, and a dual-key safe opens only after two distinct keyholders have each turned a key. A Phase 011 fiscal purse keeps its coin, and only its holder may put coin into it or take coin out. A resident's own coin adds `COIN_WEIGHT` per coin to the carried weight. The default is 0, so the founding town's carried weight does not change. The report's economy section now has a `coin` block that counts where the coin is.

The self-test is clean (0 errors, 0 warnings). The full suite gives 2162 passed, 6 skipped, 7 failed. Three failures are the Ocelot adapter tests that fail at baseline. Four are over-HTTP TUI tests (`test_phase057_tui.py`) that depend on uncommitted work in `bigville/server.py` and `bigville/backends/human.py`. Both are listed under Validation.

## Changes

Files created:
- `tests/test_phase041_coin_safe.py` (10 tests).
- `docs/phases/phase041/` (this report and the logs listed under Validation).

Files changed, in the order a reviewer meets them. For the shared files I give each hunk by method.

- `packs/bigville/world/containers.json`, `packs/test_hamlet/world/containers.json` (clean before this phase): tables `COIN_WEIGHT` (0.0) and `COIN_VOLUME` (0.0), both APPROX, with an explanation in `_doc`. Both files are in the exporter's layout (verified, see Validation).
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json` (clean before): one code, `full`, with a description.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json` (shared; the other session has uncommitted hunks near line 868). My hunk is one insertion at line 36 of each file: entries for `COIN_WEIGHT` and `COIN_VOLUME`, bound to `world/containers.json`.
- `domains/world_affordances.py` (clean before): `COIN_WEIGHT`, `COIN_VOLUME` bound from the pack, after `CONTAINERS`.
- `domains/bigville_entities.py` (shared): `_check_coin_storage` (new function, before `_check_doors`, about line 545) and its call in `check_consistency` after `_check_locks` (line 2166). The other hunks in this file (2184, 2190) are not mine.
- `worlds/bigville_world.py` (shared). My hunks, by method:
  - `carried_weight`: adds `coin(actor) * COIN_WEIGHT`.
  - `give`: the coin branch refreshes the carry state of both parties.
  - `_phys`: coin takes `COIN_WEIGHT` and `COIN_VOLUME` instead of the item default (1.0 and 1.0).
  - `put`: first branch sends a coin move to `_put_coin`. A missing container is refused as `unknown_target`, where it used to raise a `KeyError`.
  - New block before `fill`: `_coin_place`, `_coin_open`, `_coin_stored`, `_add_stored_coin`, `_coin_fits`, `_put_coin`, `_fetch_coin`, `_coin_endpoint`.
  - `fetch`: a coin move with a source goes to `_fetch_coin`. The store path is unchanged.
  - `_major_action_attempt`, `put` branch and `fetch` branch: accept a purse name as the target, only when `kind == "coin"`. Any other name is refused as before.
  - Not mine, left as found: the hunks in `_actor_options` and `resident_plan_from_context`.
- `bigville/reporting.py` (clean before): `economy()` builds `coin` (`resident_purses`, `stored_in_containers`, `in_purses`, `in_store`, `total`) and returns it under the key `coin`.

## Design

- **Purse.** The resident's `coin` attribute is their purse. It is unchanged.
- **Container.** Stored coin is the container's `coin` pile, the same pile `fill` already uses for coin from the store. Its weight and volume come from `COIN_WEIGHT` and `COIN_VOLUME`, through `_phys`.
- **Fiscal purse.** A purse keeps its `coin` attribute and its `recorded` ledger. `put` and `fetch` move coin through `_move_fiscal_coin`, so the ledger moves with the coin. Only the purse's holder, from `_acts_for`, may move coin in or out. A purse has no lock and no cell.
- **Access.** A container opens through `_container_accessible`, the same rule as its other contents (Phase 030). A container with a cell requires presence during a turn. A container with no cell has no presence rule, as in Phase 030.
- **Refusals.** `unknown_target`, `malformed`, `not_in_reach`, `container_locked`, `out_of_stock`, `full`, `slot_used`. `full` is the only new code, and it fires only when `COIN_WEIGHT` or `COIN_VOLUME` is above 0.
- **Claims.** Inside a turn, `put` and `fetch` of coin claim the same one major action as any other `put` or `fetch`. A direct call outside dispatch claims it itself, as the existing code does.
- **Handovers.** Each move records one `put` or `fetch` handover with `good = "coin"`. The endpoints are `actor`, `container` or `purse`. The fiscal count (`_transactions`) is unchanged.
- **Carrying.** A resident's coin counts at `COIN_WEIGHT` in `carried_weight`. Stored coin does not count toward the resident. It counts toward the container's `contents_weight`.

## Data and sources

- `COIN_WEIGHT` = 0.0 kg per coin, APPROX. No source was consulted, and a real coin's mass is not sourced here. The value 0 keeps the founding town unchanged.
- `COIN_VOLUME` = 0.0 litres per coin, APPROX. Same reason. With volume 0, coin does not use container capacity, so only `max_load` limits it.
- `full`: a refusal text, not a figure.
- No distribution or real-world figure is used.

## Changed numbers

- **Store coin pile.** Before: a coin pile weighed 1.0 kg and took 1.0 litre per coin, the item default. After: `COIN_WEIGHT` and `COIN_VOLUME`, both 0.0. This changes only coin piles. I did not check whether the founding town ever holds a coin pile, but the existing coin tests pass. The 192-turn probe showed 0 deaths; I did not compare digests for this change.
- **`carried_weight`.** Adds `coin * COIN_WEIGHT`, which is 0.0 by default.
- **Report.** Adds the key `economy.coin`.
- **Refusal codes.** Adds `full` to both packs.
- **Tests.** No existing test was edited. No test number changed.

## Validation

Commands, run in `/home/matt/ozmadev/bigville`. Results are the final state of the tree.

| Command | Result | Log |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0); WARNINGS (0) | `selftest.log` |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0); WARNINGS (0) | `hamlet_check.log` |
| `python3 tools/generate_seeds.py --check` | exit 0; match pack 'bigville' (31 files) | `seeds_check.log` |
| Exporter layout, run on a copy: `cp -r packs tools domains bigville/__init__.py /tmp/p041_repo/`, then `python3 tools/export_pack.py` there | exit 0; normalised 254 tables; my edited files `containers.json` and `refusal_reasons.json` (both packs) and `pack.json` (both packs) are byte-identical to the copy's output. The live packs were not exported. | `export_check_tmp.log` |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase041_coin_safe.py` | 10 passed | |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase041_coin_safe.py tests/test_phase058_persona.py tests/test_phase013a_packs.py` | 60 passed | |
| `timeout 3000 python3 -m pytest -q -p no:cacheprovider -n 4` (full suite) | 2162 passed, 6 skipped, 7 failed (809 s) | `full_pytest.log` |
| `PYTHONPATH=. python3 /tmp/death_probe.py 192` | `"deaths": 0`, `"first_death_turn": null` | `death_probe_192.log` |

The village checks above are the only village runs. I did not run the 100-resident run that the brief does not ask for. `village_eval.py` was not run as a whole, but `tests/test_package17_18_village_eval.py` passed in the full suite.

Full suite failures, verbatim where they fit:

1. Three Ocelot tests, which fail at baseline with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`:
   - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
   - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
   - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`
2. Four over-HTTP TUI tests in `tests/test_phase057_tui.py`. The failing assertion is `AttributeError: 'NoneType' object has no attribute 'action'` at `service.game.last_responses[PLAYER].major_action.action`, so no response was recorded for the player. The failures are:
   - `test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`
   - `test_over_http_walking_to_a_known_place_sends_the_rows_destination`
   - `test_over_http_a_reaction_is_delivered_to_the_holder`
   - `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`

   Run alone, the file gave 4 failed and 44 passed (`tui_isolated_run.log`). An earlier isolated run gave 5 failed, so the set varies between runs. These tests drive `bigville/server.py` and `bigville/backends/human.py`, both modified in the other session's uncommitted work. I did not run them on a baseline without my change, and I cannot do that without stashing, which the rules forbid. My edits cannot reach the `work` path: `_actor_options`, `resident_plan_from_context`, and the server are unchanged by me, and my world edits affect only coin moves, the default-zero carried weight, the coin branch of `give`, and the `put`/`fetch` branches for names that are not containers (which those tests do not use). The supervisor should check these four on a clean tree.

## Limits

- **Purses are holder-only.** A purse has no lock. Only its holder can put coin in or take coin out, and that is the only access check. The brief's dual-key case for a purse is not implemented.
- **Resident policy.** No option is published for coin storage. `_actor_options` offers `put` and `fetch` only for goods, so no backend stores or takes coin. The cheap backend never stores coin.
- **Evaluation conservation not updated.** `bigville/village_eval.py` `_resource_snapshot` (outside this phase's write scope) does not read resident coins or purse coins. Coin stored in containers is counted there, through the container piles. A coin `fetch` is a conservative transfer action in `_CONSERVATIVE_TRANSFER_ACTIONS`, so its check sees the container fall and the resident's purse not rise, and it counts a failure. No village path publishes coin moves, so the registered village runs do not hit this. A two-line change to `_resource_snapshot` would count resident and purse coin: add `coin` per actor, and the `coin` attribute of each Purse node.
- **No strongbox kind.** The brief's examples name a strongbox. I did not add a container kind, which would have needed an item entry and an asset rebuild. A lockable `safe` and `chest` already exist.
- **Stored coin is not checkpointed by any test.** `Purse` and coin piles are plain values. The untracked persistence layer (`bigville/world_persistence.py`) has not been checked.
- **`_phys` change.** The coin pile's per-unit weight and volume are now read from the pack, not from the item default. This is an intended change, listed under Changed numbers.

## Open questions

1. Should the evaluation's conservation check (`village_eval._resource_snapshot`) count resident coin and purse coin? It is outside this phase's write scope. The change is small. The supervisor decides whether to add it.
2. Should a purse take a lock and a `keys_required` too, the way a container does? A dual-key treasury needs that. It would also need the purse to get a cell.
3. Should a backend publish `put` and `fetch` options for coin? That is a decision for Tract B's agent side.
4. Should `COIN_WEIGHT` and `COIN_VOLUME` get a sourced value? A real coin's mass is a few grams, but I did not source it.

## Follow-ups

- The untracked persistence owner: keep the `Purse.coin` attribute and the containers' `coin` piles across a checkpoint.
- Phase 011's Open question 1 (purses are not opened at founding): unchanged.
