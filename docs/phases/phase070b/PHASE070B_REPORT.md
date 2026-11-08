# Phase 070b: aimed strikes, injury that lowers capacity, disease loci, sleep debt, and a free glance

## Summary

Five user decisions, all implemented and tested in the physical layer. The entity self-test is at 0 errors and
0 warnings. The test_hamlet check is clean. The 60- and 200-turn simple village digests equal the Phase 071
digests, and no resident took located harm in either run. Two existing tests changed: one sleep-debt test was
rewritten for the new rule, and one chest test got a higher starting strength because an accident now leaves an
arm injury that lowers strength. The full suite (tests/ only) ends with 8 failures: 3 Ocelot tests the brief lists
as baseline failures, 4 TUI tests in `tests/test_phase057_tui.py`, and 1 timing test that passes alone (see Validation).

The LLM reply channel does not route a free glance (only `speak` is routed). That hand-off is open.

## Decision 1: aimed strikes

- `strike_begin` takes `plan["region"]`, an ANATOMY node. A non-string region is `malformed`. An unknown region is
  refused with `unknown_region` (a new REFUSAL_REASONS code, both packs) before any slot is used.
- `strike_resolve` calls `_strike_locus(pending, choice)`. With no region it returns None, and `harm()` draws from
  HARM_LOCUS as before. With a region the chance is `STRIKE_AIM.base + skill_weight x striker skill`, times
  `brace_factor` when the target resists or braces. The draw is `domains/interoception.draw(seed, "aim", attacker,
  target, turn)`. A hit gives the region as the locus. A miss gives None, and the table draws.
- The strike description (`major_actions.json`, both packs) names the region and says it goes in `params region`.
  The reply schema has no per-action param table, so `params` passes through to `major_action` unchanged.
- Values (APPROX, `STRIKE_AIM` in `world/interoception.json`): base 0.5, skill_weight 0.3, brace_factor 0.6.
- Not run: an aimed blow through a real LLM reply and `to_wire`. The path is covered by reading the code only.

## Decision 2: located injury lowers capacity

- `INJURY_EFFECTS` (APPROX): leg speed 1.0; arm strength 0.8; back strength 0.5 and stamina 0.5; chest strength
  0.3 and stamina 0.5; head strength 0.2 and stamina 0.2; floor 0.5. The factor is
  `max(floor, 1 - sum(weight x ledger value))`. The ledger is the plain harm amount at each locus, healing at
  `located_heal_per_tick`. The press boost is not counted.
- Hooks: `move_actor` divides the walking interval by the speed factor. `effective_strength` and `effective_stamina`
  multiply by their factor. The factor is exactly 1.0 with an empty ledger. Walking speed through
  `speed_factor()` (the exhaustion band) is not changed. That path also feeds contest, throw and intensity ceilings.
- Tests: `test_an_arm_injury_lowers_effective_strength_by_its_weight`,
  `test_a_leg_injury_slows_walking_and_the_slowdown_heals_back`,
  `test_a_leg_injury_lengthens_the_walking_interval`, and `test_an_empty_ledger_gives_every_capacity_factor_exactly_one`.
- Village: no resident took located harm in the 60- or 200-turn runs (see Validation), so the digests are unchanged.

## Decision 3: disease with a region

- `DISEASE` rows take an optional `locus`. `world._disease_locus(actor)` returns it, or None. The illness harm calls
  in `_illness_day` and `_daily_life_tick` pass it, so the harm lands in the ledger there. `body.locus_for()` makes
  the `illness` source feel from that place. The self-test checks that each DISEASE locus is an ANATOMY node.
- No existing row changed. The only pack disease is fever, which stays whole-body. No plain-sense cough exists to
  give a chest locus. HARM_LOCUS.illness is still the fallback.
- Test: `test_a_disease_with_a_locus_feels_and_harms_from_that_place` (a monkeypatched row, not in the pack).

## Decision 4: sleep debt in hours

- `BODY_RATES.sleep_need_hours`: infant 12, child 9, youth 8, adult 7, elder 7 (lower end of the NSF ranges,
  Hirshkowitz et al. 2015, doi:10.1016/j.sleh.2015.01.010 and doi:10.1016/j.sleh.2015.10.004). The mapping and the
  preschool gap are in the `_doc`. The Van Dongen et al. 2003 citation (Sleep 26(2):117-126) is in the `_doc` too.
- Per tick (tick_hours from TIME, 0.25 h): awake adds `tick_hours x need / 24`; asleep takes off
  `tick_hours x (24 - need) / 24`; floor 0. The read is `debt / (sleep_debt_read_nights x need)`, capped at 1, with
  `sleep_debt_read_nights` = 2.0 (APPROX).
