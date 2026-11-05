# Phase 011: fiscal institutions as data

## Summary

The fiscal institutions from the eight seed files are now data: nine institution entries in
`FISCAL_INSTITUTIONS`, two purses and four physical actions in `world/fiscal.json`, and a backend-owned list for
the rules the world does not decide. All 44 seed rules map to exactly one entry or to the backend. The world
has the physical side: purses hold coin, and obligations record what is owed and any arrears. Coin moves only
when the parties stand together and the coin is there.

Phase 011 is not complete. One existing acceptance test, `tests/test_phase015_offices.py::test_the_fixture_renames_two_offices_and_inherits_everything_else`,
now fails because the fiscal entries name the offices `clerk` and `mayor`, which that fixture renames. See Open questions.

This run resumed a previous run that stopped partway. The previous run's data is kept, with the corrections listed under Changes.

## Changes

Files created in this phase, or created by the previous run and kept:

- `packs/bigville/frames/fiscal_institutions.json`: `FISCAL_INSTITUTIONS` (9 entries) and `FISCAL_BACKEND_OWNED` (20 rows).
- `packs/bigville/world/fiscal.json`: `FISCAL_PURSES` (`treasury`, `church_funds`) and `FISCAL_ACTIONS` (`assess_obligation`, `pay_obligation`, `collect`, `deliver_collected`).
- `packs/test_hamlet/frames/fiscal_institutions.json`, `packs/test_hamlet/world/fiscal.json`: empty tables, so the test hamlet has no fiscal rules.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: four new table entries each.
- `bigville/seeds/gen_fiscal_*.json` (9 files): generated from `FISCAL_INSTITUTIONS` by `tools/generate_seeds.py`. The eight hand-written seed files are unchanged.
- `domains/generated_seeds.py`: one `gen_fiscal_<name>` seed per institution.
- `domains/knowledge.py`: fiscal institutions are knowable like laws (`fiscal:<name>` rows), and `check_knowledge` checks their `knowledge` spec.
- `domains/shared_frames.py`: exports `FISCAL_INSTITUTIONS`, `FISCAL_BACKEND_OWNED`.
- `domains/world_affordances.py`: exports `FISCAL_PURSES`, `FISCAL_ACTIONS`, and `round_bp(amount, bp)`, which returns `(amount*bp + 5000) // 10000` for whole coins. It rejects fractions, negative amounts, and rates outside 0..10000.
- `domains/bigville_entities.py`: `check_fiscal` and `_check_fiscal`, called from `check_consistency`.
- `worlds/bigville_world.py`: `from domains.world_affordances import round_bp`. New methods after the retired `pay_wage` stub: `found_purse`, `_purse_node`, `_fiscal_party`, `_party_location`, `_acts_for`, `_move_fiscal_coin`, `_obligation_attrs`, `_record_arrears`, `assess_obligation`, `pay_obligation`, `collect`, `deliver_collected`. New branch in `major_action` for `pay_obligation`, `collect`, `deliver_collected`.
- `tests/test_phase011_fiscal.py` (new, 38 tests).
- `tests/test_phase017_generated_seeds.py`: one number changed (see Validation).
- `docs/phases/phase011/PHASE011_REPORT.md` (this file).

Hunks in `worlds/bigville_world.py` that are not mine (other session, left as found): the `"food"` key in the fetch option in `_actor_options`, and `resident_plan_from_context`.

Two pack files were rewritten in the exporter's layout (`tools/export_pack.py`). The content is identical, checked by loading both versions. The exporter rewrites them as multi-line JSON, and `test_phase013a_packs::test_export_rerun_is_byte_identical` requires that layout.

`_doc` in the previous run's files is kept.

### Rule-to-entry mapping

