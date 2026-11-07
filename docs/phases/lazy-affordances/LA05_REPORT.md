# LA05 — LLM prompt, agent view, Ocelot and UI on-demand

Status: complete. Phase LA05 of the lazy-affordances plan.
Base commit: `e1a88295f3a8547192bf2a9d43e93c118fe25a75` (LA04, branch `lazy-affordances`).
No commit or stage was performed by this phase. The full suite was not run (LA04's note says a
suite may still be active); targeted tests only.

## What changed

### `domains/agent_view.build_lazy_agent_view(game, actor, mode="agent")`

A second builder that publishes **entities and capabilities** from `world.observe(actor)`. It never calls
`actor_affordances()` or `_actor_options()`. Sections and their source:

| Section | Built from |
|---|---|
| `self` | the existing persona/body/skills/carrying/knows/places/kin/notes/lessons helpers; `knows` also carries a bounded recipe list (job recipe first, then `observation.known_recipes`, at most 24) so a proposal can name a recipe in `params.recipe` |
| `now` | the existing `_now` helper |
| `around.people` | `observation.nearby_actors`, nearest 8: stable name, distance words, role and cheap looks; a stranger keeps the view's stranger wording |
| `around.things` | `observation.visible_objects` + `observation.containers_in_reach` (12 max) with stable ids and kind words, then 8 stable place handles |
| `around.seen` | cell features (buildings, land, sites, fixtures, shops, projects, infrastructure, animals, crops), named places from `observation.places`, and witnessed object moves (20 max) |
| `map` | the existing fogged map (`map_memory`) or the existing terrain patch |
| `can` | a bounded capability list (28 max) in the existing `handle`/`action`/`what` shape |
| `last` | the existing `_last`, including the `world.last_outcome` refusal reason in words |
| `reaction` | the existing contest reaction helper |

`can` rows are **capabilities, not the legal menu**. Their `handle` is always empty. The action is the view's
verb (`walk`, `eat`, `work`, `move something`, …); `what` is the bounded capability ("food you can reach",
"work at a recipe you know", "fetch goods from a container in reach", …). The entities those capabilities act
on are the stable ids in `around.things`, `self.carrying` and `self.knows`, so the model composes the proposal
itself.

Walk destinations are the one place where a stable handle is published: `around.things` carries named places
and adjacent ground as `cell:x,y` handles with the place's words. This is a stable cell, not an ephemeral
`target:N` key. `reply_schema.to_wire` (below) reads a move's cell handle as `params.destination`.

`mode="referee"` is supported in the lazy view but deliberately omits the menu's `affordances` block: it has
body, calendar, carry, skills and nearby numbers only. Callers that need the exhaustive menu ask
`build_agent_view(game, actor, mode="referee")` explicitly. The menu agent view itself is unchanged.

### `BigvilleGame._lazy_context`

When the backend has `wants_agent_view`, the lazy context now builds `build_lazy_agent_view` and attaches it.
A failure is caught and leaves `agent_view=None`, exactly as the menu path does; the LLM backend then counts
an `internal_error` rather than raising into the world. `affordances` stays `[]`.

The lazy context also copies the root observation aliases (`calendar`, `position`, `health`, `hunger`,
`energy`, `intoxication_band`, `inventory`, `held_items`, `worn`, `job`, `known_recipes`, `nearby_actors`,
`last_outcome`, `heard`) from `observations["entities"]`. The packet's usual-now line and the LLM call budget
already read `context.observations["calendar"]`, so this is the documented LA04 alias behaviour, and it keeps
generic readers on the same values menu mode publishes.

### Prompt and direct-param wording

- `packet_system(pack, lazy=False)` keeps the pack's rules and the menu text byte-for-byte by default.
- A lazy context gets an added "Proposing in this mode" block: public.can lists capabilities, its handle may be
  empty, direct details go in `major_action.params` (`kind`, `recipe`, `object_id`, `destination`, `recipient`,
  `container`, `source`, `animal`, `crop_node`, `land`, `project`, `patient`, `name`), a walk copies a place
  handle from `public.around.things`, and the world may refuse an ordinary proposal.
- No pack data was changed. The lazy wording lives in `packet_system`; menu mode receives the previous text.

### Direct params in `reply_schema.to_wire`

`to_wire` already passed params through with `affordances=None`. The lazy path passes an explicit `[]`
(the "no menu" marker), which now means:

- no row is bound; a thing id in `major_action.target` stays a direct param (`params.target`), never an invented
  menu row;
- view words are read back to the world's action name (`walk` → `move`, `hand over` → `transfer`);
- a move's stable `cell:x,y` target becomes `params.destination = (x, y)`, and a `destination` list is
  normalised to a tuple;
