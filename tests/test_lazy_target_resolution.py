"""LA02: action-specific target resolution for backend proposals.

Enactment must not rebuild the exhaustive affordance menu just to find a
target.  A proposal that names stable identities (actors, containers,
projects, infrastructure, crops, animals or cells) installs an empty target
map; only a legacy ``target:N`` proposal falls back to ``_actor_options``.

The tests here check three things:

- direct-name/direct-cell plans never call ``_actor_options``;
- each direct form produces the same world state as the equivalent legacy
  ``target:N`` option on a fresh, identically prepared world;
- malformed direct values are refused with an existing refusal code and never
  raise.

The existing Phase 020 validation tournament remains the exhaustive check that
every published option can still be enacted; it is run alongside this file.
"""
from __future__ import annotations

import pytest

from bigville.api import create_game
from bigville.tick_trace import TurnTrace, semantic_step_trace
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld


# ------------------------------------------------------------------ fixtures/helpers
def _town():
    """A deterministic seeded village, advanced one tick."""
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    world.tick()
    return world


def _seed_inventory(world, actor, kind, qty=3.0):
    stock = world._inventory_stock(actor, kind, create=True)
    world.eng.set_attr(stock, "qty", float(qty))


def _spy_options(world):
    """Wrap ``_actor_options`` on this instance and return the call list."""
    calls = []
    original = world._actor_options

    def counted(actor):
        calls.append(actor)
        return original(actor)

    world._actor_options = counted
    return calls


def _prepared(setup):
    world, actor = setup()
    world.actor_tick(actor)
    return world, actor


def _option(world, actor, action):
    options = world.actor_affordances(actor)
    match = next((option for option in options if option["action"] == action), None)
    assert match is not None, f"setup offered no {action} option: {[o['action'] for o in options]}"
    return match


def _first_storage_container(world):
    return next(name for name, (node, _) in world._containers.items()
                if world.eng.node(node)["attrs"].get("kind") != "carrier")


# ------------------------------------------------------------------ scenario setups
def _setup_move():
    world = _town()
    actor = sorted(world._actors)[0]
    return world, actor


def _setup_give():
    world = _town()
    actor, recipient = sorted(world._actors)[:2]
    world._move_actor_to(recipient, world.actor_position(actor))
    _seed_inventory(world, actor, "bread")
    world._la02_recipient = recipient
    return world, actor


def _setup_transfer():
    return _setup_give()


def _setup_put():
    world = _town()
    actor = sorted(world._actors)[0]
    container = _first_storage_container(world)
    world._move_actor_to(actor, world.container_position(container))
    _seed_inventory(world, actor, "bread")
    return world, actor


def _setup_fetch():
    world = _town()
    actor = sorted(world._actors)[0]
    world.add_container("la02_barrel", kind="barrel", holds="bread",
                        cell=world.actor_position(actor))
    world.eng.set_attr(world._containers["la02_barrel"][1]["bread"], "qty", 3.0)
    return world, actor


def _setup_lock():
    world = _town()
    actor = sorted(world._actors)[0]
    world.add_container("la02_box", kind="chest", holds="bread", lock_id=77.0,
                        locked=True, cell=world.actor_position(actor))
    world.give_key(actor, 77.0)
    return world, actor


def _setup_lock_open():
    world = _town()
    actor = sorted(world._actors)[0]
    world.add_container("la02_box", kind="chest", holds="bread", lock_id=77.0,
                        locked=False, cell=world.actor_position(actor))
    world.give_key(actor, 77.0)
    return world, actor


def _setup_care():
    world = _town()
    actor, patient = sorted(world._actors)[:2]
    world._move_actor_to(patient, world.actor_position(actor))
    world.eng.set_attr(world._actors[patient], "health", "ill")
    return world, actor


def _setup_build():
    world = _town()
    actor = sorted(world._actors)[0]
    world.set_stock("timber", 100.0)
    world.set_stock("thatch", 100.0)
    world.propose_building("house", site=world.actor_position(actor), name="la02_house")
    return world, actor


