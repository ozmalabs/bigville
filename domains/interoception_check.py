"""interoception_check.py -- self-test checks for a pack's interoception tables (Phase 069).

    check_interoception(pack_name, errors, warnings, info)

Called from the entity self-test (domains/bigville_entities.check_consistency). It reads the pack directly with
domains/pack.load_pack and checks:
- the tables exist (ANATOMY, QUALITY_TREE, VOCALISATIONS, CHANNELS, SIGNAL_SOURCES, PATTERNS, FEELING,
  INTEROCEPTION);
- each tree has exactly one root, every parent exists, and every node reaches the root (no cycle, no node
  unreachable from its root), and labels are unique words with no digit;
- every quality node has a vocalisation with forms made of letters only;
- every channel cap is a whole number no deeper than its tree;
- every signal source names a read the body computes, a channel, a quality node, a locus node, a pattern, and a
  floor below its ceiling with an awareness in [0, 1];
- the depth rule, the acuity range and life-stage factors, the attention values, the renderer and the feeling
  levels are present and in range; felt_body_keys and forbidden_words are plain lists.
Also reports the number of sources and of felt keys in the info list.
"""
from __future__ import annotations

import re

from domains import interoception as I
from domains.pack import PackError, load_pack

REQUIRED = ("ANATOMY", "QUALITY_TREE", "VOCALISATIONS", "CHANNELS", "SIGNAL_SOURCES", "PATTERNS", "FEELING",
            "INTEROCEPTION")
DEPTH_KEYS = ("base", "intensity_weight", "acuity_weight", "attention_weight", "impairment_weight", "jitter")
ATTENTION_KINDS = ("idle", "absorbed", "asleep")
LETTERS = re.compile(r"^[a-z]+$")
_DIGIT = re.compile(r"\d")


def _rows(table):
    return {name: row for name, row in table.items() if not str(name).startswith("_")}


def _tree(name, table, errors):
    """Check one tree. Returns the set of nodes (empty when the tree is broken)."""
    rows = _rows(table)
    roots = [node for node, row in rows.items() if isinstance(row, dict) and row.get("parent") is None]
    if len(roots) != 1:
        errors.append(f"INTEROCEPTION: {name} must have exactly one root (parent null), has {sorted(roots)}")
        return set()
    ok = True
    for node, row in rows.items():
        if not isinstance(row, dict):
            errors.append(f"INTEROCEPTION: {name}[{node}] must be a row with a parent")
            ok = False
            continue
        parent = row.get("parent")
        if parent is not None and parent not in rows:
            errors.append(f"INTEROCEPTION: {name}[{node}] has parent {parent!r}, which is not in {name}")
            ok = False
    if not ok:
        return set()
    for node in rows:
        try:
            I.depth_of(rows, node)      # raises on a cycle; with one root and no missing parent, it reaches the root
        except (KeyError, ValueError) as exc:
            errors.append(f"INTEROCEPTION: {name}[{node}] does not reach the root {roots[0]!r} ({exc})")
            ok = False
    return set(rows) if ok else set()


