"""population.py -- how a founding Bigville population is drawn, as data and pure functions.

Innate preference distributions (taste, colour, food neophobia) and the psychology of preference;
body distributions (strength, stamina); provisioning traits; starting education by station; and the
founding town -- BALANCE_SCENARIO and its scaling -- with the job seeding that staffs it sustainably
(seed_jobs, check_job_seed). The individual varies; the distribution is the fact.
"""
from __future__ import annotations
from domains.world_affordances import (
    ANIMALS,
    CROPS,
    ITEMS,
    LIFE_STAGES,
    PASTURE_YIELDS,
    RECIPES,
    WATER_SOURCES,
    _balance_flows,
    _recipes_for,
    feed_kinds,
)
from domains.shared_frames import (
    JOBS,
    METASKILLS,
    SKILL_LIMITATIONS,
    KIN_TERMS,
    INHERITANCE_CUSTOM,
)

from domains.pack import load_pack as _load_pack

# Tables and constants below are read from the "bigville" data pack (packs/bigville/).
# Their explanatory comments are in the pack files as "_doc"; domains/pack.py
# compiles the derived entries. Functions in this module read these names unchanged.
_PACK = _load_pack(globals().get("_PACK_NAME", "bigville"))   # data_view seeds _PACK_NAME
STATION_EDUCATION = _PACK["STATION_EDUCATION"]
PREFERENCE_RESEARCH = _PACK["PREFERENCE_RESEARCH"]
BITTER_TASTER_STATUS = _PACK["BITTER_TASTER_STATUS"]
BITTER_LIKING_BY_STATUS = _PACK["BITTER_LIKING_BY_STATUS"]
COLOUR_PREFERENCE = _PACK["COLOUR_PREFERENCE"]
TASTE_PREFERENCE = _PACK["TASTE_PREFERENCE"]
CILANTRO_SOAPY_FRACTION = _PACK["CILANTRO_SOAPY_FRACTION"]
FOOD_NEOPHOBIA = _PACK["FOOD_NEOPHOBIA"]
SSAT_RATE = _PACK["SSAT_RATE"]
NOVELTY_SWING = _PACK["NOVELTY_SWING"]
MERE_EXPOSURE_GAIN = _PACK["MERE_EXPOSURE_GAIN"]
MERE_EXPOSURE_DECAY = _PACK["MERE_EXPOSURE_DECAY"]
PHYSIQUE = _PACK["PHYSIQUE"]
APTITUDE = _PACK["APTITUDE"]
TALENT = _PACK["TALENT"]
LIMITATION_PREVALENCE = _PACK["LIMITATION_PREVALENCE"]
PLAN_HORIZON = _PACK["PLAN_HORIZON"]
BALANCE_SCENARIO = _PACK["BALANCE_SCENARIO"]
JOB_REFERENCE_PER_100 = _PACK["JOB_REFERENCE_PER_100"]
JOB_TARGET_LOAD = _PACK["JOB_TARGET_LOAD"]
# Founding households and kin (Phase 009); sources and APPROX marks in packs/bigville/population/household_composition.json.
HOUSEHOLD_SIZE = _PACK["HOUSEHOLD_SIZE"]
EXTENDED_FAMILY = _PACK["EXTENDED_FAMILY"]
EXTENDED_KIN = _PACK["EXTENDED_KIN"]
AGE_AT_FIRST_UNION = _PACK["AGE_AT_FIRST_UNION"]
CHILDREN_PER_UNION = _PACK["CHILDREN_PER_UNION"]
INFANT_SURVIVAL = _PACK["INFANT_SURVIVAL"]
ADULT_LIFESPAN = _PACK["ADULT_LIFESPAN"]
PARENT_AGE_AT_BIRTH = _PACK["PARENT_AGE_AT_BIRTH"]
KIN_MODEL = _PACK["KIN_MODEL"]
KINSHIP_STREAM = _PACK["KINSHIP_STREAM"]
HOUSEHOLD_TARGETS = _PACK["HOUSEHOLD_TARGETS"]
# The founding cast (Phase 016a; reshaped in 016b): who lives in the founding town and how their traits are drawn.
# Empty in a pack with no founding town. Sources and APPROX marks: packs/bigville/population/founding_*.json.
FOUNDING_JOBS = _PACK["FOUNDING_JOBS"]
FOUNDING_AGE = _PACK["FOUNDING_AGE"]
FOUNDING_CLASS = _PACK["FOUNDING_CLASS"]
FOUNDING_ANCHOR_NAMES = _PACK["FOUNDING_ANCHOR_NAMES"]
FOUNDING_DRAW_BOUNDS = _PACK["FOUNDING_DRAW_BOUNDS"]
FOUNDING_FIRST_NAMES = _PACK["FOUNDING_FIRST_NAMES"]
FOUNDING_LAST_NAMES = _PACK["FOUNDING_LAST_NAMES"]
FOUNDING_PERSONALITY = _PACK["FOUNDING_PERSONALITY"]
FOUNDING_CAUSAL_RESOLUTION = _PACK["FOUNDING_CAUSAL_RESOLUTION"]


def _draw_categorical(rng, dist):
    ks = list(dist)
    return str(ks[int(rng.choice(len(ks), p=[dist[k] for k in ks]))])


def draw_favourite_colour(rng):
    """Draw a person's favourite colour from the (blue-led) population distribution."""
    return _draw_categorical(rng, COLOUR_PREFERENCE)


def draw_bitter_status(rng):
    """Draw a person's bitter-taster status (25/50/25 -- non/medium/super)."""
    return _draw_categorical(rng, BITTER_TASTER_STATUS)


