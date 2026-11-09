"""Instrumented balance harness for the Bigville default town (menu mode, simple backend).

Usage: python3 harness.py --seed 305000 --days 7 --lever base --out out.json [--daynight]

All levers are in-process overrides (monkeypatching pack tables / module constants / world attributes).
The harness itself only OBSERVES: wrappers record, they never change a value.
"""
import sys, os, json, math, argparse, collections, random, time

ORIG_CWD = os.getcwd()
T = os.environ.get("BV_TREE", "/tmp/balance/tree")
sys.path.insert(0, T)
os.chdir(T)

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=305000)
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--lever", default="base")
ap.add_argument("--out", default=None)
ap.add_argument("--daynight", action="store_true")
ap.add_argument("--trace-roles", default="farmer,miller,baker,farm_labourer,labourer")
ap.add_argument("--trace-days", type=int, default=3)
args = ap.parse_args()
if args.out:
    args.out = os.path.abspath(os.path.join(ORIG_CWD, args.out))

from bigville.api import create_game
import domains.world_affordances as WA
import domains.bigville_entities as BE
from bigville.backends import cheap as CH

# ----------------------------------------------------------------------------- levers (pre-create)
LEVER = args.lever
PARAMS = {}
for part in LEVER.split("+"):
    name, _, val = part.partition("=")
    PARAMS[name] = float(val) if val else True

pre = {}
if "walk_cost" in PARAMS:      # L2: scale the per-cell walking energy: CARRYING.base_move_energy
    WA.CARRYING["base_move_energy"] = float(WA.CARRYING["base_move_energy"]) * PARAMS["walk_cost"]
if "rest_rec" in PARAMS:       # L3: EXHAUSTION.rest_recovery_per_unit scaled (module constant is a copy of the table value)
    k = PARAMS["rest_rec"]
    WA.EXHAUSTION["rest_recovery_per_unit"] = float(WA.EXHAUSTION["rest_recovery_per_unit"]) * k
    WA.REST_RECOVERY_PER_UNIT = WA.EXHAUSTION["rest_recovery_per_unit"]
    BE.REST_RECOVERY_PER_UNIT = WA.REST_RECOVERY_PER_UNIT if hasattr(BE, "REST_RECOVERY_PER_UNIT") else None
if "sleep_gain" in PARAMS:
    WA.EXHAUSTION["rest_gain"] = float(WA.EXHAUSTION["rest_gain"]) * PARAMS["sleep_gain"]
if "rest_thr" in PARAMS:       # L6: simple-policy rest threshold (per-instance; the default profile object is built at import)
    _orig_init = CH.DeterministicBackend.__init__

    def _init(self, *a, **k):
        _orig_init(self, *a, **k)
        self.rest_energy_threshold = float(PARAMS["rest_thr"])

    CH.DeterministicBackend.__init__ = _init
if "hbs" in PARAMS:            # HUNGER_BEFORE_SLEEP
    CH.HUNGER_BEFORE_SLEEP = PARAMS["hbs"]
if "due_floor" in PARAMS:
    for d in WA.DUTIES.values() if isinstance(WA.DUTIES, dict) else []:
        pass

# per-index stamina draw (fixed seed) shared by L4 and L5(i)
STA_SD = PARAMS.get("sta_dist", PARAMS.get("sta_dist_n", PARAMS.get("reassign_sd", 0.15)))
_rnd = random.Random(777)
STA_DRAW = [min(1.4, max(0.6, _rnd.gauss(1.0, STA_SD))) for _ in range(100)]
FOOD_JOBS = {"farmer", "farm_labourer", "animal_keeper", "dairymaid", "miller", "baker", "fisher", "butcher", "fishmonger"}

