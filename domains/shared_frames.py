"""shared_frames.py -- the frames Bigville residents can hold in common, as PURE DATA.

Skills (what a person can do), trades (organised ways of working that exercise skills and make
recipes), and jobs (the positions a resident is seeded into, bundling trades and duties); the shared
concepts, policies, laws, charters, and procedures of the village; land tenure; offices, households,
and the division of labour. A frame here is a TEMPLATE: a resident holds it only once it is seeded,
taught, read, or observed. The world itself is in world_affordances.
"""
from __future__ import annotations


# ---------------------------------------------------------------- SKILLS
# A SKILL is what a person can do with their hands or head -- carried by a person, learned by
# apprenticeship, schooling, or practice, and exercised by recipes. A TRADE (below) is an organised
# way of working: a workshop, its kit, and the skills it exercises. A JOB (further below) is the
# position a resident is seeded into, bundling trades and duties. One skill serves many trades
# (cooking: the cook, the farmer's household); one trade can exercise several skills (the weaver
# spins and weaves). `kind`: craft (made goods), land (fields, animals, woods), care (people),
# office (governance and records), general (anyone's, with practice).
SKILLS = {
    "smithing":      {"kind": "craft"}, "carpentry": {"kind": "craft"}, "sawing": {"kind": "craft"},
    "coopering":     {"kind": "craft"}, "masonry": {"kind": "craft"}, "quarrying": {"kind": "land"},
    "milling":       {"kind": "craft"}, "baking": {"kind": "craft"}, "cooking": {"kind": "general"},
    "brewing":       {"kind": "craft"}, "dairying": {"kind": "craft"}, "butchery": {"kind": "craft"},
    "tanning":       {"kind": "craft"}, "shoemaking": {"kind": "craft"}, "spinning": {"kind": "general"},
    "weaving":       {"kind": "craft"}, "tailoring": {"kind": "craft"}, "dyeing": {"kind": "craft"},
    "papermaking":   {"kind": "craft"}, "printing": {"kind": "craft"}, "inkmaking": {"kind": "craft"},
    "candle_making": {"kind": "craft"}, "charcoal_burning": {"kind": "land"},
    "fieldwork":     {"kind": "land"}, "husbandry": {"kind": "land"}, "shepherding": {"kind": "land"},
    "felling":       {"kind": "land"}, "foraging": {"kind": "general"}, "fishing": {"kind": "land"},
    "smoking":       {"kind": "craft"}, "storekeeping": {"kind": "general"}, "sanitation": {"kind": "general"},
    "water_drawing": {"kind": "general"}, "composting": {"kind": "land"},
    "writing":       {"kind": "office"}, "reckoning": {"kind": "office"}, "governance": {"kind": "office"},
    "law":           {"kind": "office"}, "policing": {"kind": "office"}, "teaching": {"kind": "care"},
    "medicine":      {"kind": "care"}, "midwifery": {"kind": "care"}, "ministry": {"kind": "care"},
    "trading":       {"kind": "general"}, "service": {"kind": "general"}, "labour": {"kind": "general"},
}

# The skills each trade exercises (its first is the trade's main skill, which its recipes use).
TRADE_SKILLS = {
    "smith": ["smithing"], "woodworker": ["carpentry"], "collier": ["charcoal_burning"],
    "sawyer": ["sawing"], "miller": ["milling"], "cooper": ["coopering"], "tanner": ["tanning"],
    "cobbler": ["shoemaking"], "weaver": ["weaving", "spinning"], "tailor": ["tailoring"],
    "brewer": ["brewing"], "dyer": ["dyeing"], "papermaker": ["papermaking"],
    "printer": ["printing", "writing"], "inkmaker": ["inkmaking"], "baker": ["baking"],
    "cook": ["cooking"], "dairymaid": ["dairying"], "fisher": ["fishing"],
    "granary_keeper": ["storekeeping", "reckoning"], "cellar_keeper": ["storekeeping"],
    "water_keeper": ["water_drawing"], "sanitation_keeper": ["sanitation"],
    "compost_keeper": ["composting"], "smoker": ["smoking"],
    "mayor": ["governance", "reckoning"], "constable": ["policing"], "clerk": ["writing", "reckoning"],
    "councillor": ["governance"], "midwife": ["midwifery"], "doctor": ["medicine"],
    "scribe": ["writing"], "teacher": ["teaching", "writing"], "butcher": ["butchery"],
    "farmer": ["fieldwork", "composting"], "shepherd": ["shepherding"], "animal_keeper": ["husbandry"],
    "labourer": ["labour"], "forester": ["felling", "foraging"], "quarrier": ["quarrying"],
    "mason": ["masonry"], "servant": ["service"], "merchant": ["trading", "reckoning"],
    "innkeeper": ["service", "brewing"], "pastor": ["ministry"], "lawyer": ["law", "writing"],
    "reporter": ["writing"], "shopkeeper": ["trading", "reckoning"], "banker": ["reckoning", "trading"],
    "landlord": ["reckoning"], "chandler": ["candle_making"],
}

