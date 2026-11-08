"""DS02: every runtime stateless chance draw is state-derived.

These tests pin the contract of ``_stable_draw`` and the draws migrated to it:
the same world seed, purpose, parts and involved party state give the same
value; changing the involved state (or the day/period) changes the value; draw
order does not matter.  Probability tables and thresholds are asserted to be
unchanged.
"""
from __future__ import annotations

import pytest

from bigville.api import create_game
from bigville.tick_trace import semantic_world_state
from domains import bigville_entities as E
from domains import determinism
from worlds import body as B
from worlds.bigville_world import BigvilleWorld as World

A, H = "Ada", "Hal"
PACK = "bigville"
TABLES = B.pack_tables(PACK)


# ------------------------------------------------------------------ fixtures


def _actor_world(seed=305000, actors=(A, "Ben")):
    world = World(autonomous_actors=False, map_seed=seed)
    cell = world.map_position_node(world._store)
    for name in actors:
        world.add_actor(name, role="hand", home_cell=cell)
        world._move_actor_to(name, cell)
    return world


def _birth_world(seed=305000):
    return World.from_town100(seed=seed, physical_subsystems={"births": True})


def _union_women(world, low=25, high=40):
    out = []
    for name in world._actors:
        attrs = world.eng.node(world._actors[name])["attrs"]
        if (attrs.get("kin_sex") == "female" and low <= float(attrs["age"]) <= high
                and world._union_partner(name) is not None):
            out.append(name)
    return out


def _set_day(world, day):
    world.eng.set_attr(world._town, "day", float(day))


def _fixed_delivery(world, monkeypatch, **chances):
    values = {"stillbirth": 0.0, "maternal_death": 0.0, "infant_first_year_death": 0.0}
    values.update(chances)
    for key, value in values.items():
        monkeypatch.setitem(world.E.BIRTHS, key, value)


def _pregnant_woman(world):
    mother = _union_women(world)[0]
    _set_day(world, 100)
    world._conceive(mother, world._union_partner(mother), 100)
    return mother


def _strike_world():
    world = _actor_world(actors=(A, H))
    world.tick()
    world.mark_turn_start()
    return world


def _strike_pending(world, region="head"):
    return {"region": region, "attacker": A, "target": H, "attacker_side": {"skill": 0.0}}


# ------------------------------------------------------- helper contract


def test_same_state_purpose_and_parts_give_the_same_draw():
    world = _actor_world()
    key = ("illness", A, "fever", 7)
    assert world._stable_draw(*key) == world._stable_draw(*key)
    twin = _actor_world()
    assert world._stable_draw(*key) == twin._stable_draw(*key)


def test_changing_the_involved_actor_or_body_state_changes_the_draw():
    world = _actor_world()
    key = ("meal_illness", A, 3.0, "bread", 1)
    base = world._stable_draw(*key)
    twin = _actor_world()
    twin.eng.set_attr(twin._actors[A], "health_value", 0.25)
    assert twin._stable_draw(*key) != base

    twin = _actor_world()
    twin.eng.set_attr(twin._bodies[A], "mood", 99.0)
    assert twin._stable_draw(*key) != base

    twin = _actor_world()
    twin.eng.set_attr(twin._actors[A], "stamina", 0.1)
    assert twin._stable_draw(*key) != base


def test_explicit_actors_include_state_for_a_child_or_third_party():
    world = _actor_world()
    base = world._stable_draw("births", "infant", "Baby", 7)
    explicit = world._stable_draw("births", "infant", "Baby", 7, actors=(A, "Baby"))
    assert base != explicit
    twin = _actor_world()
    twin.eng.set_attr(twin._actors[A], "health_value", 0.25)
    assert twin._stable_draw("births", "infant", "Baby", 7, actors=(A, "Baby")) != explicit


def test_draw_order_a_then_b_matches_b_then_a_per_actor():
    first, second = _actor_world(), _actor_world()
    a_then_b = {name: first._stable_draw("illness", name, "fever", 7) for name in (A, "Ben")}
    b_then_a = {name: second._stable_draw("illness", name, "fever", 7) for name in ("Ben", A)}
    assert a_then_b == b_then_a


