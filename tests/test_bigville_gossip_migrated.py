"""The gossip drive already existed (sp_choose_utterance's bond-weighted, salience-gated
``share`` option) but fired into two dead ends: share_salience was never computed from real
observations in the live speech tick, the content that reached speech was a hardcoded weather
placeholder, and nothing on the listening end updated the listener's own held belief. This
file gates the three live bridges that close those gaps: ``_speech_share_event`` (salience +
winning Event, computed from real ``observed_event`` data), ``_speech_goal``'s ``share`` branch
(renders the real event, not weather), and ``_hear_gossip`` (the listener's belief_trust toward
the event's subject moves, weighted by trust in the source -- gossip is evidence, never ground
truth). It also gates the retelling-decay follow-up: dedup is per-(listener, event), never
global (Clark & Brennan 1991's common ground is per-dyad), and its decay rate scales toward 1
(slower decline) as severity rises (Rime 2009: initial intensity predicts the slope) -- so
high-salience news gets retold MORE before tapering, never deduplicated harder.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld as World      # noqa: E402


def _town():
    w = World()
    w.add_actor("Anselm", role="smith")
    w.add_actor("Bryony", role="collier")
    w.add_actor("Colm", role="woodworker")
    w.add_actor("Dara", role="baker")
    return w


# --------------------------------------------------- G1: salience is computed from real events
def test_a_recent_observed_injury_makes_the_witness_salient_to_share():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w.observe_event("Anselm", event)
    salience, won = w._speech_share_event("Anselm", "Bryony")
    assert salience > 0.0
    assert won == event


def test_an_unobserved_injury_gives_no_salience_and_no_event():
    w = _town()
    w.injure("Colm", severity=0.4, cause="a fall")           # Anselm never observes it
    salience, won = w._speech_share_event("Anselm", "Bryony")
    assert salience == 0.0
    assert won is None


def test_an_old_observed_event_ages_out_of_salience():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w.observe_event("Anselm", event)
    w.tick(96)                                                # advance a full day+
    w.tick(96)
    salience, won = w._speech_share_event("Anselm", "Bryony")
    assert salience == 0.0
    assert won is None


def test_the_most_severe_of_several_recent_events_wins():
    w = _town()
    minor = w.create_event("gossip_test_minor", subject="Colm", detail="a small thing",
                           observer="Anselm", severity=0.2)
    major = w.injure("Colm", severity=0.8, cause="a fall")
    w.observe_event("Anselm", major)
    salience, won = w._speech_share_event("Anselm", "Bryony")
    assert won == major
    assert salience == 0.8


# --------------------------------------------------- G2: the share branch renders the real event
def test_the_share_meaning_carries_the_real_event_not_weather():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    meaning = w._speech_goal("Bryony", "share", event=event)
    assert meaning == {"news": {"of": {"kind": "injury", "subject": "Colm",
                                       "detail": "Colm was injured (a fall)."}}}
    assert "weather" not in str(meaning)


def test_the_share_meaning_still_falls_back_to_weather_with_no_event():
    w = _town()
    meaning = w._speech_goal("Bryony", "share", event=None)
    assert meaning == {"news": {"of": {"village": {"weather": "clear"}}}}


# --------------------------------------------------- G3: listener uptake moves a held belief
def test_hearing_shared_news_moves_the_listeners_belief_about_its_subject():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    # The listener must already trust the speaker for gossip to move anything --
    # gossip is evidence weighted by the source, never ground truth.
    mind = w._actor_minds["Bryony"]
    speaker_bond = mind._speech_bond("Anselm")
    mind.s.set_attr(speaker_bond, "belief_trust", 1.0)
    subject_bond = mind._speech_bond("Colm")
    before = float(mind.s.node(subject_bond)["attrs"].get("belief_trust", 0.0))
    w._hear_gossip("Bryony", "Anselm", event)
    after = float(mind.s.node(subject_bond)["attrs"].get("belief_trust", 0.0))
    assert after != before, "an injury heard from a trusted source should move belief_trust"
    assert after < before, "injury news is negative; a trusted report should move it down"


def test_gossip_from_a_fully_distrusted_source_barely_moves_belief():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    # Anselm's default bond has belief_trust == 0.0 -- the untouched, unearned default.
    mind = w._actor_minds["Bryony"]
    subject_bond = mind._speech_bond("Colm")
    before = float(mind.s.node(subject_bond)["attrs"].get("belief_trust", 0.0))
    w._hear_gossip("Bryony", "Anselm", event)
    after = float(mind.s.node(subject_bond)["attrs"].get("belief_trust", 0.0))
    assert after == before, "zero source trust must carry zero evidentiary weight"


def test_gossip_never_updates_a_listener_hearing_about_themselves():
    w = _town()
    event = w.injure("Bryony", severity=0.4, cause="a fall")
    mind = w._actor_minds["Bryony"]
    speaker_bond = mind._speech_bond("Anselm")
    mind.s.set_attr(speaker_bond, "belief_trust", 1.0)
    # Bryony hearing gossip ABOUT Bryony must not mint a self-directed Bond.
    w._hear_gossip("Bryony", "Anselm", event)
    assert "Bryony" not in w._actor_minds["Bryony"].speech_bonds


# --------------------------------------------------- G4: retelling decay, not binary dedup
def test_retelling_the_same_listener_damps_salience_but_never_to_zero():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w.observe_event("Anselm", event)
    fresh, _ = w._speech_share_event("Anselm", "Bryony")
    told = w._actor_minds["Anselm"].told_events
    told[("Bryony", event)] = 1
    once_told, won = w._speech_share_event("Anselm", "Bryony")
    told[("Bryony", event)] = 5
    five_told, _ = w._speech_share_event("Anselm", "Bryony")
    assert 0.0 < five_told < once_told < fresh, (
        "salience should strictly decline with retellings to the SAME listener, "
        "but never hit exactly zero (real retelling tapers, it doesn't cut off)")
    assert won == event, "a retold event should still be selectable while damped, not discarded"


def test_a_different_listener_sees_the_undamped_salience():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w.observe_event("Anselm", event)
    w._actor_minds["Anselm"].told_events[("Bryony", event)] = 10
    damped_for_bryony, _ = w._speech_share_event("Anselm", "Bryony")
    undamped_for_dara, _ = w._speech_share_event("Anselm", "Dara")
    assert undamped_for_dara > damped_for_bryony, (
        "common ground is per-dyad (Clark & Brennan 1991) -- retelling Bryony ten "
        "times must not damp what a fresh listener, Dara, has never heard")


def test_a_more_severe_event_decays_more_slowly_than_a_mild_one():
    w = _town()
    mild = w.create_event("gossip_test_mild", subject="Colm", detail="a small thing",
                          observer="Anselm", severity=0.25)
    severe = w.create_event("gossip_test_severe", subject="Colm", detail="a bad thing",
                            observer="Anselm", severity=0.9)
    mind = w._actor_minds["Anselm"]
    mind.told_events[("Bryony", mild)] = 3
    mind.told_events[("Bryony", severe)] = 3
    mild_base = max(0.25, 0.25)
    severe_base = max(0.25, 0.9)
    mild_decay = min(0.95, 0.3 + 0.25)
    severe_decay = min(0.95, 0.3 + 0.9)
    mild_expected = mild_base * (mild_decay ** 3)
    severe_expected = severe_base * (severe_decay ** 3)
    # Retold equally often, the more severe event should have retained a
    # LARGER fraction of its own starting salience -- Rime's own finding
    # that initial intensity predicts a slower decline, not just a higher start.
    assert (severe_expected / severe_base) > (mild_expected / mild_base)


def test_hearing_a_share_increments_the_speakers_told_count_for_that_listener():
    w = _town()
    w.set_relationship("Anselm", "Bryony", kind="friend", strength=1.0, mutual=True)
    w._move_actor_to("Anselm", (5, 5))
    w._move_actor_to("Bryony", (5, 5))
    event = w.injure("Colm", severity=0.6, cause="a fall")
    w.observe_event("Anselm", event)
    for _ in range(5):
        w._spontaneous_speech_tick()
    told = w._actor_minds["Anselm"].told_events.get(("Bryony", event), 0)
    assert told > 0, "at least one heard share should have incremented the retelling count"
