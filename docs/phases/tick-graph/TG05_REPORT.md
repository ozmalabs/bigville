# TG05 — Parallel commit of independent effects

Base commit: `1901b2e` (TG04: effect intents and per-turn tick graph)

No file was staged or committed. The pre-existing untracked `.opencode/`
directory was not touched.

## Scope

TG05 adds an opt-in `executor="threaded"` commit path. The default remains
`executor="serial"` and keeps the historical serial loop byte-for-byte. The
threaded path is allowed to change internal graph node-id allocation order, so
equivalence is proved on the semantic oracle added here, never on node ids or
on the raw checkpoint digest.

Files changed:

- `bigville/runtime.py` — module-level graph lock.
- `worlds/bigville_world.py` — thread-local attempt state; event/utterance log
  lock and a locked utterance snapshot helper.
- `bigville/world_persistence.py` — exclude `_attempt_state` from checkpoints.
- `bigville/game.py` — executor option, component scheduler, physical-event
  append lock.
- `bigville/tick_trace.py` — semantic world oracle (default trace unchanged).
- `tests/test_tick_graph_executor.py` (new).
- `docs/phases/tick-graph/TG05_REPORT.md` (this report).

## Locking and thread-local design

### Canonical graph lock

`bigville/runtime.py` now has one module-level `threading.RLock`
(`_GRAPH_LOCK`). It guards `add_node`, `add_edge_unchecked`,
`remove_edge_unchecked`, `remove_node`, `set_attr`, `node`, `has_node`,
`has_edge`, `neighbours`, `in_neighbours` and `nodes`. The lock is re-entrant
because public helpers call one another (for example `load_seed_manifest` calls
`nodes`/`add_node`). It is module level, so it is never written into a
checkpoint or copied with a world. Checkpoint serialisation is deliberately
outside the lock, matching the phase instruction.

### Per-attempt state

`BigvilleWorld` now owns `self._attempt_state = threading.local()`. The
existing private names are properties over that object:

- `_outcome_open`
- `_refusal_code`
- `_major_dispatch`

Every existing assignment and read keeps working, but two residents' attempts
running in different threads can no longer see one another's open outcome,
refusal code or major-dispatch guard. `_actor_tick_in_progress` remains
instance-level as instructed.

`_attempt_state` is listed in `bigville/world_persistence.py::_EXTERNAL_FIELDS`:
it is session/thread state and is never checkpointed. A restored world
constructs a fresh `threading.local()` in its constructor.

### Event and utterance logs

`worlds/bigville_world.py` adds module-level `_EVENT_LOG_LOCK` around the
`len(log) + 1` key insertion in `create_event` and in `speak`. Without it two
concurrent writers could mint the same `event:N` key and silently drop a
record. `utterances_from(first_utterance)` returns a locked snapshot of the
utterance tail; `game._record_speech_witnesses` uses it so a worker cannot
iterate a dictionary while another unit appends to it. The serial path reads
the same nodes in the same order.

### Physical-event appends

`bigville/game.py` adds module-level `_PHYSICAL_EVENTS_LOCK`. Both
`_record_physical_changes` and `_record_speech_witnesses` hold it only around
the `_physical_events[observer].append(...)`. The lock is never held while
calling into the world. The TG03 `distance` lock is unchanged.

## Executor

`BigvilleGame` now has validated `executor` (`"serial"` or `"threaded"`) and
`executor_workers` (positive int, default 4) properties, accepted by the
constructor as well. The default is `serial`.

`_apply_turn` dispatches to `_apply_turn_threaded` only when all of these hold:

- `executor == "threaded"`;
- `start == 0` (a resumed turn stays ordered);
- `last_tick_graph is not None` (a disabled graph falls back to serial);
- no response in the turn is a contest (`take`/`strike`/`restrain`/`throw`),
  because a contest can suspend for a human reaction.

Otherwise the historical serial loop runs unchanged.

### Units and components

A unit that can move an object also declares a write on a `witness:<name>`
resource for the actor and every resident within one cell, whenever the world
holds physical objects. Those are exactly the observers whose
`_physical_events` list `_record_physical_changes` may append to. Two nearby
units that move different objects therefore share a witness resource and are
merged into one component instead of racing the same observer's event list.

