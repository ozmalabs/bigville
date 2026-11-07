# LA03 — Observation model and indices

Status: complete. Phase LA03 of the lazy-affordances plan.
Base commit: `6e54bb43527ec81152a1744d0c303aa001854746` (branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

### `BigvilleWorld.observe(actor)`

A new cheap, deterministic, JSON-safe, read-only observation. It never calls
`actor_affordances()` or `_actor_options()`. The returned dictionary has these
keys:

| Key | Shape |
|---|---|
| `turn` | integer world turn |
| `calendar` | the existing `calendar()` record: clock, day, hour, week, year, season, weather |
| `position` | actor cell tuple (or `None`) |
| `terrain`, `terrain_movement` | existing terrain read-off and movement table |
| `health`, `hunger`, `energy`, `intoxication`, `intoxication_band` | body read-offs |
| `inventory` | `{kind: qty}` |
| `held_items` | existing list of discrete carried items |
| `worn` | garment kinds |
| `carrying` | `carry_state()`: weight, capacity, ratio, overload, speed, movement cost |
| `carried_weight`, `carry_ratio` | convenience copies of the two headline carry figures |
| `turn_state` | existing `actor_turn_state()` |
| `job` | `None`, or `{recipe, remaining, start_cell, paused}` |
| `skills` | `skill_levels()` |
| `known_recipes` | sorted recipe names the world believes the actor can attempt |
| `last_outcome` | existing `last_outcome()` record or `None` |
| `nearby_actors` | actors within radius 8: id/name/role/klass/group/position/distance/`shared_bucket_count`/`tie_strength`/`band_code` |
| `visible_objects` | accessible objects with stable id/name/kind/location and boolean tags `reachable`, `grabbable`, `container`, `open`, `locked`, `edible`, `tool` |
| `containers_in_reach` | reachable containers with id/name/kind/open/locked/reachable and an open-container `contents` summary (`id`/`kind`/`name`) |
| `cell` | position, terrain, buildings on the cell, land, gathering sites, square fixtures, sorted walkable exits, occupancy count |
| `heard` | recent utterances delivered to this actor, same shape as `heard_utterances(actor, limit=20)` |
| `aftereffects` | only when the world has aftereffect state (same conditional as the menu context) |

`known_recipes` uses the existing recipe registry and knowledge edges: every
recipe marked common (the data default) plus any recipe whose `ActionSpec` the
actor holds a `knows` edge to. It deliberately does not run ingredient, tool or
site validation for every recipe.

`visible_objects` preserves the insertion order of `physical_objects()`, so it
agrees list-for-list with `physical_object_observations()` (and the tests assert
that). Cells/positions remain tuples; `json.dumps(..., allow_nan=False)` accepts
the whole document.

### Derived indices

1. **Object location index.** `_physical_object_locations` is now a
   `_PhysicalObjectLocations` dict subclass that maintains
   `location -> {object ids}` in every mapping mutation. The index is also the
   read path of `_physical_object_index` (`location -> set(ids)`) and
   `_visible_physical_object_records()`. It is reset and rebuilt in
   `_install_physical_objects()`, and `move_physical_object()` routes through
   the indexed mapping.
   - Fallback: `_ensure_physical_object_locations()` rewraps and rebuilds the
     index whenever the mapping is not the indexed subclass (a restored
     checkpoint or a replaced mapping) or the object registry has grown/shrunk.
     Direct mutation of the indexed mapping is maintained automatically;
     replacement with a plain dict is rebuilt from that mapping, with the
     node's `location` attribute filling any missing entry.
2. **Utterance recipient index.** `_heard_utterance_index` maps each recipient
   to the utterance nodes delivered with `heard=1`. `speak()` appends to every
   recipient entry, including every recipient of a broadcast. `heard_utterances()`
   reads the index; if the index is missing or its log-size stamp no longer
   matches `_utterances`, it rebuilds by the old full scan. Output order and
   shape are unchanged.
3. **TG02 occupancy index** is kept for `nearby_actors`; `observe` uses
   `actors_near(position, 8)` exactly as the menu context does.

The public `physical_objects()`, `physical_object_observations()` and
`heard_utterances()` APIs keep working; only `heard_utterances()` reuses the
new index, with the old scan as the fallback.

### Lazy context

`BigvilleGame._context()` now branches cleanly on `affordance_mode`:

- **`menu`**: the existing code path is untouched. The LA02 two-turn TG01
  digest is still
  `a3aa31304905a0f8705a41135eaade7ce50ed5d63758e7ebf056a1532ff5788d`.
- **`lazy`**: delegates to `_lazy_context()`, which:
  - builds `observations["entities"] = world.observe(actor)`;
  - adds the game-owned `physical_events`;
  - adds the practice records using the same `practice_window` /
    `_published_practice` logic as menu mode;
  - adds `world_frames` (laws, policies, documents) and `known_references` from
    the character's memories, through the same document-frame logic;
  - adds `continuation` when active and `last_outcome` at top level;
  - sets `affordances = []`;
  - does not build `recipient_interfaces` (the menu-era O(N) block that
    described every backend to every other backend);
  - does not build an `agent_view` (the current view builder calls
    `actor_affordances()`; LA05 owns the lazy view).

The `skip_affordances` measurement seam from LA01 remains available in menu
mode, though the lazy path no longer needs it.

## Lazy-versus-menu measurement

Command (one pass per path and size, construction excluded, practice window
cleared before each pass; `tools/benchmark_affordances.py`'s TG07 scenario
builder and `build_game` were reused without modification):

```bash
python3 - <<'PY'
import time
from tools.benchmark_affordances import build_game, _actors

def run(size):
    menu_game = build_game(size)
    lazy_game = build_game(size)
    lazy_game.affordance_mode = "lazy"
    actors = _actors(menu_game)
    menu_game._published_practice.clear()
    start = time.perf_counter()
    for actor in actors:
        menu_game._context(actor)
    menu = time.perf_counter() - start
    lazy_game._published_practice.clear()
    start = time.perf_counter()
    for actor in actors:
        lazy_game._context(actor)
    lazy = time.perf_counter() - start
    return size, len(actors), menu, lazy

for size in (50, 100):
    print(run(size))
PY
```

| size | actors | menu total ms | menu ms/actor | lazy total ms | lazy ms/actor | ratio |
|---|---|---|---|---|---|---|
| 50 | 50 | 391.184 | 7.824 | 27.160 | 0.543 | 14.403x |
| 100 | 100 | 898.722 | 8.987 | 65.446 | 0.654 | 13.732x |

These are same-host relative numbers. The host was not fully idle (a full test
run had been active earlier in the worktree), so re-measure on an idle host
before quoting absolute milliseconds in LA06.

## Commands and exact results

```bash
python3 -m pytest -q tests/test_lazy_observation.py \
  tests/test_lazy_target_resolution.py tests/test_lazy_affordances.py \
  -p no:cacheprovider
# 54 passed in 34.65s

python3 -m pytest -q tests/test_tick_trace.py tests/test_phase028_hearing.py \
  tests/test_bigville_world_persistence.py -p no:cacheprovider
# 27 passed in 43.47s

python3 -m pytest -q tests/test_lazy_observation.py -p no:cacheprovider
# 7 passed in 0.45s
```

Additional check run beyond the two requested gates:

```bash
python3 -m pytest -q tests/test_simple_movement_access.py \
  tests/test_bigville_board_games.py tests/test_bigville_speech_migrated.py \
  tests/test_bigville_world_migrated.py -p no:cacheprovider
# 139 passed, 1 failed in 16.88s
```

The one failure is a stale negative-name assertion, not an LA03 behavioural
failure:

```text
tests/test_bigville_world_migrated.py::test_world_does_not_store_actor_demand_beliefs_or_choose_recipes
assert not any(hasattr(w, name) for name in
               ("observe", "belief", "will_make", "want_qty", "produce_run"))
```

That test predates LA03 and used the absence of a world `observe` attribute as
a proxy for "the world does not store actor demand beliefs". LA03 deliberately
adds `BigvilleWorld.observe(actor)` as required by this phase. The assertion
should be narrowed to the demand-belief names by the supervisor (removing
`"observe"` from the guard), or the phase plan should choose a different public
name. No engine or gameplay behaviour failed in that file.

## Limitations

- The cheap/simple backend is not adapted in LA03. A lazy turn may propose
  nothing useful yet; only observation shape, call counts and menu equivalence
  are gated here.
- `recipient_interfaces` is intentionally absent from lazy contexts. Any
  caller that needs the menu-era backend capability map must stay on menu mode
  until LA05.
- `agent_view` is not built in lazy mode because its current builder calls
  `actor_affordances()`. Ocelot/UI action pickers still use the menu; LA05 owns
  those surfaces.
- `known_recipes` is the world's broad knowledge view (common recipes plus
  explicit knowledge edges), not the character's private recipe memories. LA04
  may combine it with backend-owned knowledge.
- The location index keeps stale ids if the canonical mapping is edited to
  contain ids that are no longer in `_physical_objects`; observation filters
  those out via the registry, and the next rebuild drops them.
- The stale `test_bigville_world_migrated.py` assertion above is the only known
  conflicting test outside this phase's file scope.

## Handoff to LA04

LA04 can consume `context.observations["entities"]` (turn/calendar/position,
self state, nearby actors, visible objects with capability tags, containers in
reach, cell features, known recipes, heard speech) and the game-owned fields
alongside it (`physical_events`, `practice`, `world_frames`,
`known_references`, `last_outcome`, `continuation`). It should generate
candidates from that local observation, propose with the stable ids/names/cells
LA02 already accepts, and use `last_outcome`/refusals as ordinary feedback.
The menu path and `actor_affordances()` remain untouched as the equivalence
oracle and as the on-demand surface for Ocelot/UI.