def draw_taste_liking(rng, taste):
    """Draw a person's liking (0..1) for a basic taste from its population mean/sd."""
    d = TASTE_PREFERENCE[taste]
    return float(min(1.0, max(0.0, rng.normal(d["mean"], d["sd"]))))


def draw_person_preferences(rng):
    """One person's innate preferences drawn from the researched distributions -- the seed a heterogeneous
    population is built from (the individual varies; the distribution is the grounded fact)."""
    status = draw_bitter_status(rng)
    taste = {t: draw_taste_liking(rng, t) for t in TASTE_PREFERENCE}
    # bitter liking is set by the trimodal taster status, not the marginal mean
    taste["bitter"] = float(min(1.0, max(0.0, rng.normal(BITTER_LIKING_BY_STATUS[status], 0.08))))
    return {"favourite_colour": draw_favourite_colour(rng), "bitter_status": status,
            "cilantro_soapy": bool(rng.random() < CILANTRO_SOAPY_FRACTION), "taste": taste,
            "food_neophobia": draw_food_neophobia(rng)}


def draw_food_neophobia(rng):
    """A person's food-neophobia trait (0 variety-seeker .. 1 routine-lover), drawn from the population."""
    return float(min(1.0, max(0.0, rng.normal(FOOD_NEOPHOBIA["mean"], FOOD_NEOPHOBIA["sd"]))))


def meal_satisfaction(base_liking, recent_repeats, neophobia, *, novel=False):
    """Satisfaction (0..1) from a meal: the base liking, DISCOUNTED by sensory-specific satiety (how many
    times this same food was eaten recently), and shifted by neophobia for a novel food. A variety-seeker
    (low neophobia) satiates fast on repetition but enjoys novelty; a routine-lover barely satiates and
    dislikes novelty. This is why a monotonous diet costs a variety-seeker far more."""
    satiety_rate = SSAT_RATE * (1.0 - float(neophobia))         # routine-lovers barely satiate
    ssat = 1.0 / (1.0 + satiety_rate * max(0, recent_repeats))
    novelty_adj = (NOVELTY_SWING * (0.5 - float(neophobia))) if novel else 0.0
    return float(min(1.0, max(0.0, base_liking * ssat + novelty_adj)))


def simulate_diet(sequence, likings, neophobia):
    """Eat a `sequence` of food kinds; return per-meal satisfaction. Sensory-specific satiety builds while
    the same food repeats and RESETS on variety. `likings` maps kind -> base liking (from taste). The mean
    is the diet's wellbeing: a repetitive (poor) diet sinks it; a varied one keeps it high."""
    sats, last, run = [], None, 0
    for food in sequence:
        run = run + 1 if food == last else 0
        sats.append(meal_satisfaction(likings.get(food, 0.5), run, neophobia))
        last = food
    return sats


def satiety_level(recent_repeats, neophobia):
    """How SICK of a food you are after eating it `recent_repeats` times in a row (0 fresh .. ->1) -- the
    complement of the sensory-specific-satiety factor. This is the APPETITE dimension the choice weighs:
    'what do I feel like'. A variety-seeker satiates (and so craves change) faster than a routine-lover."""
    rate = SSAT_RATE * (1.0 - float(neophobia))
    return float(1.0 - 1.0 / (1.0 + rate * max(0, int(recent_repeats))))


def mere_exposure_liking(base_liking, exposures):
    """Familiarity raises liking toward a ceiling (Zajonc) -- a food grows on you with repeated exposure.
    The slow long-term counter-force to short-term satiety."""
    ceiling = base_liking + MERE_EXPOSURE_GAIN * (1.0 - base_liking)
    approached = 1.0 - MERE_EXPOSURE_DECAY ** max(0, int(exposures))
    return float(min(1.0, base_liking + (ceiling - base_liking) * approached))


def draw_physique(rng):
    """Draw a person's base strength + stamina: a shared general-fitness component plus an independent
    per-stat draw, floored. The variation IS the point -- a strong person and a weak one, a sprinter
    and an endurance type, all from one distribution."""
    g = float(rng.normal(0.0, PHYSIQUE["shared_sd"]))       # general fitness raises/lowers both together
    def one():
        return float(max(PHYSIQUE["floor"], PHYSIQUE["mean"] + g + rng.normal(0.0, PHYSIQUE["sd"])))
    return {"str_base": one(), "sta_base": one()}


def _age_rate(points, age):
    rate = 0.0
    for start, value in points:
        if age >= start:
            rate = value
    return rate


def limitation_rate(name, *, age=30.0, sex=None, present=()):
    """The probability a person of this age/sex has a limitation, given ones already drawn."""
    spec = LIMITATION_PREVALENCE[name]
    rate = spec.get("rate", 0.0)
    if isinstance(rate, dict):
        rate = rate.get(sex, sum(rate.values()) / len(rate))
    if "rate_by_age" in spec:
        rate = _age_rate(spec["rate_by_age"], age)
    if "rate_by_age_sex" in spec:
        by_sex = spec["rate_by_age_sex"]
        sexes = [sex] if sex in by_sex else list(by_sex)          # unknown sex: average the sexes
        if any(age >= start for s_ in sexes for start, _ in by_sex[s_]):
            rate = sum(_age_rate(by_sex[s_], age) for s_ in sexes) / len(sexes)
    if age >= 18:
        rate *= float(spec.get("persistence", 1.0))
    for other, conditional in spec.get("given", {}).items():
        if other in present:
            rate = max(rate, float(conditional))
    return float(rate)


