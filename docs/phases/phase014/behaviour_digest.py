"""Phase 014 behaviour digest: the default world's numbers for the paths whose constants move.

Run from a repository root (the working tree, or an export of HEAD) with PYTHONHASHSEED=0:
    PYTHONHASHSEED=0 python3 docs/phases/phase014/behaviour_digest.py
Equal output before and after the phase means the moved constants kept their default values and
the paths they feed still behave the same. Covers: resident defaults, injury, treatment, care,
starvation, the document literacy gate, shop and stock prices, the calendar, and a timed job.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from worlds.bigville_world import BigvilleWorld  # noqa: E402

out = {}
w = BigvilleWorld(autonomous_actors=False)
w.add_actor("Ada", role="hand", home_cell=(1, 1))
w.add_actor("Ben", role="hand", home_cell=(1, 1), station="labouring")
w.add_actor("Cy", role="teacher", home_cell=(1, 1), literacy=1.0, capability=1.0)


def attrs(name):
    a = dict(w.eng.node(w._actors[name])["attrs"])
    keep = ("coin", "age", "skill", "reputation", "starve_limit", "health", "health_value", "injury",
            "hunger", "literacy", "capability", "learn", "life_stage", "alive", "wage_due", "aptitude")
    return {k: a.get(k) for k in keep}


out["defaults_ada"] = attrs("Ada")
out["defaults_ben"] = attrs("Ben")
out["inventory_ada"] = {"capacity": w.capacity(w._actor_inventories["Ada"]),
                        "max_load": w.max_load(w._actor_inventories["Ada"])}

# injury, treatment, care
w.injure("Ada")
out["after_injure"] = attrs("Ada")
w.care_for("Ada", "Ada")
out["after_care"] = attrs("Ada")
w.injure("Ada", severity=0.6)
w.treat("Ada", "Ada")
out["after_treat"] = attrs("Ada")

# starvation cause
w.eng.set_attr(w._actors["Ada"], "hunger", 4.0)
out["death_cause_hungry"] = w._death_cause(w.eng.node(w._actors["Ada"])["attrs"])
w.eng.set_attr(w._actors["Ada"], "hunger", 0.0)
out["death_cause_fed"] = w._death_cause(w.eng.node(w._actors["Ada"])["attrs"])

# document literacy gate: a policy needs functional literacy, a law needs education
policy = next(iter(w._policy_specs))
law = next(iter(w._law_specs))
out["policy_ben"] = w.write_document("Ben", policy, kind="policy") is not None
out["law_ben"] = w.write_document("Ben", law, kind="law") is not None
out["law_cy"] = w.write_document("Cy", law, kind="law") is not None
out["policy_cy"] = w.write_document("Cy", policy, kind="policy") is not None

# prices and shops
cell = sorted(w._map_cells)[0]
w.add_shop("digest_trade", cell, input_kind="grain", output_kind="flour")
shop = w._shops["digest_trade"]
out["shop"] = {k: w.eng.node(shop)["attrs"].get(k) for k in ("price", "coin", "trade")}
w.set_stock("grain", 5.0)
w.stock_person("Cy", "grain", 1.0)
out["stock_person_price"] = w.eng.node(w._actors["Cy"])["attrs"].get("sell_price")

# calendar: clock ticks advance the day, hour, season, week, year
w.tick(100)
out["calendar_after_100_ticks"] = w.calendar()
out["town_attrs"] = {k: w.eng.node(w._town)["attrs"].get(k) for k in
                     ("clock", "hour", "season", "year", "day", "temperature", "firewood_demand")}

# a timed job's length in ticks at the default tick length
mins = float(w.eng.node(w._actions[next(iter(w._actions))])["attrs"]["time_minutes"])
out["first_action_minutes"] = mins
w.add_tradesperson("Wayland", "smith")
out["tradesperson"] = attrs("Wayland")
print(json.dumps(out, sort_keys=True, default=str, indent=1))
