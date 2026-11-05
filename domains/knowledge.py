"""knowledge.py -- derived knowledge priors (Phase 019): what a resident is aware of and understands.

PURE. Nothing here touches a world or a backend. `derive_knowledge(person, pack)` takes one resident's
description and a pack view (`domains.bigville_entities` or a `data_view` entities view) and returns a row
for every knowable item in that pack:

    {"<type>:<name>": {"type", "name", "aware": bool, "understands": 0..1, "basis": [str, ...],
                       "location": "none"|"roughly"|"exact"   (places only)}}

`aware` means the resident knows the item exists and roughly what it is for. `understands` (0..1) means they
can use, follow, or explain it. For a skill-based item the degree is the resident's working level. Understanding
implies awareness. Every row has a non-empty `basis`: the reasons it is or is not known.

The person description (see `person_from_attrs` and `person_from_cast_record`):
    name, age, job, trades (trade names, excluding the job), literacy (0..1),
    skill_levels {skill: level}, metaskill_levels {metaskill: level},
    aptitude, talents, limitations,
    history {local, years_in_village, apprenticed [trade], former_trades [{trade, years, level}],
             past_offices [office], widowed, household_role}   (optional; absent means: local, lifelong)
    household (str), kin_terms [term names held], neighbours [{name, job, household, workplace}],
    workplace (anchor name, e.g. "mill"), home_cell.

Knowledge specs are the `knowledge` entries of the pack (see frames/knowledge.json `_doc`). Public spread
is authored (APPROX). A spec at or above KNOWLEDGE_RULES.public_cutoff is known to every resident with at
least `after_years` in the village. Below the cutoff, only a topic link (the resident practises a skill of one
of the topic's skills), a role, or a history fact makes a thing known.
"""
from __future__ import annotations

import zlib

from domains.pack import load_pack as _load_pack

_PACK = _load_pack(globals().get("_PACK_NAME", "bigville"))   # data_view seeds _PACK_NAME
KNOWLEDGE_TOPICS = _PACK["KNOWLEDGE_TOPICS"]
KNOWLEDGE_RULES = _PACK["KNOWLEDGE_RULES"]
JOB_PUBLIC = _PACK["JOB_PUBLIC"]
JOB_ROUTINE = _PACK["JOB_ROUTINE"]
KNOWABLE_PLACES = _PACK["KNOWABLE_PLACES"]
PROCEDURE_KNOWLEDGE = _PACK["PROCEDURE_KNOWLEDGE"]

PUBLIC_CUTOFF = float(KNOWLEDGE_RULES["public_cutoff"])
STORE_GOODS_PUBLIC = float(KNOWLEDGE_RULES["store_goods_public"])
LITERACY_ORDER = {"labouring": 0, "functional": 1, "educated": 2}
LOCATION_DEGREE = {"none": 0.0, "roughly": 0.5, "exact": 1.0}


# ----------------------------------------------------------------- person descriptions
def _history(history, age):
    """A history with its defaults: local and lifelong, no apprenticeships, no past offices."""
    history = dict(history or {})
    return {
        "local": bool(history.get("local", True)),
        "years_in_village": float(history.get("years_in_village", age)),
        "apprenticed": list(history.get("apprenticed", [])),
        "former_trades": [dict(f) for f in history.get("former_trades", [])],
        "past_offices": list(history.get("past_offices", [])),
        "widowed": bool(history.get("widowed", False)),
        "household_role": str(history.get("household_role", "")),
    }


def _workplace(pack, job):
    """The anchor a job works at (FOUNDING_JOBS), or '' when the pack has no founding town."""
    return str(pack.FOUNDING_JOBS.get(job, {}).get("workplace", "")) if pack.FOUNDING_JOBS else ""


def person_from_attrs(name, attrs, *, pack, history=None, kin_terms=(), neighbours=(), home_cell=None):
    """A person description from a world actor's attributes (the seeding BigvilleGame does)."""
    job = str(attrs.get("role", ""))
    listed = [t for t in str(attrs.get("trades", "")).split(",") if t]
    age = float(attrs.get("age", 30.0))
    return {
        "name": name, "age": age, "job": job,
        "trades": [t for t in listed if t != job],
        "literacy": float(attrs.get("literacy", 0.0)),
        "skill_levels": {k: float(v) for k, v in dict(attrs.get("skill_levels", {})).items()},
        "metaskill_levels": {k: float(v) for k, v in dict(attrs.get("metaskill_levels", {})).items()},
        "aptitude": float(attrs.get("aptitude", 1.0)),
        "talents": {k: float(v) for k, v in dict(attrs.get("talents", {})).items()},
        "limitations": list(attrs.get("limitations", [])),
        "history": _history(history if history is not None else attrs.get("history"), age),
        "household": str(attrs.get("household", "")),
        "kin_terms": sorted(kin_terms), "neighbours": [dict(n) for n in neighbours],
        "workplace": _workplace(pack, job), "home_cell": list(home_cell) if home_cell is not None else None,
    }


