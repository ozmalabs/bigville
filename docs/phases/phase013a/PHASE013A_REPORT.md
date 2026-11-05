# Phase 013a: pack files, compiler, and export

## Summary

The entity tables that used to be literals in `domains/world_affordances.py`, `shared_frames.py`,
`population.py`, and `bigville_entities.py` now live in `packs/bigville/` as JSON. `domains/pack.py`
loads that pack, restores the types JSON cannot hold, and runs the compiler that adds the entries
the modules used to derive at import. The four modules bind their names from the pack. Every public
table in the combined view `E` equals its value before this phase, type for type and in key order.
The self-test output is byte-identical to the baseline. The full suite passes: 332 tests, the 323
from baseline plus 9 new.

Initial `git status --short` was empty (HEAD `fc4247d`). Function bodies in all four modules are
unchanged (checked by comparing the AST of each `def` and `class` with HEAD).

## Changes

- `domains/pack.py` (new): `load_pack(name_or_path)`, manifest and `extends` handling (child replaces
  a table, or updates a dict with `"merge": true`), type restoration from `_types`, and
  `compile_tables`. The compiler has six guarded steps:
  1. `<food>_scraps` items from `leaves_scraps` (old `world_affordances.py` 306-313).
  2. Scrap prices in SCARCITY, setdefault (old 1443-1445).
  3. Heated recipes: `preparation`, a `fuel` input, and `tools` moved to `method_tools` (old 687-700).
  4. `seed_return` defaults to 1.25 on every crop (old 967-968).
  5. `origin`, `immutable`, and `enforcement` defaults on local policies and laws, then
     `POLICIES` and `LAWS` as concatenations (old `shared_frames.py` 602-607). The supervisor's
     brief named two defaults. The code sets three, so `enforcement` is included.
  6. `_SKILL_CLUSTER` (old `shared_frames.py` 206).
- `packs/bigville/pack.json` (manifest, 120 tables) and 102 table files under `world/`, `frames/`,
  and `population/`. Each file has `_doc` (the comments that explained its table, with citations),
  `_types`, and `tables`. Scalars and the dict parameters `NITROGEN`, `TRANSFER`, `PRACTICE`, and
  `APTITUDE_PRACTICE` sit in one `constants.json` per group.
- Types restored from `_types`: tuples (for example footprints, `SERVING_EQUIPMENT`,
  `STARTING_CROPS`, `RECIPE_EXERTION`, `LIMITATION_PREVALENCE` `rate_by_age`), sets and frozensets
  (`SOUP_FOODS`, `DRINK_FOODS`, `HEATED_FOOD_RECIPES`, `SLAUGHTER_PRODUCTS`, `ANIMAL_SERVICES`,
  `_PERISHABLE_RAW`), and tuple-keyed dicts (`SKILL_AFFINITY`). `_types` is generated from the data,
  not written by hand. It covers 17 tables.
- `world_affordances.py`, `shared_frames.py`, `population.py`: literal tables and their comments
  removed; a `_PACK = _load_pack("bigville")` block binds the group's names. Module-private
  `_CEREAL`, `_PERISHABLE_RAW`, and `_SKILL_CLUSTER` still exist under the same names.
- `bigville_entities.py`: `ANIMAL_SERVICES` moved to the world pack. The name is still exported
  through `E`, and it is now also a public name of `world_affordances`. `_PSEUDO` (a self-test
  helper) stays in the module.
- `tools/export_pack.py` (new). Without a manifest it bootstraps the pack from the modules (this ran
  once). With a manifest it normalises: it compiles the base, strips the derived entries, verifies
  that the result compiles back to the same tables, and rewrites the files. Output keeps the
  authored key order. It is not sorted (see Limits).
- `tests/test_phase013a_packs.py` (new, 9 tests): snapshot equality, module objects are the pack
  objects, restored types, base files hold no derived entries, export rerun is byte-identical,
  exported files compile back to the same tables, compile is idempotent, a child pack that
  `extends` bigville (one merged table, one replaced list, and inheritance checked), and a
  manifest that names a missing table.
- `docs/phases/phase013a/`: `snapshot_tables.py` and `before_tables.json` (pre-change snapshot),
  `before_selftest.txt`, `after_selftest.txt`, `selftest.diff` (empty), and `migrate_modules.py`
  (the one-time rewrite of the modules; it refuses to run twice).
