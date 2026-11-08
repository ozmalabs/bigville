"""Speech in: what a simple resident makes of an utterance it hears (Phase 060).

`understand` places one heard utterance as a speech act. The order is the speaker's well-formed `raw`
payload, then the deterministic grammar (domains/speech_grammar.py) over the text, then None. It returns
{act, slots, confidence, source}. A speaker with no held tie is a stranger, and the confidence is scaled
down for a stranger.

The hooks below change what a simple resident does (bigville/backends/cheap.py calls them). They read the
heard records from the observation and never touch the world. Every effect goes through the resident's
ordinary actions, so the world still validates each one. With SPEECH_UNDERSTANDING.enabled off, each hook
returns at once and the resident is unchanged.

Effects, with the switch on:
  greeting   a reply greeting, at most once per `greet_gap_ticks` for each speaker.
  question   a reply saying the resident is managing.
  request    a give goal, if the resident holds the item and the speaker is tied to it (`tie_min`). A stranger
             or a request the resident cannot meet gets a refusal in words. Only `give` is implemented.
  offer      accepted when the item is food and the resident is hungry (`need_hunger`); declined otherwise.
  barb       caution: the resident does not start a travel goal for `caution_ticks`, if the confidence allows.
  share      the news is kept as a place_belief memory (Phase 053's fog reads those and raises a place it names).
"""
from __future__ import annotations

import re
from collections import Counter, deque
from contextlib import contextmanager
from functools import lru_cache

from domains import speech_grammar as G
from domains.pack import load_pack

from ..character import MemoryRecord

_OVERRIDE = None          # None: the pack's switch. True or False: a test or a measurement forces it.
_PARSER = None            # Phase 061: a SpeechParser for `understand` (None: no parser).
_GIVE = re.compile(r"^(?:give|bring|hand|pass)(?: me| us)?(?: the| a| an| some)? (?P<item>[a-z][a-z' \-]*)$")


@contextmanager
def switched(value: bool):
    """Force SPEECH_UNDERSTANDING.enabled to `value` inside the block (tests and measurement runs)."""
    global _OVERRIDE
    previous, _OVERRIDE = _OVERRIDE, bool(value)
    try:
        yield
    finally:
        _OVERRIDE = previous


@contextmanager
def using_parser(parser):
    """Phase 061: the speech parser that `hear` gives to `understand` inside the block. None (the default) means no
    parser, so an utterance the grammar cannot place stays unplaced."""
    global _PARSER
    previous, _PARSER = _PARSER, parser
    try:
        yield
    finally:
        _PARSER = previous


@lru_cache(maxsize=None)
def _pack():
    return load_pack("bigville")


def _settings():
    return _pack()["SPEECH_UNDERSTANDING"]


def enabled() -> bool:
    if _OVERRIDE is not None:
        return _OVERRIDE
    return bool(_settings()["enabled"])


@lru_cache(maxsize=None)
def _compiled():
    """(rows by act, grammar rules). Built once from the pack and the templates the simple speakers use."""
    from bigville.backends.conversation import DEFAULT_TEMPLATES
    pack = _pack()
    rows = list(pack["SPEECH_ACTS"])
    tables = {name: pack[name] for name in ("SPEECH_CHATTER", "SPEECH_WEATHER")}
    return {row["act"]: row for row in rows}, G.rules_for(rows, DEFAULT_TEMPLATES, tables)


def _from_raw(raw, rows):
    """(act, slots) when the speaker's raw payload is well formed for a simple listener, else None.

    Well formed: a dict whose `act` is a row understood by the simple backend, and whose optional `slots`
    names only that row's slots. A `target` the row takes is read from the payload's `target` when absent."""
    if not isinstance(raw, dict):
        return None
    act = raw.get("act")
    row = rows.get(act) if isinstance(act, str) else None
    if row is None or row.get("understood_by") != "simple":
        return None
    declared = row.get("slots", {})
    if "slots" in raw:
        given = raw["slots"]
        if not isinstance(given, dict) or any(key not in declared for key in given):
            return None
        slots = {key: str(value) for key, value in given.items()}
    else:
        slots = {}
    if "target" in declared and "target" not in slots and raw.get("target"):
        slots["target"] = str(raw["target"])
    return act, slots


