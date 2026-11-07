"""TG03: the frozen decision snapshot and pooled context construction.

Two equivalence claims are exercised here:

* ``context_workers=1`` and ``context_workers=4`` build the same contexts and
  leave the same ``TurnTrace`` digest.
* The default deferred pipeline (``_defer_decisions=True``) matches the old
  inline build-then-decide loop (``_defer_decisions=False``), including the
  notoriously easy-to-move ``_published_practice`` windows and the human
  ``waiting`` early return.

The scenarios are the standard ``town100`` seed 305000 and the small
three-resident room used by the TG01 oracle.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import pytest

from bigville.api import create_game
from bigville.backends import HumanBackend
from bigville.backends.cheap import CheapBackend
from bigville.backends.protocol import ActorContinuation, ProposedAction
from bigville.tick_trace import TurnTrace, canonical

TURNS = 4

SMALL_SCENARIO = {
    "id": "tg03_snapshot_room",
    "name": "TG03 snapshot room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


def _town():
    return create_game(scenario="town100", seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False)


def _small():
    return create_game(scenario=SMALL_SCENARIO, seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False)


def _games(name):
    return _town if name == "town" else _small


def _install_context_capture(game):
    """Record every context a backend is actually handed, canonically.

    Wrapping the instance ``decide``/``note_turn`` is deliberate: it captures
    exactly the opportunities the old inline loop gave each backend, including
    the note-turn-only contexts of uninterrupted continuations.
    """
    records: dict[str, list[dict]] = {}
    lock = threading.Lock()

    def record(name, context):
        entry = {"turn": int(context.turn),
                 "observations": canonical(context.observations),
                 "affordances": canonical(context.affordances)}
        with lock:
            records.setdefault(name, []).append(entry)

    for name, backend in game.backends.items():
        original_decide = backend.decide

        def decide(context, _name=name, _original=original_decide):
            record(_name, context)
            return _original(context)

        backend.decide = decide
        original_note = getattr(backend, "note_turn", None)
        if callable(original_note):
            def note_turn(context, _name=name, _original=original_note):
                record(_name, context)
                return _original(context)

            backend.note_turn = note_turn
    return records


def _run_variant(make_game, *, defer, workers, turns=TURNS):
    game = make_game()
    game._defer_decisions = defer
    game.context_workers = workers
    contexts = _install_context_capture(game)
    trace = TurnTrace()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add(game)
    return {"digest": trace.hexdigest(),
            "records": list(trace.records),
            "contexts": contexts}


@lru_cache(maxsize=None)
def _variants(name):
    """The three runs a scenario needs, built once for both comparisons."""
    make = _games(name)
    return {
        "serial": _run_variant(make, defer=True, workers=1),
        "pooled": _run_variant(make, defer=True, workers=4),
        "inline": _run_variant(make, defer=False, workers=1),
    }


@pytest.mark.parametrize("name", ["small", "town"])
def test_pooled_context_build_matches_serial(name):
    variants = _variants(name)

    assert variants["pooled"]["contexts"] == variants["serial"]["contexts"]
    assert variants["pooled"]["digest"] == variants["serial"]["digest"]
    assert variants["pooled"]["records"] == variants["serial"]["records"]


@pytest.mark.parametrize("name", ["small", "town"])
def test_deferred_pipeline_matches_the_inline_oracle(name):
    variants = _variants(name)

    assert variants["serial"]["digest"] == variants["inline"]["digest"]
    assert variants["serial"]["records"] == variants["inline"]["records"]
    assert variants["serial"]["contexts"] == variants["inline"]["contexts"]


def test_context_build_is_read_only_and_snapshot_records_positions():
    game = _small()
    game._verify_context_purity = True
    actors = list(game.backends)
    before = game._world_checkpoint_digest()

    snapshot, contexts = game._build_contexts(actors)

    assert game._world_checkpoint_digest() == before
    assert snapshot.turn == int(game.world._turn)
    assert snapshot.positions == dict(game.world._actor_positions)
    assert set(snapshot.practice_windows) == set(actors)
    assert set(contexts) == set(actors)
    # Explicit form of the debug check.
    game._assert_decision_snapshot_unchanged(snapshot, before)


def test_pooled_and_serial_contexts_are_identical_for_one_snapshot():
    serial, pooled = _small(), _small()
    pooled.context_workers = 4
    actors = list(serial.backends)

    serial_snapshot, serial_contexts = serial._build_contexts(actors)
    pooled_snapshot, pooled_contexts = pooled._build_contexts(actors)

    assert serial_snapshot.positions == pooled_snapshot.positions
    assert serial_snapshot.practice_windows == pooled_snapshot.practice_windows
    for actor in actors:
        assert canonical(pooled_contexts[actor].observations) == \
            canonical(serial_contexts[actor].observations)
        assert canonical(pooled_contexts[actor].affordances) == \
            canonical(serial_contexts[actor].affordances)


class _NoteTurnCheap(CheapBackend):
    """A cheap resident that sees contexts even while holding a continuation."""

    def __init__(self, character, **kwargs):
        super().__init__(character, **kwargs)
        self.noted_turns: list[int] = []

    def note_turn(self, context):
        self.noted_turns.append(int(context.turn))


def _practice_game(defer):
    game = _small()
    game._defer_decisions = defer
    game.set_backend("Cy", _NoteTurnCheap(game.characters["Cy"]))
    request = ActorContinuation(task=ProposedAction("rest", {"kind": "tg03_practice"}),
                                interrupt_on=())
    # Ada holds an uninterrupted plan with no note_turn hook, so the inline
    # loop never builds her context. Cy holds one but does have the hook.
    game._activate_continuation("Ada", request, action_ok=True)
    game._activate_continuation("Cy", request, action_ok=True)
    return game


def test_practice_windows_match_the_inline_path_with_mixed_continuations():
    deferred, inline = _practice_game(True), _practice_game(False)
    deferred_history, inline_history = [], []

    for _ in range(3):
        assert deferred.step()["status"] == "advanced"
        deferred_history.append(dict(deferred._published_practice))
        assert inline.step()["status"] == "advanced"
        inline_history.append(dict(inline._published_practice))

    assert deferred_history == inline_history
    # Ada's uninterrupted continuation never gets a context, so her window is
    # never published; Cy's note_turn hook forces one every turn.
    assert "Ada" not in deferred._published_practice
    assert "Ada" not in inline._published_practice
    assert "Cy" in deferred._published_practice
    assert deferred._published_practice == inline._published_practice
    assert deferred.backends["Cy"].noted_turns == inline.backends["Cy"].noted_turns
    assert len(deferred.backends["Cy"].noted_turns) == 3


def _waiting_game(defer):
    game = _small()
    game._defer_decisions = defer
    game.set_backend("Ben", HumanBackend(game.characters["Ben"]))
    return game


def test_human_waiting_payload_and_later_practice_match_the_inline_path():
    deferred, inline = _waiting_game(True), _waiting_game(False)

    left, right = deferred.step(), inline.step()

    assert left["status"] == right["status"] == "waiting"
    assert left["actor"] == right["actor"] == "Ben"
    assert canonical(left["context"]) == canonical(right["context"])
    assert canonical(left["affordances"]) == canonical(right["affordances"])
    # The inline loop never reached Cy, so the deferred pre-pass must have put
    # Cy's practice window back exactly as it found it.
    assert deferred._published_practice == inline._published_practice
    assert "Cy" not in deferred._published_practice