def person_from_cast_record(record, cast, *, pack, seed):
    """A person description from one founding-cast record, as populate_town100 seeds it.

    Skill levels are those add_actor gives (each trade skill at the job's base level), plus the apprenticeship
    levels in the record's `former_skills`. Capacities are drawn as BigvilleWorld.draw_capacities draws them, so
    the description matches a world built from the same seed. The genealogical kin terms are not in the cast,
    so `kin_terms` is empty here."""
    import numpy as np
    job = record["role"]
    trades = list(record.get("trades", []))
    levels, metas = pack.initial_skill_levels((job,) + tuple(trades), float(record["skill"]))
    levels, metas = dict(levels), dict(metas)
    for skill, level in dict(record.get("former_skills", {})).items():
        levels[skill] = max(levels.get(skill, 0.0), float(level))
        meta = pack.skill_metaskill(skill)
        if meta:
            metas[meta] = max(metas.get(meta, 0.0), pack.META_FROM_SKILL * float(level))
    rng = np.random.default_rng((int(seed) * 1_000_003) ^ zlib.crc32(str(record["name"]).encode()))
    drawn = pack.draw_person_capacities(rng, age=float(record["age"]))
    household = record.get("household")
    neighbours = [{"name": other["name"], "job": other["role"],
                   "household": f"household_{int(other['household']):03d}",
                   "workplace": _workplace(pack, other["role"])}
                  for other in cast.get("residents", []) if other["name"] != record["name"]]
    return {
        "name": record["name"], "age": float(record["age"]), "job": job, "trades": trades,
        "literacy": float(record["literacy"]),
        "skill_levels": levels, "metaskill_levels": metas,
        "aptitude": float(drawn["aptitude"]), "talents": dict(drawn["talents"]),
        "limitations": list(drawn["limitations"]),
        "history": _history(record.get("history"), float(record["age"])),
        "household": f"household_{int(household):03d}" if household is not None else "",
        "kin_terms": [], "neighbours": neighbours, "workplace": _workplace(pack, job),
        "home_cell": list(record["home_cell"]),
    }


# ----------------------------------------------------------------- derivation
class _Person:
    """One person description against one pack, with the derived views the rules need."""

    def __init__(self, person, pack):
        self.pack = pack
        self.person = person
        self.name = str(person.get("name", ""))
        self.age = float(person.get("age", 30.0))
        self.job = str(person.get("job", ""))
        self.history = _history(person.get("history"), self.age)
        self.years = float(self.history["years_in_village"])
        self.levels = {k: float(v) for k, v in dict(person.get("skill_levels", {})).items()}
        self.metas = {k: float(v) for k, v in dict(person.get("metaskill_levels", {})).items()}
        self.capacity = {"aptitude": float(person.get("aptitude", 1.0)),
                         "talents": dict(person.get("talents", {})),
                         "limitations": list(person.get("limitations", []))}
        self.literacy_tier = pack.literacy_tier(float(person.get("literacy", 0.0)))
        self.former = self.history["former_trades"]
        self.apprenticed = set(self.history["apprenticed"]) | {f["trade"] for f in self.former}
        self.trades = set(person.get("trades", [])) | ({self.job} if self.job else set())
        self.practised = self.trades | self.apprenticed
        self.offices = set(self.history["past_offices"])
        if self.job in pack.GOVERNANCE_OFFICES:
            self.offices.add(self.job)
        self.clusters = {pack.skill_cluster(s) for s, lv in self.levels.items() if lv > 0} - {None}
        self.kin_terms = set(person.get("kin_terms", []))
        self.neighbours = list(person.get("neighbours", []))
        self.household = str(person.get("household", ""))
        self.workplace = str(person.get("workplace", ""))
        routine = set(JOB_ROUTINE.get(self.job, []))
        for trade in self.trades:
            building = pack.TRADES.get(trade, {}).get("building")
            if building:
                routine.add(building)
        self.routine = routine
        self._eff = {}

    def own(self, skill):
        return float(self.levels.get(skill, 0.0))

    def eff(self, skill):
        if skill not in self._eff:
            self._eff[skill] = float(self.pack.effective_skill(self.levels, self.metas, skill, self.capacity))
        return self._eff[skill]

    def meta(self, name):
        return float(self.metas.get(name, 0.0))


