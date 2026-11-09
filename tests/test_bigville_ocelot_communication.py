"""The Ocelot capability flags must match what its real resident can do."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, communication_capabilities


_BIGVILLE_ROOT = Path(__file__).resolve().parents[1]
_OCELOT_ROOT = _BIGVILLE_ROOT.parent / "ocelot"


@pytest.mark.skipif(not (_OCELOT_ROOT / "worlds" / "bigville_ocelot_adapter.py").is_file(),
                    reason="Ocelot source checkout is not present")
def test_real_ocelot_advertises_only_wired_communication_capabilities(monkeypatch):
    if not (_BIGVILLE_ROOT / "bigville" / "seeds" / "bigville_actor_decision.json").is_file():
        pytest.skip("standalone Bigville seed checkout is not present")

    monkeypatch.setenv("BIGVILLE_ROOT", str(_BIGVILLE_ROOT))
    for entry in (_OCELOT_ROOT, _OCELOT_ROOT / "runners" / "dsl" / "python"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    pytest.importorskip("substrate_rs")
    try:
        importlib.import_module("worlds.bigville_ocelot_adapter")
    except ImportError as exc:
        # Bigville's `worlds` namespace package may already be imported in this
        # process and shadow Ocelot's; run from the Ocelot checkout (see
        # docs/ocelot-integration-baseline.md) to exercise this test.
        pytest.skip(f"Ocelot's worlds.bigville_ocelot_adapter is not importable here: {exc}")
    resident_class = importlib.import_module("worlds.bigville_ocelot_adapter").BigvilleOcelotResident

    scenario = json.loads((_BIGVILLE_ROOT / "scenarios" / "simple_resident_food.json").read_text())
    scenario["actors"] = [
        {"name": "Ada", "role": "hand", "backend": "ocelot", "home_cell": [2, 2]},
        {"name": "Ben", "role": "hand", "backend": "simple", "home_cell": [2, 2]},
    ]
    game = create_game(scenario=scenario, seed=305000, player="Ben", default_backend="simple",
                       ticks_per_period=None)

    resident = game.world.actor_mind("Ada")
    assert isinstance(resident, resident_class)
    # A separate graph full-text API exists, but the ordinary game backend
    # only calls propose_free_text; the resident does not expose that hook.
    assert callable(getattr(resident, "goal_utterance", None))
    assert not callable(getattr(resident, "propose_free_text", None))
    assert not callable(getattr(getattr(resident, "speech_provider", None),
                                "propose_free_text", None))
    assert not callable(getattr(resident, "ingest_speech", None))
    assert not callable(getattr(resident, "understand_raw_speech", None))

    expected = {
        "mode": "templated",
        "supports_free_text": False,
        "understands_raw_speech": False,
        "requires_conversational_interface": True,
    }
    assert communication_capabilities(game.backends["Ada"]) == expected
    assert game.dump_held_state("Ada")["backend_state"]["communication"] == expected

    # `goal_utterance` is a separate convenience API, not the backend's
    # ordinary free-text proposal hook. A regular decision must not invent a
    # sentence from Ocelot's graph renderer or Bigville's compatibility layer.
    proposal = game.backends["Ada"].decide(game._context("Ada"))
    assert proposal.utterances == []

    raw = {"intent": "request", "object": "water", "confidence": 0.9}
    game._apply_response("Ben", ActorResponse(utterances=[{
        "target": "Ada", "text": "Could you bring some water?", "raw": raw,
    }]))
    utterance = game.world.conversation_between("Ben", "Ada")[-1]
    attrs = game.world.eng.node(utterance)["attrs"]
    assert attrs["content"] == "Could you bring some water?"
    assert attrs["raw_data"] == raw
    assert attrs["raw_understanding"]["status"] == "not_understood"
    received = game._context("Ada").observations["heard_utterances"][-1]
    assert received["text"] == attrs["content"]
    assert received["raw_data"] == raw
    assert received["raw_understanding"]["status"] == "not_understood"
