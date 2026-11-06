"""How well residents learn the world (Phase 056): metrics from the engine's own records, a leak guard, control
providers, and the report generator.

Everything here is read-only over the world. The evaluator reads the per-turn records the game already keeps
(``game.last_responses``, ``game.last_results``, the world's refusal counts, attempt counts and last attempt, the
harm and tool-wear calls it wraps on the instance, and the Phase 066 log of every prompt). Nothing here decides
for a resident.

Metric definitions (per resident unless stated):

* proposal: a major action a resident made in a turn. Its key is ``[verb, target, tool]``: the verb is the action
  name (for ``attempt``, the ``verb`` parameter), the target is the first of ``target``, ``recipe``, ``kind``,
  ``animal``, ``sow_kind`` or ``destination`` that the proposal carries, and the tool is ``tool`` or ``with``.
* failure: a proposal that did not apply (a refusal, with its REFUSAL_REASONS code), or an attempt whose outcome
  changed nothing (``no_progress`` or ``stuck``). A refusal for the resident's body (asleep, collapsed, passed out)
  is not a learning failure: it is counted as a body-state refusal and left out of the failure metrics.
* repeat failure: a failure whose key failed before for the same resident. ``repeat_mistake_rate`` is repeat
  failures over all failures (None with no failures).
* attempts to adaptation: an episode opens at a failure and closes when the resident proposes a different key or
  a proposal that does not fail. ``tries_before_switch`` is the number of failures under the old key. An episode
  still open at the end is censored, and is reported with the tries it had.
* improvised attempt: an attempt made with bare hands (the world records the tool as ``""``). Wrong-tool attempt:
  the proposal named a tool and the world used a different one. Work done with a named tool cannot be checked
  per resident, because the world keeps only a town tally for improvised jobs (open question).
* accident and breakage: a harm with cause ``accident`` on the resident, and a tool that breaks while the resident
  holds it. A tool broken with no holder is counted as unattributed.
* lesson recorded: a ``lesson`` memory update in the resident's reply. Lesson offered: its text is sent to the
  model in a later message of that resident's thread. Lesson used: offered, and the resident's next proposal
  after the offer has a key different from the key the lesson was written about.
* survival (alive at the end), food (food held at the end and its mean over turns), work (applied ``work``
  proposals), social ties (bonds with a positive strength at the end).

Leak guard: every message of every prompt in a run (the Phase 066 log) is checked with the Phase 052 rules: no
referee-only key, no raw number outside the packet's own ``sizes`` and ``omitted`` counts, and no digit in a
phrase, except in handles and in the resident's own lesson, note and persona text. A run with a violation is VOID.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any, Iterable

from domains.autopilot import DEFAULT_PACK, table as autopilot_table
from domains.pack import load_pack
from .api import create_game
from .backends.autopilot import CallBudget
from .backends.llm import LLMBackend
from .backends.prompt_packet import PACKET_SCHEMA
from .backends.prompts import pack_hash
from .llm_log import LLMLog, read_log
from .llm_scenario import choose_llm_residents

SCHEMA = "bigville/learning-eval/1"
DEFAULT_SCENARIO = "town100"
DEFAULT_SEED = 305000
DEFAULT_TURNS = 60
DEFAULT_LLM_RESIDENTS = 3
CONTROL_TURNS = 30
TARGET_KEYS = ("target", "recipe", "kind", "animal", "sow_kind", "destination")
FAILED_ATTEMPT_OUTCOMES = ("no_progress", "stuck")
# Refusals that come from the resident's body (asleep, collapsed, passed out). Nothing a resident learns changes them,
# so they are counted as refusals but are not learning failures (not in failures, repeats or episodes).
BODY_STATE_REASONS = ("asleep", "collapsed", "passed_out")
BARE_HANDS = ""
# Keys whose string values may carry digits: handles name rows (``target:0``), and the resident's own words are
# not the world's phrasing. Structural number counts are exempt by name (the packet's own ``sizes`` and ``omitted``).
DIGIT_EXEMPT_KEYS = ("handle", "lessons", "notes", "kept", "lead", "pack_hash", "system")
NUMBER_EXEMPT_KEYS = ("sizes", "omitted")
TOP_LEVEL_SKIP = ("system", "pack", "pack_hash", "schema")
PROMPT_ROLES = ("system", "user")
LESSON_TARGET = "The action did not happen with one target. I try another target before I give up on the action."
LESSON_SWITCH = "That did not happen, so I choose one of the options the world lists instead."
OPENING_RAW = ("lift", "1")
RETRY_RAW = "2"
NON_LEARNER_RAW = ("lift", "1")


# ---------------------------------------------------------------- keys and packets
def proposal_key(action_name: str, params: dict | None) -> list[str]:
    """``[verb, target, tool]`` for a proposal (see the module doc)."""
    params = params or {}
    verb = str(params.get("verb") or action_name) if action_name == "attempt" else str(action_name)
    target = next((str(params[k]) for k in TARGET_KEYS if params.get(k) not in (None, "")), "")
    tool = str(params.get("tool") or params.get("with") or "")
    return [verb, target, tool]


def _key_text(key) -> str:
    return "" if key is None else json.dumps(key)


def last_user_text(payload: dict) -> str:
    """The content of the last user message of a provider payload, or ''."""
    for message in reversed(payload.get("messages", []) or []):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def parse_packet(text: str) -> dict | None:
    """The JSON object in a user message (the packet follows any prose), or None."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def public_of(packet: dict | None) -> dict:
    """The public section a message shows: the whole packet's public part, or the changes to it."""
    if not packet:
        return {}
    if "context" in packet and isinstance(packet["context"], dict):
        return dict(packet["context"].get("public") or {})
    if "changes" in packet and isinstance(packet["changes"], dict):
        return dict((packet["changes"].get("public") or {}))
    return {}


