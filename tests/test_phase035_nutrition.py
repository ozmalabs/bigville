"""Phase 035: nutrition. Variety, protein and taste.

Energy per meal falls as the same food repeats within a period (specific satiety), so a diet of one food yields less
each meal and a varied diet does not. Protein enters a body store; a store below need accrues deficiency and a store
above it recovers. Spice adds to a meal's pleasure, consumes a unit and is not scaled by satiety. Mood moves toward
each meal's satisfaction, so a monotonous diet sinks it over days. The read-offs reach the options and the body.
Choosing what to eat, and whether to spice, is the backend's choice; these tests call the world directly.
"""
import pytest

import domains.bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World


def _tom():
    w = World(autonomous_actors=False, physical_subsystems={"monotony": True})
    w.add_actor("Tom", role="hand", home_cell=(1, 1))
    return w


def _meal(w, kind, *, spiced=False):
    """Stock one unit of `kind`, hold it, and eat it at hunger 1.0 (room for the relief). Returns the hunger relieved."""
    w.set_stock(kind, 1)
    w.fetch("Tom", kind, 1)
    w.eng.set_attr(w._actor("Tom"), "hunger", 2.0)
    assert w.eat("Tom", kind, spiced=spiced)
    return round(2.0 - float(w.hunger("Tom")), 6)


def test_every_food_has_a_protein_and_a_taste_and_the_self_test_stays_clean():
    foods = [k for k, spec in E.ITEMS.items() if spec.get("food") and not spec.get("scraps_of")]
    assert len(foods) > 50
    for kind in foods:
        spec = E.ITEMS[kind]
        assert isinstance(spec.get("protein"), (int, float)) and spec["protein"] >= 0.0, f"{kind} needs protein"
        assert isinstance(spec.get("taste"), (int, float)) and 0.0 <= spec["taste"] <= 1.0, f"{kind} needs taste"
    for kind in E.NUTRITION["spice_kinds"]:
        assert kind in E.ITEMS, f"spice {kind} must be an item"
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []


def test_bread_every_meal_lowers_the_energy_per_meal_and_raises_monotony():
    w = _tom()
    relief = [_meal(w, "bread") for _ in range(3)]
    assert relief[0] == pytest.approx(1.0), "a fresh loaf relieves a whole period"
    assert relief[0] > relief[1] > relief[2] > 0.0, "the same food yields less each meal"
    assert w.nutrition("Tom")["monotony"] > 0.0


def test_a_varied_diet_gives_each_food_its_full_value():
    w = _tom()
    for kind in ("bread", "cheese", "apple", "honey"):
        assert _meal(w, kind) == pytest.approx(E.feeds(kind)), f"{kind} is fresh in a varied diet"


def test_a_protein_poor_diet_accrues_deficiency_and_a_protein_rich_one_recovers():
    w = _tom()
    for _ in range(6):                                       # apples: about 1 g of protein each
        for _ in range(3):
            _meal(w, "apple")
        w.pass_period(1)
    peak = w.nutrition("Tom")["deficiency"]
    assert peak > 0.3, "a diet short of protein accrues deficiency"
    for _ in range(4):                                       # cheese: 300 g of protein a unit
        _meal(w, "cheese")
        w.pass_period(1)
    assert w.nutrition("Tom")["deficiency"] < peak, "a protein-rich diet recovers the deficiency"


def test_spice_adds_pleasure_consumes_a_unit_and_lifts_a_monotonous_meal():
    plain, spiced = _tom(), _tom()
    for w in (plain, spiced):
        for _ in range(3):
            _meal(w, "bread")                                # a monotonous run, identical in both worlds
    spiced.set_stock("pepper", 2)
    spiced.fetch("Tom", "pepper", 2)
    _meal(plain, "bread")
    _meal(spiced, "bread", spiced=True)
    taste = E.ITEMS["bread"]["taste"]
    assert plain.nutrition("Tom")["meal_pleasure"] == pytest.approx(taste)
    assert spiced.nutrition("Tom")["meal_pleasure"] == pytest.approx(min(1.0, taste + E.NUTRITION["spice_bonus"]))
    assert spiced.inventory_qty("Tom", "pepper") == pytest.approx(1.0), "one spice unit is consumed"
    assert plain.inventory_qty("Tom", "pepper") == 0.0
    assert spiced.body_state("Tom")["mood"] > plain.body_state("Tom")["mood"], "the spice lifts a boring meal"


