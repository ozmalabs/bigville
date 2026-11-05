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
)

# Starting literacy/capability by station in life (the world's defaults; any agent can be set higher).
STATION_EDUCATION = {
    "labouring": {"literacy": 0.15, "capability": 0.2},   # most of the village -- low literacy
    "middle":    {"literacy": 0.55, "capability": 0.5},   # functional: notes, the newspaper
    "educated":  {"literacy": 0.9,  "capability": 0.9},   # council laws, accounting
}


# ---------------------------------------------------------------------------
# NATURAL PREFERENCE DISTRIBUTIONS -- the reference for SEEDING a population's
# innate preferences (taste, colour). A population is DRAWN from these: the
# individual varies, the DISTRIBUTION is the fact. Grounded in real research.
#
# GROUNDING (fetched 2026-08 via curl; figures flagged VERIFIED vs APPROX):
#  * BITTER taster status -- VERIFIED 25/50/25 at en.wikipedia.org/wiki/Supertaster
#    (refs 13-14; Bartoshuk's PROP/PTC work, gene TAS2R38). Trimodal, robust.
#  * CILANTRO 'soapy' -- VERIFIED at en.wikipedia.org/wiki/Coriander: variation in
#    the gene OR6A2 makes a MINORITY perceive it as soapy/rotten (Eriksson et al.
#    2012, 23andMe). Exact prevalence varies by ancestry (~a few % to ~20%); the
#    fraction below is a rough mid-range, APPROX -- not a verified figure.
#  * COLOUR -- VERIFIED at en.wikipedia.org/wiki/Color_preferences that children
#    prefer red/pink & blue and cool>warm. That BLUE is the most common ADULT
#    favourite is a robust cross-survey finding (Eysenck 1941 and later); the
#    category fractions below are APPROX -- the ORDERING (blue #1) is the reliable
#    part, not the exact percentages.
#  * SWEET innate / BITTER rejected in newborns -- Steiner; Desor et al. Robust;
#    used only as the direction of the taste means below.
# The web-search budget was exhausted this session; the APPROX figures should be
# re-verified against the cited studies before any quantitative claim rests on them.
# ---------------------------------------------------------------------------

# provenance strings kept in-data so the seed carries its own citations
PREFERENCE_RESEARCH = {
    "bitter_taster": "VERIFIED 25/50/25 -- en.wikipedia.org/wiki/Supertaster (Bartoshuk; TAS2R38 PROP/PTC)",
    "cilantro_soapy": "VERIFIED gene OR6A2 -- en.wikipedia.org/wiki/Coriander (Eriksson et al. 2012, 23andMe); prevalence APPROX",
    "colour_blue_first": "ordering VERIFIED-robust (Eysenck 1941 + later); fractions APPROX -- en.wikipedia.org/wiki/Color_preferences",
    "sweet_bitter_innate": "Steiner; Desor et al. -- newborns prefer sweet, reject bitter (direction of the means)",
}

# BITTER taster status -- VERIFIED trimodal split (Bartoshuk; Wikipedia Supertaster)
BITTER_TASTER_STATUS = {"non_taster": 0.25, "medium": 0.50, "supertaster": 0.25}
# a supertaster is far more averse to bitter; a non-taster barely registers it (APPROX liking means)
BITTER_LIKING_BY_STATUS = {"non_taster": 0.55, "medium": 0.35, "supertaster": 0.12}

# FAVOURITE colour -- blue robustly #1; ORDERING reliable, FRACTIONS APPROX (must sum to 1)
COLOUR_PREFERENCE = {
    "blue": 0.33, "red": 0.14, "green": 0.13, "purple": 0.10, "black": 0.09,
    "pink": 0.06, "orange": 0.05, "yellow": 0.05, "white": 0.03, "brown": 0.02,
}

