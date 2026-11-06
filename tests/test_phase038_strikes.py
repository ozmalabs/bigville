"""Phase 038: strikes and injury.

A strike is a blow by one resident on another standing on the same cell. It reuses the Phase 029 contest: the
blow's power is the attacker's score, the target's hold is its resist or brace score (none when it does not react),
the reaction turn and the redirect rule are the take's. Harm goes through Phase 037's harm(..., "violence"). The
world records a blow as a physical event for those who can see it, and records no offence. Nothing is random.
"""
from __future__ import annotations

import pytest

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend, SimplePolicy
from bigville.backends.human import HumanBackend
from bigville.backends.protocol import ActorContext
from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

A, H = "Ada", "Hal"


def _pair():
    """Two residents on one cell (the attacker Ada and the target Hal), a tick in, turn-start cells recorded."""
    w = World(autonomous_actors=False)
    cells = sorted(w._map_cells)
    cell = cells[len(cells) // 2]
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w._move_actor_to(A, cell)
    w._move_actor_to(H, cell)
    w.tick()
    w.mark_turn_start()
    return w


def _body(w, name, **attrs):
    for key, value in attrs.items():
        w.eng.set_attr(w._bodies[name], key, float(value))


def _strike(w, attacker=A, target=H, intensity=1.0, reaction=None):
    pending, reason = w.strike_begin(attacker, {"target": target, "intensity": intensity})
    if pending is None:
        return None, None, reason
    applied, code = w.strike_resolve(pending, reaction)
    return pending, applied, code


def _far_cell(w, cell):
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) > int(E.HEARING["sight_range"]))


def _event_kinds_seen_by(w, name):
    node = w._actors[name]
    return [w.eng.node(event)["attrs"].get("kind") for event in w.eng.neighbours(node, "observed_event")]


# ------------------------------------------------------------------ pack and wiring

def test_the_strike_numbers_codes_and_action_exist_in_the_pack():
    assert E.CONTEST["strike_harm"] > 0 and E.CONTEST["attack_cost"] > 0 and E.CONTEST["redirect_harm"] >= 0
    assert "strike" in E.MAJOR_ACTIONS and E.MAJOR_ACTIONS["strike"]["description"].strip()
    assert "violence" in E.HEALTH["causes"]
    assert SimplePolicy().strike_trigger is False          # the simple backend does not strike by default


# ------------------------------------------------------------------ the blow

def test_a_blow_lowers_the_victims_health_and_the_attackers_stamina():
    w = _pair()
    health_before, reserve_before = w.health(H), w.stamina_reserve(A)
    pending, applied, code = _strike(w)
    assert applied is True and code is None
    assert pending["result"]["outcome"] == "struck"
    assert w.health(H) < health_before
    assert w.health(H) == pytest.approx(health_before - pending["result"]["harm"])
    assert w.stamina_reserve(A) < reserve_before


def test_an_unprepared_victim_takes_the_blow_in_full_and_a_resisting_one_takes_less():
    unprepared = _pair()
    _strike(unprepared)
    full = 1.0 - unprepared.health(H)
    resisting = _pair()
    pending, _applied, _code = _strike(resisting, reaction="resist")
    assert "resist" in pending["offer"]["options"]
    harmed = 1.0 - resisting.health(H)
    assert harmed < full
    # Equal force and skill: the hold equals the blow, so half of it lands ((1 + margin) / 2 with margin 0).
    assert harmed == pytest.approx(full * 0.5)


def test_a_drunk_attacker_lands_a_weaker_blow_than_a_sober_one():
    sober = _pair()
    sober.set_skill_level(A, "fighting", 0.8)
    _strike(sober)
    drunk = _pair()
    drunk.set_skill_level(A, "fighting", 0.8)
    _body(drunk, A, intoxication=0.9)
    assert drunk.effective_skill(A, "fighting") < sober.effective_skill(A, "fighting")
    _strike(drunk)
    assert drunk.health(H) > sober.health(H)


def test_a_strike_below_attack_cost_lands_weakly_and_leaves_the_attacker_collapsed():
    full = _pair()
    _strike(full)
    full_harm = 1.0 - full.health(H)
    low = _pair()
    _body(low, A, stamina_reserve=0.05)
    pending, applied, code = _strike(low)
    assert applied is True and code is None
    weak = 0.05 / float(E.CONTEST["attack_cost"])
    assert pending["result"]["weak"] == pytest.approx(weak)
    assert 1.0 - low.health(H) == pytest.approx(full_harm * weak)
    assert low.stamina_reserve(A) == 0.0                       # the effort drives the reserve to 0
    low.tick()
    assert low.collapsed(A)                                     # and the attacker is down (Phase 024)


