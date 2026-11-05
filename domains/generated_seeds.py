"""generated_seeds.py -- Ocelot seed files generated from a data pack.

    expected_files(pack)       -> {file name: file text}, the seeds the pack produces
    write_seeds(pack, out_dir) -> write those files; remove this pack's generated files it no longer makes
    check_seeds(pack, out_dir) -> problems: missing, stale, orphaned, or a hand-written seed in the way

The seed schema is the one Ocelot's loader reads (substrate/seed_loader.py): `id`, `version`,
`description`, `depends_on`, `nodes`, `edges`, `concepts` (name, definition, category), and `rules`
written as declarative principles (`name`, `head`, `body`). Each file also carries a `generated_from`
header: the pack name, the tables read, the record name (None for a whole-table file), and a sha256 of
the canonical JSON of those source rows. The hash covers only the rows a file is built from, so
editing one law changes that law's seed file and no other.

Which tables feed which files:
    LAWS, POLICIES, CHARTERS          gen_law_<name>, gen_policy_<name>, gen_charter_<name>  (one per record)
    GOVERNANCE_OFFICES                gen_office_<name>                                      (one per office)
    LAWMAKING_PROCEDURES              gen_procedure_lawmaking                                (one file per table)
    JUSTICE_PROCEDURES                gen_procedure_justice
    SKILLS, SKILL_CLUSTERS, METASKILLS  gen_skills
    TRADES, JOBS                      gen_trades
    KIN_TERMS                         gen_kinship
    RECIPES (know-how)                gen_recipes
    SHARED_CONCEPTS                   gen_shared_concepts
    FISCAL_INSTITUTIONS               gen_fiscal_<name>                                      (one per institution)
    TERRAIN_MOVEMENT                  bigville_terrain_movement (replaces the hand-written seed of this id)
A pack with no fiscal institutions (FISCAL_INSTITUTIONS empty, as in test_hamlet) produces no fiscal seeds.

Only `CANONICAL_PACK` writes to `CANONICAL_SEED_DIR`, the directory the Ocelot adapter loads Bigville
seeds from. The self-test runs the check for that pack alone; other packs are generated into a
directory the caller names.
"""
from __future__ import annotations

import hashlib
import json
import os

from domains.pack import PackError, canonical

GENERATOR = "tools/generate_seeds.py"
FORMAT = 1
SEED_VERSION = "1.0.0"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL_PACK = "bigville"
CANONICAL_SEED_DIR = os.path.join(REPO, "bigville", "seeds")

# Keys that never become text in a definition: the name is the concept's own name, and the knowledge
# spec and nested concept list are pack data read by other modules, not seed content.
_SKIP_IN_TEXT = ("name", "knowledge", "concepts")

# Hand-written seeds whose whole content is pack data, replaced in place by a generated file with the
# same id. bigville_terrain_movement.json held only a `terrain` table equal to the pack's
# TERRAIN_MOVEMENT and two concepts equal to SHARED_CONCEPTS (now in gen_shared_concepts). Its readers
# are id-based only (ENGINE_SEEDS, the self-test's file check, the runtime's seed list), and the world
# reads the pack table. The hand-written text is in git history at HEAD.
REPLACED_HAND_WRITTEN = ("bigville_terrain_movement",)


# ---------------------------------------------------------------- text helpers

def _plain(value):
    """JSON-ready copy of a pack value: tuples become lists, sets sorted lists, tuple keys strings."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=lambda m: json.dumps(m, sort_keys=True))
    return value


def _text(value):
    if isinstance(value, str):
        return value
    return json.dumps(_plain(value), sort_keys=True, ensure_ascii=False)


def _describe(record, skip=()):
    """`key: value` pairs over a record's own fields, in key order, joined by '; '."""
    return "; ".join(f"{key}: {_text(record[key])}" for key in sorted(record)
                     if key not in skip and key not in _SKIP_IN_TEXT)


def _triple(reference):
    if isinstance(reference, dict) and {"subject", "predicate", "object"} <= set(reference):
        return f"{reference['subject']} {reference['predicate']} {reference['object']}"
    return _describe(reference or {})


def _concept(name, definition, category):
    return {"name": name, "definition": definition, "category": category}


def _principle(name, head, body):
    return {"name": name, "head": head, "body": body}


