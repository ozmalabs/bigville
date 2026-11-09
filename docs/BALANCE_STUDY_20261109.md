# Bigville default town: balance study

Scope: `create_game(scenario="town100", default_backend="simple", autonomous=True, ticks_per_period="world", affordance_mode="menu", llm_log=False)`, HEAD 99c29b5 (archive copy in `/tmp/balance/tree`; the real repo was not touched). One `g.step()` = one 15-minute tick, 96 ticks = 1 day = 1 world "period". Day indices below are 0-based and refer to the day that just ended (day 0 = first 96 ticks).
Seeds: baseline 305000, 305001, 305002; levers 305000 and 305001 (a few single-seed runs are marked). All levers are in-process overrides in `/tmp/balance/harness.py`; the archive tree was not edited; three throw-away copies (tree_p, tree_c, tree_r) carry one patch each for the test-impact check in section 8. The real repo changed while I worked (not by me; I never wrote to it): HEAD moved from 99c29b5 to 683bb71 ("Engine speedups: incremental action-mode rule sweeps") and files under bigville/management/ are modified. All numbers are for 99c29b5; I did not re-run on 683bb71, so if that commit alters rule-sweep timing the exact counts could differ.

---------------------------------------------------------------------------------------------------

## 0. Verdict

**The default simulation is not balanced, and it is not close.** Against your four tests:

| test | result (baseline, 3 seeds) |
|---|---|
| survives >= 14 days at steady state | No. Extinct on day index 5-6 (all 100 dead). First starvation death day index 3-4. 420 / 425 / 434 person-days out of 700 in a 7-day window. |
| production >= consumption | No. **Zero** food produced in 5-6 days: 0 work completions, 0 harvest/water/sow actions, the 85 starting crops are dead by day 2. The only food is the starting 760-loaf store, whose feeding value falls 25 points a day. |
| residents not chronically below the rest threshold (35) | No. 41-57 % are below 35 at the end of every day; 63-74 % at 17:00 on day 0 (mean 33.7). |
| energy mostly spent on useful work | No. Of the energy spent each day (about 215-330 points per resident), **99.9 % is walking**; work is 0.00-0.27 points. About half of the walking energy buys no movement at all (section 3b). |

No lever I tested, alone or stacked, reaches a steady state. The best stack (walking cost x0.25, no energy charge on wait ticks, rest threshold 70, stay-on-job, crops tolerate 8 dry days, no bread decay) keeps all 100 alive to day index 5 and collapses on day 6-7 (676 / 667 person-days in the first 7 days against 426 for the baseline; one survivor left after day 9). Finished food made after day 0 in that run (bread, oatcake, pottage) is 3-15 units a day, against about 100 meals a day needed.

The cause is a chain, not one number: (1) residents cannot afford to reach the places where work happens (the walking energy model: about 8 energy per cell at best, 15-23 per cell in practice, a 100-point reserve, commutes of 20-60 cells), (2) the simple policy abandons or never starts work, (3) the starting economy is a three-day perishable buffer with a two-day crop watering deadline, and (4) 59 of 100 residents hold a "spare" labourer job with no duty. Stamina scalars, the stamina distribution and the job draw are not the binding constraints.

---------------------------------------------------------------------------------------------------

## 1. What I verified from your list (and what I corrected)

| your statement | verified? | measured |
|---|---|---|
| BALANCE says food supply 3.58x demand; stamina line counts only declared recipe cost, 0.02/resident/period | Yes | `python3 domains/bigville_entities.py` prints 358.0 vs 100.0, ratio 3.58, "stamina ... 0.020 stamina per resident per period". Measured effort spent per resident-day is 2.26-3.21 reserve (226-321 energy points), i.e. **110-160x** the 0.02 line. Walking is not modelled in BALANCE at all. |
| Menu mode, seed 305000: 15 work starts on day 0 then 0; moves 4119/2481/2379/2709; rests 1844/1218/886/1516; store 760 -> 542, 49, 0; fetch 218/493, eat 210/490 | Yes, exact | reproduced to the unit by the instrumented harness (the harness is observation-only). Other seeds: 11 and 13 work starts on day 0, then 0. |
| hunger >= 1 for all 100 by end of day 0 | Yes | 100/100/100 |
| mean energy at 17:00 only 25-35, p10 11-16 | Yes for day 0 only | day 0: mean 33.7 (32.9-34.5), median 25.9, p10 15.7 (11.2-19.9). Days 1-3: mean 43-50, p10 14-18. |
| about half the town below 35 at the end of each day | Yes | 0.49 / 0.51 / 0.44 / 0.51 for days 0-3 (range 0.41-0.57) |
| starvation begins day 3 (99 alive), whole town dead by day 5-6 "in the lazy-mode run" | Yes, and it is the same in **menu** mode | alive at end of day 3: 99/100/100; day 4: 21/24/34; extinct day 5/6/5 |
| sta_base exactly 1.0, sd 0 | Yes | all 100 bodies. `domains/population.py` has `PHYSIQUE` (mean 1.0, sd 0.2, shared_sd 0.12, floor 0.4) and `draw_physique()`, but **nothing calls it** (grep: only the definition). |
| 59 labourers, about 10 in food production | Yes | 59 labourer, 6 farmer, 2 farm_labourer, 1 animal_keeper, 1 dairymaid, 1 miller, 1 baker, 2 fisher, 1 butcher, 1 fishmonger = 16 food-related incl. processors |
| "walking 12 cells cost 10 energy (~0.83 per cell)" | **No, off by a factor of 10** | One walking step costs 0.1 x terrain multiplier (0.65-0.9) reserve = **6.5-9 energy points**; 12 cells empty the whole 100-point reserve. The pooled cost per cell actually moved is 8.3 (full speed), 12 (reserve < 70), 22-29 (reserve < 40) points (section 3b). Day totals: 15.5, 22.7, 19.3 points per cell moved on days 0, 1, 2. |
| one rest = +10; idle costs nothing; sleep +0.03/tick | Yes | rest +10; no Effort is minted for idle; sleep +3 points/tick. A rest tick restores 3.3x what a sleep tick does. |
| lamplighter = first adult in founding order; zero lamplighters in the cast; dusk lit median ~9.1 h after sunset; due_floor 0.9 lit nights 1-2 within 1.2 h | Yes | seed 305000 nights 0-3: 8.9 / 9.9 / 8.1 / 9.1 h. With due_floor 0.9: 8.9 / **1.2 / 1.1** / 7.6 (nights 0 and 3 are still late). |

---------------------------------------------------------------------------------------------------

## 2. Mechanisms found in the code (all read, then confirmed by counters)

