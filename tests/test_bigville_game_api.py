from __future__ import annotations

from bigville.backends import (ActorContinuation, ActorResponse, DeterministicBackend,
                               HumanBackend, OcelotBackend, ProposedAction)
from bigville.character import FrameSeed
from bigville.backends.conversation import ConversationMessage, TemplateConversationInterface
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


def _game():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    return world, BigvilleGame(world, player="Ada")


def test_human_backend_waits_then_advances_with_free_speech():
    world, game = _game()
    assert game.step()["status"] == "waiting"

    game.submit_player_response(ActorResponse(
        utterances=[{"target": "Ben", "content": "Hello there."}]))
    result = game.step()
    assert result["status"] == "advanced"
    assert result["turn"] == 1
    assert not world.actor_turn_state("Ada")["major_action_used"]
    contents = [world.eng.node(u)["attrs"]["content"]
                for u in world.conversation_between("Ada", "Ben")]
    assert "inform Hello there." in contents
    templated = next(world.eng.node(u)["attrs"] for u in world.conversation_between("Ada", "Ben")
                     if world.eng.node(u)["attrs"]["content"] == "inform Hello there.")
    assert templated["communication_mode"] == "templated"
    assert templated["conversation"]["act"] == "inform"


def test_ocelot_backend_exposes_read_only_held_state():
    world, game = _game()
    game.backends["Ben"] = OcelotBackend(world, game.characters["Ben"])
    held = game.dump_held_state("Ben")
    assert held["backend"] == "ocelot"
    assert held["character_id"] == "Ben"
    assert held["concepts"]
    assert "mind_graph" in held["backend_state"]
    assert "voice_graph" in held["backend_state"]


def test_template_interface_carries_arbitrary_world_slots():
    interface = TemplateConversationInterface({"land_claim": "claim {parcel} for {holder}"})
    message = ConversationMessage("land_claim", {"parcel": "north_field", "holder": "Ada"})
    assert interface.render(message) == "claim north_field for Ada"


def test_structured_purchase_is_rendered_for_templated_recipient():
    world, game = _game()
    game.submit_player_response(ActorResponse(utterances=[{
        "target": "Ben",
        "act": "purchase",
        "slots": {"quantity": 2, "item": "bread", "seller": "Ben"},
        "content": "Could I have two loaves?",
    }]))
    game.step()
    utterance = world.conversation_between("Ada", "Ben")[0]
    attrs = world.eng.node(utterance)["attrs"]
    assert attrs["content"] == "purchase 2 bread from Ben"
    assert attrs["communication_mode"] == "templated"


def test_cheap_backend_is_marked_as_requiring_conversational_interface():
    _, game = _game()
    assert game.characters["Ben"].backend["mode"] == "templated"
    assert game.characters["Ben"].backend["requires_conversational_interface"] is True
    assert game.dump_held_state("Ben")["backend_state"]["communication"]["mode"] == "templated"


def test_free_text_is_preserved_when_both_recipients_support_it():
    world, game = _game()
    game.backends["Ben"] = HumanBackend(game.characters["Ben"])
    game.submit_player_response(ActorResponse(
        utterances=[{"target": "Ben", "content": "Hello there."}]))
    game.backends["Ben"].submit(ActorResponse())
    game.step()
    contents = [world.eng.node(u)["attrs"]["content"]
                for u in world.conversation_between("Ada", "Ben")]
    assert "Hello there." in contents


def test_character_identity_personality_memory_and_frames_are_serializable(tmp_path):
    world, game = _game()
    character = game.characters["Ada"]
    character.identity["origin"] = "the north road"
    character.personality["patience"] = 0.8
    game.add_memory("Ada", {"content": "Ben was kind.", "kind": "episodic"})
    character.held_frames.append(FrameSeed("weather_expectation"))
    path = tmp_path / "characters.json"
    game.save_characters(path)
    assert "the north road" in path.read_text()
    assert "Ben was kind." in path.read_text()


def test_backend_continuation_walks_without_redeciding_until_arrival():
    world, game = _game()

    class WalkingBackend(DeterministicBackend):
        def __init__(self, character):
            super().__init__(character)
            self.calls = 0

        def decide(self, context):
            self.calls += 1
            return ActorResponse(
                major_action=ProposedAction("move", {"destination": (3, 1)}),
                continuation=ActorContinuation(destination=(3, 1)),
            )

    walker = WalkingBackend(game.characters["Ben"])
    game.set_backend("Ben", walker)
    game.submit_player_response(ActorResponse())
    assert game.step()["status"] == "advanced"
    game.submit_player_response(ActorResponse())
    assert game.step()["status"] == "advanced"
    assert walker.calls == 1
    assert world.actor_position("Ben") == (3, 1)

    # Arrival is a completion boundary, so the next turn asks cognition for
    # the next task instead of carrying the old route forever.
    game.submit_player_response(ActorResponse())
    assert game.step()["status"] == "advanced"
    assert walker.calls == 2


def test_continuations_can_be_disabled_for_reactive_backends():
    world, game = _game()

    class CountingBackend(DeterministicBackend):
        def __init__(self, character):
            super().__init__(character)
            self.calls = 0

        def decide(self, context):
            self.calls += 1
            return ActorResponse()

    backend = CountingBackend(game.characters["Ben"])
    game.set_backend("Ben", backend)
    game.continuations_enabled = False
    for _ in range(2):
        game.submit_player_response(ActorResponse())
        assert game.step()["status"] == "advanced"
    assert backend.calls == 2


def test_continuation_replans_when_a_need_crosses_its_threshold():
    world, game = _game()

    class NeedsBackend(DeterministicBackend):
        def __init__(self, character):
            super().__init__(character)
            self.calls = 0

        def decide(self, context):
            self.calls += 1
            return ActorResponse(
                major_action=ProposedAction("move", {"destination": (3, 1)}),
                continuation=ActorContinuation(destination=(3, 1)),
            )

    backend = NeedsBackend(game.characters["Ben"])
    game.set_backend("Ben", backend)
    game.submit_player_response(ActorResponse())
    game.step()
    world.eng.set_attr(world._actor("Ben"), "hunger", 2.0)
    game.submit_player_response(ActorResponse())
    game.step()
    assert backend.calls == 2
    assert game.last_responses["Ben"].backend_state["continuation_interrupted"] == "hunger_threshold"
