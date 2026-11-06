# Phase 029: contested actions, reaction turns and taking

## Summary

`take` is now a physical contest between two residents on one cell. The attacker's take claims its major
action. The holder may then react (resist, brace, yield or evade) if it is alive, awake, aware of the taker and
fast enough. The world computes forces from strength, size, life stage and the exhaustion step (Phase 024),
and skill enters through a technique multiplier. The outcome is one of completed, dropped on the cell, held or
redirected. Costs are stamina. Nothing is random, and no ownership, crime or law is attached.

The game calls the holder's optional `react(context)` method from the step's application loop. A human holder
makes `step()` return `waiting`, and the next step resumes the turn. A backend without `react` is recorded as not
reacting. The cheap backend has a fixed reaction policy. Ocelot and LLM adapters have no `react` and are not
changed.

Self-test: 0 errors, 0 warnings (bigville and test_hamlet). Full suite: 968 passed, 2 skipped, 3 failed. The 3
failures are the Ocelot adapter tests that also fail at baseline (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`).

## Changes

### Pack data (both packs unless noted)

- `world/contest.json` (new): table `CONTEST`. Every value and its APPROX status is in the `_doc` of the bigville file.
- `population/size.json` (new): table `SIZE`, drawn per person.
- `pack.json`: manifest entries for `CONTEST` and `SIZE`.
- `world/major_actions.json`: action `take` (kind `contest`, with description).
- `world/refusal_reasons.json`: codes `held`, `evaded`, `dropped`.
- `world/handovers.json`: kinds `take` and `yield`.
- `world/actor_defaults.json`: `body.size` = 1.0.
- `frames/skills.json`: `fighting` (kind general, learning physical).
- `frames/skill_clusters.json`: cluster `combat` (metaskill `toil`, skills `fighting`).
- `frames/knowledge.json`: topic `fighting`, so the knowledge check links the skill.
- bigville only, `frames/trade_skills.json`: `constable` now exercises `policing` and `fighting`.
- bigville only, `frames/skill_affinity.json`: closeness pair `fighting`–`policing` 0.4 (APPROX).
- test_hamlet only, `frames/metaskills.json`: metaskill `toil` (copied from bigville; the hamlet combat cluster needs it).
- test_hamlet only, `frames/trades.json` and `frames/trade_skills.json`: trade `constable` (`building` null,
  `site` "square", `tools` [], `base_skill` 0.7), exercising `fighting`. Added so the hamlet's `fighting` skill is
  exercised, which keeps its self-test at 0 warnings. See Open questions.
- `tools/export_pack.py` was run for both packs. It rewrote no other files.

### Code

- `domains/world_affordances.py`: `CONTEST = _PACK["CONTEST"]` (new 2 lines).
- `domains/population.py`: `SIZE = _PACK["SIZE"]`; `draw_size(rng, age)` (new); `draw_person_capacities` returns
  `size`, drawn last, after limitations. The earlier draws are unchanged.
- `domains/bigville_entities.py`: `_check_contest` (new function, called from `check_consistency`). It checks the
  CONTEST ranges, margin order, life stages, reaction options, the contest codes, the `take` and `yield` kinds,
  the `fighting` skill and cluster, and SIZE.
- `worlds/bigville_world.py` (my hunks only):
  - `__init__`: `self._contest = None`, `self._turn_start_positions = {}` (after `self._map_cells`).
  - import line 20: `NodeRef` added.
  - `set_capacities(..., size=None)`; `draw_capacities` passes the drawn size.
  - `add_actor`: body node gets `size`; `skill_levels`/`metaskill_levels` come from new `_founding_levels`.
  - New `_founding_levels` (before `draw_capacities`).
  - `_major_action_attempt`: the `take` branch (was a refusal, `unsupported`) now runs `take_begin` then
    `take_resolve` with no reaction. This is used when a caller enacts a take without a game.
  - New contest block before `_sleep_code`: `mark_turn_start`, `contest_pending`, `_contest_efficiency`,
    `_contest_share`, `_contest_side`, `_aware_of`, `_evade_cell`, `_contest_offer`, `take_begin`, `_contest_spend`,
    `_contest_log_practice`, `_contest_kind`, `_contest_move`, `_contest_drop`, `take_resolve`,
    `_contest_practice_after`, `_release_contest_slot`, `take_outcome`.
- `bigville/game.py` (my hunks only):
  - imports: `deque`, and `replace` from dataclasses; module constant `_WAITING`.
  - `__init__`: `self._suspended`, `self.contest_log` (deque, bounded by `CONTEST.log_limit`).
  - `step()`: rewritten. It resumes a suspended turn first. It calls `world.mark_turn_start()` before
    application, then `_apply_turn`. Behaviour of non-take responses is unchanged.
  - New methods after `step`: `_apply_turn`, `_resume_suspended`, `_finish_turn` (the old tail of `step`),
    `_is_take`, `_reaction_context`, `_waiting_for_reaction`, `_contest_choice`, `_settle_take`,
    `_report_take_outcome`, `_record_contest_witnesses`, `_log_contest`.
  - The other session's `record_action_outcome` block in `_apply_response` is not touched. My nearest hunk is
    about 90 lines from it.
- `bigville/backends/protocol.py`: comment describing the optional `react` method (no protocol change).
- `bigville/backends/human.py`: `react(context)` (queued reaction or `waiting`), `submit_reaction(response)`,
  and separate `_reactions` queue.
- `bigville/backends/cheap.py`: `DeterministicBackend.react` (fixed policy: resist, then brace, then yield,
  whichever is offered).
- `tests/test_phase029_contest.py` (new, 24 tests).

### Design

Pending contest. `take_begin` claims the attacker's slot (the Phase 020 claim) and stores a plain dict on
`world._contest`. It holds forces, the target's reaction offer, witnesses, and the slot to release. `take_resolve`
takes the reaction and returns `(applied, reason)`. The caller publishes the outcome with `take_outcome`.

Reach. The taker and holder must share a cell, the same rule `give` uses. Witnesses are awake residents on that cell.

Forces and skill. Force = (strength + trained strength) x health x size^2 x life-stage factor x exhaustion step
factor (1, 2/3, 1/3, 0). A side's score is force x (1 + 2.0 x effective fighting skill). The attacker always
brings its full force. A passive holder brings grip (0.5) x force. A resisting holder brings full force. A
bracing holder brings grip x force with technique.

Outcome. Margin m = (attacker score - holder score) / (sum). m >= 0.2: completed. 0.05 <= m < 0.2: dropped
on the cell (coin cannot fall, so it is held). Otherwise held. If the holder wins decisively (m <= -0.2), it
reacted, and its skill exceeds the attacker's by 0.3 or more, the outcome is redirected (held, and the attacker
pays `overextend` x base_cost x its share extra).

Costs. A side pays base_cost (0.2) x cost share, where cost share = min(1, load / own force) x efficiency, and
efficiency = 1 - 0.8 x skill. Load to the attacker is the holder's brought force. Load to the holder is the
attacker's full force. A cost share below 0.25 is free. A resist or brace whose cost share is at least 0.5 uses
the holder's major action, unless the holder is already acting, in which case the reaction is late.

Reaction. A target reacts when it is alive, awake, and aware. Aware means the attacker stood within the sight
range (`HEARING.sight_range`, 7) at the start of the turn. Reaction score = holder's resist score x situation,
where busy (has a timed job) = 0.7 and overloaded = 0.8. The attacker's initiative is its resist score. A
reaction score at or above initiative gives every option (resist, brace, yield, evade, if a neighbouring walkable
cell exists). Between 0.5 x initiative and initiative it is late: yield and brace only, with a 0.75 penalty on
the holder's score. Below that there is no reaction.

Yield completes as a give, with handover kind `yield`, and costs nothing. Evade moves the holder to the first
sorted walkable neighbour and voids the take (reason `evaded`). Completed takes record handover kind `take`.

Turn suspension. The game's `step()` returns `waiting` with the reaction prompt. The turn's remaining responses
are kept on `game._suspended`. A later `step()` asks the holder again and continues. The decision loop is not run
again on resume.

Practice. Each resolved contest in which the holder answers (not yield) logs 5 minutes of fighting for both
sides, in the existing `skill_practice` log. It consolidates at period end (Phase 012).

Take on an item. A discrete item (for example a knife in the holder's hand) goes through the give path with kind
`take`. A dropped item would leave the holder's hand and land on the cell. That path is implemented but no test covers it.

### Data and sources

No source in the repository gives any figure below. All of them are APPROX, and each is marked in its pack `_doc`.

| Value | Table | Value | Basis |
|---|---|---|---|
| base_cost | CONTEST | 0.2 | APPROX, model choice (stamina units are reserve fraction) |
| grip | CONTEST | 0.5 | APPROX |
| technique_weight | CONTEST | 2.0 | APPROX; chosen so a 0.9-skilled light holder beats a heavier unskilled taker decisively |
| min_efficiency | CONTEST | 0.2 | APPROX |
| trivial_below / slot_above | CONTEST | 0.25 / 0.5 | APPROX |
| decisive_margin / narrow_margin | CONTEST | 0.2 / 0.05 | APPROX |
| redirect_gap / overextend | CONTEST | 0.3 / 0.5 | APPROX |
| reaction_floor / late_penalty | CONTEST | 0.5 / 0.75 | APPROX |
| busy_factor / overloaded_factor | CONTEST | 0.7 / 0.8 | APPROX |
| size_exponent | CONTEST | 2.0 | APPROX (force scales with the body's cross-section) |
| life_stage_force | CONTEST | infant 0.2, child 0.8, youth 0.95, adult 1.0, elder 0.85 | APPROX |
| baseline_level | CONTEST | 0.1 | APPROX (every resident's fighting level at founding) |
| practice_minutes / log_limit | CONTEST | 5 / 500 | APPROX |
| size mean_by_age, sd, floor | SIZE | 0.5 (<12), 0.8 (12-17), 1.0 (18+); 0.07; 0.4 | APPROX (no height data in the repository) |
| fighting-policing closeness | skill_affinity | 0.4 | APPROX |

### Scenario numbers (computed by the implementation, `tests/test_phase029_contest.py`)

| Scenario | Holder reaction | Outcome | Attacker cost | Holder cost |
|---|---|---|---|---|
| Strong (strength 1.3) takes from weak (0.7), both unskilled | late (yield or brace only); a resist is not offered, so the hold is passive | completed | 0.000 | 0.184 |
| Weak (0.7) takes from strong (1.3), resist | resist | held | 0.184 | 0.099 |
| Light (size 0.9, fighting 0.9) vs heavy (1.15, unskilled), resist | resist | redirected, held | 0.184 | 0.056 |
| Same, holder unskilled (effective skill 0) | late; a resist is not offered, so the hold is passive | completed | 0.061 | 0.200 (full share) |
| Child (size 0.6, reserve 0.15) grabs healthy smith, resist | resist | held | 0.184 | 0.000; smith's major action unspent |
| Same child, smith at reserve 0.25 (second band) | resist | held | 0.184 | 0.053 |
| Equal unskilled residents, resist | resist | held | 0.184 | 0.184 |
| Yield | yield | yielded (give, kind `yield`) | 0.000 | 0.000 |
| Evade | evade | evaded (void) | 0.000 | 0.184 |

Passive holders, with no reaction, pay the full push on their stamina. A passive hold also loses to a stronger
taker.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0); WARNINGS (0) (`selftest_bigville.log`) |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0); WARNINGS (0) (`check_hamlet.log`) |
| `python3 -m domains.check` | exit 0 (bigville) |
| `python3 tools/generate_seeds.py` then `--check` | regenerated; check exit 0, "match pack 'bigville' (31 files)" (`seeds_check.log`) |
| `write_cast_seed` to a temp path, compared with `seeds/bigville_cast100.json` | byte-identical; founding cast unchanged |
| `python3 tools/export_pack.py` (bigville and test_hamlet) | normalised; no other files touched |
| `pytest tests/test_phase029_contest.py` | 24 passed |
| `pytest` on test_phase004/009/011/013a/013b (hamlet self-tests, pack bytes) | 113 passed after the hamlet fix |
| Full suite, baseline before edits (`baseline_pytest.log`) | 944 passed, 2 skipped, 3 failed (Ocelot) |
| Full suite, final (`full_pytest.log`) | 968 passed, 2 skipped, 3 failed (the same 3 Ocelot tests). 944 + 24 new |

Mid-phase failures, both fixed. First full run: 4 hamlet tests failed, because `fighting` was unexercised in
test_hamlet (one warning). Fixed by the hamlet `constable` trade. A second issue (an item node reference rebuilt
from a plain int) was found by the held-item test and fixed in `_contest_kind`.

Git status: start (other session's uncommitted files, recorded in the supervisor's list) and end
(`git_status_end.txt`). I did not stage, commit or revert anything.

### Test changes (existing tests)

None. No existing test was edited. Every new test is in `tests/test_phase029_contest.py`.

## Limits

- Reach is one cell, the same as `give`. The brief's "within reach" is taken as the same cell. The existing
  `not_in_reach` text says "or one step away", which `give` does not implement, so that text is not accurate
  for `give` or for `take`.
- Unaware. Awareness uses the cells at the start of the turn. In a turn, a taker cannot walk in and take
  (one major action), so a taker on the holder's cell is always seen when the holder is awake. The unaware
  case is covered by a test that overrides the start-of-turn snapshot. In play, the sleeping or collapsed
  cases (not awake) are the ones that actually occur.
- Coin does not fall on the cell (a narrow margin on coin is held).
- A dropped discrete item is implemented but untested. Dropped stock is tested.
- Physical object snapshots (Phase 028 `_record_physical_changes`) are not taken for `take`. Witnesses get a
  `contest` physical event instead, with the outcome and no content.
- Stamina is spent through an Effort node followed by `_run()`, the same way `rest()` does it.
- Cheap backends never propose a take. Village runs therefore see no contests. The fighting baseline and size
  do change them (see Changed numbers).
- Force uses effective strength (`(str_base + str_train) x health`) and does not model stamina reserve as a
  separate trait. Reserve enters through the exhaustion step only.
- Not run: the 100-resident town and any village run. Balance under contests is unmeasured.
- `take` is now a major action, so any Ocelot or LLM prompt that lists `MAJOR_ACTIONS` now includes it.

## Changed numbers (100-resident village, not run)

- Every founding resident starts with `fighting` 0.1 (`skill_levels`). Their `toil` metaskill is at least
  0.6 x 0.1 = 0.06 (`META_FROM_SKILL` 0.6). Toil-cluster skills (labour, water_drawing, sanitation) can gain a little
  transfer, and practice speed rises slightly. Not measured.
- Constables get `fighting` at the trade level (0.7 with the default skill).
- Body size is drawn per person. The founding cast seed does not hold it, so the cast is unchanged (verified bytes).
- `bigville/seeds/gen_skills.json` changed (+11, -1 lines): the new skill, cluster and trade entries.

## Open questions

1. Hamlet's `constable` trade is a placeholder to exercise `fighting`. Its `site` ("square") is not checked
   against the hamlet map, and no hamlet job seeds it. Should hamlet get a policing skill and a job instead?
2. Persistence (other session's untracked `bigville/game_persistence.py` and `world_persistence.py`). The pending
   contest (`world._contest`, a plain dict) and the suspended turn (`game._suspended`) are not in any snapshot.
   A checkpoint taken while a human reaction is pending would lose the turn. The `contest_log` is not
   checkpointed either. Those files were not edited.
3. The game mirrors the foreign `record_action_outcome` call in `_report_take_outcome`, because a take does not
   pass through `_apply_response`. The other session may want one shared helper.
4. The `not_in_reach` description ("or one step away") disagrees with `give`'s reach. That is pre-existing and
   outside this phase.
5. Whether `take` should appear as a cheap-backend option (affordance). Not added, so village behaviour does not
   change through takes.

## Follow-ups

- Ocelot and LLM `react` adapters (out of scope, per the brief). Until they exist, those holders are recorded
  as `no_react_method` in `game.contest_log`.
- Strikes and injury (Phase 038) can reuse `take_resolve`'s margin and cost rules.
- Phase 033 (restraint) and Phase 034 (intoxication through effective skill) can read the same outputs.