- `sleep_debt_rise`, `sleep_debt_fall` and `sleep_debt_full` are removed. The checker reads the new keys.
- Measurement, 200-turn simple village (seed 305017, 200 world ticks = about 2.1 simulated days; `village_200_check.json`).
  Hours asleep per day across 100 residents: min 3.5, median 8.4, max 14.2. Sleep counts an asleep flag, including
  a collapse. At the end, 0 residents felt sleep debt after habituation; the raw read ranged 0.00 to 0.47. This
  window is short and starts at a fixed time of day, so these are not a stable daily figure.

## Decision 5: free glance

- `FREE_ACTIONS.glance` (both packs; `requires_target` true; a description, Phase 018). `ATTEND.glance_bonus` 1.0
  (one acuity step, which is one depth step at acuity_weight 1.0) and `ATTEND.glance_stamina_cost` 0.0 (APPROX).
- `world.free_action("glance", target=signal:N)` calls `_body_glance`. It is refused asleep or for a handle with no
  felt signal. It uses no major action and no tick. The glance keeps the attention the resident has and caps no
  other signal. It lasts until the next tick (`Body.tick` clears `state["glance"]`).
- `domains/attend_commands.parse_line("glance [N]")` returns `{"free_action": {"action": "glance", "target": ...}}`.
  The word is the `ATTEND.verb_aliases` entry `glance`.
- Phase 054 packet: the snapshot test passes and the fixture was not edited. The prompt packet does not change.
- Not routed from LLM replies. The reply schema has no free-action key, and `bigville/game.py` routes only `speak`
  (`free_action(actor, "speak", ...)` near line 783). Adding a route means a reply key and a game.py hunk. Left open.
- Visceral signals stay vague when attended, as the user confirmed. No code changed for them.

## Changes

New files:
- `tests/test_phase070b_body.py` (15 tests).
- `docs/phases/phase070b/` (this report, `village_check.py`, digests and sleep measurement, logs, status files).

Changed, mine only:
- `worlds/body.py`: `pack_tables` (strike_aim, injury_effects, tick_hours); `focus()` (glance); `locus_for()`;
  `start_glance()`; `tick()` (clears the glance); `sleep_need()`, `_sleep_step()` (hours rule);
  `WorldBackedBody.reads()` (sleep read); `WorldBackedBody.locus_for()`; `BodyMixin._disease_locus`,
  `_body_glance`, `_body_capacity_factor`, `_strike_locus`; `attention_report` (glances count).
- `domains/interoception.py`: `derive(..., locus_for=None)`; a glance keeps the attention (`keep_attention`).
- `domains/interoception_check.py`: `RATE_KEYS` (new sleep keys); `_opt`; `_check_phase070b`; the verb alias set.
- `domains/attend_commands.py`: the glance branch of `parse_line`.
- `tests/test_phase070_locus.py`: one test rewritten (see Changed numbers).
- `tests/test_phase050_resolution.py`: one test strength changed (see Changed numbers).
- `packs/*/world/free_actions.json`, `packs/*/world/major_actions.json`: glance entry; strike region wording.

Changed, shared files (other session's uncommitted hunks are left in place):
- `worlds/bigville_world.py`, by function: `move_actor` (the walking interval line); `effective_strength` (the
  return line); `effective_stamina` (the return, now multiplied by the injury factor); `_major_action_attempt` (the
  strike plan takes `region`); `strike_begin` (region check before the slot is claimed; `"region"` in pending);
  `strike_resolve` (`_strike_locus`, `result["locus"]`, `harm(..., locus=)`); `free_action` (glance dispatch, before
  the final raise); `_illness_day` and `_daily_life_tick` (`locus=self._disease_locus(name)` on the two illness
  harms).
- `domains/world_affordances.py`: `STRIKE_AIM` and `INJURY_EFFECTS` bindings after `ATTEND`.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: two manifest lines after `ATTEND`.
- `packs/bigville/world/interoception.json` and `packs/test_hamlet/world/interoception.json`: the whole file was
  re-serialised with `json.dumps(indent=2)`, which reproduces the committed bytes. The data is the same except my
  edits: BODY_RATES sleep keys and `_doc`; ATTEND `glance_bonus`, `glance_stamina_cost`, the `glance` alias; new
  tables `STRIKE_AIM` and `INJURY_EFFECTS`. The other session's `childbirth` and `neglect` HARM_LOCUS rows are kept.
  My BODY_RATES `_doc` edit lies within about 3 lines of their hunk (lines 472 to 477).
- `packs/*/world/refusal_reasons.json`: `unknown_region` inserted before `attending`. Their `infant` code is untouched.

## Validation

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Saved to `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0). Saved to `check_test_hamlet.txt`.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)". No seed changed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase070b_body.py`: 15 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase070_locus.py`: 22 passed.
- `python3 -m pytest tests/test_phase013a_packs.py`: passed after reformatting `interoception.json` (first run failed
  on that file's bytes).
- Full suite, final: `timeout 7200 python3 -m pytest -q -p no:cacheprovider tests -rf` gives
  **8 failed, 2371 passed, 6 skipped** (`full_suite_final.log`). The failures:
  - 3 Ocelot tests the brief lists as baseline failures (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`):
    `test_bigville_ocelot_communication.py`, `test_mixed_ocelot_checkpoint_parity.py`, `test_mixed_ocelot_village.py`.
  - 4 in `tests/test_phase057_tui.py` (`test_over_http_*` and `test_the_server_refuses_a_bad_reply...`). With my
    capacity hook disabled in-process, and with `glance` removed from FREE_ACTIONS in-process, they still fail. The
    server and TUI files and the reply intensity check are the other session's uncommitted work. I did not confirm
    these at HEAD.
  - 1 in `tests/test_phase055_concurrency.py` (a timing comparison). It failed under load and passed when run alone.
  - I ran `pytest tests` only. The `docs/phases/phase044` and `phase045` copies of the other session's tests have
    the same basenames as `tests/` files and break collection of the default run.
