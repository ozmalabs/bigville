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

**Status:** done (see History). Follow-ups from the report: an item need with qty 2 consumes one
item; `_job_input` ignores building shelves and takes any resident's held item; the village policy
still gates `make_gruel`/`grind_flour` on store stock; `fertilise` still draws from the store only.

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

**Status:** done with Phase 016b (see History). The user approved rebuilding the cast
(decision 2026-11-05).

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

**Status:** done (see History). GATHERING_SITES (woodlot, orchard, kitchen_garden, quarry; APPROX)
are placed on free cells of the founding map after everything else, so no existing placement moves;
`add_gathering_site` for bare worlds. Gathering needs the actor on the site with a batch in stock;
the batch is taken when the job opens; sites regrow daily. A `move` option to reach a site was
added to the affordances. Open: the fish, lumber and stone deposits never regrow in `BigvilleWorld`
(their growback rule is only in unloaded seeds); map art for the new sites is not drawn.

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

**Status:** done (see History). Each household burns HEATING.base_burn (0.4, APPROX and unsourced)
x the day's firewood_demand per period, from members' inventories and containers at its home cell
before the town store; ash goes to the store; an unheated household's members gain chill by the
unmet share. Balance fuel line: demand 10.0 -> 29.1 against supply 36.0 (ratio 1.24, not flagged).
The forester load gives one forester at 100 residents (labourer 60 -> 59, ten roles reshuffle;
cast seeds regenerated). Open: a checked source for the burn; nothing reads chill yet.

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

**Status:** done (see History). Open-recipe options carry perceivable read-offs (fuel held, store
fuel only at the store cell, the household's felt heating shortfall, night soil held or at the
store); `psi_can.open_work_need` scores them with HOUSEHOLD_WORK weights (APPROX), and fuel and
night-soil recipes are offered only with a need. Cheap uses it through CANWeightModel. No effect
in the founding town yet: no founder holds an axe or spade and there is no take-tool-to-hand
action (follow-up). Read stamina once 022/024 land.

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

**Status:** done (see History). `BigvilleWorld.balance_scenario()` reports the scenario shape from the
built town and a test asserts it matches BALANCE_SCENARIO. The executor found the world built 61
grain beds against the scenario's 80; the supervisor fixed `_seed_village_crops` to sow the
scenario's beds per crop and raised barley_seed and oats_seed to 27 and 26 (wheat 21/27,
barley 20/27, oats 20/26 -> 27/27/26). `work_minutes_per_resident` (480) has no source (APPROX);
`woodland` is not in the table (model default 1.0).

**Goal.** `population.BALANCE_SCENARIO` hand-copies what `populate_town100` builds
(beds, plots, animals, water sources). Add a world method that reports the same
scenario shape from a built world, and a test asserting the two agree for the
100-resident town, so they cannot drift.

**Write scope.** `worlds/bigville_world.py`, `domains/population.py` (only if a
value is found to be wrong; list it), a new `tests/test_phase007_balance_scenario.py`.

**Acceptance.** The new test passes; any value corrected is listed.

---

## Phase 008 -- Animal life cycle

**Status:** done (see History). Animals age a day per period, die at lifespan (months x 30 days),
conceive when a mature fed female and male of one species share an enclosure, and give birth after
gestation; newborns get NPC backends through the existing game sync. Life-cycle figures are APPROX
(recalled, unchecked). Bees do not breed. Birth sex is a stateless seeded draw (checkpoint-safe).
Founding herd: one female per species, so no founding births. Supervisor fix: pig lifespan 15 ->
180 months.

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

**Status:** done (see History). Decision 2026-11-05: kinship as in the real world (extended
family), but a kin term is a social relation, not only a genealogical one. Supervisor review:
checked the mean household size (Laslett, 4.75) and the share of households with kin (about
10-11%) and recorded the sources in the pack; the other demographic figures stay APPROX. Left for
Phase 016/003: the cast still has one household per resident and every founder is aged 30, so
household draws are checked only by the self-test and founders have about 2.5 children. Open:
heirs are published as a public event (records office only?); no second unions, so no
half-siblings or step-family arise by genealogy.

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

**Status:** done (see History). A death leaves a 60 kg corpse item where the resident died (carried
with pick_up/drop_item). The founding graveyard sits on free grass at (33, 12) with no existing
placement moved (Phase 004 layout digest updated for the added site only). `dig_grave` (own
spade, inside the graveyard) and `bury` (open grave, corpse on graveyard ground, one grave_spoil)
are open recipes; `make_coffin` is a woodworker recipe with no mechanical effect yet. An unburied
corpse of a household gives its members a 0.05 per dawn fever chance after 3 periods (APPROX)
through the existing disease mechanism. Assets regenerated with a graveyard sprite (not viewed).
Open: which corpse bury takes (earliest); corpse decay; place-based risk; backends do not choose
dig or bury yet.