def _check(P, cond):
    """(met, note, degree) for one understanding condition. `degree` is the working level for a skill."""
    if "any" in cond:
        results = [_check(P, c) for c in cond["any"]]
        degree = next((r[2] for r in results if r[0] and r[2] is not None), None)
        return any(r[0] for r in results), "any of: " + "; ".join(r[1] for r in results), degree
    if "skill" in cond:
        level = float(cond.get("level", 0.0))
        value = P.eff(cond["skill"])
        return value + 1e-9 >= level, f"{cond['skill']} at {value:.2f} (needs {level:.2f})", value
    if "metaskill" in cond:
        level = float(cond.get("level", 0.0))
        value = P.meta(cond["metaskill"])
        return value + 1e-9 >= level, f"{cond['metaskill']} metaskill at {value:.2f} (needs {level:.2f})", None
    if "trade" in cond:
        return cond["trade"] in P.practised, f"practises the trade {cond['trade']}", None
    if "apprenticed" in cond:
        return cond["apprenticed"] in P.apprenticed, f"apprenticed to {cond['apprenticed']}", None
    if "literacy" in cond:
        need = cond["literacy"]
        met = LITERACY_ORDER[P.literacy_tier] >= LITERACY_ORDER[need]
        return met, f"reads at the {need} level (has {P.literacy_tier})", None
    if "office" in cond:
        return cond["office"] in P.offices, f"holds or has held the office of {cond['office']}", None
    if "authority" in cond:
        want = cond["authority"]
        held = sorted(o for o in P.offices if P.pack.GOVERNANCE_OFFICES.get(o, {}).get("authority") == want)
        return bool(held), f"holds an office of {want} authority" + (f" ({', '.join(held)})" if held else ""), None
    if "served" in cond:
        return "councillor" in P.offices, f"has served on the {cond['served']}", None
    if "years" in cond:
        need = float(cond["years"])
        return P.years + 1e-9 >= need, f"{P.years:g} years in the village (needs {need:g})", None
    raise ValueError(f"unknown understanding condition: {cond}")


def _understanding(P, conditions):
    """(degree, notes). Degree is 0 unless every condition is met. Then it is the working level of the first
    skill condition, or 1.0 when there is none."""
    notes, degree, all_met = [], None, True
    for cond in conditions:
        met, note, value = _check(P, cond)
        notes.append(("met: " if met else "not met: ") + note)
        if not met:
            all_met = False
        elif value is not None and degree is None:
            degree = value
    if not all_met:
        return 0.0, notes
    return (1.0 if degree is None else float(degree)), notes


def _public_awareness(P, spec):
    """(aware, notes): awareness from public spread, or from a topic the resident practises a skill of."""
    public = float(spec.get("public", 0.0))
    after = float(spec.get("after_years", 0.0))
    notes = []
    if public >= PUBLIC_CUTOFF:
        if P.years + 1e-9 >= after:
            return True, [f"public spread {public:.2f}: known to residents who have lived here {after:g} years"]
        notes.append(f"public spread {public:.2f}, but {P.years:g} years here (needs {after:g})")
    elif public > 0:
        notes.append(f"public spread {public:.2f} is below the cutoff {PUBLIC_CUTOFF:.2f}")
    else:
        notes.append("no public spread")
    for topic in spec.get("topics", []):
        linked = [s for s in KNOWLEDGE_TOPICS[topic]["skills"] if P.own(s) > 0]
        if linked:
            return True, notes + [f"topic {topic}: practises {', '.join(linked)}"]
    notes.append("no topic link to a skill held")
    return False, notes


def _row(kind, name, aware, understands, basis, **extra):
    """A derived row. Understanding implies awareness: an unaware resident understands nothing."""
    aware = bool(aware)
    row = {"type": kind, "name": name, "aware": aware,
           "understands": round(float(understands) if aware else 0.0, 4), "basis": list(basis) or ["no link"]}
    row.update(extra)
    return row