def understand(utterance, listener_context=None, parser=None):
    """Place one heard utterance (a heard_utterances record, or {"text", "raw_data"}).

    Returns {act, slots, confidence, source} with source "raw" or "grammar", or None when neither places it.
    `listener_context["stranger"]` true scales the confidence by SPEECH_UNDERSTANDING's stranger_factor.
    Phase 061: when the raw payload and the grammar both fail and `parser` is given, `parser.parse` is asked
    (it is called with the speaker, the listener from `listener_context["listener"]`, and the context). With
    `parser` None (the default) the result is unchanged."""
    context = dict(listener_context or {})
    effects = _settings()["effects"]
    rows, rules = _compiled()
    placed = _from_raw(utterance.get("raw_data"), rows)
    if placed is not None:
        act, slots = placed
        source, confidence = "raw", float(effects["raw_confidence"])
    else:
        found = G.place(str(utterance.get("text", "") or ""), rules)
        if found is None:
            if parser is None:
                return None
            return parser.parse(str(utterance.get("text", "") or ""), utterance.get("speaker"),
                                context.get("listener"), context)
        act, slots = found["act"], found["slots"]
        source, confidence = "grammar", float(effects["grammar_confidence"])
    if context.get("stranger"):
        confidence *= float(effects["stranger_factor"])
    return {"act": act, "slots": slots, "confidence": round(confidence, 4), "source": source}


# ----------------------------------------------------------------- the resident's held state

class _State:
    """What a simple resident holds from speech: the records already read, queued replies, the give goal, the
    caution, and the greetings sent. Held on the backend (not checkpointed; see the phase report)."""

    SEEN_KEEP = 400

    def __init__(self):
        self.seen = deque()
        self.seen_set = set()
        self.replies = []
        self.goal = None
        self.caution_until = -1
        self.greeted = {}
        self.stats = Counter()

    def remember(self, key) -> bool:
        """True the first time `key` is seen, False after."""
        if key in self.seen_set:
            return False
        self.seen.append(key)
        self.seen_set.add(key)
        while len(self.seen) > self.SEEN_KEEP:
            self.seen_set.discard(self.seen.popleft())
        return True


def _state(backend) -> _State:
    state = getattr(backend, "_speech_in", None)
    if state is None:
        state = _State()
        backend._speech_in = state
    return state


def stats(backend) -> dict:
    """The counts this resident has kept: heard, placed by source, per act, and each effect."""
    return dict(_state(backend).stats) if getattr(backend, "_speech_in", None) is not None else {}


def _mentions_place(text: str) -> bool:
    pack = _pack()
    phrases = [G.normalise(phrase) for phrase in pack["FOG_PLACE_WORDS"].values()]
    phrases += [G.normalise(name) for name in pack["FOG_PUBLIC_LANDMARKS"]]
    padded = f" {G.normalise(text)} "
    return any(phrase and f" {phrase} " in padded for phrase in phrases)


def _item_key(words: str):
    """The ITEMS key for a words phrase ("coloured cloth" -> "coloured_cloth"), or None."""
    key = "_".join(G.normalise(words).split())
    return key if key in _pack()["ITEMS"] else None


def _queue(state, turn, target, act, slots):
    state.replies.append({"turn": turn, "target": target, "act": act, "slots": slots})


def _apply(backend, state, effects, turn, speaker, placed, tie, inventory, hunger):
    act, slots, confidence = placed["act"], placed["slots"], placed["confidence"]
    words = _settings()["words"]
    stranger = tie <= 0.0
    if act == "greeting":
        last = state.greeted.get(speaker)
        if last is None or turn - last >= int(effects["greet_gap_ticks"]):
            state.greeted[speaker] = turn
            _queue(state, turn, speaker, "greeting", {"target": speaker})
            state.stats["effect_greeting_reply"] += 1
    elif act == "question":
        _queue(state, turn, speaker, "answer", {"answer": words["managing"]})
        state.stats["effect_question_reply"] += 1
    elif act == "request":
        match = _GIVE.match(G.normalise(slots.get("request", "")))
        item = _item_key(match.group("item")) if match else None
        if item is None or stranger or tie < float(effects["tie_min"]):
            key = "stranger" if stranger else "cannot"
            _queue(state, turn, speaker, "answer", {"answer": words[key]})
            state.stats[f"effect_request_declined_{'stranger' if stranger else 'cannot'}"] += 1
        elif inventory.get(item, 0.0) > 0.0:
            state.goal = {"item": item, "to": speaker, "until": turn + int(effects["goal_ticks"]), "live": True}
            state.stats["effect_request_goal"] += 1
        else:
            _queue(state, turn, speaker, "answer", {"answer": words["cannot"]})
            state.stats["effect_request_declined_cannot"] += 1
    elif act == "offer":
        item = _item_key(slots.get("item", ""))
        food = item is not None and bool(_pack()["ITEMS"][item].get("food"))
        if food and hunger >= float(effects["need_hunger"]):
            _queue(state, turn, speaker, "accept", {"thing": slots.get("item", "")})
            state.stats["effect_offer_accepted"] += 1
        else:
            _queue(state, turn, speaker, "decline", {"thing": slots.get("item", "")})
            state.stats["effect_offer_declined"] += 1
    elif act == "barb":
        if confidence >= float(effects["caution_min_confidence"]):
            state.caution_until = turn + int(effects["caution_ticks"])
            state.stats["effect_caution"] += 1
    elif act == "share":
        # Every news item is a place_belief. Phase 053's fog reader (map_memory._tell) raises a place only when
        # the text names one, so news about a person is read and changes nothing.
        place = _mentions_place(placed["text"])
        backend.character.memories.append(MemoryRecord(
            memory_id=f"speech:{speaker}:{turn}:{len(backend.character.memories)}",
            content={"text": placed["text"], "speaker": speaker, "turn": turn},
            kind="place_belief", source=speaker, confidence=confidence,
            salience=float(effects["memory_salience"]), turn=turn, private=True))
        state.stats["effect_news_stored"] += 1
        state.stats[f"effect_news_stored_{'place' if place else 'person'}"] += 1


