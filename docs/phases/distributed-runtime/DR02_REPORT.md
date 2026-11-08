# DR02 — Durable bundle/tick log

Status: complete (uncommitted), 8 November 2026. Phase DR02 of
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).

- Base commit: `1ddf95b` on branch `distributed-runtime` (DR01).
- New files: `bigville/bundle_log.py`, `tests/test_bundle_log.py`.
- Changed files: `bigville/sharding.py` (journal writes in `commit` only),
  `bigville/game.py` / `bigville/api.py` (optional `bundle_log_path`),
  `docs/design/DISTRIBUTED_RUNTIME.md` (DR02 status row), this report.
- No default path, no environment variable, no checkpoint change. Serial and
  threaded turns write nothing even when a path is configured.

## Record format

`BundleJournal` writes canonical JSON (the existing
`bigville.bundles.canonical_json` encoder), one object per line, in append
order:

| kind | fields |
|---|---|
| `tick_start` | `run_id`, `tick`, `base_version`, `revision` |
| `dispatch` | `bundle` (`Bundle.to_dict()`) |
| `result` | `result` (`BundleResult.to_dict()`) |
| `ack` | `ack` (`BundleAck.to_dict()`) |
| `commit` | `bundle_id`, `committed_version` |
| `tick_end` | `run_id`, `tick`, `execution_sha`, `payload_sha`, `revision`, `status` (`ok`), optional `reason` |

`tick` is the existing partitioned tick-log identity (the bundle base version).
`base_version` repeats it for readers that have only the start record.
`revision` on `tick_start` is the graph revision observed when the commit began;
`tick_end.revision` is the post-turn graph revision. `tick_end.execution_sha`
is `TickBundleLog.execution_sha` (dispatch/ack/commit order) and
`tick_end.payload_sha` is the semantic world payload hash, so replay can prove
it reconstructed the same tick.

An exception during commit or turn finalisation closes the open block with
`status="aborted"` and a `reason`. Aborted ticks are recorded for diagnosis but
are not claimed to be complete ticks.

## Durability, writers and corruption

- The file is opened lazily with `O_APPEND` on the first append; parent
  directories are created at that point. Each record is written, flushed and
  `fsync`ed before `append` returns. Constructing a game/journal never creates a
  file.