def _role_condition(cond):
    """A condition that is evidence of knowing the item: a held office or skill, a trade, an apprenticeship,
    or a history fact. Literacy and years in the village are capacities, not evidence of knowing a thing."""
    if "any" in cond:
        return any(_role_condition(c) for c in cond["any"])
    return not any(k in cond for k in ("literacy", "years"))


def _spec_row(P, kind, name, spec, conditions):
    """A row for an entry with a knowledge spec and understanding conditions.

    Aware if publicly or topically known, or if a role condition (office, skill, trade, history) is met.
    Understood to the degree the conditions give, and only when aware. With no conditions, understood by
    everyone who is publicly or topically aware."""
    aware_public, notes = _public_awareness(P, spec)
    if conditions:
        degree, understood_notes = _understanding(P, conditions)
        role_met = any(_check(P, c)[0] for c in conditions if _role_condition(c))
        aware = aware_public or role_met
        basis = notes + understood_notes
        if role_met and not aware_public:
            basis = basis + ["aware through a role held or a history fact"]
    else:
        degree = 1.0 if aware_public else 0.0
        aware = aware_public
        basis = notes + ["no understanding conditions: aware means understood"]
    return _row(kind, name, aware, degree, basis)


def _recipe_row(P, recipe):
    name, requires = recipe["name"], recipe["requires"]
    spec = recipe.get("knowledge", {})
    skill = P.pack.recipe_skill(recipe)
    cluster = P.pack.skill_cluster(skill) if skill else None
    if requires in P.practised:
        aware, basis = True, [f"trade {requires} is practised"]
    elif cluster and cluster in P.clusters:
        aware, basis = True, [f"same skill cluster as a skill held ({cluster})"]
    else:
        aware, basis = _public_awareness(P, spec)
        if not aware:
            basis = basis + [f"trade {requires} not practised"]
    degree, understood_notes = _understanding(P, spec.get("understanding_requires", []))
    return _row("recipe", name, aware or degree > 0, degree, basis + understood_notes,
                requires=requires, skill=skill)


def _goods_of(recipe):
    """Names of the goods a recipe uses or makes. `in` is a list of [kind, qty]; `out` is one or more pairs."""
    names = []
    for part in (recipe.get("in") or [], recipe.get("out") or []):
        if part and isinstance(part[0], str):
            names.append(part[0])
        else:
            names += [pair[0] for pair in part if isinstance(pair, (list, tuple)) and pair and isinstance(pair[0], str)]
    return names


def _goods_rows(P, pack, recipe_rows):
    """Kinds of goods: aware if sold in the store, or used or made by a recipe the resident is aware of.
    Understood if such a recipe is understood (to any degree)."""
    recipe_index = {r["name"]: r for r in pack.RECIPES}
    used = {}
    for row in recipe_rows:
        for good in _goods_of(recipe_index[row["name"]]):
            entry = used.setdefault(good, {"aware": [], "understood": []})
            if row["aware"]:
                entry["aware"].append(row["name"])
            if row["understands"] > 0:
                entry["understood"].append(row["name"])
    store = set(pack.STARTING_STOCK) | {chain["out"] for chain in pack.SHOP_CHAINS.values()}
    rows = []
    for good in sorted(set(used) | store):
        entry = used.get(good, {"aware": [], "understood": []})
        basis = []
        if good in store:
            basis.append(f"sold in the store (public spread {STORE_GOODS_PUBLIC:.2f})")
        if entry["aware"]:
            basis.append("used or made in recipes known: " + ", ".join(sorted(entry["aware"])[:6]))
        if entry["understood"]:
            basis.append("understood in: " + ", ".join(sorted(entry["understood"])[:6]))
        if not basis:
            basis = ["not used or made in any recipe known, and not sold in the store"]
        rows.append(_row("good", good, good in store or bool(entry["aware"]),
                         1.0 if entry["understood"] else 0.0, basis))
    return rows


def _place_row(P, name, spec):
    """A place: its existence and its location. Exact if on the resident's routine (home, trades, job
    places). Roughly if publicly known and the resident has lived here long enough. Otherwise none."""
    aware, notes = _public_awareness(P, spec)
    public = float(spec.get("public", 0.0))
    after = float(spec.get("after_years", 0.0))
    if name in P.routine:
        location = "exact"
        basis = [f"on the routine of {P.job or 'this resident'} (job places or a trade practised)"]
    elif public >= PUBLIC_CUTOFF and P.years + 1e-9 >= after:
        location = "roughly"
        basis = [f"public spread {public:.2f}: known roughly after {after:g} years here"]
    else:
        location = "none"
        basis = notes
    return _row("place", name, aware or location != "none", LOCATION_DEGREE[location], basis, location=location)


