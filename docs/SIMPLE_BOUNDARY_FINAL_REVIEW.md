# Simple village: final boundary review

Focused current-tree audit on 2026-11-05, after animal and reference
migrations, with the gossip boundary finding resolved.

## Unresolved findings

### 1. Gossip enactment used to update listener beliefs inside the world — resolved

`BigvilleWorld.enact_speech_proposal` now records the heard utterance in the
world's speech event log. It does not inspect the event's valence, read the
listener's trust, update `belief_trust`, or add to `heard_events`/`told_events`.
The legacy automatic gossip inference was removed. Recipient belief and memory
remain private cognition; a future recipient backend can consume a delivered
utterance and apply its own policy. Regression coverage confirms that two
listeners retain divergent prior beliefs after hearing the same report, and
that hearing does not create second-hand event memory or standing to retell.

### 2. Recipe priors are configured in cognition — resolved

`add_actor` and `add_recipe` no longer write recipe `knows` edges. The game
session builds private `recipe_knowledge` memories from scenario-authored
`recipe_priors`, or from the cheap backend's conventional trade catalog when a
scenario does not override it (`bigville/game.py`). `from_scenario` preserves
an explicitly empty list, so a character can begin without recipe knowledge.
Town100 uses the same backend catalog for its configured role/trade pairs.
Physical work admissibility remains independent of the private priors.

Regression coverage compares physically identical actors with distinct
explicit priors and checks that their public work affordances and world recipe
knowledge edges do not differ.

### 3. Herding resolution may bypass physical movement — low physical-mechanics issue

The animal decision lifecycle is now session-owned: `BigvilleWorld.tick()` no
longer decides or enacts animal actions; `BigvilleGame.animal_turn()` invokes
the animal backend and submits a selected action through
`apply_animal_action` (`bigville/game.py:83-109, 590-591`). One affordance
still publishes `target_escaped`, derived from enclosure integrity and target
position (`worlds/bigville_world.py:3813-3819`); these underlying facts should
be available directly if the backend is expected to interpret escape. Also,
when a herding animal and target are co-located, `_herd` moves the target
directly to the nearest enclosure cell (`worlds/bigville_world.py:3822-3839`)
rather than advancing it one adjacent step. This is a physical action
resolution issue, not an automatic cognition leak, but could distort animal
movement results.

Minimal repro: place the herding animal and target together several cells from
an intact pen, submit one legal `herd` action, and inspect target displacement.

## Recently resolved

- `tick()` contains only physical time/turn advancement; animal cognition now
  runs from the game session through an explicit backend action.
- Reference catalogs are templates only. Role/presence no longer assigns
  resident reference facts; authored scenario `reference_priors` become private
  character memories (`bigville/game.py:242-256`).
- Recipe knowledge is seeded as private game/backend memory from authored
  `recipe_priors` or the configured conventional trade catalog; the physical
  world no longer creates recipe knowledge edges.
- The reviewed `process_waste` and `school_lesson` APIs no longer gate on role.
- `_actor_options` carries neutral scores, does not hunger-filter eating/storage,
  and does not single out authored work coordinates. The old resident auto-tick
  and role-based village scheduler are definition-only.
- Council votes/meetings, deed entries, and case/dispute statements remain
  records, not global enactments. Document exposure is separated from held
  interpretation.

The remaining high item is specific to social belief formation. The rest of
the reviewed ordinary resident/world path did not reveal a live automatic
resident action selector or a role-based normative enforcement rule.