def _digest(source):
    return hashlib.sha256(canonical(source).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the plan

def plan(pack):
    """{seed id: seed dict} for every file this pack produces, in id order."""
    seeds = {}

    def add(stem, tables, source, concepts, rules, text, record=None, extra=None):
        if stem in seeds:
            raise PackError(f"generated seed id '{stem}' is produced twice")
        seeds[stem] = {
            "id": stem,
            "version": SEED_VERSION,
            "description": f"{text} Generated from the '{pack.name}' pack ({', '.join(tables)}). "
                           f"Do not edit: regenerate with {GENERATOR}.",
            "depends_on": [],
            "self_load_only": True,
            "nodes": [],
            "edges": [],
            "concepts": concepts,
            "rules": rules,
            "generated_from": {
                "pack": pack.name,
                "generator": GENERATOR,
                "format": FORMAT,
                "tables": list(tables),
                "record": record,
                "sha256": _digest(source),
            },
            **(extra or {}),
        }

    # Laws, policies, and charters: one seed per record, from its own concepts and identity.
    for table, prefix in (("LAWS", "gen_law"), ("POLICIES", "gen_policy"), ("CHARTERS", "gen_charter")):
        for rec in pack[table]:
            name = rec["name"]
            stem = f"{prefix}_{name}"
            title = rec.get("title", name)
            concepts = [_concept(c["name"], _triple(c.get("reference")), c.get("abstraction", "concept"))
                        for c in rec.get("concepts", [])]
            if not concepts:
                concepts = [_concept(name, title, rec.get("kind", "institution"))]
            rules = [_principle(f"{stem}_identity", title, _describe(rec, skip=("title", "concepts")))]
            add(stem, (table,), rec, concepts, rules,
                f"{title} ({rec.get('kind', 'institution')}, {rec.get('scope', 'village')} scope).",
                record=name)

    # Offices: one seed per office. Its authority, records, and appointments are the concept.
    for name, rec in pack["GOVERNANCE_OFFICES"].items():
        concepts = [_concept(f"office_{name}", _describe(rec), "office")]
        add(f"gen_office_{name}", ("GOVERNANCE_OFFICES",), rec, concepts, [],
            f"Office of {name.replace('_', ' ')}.", record=name)

    # Procedures: each stage of a procedure is a concept, so one file per procedure table.
    for table, short in (("LAWMAKING_PROCEDURES", "lawmaking"), ("JUSTICE_PROCEDURES", "justice")):
        stages = pack[table]
        concepts = [_concept(f"{short}_{stage}", _describe(rec), "procedure")
                    for stage, rec in stages.items()]
        add(f"gen_procedure_{short}", (table,), stages, concepts, [],
            f"The {short} procedure, one concept per stage.")

    # Skills: each skill with its cluster, each cluster, and each metaskill.
    cluster_of = pack["_SKILL_CLUSTER"]
    skills = pack["SKILLS"]
    clusters = pack["SKILL_CLUSTERS"]
    metaskills = pack["METASKILLS"]
    concepts = [_concept(f"skill_{skill}", _describe(dict(rec, cluster=cluster_of.get(skill, ""))), "skill")
                for skill, rec in skills.items()]
    concepts += [_concept(f"skill_cluster_{name}", _describe(rec), "skill_cluster")
                 for name, rec in clusters.items()]
    concepts += [_concept(f"metaskill_{name}", _describe(rec), "metaskill")
                 for name, rec in metaskills.items()]
    add("gen_skills", ("SKILLS", "SKILL_CLUSTERS", "METASKILLS"),
        {"SKILLS": skills, "SKILL_CLUSTERS": clusters, "METASKILLS": metaskills},
        concepts, [], "Skills, skill clusters, and metaskills.")

    # Trades and jobs.
    concepts = [_concept(f"trade_{name}", _describe(rec), "trade") for name, rec in pack["TRADES"].items()]
    concepts += [_concept(f"job_{name}", _describe(rec), "job") for name, rec in pack["JOBS"].items()]
    add("gen_trades", ("TRADES", "JOBS"), {"TRADES": pack["TRADES"], "JOBS": pack["JOBS"]},
        concepts, [], "Trades and the jobs that exercise them.")

    # Kin terms: one concept per term (generation, reciprocal term, genealogical paths, obligations).
    concepts = [_concept(f"kin_{term}", _describe(rec), "kin_term") for term, rec in pack["KIN_TERMS"].items()]
    add("gen_kinship", ("KIN_TERMS",), pack["KIN_TERMS"], concepts, [], "Kin terms.")

    # Recipes as know-how: one principle per recipe.
    rules = []
    for rec in pack["RECIPES"]:
        name = rec["name"]
        out_kind, out_qty = rec["out"][0], rec["out"][1]
        made = (f"makes {out_kind} x{out_qty}" if out_kind and float(out_qty) > 0
                else "makes no product")
        rules.append(_principle(
            f"{name}_know_how",
            f"{name} {made} from a {rec.get('requires', 'no trade')}",
            _describe(rec, skip=("out", "requires"))))
    add("gen_recipes", ("RECIPES",), pack["RECIPES"], [], rules, "Recipes as know-how.")

    # Shared concepts: one concept per shared reference.
    concepts = [_concept(rec["name"], _triple(rec.get("reference")), "shared") for rec in pack["SHARED_CONCEPTS"]]
    add("gen_shared_concepts", ("SHARED_CONCEPTS",), pack["SHARED_CONCEPTS"], concepts, [],
        "Shared concepts that residents can hold in common.")

    # Fiscal institutions (Phase 011): one seed per institution, its levy, base, purse, and the seed rules it came from.
    for name, rec in pack["FISCAL_INSTITUTIONS"].items():
        concepts = [_concept(f"fiscal_{name}", _describe(rec), "fiscal_institution")]
        add(f"gen_fiscal_{name}", ("FISCAL_INSTITUTIONS",), rec, concepts, [],
            f"Fiscal institution: {rec.get('title', name)}.", record=name)

    # Terrain movement: the hand-written seed of the same id is replaced (see REPLACED_HAND_WRITTEN).
    terrain = pack["TERRAIN_MOVEMENT"]
    add("bigville_terrain_movement", ("TERRAIN_MOVEMENT",), terrain, [], [],
        "Terrain movement: each terrain's relative speed, move time, and stamina multiplier. "
        "The world's map and actions read the same table from the pack.",
        extra={"terrain": terrain})

    names = [c["name"] for seed in seeds.values() for c in seed["concepts"]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise PackError(f"generated concept names are not unique: {dupes}")
    return dict(sorted(seeds.items()))


def render(seed):
    """The file text for one seed: sorted keys, 2-space indent, LF line ends, final newline."""
    return json.dumps(seed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def expected_files(pack):
    """{file name: file text} for every seed the pack produces."""
    return {f"{stem}.json": render(seed) for stem, seed in plan(pack).items()}


# ---------------------------------------------------------------- reading the directory

def _header(path):
    """The `generated_from` header of a seed file, or None for a hand-written file or an unreadable one."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b'"generated_from"' not in raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    header = data.get("generated_from") if isinstance(data, dict) else None
    return header if isinstance(header, dict) else None


def _generated_here(pack, out_dir, name):
    header = _header(os.path.join(out_dir, name))
    return header is not None and header.get("pack") == pack.name


def _orphans(pack, out_dir, expected):
    """Files this pack generated earlier that it no longer produces."""
    if not os.path.isdir(out_dir):
        return []
    return sorted(name for name in os.listdir(out_dir)
                  if name.endswith(".json") and name not in expected and _generated_here(pack, out_dir, name))


def _blockers(pack, out_dir, expected):
    """Expected files that already exist and were not generated by this pack (hand-written, or another pack).
    The ids in REPLACED_HAND_WRITTEN are the exception: their hand-written seed is replaced on purpose."""
    replaced = {f"{stem}.json" for stem in REPLACED_HAND_WRITTEN}
    return sorted(name for name in expected
                  if name not in replaced
                  and os.path.isfile(os.path.join(out_dir, name)) and not _generated_here(pack, out_dir, name))


# ---------------------------------------------------------------- write and check

def write_seeds(pack, out_dir):
    """Write every seed the pack produces into `out_dir`, and remove this pack's generated files it no
    longer makes. Refuses to overwrite a hand-written seed. Returns the names written."""
    expected = expected_files(pack)
    blocked = _blockers(pack, out_dir, expected)
    if blocked:
        raise PackError(f"refusing to overwrite hand-written seeds in {out_dir}: {blocked}")
    os.makedirs(out_dir, exist_ok=True)
    for name, text in expected.items():
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(text.encode("utf-8"))
    for name in _orphans(pack, out_dir, expected):
        os.remove(os.path.join(out_dir, name))
    return sorted(expected)


def check_seeds(pack, out_dir):
    """Problems between the seed files in `out_dir` and what the pack produces (an empty list is clean)."""
    expected = expected_files(pack)
    problems = []
    for name, text in expected.items():
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            problems.append(f"{name}: missing (run {GENERATOR})")
            continue
        with open(path, "rb") as fh:
            if fh.read() != text.encode("utf-8"):
                problems.append(f"{name}: stale, the pack '{pack.name}' no longer produces these bytes "
                                f"(run {GENERATOR})")
    for name in _orphans(pack, out_dir, expected):
        problems.append(f"{name}: generated from '{pack.name}' but the pack no longer produces it "
                        f"(delete it or run {GENERATOR})")
    for name in _blockers(pack, out_dir, expected):
        problems.append(f"{name}: a hand-written seed is in the way of generated output")
    return problems
