"""Package 13: same physical access under contrasting held norm policies."""
from bigville.api import create_game
from bigville.backends import ActorResponse, DeterministicBackend, ProposedAction
from bigville.scenarios import load_scenario
from worlds.bigville_world import BigvilleWorld


class _FetchPolicy(DeterministicBackend):
    """A scripted resident choice; the world still validates the physical fetch."""
    kind = "simple"

    def __init__(self, character, fetch):
        super().__init__(character)
        self.fetch = fetch
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        option = next((item for item in context.affordances
                       if item.get("action") == "fetch" and item.get("kind") == "bread"), None)
        if not self.fetch or option is None:
            return ActorResponse()
        return ActorResponse(major_action=ProposedAction(
            "fetch", {"kind": "bread", "target": option["target"]},
            "pkg13_policy_choice"))


class _ActionPolicy(DeterministicBackend):
    kind = "simple"

    def __init__(self, character, action=None):
        super().__init__(character)
        self.action = action

    def decide(self, context):
        return ActorResponse(major_action=self.action) if self.action else ActorResponse()


class _PropertyPolicy(DeterministicBackend):
    """Resident-held rule: communal leaves the cup shared; private takes it."""
    kind = "simple"

    def __init__(self, character, rule):
        super().__init__(character)
        self.rule = rule
        self.took = False
        self.returned = False
        self.contexts = []

    @staticmethod
    def _move(context, object_id, destination):
        return next((option for option in context.affordances
                     if option.get("action") == "move_object"
                     and option.get("object_id") == object_id
                     and option.get("destination") == destination), None)

    def decide(self, context):
        self.contexts.append(context)
        requested = any(item.get("speaker") == "Ben"
                        and "put the cup back" in item.get("text", "").lower()
                        for item in context.observations["heard_utterances"])
        if requested and not self.returned:
            option = self._move(context, "blue_cup", "table")
            if option:
                self.returned = True
                return ActorResponse(major_action=ProposedAction(
                    "move_object", {"object_id": option["object_id"],
                                    "destination": option["destination"]},
                    "I heard Ben's request and choose to return it"))
        if self.rule == "private" and not self.took:
            option = self._move(context, "blue_cup", self.character.name)
            if option:
                self.took = True
                return ActorResponse(major_action=ProposedAction(
                    "move_object", {"object_id": option["object_id"],
                                    "destination": option["destination"]},
                    "My property rule lets me keep the cup"))
        return ActorResponse()


class _WitnessPolicy(DeterministicBackend):
    """Ben's held norm: ask for return after a witnessed move from the table."""
    kind = "simple"

    def __init__(self, character):
        super().__init__(character)
        self.reactions = []

    def decide(self, context):
        evidence = next((item for item in context.observations["physical_events"]
                         if item.get("actor") == "Ada"
                         and item.get("object") == "blue_cup"
                         and item.get("from") == "table"
                         and item.get("to") == "Ada"), None)
        if evidence:
            self.reactions.append(dict(evidence))
            return ActorResponse(utterances=[{
                "target": "Ada", "text": "Please put the cup back on the table.",
                "raw": {"act": "request", "item": "blue_cup", "action": "return"},
            }])
        return ActorResponse()


def _session(actor_to_fetch):
    scenario = load_scenario("norms_property_sharing").to_dict()
    scenario["physical_objects"] = [{"id": "blue_cup", "kind": "cup", "location": "table"}]
    game = create_game(scenario=scenario, seed=713, autonomous=True,
                       ticks_per_period=None)
    world = game.world
    world.add_container("shared_larder", kind="larder", holds=(), cell=(2, 2))
    world.set_stock("bread", 1)
    assert world.fill("Ada", "shared_larder", "bread", 1)
    # Hold body state and physical configuration equal across the paired runs.
    for name in ("Ada", "Ben"):
        world.eng.set_attr(world._actors[name], "hunger", 1.0)
        game.set_backend(name, _FetchPolicy(game.characters[name], name == actor_to_fetch))
    return world, game


def test_both_residents_have_the_same_physical_fetch_option_and_action_path():
    outcomes = []
    for chooser in ("Ada", "Ben"):
        world, game = _session(chooser)
        contexts = {name: game._context(name) for name in ("Ada", "Ben")}
        for name in ("Ada", "Ben"):
            assert any(option.get("action") == "fetch"
                       and option.get("kind") == "bread"
                       for option in contexts[name].affordances)
        result = game.step()
        assert result["status"] == "advanced"
        assert game.last_results[chooser] is True
        assert world.inventory_qty(chooser, "bread") == 1.0
        assert world.contents("shared_larder", "bread") == 0.0
        outcomes.append((world.actor_position("Ada"), world.actor_position("Ben"),
                         world.inventory_qty(chooser, "bread")))
    assert outcomes[0] == outcomes[1]


