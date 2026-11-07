"""A town of LLM residents among simple locals (Phase 055), modelled on ``mixed_ocelot_scenario``.

``build_llm_town`` builds the standard town (town100, or another named scenario) with the simple backend
for everyone, then gives ``llm_residents`` of them an ``LLMBackend``. The chosen residents are the first
names in sorted order, so the same seed always gives the same mix. Each LLM resident gets a backend with its
own autopilot (the simple backend for the same character) and the same call budget object, so the pack's
per-day call cap applies to the town as a whole.

The game runs unattended (``autonomous=True``, no player). The provider is any object accepted by
``LLMBackend``; tests pass a fake, and live use passes the OpenCode Go provider from ``bigville.providers``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .api import create_game
from .backends.autopilot import CallBudget
from .backends.llm import LLMBackend
from .llm_log import attach_default as attach_default_llm_log
from domains.autopilot import DEFAULT_PACK, table

DEFAULT_LLM_RESIDENTS = 3
DEFAULT_SCENARIO = "town100"
DEFAULT_SEED = 305000


def choose_llm_residents(names, count: int) -> list[str]:
    """The first ``count`` names in sorted order. Raises when the town has fewer residents."""
    ordered = sorted(names)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("llm_residents must be a non-negative whole number")
    if count > len(ordered):
        raise ValueError(f"the town has {len(ordered)} residents, fewer than the {count} asked for")
    return ordered[:count]


def build_llm_town(provider: Any, *, llm_residents: int = DEFAULT_LLM_RESIDENTS,
                   scenario: str = DEFAULT_SCENARIO, seed: int = DEFAULT_SEED,
                   budget: CallBudget | None = None, concurrency: int | None = None,
                   pack: str = DEFAULT_PACK, settings: Any = None, llm_log: bool = True,
                   llm_log_dir: str | None = None):
    """A game with ``llm_residents`` LLM residents and the rest on the simple backend.

    ``budget`` is shared by the LLM residents; the default is the pack's calls per resident per day, with no
    spend cap. ``concurrency`` sets each LLM resident's pool share (the game's pool is the largest share).
    ``settings`` (an ``OpenCodeGoSettings``) supplies the spend cap and the concurrency from the environment
    when the other two are not given; the providers package is imported only then, so the core stays free of it.
    ``llm_log`` and ``llm_log_dir`` set the complete log (see ``create_game``); the log is ``game.llm_log``."""
    if settings is not None:
        from .providers.opencode_go import build_budget
        if budget is None:
            budget = build_budget(settings, pack)
        if concurrency is None:
            concurrency = settings.concurrency
    game = create_game(scenario=scenario, seed=seed, default_backend="cheap", autonomous=True)
    chosen = choose_llm_residents(game.characters, llm_residents)
    if budget is None:
        budget = CallBudget(max_calls_per_day=table(pack)["max_calls_per_resident_per_day"])
    for name in chosen:
        backend = LLMBackend(game.characters[name], provider, budget=budget)
        if concurrency is not None:
            backend.concurrency = int(concurrency)
        game.set_backend(name, backend)
    game.llm_residents = tuple(chosen)
    game.llm_log = attach_default_llm_log(game.backends, enabled=llm_log, log_dir=llm_log_dir)
    return game


def _utterance_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text", ""))
    return str(getattr(item, "text", item))


def step_record(game) -> dict[str, Any]:
    """What one turn did, in plain values: the turn, each resident's proposal and whether it applied."""
    responses = {}
    for actor, response in sorted(getattr(game, "last_responses", {}).items()):
        action = response.major_action
        responses[actor] = {
            "action": None if action is None else action.action,
            "params": None if action is None else json.loads(json.dumps(action.params, sort_keys=True, default=str)),
            "utterances": [_utterance_text(item) for item in response.utterances],
        }
    return {"turn": int(game.world._turn), "responses": responses,
            "results": {actor: bool(ok) for actor, ok in sorted(getattr(game, "last_results", {}).items())}}


class RunDigest:
    """A SHA-256 over the per-turn records of a run. Two runs with the same digest made the same proposals and got
    the same results, turn by turn."""

    def __init__(self):
        self._hash = hashlib.sha256()
        self.turns = 0

    def add(self, game) -> None:
        self._hash.update(json.dumps(step_record(game), sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8"))
        self._hash.update(b"\n")
        self.turns += 1

    def hexdigest(self) -> str:
        return self._hash.hexdigest()
