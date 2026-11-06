# Phase 035: Nutrition: variety, protein and taste (Tract A)

## Summary

Food now has a protein content and a taste, and the body keeps a protein store, a deficiency, the last
meal's pleasure, a specific satiety per food kind, and a mood. A loaf eaten again in the same period relieves
less (the energy of a meal is feeds x freshness x (1 - satiety)). Protein above need recovers a deficiency;
protein below need accrues one. Spice adds to a meal's pleasure, consumes a unit, and is not scaled by
satiety. Each meal moves mood toward its satisfaction, so one food sinks mood over days.

The default village keeps 0 deaths over 384 turns, but only after calibration. The first value I tried
(`monotony_rise` 0.15, cap 0.6) starved 19 residents. The chosen values (0.03, cap 0.2) starve none, and
their effect is small (mean relief per loaf falls from 0.470 to 0.454).

Three existing simple-resident tests now fail because of the monotony rule. Two check exact hunger or apple
counts, and one checks that a Farmer harvests within 28 turns. Their cause is a backend rule, explained under
Open questions. I did not change their assertions. This phase is not ready to commit until the supervisor
decides on that point.

## Changes

### New files

- `packs/bigville/world/nutrition.json`: table `NUTRITION` with its sources in `_doc`. Keys: `protein_need`
  40.0, `protein_retain` 0.5, `deficiency_rate` 0.2, `deficiency_recovery` 0.1, `monotony_rise` 0.03,
  `monotony_cap` 0.2, `monotony_retain` 0.2, `pleasure_retain` 0.5, `spice_kinds` (pepper, cinnamon, ginger),
  `spice_bonus` 0.2, `mood_rate` 0.4.
- `packs/test_hamlet/world/nutrition.json`: the same table, with `spice_kinds` empty (hamlet has no spice items).
- `tests/test_phase035_nutrition.py`: 11 tests (listed under Validation).
- `docs/phases/phase035/`: this report and the logs named under Validation.

### Pack data (edited)

