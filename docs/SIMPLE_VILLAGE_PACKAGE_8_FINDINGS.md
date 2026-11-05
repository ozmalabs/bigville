# Package 8: crop and water

## Fixture and reproduction

`scenarios/crop_water.json` sets up one spring farmer on a small walkable map,
with one wheat seed and six units of water. The test adds one physical arable
parcel at the farm cell, then runs the actual `BigvilleGame.step()` loop using
the simple backend and a task preference that only scores currently published
crop affordances. The cadence is one period per two successful game turns.

Run from `bigville/`:

```sh
python -m pytest tests/test_simple_crop_water.py -q
```

## Findings

The watered replay sows wheat, consumes the seed, publishes water when the crop
becomes thirsty, charges two units per watering, advances age on period
transitions, and publishes harvest only at maturity. The grain stock first
increases on the successful harvest turn, after age reaches four; harvest adds
eight grain and returns a seed. The backend then sows the returned seed, showing
the reserve is physical and replanting is a separate action. Two identical
seed-808 runs have identical per-turn traces, including observations,
affordances, choices, results, crop state, stocks and period number.

The no-water run has no water affordance, the wheat dies at age two after the
third period's thirst increment exceeds its wilt limit, and grain remains zero.
An out-of-season summer control publishes no wheat sow affordance and a direct
sow attempt returns no crop while preserving the seed.

One mechanic distinction surfaced: crop age increments every ecology period
while a crop is alive, even when it has not been watered. Water resets thirst
and prevents wilting; it does not itself enable an age increment. Therefore
this test demonstrates watered survival through maturity, rather than claiming
that water accelerates growth. No shared world/backend code was changed.

## Result

Focused package test passes: `2 passed`. No failing physical boundary was found
within this scenario. The trace is assembled by the test helper in memory; the
general scenario runner is unchanged.
