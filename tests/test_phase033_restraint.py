"""Phase 033: restraint.

A restraint is a grab by one resident on another standing on the same cell. It reuses the Phase 029 contest: the
grab's power is the holder's score, the held resident's hold is its resist or brace score (a passive grip when it
does not react, none when it yields), and the grab holds on a decisive margin. A held resident cannot walk, and
neither can its holder. Each tick of holding costs both awake sides by the contest's effort rule. A struggle frees
the held resident on a decisive margin. The world attaches no custody, arrest or crime to any of it. Nothing is random.
"""
from __future__ import annotations

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.human import HumanBackend
from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

A, H = "Ada", "Hal"


def _pair():
    """Two residents on one cell (the holder Ada and the target Hal), a tick in, turn-start cells recorded."""
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


def _restrain(w, holder=A, target=H, reaction=None):
    pending, reason = w.restrain_begin(holder, {"target": target})
    if pending is None:
        return None, None, reason
    applied, code = w.restrain_resolve(pending, reaction)
    return pending, applied, code


def _adjacent_cell(w, name):
    here = w.actor_position(name)
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - here[0]), abs(c[1] - here[1])) == 1)


def _far_cell(w, cell):
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) > int(E.HEARING["sight_range"]))


def _event_kinds_seen_by(w, name):
    node = w._actors[name]
    return [w.eng.node(event)["attrs"].get("kind") for event in w.eng.neighbours(node, "observed_event")]


def _reason(w, name):
    return w.eng.node(w._actors[name])["attrs"]["last_outcome"]["reason"]


# ------------------------------------------------------------------ pack and wiring

def test_the_restraint_actions_and_codes_exist_in_the_pack():
    for action in ("restrain", "release", "struggle"):
        assert E.MAJOR_ACTIONS[action]["description"].strip()
    for code in ("restrained", "holding", "already_holding", "already_restrained", "not_holding", "not_restrained",
                 "slipped", "pinned", "not_in_reach"):
        assert code in E.REFUSAL_REASONS


# ------------------------------------------------------------------ the grab

def test_a_stronger_holder_restrains_a_weaker_target_who_cannot_walk_away():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    pending, applied, code = _restrain(w, reaction=None)
    assert applied is True and code is None
    assert pending["offer"]["eligible"] is False and pending["offer"]["reason"] == "too_slow"   # too weak to answer
    assert pending["result"]["outcome"] == "restrained"
    assert w.holder_of(H) == A and w.holding_of(A) == H
    destination = _adjacent_cell(w, H)
    start = w.actor_position(H)
    w.tick()
    assert w.major_action(H, "move", destination=destination) is False
    assert _reason(w, H) == "restrained"
    assert w.move_actor(H, destination) == start            # the walk itself does not move a held resident
    assert w.actor_position(H) == start


def test_an_equal_grab_against_a_resisting_target_slips_and_leaves_no_hold():
    w = _pair()
    pending, applied, code = _restrain(w, reaction="resist")
    assert applied is False and code == "slipped"
    assert pending["result"]["outcome"] == "slipped"
    assert w.holder_of(H) is None and w.holding_of(A) is None


def test_a_holder_cannot_walk_while_holding_and_the_held_cannot_either():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    w.tick()
    assert w.major_action(A, "move", destination=_adjacent_cell(w, A)) is False
    assert _reason(w, A) == "holding"
    assert w.actor_position(A) == w.actor_position(H)


def test_restraining_someone_out_of_reach_is_refused_with_a_reason():
    w = _pair()
    far = _far_cell(w, w.actor_position(H))
    w._move_actor_to(H, far)
    pending, reason = w.restrain_begin(A, {"target": H})
    assert pending is None and reason == "not_in_reach"
    assert w.holder_of(H) is None
    assert w.major_action(A, "restrain", target=H) is False
    assert _reason(w, A) == "not_in_reach"


