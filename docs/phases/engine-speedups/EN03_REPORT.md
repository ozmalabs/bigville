# EN03 — Turn-batched rule resolution

Status: complete, 8 November 2026. Phase EN03 of
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md).

- Base commit: `44f3fb142edff3e82d123047d79523dc0f5df965`
  (branch `engine-speedups`, EN02 applied; no EN03 changes).
- Host: contended Linux host, 16 CPUs, `/proc/loadavg` `15.22–19.83`
  before/during the measurements. A full suite was also active for part of the
  run. Absolute milliseconds are noisy; call counts and the size of the
  `commit` reduction are the stable signals.
- Comparison scenario: `tools/profile_engine.py`,
  `tools.benchmark_tick_graph.build_scenario(size)`, 2 turns, seed 305000,
  `--affordance-mode lazy --snapshot-mode on_demand`, serial executor. EN02's
  on-demand snapshot is used so `finish` is not hidden behind report work.

## Batch semantics

`rule_batching="action"` is the default and is unchanged: a primitive action's
rule sweep runs immediately.

`rule_batching="turn"` adds an opt-in world scope:

- `BigvilleWorld._rule_batch_depth` and `_rule_batch_pending` are ephemeral
  instance fields. Both are listed in `bigville/world_persistence.py`'s
  `_EXTERNAL_FIELDS`; a restored world constructs fresh defaults (`0` /
  `False`).
- `BigvilleWorld.batch_rules()` is a re-entrant context manager. It increments
  the depth on entry and decrements it on exit. Only the outermost exit runs a
  sweep, and only when one is owed. Exceptions propagate unchanged; the depth
  is always balanced. An exception inside the body leaves `pending` set rather
  than swallowing the exception or running a sweep in a `finally`.
- `_run(*, force=False)` returns immediately and sets `_rule_batch_pending` when
  it is called without `force` inside an open batch. Otherwise it runs the
  existing passes and clears the pending flag.
- Primitive actions call `_request_rule_sweep()`. In action mode it is exactly
  `_run()`; inside a batch it only records that a sweep is owed, so the
  measured `_run` count is the number of *actual sweeps*, not O(actions)
  deferred requests. `_run` keeps the same guard for any direct caller.
- `resolve_actor_turn()` calls `_run(force=True)`. This is the finish boundary's
  one authoritative sweep.
- `world.rules_pending` is a read-only debug check: `False` after a settled
  turn, `True` while a batch still owes its sweep.
- `world.tick()` stays outside the batch and still runs its own two passes.

A checkpoint while a batch is open (or while a sweep is owed) is rejected in
`save_world_checkpoint` with `ValueError("cannot checkpoint Bigville during an
open rule batch")`.

## Game option

`BigvilleGame` and `create_game` accept `rule_batching` in
`{"action", "turn"}`, default `"action"`. Invalid values raise `ValueError`.
The option is a plain session choice; there is no `"auto"` resolution in this
phase.

In turn mode the game wraps the turn's joint resolution, actor commit and finish
boundary in one `world.batch_rules()` scope. `_apply_turn` and
`_resume_suspended` also open the same re-entrant scope, so direct callers and a
resumed contest turn get the same semantics. `_finish_turn` calls
`resolve_actor_turn()` (forced) before map-memory learning, continuation
activation and the optional snapshot. If `pass_period()` changed the world at a
period boundary and owed a sweep, `_finish_turn` settles that sweep too, before
continuations and the snapshot read world state. That keeps a period turn
consistent with action mode; normal turns still run only the tick passes plus
one finish sweep.

Serial, threaded and partitioned commits all share the world instance and the
batch depth. Worker units only set the pending flag; the main thread runs the
single finish sweep.

## Audited `_run()` call sites

The historical 21 call sites are now: `resolve_actor_turn` (forced,
authoritative), two `tick` passes (outside the batch), and 18 primitive sites
that request a deferred sweep.

| call site | immediate effect | deferred-audit result |
|---|---|---|
| `move_actor` | adds an `Effort` node; body stats/energy update | final sweep applies the same depletions; a later action in the same turn reads pre-sweep stats until finish. Decisions are already frozen for the turn. |
| `pass_period` | period metabolism, decay, ecology, infrastructure | `_finish_turn` settles it immediately after `pass_period`, before continuations/snapshot. |
| `water_crop` | sets crop `thirst=0` itself; sweep settles the crop | safe: the adapter's return reads the attribute it already wrote. |
| `deliver` | unloads merchant stock | final sweep performs the same stock bookkeeping; later actions can see pre-sweep condition only. |
| `fill` / `empty` | arms a container transfer | final sweep applies the transfer; later actions in the turn see the pre-transfer contents. |
| `do` | opens an instant job; sweep completes it and consumes inputs | the job completes at the finish sweep instead of during the action. This is the most ordering-sensitive primitive: two actions using the same input in one turn can diverge. |
| `start` | opens a timed job | timed jobs do not advance during commit (`_job_tick_armed` is false); only job/body bookkeeping defers. |
| `tick` (two calls) | world time, jobs, sleep, metabolism | outside the batch; unchanged. |
| `use_tool` | arms one tool use | a single use defers and the finish sweep consumes one use. A multi-use call forces a sweep per use so `times=N` is not collapsed into one. |
| `repair_tool` | arms a repair | final sweep restores condition and clears the flag. |
| `dye_garment` | arms dyeing and writes the colour | final sweep consumes the dye; the adapter's return already reads the colour it wrote. |
| `wear` / `take_off` | writes protection attrs and the wears edge | final sweep applies protection; later actions can see pre-sweep protection. |
| `expose` | sets town cold/wet | final sweep applies each resident's chill/soaked; later actions can see pre-sweep exposure. |
| `_spend_attempt_stamina` | adds an `Effort` node | final sweep applies the stamina spend; a later action can read pre-spend reserve. |
| `_enact_carry` (joint) | moves the load/carriers, queues effort and strain | final sweep applies body effects; joint outcomes depend on membership, not on the sweep. |
| `_contest_spend` | adds an `Effort` node | final sweep applies contest stamina costs. The contest itself computes its sides before spending. |
| `rest` | adds a `Rest` node | final sweep recovers stamina. The game's `_rested` ignores the primitive's return value; a direct `world.rest()` inside a batch would return pre-rest reserve. |