- Earlier run of the same suite (`full_suite.log`, before the two fixes below): 10 failed, 2369 passed. The extra
  failures were `test_phase013a_packs` (layout of `interoception.json`, fixed) and `test_phase050_resolution`
  (broken chest, a changed number, below).
- Village digests (`village_check.py`, simple backend, town100, seed 305017; same digest method as
  `docs/phases/phase070/compare_digest.py`):
  - 60 turns: digest `f334f71e...` equals `docs/phases/phase071/digest_60_new.json`. Deaths 0. Residents ever
    injured 0.
  - 200 turns: digest `eadc65c6...` equals `docs/phases/phase071/digest_200_new.json`. Deaths 0. Residents ever
    injured 0.
  - The digests cover the working tree, which includes the other session's uncommitted changes.

## Changed numbers and tests

- `tests/test_phase070_locus.py::test_chronic_short_sleep_builds_a_debt_that_a_full_night_balances`: rewritten.
  Old: debt rises by `sleep_debt_rise` per awake tick, falls by `sleep_debt_fall` per asleep tick; 1/3 asleep holds
  it; 1/4 asleep leaves `72 x rise - 23 x fall`. New: hours against need. 7 h a day holds 4.0 at 4.0. 6 h a day adds
  1.0. No sleep adds 7.0. 10 h asleep pays 3.0 back. The read is 0.5 at 7 h of debt and 1.0 at 40 h. Reason: the
  rule was replaced, as the brief asks.
- `tests/test_phase050_resolution.py::test_a_broken_chest_spills_its_contents_on_its_cell`: strength 3.0 -> 4.0.
  Reason: the first strain's accident harm lands on the arm (ledger 0.2 to 0.3), and the arm factor (0.84) makes the
  smash fail in 400 attempts at 3.0. At 3.2 and 4.0 the chest breaks within 6 attempts. The assertions are unchanged.
- The 60- and 200-turn village digests and the health, starvation and strike numbers are unchanged.
- Sleep: `BODY_RATES.sleep_debt_full` and the old sleep keys are gone; the checker reads the new keys.

## Limits

- Walking speed is tested as the step cooldown of one move and as the factor. The village has no located injury in
  60 or 200 ticks, so no digest exercises it.
- The aimed-strike chance is APPROX and untested in a village. Only the stateless draw, the brace reduction and the
  unknown-region refusal are unit-tested.
- The glance is not reachable from an LLM reply. It is reachable from `world.free_action` and `parse_line`.
- Sleep measurement covers about two simulated days (200 ticks), not a settled daily pattern.
- ATTEND's `_doc` does not yet describe the glance. Also not edited: `worlds/body.py` docstring about the glance.
- The TUI (`bigville/tui`) was not edited. It does not show the glance and does not use `parse_line`'s free-action
  result.
- Checkpoint: the new state (`glance`, `counts.glances`, `sleep_debt` in hours) is plain values in
  `world.embodiment`. `body.dump()`/`load()` carry it. `game_persistence.py` and `world_persistence.py` were not
  checked.

## Open questions

- Route the glance from LLM replies? That needs a reply key for free actions and a game.py hunk next to the `speak`
  route. Decide whether the LLM should have it at all.
- The TUI should show the glance and the aim words. Hand-off to the TUI session.
- Walking slowdown through `speed_factor()` (contest, throws, intensity ceilings) is left out. Confirm.
- Injury weights and the 0.5 floor are APPROX. Confirm the values before any village run that injures residents.
- The preschool sleep need (10 to 13 h) has no LIFE_STAGES row, so `child` uses the school-aged 9 h. Confirm.

## Deviations from the brief

- The full suite is run over `tests/`. The default `pytest` collection also reads the other session's copies under
  `docs/phases/phase044` and `phase045` and fails with an import-file mismatch.
- The brief's "Programme C" reference in the standing rules was resolved to Programme F, as the phase file says.
- `packs/*/world/refusal_reasons.json`, `pack.json` and `interoception.json` are shared with the other session's
  uncommitted changes. My hunks are described above, by line area and function.
