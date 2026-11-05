from __future__ import annotations

from bigville.backends import (ActorContinuation, ActorResponse, DeterministicBackend,
                               HumanBackend, LLMBackend, OcelotBackend, ProposedAction)
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
    assert "Hello there." in contents
    templated = next(world.eng.node(u)["attrs"] for u in world.conversation_between("Ada", "Ben")
                     if world.eng.node(u)["attrs"]["content"] == "Hello there.")
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
    assert attrs["content"] == "Could I buy 2 bread from Ben?"
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


def test_backend_owned_speech_keeps_text_and_opaque_raw_data_for_recipient():
    world, game = _game()
    raw = {"topic": "weather", "observation": "clear", "confidence": 0.9}
    game._apply_response("Ada", ActorResponse(utterances=[{
        "target": "Ben",
        "text": "The sky is clear today.",
        "raw": raw,
    }]))

    utterance = world.conversation_between("Ada", "Ben")[0]
    attrs = world.eng.node(utterance)["attrs"]
    assert attrs["content"] == "The sky is clear today."
    assert attrs["raw_data"] == raw
    assert attrs["speech_origin"] == "backend"
    assert attrs["communication_mode"] == "free_text"
    assert "conversation" not in attrs
    assert attrs["raw_understanding"]["status"] == "not_understood"
    assert "cannot interpret" in attrs["raw_understanding"]["note"]

    heard = game._context("Ben").observations["heard_utterances"]
    assert heard[-1]["text"] == "The sky is clear today."
    assert heard[-1]["raw_data"] == raw
    assert heard[-1]["raw_understanding"]["status"] == "not_understood"


def test_llm_backend_speech_is_not_rewritten_for_a_legacy_npc_recipient():
    world, game = _game()

    class Provider:
        def complete(self, _prompt):
            return {"utterances": [{
                "target": "Ada",
                "text": "The north field will need water by noon.",
                "raw": {"topic": "farm", "field": "north", "need": "water"},
            }]}

    game.set_backend("Ben", LLMBackend(game.characters["Ben"], Provider()))
    game.submit_player_response(ActorResponse())
    assert game.step()["status"] == "advanced"
    utterance = world.conversation_between("Ada", "Ben")[0]
    attrs = world.eng.node(utterance)["attrs"]
    assert attrs["content"] == "The north field will need water by noon."
    assert attrs["raw_data"] == {"topic": "farm", "field": "north", "need": "water"}
    assert attrs["communication_mode"] == "free_text"
    assert attrs["raw_understanding"]["status"] == "understood"


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


def test_nearby_residents_expose_floor_relationship_signal_when_no_bond_set():
    world, game = _game()
    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    assert nearby["Ben"]["tie_strength"] == 0.0
    assert nearby["Ben"]["band_code"] == 0.0


def test_nearby_residents_expose_held_tie_strength_and_band_code():
    world, game = _game()
    world.set_relationship("Ada", "Ben", kind="friend", strength=2.5)
    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    assert nearby["Ben"]["tie_strength"] == 2.5
    assert nearby["Ben"]["band_code"] == 3.0


def test_nearby_residents_band_code_matches_bondworld_banding_directly():
    from worlds.bigville_bond_world import BigvilleBondWorld

    world, game = _game()
    world.set_relationship("Ada", "Ben", kind="friend", strength=5.5)
    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    expected = BigvilleBondWorld._band_code(
        {"tie_strength": 5.5, "affect_resentment": 0.0})
    assert nearby["Ben"]["band_code"] == expected == 5.0


def test_nearby_residents_signal_carries_no_rendered_text():
    world, game = _game()
    world.set_relationship("Ada", "Ben", kind="friend", strength=2.5)
    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    assert set(nearby["Ben"]) == {
        "id", "name", "role", "klass", "group", "position", "distance",
        "shared_bucket_count", "tie_strength", "band_code",
    }


def test_shared_bucket_count_counts_matching_role_klass_group():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="labourer", klass="poor", group="low", home_cell=(1, 1))
    world.add_actor("Ben", role="labourer", klass="poor", group="high", home_cell=(1, 1))
    world.add_actor("Cara", role="mayor", klass="rich", group="high", home_cell=(1, 1))
    game = BigvilleGame(world, player="Ada")

    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    assert nearby["Ben"]["shared_bucket_count"] == 2  # role + klass, not group
    assert nearby["Cara"]["shared_bucket_count"] == 0  # shares nothing


def test_shared_bucket_count_zero_when_a_bucket_is_unset():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="labourer", home_cell=(1, 1))
    world.add_actor("Ben", role="labourer", home_cell=(1, 1))
    game = BigvilleGame(world, player="Ada")

    ctx = game._context("Ada")
    nearby = {r["id"]: r for r in ctx.observations["nearby_residents"]}
    # both share role="labourer"; klass/group both empty-string on both sides,
    # which must NOT count as a "shared" bucket (empty is absence, not a match).
    assert nearby["Ben"]["shared_bucket_count"] == 1


def test_populate_town100_seeds_scenario_character_data_per_resident():
    """AFFECT_COUPLING Phase 5 (TOWN100_DISPOSITION_SWITCHON_PREREG.md,
    ocelot repo): populate_town100 must populate _scenario_character_data
    BEFORE add_actor for every cast-100 resident, so an Ocelot cognition_
    factory's seed_character actually receives real identity/personality
    -- previously only from_scenario() ever did this, so a cast-100
    resident's own drawn _PARAM_SPEC params never reached it at all."""
    world = BigvilleWorld(autonomous_actors=False)
    world.populate_town100(seed=305000)

    assert len(world._scenario_character_data) == 100
    name = next(iter(world._cast100["residents"]))["name"]
    preset = world._scenario_character_data[name]
    assert preset["identity"]["role"]
    assert preset["identity"]["klass"]
    assert preset["identity"]["group"]
    for key in ("hostile_weight", "charm_weight", "mood_bias", "arousal",
                "prior_others_trust", "cred_on", "valence", "resolution_bins"):
        assert key in preset["personality"], key
    assert preset["personality"]["emotional_core_enabled"] == 1.0
