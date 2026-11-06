# Phase 026: Observable transfers replace the dead transaction record

## Summary

The `Transaction` node and `_record_transaction` are gone. Every completed physical handover of coin or
goods now writes one `Handover` fact: turn, kind (the action that moved it), good, quantity, `from` and
`to` with their endpoint kinds. The report's `economy` section counts handovers by good, by kind and by
endpoint pair, with coin as a good. It makes no claim that any handover was a sale. The report key
`transactions` is now `handovers`.

The Phase 011 fiscal moves (`pay_obligation`, `collect`, `deliver_collected`) record handovers too, as
the supervisor asked. Phase 011's tests pass unchanged.

`village_eval.py` (read only) reads `len(world._transactions)` directly from the world, not the report.
The report key rename therefore does not touch its conservation checks. To keep that harness running, the
world keeps a read-only `_transactions` whose length is the cumulative count of fiscal coin handovers.
That is the same set the old ledger counted. Its value in the registered evaluation stays 0, because the
evaluation path never creates an obligation.

## Changes

Files created or changed:

- `packs/bigville/world/handovers.json` (new): `HANDOVER_KINDS` (13 kinds with descriptions),
  `HANDOVER_ENDPOINTS` (actor, purse, container, store, merchant), `HANDOVER_LOG_LIMIT` = 1000 (APPROX,
  a design bound with no source).
- `packs/test_hamlet/world/handovers.json` (new): the same three tables, so test_hamlet keeps a clean check.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: three table entries each, bound to the new file.
- `packs/bigville/world/fiscal.json`: the `record` text of `pay_obligation` says "a Handover is recorded"
  instead of "a Transaction is recorded". Nothing else in the pack changed.
- `domains/world_affordances.py`: binds the three tables (5 added lines).
- `domains/bigville_entities.py`: `_check_handovers` (kind names, descriptions, endpoint kinds, log bound),
  called from `check_consistency`.
- `worlds/bigville_world.py`, my hunks only:
  - module: `_HandoverCount` (read-only count for village_eval).
  - `__init__`: `_handovers` and `_handover_totals` replace `_transactions`.
  - `_fill`/`_empty` handling in the actor-event pass (`_resolve_actor_events`): record `fill` and `empty`.
  - `give_newspaper`, `stock_person`, `_give_discrete_item`, `give`, `_physical_transfer`, `accept_item`.
  - fiscal: `pay_obligation`, `collect`, `deliver_collected`.
  - new block after `deliver_collected`: `_actor_endpoint`, `_party_endpoint`, `_record_handover`, and the
    `_transactions` property. `_record_transaction` is removed.
  - `deliver` (merchant), `put`, `fetch`.
  - `export_state`: key `transactions` becomes `handovers`.
  - dispatch `transfer`: passes `handover_kind="transfer"`.
  - Docstrings for `pay_obligation` and `fetch` no longer say "Transaction".
- `bigville/reporting.py`: the economy section builds `handovers` from the cumulative totals;
  `_series_metrics` reports `handovers` and `coin_handed_over` instead of `transactions` and
  `transaction_value`; `measurement.economy` reads `complete_physical_and_handover_readout`.
- `tests/test_phase026_handovers.py` (new, 15 tests).
- `tests/test_bigville_world_migrated.py` (one assertion, see below).
- `docs/phases/phase026/PHASE026_REPORT.md`, `digest_check.py`, `digest_records_on.log`,
  `digest_records_off.log` (this report and its evidence).

Other files in the working tree (README.md, bigville/game.py, bigville/runtime.py, worlds/bigville_world.py
hunks at `resident_plan_from_context` and the `"food"` flag in `_actor_options`, and the other session's
untracked files) are not touched by this phase. The files `bigville/reporting.py`, `domains/*`, and
`packs/*` had no other session changes before I started.

### Handover sites

Recorded (kind is the world primitive that moved the goods):