**Goal.** Residents die (starvation, illness) but nothing follows. Add a
graveyard building (founding: True, sprite needed -- regenerate assets), a
`dig_grave`/`bury` open action, and a `coffin` item with a woodworker recipe.
A body left unburied for several periods raises a health risk for its
household (data, APPROX).

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`,
`worlds/bigville_world.py`, assets (regenerated only), a new
`tests/test_phase010_burial.py`.

## Phase 011 -- Fiscal institutions as data

**Status:** done (see History). FISCAL_INSTITUTIONS (9 entries) and FISCAL_BACKEND_OWNED (20 rules) map
all 44 rules of the eight seeds exactly once (tested); purses and the action checks are in
`world/fiscal.json`; `round_bp` matches the seeds' IDiv formula. World: `found_purse`,
`assess_obligation`, `pay_obligation`, `collect`, `deliver_collected` (one payment action for every
institution); coin moves only face to face; a short payer at the payee records arrears and nothing
else. Nine `gen_fiscal_*` seeds generated. Supervisor fix: office clauses use authority conditions,
so the Phase 015 renamed-office fixture stays clean. Open: purses are not opened at founding; the
actions are in FISCAL_ACTIONS, not MAJOR_ACTIONS, so no backend chooses them yet.

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

**Status:** done (see History). Decision 2026-11-05: physical skill learning always remains a
world subsystem; cognitive skill learning is optional, because it is harder to model and because
leaving it to the backend stops LLM backends from "cheating" by having the world grant
understanding. Supervisor review: practice observations carry recipe, turn and day, and
`BigvilleGame._context` publishes each actor's new ones as `observations["practice"]` for one
turn. Open: borderline classifications (writing, storekeeping, trading, policing, medicine
cognitive; midwifery, cooking, service physical) await confirmation; observation nodes are not
pruned in long runs; the publication cursor is not checkpointed.

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

# Run order for the remaining phases (supervisor, 2026-11-05)

013b, 014, 015, 002, 012, 009, 016 (with 003), 019, 017, 018, 004, 005, 006, 007, 008, 010, 011.
Programme B first so later features write into the pack; 012 and 009 before 019, which derives
knowledge from skills and kinship; 017-018 after 019, which they generate from.

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

Order: 013a then 013b first (everything else writes into the pack it defines). 014-016 move content.
019 derives what each resident knows. 017-018 generate seeds and instructions from it. Phases 002-012 above continue afterwards, writing into
the pack.

## Phase 013 -- Data packs

**Decision 2026-11-05: option (b).** Packs are declarative JSON files; the derived tables are
computed by a pack compiler in code. Today's data is exported to files once, and from then on the
files are the source. JSON (not TOML) because the standard library reads and writes it and it is
easy to generate.

Split into two phases.

### Phase 013a -- Pack files, compiler, and export

**Status:** done (see History). Supervisor review: kept authored key order (sorting would change
dict iteration order); removed the dead `_CEREAL` template (CROPS holds the expanded values);
`tools/export_pack.py` builds from legacy modules only with `--bootstrap`; the pre-phase
snapshot equality is a one-time record in `docs/phases/phase013a/`, not a permanent test.

**Goal.**
- Pack layout: `packs/<name>/pack.json` (manifest: `name`, `version`, `description`, `extends`
  (optional parent pack), and the list of table files) plus one JSON file per table, grouped in
  `world/`, `frames/`, `population/` subdirectories (e.g. `packs/bigville/world/items.json`,
  `packs/bigville/frames/laws.json`). One table per file keeps diffs readable.
- `domains/pack.py`: `load_pack(name)` reads the manifest and files, applies `extends` (a child
  table replaces, or with `"merge": true` in the manifest entry, updates its parent's table by key),
  restores types JSON cannot hold (tuples, frozensets, tuple dict keys such as `SKILL_AFFINITY`'s
  pairs) from a per-table schema note, and runs the COMPILER: the derivations currently done at
  module import (scrap items from `leaves_scraps`, their SCARCITY entries, fuel slots added to
  heated recipes, preparation methods and `method_tools`, `seed_return` defaults, the
  POLICIES/LAWS concatenation and their `origin` defaults, and any other import-time loops --
  find them all). Compiling must be idempotent.
- Export: `tools/export_pack.py` writes today's tables to `packs/bigville/` as BASE data -- with
  derived entries removed (e.g. no `*_scraps` items, no added fuel slots), so the files hold what
  an author writes and the compiler adds the rest. Sorted keys, 2-space indent, deterministic.
- `domains/world_affordances.py`, `shared_frames.py`, `population.py` keep every public name, but
  their TABLES now come from `load_pack("bigville")`; their FUNCTIONS (scarcity, effective_skill,
  seed_jobs, ...) stay as code. `bigville_entities` still combines them.

**Write scope.** `domains/` (all four modules plus new `pack.py`), new `packs/bigville/`, new
`tools/export_pack.py`, a new `tests/test_phase013a_packs.py`; your report directory. Do not edit
world, backend, or other test files.

**Acceptance.**
- A test (and a check you run) shows every public table in the combined view is EQUAL to its
  value before this phase (capture the before-values from `git show HEAD:...` into a temporary
  module, or from a JSON snapshot you write in your report directory first).
- `python3 tools/export_pack.py` is byte-identical when rerun; compiling the export reproduces
  the tables exactly.
- A test shows a child pack that `extends` bigville and overrides one table (e.g. adds one item
  and one law) loads with that change and everything else inherited.
- Self-test identical to before (diff its output); full suite passes unchanged.

### Phase 013b -- The world reads a named pack

**Status:** done (see History). Review decisions: an empty BALANCE_SCENARIO means "no founding
balance model" for now; views of one pack share table objects (nothing mutates them); the map's
site layout, place labels, and `from_town100`'s pack argument move to Phase 016.

**Goal.** `BigvilleWorld(data_pack=...)` and `"data_pack"` in a scenario select the pack; every
table the world, backends, reporting, and asset generator read comes from the world's pack
rather than the module-level default. `python3 -m domains.check --pack <name>` runs the self-test
on any pack. A small test pack (a few items and recipes, one building, one trade, one law) boots
a world, runs a recipe, and passes the self-test with no code change.

## Phase 014 -- World mechanics parameters into the pack

**Status:** done (see History). Supervisor review: `BigvilleGame`, `create_game` and the scenario
runner now default `ticks_per_period` to "world" (read from the pack's TIME); `None` still means
"no period passes". `village_eval.TICKS_PER_PERIOD` is preregistered and stays. Known mismatch
kept: `TOWN_INITIAL.temperature` is 15.0 while weather uses a 0-1 scale.

**Goal.** Move the numeric and policy constants still in `worlds/bigville_world.py` into the pack:
tick length, Town initial defaults, actor defaults (skill, station, coin, reputation, age),
injury/treatment/care amounts, starvation limit, shop and stock price defaults, the
document-kind literacy gates, the engine seed list, the relationship-kind map. Each gets a
named table; the code reads it.

**Acceptance.** `grep` for each listed constant in world code finds only reads of pack tables;
the suite passes unchanged.

## Phase 015 -- Roles, offices, and procedures from the pack

**Status:** done (see History). Supervisor review: `_policy_parameters` falls back to the pack's
policy row when a scenario's policy list omits it. Open questions left for later phases:
`seed_roles` still names the old offices; `register_land` does not require a registrar (boundary
audit keeps registry records ungated); backend role-to-task sets in `cheap.py` stay in code.

**Goal.** Replace hardcoded role literals with pack lookups: household kind by role (in
`HOUSEHOLDS`), registrar and other authorities from `GOVERNANCE_OFFICES`, worker selection in
`_village_work_tick` from JOBS/LABOUR_TASKS, the grain reserve from the `winter_food_reserve`
policy's parameters. Make `LAWMAKING_PROCEDURES` and `JUSTICE_PROCEDURES` scenario-overridable
and record each civic action (proposal, vote, meeting, case, statement) with the procedure stage
it corresponds to -- records only; deciding validity stays with residents (boundary audit).

**Acceptance.** A test pack with renamed offices (e.g. "reeve" for mayor, "notary" for clerk)
runs land registration and a council vote without code changes.

## Phase 016 -- The founding town as pack data

**Status:** split by the supervisor. **016a done** (see History): the founding town's content
(roles and counts, class and literacy shares, names, personality ranges, causal-resolution
mixture, map, workplaces, building sites, labels, aliases, deposit kinds) is pack data; the town
built from it is digest-identical to before, except that the legacy `BigvilleTown100World`
adapter now reads lumber regrowth 4.0 from RESOURCE_DEPOSITS (it hard-coded 3.0; accepted).
`from_town100(data_pack=...)`; test_hamlet has no founding town. **016b ready**: merge with
Phase 003, seed the cast from JOBS, give founders real ages and drawn households, redraw the
Phase 009 genealogy from them, and decide `capability`/`skill` in `populate_town100`.
**016b done** (see History): cast counts from `seed_jobs(100)`, ages from FOUNDING_AGE (APPROX),
46 households of adult founders with one home each, genealogy drawn from the households, skill
from each job's trade, capability from FOUNDING_CLASS. The homophily test now compares odds.
Open for the user: 60 of 100 founders are spare labourers (adults only, no children); forester
has zero FTE; banker, landlord, shopkeeper, servant and quarrier have no JOBS entry; seven crafts
share workshop anchors.

**Goal.** (Also from 013b review: the 100-resident map's site layout, workplace anchors, place
labels, and fixed deposit kinds become pack data, and `from_town100`/`run_village` take the
world's pack.) Move `bigville_town100_world.py`'s content (role counts -> JOBS seeding, personality
`_PARAM_SPEC`, name pools and anchor names, work anchors, building sites, map layout parameters,
resource-mixture constants with their citations) into the pack's population and scenario data.
`from_town100` becomes "build the pack's founding town".

**Acceptance.** The 100-resident town is built from pack data; changed seeded-town test numbers
are listed (expected, per Phase 003's decision).

## Phase 017 -- Generated Ocelot seeds

**Status:** done (see History). Canonical directory: `bigville/seeds/` (the Ocelot adapter loads
it; pyproject ships it). 22 generated files (`gen_*` plus `bigville_terrain_movement`, replaced in
place). Reconciled: `bigville_action_decide` (root copy wins), `bigville_dispositions_cast100`
(copied to canonical). Pending: `bigville_actor_decision` stays as is until the other session
commits its 1.3.0 work; then keep the `bigville/seeds/` copy after checking root's `-6.0` term.
Root `seeds/` still has writers (cast and dispositions) and readers; not removed. Per-resident
knowledge seeds are not generated (open).

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

**Status:** done (see History). Prompt schema `bigville/prompt/2`; system text, action
descriptions, rules and response fields from the pack; private part is a bounded selection
(PROMPT_SELECTION caps, APPROX), about 6 KB for a founder instead of 103-160 KB; derived laws and
policies reach `world_frames` (understood: spec without its `knowledge` block; aware-only: name and
gist); chatter and weather phrases in the pack. Open: `PromptBuilder` and speech default to the
bigville pack (the world does not pass its pack); the public part (about 25-32 KB, mostly
observations) is not capped; charters do not reach `world_frames`.

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

**Supervisor note (after 019).** Seeded memories average 119 KB per founder. The turn packet must
carry a bounded, relevant selection (for example the items the current affordances, place, and
neighbours touch, plus understood laws), not every memory, and an aware-only item as its name and
gist. Also route derived law and policy understanding into `world_frames` without restoring the
global law list.

## Phase 019 -- Derived knowledge priors (awareness and understanding)

**Status:** done (see History). Supervisor review: the derived priors are about 295 memories per
founder (29,455 in the town, about 12 MB serialized, 119 KB per resident on average). The LLM
prompt builder (`bigville/backends/prompts.py`) puts every memory into each prompt, so Phase 018
must select memories rather than send them all. Derived law and policy understanding does not
reach `_context`'s `world_frames` yet (it reads only `law_knowledge`/`policy_knowledge` kinds).
History figures and public-spread values are APPROX; citations are from memory and unchecked.

**Decision 2026-11-05.** What a resident knows at the start is EXTRAPOLATED from their job, their
implied life history, and their skill levels -- not from hand-listed role names. Knowledge has
two levels that are tracked separately:
- **aware of**: they know the thing exists and roughly what it is for (the clerk keeps a land
  register; there is a law against theft; bread is made from flour; the miller is Bram).
- **understands**: they can use, follow, explain, or do it (can read and apply the land ordinance;
  knows how to bake; knows the steps of a council vote).
Unaware is the default. Understanding implies awareness.

Today's mechanism is crude: each shared concept and law lists `seed_roles` (35 lists in
`shared_frames.py`), and `bigville/game.py` (~line 280) gives every resident the common recipes
of their role's trades as "can_attempt" memories.

**Goal.**
1. **Knowable things in the pack.** Every knowable entry -- recipes, laws, policies, charters,
   procedures, offices, institutions, shared concepts, kin terms, places, notable residents --
   carries a `knowledge` spec instead of `seed_roles`:
   - `topic` tags (agriculture, smithing, land law, civic procedure, health, ...), linked in the
     pack to skills, clusters, and metaskills;
   - `public`: how widely awareness spreads among residents simply by living in the village
     (e.g. the market and the well: everyone; a charter clause: few);
   - `understanding_requires`: what turns awareness into understanding -- a skill and level, a
     metaskill, literacy for written law, holding an office, an implied-history event
     (apprenticeship, schooling, having served on the council).
2. **Implied history in the population.** For each founding resident, draw a plausible life
   history consistent with their age, job, station, household, and skills: born locally or
   incomer (and years in the village), schooling years, apprenticeship(s) and earlier jobs (which
   leave lower skill levels in those trades), past offices held, and life events (married,
   widowed, bereaved, served the council). Distributions come from historical sources where
   available (cite; mark APPROX). History is authored data about the person, consistent with
   their skills -- skill levels and history are drawn together, not independently.
3. **Derivation.** A pure function `derive_knowledge(person, pack)` returns
   `{item: {"aware": bool, "understands": degree 0..1, "basis": [...reasons]}}` from job ->
   trades -> skills (effective levels, including closeness transfer), metaskills and aptitude,
   literacy, history, household and kin, and public spread. A recipe the person's skill can
   attempt is understood to the degree of their working level; recipes in the same cluster or
   that they buy and use are aware-of; laws are aware-of by public spread and their topics,
   understood if literacy and relevant office/history allow. Every result carries its basis so a
   report can say WHY someone knows something.
4. **Seeding.** At founding the derived priors become the resident's PRIVATE memories (as
   `bigville/game.py` does for recipe priors today), split into awareness and understanding
   kinds. Scenario-authored priors still override. The world itself still holds no beliefs, per
   the boundary audit. After founding, changes in knowledge belong to the backend (and, for
   physical skills, the practice subsystem).
5. **Self-test.** Report, for a seeded town, the share of residents aware of / understanding each
   law and each trade's recipes, and flag implausible results (e.g. a law nobody is aware of, a
   trade whose own holders do not understand its core recipes).

6. **Existence and location.** Knowledge also covers WHAT EXISTS and WHERE IT IS -- buildings,
   workshops, stores and containers, water sources, fields and pasture, deposits and gathering
   sites, the market and its stalls, other residents' homes and workplaces, animals, and the
   kinds of goods to be had. These are tracked as their own items, with levels:
   - **existence** -- unaware / aware it exists (there is a tannery; there is salt to be bought);
   - **location** -- none / roughly where (a district or landmark: "out past the mill") / exactly
     where, with a route they know.
   Derived from implied history and routine: their home and workplace and the routes between,
   where their job sends them (suppliers, customers, fields, the deposits they work), their
   household's and kin's places, years in the village, and public spread (everyone knows where
   the church and the well are). Location knowledge is a held belief and can be wrong or stale --
   a resident who left five years ago remembers the old stall. Seeded location beliefs record the
   position believed and when it was learned. After founding the world only publishes what a
   resident perceives; updating the mental map is the backend's job.

**Acceptance.** Tests show: a baker understands baking and is aware of milling; a former
apprentice smith who now farms understands basic smithing at a lower degree; an illiterate
resident is aware of the theft law but does not understand its written text; an incomer of one
year is unaware of a local custom that a lifelong resident understands; a farm labourer knows
exactly where the fields and the granary are but only roughly where the tannery is; a new incomer
does not know where the quarry is; a resident seeded with an out-of-date stall location keeps
that belief until they perceive otherwise; `seed_roles` is gone from the pack and replaced by
`knowledge` specs; every derived item has a basis.

**Feeds.** Phase 017 generates each resident's knowledge seed from this derivation; Phase 018's
LLM instructions carry only the resident's derived awareness and understanding (an aware-only item
is given as a name and gist, never its full content), and only the places and things they know
exist, at the precision they know them -- never the world's map.

---

# Programme C: time, effort, and consequence

**Decision 2026-11-05 (user).** The town must sustain itself under simple deterministic backends
before Ocelot and LLM backends are plugged in. A social act (a birthday party) only means
something if it costs time and energy that would otherwise go to work, so time and effort must be
real, enforced costs, and a refused action must be visible to the actor that tried it.
Institutions (prices, laws, opening hours, enforcement) stay with residents, per the boundary
audit: these phases add physical costs and physical means, never enforcement.

**Seeds are the specification (user, 2026-11-05).** Many rules this programme needs were
designed earlier as seeds in `seeds/` (blocks R1-R80, written in the project's projected past)
and never ported. Most are in neither `ENGINE_SEEDS` nor `RESIDENT_SEEDS` in the pack, so
nothing loads them, and the Python world implements only part of the seeds it does load. Each
brief cites its seed and ports its rule. Where a brief and its seed differ, the seed wins and
the report says so. Seed parameters are often set nowhere in this repository (the adapters that
set them were not kept), so each brief says which numbers come from the seed and which are new
(APPROX). A feature with no seed at all is marked NEW DESIGN, built behind a switch that
defaults off, so the user can accept or reject it.

Source: the 2026-11-05 grounding audit of `worlds/bigville_world.py` and `bigville/game.py`,
and a survey of `seeds/` (184 files; the sections below cite the ones that matter).
Findings this programme acts on:
- `RECIPE_EXERTION` declares a stamina cost per recipe, but `_can_attempt` discards it
  (`strength_needed, _stamina = ...`) and nothing charges it. Stamina falls only through
  movement `Effort`. Job ticks add a `fatigue` attribute that nothing reads.
- `busy` hides recipe-start options in `_actor_options` only. `start`, `do` and `_can_attempt`
  never check it, so a worker can open overlapping jobs or walk away from a running one.
- Nothing reads `stamina_reserve` as a limit: no action refuses at 0, and it only decides
  whether `rest` is offered. Stamina recovers only through the `rest` action (0.1 per unit);
  there is no overnight recovery.
- The Body seeds (`seeds/bigville_body.json`, `bigville_body_choice.json`) design more than the port
  kept. `bd_exert_cost` also raises hunger by stamina spent x `HUNGER_PER_STAMINA` (the pack
  constant exists and nothing reads it). `bd_train_strength` and `bd_train_stamina` build the
  body with use toward `TRAIN_HEADROOM` (`str_train` and `sta_train` are initialised and never
  updated, and `str_done`/`sta_done` on `Effort` nodes are never read). `bd_meal_feeds` relieves
  hunger by the item's `feeds`; the port's `eat` resets hunger to 0. The seeds say an empty
  reserve means "too tired to work" and that an exhausted walker stops to rest. The engine does
  not execute seeds, so none of this runs.
- The slowdown the user remembers is seeded. `bigville_move_energy` makes the move budget a graded
  step function of energy (3, 2, 1, 0 moves per tick past `e_high` 70, `e_mid` 40, `e_low` 15 of
  100), scales the spend by 1 + hunger, and slows a laden mover; `worlds/bigville_move_world.py`
  keeps those defaults. `bigville_time_sleep` adds the sleep decision, an involuntary collapse
  below `e_collapse`, and non-restorative collapse sleep (`collapse_cap` below `rest_cap`: the
  spiral). `bigville_time_concern` makes a witnessed collapse concerning. None is in the pack's
  seed lists. An earlier search of mine by Python names (`stamina_reserve`, `move_interval`)
  missed all of it.
- Other designed and unported rules, each cited in the phase that ports it: nutrition, freshness
  and graded eating (`bigville_nutrition`, `bigville_foodstuff`, `bigville_diet_affect`);
  loudness as hearing radius and the hear-versus-witness split (`bigville_loud_comm`); taking as
  a world fact (`bigville_theft` `th_take`); the violent act and death by violence
  (`bigville_viol_act`, `bigville_viol_kill`); one health variable with age, illness,
  starvation, exhaustion and violence as routes to death (`bigville_life_health`); lock and key
  authority and dual-key safes (`bigville_container`, `bigville_coin_safe`); custody
  (`bigville_jail`); day, night and lamps (`bigville_daynight`); screening, treatment and
  well-baby care (`bigville_doctor_care`, `bigville_infant_care`); rearing
  (`bigville_life_rearing`). In the port, injury cannot kill and nothing dies of age. Not
  seeded, so NEW DESIGN behind switches: weapons, illness onset, conception and birth,
  and body growth. The world has `birth()` and nothing calls it.
- Drunkenness was designed and never ported. `seeds/bigville_nutrition.json` (block R41) adds a
  drink's `alcohol` to the eater's `intoxication`, multiplies it by `sober_rate` each epoch,
  and raises mood and lowers focus with it. The pack has `ale`, `cider`, `mead` and `beer` as
  drinks with brewing recipes but no alcohol content, and the world has no intoxication state.
  The seed's `sober_rate` and gain parameters are set nowhere in this repository. The same seed
  also designs energy density x variety, protein and deficiency, and taste and spice, none of
  which exists in the world.
- Locks and keys exist but no resident can use them. `lock` and `unlock` take no container
  argument, are not major actions, and have no `_enact_plan` branch. A key is a `holds_key`
  edge, not a held item, so it cannot be given, dropped, or taken. The town store has no lock
  at all.
- `major_action` claims the action slot before `put`, `eat`, `fetch`, `sow`, `water`,
  `harvest`, `build`, `maintain`, `care`, `tend_animals` and `rest` validate, so a refused
  attempt still uses the turn. `move`, `give`, `transfer` and `work` pre-check.
- Malformed proposals raise instead of being refused (`plan["kind"]`, `plan["recipe"]`,
  the species `assert` in `_husbandry_yield`). `BigvilleGame.step()` ticks the world before
  applying responses and catches nothing, so an exception leaves a half-applied turn.
- A refusal is a bool in `game.last_results`, overwritten each step. The world records no
  event or counter, and `ActorContext` carries no last result, so an LLM resident never
  learns that an action failed. (`AGENT_BACKENDS_PLAN.md` section 5 gates on "a failed action
  is observable to the next cognition tick"; `record_action_outcome` reaches Ocelot only.)
- `_record_transaction` is defined but has no caller anywhere, so `report["economy"]
  ["transactions"]` is empty by construction. The preregistered evaluation reports transaction
  counts "even when zero".
- `BigvilleGame.step()` applies responses in actor insertion order against a pre-tick
  decision, so the same residents always win a contested last seed or last loaf.
- `eat` sets hunger to 0 for any food unit; items carry `food: true` and no nutritional value.
- A broadcast utterance (no target) is heard by every resident at any distance; `loudness`
  is stored and never read.
- `take` of held goods always returns False because there is no contested-action model
  (`SIMPLE_VILLAGE_PACKAGE_12.md` records this as a limitation); `move_object` can take any
  accessible unattended object with no resistance. There is no restrain or block action, and
  the town store has no gate (`fetch` checks only location and quantity).
- `LLMBackend` has no concrete provider, `create_game` does not know the `"llm"` kind, and
  bad provider output raises out of `decide`.

Checked and fine (no phase): the world RNG state is checkpointed (`world_persistence.py`
saves and restores `_rng_state`); `complete_request` claims the action slot.

**Order (proposed, for supervisor confirmation).** 020, 021, 025, 026, 037 are independent of
Programme B and of 012. 022 and 023 follow 012 (both touch job completion and practice
logging). 024 follows 021 and 022. 032 follows 022. 027 can run any time; 035 follows 027 and
034. 034 follows 024 and 027. 036 follows 034 and 037. 029 follows 021, 024 and 025; 033 and
038 follow 029 (038 also 037). 030 follows 021 and is better after 029 (keys become takeable);
039 follows 030. 028 can run any time. 031 follows 018 and 021. 040 follows 029, 034 and 038. 041 follows 030 and should land before 011, which needs coin
containers for its treasury and church purses. 042 follows 024 and 028. 043 follows 037;
044 follows 009, 037 and 043; 045 follows 044. Phase 006 (household work
choice) should read the stamina reserve and exhaustion state once 022 and 024 land. Every phase
here changes behaviour the preregistered village evaluation measured, so changed replay digests
and numbers are listed in the report, and the preregistered documents themselves are not edited.

Decisions recorded 2026-11-05 (user): exhaustion slows you until you fall down (024);
contested actions resolve in an interrupt style, where the other party gets a reaction turn
depending on situation, skill, size and ability (029); the town store uses a lock and key (030); drunkenness and nutrition are restored, and the
features set aside as out of scope are added, ported from their seeds (034-039).

## Phase 020 -- Validate before claiming the action slot; refuse malformed proposals

**Status:** done (see History). `major_action` claims the slot per attempt and releases it, with the
turn record, on any refusal (claim-then-release rather than reordering every primitive); a short
fiscal payer keeps the slot because arrears are recorded. `_enact_plan` and the major actions return
False for missing, mistyped or unknown values; wrong-species milking/shearing return 0.0; `sell` and
`sell_labor` removed. `BigvilleGame` contains one actor's failure (`last_errors`). Parity sweep: 4,202
published options (move, work, eat) all enact. Open: public `enact_plan` still raises on a non-dict
plan (next to the other session's hunk); partial responses are not rolled back; `last_errors` is not
in checkpoints (the other session's game_persistence.py).

**Goal.** Make `major_action` consistent: every branch runs its physical checks first and
claims the slot only for an attempt that will be enacted, so a refused attempt costs nothing.
Make `_enact_plan` and the primitives it calls return False for a proposal with a missing or
mistyped parameter (no `KeyError`, `TypeError`, or `AssertionError` for backend input), including
milking or shearing the wrong species. Remove the retired `sell` and `sell_labor` branches from
`major_action` (they claim the slot and always fail). In `BigvilleGame.step()`, contain a failure while applying
one actor's response: that actor's result is False, the others still apply, and the turn completes.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, a new
`tests/test_phase020_validation.py`; your report directory.

**Acceptance.**
- A test per branch listed above shows a refused attempt leaves `actor_turn_state` unchanged
  and the same actor can act in the same turn.
- Tests feed each major action a plan with a missing key, a wrong type, and a nonexistent
  target, and get False with no exception.
- A parity test shows that for a seeded village actor, every option from `actor_affordances`
  can be enacted successfully on a fresh copy of the state (the boundary audit says published
  options can succeed); any option that cannot is listed in the report with its cause.
- Existing tests pass, with changed numbers listed.

**Out of scope.** Reasons for refusal and feedback to the actor (Phase 021).

## Phase 021 -- Refusal records and result feedback

**Status:** done (see History). Every refusal names a code from REFUSAL_REASONS (21 codes, in the
pack); the world logs refusals as `Refusal` nodes per actor (newest 20) with counts by action and
reason, and `last_outcome` on the actor node. `_context` and the prompt carry the actor's own last
outcome (with the reason's meaning); `BigvilleGame.last_rejections` is derived from the world log, so
checkpoints need no change in game_persistence.py (its round-trip test skips until that module is
committed); `report()["refusals"]`. Supervisor decision: an unneeded `rest` keeps logging
`not_needed`.

**Goal.** Make refusal visible. Each refusal point in the major-action primitives reports a short
physical reason code from a fixed table in the pack (for example `slot_used`, `not_in_reach`,
`out_of_stock`, `no_capacity`, `no_tool`, `unskilled`, `out_of_season`, `container_locked`,
`malformed`). Then:
- The world keeps a bounded per-actor log of refused attempts (turn, action, reason) and
  counters by action and reason, in the typed graph so they checkpoint.
- `BigvilleGame` exposes `last_rejections` beside `last_results`, persists it in
  `game_persistence`, and `_context` adds the actor's own last outcome (`applied`, `reason`)
  to its observations, for every backend. The world publishes only the actor's own attempt;
  it never tells another resident.
- `PromptBuilder` includes the last outcome in the turn packet.
- `reporting.py` adds refusal counts by action and reason.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, `bigville/game_persistence.py`,
`bigville/backends/protocol.py`, `bigville/backends/prompts.py`, `bigville/reporting.py`,
pack table for reason codes, a new `tests/test_phase021_refusals.py`.

**Acceptance.** Tests show: a refused fetch at an empty store records `out_of_stock`, appears in
the next context for that actor and not for a neighbour, survives a checkpoint round trip, and
shows in the report; a successful action records no refusal. The prompt for a resident with a
refusal contains it.

**Out of scope.** Backends adapting to refusals (their choice); retry policy (Phase 031).

## Phase 022 -- Recipe stamina is spent

**Status:** done (see History). RECIPE_EXERTION stamina is spent through Effort: evenly over a timed
job's ticks, at completion for an instant `do`; never below 0. All exertion (recipes and moves) is
scaled by 1 + hunger/starve_limit and raises hunger by HUNGER_PER_STAMINA (kept at the seed's 1.0;
the pack note about "a meal relieves ~5" is stale). `fatigue` is now a read-off of stamina spent.
Balance: a per-resident stamina line (0.020 spent vs 9.4 restorable; not flagged, because rest at
0.1/tick is unbounded by sleep). Open: `REST_RECOVERY_PER_UNIT` is in Python, move it to the pack
with Phase 024's EXHAUSTION table.

**Goal.** Charge the stamina cost `RECIPE_EXERTION` already declares. Spend it through the same
`Effort` mechanism movement uses, spread evenly over the ticks of a timed job (an instant `do`
charges at completion), for trade and open recipes alike. Retire the unread `fatigue` attribute
or turn it into a read-off of stamina spent, and record which. Port the hunger cost of
exertion from `bd_exert_cost`: stamina spent (by recipes and by movement) also raises hunger by
`HUNGER_PER_STAMINA` per unit. That constant's note assumes a meal relieves about 5 hunger,
while the port raises hunger 1.0 per period and resets it on eating, so rescale or justify the
constant and record which. Per `mv_deplete` in `bigville_move_energy`, the stamina a movement
or recipe spends is also scaled by 1 + hunger (normalised by `starve_limit`; record the
normalisation), so a hungry worker tires faster. Recovery stays with the `rest`
action; do not retune it. Add a stamina budget to the balance model: stamina spent per
resident per period by the town's labour streams against the rest the town can afford, so a
town whose labour demand exceeds sustainable effort is flagged.

**Write scope.** `worlds/bigville_world.py`, `domains/bigville_entities.py` (balance model and
self-test), `domains/world_affordances.py` (balance only), a new
`tests/test_phase022_recipe_stamina.py`; your report directory.

**Acceptance.** Tests show: forging a plough lowers the smith's reserve by its declared cost,
spread over the job; a light recipe (cost 0) leaves it unchanged; the reserve never goes
below 0. The self-test balance report includes the stamina line for the 100-resident town; if
it flags the town as unsustainable, the report states the numbers and does not retune data
without a decision.

**Out of scope.** What a low reserve prevents or slows (Phase 024).

## Phase 023 -- Timed jobs occupy the worker

**Status:** ready, with a default the user may override (decision 2026-11-05: time is a scarce
resource; a worker cannot do two things at once).

**Goal.** Make occupation a world rule, not only an affordance filter:
- `start` and `do` refuse a worker who is already `busy` with a timed job (eating between work
  pulses stays allowed, as the affordance comments intend).
- Default for leaving: a timed job advances only on ticks when its worker is at the cell where
  it started. Moving away pauses it, and it resumes on return; it is not cancelled and its
  inputs are untouched. Record the final choice in the report.
- Publish the paused state as a read-off on the actor so backends can see it.
Existing behaviour that must hold: a job short of inputs or tools stays busy and completes when
they arrive (Package 7 findings).

**Write scope.** `worlds/bigville_world.py`, `bigville/backends/cheap.py` (read the paused
read-off only), a new `tests/test_phase023_job_occupancy.py`; your report directory.

**Acceptance.** Tests show: a second `start` while busy is refused; a smith who walks to the
square leaves the forge job unfinished and it completes after he returns; eating while busy
still works; the existing job tests pass.

**Out of scope.** Cancelling a job; work that continues unattended (for example an oven load).
If the audit of recipes shows some should run unattended, list them as data for a later phase.

## Phase 024 -- Exhaustion, collapse and sleep

**Status:** ready, after 021 and 022 (decision 2026-11-05: exhaustion makes you slower until you
fall down). Spec: `seeds/bigville_move_energy.json` (v1.1.0), `bigville_time_sleep.json`,
`bigville_time_concern.json`. Seed numbers: `e_high` 70, `e_mid` 40, `e_low` 15, `energy_cost`
8 (per move), 3/2/1/0 moves per tick. Not in the seeds, so new and APPROX: `e_collapse`,
`rest_gain`, `rest_cap`, `collapse_gain`, `collapse_cap`.

**Goal.** Port the seeded exhaustion rules, as pack data in a new `EXHAUSTION` table:
1. **Slowing (`mv_energy_budget`).** The move rate is a graded step function of the reserve.
   The seed thresholds map to reserve fractions 0.70, 0.40 and 0.15, and its 3/2/1/0 moves per
   tick map to the rate ratios 1, 2/3, 1/3 and 0, so the movement interval is x1, x1.5, x3, and
   movement stops below `e_low`. The interval is the one carry load already lengthens
   (`move_interval`, `carry_move_cooldown`); the effects multiply. Thresholds vary by resident
   ("per-character"), drawn from the body capacities. A `slow_on` switch (the seed's falsifier,
   and `energy_cost` 0 for the second control) disables it per scenario.
2. **Spend (`mv_deplete`).** Hunger-modulated cost is Phase 022's. This phase reads the result.
3. **Collapse (`bt_collapse`).** When the reserve falls below `e_collapse` while awake the actor
   collapses, wherever it is. A collapsed actor is asleep and non-restorative: it gains
   `collapse_gain` per tick up to `collapse_cap`, which is below `rest_cap`, then wakes. It
   wakes weaker than a proper sleep leaves it, so a resident who keeps working falls again (the
   seed's spiral). All other major actions are refused meanwhile (reason `collapsed`, Phase 021),
   timed jobs pause (Phase 023), and the actor cannot react (Phase 029).
4. **Sleep (`bt_replenish`, `bt_wake`).** A new `sleep` major action sets the actor asleep.
   Each tick it gains `rest_gain` up to `rest_cap`, then wakes. Other major actions are refused
   while asleep (reason `asleep`), jobs pause, and the actor cannot react. The decision to sleep
   or defer (`bt_decide_sleep`: sleep drive against goal urgency, with a `sleep_enabled`
   ablation) belongs to the backend. The world publishes the facts the seed says the adapter
   writes mechanically: `lateness` (how far into the night, from the clock) and `safe` (indoors,
   at a home or shelter). The simple backend gets a deterministic version in `cheap.py`.
   `rest` stays as the short, awake recovery.
5. **Witnessed collapse (`bt_concern`).** A collapse or sleep is a physical event observed by
   residents with sight of the actor. The concern is the observer's (affect), not the world's.
   Sight does not yet shorten at night (`bigville_daynight`); that is a later phase.
6. **Read-offs.** The step, the speed factor, and the `asleep` and `collapsed` flags are in body
   state and in the options. The simple backend rests or sleeps before collapse, and its reason
   trace shows it.
7. **Extension (not in the seeds).** Timed jobs also advance at the movement factor, so a tired
   smith's job takes longer. Record it, behind the same switch.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (new table),
`domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py`,
`bigville/backends/psi_can.py`, a new `tests/test_phase024_exhaustion.py`.

**Acceptance.** Tests show: the same walk takes x1, x1.5 and x3 the ticks at reserves above 0.70,
between 0.40 and 0.70, and between 0.15 and 0.40, and cannot start below 0.15; a resident
pushed below `e_collapse` collapses, is refused other actions with the reason, wakes without
input at `collapse_cap`, and falls again if it keeps working; `sleep` restores to `rest_cap`
and wakes; an asleep or collapsed actor's job pauses; `lateness` and `safe` are published; with
`slow_on` off there is no slowdown; existing movement and job tests pass.

**Out of scope.** Exhaustion as a route to death (Phase 037 reads the collapsed flag); night
sight and `lateness` from the real sunset (Phase 042; until then `lateness` comes from the hour).

## Phase 025 -- Fair turn order

**Status:** ready

**Goal.** Residents act in insertion order every turn against decisions made before the tick,
so the first residents always win contested stock. Apply responses in a deterministic order
that varies by turn: a permutation derived from the world seed and the turn number, using its
own generator so the world RNG stream is untouched. Decisions are still taken before the tick.

**Write scope.** `bigville/game.py`, a new `tests/test_phase025_turn_order.py`.

**Acceptance.** Tests show: the same seed gives the same order on replay; over a run where two
residents repeatedly want the last unit of a stock, each wins about half the time; the world's
weather and failure stream is unchanged.

**Out of scope.** Simultaneous or negotiated resolution of conflicts.

## Phase 026 -- Observable transfers replace the dead transaction record

**Status:** ready (decision 2026-11-05: the world does not decide what counts as a trade; it
records physical handovers).

**Goal.** Remove `_record_transaction` and the `Transaction` node (no caller exists). Record
each completed physical handover (`give`, `transfer`, `fetch`, `put`) as a `Handover` fact:
turn, from, to (an actor, container or the store), kind, quantity. Bound the history as the
other turn records are. The report's `economy` section counts handovers by good and by kind of
endpoint, with coin shown as a good, and makes no claim that any handover was a sale. Rename
the report key and say so in the README example.

**Write scope.** `worlds/bigville_world.py`, `bigville/reporting.py`, `README.md` (the report
example only), a new `tests/test_phase026_handovers.py`.

**Acceptance.** Tests show a bread-for-coin exchange appears as two unrelated handovers; the
conservation checks the preregistered evaluation uses still pass; the report carries no
`transactions` key.

**Out of scope.** Pairing handovers into trades (a reader's interpretation); the preregistered
documents are not edited.

## Phase 027 -- Food value, freshness and graded eating

**Status:** ready (changes balance numbers; list them). Spec: `seeds/bigville_body.json`
`bd_meal_feeds`; `seeds/bigville_foodstuff.json` `fs_spoil`, `fs_rot`, `fs_prepare`, `fs_eat`,
`fs_nofood`. The seed's note assumes a meal relieves about 5 hunger.

**Goal.**
1. **Meals feed.** `eat` resets hunger to 0 for any food unit. Give each food item a `feeds` value
   in the pack (a loaf is the current unit: one resident's bread for a period; cite sources or
   mark APPROX), and relieve hunger by it, clamped at 0. Reconcile the unit with the world's
   hunger scale (+1.0 per period, starvation at `starve_limit`; the seed assumed about 5 per
   meal) and let the balance model compute food needs in those units. Keep the one-unit-per-meal
   rule and the serving-equipment checks.
2. **Graded eating (`fs_eat`).** Food is not accepted or rejected, it is graded. What a meal
   gives is its `feeds` x freshness (the pile's `condition`), times a `raw_penalty` from the pack
   if the food needs preparation and has none. Spoiled food is still eaten, with low value,
   pleasantness falling with freshness, and illness accruing with (1 - freshness): the harm goes
   through Phase 037's health routes as `illness` (until then, a published `illness_risk`).
   Only an empty stock yields nothing (`fs_nofood`).
3. **Spoiled food stays (`fs_rot`).** `decay` currently sets a stock to 0 at condition 0, so
   rotten food vanishes. Keep it as spoiled stock that can be eaten (item 2), left, or thrown away
   by the existing waste and compost path. Record whether a `discard` action is needed.
4. **Preparation (`fs_prepare`).** Cooking lifts freshness and taste and makes `needs_prep` food
   edible at full value. The existing recipes already prepare food; read their results.
Household rationing (`hq_ration`) is the household's choice, so it stays with residents.

**Write scope.** `domains/world_affordances.py`, `domains/bigville_entities.py`, the pack's
`items.json`, `worlds/bigville_world.py`, `bigville/backends/cheap.py` (read the value only), a
new `tests/test_phase027_food_value.py`.

**Acceptance.** Tests show: a loaf clears a period's hunger, a single apple only part of it, and
two apples as much as a loaf; stale bread relieves less than fresh and carries an illness risk;
raw wheat relieves little; a spoiled pile is not deleted and can be eaten; the self-test checks
every food item has a value; the balance report's food line is in the new units.

**Out of scope.** Variety, protein and taste (Phase 035); alcohol (Phase 034).

## Phase 028 -- Loudness is hearing range; hearing is not witnessing

**Status:** ready. Spec: `seeds/bigville_loud_comm.json` (a resident seed, so only Ocelot minds
run it; the Python world has no counterpart). Seed: loudness IS the Chebyshev hearing radius;
`eff_loudness` is the speaker's chosen loudness clamped to `max_loudness`; content is delivered
iff `eff_loudness >= dist` and the path is not hear-occluded (`lo_deliver_content`); any witness
with sight of the speaker (in range, not sight-occluded) observes that a speech act happened,
whatever the content (`lo_observe_act`, a `CommAct`).

**Goal.** A broadcast reaches every resident at any distance, `loudness` is never read, and a
targeted utterance needs the same cell. Port the seed's physics into the world:
1. The speaker chooses the loudness (a backend choice, already a parameter of `speak`); the world
   clamps it to `max_loudness` from a new pack table.
2. Content is delivered to every resident, or the target, within the Chebyshev distance
   `eff_loudness` and not hear-occluded. Use solid map cells and building footprints as
   occluders; if the map holds no usable occlusion data, record that and use distance alone.
3. A resident with sight of the speaker (a `sight_range` from the table, not sight-occluded)
   gets an observation that a speech act occurred, with the speaker and, if visible, the
   target, and no content. It is published through the existing physical-event machinery.
4. Delivery is recorded per listener (heard, or only witnessed), replacing the single `heard`
   flag. Publish to the speaker only what the speaker could perceive.
5. A `loudness` switch (the seed's falsifier): off gives a flat radius from the table.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py` (the observation only), the pack
(new hearing table), `domains/bigville_entities.py` (self-test), a new
`tests/test_phase028_hearing.py`.