One unit is one non-joint actor's major, speech and memory operations from the
TG04 graph. Joint members are skipped: `_resolve_joint_groups` has already
applied their joint act and their speech/memory before `_apply_turn`.

A unit's resource set is the union of the reads and writes of its operations.
Two units conflict when their sets share any resource. Components are built
with union-find keyed by resource, then emitted in turn order. A unit writing
`Resource("world", "global")` is unioned with every unit, so such a turn is one
global component and therefore serial.

One deliberate over-declaration: a unit containing a `speak` operation is
treated as a global writer. The TG04 pure graph declares only the utterance
log, but the world's `_speech_deliveries` reads every actor's position and
sight, the clock's light and the target's presence. Without this, a speaker and
a resident moving in the same turn produced different `target_seen` values from
serial. This costs parallelism on turns where anyone speaks; it is reported as
a limitation rather than hidden.

### Commit

Each component is submitted to a bounded `ThreadPoolExecutor` of
`executor_workers`. Actors inside a component run serially in turn order.
`_apply_unit` reproduces the serial block: `utterances_before`, the
object-witness `before` snapshots, `_apply_response_contained`, speech
witnesses and physical changes. The worker returns `(actor, result, error)`
and does not own the turn's result dicts. The main thread writes
`last_results` and `last_errors` in turn order, preserving the serial insertion
order (joint results/errors first, then non-joint actors in `order`).

Errors are contained per actor: `_apply_response_contained` still records the
actor's failure, and the main thread rebuilds `last_errors` consistently.
`_finish_turn` is called exactly once after every component has finished.

The graph is still built for every advanced turn. If
`tick_graph_enabled=False` while `executor="threaded"`, the turn falls back to
serial because there is no graph to schedule from.

## Semantic oracle

`bigville/tick_trace.py` gains:

- `semantic_world_state(world)` — normalises `world.export_state(event_tail=None)`:
  - drops the volatile `id` from `utterances` entries (it is the raw graph node
    id);
  - sorts `events`, `articles`, `editions`, `handovers`, `proposals`, `cases`,
    `animals`, `fences` and `enclosures` by canonical JSON;
  - keeps every other field of the export intact.
- `step_semantic_trace(game)` / alias `semantic_step_trace(game)` — the same
  turn fields as `step_trace`, with `world_sha256` over the semantic projection.

The default `step_trace`/`TurnTrace` behaviour, record shape and digest are
unchanged; `step_trace` was only split into a shared `_trace_fields` helper plus
the strict checkpoint digest.

Threaded equivalence is therefore **semantic**: proposals, results, errors,
continuations, actor/world observable state and counters must match. Node ids
and internal list insertion order may differ. The semantic projection is not a
claim that the canonical graph checkpoint is byte-identical.

Limits of the semantic oracle:

- It removes only the utterance node id. A future export field that embeds a
  graph node id or an allocation-order-dependent key must be added to the
  normalisation or the oracle will report a false divergence.
- It sorts the named log-like lists; other lists in the export (for example
  `speech_events`, `births`, `deaths`) keep their order. Those lists are not
  reordered by the current concurrent units in the tested scenarios, but a
  future action that writes them concurrently would need an explicit conflict
  or a normalisation rule.
- It hashes `world.export_state`, which includes derived report data. That is
  intentional: the report is an observable projection, but it also makes the
  oracle more expensive than the raw checkpoint for large worlds.

## Tests

`tests/test_tick_graph_executor.py` (9 test functions, 10 collected):

1. Serial vs threaded semantic traces match over 4 turns on `town100` seed
   305000 and on the small TG01/TG04 room; two serial runs are identical, so
   the serial TG04 oracle behaviour is unchanged. Same-thread semantic state
   and result/error equality are asserted without comparing node ids.
2. Independent `rest` units produce the same semantic world state without
   speech.
3. A sleep-wrapped `_apply_response_contained` records real concurrency:
   serial reaches a maximum of 1, threaded reaches greater than 1.
4. A `take` turn under `executor="threaded"` never enters the threaded commit
   path and matches the serial result/error state.
