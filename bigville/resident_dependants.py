"""Phase 045: a dependant who has grown up acts. The game side.

A newborn gets a DependentBackend (bigville/resident_births.py), which proposes nothing. Once the world says
the child is past the infant stage, the game replaces that backend with the simple backend, which then acts
at the child's work_fraction (the world scales its force and stamina). Infants keep the DependentBackend, so an
infant still proposes nothing. The DependentBackend class itself is not edited (Phase 044's file).

Called from BigvilleGame.step() before the turn's decisions, so a child that grew up in the last period acts
in the next turn. With the dependants switch off there are no newborns to promote, and the call returns [].
"""
from __future__ import annotations


def promote_grown_dependants(game) -> list[str]:
    """Replace the DependentBackend of each resident who is no longer an infant. Returns the names replaced."""
    from bigville.backends.cheap import CheapBackend, simple_policy_for
    from bigville.resident_births import DependentBackend
    world = game.world
    if not world._dependants_on():
        return []
    promoted = []
    for name, backend in list(game.backends.items()):
        if not isinstance(backend, DependentBackend) or name not in world._actors or name not in game.characters:
            continue
        if not world.is_alive(name) or world._life_stage_is(world._life_stage(name), "infant"):
            continue
        profile = getattr(world, "_scenario_simple_profiles", {}).get(name, "default")
        game.set_backend(name, CheapBackend(game.characters[name], policy=simple_policy_for(profile)))
        promoted.append(name)
    return promoted
