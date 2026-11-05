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


def test_plain_world_tick_advances_time_without_running_resident_policy():
    world = BigvilleWorld.from_town100()
    assert world._autonomous_actors is False
    calls = []
    world._ocelot_actor_tick = lambda: calls.append("cognition")

    world.tick()

    assert world._turn == 1
    assert calls == []


def test_title_interpretations_live_in_private_character_memory_not_world_records():
    world, game = _game()
    world.add_land("north_field", use="arable", soil="loam", area=2.0)
    world.register_land("Ada", "north_field", "Ada")
    first = world.write_deed("Ada", "sale", "north_field", from_holder="Ada", to_holder="Ben")
    game.add_memory("Ada", {"kind": "title_interpretation", "content": {
        "parcel": "north_field", "holder": "Ada"}, "private": True})
    game.add_memory("Ben", {"kind": "title_interpretation", "content": {
        "parcel": "north_field", "holder": "Ben"}, "private": True})
    second = world.write_deed("Ben", "sale", "north_field", from_holder="Ada", to_holder="Ben")
    first_attrs = dict(world.eng.node(first)["attrs"])
    second_attrs = dict(world.eng.node(second)["attrs"])
    first_attrs.pop("record_id")
    second_attrs.pop("record_id")
    assert first_attrs == second_attrs
    assert world.land_owner("north_field") == "Ada"
    assert not world.eng.neighbours(world._actors["Ada"], "knows_land_title")
    assert not world.eng.neighbours(world._actors["Ben"], "knows_land_title")
    assert game.dump_held_state("Ada")["memories"][-1]["content"]["holder"] == "Ada"
    assert game.dump_held_state("Ben")["memories"][-1]["content"]["holder"] == "Ben"


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


def test_recipe_priors_live_in_private_character_memory_not_world_action_gate():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_tradesperson("Miller", "miller")
    world.add_tradesperson("Inky", "inkmaker")
    world.set_stock("soot", 5)
    world.set_stock("oil", 5)
    game = BigvilleGame(world, player="Miller")

    miller_recipes = {
        memory.content["recipe"] for memory in game.characters["Miller"].memories
        if memory.kind == "recipe_knowledge"
    }
    inky_recipes = {
        memory.content["recipe"] for memory in game.characters["Inky"].memories
        if memory.kind == "recipe_knowledge"
    }
    assert "grind_flour" in miller_recipes
    assert "make_ink" not in inky_recipes
    assert not world.eng.neighbours(world._actors["Miller"], "knows")
    assert not world.eng.neighbours(world._actors["Inky"], "knows")

    physical_options = world.actor_affordances("Inky")
    assert any(option.get("action") == "work" and option.get("recipe") == "make_ink"
               for option in physical_options)
    response = game.backends["Inky"].decide(game._context("Inky"))
    assert response.major_action is None or response.major_action.action != "work", \
        "the simple backend has no private prior for an unlearned recipe"


def test_explicit_recipe_priors_distinguish_physically_identical_actors():
    world = BigvilleWorld(autonomous_actors=False)
    for name, priors in (("Learner", ["grind_flour"]), ("Novice", [])):
        world._scenario_character_data[name] = {"recipe_priors": priors}
        world.add_actor(name, role="miller", home_cell=(1, 1))
    game = BigvilleGame(world, player="Learner")

    def recipes(name):
        return {memory.content["recipe"] for memory in game.characters[name].memories
                if memory.kind == "recipe_knowledge"}

    assert recipes("Learner") == {"grind_flour"}
    assert recipes("Novice") == set()
    assert world.actor_affordances("Learner") == world.actor_affordances("Novice")
    assert not world.eng.neighbours(world._actors["Learner"], "knows")
    assert not world.eng.neighbours(world._actors["Novice"], "knows")


def test_ocelot_backend_rejects_local_fallback(monkeypatch):
    import pytest
    import bigville.backends.ocelot as adapter
    class RealResident: pass
    monkeypatch.setattr(adapter, "ocelot_resident_class", lambda: RealResident)
    world, game = _game()
    with pytest.raises(adapter.OcelotUnavailableError, match="real"):
        OcelotBackend(world, game.characters["Ben"])


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


def test_unread_laws_and_policies_are_not_implicit_actor_knowledge():
    world, game = _game()
    # A locally accessible physical record/object remains ordinary evidence
    # in the situated observation channel.
    visible = world.eng.add_node("PhysicalObject", {
        "object_id": "notice", "name": "notice", "kind": "written_record",
        "location": "table", "text": "Meeting at noon",
    })
    world._physical_objects["notice"] = visible
    world._physical_object_locations["notice"] = "table"
    context = game._context("Ada").observations
    assert any(item["id"] == "notice" and item["text"] == "Meeting at noon"
               for item in context["physical_objects"])
    frames = context["world_frames"]
    assert frames["laws"] == []
    assert frames["policies"] == []
    assert frames["documents"] == []

    # Reading is physical exposure. Only an explicit backend comprehension
    # update adds semantic knowledge, and that update stays resident-private.
    law = world._documents[("law", "public_order_law")]
    assert world.read_document("Ada", law) == "public_order_law"
    frames = game._context("Ada").observations["world_frames"]
    assert frames["laws"] == []
    assert frames["documents"] == [{"kind": "law", "name": "public_order_law",
                                     "title": "Public Order and Protection Law",
                                     "scope": "village", "version": 1.0}]
    assert game._context("Ben").observations["world_frames"]["laws"] == []
    assert game._apply_response("Ada", ActorResponse(memory_updates=[{
        "kind": "law_knowledge", "content": {
            "name": "public_order_law", "interpretation": "The resident's own reading."},
        "private": True,
    }]))
    assert [item["name"] for item in game._context("Ada").observations["world_frames"]["laws"]] == ["public_order_law"]
    assert game._context("Ben").observations["world_frames"]["laws"] == []
    assert not world.knows_law("Ada", "public_order_law"), "backend interpretation is not world graph knowledge"
    assert game.dump_held_state("Ada")["memories"][-1]["private"] is True


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


