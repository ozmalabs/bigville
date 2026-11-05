# Package 9: animal care, feeding and enclosure

## Current checkout status (2026-11-05)

The animal behavior/results below the historical note were superseded by later
changes. Current tests assert that Daisy stays and does not consume the abstract
grass stock during the caregiver game-turn trace. A separate direct
`animal_tick()` test covers a hungry cow eating feed when the stock location is
made reachable. The added game-turn regression
`test_game_turn_animal_backend_eats_located_feed_and_conserves_stock` now
exercises the animal backend and physical stock change during `game.step()`;
it also checks a distant-feed control. This is store-feed consumption, not
grazing. Current focused result: **6 passed**. Run:

```sh
PYTHONPATH=. pytest -q tests/test_simple_animals.py
```

## Superseded historical report

The original package note reported `graze`, grass falling from 8 to 0, and
hunger remaining zero in the first game-turn fixture. Those observations do
not describe the current checked-in test/code and must not be used as current
acceptance evidence.

---

## Original package report (historical)

`tests/test_simple_animals.py` adds a small game-turn fixture based on the
5-by-5 resident scenario. Ada is a farmer beside Daisy, a cow in a four-cell
fenced pen. Metabolism is enabled, ecology and decay are disabled, and the
period cadence is one game turn so animal changes are attributable in the trace.
Each recorded turn includes Ada's visible context and affordances, her selected
action and result, Daisy's animal NPC choice, period, grass, milk, hunger,
alive state and position.

With eight grass, Ada's simple backend selects the available `tend_animals`
affordance on both turns and produces three milk per successful care action.
The animal NPC selects `graze`, but actual grass consumption is caused by the
period rule: grass falls from 8 to 4 to 0 and Daisy's hunger remains zero. This
distinguishes NPC cognition from automatic metabolism; the current world does
not require a cognition-driven `eat` action for feed consumption. Milk is
caregiver action output and is not deducted from grass by this model.

With no grass, the same four game turns raise hunger to 1, 2, then 3 and kill
Daisy at the configured starvation threshold; hunger remains at 3 after death.
Ada milks before the period transition on the first three turns, yielding 9
milk total, and produces no more after Daisy dies. This records the current
turn ordering: husbandry occurs before that turn's period metabolism. A policy
that avoids milking a starving animal would need to make that decision in
cognition; the physical system currently permits the action while the cow is
alive.

The barrier check starts Daisy just outside an intact pen. On a real game turn,
her NPC selects `move` and enters an allowed pen cell. An attempted physical
move back outside fails while the fence is intact; breaking one bounding fence
allows the same move. This is a physical boundary check, not a cognition claim.

Focused verification:

```sh
PYTHONPATH=. pytest -q tests/test_simple_animals.py \
  tests/test_ported_features.py tests/test_bigville_world_migrated.py
```

The checks cover configured short-run behavior, not long-term herd health,
forage regrowth or whether husbandry should depend on nutrition.

Historical result: 110 passed across the focused animal, ported-feature and
migrated-world regression tests at the time of that report. Re-run the command
above for the current test result.
