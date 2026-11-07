# Phase 040: objects as arms (hitting and throwing)

## Summary

Any discrete object a resident holds in a hand can be swung (`strike` with `with`) or thrown (the new `throw`
major action). Harm, range, breakage and the cost of a heavy object come from the object's own data: ITEMS weight,
MATERIALS hardness and fragility, the container flag, and TOOL_FIT's edge lists. The numbers are in a new pack table
`OBJECT_FORCE`, all APPROX. A thrown object that reaches a resident is a contest: the target may step aside (the only
reaction offered), and a thrown object can miss, land on a neighbouring cell, or break.

Everything is behind the physical subsystem `object_force`, default off. With it off, a strike ignores `with` and a
throw is refused as `unsupported`. The self-test is at 0 errors and 0 warnings. The 22 new tests pass. The full suite
has 8 failures, and each is accounted for below: one is the Phase 054 packet snapshot, which the supervisor
anticipated, and seven are not from this phase.

Bulk goods (stone, loaf, firewood log) are not discrete items in the pack, so they cannot be thrown in this slice.
The acceptance test uses the hammer and the wooden mug instead.

## Changes

### New files
- `packs/bigville/world/object_force.json`: table `OBJECT_FORCE` (17 keys, all APPROX, with the model in `_doc`).
- `packs/test_hamlet/world/object_force.json`: the same table, so the standalone pack keeps a clean self-test.
- `tests/test_phase040_objects_as_arms.py`: 22 tests.
- `docs/phases/phase040/` (this report, and logs listed under Validation).

