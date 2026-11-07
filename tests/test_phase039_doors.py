"""Phase 039: doors and confinement.

A building may carry one door: a Lock node (Phase 030 fields, lock_strength read by Phase 050) on its Place, with an
optional entrance cell on the footprint's perimeter. A walking step that crosses the footprint boundary is refused
`door_locked` while the door is locked. While it is unlocked, a crossing is allowed only at the entrance. Lock and
unlock work on a door by the building's name, from its entrance or a cell next to it. Forcing a door is an open
attempt (Phase 050) on the lock. Evasion respects a locked door. The jail is a BUILDINGS row with `founding: False`,
locked when built or added by a scenario. The world attaches no law or sentence to it.
"""
from __future__ import annotations

import json
import os

import pytest

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAIL_AT = (20, 20)          # the scenario's requested anchor; the site is the nearest clear footprint
LOCK_ID = E.BUILDINGS["jail"]["door"]["lock_id"]
A, B = "Ada", "Hal"


def _jail(*, locked=True, keys_required=None, tick=True):
    """A world whose only building is a jail, added by a scenario as the BUILDINGS row allows. Returns the world and
    the cells: the jail's south-west corner, its entrance (bottom middle), the cell outside the entrance, and the cell
    two steps out. With `tick`, the turn clock runs and a turn has started."""
    door = dict(E.BUILDINGS["jail"]["door"], locked=locked)
    if keys_required is not None:
        door["keys_required"] = keys_required
    building = {"kind": "jail", "name": "jail", "cell": list(JAIL_AT), "spec": {"door": door}}
    w = World(autonomous_actors=False, scenario={"id": "doors", "name": "doors", "buildings": [building]})
    x, y, _w, _h = w._building_sites["jail"]
    cells = {"corner": (x, y), "entrance": (x + 1, y + 2), "outside": (x + 1, y + 3), "far": (x + 1, y + 5),
             "west": (x - 1, y)}
    if tick:
        w.tick()
        w.mark_turn_start()
    return w, cells


def _lock_attrs(w):
    return w.eng.node(w._door_lock(w._places["jail"]))["attrs"]


def _resident(w, name, cell, *, key=False):
    w.add_actor(name, role="hand", home_cell=cell)
    w._move_actor_to(name, cell)
    if key:
        w.give_key(name, opens=LOCK_ID)


def _reason(w, name):
    return w.last_outcome(name)["reason"]


def _walk(w, name, destination):
    """One walk as a major action in a fresh turn (each walk claims the turn's slot)."""
    w.mark_turn_start()
    return w.major_action(name, "move", destination=destination)


# ------------------------------------------------------------------ data and wiring

def test_the_jail_is_a_catalogue_building_that_is_not_standing_at_founding():
    row = E.BUILDINGS["jail"]
    assert row["founding"] is False
    assert "jail" not in E.founding_buildings()
    assert row["door"]["locked"] is True, "built or added by a scenario, the jail starts locked"
    assert any(p["building"] == "jail" for p in E.BUILDING_PROJECTS.values()), "a project raises it when built"


def test_founding_buildings_have_no_door_so_the_default_village_is_unchanged():
    assert [name for name, spec in E.BUILDINGS.items() if spec.get("founding", True) and "door" in spec] == []
    assert World(autonomous_actors=False)._door_places == {}


def test_the_door_refusal_code_is_in_both_packs_with_a_description():
    for pack in ("bigville", "test_hamlet"):
        reasons = json.load(open(os.path.join(ROOT, "packs", pack, "world", "refusal_reasons.json")))
        assert reasons["tables"]["REFUSAL_REASONS"]["door_locked"]["description"].strip(), pack


