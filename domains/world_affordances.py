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

# ---------------------------------------------------------------- ITEMS
# materials are bulk (measured piles); tools are discrete, made, and wear.
ITEMS = {
    # --- materials (bulk piles) ---
    "wood":     {"class": "material", "bulk": True, "fuel": 1.0},   # `fuel` = heat per unit (INPUT_TYPES)
    "timber":   {"class": "material", "bulk": True, "weight": 2.0, "volume": 3.0},  # bulky
    "ore":      {"class": "material", "bulk": True},
    "iron":     {"class": "material", "bulk": True, "weight": 3.0, "volume": 0.5},   # dense: heavy, small
    "charcoal": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "fuel": 3.0},  # burns hottest
    "grain":    {"class": "material", "bulk": True},
    "flour":    {"class": "material", "bulk": True},
    "coin":     {"class": "material", "bulk": True},
    # ecological cycles and maintenance materials
    "straw":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 2.0, "fuel": 0.3, "compostable": 1.0},
    "thatch":   {"class": "material", "bulk": True, "weight": 0.3, "volume": 2.0},
    "peat":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "fuel": 1.5},
    "dung":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "fuel": 0.6, "nitrogen": 0.4},  # dried: burn it or spread it
    "manure":   {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "nitrogen": 0.5},  # `nitrogen` = N per unit spread
    "compost":  {"class": "material", "bulk": True, "weight": 0.6, "volume": 1.0, "nitrogen": 0.6},
    "night_soil": {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0},   # latrine waste; must be composted before use
    "ash":      {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.5, "compostable": 1.0},  # left by burning fuel
    "medicine": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2, "imported": True},
    "nectar":   {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "wax":      {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.7, "candle_fat": 1.0},
    # --- crop seeds (one entry per crop in CROPS; `seed: True` marks sowable stock) ---
    "wheat_seed":    {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "barley_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "oats_seed":     {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "rye_seed":      {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "cabbage_seed":  {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "carrot_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "onion_seed":    {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "potato_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "turnip_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "bean_seed":     {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "pea_seed":      {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "leek_seed":     {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "parsnip_seed":  {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "beet_seed":     {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "garlic_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "lettuce_seed":  {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "cucumber_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "lentil_seed":   {"class": "material", "bulk": True, "seed": True, "weight": 0.2, "volume": 0.3},
    # --- tools (discrete; verb + fitness + wear + make time/effort; composite = head+handle) ---
    "knife":  {"class": "tool", "material": "metal", "verb": "cut",    "base_mult": 1.6, "wear_rate": 0.10, "make_minutes": 90,  "make_effort": 1.2, "composite": False, "demand_driver": "general", "demand_weight": 0, "base_demand": 2},
    "nails":  {"class": "tool", "material": "metal", "verb": "fasten", "base_mult": 0.8, "wear_rate": 0.05, "make_minutes": 10,  "make_effort": 1.2, "composite": False, "discrete": False, "demand_driver": "building", "demand_weight": 2, "base_demand": 1},  # a batch good (bulk), not an individually-worn tool
    "hinge":  {"class": "tool", "material": "metal", "verb": "hinge",  "base_mult": 1.0, "wear_rate": 0.05, "make_minutes": 45,  "make_effort": 1.2, "composite": False, "demand_driver": "building", "demand_weight": 1.5, "base_demand": 1},
    "spade":  {"class": "tool", "material": "metal", "verb": "dig",    "base_mult": 1.8, "wear_rate": 0.10, "make_minutes": 120, "make_effort": 1.2, "composite": False, "demand_driver": "harvest", "demand_weight": 1.5, "base_demand": 1},
    "rake":   {"class": "tool", "material": "wood",  "verb": "rake",   "base_mult": 1.2, "wear_rate": 0.10, "make_minutes": 60,  "make_effort": 0.7, "composite": False, "demand_driver": "harvest", "demand_weight": 1.5, "base_demand": 1},
    "stool":  {"class": "tool", "material": "wood",  "verb": "sit",    "base_mult": 0.6, "wear_rate": 0.05, "make_minutes": 120, "make_effort": 0.7, "composite": False, "demand_driver": "general", "demand_weight": 0, "base_demand": 1},
    "pick":   {"class": "tool", "material": "metal", "verb": "mine",   "base_mult": 2.0, "wear_rate": 0.15, "make_minutes": 120, "make_effort": 1.3, "composite": True, "demand_driver": "building", "demand_weight": 1, "base_demand": 1},
    "axe":    {"class": "tool", "material": "metal", "verb": "chop",   "base_mult": 2.2, "wear_rate": 0.15, "make_minutes": 150, "make_effort": 1.3, "composite": True, "demand_driver": "building", "demand_weight": 1, "base_demand": 1},
    "scythe": {"class": "tool", "material": "metal", "verb": "reap",   "base_mult": 2.0, "wear_rate": 0.20, "make_minutes": 180, "make_effort": 1.3, "composite": True, "demand_driver": "harvest", "demand_weight": 3, "base_demand": 1},
    # --- composite COMPONENTS (discrete items; a head + a handle assemble into a tool) ---
    "pick_head":   {"class": "component", "part": "head",   "for": "pick", "material": "metal", "verb": "mine", "base_mult": 2.0, "wear_rate": 0.15},
    "pick_handle": {"class": "component", "part": "handle", "for": "pick", "material": "wood",  "verb": "mine", "base_mult": 2.0, "wear_rate": 0.15},
    "barley":  {"class": "material", "bulk": True, "weight": 0.7, "volume": 1.0},
    "oats":    {"class": "material", "bulk": True, "weight": 0.6, "volume": 1.0},
    "rye":     {"class": "material", "bulk": True, "weight": 0.7, "volume": 1.0},
    "hops":    {"class": "material", "bulk": True, "weight": 0.3, "volume": 2.0},
    "cabbage": {"class": "material", "bulk": True, "weight": 1.0, "volume": 2.0},
    "carrot":  {"class": "material", "bulk": True, "weight": 0.5, "volume": 0.5},
    "onion":   {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.5},
    "potato":  {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.6},
    "turnip":  {"class": "material", "bulk": True, "weight": 0.7, "volume": 0.7},
    "bean":    {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.4},
    "pea":     {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "leek":    {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.8},
    "parsnip": {"class": "material", "bulk": True, "weight": 0.5, "volume": 0.6},
    "beet":    {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.6},
    # --- additional local produce and kitchen ingredients ---
    "garlic":   {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "lettuce":  {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.8},
    "cucumber": {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.8},
    "apple":    {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.4, "food": True},
    "pear":     {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.4, "food": True},
    "plum":     {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3, "food": True},
    "berry":    {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2, "food": True},
    "mushroom": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.4, "food": True},
    "lentil":   {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.4},
    "honey":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 0.7, "food": True, "decay": 0.01},
    "cream":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "decay": 0.04},
    "lard":     {"class": "material", "bulk": True, "weight": 1.0, "volume": 0.8, "food": True, "decay": 0.04, "candle_fat": 1.0},
    "vinegar":  {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "yeast":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "sugar":    {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.8},
    "mustard":  {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.4, "food": True},
    "mutton":  {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "leaves_scraps": 0.20},
    "fish":    {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True, "leaves_scraps": 0.30},
    "bacon":   {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "leaves_scraps": 0.10, "decay": 0.03},
    "sausage": {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "decay": 0.04},
    "ham":     {"class": "material", "bulk": True, "weight": 1.2, "volume": 1.0, "food": True, "leaves_scraps": 0.15, "decay": 0.03},
    "pepper":   {"class": "material", "bulk": True, "imported": True, "weight": 0.5, "volume": 0.3},
    "cinnamon": {"class": "material", "bulk": True, "imported": True, "weight": 0.3, "volume": 0.3},
    "ginger":   {"class": "material", "bulk": True, "imported": True, "weight": 0.4, "volume": 0.3},
    "nutmeg":   {"class": "material", "bulk": True, "imported": True, "weight": 0.3, "volume": 0.2},
    "sage":    {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.3},
    "thyme":   {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.3},
    "parsley": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.3},
    "bread":   {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "food": True},
    "pottage": {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "stew":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "roast":   {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "pie":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True},
    "sandwich": {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.5, "food": True},
    "butter":  {"class": "material", "bulk": True, "weight": 1.0, "volume": 0.8, "food": True, "decay": 0.05},
    "cheese":  {"class": "material", "bulk": True, "weight": 1.2, "volume": 1.0, "food": True, "decay": 0.02},
    # --- prepared foods (all remain bulk Stock, so a batch can feed a household) ---
    "gruel":          {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "staple"},
    "porridge":       {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "staple"},
    "oatcake":        {"class": "material", "bulk": True, "weight": 0.5, "volume": 0.8, "food": True, "prepared": True, "food_group": "staple"},
    "flatbread":      {"class": "material", "bulk": True, "weight": 0.5, "volume": 0.9, "food": True, "prepared": True, "food_group": "staple"},
    "pancake":        {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.7, "food": True, "prepared": True, "food_group": "staple"},
    "dumpling":       {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.6, "food": True, "prepared": True, "food_group": "staple"},
    "noodles":        {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.6, "food": True, "prepared": True, "food_group": "staple"},
    "crackers":       {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.6, "food": True, "prepared": True, "food_group": "staple", "decay": 0.04},
    "vegetable_soup": {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "vegetable"},
    "root_soup":      {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "vegetable"},
    "bean_stew":      {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "legume"},
    "lentil_stew":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "legume"},
    "fish_stew":      {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "fish"},
    "fish_pie":       {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True, "prepared": True, "food_group": "fish"},
    "meat_pie":       {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True, "prepared": True, "food_group": "meat"},
    "shepherds_pie":  {"class": "material", "bulk": True, "weight": 0.9, "volume": 1.0, "food": True, "prepared": True, "food_group": "meat"},
    "sausage_stew":   {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "meat"},
    "bacon_eggs":     {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.8, "food": True, "prepared": True, "food_group": "meat"},
    "roast_poultry":  {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "meat"},
    "roast_fish":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.9, "food": True, "prepared": True, "food_group": "fish"},
    "stuffed_cabbage": {"class": "material", "bulk": True, "weight": 0.9, "volume": 1.0, "food": True, "prepared": True, "food_group": "meat"},
    "omelette":       {"class": "material", "bulk": True, "weight": 0.5, "volume": 0.7, "food": True, "prepared": True, "food_group": "dairy"},
    "cheese_pie":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True, "prepared": True, "food_group": "dairy"},
    "buttered_bread": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "food": True, "prepared": True, "food_group": "staple"},
    "fruit_pie":      {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True, "prepared": True, "food_group": "fruit"},
    "cake":           {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.9, "food": True, "prepared": True, "food_group": "sweet"},
    "honey_cake":     {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.9, "food": True, "prepared": True, "food_group": "sweet"},
    "pudding":        {"class": "material", "bulk": True, "weight": 0.7, "volume": 0.8, "food": True, "prepared": True, "food_group": "dairy"},
    "cream_curd":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.8, "food": True, "prepared": True, "food_group": "dairy", "decay": 0.04},
    "yogurt":         {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.8, "food": True, "prepared": True, "food_group": "dairy", "decay": 0.04},
    "pickles":        {"class": "material", "bulk": True, "weight": 0.7, "volume": 0.8, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.01},
    "sauerkraut":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.9, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.01},
    "dried_fruit":    {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.6, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.015},
    "fruit_jam":      {"class": "material", "bulk": True, "weight": 0.7, "volume": 0.7, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.015},
    "salt_fish":      {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.9, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.01},
    "smoked_fish":    {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.9, "food": True, "prepared": True, "food_group": "preserve", "decay": 0.015},
    "cider":          {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "drink", "decay": 0.02},
    "mead":           {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "drink", "decay": 0.015},
    "book":    {"class": "good", "material": "paper", "verb": "read", "base_mult": 1.0, "wear_rate": 0.02, "weight": 1.0, "volume": 0.5},
    "newspaper": {"class": "material", "bulk": True, "material": "paper", "weight": 0.1, "volume": 0.2, "readable": True},
    "printing_press": {"class": "tool", "material": "metal", "verb": "print", "base_mult": 1.0, "wear_rate": 0.01, "make_minutes": 0, "make_effort": 0, "composite": False, "demand_driver": "general", "demand_weight": 0, "base_demand": 0, "imported": True},  # a machine bought in from outside
    # --- trade materials (bulk) ---
    "hide":    {"class": "material", "bulk": True},
    "leather": {"class": "material", "bulk": True},
    "wool":    {"class": "material", "bulk": True},
    "thread":  {"class": "material", "bulk": True},
    "cloth":   {"class": "material", "bulk": True},
    "stave":   {"class": "material", "bulk": True},
    # --- fluids (need a watertight container) ---
    "water":   {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "ale":     {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "drink", "decay": 0.02},
    "oil":     {"class": "material", "bulk": True, "fluid": True, "weight": 0.9, "volume": 1.0},
    "milk":    {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True},
    # --- animal products + feed (bulk) ---
    "pork":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "leaves_scraps": 0.20},
    "beef":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "leaves_scraps": 0.20},
    "poultry": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "food": True, "leaves_scraps": 0.30},
    "eggs":    {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2, "food": True},
    "hay":     {"class": "material", "bulk": True, "weight": 0.3, "volume": 3.0},
    "grass":   {"class": "material", "bulk": True, "weight": 0.2, "volume": 2.0},
    # generic kitchen scraps (peelings, crusts, mixed leavings): animal feed, not people food.
    # Meat/fish leavings are separate "<kind>_scraps" items, minted below from `leaves_scraps`.
    "scraps":  {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "scraps": True, "compostable": 1.0},
    "rag":     {"class": "material", "bulk": True, "weight": 0.3, "volume": 1.0},
    "soot":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.5},
    # --- imported goods (from OUTSIDE bigville -- acquired by trade, not made locally) ---
    "ink":    {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.5},
    "paper":  {"class": "material", "bulk": True, "imported": True, "weight": 0.2, "volume": 0.5},
    "dye":    {"class": "material", "bulk": True, "imported": True, "dyestuff": 1.0, "weight": 1.0, "volume": 0.5},
    "madder": {"class": "material", "bulk": True, "imported": True, "dyestuff": 1.0, "colour": "red",    "weight": 1.0, "volume": 0.5},
    "woad":   {"class": "material", "bulk": True, "imported": True, "dyestuff": 1.0, "colour": "blue",   "weight": 1.0, "volume": 0.5},
    "weld":   {"class": "material", "bulk": True, "imported": True, "dyestuff": 1.0, "colour": "yellow", "weight": 1.0, "volume": 0.5},
    "silk":   {"class": "material", "bulk": True, "imported": True, "weight": 0.5, "volume": 0.3},
    "velvet": {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.5},
    "fur":    {"class": "material", "bulk": True, "imported": True, "weight": 2.0, "volume": 1.0},
    "linen":  {"class": "material", "bulk": True, "imported": True, "weight": 0.8, "volume": 0.4},
    "salt":   {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.5},
    "coloured_cloth": {"class": "good", "material": "cloth", "verb": "clothe", "base_mult": 1.0, "wear_rate": 0.10},
    # --- goods (discrete; class != material -> made as discrete items with quality + wear) ---
    "shoes":  {"class": "good", "material": "leather", "verb": "walk",   "base_mult": 1.0, "wear_rate": 0.20},
    "boots":  {"class": "good", "material": "leather", "verb": "walk",   "base_mult": 1.4, "wear_rate": 0.15, "garment": True, "warmth": 1.0, "rain": 1.0, "station": "ordinary", "finery": 2.0},
    "coat":   {"class": "good", "material": "cloth",   "verb": "warm",   "base_mult": 1.2, "wear_rate": 0.10, "garment": True, "warmth": 3.0, "rain": 1.0, "station": "ordinary", "finery": 2.0},
    "shirt":  {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 0.8, "wear_rate": 0.15, "garment": True, "warmth": 1.0, "rain": 0.0, "station": "ordinary", "finery": 1.0},
    "cloak":    {"class": "good", "material": "cloth",   "verb": "warm",   "base_mult": 1.0, "wear_rate": 0.10, "garment": True, "warmth": 2.0, "rain": 3.0, "station": "ordinary", "finery": 2.0},
    "hat":      {"class": "good", "material": "cloth",   "verb": "cover",  "base_mult": 0.6, "wear_rate": 0.10, "garment": True, "warmth": 1.0, "rain": 2.0, "station": "ordinary", "finery": 1.0},
    "breeches": {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 0.8, "wear_rate": 0.12, "garment": True, "warmth": 1.0, "rain": 0.0, "station": "ordinary", "finery": 1.0},
    "dress":    {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 1.0, "wear_rate": 0.12, "garment": True, "warmth": 2.0, "rain": 0.0, "station": "ordinary", "finery": 2.0},
    "smock":    {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 0.6, "wear_rate": 0.18, "garment": True, "warmth": 1.0, "rain": 0.0, "station": "plain", "finery": 0.0},
    "tunic":    {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 0.7, "wear_rate": 0.15, "garment": True, "warmth": 1.0, "rain": 0.0, "station": "plain", "finery": 1.0},
    "cap":      {"class": "good", "material": "cloth",   "verb": "cover",  "base_mult": 0.5, "wear_rate": 0.12, "garment": True, "warmth": 1.0, "rain": 1.0, "station": "plain", "finery": 0.0},
    "apron":    {"class": "good", "material": "cloth",   "verb": "clothe", "base_mult": 0.5, "wear_rate": 0.20, "garment": True, "warmth": 0.0, "rain": 0.0, "station": "plain", "finery": 0.0},
    "clogs":    {"class": "good", "material": "wood",    "verb": "walk",   "base_mult": 0.8, "wear_rate": 0.14, "garment": True, "warmth": 0.0, "rain": 1.0, "station": "plain", "finery": 0.0},
    "gown":     {"class": "good", "material": "silk",    "verb": "clothe", "base_mult": 1.6, "wear_rate": 0.06, "garment": True, "warmth": 2.0, "rain": 0.0, "station": "fine", "finery": 5.0},
    "doublet":  {"class": "good", "material": "velvet",  "verb": "clothe", "base_mult": 1.5, "wear_rate": 0.07, "garment": True, "warmth": 2.0, "rain": 0.0, "station": "fine", "finery": 4.0},
    "fur_cloak":{"class": "good", "material": "fur",     "verb": "warm",   "base_mult": 1.6, "wear_rate": 0.05, "garment": True, "warmth": 4.0, "rain": 2.0, "station": "fine", "finery": 5.0},
    "silk_shirt":{"class":"good", "material": "silk",    "verb": "clothe", "base_mult": 1.4, "wear_rate": 0.08, "garment": True, "warmth": 1.0, "rain": 0.0, "station": "fine", "finery": 3.0},
    "fine_hat": {"class": "good", "material": "velvet",  "verb": "cover",  "base_mult": 1.3, "wear_rate": 0.07, "garment": True, "warmth": 1.0, "rain": 2.0, "station": "fine", "finery": 3.0},
    "barrel": {"class": "good", "material": "wood",    "verb": "store",  "base_mult": 1.4, "wear_rate": 0.05, "container": True, "capacity": 40.0, "lockable": False, "watertight": True},
    # --- furniture (discrete, larger) ---
    "chair":  {"class": "furniture", "material": "wood", "verb": "seat", "base_mult": 1.0, "wear_rate": 0.05},
    "table":  {"class": "furniture", "material": "wood", "verb": "work", "base_mult": 1.2, "wear_rate": 0.03},
    "bed":    {"class": "furniture", "material": "wood", "verb": "rest", "base_mult": 1.5, "wear_rate": 0.03},
    "chest":  {"class": "furniture", "material": "wood", "verb": "store","base_mult": 1.0, "wear_rate": 0.03, "container": True, "capacity": 20.0, "lockable": True, "watertight": False},
    # --- larger tools (discrete) ---
    "plough": {"class": "tool", "material": "metal", "verb": "till",  "base_mult": 2.4, "wear_rate": 0.15},
    "wheel":  {"class": "component", "part": "wheel", "for": "cart", "material": "wood", "verb": "roll", "base_mult": 1.0, "wear_rate": 0.10},
    "cart":   {"class": "tool", "material": "wood",  "verb": "haul",  "base_mult": 2.0, "wear_rate": 0.08, "container": True, "capacity": 80.0,  "max_load": 50.0,  "watertight": False},
    "wagon":  {"class": "tool", "material": "wood",  "verb": "haul",  "base_mult": 2.4, "wear_rate": 0.08, "container": True, "capacity": 200.0, "max_load": 100.0, "watertight": False},
    "loom":   {"class": "tool", "material": "wood",  "verb": "weave", "base_mult": 1.6, "wear_rate": 0.05},
    "bucket": {"class": "good", "material": "wood", "verb": "carry", "base_mult": 1.0, "wear_rate": 0.05, "container": True, "capacity": 8.0, "lockable": False, "watertight": True},
    # Tableware is reusable equipment. Consumption names the abstract vessel capability below, while
    # these variants can also be made, owned, and pressed into service via use_as_store().
    "wooden_mug":  {"class": "good", "material": "wood",  "verb": "drink", "base_mult": 0.8, "wear_rate": 0.05, "container": True, "capacity": 1.0, "lockable": False, "watertight": True},
    "metal_mug":   {"class": "good", "material": "metal", "verb": "drink", "base_mult": 1.1, "wear_rate": 0.03, "container": True, "capacity": 1.0, "lockable": False, "watertight": True},
    "wooden_bowl": {"class": "good", "material": "wood",  "verb": "serve", "base_mult": 0.8, "wear_rate": 0.05, "container": True, "capacity": 5.0, "lockable": False, "watertight": True},
    "metal_bowl":  {"class": "good", "material": "metal", "verb": "serve", "base_mult": 1.1, "wear_rate": 0.03, "container": True, "capacity": 5.0, "lockable": False, "watertight": True},
    "wooden_ladle":          {"class": "good", "material": "wood",  "verb": "serve", "base_mult": 0.8, "wear_rate": 0.05, "utensil": "ladle"},
    "metal_ladle":            {"class": "good", "material": "metal", "verb": "serve", "base_mult": 1.1, "wear_rate": 0.03, "utensil": "ladle"},
    "wooden_serving_spoon":   {"class": "good", "material": "wood",  "verb": "serve", "base_mult": 0.8, "wear_rate": 0.05, "utensil": "serving_spoon"},
    "metal_serving_spoon":    {"class": "good", "material": "metal", "verb": "serve", "base_mult": 1.1, "wear_rate": 0.03, "utensil": "serving_spoon"},
    "wooden_dipper":          {"class": "good", "material": "wood",  "verb": "serve", "base_mult": 0.8, "wear_rate": 0.05, "utensil": "dipper"},
    # --- extracted resources and the simple shop chains (RESOURCE_DEPOSITS / SHOP_CHAINS below) ---
    "stone":      {"class": "material", "bulk": True, "material": "stone", "weight": 2.5, "volume": 1.0},
    "lumber":     {"class": "material", "bulk": True, "material": "wood",  "weight": 1.5, "volume": 2.0},  # felled wood from a deposit
    "blocks":     {"class": "material", "bulk": True, "material": "stone", "weight": 2.5, "volume": 1.0},  # dressed stone (mason)
    "furniture":  {"class": "material", "bulk": True, "material": "wood",  "weight": 2.0, "volume": 3.0},  # generic carpenter output
    "fish_ready": {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0},                      # fishmonger's dressed fish
    # --- trade tools and workshop equipment named by RECIPES / TRADES. The world provides one
    # instance of each recipe tool at founding; these rows give them physical and price data.
    "hammer":       {"class": "tool", "material": "metal", "verb": "strike", "base_mult": 1.0, "wear_rate": 0.02, "weight": 1.0, "volume": 0.3},
    "saw":          {"class": "tool", "material": "metal", "verb": "saw",    "base_mult": 1.0, "wear_rate": 0.03, "weight": 1.0, "volume": 0.5},
    "adze":         {"class": "tool", "material": "metal", "verb": "shape",  "base_mult": 1.0, "wear_rate": 0.03, "weight": 1.0, "volume": 0.4},
    "awl":          {"class": "tool", "material": "metal", "verb": "pierce", "base_mult": 1.0, "wear_rate": 0.02, "weight": 0.1, "volume": 0.1},
    "needle":       {"class": "tool", "material": "metal", "verb": "sew",    "base_mult": 1.0, "wear_rate": 0.02, "weight": 0.05, "volume": 0.05},
    "cleaver":      {"class": "tool", "material": "metal", "verb": "cleave", "base_mult": 1.0, "wear_rate": 0.03, "weight": 0.8, "volume": 0.3},
    "quill":        {"class": "tool", "material": "feather", "verb": "write", "base_mult": 1.0, "wear_rate": 0.05, "weight": 0.02, "volume": 0.05},
    "net":          {"class": "tool", "material": "cloth", "verb": "fish",   "base_mult": 1.0, "wear_rate": 0.05, "weight": 2.0, "volume": 2.0},
    "board":        {"class": "tool", "material": "wood",  "verb": "knead",  "base_mult": 1.0, "wear_rate": 0.02, "weight": 1.0, "volume": 1.0},
    "drying_rack":  {"class": "tool", "material": "wood",  "verb": "dry",    "base_mult": 1.0, "wear_rate": 0.02, "weight": 3.0, "volume": 4.0},
    "smoking_rack": {"class": "tool", "material": "wood",  "verb": "smoke",  "base_mult": 1.0, "wear_rate": 0.03, "weight": 3.0, "volume": 4.0},
    "churn":        {"class": "tool", "material": "wood",  "verb": "churn",  "base_mult": 1.0, "wear_rate": 0.02, "weight": 4.0, "volume": 3.0},
    "press":        {"class": "tool", "material": "wood",  "verb": "press",  "base_mult": 1.0, "wear_rate": 0.02, "weight": 10.0, "volume": 6.0},
    "mash_tun":     {"class": "tool", "material": "wood",  "verb": "mash",   "base_mult": 1.0, "wear_rate": 0.02, "weight": 15.0, "volume": 20.0},
    "dye_vat":      {"class": "tool", "material": "wood",  "verb": "dye",    "base_mult": 1.0, "wear_rate": 0.02, "weight": 15.0, "volume": 20.0},
    # cooking equipment (PREPARATION_EQUIPMENT); the pot's capacity matches CONTAINERS["pot"]
    "pot":     {"class": "tool", "material": "metal", "verb": "boil",  "base_mult": 1.0, "wear_rate": 0.02, "weight": 2.0, "volume": 8.0,
                "container": True, "capacity": 8.0, "lockable": False, "watertight": True},
    "pan":     {"class": "tool", "material": "metal", "verb": "fry",   "base_mult": 1.0, "wear_rate": 0.02, "weight": 1.5, "volume": 1.0},
    "griddle": {"class": "tool", "material": "metal", "verb": "fry",   "base_mult": 1.0, "wear_rate": 0.02, "weight": 3.0, "volume": 1.5},
    "spit":    {"class": "tool", "material": "metal", "verb": "roast", "base_mult": 1.0, "wear_rate": 0.02, "weight": 2.0, "volume": 1.5},
    "oven":    {"class": "furniture", "material": "stone", "verb": "bake", "base_mult": 1.0, "wear_rate": 0.01, "weight": 200.0, "volume": 20.0},
    # --- crops and their seed added to close the brewing, linen, oil, and condiment chains ---
    "hops_seed":    {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "linseed":      {"class": "material", "bulk": True, "seed": True, "weight": 0.2, "volume": 0.2},  # flax seed: sown, or pressed for oil
    "mustard_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.2, "volume": 0.2},  # sown, or ground into mustard
    "flax":         {"class": "material", "bulk": True, "weight": 0.4, "volume": 2.0},
    "malt":         {"class": "material", "bulk": True, "weight": 0.6, "volume": 1.0},   # sprouted, kilned barley
    "feather":      {"class": "material", "bulk": True, "weight": 0.02, "volume": 0.2},
    "sapling":      {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0},   # lifted from the woodlot; planted as hedge
    # --- prepared foods and goods that use otherwise-idle ingredients ---
    "beer":       {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "drink", "decay": 0.015},
    "salad":      {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.8, "food": True, "prepared": True, "food_group": "vegetable", "decay": 0.3},
    "pea_soup":   {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "prepared": True, "food_group": "legume"},
    "spice_cake": {"class": "material", "bulk": True, "weight": 0.6, "volume": 0.9, "food": True, "prepared": True, "food_group": "sweet", "decay": 0.02},
    "candle":     {"class": "good", "material": "wax", "verb": "light", "base_mult": 1.0, "wear_rate": 0.25, "weight": 0.1, "volume": 0.1},
}

