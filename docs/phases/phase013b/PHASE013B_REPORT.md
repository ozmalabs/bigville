# Phase 013b: the world reads a named pack

## Summary

`BigvilleWorld(data_pack=...)` and a scenario's `"data_pack"` select the data pack a world reads.
The world's entity reads (every `E.` in `worlds/bigville_world.py`, 164 lines) now go through
`self.E`, the entity view for that pack. `domains/data_view.py` builds the view: it executes the four
entity modules again, once per pack, with their pack binding pointed at that pack. The default pack
still uses the real modules. `python3 -m domains.check --pack NAME` runs the self-test on any pack.

`packs/test_hamlet/` is a standalone pack with every table name the modules bind. It boots a world,
an actor runs its recipes, and its self-test has 0 errors and 0 warnings. The default world is
unchanged: its self-test output is byte-identical to the 013a after-state, a digest of its behaviour
matches HEAD, and the full suite passes (340 tests: 331 existing, unchanged, and 9 new).

Initial `git status --short` was empty (HEAD `9ec7059`).

## Design

- Each pack gets a `types.ModuleType` per entity module (`world_affordances`, `shared_frames`,
  `population`, `bigville_entities`). Its namespace is the module's source, executed with
  `_PACK_NAME` seeded to the pack directory. The three modules that bind `_PACK` now read
  `_load_pack(globals().get("_PACK_NAME", "bigville"))`. The default has no seed, so it is unchanged.
- Inside a view, `from domains.<module> import ...` resolves to that view's own modules through a
  replaced `__import__` in the namespace's builtins. The four modules of one view therefore see each
  other, and nothing else.
- Functions are not rewritten. They read their module's globals, which are the view's tables.
  Guards were added only where a pack can be legitimately empty (see Changes).
- Views are cached per pack directory. `load_pack` already caches compiled packs per directory.
- `entities(pack)` returns the real `domains.bigville_entities` for the default pack. Every other
  pack gets a fresh view. `world_entities(world)` returns `world.E`, or the default when a world has
  none.

## Changes

New files:
- `domains/data_view.py`: `entities(pack)`, `world_entities(world)`, and the per-pack build.
- `domains/check.py`: `python3 -m domains.check [--pack NAME_OR_PATH]`. It prints the same four
  reports as `python3 domains/bigville_entities.py`. Exit status 1 on errors.
- `packs/test_hamlet/`: `pack.json` plus 101 table files (119 table names). Layout mirrors
  `packs/bigville`: each name is in the file bigville keeps it in. Content:
  - Authored: items `coin`, `water`, `grain`, `flour`, `bread`; recipes `mill_flour` (grain to flour)
    and `bake_bread` (flour and water to two bread), both by `baker`; building `bakehouse` (provides
    `baker`); trade `baker` (no tools); job `baker` (`spare: true`); skills `baking` and `milling`
    in cluster `food_crafts` under metaskill `craftsmanship`; trade skills; local law
    `hamlet_common_law`; scarcity for the five items; starting stock; the fertiliser input type
    (tag only, needed by the nitrogen constants).
  - Copied unchanged from bigville (generic physics and psychology): terrain, weather, seasons, waste
    cycle, the action vocabulary, body and preference distributions, the nitrogen constants, and the
    physics scalars. Their citations stay in `packs/bigville`.
  - Empty, with the right type: every other name.
  - Built by `docs/phases/phase013b/author_hamlet.py`, which refuses to run twice.
- `docs/phases/phase013b/`: this report; the authoring script; `boot_requirements.py` and its output;
  `default_digest.py` with its two outputs; the two self-test outputs.
- `tests/test_phase013b_data_pack.py` (9 tests, listed under Validation).

Changed files:
- `domains/world_affordances.py`, `domains/shared_frames.py`, `domains/population.py`: the `_PACK`
  line reads `_PACK_NAME` if the view seeds it. Default unchanged.