| Entry | Seed files | Seed rules |
|---|---|---|
| `council_tax` | bigville_fisc_state, bigville_clerk_treasurer | fs_collect, ct_collect, ct_reconcile |
| `treasury_salaries` | bigville_fisc_state, bigville_clerk_treasurer | fs_pay_salary, fs_salary_unfunded, fs_treasury_empty, ct_pay_clerk |
| `rent_and_tenancy` | bigville_coll_collect, bigville_fin_tenure | bc_collect_self, bc_collect_miss, bf_rent_pay, bf_rent_miss |
| `mortgage` | bigville_fin_tenure | bf_mortgage_pay, bf_mortgage_miss |
| `tithe_and_donation` | bigville_fisc_church | fc_tithe |
| `church_stipend_and_charity` | bigville_fisc_church | fc_stipend, fc_stipend_unfunded, fc_charity, fc_charity_unfunded, fc_church_defunct |
| `wages` | bigville_coll_collect | bc_pay_wage |
| `hired_collection` | bigville_coll_collect | bc_collect_hired, bc_deliver |
| `school_fund` | bigville_school_fund | sc_school_open, sc_school_close |

24 rules are mapped this way.

### Backend-owned rules

`FISCAL_BACKEND_OWNED` lists the other 20 rules, each with a reason in the data:

| Rule | Seed |
|---|---|
| `fs_set_tax`, `fs_graft`, `fs_levy` | bigville_fisc_state |
| `bf_foreclose`, `bf_evict`, `bf_homeless_affect`, `bf_owner_equity`, `bf_mortgagor_equity`, `bf_appreciate`, `bf_rent_raise` | bigville_fin_tenure |
| `lm_wage`, `lm_switch` | bigville_labour |
| `ec_extract`, `ec_price_glut`, `ec_price_scarce`, `ec_wage`, `ec_switch` | bigville_econloop |
| `fc_donate_occasional`, `fc_parsonage_precarious`, `fc_counsel` | bigville_fisc_church |

### Purse and action design

- **Purses** (`FISCAL_PURSES`): `treasury` (holder role `clerk`) and `church_funds` (holder role `pastor`). Each is a graph node of type `Purse` with `coin`, `recorded` (the ledger: coin in minus coin out), `holder`. `found_purse(name, holder)` opens one; it refuses an unknown name, a second open of the same name, or a holder with the wrong role. Opening coin is 0 (APPROX: the seeds give no opening figure).
- **Obligation** (one node type, `Obligation`). `assess_obligation(institution, debtor, creditor, amount=… | base=…, rate_bp=…, collector=…)` records one period. The amount is either given or `round_bp(base, rate_bp)`. Parties are residents or purses. A hired collector must be a resident who is not the debtor. The agent chooses the figures, and the world only checks that they are whole coins.
- **One payment action, not one per tax** (brief item 1 allowed this). `pay_obligation(actor, obligation)` takes the institution from the obligation record. The institution is stored on the record, not in the method name.
- **`pay_obligation`** is the payer's action. The actor must be the debtor, or the holder of a purse debtor. The receiver must stand on the same cell.
- **`collect`** is the collector's action. The collector is the creditor (or the purse holder), or the hired collector named on the obligation. The debtor must stand on the collector's cell.
- **`deliver_collected`** is the hired collector's action. It moves `round_bp(held, share_bp)` to the creditor, who must stand with the collector. The rest is recorded as skimmed. It is named `deliver_collected` because `BigvilleWorld.deliver(self, merchant)` already exists.
- **Major-action slot**: `pay_obligation`, `collect`, `deliver_collected` claim the turn's one major action through `major_action`. Direct calls do not.
- Actions are listed in `FISCAL_ACTIONS` and are **not** in `MAJOR_ACTIONS`. See Limits.

### Arrears record

- A payment or collection that is refused for lack of coin, with the payer or debtor reached on the receiver's cell, records `arrears += 1` on the obligation. No coin moves.
- A payment or collection where the payer is not on the same cell is refused and records nothing.
- Nothing else changes on a miss: no eviction, no foreclosure, no service stop, no node added or removed. The test `test_a_missed_rent_becomes_arrears_with_no_eviction_and_no_other_change` checks that only the obligation's `arrears` value changes.

