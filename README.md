# Bigville

Bigville is a data-driven village simulation and game API. The canonical world
contains a map, residents, bodies, animals, farms, buildings, food production,
trade, storage, law, records, observations, affordances, and seeded resident
cognition. Actors are driven through a backend boundary: Ocelot, a human UI,
the deterministic game backend, or a future LLM backend can all propose the
same validated actions.

The public API is in `bigville/`:

```python
from bigville import create_game

game = create_game(player="Ada", default_backend="cheap")
state = game.step()
```

Bigville is standalone: its graph runtime, world mechanics, seed data, backend
protocol, persistence model, and tests are all in this repository. Cognition
providers may be embedded, remote, deterministic, human-driven, or backed by
another project; none is required to run the simulation.

## Development

```bash
python -m pip install -e .
python -m pytest -q
```

The backend and prompt work is staged in
[`docs/AGENT_BACKENDS_PLAN.md`](docs/AGENT_BACKENDS_PLAN.md).
