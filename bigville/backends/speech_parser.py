"""Speech parser: stage two of speech in (Phase 061). A small model places what the grammar cannot.

`SpeechParser.parse(text, speaker, listener, context)` places one heard utterance, in this order:

1. The grammar and the speaker's well-formed raw payload (`speech_in.understand`, Phase 060). A placed
   utterance is returned with its source, "raw" or "grammar".
2. Only when the speaker gave no structure (no raw payload), the listener is a simple backend, and the text is
   within `caps.max_utterance_chars`: the cache. The key is the frame of the normalised text (names and counts
   replaced by slots), the schema version and the fixed-reference hash. A hit costs nothing.
3. On a cache miss, one model call through the provider layer (`complete(payload, meta)`, Phase 055, Phase 066
   for the reply). The system text is the fixed prefix, built from the pack's SPEECH_ACTS and SPEECH_PARSER, so
   it is the same bytes on every call. The user part is the utterance and a minimal context. An invalid reply
   gets one repair call (`caps.repair_attempts`). The model's answer is checked against the act table and the
   slot kinds, and a name slot must be a name the listener could know. A valid answer, or a null act, is stored
   in the cache. A failure is not stored.

Every failure leaves the utterance unplaced (None) and is counted by cause in `stats`. Calls are capped per run
and by spend through `CallBudget` (bigville/backends/autopilot.py), and a call that runs past `caps.timeout_s`
is abandoned and counted as a timeout.

The cache is a JSON Lines file. Each line is {"key", "schema", "ref", "answer"}; a line whose schema or
reference hash differs from this parser's is skipped and counted as stale. The file belongs to the run's record
(see the Phase 061 report): replaying a run needs the same provider replies, and the cache is one of its inputs.

Nothing here is on by default. The simple backend calls `parse` only when `speech_in.using_parser` is set.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

from domains import speech_grammar as G
from domains.pack import load_pack

from . import speech_in
from .autopilot import CallBudget
from ..llm_transcript import ReplayMismatch, call_provider
from ..providers.openai_compatible import ProviderError

SOURCE_RAW = "raw"
SOURCE_GRAMMAR = "grammar"
SOURCE_CACHE = "cache"
SOURCE_MODEL = "model"
# Every cause a parse can end unplaced for, in the order the report lists them.
CAUSES = ("provider_error", "timeout", "replay_mismatch", "invalid_output", "invalid_cache", "call_cap",
          "spend_cap", "too_long", "not_eligible", "model_none", "cache_declined")
NUMBER_WORDS = frozenset(("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                          "fourteen fifteen sixteen seventeen eighteen nineteen twenty").split())
_BUDGET_RESIDENT = "speech-parser"       # one budget key: its per-day cap is the per-run cap
_BUDGET_DAY = 0
_VOCATIVE_START = re.compile(r"^\s*([A-Za-z][\w'\-]*)\s*[,!]")
_VOCATIVE_END = re.compile(r",\s*([A-Za-z][\w'\-]*)\s*[!.?]*\s*$")
_SLOT_TOKEN = re.compile(r"\{(\w+)\}")
_MISSING = object()


# ---------------------------------------------------------------- the fixed reference

def fixed_prefix(pack: str = "bigville") -> str:
    """The system text of every model call: the pack's intro, one line per understood act (from SPEECH_ACTS),
    the output schema, and the examples. Built from the pack only, so it is the same bytes in every run of a pack."""
    pack_table = load_pack(pack)
    spec = pack_table["SPEECH_PARSER"]
    prefix = spec["prefix"]
    lines = [prefix["intro"], "", "Speech acts (name, what it is, slots):"]
    for row in pack_table["SPEECH_ACTS"]:
        if row["understood_by"] != "simple":
            continue
        slots = ", ".join(f"{name} ({kind})" for name, kind in row["slots"].items()) or "none"
        lines.append(f"- {row['act']}: {row['description']} Slots: {slots}.")
    lines += ["", "Reply format:", prefix["schema"], "", "Examples:"]
    for example in prefix["examples"]:
        lines.append(f'Speaker "{example["speaker"]}", listener "{example["listener"]}". '
                     f'Utterance: "{example["utterance"]}"')
        lines.append(f"Reply: {json.dumps(example['reply'], sort_keys=True, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def reference_hash(prefix: str) -> str:
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()


@lru_cache(maxsize=None)
def _rows(pack: str):
    return {row["act"]: row for row in load_pack(pack)["SPEECH_ACTS"] if row["understood_by"] == "simple"}


# ---------------------------------------------------------------- the frame: names and counts as slots

def _is_count(token: str) -> bool:
    return token in NUMBER_WORDS or token.isdigit()


@lru_cache(maxsize=None)
def vocabulary(pack: str = "bigville") -> frozenset:
    """Every word the act table speaks: its patterns, its surface templates and its lexicon phrases, and the
    question openers. A capitalised word made of these is not a name ("Hello, ..." is not a vocative)."""
    from bigville.backends.conversation import DEFAULT_TEMPLATES
    pack_table = load_pack(pack)
    words = set(G.QUESTION_OPENERS)
    lexicon = {name: pack_table[name] for name in pack_table.names() if name.startswith("SPEECH_")}
    for row in pack_table["SPEECH_ACTS"]:
        for pattern in row.get("patterns", []):
            words.update(G.normalise(_SLOT_TOKEN.sub(" ", pattern)).split())
        template = DEFAULT_TEMPLATES.get(row.get("template") or "")
        if template:
            words.update(G.normalise(re.sub(r"\{\w+\}", " ", template)).split())
        if row.get("lexicon"):
            for phrase in G.lexicon_patterns(lexicon, row["lexicon"], "text"):
                words.update(G.normalise(re.sub(r"\{\w+\}", " ", phrase)).split())
    return frozenset(words)


def _vocatives(raw: str, vocab) -> list:
    """A capitalised name spoken to at the start or end of the line ("Bram, ..." or "..., Bram!"), unless the
    word is part of the act table's wording."""
    found = []
    for pattern in (_VOCATIVE_START, _VOCATIVE_END):
        match = pattern.search(raw)
        if match and match.group(1)[:1].isupper() and G.normalise(match.group(1)) not in vocab:
            found.append(match.group(1))
    return found