**Acceptance.** Tests show: loudness 5 is heard at 5 cells and not at 6; louder carries
farther; a wall between speaker and listener stops content but not the witnessed act when
there is sight; a targeted utterance at 3 cells is delivered when loudness is at least 3;
with the switch off a flat radius applies; existing conversation tests pass with changes listed.

**Out of scope.** Classroom chatter (`bigville_loud_class`, a cognitive effect); speech clarity
(Phase 036); sight that shortens at night (Phase 042).

## Phase 029 -- Contested actions: reaction turns and taking

**Status:** ready, after 021, 024 and 025 (decision 2026-11-05: contests resolve in an
interrupt style; depending on the situation and on skill, size and ability, the other party
gets a reaction turn). `SIMPLE_VILLAGE_PACKAGE_12.md` records that taking held goods is
unsupported for lack of this mechanism.

**Spec.** `seeds/bigville_theft.json` `th_take`: taking is a world fact, "anyone can physically
take what another holds; the substrate never forbids it". Recognising it as theft, charging,
trial, restitution, fines and collection (`th_recognize_theft` through `th_collect`) are the
residents' institutions and stay with them. The seed takes unconditionally; the contest and
reaction rules below are the grounded refinement the user decided on.

**Goal.** Give residents the physical means to take what another holds, with the holder able
to respond. The world attaches no ownership, crime or law to any of it.
1. **Pack table `CONTEST`.** For each contested action kind: the traits each side contributes
   (strength, size, relevant skill, stamina reserve, health, life stage, exhaustion factor), the
   margin bands for outcomes, the effort rule in item 5 (`base_cost`, `grip`, `technique_weight`, `min_efficiency`, `trivial_below`, `slot_above`,
   `redirect_gap`, `overextend`) and the reaction rules below. Mark numbers APPROX. No randomness: the same state gives the same result. A side's force is
   its effective strength scaled by size and the exhaustion step factor (Phase 024's 1, 2/3, 1/3, 0); skill enters
   separately, as item 5 describes.
2. **Size and skill.** If the pack has no body size, add a `size` trait to the drawn person
   capacities. The skills list has none for physical contest, so add one, `unarmed`
   (kind general, `learning: physical` per Phase 012, with the cluster and closeness entries the
   self-test requires). Its working level comes from `effective_skill` like any other skill.
   Most residents hold a low level; seed more where it plausibly belongs (the policing job) and
   leave authored scenario residents free to hold any level (a retired martial artist). Contests
   log practice minutes, so it trains through the existing practice subsystem.
3. **Reaction eligibility (the world computes it).** The target gets a reaction turn when it is
   alive, awake (not asleep or collapsed, Phase 024), and the actor is within reach, and its reaction score meets the
   attacker's initiative score. The scores come from the situation (was the actor already in
   the target's last observation or did it approach this turn; is the target busy with a timed
   job; is it overloaded) and from ability (reserve, exhaustion factor, health, life stage,
   skill, size). A score short of the attacker's but above a floor gives a late reaction with
   fewer options and a penalty; below the floor, none.