### Edited files, with my hunks
- `worlds/bigville_world.py`, by function:
  - `PHYSICAL_SUBSYSTEM_DEFAULTS`: key `object_force: False`.
  - `_drop_discrete_item`: optional `cell` argument (default is the actor's cell, so existing callers are unchanged).
  - New section "objects as arms (Phase 040)", placed before the strike section: `_object_on`, `_hand_held_item`,
    `_object_material`, `_object_weight_term`, `_object_hardness_term`, `_object_edge_term`, `_object_mult`,
    `_weapon_mult`, `_object_breaks`, `_object_material_entry`, `_weapon_for_strike`, `_throw_range`,
    `_cell_occludes`, `_throw_flight`, `_throw_miss_cell`, `_release_thrown`, `_publish_throw`, `_as_cell`,
    `throw_begin`, `throw_resolve`.
  - `contest_begin`: dispatches `throw` to `throw_begin`.
  - `take_resolve`: dispatches `throw` pending to `throw_resolve`; and, inside the redirected branch, the disarm
    (gated on `object_force`) that drops the attacker's first hand-held item on the cell.
  - `strike_begin`: reads `with` (gated); a `weapon` entry on the pending dict.
  - `strike_resolve`: the weapon's multiplier on the attacker's power; its effort on the attacker's cost; wear, and
    breakage when it hit; `weapon` in the result.
  - `enact_plan`: `throw` takes no option lookup; `_enact_plan` passes `with` to `strike` and routes `throw`.
  - `major_action` (keyword path): `strike` takes `with_kind`; new `throw` branch.
  - `_attempt_verb`: a verb whose `route` is `throw` delegates to the `throw` action.
- `bigville/game.py`, `_is_contest`: adds `"throw"` to the contest actions (one line, plus docstring). See Deviations.
- `domains/world_affordances.py`: `OBJECT_FORCE = _PACK["OBJECT_FORCE"]`, after `TOOL_FIT`.
- `domains/bigville_entities.py`: a call to `_check_object_force` after `_check_tool_fit`; new functions
  `_check_object_force` and `_object_weight_term_of`.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: one manifest entry each, `OBJECT_FORCE` after `TOOL_FIT`.
- `packs/bigville/world/resolution.json`: `VERBS.throw` gets `route: "throw"`, a new description, and
  `implemented: true` (was `false`).
- `packs/bigville/world/major_actions.json`: `strike` description now names `with`; new `throw` entry.
- `tests/test_simple_life.py`: expected `physical_subsystems` dict gained `"object_force": False`.
- `tests/test_scenario_runner.py`: expected `physical_subsystems` dict gained `"object_force": False`.

No change to `bigville/backends/cheap.py` (its policy never proposes a throw, and its strike trigger is unchanged),
`bigville/backends/protocol.py`, or the Phase 054 fixture.

### Numbers changed in existing tests
- `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration`: the expected
  dict gained `object_force: False`. Reason: a new switch.
- `tests/test_scenario_runner.py` (the first-run `physical_subsystems` assertion): gained `object_force: False`.
  Reason: a new switch.
No assertion was weakened or removed.

## Design

- **Harm of a blow with an object**: the Phase 038 bare-hand blow times the object's multiplier. An authored
  TOOL_FIT `strike` row (the knife's 0.3, effort 2.0) is used as it is. Otherwise the multiplier is
  `harm_scale x weight_term x hardness_term`, with `harm_scale` 2.0 so a metal hammer strikes twice as hard as a fist.
  The unarmed path is unchanged and still bypasses TOOL_FIT, as Phase 038 set out.
- **Clumsiness**: a load heavier than `unwieldy_above` x effective strength divides the multiplier by the ratio and
  multiplies the stamina by it (capped at `effort_cap`).
- **Throw range**: `range_base` x effective strength x intensity, over the weight (at least the reference weight),
  at most `range_max` cells. The flight follows the grid line (`_line`) and stops before an off-map cell or a sight
  occluder (Phase 028's `sight_occluders`). Out of range, it stops short. Neither case is refused.
- **Throw contest**: aim = (1 + technique_weight x skill) x exhaustion step x distance falloff / accuracy loss above
  intensity 1. A target that does not step aside has `passive_defence`. A target that steps aside has
  (1 + technique_weight x skill) x exhaustion step. A hit when aim reaches defence. Harm = `throw_harm` x thrown
  multiplier x intensity x distance falloff x hit quality (0.5 to 1).
- **Breakage**: on impact (an obstacle, or a person hit) an object breaks when its material's fragility reaches
  `any_fragility`, or when it is a container and the fragility reaches `container_fragility`. A broken object is kept
  as a broken tool and removed from the map (`_wear_tool` to condition 0).
- **Cost and strain** of a throw are the resolution core's (`_resolve_terms`), on a demand of weight over
  `throw_demand_unit`. Wear is the tool-wear path. Noise is published only when an object breaks.
- **Observation**: a throw is an event named `throw`, with the landing cell in its detail, seen by the witnesses.
  The world records no assault, offence or threat (a test checks that no such kind is observed).
- **Determinism**: no randomness; a test replays the same throw and compares.

## Validation

Commands and results (all run in `/home/matt/ozmadev/bigville`):

- `python3 domains/bigville_entities.py`: exit 0; `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0; `ERRORS (0)`, `WARNINGS (0)`. Log:
  `docs/phases/phase040/hamlet_check.log`.
- `python3 tools/generate_seeds.py --check`: exit 0; seeds match pack `bigville` (31 files). Log:
  `docs/phases/phase040/seeds_check.log`. No seed is regenerated: no seed data changed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase040_objects_as_arms.py`: 22 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase013a_packs.py tests/test_phase040_objects_as_arms.py tests/test_simple_life.py tests/test_scenario_runner.py`: 53 passed.
- `PYTHONPATH=. python3 /tmp/death_probe.py 192` (the 100-resident simple town, 192 turns, switch off): `"deaths": 0`,
  `"first_death_turn": null`. Log: `docs/phases/phase040/death_probe_192.log`.
- `tests/test_phase058_persona.py`: passes in the full run.
- Full suite, `timeout 3600 python3 -m pytest -v -p no:cacheprovider -rfE --durations=25`:
  **1852 passed, 8 failed, 3 skipped** of 1863 collected, in 1709.8 s. Log:
  `docs/phases/phase040/full_suite_run2_verbose.log`.
  - The brief's `timeout 1500` run was cut off at about 85 percent (the village tests are slow on this machine), so I
    raised the limit. The 1500-second run was started while another session's suite was also running.

Failures and their causes:

1. `tests/test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`: **mine, expected.**
   Adding `throw` to MAJOR_ACTIONS and changing the `strike` description grew the packet's system text from
   5673 to 5688 characters. The fixture `tests/fixtures/phase054_packet_snapshot.json` is not edited.
2. `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`:
   baseline. `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. Tract B's untracked file.
3. `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`
   and `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`:
   not from this phase. Each passes when run alone, and the mixed village test passes with the parity file. It fails
   when it runs after `test_bigville_ocelot_communication.py` (checked: 2 failed), so the baseline import failure
   leaves state behind. Tract B's files.
4. Four tests in `tests/test_phase057_tui.py` (`test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
   `test_over_http_walking_to_a_known_place_sends_the_rows_destination`,
   `test_over_http_a_reaction_is_delivered_to_the_holder`,
   `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`): **not from this phase.** The file
   passes on a clean HEAD export (48 passed). It also passes in a scratch copy of this tree that has my changes but
   `bigville/server.py` restored to HEAD (48 passed). The cause is Tract B's uncommitted `bigville/server.py`
   (36 changed lines). The refusal test expects a 400 for a bad intensity; the working server returns 200.

Behaviour checks in `tests/test_phase040_objects_as_arms.py` (22 tests, all pass): a hammer blow does twice a bare
blow's harm at the same cost; a pot is clumsy and costly for a weak swinger and not for a strong one; a wooden mug that
strikes breaks and a hammer only wears; a hammer thrown at range harms more than a wooden mug thrown at the same range;
harm falls with distance; range falls with weight and rises with strength; a throw short of range lands short, and a
throw at a wall stops on the open cell before it (a mug there breaks, a hammer survives); a miss lands on a neighbouring
cell and can be picked up again after walking there; a skilled defender steps aside from an unskilled thrower, and a skilled thrower hits a target that does not step aside; a redirected grab drops the attacker's hand object;
the live object count changes only by breakage; the same throw replays to the same result; the throw is an event
witnesses observe; the `attempt` verb `throw` is the throw action; with the switch off a strike ignores `with` and a
throw is refused as `unsupported`.

## Limits

- Every number in `OBJECT_FORCE` is APPROX and a model choice. The tests check the signs of the relations (heavier
  harms more, range falls with weight, harm falls with distance, a skilled defender steps aside), not the magnitudes.
- Bulk goods (stone, loaf, firewood log) cannot be swung or thrown. Only discrete items in hand can.
- A throw's reaction is only "evade". Resist, brace and yield do not apply to a thrown object.
- The game's react loop (`BigvilleGame` offering `react` to a holder, then `throw_resolve`) is not tested end to end.
  I tested `_is_contest` and the world methods only.
- The 100-resident town was not run with `object_force` on. The probe ran with it off only.
- Observation: a strike with an object is recorded as a `strike` event, without naming the object. A throw names it.
  What a resident holds is visible through the existing observation path, which I did not change or test.
- No bows, slings, armour, or blocking (out of scope per the brief).

## Deviations from the brief

- `bigville/game.py` got one line beyond "the event only": `_is_contest` now includes `throw`. Without it a throw at a
  resident has no reaction turn, and the brief requires one.
- The brief's example "a mug or a pot shatters". In ITEMS, the pot is metal (fragility 0.2), so it does not break.
  Only the wooden mug (a container of wood, fragility 0.6) breaks. See Open questions.
- Bare hands: the brief says the bare-hand row is `mult 0.05`. That row is TOOL_FIT's `hands_fit`, which the armed path
  does not use. The unarmed blow stays on the Phase 038 path, as Phase 038 specifies.
- Convention: an enacted throw returns `applied: True` even when it misses, because the object left the hand. A
  missed or evaded blow returns False, as Phase 038 has it. The two actions differ on purpose: a throw always moves
  the object.
- Disarm: the brief asks that a redirected take drop the attacker's held object. I drop the first object in the
  attacker's hand, since a take carries no object of its own. Gated on `object_force`.
- `cheap.py` is unchanged. The brief permits a change only if its policy already chose violence, and it does not.

## Open questions

1. Should a metal pot break when thrown or swung? ITEMS calls the pot metal, so it does not break under the current
   breakage rule. The brief's example implies it should. A ceramic material or a `breakable` flag would settle it.
2. Should bulk goods be throwable? That needs one unit taken from a stock pile and dropped as a pile on the landing
   cell. It touches the stock path and is a separate phase.
3. Should the packet snapshot be regenerated? The change (`throw` added, `strike` description extended) is intended.
   The fixture is Tract B's to update, or the supervisor's.
4. Should `object_force` become the default? Not in this phase: the brief says default off.

## Follow-ups

- Tract B: the four TUI failures come from `bigville/server.py`. Its 400 check on the intensity reply is gone in the
  working copy.
- Tract B: `test_bigville_ocelot_communication.py` leaves import state behind, which breaks the mixed-village tests when
  it runs first. The adapter module is missing from this checkout.
