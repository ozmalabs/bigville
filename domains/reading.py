"""reading.py -- what a resident reads of a written mark (Phase 064).

A written mark is a physical object whose id is a key of WRITTEN_MARKS (world/literacy.json). The agent view asks this
module for each mark in sight (`writing_rows`). Off (READING.enabled false, the pack default), the view has no
`writing` section and nothing is learned.

    known_words(game, actor, pack)      the words the resident recognises: its trade's seed, its name, the common
                                        numerals, and the words it has learned from use (held memories)
    percept(mark, tier, known, num_row, pack, truth)
                                        what the resident reads of one mark: its literacy tier chooses the reading
                                        ('words' amid squiggles, 'short', or 'full'); a mark with no known word is
                                        'unreadable'; a price is in the resident's numeracy words
    writing_rows(game, actor, rec, pack, log)
                                        the rows for the view, each mark in sight; the referee rows go to `log`; a word
                                        whose referent is carried or in view is learned, after the rows are built

The percept is the resident's own reading. The truth (the full text, the figure of the price) is for the referee block
only. A 'represented' literacy gives the full text, as the simple backend does.
"""
from __future__ import annotations

import re

from domains import numeracy
from domains import shared_frames as SF
from domains.pack import load_pack

WORD = re.compile(r"[A-Za-z]+")
PRICE = "{price}"


def table(pack):
    """The READING table: the switch, the squiggle, the dark lights, the numerals, the learned-word cap."""
    return load_pack(pack)["READING"]


def enabled(pack):
    """True when the pack switch READING.enabled is on."""
    return bool(table(pack)["enabled"])


def _tier_row(tier, pack):
    for row in load_pack(pack)["LITERACY_TIERS"]:
        if row["tier"] == tier:
            return row
    raise KeyError(f"no LITERACY_TIERS row for the literacy tier {tier!r}")


def known_words(game, actor, pack):
    """The lowercase words a resident recognises. Its trade's seed (RECOGNISED_SEED, by trade name), its own name, the
    common numerals, and the words it has learned from use (memories of the table's learned_kind)."""
    pk = load_pack(pack)
    world = game.world
    role = str(world.eng.node(world._actors[actor])["attrs"].get("role") or "")
    words = set()
    for trade in SF.JOBS.get(role, {}).get("trades", []):
        words.update(str(w).lower() for w in pk["RECOGNISED_SEED"].get(trade, []))
    words.update(str(w).lower() for w in table(pack)["common_numerals"])
    words.update(w.lower() for w in WORD.findall(actor))
    learned_kind = table(pack)["learned_kind"]
    for memory in game.characters[actor].memories:
        if memory.kind == learned_kind and isinstance(memory.content, dict):
            words.add(str(memory.content.get("word", "")).lower())
    return words


def _shown(text, known, squiggle):
    """The text with every word the resident does not know replaced by a squiggle. Spacing and punctuation stay."""
    return WORD.sub(lambda m: m.group(0) if m.group(0).lower() in known else squiggle, text)


def _fill(template, mark, num_row, pack):
    """The template with {price} replaced by the price in the numeracy words of the reader's tier."""
    if PRICE not in template:
        return template
    return template.replace(PRICE, numeracy.price_words(mark["price"], mark["unit"], num_row, pack))


def percept(mark, tier, known, num_row, pack, truth=False):
    """What the reader makes of one mark: {tier, words}. `tier` is the literacy tier name, `known` the reader's words,
    `num_row` its NUMERACY_TIERS row. The tier's reading mode (LITERACY_TIERS.reads) picks the WRITTEN_KINDS template:
    'words' shows the known words amid squiggles (a mark with none of them is 'unreadable'), 'short' the short text,
    'full' the whole text. `truth` reads the mark as a fully literate, fully numerate reader would."""
    pk = load_pack(pack)
    kind = pk["WRITTEN_KINDS"][mark["kind"]]
    templates = kind["tiers"]
    if truth:
        tier = pk["LITERACY_TIERS"][-1]["tier"]
        num_row = numeracy.tier_row(numeracy.REPRESENTED_LEVEL, pack)
        known = set()
    reads = _tier_row(tier, pack)["reads"]
    text = _fill(mark["text"], mark, num_row, pack)
    short = _fill(mark["short"], mark, num_row, pack)
    mode = reads
    shown = ""
    if reads == "words":
        if any(w.lower() in known for w in WORD.findall(text)):
            shown = _shown(text, known, table(pack)["squiggle"])
        else:
            mode = "unreadable"
    return {"tier": tier, "words": templates[mode].format(label=kind["label"], shown=shown, short=short, text=text)}


def _learn(game, actor, words, known, pack):
    """Hold each word not yet known, up to the cap (READING.learned_max). Words are held as memories."""
    if not words:
        return
    from bigville.character import MemoryRecord
    tbl = table(pack)
    character = game.characters[actor]
    learned = [m for m in character.memories if m.kind == tbl["learned_kind"] and isinstance(m.content, dict)]
    room = int(tbl["learned_max"]) - len(learned)
    for word in sorted(set(words)):
        if room <= 0:
            break
        if word in known:
            continue
        character.memories.append(MemoryRecord(
            memory_id=f"learned:{actor}:{word}", content={"type": "written_word", "word": word},
            kind=tbl["learned_kind"], source="sight", confidence=1.0, salience=0.5))
        known.add(word)
        room -= 1


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def writing_rows(game, actor, rec, pack, log):
    """The `writing` rows of the agent view: one {percept} per written mark in sight. None when reading is off (the view
    then has no writing section). Each mark's referee row (the percept beside the truth) is appended to `log`."""
    if not enabled(pack):
        return None
    if rec["light"] in table(pack)["dark_lights"]:
        return []
    world = game.world
    position = world.actor_position(actor)
    marks = load_pack(pack)["WRITTEN_MARKS"]
    tier = rec["literacy"]
    num_row = numeracy.tier_row(numeracy.level(game, actor, rec["modes"]["numeracy"]), pack)
    known = known_words(game, actor, pack)
    observed = world.physical_object_observations(actor)
    carried = {str(kind) for kind in world.inventory(actor)}
    visible = {str(item.get("kind")) for item in observed}
    rows, learn = [], []
    for item in observed:
        object_id = str(item.get("id", ""))
        mark = marks.get(object_id)
        if mark is None:
            continue
        cell = world._physical_location_cell(object_id)
        distance = _chebyshev(position, cell) if (cell is not None and position is not None) else 0
        if distance > int(rec["sight"]):
            continue
        seen = percept(mark, tier, known, num_row, pack)
        truth = percept(mark, tier, known, num_row, pack, truth=True)
        rows.append({"percept": seen["words"]})
        log.append({"subject": object_id, "kind": "writing", "distance": int(distance), "tier": seen["tier"],
                    "percept": seen["words"], "truth_tier": truth["tier"], "truth": truth["words"]})
        if mark["refers_to"] in carried or mark["refers_to"] in visible:
            learn.append(mark["refers_to"])
    _learn(game, actor, learn, known, pack)
    return rows
