# Bigville feature phases

This is the plan for extending the world now that the entity data is in place
(world affordances, shared frames, population, and the self-test in
`domains/bigville_entities.py`). Each phase is one bounded brief for the
`bigville-phase-executor` agent (`.kiro/agents/bigville-phase-executor.md`).

## How a phase runs

1. The supervising session picks the next phase whose status is **ready**, and
   confirms its dependencies are committed.
2. The executor implements it within its write scope, runs the self-test and
   the full test suite, and writes `docs/phases/phaseNNN/PHASENNN_REPORT.md`.
   It never commits.
3. The supervisor reviews the diff and report, corrects or reruns as needed,
   updates this file's status line for the phase, and commits.

Every phase shares these acceptance conditions, in addition to its own:
- `python3 domains/bigville_entities.py` exits 0 with 0 errors and 0 warnings.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` passes.
- No existing assertion is weakened; any changed test numbers are listed in the
  report with the reason.
- New data has self-test checks for its cross-references, and any real-world
  figure cites a source (or is marked APPROX).

Status values: **ready**, **blocked** (needs a decision or an earlier phase),
**done** (with commit).

## Baseline (start of this plan)

Commit `a59bc53` on `main`: 315 tests pass; self-test clean. Already in place:
typed recipe slots (fuel, fertiliser, ...), the nitrogen cycle and fertilise
action, open (household) recipes gated on strength and held tools, JOBS with
derived weights and `seed_jobs`/`seed_residents`, per-skill levels with
clusters, metaskills, aptitude, talents and limitations, the `practice`
physical subsystem, and the production-graph and balance self-tests.

---

## Phase 001 -- Workshop tool kits

**Status:** done (see History). Follow-ups recorded in the report: kits for buildings
completed later and non-founding buildings; storage for buildingless trades' tools.

**Goal.** Trade recipes currently wear a single town-wide phantom `Tool` node per
tool kind (`self._tools`, created in `BigvilleWorld.__init__` and `add_recipe`).
Replace that with physical tool items (`ToolItem`) kept at each trade's
building: at founding, each founding building in `E.BUILDINGS` gets one unbroken
tool item of every kind in `E.TRADES[trade]["tools"]` for the trades it
`provides` or staffs. A trade recipe is usable only if an unbroken tool of each
required kind is at the worker's workplace building or held by the worker.
Using it wears that item; a tool at zero condition breaks and must be replaced
(the smith's and woodworker's tool recipes make replacements, which the maker
can carry or place at a building).

**Write scope.** `worlds/bigville_world.py`; tests in a new
`tests/test_phase001_workshop_tools.py`; your report directory.

**Acceptance.**
- A new test shows: a smith at the forge can forge with the forge's hammer; the
  hammer's condition falls with use; once it breaks, forging is refused until a
  new hammer is at the forge or in the smith's hands.
- Open recipes still require the worker's own held tool (unchanged).
- The 315 existing tests still pass, changing numbers only where the brief's
  behaviour requires (listed in the report).

**Out of scope.** Moving tools between buildings by residents' choice (a backend
concern); tool ownership and theft.

---

## Phase 002 -- Recipe inputs from the worker's own stock

**Status:** ready (independent of 001)

**Goal.** Recipes take inputs only from the town store today (`qty()` in
`_resolve_jobs`), while finished goods go to the maker's inventory in the
100-resident town. Make inputs come, in order, from: the worker's own inventory,
then containers at the worker's current cell that they may access
(`_container_accessible`), then the town store. Typed slots (`fuel`, ...) use
the same order per member item. Record on the Job's Need node where each unit
came from (`drawn_from`). Update `_recipe_inputs_available` to the same rule so
published work affordances match what will run.

**Write scope.** `worlds/bigville_world.py`; a new
`tests/test_phase002_own_stock_inputs.py`; your report directory.

**Acceptance.**
- A new test shows: a baker holding 40 flour bakes from her own flour while the
  store's flour is untouched; with none held, she bakes from the store.
- A test shows bought firewood in a resident's inventory is burnt by their own
  cooking.
- Existing tests pass (list any number changes).

**Out of scope.** Choosing to buy (backend); pricing.

---

## Phase 003 -- Seed the 100-resident cast from JOBS

**Status:** ready -- the user approved rebuilding the cast (decision 2026-11-05).
Changing the residents the seeded-town tests are built on is expected; list
every changed number.

**Goal.** Replace the hand-written `ROLE_SPEC` counts in
`worlds/bigville_town100_world.py` with `E.seed_jobs(100)`, mapping each job to
the cast's workplace kinds and keeping the RNG draws for personality and
literacy deterministic.

**Write scope.** `worlds/bigville_town100_world.py`, `worlds/bigville_world.py`
(`populate_town100` only); tests that pin the old cast, with each change listed.

**Acceptance.** `E.check_job_seed(100)` agrees with the cast actually built; the
seeded-town tests pass with any changed counts explained.

---

## Phase 004 -- Located gathering and land-based work

**Status:** ready

**Goal.** Gathering recipes (`gathered_from`: woodlot, orchard, kitchen_garden,
quarry) can be done anywhere today. Add a map site per `gathered_from` kind as a
`ResourceDeposit`-style node with a stock that the recipe draws down and that
regrows each period (data in `world_affordances.py`: per-site regrowth and
capacity; cite or mark APPROX). A gathering recipe is admissible only for an
actor standing at a site of its kind with enough stock.

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`
(self-test checks), `worlds/bigville_world.py`, a new
`tests/test_phase004_located_gathering.py`; your report directory.

