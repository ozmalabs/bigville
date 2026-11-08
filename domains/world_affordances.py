"""world_affordances.py -- how the Bigville world works, as PURE DATA (plus small pure functions over it).

What exists physically and what it lets you do: items and their materials, containers, cooking,
recipes, buildings, deposits, terrain, animals, crops and the nitrogen cycle, weather, water, fuel,
waste, infrastructure, condition and decay, bodies, and the actions a resident can take.

These are FACTS ABOUT THE WORLD, not public knowledge. They include what things are worth to obtain
(SCARCITY, reference_value) and how much a harvest yields: the world runs on them, but a resident
knows any of them only as far as they have learned it -- a miller knows what a mill run gives, a
buyer only what she paid. What residents hold in common is in shared_frames; how a founding
population is drawn is in population.
"""
from __future__ import annotations

from domains.pack import load_pack as _load_pack

# Tables and constants below are read from the "bigville" data pack (packs/bigville/).
# Their explanatory comments are in the pack files as "_doc"; domains/pack.py
# compiles the derived entries. Functions in this module read these names unchanged.
_PACK = _load_pack(globals().get("_PACK_NAME", "bigville"))   # data_view seeds _PACK_NAME
ITEMS = _PACK["ITEMS"]
SCRAP_WEIGHT_FACTOR = _PACK["SCRAP_WEIGHT_FACTOR"]
SCRAP_SCARCITY_FACTOR = _PACK["SCRAP_SCARCITY_FACTOR"]
SCRAP_DECAY = _PACK["SCRAP_DECAY"]
INPUT_TYPES = _PACK["INPUT_TYPES"]
CONTAINERS = _PACK["CONTAINERS"]
COIN_WEIGHT = _PACK["COIN_WEIGHT"]     # Phase 041: kg of one coin, stored or carried (APPROX, 0)
COIN_VOLUME = _PACK["COIN_VOLUME"]     # Phase 041: litres of one coin, stored (APPROX, 0)
SERVING_UTENSILS = _PACK["SERVING_UTENSILS"]
SERVING_EQUIPMENT = _PACK["SERVING_EQUIPMENT"]
FOOD_SERVICE = _PACK["FOOD_SERVICE"]
# Phase 027: the constants of graded eating (raw_penalty, rot_illness, raw_illness), in items.json.
FOOD_GRADING = _PACK["FOOD_GRADING"]
SOUP_FOODS = _PACK["SOUP_FOODS"]
DRINK_FOODS = _PACK["DRINK_FOODS"]
PREPARATION_REQUIREMENTS = _PACK["PREPARATION_REQUIREMENTS"]
PREPARATION_EQUIPMENT = _PACK["PREPARATION_EQUIPMENT"]
PREPARATION_METHODS = _PACK["PREPARATION_METHODS"]
PREPARATION_METHODS_BY_HINT = _PACK["PREPARATION_METHODS_BY_HINT"]
HEATED_FOOD_RECIPES = _PACK["HEATED_FOOD_RECIPES"]
FUEL_PER_BATCH = _PACK["FUEL_PER_BATCH"]
RECIPES = _PACK["RECIPES"]
BUILDINGS = _PACK["BUILDINGS"]
TOWN_SQUARE_FIXTURES = _PACK["TOWN_SQUARE_FIXTURES"]
BUILDING_PROJECTS = _PACK["BUILDING_PROJECTS"]
RESOURCE_DEPOSITS = _PACK["RESOURCE_DEPOSITS"]
# Phase 004: the gathering sites a gathering recipe's `gathered_from` names (empty in a pack with none).
GATHERING_SITES = _PACK["GATHERING_SITES"]
# Phase 010: what a dead resident leaves (a body on the ground) and what an unburied body does (the
# graveyard, the body's weight, and the disease risk to its household). Empty in a pack with no graveyard.
BURIAL = _PACK["BURIAL"]
# The founding town's map and sites (Phase 016a). Empty in a pack with no founding town.
FOUNDING_MAP = _PACK["FOUNDING_MAP"]
FOUNDING_DEPOSITS = _PACK["FOUNDING_DEPOSITS"]
FOUNDING_WORKPLACES = _PACK["FOUNDING_WORKPLACES"]
FOUNDING_BUILDING_SITES = _PACK["FOUNDING_BUILDING_SITES"]
FOUNDING_PLACE_LABELS = _PACK["FOUNDING_PLACE_LABELS"]
FOUNDING_ANCHOR_ALIASES = _PACK["FOUNDING_ANCHOR_ALIASES"]
SHOP_CHAINS = _PACK["SHOP_CHAINS"]
TERRAIN_MOVEMENT = _PACK["TERRAIN_MOVEMENT"]
TERRAIN_WEAR = _PACK["TERRAIN_WEAR"]
ANIMALS = _PACK["ANIMALS"]
SLAUGHTER_PRODUCTS = _PACK["SLAUGHTER_PRODUCTS"]
ANIMAL_NPC_SETUP = _PACK["ANIMAL_NPC_SETUP"]
# Phase 021: the physical reason codes a refused major action reports, and the number of refused attempts
# each resident's log keeps (packs/*/world/refusal_reasons.json).
REFUSAL_REASONS = _PACK["REFUSAL_REASONS"]
REFUSAL_LOG_LIMIT = _PACK["REFUSAL_LOG_LIMIT"]
# Phase 026: the physical handovers of coin and goods the world records, by the action that moved them,
# by endpoint kind, and the number of Handover facts the town keeps (packs/*/world/handovers.json).
HANDOVER_KINDS = _PACK["HANDOVER_KINDS"]
HANDOVER_ENDPOINTS = _PACK["HANDOVER_ENDPOINTS"]
HANDOVER_LOG_LIMIT = _PACK["HANDOVER_LOG_LIMIT"]
# Phase 030: keys are discrete items of KEY_KIND, and the town store's founding lock (packs/*/world/locks.json).
KEY_KIND = _PACK["KEY_KIND"]
KEY_WEIGHT = _PACK["KEY_WEIGHT"]
STORE_LOCK = _PACK["STORE_LOCK"]
# Phase 028: the hearing and sight figures for speech (packs/*/world/hearing.json). Distances are cells.
HEARING = _PACK["HEARING"]
FENCE_TYPES = _PACK["FENCE_TYPES"]
ENCLOSURE_TYPES = _PACK["ENCLOSURE_TYPES"]
ANIMAL_HUSBANDRY = _PACK["ANIMAL_HUSBANDRY"]
CROPS = _PACK["CROPS"]
FIELD_WORK = _PACK["FIELD_WORK"]
ARABLE_ROTATION = _PACK["ARABLE_ROTATION"]
NITROGEN = _PACK["NITROGEN"]
STARTING_STOCK = _PACK["STARTING_STOCK"]
STARTING_CROPS = _PACK["STARTING_CROPS"]
FREE_ACTIONS = _PACK["FREE_ACTIONS"]
MAJOR_ACTIONS = _PACK["MAJOR_ACTIONS"]
MAJOR_ACTIONS = {**MAJOR_ACTIONS, **_PACK["DAYNIGHT_MAJOR_ACTIONS"]}   # Phase 042: light and douse
DAYNIGHT = _PACK["DAYNIGHT"]               # Phase 042: day, night and lamps
DAYNIGHT_LAMPS = _PACK["DAYNIGHT_LAMPS"]
MARKS = _PACK["MARKS"]                     # Phase 063: visible condition (dirt, soot, blood, ...)
MARK_RULES = _PACK["MARK_RULES"]
MARK_HARM = _PACK["MARK_HARM"]             # per point of health lost, by HEALTH cause
MARK_EVENTS = _PACK["MARK_EVENTS"]         # per occurrence, by event name
# Phase 018: the LLM prompt's premise, rules, response fields, memory selection caps, and gist text.
WORLD_PREMISE = _PACK["WORLD_PREMISE"]
PROMPT_BOUNDARY_RULES = _PACK["PROMPT_BOUNDARY_RULES"]
PROMPT_CONTINUATION_RULES = _PACK["PROMPT_CONTINUATION_RULES"]
PROMPT_RESPONSE_FIELDS = _PACK["PROMPT_RESPONSE_FIELDS"]
PROMPT_SELECTION = _PACK["PROMPT_SELECTION"]
MEMORY_GIST = _PACK["MEMORY_GIST"]
CARRYING = _PACK["CARRYING"]
SEASONS = _PACK["SEASONS"]
# Phase 011: the purses (coin containers held by an office or job) and the fiscal payment and collection
# actions (their physical checks). Empty in a pack with no fiscal institutions. The institutions are in
# frames/fiscal_institutions.json, bound in shared_frames.py.
FISCAL_PURSES = _PACK["FISCAL_PURSES"]
FISCAL_ACTIONS = _PACK["FISCAL_ACTIONS"]


