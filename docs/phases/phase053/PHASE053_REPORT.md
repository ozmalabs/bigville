# Phase 053: fog of the map, three levels of detail

## Summary

A fogged resident (its backend sets `fogged = True`: the LLM and human backends) now holds its own map at three
levels. Level 0 is absent from the map. Level 1 is a named place, roughly where it is in words, and the paths between
known places. Level 2 is the ground cell by cell (remembered terrain, and whether people were seen there) and the
exact place. The map is one `MemoryRecord` of kind `map_memory` in the character's own memories, so it checkpoints
with the character. The agent view's `map` section and `can` list are built from that map. Simple residents are not
fogged and keep their old view and affordances. A 60-turn all-simple town run matches `git archive HEAD` on every
recorded field.

The logic is in `domains/map_memory.py`. The tables are in `packs/*/world/fog.json`. The self-test is in
`domains/fog_check.py`. Tests are in `tests/test_phase053_fog.py` (21 tests).

Self-tests: both packs pass with 0 errors and 0 warnings. Live full suite: 8 failed, 1800 passed, 3 skipped. None of
the 8 is caused by this phase (see Validation for each).

## Changes

### New files

- `domains/map_memory.py`: the map. `ensure_map` (created at founding from Phase 019's place memories), `refresh`
  (cells in sight, places in landmark sight, `place_belief` memories), `learn_all` (end of turn), `route_plan` (the
  move check and `toward`), `map_section` (the agent view's `map`), `can_words` (how a move is worded), `true_patch`
  (the referee overlay).
- `domains/fog_check.py`: `check_fog(pack_name, errors, warnings, info)`. Checks the rule ranges (against
  `HEARING.sight_range`), the public landmarks and place words (against the founding tables), the headings, bands and
  templates, and that the agent view whitelist carries the map and label keys.
- `packs/bigville/world/fog.json`, `packs/test_hamlet/world/fog.json`: `FOG_RULES`, `FOG_PUBLIC_LANDMARKS`,
  `FOG_PLACE_WORDS`, `FOG_WORDS`. The hamlet's public landmark list is empty, because the hamlet has no founding sites.
  Both are exporter-canonical (checked with `tools/export_pack.py`, byte-identical).
- `tests/test_phase053_fog.py`: 21 tests (listed under Validation).
- `docs/phases/phase053/`: this report, self-test outputs, test logs, behaviour JSON for HEAD and for the clean tree,
  the sample views (`sample_views.txt`, made by `sample_views.py`), and the clean-tree build script
  (`build_clean_tree.py`).

### Files this phase owns outright (clean in the shared tree at session start)

- `domains/agent_view.py`: `_fogged_map` (the fogged `map` section), `_can` takes the game and wordings for fogged
  moves (`to`, `toward`, `spot`; a row to unknown ground is not listed), `build_agent_view` picks fogged or patch,
  and the referee block carries `true_map` for fogged residents. The non-fogged path is unchanged.
- `domains/agent_view_check.py`: the `label` section and the four new view words in the checks.
- `packs/bigville/world/agent_view.json`, `packs/test_hamlet/world/agent_view.json` (identical): the `map` whitelist
  gains `labels` and `paths`; a new `label` section (`glyph`, `word`); view words `map_full` ("the ground you have
  seen"), `map_vague`, `map_hidden`, `walk_toward` ("walk toward the {place}").
- `bigville/backends/llm.py`: `fogged = True` on `LLMBackend` (one class attribute, with a comment).
- `bigville/backends/human.py`: `fogged = True` on `HumanBackend`.
- `bigville/backends/prompts.py`: `select_knowledge` skips `map_memory` records (they would otherwise go into the
  prompt as episodic memories).
- `tests/test_phase052_agent_view.py`: one test changed (see Tests whose numbers changed).

### Shared-file hunks (each anchor is the unchanged line before the hunk)

1. `bigville/game.py`, `_finish_turn`. Anchor: the docstring line `"""The end of a turn: world turn bookkeeping, event
   expiry, periods and continuations."""`, followed by `self.world.resolve_actor_turn()`. Adds, after that line, a
   comment, `from domains.map_memory import learn_all` and `learn_all(self)`.
2. `bigville/game.py`, `_apply_response`. Anchor: `plan = {"action": proposal.action, **proposal.params}`, followed by
   `ok = bool(self.world.enact_plan(actor, plan))`. Adds, between them, a comment, `from domains.map_memory import
   route_plan` and `plan = route_plan(self, actor, plan)`.
3. `domains/bigville_entities.py`, `check_consistency`. Anchor: `    check_narration(_WORLD_PACK.path, errors, warnings,
   info)`. Adds two lines: the import and call of `check_fog`.
4. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`, manifest. Anchor: the `NARRATION` entry, the last
   table (`{"name": "NARRATION", "file": "world/narration.json"}`). Adds a comma after it and four entries:
   `FOG_RULES`, `FOG_PUBLIC_LANDMARKS`, `FOG_PLACE_WORDS`, `FOG_WORDS`, all in `world/fog.json`.
5. `tests/test_bigville_game_api.py`, `test_lesson_offer_is_a_backend_choice_and_world_does_not_infer_learning`.
   Anchor: `    assert accepted.dump_held_state("Ben")["memories"][-1]["content"] == "germination"`. The next assertion
   (`refused.dump_held_state("Ben")["memories"] == []`) now filters out `map_memory` records. See Tests below.

No hunk touches `worlds/bigville_world.py`, `bigville/character.py`, `game_persistence.py`, `world_persistence.py`,
`bigville/backends/ocelot.py`, `reply_schema.py`, `prompt_packet.json` or the TUI renderer.

### Behaviour

- **Initial map (Phase 019).** A place held as `exact` is level 2 around its cell (`exact_radius` 2). A place held
  as `roughly` is level 1. A `none` place is absent. `home` is always level 2. The public landmarks (`market`,
  `church`, `wellhouse`) are level 1 for everyone. Each routine route (home to each exact place) is level 2 along the
  shortest walkable path.
- **Learning (each turn, `learn_all`).** Every cell within `HEARING.sight_range` is level 2, stamped with the turn, the
  terrain, and a count of residents on it. A named place with a cell in sight is level 2. A structure (a building
  site, a workplace, a public landmark) within `landmark_sight` (16 cells) and beyond sight becomes level 1. A deposit
  (quarry, woodland, river) becomes known only in sight or by being told. A `place_belief` memory (told or read)
  raises the place it names to level 1, or to level 2 when the memory carries a position. Each memory is read once.
  Nothing lowers a level.
- **Ageing.** A level-2 place not seen for `stale_ticks` (288, three days) is labelled "as you remember it, <age>",
  with the age in words ("earlier today", "a season ago").
- **`can`.** A move to a level-2 place reads "walk to the <place>" (as before). A move to a level-1 place reads "walk
  toward the <place>". A move to ground the resident has seen, not a place, reads "a spot you know". A move to unknown
  ground is not listed. A shop row is worded by its trade when the resident holds that trade's place (as HEAD does).
  Several rows for one vague place collapse to one row.
- **`toward`.** The move action takes `params.toward`. A compass heading (`north`, `south-east`) aims
  `explore_steps` (12) cells ahead, or the nearest walkable cell along that heading. A place name is the nearest cell of
  that place, if the resident holds it at level 1 or 2. Anything else, or a bound destination on ground the resident
  does not know, becomes a plan with no destination, and the world refuses it as `malformed` (the existing refusal). A
  simple resident's plan is returned unchanged. The world then walks its own true shortest path, as before.
- **Map section.** Without a centre, the map is the resident's own: the sight window with level-2 terrain (and
  "unknown ground" where nothing is known), plus up to `max_labels` (5) labels, nearest first. A label is `{glyph,
  word}`. The word is the place, its rough distance and heading from the resident ("the tannery, roughly a short walk
  south-east, near your home"). Routes between known places are `paths`, at most two. With a centre and radius (a window
  on the map), only places inside the window are listed, and the level is `full` when a cell is known there, `vague`
  when only labels are, and `hidden` (no rows, no labels) otherwise. The renderer (unchanged) draws `full` rows,
  `vague` labels, and `hidden` as "You have not seen this ground yet."
- **Referee.** `referee.true_map` (the true sight window, in the same glyphs) for fogged residents.

### Sample view maps

From `docs/phases/phase053/sample_views.txt` (seed 305000). The farm labourer is Thaddeus Ramskin (farmer; the fields
are on his routine, and the tannery is rough for him). The incomer is Thaddeus Puddifoot (one year in the village).
His labourer routine puts the quarry on it, so the sample removes that one derived record to show a newcomer
without the quarry.

Farm labourer, own view (full):

```
     ..~~~~~~~~
     ..~~~~~~~~
     ..~~~~~~~~
     ..~~~~~~~~
     .........=
     .___......
     _===___...
     _=@====_..
     ._.___====
label A your home, right beside you, near the wharf
label D the tannery, roughly a short walk south-east, near your home
```

Farm labourer, a one-cell window on the wellhouse, which is rough for him (vague):

```
Landmarks you remember: A the well,
roughly a short walk east.
```

Farm labourer, a window on unknown ground (hidden):

```
You have not seen this ground yet.
```

Incomer without the quarry, a one-cell window on the quarry (hidden), and a window on the wellhouse (vague): the
hidden window renders as above, and the vague one reads "Landmarks you remember: A the well, roughly a short walk
north-east." The incomer's own view is the same as the farm labourer's in form (full cells, five labels).

## Validation

Commands are run from `/home/matt/ozmadev/bigville` on the live tree unless marked.

| Check | Command | Result |
|---|---|---|
| Entity self-test | `python3 domains/bigville_entities.py` | exit 0, ERRORS (0), WARNINGS (0). `selftest_bigville.txt`. Info: `FOG (bigville): 3 levels; 3 public landmarks, 9 place words; all fog checks pass`. |
| Hamlet check | `python3 -m domains.check --pack test_hamlet` | exit 0, ERRORS (0), WARNINGS (0). `selftest_test_hamlet.txt`. Info: `FOG (test_hamlet): 3 levels; 0 public landmarks, 9 place words; all fog checks pass`. |
| Phase 053 tests | `python3 -m pytest -q -p no:cacheprovider tests/test_phase053_fog.py` | 21 passed (on the clean tree, and again on the live tree after the last edits) |
| Full suite, live tree | `timeout 2700 python3 -m pytest -q -p no:cacheprovider` (28 min) | 8 failed, 1800 passed, 3 skipped. `full_suite_live.log`. Run before the last two small edits; see the recheck below. |
| Targeted recheck, live tree | Phase 052, 053, 054, 013a, the lesson test | 91 passed, 1 failed (the Phase 054 snapshot; see attribution). `live_touched_tests.log`. |
| Clean tree (HEAD + this phase's hunks) | `build_clean_tree.py`, then pytest on 054, 057, 052, 053, 013a | 138 passed, 1 skipped. `clean_tree_attribution.log`. |
| Behaviour, 60 turns, all simple | `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label head|mine --turns 60` (town100, seed 305000, `git archive HEAD` vs the clean tree) | Identical on every field except `elapsed_seconds` and `label`: action counts (eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15), utterances 285, 0 deaths, mean end hunger 0.4442, and the per-resident digests (100) and sample sequences. `behaviour_head.json`, `behaviour_mine.json`. |

### Attribution of the 8 live failures

- **3 Ocelot tests** (`test_bigville_ocelot_communication`, `test_mixed_ocelot_village`,
  `test_mixed_ocelot_checkpoint_parity`): `ModuleNotFoundError: worlds.bigville_ocelot_adapter` in the live tree. These
  files are untracked, so they are not in HEAD. In the clean copy they skip (no sibling `../ocelot` checkout). This
  phase does not touch the adapter or `ocelot.py`. I could not run them on HEAD.
- **4 Phase 057 HTTP tests** (`test_over_http_a_menu_row...`, `test_over_http_walking_to...`,
  `test_over_http_a_reaction...`, `test_the_server_refuses_a_bad_reply...`): these fail only on the live tree. The
  other session's uncommitted `bigville/server.py` removes `_bind_reply` and the reaction handling that these tests
  use (`git diff -- bigville/server.py`). On HEAD and on the clean tree all 5 `over_http` and refusal tests pass
  (`head_attribution_http.log`, `clean_tree_attribution.log`). The live recheck is `live_recheck_failures.log`.
- **1 Phase 054 snapshot** (`test_the_packet_matches_the_snapshot_for_a_fixed_view`): it failed in the full run and in
  the recheck, and passed in a separate run a few minutes earlier. The packet's `system` size changed (4930 to 5673).
  That text is built from `MAJOR_ACTIONS`, and the other session has `packs/bigville/world/major_actions.json` modified.
  It passes on the clean tree.

## Tests whose numbers changed

1. `tests/test_phase052_agent_view.py::test_moves_are_offered_only_to_places_the_resident_knows`. Before: the offered
   move handles equal the handles whose destination is an exact known place, and every `what` starts with "walk to
   the ". Now a fogged resident also gets its vague places as "walk toward the ..." rows, and the test checks that the
   exact rows are the exact handles, not the "toward" ones. It checks that each "toward" row's destination is known
   ground. The reason: the player is fogged, and the brief asks that a level-1 place be offered as "toward". The
   bakery shop (a trade row) is rough for the player in this seed, so its row is now "toward", as expected.
2. `tests/test_bigville_game_api.py::test_lesson_offer_is_a_backend_choice...`. The assertion
   `refused.dump_held_state("Ben")["memories"] == []` now ignores `map_memory` records. Ben is a `HumanBackend`, so it is
   fogged and holds its map record. No lesson is learned, which is what the test checks.

No assertion was weakened. No existing test number was changed in any other file. Tests added: 21 in
`tests/test_phase053_fog.py`.

## Limits

- **Sight occluders are not applied.** `HEARING.sight_occluders` (walls, trees) do not block the level-2 radius. Every
  cell within `sight_range` is seen.
- **Occupants are a count** ("people" per cell), not names, and only the count is stored.
- **Stale marking applies to places, not to cells.** A remembered cell in the rows has no age word. Only the labels of
  level-2 places carry "as you remember it".
- **Paths** are only the founding routine routes. Walking does not record new routes.
- **Told-with-position** places take the cell's terrain from the world at the moment of telling, not from what the
  resident saw.
- **Labels are capped at five** (`max_labels`). The packet's `map` cap is 900 characters (`PROMPT_PACKET.caps.map`), and
  a 15 by 15 map with twelve labels was 1,490 characters. Five labels make the default map 892 characters for the
  player. The packet measures the map but does not trim it, so the cap is advisory. Places beyond the five are still
  in `self.places` and in `can`.
- **`toward` is resolved in the game, not the binder.** Resolving a compass heading or a named place needs the world's
  cells, which `reply_schema.bind_row` does not have. The hook is the one in `game._apply_response`. The world was
  not touched.
- **The map record is created on first use.** A fogged resident gets its record at its first context or turn, so the
  held-state dump now lists it. The record is not a memory the prompt sees.
- **The map record is one record per resident**, not one per area. The brief allowed either ("one per area plus one grid
  record" is an example). Cells live in a dict in that one record.
- **Simple residents are untouched.** `game.step` for all-simple towns does no map work (`learn_all` loops over backends
  and finds no `fogged`). The 60-turn comparison above shows identical behaviour.
- **Not run.** No real LLM call (no provider, no network). The packet size was measured on the map section alone, not on
  a full packet. The 100-resident village run was not run (not asked).
- **Ocelot residents are not fogged.** `OcelotBackend` has no `fogged` flag, and `ocelot.py` was not edited.
- **Constants are APPROX.** `exact_radius` 2, `landmark_sight` 16, `stale_ticks` 288, `explore_steps` 12,
  `near_landmark_cells` 15, `max_labels` 5, and the distance and age bands are authored choices (see the `_doc` in
  `fog.json`). No figure has a source.

## Open questions

1. Should `OcelotBackend` set `fogged = True`? It is in another session's file, so I left it out. Without the flag, its
   residents see the patch and the full affordance list as before.
2. The seed has one resident who arrived one year ago, a labourer whose routine is the quarry. Phase 019 makes the quarry
   exact for them, so the brief's "newcomer does not know the quarry" case is tested by removing that record. Is that the
   right test case, or should the derivation give such an incomer no routine knowledge?
3. The packet `map` cap (900) allows five labels. Should the cap rise, or should labels be shorter?
4. The level-1 landmark rule covers structures and public landmarks, not deposits (a quarry is known by sight or by
   telling). Is that the intended reading of "a landmark visible from beyond that range"?
5. The TUI renderer shows labels only at the `vague` level. At `full` it shows rows only. Should `full` show the labels
   too? That would change the renderer, which this phase did not need to touch.
6. Should a remembered cell carry an age word in the rows, as the brief's "an old observation is marked stale" may
   intend?