def test_the_self_test_rejects_a_door_whose_entrance_is_off_the_perimeter_or_whose_lock_is_shared(monkeypatch):
    jail = E.BUILDINGS["jail"]
    errors, warnings, info = [], [], []
    monkeypatch.setitem(E.BUILDINGS, "jail", dict(jail, door=dict(jail["door"], entrance=[1, 1])))
    E._check_doors(errors, warnings, info)
    assert any("perimeter" in e for e in errors), errors
    errors.clear()
    monkeypatch.setitem(E.BUILDINGS, "jail", dict(jail, door=dict(jail["door"], lock_id=E.STORE_LOCK["lock_id"])))
    E._check_doors(errors, warnings, info)
    assert any("shared" in e for e in errors), errors


# ------------------------------------------------------------------ the locked door

def test_a_resident_inside_a_locked_building_cannot_leave():
    w, c = _jail()
    _resident(w, A, c["entrance"])
    assert _walk(w, A, c["outside"]) is False
    assert _reason(w, A) == "door_locked"
    assert w.actor_position(A) == c["entrance"], "the step across the locked door is not taken"


def test_a_resident_outside_a_locked_building_cannot_enter_without_the_key():
    w, c = _jail()
    _resident(w, A, c["outside"])
    assert _walk(w, A, c["entrance"]) is False and _reason(w, A) == "door_locked"
    assert w.actor_position(A) == c["outside"]


def test_unlocking_with_the_key_lets_the_resident_out():
    w, c = _jail()
    _resident(w, A, c["entrance"], key=True)
    assert w.unlock(A, "jail") is True
    assert _lock_attrs(w)["locked"] == 0.0
    assert _walk(w, A, c["outside"]) is True
    assert w.actor_position(A) == c["outside"]


def test_a_keyholder_outside_cannot_walk_in_until_the_door_is_unlocked():
    w, c = _jail()
    _resident(w, A, c["outside"], key=True)
    assert _walk(w, A, c["entrance"]) is False and _reason(w, A) == "door_locked"
    assert w.unlock(A, "jail") is True
    assert _walk(w, A, c["entrance"]) is True
    assert w.actor_position(A) == c["entrance"]


def test_lock_and_unlock_need_the_key_and_a_place_at_the_entrance_or_next_to_it():
    w, c = _jail(tick=False)
    _resident(w, A, c["far"], key=True)
    assert w.unlock(A, "jail") is False and w._refusal_code == "not_in_reach"
    w._move_actor_to(A, c["outside"])
    assert w.unlock(A, "jail") is True, "the cell next to the entrance is in reach"
    w._move_actor_to(A, c["entrance"])
    assert w.lock(A, "jail") is True, "the entrance itself is in reach"
    assert _lock_attrs(w)["locked"] == 1.0


def test_a_locked_door_is_not_opened_by_someone_without_the_key():
    w, c = _jail(tick=False)
    _resident(w, A, c["outside"])
    assert w.unlock(A, "jail") is False and w._refusal_code == "no_key"
    assert _lock_attrs(w)["locked"] == 1.0


def test_a_door_with_two_keyholders_opens_only_when_both_have_turned_their_keys():
    w, c = _jail(keys_required=2, tick=False)
    _resident(w, A, c["outside"], key=True)
    _resident(w, B, c["outside"], key=True)
    assert w.unlock(A, "jail") is True and _lock_attrs(w)["locked"] == 1.0, "one keyholder is not enough"
    assert w.unlock(A, "jail") is False and w._refusal_code == "already_authorised"
    assert w.unlock(B, "jail") is True and _lock_attrs(w)["locked"] == 0.0


# ------------------------------------------------------------------ the unlocked door and the walk

def test_an_unlocked_door_is_crossed_only_at_the_entrance():
    w, c = _jail(locked=False, tick=False)
    assert w._door_allows(c["entrance"], c["outside"]) is True
    x, y = c["corner"]
    assert w._door_allows((x, y + 1), (x - 1, y + 1)) is False, "a wall cell away from the entrance is shut"
    assert w._door_allows((x, y), (x - 1, y)) is False


