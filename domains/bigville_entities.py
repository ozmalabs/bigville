"""bigville_entities.py -- THE SINGLE SOURCE OF TRUTH for bigville world entities, as PURE DATA.

No game logic lives here -- only the entities and how they combine. The generic rules (the seeds:
ax_do recipe engine, ct_*/ck_* containers, cp_* physical piles) are the LOGIC; this file is the
DATA. Adding a new tool, material, container, building, or recipe -- including one combined from
different things or that works like an existing one -- is a DATA EDIT here, with no code change.

Commodities are PHYSICAL (piles/stock), never store floats: a material's quantity lives on a
first-class Stock node, made by a conserved recipe and consumed by use.
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

# The map/cast uses plain-language occupations while the craft catalogue uses production trades.
# These bridges preserve the resident's public occupation and seed the corresponding capabilities.
CAST_ROLE_TRADES = {
    "carpenter": ("woodworker",),
    "farm_labourer": ("farmer",),
    "farmer": ("farmer", "cook"),
    "fishmonger": ("fisher",),
    "forester": ("forester", "collier"),
}

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

HOUSEHOLDS = {
    "farm_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["land", "livestock", "tools"]},
    "craft_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["workshop", "tools"]},
    "landless_household": {"members": ["adult", "child", "elder"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["labour"]},
    "institutional_household": {"members": ["adult", "child"], "needs": ["food", "water", "fuel", "shelter"], "assets": ["office", "records"]},
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

GOVERNANCE_OFFICES = {
    "mayor": {"authority": "executive", "records": True, "appoints": ["constable", "clerk"]},
    "constable": {"authority": "enforcement", "records": True, "protects": ["people", "property"]},
    "clerk": {"authority": "records", "records": True, "maintains": ["taxes", "land", "laws"]},
    "councillor": {"authority": "deliberative", "records": False, "decides": ["commons", "works", "emergency"]},
    "midwife": {"authority": "care", "records": True, "supports": ["birth", "infant", "mother"]},
    "doctor": {"authority": "care", "records": True, "supports": ["injury", "disease"]},
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
# RAW-MATERIAL SCARCITY -- what the raw stuff costs (a fact a seller knows)
# ---------------------------------------------------------------------------
# How rare/costly a unit of a RAW material is to OBTAIN: for an IMPORTED good this is the exogenous
# price bigville pays the outside world; for a gathered/farmed/mined/hunted one it is a rough rarity.
# It is one of the two things a seller reasons from (raw-material cost + their own time). Scale
# anchored on coin = 1.0: abundant local stuff << 1; imported luxuries and spices >> 1.
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

# Starting literacy/capability by station in life (the world's defaults; any agent can be set higher).
STATION_EDUCATION = {
    "labouring": {"literacy": 0.15, "capability": 0.2},   # most of the village -- low literacy
    "middle":    {"literacy": 0.55, "capability": 0.5},   # functional: notes, the newspaper
    "educated":  {"literacy": 0.9,  "capability": 0.9},   # council laws, accounting
}


def literacy_tier(literacy):
    """Name the reading tier a literacy level sits in: labouring / functional / educated."""
    if float(literacy) >= LIT_EDUCATED:
        return "educated"
    if float(literacy) >= LIT_FUNCTIONAL:
        return "functional"
    return "labouring"


def scarcity(kind):
    """The general scarcity of a RAW material -- what its raw stuff costs to obtain (a per-item
    'scarcity' attr overrides the SCARCITY map; default 1.0). A fact a seller KNOWS."""
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
TRAIN_HEADROOM = 0.40   # training can add up to 40% OVER your base -- the ceiling, relative to base (APPROX)
TRAIN_RATE = 0.12       # per-session fraction of the remaining gap closed -- a SLOW build (APPROX)


def draw_physique(rng):
    """Draw a person's base strength + stamina: a shared general-fitness component plus an independent
    per-stat draw, floored. The variation IS the point -- a strong person and a weak one, a sprinter
    and an endurance type, all from one distribution."""
    g = float(rng.normal(0.0, PHYSIQUE["shared_sd"]))       # general fitness raises/lowers both together
    def one():
        return float(max(PHYSIQUE["floor"], PHYSIQUE["mean"] + g + rng.normal(0.0, PHYSIQUE["sd"])))
    return {"str_base": one(), "sta_base": one()}


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

PLAN_HORIZON = {"mean": 2.0, "sd": 1.2, "min": 1.0}   # days ahead an agent provisions (APPROX; heterogeneous)


def draw_plan_horizon(rng):
    """A person's planning horizon (days ahead they provision) -- a distributed trait. Some plan a week
    out; some live day-to-day. Floored at 1 (you always at least sort out today)."""
    return float(max(PLAN_HORIZON["min"], round(rng.normal(PLAN_HORIZON["mean"], PLAN_HORIZON["sd"]))))


def larder_for_wealth(coin, *, per_coin=0.5, floor=1.0, cap=20.0):
    """The larder capacity a given wealth can afford -- storage scales with means (floored at 1: everyone
    can keep a little; capped). The poor hold ~1 day and buy daily; the rich buy in bulk and buffer. APPROX."""
    return float(min(cap, max(floor, per_coin * float(coin))))


# Exertion also makes you HUNGRIER: the hunger gained per unit of stamina spent. Modest -- a heavy recipe
# (stamina_cost ~0.4) adds ~0.4 hunger against a meal that relieves ~5, so hard work needs more food over a
# day, not instantly. Raises the SAME hunger_level the sustenance drive reads; EATING (not buying) relieves it.
HUNGER_PER_STAMINA = 1.0


# ---------------------------------------------------------------------------
# CONSISTENCY CHECK -- does the data hang together?
# ---------------------------------------------------------------------------
# A pure function over the tables above (no world, no engine). It reports three severities:
#   errors   -- a dangling reference: a table names a kind/recipe/trade/building that does not exist.
#   warnings -- a completeness gap: an item nothing produces, an item nothing uses, a recipe whose
#               inputs can never be obtained, a crop whose seed cannot be replaced, ...
#   info     -- facts worth knowing that are not defects (counts, construction-only trades, ...).
# Run `python3 domains/bigville_entities.py` for the printed report (exit status 1 on errors). It also
# prints analyse_systems(): the production DAG, item/system weights, and the per-period balance.
# Scope: this sees only the data. Behaviour that lives in world code (e.g. reading a newspaper, the
# butcher's slaughter list, set_coin) is invisible here, so a "never used" item may still be used there.

# Gives that are services an animal performs rather than goods it yields.
ANIMAL_SERVICES = frozenset({"labour", "herding", "ratting"})


def _item_sources():
    """kind -> sorted list of the ways it comes into existence (not counting recipes)."""
    src = {}

    def add(kind, how):
        src.setdefault(kind, set()).add(how)

    for kind, spec in ITEMS.items():
        if spec.get("imported"):
            add(kind, "import")
        if spec.get("scraps_of"):
            add(kind, f"eating {spec['scraps_of']}")
    for crop, spec in CROPS.items():
        add(spec["harvest"], f"crop {crop}")
        for kind in spec.get("byproducts", {}):
            add(kind, f"byproduct of {crop}")
        if float(spec.get("seed_return", 1.0)) > 0.0:
            add(spec["seed"], f"harvest of {crop}")
    for species, spec in ANIMALS.items():
        for product in spec.get("gives", {}):
            add(product, f"animal {species}")
        if float(spec.get("manure", 0.0)) > 0.0:
            add("manure", f"animal {species}")
    for r in RECIPES:
        for kind in r.get("byproducts", {}):
            add(kind, f"byproduct of {r['name']}")
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for left in INPUT_TYPES[kind].get("byproducts", {}):
                    add(left, f"burning {kind} in {r['name']}")
    for kind in STARTING_STOCK:
        add(kind, "starting stock")
    for kind in RESOURCE_DEPOSITS:
        add(kind, "deposit")
    for trade, chain in SHOP_CHAINS.items():
        add(chain["out"], f"shop {trade}")
    for kind in PASTURE_YIELDS:
        add(kind, "pasture")
    for name, spec in FUEL_SOURCES.items():
        add(spec["fuel"], f"fuel source {name}")
    if WATER_SOURCES:
        add("water", "water source")
    for name, spec in WASTE_CYCLES.items():
        add(spec["output"], f"waste cycle {name}")
    add("coin", "currency")
    return src


def _item_uses():
    """kind -> set of the ways it is consumed or used."""
    use = {}

    def add(kind, how):
        use.setdefault(kind, set()).add(how)

    for r in RECIPES:
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for member, _units in type_members(kind):
                    add(member, f"{kind} for {r['name']}")
            else:
                add(kind, f"input to {r['name']}")
        for tool in r.get("tools", []) + r.get("method_tools", []):
            add(tool, f"tool for {r['name']}")
    for member, _units in type_members(NITROGEN["fertiliser_type"]):
        add(member, "spread on fields (fertilise)")
    for name, spec in FENCE_TYPES.items():
        add(spec["material"], f"builds {name}")
    for trade, spec in TRADES.items():
        for tool in spec.get("tools", []):
            add(tool, f"tool of {trade}")
    for species, spec in ANIMALS.items():
        for kind in feed_kinds(spec.get("eats", "")):
            add(kind, f"feed for {species}")
    for crop, spec in CROPS.items():
        add(spec["seed"], f"sown for {crop}")
    for name, spec in BUILDING_PROJECTS.items():
        for kind in spec.get("inputs", {}):
            add(kind, f"builds {name}")
    for name, spec in INFRASTRUCTURE.items():
        for kind in spec.get("maintenance", []):
            add(kind, f"maintains {name}")
    for trade, chain in SHOP_CHAINS.items():
        add(chain["in"], f"shop {trade}")
        add(chain["out"], f"sold by {trade}")
    for name, spec in LABOUR_TASKS.items():
        for kind in spec.get("inputs", []):
            if kind in ITEMS:
                add(kind, f"labour task {name}")
    for name, spec in FUEL_SOURCES.items():
        add(spec["fuel"], "fuel")
    for kind in SERVING_EQUIPMENT:
        add(kind, "serving equipment")
    for spec in SERVING_UTENSILS.values():
        for kind in spec["alternatives"]:
            add(kind, "serving utensil")
    for spec in CONTAINERS.values():
        for kind in spec.get("alternatives", []):
            add(kind, "serving vessel")
    for kind, spec in ITEMS.items():
        if spec.get("food"):
            add(kind, "eaten")
        if spec.get("garment"):
            add(kind, "worn")
        if spec.get("container"):
            add(kind, "holds goods")
        if spec.get("class") in ("tool", "good", "furniture") and spec.get("verb"):
            add(kind, f"used to {spec['verb']}")
        if spec.get("class") == "component":
            add(kind, f"part of {spec.get('for')}")
        if spec.get("readable"):
            add(kind, "read")
    add("coin", "currency")
    return use


def check_consistency():
    """Check every cross-reference and production pipeline in the entity data.

    Returns ``{"errors": [...], "warnings": [...], "info": [...], "stats": {...}}``. Each message is
    a plain string naming the table and the offending entry.
    """
    errors, warnings, info = [], [], []
    items = set(ITEMS)
    recipes = {r["name"]: r for r in RECIPES}
    known_places = set(BUILDINGS)

    def ref(kind, where):
        if kind not in items:
            errors.append(f"{where}: '{kind}' is not an item")

    # -- recipes ----------------------------------------------------------------
    seen = set()
    for r in RECIPES:
        name = r["name"]
        if name in seen:
            errors.append(f"RECIPES: duplicate recipe name '{name}'")
        seen.add(name)
        if r.get("requires") not in TRADES:
            errors.append(f"RECIPES[{name}]: requires unknown trade '{r.get('requires')}'")
        for kind, qty in r["in"]:
            if is_input_type(kind):
                if not type_members(kind):
                    errors.append(f"RECIPES[{name}].in: type slot '{kind}' has no member items")
            else:
                ref(kind, f"RECIPES[{name}].in")
            if float(qty) <= 0:
                errors.append(f"RECIPES[{name}].in: non-positive quantity for '{kind}'")
        ref(r["out"][0], f"RECIPES[{name}].out")
        if float(r["out"][1]) <= 0:
            errors.append(f"RECIPES[{name}].out: non-positive quantity")
        for tool in r.get("tools", []):
            ref(tool, f"RECIPES[{name}].tools")
        for tool in r.get("method_tools", []):
            if tool not in items and tool not in PREPARATION_EQUIPMENT:
                errors.append(f"RECIPES[{name}].method_tools: '{tool}' is neither an item nor equipment")
        hard_equipment = sorted(set(r.get("tools", [])) & set(PREPARATION_EQUIPMENT))
        if hard_equipment and name not in HEATED_FOOD_RECIPES and ITEMS.get(r["out"][0], {}).get("food"):
            warnings.append(f"RECIPES[{name}]: hard-requires cooking equipment {hard_equipment} but is not "
                            f"in HEATED_FOOD_RECIPES (so any heat+containment method is not accepted)")
        if r["out"][0] in [k for k, _ in r["in"]]:
            warnings.append(f"RECIPES[{name}]: output '{r['out'][0]}' is also an input")
        for season in r.get("seasons", []):
            if season not in SEASONS:
                errors.append(f"RECIPES[{name}].seasons: unknown season '{season}'")
        for kind in r.get("byproducts", {}):
            ref(kind, f"RECIPES[{name}].byproducts")
        if not r["in"] and not r.get("gathered_from"):
            warnings.append(f"RECIPES[{name}]: has no inputs but does not say where it is gathered_from")
    for type_name, spec in INPUT_TYPES.items():
        if type_name in items:
            errors.append(f"INPUT_TYPES[{type_name}]: type name collides with an item")
        for kind in spec.get("byproducts", {}):
            ref(kind, f"INPUT_TYPES[{type_name}].byproducts")
    for table, keys in (("MIN_SKILL", MIN_SKILL), ("RECIPE_EXERTION", RECIPE_EXERTION),
                        ("HEATED_FOOD_RECIPES", HEATED_FOOD_RECIPES)):
        for name in keys:
            if name not in recipes:
                errors.append(f"{table}: '{name}' is not a recipe")

    # -- items ------------------------------------------------------------------
    for kind, spec in ITEMS.items():
        if spec.get("class") == "component":
            if spec.get("for") not in items:
                errors.append(f"ITEMS[{kind}]: component for unknown item '{spec.get('for')}'")
        if spec.get("scraps_of") and spec["scraps_of"] not in items:
            errors.append(f"ITEMS[{kind}]: scraps of unknown item '{spec['scraps_of']}'")
        if kind.endswith("_seed") and not spec.get("seed"):
            warnings.append(f"ITEMS[{kind}]: looks like a seed but lacks seed: True")
        if spec.get("seed") and not any(c["seed"] == kind for c in CROPS.values()):
            warnings.append(f"ITEMS[{kind}]: seed for no crop")
        if spec.get("container") and float(spec.get("capacity", 0.0)) <= 0:
            errors.append(f"ITEMS[{kind}]: container without a positive capacity")
    for kind in SCARCITY:
        ref(kind, "SCARCITY")
    for kind in STARTING_STOCK:
        ref(kind, "STARTING_STOCK")

    # -- containers and food service --------------------------------------------
    for name, spec in CONTAINERS.items():
        for kind in spec.get("preferred_contents", []):
            ref(kind, f"CONTAINERS[{name}].preferred_contents")
        for kind in spec.get("alternatives", []):
            ref(kind, f"CONTAINERS[{name}].alternatives")
        if name in ITEMS and ITEMS[name].get("capacity") not in (None, spec.get("capacity")):
            errors.append(f"CONTAINERS[{name}]: capacity {spec.get('capacity')} disagrees with "
                          f"ITEMS[{name}] capacity {ITEMS[name].get('capacity')}")
    for name, spec in SERVING_UTENSILS.items():
        for kind in spec["alternatives"]:
            ref(kind, f"SERVING_UTENSILS[{name}]")
    for kind in SERVING_EQUIPMENT:
        ref(kind, "SERVING_EQUIPMENT")
    for kind in sorted(SOUP_FOODS | DRINK_FOODS):
        ref(kind, "SOUP_FOODS/DRINK_FOODS")
        if kind in items and not ITEMS[kind].get("food"):
            errors.append(f"SOUP_FOODS/DRINK_FOODS: '{kind}' is served as food but ITEMS[{kind}] lacks food: True")
    for name, spec in PREPARATION_METHODS.items():
        for eq in spec["equipment"]:
            if eq not in PREPARATION_EQUIPMENT:
                errors.append(f"PREPARATION_METHODS[{name}]: unknown equipment '{eq}'")

    # -- trades, buildings, construction ----------------------------------------
    for trade, spec in TRADES.items():
        building = spec.get("building")
        if building is None:
            if not spec.get("site"):
                errors.append(f"TRADES[{trade}]: no building and no site")
        elif building not in known_places:
            errors.append(f"TRADES[{trade}]: unknown building '{building}'")
        elif not BUILDINGS[building].get("founding", True):
            info.append(f"TRADES[{trade}]: works at '{building}', which must be built first")
        for tool in spec.get("tools", []):
            ref(tool, f"TRADES[{trade}].tools")
    for role, trades in CAST_ROLE_TRADES.items():
        for trade in trades:
            if trade not in TRADES:
                errors.append(f"CAST_ROLE_TRADES[{role}]: unknown trade '{trade}'")
    for name, spec in BUILDING_PROJECTS.items():
        if spec.get("building") not in known_places:
            errors.append(f"BUILDING_PROJECTS[{name}]: unknown building '{spec.get('building')}'")
        for kind in spec.get("inputs", {}):
            ref(kind, f"BUILDING_PROJECTS[{name}].inputs")
    for name, spec in INFRASTRUCTURE.items():
        for kind in spec.get("maintenance", []):
            ref(kind, f"INFRASTRUCTURE[{name}].maintenance")
    for name, spec in BUILDINGS.items():
        if not spec.get("founding", True) and not any(
                p.get("building") == name for p in BUILDING_PROJECTS.values()):
            warnings.append(f"BUILDINGS[{name}]: not standing at founding and no BUILDING_PROJECT raises it")
    trades_with_recipes = {r["requires"] for r in RECIPES}
    service = sorted(t for t in TRADES if t not in trades_with_recipes)
    info.append(f"TRADES with no recipe (service or gathering work): {', '.join(service)}")
    for fixture in TOWN_SQUARE_FIXTURES:
        for kind in fixture.get("goods", []):
            if kind not in items:
                warnings.append(f"TOWN_SQUARE_FIXTURES[{fixture['name']}]: goods label '{kind}' is not an item")

    # -- animals, crops, land ----------------------------------------------------
    for species, spec in ANIMALS.items():
        for field in ("eats", "ration", "starve_limit", "matures", "lifespan", "role"):
            if field not in spec:
                errors.append(f"ANIMALS[{species}]: missing '{field}'")
        for product in spec.get("gives", {}):
            if product not in items and product not in ANIMAL_SERVICES:
                errors.append(f"ANIMALS[{species}].gives: '{product}' is neither an item nor a service")
        for kind in feed_kinds(spec.get("eats", "")):
            ref(kind, f"ANIMALS[{species}].eats")
    for species in ANIMAL_NPC_SETUP:
        if species not in ANIMALS:
            errors.append(f"ANIMAL_NPC_SETUP: unknown species '{species}'")
    for task, spec in ANIMAL_HUSBANDRY.items():
        if spec["species"] not in ANIMALS:
            errors.append(f"ANIMAL_HUSBANDRY[{task}]: unknown species '{spec['species']}'")
        elif spec["product"] not in ANIMALS[spec["species"]].get("gives", {}):
            errors.append(f"ANIMAL_HUSBANDRY[{task}]: {spec['species']} does not give '{spec['product']}'")
    for crop, spec in CROPS.items():
        ref(spec["seed"], f"CROPS[{crop}].seed")
        ref(spec["harvest"], f"CROPS[{crop}].harvest")
        if spec.get("season") not in SEASONS:
            errors.append(f"CROPS[{crop}]: unknown season '{spec.get('season')}'")
        for kind in spec.get("byproducts", {}):
            ref(kind, f"CROPS[{crop}].byproducts")
        if "nitrogen" not in spec:
            warnings.append(f"CROPS[{crop}]: no nitrogen demand -- it never draws on the soil")
    for crop in STARTING_CROPS:
        if crop not in CROPS:
            errors.append(f"STARTING_CROPS: unknown crop '{crop}'")
    for group, crops in ARABLE_ROTATION.items():
        for crop in crops:
            if crop not in CROPS:
                errors.append(f"ARABLE_ROTATION[{group}]: unknown crop '{crop}'")
            elif group == "restorative" and float(CROPS[crop].get("fixes", 0.0)) <= 0.0:
                errors.append(f"ARABLE_ROTATION[restorative]: '{crop}' does not fix nitrogen")
    for soil, spec in SOILS.items():
        if "nitrogen" not in spec:
            errors.append(f"SOILS[{soil}]: no starting nitrogen")
    if NITROGEN["fertiliser_type"] not in INPUT_TYPES:
        errors.append(f"NITROGEN: fertiliser_type '{NITROGEN['fertiliser_type']}' is not an INPUT_TYPE")
    for kind in SLAUGHTER_PRODUCTS:
        ref(kind, "SLAUGHTER_PRODUCTS")
    _flows, _notes, streams = _balance_flows()
    covered = {}
    for job, spec in JOBS.items():
        for trade in spec["trades"]:
            if trade not in TRADES:
                errors.append(f"JOBS[{job}]: unknown trade '{trade}'")
        for tool in spec.get("tools", []):
            ref(tool, f"JOBS[{job}].tools")
        for stream, share in spec.get("duties", {}).items():
            if stream not in streams:
                errors.append(f"JOBS[{job}].duties: unknown work stream '{stream}'")
            covered[stream] = covered.get(stream, 0.0) + float(share)
    for stream in streams:
        if abs(covered.get(stream, 0.0) - 1.0) > 1e-6:
            errors.append(f"JOBS: work stream '{stream}' is {covered.get(stream, 0.0):.0%} covered by job duties")
    if sum(1 for spec in JOBS.values() if spec.get("spare")) != 1:
        errors.append("JOBS: exactly one job must take the spare residents (spare: True)")
    open_recipes = sorted(r["name"] for r in RECIPES if r.get("open"))
    info.append(f"open recipes (anyone capable with the tools): {', '.join(open_recipes)}")
    for name, spec in WASTE_CYCLES.items():
        ref(spec["output"], f"WASTE_CYCLES[{name}].output")
        if spec["treatment"] not in BUILDINGS and spec["treatment"] not in INFRASTRUCTURE:
            errors.append(f"WASTE_CYCLES[{name}]: unknown treatment place '{spec['treatment']}'")
    for kind in PASTURE_YIELDS:
        ref(kind, "PASTURE_YIELDS")
    for name, spec in FENCE_TYPES.items():
        if spec["material"] not in items:
            warnings.append(f"FENCE_TYPES[{name}]: material '{spec['material']}' is not an item")
    for name, spec in ENCLOSURE_TYPES.items():
        if spec["fence"] not in FENCE_TYPES:
            errors.append(f"ENCLOSURE_TYPES[{name}]: unknown fence '{spec['fence']}'")
    for kind in RESOURCE_DEPOSITS:
        ref(kind, "RESOURCE_DEPOSITS")
    for trade, chain in SHOP_CHAINS.items():
        ref(chain["in"], f"SHOP_CHAINS[{trade}].in")
        ref(chain["out"], f"SHOP_CHAINS[{trade}].out")
    for name, spec in FUEL_SOURCES.items():
        ref(spec["fuel"], f"FUEL_SOURCES[{name}]")
    for name, spec in SEASONS.items():
        for w in spec["weather"]:
            if w not in WEATHER:
                errors.append(f"SEASONS[{name}]: unknown weather '{w}'")

    # -- pipelines: sources, sinks, reachability ---------------------------------
    sources = _item_sources()
    made_by = {}
    for r in RECIPES:
        made_by.setdefault(r["out"][0], []).append(r["name"])
    uses = _item_uses()
    no_source = sorted(k for k in items if k not in sources and k not in made_by
                       and ITEMS[k].get("class") == "material")
    for kind in no_source:
        warnings.append(f"PIPELINE no source: '{kind}' (no recipe, crop, animal, deposit, import, "
                        f"or starting stock)")
    not_made = sorted(k for k in items if k not in sources and k not in made_by
                      and ITEMS[k].get("class") != "material")
    founding_tools = {t for r in RECIPES for t in r.get("tools", [])}
    for kind in not_made:
        if kind in founding_tools:
            warnings.append(f"PIPELINE cannot be made: {ITEMS[kind].get('class')} '{kind}' "
                            f"(one is provided at founding; it cannot be replaced)")
        else:
            warnings.append(f"PIPELINE cannot be made: {ITEMS[kind].get('class')} '{kind}' "
                            f"(not made, imported, or provided)")
    for kind in sorted(items - set(uses)):
        warnings.append(f"PIPELINE never used: '{kind}'")

    # Which recipes can run without someone stocking their inputs by hand (a test or scenario
    # set_stock)? Start from everything with a non-recipe source, plus the tools the
    # world provides at founding, then repeatedly add the outputs of recipes whose inputs are all
    # obtainable, until nothing changes.
    obtainable = set(sources) | founding_tools

    def can_get(kind):
        if is_input_type(kind):
            return any(member in obtainable for member, _ in type_members(kind))
        return kind in obtainable

    runnable = set()
    changed = True
    while changed:
        changed = False
        for r in RECIPES:
            if r["name"] in runnable:
                continue
            if all(can_get(k) for k, _ in r["in"]):
                runnable.add(r["name"])
                obtainable.add(r["out"][0])
                changed = True
    for r in RECIPES:
        if r["name"] not in runnable:
            missing = sorted(k for k, _ in r["in"] if not can_get(k))
            warnings.append(f"PIPELINE recipe unreachable from natural sources: '{r['name']}' -- "
                            f"no source for {', '.join(missing)}")

    # Seeds: a crop is only sustainable if its seed can be replaced after the first sowing.
    # Its own harvest cannot supply the first sowing, so a crop also needs some other first source.
    for crop, spec in CROPS.items():
        seed_src = sources.get(spec["seed"], set()) | ({"recipe"} if spec["seed"] in made_by else set())
        first = seed_src - {f"harvest of {crop}"}
        if not first:
            warnings.append(f"PIPELINE crop: '{crop}' can never be sown -- no first source of '{spec['seed']}'")
        if float(spec.get("seed_return", 1.0)) <= 0.0:
            warnings.append(f"PIPELINE crop: '{crop}' is not renewable -- its harvest returns no '{spec['seed']}'")

    stats = {
        "items": len(items), "recipes": len(RECIPES), "runnable_recipes": len(runnable),
        "buildings": len(BUILDINGS), "founding_buildings": len(founding_buildings()),
        "trades": len(TRADES), "crops": len(CROPS), "animals": len(ANIMALS),
        "containers": len(CONTAINERS),
        "items_by_class": {c: sum(1 for s in ITEMS.values() if s.get("class") == c)
                           for c in sorted({s.get("class", "?") for s in ITEMS.values()})},
    }
    return {"errors": errors, "warnings": warnings, "info": info, "stats": stats}


# ---------------------------------------------------------------------------
# PRODUCTION GRAPH, SYSTEMS, AND BALANCE
# ---------------------------------------------------------------------------
# The production graph links every item to the recipes and natural processes (crops, animals,
# deposits, imports, residents, fertilising) that consume and make it. Its cycles (seed -> crop ->
# seed, the nitrogen loop, tools that make tools) are collapsed into strongly connected components,
# leaving a DAG whose depth ("tier") says how many production steps an item sits above raw nature.
# The balance model runs the founding town's per-period flows (BALANCE_SCENARIO) through that graph
# and flags systems that cannot sustain themselves.

# Which economic system each trade's recipes belong to (used for the system weights and coupling).
SYSTEM_OF_TRADE = {
    "farmer": "agriculture", "forester": "forestry", "collier": "fuel",
    "sawyer": "timber", "woodworker": "timber", "cooper": "timber",
    "smith": "metal", "quarrier": "stone", "mason": "stone",
    "miller": "food", "baker": "food", "cook": "food", "dairymaid": "food", "butcher": "food",
    "brewer": "drink", "tanner": "textiles", "cobbler": "textiles", "weaver": "textiles",
    "tailor": "textiles", "dyer": "textiles", "papermaker": "writing", "printer": "writing",
    "inkmaker": "writing", "scribe": "writing", "chandler": "household",
}

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

_PSEUDO = {"soil_nitrogen", "food"}           # graph nodes that are not items


def _processes():
    """Natural and institutional flows, as recipe-shaped rows: {name, system, in, out}."""
    procs = []
    for crop, spec in CROPS.items():
        outs = [[spec["harvest"], spec["yield"]]] + [[k, q] for k, q in spec.get("byproducts", {}).items()]
        outs.append([spec["seed"], float(spec.get("seed_return", 1.0))])
        ins = [[spec["seed"], 1]]
        grow = float(spec["grow_periods"])
        if spec.get("nitrogen"):
            ins.append(["soil_nitrogen", float(spec["nitrogen"]) * grow])
        if spec.get("fixes"):
            outs.append(["soil_nitrogen", float(spec["fixes"]) * grow])
        procs.append({"name": f"crop:{crop}", "system": "agriculture", "in": ins, "out": outs})
    for species, spec in ANIMALS.items():
        outs = [[k, q] for k, q in spec.get("gives", {}).items() if k in ITEMS]
        if spec.get("manure"):
            outs.append(["manure", spec["manure"]])
        procs.append({"name": f"animal:{species}", "system": "husbandry",
                      "in": [[k, spec.get("ration", 1)] for k in feed_kinds(spec["eats"])[:1]], "out": outs})
    for kind, spec in RESOURCE_DEPOSITS.items():
        procs.append({"name": f"deposit:{kind}", "system": "extraction", "in": [], "out": [[kind, spec["growback"]]]})
    for kind, spec in PASTURE_YIELDS.items():
        procs.append({"name": f"pasture:{kind}", "system": "husbandry", "in": [], "out": [[kind, spec]]})
    for kind, spec in ITEMS.items():
        if spec.get("imported"):
            procs.append({"name": f"import:{kind}", "system": "trade", "in": [["coin", scarcity(kind)]], "out": [[kind, 1]]})
    procs.append({"name": "residents", "system": "household", "in": [["food", 1]],
                  "out": [[WASTE_CYCLES["human_waste"]["output"], WASTE_CYCLES["human_waste"]["per_resident"]]]})
    procs.append({"name": "fertilise", "system": "agriculture",
                  "in": [[NITROGEN["fertiliser_type"], 1]], "out": [["soil_nitrogen", 1]]})
    return procs


def build_production_graph():
    """{node: set(successors)} over item/type/recipe/process nodes, plus each node's kind label."""
    succ, kind_of = {}, {}

    def node(name, label):
        succ.setdefault(name, set())
        kind_of[name] = label
        return name

    def item_node(kind):
        if is_input_type(kind):
            t = node(f"type:{kind}", "type")
            for member, _ in type_members(kind):
                succ[node(f"item:{member}", "item")].add(t)
            return t
        if kind == "food":
            t = node("type:food", "type")
            for k, s in ITEMS.items():
                if s.get("food"):
                    succ[node(f"item:{k}", "item")].add(t)
            return t
        return node(f"item:{kind}", "pseudo" if kind in _PSEUDO else "item")

    # recipe rows carry one [kind, qty] output; normalise to the process shape (a list of outputs)
    rows = [dict(r, system=SYSTEM_OF_TRADE.get(r["requires"], "other"), name=f"recipe:{r['name']}",
                 out=[r["out"]] + [[k, q] for k, q in r.get("byproducts", {}).items()])
            for r in RECIPES] + _processes()
    for r in rows:
        step = node(r["name"], "recipe" if r["name"].startswith("recipe:") else "process")
        for kind, _ in r["in"]:
            succ[item_node(kind)].add(step)
        for kind, _ in r["out"]:
            succ[step].add(item_node(kind))
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for left in INPUT_TYPES[kind].get("byproducts", {}):
                    succ[step].add(item_node(left))
    return succ, kind_of, rows


