# Phase 009: kinship, households, and inheritance

## Summary

Genealogy is now a world fact, and kin terms are held by residents. The founding town (the
100-resident cast from `BigvilleWorld.from_town100()`) gets a seeded genealogy: 100 founders, 924
out-of-village kin, 197 unions, and 2,849 genealogical kin terms held by the founders. A held term can
disagree with the genealogy without error. On a death, the world publishes the genealogical heirs under a
data-selected custom (default partible) as an observed event and a `HeirRecord` that names successors for
the existing `inheritance` deed type. No property moves.

The household-size and extended-family shares are drawn from cited distributions and checked by the
self-test. The founding cast does not use those household draws. The cast still has one household per
resident, which Phase 016/003 must change.

The self-test is 0 errors and 0 warnings. The full suite gives 416 passed, 3 failed, 2 skipped. The three
failures are the other session's Ocelot tests and were failing before this phase's edits.

## Changes

New data (JSON, in the bigville pack; test_hamlet holds identical copies):

- `packs/bigville/frames/kinship.json`: `KIN_TERMS` (20 terms), `KIN_ATTRIBUTION` (5 kinds),
  `KIN_OBLIGATIONS` (5), `INHERITANCE_CUSTOM` (default `partible`, plus `primogeniture`).
- `packs/bigville/population/household_composition.json`: `HOUSEHOLD_SIZE`, `EXTENDED_FAMILY`,
  `EXTENDED_KIN`, `AGE_AT_FIRST_UNION`, `CHILDREN_PER_UNION`, `INFANT_SURVIVAL`, `ADULT_LIFESPAN`,
  `PARENT_AGE_AT_BIRTH`, `KIN_MODEL`, `KINSHIP_STREAM` (9009), `HOUSEHOLD_TARGETS`.
- `packs/bigville/pack.json`: 15 manifest entries added for the tables above.
- `packs/test_hamlet/frames/kinship.json`, `packs/test_hamlet/population/household_composition.json`,
  and `packs/test_hamlet/pack.json` (same 15 entries): copies of the bigville files.

Code:

- `domains/shared_frames.py`: binds `KIN_TERMS`, `KIN_ATTRIBUTION`, `KIN_OBLIGATIONS`,
  `INHERITANCE_CUSTOM`.
- `domains/population.py`: binds the household tables. Adds the pure functions `draw_household`,
  `draw_household_size`, `describe_household_distribution`, `draw_founding_kin`, `index_kinship`,
  `kin_relatives` (path matching), `genealogical_heirs`, and `describe_founding_kin`.
- `domains/bigville_entities.py`: `check_consistency` checks the kin tables (reciprocals, path steps,
  attribution links, obligations, custom tiers), the household and KIN_MODEL shares, and the household draw
  against `HOUSEHOLD_TARGETS`. It reports the draw and the founding-kin shape as INFO and raises an error
  when a draw falls outside tolerance.
- `worlds/bigville_world.py`: `populate_town100` calls `_found_kinship` as its last step, so no node id
  created earlier moves. The new methods sit after `populate_town100`: `_found_kinship`, `_hold_kin`,
  `_person_node`, `_kin_index`, `_kin_clock`, `genealogical_kin`, `kin_terms_held`, `hold_kin_term`,
  `publish_heirs`, `_record_kin_death`. `_record_death_event` calls `_record_kin_death` once per death.
- `tests/test_phase009_kinship.py`: 16 new tests (listed under Validation).

Graph vocabulary added: node types `Kin`, `Union`, `KinTerm`, `HeirRecord`. Edges `bore` (mother to child),
`fathered` (father to child), `union_with` (both ways between partners), `in_union`, `holds_kin_term` (holder
to term node), `of_kin` (term node to target), `has_heir_record`, `heir_record`. Founders keep their Agent
node and gain `kin_sex`, `kin_birth`, `kin_dead`, `kin_death`. The graph does not store edge attributes, so
each union's start and end periods sit on its `Union` node, and each person's birth period sits on the
person node. Periods are years from the founding clock (founding = 0).

Other files: `packs/*/pack.json` and the two new JSON pairs were re-serialised to the exporter's layout
(`json.dumps(indent=2, ensure_ascii=False)`), because `test_export_rerun_is_byte_identical` compares bytes.

## How founding genealogy is generated and fitted to the cast

`draw_founding_kin(founders, rng)` takes the cast's names and ages and draws from its own generator,
`np.random.default_rng(map_seed + KINSHIP_STREAM)`. The world's streams are not consumed. Steps:

1. Each founder is a child of a couple. Parents are dead or alive outside the village; their deaths come
   from `ADULT_LIFESPAN` and are never before the child's birth.
