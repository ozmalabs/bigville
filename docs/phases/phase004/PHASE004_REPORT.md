# Phase 004 report: located gathering and land-based work

## Summary

A gathering recipe (`gathered_from`: woodlot, orchard, kitchen_garden, quarry) now runs only for an actor
standing on the site of that kind, with at least one batch of the site's stock. Starting a batch draws that
stock. Each site regrows once per period (one day) up to its capacity. The founding map places one site per
kind, on cells that no existing home, workplace, farm plot, deposit, or building uses. The new data is in a
separate `GATHERING_SITES` table. The self-test is 0 errors and 0 warnings. The full suite passes apart from
three Ocelot-adapter tests in the other session's files.

## Changes

Data (packs):
- `packs/bigville/world/gathering_sites.json` (new): the `GATHERING_SITES` table, four rows, with `_doc`.
- `packs/bigville/pack.json`: manifest entry `GATHERING_SITES` after `RESOURCE_DEPOSITS`.
- `packs/test_hamlet/world/gathering_sites.json` (new): an empty `GATHERING_SITES`.
- `packs/test_hamlet/pack.json`: manifest entry `GATHERING_SITES`.

Domain:
- `domains/world_affordances.py`: binds `GATHERING_SITES = _PACK["GATHERING_SITES"]`.
- `domains/knowledge.py`: `GATHERING_SITES` joins the place rows (derivation), the known places, and the
  knowledge-spec check. Without this, the new sites would have no knowledge specs.
- `domains/bigville_entities.py`: `_check_gathering_sites` (new), called from `check_consistency`.

World:
- `worlds/bigville_town100_world.py`, `build_town_100`: places `layout["sites"]` after homes and farms.
- `worlds/bigville_world.py`, hunks by function:
  - `__init__`: `self._gathering_sites = {}`.
  - `sanity_report`: the capability-gap check uses `_capable`.
  - `populate_town100`: calls `_place_gathering_sites(layout)` after the deposits.
  - New block after `extract_resource`: `add_gathering_site`, `_place_gathering_sites`,
    `gathering_site_cell`, `gathering_stock`, `_site_has_batch`, `_site_supplies`, `_at_gathering_site`,
    `_draw_gathering_site`, `_regrow_gathering_sites`.
  - `_actor_options`: a `move` option to a site, placed before the recipe loop.
  - `can_make`: uses `_capable`.
  - `_open_job`: draws the batch from the site.
  - `_can_attempt` (new: `_capable` and `_at_gathering_site`) and `_capable` (the old body, unchanged).
  - `tick`: calls `_regrow_gathering_sites()` when the day counter advances.
  - Not mine: the `food` flag in `_actor_options`' fetch option, and `resident_plan_from_context`. The
    other session owns both, and the supervisor must stage this file by hunk.

Tests:
- `tests/test_phase004_located_gathering.py` (new): 19 tests.

Report: `docs/phases/phase004/` (this file, `snapshot_placements.py`, `head_placements.json`,
`after_placements.json`).

No existing test was edited.

## Site data and sources

All four rows are APPROX. No source gives stock, growback, capacity, or public spread for these sites. They
are sized from the recipe yields (out_qty 2 to 6 per batch) and the RESOURCE_DEPOSITS scale (stock 60,
growback 3 to 4, capacity 120), and the public spreads follow the lumber and stone deposits. The table's `_doc`
states this.

| kind | anchor | stock | growback/day | capacity | topic | public | after_years |
|---|---|---|---|---|---|---|---|
| woodlot | [29, 3] | 60 | 6 | 120 | fuel_and_light | 0.6 | 0 |
| orchard | [38, 22] | 60 | 6 | 120 | agriculture | 0.6 | 0 |
| kitchen_garden | [10, 23] | 40 | 4 | 60 | agriculture | 0.8 | 0 |
| quarry | [42, 10] | 40 | 3 | 80 | carpentry_and_building | 0.4 | 3 |

The anchors are authored. The layout has no real-world source.

## Placement

`build_town_100` places the sites after homes and farms. Each site takes the nearest GRASS cell of the founding
component to its anchor that no other placement uses. The sites add no tiles and move nothing.

- Woodlot (29, 3) is beside the forest body. Quarry (42, 10) is beside the rock face. Orchard (38, 22) and
  kitchen garden (10, 23) are on open grass.
- Checked: each site is walkable, in the largest component, and distinct from every home, workplace, farm,
  deposit, and other site.
- Existing placements: the `layout` without `sites` hashes to
  `e302d08cf52d0e521f008714847b7c81e6e792af2754177fc91c40d4bfcf87ee` (sha256 of its sorted JSON)
  at HEAD and now. A full placement snapshot of the 100-resident town (deposits, actor, land, household,
  animal, place, building-site, shop, and infrastructure cells) is byte-identical to a `git archive` export of
  HEAD 4e9c97d (`head_placements.json` and `after_placements.json`, both sha256 `2981454429…`).
- Each site has one cell and one site per kind. Sites are not per household. That is what the brief asked for,
  and it means one kitchen garden with capacity 60 serves all 100 residents.

## Admissibility rule