def _resident_rows(P):
    rows = []
    for other in P.neighbours:
        notes = []
        if other.get("household") and other.get("household") == P.household:
            notes.append("shares the household")
        if P.workplace and other.get("workplace") == P.workplace:
            notes.append(f"works at the same place ({P.workplace})")
        public = float(JOB_PUBLIC.get(other.get("job", ""), 0.0))
        if public >= PUBLIC_CUTOFF:
            notes.append(f"public spread {public:.2f}: known to everyone as the {other.get('job')}")
        aware = bool(notes)
        if not aware:
            notes = [f"no household, work, or public-role link (public {public:.2f})"]
        rows.append(_row("resident", other["name"], aware, 0.0, notes, job=other.get("job", "")))
    return rows


def derive_knowledge(person, pack):
    """Every knowable item in `pack`, derived for one resident. Pure: the same inputs give the same rows.

    Returns {"type:name": row} (see the module docstring). `pack` is a pack view with the entity tables
    (RECIPES, GOVERNANCE_OFFICES, ...) and functions (effective_skill, recipe_skill, ...)."""
    P = _Person(person, pack)
    out = {}
    recipes = [_recipe_row(P, recipe) for recipe in pack.RECIPES]
    for row in recipes:
        out[f"recipe:{row['name']}"] = row
    for row in _goods_rows(P, pack, recipes):
        out[f"good:{row['name']}"] = row
    for kind, bundles in (("law", pack.LAWS), ("policy", pack.POLICIES), ("charter", pack.CHARTERS)):
        for bundle in bundles:
            spec = bundle.get("knowledge", {})
            conditions = []
            if kind in pack.DOCUMENT_LITERACY and spec.get("written", True):
                conditions.append({"literacy": pack.DOCUMENT_LITERACY[kind]})
            conditions += list(spec.get("understanding_requires", []))
            out[f"{kind}:{bundle['name']}"] = _spec_row(P, kind, bundle["name"], spec, conditions)
    for concept in pack.SHARED_CONCEPTS:
        spec = concept.get("knowledge", {})
        out[f"concept:{concept['name']}"] = _spec_row(
            P, "concept", concept["name"], spec, list(spec.get("understanding_requires", [])))
    for name, spec in PROCEDURE_KNOWLEDGE.items():
        out[f"procedure:{name}"] = _spec_row(P, "procedure", name, spec,
                                             list(spec.get("understanding_requires", [])))
    for name, spec in pack.GOVERNANCE_OFFICES.items():
        out[f"office:{name}"] = _spec_row(P, "office", name, spec.get("knowledge", {}), [{"office": name}])
    for name, spec in pack.KIN_TERMS.items():
        know = spec.get("knowledge", {})
        aware, notes = _public_awareness(P, know)
        held = name in P.kin_terms
        notes.append("holds this term in the genealogy" if held else "holds no relation with this term")
        out[f"kin_term:{name}"] = _row("kin_term", name, aware or held, 1.0 if held else 0.0, notes)
    for name, spec in KNOWABLE_PLACES.items():
        out[f"place:{name}"] = _place_row(P, name, spec)
    for table in (pack.BUILDINGS, pack.RESOURCE_DEPOSITS, pack.WATER_SOURCES):
        for name, row in table.items():
            know = row.get("knowledge", {})
            if not know.get("personal"):
                out[f"place:{name}"] = _place_row(P, name, know)
    out["place:home"] = _row("place", "home", True, 1.0, ["this resident's own household home"],
                             location="exact")
    for name, row in pack.ANIMALS.items():
        know = row.get("knowledge", {})
        out[f"animal:{name}"] = _spec_row(P, "animal", name, know, list(know.get("understanding_requires", [])))
    for row in _resident_rows(P):
        out[f"resident:{row['name']}"] = row
    return out


