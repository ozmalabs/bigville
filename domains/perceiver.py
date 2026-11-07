"""perceiver.py -- what a resident perceives of a person or a thing, in tiers (Phase 062).

The agent view (domains/agent_view.py) asks this module how each person and thing in sight is described to a
resident. Off (PERCEPTION.enabled false, the pack default), the module is not called and the view is unchanged.

    record(game, actor, modes, pack)    the perceiver record: light, sight range, intoxication band, skill levels,
                                        literacy, and the faculty modes (a 'represented' faculty gets its full value)
    person_subject(game, other, pack)   what is there to see of a resident: its life stage, its trades, its marks
    thing_subject(words)                what is there to see of an object or container: its kind in words
    percept(kind, subject, distance, rec, pack)
                                        the tier chosen (the highest whose gates the perceiver meets), its words,
                                        and the truth (the highest tier whose subject-side gates hold)
    declared(backend, pack)             the faculty modes a backend declares (its `faculties` class attribute)

The tier table (PERCEIVER_TIERS) and the gate vocabulary (PERCEPTION.gates) live in world/perception.json. A
perceiver gate reads the observer: the light (domains/daynight via worlds/daynight.view_light), the distance
band, the intoxication band, and the skill in the subject's trade. The mark gate (Phase 062B) reads the marks the
observer sees: the world's `observable_marks(actor, distance, light)` (Phase 063) applies each mark's see_range,
see_light and visible_level, and the observer's notice_skill is applied here. The truth reads the subject's own
marks (`world.marks(actor)`), whatever the observer sees. A subject built by hand (no `observe` callable) shows its
`marks` as given.

Faculties are declared per backend: 'represented' (the backend models the faculty, so the adapter passes the full
value), 'enforced' (the adapter degrades what the backend is shown), or 'both'. Only 'represented' changes the
record in this phase; 'enforced' and 'both' keep the observer's actual value.
"""
from __future__ import annotations

from domains import shared_frames as SF
from domains.pack import load_pack
from domains.world_affordances import INTOXICATION_BANDS
from worlds import daynight as dn

FACULTIES = ("senses", "skill", "impairment", "literacy", "numeracy")
MODES = ("enforced", "represented", "both")
LIGHTS = ("day", "dim", "dark", "lamplight")
KINDS = ("person", "thing")
# The gate vocabulary and the side each gate reads (the table PERCEPTION.gates must say the same).
GATE_SIDES = {"light_not": "perceiver", "distance": "perceiver", "band_max": "perceiver",
              "trade_skill": "perceiver", "mark": "subject"}


def table(pack):
    """The PERCEPTION table of the pack (switch, bands, thresholds, the gate vocabulary)."""
    return load_pack(pack)["PERCEPTION"]


def enabled(pack):
    """True when the pack switch PERCEPTION.enabled is on."""
    return bool(table(pack)["enabled"])


def declared(backend, pack):
    """{faculty: mode} for a backend. A faculty the backend does not declare takes PERCEPTION.fallback."""
    own = dict(getattr(backend, "faculties", None) or {})
    unknown = sorted(set(own) - set(FACULTIES))
    if unknown:
        raise ValueError(f"backend declares unknown faculties {unknown}")
    fallback = table(pack)["fallback"]
    modes = {}
    for faculty in FACULTIES:
        mode = own.get(faculty, fallback)
        if mode not in MODES:
            raise ValueError(f"faculty {faculty!r} has mode {mode!r}; expected one of {MODES}")
        modes[faculty] = mode
    return modes


def _words(name):
    return " ".join(str(name or "").replace("_", " ").split())


def _literacy(world, actor):
    level = float(world.eng.node(world._actors[actor])["attrs"].get("literacy", 0.0))
    return SF.literacy_tier(level)


def record(game, actor, modes, pack):
    """The perceiver record of one resident. A 'represented' senses faculty sees in full light with the sight range
    the pack gives, a 'represented' impairment is sober, and a 'represented' skill recognises every trade."""
    world = game.world
    pk = table(pack)
    sight = int(load_pack(pack)["HEARING"]["sight_range"])
    light = dn.view_light(world, actor)
    light_known = light is not None
    if modes["senses"] == "represented":
        light = pk["light_when_off"]
        light_known = True
    else:
        if light is None:
            light = pk["light_when_off"]
        sight = dn.sight_range(world, actor, sight)
    band = world.intoxication_band(actor)
    if modes["impairment"] == "represented":
        band = INTOXICATION_BANDS[0]
    skills = dict(world.skill_levels(actor))
    return {
        "light": light,
        "light_known": light_known,
        "sight": sight,
        "band": band,
        "skills": skills,
        "skill_full": modes["skill"] == "represented",
        "literacy": "educated" if modes["literacy"] == "represented" else _literacy(world, actor),
        "modes": dict(modes),
    }


def subject_marks(game, subject):
    """The marks a resident truly carries, {name: level 0..1}: the world's `marks(actor)` (Phase 063). A test may
    script a `visible_marks(actor)` method on the world; when it exists it is read instead."""
    world = game.world
    reader = getattr(world, "visible_marks", None)
    if callable(reader):
        return {str(k): float(v) for k, v in dict(reader(subject)).items()}
    return {str(k): float(v) for k, v in dict(world.marks(subject)).items()}