A gathering recipe is admissible only when all of these hold:
1. The actor's cell is the site's cell. Standing next to it is not enough.
2. The site's stock is at least the recipe's `out_qty`.
3. The existing checks still pass: skill floor, season, strength for open recipes, and tools.

`do` and `start` both go through `_can_attempt`. `_actor_options` offers `work` only on the site. Off the site,
it offers a `move` to the site when the actor could do a batch there, the site holds a batch, and the cell is
reachable. The `move` option is the one change to what residents are offered, and I added it because without it
no resident could reach a site.

A batch is drawn from the site's stock when its job opens (`_open_job`). A timed batch therefore takes its stock
at the start, and its output arrives when the job finishes. If the job is later blocked (for example a tool
breaks), the stock is already spent.

## Regrowth

`tick()` calls `_regrow_gathering_sites()` each time the day counter advances. Each site gains its `growback`
and stays at or under `capacity`. One day is 96 ticks (`TIME.ticks_per_period`).

Existing deposits (fish, lumber, stone) do not regrow in `BigvilleWorld`. I checked this: the fish stock went
from 60 to 50 after an extraction of 10, and was still 50 after one day. The growback rule exists only in the
resource seeds (`bigville/seeds/bigville_resource_extract.json`, `bigville_econloop.json`). Neither is in the
world's `ENGINE_SEEDS`. This phase did not change deposit behaviour.

## Validation

| command | result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0) (before and after) |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS (0), WARNINGS (0) |
| `python3 tools/generate_seeds.py --check` | exit 0; "match pack 'bigville' (22 files)" |
| `python3 tools/generate_seeds.py` | rewrote the 22 files with the same bytes. `git status` shows no seed changes from this phase. |
| `python3 -m pytest -q tests/test_phase004_located_gathering.py` | 19 passed |
| `python3 -m pytest -q tests/test_phase013a_packs.py` | 8 passed (after the exporter formatting fix below) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 505 passed, 3 failed, 2 skipped (the 3 failures are below) |
| same, ignoring the other session's three failing files | 505 passed, 2 skipped, 0 failed |

Before my edits, the same shared tree gave 486 passed, 3 failed, 2 skipped. The 19 new tests bring it to 505.

Failures, verbatim, all in the other session's files:
- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
- `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
- `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

Each fails with: `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`, raised as
`OcelotUnavailableError`. They are not from this phase.

One failure of mine, now fixed: my first `gathering_sites.json` was not in the exporter's canonical form, so
`test_phase013a_packs::test_export_rerun_is_byte_identical` failed. I replaced the file with
`tools/export_pack.py --pack bigville` output. Its only change was to expand the `anchor` arrays.

I did not run a village (`run_village`) and have no gathering-throughput figures.

## Limits

- The stock, growback, capacity, and public figures are APPROX. They are untested against real demand.
- The 100-resident town now has sites, but I did not run it. Whether one kitchen garden and one woodlot
  supply the cast is unknown until a village run.
- With the new place rows, every resident is aware of the woodlot, orchard, and kitchen garden, and 98 of 100
  are aware of the quarry (`_public_awareness`, derived from the APPROX public spreads). `bigville/game.py`
  (`_derived_knowledge_memories`, the other session's file) turns each aware row into a private memory record,
  so residents start the game knowing these places exist. I did not run the game to observe that.
- Sites are not in the viewer's affordance list (`build_town_100`'s `affordances`), so the map does not draw
  them. Map art for the sites is out of scope.
- `BigvilleTown100World` (the legacy class over `BigvilleTradeWorld`) does not inherit `BigvilleWorld`. It has no
  sites and no site gating, and its gathering code is unchanged. Only `BigvilleWorld.from_town100()` and a
  scenario world with explicit sites gate gathering.
- A bare `BigvilleWorld()` has founding-map cells but no sites. A test places one with
  `add_gathering_site(kind, cell)`.

## Open questions

1. Should fish, lumber, and stone deposits regrow in `BigvilleWorld`? Today they do not. Fixing it changes
   the balance model and existing deposit behaviour, so I left it for a separate phase.
2. Should the kitchen garden be one per household, as a daily kitchen supply? The brief asked for one site per
   kind.
3. Should a site's stock be set by a demand model rather than an APPROX table value?

## Deviations from the brief

- Write scope. The brief named four files, but the user's context also required pack data and the map builder,
  and the knowledge specs needed `domains/knowledge.py`. I changed `domains/knowledge.py`,
  `worlds/bigville_town100_world.py`, both pack manifests, and the two new pack table files. I did not touch
  `docs/FEATURE_PHASES.md` or any other session file.
- Separate table, not `RESOURCE_DEPOSITS`. Sites share the `ResourceDeposit` node and the placement method, but
  they have no tile body, are not items, and must stay out of the item pipeline, the balance model, and the
  store. `RESOURCE_DEPOSITS` feeds all three.
- Stock is drawn at job open, not at completion. A completion-time check could leave a finished job waiting
  forever if the actor walked away.
- The `move` option. The brief said the world publishes affordances, and this adds one. Without it, no resident
  could reach a site.
- Regrowth is Python, not a seed rule, because the main world's engine does not load the growback seed.