def knowledge_memories(derived, *, positions=None, learned="founding", period=0):
    """The private memory records that derived knowledge seeds. No world state is read here.

    One record per item that is aware or understood. Kind "understanding" when understood to any degree, else
    "awareness". A recipe understood to any degree keeps kind "recipe_knowledge" with belief "can_attempt", the
    kind the simple backend already reads for recipe work. A place carries its location, the position believed
    (exact: a cell; roughly: a landmark; `positions` gives both from the world), and when it was learned."""
    positions = positions or {}
    out = []
    for item, row in derived.items():
        if not row["aware"]:
            continue
        content = {"item": item, "type": row["type"], "name": row["name"], "aware": True,
                   "understands": row["understands"], "basis": list(row["basis"]), "source": "derived"}
        kind = "understanding" if row["understands"] > 0 else "awareness"
        if row["type"] == "recipe" and row["understands"] > 0:
            kind = "recipe_knowledge"
            content["recipe"] = row["name"]
            content["belief"] = "can_attempt"
        if row["type"] == "place":
            location = row.get("location", "none")
            believed = positions.get(row["name"], {})
            content["location"] = location
            if location == "exact" and "position" in believed:
                content["position"] = list(believed["position"])
            if location in ("exact", "roughly") and "landmark" in believed:
                content["landmark"] = believed["landmark"]
            content["learned"] = learned
            content["period"] = period
        out.append({"memory_id": f"knowledge:{item}", "kind": kind, "content": content})
    return out


