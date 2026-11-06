"""shared_frames.py -- the frames Bigville residents can hold in common, as PURE DATA.

Skills (what a person can do), trades (organised ways of working that exercise skills and make
recipes), and jobs (the positions a resident is seeded into, bundling trades and duties); the shared
concepts, policies, laws, charters, and procedures of the village; land tenure; offices, households,
and the division of labour. A frame here is a TEMPLATE: a resident holds it only once it is seeded,
taught, read, or observed. The world itself is in world_affordances.
"""
from __future__ import annotations

from domains.pack import load_pack as _load_pack

# Tables and constants below are read from the "bigville" data pack (packs/bigville/).
# Their explanatory comments are in the pack files as "_doc"; domains/pack.py
# compiles the derived entries. Functions in this module read these names unchanged.
_PACK = _load_pack(globals().get("_PACK_NAME", "bigville"))   # data_view seeds _PACK_NAME
SKILLS = _PACK["SKILLS"]
TRADE_SKILLS = _PACK["TRADE_SKILLS"]
OPEN_RECIPE_SKILLS = _PACK["OPEN_RECIPE_SKILLS"]
METASKILLS = _PACK["METASKILLS"]
META_METASKILL = _PACK["META_METASKILL"]
# Phase 018: the chatter and weather phrases residents say (read by bigville/runtime.py).
SPEECH_CHATTER = _PACK["SPEECH_CHATTER"]
SPEECH_WEATHER = _PACK["SPEECH_WEATHER"]
SKILL_LIMITATIONS = _PACK["SKILL_LIMITATIONS"]
# Phase 034: the intoxication rates a working skill loses per unit of alcohol in the body (effective_skill).
INTOXICATION = _PACK["INTOXICATION"]
SKILL_CLUSTERS = _PACK["SKILL_CLUSTERS"]
SKILL_CLOSENESS = _PACK["SKILL_CLOSENESS"]
SKILL_AFFINITY = _PACK["SKILL_AFFINITY"]
TRANSFER = _PACK["TRANSFER"]
APTITUDE_PRACTICE = _PACK["APTITUDE_PRACTICE"]
PRACTICE = _PACK["PRACTICE"]
META_FROM_SKILL = _PACK["META_FROM_SKILL"]
TRADES = _PACK["TRADES"]
LAND_TENURE = _PACK["LAND_TENURE"]
LAND_RECORDS = _PACK["LAND_RECORDS"]
DEED_TYPES = _PACK["DEED_TYPES"]
LAND_DISPUTES = _PACK["LAND_DISPUTES"]
SHARED_CONCEPTS = _PACK["SHARED_CONCEPTS"]
LOCAL_POLICIES = _PACK["LOCAL_POLICIES"]
LOCAL_LAWS = _PACK["LOCAL_LAWS"]
GIANTVILLE_POLICIES = _PACK["GIANTVILLE_POLICIES"]
GIANTVILLE_LAWS = _PACK["GIANTVILLE_LAWS"]
LAWMAKING_PROCEDURES = _PACK["LAWMAKING_PROCEDURES"]
JUSTICE_PROCEDURES = _PACK["JUSTICE_PROCEDURES"]
CHARTERS = _PACK["CHARTERS"]
CAST_ROLE_TRADES = _PACK["CAST_ROLE_TRADES"]
HOUSEHOLDS = _PACK["HOUSEHOLDS"]
LABOUR_TASKS = _PACK["LABOUR_TASKS"]
GOVERNANCE_OFFICES = _PACK["GOVERNANCE_OFFICES"]
MIN_SKILL = _PACK["MIN_SKILL"]
LIT_FUNCTIONAL = _PACK["LIT_FUNCTIONAL"]
LIT_EDUCATED = _PACK["LIT_EDUCATED"]
SYSTEM_OF_TRADE = _PACK["SYSTEM_OF_TRADE"]
JOBS = _PACK["JOBS"]
POLICIES = _PACK["POLICIES"]
LAWS = _PACK["LAWS"]
_SKILL_CLUSTER = _PACK["_SKILL_CLUSTER"]
# How a townspeople seed's relationship labels become held ties (Phase 014).
RELATIONSHIP_KINDS = _PACK["RELATIONSHIP_KINDS"]
RELATIONSHIP_DEFAULT = _PACK["RELATIONSHIP_DEFAULT"]
# Kinship (Phase 009). Genealogy is a world fact; these are what residents call one another and the
# inheritance custom under which genealogical heirs are published. See packs/bigville/frames/kinship.json.
KIN_TERMS = _PACK["KIN_TERMS"]
KIN_ATTRIBUTION = _PACK["KIN_ATTRIBUTION"]
KIN_OBLIGATIONS = _PACK["KIN_OBLIGATIONS"]
INHERITANCE_CUSTOM = _PACK["INHERITANCE_CUSTOM"]
# Fiscal institutions (Phase 011): one entry per institution, with the seed rules it was extracted from.
# Each seed rule is in one entry's seed_rules or in FISCAL_BACKEND_OWNED (the rules the backend decides).
# The physical purses and actions are in world_affordances (FISCAL_PURSES, FISCAL_ACTIONS).
FISCAL_INSTITUTIONS = _PACK["FISCAL_INSTITUTIONS"]
FISCAL_BACKEND_OWNED = _PACK["FISCAL_BACKEND_OWNED"]


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


