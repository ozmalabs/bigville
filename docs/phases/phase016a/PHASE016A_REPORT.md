# Phase 016a: the founding town's content as pack data

## Summary

The founding town's content now lives in the bigville data pack. The cast's roles and counts, class
and literacy shares, anchor names, name pools, personality ranges, causal-resolution mixture, map
layout, workplace anchors, building sites, place labels, anchor fallbacks, and deposit kinds are all
pack tables. The town code keeps the mechanics and reads those tables through the world's pack view.

`BigvilleWorld.from_town100(data_pack=...)` builds the founding town of a pack. The default pack is
bigville. `packs/test_hamlet` has empty founding tables, so `from_town100` refuses it with a clear
error.

The 100-resident town is unchanged. The founding-town digest (from_town100, its cast records, its map,
and three village work ticks) is identical at HEAD and after the change. One legacy class changes
(see Deviations): `BigvilleTown100World` now reads its deposit numbers from the pack, so its lumber
growback is 4.0, not the 3.0 it hard-coded.

This is the first half of Phase 016. Seeding the cast from JOBS and redrawing genealogy are 016b.

Start `git status --short`: 10 modified tracked files and 15 untracked entries, all from the other
session (listed under "Not mine"). HEAD was 4e2876f.
End `git status --short`: the same entries, plus my new and modified files listed below.

## Changes

### New tables (packs/bigville)

| File | Table | Holds |
|---|---|---|
| `population/founding_cast.json` | `FOUNDING_ROLES` | 25 rows: role, count, group, role_identity_mean and sd, workplace. Counts sum to 100. |
| | `FOUNDING_CLASS` | `by_group` (rich and middle shares), `literacy_by_class`, `station_by_group` |
| | `FOUNDING_ANCHOR_NAMES` | role to register name (mayor John, pastor Mary, baker Marjorie Dough, fishmonger Doreen Ferrety, banker Scrooge) |
| | `FOUNDING_DRAW_BOUNDS` | role-identity clip range, 0.02 to 0.98 |
| `population/founding_names.json` | `FOUNDING_FIRST_NAMES`, `FOUNDING_LAST_NAMES` | the two name lists (72 first names, 55 last names); order is part of the draw |
| `population/founding_personality.json` | `FOUNDING_PERSONALITY` | the 12 drawn traits: mean, sd, lo, hi |
| | `FOUNDING_CAUSAL_RESOLUTION` | the two-component mixture for `resolution_bins`: floor and ceiling mean and sd, ceiling weight, lo, hi |
| `world/founding_map.json` | `FOUNDING_MAP` | width and height; road rows and columns with meander phases; meander offsets and step; square rectangle, centre, and label; resource bodies (water, tree, wall) as inclusive corners; scattered trees; farm-plot grid |
| | `FOUNDING_DEPOSITS` | `fish`, `lumber`, `stone` |
| `world/founding_sites.json` | `FOUNDING_WORKPLACES` | 17 workplace anchor cells |
| | `FOUNDING_BUILDING_SITES` | 30 fixed building footprint origins (each a BUILDINGS kind) |
| | `FOUNDING_PLACE_LABELS` | 16 landmark labels |
| | `FOUNDING_ANCHOR_ALIASES` | 22 building-to-workplace fallbacks |

Each file has a `_doc` with the sources or an APPROX mark. Counts, means, class and literacy
shares, and the map are authored, so they are marked APPROX or "authored; no real-world source".
The causal-resolution citations (Frederick 2005; Stieger and Reips 2016; Miller 1956; Preston and
Colman 2000) are carried over from the original code comments. The research and prereg files those
comments name (`CAUSAL_GRANULARITY_POPULATION_DISTRIBUTION_RESEARCH.md`,
`BIGVILLE_CAN_INTEGRATION_PREREG.md`) are not in this checkout, so I could not verify them. The
`_doc` says so.

### Empty tables (packs/test_hamlet)

The same 14 table names, in the same files, with empty values (`[]`, `{}`, or `""`). The hamlet's
`pack.json` lists them. An empty `FOUNDING_ROLES` means "no founding town".

### Manifests

`packs/bigville/pack.json` and `packs/test_hamlet/pack.json` each gained 14 table entries at the end.