# ----------------------------------------------------------------- static checks (the self-test)
def check_knowledge(pack, errors, warnings, info):
    """Reference and shape checks for the knowledge specs in `pack`. Appends messages to the three lists."""
    skills, metas, trades = set(pack.SKILLS), set(pack.METASKILLS), set(pack.TRADES)
    offices = set(pack.GOVERNANCE_OFFICES)
    authorities = {row.get("authority") for row in pack.GOVERNANCE_OFFICES.values()}
    infos = []
    places = set(pack.BUILDINGS) | set(pack.RESOURCE_DEPOSITS) | set(pack.WATER_SOURCES) | set(KNOWABLE_PLACES)
    jobs = set(pack.JOBS)
    topics = set(KNOWLEDGE_TOPICS)

    def check_conditions(where, conds):
        for cond in conds:
            if "any" in cond:
                check_conditions(where, cond["any"])
            elif "skill" in cond and cond["skill"] not in skills:
                errors.append(f"KNOWLEDGE {where}: unknown skill {cond['skill']}")
            elif "metaskill" in cond and cond["metaskill"] not in metas:
                errors.append(f"KNOWLEDGE {where}: unknown metaskill {cond['metaskill']}")
            elif "trade" in cond and cond["trade"] not in trades:
                errors.append(f"KNOWLEDGE {where}: unknown trade {cond['trade']}")
            elif "apprenticed" in cond and cond["apprenticed"] not in trades:
                errors.append(f"KNOWLEDGE {where}: unknown apprenticeship trade {cond['apprenticed']}")
            elif "literacy" in cond and cond["literacy"] not in LITERACY_ORDER:
                errors.append(f"KNOWLEDGE {where}: unknown literacy tier {cond['literacy']}")
            elif "office" in cond and cond["office"] not in offices:
                errors.append(f"KNOWLEDGE {where}: unknown office {cond['office']}")
            elif "authority" in cond and offices and cond["authority"] not in authorities:
                errors.append(f"KNOWLEDGE {where}: no office in this pack has authority {cond['authority']}")
            elif "authority" in cond and not offices:
                infos.append(f"KNOWLEDGE {where}: this pack has no offices, so authority {cond['authority']} is never met")
            elif "served" in cond and cond["served"] != "council":
                errors.append(f"KNOWLEDGE {where}: unknown served body {cond['served']}")
            elif not any(k in cond for k in ("skill", "metaskill", "trade", "apprenticed", "literacy",
                                             "office", "authority", "served", "years")):
                errors.append(f"KNOWLEDGE {where}: unrecognised condition {cond}")

    def check_spec(where, spec):
        if not isinstance(spec, dict):
            errors.append(f"KNOWLEDGE {where}: knowledge spec missing")
            return
        for topic in spec.get("topics", []):
            if topic not in topics:
                errors.append(f"KNOWLEDGE {where}: unknown topic {topic}")
        public = spec.get("public")
        if not isinstance(public, (int, float)) or not 0.0 <= float(public) <= 1.0:
            errors.append(f"KNOWLEDGE {where}: public must be a number from 0 to 1")
        after = spec.get("after_years", 0)
        if not isinstance(after, (int, float)) or after < 0:
            errors.append(f"KNOWLEDGE {where}: after_years must be 0 or more")
        check_conditions(where, spec.get("understanding_requires", []))

    def check_seed_roles_gone(where, row):
        if "seed_roles" in row:
            errors.append(f"KNOWLEDGE {where}: seed_roles must be replaced by a knowledge spec")

    for table_name in ("LAWS", "POLICIES", "CHARTERS"):
        for bundle in getattr(pack, table_name):
            where = f"{table_name} {bundle['name']}"
            check_spec(where, bundle.get("knowledge"))
            check_seed_roles_gone(where, bundle)
    for concept in pack.SHARED_CONCEPTS:
        check_spec(f"SHARED_CONCEPTS {concept['name']}", concept.get("knowledge"))
        check_seed_roles_gone(f"SHARED_CONCEPTS {concept['name']}", concept)
    for name, spec in PROCEDURE_KNOWLEDGE.items():
        check_spec(f"PROCEDURE_KNOWLEDGE {name}", spec)
    for row in pack.RECIPES:
        where = f"RECIPES {row['name']}"
        if "knowledge" not in row:
            errors.append(f"KNOWLEDGE {where}: knowledge spec missing")
        else:
            check_spec(where, row["knowledge"])
        check_seed_roles_gone(where, row)
    for table_name, table in (("BUILDINGS", pack.BUILDINGS), ("RESOURCE_DEPOSITS", pack.RESOURCE_DEPOSITS),
                              ("WATER_SOURCES", pack.WATER_SOURCES), ("ANIMALS", pack.ANIMALS),
                              ("GOVERNANCE_OFFICES", pack.GOVERNANCE_OFFICES), ("KIN_TERMS", pack.KIN_TERMS)):
        for name, row in table.items():
            where = f"{table_name} {name}"
            if "knowledge" not in row:
                if table_name == "GOVERNANCE_OFFICES":
                    # An office without a spec (a renamed or new office in a child pack) is known only to its
                    # holders: a default, reported, not an error.
                    infos.append(f"KNOWLEDGE {where}: no knowledge spec, so known only to its holders")
                    continue
                errors.append(f"KNOWLEDGE {where}: knowledge spec missing")
                continue
            if not row["knowledge"].get("personal"):
                check_spec(where, row["knowledge"])
            check_seed_roles_gone(where, row)
    for name, spec in KNOWABLE_PLACES.items():
        check_spec(f"KNOWABLE_PLACES {name}", spec)
    for topic, row in KNOWLEDGE_TOPICS.items():
        for skill in row.get("skills", []):
            if skill not in skills:
                errors.append(f"KNOWLEDGE_TOPICS {topic}: unknown skill {skill}")
        for cluster in row.get("clusters", []):
            if cluster not in pack.SKILL_CLUSTERS:
                errors.append(f"KNOWLEDGE_TOPICS {topic}: unknown skill cluster {cluster}")
        for meta in row.get("metaskills", []):
            if meta not in metas:
                errors.append(f"KNOWLEDGE_TOPICS {topic}: unknown metaskill {meta}")
    linked = {s for row in KNOWLEDGE_TOPICS.values() for s in row.get("skills", [])}
    unlinked = sorted(skills - linked)
    if unlinked:
        warnings.append(f"KNOWLEDGE: skills with no topic: {', '.join(unlinked)}")
    for job, value in JOB_PUBLIC.items():
        if job not in jobs:
            errors.append(f"KNOWLEDGE JOB_PUBLIC {job}: not a JOBS key")
        elif not 0.0 <= float(value) <= 1.0:
            errors.append(f"KNOWLEDGE JOB_PUBLIC {job}: must be 0..1")
    for job in sorted(jobs):
        if job not in JOB_PUBLIC:
            errors.append(f"KNOWLEDGE JOB_PUBLIC {job}: no public spread for this job")
        if job not in JOB_ROUTINE:
            errors.append(f"KNOWLEDGE JOB_ROUTINE {job}: no routine places for this job")
    for job, routine in JOB_ROUTINE.items():
        if job not in jobs:
            errors.append(f"KNOWLEDGE JOB_ROUTINE {job}: not a JOBS key")
        for place in routine:
            if place not in places:
                errors.append(f"KNOWLEDGE JOB_ROUTINE {job}: unknown place {place}")
    info.extend(sorted(set(infos)))
    info.append(f"KNOWLEDGE: {len(KNOWLEDGE_TOPICS)} topics, {len(JOB_ROUTINE)} jobs with routines, "
                f"{len(PROCEDURE_KNOWLEDGE)} procedures, {len(places)} knowable places")


