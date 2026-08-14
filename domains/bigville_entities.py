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
    "wood":     {"class": "material", "bulk": True},
    "timber":   {"class": "material", "bulk": True, "weight": 2.0, "volume": 3.0},  # bulky
    "log":      {"class": "material", "bulk": True},
    "ore":      {"class": "material", "bulk": True},
    "iron":     {"class": "material", "bulk": True, "weight": 3.0, "volume": 0.5},   # dense: heavy, small
    "charcoal": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0},
    "smoke":    {"class": "material", "bulk": True},   # the pyrolysis byproduct (conserved, not vanished)
    "grain":    {"class": "material", "bulk": True},
    "flour":    {"class": "material", "bulk": True},
    "coin":     {"class": "material", "bulk": True},
    # ecological cycles and maintenance materials
    "straw":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 2.0},
    "thatch":   {"class": "material", "bulk": True, "weight": 0.3, "volume": 2.0},
    "peat":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0},
    "dung":     {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0},
    "manure":   {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0},
    "compost":  {"class": "material", "bulk": True, "weight": 0.6, "volume": 1.0},
    "medicine": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2, "imported": True},
    "nectar":   {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "wax":      {"class": "material", "bulk": True, "weight": 0.8, "volume": 0.7},
    "wheat_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "barley_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "oats_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "rye_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "cabbage_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "carrot_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "onion_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "potato_seed": {"class": "material", "bulk": True, "weight": 0.3, "volume": 0.4},
    "turnip_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "bean_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "pea_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "leek_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "parsnip_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "beet_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "garlic_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "lettuce_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "cucumber_seed": {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2},
    "lentil_seed": {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
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
    "lard":     {"class": "material", "bulk": True, "weight": 1.0, "volume": 0.8, "food": True, "decay": 0.04},
    "vinegar":  {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "yeast":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.3},
    "sugar":    {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.8},
    "mustard":  {"class": "material", "bulk": True, "weight": 0.4, "volume": 0.4, "food": True},
    "mutton":  {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "fish":    {"class": "material", "bulk": True, "weight": 0.8, "volume": 1.0, "food": True},
    "bacon":   {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "decay": 0.03},
    "sausage": {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True, "decay": 0.04},
    "ham":     {"class": "material", "bulk": True, "weight": 1.2, "volume": 1.0, "food": True, "decay": 0.03},
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
    "newspaper": {"class": "material", "bulk": True, "material": "paper", "weight": 0.1, "volume": 0.2},
    "printing_press": {"class": "tool", "material": "metal", "verb": "print", "base_mult": 1.0, "wear_rate": 0.01, "make_minutes": 0, "make_effort": 0, "composite": False, "demand_driver": "general", "demand_weight": 0, "base_demand": 0},
    # --- crop seeds ---
    "wheat_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "barley_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "oats_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "rye_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "cabbage_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "carrot_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "onion_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "potato_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "turnip_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "bean_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "pea_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    "leek_seed": {"class": "material", "bulk": True, "seed": True, "weight": 0.1, "volume": 0.2},
    # --- trade materials (bulk) ---
    "hide":    {"class": "material", "bulk": True},
    "leather": {"class": "material", "bulk": True},
    "wool":    {"class": "material", "bulk": True},
    "thread":  {"class": "material", "bulk": True},
    "cloth":   {"class": "material", "bulk": True},
    "stave":   {"class": "material", "bulk": True},
    # --- fluids (need a watertight container) ---
    "water":   {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "ale":     {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "oil":     {"class": "material", "bulk": True, "fluid": True, "weight": 0.9, "volume": 1.0},
    "milk":    {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0, "food": True},
    # --- animal products + feed (bulk) ---
    "pork":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "beef":    {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0, "food": True},
    "poultry": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "food": True},
    "eggs":    {"class": "material", "bulk": True, "weight": 0.1, "volume": 0.2, "food": True},
    "hay":     {"class": "material", "bulk": True, "weight": 0.3, "volume": 3.0},
    "grass":   {"class": "material", "bulk": True, "weight": 0.2, "volume": 2.0},
    "scraps":  {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0},
    "rag":     {"class": "material", "bulk": True, "weight": 0.3, "volume": 1.0},
    "soot":    {"class": "material", "bulk": True, "weight": 0.2, "volume": 0.5},
    # --- imported goods (from OUTSIDE bigville -- acquired by trade, not made locally) ---
    "ink":    {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.5},
    "paper":  {"class": "material", "bulk": True, "imported": True, "weight": 0.2, "volume": 0.5},
    "dye":    {"class": "material", "bulk": True, "imported": True, "weight": 1.0, "volume": 0.5},
    "madder": {"class": "material", "bulk": True, "imported": True, "colour": "red",    "weight": 1.0, "volume": 0.5},
    "woad":   {"class": "material", "bulk": True, "imported": True, "colour": "blue",   "weight": 1.0, "volume": 0.5},
    "weld":   {"class": "material", "bulk": True, "imported": True, "colour": "yellow", "weight": 1.0, "volume": 0.5},
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
}

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
                    "preferred_contents": ["bread", "milk", "butter", "cheese", "cream", "fish", "meat"]},
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
    "make_pudding", "brew_ale", "brew_cider", "brew_mead",
})