4. **The interrupt.** `BigvilleGame` applies the attacker's `take`. The world returns a
   pending contest with its reaction offer. If a reaction is available the game calls the
   target's backend through a new optional `react(context)` method on the backend protocol.
   The reaction context names who is acting, on what, and by what means, and offers only the
   reaction options: `resist`, `yield` (completes as an ordinary `give`), `evade` (step out of
   reach; if it succeeds the contest is void), `brace`. A reaction spends the target's major
   action for the turn only when it takes real effort (item 5's `slot_above`); a trivial one is
   free, like speech. If the target's action is already used, a costly reaction is a late one. A human
   target makes the step return `waiting` with the reaction prompt. A backend with no `react`
   method does not react (recorded in the report, so a missing adapter is visible rather than
   silently biasing results); the Ocelot and LLM adapters follow separately.
5. **Resolution and effort.** Skill and force both count, in two separate places.
   - *Who prevails.* Each side's score is its force times a technique multiplier from its
     `unarmed` level: `force x (1 + technique_weight x skill)`. A skilled, light resident can
     beat a stronger clumsy one; between equally unskilled residents the stronger wins. A holder
     who does not react still holds with a passive grip (`grip` x its force).
   - *What it costs.* A side pays for the load the opponent puts on it, as a share of its own
     force, discounted by its own technique:
     `base_cost x min(1, load / own force) x efficiency(skill)`. The load is the opponent's
     force actually brought to bear (its passive grip if it is not resisting). Efficiency falls
     from 1.0 at no skill toward `min_efficiency` at full skill. The same load therefore
     costs a skilled defender who redirects it little, and an unskilled one the full share. A
     skilled attacker wastes less effort than a clumsy one.
   - Two thresholds keep trivial resistance free: a cost share below `trivial_below` is
     zero stamina, and below `slot_above` the reacting target's major action stays unspent. A
     six-foot smith swatting off a small child is below both, because the load is small. The
     same child costs a worn-out smith more, because his force has fallen. A hopeless
     attacker pays the full capped share and gets nothing; whether to try is the attacker's
     choice. `yield` brings no load and costs nothing.
   - *Outcomes.* A decisive attacker margin completes the take, with the same conservation and
     capacity checks as `give`. A narrow margin makes the goods fall on the cell (the overload
     drop). Otherwise the holder keeps them. When the holder prevails decisively and its skill
     exceeds the attacker's by at least `redirect_gap`, the outcome is `redirected`: the
     attacker's own force carries it off balance, it pays an extra `overextend` share scaled by
     how hard it committed, and the event is observed. An `injury` field exists in the table at
     zero.
   Everyone within reach observes the result as a physical event; nobody else is told.
6. **First slice.** `take` of held bulk goods, coin and discrete items (including keys,
   Phase 030). `move_object` of an unattended object is unchanged.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, `bigville/backends/protocol.py`
(optional `react`), `bigville/backends/cheap.py` (a deterministic reaction policy),
`bigville/backends/human.py`, the pack (`CONTEST`, body size, the `unarmed` skill in the skills,
clusters and closeness files), `domains/bigville_entities.py` (self-test), a new `tests/test_phase029_contest.py`.

**Acceptance.** Tests show: between equally unskilled residents a strong rested one takes a
stack from a weak one and not the reverse; a light resident with high `unarmed` resists a
heavier unskilled one, prevails, pays little, and the attacker is `redirected` and pays more
(the numbers are chosen so these hold and listed in the report); the same load costs an
unskilled defender the full share; an alert target gets a reaction and an unaware or collapsed one does not; `yield`
equals a `give` with no stamina cost; `evade` out of reach voids the contest; a narrow margin
drops the goods on the ground; a small child grabbing at a strong smith costs the smith no
stamina and no action while costing the child all it has, and the same child costs a
collapsing smith more; two evenly matched residents each spend about the same; a witness in
reach observes it and one out of reach does not; a backend without `react` is recorded as not reacting; replay is
deterministic; with no one in reach or no stock, `take` is refused with a reason.

**Out of scope.** Restraint (Phase 033); strikes and injury (Phase 038, which reuses the rule above); intoxication (Phase 034 supplies it
through effective skill and body state); several people acting together; the Ocelot and LLM `react` adapters.

## Phase 030 -- The town store has a lock and key

**Status:** ready, after 021 and best after 029 (decision 2026-11-05: the town store uses a
lock and key).

**Spec.** `seeds/bigville_container.json` `ck_lock` and `ck_unlock` (a person holding a key
that opens the container locks or unlocks it; without the key a locked container stays shut) and
`seeds/bigville_coin_safe.json` `cs_present`, `cs_open_threshold` (a lock can require
`keys_required` distinct key-holders; a dual-key safe is separation of duties).

**Goal.** Containers already carry `lock_id` and `locked`, and a key opens a lock whose id it
matches, but no resident can use any of it, and the store (a `Store` node with bulk `Stock`
nodes) has no door. Make the store lockable and the machinery usable:
- **Keys are items.** A key is a discrete item (`opens` = a lock id) held like a tool, so it can
  be given, transferred, dropped, picked up, and (with Phase 029) taken. Replace the
  `holds_key` edge, keeping `give_key` as a setup call that creates the item.
- **Lock and unlock are major actions** on a named container or on the store: the actor must be
  at its cell and hold the matching key. They are published as options only when physically
  possible. Remove the argument-less `lock()` and `unlock()` first-match behaviour.
- **Dual keys.** A lock may carry `keys_required` (default 1). It opens once that many distinct
  key-holders, each at the lock's cell, have authorised it (per resident, so one person cannot
  supply two), as `cs_open_threshold` does.
