# TG01 — Equivalence oracle and provenance trace

Base commit: `e8b6415f25f44620c22d5ea273f49a3fdcb15df0`

## Scope

Add a pure, read-only trace/digest layer for the tick-graph phases. No engine
behaviour was changed and no production file outside the TG01 scope was
touched.

## Files

- `bigville/tick_trace.py` (new)
- `tests/test_tick_trace.py` (new)
- `docs/phases/tick-graph/TG01_REPORT.md` (this report)

## Behaviour

`bigville.tick_trace` provides:

- `canonical(value)` / `canonical_json(value)` / `value_digest(value)` — a
  deterministic recursive encoder used by every digest. Dictionary keys are
  stringified before `json.dumps(sort_keys=True, separators=(",", ":"))`.
  `NodeRef` (which subclasses `int`), tuples, sets and frozensets carry explicit
  type tags; set members are sorted by their compact canonical JSON. Unknown
  values raise `TraceValueError` instead of falling back to `str`/`repr`.
  Non-finite floats and key collisions after stringification also fail loudly.
- `step_trace(game)` — records, for the turn just completed:
  - `turn`, `order` (`game.last_order`);
  - `responses`: every actor in sorted order with proposed `action`, `params`,
    `reason`, `utterances` and `waiting` flag;
  - `results` and `errors` in actor order;
  - `continuations`: each `game._continuations[actor].request.to_dict()`;
  - `world_sha256`: SHA-256 of the canonical
    `game.world.eng.to_checkpoint_dict()`.
- `TurnTrace` — `add(game)` appends `step_trace(game)`, `add_record(record)`
  appends an existing record, `.records` exposes the sequence, `.turns` the
  length, and `.digest` / `.hexdigest()` hash the canonical records with a
  newline separator.
- `first_divergence(a, b)` — accepts two `TurnTrace`s or two record iterables
  and returns `(turn, field_path)` for the first difference, `None` when the
  traces are equal, or `(turn, "<missing>")` when one trace is a strict prefix.
  Paths use dotted keys and bracket indexes, e.g.
  `responses.Ben.params.destination[1]`.

The trace reads the game and world graph only. It does not advance a turn,
mutate the world, consume RNG, or alter backend state.

## Commands and results

```bash
python3 -m pytest -q tests/test_tick_trace.py -p no:cacheprovider
# 6 passed in 35.23s

python3 -m pytest -q tests/test_phase055_concurrency.py -p no:cacheprovider
# 6 passed in 41.28s
```

`tests/test_tick_trace.py` proves:

1. Two independent `town100` seed 305000 runs with simple autonomous backends
   have identical records and digests over 4 turns, including continuation
   requests.
2. Changing one world fact changes `world_sha256` and the trace digest, and
   `first_divergence` reports `(turn, "world_sha256")`.
3. Changing one actor's proposal changes the digest and
   `first_divergence` reports `(1, "responses.Ada.action")`.
4. `first_divergence` finds the first differing turn and nested field in a
   synthetic three-turn trace, returns `None` for equal traces and
   `(turn, "<missing>")` for a prefix.
5. The canonical encoder is stable for reordered dicts and for tuples, sets,
   frozensets and `NodeRef`.
6. Wrapping `game.step()` with `TurnTrace.add()` leaves the step return value,
   `last_order`, `last_results`, `last_errors`, continuations and canonical
   world checkpoint identical to an untraced run over 2 turns.

## Known limitations

- `first_divergence` reports `world_sha256` as the field path for a world-state
  difference; it does not descend into the checkpoint because the record stores
  the digest, not the full checkpoint. The full checkpoint is available from
  the live game when a phase needs a deeper diagnosis.
- The record includes the proposal `reason` and `waiting` flag in addition to
  the minimum oracle fields. Both are deterministic and useful for diagnosing
  divergence; later phases must keep them stable or accept the oracle bump.
- `canonical` supports the value shapes the engine currently exposes (JSON
  primitives, `NodeRef`, typed containers, `to_dict()` objects and dataclasses).
  A future backend that puts an unsupported object in params will fail with
  `TraceValueError` rather than produce a misleading digest.
- Tracing 100 residents reads the whole graph checkpoint each turn. That is
  acceptable for oracle tests (the full `tests/test_tick_trace.py` suite takes
  about 35 seconds on the development machine) but it is not intended for
  production hot paths.

## Handoff to TG02

TG02 can rely on this guarantee:

> Two runs are equivalent for a phase iff their `TurnTrace` digests match on the
> same scenario, seed and turn count; a mismatch identifies the first differing
> turn and field path.

For TG02's occupancy index, capture a `TurnTrace` over the standard scenarios
before and after the change and assert equality. The world digest covers the
canonical checkpoint after every turn, so an index stored inside the world graph
must either be reconstructed deterministically or excluded in the same way the
existing checkpoint excludes derived state. `step_trace` must remain pure: if
the occupancy index needs a warm-up or refresh, do it in engine/world code, not
inside the trace.