No call site is a silent no-op: every deferred request sets the owed-sweep flag
and the finish boundary (or the outer batch exit) settles it.

## Tests

```bash
python3 -m pytest -q tests/test_engine_rule_batching.py -p no:cacheprovider
# 15 passed in 1.44 s

python3 -m pytest -q tests/test_engine_rule_batching.py \
  tests/test_engine_snapshot.py tests/test_engine_speedups.py -p no:cacheprovider
# 37 passed in 2.11 s

python3 -m pytest -q tests/test_tick_snapshot.py tests/test_lazy_*.py -p no:cacheprovider
# 122 passed, 1 skipped in 197.49 s

python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_phase029_contest.py \
  tests/test_phase047_joint_actions.py tests/test_bigville_world_persistence.py -p no:cacheprovider
# 68 passed, 1 failed in 83.59 s
# The failure is the timing threshold in
# test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical
# (0.83–0.91 of sequential instead of <0.75). It reproduces unchanged on a
# pristine `git archive HEAD` copy at base commit 44f3fb1 (ratio 0.83), so it is
# a pre-existing host-load timing failure, not an EN03 regression. The other 68
# tests pass.
```

`tests/test_engine_rule_batching.py` covers:

- 3 actors over 3 turns: action mode `_run` sweeps per turn are `[6, 6, 6]`
  (3 actions + 2 tick + finish); turn mode is `[3, 3, 3]` (2 tick + one finish
  sweep). Totals 18 vs 9.
- a turn still advances exactly one turn, applies a valid move, records a
  refused move as `False`, advances the refusal counter and leaves
  `rules_pending` false;
- a movement/body-stats turn changes energy;
- a sawpit job starts through the plan path (`work` → timed `start`) and
  advances on the next turn;
- a stock/decay turn with `ticks_per_period=1` rots bread and settles both the
  finish sweep and the period sweep;
- a rest turn raises stamina reserve;
- a contested/waiting take, then a resumed yield, both in turn mode;
- a joint carry turn is one finish sweep (3 total) and still moves the crate;
- serial, threaded and partitioned executors all complete with every action
  applied and no pending sweep;
- a checkpoint outside a batch succeeds and its `world.json` has neither batch
  field; a checkpoint inside an open batch is rejected;
- nested batches run exactly one `_resolve_jobs` pass on the outer exit;
- the option defaults to `"action"` and rejects invalid values.

```bash
python3 domains/bigville_entities.py
# ERRORS (0), WARNINGS (0), 95 INFO entries
```

## Behaviour comparison — action vs turn

Same autonomous simple backends, `affordance_mode=lazy`, default snapshot mode
in the evaluation tool. Both modes produced identical per-turn step records
(applied/refused, actions, survival, health/hunger/energy) on every run:

| scenario / seed | turns | mode | proposed | applied | refused | alive | hunger mean | energy mean | health mean | work | handovers | improvised jobs | accidents | wall s |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| small / 305000 | 12 | action | 36 | 35 | 1 (`exhausted`) | 3 | 0.196233 | 8.546667 | 1.0 | 0 | 0 | 0 | 0 | 0.779 |
| small / 305000 | 12 | turn | 36 | 35 | 1 (`exhausted`) | 3 | 0.196233 | 8.546667 | 1.0 | 0 | 0 | 0 | 0 | 0.795 |
| town100 / 305000 | 8 | action | 800 | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 100 | 0 | 1 | 0 | 23.77 |
| town100 / 305000 | 8 | turn | 800 | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 100 | 0 | 1 | 0 | 17.19 |
| town100 / 305001 | 8 | action | 800 | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 100 | 0 | 0 | 0 | 23.74 |
| town100 / 305001 | 8 | turn | 800 | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 100 | 0 | 0 | 0 | 17.45 |

- **No divergence observed** in these scenarios, at final state or in any
  per-turn step record. `move`/`work` mixes, refusals, improvised jobs,
  accidents and the attempt tallies are equal.
