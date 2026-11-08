# Phase 042b report: the lamplighter's round

Base: HEAD `a50406c` (the git HEAD of `/home/matt/ozmadev/bigville` when this phase started). The shared checkout had
uncommitted work from other sessions, including `worlds/bigville_world.py`. I did not write that file. All building and
verification ran in a clean tree made by `docs/phases/phase042b/build_clean_tree.py` (`git archive HEAD` plus the hunks
in `hunks.json`).

## Summary

With `DAYNIGHT.enabled` on, the lamplighter lit no lamp in 140 ticks at HEAD (and none in 200 ticks in Phase 042).
The cause is a chain of three faults, and the fix is in the round, the world's plan dispatch, and the lamplighter's
energy rules:

1. **The plan path refused every lamp action.** `_enact_plan` in `worlds/bigville_world.py` had no branch for `light`
   or `douse`, so a backend proposal fell through to `refuse("malformed")`. A direct `major_action(..., "light")`
   works, so the lamp code itself is fine. A probe on HEAD at a lamp at night: `enact_plan(light)` gives
   `malformed`, and `major_action(light)` lights the lamp.
2. **The round started at dawn, walked the lamplighter below e_low, and was then refused `exhausted`.** The round sits
   before the ordinary rest and sleep, and it ignored energy. Each walk ran until the reserve fell under e_low (Phase
   049's refusal, kept), then rested, then walked again. The lamplighter was still far from the lamps when the day came,
   and at day no lamp needed lighting. At HEAD: 26 `exhausted` refusals in 140 ticks.
3. **Hunger yielded the round, and the simple policy seldom feeds anyone.** At hunger 1.0 or more the round yielded to
   the ordinary policy, which rarely fetched or ate. The baseline 200-turn run has 32 meals for 100 residents
   (`docs/phases/phase058/behaviour_before.json`). So a lamplighter who missed a meal never got back to the lamps.

The fix (Phase 042b):

- The lamps are reached with a pole: `light` and `douse` act on the nearest lamp within `lamp_pole_reach` (7 cells,
  APPROX) of the lamplighter. From the station, every lamp of the square is in reach. Lamp oil is drawn from the town
  store, whose cell (the market) is the **station**. The round sends him there when lamp work is due or dusk is near.
- The round's order is in `bigville/backends/lamplighter.py`: starvation guard, a meal held first, lamp work due,
  rest by day below 35 energy (night: yield to the ordinary sleep), a walk to the station that starts only at 60
  energy, and rest at the station to 70 before dusk.
- A sleeping resident is offered no lamp work (Phase 024's `asleep` and `collapsed`), so refusals are no longer
  repeated.
- Oil: `starting_oil` 40 to 60 (APPROX). Four lamps used about 12 to 15 oil a night in the run, so 40 covered about
  three nights.

Result, three game days (`run_3day/`, town100, seed 305000, simple backend, switch on, clean tree):

| Day | Sunset / sunrise (h) | Lamps: all lit, hours after sunset | Lamps: all dark, hours after sunrise | Lights applied | Douses applied |
|---|---|---|---|---|---|
| 0 | 16.55 / 7.45 | 5.45 (after 6 lights, 4 of them before dawn) | not before dusk | 6 | 2 |
| 1 | 16.58 / 7.42 | 1.42 | 2.08 | 4 | 2 |
| 2 | 16.61 / 7.39 | 1.14 | 6.86 | 4 | 2 |

The lamplighter was alive at the end of each day, ate 7 times and slept 5 times in the three days, and his lowest
energy was 5.7 (day 0), 9.1 (day 1) and 8.9 (day 2), against a collapse at about 5. His highest hunger was 1.36. Starvation
is at 4.0 (CARE `starve_limit`). The town lost no residents: 100 of 100 alive at the end. Lamp oil in the store was
16.2 at the end of day 2 (from 60).

So the round works, but the target is only partly met. Dusk lighting finished within 1.5 hours on days 1 and 2, but
5.5 hours after sunset on day 0. Dawn douse finished 2.1 hours after sunrise on day 1 and 6.9 hours on day 2.
`DAYNIGHT.enabled` stays off.

## Changes

Shared-file hunk (applied to HEAD by the builder; not written to the working tree, which has another session's edits):

| File | Anchor (HEAD text, asserted once) | Change |
|---|---|---|
| `worlds/bigville_world.py` | `_enact_plan`: the fall-through `return self._refuse("malformed")` at its end, after the comment `# The plan names no action this resident can take, or no target for it.` | Adds `if action in _dn.ACTIONS: return self.major_action(actor, action)` (2 lines). |

Files in the working tree (all clean at HEAD before this phase; written after the builder verified them):

| File | Change |
|---|---|
| `bigville/backends/lamplighter.py` | The round, rewritten (order above; constants `HUNGER_FIRST`, `STARVE_GUARD`, `ROUND_REST_ENERGY`, `WALK_ENERGY`, `DUSK_READY_ENERGY`). |
| `worlds/daynight.py` | `act`: light and douse pick the nearest lamp in pole reach; `lamp_options`: offers light only with the store open, a station walk (`due` and `purpose`), dusk and post rests, none when asleep or collapsed; `station_cell`; `post_lamplighters` (at switch-on, posts the lamplighters at the station). `_nearest_lamp` and `_lamps_in_reach` are new helpers; `station_cell` replaces the earlier `_square_center`. |
| `domains/daynight_check.py` | Checks for `lamp_pole_reach` (at least 1), `lamplighter_station_reach` (0 or more), `lamplighter_dusk_lead_hours` (between 0 and half a day), and a warning when the pole misses a lamp from the square's centre. |
| `packs/bigville/world/daynight.json` | New keys `lamp_pole_reach` 7, `lamplighter_station_reach` 3, `lamplighter_dusk_lead_hours` 6.0 (all APPROX); `starting_oil` 60.0 (APPROX, was 40.0); `_doc` updated. Canonical by `tools/export_pack.py` (identical). |
| `packs/test_hamlet/world/daynight.json` | The same new keys and `starting_oil` 60.0 (switch off). Canonical (identical). |
| `tests/test_phase042_daynight.py` | Two tests changed (below). |
| `tests/test_phase042b_lamplighter.py` | New, 16 tests (below). |

Tests changed (Phase 042's file, with the reason):

1. `test_a_light_is_offered_only_at_a_lamp_and_only_to_a_lamplighter`: the walks offered to the lamplighter were "the
   other unlit lamps, by walking". The round now lights from the pole, so the one walk offered is to the station:
   `walks == [dn.station_cell(w)]`. The intent (a light is offered only to the lamplighter, and only where a lamp can
   be lit) is kept.
2. `test_the_backend_chooses_the_lamp_round_and_the_world_does_not`: a `move` to a lamp cell without `purpose` is no
   longer a round choice (the round walks only to the station, with `purpose: station`); and "food first" now needs a
   meal held (`eat` in the affordances). With no meal, lamp work comes first (the test asserts both).

No other existing test was changed. `tests/test_phase058_persona.py` is unchanged (see Validation).

## Validation

Commands run in the clean tree `/tmp/p42b/clean_final` (built by `build_clean_tree.py`), unless noted.

| Check | Command | Result |
|---|---|---|
| Clean build | `python3 docs/phases/phase042b/build_clean_tree.py --out /tmp/p42b/clean_final` | HEAD `a50406c` archived; 7 file copies and 1 anchored hunk (log: `logs/build_clean_tree.log`) |
| Entity self-test, bigville | `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0 |
| Pack check, bigville | `python3 -m domains.check --pack bigville` | ERRORS 0; WARNINGS 0 |
| Pack check, test_hamlet | `python3 -m domains.check --pack test_hamlet` | ERRORS 0; WARNINGS 0 |
| Phase 042, 042b, 049 | `python3 -m pytest -q -p no:cacheprovider tests/test_phase042_daynight.py tests/test_phase042b_lamplighter.py tests/test_phase049_consequences.py` | 62 passed |
| Phase 058 (50 turns) | `python3 -m pytest -q -p no:cacheprovider tests/test_phase058_persona.py` | 1 failed, see below |
| 60-turn, switch off | `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label h60 --turns 60` (HEAD archive vs clean tree, earlier build) | JSON identical except `elapsed_seconds` (wall clock: 22.0 vs 21.1 s). Every other field, including the 100 per-resident digests, equal. The wrapper run `measure_daynight_60.py --mode off` (final build) equals the HEAD file, apart from the wrapper's own `mode` and `root` keys and `elapsed_seconds`. |
| Full suite | `python3 -m pytest -q -p no:cacheprovider` (clean tree, background, `full_suite.log`) | 5 failed, 2923 passed, 6 skipped, 2052 s. Four of the five also fail on the HEAD archive (below). The fifth, `tests/management/test_cast_browser.py`, is the browser flake the brief names: it passes in isolation on the clean tree. |

**Full-suite failures, and whether they predate this phase.** Run alone on the HEAD archive, these fail the same way: `tests/test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]`, `tests/test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds`, `tests/test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears` (the last asserts `heard > 0` and gets 0). Not changed here. The Phase 058 test below also fails on HEAD. The browser test passes when run alone on the clean tree.

**Phase 058 failure, pre-existing.** `test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns` fails on
the HEAD archive too, with the same assertion: `hunger_mean_by_turn` differs from `fix024`'s reference at turn 8
(0.116 against 0.1159). The sample action sequences match. The test is not changed here.

### 60 and 288 turns, switch on and off (`measure_daynight_60.py`, bigville pack, seed 305000)

| Measure | 60 turns, off | 60 turns, on | 288 turns, off | 288 turns, on |
|---|---|---|---|---|
| Deaths / alive at end | 0 / 100 | 0 / 100 | 0 / 100 | 0 / 100 |
| Mean hunger at end | 0.4452 | 0.4427 | 1.2186 | 1.2191 |
| eat | 5 | 5 | 708 | 702 |
| fetch | 0 | 0 | 711 | 726 |
| move | 3536 | 3506 | 10779 | 10747 |
| rest | 1333 | 1319 | 3948 | 3957 |
| sleep | 55 | 56 | 432 | 435 |
| none (no action) | 1056 | 1093 | 12207 | 12198 |
| light / douse (lamplighter) | 0 / 0 | 4 / 2 | 0 / 0 | 14 / 6 |
| Utterances | 285 | 284 | 1840 | 1838 |
| Lamps lit at end | - | 2 | - | 4 |

The 60-turn off row equals the HEAD run above (`behaviour_60_head.json`). Files: `behaviour_60_off.json`,
`behaviour_60_on.json`, `behaviour_288_off.json`, `behaviour_288_on.json`.

### Reproduction (HEAD archive, switch on, 140 ticks; `reproduce_trace.py`)

`logs/head_switch_on_140_ticks.log`: lamps lit at 0 of 140 ticks; 26 `exhausted` refusals; the lamplighter walks
from (2,8) at dawn, runs out of energy on the way, and is at (21,15) at 17:00 with no lamp lit. The plan
probe (above) gives `malformed` for a `light` proposal at a lamp.

## Limits

- One seed (305000), three game days for the lamp check, and 288 turns for the comparison. The simple backend only.
  A longer run was not made.
- The two late events are sleeps, from `run_3day/three_day_ticks.jsonl`. On day 0 he slept from 13:30 to 21:15 at
  energy 5.7, and the lamps were lit at 21:45. On day 2 he slept from 08:15 to 15:00, starting at energy 16 while hungry
  (hunger above 1). While hungry with no meal, the round yields to the ordinary policy, which put him to sleep, and the
  douse waited until he woke. The round does not stop a sleep that starts while he is hungry.
- Lamp oil: 60 is an APPROX seed, with no production. The run used about 44 of the 60 over three days. Recipes that
  use oil (bread and ink, per the Phase 042 report) draw the same store, and nothing in the town presses oil.
- The station is the store's cell. Oil can only be drawn there (the store's lock). The lamplighter is posted there at
  switch-on, which moves him from his founding cell (`post_lamplighters`).
- The pole reach (7 cells) is a design rule chosen so the square's four lamps can be lit from the station. It is
  not sourced. Historical lamplighters used long poles, which is the motivation (APPROX).
- The round's valuations are APPROX and in the backend, not the pack: `WALK_ENERGY` 60, `DUSK_READY_ENERGY` 70,
  `ROUND_REST_ENERGY` 35 (the simple policy's rest threshold), `STARVE_GUARD` 3.0 (below starve_limit 4.0).
- Hunger: with no meal held, a hungry lamplighter does due lamp work before food, so food waits for the lamps.
  `STARVE_GUARD` bounds this.
- The lamplighter's energy fell to 5.7 to 9.1 in each day (collapse is near 5). The round does not change the simple
  policy's energy use.
- Lamp state is still not in persistence (Phase 042 open question).
- The lamplighter's hunger, sleep and energy depend on the simple policy, which fed 32 meals to 100 residents in the
  200-turn baseline. That is the general food problem, not fixed here.

## Open questions

1. **The pole.** Accept a physical reach of 7 cells for lamps (this report), or require walking to each lamp? Walking
   needs the lamplighter near the square all day, and a home 20 cells away cannot reach it in time.
2. **Apply the hunk.** `worlds/bigville_world.py` is dirty in the shared checkout. The commit must carry the two-line
   `_enact_plan` hunk from `hunks.json`, or the lamplighter cannot light anything.
3. **Turn the switch on?** Recommendation: not yet. Over 288 turns the other residents change little (no deaths, mean hunger
   unchanged, action counts within 1 per cent except fetch, +2 per cent). The blocker is the lamplighter's timing:
   dusk and dawn can be hours late, and his energy reaches about 5. Before the switch goes on, I would want a 7-day run on
   two seeds, and a rule that keeps him at the station through the afternoon.
4. **Oil supply.** Who presses oil, and how much store oil a town should hold? The `lamplighting` labour task exists but
   nothing produces oil.
5. **Founding placement.** Should the lamplighter be drawn near the square at founding, rather than posted at switch-on?
