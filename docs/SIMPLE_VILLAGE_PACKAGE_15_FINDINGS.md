# Package 15: resource and social stress

Harness: `bigville/stress_experiment.py`; fixture:
`scenarios/resource_social_stress.json`; focused test:
`tests/test_package15_resource_social_stress.py`.

Run with:

```sh
PYTHONPATH=. python -m bigville.stress_experiment --output /tmp/package15.json
PYTHONPATH=. pytest -q tests/test_package15_resource_social_stress.py
```

## Protocol

The harness uses four co-located residents, metabolism/ecology/decay disabled,
12 bread units in one shared larder, and hunger set to 0.65 for each actor.
It runs 16 turns with two turns per period. For each of three declared seeds,
the same starting state runs with a sharing policy and a self-priority policy.
The predeclared shock removes four units from the larder before actor decisions
on turn 2; the no-shock run is the control. Ada's sharing policy chooses one
real transfer affordance to offer bread to Ben. The self-priority policy
chooses no transfer. All other actors use the self-priority policy. Policies
receive actor-scoped observations and choose only from the published
affordances; the game resolves actions through the existing physical boundary.

The report records each turn's actor observations, affordances, chosen actions,
results, state, period, and shock. Its resource accounting treats successful
eating as consumption and the declared shock as exogenous loss.

## Measured outcomes

The focused test passes (`2 passed`). All three seeds produce the same
deterministic outcomes:

| Seed | Policy | Survivors | Final hunger (Ada/Ben/Cy/Dee) | Fetch/eat/transfer | Failed actions | Bread balance |
| --- | --- | ---: | --- | --- | ---: | --- |
| 15001 | sharing | 4 | 0 / 0 / 0 / 0 | 5 / 4 / 1 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |
| 15001 | self-priority | 4 | 0 / 0 / 0 / 0 | 4 / 4 / 0 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |
| 15002 | sharing | 4 | 0 / 0 / 0 / 0 | 5 / 4 / 1 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |
| 15002 | self-priority | 4 | 0 / 0 / 0 / 0 | 4 / 4 / 0 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |
| 15003 | sharing | 4 | 0 / 0 / 0 / 0 | 5 / 4 / 1 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |
| 15003 | self-priority | 4 | 0 / 0 / 0 / 0 | 4 / 4 / 0 | 0 | 12 initial - 4 shock - 4 eaten = 4 final |

The sharing runs end with one unit carried by Ben; self-priority runs do not.
This is a measured difference in physical distribution and interaction count,
not a claim of fairness, cooperation, or realistic social behavior. Each actor
receives 16 backend observations. The observations contain the actor's own
hunger and inventory, plus nearby resident identity and position; other
residents' hunger is not included.

The no-shock controls retain exactly four more units at the end than their
paired shocked runs, with the same four successful eat actions. Replaying a
seed produces an identical report. Resource accounting closes for every run.

## Dependency status and limits

### Superseded dependency note

An earlier version of this note recorded package 14 as red, citing two
assertion failures. That status is stale: the current `tests/test_simple_work_food_exchange.py`
asserts a seven-unit town-stock decrease (one transfer plus six units for two
milling batches), a final town grain balance of one, and an eight-unit harvest
in the separate no-carrier control. The focused current audit run passed all
package 14 tests. Reproduce with:

```sh
PYTHONPATH=. pytest -q tests/test_simple_work_food_exchange.py
```

Keep package 15's dependency description narrow: its stress harness uses
pantry fetch/eat/transfer and does not exercise the package 14 crop/carrier
workflow.

The fixture disables metabolism to isolate allocation and social choice, so
these runs do not measure starvation, long-run survival, or repeated hunger
under food scarcity. Seed variation is declared and replayed, but this small
setup is deterministic across seeds. The results demonstrate only this
bounded policy contrast and shock protocol.