- `domains/bigville_entities.py`:
  - `check_consistency`: the BREAK-EVEN loop reads `BALANCE_SCENARIO.get("beds", {})`.
  - `_processes`: the `residents` process is added only if `WASTE_CYCLES` has `human_waste`.
- `domains/world_affordances.py` `_balance_flows`: an empty scenario (no `beds`) returns no flows,
  no work, and one note. The founding-town balance model is optional for a pack.
- `domains/population.py`: `scale_scenario` returns `{}` for an empty base. `job_requirements` reads
  the work day with `.get` (a divisor that is never used when there is no work).
- `worlds/bigville_world.py`:
  - All entity reads are `self.E.` (token-level rewrite; comments and docstrings unchanged). The
    module-level `E` import is removed.
  - `requested_data_pack(data_pack, scenario_data)`: the constructor's `data_pack` and the scenario's
    `"data_pack"` are alternatives, and giving both raises `ValueError`, as for
    `physical_subsystems`.
  - `__init__` gains `data_pack=None`, sets `self.data_pack` and `self.E`.
  - `_install_map` calls `build_town_100(seed, self.E)`.
- `worlds/bigville_town100_world.py`:
  - `build_town_100(seed, entities=None)` takes its deposit tiles from the given view (default: the
    default pack). The deposit loop walks the deposits the map placed, not a fixed list of three
    (same order for bigville).
  - `BigvilleTown100World.__init__` takes `data_pack`, sets `self.data_pack` and `self.E`, and refuses
    a pack without `fish`, `lumber`, or `stone` deposits.
- `bigville/reporting.py`: the three entity reads use `world_entities(self.world)`.
- `bigville/game.py`: the two entity reads use `world_entities(self.world)`.
- `bigville/game/assets/generate_assets.py`: `--pack NAME` draws that pack's ITEMS and BUILDINGS.
  `--out DIR` sets the output directory. A non-default pack needs `--out`, so the game's assets are
  not overwritten. Default output is byte-identical to the committed sheets.

Not changed: `bigville/backends/*`. None of them reads entity tables (grep for the table names and
for `domains`). Cheap and psi backends act on the affordances the world publishes.

Tests: no existing test was changed. The suite collects 331 tests at HEAD and 331 now.

## Minimum pack contract

- Every name a module binds must be present in the pack, or the loader fails. That is 119 stored names
  (plus 3 compiled: `POLICIES`, `LAWS`, `_SKILL_CLUSTER`). Empty values are allowed.
- Content needed for a boot plus one recipe (`boot_requirements.py`, output in
  `boot_requirements.txt`). Emptying each of these makes the boot fail:
  `TERRAIN_MOVEMENT`, `CARRYING`, `LIFE_STAGES`, `HEALTH_CONDITIONS`, `CLASS_DECAY`,
  `SKILL_CLOSENESS`, `TRANSFER`, `STATION_EDUCATION`.
- The sweep covered 119 names: 38 held content and were emptied (30 still boot, 8 fail as listed
  above); 17 are scalars, which cannot be emptied; 64 were already empty. Emptying `RECIPES` boots but
  refuses `mill_flour`, as it should.
- Tolerated, because a pack can legitimately lack them: `BALANCE_SCENARIO` (empty; the balance
  model and job-load per-100 terms are skipped), the residents' waste process (when `WASTE_CYCLES`
  has no `human_waste`; the world's latrine logic already returns early without it), and the
  infrastructure table (empty in the hamlet; no infrastructure is placed).
- Not tolerated, so the hamlet supplies them: `NITROGEN` (read unconditionally by the self-test),
  which needs the `fertiliser` input type.

## Validation