def round_bp(amount, bp):
    """Whole coins: `amount` times `bp` basis points, rounded half up. The seeds' IDiv(amount*bp+5000, 10000).

    Both arguments must be whole numbers (fiscal amounts are whole coins; a fraction would be cut silently
    otherwise), `amount` not negative, and `bp` in 0..10000. Pure: no world, no state."""
    if isinstance(amount, bool) or isinstance(bp, bool):
        raise ValueError("round_bp takes whole numbers, not booleans")
    a, b = float(amount), float(bp)
    if not (a.is_integer() and b.is_integer()):
        raise ValueError(f"round_bp needs whole coins and basis points, got {amount!r} and {bp!r}")
    if a < 0 or not 0 <= b <= 10000:
        raise ValueError(f"round_bp needs amount >= 0 and 0 <= bp <= 10000, got {amount!r} and {bp!r}")
    return (int(a) * int(b) + 5000) // 10000
WEATHER = _PACK["WEATHER"]
WATER_SOURCES = _PACK["WATER_SOURCES"]
FUEL_SOURCES = _PACK["FUEL_SOURCES"]
# Phase 005: space heating each household burns per period (fuel_type, base_burn, unheated_chill).
HEATING = _PACK["HEATING"]
# Phase 006: the household-work scoring a backend applies to open recipe options (thresholds and weights).
HOUSEHOLD_WORK = _PACK["HOUSEHOLD_WORK"]
SOILS = _PACK["SOILS"]
LAND_USES = _PACK["LAND_USES"]
PASTURE_YIELDS = _PACK["PASTURE_YIELDS"]
WASTE_CYCLES = _PACK["WASTE_CYCLES"]
LIFE_STAGES = _PACK["LIFE_STAGES"]
HEALTH_CONDITIONS = _PACK["HEALTH_CONDITIONS"]
INFRASTRUCTURE = _PACK["INFRASTRUCTURE"]
SHOCKS = _PACK["SHOCKS"]
AFFORDANCES = _PACK["AFFORDANCES"]
OBSERVATION_TYPES = _PACK["OBSERVATION_TYPES"]
ADJECTIVES = _PACK["ADJECTIVES"]
CLASS_DECAY = _PACK["CLASS_DECAY"]
_PERISHABLE_RAW = _PACK["_PERISHABLE_RAW"]
SCARCITY = _PACK["SCARCITY"]
LABOUR_RATE = _PACK["LABOUR_RATE"]
TRAIN_HEADROOM = _PACK["TRAIN_HEADROOM"]
TRAIN_RATE = _PACK["TRAIN_RATE"]
RECIPE_EXERTION = _PACK["RECIPE_EXERTION"]
HUNGER_PER_STAMINA = _PACK["HUNGER_PER_STAMINA"]
# Stamina one `rest` action restores, per unit of its amount (the port's rate; APPROX, not sourced: the
# seed bd_rest_recover gives no figure). One rest action spans one clock tick (TIME.minutes_per_tick).
# The value lives in the EXHAUSTION pack table (Phase 024), with the sleep and slowdown parameters.
EXHAUSTION = _PACK["EXHAUSTION"]
# Phase 037: the health routes (one health variable, its causes, age decline, fragility and the harms).
HEALTH = _PACK["HEALTH"]
# Phase 034: alcohol in the body (INTOXICATION: Widmark scaling, the sobering rate, the bands, pass-out and the
# effect rates). The grams per drink are on the ITEMS (`alcohol`). APPROX values; see the table's _doc.
INTOXICATION = _PACK["INTOXICATION"]
INTOXICATION_BANDS = ("sober", "tipsy", "drunk", "stupefied")
# Phase 035: nutrition (protein need, the deficiency and specific-satiety rates, the spice bonus and the mood rate).
# The per-food protein and taste are on ITEMS. APPROX values; see the table's _doc.
NUTRITION = _PACK["NUTRITION"]
# Phase 043: the illness rules (DISEASE: onset, severity, progression, course) and the doctor's and midwife's
# acts (MEDICAL_CARE: screening, treatment and well-baby durations, and the skills each act needs). APPROX.
DISEASE = _PACK["DISEASE"]
MEDICAL_CARE = _PACK["MEDICAL_CARE"]
# Phase 044: pregnancy and birth (BIRTHS: conception by age, gestation, delivery risks, midwife, nursing). APPROX.
BIRTHS = _PACK["BIRTHS"]
# Phase 045: infants, dependants and coming of age (DEPENDANTS: stages, neglect, growth; enabled is off). APPROX.
DEPENDANTS = _PACK["DEPENDANTS"]
# Phase 046: detraining of trained strength and stamina (DETRAIN) and ageing of the base (BODY_AGE). APPROX.
DETRAIN = _PACK["DETRAIN"]
BODY_AGE = _PACK["BODY_AGE"]
# Phase 029: a contested take (force, cost, margins, reactions). APPROX values; see the table's _doc.
CONTEST = _PACK["CONTEST"]
# Phase 050: the one resolution rule. VERBS (the physics of a verb), MATERIALS (what a thing is made of) and
# RESOLUTION (the numbers of worlds/resolution.py). APPROX values; see the tables' _doc.
VERBS = _PACK["VERBS"]
MATERIALS = _PACK["MATERIALS"]
RESOLUTION = _PACK["RESOLUTION"]
# Phase 048: TOOL_FIT, the tool-facing part of the resolution (closeness, hardness, edge, weight, authored rows).
TOOL_FIT = _PACK["TOOL_FIT"]
# Phase 040: OBJECT_FORCE, what an object held in hand does when swung or thrown (harm curve, range, breakage).
OBJECT_FORCE = _PACK["OBJECT_FORCE"]
# Phase 047: JOINT_TASKS, people acting together (carry and crew). Numbers and sources are in the table's _doc.
JOINT_TASKS = _PACK["JOINT_TASKS"]
REST_RECOVERY_PER_UNIT = EXHAUSTION["rest_recovery_per_unit"]
ANIMAL_SERVICES = _PACK["ANIMAL_SERVICES"]
# World mechanics parameters (Phase 014): the clock, the town's starting state, a resident's
# starting state, care and starvation, default prices, the literacy gate for each written kind,
# and the seeded rules the world and a resident's mind load.
TIME = _PACK["TIME"]
TOWN_INITIAL = _PACK["TOWN_INITIAL"]
ACTOR_DEFAULTS = _PACK["ACTOR_DEFAULTS"]
CARE = _PACK["CARE"]
PRICE_DEFAULTS = _PACK["PRICE_DEFAULTS"]
DOCUMENT_LITERACY = _PACK["DOCUMENT_LITERACY"]
ENGINE_SEEDS = _PACK["ENGINE_SEEDS"]
RESIDENT_SEEDS = _PACK["RESIDENT_SEEDS"]
RESIDENT_CONCEPT_SEEDS = _PACK["RESIDENT_CONCEPT_SEEDS"]
# Phase 069: the body's feelings (world/interoception.json): the anatomy and quality trees, the sounds,
# the channels, the signal sources, the patterns, the background feeling and the depth rule. APPROX throughout.
ANATOMY = _PACK["ANATOMY"]
QUALITY_TREE = _PACK["QUALITY_TREE"]
VOCALISATIONS = _PACK["VOCALISATIONS"]
CHANNELS = _PACK["CHANNELS"]
SIGNAL_SOURCES = _PACK["SIGNAL_SOURCES"]
PATTERNS = _PACK["PATTERNS"]
FEELING = _PACK["FEELING"]
INTEROCEPTION = _PACK["INTEROCEPTION"]
# Phase 070: the located harm loci, the body rates and the observable signs (world/interoception.json).
HARM_LOCUS = _PACK["HARM_LOCUS"]
BODY_RATES = _PACK["BODY_RATES"]
OBSERVABLE_SIGNS = _PACK["OBSERVABLE_SIGNS"]
# Phase 071: attending and pressing (world/interoception.json): the attention budget, the press reaction, the remedies.
ATTEND = _PACK["ATTEND"]


