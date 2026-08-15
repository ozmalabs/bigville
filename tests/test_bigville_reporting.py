"""Population, economic, and social reporting for the standalone Bigville world."""

from __future__ import annotations

from bigville.server import GameService
from worlds.bigville_world import BigvilleWorld


def test_report_exposes_exact_census_and_sample_estimate():
    world = BigvilleWorld.from_town100(autonomous_actors=False)

    report = world.report(sample_size=10, seed=17)

    assert report["schema"] == "bigville/report/1"
    assert report["measurement"]["population"] == "complete_census"
    assert report["population"]["method"] == "census"
    assert report["population"]["total"] == 100
    assert report["population"]["alive"] == 100
    sample = report["population"]["sample_estimate"]
    assert sample["method"] == "simple_random_sample"
    assert sample["frame_size"] == 100
    assert sample["sample_size"] == 10
    assert "standard_error" in sample["estimates"]["mean_age"]
    assert report["population"]["coin_gini"] >= 0.0


def test_report_covers_physical_economy_and_recorded_social_activity():
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    names = list(world._actors)
    world.set_relationship(names[0], names[1], kind="neighbour", strength=0.8)
    world.speak(names[0], names[1], "The market is busy today.")

    report = world.report(sample_size=5, seed=3)

    economy = report["economy"]
    assert economy["food_quantity"] >= economy["food_quantity_in_stock"]
    assert economy["total_physical_reference_value"] >= economy["stock_reference_value"]
    assert economy["shops"]
    assert economy["storage"]
    assert economy["land"]
    assert economy["living_animals"]
    assert report["ecology"]["animals"]["alive"] == 7
    assert report["social"]["relationships"]["directed_bonds"] == 1
    assert report["social"]["conversation"]["utterances"] == 1
    assert report["social"]["conversation"]["speakers"] == 1


def test_report_snapshots_measure_changes_and_are_exported():
    world = BigvilleWorld.from_town100(autonomous_actors=False)
    initial = world.record_report_snapshot(label="initial", sample_size=8, seed=5)
    world.set_stock("bread", world.qty("bread") + 12)
    later = world.record_report_snapshot(label="after-harvest", sample_size=8, seed=5)

    assert initial["snapshot"]["id"] == 1
    assert later["snapshot"]["id"] == 2
    assert later["changes_since_snapshot"]["food_quantity"] == 12.0
    assert [item["label"] for item in world.report_history()] == ["initial", "after-harvest"]
    assert [item["label"] for item in later["series"]["history"]] == ["initial", "after-harvest"]
    exported = world.export_state()
    assert exported["report"]["schema"] == "bigville/report/1"
    assert len(exported["report_history"]) == 2


def test_run_village_records_periodic_report_history():
    world = BigvilleWorld.from_town100(autonomous_actors=False)

    world.run_village(periods=1, ticks_per_period=1)

    history = world.report_history()
    assert [item["label"] for item in history] == ["initial", "clock:1"]
    assert world.report()["series"]["snapshots"] == 2


def test_game_service_exposes_report_without_advancing_the_game():
    service = GameService(seed=305000)
    before = service.game.world.calendar()["clock"]

    report = service.report()

    assert report["schema"] == "bigville/report/1"
    assert report["clock"]["clock"] == before
    assert service.game.world.calendar()["clock"] == before
