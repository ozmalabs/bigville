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

**Status:** ready

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

**Status:** blocked -- needs the user's decision. Rebuilding the cast changes
the residents that the seeded-town tests are built on.

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

**Status:** blocked -- scope decision: how far kinship goes (spouses and
children only, or extended family).

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

## Phase 011 -- Taxes, wages, and rent

**Status:** blocked -- needs the user's decisions on who levies what.

## Phase 012 -- Learning as observation (boundary follow-up)

**Status:** blocked -- needs the user's decision between keeping skill practice
as a physical subsystem (current) or logging practice as an observation for the
backend to turn into learning.

---

## History

| Phase | Status | Commit | Report |
|---|---|---|---|
| (none yet) | | | |
