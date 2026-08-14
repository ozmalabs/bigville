from bigville.backends import ActorContext, DeterministicBackend, LLMBackend, PromptBuilder
from bigville.character import CharacterDefinition, FrameSeed, MemoryRecord


def test_prompt_contains_private_character_and_public_choices():
    character = CharacterDefinition(
        character_id="Ada", name="Ada", identity={"role": "farmer"},
        personality={"patience": 0.8},
        memories=[MemoryRecord("m1", "The north field is dry.")],
        held_frames=[FrameSeed("grain_goes_in_granary")],
    )
    record = PromptBuilder().build(ActorContext(
        character, 4, {"world_frames": {"laws": ["no theft"]}},
        [{"action": "move", "target": "target:north", "score": 4}],
        recipient_interfaces={"Ben": {"mode": "templated"}},
    ))
    payload = record.as_dict()
    assert payload["schema"] == "bigville/prompt/1"
    assert payload["context"]["private"]["identity"]["role"] == "farmer"
    assert payload["context"]["private"]["memories"][0]["content"] == "The north field is dry."
    assert payload["context"]["public"]["legal_affordances"][0]["action"] == "move"
    assert payload["context"]["public"]["recipient_interfaces"]["Ben"]["mode"] == "templated"


def test_llm_backend_accepts_provider_json_and_exposes_backend_state():
    class Provider:
        def complete(self, prompt):
            assert prompt["schema"] == "bigville/prompt/1"
            return '{"major_action":{"action":"rest","params":{}},"waiting":false}'

    character = CharacterDefinition(character_id="Ada", name="Ada")
    backend = LLMBackend(character, Provider())
    response = backend.decide(ActorContext(character, 0, {}, [{"action": "rest"}]))
    assert response.major_action.action == "rest"
    held = backend.dump_held_state().to_dict()
    assert held["backend"] == "llm"
    assert held["backend_state"]["prompt_schema"] == "bigville/prompt/1"
    assert held["backend_state"]["prompt_hash"]


def test_deterministic_backend_chooses_actions_but_does_not_fake_idle_rest():
    character = CharacterDefinition(character_id="Ada", name="Ada")
    backend = DeterministicBackend(character)
    context = ActorContext(
        character, 0, {"energy": 100},
        [{"action": "move", "target": "target:north", "score": 10},
         {"action": "rest", "score": 0}],
    )
    response = backend.decide(context)
    assert response.major_action.action == "move"

    idle = ActorContext(character, 1, {"energy": 100}, [{"action": "rest", "score": 0}])
    assert backend.decide(idle).major_action is None
