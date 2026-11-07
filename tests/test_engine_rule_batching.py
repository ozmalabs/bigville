"""EN03: opt-in turn-batched world-rule resolution.

``rule_batching="action"`` is the historical mode and the direct
``BigvilleGame`` default (``create_game`` defaults to ``"auto"`` since EN05):
every primitive action's ``_run()`` sweeps immediately.  ``"turn"`` opens one re-entrant
``world.batch_rules()`` scope around the action commit, records that a sweep is
owed, and lets ``_finish_turn`` run the single authoritative sweep.  A turn is
still one advanced turn with the same applied/refused records.
"""
from __future__ import annotations

import json

import pytest

from bigville.api import create_game, create_world
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.human import HumanBackend
from bigville.game import BigvilleGame
from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint
from worlds.bigville_world import BigvilleWorld

A, B, C, H = "Ada", "Ben", "Cy", "Hal"
CRATE = "crate"


def _room(*, decay=False, actors=None):
    actors = actors or ((A, "resident", [1, 1]),
                        (B, "resident", [2, 2]),
                        (C, "farmer", [3, 3]))
    return {
        "id": "en03_rule_batching_room",
        "name": "EN03 rule batching room",
        "map": {"grid": [["floor"] * 6 for _ in range(6)]},
        "actors": [{"name": name, "role": role, "home_cell": cell,
                    "backend": "simple"} for name, role, cell in actors],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False,
                                "decay": decay},
        "buildings": [], "laws": [], "policies": [], "charters": [],
    }


def _game(*, scenario=None, **kwargs):
    options = dict(scenario=scenario or _room(), seed=305000,
                   default_backend="simple", autonomous=True, llm_log=False,
                   snapshot_mode="on_demand")
    options.update(kwargs)
    return create_game(**options)


class _Proposal(DeterministicBackend):
    """A deterministic resident that always proposes one fixed major action."""

    def __init__(self, character, proposal):
        super().__init__(character)
        self._proposal = proposal

    def decide(self, context):
        return ActorResponse(major_action=self._proposal)


class _OnceProposal(_Proposal):
    """Propose the fixed action once, then do nothing."""

    def __init__(self, character, proposal):
        super().__init__(character, proposal)
        self._done = False

    def decide(self, context):
        if self._done:
            return ActorResponse()
        self._done = True
        return super().decide(context)