- **The store gets `lock_id`, `locked` and `keys_required` from pack data.** Founding state is unlocked, so the
  default town is unchanged; a scenario or pack may found it locked and name the job that
  holds the key (for example the storekeeper).
- **One check.** A single `_store_open(actor)` guards every resident-initiated path that
  reads or writes the town stock: `fetch` from the store, the store tier of recipe inputs,
  the seed draw in `sow`, `water_crop`, `fertilise`, and deposits. List every such path and its
  treatment in the report. Non-resident processes (decay, period effects, the founding village
  policy) are unaffected. A job short of access stays pending, as a job short of an input does.

**Write scope.** `worlds/bigville_world.py`, the pack (store lock data, key item),
`domains/world_affordances.py`, `domains/bigville_entities.py` (self-test),
`bigville/backends/cheap.py` (use lock and key when it holds the key; no other policy), a new
`tests/test_phase030_store_lock.py`.

**Acceptance.** Tests show: a locked store refuses `fetch` without the key and allows it with
the key; the same for each guarded path; locking and unlocking by a key holder; a key passed
to another resident opens the store for them; an unlocked store and the 100-resident town
behave as before; the existing container-lock tests pass.

**Out of scope.** Copying keys and picking locks (not seeded); who may hold the key (residents
decide); coin kept in a safe (Phase 041); locked doors (Phase 039).

## Phase 031 -- Register and harden the LLM backend

**Status:** blocked on 018 (prompts from the pack) and 021 (last outcome in the turn packet).

**Goal.** Follow `AGENT_BACKENDS_PLAN.md` section 3: register the `"llm"` kind in
`create_game` through a provider factory (no vendor SDK in core), validate provider output
against the response schema, allow one repair attempt carrying only the validation errors,
and return a no-action response after repeated invalid output instead of raising out of
`decide`. (The plan says to return `waiting`; in `BigvilleGame.step()` that stops the whole
turn for every resident, so use an idle response and record the divergence.) Record attempts, repair use and failures in backend state, and count
them in the report beside Phase 021's refusals.

**Write scope.** `bigville/backends/llm.py`, `bigville/api.py`, `bigville/reporting.py`, a new
`tests/test_phase031_llm_backend.py` using a fake provider.

**Acceptance.** Tests show: `create_game(default_backend="llm", backend_factories=...)` builds
LLM residents; invalid JSON then valid JSON succeeds on the repair; repeated invalid output
yields an idle turn and a counted failure; the world never sees an exception.

**Out of scope.** Concrete vendor providers (optional extras per the backends plan).

## Phase 032 -- Use trains the body

**Status:** ready, after 022.

**Goal.** Heavy recipes demand strength above an average body (a plough needs 1.2), and the
data says only "a strong or trained smith" can do them, but nothing trains anyone: `str_train`
and `sta_train` are set to 0.0 and never updated. Port `bd_train_strength`,
`bd_train_stamina` and `bd_effective_stats`: each effort raises trained strength or stamina
toward base x (1 + `TRAIN_HEADROOM`), closing `TRAIN_RATE` of the remaining gap scaled by
intensity (diminishing); effective strength and stamina are (base + trained) x health, and the
reserve is clamped to the effective capacity. Efforts come from movement and, after Phase 022,
from recipes (a recipe with a strength requirement trains strength). Add a `training`
physical-subsystem switch, default on, and list the tests that enumerate switches. Record how
long a labourer takes to reach a recipe's strength requirement.

**Write scope.** `worlds/bigville_world.py`, `domains/bigville_entities.py` (self-test and the
time-to-train line), tests that list subsystem switches, a new `tests/test_phase032_training.py`.

**Acceptance.** Tests show: repeated forging raises a smith's strength with diminishing gains
toward the ceiling; an actor with low health has lower effective strength and stamina; a
resident trained over a season can attempt a recipe that was above them at the start; with the
switch off nothing changes.

**Out of scope.** Detraining; ageing of stats (a later phase).

## Phase 033 -- Restraint

**Status:** ready, after 029.

**Goal.** Residents need a physical way to stop someone leaving, which is what enforcement
means once residents decide to attempt it. Using Phase 029's contest and reaction turn, add
`restrain` (hold a resident in reach), `release`, and `struggle`. While held, the target's
`move` is refused (reason shown), the holder cannot move without releasing, both can still
speak, and each tick of holding or struggling costs each side stamina by Phase 029's effort rule
(holding a child costs a smith nothing; holding a smith costs an unskilled child all it has;
holding a smith costs a skilled practitioner little). The hold ends on release, when the holder
collapses or is no longer in reach, or when the target wins a `struggle` contest. Observers
within reach see it. No arrest, crime or custody concept exists in the world.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, the pack (`CONTEST` rows),
`bigville/backends/cheap.py` (react and struggle only), a new `tests/test_phase033_restraint.py`.

**Acceptance.** Tests show: a stronger holder restrains a weaker target who cannot walk
away; the holder tires and the hold fails on collapse; the target frees itself by winning a
struggle; release lets the target leave; restraining someone out of reach is refused.