if "reassign" in PARAMS or "convert" in PARAMS or "cast_lp" in PARAMS:
    import domains.bigville_entities as _E
    _orig_plan = _E.plan_founding_town

    def _plan(seed, size=None):
        plan = _orig_plan(seed, size)
        st = [dict(r) for r in plan["staffing"]["residents"]]
        n = len(st)
        if "convert" in PARAMS:      # L5(ii): convert k labourers into farm_labourers (first k labourers in cast order)
            k = int(PARAMS["convert"]); done = 0
            for r in st:
                if done < k and r["jobs"][0] == "labourer":
                    r["jobs"] = ["farm_labourer"] + [j for j in r["jobs"][1:]]
                    r["trades"] = list(_E.JOBS["farm_labourer"]["trades"]); r["tools"] = list(_E.JOBS["farm_labourer"].get("tools", []))
                    done += 1
        if "cast_lp" in PARAMS:      # L7(vi): the lamplighter is a cast job: the first labourer in cast order becomes one
            for r in st:
                if r["jobs"][0] == "labourer":
                    r["jobs"] = ["lamplighter"]
                    r["trades"] = list(_E.JOBS["lamplighter"]["trades"]); r["tools"] = list(_E.JOBS["lamplighter"].get("tools", []))
                    break
        if "reassign" in PARAMS:     # L5(i): food-production jobs go to the highest sta_base residents (ties: younger)
            food = [i for i, r in enumerate(st) if r["jobs"][0] in FOOD_JOBS]
            order = sorted(range(n), key=lambda i: (-STA_DRAW[i], plan["ages"][i]))
            top = order[:len(food)]
            rest_idx = [i for i in range(n) if i not in set(top)]
            food_entries = [st[i] for i in food]
            other_entries = [st[i] for i in range(n) if i not in set(food)]
            new = [None] * n
            for i, e in zip(sorted(top), food_entries):
                new[i] = e
            for i, e in zip(rest_idx, other_entries):
                new[i] = e
            st = new
        plan = dict(plan); plan["staffing"] = dict(plan["staffing"]); plan["staffing"]["residents"] = st
        return plan

    _E.plan_founding_town = _plan

t0 = time.time()
g = create_game(scenario="town100", seed=args.seed, default_backend="simple", autonomous=True,
                ticks_per_period="world", affordance_mode="menu", llm_log=False)
w = g.world
eng = w.eng
names = list(w._actors)
node_name = {int(w._actors[n]): n for n in names}
role = {n: str(eng.node(w._actors[n])["attrs"].get("role")) for n in names}

LP = []
if args.daynight:
    from worlds import daynight as dn
    from domains import daynight as D
    from bigville.backends import duty as DU
    if "lp2" in PARAMS:
        w.E.DAYNIGHT["lamplighters"] = 2
    if "due_floor" in PARAMS:
        DU._DUTIES["lamplighter"]["due_floor"] = float(PARAMS["due_floor"])
    if "cast_lp" in PARAMS:
        for n in names:
            if role[n] == "lamplighter":
                eng.set_attr(w._actors[n], "jobs", "lamplighter")
    if "lp_ri" in PARAMS or "lp_sta" in PARAMS:
        def _appoint(ww):
            job = ww.E.DAYNIGHT["lamplighter_job"]
            need = int(ww.E.DAYNIGHT["lamplighters"])
            def ri(a):
                ch = g.backends[a].character
                return float((getattr(ch, "personality", {}) or {}).get("role_identity", (getattr(ch, "identity", {}) or {}).get("role_identity", 0.0)))
            cands = [a for a in ww._actors if ww.is_alive(a) and eng.node(ww._actors[a])["attrs"].get("role") != "child"]
            cands.sort(key=lambda a: (-ri(a), names.index(a)))
            for a in cands[:need]:
                eng.set_attr(ww._actors[a], "jobs", job)
        dn.appoint_lamplighters = _appoint
    dn.switch_on(w)
    LP = dn.lamplighters(w)

# ----------------------------------------------------------------------------- levers (post-create)
def body_attrs(n):
    return eng.node(w._bodies[n])["attrs"]


def set_sta_base(n, v):
    eng.set_attr(w._bodies[n], "sta_base", float(v))
    eng.set_attr(w._bodies[n], "stats_dirty", 1.0)


if "sta_lit" in PARAMS:        # L1a literal: sta_base = k, initial reserve = k (capacity; rest_cap for sleep stays 1.0)
    k = PARAMS["sta_lit"]
    for n in names:
        set_sta_base(n, k)
        eng.set_attr(w._bodies[n], "stamina_reserve", k)
cost_div = PARAMS.get("sta_cost", 1.0)   # L1b: effort cost divided by k (the normalised meaning of capacity k)