**Acceptance.** Tests show gathering refused away from a site, allowed at one,
the site's stock falling and regrowing; self-test clean.

**Out of scope.** Map art for the new sites (note it in the report).

---

## Phase 005 -- Household heating and fuel use

**Status:** ready

**Goal.** Weather already sets `firewood_demand`, and bodies track `chill`.
Each household burns `fuel` (the typed slot, from the household's own store or
the town store) each period in proportion to `firewood_demand`; a household that
cannot is cold, raising its members' `chill`. Put the per-household base burn in
`world_affordances.py` (cite or mark APPROX). Add the heating demand to the
balance model so the fuel flow reflects it.

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`,
`worlds/bigville_world.py`, a new `tests/test_phase005_heating.py`; your report
directory.

**Acceptance.** Tests show fuel burnt per period scaling with weather, and chill
rising without fuel; the balance report's fuel line includes heating.

---

## Phase 006 -- Household work choice in the backends

**Status:** ready (after 005 is useful but not required)

**Goal.** Residents rarely choose open work (splitting firewood, composting),
so night soil piles up and fuel runs out. In `bigville/backends/cheap.py` and
`psi_can.py`, give open-recipe options a score from published need signals
(the world already publishes affordances; add only physical read-offs such as
store quantities of fuel and night soil to the option, not beliefs). Keep the
backend boundary: the world publishes, the backend chooses.

**Write scope.** `bigville/backends/cheap.py`, `bigville/backends/psi_can.py`,
`worlds/bigville_world.py` (option read-offs only), a new
`tests/test_phase006_household_work.py`; your report directory.

**Acceptance.** Tests show a backend choosing `split_firewood` when the fuel read-off
is low and the actor holds an axe, and `make_compost` when night soil is high.

---

## Phase 007 -- Balance scenario from the world

**Status:** ready

**Goal.** `population.BALANCE_SCENARIO` hand-copies what `populate_town100` builds
(beds, plots, animals, water sources). Add a world method that reports the same
scenario shape from a built world, and a test asserting the two agree for the
100-resident town, so they cannot drift.

**Write scope.** `worlds/bigville_world.py`, `domains/population.py` (only if a
value is found to be wrong; list it), a new `tests/test_phase007_balance_scenario.py`.

**Acceptance.** The new test passes; any value corrected is listed.

---

## Phase 008 -- Animal life cycle

**Status:** ready

**Goal.** Animals have `matures` and `lifespan` but do not age, breed, or die
of age. Add per-species gestation and litter size (cite sources, e.g. standard
husbandry references; mark APPROX where not found), ageing each period, breeding
when a mature male and female of a species share an enclosure and are fed, and
death at lifespan. Births add animals with the species' NPC setup.

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`,
`worlds/bigville_world.py`, a new `tests/test_phase008_animal_lifecycle.py`.