1. **Time and food units.** One period = one day (96 ticks). Hunger rises by 1.0 per period (`_resolve_period_effects`) plus `HUNGER_PER_STAMINA` 0.2 per full reserve of effort spent (`_resolve_actor_events`). Effort adds 0.64 / 0.52 / 0.45 hunger per resident on days 0 / 1 / 2, which is 39 / 34 / 31 % of the daily hunger.
2. **The starting food is perishable.** 800 bread in `STARTING_STOCK` (760 in the town store, the rest in households). Bread loses 0.25 of its condition per period (class `perishable`). A loaf feeds `feeds x condition`: 0.75 on day 1, 0.50 on day 2, 0.25 on day 3, 0 after. Measured hunger relieved per eat: 0.75 (day 1) and 0.50 (day 2). So 490 eats on day 2 relieve only 245 hunger. This is why the store drains at "several meals per person" (about 5 eats per resident on day 2): the loaves are worth half as much each, not because residents gorge.
3. **Crops die unless watered.** 85 crops exist at the start; `CROPS.wilt` = 2 and thirst rises 1 per period, so unwatered crops are dead at the start of day 2 (baseline probe: 85 alive at the end of days 0 and 1, 0 at the end of days 2 and 3). Wheat needs `grow_periods` = 4 to harvest.
4. **Walking costs energy on waiting ticks.** `BigvilleWorld.move_actor` (`worlds/bigville_world.py` about line 2690-2740) builds the walking `Effort` (cost 0.1 x `move_energy` x terrain multiplier, then x (1 + hunger/4) in `_resolve_actor_events`) **before** it checks `carry_move_cooldown`. A tired walker's step interval is x1.5 (reserve 40-70), x3 (15-40), x6 (< 15), so the intervening ticks are "waiting ticks" that move nobody but still pay a full step. Measured: only **45-52 % of walking attempts move a cell** (pooled 50 / 47 / 50 % on days 0-2). I could not find any comment or test that says waiting ticks should cost energy (the tests pin distance per turn, not energy per waiting tick).
5. **The band edges sit exactly where the policy parks its walkers.** Band edges are 70 / 40 / 15 energy (speed x1, x2/3, x1/3, x1/6). The simple policy rests only below `rest_energy_threshold` = 35 (and then offers only `rest`), and a continuing walk is interrupted at 35. So a walker lives at 35-45 energy, mostly in the x3-interval band (15-40), where one cell costs 21-29 points. Below 15 a plan-path move is refused as `exhausted` (775 / 568 / 457 / 682 refusals on days 0-3, 16 % of move attempts on day 0).
6. **Capacity (`sta_base`) does not scale energy.** `energy = stamina_reserve x 100`; reserve starts at 1.0 and is clamped to `effective_stamina = (sta_base + sta_train) x health`; sleep refills to `min(rest_cap = 1.0, capacity)`, an awake rest to `capacity`; band edges are fractions of capacity; walking cost is absolute. So raising `sta_base` only raises the band edges (a x1.5 body is "tired" at a higher reserve) and the awake-rest ceiling. Walking already trains stamina: `sta_train` is +0.12 after day 0 and +0.18 after day 1 (effective stamina 1.12-1.16), which tightens the band edges slightly for everyone.
7. **Jobs are drawn without regard to capability.** `generate_cast100` takes staffing from `seed_jobs(100)`, which is a deterministic function of the job load table (no seed, no capability). People are indexed in cast order and each index carries its own age, household and home. `role_identity` is then *drawn from the job's FOUNDING_JOBS row* (e.g. baker 0.88, labourer 0.22), so it is a result of the job, not an input to it. The 59 labourers are the "spare" job (no duties). The `lamplighter` row exists in FOUNDING_JOBS but `JOBS` gives it no load, so `seed_jobs` never assigns it.
8. **Geometry.** Home -> workplace Manhattan distance: farm roles 51 cells on average (32-67), other food roles 35 (20-59), other roles 32, labourers 29 (their workplace is the town store itself). Home -> store: 28.6 cells on average (18-40). A fresh 100-point reserve is about 12 cells at best.

---------------------------------------------------------------------------------------------------

## 3. Part 1: diagnosis of the baseline (DAYNIGHT off, 3 seeds)

I ran 14 days; every seed is extinct by day index 5-6, so only days 0-5 carry data. Values are mean [min-max] over the three seeds.

### 3a. Per-day table

| day | alive (3 seeds) | cum. deaths | hunger mean | hunger p10 / p90 | store loaves | held | bread condition | meals eaten | hunger relieved | fetches | work starts | jobs completed | food produced |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 100/100/100 | 0/0/0 | 1.64 [1.63-1.64] | 1.48 [1.48-1.48] / 1.79 [1.78-1.80] | 760 [760-760] | 33 [32-34] | 0.75 [0.75-0.75] | 7 [6-8] | 7 [6-8] | 0 [0-0] | 13 [11-15] | 0/0/0 | 0 |
| 1 | 100/100/100 | 0/0/0 | 1.89 [1.85-1.94] | 1.07 [1.05-1.08] / 3.31 [3.30-3.31] | 547 [542-553] | 40 [35-46] | 0.50 [0.50-0.50] | 205 [199-210] | 154 [149-158] | 213 [207-218] | 0 [0-0] | 0/0/0 | 0 |
| 2 | 100/100/100 | 0/0/0 | 1.20 [1.19-1.22] | 1.00 [1.00-1.00] / 1.45 [1.38-1.56] | 48 [42-54] | 44 [43-44] | 0.25 [0.25-0.25] | 496 [490-507] | 248 [245-254] | 499 [493-505] | 0 [0-0] | 0/0/0 | 0 |
| 3 | 99/100/100 | 1/0/0 | 2.58 [2.53-2.62] | 2.06 [2.00-2.16] / 3.04 [2.98-3.07] | 0 [0-0] | 25 [22-30] | 1.00 [1.00-1.00] | 67 [62-76] | 17 [16-19] | 48 [42-54] | 0 [0-0] | 0/0/0 | 0 |
| 4 | 21/24/34 | 79/76/66 | 3.63 [3.60-3.66] | 3.09 [3.03-3.16] / 3.97 [3.96-3.97] | 0 [0-0] | 25 [22-30] | 1.00 [1.00-1.00] | 0 [0-0] | 0 [0-0] | 0 [0-0] | 0 [0-0] | 0/0/0 | 0 |
| 5 | 0/1/0 | 100/99/100 | 3.91 | 3.91 / 3.91 | 0 [0-0] | 7 [0-22] | 1.00 [1.00-1.00] | 0 [0-0] | 0 [0-0] | 0 [0-0] | 0 [0-0] | 0/0/0 | 0 |
| 6 | 0/0/0 | 100/100/100 | - | - / - | 0 [0-0] | 0 [0-0] | 1.00 | 0 [0-0] | 0 [0-0] | 0 [0-0] | 0 [0-0] | None/0/None | 0 |

(Bread condition 1.00 on days 3+ means the pile is empty. Deaths are all starvation. "Food produced" is 0: no recipe job ever completed and no harvest happened.) Energy at 17:00 and share below 35: day 0 33.7 / 68 %, day 1 42.9 / 51 %, day 2 49.8 / 28 %, day 3 46.5 / 49 %.

Production by recipe: work starts on day 0 are 15 / 11 / 13 (seed 305000 / 1 / 2): `make_gruel` x7 (six of them farmers), `brew_ale` x3 (innkeepers and a labourer), `grind_flour` x3, `burn_charcoal` x2. **Completed: 0 in all seeds**; at the end of every day 15 / 11 / 13 jobs exist and every one is paused.

### 3b. Daily energy budget by class (days 0-2, 3 seeds pooled)

