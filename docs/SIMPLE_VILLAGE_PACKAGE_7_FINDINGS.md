# Package 7: tools and materials

## Fixture and reproduction

`scenarios/tools_materials_job.json` defines one simple-backend smith and the
built-in timed `forge_nails` recipe (one iron, one charcoal, one hammer, five
nails). `tests/test_simple_tools_materials_job.py` runs actual game turns and
records observations, affordances, choices, results, period-driven turns, and
stock/tool state deltas. The fixture's test helper supplies finite initial
stocks and allows the hammer's physical condition to be set for the control.

Run from `bigville/`:

```sh
python -m pytest tests/test_simple_tools_materials_job.py -q
```

## Findings

With intact hammer and both materials, the simple backend starts the timed job;
the job consumes one iron and charcoal, creates five nails, clears the busy
state, and wears the hammer. With iron absent, the `forge_nails` affordance is
not published and no output is created. These controls exercise the actual
`BigvilleGame.step()` path.

The broken-hammer control now confirms the physical gate: condition zero removes
`forge_nails` from affordances, and neither the recipe nor its materials are
consumed. Starts and instant actions reject unavailable or broken instruments.
Timed jobs recheck their required instruments before consuming any inputs or
creating output; if a tool is removed or breaks while work is underway, the job
remains busy at completion with its materials intact and can finish after the
instrument is restored. The existing successful control still shows tool wear
after a completed batch.

The game runner's current compact trace omits bulk stocks and instrument
condition. This package's local trace records those quantities directly without
changing shared runner code.
