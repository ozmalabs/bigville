# Package 6: resident body, food and time

The isolated fixture `scenarios/simple_resident_food.json` places Ada in a small
walkable home with metabolism enabled and ecology/decay disabled. The test adds
a pantry at her cell and fills it with ten physical apples. It runs the actual
`BigvilleGame.step()` loop with a deterministic simple backend and an eight-turn
period cadence. Each captured turn includes the resident's observed hunger,
energy and inventory, available actions, selected action and reason, action
result, before/after body and food state, and any period transition.

With food present, Ada's first hunger response is `fetch`, followed by `eat`;
the cycle repeats when another period increases hunger. Fetch moves a unit from
the pantry into her inventory. Eating removes that unit and resets hunger.
Across the trace, `pantry + resident inventory + successfully eaten units = 10`,
with eight apples left in the pantry and no apple held after 18 turns. The
resident stays alive and ends at hunger zero. The same loop's rest case starts
with 20% stamina reserve and verifies the selected rest action increases
physical energy.

The no-food control advances five periods (two turns per period) and kills Ada
at hunger five under the configured starvation limit. The metabolism-off
control advances the same five periods with no food; hunger stays zero and Ada
remains alive. Both controls retain the same map, actor, backend, seed and
cadence, isolating the food supply and subsystem switch as the changed inputs.

Focused verification:

```sh
PYTHONPATH=. pytest -q tests/test_simple_body_food.py tests/test_simple_life.py
```

Result: 19 passed. These tests establish this short configured loop only; they
do not establish long-run self-sufficiency or test food spoilage, which is
explicitly disabled in the fixture to isolate metabolism.