| Kind | Source site | Endpoints | Good |
|---|---|---|---|
| `give` | `give()`, `give_food()`, direct calls | actor -> actor | coin, stock good, or item kind |
| `transfer` | major action `transfer` (through `_physical_transfer`) | actor -> actor | same |
| `accept` | `accept_item(..., giver=)` | actor -> actor | item kind |
| `fetch` | `fetch()` | store or container -> actor | stock |
| `put` | `put()` | actor -> container | stock |
| `fill` | armed fill in `_resolve_actor_events` | store -> container | stock |
| `empty` | armed empty in `_resolve_actor_events` (amount > 0 only) | container -> store | stock |
| `stock` | `stock_person()` | store -> actor | stock |
| `give_newspaper` | `give_newspaper()` | store -> actor | newspaper (1 copy) |
| `deliver` | `deliver()` (amount > 0 only) | merchant -> store | stock |
| `pay_obligation` | `pay_obligation()` | actor or purse -> actor or purse | coin |
| `collect` | `collect()` | actor or purse -> actor (hired collector) or creditor | coin |
| `deliver_collected` | `deliver_collected()` | actor -> actor or purse | coin |

Not recorded, and why:

- `move_physical_object_as_actor`: moves ordinary objects, not coin or goods. Open question below.
- `give_note`: moves information, not a physical good.
- `give_tool`, `give_tableware`, `give_key`, founding kit: create items from nothing. They are not
  handovers.
- `give_product`, `butcher`, `harvest`, job production: production into the store.
- `treat`/`care_for` medicine: consumption from the store.
- `drop_item`, `pick_up`, `_drop_stock`, carry overflow: a party is missing (the ground).
- `buy`, `sell_to_shop`, `sell_labor`, `pay_wage`, `purchase_utterance`: retired, they return False and
  move nothing.

### Report shape

`report["economy"]["handovers"]` is:

```
{"count": N, "retained": M,
 "by_good":     {"coin": {"count", "quantity"}, "bread": {...}, ...},
 "by_kind":     {"give": {...}, "fetch": {...}, ...},
 "by_endpoint": {"actor->actor": {...}, "store->actor": {...}, ...}}
```

`count` and the bucket counts are cumulative over the run. `retained` is the number of `Handover` nodes
the town still holds (at most `HANDOVER_LOG_LIMIT`). Quantities are in each good's unit, and coin is in
whole coins. No value field exists. Each `Handover` node holds only the facts listed above.

### Replacement text for the README report example

The README's example at line 32 currently reads `print(report["economy"]["transactions"])`. Replace that
line with:

```python
print(report["economy"]["handovers"])  # physical handovers by good, kind and endpoint; not a record of sales
```

I did not edit README.md.

## Validation

Baseline before any edit (working tree with the other session's changes):
`timeout 1500 python3 -m pytest -q -p no:cacheprovider` gave 902 passed, 2 skipped, 3 failed. The three
failures were `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
`tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
and `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
Each failed with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`, which is outside
this phase.

After the change:

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0) |
| `python3 -m domains.check --pack test_hamlet` | exit 0 |
| `python3 tools/generate_seeds.py --check` | exit 0; seeds match pack 'bigville' (31 files) |
| `python3 tools/export_pack.py` | normalised 190 tables; only the new file and the edited fiscal.json changed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 917 passed, 2 skipped, 3 failed (the same three Ocelot tests as baseline) |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase026_handovers.py` | 15 passed |

Those 917 passes are 902 baseline plus 15 new tests. Phase 011's fiscal tests and the preregistered
evaluation's smoke test (`tests/test_package17_18_village_eval.py`) pass unchanged.

Simulation check (`docs/phases/phase026/digest_check.py`): seed 305017, 24 turns, arms `baseline` and
`sharing`, run once normally and once with `_record_handover` replaced by a no-op. The `measurements_digest`,
final state, action counts, and invariant counts are identical in both arms. The records do not change
the simulation. In the recorded run the conservation checks for transfer-like actions had 27 checks with
0 failures (sharing arm) and 0 failures in baseline; 100 residents alive at the end of both arms.

## Limits

- The 100-resident village was not run for a full evaluation. The 24-turn check above is the only village
  run in this phase.
- The old `Transaction` ledger never had a caller in the evaluation path. This phase keeps the evaluation's
  `transactions` count at its prior value (0 in those runs). It does not count physical handovers as
  transactions.
- The bound `HANDOVER_LOG_LIMIT = 1000` is a design choice (APPROX). Memory use for a 100-resident run is
  not measured.
- Handover nodes, not the counts, are what `export_state()` lists. The retained list holds only the newest
  1000.
- The report counts are cumulative over the run. A world restored from a checkpoint keeps its totals only
  if its persistence writes `_handover_totals`. Their persistence layer is untracked and I did not edit it.
  That layer may need to store `_handovers` and `_handover_totals`. This is a follow-up for the session
  that owns it.

## Changed existing assertions and numbers

- `tests/test_bigville_world_migrated.py::test_canonical_market_health_calendar_and_export_are_live`.
  Old: `assert not snapshot["transactions"]  # no implicit purchase transaction`. New: asserts that the
  snapshot's `handovers` are exactly `[("stock", "fish_ready", "store", seller), ("give", "fish_ready", seller, "John")]`.
  Why: the snapshot key is renamed. The scenario does stock and give fish, which are two real handovers.
  The old assertion checked an empty ledger, and that ledger no longer exists.
