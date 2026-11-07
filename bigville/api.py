"""Construction functions for Bigville worlds and game sessions."""
from __future__ import annotations

from .backends import HumanBackend, LLMBackend, OcelotBackend
from .game import BigvilleGame
from .backends.ocelot import ocelot_resident_class
from .llm_log import attach_default as attach_default_llm_log


def _requires_ocelot(scenario, default_backend, player):
    from .scenarios import load_scenario
    if isinstance(scenario, str) and scenario in {"town100", "default"}:
        return default_backend == "ocelot"
    actors = load_scenario(scenario).actors
    return any(actor.get("name") != player and
               actor.get("backend", default_backend) == "ocelot" for actor in actors)


def create_world(*, scenario="town100", seed=305000, autonomous_actors=False,
                 cognition_factory=None, physical_subsystems=None):
    from worlds.bigville_world import BigvilleWorld

    if isinstance(scenario, str) and scenario in {"town100", "default"}:
        return BigvilleWorld.from_town100(
            seed=seed, autonomous_actors=autonomous_actors,
            cognition_factory=cognition_factory,
            physical_subsystems=physical_subsystems)
    return BigvilleWorld.from_scenario(scenario, seed=seed,
                                       autonomous_actors=autonomous_actors,
                                       cognition_factory=cognition_factory,
                                       physical_subsystems=physical_subsystems)


def llm_backend_factory(provider):
    """A ``backend_factories`` entry that builds an LLM resident around ``provider``.

    ``provider`` is an object with ``complete(prompt)`` or a callable taking the prompt
    dict. Core imports no vendor SDK; the caller supplies the provider."""
    def factory(world, character):
        return LLMBackend(character, provider)
    return factory


def create_game(*, scenario="town100", seed=305000, player=None,
                default_backend="cheap", backend_factories=None,
                cognition_factory=None, autonomous=False, ticks_per_period="world",
                llm_provider=None, llm_log=True, llm_log_dir=None,
                physical_subsystems=None, turn_semantics="sequential",
                simultaneous_priority=None, executor="serial", executor_workers=4,
                affordance_mode="auto", snapshot_mode="every_turn"):
    """Build a game session. ``"llm"`` residents need a provider, given either as
    ``llm_provider=`` (the same provider for every LLM resident) or as
    ``backend_factories={"llm": ...}`` (for example ``llm_backend_factory(p)``), not both.
    A game with LLM residents writes its complete log to ``llm_log_dir`` (else ``BIGVILLE_LLM_LOG_DIR``, else
    ``runs/llm_logs``); ``llm_log=False`` turns that off. A game without LLM residents writes nothing.

    ``affordance_mode`` defaults to ``"auto"``: it resolves to ``"lazy"``
    (observation/proposal/validation) for an autonomous session whose resident
    backends are all built-in simple/cheap, and to ``"menu"`` (the exhaustive
    per-turn legal-action menu) for a player, an LLM, Ocelot or any other
    backend.  ``"menu"`` and ``"lazy"`` may be passed explicitly and always
    win; ``game.affordance_mode_requested`` keeps the requested value while
    ``game.affordance_mode`` reports the resolved mode.  See
    ``docs/phases/lazy-affordances/LA08_REPORT.md``.

    ``snapshot_mode`` controls whether ``game.step()`` includes the full UI
    snapshot.  It defaults to ``"every_turn"`` (historical behaviour).
    ``"on_demand"`` omits the ``"snapshot"`` key so a headless turn does not
    build the world report; call ``game.snapshot()`` when it is needed.
    ``"auto"`` resolves to ``"on_demand"`` for the same autonomous simple/cheap
    sessions the affordance auto rule selects, and to ``"every_turn"`` for a
    player, LLM, Ocelot or other backend.  Explicit values always win;
    ``game.snapshot_mode_requested`` keeps the requested value while
    ``game.snapshot_mode`` reports the resolved mode."""
    if _requires_ocelot(scenario, default_backend, player) and cognition_factory is None:
        cognition_factory = ocelot_resident_class()
    if (backend_factories or {}).get("ocelot") is not None:
        raise ValueError("Use cognition_factory for the Ocelot backend")
    if llm_provider is not None and (backend_factories or {}).get("llm") is not None:
        raise ValueError("Pass llm_provider or backend_factories['llm'], not both")
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
                         cognition_factory=cognition_factory,
                         physical_subsystems=physical_subsystems)
    factories = dict(backend_factories or {})
    if llm_provider is not None:
        factories["llm"] = llm_backend_factory(llm_provider)
    game = BigvilleGame(world, player=player, autonomous=autonomous,
                        ticks_per_period=ticks_per_period,
                        turn_semantics=turn_semantics,
                        simultaneous_priority=simultaneous_priority,
                        executor=executor, executor_workers=executor_workers,
                        affordance_mode=affordance_mode,
                        snapshot_mode=snapshot_mode)
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
        elif kind == "llm":
            raise ValueError("The llm backend needs llm_provider=... or backend_factories['llm']")
        elif kind not in {"cheap", "simple", "human"}:
            raise ValueError(f"Unknown backend: {kind}")
    # LA08: backends are assigned after construction, so resolve "auto" now.
    game.resolve_affordance_mode()
    game.resolve_snapshot_mode()
    game.llm_log = attach_default_llm_log(game.backends, enabled=llm_log, log_dir=llm_log_dir)
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
