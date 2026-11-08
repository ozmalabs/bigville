# NB05 — Transport seam, checksum comparison and final docs

Status: implemented, targeted gates green. Base commit
`6ea732b615bf3b6ccb716bcb2ff9e5a8f0bd7a57`
(`NB04: dispatch partitioned turns as acknowledged bundles`, branch
`distributed-bundles`). NB05 changes are uncommitted.

## Scope

- `tests/test_bundle_transport.py` — new transport-neutral proof.
- `tools/verify_bundle_equivalence.py` — new reproducible serial/partitioned
  equivalence and checksum tool.
- `README.md` — concise distributed-bundle protocol section.
- `docs/design/DISTRIBUTED_BUNDLES.md` — status table.
- `docs/phases/distributed-bundles/NB05_REPORT.md` — this report.
- `docs/phases/distributed-bundles/FINAL_REPORT.md` — program close-out.

No game, world, executor, checkpoint or default-path behaviour changed. The
protocol objects and the NB04 transport seam already carried everything the
tests needed, so **no production fix was required**. In particular:

- `Bundle.to_dict`/`from_dict` already preserve operations, resources, params,
  tiebreaks and namespace exactly through `json.dumps`/`json.loads`;
- `LocalBundleTransport` already caches by `bundle_id`, rejects a result whose
  `bundle_id`, namespace or `base_version` does not match the dispatch, and
  rejects a stale/mismatched ack;
- `BundleResult.to_dict`/`from_dict` and `BundleAck.to_dict`/`from_dict` are
  already JSON-safe, so a result and its confirmation can cross the same wire
  boundary as the bundle.

## Transport-neutral proof

`tests/test_bundle_transport.py` builds no `BigvilleGame`, imports no world
module and never mutates a shared graph. It constructs a `Bundle` with two
operations (nested params, two resource kinds), then:

1. JSON round-trips `bundle.to_dict()` through
   `json.dumps`/`json.loads`/`Bundle.from_dict` and checks object equality and
   canonical JSON equality.
2. Dispatches the restored bundle through `LocalBundleTransport` with a
   synthetic executor that computes effects, created ids, actor rows and both
   checksums from the plain bundle alone.
3. Acknowledges the result, checks `replay`, and dispatches the same wire form
   again; the executor runs exactly once and the cached object is returned.
4. Round-trips the result and ack as independent wire messages, then preloads a
   fresh transport with the wire result. A preloaded replay must not execute
   the executor.
5. Recomputes `bundle_output_sha`/`bundle_execution_sha` from the restored
   bundle and wire result; they match the in-memory run.
6. Rejects a result whose `base_version` is stale and one whose namespace is
   mismatched. Both leave no replay entry and no dispatch-order entry.
7. Rejects stale/unknown acks.

That is the same protocol a process/socket worker would use; nothing in the
test requires the live world. Runtime is about 0.1 s.

## Verification tool

`tools/verify_bundle_equivalence.py` is import-safe: the repository root is
added to `sys.path`, `build_report(...)` is a pure builder and `main(argv)` is
the CLI. It supports:

```text
--seeds 305000,305002   (default; comma-separated)
--turns 8               (default)
--scenario town100      (default; any create_game scenario name)
--affordance-mode menu|lazy
--json                  (compact JSON; default is indented JSON)
```

For each seed it builds three games with the same scenario, seed, backend and
affordance mode: serial, partitioned, and a second partitioned replay. Every
turn it:

- steps all three and requires `status == "advanced"`;
- compares `semantic_world_state` and `tick_payload_sha` between serial and
  partitioned;
- audits the partitioned `last_bundle_log`: every dispatched id has exactly one
  result and one committed ack; no duplicate dispatch or commit; the committed
  order covers every bundle; result/ack base versions and execution hashes
  agree; the logged payload hash equals the post-turn `tick_payload_sha`;
- compares the two partitioned runs' `tick_execution_sha` and commit order;
- accumulates per-tick execution hashes into `run_execution_sha`.

It also collects every partitioned bundle as JSON, then dispatches each one
through a fresh `LocalBundleTransport` with a world-free synthetic executor.
Duplicate dispatch, replay, ack recording and re-round-trip are checked in that
transport. This is the tool-level version of the transport-neutral test.

The JSON report contains per seed: `payload_equal`, `execution_stable`,
`bundle_count`, `bundles_per_turn`, `first_divergence`,
`first_execution_divergence`, both run execution hashes, per-tick bundle ids,
results, acks, committed order, payload hashes, execution hashes, and the fake
transport summary. Exit code is non-zero on any failure.

## Verification matrix

Commands and results:

