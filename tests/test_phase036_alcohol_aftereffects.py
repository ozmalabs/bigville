"""Phase 036: alcohol's longer effects, behind the alcohol_aftereffects switch (off by default).

Tolerance lowers the dose a body takes and fades while sober. Dependence forms at dependence_tolerance; a dependent
body's craving rises while sober, a drink relieves it, and withdrawal lowers working skill and stamina. A hangover
follows a heavy episode and ends after hangover_ticks. Poisoning above poison_above is acute harm with cause
intoxication, and pass_out comes first. Speech carries a clarity figure and keeps its text. With the switch off,
none of this is read or changed.
"""
from __future__ import annotations

import pytest

from bigville.backends import ActorContext
from bigville.backends.cheap import DeterministicBackend, SimplePolicy
from bigville.character import CharacterDefinition
from bigville.reporting import SimulationReporter
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

I = E.INTOXICATION
ON = {"alcohol_aftereffects": True}


def _world(name="Ada", *, aftereffects=True, size=None):
    kwargs = {"physical_subsystems": ON} if aftereffects else {}
    w = World(autonomous_actors=False, **kwargs)
    cells = sorted(w._map_cells)
    w.add_actor(name, role="hand", home_cell=cells[len(cells) // 2])
    w.give_tableware(name, "wooden_mug")
    w.give_tableware(name, "wooden_ladle")
    w.give_tableware(name, "wooden_dipper")
    if size is not None:
        w.set_capacities(name, size=size)
    return w


def _pair(*, aftereffects=True):
    """Ada and Hal on one cell, a tick in, so speech reaches Hal at distance 0."""
    w = World(autonomous_actors=False, **({"physical_subsystems": ON} if aftereffects else {}))
    cell = sorted(w._map_cells)[len(w._map_cells) // 2]
    w.add_actor("Ada", role="hand", home_cell=cell)
    w.add_actor("Hal", role="hand", home_cell=cell)
    w._move_actor_to("Ada", cell)
    w._move_actor_to("Hal", cell)
    for name in ("Ada", "Hal"):
        for item in ("wooden_mug", "wooden_ladle", "wooden_dipper"):
            w.give_tableware(name, item)
    w.tick()
    w.mark_turn_start()
    return w


def _drink(w, name, kind="ale", count=1):
    """One drink at a time, each in its own turn (the action slot resets), as the eat action is taken."""
    w.set_stock(kind, count + 1)
    for _ in range(count):
        w.mark_turn_start()
        assert w.fetch(name, kind, 1)
        w.mark_turn_start()
        assert w.eat(name, kind, vessel="wooden_mug", utensil="wooden_dipper")


def _set_body(w, name, **attrs):
    for key, value in attrs.items():
        w.eng.set_attr(w._bodies[name], key, float(value))


def _body(w, name, key):
    return float(w.eng.node(w._bodies[name])["attrs"].get(key, 0.0))


def _give_skill(w, name, level=0.8):
    w.seed_skill_floor(name, {"fighting": level})
    return w.effective_skill(name, "fighting")


# ------------------------------------------------------------------ the switch

def test_the_switch_is_registered_and_off_by_default():
    assert World(autonomous_actors=False).physical_subsystems["alcohol_aftereffects"] is False


def test_the_table_carries_every_aftereffect_key_and_the_self_test_passes():
    for key in ("tolerance_per_drink", "dependence_tolerance", "craving_rise_per_tick", "withdrawal_above",
                "hangover_above", "hangover_ticks", "poison_above", "poison_harm", "clarity_distance_loss"):
        assert key in I
    errors, warnings, info = [], [], []
    E._check_aftereffects(errors, warnings, info)
    assert errors == []


def test_switch_off_a_drink_is_the_phase_034_dose_and_nothing_else_moves():
    w = _world(aftereffects=False)
    _drink(w, "Ada", "ale", 1)
    assert w.intoxication("Ada") == pytest.approx(E.intoxication_gain(E.alcohol("ale"), 1.0), abs=1e-4)
    assert _body(w, "Ada", "tolerance") == 0.0 and _body(w, "Ada", "craving") == 0.0
    state = w.body_state("Ada")
    assert "tolerance" not in state and "hangover_ticks" not in state
    assert w.aftereffects("Ada") == {}
    for _ in range(200):
        w.tick()
    assert _body(w, "Ada", "tolerance") == 0.0 and _body(w, "Ada", "hangover_ticks") == 0.0
    assert _body(w, "Ada", "dependent") == 0.0


# ------------------------------------------------------------------ tolerance

def test_a_tolerant_resident_takes_less_of_the_same_dose():
    fresh = _world("Ada")
    _drink(fresh, "Ada", "ale", 1)
    tolerant = _world("Ada")
    _set_body(tolerant, "Ada", tolerance=0.5)
    _drink(tolerant, "Ada", "ale", 1)
    relief = I["tolerance_relief"] * 0.5
    assert tolerant.intoxication("Ada") == pytest.approx(fresh.intoxication("Ada") * (1.0 - relief), abs=2e-4)
    assert tolerant.intoxication("Ada") < fresh.intoxication("Ada")


def test_each_drink_adds_tolerance_and_sober_ticks_fade_it():
    w = _world()
    _drink(w, "Ada", "ale", 2)
    assert _body(w, "Ada", "tolerance") == pytest.approx(2 * I["tolerance_per_drink"])
    _set_body(w, "Ada", intoxication=0.0)
    before = _body(w, "Ada", "tolerance")
    for _ in range(10):
        w.tick()
    assert _body(w, "Ada", "tolerance") == pytest.approx(before - 10 * I["tolerance_fade_per_tick"], abs=1e-9)


def test_tolerance_does_not_pass_its_maximum():
    w = _world()
    _set_body(w, "Ada", tolerance=I["tolerance_max"] - 0.01)
    _drink(w, "Ada", "ale", 1)
    assert _body(w, "Ada", "tolerance") == pytest.approx(I["tolerance_max"])


# ------------------------------------------------------------------ dependence, craving and withdrawal

def test_dependence_forms_at_the_table_tolerance_and_craving_rises_only_while_sober():
    w = _world()
    _drink(w, "Ada", "ale", 5)
    assert _body(w, "Ada", "dependent") == 1.0
    assert w.aftereffects("Ada")["dependent"] == 1
    assert _body(w, "Ada", "craving") == 0.0
    for _ in range(120):
        w.tick()
    assert w.intoxication("Ada") < I["bands"]["tipsy"]
    craving = _body(w, "Ada", "craving")
    assert 0.0 < craving < 1.0


def test_a_dependent_resident_in_withdrawal_has_a_skill_and_stamina_penalty_that_a_drink_relieves():
    w = _world()
    skill_sober = _give_skill(w, "Ada")
    stamina_sober = w.effective_stamina("Ada")
    _set_body(w, "Ada", dependent=1.0, craving=0.4)
    assert w.aftereffects("Ada")["withdrawal"] == 1
    assert w.effective_skill("Ada", "fighting") == pytest.approx(
        round(skill_sober * (1.0 - I["withdrawal_skill"] * 0.4), 4), abs=1e-4)
    assert w.effective_stamina("Ada") == pytest.approx(stamina_sober * (1.0 - I["withdrawal_stamina"] * 0.4), rel=1e-6)
    _drink(w, "Ada", "ale", 1)
    assert _body(w, "Ada", "craving") == pytest.approx(max(0.0, 0.4 - I["craving_relief_per_drink"]))
    assert w.aftereffects("Ada")["withdrawal"] == 0


def test_a_craving_below_the_withdrawal_line_gives_no_penalty():
    w = _world()
    skill_sober = _give_skill(w, "Ada")
    _set_body(w, "Ada", dependent=1.0, craving=I["withdrawal_above"] - 0.05)
    assert w.effective_skill("Ada", "fighting") == pytest.approx(skill_sober)


def test_a_non_dependent_resident_never_craves():
    w = _world()
    _drink(w, "Ada", "ale", 1)
    for _ in range(150):
        w.tick()
    assert _body(w, "Ada", "craving") == 0.0 and w.aftereffects("Ada")["withdrawal"] == 0


# ------------------------------------------------------------------ hangover

def test_a_heavy_night_leaves_a_hangover_that_then_ends():
    w = _world()
    _give_skill(w, "Ada")
    skill_sober = w.effective_skill("Ada", "fighting")
    _drink(w, "Ada", "mead", 3)
    assert w.intoxication("Ada") >= I["hangover_above"]
    assert _body(w, "Ada", "hangover_ticks") == 0.0
    while w.intoxication("Ada") >= I["bands"]["tipsy"]:
        w.tick()
    assert 0.0 < _body(w, "Ada", "hangover_ticks") <= float(I["hangover_ticks"])
    while w.intoxication("Ada") > 0.0:
        w.tick()
    left = int(_body(w, "Ada", "hangover_ticks"))
    assert left > 0
    assert w.aftereffects("Ada")["hangover_ticks"] == left
    assert w._hangover_recovery_factor("Ada") == pytest.approx(I["hangover_recovery"])
    assert w.effective_skill("Ada", "fighting") == pytest.approx(skill_sober * (1.0 - I["hangover_skill"]), rel=1e-3)
    for _ in range(left):
        w.tick()
    assert _body(w, "Ada", "hangover_ticks") == 0.0
    assert w._aftereffect_skill_factor("Ada") == pytest.approx(1.0)
    assert w.effective_skill("Ada", "fighting") == pytest.approx(skill_sober, rel=1e-3)


def test_a_light_night_leaves_no_hangover():
    w = _world()
    _drink(w, "Ada", "ale", 1)
    while w.intoxication("Ada") >= I["bands"]["tipsy"]:
        w.tick()
    assert _body(w, "Ada", "hangover_ticks") == 0.0


def test_a_hangover_cuts_the_stamina_a_sleeper_regains():
    gains = []
    for hangover in (0.0, 10.0):
        w = _world()
        _set_body(w, "Ada", hangover_ticks=hangover)
        w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 0.2)
        node = w._actors["Ada"]
        w.eng.set_attr(node, "asleep", 1.0)
        w.eng.set_attr(node, "sleep_kind", 1.0)
        w._job_tick_armed = True
        w._resolve_sleep()
        w._job_tick_armed = False
        gains.append(_body(w, "Ada", "stamina_reserve") - 0.2)
    assert gains[0] > 0.0
    assert gains[1] == pytest.approx(gains[0] * I["hangover_recovery"], rel=1e-6)


# ------------------------------------------------------------------ poisoning and pass-out

def test_an_ordinary_dose_does_no_poison_harm():
    w = _world()
    _drink(w, "Ada", "ale", 1)
    for _ in range(100):
        w.tick()
    assert w.is_alive("Ada") and w.health("Ada") == pytest.approx(1.0)
    assert w._deaths == []


def test_a_lethal_dose_passes_out_first_then_kills_through_harm_with_cause_intoxication():
    w = _world()
    _drink(w, "Ada", "mead", 5)
    code_at_first_harm = None
    for _ in range(400):
        if not w.is_alive("Ada"):
            break
        health = w.health("Ada")
        w.tick()
        if code_at_first_harm is None and w.health("Ada") < health:
            code_at_first_harm = w._sleep_code("Ada")
    assert not w.is_alive("Ada")
    assert code_at_first_harm == "passed_out", "pass_out is checked before the poison harm in the same tick"
    assert w._deaths[-1]["cause"] == "intoxication"
    assert w.eng.node(w._actors["Ada"])["attrs"]["death_cause"] == "intoxication"


def test_poison_harm_scales_from_zero_at_the_threshold_to_full_at_one():
    w = _world()
    _set_body(w, "Ada", intoxication=1.0)
    health = w.health("Ada")
    w.tick()
    level = w.intoxication("Ada")
    expected = I["poison_harm"] * (level - I["poison_above"]) / (1.0 - I["poison_above"])
    assert level == pytest.approx(1.0 - E.sober_per_tick(), abs=1e-4)
    assert health - w.health("Ada") == pytest.approx(expected, abs=1e-4)
    assert w._deaths == [] and w.health("Ada") > 0.0
    w2 = _world()
    _set_body(w2, "Ada", intoxication=I["poison_above"])
    w2.tick()
    assert w2.health("Ada") == pytest.approx(1.0)


# ------------------------------------------------------------------ speech clarity

def test_a_drunk_speaker_is_less_clear_and_the_text_is_unchanged():
    sober = _pair()
    drunk = _pair()
    _set_body(drunk, "Ada", intoxication=0.67)     # three mugs of mead, set directly (the drink needs a stocked town)
    assert drunk.intoxication("Ada") > 0.5
    u_sober = sober.speak("Ada", None, "Mind the well, Hal.")
    u_drunk = drunk.speak("Ada", None, "Mind the well, Hal.")
    assert sober.eng.node(u_sober)["attrs"]["content"] == drunk.eng.node(u_drunk)["attrs"]["content"]
    assert sober.eng.node(u_sober)["attrs"]["clarity"] == pytest.approx(1.0)
    assert drunk.eng.node(u_drunk)["attrs"]["clarity"] == pytest.approx(1.0 - drunk.intoxication("Ada"), abs=1e-4)
    heard_sober = sober.heard_utterances("Hal")[-1]
    heard_drunk = drunk.heard_utterances("Hal")[-1]
    assert heard_sober["text"] == heard_drunk["text"] == "Mind the well, Hal."
    assert heard_drunk["clarity"] < heard_sober["clarity"]


def test_distance_against_loudness_lowers_clarity_for_a_sober_speaker():
    w = _pair()
    assert w.speech_clarity("Ada", distance=0.0, radius=3.0) == pytest.approx(1.0)
    assert w.speech_clarity("Ada", distance=3.0, radius=3.0) == pytest.approx(1.0 - I["clarity_distance_loss"])


def test_switch_off_speech_has_no_clarity_figure():
    w = _pair(aftereffects=False)
    u = w.speak("Ada", None, "Hello.")
    assert "clarity" not in w.eng.node(u)["attrs"]
    assert "clarity" not in w.heard_utterances("Hal")[-1]
    assert w.speech_clarity("Ada") == 1.0


# ------------------------------------------------------------------ the backend's coping policy and the reporter

def _coping_context(*, mood, craving=0.0, level=0.0, switch=True):
    character = CharacterDefinition(character_id="Tom", name="Tom", identity={"role": "mason"})
    affordances = [{"action": "eat", "kind": "ale", "trade": "", "recipe": "", "target": "", "score": 0.0},
                   {"action": "eat", "kind": "bread", "trade": "", "recipe": "", "target": "", "score": 0.0}]
    observations = {"calendar": {"hour": 9.0}, "hunger": 0.0, "energy": 100.0, "intoxication": level}
    if switch:
        observations["aftereffects"] = {"mood": mood, "craving": craving, "tolerance": 0.0, "dependent": 0,
                                        "hangover_ticks": 0, "withdrawal": 0}
    return ActorContext(character, 1, observations, affordances)


def test_the_coping_policy_is_off_by_default_and_prefers_a_drink_only_when_distressed():
    character = CharacterDefinition(character_id="Tom", name="Tom", identity={"role": "mason"})
    off = DeterministicBackend(character)
    assert off._coping_bonus(_coping_context(mood=0.1), {"action": "eat", "kind": "ale"}) == 0.0
    on = DeterministicBackend(character, policy=SimplePolicy(coping_drink=True))
    ale = {"action": "eat", "kind": "ale"}
    assert on._coping_bonus(_coping_context(mood=0.1), ale) == pytest.approx(I["coping_bonus"])
    assert on._coping_bonus(_coping_context(mood=0.9), ale) == 0.0
    assert on._coping_bonus(_coping_context(mood=0.9, craving=I["withdrawal_above"]), ale) == pytest.approx(
        I["coping_bonus"])
    assert on._coping_bonus(_coping_context(mood=0.1), {"action": "eat", "kind": "bread"}) == 0.0
    assert on._coping_bonus(_coping_context(mood=0.1, switch=False), ale) == 0.0
    assert on._coping_bonus(_coping_context(mood=0.1, level=0.5), ale) == 0.0


def test_the_reporter_counts_dependence_and_hangover_and_is_empty_when_off():
    w = _world()
    _drink(w, "Ada", "ale", 5)
    report = SimulationReporter(w).aftereffects()
    assert report["dependent"] == 1 and report["residents"] == 1 and report["tolerance_mean"] > 0.0
    off = SimulationReporter(_world(aftereffects=False)).aftereffects()
    assert off["dependent"] == 0 and off["residents"] == 0, "empty while the switch is off"
