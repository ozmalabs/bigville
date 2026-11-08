"""Deterministic chance: canonical seeds and draws for simulation outcomes.

Every runtime chance outcome in Bigville must derive from the world seed, a
stable purpose, the turn/period, and the canonical state of the parties
involved.  This module is the single source of that rule.  It is import-safe:
it never constructs a world and never reads process identity, the wall clock,
``id()`` or Python's salted ``hash()``.

The canonical form is deliberately explicit.  Mappings are ordered by their
canonical keys, sets by their canonical members, and tuples/lists share one
sequence form so a restored checkpoint (which may decode a tuple as a list)
still produces the same draw.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

__all__ = [
    "canonical_bytes",
    "derive_seed",
    "uniform",
    "choice",
    "shuffle",
    "sample",
    "world_seed",
    "actor_state",
    "state_uniform",
    "state_seed",
]

_DOMAIN = b"bigville.determinism.v1"
_TWO53 = float(1 << 53)


def _dump(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalise(value, path: str = "value", active: set[int] | None = None):
    """Return a JSON-safe canonical value, rejecting unsupported inputs."""
    if active is None:
        active = set()

    # bool must precede int (it is an int subclass), and NodeRef is an int.
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float cannot be canonicalised at {path}: {value!r}")
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return {"$type": "bytes", "hex": bytes(value).hex()}

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise ValueError(f"cyclic mapping cannot be canonicalised at {path}")
        active.add(identity)
        try:
            pairs = []
            for key, item in value.items():
                normal_key = _normalise(key, f"{path}.key", active)
                normal_item = _normalise(item, f"{path}[{key!r}]", active)
                pairs.append([normal_key, normal_item])
            pairs.sort(key=lambda pair: _dump(pair[0]))
            return {"$type": "mapping", "items": pairs}
        finally:
            active.discard(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise ValueError(f"cyclic sequence cannot be canonicalised at {path}")
        active.add(identity)
        try:
            return {"$type": "sequence", "items": [
                _normalise(item, f"{path}[{index}]", active)
                for index, item in enumerate(value)]}
        finally:
            active.discard(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in active:
            raise ValueError(f"cyclic set cannot be canonicalised at {path}")
        active.add(identity)
        try:
            items = [_normalise(item, f"{path}{{member}}", active) for item in value]
            items.sort(key=_dump)
            return {"$type": "set", "items": items}
        finally:
            active.discard(identity)

    raise TypeError(
        f"unsupported canonical value at {path}: {type(value).__name__}; "
        "only primitives, mappings, sequences and sets are allowed"
    )


def canonical_bytes(*parts) -> bytes:
    """Canonical bytes for ``parts``; equal inputs always give equal bytes.

    Dict/set iteration order, the distinction between tuple and list, and an
    int subclass such as ``NodeRef`` do not affect the result.  Non-finite
    floats and arbitrary objects are rejected with a clear error.
    """
    return _dump(_normalise(list(parts))).encode("utf-8")


def derive_seed(world_seed_value, *parts) -> int:
    """A 128-bit BLAKE2b seed over the world seed, domain and ``parts``."""
    digest = hashlib.blake2b(digest_size=16)
    digest.update(_DOMAIN)
    digest.update(canonical_bytes(int(world_seed_value), *parts))
    return int.from_bytes(digest.digest(), "big")


def uniform(world_seed_value, *parts) -> float:
    """Map a derived seed to a deterministic value in ``[0, 1)``."""
    seed = derive_seed(world_seed_value, *parts)
    return float(seed >> (128 - 53)) / _TWO53


def _ordered(sequence):
    """A stable order for a sequence; sets are sorted by canonical member bytes."""
    if isinstance(sequence, (set, frozenset)):
        return sorted(sequence, key=canonical_bytes)
    return list(sequence)


def choice(sequence, world_seed_value, *parts):
    """Choose one member of ``sequence`` deterministically."""
    items = _ordered(sequence)
    if not items:
        raise IndexError("cannot choose from an empty sequence")
    return items[derive_seed(world_seed_value, "choice", *parts) % len(items)]


def shuffle(sequence, world_seed_value, *parts) -> list:
    """Return a deterministically shuffled new list; the input is not mutated."""
    items = _ordered(sequence)
    for index in range(len(items) - 1, 0, -1):
        other = derive_seed(world_seed_value, "shuffle", *parts, index) % (index + 1)
        items[index], items[other] = items[other], items[index]
    return items


def sample(sequence, k, world_seed_value, *parts) -> list:
    """Return a deterministic sample of ``k`` members; the input is not mutated."""
    items = _ordered(sequence)
    k = int(k)
    if k < 0:
        raise ValueError("sample size must not be negative")
    if k > len(items):
        raise ValueError("sample larger than population")
    for index in range(k):
        other = index + derive_seed(
            world_seed_value, "sample", *parts, index) % (len(items) - index)
        items[index], items[other] = items[other], items[index]
    return items[:k]


def world_seed(world) -> int:
    """The world's deterministic seed; never process identity or wall time."""
    for attr in ("_burial_seed", "_animal_life_seed"):
        value = getattr(world, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    map_node = getattr(world, "_map_node", None)
    engine = getattr(world, "eng", None)
    if map_node is not None and engine is not None:
        try:
            value = engine.node(map_node)["attrs"].get("seed")
        except (KeyError, TypeError, ValueError):
            value = None
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    value = getattr(world, "map_seed", None)
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    raise ValueError(
        "world has no deterministic seed (expected _burial_seed, map seed "
        "or _animal_life_seed)"
    )


def _sorted_mapping(mapping: Mapping) -> dict:
    return {key: mapping[key]
            for key in sorted(mapping, key=lambda key: _dump(_normalise(key)))}


# Per-turn action bookkeeping is not part of a party's stable state for a
# chance draw.  Including it would make a draw depend on whether another shard
# had already claimed the action slot or recorded an outcome, which is exactly
# the order-dependence this module removes.  Physical/body/skill/relationship
# state stays in.
_VOLATILE_ACTOR_KEYS = frozenset({
    "turn", "major_action_used", "major_action_kind", "last_major_action",
    "last_outcome", "refusal_counts", "busy", "stats_dirty",
    "carry_move_cooldown", "fill_armed", "empty_armed", "use_armed",
    "repair_armed", "dye_armed", "wear_armed", "work_armed", "pick_armed",
})


def _stable_attrs(attrs: Mapping) -> dict:
    return _sorted_mapping({
        key: value for key, value in attrs.items()
        if str(key) not in _VOLATILE_ACTOR_KEYS
        and not str(key).endswith("_armed")
    })


def actor_state(world, name) -> dict:
    """A canonical, stable snapshot of one actor and their body.

    Missing actors are reported as ``{"name": ..., "present": False}`` rather
    than raising, so a draw for a departed actor is still stable.
    """
    key = str(name)
    actors = getattr(world, "_actors", None) or {}
    if key not in actors:
        return {"name": key, "present": False}

    engine = getattr(world, "eng", None)
    try:
        attrs = dict(engine.node(actors[key])["attrs"])
    except (KeyError, TypeError, ValueError):
        return {"name": key, "present": False}

    bodies = getattr(world, "_bodies", None) or {}
    body_attrs = {}
    body_node = bodies.get(key)
    if body_node is not None:
        try:
            body_attrs = dict(engine.node(body_node)["attrs"])
        except (KeyError, TypeError, ValueError):
            body_attrs = {}

    positions = getattr(world, "_actor_positions", None) or {}
    position = positions.get(key) if hasattr(positions, "get") else None
    if isinstance(position, (list, tuple)):
        position = list(position)

    return {
        "name": key,
        "present": True,
        "alive": float(attrs.get("alive", 0.0)) == 1.0,
        "position": position,
        "attrs": _stable_attrs(attrs),
        "body": _stable_attrs(body_attrs),
    }


def _involved_actors(world, parts, actors) -> list[str]:
    if isinstance(actors, str):
        actors = (actors,)
    names = {str(actor) for actor in (actors or ())}
    known = getattr(world, "_actors", None) or {}
    for part in parts:
        if isinstance(part, str) and part in known:
            names.add(part)
    return sorted(names)


def _state_parts(world, purpose, parts, actors):
    names = _involved_actors(world, parts, actors)
    states = {name: actor_state(world, name) for name in names}
    return ("state", str(purpose), *parts, states)


def state_seed(world, purpose, *parts, actors=()) -> int:
    """A 128-bit seed including the world seed, purpose, parts and actor state."""
    return derive_seed(world_seed(world), *_state_parts(world, purpose, parts, actors))


def state_uniform(world, purpose, *parts, actors=()) -> float:
    """The runtime default: a state-derived draw in ``[0, 1)``.

    Every name in ``parts`` that belongs to a world actor is included
    automatically, as is every explicit name in ``actors``.
    """
    return uniform(world_seed(world), *_state_parts(world, purpose, parts, actors))