def test_a_resident_already_holding_or_already_held_is_refused_and_nothing_is_claimed():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    w.add_actor("Cy", role="hand", home_cell=w.actor_position(A))
    w._move_actor_to("Cy", w.actor_position(A))
    pending, reason = w.restrain_begin(A, {"target": "Cy"})
    assert pending is None and reason == "already_holding"
    pending, reason = w.restrain_begin("Cy", {"target": H})
    assert pending is None and reason == "already_restrained"


# ------------------------------------------------------------------ the hold: costs, collapse, release

def test_holding_a_child_costs_a_smith_nothing():
    w = _pair()
    _body(w, A, str_base=3.0)              # the smith holds the child
    _body(w, H, str_base=1.0)
    w.eng.set_attr(w._actors[H], "life_stage", "child")
    _restrain(w, reaction="yield")
    smith_before = w.stamina_reserve(A)
    w._holds_tick()
    assert w.stamina_reserve(A) == smith_before          # the grip the child brings is below the trivial share


def test_a_child_holding_a_smith_pays_the_contest_cost_each_tick():
    w = _pair()
    _body(w, A, str_base=1.0)              # the child holds the smith
    _body(w, H, str_base=3.0)
    w.eng.set_attr(w._actors[A], "life_stage", "child")
    _restrain(w, reaction="yield")
    child_before = w.stamina_reserve(A)
    w._holds_tick()
    drop = child_before - w.stamina_reserve(A)
    assert 0.0 < drop <= E.CONTEST["base_cost"] + 1e-9   # the full share, through the seeded effort conversion


def test_the_holder_tires_and_the_hold_fails_on_collapse():
    w = _pair()
    _body(w, A, str_base=1.0)
    _body(w, H, str_base=3.0)
    w.eng.set_attr(w._actors[A], "life_stage", "child")
    _restrain(w, reaction="yield")
    assert w.holder_of(H) == A
    for _ in range(12):
        w.tick()
        if w.holder_of(H) is None:
            break
    assert w.collapsed(A) is True
    assert w.holder_of(H) is None and w.holding_of(A) is None
    assert w.major_action(H, "move", destination=_adjacent_cell(w, H)) is True


def test_the_target_frees_itself_by_winning_a_struggle():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction=None)
    assert w.holder_of(H) == A
    _body(w, H, str_base=12.0)              # the target has grown much stronger than the holder
    w.tick()
    assert w.major_action(H, "struggle") is True
    assert w.holder_of(H) is None and w.holding_of(A) is None
    assert w.eng.node(w._actors[H])["attrs"]["last_outcome"]["applied"] is True


def test_a_struggle_the_holder_wins_leaves_the_hold_standing():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction=None)
    w.tick()
    assert w.major_action(H, "struggle") is False
    assert _reason(w, H) == "pinned"
    assert w.holder_of(H) == A


def test_release_lets_the_target_leave():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    w.tick()
    assert w.major_action(A, "release") is True
    assert w.holder_of(H) is None and w.holding_of(A) is None
    w.tick()
    assert w.major_action(H, "move", destination=_adjacent_cell(w, H)) is True


def test_release_and_struggle_without_a_hold_are_refused_with_a_reason():
    w = _pair()
    assert w.major_action(A, "release") is False
    assert _reason(w, A) == "not_holding"
    assert w.major_action(H, "struggle") is False
    assert _reason(w, H) == "not_restrained"


# ------------------------------------------------------------------ the reaction, witnesses, slot

def test_evade_steps_the_target_out_of_reach_and_voids_the_restraint():
    w = _pair()                              # equal residents: the target can answer with every option
    pending, applied, code = _restrain(w, reaction="evade")
    assert applied is False and code == "evaded"
    assert w.holder_of(H) is None
    assert w.actor_position(H) != w.actor_position(A)


def test_a_witness_in_sight_sees_the_grab_and_one_out_of_sight_does_not():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    cell = w.actor_position(H)
    codes = w._occluder_codes(E.HEARING["sight_occluders"])
    near = next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) == 2 and not w._line_blocked(cell, c, codes))
    far = _far_cell(w, cell)
    w.add_actor("Wes", role="hand", home_cell=near)
    w._move_actor_to("Wes", near)
    w.add_actor("Fay", role="hand", home_cell=far)
    w._move_actor_to("Fay", far)
    _restrain(w, reaction="resist")
    assert "restrain" in _event_kinds_seen_by(w, "Wes")
    assert "restrain" not in _event_kinds_seen_by(w, "Fay")
    assert "restrain" in _event_kinds_seen_by(w, H)


