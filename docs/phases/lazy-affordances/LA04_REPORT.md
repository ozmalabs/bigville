# LA04 — Lazy cognition for the deterministic simple backend

Status: complete. Phase LA04 of the lazy-affordances plan.
Base commit: `9d54a86` (LA03, branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

### Observation enrichment (`BigvilleWorld.observe`)

The LA03 observation still publishes entities and capabilities, never the
legal menu. LA04 adds only the local facts the cheap backend needs to propose:

| Field | Shape |
|---|---|
| `actor` | the observing actor's stable id |
| `inventory_details` | `{kind, qty, edible, meal_value, prepared, tool}` per carried kind; no recipe validation |
| `held`, `holder`, `holding` | whether the actor is held, by whom, and whom it holds |
| `places` | `{home, work, market, buildings, gathering_sites, farms}`; stable cells, unknown places omitted |
| `cell.animals` | `{id, name, species, alive, task}` for animals on the actor's cell |
| `cell.crops` | `{id, kind, stage, mature, age, grow_periods, thirst}` for living crops on the cell |
| `cell.building_projects` | `{id, name, project, status, progress, labour, inputs}` on the cell |
| `cell.infrastructure` | `{id, kind, condition, maintenance}` on the cell |
| `cell.shops` | `{trade, input_kind, output_kind}` on the cell |
| `cell.land[].sow_kind` | the pack's current rotation crop for an arable parcel, when it names one |
| `nearby_actors[].health/injury` | the read-offs needed to name a local patient |
| `containers_in_reach[]` | now also includes accessible world containers on the actor's cell, tagged `world_container: true`, with an open/locked/contents summary |

`places` is bounded and deterministic: 24 buildings, 8 gathering sites, 24
farm parcels, all sorted. `containers_in_reach` is deduplicated by id, with the
world container preferred when a physical object shares the id.

`observe` remains read-only and JSON-safe. It does not call
`actor_affordances()` or `_actor_options()`. The LA03 tests still pass without
modification.

### Cheap backend lazy candidates

At the top of `DeterministicBackend.decide`, when `context.affordances` is empty
and `context.observations["entities"]` is present, the backend builds
`self._lazy_candidates(context)` and assigns it to `context.affordances`. The
rest of `decide` is unchanged: goals, filters, PSI/CAN valuation, selection,
speech and continuation all run on the generated candidates.

The generator returns plain menu-shaped dicts with `action`, `kind`, `trade`,
`recipe`, `target` and `score`, plus direct stable params accepted by
`_enact_plan`:

- **eat** — carried `inventory_details` entries that are edible, when hunger > 0;
- **rest** — when energy is below `rest_energy_threshold`;
- **sleep** — only at night or below `collapse_guard_energy`, with `safe` and
  `lateness` read-offs so the existing sleep path can select it;
- **move** — home/work/market, local buildings, gathering sites, farm parcels,
  adjacent `cell.exits`, and nearby actors at distance > 0; every candidate
  carries both `destination` (the cell) and a stable label, and cells are
  deduplicated;
- **work** — the current job's recipe, recipes whose `at_building` matches a
  building on the actor's cell, then up to eight common recipes; output `kind`
  and `intensity: 1.0` included when cheaply known;
- **fetch** — each reachable open world container with contents, by kind, with
  `source` and `physical_source: "container"`;
- **put** — each carried kind into each reachable open world container;
- **give/transfer** — carried kinds against co-located actors; `transfer` is
  still gated by `SimplePolicy.allow_transfers`, while the direct `give` form
  is proposed as this phase's design asks;
- **move_object** — visible grabbable objects against self, nearby actors,
  reachable containers, `table` and `world`, gated by
  `SimplePolicy.allow_object_moves` as in menu mode;
- **tend_animals** — local animals, using the pack's husbandry task when it
  names one, otherwise `tend` (the world refuses if that is not a task);
- **water/harvest** — local crops, using the observation's thirst/maturity;
- **sow/fertilise** — direct `land`/`sow_kind` when the pack names a crop,
  otherwise sow is skipped; fertilise is proposed for local arable parcels;
- **build/maintain/care** — only when the observation names a local project,
  infrastructure below 0.8 condition, or a co-located ill/injured patient;
- **struggle/release** — when the observation reports `held`/`holding`.

No candidate uses a `target:N` key. The list is sorted with a stable key,
deduplicated by construction and capped at 64 (needs actions survive the cap).
Lazy contexts also copy the root observation aliases (`hunger`, `energy`,
`calendar`, …) from `entities` so the existing PSI/CAN model and goal rules
read the same values menu mode publishes. Lazy work knowledge unions the
character's recipe memories with the observation's `known_recipes`; menu mode
does not do this.

### Refusal fallback

`last_outcome` is read from the lazy context (top level or
`entities.last_outcome`). If the previous major action was refused and the
backend's retained `last_choice` names the same action, the exact physical
action/params signature is removed from the candidate list before scoring. The
signature ignores scores, labels and trace fields, so only a genuinely identical
proposal is suppressed.

If nothing scores, or the model's choice still matches the refused signature,
`_refusal_fallback` makes a fresh proposal: `rest` when energy is low, otherwise
a move to an adjacent exit, otherwise no action. It never rewrites the refused
action into a different valid action silently; the world validates the fallback
normally. Menu mode never enters this path.

## Candidate/selection behaviour

- Lazy mode reuses the existing goal update, role preference, hunger/food,
  meal-value, intoxication, hook, resume-job and path-preference scoring.
- Lazy mode does not build `recipient_interfaces`, an agent view, or the menu.
- Menu mode is untouched: no `entities` key, no lazy candidates, no fallback.

## Commands and exact results

```bash
python3 -m pytest -q tests/test_lazy_cheap.py tests/test_lazy_observation.py \
  tests/test_lazy_target_resolution.py -p no:cacheprovider
# 59 passed in 51.23s

python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
# 66 passed in 57.65s

python3 -m pytest -q tests/test_simple_life.py tests/test_fix_simple_village.py \
  tests/test_phase059_autopilot.py tests/test_phase055_concurrency.py \
  -p no:cacheprovider
# 63 passed, 1 failed in 289.97s
```

The single failure is the timing assertion in
`tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`:

```text
SPEEDUP sequential=13.69s concurrent=10.84s ratio=0.79 calls=13
assert concurrent_seconds < 0.75 * sequential_seconds
```

The two semantic assertions before it passed: the sequential and concurrent
digests were identical and the provider calls were identical. The host was
contended (load average ~7.5 with another full pytest suite at ~100% CPU), and
the same timing-only failure reproduced on two isolated retries (ratios 0.76
and 0.79). This is an environment-sensitive throughput test, not a menu
behaviour change in this phase.

`tests/test_lazy_cheap.py` alone: 12 passed, including the 4-turn town100 run,
the direct-param check, the bounded/deterministic list check, the refusal
fallback, and the two-turn menu trace digest
`a3aa31304905a0f8705a41135eaade7ce50ed5d63758e7ebf056a1532ff5788d`.

## Refusal observations

- Four-turn lazy town100 run, seed 305000: **0 refusals** (`{}` by reason).
  All 100 residents applied one action per turn (400/400). In this seed every
  chosen and applied action was `work`; the run does not exercise refusal
  variety. This is reported, not asserted to a fixed number.
- Deliberate invalid proposal: a `move` to cell `(99, 99)` was refused with the
  world's existing `unknown_target` code. The turn still advanced. The next
  lazy turn did not repeat `(99, 99)`; the fallback proposed an adjacent-cell
  move.
- The lazy tests also exercise fetch/put against a world container, eat from a
  carried loaf, daytime rest and night sleep, move_object to self, and give to a
  co-located actor without relying on menu target keys.

## Limitations and semantic caveats

- Exact-refusal suppression compares the retained proposal's physical params.
  The world's `last_outcome` records only the action and reason, so if the
  backend has no retained params it can only suppress a parameterless repeat.
  A refused action re-proposed with different params is a genuinely different
  proposal and is allowed; this is intentional.
- `give` is proposed by default in lazy mode, whereas menu mode publishes only
  `transfer` and gates it behind `allow_transfers`. Lazy mode is opt-in, but
  this is a real behavioural difference LA06 should evaluate. Give/transfer
  remain same-cell proposals; the world refuses a handover at distance 1, so
  the design's optional distance-1 give is skipped.
- Work candidates include common recipes without ingredient/tool/site
  validation, so lazy mode can spend turns on world refusals. In this seed the
  chosen work happened to apply, so refusals were zero; other seeds may differ.
- `move_object`, `transfer` and travel retain their existing policy gates, so a
  candidate can exist without being chosen.
- `places` is deliberately bounded and omits unknown homes/workplaces/markets.
  The self id is now published as `actor` because a lazy proposal needs a stable
  destination for moving an object into its own hands.
- World containers are exposed only when accessible and on the actor's current
  cell. Distant containers are reached by `move`, not by an impossible fetch.
- Sowing is proposed only when `_rotation_crop` names an in-season crop with
  seed; fertilising is proposed for local arable parcels and may be refused as
  `not_needed` or `out_of_stock`.
- The concurrency timing failure above is environmental; it should be re-run on
  an idle host before being quoted as a regression or a pass.

## Handoff to LA05

LA05 can consume the lazy observation directly:

- `inventory_details`, `places`, `cell.*`, `containers_in_reach` and
  `nearby_actors` give a bounded entity list with stable ids/cells for a lazy
  prompt packet.
- `last_outcome` and `entities.last_outcome` are the refusal feedback to show
  the provider on the next turn.
- Proposals should use the same direct params as `_lazy_candidates`; no
  `target:N` keys are needed.
- `agent_view` should expose this observation in lazy mode; the full menu stays
  an explicit on-demand query for Ocelot/UI action pickers.
- Ocelot's `replace_options` path remains menu-only; lazy mode must either
  request a menu explicitly or consume the observation/proposal adapter.
