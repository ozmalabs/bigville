"""Phase 015: roles, offices, and procedures come from the data pack.

The default pack's values reproduce the role literals the world used to hold: household kind by
role and cast group, the registrar and land-owner roles, the worker roles of the village work tick,
the winter grain reserve, and the lawmaking and justice stages. The acceptance fixture is
tests/fixtures/phase015_offices, a child pack (extends bigville) that renames the mayor to reeve
and the clerk to notary. Only its GOVERNANCE_OFFICES and HOUSEHOLDS tables differ. The tests run
land registration and a council vote in a world built on that pack, with no change to the code.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains import bigville_entities as DEFAULT          # noqa: E402
from domains.data_view import entities                     # noqa: E402
from worlds.bigville_world import BigvilleWorld            # noqa: E402

FIXTURE = os.path.join(_ROOT, "tests", "fixtures", "phase015_offices")


def _attrs(world, node):
    return world.eng.node(node)["attrs"]


def _child(tmp_path, tables):
    """A child pack that extends bigville, replacing the named tables (same format as Phase 014)."""
    root = tmp_path / "child_pack"
    (root / "frames").mkdir(parents=True)
    entries = []
    for name, value in tables.items():
        rel = f"frames/{name.lower()}.json"
        (root / rel).write_text(json.dumps({"_doc": "phase 015 test override", "_types": {},
                                            "tables": {name: value}}, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        entries.append({"name": name, "file": rel})
    (root / "pack.json").write_text(json.dumps({
        "format": 1, "name": "child_pack", "version": 1, "description": "phase 015 test child of bigville",
        "extends": "bigville", "tables": entries}), encoding="utf-8")
    return str(root)


# ------------------------------------------------------------- the default pack

def test_household_kind_follows_the_pack_roles_then_groups_then_the_fallback():
    w = BigvilleWorld()
    expected = {
        ("farmer", "low"): "farm_household",
        ("farm_labourer", "middle"): "farm_household",
        ("clerk", "low"): "institutional_household",
        ("councillor", "high"): "institutional_household",
        ("mayor", "middle"): "institutional_household",
        ("constable", "low"): "institutional_household",
        ("teacher", "high"): "institutional_household",
        ("midwife", "high"): "craft_household",
        ("baker", "high"): "craft_household",
        ("baker", "low"): "landless_household",
        ("hand", "middle"): "landless_household",
    }
    for (role, group), kind in expected.items():
        assert w.household_kind_for(role, group) == kind, (role, group)
    assert w.household_kind_for() == "landless_household"
    w.add_household("loner")
    assert _attrs(w, w._households["loner"])["kind"] == "landless_household"


def test_registrar_and_land_owner_roles_are_the_pack_values():
    w = BigvilleWorld()
    assert w._registrar_roles() == {"clerk"}
    assert w._land_holder_roles() == {"farmer"}
    assert DEFAULT.GOVERNANCE_OFFICES["clerk"]["registrar"] is True
    assert DEFAULT.HOUSEHOLDS["landless_household"]["fallback"] is True


def test_village_worker_roles_come_from_labour_tasks():
    w = BigvilleWorld()
    w.add_actor("Lia", role="farm_labourer", home_cell=(1, 1))
    w.add_actor("Fay", role="farmer", home_cell=(1, 1))
    w.add_actor("Bo", role="baker", home_cell=(1, 1))
    assert w._labour_workers("farm") == ["Lia"], "field labourers are the first worker role"
    assert w._labour_workers("bake") == ["Bo"]
    assert w._labour_workers("mill") == []
    w2 = BigvilleWorld()
    w2.add_actor("Fay", role="farmer", home_cell=(1, 1))
    assert w2._labour_workers("farm") == ["Fay"], "farmers take over when there are no labourers"


def test_the_winter_reserve_is_the_policy_parameters():
    w = BigvilleWorld()
    assert w._policy_parameters("winter_food_reserve") == {"minimum_grain": 4.0, "feed_periods": 4.0}
    assert DEFAULT.check_consistency()["errors"] == []


def test_the_grain_reserve_changes_when_the_pack_policy_changes(tmp_path):
    """A miller grinds grain only above 30 grain plus the reserve. With the default reserve of 4,
    35 grain is enough; with a child pack's minimum of 10, the reserve is 10 and 35 is not."""
    base = [dict(p) for p in DEFAULT.LOCAL_POLICIES]

    def grinds(world):
        world.add_actor("Mo", role="miller", trades=("miller",), home_cell=(1, 1))
        world.set_stock("grain", 35)
        world._village_work_tick(0)
        return world.busy("Mo")

    assert grinds(BigvilleWorld()) is True
    tighter = [dict(p, parameters={"minimum_grain": 10.0, "feed_periods": 4.0})
               if p["name"] == "winter_food_reserve" else p for p in base]
    child = BigvilleWorld(data_pack=_child(tmp_path, {"LOCAL_POLICIES": tighter}))
    assert child._policy_parameters("winter_food_reserve")["minimum_grain"] == 10.0
    assert grinds(child) is False


