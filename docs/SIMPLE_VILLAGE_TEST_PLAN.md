# Simple backend: staged village verification plan

## Objective and boundary

Build evidence, from small scenarios to an extended live village, that the simple
backend can perceive, choose, act and respond to the consequences of its actions.
The same physical starting conditions must support different cognitive policies.
A successful run demonstrates the stated checks; it does not prove that a society
is realistic or self-sustaining outside the tested conditions.

The world owns physical state and causality: space, reachability, time, bodies,
resources, physical objects, observable events, and the physically possible
consequences of actions. It publishes situated observations and affordances and
resolves simultaneous actions. It may enforce physical constraints and scheduling
limits such as reach, capacity, locks and time. It must not decide what an agent
believes, wants, intends, understands, values, consents to, promises, owns by
right, or considers lawful. Social, legal, economic and game rules are agent-held
interpretations and decisions, implemented in the cognitive backend. A written
law or price tag may exist physically; its meaning and enforcement must arise
from agents. A physical action can violate a norm and have physical and social
consequences. Records and labels are evidence, not automatic authority. Avoid
leaking hidden state into a resident's observations.

This is a target, not a claim about current code. In particular, audit the
world's `_actor_options`, `resident_plan`, purchase-utterance/price/willingness
checks, automatic output claiming, relationship and law handling, and scenario
seed loading. Decide case by case which state is physical evidence, which is
agent-held interpretation, and which behavior must move to the backend. Do not
remove physical reach, possession or resource conservation in the process.
Changing a social rule should not change what is physically possible, though it
may change an actor's choices and the actions other actors take in response.

## Work package contract

Each numbered package is intended for one Luna agent and one focused change:
a fixture, a narrow backend/world adjustment if needed, tests, and a short note
of findings. If a package cannot be completed without a broader redesign, stop
at a reproducible failing test and identify the dependency; do not silently
weaken the check. Run the focused tests and applicable existing regressions.
Preserve existing work and coordinate shared-file edits when packages run in
parallel. A reviewer integrates each package and runs the gate before starting
its dependants. Parallel execution is optional, not a requirement.

Fixtures specify map, initial actor and resource state, backend and policy,
clock/period cadence, seed, observation scope, subsystem configuration, action
budget, expected effects and a negative or control case. Use actual game turns
and physical state for end-to-end tests; isolated policy tests can use recorded
contexts. Assertions must cover cause, effect and observation, not just an
accepted response. Record traces containing turn, actor, visible observations,
affordances, selected action and reason, result, relevant state deltas and
period transitions. Run fixed seeds with deterministic replay; where a claim
involves robustness use multiple predeclared seeds and report each result.
Controls should fail for the intended reason, not because of unrelated setup.
Tests must not assume events become known to agents who did not observe them.

## Foundation

1. **Baseline and inventory.** Capture the current commit, dirty state, Python
   environment, full-suite result, and short 100-resident smoke result. Catalogue
   world methods that make cognitive or normative decisions and existing physical
   action paths. Deliver a table with a reproduction and affected tests for each
   suspect; do not refactor in this package. Gate: another developer can reproduce
   the baseline and trace each item to code.

2. **Scenario runner and trace.** Add a small unattended runner for authored
   scenarios, configurable seed, duration and period cadence, with compact
   machine-readable action/result/state traces. Verify reproducibility, that a
   waiting human does not advance time, and that tracing is observational. Keep
   the existing game/world APIs usable. Gate: two identical runs have identical
   relevant traces and a changed seed is recorded.

3. **Subsystem switches.** Define named, explicit physical subsystem switches
   with documented defaults and dependencies; implement a small initial set for
   metabolism, ecology and decay, exposing effective configuration in traces.
   Disabling one must suppress its effects without silently disabling unrelated
   mechanics. Reject unknown or incompatible settings. Add a custom extension
   seam for future physical subsystems. Gate: paired on/off scenarios show the
   intended state difference and unchanged unrelated physical invariants.
   Scenario seed identifiers alone are not evidence that a rule was executed.

4. **Simple-policy configuration.** Make per-actor scenario profiles usable
   through a documented registry/factory, including goals, action preferences
   and optional small stateful policy hooks. Retain a bounded deterministic
   default and never invent an unavailable action. Unknown profiles fail clearly.
   Gate: same observations and affordances with two profiles produce distinct,
   reproducible choices; neither profile can bypass the world action boundary.

## Isolated physical loops

5. **Movement and access.** One resident, a small map and an object behind a
   route; test movement, obstacles, reach, carrying and action failure. Include
   an unreachable target and a blocked route. Gate: object position changes
   only after a reachable, successful physical action; failed actions are visible.

6. **Body, food and time.** One resident and a local food container: exercise
   period-driven hunger, fetch, eat, stamina loss and rest. Compare food-present
   and food-absent runs; demonstrate starvation under the latter's configured
   horizon. Include a control disabling metabolism. Gate: inventories conserve
   food and the backend responds to observed hunger and energy.

