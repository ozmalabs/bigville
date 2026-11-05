# Package 10: storage, decay and construction

## Current checkout status (2026-11-05)

The earlier construction-failure report below was superseded. The current test
`test_simple_backend_constructs_only_with_inputs_and_labor` asserts ten
successful game turns, progress from 1 through 10, exact exhaustion of the 12
timber and 8 thatch inputs, and no build affordance with missing inputs. Current
focused result in the independent audit subset: **4 passed** as part of a
15-test run.

Reproduce the current test result with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_storage_decay_construction.py
```

## Superseded historical failure report

At an earlier checkout, construction completed after nine turns with fractional
input consumption and false intermediate action results. That report does not
match the current assertions or focused result. The original findings are
retained below as history only; rerun the command above before treating any
result as current.

---

## Original package report (historical)

Added `tests/test_simple_storage_decay_construction.py` to exercise physical
storage and construction in the simple-backend turn loop, with direct physical
controls for lock access and decay configuration.

## Results

- A resident's selected `put` action moves one unit from their inventory into a
  pantry on a real turn. Town stock + carried stock + pantry contents remain
  conserved.
- A too-small container does not publish `put`; a locked container rejects the
  attempted action without moving stock, then accepts it once the resident has
  its matching key.
- With decay enabled, grain keeps better in a granary than bread in that same
  unsuitable storage. Both quantities remain unchanged during the tested
  intervals; the condition/freshness ledger degrades. With decay disabled, the
  stored food's condition remains unchanged across periods.
- The construction control confirms that the simple actor has no `build`
  affordance while materials are absent.

## Construction gate failure (historical)

The real-turn construction test is intentionally left as a failing regression
test. A house project declares 10 labour and inputs of 12 timber plus 8 thatch.
With one labour selected per turn, the project currently completes in 9 turns;
it has spent 10.8 timber and 7.2 thatch and leaves 1.2 timber and 0.8 thatch
behind. The completion gate therefore creates a house without spending the
declared labour or all scaled inputs. Intermediate selected `build` turns also
return `False` from the game API even though progress and inputs change; only
the completion turn returns `True`.

Reproduce with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_storage_decay_construction.py
```

Historical expected result: 3 passed, 1 failed at the construction conservation
assertion. The current implementation/test has since changed; this old failure
description is not the current result. Consult the current status at the top of
this note and rerun the focused command.
