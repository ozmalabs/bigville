# Simple backend baseline and cognitive boundary inventory

Captured 2026-11-05 in the shared working tree for package 1 of
[`SIMPLE_VILLAGE_TEST_PLAN.md`](SIMPLE_VILLAGE_TEST_PLAN.md). No implementation
files were changed for this inventory.

## Reproduction snapshot

| Item | Captured value |
|---|---|
| Repository | `/home/matt/ozma/bigville` |
| HEAD | `a7da178e1cedde48cfb3569a721db28484d5bf94` |
| Tree at capture | Dirty: `README.md`, `bigville/__init__.py`, `bigville/api.py`, `bigville/backends/{__init__,cheap,ocelot,psi_can}.py`, `bigville/game.py`, `bigville/held_board_games.py`, `docs/SCENARIOS.md`, `tests/test_bigville_{board_games,game_api,scenarios}.py`, `worlds/bigville_world.py` modified; `docs/SIMPLE_VILLAGE_TEST_PLAN.md`, `tests/test_simple_life.py` untracked. These were present before this document was added. Preserve as intentional work. |
| Python | `Python 3.14.8` |
| Test command | `python -m pytest -q` |
| Full suite | **218 passed in 14.15s** (dirty tree) |
| 100-resident smoke | **100 actors**, town seed `305000`, simple backend, autonomous game, 8 successful game steps, cadence 8; initialization 0.161s, total wall 1.958s; all 100 alive. `sanity_report()['errors']` and `negative_stocks` were empty. |

Reproduce the smoke from the repository root:

```bash
python - <<'PY'
from bigville import create_game
game = create_game(seed=305000, default_backend="simple", autonomous=True,
                   ticks_per_period=8)
for _ in range(8):
    game.step()
assert len(game.characters) == 100
print("turn", game.world._turn,
      "alive", sum(game.world.is_alive(n) for n in game.characters),
      "sanity", game.world.sanity_report())
PY
```

The full-suite timing and smoke wall time are one local observation, not a
performance guarantee. The smoke is an initialization/short-turn check and
does not exercise a complete production and consumption cycle. Its sanity
report included warnings about edible stock shelf life and meat feed, plus
many recipe capability gaps; these are reported diagnostics, not invariant
errors. Because the tree was dirty, the results describe the checked-out state
and cannot be attributed solely to `HEAD`.

## Suspect methods and boundary assessment