def _strongly_connected(succ):
    """Tarjan's algorithm (iterative). Returns a list of components (sets of nodes)."""
    index, low, on, stack, comps, counter = {}, {}, set(), [], [], [0]
    for root in sorted(succ):
        if root in index:
            continue
        work = [(root, iter(sorted(succ[root])))]
        index[root] = low[root] = counter[0]; counter[0] += 1
        stack.append(root); on.add(root)
        while work:
            v, children = work[-1]
            advanced = False
            for w in children:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1
                    stack.append(w); on.add(w)
                    work.append((w, iter(sorted(succ.get(w, ())))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = set()
                while True:
                    w = stack.pop(); on.discard(w); comp.add(w)
                    if w == v:
                        break
                comps.append(comp)
    return comps


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


def _balance_flows(sc=None):
    """Per-period supply and demand of the town's coupled flows under a scenario (default
    BALANCE_SCENARIO). Returns (flows, notes, work) where work is {stream: minutes per period}."""
    sc = sc or BALANCE_SCENARIO
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


def analyse_systems():
    """Build the production DAG, weigh items and systems, and find balance issues.

    Returns {"graph": {...}, "loops": [...], "deepest": [...], "keystones": [...],
             "systems": {...}, "coupling": [...], "flows": {...}, "issues": [...], "notes": [...]}."""
    succ, kind_of, rows = build_production_graph()
    comps = _strongly_connected(succ)
    comp_of = {n: i for i, c in enumerate(comps) for n in c}
    dag = {i: set() for i in range(len(comps))}
    for v, ws in succ.items():
        for w in ws:
            if comp_of[v] != comp_of[w]:
                dag[comp_of[v]].add(comp_of[w])
    preds = {i: set() for i in dag}
    for v, ws in dag.items():
        for w in ws:
            preds[w].add(v)
    # tier = longest path from a source component (Kahn order)
    tier, order, indeg = {}, [], {i: len(preds[i]) for i in dag}
    ready = sorted(i for i, d in indeg.items() if d == 0)
    while ready:
        v = ready.pop(0); order.append(v)
        tier[v] = max((tier[p] + 1 for p in preds[v]), default=0)
        for w in sorted(dag[v]):
            indeg[w] -= 1
            if indeg[w] == 0:
                ready.append(w)
    acyclic = len(order) == len(dag)

    def items_in(comp):
        return sorted(n.split(":", 1)[1] for n in comp if kind_of[n] in ("item", "pseudo"))

    loops = []
    for i, c in enumerate(comps):
        if len(c) > 1:
            members = items_in(c)
            steps = sorted(n for n in c if kind_of[n] in ("recipe", "process"))
            loops.append({"items": members, "steps": len(steps), "size": len(c), "component": i})
    loops.sort(key=lambda l: -l["size"])
    loop_label = {l["component"]: f"[loop {n + 1}: {len(l['items'])} items]" for n, l in enumerate(loops)}

    def label(c):
        if c in loop_label:
            return loop_label[c]
        names = items_in(comps[c])
        return names[0] if names else None

    # depth: items ranked by tier, with one longest chain back to a source
    item_tier = {n.split(":", 1)[1]: tier[comp_of[n]] for n in succ if kind_of[n] == "item"}
    deepest = []
    for kind in sorted(item_tier, key=lambda k: (-item_tier[k], k))[:5]:
        c = comp_of[f"item:{kind}"]
        chain = [label(c)]
        while preds[c]:
            c = max(preds[c], key=lambda p: (tier[p], -p))
            name = label(c)
            if name and name != chain[-1]:
                chain.append(name)
        deepest.append({"item": kind, "tier": item_tier[kind], "chain": list(reversed(chain))})

    # keystones: how many recipes become unreachable if one item vanished from the world
    sources = _item_sources()
    base = set(sources) | {t for r in RECIPES for t in r.get("tools", [])}

    def reachable(removed):
        have = set(base) - {removed}
        ran, changed = set(), True
        while changed:
            changed = False
            for r in RECIPES:
                if r["name"] in ran or r["out"][0] == removed:
                    continue
                if all((any(m in have for m, _ in type_members(k)) if is_input_type(k) else k in have)
                       for k, _ in r["in"]):
                    ran.add(r["name"]); have.add(r["out"][0]); changed = True
        return ran

    everything = reachable(None)
    keystones = []
    for kind in sorted(ITEMS):
        lost = len(everything) - len(reachable(kind))
        if lost:
            keystones.append((kind, lost))
    keystones.sort(key=lambda kv: (-kv[1], kv[0]))

    # systems: size, value made per batch, labour; and which systems feed which
    systems, producer_system = {}, {}
    for r in rows:
        if not r["name"].startswith("recipe:"):
            for k, _ in r["out"]:
                producer_system.setdefault(k, set()).add(r["system"])
    for r in RECIPES:
        sysname = SYSTEM_OF_TRADE.get(r["requires"], "other")
        s = systems.setdefault(sysname, {"recipes": 0, "value": 0.0, "labour": 0.0})
        s["recipes"] += 1
        s["value"] += reference_value(r["out"][0]) * float(r["out"][1])
        s["labour"] += float(r.get("time_minutes", 0.0))
        producer_system.setdefault(r["out"][0], set()).add(sysname)
    coupling = {}
    for r in RECIPES:
        sysname = SYSTEM_OF_TRADE.get(r["requires"], "other")
        for k, q in r["in"]:
            kinds = [m for m, _ in type_members(k)] if is_input_type(k) else [k]
            for kk in kinds[:1]:
                for src in producer_system.get(kk, ()):
                    if src != sysname:
                        weight = (reference_value(kk) * float(q)) if not is_input_type(k) else float(q)
                        coupling[(src, sysname)] = coupling.get((src, sysname), 0.0) + weight
    coupling = sorted(((a, b, round(w, 2)) for (a, b), w in coupling.items()), key=lambda t: -t[2])

    # balance issues
    flows, notes, _work = _balance_flows()
    issues = []
    for name, (supply, demand) in flows.items():
        if demand <= 0:
            continue
        ratio = supply / demand
        if ratio < 1.0:
            issues.append(f"DEFICIT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"({ratio:.0%} covered)")
        elif ratio < 1.15:
            issues.append(f"TIGHT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"(only {ratio - 1:.0%} margin)")
        elif ratio > 6.0 and name in ("fuel (heat)", "soil nitrogen", "water"):
            issues.append(f"GLUT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"({ratio:.1f}x -- the constraint may be too loose to matter)")
    for crop, spec in CROPS.items():
        if float(spec.get("seed_return", 1.0)) <= 1.0 and crop in BALANCE_SCENARIO["beds"]:
            issues.append(f"BREAK-EVEN seed for {crop}: a harvest returns {spec.get('seed_return', 1.0)} seed per "
                          f"seed sown, so every bed lost to wilting shrinks the seed stock for good")
    # recipes that cost much more than the cheapest way to make the same thing
    for r in RECIPES:
        out, oq = r["out"]
        per = _recipe_unit_cost(r)
        ref = reference_value(out)
        if ref > 0 and per > 1.5 * ref and len(_recipes_for(out)) > 1 and not r.get("fallback"):
            issues.append(f"DOMINATED recipe {r['name']}: {per:.2f}/unit vs {ref:.2f} by the cheapest recipe "
                          f"for {out}")
    for kind, spec in ITEMS.items():
        if spec.get("imported") and _recipes_for(kind):
            m, l = _value_parts(kind)
            if m + l * LABOUR_RATE < scarcity(kind) * 0.5:
                issues.append(f"IMPORT {kind}: making it locally ({m + l * LABOUR_RATE:.2f}) costs under half "
                              f"the import price ({scarcity(kind):.2f}) -- the import is unlikely to be used")
    return {"graph": {"nodes": len(succ), "edges": sum(len(v) for v in succ.values()),
                      "components": len(comps), "tiers": max(tier.values(), default=0) + 1,
                      "acyclic_after_condensing": acyclic},
            "loops": loops, "deepest": deepest, "keystones": keystones[:10],
            "systems": systems, "coupling": coupling[:12], "flows": flows,
            "issues": issues, "notes": notes}


def format_systems_report(analysis=None):
    """Render analyse_systems() as text."""
    a = analysis or analyse_systems()
    g = a["graph"]
    lines = ["PRODUCTION GRAPH",
             f"  {g['nodes']} nodes, {g['edges']} edges -> {g['components']} components; "
             f"{g['tiers']} tiers deep; acyclic after condensing loops: {g['acyclic_after_condensing']}",
             f"  loops ({len(a['loops'])}; a loop is a cycle such as seed -> crop -> seed):"]
    for loop in a["loops"][:6]:
        shown = ", ".join(loop["items"][:12]) + (" ..." if len(loop["items"]) > 12 else "")
        lines.append(f"    - {len(loop['items'])} items / {loop['steps']} steps: {shown}")
    if len(a["loops"]) > 6:
        lines.append(f"    - ... and {len(a['loops']) - 6} smaller loops")
    lines.append("  deepest items (tier: one chain from raw nature):")
    for d in a["deepest"]:
        lines.append(f"    - {d['item']} (tier {d['tier']}): {' -> '.join(d['chain'])}")
    lines.append("  keystone items (recipes that become unreachable without them):")
    lines.append("    " + ", ".join(f"{k} {n}" for k, n in a["keystones"]))
    lines += ["", "SYSTEMS (recipes, reference value made per batch, labour minutes per batch)"]
    total_v = sum(s["value"] for s in a["systems"].values()) or 1.0
    for name, s in sorted(a["systems"].items(), key=lambda kv: -kv[1]["value"]):
        lines.append(f"  {name:<12} {s['recipes']:>3} recipes  value {s['value']:>8.1f} "
                     f"({s['value'] / total_v:>4.0%})  labour {s['labour']:>6.0f}")
    lines.append("  strongest couplings (producer -> consumer: weight of inputs crossing):")
    for src, dst, w in a["coupling"]:
        lines.append(f"    {src} -> {dst}: {w}")
    lines += ["", "BALANCE (per period, BALANCE_SCENARIO)"]
    for name, (supply, demand) in a["flows"].items():
        ratio = supply / demand if demand else float("inf")
        lines.append(f"  {name:<18} supply {supply:>8.1f}  demand {demand:>8.1f}  ratio {ratio:>5.2f}")
    for note in a["notes"]:
        lines.append(f"  note: {note}")
    lines.append(f"  issues ({len(a['issues'])}):")
    lines.extend(f"    - {issue}" for issue in a["issues"]) if a["issues"] else lines.append("    none")
    return "\n".join(lines)


def format_consistency_report(report=None):
    """Render check_consistency() as readable text, warnings grouped by their table/area."""
    report = report or check_consistency()
    s = report["stats"]
    lines = ["bigville entities -- consistency report", "=" * 40,
             f"items {s['items']}  recipes {s['recipes']} ({s['runnable_recipes']} runnable)  "
             f"buildings {s['buildings']} ({s['founding_buildings']} at founding)  trades {s['trades']}",
             f"crops {s['crops']}  animals {s['animals']}  containers {s['containers']}",
             "items by class: " + ", ".join(f"{c} {n}" for c, n in s["items_by_class"].items()), ""]
    for title, key in (("ERRORS", "errors"), ("WARNINGS", "warnings"), ("INFO", "info")):
        msgs = report[key]
        lines.append(f"{title} ({len(msgs)})")
        groups = {}
        for m in msgs:
            groups.setdefault(m.split(":", 1)[0].split("[", 1)[0], []).append(m)
        for group in sorted(groups):
            lines.append(f"  {group} ({len(groups[group])})")
            for m in groups[group]:
                # pipeline groups name the problem; the entry is just the subject
                lines.append(f"    - {m.split(':', 1)[1].strip() if m.startswith('PIPELINE') else m}")
        if not msgs:
            lines.append("  none")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys as _sys
    _report = check_consistency()
    print(format_consistency_report(_report))
    print(format_systems_report(analyse_systems()))
    print()
    print(format_jobs_report())
    _sys.exit(1 if _report["errors"] else 0)