| Command | Result |
|---|---|
| `git status --short` (start) | empty |
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0, WARNINGS 0; output identical to `docs/phases/phase013a/after_selftest.txt` (`diff` empty) |
| `python3 -m domains.check` | exit 0; output identical to the script's (`diff` empty) |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0, WARNINGS 0; output in `selftest_hamlet.txt` |
| `PYTHONHASHSEED=0 python3 docs/phases/phase013b/default_digest.py`, run on `git archive HEAD` and on the working tree | both outputs identical (`digest_head_HEAD.json`, `digest_working_tree.json`). The digest covers a bare world boot, a baker's two calls and three periods, the 100-resident town from `from_town100()` with three periods, the town100 map hash, deposits, and residents |
| `python3 bigville/game/assets/generate_assets.py --out <tmp>` | exit 0; the 12 files (11 sheets and `manifest.json`) are byte-identical to the committed ones (`cmp`) |
| `python3 bigville/game/assets/generate_assets.py --pack test_hamlet --out <tmp>` | exit 0 (renders 5 items); without `--out` exits 2 |
| `python3 docs/phases/phase013b/boot_requirements.py` | 119 tables checked; 8 need content (listed above) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase013b_data_pack.py` | 9 passed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 340 passed in 61.23 s |

Smoke runs on the hamlet world (not in the test file): `tick(192)` ran in 0.3 s with no error;
`pass_period(3)` ran with no error; the baker recipe sequence gave bread 2.0, flour 0.0, water 1.0.

The 9 new tests: the hamlet boots and its baker runs `mill_flour` then `bake_bread`; `domains.check`
exits 0 on the hamlet with 0 errors and 0 warnings; `domains.check` on the default pack equals the
script's output; a fresh view of bigville (a child pack that extends it with no change) has the same
public tables as the default modules, with 0 consistency errors; a world on that fresh view and the
default world give the same stock and inventory after a sawyer's recipe; two worlds with different
packs in one process do not share tables or recipes, and the default modules are unchanged; a scenario
selects the pack; giving the pack twice raises `ValueError`; an unknown pack raises `PackError`; the
hamlet extends nothing and names every bigville table.

## Limits

- A view and the default modules share the `Pack` table objects of the same pack, because
  `load_pack` caches per directory. Two worlds on one pack share their tables. No code in the repo
  assigns into or mutates an entity table through `E` (a grep for assignments and `update`/`append`
  calls on `E.` found none), but nothing enforces that.
- The map generator (`build_town_100`) still uses bigville's site layout, building sites, and place
  labels for every pack. Only the deposit kinds come from the pack. The hamlet's map therefore has
  bigville's named sites and labels (for example "Bakery", "Mill").
- `BigvilleWorld.from_town100`, `from_townspeople_50`, `run_village`, and `populate_town100` are
  bigville-only. They take no `data_pack` argument, and `run_village` refuses a world without the
  100-resident cast. The 100-resident town's cast (`ROLE_SPEC`, names, anchors) is bigville's.
- `BigvilleTown100World` refuses packs without the fish, lumber, and stone deposits.
- The hamlet's copied constants are copies. Changing bigville's copy later does not change the hamlet.
- The hamlet was run only for a few hundred ticks and three periods, with one resident. It was not
  run with a population, with an autopilot, or through `run_village` (which needs the 100-resident
  cast). The self-test's JOBS report seeds it at 100, 30, and 8 residents, with no error.
- The scenario key `"data_pack"` is implemented and tested through an inline scenario. No file under
  `scenarios/` uses it.
- `tools/export_pack.py` is unchanged. It still imports the default modules.
- The 013a report says 332 tests passed. HEAD collects 331 (the history table in
  `docs/FEATURE_PHASES.md` says 331). I did not change the 013a report.

## Open questions

1. Should a pack state "no founding balance" with an explicit flag, instead of an empty
   `BALANCE_SCENARIO` standing for that? The guard works, but an empty table could also mean a
   forgotten table.
2. Should the map's site layout and place labels move into a pack table (in Phase 014 or 015)?
   Until then, a non-bigville world is drawn on bigville's sites.
3. Should a view deep-copy its pack's tables, so that two worlds on the same pack are isolated? That
   costs a copy per view. Nothing mutates tables today.
4. Should `from_town100` and `run_village` take `data_pack` for symmetry, or stay bigville-only until
   the cast is in a pack (Phase 003)?