# ----------------------------------------------------------------- the seeded town's shares (the self-test table)
def _practised(person):
    history = _history(person.get("history"), float(person.get("age", 30.0)))
    trades = {person.get("job", "")} | set(person.get("trades", [])) | set(history["apprenticed"])
    trades |= {f["trade"] for f in history["former_trades"]}
    return trades - {""}


def town_knowledge_shares(cast, pack, *, seed):
    """Shares of the seeded residents who are aware of, and understand, each law, policy, charter, and concept,
    and, for each trade, how many of its holders understand one of its core recipes.

    `cast` is a founding cast (worlds.bigville_town100_world.generate_cast100). Pure given the cast."""
    persons = [person_from_cast_record(r, cast, pack=pack, seed=seed) for r in cast["residents"]]
    derived = [derive_knowledge(p, pack) for p in persons]
    n = len(persons)
    items = {}
    for key in derived[0]:
        row_type = derived[0][key]["type"]
        if row_type not in ("law", "policy", "charter", "concept"):
            continue
        aware = sum(1 for d in derived if d[key]["aware"])
        understood = sum(1 for d in derived if d[key]["understands"] > 0)
        items[key] = {"type": row_type, "aware": aware / n, "understands": understood / n}
    trades = {}
    core = {}
    for recipe in pack.RECIPES:
        core.setdefault(recipe["requires"], []).append(recipe["name"])
    for trade, recipes in sorted(core.items()):
        holders = [i for i, p in enumerate(persons) if trade in _practised(p)]
        if not holders:
            continue
        holders_understanding = sum(
            1 for i in holders if any(derived[i][f"recipe:{r}"]["understands"] > 0 for r in recipes))
        residents_aware = sum(
            1 for d in derived if any(d[f"recipe:{r}"]["aware"] for r in recipes))
        trades[trade] = {"holders": len(holders), "holders_understanding": holders_understanding / len(holders),
                         "residents_aware": residents_aware / n, "recipes": len(recipes)}
    report = [f"KNOWLEDGE SHARES (seeded cast, {n} residents, seed {seed}): share aware / share understanding"]
    for key, row in items.items():
        if row["type"] == "law":
            report.append(f"  {key}: aware {row['aware']:.2f}, understands {row['understands']:.2f}")
    for key, row in items.items():
        if row["type"] != "law":
            report.append(f"  {key}: aware {row['aware']:.2f}, understands {row['understands']:.2f}")
    for trade, row in trades.items():
        report.append(f"  trade {trade} ({row['holders']} holders, {row['recipes']} recipes): holders understanding "
                      f"a core recipe {row['holders_understanding']:.2f}; residents aware of one {row['residents_aware']:.2f}")
    return {"n": n, "items": items, "trades": trades, "report": report, "persons": persons, "derived": derived}


def knowledge_shares_flags(shares, pack, errors, warnings):
    """Errors and warnings for implausible shares: a law nobody is aware of is an error; a law few are aware of,
    or a trade whose holders mostly do not understand its core recipes, is a warning (thresholds in
    KNOWLEDGE_RULES)."""
    law_min = float(KNOWLEDGE_RULES["check_law_aware_min"])
    trade_min = float(KNOWLEDGE_RULES["check_trade_understand_min"])
    for key, row in shares["items"].items():
        if row["type"] != "law":
            continue
        if row["aware"] == 0:
            errors.append(f"KNOWLEDGE SHARES {key}: no resident of the seeded cast is aware of this law")
        elif row["aware"] < law_min:
            warnings.append(f"KNOWLEDGE SHARES {key}: only {row['aware']:.2f} of residents are aware of this law "
                            f"(warning below {law_min})")
    for trade, row in shares["trades"].items():
        if row["holders_understanding"] == 0:
            errors.append(f"KNOWLEDGE SHARES trade {trade}: none of its {row['holders']} holders understands a core recipe")
        elif row["holders_understanding"] < trade_min:
            warnings.append(f"KNOWLEDGE SHARES trade {trade}: {row['holders_understanding']:.2f} of its "
                            f"{row['holders']} holders understand a core recipe (warning below {trade_min})")