def frame(text, names, vocab=frozenset()):
    """(frame text, values) for one utterance. Each name in `names` (and each vocative not in `vocab`) becomes
    {name1}, {name2}, ... in the order it first appears; each count word or digit becomes {n1}, {n2}, ... . `values`
    maps each slot to the normalised words it stood for. Two utterances that differ only in those words have one
    frame."""
    raw = str(text)
    tokens = G.normalise(raw).split()
    phrases = set()
    for name in list(names) + _vocatives(raw, vocab):
        parts = tuple(G.normalise(name).split())
        if parts:
            phrases.add(parts)
    ordered = sorted(phrases, key=len, reverse=True)
    placeholder_of, values, counters = {}, {}, {"name": 0, "n": 0}
    out, index = [], 0
    while index < len(tokens):
        kind, step = None, None
        for phrase in ordered:
            if tuple(tokens[index:index + len(phrase)]) == phrase:
                kind, step = "name", phrase
                break
        if step is None and _is_count(tokens[index]):
            kind, step = "n", (tokens[index],)
        if step is None:
            out.append(tokens[index])
            index += 1
            continue
        value = " ".join(step)
        if value not in placeholder_of:
            counters[kind] += 1
            slot = f"{kind}{counters[kind]}"
            placeholder_of[value] = slot
            values[slot] = value
        out.append("{" + placeholder_of[value] + "}")
        index += len(step)
    return " ".join(out), values


def _templatise(value: str, slots_by_value: dict, speaker: str, listener: str) -> str:
    """A normalised slot value with the words that were slots in this utterance put back as placeholders. The
    speaker and the listener are placeholders too, so a cached answer means the same for anyone."""
    phrases = dict(slots_by_value)
    if speaker:
        phrases.setdefault(tuple(speaker.split()), "speaker")
    if listener:
        phrases.setdefault(tuple(listener.split()), "listener")
    ordered = sorted(phrases, key=len, reverse=True)
    tokens, out, index = value.split(), [], 0
    while index < len(tokens):
        for phrase in ordered:
            if tuple(tokens[index:index + len(phrase)]) == phrase:
                out.append("{" + phrases[phrase] + "}")
                index += len(phrase)
                break
        else:
            out.append(tokens[index])
            index += 1
    return " ".join(out)


