"""Regression coverage for features ported out of the substrate repository."""

from bigville.backends import ActorContext, CheapBackend
from bigville.backends.conversation import ConversationMessage, TemplateConversationInterface
from bigville.character import CharacterDefinition
from bigville.runtime import WorldAdapter
from worlds.bigville_speech_world import BigvilleSpeechWorld, SPEECH_MENU
from worlds.bigville_world import BigvilleWorld


def test_cheap_backend_records_psi_and_can_weighted_choice():
    character = CharacterDefinition(
        "Ada", "Ada", identity={"role": "farmer"},
        personality={"role_identity": 0.9, "prior_world_safe": 0.8},
    )
    backend = CheapBackend(character)
    response = backend.decide(ActorContext(
        character=character, turn=4,
        observations={"hunger": 3.0, "energy": 0.8, "health": "healthy"},
        affordances=[
            {"action": "eat", "kind": "bread", "score": 10.0},
            {"action": "work", "recipe": "make_bread", "score": 10.0},
        ],
    ))
    assert response.major_action.reason == "cheap_psi_can"
    assert backend.last_choice["decision_model"] == "psi_can_weighted"
    assert backend.last_choice["psi"]["hunger"] == 0.75
    assert "survival" in backend.last_choice["can"]


def test_seeded_animals_have_species_npcs_and_paddock_fences():
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    assert "village_paddock" in world.enclosures()
    assert len(world._fences) == 16
    assert len(world._animal_minds) == len(world._animals) == 7
    sanity = world.sanity_report()
    assert sanity["animals_in_enclosures"] == 7
    assert sanity["intact_enclosures"] == 1
    choices = world.animal_tick()
    assert choices["dog_6"]["decision_model"] == "psi_can_weighted"
    assert choices["dog_6"]["can"]["duty"] > 0.0
    assert world.animal_enclosure("dog_6") == "village_paddock"


def test_fence_contains_animals_until_broken():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_animal("Daisy", "cow", cell=(10, 10))
    world.add_enclosure("yard", [(10, 10), (10, 11), (11, 10), (11, 11)])
    world.eng.add_edge_unchecked(world._animals["Daisy"], "kept_in", world._enclosures["yard"])
    outside = next(cell for cell in world._map_cells if cell not in world.enclosure_cells("yard"))
    assert world._move_animal_to("Daisy", outside) == (10, 10)
    fence = next(name for name in world._fences if name.startswith("yard:fence:"))
    world.break_fence(fence)
    assert world._move_animal_to("Daisy", outside) == outside
    assert not world.enclosure_intact("yard")


def test_death_event_is_not_magically_known_by_other_residents():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    world.eng.set_attr(world._actors["Ada"], "alive", 0.0)
    world.eng.set_attr(world._actors["Ada"], "hunger", 4.0)
    world._run()
    assert len(world._deaths) == 1
    event = next(iter(world._events.values()))
    assert world.event_data(event)["kind"] == "death"
    assert world.event_data(event)["public"] == 0.0
    assert list(world.eng.neighbours(world._actors["Ben"], "observed_event")) == []
    world.observe_event("Ben", event)
    assert list(world.eng.neighbours(world._actors["Ben"], "observed_event")) == [event]


def test_speech_menu_and_templated_fallback_cover_new_acts():
    names = {option["name"] for option in SPEECH_MENU}
    assert {"request", "offer", "question", "thanks", "apology",
            "farewell", "complaint", "promise"} <= names
    world = BigvilleSpeechWorld()
    world.add_agent("Ada")
    world.add_agent("Ben")
    world.hold_bond("Ada", "Ben")
    world.encounter("Ada", "Ben", goal_pressure=1.0)
    assert world.decide("Ada", "Ben") == "request"
    assert TemplateConversationInterface().render(
        ConversationMessage("offer", {"item": "bread", "recipient": "Ben"})) == "offer bread to Ben"
    assert TemplateConversationInterface().render(
        ConversationMessage("apology", {"target": "Ben", "reason": "the delay"})) == "apologize to Ben for the delay"


def test_standalone_goal_renderer_produces_surface_speech_not_graph_keys():
    voice = WorldAdapter()
    assert voice.utterance_for({"weather": {"of": "rain"}}) == "It is raining today."
    content = voice.utterance_for({"news": {"of": {
        "kind": "injury", "subject": "Garnet", "detail": "Garnet was injured (a fall)."
    }}})
    assert content == "I heard that Garnet was injured (a fall)."
    assert "news of" not in content