cast_names = [r["name"] for r in w.cast["residents"]] if hasattr(w, "cast") else names
idx_of = {nm: i for i, nm in enumerate(cast_names)}
STA = {n: 1.0 for n in names}
if "sta_dist" in PARAMS or "sta_dist_n" in PARAMS or "reassign" in PARAMS:
    for n in names:
        v = STA_DRAW[idx_of.get(n, 0)]
        STA[n] = v
        if "sta_dist" in PARAMS or "reassign_lit" in PARAMS:   # literal body attr
            set_sta_base(n, v)
            eng.set_attr(w._bodies[n], "stamina_reserve", min(1.0, v))
COST_DIV = {n: (cost_div if cost_div != 1.0 else 1.0) for n in names}
if "sta_dist_n" in PARAMS:      # cost-normalised: effort cost / sta_i
    for n in names: COST_DIV[n] = STA[n]
if "no_decay" in PARAMS:      # diagnostic D1: perishable stock does not lose condition (tests the 25%/day bread decay)
    for _st in eng.nodes("Stock"):
        eng.set_attr(_st, "decay", 0.0)
if "wilt" in PARAMS:          # diagnostic D2: crops tolerate N dry periods (pack CROPS.wilt is 2)
    for _c in eng.nodes("Crop"):
        eng.set_attr(_c, "wilt", float(PARAMS["wilt"]))
    for _k, _v in WA.CROPS.items():
        _v["wilt"] = float(PARAMS["wilt"])
WAIT_FREE = "wait_free" in PARAMS
if "lp_sta" in PARAMS:
    for n in LP:
        COST_DIV[n] = PARAMS["lp_sta"]
skip_walk = [False]

ROLE_FOOD = {"farmer", "farm_labourer", "miller", "baker", "fisher", "dairymaid", "animal_keeper", "butcher",
             "fishmonger", "forester"}


# ----------------------------------------------------------------------------- instrumentation
tick = 0
DAY = lambda: tick // 96

# effort registry: node id -> (actor, body_use, declared_cost)
effort_reg = {}
_orig_add_node = eng.add_node
_orig_set_attr = eng.set_attr



_orig_add_edge = eng.add_edge_unchecked
last_drop = [0.0]
last_gain = [0.0]


def add_edge(source, edge, target, attrs=None):
    if edge == "exerted":
        a = eng.node(target)["attrs"]
        nm = node_name.get(int(source))
        div = COST_DIV.get(nm, 1.0)
        if div != 1.0:
            _orig_set_attr(target, "stamina_cost", float(a.get("stamina_cost", 0.0)) / div)
        if skip_walk[0] and str(a.get("body_use", "")) == "walk":
            _orig_set_attr(target, "stamina_cost", 0.0)
        effort_reg[int(target)] = (node_name.get(int(source)), str(a.get("body_use", "")), float(a.get("stamina_cost", 0.0)),
                                   w.exhaustion_step(node_name.get(int(source))) if node_name.get(int(source)) else -1)
    return _orig_add_edge(source, edge, target, attrs) if attrs is not None else _orig_add_edge(source, edge, target)


eng.add_edge_unchecked = add_edge

# per-day, per-role accumulators
def rd():
    return collections.defaultdict(lambda: collections.defaultdict(float))

E_spent = collections.defaultdict(lambda: collections.defaultdict(float))     # (day, role) -> {walk, work, other, declared_walk...}
E_band = collections.defaultdict(lambda: collections.defaultdict(float))
at_work_ticks = collections.defaultdict(int)
arrive_tick = {}
starts_recipe = collections.Counter()
starts_role_recipe = collections.Counter()
eat_val = collections.defaultdict(float); eat_n = collections.Counter(); eaters = collections.defaultdict(set)
bread_cond = {}
E_gain = collections.defaultdict(lambda: collections.defaultdict(float))      # (day, role) -> {rest, sleep}
body_ids = {int(w._bodies[n]): n for n in names}
tick_gain = collections.defaultdict(float)     # actor -> total positive reserve delta this tick
tick_rest = collections.defaultdict(float)


