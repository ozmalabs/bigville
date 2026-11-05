# Phase 015: roles, offices, and procedures from the pack

## Summary

The world no longer holds the role literals for households, registrar, land owners, village workers,
the bakery keeper, the winter grain reserve, or the gruel cook. Each now comes from a pack table:
HOUSEHOLDS, GOVERNANCE_OFFICES, LABOUR_TASKS, SHOP_CHAINS, LOCAL_POLICIES (winter_food_reserve), and
RECIPES (make_gruel). LAWMAKING_PROCEDURES and JUSTICE_PROCEDURES can be overridden by a scenario's
`procedures` key. Each civic record (proposal, vote, meeting, case, statement) carries the stage that
the pack lists for it. The records do not decide validity.

The acceptance fixture is `tests/fixtures/phase015_offices`, a child pack (`extends` bigville) that
renames the mayor to reeve and the clerk to notary. A world on that pack registers land under the notary
and holds a council vote under the reeve, with no code change.

Behaviour for the bigville pack is unchanged. The self-test output is byte-identical to the baseline. A
digest of the 100-resident town's households, land owners, residents, crop beds, and three village work
ticks matches HEAD. I edited no existing test.

Initial `git status --short` was empty (HEAD `53132e2`). Other sessions changed files during this phase
(see Deviations). I did not touch those files.

## Changes

### Role literals replaced

| Old literal (location in `worlds/bigville_world.py`) | Now read from |
|---|---|
| Household kind by role: `farmer`, `farm_labourer` -> farm; `clerk`, `councillor`, `mayor`, `constable`, `teacher` -> institutional; cast group `high` -> craft; else landless (`populate_town100`) | `HOUSEHOLDS[*].roles`, `.groups`, `.fallback` via `household_kind_for(role, group)` |
| `add_household(kind="landless_household")` default | `HOUSEHOLDS` kind with `fallback: true` (`kind=None` resolves to it) |
| Owners of founding parcels: `role == "farmer"` (`populate_town100`) | `HOUSEHOLDS.farm_household.land_roles` via `_land_holder_roles()` |
| Registrar: `role == "clerk"` when choosing the founding land-register clerk; `_require_clerk` | `GOVERNANCE_OFFICES[*].registrar` via `_registrar_roles()` |
| Baker seeding and baker work: `role == "baker"` (`populate_town100`, `_village_work_tick`) | `LABOUR_TASKS.bake.worker_roles` (new task row, see below) |
| Field workers: `farm_labourer` first, `farmer` if none (`_village_work_tick`); `farmer` or `farm_labourer` (`_seed_village_crops`) | `LABOUR_TASKS.farm.worker_roles` (priority order) via `_labour_workers` and `_workers_with_roles` |
| Miller: `role == "miller"` (`_village_work_tick`) | `LABOUR_TASKS.mill.worker_roles` |
| Gruel cook: trade `"cook"` (`_village_work_tick`) | `RECIPES.make_gruel.requires` (already in the pack; it is the trade the recipe names) |
| Bakery shopkeeper: `trade == "bakery" and role == "baker"` (`_shopkeeper_for_trade`) | `SHOP_CHAINS.bakery.keeper_roles` |
| Grain reserve `max(4.0, feed * 4.0)` (`_village_work_tick`) | `LOCAL_POLICIES.winter_food_reserve.parameters` = `minimum_grain` 4.0 and `feed_periods` 4.0, read by `_policy_parameters` |

### Scenario-overridable procedures and civic stages

- The scenario key `procedures` takes `{"lawmaking": {...}, "justice": {...}}`. Each stage given in full
  replaces or adds that stage. A stage given as `null` is removed. Any other top-level key raises
  ValueError. `_procedure_tables()` applies the overrides once, in `__init__`.
- Each stage in `LAWMAKING_PROCEDURES` and `JUSTICE_PROCEDURES` has a `civic_actions` list:
  lawmaking `proposal`, `meeting`, `vote`; justice `case`, `statement`. `_civic_record(table, action)` puts
  `civic_action` and `stage` on each record. An action that no stage lists gets `stage: ""`.
- Records that now carry a stage:
  - `LawProposal` (`proposal`, stage `proposal`).
  - `CouncilVote` (`vote`, stage `vote`). This is a new node per vote, linked by `has_vote` from the town
    and `cast_vote` from the voter. The `voted_for`/`voted_against` edges are kept, so the tally is
    unchanged.
  - `CouncilMeeting` (`meeting`, stage `deliberation`).
  - `Case` and `LandDispute` (`case`, stage `complaint`).
  - `CaseStatement` and `LandDisputeStatement` (`statement`, stage `judgment`).
- The world records these stages and makes no check on whether a stage was carried out validly.

### Pack data (packs/bigville only)

