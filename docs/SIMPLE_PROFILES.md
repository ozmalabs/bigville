# Simple backend policy profiles

Simple actors use `DeterministicBackend` with the bounded `default` policy
unless a scenario names another registered profile. Profiles adjust selection
among affordances already published in the actor context. The backend copies
the chosen affordance into a proposal; the world continues to validate and
resolve that proposal.

## Registering a profile

Register a `SimplePolicy` value or a zero argument factory that returns one:

```python
from bigville.backends import SimplePolicy, register_simple_profile

register_simple_profile("farm_first", SimplePolicy(
    goal_priorities={"tend_farm": 20},
    action_bonuses={"harvest": 8, "water": 8},
))
```

`action_bonuses` adjust the score of matching available actions. `goal_priorities`
adjust the order in which the backend maintains its needs driven goals.
Profiles are copied per actor via the factory form when they carry mutable
configuration or hook state. Duplicate names raise unless `replace=True` is
explicitly supplied. Unknown profile names raise `ValueError` during game
construction.

## Stateful hooks

An optional hook object can implement
`score_adjustment(backend, context, option) -> number`. It is called once for
each admissible option. The hook may retain small backend policy state and
adjust a score; it cannot insert an option or change the selected action's
parameters. Keep hooks deterministic if deterministic replay is required.

## Scenario use

Set `simple_profile` on an actor in a scenario definition. Backend selection
must be `simple` or `cheap` (the simple backend's compatibility name):

```json
{"name": "Ada", "role": "farmer", "backend": "simple",
 "simple_profile": "farm_first"}
```

Profiles do not modify observations, affordances, physical constraints, or
world-side action results. The default remains needs driven and deterministic.
