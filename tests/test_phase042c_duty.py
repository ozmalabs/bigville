"""Phase 042c: the lamplighter's lamp work is a duty, a drive on the same urgency scale as hunger and tiredness.

1. The due level: nothing pending is no duty; the level rises before the due time and after it, to 1.
2. The urgencies: hunger and tiredness reach 1.0 at starvation and at collapse.
3. The duty holds only when its urgency (role_identity x due level) beats the larger need: a dutiful resident forgoes
   a meal or a sleep, a lax one does not, and starvation or collapse ends a duty whatever the role.
4. The backend's choice (DeterministicBackend.decide) follows the holding rule.
5. The world publishes the lamp facts on the lamplighter's offers, and no one else is offered them.
6. No duty is offered with day and night off, and the duty tables are in the pack.

The three-day runs that show the timing (and the role_identity variation) are scripts, docs/phases/phase042c.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bigville.backends import ActorContext, DeterministicBackend  # noqa: E402
from bigville.backends.duty import due_level, duty_action, duty_drive, need_urgencies  # noqa: E402
from bigville.character import CharacterDefinition  # noqa: E402
from domains import bigville_entities as E  # noqa: E402
from worlds import daynight as dn  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402

DUTY = E.DUTIES["lamplighter"]
TIME = E.TIME
TPD = int(TIME["ticks_per_day"])
STARVE = float(E.CARE["starve_limit"])


def _clock_at(day, hour):
    offset = (hour - float(TIME["start_hour"])) % 24.0
    return day * TPD + int(round(offset * TPD / 24.0))


def _set_clock(w, clock):
    w.eng.set_attr(w._town, "clock", float(clock))
    w._advance_calendar()


def _on():
    w = World()
    w.add_actor("Bob", role="labourer", skill=0.9)
    w.add_actor("Ada", role="labourer", skill=0.9)
    dn.switch_on(w)
    return w


def _facts(light_pending=4.0, light_hours=-1.0, douse_pending=0.0, douse_hours=0.0, job="lamplighter"):
    return {"job": job, "light_pending": light_pending, "light_hours": light_hours,
            "douse_pending": douse_pending, "douse_hours": douse_hours}


LIGHT = {"action": "light", "lamp": "square_north_west", "lamplighter": True, "night": True, "lit": False,
         "duty": _facts()}
LATE = {"action": "light", "lamp": "square_north_west", "lamplighter": True, "night": True, "lit": False,
        "duty": _facts(light_hours=-3.0)}   # three hours after dusk: the level has reached 1
WALK = {"action": "move", "destination": (22, 14), "lamplighter": True, "night": True, "purpose": "station",
        "due": True, "duty": _facts()}
EAT = {"action": "eat", "kind": "bread", "meal_value": 1.0, "food": True, "score": 0.0}


def _character(role_identity, name="Bob"):
    return CharacterDefinition(character_id=name, name=name, identity={"role": "labourer", "life_stage": "adult"},
                               personality={"role_identity": float(role_identity)})


def _ctx(affordances, role_identity, hunger=0.0, energy=100.0):
    return SimpleNamespace(character=_character(role_identity), affordances=affordances,
                           observations={"hunger": hunger, "energy": energy})


def _decide(affordances, role_identity, hunger=0.0, energy=100.0):
    """The simple backend's decision for a resident with these offers. Its character is the lamplighter's."""
    context = ActorContext(_character(role_identity), 1,
                           {"hunger": hunger, "energy": energy, "hour": 22.0, "turn": 1,
                            "calendar": {"hour": 22.0, "clock": 0.0}, "heard_utterances": []},
                           [dict(o) for o in affordances])
    return DeterministicBackend(context.character).decide(context).major_action


# ------------------------------------------------------------- 1. the due level

def test_nothing_pending_is_no_duty():
    assert due_level(0.0, -1.0, DUTY) == 0.0


def test_the_level_is_zero_well_before_the_due_time_and_rises_over_the_lead():
    lead = float(DUTY["lead_hours"])
    assert due_level(4.0, lead + 1.0, DUTY) == 0.0
    assert due_level(4.0, lead, DUTY) == 0.0
    assert abs(due_level(4.0, lead / 2.0, DUTY) - float(DUTY["due_floor"]) / 2.0) < 1e-9
    assert abs(due_level(4.0, 0.0, DUTY) - float(DUTY["due_floor"])) < 1e-9


def test_the_level_rises_after_the_due_time_to_one_over_the_ramp():
    floor, ramp = float(DUTY["due_floor"]), float(DUTY["ramp_hours"])
    assert abs(due_level(4.0, -ramp / 2.0, DUTY) - (floor + (1.0 - floor) / 2.0)) < 1e-9
    assert due_level(4.0, -ramp, DUTY) == 1.0
    assert due_level(4.0, -ramp * 5.0, DUTY) == 1.0


# ------------------------------------------------------------- 2. the needs' urgencies

def test_hunger_and_tiredness_reach_one_at_starvation_and_collapse():
    assert need_urgencies({"hunger": 0.0, "energy": 100.0}) == (0.0, 0.0)
    assert need_urgencies({"hunger": STARVE, "energy": 100.0})[0] == 1.0
    assert need_urgencies({"hunger": 0.0, "energy": 5.0})[1] == 1.0
    assert abs(need_urgencies({"hunger": 0.0, "energy": 60.0})[1] - 40.0 / 95.0) < 1e-9   # (100 - 60) / (100 - 5)


# ------------------------------------------------------------- 3. the holding rule

def test_a_dutiful_lamplighter_holds_his_duty_over_a_meal():
    drive = duty_drive(_ctx([LIGHT, EAT], 0.9, hunger=2.0), _character(0.9))
    assert drive is not None and drive.holds and drive.urgency == 0.9 * drive.level


def test_a_lax_lamplighter_does_not_hold_his_duty_over_a_meal():
    drive = duty_drive(_ctx([LIGHT, EAT], 0.1, hunger=2.0), _character(0.1))
    assert drive is not None and not drive.holds


def test_starvation_ends_a_duty_whatever_the_role():
    assert duty_drive(_ctx([LIGHT, EAT], 1.0, hunger=STARVE), _character(1.0)).holds is False


def test_collapse_ends_a_duty_whatever_the_role():
    assert duty_drive(_ctx([LIGHT], 1.0, energy=5.0), _character(1.0)).holds is False


def test_a_dutiful_lamplighter_keeps_lamp_work_at_low_energy_above_collapse():
    assert duty_drive(_ctx([LATE], 0.9, energy=20.0), _character(0.9)).holds is True


def test_the_duty_urgency_grows_with_role_identity_and_the_forgone_meal_threshold_too():
    thresholds = []
    for role in (0.1, 0.5, 0.9):
        drive = duty_drive(_ctx([LIGHT], role), _character(role))
        assert drive.urgency == role * drive.level
        thresholds.append(drive.urgency)   # the hunger urgency at which he stops holding the duty
    assert thresholds == sorted(thresholds) and thresholds[0] < thresholds[-1]
    # Hunger at which each role gives way to a meal: monotone, a higher role forgoes more hunger.
    gives_way = [min(h for h in [i / 10.0 for i in range(0, 41)]
                     if not duty_drive(_ctx([LIGHT, EAT], role, hunger=h), _character(role)).holds)
                 for role in (0.1, 0.5, 0.9)]
    assert gives_way == sorted(gives_way) and gives_way[0] < gives_way[-1]


def test_with_no_duty_due_there_is_no_drive():
    assert duty_drive(_ctx([EAT], 0.9, hunger=2.0), _character(0.9)) is None
    not_due = {**LIGHT, "duty": _facts(light_pending=0.0)}
    assert duty_drive(_ctx([not_due], 0.9), _character(0.9)) is None
    early = {**LIGHT, "duty": _facts(light_hours=float(DUTY["lead_hours"]) + 2.0)}
    assert duty_drive(_ctx([early], 0.9), _character(0.9)) is None


def test_a_duty_that_does_not_hold_adds_a_bonus_to_its_offers_in_place_and_on_the_walk():
    drive = duty_drive(_ctx([LIGHT, WALK], 0.1, hunger=2.0), _character(0.1))
    assert drive.holds is False
    in_place = drive.bonus(LIGHT)
    walk = drive.bonus(WALK)
    assert abs(in_place - drive.urgency * (float(DUTY["score_weight"]) + float(DUTY["in_place_bonus"]))) < 1e-9
    assert abs(walk - drive.urgency * float(DUTY["score_weight"])) < 1e-9
    assert drive.bonus(EAT) == 0.0


# ------------------------------------------------------------- 4. the backend's choice

def test_a_dutiful_lamplighter_lights_the_lamp_before_he_eats():
    assert _decide([LIGHT, EAT], 0.9, hunger=2.0).action == "light"


def test_a_lax_lamplighter_eats_before_he_lights_the_lamp():
    assert _decide([LIGHT, EAT], 0.1, hunger=2.0).action == "eat"


def test_a_dutiful_lamplighter_walks_to_the_station_with_its_destination_and_a_continuation():
    proposal = _decide([WALK, EAT], 0.9, hunger=2.0)
    assert proposal.action == "move" and proposal.params == {"destination": (22, 14)}


def test_a_resident_with_no_duty_offer_takes_the_ordinary_choice():
    ordinary = _decide([EAT], 0.9, hunger=2.0)
    assert ordinary.action == "eat"


def test_duty_action_names_no_destination_for_a_lamp_and_a_destination_for_a_walk():
    assert duty_action({"action": "light", "lamp": "x"}) == ("light", {}, None)
    action, params, continuation = duty_action(WALK)
    assert action == "move" and params == {"destination": (22, 14)} and continuation.destination == (22, 14)


# ------------------------------------------------------------- 5. the world's facts

def test_the_square_publishes_its_lamp_facts_on_the_lamplighters_offers_at_night():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    offers = dn.lamp_options(w, lamplighter)
    lights = [o for o in offers if o["action"] == "light"]
    assert lights, "a light is offered at the station after dusk"
    facts = lights[0]["duty"]
    assert facts["job"] == "lamplighter" and facts["light_pending"] == float(len(w._dn_lamps))
    assert facts["douse_pending"] == 0.0 and facts["light_hours"] < 0.0


def test_by_day_the_lamps_publish_hours_until_dusk_and_the_lit_ones_publish_a_douse_due_since_dawn():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 12.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    facts = dn.lamp_facts(w, night=False)
    assert facts["light_pending"] == float(len(w._dn_lamps)) and facts["light_hours"] > 0.0
    assert facts["douse_pending"] == 0.0
    for node in w._dn_lamps.values():
        w.eng.set_attr(node, "lit", 1.0)
        w.eng.set_attr(node, "fuel", 1.0)
    facts = dn.lamp_facts(w, night=False)
    assert facts["douse_pending"] == float(len(w._dn_lamps)) and facts["douse_hours"] < 0.0


def test_at_the_station_before_dawn_with_the_lamps_lit_a_standby_rest_carries_the_douse_facts():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 5.0))           # dark, two hours before sunrise (about 07:30 at this pack's latitude)
    for node in w._dn_lamps.values():
        w.eng.set_attr(node, "lit", 1.0)
        w.eng.set_attr(node, "fuel", 1.0)
    w._move_actor_to(lamplighter, dn.station_cell(w))
    offers = dn.lamp_options(w, lamplighter)
    assert [o["action"] for o in offers] == ["rest"] and offers[0]["purpose"] == "standby"
    assert offers[0]["duty"]["douse_pending"] == float(len(w._dn_lamps)) and offers[0]["duty"]["douse_hours"] > 0.0


def test_a_standby_rest_is_not_offered_far_from_a_due_time():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 9.0))           # daylight, lamps dark: sunset is more than the lead away
    w._move_actor_to(lamplighter, dn.station_cell(w))
    assert all(o["action"] != "rest" for o in dn.lamp_options(w, lamplighter))


def test_no_lamp_is_pending_while_the_store_has_no_oil():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    w.set_stock(w.E.DAYNIGHT["oil_item"], 0.0)
    assert dn.lamp_facts(w, night=True)["light_pending"] == 0.0


def test_only_the_lamplighter_is_offered_a_duty():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to("Ada", dn.station_cell(w))
    assert dn.lamp_options(w, "Ada") == []
    w._move_actor_to(lamplighter, dn.station_cell(w))
    offers = dn.lamp_options(w, lamplighter)
    assert any(o["action"] == "light" for o in offers)
    assert all("duty" in o for o in offers if o["action"] in {"light", "douse", "move"})


def test_with_day_and_night_off_no_offer_carries_a_duty():
    w = World()
    w.add_actor("Bob", role="labourer", skill=0.9)
    assert dn.lamp_options(w, "Bob") == []


# ------------------------------------------------------------- 6. the tables

def test_the_duty_table_is_in_the_pack_and_the_test_pack_has_none():
    from domains import world_affordances as WA
    assert "lamplighter" in WA.DUTIES
    assert set(DUTY["acts"]) == {"light", "douse"}
    assert float(DUTY["lead_hours"]) == float(E.DAYNIGHT["lamplighter_dusk_lead_hours"])