def test_spice_without_a_unit_adds_nothing():
    w = _tom()
    _meal(w, "bread", spiced=True)
    assert w.nutrition("Tom")["meal_pleasure"] == pytest.approx(E.ITEMS["bread"]["taste"])


def test_mood_sinks_over_days_on_one_food_and_holds_on_a_varied_diet():
    def run(kinds_per_day):
        w = _tom()
        history = []
        for _ in range(8):
            for kind in kinds_per_day:
                _meal(w, kind)
            w.pass_period(1)
            history.append(w.body_state("Tom")["mood"])
        return history

    monotonous = run(["bread", "bread", "bread"])            # bread at every meal
    varied = run(["cheese", "stew", "honey"])                # three foods, each once a day
    assert monotonous[-1] < monotonous[1], "one food sinks the mood day by day"
    assert varied[-1] > monotonous[-1] + 0.1, "a varied diet holds the mood"


def test_the_read_offs_reach_the_options_and_the_body():
    w = _tom()
    _meal(w, "bread")
    w.set_stock("bread", 1)
    w.fetch("Tom", "bread", 1)
    options = [o for o in w._actor_options("Tom") if o.get("action") == "eat" and o.get("kind") == "bread"]
    assert options, "a held loaf is an eat option"
    assert options[0]["monotony"] > 0.0
    assert options[0]["meal_pleasure"] == pytest.approx(E.ITEMS["bread"]["taste"])
    state = w.body_state("Tom")
    for key in ("deficiency", "meal_pleasure", "monotony", "protein_store"):
        assert key in state
    assert state["monotony"] == pytest.approx(w.nutrition("Tom")["monotony"])


def test_a_protein_shortfall_in_the_founding_balance_is_flagged():
    supply, need = E.protein_balance(E.BALANCE_SCENARIO)
    assert supply >= need, "the founding staple gives the protein need"
    supply, need = E.protein_balance(dict(E.BALANCE_SCENARIO, food_per_resident=0.9))
    assert supply < need, "a staple too thin for the protein need is a shortfall"


def test_the_reporter_publishes_the_town_nutrition_read_offs():
    from bigville.reporting import SimulationReporter
    w = _tom()
    _meal(w, "bread")
    counts = SimulationReporter(w).nutrition()
    assert counts["residents"] == 1 and counts["short_of_protein"] == 0
    assert counts["protein_store_mean"] == pytest.approx(E.ITEMS["bread"]["protein"])
    assert "nutrition" in SimulationReporter(w).report(sample_size=5)


def test_the_satisfaction_form_scales_taste_by_satiety_and_adds_the_spice_bonus_unscaled():
    taste = E.ITEMS["bread"]["taste"]
    assert E.satisfaction_of_meal("bread", 0.0) == pytest.approx(taste)
    assert E.satisfaction_of_meal("bread", 0.5) == pytest.approx(taste * 0.5)
    assert E.satisfaction_of_meal("bread", 0.5, 0.2) == pytest.approx(taste * 0.5 + 0.2)


def test_with_the_monotony_switch_off_a_repeated_loaf_keeps_its_energy_and_still_tracks_satiety():
    w = World(autonomous_actors=False)
    assert w.physical_subsystems["monotony"] is False
    w.add_actor("Tom", role="hand", home_cell=(1, 1))
    relief = [_meal(w, "bread") for _ in range(3)]
    assert relief == [pytest.approx(1.0)] * 3, "off, the same food relieves the same each meal"
    assert w.nutrition("Tom")["monotony"] > 0.0, "satiety is still tracked for pleasure and mood"
