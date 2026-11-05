from collections import Counter

from bigville import create_board_game, create_world


def test_monopoly_room_has_neutral_objects_not_world_game_state():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    assert not hasattr(world, "_board_game")
    assert not list(world.eng.nodes("Property"))
    assert not list(world.eng.nodes("MonopolyGame"))
    assert all("monopoly" not in str(world.eng.node(node)["attrs"]).lower()
               for node in world.eng.nodes("MapCell"))

    objects = world.physical_objects()
    counts = Counter(item["kind"] for item in objects)
    assert counts["property card"] == 28
    assert counts["banknote"] == 212
    assert counts["chance card"] == 16
    assert counts["community chest card"] == 16
    assert counts["playing token"] == 8
    assert all(item["location"] == "game_box"
               for item in objects if item["kind"] != "box")
    assert not list(world.eng.nodes("GameBox"))


def test_room_starts_boxed_and_does_not_synthesize_setup():
    experiment = create_board_game(scenario="monopoly_four_players", seed=1)
    assert experiment.summary() == {
        "rules": None,
        "ticks": 0,
        "setup_ready": False,
        "banker": None,
        "tokens": {},
        "finished": False,
        "winner": None,
        "termination": "room_observation_only",
        "participants": ["Alice", "Bob", "Cara", "Dan"],
        "events": 0,
        "utterances": 0,
    }
    assert experiment.state["event_log"] == []
    assert all(item["location"] == "game_box"
               for item in experiment.physical_world.physical_objects()
               if item["kind"] != "box")

    experiment.run(ticks=0)
    assert experiment.state["event_log"] == []
    assert experiment.state["setup"]["banker"] is None
    assert experiment.state["setup"]["tokens"] == {}


def test_actor_ticks_can_move_objects_without_creating_game_meaning():
    experiment = create_board_game(scenario="monopoly_four_players", seed=1,
                                   backend="ocelot")
    result = experiment.run(ticks=8)
    kinds = {event["kind"] for event in result["event_log"]}
    assert "actor_tick" in kinds
    assert "backend_decision" in kinds
    assert not kinds & {"setup_complete", "choose_banker", "banker_vote",
                        "choose_token", "buy_property", "trade_property",
                        "roll", "rent", "bankruptcy"}
    assert result["setup"]["banker"] is None
    assert result["setup"]["tokens"] == {}
    assert result["winner"] is None
    assert result["finished"] is False

    actions = {event.get("action") for event in result["event_log"]
               if event["kind"] == "backend_decision"}
    assert actions <= {"move_object", "open_object", "read_object", "observe_room", ""}


def test_world_object_affordances_are_generic_and_can_move_any_object():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    options = world.physical_object_affordances("Alice")
    assert options
    assert {option["action"] for option in options} <= {"move_object", "open_object"}
    assert not {option["action"] for option in options} & {
        "purchase", "buy_property", "trade", "trade_property", "turn",
    }

    box = next(item for item in world.physical_objects() if item["kind"] == "box")
    assert world.move_physical_object_as_actor("Alice", box["id"], "Bob")
    moved = next(item for item in world.physical_objects() if item["id"] == box["id"])
    assert moved["location"] == "Bob"


def test_contents_become_observable_only_when_container_is_accessible():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    assert not any(item["kind"] == "rulebook"
                   for item in world.physical_object_observations("Alice"))
    assert world.move_physical_object_as_actor("Alice", "game_box", "Alice")
    assert world.open_physical_object_as_actor("Alice", "game_box")
    visible = world.physical_object_observations("Alice")
    assert any(item["kind"] == "rulebook" for item in visible)
    assert any(option["object_id"] == "rulebook"
               for option in world.physical_object_affordances("Alice"))


def test_monopoly_rulebook_contains_the_complete_physical_rule_set():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    rulebook = next(item for item in world.physical_objects()
                    if item["id"] == "rulebook")
    text = rulebook["text"]
    required_sections = (
        "Contents", "Preparing the table", "The board spaces", "A turn",
        "Buying and auctioning property", "Colour groups and rent",
        "Railroads and utilities", "Building houses and hotels",
        "Chance card instructions", "Community Chest card instructions",
        "Jail", "Mortgages and trades", "Debts and bankruptcy",
        "Ending the game",
    )
    assert all(section in text for section in required_sections)
    assert len(text) >= 12000
    assert text.count("price ") >= 22
    assert text.count("rent") >= 20
    assert "Get Out of Jail Free" in text
    assert "three times in succession" in text


def test_standalone_ocelot_label_does_not_fake_document_understanding():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    assert world.move_physical_object_as_actor("Alice", "game_box", "Alice")
    assert world.open_physical_object_as_actor("Alice", "game_box")
    rulebook = next(item for item in world.physical_object_observations("Alice")
                    if item["kind"] == "rulebook")
    mind = world.actor_mind("Alice")

    first = mind.ingest_document(rulebook["text"], name=rulebook["name"])
    second = mind.ingest_document(rulebook["text"], name=rulebook["name"])

    assert first["status"] == "not_understood"
    assert second == first
    assert not list(mind.s.nodes("Understanding"))
    assert len(list(mind.s.nodes("ComprehensionResidual"))) == 1


def test_ocelot_ticks_are_decisions_not_a_hidden_game_driver():
    experiment = create_board_game(scenario="monopoly_four_players", seed=1,
                                   backend="ocelot")
    assert {backend.kind for backend in experiment.backends.values()} == {"ocelot"}
    result = experiment.run(ticks=12)
    assert result["turn"] == 12
    assert result["finished"] is False
    assert result["utterances"]
    assert all(utterance["text"] for utterance in result["utterances"])
    assert all(utterance["target"] in {"Alice", "Bob", "Cara", "Dan"}
               for utterance in result["utterances"])
    for backend in experiment.backends.values():
        held = backend.dump_held_state().to_dict()
        assert held["backend"] == "ocelot"
    assert not list(experiment.physical_world.eng.nodes("Property"))
    assert not list(experiment.physical_world.eng.nodes("MonopolyGame"))