### Moved constants

| Was (HEAD) | Now |
|---|---|
| `ROLE_SPEC` (worlds/bigville_town100_world.py) | `FOUNDING_ROLES` |
| `_CLASS_BY_GROUP`, `_LIT_BY_CLASS` (inline in `generate_cast100`) | `FOUNDING_CLASS.by_group`, `FOUNDING_CLASS.literacy_by_class` |
| station map `{"low": "labouring", ...}` (inline in `populate_town100`, bigville_world.py) | `FOUNDING_CLASS.station_by_group` |
| role-identity clip `0.02, 0.98` (inline in `generate_cast100`) | `FOUNDING_DRAW_BOUNDS.role_identity` |
| `_ANCHOR_NAMES` | `FOUNDING_ANCHOR_NAMES` |
| `_FIRST`, `_LAST` | `FOUNDING_FIRST_NAMES`, `FOUNDING_LAST_NAMES` |
| `_PARAM_SPEC` | `FOUNDING_PERSONALITY` (dict of mean, sd, lo, hi) |
| `_RES_FLOOR_MEAN/SD`, `_RES_CEIL_MEAN/SD`, `_RES_CEIL_WEIGHT`, `_RES_LO`, `_RES_HI` | `FOUNDING_CAUSAL_RESOLUTION` |
| `W100`, `H100`, and the inline road rows and columns, phases, meander offsets, square, resource bodies, scattered trees, farm grid (in `build_town_100`) | `FOUNDING_MAP` |
| `_TOWN100_DEPOSITS` | `FOUNDING_DEPOSITS` |
| `_WORK_ANCHORS` | `FOUNDING_WORKPLACES` |
| `_BUILDING_SITES` | `FOUNDING_BUILDING_SITES` |
| `_KINDNAME` labels and "Market Square" (inline in `build_town_100`) | `FOUNDING_PLACE_LABELS`, and `FOUNDING_MAP.square.label` |
| alias dict (inline in `_anchor_for_building`, bigville_world.py) | `FOUNDING_ANCHOR_ALIASES` |
| `BigvilleTown100World._TRADE_RECIPE` | existing `SHOP_CHAINS` (same four trades and values) |
| literal deposit numbers and store kinds in `BigvilleTown100World.__init__` | existing `RESOURCE_DEPOSITS` (stock, growback, capacity), `FOUNDING_DEPOSITS` (store kinds) |

### Stays in code

- The map builder's algorithms: the meander and road-linking functions, the largest-component
  search, plot selection (`_take`), and the rule that homes equal the sum of role counts.
- `SEED_DEFAULT = 305000`: the default seed of `from_town100`, `create_world`, and the builders. It is
  a runtime argument, not a table.
- `NAME_POOL_DRAW = 200`: the name draw size. It sets the stream length, so it is code.
- `DRAW_CLIP_DECIMALS = 4` (read by the Ocelot adapter as a precision contract), `_draw_clip`, the
  RNG stream offsets (+7, +13), the draw order, and the mixture's sampling rule.
- `_TILE_BY_NAME`: maps tile names to the simulation's tile codes.
- `populate_town100`: literacy-based `capability` (0.9 or 0.55), `skill=0.7`, and the household and
  land logic. Phase 016b rewrites this cast, so I left it. Its `skill=0.7` matches `ACTOR_DEFAULTS.skill`.
- `run_village`: it builds no town. It requires the cast that `from_town100` built, and it already reads
  `self.E`. It is unchanged.
- The cast record's `description` string ("100-resident bigville cast ..."). It is text only.

### Code changes

- `domains/world_affordances.py`: binds the six `FOUNDING_MAP`, `FOUNDING_DEPOSITS`,
  `FOUNDING_WORKPLACES`, `FOUNDING_BUILDING_SITES`, `FOUNDING_PLACE_LABELS`, and
  `FOUNDING_ANCHOR_ALIASES` tables from the pack.