- `tests/test_bigville_topic_style_migrated.py` (two `assert not w._transactions`): unchanged. The
  `_transactions` compatibility count is still 0 there.
- `tests/test_phase011_fiscal.py`: unchanged. No assertion reads a Transaction node.
- No balance, price, rate, or population number changed.

## Deviations from the brief

- Write scope: the brief names `worlds/bigville_world.py`, `bigville/reporting.py`, the README example and a
  test file. I also changed `packs/bigville/world/handovers.json` (new), `packs/bigville/pack.json`,
  `packs/test_hamlet/world/handovers.json` (new), `packs/test_hamlet/pack.json`,
  `packs/bigville/world/fiscal.json` (one description string), `domains/world_affordances.py`,
  `domains/bigville_entities.py` (self-test checks), and `tests/test_bigville_world_migrated.py` (one
  assertion). Pack data and bound entities are required for the log bound and the kinds table, and the
  preamble says tunable numbers go in the pack.
- Kinds: the brief lists `give`, `transfer`, `fetch` and `put`. I added `accept`, `fill`, `empty`, `stock`,
  `give_newspaper`, `deliver`, `pay_obligation`, `collect` and `deliver_collected`, because each moves coin or
  goods between two existing endpoints. The supervisor's note named `collect`, the Phase 011 coin moves, and
  "any other existing physical coin/goods handover". Each addition is listed in the sites table above.
- The brief says "counts handovers by good and by kind of endpoint". I read "kind of endpoint" as the
  `from_kind->to_kind` pair. The report also gives counts by the action kind.
- The fiscal `_transactions` count includes `collect`, which the old ledger did not record. The count is
  still 0 in every evaluation run, because no obligation is created in the evaluation path.

## Open questions

1. `move_physical_object_as_actor` moves objects into another resident's hands (for example board-game
   pieces). It is not recorded because it is not coin or goods. Should a move to another resident count as a
   handover?
2. Should `village_eval.py`'s `transactions` count physical handovers instead? Doing so would change the
   registered social-domain tagging (`_domain`) and the `transactions_total` output, and the preregistered
   protocol says those are not to be tuned after observation. I kept the old count. The decision needs the
   supervisor's sign-off.
3. `HANDOVER_LOG_LIMIT = 1000`: is 1000 the right bound, or should the bound be per resident like
   `REFUSAL_LOG_LIMIT`?

## Follow-ups

- The untracked persistence layer (`bigville/world_persistence.py`) should store `_handovers` and
  `_handover_totals` so counts survive a checkpoint.
- `docs/SIMPLE_BOUNDARY_AUDIT.md` (lines 279-280) still says "Transaction records remain evidence". The
  docs are outside this phase's scope.
- `bigville/held_board_games.py` comment at line 522 mentions transactions in prose only.