def _setup_maintain():
    world = _town()
    actor = sorted(world._actors)[0]
    name = next(iter(world._infrastructure))
    world._move_actor_to(actor, world.map_position_node(world._infrastructure[name]))
    spec = world.E.INFRASTRUCTURE[world.eng.node(world._infrastructure[name])["attrs"]["kind"]]
    for kind in spec.get("maintenance", ()):
        world.set_stock(kind, 10.0)
    world.eng.set_attr(world._infrastructure[name], "condition", 0.5)
    return world, actor


def _setup_tend_animals():
    world = _town()
    actor = sorted(world._actors)[0]
    animal = next(iter(world._animals))
    world._move_actor_to(actor, world.map_position_node(world._animals[animal]))
    return world, actor


def _setup_water():
    world = _town()
    actor = sorted(world._actors)[0]
    crop = next(iter(world._living_crops()))
    world._move_actor_to(actor, world.map_position_node(crop))
    world.eng.set_attr(crop, "thirst", 1.0)
    world.set_stock("water", 100.0)
    return world, actor


def _setup_harvest():
    world = _town()
    actor = sorted(world._actors)[0]
    crop = next(iter(world._living_crops()))
    world._move_actor_to(actor, world.map_position_node(crop))
    attrs = world.eng.node(crop)["attrs"]
    world.eng.set_attr(crop, "age", float(attrs["grow_periods"]))
    return world, actor


# Name -> (setup, action, direct-plan builder from the selected option and its
# target map).  Every direct plan names a stable value, never a "target:N" key.
CASES = {
    "move": (_setup_move, "move",
             lambda option, targets: {"action": "move", "destination": option["destination"]}),
    "transfer": (_setup_transfer, "transfer",
                 lambda option, targets: {"action": "transfer", "recipient": option["recipient"],
                                          "kind": option["kind"], "amount": 1.0}),
    "put": (_setup_put, "put",
            lambda option, targets: {"action": "put", "container": targets[option["target"]],
                                     "kind": option["kind"], "amount": 1.0}),
    "fetch": (_setup_fetch, "fetch",
              lambda option, targets: {
                  "action": "fetch",
                  "source": option.get("source_container") or targets[option["target"]],
                  "kind": option["kind"], "amount": 1.0}),
    "unlock": (_setup_lock, "unlock",
               lambda option, targets: {"action": "unlock", "container": targets[option["target"]]}),
    "lock": (_setup_lock_open, "lock",
             lambda option, targets: {"action": "lock", "container": targets[option["target"]]}),
    "care": (_setup_care, "care",
             lambda option, targets: {"action": "care", "patient": option["patient"],
                                      "care_kind": option.get("care_kind")}),
    "build": (_setup_build, "build",
              lambda option, targets: {"action": "build", "project": option["project"]}),
    "maintain": (_setup_maintain, "maintain",
                 lambda option, targets: {"action": "maintain", "name": option["name"]}),
    "tend_animals": (_setup_tend_animals, "tend_animals",
                     lambda option, targets: {"action": "tend_animals",
                                              "animal": option["animal"], "kind": option["kind"]}),
    "water": (_setup_water, "water",
              lambda option, targets: {"action": "water", "crop_node": option["crop_node"]}),
    "harvest": (_setup_harvest, "harvest",
                lambda option, targets: {"action": "harvest", "crop_node": option["crop_node"]}),
}


# ------------------------------------------------------------------ direct plans are menu-free
@pytest.mark.parametrize("case", sorted(CASES))
def test_a_direct_proposal_never_builds_the_menu(case):
    setup, action, direct = CASES[case]

    menu_world, menu_actor = _prepared(setup)
    option = _option(menu_world, menu_actor, action)
    plan = direct(option, menu_world._actor_targets[menu_actor])

    world, actor = _prepared(setup)
    calls = _spy_options(world)
    assert world.enact_plan(actor, plan) is True
    assert calls == [], f"{case} rebuilt the exhaustive menu for a direct proposal"


def test_a_direct_give_never_builds_the_menu():
    world, actor = _prepared(_setup_give)
    plan = {"action": "give", "recipient": world._la02_recipient,
            "kind": "bread", "amount": 1.0}
    calls = _spy_options(world)
    assert world.enact_plan(actor, plan) is True
    assert calls == []


