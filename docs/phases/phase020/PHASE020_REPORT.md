# Phase 020: validate before claiming the action slot; refuse malformed proposals

## Summary

`major_action` now treats a refused attempt as free. Each branch runs the same physical checks the
primitive runs, and the action slot is held only while an attempt runs. A refused attempt releases
the slot and removes the turn record it created, so `actor_turn_state` is unchanged and the same
actor can act again in that turn. Malformed backend proposals (missing, mistyped or nonexistent
values) return False with no exception, in `_enact_plan` and in `major_action`. The retired `sell`
and `sell_labor` branches are removed. `BigvilleGame.step()` contains a failure while one actor's
response is applied. The other actors still apply and the turn completes.

Result: self-test 0 errors, 0 warnings. Full suite 831 passed, 2 skipped, 3 failed. The 3 failures
are the same ocelot-adapter tests that fail at baseline, with the same error.

## Changes

`worlds/bigville_world.py` (hunks by function; the other session's hunks are `resident_plan_from_context`
and the `_actor_options` line near 6688 in the working tree):

- `_husbandry_yield`: species mismatch, dead animal, unknown animal or task return 0.0 instead of
  `assert`. Unknown resident also returns 0.0.
- `milk`, `shear`: now delegate to new `_husbandry_act`. The slot is claimed only for a yield
  that happens (see Limits for the effect on the period routine).
- New helpers, placed before `major_action`: `_as_key`, `_as_amount` (reject bools, non-finite
  and non-numeric values), `_known_ref`, `_walked_toward`, `_rested`, `_claimed_attempt`
  (claim, run with dispatch set, release on refusal or exception, optional `consumed` for a refusal
  that still counts as an attempt), `_release_major_action` (restores `major_action_used`,
  `major_action_kind`, `last_major_action`, removes the `MajorAction` node and its `_turn_actions`
  entry).
- `major_action`: rewritten branch by branch. Every branch validates its arguments, then calls
  `_claimed_attempt`. Branches: `move` (refused when the destination equals the current cell),
  `move_object`, `give`, `transfer`, `take` (unchanged, returns False), `put`, `pick_up`, `drop`,
  `eat`, `rest` (always enacted), `fetch`, `build`, `maintain`, `care`, `tend_animals`,
  `work`/`make`/`start`, `water`, `harvest`, `sow`, `fertilise`, `pay_obligation`, `collect`,
  `deliver_collected`, `complete_request` (keeps its own claim, after its checks). `sell` and
  `sell_labor` branches removed. Unknown action names still raise `ValueError`
  (`test_bigville_world_migrated.py` asserts this for `buy`).
- `_enact_plan`: no `plan[...]` indexing. Uses `.get` with the key-type checks in `major_action`.
  Returns False for a non-dict plan, an unknown or missing `action`, a non-string `kind` for
  `eat`, and any target this resident does not have.

