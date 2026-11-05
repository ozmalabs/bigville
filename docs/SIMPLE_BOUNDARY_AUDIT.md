# Simple village: legacy world-side boundary audit

Captured 2026-11-05 from the shared working tree. This is a source audit and
migration inventory, not a claim that the world/backend boundary is complete.
No tests were run for this audit, and no implementation files were changed.

## Current status

The existing baseline inventory is in [`SIMPLE_BASELINE.md`](SIMPLE_BASELINE.md),
and the staged target and package gates are in
[`SIMPLE_VILLAGE_TEST_PLAN.md`](SIMPLE_VILLAGE_TEST_PLAN.md). Since that baseline,
the dirty working tree adds a cognition-owned `transfer` action and situated
physical-object observations with short-lived witness events. The current
`BigvilleGame._context` publishes `physical_objects` and `physical_events`
(`bigville/game.py:279-304`), and `_record_physical_changes` reports visible
movement without assigning theft, permission, or ownership (`bigville/game.py:320-357`).
`tests/test_simple_norms_enforcement.py` now tests those observations, failed
moves, and late-arriving observers. Thus the earlier statement in
[`SIMPLE_VILLAGE_PACKAGE_13_FINDINGS.md`](SIMPLE_VILLAGE_PACKAGE_13_FINDINGS.md)
that the actor context lacks these inputs is stale.

The remaining norms-package blocker is contested taking: `major_action("take")`
currently returns `False` (`worlds/bigville_world.py:6392-6396`). There is no
backend-facing action that can take another resident's held inventory under
physical reach/capacity checks, so the same-item property-policy contrast and
physical enforcement consequence remain untested. The shared-larder fetch
control demonstrates equal access to a common container, not contested property.

## Migration inventory

### 1. Purchase and agreement — high priority; partially migrated

The neutral physical `transfer` path checks co-location, source possession, and
recipient capacity, then moves the held good (`worlds/bigville_world.py:3300-3339`,
`6381-6391`). `_actor_options` now publishes capacity-safe transfer options
without consulting price or seller willingness (`worlds/bigville_world.py:5533-5555`).
This is the correct physical seam.

Legacy purchase remains a world-interpreted agreement. `_person_purchase` requires
a matching purchase utterance, `sell_willing`, buyer coin, seller inventory, and
co-location, then couples item and coin movement into a transaction
(`worlds/bigville_world.py:3215-3239`). `_shop_give`, `give(...,
payment_kind="coin")`, `buy`, and the legacy purchase branch of `_enact_plan`
route into that path (`3200-3213`, `3252-3278`, `3341-3376`, `5838-5851`).
Speech, willingness, and price acceptance are agent-held decisions; only reach,
physical possession, capacity, and conservation belong in transfer resolution.

Exact tests to preserve or extend:

- `tests/test_package12_exchange_consent.py::test_backend_acceptance_hands_over_goods_without_price_or_world_agreement`
- `tests/test_package12_exchange_consent.py::test_offer_is_observed_and_acceptance_or_refusal_is_a_backend_choice`
- `tests/test_package12_exchange_consent.py::test_legacy_paid_give_is_only_a_physical_transfer`
- `tests/test_bigville_world_migrated.py::test_legacy_buy_does_not_force_speech_or_transfer_goods`
- `tests/test_bigville_world_migrated.py::test_give_moves_goods_without_purchase_speech_or_automatic_payment`
- `tests/test_bigville_world_migrated.py::test_purchase_is_between_people_and_needs_no_shop`
- `tests/test_bigville_world_migrated.py::test_normal_actor_affordances_do_not_turn_seeded_sale_terms_into_purchase_intent`

Implemented follow-up: the live `give` and `transfer` actions now perform only
the explicitly directed physical handover, checking co-location, source
possession, recipient capacity, and amount. Legacy payment arguments are
accepted but inert; coin movement must be a separate explicit transfer.
`_person_purchase`/`_shop_give` and the `buy` auto-speech/auto-transfer path are
removed (`buy` now returns false without side effects). `_enact_plan` no longer
creates buyer speech or an automatic payment when given a `give` plan. Market
counterparty lookup reports presence and physical possession only, without
filtering on `sell_willing`. Tests now cover explicit transfer with and without
legacy payment kwargs, including extreme price and both willingness values,
and verify that `buy` creates no utterance, transaction, or inventory change.