# ---------------------------------------------------------------- SCRAPS (a modifier)
# Scraps are a MODIFIER on a food, not one shared pile: eating a unit of a food with
# `leaves_scraps` leaves that fraction behind as "<food>_scraps" (pork -> pork_scraps). Each scrap
# item derives its values from its source -- lighter, cheaper, and quicker to spoil -- and is still
# food, so it can be fed to animals that eat scraps (pigs, dogs) or eaten by people who cannot
# afford better. Generic "scraps" (kitchen leavings) remains animal feed only.
SCRAP_WEIGHT_FACTOR = 0.5      # scraps are bone, rind, skin: half the weight per unit of the cut
SCRAP_SCARCITY_FACTOR = 0.15   # and worth a small fraction of it
SCRAP_DECAY = 0.35             # scraps spoil faster than any whole food (perishable class is 0.25)


def scrap_kind(kind):
    """The scrap item a food leaves, or None if eating it leaves nothing."""
    return f"{kind}_scraps" if ITEMS.get(kind, {}).get("leaves_scraps") else None


for _kind, _spec in list(ITEMS.items()):
    if _spec.get("leaves_scraps"):
        ITEMS[f"{_kind}_scraps"] = {
            "class": "material", "bulk": True, "food": True, "scraps": True, "scraps_of": _kind,
            "food_group": "scraps", "fare": "poor", "compostable": 1.0,
            "weight": round(float(_spec.get("weight", 1.0)) * SCRAP_WEIGHT_FACTOR, 3),
            "volume": float(_spec.get("volume", 1.0)), "decay": SCRAP_DECAY,
        }


def feed_kinds(eats):
    """Every stock kind an animal with diet `eats` will accept, in the order it eats them.

    A diet of "scraps" accepts generic kitchen scraps first, then any food's scraps."""
    if eats != "scraps":
        return (eats,)
    return ("scraps",) + tuple(sorted(k for k, s in ITEMS.items() if s.get("scraps_of")))


# ---------------------------------------------------------------- TYPED INPUT SLOTS
# A recipe input normally names one item kind (`["charcoal", 1]` -- a smith needs charcoal and
# nothing else will do). An input may instead name a TYPE from this table (`["fuel", 1]`): the slot
# accepts any item carrying the type's `tag`, and the quantity is measured in the tag's units. A
# member with tag value v supplies v units per item, so 1 fuel is 1 wood, or 1/3 charcoal, or ~3.3
# straw. A slot may be filled from several members; the cheapest per unit (by reference value) burns
# first, so a cook reaches for straw and dung before the smith's charcoal. Type names must not
# collide with item names. `byproducts` are left per unit of the slot consumed (burning leaves ash).
INPUT_TYPES = {
    "fuel":        {"tag": "fuel",        "measure": "heat",
                    "byproducts": {"ash": 0.2, "soot": 0.05}},
    "fertiliser":  {"tag": "nitrogen",    "measure": "nitrogen"},
    "compostable": {"tag": "compostable", "measure": "units"},
    "dyestuff":    {"tag": "dyestuff",    "measure": "units"},
    "candle_fat":  {"tag": "candle_fat",  "measure": "units"},
}


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

