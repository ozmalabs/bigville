"""Construction functions for Bigville worlds and game sessions."""
from __future__ import annotations

from .backends import HumanBackend, OcelotBackend
from .game import BigvilleGame
from .backends.ocelot import ocelot_resident_class


def _requires_ocelot(scenario, default_backend, player):
    from .scenarios import load_scenario
    if isinstance(scenario, str) and scenario in {"town100", "default"}:
        return default_backend == "ocelot"
    actors = load_scenario(scenario).actors
    return any(actor.get("name") != player and
               actor.get("backend", default_backend) == "ocelot" for actor in actors)


def create_world(*, scenario="town100", seed=305000, autonomous_actors=False,
                 cognition_factory=None):
    from worlds.bigville_world import BigvilleWorld

    if isinstance(scenario, str) and scenario in {"town100", "default"}:
        return BigvilleWorld.from_town100(
            seed=seed, autonomous_actors=autonomous_actors,
            cognition_factory=cognition_factory)
    return BigvilleWorld.from_scenario(scenario, seed=seed,
                                       autonomous_actors=autonomous_actors,
                                       cognition_factory=cognition_factory)


def create_game(*, scenario="town100", seed=305000, player=None,
                default_backend="cheap", backend_factories=None,
                cognition_factory=None, autonomous=False, ticks_per_period=96):
    if _requires_ocelot(scenario, default_backend, player) and cognition_factory is None:
        cognition_factory = ocelot_resident_class()
    if (backend_factories or {}).get("ocelot") is not None:
        raise ValueError("Use cognition_factory for the Ocelot backend")
    if cognition_factory is not None:
        from .scenarios import load_scenario
        from worlds.bigville_world import BigvilleOcelotActor
        actors = ([] if isinstance(scenario, str) and scenario in {"town100", "default"}
                  else load_scenario(scenario).actors)
        kinds = {actor["name"]: actor.get("backend", default_backend) for actor in actors}
        provider = cognition_factory
        cognition_factory = lambda name: (provider(name) if name != player and
                                            kinds.get(name, default_backend) == "ocelot"
                                            else BigvilleOcelotActor(name))
    world = create_world(scenario=scenario, seed=seed, autonomous_actors=False,
                         cognition_factory=cognition_factory)
    factories = dict(backend_factories or {})
    game = BigvilleGame(world, player=player, autonomous=autonomous,
                        ticks_per_period=ticks_per_period)
    scenario_backends = getattr(world, "_scenario_actor_backends", {})
    for name, character in game.characters.items():
        kind = "human" if name == game.player else scenario_backends.get(name, default_backend)
        factory = factories.get(kind)
        if factory is not None:
            game.set_backend(name, factory(world, character))
        elif kind == "ocelot":
            game.set_backend(name, OcelotBackend(world, character))
        elif kind == "human":
            game.set_backend(name, HumanBackend(character))
        elif kind not in {"cheap", "simple", "human"}:
            raise ValueError(f"Unknown backend: {kind}")
    return game


def create_board_game(*, scenario="monopoly_four_players", seed=305000, backend=None,
                      cognition_factory=None):
    """Create a room observation with physical tabletop objects.

    The returned session does not set up or run a game. Participants receive
    cognition ticks and may interpret or ignore the objects. The world exposes
    only generic physical affordances; any game frame remains private to the
    participants or an external experiment.
    """
    from .held_board_games import HeldMonopolyExperiment
    from .scenarios import load_scenario

    definition = load_scenario(scenario)
    needs_ocelot = (backend == "ocelot" if backend is not None else
                    _requires_ocelot(definition, "cheap", None))
    if needs_ocelot and cognition_factory is None:
        cognition_factory = ocelot_resident_class()
    if cognition_factory is not None:
        from worlds.bigville_world import BigvilleOcelotActor
        kinds = {actor["name"]: backend or actor.get("backend", "cheap")
                 for actor in definition.actors}
        provider = cognition_factory
        cognition_factory = lambda name: (provider(name) if kinds.get(name) == "ocelot"
                                            else BigvilleOcelotActor(name))
    # The physical room and its neutral objects always exist. The backend is
    # optional; it does not determine whether the world has the objects.
    from worlds.bigville_world import BigvilleWorld
    physical_world = BigvilleWorld.from_scenario(
        definition, seed=seed, autonomous_actors=False,
        cognition_factory=cognition_factory)
    return HeldMonopolyExperiment.from_scenario(
        definition, seed=seed, backend_override=backend,
        physical_world=physical_world)


def create_tabletop_experiment(*, scenario, seed=305000, cognition_factory=None):
    """Create generic held setup state for any scenario-authored tabletop game."""
    from .held_board_games import HeldTabletopExperiment
    from .scenarios import load_scenario
    from worlds.bigville_world import BigvilleWorld

    definition = load_scenario(scenario)
    physical_world = BigvilleWorld.from_scenario(
        definition, seed=seed, autonomous_actors=False,
        cognition_factory=cognition_factory)
    return HeldTabletopExperiment.from_scenario(
        definition, physical_world=physical_world)
