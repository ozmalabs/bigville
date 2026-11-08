# Bigville

Bigville is a data-driven village simulation and game API. The canonical world
contains a map, residents, bodies, animals, farms, buildings, food production,
trade, storage, law, records, observations, affordances, and seeded resident
cognition. Actors are driven through a backend boundary: Ocelot, a human UI,
the deterministic game backend, or a future LLM backend can all propose the
same validated actions.

Recipe work follows that boundary too: the world publishes physically legal
recipes and validates explicit craft actions. It does not infer an actor's
demand beliefs, choose a recipe, or size a production run from town-wide
signals. Those expectations and choices belong to the actor's cognition
backend.

## A system for embodied agent research

Bigville provides a shared, persistent world in which an agent's cognition is
coupled to a simulated body. A resident has a position, physical needs and
capabilities, and acts among other residents, objects and institutions.
Observations and affordances come from that situation; actions are proposed by
the resident's backend, checked and enacted by the world, and their outcomes
change what can happen next. For example, food has to be reached, acquired and
eaten; exertion, exhaustion and injury have consequences; and objects and
resources remain in the world for other residents to encounter. The API is the
interface to this loop: the modeled body, environment and their interaction
give the actions their meaning.

This design makes Bigville useful as an experimental system for questions in
embodied cognition, artificial life and social simulation:

- **Perception and action:** how do limited observation, location, effort and
  changing bodily needs affect a resident's choices and its ability to learn
  what the world permits?
- **Cognition in context:** how do Ocelot, deterministic, human and LLM
  backends behave when situated in the same world, and how do their decisions
  change when resources, bodies or social surroundings change?
- **Social and institutional dynamics:** how do individual actions and their
  consequences accumulate into patterns of work, exchange, cooperation,
  conflict and governance in a shared village?
- **Experimental intervention:** how do outcomes change when a scenario,
  initial conditions, population or backend changes? Seeded scenarios,
  world reports and action outcomes support controlled runs and inspection of
  the resulting trajectories.

The intellectual grounding is the relationship between mind, body and world.
Varela, Thompson and Rosch's [*The Embodied Mind*](https://mitpress.mit.edu/9780262529365/the-embodied-mind/)
describes cognition and perception as arising through embodied, situated
activity. Gibson's [account of affordances](https://www.routledge.com/The-Ecological-Approach-to-Visual-Perception-Classic-Edition/Gibson/p/book/9781848725782)
connects opportunities for action to the relationship between an organism
and its environment. Brooks's [work on situated robotics](https://people.csail.mit.edu/brooks/papers/representation.pdf)
likewise makes ongoing perception and action central to intelligent behaviour.
Bigville takes these ideas as design influences: its bodies and environment
are computational models, and the system does not claim to reproduce lived
experience or establish that its agents are human-like.