def set_attr(node, key, value):
    ni = int(node)
    if key == "stamina_reserve" and ni in body_ids:
        old = float(eng.node(ni)["attrs"].get("stamina_reserve", 1.0))
        d = float(value) - old
        n = body_ids[ni]
        if d < 0:
            last_drop[0] = -d
        elif d > 0:
            tick_gain[n] += d
            last_gain[0] = d
    elif key == "cost_done" and int(node) in effort_reg and float(value) == 1.0:
        n, use, decl, bnd = effort_reg[int(node)]
        r = role.get(n, "?")
        if use == "walk":
            E_band[(DAY(), bnd)]["energy"] += last_drop[0]; E_band[(DAY(), bnd)]["attempts"] += 1
        cat = "walk" if use == "walk" else "work"
        E_spent[(DAY(), r)][cat] += last_drop[0]
        E_spent[(DAY(), r)]["n_" + cat] += 1
        E_spent[(DAY(), r)]["declared_" + cat] += decl
        last_drop[0] = 0.0
    elif key == "rest_done" and float(value) == 1.0:
        # find the actor whose rested edge holds this event
        pass
    elif key == "complete" and float(value) == 1.0:
        on_complete(ni)
    return _orig_set_attr(node, key, value)


eng.set_attr = set_attr

# production
prod = collections.defaultdict(float)                 # (day, recipe) -> units of output (all kinds)
prod_kind = collections.defaultdict(float)            # (day, kind) -> positive stock deltas inside completions
prod_by_role = collections.defaultdict(float)         # (day, role, recipe) -> completions
completions = collections.Counter()                   # (day, recipe) -> n
completions_role = collections.Counter()              # (day, role, recipe)
stock_buf = []
_orig_set_stock = w.set_stock


def set_stock(kind, qty):
    before = w.qty(kind)
    r = _orig_set_stock(kind, qty)
    d = w.qty(kind) - before
    if d > 0:
        stock_buf.append((kind, d))
    return r


w.set_stock = set_stock
_orig_plan = w._plan_inputs


def plan_inputs(*a, **k):
    stock_buf.clear()
    return _orig_plan(*a, **k)


w._plan_inputs = plan_inputs


def on_complete(job):
    if eng.node(job)["type"] != "Job":
        return
    ja = eng.node(job)["attrs"]
    actor = str(ja.get("canonical_actor", ""))
    asp = eng.neighbours(job, "runs")
    rec = eng.node(asp[0])["attrs"].get("name", "?") if asp else "?"
    completions[(DAY(), rec)] += 1
    completions_role[(DAY(), role.get(actor, "?"), rec)] += 1
    for kind, d in stock_buf:
        prod_kind[(DAY(), kind)] += d
    stock_buf.clear()


# cells walked (per actor per tick), by wrapping move_actor
cells_tick = collections.defaultdict(int)
_orig_move = w.move_actor


def move_actor(actor, destination):
    before = w.actor_position(actor)
    band_before = w.exhaustion_step(actor)
    if WAIT_FREE:
        cd = float(eng.node(w._actors[actor])["attrs"].get("carry_move_cooldown", 0.0))
        skip_walk[0] = cd >= 1.0 - 1e-9
    try:
        r = _orig_move(actor, destination)
    finally:
        skip_walk[0] = False
    after = w.actor_position(actor)
    if before is not None and after is not None and tuple(before) != tuple(after):
        cells_tick[actor] += abs(before[0] - after[0]) + abs(before[1] - after[1])
        E_band[(DAY(), band_before)]["cells"] += 1
    return r


w.move_actor = move_actor

_orig_eat = w.eat


def eat(actor, *a, **k):
    h0 = float(eng.node(w._actors[actor])["attrs"].get("hunger", 0.0))
    r = _orig_eat(actor, *a, **k)
    if r:
        lm = w.last_meal(actor)
        eat_val[DAY()] += lm["value"]; eat_n[DAY()] += 1; eaters[DAY()].add(actor)
        eat_val[("h_before", DAY())] += h0
    return r


w.eat = eat

# decision log (wrap DeterministicBackend.decide)
dec = collections.defaultdict(lambda: collections.Counter())   # (day, role) -> counters
stay_ct = collections.Counter()
trace = collections.defaultdict(list)
work_recipes = collections.Counter()
trace_roles = set(args.trace_roles.split(","))
_orig_decide = CH.DeterministicBackend.decide


