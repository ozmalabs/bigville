# LA02 — Action-specific target resolution

Status: complete. Phase LA02 of the lazy-affordances plan.
Base commit: `9725e10eee6892e907b1b7e24a231a6d06ee5ee0` (branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

### `BigvilleWorld.resolve_targets(actor, action, params)`

Every external proposal now resolves its targets before enactment:

- **Direct proposals** (stable names, ids, tuples or cells) install an empty
  target map and return it. `_actor_targets[actor]` is replaced, not merged, so a
  stale `target:N` entry cannot outlive the turn that published it. Replacing
  the map with `{}` is deliberate and documented on the method.
- **Legacy proposals** whose `target`, `recipient`, `container`, `source`,
  `destination`, `patient`, `project`, `name`, `animal`, `land`, `crop_node`,
  `sow_kind`, `with` or `joint` value is a string beginning `target:` fall back
  to `_actor_options(actor)` and return that menu's map. This is the only path
  that builds the exhaustive menu.
- Unknown actions and malformed proposals also install `{}`; they do not raise
  here. `_enact_plan` refuses them with its existing refusal code.

The method returns the exact map it installed, and that map is also stored on
`self._actor_targets[actor]` for the tick graph's `alias()` resolution.

### `enact_plan()`

The old blanket `if needs_targets: self._actor_options(actor)` heuristic is
gone. `enact_plan()` always calls `resolve_targets()`, which is cheap for direct
proposals. `_attempt` wrapping, refusal publication and the action slot are
unchanged.

### `_enact_plan()` direct-field preference

`target_of()` now resolves a non-ephemeral target value to itself and accepts a
tuple/list as a direct cell. An unresolved `target:N` key returns `None` exactly
as before, so no malformed legacy key becomes a literal destination.

The four branches that previously ignored their direct field now prefer it:

- `give`: `_as_key(plan["recipient"]) or target_of()`
- `lock`/`unlock`: `_as_key(plan["container"]) or target_of()`
- `put`: `_as_key(plan["container"]) or target_of()`
- `fetch`: `_as_key(plan["source"]) or target_of()`

`transfer`, `move`, `care`, `build`, `maintain`, `tend_animals` and
`water`/`harvest`/`sow`/`fertilise` already preferred their direct fields or
their existing `crop_node` / `sow_kind`+`land` forms; their validation was left
intact. No refusal check was removed or weakened.

## Resolution rules

| Verb | Direct forms accepted without a menu |
|---|---|
| `give` | `recipient` actor name, or direct `target` |
| `transfer` | `recipient`, or direct `target` |
| `lock` / `unlock` | `container`, or direct `target` |
| `put` | `container`, or direct `target` |
| `fetch` | `source` container, or direct `target` (container name, or the `("store", kind)` tuple) |
| `move` | `destination` tuple/list/name, or direct `target` cell |
| `care` | `patient`, or direct `target` actor |
| `build` | `project`, or direct `target` project name/cell |
| `maintain` | `name`, or direct `target` infrastructure name/cell |
| `tend_animals` | `animal`, or direct `target` animal name/cell |
| `water` / `harvest` | `crop_node`, or direct `target` crop node/cell |
| `sow` | `sow_kind` + `land`, or direct `target` `(crop, land)` |
| `fertilise` | direct `target` land name/cell (or the legacy menu key) |
| `joint` | the `joint` dict itself |
| `attempt` | `verb` with direct `target`/`with` |
| `rest`, `sleep`, `eat`, `work`, `move_object`, `take`, `strike`, `throw`, `restrain`, `release`, `struggle` | no target map needed (unchanged) |

An unrecognised direct value is not rewritten into a valid one. The existing
`_enact_plan` branch or `major_action` refuses it.

## Menu-free outcome

These verbs now enact from stable values without calling `_actor_options`:
`move`, `give`, `transfer`, `put`, `fetch`, `lock`, `unlock`, `care`, `build`,
`maintain`, `tend_animals`, `water`, `harvest`, plus the no-target verbs above.
`sow` uses `sow_kind`+`land` or a direct target tuple, `fertilise` uses a
direct target land, and `joint`/`attempt` are menu-free by construction.

Only a legacy `target:N` proposal (UI action pickers, Ocelot's current adapter,
old backend output) builds the menu.

## Fallback compatibility

A legacy option still carries `target:N` alongside some direct fields (for
example a `transfer` option has both `recipient` and `target`). Because the
proposal still contains the ephemeral key, `resolve_targets` rebuilds the menu
and the old target map, so replaying a stored option keeps exactly the old
semantics. The Phase 020 tournament confirms every published option still
enacts on a fresh world.

Replacing `_actor_targets[actor]` with `{}` for direct proposals is safe for the
tick graph: its `alias()` returns an actor name or an already-direct value
unchanged, and only a legacy key consults the map.

## Tests

New file: `tests/test_lazy_target_resolution.py` (40 tests).

It covers:

- direct proposals for `move`, `transfer`, `put`, `fetch`, `lock`, `unlock`,
  `care`, `build`, `maintain`, `tend_animals`, `water`, `harvest` and `give`
  never call `_actor_options`;
- for the same twelve menu-backed cases, a direct plan and the legacy
  `target:N` option produce `True` and byte-identical `export_state()` on
  separate fresh worlds;
- a legacy `target:N` option still calls `_actor_options` once and resolves;
- `resolve_targets()` returns the installed map and stores the same object on
  `_actor_targets[actor]`;
- twelve malformed/unknown direct values return `False`, call no menu, do not
  raise, and leave a refusal reason from `REFUSAL_REASONS`;
- the menu-mode `TurnTrace` digest over two turns on the small TG01 scenario is
  still `a3aa31304905a0f8705a41135eaade7ce50ed5d63758e7ebf056a1532ff5788d`,
  recorded from the LA01 base commit by running the same scenario against a
  `git archive HEAD` copy of `9725e10`.

Commands and exact results:

```bash
python3 -m pytest -q tests/test_lazy_target_resolution.py tests/test_phase020_validation.py -p no:cacheprovider
# 240 passed in 152.60s (0:02:32)

python3 -m pytest -q tests/test_lazy_affordances.py tests/test_phase054_actionable.py tests/test_bigville_game_api.py -p no:cacheprovider
# 53 passed in 28.09s

python3 -m pytest -q tests/test_phase047_joint_actions.py tests/test_phase033_restraint.py tests/test_phase029_contest.py -p no:cacheprovider
# 78 passed in 8.78s

python3 -m pytest -q tests/test_phase035_nutrition.py tests/test_phase048_tool_fitness.py tests/test_bigville_world_migrated.py -p no:cacheprovider
# 138 passed in 22.82s (design integration gate, run additionally)

python3 -m pytest -q tests/test_tick_trace.py tests/test_tick_snapshot.py -p no:cacheprovider
# 14 passed in 110.46s (LA01 trace/snapshot oracle, run additionally)
```

The first command includes the unchanged Phase 020 validation tournament
(`test_every_published_option_of_a_seeded_village_actor_can_be_enacted_on_a_fresh_copy`),
so the exhaustive published-option boundary check is not weakened. The second
includes the LA01 menu trace test. The third covers joint actions, restraint and
contested takes, where `_enact_plan` target resolution is also exercised.

## Limitations

- Direct resolution installs `{}` rather than a per-action subset of candidates.
  This is the documented LA02 compromise: it removes the menu from the direct
  path without introducing a new candidate index. LA03 can add observation
  indices without changing this contract.
- `resolve_targets` is conservative: any ephemeral-looking value in a known
  target field triggers the full menu, even if the action would have used only a
  direct field. That preserves legacy semantics at the cost of a menu rebuild for
  mixed proposals.
- `_enact_plan` still contains verb-specific target selection. There is no
  unified typed target schema yet; unknown direct values fall through to the
  existing `major_action` refusals.
- The menu-mode trace oracle is a fixed digest for one tiny scenario, not a
  broad replay corpus; the Phase 020 tournament supplies the broader enactment
  check.

## Handoff to LA03

LA03 can rely on direct stable ids: `resolve_targets` no longer needs the menu
for direct proposals, and `_enact_plan` accepts actor names, container names,
project/infrastructure names, animal/crop names or node ids, and cells without
`target:N`. The observation model should publish those stable ids plus
capability tags. It should not call `actor_affordances()`; legacy menu
consumers keep the `target:N` fallback untouched.

LA03 does not need to change the LA02 resolution contract. If it introduces an
observation-specific index, it can be layered beside `_actor_targets`; the
enactment path only requires that a direct proposal's values remain resolvable
by the existing `_enact_plan` branches.