# basic-TASTE liking -- population mean/sd per taste. MEANS follow the robust
# innate direction (sweet liked, bitter rejected); SDs APPROX. Bitter's real
# structure is the taster trimodal above (this mean is the marginal).
TASTE_PREFERENCE = {
    "sweet":  {"mean": 0.80, "sd": 0.12},   # innately preferred (Steiner)
    "salty":  {"mean": 0.62, "sd": 0.15},
    "umami":  {"mean": 0.60, "sd": 0.16},
    "sour":   {"mean": 0.42, "sd": 0.18},
    "bitter": {"mean": 0.30, "sd": 0.22},   # innately rejected; taster-status trimodal
}

# CILANTRO 'soapy' -- OR6A2; a MINORITY. APPROX mid of the ~few%-to-~20% range.
CILANTRO_SOAPY_FRACTION = 0.13


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


# ---------------------------------------------------------------------------
# THE PSYCHOLOGY OF PREFERENCE -- how preference AFFECTS wellbeing, so a monotonous
# (e.g. poor) diet is modelled, not just a static taste. Two opposing forces on
# repetition + one distributed trait + a soft baseline:
#  * SENSORY-SPECIFIC SATIETY (short-term) -- VERIFIED, en.wikipedia.org/wiki/
#    Sensory-specific_satiety: 'the declining satisfaction generated by the
#    consumption of a certain type of food, and the consequent renewal ... from a
#    new flavour' (Rolls et al. 1981). Eating the SAME thing wears out its pleasure;
#    variety renews it. Rate parameters below APPROX (model choices).
#  * MERE-EXPOSURE (long-term) -- VERIFIED, en.wikipedia.org/wiki/Mere-exposure_effect
#    (Zajonc): familiarity BUILDS liking. The counter-force -- comfort food. APPROX rate.
#  * FOOD NEOPHOBIA (trait, distributed) -- VERIFIED, en.wikipedia.org/wiki/
#    Food_neophobia (rejection of novel foods; Pliner & Hobden Food Neophobia Scale).
#    High-neophobia = routine-loving, content with the same/bland, dislikes novelty;
#    low = variety-seeking, satiates fast on monotony, likes novelty. Distribution APPROX.
#  * HEDONIC ADAPTATION -- VERIFIED, en.wikipedia.org/wiki/Hedonic_treadmill: a soft
#    happiness set-point; the monotony hit rides OVER the baseline (used as direction).
# So: a routine-loving person is happy on plain repeated food; a variety-seeker on the
# same diet suffers -- and a poor household constrained to one cheap food eats it day
# after day, so the monotony welfare cost lands hardest on the variety-seeking poor.
# ---------------------------------------------------------------------------

PREFERENCE_RESEARCH.update({
    "sensory_specific_satiety": "VERIFIED -- en.wikipedia.org/wiki/Sensory-specific_satiety (Rolls et al. 1981); rates APPROX",
    "food_neophobia": "VERIFIED trait -- en.wikipedia.org/wiki/Food_neophobia (Pliner & Hobden scale); distribution APPROX",
    "mere_exposure": "VERIFIED -- en.wikipedia.org/wiki/Mere-exposure_effect (Zajonc); rate APPROX",
    "hedonic_adaptation": "VERIFIED (direction) -- en.wikipedia.org/wiki/Hedonic_treadmill; soft set-point",
})

FOOD_NEOPHOBIA = {"mean": 0.40, "sd": 0.20}   # 0=variety-seeker .. 1=routine-lover (APPROX distribution)
SSAT_RATE = 0.55            # sensory-specific satiety per repeat, for a pure variety-seeker (APPROX)
NOVELTY_SWING = 0.30        # neophobia's push on a NOVEL food's liking (+ for neophilic, - for neophobic)
MERE_EXPOSURE_GAIN = 0.6    # fraction of the gap to full liking that familiarity eventually closes (APPROX)
MERE_EXPOSURE_DECAY = 0.7   # per-exposure approach rate toward that ceiling


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