def test_default_simple_policy_does_not_spontaneously_move_room_objects():
    _world, game = _session("Ada")
    backend = DeterministicBackend(game.characters["Ada"])
    response = backend.decide(game._context("Ada"))
    assert response.major_action is None or response.major_action.action != "move_object"


def test_observer_context_exposes_visible_objects_and_witnessed_movement():
    """Situated evidence names a visible mover without assigning intent."""
    world, game = _session("Ada")
    context = game._context("Ben")
    assert "physical_objects" in context.observations
    assert context.observations["physical_objects"] == world.physical_object_observations("Ben")
    assert context.observations["physical_events"] == []
    assert any(option.get("action") == "move_object"
               and option.get("object_id") == "blue_cup"
               and option.get("destination") == "Ada"
               for option in context.affordances)

    game.set_backend("Ada", _ActionPolicy(game.characters["Ada"], ProposedAction(
        "move_object", {"object_id": "blue_cup", "destination": "Ada"})))
    game.set_backend("Ben", _ActionPolicy(game.characters["Ben"]))
    game.step()
    stored_events = [dict(event) for event in game._physical_events.get("Ben", [])]
    game._context("Ben")
    game._context("Ben")
    assert game._physical_events["Ben"] == stored_events
    events = game._context("Ben").observations["physical_events"]
    assert events == [{"actor": "Ada", "action": "moved_object", "object": "blue_cup",
                       "from": "table", "to": "Ada", "turn": int(world._turn),
                       "expires_turn": int(world._turn)}]
    assert "theft" not in str(events).lower()
    game.step()
    assert game._context("Ben").observations["physical_events"] == []


def _norm_session(rule, *, witness_visible=True):
    world, game = _session("Ada")
    if not witness_visible:
        while world.actor_position("Ben") != (3, 3):
            world.move_actor("Ben", (3, 3))
    resident = _PropertyPolicy(game.characters["Ada"], rule)
    witness = _WitnessPolicy(game.characters["Ben"])
    game.set_backend("Ada", resident)
    game.set_backend("Ben", witness)
    return world, game, resident, witness


def test_agent_held_property_policies_change_choice_with_same_physical_options():
    paired = []
    for rule in ("communal", "private"):
        world, game, resident, witness = _norm_session(rule)
        initial = {"objects": world.physical_objects(),
                   "positions": {name: world.actor_position(name) for name in ("Ada", "Ben")},
                   "inventory": {name: world.inventory(name) for name in ("Ada", "Ben")},
                   "affordances": game._context("Ada").affordances}
        assert any(option.get("object_id") == "blue_cup"
                   and option.get("destination") == "Ada"
                   for option in initial["affordances"])
        first = game.step()
        after_choice = next(item for item in world.physical_objects()
                            if item["id"] == "blue_cup")["location"]
        if rule == "private":
            assert first["results"]["Ada"] is True
            assert after_choice == "Ada"
            # Ben's next backend pass gets the situated movement event and
            # chooses a request under Ben's own rule.
            game.step()
            assert len(witness.reactions) == 1
            assert resident.returned is False  # delivery follows the decision pass
            assert any(item["speaker"] == "Ben"
                       for item in world.heard_utterances("Ada"))
            # Ada independently chooses the physical return action after
            # receiving Ben's speech; no world rule moves the cup for her.
            game.step()
            assert resident.returned
            assert next(item for item in world.physical_objects()
                        if item["id"] == "blue_cup")["location"] == "table"
        else:
            assert first["results"]["Ada"] is True  # successful observation/idle turn
            assert after_choice == "table"
            game.step()
            assert witness.reactions == []
        final = {"objects": world.physical_objects(),
                 "positions": {name: world.actor_position(name) for name in ("Ada", "Ben")},
                 "inventory": {name: world.inventory(name) for name in ("Ada", "Ben")}}
        assert initial["positions"] == final["positions"]
        assert initial["inventory"] == final["inventory"]
        assert len([item for item in final["objects"] if item["id"] == "blue_cup"]) == 1
        paired.append((initial, after_choice, final))
    # Norm changes choices and social response; the physical room starts the
    # same, and all object movement remains accounted for in location state.
    assert paired[0][0]["objects"] == paired[1][0]["objects"]
    assert paired[0][1] != paired[1][1]


