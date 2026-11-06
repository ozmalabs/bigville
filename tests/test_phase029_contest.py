"""Phase 029: contested actions, reaction turns and taking.

A take is a physical contest on one cell. Each side's force is strength, size, life stage and the exhaustion
step; skill enters through a technique multiplier. The holder may react (resist, brace, yield, evade) when it is
alive, awake, aware of the taker and fast enough. The outcome is completed, dropped on the cell, held, or
redirected. Costs fall on stamina. Nothing is random, and the world attaches no ownership or crime to a take.
"""
from __future__ import annotations

import numpy as np
import pytest

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.human import HumanBackend
from bigville.game import BigvilleGame
from domains import bigville_entities as E
from domains import population as P
from worlds.bigville_world import BigvilleWorld as World

A, H = "Ada", "Hal"


def _pair(*, cell_of_holder=None):
    """Two residents on one cell (the taker Ada and the holder Hal), a tick in, sight snapshot taken."""
    w = World(autonomous_actors=False)
    cells = sorted(w._map_cells)
    cell = cells[len(cells) // 2]
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w._move_actor_to(A, cell)
    w._move_actor_to(H, cell if cell_of_holder is None else cell_of_holder)
    w.tick()
    w.mark_turn_start()
    return w


def _body(w, name, **attrs):
    for key, value in attrs.items():
        w.eng.set_attr(w._bodies[name], key, float(value))


def _take(w, attacker=A, holder=H, kind="coin", amount=4.0, reaction=None):
    pending, reason = w.take_begin(attacker, {"source": holder, "kind": kind, "amount": amount})
    if pending is None:
        return None, None, reason
    applied, code = w.take_resolve(pending, reaction)
    return pending, applied, code


def _plain(value):
    """True when a value is plain data (no objects, no random generators)."""
    if isinstance(value, dict):
        return all(isinstance(k, str) and _plain(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_plain(v) for v in value)
    return value is None or isinstance(value, (str, int, float, bool))


def _far_cell(w, cell):
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) > int(E.HEARING["sight_range"]))


def _neighbour(w, cell):
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) == 1)


# ------------------------------------------------------------------ pack and wiring

def test_the_contest_tables_and_codes_exist_in_the_pack():
    assert E.CONTEST["base_cost"] > 0 and E.CONTEST["decisive_margin"] > E.CONTEST["narrow_margin"]
    assert {"held", "evaded", "dropped"} <= set(E.REFUSAL_REASONS)
    assert "take" in E.MAJOR_ACTIONS and E.MAJOR_ACTIONS["take"]["description"].strip()
    assert {"take", "yield"} <= set(E.HANDOVER_KINDS)
    assert E.SKILLS["fighting"]["learning"] == "physical"
    assert any("fighting" in c["skills"] for c in E.SKILL_CLUSTERS.values())


def test_a_resident_starts_with_the_fighting_baseline_and_a_constable_with_the_trade_level():
    w = _pair()
    assert w.skill_level(H, "fighting") >= E.CONTEST["baseline_level"] - 1e-9
    w.add_actor("Cy", role="constable", home_cell=w.actor_position(H))
    assert w.skill_level("Cy", "fighting") == pytest.approx(E.ACTOR_DEFAULTS["skill"])


def test_the_draw_gives_a_size_and_leaves_the_earlier_draws_in_place():
    drawn = P.draw_person_capacities(np.random.default_rng(1), age=35.0)
    assert E.SIZE["floor"] <= drawn["size"]
    first = np.random.default_rng(1).normal(E.APTITUDE["mean"], E.APTITUDE["sd"])
    assert drawn["aptitude"] == pytest.approx(round(max(E.APTITUDE["floor"], first), 4))
    rng = np.random.default_rng(2)
    child = np.mean([P.draw_size(rng, age=5.0) for _ in range(400)])
    adult = np.mean([P.draw_size(rng, age=30.0) for _ in range(400)])
    assert child < 0.6 and 0.95 < adult < 1.05


def test_the_body_takes_the_size_from_the_capacity_draw():
    import zlib
    w = _pair()
    w.draw_capacities(H, seed=7)
    rng = np.random.default_rng((7 * 1_000_003) ^ zlib.crc32(H.encode()))
    expected = P.draw_person_capacities(rng, age=30.0)["size"]
    assert w.eng.node(w._bodies[H])["attrs"]["size"] == pytest.approx(expected)


# ------------------------------------------------------------------ who prevails and what it costs

def test_a_strong_rested_resident_takes_from_a_weak_one_and_not_the_reverse():
    strong = _pair()
    _body(strong, A, str_base=1.3)
    _body(strong, H, str_base=0.7)
    _pending, applied, _ = _take(strong, reaction="resist")
    assert applied is True and strong.coin(A) == pytest.approx(14.0)

    weak = _pair()
    _body(weak, A, str_base=0.7)
    _body(weak, H, str_base=1.3)
    pending, applied, code = _take(weak, reaction="resist")
    assert applied is False and code == "held"
    assert pending["result"]["outcome"] == "held" and weak.coin(A) == pytest.approx(10.0)


