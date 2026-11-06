"""Run the town100 game with simple backends for N turns; print deaths by cause and the turn of each death."""
import collections
import json
import sys

from bigville.api import create_game
from bigville import village_eval as ve

turns = int(sys.argv[1]) if len(sys.argv) > 1 else 192
game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True,
                   ticks_per_period=ve.TICKS_PER_PERIOD)
world = game.world
first = {}
for t in range(turns):
    game.step()
    if len(world._deaths) and "first" not in first:
        first["first"] = t
deaths = world._deaths
causes = collections.Counter(str(d.get("cause", d.get("reason", "?"))) if isinstance(d, dict) else str(d) for d in deaths)
print(json.dumps({"turns": turns, "ticks_per_period": ve.TICKS_PER_PERIOD, "deaths": len(deaths),
                  "first_death_turn": first.get("first"), "causes": causes,
                  "sample": [d if isinstance(d, dict) else str(d) for d in deaths[:3]]}, default=str))
