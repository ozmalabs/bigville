"""Shared draft resolver and disposable, deterministic scenario preview."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..api import create_world
from ..scenarios import list_scenarios, load_scenario
from .catalog import _scenario_entry, build_capability_catalog
from .cast_generation import generate_cast

ALLOWED_FIELDS = {
    "scenario_id", "name", "seed", "autonomous", "default_backend",
    "ticks_per_period", "turn_limit",
}
OPTIONAL_PROFILE_FIELDS = {"default_profile_id", "actor_backend_profiles"}
OPTIONAL_CAST_FIELDS = {"cast_generation"}
DRAFT_FIELDS = ALLOWED_FIELDS | OPTIONAL_PROFILE_FIELDS | OPTIONAL_CAST_FIELDS
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


def resolve_draft(payload: Any, *, profile_registry=None) -> dict[str, Any]:
    """Validate and normalize a request without building a world or run."""
    errors: dict[str, str] = {}
    if not isinstance(payload, dict):
        payload = {}
        errors["draft"] = "Expected a JSON object."
    unknown = sorted(str(key) for key in set(payload) - DRAFT_FIELDS)
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

    if profile_registry is None:
        from .profiles import BackendProfileRegistry
        profile_catalog = BackendProfileRegistry().public_profiles()
    else:
        profile_catalog = profile_registry.public_profiles()
    profiles = {item["id"]: item for item in profile_catalog["profiles"]}
    requested_backend = payload.get("default_backend", "simple")
    if not isinstance(requested_backend, str):
        errors["default_backend"] = "Choose a backend kind from an available profile."
        requested_backend = ""
    if requested_backend == "cheap":
        requested_backend = "simple"
    requested_profile = payload.get("default_profile_id")
    if requested_profile is not None and not isinstance(requested_profile, str):
        errors["default_profile_id"] = "Profile ID must be a string from the server profile list."
        requested_profile = None
    if requested_profile is None:
        if requested_backend not in {"simple", "ocelot", "llm"}:
            errors["default_backend"] = "Only the simple backend is supported unless an available server-configured profile is selected."
            default_profile = None
        else:
            choices = [item for item in profile_catalog["profiles"]
                       if item["kind"] == requested_backend and item["available"]]
            if requested_backend == "simple":
                choices = [item for item in choices if item["id"] == "simple.default"]
            default_profile = choices[0] if len(choices) == 1 else None
            if default_profile is None:
                errors["default_backend"] = "Only the simple backend is supported unless an available server-configured profile is selected."
    else:
        default_profile = profiles.get(requested_profile)
        if default_profile is None:
            errors["default_profile_id"] = "Choose a listed backend profile."
        elif not default_profile["available"]:
            errors["default_profile_id"] = default_profile["reason"] or "This profile is unavailable."
        elif requested_backend not in {"simple", "cheap", default_profile["kind"]}:
            errors["default_backend"] = "Backend kind does not match the selected profile."
    backend = default_profile["kind"] if default_profile else "simple"

    cadence = payload.get("ticks_per_period", "world")
    if cadence != "world" and cadence is not None and (
            isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < 1):
        errors["ticks_per_period"] = "Use 'world', null, or a positive integer."

    turn_limit = payload.get("turn_limit")
    if turn_limit is not None and (
            isinstance(turn_limit, bool) or not isinstance(turn_limit, int) or
            turn_limit < 1 or turn_limit > MAX_TURN_LIMIT):
        errors["turn_limit"] = f"Turn limit must be an integer from 1 to {MAX_TURN_LIMIT}."

    cast_generation_result = None
    if "cast_generation" in payload:
        if scenario_id == "town100":
            errors["cast_generation"] = "Generated casts are not supported for built-in town100."
        elif "scenario_id" not in errors:
            try:
                scenario_definition = load_scenario(scenario_id)
                scenario_entry_for_cast = _scenario_entry(scenario_id)
                cast_generation_result = generate_cast(
                    scenario_definition.to_dict(), payload["cast_generation"], seed=seed,
                    scenario_hash=scenario_entry_for_cast["content_hash"], profiles=profiles,
                    default_profile_id=default_profile["id"] if default_profile else "simple.default",
                )
                errors.update(cast_generation_result.get("errors", {}))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                errors["cast_generation"] = "Scenario does not provide a valid generated-cast contract."

    actor_overrides: list[dict[str, str]] = []
    actor_backend_profiles = payload.get("actor_backend_profiles", {})
    if not isinstance(actor_backend_profiles, dict):
        errors["actor_backend_profiles"] = "Actor profile assignments must be an object keyed by authored actor name."
        actor_backend_profiles = {}
    elif any(not isinstance(actor, str) or not isinstance(profile, str)
             for actor, profile in actor_backend_profiles.items()):
        errors["actor_backend_profiles"] = "Actor names and profile IDs must be strings."
        actor_backend_profiles = {}
    if scenario_id == "town100" and actor_backend_profiles:
        errors["actor_backend_profiles"] = "Per-actor profile overrides are not supported for built-in town100."

    definition = None
    if isinstance(scenario_id, str) and scenario_id and "scenario_id" not in errors:
        try:
            if scenario_id != "town100":
                definition = load_scenario(scenario_id)
            actors = definition.actors if definition else []
            generated_cast = cast_generation_result.get("actors", []) if cast_generation_result else []
            generated_profiles = cast_generation_result.get("profiles", {}) if cast_generation_result else {}
            actor_names = {str(actor.get("name", "")) for actor in actors + generated_cast}
            authored_actor_names = {str(actor.get("name", "")) for actor in actors}
            for unknown_actor in sorted(set(actor_backend_profiles) - actor_names):
                errors[f"actor_backend_profiles.{unknown_actor}"] = "Actor is not present in this authored scenario."
            scenario_profile_ids = {}
            scenario_kinds = {}
            for actor in actors:
                actor_backend = actor.get("backend")
                if actor_backend is None:
                    continue
                actor_name = str(actor.get("name", "(unnamed actor)"))
                # An explicit actor profile wins before scenario profile readiness is checked.
                if actor_name in actor_backend_profiles:
                    continue
                kind = "simple" if actor_backend == "cheap" else actor_backend
                candidates = [item for item in profile_catalog["profiles"]
                              if item["kind"] == kind and item["available"]]
                if kind == "simple":
                    candidates = [item for item in candidates if item["id"] == "simple.default"]
                if not isinstance(kind, str) or len(candidates) != 1:
                    errors["scenario_id"] = (
                        f"Scenario actor {actor_name!r} selects backend {actor_backend!r}, "
                        "which has no unique available server profile.")
                    continue
                scenario_profile_ids[actor_name] = candidates[0]["id"]
                scenario_kinds[actor_name] = kind
                actor_overrides.append({"actor": actor_name, "backend": kind,
                                        "source": "scenario_override"})
            for actor_name, profile_id in actor_backend_profiles.items():
                profile = profiles.get(profile_id)
                if profile is None:
                    errors[f"actor_backend_profiles.{actor_name}"] = "Choose a listed backend profile."
                elif not profile["available"]:
                    errors[f"actor_backend_profiles.{actor_name}"] = profile["reason"] or "This profile is unavailable."
            resolved_actor_profiles = []
            for actor_name in sorted(actor_names):
                if actor_name in actor_backend_profiles:
                    profile = profiles.get(actor_backend_profiles[actor_name])
                    source = "user_override"
                elif actor_name in generated_profiles:
                    profile = profiles.get(generated_profiles[actor_name])
                    source = "cast_group"
                elif actor_name in scenario_profile_ids:
                    profile = profiles.get(scenario_profile_ids[actor_name])
                    source = "scenario_override"
                else:
                    profile = default_profile
                    source = "default"
                if profile:
                    resolved_actor_profiles.append({
                        "actor": actor_name, "profile_id": profile["id"],
                        "profile_revision": profile["revision"], "backend": profile["kind"],
                        "source": source,
                    })
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            definition = None
            resolved_actor_profiles = []
    else:
        resolved_actor_profiles = []

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
    capability_revision = _hash({"capabilities": catalog["revision"],
                                  "backend_profiles": profile_catalog["revision"]})
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
            "default_profile_id": default_profile["id"] if default_profile else "simple.default",
            "default_profile_revision": default_profile["revision"] if default_profile else "unknown",
            "actor_backend_profiles": dict(sorted(actor_backend_profiles.items())),
            "resolved_actor_profiles": resolved_actor_profiles,
            "backend_profiles_revision": profile_catalog["revision"],
            "ticks_per_period": cadence,
            "turn_limit": turn_limit,
            "scenario_source": scenario_entry["source"],
            "scenario_content_hash": scenario_entry["content_hash"],
            "actor_backend_overrides": actor_overrides,
            "physical_subsystems": scenario_entry["physical_subsystems"],
            "capability_revision": capability_revision,
            "engine_build": catalog["engine_build"],
        }
        if cast_generation_result is not None:
            normalized.update({
                "cast_generation": {"schema_version": cast_generation_result["generator_version"],
                                    "groups": cast_generation_result["groups"]},
                "cast_generation_version": cast_generation_result["generator_version"],
                "generated_cast": cast_generation_result["actors"],
                "cast_group_profiles": cast_generation_result["profiles"],
                "cast_generation_hash": cast_generation_result["generator_hash"],
            })
        canonical_config = {key: value for key, value in normalized.items()
                            if key != "capability_revision"}
        configuration_hash = _hash(canonical_config)
    template_draft = {}
    if normalized is not None:
        for key in ALLOWED_FIELDS:
            template_draft[key] = normalized[key]
        if "default_profile_id" in payload:
            template_draft["default_profile_id"] = normalized["default_profile_id"]
        if "actor_backend_profiles" in payload:
            template_draft["actor_backend_profiles"] = normalized["actor_backend_profiles"]
        if "cast_generation" in payload:
            template_draft["cast_generation"] = normalized["cast_generation"]
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "capability_revision": capability_revision,
        "normalized": normalized,
        "configuration_hash": configuration_hash,
        "canonical_config": canonical_config,
        "template_draft": template_draft,
    }


def preview_draft(payload: Any, *, profile_registry=None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (preview, resolution); preview is absent when the draft is invalid."""
    resolution = resolve_draft(payload, profile_registry=profile_registry)
    if not resolution["valid"]:
        return None, resolution
    config = resolution["normalized"]
    from .cast_generation import materialize_scenario
    scenario = materialize_scenario(config["scenario_id"], config, profile_registry)
    world = create_world(scenario=scenario, seed=config["seed"],
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
        assignment = next((item for item in config["resolved_actor_profiles"]
                           if item["actor"] == actor), None)
        cast.append({
            "name": actor,
            "role": attrs.get("role"),
            "backend": assignment["backend"] if assignment else config["default_backend"],
            "backend_source": assignment["source"] if assignment else "default",
            "position": list(position) if position is not None else None,
        })
    full_cast_count = len(cast)
    cast_summary = {"count": full_cast_count, "actors": cast[:MAX_ACTORS],
                    "truncated": full_cast_count > MAX_ACTORS}
    if "cast_generation_version" in config:
        cast_summary["groups"] = [
            {"id": group["id"], "role": group["role"], "count": group["count"],
             "backend_profile_id": group["backend_profile_id"],
             "actors": [actor["name"] for actor in config["generated_cast"]
                        if actor.get("group") == group["id"]]}
            for group in config["cast_generation"]["groups"]]
        cast_summary["generation"] = {"version": config["cast_generation_version"],
                                       "hash": config["cast_generation_hash"]}
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
        "cast": cast_summary,
        "profile_assignments": config["resolved_actor_profiles"],
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_PREVIEW_BYTES:
        raise PreviewTooLarge("Preview response exceeds the 1 MB response limit.")
    return result, resolution
