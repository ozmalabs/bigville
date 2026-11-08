# Phase 044 rebase note: HEAD f49a2f8 + 044

Base: `f49a2f88029c379250d735ad03b0550bdbaf9742` (f49a2f8). The 044 hunks were first anchored on 9074cc3. The
earlier manifest is kept as `hunks_9074cc3.json` for history. The original report, `PHASE044_REPORT.md`, still
describes the 9074cc3 build and is not rewritten.

## Build

    python3 docs/phases/phase044/build_clean_tree.py --dest /tmp/p044            # base HEAD
    python3 docs/phases/phase044/build_clean_tree.py --dest /tmp/p044b --base <commit>

The builder exports the base with `git archive`, copies the 6 files in `files/`, and applies the 22 hunks in
`hunks.json`. Each anchor must occur exactly once in the text at its point. It refuses to overwrite a base path.

## Hunks that changed, and why

| Hunk | File | Change | Why |
|---|---|---|---|
| 1 | `worlds/bigville_world.py` | `class BigvilleWorld:` becomes `class BigvilleWorld(BirthsMixin, BodyMixin):` | Phase 069 made `BodyMixin` the base class. The births mixin goes first, as in the later live tree. |
| 12, 13 | `packs/{bigville,test_hamlet}/pack.json` | The `BIRTHS` entry now follows `TUI_PROSE`, the last entry at f49a2f8. The entry is one line, like the TUI entries. | The 9074cc3 anchor (`IMPAIRMENT_NEIGHBOURS`, multi-line) is no longer the last entry. |
| 20, 21 (new) | `packs/{bigville,test_hamlet}/world/interoception.json` | `"childbirth": {}` added to `HARM_LOCUS`. | Phase 070 requires a `HARM_LOCUS` row for every `HEALTH` cause. An empty row is whole-body harm, which the table documents for illness and age. |

The other 17 hunks apply to f49a2f8 unchanged. The text of `worlds/bigville_world.py`, `domains/world_affordances.py`,
`domains/bigville_entities.py`, `bigville/game.py`, `packs/*/world/{health,marks}.json` and the two test
expectation files is identical to the 9074cc3 anchors.

No new module changed, so `files/` is unchanged. Its copies match the shared checkout's `worlds/births.py`,
`domains/fertility_check.py`, `bigville/resident_births.py` and the two births tables and test file.

## Semantics checked against HEAD (Phase 069 to 071)

- `harm(actor, amount, cause, locus=None, *, fragility=True)`. The births calls use `fragility=False` by keyword, so
  they bind as before. The new locus draw is a stateless hash (`_body_harm_locus`), not the world RNG, so the
  births draws are unaffected.
- With `childbirth` and `illness` as whole-body causes, a birth harm writes no located ledger entry.
- The births read-offs `pregnant`, `term_fraction` and `nursed` do not collide with `body_state`'s keys. The
  mixin method names do not overlap with `BodyMixin` or with `BigvilleWorld`'s own methods.
- A newborn gets a body: `birth()` calls `add_actor`, which calls `_body_init`.

## Results (scratch trees from the builder, not the shared checkout)

| Check | HEAD f49a2f8 | HEAD + 044 |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0; INFO 105 | exit 0; ERRORS 0; WARNINGS 0; INFO 109 (4 `BIRTHS` lines) |
| `python3 -m domains.check` (bigville) | exit 0; 0 / 0 | exit 0; 0 / 0 |
| `python3 -m domains.check --pack test_hamlet` | exit 0; 0 / 0 | exit 0; 0 / 0 |
| `tools/export_pack.py --pack X --out DIR`, every file compared with the tree | not applicable | both packs: 159 files, all identical |
| Focused tests (`test_phase044_births`, 043, 057, 063, 065, 069, 070, 071, `test_simple_life`, `test_scenario_runner`) | 205 passed (without the 044 file) | 223 passed |
| 60-turn simple-backend run, `measure_behaviour.py --turns 60`, `PYTHONHASHSEED=0` | reference | identical to HEAD (all fields except `elapsed_seconds` and `label`) |

Focused command: `python3 -m pytest -q -p no:cacheprovider <files>` in each tree. HEAD ran the same list without the
044 file. The HEAD run is `focused_head.log`, and `focused_p044.log` is the stage run.

Logs for this stage are in `rebase/` (self-test, pack checks, focused runs, measurement). The export comparison
printed one line per pack and has no log file. Its result is the table row above.

No test was edited. No assertion was weakened. The 044 hunks include the two expectation edits from the original
phase (`births` in the physical-subsystem dict), which still apply on f49a2f8.

## Files and hunks at this stage

New (6): `worlds/births.py`, `domains/fertility_check.py`, `bigville/resident_births.py`,
`packs/bigville/world/births.json`, `packs/test_hamlet/world/births.json`, `tests/test_phase044_births.py`.

Shared (22 hunks in 14 files):
- `worlds/bigville_world.py`: 7 (hunks 0 to 6). Hunk 1 changed.
- `domains/world_affordances.py`: 1 (7).
- `domains/bigville_entities.py`: 2 (8, 9).
- `bigville/game.py`: 2 (10, 11).
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: 2 (12, 13). Changed.
- `packs/*/world/health.json`: 2 (14, 15).
- `packs/*/world/marks.json`: 2 (16, 17).
- `tests/test_simple_life.py`, `tests/test_scenario_runner.py`: 2 (18, 19).
- `packs/*/world/interoception.json`: 2 (20, 21). New.

## Open items

- The 069-071 `harm()` accepts a locus. The births code passes none. Childbirth could take a located row
  (ANATOMY has `upper_belly`) instead of `{}`. That is a design choice, so it is left whole-body here.
- The full suite was not run at this stage. The stage-045 full run covers the 044 files too (see the 045 note).