def scrap_kind(kind):
    """The scrap item a food leaves, or None if eating it leaves nothing."""
    return f"{kind}_scraps" if ITEMS.get(kind, {}).get("leaves_scraps") else None


def feeds(kind):
    """Loaf-equivalents of hunger one unit of `kind` relieves when eaten fresh (ITEMS `feeds`, Phase 027).
    1.0 is one resident's meal. Derived scraps are animal feed, not people food, and relieve nothing."""
    spec = ITEMS.get(kind, {})
    if spec.get("scraps_of"):
        return 0.0
    return float(spec.get("feeds", 0.0))


def alcohol(kind):
    """Grams of ethanol in one serving of `kind` (ITEMS `alcohol`, Phase 034). 0 for a food with none."""
    return float(ITEMS.get(kind, {}).get("alcohol", 0.0))


def sober_per_tick():
    """The fall in intoxication per clock tick: the table's hourly rate over one tick (TIME.minutes_per_tick)."""
    return float(INTOXICATION["sober_per_hour"]) * float(TIME["minutes_per_tick"]) / 60.0


def intoxication_gain(grams, size=1.0):
    """What `grams` of alcohol adds to a body's intoxication (0 sober to 1 at full scale). Widmark's formula:
    blood alcohol in g/100 ml is grams / (widmark_r x body kg x 10), with body kg = reference_kg x size, and the
    level is that blood alcohol over full_bac_percent. A smaller body (size below 1) takes more."""
    t = INTOXICATION
    body_kg = float(t["reference_kg"]) * float(size)
    blood_alcohol = float(grams) / (float(t["widmark_r"]) * body_kg * 10.0)
    return blood_alcohol / float(t["full_bac_percent"])