# ---------------------------------------------------------------- RECIPES
# how things are made / combined: inputs -> output, with difficulty and make-time. `requires` is the
# trade/role. Inputs and tools are deliberately variable-length. Serving vessels and utensils belong
# to FOOD_SERVICE below: they are needed when food is consumed, not when the batch is cooked.
RECIPES = [
    {"name": "saw_planks",    "requires": "sawyer",     "in": [["log", 1]],                  "out": ["timber", 2],   "difficulty": 0.8, "time_minutes": 20},
    {"name": "burn_charcoal", "requires": "collier",    "in": [["wood", 4]],                 "out": ["charcoal", 1], "difficulty": 2.0, "time_minutes": 60},
    {"name": "smelt_iron",    "requires": "smith",      "in": [["ore", 2], ["charcoal", 1]], "out": ["iron", 1],     "difficulty": 3.0, "time_minutes": 90},
    {"name": "forge_nails",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]],"out": ["nails", 5],    "difficulty": 1.5, "time_minutes": 10, "tools": ["hammer"]},
    {"name": "forge_knife",   "requires": "smith",      "in": [["iron", 1], ["charcoal", 1]],"out": ["knife", 1],    "difficulty": 2.0, "time_minutes": 90, "tools": ["hammer"]},
    {"name": "carve_rake",    "requires": "woodworker", "in": [["timber", 1]],               "out": ["rake", 1],     "difficulty": 0.7, "time_minutes": 60},
    {"name": "grind_flour",   "requires": "miller",     "in": [["grain", 3]],                "out": ["flour", 2],    "difficulty": 1.0, "time_minutes": 30},
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
    {"name": "dye_cloth",    "requires": "dyer",       "in": [["cloth", 1], ["dye", 1]],    "out": ["coloured_cloth", 1], "difficulty": 1.0, "time_minutes": 120, "tools": ["dye_vat"]},
    # recipes that EXIST but are not COMMONLY KNOWN in bigville (common: False -> must be taught or read to be made here)
    {"name": "make_paper",   "requires": "papermaker", "in": [["rag", 3], ["water", 2]],    "out": ["paper", 5],   "difficulty": 2.0, "time_minutes": 240, "tools": ["press"], "common": False},
    {"name": "print_newspaper", "requires": "printer",   "in": [["paper", 1], ["ink", 1]],   "out": ["newspaper", 20], "difficulty": 1.2, "time_minutes": 60, "tools": ["printing_press"]},
    {"name": "make_sandwich", "requires": "cook",     "in": [["ham", 1], ["bread", 1]],   "out": ["sandwich", 1], "difficulty": 0.5, "time_minutes": 10},
    {"name": "make_ink",     "requires": "inkmaker",   "in": [["soot", 1], ["oil", 1]],     "out": ["ink", 3],     "difficulty": 1.5, "time_minutes": 120, "common": False},
    # --- food / cooking ---
    {"name": "bake_bread",   "requires": "baker",     "in": [["flour", 2], ["water", 1]],                          "out": ["bread", 3],   "difficulty": 1.5, "time_minutes": 120, "tools": ["oven"]},
    {"name": "make_pottage", "requires": "cook",      "in": [["oats", 1], ["water", 2], ["cabbage", 1]],           "out": ["pottage", 3], "difficulty": 1.0, "time_minutes": 90,  "tools": ["pot"]},
    {"name": "make_stew",    "requires": "cook",      "in": [["beef", 1], ["carrot", 1], ["onion", 1], ["water", 2]],"out": ["stew", 3],   "difficulty": 1.5, "time_minutes": 150, "tools": ["pot"]},
    {"name": "roast_meat",   "requires": "cook",      "in": [["pork", 1], ["salt", 1]],                            "out": ["roast", 1],   "difficulty": 1.5, "time_minutes": 120, "tools": ["spit"]},
    {"name": "make_pie",     "requires": "baker",     "in": [["flour", 2], ["beef", 1], ["onion", 1]],             "out": ["pie", 1],     "difficulty": 2.0, "time_minutes": 150, "tools": ["oven"]},
    {"name": "churn_butter", "requires": "dairymaid", "in": [["milk", 4]],                                         "out": ["butter", 1],  "difficulty": 1.0, "time_minutes": 60,  "tools": ["churn"]},
    {"name": "make_cheese",  "requires": "dairymaid", "in": [["milk", 6], ["salt", 1]],                            "out": ["cheese", 2],  "difficulty": 1.5, "time_minutes": 240, "tools": ["press"]},
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
    {"name": "smoke_fish",            "requires": "cook", "in": [["fish", 2], ["salt", 1], ["smoke", 1]],              "out": ["smoked_fish", 2],   "difficulty": 1.2, "time_minutes": 150, "tools": ["smokehouse"]},
    {"name": "brew_cider",            "requires": "brewer", "in": [["apple", 4], ["water", 2]],                        "out": ["cider", 5],         "difficulty": 1.8, "time_minutes": 360, "tools": ["mash_tun"]},
    {"name": "brew_mead",             "requires": "brewer", "in": [["honey", 2], ["water", 2]],                        "out": ["mead", 4],          "difficulty": 2.0, "time_minutes": 360, "tools": ["mash_tun"]},
    {"name": "bind_book",    "requires": "scribe",    "in": [["paper", 3], ["ink", 1]],                            "out": ["book", 1],    "difficulty": 1.5, "time_minutes": 180, "tools": ["quill"]},
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
}