def test_purpose_parts_seed_and_day_matter():
    world = _actor_world()
    base = world._stable_draw("illness", A, "fever", 7)
    assert world._stable_draw("burial", A, "fever", 7) != base
    assert world._stable_draw("illness", A, "fever", 8) != base
    assert world._stable_draw("illness", A, "cough", 7) != base
    assert _actor_world(seed=305001)._stable_draw("illness", A, "fever", 7) != base


# ------------------------------------------------------------ meal illness


def test_meal_illness_draw_is_stable_and_state_dependent():
    world = _actor_world()
    key = ("meal_illness", A, 3.0, "bread", 1)
    base = world._stable_draw(*key)
    assert world._stable_draw(*key) == base
    assert world._stable_draw("meal_illness", A, 3.0, "bread", 2) != base
    assert world._stable_draw("meal_illness", A, 4.0, "bread", 1) != base

    world.eng.set_attr(world._bodies[A], "mood", 0.9)
    assert world._stable_draw(*key) != base


# ------------------------------------------------------- disease and burial


def test_disease_onset_draw_is_stable_and_state_dependent():
    world = _actor_world()
    key = ("illness", A, "fever", 7)
    base = world._stable_draw(*key)
    assert world._stable_draw(*key) == base
    world.eng.set_attr(world._actors[A], "health_value", 0.4)
    assert world._stable_draw(*key) != base


def test_burial_roll_is_stable_and_state_and_day_dependent():
    world = _actor_world()
    _set_day(world, 5)
    first = world._burial_roll(A)
    assert world._burial_roll(A) == first
    assert world._burial_roll(A) == world._stable_draw("burial", A, 5)
    assert world._burial_roll("Ben") != first

    world.eng.set_attr(world._actors[A], "health_value", 0.2)
    assert world._burial_roll(A) != first
    _set_day(world, 6)
    assert world._burial_roll(A) != first


# ----------------------------------------------------------------- births


@pytest.mark.parametrize("purpose", ("conceive", "name", "stillbirth", "sex", "maternal"))
def test_birth_draws_are_stable_and_state_or_day_dependent(purpose):
    first, second = _birth_world(), _birth_world()
    mother = _union_women(first)[0]
    assert _union_women(second)[0] == mother
    day = 100
    key = ("births", purpose, mother, day)
    base = first._stable_draw(*key, actors=(mother,))
    assert first._stable_draw(*key, actors=(mother,)) == base
    assert second._stable_draw(*key, actors=(mother,)) == base
    assert first._stable_draw("births", purpose, mother, day + 1, actors=(mother,)) != base

    first.eng.set_attr(first._actors[mother], "health_value", 0.25)
    assert first._stable_draw(*key, actors=(mother,)) != base


def test_birth_infant_draw_includes_the_child_and_the_mother(monkeypatch):
    first, second = _birth_world(), _birth_world()
    for world in (first, second):
        _fixed_delivery(world, monkeypatch)
    mother = _pregnant_woman(first)
    assert _pregnant_woman(second) == mother
    day = 100 + int(E.BIRTHS["gestation_days"])
    for world in (first, second):
        _set_day(world, day)
        world._births_day()
    child = first._births[-1]["child"]
    assert second._births[-1]["child"] == child

    key = ("births", "infant", child, day)
    base = first._stable_draw(*key, actors=(mother, child))
    assert second._stable_draw(*key, actors=(mother, child)) == base
    child_only = first._stable_draw(*key)
    assert child_only == second._stable_draw(*key), "the child is auto-included by name"
    assert child_only != base, "the mother's state is part of the delivery draw"

    first.eng.set_attr(first._actors[child], "health_value", 0.3)
    assert first._stable_draw(*key, actors=(mother, child)) != base

    third = _birth_world()
    _fixed_delivery(third, monkeypatch)
    _pregnant_woman(third)
    _set_day(third, day)
    third._births_day()
    child_name = third._births[-1]["child"]
    assert third._stable_draw(*key, actors=(mother, child_name)) == base


# ------------------------------------------------------------- strike aim


