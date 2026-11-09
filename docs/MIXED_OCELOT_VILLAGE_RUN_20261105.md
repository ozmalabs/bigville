# Mixed Ocelot village run — 2026-11-05

## Setup and limits

The reproducible harness uses `resource_social_stress`, seed `305000`, four
residents, and two real Ocelot minds (`Ada`, `Ben`) alongside two standard
simple residents (`Cy`, `Dee`). It disables metabolism, ecology, and decay to
focus the run on decisions and action outcomes. A shared pantry starts with 12
bread and each resident starts at hunger `0.65`. Ocelot's existing emotional
appraisal is explicitly enabled so applied and rejected proposals update its
private graph.

The hard run limit is **eight turns and five seconds**. The post-change run
completed all eight turns in **0.822 s total** (0.368 s setup, 0.454 s turn
loop, 47.7 ms average per turn). `/usr/bin/time -v` measured **0.94 s wall time
and 61,416 KiB peak RSS**. The RSS is a host-specific measurement; the harness
does not enforce an RSS threshold.

Run from the Ocelot checkout with both repository roots and the DSL bindings
on `PYTHONPATH`:

```sh
cd /path/to/ocelot
BIGVILLE_ROOT=/path/to/bigville \
PYTHONPATH=/path/to/bigville:/path/to/ocelot:/path/to/ocelot/runners/dsl/python \
.venv/bin/python /path/to/bigville/tools/run_mixed_ocelot_village.py \
  --turns 8 --output /tmp/mixed-ocelot-village.json
```

The raw traces preserve the before/after comparison:

- [Pre-hunger utility trace](runs/mixed_ocelot_village_seed305000_pre_hunger.json)
- [Hunger utility trace](runs/mixed_ocelot_village_seed305000_post_hunger.json)

## Before and after hunger valuation

In the pre-change run, Ocelot residents repeatedly fetched bread and put it
back while hunger stayed at `0.65`. The Ocelot decision seed scored affordance
score and travel effort but did not read hunger. Though hunger was already in
the graph's `CognitiveObservation`, it did not affect the choice.

The Ocelot adapter now projects the latest observed hunger onto the resident
graph, and the packaged Bigville action seed applies appetite utility to food
affordances before its graph Argmax. The same-score causal control now produces
three distinct results: at hunger `0.0`, work beats eat/fetch; at hunger `0.65`
with bread carried, eat wins; at hunger `0.65` without carried food, fetch
wins. The world also marks container fetch affordances with their physical
`food` property, which lets cognition distinguish food retrieval from other
fetch actions. This control uses the actual Ocelot resident and the seed loaded
by `_bigville_seed()` from the packaged `bigville/seeds` directory.

In the eight-turn mixed run, both Ocelot residents fetched on turn 1 and ate on
turn 2. Hunger fell from `0.65` to `0.0`; neither fetched again while sated.
They completed work on turns 3 and 6, and abstained on the other turns. The
simple residents fetched and ate on turns 1–2, then made no further proposals.
The pantry ended at 8 bread; all four residents ended with zero hunger and
empty inventories.

The repeated rejected rest proposal was caused by the world offering `rest`
even at full stamina although enactment rejects rest at reserve `>= 0.8`. The
world now offers rest only below that threshold. Ocelot also receives a
cognition-owned `none` option at score `-0.5`, which allows it to abstain when
all physical actions score lower; ordinary nonnegative physical options still
beat it. The direct world regression checks rest is absent at full stamina and
present below the threshold. There were no rejected actions in the normal
eight-turn trace. This integration run covers hunger valuation and rest
applicability/abstention, not broad autonomous village policy.

## Perception, memory, outcomes, and rejection

Each Ocelot resident accumulated eight `CognitiveObservation` nodes and zero
episodic `Memory` nodes or character-held memories. The decision changes
therefore use current graph-held observations; this run does not demonstrate
episodic memory or save/reload behavior.

Each Ocelot appraisal graph recorded four successful actions (two `work`, one
`fetch`, one `eat`). After the normal run, the harness submitted one deliberate
`phase6_invalid_probe` through the ordinary game action boundary; the world
rejected it, and the Ocelot appraisal recorded the failed outcome
(`individual_cost = 1`, `goal_blocked = 1`). The probe does not change the
measured village state.

The real-provider regression test checks the same affordances at hunger zero
and `0.65`, checks their graph-materialized scores and selected actions, and
checks that the eight-turn mixed run does not fetch again after residents are
fed. It also verifies that the graph selects `none` when sated with no useful
action. The full targeted suite passed: **39 tests** across the Ocelot adapter,
Bigville game API, and mixed-village integration test.