### Knowledge and seed changes

- Each institution has a `knowledge` spec (`topics`, `public`, `after_years`, `understanding_requires`). `public` values and `understanding_requires` are authored judgement (APPROX), not sourced figures. They are checked by `check_knowledge`.
- `understanding_requires` names offices `clerk` and `mayor` for `council_tax` and `treasury_salaries`. This is the cause of the Phase 015 failure below.
- Seed files: the eight hand-written files are unchanged. Nine `gen_fiscal_*.json` files are generated. `tools/generate_seeds.py --check` reports 31 files, matching the pack.
- Concept names `fiscal_<name>` do not appear in any hand-written seed file (checked by grep). The hand-written seeds have no `concepts` entries.

## Validation

Commands, run on this checkout:

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Info line: `FISCAL: 9 institutions, 44 seed rules mapped (20 backend-owned), 2 purses`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, no balance or job issues.
- `python3 tools/generate_seeds.py --check`: exit 0, `generated seeds in ... match pack 'bigville' (31 files)`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase011_fiscal.py`: 38 passed.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (full suite): **4 failed, 630 passed, 2 skipped** in 134 s. Failures:
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities` (other session), verbatim: `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` raised via `OcelotUnavailableError: Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter and its dependencies on PYTHONPATH; select 'simple' for local NPCs. Adapter import failed (ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter')`.
  - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control` (other session): `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
  - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action` (other session): `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
  - `tests/test_phase015_offices.py::test_the_fixture_renames_two_offices_and_inherits_everything_else` (this phase, see Open questions), verbatim: `assert report["errors"] == [] and report["warnings"] == []`, with `KNOWLEDGE FISCAL_INSTITUTIONS council_tax: unknown office clerk`, `KNOWLEDGE FISCAL_INSTITUTIONS council_tax: unknown office mayor`, `KNOWLEDGE FISCAL_INSTITUTIONS treasury_salaries: unknown office clerk`, `KNOWLEDGE FISCAL_INSTITUTIONS treasury_salaries: unknown office mayor`.
- Suite with the other session's files ignored (`tests/test_bigville_game_api.py`, `tests/test_bigville_scenarios.py`, `tests/test_bigville_*persistence*.py`, `tests/test_bigville_ocelot_*.py`, `tests/test_mixed_ocelot_*.py`): **1 failed, 576 passed**. The one failure is the Phase 015 test above.
- `tests/test_phase013a_packs.py`: 8 passed (after the exporter layout fix below). `tests/test_phase017_generated_seeds.py`: passes after the count change below.

Changed numbers and why:

- `tests/test_phase017_generated_seeds.py`, `test_regenerating_is_byte_identical`: the expected file count changed from `22` to `31`. The nine new `gen_fiscal_*.json` seeds are the difference, so the count of generated files changed by design.

The earlier failure in `test_phase013a_packs::test_export_rerun_is_byte_identical` came from the hand-written layout of two fiscal pack files. Adopting the exporter's layout fixed it, with the content unchanged.

## Limits

- **Purses are not opened at founding.** `from_town100` does not call `found_purse`, so a founded town has no treasury or church purse yet. Tests open them explicitly.
- **Arrears record only attempts.** A period is recorded as arrears only when a payment or collection is attempted and found short. A debtor no one visits accrues no record. Nothing marks a period as missed when time passes.
- **Not in the LLM prompt.** `FISCAL_ACTIONS` is not in `MAJOR_ACTIONS`, so `bigville/backends/prompts.py` does not list the actions and no backend chooses them yet. They can be called as direct world methods or through `major_action`. Adding them to `MAJOR_ACTIONS` (with descriptions, as Phase 018 requires) belongs with a backend route for them.
- **Purse coin is outside resident reports.** `bigville/reporting.py` sums `coin` over living residents only. Purse coin does not appear in those figures. Phase 041 covers coin in containers.
- **Checkpoints not tested.** `Purse` and `Obligation` nodes use scalar attributes, which the graph encoder accepts (`bigville/runtime.py`). I did not run a save and reload with them.
- **No rates, no decisions.** The world sets no rate, does not decide to pay, collect, evict, or foreclose.
- **Scope.** The brief named `pay_tax`, `pay_rent`, `pay_tithe`, `pay_mortgage`, and `collect`. I implemented one `pay_obligation` plus `collect` and `deliver_collected`, because the seed rules have one shape: a debtor, a creditor, a period amount.
- **No long village run.** I did not run `from_town100`.