def draw_person_capacities(rng, *, age=30.0, sex=None):
    """One person's aptitude, metaskill talents, and limitations, drawn from the distributions above.

    `rng` is a numpy Generator. Returns {"aptitude", "aptitude_base", "talents", "limitations"}."""
    aptitude = float(max(APTITUDE["floor"], rng.normal(APTITUDE["mean"], APTITUDE["sd"])))
    talents = {m: round(float(max(TALENT["floor"], rng.normal(TALENT["mean"], TALENT["sd"]))), 4)
               for m in METASKILLS}
    present = []
    # conditions with no comorbidity dependence first, so `given` can see them
    order = sorted(LIMITATION_PREVALENCE, key=lambda n: (bool(LIMITATION_PREVALENCE[n].get("given")), n))
    for name in order:
        if rng.random() < limitation_rate(name, age=age, sex=sex, present=present):
            present.append(name)
    return {"aptitude": round(aptitude, 4), "aptitude_base": round(aptitude, 4),
            "talents": talents, "limitations": sorted(present)}


def describe_capacity_distribution(n=10000, *, seed=1, age=35.0):
    """Draw `n` adults (half each sex) and summarise them: for checking against the sources."""
    import numpy as np
    rng = np.random.default_rng(seed)
    people = [draw_person_capacities(rng, age=age, sex=("male", "female")[i % 2]) for i in range(n)]
    aptitudes = sorted(p["aptitude"] for p in people)
    rates = {name: sum(name in p["limitations"] for p in people) / n for name in LIMITATION_PREVALENCE}
    return {"n": n, "age": age,
            "aptitude_mean": round(sum(aptitudes) / n, 4),
            "aptitude_p02": aptitudes[int(0.02 * n)], "aptitude_p98": aptitudes[int(0.98 * n)],
            "any_limitation": round(sum(bool(p["limitations"]) for p in people) / n, 4),
            "limitation_rates": {k: round(v, 4) for k, v in rates.items()}}


def draw_plan_horizon(rng):
    """A person's planning horizon (days ahead they provision) -- a distributed trait. Some plan a week
    out; some live day-to-day. Floored at 1 (you always at least sort out today)."""
    return float(max(PLAN_HORIZON["min"], round(rng.normal(PLAN_HORIZON["mean"], PLAN_HORIZON["sd"]))))


def larder_for_wealth(coin, *, per_coin=0.5, floor=1.0, cap=20.0):
    """The larder capacity a given wealth can afford -- storage scales with means (floored at 1: everyone
    can keep a little; capped). The poor hold ~1 day and buy daily; the rich buy in bulk and buffer. APPROX."""
    return float(min(cap, max(floor, per_coin * float(coin))))


def scale_scenario(population):
    """BALANCE_SCENARIO resized to a town of `population` working residents."""
    import math
    base = BALANCE_SCENARIO
    if not base:   # a pack without a founding balance scenario
        return {}
    f = float(population) / float(base["residents"])
    beds = {c: max(1, int(round(n * f))) for c, n in base["beds"].items()}
    # water: the town opens sources (in the founding town's order) until they cover its fields and
    # staple with a 20% margin
    staple = next(r for r in RECIPES if r["name"] == base["staple"])
    demand = sum(float(n) * float(CROPS[c]["water"]) for c, n in beds.items())
    demand += (float(population) * float(base["food_per_resident"]) / float(staple["out"][1])
               * sum(float(q) for k, q in staple["in"] if k == "water"))
    sources, water = [], 0.0
    while water < 1.2 * demand or not sources:
        kind = base["water_sources"][len(sources) % len(base["water_sources"])]
        sources.append(kind)
        water += float(WATER_SOURCES[kind]["yield"])
    animals = {a: int(round(n * f)) for a, n in base["animals"].items()}
    # pasture: enough area to graze the herd (20% margin), never less than the scaled founding area
    pasture = float(base["pasture_area"]) * f
    for diet in {ANIMALS[a]["eats"] for a, n in animals.items() if n}:
        per_area = sum(float(PASTURE_YIELDS.get(k, 0.0)) for k in feed_kinds(diet))
        need = sum(float(n) * float(ANIMALS[a].get("ration", 1)) for a, n in animals.items()
                   if ANIMALS[a]["eats"] == diet)
        if per_area > 0:
            pasture = max(pasture, 1.2 * need / per_area)
    return dict(base, residents=int(population), beds=beds,
                plots=max(1, int(math.ceil(base["plots"] * f))),
                animals=animals,
                pasture_area=round(pasture, 2),
                woodland=max(1.0, f),                       # one woodlot at least, more for a city
                water_sources=sources)


def job_requirements(population):
    """{job: full-time workers needed} for a town of `population`, plus the work streams behind it."""
    sc = scale_scenario(population)
    flows, notes, work = _balance_flows(sc)
    # With no balance scenario `work` is empty, so this divisor is never used (it avoids a KeyError).
    day = float(sc.get("work_minutes_per_resident", 1.0))
    fte = {}
    for job, spec in JOBS.items():
        load = sum(float(share) * work.get(stream, 0.0) / day for stream, share in spec.get("duties", {}).items())
        load += float(spec.get("fixed", 0.0)) + float(spec.get("per_100", 0.0)) * float(population) / 100.0
        fte[job] = round(load, 4)
    return fte, work, flows, sc


def job_weights(population=100):
    """The RELATIVE weight of each job: the share of the town's residents it needs."""
    fte, _, _, _ = job_requirements(population)
    return {job: round(load / float(population), 4) for job, load in fte.items()}