def test_unseen_move_creates_no_witness_reaction_even_after_late_arrival():
    world, game, resident, witness = _norm_session("private", witness_visible=False)
    assert world.distance(world.actor_position("Ada"), world.actor_position("Ben")) > 1
    before = world.physical_objects()
    game.step()
    assert game.last_results["Ada"] is True
    assert next(item for item in world.physical_objects()
                if item["id"] == "blue_cup")["location"] == "Ada"
    assert game._context("Ben").observations["physical_events"] == []
    assert witness.reactions == []

    # Late arrival exposes the current scene, but it cannot reconstruct the
    # actor or action that changed it, so no sanction/request is generated.
    world.move_actor("Ben", world.actor_position("Ada"))
    game.step()
    assert witness.reactions == []
    assert not any(item["speaker"] == "Ben" for item in world.heard_utterances("Ada"))
    assert sum(item["id"] == "blue_cup" for item in world.physical_objects()) == 1
    assert before[0]["location"] == "table"


def test_late_arrival_does_not_turn_a_hidden_move_into_a_witnessed_event():
    world, game = _session("Ada")
    world.move_actor("Ben", (3, 2))
    world.move_actor("Ben", (3, 3))
    game.set_backend("Ada", _ActionPolicy(game.characters["Ada"], ProposedAction(
        "move_object", {"object_id": "blue_cup", "destination": "world"})))
    game.set_backend("Ben", _ActionPolicy(game.characters["Ben"]))
    game.step()
    assert game._context("Ben").observations["physical_events"] == []
    assert {item["id"] for item in game._context("Ben").observations["physical_objects"]} >= {"blue_cup"}

    world.move_actor("Ben", world.actor_position("Ada"))
    game.step()
    assert game._context("Ben").observations["physical_events"] == []


def test_held_legal_interpretation_does_not_gate_unobserved_physical_action():
    """Legal belief lives with the decision maker; the room only checks physics."""
    outcomes = []
    for interpretation in ("forbidden", "permitted"):
        world, game = _session("Ada")
        # Make the same move unobservable to Ben. The backend-held label is
        # deliberately not an action precondition supplied by the world.
        # ``move_actor`` resolves one physical step, not a teleport. Walk until
        # Ben is truly beyond the witness radius before testing hidden action.
        while world.actor_position("Ben") != (3, 3):
            world.move_actor("Ben", (3, 3))
        assert world.distance(world.actor_position("Ada"),
                              world.actor_position("Ben")) > 1
        context = game._context("Ada")
        option = _PropertyPolicy._move(context, "blue_cup", "Ada")
        assert option is not None
        held_belief = {"interpretation": interpretation,
                       "rule": "taking a cup from the table is " + interpretation}

        class BeliefPolicy(DeterministicBackend):
            kind = "simple"

            def decide(self, actor_context):
                # The scripted resident elects to act under either private
                # interpretation; only physical affordances validate the move.
                return ActorResponse(major_action=ProposedAction(
                    "move_object", {"object_id": option["object_id"],
                                    "destination": option["destination"]},
                    held_belief["rule"]))

        policy = BeliefPolicy(game.characters["Ada"])
        policy.held_belief = held_belief
        witness = _WitnessPolicy(game.characters["Ben"])
        game.set_backend("Ada", policy)
        game.set_backend("Ben", witness)
        result = game.step()
        assert result["status"] == "advanced"
        assert game.last_results["Ada"] is True
        assert next(item for item in world.physical_objects()
                    if item["id"] == "blue_cup")["location"] == "Ada"
        assert game._context("Ben").observations["physical_events"] == []
        assert witness.reactions == []
        assert not any(item["speaker"] == "Ben"
                       for item in world.heard_utterances("Ada"))
        outcomes.append((policy.held_belief["interpretation"],
                         context.affordances, world.physical_objects()))

    assert outcomes[0][0] != outcomes[1][0]
    assert outcomes[0][1] == outcomes[1][1]


def test_conflicting_held_legal_policies_do_not_gate_proposal_records():
    """Residents can record proposals regardless of their private legal views."""
    world = BigvilleWorld.from_town100(seed=305000)
    authors = list(world._actors)[:2]
    inherited = next(iter(world.inherited_law_names()))
    outcomes = []
    for author, interpretation in zip(authors, ("may be changed", "must remain unchanged")):
        held_policy = {"law": inherited, "interpretation": interpretation}
        proposal = world.propose_local_law(author, held_policy["law"])
        attrs = world.eng.node(proposal)["attrs"]
        assert attrs["name"] == inherited
        assert attrs["author"] == author
        outcomes.append((held_policy["interpretation"], attrs["name"], attrs["author"]))
    assert outcomes[0][0] != outcomes[1][0]
    assert outcomes[0][1:] != outcomes[1][1:]

