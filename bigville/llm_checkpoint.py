"""Checkpoints for LLM residents (fix_llm_ops).

A game checkpoint (bigville/game_persistence.py) stores each resident's backend as JSON. For an ``LLMBackend`` it
stores the output of ``checkpoint_llm_backend``, and on load it calls ``restore_llm_backend``.

What the checkpoint holds: the backend's state (``LLMBackend.to_dict``: threads, counts, gate, autopilot, call
budget counts), and the constructor settings that the state does not hold (pack names, thread size, full-packet
interval, concurrency, the autopilot's policy, and the call budget's caps).

What it does not hold:

* The provider. A provider is a live object (a client with a key, or a replay file). The caller passes it at load.
* The character. Memories and held frames are in the game checkpoint. The restored backend must be built for the
  character restored from the same checkpoint.
* The log. The log is a file. The caller attaches one (``llm_log.attach_default`` or ``attach``).
* A custom prompt builder, schema, or a policy with a hook callback. These are refused at save, so a checkpoint
  never silently drops them.

Shared budget: the LLM residents of one game usually share one ``CallBudget`` (``build_llm_town``). ``llm_budget_for``
rebuilds one shared budget from all the LLM entries of a checkpoint. Its per-resident day counts are the union of
the entries, and its spend is the largest value seen. For a shared budget every entry holds the same values, so this
is exact. For separate budgets (``create_game`` gives each LLM resident its own) the day counts are disjoint and the
union is exact, but the spend is the largest single resident's spend, not the sum. ``create_game`` sets no spend cap,
so the spend total does not limit anything there.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Iterable

from domains.autopilot import DEFAULT_PACK
from .backends.autopilot import CallBudget
from .backends.cheap import SimplePolicy
from .backends.llm import LLMBackend
from .backends.prompts import PROMPT_SCHEMA, PromptBuilder

KIND = "llm"
SCHEMA = "bigville/llm-checkpoint/1"


def _json(value: Any) -> Any:
    """A JSON-safe copy. Raises if the value holds anything JSON cannot represent."""
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _policy_to_json(policy: SimplePolicy) -> dict[str, Any]:
    if type(policy) is not SimplePolicy:
        raise TypeError(f"custom simple policy class {type(policy).__name__} cannot be checkpointed")
    if policy.hook is not None:
        raise TypeError("SimplePolicy hook callbacks cannot be checkpointed")
    data = asdict(policy)
    data.pop("hook")
    return _json(data)


def _policy_from_json(data: dict[str, Any]) -> SimplePolicy:
    # JSON has no tuples: fields that were tuples come back as lists.
    fields = {key: tuple(value) if isinstance(value, list) else value for key, value in data.items()}
    return SimplePolicy(**fields, hook=None)


def checkpoint_llm_backend(backend: LLMBackend) -> dict[str, Any]:
    """The checkpoint of one LLM backend as JSON-safe data. Does not store the provider, the character or the log."""
    if not isinstance(backend, LLMBackend):
        raise TypeError(f"not an LLM backend: {type(backend).__name__}")
    if backend.prompt_builder.schema != PROMPT_SCHEMA:
        raise TypeError(f"prompt schema {backend.prompt_builder.schema!r} cannot be checkpointed")
    autopilot = backend.autopilot
    policy = None
    if autopilot is not None:
        policy = _policy_to_json(autopilot.policy)
    budget = None
    if backend.budget is not None:
        budget = {"max_calls_per_day": backend.budget.max_calls_per_day, "max_spend": backend.budget.max_spend}
    config = {
        "prompt_pack": backend.prompt_builder.pack.name,
        "pack": backend.gate.pack if backend.gate is not None else None,
        "autopilot": autopilot is not None,
        "policy": policy,
        "thread_chars": backend.thread_chars,
        "full_every": backend.full_every,
        "concurrency": int(backend.concurrency),
        "budget": budget,
    }
    return _json({"kind": KIND, "schema": SCHEMA, "resident": backend.character.character_id,
                  "config": config, "state": backend.to_dict()})


def _check_envelope(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise ValueError(f"not an LLM checkpoint: kind {data.get('kind') if isinstance(data, dict) else type(data)!r}")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported LLM checkpoint schema: {data.get('schema')!r}")


def restore_llm_backend(data: dict[str, Any], character, provider=None, *,
                        budget: CallBudget | None = None) -> LLMBackend:
    """The LLM backend in ``data``, for ``character``. ``provider`` is required: the checkpoint does not hold one.

    ``budget``: a budget to share with the other LLM residents (see ``llm_budget_for``). When it is given, the
    budget's counts are not reset from this entry. When it is None, the backend gets its own budget with the saved
    caps and counts."""
    _check_envelope(data)
    if provider is None:
        raise ValueError(f"the LLM resident {data.get('resident')!r} needs a provider to resume from this checkpoint: "
                         "pass llm_provider=... (a checkpoint does not hold the provider)")
    if data.get("resident") != character.character_id:
        raise ValueError(f"checkpoint is for {data.get('resident')!r}, not {character.character_id!r}")
    config = data["config"]
    state = dict(data["state"])
    if budget is None and config["budget"] is not None:
        budget = CallBudget(**config["budget"])
    elif budget is not None:
        state["budget"] = None
    policy = _policy_from_json(config["policy"]) if config["policy"] is not None else None
    backend = LLMBackend.from_dict(
        state, character, provider,
        prompt_builder=PromptBuilder(pack=config["prompt_pack"]),
        autopilot=bool(config["autopilot"]), policy=policy,
        budget=budget, pack=config["pack"] or DEFAULT_PACK,
        thread_chars=config["thread_chars"], full_every=config["full_every"])
    backend.concurrency = int(config["concurrency"])
    return backend


def llm_budget_for(checkpoints: Iterable[Any]) -> CallBudget | None:
    """One budget for all the LLM entries of a checkpoint (the entries that are not LLM are ignored). None when there
    are none, or when they have no budget. See the module docstring for how the counts and spend are merged."""
    entries = [data for data in checkpoints if isinstance(data, dict) and data.get("kind") == KIND]
    for data in entries:
        _check_envelope(data)
    caps = [data["config"]["budget"] for data in entries]
    if any(cap != caps[0] for cap in caps):
        raise ValueError("LLM residents in one checkpoint disagree about the call budget caps")
    if not caps or caps[0] is None:
        return None
    shared = CallBudget(**caps[0])
    calls: dict[tuple, int] = {}
    spent = 0.0
    for data in entries:
        snapshot = data["state"]["budget"]
        if snapshot is None:
            continue
        for resident, day, count in snapshot["calls_by_day"]:
            key = (resident, day)
            calls[key] = max(calls.get(key, 0), int(count))
        spent = max(spent, float(snapshot["spent"]))
    shared.calls_by_day = calls
    shared.spent = spent
    return shared