def test_a_strike_can_be_tried_at_any_stamina_including_none():
    w = _pair()
    _body(w, A, stamina_reserve=0.0)
    pending, reason = w.strike_begin(A, {"target": H, "intensity": 1.0})
    assert pending is not None and reason is None


def test_a_lethal_blow_kills_and_is_recorded_as_violence():
    w = _pair()
    w.eng.set_attr(w._actors[H], "health_value", 0.05)
    _strike(w)
    assert w.is_alive(H) is False
    attrs = w.eng.node(w._actors[H])["attrs"]
    assert attrs.get("last_cause") == "violence"
    assert str(attrs.get("death_cause", "")) == "violence"


def test_intensity_scales_the_harm_and_the_cost_and_a_pulled_blow_barely_harms():
    normal = _pair()
    pending_n, _a, _c = _strike(normal, intensity=1.0)
    pulled = _pair()
    pending_p, _a, _c = _strike(pulled, intensity=0.1)
    assert pending_p["result"]["harm"] == pytest.approx(pending_n["result"]["harm"] * 0.1)
    assert pending_p["result"]["attacker_cost"] < pending_n["result"]["attacker_cost"]
    hard = _pair()
    pending_h, _a, _c = _strike(hard, intensity=2.0)
    assert pending_h["result"]["harm"] == pytest.approx(pending_n["result"]["harm"] * 2.0)
    assert pending_h["result"]["attacker_cost"] > pending_n["result"]["attacker_cost"] * 2.0   # k > 1


# ------------------------------------------------------------------ redirection

def test_a_skilled_defender_redirects_an_unskilled_attacker_who_pays_more_and_is_hurt():
    w = _pair()
    w.set_skill_level(A, "fighting", 0.0)
    w.set_skill_level(H, "fighting", 0.9)
    pending, applied, code = _strike(w, reaction="resist")
    result = pending["result"]
    assert result["outcome"] == "redirected" and result["redirected"]
    assert applied is True and code is None
    assert w.health(H) == pytest.approx(1.0)                    # the blow was turned back: no harm to the target
    assert w.health(A) == pytest.approx(1.0 - float(E.CONTEST["redirect_harm"]))
    assert result["attacker_cost"] > result["target_cost"] * 2


# ------------------------------------------------------------------ witnesses

def test_a_witness_in_sight_sees_the_blow_and_one_out_of_sight_does_not():
    w = _pair()
    cell = w.actor_position(H)
    codes = w._occluder_codes(E.HEARING["sight_occluders"])
    near = next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) == 2 and not w._line_blocked(cell, c, codes))
    far = _far_cell(w, cell)
    w.add_actor("Wes", role="hand", home_cell=near)
    w._move_actor_to("Wes", near)
    w.add_actor("Fay", role="hand", home_cell=far)
    w._move_actor_to("Fay", far)
    _strike(w)
    assert "strike" in _event_kinds_seen_by(w, "Wes")
    assert "strike" not in _event_kinds_seen_by(w, "Fay")
    assert "strike" in _event_kinds_seen_by(w, H)               # the target sees it too


def test_a_sleeping_resident_does_not_witness_a_blow():
    w = _pair()
    cell = w.actor_position(H)
    w.add_actor("Sam", role="hand", home_cell=cell)
    w._move_actor_to("Sam", cell)
    w.eng.set_attr(w._actors["Sam"], "asleep", 1.0)
    _strike(w)
    assert "strike" not in _event_kinds_seen_by(w, "Sam")


# ------------------------------------------------------------------ refusals and the slot

def test_a_strike_with_no_one_in_reach_or_on_no_one_is_refused_with_a_reason():
    w = _pair()
    assert _strike(w, target="Nobody")[2] == "unknown_target"
    assert _strike(w, target=A)[2] == "wrong_target"
    w._move_actor_to(H, _far_cell(w, w.actor_position(A)))
    assert _strike(w)[2] == "not_in_reach"
    assert w.major_action(A, "strike", target=H) is False
    assert w.last_outcome(A)["reason"] == "not_in_reach"


