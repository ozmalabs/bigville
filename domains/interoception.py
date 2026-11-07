"""interoception.py -- what a body lets its mind feel (Phase 069).

Pure functions over a body's tables (packs/<pack>/world/interoception.json) and its reads. The world's body
object (worlds/body.py) collects the reads and the interoceptor record and calls these functions. Nothing here
touches the world.

    draw(seed, *parts)              a stateless draw in [0, 1), keyed on the seed and the parts (no random state)
    resolve(tree, node, depth)      the ancestor of `node` at `depth` (the whole node when depth is deeper)
    derive(tables, reads, record, seed, actor, turn, previous)
                                    every source's truth, the felt signals and the background feeling
    felt_body(derived)              the mind's view: {feeling?, signals}, sounds and places only, no cause
    referee_block(derived)          the truth beside each signal: source, true quality and locus, depths chosen
    render_felt_body(felt)          the felt body as plain lines, for a terminal (a caller's rendering only)

The depth rule and the renderer are described in the pack (INTEROCEPTION, VOCALISATIONS, PATTERNS). Every
resolved depth is the lower of: the raw depth from the rule, the channel's cap, and the true node's own depth.
"""
from __future__ import annotations

import hashlib
import math
import re

# The reads a source may name. Each one is computed by an embodiment (worlds/body.py); a source naming another
# read is a self-test error.
READS = ("hunger", "exertion", "exhaustion", "chill", "wetness", "illness", "intoxication", "harm")
VOWELS = "aeiouy"


def _rows(table):
    """A table's rows, without its '_doc' and other '_' keys."""
    return {name: row for name, row in table.items() if not str(name).startswith("_")}


