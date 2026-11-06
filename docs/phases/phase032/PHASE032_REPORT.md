# Phase 032: Use trains the body

## Summary

Each effort that uses strength or stamina now raises the trained part of that stat, by the seed's rule
(`bd_train_strength`, `bd_train_stamina`): intensity x TRAIN_RATE x (base x TRAIN_HEADROOM - trained). Gains
diminish toward the ceiling. Effective strength and stamina are (base + trained) x health (`bd_effective_stats`),
the reserve is clamped to the effective stamina, and the recipe strength gate reads effective strength. Efforts
come from movement (stamina) and from recipes (stamina, and strength when the recipe has a strength requirement).
A `training` physical-subsystem switch, default on, turns all training off.

Heavy trade recipes were not strength-gated before this phase. The gate in `_capable` and `_can_attempt` applied
only to open (household) recipes, and no open recipe needs more than 1.0. This phase applies the strength gate to
every recipe with a strength requirement. That is what the brief needs (a resident must be able to reach a recipe
that was above them at the start), and it changes the founding town. See Open questions, item 1.

Self-test: 0 errors, 0 warnings. Time-to-train line: a founding labourer (strength 1.0, health 1.0) reaches the
plough's 1.2 in **15 efforts** of 0.4 stamina, one per 240-minute forge_plough batch: **60.0 hours of forging**.
Full suite: 1026 passed, 2 skipped, 3 failed. The 3 failures are the Ocelot adapter tests that also fail without
this phase (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`).

## Changes

### Code

- `worlds/bigville_world.py` (my hunks only; the other session's `"food"` flag in `_actor_options` and
  `resident_plan_from_context` are uncommitted in the same file and I did not touch them):
  - `PHYSICAL_SUBSYSTEM_DEFAULTS`: `"training": True`.
  - `_run`: calls `_resolve_body_stats()` after `_resolve_actor_events()`, so the sleep band sees fresh capacity.
  - `_resolve_actor_events`, `exerted` branch: after the cost is spent and hunger is raised, the effort trains each
    stat it uses, once (`_train_from_effort`), when `training` is on. The `rested` branch caps recovery at
    `effective_stamina` instead of the stored `stamina`.
  - New block "body training and effective stats (Phase 032)", before the exhaustion block: `effective_strength`,
    `effective_stamina`, `_effective_body_stat`, `_train_from_effort`, `_resolve_body_stats`.
  - `body_state`: `strength` and `stamina` come from the effective helpers, not the stored attributes.
  - `_exhaustion_band`: the capacity is `effective_stamina`.
  - `_contest_side` (Phase 029): force reads `effective_strength`. This is the one definition of effective strength.
  - `_open_job`: the Job node stores `uses_strength` (1 when the recipe has a strength requirement).
  - `_spend_job_stamina`: the Effort node gets `uses_strength` from the job.
  - movement Effort (in the move step): `intensity` is now `min(1, stamina_cost)`, the same scale as recipe efforts.
    Before it was `min(1, effort)`. No code read the old value.
  - `_recipe_refusal` (`unskilled`), `_capable` and `_can_attempt`: the strength check runs for every recipe with a
    strength requirement, not only open ones. The open-recipe check for held tools is unchanged.
- `domains/world_affordances.py`:
  - `train_gain(base, trained, intensity=1.0)`: now takes the effort's intensity (capped at 1). Default keeps the old value.
  - `efforts_to_train(base, target, intensity)`: new. Counts the efforts the world's rule needs (it iterates the same
    `train_gain`), or returns None when the target is above base x (1 + TRAIN_HEADROOM) or intensity is 0.
- `domains/bigville_entities.py`:
  - `_check_training` (new, called from `check_consistency`): TRAIN_HEADROOM in [0, 1], TRAIN_RATE in (0, 1],
    no negative stamina cost, and every recipe's strength requirement reachable from the founding body (an ERROR
    otherwise). It also writes the time-to-train INFO line.
- `packs/bigville/world/constants.json`: the `_doc` text for TRAIN_HEADROOM and TRAIN_RATE now cites the seed
  (`seeds/bigville_body.json`, rules `bd_train_strength` and `bd_train_stamina`). Values unchanged: 0.4 and 0.12.
  Both packs already carried these values. `packs/test_hamlet` defers to the bigville citations and is unchanged.
  `tools/export_pack.py` rewrote nothing else (`git status` shows only this file under `packs/`).

### Tests

- New: `tests/test_phase032_training.py` (10 tests). Covered: repeated forging gives diminishing gains toward the
  ceiling (200 batches, each gain matches `train_gain`); a trained smith can start the plough after 39 knife batches,
  which equals `efforts_to_train`; low health lowers effective strength and stamina, clamps the reserve, and blocks a
  knife; training off changes no body value; walking trains stamina only when on; a timed plough trains in its ticks;
  contest force scales with effective strength; the count helper's edge cases; exertion counts the capacity an
  effort adds.
- Existing tests, list of every change (all setup or one number; no assertion removed):
  1. `tests/test_simple_life.py::test_physical_subsystems_default_on_...`: expected switch dict gains `"training": True`.
  2. `tests/test_scenario_runner.py::test_runner_replays_...`: expected switch dict gains `"training": True`.
  3. `tests/test_phase022_recipe_stamina.py::_smith`: smith `str_base` 1.3 (the plough needs 1.2; without this the
     gate refuses the plough). Setup only.
  4. `tests/test_phase022_recipe_stamina.py::test_an_instant_craft_...`: `fatigue` expected value changed from
     `declared` (0.4) to `declared + train_gain(1.0, 0.0, declared)` (0.4192). The read-off is capacity less
     reserve. The forge adds stamina capacity by the training gain (0.0192), so the deficit grows by that gain. The
     reserve assertion (drop of exactly 0.4) is unchanged.
  5. `tests/test_phase023_job_occupancy.py::_smith`: `str_base` 1.3. Setup only.
  6. `tests/test_phase024_exhaustion.py::_smith_at_forge`: `str_base` 1.3. Setup only.
  7. `tests/test_phase024_exhaustion.py::_resident`: now takes `**world_kwargs`. Setup only.
  8. `tests/test_phase024_exhaustion.py::test_a_resident_who_keeps_working_after_a_collapse_falls_again`: built with
     `physical_subsystems={"training": False}`. A walking step trains stamina (+0.0048 at base 1.0), which moves the
     e_low band boundary this test walks across. The test is about exhaustion, so it keeps capacity at its founding value.
  9. `tests/test_phase030_store_lock.py`: smith `str_base` 1.3. Setup only.
  10. `tests/test_bigville_topic_style_migrated.py::test_production_requires_...`: smith `str_base` 1.1 (scythe needs 1.1).
      Setup only.
  11. `tests/test_bigville_world_migrated.py`: three tests set `str_base` 1.3 on the smith (furniture and plough) or
      joiner (cart 1.05, wagon 1.2). Setup only.

## Design

- Formulas (seed): trained gain per effort = `intensity x 0.12 x (base x 0.4 - trained)`. The seed's trained-part
  ceiling is base x 0.4. Effective stat = (base + trained) x health, so the total ceiling is base x 1.4. The brief said
  "base x (1 + TRAIN_HEADROOM)" for the total. The seed's form gives the same total, so the seed was followed.
- Intensity: the effort's stamina cost, capped at 1. A recipe batch with cost 0.4 has intensity 0.4. A timed
  job's tick has its share of the cost. A movement step's cost is `effort x 0.1`. Movement intensity was
  `min(1, effort)` before, which the seed does not define; the port now uses the cost scale.
- Once per effort: `str_done` and `sta_done` on each Effort, as the seed's `where` clauses require. Training is
  applied in the same resolution pass as the cost, so each Effort trains once.
- Recomputed every run: `_resolve_body_stats` recomputes effective stats on every run, not only when `stats_dirty`
  is set, so a health change shows up on the next run. The flag is set by training and cleared by the recompute.
- Reserve clamp (seed `bd_effective_stats`): the reserve is limited to the effective stamina on each run.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs in `docs/phases/phase032/`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (`selftest_bigville.log`) | exit 0; ERRORS (0); WARNINGS (0); INFO (73) |
| `python3 -m domains.check --pack test_hamlet` (`check_hamlet.log`) | exit 0 |
| `python3 tools/generate_seeds.py --check` (`seeds_check.log`) | exit 0; "match pack 'bigville' (31 files)" |
| `python3 tools/export_pack.py` | normalised 197 tables; `git status` shows only `constants.json` under `packs/` |
| `pytest tests/test_phase032_training.py` | 10 passed |
| Affected files (phase022, 023, 024, 029, 030, simple_life, scenario_runner, topic_style, world_migrated) | 251 passed |
| Full suite `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (`full_pytest.log`) | 1026 passed, 2 skipped, 3 failed (Ocelot adapter, baseline) |

No full-suite run was taken before my edits, so this phase has no same-tree baseline. The Phase 029 report
recorded its own end state (968 passed, 3 Ocelot failures), and the Ocelot failures recur here with the other
session's uncommitted files present.

The 3 failures are `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
`test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
and `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
Each raises `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.

Time-to-train, checked two ways:
- Formula (self-test): plough, 15 efforts x 240 min = 60.0 h.
- World (test `test_a_resident_trained_by_forging...`): a founding smith forging knives (cost 0.15, 90 min) reaches
  the plough's 1.2 after 39 batches, the value `efforts_to_train(1.0, 1.2, 0.15)` returns. 39 x 90 min = 58.5 h.
  Knives are the route open to a base-1.0 smith, because the plough is closed until 1.2.

## Limits

- The 100-resident village was not run (the brief did not ask for it). Expected changes, not measured:
  - Forging the plough, scythe, wagon and cart is refused (`unskilled`) for base-1.0 smiths and joiners until
    trained. Scythe (1.1), cart (1.05), plough and wagon (1.2) are all above base. Ploughs and wagons may be made
    much less often, and anything downstream of them changes.
  - Walking and forging raise trained stamina, so capacity rises above 1.0 over time, and the exhaustion thresholds
    move with it.
  - Strength and stamina read-offs change for anyone who trains.
- Training off does not restore the baseline for trades. The strength gate applies with training off, so base-1.0
  bodies still cannot start the plough, wagon, scythe or cart. Training off only stops the body from changing.
- Sleep restores the reserve to `rest_cap` (1.0, absolute). Trained endurance above 1.0 can only be reached by the
  `rest` action, which clamps to effective stamina. The two caps disagree above 1.0.
- A walking step trains stamina by about 0.0048 at base 1.0 (intensity 0.1, gap 0.4). That is 1.2% of the remaining
  gap per step. A long walk saturates the ceiling quickly. Not measured in a village run.
- Health (body `health`) is never changed by the port's rules, only by a test or a future rule. The health
  scaling is tested by setting it directly.
- Contest efforts (Phase 029) spend stamina without training. The brief lists only movement and recipes as sources.
- A timed job trains tick by tick (each tick's share is its own intensity). Its total is close to the one-batch
  count but not equal, because the gap shrinks within the job. The self-test line uses one effort per batch.
- The balance model's stamina line does not count training or the larger capacity.

## Open questions

1. **Trade strength gate.** Confirm that heavy trade recipes should be gated (the RECIPE_EXERTION doc says a heavy
   trade "DEMANDS strength you must HAVE to do it at all"). It is the largest change in this phase: base-1.0 smiths
   and joiners cannot start the plough, scythe, wagon or cart until trained, and training off keeps them closed. The
   alternatives are to gate only with training on, or to lower the requirements. The test files now give their
   smiths and joiners strength 1.1 to 1.3 to stay on the intended path.
2. **Movement intensity.** Walking trains stamina by the step cost x 0.12 x gap (see Limits). Should walking train at all,
   or only deliberate work?
3. **Contest training.** Should a contested push (Phase 029) train strength, as a strength task?
4. **Endurance above 1.0.** Should sleep restore to effective stamina instead of the absolute `rest_cap` 1.0?

## Follow-ups

- Phase 046 (detraining and ageing of stats) can read `str_train` and `sta_train`; this phase does not decay them.
- The balance model's stamina line could count training and the larger capacity.
- Git: the other session committed some of its files between my first `git status` and this one (for example
  `docs/FEATURE_PHASES.md` and `bigville/api.py` are no longer modified). The end status is in `git_status_end.txt`.
  Stage this phase with `git add -p` for `worlds/bigville_world.py`, because the `"food"` flag and
  `resident_plan_from_context` hunks are still uncommitted there and belong to the other session.