- Existing tests: none changed.

## Validation

| Command | Result |
|---|---|
| `git status --short` (start) | empty |
| `python3 docs/phases/phase013a/snapshot_tables.py` (before, on HEAD code) | wrote `before_tables.json`: E 120, world_affordances 62, shared_frames 37, population 29, private 4 |
| `python3 domains/bigville_entities.py > before_selftest.txt` | exit 0; ERRORS 0, WARNINGS 0, INFO 5 |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (baseline) | 323 passed |
| `python3 tools/export_pack.py` (bootstrap, before the module rewrite) | 120 tables into 102 files; compile of the base equals the legacy tables for every name (checked inside the tool) |
| `python3 docs/phases/phase013a/migrate_modules.py` | removed 291 / 127 / 123 / 13 comment blocks (world / shared / population / entities); bindings inserted; every removed comment line found in a pack `_doc` |
| Snapshot check after rewrite (`snapshot_tables.snapshot()` vs `before_tables.json`, as a string compare) | identical except `world_affordances.ANIMAL_SERVICES` (new name, same value); no value changed |
| `python3 tools/export_pack.py` run three times | runs 1 and 2 byte-identical (md5 of all 103 files, `pack.json` included) |
| `python3 domains/bigville_entities.py` (final) | exit 0; ERRORS 0, WARNINGS 0, INFO 5; `diff before_selftest.txt after_selftest.txt` empty |
| AST comparison of `def` and `class` nodes with HEAD, 4 modules | 0 changed (world 32, shared 16, population 23, entities 10) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider tests/test_phase013a_packs.py` | 9 passed |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (final) | 332 passed in 57.70s |

No asset regeneration was needed: `ITEMS` and `BUILDINGS` keep their values. The asset manifest
test passes.

## Limits

- Equality was checked on the tables, the self-test output, and the suite. No village run
  (`run_village`) was done, and no behaviour beyond that was checked.
- Key order is kept as authored, not sorted as the brief asked. `ITEMS`, `SCARCITY`, and other
  dicts are iterated in order, so sorting could change iteration order. The snapshot compares key
  order, and it matches.
- `_CEREAL` is stored as a private table, but the compiler does not use it. `CROPS` in the pack
  holds the expanded cereal values. Editing `_CEREAL` alone changes nothing.
- The four cereal crops shared one `byproducts` dict through `**_CEREAL`. In the pack each crop
  has its own copy with the same value. Mutating one crop's `byproducts` in code no longer changes
  the others.
- `PREFERENCE_RESEARCH.update({...})` is stored as merged base data, not compiled. The merged table
  is what the file holds.
- Banners were moved mechanically, then reviewed. Three banners that head code (BACKEND VALUE
  REFERENCE above `reference_value`, BODIES above the training functions, and CONSISTENCY CHECK
  above the self-test functions) were moved back into the modules. Judgement calls kept in the pack
  docs: the psychology-of-preference block (heads the `PREFERENCE_RESEARCH` entries), the PHYSIQUE
  block, the SOCIAL ACTIONS block (heads `FREE_ACTIONS`), and the PROVISIONING block (heads the
  `APTITUDE` tables).
- `export_pack.py` bootstrap mode reads comments from the module source. Do not run it again: with
  the rewritten modules it would write empty `_doc` strings. It runs only when `pack.json` is absent.
- Incident: the first bootstrap resolved the bare name `bigville` as the relative directory
  `bigville/`, the game package. It wrote 102 table files and `pack.json` there. I deleted those
  103 untracked paths by name (`bigville/pack.json`, `bigville/world/`, `bigville/frames/`,
  `bigville/population/`). `git status` shows no change under `bigville/`. The resolver now treats
  only absolute paths and paths with a separator as directories.

## Open questions

1. Key order: keep the authored order (current) or sort keys as the brief said? Sorting changes
   the iteration order of `ITEMS` and the other dicts.
2. `_CEREAL`: keep it as a stored template that the compiler expands, so that CROPS holds only the
   authored values? Or drop the private name?
3. `PREFERENCE_RESEARCH.update`: keep it as merged base data, or make it a compile step that
   appends to an authored base?
4. Should `export_pack.py` stay as the normaliser for `packs/bigville`? Or should pack files be
   edited directly and checked with `load_pack`?