- `domains/population.py`: binds the eight cast and personality tables from the pack.
- `domains/bigville_entities.py`: new `_check_founding_town(errors, warnings, info)`, called from
  `check_consistency`. Rules:
  - All required founding tables are filled, or all are empty. A partly filled pack is an error.
  - Each role's group has a `by_group` entry, and each group has a station that is a
    `STATION_EDUCATION` key.
  - Each workplace is a `FOUNDING_WORKPLACES` key, a `FOUNDING_DEPOSITS` kind, or `farm`.
  - Each building site is a `BUILDINGS` kind and lies on the map. Each place label names a workplace.
  - Each deposit's tile has a resource body on the map. Body rectangles, the square, roads, trees, and
    farm origin lie on the map.
  - The name pool can cover every resident who draws a name.
  - Anchor roles exist in `FOUNDING_ROLES`.
  - A role in none of JOBS, TRADES, or CAST_ROLE_TRADES is info, not an error.
  - Alias targets that name no workplace are info. They fall back to the market, as at HEAD.
- `worlds/bigville_town100_world.py`: the cast, the map, and the adapter read the view.
  - `build_town_100(seed, entities=None)`, `generate_cast100(layout, seed, entities=None)`: default
    to the default pack, so `worlds/bigville_social_seed.py` keeps its call form.
  - `BigvilleTown100World` takes `data_pack`. It refuses a pack with no founding town, and a pack
    missing a `FOUNDING_DEPOSITS` deposit.
  - Compatibility views, kept for callers that read the private names (see Limits):
    `_PARAM_SPEC` (the tuple form of `FOUNDING_PERSONALITY`), `_draw_resolution_bins(rng,
    mixture=None)`, and `_name_pool(n, rng, first=None, last=None)`.
- `worlds/bigville_world.py` (my edits at about lines 1312-1346, 1378-1383, 1868-1880, and 1985-2036):
  - `_install_map`: builds the founding map only if the pack has one. Otherwise the world has no
    tiles, sites, or deposits. The width and height read with `.get`.
  - `_anchor_for_building`: the alias table comes from `self.E.FOUNDING_ANCHOR_ALIASES`.
  - `from_town100(..., data_pack=None)`: the new keyword is passed to the constructor. The old call
    form works.
  - `populate_town100`: raises `ValueError` for a pack with no founding town. Reads the cast and the
    station map from `self.E`.
  - `run_village` is unchanged.

Not mine, in the same file: the other session's hunks at about lines 5943 (`food` flag) and 6234
(`resident_plan_from_context`). They are untouched. The supervisor needs to stage the two sets
separately.

### Tests and tools

- `tests/test_phase016a_founding_town.py` (new, 3 tests): the bigville town is built from the pack, with
  its role counts and deposits; a child pack that changes the first-name pool and moves one role count
  builds a different town and keeps the inherited map, with no code change; the hamlet has no founding
  town, its self-test is clean, and `from_town100` and `BigvilleTown100World` refuse it.
- `docs/phases/phase016a/author_founding_pack.py`: wrote the tables from the HEAD constants, then read
  them back through `load_pack` and compared each value and key order. It was run once and refuses to
  run again. It cannot run on the current tree, because it imports `T.W100`, which is gone.
- `docs/phases/phase016a/founding_town_digest.py`: the digest (see Validation).
- `docs/phases/phase016a/compare_digests.py`: section-by-section comparison of two digests.

### Not mine

Modified before my start: README.md, bigville/backends/ocelot.py, bigville/game.py,
bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py,
worlds/bigville_world.py. Untracked before my start: bigville/game_persistence.py,
bigville/mixed_ocelot_scenario.py, bigville/world_persistence.py,
docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md, docs/ocelot-integration-baseline.md, docs/runs/,
tests/test_bigville_game_persistence.py, tests/test_bigville_graph_persistence.py,
tests/test_bigville_ocelot_communication.py, tests/test_bigville_ocelot_fresh_process.py,
tests/test_bigville_world_persistence.py, tests/test_mixed_ocelot_checkpoint_parity.py,
tests/test_mixed_ocelot_village.py, tools/run_mixed_ocelot_scale.py,
tools/run_mixed_ocelot_village.py.

Not edited: `docs/FEATURE_PHASES.md`, `bigville/village_eval.py`, any existing test.

## Validation

