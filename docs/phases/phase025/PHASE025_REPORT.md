# Phase 025: fair turn order

## Summary

Each turn, `BigvilleGame.step()` now applies the actors' responses in a permutation that changes
from turn to turn. The permutation comes from the map seed and the turn number, through a
`random.Random` built inside a helper call. The helper holds no state and does not read or advance
`world._rng`. Decisions are still taken for every actor before the tick. The applied order is kept
in `game.last_order`. Self-test: 0 errors, 0 warnings. Tests: 884 passed, 1 skipped, 0 failed (with
the other session's untracked test files excluded; see Validation).

## Changes

Files:
- `bigville/game.py` (tracked, modified by this phase):
  - `import random` added to the imports.
  - `__init__`: `self.last_order: list[str] = []`.
  - New method `turn_order(actors, turn)`, placed directly before `step()`.
  - `step()`: the apply loop now iterates `order = self.turn_order(list(responses), turn)` and sets
    `self.last_order = order`. The loop body is unchanged.
- `tests/test_phase025_turn_order.py` (new): 7 tests.
- `docs/phases/phase025/PHASE025_REPORT.md` (this report) and `docs/phases/phase025/suite_run.log`.

Hunks in shared files. The other session's hunk in `_apply_response` (`record_action_outcome`,
about lines 664 to 676) is untouched. My hunks are at the import block, `__init__`, the new helper
(about lines 746 to 763) and the `step()` apply loop (about lines 792 to 799). None is within 4
lines of theirs.

Design:
- Seed: the world keeps the map seed as the `seed` attribute of its `Map` graph node
  (`worlds/bigville_world.py`, `_install_map`). `turn_order` reads that node with
  `getattr(world, "_map_node", None)`, and uses 0 when no map exists. The world also keeps the same
  seed in `_animal_life_seed` and `_burial_seed`. I used the map node because it is the stored map
  seed and is checkpointed with the graph.
- Generator: `random.Random(f"{seed}:{turn}")`, created per call. Actor names are sorted before the
  shuffle, so the result does not depend on the order the backends were registered.
- The turn used is `world._turn` after `tick()`, so every call in one step gets the same value.
- Checkpoints: nothing new is stored. `last_order` is a plain list on the game object. It is
  recomputed on the next step, so a restored game needs no saved copy.

## Data and sources

No pack data, rates or real-world figures are involved.

## Validation

Commands and results:
- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0).
- `python3 -m domains.check --pack test_hamlet`: exit 0.
- `python3 tools/generate_seeds.py --check`: exit 0, "generated seeds ... match pack 'bigville' (31 files)".
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase025_turn_order.py`: 7 passed in about 60 s.
  The contested-stock test takes about 50 s of that.
- Full suite, with the untracked files of the other session excluded (`--ignore` on
  `test_bigville_game_persistence.py`, `test_bigville_graph_persistence.py`,
  `test_bigville_ocelot_communication.py`, `test_bigville_ocelot_fresh_process.py`,
  `test_bigville_world_persistence.py`, `test_mixed_ocelot_checkpoint_parity.py`,
  `test_mixed_ocelot_village.py`): `884 passed, 1 skipped in 312.36s`, exit 0. Log in
  `docs/phases/phase025/suite_run.log`.

The new tests:
1. Same map seed and turn give the same order on replay (two worlds built from seed 305000).
2. The order is a permutation of the actors, and it changes between turns.
3. A different map seed gives a different order on some turns.
4. The order does not depend on the order the names are listed in.
5. Calling `turn_order` 49 times leaves `world._rng.getstate()` unchanged.
6. A `step()` records `last_order`, and it equals `turn_order` for the responded actors.
7. Two residents who each fetch the single unit of bread at the store every turn for 120 turns:
   exactly one succeeds each turn, and the first resident wins between 35% and 65% of turns.
   I did not run the test against the old insertion-order loop. By reading the loop, the first
   applied resident takes the unit each turn in that version.

Not run: the 100-resident village run and any run of the other session's ocelot scenarios.

## Limits

- Only the two contenders act in test 7. `step()` builds a context for every backend, and 100
  decisions per turn took about 1.3 s each step, so the test removes the other backends.
- Test 7 empties each contender's bag of bread at the start of the turn, because the volume limit
  otherwise refuses the second fetch (`no_capacity`) from turn 102 on. This is a fixture write to
  the inventory node, not a game action.
- The order is uniform over permutations. It does not weight residents by any physical priority.
  The brief asks for no more than this.
- Resolution order is per turn only. Two residents who both act on a shared stock still see
  decisions made before the tick, as the brief specifies.
- The change affects the 100-resident village. Any existing village result that depended on the
  insertion order will now differ. This was not measured, because the brief did not ask for a
  village run.

## Open questions

- Should the seed come from a dedicated public world attribute rather than the Map node? The
  current choice uses only data the world already stores.
- The brief's stated baseline (872 passed, 1 skipped) does not match the tree I ran against.
  Full-suite numbers here include the other session's modified tracked tests, so the difference
  from 872 is not isolated.

## Deviations

- HEAD is `ecd6f18` ("Phase 024: exhaustion slows residents..."), not `c8534f8-amended` as the
  request said. The Phase 024 work is present.
- The request said the baseline was 872 passed, 1 skipped. The full run here gives 884 passed,
  1 skipped, with 7 new tests and the other session's untracked test files excluded. I did not
  stash or check out a clean baseline, because the preamble forbids it, so the exact before/after
  count is not isolated.
- The seed is the Map node attribute, not `_burial_seed` or `_animal_life_seed`. The same value is
  stored in those attributes.