7. **Tools and materials.** A single worker, finite input and a required tool:
   execute a simple timed job, wear and repair if supported. Compare missing
   material and missing tool; assert no output without physical inputs. Gate:
   resource accounting and job state agree after each step.

8. **Crop and water.** A farmer, seeds, plot and water: sow, water, grow and
   harvest with explicit period cadence. Include a no-water control and a
   season or timing constraint. Gate: crop and water state reflect actions and
   period effects; no harvested output appears without growth.

9. **Animals.** A bounded animal enclosure and caregiver: verify autonomous
   animal hunger, movement, feeding and care, plus one physical product where
   supported. Include food absent and barrier failure controls. Gate: animal
   action and metabolic effects use the configured mechanics and conservation;
   distinguish current automatic feeding from cognition-driven behavior.

10. **Storage, decay and construction.** Check that quantities move between
    physical locations, capacity and access apply, food can spoil, and a small
    structure consumes inputs and labor. Compare suitable/unsuitable storage and
    missing materials. Gate: no implicit transfer, loss or creation except the
    documented physical transformations.

## Interaction and agent-held rules

11. **Observation and communication.** Two residents in and out of range send
    and receive structured speech through the simple backend. Test non-delivery,
    movement into range, and a visible effect on recipient-held state or a later
    decision. Gate: private state and unobserved events do not leak; a message
    alone does not physically transfer an object or compel an action.

12. **Exchange and consent.** Two actors physically hold food and tokens. Add a
    simple backend trade policy covering offer, acceptance, refusal and physical
    handover. Compare willing and unwilling sellers, and test attempted taking or
    broken agreement where physically possible. Move any implicit price,
    willingness or agreement decision found in the world to agent cognition;
    physical possession, reach and capacity remain world checks. Gate: a trade
    happens through observable actor actions, not a world-side agreement, and a
    refusal is an actor choice rather than a law of physics.

13. **Norms and enforcement.** Two otherwise identical rooms use different
    backend-held property or sharing policies. An actor can physically take the
    same accessible object in both; an observer can react only after observing
    it. Model enforcement as actor action and its physical consequence. Gate:
    physical possibility remains invariant across policies, but actor decisions
    or reactions differ; an unobserved action creates no omniscient sanction.

14. **Work, food and exchange.** Three to five actors with complementary roles
    produce, carry, offer and consume food over multiple periods. Exercise the
    isolated mechanics through the same backend/action boundary. Compare a run
    without one critical input or participant. Gate: trace the provenance of each
    consumed unit, no hidden allocation occurs, and the control exposes the
    expected shortage rather than magically satisfying needs.

15. **Resource and social stress.** Use a small population with limited stock,
    shared space and competing needs. Introduce a predeclared shock and compare
    two backend policies under identical physical conditions. Gate: report
    survival, hunger, resource balances, failed actions, interactions and agent
    observations over multiple seeds; distinguish measured outcomes from claims
    of fairness, cooperation or realistic society.

16. **Room-scale scenario adaptation.** Adapt one existing restaurant or
    tabletop scenario using scenario-specific simple policies, without inventing
    game or service rules in the physical world. Test an alternate interpretation
    or refusal over the same objects. Gate: trace observable actions and agent-held
    interpretations; no automatic game setup, agreement or service outcome.

## Integration and release gate

17. **Village integration smoke.** Run the actual town100 through unattended
    `BigvilleGame` with simple backends, not the world's autonomous fallback.
    Capture initialization, selected policies, subsystem settings, action results,
    supply and population metrics. Inspect at least one complete food, work and
    social causal chain. Gate: no crashes, unexplained action failures, invalid
    physical balances or cognitive decisions made by the world. Record CPU time
    and memory so the extended run is practical.

18. **Extended live village evaluation.** Before running, commit a configuration
    and acceptance thresholds based on the observed baseline: duration in turns
    and periods, at least three fixed seeds, population, resources, physical
    subsystem settings, backend profiles, and thresholds for survival, food,
    action success, resource conservation, observation privacy and runtime.
    Include a deliberately resource-constrained control and a policy variation.
    Run long enough to cover repeated production, consumption, spoilage and
    social encounters, not merely startup. Gate: publish per-seed summaries,
    time series, action and failure counts, causal trace samples, invariant
    violations, initial/final state, exact command, elapsed time and limitations.
    Investigate every threshold failure; do not tune thresholds after the fact
    without labeling and rerunning the experiment. Passing demonstrates only the
    stated conditions, not general societal realism or indefinite sustainability.

Dependencies: 1 precedes all; 2–4 establish the shared test boundary; 5–10 can
then be developed independently where they do not edit the same code. 11–13
follow the relevant physical loops and boundary audit; 14 depends on 6–8 and
12; 15 depends on 11–14; 16 depends on 5, 11 and 13; 17 depends on the preceding
relevant gates; 18 follows 17. Findings can split a package further, but each
split retains a focused fixture, negative control and reviewable gate.