| Check | Command | Result |
|---|---|---|
| Self-test, bigville | `python3 domains/bigville_entities.py` | exit 0; ERRORS 0, WARNINGS 0. INFO 8 to 10: two new lines (the founding-town summary and the alias fallbacks). Diff: `selftest_before.txt`, `selftest_after.txt` |
| Self-test, hamlet | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0, WARNINGS 0. INFO 5 to 6: "FOUNDING TOWN: none" |
| Negative check | a child pack with a bad workplace, a bad group, and an anchor role that exists in no row | 4 errors, each naming the table and the value (run by hand, not in the test suite) |
| Digest, HEAD | `git archive HEAD`, then `PYTHONHASHSEED=0 python3 docs/phases/phase016a/founding_town_digest.py` | saved as `digest_head.json.gz` |
| Digest, after | the same command on the working tree | saved as `digest_after.json.gz` |
| Digest, comparison | `python3 docs/phases/phase016a/compare_digests.py digest_head.json.gz digest_after.json.gz` | `digest_comparison.txt`: every section identical except `adapter` (see below) |
| Phase 013b digest | `PYTHONHASHSEED=0 python3 docs/phases/phase013b/default_digest.py` | byte-identical to its stored `digest_working_tree.json` |
| Suite, HEAD | clean export: `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 394 passed, 86 s (`pytest_head_clean_export.txt`) |
| Suite, after | the same command on the working tree | 3 failed, 419 passed, 2 skipped (`pytest_after_full.txt`). Failures below |
| Suite, after, other session's Ocelot files ignored | same command with `--ignore` for the 3 failing files | 419 passed, 2 skipped, 0 failed (`pytest_after_ignoring_other_session_ocelot_files.txt`) |
| Suite, with Ocelot checkout on the path | `PYTHONPATH=/home/matt/ozmadev/ocelot pytest ...` | 420 passed, 2 failed, 2 skipped (`pytest_after_full_with_ocelot_on_pythonpath.txt`). Failures below |
| New tests | `pytest tests/test_phase016a_founding_town.py` | 3 passed |

The three failures in the default environment. These are the other session's files, untracked, and
they import `worlds.bigville_ocelot_adapter`, which lives in the Ocelot checkout and is not on this
environment's path:

- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`:
  `E   ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`
- `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`:
  `E       ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`
- `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`:
  `bigville.backends.ocelot.OcelotUnavailableError: Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter and its dependencies on PYTHONPATH; select 'simple' for local NPCs. Adapter import failed (ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter')`

With `PYTHONPATH=/home/matt/ozmadev/ocelot`, those three pass. But the Ocelot checkout has its own
`domains` package, which then shadows this repo's. Two `test_phase013b_data_pack.py` tests run
`python -m domains.check` in a subprocess and fail with `No module named domains.check`. On the clean
HEAD export with the same `PYTHONPATH`, `test_phase013b_data_pack.py` fails at collection. So the clash
predates this phase.

Test-count changes: no existing test was edited, and no test number changed. The only new test file
is `tests/test_phase016a_founding_town.py`.

Not run: a 100-resident `run_village` (the brief did not ask for it), and any performance measurement.

## Digest result

`founding_town_digest.py` builds `BigvilleWorld.from_town100()` and records, in canonical JSON:

- every resident's graph attributes, position, household, and held kin terms;
- households, land, farm cells, stock, building sites, places;
- the map layout, a SHA-256 of the tile grid, the map affordances, and the map node;
- node-type counts of the whole graph (Agent 130, MapCell 2080, Kin 924, KinTerm 2849, Union 197, Household 100, Land 9, and the rest);
- the kinship index sizes, and the world RNG state hash;
- the same state after three `_village_work_tick` calls, with each return value;
- the cast record (`_cast100`, including personality params and `resolution_bins`) and `_scenario_character_data`;
- `build_town_100(305000)`: grid hash, layout, affordances;
- `BigvilleTown100World(seed=305000)`: residents, cast, deposits, shops, stores.

Results (`digest_comparison.txt`):

- Sections `founding_town`, `after_three_village_work_ticks`, `returns_of_three_village_work_ticks`,
  `cast100_record`, `scenario_character_data`, and `build_town_100`: identical.
- Section `adapter`: identical except `adapter/deposits[1]/growback`, which is `3.0` at HEAD and `4.0`
  after the change (the lumber deposit of the legacy adapter).