def check_interoception(pack_name, errors, warnings, info):
    """Run every interoception check on the named pack, appending to errors, warnings and info."""
    try:
        pack = load_pack(pack_name)
    except PackError as exc:
        errors.append(f"INTEROCEPTION: cannot load pack '{pack_name}': {exc}")
        return
    missing = [name for name in REQUIRED if name not in pack]
    if missing:
        errors.append(f"INTEROCEPTION: pack '{pack_name}' has no {', '.join(missing)} table")
        return
    before = len(errors)
    anatomy = _rows(pack["ANATOMY"])
    qtree = _rows(pack["QUALITY_TREE"])
    anatomy_ok = _tree("ANATOMY", pack["ANATOMY"], errors)
    qtree_ok = _tree("QUALITY_TREE", pack["QUALITY_TREE"], errors)
    labels = [str(row.get("label", "")) for row in anatomy.values()]
    for label in labels:
        if not label.strip() or _DIGIT.search(label):
            errors.append(f"INTEROCEPTION: an ANATOMY label is empty or has a digit: {label!r}")
    if len(set(labels)) != len(labels):
        errors.append("INTEROCEPTION: two ANATOMY regions share a label, so a felt place would be ambiguous")
    vocal = _rows(pack["VOCALISATIONS"])
    for node in qtree:
        if node not in vocal:
            errors.append(f"INTEROCEPTION: quality node {node!r} has no VOCALISATIONS row")
    for node, row in vocal.items():
        forms = row.get("forms") if isinstance(row, dict) else None
        if node not in qtree:
            errors.append(f"INTEROCEPTION: VOCALISATIONS[{node}] is not a QUALITY_TREE node")
        if not isinstance(forms, list) or not forms:
            errors.append(f"INTEROCEPTION: VOCALISATIONS[{node}] needs a non-empty forms list")
            continue
        for form in forms:
            if not isinstance(form, str) or not LETTERS.match(form):
                errors.append(f"INTEROCEPTION: VOCALISATIONS[{node}] form {form!r} must be letters only (a sound)")
    channels = _rows(pack["CHANNELS"])
    for name, row in channels.items():
        for key, tree_name, tree_ok, limit in (("quality_cap", "QUALITY_TREE", qtree_ok, qtree),
                                               ("locus_cap", "ANATOMY", anatomy_ok, anatomy)):
            cap = row.get(key)
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
                errors.append(f"INTEROCEPTION: CHANNELS[{name}].{key} must be a whole number of at least 0")
                continue
            if tree_ok and cap > I.max_depth(limit):
                errors.append(f"INTEROCEPTION: CHANNELS[{name}].{key} is {cap}, deeper than {tree_name} "
                              f"(its deepest level is {I.max_depth(limit)})")
    sources = _rows(pack["SIGNAL_SOURCES"])
    patterns = _rows(pack["PATTERNS"])
    for name, row in sources.items():
        if not isinstance(row, dict):
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] must be a row")
            continue
        if row.get("read") not in I.READS:
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] names read {row.get('read')!r}; the body computes "
                          f"{list(I.READS)}")
        if row.get("channel") not in channels:
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] names channel {row.get('channel')!r}, not in CHANNELS")
        if qtree_ok and row.get("quality") not in qtree:
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] names quality {row.get('quality')!r}, not a "
                          f"QUALITY_TREE node")
        if anatomy_ok and row.get("locus") not in anatomy:
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] names locus {row.get('locus')!r}, not an ANATOMY node")
        if row.get("pattern") not in patterns:
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] names pattern {row.get('pattern')!r}, not in PATTERNS")
        try:
            if not float(row["floor"]) < float(row["ceiling"]):
                errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] needs floor below ceiling")
            if not 0.0 <= float(row["awareness"]) <= 1.0:
                errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}].awareness must be in [0, 1]")
        except (KeyError, TypeError, ValueError):
            errors.append(f"INTEROCEPTION: SIGNAL_SOURCES[{name}] needs numeric floor, ceiling and awareness")
    for name, row in patterns.items():
        if not isinstance(row.get("repeat"), int) or isinstance(row.get("repeat"), bool) or row["repeat"] < 1:
            errors.append(f"INTEROCEPTION: PATTERNS[{name}].repeat must be a whole number of at least 1")
        if not isinstance(row.get("tail"), str) or _DIGIT.search(row.get("tail", "")):
            errors.append(f"INTEROCEPTION: PATTERNS[{name}].tail must be a string with no digit")
    rules = pack["INTEROCEPTION"]
    depth = rules.get("depth", {})
    for key in DEPTH_KEYS:
        if not isinstance(depth.get(key), (int, float)) or isinstance(depth.get(key), bool):
            errors.append(f"INTEROCEPTION: depth.{key} must be a number")
    acuity = rules.get("acuity", {})
    rng = acuity.get("range", [])
    if not (isinstance(rng, list) and len(rng) == 2 and 0.0 < float(rng[0]) <= float(rng[1])):
        errors.append("INTEROCEPTION: acuity.range must be [low, high] with 0 < low <= high")
    stages = acuity.get("life_stage", {})
    for stage in pack["LIFE_STAGES"]:
        if stage not in stages:
            errors.append(f"INTEROCEPTION: acuity.life_stage has no factor for life stage {stage!r}")
    attention = rules.get("attention", {})
    for kind in ATTENTION_KINDS:
        if kind not in attention:
            errors.append(f"INTEROCEPTION: attention has no value for {kind!r}")
    for key in ("signals_max", "stretch_max"):
        value = rules.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"INTEROCEPTION: {key} must be a whole number of at least 0")
    feeling = pack["FEELING"]
    levels = feeling.get("levels", [])
    if not levels or float(levels[0]["min"]) != 0.0 or any(
            float(a["min"]) >= float(b["min"]) for a, b in zip(levels, levels[1:])):
        errors.append("INTEROCEPTION: FEELING.levels must start at min 0 and rise in min")
    for key in ("felt_body_keys", "forbidden_words"):
        value = rules.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"INTEROCEPTION: {key} must be a list of strings")
    if len(errors) == before:
        info.append(f"INTEROCEPTION ({pack.name}): {len(anatomy)} body regions, {len(qtree)} quality kinds, "
                    f"{len(sources)} signal sources; all interoception checks pass")