def intoxication_band(level):
    """'sober', 'tipsy', 'drunk' or 'stupefied' for an intoxication level, by the table's lower band edges."""
    bands = INTOXICATION["bands"]
    if float(level) >= float(bands["stupefied"]):
        return "stupefied"
    if float(level) >= float(bands["drunk"]):
        return "drunk"
    if float(level) >= float(bands["tipsy"]):
        return "tipsy"
    return "sober"


def meal_value(kind, freshness):
    """Hunger one unit of food relieves at a given freshness (0 to 1, the pile's condition): feeds x
    freshness, times FOOD_GRADING raw_penalty when the food needs preparation and has none (`needs_prep`).
    Spoiled food (freshness 0) relieves nothing but is still eaten, so the grading never refuses."""
    value = feeds(kind) * min(1.0, max(0.0, float(freshness)))
    if ITEMS.get(kind, {}).get("needs_prep"):
        value *= float(FOOD_GRADING["raw_penalty"])
    return value


def meal_illness_risk(kind, freshness):
    """Chance of illness from one meal (0 to 1): rot_illness x (1 - freshness), plus raw_illness when the
    food needs preparation and has none. Phase 037's health routes turn this risk into the illness."""
    risk = float(FOOD_GRADING["rot_illness"]) * (1.0 - min(1.0, max(0.0, float(freshness))))
    if ITEMS.get(kind, {}).get("needs_prep"):
        risk += float(FOOD_GRADING["raw_illness"])
    return min(1.0, risk)


def protein(kind):
    """Grams of protein in one unit of `kind` (ITEMS `protein`, Phase 035). 0 for a food with none."""
    return float(ITEMS.get(kind, {}).get("protein", 0.0))


def taste(kind):
    """The hedonic rating of `kind`, 0 to 1 (ITEMS `taste`, Phase 035). 0 for a food with none."""
    return float(ITEMS.get(kind, {}).get("taste", 0.0))


def is_spice(kind):
    """True for an item that spices a meal (NUTRITION `spice_kinds`)."""
    return kind in NUTRITION["spice_kinds"]


def satisfaction_of_meal(kind, satiety, spice_bonus=0.0):
    """How a meal lands with the eater, 0 to 1: the input to the mood rule (seed af_meal_mood).

    Pleasantness falls as the food is eaten (sensory-specific satiety, Rolls et al., 1981), so the taste is scaled
    by (1 - satiety). The spice bonus is added on top and not scaled, so a spiced meal is still enjoyed when the
    food is monotonous (seed nu_eat). The sum is clipped to [0, 1]. This is the world's form, read from the body's
    satiety. population.meal_satisfaction is a different model (per-person neophobia and a count of repeats), used
    by the population's diet simulation; the two are not unified (see the Phase 035 report)."""
    level = min(1.0, max(0.0, float(satiety)))
    return min(1.0, max(0.0, taste(kind) * (1.0 - level) + float(spice_bonus)))


def protein_balance(sc):
    """(supply, need), grams of protein per period, for the balance scenario `sc` (Phase 035), or None without one.

    Supply is the staple's protein as the founding diet eats it: residents x food_per_resident loaves x the protein
    of one loaf of the staple's output. Need is residents x NUTRITION protein_need. The model reads the staple only,
    so it says what the staple alone supplies."""
    if not sc or "beds" not in sc:
        return None
    staple = next(r for r in RECIPES if r["name"] == sc["staple"])
    residents = float(sc["residents"])
    supply = residents * float(sc["food_per_resident"]) * protein(staple["out"][0])
    need = residents * float(NUTRITION["protein_need"])
    return supply, need


def feed_kinds(eats):
    """Every stock kind an animal with diet `eats` will accept, in the order it eats them.

    A diet of "scraps" accepts generic kitchen scraps first, then any food's scraps."""
    if eats != "scraps":
        return (eats,)
    return ("scraps",) + tuple(sorted(k for k, s in ITEMS.items() if s.get("scraps_of")))


def is_input_type(kind):
    """True if a recipe input names a type slot rather than an item."""
    return kind in INPUT_TYPES and kind not in ITEMS


def type_members(type_name):
    """((kind, units_per_item), ...) that fill a type slot, cheapest per unit first."""
    tag = INPUT_TYPES[type_name]["tag"]
    members = [(k, float(s[tag])) for k, s in ITEMS.items() if float(s.get(tag, 0.0) or 0.0) > 0.0]
    return tuple(sorted(members, key=lambda kv: (reference_value(kv[0]) / kv[1], kv[0])))


def type_plan(type_name, qty, available):
    """How to fill `qty` units of a type slot from stock: [(kind, amount), ...], or None if short.

    `available(kind)` returns the quantity on hand. The plan takes from the cheapest member first and
    only moves to the next when that one is exhausted."""
    remaining, plan = float(qty), []
    for kind, units in type_members(type_name):
        if remaining <= 1e-9:
            break
        have = float(available(kind))
        if have <= 0.0:
            continue
        take = min(have, remaining / units)
        plan.append((kind, round(take, 6)))
        remaining -= take * units
    return plan if remaining <= 1e-6 else None


def type_byproducts(type_name, qty):
    """{kind: amount} left behind by consuming `qty` units of a type slot."""
    return {k: float(v) * float(qty) for k, v in INPUT_TYPES[type_name].get("byproducts", {}).items()}


def founding_buildings():
    """The catalogue buildings standing when the town is founded (everything not `founding: False`)."""
    return {kind: spec for kind, spec in BUILDINGS.items() if spec.get("founding", True)}


def adjectival(kind):
    """The adjectival CLASS of an item, inferred from its data (food/material/class)."""
    spec = ITEMS.get(kind, {})
    if spec.get("food") or kind in _PERISHABLE_RAW: return "perishable"
    mat, cls = spec.get("material"), spec.get("class")
    if mat == "metal" or kind in ("iron", "ore", "nails", "steel"): return "metal"
    if mat == "cloth" or kind in ("wool", "cloth", "thread"): return "textile"
    if mat == "leather" or kind in ("leather", "hide"): return "leather"
    if mat == "stone" or kind in ("stone", "blocks"): return "stone"
    if mat == "wood" or cls == "furniture" or kind in ("timber", "wood", "log", "stave"): return "wood"
    return "durable"