def test_strike_aim_uses_the_state_derived_draw_and_keeps_its_chance(monkeypatch):
    world = _strike_world()
    pending = _strike_pending(world)
    draw = determinism.state_uniform(
        world, "strike_aim", A, H, world._turn, "head", actors=(A, H))
    assert 0.0 < draw < 1.0

    monkeypatch.setitem(TABLES["strike_aim"], "base", min(1.0, draw + 1e-6))
    assert world._strike_locus(pending, None) == "head"
    assert world._strike_locus(pending, None) == "head", "same state, same answer"

    monkeypatch.setitem(TABLES["strike_aim"], "base", max(0.0, draw - 1e-6))
    assert world._strike_locus(pending, None) is None

    # A brace multiplies the same chance by brace_factor; the draw is unchanged.
    brace = float(TABLES["strike_aim"]["brace_factor"])
    monkeypatch.setitem(TABLES["strike_aim"], "base", draw * 1.5)
    assert world._strike_locus(pending, None) == "head"
    assert world._strike_locus(pending, "brace") is None
    assert brace < 1.0


def test_strike_aim_draw_is_attacker_target_and_turn_dependent():
    world = _strike_world()
    base = determinism.state_uniform(
        world, "strike_aim", A, H, world._turn, "head", actors=(A, H))
    world.eng.set_attr(world._actors[H], "health_value", 0.2)
    assert determinism.state_uniform(
        world, "strike_aim", A, H, world._turn, "head", actors=(A, H)) != base

    twin = _strike_world()
    assert determinism.state_uniform(
        twin, "strike_aim", A, H, twin._turn + 1, "head", actors=(A, H)) != base

    unaimed = _strike_pending(world, region=None)
    assert world._strike_locus(unaimed, None) is None


# ------------------------------------------------------------ harm locus


def test_harm_locus_uses_the_state_derived_draw():
    world = _actor_world()
    world._turn = 3
    weights = TABLES["harm_locus"]["injury"]
    first = world._body_harm_locus(A, "injury")
    assert first in weights
    assert world._body_harm_locus(A, "injury") == first
    assert world._body_harm_locus(A, "starvation") is None

    before = determinism.state_uniform(world, "harm_locus", A, "injury", 3)
    world.eng.set_attr(world._actors[A], "health_value", 0.4)
    assert determinism.state_uniform(world, "harm_locus", A, "injury", 3) != before


# ---------------------------------------------------------- animal births


def _animal_world(seed=305000):
    world = World(autonomous_actors=False, map_seed=seed)
    world.add_animal("Bess", "cow", cell=next(iter(world._map_cells)), sex="female")
    return world


def test_animal_birth_sex_is_stable_and_state_or_seed_dependent():
    share = float(E.ANIMALS["cow"]["birth_male_share"])
    first, second = _animal_world(), _animal_world()
    base = determinism.state_uniform(first, "animal_birth", "Bess", 0, 0, actors=("Bess",))
    assert determinism.state_uniform(second, "animal_birth", "Bess", 0, 0, actors=("Bess",)) == base
    assert determinism.state_uniform(_animal_world(305001), "animal_birth", "Bess", 0, 0,
                                     actors=("Bess",)) != base
    assert determinism.state_uniform(first, "animal_birth", "Bess", 1, 0, actors=("Bess",)) != base
    assert determinism.state_uniform(first, "animal_birth", "Bess", 0, 1, actors=("Bess",)) != base

    other = _animal_world()
    other.eng.set_attr(other._animals["Bess"], "hunger", 1.0)
    assert determinism.state_uniform(other, "animal_birth", "Bess", 0, 0, actors=("Bess",)) != base

    # The actual birth uses the same draw and the same species table.
    expected = "male" if base < share else "female"
    first._give_birth("Bess")
    young = next(name for name in first._animals if name != "Bess")
    assert first.eng.node(first._animals[young])["attrs"]["sex"] == expected