Classes: farm = farmer + farm_labourer (8 residents), other_food = animal_keeper, dairymaid, miller, baker, fisher x2, butcher, fishmonger (8), labourer (59), other (25). Energy figures are points of the 0-100 scale per resident.

| day | class | walk % ticks | rest % | sleep % | work % | eat+fetch % | idle % | cells/res | walk energy/res | work energy/res | rest recovered/res | sleep recovered/res | energy per cell moved | walk attempts that moved |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | farm(farmer+farm_labourer) | 51 | 19 | 28 | 0.8 | 0.0 | 0.8 | 21.2 | 322 | 0.00 | 185 | 78 | 15.2 | 51% |
| 0 | other_food | 50 | 18 | 30 | 0.2 | 1.0 | 0.7 | 20.8 | 313 | 0.00 | 174 | 84 | 15.1 | 52% |
| 0 | labourer | 52 | 20 | 28 | 0.0 | 0.0 | 0.6 | 20.7 | 324 | 0.03 | 192 | 77 | 15.6 | 50% |
| 0 | other | 50 | 19 | 30 | 0.2 | 0.0 | 0.7 | 20.4 | 314 | 0.27 | 182 | 83 | 15.4 | 50% |
| 1 | farm(farmer+farm_labourer) | 34 | 14 | 46 | 0.0 | 4.4 | 1.6 | 12.2 | 269 | 0.00 | 132 | 130 | 22.1 | 46% |
| 1 | other_food | 32 | 14 | 47 | 0.0 | 5.6 | 1.8 | 11.8 | 263 | 0.00 | 131 | 131 | 22.4 | 46% |
| 1 | labourer | 31 | 13 | 50 | 0.0 | 4.2 | 1.9 | 11.7 | 266 | 0.00 | 121 | 140 | 22.7 | 47% |
| 1 | other | 33 | 13 | 48 | 0.0 | 4.4 | 1.8 | 11.9 | 269 | 0.00 | 126 | 135 | 22.7 | 47% |
| 2 | farm(farmer+farm_labourer) | 29 | 12 | 49 | 0.0 | 8.0 | 1.6 | 10.2 | 234 | 0.00 | 113 | 138 | 22.8 | 45% |
| 2 | other_food | 29 | 8 | 51 | 0.0 | 9.5 | 1.7 | 11.8 | 222 | 0.00 | 80 | 144 | 18.8 | 49% |
| 2 | labourer | 28 | 8 | 51 | 0.0 | 11.0 | 1.8 | 11.3 | 217 | 0.00 | 78 | 144 | 19.2 | 50% |
| 2 | other | 27 | 7 | 53 | 0.0 | 9.9 | 1.8 | 11.3 | 213 | 0.00 | 69 | 151 | 18.8 | 51% |

Walking by exhaustion band (3 seeds pooled):

| day | band (reserve) | walk attempts | cells moved | energy per attempt | energy per cell moved | cells per attempt |
|---|---|---|---|---|---|---|
| 0 | 0 (>= 70) | 2026 | 1832 | 7.5 | 8.3 | 0.90 |
| 0 | 1 (40-70) | 2359 | 1477 | 7.6 | 12.2 | 0.63 |
| 0 | 2 (15-40) | 7997 | 2899 | 7.9 | 21.7 | 0.36 |
| 1 | 0 | 1182 | 648 | 11.0 | 20.0 | 0.55 |
| 1 | 1 | 1636 | 1154 | 10.0 | 14.2 | 0.71 |
| 1 | 2 | 4692 | 1731 | 10.8 | 29.3 | 0.37 |
| 2 | 0 | 1054 | 590 | 10.4 | 18.5 | 0.56 |
| 2 | 1 | 1947 | 1420 | 8.9 | 12.3 | 0.73 |
| 2 | 2 | 3769 | 1374 | 9.8 | 27.0 | 0.36 |

Energy per attempt is higher on days 1-2 because the effort cost is multiplied by (1 + hunger/4) and everyone is hungry.

Answers:
* **Is the day's energy spent on useful work?** No. Walking is 99.9 % of effort energy: 313-324 points per resident on day 0 versus 0.00-0.27 for work; 213-269 on days 1-2. Work is under 1 % of ticks on day 0 and 0.0 % afterwards.
* **Dominant sink.** Walking, and within walking the waiting-tick charge: about half of all walking energy buys no movement. The remaining energy goes to recovering it: rest ticks are 18-20 % of ticks on day 0 and rest restores 174-192 points per resident; sleep restores 77-84 on day 0 and 130-151 on days 1-2. Sleep is 28-30 % of ticks on day 0, 46-53 % later.
* **Cells walked.** 21 cells per resident on day 0, 10-12 on days 1-2. The mean farmer commute is 51 cells. At end of days 0 / 1 / 2 / 3 the six farmers are 36 / 33 / 35 / 44 cells from their fields (farm roles start 51 cells away on average); the miller 14 / 12 / 9 / 9 from the mill, the baker 25 / 17 / 16 / 14 from the bakery.
* **Residents never reach their workplaces.** Over the whole run, residents who ever stood on their own workplace cell: farmers 0/6, farm_labourers 0/2, animal_keeper 0/1, dairymaid 0/1, miller 0/1, baker 0/1, fishers 0/2, fishmonger 0/1, butcher 1/1, labourers 59/59 (their workplace is the store; first arrivals at tick 118-121, i.e. day 1). Same in all three seeds.

### 3c. Why work stops after day 0 (counts, not guesses)

Evidence from the decision wrapper and the job census (seed 305000 unless stated; seeds agree):

1. **The 15 starts are all at tick 0, at home, and are abandoned on tick 1.** At tick 0, residents standing on a cell that offers a recipe they know start it (`make_gruel` 3 ticks, `grind_flour` 3, `burn_charcoal` 4, `brew_ale` 32). On tick 1 each of them chooses a `move` (PSI/CAN weighted score 31-56 for a walk to the store at (22,14) or to a farm task) and the job pauses because the worker left its start cell. After tick 1 the census is: 15 jobs, 0 complete, 15 paused, remaining ticks unchanged (e.g. gruel 3 -> 2) for the rest of the run. `DeterministicBackend.decide` has no "stay with the job you started" rule. The only counterweight is `RESUME_JOB_BONUS` = 40 for walking back to the paused job's cell: in the rest_thr70 run, paused-job holders were offered a resume 1,880 times and took it 213 times (11 %).
2. **Everyone else never has a work candidate.** Diagnostic run (`diag_work.py`, seed 305000, 3 days): of 1,673 awake labourer decisions on day 0, 1,579 (94 %) carried work offers (5 household recipes), but the offer reaches the scoring stage in 4 decisions (0.25 %) and in **0** of ~3,000 on days 1-2. The policy drops a work offer unless the recipe is in the resident's own `recipe_knowledge` memory (`cheap.py`: `o.get("action") != "work" or recipe in known_recipes`), and a typical labourer, the mayor, smith, baker (bakers know only the bakery recipes) do not know the household recipes offered at the market.
3. **The specialists who do know the food recipes are 30-60 cells away and cannot get there** (section 3b): 15 of 16 food-related residents never stood on their own workplace cell (the butcher did). The fields are not reached, so no `water`, `sow` or `harvest` is ever attempted on days 0-3: act counters show 0 such actions, and the 85 crops are dead on day 2.
4. **Refusals are not the reason.** The only refusals are `exhausted` moves (16-20 % of move attempts on days 0-1) and a few `out_of_stock` fetches on day 3. The policy never attempts work it is not offered, so there are no work refusals.
5. **Rest rule.** 71 % of awake labourer decisions on day 0 occur with energy < 35, where the policy offers only `rest`; farmers 68 %. Observed farmer walk (probe, ticks 18-39): 22 ticks for 4 cells; energy cycles 43 -> 10-14 -> three rests -> 43.
6. **Preferred-task bias (`role_bonus`) is not the cause.** Farmers get +24 for field moves, labourers -24 for them, but the bias is applied only to moves that exist; the walks themselves fail on energy first. I did not test removing it.
7. **Control for the policy cause.** Lever L6b (`stay_job`: a resident with an open running job and hunger < 1 and energy >= 35 returns a blank turn) completes 22-23 jobs on day 0 and makes 96-97 units of gruel/ale/flour/charcoal. Production still stops after day 0 (starts 32 -> 0), because the candidates in point 2 and the access problem in point 3 are untouched. So the policy abandonment is real but only one of three independent blockers.