def test_a_restraint_through_enact_plan_uses_one_major_action_per_turn():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    assert w.enact_plan(A, {"action": "restrain", "target": H}) is True
    w.tick()
    assert w.enact_plan(A, {"action": "release"}) is True
    assert w.enact_plan(A, {"action": "release"}) is False    # not holding any more, and the slot is spent


def test_a_human_target_makes_the_step_wait_for_its_reaction_and_then_resumes():
    w = _pair()
    _body(w, A, str_base=2.0)                # a target this much weaker is too slow to answer; a late answer is offered
    _body(w, H, str_base=1.5)
    game = BigvilleGame(w, autonomous=True)
    human = HumanBackend(game.characters[H], chooser=lambda context: ActorResponse())
    game.set_backend(H, human)
    game.set_backend(A, _Grabber(game.characters[A]))
    waiting = game.step()
    assert waiting["status"] == "waiting" and waiting["actor"] == H
    assert waiting["reaction"]["actor"] == A and "yield" in waiting["reaction"]["options"]
    human.submit_reaction(ActorResponse(backend_state={"reaction": "yield"}))
    done = game.step()
    assert done["status"] == "advanced"
    entry = game.contest_log[-1]
    assert entry["outcome"] == "restrained" and w.holder_of(H) == A


def test_a_target_without_react_is_recorded_as_not_reacting_and_is_held():
    w = _pair()
    _body(w, A, str_base=2.0)
    _body(w, H, str_base=1.5)
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(H, _Plain(game.characters[H]))
    game.set_backend(A, _Grabber(game.characters[A]))
    game.step()
    entry = game.contest_log[-1]
    assert entry["note"] == "no_react_method" and entry["outcome"] == "restrained"
    assert w.holder_of(H) == A


def test_replay_gives_the_same_hold_and_reserves():
    def run():
        w = _pair()
        _body(w, A, str_base=1.0)
        _body(w, H, str_base=3.0)
        w.eng.set_attr(w._actors[A], "life_stage", "child")
        _restrain(w, reaction="yield")
        for _ in range(12):
            w.tick()
        return w.holder_of(H), round(w.stamina_reserve(A), 6), round(w.stamina_reserve(H), 6)

    assert run() == run()


class _Grabber(DeterministicBackend):
    """Proposes a restraint of Hal every turn."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("restrain", {"target": H}))


class _Plain(DeterministicBackend):
    """No react method: the game must record that the target did not react."""

    react = None

    def decide(self, context):
        return ActorResponse()


# ------------------------------------------------------------------ published options and the cheap policy

def test_a_held_resident_is_offered_struggle_and_no_travel_and_a_holder_is_offered_release():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    held = [o.get("action") for o in w.actor_affordances(H)]
    holder = [o.get("action") for o in w.actor_affordances(A)]
    assert "struggle" in held and "move" not in held
    assert "release" in holder and "move" not in holder and "struggle" not in holder


def test_the_cheap_backend_struggles_free_on_its_turn_when_it_is_strong_enough():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    _body(w, H, str_base=12.0)
    game = BigvilleGame(w, autonomous=True)
    game.set_backend(H, DeterministicBackend(game.characters[H]))
    game.set_backend(A, _Plain(game.characters[A]))
    game.step()
    assert game.last_results[H] is True
    assert w.holder_of(H) is None and w.holding_of(A) is None


def test_a_held_resident_can_still_speak_to_the_holder():
    w = _pair()
    _body(w, A, str_base=3.0)
    _body(w, H, str_base=1.0)
    _restrain(w, reaction="resist")
    before = len(w._utterances)
    w.speak(H, target=A, content="let me go")
    assert len(w._utterances) == before + 1
