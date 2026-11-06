from __future__ import annotations

import json

import pytest

from bigville.api import create_world
from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint


class _ResidentCheckpoint:
    def __init__(self, name, marker=0):
        self.name = name
        self.marker = marker

    def save(self, path):
        path = path / "resident.json"
        path.write_text(json.dumps({"name": self.name, "marker": self.marker}))

    @classmethod
    def load(cls, path):
        data = json.loads((path / "resident.json").read_text())
        return cls(**data)


def _world():
    scenario = {
        "id": "checkpoint_fixture",
        "name": "Checkpoint fixture",
        "map": {"grid": [["floor", "floor"], ["floor", "floor"]]},
        "actors": [
            {"name": "Ada", "role": "farmer", "home_cell": [0, 0]},
            {"name": "Ben", "role": "farmer", "home_cell": [1, 0]},
        ],
        "buildings": [], "laws": [], "policies": [], "charters": [],
        "stocks": {"grain": 8},
    }
    return create_world(scenario=scenario, seed=8821,
                        cognition_factory=lambda name: _ResidentCheckpoint(name, 5))


def _save(world, path):
    save_world_checkpoint(world, path)


def _load(path):
    return load_world_checkpoint(path, resident_loader=lambda _name, folder:
                                 _ResidentCheckpoint.load(folder))


def test_world_checkpoint_round_trip_and_next_period_match_uninterrupted(tmp_path):
    control = _world()
    saved = _world()
    saved.pass_period(2)
    control.pass_period(2)
    saved.set_stock("grain", 13)
    control.set_stock("grain", 13)
    saved._actor_targets["Ada"]["remembered"] = ("field", 2)
    control._actor_targets["Ada"]["remembered"] = ("field", 2)

    checkpoint = tmp_path / "town"
    _save(saved, checkpoint)
    restored = _load(checkpoint)

    assert restored.export_state() == saved.export_state()
    assert restored.eng.to_checkpoint_dict() == saved.eng.to_checkpoint_dict()
    assert restored.actor_mind("Ada").marker == 5
    assert restored._actor_targets["Ada"]["remembered"] == ("field", 2)

    restored.pass_period()
    control.pass_period()
    assert restored.export_state() == control.export_state()
    assert restored.eng.to_checkpoint_dict() == control.eng.to_checkpoint_dict()


def test_world_checkpoint_requires_resident_owned_save_method(tmp_path):
    world = _world()
    world._actor_minds["Ada"] = object()
    with pytest.raises(TypeError, match=r"resident 'Ada'.*save\(path\)"):
        save_world_checkpoint(world, tmp_path / "town")


def test_world_checkpoint_requires_one_mind_for_every_actor(tmp_path):
    world = _world()
    world._actor_minds.pop("Ada")
    with pytest.raises(ValueError, match="resident minds must match world actors"):
        save_world_checkpoint(world, tmp_path / "town")


def test_world_load_validates_provider_name_and_does_not_construct_throwaway_minds(tmp_path):
    world = _world()
    checkpoint = tmp_path / "town"
    save_world_checkpoint(world, checkpoint)
    created = []

    def cognition_factory(name):
        created.append(name)
        return _ResidentCheckpoint(name)

    with pytest.raises(ValueError, match="resident loader name mismatch"):
        load_world_checkpoint(
            checkpoint,
            resident_loader=lambda _name, _path: _ResidentCheckpoint("WrongName"),
            cognition_factory=cognition_factory,
        )
    assert created == []


def test_builtin_fallback_residents_restore_their_private_graphs(tmp_path):
    world = create_world(scenario="house_argument", seed=71)
    mind = world.actor_mind("Mara")
    mind.heard_events["event:1"] = {"strength": 0.6, "day_heard": 2}
    mind.told_events[("Jon", "event:1")] = 3
    mind.speech_backend._bond("Jon", {"strength": 0.4})
    mind.voice.add_communicative_goal({"greeting": {"of": "Jon"}})
    mind.voice.set_addressee(mind.speech_bonds["Jon"])
    mind.speech_choices["Jon"] = {"kind": "greeting", "spoken": True}
    before_graph = mind.s.to_checkpoint_dict()

    checkpoint = tmp_path / "town"
    save_world_checkpoint(world, checkpoint)
    restored = load_world_checkpoint(checkpoint)
    restored_mind = restored.actor_mind("Mara")

    assert restored_mind.s.to_checkpoint_dict() == before_graph
    assert restored_mind.heard_events == mind.heard_events
    assert restored_mind.told_events == mind.told_events
    assert restored_mind.speech_choices == mind.speech_choices
    assert restored_mind.voice._goals == mind.voice._goals
    assert restored_mind.voice._addressee == mind.voice._addressee
    assert restored_mind.speech_backend.mind is restored_mind


def test_world_checkpoint_requires_matching_extension_callbacks(tmp_path):
    world = _world()
    world.register_physical_subsystem("custom", lambda _world, _periods: None)
    checkpoint = tmp_path / "town"
    save_world_checkpoint(world, checkpoint)
    with pytest.raises(ValueError, match="matching physical subsystem extension"):
        load_world_checkpoint(checkpoint, resident_loader=lambda _name, path:
                              _ResidentCheckpoint.load(path))


def test_world_checkpoint_rejects_pack_identity_mismatch(tmp_path):
    world = _world()
    checkpoint = tmp_path / "town"
    save_world_checkpoint(world, checkpoint)
    manifest_path = checkpoint / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["data_pack"]["sha256"] = "changed-pack"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="data pack identity or content mismatch"):
        load_world_checkpoint(checkpoint, resident_loader=lambda _name, path:
                              _ResidentCheckpoint.load(path))
