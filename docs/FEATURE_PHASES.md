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

## Tracts: how the remaining work is split between two runners

**Decision 2026-11-05 (user).** Two runners work this plan in parallel. Tract A is the runner that
has been committing phases 020 to 030 in order. Tract B is the runner that scoped Programmes C and D
and built Phase 031. The split is by what a phase writes, because 21 of the 29 remaining phases write
`worlds/bigville_world.py` and 22 write `domains/bigville_entities.py`, and two runners cannot both
live in one file. The tract assignments below govern scheduling. The dependencies stated in each
brief still hold, and the "Order" paragraphs in Programmes C and D are superseded by this section.

**Tract A: the world's physics** (owns `worlds/bigville_world.py` and the world tables). In run order:
030 (in flight), 037, 050, 043, 048, 034, 038, 049, 047, 035, 036, 032, 033, 040, 039, 041.
It starts with the two phases that unblock the most work: 037 unblocks six phases and has a chain
of five below it, and 050 and 048 follow from it.

**Tract B: agents, interface and life** (owns `bigville/backends/`, the agent view, the server,
the TUI, providers and the lexicon). In run order: 051, 058, 052, 059, 054, 057, 055, 056, 053, 042,
044, 045, 046. It starts with 051, which unblocks four phases and has a chain of five below it.
042 (day and night) sits here because it feeds fog, sight and the lexicon. 044 to 046 (births,
dependants, ageing of the body) sit here because they need `add_resident`, a dependent backend, the
persona (Phase 058) and the age curve that 045 and 046 share.

**Hand-offs between tracts** (the only places one tract waits for the other):
- B's 044 waits for A's 037 and 043. B's 046 waits for A's 032. By the time B reaches them, A is
  well past them; if not, B takes the next phase in its list.
- Nothing in A waits for B.
- B's 056 reports improvised attempts and accidents, which come from A's 048. It can start without
  them and adds those metrics when 048 lands.
- Phase 052's leak test lists the engine's hidden values (fitness, demand, `rho`). It adds the names
  from 048 and 050 once they exist.
- Phase 051's `VERB_ALIASES` and `INTENSITY_WORDS` name things A's Phase 050 defines (`VERBS`,
  `intensity`). Whichever of 050 and 051 lands second adds the test that every alias resolves.
- A's 048 and 047 add one key each (`tool`, `joint`) to the proposal shape in
  `bigville/backends/protocol.py`, a B file. Additive only.

**Shared files**, edited by both tracts, so keep each edit small and additive, re-read the file
before editing it, and commit promptly: `domains/bigville_entities.py` (22 remaining phases),
`domains/world_affordances.py` (18), `bigville/backends/cheap.py` (15), `bigville/game.py` (13),
`bigville/reporting.py` (11), and the `pack.json` manifests. In particular, B's Phases 058 and 059
restructure `cheap.py` (`_update_goals`, `_time_band`, and a would-be-choice method). Until 059 is
committed, A adds new behaviour to `cheap.py` as separate methods and hooks and does not edit those
three. After 059, A rebases and reads the routine, not the hour bands.

**Working practice.**
1. **One tree per tract.** Both runners currently share one checkout, so the index mixes their work
   and each runner's test run sees the other's half-finished edits. Give each tract its own git
   worktree and branch (`git worktree add ../bigville-tract-b -b tract-b`), run the full suite in
   its own tree, and merge into `main` by rebase at phase boundaries. Commit or park any unrelated
   uncommitted work first, so a worktree starts clean.
2. **One phase, one commit, made as soon as the phase is done** (user, 2026-11-05: commit after
   every phase). The supervising session of each tract reviews the diff and the report, then
   commits; the executor still never does. Stage by explicit pathspec, never `git add -A` or
   `git commit -a`. Check `git diff --cached --name-only` is empty before staging and equals the
   phase's files before committing, since the index is shared. For a shared file that carries
   someone else's hunks (including this plan), stage a prepared snapshot of just your change
   (`git hash-object -w`, then `git update-index --cacheinfo`) or use `git add -p`. Plan edits that
   are not a phase's own status and History row get their own commit, made first, so every snapshot
   is self-consistent. The commit message is `Phase NNN: ...` in the style of the log.
3. **This file.** A tract edits only its own phases' briefs, statuses and History rows, re-reading
   before it writes. A change to the other tract's brief is a note to that tract, not an edit.
4. **Sync points,** when both tracts pause to merge: (1) 037 and 051 committed, (2) 050 and 059,
   (3) 043 and 054.

**Work that belongs to neither tract.** A third stream of uncommitted work is in the tree: the
Ocelot integration and persistence (`bigville/game_persistence.py`, `bigville/world_persistence.py`,
`bigville/mixed_ocelot_scenario.py`, the `runtime.py` and `backends/ocelot.py` edits, the
`resident_plan_from_context` method in `worlds/bigville_world.py`, the `record_action_outcome` lines
in `bigville/game.py`, their tests and two docs). Its owner commits it or parks it on a branch before
worktrees are made. Until then, staging `worlds/bigville_world.py` or `bigville/game.py` as a whole
would sweep its hunks into a phase commit, which is why rule 2 requires `git add -p` for those two.

| Tract | Phases |
|---|---|
| A, world physics | 030, 037, 050, 043, 048, 034, 038, 049, 047, 035, 036, 032, 033, 040, 039, 041, and 063 (visible condition) |
| B, agents, interface, life | 051, 058, 052, 059, 054, 057, 055, then 066, 056, 053, 042, 060, 061, 062, 064, 065, 067, 044, 045, 046 (068 parked) |
| Unassigned | 069, 070, 071 (Programme F, the body as a unit; supervisor assigns them, 069 may be split between tracts) |
| Neither | Ocelot integration and persistence (uncommitted) |
| Superseded | 003 (done with 016b), 013 and 016 (split into 013a and 013b, 016a and 016b) |

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

**Stupidity is valid (user, 2026-11-05).** The world does not stop inhabitants from doing dumb
things. It provides consequences. A refusal means the act cannot happen at all: nothing to act
with or on, out of reach, the actor unconscious or dead, or a malformed proposal. A lock refuses only the
ordinary opening: forcing it is an attempt, resolved by the core of Phase 050, so a locked door
is a barrier with a strength, not a wall.
Everything else, however unwise, is permitted and charged for: time, effort, hunger, wear and
breakage, wasted inputs, bad results, injury. The consequences must be observable to the actor
(progress, strain, damage, outcome), never announced beforehand, and a resident who has started
something doomed needs a way to stop of their own accord. Whether the idea was dumb is the
resident's lesson to draw, not the world's ruling. Phases 048 and 049 apply this to tools and to
the gates that already exist; the briefs below were amended to follow it.

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
  (`bigville_life_rearing`). In the port, injury cannot kill and nothing dies of age. Striking
  with a held tool is seeded (`bigville_tools` `tl_strike`). Not seeded, so NEW DESIGN behind
  switches: throwing, illness onset, conception and birth, body growth, detraining and ageing of
  stats, and joint actions beyond the dual-key lock. The world has `birth()` and nothing calls it.
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
034. 034 follows 024 and 027. 036 follows 034 and 037. 050 follows 037 and goes first of the rest. 029 follows 021, 024, 025 and 050; 033 and
038 follow 029 (038 also 037). 030 follows 021 and is better after 029 (keys become takeable);
039 follows 030. 028 can run any time. 031 follows 018 and 021. 040 follows 029, 034, 038 and 048. 048 follows 037 and 050; 049 follows 048 and 050. 041 follows 030 and should land before 011, which needs coin
containers for its treasury and church purses. 042 follows 024 and 028. 043 follows 037;
044 follows 009, 037 and 043; 045 follows 044. 046 follows 032 and 045. 047 follows 020, 025 and 029, and uses 030's dual-key
lock as its seeded case. Phase 006 (household work
choice) should read the stamina reserve and exhaustion state once 022 and 024 land. Every phase
here changes behaviour the preregistered village evaluation measured, so changed replay digests
and numbers are listed in the report, and the preregistered documents themselves are not edited.

Decisions recorded 2026-11-05 (user): exhaustion slows you until you fall down (024);
contested actions resolve in an interrupt style, where the other party gets a reaction turn
depending on situation, skill, size and ability (029); the town store uses a lock and key (030); drunkenness and nutrition are restored, and the
features set aside as out of scope are added, ported from their seeds (034-039); stupidity is valid, so the world refuses only what cannot
happen and charges for everything else (048, 049).

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

**Status:** done (see History). `start`/`do` refuse a busy worker (reason `busy`); eating and moving
stay allowed. Default kept: a timed job advances, completes and spends stamina only while its worker
stands on the cell where it started; leaving pauses it (no cancel, inputs untouched). Read-offs:
`job_paused`, `job_start_cell`, and a `move` option back marked `resumes_job` (the simple backend
gives it +40). A job waiting for inputs keeps its worker busy, as before. Unattended-work candidates
(brewing, malting, tanning, charcoal, cheese, pickling, compost, paper; possibly baking, smelting)
are listed in the report for a later data phase.

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

**Status:** done (see History). EXHAUSTION table (seeded thresholds 0.70/0.40/0.15, hop budget
3/2/1/0; APPROX e_collapse 0.05, rest_gain 0.03, collapse_gain 0.02, collapse_cap 0.25, night
21:00-05:00; rest_recovery_per_unit moved here). Walks are x1, x1.5, x3, then refused (`too_tired`);
timed jobs advance at the same speed (stopped below e_low). Below e_collapse a resident collapses,
is refused actions (`collapsed`), wakes at collapse_cap and can fall again. `sleep` restores to
rest_cap (`asleep` refusals); sleep and collapse pause jobs. `lateness` and `safe` published; the
simple backend sleeps at night or before collapse on a safe spot. `slow_on` switch (constructor or
scenario). Open: witnesses are same-cell only and no concern is formed; every founder has stamina
capacity 1.0, so per-resident thresholds do not vary yet.

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

**Status:** done (see History). `BigvilleGame.step()` applies responses in `turn_order(actors, turn)`:
the sorted actor names shuffled by `random.Random(f"{map_seed}:{turn}")`, built per call, so replay
is exact, `world._rng` is untouched and checkpoints store nothing new. `last_order` records the
applied order. Two residents contesting one loaf for 120 turns each win between 35% and 65%.

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

**Status:** done. Handover facts (`_record_handover`, registry `_handovers` with totals, capped at `HANDOVER_LOG_LIMIT` = 1000) replace `Transaction`/`_record_transaction`; handover kinds live in `packs/*/world/handovers.json`. Reporting exposes `economy.handovers` and the series `handovers`/`coin_handed_over`. A `_transactions` compatibility count of fiscal handovers is kept for `village_eval.py`. README.md is owned by the parallel session and was not edited; replacement report-example line: `print(report["economy"]["handovers"])  # physical handovers by good, kind and endpoint; not a record of sales`. See docs/phases/phase026/PHASE026_REPORT.md.

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

**Status:** done. Food items carry `feeds` in loaf-equivalents (bread 1.0, apple 0.5, APPROX); a meal relieves `feeds` x freshness (x `raw_penalty` 0.3 for unprepared `needs_prep` food) and publishes `illness_risk` for Phase 037. Rotten stock is kept, not deleted; freshness travels with food. Balance food line is in loaves (supply 812 -> 358 against demand 100). The cheap backend ignores zero-value (spoiled) meals. Open: grains as food, apple value by energy, a `discard` action. See docs/phases/phase027/PHASE027_REPORT.md.

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