def seed_jobs(population):
    """Assign jobs to `population` founding residents.

    Returns {"residents": [{"jobs", "trades", "tools", "load"}...], "fte", "holders", "short"}.
    Every job with any load gets at least one holder. Each job's load is cut into whole days plus a
    remainder, and the pieces are dealt largest-first to whoever is least loaded so far, so a hamlet
    spreads its offices and crafts across everyone rather than heaping them on one person. Residents
    left with nothing join the production job most loaded per holder, until each is at
    JOB_TARGET_LOAD or below; the rest become labourers. `short` is how many more people the jobs
    need than `population` (0 when the town can staff itself)."""
    import math
    n = int(population)
    fte, _, _, _ = job_requirements(population)
    pieces = []
    for job, load in fte.items():
        whole = int(load)
        pieces += [(1.0, job)] * whole
        if load - whole > 1e-9:
            pieces.append((load - whole, job))
    pieces.sort(key=lambda p: (-p[0], p[1]))
    total = sum(fte.values())
    short = max(0, int(math.ceil(total - 1e-9)) - n, len([p for p in pieces if p[0] >= 1.0]) - n)
    people = [{"jobs": {}} for _ in range(max(n, 1))]
    for load, job in pieces:
        # least loaded person who does not already hold this job (else least loaded overall)
        fresh = [p for p in people if job not in p["jobs"]] or people
        person = min(fresh, key=lambda p: sum(p["jobs"].values()))
        person["jobs"][job] = person["jobs"].get(job, 0.0) + load
    if max(sum(p["jobs"].values()) for p in people) > 1.0 + 1e-6:
        short = max(short, 1)
    holders = {job: sum(1 for p in people if job in p["jobs"]) for job in fte}
    production = [job for job, spec in JOBS.items() if spec.get("duties") and fte[job] > 0]
    spare = next(j for j, spec in JOBS.items() if spec.get("spare"))
    for person in [p for p in people if not p["jobs"]]:
        loads = {job: fte[job] / holders[job] for job in production if holders[job]}
        job = max(loads, key=lambda j: (loads[j], j)) if loads else None
        if job is None or loads[job] <= JOB_TARGET_LOAD:
            job = spare
        person["jobs"][job] = 0.0
        holders[job] = holders.get(job, 0) + 1
    residents = []
    for p in people:
        jobs = sorted(p["jobs"], key=lambda j: (-p["jobs"][j], j))
        trades, tools = [], []
        for job in jobs:
            trades += [t for t in JOBS[job]["trades"] if t not in trades]
            tools += [t for t in JOBS[job].get("tools", []) if t not in tools]
        residents.append({"jobs": jobs, "trades": trades, "tools": tools,
                          "load": round(sum(p["jobs"].values()), 4)})
    return {"residents": residents, "fte": fte, "holders": holders, "short": short}


def check_job_seed(population):
    """Is the seeded town of `population` sustainable at the start? Returns {"ok", "issues", ...}."""
    seed = seed_jobs(population)
    fte, work, flows, sc = job_requirements(population)
    issues = []
    if seed["short"]:
        issues.append(f"LABOUR: the jobs need {population + seed['short']} people; only {population} "
                      f"are seeded ({seed['short']} short)")
    for job, load in fte.items():
        if load > 0 and seed["holders"].get(job, 0) == 0:
            issues.append(f"UNSTAFFED {job}: needs {load:.2f} full-time but no one holds it")
    for name, (supply, demand) in flows.items():
        if demand > 0 and supply < demand:
            issues.append(f"DEFICIT {name}: supply {supply:.1f} vs demand {demand:.1f} per period")
    for job, (lo, hi) in JOB_REFERENCE_PER_100.items():
        per_100 = fte.get(job, 0.0) * 100.0 / float(population)
        if not lo <= per_100 <= hi:
            issues.append(f"UNREALISTIC {job}: {per_100:.2f} full-time per 100 residents; history suggests "
                          f"{lo}-{hi} (check the recipe's batch size and time)")
    for job, spec in JOBS.items():
        for tool in spec.get("tools", []):
            if not _recipes_for(tool) and not ITEMS.get(tool, {}).get("imported"):
                issues.append(f"TOOL {tool} for {job} cannot be made or imported to replace a worn one")
    return {"ok": not issues, "issues": issues, "seed": seed, "fte": fte, "work": work,
            "flows": flows, "scenario": sc}