Remaining boundary: `purchase_utterance` remains an explicit compatibility
helper for callers that deliberately request a purchase proposal; cognition
must choose speech through its normal response path in live play. Reverse sale
and labor settlement have since been retired: `sell_to_shop`, `sell_labor`, and
`pay_wage` return false without changing goods, coin, wage-due state, or
transaction records. The hungry-actor affordance no longer offers fixed-wage
labor. Agent-selected exchanges can still use separate explicit physical
transfers; no shop acceptance, price, wage, or debt discharge is inferred.

### 2. Civic law, legal records, and case outcomes — high priority

Law documents and provenance can be physical evidence; a resident's knowledge
and interpretation must remain held by that resident. Current lawmaking code
turns role tags and vote counts into a global active-law result: `vote_on_law`
restricts voters by role (`worlds/bigville_world.py:3667-3675`), and
`hold_council` computes majority/quorum, enacts or rejects a proposal, updates
the shared law table, and seeds written documents (`3677-3701`). These are
institutional rules implemented as world-side procedure. Case and dispute
resolvers likewise restrict who may adjudicate by role and record an authoritative
resolution (`2791-2802`, `3713-3727`). In the inspected Python paths, verdicts
and remedies are stored as records; they do not themselves impose a physical
sanction or change land/inventory state.

The sharper legal boundary breach was deed registration. `register_deed` now
appends a deed to the register as a physical evidence record without checking
the writer's role, the prior holder, or the deed's consistency, and without
changing the parcel's title record. A title record reports what was written; it
is not automatically true legal title and does not gate physical actions.
Creating or inspecting a record does not seed a resident's interpretation.
Interpretations belong in private character memories/backend-held state; the
world only returns the observed register entry. Deed reading is likewise a
separate observation. Likewise,
`bigville/game.py:300-304` currently places every active law and policy spec into
every actor's `world_frames`, regardless of whether the actor read a document or
could observe one. This bypasses the resident-specific `read_document` and
`knows_law` state (`worlds/bigville_world.py:3783-3810`) and risks leaking
normative content into cognition.

Exact tests to preserve or extend:

- `tests/test_bigville_world_migrated.py::test_village_systems_and_layered_written_laws_are_data_driven`
- `tests/test_bigville_world_migrated.py::test_giantville_core_laws_are_inherited_and_locally_enforced`
- `tests/test_bigville_world_migrated.py::test_council_charter_defines_lawmaking_and_justice`
- `tests/test_bigville_world_migrated.py::test_records_office_registers_land_titles_and_disputes`
- `tests/test_bigville_world_migrated.py::test_council_votes_are_records_and_do_not_make_world_active_law`
- `tests/test_simple_norms_enforcement.py::test_conflicting_held_legal_policies_do_not_gate_proposal_records`

Bounded next step: stop broadcasting law/policy semantics through general actor
context; expose only observable records/text through a defined physical/document
observation path and keep comprehension in resident-held state. Add a paired
scenario where backend-held policies differ but physical transfer/access remains
the same, and verify an unread actor's context does not reveal law text or
semantic metadata. Keep registry/title updates as records unless an agent
chooses to honor them through an action.

Implemented follow-up: `BigvilleGame._context` now includes law and policy
specifications only when that resident already holds the corresponding
knowledge (`knows_law` / `knows_policy`). Its document list contains only
written records that resident has read, with the record's observable identity
and catalog metadata. The global law/policy registries are no longer copied into
every resident's cognition context. `tests/test_bigville_game_api.py` covers the
unread/read contrast and verifies another resident remains unaware.

Bounded physical-policy follow-up: `tests/test_simple_norms_enforcement.py`
also compares a backend-held "forbidden" interpretation with a "permitted"
interpretation while the same move option and world state are available. The
scripted actor can perform that move under either belief. When the move is not
observed, the witness receives no movement event and produces no response.
This demonstrates that the backend can choose a physical action regardless of
its held legal interpretation and that the world does not infer a sanction
from an unseen change. It does not model legal compliance or adjudication.

The civic APIs remain unresolved world-side institutional behavior, even though
they are not currently exposed as normal `BigvilleGame` action affordances:

- `vote_on_law(voter, proposal, support)` checks the global role tag and writes
  a vote edge; `hold_council(chair, proposal)` counts votes, changes proposal
  status, mutates the global active `_law_specs`, and seeds documents. Required
  work: move vote choice and legal interpretation to resident-held state;
  represent the council and promulgation as observable records/events; do not
  make a world-computed majority update the cognition registry. Keep the
  current canonical-council regression test until a replacement contract is
  implemented.