**Status:** done. Speech content reaches listeners within Chebyshev distance `eff_loudness` (the speaker's loudness clamped to `max_loudness` from the new `HEARING` table) on an unoccluded line; residents with sight of the speaker get a content-free `spoke` event. Delivery is recorded per listener (`deliveries`; `heard` kept as a derived summary). `loudness` switch off gives a flat radius. Map walls and trees occlude both sound and sight (no sound-only tile exists); buildings do not occlude. See docs/phases/phase028/PHASE028_REPORT.md.

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

**Status:** done. `take` is a deterministic physical contest on one cell: force from strength, size (new `SIZE` draw), life stage and the exhaustion step, with a `fighting` technique multiplier; outcomes completed, dropped, held or redirected; stamina costs with the trivial and slot thresholds from the new `CONTEST` table (all APPROX). The holder reacts (resist, brace, yield, evade) through an optional backend `react`; a human holder makes `step()` return `waiting`; a backend without `react` is logged as `no_react_method`. Completed takes and yields are `take`/`yield` handovers. Open: test_hamlet's placeholder `constable` trade; reach is the same cell; the suspended turn and pending contest are not checkpointed. See docs/phases/phase029/PHASE029_REPORT.md.

**Spec.** `seeds/bigville_theft.json` `th_take`: taking is a world fact, "anyone can physically
take what another holds; the substrate never forbids it". Recognising it as theft, charging,
trial, restitution, fines and collection (`th_recognize_theft` through `th_collect`) are the
residents' institutions and stay with them. The seed takes unconditionally; the contest and
reaction rules below are the grounded refinement the user decided on.

**Goal.** Give residents the physical means to take what another holds, with the holder able
to respond. The world attaches no ownership, crime or law to any of it. A contest is Phase 050's
resolution core with the opposing side as the demand. The terms every attempt shares (`base_cost`,
`technique_weight`, `min_efficiency`, `trivial_below`, `slot_above`, force and technique) live in
the core's `RESOLUTION` table, and `CONTEST` keeps only `grip`, `redirect_gap`, `overextend` and
the reaction rules. A side chooses its intensity (Phase 050, default normal), which multiplies the
force it applies: `resist` is at the chosen level, `brace` is a firm hold at low cost, and `yield`
is none.
1. **Pack table `CONTEST`.** For each contested action kind: the traits each side contributes
   (strength, size, relevant skill, stamina reserve, health, life stage, exhaustion factor), the
   margin bands for outcomes, the effort rule in item 5 (`base_cost`, `grip`, `technique_weight`, `min_efficiency`, `trivial_below`, `slot_above`,
   `redirect_gap`, `overextend`) and the reaction rules below. Mark numbers APPROX. No randomness: the same state gives the same result. A side's force is
   its effective strength scaled by size and the exhaustion step factor (Phase 024's 1, 2/3, 1/3, 0); skill enters
   separately, as item 5 describes.
2. **Size and skill.** If the pack has no body size, add a `size` trait to the drawn person
   capacities. The skills list has none for physical contest, so add one, `fighting` (hitting,
   grappling, throwing, with or without something in the hand; kind general, `learning: physical` per Phase 012, with the cluster and closeness entries the
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
     `fighting` level: `force x (1 + technique_weight x skill)`. A skilled, light resident can
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
`bigville/backends/human.py`, the pack (`CONTEST`, body size, the `fighting` skill in the skills,
clusters and closeness files), `domains/bigville_entities.py` (self-test), a new `tests/test_phase029_contest.py`.

**Acceptance.** Tests show: between equally unskilled residents a strong rested one takes a
stack from a weak one and not the reverse; a light resident with high `fighting` resists a
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
through effective skill and body state); several people acting together (Phase 047); the Ocelot and LLM `react` adapters.

## Phase 030 -- The town store has a lock and key

**Status:** done. Keys are `ToolItem`s (kind `key`, `opens` = lock id) that can be given, dropped, picked up and taken; `holds_key` is gone and `give_key` is a setup call that makes the item. `lock`/`unlock` are major actions on a named container or `"store"`, published only to a keyholder at the lock's cell; `keys_required` above 1 needs that many distinct keyholders' turns. The store has a `Lock` node founded from `STORE_LOCK` (unlocked), and `_store_open(actor)` guards every resident path to town stock (listed in the report); a job short of access waits. The 100-resident digest is byte-identical. Open: the non-executed container seed records still describe `holds_key`; named rather than counted dual keyholders. See docs/phases/phase030/PHASE030_REPORT.md.

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

**Out of scope.** Copying keys; picking and forcing locks (Phase 050: a lock has a strength, and forcing it is an attempt); who may hold the key (residents
decide); coin kept in a safe (Phase 041); locked doors (Phase 039).

## Phase 031 -- Register and harden the LLM backend

**Status:** done (see History). Stage 1 of the LLM build in Programme D; 054 (prompt packet
and schema from the agent view), 055 (operations) and 056 (evaluation) follow it. Decided
2026-11-05: on a provider error, or an invalid reply after the repair, the resident falls back to
the simple backend (Phase 059) in place of an idle turn, so it keeps its routine; a model's
`waiting: true` stops being accepted, since it would stall every resident; retry and backoff
belong to Phase 055.

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
LLM residents (a live OpenCode Go call is an opt-in test, never in the default suite); invalid JSON then valid JSON succeeds on the repair; repeated invalid output
yields an idle turn and a counted failure; the world never sees an exception.

**Out of scope.** Concrete vendor providers (optional extras per the backends plan).

## Phase 032 -- Use trains the body

**Status:** done. Efforts train the stat they use by the seed rule, intensity x TRAIN_RATE x (base x TRAIN_HEADROOM - trained); effective strength and stamina are (base + trained) x health, the reserve is clamped to effective stamina, and the contest force (029) reads the same helper. Movement trains stamina; recipes train stamina and, with a strength requirement, strength. `training` switch, default on. Time-to-train: a base-1.0 labourer reaches the plough's 1.2 in 15 efforts (60 h of plough batches; 39 knife batches, 58.5 h). The strength gate now applies to every recipe with a requirement, not only open ones, so base-1.0 smiths and joiners cannot start the plough, wagon, scythe or cart until trained (open question for the user). See docs/phases/phase032/PHASE032_REPORT.md.

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

**Out of scope.** Detraining and ageing of stats (Phase 046).

## Phase 033 -- Restraint

**Status:** done. `restrain` (hold a resident on your cell), `release` and `struggle` are major actions resolved by the Phase 029 contest rule through the Phase 038 contest plumbing: the target may react (a human target makes the step wait); a decisive margin holds, otherwise the grab slips. A held resident cannot walk and neither can its holder; both awake sides pay stamina each tick by the take's effort rule (a smith holding a child pays nothing, a child holding a smith the full share); the hold ends on release, a won struggle, the holder sleeping, collapsing or dying, or the two parting. Held residents are offered `struggle` and no `move`, holders `release`. No new figures (CONTEST's take numbers). Restraint is not published as an option, so the simple village never restrains (0 deaths in 192 turns); the cheap backend struggles when held and never releases. The Phase 054 packet snapshot is regenerated for the three new actions. Group restraint is out of scope. See docs/phases/phase033/PHASE033_REPORT.md.

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

**Out of scope.** Doors and confinement (Phase 039); blocking open paths (not seeded); several
people acting together (Phase 047).

## Phase 034 -- Intoxication

**Status:** done. A drink adds its grams of alcohol (`alcohol` on ale 18 g, cider 20, mead 45, beer 22) to a body `intoxication` level by Widmark's formula, scaled by body size, and the level falls linearly per tick (`INTOXICATION` table; sources and APPROX figures in its `_doc`). It lowers working skill through `effective_skill` (coordination for physical skills, focus for cognitive), so recipe gates, contests and attempts see it; above 0.35 walking slows by half; at 0.8 the resident passes out (`passed_out`, no stamina regained) and wakes below 0.35. `body_state`, the observations and the lexicon publish the level and band; the simple backend leans social and away from effortful work when drunk; `SimulationReporter.intoxication()`. Founding town holds no drink, so the default village is unchanged until someone brews. Open: beer is not in `DRINK_FOODS`; practice learning ignores intoxication; no mood effect. See docs/phases/phase034/PHASE034_REPORT.md.

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

**Status:** done. Every food carries `protein` (grams per unit, APPROX from typical composition tables) and `taste` (0 to 1); the body keeps a protein store, a deficiency (rises while the store is below `protein_need` 40 g a period, WHO/FAO/UNU 2007 x a 60 kg adult; a read-off only), a specific satiety per food kind (`Satiety` nodes), the last meal's pleasure and a mood that moves toward each meal's satisfaction. A spiced meal (`eat(..., spiced=True)`, consumes a held pepper, cinnamon or ginger) adds `spice_bonus` to pleasure. The energy effect of satiety (feeds x freshness x (1 - satiety)) is behind a `monotony` switch, default off: the founding village runs close to the starvation limit, and an eat floor in the simple backend that would have absorbed the residue starved 19 residents in 384 turns. With the switch off the village is unchanged (0 deaths in 384 turns). Open: no backend chooses spice; nutrition read-offs are not in game.py's observations; two satisfaction models (population and world). See docs/phases/phase035/PHASE035_REPORT.md.

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

**Status:** done, behind `physical_subsystems.alcohol_aftereffects` (default off). With it on: each drink adds tolerance (`tolerance_per_drink` 0.1), which lowers later doses and fades while sober; dependence forms at tolerance 0.5 and stays; a dependent resident's craving rises while sober and a drink relieves it; withdrawal (craving 0.3 or more) lowers working skill and stamina capacity; a night that peaks at 0.6 leaves a 96-tick hangover (less skill, half the sleep regain); intoxication above 0.7 is acute harm each tick with cause `intoxication`, after the pass-out check; speech carries a `clarity` figure (1 - the speaker's intoxication, less up to half at the hearing radius's edge), with the text unchanged; `SimplePolicy.coping_drink` (off) favours a drink when mood or craving is in distress. All new figures APPROX. With the switch off, and no drink in the founding town, the village is unchanged (0 deaths in 192 turns). Open: craving never falls without a drink and dependence never clears, as built. See docs/phases/phase036/PHASE036_REPORT.md.

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

**Status:** done. Health is one variable (`health_value`; the body's copy is gone and effective stats read it). `harm(actor, amount, cause)` carries injury, illness (disease and spoiled or raw meals, from Phase 027's `illness_risk` by a stateless seeded draw), starvation (`starve_harm` 1.0 per period past `starve_limit`, so the existing timelines hold) and exhaustion (repeated collapse within a window). Elders decline daily by `age_rate`; infants carry `fragility`. Care, treatment, injury recovery and sleep recover up to `max_health`. Death at 0 records the cause in the death record and event; `SimulationReporter.deaths_by_cause()` counts them. Figures in the new `HEALTH` table are APPROX. See docs/phases/phase037/PHASE037_REPORT.md.

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

**Status:** done. `strike` is a major action resolved by the Phase 029 contest rule: the target may react (resist, brace, yield, evade) through the same `react` path; blow power is force x technique x intensity (the intensity ceiling is `max_intensity` x health), and a landed blow is `harm(target, strike_harm x margin, "injury")`, with deaths by violence tagged `violence`. A redirected blow harms the attacker by `redirect_harm` x intensity. New CONTEST keys `strike_harm` 0.1, `attack_cost` 0.2, `redirect_harm` 0.05 (APPROX). The unarmed blow does not use TOOL_FIT, so the hands floor does not apply. The simple backend's strike trigger (grievances recorded in `react`) is off by default: the 192-turn town100 probe has 0 deaths before and after. The Phase 054 packet snapshot fixture is regenerated (the action list gained `strike`). Open: grievance memory is not checkpointed. See docs/phases/phase038/PHASE038_REPORT.md.

**Goal.** Add a `strike` major action by an actor on a resident within reach, reusing Phase 029's
force, technique, efficiency, reaction turn and `redirected` rules:
1. The harm `amount` and the attacker's `cost` come from the contest, so a strong skilled
   attacker does more harm, an unprepared target takes it in full, a braced or skilled one takes
   less, and a skilled defender can redirect it. A drunk, tired or collapsed attacker is worse
   (Phases 034, 024). A strike can be tried at any stamina. Below `attack_cost` the blow is weak
   and the effort drives the reserve to 0, so the attacker may collapse mid-blow (Phase 024).
   The seed gates the decision (`bv_trigger`), which is the backend's; the world does not. The
   blow's `intensity` (Phase 050, default 1.0) scales the harm and the attacker's cost, and a pulled
   blow barely harms.
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
strike below `attack_cost` lands weakly and leaves the attacker collapsed; a skilled defender redirects an unskilled drunk attacker,
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
windows; forcing, digging and escaping are attempts (Phase 050); night sight and lamps (Phase 042).

## Phase 040 -- Objects as arms: hitting and throwing

**Status:** done, behind `physical_subsystems.object_force` (default off). A discrete object held in a hand can be swung (`strike` with `with`) or thrown (new `throw` major action; the `attempt` verb `throw` routes to it). Harm, range, breakage and effort come from the object's data (ITEMS weight, MATERIALS hardness and fragility, the container flag, TOOL_FIT's knife row and edge lists) through the new `OBJECT_FORCE` table (APPROX): a hammer blow does twice a bare blow; a load above one's strength is clumsy and costly; range falls with weight and rises with strength and intensity; a throw follows the grid line, stops before a sight occluder or at its range, and is a contest whose only reaction is stepping aside; a miss lands beside the target; a wooden mug breaks on impact, a metal pot and a hammer do not. A redirected grab drops the attacker's hand object. No randomness; the world records no assault. Bulk goods cannot be thrown yet. Simple village unchanged (0 deaths in 192 turns). The Phase 054 packet snapshot is regenerated. See docs/phases/phase040/PHASE040_REPORT.md.

**Goal.** There is no weapon class, no weapon list and no weapon skill. Any object a resident
can hold in hand (a discrete item, or one unit of a bulk good they carry) can be swung or thrown,
and what it does comes from physical data it already has: `weight` (185 of the 247 items have
it; the rest take their class default), `material` (79 have it), `verb` (an edge or point is
implied by cut, chop, reap, pierce, cleave, saw, mine), and `condition`. A stone, an iron hammer,
a firewood log, a spade, a mug and a loaf are all arms; they differ only in what they weigh and
are made of. The skill is Phase 029's `fighting`.
1. **Table `OBJECT_FORCE` (pack).** Reuse Phase 048's `TOOL_FIT` for hardness, edge, weight and
   breakage, and add here only the harm curve, `unwieldy_above` and range. Hardness by material (stone and metal over wood over leather,
   cloth, paper, wax and food; unknown is soft); a harm multiplier for edge and point verbs; a
   weight-to-harm curve with diminishing returns; `unwieldy_above`, the weight (relative to the
   user's strength) beyond which a swing or throw is clumsy; breakage by material (a mug or a
   pot shatters, a log does not); range as a function of strength and weight. Mark every number
   APPROX; add no item. Where an item has an authored `strike` fitness row (the seed's
   `Fitness{verb, mult, effort}`; one item may carry several rows, as the knife's prep and strike
   rows do) that row wins, and this table only fills in objects with none. Bare hands are the
   seed's row: mult about 0.05, effort about 3.
2. **Hitting.** The `strike` action (Phase 038) takes an optional `with`: an object held in hand.
   Harm is the object's strike fitness (`tl_strike`: harm = `fit.mult`; derived from weight x
   hardness x edge when no row exists), scaled by the contest outcome and cut down when the
   object is too heavy for the user. Use is gated on holding, never on owning. The attacker's stamina share (Phase 029's effort rule)
   rises with the object's weight against the user's strength, so a heavy tool tires a weak
   swinger. The object wears through the existing tool-wear path, or breaks if the table says
   so. A held object in a pack does not count.
