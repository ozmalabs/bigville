"""Log each simple-backend decision for named residents over a turn window: hunger, energy, food options, choice."""
import sys, json
from bigville.backends import cheap
from bigville.api import create_game
from bigville import village_eval as ve
NAMES = set(sys.argv[2].split(","))
LO, HI = int(sys.argv[3]), int(sys.argv[4])
orig = cheap.DeterministicBackend.decide
def decide(self, context):
    r = orig(self, context)
    if self.character.name in NAMES and LO <= context.turn <= HI:
        foods = [{k: o.get(k) for k in ("action", "kind", "food", "fetch_kind", "physical_source", "stock_source", "score", "legal", "target", "destination") if o.get(k) is not None}
                 for o in context.affordances if o.get("food") or o.get("fetch_kind") or o.get("physical_source") == "container" or o.get("action") in ("sleep", "rest", "eat")]
        print(json.dumps({"turn": context.turn, "who": self.character.name, "hunger": context.observations.get("hunger"),
                          "energy": context.observations.get("energy"), "n_aff": len(context.affordances),
                          "reason": self.last_choice.get("reason"), "choice": self.last_choice.get("action"),
                          "food_aff": foods[:6], "sleep_aff": [o for o in context.affordances if o.get("action") == "sleep"][:1]}, default=str)[:900])
    return r
cheap.DeterministicBackend.decide = decide
game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True, ticks_per_period=ve.TICKS_PER_PERIOD)
for t in range(HI + 1):
    game.step()
print("deaths", [(d["actor"], d["cause"]) for d in game.world._deaths])