def test_a_walk_to_an_unlocked_entrance_goes_round_to_it_and_no_other_wall_cell():
    w, c = _jail(locked=False, tick=False)
    _resident(w, A, c["west"])
    cell = c["west"]
    for _ in range(200):
        if cell == c["entrance"]:
            break
        nxt = w._movement_step(cell, c["entrance"])
        assert nxt is not None and w._door_allows(cell, nxt)
        w._move_actor_to(A, nxt)
        cell = nxt
    assert w.actor_position(A) == c["entrance"]


def test_a_locked_door_shuts_the_walk_and_unlocking_reopens_it():
    w, c = _jail(tick=False)
    assert w._door_stops_walk(c["outside"], c["corner"]) is True
    w.eng.set_attr(w._door_lock(w._places["jail"]), "locked", 0.0)
    assert w._door_stops_walk(c["outside"], c["corner"]) is False


# ------------------------------------------------------------------ attempts and evasion

def test_forcing_the_door_is_an_open_attempt_on_its_lock_by_its_building_name():
    w, c = _jail(tick=False)
    _resident(w, A, c["far"])
    w.mark_turn_start()
    assert w.major_action(A, "attempt", verb="force", target="jail") is False
    assert _reason(w, A) == "not_in_reach"
    w._move_actor_to(A, c["outside"])
    w.mark_turn_start()
    assert w.major_action(A, "attempt", verb="force", target="jail", intensity=1.0) is True
    record = w.eng.node(w._actors[A])["attrs"]["last_attempt"]
    assert record["verb"] == "force" and record["target"] == "jail"
    assert record["outcome"] == "progress" and _lock_attrs(w)["locked"] == 1.0, "one blow does not break the lock"


def test_blows_wear_the_lock_down_and_the_door_stays_shut():
    """Forcing accrues progress on the lock blow by blow, and the lock stays shut. A tired resident's blow is
    refused (the loop stops there). Breaking a lock takes many blows across rests, which this test does not run."""
    w, c = _jail(tick=True)
    _resident(w, A, c["outside"])
    progress = []
    for _ in range(3):
        w.tick()
        w.mark_turn_start()
        if not w.major_action(A, "attempt", verb="force", target="jail", intensity=1.0):
            break
        progress.append(_lock_attrs(w)["lock_progress"])
    assert len(progress) >= 1 and progress == sorted(progress) and progress[0] > 0.0
    assert _lock_attrs(w)["locked"] == 1.0
    assert w._door_stops_walk(c["outside"], c["corner"]) is True


def test_an_attempt_at_a_door_that_is_already_open_is_refused():
    w, c = _jail(locked=False, tick=False)
    _resident(w, A, c["outside"])
    w.mark_turn_start()
    assert w.major_action(A, "attempt", verb="pry", target="jail") is False
    assert _reason(w, A) == "already_unlocked"


def test_evasion_never_steps_across_a_locked_door():
    w, c = _jail(tick=False)
    _resident(w, B, c["entrance"])
    assert w._evade_cell(B) != c["outside"], "the outside cell is across the locked door"
    assert w._evade_cell(B) is None or w._door_allows(c["entrance"], w._evade_cell(B))


def test_a_town_with_no_door_is_untouched_by_the_door_rule():
    w = World(autonomous_actors=False)
    assert w._door_allows((5, 5), (5, 6)) is True
    assert w._door_stops_walk((5, 5), (5, 6)) is False


def test_the_door_state_is_plain_graph_data():
    w, _c = _jail(tick=False)
    attrs = _lock_attrs(w)
    assert set(attrs) == {"lock_id", "locked", "keys_required", "lock_strength", "lock_condition", "lock_progress"}
    assert all(isinstance(v, float) for v in attrs.values())


@pytest.mark.parametrize("name", ["store", "jail"])
def test_lock_by_name_resolves_the_store_and_the_door(name):
    w, _c = _jail(tick=False)
    node, reach = w._lockable(name)
    assert w.eng.node(node)["type"] == "Lock"
    assert reach and all(isinstance(cell, tuple) for cell in reach)