## Open questions

1. **Phase 015 acceptance fixture (blocking the suite).** `tests/fixtures/phase015_offices` renames `mayor` to `reeve` and `clerk` to `notary`, and its test asserts the child pack has no consistency errors. The fiscal entries name `clerk` and `mayor` in `understanding_requires` (and `clerk` in `holder_role` and `agent_role`, though those resolve because `clerk` is also a job). The result is four knowledge errors. Options, for the supervisor to choose:
   1. Express the office clause in `understanding_requires` through a role-independent predicate. This needs a `knowledge.py` extension, which is outside this phase.
   2. Extend the Phase 015 fixture to rename the fiscal references too. That changes a test owned by another phase, and the fixture's stated purpose ("inherits everything else") argues against it.
   3. Drop the office clauses and leave the institutions public to everyone. This changes the authored meaning of `understanding_requires`.
   I did not pick one, because each option is outside this brief.
2. **Office and job holder roles.** `found_purse` checks that the holder's `role` attribute equals the purse's `holder_role`. Whether a resident keeps the role after an office change is not modelled.
3. **Whether `FISCAL_ACTIONS` should join `MAJOR_ACTIONS`** once a backend route exists. Phase 018 requires a description for each entry, and every entry has one.

## Deviations from the brief

- The brief said to follow `pay_wage`. `pay_wage` is now a retired stub that returns `False`. The new methods follow the physical checks of `_physical_transfer_precheck` (co-location, possession, whole coins) and the one-slot rule of `give`.
- The brief said to add entries to `MAJOR_ACTIONS` and `FREE_ACTIONS`. The fiscal actions are in `FISCAL_ACTIONS` (the previous run's choice). I kept that choice, so no entry in those two tables changed and the Phase 018 description check does not apply to them. Their descriptions are checked by `check_fiscal`.
- Method name collision: `deliver` already exists on `BigvilleWorld`. Renamed to `deliver_collected`, in the world, the action table, and the tests. The first version was silently shadowed by the existing method and its tests failed.
- `deliver_collected` requires the collector to stand with the creditor. The previous run's table did not, but a coin handover needs both parties present, like `pay_obligation`. I added that check to the table.
- Files outside the brief's write scope were changed: `packs/*` (pack tables, four fiscal pack files), `bigville/seeds/gen_fiscal_*.json`, `domains/generated_seeds.py`, `domains/knowledge.py`, and `tests/test_phase017_generated_seeds.py`. The first group was created by the previous run; the test change is listed above.

## Follow-ups

- Open the purses in the founding path, once there is a holder for each.
- A period-end hook that records a missed period as arrears, if the supervisor wants arrears without a visit.
- Add `pay_obligation`, `collect`, and `deliver_collected` to `MAJOR_ACTIONS` with descriptions when a backend route exists.
- Round-trip a checkpoint that contains purses and obligations.
- Resolve the Phase 015 conflict (Open questions 1).

## Supervisor review: the Phase 015 conflict

Resolved with option 1, which already existed: Phase 019's knowledge conditions accept `{"authority": ...}`
so that a renamed office keeps a valid spec. `council_tax` now requires any of the `records`, `executive`
or `deliberative` authorities (clerk, mayor, councillor in bigville; notary, reeve, councillor in the
Phase 015 fixture), and `treasury_salaries` requires `records` or `executive`. The meaning is unchanged
for the bigville pack. `tests/test_phase015_offices.py` passes again with no edit; the generated fiscal
seeds were regenerated (31 files, `--check` clean).
