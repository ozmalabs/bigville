"""Package 11: simple-backend speech is situated input, not a world action."""
from bigville.backends import ActorResponse, DeterministicBackend
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


class _Speaker(DeterministicBackend):
    kind = "simple"

    def __init__(self, character):
        super().__init__(character)
        self.sent = 0

    def decide(self, context):
        if self.sent < 2:
            self.sent += 1
            return ActorResponse(utterances=[{
                "target": "Ben", "text": "Could you bring one apple?",
                "raw": {"act": "request", "slots": {"item": "apple", "quantity": 1}},
            }])
        return ActorResponse()


class _Listener(DeterministicBackend):
    kind = "simple"

    def __init__(self, character):
        super().__init__(character)
        self.seen = []
        self.responses = 0

    def decide(self, context):
        heard = context.observations["heard_utterances"]
        self.seen.append(list(heard))
        if any(item["speaker"] == "Ada" and "apple" in item["text"] for item in heard):
            self.responses += 1
            return ActorResponse(utterances=[{
                "target": "Ada", "act": "inform",
                "slots": {"meaning": "I heard you"},
                "content": "I heard you.",
            }])
        return ActorResponse()


def _game():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(2, 1))
    world.add_actor("Cy", role="hand", home_cell=(1, 2))
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    speaker = _Speaker(game.characters["Ada"])
    listener = _Listener(game.characters["Ben"])
    observer = _Listener(game.characters["Cy"])
    game.set_backend("Ada", speaker)
    game.set_backend("Ben", listener)
    game.set_backend("Cy", observer)
    return world, game, speaker, listener, observer


def test_simple_speech_is_range_gated_then_recipient_policy_responds():
    world, game, _speaker, listener, observer = _game()
    starting_inventories = {name: world.inventory(name) for name in ("Ada", "Ben", "Cy")}

    # Normal speech carries one cell (HEARING table, loudness 1.0). Ben starts two cells from Ada, so the
    # utterance is not heard. Cy, adjacent to Ada, is not the target and hears nothing.
    world.move_actor("Ben", (3, 1))
    game.step()
    assert world.heard_utterances("Ben") == []
    assert listener.responses == 0
    assert world.heard_utterances("Cy") == []

    # Moving the recipient into range enables delivery on the next utterance.
    world.move_actor("Ben", world.actor_position("Ada"))
    game.step()
    delivered = world.heard_utterances("Ben")
    assert delivered and delivered[-1]["speaker"] == "Ada"
    assert "Could you bring one apple?" in delivered[-1]["text"]
    assert listener.responses == 0  # same-turn speech is not retroactive input

    # The listener sees the record at its next decision and chooses to reply.
    game.step()
    assert listener.responses == 1
    assert any(item["speaker"] == "Ada" for item in listener.seen[-1])
    assert not any(item["speaker"] == "Ada" for item in observer.seen[-1])
    assert any(item["speaker"] == "Ben" for item in world.heard_utterances("Ada"))

    # Speech alone transfers no goods and compels no major action.
    assert {name: world.inventory(name) for name in starting_inventories} == starting_inventories
    assert not world.actor_turn_state("Ben")["major_action_used"]


def test_private_or_unobserved_state_is_not_published_in_actor_context():
    world, game, *_ = _game()
    world.eng.node(world._actors["Ada"])["attrs"]["private_secret"] = "unobserved"
    context = game._context("Ben")
    assert "private_secret" not in context.observations
    assert context.observations["heard_utterances"] == []