- `register_deed` now records submissions without validating claimed parties or
  mutating `_titles`. `test_records_office_registers_land_titles_and_disputes`
  checks that competing deeds are both recorded, title evidence is unchanged,
  and observation alone does not assign belief. `test_title_interpretations_live_in_private_character_memory_not_world_records`
  checks that opposite private character memories coexist while two equal deed
  records can be written and the world title stays unchanged. Physical
  transfer/access remains separate from these records.
- `resolve_land_dispute` and `resolve_case` formerly restricted speakers by
  role and wrote a globally authoritative outcome/remedy. They now append
  attributed statement records for any resident. The original dispute/case
  remains open with its original evidence, and no title, land, inventory, or
  access state changes. A recorded verdict, winner, or proposed remedy is
  evidence of what its speaker said; each resident must interpret it, and any
  physical response must be a separately chosen action. Focused tests preserve
  competing statements by ordinary residents and confirm that underlying case
  and title records remain unchanged.

Implemented follow-up (vote and meeting slice): `vote_on_law` now records a
resident's expressed vote without checking the resident's role or proposal
status. `hold_council` records a meeting and the observed vote tally; it no
longer computes quorum, changes proposal status, mutates `_law_specs`, or
publishes written law. A tally is evidence residents may interpret, not a
world-issued enactment. `test_council_votes_are_records_and_do_not_make_world_active_law`
also verifies that a non-official can record a vote and a positive tally does
not create active law. Proposal setup no longer rejects a name because it
belongs to an inherited law. `propose_local_law` records the resident's
expressed proposal and leaves the inherited registry untouched; residents
interpret whether such a proposal is admissible. A focused paired test gives
residents conflicting held legal interpretations and checks that both can
record proposals against the same inherited law.

Remaining civic migrations: vote replacement does not yet provide
resident-held deliberation, promulgation, or knowledge updates. Dispute and
case filing remains a public evidence-recording API, while all later
`resolve_*` calls are attributed statements. Resident beliefs, acceptance of a
remedy, deliberation, and any physical response are not modeled by these world
APIs. The legacy method names `resolve_land_dispute` and `resolve_case` remain
for caller compatibility, but they no longer imply a world decision.

These methods are direct world APIs and may still be used by setup/tests; the
absence of a backend dispatch route is not considered a completed migration.

### 3. Education and knowledge transfer — high priority

`school_lesson` directly increments pupil literacy or capability from teacher
role, pupil life/learning flags, and the teacher's level (`worlds/bigville_world.py:5447-5463`).
`teach_reference` directly copies a reference when the teacher knows it
(`6589-6593`), and `read_recipe` directly adds recipe knowledge after a literacy
check (`6595-6614`). These functions make the world decide learning outcomes.
A teacher's presence, a lesson, and a written recipe can be world observations;
understanding and acquisition should be learner-side cognitive updates.

Before the migration, period advancement also updated schooling and
apprenticeship attributes. The live Python path has now been removed; the
`ed_school` and `sk_apprentice` seed definitions remain historical data and do
not run in the current world engine.

Exact tests to preserve or extend:

- `tests/test_bigville_world_migrated.py::test_school_attendance_and_lessons_do_not_infer_literacy`
- `tests/test_bigville_world_migrated.py::test_canonical_school_journal_and_resident_plan_are_live_state`
- `tests/test_bigville_world_migrated.py::test_apprenticeship_is_observed_but_does_not_infer_skill_gain`
- `tests/test_bigville_topic_style_migrated.py::test_a_capped_apprentice_does_not_mint_a_new_event_every_period`