5. A joint turn is resolved before commit, enters the threaded commit once and
   matches serial.
6. `tick_graph_enabled=False` forces a serial fallback and records no graph.
7. Executor and worker options reject invalid values.
8. Twelve threads adding 200 nodes each produce unique ids, fill `1..2400` and
   leave `_next_id == 2401`.
9. A direct two-thread `_attempt` test proves each thread sees its own refusal
   code, dispatch guard and open outcome, both attempts publish, and the main
   thread starts fresh.

## Commands and results

```bash
python3 -m py_compile bigville/runtime.py bigville/game.py \
  bigville/tick_trace.py bigville/world_persistence.py \
  worlds/bigville_world.py
# OK

python3 -m pytest -q tests/test_tick_graph_executor.py -p no:cacheprovider
# 10 passed in 32.40s

python3 -m pytest -q tests/test_tick_graph_executor.py tests/test_tick_graph.py \
  tests/test_tick_snapshot.py tests/test_tick_trace.py -p no:cacheprovider
# 38 passed in 132.25s (0:02:12)

python3 -m pytest -q tests/test_phase055_concurrency.py \
  tests/test_phase029_contest.py tests/test_phase038_strikes.py \
  tests/test_phase047_joint_actions.py tests/test_bigville_world_persistence.py \
  -p no:cacheprovider
# first run: 1 failed, 87 passed in 55.22s
# isolated rerun of tests/test_phase055_concurrency.py: 6 passed in 43.59s
# full group rerun: 88 passed in 54.52s
```

Flaky timing observation: the first group run failed only
`test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`
at a speed-up ratio of 0.75 against its strict `< 0.75` threshold (sequential
10.32s, concurrent 7.76s). This is the same timing-only assertion TG04 already
recorded as flaky. No determinism, digest or result assertion failed. The test
passed alone (ratio 0.74) and the whole group then passed (ratio 0.71).

## Known limitations

- A turn containing any speech is committed as one global component. This is
  more conservative than the TG04 graph and reduces threaded parallelism for
  conversational turns; it is required because speech delivery reads global
  positions and light.
- The scheduler trusts the TG04 resource table. An action that mutates shared
  world state without declaring it can still race. The semantic tests are the
  guard: a divergence appears as a differing `world_sha256`, not as a node-id
  difference.
- Within a component the units run serially in turn order, but components have
  no ordering relative to one another. The world's rule sweep (`_run`) and
  global counters are not isolated by a separate world lock; the tested
  independent units (rests, sleeps and idle actors) remained equivalent. A
  future action with a non-commutative global sweep needs its own conflict or
  lock before it may be placed in a multi-actor threaded turn.
- Per-observer `_physical_events` list order is protected against corruption
  but not proven identical to serial ordering when two independent units both
  witness the same observer. Those records feed the next turn's context; the
  conservative speech component covers the main case.
- `executor`/`executor_workers` are constructor/attribute options on
  `BigvilleGame`; they are not yet exposed through `bigville/api.py`'s
  `create_game`, which was outside this phase's scope.
- The TG05 contest test proves the threaded commit is skipped for a `take` and
  that the autonomous result matches serial. A full human-reaction wait/resume
  cycle was not re-run on the threaded path here; the fallback condition is
  what keeps it ordered, and the existing Phase 029 contest suite covers the
  serial wait/resume behaviour.

## Handoff to TG06

TG06 can rely on:

- `executor="serial"` is still the default and the historical serial loop is
  unchanged; `tick_graph_enabled` and the TG04 oracle are unchanged.
- `executor="threaded"` is an observationally-equivalent opt-in for
  declared-independent actor units, with contests, resumed turns and missing
  graphs deliberately falling back to serial.
- `semantic_world_state` / `step_semantic_trace` compare a normalised
  node-id-free world projection. Use them for simultaneous-mode equivalence;
  keep `step_trace` for the strict checkpoint where node ids are expected to
  match.
- Before simultaneous semantics can widen concurrency, move the speech
  dependency into the graph's declared resources (or another explicit
  pre-commit read set) rather than keeping the scheduler's conservative global
  override.
- The graph lock, thread-local attempt state and event-log locks are
  independent of turn semantics and can stay in place for TG06.
