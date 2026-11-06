"""Capability discovery derived from the checked-out Bigville implementation."""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

from ..scenarios import SCENARIO_ROOT, load_scenario, list_scenarios


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _build_identity() -> dict[str, str | None]:
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    try:
        from importlib.metadata import version
        package_version = version("bigville")
    except Exception:
        package_version = None
    return {"package_version": package_version, "git_commit": commit or None}


def _scenario_entry(identifier: str) -> dict[str, Any]:
    if identifier == "town100":
        from worlds.bigville_world import BigvilleWorld
        defaults = dict(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
        return {
            "id": identifier, "name": "Town 100", "source": "built_in",
            "type": "village", "content_hash": None,
            "content_hash_reason": "Built-in town100 pack identity is not exposed by the engine.",
            "physical_subsystems": defaults,
        }

    definition = load_scenario(identifier)
    data = definition.to_dict()
    from worlds.bigville_world import BigvilleWorld
    defaults = dict(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
    overrides = data.get("physical_subsystems", {})
    effective = {**defaults, **overrides} if isinstance(overrides, dict) else defaults
    source_path = (SCENARIO_ROOT / f"{identifier}.json").resolve()
    try:
        source = source_path.relative_to(SCENARIO_ROOT.resolve()).as_posix()
    except ValueError:
        source = "authored"
    scenario_type = data.get("type")
    if scenario_type is None:
        scenario_type = "tabletop" if any(
            item.get("kind") == "board_game"
            for item in data.get("map", {}).get("affordances", [])
            if isinstance(item, dict)
        ) else "authored_world"
    return {
        "id": definition.id, "name": definition.name, "source": "authored",
        "source_file": source,
        "type": str(scenario_type),
        "content_hash": _canonical_hash(data),
        "content_hash_reason": None,
        "physical_subsystems": effective,
    }


def _backend_catalog() -> list[dict[str, Any]]:
    backends = [{"kind": "simple", "available": True, "reason": None},
                {"kind": "human", "available": True, "reason": None}]
    try:
        from ..backends.ocelot import ocelot_resident_class
        ocelot_resident_class()
    except Exception as exc:
        backends.append({"kind": "ocelot", "available": False,
                         "reason": str(exc)})
    else:
        backends.append({"kind": "ocelot", "available": True, "reason": None})
    backends.append({"kind": "llm", "available": False,
                     "reason": "No server-side LLM provider is configured."})
    return backends


def build_capability_catalog() -> dict[str, Any]:
    """Return a fresh, JSON-safe catalog without creating a world or provider."""
    scenarios = [_scenario_entry("town100")]
    scenarios.extend(_scenario_entry(identifier) for identifier in list_scenarios())
    from worlds.bigville_world import BigvilleWorld
    defaults = dict(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
    backends = _backend_catalog()
    return {
        "schema_version": 1,
        "revision": _canonical_hash({"scenarios": scenarios,
                                    "subsystems": defaults,
                                    "backends": backends}),
        "engine_build": _build_identity(),
        "scenarios": scenarios,
        "physical_subsystems": [
            {"name": name, "default": enabled}
            for name, enabled in defaults.items()
        ],
        "backends": backends,
    }
