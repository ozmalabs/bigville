"""Construction functions for Bigville worlds and game sessions."""
from __future__ import annotations

from .backends import OcelotBackend
from .game import BigvilleGame


def create_world(*, scenario="town100", seed=305000, autonomous_actors=True):
    from worlds.bigville_world import BigvilleWorld

    if scenario in {"town100", "default"}:
        return BigvilleWorld.from_town100(seed=seed, autonomous_actors=autonomous_actors)
    return BigvilleWorld(map_seed=seed, autonomous_actors=autonomous_actors)


def create_game(*, scenario="town100", seed=305000, player=None,
                default_backend="cheap", backend_factories=None):
    world = create_world(scenario=scenario, seed=seed, autonomous_actors=False)
    factories = dict(backend_factories or {})
    game = BigvilleGame(world, player=player)
    for name, character in game.characters.items():
        kind = "human" if name == game.player else default_backend
        factory = factories.get(kind)
        if factory is not None:
            game.set_backend(name, factory(world, character))
        elif kind == "ocelot":
            game.set_backend(name, OcelotBackend(world, character))
    return game