# ---------------------------------------------------------------------------
# PHYSIQUE -- the body's STRENGTH and STAMINA. Each is a BASE stat drawn per person
# (population variation), an EFFECTIVE value that HEALTH modulates (a sick or injured
# body is weaker and tires sooner), and a TRAINED component that slowly grows with USE
# toward a ceiling RELATIVE TO the base -- your base sets both how strong you start and
# how far training can take you. So growth is always "relative to and based on base
# stats and variations": a higher base means a higher ceiling and larger absolute gains.
#
# Distributions APPROX (normalized ~1.0 units, NOT a measured population): strength and
# stamina share a general-fitness component + independent variation, so they correlate
# loosely (a fit person tends to be both) without collapsing to one axis -- a sprinter
# (fast-twitch strength) and an endurance runner (slow-twitch stamina) still vary apart.
# ---------------------------------------------------------------------------

PHYSIQUE = {
    "mean": 1.0, "sd": 0.20,        # base strength/stamina, normalized units (APPROX)
    "shared_sd": 0.12,              # a general-fitness component common to both stats
    "floor": 0.40,                  # nobody is at zero
}


def draw_physique(rng):
    """Draw a person's base strength + stamina: a shared general-fitness component plus an independent
    per-stat draw, floored. The variation IS the point -- a strong person and a weak one, a sprinter
    and an endurance type, all from one distribution."""
    g = float(rng.normal(0.0, PHYSIQUE["shared_sd"]))       # general fitness raises/lowers both together
    def one():
        return float(max(PHYSIQUE["floor"], PHYSIQUE["mean"] + g + rng.normal(0.0, PHYSIQUE["sd"])))
    return {"str_base": one(), "sta_base": one()}


# ---------------------------------------------------------------------------
# PROVISIONING traits -- the HUMAN CONDITION: everyone must work out food EVERY day of their
# lives; it never resolves, only renews. How well you can get AHEAD of it varies by person:
#  * PLAN HORIZON -- how many days ahead you provision. A distributed trait: some think a week
#    out, some live day-to-day. APPROX distribution.
#  * LARDER -- how much food you can STORE, which you must be able to AFFORD. A bigger larder +
#    coin lets you buy in bulk and hold a buffer; with a tiny larder you live hand-to-mouth and
#    are exposed the day supply fails. So provisioning is bounded by min(what you project you'll
#    need, what you can store). Larder capacity is set from wealth (a purchased/rented resource).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# APTITUDE, TALENTS, AND LIMITATIONS -- how skill capacity varies between people
# ---------------------------------------------------------------------------
# APTITUDE (the meta-metaskill, general learning ability): IQ is normed to a normal distribution,
# mean 100 and SD 15 (en.wikipedia.org/wiki/Intelligence_quotient; ~2% each above 130 and below 70).
# Aptitude is that scale divided by 100 -- a multiplier with mean 1.0 and SD 0.15 -- floored at 0.4.
APTITUDE = {"mean": 1.0, "sd": 0.15, "floor": 0.40}
# TALENT: each metaskill's specific ability beyond what aptitude explains (the part of a broad ability
# not shared with g). Independent per metaskill; SD APPROX (a model choice), floor 0.5.
TALENT = {"mean": 1.0, "sd": 0.12, "floor": 0.50}