def decide(self, context):
    resp = _orig_decide(self, context)
    try:
        n = context.actor if hasattr(context, "actor") else self.character.name
        n = getattr(self.character, "name", n)
        r = role.get(n, "?")
        d = DAY()
        c = dec[(d, r)]
        obs = context.observations
        hunger = float(obs.get("hunger", 0.0)); energy = float(obs.get("energy", 100.0))
        acts = collections.Counter(o.get("action") for o in context.affordances)
        ma = resp.major_action.action if resp.major_action else "none"
        c["decisions"] += 1
        c["act_" + ma] += 1
        if energy < 35: c["energy_lt35"] += 1
        if hunger >= 1: c["hunger_ge1"] += 1
        if hunger > 0: c["hunger_gt0"] += 1
        if acts.get("work"):
            c["has_work_opt"] += 1
            for o in context.affordances:
                if o.get("action") == "work":
                    work_recipes[(d, r, str(o.get("recipe")))] += 1
        if any(o.get("resumes_job") for o in context.affordances):
            c["has_resume_opt"] += 1
            if resp.major_action and any(o.get("resumes_job") and o.get("destination") == resp.major_action.params.get("destination") for o in context.affordances) and ma == "move":
                c["resume_chosen"] += 1
        if w._job_of(n) is not None: c["decide_with_open_job"] += 1
        if acts.get("work") and ma != "work": c["work_opt_not_chosen"] += 1
        if acts.get("work") and ma != "work" and energy < 35: c["work_opt_energy_block"] += 1
        if acts.get("work") and ma != "work" and energy >= 35: c["work_opt_energy_ok_not_chosen"] += 1
        if acts.get("work") and ma != "work" and energy >= 35 and hunger >= HB: c["work_opt_hungry_fetch_first"] += 1
        reason = (getattr(self, "last_choice", {}) or {}).get("reason")
        if reason: c["reason_" + str(reason)] += 1
        if r in trace_roles and d < args.trace_days:
            trace[n].append((tick, round(energy, 1), round(hunger, 2), ma, reason,
                             dict(acts) if len(trace[n]) < 40 else None))
    except Exception as e:  # never break the run
        dec[("err", str(e))]["n"] += 1
    return resp


HB = CH.HUNGER_BEFORE_SLEEP
CH.DeterministicBackend.decide = decide

if "stay_job" in PARAMS:      # L6b: a resident with an open, running job and no urgent need keeps working (returns a blank turn)
    from bigville.backends.protocol import ActorResponse as _AR
    _decide_inner = CH.DeterministicBackend.decide

    def _decide_stay(self, context):
        n = self.character.name
        obs = context.observations
        if (w._job_of(n) is not None and not w.job_paused(n) and float(obs.get("energy", 100.0)) >= 35.0
                and float(obs.get("hunger", 0.0)) < CH.HUNGER_BEFORE_SLEEP):
            stay_ct[DAY()] += 1
            return _AR()
        return _decide_inner(self, context)

    CH.DeterministicBackend.decide = _decide_stay

# ----------------------------------------------------------------------------- static layout
pos0 = {n: tuple(w.actor_position(n)) for n in names}
store_cell = tuple(w.map_position_node(w._store))
work_cell = {n: (int(eng.node(w._actors[n])["attrs"].get("work_x", -1)), int(eng.node(w._actors[n])["attrs"].get("work_y", -1))) for n in names}

def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ----------------------------------------------------------------------------- run
food_kinds = [k for k, s in w._item_specs.items() if s.get("food")]


def food_store():
    return sum(float(w.qty(k)) for k in food_kinds)


def food_held():
    return sum(float(q) for n in names if w.is_alive(n) for k, q in w.inventory(n).items() if w._item_specs.get(k, {}).get("food"))


def attrs(n):
    return eng.node(w._actors[n])["attrs"]


cat_ticks = collections.defaultdict(lambda: collections.Counter())  # (day, role) -> {cat: ticks}
act_ct = collections.defaultdict(lambda: collections.Counter())      # (day,) -> action counts (applied)
act_role = collections.defaultdict(lambda: collections.Counter())    # (day, role) -> action counts (applied)
cells_day = collections.defaultdict(int)                             # (day, role)
fetch_units = collections.defaultdict(float)
eat_relief = collections.defaultdict(float)
days_out = []
dist_end = {}   # (day, role) -> [mean dist to work, mean dist to store, share at work cell, share within 2 of store]
prev_pos = dict(pos0)
dusk = None
prev_ref = collections.Counter()
lp_ticks = []
refusals_prev = {"by_reason": {}, "by_action": {}}
prev_deaths = 0
lamp_events = []
min_energy_day = collections.defaultdict(lambda: 1e9)  # (day, name) -> min energy (for lamplighter tracking)
ENERGY_LOG = {}