def _instantiate(template: str, values: dict, speaker: str, listener: str) -> str:
    """Inverse of `_templatise` for the utterance now heard. Raises KeyError when a slot has no value here."""
    def fill(match):
        key = match.group(1)
        if key == "speaker":
            return speaker
        if key == "listener":
            return listener
        return values[key]
    return _SLOT_TOKEN.sub(fill, template)


# ---------------------------------------------------------------- the reply check

def _decode(reply):
    """(object, reason). The reply is a dict, or text holding one JSON object (a fenced block is accepted)."""
    if isinstance(reply, dict):
        return reply, None
    text = str(reply).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        obj = json.loads(text)
    except ValueError:
        return None, "bad_json"
    if not isinstance(obj, dict):
        return None, "not_an_object"
    return obj, None


def check_reply(reply, *, text, allowed_names, pack: str = "bigville"):
    """(answer, reason). `answer` is {"act": name or None, "slots": {slot: normalised words}} when the reply is
    well formed, else None with the reason. The checks are the speaker's raw payload's checks (Phase 060: an
    understood act, slots that the act names), plus the slot kinds:
      name      a name the listener could know: in `allowed_names` (the speaker, the listener, or a name in view)
      word      one word from the line
      question  starts with a question word, and its words are in the line
      text      words from the line
    `act` null is a valid reply: the model found no act in the line."""
    obj, reason = _decode(reply)
    if obj is None:
        return None, reason
    act = obj.get("act")
    if act is None:
        return {"act": None, "slots": {}}, None
    rows = _rows(pack)
    if not isinstance(act, str) or act not in rows:
        return None, "unknown_act"
    given = obj.get("slots", {})
    if given is None:
        given = {}
    if not isinstance(given, dict):
        return None, "slots_not_an_object"
    declared = rows[act]["slots"]
    line = " " + G.normalise(text) + " "
    allowed = {G.normalise(name) for name in allowed_names if G.normalise(name)}
    slots = {}
    for key, value in given.items():
        if key not in declared:
            return None, "unknown_slot"
        if not isinstance(value, str):
            return None, "slot_not_text"
        words = G.normalise(value)
        if not words:
            return None, "empty_slot"
        kind = declared[key]
        if kind == "name":
            if words not in allowed:
                return None, "invented_name"
        elif f" {words} " not in line:
            return None, "slot_not_in_line"
        elif kind == "word" and len(words.split()) != 1:
            return None, "slot_not_one_word"
        elif kind == "question" and words.split()[0] not in G.QUESTION_OPENERS:
            return None, "not_a_question"
        slots[key] = words
    return {"act": act, "slots": slots}, None


# ---------------------------------------------------------------- the parser

def _is_simple(listener) -> bool:
    """A simple backend: the deterministic one (kind "cheap"), which does not take raw speech."""
    return getattr(listener, "kind", None) == "cheap" and not getattr(listener, "understands_raw_speech", False)