| File | Change |
|---|---|
| `frames/households.json` | Added `roles`, `groups`, `land_roles`, `fallback` to the four kinds. Documented in `_doc`. |
| `frames/governance_offices.json` | `clerk` gets `registrar: true`. `_doc` added. |
| `frames/labour_tasks.json` | `worker_roles` on `farm` and `mill`. New row `bake` (skills `baker`, `worker_roles` `baker`, inputs `flour`, `water`, output `bread`). |
| `world/shop_chains.json` | `bakery.keeper_roles: ["baker"]`. |
| `frames/local_policies.json` | `winter_food_reserve.parameters`. `_doc` describes parameters. |
| `frames/lawmaking_procedures.json` | `civic_actions` on each stage (`proposal`, `meeting`, `vote`; others `[]`). |
| `frames/justice_procedures.json` | `civic_actions` on each stage (`case`, `statement`; others `[]`). |

`packs/test_hamlet` is unchanged. Its HOUSEHOLDS and GOVERNANCE_OFFICES tables are empty, it has no
winter policy, and the village work tick is not run for it.

### Self-test (`domains/bigville_entities.py`, `check_consistency`)

New checks, all passing on bigville and hamlet:
- HOUSEHOLDS: exactly one fallback; no role or group listed by two kinds; groups in low/middle/high;
  `land_roles` a subset of `roles`.
- GOVERNANCE_OFFICES: at least one registrar when the table is not empty; a registrar's authority is
  `records`; `appoints` names offices.
- LABOUR_TASKS: a `worker_roles` list, when present, is not empty.
- LAWMAKING/JUSTICE_PROCEDURES: `civic_actions` use only that table's actions, each listed once.
- POLICIES: `parameters` values are numbers >= 0; winter_food_reserve has `minimum_grain` and `feed_periods`.

### Files

- `worlds/bigville_world.py`: the replacements above, `household_kind_for`, `_land_holder_roles`,
  `_registrar_roles`, `_workers_with_roles`, `_labour_workers`, `_procedure_tables`, `_civic_record`,
  `_policy_parameters`, stage fields on civic records. `_require_clerk` now checks the registrar role.
- `domains/bigville_entities.py`: new checks (above).
- `packs/bigville/frames/{households,governance_offices,labour_tasks,lawmaking_procedures,justice_procedures,local_policies}.json`
  and `packs/bigville/world/shop_chains.json`: data above.
- `tests/test_phase015_offices.py` (new, 13 tests).
- `tests/fixtures/phase015_offices/` (new): `pack.json` (`extends: bigville`, replaces GOVERNANCE_OFFICES and
  HOUSEHOLDS), `frames/governance_offices.json` (mayor -> reeve, clerk -> notary with registrar true),
  `frames/households.json` (institutional roles notary, councillor, reeve, constable, teacher).
- `docs/phases/phase015/`: this report, `behaviour_digest.py`, the self-test and digest outputs, and the
  pytest outputs.

## Validation

