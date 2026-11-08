"""Phase 008: animals age each period, breed after gestation, and die at their lifespan.

One period is one day (TIME.ticks_per_period = 96). The animal data gives maturity and lifespan in
months; a month is TIME.days_per_year / 12 = 30 days. Breeding is a physical event: a mature, fed
female and a mature, fed male of one species that share an enclosure. Births add animals with the
species' NPC setup (applied by BigvilleGame.animal_turn, which syncs backends for every animal).
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld as World  # noqa: E402
from domains import bigville_entities as E                 # noqa: E402
from bigville.game import BigvilleGame                     # noqa: E402

MONTH = 30.0   # TIME.days_per_year / 12


def _cell(world, index=0):
    return sorted(world._map_cells)[index]


def _store_pen(world):
    """A one-cell enclosure on the feed store's cell, so an animal there can eat from the store."""
    if world.map_position_node(world._store) is None:
        world.eng.add_edge_unchecked(world._store, "at_cell", world._map_cells[_cell(world)])
    store_cell = world.map_position_node(world._store)
    world.add_enclosure("pen", [store_cell])
    return store_cell


def _pen(world, name, cell):
    world.add_enclosure(name, [cell])
    return cell


def _fed(world, names):
    """Mark animals as having eaten since the last period (zero hunger), as an eat action would."""
    for name in names:
        if world.animal_alive(name):
            world.eng.set_attr(world._animals[name], "hunger", 0.0)


def _attrs(world, name):
    return world.eng.node(world._animals[name])["attrs"]


def _kinds(world):
    return sorted(name for name in world._animals if world.animal_alive(name))


# ------------------------------------------------------------------ ageing
def test_animals_age_one_day_per_period_and_start_adult_when_founding():
    world = World()
    cell = _cell(world)
    world.add_animal("Bess", "cow", cell=cell)
    world.add_animal("Lamb", "sheep", cell=cell, age_days=0.0)
    founding_age = float(E.ANIMALS["cow"]["matures"]) * MONTH
    assert _attrs(world, "Bess")["age_days"] == founding_age, "a founding animal starts at maturity"
    assert _attrs(world, "Lamb")["age_days"] == 0.0
    for period in range(1, 11):
        world.pass_period()
        _fed(world, ["Bess", "Lamb"])
    assert _attrs(world, "Bess")["age_days"] == founding_age + 10.0, "one period is one day"
    assert _attrs(world, "Lamb")["age_days"] == 10.0
    assert _attrs(world, "Bess")["age_days"] / MONTH == pytest.approx(24.0 + 10.0 / MONTH)


# ------------------------------------------------------------------ birth after gestation
def test_a_fed_pair_conceives_and_the_birth_comes_after_the_gestation():
    world = World()
    cell = _store_pen(world)
    gestation = int(E.ANIMALS["cow"]["gestation_days"])
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Hob", "cow", cell=cell, enclosure="pen", sex="male")
    game = BigvilleGame(world, autonomous=True)
    _fed(world, ["Bess", "Hob"])
    world.pass_period()                     # the first period: conception (both mature and fed)
    assert _attrs(world, "Bess")["sire"] == "Hob"
    assert _attrs(world, "Bess")["gestating_days"] == float(gestation)
    born_at = None
    for _ in range(gestation + 5):
        _fed(world, ["Bess", "Hob"] + [n for n in _kinds(world) if n not in ("Bess", "Hob")])
        before = len(world._animals)
        world.pass_period()
        if len(world._animals) > before and born_at is None:
            born_at = int(world.eng.node(world._town)["attrs"]["period"])
    assert born_at == 1 + gestation, "the litter comes exactly one gestation after conception"
    assert len(world._animals) == 3, "one calf: a cow's litter is one"
    calf = next(name for name in world._animals if name not in ("Bess", "Hob"))
    calf_attrs = _attrs(world, calf)
    assert calf_attrs["species"] == "cow" and calf_attrs["dam"] == "Bess" and calf_attrs["sire"] == "Hob"
    assert calf_attrs["sex"] in ("male", "female")
    assert world.animal_enclosure(calf) == "pen" and world.animal_position(calf) == world.animal_position("Bess")
    assert _attrs(world, "Bess")["gestating_days"] == 0.0, "the dam is no longer carrying"