def test_private_bond_affects_do_not_leak_into_resident_context():
    world, game = _game()
    world.set_relationship("Ada", "Ben", kind="feud", strength=-3.0)
    nearby = {r["id"]: r for r in game._context("Ada").observations["nearby_residents"]}
    assert nearby["Ben"]["tie_strength"] == 0.0
    assert nearby["Ben"]["band_code"] == -1.0
    assert not {"affect_affection", "affect_resentment", "kind", "strength"} & set(nearby["Ben"])


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

    # Town100's backend trade catalog explicitly seeds private craft priors;
    # population roles never create public recipe-knowledge edges.
    game = BigvilleGame(world, autonomous=True)
    baker = next(record["name"] for record in world._cast100["residents"]
                 if record["role"] == "baker")
    baker_priors = {memory.content.get("recipe") for memory in game.characters[baker].memories
                    if memory.kind == "recipe_knowledge"}
    assert "bake_bread" in baker_priors
    assert not world.eng.neighbours(world._actors[baker], "knows")


def test_lesson_offer_is_a_backend_choice_and_world_does_not_infer_learning():
    """Game.step delivers only in-range lessons; learner backends choose retention."""
    def run(accept):
        world = BigvilleWorld(autonomous_actors=False)
        world.add_actor("Ada", role="teacher", home_cell=(1, 1), literacy=1.0)
        world.add_actor("Ben", role="hand", home_cell=(1, 1), literacy=0.2)
        world.add_actor("Cy", role="hand", home_cell=(5, 5), literacy=0.2)
        game = BigvilleGame(world, player="Ada")
        literacy_before = world.literacy("Ben")
        references_before = world.known_references("Ben")
        game.submit_player_response(ActorResponse(utterances=[{
            "target": "Ben",
            "text": "A seed needs water and warmth to sprout.",
            "raw": {"act": "lesson", "topic": "germination"},
        }]))
        game.backends["Ben"] = HumanBackend(game.characters["Ben"], chooser=lambda _ctx: ActorResponse())
        game.backends["Cy"] = HumanBackend(game.characters["Cy"], chooser=lambda _ctx: ActorResponse())
        game.step()
        context = game._context("Ben")
        heard = context.observations["heard_utterances"][-1]
        assert heard["text"] == "A seed needs water and warmth to sprout."
        assert game._context("Cy").observations["heard_utterances"] == []

        backend = HumanBackend(game.characters["Ben"], chooser=lambda _ctx: ActorResponse(
            memory_updates=([{"kind": "learned_lesson", "content": "germination"}]
                            if accept else [])))
        game.set_backend("Ben", backend)
        game.submit_player_response(ActorResponse())
        game.step()
        return game, world, context, literacy_before, references_before

    accepted, accepted_world, accepted_context, accepted_literacy, accepted_references = run(True)
    refused, refused_world, refused_context, refused_literacy, refused_references = run(False)
    assert accepted_context.observations["position"] == refused_context.observations["position"]
    assert accepted_context.observations["heard_utterances"] == refused_context.observations["heard_utterances"]
    assert accepted_literacy == refused_literacy == 0.2
    assert accepted_world.literacy("Ben") == accepted_literacy
    assert refused_world.literacy("Ben") == refused_literacy
    assert accepted_world.known_references("Ben") == accepted_references
    assert refused_world.known_references("Ben") == refused_references
    assert accepted.dump_held_state("Ben")["memories"][-1]["content"] == "germination"
    assert refused.dump_held_state("Ben")["memories"] == []


def test_reference_priors_are_explicit_private_character_memory():
    world = BigvilleWorld.from_scenario({"actors": [
        {"name": "Ada", "role": "farmer",
         "reference_priors": ["grain_in_granary"]},
        {"name": "Ben", "role": "farmer"},
    ]})
    game = BigvilleGame(world, player="Ada")

    # Same role gives no shared assumptions. Only authored setup changes Ada's
    # backend-held state; the world has no resident belief edge for either.
    assert world.known_references("Ada") == world.known_references("Ben") == set()
    assert list(world.eng.neighbours(world._town, "has_reference")) == []
    assert game._context("Ada").observations["known_references"] == ["grain_in_granary"]
    assert game._context("Ben").observations["known_references"] == []
    assert game.dump_held_state("Ada")["memories"][-1]["kind"] == "reference_knowledge"

    world.add_actor("Clerk", role="clerk")
    assert game._context("Ben").observations["known_references"] == []