| Command | Result |
|---|---|
| `git status --short` (start) | empty |
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0). Output identical to the baseline (`diff docs/phases/phase015/before_selftest.txt docs/phases/phase015/after_selftest.txt` is empty). |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0), WARNINGS (0) (`after_selftest_hamlet.txt`) |
| `PYTHONHASHSEED=0 python3 docs/phases/phase015/behaviour_digest.py` on `git archive HEAD`, and on HEAD plus my changed files | byte-identical (`digest_head.json`, `digest_head_plus_my_files.json`). The digest covers 100 households, residents, land owners, crop beds after seeding, and three `_village_work_tick` calls with `pass_period(1)`. It does not run `run_village`. |
| Same digest on the working tree (including other sessions' edits) | byte-identical to HEAD (`digest_working_tree.json`) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase013a_packs.py tests/test_phase013b_data_pack.py tests/test_phase014_parameters.py` | 28 passed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase015_offices.py` | 13 passed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (full suite) | **1 failed, 367 passed, 1 skipped** (83 s; `after_pytest.txt`) |
| Full suite with `--ignore=tests/test_bigville_ocelot_communication.py` | 367 passed, 1 skipped (`after_pytest_excluding_foreign_file.txt`) |

The one failure, verbatim:
`FAILED tests/test_bigville_ocelot_communication.py::test_real_ocelot_is_free_text_capable_but_raw_speech_is_opaque`
`ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`

That file is untracked and came from another session. The module it imports exists nowhere in this
checkout, so the failure does not come from this phase. I did not work around it.

The one skip is `tests/test_bigville_game_api.py:180`, "real Ocelot provider is not on PYTHONPATH".

Test-file edits: none. No existing test number or assertion was changed.

## Limits

- The 100-resident village (`run_village`) was not run. The digest runs three work ticks and no cognition.
- The grain-reserve test uses a child pack (`minimum_grain` 10) and a single miller. It does not test
  the reserve across a full run.
- `_require_clerk` has no callers in the code. It is kept and now reads the pack, but no path enforces
  it. `register_land` and `write_deed` still accept any actor as the clerk, as before.
- Procedure stages are recorded but not checked. A scenario can give any stage names, and a missing
  stage yields `stage: ""`.
- The LABOUR_TASKS `bake` row (`inputs: flour, water`) was added for the baker lookup. Its inputs are not
  used by the production balance beyond the self-test's item-use list, which is unchanged.
- The `resident_plan_from_context` hunk (see Deviations) is not part of this phase. Its behaviour was
  not checked here.

## Deviations and surprises

- **Another session edited files in this checkout during the phase.** Modified: `bigville/backends/ocelot.py`,
  `bigville/game.py`, `docs/AGENT_BACKENDS_PLAN.md`, `tests/test_bigville_game_api.py`,
  `tests/test_bigville_scenarios.py`. Untracked: `tests/test_bigville_ocelot_communication.py`. I did not
  change or revert any of them.
- **`worlds/bigville_world.py` contains a method I did not write.** `resident_plan_from_context` (about line
  5905) is not in HEAD. It arrived during the phase. The file-level diff therefore includes it. Committing
  `worlds/bigville_world.py` would include it too. The supervisor needs to separate the two before committing.
- **One intermittent failure.** `tests/test_bigville_game_api.py::test_village_resident_observes_affordances_decides_and_receives_outcome`
  failed once, in a three-file batch (1 failed, 148 passed). It passed on the rerun, and on 8 hash seeds run
  alone. I could not reproduce it. It ran while the other session's edits to that test file were in place.
- The brief asked for `bigville_world` literals only. I also changed `SHOP_CHAINS.bakery` (a shopkeeper
  rule) and used `RECIPES.make_gruel.requires` for the cook. Both removed literals in `_shopkeeper_for_trade`
  and `_village_work_tick`.
- `LABOUR_TASKS` gained a `bake` row, which the brief did not name. Without it, the baker lookup had no
  pack home.
- The vote record is a new node (`CouncilVote`), where the old code kept only an edge. The tally and the
  edges are unchanged.
- `_require_clerk`'s assertion message changed from "is not the village clerk" to "does not hold a registrar
  office". No test matches the old text.

## Left in code (deliberately)

| Literal | Where | Reason |
|---|---|---|
| Role-to-task sets (`farmer`, `farm_labourer`, `woodworker`, `doctor`, `midwife`, ...) | `bigville/backends/cheap.py` (about lines 151-155, 272-276) | Backend cognition, not world code. Out of this phase's scope. |
| Speech chatter keyed by role (`"farmer": "The fields need rain..."`) | `bigville/runtime.py` (about line 261) | Runtime chatter, not world code. |
| ROLE_SPEC, role counts, names, anchors | `worlds/bigville_town100_world.py` | Phase 016 (founding town as pack data). |
| `seed_roles` (`mayor`, `clerk`, `constable`, ...) | `packs/bigville/frames/*_policies.json`, `*_laws.json`, `charters.json` | Pack data. Only `shared_concepts_for` reads it, and nothing calls that helper (it is marked legacy). Still names the old offices. See open question 1. |
| Recipe names `make_gruel`, `grind_flour`, `bake_bread` | `_village_work_tick`, `_village_start` | Recipe identifiers, not roles. |
| Bread target `200.0` and `3.0` per resident | `_village_work_tick` | Scenario quantities, not roles. Outside this phase's list. |
| Civic action names `proposal`, `meeting`, `vote`, `case`, `statement` | `worlds/bigville_world.py` civic methods | These name the record kinds in the brief. The stage each maps to is in the pack. |
| Animal species `cow`, `sheep` for milk and shear | `_village_work_tick` | Animal kinds, not roles. |
| Building and map names (`granary`, `kitchen`, `wellhouse`, `bakery` alias) | `populate_town100`, the building alias table | Buildings, not roles. |
| `_shopkeeper_for_trade` generic `role == trade` | same function | Generic rule, not a literal role. |

## Open questions

1. Should `seed_roles` name offices (for example, `reeve`) or stay as data about the old names? In the
   fixture, the renamed offices keep the old names in `seed_roles`. Nothing reads them today.
2. Should `register_land` require the clerk to be a registrar? The boundary audit says a register entry is
   a record and must not be gated by role. The current code does not check, and this phase kept that.
3. Should a registrar check run anywhere? `_require_clerk` has no callers today.

## Follow-ups

- Phase 016: move `ROLE_SPEC` and the founding cast's roles into pack population data.
- Decide on `seed_roles` (open question 1) when the concept seeding is revisited.
- Backends: read role-to-task sets from the pack (`cheap.py`), and replace the runtime chatter keys.
- Separate the `resident_plan_from_context` hunk from this phase before committing `worlds/bigville_world.py`.
- Check the `test_village_resident_observes...` flake once the other session's test edits settle.
