# Phase 045 rebase note: HEAD f49a2f8 + 044 + 045

Base: `f49a2f88029c379250d735ad03b0550bdbaf9742` (f49a2f8). The 045 hunks were first anchored on 9074cc3 with 044.
The earlier manifest is kept as `hunks_9074cc3.json`. `PHASE045_REPORT.md` still describes the 9074cc3 build and
is not rewritten. The 044 changes are in `../phase044/REBASE_NOTE.md`.

## Build

    python3 docs/phases/phase045/build_clean_tree.py --dest /tmp/p044 --stage 044   # HEAD + 044 only
    python3 docs/phases/phase045/build_clean_tree.py --dest /tmp/p045 --stage 045   # HEAD + 044 + 045 (default)

`--base` defaults to HEAD (resolved and printed). The 044 steps reuse the 044 builder's functions. The 045 hunks
are in `hunks.json` (26). Each anchor must occur exactly once in the text at its point.

## Hunks that changed, and why

| Hunk | File | Change | Why |
|---|---|---|---|
| 0, 1 | `packs/{bigville,test_hamlet}/pack.json` | Anchor is the 044 `BIRTHS` entry (one line now), and the new entry is one line. | 044's entry is one line at f49a2f8. |
| 12 | `worlds/bigville_world.py` | `class BigvilleWorld(BirthsMixin, BodyMixin):` becomes `class BigvilleWorld(BirthsMixin, DependantsMixin, BodyMixin):` | The class base at f49a2f8 has `BodyMixin`. This order matches the live tree. |
| 16 | `worlds/bigville_world.py` | The infant refusal is appended to HEAD's refusal chain, after the `attending` refusal: `(sleep or attending or infant)`. | HEAD's gate is `(self._sleep_code(actor) or self._attending_refusal(actor, action))` (Phase 071). The old anchor (`sleep_code = self._sleep_code(actor) if gated else None`) no longer exists. Sleep and attending keep their order. With the switch off, `_dependant_refusal` returns None, so the gate is unchanged. |
| 24, 25 (new) | `packs/{bigville,test_hamlet}/world/interoception.json` | `"neglect": {}` added to `HARM_LOCUS`, after `childbirth`. | The Phase 070 self-test needs a row per HEALTH cause. Neglect is a whole-body cause, like starvation. |

The other 20 hunks are unchanged from 9074cc3. The 2 new neglect rows are in the table above.

## Semantics checked against HEAD (Phase 069 to 071)

- `harm()` takes `locus` as its fourth positional argument. The neglect call is `self.harm(name, harm, "neglect")`, with no
  locus and no fragility argument. The `neglect` row is empty, so no located ledger entry is written.
- The `body_state` read-off `dependant` (045) and the aftereffects read-off `dependent` (Phase 036) differ by one letter.
  Both keys appear in `body_state`. Renaming would change a published key, so it is left as is. The 045 report should
  be read with this in mind.
- Mixin method names do not overlap between `DependantsMixin`, `BirthsMixin` and `BodyMixin`, and `BigvilleWorld`
  shadows none of them.

## Results (scratch trees from the builder, not the shared checkout)

| Check | HEAD + 044 | HEAD + 044 + 045 |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0; INFO 109 | exit 0; ERRORS 0; WARNINGS 0; INFO 114 (5 `DEPENDANTS` lines) |
| `python3 -m domains.check` (bigville) | exit 0; 0 / 0 | exit 0; 0 / 0 |
| `python3 -m domains.check --pack test_hamlet` | exit 0; 0 / 0 | exit 0; 0 / 0 |
| `tools/export_pack.py --pack X --out DIR`, every file compared with the tree | 159 files, identical (both packs) | 160 files, identical (both packs) |
| Focused tests: 044 births (18), 045 dependants (17), 043, 057, 063, 065, 069, 070, 071, `test_simple_life`, `test_scenario_runner` | 223 passed | 240 passed (`focused_p045.log`) |
| 60-turn simple-backend run, `PYTHONHASHSEED=0 ... --turns 60` | identical to HEAD | identical to HEAD (all fields except `elapsed_seconds` and `label`) |
| **Full suite**, `python3 -m pytest -q -p no:cacheprovider` (`timeout 5400`) | not run at this stage | **2354 passed, 5 skipped, 0 failed**, 3861 s (`full_p045.log`) |

The HEAD focused baseline (the common list without the 044 and 045 files) passed 205 tests (`../phase044/rebase/focused_head.log`).
The full suite was not run on f49a2f8 alone in this session.
No test was edited. No assertion was removed or weakened. The only tests with a new expectation are the two physical-subsystem
dictionary expectations from 044, which still apply on f49a2f8.

Runner: `rebase/run_all.sh` runs the focused tests, the 60-turn runs and then the full suite, one stage at a time. Its
status file is `rebase/status.txt`. The full suite ran in the background with `nohup`, from 11:48 to 12:53, under load averages
of about 10 to 11 from other sessions. No flake showed.

## Files and hunks at this stage

New (7 from 045, plus 6 from 044):
- 045: `domains/dependants.py`, `worlds/dependants.py`, `bigville/resident_dependants.py`,
  `bigville/backends/dependants_policy.py`, `packs/bigville/world/dependants.json`,
  `packs/test_hamlet/world/dependants.json`, `tests/test_phase045_dependants.py`.
- 044: as in `../phase044/REBASE_NOTE.md`.

Shared hunks added by 045: 26 (the 045 manifest, hunks 0 to 25). The 22 from 044 are listed in its note.
- `packs/*/pack.json`: 2 (0, 1). Anchor changed.
- `packs/*/world/health.json`: 2 (2, 3).
- `packs/*/world/marks.json`: 2 (4, 5).
- `packs/*/world/refusal_reasons.json`: 2 (6, 7).
- `domains/world_affordances.py`: 1 (8).
- `domains/bigville_entities.py`: 2 (9, 10).
- `worlds/bigville_world.py`: 9 (11 to 19). Hunks 12 and 16 changed.
- `bigville/backends/cheap.py`: 2 (20, 21).
- `bigville/game.py`: 2 (22, 23).
- `packs/*/world/interoception.json`: 2 (24, 25). New.

## Open items

- `childbirth` and `neglect` are whole-body rows (`{}`). The 070 design allows located rows (`upper_belly` exists in ANATOMY for childbirth).
  Changing that is a design decision, so it is not made here.
- The shared checkout's `worlds/bigville_world.py` already reads `class BigvilleWorld(BirthsMixin, DependantsMixin, BodyMixin):`,
  the same as the rebuilt tree. The builders never read the shared checkout, so they do not depend on its uncommitted state.
- Not checked here: the 100-resident run with births or dependants on, and the `game_persistence.py` hook (Ocelot-owned).
  The 044 and 045 reports still describe these.