# ------------------------------------------------------------------ direct/legacy equivalence
@pytest.mark.parametrize("case", sorted(CASES))
def test_direct_form_reaches_the_same_world_state_as_the_legacy_target_key(case):
    setup, action, direct = CASES[case]

    menu_world, menu_actor = _prepared(setup)
    option = _option(menu_world, menu_actor, action)
    plan = direct(option, menu_world._actor_targets[menu_actor])
    assert str(option.get("target", "")).startswith("target:"), "legacy option lost its key"

    legacy_world, legacy_actor = _prepared(setup)
    legacy_result = legacy_world.enact_plan(legacy_actor, dict(option))

    direct_world, direct_actor = _prepared(setup)
    direct_result = direct_world.enact_plan(direct_actor, plan)

    assert legacy_result is True
    assert direct_result is True
    assert legacy_world.export_state() == direct_world.export_state()


def test_a_legacy_target_key_still_builds_the_menu_and_resolves():
    world, actor = _prepared(_setup_move)
    option = _option(world, actor, "move")
    before = world.actor_position(actor)
    calls = _spy_options(world)
    assert world.enact_plan(actor, dict(option)) is True
    assert calls == [actor]
    assert world.actor_position(actor) != before


def test_resolve_targets_returns_the_installed_map():
    world, actor = _prepared(_setup_move)
    plan = {"action": "move", "destination": world.actor_position(actor)}
    calls = _spy_options(world)
    targets = world.resolve_targets(actor, "move", plan)
    assert targets == {}
    assert world._actor_targets[actor] is targets
    assert calls == []

    world, actor = _prepared(_setup_move)
    calls = _spy_options(world)
    legacy = world.resolve_targets(actor, "move", {"action": "move", "target": "target:0"})
    assert calls == [actor]
    assert legacy is world._actor_targets[actor]
    assert legacy  # the menu published at least one target


# ------------------------------------------------------------------ malformed direct values
MALFORMED_DIRECT = [
    ("move", {"destination": "not-a-cell"}),
    ("give", {"recipient": "Nobody", "kind": "bread"}),
    ("transfer", {"recipient": "Nobody", "kind": "bread"}),
    ("put", {"container": "no_such_container", "kind": "bread"}),
    ("fetch", {"source": "no_such_container", "kind": "bread"}),
    ("lock", {"container": "no_such_container"}),
    ("care", {"patient": "Nobody"}),
    ("build", {"project": "no_such_project"}),
    ("maintain", {"name": "no_such_infrastructure"}),
    ("tend_animals", {"animal": "no_such_animal", "kind": "milk"}),
    ("water", {"crop_node": 999999}),
    ("harvest", {"target": 999999}),
]


@pytest.mark.parametrize("action,kwargs", MALFORMED_DIRECT,
                         ids=[f"{action}-{index}" for index, (action, _) in enumerate(MALFORMED_DIRECT)])
def test_an_unknown_direct_value_is_refused_without_a_menu_or_an_exception(action, kwargs):
    world = _town()
    actor = sorted(world._actors)[0]
    world.actor_tick(actor)
    calls = _spy_options(world)

    assert world.enact_plan(actor, {"action": action, **kwargs}) is False
    assert calls == []

    outcome = world.eng.node(world._actors[actor])["attrs"]["last_outcome"]
    assert outcome["applied"] is False
    assert outcome["reason"] in E.REFUSAL_REASONS


# ------------------------------------------------------------------ menu-mode trace oracle
SMALL_SCENARIO = {
    "id": "la01_mode_room",
    "name": "LA01 mode room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}

# Recorded from the LA01 base commit (9725e10) with the exact scenario above.
MENU_DIGEST_AT_LA01 = "8a49c09be5cbe1404d0626c81d531a3cb40dec2c04ff1196dd888e291f84ee3b"


def _small_trace(turns=2):
    game = create_game(scenario=SMALL_SCENARIO, seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False, affordance_mode="menu")
    trace = TurnTrace()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add_record(semantic_step_trace(game))
    return trace


def test_menu_mode_trace_digest_is_unchanged_over_two_turns():
    trace = _small_trace()
    assert trace.turns == 2
    assert trace.hexdigest() == MENU_DIGEST_AT_LA01
    assert trace.hexdigest() == _small_trace().hexdigest()