**Acceptance.** Tests show ageing, a birth after gestation, and death at
lifespan; self-test checks the new fields.

**Out of scope.** Animal sex ratios in founding herds beyond one pair per
species where the town has two or more (record the choice).

---

## Phase 009 -- Kinship, households, and inheritance

**Status:** ready (decision 2026-11-05: kinship as in the real world -- extended
family -- but a kin term is a social relation, not only a genealogical one: an
uncle does not have to be a biological uncle).

**Goal.** Separate the two layers real kinship has:
1. **Genealogy (world fact):** who bore or fathered whom, and recorded unions.
   Store as `bore`/`fathered` and `union_with` edges between Agent nodes, with
   the period of each. These are physical/recorded facts.
2. **Kin terms (shared frame):** what people call and treat one another. Add to
   `shared_frames.py`:
   - `KIN_TERMS`: the extended-family terms (parent, child, sibling, half-sibling,
     grandparent, grandchild, aunt/uncle, niece/nephew, cousin, spouse, in-laws,
     step-relations), each with its usual genealogical paths (uncle = parent's
     brother, or parent's sister's husband), reciprocal term, and generation.
   - `KIN_ATTRIBUTION`: the ways a term is held WITHOUT the genealogical path --
     adoption, fostering, godparenthood, step-family, and honorific/fictive kin
     (a family friend called "uncle") -- and which obligations each carries.
   - `KIN_OBLIGATIONS`: what a term normally implies (care for children and
     elders, inheritance claim, hospitality), as frames residents may hold.
   A resident's kin terms for others are HELD by that resident (seed them as
   private references from genealogy at founding; later changes belong to the
   backend). The world never decides who counts as someone's uncle.
3. **Founding families (population):** in `population.py`, draw household
   composition for a founding town from real distributions (household size,
   share of extended-family households, age at first union, children per woman,
   share living with grandparents) for a pre-industrial English/European village;
   cite sources (e.g. Laslett / Cambridge Group household studies, Wrigley &
   Schofield) and mark APPROX where needed. Generate genealogy for the seeded
   residents (including dead ancestors where needed to link cousins), then seed
   each resident's held kin terms from it.
4. **Inheritance:** when a resident dies, publish who the genealogical heirs
   are under the data's default custom (in `shared_frames.py`, e.g. partible vs
   primogeniture -- choose one default and make it a data switch) as an
   observation and as the input to the existing `inheritance` deed type. The
   world does not transfer property by itself.

**Write scope.** `domains/shared_frames.py`, `domains/population.py`,
`domains/bigville_entities.py` (self-test checks and a kinship summary in the
report), `worlds/bigville_world.py`, a new `tests/test_phase009_kinship.py`.

**Acceptance.** Tests show: genealogy recorded at founding; an aunt identified
by path; a fictive "uncle" held by a resident with no genealogical path; the
two layers disagreeing without error; heirs published on a death and no
property moved automatically. The self-test reports household-size and
extended-family shares against their sources.

**Out of scope.** Courtship and marriage choice (backend); births during the run
(a later phase).

---

## Phase 010 -- Death, burial, and the graveyard

**Status:** ready