# Open (household) recipes are done by anyone, so they name the skill they exercise directly.
# Every other recipe exercises its trade's main skill (recipe_skill).
OPEN_RECIPE_SKILLS = {
    "split_firewood": "felling", "lift_saplings": "foraging", "gather_berries": "foraging",
    "gather_mushrooms": "foraging", "pick_apples": "foraging", "pick_pears": "foraging",
    "pick_plums": "foraging", "cut_sage": "foraging", "cut_thyme": "foraging",
    "cut_parsley": "foraging", "make_compost": "composting", "make_thatch": "fieldwork",
    "spin_thread": "spinning", "cut_rags": "tailoring", "bake_bread_at_home": "cooking",
}


def trade_skills(trade):
    """The skills a trade exercises (main skill first)."""
    return list(TRADE_SKILLS.get(trade, ()))


def recipe_skill(recipe):
    """The skill a recipe row exercises: its own for open work, else its trade's main skill."""
    if recipe["name"] in OPEN_RECIPE_SKILLS:
        return OPEN_RECIPE_SKILLS[recipe["name"]]
    skills = TRADE_SKILLS.get(recipe.get("requires"), ())
    return skills[0] if skills else None


def job_skills(job):
    """Every skill a job's trades exercise (no repeats, in trade order)."""
    out = []
    for trade in JOBS[job]["trades"]:
        out += [s for s in TRADE_SKILLS.get(trade, ()) if s not in out]
    return out


