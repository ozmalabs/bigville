"""Public API for the standalone Bigville simulation."""

# Both projects use these top-level packages. Include both distributions
# when Ocelot's regular packages and Bigville's namespace packages coexist.
from pkgutil import extend_path
import domains as _domains
import worlds as _worlds

_domains.__path__ = extend_path(_domains.__path__, _domains.__name__)
_worlds.__path__ = extend_path(_worlds.__path__, _worlds.__name__)

from .api import create_board_game, create_game, create_tabletop_experiment, create_world
from .character import CharacterDefinition, FrameSeed, MemoryRecord
from .game import BigvilleGame
from .reporting import SimulationReporter
from .scenarios import ScenarioDefinition, list_scenarios, load_scenario

__all__ = [
    "BigvilleGame",
    "SimulationReporter",
    "CharacterDefinition",
    "FrameSeed",
    "MemoryRecord",
    "create_game",
    "create_world",
    "create_board_game",
    "create_tabletop_experiment",
    "ScenarioDefinition",
    "load_scenario",
    "list_scenarios",
]