# ---------------------------------------------------------------- CONTAINERS
# vessels with a capacity; some lockable (a safe is a lockable container). A container is a peer
# class of a pile -- a physical, located, claimable world-fact that holds contents.
CONTAINERS = {
    "sack":   {"capacity": 10.0,  "lockable": False},
    "bucket": {"capacity": 8.0,   "lockable": False},
    "barrel": {"capacity": 40.0,  "lockable": False},
    "bin":    {"capacity": 100.0, "lockable": False},
    "chest":  {"capacity": 20.0,  "lockable": True},
    "safe":   {"capacity": 200.0, "lockable": True},
    "larder":      {"capacity": 100.0, "lockable": False, "decay_factor": 0.3,
                    "storage_class": "cool_food", "mismatch_decay_factor": 2.0,
                    "preferred_contents": ["bread", "milk", "butter", "cheese", "cream", "fish",
                                           "pork", "beef", "mutton", "poultry", "bacon", "ham", "sausage"]},
    # Long-term stores are deliberately distinct from ordinary containers. Their decay factors are
    # multipliers on the normal decay rate, so a dry, well-built granary preserves a harvest across
    # seasons without making food immortal. `preferred_contents` is an affinity, not a whitelist:
    # people may put other things in the building, but unsuitable perishables keep worse there.
    "granary":     {"capacity": 500.0, "lockable": True, "decay_factor": 0.08,
                    "storage_class": "dry_grain", "mismatch_decay_factor": 8.0,
                    "preferred_contents": ["grain", "barley", "oats", "rye", "flour", "bean", "pea", "lentil"]},
    "root_cellar": {"capacity": 250.0, "lockable": False, "decay_factor": 0.15,
                    "storage_class": "root_crop", "mismatch_decay_factor": 4.0,
                    "preferred_contents": ["cabbage", "carrot", "onion", "potato", "turnip", "leek", "parsnip", "beet", "garlic"]},
    "pantry":      {"capacity": 150.0, "lockable": False, "decay_factor": 0.25,
                    "storage_class": "prepared_food", "mismatch_decay_factor": 3.0,
                    "preferred_contents": ["bread", "crackers", "bacon", "ham", "cheese", "butter", "pickles", "sauerkraut", "dried_fruit", "fruit_jam", "salt_fish", "smoked_fish"]},
    # Abstract vessel capabilities used when serving. The wooden/metal item variants above are the
    # physical vessels; these entries let consumption accept either material.
    "mug":     {"capacity": 1.0, "lockable": False, "watertight": True, "alternatives": ["wooden_mug", "metal_mug"]},
    "bowl":    {"capacity": 5.0, "lockable": False, "watertight": True, "alternatives": ["wooden_bowl", "metal_bowl"]},
    "pot":     {"capacity": 8.0, "lockable": False, "watertight": True},
}

# ---------------------------------------------------------------- FOOD SERVICE
# Cooking creates a Stock pile. Consumption is a separate act: a person needs a serving vessel whose
# capacity can hold one portion, plus an appropriate utensil (or a bowl used as the scoop). A larger
# bowl/pot/barrel is a source, not a substitute for the smaller vessel the eater drinks/eats from.
SERVING_UTENSILS = {
    "ladle":          {"alternatives": ["wooden_ladle", "metal_ladle"], "for": ["soup"]},
    "serving_spoon":  {"alternatives": ["wooden_serving_spoon", "metal_serving_spoon"], "for": ["soup", "pudding"]},
    "dipper":         {"alternatives": ["wooden_dipper"], "for": ["drink"]},
}

SERVING_EQUIPMENT = (
    "wooden_mug", "wooden_bowl", "wooden_ladle", "wooden_serving_spoon", "wooden_dipper",
)

FOOD_SERVICE = {
    "soup": {"container": "bowl", "portion_volume": 1.0,
             "utensils": ["ladle", "serving_spoon", "bowl"],
             "sources": ["pot", "bowl", "barrel"]},
    "drink": {"container": "mug", "portion_volume": 1.0,
               "utensils": ["dipper", "mug"],
               "sources": ["barrel", "bowl", "pot"]},
}

# The made foods that are liquid/semi-liquid at the point of eating. Other foods can be eaten from
# the stock directly by the existing resident-eating loop, while these require the service affordance.
SOUP_FOODS = {"pottage", "stew", "gruel", "porridge", "vegetable_soup", "root_soup", "bean_stew",
              "lentil_stew", "fish_stew", "sausage_stew", "pudding"}
DRINK_FOODS = {"ale", "cider", "mead"}

# ---------------------------------------------------------------- PREPARATION
# A dish is not intrinsically an oven product or a pot product. It needs a heat source and a way to
# contain/support the food; the method affects the descriptive style (and can later affect taste or
# quality) without making one appliance the hidden universal requirement.
PREPARATION_REQUIREMENTS = ("heat", "containment")
PREPARATION_EQUIPMENT = {
    "oven":      {"provides": ["heat", "containment"], "prefix": "oven_baked",   "modifier": "even_heat"},
    "pot":       {"provides": ["containment"],          "prefix": "pot_cooked",    "modifier": "moist"},
    "pan":       {"provides": ["containment"],          "prefix": "pan_cooked",    "modifier": "browned"},
    "griddle":   {"provides": ["containment"],          "prefix": "griddle_cooked", "modifier": "browned"},
    "spit":      {"provides": ["containment"],          "prefix": "spit_roasted",   "modifier": "fire_roasted"},
    "hot_coals": {"provides": ["heat"],                 "prefix": "coal_cooked",    "modifier": "smoky"},
    "hearth":    {"provides": ["heat"],                 "prefix": "hearth_cooked",  "modifier": "smoky"},
}
PREPARATION_METHODS = {
    "oven_baked":    {"equipment": ["oven"],                 "prefix": "oven_baked",    "modifier": "even_heat"},
    "hearth_pot":    {"equipment": ["pot", "hot_coals"],    "prefix": "hearth_cooked",  "modifier": "smoky"},
    "coal_pan":      {"equipment": ["pan", "hot_coals"],    "prefix": "pan_cooked",     "modifier": "browned"},
    "coal_griddle":  {"equipment": ["griddle", "hot_coals"], "prefix": "griddle_cooked", "modifier": "browned"},
    "coal_spit":     {"equipment": ["spit", "hot_coals"],   "prefix": "spit_roasted",   "modifier": "fire_roasted"},
}
PREPARATION_METHODS_BY_HINT = {
    "oven": ["oven_baked", "hearth_pot", "coal_pan"],
    "pot": ["hearth_pot", "oven_baked"],
    "griddle": ["coal_griddle", "coal_pan"],
    "spit": ["coal_spit", "oven_baked"],
    "mash_tun": ["hearth_pot"],
}

# These are the recipes whose food is cooked rather than assembled, cured, churned, or merely
# preserved. They get the same abstract requirement, while `method` remains an available description.
HEATED_FOOD_RECIPES = frozenset({
    "bake_bread", "make_pottage", "make_stew", "roast_meat", "make_pie",
    "make_gruel", "make_porridge", "bake_oatcakes", "bake_flatbread", "make_pancakes",
    "make_dumplings", "make_noodles", "bake_crackers", "make_vegetable_soup", "make_root_soup",
    "make_bean_stew", "make_lentil_stew", "make_fish_stew", "make_sausage_stew", "make_bacon_eggs",
    "roast_poultry", "roast_fish", "stuffed_cabbage", "make_omelette", "make_fish_pie",
    "make_meat_pie", "make_shepherds_pie", "make_cheese_pie", "bake_cake", "bake_honey_cake",
    "make_pudding", "brew_ale", "brew_cider", "brew_mead", "bake_bread_at_home",
    "make_fruit_pie", "make_yogurt", "make_fruit_jam", "make_pea_soup", "bake_spice_cake", "brew_beer",
    "render_lard",
})

# Every heated dish burns fuel: the loop below adds a `["fuel", n]` typed input to each recipe in
# HEATED_FOOD_RECIPES (1 unit of heat unless listed here). Non-food heat work (dyeing, smoking,
# malting, candle-making) names its fuel input directly in the recipe row.
FUEL_PER_BATCH = {"brew_ale": 2, "brew_beer": 2, "brew_cider": 2, "brew_mead": 2,
                  "bake_bread": 6, "bake_bread_at_home": 1}   # 0.1 heat/loaf in an oven, 0.33 at home