# ---------------------------------------------------------------- control providers
class _Scripted:
    """Shared state for the scripted control providers: deterministic, thread-safe, and no network."""

    wants_meta = True

    def __init__(self, pack: str = DEFAULT_PACK):
        self.pack = pack
        self.not_done = load_pack(pack)["VIEW_WORDS"]["not_done"]
        self.calls: dict[str, int] = {}
        self._lock = threading.Lock()

    def _count(self, actor: str) -> None:
        self.calls[actor] = self.calls.get(actor, 0) + 1

    @staticmethod
    def _reply(action: dict | None, lesson: str | None = None) -> str:
        body: dict[str, Any] = {"major_action": action, "utterances": []}
        if lesson:
            body["memory_updates"] = [{"kind": "lesson", "text": lesson}]
        return json.dumps(body, sort_keys=True)


class ScriptedLearner(_Scripted):
    """A control learner. It reads its last outcome in ``public.last`` (merged with the changes the packet
    carries, since a delta packet shows only what changed), and changes what it does after a refusal:

    1. a raw action that was refused is tried once more with a different target;
    2. then the resident switches to the first option the world lists (``public.can``) whose handle has not failed.

    Each change comes with a lesson in ``memory_updates``. No randomness and no clock."""

    def __init__(self, pack: str = DEFAULT_PACK, opening=OPENING_RAW):
        super().__init__(pack)
        self.opening = (str(opening[0]), str(opening[1]))
        self._state: dict[str, dict[str, Any]] = {}

    def complete(self, payload, meta=None):
        meta = dict(meta or {})
        actor = str(meta.get("actor", ""))
        with self._lock:
            self._count(actor)
            public = public_of(parse_packet(last_user_text(payload)))
            st = self._state.setdefault(actor, {"last": None, "raw_tries": 0, "failed": [], "seen": None,
                                                "can": []})
            # A delta packet lists only what changed, so the learner keeps the last value it was shown.
            if "last" in public:
                st["seen"] = public["last"]
            if "can" in public:
                st["can"] = list(public["can"] or [])
            failed = st["last"] is not None and bool((st["seen"] or {}).get("outcome") == self.not_done)
            lesson = None
            if st["last"] is None:
                key = ("raw", self.opening[1])
                action = {"action": self.opening[0], "params": {"target": self.opening[1]}}
                st["raw_tries"] = 1
            elif failed:
                st["failed"].append(st["last"])
                if st["last"][0] == "raw" and st["raw_tries"] < 2:
                    key = ("raw", RETRY_RAW)
                    action = {"action": self.opening[0], "params": {"target": RETRY_RAW}}
                    st["raw_tries"] += 1
                    lesson = LESSON_TARGET
                else:
                    option = self._option(st["can"], st["failed"])
                    if option is None:
                        key, action = ("wait", ""), {"action": "wait", "params": {}}
                    else:
                        key = ("handle", option["handle"])
                        action = {"action": str(option["action"]), "target": option["handle"]}
                        lesson = LESSON_SWITCH
            else:
                # Nothing failed: repeat the last proposal.
                key = st["last"]
                if key[0] == "handle":
                    row = self._row(st["can"], key[1])
                    action = {"action": str(row["action"]) if row else "wait", "target": key[1]}
                elif key[0] == "raw":
                    action = {"action": self.opening[0], "params": {"target": key[1]}}
                else:
                    action = {"action": "wait", "params": {}}
            st["last"] = key
            return self._reply(action, lesson)

    @staticmethod
    def _row(rows: list, handle: str) -> dict | None:
        for row in rows:
            if row.get("handle") == handle:
                return row
        return None

    @staticmethod
    def _option(rows: list, failed: list) -> dict | None:
        failed_handles = {key[1] for key in failed if key and key[0] == "handle"}
        for row in rows:
            handle = str(row.get("handle", ""))
            if handle and handle not in failed_handles and row.get("action") not in (None, ""):
                return {"handle": handle, "action": row.get("action")}
        return None


class ScriptedNonLearner(_Scripted):
    """A control non-learner. It sends the same raw action every consult and ignores ``public.last``."""

    def complete(self, payload, meta=None):
        meta = dict(meta or {})
        with self._lock:
            self._count(str(meta.get("actor", "")))
        return self._reply({"action": NON_LEARNER_RAW[0], "params": {"target": NON_LEARNER_RAW[1]}})


