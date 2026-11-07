# TG06 — Simultaneous turn semantics (opt-in)

Base commit: `1b6d2ad` (TG05: opt-in threaded commit and semantic oracle)

No file was staged or committed. The pre-existing untracked `.opencode/`
directory was not touched.

## Scope and files

TG06 adds an explicit, non-default `turn_semantics="simultaneous"` mode. The
default `turn_semantics="sequential"` is unchanged and keeps the exact TG05
behaviour and trace digests.

Files changed:

- `worlds/tick_graph.py` — pure `Claim` and `resolve_claims`.
- `bigville/game.py` — option plumbing, item-claim detection, suppression in
  both commit paths, refusal publication.
- `bigville/api.py` — `create_game` pass-through options.
- `tests/test_tick_simultaneous.py` (new).
- `docs/phases/tick-graph/TG06_REPORT.md` (this report).
- `docs/design/TICK_GRAPH.md` — TG06 status row only.

## Options

`BigvilleGame` accepts:

```python
BigvilleGame(world, ..., turn_semantics="sequential", simultaneous_priority=None)
```

- `turn_semantics` must be `"sequential"` or `"simultaneous"`; any other value
  raises `ValueError`. It is also a validated property.
- `simultaneous_priority` is `None` or a callable
  `(game, actor, index) -> sortable`; a non-callable raises `ValueError`.
- `executor` remains independent. Simultaneous mode works with
  `executor="serial"` and with `executor="threaded"` /
  `executor_workers=N`.

`create_game(...)` accepts and passes through `turn_semantics`,
`simultaneous_priority`, `executor` and `executor_workers`; all previous
parameters and defaults are retained.

## Claim model

`worlds/tick_graph.py` now has:

```python
@dataclass(frozen=True)
class Claim:
    resource: Resource
    actor: str
    index: int
    priority: Any
```

and

```python
resolve_claims(claims) -> (winners, losers)
```

`resolve_claims` groups by resource, chooses the maximum by
`(priority, -index, actor)` and returns:

- `winners: {Resource: Claim}` for every claimed resource;
- `losers: {Resource: tuple[Claim, ...]}` only for contested resources, in
  deterministic priority order.

It has no world parameter and performs no mutation or engine import. Resource
iteration is sorted by the stable string form, so input order cannot affect the
result.

## Priority policy

The default priority is **higher `world.effective_strength(actor)` wins**. A
tie goes to the actor earlier in `turn_order`, and then to the lexicographically
larger actor id (the documented `max` order). `effective_strength` is
read-only, so the default policy cannot mutate the world. A custom callable
replaces the strength value and is combined with the same `-index` / actor-id
tie-breaks.

The requirement that priorities be mutually comparable is the caller's
responsibility for a custom callable; the built-in strength values always are.

## Simultaneous policy (first slice)

At the top of `_apply_turn`, before the serial/threaded branch and before any
response is applied, simultaneous mode:

1. Uses `last_tick_graph`, or builds a throwaway graph when the TG04 flag has
   disabled graph storage. In the disabled case `last_tick_graph` deliberately
   stays `None`, so the existing flag remains observable; only claim detection
   uses the local graph.
2. Takes every non-joint actor response with a major action and collects its
   `Resource("item", id)` writes from that actor's major graph operation.
3. Resolves all claims with `simultaneous_priority`.
4. Suppresses every claimant that loses any contested item resource. An actor
   whose major action claims several item resources and loses one is suppressed
   for the whole action, because a major action cannot be partially applied.

Only `Resource("item", ...)` is claimed in this phase. `stock`, `container`,
`actor`, `cell`, `building`, `job`, `animal`, `relationship`, `utterance`,
`memory` and `world` keep their existing rules. Contests
(`take`/`strike`/`restrain`/`throw`), same-cell moves, joint acts and every
other action are still governed by the TG05 engine semantics.

## Suppression

For a suppressed actor:

- its major action is not enacted;
- its utterances and memory updates still apply;
- `last_results[actor]` is `False`;
- `world._publish_outcome(actor, action, False, "not_possible")` is called
  under the TG05 module-level graph lock, producing the existing
  `not_possible` refusal record and `last_outcome`;
- a continuation sees `action_ok=False` through the existing `_finish_turn`
  path.

No new refusal code is introduced and the data pack is unchanged. The serial
loop applies this through `_apply_suppressed_response`; the threaded path does
the same inside `_apply_unit`, and the main thread still writes results/errors
in deterministic turn order.

## What is and is not simultaneous yet

Simultaneous **arbitration** is implemented: contested exclusive item claims
are decided from the frozen responses rather than by whichever actor happens to
commit first. The winner and every loser are known before either commit path
starts.

