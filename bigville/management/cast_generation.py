"""Versioned, deterministic cast generation for opted-in authored scenarios."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
from typing import Any


GENERATOR_VERSION = 1
MAX_GENERATED_ACTORS = 100
MAX_TOTAL_ACTORS = 200
GROUP_ID = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
TRAIT_BOUNDS = {
    "age": (0.0, 120.0),
    "skill": (0.0, 1.0),
    "literacy": (0.0, 1.0),
    "capability": (0.0, 1.0),
    "learn": (0.0, 1.0),
}
ACTOR_FIELDS = {"name", "role", "backend", "home_cell", "group", "age", "skill",
                "literacy", "capability", "learn"}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _feature(scenario_data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    feature = scenario_data.get("management_cast_generation")
    if not isinstance(feature, dict):
        return None, "This scenario does not declare support for generated casts."
    if (feature.get("schema_version") != GENERATOR_VERSION or
            not isinstance(feature.get("roles"), list) or
            any(not isinstance(role, str) or not role.strip() for role in feature["roles"])):
        return None, "Scenario cast generation capability metadata is invalid or unsupported."
    maximum = feature.get("max_generated")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_GENERATED_ACTORS:
        return None, "Scenario cast generation capacity must be between 1 and 100."
    return feature, None


def _home_cells(scenario_data: dict[str, Any]) -> tuple[list[list[int]], str | None]:
    map_data = scenario_data.get("map")
    grid = map_data.get("grid") if isinstance(map_data, dict) else None
    layout = map_data.get("layout", {}) if isinstance(map_data, dict) else {}
    homes = layout.get("homes") if isinstance(layout, dict) else None
    if not isinstance(grid, list) or not grid or not isinstance(homes, list):
        return [], "Generated actors require an authored map with listed home cells."
    height = len(grid)
    width = len(grid[0]) if isinstance(grid[0], list) else 0
    if not width or any(not isinstance(row, list) or len(row) != width for row in grid):
        return [], "Scenario map must be a non-empty rectangular grid."
    terrain_codes = {"grass": 0, "path": 1, "wall": 2, "floor": 3,
                     "square": 4, "tree": 5, "water": 6}
    solids = {2, 5, 6}
    cells: list[list[int]] = []
    for raw in homes:
        if (not isinstance(raw, (list, tuple)) or len(raw) != 2 or
                any(isinstance(value, bool) or not isinstance(value, int) for value in raw)):
            return [], "Every scenario home cell must be an integer [x, y] coordinate."
        x, y = raw
        if x < 0 or y < 0 or x >= width or y >= height:
            return [], "Scenario home cell is outside the map bounds."
        tile = grid[y][x]
        if isinstance(tile, str):
            if tile not in terrain_codes:
                return [], f"Unknown scenario terrain {tile!r} at a generated home cell."
            tile = terrain_codes[tile]
        if isinstance(tile, bool) or not isinstance(tile, int) or not 0 <= tile <= 6:
            return [], "Scenario home cell uses an unknown terrain code."
        if tile in solids:
            return [], "Generated actors require walkable scenario home cells."
        cell = [x, y]
        if cell not in cells:
            cells.append(cell)
    return cells, None


def _generated_seed(seed: int, scenario_hash: str, group: str,
                    ordinal: int, trait: str) -> int:
    payload = f"cast-generator:{GENERATOR_VERSION}:{seed}:{scenario_hash}:{group}:{ordinal}:{trait}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def _validated_range(value: Any, trait: str) -> tuple[float, float] | None:
    if not isinstance(value, dict) or set(value) != {"min", "max"}:
        return None
    low, high = value["min"], value["max"]
    if (isinstance(low, bool) or isinstance(high, bool) or
            not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or
            not math.isfinite(low) or not math.isfinite(high)):
        return None
    minimum, maximum = TRAIT_BOUNDS[trait]
    if low < minimum or high > maximum or low > high:
        return None
    return float(low), float(high)


def generate_cast(scenario_data: dict[str, Any], request: Any, *, seed: int,
                  scenario_hash: str, profiles: dict[str, dict[str, Any]],
                  default_profile_id: str) -> dict[str, Any]:
    """Return normalized generation, deterministic actors, and field errors."""
    errors: dict[str, str] = {}
    feature, feature_error = _feature(scenario_data)
    if feature_error:
        return {"errors": {"cast_generation": feature_error}}
    if not isinstance(request, dict) or set(request) != {"schema_version", "groups"}:
        return {"errors": {"cast_generation": "Use schema_version and groups only."}}
    if request.get("schema_version") != GENERATOR_VERSION:
        return {"errors": {"cast_generation.schema_version": "Only cast generation schema version 1 is supported."}}
    groups = request.get("groups")
    if not isinstance(groups, list) or not groups or len(groups) > 20:
        return {"errors": {"cast_generation.groups": "Provide 1 to 20 cast groups."}}
    allowed_roles = set(feature["roles"])
    max_generated = min(feature["max_generated"], MAX_GENERATED_ACTORS)
    normalized_groups = []
    seen_group_ids: set[str] = set()
    total = 0
    for index, group in enumerate(groups):
        path = f"cast_generation.groups.{index}"
        if not isinstance(group, dict) or set(group) - {"id", "count", "role", "backend_profile_id", "traits"}:
            errors[path] = "Group fields are id, count, role, backend_profile_id, and traits."
            continue
        group_id, count, role = group.get("id"), group.get("count"), group.get("role")
        if not isinstance(group_id, str) or not GROUP_ID.fullmatch(group_id):
            errors[f"{path}.id"] = "Use a lowercase group ID of at most 24 letters, digits, underscores, or hyphens."
        elif group_id in seen_group_ids:
            errors[f"{path}.id"] = "Group IDs must be unique."
        else:
            seen_group_ids.add(group_id)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= max_generated:
            errors[f"{path}.count"] = f"Group count must be from 1 to {max_generated}."
        else:
            total += count
        if not isinstance(role, str) or role not in allowed_roles:
            errors[f"{path}.role"] = "Choose a role declared by this scenario."
        profile_id = group.get("backend_profile_id", default_profile_id)
        if not isinstance(profile_id, str) or profile_id not in profiles:
            errors[f"{path}.backend_profile_id"] = "Choose a server backend profile."
        elif not profiles[profile_id]["available"]:
            errors[f"{path}.backend_profile_id"] = profiles[profile_id].get("reason") or "Backend profile is unavailable."
        traits = group.get("traits", {})
        if not isinstance(traits, dict) or set(traits) - set(TRAIT_BOUNDS):
            errors[f"{path}.traits"] = "Traits may contain only age, skill, literacy, capability, and learn ranges."
            traits = {}
        normalized_traits = {}
        for trait, value in traits.items():
            valid = _validated_range(value, trait)
            if valid is None:
                errors[f"{path}.traits.{trait}"] = (
                    f"Use a finite min/max range within {TRAIT_BOUNDS[trait][0]} and {TRAIT_BOUNDS[trait][1]}.")
            else:
                normalized_traits[trait] = {"min": valid[0], "max": valid[1]}
        normalized_groups.append({"id": group_id, "count": count, "role": role,
                                  "backend_profile_id": profile_id,
                                  "traits": normalized_traits})
    if total > max_generated:
        errors["cast_generation.groups"] = f"Generated cast total cannot exceed scenario capacity {max_generated}."
    actor_data = scenario_data.get("actors", [])
    if not isinstance(actor_data, list) or len(actor_data) + total > MAX_TOTAL_ACTORS:
        errors["cast_generation.groups"] = f"Total cast cannot exceed {MAX_TOTAL_ACTORS} actors."
        actor_data = actor_data if isinstance(actor_data, list) else []
    map_data = scenario_data.get("map") if isinstance(scenario_data.get("map"), dict) else {}
    grid = map_data.get("grid") if isinstance(map_data.get("grid"), list) else []
    height = len(grid)
    width = len(grid[0]) if grid and isinstance(grid[0], list) else 0
    grid_valid = bool(width) and all(isinstance(row, list) and len(row) == width for row in grid)
    if not grid_valid:
        errors["cast_generation"] = "Generated cast scenarios need a non-empty rectangular map."
    terrain_codes = {"grass": 0, "path": 1, "wall": 2, "floor": 3,
                     "square": 4, "tree": 5, "water": 6}
    names = []
    for index, actor in enumerate(actor_data):
        path = f"cast_generation.authored_actors.{index}"
        if not isinstance(actor, dict):
            errors[path] = "Scenario actor definitions must be objects."
            continue
        actor_name = actor.get("name")
        if not isinstance(actor_name, str) or not actor_name.strip():
            errors[f"{path}.name"] = "Authored actors need a non-empty string name."
        else:
            names.append(actor_name)
        home = actor.get("home_cell")
        if home is None:
            continue
        if (not isinstance(home, (list, tuple)) or len(home) != 2 or
                any(isinstance(value, bool) or not isinstance(value, int) for value in home)):
            errors[f"{path}.home_cell"] = "Authored home cells must be integer [x, y] coordinates."
            continue
        x, y = home
        if not grid_valid or x < 0 or y < 0 or x >= width or y >= height:
            errors[f"{path}.home_cell"] = "Authored home cell is outside the map bounds."
            continue
        tile = grid[y][x]
        if isinstance(tile, str):
            if tile not in terrain_codes:
                errors[f"{path}.home_cell"] = "Authored home cell uses unknown terrain."
                continue
            tile = terrain_codes[tile]
        if (isinstance(tile, bool) or not isinstance(tile, int) or
                not 0 <= tile <= 6 or tile in {2, 5, 6}):
            errors[f"{path}.home_cell"] = "Authored home cell must be on walkable known terrain."
    if len(set(names)) != len(names):
        errors["cast_generation.authored_actors"] = "Authored actor names must be unique when generated casts are enabled."
    name_set = set(names)
    for group in normalized_groups:
        if not isinstance(group.get("id"), str) or not isinstance(group.get("count"), int):
            continue
        for ordinal in range(1, group["count"] + 1):
            name = f"{group['id']}-{ordinal:03d}"
            if name in name_set:
                errors[f"cast_generation.groups.{group['id']}.id"] = f"Generated actor name {name!r} already exists."
            name_set.add(name)
    home_cells, home_error = _home_cells(scenario_data)
    if home_error:
        errors["cast_generation"] = home_error
    else:
        homes = (scenario_data.get("map") or {}).get("layout", {}).get("homes", [])
        reserved = set()
        implicit_index = 0
        for actor in actor_data:
            if not isinstance(actor, dict):
                continue
            home = actor.get("home_cell")
            if home is None:
                if homes:
                    allocated = homes[implicit_index % len(homes)]
                    implicit_index += 1
                    try:
                        reserved.add((int(allocated[0]), int(allocated[1])))
                    except (TypeError, ValueError, IndexError):
                        pass
            elif isinstance(home, (list, tuple)) and len(home) == 2:
                try:
                    reserved.add((int(home[0]), int(home[1])))
                except (TypeError, ValueError):
                    pass
        available_homes = [cell for cell in home_cells if tuple(cell) not in reserved]
        if total > len(available_homes):
            errors["cast_generation.groups"] = (
                f"Requested {total} generated actors, but only {len(available_homes)} unoccupied, "
                "walkable home cells are available. Generated actors use distinct homes; no household sharing is inferred.")

    if errors:
        return {"errors": errors}
    normalized_groups.sort(key=lambda item: item["id"])
    homes = (scenario_data.get("map") or {}).get("layout", {}).get("homes", [])
    reserved = set()
    implicit_index = 0
    for actor in actor_data:
        home = actor.get("home_cell")
        if home is None:
            if homes:
                allocated = homes[implicit_index % len(homes)]
                implicit_index += 1
                reserved.add((int(allocated[0]), int(allocated[1])))
        else:
            reserved.add((int(home[0]), int(home[1])))
    available_homes = [cell for cell in home_cells if tuple(cell) not in reserved]
    actors = []
    actor_profiles = {}
    cursor = 0
    for group in normalized_groups:
        profile = profiles[group["backend_profile_id"]]
        for ordinal in range(1, group["count"] + 1):
            name = f"{group['id']}-{ordinal:03d}"
            actor = {"name": name, "role": group["role"], "group": group["id"],
                     "backend": profile["kind"], "home_cell": available_homes[cursor]}
            cursor += 1
            for trait, bounds in group["traits"].items():
                generator = random.Random(_generated_seed(seed, scenario_hash, group["id"], ordinal, trait))
                actor[trait] = round(generator.uniform(bounds["min"], bounds["max"]), 6)
            if set(actor) - ACTOR_FIELDS:
                raise AssertionError("cast generator emitted unsupported actor fields")
            actors.append(actor)
            actor_profiles[name] = group["backend_profile_id"]
    payload = {"generator_version": GENERATOR_VERSION, "groups": normalized_groups,
               "actors": actors, "profiles": actor_profiles}
    return {**payload, "generator_hash": _hash({"seed": seed, "scenario_hash": scenario_hash,
                                                  "generator_version": GENERATOR_VERSION,
                                                  "groups": normalized_groups, "actors": actors})}


def materialize_scenario(scenario_id: str, config: dict[str, Any], profile_registry=None) -> dict[str, Any] | str:
    """Copy authored scenario actors, append the immutable resolved generated cast, apply profile overrides."""
    if scenario_id == "town100":
        return "town100"
    from ..scenarios import load_scenario
    data = copy.deepcopy(load_scenario(scenario_id).to_dict())
    generated = config.get("generated_cast", [])
    data["actors"] = copy.deepcopy(data.get("actors", [])) + copy.deepcopy(generated)
    resolved = {item["actor"]: item for item in config.get("resolved_actor_profiles", [])}
    for actor in data["actors"]:
        assignment = resolved.get(actor.get("name"))
        if assignment and (actor.get("name") in config.get("actor_backend_profiles", {}) or
                           assignment.get("source") == "cast_group"):
            actor["backend"] = assignment["backend"]
    return data
