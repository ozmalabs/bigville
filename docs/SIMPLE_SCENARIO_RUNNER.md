# Simple scenario runner

Run a scenario through real `BigvilleGame` turns with the unattended simple
backend:

```sh
python -m bigville.scenario_runner town100 --seed 17 --turns 20 \
  --ticks-per-period 4 --backend simple --output /tmp/town-trace.json
```

The JSON trace records the requested seed and cadence, each actor's situated
observations and affordances, proposed action and result, compact physical state
changes, and period transitions. The `--backend` option selects the backend for
all scenario actors when supplied; without it, authored backend selections are
preserved and `simple` is the default for actors without a selection. Human
waiting is treated as a runner error; ordinary game sessions still return
`waiting` without advancing the turn or clock.

Trace collection reads state around each actual game step. A trace is evidence
of the recorded run, not a claim that the policy or world model is realistic.

## Physical subsystem configuration

Scenarios may set a `physical_subsystems` mapping of names to booleans. The
independent switches `metabolism`, `ecology`, and `decay` default to `true`;
there are no dependencies among them. Metabolism gates period hunger/starvation
for residents and animals and daily age/recovery updates. Ecology gates crop
growth and wilting plus town100 renewable water and pasture yields. Decay gates
perishable-stock freshness and passive ToolItem condition loss. Disabling a
switch leaves the clock, actor actions, jobs, and other switches running. Invalid
names and non-boolean values fail during world construction. The runner records
the complete effective switch mapping at the trace root.

World extensions can supply a mapping of custom subsystem names to callbacks
through `BigvilleWorld(..., physical_subsystem_extensions={...})`; callbacks
receive `(world, 1)` once for each elapsed period and are disabled by default.
Custom switches can also be installed on an existing world with
`register_physical_subsystem(name, callback, enabled=False)`. Register custom
callbacks before advancing the clock. Scenario configuration naming a custom
switch is valid only when that extension has been supplied to the world.