### 3d. Which of (i)-(v)?

Ranked by what removing it does and by counts:

1. **(i) No production, at all** (proximate cause of the collapse): 0 completions, 0 field actions. It is produced by three blockers that each remove production on their own:
   * **(iii) energy/access** is the enabling cause. Even with travel nearly free (walking cost x0.1, no wait charge, rest threshold 70, stay-on-job; seed 305000) farmers reach the fields on day 2 (21 `water`, 6 `sow`), too late for 58 of the 85 crops; the town is extinct on day 7.
   * **(v) the simple policy**: abandons jobs, drops work offers the resident does not know, parks walkers in the slowest band, brings 1 loaf per fetch trip.
   * **(iv) job mix**: 59 % of residents hold a duty-less labourer job and have no usable recipe where they are; only about 16 residents can produce food, all far from home.
2. **(ii) the free store being drained** is a symptom with a clock: it is a fixed perishable stock worth about 3 days of feeding. With bread decay switched off the store empties during day 4 instead of day 3, all 100 are alive at the end of day 4 (baseline 21-34), 29 at the end of day 5, and one is left on day 6: +104 person-days, but the town is still dead. It sets the deadline; it is not the root cause.
3. **Not causes:** stamina capacity as a scalar, the stamina distribution, and who holds the food jobs (section 4).

---------------------------------------------------------------------------------------------------

## 4. Part 2: lever results

Metrics ("extinct" = first day index with 0 alive; None = one resident still alive at the end of day 6): alive at the end of day indices 2 / 3 / 4 / 5, first death and extinct day index, **person-days** = sum of alive counts at the end of days 0-6 (700 is perfect; baseline 426, seed range 420-434, so differences under about 15 are noise), store loaves at the end of day 2, food made = units added to the store inside job completions over 7 days, jobs completed, mean energy at 17:00 for days 0-2, share below 35 at the end of days 1-3, share below 35 at 17:00 for days 0-2, cells walked per resident on days 1-3.

| lever | seeds | alive end d2 / d3 / d4 / d5 | first death (idx) | extinct (idx) | person-days of 700 (delta vs base) | store loaves end d2 | food made (units, 7 d) | jobs completed | energy @17:00 d0-2 | share<35 end of day d1-3 | share<35 @17:00 d0-2 | cells/resident/day d1-3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 0,1,2 | 100 / 100 / 26 / 0 | 3/4/4 | 5/6/5 | 426 (+0) | 48 | 0 | 0.0 | 42 | 0.49 | 0.49 | 11.8 |
| L2 walk cost/cell x0.5 | 0,1 | 100 / 99 / 66 / 2 | 3/4 | 6/6 | 468 (+42) | 143 | 30 | 1.0 | 47 | 0.33 | 0.44 | 21.7 |
| L2+ walk cost/cell x0.25 (extra) | 0 | 100 / 100 / 96 / 34 | 4 | 6 | 530 (+104) | 207 | 33 | 2.0 | 37 | 0.39 | 0.62 | 31.9 |
| L2b no energy charged on cooldown-wait ticks | 0,1 | 100 / 100 / 82 / 7 | 4/4 | 6/6 | 490 (+63) | 191 | 30 | 1.0 | 43 | 0.40 | 0.50 | 19.2 |
| L1 stamina x1.5, normalised (all effort cost /1.5) | 0,1 | 100 / 98 / 42 / 0 | 3/4 | 5/6 | 441 (+15) | 143 | 15 | 0.5 | 46 | 0.34 | 0.47 | 17.0 |
| L1 stamina x2, normalised (all effort cost /2) | 0,1 | 100 / 100 / 69 / 2 | 3/4 | 6/6 | 470 (+44) | 182 | 30 | 1.0 | 47 | 0.31 | 0.48 | 20.8 |
| L1 stamina x1.5, literal sta_base=1.5 | 0,1 | 98 / 97 / 7 / 0 | 2/2 | 5/5 | 402 (-24) | 0 | 15 | 0.5 | 44 | 0.32 | 0.45 | 9.4 |
| L1 stamina x2, literal sta_base=2.0 | 0,1 | 68 / 67 / 40 / 2 | 2/2 | 6/6 | 376 (-50) | 0 | 15 | 0.5 | 33 | 0.27 | 0.56 | 7.0 |
| L3 rest_recovery_per_unit x0.5 (+5/rest) | 0,1 | 74 / 74 / 56 / 2 | 2/2 | 6/6 | 406 (-20) | 268 | 0 | 0.0 | 34 | 0.47 | 0.67 | 10.4 |
| L3 rest_recovery_per_unit x2 (+20/rest) | 0,1 | 100 / 100 / 12 / 0 | 4/4 | 5/5 | 412 (-14) | 18 | 15 | 0.5 | 46 | 0.36 | 0.45 | 13.8 |
| L4 sta_base ~ N(1,0.15) clip .6-1.4, literal | 0,1 | 97 / 96 / 28 / 1 | 2/2 | 6/6 | 421 (-5) | 60 | 0 | 0.0 | 40 | 0.46 | 0.51 | 11.4 |
| L4 same draw, normalised (effort cost / sta_i) | 0,1 | 90 / 88 / 32 / 2 | 2/2 | 6/6 | 411 (-15) | 142 | 15 | 0.5 | 41 | 0.47 | 0.53 | 11.6 |
| L5i food jobs to highest-sta residents (+L4 normalised draw) | 0,1 | 90 / 88 / 40 / 4 | 2/2 | 6/6 | 421 (-5) | 153 | 15 | 0.5 | 41 | 0.46 | 0.51 | 11.5 |
| L5ii 15 labourers -> farm_labourer | 0,1 | 100 / 98 / 21 / 0 | 3/4 | 5/6 | 420 (-6) | 42 | 0 | 0.0 | 43 | 0.49 | 0.49 | 11.7 |
| L6 policy rest threshold 35 -> 70 | 0,1 | 100 / 100 / 8 / 0 | 4/3 | 5/5 | 407 (-19) | 15 | 30 | 1.0 | 44 | 0.25 | 0.41 | 16.5 |
| L6 policy: keep working an open job (no abandon) | 0,1 | 96 / 96 / 39 / 1 | 2/2 | 6/6 | 433 (+7) | 112 | 96 | 22.5 | 42 | 0.43 | 0.49 | 11.8 |
| L6 rest_thr 70 + stay_job | 0,1 | 100 / 100 / 22 / 1 | 4/2 | 5/None | 422 (-4) | 76 | 96 | 22.5 | 47 | 0.27 | 0.41 | 16.2 |
| L6+L2b: rest_thr 70 + stay_job + wait_free | 0,1 | 100 / 100 / 62 / 4 | 4/4 | 6/None | 466 (+40) | 236 | 102 | 25.5 | 49 | 0.28 | 0.36 | 21.6 |