class _Taker(DeterministicBackend):
    """Propose to take four coin from Hal."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "take", {"source": H, "kind": "coin", "amount": 4.0}))


def _count_sweeps(world):
    """Count *actual* ``_run`` executions, not deferred requests."""
    calls = []
    real = world._run

    def measured(*args, **kwargs):
        calls.append(bool(kwargs.get("force")))
        return real(*args, **kwargs)

    world._run = measured
    return calls


# ------------------------------------------------------------------ call count
def test_turn_mode_run_count_is_constant_and_action_mode_keeps_the_old_count():
    action = _game(rule_batching="action")
    turn = _game(rule_batching="turn")
    action_calls = _count_sweeps(action.world)
    turn_calls = _count_sweeps(turn.world)

    action_per_turn, turn_per_turn = [], []
    for _ in range(3):
        before = len(action_calls)
        action.step()
        action_per_turn.append(len(action_calls) - before)

        before = len(turn_calls)
        turn.step()
        turn_per_turn.append(len(turn_calls) - before)

    # Three actors: action mode is actions + the two tick passes + finish.
    assert action_per_turn == [6, 6, 6]
    # Turn mode is the two world.tick passes + one finish sweep.
    assert turn_per_turn == [3, 3, 3]
    assert len(turn_calls) == 9
    assert len(action_calls) == 18


# ------------------------------------------------------------------ turn result
def test_turn_still_advances_applies_and_records_a_refusal():
    game = _game(rule_batching="turn")
    start = game.world.actor_position(A)
    destination = next(cell for cell in sorted(game.world._map_cells)
                       if abs(cell[0] - start[0]) + abs(cell[1] - start[1]) == 1)
    game.set_backend(A, _Proposal(game.characters[A],
                                  ProposedAction("move", {"destination": destination})))
    # Moving to the cell the resident already stands on is refused.
    game.set_backend(B, _Proposal(game.characters[B],
                                  ProposedAction("move", {"destination":
                                                          game.world.actor_position(B)})))

    result = game.step()

    assert result["status"] == "advanced"
    assert result["turn"] == 1
    assert result["results"] == game.last_results
    assert game.last_results[A] is True
    assert game.last_results[B] is False
    assert game.world.actor_position(A) == destination
    assert game.world.refusal_counts()["total"] >= 1
    assert game.world.rules_pending is False
    assert game.world._rule_batch_depth == 0


# ------------------------------------------------------------------ body stats
def test_movement_body_stats_turn_changes_energy_and_settles_rules():
    game = _game(rule_batching="turn")
    before = {name: game.world.energy(name) for name in (A, B, C)}

    result = game.step()

    assert result["status"] == "advanced"
    assert all(applied for applied in game.last_results.values())
    after = {name: game.world.energy(name) for name in (A, B, C)}
    assert any(abs(after[name] - before[name]) > 1e-9 for name in before)
    assert game.world.rules_pending is False


# ------------------------------------------------------------------ job turn
def _sawpit_game(rule_batching: str):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_tradesperson("Sawyer", "sawyer")
    world.set_stock("lumber", 20)
    x, y, _width, _height = world._building_sites["sawpit"]
    world._move_actor_to("Sawyer", (x, y))
    game = BigvilleGame(world, autonomous=True, rule_batching=rule_batching,
                        snapshot_mode="on_demand")
    game.set_backend("Sawyer", _OnceProposal(
        game.characters["Sawyer"],
        ProposedAction("work", {"recipe": "saw_planks"})))
    return world, game


def test_job_start_and_progress_turn_is_batched():
    world, game = _sawpit_game("turn")

    first = game.step()
    assert first["status"] == "advanced"
    assert game.last_results["Sawyer"] is True
    job = world._job_of("Sawyer")
    assert job is not None
    remaining = float(world.eng.node(job)["attrs"]["remaining"])
    assert remaining > 0.0
    assert world.rules_pending is False

    second = game.step()
    assert second["status"] == "advanced"
    assert float(world.eng.node(job)["attrs"]["remaining"]) < remaining
    assert world.rules_pending is False


# ------------------------------------------------------------------ stock / decay
def test_stock_decay_period_turn_settles_its_own_sweep():
    game = _game(scenario=_room(decay=True), rule_batching="turn",
                 ticks_per_period=1)
    game.world.set_stock("bread", 20)
    before = game.world.stock_condition("bread")

    for _ in range(2):
        assert game.step()["status"] == "advanced"
        assert game.world.rules_pending is False
        assert game.world._rule_batch_depth == 0

    assert game.world.qty("bread") == 20.0
    assert game.world.stock_condition("bread") < before


# ------------------------------------------------------------------ sleep / rest
def test_rest_turn_recovers_stamina_and_settles_rules():
    game = _game(rule_batching="turn")
    body = game.world._bodies[A]
    game.world.eng.set_attr(body, "stamina", 0.2)
    game.world.eng.set_attr(body, "stamina_reserve", 0.2)
    game.set_backend(A, _Proposal(game.characters[A],
                                  ProposedAction("rest", {"amount": 1.0})))
    before = game.world.stamina_reserve(A)

    result = game.step()

    assert result["status"] == "advanced"
    assert game.last_results[A] is True
    assert game.world.stamina_reserve(A) > before
    assert game.world.rules_pending is False


# ------------------------------------------------------------------ contest
def _contest_pair():
    world = BigvilleWorld(autonomous_actors=False)
    cell = sorted(world._map_cells)[len(world._map_cells) // 2]
    world.add_actor(A, role="hand", home_cell=cell)
    world.add_actor(H, role="hand", home_cell=cell)
    world._move_actor_to(A, cell)
    world._move_actor_to(H, cell)
    world.tick()
    world.mark_turn_start()
    world.set_coin(H, 10.0)
    return world


def test_contested_waiting_and_resume_turn_work_in_turn_mode():
    world = _contest_pair()
    game = BigvilleGame(world, autonomous=True, rule_batching="turn",
                        snapshot_mode="on_demand")
    human = HumanBackend(game.characters[H],
                         chooser=lambda context: ActorResponse())
    game.set_backend(H, human)
    game.set_backend(A, _Taker(game.characters[A]))

    waiting = game.step()
    assert waiting["status"] == "waiting"
    assert waiting["actor"] == H
    assert "yield" in waiting["reaction"]["options"]
    assert world.rules_pending is False

    human.submit_reaction(ActorResponse(backend_state={"reaction": "yield"}))
    done = game.step()
    assert done["status"] == "advanced"
    assert game.last_results[A] is True
    assert world.rules_pending is False
    assert world._rule_batch_depth == 0


# ------------------------------------------------------------------ joint turn
def _open_cell(world):
    for cell in sorted(world._map_cells):
        line = [(cell[0] + k, cell[1]) for k in range(5)]
        if all(c in world._map_cells and world.terrain_state(c)["speed"] > 0
               for c in line):
            return cell
    raise AssertionError("no open ground")


def _crate_world():
    world = BigvilleWorld(autonomous_actors=False,
                          physical_subsystems={"joint_actions": True})
    cell = _open_cell(world)
    for name in (A, B):
        world.add_actor(name, role="hand", home_cell=cell)
        world._move_actor_to(name, cell)
    node = world.eng.add_node("PhysicalObject", {
        "object_id": CRATE, "name": CRATE, "kind": CRATE, "location": "world",
        "mass": 80.0, "cell": [cell[0] + 1, cell[1]]})
    world._physical_objects[CRATE] = node
    world._physical_object_locations[CRATE] = "world"
    world.tick()
    return world, cell


def _crate_cell(world):
    return world._physical_location_cell(CRATE)


class _Carrier(DeterministicBackend):
    def __init__(self, character, task):
        super().__init__(character)
        self._task = task

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "joint", {"joint": dict(self._task)}, "test"))


def test_joint_turn_is_one_finish_sweep():
    world, _cell = _crate_world()
    game = BigvilleGame(world, autonomous=True, rule_batching="turn",
                        snapshot_mode="on_demand")
    task = {"task": "carry", "object": CRATE, "toward": [1, 0]}
    for name in (A, B):
        game.set_backend(name, _Carrier(game.characters[name], task))
    start = _crate_cell(world)
    calls = _count_sweeps(world)

    result = game.step()

    assert result["status"] == "advanced"
    assert _crate_cell(world) != start
    assert game.last_results == {A: True, B: True}
    assert len(calls) == 3            # two world.tick passes + one finish sweep
    assert not any(force for force in calls[:-1])
    assert world.rules_pending is False


# ------------------------------------------------------------------ executors
@pytest.mark.parametrize("executor", ["serial", "threaded", "partitioned"])
def test_turn_mode_completes_in_every_executor(executor):
    game = _game(rule_batching="turn", executor=executor)
    result = game.step()
    assert result["status"] == "advanced"
    assert result["turn"] == 1
    assert set(game.last_results) == {A, B, C}
    assert all(applied for applied in game.last_results.values())
    assert game.world.rules_pending is False
    assert game.world._rule_batch_depth == 0


# ------------------------------------------------------------------ checkpoints
def test_checkpoint_outside_a_batch_excludes_batch_fields(tmp_path):
    world = create_world(scenario=_room(), seed=305000)
    checkpoint = tmp_path / "outside"
    save_world_checkpoint(world, checkpoint)

    manifest = json.loads((checkpoint / "manifest.json").read_text())
    attrs = json.loads((checkpoint / manifest["generation"] / "world.json").read_text())
    assert "_rule_batch_depth" not in attrs
    assert "_rule_batch_pending" not in attrs

    restored = load_world_checkpoint(checkpoint)
    assert restored._rule_batch_depth == 0
    assert restored.rules_pending is False


def test_checkpoint_during_an_open_batch_is_rejected(tmp_path):
    world = create_world(scenario=_room(), seed=305000)
    with world.batch_rules():
        world._request_rule_sweep()
        assert world.rules_pending is True
        with pytest.raises(ValueError, match="open rule batch"):
            save_world_checkpoint(world, tmp_path / "during")
    assert world.rules_pending is False


# ------------------------------------------------------------------ scope semantics
def test_nested_batches_run_exactly_one_sweep_on_the_outer_exit():
    world = create_world(scenario=_room(), seed=305000)
    passes = []
    real = world._resolve_jobs

    def counted():
        passes.append(1)
        return real()

    world._resolve_jobs = counted
    with world.batch_rules():
        world._run()
        with world.batch_rules():
            world._run()
        assert passes == []
        assert world.rules_pending is True
    assert len(passes) == 1
    assert world.rules_pending is False


# ------------------------------------------------------------------ option
def test_rule_batching_direct_default_is_action_and_validates():
    # EN05: create_game defaults to "auto"; the direct constructor keeps the
    # historical per-action default.
    world = create_world(scenario=_room(), seed=305000)
    game = BigvilleGame(world, autonomous=True)
    assert game.rule_batching_requested == "action"
    assert game.rule_batching == "action"

    game.rule_batching = "turn"
    assert game.rule_batching == "turn"

    with pytest.raises(ValueError):
        game.rule_batching = "sometimes"
    with pytest.raises(ValueError):
        _game(rule_batching="sometimes")
