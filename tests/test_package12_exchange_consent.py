"""Package 12 scenario: exchange and consent boundaries."""
import pytest

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


class _TransferBackend(DeterministicBackend):
    kind = "simple"

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "transfer", {"source": "Ben", "recipient": "Ada",
                         "kind": "apple", "amount": 1},
            "Ben chose to accept Ada's offer"))


class _TakeBackend(DeterministicBackend):
    kind = "simple"

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "move_object", {"object_id": "apple-token", "destination": "Ben"},
            "Ben chose to move an unattended accessible object"))


class _OfferBackend(DeterministicBackend):
    kind = "simple"

    def __init__(self, character):
        super().__init__(character)
        self.sent = False

    def decide(self, context):
        if self.sent:
            return ActorResponse()
        self.sent = True
        return ActorResponse(utterances=[{
            "target": "Ben", "text": "Would you trade one apple for one coin?",
            "raw": {"act": "offer", "kind": "apple", "amount": 1, "price": 1},
        }])


class _SellerDecisionBackend(DeterministicBackend):
    kind = "simple"

    def __init__(self, character, accepted):
        super().__init__(character)
        self.accepted = accepted
        self.decisions = []

    def decide(self, context):
        offer = next((item for item in context.observations["heard_utterances"]
                      if item["speaker"] == "Ada" and "trade one apple" in item["text"]), None)
        if offer is None:
            return ActorResponse()
        answer = "I accept." if self.accepted else "I refuse."
        self.decisions.append((offer, answer))
        transfer = (ProposedAction("transfer", {
            "source": "Ben", "recipient": "Ada", "kind": "apple", "amount": 1,
        }, "Ben accepted the observed offer") if self.accepted else None)
        return ActorResponse(major_action=transfer,
                             utterances=[{"target": "Ada", "text": answer}])


def _exchange_world(*, willing=True, seller_at=(1, 1), buyer_at=(1, 1)):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=buyer_at)
    world.add_actor("Ben", role="hand", home_cell=seller_at)
    world.set_stock("apple", 1)
    world.stock_person("Ben", "apple", 1, price=1, willing=willing)
    world.set_coin("Ada", 2)
    return world


def test_backend_acceptance_hands_over_goods_without_price_or_world_agreement():
    world = _exchange_world(willing=False)
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    game.set_backend("Ben", _TransferBackend(game.characters["Ben"]))

    before = world.inventory("Ben").get("apple", 0)
    result = game.step()

    assert result["results"]["Ben"] is True
    assert world.inventory("Ada").get("apple", 0) == 1
    assert world.inventory("Ben").get("apple", 0) == before - 1
    assert world.coin("Ada") == 2


def test_offer_is_observed_and_acceptance_or_refusal_is_a_backend_choice():
    answers = []
    for accepted in (True, False):
        world = _exchange_world(willing=False)
        game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
        seller = _SellerDecisionBackend(game.characters["Ben"], accepted)
        game.set_backend("Ada", _OfferBackend(game.characters["Ada"]))
        game.set_backend("Ben", seller)

        game.step()  # Ada proposes; speech does not change inventories.
        game.step()  # Ben sees the offer and chooses a response.

        assert seller.decisions
        assert seller.decisions[-1][1] == ("I accept." if accepted else "I refuse.")
        if accepted:
            assert world.inventory("Ada").get("apple") == 1
            assert world.inventory("Ben").get("apple", 0) == 0
            assert world.coin("Ada") == 2  # price/payment is not a world gate
        else:
            assert world.inventory("Ada").get("apple", 0) == 0
            assert world.inventory("Ben").get("apple") == 1
        answers.append(seller.decisions[-1][1])
    assert answers == ["I accept.", "I refuse."]


def test_backend_can_move_an_accessible_unattended_object_to_itself():
    world = BigvilleWorld(scenario={
        "id": "accessible_unattended_object",
        "actors": [
            {"name": "Ada", "role": "hand", "home_cell": [1, 1]},
            {"name": "Ben", "role": "hand", "home_cell": [1, 1]},
        ],
        "physical_objects": [{"id": "apple-token", "kind": "token", "location": "world"}],
    }, autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    game.set_backend("Ben", _TakeBackend(game.characters["Ben"]))

    result = game.step()

    assert result["results"]["Ben"] is True
    assert world.physical_objects()[0]["location"] == "Ben"
    assert world.eng.has_edge(world._actors["Ben"], "holds_object",
                              world._physical_objects["apple-token"])


def test_accessible_unattended_tool_can_be_physically_picked_up():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ben", role="hand", home_cell=(1, 1))
    item = world.eng.add_node("ToolItem", {
        "kind": "pick", "weight": 2.0, "quality": 1.0,
        "condition": 1.0, "broken": 0.0,
    })
    world.eng.add_edge_unchecked(world._town, "has_tool_item", item)
    world._attach_at_cell(item, (1, 1))
    world.tick()
    world.actor_tick()

    assert world.major_action("Ben", "pick_up", item=item)
    assert world._item_owner_edge("Ben", item) is not None


def test_physical_give_checks_reach_and_possession_without_price_or_consent():
    world = _exchange_world()
    # Possession and co-location permit the physical transfer even though no
    # offer, acceptance, price, or payment exists.
    world.tick()
    world.actor_tick()
    assert world.major_action("Ben", "give", recipient="Ada", kind="apple", amount=1)
    assert world.inventory("Ada").get("apple") == 1
    assert world.coin("Ada") == 2

    world2 = _exchange_world(seller_at=(2, 1))
    world2.tick()
    world2.actor_tick()
    assert not world2.major_action("Ben", "give", recipient="Ada", kind="apple", amount=1)
    assert world2.inventory("Ben").get("apple") == 1

    world3 = BigvilleWorld(autonomous_actors=False)
    world3.add_actor("Ada", role="hand", home_cell=(1, 1))
    world3.add_actor("Ben", role="hand", home_cell=(1, 1))
    world3.set_stock("apple", 1)
    world3.tick()
    world3.actor_tick()
    assert not world3.major_action("Ben", "give", recipient="Ada", kind="apple", amount=1)
    assert world3.inventory("Ada").get("apple", 0) == 0


def test_legacy_paid_give_is_only_a_physical_transfer():
    for willing in (True, False):
        world = _exchange_world(willing=willing)
        seller_coin = world.coin("Ben")
        world.eng.set_attr(world._actors["Ben"], "sell_price", 1_000_000.0)
        # Legacy commerce metadata and payment kwargs cannot create a world
        # agreement. The explicit give moves only the named held good.
        assert world.give("Ben", "Ada", "apple", 1,
                          payment_kind="coin", payment_amount=1)
        assert world.inventory("Ada").get("apple") == 1
        assert world.inventory("Ben").get("apple", 0) == 0
        assert world.coin("Ada") == 2
        assert world.coin("Ben") == seller_coin

