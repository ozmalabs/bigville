# Package 17–18 town100 evaluation preregistration

## Status

This document registers the extended protocol before any extended evaluation
run. The evaluator and its smoke tests exist; no 480-turn arm has been run.
Package 14 has a focused green result from its owner, but the extended
evaluation remains deferred until the root integrates and confirms the full
suite and major-action boundary prerequisites. This document and a smoke run do
not establish the package claim gate.

The harness uses the actual `create_game(scenario="town100",
default_backend="simple", autonomous=True)` simulation. It does not substitute
a hand-built world or alter action admissibility.

## Registered design

The experiment is a four-cell factorial comparison of a fixed initial edible
stock shock and a modest sharing preference. It runs all cells at each of three
seeds:

| Arm | Initial resource condition | Simple-policy preference |
| --- | --- | --- |
| `baseline` | Town stocks unchanged | Default policy |
| `food_shock` | Remove 20% of each positive edible town stock before turn 1 | Default policy |
| `sharing` | Town stocks unchanged | Permit legal transfers; add +8 score to transfer affordances |
| `food_shock_sharing` | Same 20% edible-stock removal | Same conservative sharing preference |

The sharing treatment changes only which already-published legal affordances
the simple policy may prefer. It does not mint transfer affordances or bypass
the world's physical validation. The shock is an exogenous setup change, not an
actor action. No food is removed from resident inventories, containers, or
natural deposits.

| Setting | Preregistered value |
| --- | --- |
| Seeds | `305017`, `305018`, `305019` |
| Duration per cell | 480 successful shared turns (5 periods) |
| Period cadence | 96 turns |
| Conditions | All four arms at each seed (12 cells) |
| Replay | Repeat all four arms at seed `305017` (4 additional cells) |
| Per-cell ceiling | 900 seconds, including game construction |
| Total ceiling | 15,000 seconds for 16 cells |
| Compact report ceiling | 4 MB JSON |

The runner refuses more than 480 turns, unknown seeds/arms, altered cadence,
and per-cell time ceilings above 900 seconds. Smaller smoke budgets are allowed
but the report marks them as incomplete and cannot set `claim_gate_ready`.
`--no-replay` also makes the preregistered protocol incomplete.

## Measures and registered thresholds

Every turn records a causal trace grouped by work, food, and social domains.
Per selected action, the trace associates the action type and result with the
immediate resident-inventory and world-resource deltas, plus any utterances and
transactions emitted during that same action application. It also records
per-resident hunger deltas, period transitions, and per-turn invariant
outcomes. The compact JSON folds the detailed time series into five
period-level summaries by action and outcome. Its SHA-256 replay digest still
covers all per-turn measurements and causal events.

The registered per-cell acceptance criteria are:

1. At least 90% of the initial 100 residents survive.
2. At most 20% of survivors have hunger at or above 0.95.
3. Selected major-action failures are at most 5%; selected actions must have
   boolean results.
4. There are no negative town stocks or tracked resource quantities, no
   `sanity_report()` errors on any turn, and no failed conservation checks for
   transfer-like `fetch`, `transfer`, `store`, or `withdraw` actions. Those
   actions must preserve the measured item total across town stocks, resident
   inventories, containers, dropped stocks, and deposits.
5. The registered food shock is applied in both food-shock arms at every seed.
6. Each same-seed policy pair begins with identical residents and resources;
   each shock pair differs only by the registered 20% town food-stock removal.
7. Each cell completes within 900 seconds; all 16 cells complete within
   15,000 seconds.
8. All four arms replay identically at seed `305017`.

Utterance and transaction counts, hunger summaries, action-class outcomes, and
resource deltas are reported even when zero; no minimum social-interaction
count is claimed. Resource totals across a full run are diagnostic only:
metabolism, ecology, decay, eating, extraction, and recipes are legitimate
sources and sinks. Conservation is asserted only for the registered
transfer-like actions where total measured item quantity should be unchanged.

These are operational thresholds registered for this simulation, not claims
of calibration to empirical village data. A threshold failure remains a
failure; the thresholds are not to be tuned after observing the extended run.

## Commands

After the root records the full-suite and major-action boundary prerequisites,
the exact extended evaluation command from the repository root is:

```bash
PYTHONPATH=bigville python -m bigville.village_eval \
  --output bigville/docs/artifacts/package17-18-village-eval.json
```

It runs the 12 seed/arm cells and the four seed-305017 replays, and returns
nonzero if a registered runtime/outcome criterion fails. The report records
`evaluation_passed` for this protocol but always leaves `claim_gate_ready`
false: external package 14, full-suite, and major-action prerequisites are
separately owned and must be reviewed and recorded beside the JSON artifact.

One bounded smoke/practicality command (not a gate run) is:

```bash
PYTHONPATH=bigville python -m bigville.village_eval \
  --seed 305017 --arm baseline --turns 8 --output /tmp/package17-18-village-eval-practicality.json
```

Unit test command:

```bash
PYTHONPATH=bigville python -m pytest -q bigville/tests/test_package17_18_village_eval.py
```

## Risks and limits

The complete design can take several hours. A timeout is an incomplete
evaluation, not a pass. The per-action causal wrapper observes state immediately
before and after the ordinary game response handler. Digest coverage is the
reported causal trace, not private backend memory, every graph node, or all
event payloads. Action failure rate uses selected major actions as the
denominator; no proposal is not a failed action. The causal categorization is a
measurement convention based on action names and immediate state changes.

The bounded practicality smoke (seed `305017`, baseline arm, 8 turns with its
replay) took 21.305 seconds for both runs; the first run measured 10.540 seconds
and the replay took 10.639 seconds. The compact report was 18,183 bytes. Linear
extrapolation is approximately 632 seconds per 480-turn cell and 10,119 seconds
for the 16-cell protocol, within the registered 900/15,000-second ceilings.
This is only a planning estimate: period transitions and graph growth may
increase later-run cost. The full duration remains unrun.
