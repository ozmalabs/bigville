"""LA05: the lazy LLM path publishes entities and capabilities, not the exhaustive legal menu.

The real provider interface is exercised with the in-process ``FakeProvider``; no network is used. These tests
hold the LLM contract of the lazy path:

* a lazy context gets ``build_lazy_agent_view`` and a packet built from it, with no menu call at all;
* ``public.can`` is a bounded capability list and the packet has no exhaustive ``legal_affordances``;
* a direct proposal in ``major_action.params`` reaches the world and is enacted or refused by it;
* a refusal's reason is visible in the next packet's ``public.last``;
* menu mode keeps its old system text and agent view;
* the UI's explicit on-demand affordance query still works, and ``game.step`` does not use it.
"""
from __future__ import annotations

import json
import unittest.mock as mock

from bigville.api import create_game
from bigville.backends import LLMBackend, reply_schema
from bigville.backends.prompt_packet import packet_system
from bigville.server import GameService
from bigville.tui.client import EmbeddedClient
from domains.pack import load_pack
from tests.llm_stub import FakeProvider
from worlds.bigville_world import BigvilleWorld


SMALL_SCENARIO = {
    "id": "la05_lazy_llm",
    "name": "LA05 lazy LLM room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "llm", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "apple", "name": "apple", "kind": "apple", "location": "table"},
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": True},
    ],
}


def _reply(action=None, **params):
    major = None if action is None else {"action": action, "params": params}
    return json.dumps({"major_action": major, "utterances": [], "memory_updates": [],
                       "continuation": None})


def _game(reply, *, mode="lazy", player=None, autopilot=False):
    provider = FakeProvider(reply)
    if autopilot:
        game = create_game(
            scenario=SMALL_SCENARIO, seed=305101, player=player,
            default_backend="simple", llm_provider=provider,
            autonomous=player is None, llm_log=False, affordance_mode=mode)
    else:
        factory = lambda world, character: LLMBackend(character, provider, autopilot=False)
        game = create_game(
            scenario=SMALL_SCENARIO, seed=305101, player=player,
            default_backend="simple", backend_factories={"llm": factory},
            autonomous=player is None, llm_log=False, affordance_mode=mode)
    game._test_provider = provider
    return game


def _seed_bread(world, actor="Ada", qty=2.0, hunger=2.0):
    stock = world._inventory_stock(actor, "bread", create=True)
    world.eng.set_attr(stock, "qty", float(qty))
    world.eng.set_attr(world._actors[actor], "hunger", float(hunger))


def _spy_menu_calls():
    """Patch the world's two menu builders while a block runs. Returns the call list.

    The patch delegates to the real methods if anything calls them, so a test fails on the count but not on a
    broken menu. The caller passes the returned list to an assertion after the block.
    """
    calls = []
    real_affordances = BigvilleWorld.actor_affordances
    real_options = BigvilleWorld._actor_options

    def actor_affordances(self, actor):
        calls.append(("actor_affordances", actor))
        return real_affordances(self, actor)

    def actor_options(self, actor):
        calls.append(("_actor_options", actor))
        return real_options(self, actor)

    return calls, mock.patch.object(BigvilleWorld, "actor_affordances", actor_affordances), \
        mock.patch.object(BigvilleWorld, "_actor_options", actor_options)


def test_lazy_context_and_packet_build_without_any_menu_call():
    game = _game(_reply("rest"))
    calls, patch_affordances, patch_options = _spy_menu_calls()
    with patch_affordances, patch_options:
        context = game._context("Ada")
        record = game.backends["Ada"].prompt_builder.build(context)
        game.step()
    assert calls == []
    assert context.agent_view is not None
    assert context.affordances == []
    assert isinstance(context.observations.get("entities"), dict)
    # LA05 root alias: the packet's usual-now line and the call budget read it.
    assert context.observations["calendar"]["hour"] == 7.0
    assert record.system.endswith(
        "- The world checks the proposal against what exists. A refusal is ordinary: it is shown in "
        "public.last on the next turn.")
    assert "Proposing in this mode:" in record.system


def test_the_packet_publishes_capabilities_and_entities_not_the_legal_menu():
    game = _game(_reply("rest"))
    context = game._context("Ada")
    record = game.backends["Ada"].prompt_builder.build(context)
    public = record.context["public"]

    assert public["can"], "the lazy packet has no capability rows"
    assert all(row["handle"] == "" for row in public["can"])
    assert {row["action"] for row in public["can"]} >= {"eat", "rest", "walk"}
    assert public["around"]["things"], "the lazy packet has no visible things"
    assert any(row["what"].startswith("apple") for row in public["around"]["things"])
    assert public["around"]["people"], "the lazy packet has no nearby people"
    assert json.dumps(record.context).count("legal_affordances") == 0
    # A bounded list, not the town's exhaustive option set.
    assert len(public["can"]) <= 28


