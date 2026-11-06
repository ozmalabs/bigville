# Phase 038: Strikes and injury

## Summary

A `strike` major action lets one resident hit another on the same cell with bare hands. It reuses the
Phase 029 contest: the blow's power is the attacker's score, the target's hold is its resist or brace
score, the reaction turn and the redirect rule are the take's, and stamina costs follow the take's rule.
Harm goes through `harm(target, amount, "violence")`, so a lethal blow records cause `violence`. A blow
is observed by everyone who can see the attacker (sight range and occluders, as speech is). The simple
backend has an optional trigger from the seeded `bv_trigger`, off by default.

Status: implemented; self-test clean; the new phase 038 tests pass (19). The full suite has one failure
caused by this phase (a prompt-packet snapshot that lists the action vocabulary), which needs a decision
(see Open questions). Seven other failures come from other sessions' work and are listed under Validation.
Nothing is committed.

## Changes

Files created:
- `tests/test_phase038_strikes.py` (19 tests).
- `docs/phases/phase038/PHASE038_REPORT.md`, `death_probe_before.log`, `death_probe_after.log`.

Files changed (phase 038 hunks only; the other sessions' uncommitted hunks in the same files were not touched):
- `packs/bigville/world/contest.json`: `CONTEST` gains `strike_harm` (0.1), `attack_cost` (0.2),
  `redirect_harm` (0.05), all APPROX. The `_doc` gains a STRIKES paragraph.
- `packs/test_hamlet/world/contest.json`: the same three keys and paragraph (it is a copy of the table).
- `packs/bigville/world/major_actions.json` and `packs/test_hamlet/world/major_actions.json`: a `strike`
  entry (kind `violence`, with a description).
- `worlds/bigville_world.py`:
  - `_contest_side`: a `power` key (the blow's strength without the exhaustion step). The other keys are
    unchanged; the take's values are numerically identical.
  - `take_resolve`: a dispatch to `strike_resolve` when the pending dict's action is `strike`.
  - `take_outcome`: an `action` keyword (default `take`).
  - New block after `take_outcome`: `contest_begin`, `strike_begin`, `_strike_witnesses`, `strike_resolve`.
  - `enact_plan`: `strike` is in the set that needs no affordance targets.
  - `_enact_plan`: a `strike` branch.
  - `_major_action_attempt`: a `strike` branch (a blow with no game, no reaction).
- `bigville/game.py` (all in the contest code, after the Tract B hunks at lines 720 and 824-870):
  - `_apply_turn`: contest routing through `_is_contest` and `world.contest_begin`.
  - `_is_contest`: new static method after `_is_take`.
  - `_reaction_context`: `by` reads `pending["by"]` (default `hand`).
  - `_settle_take`, `_report_take_outcome`: the action name is passed through (default `take`).
  - `_record_contest_witnesses`: a strike is recorded as action `strike`; takes are unchanged (`contest`).
- `bigville/backends/cheap.py` (all phase 038; `decide`'s goal and choice methods are not restructured):
  - Import of `CONTEST`.
  - `SimplePolicy`: `strike_trigger` (False), `strike_threshold` (1.0), `strike_desperation_gain` (1.0).
  - `__init__`: `self.grievances`.
  - `decide`: a three-line early return, after the unlock block, when `_strike_proposal` returns a target.
  - `react`: records the contest's actor as a grievance. Its choice is unchanged.
  - New method `_strike_proposal`.
- `domains/bigville_entities.py` (`_check_contest` only): the new keys in the expected list, the positive
  check for `strike_harm` and `attack_cost`, the non-negative check for `redirect_harm`, the `strike` entry
  in MAJOR_ACTIONS, and `violence` in HEALTH causes.

No existing test was changed.

## Design

Blow power: `force x (1 + technique_weight x skill)`, where force has no exhaustion step (see Deviations).
Hold: none when the target does not react (or yields); `resist` gives `force x (1 + tw x skill)`; `brace`
gives `grip x force x (1 + tw x skill)`; both times the late penalty if late.
Landed share: `(1 + m) / 2`, with `m = (power - hold) / (power + hold)`. An unprepared target takes the blow
in full. Equal force and skill, with a resist, lands half.
Harm: `strike_harm x intensity x weak x landed x power`, with `weak = min(1, reserve / attack_cost)`. The
harm is applied with `harm(target, ..., "violence")`, so the life-stage fragility applies. An average
unskilled adult's full blow is `0.1 x 1.2 = 0.12` of health.
Attacker's cost: the take rule with the passive grip as load (no load after `yield`), times
`intensity^k` (k from RESOLUTION, 1.5). A redirected blow adds the overextend cost.
Target's cost: only for `resist`, `brace` and `evade`, using the take rule with the blow's force as load.
Redirect: when the hold wins decisively (`m <= -decisive_margin`), the reaction is resist or brace, and the
target's skill exceeds the attacker's by `redirect_gap`. The target takes no harm. The attacker takes
`redirect_harm x intensity` as `violence`.
Evade: the target steps to an adjacent open cell. No harm. The attacker's swing stays on record and its slot is
not released.
Witnesses: living, awake residents within HEARING `sight_range` (Chebyshev distance) with no sight occluder on
the line. A world `strike` event is created and observed by them (`observed_event` edges). The game also
logs a per-turn physical event for each witness on the cell, as takes do.
Refusals: unknown or self target, a dead target (`wrong_target`), a target off the cell (`not_in_reach`), a
malformed intensity, a used slot (`slot_used`), and a sleeping or collapsed actor (the sleep codes). Stamina
never refuses a blow.
Intensity: clamped with `RESOLUTION.max_intensity x health` (see Deviations).

Simple backend trigger (off by default): a resident proposes a strike when its `strike_trigger` is set,
it holds a grievance against a person on its cell (recorded when it reacts to a contest that person made),
its energy is at least `attack_cost` (x 100, the seed's gate), and
`snap_pressure (0) + w_spite x 1 + hunger x strike_desperation_gain >= strike_threshold`.

## Validation

Commands and results (run from the repo root):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0).
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0).
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)".
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase038_strikes.py`: 19 passed.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase029_contest.py tests/test_phase050_resolution.py`:
  68 passed (run before the last two fixes; the full suite below ran after them).
- Full suite: `timeout 1500 python3 -m pytest -q -p no:cacheprovider --ignore=tests/test_bigville_ocelot_communication.py`
  (I ignored that one file, which is another session's untracked file):
  **1627 passed, 7 failed, 3 skipped** in 1164 s.
  - `tests/test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`: **caused by
    this phase**. The packet's system text is 9 characters longer (`"system": 4921` in the fixture, `4930` now)
    because `strike` is in MAJOR_ACTIONS. It passes when `major_actions.json` is at HEAD (checked on a copy of
    the live tree, twice). The fixture is `tests/fixtures/phase054_packet_snapshot.json`, which is outside this
    phase's write scope, so I did not change it.
  - `tests/test_phase057_tui.py`, four HTTP tests (`test_over_http_a_menu_row...`,
    `test_over_http_walking_to_a_known_place...`, `test_over_http_a_reaction_is_delivered_to_the_holder`,
    `test_the_server_refuses_a_bad_reply...`): **not caused by this phase**. They still fail on a copy with
    my game, world, cheap and pack-table edits reverted to HEAD. The failures are in the server and TUI path
    (`last_responses` is None; a bad reply returns 200).
  - `tests/test_mixed_ocelot_village.py` and `tests/test_mixed_ocelot_checkpoint_parity.py`: `ModuleNotFoundError:
    No module named 'worlds.bigville_ocelot_adapter'`. This is the baseline failure in the preamble.
- Death probe, `PYTHONPATH=. python3 /tmp/death_probe.py 192` (town100, simple backends, 192 ticks):
  before the edits `{"deaths": 0}`, after `{"deaths": 0}` (`death_probe_before.log`, `death_probe_after.log`).
  This is a 192-tick run, not a full village period sequence, and it is not a balance claim.

## Limits

- The numbers `strike_harm`, `attack_cost`, `redirect_harm` and the simple policy's threshold and gains are
  APPROX model choices. The seed `bigville_viol_act.json` gives no values. No source is cited.
- The tests check the arithmetic and the rules on two- and three-resident setups. They do not show a
  village where strikes happen, and no such run was made.
- The unarmed blow does not use TOOL_FIT or `hands_fit`. Phase 040's object strike will need a fit.
- The simple trigger's grievance memory (`self.grievances`) is backend state. Nothing checkpoints it, so a
  restored simple resident forgets its grievances. The Tract B checkpoint would need to read it.
- Reactions to a strike use the take's options. `evade`, `brace` and `resist` are the same as for takes.
  Only the simple backend's `react` (fixed policy) is wired. The Ocelot and LLM adapters do not react.
- Several people striking together (Phase 047) and striking with an object (Phase 040) are out of scope.
- Strike events are recorded as world events and as the game's physical events. Nothing records an offence.

## Deviations

1. **Blow power excludes the exhaustion step.** The take's force includes the exhaustion step, which is 0
   below `e_low` (0.15). `attack_cost` is 0.2. Using the stepped force, a blow at reserve 0.05 would be zero, not
   weak as the brief says. The blow uses `power` (no step). The step still raises the attacker's cost (a
   tired attacker pays the full share) and sets its reaction score. Tiredness weakens the blow through `weak`.
2. **Intensity ceiling excludes the speed factor.** With the speed factor, a blow below `e_low` would clamp to
   intensity 0, so nothing would land. The ceiling is `max_intensity x health`.
3. **The redirect's harm to the attacker is certain, not random.** The brief said "may be hurt". It is always
   `redirect_harm x intensity` on a redirect. Nothing in the rules is random.
4. The redirect test uses an unskilled sober attacker. The drunk effect is tested separately (through
   effective skill, a weaker blow).

## Open questions

1. **Decide the phase 054 snapshot.** Either regenerate `tests/fixtures/phase054_packet_snapshot.json` (a
   Tract B fixture; the change is the strike entry, so the packet now lists strike for LLM residents), or
   remove `strike` from MAJOR_ACTIONS (then the LLM cannot see the action, and the self-test check I added
   must go). I recommend regenerating the fixture.
2. Should the simple backend's grievances be checkpointed? It needs a Tract B change to the checkpoint encoder.
3. The exhaustion choice in Deviation 1 is mine. Please confirm it, or say which of the two effects should win.

## Concurrent work (not mine)

- `packs/bigville/world/prompt_packet.json` and `packs/test_hamlet/world/prompt_packet.json` gained a
  `thread` block during this phase. They were not modified when the phase started. I did not touch them.
- The other hunks in `worlds/bigville_world.py`, `bigville/game.py` and `domains/bigville_entities.py` belong to
  other sessions. Phase 038's hunks in those files are listed under Changes. `bigville/backends/cheap.py` and the
  four pack table files had no other session's changes, so all their differences are this phase's.