def test_a_litter_has_the_species_size_and_records_its_parents():
    world = World()
    cell = _store_pen(world)
    litter = int(E.ANIMALS["pig"]["litter"])
    gestation = int(E.ANIMALS["pig"]["gestation_days"])
    world.add_animal("Sow", "pig", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Boar", "pig", cell=cell, enclosure="pen", sex="male")
    for _ in range(gestation + 2):
        _fed(world, ["Sow", "Boar"] + [n for n in _kinds(world) if n not in ("Sow", "Boar")])
        world.pass_period()
    young = [name for name in world._animals if name not in ("Sow", "Boar")]
    assert len(young) == litter
    assert all(_attrs(world, name)["species"] == "pig" and _attrs(world, name)["dam"] == "Sow"
               and _attrs(world, name)["sire"] == "Boar" for name in young)


# ------------------------------------------------------------------ NPC setup for newborns
def test_newborns_get_their_species_npc_setup_when_the_game_syncs_backends():
    world = World()
    cell = _store_pen(world)
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Hob", "cow", cell=cell, enclosure="pen", sex="male")
    game = BigvilleGame(world, autonomous=True)
    assert set(game._animal_backends) == {"Bess", "Hob"}
    _fed(world, ["Bess", "Hob"])
    world.pass_period()
    for _ in range(int(E.ANIMALS["cow"]["gestation_days"])):
        _fed(world, ["Bess", "Hob"] + [n for n in _kinds(world) if n not in ("Bess", "Hob")])
        world.pass_period()
    calf = next(name for name in world._animals if name not in ("Bess", "Hob"))
    assert calf not in game._animal_backends, "backends are created on the next sync, not at the birth"
    choices = game.animal_turn()
    backend = game._animal_backends[calf]
    assert backend.species == "cow"
    assert backend.setup["role"] == E.ANIMAL_NPC_SETUP["cow"]["role"]
    assert choices[calf]["decision_model"] == "psi_can_weighted"


# ------------------------------------------------------------------ no birth without a mature pair
def test_no_conception_without_a_mature_male_and_female_in_one_enclosure():
    world = World()
    west, east = _cell(world, 0), _cell(world, 1)
    world.add_enclosure("west", [west])
    world.add_enclosure("east", [east])
    world.add_animal("Bess", "cow", cell=west, enclosure="west", sex="female")
    world.add_animal("Hob", "cow", cell=east, enclosure="east", sex="male")
    for _ in range(20):
        _fed(world, ["Bess", "Hob"])
        world.pass_period()
    assert _attrs(world, "Bess")["gestating_days"] == 0.0, "a mature pair in different enclosures does not breed"
    assert len(world._animals) == 2

    # Same enclosure, but the male is a calf: no conception until he is mature.
    cell = _cell(world, 2)
    world.add_enclosure("barn", [cell])
    world.add_animal("Cass", "cow", cell=cell, enclosure="barn", sex="female")
    world.add_animal("Tam", "cow", cell=cell, enclosure="barn", sex="male", age_days=0.0)
    for _ in range(20):
        _fed(world, ["Cass", "Tam"])
        world.pass_period()
    assert _attrs(world, "Cass")["gestating_days"] == 0.0, "an immature male does not breed"

    # Once he is mature, the same pair conceives on the next period.
    world.eng.set_attr(world._animals["Tam"], "age_days", float(E.ANIMALS["cow"]["matures"]) * MONTH)
    _fed(world, ["Cass", "Tam"])
    world.pass_period()
    assert _attrs(world, "Cass")["sire"] == "Tam"


def test_two_females_or_two_males_do_not_breed():
    world = World()
    cell = _store_pen(world)
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Cass", "cow", cell=cell, enclosure="pen", sex="female")
    for _ in range(10):
        _fed(world, ["Bess", "Cass"])
        world.pass_period()
    assert _attrs(world, "Bess")["gestating_days"] == 0.0 and _attrs(world, "Cass")["gestating_days"] == 0.0
    assert len(world._animals) == 2


def test_no_conception_across_species_in_one_enclosure():
    world = World()
    cell = _store_pen(world)
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Ram", "sheep", cell=cell, enclosure="pen", sex="male")
    for _ in range(10):
        _fed(world, ["Bess", "Ram"])
        world.pass_period()
    assert _attrs(world, "Bess")["gestating_days"] == 0.0


# ------------------------------------------------------------------ no birth when unfed
def test_no_conception_when_the_dam_or_the_sire_did_not_eat_in_the_period():
    world = World()
    cell = _store_pen(world)
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Hob", "cow", cell=cell, enclosure="pen", sex="male")
    # Hungry since the last period: the pair does not conceive (the animals survive one period).
    world.eng.set_attr(world._animals["Bess"], "hunger", 1.0)
    world.eng.set_attr(world._animals["Hob"], "hunger", 1.0)
    world.pass_period()
    assert world.animal_alive("Bess") and world.animal_alive("Hob")
    assert _attrs(world, "Bess")["gestating_days"] == 0.0, "an unfed pair does not conceive"
    # Fed for one period but the sire was hungry: still no conception.
    _fed(world, ["Bess"])
    world.eng.set_attr(world._animals["Hob"], "hunger", 1.0)
    world.pass_period()
    assert _attrs(world, "Bess")["gestating_days"] == 0.0, "the sire must be fed too"
    # Both fed: conception.
    _fed(world, ["Bess", "Hob"])
    world.pass_period()
    assert _attrs(world, "Bess")["sire"] == "Hob"


def test_a_fed_pair_breeds_when_the_animals_eat_at_the_store():
    """The real feeding path: each animal eats its ration at the store, then time passes."""
    world = World()
    store_cell = _store_pen(world)
    world.set_stock("grass", 10000)
    world.add_animal("Bess", "cow", cell=store_cell, enclosure="pen", sex="female")
    world.add_animal("Hob", "cow", cell=store_cell, enclosure="pen", sex="male")
    for _ in range(3):
        for name in ("Bess", "Hob"):
            assert world.apply_animal_action(name, "eat", {"kind": "grass"})
        world.pass_period()
    assert _attrs(world, "Bess")["sire"] == "Hob", "fed by the store, the pair conceives"


# ------------------------------------------------------------------ death at lifespan, and its record
def test_an_animal_dies_at_its_lifespan_and_the_death_is_recorded():
    world = World()
    cell = _cell(world)
    lifespan_days = float(E.ANIMALS["cow"]["lifespan"]) * MONTH
    world.add_animal("Old", "cow", cell=cell, age_days=lifespan_days - 2.0)
    world.pass_period()
    _fed(world, ["Old"])
    assert world.animal_alive("Old"), "one day short of the lifespan, the cow is alive"
    world.pass_period()
    assert not world.animal_alive("Old")
    assert _attrs(world, "Old")["death_cause"] == "old_age"
    assert _attrs(world, "Old")["death_period"] == 2.0
    assert _attrs(world, "Old")["age_days"] == lifespan_days


def test_a_dead_animal_neither_ages_nor_breeds():
    world = World()
    cell = _store_pen(world)
    world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female", age_days=float(E.ANIMALS["cow"]["lifespan"]) * MONTH - 1)
    world.add_animal("Hob", "cow", cell=cell, enclosure="pen", sex="male")
    _fed(world, ["Bess", "Hob"])
    world.pass_period()
    assert not world.animal_alive("Bess")
    age = _attrs(world, "Bess")["age_days"]
    world.pass_period()
    assert _attrs(world, "Bess")["age_days"] == age, "the dead do not age"
    assert _attrs(world, "Bess")["gestating_days"] == 0.0


def test_starvation_is_recorded_as_the_cause_of_death():
    world = World()
    cell = _cell(world)
    world.add_animal("Star", "cow", cell=cell)
    for _ in range(int(E.ANIMALS["cow"]["starve_limit"])):
        world.pass_period()
    assert not world.animal_alive("Star")
    assert _attrs(world, "Star")["death_cause"] == "starvation"
    assert _attrs(world, "Star")["death_period"] == float(E.ANIMALS["cow"]["starve_limit"])


# ------------------------------------------------------------------ bees
def test_bees_do_not_breed_pairwise():
    assert E.ANIMALS["bee"]["breeds"] is False
    world = World()
    cell = _store_pen(world)
    world.add_animal("Queen", "bee", cell=cell, enclosure="pen", sex="female")
    world.add_animal("Drone", "bee", cell=cell, enclosure="pen", sex="male")
    for _ in range(60):
        _fed(world, ["Queen", "Drone"])
        world.pass_period()
    assert len(world._animals) == 2 and _attrs(world, "Queen")["gestating_days"] == 0.0


# ------------------------------------------------------------------ sex of the young
def test_birth_sex_is_a_pure_function_of_the_seed_and_the_litter():
    """Births keep no world RNG state, and the same seed and dam give the same sexes in order."""
    def litters(seed_world):
        world = seed_world
        cell = _store_pen(world)
        world.add_animal("Bess", "cow", cell=cell, enclosure="pen", sex="female")
        world.add_animal("Hob", "cow", cell=cell, enclosure="pen", sex="male")
        assert not hasattr(world, "_rng"), "the world keeps no shared RNG"
        sexes = []
        for _ in range(12):
            before = set(world._animals)
            world._give_birth("Bess")
            (young,) = set(world._animals) - before
            sexes.append(_attrs(world, young)["sex"])
        assert not hasattr(world, "_rng"), "births do not create a world RNG"
        return sexes

    first, second = litters(World()), litters(World())
    assert first == second, "the same world gives the same sexes"
    assert set(first) == {"male", "female"}, "twelve births of a cow include both sexes"


# ------------------------------------------------------------------ founding herd
def test_the_founding_herd_is_one_female_of_each_species_and_does_not_breed():
    town = World.from_town100(autonomous_actors=False)
    founders = list(town._animals)
    assert len(founders) == 7
    assert {_attrs(town, name)["sex"] for name in founders} == {"female"}
    for _ in range(3):
        town.pass_period()
    assert len(town._animals) == 7, "one animal per species has no mate, so no birth"
    assert all(_attrs(town, name)["gestating_days"] == 0.0 for name in founders)


# ------------------------------------------------------------------ self-test
def test_the_self_test_is_clean_for_the_life_cycle_fields():
    report = E.check_consistency()
    assert report["errors"] == []


@pytest.mark.parametrize("species, change, message", [
    ("cow", {"gestation_days": 0}, "gestation_days must be at least 1"),
    ("cow", {"litter": 1.5}, "litter must be a whole number"),
    ("cow", {"breeding_interval_days": 100}, "shorter than gestation_days"),
    ("cow", {"birth_male_share": 1.5}, "birth_male_share must be between 0 and 1"),
    ("cow", {"founding_sex": "herm"}, "founding_sex must be"),
    ("cow", {"breeds": "yes"}, "'breeds' must be true or false"),
    ("cow", {"approx": ["colour"]}, "'approx' must list only"),
    ("cow", {"lifespan": 1}, "lifespan must be longer than matures"),
])
def test_the_self_test_reports_bad_life_cycle_fields(monkeypatch, species, change, message):
    bad = dict(E.ANIMALS[species], **change)
    monkeypatch.setitem(E.ANIMALS, species, bad)
    errors = E.check_consistency()["errors"]
    assert any(message in error for error in errors), errors


def test_the_self_test_requires_a_breeder_to_have_its_life_cycle_fields(monkeypatch):
    bad = {k: v for k, v in E.ANIMALS["cow"].items() if k != "gestation_days"}
    monkeypatch.setitem(E.ANIMALS, "cow", bad)
    assert any("needs 'gestation_days'" in error for error in E.check_consistency()["errors"])


def test_the_self_test_rejects_life_cycle_fields_on_a_non_breeder(monkeypatch):
    monkeypatch.setitem(E.ANIMALS, "bee", dict(E.ANIMALS["bee"], gestation_days=10))
    assert any("does not breed" in error for error in E.check_consistency()["errors"])