# ------------------------------------------------------- the acceptance fixture

def test_the_fixture_renames_two_offices_and_inherits_everything_else():
    child = entities(FIXTURE)
    assert "reeve" in child.GOVERNANCE_OFFICES and "mayor" not in child.GOVERNANCE_OFFICES
    assert child.GOVERNANCE_OFFICES["notary"]["registrar"] is True
    assert child.ITEMS == DEFAULT.ITEMS, "tables the fixture does not name are inherited"
    assert child.LAWMAKING_PROCEDURES == DEFAULT.LAWMAKING_PROCEDURES
    report = child.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []


def test_registrar_and_households_use_the_renamed_offices_with_no_code_change():
    w = BigvilleWorld(data_pack=FIXTURE)
    assert w._registrar_roles() == {"notary"}
    w.add_actor("Ada", role="notary", station="educated", home_cell=(1, 1))
    w.add_actor("Old", role="clerk", station="educated", home_cell=(1, 1))
    w._require_clerk("Ada")
    with pytest.raises(AssertionError, match="registrar office"):
        w._require_clerk("Old")
    assert w.household_kind_for("reeve", "middle") == "institutional_household"
    assert w.household_kind_for("clerk", "high") == "craft_household", "'clerk' is no longer an office here"


def test_land_registration_runs_under_the_renamed_registrar():
    w = BigvilleWorld(data_pack=FIXTURE)
    w.add_actor("Ada", role="notary", station="educated", home_cell=(1, 1))
    w.add_actor("Bram", role="farmer", station="educated", home_cell=(1, 1))
    w.add_household("farm", kind="farm_household")
    w.assign_household("Bram", "farm")
    w.add_land("north_field", use="arable", soil="loam", area=2.0)
    title = w.register_land("Ada", "north_field", "farm", holder_kind="household", witnesses=("Bram",))
    assert w.land_owner("north_field") == "farm"
    assert _attrs(w, title)["tenure"] == "freehold"
    assert w.land_record("north_field")["basis"] == "grant"
    deed = w.write_deed("Ada", "sale", "north_field", from_holder="farm", to_holder="Bram",
                        witnesses=("Bram",), consideration=12.0)
    w.register_deed("Ada", deed)
    assert _attrs(w, deed)["registered"] == 1.0
    assert w.land_owner("north_field") == "farm", "registering a deed does not change the title"


def test_a_council_vote_under_the_renamed_reeve_is_recorded_at_its_procedure_stages():
    w = BigvilleWorld(data_pack=FIXTURE)
    w.add_actor("Rhys", role="reeve", station="educated", home_cell=(1, 1))
    w.add_actor("Ada", role="notary", station="educated", home_cell=(1, 1))
    w.add_actor("Bram", role="farmer", station="educated", home_cell=(1, 1))
    proposal = w.propose_local_law("Bram", "market_day", title="Market Day")
    assert _attrs(w, proposal)["stage"] == "proposal"
    assert w.vote_on_law("Bram", proposal, True)
    assert w.vote_on_law("Ada", proposal, False)
    votes = w.eng.neighbours(w._town, "has_vote")
    assert sorted(_attrs(w, v)["stage"] for v in votes) == ["vote", "vote"]
    assert sorted(_attrs(w, v)["support"] for v in votes) == [0.0, 1.0]
    meeting = w.hold_council("Rhys", proposal)
    attrs = _attrs(w, meeting)
    assert attrs["chair"] == "Rhys"
    assert attrs["votes_for_observed"] == 1 and attrs["votes_against_observed"] == 1
    assert attrs["stage"] == "deliberation" and attrs["civic_action"] == "meeting"
    assert "market_day" not in w.law_names(), "a tally is a record, not enacted law"
    assert _attrs(w, proposal)["status"] == "open"