`bigville/game.py` (separate hunks from the other session's `record_action_outcome` block in `_apply_response`):

- New method `_apply_response_contained(actor, response)`: wraps `_apply_response`, records
  `"TypeName: message"` in `self.last_errors[actor]`, returns False.
- `step()`: `self.last_errors = {}` reset next to `self.last_results = {}`. The per-actor call
  now goes through `_apply_response_contained`.

`tests/test_phase020_validation.py` (new, 200 tests):

- 18 refusal scenarios, one per branch that can refuse (`fiscal` scenarios are separate): refused
  attempt leaves turn state and turn records unchanged; a following `rest` succeeds in the same turn.
- 4 fiscal tests: short payer keeps the slot (arrears); payer or collector out of reach is refused
  and frees the slot; deliver with nothing held is refused.
- Record release and accepted-attempt tests.
- 1 test per malformed major-action argument set (81 cases): missing key, wrong type, nonexistent target.
- The retired `sell` and `sell_labor` raise `ValueError`.
- 90 malformed backend plans (18 actions x 5 shapes), and a plan without `action`.
- Wrong-species milking and shearing return 0.0 and leave the slot free.
- Parity test: for 3 seeded residents of the 100-resident town at tick 1, each option from
  `actor_affordances` is enacted with `enact_plan` on a freshly built town. All return True.
- Containment: one actor's `enact_plan` raises. That actor's result is False, the other actor's
  move applies, `world._turn` advances, and `last_errors` names the error.

Existing tests: no assertion was edited and no existing test number was changed.

Design note: the slot is claimed before the primitive runs and released on refusal, rather than
reordering every primitive's checks ahead of its own claim. Several primitives already claim the
slot internally after their checks, and these now run with dispatch set so they do not claim twice.
A primitive's refusal path must not mutate world state. Pay and collect are the exception that is
deliberate: a short payer's arrears are recorded, so the slot stays used.

## Validation

Commands are run from `/home/matt/ozmadev/bigville`.

- Baseline before edits: `timeout 1500 python3 -m pytest -q -p no:cacheprovider`:
  631 passed, 2 skipped, 3 failed (ocelot adapter).
- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)".
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase020_validation.py`:
  200 passed.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (after edits): 831 passed, 2 skipped,
  3 failed. The failures are `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`,
  each with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
- Parity sweep over all 100 residents at tick 1 and tick 3 (`parity_sweep.py`, log in
  `parity_sweep.log`): 4,202 options enacted on fresh towns, all returned True
  (3,200 move, 1,000 work, 2 eat). No failures.

## Limits

- The parity sweep and test only cover the option kinds the town published: `move`, `work` and
  `eat`. No option of kind `fetch`, `put`, `give`, `tend_animals` and so on appeared in those states,
  so their enactment is covered only by the malformed-argument and refusal tests.
- `build` has no release-path refusal test: the town has no building projects at founding, so only
  the nonexistent-project precheck is exercised.
- Not every primitive was read line by line for mutation before refusal. Refusal paths of the
  branch primitives were checked by reading and by the refusal tests. `_accept_discrete_item`
  and `fetch` were read only in part.
- `enact_plan(actor, plan)` (public) still calls `dict(plan)`, so a non-mapping `plan` raises
  `TypeError`. I did not edit it: the other session's hunk in `resident_plan_from_context` ends
  4 lines above it. `_enact_plan` itself accepts only dicts.
- A partially applied response is not rolled back when `_apply_response` raises. Utterances
  before the failure point still apply.
- The 100-resident village was not run.

## Behaviour changes

No existing test number changed. Behaviour changes that a village run may show (not measured):

- A refused attempt no longer uses the slot. This covers `tend_animals` on a cooldown or from the
  wrong cell, `eat` of food not held, `fetch` of a missing item, `move` to the current cell
  (now refused), and `care` for a healthy resident.
- The period routine in `pass_period` (around line 5296 of `worlds/bigville_world.py`) calls
  `milk` and `shear` for farmers whose slot is free. A milking refused on cooldown no longer uses
  that farmer's slot, so the farmer may act again later in the period.
- `milk` and `shear` with the wrong species return 0.0. Before, they raised `AssertionError`.
- `major_action(..., "sell")` and `"sell_labor"` raise `ValueError`. Before, they claimed the slot and
  returned False.
- `BigvilleGame` has a new attribute `last_errors` (dict, reset each step). It is not in
  `game_persistence.py`, which is the other session's untracked file. If checkpoints should carry
  it, that file would need a change.

## Open questions

1. Should `enact_plan` also refuse a non-mapping plan? That needs an edit in the lines the other
   session has open.
2. Should a partly applied response be rolled back, or should an exception be surfaced as
   a turn error for that actor?
3. Keep the period routine's `milk`/`shear` claiming a slot for a refused milking, to keep the
   village unchanged? The current behaviour follows the phase rule, but it is not measured.