| Code / behavior | Physical evidence vs cognition/norm | Reproduction and likely affected tests |
|---|---|---|
| `worlds/bigville_world.py::_actor_options` (5242) | Mostly publishes affordances using alive state, possession, reachability, capacity, routes, stock, and co-location: physical constraints. It also filters sellers on `sell_willing`, makes hunger the trigger for purchase/fetch choices, subtracts `sell_price` from candidate scores, checks buyer coin, and uses a shop's price/stock as a choice condition. Willingness and valuation are agent-held; current world affordance generation embeds part of those judgments. Keep reach, capacity, possession, stock conservation, and physical shop location as world facts. | Call `actor_affordances(actor)` on an otherwise equivalent seller with `sell_willing` toggled, or vary `sell_price` / buyer coin while holding positions and inventory fixed; compare output. Tests: `tests/test_bigville_world_migrated.py` purchase tests (662, 686, 708), seeded town food/time tests (1254, 1268); game API purchase and context tests in `tests/test_bigville_game_api.py`. |
| `worlds/bigville_world.py::resident_plan` (5577), `_decide_actor`, `perform_plan` | `resident_plan` delegates selection to the Ocelot actor's graph and returns its decision. That is an alternate cognition path, not a physical affordance query. `perform_plan` also selects internally before enacting. Keep for compatibility while establishing the simple backend boundary; avoid using these as the simple backend decision path. | Invoke `resident_plan(actor)` and compare with `actor_affordances(actor)`; inspect choice and reason. Tests: `tests/test_bigville_world_migrated.py::test_canonical_school_journal_and_resident_plan_are_live_state`; `tests/test_bigville_scenarios.py::test_scenario_actor_backend_selection_and_turn_flow`. |
| `_person_purchase`, `purchase_utterance`, `give` (around 3020, 3152) | Utterance as an event is observable evidence. `_person_purchase` currently requires a purchase speech record, `sell_willing`, and payment in coin at the seller's stored price, then couples item and coin transfers into a completed transaction. Speech, price acceptance, willingness, and agreement are social/economic decisions; co-location/reach, physical item availability, capacity, and conservation are world constraints. The world presently interprets speech as a prerequisite token and performs the agreement's exchange. | Create utterance then vary seller willingness, payment, or seller inventory; exercise direct `give(..., payment_kind=...)`. Tests: `tests/test_bigville_world_migrated.py::test_purchase_is_preceded_by_a_free_market_utterance`, `::test_purchase_is_a_speech_then_give_not_a_buy_action`, `::test_purchase_is_between_people_and_needs_no_shop`; API structured speech test in `tests/test_bigville_game_api.py`. |
| `_claim_canonical_job_outputs` (1224) | On completion of canonical town jobs it moves output stock to maker inventory and sets willingness and price attributes. The transfer conserves a physical product, but automatically assigning it to the maker and setting commercial intent/price are scenario policy and economic interpretation. Separate from generic job output production. | Run a town100 canonical production job through completion and inspect stock, maker inventory, `sell_willing`, and `sell_price`. Tests to inspect: `tests/test_bigville_world_migrated.py` canonical village/job and market tests (1139 onward, 1310); town work paths also exercised by scenario and world suite. |
| Relationship state: `set_relationship`, `relationship`, actor context assembly (around 4800; game API context) | Relationship values are agent-held beliefs/feelings, even when stored as graph evidence. Storage and querying are neutral; treating them as objective truth or using them to compel behavior would cross the boundary. Nearby relationship signals currently expose a floor/default signal and configured relationship value to the actor context. | Set, query, and inspect a nearby actor context; verify recipient-specific visibility. Tests: `tests/test_bigville_game_api.py::test_nearby_residents_expose_floor_relationship_signal_when_no_bond_set` and adjacent relationship tests (225–256); `tests/test_bigville_disposition_seed.py` checks opt-in generated relationships reach context. |
| Law / records: `read_document`, `knows_law`, law metadata and enforcement fields (around 3512–3594) | A written law and its provenance, authorship, text, and whether an actor read it are physical/record evidence. Knowing a law can be agent-held state. `law_enforcement` metadata and methods need review wherever used to make conduct impossible or automatically punish it: lawfulness/enforcement belongs to agents' interpretations and actions, not the physical boundary. This inventory found explicit record and council machinery; it did not establish that all law enforcement is world-side. | Write/read a law as two different actors; check that an unread resident does not know it; inspect actions and event consequences after a norm violation. Tests: `tests/test_bigville_world_migrated.py::test_village_systems_and_layered_written_laws_are_data_driven`, `::test_giantville_core_laws_are_inherited_and_locally_enforced`, `::test_council_charter_defines_lawmaking_and_justice`, canonical law test at 1294. |
| Scenario seed loading: `from_town100` / `populate_town100` (1847, 1920) and `from_scenario` | Loading cast identity, initial positions, resources, documents, and authored relationship priors is initialization of evidence/state. Seed choices must not be mistaken for runtime resident knowledge or consent. Opt-in disposition seeding is distinct from bare town loading. | Load same town seed twice and compare population/state; compare bare town with opt-in `seed_generated_relationships`; load an authored compact scenario and inspect per-actor backend/context. Tests: `tests/test_bigville_game_api.py::test_populate_town100_seeds_scenario_character_data_per_resident`; `tests/test_bigville_scenarios.py` compact scenario tests; `tests/test_bigville_disposition_seed.py::test_seed_generated_relationships_not_auto_wired_into_from_town100` and context tests. |
| Generic action boundary: `major_action`, `_enact_plan`, movement / item / job APIs | Physical enforcement belongs here: one major action per turn, reach/access, capacity, possession, valid resources and actual consequences. These are not normative judgments. Review each proposed action for hidden social checks, but retain physical rejection and observable failure results. | Attempt movement to unreachable destination; item handover without possession/reach/capacity; job with missing physical input. Tests span `tests/test_bigville_world_migrated.py` movement/resource/job tests and `tests/test_simple_life.py` turn/action checks (the latter was untracked at capture). |

## Scope and limits

This is a source and regression-test inventory, not a comprehensive dynamic
audit. Suspects are classified for follow-up rather than redesigned here. In
particular, an affordance may safely encode physical admissibility while its
score and its social meaning should come from cognition. The next packages
should use action traces to distinguish those cases and preserve physical reach,
possession, capacity, and resource conservation.
