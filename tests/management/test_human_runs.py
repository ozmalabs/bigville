import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.management.runs import RunConflict, RunRegistry


@pytest.fixture
def human_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    value = {
        "id": "human_fixture", "name": "Human Fixture",
        "map": {"grid": [["wall"] * 6] + [["wall"] + ["floor"] * 4 + ["wall"] for _ in range(4)] + [["wall"] * 6],
                "layout": {"w": 6, "h": 6, "homes": [[2, 2], [3, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]},
                   {"name": "Bob", "role": "hand", "backend": "simple", "home_cell": [3, 2]}],
    }
    (root / "human_fixture.json").write_text(json.dumps(value))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return value


def draft(**changes):
    value = {"scenario_id": "human_fixture", "name": "Human test", "seed": 42,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world",
             "turn_limit": 4}
    value.update(changes)
    return value


def test_player_selection_requires_a_valid_cast_member(human_scenario):
    valid = resolve_draft(draft(autonomous=False, player="Ada"))
    assert valid["valid"], valid["errors"]
    assert valid["canonical_config"]["player"] == "Ada"
    assert next(item for item in valid["canonical_config"]["resolved_actor_profiles"]
                if item["actor"] == "Ada")["backend"] == "human"
    assert not resolve_draft(draft(autonomous=False))["valid"]
    assert "player" in resolve_draft(draft(autonomous=False, player="Missing"))["errors"]
    assert "player" in resolve_draft(draft(player="Ada"))["errors"]


def test_town100_player_is_resolved_from_the_real_built_in_cast():
    from bigville.api import create_world

    name = sorted(create_world(scenario="town100", seed=73)._actors)[0]
    result = resolve_draft(draft(scenario_id="town100", seed=73,
                                 autonomous=False, player=name))
    assert result["valid"], result["errors"]
    assert result["canonical_config"]["player"] == name


def test_human_prompt_is_agent_only_and_submission_advances_once(human_scenario, tmp_path):
    resolution = resolve_draft(draft(autonomous=False, player="Ada"))
    registry = RunRegistry(tmp_path / "registry")
    record, _ = registry.create_run({
        "draft": draft(autonomous=False, player="Ada"), "idempotency_key": "human-test",
        "expected_config_hash": resolution["configuration_hash"],
        "expected_capability_revision": resolution["capability_revision"],
    })
    game = registry._ensure_game(registry._runtime[record["id"]], record)
    game.world.eng.set_attr(game.world._bodies["Ada"], "stamina_reserve", 0.1)

    from bigville.backends import ActorResponse, DeterministicBackend

    class CountingIdle(DeterministicBackend):
        def __init__(self):
            super().__init__(game.characters["Bob"])
            self.calls = 0

        def decide(self, _context):
            from bigville.backends.protocol import ActorResponse
            self.calls += 1
            return ActorResponse()

    bob = CountingIdle()
    game.set_backend("Bob", bob)
    waiting = registry.command(record["id"], "step")
    assert waiting["status"] == "waiting" and bob.calls == 0
    prompt = registry.get_player_prompt(record["id"])
    assert prompt["actor"] == "Ada" and prompt["mode"] == "action"
    assert prompt["view"]["mode"] == "agent" and "referee" not in prompt["view"]
    assert "snapshot" not in prompt
    rest = next(item for item in prompt["actions"] if item["action"] == "rest")
    from bigville.management.runs import InvalidRunRequest
    with pytest.raises(InvalidRunRequest, match="currently advertised"):
        registry.submit_player_input(record["id"], {
            "token": prompt["token"], "turn": prompt["turn"], "selection": "take:forged",
        })
    updated = registry.submit_player_input(record["id"], {
        "token": prompt["token"], "turn": prompt["turn"], "selection": rest["handle"],
    })
    assert updated["status"] == "waiting" and updated["turn"] == 1
    assert bob.calls == 1, "the NPC must decide once for the advanced turn"
    assert game.world.last_outcome("Ada")["applied"] is True
    next_prompt = registry.get_player_prompt(record["id"])
    assert next_prompt["token"] != prompt["token"]
    with pytest.raises(RunConflict, match="stale"):
        registry.submit_player_input(record["id"], {
            "token": prompt["token"], "turn": prompt["turn"], "selection": rest["handle"],
        })


def test_contested_reaction_uses_separate_wait_and_reaction_queue(human_scenario, tmp_path):
    from bigville.backends import ActorResponse, DeterministicBackend
    from bigville.backends.protocol import ProposedAction

    resolution = resolve_draft(draft(autonomous=False, player="Bob"))
    registry = RunRegistry(tmp_path / "registry")
    record, _ = registry.create_run({
        "draft": draft(autonomous=False, player="Bob"), "idempotency_key": "human-reaction",
        "expected_config_hash": resolution["configuration_hash"],
        "expected_capability_revision": resolution["capability_revision"],
    })
    game = registry._ensure_game(registry._runtime[record["id"]], record)
    game.world.eng.set_attr(game.world._bodies["Bob"], "stamina_reserve", 0.1)
    game.world.eng.set_attr(game.world._bodies["Bob"], "str_base", 2.0)
    game.world.eng.set_attr(game.world._bodies["Ada"], "str_base", 0.2)
    game.world._move_actor_to("Ada", game.world.actor_position("Bob"))
    game.world.set_coin("Bob", 10.0)

    class Taker(DeterministicBackend):
        def decide(self, _context):
            return ActorResponse(major_action=ProposedAction(
                "take", {"source": "Bob", "kind": "coin", "amount": 1.0}))

    game.set_backend("Ada", Taker(game.characters["Ada"]))
    waiting = registry.command(record["id"], "step")
    assert waiting["status"] == "waiting"
    action_prompt = registry.get_player_prompt(record["id"])
    rest = next(item for item in action_prompt["actions"] if item["action"] == "rest")
    reaction_wait = registry.submit_player_input(record["id"], {
        "token": action_prompt["token"], "turn": action_prompt["turn"],
        "selection": rest["handle"],
    })
    assert reaction_wait["status"] == "waiting"
    prompt = registry.get_player_prompt(record["id"])
    assert prompt["mode"] == "reaction" and prompt["reactions"]
    assert "reaction" in prompt["view"]
    reply = prompt["reactions"][0]
    updated = registry.submit_player_input(record["id"], {
        "token": prompt["token"], "turn": prompt["turn"], "selection": reply,
    })
    assert updated["status"] == "waiting"
    assert game.contest_log[-1]["reaction"] == reply


def test_human_turn_limit_completes_without_requesting_another_action(human_scenario, tmp_path):
    request_draft = draft(autonomous=False, player="Ada", turn_limit=1)
    resolution = resolve_draft(request_draft)
    registry = RunRegistry(tmp_path / "registry")
    record, _ = registry.create_run({
        "draft": request_draft, "idempotency_key": "human-turn-limit",
        "expected_config_hash": resolution["configuration_hash"],
        "expected_capability_revision": resolution["capability_revision"],
    })
    game = registry._ensure_game(registry._runtime[record["id"]], record)
    game.world.eng.set_attr(game.world._bodies["Ada"], "stamina_reserve", 0.1)
    registry.command(record["id"], "step")
    prompt = registry.get_player_prompt(record["id"])
    rest = next(item for item in prompt["actions"] if item["action"] == "rest")
    updated = registry.submit_player_input(record["id"], {
        "token": prompt["token"], "turn": prompt["turn"], "selection": rest["handle"],
    })
    assert updated["status"] == "completed" and updated["turn"] == 1


def test_player_input_endpoint_rejects_unauthorized_actor_and_raw_params(human_scenario, tmp_path):
    server = create_server(port=0, data_dir=tmp_path / "server-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        draft_value = draft(autonomous=False, player="Ada")
        resolution = resolve_draft(draft_value)
        created, _ = server.run_registry.create_run({
            "draft": draft_value, "idempotency_key": "http-human",
            "expected_config_hash": resolution["configuration_hash"],
            "expected_capability_revision": resolution["capability_revision"],
        })
        record = server.run_registry.command(created["id"], "step")
        prompt = server.run_registry.get_player_prompt(record["id"])
        forbidden_view = Request(
            f"{base}{API_PREFIX}/runs/{record['id']}/views/agent?actor=Bob")
        with pytest.raises(HTTPError) as forbidden:
            urlopen(forbidden_view)
        assert forbidden.value.code == 400
        from bigville.management.runs import InvalidRunRequest
        with pytest.raises(InvalidRunRequest, match="Only the selected player"):
            server.run_registry.get_run_view(record["id"], perspective="agent", actor="Bob")
        url = f"{base}{API_PREFIX}/runs/{record['id']}/player-input"
        request = Request(url, data=json.dumps({
            "token": prompt["token"], "turn": prompt["turn"], "selection": "rest",
            "actor": "Bob",
        }).encode(), method="POST", headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as invalid:
            urlopen(request)
        body = json.loads(invalid.value.read())
        assert invalid.value.code == 422 and "input" in body["error"]["fields"]

        raw = Request(url, data=json.dumps({
            "token": prompt["token"], "turn": prompt["turn"], "selection": "rest",
            "major_action": {"action": "take", "params": {"source": "Bob", "amount": 1000}},
        }).encode(), method="POST", headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as unsupported:
            urlopen(raw)
        assert unsupported.value.code == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