for t in range(96 * args.days):
    tick = t
    day = t // 96
    cells_tick.clear(); tick_gain.clear()
    hung_before = {n: float(attrs(n).get("hunger", 0.0)) for n in names}
    g.step()
    for n in names:
        if not w.is_alive(n):
            continue
        r = role[n]
        resp = g.last_responses.get(n)
        res = g.last_results.get(n)
        ok = res.get("applied", False) if isinstance(res, dict) else bool(res)
        a = resp.major_action.action if (resp is not None and resp.major_action is not None) else None
        sleeping = w._sleep_code(n) is not None
        job = w._job_of(n)
        job_active = job is not None and not w.job_paused(n)
        cells = cells_tick.get(n, 0)
        cell_total = cells
        if sleeping:
            cat = "sleep"
        elif job_active:
            cat = "work"
        elif a == "move" or cells > 0:
            cat = "walk"
        elif a == "rest":
            cat = "rest"
        elif a is None:
            cat = "idle"
        else:
            cat = "act_" + a
        cat_ticks[(day, r)][cat] += 1
        cells_day[(day, r)] += cell_total
        if work_cell[n][0] >= 0 and tuple(w.actor_position(n)) == work_cell[n]:
            at_work_ticks[(day, r)] += 1
            arrive_tick.setdefault(n, t)
        if a == "work" and ok:
            rc = str(resp.major_action.params.get("recipe"))
            starts_recipe[(day, rc)] += 1; starts_role_recipe[(day, r, rc)] += 1
        if a is not None and ok:
            act_ct[day][a] += 1
            act_role[(day, r)][a] += 1
            if a == "eat":
                eat_relief[day] += max(0.0, hung_before[n] - float(attrs(n).get("hunger", 0.0)))
            if a == "fetch":
                pr = resp.major_action.params
                fetch_units[(day, str(pr.get("kind")))] += float(pr.get("amount", pr.get("qty", 0)) or 0)
        elif a is not None and not ok:
            act_ct[day]["REFUSED_" + a] += 1
        # gains this tick: attribute to rest vs sleep
        gain = tick_gain.get(n, 0.0)
        if gain:
            if a == "rest" and not sleeping and not (w._sleep_code(n)):
                E_gain[(day, r)]["rest"] += gain
            else:
                E_gain[(day, r)]["sleep"] += gain
    if (t % 96) == 95:
        acc = collections.defaultdict(list)
        for n in names:
            if not w.is_alive(n): continue
            p = tuple(w.actor_position(n)); wc = work_cell[n]
            acc[role[n]].append((dist(p, wc) if wc[0] >= 0 else None, dist(p, store_cell), 1 if p == wc else 0))
        for r, v in acc.items():
            dw = [x[0] for x in v if x[0] is not None]
            dist_end[f"{day}|{r}"] = dict(n=len(v), to_work=round(sum(dw)/len(dw),1) if dw else None,
                                         to_store=round(sum(x[1] for x in v)/len(v),1), at_work=sum(x[2] for x in v))
    if (t % 96) == 95:
        try:
            bread_cond[day] = round(w._pile_condition(w._stock["bread"]), 3)
        except Exception:
            pass
    if args.daynight:
        cal = w.calendar()
        lit = sum(1 for nn in w._dn_lamps.values() if float(eng.node(nn)["attrs"]["lit"]) == 1.0)
        lprow = {"t": t, "clock": float(cal["clock"]), "hour": float(cal["hour"]), "lit": lit, "night": int(dn.is_night(w)),
                 "lp": {}}
        for n in LP:
            resp = g.last_responses.get(n); res = g.last_results.get(n)
            ok = res.get("applied", False) if isinstance(res, dict) else bool(res)
            a = resp.major_action.action if (resp is not None and resp.major_action is not None) else None
            be = g.backends.get(n); ch = (be.last_choice or {}) if be is not None else {}
            lprow["lp"][n] = {"alive": bool(w.is_alive(n)), "energy": round(float(w.energy(n)), 2) if w.is_alive(n) else None,
                              "hunger": round(float(attrs(n).get("hunger", 0.0)), 3) if w.is_alive(n) else None,
                              "asleep": w._sleep_code(n) is not None, "act": a if ok else (("REF:" + a) if a else None),
                              "reason": ch.get("reason"), "pos": list(w.actor_position(n) or ())}
        lp_ticks.append(lprow)
    if (t % 96) == 44:
        alive = [n for n in names if w.is_alive(n)]
        dusk = sorted(float(w.energy(n)) for n in alive)
    if (t % 96) == 95:
        alive = [n for n in names if w.is_alive(n)]
        row = dict(day=day, alive=len(alive))
        if alive:
            hung = [float(attrs(n).get("hunger", 0)) for n in alive]
            hs = sorted(hung)
            en = [float(w.energy(n)) for n in alive]
            row.update(hunger_mean=round(sum(hung) / len(hung), 3), hunger_p10=round(hs[int(.1 * len(hs))], 2),
                       hunger_p90=round(hs[int(.9 * len(hs))], 2), hunger_ge1=sum(1 for h in hung if h >= 1),
                       energy_mean=round(sum(en) / len(en), 1), energy_lt35=sum(1 for e in en if e < 35),
                       share_lt35=round(sum(1 for e in en if e < 35) / len(en), 3),
                       dusk_energy_mean=round(sum(dusk) / len(dusk), 1) if dusk else None,
                       dusk_energy_p10=round(dusk[int(.1 * len(dusk))], 1) if dusk else None,
                       dusk_energy_med=round(dusk[len(dusk) // 2], 1) if dusk else None,
                       dusk_share_lt35=round(sum(1 for e in dusk if e < 35) / len(dusk), 3) if dusk else None)
        jl = [eng.node(j)["attrs"] for j in eng.nodes("Job")]
        row["jobs_total"] = len(jl); row["jobs_complete"] = sum(1 for a in jl if float(a.get("complete", 0)) == 1.0)
        row["jobs_open_paused"] = sum(1 for a in jl if float(a.get("complete", 0)) != 1.0 and w.job_paused(str(a.get("canonical_actor", ""))))
        row["jobs_open_running"] = sum(1 for a in jl if float(a.get("complete", 0)) != 1.0 and not w.job_paused(str(a.get("canonical_actor", ""))))
        try:
            row["crops_alive"] = len(list(w._living_crops())); row["crops_nodes"] = len(eng.nodes("Crop"))
        except Exception:
            pass
        row["food_store"] = round(food_store(), 1)
        row["food_held"] = round(food_held(), 1)
        row["deaths_cum"] = len(w._deaths)
        row["deaths_cause_cum"] = dict(collections.Counter(d["cause"] for d in w._deaths))
        rc = w.refusal_counts()
        row["refusals_day"] = {k: v - refusals_prev["by_reason"].get(k, 0) for k, v in rc["by_reason"].items()}
        row["refusals_by_action_day"] = {a: {k: v - refusals_prev["by_action"].get(a, {}).get(k, 0) for k, v in d.items()}
                                          for a, d in rc["by_action"].items()}
        refusals_prev = rc
        row["acts"] = dict(act_ct[day])
        row["elapsed_s"] = round(time.time() - t0, 1)
        days_out.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ("refusals_by_action_day",)}), flush=True)
        if not alive:
            break