# Fixtures are physical square contents, not decorative background pixels. Their offsets are
# interpreted relative to the scenario's declared square bounds and exported to any client.
TOWN_SQUARE_FIXTURES = [
    {"name": "north_market_stall", "kind": "market_stall", "offset": [-4, -2], "goods": ["bread", "grain"]},
    {"name": "east_market_stall", "kind": "market_stall", "offset": [1, -2], "goods": ["fish", "cheese"]},
    {"name": "west_market_stall", "kind": "market_stall", "offset": [-1, 1], "goods": ["cloth", "tools"]},
    {"name": "town_noticeboard", "kind": "noticeboard", "offset": [-5, 0], "goods": []},
    {"name": "public_well", "kind": "well", "offset": [4, 0], "goods": ["water"]},
    {"name": "south_bench_west", "kind": "bench", "offset": [-3, 2], "goods": []},
    {"name": "south_bench_east", "kind": "bench", "offset": [2, 2], "goods": []},
]

# Construction is separate from the catalogue of places already present when the town is
# founded.  A project can create another instance of any catalogue building (a second granary,
# a new house, a barn, a bridge, and so on) without teaching the world a special-case builder.
BUILDING_PROJECTS = {
    "house": {"building": "house", "staff_role": "", "sheltered": True,
              "rooms": ["living_room", "hearth"], "inputs": {"timber": 12, "thatch": 8},
              "labour": 10.0, "affordance": "shelter"},
    "barn": {"building": "barn", "staff_role": "", "sheltered": True,
             "rooms": ["stall", "hayloft"], "inputs": {"timber": 18, "thatch": 12},
             "labour": 14.0, "affordance": "house_livestock"},
    "granary": {"building": "granary", "inputs": {"timber": 20, "thatch": 15},
                "labour": 18.0, "affordance": "store_dry_food"},
    "root_cellar": {"building": "root_cellar", "inputs": {"stone": 18, "timber": 10},
                    "labour": 16.0, "affordance": "store_root_crops"},
    "wellhouse": {"building": "wellhouse", "inputs": {"stone": 12, "timber": 6},
                  "labour": 12.0, "affordance": "draw_water"},
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
    "midwife":    {"building": "dairy", "tools": [], "base_skill": 0.7, "literacy": 0.7, "capability": 0.8},
    "doctor":     {"building": "dairy", "tools": [], "base_skill": 0.8, "literacy": 0.9, "capability": 0.9},
    "scribe":     {"building": "scriptorium", "tools": ["quill"], "base_skill": 0.7, "literacy": 0.9, "capability": 0.9},
    "teacher":    {"building": "school",       "tools": [],        "base_skill": 0.7, "literacy": 0.95, "capability": 0.95},
    "butcher":    {"building": "shambles",     "tools": ["cleaver"], "base_skill": 0.6},
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


# ---------------------------------------------------------------- SHARED REFERENCES
# A reference is a subject/predicate/object TEMPLATE in the domain data. It is not itself a town fact:
# when seeded, the world creates a resident-owned fact/reference node. `seed_roles` is an initial
# knowledge distribution, not a truth restriction: a resident can learn any reference later by being
# told, observing it, or reading it. "*" means the fact is ordinarily public once its office exists.
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
    """Return the references initially seeded to a resident in `role`."""
    present = set(present_roles or ())
    return [c for c in all_reference_templates()
            if ("*" in c.get("seed_roles", ()) or role in c.get("seed_roles", ()))
            and (not c.get("requires_role") or c["requires_role"] in present)]


# ---------------------------------------------------------------- ANIMALS
# livestock + working animals as DATA. `gives` maps a product -> yield; `eats` is the feed; matures
# and lifespan are in the sim's months; a draught animal has a `pull` (the weight it can haul).
ANIMALS = {
    "pig":     {"gives": {"pork": 40, "hide": 2},            "eats": "scraps", "matures": 6,  "lifespan": 15,  "role": "meat", "ration": 2, "starve_limit": 3},
    "cow":     {"gives": {"milk": 3, "beef": 200, "hide": 5},"eats": "grass",  "matures": 24, "lifespan": 240, "role": "dairy", "ration": 4, "starve_limit": 3},
    "chicken": {"gives": {"eggs": 1, "poultry": 2},          "eats": "grain",  "matures": 5,  "lifespan": 96,  "role": "eggs", "ration": 1, "starve_limit": 4},
    "horse":   {"gives": {"labour": 1},                      "eats": "hay",    "matures": 36, "lifespan": 360, "role": "draught", "ration": 3, "starve_limit": 3, "pull": 500.0},
    "dog":     {"gives": {"herding": 1},                     "eats": "meat",   "matures": 12, "lifespan": 180, "role": "working", "ration": 1, "starve_limit": 5, "ration": 1, "starve_limit": 5},
    "cat":     {"gives": {"ratting": 1},                     "eats": "milk",   "matures": 8,  "lifespan": 180, "role": "working"},
    "sheep":   {"gives": {"wool": 4, "mutton": 60}, "eats": "grass", "matures": 12, "lifespan": 120, "role": "wool"},
    "bee":     {"gives": {"honey": 3, "wax": 1}, "eats": "nectar", "matures": 1, "lifespan": 36, "role": "pollination"},
}

ANIMAL_HUSBANDRY = {
    "milk": {"species": "cow", "product": "milk", "cooldown": 1,
             "roles": ["farmer", "dairymaid", "animal_keeper"]},
    "shear": {"species": "sheep", "product": "wool", "cooldown": 12,
              "roles": ["farmer", "shepherd", "animal_keeper"]},
}


# ---------------------------------------------------------------- CROPS
# every crop is SOWN from its seed, GROWS over `grow_periods` (each period it must be WATERED or it
# builds thirst and WILTS past `wilt`), and when mature is HARVESTED for `yield` of its product.
CROPS = {
    "wheat":   {"seed": "wheat_seed",   "harvest": "grain",   "grow_periods": 4, "water": 2, "yield": 8,  "wilt": 2, "season": "spring"},
    "barley":  {"seed": "barley_seed",  "harvest": "barley",  "grow_periods": 4, "water": 2, "yield": 8,  "wilt": 2, "season": "spring"},
    "oats":    {"seed": "oats_seed",    "harvest": "oats",    "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring"},
    "rye":     {"seed": "rye_seed",     "harvest": "rye",     "grow_periods": 4, "water": 1, "yield": 7,  "wilt": 3, "season": "autumn"},
    "cabbage": {"seed": "cabbage_seed", "harvest": "cabbage", "grow_periods": 3, "water": 3, "yield": 6,  "wilt": 2, "season": "spring"},
    "carrot":  {"seed": "carrot_seed",  "harvest": "carrot",  "grow_periods": 3, "water": 2, "yield": 10, "wilt": 2, "season": "spring"},
    "onion":   {"seed": "onion_seed",   "harvest": "onion",   "grow_periods": 3, "water": 2, "yield": 9,  "wilt": 2, "season": "spring"},
    "potato":  {"seed": "potato_seed",  "harvest": "potato",  "grow_periods": 4, "water": 2, "yield": 12, "wilt": 2, "season": "spring"},
    "turnip":  {"seed": "turnip_seed",  "harvest": "turnip",  "grow_periods": 2, "water": 2, "yield": 8,  "wilt": 2, "season": "autumn"},
    "bean":    {"seed": "bean_seed",    "harvest": "bean",    "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring"},
    "pea":     {"seed": "pea_seed",     "harvest": "pea",     "grow_periods": 3, "water": 2, "yield": 7,  "wilt": 2, "season": "spring"},
    "leek":    {"seed": "leek_seed",    "harvest": "leek",    "grow_periods": 4, "water": 2, "yield": 6,  "wilt": 2, "season": "autumn"},
    "parsnip": {"seed": "parsnip_seed", "harvest": "parsnip", "grow_periods": 4, "water": 2, "yield": 6, "wilt": 2, "season": "autumn"},
    "beet":    {"seed": "beet_seed",    "harvest": "beet",    "grow_periods": 3, "water": 2, "yield": 8, "wilt": 2, "season": "autumn"},
    "garlic":  {"seed": "garlic_seed",  "harvest": "garlic",  "grow_periods": 4, "water": 1, "yield": 8, "wilt": 3, "season": "autumn"},
    "lettuce": {"seed": "lettuce_seed", "harvest": "lettuce", "grow_periods": 2, "water": 3, "yield": 8, "wilt": 1, "season": "spring"},
    "cucumber": {"seed": "cucumber_seed", "harvest": "cucumber", "grow_periods": 3, "water": 3, "yield": 8, "wilt": 1, "season": "summer"},
    "lentil":  {"seed": "lentil_seed",  "harvest": "lentil",  "grow_periods": 3, "water": 2, "yield": 7, "wilt": 2, "season": "spring"},
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
}

STARTING_CROPS = ("wheat", "barley", "oats", "cabbage", "potato", "carrot", "onion", "bean")

# The map/cast uses plain-language occupations while the craft catalogue uses production trades.
# These bridges preserve the resident's public occupation and seed the corresponding capabilities.
CAST_ROLE_TRADES = {
    "carpenter": ("woodworker",),
    "farm_labourer": ("farmer",),
    "farmer": ("farmer", "cook"),
    "fishmonger": ("fisher",),
    "forester": ("collier",),
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
    "loam": {"fertility": 0.85, "water_retention": 0.75, "drainage": 0.65, "erosion": 0.10},
    "clay": {"fertility": 0.75, "water_retention": 0.90, "drainage": 0.30, "erosion": 0.08},
    "sand": {"fertility": 0.35, "water_retention": 0.25, "drainage": 0.95, "erosion": 0.25},
    "chalk": {"fertility": 0.55, "water_retention": 0.45, "drainage": 0.80, "erosion": 0.15},
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

WASTE_CYCLES = {
    "human_waste": {"source": "household", "treatment": "latrine", "output": "compost", "risk": 0.8},
    "animal_manure": {"source": "livestock", "treatment": "compost_yard", "output": "manure", "risk": 0.4},
    "kitchen_scraps": {"source": "kitchen", "treatment": "compost_yard", "output": "compost", "risk": 0.2},
    "ash": {"source": "hearth", "treatment": "ash_pit", "output": "soil_amendment", "risk": 0.1},
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
    in1 = ins[0]
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
    "smoke": 0.02, "soot": 0.05, "scraps": 0.05, "grass": 0.05, "water": 0.05, "rag": 0.1, "hay": 0.1,
    "thatch": 0.2, "peat": 0.3, "dung": 0.05, "manure": 0.05, "compost": 0.1,
    "medicine": 6.0, "nectar": 0.2, "wax": 1.0,
    # abundant local raw
    "wood": 0.3, "log": 0.5, "ore": 0.6, "grain": 0.5, "straw": 0.2,
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
            m, l = _value_parts(ik, _seen | {kind})
            mat += m * float(iq)
            lab += l * float(iq)
        mat, lab = mat / outq, lab / outq
        val = mat + lab * LABOUR_RATE
        if best is None or val < best[2]:
            best = (mat, lab, val)
    return (best[0], best[1])


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