- `packs/bigville/world/items.json`: every food (70 items, not the derived scraps) gains `protein` (grams per
  unit) and `taste` (0 to 1), placed after `feeds`. The file's diff is these keys only. Written by a
  one-off script in `/tmp` that reproduces the file's layout exactly. `feeds` stays the energy density
  (the brief's `energy`); there is no second energy field.
- `packs/test_hamlet/world/items.json`: `bread` gains `protein` 42.5 and `taste` 0.45.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: one manifest entry, `NUTRITION`, after
  `INTOXICATION` (four lines each). These files also carry Tract B's uncommitted edits, which I did not touch.

### Code

- `domains/world_affordances.py` (my hunks only): binds `NUTRITION`, and adds `protein(kind)`, `taste(kind)`,
  `is_spice(kind)`, `satisfaction_of_meal(kind, satiety, spice_bonus)` and `protein_balance(sc)` before
  `feed_kinds`. `meal_value` is unchanged (the world applies satiety per actor).
- `domains/bigville_entities.py` (my hunks only): `protein_balance` added to the world_affordances import;
  `_check_nutrition(...)` called after `_check_food_grading`; the function itself before
  `_check_prompt_instructions`; a `DEFICIT protein` issue in the balance section, before the break-even loop.
- `worlds/bigville_world.py` (my hunks only): `eat(..., spiced=False)` (docstring updated); `pre_satiety`
  scales the energy of a meal, and `_nutrition_meal` runs after `_record_meal`; a new section
  "nutrition (Phase 035)" with `_satiety_level`, `_satiety_node` (a `Satiety` node per food kind, linked from
  the Body by `has_satiety`), `_take_spice`, `_nutrition_meal`, `_nutrition_period`, `nutrition`; `meal_value`
  now multiplies by (1 - satiety); `_resolve_period_effects` calls `_nutrition_period` for each living
  resident, before the starvation check; `add_actor`'s Body node gains `protein_store`, `deficiency`,
  `meal_pleasure`, `monotony`; `body_state` gains those four keys; the eat option gains `monotony` and
  `meal_pleasure`; the `_record_meal` docstring is corrected.
- `bigville/reporting.py` (my hunks only): `nutrition()` (residents short of protein, mean deficiency, mean
  protein store, mean mood), and a `"nutrition"` key in `report()`.

### Backend files, reviewed and unchanged

- `bigville/backends/cheap.py`: unchanged. Eat options already score by `meal_value`, and `meal_value` now
  carries satiety, so the simple backend sees variety without a new rule. See Open questions for the
  consequence.
- `bigville/backends/psi_can.py`, `bigville/backends/prompts.py`: unchanged. `PromptBuilder` reads
  `context.observations`, which `bigville/game.py` builds from named keys. The nutrition read-offs are not in
  that list, and `game.py` is outside this write scope.

### Tests

- `tests/test_phase035_nutrition.py` (new, 11 tests).
- `tests/test_phase027_food_value.py::test_a_single_apple_relieves_part_of_a_period_and_two_apples_a_loaf`:
  old `assert _hunger(two) == _hunger(loaf) == 0.0`. New: `assert _hunger(loaf) == 0.0`, and
  `assert _hunger(two) == pytest.approx(1.0 - 0.5 - 0.5 * (1.0 - monotony_rise))`. Reason: the second apple of
  one kind in a period relieves less (specific satiety), so two apples no longer equal a loaf. The value is
  about 0.015 at `monotony_rise` 0.03. Intent kept: a fresh apple relieves 0.5, and the test is exact.

## Design and data

- **Codebook.** `protein` = g/100 g x 10 x unit weight (kg). The g/100 g values are APPROX, recalled from
  typical composition tables (McCance and Widdowson, The Composition of Foods, 6th ed., 2002). I did not check
  them row by row against the table. `taste` is an APPROX 0-1 judgement per food. Examples: bread 8.5 g/100 g,
  taste 0.45, so a loaf (0.5 kg) has 42.5 g. Cheese has 300 g per unit, because a cheese unit weighs 1.2 kg.
- **Protein need.** 40 g per resident per period. WHO/FAO/UNU (2007) safe level 0.66 g/kg/day for adults
  (WHO Technical Report Series 935) times a 60 kg reference adult (APPROX). It is flat, so children are
  overstated; that makes the balance check conservative.
- **Store and deficiency.** At period close the store is read: below need, deficiency rises by
  `deficiency_rate` x the shortfall share; otherwise it falls by `deficiency_recovery`. Then the store keeps
  `protein_retain` of itself. Steady state for one loaf a day is about 85 g, so the founding bread diet
  never accrues deficiency. Deficiency is a read-off only (Mind rule, seed nu_psych). It changes no world
  physics and cannot cause harm.
- **Specific satiety.** Each meal of a kind raises that kind's satiety by `monotony_rise`, up to
  `monotony_cap`. The satiety fades by `monotony_retain` per period. Energy = feeds x freshness x (1 - satiety)
  (Rolls, Rolls, Rowe and Sweeney, 1981, Physiology and Behavior, sensory-specific satiety). The rise and cap
  are APPROX. They are small because one unit is a whole day's loaf, and the founding town eats about 2.5
  loaves a day (see Validation).
- **Pleasure and spice.** `meal_pleasure` = taste + spice bonus (clipped to 1). A spiced meal takes the bonus
  only if a spice unit is held, and consumes one unit. The bonus is not scaled by satiety, so a monotonous
  meal, spiced, still feels better. The bonus is 0.2 (APPROX).
- **Mood.** `satisfaction_of_meal` = taste x (1 - satiety) + spice bonus, clipped to 0-1. Mood moves by
  (satisfaction - mood) x 0.4 per meal (seed af_meal_mood; 0.4 is the seed's adaptation rate). Mood feeds no
  decision in the village: the only `mood` in the backends is a personality `mood_bias`, not the body's value.
- **Balance.** `protein_balance(BALANCE_SCENARIO)` gives supply = residents x food_per_resident x protein of
  one loaf, and need = residents x protein_need. The founding figures are 42.5 g supplied against 40 g needed,
  so the info line reports them. A DEFICIT issue appears only when supply is under need. The model reads
  the staple only, not the whole harvest. I kept protein out of the `flows` table: at 1.06 cover, the existing
  check would print a TIGHT warning and break the 0-warning rule.

## Validation

Commands run from `/home/matt/ozmadev/bigville`. Logs are in `docs/phases/phase035/`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (`selftest.log`) | exit 0. ERRORS (0), WARNINGS (0). INFO: protein, the founding staple gives 42.5 g per resident per period against 40.0 g |
| `python3 -m domains.check --pack test_hamlet` (`hamlet_check.log`) | exit 0 |
| `python3 tools/generate_seeds.py --check` (`generate_seeds_check.log`) | exit 0, "match pack 'bigville' (31 files)" |
| Pack bytes: `export_pack.py --pack bigville` and `--pack test_hamlet` into `/tmp`, diffed | items.json, nutrition.json and pack.json identical for both packs. The live packs were not exported into |
| `pytest tests/test_phase013a_packs.py` | 8 passed |
| `python3 bigville/game/assets/generate_assets.py` and `tools/build_style_assets.py`, run in a copy of the tree | regenerated assets are byte-identical to the live ones, so no asset file changes |
| `pytest tests/test_phase035_nutrition.py tests/test_phase027_food_value.py` | 24 passed (11 new, 13 existing) |
| `pytest tests/test_phase034_intoxication.py tests/test_phase037_health_routes.py tests/test_fix024_starvation.py tests/test_phase058_persona.py tests/test_phase054_actionable.py tests/test_phase054_llm_prompt.py` | all passed in the targeted run |
| Death probe, town of 100, simple backend, 384 turns, at baseline (session start, working tree) | 0 deaths. 13m24s |
| Death probe, first setting (`monotony_rise` 0.15, cap 0.6) | 19 starvation deaths, first at turn 287 |
| Death probe, second setting (0.05, cap 0.3) | 1 starvation death, Ottoline Rundle, at turn 383 |
| Death probe, final setting (0.03, cap 0.2) (`death_probe_after_384.log`) | 0 deaths |
| Full suite on the live tree, after the final setting (`full_suite.log`) | 10 failed, 1710 passed, 3 skipped (1250 s). See below |
| Full suite on an untouched copy of the tree, before my edits (`full_suite_baseline_copy.log`) | 4 failed, 1699 passed, 9 skipped |

### Calibration and the village

Measured with a diagnostic that logs every eat (`diag_baseline_384.log`, `diag_after_384.log`):

| Setting | Deaths (384 turns) | Mean relief per loaf | Peak hunger, any resident | Eat events |
|---|---|---|---|---|
| No monotony (baseline) | 0 | 0.470 | 3.78 | 757 |
| 0.15, cap 0.6 (300 turns) | 9 by turn 288, 19 at turn 384 (first at 287) | 0.369 | 3.96 at turn 300 | 752 at turn 300 |
| 0.05, cap 0.3 (300 turns, then probe) | 1 (turn 383, probe) | 0.448 | 3.74 at turn 240 | 756 at turn 300 |
| **0.03, cap 0.2 (final)** | **0** | **0.454** | **3.78** | **759** |
| 0.02, cap 0.2 (tried, not chosen) | 0 | 0.460 | 3.76 | 757 |

The baseline peak hunger (3.78 at turn 384, and 3.74 at turn 240) sits close to the starvation limit of 4.0
(`CARE.starve_limit`). The founding diet has little margin, so the monotony rule has to stay small. A
run where it exceeds 4 would kill a resident.

### Behaviour checks that held

- Bread three times in a period: relief 1.00, 0.97, 0.94; monotony read-off 0.09. A varied diet (bread, cheese,
  apple, honey) gives each food its full feeds.
- Protein: apples 3 a day for six days raise deficiency to 1.0 (0.19, 0.37, 0.54, 0.72, 0.89, 1.0). Cheese
  a day for four days lowers it to 0.6.
- Spice: a spiced loaf after three plain ones has pleasure 0.65 (taste 0.45 + 0.2), consumes one pepper, and
  leaves mood above the unspiced loaf. Spice with no unit adds nothing.
- Mood: bread three times a day for eight days: mood 0.50 falls to 0.42 and holds. Cheese, stew and honey
  once a day: mood rises to 0.76.

## Limits

- Every constant except the self-test figures is APPROX. The protein g/100 g and taste values are judgements
  from memory of typical tables, not checked against the source.
- The village run is the 384-turn probe with simple backends only. There is no LLM run.
- `protein_need` is flat for all ages.
- The monotony rule is calibrated to one founding diet (bread). Other diets are not measured.
- Deficiency has no physical effect in the world, so it cannot cause death. Its only effect is the read-off
  for the backend's mind rule, which no backend uses yet.
- A saved game (checkpoint) from before this phase has no nutrition attributes on its Body nodes. Every
  reader uses `.get` with a default of zero, so it loads, but the satiety nodes are not restored from it.
  I did not test checkpoint round-trips for `Satiety` nodes; Tract B's persistence modules are not in my scope.

## Open questions and decisions for the supervisor

1. **Three existing tests fail because of monotony, and the cause is a backend rule.** Verbatim failures:
   - `tests/test_simple_body_food.py:74`: `assert world.contents("home_pantry", "apple") == 7`, got `6.0`.
   - `tests/test_simple_life.py:27`: `assert world.hunger("Ada") == 0.75`, got `0.7545`.
   - `tests/test_simple_work_food_exchange.py:194`: `assert any(selected(row, "Farmer").get("action") == "harvest" ...)`,
     got `False`.

   Cause: `cheap.py` line 229 sets `fed_first = hunger > 0 and any(eat option)`, so any hunger above zero makes
   the resident eat again. Repeated bread leaves a small residue (0.006 to 0.03), so the resident eats the
   stock down, and the Farmer in the 28-turn trace never reaches the harvest (`farmer_trace_baseline.txt` and
   `farmer_trace_after.txt`). The village is not hurt (the probe shows 0 deaths, and eat events are 759 against
   757). Options:
   - (a) Accept the new behaviour and update the three assertions, listing each. This is deliberate
     monotony's effect, but it is one a supervisor should approve.
   - (b) Change `cheap.py`'s eat trigger from `hunger > 0` to a small floor. That is a backend change, and
     `cheap.py` is a shared file.
   - (c) Floor residues in the world (a meal that leaves under a set hunger leaves none). This does not
     remove the effect for repeat eating, since the residue grows with each repeat.
   I have not edited these three tests. I recommend (a) or (b) and will apply the decision.

2. **Spice is not chosen by any backend.** `eat(..., spiced=True)` is a Python keyword. The eat action's
   proposal schema is unchanged, so no snapshot changed. A backend that spices meals needs a proposal field,
   which is a protocol change (`bigville/backends/protocol.py`).
3. **The nutrition read-offs do not reach `PromptBuilder`.** `bigville/game.py` builds observations from named
   keys. Adding `deficiency`, `monotony` and `meal_pleasure` to that list is a one-line change in `game.py`,
   which is outside this write scope and is Tract B's file.
4. **Two satisfaction models.** `domains/population.py` already has `meal_satisfaction(base_liking,
   recent_repeats, neophobia)`, a count-based model with per-person neophobia, used by its diet simulation. The
   world's `satisfaction_of_meal` uses the body's continuous satiety. I kept both, under different names, and
   did not unify them.

## Follow-ups

- Decide Open question 1. Then update or keep the three tests, and rerun the probe and the suite.
- If a village diet other than bread is tuned, rerun the probe with `monotony_rise` as the only changed number.

## Full-suite failures (live tree)

- Three are the known Ocelot import failures. They are environmental: the skip check in
  `tests/test_bigville_ocelot_communication.py` looks for a sibling `../ocelot` folder. That folder exists beside
  the live checkout, so the tests run and fail with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
  The untouched copy under `/tmp` has no sibling folder, so these tests skip there. Phases 034 and 037 recorded the same failures.
- Four are `tests/test_phase057_tui.py` over-HTTP tests (`last_responses` is `None`, `contest_log` is empty,
  and a bad reply returns 200). They also fail in the untouched copy, so they predate this phase. They sit in
  Tract B's in-flight work.
- Three are the new failures in Open question 1.

## Git state

- Start: `git status --short` (32 entries; recorded at session start). End: 41 entries, including this phase's
  new files.
- Changed in this phase, by file: `packs/bigville/world/items.json`, `packs/test_hamlet/world/items.json`,
  `domains/world_affordances.py`, `domains/bigville_entities.py`, `worlds/bigville_world.py`,
  `bigville/reporting.py`, `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`,
  `tests/test_phase027_food_value.py`. Created: `packs/bigville/world/nutrition.json`,
  `packs/test_hamlet/world/nutrition.json`, `tests/test_phase035_nutrition.py`, `docs/phases/phase035/`.
- Shared files carry other sessions' hunks as well. The hunks listed above are mine.
- Nothing staged or committed.

## Supervisor decision (Open question 1)

- Option (b), an eat floor in `cheap.py` (`EAT_HUNGER_FLOOR` 0.05), was tried and rejected: with it the 384-turn
  probe starved 19 residents (first at turn 287). The founding village runs close to the starvation limit (peak
  hunger 3.78 of 4.0), and the simple residents' early eating is what keeps them alive. The floor was removed and
  `cheap.py` is unchanged by this phase.
- Instead, the energy effect of specific satiety is behind a new physical subsystem switch, `monotony`, default off.
  With it off a repeated food keeps its full energy; satiety is still tracked and still lowers the meal's pleasure
  and the mood, and protein, deficiency, taste and spice work as described. With it on, the rule is as calibrated
  above (rise 0.03, cap 0.2).
- Consequences: the three simple-resident tests pass unchanged; the Phase 027 two-apples test is back to its
  committed assertion (the edit listed above is reverted); `tests/test_simple_life.py` and
  `tests/test_scenario_runner.py` gain `"monotony": False` in their expected switch dicts; the Phase 035 tests turn
  the switch on, and one new test checks the off behaviour. The 384-turn probe with the switch off: 0 deaths.