# LIMITATIONS -- prevalence in a population, with the published figure each is set from. Age/sex
# dependence follows the sources; `persistence` is the share of childhood cases still present in
# adults; `given` gives a higher rate when another condition is present (comorbidity).
LIMITATION_PREVALENCE = {
    # 5-10% of school-age children have a reading or a maths learning disorder; ~40% of children with
    # the maths disorder also have the reading one (PubMed 39827782). A Spanish primary-school sample
    # found risk of dyslexia 8.5% (Frontiers in Psychology 2025, 10.3389/fpsyg.2025.1664437).
    "dyslexia": {"rate": 0.07, "given": {"dyscalculia": 0.40}},
    # 3-7% of children, adolescents, and adults (PubMed 30905334).
    "dyscalculia": {"rate": 0.05},
    # 5-6% of school-age children (PMC8448494, DSM-5); continues into adulthood in 50-70% (PMC10784181).
    "developmental_coordination_disorder": {"rate": 0.055, "persistence": 0.6},
    # red-green colour vision deficiency: up to 8% of males and 0.5% of females of Northern European
    # descent, lower elsewhere (PMC12385717).
    "colour_vision_deficiency": {"rate": {"male": 0.08, "female": 0.005}},
    # essential tremor: ~0.4% overall; 5.79% at age >= 65 in a meta-analysis (PubMed 34277141).
    "essential_tremor": {"rate_by_age": [(0, 0.004), (65, 0.058)]},
    # persistent adult ADHD: 2.58% of adults, adjusted to the 2020 global population (meta-analysis,
    # PubMed 33692893); 5-7% in childhood (PMC9197091).
    "adult_adhd": {"rate_by_age": [(0, 0.06), (18, 0.026)]},
    # symptomatic hand osteoarthritis: 8% of US adults (NHANES III, PubMed 17304684); at 71-100 years,
    # 26.2% of women and 13.4% of men (Framingham, PubMed 12446258). The under-50 rate is APPROX.
    "hand_osteoarthritis": {"rate_by_age": [(0, 0.0), (35, 0.02), (50, 0.08)],
                            "rate_by_age_sex": {"male": [(71, 0.134)], "female": [(71, 0.262)]}},
}


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


PLAN_HORIZON = {"mean": 2.0, "sd": 1.2, "min": 1.0}   # days ahead an agent provisions (APPROX; heterogeneous)


def draw_plan_horizon(rng):
    """A person's planning horizon (days ahead they provision) -- a distributed trait. Some plan a week
    out; some live day-to-day. Floored at 1 (you always at least sort out today)."""
    return float(max(PLAN_HORIZON["min"], round(rng.normal(PLAN_HORIZON["mean"], PLAN_HORIZON["sd"]))))


def larder_for_wealth(coin, *, per_coin=0.5, floor=1.0, cap=20.0):
    """The larder capacity a given wealth can afford -- storage scales with means (floored at 1: everyone
    can keep a little; capped). The poor hold ~1 day and buy daily; the rich buy in bulk and buffer. APPROX."""
    return float(min(cap, max(floor, per_coin * float(coin))))

# The founding town the balance model assumes. These mirror what worlds/bigville_world.py builds
# for the 100-resident scenario (populate_town100 / _seed_village_crops): keep them in step.
BALANCE_SCENARIO = {
    "residents": 100,
    "food_per_resident": 1.0,                 # food units eaten per resident per period
    "staple": "bake_bread",                   # the recipe most food is assumed to come through
    "beds": {"wheat": 27, "barley": 27, "oats": 26},
    "plots": 8, "plot_area": 1.0, "soil": "loam",
    "animals": {"cow": 1, "chicken": 1, "pig": 1, "sheep": 1, "horse": 1, "bee": 1, "dog": 1},
    "pasture_area": 4.0,
    "water_sources": ["well", "spring", "spring", "stream"],
    "work_minutes_per_resident": 8 * 60,      # a working day per period
}

# Historical staffing per 100 residents a derived job weight should fall within. A weight outside its
# range means a recipe's batch size or time is unrealistic, and the jobs report says so.
#   miller -- Domesday (1086) recorded ~6,000 watermills in England for ~1.5-2 million people: ~1 mill
#             per 300 people (historymedieval.com/watermills-a-key-tech-of-the-middle-ages). APPROX.
#   baker  -- a village baker's large oven served the village; one baker per few hundred people. APPROX.
JOB_REFERENCE_PER_100 = {"miller": (0.2, 0.6), "baker": (0.25, 0.6)}

# A production job keeps spare hands until each holder carries at most this share of a full day.
JOB_TARGET_LOAD = 0.8


def scale_scenario(population):
    """BALANCE_SCENARIO resized to a town of `population` working residents."""
    import math
    base = BALANCE_SCENARIO
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
    day = float(sc["work_minutes_per_resident"])
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