Definitions of what I actually did:
* **L1 normalised** ("stamina x k" meaning "a k times bigger reserve"): every Effort's `stamina_cost` is divided by k (walk, work and the rest). Rest recovery is unchanged, so rests are relatively larger; hunger from effort also falls by 1/k because it is proportional to energy spent. **L1 literal**: `sta_base` = k and the starting reserve = k, nothing else; this is what the world does today if you edit the cast value.
* **L2**: `CARRYING.base_move_energy` x0.5 (the per-cell walking cost; the hard-coded 0.1 conversion in `move_actor` is unchanged) and x0.25 (single seed); **L2b** `wait_free`: the walking Effort costs nothing on a tick where `carry_move_cooldown >= 1` (no step is taken).
* **L3**: `EXHAUSTION.rest_recovery_per_unit` and the module copies x0.5 / x2.
* **L4**: `sta_base` ~ N(1.0, 0.15) clipped to 0.6-1.4 from a fixed generator, per cast index. Literal (`sta_base` and starting reserve = min(1, v)) and normalised (effort cost / v for that resident).
* **L5(i)**: `plan_founding_town` patched so that the food-production jobs (farmer, farm_labourer, animal_keeper, dairymaid, miller, baker, fisher, butcher, fishmonger) go to the highest-`sta_base` residents (ties: younger), on top of the L4 normalised draw. The right control is the L4 normalised row. **L5(ii)**: the first 15 labourers in cast order are re-staffed as farm_labourer (same code path as the cast draw, so they get farm workplaces).
* **L6**: `rest_energy_threshold` 35 -> 70 set on each `DeterministicBackend`; `stay_job` as in 3c.7.

Reading the table:

* **Stamina capacity.** Literal x1.5 and x2 are *worse than baseline* (-24 and -50 person-days). At x2 the store is empty a day early (298 loaves at the end of day 1 vs 542; 123 loaves in pockets vs 40; 459 fetches on day 1 vs 218) and 30-34 residents who got no loaf starve on day index 2. Mechanism not traced beyond that: sleep refills only to `rest_cap` = 1.0, the band edges move up with capacity, and walking cost does not change, so a bigger `sta_base` buys nothing. Normalised x2 is equivalent to walking x0.5 (+44 vs +42); x1.5 normalised +15 (within noise). If you want a "bigger body", it has to be implemented as an effort-cost divisor or `rest_cap` must scale with capacity; editing `sta_base` alone does not do it.
* **Walking cost** is the strongest single energy lever (x0.5: +42; x0.25: +104 on one seed, alive 96 at day 4) and the wait-tick charge alone gives +63 with a single semantic change and cells per resident up from 11.8 to 19.2 a day.
* **Rest recovery** is not generous in a way that causes loops: halving it doubles rest ticks on day 0 (3165 vs 1844), only 39 residents reach the store on day 1 (baseline 69) and 25-27 starve a day earlier (-20 person-days); doubling it gives nothing (-14, noise). The rest loop in the data comes from the 35 threshold sitting inside the x3-interval band, not from the +10 per rest.
* **Stamina distribution** has no mean benefit and spreads the damage: -5 (literal) / -15 (normalised) person-days. Normalised: 10-11 residents starve a day early and their mean sta is 0.83-0.86 against 1.0 (the weak die first). Literal: 5 early deaths with mean sta 1.17 (the strong, for the capacity reason above).
* **Job draw / headcount** has no measurable effect: capability-first assignment is +10 vs its own control (noise); 15 extra farm labourers -6. Nobody food-related reaches a workplace in either case, so who holds the job is irrelevant until access is fixed. I did not test it after the access fix.
* **Policy** levers alone are within noise on survival. `rest_thr 70` cuts the share below 35 at the end of day from 0.49 to 0.25 and raises cells walked from 11.8 to 16.5 a day, but does not change the extinction day (5/5 vs 5/6) and costs 19 person-days. `stay_job` produces the only substantial food in these runs (96 units on day 0, once).

### Stacked configurations (ceiling tests, 14 days, one or two seeds)

"wilt 8" = crops tolerate 8 dry periods instead of 2 (starting crops and the CROPS table). "no decay" = stock `decay` set to 0 on the starting piles. Days are indices; person-days use the first 7 days so they compare with the lever table (baseline 426).

| configuration (all but the last two include wait_free + rest_thr 70 + stay_job) | seed | alive at end of day index 0..(last) | extinct (idx) | person-days, 7-day window | harvest / water / sow actions (whole run) | jobs completed |
|---|---|---|---|---|---|---|
| walk x0.5 | 305000 | 100,100,100,100,97,36,1,0 | 7 | 534 | 0 / 26 / 13 | 26 |
| walk x0.5 | 305001 | 100,100,100,100,98,37,0 | 6 | 535 | 0 / 15 / 13 | 25 |
| walk x0.25 | 305000 | 100,100,100,100,97,46,0 | 6 | 543 | 0 / 28 / 13 | 28 |
| walk x0.1 | 305000 | 100,100,100,100,91,47,2,0 | 7 | 540 | 21 / 93 / 42 | 35 |
| walk x0.25 + wilt 8 | 305000 | 100,100,100,100,97,50,3,1,0 | 8 | 550 | 70 / 38 / 32 | 38 |
| walk x0.25 + wilt 8 + no decay | 305000 | 100,100,100,100,100,100,76,8,3,1... | none (alive 1) | 676 | 26 / 17 / 13 | 39 |
| walk x0.25 + wilt 8 + no decay | 305001 | 100,100,100,100,100,100,67,4,2,1... | none (alive 1) | 667 | 31 / 19 / 1 | 41 |
| wilt 8 + no decay only (no energy or policy fixes) | 305000 | 100,100,100,100,100,27,1,1,1,1 | none (alive 1) | 528 | 0 / 0 / 0 | 0 |
| no decay only | 305000 | 100,100,100,100,100,29,1 | none (alive 1) | 530 | 0 / 0 / 0 | 0 |

Conclusion of the ceiling tests: fixing energy, the policy, the watering deadline and the decay together buys about 2 days (collapse at day index 6-7 instead of 4-5) and still produces only 3-15 units a day of finished food after day 0, against about 100 meals a day. The remaining gap is in the production chain itself (who farms, harvest -> grind -> bake needs three different workers at three sites, none staffed beyond 1-2 people), which I did not try to fix.