def decay_rate(kind):
    """How fast an item takes damage OVER TIME (per period): a per-item override (preserved/salted
    goods) if set, else its adjectival class's rate."""
    ov = ITEMS.get(kind, {}).get("decay")
    return float(ov) if ov is not None else CLASS_DECAY[adjectival(kind)]


def storage_decay_factor(container_kind, item_kind):
    """Return a storage environment's content multiplier, without enforcing content types.

    Preferred contents get the container's normal decay environment. Other perishable contents get
    the declared mismatch penalty; durable contents are unaffected because their normal decay is zero.
    """
    spec = CONTAINERS.get(container_kind, {})
    if not spec.get("storage_class") or item_kind in spec.get("preferred_contents", ()):
        return 1.0
    return float(spec.get("mismatch_decay_factor", 1.0))

def adjective(kind, condition):
    """The adjective describing an item at a given condition (1.0 -> 0.0), from its adjectival class."""
    stages = ADJECTIVES[adjectival(kind)]
    n = len(stages)
    return stages[min(n - 1, max(0, int((1.0 - float(condition)) * n)))]


def _serving_kind(kind):
    """Collapse a physical vessel/utensil to its reusable serving capability."""
    spec = ITEMS.get(kind, {})
    if spec.get("utensil"):
        return str(spec["utensil"])
    if kind in ("mug", "wooden_mug", "metal_mug"):
        return "mug"
    if kind in ("bowl", "wooden_bowl", "metal_bowl"):
        return "bowl"
    if kind == "pot":
        return "pot"
    return kind


def vessel_capacity(kind):
    """Capacity of a physical or abstract serving vessel, in the catalog's volume units."""
    spec = ITEMS.get(kind, {}) or CONTAINERS.get(kind, {})
    return float(spec.get("capacity", 0.0))


def food_service(kind):
    """The consumption-time serving contract for a food, or ``None`` for direct-eat foods."""
    if kind in SOUP_FOODS:
        return FOOD_SERVICE["soup"]
    if kind in DRINK_FOODS:
        return FOOD_SERVICE["drink"]
    return None


def serving_utensil_options(kind):
    """Physical utensils/vessels that can serve one portion of `kind`."""
    service = food_service(kind)
    if service is None:
        return ()
    options = []
    for capability in service["utensils"]:
        if capability in CONTAINERS:
            options.append(capability)
            options.extend(CONTAINERS[capability].get("alternatives", []))
        elif capability in SERVING_UTENSILS:
            options.extend(SERVING_UTENSILS[capability]["alternatives"])
        else:
            options.append(capability)
    return tuple(options)


def can_serve(food_kind, vessel_kind, utensil_kind, *, source_kind=None):
    """Whether one portion can be served and consumed with the supplied equipment.

    The target vessel must have enough capacity.  A larger source may be a pot, barrel, or bowl;
    importantly, a bowl is itself an accepted soup scoop, so a serving bowl can scoop from a larger
    bowl without requiring a separate ladle.  ``source_kind`` is optional because a food stock can
    already represent a single portion.
    """
    service = food_service(food_kind)
    if service is None or vessel_capacity(vessel_kind) < float(service["portion_volume"]):
        return False
    if _serving_kind(utensil_kind) not in service["utensils"]:
        return False
    if source_kind is not None:
        if _serving_kind(source_kind) not in service["sources"]:
            return False
        if vessel_capacity(source_kind) < float(service["portion_volume"]):
            return False
    return True


def preparation_methods(recipe_name, equipment=None):
    """Return viable preparation methods for a recipe and available equipment.

    A method is viable when the union of its equipment provides both heat and containment. With no
    equipment argument this returns the catalog's possible methods; callers can pass a set of actual
    equipment kinds to select, for example, ``{"pot", "hot_coals"}`` instead of an oven.
    """
    recipe = next((r for r in RECIPES if r["name"] == recipe_name), None)
    if recipe is None or "preparation" not in recipe:
        return ()
    available = None if equipment is None else set(equipment)
    required = set(recipe["preparation"]["requires"])
    viable = []
    method_names = recipe["preparation"].get("methods", PREPARATION_METHODS)
    for name in method_names:
        method = PREPARATION_METHODS[name]
        if available is not None and not set(method["equipment"]) <= available:
            continue
        provides = set().union(*(set(PREPARATION_EQUIPMENT[e]["provides"]) for e in method["equipment"]))
        if required <= provides:
            viable.append(name)
    return tuple(viable)

def recipe_to_actionspec(r):
    """Translate a data recipe into the legacy two-slot ActionSpec shape plus its complete data.

    The old action adapter exposes ``in1_*``/``in2_*`` for compatibility.  The canonical ``inputs``
    field preserves every ingredient, so recipes with three or more inputs (most substantial dishes)
    remain representable to newer generic consumers.
    """
    ins = r["in"]
    in1 = ins[0] if ins else ["none", 0]            # gathering recipes have no inputs
    in2 = ins[1] if len(ins) > 1 else ["none", 0]
    return {"name": r["name"], "requires": r["requires"],
            "inputs": [[kind, float(qty)] for kind, qty in ins],
            "tools": list(r.get("tools", [])),
            "method_tools": list(r.get("method_tools", [])),
            "preparation": dict(r.get("preparation", {})),
            "in1_kind": in1[0], "in1_qty": float(in1[1]),
            "in2_kind": in2[0], "in2_qty": float(in2[1]),
            "out_kind": r["out"][0], "out_qty": float(r["out"][1]),
            "difficulty": float(r["difficulty"]), "time_minutes": float(r["time_minutes"]),
            "wear_rate": 0.0}


def scarcity(kind):
    """The general scarcity of a RAW material -- what its raw stuff costs to obtain (a per-item
    'scarcity' attr overrides the SCARCITY map; default 1.0). A fact about the world, which residents
    know only as far as they have learned it."""
    ov = ITEMS.get(kind, {}).get("scarcity")
    if ov is not None:
        return float(ov)
    return float(SCARCITY.get(kind, 1.0))