def draw(seed, *parts):
    """A draw in [0, 1) that depends only on the seed and `parts`. Keyed by a hash, so it is the same in every
    process (Python's own hash() is salted per run and is not used)."""
    text = ":".join(str(part) for part in (seed,) + parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def depth_of(tree, node):
    """Steps from the root to `node` (the root is 0). KeyError for a node not in the tree. Keys starting with '_'
    are table comments, not nodes."""
    tree = _rows(tree)
    depth = 0
    seen = set()
    current = node
    while True:
        if current not in tree:
            raise KeyError(f"node {current!r} is not in the tree")
        if current in seen:
            raise ValueError(f"tree has a cycle at {current!r}")
        seen.add(current)
        parent = tree[current].get("parent")
        if parent is None:
            return depth
        current = parent
        depth += 1


def max_depth(tree):
    """The deepest node's depth in a tree (0 for a root alone)."""
    rows = _rows(tree)
    return max(depth_of(rows, node) for node in rows)


def resolve(tree, node, depth):
    """The ancestor of `node` at `depth` steps from the root. A depth at or beyond the node's own depth gives the
    node itself; depth 0 is always the root. Negative depths are read as 0."""
    own = depth_of(tree, node)
    target = min(max(int(depth), 0), own)
    current = node
    for _ in range(own - target):
        current = tree[current]["parent"]
    return current


def _clamp(value, low, high):
    return max(low, min(high, value))


def intensity_of(spec, read):
    """A source's intensity: its read scaled from floor (0) to ceiling (1) and clamped. A read that is not finite
    gives 0."""
    value = float(read)
    if not math.isfinite(value):
        return 0.0
    floor, ceiling = float(spec["floor"]), float(spec["ceiling"])
    if ceiling <= floor:
        return 1.0 if value >= ceiling else 0.0
    return _clamp((value - floor) / (ceiling - floor), 0.0, 1.0)


def acuity_of(rules, seed, actor, life_stage):
    """A resident's acuity, drawn once from the pack's range and scaled by the life stage. Kept by the body."""
    low, high = (float(x) for x in rules["range"])
    stage = float(rules["life_stage"].get(str(life_stage), 1.0))
    return (low + (high - low) * draw(seed, "acuity", actor)) * stage


def raw_depth(rules, intensity, acuity, attention, impairment, jitter):
    """The depth rule, before the caps. Monotone: intensity, acuity and attention raise it; impairment lowers it.
    `jitter` is a value in [-1, 1] (a draw), scaled by the pack's jitter."""
    d = rules["depth"]
    return (float(d["base"]) + float(d["intensity_weight"]) * intensity
            + float(d["acuity_weight"]) * (acuity - 1.0)
            + float(d["attention_weight"]) * attention
            - float(d["impairment_weight"]) * impairment
            + float(d["jitter"]) * jitter)


def chosen_depth(raw, cap, true_depth):
    """The depth a feeling is placed at: floor of the raw depth, at least 0, at most the channel cap and at most
    the true node's own depth."""
    return max(0, min(int(math.floor(raw)), int(cap), int(true_depth)))


def _first_vowel_index(form):
    for index, letter in enumerate(form):
        if letter in VOWELS:
            return index
    return len(form) - 1


def stretch(form, intensity, rules):
    """The form with its first vowel (or last letter) repeated 1 + round(intensity x stretch_max) times in all."""
    index = _first_vowel_index(form)
    extra = int(round(_clamp(intensity, 0.0, 1.0) * float(rules["stretch_max"])))
    return form[:index] + form[index] * (1 + extra) + form[index + 1:]


def trend_of(intensity, previous, delta):
    """'rising' or 'fading' against the last turn's intensity by more than `delta`; None when steady or new."""
    if previous is None:
        return None
    change = float(intensity) - float(previous)
    if change > float(delta):
        return "rising"
    if change < -float(delta):
        return "fading"
    return None


def sound(tables, quality, intensity, pattern, seed):
    """The sound of a quality node at an intensity, in a pattern. The form is chosen by a draw keyed on the seed and
    the node, so it does not depend on which resident feels it: two residents who feel the same node say the same
    sound. Never a word and never a cause."""
    vocal = _rows(tables["vocalisations"])[quality]["forms"]
    form = vocal[int(draw(seed, "form", quality) * len(vocal)) % len(vocal)]
    word = stretch(form, intensity, tables["rules"])
    spec = _rows(tables["patterns"])[pattern]
    text = " ".join([word] * int(spec["repeat"]))
    tail = str(spec["tail"])
    if not tail and float(intensity) >= float(tables["rules"]["strong_at"]):
        tail = "!"
    return text + tail


def level_of(feeling_table, total):
    """The coarse word for the background feeling's total: the highest level whose min is at or below it."""
    label = None
    best = -1.0
    for level in feeling_table["levels"]:
        minimum = float(level["min"])
        if minimum <= float(total) and minimum >= best:
            best = minimum
            label = str(level["label"])
    return label


def derive(tables, reads, record, seed, actor, turn, previous=None):
    """Every source's truth for one resident at one turn.

    tables    {"anatomy", "quality_tree", "vocalisations", "channels", "sources", "patterns", "feeling", "rules"}
              (each a pack table, '_'-keys allowed). "sources" is SIGNAL_SOURCES.
    reads     {read name: value} for every read a source names.
    record    the interoceptor record: {"acuity", "attention", "impairment"} (plain numbers).
    previous  {source name: intensity} at the last tick, or None. It gives the trend of each source.

    Returns {"sources": [row...], "feeling": {"sound", "level"} or None, "signals": [row...]} where a row carries
    the truth (quality_true, locus_true, the depths chosen, the shown nodes) and `felt` (above awareness)."""
    anatomy = _rows(tables["anatomy"])
    qtree = _rows(tables["quality_tree"])
    channels = _rows(tables["channels"])
    rules = tables["rules"]
    feeling_table = tables["feeling"]
    rows = []
    for name, spec in sorted(_rows(tables["sources"]).items()):
        read = str(spec["read"])
        intensity = intensity_of(spec, reads.get(read, 0.0))
        jitter = 2.0 * draw(seed, "jitter", actor, turn, name) - 1.0
        raw = raw_depth(rules, intensity, float(record["acuity"]), float(record["attention"]),
                        float(record["impairment"]), jitter)
        channel = channels[str(spec["channel"])]
        q_depth = chosen_depth(raw, channel["quality_cap"], depth_of(qtree, spec["quality"]))
        l_depth = chosen_depth(raw, channel["locus_cap"], depth_of(anatomy, spec["locus"]))
        q_shown = resolve(qtree, spec["quality"], q_depth)
        l_shown = resolve(anatomy, spec["locus"], l_depth)
        last = None if previous is None else previous.get(name)
        trend = trend_of(intensity, last, rules["trend_delta"])
        pattern = trend or str(spec["pattern"])
        rows.append({
            "source": name,
            "read": read,
            "intensity": round(intensity, 6),
            "felt": intensity > 0.0 and intensity >= float(spec["awareness"]),
            "channel": str(spec["channel"]),
            "quality_true": str(spec["quality"]),
            "quality_depth": q_depth,
            "quality_shown": q_shown,
            "locus_true": str(spec["locus"]),
            "locus_depth": l_depth,
            "locus_shown": l_shown,
            "pattern": pattern,
            "sound": sound(tables, q_shown, intensity, pattern, seed),
            "where": str(anatomy[l_shown]["label"]),
        })
    total = min(1.0, sum(row["intensity"] for row in rows))
    feeling = None
    if total >= float(feeling_table["floor"]) and total > 0.0:
        feeling = {"sound": sound(tables, _root(qtree), total, "steady", seed),
                   "level": level_of(feeling_table, total)}
    signals = sorted((row for row in rows if row["felt"]),
                     key=lambda row: (-row["intensity"], row["source"]))
    signals = signals[:int(rules["signals_max"])]
    return {"sources": rows, "feeling": feeling, "signals": signals, "total": round(total, 6)}


def _root(tree):
    for node, row in tree.items():
        if not node.startswith("_") and row.get("parent") is None:
            return node
    raise KeyError("quality tree has no root")


def intensities(tables, reads):
    """{source name: intensity} for every source (felt or not). The body keeps these for the trend."""
    return {name: intensity_of(spec, reads.get(str(spec["read"]), 0.0))
            for name, spec in sorted(_rows(tables["sources"]).items())}


def felt_body(derived):
    """What the mind may feel: the background feeling and the felt signals, as sounds and places. Keys: feeling
    (omitted when absent), and signals (a list, possibly empty), each signal {sound, where}. No cause, no depth,
    no number."""
    out = {}
    if derived["feeling"] is not None:
        out["feeling"] = {"sound": derived["feeling"]["sound"], "level": derived["feeling"]["level"]}
    out["signals"] = [{"sound": row["sound"], "where": row["where"]} for row in derived["signals"]]
    return out


def referee_block(derived, record):
    """The truth, for the referee mode and tests: the record used, and each source with its true quality and
    locus, the depths chosen, the nodes shown and whether it was felt."""
    return {
        "record": {key: record[key] for key in sorted(record)},
        "feeling": derived["feeling"],
        "sources": [dict(row) for row in derived["sources"]],
        "signals": [row["source"] for row in derived["signals"]],
    }


def render_felt_body(felt):
    """The felt body as plain lines for a terminal: the feeling first, then each signal with its place. A caller
    (the terminal interface) decides how to draw them; this only words what the body reports."""
    lines = []
    feeling = felt.get("feeling")
    if feeling:
        lines.append(f"feeling: {feeling['sound']} ({feeling['level']})")
    for signal in felt.get("signals", []):
        lines.append(f"  {signal['sound']} -- {signal['where']}")
    return lines


def normal_letters(text):
    """A sound with its punctuation dropped and each run of one letter cut to one: 'uuuugh!' -> 'ugh'."""
    letters = re.sub(r"[^a-z]", "", str(text).lower())
    return re.sub(r"(.)\1+", r"\1", letters)