# ----------------------------------------------------------------------------- summary
layout = {}
for n in names:
    layout[n] = dict(role=role[n], home=pos0[n], work=work_cell[n],
                     home_work=dist(pos0[n], work_cell[n]) if work_cell[n][0] >= 0 else None,
                     work_store=dist(work_cell[n], store_cell) if (store_cell and work_cell[n][0] >= 0) else None,
                     home_store=dist(pos0[n], store_cell) if store_cell else None)

lamp_days = []
if args.daynight and lp_ticks:
    tpd = int(BE.TIME["ticks_per_day"])
    last_clock = lp_ticks[-1]["clock"]
    for day in range(args.days):
        sunrise, sunset, length = D.sunrise_sunset(day % int(BE.TIME["days_per_year"]), BE.DAYNIGHT)
        base = day * tpd
        sr = base + (sunrise - float(BE.TIME["start_hour"])) * tpd / 24.0
        ss = base + (sunset - float(BE.TIME["start_hour"])) * tpd / 24.0
        day_rows = [r for r in lp_ticks if base <= r["clock"] < base + tpd]
        if not day_rows:
            continue
        after = [r for r in lp_ticks if r["clock"] >= ss and r["clock"] < sr + tpd]
        all_lit = next((r for r in after if r["lit"] == len(w._dn_lamps)), None)
        all_dark = next((r for r in lp_ticks if r["clock"] >= sr and r["lit"] == 0 and r["clock"] < ss), None)
        per = {}
        for n in LP:
            rows = [r["lp"][n] for r in day_rows]
            ens = [x["energy"] for x in rows if x["energy"] is not None]
            acts = collections.Counter(x["act"] for x in rows)
            per[n] = dict(role=role[n], min_energy=min(ens) if ens else None, alive_end=rows[-1]["alive"], max_hunger=max([x["hunger"] for x in rows if x["hunger"] is not None] or [None]),
                          light=acts.get("light", 0), douse=acts.get("douse", 0), duty_ticks=sum(1 for x in rows if x["reason"] == "duty"),
                          sleep_ticks=sum(1 for x in rows if x["asleep"]), rest_ticks=acts.get("rest", 0))
        lamp_days.append(dict(day=day, sunrise=round(sunrise, 2), sunset=round(sunset, 2),
                              dusk_all_lit_h=round((all_lit["clock"] - ss) / (tpd / 24.0), 2) if all_lit and all_lit["clock"] >= ss else None,
                              dawn_all_dark_h=round((all_dark["clock"] - sr) / (tpd / 24.0), 2) if all_dark else None,
                              town_alive_end=sum(1 for n in names if w.is_alive(n)) if False else None, lamplighters=per))
