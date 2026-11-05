# Package 14: work, food and exchange

Fixture: `scenarios/work_food_exchange.json`; focused check:
`tests/test_simple_work_food_exchange.py`.

Run with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_work_food_exchange.py
```

## Findings

The fixture runs Farmer, Carrier, Eater, Miller and Baker through simple-backend
turns. Farmer sows, waters and harvests a crop. Carrier chooses a fetch from
town stock, physically moves to the Eater, and chooses a physical transfer.
Miller starts the existing `grind_flour` recipe twice; Baker starts
`bake_bread`. Carrier later fetches bread after recipe output is in town stock,
moves to the Eater, transfers it, and the Eater consumes it. The trace keeps
the observations, affordances, chosen actions and reasons, results, periods,
stocks and inventories for each turn.

Movement toward another resident is published only while the actor carries a
good that the resident can physically receive, and only when a route is
reachable. The option names its recipient and destination cell; it does not
transfer the good or make the destination a goal. Scenario cognition selects
the route and later transfer. Simple profiles can opt out of travel or work
while still observing those physical affordances.

The trace accounts for the crop output: one returned seed produces eight
grain; Carrier fetches and delivers one, Miller consumes six grain in two
batches and produces four flour, and one grain remains in town stock. Baker
consumes two flour and one water and produces three bread; Carrier fetches one
loaf, delivers it, and Eater eats it. Two flour and two bread remain in town
stock at the end. An unreachable direct fetch fails without changing stock.

The no-carrier control omits the carrier and processors. Harvest leaves all
eight grain units in town stock; no actor receives the crop output through
automatic allocation, and the hungry consumer cannot fetch it under the
default policy. Startup bread is an explicit finite stock moved into resident
inventories, separate from crop-derived output.

The focused package gate passes. The recipe affordances reflect physical
feasibility; scenario backend policy selects the miller and baker tasks.