- One process-local writer per path is enforced. Cross-process writers are not
  supported: the documented rule is a single writer (an external lock is the
  caller's responsibility). Readers do not take the writer registry.
- A duplicate identical record inside one open tick raises
  `DuplicateRecordError`; a second `tick_start` while a tick is open raises;
  records outside an open tick raise. A failed write is not treated as
  appended.
- `read()` yields complete records. A final line without its newline is a
  truncated tail: it is not yielded and is reported by
  `last_read_report.truncated_tail` / `truncated_bytes`. A malformed complete
  line anywhere raises `JournalCorruptionError` with its 1-based line number;
  malformed middle lines are never skipped.

## Replay and verify semantics

`replay(allow_truncated=False, allow_incomplete=False)` returns one
`TickBundleLog` per tick block, in journal order. It rebuilds the log from
`Bundle.from_dict` / `BundleResult.from_dict` / `BundleAck.from_dict` and
recomputes:

- bundle/result/ack identity, namespace and base version (the `TickBundleLog`
  rules);
- `bundle_output_sha(result)` and `bundle_execution_sha(bundle, result)` against
  the stored result checksums;
- every dispatched bundle has result, ack and commit records in
  dispatch → result → ack → commit order;
- no duplicate dispatch/result/ack/commit (the live log treats an identical
  duplicate as idempotent; replay is stricter because a durable duplicate is a
  writer/audit bug);
- commit versions are non-decreasing and match the committed ack;
- `tick_end` checksums equal the replayed log, and the end revision is not older
  than the base, the start revision, or the last committed version.

`verify()` runs replay and returns a `JournalVerification` report (records,
ticks, aborted ticks, bundles, bytes, revisions, truncation flag). A truncated
tail is an error unless `allow_truncated=True`; an aborted or unclosed tick is
an error unless `allow_incomplete=True`. Replay attaches the stored payload hash
to the rebuilt `TickBundleLog` so `to_dict()` matches the live log.

## Integration

- `BigvilleGame(..., bundle_log_path=None)` and
  `create_game(..., bundle_log_path=None)`. When set, `game.bundle_journal` is a
  `BundleJournal`; when unset it is `None`.
- `_apply_turn_partitioned` passes the journal to
  `PartitionedExecutor(..., journal=...)`. `PartitionedExecutor.commit` writes
  `tick_start`, every dispatch, and result/ack/commit through the normal commit
  loop. `_apply_turn_partitioned` writes `tick_end` after `_finish_turn` and the
  payload hash are known, with the post-turn world revision.
- A journal write or `fsync` failure propagates and fails the turn. This is the
  explicit opt-in contract (the alternative — silently continuing with an
  incomplete audit trail — was rejected). If commit/finish raises, the game
  makes a best-effort `tick_end(status="aborted")` and re-raises the original
  exception so the real failure is never masked.
- Serial and threaded paths do not import or call the journal writer; with a
  configured path they leave the filesystem untouched (`last_bundle_log` stays
  `None`).

## Overhead measurement

Host: shared worktree host, a full test suite was potentially active; timings
below therefore include contention/warm-up noise. Setup: `town100`, seed
`305000`, `executor="partitioned"`, 4 workers, `affordance_mode="lazy"`,
`snapshot_mode="on_demand"`, 4 turns, journal off then on in one process.

| turn | off (ms) | on (ms) | delta (ms) |
|---|---:|---:|---:|
| 1 | 711.2 | 797.0 | 85.8 |
| 2 | 1032.7 | 1089.2 | 56.5 |
| 3 | 237.2 | 395.7 | 158.5 |
| 4 | 188.0 | 395.8 | 207.8 |
| mean | 542.3 | 669.4 | 127.2 |

- Total journal overhead: 508.7 ms over 4 turns (~127 ms/turn in this noisy
  run). The per-record `fsync` is the dominant cost, not JSON encoding.
- Journal size: 388,861 bytes for 24 records (4 ticks, 4 bundles — one bundle
  per turn in this cheap lazy run), ~97 KB/turn, ~16 KB/record.
- Replay/verify of the produced journal succeeded and reported 4 ticks, 0
  aborted, 4 bundles.

## Tests

New `tests/test_bundle_log.py` (24 tests): synthetic write/read/replay/verify
round trip with canonical-line checks and exact log reconstruction; two
identical tick versions as separate blocks; truncated final line reported and
refused by default (accepted only explicitly); malformed middle line raises with
line number; missing result/ack/commit and missing `tick_end`; duplicate
dispatch/result/ack/commit; result for an undispatched bundle; ack without a
result; output/execution checksum tampering; revision and non-monotonic commit
order mismatch; duplicate `append`/commit rejected without a second line; path
validation, lazy file creation and context-manager close; a real partitioned
small-scenario game journal replayed to `last_bundle_log`; serial and threaded
games create no file/records.

Commands on this worktree:

```text
python3 -m pytest -q tests/test_bundle_log.py -p no:cacheprovider
24 passed in 1.21s

python3 -m pytest -q tests/test_bundle_log.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_bundle_dispatch.py \
  tests/test_graph_revisions.py -p no:cacheprovider
147 passed in 22.09s

python3 -m pytest -q tests/test_tick_sharding.py \
  tests/test_tick_graph_executor.py -p no:cacheprovider
29 passed in 36.27s
```

`python3 domains/bigville_entities.py` completed with `ERRORS (0)` and
`WARNINGS (0)`; production graph 481 nodes / 864 edges / 284 components.

## Limitations

- Replay uses `TickBundleLog`'s private `_payload_sha` slot to attach the stored
  payload hash; the in-memory log has no public setter for an externally
  supplied hash.
- `tick` remains the graph revision. A turn with no graph mutation can legitimately
  reuse the previous tick value; replay groups by record block, not by a
  `(run_id, tick)` key. Consumers should not assume tick values are unique.
- Durability is per-record `fsync`; it is intentionally simple, not a
  group-commit or WAL. A crash can leave a truncated final line, which is
  reported and refused by default.
- Cross-process writer exclusion is documented, not enforced. The process-local
  registry catches accidental double-open in one process only.
- Aborted ticks need `allow_incomplete=True`; their checksums are not a proof of
  a complete tick.
- The journal records `BundleResult.effects` as currently emitted. In DR02 those
  effects are empty for the in-process executor; DR03 will populate them.
- No journal rotation, retention or compression policy is added.

## Handoff to DR03

- Populate `BundleResult.effects` with the recorded graph delta; the journal
  already serializes the full result, so delta replay can use
  `result.effects` without a new record kind.
- Validate a result delta against the dispatch `base_version` with the same
  stale-base rule; a journal replay should be able to apply each delta to a
  restored graph and compare the canonical state.
- Consider a replay-time check that the committed effect delta advances the
  revision exactly as `tick_end.revision` reports. If DR03 adds an authoritative
  per-bundle delta revision, `commit` can carry that instead of the current
  observed walking maximum.
