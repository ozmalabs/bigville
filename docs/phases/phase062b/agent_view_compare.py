import hashlib
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from bigville.api import create_game
g = create_game(scenario="town100", seed=305000, player="Verity Peaseblossom")
out = {}
names = [g.player] + sorted(g.world._actors)[:4]
for n in names:
    for mode in ("agent", "referee"):
        try:
            v = g.agent_view(n, mode=mode)
        except TypeError:
            v = g.agent_view(n)
        out[f"{n}|{mode}"] = json.dumps(v, sort_keys=True, default=str)
blob = json.dumps(out, sort_keys=True)
print(hashlib.sha256(blob.encode()).hexdigest(), len(out))