class SpeechParser:
    """Places heard speech for simple listeners. See the module docstring.

    `provider` is any object with complete(payload, meta) (Phase 055/066). `cache_path` (optional) is the JSONL
    cache, loaded at construction and appended to. `max_calls` and `max_spend` (None for no cap) feed a CallBudget.
    Thread-safe: the cache and the counts are locked, and the budget locks its own counts."""

    def __init__(self, provider, *, pack: str = "bigville", cache_path=None, max_calls=None, max_spend=None,
                 timeout_s=None, repair_attempts=None, budget: CallBudget | None = None):
        spec = load_pack(pack)["SPEECH_PARSER"]
        caps = spec["caps"]
        self.provider = provider
        self.pack = pack
        self.prefix = fixed_prefix(pack)
        self.reference_hash = reference_hash(self.prefix)
        self.schema_version = int(spec["schema_version"])
        self.timeout_s = float(caps["timeout_s"] if timeout_s is None else timeout_s)
        self.repair_attempts = int(caps["repair_attempts"] if repair_attempts is None else repair_attempts)
        self.max_chars = int(caps["max_utterance_chars"])
        self.confidence = float(spec["confidence"]["model"])
        self._vocab = vocabulary(pack)
        if budget is None:
            budget = CallBudget(
                max_calls_per_day=caps["max_calls_per_run"] if max_calls is None else max_calls,
                max_spend=caps["max_spend"] if max_spend is None else max_spend)
        self.budget = budget
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.stats = Counter()
        self.latencies_ms: list[float] = []
        self.cost = 0.0
        self.calls = 0
        self._cache: dict = {}
        self._lock = threading.Lock()
        if self.cache_path is not None and self.cache_path.exists():
            self._load()

    # -- the cache ------------------------------------------------------------------
    def _load(self) -> None:
        with open(self.cache_path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("schema") != self.schema_version or record.get("ref") != self.reference_hash:
                    self.stats["cache_stale"] += 1
                    continue
                self._cache[record["key"]] = record["answer"]

    def _store(self, key: str, answer) -> None:
        with self._lock:
            self._cache[key] = answer
            if self.cache_path is not None:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                line = {"key": key, "schema": self.schema_version, "ref": self.reference_hash, "answer": answer}
                with open(self.cache_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n")

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    # -- counting ---------------------------------------------------------------------
    def _count(self, key: str, n: int = 1) -> None:
        with self._lock:
            self.stats[key] += n

    def _unplaced(self, cause: str):
        self._count("unplaced")
        self._count(cause)
        return None

    def _placed(self, answer: dict, source: str, stranger: bool):
        confidence = self.confidence
        if source in (SOURCE_MODEL, SOURCE_CACHE) and stranger:
            confidence *= float(speech_in._settings()["effects"]["stranger_factor"])
        self._count(f"placed_{source}")
        return {"act": answer["act"], "slots": dict(answer["slots"]), "confidence": round(confidence, 4),
                "source": source}

    # -- the public call ----------------------------------------------------------------
    def parse(self, text, speaker, listener, context=None):
        """A placed utterance ({act, slots, confidence, source}) or None. See the module docstring."""
        context = dict(context or {})
        text = str(text or "")
        self._count("utterances")
        stranger = bool(context.get("stranger", False))
        placed = speech_in.understand({"text": text, "speaker": speaker, "raw_data": context.get("raw_data")},
                                      {"stranger": stranger})
        if placed is not None:
            self._count(f"placed_{placed['source']}")
            return placed
        if context.get("raw_data") is not None or not _is_simple(listener):
            return self._unplaced("not_eligible")
        if len(text) > self.max_chars:
            return self._unplaced("too_long")
        return self._model_stage(text, str(speaker or ""), context, stranger)

    def _model_stage(self, text, speaker, context, stranger):
        listener_name = str(context.get("listener_name", "listener"))
        names = [speaker, listener_name] + [str(name) for name in context.get("names", []) or []]
        names = [name for name in names if G.normalise(name)]
        frame_text, values = frame(text, names, self._vocab)
        speaker_words = G.normalise(speaker)
        listener_words = G.normalise(listener_name)
        with self._lock:
            cached = self._cache.get(frame_text, _MISSING)
        if cached is not _MISSING:
            self._count("cache_lookup_hit")
            if cached is None:
                return self._unplaced("cache_declined")
            answer = self._from_template(cached, values, speaker_words, listener_words, names, text)
            if answer is None:
                return self._unplaced("invalid_cache")
            return self._placed(answer, SOURCE_CACHE, stranger)
        self._count("cache_miss")
        answer = self._ask(text, speaker, context, listener_name, names, frame_text, values, speaker_words,
                           listener_words)
        if answer is None:
            return None
        if answer["act"] is None:
            return self._unplaced("model_none")
        return self._placed(answer, SOURCE_MODEL, stranger)

    def _from_template(self, template, values, speaker_words, listener_words, names, text):
        if template is None:
            return None
        try:
            slots = {key: _instantiate(value, values, speaker_words, listener_words)
                     for key, value in template["slots"].items()}
        except KeyError:
            return None
        answer, reason = check_reply({"act": template["act"], "slots": slots}, text=text,
                                     allowed_names=names, pack=self.pack)
        if reason is not None:
            self._count(f"reject:{reason}")
            return None
        return answer

    def _ask(self, text, speaker, context, listener_name, names, frame_text, values, speaker_words,
             listener_words):
        """One model call and at most `repair_attempts` repairs. Stores the answer on success. Returns the answer
        (act may be None), or None when the call was unplaced (the cause is counted here)."""
        payload = {"system": self.prefix, "utterance": text, "speaker": speaker,
                   "listener_knows_speaker": not bool(context.get("stranger", False)),
                   "topic_words": [str(word) for word in context.get("topic_words", []) or []][:8]}
        turn = context.get("turn", 0)
        attempt = 0
        while True:
            cause = self.budget.reserve(_BUDGET_RESIDENT, _BUDGET_DAY)
            if cause is not None:
                self._unplaced(cause)
                return None
            with self._lock:
                self.calls += 1
            reply, failure = self._call(payload, {"turn": turn, "actor": listener_name, "attempt": attempt,
                                                  "session": listener_name})
            if failure is not None:
                self._unplaced(failure)
                return None
            answer, reason = check_reply(reply, text=text, allowed_names=names, pack=self.pack)
            if answer is not None:
                break
            self._count(f"reject:{reason}")
            if attempt >= self.repair_attempts:
                self._unplaced("invalid_output")
                return None
            attempt += 1
            self._count("repairs")
            payload = dict(payload, repair={"previous_reply": str(reply)[:300], "problem": reason})
        if answer["act"] is None:
            self._store(frame_text, None)
            return answer
        slots_by_value = {tuple(value.split()): slot for slot, value in values.items()}
        template = {"act": answer["act"],
                    "slots": {key: _templatise(value, slots_by_value, speaker_words, listener_words)
                              for key, value in answer["slots"].items()}}
        self._store(frame_text, template)
        return answer

    def _call(self, payload, meta):
        """(reply, failure). The call runs in a worker thread so the timeout can end it. The cost is read in the
        same thread, because a provider's last_cost is per thread."""
        outcome = {}

        def work():
            try:
                outcome["reply"] = call_provider(self.provider, payload, meta)
                outcome["cost"] = getattr(self.provider, "last_cost", None)
            except ReplayMismatch as exc:
                outcome["failure"] = "replay_mismatch"
                outcome["error"] = exc
            except ProviderError as exc:
                outcome["failure"] = "provider_error"
                outcome["error"] = exc
            except Exception as exc:  # any other failure is a provider failure for the caller
                outcome["failure"] = "provider_error"
                outcome["error"] = exc

        started = time.perf_counter()
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(self.timeout_s)
        elapsed = (time.perf_counter() - started) * 1000.0
        with self._lock:
            self.latencies_ms.append(round(elapsed, 3))
        if worker.is_alive():
            return None, "timeout"
        if "failure" in outcome:
            return None, outcome["failure"]
        cost = outcome.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            self.budget.record_cost(cost)
            with self._lock:
                self.cost += float(cost)
        return outcome["reply"], None

    # -- the report -------------------------------------------------------------------
    def summary(self) -> dict:
        """Counts for the report: utterances, the placed share by source, unplaced causes, calls, cost, latency."""
        with self._lock:
            stats = dict(self.stats)
            latencies = list(self.latencies_ms)
        total = stats.get("utterances", 0)
        placed = {source: stats.get(f"placed_{source}", 0) for source in (SOURCE_RAW, SOURCE_GRAMMAR,
                                                                         SOURCE_CACHE, SOURCE_MODEL)}
        return {
            "utterances": total,
            "placed": placed,
            "placed_total": sum(placed.values()),
            "unplaced": stats.get("unplaced", 0),
            "causes": {cause: stats.get(cause, 0) for cause in CAUSES if stats.get(cause, 0)},
            "rejections": {key[len("reject:"):]: value for key, value in sorted(stats.items())
                           if key.startswith("reject:")},
            "cache_hits": stats.get("cache_lookup_hit", 0),
            "cache_misses": stats.get("cache_miss", 0),
            "cache_entries": self.cache_size,
            "calls": self.calls,
            "repairs": stats.get("repairs", 0),
            "cost": round(self.cost, 6),
            "latency_ms_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        }