The actual world writes are still applied by the existing serial or threaded
executor. This phase does not re-enact the whole world from a snapshot and does
not roll back a loser's side effects; it prevents the loser's major action from
starting. Effects outside the item slice remain ordered exactly as in TG05.

## Tests

`tests/test_tick_simultaneous.py` (16 test cases):

- pure `resolve_claims`: one claimant, higher priority, ordered tie-breaks,
  multiple resources, input-order independence;
- `pick_up` proposals mint the same `Resource("item", ...)` claims (proving the
  claim layer covers the requested verb even though scenario physical objects
  are enacted with `move_object` in this engine);
- sequential crate scenario: first in turn order gets the object, the other is
  refused;
- simultaneous crate scenario with a priority that prefers the later-turn
  actor: that actor wins, the other has `last_results=False` and a
  `not_possible` refusal, and the object location matches the winner;
- three repeats × (`serial` workers 1, `threaded` workers 1, `threaded`
  workers 3) produce identical winner, results, refusals and semantic world
  state;
- two actors claiming different objects are both applied and neither is
  suppressed;
- a suppressed actor's speech and memory still apply;
- option validation and `create_game` pass-through;
- sequential runs are identical over two turns and never call
  `resolve_claims` (monkeypatched recorder);
- simultaneous claims still suppress with `tick_graph_enabled=False`, using a
  local graph while `last_tick_graph` stays `None`.

## Commands and results

```bash
python3 -m pytest -q tests/test_tick_simultaneous.py -p no:cacheprovider
# 16 passed in 1.53s

python3 -m pytest -q tests/test_tick_simultaneous.py \
  tests/test_tick_graph_executor.py tests/test_tick_graph.py \
  tests/test_tick_snapshot.py tests/test_tick_trace.py -p no:cacheprovider
# 55 passed in 136.60s (0:02:16)

python3 -m pytest -q tests/test_phase055_concurrency.py \
  tests/test_phase029_contest.py tests/test_phase038_strikes.py \
  tests/test_phase047_joint_actions.py tests/test_bigville_game_api.py \
  -p no:cacheprovider
# 108 passed in 55.60s
```

## Known limitations

- **Item resources only.** The first policy slice does not arbitrate exclusive
  claims on stock, containers, actors, cells or world-global state. Those
  effects keep the TG05 serial/tie-break order even in simultaneous mode.
- **No rollback or snapshot replay.** A loser is stopped before its major
  action; the rest of the turn still mutates live world state. An action that
  wrote before the arbitration point (for example via free speech) is not
  undone, and the mode is not yet a full "apply everything from a frozen
  snapshot" engine.
- **Whole-action suppression.** If one action legitimately claims multiple item
  resources and loses one contest, the entire action is suppressed. This is
  conservative and avoids partial effects.
- **Graph over-declaration is inherited.** An item write the TG04 verb table
  declares conservatively can create a contest that the physical action would
  not actually have. The table is deliberately conservative, so the failure
  mode is lost parallelism or an extra refusal, never an unarbitrated race.
- **Scenario pick-up verb.** A scenario-authored physical object is moved with
  `move_object` (destination = resident) in this engine. A raw `pick_up` major
  action is only routed to `World.pick_up` for `ToolItem` nodes; `enact_plan`
  does not route it for scenario objects. The claim layer itself is
  action-agnostic and test-proven to mint `pick_up` item claims, but the
  end-to-end crate scenario uses `move_object`.
- **Contest suspension and recomputation.** Suppression is recomputed at the
  start of each `_apply_turn` call. Because claims come from the frozen
  responses and the default priority is read-only, a resumed contest turn
  reaches the same winners. Actors before the resume index are not reapplied.
- **Custom priority contract.** A custom callable must be deterministic and
  return mutually comparable values across every claimant. The engine does not
  sandbox or memoise it.

## Handoff to TG07

TG07 can rely on:

- `turn_semantics="sequential"` remains byte-for-byte TG05 and never invokes
  claim resolution.
- `turn_semantics="simultaneous"` has a pure, reusable claim layer
  (`Claim`, `resolve_claims`) that a sharded coordinator can run before
  dispatch.
- Suppression is an explicit, observable refusal (`not_possible`) rather than a
  silent first-writer win, and it applies identically on serial and threaded
  commit paths.
- The remaining work for broader simultaneous semantics is to widen the claim
  resource kinds (cells, containers, stock, world-global) and to decide which
  conflicts should use the existing contest resolution instead of
  suppression. Those are policy choices for a later phase, not executor work.
- A partitioned executor must run claim resolution at the coordinator barrier
  before assigning winning units to shards; losing units still need their
  speech/memory delivered.