Before any code edit, the working tree's digest was byte-identical to HEAD's (the first digest run, which
covered the same from_town100 sections).

The digests are not stored in plain text (about 2 MB each). The gzipped copies and the SHA-256 of the
canonical forms are in the report directory. The canonical SHA-256 is `3e866c0d...` for HEAD and
`eb3c479f...` for after. They differ only by the adapter line above.

## Limits

- The digest covers one world (seed 305000, no autonomous actors) and three work ticks. It does not
  cover a multi-period run, the 100-resident village, or any other seed.
- A pack with no founding map has no tiles at all. The hamlet previously borrowed bigville's expanded
  map and sites (the 013b report recorded this). Now it has none. Its buildings get site (0, 0) and no
  cell. The hamlet's 013b and 014 tests pass unchanged. Its behaviour outside those tests is not
  checked.
- `from_town100` on a pack with no founding town builds the world (with no map) before it refuses.
- The self-test checks cross-references. It does not check that role counts are realistic, or that the
  mixture's parameters are right.
- The compatibility views (`_PARAM_SPEC`, `_draw_resolution_bins`, `_name_pool`) are derived from the
  default pack at import. A child pack's changes do not reach them, and only the default pack's values
  are used.
- Entity tables are shared between worlds on one pack (as in 013b). Nothing in the founding code
  mutates them.

## Deviations

1. Lumber growback in the legacy adapter `BigvilleTown100World` changes from 3.0 to 4.0. HEAD hard-coded
   3.0 for all three deposits, while `RESOURCE_DEPOSITS` and `from_town100` use 4.0 for lumber. Reading
   the table makes the adapter agree with the town. This is the only digest difference. If you want
   zero change, the alternative is to keep a literal 3.0 for lumber in the adapter, which breaks the rule
   that the code reads tables. Your call.
2. `from_town100(data_pack=...)` refuses a pack with no founding town after the world is constructed,
   not before. The error names the pack.
3. The hamlet has no map (see Limits).
4. Compatibility views were added so that other checkouts keep working. The Ocelot adapter at
   `/home/matt/ozmadev/ocelot/worlds/bigville_ocelot_adapter.py:776` imports `_PARAM_SPEC` and reads
   `["arousal"][0]` and three more keys. It has no other dependency on this module. Its test
   (`tests/test_bigville_ocelot_fresh_process.py`) failed with `ImportError: cannot import name
   '_PARAM_SPEC'` before I added the view, and passes now.
5. I added `name_pool(first=None, last=None)` and `_draw_resolution_bins(rng, mixture=None)` defaults.
   They keep the old call forms.

## Open questions and notes for 016b

- `FOUNDING_ROLES` counts are the cast 016b replaces with `E.seed_jobs(100)`. Roles with no JOBS entry
  today: quarrier, servant, reporter, landlord, banker, shopkeeper, fishmonger (among others). The
  self-test lists them as info. `fishmonger` has no entry in TRADES, JOBS, or CAST_ROLE_TRADES.
- `populate_town100` still holds the literacy-based `capability` values (0.9 and 0.55) and `skill=0.7`.
  016b should decide whether they come from JOBS or from `ACTOR_DEFAULTS`.
- The Ocelot adapter's `_param_spec_reference_means` should read `E.FOUNDING_PERSONALITY` directly. Once
  it does, the `_PARAM_SPEC` view can go. That change is in the Ocelot repo, not this one.
- `worlds/bigville_social_seed.py` keeps its own `_SELF_PARAM_SPEC` and priors (its own tables, not
  moved in this phase).
- `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json` are generated from the
  founding cast. `write_cast_seed` still writes from the default pack. I did not regenerate them, and the
  output would be identical only if the cast is unchanged.
- `FOUNDING_ANCHOR_ALIASES` maps `compost_yard`, `root_cellar`, `granary`, and `dairy` to `farm`, which is
  not a workplace. Those four have fixed sites, so the fallback never runs for them today. Decide
  whether `farm` should name a workplace.
- `FOUNDING_WORKPLACES` gives the workplace of each cast role. The `farm` role is a special case in the
  code, not a table entry. A 016b cast needs a clear rule for who works where.
- `author_founding_pack.py` cannot re-run. It is a record of the HEAD values.
