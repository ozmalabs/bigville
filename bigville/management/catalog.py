"""Capability discovery derived from the checked-out Bigville implementation."""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

from ..scenarios import SCENARIO_ROOT, load_scenario, list_scenarios

_SUBSYSTEM_DESCRIPTIONS = {
    "metabolism": "Resident hunger, thirst, rest, and related body needs.",
    "ecology": "Ecological growth and resource recovery over time.",
    "decay": "Physical decay of stored or built materials over time.",
    "practice": "Consolidation of physical skills from completed work.",
    "cognitive_practice": "Consolidation of cognitive skills from completed work.",
    "loudness": "Speech loudness affects how far a resident can be heard.",
    "training": "Physical effort trains strength and stamina.",
    "illness": "Illness onset and course, including medical care affordances.",
}


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
    source_digest = hashlib.sha256()
    source_files = []
    for relative_dir, suffixes in (("bigville", {".py"}), ("worlds", {".py"}),
                                   ("domains", {".py"}), ("packs", {".json"}),
                                   ("seeds", {".json"})):
        directory = root / relative_dir
        if directory.is_dir():
            source_files.extend(path for path in directory.rglob("*")
                                if path.is_file() and path.suffix in suffixes)
    for path in sorted(source_files):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        source_digest.update(len(relative).to_bytes(4, "big"))
        source_digest.update(relative)
        content = path.read_bytes()
        source_digest.update(len(content).to_bytes(8, "big"))
        source_digest.update(content)
    return {"package_version": package_version, "git_commit": commit or None,
            "engine_source_hash": source_digest.hexdigest() if source_files else None}


def _scenario_entry(identifier: str) -> dict[str, Any]:
    if identifier == "town100":
        from worlds.bigville_world import BigvilleWorld
        defaults = dict(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
        return {
            "id": identifier, "name": "Town 100", "source": "built_in",
            "type": "village", "content_hash": None,
            "content_hash_reason": "Built-in town100 pack identity is not exposed by the engine.",
            "physical_subsystems": defaults,
            "physical_subsystem_sources": {name: "engine_default" for name in defaults},
        }

    definition = load_scenario(identifier)
    data = definition.to_dict()
    from worlds.bigville_world import BigvilleWorld
    defaults = dict(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
    overrides = data.get("physical_subsystems", {})
    effective = {**defaults, **overrides} if isinstance(overrides, dict) else defaults
    override_names = set(overrides) if isinstance(overrides, dict) else set()
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
        "physical_subsystem_sources": {
            name: "scenario_override" if name in override_names else "engine_default"
            for name in defaults
        },
        "actors": [{"name": str(actor.get("name", "")),
                    "scenario_backend": actor.get("backend")}
                   for actor in definition.actors],
        "cast_generation": (dict(data["management_cast_generation"])
                            if isinstance(data.get("management_cast_generation"), dict)
                            else None),
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
    subsystem_catalog = [
        {"name": name, "default": enabled,
         "description": _SUBSYSTEM_DESCRIPTIONS.get(name, "Engine-defined physical subsystem.")}
        for name, enabled in defaults.items()
    ]
    backends = _backend_catalog()
    return {
        "schema_version": 1,
        "revision": _canonical_hash({"scenarios": scenarios,
                                    "subsystems": subsystem_catalog,
                                    "backends": backends,
                                    "engine_build": (engine_build := _build_identity())}),
        "engine_build": engine_build,
        "scenarios": scenarios,
        "physical_subsystems": subsystem_catalog,
        "backends": backends,
    }