def test_cases_and_statements_carry_their_justice_stage():
    w = BigvilleWorld(data_pack=FIXTURE)
    w.add_actor("Ada", role="notary", station="educated", home_cell=(1, 1))
    w.add_actor("Bram", role="farmer", station="educated", home_cell=(1, 1))
    w.add_actor("Cy", role="constable", station="educated", home_cell=(1, 1))
    w.add_household("farm", kind="farm_household")
    w.add_land("north_field", use="arable", soil="loam", area=2.0)
    case = w.file_case("Bram", "Cy", charge="theft", law="public_order_law", evidence="a ledger")
    assert _attrs(w, case)["stage"] == "complaint" and _attrs(w, case)["civic_action"] == "case"
    statement = w.resolve_case("Ada", case, verdict="guilty", remedy="fine")
    assert _attrs(w, statement)["stage"] == "judgment"
    assert _attrs(w, statement)["civic_action"] == "statement"
    assert _attrs(w, case)["status"] == "open", "a statement does not close the case"
    dispute = w.file_land_dispute("Bram", "north_field", against="Cy", grounds="fence line")
    assert _attrs(w, dispute)["stage"] == "complaint"
    ruling = w.resolve_land_dispute("Ada", dispute, outcome="fence moved")
    assert _attrs(w, ruling)["stage"] == "judgment"
    assert _attrs(w, dispute)["status"] == "open"


# -------------------------------------------------- scenario-overridable procedures

def test_a_scenario_overrides_procedure_stages_and_the_records_follow_them():
    default = BigvilleWorld()
    assert "vote" in default.lawmaking_procedures() and "deliberation" in default.lawmaking_procedures()
    w = BigvilleWorld(scenario={"procedures": {"lawmaking": {
        "vote": None,
        "ballot": {"actor": "council", "civic_actions": ["vote"], "requires": ["quorum"]},
        "deliberation": None,
    }}})
    assert "ballot" in w.lawmaking_procedures() and "vote" not in w.lawmaking_procedures()
    assert "deliberation" not in w.lawmaking_procedures()
    assert w.justice_procedures() == default.justice_procedures(), "an untouched table is inherited"
    w.add_actor("Rhys", role="reeve", station="educated", home_cell=(1, 1))
    w.add_actor("Bram", role="farmer", station="educated", home_cell=(1, 1))
    proposal = w.propose_local_law("Bram", "market_day")
    w.vote_on_law("Bram", proposal, True)
    (vote,) = w.eng.neighbours(w._town, "has_vote")
    assert _attrs(w, vote)["stage"] == "ballot"
    meeting = w.hold_council("Rhys", proposal)
    assert _attrs(w, meeting)["stage"] == "", "no stage lists the meeting, so it records no stage"
    assert _attrs(w, meeting)["civic_action"] == "meeting"


def test_an_unknown_procedure_table_in_a_scenario_is_refused():
    with pytest.raises(ValueError, match="judicial"):
        BigvilleWorld(scenario={"procedures": {"judicial": {}}})


def test_procedure_stages_name_only_their_own_civic_actions_in_the_pack():
    assert DEFAULT.check_consistency()["errors"] == []
    for table, actions in ((DEFAULT.LAWMAKING_PROCEDURES, {"proposal", "meeting", "vote"}),
                           (DEFAULT.JUSTICE_PROCEDURES, {"case", "statement"})):
        listed = [a for spec in table.values() for a in spec.get("civic_actions", [])]
        assert set(listed) <= actions and len(listed) == len(set(listed))