out = dict(lever=LEVER, lamp_days=lamp_days, lamplighters=LP, lp_role_identity={n: g.backends[n].character.personality.get("role_identity") for n in LP}, seed=args.seed, days=args.days, store_cell=store_cell,
           rows=days_out,
           deaths=[dict(actor=d["actor"], day=d["day"], cause=d["cause"]) for d in w._deaths],
           cat_ticks={f"{d}|{r}": dict(c) for (d, r), c in cat_ticks.items()},
           cells={f"{d}|{r}": v for (d, r), v in cells_day.items()},
           E_spent={f"{d}|{r}": dict(c) for (d, r), c in E_spent.items()},
           E_gain={f"{d}|{r}": dict(c) for (d, r), c in E_gain.items()},
           act_role={f"{d}|{r}": dict(c) for (d, r), c in act_role.items()},
           completions={f"{d}|{r}": v for (d, r), v in completions.items()},
           completions_role={f"{d}|{r}|{x}": v for (d, r, x), v in completions_role.items()},
           prod_kind={f"{d}|{k}": round(v, 2) for (d, k), v in prod_kind.items()},
           fetch_units={f"{d}|{k}": v for (d, k), v in fetch_units.items()},
           eat_relief={str(d): round(v, 2) for d, v in eat_relief.items()},
           work_recipes={f"{d}|{r}|{x}": v for (d, r, x), v in work_recipes.items()},
           decisions={f"{d}|{r}": dict(c) for (d, r), c in dec.items()},
           trace={n: v for n, v in list(trace.items())[:40]},
           stay_ct={str(k): v for k, v in stay_ct.items()}, dist_end=dist_end, E_band={f"{d}|{b}": dict(c) for (d, b), c in E_band.items()},
           at_work_ticks={f"{d}|{r}": v for (d, r), v in at_work_ticks.items()}, arrive_tick=arrive_tick,
           starts_recipe={f"{d}|{r}": v for (d, r), v in starts_recipe.items()},
           starts_role_recipe={f"{d}|{r}|{x}": v for (d, r, x), v in starts_role_recipe.items()},
           eat_val={str(k): round(v, 3) for k, v in eat_val.items()}, eat_n={str(k): v for k, v in eat_n.items()},
           eaters={str(k): len(v) for k, v in eaters.items()}, bread_cond=bread_cond, layout=layout, roles=dict(role), elapsed_s=round(time.time() - t0, 1))
if args.out:
    json.dump(out, open(args.out, "w"), default=str)
    if args.daynight:
        json.dump(lp_ticks, open(args.out + ".lpticks", "w"), default=str)
print("DONE", LEVER, args.seed, round(time.time() - t0, 1), "s", flush=True)