The system is complementary to recent agent research. Park et al.'s
[*Generative Agents*](https://arxiv.org/abs/2304.03442) explores believable
social behaviour using language-model memories, reflection and planning in a
town. [*Emergence World*](https://arxiv.org/html/2606.08367v1) studies
long-horizon, heterogeneous agent populations using a persistent spatial
environment, memories, governance and context-gated tools. Bigville shares the
interest in agents acting together over time, while making a simulated body's
needs and capabilities, physical resources and world-side consequences a
foundation for the cognition loop. Emergence World also enforces contextual
preconditions; the difference is one of modeling emphasis, not a claim that
its agents lack a world or that an API cannot mediate embodied action.

The [feature plan](docs/FEATURE_PHASES.md) sets out further work on a limited
agent view, personas and routines, and comparative learning evaluation; these
are planned phases rather than claims about the current system. Research use
still requires explicit hypotheses, controls, repeated runs and validation
against appropriate observations.

The public API is in `bigville/`:

```python
from bigville import create_game

game = create_game(player="Ada", default_backend="cheap")
state = game.step()
```

The simulation also exposes a read-only statistical report. It contains an
exact census and physical/economic/social measurements, plus a deterministic
simple-random sample estimate with finite-population standard errors:

```python
report = game.world.report(sample_size=30, seed=7)
print(report["population"]["alive"])
print(report["economy"]["transactions"])
print(report["social"]["conversation"])
```

`run_village()` records compact period snapshots and deltas in the report's
`series` field. The same current report is available to clients at
`GET /api/report`; it does not advance the simulation or create world facts.

Bigville is standalone: its graph runtime, world mechanics, seed data, backend
protocol, persistence model, and tests are all in this repository. Cognition
providers may be embedded, remote, deterministic, human-driven, or backed by
another project; none is required to run the simulation.

## Play the village

The repository includes a playable Phaser 3 browser client. It uses the
canonical Python world over a small standard-library HTTP API.

```bash
python -m pip install -e .
python -m bigville.server
# open http://127.0.0.1:8765/
```

The cosy pixel-art terrain tiles, reusable building sprites, and supporting
sprite/icon sheets are included in the package. The client uses a square-cell
3/4 top-down presentation with a close 2x pixel-art scale, upright facades,
and row-based depth. It assembles the map from the scenario's exported grid
and building placements, so changing the world seed or scenario changes the
geography without requiring a new backdrop.
Use the action buttons to submit a major action, or speak to another resident;
autonomous deterministic residents take their own backend decisions on the
same turn.

Terrain movement is seeded data: paths have a faster, lower-effort travel
profile, while each map cell publishes its own speed and stamina multiplier.
The simple NPC backend uses that path preference when choosing comparable moves.

### Screenshots

![Bigville town-square overview](docs/screenshots/bigville-overview.png)

![Bigville town-square close-up at 200% zoom](docs/screenshots/bigville-detail.png)

![Bigville after a turn](docs/screenshots/bigville-after-turn.png)

![Animated Bigville simulation](docs/screenshots/bigville-simulation.gif)

The animation is produced from a live run of the client and backend:

```bash
python tools/record_game.py --turns 24
```

The recorder requires the optional local tools `playwright` and `Pillow`, plus
a Chromium-compatible browser.

Occupied buildings are rendered as open-roof rooms, so residents and their
interiors remain visible while the village continues to run.

The art scale and asset contract is documented in
[`docs/GAME_ART_DESIGN.md`](docs/GAME_ART_DESIGN.md). The item atlas is
generated from every entry in `domains/bigville_entities.ITEMS`; the inspector
shows bulk stock, discrete carried objects, and worn clothing. A held tool is
rendered on the resident, so a resident carrying a pick visibly has a pick.
The current art direction board is included at
[`bigville/game/assets/stardew_like_art_direction.png`](bigville/game/assets/stardew_like_art_direction.png);
the original village rendering is preserved as a reference at
[`bigville/game/assets/style_source_village.png`](bigville/game/assets/style_source_village.png),
but it is not drawn as a backdrop. `tools/build_style_assets.py` turns the
reference language into assembled material fields, terrain transitions, props,
and building facades. Broad surfaces are masked to the canonical map cells,
while paths are transparent topology-aware interfaces: their dirt footprint
connects to neighbouring path cells and leaves a grass shoulder at endpoints,
corners, and turns. This keeps grass, paths, water, soil, and stone from reading
as a checkerboard of independently stamped squares. Material boundaries also
get sparse pixel-art edge overlays on both sides, so grass does not meet stone,
soil, or water as a ruler-straight seam. It also includes matching roof-off cutaway facades with furnished
interiors, so scenarios can use different maps with the same cosy visual style
without falling back to a separate interior art language. Residents use a
32px directional walk-cycle atlas with idle, step-A, and step-B frames, so
movement is rendered as a short physical walk between simulation cells.
Common hand-held objects use a separate detailed atlas and are anchored to the
walking hand rather than floating at a fixed map offset.

## Cognition backends

`simple` (also spelled `cheap` for compatibility) selects the lightweight
deterministic NPC backend, suitable for low-cost residents and animal-style
policies. Selecting `ocelot` requires Ocelot's actual
`worlds.bigville_ocelot_adapter.BigvilleOcelotResident` and its dependencies;
the session raises `OcelotUnavailableError` instead of using a local fallback.
Put both repositories on `PYTHONPATH`. The current Ocelot adapter also reads
some seed files relative to the working directory, so run from the Ocelot
checkout. Scenario-authored backend choices take precedence over the default.

`BigvilleWorld.tick()` advances physical time and does not choose resident or
animal policies. `BigvilleGame` owns resident and animal backends, invokes them
for a successful turn, and submits their proposed actions to world-side
physical validation. The world publishes animal actions from adjacent legal
movement, reachable stocked feed, and available herding targets; hunger and
species preferences are backend motivations. Feeding consumes stock only when
the animal is within physical reach. For an unattended run, pass `autonomous=True` to `create_game`; Game sessions
advance metabolism and ecology once per 96 successful turns by default; set
`ticks_per_period` to another positive integer or `None` to manage periods
externally. A waiting human does not advance time. Residents must still acquire
and eat food through physical actions.

Scenarios can customise the deterministic policy using a backend factory and
`SimplePolicy`, both without changing world rules. For example:

```python
from bigville.backends import DeterministicBackend, SimplePolicy

factories = {"simple": lambda world, character: DeterministicBackend(
    character, policy=SimplePolicy(action_bonuses={"inspect": 50}))}
game = create_game(scenario="my_scenario", default_backend="simple",
                   backend_factories=factories, autonomous=True)
```

The bonus applies only when the world offers `inspect`; it does not create an
affordance or bypass physical admissibility. Scenario-authored backend choices
still override `default_backend`.

`DeterministicBackend` is the cheap, repeatable NPC backend. It maintains
needs-driven goals, changes priorities across morning/workday/evening/night,
chooses from the world's current legal affordances, and occasionally speaks in
structured social acts to nearby people. `LLMBackend` is a provider-neutral
adapter: pass an object with `complete(prompt)` and it will receive a versioned
JSON prompt containing the character state, public observations, world frames,
legal affordances, and recipient capabilities. The provider returns a JSON
`ActorResponse`.

Backends may return an optional `continuation` containing a physical
`destination` or repeatable `task`. Bigville reuses that plan without querying
cognition again until arrival or an unexpected encounter, hunger/energy
threshold, world event, or task failure. Set `poll_each_turn: true`, or
construct `BigvilleGame(..., continuations=False)`, for reactive
decide-every-turn behavior. Replayed actions still pass through the world's
admissibility and one-major-action rules.

### Affordance modes

`create_game(..., affordance_mode="auto")` is the default.  `"auto"` resolves
to **lazy** for an autonomous session whose resident backends are all built-in
simple/cheap, and to **menu** for a player, an LLM, Ocelot, any other backend,
or an explicitly menu-mode caller.  The game exposes both values:
`game.affordance_mode_requested` is the request (`"auto"`, `"menu"` or
`"lazy"`) and `game.affordance_mode` is the resolved mode.  A direct
`BigvilleGame(world)` constructor still defaults to `menu`.

In lazy mode a backend receives a cheap observation of local entities and
capabilities; it proposes stable names, ids or cells and the world validates
them, returning an ordinary refusal when a proposal is not admissible.  Menu
mode keeps the exhaustive per-turn legal-action menu for UI action pickers,
Ocelot's adapter, debugging and equivalence tests.  Both explicit
`affordance_mode="menu"` and `affordance_mode="lazy"` remain available and
always win.  See `docs/design/LAZY_AFFORDANCES.md`,
`docs/phases/lazy-affordances/LA08_REPORT.md` and
`docs/phases/lazy-affordances/FINAL_REPORT.md` for the evaluation and the
small-room travel caveat.

### Engine performance

`create_game` resolves three session options by backend.  For an autonomous
session whose resident backends are all built-in simple/cheap, the defaults are
`affordance_mode="auto"` → **lazy**, `snapshot_mode="auto"` → **on_demand**,
and `rule_batching="auto"` → **turn**.  That headless path skips the exhaustive
menu, does not build a snapshot/report on every turn, and runs one world-rule
sweep at the finish boundary instead of one per action.  A player, LLM, Ocelot
or any other backend resolves to menu/every_turn/action, so UI and cognition
sessions keep the historical semantics.  A direct `BigvilleGame(world)`
constructor still defaults to menu/every_turn/action.

Explicit values always win.  `snapshot_mode="every_turn"` restores the
per-turn `step()["snapshot"]`; in `"on_demand"` call `game.snapshot()` when a
UI or debugger needs one.  `rule_batching="turn"` is the batched finish sweep
and `"action"` the historical per-action sweep.  `set_backend()` re-resolves
all three auto modes.  On the synthetic simple town this cuts `step` time by
about 55%/55%/66% at 50/100/200 residents, with `_run` sweeps falling from
actions+3 to 3 per turn and identical behaviour on the evaluated town100 and
small-room runs.  See
[`docs/phases/engine-speedups/FINAL_REPORT.md`](docs/phases/engine-speedups/FINAL_REPORT.md).

### Distributed bundle protocol

The tick graph can also be committed as **bundles**: an explicit unit of work
that carries its namespace, base version, operations and declared read/write
sets.  This is a local, in-process protocol today, but its shapes are the ones
a worker process or socket transport would use.  It is opt-in with
`create_game(..., executor="partitioned")`; serial and threaded sessions are
unchanged.

```text
Bundle -> BundleResult -> BundleAck
namespace = r<run_id>/t<tick>/<executor>/s<shard>/b<bundle_seq>/a<attempt>
```

- A `Bundle` is built from one coordinator/shard conflict group.  Its
  `bundle_id` is the canonical namespace name and is also the idempotence key;
  retries reuse it.
- `LocalBundleTransport` dispatches to a caller-supplied executor, caches the
  result by `bundle_id`, and records acknowledgements.  A duplicate dispatch
  returns the cached result without executing twice.  The transport protocol
  is `dispatch`, `acknowledge` and `replay`; the game does not depend on the
  transport class.
- A result is not visible until the coordinator acknowledges it.  Results with
  a mismatched bundle/namespace or a stale base version are rejected, never
  merged.  Commits follow the deterministic bundle plan order, not worker
  completion order.
- `game.last_bundle_log` records the partitioned turn's dispatched bundles,
  results, acks, committed order and checksums.  Serial and threaded turns
  leave it `None`.

There are two checksum scopes.  **Execution** checksums
(`bundle_input_sha`, `bundle_output_sha`, `bundle_execution_sha`,
`tick_execution_sha`, `run_execution_sha`) identify the executor path,
namespace and commit order.  **Payload** checksums (`tick_payload_sha`) hash the
semantic world after a turn with allocation ids and insertion order removed;
that is the cross-executor equivalence hash.

Run the bundle verification matrix with:

```bash
python3 tools/verify_bundle_equivalence.py
python3 tools/verify_bundle_equivalence.py --seeds 305000,305002 --turns 8
python3 tools/verify_bundle_equivalence.py --seeds 305002 --affordance-mode lazy
python3 tools/verify_bundle_equivalence.py --json
python3 tools/verify_bundle_equivalence.py \
  --seeds 305000,305002,305004,305006 --turns 8 \
  --journal /tmp/dr05.jsonl --deltas --process
```

The tool runs serial and partitioned games turn by turn, compares
`tick_payload_sha` and graph revisions, audits every dispatched bundle for
exactly one result and one committed ack, checks deterministic commit order,
replays each seed through a second partitioned game to compare execution
checksums, and re-dispatches every bundle through a JSON round trip with a
synthetic executor that has no world.  It exits non-zero on any divergence.

#### Distributed runtime (DR01-DR05)

The bundle protocol now has a local runtime seam built on the same objects:

- **Revisions.** `BigvilleGraph.revision` / `BigvilleWorld.revision` advance on
  every mutation and are carried as the bundle `base_version`.  A stale result
  is rejected, never merged; committed acks are monotonic and round-trip through
  checkpoints.
- **Durable journal.** `create_game(..., bundle_log_path=...)` writes an
  append-only JSONL journal of `tick_start`/`dispatch`/`result`/`ack`/`commit`/
  `tick_end` records.  `BundleJournal.read/replay/verify` rebuild and check the
  tick logs and checksums, including truncated-tail and corruption reporting.
  Serial and threaded turns write nothing.
- **Effect deltas.** Partitioned bundle results carry `GraphDelta` effects:
  `graph.record_changes()` records nodes, edges and attr old/new values, and
  `GraphDelta.from_effects(...).apply_to(graph)` replays them against a
  same-base snapshot.  Effects are JSON-safe and stored in the journal.
- **Local process transport.** `ProcessBundleTransport` dispatches serialized
  bundles to `multiprocessing` workers with an idempotence cache, timeouts,
  retries, crash/restart and clean shutdown.  It is a transport seam, not the
  default; `PartitionedExecutor(transport=...)` accepts it.
- **Integration verification.** The verification tool's `--journal`, `--deltas`
  and `--process` scopes check journal replay equality, delta round trips and a
  real worker round trip in one pass.

This is still **local only**.  There is no network/socket transport,
authentication, backpressure, snapshot shipping/restore, cross-host worker
supervision, durable coordinator recovery or live-world worker executor.  A
bundle executor still mutates the shared in-process world; the effects are the
replayable record, not an alternative write path.  See
[`docs/phases/distributed-runtime/FINAL_REPORT.md`](docs/phases/distributed-runtime/FINAL_REPORT.md)
for the capability list and remaining work, and
[`docs/phases/distributed-bundles/FINAL_REPORT.md`](docs/phases/distributed-bundles/FINAL_REPORT.md)
for the underlying protocol.

### Real Ocelot integration

Bigville does not bundle the Ocelot substrate. The Ocelot repository provides
`worlds.bigville_ocelot_adapter.BigvilleOcelotResident`, which can be passed as
`cognition_factory` (or used through `create_bigville_board_game`). Physical
`read_object` actions then enter Ocelot's real deep document reader. Bigville
only records the returned graph evidence; its dependency-free fallback records
an explicit comprehension residual instead of claiming that stored prose was
understood.

## Development

```bash
python -m pip install -e .
python -m pytest -q
```

The backend and prompt work is staged in
[`docs/AGENT_BACKENDS_PLAN.md`](docs/AGENT_BACKENDS_PLAN.md).

## Local management discovery service

The separately launched management service exposes health, capabilities, a
local run registry, and run lifecycle commands. It remains a loopback-only,
single-user service.

```bash
python -m bigville.management.http
# http://127.0.0.1:8766/api/management/v1/health
# http://127.0.0.1:8766/api/management/v1/capabilities
# http://127.0.0.1:8766/api/management/v1/backend-profiles
# Open http://127.0.0.1:8766/ for the management shell.
```

Run metadata is stored by default in `~/.local/share/bigville-management`.
Set `BIGVILLE_MANAGEMENT_DATA_DIR` or pass `--data-dir` to choose another
local directory. The service only binds to loopback IP addresses. Backend
profiles are listed separately from engine capabilities. Ocelot is marked
unavailable when its external adapter cannot be imported. An LLM profile
requires a matching adapter registered in the server process; no provider or
model is treated as available just because it appears in configuration.
Optional `secret_ref` values in the local `backend_profiles.json` file are
passed only to the registered server adapter and are omitted from API
responses, run records and templates. Profile files may contain only IDs,
revisions, adapter names and local secret references, never credential
values. Authored scenarios can override an actor's profile; per-actor
assignments are rejected for built-in `town100`. On service restart,
unfinished in-memory runs are marked failed with an interruption reason;
worlds are not silently resumed. Each completed turn can be captured as a
full game checkpoint and forked into a separate paused run. Checkpoint files
and immutable metadata live below the management data directory. LLM adapter
state has no registered game-checkpoint adapter and is rejected for checkpoint
creation. Runs with provider-owned Ocelot resident minds are also rejected
because this service does not configure Ocelot's resident restore loader. The
UI reports both backend limitations before checkpoint creation. Local simple
backend game checkpoints use the engine's built-in restore path. An interrupted
run can be forked from a verified saved checkpoint, but it is never resumed
automatically. Remote and multi-user deployment and authentication are out of
scope.

The command-line service starts without third-party LLM adapters, so configured
LLM profiles remain unavailable there until an embedding server registers an
adapter. Python integrations can pass a `BackendAdapterRegistry` to
`create_server(profile_adapters=...)`; adapters receive the server-side profile
including any local `secret_ref` and must return an `LLMBackend`. The management
shell cannot register providers or submit credentials. Only the built-in
`simple.default` and `ocelot.default` profiles are accepted for those kinds;
custom simple/Ocelot variants are rejected because the engine does not route
their settings separately.

Authored scenarios may opt into management cast generation with a
`management_cast_generation` declaration. The bundled `management_cast_demo`
scenario declares schema version 1 and supports up to eight generated residents
because it has eight free home cells. A scenario may declare up to 100 generated
actors, subject to its map's walkable, unoccupied home cells and the 200-actor
service limit. Each group selects a declared role, a server backend profile, a
population count, and optional bounded age/skill/literacy/capability/learning
ranges. Generated names are stable from group IDs (`group-001`, etc.); each
generated actor gets a distinct free home. Authored home sharing is preserved,
but the generator does not infer household relationships or share generated
homes. The generator uses deterministic trait streams derived from the run's
single world seed and scenario/config identity, and records its version, inputs,
generated actor data and hash in the immutable run configuration. Preview and
launch use the same resolved actor records. `town100` does not declare this
contract and rejects cast-generation options; its normal cast remains unchanged.

### Recorded reports and comparisons

The report shown under **Reports & events** is a read-only live readout of the
current in-memory run. Use **Record report snapshot** to preserve an immutable
report for comparison; snapshots and their run/configuration provenance are
stored in the local registry and survive a service restart. A restart still
does not restore the world itself. Compare selects the latest recorded snapshot
for each selected run. The comparison currently supports schema
`bigville/report/1` and a small allowlist of count/value metrics with explicit
units. Unknown schemas, absent snapshots, missing values, and non-numeric
values are shown as unavailable. Population/social counts have common defined
units; economic values are compared only when scenario source and content
identity match. No values are interpolated or reconstructed.

The API offers `POST /api/management/v1/runs/{id}/report-snapshots` to capture,
`GET /api/management/v1/runs/{id}/report-snapshots` to list,
`POST /api/management/v1/reports/compare` with `{"run_ids":[...]}`, and
`GET /api/management/v1/runs/{id}/reproducibility` for a downloadable metadata
document. Reproducibility export includes normalized configuration, its hash,
capability/profile revisions, template/checkpoint references, and report
snapshot IDs. It omits secret-bearing keys and never contains provider
credential values. Engine build identity is copied from the normalized run
configuration; if no canonical identifier was available at creation, it stays
null rather than being guessed.

The shell remains a local, single-user operator tool. Runs use in-memory worlds;
on service restart unfinished runs are marked interrupted and are not resumed.
Checkpoints are a separate supported recovery path with adapter restrictions
described above. Agent perspective responses are server-filtered and do not
include referee reports. At narrow widths the navigation and form controls
stack, while wide comparison tables scroll inside their own region. Inputs and
actions retain visible labels, headings, status announcements, and keyboard
focus behavior. There is no remote/multi-user deployment or authentication
claim.

#### Troubleshooting

- If the shell does not load, start the service with `python -m
  bigville.management.http` and check the local `/api/management/v1/health`
  endpoint. The service refuses non-loopback bind addresses.
- If an LLM profile is unavailable, register its adapter in the server process
  and verify the adapter ID and local profile revision. The shell cannot submit
  credentials or make an unregistered provider ready.
- If a run is marked interrupted after restart, its world was in memory and is
  not recoverable from run metadata. Fork from a supported checkpoint when one
  exists, or create a new run from the saved template/configuration.
- If a comparison says a value is unavailable, check that each run has a
  recorded snapshot and that the report schema is supported. Economic values
  additionally require matching known scenario and engine/pack source identity.