2. The couple's other children are founders with probability `SIBLING_IN_VILLAGE` (0.25), else people
   outside the village.
3. Each parent's parents are an existing couple in the record with probability `GRANDPARENT_REUSE` (0.3),
   else a new couple with their own other children. Reuse makes two parents siblings and their children
   cousins. The record stops three generations above the founders.
4. A founder has a union with probability `EVER_MARRIED` (0.8). The spouse is a founder with probability
   `SPOUSE_IN_VILLAGE` (0.3), else a person outside the village. Union start follows
   `AGE_AT_FIRST_UNION`.
5. Children are born after a union starts and before either parent dies, spaced by `CHILD_SPACING_YEARS`.
   Child count follows `CHILDREN_PER_UNION`. Infant deaths follow `INFANT_SURVIVAL`.

Generated shape for the 100-founder cast (`describe_founding_kin`, seed 305009): every founder has a parent
on record, 69% are joined by a union, every founder has an aunt or uncle, 60% have a first cousin, and
married founders average 2.5 children.

The cast gives every founder the default age of 30 (`ACTOR_DEFAULTS.age`), and the genealogy uses that age.
Children of founders therefore fall in the few years before the founding year, which limits the count.

Held terms: `kin_relatives` follows each term's paths from the holder. A target takes the first term in
table order that fits (its sex, and `shared_parents` where set). Every founder holds its genealogical terms
as `KinTerm` nodes with attribution `genealogy`. The founding seed writes only these genealogical terms.
Fictive terms are not seeded. They arrive through `hold_kin_term`.

## Inheritance

`INHERITANCE_CUSTOM.default = "partible"`: a spouse takes an equal share with the children in the first tier,
and the children split equally. Parents and then siblings inherit only if the tier above has no living member.
`primogeniture` (spouse as life interest, eldest child takes all) is the second custom in the table; select it
by name.

`publish_heirs(name)` (called from every death of a founder): sets `kin_dead` and `kin_death`, computes heirs
from the graph, writes a `HeirRecord` (predecessor, custom, `deed_type: inheritance`, heirs with shares and life
interest), and records a public `heirs_published` event. It changes no stock, coin, carried goods, land title,
land holder, or household. The `inheritance` deed is still for the records office to write, using `write_deed`.

## Validation

Commands and results (working tree, after the last edit):

- `python3 domains/bigville_entities.py`: exit 0. ERRORS (0), WARNINGS (0). INFO includes:
  - `HOUSEHOLDS: household size (mean members): sample 4.676 vs 4.750 (tolerance 0.30; Laslett 1972; Wrigley and Schofield 1981 (APPROX))`
  - `HOUSEHOLDS: extended-family share of households: sample 0.101 vs 0.100 (tolerance 0.03; Laslett 1972 (APPROX))`
  - `FOUNDING KIN (100 adults of 30, ...)`: 100% have a parent on record, 69% joined by a union, 100% have an aunt or uncle, 60% have a first cousin, married founders average 2.5 children.
- `python3 -m domains.check --pack test_hamlet`: exit 0. ERRORS (0), WARNINGS (0).
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider`: **3 failed, 416 passed, 2 skipped** (93 s).
  - Failed, verbatim error: `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` (from `bigville/backends/ocelot.py`, raised as `OcelotUnavailableError`):
    - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
    - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
    - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`
  - These three fail on the shared tree before any Phase 009 edit (run at session start: 3 failed, 400 passed, 2 skipped). They belong to the other session's uncommitted files. Ignoring them, the suite passes: 416 passed, 2 skipped.
  - Before the fix to `test_export_rerun_is_byte_identical` (my JSON layout), that test failed. It passes now.
- `tests/test_phase009_kinship.py`: 16 passed.
  - Genealogy at founding: `test_genealogy_is_recorded_for_every_founder`, `test_births_are_bore_or_fathered_by_the_parent_sex`, `test_the_founding_genealogy_is_the_same_for_the_same_seed`.
  - No change to residents or stock: `test_founding_genealogy_leaves_every_resident_and_the_stock_unchanged` (builds the town with and without `_found_kinship`, compares every non-kin attribute, stock, households, and land owners).
  - Aunt by path: `test_an_aunt_is_identified_by_her_path` (walks the graph, not the E helper).
  - Fictive uncle with no path: `test_a_fictive_uncle_is_held_by_a_resident_with_no_genealogical_path`.
  - Disagreeing layers: `test_the_held_term_and_the_genealogy_may_disagree_without_error`; attribution limits: `test_an_attribution_only_gives_the_terms_it_lists`.
  - Death and heirs: `test_a_death_publishes_genealogical_heirs_and_moves_no_property`, `test_primogeniture_gives_the_eldest_child_the_whole_and_the_spouse_a_life_interest`, `test_publishing_heirs_for_a_resident_with_no_genealogy_is_a_no_op_on_the_record`.
  - Pure draws: `test_relatives_by_path_distinguish_full_and_half_siblings`, `test_generated_genealogy_is_consistent_with_its_own_ages`, `test_a_founder_has_a_grandparent_and_an_aunt_or_uncle_by_path`.
  - Self-test: `test_the_self_test_reports_household_and_extended_family_shares_against_their_sources`, `test_the_test_hamlet_pack_keeps_the_kinship_tables_and_a_clean_self_test`.