**Goal.** Residents die (starvation, illness) but nothing follows. Add a
graveyard building (founding: True, sprite needed -- regenerate assets), a
`dig_grave`/`bury` open action, and a `coffin` item with a woodworker recipe.
A body left unburied for several periods raises a health risk for its
household (data, APPROX).

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`,
`worlds/bigville_world.py`, assets (regenerated only), a new
`tests/test_phase010_burial.py`.

## Phase 011 -- Fiscal institutions as data

**Status:** ready (decision 2026-11-05: the institutions are already designed;
pull them out of the code into the data).

**Goal.** Taxes, rent, mortgages, tithes, wages, and collection are designed as
graph-rule seeds -- `seeds/bigville_fisc_state.json`, `bigville_clerk_treasurer`,
`bigville_coll_collect`, `bigville_fin_tenure`, `bigville_labour`,
`bigville_econloop`, `bigville_school_fund`, `bigville_fisc_church` (mirrored in
`bigville/seeds/`). The rule engine does not execute seeds (`bigville/runtime.py`
`settle()` is a no-op), and the world loads none of these. Their parameters and
structure live in rule bodies and descriptions. Extract them into data:
- In `shared_frames.py`, `FISCAL_INSTITUTIONS`: one entry per institution
  (council tax, treasury salaries, rent and tenancy, mortgage, tithe and
  donation, church stipend and charity, wages, hired collection, school fund),
  each with who levies and who pays, the base (income, land, rent), the rate in
  basis points and who sets it, the schedule, what collection physically
  requires (proximity, a collector), the consequence of non-payment (arrears,
  eviction, foreclosure, unfunded service), and the seed rule names it came from.
- In `world_affordances.py`, only the physical parts: purses (treasury, church
  funds) as containers of coin, and the payment/collection actions as validated
  transfers. Keep the integer-coin rounding the seeds use
  (`IDiv(amount*bp+5000, 10000)`), as a helper function.
- In `worlds/bigville_world.py`, add the transfer actions (`pay_tax`,
  `pay_rent`, `pay_tithe`, `collect`, ...) following `pay_wage`: each checks
  physical preconditions (coin held, collector co-located for collection) and
  records an obligation/arrears fact. Setting rates, deciding to pay, evicting,
  and graft are agent choices (backend), per the boundary audit: the world
  records and validates, it does not enforce.
Leave the seed JSON files untouched; record in the report which rule maps to
which data entry.

**Write scope.** `domains/shared_frames.py`, `domains/world_affordances.py`,
`domains/bigville_entities.py`, `worlds/bigville_world.py`, a new
`tests/test_phase011_fiscal.py`.

**Acceptance.** Every rule in the eight seeds is mapped to a data entry or listed
as backend-owned in the report; tests show a tax paid by a co-located payer, a
missed rent becoming arrears with no automatic eviction, and the rounding helper
matching the seeds' formula; self-test checks the new tables.

---

## Phase 012 -- Physical and cognitive skill learning

**Status:** ready (decision 2026-11-05: physical skill learning always remains a
world subsystem; cognitive skill learning is optional, because it is harder to
model and because leaving it to the backend stops LLM backends from "cheating"
by having the world grant understanding).

**Goal.** Split skills by kind of learning:
- Tag every skill in `shared_frames.SKILLS` with `"learning": "physical"` or
  `"cognitive"` (the hand and body vs. understanding: e.g. smithing, felling,
  baking physical; writing, reckoning, law, governance, teaching cognitive;
  record the classification and borderline cases such as medicine and trading
  in the report). Do the same for each metaskill.
- The `practice` subsystem keeps consolidating PHYSICAL skills always.
- Add a separate physical-subsystem switch `cognitive_practice`, default OFF.
  When off, completed work still logs practice minutes for cognitive skills,
  but the world does not change their levels; it publishes the practice as an
  observation to the actor (so a backend may learn from it). When on, cognitive
  skills consolidate like physical ones.
- Aptitude's learning-to-learn gain applies only through skills whose learning
  the world is modelling.

**Write scope.** `domains/shared_frames.py`, `domains/bigville_entities.py`,
`worlds/bigville_world.py`, tests that list the subsystem switches (add
`cognitive_practice`), a new `tests/test_phase012_cognitive_learning.py`.

**Acceptance.** Tests show smithing practice raising smithing with the switch
off; writing practice leaving writing unchanged and producing an observation
with the switch off; writing rising with it on.

---

# Programme B: everything in the data, generated seeds and instructions

**Decision 2026-11-05.** All world content -- laws, institutions, roles, procedures, parameters,
and the founding town -- lives in the data, not the code. Ocelot seeds and LLM backend
instructions are GENERATED from that data, so a different scenario runs by swapping the data
pack. The code is mechanics only: it reads the pack, validates actions, and records facts.

Survey findings this programme acts on (2026-11-05):
- The world imports one data set at module level (`from domains import bigville_entities as E`,
  `worlds/bigville_world.py:23`). A scenario can override stocks, actors, buildings, policies,
  laws, charters, map, and subsystem switches, but not items, recipes, skills, crops,
  procedures, offices, or population distributions.
- The 184 seed JSON files are never executed here (`BigvilleGraph.settle()` is a no-op; loading
  records an id only). They are hand-written, and `seeds/` and `bigville/seeds/` have drifted
  (`bigville_action_decide`, `bigville_actor_decision` differ; one file is only in each).
- Content still in code: role sets and household mapping in `populate_town100`
  (`bigville_world.py` ~1996-2068), the founding land/tenure spec, `_require_clerk`, shop and
  stock prices, `add_actor` defaults ("this town is uppity"), care/injury numbers, the
  document-kind literacy gate, the village production autopilot (`_village_work_tick`, roles and
  the grain reserve), `MINUTES_PER_TICK`, Town initial defaults, the engine seed list, the
  townspeople relationship map, `worlds/bigville_town100_world.py` (`ROLE_SPEC`, `_PARAM_SPEC`,
  names, anchors, building sites, the resource-mixture constants), speech chatter in
  `bigville/runtime.py` (~251-270), and the single hardcoded LLM system prompt
  (`bigville/backends/prompts.py:62`).
- `LAWMAKING_PROCEDURES`, `JUSTICE_PROCEDURES`, and `GOVERNANCE_OFFICES` are described in data but
  never consulted by the civic methods.

Order: 013 first (everything else writes into the pack it defines). 014-016 move content.
017-018 generate seeds and instructions. Phases 002-012 above continue afterwards, writing into
the pack.

## Phase 013 -- Data packs

**Status:** blocked -- needs the user's decision on the pack format (see Open decision below).

**Goal.** The world takes its data from a named DATA PACK instead of a module-level import:
`BigvilleWorld(data_pack="bigville")`, or `"data_pack"` in a scenario. The current
`domains/` modules become the `bigville` pack. A pack may extend another pack and override
individual tables. Every `E.` read in the world, backends, reporting, and asset generator goes
through the world's pack. `from domains import bigville_entities as E` keeps working as the
default pack's view. The self-test runs against any pack:
`python3 -m domains.check --pack <name>`.

**Acceptance.** A small test pack (a handful of items, recipes, one building, one trade, one
law) boots a world, runs a recipe, and passes the self-test, with no change to world code. The
existing suite passes unchanged.

**Open decision.** (a) Packs as Python modules (today's form; derived tables such as scraps and
fuel slots stay as code in the pack), with a JSON export for other tools. Smallest change.
(b) Packs as declarative JSON/TOML files, with the derived tables computed by a pack compiler in
code. Truly "swap the files", easy to diff and to generate, and lets an LLM or a non-programmer
author a scenario; a bigger move. Recommendation: (b), done as 013 = compiler + Python-to-file
export of today's data, so the files are produced from the current modules once and then become
the source.

## Phase 014 -- World mechanics parameters into the pack

**Status:** blocked on 013.

**Goal.** Move the numeric and policy constants still in `worlds/bigville_world.py` into the pack:
tick length, Town initial defaults, actor defaults (skill, station, coin, reputation, age),
injury/treatment/care amounts, starvation limit, shop and stock price defaults, the
document-kind literacy gates, the engine seed list, the relationship-kind map. Each gets a
named table; the code reads it.

**Acceptance.** `grep` for each listed constant in world code finds only reads of pack tables;
the suite passes unchanged.

## Phase 015 -- Roles, offices, and procedures from the pack

**Status:** blocked on 013.

**Goal.** Replace hardcoded role literals with pack lookups: household kind by role (in
`HOUSEHOLDS`), registrar and other authorities from `GOVERNANCE_OFFICES`, worker selection in
`_village_work_tick` from JOBS/LABOUR_TASKS, the grain reserve from the `winter_food_reserve`
policy's parameters. Make `LAWMAKING_PROCEDURES` and `JUSTICE_PROCEDURES` scenario-overridable
and record each civic action (proposal, vote, meeting, case, statement) with the procedure stage
it corresponds to -- records only; deciding validity stays with residents (boundary audit).

**Acceptance.** A test pack with renamed offices (e.g. "reeve" for mayor, "notary" for clerk)
runs land registration and a council vote without code changes.

## Phase 016 -- The founding town as pack data

**Status:** blocked on 013; merge with Phase 003 (seeding the cast from JOBS).

**Goal.** Move `bigville_town100_world.py`'s content (role counts -> JOBS seeding, personality
`_PARAM_SPEC`, name pools and anchor names, work anchors, building sites, map layout parameters,
resource-mixture constants with their citations) into the pack's population and scenario data.
`from_town100` becomes "build the pack's founding town".

**Acceptance.** The 100-resident town is built from pack data; changed seeded-town test numbers
are listed (expected, per Phase 003's decision).

## Phase 017 -- Generated Ocelot seeds

**Status:** blocked on 013.

**Goal.** A generator (`tools/generate_seeds.py`, deterministic) writes Ocelot seed JSON from the
pack: concept and frame seeds for laws, policies, charters, procedures, offices, skills and
trades, kin terms, fiscal institutions, recipes as know-how, and shared concepts, in the existing
seed schema (`id`, `version`, `description`, `depends_on`, `nodes`, `edges`, `concepts`,
`rules`). Generated files carry a `generated_from` header (pack name and a content hash) and go
in one canonical directory. Reconcile `seeds/` and `bigville/seeds/` into that one directory
(the four known differences decided in the report). Hand-written cognition seeds (decision,
speech, affect) stay hand-written unless their content is pack data. A check (in the self-test
and a test) fails if generated seeds are stale relative to the pack.

**Acceptance.** Regenerating is byte-identical; editing a law in the pack and regenerating
changes exactly that law's seed; the staleness check catches an unregenerated edit.

## Phase 018 -- Generated LLM instructions

**Status:** blocked on 013.

**Goal.** `PromptBuilder` builds its system instructions from the pack: the world's premise and
name, the action vocabulary (`MAJOR_ACTIONS`, `FREE_ACTIONS`, with descriptions added to the
pack), and the boundary rules (validated proposals, no invented facts). The private part carries
only what that resident HOLDS -- their seeded and learned frames (laws they know, kin terms they
use, skills they have) -- never the pack's world facts, so an LLM resident cannot "cheat" by
reading how the world works. Move the speech chatter and weather phrases from `runtime.py` into
the pack. Record the prompt schema version and the pack hash in each prompt record.

**Acceptance.** Tests show: the system prompt changes when the pack's actions change; a resident
who has not been seeded a law does not see it; a different pack yields a different premise with
no code change.

---

## History

| Phase | Status | Commit | Report |
|---|---|---|---|
| 001 Workshop tool kits | done | (this commit) | docs/phases/phase001/PHASE001_REPORT.md -- supervisor applied the five setup-only test edits the report proposed (tests/test_simple_tools_materials_job.py, tests/test_bigville_world_migrated.py); 323 passed |