- Wall time fell about 27% on the 8-turn town runs; the 12-turn small room is
  too short for its wall time to be meaningful.

## Performance — action vs turn

Two samples, 50/100 residents, 2 turns, lazy, on-demand snapshot. Load average
was 15.2–19.8. `run/turn` counts actual `_run` sweeps.

Sample 1:

| size | mode | step ms | context ms | world tick ms | commit ms | finish ms | `_run`/turn | node/turn | near/turn | applied/turn |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | action | 289.589 | 82.942 | 5.772 | 139.602 | 14.199 | 53 | 88,467 | 126 | 50 |
| 50 | turn | 165.340 | 77.528 | 6.232 | 15.415 | 16.454 | 3 | 26,642 | 126 | 50 |
| 100 | action | 947.364 | 208.579 | 8.710 | 558.026 | 45.758 | 103 | 298,551.5 | 253 | 100 |
| 100 | turn | 481.644 | 224.650 | 11.433 | 43.492 | 58.914 | 3 | 69,901.5 | 253 | 100 |

Sample 2 (reverse order):

| size | mode | step ms | context ms | world tick ms | commit ms | finish ms | `_run`/turn |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 50 | turn | 166.828 | 72.090 | 5.956 | 16.851 | 17.381 | 3 |
| 50 | action | 302.169 | 77.081 | 5.542 | 153.829 | 15.691 | 53 |
| 100 | turn | 464.987 | 208.897 | 10.504 | 51.444 | 49.421 | 3 |
| 100 | action | 949.008 | 184.827 | 10.034 | 556.986 | 49.571 | 103 |

Stable findings:

- `_run` sweeps per turn fall from `actions + 3` (53 / 103) to exactly `3`
  (two tick passes plus the finish sweep).
- Commit excluding finish falls by about 89% at 50 (139.6 → 15.4 ms) and 92% at
  100 (558.0 → 43.5 ms) in sample 1; sample 2 is equivalent (153.8 → 16.9,
  557.0 → 51.4).
- Total step falls by 43% at 50 and 49% at 100 in sample 1, and by 45% / 51% in
  sample 2. This is the combined effect of fewer rule passes and the
  corresponding node reads.
- Node reads per turn fall 70% at 50 (88,467 → 26,642) and 77% at 100
  (298,551.5 → 69,901.5). `actors_near` and `applied` are unchanged, as they
  should be.
- `finish` is not a like-for-like smaller number: in action mode the finish
  sweep only settles effects from the last action plus turn bookkeeping, while
  in turn mode the finish sweep applies every deferred action effect. The work
  moves from `commit` into `finish`; the total is what falls.
- `world.tick` is unchanged/slightly higher (5.5–11.4 ms), as expected: it is
  outside the batch and still runs its two passes.

## Divergences and limitations

- The observed scenarios showed no behavioural divergence, but turn batching is
  an ordering change by construction. Actions that read body/stock/container
  state earlier in the same turn can see pre-sweep state instead of the result
  of the preceding action. The most exposed primitive is instant `do`:
  completing a job at the finish sweep rather than during the action can change
  which later action wins a shared input. `move`/effort, contest stamina, tool
  wear, clothing/exposure and container transfers have the same class of
  intra-turn visibility difference even when the final state converges.
- The audited scenarios exercise the town's simple move/work/rest/sleep pattern.
  They do not establish equivalence for every recipe, container, clothing or
  combat permutation; downstream consumers that depend on intra-turn read-offs
  should be checked before turn mode becomes a default.
- A multi-use `use_tool(times=N)` deliberately forces a sweep per use. A turn
  containing one is therefore not the constant-3 case; this preserves the
  historical N uses instead of silently collapsing them.
- A period boundary legitimately runs two finish sweeps in turn mode (the
  authoritative action sweep and the period-effect sweep). Normal turns run
  three total `_run` calls; period turns run four. `world.tick`'s two passes are
  never batched.
- Checkpoints are rejected while a batch is open. That is stricter than the
  historical "actor tick or major dispatch" guard; a caller that checkpoints
  from inside a hook during an action commit now gets a clear error rather than
  a checkpoint with a half-applied turn.
- Measurements are single-host, in-process, under load ~15–20 with a full suite
  active. Absolute values should be re-measured on an idle host for EN05.
- `tools/profile_engine.py` gained `--rule-batching` (default `action`) and a
  batching column/field so the two modes can be compared directly. This is the
  only file changed outside the EN03 scope list, and it is measurement-only.

## EN05 recommendation

Keep `rule_batching="action"` as the default in this phase. Turn mode is a clear
performance win (`_run` 53/103 → 3, commit −89/−92%, step −43/−51%) with no
observed divergence on town100 seeds 305000/305001 (8 turns) or the 12-turn
small scenario. EN05 should re-test on an idle host and consider resolving
`rule_batching="turn"` for headless autonomous simple/cheap sessions (mirroring
the `"auto"` affordance/snapshot pattern), while leaving player, LLM and Ocelot
sessions on `"action"` until intra-turn read-off consumers are audited. If EN05
does not make it a default, it should at least document turn mode as the
recommended option for headless evaluation runs.