# ---------------------------------------------------------------- the leak guard (Phase 052 rules, over prompts)
def _walk(value: Any, path: str, referee: set, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else str(key)
            if key in referee:
                out.append(f"referee-only key at {here}")
            if key in NUMBER_EXEMPT_KEYS:
                continue
            _walk(item, here, referee, out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", referee, out)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, (int, float)):
        out.append(f"raw number at {path}")
    elif isinstance(value, str):
        leaf = path.rsplit(".", 1)[-1]
        if any(part in DIGIT_EXEMPT_KEYS for part in path.split(".")) or leaf in DIGIT_EXEMPT_KEYS:
            return
        if re.search(r"\d", value):
            out.append(f"a digit in the phrase at {path}")


def guard_message(content: str, pack: str) -> list[str]:
    """The problems in one message of a prompt. Empty when the message is clean."""
    referee = set(load_pack(pack)["AGENT_VIEW_REFEREE_ONLY"])
    problems: list[str] = []
    packet = parse_packet(content)
    if packet is None:
        for name in referee:
            if f'"{name}"' in content or f"{name}:" in content:
                problems.append(f"referee-only name in prose: {name}")
        return problems
    for key, value in packet.items():
        if key in TOP_LEVEL_SKIP:
            continue
        _walk(value, str(key), referee, problems)
    prose = content[:content.find("{")] if "{" in content else content
    for name in referee:
        if re.search(rf"\b{re.escape(name)}\b", prose):
            problems.append(f"referee-only name in prose: {name}")
    return problems


def guard_log(path: str | Path, pack: str = DEFAULT_PACK) -> dict[str, Any]:
    """Check every message of every call in a Phase 066 log. ``void`` is True when any message fails."""
    checked = 0
    violations: list[dict[str, Any]] = []
    for record in read_log(path):
        if record.get("kind") != "call":
            continue
        for index, message in enumerate(record.get("messages", []) or []):
            # The world's prompts are the system and user messages. An assistant message is the model's own reply.
            if message.get("role") not in PROMPT_ROLES:
                continue
            checked += 1
            for problem in guard_message(str(message.get("content", "")), pack):
                violations.append({"turn": record.get("turn"), "resident": record.get("resident"),
                                   "message": index, "role": message.get("role"), "problem": problem})
    return {"prompts_checked": checked, "violation_count": len(violations), "violations": violations[:20],
            "void": bool(violations)}


# ---------------------------------------------------------------- the per-turn recorder
def _fresh() -> dict[str, Any]:
    return {"proposals": 0, "applied": 0, "failures": 0, "repeat_failures": 0, "work_applied": 0,
            "improvised_attempts": 0, "wrong_tool_attempts": 0, "accidents": 0, "breakages": 0,
            "tools": {}, "adaptations": [], "episode": None, "lessons": [], "last_failed_key": None,
            "body_state_refusals": 0,
            "keys_by_turn": {},
            "seen_fail": set(), "refusals_by_reason": {}, "food_series": [], "alive_series": [],
            "strain_series": [], "turn_rows": []}


class Recorder:
    """Reads a game turn by turn. Attach it before the first step; call ``after_turn`` after each step."""

    def __init__(self, game, subjects: Iterable[str], pack: str = DEFAULT_PACK):
        self.game = game
        self.world = game.world
        self.pack = pack
        self.subjects = [str(name) for name in subjects]
        self.state = {name: _fresh() for name in game.characters}
        self.population: list[dict[str, Any]] = []
        self.unattributed_breakages = 0
        self._breaks: list[Any] = []
        self._wrap()

    def _wrap(self) -> None:
        world = self.world
        original_harm = world.harm
        original_wear = world._wear_tool

        def harm(actor, amount, cause, *args, **kwargs):
            result = original_harm(actor, amount, cause, *args, **kwargs)
            if str(cause) == "accident" and actor in self.state:
                self.state[actor]["accidents"] += 1
            return result

        def wear(item, amount, *args, **kwargs):
            before = self._broken(item)
            result = original_wear(item, amount, *args, **kwargs)
            if not before and self._broken(item):
                self._breaks.append(item)
            return result

        world.harm = harm
        world._wear_tool = wear

    def _broken(self, item) -> bool:
        return float(self.world.eng.node(item)["attrs"].get("broken", 0.0)) == 1.0

    def _holder(self, item) -> str | None:
        for name in self.world._actors:
            node = self.world._actors[name]
            for edge in ("holds_in_hand", "holds_tableware", "holds"):
                if item in self.world.eng.neighbours(node, edge):
                    return name
        return None

    def _attr(self, name: str, key: str, default=0.0):
        return self.world.eng.node(self.world._actors[name])["attrs"].get(key, default)

    def after_turn(self, game) -> None:
        world = self.world
        turn = int(world._turn)
        responses = getattr(game, "last_responses", {}) or {}
        results = getattr(game, "last_results", {}) or {}
        # Lessons first: a lesson in this turn's reply is about the failure before this turn, not this turn's.
        self._lessons(responses, turn)
        for actor, response in sorted(responses.items()):
            action = response.major_action
            if action is None or actor not in self.state:
                continue
            self._proposal(actor, action, bool(results.get(actor)), turn)
        for item in self._breaks:
            holder = self._holder(item)
            if holder is None:
                self.unattributed_breakages += 1
            else:
                self.state[holder]["breakages"] += 1
        self._breaks = []
        self._snapshot(turn)

    def _proposal(self, actor: str, action, applied: bool, turn: int) -> None:
        st = self.state[actor]
        key = proposal_key(action.action, dict(action.params or {}))
        st["proposals"] += 1
        st["keys_by_turn"][turn] = key
        outcome = self.world.last_outcome(actor) or {}
        reason = outcome.get("reason") if outcome.get("turn") == turn else None
        attempt = self.world.last_attempt(actor) if hasattr(self.world, "last_attempt") else None
        attempt = attempt if attempt and int(attempt.get("turn", -1)) == turn else None
        failed = not applied
        if attempt is not None:
            st["tools"][attempt.get("tool", "")] = st["tools"].get(attempt.get("tool", ""), 0) + 1
            if attempt.get("tool", "") == BARE_HANDS:
                st["improvised_attempts"] += 1
            named = str((action.params or {}).get("tool") or (action.params or {}).get("with") or "")
            if named and attempt.get("tool", "") != named:
                st["wrong_tool_attempts"] += 1
            if attempt.get("outcome") in FAILED_ATTEMPT_OUTCOMES:
                failed = True
        if applied:
            st["applied"] += 1
            if action.action == "work":
                st["work_applied"] += 1
        if reason and not applied:
            st["refusals_by_reason"][reason] = st["refusals_by_reason"].get(reason, 0) + 1
            if reason in BODY_STATE_REASONS:
                st["body_state_refusals"] += 1
                return
        ep = st["episode"]
        if ep is not None and (ep["key"] != key or not failed):
            st["adaptations"].append({"key": ep["key"], "tries": ep["tries"], "closed": True})
            st["episode"] = None
        if failed:
            st["failures"] += 1
            if _key_text(key) in st["seen_fail"]:
                st["repeat_failures"] += 1
            st["seen_fail"].add(_key_text(key))
            st["last_failed_key"] = key
            if st["episode"] is None:
                st["episode"] = {"key": key, "tries": 0}
            st["episode"]["tries"] += 1

    def _lessons(self, responses, turn: int) -> None:
        for actor, response in sorted(responses.items()):
            if actor not in self.state:
                continue
            for item in response.memory_updates or []:
                if str(item.get("kind", "")) != "lesson":
                    continue
                text = (item.get("content") or {}).get("text", item.get("text", ""))
                self.state[actor]["lessons"].append({"turn": turn, "text": str(text),
                                                     "concerns": self.state[actor]["last_failed_key"]})

    def _snapshot(self, turn: int) -> None:
        alive_total = 0
        for name, st in self.state.items():
            alive = bool(self.world.is_alive(name))
            alive_total += int(alive)
            st["alive_series"].append(int(alive))
            st["strain_series"].append(round(float(self._attr(name, "strain", 0.0)), 6))
        for name in self.subjects:
            st = self.state[name]
            st["food_series"].append(round(self._food(name), 6))
            st["turn_rows"].append({"turn": turn, "alive": int(self.world.is_alive(name)),
                                    "strain": round(float(self._attr(name, "strain", 0.0)), 6),
                                    "food": round(self._food(name), 6), "proposals": st["proposals"],
                                    "failures": st["failures"], "repeat_failures": st["repeat_failures"],
                                    "refusals": sum(st["refusals_by_reason"].values()),
                                    "work_applied": st["work_applied"], "accidents": st["accidents"],
                                    "breakages": st["breakages"]})
        self.population.append({"turn": turn, "alive": alive_total,
                                "failures": sum(st["failures"] for st in self.state.values()),
                                "repeat_failures": sum(st["repeat_failures"] for st in self.state.values()),
                                "refusals": int(self.world.refusal_counts()["total"]),
                                "refusals_by_reason": dict(sorted(self.world.refusal_counts()["by_reason"].items())),
                                "accidents": sum(st["accidents"] for st in self.state.values()),
                                "breakages": sum(st["breakages"] for st in self.state.values()),
                                "unattributed_breakages": self.unattributed_breakages})

    def _food(self, name: str) -> float:
        total = 0.0
        for kind, qty in self.world.inventory(name).items():
            if self.world._item_specs.get(kind, {}).get("food"):
                total += float(qty)
        return total

    def finish(self) -> None:
        """Close open episodes as censored, and read the end state."""
        for name, st in self.state.items():
            if st["episode"] is not None:
                st["adaptations"].append({"key": st["episode"]["key"], "tries": st["episode"]["tries"],
                                          "closed": False})
                st["episode"] = None

    def ties(self, name: str) -> int:
        count = 0
        for (a, b), bond in self.world._relationships.items():
            if name in (a, b) and float(self.world.eng.node(bond)["attrs"].get("strength", 0.0)) > 0.0:
                count += 1
        return count


# ---------------------------------------------------------------- summaries
def _rate(part: int, whole: int):
    return None if whole == 0 else round(part / whole, 6)


def _mean(values):
    values = [v for v in values if v is not None]
    return None if not values else round(sum(values) / len(values), 6)


def summarise_resident(recorder: Recorder, name: str, backend=None) -> dict[str, Any]:
    st = recorder.state[name]
    closed = [a["tries"] for a in st["adaptations"] if a["closed"]]
    censored = [a["tries"] for a in st["adaptations"] if not a["closed"]]
    counts = {}
    if backend is not None:
        raw = getattr(backend, "llm_counts", None)
        counts = raw() if callable(raw) else (raw or {})
    successes = int(counts.get("successes", 0)) if counts else 0
    deviations = int(counts.get("deviations", 0)) if counts else 0
    return {
        "survived": bool(recorder.world.is_alive(name)),
        "food_end": round(recorder._food(name), 6),
        "food_mean": _mean(st["food_series"]),
        "work_applied": st["work_applied"],
        "ties_end": recorder.ties(name),
        "proposals": st["proposals"], "applied": st["applied"],
        "failures": st["failures"], "repeat_failures": st["repeat_failures"],
        "repeat_mistake_rate": _rate(st["repeat_failures"], st["failures"]),
        "body_state_refusals": st["body_state_refusals"],
        "refusals_by_reason": dict(sorted(st["refusals_by_reason"].items())),
        "refusals": sum(st["refusals_by_reason"].values()),
        "adaptation": {"switched": len(closed), "tries_before_switch_mean": _mean(closed),
                       "censored_episodes": len(censored), "censored_tries": censored},
        "improvised_attempts": st["improvised_attempts"], "wrong_tool_attempts": st["wrong_tool_attempts"],
        "accidents": st["accidents"], "breakages": st["breakages"],
        "tools_used": dict(sorted(st["tools"].items())),
        "strain_end": st["strain_series"][-1] if st["strain_series"] else 0.0,
        "strain_max": max(st["strain_series"]) if st["strain_series"] else 0.0,
        "lessons_recorded": len(st["lessons"]),
        "lessons": [{"turn": item["turn"], "text": item["text"], "concerns": item["concerns"]}
                    for item in st["lessons"]],
        "llm": {"successes": successes, "deviations": deviations,
                "deviation_rate": _rate(deviations, successes),
                "failures": int(counts.get("failures", 0)) if counts else 0,
                "autopilot_turns": int(counts.get("autopilot_turns", 0)) if counts else 0,
                "calls": int(counts.get("calls", 0)) if counts else 0} if backend is not None else None,
    }


def lessons_used(recorder: Recorder, records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Offered and used counts per resident, read from the log's messages (see the module doc)."""
    out: dict[str, dict[str, int]] = {}
    turns_by_resident: dict[str, list[tuple[int, str]]] = {}
    for record in records:
        if record.get("kind") != "call":
            continue
        text = "\n".join(str(m.get("content", "")) for m in record.get("messages", []) or [])
        turns_by_resident.setdefault(str(record.get("resident")), []).append((int(record.get("turn", -1)), text))
    for name in recorder.subjects:
        offered = used = recorded = 0
        seq = turns_by_resident.get(name, [])
        keys = recorder.state[name]["keys_by_turn"]
        for item in recorder.state[name]["lessons"]:
            recorded += 1
            later = [(turn, text) for turn, text in seq if turn > item["turn"] and item["text"] in text]
            if not later:
                continue
            offered += 1
            first_offer = later[0][0]
            # The reply to the consult that carries the lesson is the first decision the lesson can change.
            after = sorted(turn for turn in keys if turn >= first_offer)
            if after and item.get("concerns") is not None and keys[after[0]] != item["concerns"]:
                used += 1
        out[name] = {"recorded": recorded, "offered": offered, "used": used}
    return out


# ---------------------------------------------------------------- arms
def _provider_for(kind: str, pack: str):
    if kind == "learner":
        return ScriptedLearner(pack)
    if kind == "nonlearner":
        return ScriptedNonLearner(pack)
    raise ValueError(f"unknown scripted provider {kind!r}")


def ocelot_status() -> dict[str, Any]:
    """Whether the Ocelot backend can be used here. The adapter lives in a sibling checkout, so a plain checkout
    usually cannot import it. The arm is then reported as skipped, with the reason."""
    try:
        from .backends import ocelot  # noqa: F401
        import worlds.bigville_ocelot_adapter  # noqa: F401
    except Exception as exc:  # any import failure means the arm cannot run here
        return {"status": "skipped", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"status": "available", "reason": ""}


def run_arm(name: str, *, kind: str, scenario: str = DEFAULT_SCENARIO, seed: int = DEFAULT_SEED,
            turns: int = DEFAULT_TURNS, llm_residents: int = DEFAULT_LLM_RESIDENTS,
            provider: str | None = None, autopilot: bool = True, budget: bool = True,
            pack: str = DEFAULT_PACK, log_path: str | Path | None = None) -> dict[str, Any]:
    """Run one arm and return its record. ``kind`` is "simple" (every resident on the simple backend) or "llm"
    (``llm_residents`` residents on a scripted provider; the others simple). ``budget`` applies the pack's daily
    call cap to the LLM residents; the controls run without it, so every turn is a consult."""
    game = create_game(scenario=scenario, seed=seed, default_backend="cheap", autonomous=True)
    subjects = choose_llm_residents(game.characters, llm_residents)
    log = None
    run_provider = None
    if kind == "llm":
        if provider is None:
            raise ValueError("an llm arm needs a provider name")
        run_provider = _provider_for(provider, pack)
        shared = CallBudget(max_calls_per_day=autopilot_table(pack)["max_calls_per_resident_per_day"]) \
            if budget else None
        if log_path is not None:
            Path(log_path).unlink(missing_ok=True)
            Path(log_path).with_suffix(Path(log_path).suffix + ".head.json").unlink(missing_ok=True)
            log = LLMLog(log_path, run_id=f"{name}-{seed}", gzip=True)
        for resident in subjects:
            game.set_backend(resident, LLMBackend(game.characters[resident], run_provider, budget=shared,
                                                  autopilot=autopilot, pack=pack, log=log))
    recorder = Recorder(game, subjects, pack)
    digest = hashlib.sha256()
    for _ in range(int(turns)):
        status = game.step()
        recorder.after_turn(game)
        digest.update(json.dumps({"turn": int(game.world._turn),
                                  "responses": {a: (r.major_action.action if r.major_action else None)
                                                for a, r in sorted(getattr(game, "last_responses", {}).items())},
                                  "results": dict(sorted(getattr(game, "last_results", {}).items()))},
                                 sort_keys=True, default=str).encode())
        if isinstance(status, dict) and status.get("status") == "waiting":
            break
    recorder.finish()
    residents = {}
    for resident in subjects:
        backend = game.backends.get(resident)
        summary = summarise_resident(recorder, resident, backend if kind == "llm" else None)
        residents[resident] = {"summary": summary, "curves": recorder.state[resident]["turn_rows"]}
    result = {
        "name": name, "kind": kind, "provider": provider, "autopilot": bool(autopilot and kind == "llm"),
        "budget": bool(budget and kind == "llm"), "scenario": scenario, "seed": int(seed),
        "turns": int(recorder.population[-1]["turn"]) if recorder.population else 0,
        "subjects": subjects, "residents": residents,
        "population": recorder.population,
        "population_summary": {
            "alive_end": recorder.population[-1]["alive"] if recorder.population else 0,
            "failures": sum(st["failures"] for st in recorder.state.values()),
            "repeat_failures": sum(st["repeat_failures"] for st in recorder.state.values()),
            "refusals": recorder.population[-1]["refusals"] if recorder.population else 0,
            "refusals_by_reason": recorder.population[-1]["refusals_by_reason"] if recorder.population else {},
            "body_state_refusals": sum(st["body_state_refusals"] for st in recorder.state.values()),
            "accidents": sum(st["accidents"] for st in recorder.state.values()),
            "breakages": sum(st["breakages"] for st in recorder.state.values()),
            "unattributed_breakages": recorder.unattributed_breakages,
        },
        "digest": digest.hexdigest(),
        "pack_hash": pack_hash(load_pack(pack)),
        "prompt_schema": PACKET_SCHEMA,
        "log": None,
    }
    if log is not None:
        result["log"] = str(log_path)
        result["guard"] = guard_log(log_path, pack)
        result["void"] = result["guard"]["void"]
        records = read_log(log_path)
        result["lessons_offered"] = lessons_used(recorder, records)
    else:
        result["guard"] = None
        result["void"] = False
        result["lessons_offered"] = {}
    for name in subjects:
        residents[name]["summary"]["lessons_offered"] = result["lessons_offered"].get(name, {"recorded": 0,
                                                                                         "offered": 0, "used": 0})
    return result


def run_controls(*, scenario: str = DEFAULT_SCENARIO, seed: int = DEFAULT_SEED, turns: int = CONTROL_TURNS,
                 pack: str = DEFAULT_PACK, log_dir: str | Path | None = None) -> dict[str, Any]:
    """The learner and the non-learner on the same residents, every turn a consult, no call cap."""
    arms = {}
    for kind in ("learner", "nonlearner"):
        log = None if log_dir is None else Path(log_dir) / f"control_{kind}.jsonl.gz"
        arms[kind] = run_arm(f"control_{kind}", kind="llm", provider=kind, scenario=scenario, seed=seed,
                             turns=turns, autopilot=False, budget=False, pack=pack, log_path=log)
    return {"arms": arms, "comparison": compare_controls(arms)}


def compare_controls(arms: dict[str, dict]) -> dict[str, dict[str, Any]]:
    """Side by side: the repeat-mistake rate, failures and adaptation of each control, over its subjects."""
    out = {}
    for kind, arm in arms.items():
        rows = [arm["residents"][name]["summary"] for name in arm["subjects"]]
        failures = sum(r["failures"] for r in rows)
        repeats = sum(r["repeat_failures"] for r in rows)
        switched = [t for r in rows for t in [r["adaptation"]["tries_before_switch_mean"]] if t is not None]
        out[kind] = {"failures": failures, "repeat_failures": repeats,
                     "repeat_mistake_rate": _rate(repeats, failures),
                     "refusals": sum(r["refusals"] for r in rows),
                     "tries_before_switch_mean": _mean(switched),
                     "censored_episodes": sum(r["adaptation"]["censored_episodes"] for r in rows),
                     "lessons_recorded": sum(r["lessons_recorded"] for r in rows),
                     "lessons_offered": sum(r["lessons_offered"]["offered"] for r in rows),
                     "lessons_used": sum(r["lessons_offered"]["used"] for r in rows),
                     "void": bool(arm.get("void"))}
    return out


def marginal(llm_arm: dict[str, Any], simple_arm: dict[str, Any]) -> dict[str, Any]:
    """What the model changed: the deviation rate of each LLM resident, and its outcomes against the same resident
    in the pure-simple run on the same seed."""
    rows = []
    for name in llm_arm["subjects"]:
        model = llm_arm["residents"][name]["summary"]
        control = simple_arm["residents"][name]["summary"]
        rows.append({"resident": name,
                     "deviation_rate": model["llm"]["deviation_rate"] if model.get("llm") else None,
                     "successes": model["llm"]["successes"] if model.get("llm") else 0,
                     "survived": {"model": model["survived"], "simple": control["survived"]},
                     "food_end": {"model": model["food_end"], "simple": control["food_end"]},
                     "work_applied": {"model": model["work_applied"], "simple": control["work_applied"]},
                     "ties_end": {"model": model["ties_end"], "simple": control["ties_end"]},
                     "repeat_mistake_rate": {"model": model["repeat_mistake_rate"],
                                             "simple": control["repeat_mistake_rate"]}})
    rates = [row["deviation_rate"] for row in rows if row["deviation_rate"] is not None]
    return {"control_arm": simple_arm["name"], "model_arm": llm_arm["name"], "residents": rows,
            "deviation_rate_mean": _mean(rates)}


def ocelot_skipped(reason: str) -> dict[str, Any]:
    return {"name": "ocelot", "kind": "ocelot", "status": "skipped", "reason": reason}


def digest_of(record: dict[str, Any]) -> str:
    """SHA-256 over the metric content of a record: no file paths, no provenance."""
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ("log", "provenance")}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(strip(record), sort_keys=True, default=str).encode()).hexdigest()


def run_evaluation(*, scenario: str = DEFAULT_SCENARIO, seed: int = DEFAULT_SEED, turns: int = DEFAULT_TURNS,
                   control_turns: int = CONTROL_TURNS, llm_residents: int = DEFAULT_LLM_RESIDENTS,
                   pack: str = DEFAULT_PACK, log_dir: str | Path | None = None) -> dict[str, Any]:
    """The whole evaluation: the two controls, the simple arm, the scripted LLM arms (learner and non-learner, with
    the autopilot and the pack's call cap), the Ocelot arm (skipped when unavailable), and the marginal effect."""
    logs = None if log_dir is None else Path(log_dir)
    controls = run_controls(scenario=scenario, seed=seed, turns=control_turns, pack=pack, log_dir=logs)
    arms: dict[str, Any] = {}
    arms["simple"] = run_arm("simple", kind="simple", scenario=scenario, seed=seed, turns=turns,
                             llm_residents=llm_residents, pack=pack)
    for kind in ("learner", "nonlearner"):
        log = None if logs is None else logs / f"arm_{kind}.jsonl.gz"
        arms[f"scripted_{kind}"] = run_arm(f"scripted_{kind}", kind="llm", provider=kind, scenario=scenario,
                                           seed=seed, turns=turns, llm_residents=llm_residents, pack=pack,
                                           log_path=log)
    status = ocelot_status()
    arms["ocelot"] = ocelot_skipped(status["reason"]) if status["status"] != "available" else         {"name": "ocelot", "kind": "ocelot", "status": "not_run",
         "reason": "adapter importable, but no Ocelot run is part of this evaluation"}
    record = {"schema": SCHEMA, "scenario": scenario, "seed": int(seed), "turns": int(turns),
              "llm_residents": int(llm_residents), "pack": pack, "pack_hash": pack_hash(load_pack(pack)),
              "prompt_schema": PACKET_SCHEMA, "providers": "scripted fakes only (no network)",
              "controls": {"arms": controls["arms"], "comparison": controls["comparison"]},
              "arms": arms, "marginal": marginal(arms["scripted_learner"], arms["simple"])}
    record["void_arms"] = sorted(name for name, arm in arms.items() if arm.get("void"))
    record["digest"] = digest_of(record)
    return record


def write_json(record: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(record, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(record: dict[str, Any]) -> str:
    """The report, in the house style of the preregistered evaluations: a header with the scenario, seed, pack hash
    and prompt schema, the controls, the comparison, the marginal effect, and the void rule."""
    lines = [f"# Learning evaluation: {record['scenario']}, seed {record['seed']}", "",
             f"Schema `{SCHEMA}`. Scenario `{record['scenario']}`, seed `{record['seed']}`, pack `{record['pack']}`, "
             f"pack hash `{record['pack_hash']}`, prompt schema `{record['prompt_schema']}`.", "",
             "Providers are scripted fakes (no network, no model). A VOID arm is reported with its metrics but its "
             "numbers do not count.", ""]
    ctrl = record["controls"]
    lines += ["## Control: learner against non-learner", "",
              f"Same residents, every turn a consult, {ctrl['arms']['learner']['turns']} turns, no call cap.", "",
              "| metric | learner | non-learner |", "| --- | --- | --- |"]
    cmp_ = ctrl["comparison"]
    for label, key in (("learning failures", "failures"), ("repeat failures", "repeat_failures"),
                       ("repeat-mistake rate", "repeat_mistake_rate"), ("refusals", "refusals"),
                       ("tries before switch (mean)", "tries_before_switch_mean"),
                       ("censored episodes (never switched)", "censored_episodes"),
                       ("lessons recorded", "lessons_recorded"), ("void", "void")):
        lines.append(f"| {label} | {_fmt(cmp_['learner'][key])} | {_fmt(cmp_['nonlearner'][key])} |")
    lines.append("")
    lines += ["## Backends on one scenario and seed", "",
              "Failures are learning failures (body-state refusals excluded; see the method note).", "",
              "| arm | kind | void | survived (subjects) | failures | repeat-mistake rate | deviation rate | "
              "work (subjects) | ties (subjects) | body-state refusals (subjects) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for arm in record["arms"].values():
        if arm.get("status") == "skipped":
            lines.append(f"| {arm['name']} | {arm['kind']} | skipped: {arm['reason']} | | | | | | | |")
            continue
        rows = [arm["residents"][n]["summary"] for n in arm["subjects"]]
        deviations = [r["llm"]["deviation_rate"] for r in rows if r.get("llm") and r["llm"]["deviation_rate"] is not None]
        lines.append(
            f"| {arm['name']} | {arm['kind']} | {_fmt(arm['void'])} | "
            f"{sum(r['survived'] for r in rows)}/{len(rows)} | {sum(r['failures'] for r in rows)} | "
            f"{_fmt(_rate(sum(r['repeat_failures'] for r in rows), sum(r['failures'] for r in rows)))} | "
            f"{_fmt(_mean(deviations))} | {sum(r['work_applied'] for r in rows)} | "
            f"{sum(r['ties_end'] for r in rows)} | {sum(r['body_state_refusals'] for r in rows)} |")
    lines.append("")
    if record.get("marginal"):
        marg = record["marginal"]
        lines += [f"## Marginal effect: {marg['model_arm']} against {marg['control_arm']}", "",
                  "Deviation is the share of consulted replies that departed from the autopilot's would-be "
                  f"choice (mean over residents: {_fmt(marg['deviation_rate_mean'])}). Outcomes are the same "
                  "resident's in the pure-simple run on the same seed.", "",
                  "| resident | deviation | survived (model / simple) | food end (model / simple) | "
                  "work (model / simple) | ties (model / simple) |", "| --- | --- | --- | --- | --- | --- |"]
        for row in marg["residents"]:
            lines.append(
                f"| {row['resident']} | {_fmt(row['deviation_rate'])} | "
                f"{_fmt(row['survived']['model'])} / {_fmt(row['survived']['simple'])} | "
                f"{_fmt(row['food_end']['model'])} / {_fmt(row['food_end']['simple'])} | "
                f"{row['work_applied']['model']} / {row['work_applied']['simple']} | "
                f"{row['ties_end']['model']} / {row['ties_end']['simple']} |")
        lines.append("")
    lines += ["## Whole town, per arm", "",
              "All residents, not only the subjects. Body-state refusals are counted here and kept out of the learning "
              "failures.", "",
              "| arm | alive at end | learning failures | body-state refusals | refusals by reason | accidents | "
              "breakages |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for arm in record["arms"].values():
        if arm.get("status") == "skipped":
            continue
        pop = arm["population_summary"]
        by_reason = ", ".join(f"{k} {v}" for k, v in sorted(pop["refusals_by_reason"].items())) or "none"
        lines.append(f"| {arm['name']} | {pop['alive_end']} | {pop['failures']} | {pop['body_state_refusals']} | "
                     f"{by_reason} | {pop['accidents']} | {pop['breakages']} |")
    lines.append("")
    lines += ["## Leak guard", "", "| arm | prompts checked | violations | void |", "| --- | --- | --- | --- |"]
    for arm in record["arms"].values():
        guard = arm.get("guard")
        if guard:
            lines.append(f"| {arm['name']} | {guard['prompts_checked']} | {guard['violation_count']} | "
                         f"{_fmt(guard['void'])} |")
    lines.append("")
    lines += ["## Method", "",
              "Every metric is read from the engine's records (see `bigville/learning_eval.py`). A body-state refusal "
              "(asleep, collapsed, passed out) is counted as a refusal and kept out of the learning failures. The arms share "
              "the seed, so the residents and the first turn are the same in each arm. The digest of each arm is "
              f"the SHA-256 of its per-turn proposals and results: `{record['digest']}`.", ""]
    return "\n".join(lines)
