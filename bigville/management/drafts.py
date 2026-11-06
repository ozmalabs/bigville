"""Shared draft resolver and disposable, deterministic scenario preview."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..api import create_world
from ..scenarios import list_scenarios, load_scenario
from .catalog import _scenario_entry, build_capability_catalog

ALLOWED_FIELDS = {
    "scenario_id", "name", "seed", "autonomous", "default_backend",
    "ticks_per_period", "turn_limit",
}
MAX_NAME_LENGTH = 80
MAX_TURN_LIMIT = 1_000_000
MAX_SEED_ABS = (1 << 53) - 1
MAX_MAP_EDGE = 40
MAX_ACTORS = 200
MAX_PREVIEW_BYTES = 1_000_000


class PreviewTooLarge(ValueError):
    """The bounded preview would exceed the configured response size."""


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_draft(payload: Any) -> dict[str, Any]:
    """Validate and normalize a request without building a world or run."""
    errors: dict[str, str] = {}
    if not isinstance(payload, dict):
        payload = {}
        errors["draft"] = "Expected a JSON object."
    unknown = sorted(str(key) for key in set(payload) - ALLOWED_FIELDS)
    for key in unknown:
        errors[key] = "Unknown field."

    scenario_id = payload.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id:
        errors["scenario_id"] = "Choose a scenario ID."
    elif scenario_id != "town100":
        try:
            if scenario_id not in list_scenarios():
                raise FileNotFoundError(scenario_id)
            definition = load_scenario(scenario_id)
            if definition.id != scenario_id:
                errors["scenario_id"] = "Use a discoverable scenario ID, not a path or alias."
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            errors["scenario_id"] = "Scenario ID is not available in this checkout."

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        errors["name"] = "Name is required."
    elif len(name.strip()) > MAX_NAME_LENGTH:
        errors["name"] = f"Name must be at most {MAX_NAME_LENGTH} characters."
    else:
        name = name.strip()

    seed = payload.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        errors["seed"] = "Seed must be an explicit nonnegative integer."
    elif seed < 0 or seed > MAX_SEED_ABS:
        errors["seed"] = f"Seed must be a nonnegative integer no greater than {MAX_SEED_ABS}."

    if payload.get("autonomous") is not True:
        errors["autonomous"] = "Only autonomous runs are supported in this phase."

    backend = payload.get("default_backend", "simple")
    if not isinstance(backend, str) or backend not in {"simple", "cheap"}:
        errors["default_backend"] = "Only the simple backend is supported in this phase."
    else:
        backend = "simple"

    cadence = payload.get("ticks_per_period", "world")
    if cadence != "world" and cadence is not None and (
            isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < 1):
        errors["ticks_per_period"] = "Use 'world', null, or a positive integer."

    turn_limit = payload.get("turn_limit")
    if turn_limit is not None and (
            isinstance(turn_limit, bool) or not isinstance(turn_limit, int) or
            turn_limit < 1 or turn_limit > MAX_TURN_LIMIT):
        errors["turn_limit"] = f"Turn limit must be an integer from 1 to {MAX_TURN_LIMIT}."

    actor_overrides: list[dict[str, str]] = []
    if isinstance(scenario_id, str) and scenario_id and "scenario_id" not in errors:
        try:
            if scenario_id != "town100" and scenario_id not in list_scenarios():
                raise FileNotFoundError(scenario_id)
            definition = load_scenario(scenario_id)
            for actor in definition.actors:
                actor_backend = actor.get("backend")
                if actor_backend is None:
                    continue
                if not isinstance(actor_backend, str) or actor_backend not in {"simple", "cheap"}:
                    actor_name = str(actor.get("name", "(unnamed actor)"))
                    errors["scenario_id"] = (
                        f"Scenario actor {actor_name!r} selects unsupported backend "
                        f"{actor_backend!r}; only simple is available in this phase.")
                    break
                actor_overrides.append({
                    "actor": str(actor.get("name", "(unnamed actor)")), "backend": "simple",
                    "source": "scenario_override",
                })
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    if isinstance(scenario_id, str) and scenario_id and "scenario_id" not in errors:
        try:
            scenario_data = load_scenario(scenario_id).to_dict()
            from worlds.bigville_world import BigvilleWorld
            supported = set(BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS)
            configured = scenario_data.get("physical_subsystems", {})
            if not isinstance(configured, dict):
                errors["scenario_id"] = "Scenario physical_subsystems must be an object."
            else:
                unknown_subsystems = sorted(set(configured) - supported)
                invalid_values = sorted(name for name, value in configured.items()
                                        if not isinstance(value, bool))
                if unknown_subsystems:
                    errors["scenario_id"] = (
                        "Scenario uses unsupported physical subsystems: "
                        + ", ".join(map(str, unknown_subsystems)) + ".")
                elif invalid_values:
                    errors["scenario_id"] = (
                        "Scenario physical subsystem values must be booleans: "
                        + ", ".join(invalid_values) + ".")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    catalog = build_capability_catalog()
    capability_revision = catalog["revision"]
    warnings = []
    if actor_overrides:
        warnings.append("Authored scenario backend overrides take precedence over the default backend.")

    normalized = None
    canonical_config = None
    configuration_hash = None
    if not errors:
        scenario_entry = _scenario_entry(scenario_id)
        normalized = {
            "schema_version": 1,
            "name": name,
            "scenario_id": scenario_id,
            "seed": seed,
            "autonomous": True,
            "default_backend": backend,
            "ticks_per_period": cadence,
            "turn_limit": turn_limit,
            "scenario_source": scenario_entry["source"],
            "scenario_content_hash": scenario_entry["content_hash"],
            "actor_backend_overrides": actor_overrides,
            "physical_subsystems": scenario_entry["physical_subsystems"],
            "capability_revision": capability_revision,
            "engine_build": catalog["engine_build"],
        }
        canonical_config = {key: value for key, value in normalized.items()
                            if key != "capability_revision"}
        configuration_hash = _hash(canonical_config)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "capability_revision": capability_revision,
        "normalized": normalized,
        "configuration_hash": configuration_hash,
        "canonical_config": canonical_config,
    }


def preview_draft(payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (preview, resolution); preview is absent when the draft is invalid."""
    resolution = resolve_draft(payload)
    if not resolution["valid"]:
        return None, resolution
    config = resolution["normalized"]
    world = create_world(scenario=config["scenario_id"], seed=config["seed"],
                         autonomous_actors=False)
    grid = world._map_grid or []
    from worlds.bigville_sim_world import TILE_NAME
    full_width = max((len(row) for row in grid), default=0)
    full_height = len(grid)
    tile_counts: dict[str, int] = {}
    for row in grid:
        for tile in row:
            terrain = TILE_NAME.get(tile, f"tile_{tile}")
            tile_counts[terrain] = tile_counts.get(terrain, 0) + 1
    preview_grid = [
        [TILE_NAME.get(tile, f"tile_{tile}") for tile in row[:MAX_MAP_EDGE]]
        for row in grid[:MAX_MAP_EDGE]
    ]
    cast = []
    for actor in sorted(world._actors):
        position = world.actor_position(actor)
        actor_node = world.eng.node(world._actors[actor])
        attrs = actor_node.get("attrs", {})
        overridden = getattr(world, "_scenario_actor_backends", {}).get(actor)
        cast.append({
            "name": actor,
            "role": attrs.get("role"),
            "backend": "simple" if overridden in {"simple", "cheap"} else config["default_backend"],
            "backend_source": "scenario_override" if overridden else "default",
            "position": list(position) if position is not None else None,
        })
    full_cast_count = len(cast)
    result = {
        "schema_version": 1,
        "configuration_hash": resolution["configuration_hash"],
        "canonical_config": resolution["canonical_config"],
        "capability_revision": resolution["capability_revision"],
        "map": {
            "available": bool(grid), "width": full_width, "height": full_height,
            "tile_counts": tile_counts, "grid": preview_grid,
            "truncated": full_width > MAX_MAP_EDGE or full_height > MAX_MAP_EDGE,
        },
        "cast": {"count": full_cast_count, "actors": cast[:MAX_ACTORS],
                 "truncated": full_cast_count > MAX_ACTORS},
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_PREVIEW_BYTES:
        raise PreviewTooLarge("Preview response exceeds the 1 MB response limit.")
    return result, resolution