def test_a_strike_through_enact_plan_is_one_major_action_per_turn():
    w = _pair()
    assert w.enact_plan(A, {"action": "strike", "target": H, "intensity": 1.0}) is True
    assert w.enact_plan(A, {"action": "strike", "target": H, "intensity": 1.0}) is False
    assert w.last_outcome(A)["reason"] == "slot_used"


# ------------------------------------------------------------------ through the game

class _Striker(DeterministicBackend):
    """Proposes a blow on Hal every turn."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("strike", {"target": H, "intensity": 1.0}))


class _Plain(DeterministicBackend):
    """No react method: the game must record that the target did not react."""

    react = None

    def decide(self, context):
        return ActorResponse()


def test_a_human_target_makes_the_step_wait_for_its_reaction_and_then_resumes():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    human = HumanBackend(game.characters[H], chooser=lambda context: ActorResponse())
    game.set_backend(H, human)
    game.set_backend(A, _Striker(game.characters[A]))
    waiting = game.step()
    assert waiting["status"] == "waiting" and waiting["actor"] == H
    assert waiting["reaction"]["actor"] == A and "resist" in waiting["reaction"]["options"]
    human.submit_reaction(ActorResponse(backend_state={"reaction": "resist"}))
    done = game.step()
    assert done["status"] == "advanced"
    entry = game.contest_log[-1]
    assert entry["reaction"] == "resist" and entry["outcome"] in ("struck", "redirected")
    assert w.health(H) < 1.0 or entry["outcome"] == "redirected"


def test_a_target_without_react_is_recorded_as_not_reacting_and_takes_the_blow():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(H, _Plain(game.characters[H]))
    game.set_backend(A, _Striker(game.characters[A]))
    game.step()
    entry = game.contest_log[-1]
    assert entry["note"] == "no_react_method" and entry["outcome"] == "struck"
    assert w.health(H) < 1.0


def test_replay_gives_the_same_blows_and_health():
    def run():
        w = _pair()
        w.set_skill_level(H, "fighting", 0.5)
        pending, applied, code = _strike(w, reaction="brace")
        return pending["result"], applied, code, w.health(H), w.stamina_reserve(A), w.stamina_reserve(H)

    assert run() == run()


# ------------------------------------------------------------------ the simple backend's trigger

def _context(game, name, *, hunger=1.0, energy=100.0, near=None):
    residents = [{"id": other, "distance": 0} for other in (near or [])]
    return ActorContext(character=game.characters[name], turn=3,
                        observations={"hunger": hunger, "energy": energy, "nearby_residents": residents},
                        affordances=[])


def test_the_simple_backend_never_strikes_by_default_even_with_a_grievance():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    backend = DeterministicBackend(game.characters[A])
    backend.grievances = {H: 1}
    assert backend._strike_proposal(_context(game, A, hunger=2.0, near=[H])) is None
    response = backend.decide(_context(game, A, hunger=2.0, near=[H]))
    assert response.major_action is None or response.major_action.action != "strike"


def test_with_the_trigger_on_a_hungry_resident_with_a_grievance_strikes_the_person_on_its_cell():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    backend = DeterministicBackend(game.characters[A], policy=SimplePolicy(strike_trigger=True))
    backend.grievances = {H: 1}
    assert backend._strike_proposal(_context(game, A, hunger=0.0, near=[H])) is None   # w_spite alone is short
    assert backend._strike_proposal(_context(game, A, hunger=1.0, near=[])) is None    # nobody on the cell
    assert backend._strike_proposal(_context(game, A, hunger=1.0, energy=5.0, near=[H])) is None   # below attack_cost
    assert backend._strike_proposal(_context(game, A, hunger=1.0, near=[H])) == {"target": H, "intensity": 1.0}


def test_a_contest_the_simple_backend_reacts_to_is_recorded_as_a_grievance():
    w = _pair()
    game = BigvilleGame(w, autonomous=True)
    backend = DeterministicBackend(game.characters[H])
    context = ActorContext(character=game.characters[H], turn=4,
                           observations={"reaction": {"actor": A, "options": ["resist", "yield"]}}, affordances=[])
    response = backend.react(context)
    assert response.backend_state["reaction"] == "resist"
    assert backend.grievances == {A: 4}
