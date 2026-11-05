# `_actor_options` affordance audit

Audit date: 2026-11-05. This audit distinguishes legal physical actions from
the cognition rules that rank or suppress them.

## Confirmed cognition leaks

`World._actor_options` is not a neutral list of physically possible actions.
The following inputs alter the offered choice set or its scores even when
physical state is held fixed:

* Hunger controls whether a resident can see `fetch`/`move` choices for
  household food (`hungry and not held_food`, around line 5375). This is a
  goal rule. A resident may fetch food for another purpose or stockpile it;
  the physically grounded conditions are stock at a reachable container and
  receiving capacity. The resident backend already sees hunger and filters
  `eat` when it is not hungry, so hunger need not be encoded by the world.
* Hunger and held food suppress travel to the town store to collect a
  tradesperson's output (around line 5441). Trade role matching also decides
  who is invited to collect which output. Those are task/identity preferences;
  physical feasibility is output stock, reachability, and capacity.
* `score` fields encode world-selected priorities (eat 100/-1, hungry fetch
  98, work 12/10, care 38/20, etc.). `_option_value` in the Ocelot path and
  simple backend both consume these values, so they directly steer cognition.
  Terrain/stamina cost is an appropriate mechanical read-off; the base
  desirability values are not physical conditions.
* Role/trade labels restrict who is offered farming, animal care, building,
  maintenance, and care tasks. Skill/input checks for recipe work are
  mechanical constraints, while the role gates and the decision to address a
  task are cognition/task ownership. In particular, care options are selected
  by doctor/midwife role and a world-computed `needs_care` predicate.
* `work_x/work_y` is a seeded occupation assignment that creates a movement
  target. The destination is physically real, but selecting that resident's
  work goal belongs to cognition.

The ordinary movement reachability gate, co-location, carried possession,
capacity, stock conservation, terrain, tool/input feasibility, cooldowns, and
alive state are physical constraints and should remain backend-enforced by the
world.

## Reproduction

The existing purchase invariance regression
`test_normal_actor_affordances_do_not_turn_seeded_sale_terms_into_purchase_intent`
shows that price and willingness no longer influence the normal options.
Equivalent direct probes for remaining leaks:

1. Give an actor empty inventory, place bread in a reachable household
   container, and compare `actor_affordances` with hunger 0 vs 1. Current code
   adds a `move` or `fetch` only in the hungry case.
2. Keep animal, cooldown, location, and path fixed; change actor role between
   `hand` and `farmer`. `test_husbandry_opportunity_is_role_invariant_and_farmer_preference_is_cognitive`
   verifies the world publishes the same action while simple cognition favors
   the farmer.
3. Keep a reachable workplace fixed and vary `work_x/work_y`. Current code
   adds a scored movement option to that cell.

## Migration boundary

The first migration publishes physically feasible household food fetch/move
choices independent of hunger, leaving hunger preference to the simple
backend. Role-gated affordances for husbandry, crop work, building,
maintenance, care, and trade-output collection have also been removed.
Reachability, animal/crop/project state, cooldowns, alive state, and material
availability remain physical gates. The simple backend now gives seeded role
preferences to these tasks after publication; role labels affect choice,
not legality. Role checks in the corresponding physical care, husbandry, and
maintenance operations were removed so published options can succeed.

Follow-up after the 2026-11-05 final review: ordinary actor affordances now use
neutral `score: 0.0` values. Hunger no longer changes the eat score or hides
storage travel. Care publication mirrors `care_for`'s physical precondition
(illness, injury, or hunger at its applicability threshold), and authored work
coordinates no longer add a destination. The simple backend applies hunger
and role/task preferences to published choices; role/task preference is a
score adjustment rather than a role-based removal of task affordances. Ocelot
sees the same neutral world scores and physical route metadata.

Residual boundaries: care remains a deliberately simple physical aid, not
clinical competence. Teaching and waste processing retain their legacy role
rules because they are not published as ordinary actor affordances. Recipe
work still uses the existing skill/input contract and timed-job availability.
Town stock collection and transfers remain behind explicit simple-policy
preferences. Crop dispatch carries stable crop/land identifiers through the
backend boundary, and sowing checks seed stock again at execution time to
handle multiple actors choosing against the same observation. Animal backend
scheduling belongs to `BigvilleGame`; `BigvilleWorld.tick()` advances animal
physics only. Animal affordances describe reachable feed, legal adjacent
destinations, and possible herding targets. Hunger and species preferences
rank those choices in `AnimalNPCBackend`, while `apply_animal_action` validates
and enacts the selected action against current physical state.