def format_jobs_report(populations=(100, 30, 8)):
    """Render the job weights and the seeded staffing for several town sizes."""
    lines = ["JOBS (full-time equivalents needed -> holders seeded; relative weight = share of residents)"]
    checks = {n: check_job_seed(n) for n in populations}
    weights = job_weights(100)
    head = "  " + "job".ljust(15) + "weight".rjust(8) + "".join(f"N={n}".rjust(18) for n in populations)
    lines.append(head)
    for job in JOBS:
        row = "  " + job.ljust(15) + f"{weights[job]:>8.3f}"
        for n in populations:
            c = checks[n]
            row += f"{c['fte'][job]:>8.2f} -> {c['seed']['holders'].get(job, 0):>3}".rjust(18)
        lines.append(row)
    for n in populations:
        c = checks[n]
        multi = [r for r in c["seed"]["residents"] if len(r["jobs"]) > 1]
        lines.append(f"  N={n}: {len(c['seed']['residents'])} residents, {len(multi)} holding several jobs"
                     + (f" (e.g. {' + '.join(multi[0]['jobs'])})" if multi else "")
                     + f"; sustainable start: {c['ok']}")
        for issue in c["issues"]:
            lines.append(f"    - {issue}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Households and kin (Phase 009)
# ---------------------------------------------------------------------------
# Genealogy is a world fact: persons, births (parent to child, bore or fathered by the parent's sex), and
# unions with their periods. Kin terms are not facts: a resident holds them. The functions below draw a
# founding household and a founding genealogy from the cited distributions, index a genealogy, match
# KIN_TERMS paths against it, and list the genealogical heirs of a death under the inheritance custom.
# Periods are years; the founding year is 0 and the present is `now`.


def _clipped_normal(rng, spec):
    v = float(rng.normal(spec["mean"], spec["sd"]))
    if spec.get("min") is not None:
        v = max(float(spec["min"]), v)
    if spec.get("max") is not None:
        v = min(float(spec["max"]), v)
    return v


def _child_count(rng):
    """Children ever born to a union (CHILDREN_PER_UNION), at least zero."""
    return max(0, int(round(_clipped_normal(rng, CHILDREN_PER_UNION))))


def draw_household_size(rng):
    """A founding household's member count, from HOUSEHOLD_SIZE (9 means nine or more)."""
    sizes = sorted(HOUSEHOLD_SIZE, key=int)
    return int(sizes[int(rng.choice(len(sizes), p=[HOUSEHOLD_SIZE[k] for k in sizes]))])


def draw_household(rng):
    """One founding household: its size, whether a kinsman beyond the nuclear family lives in it
    (EXTENDED_FAMILY), and which kinsman (EXTENDED_KIN)."""
    size = draw_household_size(rng)
    extended = bool(rng.random() < float(EXTENDED_FAMILY))
    kin = _draw_categorical(rng, EXTENDED_KIN) if extended else None
    if extended:
        size = max(size, 2)
    return {"size": size, "extended": extended, "kin": kin}


def describe_household_distribution(n=20000, *, seed=1):
    """Draw `n` households and summarise them against HOUSEHOLD_TARGETS (the self-test's check)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    homes = [draw_household(rng) for _ in range(n)]
    return {"n": n,
            "mean_size": round(sum(h["size"] for h in homes) / n, 4),
            "extended_share": round(sum(h["extended"] for h in homes) / n, 4),
            "grandparent_share": round(sum(h["kin"] == "grandparent" for h in homes) / n, 4)}


def _sex_of(rng, sex=None):
    if sex in ("male", "female"):
        return sex
    return "female" if rng.random() < 0.5 else "male"


def draw_founding_ages(n, seed):
    """Ages (whole years) of `n` founders: a clipped Normal from FOUNDING_AGE on its own stream
    (seed + FOUNDING_AGE['stream']), so no other draw of the founding town moves when ages change."""
    import numpy as np
    rng = np.random.default_rng(int(seed) + int(FOUNDING_AGE["stream"]))
    return [int(round(_clipped_normal(rng, FOUNDING_AGE))) for _ in range(int(n))]


def draw_founding_households(ages, sexes, rng):
    """Group the founders into households (Phase 016b). Each household is:

    * a head: the first founder, in a seeded order, aged at least AGE_AT_FIRST_UNION.male.mean (a
      founder who has had time to marry and have children); if none is left, the first left over;
    * married with probability EVER_MARRIED. The spouse lives in the household only if an opposite-sex
      founder of similar age (within ten years, both adult) is free and a SPOUSE_IN_VILLAGE draw succeeds;
      otherwise the spouse is outside the village (the genealogy records the union either way);
    * the head's adult children: free founders at least PARENT_AGE_AT_BIRTH.female.min years younger than
      each parent (the youngest parent sets the limit), filled up to the drawn size;
    * for a household whose drawn extended kin is a sibling, one free adult founder whose age is within
      SIBLING_MAX_GAP_YEARS of the head's. Grandparents and other kin are not founders, so an extended
      household drawn with them has no founder kin (see the report).

    The size is the draw_household size (HOUSEHOLD_SIZE): it caps the household, it does not force it.
    Children under 18 are not modelled, so a household holds only the founders who fit the rules above.
    Returns a list of dicts with founder indices: head, spouse, children, siblings, members, size_drawn,
    extended_drawn, kin_drawn, extended (a sibling lives in it), married (a union, co-resident or not)."""
    adult = float(LIFE_STAGES["adult"]["age_min"])
    head_min = float(AGE_AT_FIRST_UNION["male"]["mean"])
    gap = float(PARENT_AGE_AT_BIRTH["female"]["min"])
    sibling_gap = float(KIN_MODEL["SIBLING_MAX_GAP_YEARS"])
    order = [int(i) for i in rng.permutation(len(ages))]
    taken, households = set(), []
    while len(taken) < len(ages):
        pool = [i for i in order if i not in taken]
        eligible = [i for i in pool if ages[i] >= head_min]
        head = (eligible or pool)[0]
        taken.add(head)
        drawn = draw_household(rng)
        married = bool(rng.random() < float(KIN_MODEL["EVER_MARRIED"]))
        spouse = None
        if married:
            cands = [i for i in order if i not in taken and sexes[i] != sexes[head]
                     and abs(ages[i] - ages[head]) <= 10 and min(ages[i], ages[head]) >= adult]
            if cands and rng.random() < float(KIN_MODEL["SPOUSE_IN_VILLAGE"]):
                spouse = cands[0]
                taken.add(spouse)
        parents = [ages[head]] + ([ages[spouse]] if spouse is not None else [])
        slots = drawn["size"] - (1 if spouse is None else 2)
        children = []
        for i in order:
            if slots <= 0:
                break
            if i not in taken and adult <= ages[i] <= min(parents) - gap:
                children.append(i)
                taken.add(i)
                slots -= 1
        siblings = []
        if drawn["extended"] and drawn["kin"] == "sibling" and slots > 0:
            for i in order:
                if i not in taken and adult <= ages[i] and abs(ages[i] - ages[head]) <= sibling_gap:
                    siblings.append(i)
                    taken.add(i)
                    break
        members = [head] + ([spouse] if spouse is not None else []) + children + siblings
        households.append({"index": len(households), "head": head, "spouse": spouse, "children": children,
                           "siblings": siblings, "members": members, "size_drawn": drawn["size"],
                           "extended_drawn": drawn["extended"], "kin_drawn": drawn["kin"],
                           "extended": bool(siblings), "married": married})
    return households


def draw_founding_kin(founders, rng, *, present=0.0):
    """Draw the households and genealogy of a founding population from the cited distributions.

    `founders` is a list of {"name", "age"} (and optionally "sex"), in cast order; founder i is person i.
    The households come first (draw_founding_households). The genealogy is then fitted to them:

    * the head's parents are a couple who bear the head and the head's siblings (who share parents);
      the couple's other children (aunts and uncles) are outside the village. The head's parents'
      parents are a couple already in the record with probability GRANDPARENT_REUSE, else a new couple;
    * the spouse's parents are a couple of their own;
    * a head and a co-resident spouse form a union, which starts after both are of age and before their
      first child (a union starts at the first of its children's births less one year, and never after
      the founding year). Their children are the household's adult children, plus any outside children
      up to CHILDREN_PER_UNION;
    * a head with no spouse bears their adult children alone (a single parent on record). No outside
      partner is invented.

    Returns {"persons", "births", "unions", "founders", "households"}. Persons are dicts {id, name, sex,
    birth, death, in_village, founder} (death None = alive at `present`); births are {parent, child,
    period}; unions are {a, b, start, end} (end None = still joined); households are the draw_founding_
    households records. Everything comes from `rng`, so a seed fixes it.
    """
    persons, births, unions = [], [], []
    now = float(present)

    def person(name, sex, birth, *, in_village=False, founder=False):
        pid = len(persons)
        persons.append({"id": pid, "name": name, "sex": sex, "birth": float(birth), "death": None,
                        "in_village": bool(in_village), "founder": bool(founder)})
        return pid

    def mortal(pid, *, not_before=None, infant=False):
        """Give a person a death drawn from ADULT_LIFESPAN (None when alive at `now`). A parent dies no
        earlier than `not_before`, the birth of a child they had. An infant may die in the first year."""
        p = persons[pid]
        if infant and p["birth"] + 0.5 <= now and rng.random() >= float(INFANT_SURVIVAL):
            p["death"] = p["birth"] + 0.5
            return pid
        life = max(0.0, float(rng.normal(ADULT_LIFESPAN["mean"], ADULT_LIFESPAN["sd"])))
        death = p["birth"] + life
        if not_before is not None:
            death = max(death, float(not_before) + 0.5)
        p["death"] = death if death <= now else None
        return pid

    def couple(a, b, start):
        deaths = [persons[x]["death"] for x in (a, b) if persons[x]["death"] is not None]
        end = min(deaths) if deaths else None
        unions.append({"a": a, "b": b, "start": float(start), "end": None if end is None else float(end)})

    def bear(parents, child, period):
        for parent in parents:
            births.append({"parent": parent, "child": child, "period": float(period)})

    def window_end(ids, hi):
        """The latest birth for a child of `ids`: before `hi`, the founding year, and each parent's death."""
        ends = [min(now, float(hi))] + [persons[x]["death"] for x in ids if persons[x]["death"] is not None]
        return min(ends) - 0.5

    def child_births(lo, hi, n):
        """Up to `n` birth periods in [lo, hi], one per stratum so they are spread out, capped so that
        CHILD_SPACING_YEARS separates them where the window allows."""
        if hi < lo or n <= 0:
            return []
        n = min(int(n), int((hi - lo) / float(KIN_MODEL["CHILD_SPACING_YEARS"])) + 1)
        width = (hi - lo) / n
        return [float(lo + (i + float(rng.random())) * width) for i in range(n)]

    def grandparent_couple(child_birth):
        """A couple born before a child born at `child_birth`, with their other children."""
        mb = child_birth - _clipped_normal(rng, PARENT_AGE_AT_BIRTH["female"])
        fb = child_birth - _clipped_normal(rng, PARENT_AGE_AT_BIRTH["male"])
        gm = mortal(person("", "female", mb), not_before=child_birth)
        gf = mortal(person("", "male", fb), not_before=child_birth)
        start = max(mb, fb) + 17.0
        couple(gf, gm, start)
        ids = (gf, gm)
        for b in child_births(start + 0.5, window_end(ids, min(mb + 42.0, fb + 60.0)),
                              _child_count(rng) - 1):
            kid = mortal(person("", _sex_of(rng), b), infant=True)
            bear(ids, kid, b)
        return {"ids": ids, "start": start, "hi": min(mb + 42.0, fb + 60.0)}

    pool = []

    def attach_to_grandparents(parent):
        pb = persons[parent]["birth"]
        options = []
        if rng.random() < float(KIN_MODEL["GRANDPARENT_REUSE"]):
            options = [g for g in pool if g["start"] + 0.5 <= pb <= window_end(g["ids"], g["hi"])]
        if options:
            g = options[int(rng.integers(len(options)))]
        else:
            g = grandparent_couple(pb)
            pool.append(g)
        bear(g["ids"], parent, pb)

    def parents_of(sibs):
        """A couple who are the parents of `sibs` (a list of (founder id, birth)), and of the others they
        had. The parents' births are set so that every sibling is born while each parent is of a
        plausible parenting age (PARENT_AGE_AT_BIRTH)."""
        eldest = min(b for _, b in sibs)
        youngest = max(b for _, b in sibs)
        mb = max(eldest - _clipped_normal(rng, PARENT_AGE_AT_BIRTH["female"]),
                 youngest - float(PARENT_AGE_AT_BIRTH["female"]["max"]))
        fb = max(eldest - _clipped_normal(rng, PARENT_AGE_AT_BIRTH["male"]),
                 youngest - float(PARENT_AGE_AT_BIRTH["male"]["max"]))
        mother = mortal(person("", "female", mb), not_before=youngest)
        father = mortal(person("", "male", fb), not_before=youngest)
        ids = (father, mother)
        start = min(max(mb, fb) + 17.0, eldest - 0.5)
        couple(father, mother, start)
        for sid, b in sibs:
            bear(ids, sid, b)
        for b in child_births(start + 0.5, window_end(ids, min(mb + 42.0, fb + 60.0)),
                              max(0, _child_count(rng) - len(sibs))):
            kid = mortal(person("", _sex_of(rng), b), infant=True)
            bear(ids, kid, b)
        attach_to_grandparents(father)
        attach_to_grandparents(mother)
        return ids

    sexes = [_sex_of(rng, f.get("sex")) for f in founders]
    ages = [float(f["age"]) for f in founders]
    founder_ids = [person(str(f.get("name", "")), sexes[i], now - ages[i], in_village=True, founder=True)
                   for i, f in enumerate(founders)]
    households = draw_founding_households(ages, sexes, rng)

    def marry(fid, spouse, kids):
        """A union of founder `fid` and `spouse` (a person id, or None for a spouse outside the village).
        The union starts after both partners are of age (AGE_AT_FIRST_UNION), no later than the founding
        year, and before the first of `kids`, the founders born to the couple. An outside spouse is born
        at most 16 years before the start and 18 years before the youngest child. The couple also has
        outside children, up to CHILDREN_PER_UNION. Returns the spouse's person id."""
        me = persons[fid]
        desired = me["birth"] + _clipped_normal(rng, AGE_AT_FIRST_UNION[me["sex"]])
        if spouse is not None:
            desired = max(desired, persons[spouse]["birth"] + _clipped_normal(rng, AGE_AT_FIRST_UNION[persons[spouse]["sex"]]))
        start = min(desired, now - 0.5)
        youngest = min((persons[k]["birth"] for k in kids), default=None)
        if youngest is not None:
            start = min(start, youngest - 1.0)
        if spouse is None:
            opposite = "male" if me["sex"] == "female" else "female"
            cap = start - 16.0 if youngest is None else min(start - 16.0, youngest - 18.0)
            spouse = mortal(person("", opposite, min(me["birth"] + float(rng.normal(0.0, 3.0)), cap)),
                            not_before=start)
        couple(fid, spouse, start)
        ids = (fid, spouse)
        for kid in kids:
            bear(ids, kid, persons[kid]["birth"])
        for b in child_births(start + 0.5, window_end(ids, now), max(0, _child_count(rng) - len(kids))):
            kid = mortal(person("", _sex_of(rng), b), infant=True)
            bear(ids, kid, b)
        return spouse

    decided = set()
    out = []
    for hh in households:
        head = founder_ids[hh["head"]]
        sibs = [(founder_ids[i], persons[founder_ids[i]]["birth"]) for i in [hh["head"]] + hh["siblings"]]
        parents_of(sibs)
        spouse = founder_ids[hh["spouse"]] if hh["spouse"] is not None else None
        if spouse is not None:
            parents_of([(spouse, persons[spouse]["birth"])])
        kids = [founder_ids[i] for i in hh["children"]]
        decided.add(head)
        if hh["married"]:
            if spouse is not None:
                decided.add(spouse)
            marry(head, spouse, kids)
        else:
            for kid in kids:
                bear((head,), kid, persons[kid]["birth"])
        out.append(dict(hh, head=head, spouse=spouse, children=kids,
                        siblings=[founder_ids[i] for i in hh["siblings"]],
                        members=[founder_ids[i] for i in hh["members"]]))
    # founders who are not a head or a spouse (adult children and siblings) may marry outside the village
    for fid in founder_ids:
        if fid not in decided and rng.random() < float(KIN_MODEL["EVER_MARRIED"]):
            marry(fid, None, [])
    return {"persons": persons, "births": births, "unions": unions, "founders": founder_ids,
            "households": out}


def index_kinship(persons, births, unions):
    """Index a genealogy for path queries. `persons` is a list of person dicts or an {id: dict} map."""
    people = {p["id"]: p for p in persons} if isinstance(persons, list) else dict(persons)
    parents = {pid: set() for pid in people}
    children = {pid: set() for pid in people}
    partners = {pid: [] for pid in people}
    for b in births:
        parents[b["child"]].add(b["parent"])
        children[b["parent"]].add(b["child"])
    for u in unions:
        partners[u["a"]].append(u)
        partners[u["b"]].append(u)
    return {"persons": people,
            "parents": {k: sorted(v) for k, v in parents.items()},
            "children": {k: sorted(v) for k, v in children.items()},
            "partners": partners}


def _alive_at(index, pid, now):
    p = index["persons"][pid]
    return p["birth"] <= now and (p["death"] is None or p["death"] > now)


def _partners_at(index, pid, now):
    """Partners joined to `pid` at `now` (a union counts from its start until its end)."""
    out = set()
    for u in index["partners"][pid]:
        if u["start"] > now or (u["end"] is not None and u["end"] <= now):
            continue
        out.add(u["b"] if u["a"] == pid else u["a"])
    return sorted(out)


def _step(index, nodes, token, now):
    out = set()
    for x in nodes:
        if token == "parent":
            out.update(index["parents"][x])
        elif token == "child":
            out.update(index["children"][x])
        elif token == "spouse":
            out.update(_partners_at(index, x, now))
        elif token == "sibling":
            for par in index["parents"][x]:
                out.update(c for c in index["children"][par] if c != x)
        else:
            raise ValueError(f"unknown kin step '{token}' (KIN_TERMS paths use parent, child, spouse, sibling)")
    return out


def kin_relatives(index, holder, now=0.0):
    """Everyone `holder` can place in a KIN_TERMS term by genealogy: {target id: (term, path)}.

    Each term's paths are followed from the holder. A target takes the first term in table order that
    fits (its sex, and shared_parents where the term sets it). Terms with no paths arise only by
    attribution and are never matched here."""
    result = {}
    for term, spec in KIN_TERMS.items():
        matched = {}
        for path in spec.get("paths", []):
            frontier = {holder}
            for token in path:
                frontier = _step(index, frontier, token, now)
            for target in frontier:
                if target != holder:
                    matched.setdefault(target, " > ".join(path))
        for target, path_text in sorted(matched.items()):
            if target in result:
                continue
            if spec.get("sex") and index["persons"][target]["sex"] != spec["sex"]:
                continue
            if "shared_parents" in spec:
                shared = len(set(index["parents"][holder]) & set(index["parents"][target]))
                if shared != (2 if spec["shared_parents"] == "both" else 1):
                    continue
            result[target] = (term, path_text)
    return result


def genealogical_heirs(index, deceased, now, custom=None):
    """Who inherits from `deceased` at `now` under `custom` (default INHERITANCE_CUSTOM's default).

    Returns [{"id", "kind", "share", "life_interest"}] for the first tier with living members. Shares
    are fractions of the estate. This only names the heirs: no property moves, and the deed type
    'inheritance' is for the records office to write."""
    spec = INHERITANCE_CUSTOM["customs"][custom or INHERITANCE_CUSTOM["default"]]
    groups = {
        "child": [c for c in index["children"][deceased] if _alive_at(index, c, now)],
        "parent": [p for p in index["parents"][deceased] if _alive_at(index, p, now)],
        "sibling": [s for s in _step(index, {deceased}, "sibling", now) if _alive_at(index, s, now)],
        "spouse": [s for s in _partners_at(index, deceased, now) if _alive_at(index, s, now)],
    }
    out = []
    if spec["spouse"] == "life_interest":
        out += [{"id": s, "kind": "spouse", "share": 0.0, "life_interest": True} for s in groups["spouse"]]
    for number, tier in enumerate(spec["tiers"]):
        members = [(kind, pid) for kind in tier["kinds"] for pid in groups[kind]]
        if number == 0 and spec["spouse"] == "share":
            members += [("spouse", pid) for pid in groups["spouse"]]
        if not members:
            continue
        if tier["rule"] == "eldest":
            kind, pid = min(members, key=lambda m: (index["persons"][m[1]]["birth"], m[1]))
            out.append({"id": pid, "kind": kind, "share": 1.0, "life_interest": False})
        else:
            out += [{"id": pid, "kind": kind, "share": 1.0 / len(members), "life_interest": False}
                    for kind, pid in members]
        break
    return out


def plan_founding_town(seed, size=None):
    """The founding cast's staffing, ages, households, and genealogy, all from one seed (Phase 016b).

    `staffing` is E.seed_jobs(size): each resident's jobs, in cast order. `ages` are the founders' ages on
    the FOUNDING_AGE stream. `kin` is draw_founding_kin over those ages, on the KINSHIP_STREAM generator.
    The map (one home per household), the cast, and the genealogy all read this plan, so they agree."""
    import numpy as np
    size = int(BALANCE_SCENARIO["residents"]) if size is None else int(size)
    staffing = seed_jobs(size)
    ages = draw_founding_ages(size, seed)
    kin = draw_founding_kin([{"name": str(i), "age": age} for i, age in enumerate(ages)],
                            np.random.default_rng(int(seed) + int(KINSHIP_STREAM)))
    return {"staffing": staffing, "ages": ages, "kin": kin}


def describe_founding_kin(founders=100, *, seed=1):
    """Draw a founding population (ages from FOUNDING_AGE) and report its households and genealogy:
    realised household sizes and extended shares, the kin on record, and the unions.

    `size` of a household is the number of founders in it (children under 18 are not modelled)."""
    import numpy as np
    ages = draw_founding_ages(founders, seed)
    rng = np.random.default_rng(int(seed) + int(KINSHIP_STREAM))
    kin = draw_founding_kin([{"name": str(i), "age": age} for i, age in enumerate(ages)], rng)
    index = index_kinship(kin["persons"], kin["births"], kin["unions"])
    ids = kin["founders"]
    terms = {f: kin_relatives(index, f) for f in ids}
    households = kin["households"]
    members = [len(h["members"]) for h in households]
    drawn = [h["size_drawn"] for h in households]

    def share(pred):
        return round(sum(1 for f in ids if pred(f)) / founders, 4)

    unions_of = {f: _partners_at(index, f, 0.0) for f in ids}
    married_heads = [h for h in households if h["spouse"] is not None]
    return {"founders": founders,
            "ages_mean": round(sum(ages) / max(1, len(ages)), 2),
            "with_parent_on_record": share(lambda f: bool(index["parents"][f])),
            "in_a_union": share(lambda f: bool(unions_of[f])),
            "with_aunt_or_uncle": share(lambda f: any(t in ("aunt", "uncle") for t, _ in terms[f].values())),
            "with_cousin": share(lambda f: any(t == "cousin" for t, _ in terms[f].values())),
            "mean_children_with_spouse": round(sum(len(h["children"]) for h in married_heads)
                                               / max(1, len(married_heads)), 3),
            "households": len(households),
            "mean_members": round(sum(members) / max(1, len(members)), 3),
            "mean_drawn_size": round(sum(drawn) / max(1, len(drawn)), 3),
            "single_member_share": round(sum(1 for m in members if m == 1) / max(1, len(members)), 4),
            "extended_share": round(sum(1 for h in households if h["extended"]) / max(1, len(households)), 4),
            "extended_drawn_share": round(sum(1 for h in households if h["extended_drawn"])
                                          / max(1, len(households)), 4),
            "spouse_co_resident_share": round(len(married_heads) / max(1, len(households)), 4)}