# ---------------------------------------------------------------------------
# BACKEND VALUE REFERENCE -- for the OPERATOR to inspect, NOT an agent input
# ---------------------------------------------------------------------------
# A reference value the HUMAN reads to compare what the MARKET will discover against the raw-input-cost
# + labour baseline (market value vs raw input costs). The agents/sellers do NOT consume this: they
# price from their own understanding of their own costs, and the market clears -- price emerges
# bottom-up. This is read-only analyst tooling (a pure function over the catalog, like decay_rate /
# adjectival), deliberately kept OUT of the agent decision path. reference_value = embodied material
# scarcity + embodied labour priced at LABOUR_RATE; material_value and embodied_labour are the two
# components, separable so relative scarcity and total labour can each be read.


def _recipes_for(kind):
    return [r for r in RECIPES if r["out"][0] == kind]


def _value_parts(kind, _seen=frozenset()):
    """(embodied material scarcity, total embodied labour MINUTES) in ONE unit of `kind`.
    A RAW item (no recipe, or a cycle) = (its scarcity, 0). A MADE item accumulates its inputs'
    parts (x qty) plus its own recipe time, divided by the batch size; the recipe chosen is the one
    giving the LEAST reference value (the socially-necessary way to make it)."""
    recs = _recipes_for(kind)
    if not recs or kind in _seen:
        return (scarcity(kind), 0.0)
    best = None
    for r in recs:
        outq = float(r["out"][1]) or 1.0
        mat, lab = 0.0, float(r.get("time_minutes", 0.0))
        for ik, iq in r["in"]:
            if is_input_type(ik):                     # a type slot costs its cheapest member per unit
                m, l = _type_value_parts(ik, _seen | {kind})
            else:
                m, l = _value_parts(ik, _seen | {kind})
            mat += m * float(iq)
            lab += l * float(iq)
        mat, lab = mat / outq, lab / outq
        val = mat + lab * LABOUR_RATE
        if best is None or val < best[2]:
            best = (mat, lab, val)
    return (best[0], best[1])


def _type_value_parts(type_name, _seen=frozenset()):
    """(material, labour) for ONE unit of a type slot: the cheapest member, per unit it supplies."""
    tag = INPUT_TYPES[type_name]["tag"]
    best = None
    for kind, spec in ITEMS.items():
        units = float(spec.get(tag, 0.0) or 0.0)
        if units <= 0.0 or kind in _seen:
            continue
        m, l = _value_parts(kind, _seen)
        m, l = m / units, l / units
        if best is None or m + l * LABOUR_RATE < best[0] + best[1] * LABOUR_RATE:
            best = (m, l)
    return best or (1.0, 0.0)


def material_value(kind):
    """The embodied material-scarcity in a unit of `kind` (the raw-input-cost component)."""
    return round(_value_parts(kind)[0], 4)


def embodied_labour(kind):
    """The TOTAL labour, in minutes, embodied in a unit of `kind` through its whole production chain."""
    return round(_value_parts(kind)[1], 4)


def reference_value(kind):
    """The operator's reference value for a unit of `kind`: embodied material scarcity + embodied
    labour priced at LABOUR_RATE. A baseline to hold the market's discovered price against -- the
    agents do not read it."""
    m, l = _value_parts(kind)
    return round(m + l * LABOUR_RATE, 4)


# ---------------------------------------------------------------------------
# BODIES -- how strength and stamina are used and grow (population.PHYSIQUE draws the base stats)
# ---------------------------------------------------------------------------
def train_ceiling(base):
    """The trained-component ceiling, RELATIVE TO base: use can build up to TRAIN_HEADROOM over base."""
    return float(base) * TRAIN_HEADROOM


def train_gain(base, trained, intensity=1.0):
    """Diminishing-returns increment to the trained component from ONE effort (Phase 032): the seed's
    bd_train_strength / bd_train_stamina, intensity x TRAIN_RATE x (ceiling - trained), where the ceiling is
    base x TRAIN_HEADROOM. Anchored to base: a higher base has a higher ceiling and larger absolute gains.
    `intensity` is the effort's stamina cost, capped at 1 (the seed's `intensity` on an Effort node)."""
    intensity = min(1.0, max(0.0, float(intensity)))
    return float(intensity * TRAIN_RATE * max(0.0, train_ceiling(base) - float(trained)))


def efforts_to_train(base, target, intensity):
    """How many efforts of `intensity` a body with base strength `base` (health 1.0) needs before its
    effective strength reaches `target`, applying train_gain once per effort as the world does. None when
    the target is above base x (1 + TRAIN_HEADROOM), the most training can add, or when intensity is 0."""
    base, target = float(base), float(target)
    need = target - base
    if need <= 0.0:
        return 0
    if base * (1.0 + TRAIN_HEADROOM) + 1e-12 < target or float(intensity) <= 0.0:
        return None
    trained, count = 0.0, 0
    while trained + 1e-12 < need:
        trained += train_gain(base, trained, intensity)
        count += 1
    return count


def effective_stat(base, trained, health):
    """The body's EFFECTIVE strength/stamina: the (base + trained) potential SCALED by health -- a sick or
    injured body is weaker. Health 1.0 -> full potential; lower health -> proportionally less. (Mirrors the
    graph rule bd_effective_stats.)"""
    return float((float(base) + float(trained)) * float(health))


def recipe_exertion(name):
    """(strength_req, stamina_cost) for a recipe -- heavy trades demand strength AND tire you; light 0/0."""
    return RECIPE_EXERTION.get(name, (0.0, 0.0))


# ---------------------------------------------------------------------------
# BALANCE MODEL -- the per-period flows a town of a given shape runs on
# ---------------------------------------------------------------------------
# A pure function of the world's data and a scenario (population.BALANCE_SCENARIO, or one scaled by
# population.scale_scenario): what the town's fields, animals, woodland, and water supply, what its
# residents and staple consume, and the minutes of work each stream takes.
def _tag_yield(kind, tag, _memo=None, _seen=frozenset()):
    """Best units of `tag` (e.g. 'fuel', 'nitrogen', 'food') one unit of `kind` can become, following
    recipes forward. An upper bound: other inputs a recipe needs are assumed available."""
    _memo = {} if _memo is None else _memo
    if (kind, tag) in _memo:
        return _memo[(kind, tag)]
    spec = ITEMS.get(kind, {})
    best = feeds(kind) if tag == "food" else float(spec.get(tag, 0.0) or 0.0)
    if kind not in _seen:
        for r in RECIPES:
            for ik, iq in r["in"]:
                if ik == kind and float(iq) > 0:
                    out, oq = r["out"]
                    best = max(best, float(oq) / float(iq) * _tag_yield(out, tag, _memo, _seen | {kind}))
    _memo[(kind, tag)] = best
    return best