def skill_cluster(skill):
    return _SKILL_CLUSTER.get(skill)


def skill_metaskill(skill):
    cluster = _SKILL_CLUSTER.get(skill)
    return SKILL_CLUSTERS[cluster]["metaskill"] if cluster else None


# How a skill is learned (Phase 012). "physical": the hand and body learn it by practice, and the world
# always consolidates that practice into levels. "cognitive": understanding, which the world consolidates
# only when the `cognitive_practice` subsystem is on; otherwise the practice is published to the actor.
LEARNING_KINDS = ("physical", "cognitive")


def skill_learning(skill):
    """'physical' or 'cognitive' (the pack's `learning` tag), or None for an unknown skill."""
    return SKILLS.get(skill, {}).get("learning")


def skill_closeness(a, b):
    """How much practice of skill `a` carries to skill `b` (symmetric, 0..1)."""
    if a == b:
        return 1.0
    pair = SKILL_AFFINITY.get((a, b), SKILL_AFFINITY.get((b, a)))
    if pair is not None:
        return float(pair)
    ca, cb = _SKILL_CLUSTER.get(a), _SKILL_CLUSTER.get(b)
    if ca and ca == cb:
        return float(SKILL_CLOSENESS["cluster"])
    if ca and cb and SKILL_CLUSTERS[ca]["metaskill"] == SKILL_CLUSTERS[cb]["metaskill"]:
        return float(SKILL_CLOSENESS["metaskill"])
    return 0.0


def skill_transfer(levels, skill):
    """(transfer, source): the best carry-over to `skill` from a person's OTHER skills."""
    best, source = 0.0, None
    for held, level in levels.items():
        if held == skill:
            continue
        t = float(level) * skill_closeness(held, skill)
        if t > best:
            best, source = t, held
    return best, source


def aptitude_factor(person, metaskill):
    """How much a person's aptitude helps with a metaskill: aptitude ** g_loading (1.0 if average)."""
    aptitude = float((person or {}).get("aptitude", 1.0))
    loading = float(METASKILLS.get(metaskill, {}).get("g_loading", 0.0)) if metaskill else 0.0
    return max(0.0, aptitude) ** loading


def _intoxication_effect(person, skill):
    """The level a working skill loses while the body holds alcohol (Phase 034): coordination_rate per unit of
    intoxication for a physical skill, focus_rate for a cognitive one. Zero when sober or when no level is given."""
    level = float((person or {}).get("intoxication", 0.0))
    if level <= 0.0:
        return 0.0
    rate = INTOXICATION["focus_rate"] if skill_learning(skill) == "cognitive" else INTOXICATION["coordination_rate"]
    return -float(rate) * level