**Out of scope.** Doors and confinement (Phase 039); blocking open paths and several people
acting together (not seeded).

## Phase 034 -- Intoxication

**Status:** ready, after 024 and 027 (decision 2026-11-05: drunkenness existed in the design and
is restored). Spec: `seeds/bigville_nutrition.json` (block R41) `nu_eat` (`intoxication` += the
food's `alcohol`), `nu_metabolize` (it is multiplied by `sober_rate` each epoch), `nu_psych`
(mood rises and focus falls, a Mind rule). The seed's rate and gain values are set nowhere, so
the rates here are new and marked APPROX.

**Goal.** Make alcohol a physical fact and give the body an intoxication state.
1. **Data.** Add `alcohol` (strength per serving) to the drink items that have it (`ale`,
   `cider`, `mead`, `beer`; cite historical small-ale, cider and mead strengths or mark APPROX),
   and an `INTOXICATION` pack table: `sober_per_tick`, the band thresholds (sober, tipsy, drunk,
   stupefied), the effect rates below, and `pass_out` and `wake_below`. The self-test checks
   that every item with `alcohol` is a drink and that each brewing recipe's output carries it.
2. **State.** `intoxication` lives on the Body node. Eating a drink (the existing `eat`, with its
   mug and dipper checks) adds the item's alcohol divided by a body-size factor, so a lighter
   body is affected more. It uses the `size` trait Phase 029 adds (whichever phase lands first
   adds it, and the report says which). It wears off each tick by `sober_per_tick` (the seed's
   multiplicative `sober_rate`, rescaled from its epoch to ticks, or linear if the report argues
   for it). It runs only when the `metabolism` subsystem is on.
3. **Physical effects, as world rules.** Coordination and focus fall with intoxication: working
   skill levels drop by a rate x intoxication, physical skills at the coordination rate and
   cognitive skills at the focus rate (Phase 012's `learning` tags choose which). Apply it
   through the existing limitation path in `effective_skill`, extended with a term from current
   body state, so recipe skill gates and quality, practice learning, and contests all see it with
   no new mechanism. Above `stagger_above` movement slows by the same speed factor Phase 024
   uses (the factors multiply). Reaction scores (Phase 029) fall. At `pass_out` the actor
   passes out into Phase 024's asleep state (reason `passed_out`) and wakes unaided once
   intoxication falls below `wake_below`.
4. **No effect on choices.** The world does not change mood, judgement, speech or what a
   resident decides to do. It publishes `intoxication` and its band in body state and in the
   options. The simple backends read it as policy (a drunk resident leans toward social options
   and away from effortful or exacting ones, shown in the reason trace); `PromptBuilder` gives an
   LLM resident its band as felt body state, not as rules; Ocelot reads the body read-off.
5. **Report.** Counts of residents by band per period and alcohol consumed.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (table),
`domains/shared_frames.py` (the body-state term in `effective_skill` only), the pack (items and
new table file), `domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py`,
`bigville/backends/psi_can.py`, `bigville/backends/prompts.py`, `bigville/reporting.py`, a new
`tests/test_phase034_intoxication.py`.

**Acceptance.** Tests show: a mug of ale raises intoxication by its alcohol, more for a lighter
body; it wears off over the table's duration; bread and water leave it unchanged; a smith drunk
past the threshold fails a recipe whose skill gate he passes sober and passes it again once
sober; the same walk takes longer when staggering; at `pass_out` the actor is refused actions
with the reason shown and wakes without input; with `metabolism` off nothing changes; the simple
backend's reason trace shows an intoxicated resident preferring a social option; and, if
Phase 029 is committed, an unskilled drunk loses a contest he wins sober.

**Out of scope.** Hangover, tolerance, dependence, poisoning and speech clarity (Phase 036).
Selling and licensing of drink are not world features: prices, licences and opening hours are
what residents do with these physical facts.

## Phase 035 -- Nutrition: variety, protein and taste

**Status:** ready, after 027 and 034 (decision 2026-11-05: nutrition is restored). Spec:
`seeds/bigville_nutrition.json` `nu_eat`, `nu_metabolize`, `nu_deficiency`, `nu_psych` and
`seeds/bigville_diet_affect.json` `af_meal_mood`. The seeds name the quantities and leave every
rate unset (`protein_decay`, `monotony_decay`, `pleasure_decay`, the protein need, the spice
bonus, the deficiency rates), so the numbers are new and marked APPROX with nutrition sources.

**Goal.**
1. **Food codebook.** Each food in the pack gets `energy` (density, its `feeds` from Phase 027),
   `protein` and `taste`; drinks keep `alcohol` (Phase 034).
2. **Body state.** `monotony` (specific satiety, per food kind), `protein_store`, `deficiency`
   and `meal_pleasure`, beside `intoxication`.
3. **Eating (`nu_eat`).** Energy gained is density x variety, `feeds x (1 - monotony)`, so
   a diet of one food yields less each time. Protein adds to the store. Monotony rises when a
   food repeats. Meal pleasure is the food's taste, plus a bonus if the meal is spiced and a spice
   unit is in stock, which is consumed. The bonus is decoupled from the energy monotony: a
   boring meal, spiced, is still enjoyable.
4. **Per period (`nu_metabolize`, `nu_deficiency`).** Protein, monotony and pleasure decay.
   While the protein store is below the need, deficiency accrues; a sufficient diet recovers it.
5. **Mood (`af_meal_mood`).** Each meal moves the body's `mood` toward its satisfaction,
   `mood += (satisfaction - mood) x 0.4`, so a monotonous diet sinks mood over days and variety
   holds it. The seed leaves `meal_satisfaction` (a sensory-specific-satiety model) to the
   adapter; define it from taste and monotony, cite the research, and record the form.
6. **Mind effects stay with the backend.** `nu_psych` is a Mind rule: mood and focus shaped by
   intoxication, pleasure and deficiency. The world publishes `intoxication`, `deficiency`,
   `meal_pleasure` and `monotony` as read-offs. Simple backends and PromptBuilder use them.
7. The balance model includes protein supply against need, so a town without enough protein is
   flagged.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py`,
`domains/bigville_entities.py` (self-test and balance), the pack (`items.json`, new constants),
`bigville/backends/cheap.py`, `bigville/backends/psi_can.py`, `bigville/backends/prompts.py`,
`bigville/reporting.py`, a new `tests/test_phase035_nutrition.py`.

**Acceptance.** Tests show: eating bread every meal raises monotony and lowers energy per meal, a
varied diet does not; a protein-poor diet accrues deficiency that a protein-rich one recovers;
spice raises pleasure, consumes a unit and rescues a monotonous diet's pleasure; mood sinks over
days on one food and holds on a varied diet; the read-offs appear in the options; the self-test
checks every food has the codebook fields; the balance report flags a protein shortfall.

**Out of scope.** Household rationing (the household's choice); taste preferences and cooking
quality beyond Phase 027.

## Phase 036 -- Alcohol's longer effects

**Status:** ready, after 034 and 037 (decision 2026-11-05: the features set aside in 034 are
added). Seeded: dependence as a coping spiral in `seeds/bigville_affect_decide.json`
`af_choose_action` (grief shifts the choice from work toward withdraw, then drink, then snap) and
`bigville_affect_spiral.json` (`af_outcome_drink`: income down and wellbeing down;
`af_hardship_grief` closes the loop). NEW DESIGN, not seeded: tolerance, withdrawal and craving,
hangover, poisoning, and speech clarity. The unseeded parts sit behind an
`alcohol_aftereffects` switch, default off, so they can be accepted or dropped.

**Goal.**
1. **Dependence (seeded).** The choice to drink as coping is the backend's (it is a Mind rule, and
   the affect seeds are not loaded). The world side already follows from earlier phases: drinking
   uses the action slot (less work, less income), impairs skill (034), and costs stamina and
   health (below). The simple backend gets an optional deterministic coping policy, default
   off, driven by whatever distress read-off exists. The brief lists which read-offs a backend
   needs for it.
2. **Tolerance, withdrawal (NEW).** A body `tolerance` rises with repeated intoxication and
   falls when sober, scaling down the effect of a dose. A body `craving` rises after dependence
   forms and sober time passes, and is relieved by drinking; withdrawal is a published stamina
   and skill penalty while craving is high. All three are pack data.
3. **Hangover (NEW).** When intoxication falls from a high level, a `hangover` penalty to
   stamina recovery and working skill lasts for a table-set number of ticks.
4. **Poisoning (NEW).** Intoxication above `poison_above` is an acute harm each period through
   Phase 037 with cause `intoxication`; it can kill, and `pass_out` (Phase 034) happens first.
5. **Speech clarity (NEW).** Each utterance carries a `clarity` from 0 to 1, set by the speaker's
   intoxication (and, with Phase 028, by distance against loudness). The text is delivered
   unchanged. How a listener treats low clarity is its cognition, and `PromptBuilder` may note
   it. The world never rewrites speech.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (table),
`domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py`,
`bigville/backends/prompts.py`, `bigville/reporting.py`, a new
`tests/test_phase036_alcohol_aftereffects.py`.

**Acceptance.** Tests show, with the switch on: the same dose affects a tolerant resident less
and tolerance fades; a dependent resident gets withdrawal penalties and drinking relieves them;
a hangover follows a heavy night and then ends; a lethal dose harms through the health routes,
the death cause reads `intoxication`, and an ordinary dose does not; an utterance by a drunk has
lower clarity and identical text; with the switch off nothing changes.

**Out of scope.** Selling and licensing of drink (residents' institutions); the affect seeds'
choice rules (the backend's).

## Phase 037 -- One health, several routes to death

**Status:** ready (independent of Programme B). Spec: `seeds/bigville_life_health.json`
`bl_age`, `bl_acute`, `bl_recover`, `bl_death`: health is one variable with two timescales, a
chronic decline with age and acute drops tagged with a cause (illness, injury, starvation,
exhaustion; violence is the fifth, via `bigville_viol_kill`), recoverable by care, rest and
treatment up to `max_health`; death is health at or below 0, and the cause is the last tag. The
seed's `age_rate`, `illness_amount` and `care_amount` are set by the adapter, so the figures are
new and marked APPROX with demographic sources. `bigville_doctor_care` and `bigville_infant_care`
make care and fees residents' business and are not part of this phase.

**Goal.** In the port, health is `health_value` and death comes from separate paths: starvation
kills at a hunger threshold, only disease can reduce health to death, injury cannot kill, and
nothing dies of age. Replace that with the seeded model:
1. A single `harm(actor, amount, cause)` entry point sets the acute drop and the cause tag.
   `injure`, disease, starvation, exhaustion and (later) violence, poisoning and spoiled food use
   it.
2. Chronic decline: a per-life-stage `age_rate` in the pack lowers health each day for elders
   (and infants carry a `fragility` multiplier on acute harm, as `bi_onset` does).
3. Starvation: hunger beyond `starve_limit` becomes acute harm each period at `starve_harm`. The
   default is large enough that the existing timelines hold, and it is softenable.
4. Recovery (`bl_recover`) by care, rest and treatment, capped at `max_health`.
5. Death at health <= 0 records the cause (age, illness, injury, starvation, exhaustion,
   violence, intoxication) in the death record and event, and `death_by_violence`-style tags
   are readable.
6. Exhaustion: the collapsed flag from Phase 024 is the exhaustion route. Define the rule
   (for example repeated collapse without recovery within a window harms), mark it APPROX, and
   record it.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py`,
`domains/bigville_entities.py` (self-test), the pack (health table), `bigville/reporting.py`
(deaths by cause), a new `tests/test_phase037_health_routes.py`.

**Acceptance.** Tests show: a large enough injury kills and records `injury`; an elder past the
table's age decline dies of age after enough days while a young adult does not; starvation
timelines in the existing tests are unchanged; care and rest recover health up to the cap;
every death has a cause; the report counts deaths by cause.

**Out of scope.** Fees and who pays (residents' institutions); screening, treatment and
well-baby effects (Phase 043); births (Phases 044 and 045).

## Phase 038 -- Strikes and injury

**Status:** ready, after 029 and 037 (decision 2026-11-05: strikes and injury are added). Spec:
`seeds/bigville_viol_act.json` (`bv_trigger`, `bv_refrain`, `bv_harm_victim`,
`bv_cost_aggressor`) and `bigville_viol_kill.json`. The act is a `ViolentAct{amount, cost}`: it
lowers the victim's health by `amount`, lowers the aggressor's stamina by `cost`, and is gated on
the aggressor's stamina being at least `attack_cost`. The decision to commit it
(`snap_pressure + w_spite x spite_gain + hunger x desperation_gain` against a threshold) is
the resident's. Evidence, prosecution and sentencing (`bigville_viol_evidence`,
`bigville_viol_prosecute`) are the residents' institutions.

**Goal.** Add a `strike` major action by an actor on a resident within reach, reusing Phase 029's
force, technique, efficiency, reaction turn and `redirected` rules:
1. The harm `amount` and the attacker's `cost` come from the contest, so a strong skilled
   attacker does more harm, an unprepared target takes it in full, a braced or skilled one takes
   less, and a skilled defender can redirect it. A drunk, tired or collapsed attacker is worse
   (Phases 034, 024). The attacker needs at least `attack_cost` stamina; otherwise the strike is
   refused with that reason.
2. A landed strike calls Phase 037's `harm(victim, amount, "violence")`, and a death by it is
   recorded as violence. A redirected strike leaves the attacker off balance and may harm it
   (`redirect_harm`, a table field, default small).
3. Strikes are observed by everyone with sight of the actor, as physical events. Nothing records
   an offence, a crime or a witness's judgement.
4. The decision is the backend's. The simple backend gets the seeded trigger as an optional
   policy, default off, using the personality weights that already exist.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, the pack (`CONTEST` strike rows),
`bigville/backends/cheap.py` (react and the optional trigger), a new `tests/test_phase038_strikes.py`.

**Acceptance.** Tests show: a strike lowers the victim's health and the attacker's stamina; a
strike below `attack_cost` is refused; a skilled defender redirects an unskilled drunk attacker,
who pays more and may be hurt; a lethal strike kills with cause `violence`; a witness in sight
observes it and one out of sight does not; replay is deterministic.

**Out of scope.** Weapons (Phase 040); prosecution and evidence (residents' institutions);
group violence.

## Phase 039 -- Doors and confinement

**Status:** ready, after 030, and a survey first. Spec: `seeds/bigville_jail.json` (custody is an
institution's roll: a charge's `jail_term`, `sentence_remaining`, served a day at a time by the
curfew bell, released at 0, "the FULL term, no early release") and the lock and key rules of
Phase 030. The roll, the sentence and the release are the residents' institution. What the
world supplies is the physical fact that a locked room holds whoever is inside.

**Goal.** The executor first reports how buildings, entrances and interiors are modelled
(footprints, entrance cells, interior cells). If each building has an entrance cell on the map
graph, make a door a property of that cell:
1. A door carries `lock_id`, `locked` and `keys_required`, and uses Phase 030's lock and unlock
   actions.
2. Movement into or out of a locked door cell is refused without the key (reason
   `door_locked`). A resident inside a building whose only door is locked cannot leave.
3. A jail is an ordinary building (a kind in the pack) with a lockable door. Who holds the key and
   who is inside are residents' business.
If interiors are not cells, or entrances are not on the graph, stop and report the options
(for example giving a building a single entrance cell) rather than inventing a model.

**Write scope.** `worlds/bigville_world.py`, the pack (building kinds, door data),
`domains/bigville_entities.py` (self-test), a new `tests/test_phase039_doors.py`.

**Acceptance.** Tests show: a resident inside a locked building cannot leave, unlocking with the
key lets them, a resident outside cannot enter without it, a dual-key door needs two key-holders,
and an unlocked building behaves as before.

**Out of scope.** Jail records, sentences, bell-driven serving and release (the institution);
windows, digging and escape; night sight and lamps (Phase 042).

## Phase 040 -- Weapons

**Status:** ready, after 029, 034 and 038 (decision 2026-11-05: weapons are added). NEW DESIGN:
no seed defines a weapon. The word "armed" in `bigville_theft` `th_take` and elsewhere is a rule's
trigger flag (`*_armed`), not a weapon. The existing tools (`knife`, `axe`, `hammer`, `pick`,
`scythe`) carry a `verb` (cut, chop, strike, mine, reap), so they are already the natural
improvised weapons. Behind a `weapons` switch, default off.

**Goal.**
1. **Data.** An optional `weapon` row on an item: `force` (added to the wielder's force),
   `harm` (multiplier on strike harm), `reach` (1 or 2 cells), `skill`, `wear_per_use`. A
   pack table `IMPROVISED` gives the tools above a weaker row (poor fit, high wear). Add a few
   purpose-made items with woodworker or smith recipes (a cudgel, a quarterstaff, a spear; cite
   or mark APPROX), and a physical skill `arms` (kind general, learning physical, clustered with
   `unarmed`), with the cluster and closeness entries the self-test needs.
2. **Wielding.** A weapon counts only when held in hand (`holds_in_hand`). One in a pack does not.
3. **Effect.** In contests (Phase 029) the wielder's force rises by `force` and the technique
   uses `arms`; in strikes (Phase 038) harm is multiplied by `harm`. Reach lets a wielder
   open a contest from 2 cells, so the target's reaction window is shorter. A weapon wears with
   use and breaks at 0 (the tool-wear path, `bigville_tool_wear`).
4. **Disarming.** A `redirected` outcome (Phase 029) with a large skill gap drops the
   attacker's weapon on the cell, and `take` from a hand is an ordinary contest.
5. Wielded weapons are visible to residents with sight, as held tools already are. New items
   need sprites (regenerate assets). Owning or carrying a weapon is not an offence: law is the
   residents'.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py`,
`domains/shared_frames.py` (skill), `domains/bigville_entities.py` (self-test), the pack (items,
recipes, skills), assets (regenerated only), `bigville/backends/cheap.py` (use a held weapon in
contests and strikes; no other policy), a new `tests/test_phase040_weapons.py`.

**Acceptance.** Tests show: a held cudgel adds force and one in a pack does not; a knife strike
harms more than an unarmed one; the weapon wears and breaks; a skilled unarmed defender
disarms an unskilled attacker; a spear opens a contest from 2 cells; with the switch off nothing
changes; the asset manifest test passes after regeneration.

**Out of scope.** Armour; ranged weapons; trade in weapons (residents).

## Phase 041 -- Physical coin and safes

**Status:** ready, after 030 (decision 2026-11-05: added). Spec:
`seeds/bigville_coin_safe.json` v1.1.0 (block R47): coins are physical and must be stored, in a
safe behind keys. `cs_present`, `cs_open_threshold` (opens at `keys_required` distinct
authorisers, a dual-key safe is separation of duties), `cs_withdraw` and `cs_deposit` (conserved,
capped at what the safe or purse holds), `cs_denied` (a closed safe refuses). Phase 011 builds
treasury and church purses and needs this first.

**Goal.** Coin is a number on the resident (`coin`) and can only move by `give`. Make it
storable:
1. A lockable container may hold `coin` (a safe, a strongbox, a purse), added to a container's
   `holds` list in the pack. `put` and `fetch` move coin between a resident and an accessible
   container, conserved and capped by what is held or stored. A closed or locked container
   refuses (reason `container_locked`); Phase 030's keys, authorisation and `keys_required` apply.
2. The resident's own `coin` stays their purse. Stored coin is not carried: it does not count
   toward their holdings, and it does not move when they do.
3. An optional `coin_weight` (default 0, APPROX) makes a large purse heavier through the existing
   carry model.
4. Reports and the evaluation's conservation checks count stored coin, so the coin total holds.
5. Taking a purse from a resident is Phase 029's contest on `coin`.

**Write scope.** `worlds/bigville_world.py`, the pack (container kinds, `coin_weight`),
`domains/bigville_entities.py` (self-test), `bigville/reporting.py`, a new
`tests/test_phase041_coin_safe.py`.

**Acceptance.** Tests show: coin deposited in an open safe leaves the resident and is withdrawn
whole; a closed safe refuses both; a dual-key safe opens only with two distinct key-holders; coin
is conserved across every move; the existing coin and transfer tests pass.

**Out of scope.** Interest, lending and banks (`bigville_fin_bank`, residents' institutions);
counterfeiting.

## Phase 042 -- Day, night and lamps

**Status:** ready, after 024 and 028 (decision 2026-11-05: added). Spec:
`seeds/bigville_daynight.json` (block R59): daylight length is astronomical, a function of
latitude and day of year; `moon_illum` is the synodic cycle over sim-days; `is_night` compares
the hour with the calculated sunrise and sunset; `light_level` is moonlight x (1 - cloud) at
night and sunlight x (1 - cloud) by day; an outdoor, unsheltered resident at a place with no lit
lamp `sees_dark` when `light_level` is below `see_threshold`; a lit lamp lets you see; the
lamplighter (a council office) lights the lamps at night and douses them by day. The seed notes
a hook: you cannot work a field you cannot see. The world has an hour of day and weather but no
sun, moon, cloud or lamp, and the town square has no lamp fixtures.

**Goal.**
1. **Sky.** The pack gets `latitude` and the moon's synodic period (APPROX, astronomy). Each
   tick computes sunrise, sunset, `is_night`, `moon_illum` and `light_level`. Add a `cloud` value to
   each weather type.
2. **Seeing (`dn_perceive`, `dn_lamp_saves`).** `sees_dark` per resident, as above. A resident
   indoors (inside a building's footprint) does not.
3. **Lamps.** Street lamps are fixtures at map cells, each with `lit`, a fuel reservoir and a burn
   rate, filled from `oil` stock. `light` and `douse` are major actions at the lamp's cell. The
   lamplighter job is a resident role: the world gives the lamp and the actions and lights nothing
   itself. Add lamp oil to the balance model and a lamplighter to the jobs table (a `lamplighter`
   task in `LABOUR_TASKS`).
4. **Consequences.** Sight range for witnessing (Phase 028, and `bigville_time_concern`, which
   notes sight is "short at night") shortens in the dark. Outdoor work (field work, gathering,
   outdoor building) is refused in the dark (reason `too_dark`), the seed's hook.
5. **Lateness.** Phase 024's `lateness` read-off now derives from the real sunset.
6. **Extensions (not in the seed, flagged).** A lit carried light (a `candle`, which exists, or a
   new `lantern`) lets its holder see and burns fuel or wax. Travel in the dark is slowed by a
   table factor (APPROX), default 1.0 to match the seed.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (sky, lamp and light
tables), `domains/bigville_entities.py` (self-test and balance), the pack (fixtures, jobs, items),
assets (regenerated only, for lamps and the lantern), `bigville/backends/cheap.py` (use the
light and douse actions only if the resident is the lamplighter), a new
`tests/test_phase042_daynight.py`.

**Acceptance.** Tests show: daylight is longer in summer than winter at the pack's latitude;
a clear full-moon night is bright enough to see and a new-moon or overcast one is not; an
outdoor resident sees in the dark beside a lit lamp and not beside an unlit one; lamps burn oil and
go out when it runs out; field work is refused in the dark with the reason shown and allowed at
dawn; witnessing range shortens at night; the balance report includes lamp oil.

**Out of scope.** Moon phase effects other than light; astronomy beyond the formulae; bells and
the curfew (`bigville_bells`, residents' institution).

## Phase 043 -- Screening, treatment, well-baby care and illness

**Status:** ready, after 037 (decision 2026-11-05: added). Spec: `seeds/bigville_doctor_care.json`
(`bd_checkup`, `bd_treat`, `bd_onset`, `bd_recover`) and `seeds/bigville_infant_care.json`
(`bi_wellbaby`, `bi_onset`). The effective acute drop is `disease_base + (screened ? 0 :
progression) - (treated ? treat_relief : 0)`; treated patients heal fast and untreated ones at
`natural_care`; an infant takes `disease_base + (well_baby ? 0 : infant_fragility)`. The
seeds' fees, `funds` and affordability gate (a coin test; `public_health` paid by the treasury)
are the residents' institutions and are not world rules here: a doctor decides whether to treat,
and a fee is an ordinary handover. Their parameters are set by the adapter and so are new,
APPROX. NEW DESIGN, behind an `illness` switch, default off: the seeds leave illness onset
(`disease_armed`) to the adapter and the port has none (only `diagnose`).

**Goal.**
1. **Screening, treatment, well-baby.** `checkup` (a preventive visit sets `screened`), `treat`
   (sets `treated`, consumes `medicine`) and `well_baby_visit` (sets `well_baby` for an infant) are
   major actions by a resident with the medical skill, co-located with the patient. They use
   the effective-drop and recovery rules above through Phase 037's `harm` and recovery.
   The flags lapse after a table-set number of periods.
2. **Illness onset (NEW).** A pack table of diseases (seasonal rate, life-stage fragility,
   severity; cite parish-register mortality sources or mark APPROX) raises illness through
   `harm(..., "illness")`, using a dedicated seeded stream so the world RNG is not disturbed.
3. **Read-offs.** `screened`, `treated`, `well_baby` and `illness` are in body state so any
   backend can see them.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (disease and care
tables), `domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py` (a doctor or
midwife offers care when asked; no other policy), a new `tests/test_phase043_care.py`.

**Acceptance.** Tests show: an unscreened patient's illness drops health more than a screened
one's; a treated patient recovers faster; an unvisited infant takes the fragility penalty and a
seen one does not; treatment consumes medicine and needs the doctor in reach; with the switch off
no illness arrives; with it on, onset is deterministic for a seed.

**Out of scope.** Fees, funding and public health programmes (residents' institutions);
epidemic spread between residents (a later phase).

## Phase 044 -- Pregnancy and birth

**Status:** ready, after 009, 037 and 043 (decision 2026-11-05: births are added). NEW DESIGN:
no seed covers conception, pregnancy or birth. `birth()` exists on the world and nothing calls
it. Seeded neighbours: `bigville_life_inheritance` (death passes the estate), `bigville_will`,
`bigville_infant_care` (infant fragility). Behind a `births` switch, default off, so a scenario
can keep a fixed population.

**Goal.**
1. **Fertility.** A pack table gives age-specific marital fecundability for a pre-industrial
   English village (Wrigley and Schofield, Henry's natural-fertility schedules; mark APPROX where
   needed). Each period, each fertile woman in a recorded union (Phase 009's `union_with`)
   may conceive, drawn from a dedicated seeded stream. Courtship and union choice are the
   residents' (Phase 009).
2. **Pregnancy.** A `pregnant` body state with a due day (gestation about 270 days, cited),
   published as a read-off. It raises food need (the life-stage multiplier) and lowers work
   capacity late in term (a table `pregnancy_load`), and carries a delivery risk.
3. **Birth.** At term a birth event calls `birth()`: the newborn is a new resident with a name
   from the pack's name pool, genealogy edges (Phase 009's `bore` and `fathered`), the
   mother's household, and a starting stock of body traits. Maternal and infant mortality are
   table risks through Phase 037's `harm`, lowered by a midwife in reach (`midwifery` skill).
   Stillbirth is a recorded outcome.
4. **The game side.** `BigvilleGame` gains `add_resident`, which builds the newborn's
   character and attaches a dependent backend that proposes nothing until the child reaches
   an age where it acts (Phase 045). Persistence (`game_persistence`) carries the new residents.
5. **Estates and heirs.** The existing heirs observation (Phase 009) now fires for real deaths;
   estate transfer stays the residents' choice, per `bigville_will`.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, `bigville/game_persistence.py`,
`domains/population.py` and the pack (fertility, names, risks), `domains/bigville_entities.py`
(self-test: a long-run town stays within a plausible growth band), a new
`tests/test_phase044_births.py`.

**Acceptance.** Tests show: with the switch off the population is fixed; with it on, a
fertile united woman conceives at the table rate over many seeds, carries to the due day, and
delivers a newborn with genealogy and household; a midwife in reach lowers the mortality;
deterministic for a seed; a checkpoint round trip keeps a pregnancy and a newborn; the self-test
reports the births per woman and the 100-resident town's growth against its source.

**Out of scope.** Contraception, courtship, adoption (a kin-term matter, Phase 009); twins and
multiple births beyond a table rate.

## Phase 045 -- Infants, dependants and coming of age

**Status:** ready, after 044 (decision 2026-11-05: added). Spec: the data `LIFE_STAGES` (age
bands with `work_fraction`, `care` and `food`), `seeds/bigville_infant_care.json` (fragility),
`seeds/bigville_life_rearing.json` `bl_come_of_age` (a resident, Mind-side rule: nurture, the net
of regulated and neglected care, shapes the adult priors and flags `adult`). The prior-shaping
is the backend's. Body growth is NEW DESIGN.

**Goal.**
1. **Dependants act only as they can.** An infant proposes nothing and is refused any major
   action (reason `infant`); a child acts at its `work_fraction`, which scales the force and
   job rate it brings. Their `food` fraction scales hunger relief needed, and `care` is the
   attention they need.
2. **Care is physical presence.** A dependant's `care` need is met by a caregiver in reach and
   awake; a dependant neglected for a table-set number of ticks takes harm through Phase 037
   (cause `neglect`, or starvation if unfed). The world publishes `care_received` over childhood
   as a read-off. Turning it into adult priors is the backend's, as `bl_come_of_age` does.
3. **Growth (NEW).** Base strength and stamina rise along a table curve from the infant value to
   the drawn adult value across the life stages, so a child is weaker and tires sooner. Training
   (Phase 032) builds on the current base.
4. **Coming of age.** Crossing the adult threshold sets the `adult` flag, allows the full
   action set, and publishes an observation. It changes no beliefs.
5. **Where an infant is.** The executor first records how a dependant moves. The default is that an
   infant stays where it is placed and its household's caregivers must be in reach to care for it;
   carrying is a later phase.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, `domains/world_affordances.py`
(growth curve, care table), `domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py`
(a caregiver's dependant policy, default on for parents), a new `tests/test_phase045_dependants.py`.

**Acceptance.** Tests show: an infant is refused actions with the reason; an unattended infant
is harmed after the table's span and an attended one is not; a child's force and job rate scale
with its stage and rise with age; coming of age sets the flag once; a caregiver's policy feeds and
tends its infant in the simple village without help.

**Out of scope.** Schooling and apprenticeship (existing relations, Phase 012); the Mind-side
rearing priors (the backend's); carrying infants.

---

## History

| Phase | Status | Commit | Report |
|---|---|---|---|
| 001 Workshop tool kits | done | (this commit) | docs/phases/phase001/PHASE001_REPORT.md -- supervisor applied the five setup-only test edits the report proposed (tests/test_simple_tools_materials_job.py, tests/test_bigville_world_migrated.py); 323 passed |
| 013a Pack files, compiler, export | done | (this commit) | docs/phases/phase013a/PHASE013A_REPORT.md -- 119 tables in packs/bigville; self-test output identical; 331 passed |
| 013b World reads a named pack | done | (this commit) | docs/phases/phase013b/PHASE013B_REPORT.md -- data_view per-pack module views; domains.check --pack; packs/test_hamlet; 340 passed |
| 014 World mechanics parameters | done | (this commit) | docs/phases/phase014/PHASE014_REPORT.md -- TIME, TOWN_INITIAL, ACTOR_DEFAULTS, CARE, PRICE_DEFAULTS, DOCUMENT_LITERACY, ENGINE_SEEDS, RESIDENT_SEEDS, RELATIONSHIP_KINDS tables; ticks_per_period read from TIME; 351 passed |
| 015 Roles, offices, procedures | done | (this commit) | docs/phases/phase015/PHASE015_REPORT.md -- HOUSEHOLDS roles/groups/fallback, GOVERNANCE_OFFICES registrar, LABOUR_TASKS worker_roles (+bake), winter reserve parameters, scenario `procedures`, civic records carry stage; fixture tests/fixtures/phase015_offices (reeve/notary); 364 passed |
| 002 Recipe inputs from own stock | done | (this commit) | docs/phases/phase002/PHASE002_REPORT.md -- draw order own -> accessible container at cell -> store; drawn_from on Need; affordance uses the same planner; 373 passed |
| 012 Physical and cognitive learning | done | (this commit) | docs/phases/phase012/PHASE012_REPORT.md -- `learning` tag on every skill and metaskill; `cognitive_practice` switch (default off) with a `practice` observation in the actor's context; 378 passed |
| 009 Kinship, households, inheritance | done | (this commit) | docs/phases/phase009/PHASE009_REPORT.md -- genealogy (bore/fathered/union_with) as world fact, held KinTerm references, KIN_TERMS/ATTRIBUTION/OBLIGATIONS, partible default custom, heirs published on death with no transfer; household draw checked against Laslett; 394 passed |
| 016a Founding town as pack data | done | (this commit) | docs/phases/phase016a/PHASE016A_REPORT.md -- 14 founding tables (population/founding_*, world/founding_*); town digest identical except legacy adapter lumber growback 3.0 -> 4.0; 397 passed |
| 016b + 003 Founding cast from JOBS | done | (this commit) | docs/phases/phase016b/PHASE016B_REPORT.md -- seed_jobs(100) cast, drawn ages, 46 households, genealogy from households; households 100 -> 46 in test_bigville_world_migrated; homophily test compares odds; 411 passed |
| 019 Derived knowledge priors | done | (this commit) | docs/phases/phase019/PHASE019_REPORT.md -- domains/knowledge.py derive_knowledge; knowledge specs replace seed_roles; implied history on its own stream (20 founders gain former-trade levels); awareness/understanding/location memories; 434 passed |
| 017 Generated Ocelot seeds | done | (this commit) | docs/phases/phase017/PHASE017_REPORT.md -- domains/generated_seeds.py + tools/generate_seeds.py; 22 files in bigville/seeds with generated_from headers; staleness check in the self-test; 447 passed |
| 018 Generated LLM instructions | done | (this commit) | docs/phases/phase018/PHASE018_REPORT.md -- prompts from the pack, bounded memory selection, derived laws in world_frames, speech lexicon in the pack; prompt schema 1 -> 2 in test_bigville_backends; 464 passed |
| 004 Located gathering | done | (this commit) | docs/phases/phase004/PHASE004_REPORT.md -- GATHERING_SITES placed without moving existing sites; site-gated gathering with daily regrowth; 483 passed |
| 005 Household heating | done | (this commit) | docs/phases/phase005/PHASE005_REPORT.md -- HEATING table, household burn own-store-first, chill when unheated, heating in the balance fuel line; cast gains a forester; 497 passed |
| 006 Household work choice | done | (this commit) | docs/phases/phase006/PHASE006_REPORT.md -- open-recipe read-offs and HOUSEHOLD_WORK scoring in psi_can; no founding change (no held axes or spades); 514 passed |
| 007 Balance scenario from the world | done | (this commit) | docs/phases/phase007/PHASE007_REPORT.md -- balance_scenario() from the built town; grain beds 61 -> 80 to match the scenario (barley/oats seed 27/26); 520 passed |
| 008 Animal life cycle | done | (this commit) | docs/phases/phase008/PHASE008_REPORT.md -- ageing, breeding in shared enclosures when fed, gestation, death at lifespan; pig lifespan 15 -> 180 months; 546 passed |
| 010 Death, burial, graveyard | done | (this commit) | docs/phases/phase010/PHASE010_REPORT.md -- corpse item on death, graveyard, dig_grave/bury/make_coffin, unburied-body household risk; Phase 004 layout digest updated for the graveyard site; 571 passed |
| 011 Fiscal institutions as data | done | (this commit) | docs/phases/phase011/PHASE011_REPORT.md -- 44 seed rules mapped to 9 institutions or the backend; purses, obligations, face-to-face payment and arrears; round_bp; generated seeds 22 -> 31; 609 passed |
| 020 Validate before claiming the slot | done | (this commit) | docs/phases/phase020/PHASE020_REPORT.md -- refused attempts free the slot; malformed proposals return False; step() contains failures; 809 passed |
| 021 Refusal records and feedback | done | (this commit) | docs/phases/phase021/PHASE021_REPORT.md -- REFUSAL_REASONS table, per-actor refusal log and counts, last outcome in context and prompt, report refusals; 828 passed |
| 022 Recipe stamina is spent | done | (this commit) | docs/phases/phase022/PHASE022_REPORT.md -- declared recipe stamina charged via Effort, hunger-scaled exertion raises hunger, fatigue a read-off, balance stamina line; 835 passed |