# ---------------------------------------------------------------- TRADES
# a trade unifies a role with its building, its typical tools, and its baseline skill. Recipes
# reference the trade via `requires`; a building `provides` it; a tradesperson practises it with a
# skill (which sets the QUALITY of everything the trade makes). Adding a trade is a data row.
TRADES = {
    "smith":      {"building": "forge",           "tools": ["hammer"], "base_skill": 0.7},
    "woodworker": {"building": "woodshop",        "tools": ["saw"],    "base_skill": 0.7},
    "collier":    {"building": "charcoal_hearth", "tools": [],         "base_skill": 0.6},
    "sawyer":     {"building": "sawpit",          "tools": ["saw"],    "base_skill": 0.6},
    "miller":     {"building": "mill",            "tools": [],         "base_skill": 0.6},
    "cooper":     {"building": "cooperage",       "tools": ["adze"],   "base_skill": 0.7},
    "tanner":     {"building": "tannery",         "tools": [],         "base_skill": 0.6},
    "cobbler":    {"building": "cobbler",         "tools": ["awl"],    "base_skill": 0.7},
    "weaver":     {"building": "weavery",         "tools": ["loom"],   "base_skill": 0.7},
    "tailor":     {"building": "tailorshop",      "tools": ["needle"], "base_skill": 0.7},
    "brewer":     {"building": "inn",             "tools": ["mash_tun"], "base_skill": 0.6},
    "dyer":       {"building": "dyehouse",        "tools": ["dye_vat"],  "base_skill": 0.6},
    "papermaker": {"building": "papermill",       "tools": ["press"],    "base_skill": 0.6},
    "printer":    {"building": "printshop",       "tools": ["printing_press"], "base_skill": 0.7, "literacy": 0.9, "capability": 0.8},
    "inkmaker":   {"building": "inkhouse",        "tools": [],           "base_skill": 0.6},
    "baker":      {"building": "bakery",      "tools": ["oven"],  "base_skill": 0.7},
    "cook":       {"building": "kitchen",     "tools": ["pot"],   "base_skill": 0.6},
    "dairymaid":  {"building": "dairy",       "tools": ["churn"], "base_skill": 0.6},
    "fisher":     {"building": "wharf",       "tools": ["net"],   "base_skill": 0.6},
    "granary_keeper": {"building": "granary", "tools": [], "base_skill": 0.5},
    "cellar_keeper": {"building": "root_cellar", "tools": [], "base_skill": 0.5},
    "water_keeper": {"building": "wellhouse", "tools": ["bucket"], "base_skill": 0.5},
    "sanitation_keeper": {"building": "latrine", "tools": [], "base_skill": 0.5},
    "compost_keeper": {"building": "compost_yard", "tools": [], "base_skill": 0.5},
    "smoker":     {"building": "smokehouse", "tools": [], "base_skill": 0.6},
    "mayor":      {"building": "townhall", "tools": [], "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "constable":  {"building": "watchhouse", "tools": [], "base_skill": 0.7},
    "clerk":      {"building": "townhall", "tools": ["quill"], "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "councillor": {"building": "townhall", "tools": [], "base_skill": 0.6, "literacy": 0.8, "capability": 0.8},
    "midwife":    {"building": "surgery", "tools": [], "base_skill": 0.7, "literacy": 0.7, "capability": 0.8},
    "doctor":     {"building": "surgery", "tools": [], "base_skill": 0.8, "literacy": 0.9, "capability": 0.9},
    "scribe":     {"building": "scriptorium", "tools": ["quill"], "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "teacher":    {"building": "school",       "tools": [],        "base_skill": 0.7, "literacy": 0.95, "capability": 0.95},
    "butcher":    {"building": "shambles",     "tools": ["cleaver"], "base_skill": 0.6},
    # Occupations of the cast whose work is outdoors or not tied to a catalogue building.
    # `building: None` + `site` names the map work-site kind instead.
    "farmer":        {"building": None, "site": "farm",    "tools": ["spade", "plough"], "base_skill": 0.7},
    "shepherd":      {"building": None, "site": "pasture", "tools": [],         "base_skill": 0.6},
    "animal_keeper": {"building": None, "site": "pasture", "tools": [],         "base_skill": 0.6},
    "labourer":      {"building": None, "site": "market",  "tools": [],         "base_skill": 0.5},
    "forester":      {"building": None, "site": "lumber",  "tools": ["axe"],    "base_skill": 0.6},
    "quarrier":      {"building": None, "site": "stone",   "tools": ["pick"],   "base_skill": 0.6},
    "mason":         {"building": None, "site": "mason",   "tools": ["hammer"], "base_skill": 0.7},
    "servant":       {"building": None, "site": "manor",   "tools": [],         "base_skill": 0.5},
    "merchant":      {"building": None, "site": "market",  "tools": [],         "base_skill": 0.7, "literacy": 0.8, "capability": 0.8},
    "innkeeper":     {"building": "inn",      "tools": ["mash_tun"], "base_skill": 0.7},
    "pastor":        {"building": "church",   "tools": [],  "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "lawyer":        {"building": "townhall", "tools": ["quill"], "base_skill": 0.7, "literacy": 0.95, "capability": 0.9},
    "reporter":      {"building": "printshop", "tools": ["quill"], "base_skill": 0.6, "literacy": 0.9, "capability": 0.8},
    "shopkeeper":    {"building": None, "site": "store",  "tools": [], "base_skill": 0.7, "literacy": 0.8, "capability": 0.8},
    "banker":        {"building": None, "site": "bank",   "tools": [], "base_skill": 0.7, "literacy": 0.95, "capability": 0.9},
    "landlord":      {"building": None, "site": "estate", "tools": [], "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "chandler":      {"building": None, "site": "market", "tools": ["pot"], "base_skill": 0.6},
}


# ---------------------------------------------------------------- LAND TENURE AND REGISTRY
# Land is a physical parcel; title, deed, lease, and dispute records are institutional objects layered
# over it. A registry entry is not automatically known by every resident: the clerk registers it, the
# parties/witnesses may know it, and others learn it by inspecting or hearing the record.
LAND_TENURE = {
    "freehold": {"transferable": True, "heritable": True, "term": None, "rights": ["use", "exclude", "transfer"]},
    "lease": {"transferable": False, "heritable": False, "term": 12, "rights": ["use", "harvest"]},
    "commons": {"transferable": False, "heritable": False, "term": None, "rights": ["use", "graze", "gather"]},
    "stewardship": {"transferable": False, "heritable": False, "term": None, "rights": ["manage", "harvest", "maintain"]},
}

LAND_RECORDS = {
    "office": "records_office",
    "register": "land_register",
    "recorded_by": "clerk",
    "required_fields": ["parcel", "holder", "tenure", "effective", "witnesses", "basis"],
    "public_inspection": True,
    "archive": "deed_archive",
}

DEED_TYPES = {
    "grant": {"parties": ["grantor", "grantee"], "requires": ["authority", "parcel", "witnesses"], "changes": "title"},
    "sale": {"parties": ["seller", "buyer"], "requires": ["consideration", "parcel", "witnesses"], "changes": "title"},
    "lease": {"parties": ["lessor", "lessee"], "requires": ["term", "parcel", "witnesses"], "changes": "possession"},
    "inheritance": {"parties": ["predecessor", "successor"], "requires": ["death_or_will", "parcel", "witnesses"], "changes": "title"},
    "boundary": {"parties": ["neighbour_a", "neighbour_b"], "requires": ["survey", "witnesses"], "changes": "boundary"},
}

LAND_DISPUTES = {
    "trespass": {"remedies": ["warning", "compensation", "injunction"]},
    "boundary": {"remedies": ["survey", "boundary_order", "compensation"]},
    "inheritance": {"remedies": ["title_award", "shared_use", "compensation"]},
    "lease_default": {"remedies": ["cure_period", "termination", "compensation"]},
    "commons_enclosure": {"remedies": ["removal", "fine", "restoration"]},
}


# ---------------------------------------------------------------- SHARED REFERENCES
# A reference is a physical subject/predicate/object template in domain data, not a town fact or
# resident belief. `seed_roles` is retained as authoring metadata for character setup tools; the
# physical world must not infer knowledge from role or population composition.
SHARED_CONCEPTS = [
    {"name": "grain_in_granary",
     "reference": {"subject": "grain", "predicate": "stored_in", "object": "granary"},
     "seed_roles": ["farmer", "farm_labourer", "miller", "baker", "cook", "granary_keeper"]},
    {"name": "roots_in_cellar",
     "reference": {"subject": "root_crops", "predicate": "stored_in", "object": "root_cellar"},
     "seed_roles": ["farmer", "farm_labourer", "cook", "granary_keeper"]},
    {"name": "prepared_food_in_pantry",
     "reference": {"subject": "prepared_food", "predicate": "stored_in", "object": "pantry"},
     "seed_roles": ["cook", "baker", "dairymaid", "granary_keeper", "innkeeper"]},
    {"name": "granary_is_long_term_storage",
     "reference": {"subject": "granary", "predicate": "provides", "object": "long_term_storage"},
     "seed_roles": ["farmer", "farm_labourer", "miller", "granary_keeper", "clerk"]},
    {"name": "miller_grinds_grain",
     "reference": {"subject": "miller", "predicate": "processes", "object": "grain"},
     "seed_roles": ["farmer", "farm_labourer", "miller", "baker", "cook"]},
    {"name": "cook_needs_heat_and_containment",
     "reference": {"subject": "cooking", "predicate": "requires", "object": "heat_and_containment"},
     "seed_roles": ["cook", "baker", "dairymaid"]},
    {"name": "food_requires_serving_vessel",
     "reference": {"subject": "soup_or_drink", "predicate": "served_with", "object": "vessel_and_utensil"},
     "seed_roles": ["cook", "baker", "dairymaid", "innkeeper"]},
    {"name": "constable_holds_constable_post",
     "reference": {"subject": "constable", "predicate": "holds_position", "object": "constable_post"},
     "seed_roles": ["*"], "requires_role": "constable"},
    {"name": "mayor_holds_mayoral_office",
     "reference": {"subject": "mayor", "predicate": "holds_position", "object": "mayoral_office"},
     "seed_roles": ["*"], "requires_role": "mayor"},
    {"name": "market_is_public_exchange",
     "reference": {"subject": "market", "predicate": "is_for", "object": "public_exchange"},
     "seed_roles": ["*"]},
    {"name": "well_provides_clean_water",
     "reference": {"subject": "well", "predicate": "provides", "object": "clean_water"},
     "seed_roles": ["farmer", "farm_labourer", "water_keeper", "midwife", "doctor"]},
    {"name": "latrine_kept_away_from_well",
     "reference": {"subject": "latrine", "predicate": "kept_away_from", "object": "well"},
     "seed_roles": ["water_keeper", "sanitation_keeper", "midwife", "doctor", "clerk"]},
    {"name": "manure_returns_to_soil",
     "reference": {"subject": "manure", "predicate": "returns_to", "object": "soil"},
     "seed_roles": ["farmer", "farm_labourer", "compost_keeper", "animal_keeper"]},
    {"name": "crop_rotation_preserves_fertility",
     "reference": {"subject": "crop_rotation", "predicate": "preserves", "object": "soil_fertility"},
     "seed_roles": ["farmer", "farm_labourer", "miller"]},
    {"name": "maintenance_prevents_failure",
     "reference": {"subject": "maintenance", "predicate": "prevents", "object": "infrastructure_failure"},
     "seed_roles": ["craftsperson", "labourer", "mayor", "clerk"]},
    {"name": "illness_requires_care_and_rest",
     "reference": {"subject": "illness", "predicate": "requires", "object": "care_and_rest"},
     "seed_roles": ["parent", "midwife", "doctor", "teacher"]},
    {"name": "contagious_illness_requires_separation",
     "reference": {"subject": "contagious_illness", "predicate": "requires", "object": "separation"},
     "seed_roles": ["midwife", "doctor", "constable", "mayor"]},
    {"name": "children_require_care",
     "reference": {"subject": "children", "predicate": "require", "object": "adult_care"},
     "seed_roles": ["parent", "midwife", "teacher"]},
    {"name": "weather_changes_work_priorities",
     "reference": {"subject": "weather", "predicate": "changes", "object": "work_priorities"},
     "seed_roles": ["farmer", "farm_labourer", "forester", "mayor", "clerk"]},
    {"name": "land_registry_records_title",
     "reference": {"subject": "land_registry", "predicate": "records", "object": "land_title"},
     "seed_roles": ["clerk", "mayor", "councillor", "farmer", "constable"]},
    {"name": "deed_is_evidence_of_transfer",
     "reference": {"subject": "deed", "predicate": "is_evidence_of", "object": "land_transfer"},
     "seed_roles": ["clerk", "mayor", "councillor", "farmer"]},
    {"name": "registered_title_identifies_holder",
     "reference": {"subject": "registered_title", "predicate": "identifies", "object": "land_holder"},
     "seed_roles": ["clerk", "mayor", "councillor", "constable", "farmer"]},
    {"name": "land_dispute_goes_to_council",
     "reference": {"subject": "land_dispute", "predicate": "goes_to", "object": "council_hearing"},
     "seed_roles": ["clerk", "mayor", "councillor", "constable", "farmer"]},
    {"name": "paths_are_preferred_travel_surface",
     "reference": {"subject": "path", "predicate": "preferred_for", "object": "travel"},
     "seed_roles": ["*"]},
    {"name": "terrain_changes_travel_cost",
     "reference": {"subject": "terrain", "predicate": "changes", "object": "travel_speed_and_stamina"},
     "seed_roles": ["*"]},
]


# Policies and laws have two representations: a durable written document and resident-held concepts.
# Each concept is deliberately present at several abstraction levels. A resident may understand the
# principle without knowing the office procedure, or know the procedure without understanding its
# justification. The document is never the resident's knowledge by itself.
LOCAL_POLICIES = [
    {"name": "winter_food_reserve", "title": "Winter Food Reserve Policy", "kind": "policy",
     "scope": "village", "seed_roles": ["mayor", "clerk", "farmer", "miller", "granary_keeper", "cook"],
     "concepts": [
         {"name": "reserve_food_for_winter", "abstraction": "principle", "reference": {"subject": "village", "predicate": "should_preserve", "object": "food_for_winter"}},
         {"name": "reserve_is_administered_by_granary", "abstraction": "institutional", "reference": {"subject": "granary_keeper", "predicate": "administers", "object": "winter_reserve"}},
         {"name": "reserve_stock_is_counted_monthly", "abstraction": "operational", "reference": {"subject": "reserve_stock", "predicate": "is_counted", "object": "monthly"}},
     ]},
    {"name": "water_safety_policy", "title": "Water Safety Policy", "kind": "policy",
     "scope": "village", "seed_roles": ["mayor", "clerk", "midwife", "doctor", "constable"],
     "concepts": [
         {"name": "clean_water_protects_health", "abstraction": "principle", "reference": {"subject": "clean_water", "predicate": "protects", "object": "health"}},
         {"name": "well_is_kept_separate_from_latrine", "abstraction": "institutional", "reference": {"subject": "well", "predicate": "kept_separate_from", "object": "latrine"}},
         {"name": "water_source_is_inspected_after_flood", "abstraction": "operational", "reference": {"subject": "water_source", "predicate": "is_inspected_after", "object": "flood"}},
     ]},
]

LOCAL_LAWS = [
    {"name": "commons_and_land_law", "title": "Commons and Land Ordinance", "kind": "law",
     "scope": "village", "seed_roles": ["mayor", "clerk", "constable", "councillor", "farmer"],
     "concepts": [
         {"name": "commons_are_shared_resource", "abstraction": "principle", "reference": {"subject": "commons", "predicate": "belongs_to", "object": "village"}},
         {"name": "council_sets_grazing_rules", "abstraction": "institutional", "reference": {"subject": "council", "predicate": "sets_rules_for", "object": "grazing"}},
         {"name": "unauthorised_enclosure_is_offence", "abstraction": "operational", "reference": {"subject": "unauthorised_enclosure", "predicate": "is", "object": "offence"}},
     ]},
    {"name": "public_order_law", "title": "Public Order and Protection Law", "kind": "law",
     "scope": "village", "seed_roles": ["mayor", "clerk", "constable", "councillor"],
     "concepts": [
         {"name": "people_and_property_are_protected", "abstraction": "principle", "reference": {"subject": "constable", "predicate": "protects", "object": "people_and_property"}},
         {"name": "constable_answers_to_council", "abstraction": "institutional", "reference": {"subject": "constable", "predicate": "answers_to", "object": "council"}},
         {"name": "theft_is_reported_to_constable", "abstraction": "operational", "reference": {"subject": "theft", "predicate": "is_reported_to", "object": "constable"}},
     ]},
]


# Giantville supplies the constitutional floor and general policy. Bigville inherits these entries as
# seed data: they are immutable from within Bigville, but their enforcement is still local.
GIANTVILLE_POLICIES = [
    {"name": "giantville_public_health_baseline", "title": "Public Health Baseline", "kind": "policy",
     "scope": "giantville_and_dependencies", "origin": "giantville", "immutable": True,
     "enforcement": "bigville", "seed_roles": ["mayor", "clerk", "midwife", "doctor", "constable"],
     "concepts": [
         {"name": "safe_water_is_public_duty", "abstraction": "principle", "reference": {"subject": "safe_water", "predicate": "is", "object": "public_duty"}},
         {"name": "health_officers_report_outbreaks", "abstraction": "institutional", "reference": {"subject": "health_officer", "predicate": "reports", "object": "outbreak"}},
         {"name": "outbreak_isolation_is_authorised", "abstraction": "operational", "reference": {"subject": "outbreak", "predicate": "authorises", "object": "isolation"}},
     ]},
]

GIANTVILLE_LAWS = [
    {"name": "giantville_murder_law", "title": "Prohibition of Murder", "kind": "law",
     "scope": "giantville_and_dependencies", "origin": "giantville", "immutable": True,
     "enforcement": "bigville", "seed_roles": ["mayor", "clerk", "constable", "councillor"],
     "concepts": [
         {"name": "murder_is_forbidden", "abstraction": "principle", "reference": {"subject": "murder", "predicate": "is", "object": "forbidden"}},
         {"name": "constable_investigates_murder", "abstraction": "institutional", "reference": {"subject": "constable", "predicate": "investigates", "object": "murder"}},
         {"name": "murder_is_reported_and_prosecuted", "abstraction": "operational", "reference": {"subject": "murder", "predicate": "is", "object": "reported_and_prosecuted"}},
     ]},
    {"name": "giantville_theft_law", "title": "Prohibition of Theft", "kind": "law",
     "scope": "giantville_and_dependencies", "origin": "giantville", "immutable": True,
     "enforcement": "bigville", "seed_roles": ["mayor", "clerk", "constable", "councillor", "merchant"],
     "concepts": [
         {"name": "theft_is_forbidden", "abstraction": "principle", "reference": {"subject": "theft", "predicate": "is", "object": "forbidden"}},
         {"name": "constable_recognises_property_claims", "abstraction": "institutional", "reference": {"subject": "constable", "predicate": "recognises", "object": "property_claims"}},
         {"name": "stolen_goods_are_recovered", "abstraction": "operational", "reference": {"subject": "stolen_goods", "predicate": "are", "object": "recovered"}},
     ]},
]

LAWMAKING_PROCEDURES = {
    "proposal": {"actor": "resident_or_councillor", "requires": ["grievance_or_need", "witnessed_observation"]},
    "notice": {"actor": "clerk", "requires": ["written_proposal", "public_notice"]},
    "deliberation": {"actor": "council", "requires": ["meeting", "speakers", "record"]},
    "vote": {"actor": "council", "requires": ["quorum", "majority"]},
    "promulgation": {"actor": "clerk", "requires": ["approved_law", "written_record"]},
    "effective": {"actor": "council", "requires": ["effective_date", "public_notice"]},
}

JUSTICE_PROCEDURES = {
    "complaint": {"actor": "resident", "requires": ["harm_or_claim", "complainant"]},
    "investigation": {"actor": "constable", "requires": ["complaint", "witnesses", "property_or_scene"]},
    "hearing": {"actor": "council_or_court", "requires": ["notice", "accused", "evidence"]},
    "judgment": {"actor": "council_or_court", "requires": ["hearing", "law", "record"]},
    "remedy": {"actor": "constable_or_council", "requires": ["judgment", "proportionate_penalty"]},
    "appeal": {"actor": "council", "requires": ["judgment", "new_evidence_or_error"]},
}

CHARTERS = [
    {"name": "bigville_council_charter", "title": "Charter of the Bigville Council", "kind": "charter",
     "scope": "bigville", "origin": "giantville", "immutable": True, "enforcement": "bigville",
     "seed_roles": ["mayor", "clerk", "constable", "councillor", "lawyer", "teacher"],
     "concepts": [
         {"name": "council_derives_authority_from_charter", "abstraction": "principle", "reference": {"subject": "council", "predicate": "derives_authority_from", "object": "charter"}},
         {"name": "council_makes_local_law", "abstraction": "institutional", "reference": {"subject": "council", "predicate": "makes", "object": "local_law"}},
         {"name": "local_law_requires_notice_and_majority", "abstraction": "operational", "reference": {"subject": "local_law", "predicate": "requires", "object": "notice_and_majority"}},
         {"name": "justice_requires_hearing_and_record", "abstraction": "principle", "reference": {"subject": "justice", "predicate": "requires", "object": "hearing_and_record"}},
         {"name": "constable_investigates_council_judges", "abstraction": "institutional", "reference": {"subject": "constable", "predicate": "investigates_and_council", "object": "judges"}},
         {"name": "judgment_is_written_before_remedy", "abstraction": "operational", "reference": {"subject": "judgment", "predicate": "precedes", "object": "remedy"}},
     ]},
]

# Public compatibility views: the canonical Bigville world sees the inherited and local seed data as
# one law/policy book, while origin and immutability remain explicit on every entry.
for _bundle in LOCAL_POLICIES + LOCAL_LAWS:
    _bundle.setdefault("origin", "bigville")
    _bundle.setdefault("immutable", False)
    _bundle.setdefault("enforcement", "bigville")
POLICIES = GIANTVILLE_POLICIES + LOCAL_POLICIES
LAWS = GIANTVILLE_LAWS + LOCAL_LAWS


def all_reference_templates():
    """Flatten base concepts plus policy/law concepts into seedable reference templates."""
    templates = []
    for concept in SHARED_CONCEPTS:
        row = dict(concept)
        row.setdefault("abstraction", "operational")
        row.setdefault("source_kind", "shared")
        templates.append(row)
    for bundle in POLICIES + LAWS + CHARTERS:
        for concept in bundle["concepts"]:
            row = dict(concept)
            row["source_kind"] = bundle["kind"]
            row["source_name"] = bundle["name"]
            row["source_origin"] = bundle.get("origin", "bigville")
            row["source_immutable"] = bool(bundle.get("immutable", False))
            row.setdefault("seed_roles", bundle.get("seed_roles", []))
            templates.append(row)
    return templates


def shared_concepts_for(role, present_roles=None):
    """Legacy authoring helper; world construction must not use it to assign beliefs."""
    present = set(present_roles or ())
    return [c for c in all_reference_templates()
            if ("*" in c.get("seed_roles", ()) or role in c.get("seed_roles", ()))
            and (not c.get("requires_role") or c["requires_role"] in present)]

# The map/cast uses plain-language occupations while the craft catalogue uses production trades.
# These bridges preserve the resident's public occupation and seed the corresponding capabilities.
CAST_ROLE_TRADES = {
    "carpenter": ("woodworker",),
    "farm_labourer": ("farmer",),
    "farmer": ("farmer", "cook"),
    "fishmonger": ("fisher",),
    "forester": ("forester", "collier"),
}

HOUSEHOLDS = {
    "farm_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["land", "livestock", "tools"]},
    "craft_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["workshop", "tools"]},
    "landless_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["labour"]},
    "institutional_household": {"members": ["adult", "child"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["office", "records"]},
}

LABOUR_TASKS = {
    "water": {"seasonal": True, "skills": ["labourer", "farmer"], "inputs": ["container", "water_source"], "outputs": ["water"]},
    "farm": {"seasonal": True, "skills": ["farmer", "farm_labourer"], "inputs": ["land", "seed", "water"], "outputs": ["harvest"]},
    "preserve": {"seasonal": True, "skills": ["cook", "baker", "dairymaid"], "inputs": ["food", "salt", "fuel"], "outputs": ["preserved_food"]},
    "mill": {"seasonal": False, "skills": ["miller"], "inputs": ["grain", "mill"], "outputs": ["flour"]},
    "fuel": {"seasonal": True, "skills": ["labourer", "collier", "forester"], "inputs": ["woodlot", "tool"], "outputs": ["fuel"]},
    "maintenance": {"seasonal": False, "skills": ["craftsperson", "labourer"], "inputs": ["material", "tool"], "outputs": ["condition"]},
    "care": {"seasonal": False, "skills": ["parent", "midwife", "doctor"], "inputs": ["time", "medicine"], "outputs": ["health"]},
    "governance": {"seasonal": False, "skills": ["mayor", "clerk", "constable", "councillor"], "inputs": ["records", "authority"], "outputs": ["decision"]},
}

GOVERNANCE_OFFICES = {
    "mayor": {"authority": "executive", "records": True, "appoints": ["constable", "clerk"]},
    "constable": {"authority": "enforcement", "records": True, "protects": ["people", "property"]},
    "clerk": {"authority": "records", "records": True, "maintains": ["taxes", "land", "laws"]},
    "councillor": {"authority": "deliberative", "records": False, "decides": ["commons", "works", "emergency"]},
    "midwife": {"authority": "care", "records": True, "supports": ["birth", "infant", "mother"]},
    "doctor": {"authority": "care", "records": True, "supports": ["injury", "disease"]},
}


# ---------------------------------------------------------------------------
# MIN_SKILL -- the minimum skill to ATTEMPT a recipe at all (apprenticeship)
# ---------------------------------------------------------------------------
# Distinct from difficulty (which sets how WELL it comes out): min_skill is the floor below which you
# cannot make the thing at all. Basic work is 0.0 -- an apprentice can attempt it (badly). Master /
# specialist work needs real skill in the hand, which you build by APPRENTICESHIP over time: you
# cannot simply read how to be a blacksmith or a fine tailor. A recipe not listed here is 0.0.
MIN_SKILL = {
    # master smithing
    "forge_plough": 0.7, "smelt_iron": 0.65, "forge_scythe": 0.5,
    # the wright's heavy work
    "make_wagon": 0.7, "make_cart": 0.6,
    # fine tailoring (the specialist recipes -- already common:False, so learned AND skilled)
    "sew_gown": 0.7, "sew_doublet": 0.65, "sew_fur_cloak": 0.6, "sew_silk_shirt": 0.6, "sew_fine_hat": 0.55,
}


def min_skill(recipe_name):
    """The minimum skill needed to ATTEMPT a recipe (default 0.0 -- apprentice-level work)."""
    return float(MIN_SKILL.get(recipe_name, 0.0))


# ---------------------------------------------------------------------------
# LITERACY + GENERAL CAPABILITY -- class-graded, and raised by schooling
# ---------------------------------------------------------------------------
# Reading/writing and general capability (reckoning, comprehension) are NOT the trade skill in the
# hand -- a fine smith may be illiterate. They are class-graded into three tiers:
#   - labouring (farm labourers): LOW literacy -- cannot reliably read or write.
#   - middle: FUNCTIONAL literacy -- read/write notes, read the newspaper and get most of it.
#   - educated: read & understand the council LAWS and do ACCOUNTING.
# THIS town is uppity, though: residents default to EDUCATED (the world's add_actor default) -- a
# labouring/middle start is opt-in. Schooling raises both, for those who go and can learn. Two
# thresholds name the tiers:
LIT_FUNCTIONAL = 0.4   # read/write notes, read the newspaper, read a written recipe
LIT_EDUCATED   = 0.8   # read & understand the council laws; keep accounts


def literacy_tier(literacy):
    """Name the reading tier a literacy level sits in: labouring / functional / educated."""
    if float(literacy) >= LIT_EDUCATED:
        return "educated"
    if float(literacy) >= LIT_FUNCTIONAL:
        return "functional"
    return "labouring"


# ---------------------------------------------------------------------------
# ECONOMIC SYSTEMS -- how the village groups its trades
# ---------------------------------------------------------------------------
# Which economic system each trade's recipes belong to (the self-test weighs systems and their
# coupling by this).
SYSTEM_OF_TRADE = {
    "farmer": "agriculture", "forester": "forestry", "collier": "fuel",
    "sawyer": "timber", "woodworker": "timber", "cooper": "timber",
    "smith": "metal", "quarrier": "stone", "mason": "stone",
    "miller": "food", "baker": "food", "cook": "food", "dairymaid": "food", "butcher": "food",
    "brewer": "drink", "tanner": "textiles", "cobbler": "textiles", "weaver": "textiles",
    "tailor": "textiles", "dyer": "textiles", "papermaker": "writing", "printer": "writing",
    "inkmaker": "writing", "scribe": "writing", "chandler": "household",
}


# ---------------------------------------------------------------------------
# JOBS -- who the founding townspeople are
# ---------------------------------------------------------------------------
# A JOB is what a resident is seeded as: the trades (capabilities) it carries and the tools its holder
# starts with. Its WEIGHT -- how many full-time workers the town needs in it -- is derived, not
# guessed: the balance model says how many minutes per period each work stream takes for a town of N
# (the staple chain by trade, field work, animal care, firewood, felling, compost, fertilising), and
# `duties` says what share of each stream this job covers. Jobs the model cannot derive (crafts,
# offices, services) give a full-time-equivalent load as `fixed + per_100 * N / 100`: a village of
# eight still needs someone to keep order part-time; a town of 400 needs several constables.
#
# seed_jobs(N) turns the weights into N residents. Heavy jobs get several holders; light ones are
# packed together so one person in a hamlet is farmer, constable, and smith. Spare residents go where
# the margin is thinnest. That is only the starting point: after seeding, residents decide for
# themselves, and `open` recipes (splitting firewood, gathering, composting) can be done by anyone
# capable who holds the tools -- everyone else buys the result or is given it.
JOBS = {
    # production jobs: their load is derived from the balance model's work streams
    "farmer":        {"trades": ["farmer", "cook"], "tools": ["spade", "scythe"],
                      "duties": {"field": 0.6, "compost": 1.0, "fertilise": 1.0}},
    "farm_labourer": {"trades": ["farmer"], "tools": ["spade"], "duties": {"field": 0.4}},
    "animal_keeper": {"trades": ["animal_keeper", "shepherd"], "tools": [], "duties": {"husbandry": 1.0}},
    "miller":        {"trades": ["miller"], "tools": [], "duties": {"trade:miller": 1.0}},
    "baker":         {"trades": ["baker"], "tools": [], "duties": {"trade:baker": 1.0}},
    "forester":      {"trades": ["forester", "collier"], "tools": ["axe"],
                      "duties": {"firewood": 1.0, "felling": 1.0}},
    # crafts: full-time equivalents = fixed + per_100 * residents / 100
    "smith":         {"trades": ["smith"], "tools": ["hammer"], "fixed": 0.10, "per_100": 1.0},
    "carpenter":     {"trades": ["woodworker", "sawyer"], "tools": ["saw"], "fixed": 0.10, "per_100": 1.0},
    "cooper":        {"trades": ["cooper"], "tools": ["adze"], "fixed": 0.05, "per_100": 0.5},
    "mason":         {"trades": ["mason", "quarrier"], "tools": ["hammer", "pick"], "fixed": 0.05, "per_100": 1.0},
    "leatherworker": {"trades": ["tanner", "cobbler"], "tools": ["awl"], "fixed": 0.05, "per_100": 0.5},
    "weaver":        {"trades": ["weaver"], "tools": [], "fixed": 0.05, "per_100": 0.5},
    "tailor":        {"trades": ["tailor", "dyer"], "tools": ["needle"], "fixed": 0.05, "per_100": 0.5},
    "fisher":        {"trades": ["fisher"], "tools": ["net"], "fixed": 0.0, "per_100": 2.0},
    "butcher":       {"trades": ["butcher"], "tools": ["cleaver"], "fixed": 0.05, "per_100": 0.5},
    "dairymaid":     {"trades": ["dairymaid"], "tools": ["churn"], "fixed": 0.05, "per_100": 0.5},
    "innkeeper":     {"trades": ["innkeeper", "brewer"], "tools": ["mash_tun"], "fixed": 0.10, "per_100": 1.0},
    # offices and services
    "mayor":         {"trades": ["mayor"], "tools": [], "fixed": 0.20, "per_100": 0.8},
    "clerk":         {"trades": ["clerk", "scribe"], "tools": ["quill"], "fixed": 0.10, "per_100": 1.5},
    "constable":     {"trades": ["constable"], "tools": [], "fixed": 0.20, "per_100": 0.8},
    "councillor":    {"trades": ["councillor"], "tools": [], "fixed": 0.10, "per_100": 1.0},
    "teacher":       {"trades": ["teacher"], "tools": [], "fixed": 0.10, "per_100": 1.5},
    "doctor":        {"trades": ["doctor"], "tools": [], "fixed": 0.10, "per_100": 0.9},
    "midwife":       {"trades": ["midwife"], "tools": [], "fixed": 0.10, "per_100": 0.9},
    "pastor":        {"trades": ["pastor"], "tools": [], "fixed": 0.20, "per_100": 0.8},
    # whoever is left: general hands, who can still do any open work they hold the tools for
    "labourer":      {"trades": ["labourer"], "tools": ["axe"], "spare": True},
}