```text
python3 tools/verify_bundle_equivalence.py --seeds 305000,305002 --turns 8 --json
  exit 0, 37.67 s
  seed 305000: payload_equal=True execution_stable=True bundles=8
               per-turn=[1,1,1,1,1,1,1,1]
               run execution sha efdc3f93d6ede36d9ac05c1d3e66f0f345b659ea41bc07e95c4f15f6f05a554a
               replay sha        efdc3f93d6ede36d9ac05c1d3e66f0f345b659ea41bc07e95c4f15f6f05a554a
  seed 305002: payload_equal=True execution_stable=True bundles=8
               per-turn=[1,1,1,1,1,1,1,1]
               run execution sha 58d49103c5d4b5716b859db4ac1269ee06e90a4bfc0c48b2bab8d6ce21da0140
               replay sha        58d49103c5d4b5716b859db4ac1269ee06e90a4bfc0c48b2bab8d6ce21da0140
  fake transport: 8/8 and 8/8 bundles round-tripped; duplicate dispatch
                  idempotent; every ack and replay recorded.

python3 tools/verify_bundle_equivalence.py --seeds 305002 --turns 8 \
  --affordance-mode lazy --json
  exit 0, 15.60 s
  seed 305002: payload_equal=True execution_stable=True bundles=13
               per-turn=[1,1,2,2,1,2,3,1]
               run execution sha e44c270fcc35d916b020c3b7cd3aa8591349409df5d09415251df2833a8113e3
               replay sha        e44c270fcc35d916b020c3b7cd3aa8591349409df5d09415251df2833a8113e3
  fake transport: 13/13 bundles round-tripped; duplicate dispatch idempotent.

python3 tools/verify_bundle_equivalence.py --seeds 305004,305006 --turns 8 --json
  exit 0, 37.17 s
  both seeds: payload_equal=True execution_stable=True bundles=8
              per-turn=[1,1,1,1,1,1,1,1]
              run sha == replay sha for each seed
              fake transport: 8/8 bundles per seed.
```

On the menu-mode `town100` sample each turn collapsed to one coordinator
bundle, so that matrix proves per-turn equivalence and log completeness but
not multi-bundle concurrency. The lazy run produced 1–3 bundles per turn
(13 total) and exercises multi-bundle dispatch, deterministic ordering and
multi-bundle replay. The NB04 forced-shard tests remain the coverage for
multiple spatial shards in a single turn.

## Targeted test gates

```text
python3 -m pytest -q tests/test_bundle_transport.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_node_origins.py \
  tests/test_bundle_dispatch.py -p no:cacheprovider
134 passed in 23.60s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py tests/test_engine_defaults.py \
  tests/test_lazy_*.py -p no:cacheprovider
175 passed, 1 skipped in 103.51s

python3 domains/bigville_entities.py
ERRORS 0, WARNINGS 0, INFO 95
```

The full suite was not run for this phase; the host had an active suite and
these targeted gates are the NB05 contract. No full-suite pass is claimed.

## Limitations (unchanged, now explicit in README)

- **Shared-world callback.** The NB04 executor mutates the in-process world
  during dispatch. A result is logically invisible until ack, but an
  infrastructure failure after partial mutation cannot be rolled back.
- **Turn version, not per-commit revision.** `base_version` is
  `int(world._turn)`; several bundles in one turn share it, and
  `committed_version` does too.
- **No network or processes.** There is no socket/process transport, worker
  lifecycle, supervision, authentication or backpressure.
- **No durable log.** `TickBundleLog` and the transport cache are in memory and
  not checkpointed. A fresh default transport is created per commit; callers
  must inject/persist one to replay across calls.
- **No snapshot shipping.** The bundle carries operations and declared
  resources, not a world checkpoint; remote restore is not implemented.
- **Graph-only created ids.** `created_ids` covers the world graph under the
  bundle namespace. Nested resident graphs share the namespace context but are
  not part of `world.eng.nodes_by_origin`.

## Handoff

For real distribution, the next work is:

1. a process/socket `BundleTransport` with the same `dispatch`/`acknowledge`/
   `replay` contract and a serialisation codec around the already-tested JSON;
2. worker lifecycle, supervision, retries with the same namespace/attempt, and
   stale-base rejection against a live world revision;
3. a durable coordinator dispatch/result/ack log (checkpointed or
   append-only), so replay survives a coordinator restart;
4. snapshot or delta shipping and remote restore, replacing the shared-world
   callback with `BundleResult.effects` deltas;
5. backpressure, quotas and authentication/authorisation at the transport
   boundary.

The protocol objects, checksum scopes, idempotence key and ack rules are
complete and transport-neutral; those five items are infrastructure, not a
change to the bundle contract.
