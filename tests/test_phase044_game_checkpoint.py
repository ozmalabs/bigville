"""Phase 044 follow-up: a game with a newborn can be saved and loaded. The newborn's DependentBackend needs a branch in
bigville/game_persistence.py (_backend_checkpoint and _build_backend); before it, save_game_checkpoint raised
TypeError("unsupported backend DependentBackend") once a newborn existed.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.game import BigvilleGame                          # noqa: E402
from bigville.game_persistence import load_game_checkpoint, save_game_checkpoint  # noqa: E402
from bigville.resident_births import DependentBackend           # noqa: E402
from worlds.bigville_world import BigvilleWorld as World        # noqa: E402


def _game_with_newborn(monkeypatch):
    w = World.from_town100(seed=305000, physical_subsystems={"births": True})
    for key, value in {"stillbirth": 0.0, "maternal_death": 0.0, "infant_first_year_death": 0.0}.items():
        monkeypatch.setitem(w.E.BIRTHS, key, value)
    game = BigvilleGame(w, autonomous=True, ticks_per_period="world")
    mother = next(n for n in w._actors
                  if w.eng.node(w._actors[n])["attrs"].get("kin_sex") == "female"
                  and 25 <= float(w.eng.node(w._actors[n])["attrs"]["age"]) <= 40
                  and w._union_partner(n) is not None)
    w.eng.set_attr(w._town, "day", 100.0)
    w._conceive(mother, w._union_partner(mother), 100)
    w.eng.set_attr(w._town, "day", float(w.eng.node(w._actors[mother])["attrs"]["due_day"]))
    w._births_day()
    child = w._births[-1]["child"]
    game.step()                      # attaches the newborn's character and DependentBackend
    assert isinstance(game.backends[child], DependentBackend)
    return game, child


def test_a_game_with_a_newborn_saves_and_loads_with_a_dependent_backend(monkeypatch, tmp_path):
    game, child = _game_with_newborn(monkeypatch)
    save_game_checkpoint(game, tmp_path / "game")
    restored = load_game_checkpoint(tmp_path / "game")
    assert child in restored.characters
    backend = restored.backends[child]
    assert isinstance(backend, DependentBackend)
    assert backend.character.character_id == child
    assert backend.decide(None).major_action is None
