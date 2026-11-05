# Scenarios

Bigville is a scenario runner. `town100` is the village scenario, not a
requirement of the simulation boundary.

A scenario can be a JSON file in `scenarios/`, an inline dictionary, or a
`ScenarioDefinition`. The common fields are:

```json
{
  "id": "restaurant",
  "name": "The Lantern Restaurant",
  "map": {"grid": [["wall", "floor", "wall"]]},
  "buildings": [],
  "seeds": ["conversation"],
  "actors": [{
    "name": "Ruth",
    "role": "server",
    "backend": "ocelot",
    "home_cell": [1, 1]
  }],
  "initial": {"hour": 12.0},
  "laws": [],
  "policies": [],
  "charters": [],
  "metadata": {"domain": "service_social"}
}
```

Run one through the normal API:

```python
from bigville import create_game

game = create_game(scenario="restaurant", player="Nell")
```

The same interface can represent a room-scale argument, a restaurant, a
court hearing, a market exchange, or a full village. The world still owns
physical admissibility and time; actors and their cognition backends own
decisions, speech, and interpretation.

Board games follow the same boundary. `monopoly_four_players` seeds four
people in a room with a neutral physical box and ordinary physical objects:
cards, banknotes, tokens, dice, houses, hotels, and a board. The world does
not know that these objects form Monopoly and does not require anyone to open
or use them. The participants may interpret the objects as Monopoly, another
game, or nothing at all:

```python
from bigville import create_board_game

experiment = create_board_game(scenario="monopoly_four_players", seed=1)
experiment.run(ticks=40)
print(experiment.summary())
```

Every tick asks one participant's cognition backend what to do with its
observations. Opening the box, reading the rulebook, choosing a token, talking,
or playing a game only happen if an agent proposes the corresponding action.
There is no synthetic election, setup completion, turn order, transaction, or
winner in this room session. A different held game can interpret the same
physical objects differently, or ignore them entirely.

To run the same held game through the Ocelot cognition adapter, use
`backend="ocelot"`. The physical room is still the only world-engine state;
Ocelot receives the held frame and owns its speech output.

```python
experiment = create_board_game(scenario="monopoly_four_players", seed=1,
                               backend="ocelot")
result = experiment.run(ticks=40)
```

The world engine contains no Monopoly properties or turn ledger.

For a new tabletop game, use the generic setup boundary:

```python
from bigville import create_tabletop_experiment

table = create_tabletop_experiment(scenario="your_game")
table.setup()
```
