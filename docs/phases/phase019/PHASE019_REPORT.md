# Phase 019: derived knowledge priors (awareness, understanding, existence and location)

## Summary

Every founder's starting knowledge is now derived from their job, skills, implied history, literacy, household,
and the village's public spread. `domains/knowledge.py` holds the pure function `derive_knowledge(person, pack)`.
The result is seeded as each resident's private memories, split into `awareness` and `understanding` kinds. A
scenario actor with no recorded history still gets only the recipe priors its trades give, as before.

The implied history is drawn per founder on its own stream (`seed + 9019`), after the cast, households, and
genealogy. Names, ages, households, personality, literacy, and genealogy are unchanged. 20 founders have an earlier
apprenticeship in another trade, and their skill levels in that trade (and the metaskill those imply) are the only
numbers that moved. The list is under Changed numbers.

The seeded town has 29,455 memories, an average of 295 per resident. The game build for the town takes 0.33 s.
Self-test: 0 errors, 0 warnings. Full suite: 3 failed (the other session's Ocelot tests), 456 passed, 2 skipped.
The 23 new tests in `tests/test_phase019_knowledge.py` pass. No existing test was edited.

## Changes

New files:
- `domains/knowledge.py`: `derive_knowledge`, the person builders (`person_from_attrs`, `person_from_cast_record`),
  `knowledge_memories` (memory records from derived rows), `check_knowledge` (self-test references),
  `town_knowledge_shares` and `knowledge_shares_flags` (the shares table and its flags). Pure: no world, no backend.
- `packs/bigville/frames/knowledge.json`, `packs/test_hamlet/frames/knowledge.json`: `KNOWLEDGE_TOPICS` (21),
  `KNOWLEDGE_RULES`, `JOB_PUBLIC` and `JOB_ROUTINE` (28 jobs each), `KNOWABLE_PLACES` (market, field, pasture),
  `PROCEDURE_KNOWLEDGE` (lawmaking, justice). The hamlet's copy is filtered to its own skills, jobs, and places.
- `packs/bigville/population/history.json`, `packs/test_hamlet/population/history.json`: `HISTORY` (distributions,
  stream, citations) and `FORMER_TRADES` (18 trades an apprentice might have left).
- `tests/test_phase019_knowledge.py`: 23 tests, one group per Acceptance bullet plus purity, seeding, history, and
  self-test checks.

Pack edits (both packs unless noted):
- `seed_roles` removed everywhere. Each entry carries a `knowledge` spec:
  - recipes (163, `world/recipes.json`), buildings (35, `world/buildings.json`; `house` is `personal`), deposits (3),
    water sources (4), animals (8, `world/animals.json`), offices (6, `frames/governance_offices.json`),
    kin terms (20, `frames/kinship.json`), shared concepts (25, `frames/shared_concepts.json`),
    laws, policies, and charters (their bundle files; the hamlet's `hamlet_common_law` too).
  - Procedures are in `PROCEDURE_KNOWLEDGE` (knowledge.json). The lawmaking and justice tables are stage dicts,
    so they cannot carry a spec without changing their consumers.
- `packs/*/pack.json`: manifest entries for the eight new tables.
- `packs/bigville/world/recipes.json` is in the exporter's key order (the export test compares bytes).

Code:
- `domains/population.py`: `draw_founding_history(residents, seed)`, `HISTORY` and `FORMER_TRADES` bindings.
- `domains/shared_frames.py`: `all_reference_templates` reads `knowledge` (a concept inherits its bundle's spec).
  `shared_concepts_for` is removed. It assigned concepts by role, nothing called it, and the boundary audit forbids
  that kind of assignment.
- `domains/bigville_entities.py`: imports `domains.knowledge`; `_check_knowledge` runs in `check_consistency`.
- `domains/data_view.py`: `knowledge` joins the module list of a pack view. Outside the listed write scope, but the
  hamlet view could not load without it.
- `worlds/bigville_town100_world.py` (`generate_cast100`): draws each record's `history` and `former_skills` after the
  cast is complete.
- `worlds/bigville_world.py`: `populate_town100` stores `history` on the actor node and calls `seed_skill_floor`;
  `seed_skill_floor` is new.
- `bigville/game.py`: the recipe block in `_characters_from_world` is replaced by the derived seeding, and
  `_derived_knowledge_memories` is new. The backend is not touched: the simple backend still reads
  `recipe_knowledge` memories.
- `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json`: regenerated. The only new keys are
  `history` and `former_skills`.

### Knowledge spec format

```json
"knowledge": {
  "topics": ["milling_and_baking"],
  "public": 0.9,
  "after_years": 0,
  "understanding_requires": [
    {"trade": "baker"}, {"skill": "baking", "level": 0.0}, {"apprenticed": "baker"}
  ]
}
```

- `topics`: names in `KNOWLEDGE_TOPICS`.
- `public` (0..1): how widely awareness spreads by living in the village. At or above `public_cutoff` (0.2) every
  resident with `after_years` in the village is aware. Below it, only a topic link, a role, or history makes a thing
  known. The values are authored judgement (APPROX).
- `understanding_requires`: every condition must hold. Conditions: `{skill, level}`, `{metaskill, level}`, `{trade}`
  (practised, including a former trade), `{apprenticed}`, `{literacy: functional|educated}`, `{office}`,
  `{authority}` (holds an office of that authority, e.g. `deliberative`), `{served: council}`, `{years}`, and
  `{any: [...]}`.
- `written` (bundles; default true): a written law, policy, or charter also needs DOCUMENT_LITERACY's tier for its
  kind. No entry sets `written: false` yet.
- `personal` (buildings): the place is each resident's own, so it is not listed.

Offices are referenced by `authority`, not by name, so a child pack that renames an office keeps valid specs.

### Topic links

`KNOWLEDGE_TOPICS` maps 21 topics to skills, skill clusters, and metaskills. Every one of the 46 skills belongs to a
topic (a self-test warning otherwise). Each topic is a `knowledge` tag, so an item is linked to what its holders do.
Examples: `milling_and_baking` (milling, baking; cluster foodcraft), `land_law` (law, reckoning; cluster letters).

### History model and sources

`draw_founding_history` draws nine uniforms per founder in a fixed order, from `default_rng(seed + 9019)`:

| Fact | Rule |
|---|---|
| Local or incomer | local with probability 0.6 (adults) or 0.9 (children in the household) (APPROX) |
| Years in village | local: all of their age. Incomer: uniform 1 to age-1 |
| Schooling | literate: 2 to 8 years (APPROX). Unlettered: 0 |
| Apprenticed in current trade | probability 0.15 / 0.3 / 0.2 for low / middle / high group (APPROX). A history fact only |
| Former trade | probability 0.25 (APPROX), age 25 or older, from 18 trades; years 1 to 6 (APPROX) |
| Former-trade level | min(trade base_skill, 0.1 x years) (model choice, APPROX) |
| Past office | councillor, probability 0.08 (middle) or 0.15 (high) (APPROX); the council is served by councillors |
| Widowed | household head with no spouse in the household, age 45 or older, probability 0.25 (APPROX) |

Consistency: an incomer's years are at least 1 and at most their age; the unlettered have no schooling; a former
trade's years fit the age; its level equals the formula above and never exceeds the trade's base skill.

Sources (from memory, not checked against the texts): Statute of Artificers 1563 (5 Eliz. c. 4) for the seven-year
apprenticeship term, which the history does not use directly because the current-trade apprenticeship is a fact
only; Kussmaul (1981) on servant and apprentice ages (start about 14); Cressy (1980) on signature literacy and
schooling (the schooling range is APPROX; the literacy shares come from 016a's class table); Laslett (1972) on
households, as Phase 009. Every value in `HISTORY` is marked APPROX in its `_doc`.

### Derivation rules

Per item type (`derive_knowledge` returns one row per item, `aware`, `understands`, `basis`, and `location` for places):

- Recipe: aware if the trade is practised, or a skill in its cluster is held, or the topic link or public spread
  applies. Understood if the trade is practised, the working level of its skill is at least `MIN_SKILL`, and, for an
  uncommon recipe, the person is apprenticed in that trade. The degree is the working level (`effective_skill`,
  including closeness transfer).
- Law, policy, charter, concept, procedure, office, animal: aware by public spread or topic link, or by a role
  condition met (office, skill, trade, history). Understood only if aware, to the degree the conditions give
  (1.0 when none apply). Literacy and years are capacities and never make a thing known.
- Kin term: aware by public spread (1.0). Understood if the resident holds the term in the genealogy.
- Place (buildings, deposits, water, market, field, pasture, own home): exact if on the resident's routine (their
  home, their job's `JOB_ROUTINE` places, and the buildings of their trades). Roughly if public spread reaches them
  and the resident has lived there long enough. Otherwise none. Existence is aware if location is not none, or by
  public spread or topic link. Degrees: exact 1.0, roughly 0.5, none 0.
- Resident (neighbour): aware if they share the household, work at the same anchor, or hold a public-facing job
  (`JOB_PUBLIC` at or above the cutoff).
- Good: aware if store-sold (`STORE_GOODS_PUBLIC`) or used or made in a recipe the resident is aware of.
  Understood if such a recipe is understood.

Understanding implies awareness by construction (`_row`).

### Seeding and memory kinds

`knowledge_memories` makes one record per aware item, with content `{item, type, name, aware, understands, basis,
source}`. Kinds:
- `understanding`: understood to any degree.
- `awareness`: aware only.
- `recipe_knowledge`: an understood recipe. This is the kind the simple backend reads for work and the kind about ten
  tests check. The derived recipe memory also carries `recipe` and `belief: can_attempt`.

Places add `location`, `learned` ("founding"), `period` (0), and the position believed: `position` for an exact
location (the world's cell, or the home cell), and `landmark` (from `FOUNDING_ANCHOR_ALIASES`) for a rough one.
Positions are from the world at founding, not the map: no memory holds the map.

Scenario-authored priors override derived ones: an existing memory with the same `item` is not replaced, and explicit
`recipe_priors` replace derived recipe memories. A resident with no `history` (a scenario actor) gets recipe priors
only.

The world holds no beliefs. Seeding reads world facts (job, skills, household, kin terms, cells) and writes only to
the character's memories. Nothing writes memories after founding.

### Location model

Exact, roughly, or none, as above. The routine for each job is authored in `JOB_ROUTINE`. A farm labourer knows the
field and the granary exactly (both on the farm routine), the tannery roughly (market-anchored and publicly known),
and a newcomer of one year does not know the stone deposit (the quarry, three years to spread).

## Validation

| Check | Command | Result |
|---|---|---|
| Self-test, bigville (before) | `python3 domains/bigville_entities.py` | exit 0; ERRORS 0, WARNINGS 0 (`selftest_before.txt`) |
| Self-test, bigville (after) | same | exit 0; ERRORS 0, WARNINGS 0 (`selftest_after.txt`) |
| Hamlet check (before) | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0, WARNINGS 0 (`hamlet_before.txt`) |
| Hamlet check (after) | same | exit 0; ERRORS 0, WARNINGS 0 (`hamlet_after.txt`) |
| Phase 019 tests | `pytest tests/test_phase019_knowledge.py` | 23 passed |
| Full suite, before | `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 3 failed, 433 passed, 2 skipped (`pytest_before.txt`) |
| Full suite, after | same | 3 failed, 456 passed, 2 skipped (`pytest_after.txt`) |
| Full suite, other session's Ocelot files ignored | same, with `--ignore` for the three files below | 456 passed, 2 skipped (`pytest_ignoring_other_session_ocelot.txt`) |

The three failures are the other session's, and they fail on the baseline too (`baseline_failures.txt`):
```
FAILED tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities
FAILED tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control
FAILED tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action
E   ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'
```

Also run: the export byte test (`test_export_rerun_is_byte_identical`) passes after `world/recipes.json` was written
in the exporter's order. The 100-resident village run was not run (not asked).

## Self-test findings: the seeded town's shares

The table is in the self-test INFO section (`selftest_after.txt`). Shares are over the 100 founders. Laws and policies
are understood by the literate share (0.78), and nearly everyone is aware of them:

| Item | Aware | Understands |
|---|---|---|
| law:commons_and_land_law | 1.00 | 0.78 |
| law:public_order_law | 1.00 | 0.78 |
| law:giantville_theft_law | 1.00 | 0.78 |
| law:giantville_murder_law | 1.00 | 0.78 |
| policy:winter_food_reserve | 0.98 | 0.77 |
| policy:water_safety_policy | 1.00 | 0.78 |
| policy:giantville_public_health_baseline | 0.99 | 0.77 |
| charter:bigville_council_charter | 0.04 | 0.03 |

Trades (holders of the trade; "core recipe" means any recipe whose `requires` is the trade): every trade's holders
understand a core recipe (1.00 in all 20 trades that have holders in the cast; 5 recipe trades have none). The share
of all residents aware of one core recipe ranges from 0.03 (smith, cobbler) to 1.00 (cook, farmer, tailor, weaver),
because those recipes are linked through the food, field, and fibre clusters.

Concepts with zero understanding are data facts about the cast, not errors. `granary_is_long_term_storage` and
`latrine_kept_away_from_well` need storekeeping and sanitation, and no founding job practises either (the
`granary_keeper` and `sanitation_keeper` trades have no JOBS entry). `deed_is_evidence_of_transfer` has aware 0.03 and
understands 0.00. The clerk and the mayor are aware through their reckoning, but the concept asks for the law skill, which
no founder has.

Flags: a law no one is aware of is an error; a law aware to fewer than 0.2 of residents, or a trade whose holders
understand a core recipe at below 0.5, is a warning (thresholds in `KNOWLEDGE_RULES`). None fired.

## Memory counts and timing

| | HEAD | This phase |
|---|---|---|
| Memories per resident (mean, min to max) | 4.3 (all `recipe_knowledge`) | 294.6 (218 to 438) |
| Total seeded memories | 432 | 29,455 |
| By kind | recipe_knowledge 432 | awareness 20,334; understanding 8,579; recipe_knowledge 542 |
| `BigvilleGame(from_town100(), autonomous=True)` | 0.00 s (below timer resolution) | 0.33 s to 0.36 s |

Derived memories by type, all residents: goods 7,549; residents 7,598 (aware only); places 4,497; recipes 3,109;
concepts 2,403; kin terms 2,000; animals 798; offices 600; procedures 200; laws 400; policies 297; charters 4.

`from_town100()` itself takes 0.25 s to 0.37 s, unchanged in kind. Derivation is about 3 ms per resident.

Recipes against the legacy rule (the 100 founders, same cast): the legacy rule gave 432 recipe priors. Derived
recipe understanding gives 542 (+110). None of the 432 is lost. The additions are the recipes of former trades
(of the 110 additions, 71 are for labourers with an earlier apprenticeship, and 29 for farmers).

## Changed numbers

Skill and metaskill levels changed for 20 founders. Each is a former-trade apprenticeship with level
min(base skill, 0.1 x years). The main `skill` and every current-trade level are unchanged, as are all other
attributes. Metaskill values use `META_FROM_SKILL` (0.6) x skill level, the rule `add_actor` uses.

| Founder | Job | Former trade | Years | Level | Skill levels (before to after) | Metaskill (before to after) |
|---|---|---|---|---|---|---|
| Adelina Gorse | labourer | sawyer | 1 | 0.1 | sawing 0.0 to 0.1 | craftsmanship 0.0 to 0.06 |
| Adelina Norbisham | labourer | cook | 1 | 0.1 | cooking 0.0 to 0.1 | provisioning 0.0 to 0.06 |
| Barnaby Rushton | labourer | mason | 6 | 0.6 | masonry 0.0 to 0.6 | craftsmanship 0.0 to 0.36 |
| Constance Ottermole | farmer | butcher | 1 | 0.1 | butchery 0.0 to 0.1 | none |
| Corvin Cobb | labourer | tailor | 3 | 0.3 | tailoring 0.0 to 0.3 | craftsmanship 0.0 to 0.18 |
| Corvin Kindle | weaver | dyer | 4 | 0.4 | dyeing 0.0 to 0.4 | none |
| Cuthbert Wold | farmer | dairymaid | 2 | 0.2 | dairying 0.0 to 0.2 | none |
| Doreen Ferrety | fishmonger | miller | 6 | 0.6 | milling 0.0 to 0.6 | provisioning 0.0 to 0.36 |
| Garnet Hollow | constable | mason | 6 | 0.6 | masonry 0.0 to 0.6 | craftsmanship 0.0 to 0.36 |
| Henrietta Peaseblossom | labourer | weaver | 2 | 0.2 | spinning and weaving 0.0 to 0.2 | craftsmanship 0.0 to 0.12 |
| Ida Ditchwater | clerk | mason | 1 | 0.1 | masonry 0.0 to 0.1 | craftsmanship 0.0 to 0.06 |
| Jem Grubb | labourer | dyer | 6 | 0.6 | dyeing 0.0 to 0.6 | craftsmanship 0.0 to 0.36 |
| Lemuel Bindle | innkeeper | mason | 4 | 0.4 | masonry 0.0 to 0.4 | craftsmanship 0.0 to 0.24 |
| Lemuel Bramble | labourer | butcher | 2 | 0.2 | butchery 0.0 to 0.2 | provisioning 0.0 to 0.12 |
| Mordecai Hobb | labourer | cobbler | 5 | 0.5 | shoemaking 0.0 to 0.5 | craftsmanship 0.0 to 0.3 |
| Mordecai Tremble | labourer | brewer | 4 | 0.4 | brewing 0.0 to 0.4 | provisioning 0.0 to 0.24 |
| Prudence Gorse | labourer | collier | 2 | 0.2 | charcoal_burning 0.0 to 0.2 | stewardship 0.0 to 0.12 |
| Septimus Underhill | labourer | tanner | 1 | 0.1 | tanning 0.0 to 0.1 | craftsmanship 0.0 to 0.06 |
| Thaddeus Ramskin | farmer | smith | 3 | 0.3 | smithing 0.0 to 0.3 | craftsmanship 0.0 to 0.18 |
| Winifred Ottermole | labourer | miller | 6 | 0.6 | milling 0.0 to 0.6 | provisioning 0.0 to 0.36 |

"None" means the metaskill level did not change: the former trade's metaskill was already at least that high.
These are the 20 residents whose attributes differ from the pre-change snapshot. Every other resident is identical.

No existing test number was changed. The 23 tests are new.

## Deviations

1. Understood recipes keep the kind `recipe_knowledge` rather than a new `understanding` kind. The simple backend and
   about ten existing tests read that kind. Other understood items use `understanding`.
2. Derived awareness is seeded only for residents with a `history`. A scenario actor (no history) gets recipe priors
   only, so the existing lesson test (`test_lesson_offer_is_a_backend_choice...`) keeps its intent. This is the main
   limit of the scenario path: the derived knowledge is a founding feature.
3. Office specs sit inline in the `GOVERNANCE_OFFICES` rows. An office with no spec (a renamed office in a child pack)
   is known only to its holder, and the self-test reports it as info. The phase 015 fixture renames offices and
   replaces the table, so an error here would break an existing test.
4. Office conditions use `authority`, not office names, for the same reason.
5. Procedure knowledge is in the sibling table `PROCEDURE_KNOWLEDGE`, not in the stage dicts.
6. `data_view.MODULES` gained `knowledge`. The hamlet view could not load without it.
7. `shared_concepts_for` was removed rather than rewritten (no callers).
8. Only the founders' aptitude, talents, and limitations are drawn with the world's own stream, for the shares table.
   `person_from_cast_record` reproduces `draw_capacities`, so the table matches a world built from the same seed.
9. Other seeded or legacy files still say `seed_roles` (`bigville/seeds/*.json`, `docs/phases/phase013b/author_hamlet.py`).
   They are not pack files. I left them alone.

## Limits

- Not modelled: bereavement and marriage as history events (marriage is the household role only); children and
  lodgers; the routes between home and work; other residents' homes as location items (co-residents are aware of,
  not located); stalls within the market; water sources have landmark positions only.
- Public spread values, the history distributions, the routine lists, and the topic map are authored judgement, not
  measured. They are APPROX, and the citations are from memory.
- The shares are for the 100-resident founding cast at seed 305000, one seed. They do not show the balance of the
  village.
- The cognition context does not yet show derived knowledge. The world's `known_laws` and `known_policies` in
  `_context` still come from `law_knowledge` and `policy_knowledge` memories, which derivation does not write. A
  derived law the resident understands is not in their context frames (see Follow-ups).
- A location belief for an exact place is a position at founding. Nothing updates it, as the brief requires. No stale
  belief is created by the seeding itself.
- The founding cast has no storekeeper or sanitation worker (the JOBS table has no such job), so the storekeeping and
  sanitation concepts are understood by no one.

## Open questions

1. Should the public-spread cutoff (0.2) be a per-item rule or stay one threshold? A single cutoff makes a village
   fact known to every resident who has lived there long enough. Items below it need a topic or a role.
2. Should `JOB_PUBLIC` at or above the cutoff make every holder of a notable job known to all? That makes the 38 founders with a
   public-facing job known to each resident (76 resident memories on average, including household and co-workers). It is judged plausible for a village of 100.
3. Should a scenario actor get the derived awareness as well? That would change the scenario tests that count
   memories, so I held back.
4. Should the 0.2 cutoff apply to laws as well as to places? The charter is the only item that is nearly unknown (0.04).

## Follow-ups

For Phase 017 (generated Ocelot seeds):
- Generate each resident's knowledge seed with `derive_knowledge` and `knowledge_memories`. The output is a list of
  `{memory_id, kind, content}` records, ready to become Ocelot memories.
- The seed is about 295 records per resident (29,455 in total). Consider sending only awareness or understanding of
  the derived items the resident's context needs, rather than all of them.

For Phase 018 (LLM instructions):
- Carry only derived awareness and understanding. Give an aware-only item as its name and gist (its `basis` is the
  reason, not the content). Give a located place at the precision held: an exact cell, or the landmark for a rough
  location. Never the map.
- The `basis` strings are for reports and tests. Do not paste them into a prompt verbatim.
- Decide how a derived law reaches the context. Today `_context` reads only `law_knowledge` memories, so an understood
  law is absent from `world_frames.laws`. That is the boundary audit's concern, and 018 must not restore the global
  law list.

## Working tree

Start (`git status --short`): the other session's modified files (README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py),
and its untracked files (game_persistence, mixed_ocelot_scenario, world_persistence, the persistence and Ocelot tests,
tools, docs, and docs/runs/).

Files I changed or created: `domains/knowledge.py` (new), `domains/population.py`, `domains/shared_frames.py`,
`domains/bigville_entities.py`, `domains/data_view.py`, `packs/bigville/frames/{charters,giantville_laws,
giantville_policies,governance_offices,kinship,local_laws,local_policies,shared_concepts}.json`,
`packs/bigville/frames/knowledge.json` (new), `packs/bigville/population/history.json` (new),
`packs/bigville/world/{animals,buildings,recipes,resource_deposits,water_sources}.json`, `packs/bigville/pack.json`,
`packs/test_hamlet/frames/{kinship,local_laws,knowledge}.json` (knowledge new), `packs/test_hamlet/population/history.json`
(new), `packs/test_hamlet/world/{buildings,recipes}.json`, `packs/test_hamlet/pack.json`, `seeds/bigville_cast100.json`,
`bigville/seeds/bigville_cast100.json`, `worlds/bigville_town100_world.py`, `tests/test_phase019_knowledge.py` (new),
and this report and its logs in `docs/phases/phase019/`.

Hunks in shared files, by function, for staging:
- `bigville/game.py`, mine: `_derived_knowledge_memories` (new method, before `_characters_from_world`) and the three
  hunks inside `_characters_from_world` (the recipe block). The other session's hunk is `_apply_response`
  (`record_action_outcome`).
- `worlds/bigville_world.py`, mine: `populate_town100` (the `history` attribute and the `seed_skill_floor` call) and
  `seed_skill_floor` (new, after `set_skill_level`). The other session's hunks are `_actor_options` (one line) and
  `resident_plan_from_context`.

Nothing was committed, branched, stashed, or reverted. I did not edit `docs/FEATURE_PHASES.md` or any test of the other
session's (`tests/test_bigville_game_api.py` and `tests/test_bigville_scenarios.py` contain its hunks; my one new
test is in its own file).