def test_animal_names_are_auto_included_in_state_draws():
    world = _animal_world()
    assert determinism.actor_state(world, "Bess") == {"name": "Bess", "present": False}
    assert determinism.animal_state(world, "Bess")["present"] is True
    assert determinism.entity_state(world, "Bess") == determinism.animal_state(world, "Bess")
    auto = determinism.state_uniform(world, "animal_birth", "Bess", 0, 0)
    explicit = determinism.state_uniform(world, "animal_birth", "Bess", 0, 0, actors=("Bess",))
    assert auto == explicit
    world.eng.set_attr(world._animals["Bess"], "hunger", 1.0)
    assert determinism.state_uniform(world, "animal_birth", "Bess", 0, 0) != auto


def test_animal_litter_size_and_sex_table_are_unchanged():
    assert E.ANIMALS["cow"]["litter"] == 1
    assert E.ANIMALS["pig"]["litter"] == 10
    for species in ("cow", "pig", "sheep", "dog", "cat", "chicken", "horse"):
        assert E.ANIMALS[species]["birth_male_share"] == 0.5


# ------------------------------------------------------- tables unchanged


def test_probability_tables_and_thresholds_are_unchanged():
    assert E.BIRTHS["stillbirth"] == pytest.approx(0.03)
    assert E.BIRTHS["maternal_death"] == pytest.approx(0.01)
    assert E.BIRTHS["infant_first_year_death"] == pytest.approx(0.25)
    assert E.BIRTHS["midwife_factor"] == pytest.approx(0.5)
    assert E.BIRTHS["conception_per_year"][0]["rate"] == pytest.approx(0.5)
    assert E.DISEASE["fever"]["onset_per_day"]["summer"] == pytest.approx(0.002)
    assert E.DISEASE["fever"]["onset_per_day"]["winter"] == pytest.approx(0.001)
    assert E.BURIAL["onset_chance"] == pytest.approx(0.05)
    assert E.BURIAL["risk_after_periods"] == 3
    assert E.meal_illness_risk("bread", 0.0) == pytest.approx(0.3)
    assert E.meal_illness_risk("bread", 1.0) == pytest.approx(0.0)
    aim = TABLES["strike_aim"]
    assert aim["base"] == pytest.approx(0.5)
    assert aim["skill_weight"] == pytest.approx(0.3)
    assert aim["brace_factor"] == pytest.approx(0.6)


# -------------------------------------------- serial vs partitioned chance run


CHANCE_SCENARIO = {
    "id": "ds02_chance_room",
    "name": "DS02 chance room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
    ],
    "initial": {"hour": 6.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {
        "metabolism": True, "illness": True, "births": True,
        "ecology": False, "decay": False, "practice": False, "training": False,
    },
    "buildings": [], "laws": [], "policies": [], "charters": [],
}


def _chance_game(executor):
    game = create_game(scenario=CHANCE_SCENARIO, seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False, executor=executor,
                       affordance_mode="menu")
    world = game.world
    # Start one tick before a day boundary so the dawn tick draws weather and
    # illness onset in the first step.
    world.eng.set_attr(world._town, "clock", 95.0)
    world.add_infrastructure("ds_well", kind="well")
    world.eng.set_attr(world._infrastructure["ds_well"], "failure_risk", 1.0)
    world.add_animal("DsDam", "cow", cell=next(iter(world._map_cells)), sex="female")
    world.eng.set_attr(world._animals["DsDam"], "gestating_days", 1.0)
    world.eng.set_attr(world._animals["DsDam"], "sire", "DsSire")
    return game


def test_serial_and_partitioned_chance_heavy_runs_match_semantically():
    games = {name: _chance_game(name) for name in ("serial", "partitioned")}
    for game in games.values():
        assert game.step()["status"] == "advanced"   # dawn tick: weather + illness onset
        game.world.pass_period(1)                    # infrastructure failure draw
        assert game.step()["status"] == "advanced"   # period effects: animal birth sex
    serial, partitioned = games["serial"].world, games["partitioned"].world

    # The run really exercised the chance streams.
    assert float(serial.eng.node(serial._infrastructure["ds_well"])["attrs"]["condition"]) < 1.0
    assert any(float(serial.eng.node(serial._animals[name])["attrs"].get("births", 0.0)) > 0.0
               for name in serial._animals)

    assert semantic_world_state(serial) == semantic_world_state(partitioned)