def _recipe_unit_cost(r):
    """Reference cost of one unit of a recipe's output made THIS way (inputs + labour)."""
    cost = float(r.get("time_minutes", 0.0)) * LABOUR_RATE
    for k, q in r["in"]:
        m, l = _type_value_parts(k) if is_input_type(k) else _value_parts(k)
        cost += (m + l * LABOUR_RATE) * float(q)
    return cost / float(r["out"][1])


def mean_firewood_demand():
    """The year's mean firewood_demand (WEATHER). Each season is weighted equally (TIME gives each a
    90-day span in the founding calendar), and within a season each weather option is equally likely,
    as the world draws one per day (world_affordances' _set_daily_weather)."""
    per_season = []
    for season in SEASONS.values():
        options = [float(WEATHER[w]["firewood_demand"]) for w in season.get("weather", ()) if w in WEATHER]
        if options:
            per_season.append(sum(options) / len(options))
    return sum(per_season) / len(per_season) if per_season else 1.0


def heating_demand(sc):
    """Fuel burnt for space heating per period (one day), averaged over the year's weather: each of the
    scenario's households burns HEATING base_burn x firewood_demand. Zero without households or HEATING."""
    if not sc or not HEATING:
        return 0.0
    return float(sc.get("households", 0)) * float(HEATING["base_burn"]) * mean_firewood_demand()