def test_a_light_skilled_holder_redirects_a_heavier_unskilled_taker_and_pays_less():
    w = _pair()
    _body(w, A, size=1.15)
    _body(w, H, size=0.9)
    w.set_skill_level(H, "fighting", 0.9)
    w.set_skill_level(A, "fighting", 0.0)
    pending, applied, code = _take(w, reaction="resist")
    result = pending["result"]
    assert pending["offer"]["eligible"] and "resist" in pending["offer"]["options"]
    assert result["outcome"] == "redirected" and result["redirected"] and applied is False and code == "held"
    assert result["target_cost"] < E.CONTEST["base_cost"] * 0.5          # little, against a full share of 0.2
    assert result["attacker_cost"] > result["target_cost"] * 2             # the taker pays more

    unskilled = _pair()
    _body(unskilled, A, size=1.15)
    _body(unskilled, H, size=0.9)
    unskilled.set_skill_level(A, "fighting", 0.0)
    unskilled.set_skill_level(H, "fighting", 0.0)
    unskilled.effective_skill = lambda actor, skill: 0.0                 # no skill at all
    pending_u, _applied, _code = _take(unskilled, reaction="resist")
    share = min(1.0, pending_u["attacker_side"]["force"] / pending_u["target_side"]["force"])
    assert pending_u["result"]["target_cost"] == pytest.approx(E.CONTEST["base_cost"] * share)
    assert pending_u["result"]["target_cost"] > result["target_cost"] * 3


def test_a_small_child_grabbing_a_strong_smith_costs_the_smith_nothing_and_the_child_all_it_has():
    w = _pair()
    w.eng.set_attr(w._actors[A], "life_stage", "child")
    # A child at reserve 0.15 is at the second exhaustion band, so its force is a third of its size force.
    _body(w, A, size=0.6, stamina_reserve=0.15)
    _body(w, H, stamina_reserve=1.0)
    pending, applied, _code = _take(w, reaction="resist")
    result = pending["result"]
    assert result["target_cost"] == 0.0
    assert w.stamina_reserve(H) == pytest.approx(1.0)
    assert w.eng.node(w._actors[H])["attrs"].get("major_action_used", 0.0) == 0.0
    assert result["attacker_cost"] > 0.0 and w.stamina_reserve(A) == pytest.approx(0.0)
    assert applied is False


def test_a_collapsing_smith_pays_more_for_the_same_child():
    healthy = _pair()
    healthy.eng.set_attr(healthy._actors[A], "life_stage", "child")
    _body(healthy, A, size=0.6, stamina_reserve=0.15)
    healthy_pending, _a, _c = _take(healthy, reaction="resist")

    tired = _pair()
    tired.eng.set_attr(tired._actors[A], "life_stage", "child")
    _body(tired, A, size=0.6, stamina_reserve=0.15)
    _body(tired, H, stamina_reserve=0.25)
    tired_pending, applied, _c = _take(tired, reaction="resist")
    assert healthy_pending["result"]["target_cost"] == 0.0
    assert tired_pending["result"]["target_cost"] > 0.0
    assert applied is False and tired_pending["result"]["outcome"] == "held"


def test_two_evenly_matched_residents_each_spend_about_the_same():
    w = _pair()
    pending, _applied, _code = _take(w, reaction="resist")
    result = pending["result"]
    assert result["attacker_cost"] > 0.0
    assert result["attacker_cost"] == pytest.approx(result["target_cost"], abs=0.01)


def test_a_narrow_margin_drops_the_goods_on_the_cell():
    # A passive holder (no reaction) brings grip x force = 0.5. A taker of strength 0.5 scores 0.6, a margin of
    # (0.6 - 0.5) / (0.6 + 0.5) = 0.09, between narrow (0.05) and decisive (0.2): the goods fall on the cell.
    w = _pair()
    _body(w, A, str_base=0.5)
    w.set_stock("bread", 10.0)
    assert w._move_stock_to_inventory(H, "bread", 2.0)
    pending, applied, code = _take(w, kind="bread", amount=2.0, reaction=None)
    assert pending["result"]["outcome"] == "dropped" and applied is False and code == "dropped"
    assert w.inventory_qty(H, "bread") == pytest.approx(0.0)
    assert w.inventory_qty(A, "bread") == pytest.approx(0.0)
    dropped = [w.eng.node(node)["attrs"] for node in w._dropped_stocks.values()]
    assert any(d["kind"] == "bread" and d["qty"] == pytest.approx(2.0) for d in dropped)