---------------------------------------------------------------------------------------------------

## 5. L7: lamplighter timing (DAYNIGHT on, 7 days, seeds 305000 and 305001)

`worlds.daynight.switch_on(w)` right after `create_game`. Definitions are those of `duty_run.py` (hours after that day's sunset until all four lamps are lit; hours after sunrise until all four are dark); I computed them from my own tick log. "never" means the lamps were not all lit that night. LP = lamplighter.

| variant | seed | lamplighter(s) (role_identity) | dusk all-lit, h after sunset, days 0-3 | dawn all-dark, h after sunrise, days 0-3 | LP min energy/day (days 0-3) | LP alive end of day 3 | town alive end of days 2,3,4 | person-days |
|---|---|---|---|---|---|---|---|---|
| (i) baseline duty (first adult in founding order) | 305000 | Verity (0.89) | 8.9/9.9/8.1/9.1 | 1.1/6.6/5.1/7.6 | 5.7/8.0/7.6/8.9 | True | 100/98/20 | 418 |
| (i) baseline duty (first adult in founding order) | 305001 | Josiah (0.84) | 3.5/2.7/8.9/1.1 | 1.1/1.1/1.1/- | 8.9/8.3/9.4/9.7 | True | 100/100/24 | 424 |
| (ii) 2 lamplighters (founding order x2) | 305000 | Verity (0.89), Ida (0.56) | 8.4/1.2/4.1/1.6 | 0.6/5.1/1.6/0.9 | 6.1/7.6/9.9/9.3 | True | 100/99/21 | 420 |
| (ii) 2 lamplighters (founding order x2) | 305001 | Josiah (0.84), Jem (0.62) | 5.0/6.7/1.1/7.4 | 0.6/1.1/1.1/6.4 | 5.7/8.7/9.2/9.6 | True | 100/100/28 | 428 |
| (iii) lamplighter = highest role_identity adult | 305000 | Constance (0.95) | 8.9/1.2/4.9/6.9 | 1.1/5.6/2.4/3.4 | 5.7/7.7/8.8/10.9 | True | 100/98/17 | 415 |
| (iii) lamplighter = highest role_identity adult | 305001 | Adelina (0.94) | 4.2/11.7/4.9/4.1 | 1.1/1.1/1.1/3.6 | 8.9/8.4/12.8/6.8 | True | 100/100/19 | 419 |
| (iv) (iii) + his effort cost /1.5 | 305000 | Constance (0.95) | -/10.4/9.4/7.9 | 1.1/2.1/4.6/- | 10.9/14.1/12.4/11.8 | True | 100/98/22 | 421 |
| (iv) (iii) + his effort cost /1.5 | 305001 | Adelina (0.94) | 10.9/1.2/1.1/7.4 | 1.1/3.3/6.6/4.9 | 10.7/14.1/14.1/14.6 | True | 100/100/19 | 419 |
| (v) due_floor 0.9 | 305000 | Verity (0.89) | 8.9/1.2/1.1/7.6 | 1.1/6.6/5.4/3.9 | 5.7/9.7/10.2/9.7 | True | 100/98/20 | 418 |
| (v) due_floor 0.9 | 305001 | Josiah (0.84) | 1.4/2.7/8.9/1.1 | 1.1/1.1/1.1/- | 8.9/8.3/9.4/9.7 | True | 100/100/26 | 426 |
| (vi) lamplighter drawn as a cast job (role_identity ~0.3) | 305000 | Ephraim (0.49) | 13.9/9.4/0.1/5.4 | 1.1/1.3/-/3.9 | 8.9/7.8/10.4/9.3 | True | 100/98/21 | 419 |
| (vi) lamplighter drawn as a cast job (role_identity ~0.3) | 305001 | Vernon (0.24) | -/-/-/- | 1.1/0.1/-/0.1 | 5.7/7.0/12.1/14.0 | True | 100/100/26 | 426 |

| variant | median dusk lag (h, nights lit) | mean dusk lag | nights lit within 2 h / all nights (never lit) | median dawn lag (h) | mean dawn | mornings dark within 2 h | mean LP min energy | person-days (mean) |
|---|---|---|---|---|---|---|---|---|
| (i) baseline duty (first adult in founding order) | 8.5 | 6.5 | 1/8 (0) | 1.1 | 3.4 | 4/7 | 8.3 | 421 |
| (ii) 2 lamplighters (founding order x2) | 4.5 | 4.4 | 3/8 (0) | 1.1 | 2.2 | 6/8 | 8.2 | 424 |
| (iii) lamplighter = highest role_identity adult | 4.9 | 5.8 | 1/8 (0) | 1.7 | 2.4 | 4/8 | 8.8 | 417 |
| (iv) (iii) + his effort cost /1.5 | 7.9 | 6.9 | 2/8 (1) | 3.3 | 3.4 | 2/7 | 12.8 | 420 |
| (v) due_floor 0.9 | 2.1 | 4.1 | 4/8 (0) | 1.1 | 2.9 | 4/7 | 8.9 | 422 |
| (vi) lamplighter drawn as a cast job (role_identity ~0.3) | 7.4 | 7.2 | 1/8 (4) | 1.1 | 1.3 | 5/6 | 9.4 | 422 |

Energy-fixed world (wait-tick charge removed and walking cost x0.5), same measurements:

| variant (energy fixed: wait_free + walk x0.5) | seed | dusk all-lit, h after sunset, nights 0-3 | dawn all-dark, h, mornings 0-3 | LP min energy/day | person-days |
|---|---|---|---|---|---|
| baseline duty | 305000 | never/12.7/7.6/1.1 | 1.1/1.3/1.1/4.4 | 15.8/13.6/12.0/18.1 | 532 |
| baseline duty | 305001 | never/7.2/1.1/never | 1.1/2.8/4.4/3.6 | 15.9/12.1/22.8/7.9 | 535 |
| due_floor 0.9 | 305000 | never/12.7/7.6/1.1 | 1.1/1.3/1.1/4.4 | 15.8/13.6/12.0/15.5 | 532 |
| due_floor 0.9 | 305001 | never/13.7/never/5.6 | 1.1/4.8/1.1/1.4 | 13.0/13.8/15.2/14.5 | 535 |

What the tick logs show (`dnt_*` runs, seed 305000, `*.lpticks`): the dusk lag is a function of the lamplighter's energy at sunset.
* Baseline duty, nights 0-3: energy at sunset 17 / 38 / 15 / 24; **he sleeps after sunset on every night** (sleep_before_collapse at energy 8-14, 7-9 hours of sleep to refill 3 points per tick), lights the first lamp when he wakes at 100: lag 8.9 / 9.9 / 8.1 / 9.1 h.
* due_floor 0.9: nights 1 and 2 he is at 87 and 84 at sunset, does not sleep, and lights within 1.17 / 1.14 h. Nights 0 and 3 he is at 17 and 25 and sleeps: 8.9 and 7.6 h. The policy change makes the duty beat tiredness earlier, but it cannot help a lamplighter who is already exhausted at dusk.
* His minimum energy each day is 5.7-10.9 in every variant except (iv) (10.7-14.6), i.e. he lives at the collapse floor. In the energy-fixed world it is 8-23 (mean 14.8) and the lag does not improve (7.2 h median over the nights that were lit; 3 of 8 nights never lit), because from an energy of 20-40 at sunset he walks to the square in the slow band for four hours and then sleeps.

Reading, with n = 8 nights per variant (two seeds x four nights; the lag is bimodal, about 1 h or 8-10 h, so medians are fragile):
* **Second lamplighter (ii):** median dusk lag 4.5 h vs 8.5 h, lit within 2 h on 3 of 8 nights vs 1 of 8, dark within 2 h on 6 of 8 mornings vs 4 of 7. The second holder has lower role_identity (0.56-0.62).
* **Highest role_identity (iii):** 4.9 h median, 1/8 within 2 h, no clear change (role_identity 0.94-0.95 vs 0.84-0.89 is a small difference on the duty rule).
* **(iii) + his effort cost /1.5 (iv):** worse on dusk (7.9 h, one night never lit) although his minimum energy rises to 12.8; stamina does not decide *where he is* at dusk.
* **due_floor 0.9 (v):** best on dusk, median 2.1 h, 4/8 nights within 2 h.
* **Cast job (vi):** the FOUNDING_JOBS lamplighter row has role_identity mean 0.3 (drawn 0.49 on seed 305000, 0.24 on 305001). The duty urgency is role_identity x level against the larger of hunger and tiredness, so a low-identity lamplighter never wins: on seed 305001 the lamps were **never** lit in four nights, on 305000 they were lit on all four nights, at 13.9 / 9.4 / 0.1 / 5.4 h. As currently defined this row is not usable for the duty.
* **Does the town survive longer?** No. Every variant is at 415-428 person-days (baseline 421); the lamplighter is alive at the end of day 3 in all 12 runs; town extinct day 5-6 as before.

---------------------------------------------------------------------------------------------------

## 6. Ranked causes, with evidence

| rank | cause | evidence |
|---|---|---|
| 1 | No production loop starts: workers cannot reach sites in time, the 11-15 jobs that do start are abandoned on tick 1, and most of the town (59 labourers, officials) is never offered an applicable recipe | 0 completions / 0 harvests in every baseline run; 15 of 16 food workers never on their workplace cell; jobs 15 paused / 0 complete; labourer work offers reach scoring in 4 of 1,579 decisions; crops 85 -> 0 on day 2 |
| 2 | Walking energy model against the map scale: 100-point reserve = 12 cells at best; commutes 29-51 cells; full step charged on waiting ticks (about half of attempts move a cell); band edges and the 35 rest threshold park walkers at x3 interval | 99.9 % of effort energy is walking; 15.5 / 22.7 / 19.3 points per cell moved; wait_free +63 and walk x0.5 +42 person-days; ceiling tests |
| 3 | Fixed perishable start stock: 3 days of feeding value, then 0; no replenishment | bread condition 0.75 / 0.50 / 0.25 / 0; hunger relieved per eat 0.75, 0.50; no_decay +104 person-days (one extra day) |
| 4 | Crop watering deadline shorter than the commute | CROPS.wilt = 2, crops 0 alive on day 2; wilt 8 raises the best stack from collapse day 6 to day 7-8 |
| 5 | Simple policy: no stay-on-job, known-recipe gate, rest threshold inside the slow band, one loaf per fetch | 3c.1-3c.5; stay_job makes the only food in the baseline family (96 units) |
| 6 | Job mix: 59 % spare labourers; 16 food-related jobs | 3c.2, section 2.7 |
| 7 | Stamina scalar / distribution / job-capability weighting | no effect or negative (section 4) |

---------------------------------------------------------------------------------------------------

## 7. Recommendation, on your questions

Order of work, because later items are untestable until earlier ones are in:

1. **Fix the walking energy accounting first (Tract A world code).** Mint the walking `Effort` only on a tick where a step is actually taken (or charge a tired walker the same total per cell, not per tick). Measured: +63 person-days, energy per cell from 15-23 to about 8, cells per day 11.8 -> 19.2, share below 35 at day end 0.49 -> 0.40. It looks like an unintended side effect: the effort is minted before the cooldown check, the nearby comment describes the waiting ticks but not a cost for them, and no test I ran pins their energy (section 8). Please confirm intent with whoever owns Phase 024/049.
2. **Then rescale walking against the map (pack data plus one Tract A constant).** Either `CARRYING.base_move_energy` 1.0 -> about 0.25-0.5, or shorten the commute (move homes or workplaces; the farm commute is 51 cells, a reserve is 12). With the wait charge fixed, the needed order of magnitude is: a farmer should reach a field and still have most of a reserve left, which means about 2-4 points per cell, not 8. x0.25 gave +104 person-days (one seed); x0.1 got the farmers to the fields on day 2.
3. **Then the simple policy (backend constants, no world change).** Add stay-on-job, hysteresis for the rest rule (rest until the reserve is back above the x1 band edge, 70, before resuming a walk), and decide whether the known-recipe gate should keep removing the only work offers most residents see. Alone these are within noise; they matter only after items 1-2.
4. **Then the economy's clock (pack data).** The starting bread decays to nothing in 3 days and the crops die after 2 dry days. Either make the start stock last (slower decay or a larger non-perishable buffer), lengthen `CROPS.wilt`, or start residents next to the fields. Without this the first harvest (day 4 at the earliest) arrives after the food is gone.
5. **Lamplighter.** Do not add a second lamplighter yet. The lag is the lamplighter being exhausted or far from the square at sunset, which is the same walking sink; the cheapest effective change in the unmodified world is `DUTIES.lamplighter.due_floor` 0.5 -> 0.9 (median 2.1 h, 4/8 nights within 2 h), and a second lamplighter is the next (4.5 h, 3/8). After items 1-2, re-measure: in my energy-fixed run the lag did not improve (7.2 h), so the lamplighter needs a policy of being rested and in place at dusk, not a stamina bonus (iv) or an appointment by role_identity (iii). If you add the lamplighter to the cast, its `role_identity_mean` (0.3) must be raised (about 0.8+): at 0.24 the lamps were never lit.
6. **Overall stamina: do not change `sta_base` as a global scalar.** Literal x1.5 / x2 lowered survival by 24 / 50 person-days. If you want a bigger body, implement capacity as a divisor on effort cost (normalised x2 = walking x0.5, +44) or make `rest_cap`, the starting reserve and the policy thresholds relative to capacity.
7. **Stamina distribution: do it later, for variety, not for balance.** Wire `draw_physique` (the `PHYSIQUE` table already exists) on its own random stream. Expected effect on the town is slightly negative on survival (-5 to -15 person-days) with early deaths among the weak, and it needs the energy model fixed first.
8. **Job draw: do not add capability weighting now.** Capability-first assignment of food jobs gave no measurable gain (+10 vs control, noise) because no food worker reaches a workplace; 15 extra farm labourers gave -6. Revisit after items 1-4. The real job-mix issue is the 59 duty-less labourers with no applicable recipe, which a draw tweak does not address (they need duties, e.g. hauling and field work as data).

---------------------------------------------------------------------------------------------------

## 8. What each recommendation touches, and the risks

| change | where | blast radius I could identify |
|---|---|---|
| wait ticks free | Tract A: `worlds/bigville_world.py` `move_actor` | every fatigued walk changes: energy, hunger from effort (0.2 x energy), speeds over time, who reaches what. Tests that read energy after walking: `tests/test_phase024_exhaustion.py`, `tests/test_phase070b_body.py`, `tests/test_bigville_world_migrated.py` (move_energy), about 35 test files read `stamina_reserve`/`energy`. **Measured: with this change applied to a scratch copy, the whole suite shows no new failure** (section 8 test results), including the three `MENU_DIGEST_AT_LA01` tests, so the pinned digests do not exercise fatigued walking. Docs/phases run logs that quote movement numbers will no longer match. |
| walking cost scale | pack data `packs/bigville/world/carrying.json` (`base_move_energy`); `move_actor` hard-codes the 0.1 factor | **Measured with `base_move_energy` 0.5: 2 new failures out of 3,104**: `test_bigville_world_migrated.py::test_overweight_acceptance_is_possible_but_slows_and_costs_energy` (pins load-vs-energy numbers) and `test_phase013a_packs.py::test_export_rerun_is_byte_identical` (very likely because I rewrote `carrying.json` with a different JSON layout; not a behavioural pin). A pack-level constant for the 0.1 factor would be cleaner than two numbers multiplied in code. |
| policy (stay-on-job, rest hysteresis, known-recipe gate) | `bigville/backends/cheap.py` constants and `decide` | **Measured with `rest_energy_threshold` 35 -> 70** (78 test files that mention the simple backend, 1,592 tests): 1 new failure, `tests/test_lazy_work.py::test_town100_menu_run_is_unchanged` (pins the town100 menu run). `test_fix024_starvation.py` (first 97 turns, seed 305017) still passes. `test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns` already fails in the scratch control, so I cannot say whether it would pin the change. The lexicon doc mentions 35 as not cross-checked. |
| pack economy (decay, wilt, start stock) | `packs/bigville/world/*.json` (`CLASS_DECAY`, `CROPS`, `STARTING_STOCK`, `STARTING_CROPS`) | `tests/test_phase007_balance_scenario.py`, BALANCE self-test, anything that pins starting stock. |
| due_floor / second lamplighter | `packs/bigville/world/duty.json` (`DUTIES`); `DAYNIGHT.lamplighters` in the DAYNIGHT table; `worlds/daynight.py` `appoint_lamplighters` | `tests/test_phase042_daynight.py`, `test_phase042b_lamplighter.py`, `test_phase042c_duty.py`. |
| stamina distribution | cast draw (`worlds/bigville_town100_world.py`, `domains/population.py`), body defaults (`actor_defaults.json`) | the committed `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json` are checked byte-for-byte against the generator in `tests/test_phase016b_founding_cast.py` and read by `test_phase019_knowledge.py`: any new draw must use its own stream and stay out of the cast record, or both seed files and those tests change. |
| job draw | `domains/population.py` `seed_jobs`, `generate_cast100` | the same cast seed files; `test_phase016a/b` (counts are asserted against `seed_jobs`), `test_phase019_knowledge.py`; every downstream fixture keyed on cast indices or names. |

Test impact, measured on throw-away copies of the archive (not the repo), full suite `pytest tests --ignore=tests/live` (3,104 tests, xdist -n 2):

| scratch copy | change | passed | failed | new failures vs control |
|---|---|---|---|---|
| control | none (HEAD archive) | 3085 | 6 | - (6 pre-existing, see below) |
| wait ticks free | `move_actor` mints the walking Effort only when `carry_move_cooldown < 1` | 3085 | 6 | **none** |
| walking cost x0.5 | `packs/bigville/world/carrying.json` `base_move_energy` 1.0 -> 0.5 | 3083 | 8 | `tests/test_bigville_world_migrated.py::test_overweight_acceptance_is_possible_but_slows_and_costs_energy`, `tests/test_phase013a_packs.py::test_export_rerun_is_byte_identical` (probably my JSON re-serialisation) |
| rest threshold 70 | `SimplePolicy.rest_energy_threshold` default 35.0 -> 70.0; only the 78 test files that mention the simple backend were run (1,592 tests) | 1577 | 4 (3 of them pre-existing) | `tests/test_lazy_work.py::test_town100_menu_run_is_unchanged` |

Pre-existing failures in the control copy (I did not investigate them; they may depend on the repo's git state, untracked files, ports or timing, which the archive copy lacks): `tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world`, `tests/test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]`, `tests/test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds`, `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`, `tests/test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns`, `tests/test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears`.

Not run: the stamina-distribution and job-draw changes (they were applied in-process only), the pack-economy changes (decay, wilt), and the lamplighter changes. For the cast changes the byte-for-byte cast-seed check in `tests/test_phase016b_founding_cast.py` is the test that will fail if the cast record changes.

---------------------------------------------------------------------------------------------------

## 9. Uncertainty and what I did not measure

* **Seeds.** Baseline has 3 seeds; most levers have 2 (305000, 305001); walk x0.25, the x0.1 and x0.25 ceilings, "wilt 8", "wilt 8 + no decay" (no energy fixes), "no decay" are single seed. Baseline person-days range 420-434, so differences below about 15 are noise. The lamplighter results are 8 nights per variant and the lag is bimodal; treat the L7 ordering as indicative only.
* **Lever definitions matter.** "Stamina x k" has no single meaning in this code. I report both the literal edit (harmful) and a cost-divisor model (helpful); the divisor model also lowers hunger from effort, which a physical "bigger body" would not necessarily do.
* **Interaction.** I did not run a factorial design. The stacked runs show the levers are not additive (rest_thr 70 + stay_job + wait_free is +40 while wait_free alone is +63).
* **Not measured:** 14-day steady state (no configuration reached one); the effect of removing `role_bonus`; hauling/field duties for labourers; the production chain (harvest -> grind -> bake) as a staffed system; behaviour with LLM or other backends; lazy mode (the user's lazy-mode run was not repeated); what happens if homes sit next to workplaces. The test-impact numbers in section 8 come from throw-away copies, one lever per copy; I did not test combinations, and I did not run the pack/pack-export or doc cross-checks beyond the suite.
* **The "wait ticks cost energy" finding** is from reading `move_actor` and from direct measurement (probe: a farmer at reserve 20-45 pays 6.6-7 points every tick and advances a cell every third tick). I did not find a document that says it is intended.
* The harness wraps methods and graph calls of the loaded world to record counters; it does not change any value. The baseline run reproduces your numbers exactly, which is the check that it is observation-only.

---------------------------------------------------------------------------------------------------

## 10. Files

* `/tmp/balance/harness.py` (instrumented runner; levers by `--lever name=value+name2`), `/tmp/balance/diag_work.py`, `/tmp/balance/analyze_*.py`, `/tmp/balance/mk_*.py`.
* Raw outputs: `/tmp/balance/out/*.json` (per run: per-day rows, per-role tick categories, energy by band, decisions, traces), `*.log`, `*.lpticks` (lamplighter tick logs), `out/pytest_*.log`.
* Reproduce the baseline: `cd /tmp/balance && python3 harness.py --seed 305000 --days 7 --lever base --out out/x.json`.