def _seen_marks(subject, ctx, pack):
    """The marks the observer sees: the subject's `observe(distance, light)` rows (the world's visibility rule at
    the observer's distance and light), each kept unless the row names a notice_skill the observer lacks. A
    subject with no `observe` (built by hand) shows its marks as given."""
    observe = subject.get("observe")
    if observe is None:
        return dict(subject["marks"])
    pk = table(pack)
    seen = {}
    for row in observe(ctx["distance"], float(pk["light_level"][ctx["light"]])):
        skill = row.get("notice_skill")
        if skill and not ctx["skill_full"] and float(ctx["skills"].get(skill, 0.0)) < float(pk["notice_min_level"]):
            continue
        seen[str(row["kind"])] = float(row["level"])
    return seen


def person_subject(game, other, pack):
    """What is there to see of a resident: its life stage and job words, the main skills of its trades, its marks.
    `observe` gives what an observer at a distance and in a light could see of its marks (Phase 063)."""
    world = game.world
    attrs = world.eng.node(world._actors[other])["attrs"]
    role = str(attrs.get("role") or "")
    trades = SF.JOBS.get(role, {}).get("trades", []) if role else []
    trade_skills = [SF.trade_skills(trade)[0] for trade in trades if SF.trade_skills(trade)]
    stage = str(attrs.get("life_stage") or "adult")
    stage_noun = table(pack)["stage_nouns"].get(stage, stage)

    def observe(distance, light):
        return world.observable_marks(other, distance, light)
    return {"stage": stage_noun, "job": _words(role), "trade_skills": trade_skills,
            "marks": subject_marks(game, other), "observe": observe}


def thing_subject(kind_words):
    """What is there to see of an object or container: its kind in words."""
    return {"kind": _words(kind_words), "marks": {}, "trade_skills": []}


def _fill(words, subject):
    out = words
    for key in ("stage", "job", "kind"):
        if "{" + key + "}" in out:
            out = out.replace("{" + key + "}", str(subject.get(key, "")))
    return out


def _passes(gate, ctx, subject, pack, truth):
    """True when every condition in `gate` holds. In `truth` mode the perceiver conditions are not read (the light,
    the distance and the intoxication are the observer's), so only the subject's own facts count: a visible mark,
    and whether the subject has a trade to recognise at all."""
    pk = table(pack)
    for kind, value in gate.items():
        if kind == "mark":
            marks = subject["marks"] if truth else _seen_marks(subject, ctx, pack)
            ok = float(marks.get(value, 0.0)) >= float(pk["mark_min_level"])
        elif kind == "trade_skill":
            has_trade = bool(subject["trade_skills"])
            if truth:
                ok = has_trade
            else:
                ok = has_trade and (bool(ctx["skill_full"]) or any(
                    float(ctx["skills"].get(skill, 0.0)) >= float(pk["trade_min_level"])
                    for skill in subject["trade_skills"]))
        elif truth:
            continue
        elif kind == "light_not":
            ok = ctx["light"] not in value
        elif kind == "distance":
            ok = int(ctx["distance"]) <= int(pk["distance_bands"][value])
        elif kind == "band_max":
            ok = INTOXICATION_BANDS.index(ctx["band"]) <= INTOXICATION_BANDS.index(value)
        else:
            raise KeyError(f"no gate named {kind!r}")
        if not ok:
            return False
    return True


def _pick(kind, ctx, subject, pack, truth):
    rows = load_pack(pack)["PERCEIVER_TIERS"][kind]
    passing = [row for row in rows if _passes(row["gate"], ctx, subject, pack, truth)]
    return max(passing, key=lambda row: row["tier"])


def percept(kind, subject, distance, rec, pack):
    """The percept of one subject for one observer: {tier, words, truth_tier, truth}. Tier 0 is always met."""
    if kind not in KINDS:
        raise KeyError(f"no perceived kind named {kind!r}")
    ctx = {"light": rec["light"], "band": rec["band"], "skills": rec["skills"],
           "skill_full": rec["skill_full"], "distance": int(distance)}
    chosen = _pick(kind, ctx, subject, pack, truth=False)
    truth = _pick(kind, ctx, subject, pack, truth=True)
    return {"tier": chosen["tier"], "words": _fill(chosen["words"], subject),
            "truth_tier": truth["tier"], "truth": _fill(truth["words"], subject)}


def referee_row(subject_name, kind, distance, result):
    """One row of the referee block: what the observer was given beside what was there."""
    return {"subject": subject_name, "kind": kind, "distance": int(distance), "tier": result["tier"],
            "percept": result["words"], "truth_tier": result["truth_tier"], "truth": result["truth"]}


def summary(rec):
    """The observer's record in numbers, for the referee block."""
    return {"light": rec["light"], "light_known": rec["light_known"], "sight": rec["sight"],
            "band": rec["band"], "skills": dict(rec["skills"]), "literacy": rec["literacy"],
            "modes": dict(rec["modes"])}