- all other params (`kind`, `recipe`, `object_id`, `recipient`, `container`, `source`, …) pass through to
  `_enact_plan` unchanged.

Menu mode keeps the old handle-binding path. `LLMBackend._ask` passes `[]` for a lazy context even after the
autopilot has filled `context.affordances` with its own candidate rows, so those rows can never bind a lazy
reply. `PromptBuilder._packet` uses `observations.entities` as the lazy marker for the same reason.

### Ocelot and UI boundary

- `game.agent_view()` remains the **menu** agent view. Server `/api/view` and the TUI still use it; the UI's
  action pickers and `EmbeddedClient.affordances()` still call `actor_affordances()` on demand.
- Ocelot's `replace_options(context.affordances)` path consumes the full menu. `_context` therefore keeps an
  Ocelot actor (or any backend marked `wants_affordance_menu`) on the menu path even in a lazy game. This is an
  explicit per-actor exception, not a silent fallback: the alternative is an empty option list and a broken
  adapter contract. Ocelot backends were not modified.
- `game.step` in lazy mode was instrumented in the tests: neither `actor_affordances` nor `_actor_options` is
  called during a step. The on-demand query (`GameService.state()`, `EmbeddedClient.affordances()`) still
  returns the menu.

## Commands and exact results

```bash
python3 -m pytest -q tests/test_lazy_llm.py tests/test_lazy_cheap.py tests/test_lazy_observation.py -p no:cacheprovider
# 28 passed in 12.40s

python3 -m pytest -q tests/test_phase054_llm_prompt.py tests/test_phase054_actionable.py tests/test_bigville_server.py tests/test_phase057_tui.py -p no:cacheprovider
# 106 passed in 131.27s (a first run had 118.80s; the host was not idle)

python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
# 75 passed in 50.51s

python3 -m pytest -q tests/test_phase052_agent_view.py tests/test_phase053_fog.py -p no:cacheprovider
# 47 passed in 90.22s

python3 domains/bigville_entities.py
# exit 0
```

`tests/test_lazy_llm.py` alone: **9 passed in 0.45s**. It covers:

- lazy context + packet + `game.step` with a fake provider and a spy on both menu builders: zero menu calls;
- `public.can` capabilities (empty handles), `around.things`/`people`, no `legal_affordances`;
- a direct `{"action": "eat", "params": {"kind": "bread"}}` reply accepted and enacted;
- a direct walk to `(99, 99)` refused by the world, with the refusal reason in the next packet's `public.last`;
- a place `cell:x,y` handle becoming `params.destination`;
- menu-mode system text and menu agent view unchanged;
- UI on-demand affordances still returned while a lazy step calls no menu;
- an Ocelot-marked actor staying on the menu path;
- autopilot candidate rows not turning the lazy packet back into a menu interface.

## Limitations and semantic caveats

- The lazy view's `around.seen` uses the existing whitelist, whose `seen` rows have only `who`/`did`. Cell
  features and places therefore read as `{who: "bakery", did: "is here"}` or
  `{who: "mill", did: "you know where it is"}`. It is the same information in the existing shape, not a new
  whitelisted section; the pack and `agent_view_check` are untouched.
- Walk is the only capability with a per-place handle. Other actions take direct params from `around.things`
  and `self` (stable object ids, names, kinds, recipes). A model that puts a thing id in `major_action.target`
  keeps it as `params.target`; for actions whose world branch needs a different param name (for example
  `move_object`'s `object_id`), the model must use the named param, as the lazy interface says.
- `self.knows` publishes a bounded recipe list (job recipe + up to 24 observation recipes), not every
  `known_recipes` entry. This is a prompt cap, not a claim about what the resident knows.
- Lazy `mode="referee"` has no `affordances` block. Use the menu `build_agent_view` for a referee view that
  includes the exhaustive menu.
- Ocelot actors remain menu-mode in a lazy game. A future Ocelot adapter that consumes the observation could
  set `wants_affordance_menu = False`; today `kind == "ocelot"` forces the menu.
- The server's `GameService` still constructs its game in menu mode; no server route was changed. A lazy game
  is opt-in through `create_game(..., affordance_mode="lazy")`.
- The second requested suite took **131.27s** on the final run (118.80s on an earlier run), over the 120s
  guidance; the host was not fully idle. The counts are exact, but wall-clock is same-host and not a
  performance claim.

## Handoff to LA06

LA06 can evaluate the lazy LLM path with the usual scenarios and seeds. The metrics to record are refusals by
reason (the next packet's `public.last` already carries the reason), actions applied, direct-param shapes the
model actually chose, and whether capability rows plus stable place/thing handles are enough for movement and
trade. The mode remains opt-in; `game.agent_view`, server, TUI and Ocelot continue to use the on-demand menu,
so LA06 can decide the default without changing those adapters first.
