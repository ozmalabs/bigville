"""life_stage_check.py -- self-test checks for life-stage inheritance (Phase 070c).

What it checks, for the pack at `pack_path`:

* LIFE_STAGES: every stage has numeric age_min <= age_max; an `inherits` names an existing stage; the inheritance has
  no cycle (domains/pack.py compiles LIFE_STAGE_CHAIN and would raise, so this reports it as an error first).
* The bands are contiguous whole years: sorted by age_min, the first starts at 0, and each band starts one year after
  the band below ends. A gap or an overlap is an error (the whole-year rule of DEPENDANTS-off would send a gap age to elder).
* Each inheriting stage is covered wherever its nearest ancestor is covered, in every STAGE_KEYED table (after the
  loader's fill). A missing entry is an error.
* The lexicon names every stage, self and other (LEXICON_QUANTITIES.life_stage).
* The info line lists each inheritance (stage, parent, and the sleep need the stage gives).

APPROX: none; this module only checks structure. The pack data is in packs/*/world/life_stages.json.
"""
from __future__ import annotations

from domains.pack import load_pack, stage_dicts


def _chain_problems(stages, errors):
    """Errors for unknown parents and cycles. Returns {stage: [stage, ancestor, ...]} for the stages that resolve."""
    chain = {}
    for stage, row in stages.items():
        seen = [stage]
        parent = row.get("inherits")
        while parent:
            if parent not in stages:
                errors.append(f"LIFE_STAGES[{stage}].inherits names {parent!r}, which is not a life stage")
                break
            if parent in seen:
                errors.append(f"LIFE_STAGES inheritance has a cycle: {' -> '.join(seen + [parent])}")
                break
            seen.append(parent)
            parent = stages[parent].get("inherits")
        else:
            chain[stage] = seen
    return chain


def check_life_stages(pack_path, errors, warnings, info):
    pack = load_pack(pack_path)
    if "LIFE_STAGES" not in pack:
        return
    stages = pack["LIFE_STAGES"]
    for stage, row in stages.items():
        for field in ("age_min", "age_max"):
            if not isinstance(row.get(field), (int, float)) or isinstance(row.get(field), bool):
                errors.append(f"LIFE_STAGES[{stage}].{field} must be a whole year, not {row.get(field)!r}")
        if isinstance(row.get("age_min"), (int, float)) and isinstance(row.get("age_max"), (int, float)):
            if float(row["age_min"]) > float(row["age_max"]):
                errors.append(f"LIFE_STAGES[{stage}]: age_min {row['age_min']} is above age_max {row['age_max']}")
    chain = _chain_problems(stages, errors)

    bands = sorted(stages.items(), key=lambda item: float(item[1]["age_min"]))
    if bands and float(bands[0][1]["age_min"]) != 0.0:
        errors.append(f"LIFE_STAGES: the first band {bands[0][0]!r} must start at age 0, not {bands[0][1]['age_min']}")
    for (below, lower), (above, upper) in zip(bands, bands[1:]):
        if float(lower["age_max"]) + 1.0 != float(upper["age_min"]):
            errors.append(f"LIFE_STAGES: {below!r} ends at {lower['age_max']} and {above!r} starts at {upper['age_min']}; "
                          "the bands must be contiguous whole years")

    if "STAGE_KEYED" in pack:
        for path in pack["STAGE_KEYED"].get("paths", []):
            if str(path).split(".")[0] not in pack.tables:
                info.append(f"STAGE_KEYED: {path!r} is not in this pack (skipped)")
                continue
            tables = stage_dicts(pack.tables, str(path))
            if not tables:
                if "*" in str(path):
                    info.append(f"STAGE_KEYED: {path!r} has no rows in this pack (skipped)")
                else:
                    errors.append(f"STAGE_KEYED: path {path!r} names no table in this pack")
                continue
            for table in tables:
                for stage, ancestors in chain.items():
                    if stage in table:
                        continue
                    if any(ancestor in table for ancestor in ancestors[1:]):
                        errors.append(f"STAGE_KEYED {path}: {stage!r} inherits an entry it does not have")

    for key in ("self", "other"):
        words = (pack["LEXICON_QUANTITIES"].get("life_stage", {}).get(key, {}) if "LEXICON_QUANTITIES" in pack else {})
        for stage in stages:
            if stage not in words:
                errors.append(f"LEXICON_QUANTITIES.life_stage.{key} has no phrase for life stage {stage!r}")

    inherits = [f"{stage} from {row['inherits']}" for stage, row in stages.items() if row.get("inherits")]
    if inherits:
        info.append(f"LIFE_STAGES: inheritance ({'; '.join(inherits)}); bands "
                    + ", ".join(f"{stage} {int(row['age_min'])}-{int(row['age_max'])}" for stage, row in bands))