def test_a_direct_eat_proposal_is_accepted_and_enacted_by_the_world():
    game = _game(_reply("eat", kind="bread"))
    _seed_bread(game.world)
    context = game._context("Ada")
    response = game.backends["Ada"].decide(context)
    proposal = response.major_action
    assert proposal is not None and proposal.action == "eat"
    assert proposal.params["kind"] == "bread"

    before = game.world.inventory_qty("Ada", "bread")
    applied = game.world.enact_plan("Ada", {"action": proposal.action, **proposal.params})
    assert applied is True
    assert game.world.inventory_qty("Ada", "bread") < before


def test_a_place_handle_walks_and_an_invalid_destination_is_refused_then_shown_in_last():
    game = _game(_reply("walk", destination=[99, 99]))
    context = game._context("Ada")
    response = game.backends["Ada"].decide(context)
    proposal = response.major_action
    assert proposal is not None and proposal.action == "move"
    assert proposal.params["destination"] == (99, 99)

    applied = game.world.enact_plan("Ada", {"action": proposal.action, **proposal.params})
    assert applied is False
    outcome = game.world.last_outcome("Ada")
    assert outcome and not outcome["applied"]
    reason = str(outcome["reason"])
    assert reason

    next_context = game._context("Ada")
    record = game.backends["Ada"].prompt_builder.build(next_context)
    last = record.context["public"]["last"]
    assert last["outcome"] == "it did not happen"
    assert last["reason"] == load_pack("bigville")["REFUSAL_REASONS"][reason]["description"]
    assert next_context.observations["last_outcome"]["reason"] == reason


def test_a_walk_capability_copies_a_stable_cell_handle_into_destination():
    game = _game(_reply("walk", destination=[99, 99]))
    context = game._context("Ada")
    view = context.agent_view
    cells = [row["handle"] for row in view["around"]["things"] if row["handle"].startswith("cell:")]
    assert cells, "the lazy view published no place cells"
    handle = cells[0]
    wire = reply_schema.to_wire(
        {"major_action": {"action": "walk", "target": handle, "params": {}}},
        "bigville", affordances=[])
    assert wire["major_action"]["action"] == "move"
    destination = wire["major_action"]["params"]["destination"]
    assert isinstance(destination, tuple) and len(destination) == 2
    x, y = handle.split(":", 1)[1].split(",")
    assert destination == (int(x), int(y))


def test_the_autopilot_candidate_rows_do_not_turn_the_lazy_packet_into_the_menu_interface():
    game = _game(_reply("rest"), autopilot=True)
    context = game._context("Ada")
    assert context.affordances == []
    game.backends["Ada"].decide(context)
    # The autopilot wrote its candidate list into the shared context before the consult; the packet and the
    # reply binding must still use the lazy interface.
    assert context.affordances, "the autopilot should carry candidates in lazy mode"
    payload = game._test_provider.calls[-1]["payload"]
    assert "Proposing in this mode:" in payload["system"]
    sent = json.dumps(payload["messages"])
    assert "legal_affordances" not in sent


def test_menu_mode_keeps_the_old_system_text_and_menu_agent_view():
    game = _game(_reply("rest"), mode="menu")
    context = game._context("Ada")
    assert context.affordances
    assert "entities" not in context.observations
    assert context.agent_view is not None
    assert context.agent_view == game.agent_view("Ada")
    record = game.backends["Ada"].prompt_builder.build(context)
    assert record.system == packet_system("bigville")
    assert "Proposing in this mode:" not in record.system
    assert "legal_affordances" not in json.dumps(record.context)


def test_ui_on_demand_affordances_still_work_and_step_does_not_ask_for_them():
    game = _game(_reply("rest"))
    calls, patch_affordances, patch_options = _spy_menu_calls()
    with patch_affordances, patch_options:
        game.step()
    assert calls == []

    # Ada is not the human player in an autonomous game; use a menu-mode game with an explicit player for the UI.
    ui_game = _game(_reply("rest"), mode="menu", player="Ada")
    client = EmbeddedClient(ui_game, "Ada")
    assert client.view()["mode"] == "agent"
    assert client.affordances()
    calls, patch_affordances, patch_options = _spy_menu_calls()
    with patch_affordances, patch_options:
        state = _service(ui_game).state()
    assert ("actor_affordances", "Ada") in calls
    assert state["player_context"]["affordances"]


def _service(game):
    """A GameService around an already-built game (the constructor would build its own)."""
    service = GameService.__new__(GameService)
    service.game = game
    service.player_name = game.player
    service.mode = "referee"
    return service


def test_an_ocelot_actor_stays_on_the_menu_path_in_a_lazy_game():
    game = _game(_reply("rest"))
    game.backends["Ada"] = mock.Mock(kind="ocelot", wants_agent_view=False)
    context = game._context("Ada")
    assert context.affordances, "Ocelot's replace_options path needs the menu"
    assert context.agent_view is None