Implemented boundary: period advancement preserves attendance and apprenticeship
edges but does not change literacy, capability, or skill. `school_lesson` is a
bounded physical delivery record (teacher role, live pupil, adjacency, and the
teacher's major-action slot); it does not change learner attributes. Recipe and
reference `teach` methods now record an explanation attempt without adding
learner knowledge. Reading a book or written recipe returns its inscription as
an observation and leaves learner state untouched. Recipe execution is no
longer gated by `knows` edges or role labels: published work affordances and
execution require only physical inputs, usable tools, and the resident's
mechanical skill floor. Existing knowledge edges remain as authored/seeded
legacy priors, but they are not an action rule. `BigvilleGame` copies these
authored starting priors into private `CharacterDefinition` semantic memories;
the simple backend consults those memories before choosing recipe work. Thus
the world publishes physically feasible work without telling that backend the
resident has learned every option. Tests cover unknown recipes remaining
physically executable, private memory priors, the simple backend declining an
unknown recipe, explicit teaching and reading not changing learner knowledge,
and insufficient skill still refusing work.

Remaining blocker: the current game/backend protocol has no standardized
recipe-learning update or physically situated recipe-document observation.
Written recipe records are still legacy graph nodes rather than positioned,
held documents, and the old actor `knows` edges remain seeded for compatibility.
Backend-owned recipe comprehension therefore still needs a defined
world-observation and memory-update contract before the simulator can model it
end to end. The physical
recipe affordance currently identifies eligible recipes by ID but does not
publish the recipe's full instructions; a backend must not infer that its actor
knows those instructions from seeing a feasible work affordance.

### 4. Relationships — medium priority; seeding is appropriate, live outcomes need care

`set_relationship` creates a Bond held by one source resident, and `mutual=True`
creates a separate reverse model (`worlds/bigville_world.py:5063-5087`). That is
appropriate for authored prior beliefs if used at initialization. The method is
also callable during live simulation and writes those beliefs directly, so it
should not stand in for observed interaction or a social outcome. Actor context
publishes a nearby-resident relationship signal (`bigville/game.py:261-277`);
verify it reflects only the observer's own held bond and does not invent a shared
global relationship. No automatic relationship enforcement or obligation was
identified in the reviewed paths; speech choice uses the resident's private mind.

Exact tests to preserve or extend:

- `tests/test_bigville_game_api.py` relationship-context tests, including `test_nearby_residents_expose_floor_relationship_signal_when_no_bond_set`
- `tests/test_bigville_disposition_seed.py::test_seed_generated_relationships_reaches_actor_context`
- `tests/test_bigville_disposition_seed.py::test_seed_generated_relationships_feud_strength_is_negative`
- `tests/test_bigville_disposition_seed.py::test_seed_generated_relationships_not_auto_wired_into_from_town100`
- `tests/test_bigville_topic_style_migrated.py::test_townspeople_50_relationships_translate_to_real_set_relationship_calls`
- `tests/test_bigville_topic_style_migrated.py::test_a_bare_from_town100_still_seeds_zero_relationships`
- `tests/test_bigville_topic_style_migrated.py::test_town100_workplace_relationships_are_sparse_not_all_pairs`

Bounded next step: keep explicit authored ties as actor-held priors; have new
belief/affect changes derive from witnessed or communicated events in the
resident's mind. Test asymmetric beliefs directly.

### 5. Other economic settlement and automatic output allocation — medium priority

`sell_to_shop`, `sell_labor`, and `pay_wage` previously determined/settled a
price or wage and mutated coin, goods, and wage-due state. They now return false
without side effects. Physical conservation remains available through separate
explicit transfers; agreement and terms must be chosen by agents, and any
resulting transfers must be separate choices. Transaction records remain
evidence only for transactions initiated through other paths.

`_claim_canonical_job_outputs` automatically moves completed town100 job output
from common stock to the named maker's carrier (`worlds/bigville_world.py:1411-1433`).
The move itself is physical and conserved, but the automatic recipient assignment
is scenario economic allocation. Consider making collection a separate physical
action so no hidden rule allocates a produced good to its maker.

Relevant existing checks include
`tests/test_bigville_topic_style_migrated.py::test_a_completed_sale_mints_a_self_observed_event`, canonical village/job
and market tests in `tests/test_bigville_world_migrated.py`, and
`tests/test_package12_exchange_consent.py` transfer conservation tests.

## Recommended bounded order

1. Finish the package 12 boundary: remove utterance, `sell_willing`, price, and
   agreement as live world transfer gates; retain physical reach, possession,
   capacity, turn budget, and conservation. Make backend acceptance/refusal and
   payment observable actor choices. Run the exact package 12 tests above.
2. Close the law/policy context leak and separate registered-title evidence from
   physical action admissibility. Add unread-law-context and paired-policy tests;
   retain the existing law/council/deed regressions listed above.
3. Consolidate school/reference learning under the resident cognitive backend,
   first resolving duplicate direct and seeded advancement. Add accepted/refused
   lesson tests and preserve the school/apprenticeship regressions above.
4. Add a contested physical taking action with reach/capacity and observable
   consequences before claiming the property/enforcement package complete. Keep
   policy differences in backends and preserve the current witness-event tests in
   `tests/test_simple_norms_enforcement.py`.

The exact package test commands are documented in the corresponding package
findings. This audit did not run them; all proposed work remains outstanding.