def _limitation_effects(person, skill):
    """(level delta, learn multiplier) from a person's limitations, for `skill` and its metaskill."""
    meta = skill_metaskill(skill)
    delta, learn = 0.0, 1.0
    for name in (person or {}).get("limitations", ()):
        spec = SKILL_LIMITATIONS.get(name, {})
        learn *= float(spec.get("all_learning", 1.0))
        for effect in (spec.get("skills", {}).get(skill), spec.get("metaskills", {}).get(meta)):
            if effect:
                delta += float(effect.get("level", 0.0))
                learn *= float(effect.get("learn", 1.0))
    return delta, learn


def effective_skill(levels, metas, skill, person=None):
    """A person's working level at `skill`: their own, lifted by transfer through the metaskill (which
    aptitude sharpens), then lowered by any limitations. `person` is {"aptitude", "talents",
    "limitations"}; omitted, they are average and unlimited."""
    own = float(levels.get(skill, 0.0))
    transfer, _ = skill_transfer(levels, skill)
    meta_name = skill_metaskill(skill)
    meta = float(metas.get(meta_name, 0.0)) * aptitude_factor(person, meta_name)
    lift = transfer * (TRANSFER["base"] + TRANSFER["meta"] * min(1.0, meta))
    delta, _learn = _limitation_effects(person, skill)
    delta += _intoxication_effect(person, skill)
    return max(0.0, min(1.0, own + (1.0 - own) * lift + delta))


def practice_gain(levels, metas, skill, minutes, person=None):
    """(skill gain, metaskill gain, aptitude gain) from `minutes` of practice at `skill`.

    Learning speed rises with transfer from close skills and with the metaskill, and is scaled by
    aptitude (through the metaskill's g_loading), the person's talent for that metaskill, and any
    limitations. Every hour of practice also nudges aptitude toward its ceiling (learning to learn)."""
    hours = float(minutes) / 60.0
    own = float(levels.get(skill, 0.0))
    transfer, _ = skill_transfer(levels, skill)
    meta_name = skill_metaskill(skill)
    meta = float(metas.get(meta_name, 0.0))
    person = person or {}
    gift = aptitude_factor(person, meta_name) * float(person.get("talents", {}).get(meta_name, 1.0))
    _delta, learn = _limitation_effects(person, skill)
    speed = (1.0 + PRACTICE["transfer"] * transfer + PRACTICE["meta"] * meta) * gift * learn
    gain = min(1.0 - own, PRACTICE["rate"] * hours * (1.0 - own) * speed)
    meta_gain = (min(1.0 - meta, PRACTICE["meta_rate"] * hours * (1.0 - meta) * gift * learn)
                 if meta_name else 0.0)
    aptitude = float(person.get("aptitude", 1.0))
    ceiling = float(person.get("aptitude_base", aptitude)) * (1.0 + APTITUDE_PRACTICE["headroom"])
    aptitude_gain = max(0.0, APTITUDE_PRACTICE["rate"] * hours * (ceiling - aptitude))
    return gain, meta_gain, aptitude_gain


def initial_skill_levels(trades, level):
    """({skill: level}, {metaskill: level}) for someone practised in `trades` at `level`."""
    levels, metas = {}, {}
    for trade in trades:
        for skill in TRADE_SKILLS.get(trade, ()):
            levels[skill] = max(levels.get(skill, 0.0), float(level))
    for skill, lv in levels.items():
        meta = skill_metaskill(skill)
        if meta:
            metas[meta] = max(metas.get(meta, 0.0), META_FROM_SKILL * lv)
    return levels, metas


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
            # A concept inherits its bundle's knowledge spec (Phase 019); see domains/knowledge.py.
            row.setdefault("knowledge", bundle.get("knowledge", {}))
            templates.append(row)
    return templates


def min_skill(recipe_name):
    """The minimum skill needed to ATTEMPT a recipe (default 0.0 -- apprentice-level work)."""
    return float(MIN_SKILL.get(recipe_name, 0.0))


def literacy_tier(literacy):
    """Name the reading tier a literacy level sits in: labouring / functional / educated."""
    if float(literacy) >= LIT_EDUCATED:
        return "educated"
    if float(literacy) >= LIT_FUNCTIONAL:
        return "functional"
    return "labouring"