def test_the_same_taker_is_held_off_when_the_holder_resists():
    # Resisting brings the holder's full force with technique (score 1.2), so the taker's 0.6 loses outright.
    w = _pair()
    _body(w, A, str_base=0.5)
    w.set_stock("bread", 10.0)
    assert w._move_stock_to_inventory(H, "bread", 2.0)
    pending, applied, code = _take(w, kind="bread", amount=2.0, reaction="resist")
    assert pending["result"]["outcome"] == "held" and applied is False and code == "held"
    assert w.inventory_qty(H, "bread") == pytest.approx(2.0)


def test_a_decisive_win_completes_a_stock_take_through_the_give_path():
    w = _pair()
    _body(w, A, str_base=1.3)
    _body(w, H, str_base=0.7)
    w.set_stock("bread", 10.0)
    assert w._move_stock_to_inventory(H, "bread", 2.0)
    pending, applied, code = _take(w, kind="bread", amount=2.0, reaction="resist")
    assert applied is True and code is None and pending["result"]["outcome"] == "completed"
    assert w.inventory_qty(A, "bread") == pytest.approx(2.0)
    kinds = [w.eng.node(n)["attrs"]["kind"] for n in w._handovers.values()]
    assert kinds[-1] == "take"


# ------------------------------------------------------------------ reactions

def test_an_alert_target_is_offered_a_reaction_and_an_unaware_or_collapsed_one_is_not():
    alert = _pair()
    pending, _a, _c = _take(alert)
    assert pending["offer"]["eligible"] and pending["offer"]["aware"]

    unaware = _pair()
    unaware._turn_start_positions[A] = _far_cell(unaware, unaware.actor_position(H))
    pending, _a, _c = _take(unaware)
    assert pending["offer"]["eligible"] is False and pending["offer"]["reason"] == "unaware"

    down = _pair()
    down._lie_down(H, collapsed=True)
    pending, _a, _c = _take(down)
    assert pending["offer"]["eligible"] is False and pending["offer"]["reason"] == "collapsed"


def test_yield_is_a_give_with_no_stamina_cost():
    w = _pair()
    _body(w, H, stamina_reserve=0.8)
    pending, applied, code = _take(w, reaction="yield")
    assert applied is True and code is None
    assert w.coin(A) == pytest.approx(14.0) and w.coin(H) == pytest.approx(6.0)
    assert w.stamina_reserve(H) == pytest.approx(0.8)
    assert pending["result"]["target_cost"] == 0.0
    last = w.eng.node(list(w._handovers.values())[-1])["attrs"]
    assert last["kind"] == "yield"


def test_evading_out_of_reach_voids_the_contest_and_frees_the_taker():
    w = _pair()
    pending, applied, code = _take(w, reaction="evade")
    assert applied is False and code == "evaded"
    assert pending["result"]["outcome"] == "evaded"
    assert w.coin(A) == pytest.approx(10.0)
    assert w.actor_position(H) != w.actor_position(A)
    assert float(w.eng.node(w._actors[A])["attrs"].get("major_action_used", 0.0)) == 0.0


def test_a_costly_reaction_with_the_holders_action_used_is_late_and_only_yield_or_brace():
    w = _pair()
    w.eng.set_attr(w._actors[H], "major_action_used", 1.0)   # the holder already acted this turn
    pending, _a, _c = _take(w, reaction=None)               # equal residents: resisting would cost 0.92 x 0.2
    offer = pending["offer"]
    assert offer["eligible"] and offer["late"] and offer["penalty"] == E.CONTEST["late_penalty"]
    assert set(offer["options"]) <= {"yield", "brace"}


def test_a_backend_without_react_is_recorded_as_not_reacting():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(H, _Plain(game.characters[H]))
    w.set_coin(H, 10.0)
    game.set_backend(A, _Taker(game.characters[A]))
    game.step()
    assert game.contest_log[-1]["note"] == "no_react_method"
    assert game.contest_log[-1]["applied"] is True          # a passive hold loses to a stronger push


# ------------------------------------------------------------------ refusals, witnesses, practice

def test_a_take_with_no_one_in_reach_or_nothing_held_is_refused_with_a_reason():
    w = _pair()
    w._move_actor_to(H, _neighbour(w, w.actor_position(A)))
    assert w.major_action(A, "take", source=H, kind="coin", amount=1.0) is False
    assert w.last_outcome(A)["reason"] == "not_in_reach"

    w = _pair()
    w.set_coin(H, 0.0)
    assert w.major_action(A, "take", source=H, kind="coin", amount=1.0) is False
    assert w.last_outcome(A)["reason"] == "out_of_stock"


def test_a_take_without_a_game_is_resolved_without_a_reaction_and_is_reported():
    w = _pair()
    assert w.enact_plan(A, {"action": "take", "source": H, "kind": "coin", "amount": 4.0}) is True
    assert w.coin(A) == pytest.approx(14.0)
    assert w.last_outcome(A)["action"] == "take" and w.last_outcome(A)["applied"] is True