- Build cost: `BigvilleWorld.from_town100()` takes about 0.5 s with the kinship graph (Agent 130, Kin 924, Union 197, KinTerm 2849).

Existing tests were not edited.

## Limits

- **Households are not drawn for the cast.** `populate_town100` makes one household per resident
  (`add_household` per record). `draw_household` is used only in the self-test. The founding town's
  household sizes do not match the cited distribution. Phase 016/003 must change this.
- **Ages are the cast default.** Every founder is 30 (`ACTOR_DEFAULTS.age`). Married founders therefore have
  about 2.5 children on record, below the 4.8 mean draw, because their births must fit the few years since
  their union. Real ages would change this.
- **Genealogy depth and coverage.** The record stops three generations above the founders. Out-of-village
  kin have no recorded children, so a founder's cousins are the children of founder-linked parents only.
  Great-grandparents and more distant kin are absent.
- **No half-siblings, step-family, or godparents in the genealogy.** `half_sibling` has a path and a
  `shared_parents: one` filter, but the generator makes no second unions, so none arise. `step_*` and
  `godparent` have no path and arise only by attribution.
- **Spouses.** 69% of founders are joined. A joined founder's spouse is another founder when an eligible
  partner (opposite sex, not a sibling, born within 10 years) exists and a 0.3 draw succeeds; otherwise the
  spouse is outside the village. Spouse pairing is a model parameter, not a measured figure.
- **Sources.** No web or document access was available this session. The citations (Laslett 1972; Wrigley and
  Schofield 1981; Hajnal 1965; Goody, Thirsk and Thompson 1976) are written from knowledge of those works, and
  I did not check the figures against the texts. Every household and kin number in the pack is marked APPROX.
  The default partible custom is a model choice. Verify the figures before relying on the exact values.
- **Only the founding town has genealogy.** `from_scenario` and `from_townspeople_50` worlds have no kin
  nodes. `kin_terms_held` returns an empty list for them. `genealogical_kin` and `publish_heirs` raise for
  them, and `publish_heirs` returns None.
- **Heirs are published at every founder death** (`heirs_published`, public). Deaths of non-founders do
  not publish, because they have no kin record.

## Open questions

1. Should heir publication be public (every resident sees it, as the event does now) or limited to the records
   office? I chose public because the brief calls it an observation.
2. Should the default custom stay partible? The choice is a model default, and primogeniture is in the table.
3. Phase 016/003: should the cast get real ages and households before genealogy is redrawn? The current
   draw assumes the cast's default ages.

## Follow-ups

- Phase 016/003: give the cast ages and household assignments, then apply `draw_household` and redraw the
  founding genealogy from those ages. The genealogy stream is seeded separately, so the cast's own draws stay
  unchanged.
- A records-office step that writes an `inheritance` deed from a `HeirRecord` (existing `write_deed`). It is not
  automatic here, and I did not add one.
- Second unions in the generator, to produce half-siblings and step-family.
- Deeper genealogy (great-grandparents) if the kin terms need longer paths.

## Working tree

Start of phase (`git status --short`): the other session's uncommitted files (README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py,
and the untracked files of the same session (game_persistence, mixed_ocelot_scenario, world_persistence, and several tests, tools, and docs).
My edits to `worlds/bigville_world.py` are additive hunks: the new kinship methods after `populate_town100`,
one call in `populate_town100`, and one call in `_record_death_event`.

End of phase: the same entries, plus these files from this phase:

- Modified: `domains/bigville_entities.py`, `domains/population.py`, `domains/shared_frames.py`,
  `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`, `worlds/bigville_world.py` (additive).
- New: `packs/bigville/frames/kinship.json`, `packs/bigville/population/household_composition.json`,
  `packs/test_hamlet/frames/kinship.json`, `packs/test_hamlet/population/household_composition.json`,
  `tests/test_phase009_kinship.py`, `docs/phases/phase009/PHASE009_REPORT.md`.

Nothing was committed.