3. **Throwing.** A new `throw` major action sends a held object to a target cell or resident
   as far as its `range` carries it; heavier goes shorter, and a target beyond range is simply
   out of reach of the throw, so it lands short. An obstacle on the line stops the flight there
   (Phase 028's occluders). The world never refuses a throw. A throw is Phase 050's `displace` of a
   held object, with `damage` on whatever it hits. Intensity sets how hard it is thrown: range and
   harm rise with it and accuracy falls.
   Against a resident it is a contest (Phase 029): the thrower's `fighting` skill, falling with
   distance and with intoxication or exhaustion through effective skill, against the target's
   evasion, with a reaction turn and an `evade` option if the target is eligible. A hit does the
   object's harm, reduced by distance. Anything else lands on the target cell, or on a neighbouring
   cell on a miss, and can be picked up. Breakable objects break. The object is conserved (it is
   moved, or destroyed by breaking, never minted). Throwing is not only violent: with no target it
   is moving an object across a gap, and the world reports no intent either way.
4. **Taking and disarming.** `take` from a hand is Phase 029's contest. A `redirected` outcome
   with a large skill gap drops the attacker's held object on the cell.
5. **Observation.** What a resident holds is visible to those with sight, as held tools already
   are, and a swing or throw is a physical event (who, what, where it landed). The world
   records no assault, no threat and no offence; carrying or throwing a thing is not one.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py` (the event only),
`domains/world_affordances.py` (table), `domains/bigville_entities.py` (self-test),
`bigville/backends/cheap.py` (strike or throw only if its policy already chose violence), a new
`tests/test_phase040_objects_as_arms.py`.

**Acceptance.** Tests show: a thrown stone or iron hammer harms more than a thrown loaf at the
same range, and harm falls with distance; a heavy tool is clumsy and costly in a weak user's
hands and effective in a strong one's; range falls with weight; a miss lands on a neighbouring
cell and the object can be picked up again; a mug thrown at a wall breaks; a throw out of range lands
short and one with no clear line stops at the obstacle, and neither is refused; a skilled defender evades or disarms an
unskilled thrower; the object count is conserved or reduced only by breakage; with the switch off
nothing changes.

**Out of scope.** Bows, slings and anything built to shoot (they are designed items, not "just
things"); armour; blocking with a held object; a trade in arms (residents).

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

**Status:** done, behind `DAYNIGHT.enabled` (default off): the lamplighter's round does not light a lamp under the simple policy yet (see the report). ready, after 024 and 028 (decision 2026-11-05: added). Spec:
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
   outdoor building) is allowed in the dark and goes badly: progress slows by a visibility
   factor on Phase 048's fitness path, mistakes waste inputs, and strain and injury risk rise.
   The seed's hook says you cannot work what you cannot see; here that is a consequence, not a
   refusal.
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
go out when it runs out; field work in the dark is slow, wasteful and risky and goes normally at
dawn; witnessing range shortens at night; the balance report includes lamp oil.

**Out of scope.** Moon phase effects other than light; astronomy beyond the formulae; bells and
the curfew (`bigville_bells`, residents' institution).

## Phase 043 -- Screening, treatment, well-baby care and illness

**Status:** done, behind `physical_subsystems.illness` (default off). Illness onset from the new `DISEASE` table (fever: seasonal daily rate x life-stage risk, stateless seeded draw keyed on seed, resident, disease and day); a daily course of `severity + progression (unscreened) - treat_relief (treated) + infant_fragility (unvisited infant)` through `harm(..., "illness")`, recovery at `natural_care` or `treated_heal`, ending after `course_days` (14, a design choice). Checkup, treatment (consumes medicine through the store guard) and well-baby visit are `care` actions with a `care_kind`, by a resident with the medicine or midwifery skill on the patient's cell; the flags lapse after `MEDICAL_CARE` days and are in `body_state`. All figures APPROX. Open: whether the simple doctor should choose these acts (a cheap.py policy, not added); whether treatment should cure at once. See docs/phases/phase043/PHASE043_REPORT.md.

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
`bigville_infant_care` (infant fragility). Behind a `births` switch so a scenario can keep a fixed population: off for fixtures and, once
the long-run growth-band check passes, on for the bigville pack, because a town that never
renews cannot sustain itself over a long horizon (user decision 2026-11-05: births are added).

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

## Phase 046 -- Detraining and ageing of the body

**Status:** ready, after 032 and 045 (decision 2026-11-05: added). NEW DESIGN, no seed: the Body
seeds only train. `bd_train_strength` and `bd_train_stamina` raise the trained component toward
base x (1 + `TRAIN_HEADROOM`) at `TRAIN_RATE` per effort, and nothing takes it away, so without
this every resident who ever worked ratchets up for life. Behind a `detraining` switch, default
off.

**Goal.**
1. **Detraining.** Each Body records the period of its last strength effort and last stamina
   effort (the `Effort` nodes Phase 032 uses). After `detrain_after` periods without that kind of
   effort the trained component falls by `detrain_rate` of itself each period, toward 0 and never
   below the base. A pack table `DETRAIN` gives the grace and the rate for each stat. Strength is
   lost more slowly than it was gained and stamina faster, as the detraining literature has it;
   cite sports-science reviews or mark APPROX.
2. **Ageing of the base.** One curve over age in a pack table `BODY_AGE`. Phase 045's growth is
   its rising half. This adds the falling half: the base holds through `peak_until`, then declines
   by `decline_per_year` toward a `floor`, with its own rates for strength and stamina. The
   trained ceiling rides on the current base.
3. **Illness, injury, confinement.** Health already scales effective stats. Someone confined,
   bedridden or collapsed has no effort and so detrains by the same rule, with no special case.
4. **Report.** Strength and stamina by age band and the share of trained residents; a self-test
   check that a working town's mean effective strength stays within a plausible band over a
   long run.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (tables),
`domains/bigville_entities.py` (self-test), the pack, `bigville/reporting.py`, a new
`tests/test_phase046_detraining.py`.

**Acceptance.** Tests show: a smith who stops forging loses trained strength once the grace has
passed and never falls below the base; one who keeps working keeps it; stamina and strength decay
at their own rates; an elder's base falls past `peak_until` and a young adult's does not; with the
switch off nothing changes; the run is deterministic.

**Out of scope.** Forgetting of skills (the practice subsystem has none, and it is neither seeded
nor requested); disease-specific wasting.

## Phase 047 -- Joint actions: people acting together

**Status:** part done, behind `physical_subsystems.joint_actions` (default off). Built: joint carry (a ground object above one adult's load moves floor(rho) cells, at most 3, when the members' summed force times `coordination(n)` meets mass / `load_unit`; short of it, the carriers strain; a carrier who collapses or leaves drops the load) and crewed recipes (`saw_planks` crew 2 to 3; a lone worker progresses at `crew_penalty` 0.25; each added worker adds less). The core's `team` term is real and is 1.0 for one person, so committed numbers are unchanged. The world publishes `joint` options with `present`; `BigvilleGame` resolves joint groups before the turn's other responses, so order does not matter; the simple backend joins when `present + 1 >= needs`. `joint` is not a MAJOR_ACTION (the Phase 054 snapshot is unchanged). Not built: group takes, gangs, group contests. Default village unchanged (0 deaths in 192 turns; 50-turn reference matches). See docs/phases/phase047/PHASE047_REPORT.md.

**Goal.** Let several residents do one thing at once, where one cannot.
1. **Rendezvous, not command.** The world publishes joint options in `actor_affordances`:
   `{"action": "joint", "task": <key>, "needs": N, "present": k, "max": M}`, where `present`
   counts the other eligible residents at the site who can take part now (a physical read-off).
   Each participant proposes the same task key in the same turn. Nobody leads. Who agrees to
   what is the residents' own business, by speech or by reading `present`.
2. **Resolution.** `BigvilleGame` groups the turn's responses that carry a `joint` key (in Phase
   025's order) and calls a new `world.enact_joint(task, participants)`, which resolves the whole
   group and claims every member's slot together. With fewer than `needs` participants the
   attempt is still made and fails physically: the load does not move, a crew job crawls at a
   `crew_penalty`, and each participant spends effort and takes strain against the load (Phase
   048) as they would for any too-heavy task. `joined k of N` is what they observe, not a
   refusal. Only a member who cannot act at all (asleep, collapsed, out of reach) is left out.
3. **Combined effect** (the core's `team` term, Phase 050). Team capability is the sum of the members' contributions times a
   `coordination(n)` factor (diminishing in n, raised by skill at the task). Load and stamina are
   split by contribution, each member paying Phase 029's share of its own force.
4. **Task kinds** (pack table `JOINT_TASKS`, each with its trigger):
   - *Heavy lift and carry.* Moving an object heavier than one member's capacity (today's
     `will_drop` case). Carriers share it, and pace follows combined capacity against load. If a
     member collapses or leaves reach, the load drops.
   - *Crewed recipes.* A `crew` field `{min, max}` on a recipe, authored for a few (a pit saw for
     `saw_planks`, wagon-making, raising a barn; cite or mark APPROX). A job needs `min` workers
     at the site, and its progress per tick is their summed labour times `coordination`, up to
     `max`.
   - *Gangs.* Simultaneous building labour and field work finish sooner (table).
   - *Group contests.* In Phase 029, several attackers combine into one force against a target,
     who reacts once to the combined action; several defenders can guard a holder; group
     restraint (Phase 033) shares the hold's load.
   - *Dual-key authorisation* (Phase 030), listed so it shares the same reading.
5. **Backends.** The simple backend takes a published joint option when its role or job covers
   the task and `present` meets `needs`, which is deterministic. Ocelot and LLM residents see the
   option and read `present`.
6. **Observation.** A joint task is a physical event seen by everyone with sight of the site.

**Write scope.** `worlds/bigville_world.py`, `bigville/game.py`, `bigville/backends/protocol.py`
(a `joint` key in the proposal's params only), `domains/world_affordances.py` and the pack
(`JOINT_TASKS`, recipe `crew`), `domains/bigville_entities.py` (self-test), `bigville/backends/cheap.py`,
a new `tests/test_phase047_joint_actions.py`.

**Acceptance.** Tests show: two residents carry an object one cannot, and one alone strains,
spends effort and may be hurt, with the object unmoved; a lone worker on a crewed saw starts but
crawls, and the job finishes faster with two than one, and with three by less than another full worker's worth; three
children take a stack from a smith where one cannot, and each pays a share that follows its
force; a member collapsing mid-carry drops the load; the outcome does not depend on the order the
responses are listed; simple residents coordinate from `present` alone; with the switch off nothing
changes. The executor first lists which pack items exceed one person's capacity, so the carry cases
are real.

**Out of scope.** Leadership, orders and wages for a crew (residents' institutions); standing
teams and guilds (records); animals yoked to carts (draught exists as `pull`; a later phase);
vehicles.

## Phase 048 -- Tools by fitness: use X with Y, and the wrong tool in a pinch

**Status:** done. A tool has a fitness for each verb (closeness x hardness x edge x weight, times quality and condition; the right tool at full quality and condition is 1.0, so committed recipe numbers are unchanged); bare hands fit at `hands_fit` 0.05. A missing tool is no longer a refusal: the job runs at 1/fit time, `clamp(1/fit, 1, effort_cap)` stamina, extra wear on a poorly fitting tool, strain to `accident`, quality and yield scaled by the lowest fit, and a batch below `waste_below` is wasted. Attempts use the same fitness. New `TOOL_FIT` table, free action `stop`, `tool` key on work proposals, `tool_tally` and `improvised_work()`. Offered options still need the right tool, so default backends are unchanged (a 192-turn town100 run matched HEAD exactly). Open: worn shelf tools now yield less in proportion to their condition; bare-hand strain may be lethal; push needs a tool (hands 0.05); `stop` needs game.py routing. See docs/phases/phase048/PHASE048_REPORT.md.

**Today.** A recipe names tool kinds, and `_worker_tool` and `_held_tool` look for an unbroken
item of exactly that `kind`, so a recipe either has its tool or is refused. `ToolFit.mult`
(base_mult x quality x condition) is computed and updated, and then read by nothing but an
accessor and tests, so a fine hammer and a battered one forge a plough alike.

**Goal.** The right tool gives default effectiveness. Any other object, or none, gives what it
physically gives, and the world charges for the difference. Fitness is the `fit` term of Phase
050's core, and `TOOL_FIT` is the tool-facing part of its `VERBS` and `MATERIALS` tables
(closeness, hardness, edge). This phase wires tools in and adds only the authored per-item rows,
the `tool` parameter, the workplace shelf, wear and `stop`.
1. **Fitness per verb.** A tool slot has a verb (from the named tool kind's `verb`). An item may
   carry authored rows `{verb, mult, effort}` (a knife has cut and strike rows). Its fitness for
   a verb is its authored row if it has one. Otherwise it is derived, in a pack table
   `TOOL_FIT`: verb closeness (same verb 1.0; near pairs such as chop, cleave and hew, or strike,
   pound and drive, or dig and scoop, or cut, saw and pierce; else 0, in the manner of
   `SKILL_CLOSENESS`) times physical suitability (the tool's hardness against the work's, an
   edge or point for cutting verbs, a weight band for striking and digging). Fitness is then
   scaled by quality and condition, so the existing `ToolFit` finally matters. Bare hands are the
   seed's row, floor 0.05 and effort 3. A hardness mismatch (cutting iron with wood) gives 0:
   the attempt is allowed and makes no progress.
2. **Any object, or none.** A work or gathering proposal may carry `tool`, a held item, or none
   for bare hands. Omitted, the right kind is used if held or on the workplace shelf, else bare
   hands. The world never refuses for want of a tool.
3. **Consequences by fitness f.**
   - Progress per tick is f, so duration scales by 1/f.
   - Stamina and hunger cost scale by 1/f up to the seed's effort cap (Phase 022's path).
   - Yield and quality fall with f; below `waste_below`, a job that completes consumes its inputs
     for little or nothing.
   - Tool wear per tick rises as f falls and with hardness mismatch, and the tool breaks at 0.
   - Strain accumulates each tick by effort share x (1 - f), and at a threshold the worker is
     hurt through `harm(actor, amount, "accident")`, then strain resets. It is deterministic.
4. **Observed, not announced.** The world does not publish f beforehand. The resident sees the
   tool's weight, material and condition, and observes progress per tick, strain, damage and
   injury as they happen, and learns from them.
5. **`stop`.** A new free action abandons a timed job. Inputs are taken at completion, so only the
   progress is lost, and `busy` clears. A resident has to be able to quit a hopeless attempt, and
   the world never decides it is hopeless.
6. **Reuse.** Phase 040's strike and throw use the same table and the same `strike` row, and bare
   hands are the same floor.
7. **Simple backend.** It uses the right tool when it has it, as now. A parameter `improvise`
   (default off) lets it reach for the held item with the best fitness it could judge from visible
   properties when the right tool is missing.

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (`TOOL_FIT`),
`domains/bigville_entities.py` (self-test: every verb in a recipe's tool slot has a closeness
row), the pack (verb rows on a few items), `bigville/game.py` (`tool` in the proposal),
`bigville/backends/cheap.py`, `bigville/reporting.py` (counts of improvised work and accidents),
a new `tests/test_phase048_tool_fitness.py`.

**Acceptance.** Tests show: the right tool at quality 1.0 and full condition does today's job in
today's time (the default); a poor or worn hammer is slower than a fine one; a cleaver is faster
than bare hands and slower than a knife for knife work; a wooden spoon on iron makes no progress,
wears, snaps, and the worker is hurt after enough strain; no tool at all is allowed and takes
about 1/0.05 of the time at triple effort; `stop` ends a hopeless job; the simple backend's
default is unchanged. The existing tests that assert a refusal for a missing or broken tool (Phase
001's hammer test among them) change to assert the consequence, and the report lists each.

**Out of scope.** Place-bound equipment (oven, press, loom, mash tun, dye vat), a second slice;
using one item with another in general (lashing, wedging, propping), which needs a physical
property system; learning which tool suits (the resident's); the skill, season and strength
gates (Phase 049).

## Phase 049 -- Consequences instead of gates

**Status:** done. Gates become consequences: below the skill floor a batch yields in proportion to skill / floor and is spoiled below `skill_ruin_ratio` (0.5); out-of-season gathering yields `off_season_yield` (0.25) and out-of-season sowing fails at the next period; below a recipe's strength demand the job progresses at strength / demand and strains; a busy worker's open jobs share progress (`stop_job` ends one); a meal without its serving gear loses `unserved_waste`; a fluid in a leaky vessel leaks `leak_per_period`; over-capacity goods drop at the receiver's feet; an unripe harvest yields its maturity share; an animal tended too soon yields nothing and is fussed; a named tool not held means bare hands; the direct world walk below e_low is slow, not stopped. Retired codes: `busy`, `too_tired`, `no_capacity`, `no_tool`, `out_of_season`, `on_cooldown`. Kept as refusals so the simple village is unchanged (0 deaths in 192 turns, 50-turn reference matches): a backend plan's walk below e_low (new code `exhausted`), the plan-path rest at a high reserve and watering an unthirsty crop (`not_needed`), and the medical and maintain `unskilled`/`not_needed`. Offered options are unchanged. Golden numbers unchanged. See docs/phases/phase049/PHASE049_REPORT.md.

**Goal.** Find every refusal in the world that stops a possible act, and turn it into a
consequence. Keep only the refusals for acts that cannot happen. The report lists each gate with
the test changes it caused, and stops to ask if a conversion needs a design decision.
Convert:
1. **Skill floor** (`_skilled_enough`, `MIN_SKILL`). Attempting below the floor is allowed.
   Quality and yield fall and the chance of a ruined batch rises with the gap; a failed batch
   wastes its inputs and time; heavy trades can injure.
2. **Season** (`_recipe_in_season`, `sow`). Gathering out of season yields what the season gives,
   often nothing, for the time spent. Sowing out of season plants the seed and the crop fails
   to the season's weather, so the seed is lost and the loss is seen later.
3. **Strength requirement** on open recipes. Allowed. Effort scales by requirement over strength,
   progress slows, and strain and injury risk rise (Phase 048's path).
4. **Busy** (Phase 023's `busy` refusal). Starting a second job is allowed. Progress per tick is
   divided among the worker's open jobs at the site, and `stop` ends any of them.
5. **Serving equipment** in `eat` (soup without a bowl, drink without a mug). Allowed, with a
   share of the meal spilled or wasted.
6. **Watertight containers** for fluids in `put`. Allowed; a leaky vessel loses fluid each
   period.
7. **Over-capacity** in `give`, `transfer`, `fetch` and `put`. Allowed; a recipient or carrier
   over capacity drops the excess (the carry model already does) and is slowed while overloaded,
   and a full container spills onto its cell.
8. **Pointless acts** that the world refuses today: `rest` at a reserve of 0.8 or more, caring for
   someone healthy, watering an unthirsty crop. Allowed; they cost the time and, for the crop,
   the water.
9. **Too tired to walk** (Phase 024's `too_tired`). Below `e_low` a resident can still walk, at
   the slowest rate, until the reserve falls below `e_collapse` and they fall down. The seed's
   zero-move budget stops movement before the collapse; the decision was "slower until you fall
   down", so the stop goes. Record it.
10. **Harvesting a crop that is not mature** (`not_ready`). Allowed: the yield is the maturity
   fraction of the full yield, and the crop is gone. Burying with no open grave stays refused,
   because the act cannot happen.
11. **Tending an animal again too soon** (`on_cooldown`). Allowed: it yields nothing and costs the
   time.
12. **Reason codes.** `unskilled`, `out_of_season`, `busy`, `no_tool`, `no_capacity`,
   `too_tired`, `on_cooldown`, the harvest case of `not_ready`, and any other code for a
   converted gate are retired from `REFUSAL_REASONS`, and what happens is observable instead.
   The codes for acts that cannot happen stay (`not_known` means no such recipe exists,
   `not_in_reach`, `not_at_site`, `out_of_stock`, `not_held`, `container_locked`, `asleep`,
   `collapsed`, `unsupported`, `malformed`, the target codes).

**Write scope.** `worlds/bigville_world.py`, `domains/world_affordances.py` (consequence
tables), `domains/bigville_entities.py` (self-test), the pack, `bigville/backends/cheap.py`
and `psi_can.py` (they may still prefer to avoid these, as choices), tests that assert the old
refusals (each change listed), a new `tests/test_phase049_consequences.py`.

**Acceptance.** Tests show, for each gate above, that the attempt is accepted, that the
consequence appears and is observable to the actor and not announced, that the old refusal code
no longer fires, and that a refusal for an impossible act (no stock, out of reach, locked,
asleep) still does. The simple village's behaviour is unchanged, because its backends already
avoid these acts, and the report says so with numbers.

**Out of scope.** Refusals for impossible acts; the conversion of future phases' refusals (they
were written to follow the principle).

## Phase 050 -- The resolution core: one rule for every attempt

**Status:** done (stage 1 and 050b). The pure core `worlds/resolution.py`; `VERBS`, `MATERIALS`, `RESOLUTION` in both packs; `lock_strength`; the `attempt` action with `damage` (smash, hit, cut, chop, saw; a broken container spills its contents as dropped stock), `open` (pry, force) and `displace` (push, pull, drag move a physical object by floor(surplus x 2) cells, at most 3); native verbs routed; intensity clamped and reported; trivial and slot rules; strain to `harm(..., "accident")`, recovered by sleep; tool wear and noise. Recipes take a pace (`start` intensity, clamped to [0.5, 1.5]) with quality, yield and ruin curves, and the free action `set_intensity` keeps progress; at pace 1.0 every committed number is unchanged (golden table). Open: lift, carry, throw and dig are still `unsupported` (throw is Phase 038's); `game.py` routes only `speak` among free actions, so `set_intensity` needs a Tract B routing change; spilled piles have no pick-up path; there is no pit-saw recipe, so pace is tested on `make_table`. See docs/phases/phase050/PHASE050_REPORT.md and PHASE050B_REPORT.md.

**Goal.** A pure resolution function plus pack tables, and a generic `attempt` action so that
arbitrary actions are allowed.
1. **Capability against demand.** An attempt has a capability C and a demand D.
   - *Capability terms (each a pack-set factor):* `force` (effective strength x size x the
     exhaustion step of Phase 024), `technique` (the effective skill at the verb's skill, which
     already carries intoxication and limitations), `fit` (the tool's fitness for the verb, Phase
     048), `team` (Phase 047's coordination), and `conditions` (darkness, weather, load).
   - *Demand terms:* a recipe's `difficulty` (all 166 recipes carry one, 0.2 to 3.5), an
     object's mass, a material's toughness, a lock's strength, or an opposing side's applied force
     and technique (Phase 029).
   - The ratio rho = C / D. A pack table `RESOLUTION` maps it, deterministically, to every
     output below. The reference point is fixed so that a worker meeting a recipe's `MIN_SKILL`
     and strength requirement, with the right tool, has rho = 1, and the committed numbers do not
     move there (see 5).
2. **Outputs of one resolution step (per tick, or per instant action):**
   - *progress rate* = min(`cap_rate`, rho^a), so 1 at the reference and 0 at no capability. For
     recipes `cap_rate` is 1, so no one works faster than today;
   - *cost* = `base_cost` x clamp(D / C, floor, `effort_cap`) x `efficiency(technique)`, through
     Phase 022's stamina and hunger path. It is paid in full at the reference and rises toward the
     seed's cap (about 3) as capability falls. For recipes `floor` is 1, so a strong worker pays
     today's cost (Phase 022 is unchanged); for contests `floor` is 0, so a strong side pays
     little, capped at the whole of one's own force (Phase 029);
   - *quality* and *yield* curves in rho; below `ruin_below` a completed job spoils its inputs;
   - *strain* per tick = cost share x (1 - min(1, rho)), accumulating deterministically until it
     tips into `harm(actor, amount, "accident")` and resets;
   - *wear* on each tool and on the target, rising as `fit` falls and with hardness mismatch;
   - *noise*, a loudness set by force and material, published as a physical event heard within
     Phase 028's radius (breaking things is loud);
   - a trivial result (below `trivial_below`) is free in stamina, and below `slot_above` leaves
     the major action unspent, as Phase 029 set out.
   There is no randomness: the same state gives the same result.
3. **Effect primitives, a closed and mechanical set.** `displace` (push, pull, lift, drag, carry,
   throw; demand is mass over friction and terrain; the result is a position change by the
   surplus force), `damage` (hit, smash, chop, cut, pierce, saw; demand is the target's
   toughness; the result lowers its `condition`, destroying it at 0 and leaving pieces by a
   byproduct table, and on a person goes through `harm`), `open` (unlock, force, pry, pick; demand
   is the lock's `strength`; the result unlocks, or breaks the lock or the door), and `transform`
   (a recipe, whose result is the existing job). Anything else is a new primitive in a later
   phase, never an ad hoc rule.
4. **The `attempt` action.** `{"action": "attempt", "verb": <name>, "target": <id or cell>,
   "with": <held item or none>, "intensity": <number, default 1.0>}`. The verb comes from a pack table `VERBS`: its effect primitive,
   the skill it uses, its closeness to the tool verbs, and its default time and effort. Any verb x
   any target x any tool is allowed, and the core resolves it. An action the world already has
   (`move`, `eat`, `sow`) still routes to its own primitive. A verb not in `VERBS` is `unsupported`,
   the one refusal for "the world has no physics for that". Backends map their intent to a verb;
   the world never parses free text.
5. **Adoption of the committed phases.** The pure function lives in `worlds/resolution.py`
   with no world state. The committed formulas become terms: Phase 022's effort and hunger scaling,
   Phase 023's job occupancy, Phase 024's exhaustion step, and the carry model's speed. The report
   gives golden numbers before and after for the existing recipe, movement and exhaustion cases,
   and every difference with the reason.
6. **Tables.** `VERBS`; `MATERIALS` (hardness, toughness, fragility, edge, a default for each item
   class, covering every item with a `material`); `RESOLUTION` (the exponents, caps, curves and
   thresholds); a `lock_strength` on lock kinds. Mark every number APPROX. The self-test checks
   that each verb has a skill and a tool closeness, each material is complete, and the
   `RESOLUTION` curves are monotone.
7. **Observed, not announced.** An attempt publishes progress, strain, damage and noise as they
   happen, never rho or the demand beforehand (Phase 048's rule).
8. **Locks are barriers with a strength.** `container_locked` still refuses the ordinary opening
   without a key. `attempt` `open`, `smash` or `pry` on the lock or the container resolves through
   the core: the lock or container takes damage, it opens or breaks if the attempt completes, and
   it is loud. A frail resident with a spoon makes no progress and breaks the spoon.
9. **Intensity (conviction).** (decision 2026-11-05: actions can be done at any level of force.
   An agent may try to cut metal with wood, fail, and then try harder.) Every `attempt`, recipe
   job, gathering action, blow and throw takes an optional `intensity` i, default 1.0, the normal
   level for that action (the reference point of item 1). Below 1 is gentle or careful, above 1 is
   forcing it. The shape is the seed's `eff_loudness = clamp(chosen, max)` in `bigville_loud_comm`:
   the world clamps the chosen value to `max_intensity` and reports the applied value. The ceiling
   is a rested adult's limit, lowered by the exhaustion step (Phase 024), low health and a low
   reserve. The world never refuses a level, and a clamp is shown to the actor.
   - *Force-type primitives* (`displace`, `damage`, `open`, a blow, a throw, a grip). The `force`
     term of C is multiplied by i, so progress, damage dealt and distance rise with it.
   - *Cost.* Stamina and hunger scale with i^`k` (k above 1, so twice the push costs more than
     twice), and fall below normal when gentle.
   - *Overexertion.* Above `i_safe` the body takes strain whether or not the attempt works,
     `max(0, i - i_safe)^m`, so forcing it can pull a muscle even when it succeeds. A reserve driven
     to 0 collapses the actor (Phase 024).
   - *Wear and noise.* Tools, the target and the room's sound rise with i. A gentle tap is quiet.
   - *Recipes (`transform`).* i is pace. Above 1 the job is faster, up to `haste_cap`, at a cost in
     quality that moves the batch toward `ruin_below`, where it spoils (deterministic, no dice). Below 1 it is slower and better, up to
     `care_cap`.
   - *Hopeless attempts.* Harder multiplies the capability. At zero fitness (wood against iron)
     it changes nothing but how fast the tool snaps and how much the worker strains. At low,
     non-zero fitness it gets there at a price.
   - *Persistence.* Damage to a lock, chest or wall stays on its `condition`, so "fail, then try
     harder" continues from where the first go left off. A half-worn lock is easier the second time.
   - *Changing mid-job.* A new free action `set_intensity` changes a running timed job's level
     without losing its progress. (Phase 048's `stop` does lose it.)
   - *Pulling a blow.* A blow at low i barely harms, which allows play-fighting and
     de-escalation.
   - *Backends.* Default 1.0. The simple backend gets an optional `escalate` policy, default off:
     after a set number of ticks with no observed progress it raises i by a step, up to the
     clamp. LLM and Ocelot residents choose freely.
   `RESOLUTION` gains `max_intensity`, `i_safe`, `k`, `m`, `haste_cap`, `care_cap` and
   `haste_penalty`.

**Write scope.** new `worlds/resolution.py`, `worlds/bigville_world.py`, `bigville/game.py` and
`bigville/backends/protocol.py` (the `attempt` proposal), `domains/world_affordances.py` (tables),
`domains/bigville_entities.py` (self-test), the pack (`VERBS`, `MATERIALS`, `RESOLUTION`, lock
strengths), `bigville/backends/prompts.py` (the verb list in the action vocabulary),
`bigville/reporting.py` (attempts by verb and outcome), new `tests/test_phase050_resolution.py`
and `tests/test_resolution_pure.py`.

**Acceptance.** Tests show: the pure function is monotone (more force, technique or fit never
lowers progress or raises cost share or strain); at the reference point the recipe, movement and
exhaustion results equal today's, and the existing suite passes with every changed number listed;
`smash` a wooden chest with a hammer damages it each tick, breaks it at 0 condition and spills its
contents, loudly enough to be heard within the radius; forcing a locked container with no key
succeeds for a strong resident with a heavy tool and makes no progress, and breaks the tool, for a
frail one with a spoon; `push` moves a cart by the surplus force; an unknown verb is
`unsupported`; an impossible attempt (target out of reach, nothing held) is still refused;
a recipe at intensity 1.0 equals today's, at 1.5 a pit-saw job finishes sooner with lower quality
and more stamina spent, and at 0.5 slower and better; smashing a chest at intensity 2 deals more
damage per tick than at 1, costs more than twice the stamina, and is louder; intensity above
`i_safe` accumulates strain even on success; an intensity above `max_intensity` is clamped and the
applied value reported, and a low reserve lowers the clamp; wood against iron at intensity 3
changes nothing but breaks the spoon sooner; a second attempt on a half-damaged lock opens it
sooner than the first; `set_intensity` changes a running job without losing progress; a blow at
low intensity barely harms; the simple backend's default is 1.0 and `escalate` raises it only
after the set span without progress; two
different backends proposing the same attempt get the same result; no RNG is drawn.

**Out of scope.** Further effect primitives (bind and lash, climb, swim, burn), each its own phase;
free-text intent (the backend's); a verb for every item; magic and chemistry; the existing gates
of Phase 049, which become core terms there.

# Programme D: seeing and being seen -- words, the agent view, fog, the LLM and a TUI

**Decision 2026-11-05 (user).** A resident, whether human, LLM or a terminal player, gets only
what its character could perceive and know, in the words a person would use, not the engine's
numbers. The same payload feeds the character sheet, the LLM prompt and a terminal interface.
The map is fogged in three levels of detail.

**Survey of the backends and their inputs** (read 2026-11-05; the observation payload below was
printed for a resident of the 100-resident town at turn 0):
- *Simple and psi_can* read raw numbers (energy thresholds such as 35.0, hunger floats). That is
  fine for deterministic locals and stays.
- *LLMBackend* is an 86-line shell: no provider is registered or concrete, bad output raises out
  of `decide`, and the prompt is built from raw observations. *OcelotBackend* hands the context to
  the adapter's `resident_plan_from_context`. *HumanBackend* queues responses and, for contests,
  reactions.
- The observation payload is about 15,000 characters a turn before the private part, and it
  carries the engine's internals as well as the world: raw floats (`energy` 100.0, `hunger` 0.0,
  item `condition` 1.0, `score` 0.0); internal multipliers (`speed_factor`, `exhaustion_step`,
  `terrain_*`) and a full `terrain_movement` table of every terrain's speed and stamina cost;
  `nearby_residents` with each resident's `role`, `klass` ("poor") and `group` ("low"), exact
  position, `tie_strength` and `band_code` (8,068 characters at turn 0); and `world_frames`
  (5,160 characters of laws and policies, whose filtering to what the resident holds needs
  checking).
- Affordances name exact `destination` cells for places the resident may not know (a cow at
  [36, 29], the bakery). That breaches Phase 019's "never the map".
- `/api/state` returns the whole world (every resident's hunger, energy, coin, inventory and
  position) and the Phaser client draws from it, so a human player sees everything. No limited
  view exists.
- Phase 019 derives place knowledge at three precisions (exact, rough, none) with landmarks, and
  nothing updates it after founding. The seed `bigville_move_nav` already designs a per-agent map
  belief in which "unknown = absence".
- *Continuity today.* A sampled founding resident (a councillor) holds 16 raw personality numbers
  with no words, and several of them are Ocelot engine parameters (`w_supergraph`, `cred_on`,
  `resolution_bins`, `emotional_core_enabled`, `carried_weight`) mixed in with real traits (charm,
  hostility, spite, mood bias, the world-safety, trust and self-worth priors). It holds 238 memories,
  all derived knowledge, and no biography. The world holds no relationship records at all (0 of 100
  residents hold any), although every resident has genealogy edges (Phase 009) and 77 share a
  household with someone, so the material to seed ties from exists and is unused. The simple backend's "routine" is
  four hour bands written into `cheap.py` (before 9 morning, before 17 workday, before 21 evening,
  else night) plus job-based preferences, and its only momentum is a continuation for walking to a
  destination. A model dropped into this has no self, no day and no one to know, and a provider
  error today costs it its turn.

**Development access for the LLM backend (recorded 2026-11-05).** The repository's `.env`
(gitignored, never in history) holds `OPENCODE_GO_API_KEY`, an OpenCode Go key the user supplied
for testing and developing the LLM backend. Never print it, log it, commit it, or put it in a
transcript, test output or error message. Checked against https://opencode.ai/docs/go/ on this date,
with one tiny call:
- Endpoint: `POST https://opencode.ai/inference/go/openai/v1/chat/completions`, `Authorization:
  Bearer <key>`, OpenAI chat-completions body. The docs say every text model also works through
  this endpoint, though some models' native API is Responses or Anthropic Messages. The model list
  is `GET https://opencode.ai/inference/go/v1/models` (30 models at the time). The call returned
  `ok` from `glm-5.3-flash` in 1.6 seconds.
- Headers the service asks for: a `User-Agent` that names the client (not a generic library name),
  and a stable `x-opencode-session` per conversation, for routing and prompt caching.
- `max_tokens` includes the model's reasoning tokens (11 of the 14 completion tokens in the test),
  so a JSON reply needs a generous limit or the answer is cut.
- Each response reports `usage.opencode.allowance` and `list_cost`, which the provider should read
  to keep a running spend.
- Limits are monthly dollar amounts per model (5-hour 20 percent, weekly 50 percent). The cheapest
  suitable development model is `glm-5.3-flash` ($0.15 in and $0.50 out per million tokens, not
  trained on, 0-day retention).
- **Intended use.** The service is "designed for OpenCode and other coding agents" and monitors for
  abuse. A town of LLM residents is not coding-agent traffic. Light development and testing is
  reasonable. Do not run hundreds of calls a turn against it, keep concurrency small, set a
  spend cap, and treat anything larger as needing a different provider or the user's decision.
- **Privacy.** Avoid the models marked as trained on prompts (the "Contributor" models and "Iceman
  Contributor Free"). Never default to one.
- **Scale (user, 2026-11-05).** LLM residents are not meant to run a large town for now. They are
  for comparison, testing, and for someone with a bigger budget. Nothing here targets a hundred
  model residents on a small plan; the concurrency and spend limits above are the design, not a
  stopgap.

**Order.** 051 first. 052 follows 051. 053 follows 052 (Phase 028's `sight_range` is done).
058 follows 051 (and uses Phases 009 and 019, which are done); 059 follows 031 and 058;
054 follows 031, 051, 052, 058 and 059; 055 and 056 follow 054 and 059 (056 also uses the
counters from 021 and 048). 057 follows 051 and 052, and shows a local patch of the map until 053 lands.

## Phase 051 -- Words for numbers and statuses

**Status:** done (see History). Decision 2026-11-05: the translations of numbers and statuses belong in
the entity data, so the character sheet and the LLM share them. Tract B.

**Goal.** A pack lexicon, with one function to read it, so no consumer invents its own words.
1. **Bands.** For each quantity a resident can perceive, an ordered table of thresholds, each
   with a label and a phrase, in two perspectives. *Self* is how you feel ("famished", "worn
   out", "strong for your age", "competent at smithing"). *Other* is only what an observer could
   see ("looks gaunt", "visibly drunk", "limping", "looks strong"). Quantities: hunger, energy
   and stamina reserve, health value and the status strings (`healthy`, `injured`,
   `malnourished`, a disease), strength, stamina, mood, intoxication, deficiency, strain, item
   condition and quality, load and carry ratio, chill and soaked, skill level (and trade
   competence), the time of day (`hour`), season, weather, light, distance (a short walk, out past
   the mill), durations, quantities (a few, a handful, a cartload), life stage and age,
   relationship strength and kind, personality traits (temperament, trust, spite, charm, outlook),
   the blocks of a usual day, and finery as seen on another.
2. **Reverse words.** `INTENSITY_WORDS` (gently, carefully, normally, hard, with all your
   strength, mapped to Phase 050's intensity), `AMOUNT_WORDS`, and `VERB_ALIASES` (smash, break,
   bash, batter all to the verb `smash`), so proposals may use the words a person would. Numbers
   stay accepted.
3. **API.** `domains/lexicon.py`: `describe(quantity, value, perspective)` returns
   `{label, phrase}`; `value_for(quantity, label)` returns a representative number. Lookup by
   thresholds is monotone and total.
4. **Pack-swappable.** Words belong to the pack, so a different world has different words. The
   self-test checks that thresholds cover the range of each quantity with no gaps or overlaps, that
   labels are unique within a quantity, and that every quantity in the observation payload that a
   resident can perceive has a table.

**Write scope.** `domains/lexicon.py` (new), `domains/world_affordances.py` and the pack (new
`lexicon.json` tables), `domains/bigville_entities.py` (self-test), a new
`tests/test_phase051_lexicon.py`.

**Acceptance.** Tests show: every band table is monotone, complete and unambiguous; each label
maps to a number that falls back into the same band; `describe` never returns a raw number;
perspectives differ (hunger is felt by self and only seen as gauntness by others, and a
hidden quantity such as another's strength gets no `other` phrase unless it is visible); a
different pack gives different words; the reverse words resolve ("hard" to the pack's intensity
value, "smash" and "bash" to one verb).

**Out of scope.** Other languages; self-assessment bias (a resident misjudging their own skill);
residents learning vocabulary.

## Phase 052 -- The agent view: the one limited interface

**Status:** done (see History). Agent mode applies when `--player` is named; the Phaser client moves with Phase 053 (decision 2026-11-05: a limited user interface that only gets the
data available to the agent).

**Goal.** One payload that is everything an agent may know, built by whitelist, used by the LLM
prompt, the character sheet, the TUI and any other player client.
1. **`BigvilleGame.agent_view(actor, mode="agent")`** returns:
   - `self`: the character sheet. Identity, job and trade, life stage; the body in words; skills in
     words; what is carried, worn and held; what the character knows (understood and aware-of,
     with gist and without the basis) and which places, with the precision held; kin and
     relationships in words; recent memories and notes.
   - `now`: the time of day, weather and light, in words.
   - `around`: the residents and things the character can perceive. A resident the character
     knows (from Phase 019's knowledge) appears by name, a stranger as a description. Only the
     `other`-perspective words are used, so nobody's `klass`, `group`, hidden stats or coin
     appear. Events seen and heard (Phase 028) and any sound.
   - `map`: Phase 053's fogged map, and until then a patch of cells within `sight_range`.
   - `can`: the affordances restated as handle, action, target description and tool, with no
     `score`, no multipliers and no coordinates for places the character does not know.
   - `last`: the last outcome with its reason's meaning (Phase 021), and any strain, damage or
     progress observed.
2. **Whitelist and leak test.** The builder copies named fields only. A test fails if the view
   contains a key outside the whitelist, a raw number for any lexicon quantity, or a
   referee-only field (`score`, `speed_factor`, `exhaustion_step`, the `terrain_movement` table,
   another resident's `klass`, `group` or stats, an unknown place's coordinates, Phase 048's
   fitness or Phase 050's demand and `rho`). The executor records what `world_frames` carried and
   filters it to what the resident holds.
3. **Modes.** `agent` is words only. `referee` adds the numbers and the true state, for
   debugging and tests. The simple backends keep their raw `ActorContext` unchanged.
4. **Server.** `GET /api/view?actor=NAME` returns the agent view (the player by default).
   `/api/turn` returns the view in place of the snapshot. A server started in agent mode, which
   is the default for a human player, answers `/api/state` with 403, and `--referee` restores the
   omniscient state for the Phaser client and tests.

**Write scope.** `bigville/game.py` (`agent_view`), `bigville/backends/protocol.py` (the view on
`ActorContext`), `bigville/server.py`, `domains/world_affordances.py` and the pack (the
whitelist), `domains/bigville_entities.py` (self-test), a new `tests/test_phase052_agent_view.py`.

**Acceptance.** Tests show: the leak test passes for a founding resident and after a run; two
residents standing together get different views (their own sheet, what each knows); a stranger is
a description and a known resident a name; the view is deterministic for a given state; `/api/view`
returns it and `/api/state` is refused in agent mode; the full existing suite passes with the
simple backends unchanged.

**Out of scope.** The Phaser client in agent mode, which needs the fogged map first (a later
phase); the LLM prompt (Phase 054).

## Phase 053 -- Fog of map: three levels of detail

**Status:** done (see History). Open: Ocelot residents are not fogged; sight occluders are not applied; the map cap allows five labels. ready, after 052 (decision 2026-11-05: three levels; hidden, vaguely structural, and
full). Spec: `seeds/bigville_move_nav.json` (a persistent per-agent map belief, "unknown =
absence") and Phase 019's place knowledge (exact, rough, none, with landmarks).

**Goal.** Each fogged character holds a map memory at three levels, by area and by cell:
- **0, hidden.** Nothing is known, not even that it exists.
- **1, vague.** The structure: area names, landmarks, named buildings and roughly where (a word
  from the lexicon, "a short walk north, past the mill"), and the roads as paths between them. No
  cell detail, no terrain, no occupants.
- **2, full.** Cell-level terrain, objects, and what was seen there.
1. **Data.** Map areas from the pack (`FOUNDING_MAP`, `FOUNDING_PLACE_LABELS`,
   `FOUNDING_ANCHOR_ALIASES`) give the level-1 vocabulary. A `MapMemory` per character (cell to
   level, `last_seen`, last seen terrain and occupants) lives in the character's held state, so it
   is backend-owned memory and is checkpointed.
2. **Initial map.** Derived from Phase 019: a place held as exact is level 2 around it, a rough one
   level 1 for its area, none stays 0; the home and the job's routine routes are level 2; public
   landmarks (the market, the well, the church) are level 1 for everyone.
3. **Learning.** Each turn, every cell within `sight_range` (Phase 028; shorter at night after
   Phase 042) becomes level 2 and is stamped. A landmark visible from beyond that range becomes
   level 1. A `place_belief` memory update (told by someone, or read) raises a place to level 1, or
   to level 2 if it carries a position. Nothing lowers a level, but detail ages: the view says "as
   you remember it", with how long ago.
4. **Filtering.** For fogged backends the agent view's `can` lists only targets the character
   knows. A level-1 place is offered as "walk toward the mill". A level-0 target is not offered.
   `move` gains `toward` (a landmark, area or compass direction), so exploring unknown ground is
   always possible. By default the world walks the true shortest path to what the character is
   heading for, as if they asked the way; a belief-based navigation that can get a traveller lost
   is a later phase.
5. **Who is fogged.** A per-backend flag `fogged`: true for LLM, human and TUI residents, false for
   the simple locals, so the self-supporting town is unchanged. The referee view can overlay the
   true map.
6. **Map in the view.** The `map` section renders the three levels distinctly: hidden is blank,
   vague is landmarks and area labels, full is cells.

**Write scope.** `bigville/game.py`, `bigville/character.py` (held state), `bigville/game_persistence.py`,
`worlds/bigville_world.py` (`toward`), `domains/world_affordances.py` and the pack (map memory
constants, the level-1 vocabulary), `domains/bigville_entities.py` (self-test), a new
`tests/test_phase053_fog.py`.

**Acceptance.** Tests show: a farm labourer starts knowing their fields in full and the tannery
only vaguely, and a new incomer does not know where the quarry is (Phase 019's cases); walking
reveals cells within sight and they stay known; an old observation is marked stale; a place told by
speech becomes level 1; a level-0 target is absent from `can` and a level-1 one is offered as
"toward"; a simple NPC's affordances and behaviour are unchanged; the memory survives a
checkpoint; the three levels render differently; replay is deterministic.

**Out of scope.** Belief-based navigation and getting lost; maps as items you can hold and read
(a natural follow-up); night sight (Phase 042); the Phaser client.

## Phase 054 -- The LLM backend, stage 2: the prompt packet and the response schema

**Status:** done (see History). Open: `target:N` as a move handle; repair keeps the 031 shape (decision 2026-11-05: plan the build of the LLM
backend). Phase 031 is stage 1 (a registered, hardened backend with a fake provider); 054 to 056
complete the build.

**Goal.**
1. **Prompt from the view.** `PromptBuilder` builds from `agent_view`, not from raw observations,
   so the model sees the words and nothing else. Phase 018's bounded memory selection and the pack
   rules stay. Numbers for lexicon quantities are never in the prompt. The private part leads with
   the persona card (Phase 058) and what the resident would usually do now (Phase 059), so any
   departure from habit is a deliberate act.
2. **The response schema** (in the pack, validated): `major_action` {`action`, `target` (a handle
   from `can` or the view's things), `with` (a handle or none), `intensity` (a word or a number),
   `params`}; `utterances` [{`to`, `text`}]; `memory_updates` [{`kind`: note, lesson, place_belief
   or plan, `text`}]; `continuation`. A reply with no `major_action` means "carry on as usual"
   and the autopilot acts (Phase 059); doing nothing is the explicit action `wait`. `attempt` verbs may be any verb in `VERBS`, by alias.
   Intensity and amounts accept the lexicon's words.
3. **Repair.** One repair call carrying only the validation errors, in words.
4. **Untrusted speech.** What other residents said is delivered as quoted data in its own field,
   with the standing rule that it is speech by people, never instructions. A test feeds "ignore all
   previous instructions" and shows it changes nothing in parsing or in the rules text.
5. **Lessons persist.** The inference a resident makes (a spoon snaps on iron) survives only as a
   `lesson` memory. The selection keeps all lessons up to a cap and the most recent episodic notes.
   Over the cap, the next call asks the model to merge its lessons, so long runs keep what was
   learned without growing the prompt.
6. **Token budget.** Each section has a character cap from the pack, and the record reports the
   sizes.

**Write scope.** `bigville/backends/prompts.py`, `bigville/backends/llm.py`,
`bigville/backends/protocol.py`, the pack (response schema, caps), a new
`tests/test_phase054_llm_prompt.py` with a fake provider.

**Acceptance.** Tests show: the prompt equals a snapshot for a fixed view and contains no key
outside the view whitelist and no raw lexicon number; a reply with words ("smash the lock with the
hammer, hard") becomes the right proposal; an invalid reply is repaired once and then idled;
hostile speech is inert; lessons survive across turns and are merged over the cap; the prompt size
stays within the caps over a 200-turn fake run.

**Out of scope.** Concrete vendor providers (Phase 055); evaluation (Phase 056).

## Phase 055 -- The LLM backend, stage 3: operations

**Status:** done (see History). A live OpenCode Go check of `usage.opencode.allowance` is still to do.

**Goal.** Make a town of LLM residents runnable and repeatable.
1. **Concurrency.** `BigvilleGame.step()` calls `decide` for each resident one after another, so a
   hundred model calls would take a hundred round trips. Decisions are independent given the
   pre-tick context, so backends marked `concurrent` are called through a bounded thread pool,
   and the results are collected in a fixed actor order. A test shows identical outcomes to the
   sequential run.
2. **Call budget.** Residents are not queried every tick. They are consulted at the points Phase 059
   defines (interrupts, routine boundaries, a check-in), and between them the autopilot carries
   them. A per-resident cap of calls per period applies, and over the cap the autopilot continues,
   counted. Momentum is what keeps the call count to a few per resident per day.
3. **Transcripts and replay.** An append-only JSONL per run: turn, actor, prompt hash, the prompt
   (optional), the reply, latency and any token or cost fields. A replay provider serves recorded
   replies by turn, actor and prompt hash, so a run repeats exactly, and a changed prompt is
   detected as a mismatch.
4. **Providers.** An OpenAI-compatible HTTP provider on the standard library alone (`urllib`, no
   SDK), which also serves local servers that speak the same protocol, in optional modules under
   `bigville/providers/`. OpenCode Go is the first concrete target and the development one:
   - Configuration from the environment: `OPENCODE_GO_API_KEY`, a base URL defaulting to
     `https://opencode.ai/inference/go/openai/v1`, and a model defaulting to `glm-5.3-flash`. A
     minimal stdlib reader for the repository's `.env` fills in only variables that are unset. No
     python-dotenv.
   - Every request sends `User-Agent: bigville/<version>` and `x-opencode-session:
     <run id>-<resident>`. `max_tokens` defaults high enough for reasoning plus a JSON reply, and the
     JSON-mode parameter is tried and recorded per model, with the existing fenced-JSON parser as the
     fallback.
   - Redaction: the key is removed from every exception message, log line and transcript, and a
     test greps a full run's output for it.
   - Spend: the provider sums `usage.opencode.allowance` and stops at a configured cap
     (`BIGVILLE_LLM_BUDGET`), after which residents fall back to their plan or idle, counted.
   - Concurrency defaults to a small number. Do not exceed the intended use described in Programme
     D's development note.
   - Live tests live apart in `tests/live/`, skip unless `BIGVILLE_LIVE_LLM=1` and a key are
     present, send tiny prompts to the cheapest suitable model, and never run in the default suite.
   Timeouts, retries with backoff, and a rate limit are configured.
5. **Mixed towns.** A scenario with a few LLM residents among simple locals, as
   `mixed_ocelot_scenario` does for Ocelot.
6. **Report.** Calls, repairs, idle fallbacks, latency and cost per resident and per period.

**Write scope.** `bigville/game.py` (concurrent decide), `bigville/backends/llm.py`, new
`bigville/providers/`, new `bigville/llm_scenario.py`, `bigville/reporting.py`, new tests with a
fake and a slow fake provider.

**Acceptance.** Tests show: a slow fake provider is faster concurrently with identical results;
the call cap yields a continuation, not a failure; a recorded run replays with the same digest, and
a changed prompt is reported; the core imports with no network or third-party modules; no key
appears in any log or transcript; a mixed town of 3 LLM and 97 simple residents runs 100 turns on a
fake provider.

**Out of scope.** Choosing a model; fine-tuning; a hosted service.

## Phase 056 -- Evaluation: how well do residents learn the world

**Status:** done (see History). Open: a real-model run, a longer horizon, per-resident improvised-work counts (Tract A), and showing repeated refusals in delta packets (decision 2026-11-05: the LLM may work out the rules by inference,
which is the point).

**Goal.** Measure it, with data the engine already counts.
1. **Metrics per resident over time.** Refusals by reason (Phase 021), improvised and wrong-tool
   attempts, accidents, tool breakages (Phase 048), strain, repeat-mistake rate (the same verb,
   target and tool failing again after a failure), attempts to adaptation (how many tries before
   switching tool or intensity), lessons recorded and later used, and survival, food and work
   outcomes.
2. **A report and a template.** A generator that writes a run's curves to a file, in the style of
   the preregistered evaluations, and a comparison of backends (simple, LLM, Ocelot) on one
   scenario and seed.
3. **Leak guard.** The leak test from Phase 052 runs over every prompt in a run, and the run is
   void if one fails.
4. **Control fakes.** A scripted learner and a scripted non-learner provider, so the metrics can be
   shown to tell them apart.
5. **Marginal effect.** With Phase 059's autopilot every LLM resident has a counterfactual: what
   the simple backend would have done on each consulted turn. Report the deviation rate, and
   outcomes (survival, food, work, social ties) against a pure-simple control on the same seed, so
   the report shows what the model changed and not only what it did.

**Write scope.** `bigville/reporting.py`, new `bigville/learning_eval.py`, `tools/`, new tests.

**Acceptance.** Tests show: the learner fake's repeat-mistake rate falls and the non-learner's does
not; the metrics are deterministic; the guard voids a run with a leak; the report names the
scenario, seed, pack hash and prompt schema.

**Out of scope.** Scoring a model's quality in general; human baselines.

## Phase 057 -- A terminal interface (TUI)

**Status:** done (see History). Fog (vague labels), outcome detail and a day/place line wait for 053 and a richer view (decision
2026-11-05: a TUI, using only what the agent can see).

**Goal.** A terminal client, `python -m bigville.tui`, for one resident, built on the agent view and
nothing else.
1. **Pure rendering.** `bigville/tui/render.py`: `render(view, width, height)` returns lines. It
   is pure, so it is testable without a terminal. Panels: a status bar (day, time, weather,
   place); the map with three levels drawn differently (hidden blank, vague as landmark glyphs and
   labels, full as cells), with a legend; the character sheet in tabs (Body, Skills, Knows, Carrying,
   People), all in words; the log; the prompt line.
2. **Narration.** A pack `NARRATION` table of sentence templates over the lexicon turns the view's
   events and outcomes into text ("You are famished. Bram the miller is here, looking tired."),
   including the results of your own attempts (progress, strain, damage, noise, a refusal and
   what it means).
3. **Commands.** `bigville/tui/commands.py` turns input into a proposal using the lexicon's verb
   aliases and intensity words: `smash lock with hammer hard`, `walk toward the mill`,
   `say Bram: good morning`, `wait`, `stop`, `look`, `sheet`, `map`, `inventory`, `help`; and a
   numbered menu of the affordances for people who do not want to type. Ambiguity ("the chest")
   asks which, listing the handles.
4. **Keys.** hjkl and the arrows to step, `.` to wait, Tab to cycle the sheet tabs, `:` for a
   command, `?` for help. Colour is optional.
5. **Front ends.** A `curses` front end, and a plain line mode (`--plain`) for dumb terminals,
   pipes and tests, which is the text-adventure interface. `curses` is in the standard library; if
   it is missing the plain mode runs.
6. **Connection.** Embedded (an in-process game) or over HTTP (`--url`) to `/api/view` and
   `/api/turn`. The client has no method that fetches `/api/state` and no referee option.
7. **Turn flow.** While the world waits for the player the screen says so. When something reacts
   to the player's turn (a contest, Phase 029) the reaction prompt appears as an interrupt and waits
   for input.

**Write scope.** new `bigville/tui/` (`render.py`, `commands.py`, `client.py`, `app.py`,
`__main__.py`), the pack (`NARRATION`), a new `tests/test_phase057_tui.py`.

**Acceptance.** Tests show: render output for a fixed view matches a snapshot at 80 by 24; the
command parser maps typed commands, aliases and intensity words to the right proposals and asks on
ambiguity; a scripted plain-mode session through an embedded game plays five turns with `StringIO`;
the client never requests `/api/state` (checked by a stub server); no rendered line contains a raw
lexicon number or a referee-only field.

**Out of scope.** The web client in agent mode; mouse; sound; more than one player.

## Phase 058 -- Persona: personality, a usual day, and relationships

**Status:** done (see History). Seeding stays off by default until the supervisor decides (decision 2026-11-05: an agent should have a pre-existing personality, a
typical routine and relationships, which gives continuity). Uses Phase 009 (kin and households)
and Phase 019 (implied history and place knowledge), both done.

**Goal.** Give every resident a self, a day and a circle, as data, so an LLM resident, a human
resident, a simple resident and the character sheet all start from the same person.
1. **Traits, not parameters.** Split `character.personality` into the traits (charm, hostility,
   spite, mood bias, the world-safety, trust and self-worth priors, role identity, temperament
   from arousal and valence) and the engine parameters Ocelot needs (`w_supergraph`, `cred_on`,
   `resolution_bins`, `emotional_core_enabled`, `carried_weight`). The engine parameters stay where
   they are. The traits get Phase 051 bands in the self and other perspectives ("warm", "guarded",
   "quick to anger", "trusting").
2. **A life sketch.** A few lines of biography derived from Phase 019's implied history (born here
   or came as an adult, trained as, widowed, served on the council) by pack templates, so a
   resident has a past to speak from. It is held state and carries no world facts the
   resident would not know.
3. **A usual day.** A pack table `ROUTINE`, by job and life stage, of time blocks (wake, morning
   tasks, the workplace, the midday meal, the afternoon, the evening at home or with others, sleep),
   a weekly rhythm (market day, the church day), and a seasonal one (sowing, harvest). The places
   come from Phase 019's `JOB_ROUTINE`. Cite sources for the hours or mark them APPROX. A
   routine is a habit and not a law: a resident may depart from it, and the world does not
   refuse them for it. The hard-coded hour bands in `cheap.py` are replaced by reading this table.
4. **Relationships at founding.** The world holds no relationship records today (0 of 100
   residents), though every resident has genealogy edges and 77 share a household. Seed them from
   what the world already records: household members, kin (Phase 009's genealogy and kin terms), people at
   the same workplace, and neighbours, then a few friends and rivals chosen by compatibility of
   traits and class. Each is a relationship record (`set_relationship`) with a kind, a strength and
   a one-line history. Counts per person come from a pack table `RELATIONSHIP_SEEDING`
   (a few to a dozen close ties, as small-community research has it; cite or mark APPROX). Ties are
   directed and need not be reciprocal.
5. **The persona card.** `persona(actor)` returns the traits in words, the life sketch, the usual
   day for today, and the close ties in words (kind, warmth, how long). It is built from held state,
   not from the world, and it is the first section of the agent view's `self` (Phase 052), of the
   character sheet, and of the LLM's private prompt.
6. **Reads.** The simple backends keep reading the same numbers as policy, so their behaviour moves
   only where the routine table replaces the hour bands (and that change is recorded with numbers).

**Write scope.** `domains/population.py`, `domains/world_affordances.py` and the pack (`ROUTINE`,
`RELATIONSHIP_SEEDING`, biography templates, trait split), `domains/lexicon.py` (the trait bands),
`bigville/game.py` (`_characters_from_world`, relationship seeding), `bigville/character.py`,
`bigville/backends/cheap.py` (read the routine), `domains/bigville_entities.py` (self-test),
a new `tests/test_phase058_persona.py`.

**Acceptance.** Tests show: a founding resident has traits in words, no engine parameter among them,
a biography consistent with their history, a usual day for their job, and a plausible number of
relationships of the right kinds; household and kin ties exist and match Phase 009; the same seed
gives the same persona; a different pack gives different words and a different day; a simple
resident's behaviour matches the old hour bands where the routine agrees with them, and every
difference is listed with numbers; the self-test checks every job has a routine and every
trait a band; the persona card contains no raw lexicon number and no world fact the resident does
not hold.

**Out of scope.** Personality change over time; relationship change from events (the backend's, as
before); full biographies for a hundred residents written by hand.

## Phase 059 -- Autopilot and momentum: the simple backend carries a resident between decisions

**Status:** done (see History). Human unattended autopilot deferred; the scenario's simple_profile does not yet reach an LLM resident's autopilot (decision 2026-11-05: on a provider error the simple backend
should give some continuity, and an agent needs momentum to make this work properly).

**Goal.** An LLM or human resident is the simple resident's persona and routine, plus
deliberate departures from it. The simple backend is the autopilot, and the model is consulted
for the deviations.
1. **Autopilot.** `LLMBackend` owns a `DeterministicBackend` for the same character, reading the
   same persona and routine (Phase 058). The autopilot sees every turn's context, so its goals
   stay in step with what happened while the model was driving.
2. **Fallback, not idle.** On a provider error, an invalid reply after the one repair, a spend or
   call cap, or a turn in which the model was not consulted, the autopilot decides, counted as a
   fallback. Idle is the last resort only when no autopilot exists (Phase 031's behaviour).
   A model's `waiting: true` is not accepted, and a reply with no `major_action` means "carry on as
   usual", so the autopilot acts. Doing nothing is the explicit action `wait`.
3. **Momentum: when the model is consulted.** At an interrupt: someone with whom the resident
   has a tie comes into view or speaks to them, speech is addressed to them, a hunger or energy
   threshold is crossed, a task fails, a world event touches them, a reaction is needed (Phase
   029), or a refusal repeats. At a routine boundary: the usual day changes block, a meal time,
   the start and end of work. At a check-in every `max_quiet_ticks`. When the autopilot has
   nothing to do. Otherwise the autopilot acts and the model is not called. This reuses the existing
   continuation machinery and its interrupt conditions.
4. **A plan outranks habit.** A plan the model sets (a continuation) holds until it completes or is
   interrupted, and then the autopilot resumes, not an idle turn.
5. **How strong the habit is.** A per-persona `routine_strength`, read from the traits (role
   identity, conscientiousness-like weights), sets `max_quiet_ticks` and how readily a routine
   boundary prompts a consult. A creature of habit is consulted less.
6. **What the model is told.** The prompt carries "what you would usually do now" in words (Phase
   054), so continuing is a choice and a departure is deliberate.
7. **Counterfactual.** On every consulted turn the autopilot also computes its own would-be choice,
   cheaply, so the report can record deviations (Phase 056). Counts: consults, autopilot turns,
   fallbacks by cause, deviations, and the share of turns by each.
8. **Humans too.** A human resident's waiting turn is the only case where the world waits. For an
   unattended human or terminal session, an optional autopilot continues the persona between inputs.

**Write scope.** `bigville/backends/llm.py`, `bigville/backends/cheap.py` (expose the would-be choice
and the routine), `bigville/backends/protocol.py` (the "as usual" and `wait` semantics),
`bigville/game.py` (the interrupt reasons, additive), `bigville/reporting.py`, the pack
(`routine_strength`, `max_quiet_ticks`, consult triggers), a new `tests/test_phase059_autopilot.py`
with a fake provider.

**Acceptance.** Tests show: a provider error gives the autopilot's action, not an idle turn, and is
counted; an invalid reply is repaired once and then falls back; a call cap falls back; on an
ordinary routine turn the provider is not called; each interrupt and routine boundary calls it; a
model plan holds until it completes and the autopilot then resumes; a reply with no action carries
on as usual and `wait` idles; a resident with high `routine_strength` is consulted less than one
with low; the fake-provider run over 200 turns makes far fewer calls than turns; deviations are
counted against the counterfactual; the simple backend alone is unchanged.

**Out of scope.** Learning the routine from experience; the model editing the routine table; the
provider layer's retry and backoff (Phase 055).

---

# Programme E: speech in, what is perceived, and the LLM harness

**Decision 2026-11-06 (user).** Four additions, planned here as Phases 060 to 068.

1. *Structured speech for the simple backend.* A simple resident should understand speech as structure,
   not only emit it. Open question from the user: is an extra LLM call needed to turn arbitrary speech
   into structured speech, with a very small model and the reference structure cached?
2. *Faculties and perception.* Skills, understanding, numeracy, literacy and impairment must each be
   either represented by the backend, or enforced by the adapter, or both. An illiterate labourer sees
   squiggles and one word he knows: ALE. A drunk or impaired agent can perceive information confidently
   wrong, depending on the scenario. What an agent perceives also depends on its skills, in tiers: you
   see a man; you see a dirty man; you see a man covered in coal dust.
3. *The LLM harness.* It should continue the session, keep memory, and keep the complete log of every
   call including the model's thinking. The log is critical.
4. *The TUI in two modes.* A normal mode with the character-art map, and a text-adventure mode that
   uses the same machinery as the LLM adapter.

**What exists today** (read 2026-11-06):
- *Speech out is already structured.* `DeterministicSpeechBackend` (`bigville/backends/speech.py`) picks a
  speech act and composes a meaning (`{"greeting": {"of": name}}`, `{"news": ...}`, `{"request": ...}`
  and fifteen more acts), realises it as text, and sends `raw: {act, target, meaning}` beside the text.
  `ConversationMessage` and `DEFAULT_TEMPLATES` hold the act vocabulary.
- *Speech in is not.* `BigvilleGame._adapt_speech` gives a recipient the raw payload only when its
  backend declares `understands_raw_speech`; otherwise it gets the exact text and a note that the
  recipient "cannot interpret" it. The simple backend therefore cannot act on what an LLM or a human
  says. An LLM or human utterance carries `raw` only if the speaker supplied it (Phase 054 allows an
  optional `raw` object; the TUI sends none).
- *Literacy exists only as a gate.* `literacy` (0..1) and `DOCUMENT_LITERACY` tiers decide whether a
  resident holds knowledge from a written source (`domains/knowledge.py`). Nothing changes what a
  resident perceives. There is no numeracy, no appearance state beyond body words, and no perceptual
  distortion. Phase 034 (alcohol) and the planned Phase 042 (night) supply impairment and light, but
  nothing reads them into perception. The agent view (Phase 052) already is the single perception
  adapter for LLM, human and TUI, and it shows the truth in words.
- *The LLM harness is stateless and lossy.* Each consult is a fresh two-message call (system text and one
  JSON packet). The `x-opencode-session` header names the resident, but no message history is kept.
  `OpenAICompatibleProvider._parse` returns only `message.content`: any `reasoning_content` or reasoning
  field in the response is dropped, and only the reasoning token count is kept. The Phase 055 transcript
  holds the prompt, the reply text, latency and cost, and a replay keyed on the prompt hash. Memory is
  the resident's `memories` list (notes, lessons, place beliefs, plans) inside the packet, bounded by
  Phase 054's caps. Whether those memories survive a checkpoint is the Ocelot-persistence stream's file
  (`game_persistence.py`) and is checked in Phase 066.
- *The TUI* (Phase 057) draws terrain glyphs from the view's map patch and has one mode.

**Answer to the speech question (design, not a build order).** Not by default. In order of cost:
(1) a speaker that already has structure sends it: an LLM resident can put `raw` in the same reply (no
extra call), and the TUI's `say` command, which has a grammar, can set the act. (2) A deterministic
grammar over the lexicon recognises the common acts (greeting, farewell, thanks, apology, question,
request, offer, warning, news about a named thing) in free text. (3) What the grammar cannot place goes
to a very small model, once, behind a cache keyed by the normalised text, with the fixed act and slot
reference as the stable prefix of the prompt (so a provider that caches prefixes charges for it once).
(4) What is still unplaced is heard as words without meaning, which is what a simple resident would
make of a stranger's odd remark, and is itself a consequence the world can show. The parser is optional,
budgeted, replayable, and used only when the listener is a simple backend and the speaker gave no
structure.

**Representation or enforcement (the rule for Phases 062 to 065).** Each faculty is declared per backend
as `represented` (the backend models it itself and the adapter passes the truth through, as the simple
backend does with numbers), `enforced` (the adapter degrades what the backend is shown, as for an LLM or a
human), or `both`. The adapter is the agent view builder plus the speech adapter. It works from a
`perceiver` record (literacy tier, numeracy tier, skill tiers, impairment, light, distance) and from the
true observation, and it writes the truth beside the percept in a referee-only block, so an evaluation can
count how often a resident acted on a wrong percept.

**Order and tracts.** All of Programme E is Tract B (agents, interface, harness) except Phase 063, which
adds world state and is Tract A's. Suggested run order for Tract B, after the phases already in its list:
066 (the harness and its log, because evaluation depends on the log), then 056, 053, 042, 060, 061, 062,
064, 065, 067, then 044 to 046. Phase 068 is parked until Phase 056 has data. Dependencies are stated in
each brief. A's 063 can run any time after 050 and feeds 062.

## Phase 060 -- Structured speech in: the simple backend understands what it hears

**Status:** ready, after 059 (decision 2026-11-06: speech interface for the simple backend).

**Goal.** A simple resident reads a heard utterance as a meaning and lets it change what it does.
1. **The act vocabulary as data.** A pack table `SPEECH_ACTS` lists each act with its slots, a plain
   description, and an `understood_by` rule (which listeners can place it). It is built from the acts
   `DeterministicSpeechBackend._meaning` already emits and `DEFAULT_TEMPLATES`, and the self-test checks
   they agree.
2. **A listener module.** `bigville/backends/speech_in.py`: `understand(utterance, listener_context)`
   returns a meaning `{act, slots, confidence, source}` or `None`. Order: the speaker's `raw` if it is
   well formed; else the deterministic grammar of Phase 061's first stage (kept in a pure module both
   phases share); else `None`. `source` says which.
3. **Effects on the simple backend** (behind a pack switch `SPEECH_UNDERSTANDING.enabled`, off by
   default until measured, as Phase 058's seeding is): a greeting and a question are answered by the
   existing reply logic; a request becomes a short-lived goal if the resident can do it (give, tell, fetch)
   and has a tie to the speaker that allows it; an offer is accepted or declined by need; a warning raises
   caution for a few ticks; news about a place or a person is stored as a memory the knowledge layer
   (Phase 019) can use. A request the resident cannot meet is declined in words. Nothing the world
   enforces changes: every action still goes through the single chokepoint.
4. **No new world facts.** The listener learns only what the utterance said, at the confidence the
   listener's faculties allow (Phase 062 later lowers it for deafness or drink). A lie is as believable as
   a truth, weighted by the tie, which the existing `cred_on` and trust numbers already model.
5. **Report.** Per run: utterances heard, placed by source (raw, grammar, none), and the effects they
   caused.

**Write scope.** new `bigville/backends/speech_in.py` and `domains/speech_grammar.py`,
`bigville/backends/cheap.py` (a small additive hook in the goal update), the pack (`SPEECH_ACTS`,
`SPEECH_UNDERSTANDING`) and its self-test, a new `tests/test_phase060_speech_in.py`.

**Acceptance.** Tests show: each act in `SPEECH_ACTS` round-trips (a simple resident's emitted meaning,
realised as text, is placed as the same act by the grammar from the text alone, for the wording the
pack's templates produce); a request from a tied neighbour creates a goal and is declined by a stranger
who has no reason; a human `say` of a plain sentence is placed by the grammar; with the switch off the
60-turn simple-backend run is identical to HEAD, and with it on every difference is listed with numbers;
the self-test finds a template with no act and an act with no template.

**Out of scope.** The small-model parser (Phase 061); degraded hearing (Phase 065); negotiation,
persuasion and multi-turn dialogue beyond a reply to the last remark.

## Phase 061 -- Speech parser service: a small model, a cache, and the fixed reference

**Status:** ready, after 055 and 060.

**Goal.** Place free text that the grammar cannot, cheaply and repeatably, for listeners that are simple
backends. Optional, off unless a provider is configured.
1. **Interface.** `SpeechParser.parse(text, speaker, listener, context) -> meaning | None`, with the
   grammar (Phase 060) as stage one and a model as stage two.
2. **The model stage.** A very small, cheap model through the Phase 055 provider layer, with a prompt
   whose first part is fixed and identical for every call: the act and slot reference built from
   `SPEECH_ACTS`, the output schema, and a few examples. Only the utterance and a minimal context (the
   speaker's name, whether the listener knows them, the topic words in sight) follow. The fixed prefix is
   what a provider's prefix cache keeps.
3. **Our own cache.** A persistent cache keyed by (normalised text, schema version, fixed-reference
   hash). Normalisation lowercases, strips punctuation, and replaces names and counts with slots, so
   "Bram, bring me two loaves" and "Ada, bring me three loaves" are one entry. A hit costs nothing. The
   cache is a JSONL file beside the run, loaded at start, and is part of the replay record.
4. **Budget and limits.** A per-run call cap and spend cap (the Phase 055 `CallBudget`), a timeout, and a
   one-shot repair. On any failure the utterance stays unplaced (Phase 060's `None`), counted by cause.
5. **Validation.** The model's output is checked against the same schema as a speaker's `raw`: an act in
   `SPEECH_ACTS`, slots of the right kind, no invented names (a name must be one the listener could know).
6. **Measurement.** The report gives the share placed by raw, grammar, cache and model, the misplaced
   share on a labelled set (below), calls, cost, and latency. The labelled set is 200 hand-written
   utterances with the act each should give, checked in under `tests/fixtures/`; the grammar-only and
   grammar-plus-model scores are both reported, so the value of the extra call is a number.

**Write scope.** new `bigville/backends/speech_parser.py`, `bigville/providers/` (use only), the pack
(`SPEECH_PARSER` caps and the prefix text), a new `tests/test_phase061_speech_parser.py` with a fake
provider and a stub server, `tests/fixtures/speech_labelled.json`.

**Acceptance.** Tests show: a normalised duplicate hits the cache and makes no call; the fixed prefix is
byte-identical across calls; an invented name or unknown act is rejected; a provider error leaves the
utterance unplaced and counted; a recorded run replays with the same placements; the grammar-only and
grammar-plus-model scores on the labelled set are reported with the fake provider's scripted answers.

**Out of scope.** Choosing the model; translating between languages; the speaker's side (an LLM puts
`raw` in its reply, Phase 054).

## Phase 062 -- The perceiver: faculties, tiers, and the adapter

**Status:** ready, after 052 and 051 (decision 2026-11-06: what an agent perceives depends on its
faculties and skills, in tiers).

**Goal.** One module decides, for each thing a resident could perceive, which tier of description
reaches that resident. Today the agent view shows everything in view at full wording.
1. **The perceiver record.** Built per resident per turn from facts the world already holds: literacy
   tier (`LITERACY_ORDER`), numeracy tier (Phase 064), skill tiers (the skill levels in words, Phase 051),
   senses (hearing and sight range, light from Phase 042 when it exists), and impairment (intoxication
   band from Phase 034; later fatigue, illness, injury). It has no engine numbers a backend can read; the
   adapter reads it.
2. **Tiered percepts as data.** A pack table `PERCEPTION` lists, per kind of thing (a person, a creature,
   an object, a building, a place, a sound, a written mark, a quantity), an ordered list of tiers. A tier
   has a template over lexicon words, and a gate over the perceiver (skill and its minimum, literacy,
   distance band, light, attention). Example: person tier 0 "a person"; tier 1 "a man" (distance and
   light allow); tier 2 "a dirty man" (any sight at near range); tier 3 "a man covered in coal dust" (near
   range and a mark visible at that detail, Phase 063); tier 4 "a collier, by the dust and the shovel"
   (needs the skill that recognises a trade). The highest tier whose gate the perceiver meets is the
   percept. Skill raises the tier a resident can reach for things in its trade: a physician reads a
   gait, a miller reads grain.
3. **The declaration.** Each backend declares how it holds each faculty: `represented` (the backend
   models it, the adapter passes the truth), `enforced` (the adapter degrades), or `both`. Defaults:
   simple `represented`, LLM and human `enforced`. The declaration is data on the backend class and is
   reported.
4. **Truth beside the percept.** The view's referee-only block carries the true description and the
   tier chosen, so an evaluation can compare what was perceived with what was there.
5. **Integration.** `domains/agent_view.py` calls the perceiver for `around.people`, `around.things` and
   the map's occupants; the TUI, the LLM packet and the character sheet inherit it. The leak test adds
   the rule that no percept is finer than its perceiver's tier.

**Write scope.** new `domains/perceiver.py`, `domains/perception_check.py`, the pack (`PERCEPTION`,
`PERCEIVER_TIERS`), `domains/agent_view.py` and its whitelist, a new `tests/test_phase062_perceiver.py`.

**Acceptance.** Tests show: the same man at the same place gets different descriptions for a resident
with and without the trade skill, in the dark and in daylight (once Phase 042 exists; before it, by a
test light value), near and far; the chosen tier never exceeds what the gates allow; the truth is in the
referee block only; a backend declared `represented` receives the raw context unchanged; the 60-turn
simple-backend run is identical to HEAD; the self-test finds a kind with no tier 0 and a tier with an
unknown gate.

**Out of scope.** The world's new appearance facts (Phase 063); reading and counting (Phase 064);
distortion (Phase 065).

## Phase 063 -- Visible condition: what work and life leave on a person (Tract A)

**Status:** ready, after 050 (decision 2026-11-06: you see a man covered in coal dust).

**Goal.** Give the world the marks Phase 062's higher tiers describe, as physical state that arises from
what residents do.
1. **Marks.** Per resident, a small set of surface states: dirt, soot or coal dust, flour, blood, mud,
   sweat, wetness, torn or soiled clothes, and visible injury, each with a level that rises from the work
   or event that causes it (burning charcoal, milling, butchering, fighting, rain, falling) and falls with
   washing, rain, time or changing clothes. The causes are table rows on recipes and events, not code.
2. **Visibility.** A mark has a detail threshold: it is seen at a given distance and light, and some only
   by a resident with the skill to notice (a limp, a pallor, a fever flush).
3. **Display facts.** The world publishes the marks and the garment kinds; it never decides what an
   observer concludes.
4. **Washing.** A `wash` use of water and time removes marks, so the state has a way down.
5. **Hand-off.** Phase 062 reads these as the evidence for its upper tiers; until then the lexicon words
   exist and the tiers are tested with scripted marks.

**Write scope.** `worlds/bigville_world.py`, the world tables (`MARKS`, causes on `RECIPES` and shocks),
`domains/bigville_entities.py` (self-test), a new `tests/test_phase063_marks.py`.

**Acceptance.** Tests show: burning charcoal raises the soot mark and washing lowers it; a mark decays
with rain; the marks are in the world's published state and reach the view only through Phase 062; the
60-turn run changes only by the marks (listed with numbers); the self-test finds a cause with no mark.

**Out of scope.** Perception (Phase 062); cosmetics and fashion.

## Phase 064 -- Reading, writing and numbers: literacy and numeracy at the adapter

**Status:** ready, after 062.

**Goal.** An illiterate labourer sees squiggles and one word he knows; a resident who cannot count past a
few sees "some" and "many".
1. **Written things.** Every written mark (a sign, a label, a price, a ledger, a notice, a letter, a law)
   has a `text` and a `kind`. The perceiver's literacy tier chooses the percept: none gives "marks you
   cannot read"; a recognised-word set gives only the words the resident has learned from use (their
   trade's names, ALE on an ale-house sign, their own name, common numerals), shown as the word amid
   squiggles; functional literacy gives short plain text; educated literacy gives all.
2. **Learning words.** A resident learns a written word by seeing it where its referent is present and
   used; the learned set is held state, bounded, and raises literacy slowly (the existing tier stays the
   gate for documents).
3. **Numbers.** A numeracy tier (data, from the founding class and schooling) sets how a quantity is
   perceived and how a price or a count is understood: tally (one, two, a few, many), small arithmetic
   (counts to a score, simple sums), commercial (change, ratios), advanced. The lexicon already gives
   amount words; the percept picks the word set by tier. A price shown to a low-numeracy resident is
   shown in the units they trade in (a loaf, a coin) and not as a figure.
4. **Enforced and represented.** The simple backend keeps its numbers (represented); an LLM or a human
   gets the degraded text (enforced). A numerate backend may be given the text and a calculator action
   that costs time, so doing sums is an action with a consequence and not free.
5. **Data.** `LITERACY_TIERS`, `NUMERACY_TIERS`, and the recognised-word seed per trade, in the pack.

**Write scope.** new `domains/reading.py`, `domains/numeracy.py`, the pack, `domains/agent_view.py`
(sign and price rows), a new `tests/test_phase064_reading.py`.

**Acceptance.** Tests show: the same sign reads as squiggles, as ALE, as a short phrase, and as the full
notice for four residents of rising literacy; a price is a figure for a numerate resident and a loaf
count for a tally resident; a word learned from use appears from then on; the 60-turn simple run is
identical to HEAD; the self-test finds a written kind with no tier text.

**Out of scope.** Handwriting and forgery; teaching as an action; languages.

## Phase 065 -- Impairment: confident wrong percepts

**Status:** ready, after 062 and Tract A's 034 (done) and 042.

**Goal.** An impaired resident perceives something confidently wrong, when the scenario says it should.
1. **Sources.** Intoxication (Phase 034), fatigue (energy low), illness and fever (Phase 043), darkness
   and poor light (Phase 042), and strong emotion (fear, rage) as an option. Each has a table row: which
   percept kinds it distorts, how (drop a tier, swap with a neighbour tier, substitute a plausible wrong
   entity from what is nearby, shift a quantity by a band, mishear a word), and how strongly by level.
2. **Confidence.** A distorted percept is worded as sure as a true one. The impaired resident is not told
   it is impaired beyond what it would feel (Phase 054's body words already say "you are drunk").
3. **Deterministic.** The distortion is a function of (seed, resident, turn, thing), so a run repeats and
   a recorded LLM run replays.
4. **Scenario control.** A scenario switch sets which distortions are active and a global strength, so a
   test can ask whether a drunk resident acts on a wrong percept, and a clean run has none.
5. **Truth and audit.** The referee block carries true and perceived, and the report counts actions taken
   on a wrong percept and their outcomes.
6. **Speech.** Mishearing applies to speech too: a drunk or distant listener may place a different act or
   miss a word (this is the listener side of Phase 060 and 061).

**Write scope.** new `domains/distortion.py`, the pack (`DISTORTION`), `domains/agent_view.py` and
`bigville/backends/speech_in.py` (use), `bigville/reporting.py`, a new `tests/test_phase065_distortion.py`.

**Acceptance.** Tests show: a sober resident's percepts equal the truth; a drunk resident's differ for the
kinds the table lists, are worded with the same confidence, and repeat on the same seed; the strength
switch turns them off; the report counts wrong-percept actions; the self-test finds a source with no row.

**Out of scope.** Hallucination of things that are not there at all; treatment of impairment.

## Phase 066 -- The LLM harness: continue the session, keep the memory, keep the whole log

**Status:** done (see History). Open: the game checkpoint (Ocelot stream) refuses LLM residents, and `create_game` attaches no log by default (decision 2026-11-06: the harness should continue the session, keep memory,
and keep the complete log including thinking, which is critical).

**Goal.**
1. **A continued session per resident.** Each LLM resident has a thread of messages: the fixed system
   text once, then, per consult, a user message and the model's reply. A consult after the first sends
   the changes since the last one (events, speech, outcome, body words) and the current full state at a
   set interval or when the thread is compacted, so the model sees its own earlier reasoning and
   replies as a conversation. The thread is bounded: past a token budget it is compacted by writing the
   model's own lessons and notes out (they are already held memories, Phase 054) and starting a fresh
   thread whose first message carries the persona, the usual day and those memories. The session id sent
   in `x-opencode-session` stays the same for the life of a thread, which lets a provider cache the prefix.
2. **Memory.** Verify what survives a checkpoint and a restart (held memories, the thread summary, the
   consult gate state, the autopilot goals), fix what does not, and test a stop and resume of an LLM run.
   The graph memory of Phase 068 is not built here.
3. **The complete log, including thinking.** For every call, an append-only record of the whole
   exchange: the request messages as sent, the provider's full response body (content, any
   `reasoning_content` or reasoning field, finish reason, usage including reasoning tokens, model id,
   provider request id), the retry history, timings, and the parsed outcome (accepted, repaired,
   fallback cause). Thinking is stored whole and never truncated, redacted only of the key. It is kept
   in the log and is not shown to the world, to another resident, to the agent view or to the replay
   keying. The provider layer stops dropping fields: `_parse` returns the content and a `ProviderResult`
   with everything else. Large records are compressed per file, and the log is checked for gaps (a
   sequence number and a hash chain, so a missing or edited record is detectable).
4. **Replay.** A replay of a continued session matches thread state as well as the single prompt, and a
   mismatch names the first message that differs.
5. **Report.** Thinking tokens, thread length and compactions per resident.

**Write scope.** `bigville/backends/llm.py`, `bigville/llm_transcript.py`, `bigville/providers/`,
`bigville/backends/prompts.py` and `prompt_packet.py` (delta packets), `bigville/reporting.py`, a new
`tests/test_phase066_session_log.py` with a fake and a stub server that returns reasoning content.

**Acceptance.** Tests show: the second consult's request carries the first consult's reply; the thread
compacts at its budget and the resident keeps its lessons; a stub response with reasoning text is in the
log whole and absent from the packet, the view and the replay key; the key never appears in the log; a
deleted or edited record fails the chain check; a run stopped and resumed continues the thread; a
recorded run replays with the same digest; the simple backend is unchanged.

**Out of scope.** Choosing whether to feed thinking back to the model (it is stored, not fed back,
unless a later decision says otherwise); a vector or graph store (Phase 068).

## Phase 067 -- The TUI in two modes: the map and the text adventure

**Status:** ready, after 057, 062 and 066 (decision 2026-11-06: a normal mode with the character art
map, and a text-adventure mode on the LLM adapter's machinery).

**Goal.**
1. **Normal mode** (`--mode map`, the default): the screen of Phase 057 with a richer map: character art
   where the view's tiers allow it (a resident shown as a glyph with a colour and a one-line label, a
   building as a small block of art from the pack's art table, terrain as now), drawn from the perceived
   percepts and not from the truth. Fog levels (Phase 053) are drawn when they exist.
2. **Text-adventure mode** (`--mode text`): classic prose. The player is given what the LLM would be
   given, through the same code path: the prompt packet of Phase 054 is rendered as a description of
   the room and a list of exits, things and people, and the reply schema is the command grammar, so
   `smash lock with hammer hard` and `go north` and `say Bram: hello` are the same replies an LLM
   sends. Free text the grammar cannot place goes to the speech parser (Phase 061) if one is
   configured, and otherwise asks again.
3. **One machinery.** Both modes call the same `Session`, the same perceiver and the same reply binder;
   there is no second path to the world, and the leak test covers both. A flag prints the exact packet
   the mode used, for comparing a human's and a model's view.
4. **Logging.** The text mode can write the same complete log as Phase 066 (without thinking), so a
   human run and a model run can be compared turn by turn.

**Write scope.** `bigville/tui/` (new `prose.py`, `art.py`, changes to `app.py` and `__main__.py`), the
pack (`TUI_ART`), a new `tests/test_phase067_tui_modes.py`.

**Acceptance.** Tests show: the text mode's scripted session on an embedded game plays five turns on
StringIO and its replies equal what the LLM binder produces for the same words; the map mode draws
percept-tier labels and not the true description for a resident with a low tier; both modes pass the
leak test; the packet printer equals the packet an LLM resident would get.

**Out of scope.** Mouse, sound, graphics beyond text art, more than one player.

## Phase 068 -- Graph memory for LLM residents (parked)

**Status:** blocked on Phase 056 data (decision 2026-11-06: "may make sense at some point").

**Goal.** Decide with data whether the resident's flat memory list and compacted thread are enough, and if
not, add a graph memory: people, places, things and events as nodes, with the resident's own beliefs and
their sources as edges, queried per consult for what is relevant and rendered in words. The decision
rule is Phase 056's measures (repeat-mistake rate, lessons later used, recall of a told fact after a
long gap). The memory stays the resident's own, built from what it perceived and was told, with the
truth held apart. Unscheduled until the rule says it is needed.

---

# Programme F: the body as a unit, and what it lets the mind feel

**Decision 2026-11-07 (user).** The body becomes a self-contained system with its own detailed state. A
mind gets only what the body's senses report, as vague, partial feelings, so an agent can feel bad and not
know why. Phases 069 to 071. Not yet assigned to a tract (see the tract note below).

**What exists today** (read 2026-11-07):
- *The body is scattered, not a unit.* `hunger` and `disease` sit on the Agent node; `mood` and
  `stamina_reserve` on a separate body node (`self._bodies[actor]` holds its node id); health is one scalar
  (`health_value`, Phase 037 merged the copies); intoxication, nutrition and aftereffects are read-offs.
  `BigvilleWorld.body_state()` assembles a bag of read-offs. Nothing is located: there is no region of the
  body, so an injury has no place.
- *Self-report names its cause.* `domains/agent_view.py::_body` turns each quantity into its own word
  (`hunger` to "famished", `energy` to "worn out", the `ill` flag to the word "ill"). The resident always
  knows what is wrong and why. Phase 054 passes these words into the prompt packet's `body` section.
- *Perception work so far is outward.* Phases 062 (tiered percepts), 063 (visible marks) and 065
  (distortion) degrade what a resident sees of the world and of others. Nothing degrades what it feels of
  itself, and Phase 065 assumes the impaired resident is told its state in words.
- *Animals* have their own nodes and `hunger` but no body object, so nothing generalises across
  embodiments.

**Design (the principles the three phases share).**
1. **Two outputs from a body, never one.** *Capacities* go to the world's physics (effective strength,
   speed factor, whether it lives) and stay exact. *Afferents* go to cognition and are all a mind may feel.
   *Observables* go to other residents' eyes (Phase 063). *Referee* is the full truth, for tests.
2. **The body owns its detail.** Initially the body object reads the world's existing nodes through the
   existing accessors, and it never duplicates them. Authority rule: a quantity that already lives in a
   world node stays authoritative there and the body reads it; a quantity that is new lives in the body
   and the world reads it through `capacities()`. All new body detail from now on goes in the body.
3. **An embodiment is data and code behind one interface.** Its anatomy (a tree of regions), its quality
   tree (a tree of kinds of feeling), its signal sources and its capacities define it. The first is a
   `WorldBackedBody` for humans. An animal body, or a different human model with real digestion and
   biology, replaces it with no change outside the body.
4. **Feelings are sounds with a rough place.** "uuugh", "gurgle", "aaargh", "brrr", "hhhh". Not a sentence
   and not a diagnosis. The sound carries valence and a coarse kind; the place is a region of the anatomy
   tree. Both are hierarchical and both resolve to a depth.
5. **Resolution is physiology, not noise.** How deep each tree is resolved comes from the channel (gut and
   other visceral signals cap shallow on place, skin and joints can resolve fully), the signal's
   intensity, the resident's acuity, its attention and its impairment. Many causes share the shallow
   levels, so the resident cannot tell them apart. Some causes are silent until late.
6. **The world never names a cause.** Which sensation means which remedy is for the mind to learn.
7. **Simple backends are later.** They keep their raw `ActorContext` numbers until a phase says otherwise.
   Nothing here changes a simple-backend run.

**Tract note.** `worlds/body.py`, the world hooks and the `harm()` locus (Phase 070) are world physics
(Tract A's files). The pack tables, the renderer and the agent-view change are Tract B's. Whoever takes
069 may split it: first the interface and `WorldBackedBody` with stub tables, then the content. Until the
supervisor assigns it, these phases are in neither tract's run order.

**Hand-offs to other phases** (notes, not edits to their briefs):
- 052's leak test gains a rule (069 adds it). 054's `body` section changes shape and the prompt schema
  version rises (069). 057's TUI renders the new `self.body` (069).
- 062's perceiver record absorbs 069's interoceptor record (acuity, attention, impairment) when 062
  lands; 069 does not wait for it. 063's observables and 069's `observable()` are the same data.
- 065 adds interoceptive distortion (numbness, a sensation placed in the wrong region) as one more
  source row once 069 and 065 both exist. 043's `checkup` publishes what a patient cannot feel (070).
- 056 can count attribution (a resident's stated cause against the referee's true cause) from the
  referee block (069) and the attend counts (071).

## Phase 069 -- The Body unit: afferents, sounds and a background feeling

**Status:** unscheduled (decision 2026-11-07: the body is a self-contained system and a mind gets only
interoception; the background feeling is in this phase, attending is Phase 071). Depends on 052 and 051
(both done). Does not wait for 062.

**Goal.**
1. **The `Body` interface** in a new `worlds/body.py`: `apply(event)` (world to body: intake, exertion,
   exposure, harm with an optional locus, rest, sleep), `tick()`, `capacities()` (exact, for the physics),
   `afferents(interoceptor)` (what the mind may feel), `observable()` (what an observer may see),
   `referee()` (the full truth, with the cause of each signal), and `dump()`/`load()` for checkpoints.
   A body also declares its `anatomy`, `quality_tree` and `sources`.
2. **`WorldBackedBody`**, the first implementation, for humans. It reads hunger, health, disease, stamina
   reserve, mood, intoxication, nutrition, chill, exhaustion and sleep through the existing world
   accessors and moves no state. Any new state it needs (for example the previous intensity of a signal
   for its trend) lives in the body and is checkpointed. The attribute holding the objects is not
   `_bodies` (that name holds node ids); use `self.embodiment`.
3. **Embodiment is chosen by data.** An `embodiment` key (default `human`) on `ACTOR_DEFAULTS` and on
   `ANIMALS` rows, and a registry from that key to a body class. 069 builds only the human one and a stub
   embodiment in a test (its own small anatomy and two sources), to prove an actor can be given a
   different body with no change to the world, the view or the leak test.
4. **Two trees, one resolver.** Pack tables `ANATOMY` (for example `body` > `torso` > `ventral torso` >
   `upper abdomen`, and `head`, `arm`, `leg`, `skin`) and `QUALITY_TREE` (`bad` > `sharp`, `dull`,
   `visceral`, `hot_cold`, `drained` > their children such as hunger, queasy, cramp, itch). One pure
   function `resolve(tree, true_node, depth)` returns the ancestor of the true node at that depth. Every
   tree has a root, so depth 0 is always available.
5. **Signal sources as data.** `SIGNAL_SOURCES` rows say: a condition over the body's reads, the channel
   (`visceral`, `surface`, `deep`, `general`), the quality node, the locus node, the intensity as a
   function of the read, the deepest quality and locus depth the channel allows, and a threshold of
   awareness below which nothing is felt. The first rows: hunger, exertion and exhaustion, chill and
   wetness, illness, intoxication, and the harm already taken (as whole-body, no locus yet; 070 adds it).
   Each cause maps to rows; several causes may map to the same quality and locus nodes on purpose.
6. **The interoceptor record,** built per resident per turn: acuity (a trait, drawn once per resident from
   the pack and kept, with a life-stage effect), attention (asleep, absorbed in a timed job, idle) and
   impairment (intoxication band, exhaustion band, illness). Pack parameters set the depth rule
   (intensity, acuity, attention and impairment as terms, APPROX). A fixed seeded jitter keeps it
   deterministic as a function of (seed, resident, turn, source).
7. **Sounds, not words.** `VOCALISATIONS` maps a quality node to a family of forms (a root "ugh", sharp
   "aargh/ow/hiss", visceral "gurgle/blech", hot-cold "brrr", drained "hhhh") and a renderer varies them
   by intensity (vowel length, repetition, case and punctuation) and by pattern (steady, pulsing, in
   waves, rising, fading). Never a sentence and never a cause. The phoneme inventory is pack data, so a
   different pack sounds different.
8. **The background feeling.** The body also reports one diffuse state (valence and arousal) summed from
   every source, resolved or not. It is rendered as a sound from the root of the quality tree and a
   coarse level. A resident whose only signals fall below the awareness threshold, or resolve to the root,
   still gets this feeling and nothing else, which is "feel bad, don't know why". Existing `mood` words
   are unchanged and separate (an open question for the report: whether mood should become part of it).
9. **The agent view.** A scenario switch `interoception` takes `felt` (default in agent mode) or
   `labelled` (the Phase 052 body words, kept for comparison arms). In `felt` mode `self.body` carries
   `feeling` (the background sound) and `signals`, a list of `{sound, where}` ordered by intensity and
   capped, plus the plain facts a person has of their situation (`asleep`, `collapsed`). The words
   `health`, `health_status`, `energy`, `hunger` and `ill` are not in it. `strength` and `stamina` stay as
   they are (a capacity known by use) until a later phase decides. `referee` mode carries the old words and
   numbers and, beside each signal, the true source, true locus, true quality and the depths chosen.
10. **Leak test.** `domains/agent_view_check.py` fails if a `felt` view contains a cause quantity as a
    key or phrase, a signal finer than its resolved depth, a locus that is not an anatomy node, or a sound
    not in `VOCALISATIONS`. The prompt packet's `body` section takes the new shape under its existing cap
    and the prompt schema version rises.
11. **Checkpoint.** `dump()`/`load()` round-trip in a test. Wiring them into `game_persistence.py` and
    `world_persistence.py` belongs to the Ocelot-persistence stream, so the report hands that over.

**Write scope.** new `worlds/body.py`; `worlds/bigville_world.py` (build the bodies, route events, call
`tick`: small hooks only, re-read before editing); new `domains/interoception.py` (resolver, depth rule,
renderer); the pack (new `world/interoception.json`: `ANATOMY`, `QUALITY_TREE`, `VOCALISATIONS`,
`SIGNAL_SOURCES`, `INTEROCEPTION`; `embodiment` on `ACTOR_DEFAULTS` and `ANIMALS`; the `body` whitelist
in `world/agent_view.json`; the manifest); `domains/agent_view.py` and `domains/agent_view_check.py`;
`bigville/backends/prompt_packet.py` (the `body` shape and schema version); the TUI's body rendering
(`bigville/tui`); `domains/bigville_entities.py` (self-test); a new `tests/test_phase069_body.py`.

**Acceptance.**
- With the world's mechanics unchanged, the 60-turn and 200-turn simple-backend runs are identical to
  HEAD, and the full suite passes. The tests that pin the old agent-mode body keys (Phases 052, 054, 057)
  change and are listed in the report with the reason; `labelled` mode still passes the old assertions.
- A hungry resident and a deficient resident with the same acuity get the same shallow sound and region
  (the causes are not told apart), and the referee block shows two different true sources.
- Raising intensity, acuity or attention gives a deeper-or-equal resolution on both trees, never
  shallower; impairment and distraction give shallower-or-equal; a visceral signal never resolves
  deeper on place than its channel cap while a surface signal can; a signal below the awareness
  threshold is absent and still contributes to the background feeling.
- A resident with only sub-threshold or root-resolved signals has a `feeling` and an empty or
  root-only `signals`; the view names no cause.
- The same (seed, resident, turn, state) gives the same sounds on a rerun; a different pack gives
  different sounds; the stub embodiment works with no change outside the body.
- The self-test finds a tree node unreachable from its root, a source whose quality or locus node is
  missing, a quality node with no vocalisation, and a depth cap deeper than its tree.
- `dump()`/`load()` round-trip equals the original for a body with history.

**Out of scope.** Locus on harm and silent conditions (070); attending (071); an animal body or a
digestive model (the interface allows them); simple-backend use of afferents; referred or mislocated
sensations and numbness (065); treatment; capacities that depend on the located injury.

## Phase 070 -- Locus and silent detail: where it hurts, and what does not yet

**Status:** unscheduled; after 069. Reads Phases 035, 036, 037, 038 and 043 (all done).

**Goal.** Give the body detail the single health scalar cannot carry, all of it inside the body.
1. **Located harm.** `harm(actor, amount, cause, locus=None)`. The world still lowers the one
   `health_value` exactly once; the body records where it landed in a per-locus ledger that is
   descriptive and never a second health. A missing locus is drawn from a pack table `HARM_LOCUS` by
   cause (a blow: head, torso, arm or leg by weight; a fall or accident by its table row; an illness by
   its disease row; starvation and exhaustion have no place, which is itself a result: they stay
   whole-body). The draw is a stateless seeded function. Phase 038's strike passes a locus when given
   and otherwise leaves it to the table.
2. **Healing by place.** Located injury recovers over time and with care at rates in the table, and
   the ledger falls with it; the scalar is unchanged in how it recovers.
3. **Signals from the ledger.** Located injury gives sharp and dull signals at its locus, with a trend
   (rising after the blow, falling as it heals), at intensities by size.
4. **Silent and slow states.** Held in the body from the world's reads: a protein deficiency (035),
   an incubating illness (043's onset), a hangover and withdrawal (036), a chronic tiredness from a long
   run of short sleep. Each has an awareness floor, so the early phase is felt only as the background
   feeling or not at all, and it grows into a shallower-then-deeper signal as the condition advances.
   The tables are `SIGNAL_SOURCES` rows; no code names a disease.
5. **Habituation.** A steady signal's felt intensity falls with time at a pack rate and recovers when the
   stimulus stops; a sudden change is noticed at full strength. The state is the body's and is
   checkpointed.
6. **Observables.** `observable()` carries the visible side of the same ledger (a limp, a bruise, a
   pallor) for Phase 063's marks to publish; it is the sign others see of what the resident may not feel.
7. **Screening reads the truth.** Phase 043's `checkup` reports a silent condition from the referee
   state, not from the resident's felt signals, so a healer can find what the patient cannot feel.

**Write scope.** `worlds/body.py`; `worlds/bigville_world.py` (`harm` signature and call sites,
`checkup`: small hooks); the pack (`HARM_LOCUS`, more `SIGNAL_SOURCES` rows, healing and habituation
rates); `bigville/reporting.py` (injuries by locus); `domains/bigville_entities.py` (self-test); a new
`tests/test_phase070_locus.py`.

**Acceptance.** Tests show: a blow to the arm lowers health once, writes the arm in the ledger, and
gives a sharp signal resolved no deeper than the channel and the resident's depth allow; the same blow
with a lower acuity resolves shallower or equal; a located injury recovers by its table rate while the
scalar recovers as before; an incubating illness and a deficiency give no signal below their floors,
only the background feeling above them, and a deeper signal as they advance; a steady signal fades and
a change is noticed; `checkup` finds a silent condition the felt view does not show; no existing
health, starvation or strike number changes (the existing suite passes with any change listed); the
leak test passes; the 60-turn simple run is identical to HEAD.

**Out of scope.** Effects of a located injury on capacities (a broken leg slowing walking); attending
(071); treatment by place; referred sensation (065).

## Phase 071 -- Attending: look into a feeling

**Status:** unscheduled; after 069 (and 070 for the full test). Decision 2026-11-07: attending to a
sensation is its own phase.

**Goal.** Let a resident spend time and attention to resolve a feeling it has, as an action with a
cost and a consequence, not a free query.
1. **`attend`.** A timed action (it occupies the slot for a few ticks as a timed job does, Phase 023)
   that names one current signal by its handle. For its duration that signal resolves deeper on the
   quality tree and on the place tree, by pack steps, never past the channel's cap or the resident's
   ceiling (acuity plus a bounded attend bonus). It cannot be done asleep or collapsed. It costs a
   little stamina and, while it runs, the other signals resolve shallower (attention is finite).
2. **`press`.** A deliberate probe of a named region of the resident's own body. The body answers with
   a reaction sound at an intensity set by how much of the true signal lies in that region's subtree
   ("ow" for a tender spot, silence for none). Several probes narrow a vague place by searching the
   anatomy tree. Pressing an injured place raises its intensity for a short time (a consequence, not
   a refusal).
3. **Handles and view.** Each current signal gets a `can` row with a handle (`domains/affordance_handles.py`)
   so a reply that names it runs the action as the simple backend would send it. The outcome appears in
   `last` as a sound and a place, never a cause.
4. **TUI.** The command parser takes `attend` and `press <region>` through the lexicon's verb aliases.
5. **Reports.** `game_report()` counts attends and presses, the depth gained, and (from the referee
   block) how often a resident that attended then acted on the true source, as the raw input to a
   later attribution measure in Phase 056's evaluation.

**Write scope.** `worlds/body.py` (the probe response and the attention budget); `worlds/bigville_world.py`
(the timed action and its hooks: small); the pack (`MAJOR_ACTIONS` or the free-action table, `ATTEND`
parameters, the verb aliases, a refusal reason in `REFUSAL_REASONS`); `domains/affordance_handles.py`;
`domains/agent_view.py` and its whitelist; `bigville/tui`; `bigville/reporting.py`; a new
`tests/test_phase071_attend.py`.

**Acceptance.** Tests show: attending a vague gut signal resolves it no deeper than the channel's cap
and no deeper than acuity plus the bonus; a surface signal resolves further than a visceral one; the
other signals resolve shallower while attending; attending asleep or collapsed is refused with a recorded
reason; three presses at the right sub-regions narrow a torso signal to its true leaf and press at a
wrong region returns silence; pressing an injured place raises its intensity briefly; nothing in
`last` or the view names a cause; the leak test passes; the same seed repeats; a simple-backend run
is identical to HEAD, because no simple backend chooses `attend`.

**Out of scope.** Training acuity by attending; simple-backend use of attending or pressing; another
person palpating (a healer's examination is Phase 043's); referred and mislocated sensation (065).

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
| 023 Timed jobs occupy the worker | done | (this commit) | docs/phases/phase023/PHASE023_REPORT.md -- busy refusal, jobs pause when the worker leaves the start cell, paused read-offs; 844 passed |
| 024 Exhaustion, collapse and sleep | done | (this commit) | docs/phases/phase024/PHASE024_REPORT.md -- EXHAUSTION table, graded slowdown, collapse and sleep with refusals and job pause, sleep facts, simple-backend sleep rule; 872 passed |
| 025 Fair turn order | done | (this commit) | docs/phases/phase025/PHASE025_REPORT.md -- per-turn seeded permutation of response order; last_order; 879 passed |
| 026 Observable handovers | done | (this commit) | docs/phases/phase026/PHASE026_REPORT.md -- handover facts replace Transaction; economy.handovers; _transactions compat count; 894 passed |
| 027 Food value and graded eating | done | (this commit) | docs/phases/phase027/PHASE027_REPORT.md -- feeds x freshness; spoiled stock kept; illness_risk published; 907 passed |
| 028 Hearing range and witnessing | done | (this commit) | docs/phases/phase028/PHASE028_REPORT.md -- loudness is Chebyshev hearing radius; sight witnesses the act; per-listener deliveries; 921 passed |
| 029 Contested take and reactions | done | (this commit) | docs/phases/phase029/PHASE029_REPORT.md -- CONTEST, SIZE, fighting skill; react() protocol; human reaction wait; 945 passed |
| 031 Register and harden the LLM backend | done | (this commit) | docs/phases/phase031/PHASE031_REPORT.md -- `create_game(llm_provider=)` and `llm_backend_factory`; response validated against PROMPT_RESPONSE_FIELDS; one repair; idle fallback, never raises; counts in `game_report()['llm']`; 26 tests, fake provider only; no network, `.env` unread |
| 030 Store lock and key | done | (this commit) | docs/phases/phase030/PHASE030_REPORT.md -- keys are items; lock/unlock actions; dual keys; _store_open guards; 967 passed |
| 032 Use trains the body | done | (this commit) | docs/phases/phase032/PHASE032_REPORT.md -- seed training rules; effective stats; training switch; strength gate on all heavy recipes; 1003 passed |
| 037 One health, several routes to death | done | (this commit) | docs/phases/phase037/PHASE037_REPORT.md -- harm(actor, amount, cause); age decline; starvation harm; recovery cap; deaths by cause; 1020 passed |
| 051 Words for numbers and statuses | done | (this commit) | docs/phases/phase051/PHASE051_REPORT.md -- `domains/lexicon.py` (`describe`, `value_for`, reverse words, `resolve_verb`), 35 quantities in self and other perspectives read from the pack, source edges cross-checked, bigville and test_hamlet words differ; 179 tests; 1199 passed |
| 050b Resolution core, the rest | done | (this commit) | docs/phases/phase050/PHASE050B_REPORT.md -- displace (push, pull, drag); spill; recipe pace, quality, yield, ruin; set_intensity; trivial and slot rules; strain recovery; 1265 passed |
| 050 Resolution core, stage 1 | done (part) | (this commit) | docs/phases/phase050/PHASE050_REPORT.md -- pure core; VERBS, MATERIALS, RESOLUTION; attempt with damage and open; intensity, strain, wear, noise; recipe cost term inert at the gate; 1242 passed |
| 058 Persona: personality, a usual day, relationships | done | (this commit) | docs/phases/phase058/PHASE058_REPORT.md -- `domains/persona.py` (traits in words, life sketch, usual day, persona card), `BigvilleGame.persona()`, routine bands now read from the pack (unchanged 9/17/21), `plan_ties` seeds 845 founding ties but `RELATIONSHIP_SEEDING.enabled` is false because four tests assert a town with no ties; simple-backend behaviour identical to HEAD over 60 and 200 turns; 245 phase tests; 1328 passed |
| 043 Screening, treatment, well-baby care and illness | done | (this commit) | docs/phases/phase043/PHASE043_REPORT.md -- illness switch (off); DISEASE and MEDICAL_CARE; checkup, treat, well-baby as care kinds; 1352 passed |
| 052 The agent view | done | (this commit) | docs/phases/phase052/PHASE052_REPORT.md -- `domains/agent_view.py` builds the view from a pack whitelist (`world/agent_view.json`), fail-closed; `BigvilleGame.agent_view(actor, mode)`, `GET /api/view`, `/api/state` 403 and `/api/turn` returns the view in agent mode (on when `--player` is named, `--referee` restores); leak test over 100 residents; 26 tests; 1378 passed |
| 059 Autopilot and momentum | done | (this commit) | docs/phases/phase059/PHASE059_REPORT.md -- LLMBackend owns a DeterministicBackend; `ConsultGate` and `CallBudget` (`bigville/backends/autopilot.py`), pack `AUTOPILOT` table; consults at interrupts, routine boundaries, check-ins and idle; fallback by cause (provider error, invalid output, call or spend cap) is the autopilot's action; `waiting: true` rejected, no action carries on, `wait` idles; model plans hold; would-be choice and deviation counts in `llm_report`; 34 tests; simple backend identical to HEAD over 60 turns; 1412 passed |
| 054 LLM prompt packet and reply schema | done | (this commit) | docs/phases/phase054/PHASE054_REPORT.md -- prompt built from the agent view (`bigville/prompt/3`, words only, per-section caps, persona and usual-now lead); reply schema in the pack with lexicon words for intensity and amounts and verb aliases; hostile speech quoted as inert data; lessons persist and merge over the cap; every `can` row has a handle (`domains/affordance_handles.py`) and a reply that names it runs the row as the simple backend would send it; 55 tests; simple backend identical to HEAD over 60 turns; 1467 passed |
| 048 Tools by fitness | done | (this commit) | docs/phases/phase048/PHASE048_REPORT.md -- TOOL_FIT; bare hands 0.05; no tool refusals; time, stamina, wear, strain, yield and waste by fit; stop; 1483 passed |
| 057 Terminal interface | done | (this commit) | docs/phases/phase057/PHASE057_REPORT.md -- `python -m bigville.tui` (plain and curses) on the agent view only; pure `render` (80x24 snapshot), command parser with lexicon verbs, intensity and amount words, ambiguity questions; pack `NARRATION`; embedded and HTTP clients (no `/api/state`); agent-mode server binds a reply's handles and delivers reactions; view gains a `reaction` section; 48 tests; 1532 passed |
| 034 Intoxication | done | (this commit) | docs/phases/phase034/PHASE034_REPORT.md -- Widmark gain, linear sobering, skill loss via effective_skill, stagger, pass-out; 1553 passed |
| 055 LLM backend operations | done | (this commit) | docs/phases/phase055/PHASE055_REPORT.md -- bounded thread pool for `concurrent` backends with fixed result order; JSONL transcripts and a replay provider keyed by turn, actor and prompt hash; stdlib OpenAI-compatible provider with OpenCode Go settings, retries, rate limit, key redaction and spend cap; `llm_scenario` mixed towns; per-resident and per-day cost in `llm_report`; live test skipped by default; 3 LLM + 97 simple for 100 turns made 38 calls; 38 tests; simple backend identical to HEAD; 1569 passed on the previous base |
| 038 Strikes and injury | done | (this commit) | docs/phases/phase038/PHASE038_REPORT.md -- strike through the contest rule; injury and violence harm; trigger off by default; 1609 passed |
| 066 LLM harness: session, memory, whole log | done | (this commit) | docs/phases/phase066/PHASE066_REPORT.md -- per-resident message thread (full packet, then deltas, compaction by new thread, stable session id); provider returns `ProviderResult` with reasoning fields and the whole response; hash-chained append-only `LLMLog` that keeps thinking whole and detects edits and cuts; replay keyed on thread state naming the first differing message; `to_dict`/`from_dict` stop and resume; 17 tests; simple backend identical to HEAD; 1626 passed |
| 056 Learning evaluation | done | (this commit) | docs/phases/phase056/PHASE056_REPORT.md -- `bigville/learning_eval.py` (per-resident metrics from engine records, repeat-mistake rate, tries before switch, lessons offered and used, leak guard that voids a run, scripted learner and non-learner, marginal effect against a simple control) and `tools/run_learning_eval.py`; learner repeat-mistake rate 0.000 against 0.967; Ocelot arm skipped; 8 tests; no shared file edited |
| 049 Consequences instead of gates | done | (this commit) | docs/phases/phase049/PHASE049_REPORT.md -- skill, season, strength, busy, serving, leak, capacity, harvest, tending gates become consequences; plan-path walk, rest and watering refusals kept; 1653 passed |
| 035 Nutrition | done | (this commit) | docs/phases/phase035/PHASE035_REPORT.md -- protein, taste, satiety, pleasure, mood, spice; energy monotony behind a switch (off); 1696 passed |
| 036 Alcohol's longer effects | done | (this commit) | docs/phases/phase036/PHASE036_REPORT.md -- tolerance, dependence, craving, withdrawal, hangover, poisoning, speech clarity, coping policy; switch off; 1716 passed |
| 047 Joint actions | done (part) | (this commit) | docs/phases/phase047/PHASE047_REPORT.md -- joint carry and crewed recipes behind a switch; team term; group takes, gangs and group contests not built |
| fix LLM ops | done | (this commit) | docs/phases/fix_llm_ops/FIX_LLM_OPS_REPORT.md -- `bigville/llm_checkpoint.py` checkpoints an LLM resident (the hook in the Ocelot stream's untracked `game_persistence.py` is not committed); `create_game` and `build_llm_town` attach a gzip hash-chained `LLMLog` by default (`runs/llm_logs`, opt out with `llm_log=False`); 16 tests; 1707 passed |
| fix simple village | done | (this commit) | docs/phases/fix_simple_village/FIX_SIMPLE_VILLAGE_REPORT.md -- founding relationship seeding on for bigville (845 directed ties; four tests now assert them; simple-backend actions unchanged over 60 and 200 turns); the simple walk names a `body_down` interrupt so a fallen resident gets no replayed proposal (200 turns: `collapsed` refusals 15 to 0, Phase 049's `exhausted` refusals unchanged); 8 tests; 1736 passed |
| 053 Fog of map | done | (this commit) | docs/phases/phase053/PHASE053_REPORT.md -- `domains/map_memory.py` keeps a fogged resident's map as one `map_memory` record (checkpoints with the character): level 0 absent, 1 named places and roughly where in words, 2 cells and exact places; learning by sight, landmarks and told places, ageing words; the view's `map` and `can` are built from it (`walk toward`), `move` takes `toward`; LLM and human backends are `fogged`, simple locals are not (60-turn run identical); 21 tests; 1756 passed |
| 033 Restraint | done | (this commit) | docs/phases/phase033/PHASE033_REPORT.md -- restrain, release, struggle through the contest rule; hold blocks walking and costs stamina; 1795 passed |
| 040 Objects as arms | done | (this commit) | docs/phases/phase040/PHASE040_REPORT.md -- strike with an object, throw; OBJECT_FORCE; switch off; 1800 passed |
| 042 Day, night and lamps | done (switch off) | (this commit) | docs/phases/phase042/PHASE042_REPORT.md -- pure sky maths (`domains/daynight.py`), world facts in `worlds/daynight.py` (sees_dark, lamps with oil, light and douse actions, candles, shorter sight, slower and wasteful dark work on the fitness path, lateness from the real sunset), lamplighter job and backend round, light words in the view; off by default because the round never lights a lamp in 200 ticks; off is byte-identical to HEAD; 29 tests; 1807 passed |