class _Taker(DeterministicBackend):
    """Proposes to take 4 coin from Hal every turn."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("take", {"source": H, "kind": "coin", "amount": 4.0}))


class _Holder(DeterministicBackend):
    """Answers a take with a fixed reaction and proposes nothing."""

    def __init__(self, character, reaction):
        super().__init__(character)
        self.reaction = reaction

    def decide(self, context):
        return ActorResponse()

    def react(self, context):
        return ActorResponse(backend_state={"reaction": self.reaction})


class _Idle(DeterministicBackend):
    def decide(self, context):
        return ActorResponse()


class _Plain(DeterministicBackend):
    """A backend with no ``react`` method: the game must record that the holder did not react."""

    react = None

    def decide(self, context):
        return ActorResponse()


def test_only_people_on_the_cell_see_a_contest():
    w = _pair()
    witness = "Wes"
    far = "Fay"
    w.add_actor(witness, role="hand", home_cell=w.actor_position(H))
    w._move_actor_to(witness, w.actor_position(H))
    w.add_actor(far, role="hand", home_cell=w.actor_position(H))
    w._move_actor_to(far, _neighbour(w, w.actor_position(H)))
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(A, _Taker(game.characters[A]))
    game.set_backend(H, _Holder(game.characters[H], "resist"))
    game.set_backend(witness, _Idle(game.characters[witness]))
    game.set_backend(far, _Idle(game.characters[far]))
    w.set_coin(H, 10.0)
    game.step()
    seen = [e for e in game._physical_events.get(witness, []) if e["action"] == "contest"]
    assert seen and seen[0]["actor"] == A and seen[0]["target"] == H
    assert not [e for e in game._physical_events.get(far, []) if e["action"] == "contest"]
    assert not [e for e in game._physical_events.get(A, []) if e["action"] == "contest"]


def test_contests_log_fighting_practice_that_consolidates_at_period_end():
    w = _pair()
    before_a = w.skill_level(A, "fighting")
    before_h = w.skill_level(H, "fighting")
    _take(w, reaction="resist")
    log_a = w.eng.node(w._actors[A])["attrs"]["skill_practice"]
    assert log_a["fighting"] == pytest.approx(E.CONTEST["practice_minutes"])
    w._consolidate_practice()
    assert w.skill_level(A, "fighting") > before_a
    assert w.skill_level(H, "fighting") > before_h


def test_the_pending_contest_is_plain_data_and_replay_gives_the_same_result():
    first = _pair()
    second = _pair()
    pending_a, _x, _y = _take(first, reaction="resist")
    pending_b, _x2, _y2 = _take(second, reaction="resist")
    assert _plain(pending_a)
    assert pending_a["result"] == pending_b["result"]
    assert pending_a["offer"] == pending_b["offer"]


def test_a_human_holder_makes_the_step_wait_and_then_resumes_the_turn():
    w = _pair()
    w.set_coin(H, 10.0)
    game = BigvilleGame(w, autonomous=True)
    human = HumanBackend(game.characters[H], chooser=lambda context: ActorResponse())
    game.set_backend(H, human)
    game.set_backend(A, _Taker(game.characters[A]))
    waiting = game.step()
    assert waiting["status"] == "waiting" and waiting["actor"] == H
    assert waiting["reaction"]["actor"] == A and "yield" in waiting["reaction"]["options"]
    assert game.step()["status"] == "waiting"
    human.submit_reaction(ActorResponse(backend_state={"reaction": "yield"}))
    done = game.step()
    assert done["status"] == "advanced"
    assert w.coin(A) == pytest.approx(14.0) and game.contest_log[-1]["reaction"] == "yield"


def test_a_held_item_is_taken_like_any_other_good_and_recorded_as_a_take():
    w = _pair()
    _body(w, A, str_base=1.3)
    _body(w, H, str_base=0.7)
    item = w.eng.add_node("ToolItem", {"kind": "knife", "weight": w.item_weight("knife"), "quality": 1.0,
                                       "condition": 1.0, "broken": 0.0, "wear": 0.0, "decay": 0.0,
                                       "use_armed": 0.0, "repair_armed": 0.0})
    w.eng.add_edge_unchecked(w._town, "has_tool_item", item)
    w._remove_item_location(item)
    w.eng.add_edge_unchecked(w._actor(H), "holds_in_hand", item)
    w._actor_hands[H] = item
    pending, applied, code = _take(w, kind=item, reaction="resist")
    assert applied is True and code is None and pending["result"]["outcome"] == "completed"
    assert w._item_owner_edge(A, item) is not None and w._item_owner_edge(H, item) is None
    assert w.eng.node(list(w._handovers.values())[-1])["attrs"]["kind"] == "take"