# ---------------------------------------------------------------- RECIPES
# how things are made / combined: inputs -> output, with difficulty and make-time. `requires` is the
# trade/role. `fallback: True` marks a deliberately costlier way to make something (home baking) that
# people use when the efficient maker is missing. `open: True` marks household work ANYONE may do -- no trade needed -- provided they are
# strong and skilled enough (RECIPE_EXERTION, MIN_SKILL) and hold the recipe's tools themselves (a
# trade recipe uses its workshop's kit instead). Everyone else buys the result, or is given it. `byproducts` ({kind: qty}) are left per batch alongside the output (milling leaves bran). Inputs and tools are deliberately variable-length. Serving vessels and utensils belong
# to FOOD_SERVICE below: they are needed when food is consumed, not when the batch is cooked.
RECIPES = [
    {"name": "saw_planks",    "requires": "sawyer",     "in": [["lumber", 1]],               "out": ["timber", 2],   "difficulty": 0.8, "time_minutes": 20},
    {"name": "burn_charcoal", "requires": "collier",    "in": [["wood", 4]],                 "out": ["charcoal", 1], "difficulty": 2.0, "time_minutes": 60},
    {"name": "smelt_iron",    "requires": "smith",      "in": [["ore", 2], ["charcoal", 1]], "out": ["iron", 1],     "difficulty": 3.0, "time_minutes": 90},
    {"name": "forge_nails",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]],"out": ["nails", 5],    "difficulty": 1.5, "time_minutes": 10, "tools": ["hammer"]},
    {"name": "forge_knife",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]],"out": ["knife", 1],    "difficulty": 2.0, "time_minutes": 90, "tools": ["hammer"]},
    {"name": "carve_rake",    "requires": "woodworker", "in": [["timber", 1]],               "out": ["rake", 1],     "difficulty": 0.7, "time_minutes": 60},
    {"name": "grind_flour",   "requires": "miller",     "in": [["grain", 30]],               "out": ["flour", 20],   "difficulty": 1.0, "time_minutes": 45, "byproducts": {"scraps": 10}},  # a water-mill run; bran
    {"name": "forge_pick_head",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]],"out": ["pick_head", 1],  "difficulty": 1.3, "time_minutes": 120, "tools": ["hammer"]},
    {"name": "carve_pick_handle", "requires": "woodworker", "in": [["timber", 1]],               "out": ["pick_handle", 1],"difficulty": 0.7, "time_minutes": 60},
    # ASSEMBLE = an action on two ITEM inputs (a head + a handle) using a hammer -- not special
    {"name": "assemble_pick", "requires": "smith", "in": [["pick_head", 1], ["pick_handle", 1]], "out": ["pick", 1], "difficulty": 0.5, "time_minutes": 15, "tools": ["hammer"]},
    {"name": "forge_scythe",  "requires": "smith", "in": [["iron", 2], ["charcoal", 1]], "out": ["scythe", 1], "difficulty": 2.5, "time_minutes": 180, "tools": ["hammer"]},
    {"name": "rive_staves",  "requires": "cooper",     "in": [["timber", 1]],               "out": ["stave", 3],   "difficulty": 1.0, "time_minutes": 30,  "tools": ["adze"]},
    {"name": "raise_barrel", "requires": "cooper",     "in": [["stave", 6]],                "out": ["barrel", 1],  "difficulty": 2.0, "time_minutes": 120, "tools": ["adze"]},
    {"name": "tan_hide",     "requires": "tanner",     "in": [["hide", 2]],                 "out": ["leather", 1], "difficulty": 1.5, "time_minutes": 240},
    {"name": "make_shoes",   "requires": "cobbler",    "in": [["leather", 1]],              "out": ["shoes", 1],   "difficulty": 1.5, "time_minutes": 120, "tools": ["awl"]},
    {"name": "weave_cloth",  "requires": "weaver",     "in": [["wool", 3]],                 "out": ["cloth", 1],   "difficulty": 1.5, "time_minutes": 180, "tools": ["loom"]},
    {"name": "sew_coat",     "requires": "tailor",     "in": [["cloth", 2]],                "out": ["coat", 1],    "difficulty": 1.5, "time_minutes": 150, "tools": ["needle"]},
    {"name": "sew_cloak",    "requires": "tailor",     "in": [["cloth", 3]],                "out": ["cloak", 1],   "difficulty": 1.5, "time_minutes": 150, "tools": ["needle"]},
    {"name": "sew_hat",      "requires": "tailor",     "in": [["cloth", 1]],                "out": ["hat", 1],     "difficulty": 1.0, "time_minutes": 60,  "tools": ["needle"]},
    {"name": "sew_breeches", "requires": "tailor",     "in": [["cloth", 2]],                "out": ["breeches", 1],"difficulty": 1.3, "time_minutes": 120, "tools": ["needle"]},
    {"name": "sew_dress",    "requires": "tailor",     "in": [["cloth", 3]],                "out": ["dress", 1],   "difficulty": 1.8, "time_minutes": 200, "tools": ["needle"]},
    {"name": "sew_smock",    "requires": "tailor",     "in": [["cloth", 1]],                "out": ["smock", 1],   "difficulty": 0.6, "time_minutes": 40,  "tools": ["needle"]},
    {"name": "sew_tunic",    "requires": "tailor",     "in": [["cloth", 2]],                "out": ["tunic", 1],   "difficulty": 0.9, "time_minutes": 80,  "tools": ["needle"]},
    {"name": "sew_cap",      "requires": "tailor",     "in": [["cloth", 1]],                "out": ["cap", 1],     "difficulty": 0.5, "time_minutes": 30,  "tools": ["needle"]},
    {"name": "sew_apron",    "requires": "tailor",     "in": [["cloth", 1]],                "out": ["apron", 1],   "difficulty": 0.5, "time_minutes": 30,  "tools": ["needle"]},
    {"name": "make_clogs",   "requires": "cobbler",    "in": [["wood", 2]],                 "out": ["clogs", 1],   "difficulty": 0.8, "time_minutes": 60,  "tools": ["awl"]},
    {"name": "sew_gown",     "requires": "tailor",     "in": [["silk", 3]],                 "out": ["gown", 1],    "difficulty": 2.8, "time_minutes": 360, "tools": ["needle"], "common": False},
    {"name": "sew_doublet",  "requires": "tailor",     "in": [["velvet", 2]],               "out": ["doublet", 1], "difficulty": 2.5, "time_minutes": 300, "tools": ["needle"], "common": False},
    {"name": "sew_fur_cloak","requires": "tailor",     "in": [["fur", 3]],                  "out": ["fur_cloak", 1],"difficulty": 2.2,"time_minutes": 260, "tools": ["needle"], "common": False},
    {"name": "sew_silk_shirt","requires": "tailor",    "in": [["silk", 2]],                 "out": ["silk_shirt", 1],"difficulty":2.3,"time_minutes": 240, "tools": ["needle"], "common": False},
    {"name": "sew_fine_hat", "requires": "tailor",     "in": [["velvet", 1]],               "out": ["fine_hat", 1],"difficulty": 2.0, "time_minutes": 180, "tools": ["needle"], "common": False},
    {"name": "make_chair",   "requires": "woodworker", "in": [["timber", 2]],               "out": ["chair", 1],   "difficulty": 1.0, "time_minutes": 90,  "tools": ["saw"]},
    {"name": "make_table",   "requires": "woodworker", "in": [["timber", 4]],               "out": ["table", 1],   "difficulty": 1.3, "time_minutes": 150, "tools": ["saw"]},
    {"name": "make_bed",     "requires": "woodworker", "in": [["timber", 5]],               "out": ["bed", 1],     "difficulty": 1.5, "time_minutes": 240, "tools": ["saw"]},
    {"name": "make_chest",   "requires": "woodworker", "in": [["timber", 3]],               "out": ["chest", 1],   "difficulty": 1.3, "time_minutes": 120, "tools": ["saw"]},
    {"name": "forge_plough", "requires": "smith",      "in": [["iron", 3], ["charcoal", 2]],"out": ["plough", 1],  "difficulty": 3.0, "time_minutes": 240, "tools": ["hammer"]},
    {"name": "make_wheel",   "requires": "woodworker", "in": [["timber", 1]],               "out": ["wheel", 1],   "difficulty": 1.0, "time_minutes": 90,  "tools": ["saw"]},
    {"name": "make_cart",    "requires": "woodworker", "in": [["timber", 6], ["wheel", 2]],  "out": ["cart", 1],    "difficulty": 2.5, "time_minutes": 300, "tools": ["saw"]},
    {"name": "make_wagon",   "requires": "woodworker", "in": [["timber", 10], ["wheel", 4]], "out": ["wagon", 1],   "difficulty": 3.5, "time_minutes": 480, "tools": ["saw"]},
    {"name": "make_loom",    "requires": "woodworker", "in": [["timber", 4]],               "out": ["loom", 1],    "difficulty": 2.0, "time_minutes": 180, "tools": ["saw"]},
    {"name": "carve_wooden_mug",  "requires": "woodworker", "in": [["timber", 1]],               "out": ["wooden_mug", 1],  "difficulty": 0.8, "time_minutes": 45,  "tools": ["knife"]},
    {"name": "forge_metal_mug",    "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]], "out": ["metal_mug", 1],    "difficulty": 1.4, "time_minutes": 75,  "tools": ["hammer"]},
    {"name": "carve_wooden_bowl", "requires": "woodworker", "in": [["timber", 1]],               "out": ["wooden_bowl", 1], "difficulty": 0.9, "time_minutes": 60,  "tools": ["knife"]},
    {"name": "forge_metal_bowl",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]], "out": ["metal_bowl", 1],   "difficulty": 1.6, "time_minutes": 90,  "tools": ["hammer"]},
    {"name": "carve_wooden_ladle",        "requires": "woodworker", "in": [["timber", 1]],               "out": ["wooden_ladle", 1],        "difficulty": 0.7, "time_minutes": 45, "tools": ["knife"]},
    {"name": "forge_metal_ladle",          "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]], "out": ["metal_ladle", 1],          "difficulty": 1.3, "time_minutes": 60, "tools": ["hammer"]},
    {"name": "carve_wooden_serving_spoon", "requires": "woodworker", "in": [["timber", 1]],               "out": ["wooden_serving_spoon", 1], "difficulty": 0.6, "time_minutes": 35, "tools": ["knife"]},
    {"name": "forge_metal_serving_spoon",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]], "out": ["metal_serving_spoon", 1],   "difficulty": 1.2, "time_minutes": 50, "tools": ["hammer"]},
    {"name": "carve_wooden_dipper",         "requires": "woodworker", "in": [["timber", 1]],               "out": ["wooden_dipper", 1],         "difficulty": 0.7, "time_minutes": 40, "tools": ["knife"]},
    {"name": "brew_ale",     "requires": "brewer",     "in": [["grain", 3], ["water", 4]],  "out": ["ale", 5],     "difficulty": 2.0, "time_minutes": 480, "tools": ["mash_tun"]},
    {"name": "dye_cloth",    "requires": "dyer",       "in": [["cloth", 1], ["dyestuff", 1], ["fuel", 1]],    "out": ["coloured_cloth", 1], "difficulty": 1.0, "time_minutes": 120, "tools": ["dye_vat"]},
    # recipes that EXIST but are not COMMONLY KNOWN in bigville (common: False -> must be taught or read to be made here)
    {"name": "make_paper",   "requires": "papermaker", "in": [["rag", 3], ["water", 2]],    "out": ["paper", 5],   "difficulty": 2.0, "time_minutes": 240, "tools": ["press"], "common": False},
    {"name": "print_newspaper", "requires": "printer",   "in": [["paper", 1], ["ink", 1]],   "out": ["newspaper", 20], "difficulty": 1.2, "time_minutes": 60, "tools": ["printing_press"]},
    {"name": "make_sandwich", "requires": "cook",     "in": [["ham", 1], ["bread", 1]],   "out": ["sandwich", 1], "difficulty": 0.5, "time_minutes": 10},
    {"name": "make_ink",     "requires": "inkmaker",   "in": [["soot", 1], ["oil", 1]],     "out": ["ink", 3],     "difficulty": 1.5, "time_minutes": 120, "common": False},
    # --- food / cooking ---
    # A bakery oven load: one firing bakes ~60 loaves (a loaf is one resident's bread for a period) in
    # about two hours of the baker's work, on far less fuel per loaf than a household hearth -- so one
    # baker feeds a couple of hundred people, as village bakers did. Baking at home is open to anyone
    # but costs much more time and fuel per loaf.
    {"name": "bake_bread",   "requires": "baker",     "in": [["flour", 40], ["water", 20]],                        "out": ["bread", 60],  "difficulty": 1.5, "time_minutes": 120, "tools": ["oven"]},
    {"name": "bake_bread_at_home", "requires": "cook", "open": True, "fallback": True, "in": [["flour", 2], ["water", 1]],          "out": ["bread", 3],   "difficulty": 1.0, "time_minutes": 90},
    {"name": "make_pottage", "requires": "cook",      "in": [["oats", 1], ["water", 2], ["cabbage", 1]],           "out": ["pottage", 3], "difficulty": 1.0, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "make_stew",    "requires": "cook",      "in": [["beef", 1], ["carrot", 1], ["onion", 1], ["water", 2]],"out": ["stew", 3],   "difficulty": 1.5, "time_minutes": 150, "tools": ["pot"]},
    {"name": "roast_meat",   "requires": "cook",      "in": [["pork", 1], ["salt", 1]],                            "out": ["roast", 1],   "difficulty": 1.5, "time_minutes": 120, "tools": ["spit"]},
    {"name": "make_pie",     "requires": "baker",     "in": [["flour", 2], ["beef", 1], ["onion", 1]],             "out": ["pie", 1],     "difficulty": 2.0, "time_minutes": 150, "tools": ["oven"]},
    {"name": "churn_butter", "requires": "dairymaid", "in": [["milk", 4]],                                         "out": ["butter", 1],  "difficulty": 1.0, "time_minutes": 60,  "tools": ["churn"]},
    {"name": "make_cheese",  "requires": "dairymaid", "in": [["milk", 6], ["salt", 1]],                            "out": ["cheese", 2],  "difficulty": 1.5, "time_minutes": 240, "tools": ["press"], "byproducts": {"scraps": 2}},  # whey
    {"name": "salt_pork",    "requires": "cook",      "in": [["pork", 2], ["salt", 1]],                            "out": ["bacon", 2],   "difficulty": 1.0, "time_minutes": 60},
    # --- expanded staple foods ---
    {"name": "make_gruel",       "requires": "cook",  "in": [["grain", 1], ["water", 2]],                         "out": ["gruel", 3],       "difficulty": 0.6, "time_minutes": 45,  "tools": ["pot"]},
    {"name": "make_porridge",    "requires": "cook",  "in": [["oats", 1], ["milk", 1], ["water", 1]],            "out": ["porridge", 3],    "difficulty": 0.8, "time_minutes": 60,  "tools": ["pot"]},
    {"name": "bake_oatcakes",    "requires": "baker", "in": [["oats", 2], ["flour", 1], ["water", 1]],          "out": ["oatcake", 4],      "difficulty": 1.0, "time_minutes": 90,  "tools": ["oven"]},
    {"name": "bake_flatbread",   "requires": "baker", "in": [["flour", 2], ["water", 1], ["oil", 1]],            "out": ["flatbread", 4],    "difficulty": 1.0, "time_minutes": 75,  "tools": ["oven"]},
    {"name": "make_pancakes",    "requires": "cook",  "in": [["flour", 2], ["eggs", 1], ["milk", 1]],            "out": ["pancake", 5],      "difficulty": 1.0, "time_minutes": 60,  "tools": ["griddle"]},
    {"name": "make_dumplings",   "requires": "cook",  "in": [["flour", 2], ["eggs", 1], ["water", 1]],           "out": ["dumpling", 6],     "difficulty": 1.2, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "make_noodles",     "requires": "cook",  "in": [["flour", 2], ["eggs", 1]],                         "out": ["noodles", 4],      "difficulty": 1.2, "time_minutes": 90,  "tools": ["board"]},
    {"name": "bake_crackers",    "requires": "baker", "in": [["flour", 2], ["water", 1], ["salt", 1]],          "out": ["crackers", 6],     "difficulty": 0.9, "time_minutes": 75,  "tools": ["oven"]},
    # --- soups, stews, and savoury meals ---
    {"name": "make_vegetable_soup", "requires": "cook", "in": [["potato", 1], ["carrot", 1], ["onion", 1], ["water", 2]], "out": ["vegetable_soup", 4], "difficulty": 1.0, "time_minutes": 100, "tools": ["pot"]},
    {"name": "make_root_soup",       "requires": "cook", "in": [["turnip", 1], ["parsnip", 1], ["leek", 1], ["water", 2]],   "out": ["root_soup", 4],       "difficulty": 1.0, "time_minutes": 100, "tools": ["pot"]},
    {"name": "make_bean_stew",       "requires": "cook", "in": [["bean", 1], ["carrot", 1], ["onion", 1], ["water", 2]],     "out": ["bean_stew", 4],       "difficulty": 1.1, "time_minutes": 120, "tools": ["pot"]},
    {"name": "make_lentil_stew",     "requires": "cook", "in": [["lentil", 1], ["onion", 1], ["garlic", 1], ["water", 2]],   "out": ["lentil_stew", 4],     "difficulty": 1.1, "time_minutes": 120, "tools": ["pot"]},
    {"name": "make_fish_stew",       "requires": "cook", "in": [["fish", 1], ["potato", 1], ["onion", 1], ["water", 2]],    "out": ["fish_stew", 3],       "difficulty": 1.4, "time_minutes": 130, "tools": ["pot"]},
    {"name": "make_sausage_stew",    "requires": "cook", "in": [["sausage", 1], ["bean", 1], ["onion", 1], ["water", 2]],   "out": ["sausage_stew", 4],    "difficulty": 1.3, "time_minutes": 125, "tools": ["pot"]},
    {"name": "make_bacon_eggs",     "requires": "cook", "in": [["bacon", 1], ["eggs", 2]],                               "out": ["bacon_eggs", 2],     "difficulty": 0.8, "time_minutes": 45,  "tools": ["griddle"]},
    {"name": "roast_poultry",       "requires": "cook", "in": [["poultry", 1], ["salt", 1], ["sage", 1]],              "out": ["roast_poultry", 2],   "difficulty": 1.5, "time_minutes": 135, "tools": ["spit"]},
    {"name": "roast_fish",          "requires": "cook", "in": [["fish", 1], ["salt", 1], ["thyme", 1]],                "out": ["roast_fish", 2],      "difficulty": 1.3, "time_minutes": 90,  "tools": ["spit"]},
    {"name": "stuffed_cabbage",     "requires": "cook", "in": [["cabbage", 1], ["pork", 1], ["grain", 1], ["onion", 1]], "out": ["stuffed_cabbage", 4], "difficulty": 1.8, "time_minutes": 160, "tools": ["pot"]},
    {"name": "make_omelette",       "requires": "cook", "in": [["eggs", 2], ["milk", 1], ["onion", 1]],                 "out": ["omelette", 2],       "difficulty": 1.0, "time_minutes": 50,  "tools": ["griddle"]},
    # --- pies, dairy, and sweets ---
    {"name": "make_fish_pie",       "requires": "baker", "in": [["flour", 2], ["fish", 1], ["onion", 1]],             "out": ["fish_pie", 2],       "difficulty": 1.8, "time_minutes": 150, "tools": ["oven"]},
    {"name": "make_meat_pie",       "requires": "baker", "in": [["flour", 2], ["beef", 1], ["onion", 1]],             "out": ["meat_pie", 2],       "difficulty": 1.8, "time_minutes": 150, "tools": ["oven"]},
    {"name": "make_shepherds_pie",  "requires": "baker", "in": [["flour", 1], ["mutton", 1], ["potato", 2], ["onion", 1]], "out": ["shepherds_pie", 3], "difficulty": 2.0, "time_minutes": 180, "tools": ["oven"]},
    {"name": "make_cheese_pie",     "requires": "baker", "in": [["flour", 2], ["cheese", 1], ["eggs", 1]],              "out": ["cheese_pie", 2],     "difficulty": 1.8, "time_minutes": 145, "tools": ["oven"]},
    {"name": "make_buttered_bread", "requires": "cook",  "in": [["bread", 1], ["butter", 1]],                           "out": ["buttered_bread", 2], "difficulty": 0.4, "time_minutes": 10},
    {"name": "make_fruit_pie",      "requires": "baker", "in": [["flour", 2], ["apple", 1], ["berry", 1]],              "out": ["fruit_pie", 2],      "difficulty": 1.7, "time_minutes": 150, "tools": ["oven"]},
    {"name": "bake_cake",           "requires": "baker", "in": [["flour", 2], ["eggs", 1], ["milk", 1], ["honey", 1]],    "out": ["cake", 3],           "difficulty": 2.0, "time_minutes": 150, "tools": ["oven"]},
    {"name": "bake_honey_cake",     "requires": "baker", "in": [["flour", 2], ["honey", 1], ["eggs", 1]],                 "out": ["honey_cake", 3],     "difficulty": 1.8, "time_minutes": 130, "tools": ["oven"]},
    {"name": "make_pudding",        "requires": "cook",  "in": [["milk", 2], ["eggs", 1], ["honey", 1]],                 "out": ["pudding", 3],        "difficulty": 1.3, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "make_cream_curd",     "requires": "dairymaid", "in": [["milk", 4], ["salt", 1]],                            "out": ["cream_curd", 2],    "difficulty": 1.4, "time_minutes": 180, "tools": ["press"]},
    {"name": "make_yogurt",         "requires": "dairymaid", "in": [["milk", 3]],                                         "out": ["yogurt", 2],        "difficulty": 1.2, "time_minutes": 180, "tools": ["pot"]},
    # --- preserving and drinks ---
    {"name": "make_pickles",         "requires": "cook", "in": [["cucumber", 2], ["vinegar", 1], ["salt", 1]],          "out": ["pickles", 3],        "difficulty": 1.2, "time_minutes": 120, "tools": ["barrel"]},
    {"name": "make_sauerkraut",      "requires": "cook", "in": [["cabbage", 3], ["salt", 1]],                           "out": ["sauerkraut", 3],     "difficulty": 1.0, "time_minutes": 120, "tools": ["barrel"]},
    {"name": "dry_fruit",             "requires": "cook", "in": [["apple", 3]],                                          "out": ["dried_fruit", 2],   "difficulty": 0.7, "time_minutes": 180, "tools": ["drying_rack"]},
    {"name": "make_fruit_jam",        "requires": "cook", "in": [["berry", 3], ["sugar", 1]],                          "out": ["fruit_jam", 3],     "difficulty": 1.1, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "salt_fish",             "requires": "cook", "in": [["fish", 2], ["salt", 1]],                             "out": ["salt_fish", 2],     "difficulty": 0.9, "time_minutes": 75,  "tools": ["barrel"]},
    {"name": "smoke_fish",            "requires": "cook", "in": [["fish", 2], ["salt", 1], ["fuel", 1]],               "out": ["smoked_fish", 2],   "difficulty": 1.2, "time_minutes": 150, "tools": ["smoking_rack"]},
    {"name": "brew_cider",            "requires": "brewer", "in": [["apple", 4], ["water", 2]],                        "out": ["cider", 5],         "difficulty": 1.8, "time_minutes": 360, "tools": ["mash_tun"]},
    {"name": "brew_mead",             "requires": "brewer", "in": [["honey", 2], ["water", 2]],                        "out": ["mead", 4],          "difficulty": 2.0, "time_minutes": 360, "tools": ["mash_tun"]},
    {"name": "bind_book",    "requires": "scribe",    "in": [["paper", 3], ["ink", 1]],                            "out": ["book", 1],    "difficulty": 1.5, "time_minutes": 180, "tools": ["quill"]},
    # --- forestry and gathering. A recipe with no inputs is labour on the land: `gathered_from` names
    # where it is done, and `seasons` limits when (both are data; the world checks the season). ---
    {"name": "split_firewood",  "requires": "forester", "open": True, "in": [["lumber", 1]], "out": ["wood", 4],     "difficulty": 0.8, "time_minutes": 40, "tools": ["axe"]},
    {"name": "lift_saplings",   "requires": "forester", "open": True, "in": [], "out": ["sapling", 3],  "difficulty": 0.6, "time_minutes": 60,  "gathered_from": "woodlot", "seasons": ["winter", "spring"]},
    {"name": "gather_berries",  "requires": "forester", "open": True, "in": [], "out": ["berry", 4],    "difficulty": 0.4, "time_minutes": 90,  "gathered_from": "woodlot", "seasons": ["summer"]},
    {"name": "gather_mushrooms","requires": "forester", "open": True, "in": [], "out": ["mushroom", 3], "difficulty": 0.6, "time_minutes": 90,  "gathered_from": "woodlot", "seasons": ["autumn"]},
    {"name": "pick_apples",     "requires": "farmer", "open": True,   "in": [], "out": ["apple", 6],    "difficulty": 0.4, "time_minutes": 90,  "gathered_from": "orchard", "seasons": ["autumn"]},
    {"name": "pick_pears",      "requires": "farmer", "open": True,   "in": [], "out": ["pear", 5],     "difficulty": 0.4, "time_minutes": 90,  "gathered_from": "orchard", "seasons": ["autumn"]},
    {"name": "pick_plums",      "requires": "farmer", "open": True,   "in": [], "out": ["plum", 5],     "difficulty": 0.4, "time_minutes": 90,  "gathered_from": "orchard", "seasons": ["summer"]},
    {"name": "cut_sage",        "requires": "farmer", "open": True,   "in": [], "out": ["sage", 2],     "difficulty": 0.3, "time_minutes": 30,  "gathered_from": "kitchen_garden", "seasons": ["spring", "summer"]},
    {"name": "cut_thyme",       "requires": "farmer", "open": True,   "in": [], "out": ["thyme", 2],    "difficulty": 0.3, "time_minutes": 30,  "gathered_from": "kitchen_garden", "seasons": ["spring", "summer"]},
    {"name": "cut_parsley",     "requires": "farmer", "open": True,   "in": [], "out": ["parsley", 2],  "difficulty": 0.3, "time_minutes": 30,  "gathered_from": "kitchen_garden", "seasons": ["spring", "summer"]},
    {"name": "dig_ore",         "requires": "quarrier", "in": [], "out": ["ore", 2],      "difficulty": 1.5, "time_minutes": 120, "gathered_from": "quarry", "tools": ["pick"]},
    # --- the smith's tools and cooking metal (smithing heat is charcoal specifically, not any fuel) ---
    {"name": "forge_hammer",  "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["hammer", 1],  "difficulty": 1.5, "time_minutes": 90,  "tools": ["hammer"]},
    {"name": "forge_saw",     "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["saw", 1],     "difficulty": 2.0, "time_minutes": 120, "tools": ["hammer"]},
    {"name": "forge_adze",    "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["adze", 1],    "difficulty": 1.6, "time_minutes": 100, "tools": ["hammer"]},
    {"name": "forge_awl",     "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["awl", 1],     "difficulty": 0.8, "time_minutes": 30,  "tools": ["hammer"]},
    {"name": "forge_needle",  "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["needle", 1],  "difficulty": 1.2, "time_minutes": 40,  "tools": ["hammer"]},
    {"name": "forge_cleaver", "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["cleaver", 1], "difficulty": 1.5, "time_minutes": 90,  "tools": ["hammer"]},
    {"name": "forge_spade",   "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["spade", 1],   "difficulty": 1.4, "time_minutes": 120, "tools": ["hammer"]},
    {"name": "forge_axe",     "requires": "smith", "in": [["iron", 2], ["charcoal", 1]], "out": ["axe", 1],     "difficulty": 2.0, "time_minutes": 150, "tools": ["hammer"]},
    {"name": "forge_hinge",   "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["hinge", 1],   "difficulty": 1.0, "time_minutes": 45,  "tools": ["hammer"]},
    {"name": "forge_pot",     "requires": "smith", "in": [["iron", 2], ["charcoal", 1]], "out": ["pot", 1],     "difficulty": 1.8, "time_minutes": 120, "tools": ["hammer"]},
    {"name": "forge_pan",     "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["pan", 1],     "difficulty": 1.4, "time_minutes": 90,  "tools": ["hammer"]},
    {"name": "forge_griddle", "requires": "smith", "in": [["iron", 2], ["charcoal", 1]], "out": ["griddle", 1], "difficulty": 1.4, "time_minutes": 90,  "tools": ["hammer"]},
    {"name": "forge_spit",    "requires": "smith", "in": [["iron", 1], ["charcoal", 1]], "out": ["spit", 1],    "difficulty": 1.0, "time_minutes": 60,  "tools": ["hammer"]},
    # --- woodwork, cooperage, masonry: workshop equipment and the oven ---
    {"name": "make_stool",        "requires": "woodworker", "in": [["timber", 1]], "out": ["stool", 1],        "difficulty": 0.7, "time_minutes": 60,  "tools": ["saw"]},
    {"name": "make_board",        "requires": "woodworker", "in": [["timber", 1]], "out": ["board", 1],        "difficulty": 0.4, "time_minutes": 30,  "tools": ["saw"]},
    {"name": "make_drying_rack",  "requires": "woodworker", "in": [["timber", 2]], "out": ["drying_rack", 1],  "difficulty": 0.8, "time_minutes": 90,  "tools": ["saw"]},
    {"name": "make_smoking_rack", "requires": "woodworker", "in": [["timber", 2]], "out": ["smoking_rack", 1], "difficulty": 0.8, "time_minutes": 90,  "tools": ["saw"]},
    {"name": "make_press",        "requires": "woodworker", "in": [["timber", 4], ["nails", 4]], "out": ["press", 1], "difficulty": 2.0, "time_minutes": 240, "tools": ["saw"]},
    {"name": "make_bucket",       "requires": "cooper", "in": [["stave", 3]],  "out": ["bucket", 1],   "difficulty": 1.0, "time_minutes": 60,  "tools": ["adze"]},
    {"name": "make_churn",        "requires": "cooper", "in": [["stave", 4]],  "out": ["churn", 1],    "difficulty": 1.2, "time_minutes": 90,  "tools": ["adze"]},
    {"name": "make_mash_tun",     "requires": "cooper", "in": [["stave", 10]], "out": ["mash_tun", 1], "difficulty": 2.2, "time_minutes": 240, "tools": ["adze"]},
    {"name": "make_dye_vat",      "requires": "cooper", "in": [["stave", 8]],  "out": ["dye_vat", 1],  "difficulty": 2.0, "time_minutes": 200, "tools": ["adze"]},
    {"name": "dress_stone",       "requires": "mason",  "in": [["stone", 1]],  "out": ["blocks", 1],   "difficulty": 1.0, "time_minutes": 45,  "tools": ["hammer"]},
    {"name": "build_oven",        "requires": "mason",  "in": [["blocks", 8]], "out": ["oven", 1],     "difficulty": 2.0, "time_minutes": 480, "tools": ["hammer"]},
    # --- fibre: spinning, linen, nets, shirts, boots, rags, quills ---
    {"name": "spin_thread",  "requires": "weaver", "open": True,  "in": [["wool", 1]],               "out": ["thread", 2], "difficulty": 0.8, "time_minutes": 90},
    {"name": "spin_linen",   "requires": "weaver",  "in": [["flax", 3]],               "out": ["linen", 1],  "difficulty": 1.6, "time_minutes": 240, "tools": ["loom"]},
    {"name": "knit_net",     "requires": "weaver",  "in": [["thread", 4]],             "out": ["net", 1],    "difficulty": 1.2, "time_minutes": 180},
    {"name": "sew_shirt",    "requires": "tailor",  "in": [["linen", 2], ["thread", 1]], "out": ["shirt", 1], "difficulty": 1.0, "time_minutes": 90,  "tools": ["needle"]},
    {"name": "cut_rags",     "requires": "tailor", "open": True,  "in": [["cloth", 1]],              "out": ["rag", 6],    "difficulty": 0.2, "time_minutes": 15},
    {"name": "make_boots",   "requires": "cobbler", "in": [["leather", 2]],            "out": ["boots", 1],  "difficulty": 1.8, "time_minutes": 180, "tools": ["awl"]},
    {"name": "cut_quill",    "requires": "scribe",  "in": [["feather", 1]],            "out": ["quill", 1],  "difficulty": 0.5, "time_minutes": 15,  "tools": ["knife"]},
    # --- butchery and dairy ---
    {"name": "cure_ham",     "requires": "butcher",   "in": [["pork", 3], ["salt", 1]],                 "out": ["ham", 2],     "difficulty": 1.2, "time_minutes": 90,  "tools": ["cleaver"]},
    {"name": "make_sausage", "requires": "butcher",   "in": [["pork", 2], ["salt", 1], ["sage", 0.5], ["pepper", 0.5]], "out": ["sausage", 3], "difficulty": 1.3, "time_minutes": 90, "tools": ["cleaver"]},
    {"name": "render_lard",  "requires": "butcher",   "in": [["pork", 2], ["fuel", 1]],                 "out": ["lard", 1],    "difficulty": 0.8, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "skim_cream",   "requires": "dairymaid", "in": [["milk", 3]],                              "out": ["cream", 1],   "difficulty": 0.4, "time_minutes": 30},
    # --- brewing, milling, condiments ---
    {"name": "malt_barley",     "requires": "brewer", "in": [["barley", 3], ["water", 1], ["fuel", 1]], "out": ["malt", 3],  "difficulty": 1.4, "time_minutes": 240},
    {"name": "brew_beer",       "requires": "brewer", "in": [["malt", 3], ["hops", 1], ["water", 4], ["yeast", 1]], "out": ["beer", 5], "difficulty": 2.2, "time_minutes": 480, "tools": ["mash_tun"]},
    {"name": "propagate_yeast", "requires": "brewer", "in": [["grain", 1], ["water", 1]],              "out": ["yeast", 2],   "difficulty": 0.8, "time_minutes": 60},
    {"name": "make_vinegar",    "requires": "brewer", "in": [["cider", 2]],                            "out": ["vinegar", 2], "difficulty": 0.6, "time_minutes": 120, "tools": ["barrel"]},
    {"name": "grind_rye",       "requires": "miller", "in": [["rye", 30]],                             "out": ["flour", 20],  "difficulty": 1.0, "time_minutes": 45, "byproducts": {"scraps": 10}},
    {"name": "press_linseed_oil", "requires": "miller", "in": [["linseed", 3]],                        "out": ["oil", 1],     "difficulty": 1.2, "time_minutes": 60,  "tools": ["press"]},
    {"name": "make_mustard",    "requires": "cook",   "in": [["mustard_seed", 2], ["vinegar", 1]],     "out": ["mustard", 2], "difficulty": 0.6, "time_minutes": 30},
    # --- dishes that use otherwise-idle produce and spices ---
    {"name": "make_salad",      "requires": "cook",  "in": [["lettuce", 2], ["cucumber", 1], ["parsley", 1]], "out": ["salad", 3], "difficulty": 0.4, "time_minutes": 15},
    {"name": "make_pea_soup",   "requires": "cook",  "in": [["pea", 2], ["onion", 1], ["water", 2]],   "out": ["pea_soup", 4], "difficulty": 0.9, "time_minutes": 100, "tools": ["pot"]},
    {"name": "pickle_beets",    "requires": "cook",  "in": [["beet", 2], ["vinegar", 1], ["salt", 1]], "out": ["pickles", 3],  "difficulty": 1.0, "time_minutes": 90,  "tools": ["barrel"]},
    {"name": "bake_spice_cake", "requires": "baker", "in": [["flour", 2], ["honey", 1], ["eggs", 1], ["cinnamon", 0.5], ["ginger", 0.5], ["nutmeg", 0.5]], "out": ["spice_cake", 3], "difficulty": 2.2, "time_minutes": 150, "tools": ["oven"]},
    # --- household goods and soil: candles (wax or tallow), thatch, compost ---
    {"name": "make_candles",  "requires": "chandler", "in": [["candle_fat", 1], ["thread", 0.5], ["fuel", 0.5]], "out": ["candle", 1], "difficulty": 0.8, "time_minutes": 60, "tools": ["pot"]},
    {"name": "make_thatch",   "requires": "farmer", "open": True,   "in": [["straw", 4]],                       "out": ["thatch", 2],  "difficulty": 0.6, "time_minutes": 60},
    # Human waste is composted before it goes on a field; the compost heap also takes any scraps,
    # straw, or ash (the `compostable` type).
    {"name": "make_compost",  "requires": "farmer", "open": True,   "in": [["night_soil", 2], ["compostable", 2]], "out": ["compost", 3], "difficulty": 0.5, "time_minutes": 60, "tools": ["spade"]},
]

# Attach the abstract requirement to the dish rows without baking a particular appliance into the
# recipe. The former appliance-specific entries are retained as `method_tools` hints for callers that
# want a default presentation, but they are not production requirements.
for _recipe in RECIPES:
    if _recipe["name"] in HEATED_FOOD_RECIPES:
        _hints = list(_recipe.get("tools", []))
        _methods = []
        for _hint in _hints:
            for _method in PREPARATION_METHODS_BY_HINT.get(_hint, PREPARATION_METHODS):
                if _method not in _methods:
                    _methods.append(_method)
        _recipe["preparation"] = {"requires": list(PREPARATION_REQUIREMENTS),
                                   "methods": _methods or list(PREPARATION_METHODS)}
        if not any(_kind == "fuel" for _kind, _ in _recipe["in"]):
            _recipe["in"] = list(_recipe["in"]) + [["fuel", FUEL_PER_BATCH.get(_recipe["name"], 1)]]
        if "tools" in _recipe:
            _recipe["method_tools"] = _recipe.pop("tools")

# ---------------------------------------------------------------- BUILDINGS
# places, their staff/role, whether they shelter, and their rooms/affordances.
BUILDINGS = {
    "forge":    {"staff_role": "blacksmith", "provides": "smith",      "sheltered": True,  "rooms": ["smithy", "clamp"]},
    "woodshop": {"staff_role": "woodworker", "provides": "woodworker", "sheltered": True,  "rooms": ["shop"]},
    "mill":     {"staff_role": "miller",     "provides": "miller",     "sheltered": True,  "rooms": ["millroom", "store"]},
    "sawpit":   {"staff_role": "sawyer",     "provides": "sawyer",     "sheltered": False, "rooms": ["pit"]},
    "cooperage":  {"staff_role": "cooper",  "provides": "cooper",  "sheltered": True,  "rooms": ["workshop"]},
    "tannery":    {"staff_role": "tanner",  "provides": "tanner",  "sheltered": False, "rooms": ["pits", "drying"]},
    "cobbler":    {"staff_role": "cobbler", "provides": "cobbler", "sheltered": True,  "rooms": ["bench"]},
    "school":     {"staff_role": "teacher", "provides": "teacher", "sheltered": True,  "rooms": ["schoolroom"]},
    "printshop":  {"staff_role": "printer", "provides": "printer", "sheltered": True,  "rooms": ["pressroom"]},
    "weavery":    {"staff_role": "weaver",  "provides": "weaver",  "sheltered": True,  "rooms": ["loomroom"]},
    "tailorshop": {"staff_role": "tailor",  "provides": "tailor",  "sheltered": True,  "rooms": ["cuttingroom"]},
    "inn":        {"staff_role": "innkeeper", "provides": "brewer", "sheltered": True,  "rooms": ["taproom", "cellar", "brewhouse"]},
    "dyehouse":   {"staff_role": "dyer",      "provides": "dyer",   "sheltered": True,  "rooms": ["vatroom"]},
    "bakery":      {"staff_role": "baker",     "provides": "baker",     "sheltered": True,  "rooms": ["ovenroom"]},
    "kitchen":     {"staff_role": "cook",      "provides": "cook",      "sheltered": True,  "rooms": ["hearthroom"]},
    "dairy":       {"staff_role": "dairymaid", "provides": "dairymaid", "sheltered": True,  "rooms": ["churnroom"]},
    "wharf":       {"staff_role": "fisher",    "provides": "fisher",    "sheltered": False, "rooms": ["dock"]},
    "granary":     {"staff_role": "granary_keeper", "provides": "granary", "sheltered": True,
                    "rooms": ["grain_floor", "dry_store"]},
    "root_cellar": {"staff_role": "cellar_keeper", "provides": "root_storage", "sheltered": True,
                    "rooms": ["root_store"]},
    "wellhouse":   {"staff_role": "water_keeper", "provides": "water", "sheltered": False,
                    "rooms": ["well"]},
    "latrine":     {"staff_role": "sanitation_keeper", "provides": "sanitation", "sheltered": False,
                    "rooms": ["privy"]},
    "compost_yard": {"staff_role": "compost_keeper", "provides": "compost", "sheltered": False,
                    "rooms": ["heap"]},
    "smokehouse":  {"staff_role": "smoker", "provides": "smokehouse", "sheltered": True,
                    "rooms": ["smoke_room"]},
    "townhall":    {"staff_role": "mayor", "provides": "governance", "sheltered": True,
                     "footprint": (4, 4),
                     "rooms": ["council_room", "records_room"]},
    "church":      {"staff_role": "pastor", "provides": "worship", "sheltered": True,
                     "display_name": "Church", "footprint": (4, 4),
                     "rooms": ["nave", "vestry"]},
    "watchhouse":  {"staff_role": "constable", "provides": "constable", "sheltered": True,
                    "display_name": "Police Station", "rooms": ["watch_room", "lockup"]},
    "records_office": {"staff_role": "clerk", "provides": "land_registry", "sheltered": True,
                       "rooms": ["land_register", "deed_archive", "public_counter"]},
    "scriptorium": {"staff_role": "scribe",    "provides": "scribe",    "sheltered": True,  "rooms": ["deskroom"]},
    "shambles":    {"staff_role": "butcher",   "provides": "butcher",   "sheltered": False, "rooms": ["killing_floor"]},
    "surgery":     {"staff_role": "doctor",    "provides": "care",      "sheltered": True,
                    "display_name": "Surgery", "rooms": ["consulting_room", "sickroom", "lying_in_room"]},
    # Catalogue buildings that are NOT standing when the town is founded (`founding: False`). They
    # are valid places -- a trade can name them and a BUILDING_PROJECT can raise them -- but the
    # founding town does not contain them (see founding_buildings()).
    "charcoal_hearth": {"staff_role": "collier", "provides": "collier", "sheltered": False,
                        "rooms": ["clamp_floor"], "founding": False},
    "papermill":   {"staff_role": "papermaker", "provides": "papermaker", "sheltered": True,
                    "rooms": ["vat_room", "drying_loft"], "founding": False},
    "inkhouse":    {"staff_role": "inkmaker",   "provides": "inkmaker",   "sheltered": True,
                    "rooms": ["mixing_room"], "founding": False},
    "house":       {"staff_role": "", "sheltered": True, "rooms": ["living_room", "hearth"], "founding": False},
    "barn":        {"staff_role": "", "sheltered": True, "rooms": ["stall", "hayloft"], "founding": False},
}


def founding_buildings():
    """The catalogue buildings standing when the town is founded (everything not `founding: False`)."""
    return {kind: spec for kind, spec in BUILDINGS.items() if spec.get("founding", True)}

# Fixtures are physical square contents, not decorative background pixels. Their offsets are
# interpreted relative to the scenario's declared square bounds and exported to any client.
TOWN_SQUARE_FIXTURES = [
    {"name": "north_market_stall", "kind": "market_stall", "offset": [-4, -2], "goods": ["bread", "grain"]},
    {"name": "east_market_stall", "kind": "market_stall", "offset": [1, -2], "goods": ["fish", "cheese"]},
    {"name": "west_market_stall", "kind": "market_stall", "offset": [-1, 1], "goods": ["cloth", "knife", "spade"]},
    {"name": "town_noticeboard", "kind": "noticeboard", "offset": [-5, 0], "goods": []},
    {"name": "public_well", "kind": "well", "offset": [4, 0], "goods": ["water"]},
    {"name": "south_bench_west", "kind": "bench", "offset": [-3, 2], "goods": []},
    {"name": "south_bench_east", "kind": "bench", "offset": [2, 2], "goods": []},
]

# Construction is separate from the catalogue of places already present when the town is
# founded.  A project creates another instance of a catalogue building (a second granary, a new
# house, a barn); the building's staff, shelter, and rooms come from BUILDINGS, and the project
# adds only what raising it costs.
BUILDING_PROJECTS = {
    "house": {"building": "house", "inputs": {"timber": 12, "thatch": 8},
              "labour": 10.0, "affordance": "shelter"},
    "barn": {"building": "barn", "inputs": {"timber": 18, "thatch": 12},
             "labour": 14.0, "affordance": "house_livestock"},
    "granary": {"building": "granary", "inputs": {"timber": 20, "thatch": 15},
                "labour": 18.0, "affordance": "store_dry_food"},
    "root_cellar": {"building": "root_cellar", "inputs": {"stone": 18, "timber": 10},
                    "labour": 16.0, "affordance": "store_root_crops"},
    "wellhouse": {"building": "wellhouse", "inputs": {"stone": 12, "timber": 6},
                  "labour": 12.0, "affordance": "draw_water"},
    "charcoal_hearth": {"building": "charcoal_hearth", "inputs": {"stone": 6, "timber": 4},
                        "labour": 6.0, "affordance": "burn_charcoal"},
    "papermill": {"building": "papermill", "inputs": {"timber": 16, "stone": 10},
                  "labour": 16.0, "affordance": "make_paper"},
    "inkhouse": {"building": "inkhouse", "inputs": {"timber": 10, "stone": 4},
                 "labour": 8.0, "affordance": "make_ink"},
}

# Renewable natural-resource deposits a map can place. `tile` names the map tile that IS the
# resource body (the deposit sits on a walkable cell beside it); stock/growback/capacity seed the
# world's ResourceDeposit node. The kind is also the item extracted (ITEMS).
RESOURCE_DEPOSITS = {
    "fish":   {"tile": "water", "stock": 60.0, "growback": 3.0, "capacity": 120.0, "minutes_per_unit": 30},
    "lumber": {"tile": "tree",  "stock": 60.0, "growback": 4.0, "capacity": 120.0, "minutes_per_unit": 40},
    "stone":  {"tile": "wall",  "stock": 60.0, "growback": 3.0, "capacity": 120.0, "minutes_per_unit": 40},
}

# The one-input shop chains the cast's shopkeeping trades run (deliver input -> work -> sell output).
# The map's `work` sites name where each shop stands; a trade with no work site gets no shop.
SHOP_CHAINS = {
    "fishmonger": {"in": "fish",   "out": "fish_ready"},
    "carpenter":  {"in": "lumber", "out": "furniture"},
    "mason":      {"in": "stone",  "out": "blocks"},
    "bakery":     {"in": "grain",  "out": "bread"},
}


# ---------------------------------------------------------------- TERRAIN MOVEMENT
# Movement is scenario data, not a hard-coded preference in a cognition backend.  The world maps
# tile names onto these records and publishes the read-off with each movement affordance.  A speed
# of 1.0 is the ordinary grass baseline; ``move_time`` is the relative time for one step and
# ``stamina_multiplier`` scales the body's existing exertion event.
TERRAIN_MOVEMENT = {
    "grass":  {"speed": 1.00, "move_time": 1.00, "stamina_multiplier": 1.00},
    "path":   {"speed": 1.35, "move_time": 0.75, "stamina_multiplier": 0.65},
    "floor":  {"speed": 1.05, "move_time": 0.95, "stamina_multiplier": 0.90},
    "square": {"speed": 1.15, "move_time": 0.85, "stamina_multiplier": 0.80},
    "tree":   {"speed": 0.45, "move_time": 2.20, "stamina_multiplier": 2.00},
    "water":  {"speed": 0.00, "move_time": 999.0, "stamina_multiplier": 4.00},
    "wall":   {"speed": 0.00, "move_time": 999.0, "stamina_multiplier": 4.00},
}


# ---------------------------------------------------------------- TERRAIN WEAR
# Ground remembers footfall.  A terrain may declare what repeated traversal turns it INTO
# (``wears_to``) and what disuse turns it BACK into (``reverts_to``); a terrain with no record
# here is inert and never changes.  Both directions are the same accumulator: ``wear`` on a map
# cell runs 0.0 -> 1.0 toward ``wears_to``, and decays toward ``reverts_to`` when nobody walks
# there.  The cell's movement read-off is interpolated across that accumulator rather than
# switching at the end, so ground that is part-worn is already part-easier -- which is what lets
# traffic recruit more traffic instead of nothing happening until a threshold trips.
#
# ``passes_to_form`` is how many traversals convert a fresh cell, and ``ticks_to_fade`` how many
# idle turns undo it.  Stating them as counts rather than per-event deltas keeps this an
# experiment parameter: a scenario asking "how many crossings make a desire path?" sets the
# number it is asking about.  ``load_sensitive`` scales a pass by the walker's carried load, so a
# heavy cart wears ground faster than a child -- omit it and every walker wears alike.
#
# A cell keeps the terrain it was SEEDED as and one accumulator over it, so wearing and fading
# are one quantity read in two directions and a formed path is never confused with a built one.
# Ground seeded as ``path`` has no record here and so is permanent infrastructure; a path that
# WORE into existence is only ever the far end of grass's accumulator, and stops being a path the
# moment the traffic that made it stops.
TERRAIN_WEAR = {
    "grass": {"wears_to": "path",  "passes_to_form":  40.0, "ticks_to_fade": 400.0,
              "load_sensitive": True},
    "tree":  {"wears_to": "grass", "passes_to_form": 120.0, "ticks_to_fade": 600.0,
              "load_sensitive": True},
}


# ---------------------------------------------------------------- ANIMALS
# livestock + working animals as DATA. `gives` maps a product -> yield; `eats` is the feed; matures
# and lifespan are in the sim's months; a draught animal has a `pull` (the weight it can haul).
ANIMALS = {
    "pig":     {"gives": {"pork": 40, "hide": 2},            "eats": "scraps", "matures": 6,  "lifespan": 15,  "role": "meat", "ration": 2, "starve_limit": 3, "manure": 0.8, "care_minutes": 15},
    "cow":     {"gives": {"milk": 3, "beef": 200, "hide": 5},"eats": "grass",  "matures": 24, "lifespan": 240, "role": "dairy", "ration": 4, "starve_limit": 3, "manure": 2.0, "care_minutes": 45},
    "chicken": {"gives": {"eggs": 1, "poultry": 2, "feather": 2}, "eats": "grain", "matures": 5, "lifespan": 96, "role": "eggs", "ration": 1, "starve_limit": 4, "manure": 0.1, "care_minutes": 10},
    "horse":   {"gives": {"labour": 1},                      "eats": "hay",    "matures": 36, "lifespan": 360, "role": "draught", "ration": 3, "starve_limit": 3, "pull": 500.0, "manure": 1.5, "care_minutes": 30},
    "dog":     {"gives": {"herding": 1},                     "eats": "scraps", "matures": 12, "lifespan": 180, "role": "working", "ration": 1, "starve_limit": 5, "care_minutes": 5},
    "cat":     {"gives": {"ratting": 1},                     "eats": "milk",   "matures": 8,  "lifespan": 180, "role": "working", "ration": 1, "starve_limit": 3, "care_minutes": 0},
    "sheep":   {"gives": {"wool": 4, "mutton": 60}, "eats": "grass", "matures": 12, "lifespan": 120, "role": "wool", "ration": 1, "starve_limit": 3, "manure": 0.6, "care_minutes": 10},
    "bee":     {"gives": {"honey": 3, "wax": 1}, "eats": "nectar", "matures": 1, "lifespan": 36, "role": "pollination", "ration": 1, "starve_limit": 3, "care_minutes": 5},
}

# `care_minutes` is the daily husbandry one animal takes (feeding, mucking out, milking).
# `manure` is what a FED animal leaves per period (collected into the store as `manure`). `gives`
# lists everything an animal can yield; SLAUGHTER_PRODUCTS are the ones taken only by killing it.
SLAUGHTER_PRODUCTS = frozenset({"pork", "beef", "mutton", "poultry", "fish", "ham", "bacon",
                                "sausage", "hide", "feather"})

# Species-specific inputs for the inexpensive animal cognition backend.  These
# are preferences and identity, not permissions: the world still publishes
# admissible animal actions and enforces movement and feeding.
ANIMAL_NPC_SETUP = {
    "pig": {"role": "livestock", "drives": ("survival", "comfort"),
            "personality": {"mood_bias": 0.20, "prior_world_safe": 0.65}},
    "cow": {"role": "grazing_livestock", "drives": ("survival", "comfort"),
            "personality": {"mood_bias": 0.25, "prior_world_safe": 0.70}},
    "chicken": {"role": "poultry", "drives": ("survival", "security"),
                "personality": {"mood_bias": 0.10, "prior_world_safe": 0.55}},
    "horse": {"role": "draught", "drives": ("survival", "security", "duty"),
              "personality": {"mood_bias": 0.05, "prior_world_safe": 0.45}},
    "dog": {"role": "herding_dog", "drives": ("care", "duty", "security"),
            "preferred_targets": ("cow", "sheep", "pig"),
            "personality": {"mood_bias": 0.15, "role_identity": 0.85,
                            "prior_world_safe": 0.55}},
    "cat": {"role": "working_cat", "drives": ("survival", "security"),
            "personality": {"mood_bias": 0.30, "prior_world_safe": 0.50}},
    "sheep": {"role": "grazing_livestock", "drives": ("survival", "security"),
              "personality": {"mood_bias": 0.15, "prior_world_safe": 0.65}},
    "bee": {"role": "pollinator", "drives": ("duty", "survival"),
            "personality": {"mood_bias": 0.05, "role_identity": 0.75,
                            "prior_world_safe": 0.60}},
}

# Fences and enclosures are physical map entities.  They do not impose a
# storage or ownership policy; they only constrain animal movement while intact.
FENCE_TYPES = {
    "wooden_fence": {"material": "timber", "durability": 1.0, "animal_barrier": True},
    "hedge": {"material": "sapling", "durability": 0.8, "animal_barrier": True},
    "stone_wall": {"material": "stone", "durability": 1.4, "animal_barrier": True},
    "gate": {"material": "timber", "durability": 1.0, "animal_barrier": False},
}

ENCLOSURE_TYPES = {
    "paddock": {"purpose": "livestock", "fence": "wooden_fence"},
    "yard": {"purpose": "working_animals", "fence": "wooden_fence"},
    "orchard": {"purpose": "crops", "fence": "hedge"},
}

ANIMAL_HUSBANDRY = {
    "milk": {"species": "cow", "product": "milk", "cooldown": 1,
             "roles": ["farmer", "dairymaid", "animal_keeper"]},
    "shear": {"species": "sheep", "product": "wool", "cooldown": 12,
              "roles": ["farmer", "shepherd", "animal_keeper"]},
    "collect_eggs": {"species": "chicken", "product": "eggs", "cooldown": 1,
                     "roles": ["farmer", "farm_labourer", "animal_keeper"]},
}


# ---------------------------------------------------------------- CROPS
# every crop is SOWN from its seed, GROWS over `grow_periods` (each period it must be WATERED or it
# builds thirst and WILTS past `wilt`), and when mature is HARVESTED for `yield` of its product.
#   nitrogen    -- soil nitrogen a bed draws from its land parcel each period it grows. The harvest
#                  scales with how much of that demand the soil met (see NITROGEN["yield_floor"]).
#   fixes       -- nitrogen a legume returns to the parcel each period (bacteria in its root nodules).
#   byproducts  -- other harvest per bed (straw from cereals), scaled like the yield.
#   seed_return -- seed saved back from the harvest (default 1), which is what makes a crop renewable.
_CEREAL = {"nitrogen": 0.06, "byproducts": {"straw": 3}, "seed_return": 1.5}
CROPS = {
    "wheat":   {"seed": "wheat_seed",   "harvest": "grain",   "grow_periods": 4, "water": 2, "yield": 8,  "wilt": 2, "season": "spring", **_CEREAL},
    "barley":  {"seed": "barley_seed",  "harvest": "barley",  "grow_periods": 4, "water": 2, "yield": 8,  "wilt": 2, "season": "spring", **_CEREAL},
    "oats":    {"seed": "oats_seed",    "harvest": "oats",    "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring", **_CEREAL},
    "rye":     {"seed": "rye_seed",     "harvest": "rye",     "grow_periods": 4, "water": 1, "yield": 7,  "wilt": 3, "season": "autumn", **_CEREAL},
    "cabbage": {"seed": "cabbage_seed", "harvest": "cabbage", "grow_periods": 3, "water": 3, "yield": 6,  "wilt": 2, "season": "spring", "nitrogen": 0.08},
    "carrot":  {"seed": "carrot_seed",  "harvest": "carrot",  "grow_periods": 3, "water": 2, "yield": 10, "wilt": 2, "season": "spring", "nitrogen": 0.04},
    "onion":   {"seed": "onion_seed",   "harvest": "onion",   "grow_periods": 3, "water": 2, "yield": 9,  "wilt": 2, "season": "spring", "nitrogen": 0.04},
    "potato":  {"seed": "potato_seed",  "harvest": "potato",  "grow_periods": 4, "water": 2, "yield": 12, "wilt": 2, "season": "spring", "nitrogen": 0.06},
    "turnip":  {"seed": "turnip_seed",  "harvest": "turnip",  "grow_periods": 2, "water": 2, "yield": 8,  "wilt": 2, "season": "autumn", "nitrogen": 0.04},
    "bean":    {"seed": "bean_seed",    "harvest": "bean",    "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring", "nitrogen": 0.02, "fixes": 0.08},
    "pea":     {"seed": "pea_seed",     "harvest": "pea",     "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring", "nitrogen": 0.02, "fixes": 0.08},
    "leek":    {"seed": "leek_seed",    "harvest": "leek",    "grow_periods": 4, "water": 2, "yield": 6,  "wilt": 2, "season": "autumn", "nitrogen": 0.04},
    "parsnip": {"seed": "parsnip_seed", "harvest": "parsnip", "grow_periods": 4, "water": 2, "yield": 6,  "wilt": 2, "season": "autumn", "nitrogen": 0.04},
    "beet":    {"seed": "beet_seed",    "harvest": "beet",    "grow_periods": 3, "water": 2, "yield": 8,  "wilt": 2, "season": "autumn", "nitrogen": 0.05},
    "garlic":  {"seed": "garlic_seed",  "harvest": "garlic",  "grow_periods": 4, "water": 1, "yield": 8,  "wilt": 3, "season": "autumn", "nitrogen": 0.03},
    "lettuce": {"seed": "lettuce_seed", "harvest": "lettuce", "grow_periods": 2, "water": 3, "yield": 8,  "wilt": 1, "season": "spring", "nitrogen": 0.03},
    "cucumber": {"seed": "cucumber_seed", "harvest": "cucumber", "grow_periods": 3, "water": 3, "yield": 8, "wilt": 1, "season": "summer", "nitrogen": 0.05},
    "lentil":  {"seed": "lentil_seed",  "harvest": "lentil",  "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring", "nitrogen": 0.02, "fixes": 0.08},
    "hops":    {"seed": "hops_seed",    "harvest": "hops",    "grow_periods": 4, "water": 2, "yield": 5,  "wilt": 2, "season": "spring", "nitrogen": 0.06},
    "flax":    {"seed": "linseed",      "harvest": "flax",    "grow_periods": 3, "water": 2, "yield": 6,  "wilt": 2, "season": "spring", "nitrogen": 0.03, "seed_return": 3},
    "mustard": {"seed": "mustard_seed", "harvest": "mustard_seed", "grow_periods": 2, "water": 2, "yield": 4, "wilt": 2, "season": "spring", "nitrogen": 0.04},
}

for _spec in CROPS.values():          # a harvest saves back a little more seed than it took
    _spec.setdefault("seed_return", 1.25)

# Minutes of field work per crop bed: sowing and harvesting once per crop, watering every period,
# and one fertilise action (spreading NITROGEN["fertilise_amount"] on a plot).
FIELD_WORK = {"sow": 20, "water": 10, "harvest": 30, "fertilise": 30}

# Which crops a farmer sows on an arable plot: the main rotation normally, and a nitrogen-fixing
# restorative crop when the plot's nitrogen has fallen below NITROGEN["restore_below"] of capacity.
ARABLE_ROTATION = {"main": ("wheat", "barley", "oats"), "restorative": ("bean", "pea", "lentil")}

# ---------------------------------------------------------------- THE NITROGEN CYCLE
# Each land parcel holds soil nitrogen (`nitrogen` on the Land node), in units per unit of area:
#   in:   SOILS[...]["nitrogen"] at the start; `mineralisation` each period (organic matter slowly
#         releasing N, plus rain); legume `fixes`; and fertiliser a farmer spreads (any item with a
#         `nitrogen` tag -- manure, compost, dung -- via the `fertilise` action).
#   out:  each growing bed's `nitrogen` demand (carried off in the harvest), and `leaching` -- a
#         fraction of the parcel's N lost each period, scaled by the soil's drainage.
#   loop: people eat the harvest -> night soil at the latrine -> composted (make_compost) -> spread;
#         livestock eat pasture -> manure -> spread; burnt fuel -> ash -> compost.
# A bed whose demand was fully met yields its full `yield`; one that got none yields `yield_floor`
# of it. Beds not on a land parcel (small test fixtures) are unaffected.
NITROGEN = {
    "capacity_per_area": 12.0,
    "mineralisation_per_area": 0.10,
    "leaching": 0.01,
    "yield_floor": 0.30,
    "fertiliser_type": "fertiliser",     # the INPUT_TYPES slot the fertilise action draws on
    "fertilise_amount": 2.0,             # nitrogen spread per fertilise action
    "fertilise_below": 0.60,             # farmers offer to fertilise a plot below this fraction of capacity
    "restore_below": 0.40,               # ...and sow a restorative legume below this fraction
}

# Founding provisions for the 100-resident scenario.  These are a finite bridge to the first
# harvest, not an infinite food cheat: residents and livestock still consume the physical stocks,
# and the reserve fails unless the village grows, preserves, trades, or imports replacements.
STARTING_STOCK = {
    # Eight days of reserve for the 100-person founding cast; the first local
    # harvest is intentionally timed to replace this finite bridge.
    "bread": 800.0,
    "water": 100.0,
    "wood": 40.0,
    "salt": 20.0,
    "wheat_seed": 40.0,
    "barley_seed": 20.0,
    "oats_seed": 20.0,
    "potato_seed": 20.0,
    "cabbage_seed": 20.0,
    "carrot_seed": 20.0,
    "onion_seed": 20.0,
    "bean_seed": 20.0,
    "grass": 120.0,
    "hay": 120.0,
    "grain": 40.0,
    "scraps": 40.0,
    "nectar": 40.0,
    # seed for every other crop, so each can be sown; harvest seed_return keeps them going
    "rye_seed": 10.0, "turnip_seed": 10.0, "pea_seed": 20.0, "leek_seed": 10.0, "parsnip_seed": 10.0,
    "beet_seed": 10.0, "garlic_seed": 10.0, "lettuce_seed": 10.0, "cucumber_seed": 10.0,
    "lentil_seed": 10.0, "hops_seed": 10.0, "linseed": 10.0, "mustard_seed": 10.0,
}

STARTING_CROPS = ("wheat", "barley", "oats", "cabbage", "potato", "carrot", "onion", "bean")

# ---------------------------------------------------------------------------
# SOCIAL ACTIONS -- these are actions an actor can perform while retaining the
# one substantial action available in a turn.  The distinction is data, not a
# special case in the world adapter: social contact, signalling, and consent
# do not consume the actor's major-action slot; travelling, working, eating,
# building, and carrying out an accepted task do.
#
# A request is not a world affordance.  It is a speech act carried by an
# utterance and interpreted by the listener's conversation concepts (the
# generic ``conversation`` seed).  Keeping ``ask`` here would let the world
# bypass comprehension and mint a request merely because an adapter called a
# method, which is precisely the wrong boundary for free-text conversation.

FREE_ACTIONS = {
    "speak": {"kind": "utterance", "requires_target": False},
    "write_note": {"kind": "written_message", "requires_target": False},
    "give_note": {"kind": "handoff", "requires_target": True},
    "accept": {"kind": "consent", "requires_target": True},
    "decline": {"kind": "refusal", "requires_target": True},
    "reply": {"kind": "utterance", "requires_target": True},
}

MAJOR_ACTIONS = {
    "move": {"kind": "travel"},
    # A purchase is a conversation followed by physical transfers.  There is
    # deliberately no ``buy`` action here: the actor can say what they want,
    # then give coin and receive the good through the ordinary give action.
    "give": {"kind": "transfer"},
    "put": {"kind": "placement"},
    "pick_up": {"kind": "handling"},
    "drop": {"kind": "handling"},
    "sell": {"kind": "exchange"},
    "sell_labor": {"kind": "exchange"},
    "work": {"kind": "production"},
    "eat": {"kind": "consumption"},
    "water": {"kind": "agriculture"},
    "rest": {"kind": "recovery"},
    "fetch": {"kind": "delegated_task"},
    "build": {"kind": "construction"},
    "harvest": {"kind": "agriculture"},
    "sow": {"kind": "agriculture"},
    "fertilise": {"kind": "agriculture"},
    "tend_animals": {"kind": "husbandry"},
    "maintain": {"kind": "maintenance"},
    "care": {"kind": "care"},
}

# Carrying is deliberately a physical threshold model, not a hard inventory
# gate.  A person can take hold of something they can barely manage; the
# consequences are slower travel and higher exertion.  The second threshold
# is the point at which the hand cannot retain it and the object falls.
CARRYING = {
    "overload_ratio": 1.0,
    "drop_ratio": 2.0,
    "base_move_energy": 1.0,
    "overload_energy_factor": 4.0,
}


# ---------------------------------------------------------------- VILLAGE SYSTEMS
# Data-driven schemas for the material, biological, infrastructural, and social systems a village
# coordinates. These are affordances and observation schemas, not hidden town facts.
SEASONS = {
    "spring": {"months": [1, 2, 3], "weather": ["rain", "cool", "mild"]},
    "summer": {"months": [4, 5, 6], "weather": ["hot", "dry", "storm"]},
    "autumn": {"months": [7, 8, 9], "weather": ["cool", "rain", "wind"]},
    "winter": {"months": [10, 11, 12], "weather": ["cold", "wet", "frost"]},
}

WEATHER = {
    "clear": {"rain": 0.0, "temperature": 0.6, "firewood_demand": 0.8},
    "rain": {"rain": 1.0, "temperature": 0.4, "firewood_demand": 0.9},
    "dry": {"rain": 0.0, "temperature": 0.8, "firewood_demand": 0.8},
    "storm": {"rain": 1.0, "temperature": 0.5, "firewood_demand": 0.9},
    "cold": {"rain": 0.3, "temperature": 0.1, "firewood_demand": 1.5},
    "wet": {"rain": 1.0, "temperature": 0.2, "firewood_demand": 1.2},
    "frost": {"rain": 0.0, "temperature": 0.0, "firewood_demand": 1.7},
    "wind": {"rain": 0.2, "temperature": 0.3, "firewood_demand": 1.1},
    "cool": {"rain": 0.2, "temperature": 0.4, "firewood_demand": 1.0},
    "mild": {"rain": 0.3, "temperature": 0.55, "firewood_demand": 0.85},
    "hot": {"rain": 0.0, "temperature": 0.95, "firewood_demand": 0.6},
}

WATER_SOURCES = {
    "well": {"kind": "groundwater", "yield": 40.0, "quality": 0.95, "seasonal": 0.10, "labour": 0.2},
    "spring": {"kind": "spring", "yield": 60.0, "quality": 0.98, "seasonal": 0.15, "labour": 0.1},
    "stream": {"kind": "surface", "yield": 100.0, "quality": 0.65, "seasonal": 0.40, "labour": 0.3},
    "rain_cistern": {"kind": "rainwater", "yield": 80.0, "quality": 0.75, "seasonal": 0.55, "labour": 0.1},
}

FUEL_SOURCES = {
    "woodlot": {"fuel": "wood", "renewable": True, "regrowth_periods": 48, "yield": 20.0, "labour": 1.0},
    "peat_cut": {"fuel": "peat", "renewable": False, "regrowth_periods": 0, "yield": 30.0, "labour": 1.5},
    "charcoal_hearth": {"fuel": "charcoal", "renewable": True, "regrowth_periods": 1, "yield": 8.0, "labour": 2.0},
    "dung_heap": {"fuel": "dung", "renewable": True, "regrowth_periods": 1, "yield": 5.0, "labour": 0.5},
}

SOILS = {
    "loam": {"fertility": 0.85, "water_retention": 0.75, "drainage": 0.65, "erosion": 0.10, "nitrogen": 8.0},
    "clay": {"fertility": 0.75, "water_retention": 0.90, "drainage": 0.30, "erosion": 0.08, "nitrogen": 7.0},
    "sand": {"fertility": 0.35, "water_retention": 0.25, "drainage": 0.95, "erosion": 0.25, "nitrogen": 3.0},
    "chalk": {"fertility": 0.55, "water_retention": 0.45, "drainage": 0.80, "erosion": 0.15, "nitrogen": 5.0},
}

LAND_USES = {
    "arable": {"soil": ["loam", "clay", "chalk"], "supports": ["crop", "pasture"]},
    "kitchen_garden": {"soil": ["loam", "clay"], "supports": ["vegetable", "herb"]},
    "orchard": {"soil": ["loam", "chalk"], "supports": ["tree_fruit", "bee"]},
    "pasture": {"soil": ["loam", "chalk"], "supports": ["grass", "livestock"]},
    "woodlot": {"soil": ["loam", "clay", "sand"], "supports": ["wood", "wild_food"]},
    "common": {"soil": ["loam", "clay", "sand", "chalk"], "supports": ["gathering", "grazing"]},
}

# Pasture is productive land, not just a place-marker for animals.  These
# yields are per unit of pasture area per period and become physical feed
# stocks; livestock still consumes them through the generic animal rules.
PASTURE_YIELDS = {"grass": 2.0, "hay": 1.0, "nectar": 1.0}

# Where each waste stream goes. `output` is the stock it becomes at its `treatment` place; the
# compost heap (make_compost) then turns night soil, scraps, and ash into compost for the fields.
# `per_resident` is the night soil one living resident leaves per period (kept only while a latrine
# stands; without one it is lost, and with it the nitrogen).
WASTE_CYCLES = {
    "human_waste": {"source": "household", "treatment": "latrine", "output": "night_soil", "risk": 0.8,
                    "per_resident": 0.2},
    "animal_manure": {"source": "livestock", "treatment": "compost_yard", "output": "manure", "risk": 0.4},
    "kitchen_scraps": {"source": "kitchen", "treatment": "compost_yard", "output": "compost", "risk": 0.2},
    "ash": {"source": "hearth", "treatment": "compost_yard", "output": "ash", "risk": 0.1},
}

LIFE_STAGES = {
    "infant": {"age_min": 0, "age_max": 3, "work_fraction": 0.0, "care": 1.0, "food": 0.35},
    "child": {"age_min": 4, "age_max": 12, "work_fraction": 0.25, "care": 0.5, "food": 0.60},
    "youth": {"age_min": 13, "age_max": 17, "work_fraction": 0.65, "care": 0.1, "food": 0.80},
    "adult": {"age_min": 18, "age_max": 64, "work_fraction": 1.0, "care": 0.0, "food": 1.0},
    "elder": {"age_min": 65, "age_max": 99, "work_fraction": 0.35, "care": 0.2, "food": 0.85},
}

HEALTH_CONDITIONS = {
    "healthy": {"work_fraction": 1.0, "food_need": 1.0, "care_need": 0.0, "contagious": False},
    "injured": {"work_fraction": 0.35, "food_need": 1.1, "care_need": 0.8, "contagious": False},
    "malnourished": {"work_fraction": 0.50, "food_need": 1.2, "care_need": 0.5, "contagious": False},
    "fever": {"work_fraction": 0.0, "food_need": 1.0, "care_need": 1.0, "contagious": True},
    "chronic": {"work_fraction": 0.60, "food_need": 1.1, "care_need": 0.6, "contagious": False},
}

INFRASTRUCTURE = {
    "well": {"affordance": "draw_water", "maintenance": ["stone", "timber"], "capacity": 40.0, "failure_risk": 0.02},
    "latrine": {"affordance": "contain_waste", "maintenance": ["timber"], "capacity": 20.0, "failure_risk": 0.05},
    "compost_yard": {"affordance": "process_waste", "maintenance": ["timber"], "capacity": 50.0, "failure_risk": 0.03},
    "smokehouse": {"affordance": "preserve_meat", "maintenance": ["stone", "timber"], "capacity": 30.0, "failure_risk": 0.04},
    "mill": {"affordance": "grind_grain", "maintenance": ["timber", "stone", "iron"], "capacity": 100.0, "failure_risk": 0.03},
    "granary": {"affordance": "store_dry_food", "maintenance": ["timber", "thatch"], "capacity": 500.0, "failure_risk": 0.02},
    "root_cellar": {"affordance": "store_root_crops", "maintenance": ["stone", "timber"], "capacity": 250.0, "failure_risk": 0.03},
    "road": {"affordance": "move_goods", "maintenance": ["stone", "timber"], "capacity": 1.0, "failure_risk": 0.04},
}

SHOCKS = {
    "drought": {"duration": [2, 6], "effects": ["water_shortage", "crop_failure", "fire_risk"]},
    "flood": {"duration": [1, 3], "effects": ["crop_damage", "contamination", "road_damage"]},
    "blight": {"duration": [2, 5], "effects": ["crop_loss", "seed_shortage"]},
    "livestock_disease": {"duration": [1, 4], "effects": ["animal_loss", "milk_shortage", "labour_loss"]},
    "fire": {"duration": [1, 1], "effects": ["building_damage", "fuel_shortage", "displacement"]},
    "trade_blockade": {"duration": [2, 8], "effects": ["import_shortage", "price_rise", "salt_shortage"]},
    "epidemic": {"duration": [2, 8], "effects": ["illness", "care_shortage", "labour_loss", "mortality"]},
}

AFFORDANCES = {
    "draw_water": {"domain": "water", "requires": ["water_source", "container"], "outputs": ["water"]},
    "store_harvest": {"domain": "storage", "requires": ["storage_place", "labour"], "outputs": ["stored_stock"]},
    "preserve_food": {"domain": "food", "requires": ["food", "heat_or_drying", "container"], "outputs": ["preserved_food"]},
    "compost_waste": {"domain": "waste", "requires": ["waste_site", "labour"], "outputs": ["compost", "manure"]},
    "repair_infrastructure": {"domain": "maintenance", "requires": ["material", "skill", "time"], "outputs": ["condition"]},
    "hold_assembly": {"domain": "governance", "requires": ["meeting_place", "participants"], "outputs": ["decision"]},
    "teach_reference": {"domain": "knowledge", "requires": ["teacher", "learner", "shared_experience"], "outputs": ["resident_fact"]},
    "publish_law": {"domain": "governance", "requires": ["authority", "writer", "document"], "outputs": ["written_law"]},
}

OBSERVATION_TYPES = {
    "weather": {"subjects": ["season", "rain", "temperature", "wind"], "source": "environment"},
    "soil": {"subjects": ["fertility", "moisture", "erosion"], "source": "land"},
    "storage": {"subjects": ["quantity", "condition", "capacity"], "source": "container"},
    "health": {"subjects": ["illness", "injury", "mortality"], "source": "residents"},
    "labour": {"subjects": ["available_time", "skill", "fatigue", "care"], "source": "households"},
    "prices": {"subjects": ["scarcity", "price", "imports"], "source": "market"},
    "authority": {"subjects": ["office", "compliance", "dispute"], "source": "governance"},
}


# ---------------------------------------------------------------- ADJECTIVES (condition classes)
# Each item belongs to an ADJECTIVAL CLASS -- a separate class whose ordered stages describe how it
# degrades. Condition runs 1.0 (perfect) -> 0.0 (destroyed); the adjective is the stage it has reached.
ADJECTIVES = {
    "metal":      ["pristine", "worn",      "rusty",   "ruined"],
    "perishable": ["fresh",    "stale",     "rotten",  "putrid"],
    "textile":    ["new",      "worn",      "frayed",  "ragged"],
    "wood":       ["sound",    "weathered", "rotten",  "crumbling"],
    "leather":    ["supple",   "worn",      "cracked", "perished"],
    "stone":      ["solid",    "chipped",   "cracked", "crumbling"],
    "durable":    ["sound",    "worn",      "damaged", "broken"],
}
# how fast each class takes DAMAGE OVER TIME (per period) -- food rots fast, metal rusts slowly
CLASS_DECAY = {"perishable": 0.25, "textile": 0.05, "leather": 0.05, "wood": 0.04,
               "metal": 0.02, "durable": 0.01, "stone": 0.005}
# raw produce/meat that spoil even though they are ingredients (not food-flagged dishes)
_PERISHABLE_RAW = {"cabbage","carrot","onion","potato","turnip","bean","pea","leek","parsnip","beet",
                   "garlic","lettuce","cucumber","lentil","mushroom",
                   "mutton","fish","beef","pork","poultry","hide","milk","eggs","butter"}

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


# ---------------------------------------------------------------------------
# RAW-MATERIAL SCARCITY -- what the raw stuff costs to obtain (a fact about the world)
# ---------------------------------------------------------------------------
# How rare/costly a unit of a RAW material is to OBTAIN: for an IMPORTED good this is the exogenous
# price bigville pays the outside world; for a gathered/farmed/mined/hunted one it is a rough rarity.
# Scale anchored on coin = 1.0: abundant local stuff << 1; imported luxuries and spices >> 1.
# This is how the world IS at the start, not public information: a seller reasons from what they
# have learned of it (their own raw-material costs and time), and different residents know it
# differently -- or not at all.
SCARCITY = {
    # near-free local by-products / gathered
    "soot": 0.05, "ash": 0.05, "night_soil": 0.02, "scraps": 0.05, "grass": 0.05, "water": 0.05, "rag": 0.1, "hay": 0.1,
    "thatch": 0.2, "peat": 0.3, "dung": 0.05, "manure": 0.05, "compost": 0.1,
    "medicine": 6.0, "nectar": 0.2, "wax": 1.0,
    # abundant local raw
    "wood": 0.3, "ore": 0.6, "grain": 0.5, "straw": 0.2,
    # farm crops (a unit of harvest)
    "barley": 0.5, "oats": 0.5, "rye": 0.5, "hops": 1.5,
    "cabbage": 0.4, "carrot": 0.4, "onion": 0.4, "potato": 0.3, "turnip": 0.3, "bean": 0.4,
    "pea": 0.4, "leek": 0.4, "parsnip": 0.4, "beet": 0.4, "garlic": 0.5, "lettuce": 0.4,
    "cucumber": 0.4, "lentil": 0.5, "apple": 0.5, "pear": 0.6, "plum": 0.7, "berry": 0.8,
    "mushroom": 0.8, "honey": 1.2, "cream": 1.0, "lard": 1.2, "vinegar": 1.0, "yeast": 0.6,
    "sugar": 4.0, "mustard": 2.0,
    # seed corn (a little dearer than the crop -- held back, not eaten)
    "wheat_seed": 0.6, "barley_seed": 0.6, "oats_seed": 0.6, "rye_seed": 0.6, "cabbage_seed": 0.5,
    "carrot_seed": 0.5, "onion_seed": 0.5, "potato_seed": 0.5, "turnip_seed": 0.5, "bean_seed": 0.5,
    "pea_seed": 0.5, "leek_seed": 0.5, "parsnip_seed": 0.5, "beet_seed": 0.5,
    "garlic_seed": 0.5, "lettuce_seed": 0.5, "cucumber_seed": 0.5, "lentil_seed": 0.5,
    "hops_seed": 0.8, "linseed": 0.5, "mustard_seed": 0.8,
    # new raw produce and by-products
    "flax": 0.6, "feather": 0.1, "sapling": 0.3,
    # animal yield
    "milk": 0.6, "eggs": 0.6, "wool": 1.0, "hide": 1.2,
    # meat + cured meat (a beast's-worth of labour behind it)
    "fish": 1.5, "poultry": 1.6, "pork": 1.8, "mutton": 2.0, "beef": 2.2, "sausage": 2.5, "ham": 3.0,
    # processed staples / mineral
    "thread": 0.8, "oil": 1.5, "salt": 3.0, "coin": 1.0,
    # herbs (grown locally) vs SPICES (imported, dear)
    "sage": 1.0, "thyme": 1.0, "parsley": 0.8,
    "pepper": 8.0, "cinnamon": 10.0, "ginger": 9.0, "nutmeg": 12.0,
    # imported dyes + fine fabrics -- the luxuries
    "dye": 5.0, "madder": 5.0, "woad": 6.0, "weld": 5.0, "linen": 3.0,
    "fur": 8.0, "velvet": 10.0, "silk": 12.0,
    # finished goods bought in ready-made (no local recipe) -- moderately dear
    "hinge": 3.0, "bucket": 3.0, "shirt": 4.0, "stool": 4.0, "spade": 6.0, "boots": 6.0, "axe": 8.0,
    "printing_press": 15.0,   # an expensive machine, bought in
    # extracted resources + the shop-chain outputs
    "stone": 0.4, "lumber": 0.5, "blocks": 1.0, "furniture": 4.0, "fish_ready": 1.8,
    # trade tools and workshop equipment (no local recipe yet -- priced as bought-in)
    "hammer": 4.0, "saw": 5.0, "adze": 4.0, "awl": 1.5, "needle": 0.5, "cleaver": 4.0, "quill": 0.3,
    "net": 3.0, "board": 1.0, "drying_rack": 2.0, "smoking_rack": 2.5, "churn": 3.0, "press": 8.0,
    "mash_tun": 8.0, "dye_vat": 6.0, "pot": 4.0, "pan": 3.0, "griddle": 3.5, "spit": 3.0, "oven": 20.0,
}
# scraps are priced as a cheap fraction of the food they were left from
for _kind, _spec in ITEMS.items():
    if _spec.get("scraps_of"):
        SCARCITY.setdefault(_kind, round(SCARCITY.get(_spec["scraps_of"], 1.0) * SCRAP_SCARCITY_FACTOR, 4))


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
LABOUR_RATE = 0.02   # reference value per MINUTE of labour (an hour of work ~ 1.2 in coin units)


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
TRAIN_HEADROOM = 0.40   # training can add up to 40% OVER your base -- the ceiling, relative to base (APPROX)
TRAIN_RATE = 0.12       # per-session fraction of the remaining gap closed -- a SLOW build (APPROX)


def train_ceiling(base):
    """The trained-component ceiling, RELATIVE TO base: use can build up to TRAIN_HEADROOM over base."""
    return float(base) * TRAIN_HEADROOM


def train_gain(base, trained):
    """Diminishing-returns increment to the trained component from ONE session -- a slow approach to the
    base-relative ceiling. Anchored to base: a higher base has a higher ceiling and larger absolute gains.
    (Mirrors the graph rule bd_train_* so a test can check the model; the agent's growth is the RULE.)"""
    return float(TRAIN_RATE * max(0.0, train_ceiling(base) - float(trained)))


def effective_stat(base, trained, health):
    """The body's EFFECTIVE strength/stamina: the (base + trained) potential SCALED by health -- a sick or
    injured body is weaker. Health 1.0 -> full potential; lower health -> proportionally less. (Mirrors the
    graph rule bd_effective_stats.)"""
    return float((float(base) + float(trained)) * float(health))


# A recipe's PHYSICAL demand: (strength REQUIREMENT, stamina COST), in the body's normalized stat units
# (an average untrained body is ~1.0). A heavy trade DEMANDS strength you must HAVE to do it at all (a gate
# -- you cannot swing the plough-hammer if you're not strong enough), and it COSTS stamina you must SPEND
# (depleting your reserve; rest restores it). Light trades (sewing, baking, ink) are 0/0 -- no barrier.
# The heaviest (plough, wagon) sit ABOVE an average body, so only a strong or trained smith can do them.
RECIPE_EXERTION = {
    # heavy forge work -- above an average body: must train/be strong (str_req > 1.0)
    "forge_plough": (1.20, 0.40), "forge_scythe": (1.10, 0.35), "make_wagon": (1.20, 0.40),
    "make_cart": (1.05, 0.35), "raise_barrel": (1.00, 0.30),
    # demanding but within an average body's reach (str_req <= 1.0, modest cost)
    "smelt_iron": (0.90, 0.15), "forge_knife": (0.90, 0.15), "forge_nails": (0.90, 0.15),
    "forge_pick_head": (0.90, 0.15), "make_bed": (0.95, 0.20), "make_table": (0.95, 0.20),
    "rive_staves": (0.85, 0.15), "burn_charcoal": (0.80, 0.20), "saw_planks": (0.85, 0.15),
    # open household work: a frail body cannot split logs or dig a compost heap
    "split_firewood": (0.75, 0.20), "make_compost": (0.60, 0.15), "dig_ore": (0.90, 0.25),
    "lift_saplings": (0.50, 0.10),
}


def recipe_exertion(name):
    """(strength_req, stamina_cost) for a recipe -- heavy trades demand strength AND tire you; light 0/0."""
    return RECIPE_EXERTION.get(name, (0.0, 0.0))


# Exertion also makes you HUNGRIER: the hunger gained per unit of stamina spent. Modest -- a heavy recipe
# (stamina_cost ~0.4) adds ~0.4 hunger against a meal that relieves ~5, so hard work needs more food over a
# day, not instantly. Raises the SAME hunger_level the sustenance drive reads; EATING (not buying) relieves it.
HUNGER_PER_STAMINA = 1.0


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
    best = (1.0 if spec.get("food") else 0.0) if tag == "food" else float(spec.get(tag, 0.0) or 0.0)
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


def _balance_flows(sc):
    """Per-period supply and demand of a town's coupled flows under scenario `sc` (see
    population.BALANCE_SCENARIO). Returns (flows, notes, work): work is {stream: minutes per period}."""
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
    flows["food (upper bound)"] = (food_supply, food_demand)
    notes.append(f"food: harvest could make {food_supply:.1f} food units/period by the best recipes "
                 f"(an upper bound; {staple_supply:.1f} of it from grain)")

    # fuel: the staple burns fuel; straw and the lumber deposit (split into firewood) supply it
    fuel_demand = sum(batches * sum(float(q) for k, q in next(r for r in RECIPES if r["name"] == n)["in"]
                                    if k == "fuel") for n, batches in chain.items())
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
    return flows, notes, work