def hear(backend, context) -> None:
    """Read the heard utterances of this turn that have not been read before, and apply their effects."""
    if not enabled():
        return
    observations = context.observations
    turn = int(context.turn)
    effects = _settings()["effects"]
    state = _state(backend)
    nearby = {str(resident.get("id")): resident for resident in observations.get("nearby_residents", []) or []}
    inventory = observations.get("inventory", {}) or {}
    hunger = float(observations.get("hunger", 0.0))
    for record in observations.get("heard_utterances", []) or []:
        key = (float(record.get("turn", 0.0)), str(record.get("speaker", "")), str(record.get("text", "")))
        if not state.remember(key):
            continue
        state.stats["heard"] += 1
        speaker = str(record.get("speaker", ""))
        tie = float(nearby.get(speaker, {}).get("tie_strength", 0.0))
        placed = understand(record, {"stranger": tie <= 0.0, "listener": backend, "turn": turn,
                                     "names": [str(r.get("name", rid)) for rid, r in nearby.items()],
                                     "listener_name": str(getattr(backend.character, "name", "listener")),
                                     "topic_words": list(dict.fromkeys(str(o.get("kind")) for o in context.affordances
                                                                      if o.get("kind")))[:8]},
                            parser=_PARSER)
        if placed is None:
            state.stats["unplaced"] += 1
            continue
        state.stats[f"placed_{placed['source']}"] += 1
        state.stats[f"act_{placed['act']}"] += 1
        placed["text"] = str(record.get("text", ""))
        _apply(backend, state, effects, turn, speaker, placed, tie, inventory, hunger)


def next_reply(backend, context):
    """The queued reply that is due, as a backend utterance, or None. One reply per turn; a reply older than
    `reply_ticks` is dropped."""
    if not enabled():
        return None
    state = _state(backend)
    turn = int(context.turn)
    ttl = int(_settings()["effects"]["reply_ticks"])
    while state.replies:
        reply = state.replies.pop(0)
        if turn - reply["turn"] > ttl:
            state.stats["reply_expired"] += 1
            continue
        backend.last_speech_turn = int(context.turn)
        state.stats["reply_sent"] += 1
        return {"target": reply["target"], "act": reply["act"], "slots": dict(reply["slots"]), "content": ""}
    return None


def add_goals(backend, context, candidates) -> None:
    """Update the give goal and the caution, then offer the goal to the goal choice. `candidates` is the list
    `_update_goals` builds: (kind, priority, reason) tuples. Called once per turn before the goal is picked."""
    if not enabled():
        return
    state = _state(backend)
    turn = int(context.turn)
    effects = _settings()["effects"]
    inventory = context.observations.get("inventory", {}) or {}
    goal = state.goal
    if goal is not None:
        last = backend.last_choice or {}
        done = (last.get("action") == "transfer" and last.get("recipient") == goal["to"]
                and last.get("kind") == goal["item"])
        if done:
            state.goal = None
            state.stats["goal_done"] += 1
        elif turn > goal["until"] or inventory.get(goal["item"], 0.0) <= 0.0:
            state.goal = None
            state.stats["goal_dropped"] += 1
        else:
            goal["live"] = True
            state.stats["goal_ticks"] += 1
            candidates.insert(0, ("speech_give", float(effects["goal_priority"]),
                                  f"{goal['to']} asked for {goal['item']}"))
    if turn < state.caution_until:
        candidates[:] = [c for c in candidates if c[0] != "travel"]
        state.stats["caution_ticks"] += 1


def goal_bonus(backend, option) -> float:
    """The bonus the give goal gives an option: a transfer of the item to the asker, or a step toward the asker."""
    state = _state(backend)
    goal = state.goal
    if goal is None or not goal.get("live") or option.get("recipient") != goal["to"]:
        return 0.0
    if option.get("action") == "move" or (option.get("action") == "transfer"
                                           and option.get("kind") == goal["item"]):
        return float(_settings()["effects"]["goal_bonus"])
    return 0.0


def allows_transfer(backend, option) -> bool:
    """True when a give goal is live and this transfer is the item to the asker. Lets the goal use a transfer
    option that the simple policy otherwise filters out (allow_transfers)."""
    if not enabled():
        return False
    state = _state(backend)
    goal = state.goal
    return bool(goal and goal.get("live") and option.get("action") == "transfer"
                and option.get("recipient") == goal["to"] and option.get("kind") == goal["item"])
