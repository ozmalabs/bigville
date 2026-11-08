"""Strict checkpoint support for a Bigville physical world.

The public ``export_state`` projection is intended for display and reports.
This module stores the canonical typed graph plus every JSON/type-safe world
index, while cognition residents retain ownership of their own checkpoints.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from .runtime import BigvilleGraph, NodeRef, _checkpoint_decode, _checkpoint_encode


_SCHEMA = "bigville/world-checkpoint/1"
_EXTERNAL_FIELDS = {
    "E", "eng", "_cognition_factory", "_physical_subsystem_extensions",
    "_conversation_adapter", "_actor_minds",
    # Derived caches are intentionally discarded and rebuilt lazily.
    "_distance_fields", "_travel_time_fields",
    # TG05: per-attempt thread-local state; a restored world constructs a fresh one.
    "_attempt_state",
    # EN03: turn-batch bookkeeping; a restored world starts with no open batch.
    "_rule_batch_depth", "_rule_batch_pending",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_manifest(directory: Path) -> dict[str, str]:
    return {file.relative_to(directory).as_posix(): _sha256(file)
            for file in sorted(directory.rglob("*")) if file.is_file()}


def _pack_identity(data_pack: str) -> dict[str, str | None]:
    from domains.pack import load_pack

    pack = load_pack(data_pack)
    canonical = json.dumps(_checkpoint_encode(pack.base, "pack.base"),
                           sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"name": pack.name, "extends": pack.extends,
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def _save_resident(name: str, mind, destination: Path, data_pack: str) -> str:
    """Save a built-in fallback mind or delegate to provider-owned storage."""
    from worlds.bigville_world import BigvilleOcelotActor

    if isinstance(mind, BigvilleOcelotActor):
        expected = {"name", "s", "agent", "inner", "speech_bonds", "speech_encounters",
                    "speech_choices", "speech_backend", "told_events", "_read_documents",
                    "heard_events", "voice", "_voice_targets"}
        unknown = set(mind.__dict__) - expected
        if unknown:
            raise TypeError(f"unsupported fallback resident state for {name!r}: {sorted(unknown)}")
        voice_expected = {"s", "_addressee", "_goals"}
        voice_unknown = set(mind.voice.__dict__) - voice_expected
        if voice_unknown:
            raise TypeError(
                f"unsupported fallback voice state for {name!r}: {sorted(voice_unknown)}"
            )
        state = {
            "name": mind.name,
            "data_pack": data_pack,
            "agent": int(mind.agent),
            "graph": mind.s.to_checkpoint_dict(),
            "speech_bonds": mind.speech_bonds,
            "speech_encounters": mind.speech_encounters,
            "speech_choices": mind.speech_choices,
            "told_events": mind.told_events,
            "read_documents": mind._read_documents,
            "heard_events": mind.heard_events,
            "voice_graph": mind.voice.s.to_checkpoint_dict(),
            "voice_addressee": mind.voice._addressee,
            "voice_goals": mind.voice._goals,
        }
        encoded = _checkpoint_encode(state, "resident")
        (destination / "fallback.json").write_text(
            json.dumps(encoded, sort_keys=True, separators=(",", ":"), allow_nan=False),
            encoding="utf-8")
        return "bigville_fallback"
    save = getattr(mind, "save", None)
    if not callable(save):
        raise TypeError(f"resident {name!r} has no save(path) checkpoint method")
    save(destination)
    return "provider"


def _load_fallback_resident(name: str, directory: Path):
    from worlds.bigville_world import BigvilleOcelotActor
    from .backends.speech import DeterministicSpeechBackend

    encoded = json.loads((directory / "fallback.json").read_text(encoding="utf-8"))
    state = _checkpoint_decode(encoded, "resident")
    if state.get("name") != name:
        raise ValueError(f"fallback resident checkpoint name mismatch: expected {name!r}")
    mind = BigvilleOcelotActor(str(name), data_pack=state["data_pack"])
    mind.s = BigvilleGraph.from_checkpoint_dict(state["graph"])
    mind.inner = mind.s
    mind.agent = NodeRef(state["agent"])
    if not mind.s.has_node(mind.agent):
        raise ValueError(f"fallback resident {name!r} has a missing agent node")
    mind.speech_bonds = state["speech_bonds"]
    mind.speech_encounters = state["speech_encounters"]
    mind.speech_choices = state["speech_choices"]
    mind.told_events = state["told_events"]
    mind._read_documents = state["read_documents"]
    mind.heard_events = state["heard_events"]
    mind.voice.s = BigvilleGraph.from_checkpoint_dict(state["voice_graph"])
    mind.voice._addressee = state["voice_addressee"]
    mind.voice._goals = state["voice_goals"]
    mind._voice_targets = {}
    mind.speech_backend = DeterministicSpeechBackend(mind)
    return mind


def save_world_checkpoint(world, path: str | Path) -> None:
    """Save a world at a quiescent boundary, including resident checkpoints.

    Every external mind must implement ``save(path)``. Arbitrary callables,
    custom graph values, or in-progress action dispatch are rejected.
    """
    root = Path(path)
    if getattr(world, "_actor_tick_in_progress", False) or getattr(world, "_major_dispatch", False):
        raise ValueError("cannot checkpoint Bigville during an actor tick or major-action dispatch")
    if (getattr(world, "_rule_batch_depth", 0)
            or getattr(world, "_rule_batch_pending", False)):
        raise ValueError("cannot checkpoint Bigville during an open rule batch")
    extensions = getattr(world, "_physical_subsystem_extensions", {})
    if not isinstance(extensions, dict) or any(not callable(fn) for fn in extensions.values()):
        raise TypeError("invalid physical subsystem extension registry")
    if set(world._actor_minds) != set(world._actors):
        missing = sorted(set(world._actors) - set(world._actor_minds))
        extra = sorted(set(world._actor_minds) - set(world._actors))
        raise ValueError(f"resident minds must match world actors (missing={missing}, extra={extra})")

    attrs = {}
    for key, value in world.__dict__.items():
        if key in _EXTERNAL_FIELDS:
            continue
        attrs[key] = _checkpoint_encode(value, f"world.{key}")
    attrs["_construction"] = "town100" if hasattr(world, "_cast100") else "scenario"
    # DS01: runtime chance is state-derived; no RNG state is written.  Old
    # checkpoints may still carry ``_rng_state`` and are ignored on restore.
    encoded_attrs = json.dumps(attrs, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")
    graph_data = world.eng.to_checkpoint_dict()
    encoded_graph = json.dumps(graph_data, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")

    root.mkdir(parents=True, exist_ok=True)
    generation = "generation-" + uuid.uuid4().hex
    staging = root / ("." + generation)
    staging.mkdir()
    try:
        (staging / "graph.json").write_bytes(encoded_graph)
        (staging / "world.json").write_bytes(encoded_attrs)
        residents_dir = staging / "residents"
        residents_dir.mkdir()
        residents = {}
        for index, (name, mind) in enumerate(world._actor_minds.items()):
            relative = f"residents/{index:04d}"
            destination = staging / relative
            destination.mkdir()
            kind = _save_resident(name, mind, destination, str(world.data_pack))
            residents[str(name)] = {"path": relative, "kind": kind}

        files = _file_manifest(staging)
        committed = root / generation
        os.replace(staging, committed)
        manifest = {"schema": _SCHEMA, "generation": generation,
                    "files": files, "residents": residents,
                    "extension_names": sorted(extensions),
                    "data_pack": _pack_identity(str(world.data_pack))}
        fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, root / "manifest.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _restore_scenario(world_class, state: dict, graph: BigvilleGraph,
                      physical_subsystem_extensions: dict, cognition_factory):
    """Construct current data/pack views, then overlay the saved canonical state."""
    attrs = state
    scenario = _checkpoint_decode(attrs["_scenario_data"], "world._scenario_data")
    pack = _checkpoint_decode(attrs["data_pack"], "world.data_pack")
    physical_subsystems = _checkpoint_decode(attrs["physical_subsystems"],
                                             "world.physical_subsystems")
    construction = attrs.get("_construction", "scenario")
    if construction not in {"scenario", "town100"}:
        raise ValueError(f"unsupported world construction mode: {construction!r}")
    physical_override = (None if "physical_subsystems" in scenario
                         else physical_subsystems)
    map_nodes = graph.nodes("Map")
    map_seed = (int(graph.node(map_nodes[0])["attrs"].get("seed", 1))
                if map_nodes else 1)
    world = world_class(map_seed=map_seed, scenario=(None if construction == "town100" else scenario),
                        data_pack=pack,
                        physical_subsystems=physical_override,
                        physical_subsystem_extensions=physical_subsystem_extensions,
                        cognition_factory=None)
    # Runtime actors created from scenarios are installed by the constructor
    # wrapper. Populate custom/town100 worlds through the same public methods.
    if construction == "town100":
        world.populate_town100(seed=map_seed)
    elif scenario.get("actors"):
        for actor in scenario["actors"]:
            data = dict(actor)
            name = str(data.pop("name"))
            backend = data.pop("backend", None)
            profile = data.pop("simple_profile", None)
            world._scenario_character_data[name] = {
                "identity": dict(data.get("identity", {})),
                "personality": dict(data.get("personality", {})),
                "memories": list(data.get("memories", [])),
                "held_frames": list(data.get("held_frames", data.get("frames", []))),
                "reference_priors": list(data.get("reference_priors", [])),
                "recipe_priors": list(data["recipe_priors"]) if "recipe_priors" in data else None,
            }
            supported = {"role", "skill", "station", "literacy", "capability", "learn",
                         "home_cell", "work_cell", "klass", "age", "life_stage",
                         "role_identity", "group", "traits", "trades"}
            world.add_actor(name, **{key: data[key] for key in supported if key in data})
            if backend:
                world._scenario_actor_backends[name] = str(backend)
            if profile:
                world._scenario_simple_profiles[name] = str(profile)

    world.eng = graph
    restored = {}
    for key, encoded in attrs.items():
        # `_rng_state` is the pre-DS01 checkpoint field; ignore it cleanly so
        # an old checkpoint restores under the state-derived rule.  `_rng`
        # itself was external and never written, but tolerate it likewise.
        if key in {"_rng_state", "_rng", "_construction"}:
            continue
        if key in _EXTERNAL_FIELDS:
            raise ValueError(f"checkpoint attempts to restore external field {key!r}")
        restored[key] = _checkpoint_decode(encoded, f"world.{key}")
    for key, value in restored.items():
        setattr(world, key, value)
    world.eng._inner = world.eng
    world._distance_fields = {}
    world._travel_time_fields = {}
    world._cognition_factory = cognition_factory
    world._physical_subsystem_extensions = dict(physical_subsystem_extensions)
    world._conversation_adapter = None
    world._actor_minds = {}
    return world


def load_world_checkpoint(path: str | Path, *, resident_loader: Callable | None = None,
                          physical_subsystem_extensions: dict | None = None,
                          cognition_factory=None):
    """Load a world and reattach each separately persisted resident mind.

    ``resident_loader(name, checkpoint_path)`` is required when the checkpoint
    contains residents; it should call each provider's own load method.
    """
    from worlds.bigville_world import BigvilleWorld

    root = Path(path)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != _SCHEMA:
            raise ValueError(f"unsupported world checkpoint schema: {manifest.get('schema')!r}")
        generation = manifest.get("generation")
        if not isinstance(generation, str) or not generation.startswith("generation-") or Path(generation).name != generation:
            raise ValueError("invalid world checkpoint generation")
        directory = root / generation
        files = manifest.get("files")
        if not isinstance(files, dict) or _file_manifest(directory) != files:
            raise ValueError("world checkpoint file checksum mismatch")
        callbacks = dict(physical_subsystem_extensions or {})
        if sorted(callbacks) != manifest.get("extension_names", []):
            raise ValueError("world checkpoint requires matching physical subsystem extension callbacks")
        graph = BigvilleGraph.from_checkpoint_dict(
            json.loads((directory / "graph.json").read_text(encoding="utf-8")))
        attrs = json.loads((directory / "world.json").read_text(encoding="utf-8"))
        pack_name = _checkpoint_decode(attrs["data_pack"], "world.data_pack")
        if _pack_identity(pack_name) != manifest.get("data_pack"):
            raise ValueError("world checkpoint data pack identity or content mismatch")
        world = _restore_scenario(BigvilleWorld, attrs, graph, callbacks, cognition_factory)
        residents = manifest.get("residents", {})
        provider_names = [name for name, entry in residents.items()
                          if entry.get("kind") == "provider"]
        if provider_names and resident_loader is None:
            raise ValueError(
                "world checkpoint has provider-owned resident minds; "
                "provide resident_loader(name, path)"
            )
        for name, entry in residents.items():
            if not isinstance(entry, dict):
                raise ValueError(f"invalid resident checkpoint record for {name!r}")
            relative = entry.get("path")
            resident_path = Path(relative)
            if resident_path.is_absolute() or ".." in resident_path.parts:
                raise ValueError(f"invalid resident checkpoint path for {name!r}")
            if entry.get("kind") == "bigville_fallback":
                mind = _load_fallback_resident(name, directory / resident_path)
            elif entry.get("kind") == "provider":
                mind = resident_loader(name, directory / resident_path)
            else:
                raise ValueError(f"unknown resident checkpoint kind for {name!r}")
            if str(getattr(mind, "name", "")) != str(name):
                raise ValueError(
                    f"resident loader name mismatch for {name!r}: "
                    f"restored {getattr(mind, 'name', None)!r}"
                )
            world._actor_minds[name] = mind
        if set(world._actor_minds) != set(world._actors):
            raise ValueError("resident checkpoint names do not match world actors")
        world._cognition_factory = cognition_factory
        return world
    except Exception as exc:
        raise ValueError(f"could not restore Bigville world checkpoint at {root}: {exc}") from exc
