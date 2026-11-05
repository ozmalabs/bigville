"""Data-driven scenario definitions for arbitrary Bigville experiments.

The canonical village is one scenario.  Small experiments can provide the
same world boundary with a compact map, selected places, actors, seed manifests
and initial state without importing a second simulation implementation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIO_ROOT = Path(__file__).resolve().parent.parent / "scenarios"


@dataclass(frozen=True)
class ScenarioDefinition:
    """Validated-enough, JSON-friendly scenario data.

    The contents intentionally remain open-ended.  The world consumes the
    common construction fields and preserves the rest as scenario metadata for
    experiment-specific readers.
    """

    id: str
    name: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)

    @property
    def actors(self) -> list[dict[str, Any]]:
        return [dict(actor) for actor in self.data.get("actors", [])]


def _definition(value: dict[str, Any], *, fallback_id="custom") -> ScenarioDefinition:
    if not isinstance(value, dict):
        raise TypeError("scenario must be a mapping, path, or scenario id")
    data = dict(value)
    identifier = str(data.get("id", fallback_id))
    data["id"] = identifier
    data.setdefault("name", identifier.replace("_", " ").title())
    data.setdefault("actors", [])
    data.setdefault("map", {})
    return ScenarioDefinition(identifier, str(data["name"]), data)


def _expand_text_files(value: Any, base: Path) -> Any:
    """Resolve authored text assets without giving the world their semantics."""
    if isinstance(value, list):
        return [_expand_text_files(item, base) for item in value]
    if not isinstance(value, dict):
        return value
    expanded = {key: _expand_text_files(child, base)
                for key, child in value.items()}
    text_file = expanded.get("text_file")
    if text_file and "text" not in expanded:
        path = (base / str(text_file)).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"scenario text asset not found: {text_file}")
        expanded["text"] = path.read_text(encoding="utf-8")
    return expanded


def load_scenario(value: str | Path | dict[str, Any] | ScenarioDefinition) -> ScenarioDefinition:
    """Load an inline definition, JSON file, or file from ``scenarios/``."""
    if isinstance(value, ScenarioDefinition):
        return value
    if isinstance(value, dict):
        return _definition(value)
    candidate = Path(value)
    if not candidate.exists():
        candidate = SCENARIO_ROOT / f"{candidate}.json"
    if not candidate.is_file():
        raise FileNotFoundError(f"scenario not found: {value}")
    data = _expand_text_files(json.loads(candidate.read_text(encoding="utf-8")),
                              candidate.parent)
    return _definition(data, fallback_id=candidate.stem)


def list_scenarios() -> list[str]:
    return sorted(path.stem for path in SCENARIO_ROOT.glob("*.json"))