def _balance_flows(sc):
    """Per-period supply and demand of a town's coupled flows under scenario `sc` (see
    population.BALANCE_SCENARIO). Returns (flows, notes, work): work is {stream: minutes per period}.
    A pack with no balance scenario (an empty `sc`, as a pack without a founding town may have) has no
    flows and no work: the model is a calibration of the founding town, and it is optional."""
    if not sc or "beds" not in sc:
        return {}, ["no balance scenario in this pack (BALANCE_SCENARIO is empty)"], {}
    flows, notes, work = {}, [], {}
    beds = sc["beds"]
    harvest = {}
    for crop, n in beds.items():
        spec = CROPS[crop]
        per = float(n) / float(spec["grow_periods"])
        harvest[spec["harvest"]] = harvest.get(spec["harvest"], 0.0) + per * float(spec["yield"])
        for k, q in spec.get("byproducts", {}).items():
            harvest[k] = harvest.get(k, 0.0) + per * float(q)
    residents = float(sc["residents"])
    staple = next(r for r in RECIPES if r["name"] == sc["staple"])
    food_demand = residents * float(sc["food_per_resident"])
    # batches of every recipe in the staple's supply chain (inputs made by exactly one recipe)
    chain, chain_seen = {}, set()

    def run_chain(recipe, batches):
        chain[recipe["name"]] = chain.get(recipe["name"], 0.0) + batches
        for kind, qty in recipe["in"]:
            makers = [] if is_input_type(kind) else _recipes_for(kind)
            if makers and kind not in harvest and kind not in chain_seen:
                # follow the cheapest recipe for each intermediate (the one reference_value uses)
                maker = min(makers, key=lambda r: (_recipe_unit_cost(r), r["name"]))
                chain_seen.add(kind)
                run_chain(maker, batches * float(qty) / float(maker["out"][1]))
                chain_seen.discard(kind)

    run_chain(staple, food_demand / float(staple["out"][1]))
    chain_byproducts = {}
    for name, batches in chain.items():
        recipe = next(r for r in RECIPES if r["name"] == name)
        for kind, qty in recipe.get("byproducts", {}).items():
            chain_byproducts[kind] = chain_byproducts.get(kind, 0.0) + batches * float(qty)

    # food: what the harvest could become, best path per crop (upper bound)
    food_supply = sum(q * _tag_yield(k, "food") for k, q in harvest.items())
    staple_supply = sum(q * _tag_yield(k, "food") for k, q in harvest.items()
                        if any(k == ik for ik, _ in staple["in"]) or _tag_yield(k, "food") and k == "grain")
    flows["food (loaves, upper bound)"] = (food_supply, food_demand)
    notes.append(f"food: harvest could make {food_supply:.1f} loaves/period by the best recipes "
                 f"(an upper bound; {staple_supply:.1f} of it from grain)")

    # fuel: the staple burns fuel; straw and the lumber deposit (split into firewood) supply it
    fuel_demand = sum(batches * sum(float(q) for k, q in next(r for r in RECIPES if r["name"] == n)["in"]
                                    if k == "fuel") for n, batches in chain.items())
    heat = heating_demand(sc)
    fuel_demand += heat
    notes.append(f"heating: {float(sc.get('households', 0)):.0f} households burn {heat:.1f} fuel/period on average "
                 f"(base {float(HEATING.get('base_burn', 0.0)):g} x mean firewood demand {mean_firewood_demand():.2f}); "
                 f"the cooking staple chain is the rest")
    straw_heat = sum(q * _tag_yield(k, "fuel") for k, q in harvest.items())
    lumber_regrowth = float(RESOURCE_DEPOSITS["lumber"]["growback"]) * float(sc.get("woodland", 1.0))
    fuel_supply = straw_heat + lumber_regrowth * _tag_yield("lumber", "fuel")
    flows["fuel (heat)"] = (fuel_supply, fuel_demand)
    # the heat straw cannot cover is firewood: felled lumber split into wood
    split = next(r for r in RECIPES if r["name"] == "split_firewood")
    wood_heat = max(0.0, fuel_demand - straw_heat)
    split_batches = wood_heat / (float(split["out"][1]) * _tag_yield("wood", "fuel"))
    work["firewood"] = split_batches * float(split["time_minutes"])
    work["felling"] = split_batches * float(split["in"][0][1]) * float(RESOURCE_DEPOSITS["lumber"]["minutes_per_unit"])

    # nitrogen: beds draw it; mineralisation, legumes, manure, and composted night soil return it
    n_demand = sum(float(n) * float(CROPS[c].get("nitrogen", 0.0)) for c, n in beds.items())
    n_fix = sum(float(n) * float(CROPS[c].get("fixes", 0.0)) for c, n in beds.items())
    mineral = float(sc["plots"]) * float(sc["plot_area"]) * float(NITROGEN["mineralisation_per_area"])
    leach = (float(sc["plots"]) * float(SOILS[sc["soil"]]["nitrogen"]) * float(sc["plot_area"])
             * float(NITROGEN["leaching"]) * float(SOILS[sc["soil"]]["drainage"]))
    manure = sum(float(n) * float(ANIMALS[a].get("manure", 0.0)) for a, n in sc["animals"].items())
    night_soil = residents * float(WASTE_CYCLES["human_waste"]["per_resident"])
    ash = fuel_demand * float(INPUT_TYPES["fuel"]["byproducts"].get("ash", 0.0))
    diet_scraps = sum(float(n) * float(ANIMALS[a].get("ration", 1)) for a, n in sc["animals"].items()
                      if ANIMALS[a]["eats"] == "scraps")
    spare_scraps = max(0.0, chain_byproducts.get("scraps", 0.0) - diet_scraps)
    compost_recipe = next(r for r in RECIPES if r["name"] == "make_compost")
    ns_per, cm_per = (float(q) for k, q in compost_recipe["in"])
    compostables = ash + spare_scraps
    composted = min(night_soil, compostables * ns_per / cm_per)   # each batch needs compostables too
    n_supply = (mineral + n_fix + manure * _tag_yield("manure", "nitrogen")
                + composted * _tag_yield("night_soil", "nitrogen"))
    work["compost"] = composted / ns_per * float(compost_recipe["time_minutes"])
    spread = NITROGEN["fertilise_amount"]
    work["fertilise"] = (manure * _tag_yield("manure", "nitrogen")
                         + composted * _tag_yield("night_soil", "nitrogen")) / spread * FIELD_WORK["fertilise"]
    flows["soil nitrogen"] = (n_supply, n_demand + leach)
    notes.append(f"nitrogen: {composted:.1f} of {night_soil:.1f} night soil/period can be composted -- the "
                 f"heap needs compostables: {ash:.1f} ash + {spare_scraps:.1f} scraps the animals leave "
                 f"(straw is also wanted as fuel and thatch)")

    # animal feed by diet
    diets = {}
    for a, n in sc["animals"].items():
        spec = ANIMALS[a]
        diets[spec["eats"]] = diets.get(spec["eats"], 0.0) + float(n) * float(spec.get("ration", 1))
    for diet, demand in sorted(diets.items()):
        supply = sum(float(PASTURE_YIELDS.get(k, 0.0)) * float(sc["pasture_area"]) for k in feed_kinds(diet))
        supply += sum(harvest.get(k, 0.0) + chain_byproducts.get(k, 0.0) for k in feed_kinds(diet))
        flows[f"feed: {diet}"] = (supply, demand)
    if "grain" in diets:
        notes.append("feed: animals that eat grain compete with people for the staple")

    # water: every growing bed is watered every period, and the staple uses some
    water_demand = sum(float(n) * float(CROPS[c]["water"]) for c, n in beds.items())
    water_demand += food_demand / float(staple["out"][1]) * sum(float(q) for k, q in staple["in"] if k == "water")
    water_supply = sum(float(WATER_SOURCES[k]["yield"]) for k in sc["water_sources"])
    flows["water"] = (water_supply, water_demand)

    # work: the staple chain by trade, the fields, and the animals (minutes per period)
    for name, batches in chain.items():
        recipe = next(r for r in RECIPES if r["name"] == name)
        key = f"trade:{recipe['requires']}"
        work[key] = work.get(key, 0.0) + batches * float(recipe["time_minutes"])
    work["field"] = sum(float(n) * (FIELD_WORK["water"]
                                    + (FIELD_WORK["sow"] + FIELD_WORK["harvest"]) / float(CROPS[c]["grow_periods"]))
                        for c, n in beds.items())
    work["husbandry"] = sum(float(n) * float(ANIMALS[a].get("care_minutes", 0.0)) for a, n in sc["animals"].items())
    labour_have = residents * float(sc["work_minutes_per_resident"])
    flows["labour (minutes)"] = (labour_have, sum(work.values()))
    # stamina: the declared stamina cost (RECIPE_EXERTION) of the recipes the labour streams run, per
    # resident per period, against the stamina rest can restore in the minutes labour leaves free.
    # Streams without a declared cost (field work, husbandry, felling, fertilising) and walking are not
    # counted, so the spend is a lower bound. The affordable figure is an upper bound: it assumes every
    # non-labour tick is a rest action at REST_RECOVERY_PER_UNIT, and reserves no time for sleep.
    spend = sum(batches * recipe_exertion(name)[1] for name, batches in chain.items())
    spend += split_batches * recipe_exertion("split_firewood")[1]
    spend += (composted / ns_per) * recipe_exertion("make_compost")[1]
    per_resident = max(1.0, residents)
    period_minutes = float(TIME["ticks_per_period"]) * float(TIME["minutes_per_tick"])
    free_ticks = max(0.0, period_minutes - sum(work.values()) / per_resident) / float(TIME["minutes_per_tick"])
    flows["stamina (per resident)"] = (free_ticks * REST_RECOVERY_PER_UNIT, spend / per_resident)
    notes.append(f"stamina: labour spends {spend / per_resident:.3f} stamina per resident per period on declared "
                 f"recipe costs (lower bound); rest can restore {free_ticks * REST_RECOVERY_PER_UNIT:.3f} in the "
                 f"{free_ticks:.1f} ticks labour leaves free (upper bound, no sleep reserved)")
    if DAYNIGHT["enabled"]:   # Phase 042: lamp oil, stock against one period's burn
        from domains.daynight import lamp_oil_per_period
        flows["lamp oil (stock vs one period)"] = (float(DAYNIGHT["starting_oil"]), lamp_oil_per_period(
            len(DAYNIGHT_LAMPS), DAYNIGHT["lamp_burn_per_tick"], TIME, DAYNIGHT))
    return flows, notes, work
