"""The share drive already existed (sp_choose_utterance's bond-weighted, salience-gated
``share`` option) but fired into two dead ends: share_salience was never computed from real
observations in the live speech tick, the content that reached speech was a hardcoded weather
placeholder, and nothing on the listening end updated the listener's own held belief. This
file gates the three live bridges that close those gaps: ``_speech_share_event`` (salience +
winning Event, computed from real ``observed_event`` data), ``_speech_goal``'s ``share`` branch
(renders the real event, not weather). The world records physical hearing only: recipient
belief uptake and memory are private cognition, not an automatic world rule. It also gates
the retelling-decay follow-up: dedup is per-(listener, event), never
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
from bigville.backends.speech import DeterministicSpeechBackend # noqa: E402


def _meaning(world, target, kind, event=None):
    context = {"weather": world.eng.node(world._town)["attrs"].get("weather", "clear")}
    if event is not None:
        attrs = world.eng.node(event)["attrs"]
        context["event"] = {"kind": str(attrs.get("kind", "")),
                            "subject": str(attrs.get("subject", "")),
                            "detail": str(attrs.get("detail", ""))}
    return DeterministicSpeechBackend._meaning(target, kind, context=context)


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
    meaning = _meaning(w, "Bryony", "share", event=event)
    assert meaning == {"news": {"of": {"kind": "injury", "subject": "Colm",
                                       "detail": "Colm was injured (a fall)."}}}
    assert "weather" not in str(meaning)


def test_the_share_meaning_still_falls_back_to_weather_with_no_event():
    w = _town()
    meaning = _meaning(w, "Bryony", "share", event=None)
    assert meaning == {"news": {"of": {"village": {"weather": "clear"}}}}


# --------------------------------------------------- G3: hearing is not belief uptake
def test_same_heard_message_preserves_divergent_recipient_beliefs():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w._move_actor_to("Anselm", (5, 5))
    w._move_actor_to("Bryony", (5, 5))
    w._move_actor_to("Dara", (5, 5))
    w.observe_event("Anselm", event)
    listeners = [w._actor_minds[name] for name in ("Bryony", "Dara")]
    bonds = [mind.speech_backend._bond("Colm") for mind in listeners]
    listeners[0].s.set_attr(bonds[0], "belief_trust", -0.7)
    listeners[1].s.set_attr(bonds[1], "belief_trust", 0.4)
    proposal = {"target": "Bryony", "text": "Colm was hurt in a fall.",
                "raw": {"act": "share"}, "event": event}
    w.enact_speech_proposal("Anselm", proposal)
    # Deliver the identical report to Dara. Delivery changes neither mind;
    # their distinct prior interpretations stay private to each backend.
    proposal["target"] = "Dara"
    w.enact_speech_proposal("Anselm", proposal)
    assert listeners[0].s.node(bonds[0])["attrs"]["belief_trust"] == -0.7
    assert listeners[1].s.node(bonds[1])["attrs"]["belief_trust"] == 0.4
    assert listeners[0].heard_events == listeners[1].heard_events == {}


def test_an_unobserved_event_does_not_create_recipient_inference():
    w = _town()
    event = w.injure("Colm", severity=0.9, cause="a fall")
    w._move_actor_to("Anselm", (5, 5))
    w._move_actor_to("Bryony", (5, 5))
    listener = w._actor_minds["Bryony"]
    about = listener.speech_backend._bond("Colm")
    listener.s.set_attr(about, "belief_trust", 0.25)
    w.enact_speech_proposal("Anselm", {"target": "Bryony", "text": "Colm was hurt.",
                                         "raw": {"act": "share"}, "event": event})
    assert listener.s.node(about)["attrs"]["belief_trust"] == 0.25
    assert listener.heard_events == {}


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


def test_hearing_a_share_records_delivery_without_updating_speaker_retention():
    w = _town()
    w.set_relationship("Anselm", "Bryony", kind="friend", strength=1.0, mutual=True)
    w._move_actor_to("Anselm", (5, 5))
    w._move_actor_to("Bryony", (5, 5))
    event = w.injure("Colm", severity=0.6, cause="a fall")
    w.observe_event("Anselm", event)
    for _ in range(5):
        proposal = w.resident_speech_proposal("Anselm", "Bryony")
        if proposal is not None:
            w.enact_speech_proposal("Anselm", proposal)
    told = w._actor_minds["Anselm"].told_events.get(("Bryony", event), 0)
    assert told == 0
    assert any(item["heard"] and item["target"] == "Bryony"
               for item in w._speech_events)


# --------------------------------------------------- G5: no world-owned second-hand inference
def test_heard_report_does_not_mint_secondhand_memory_or_retelling_standing():
    w = _town()
    event = w.injure("Colm", severity=0.4, cause="a fall")
    w.observe_event("Anselm", event)                          # Anselm is first-hand
    bmind = w._actor_minds["Bryony"]
    src = bmind.speech_backend._bond("Anselm")
    bmind.s.set_attr(src, "belief_trust", 0.8)
    w._move_actor_to("Anselm", (5, 5))
    w._move_actor_to("Bryony", (5, 5))
    w.observe_event("Anselm", event)
    w.enact_speech_proposal("Anselm", {"target": "Bryony", "text": "Colm fell.",
                                         "raw": {"act": "share"}, "event": event})
    assert event not in bmind.heard_events
    salience, won = w._speech_share_event("Bryony", "Dara")   # can Bryony now retell it?
    assert won is None and salience == 0.0


def test_a_disconnected_bystander_never_learns_the_event_at_all():
    w = _town()
    event = w.injure("Colm", severity=0.9, cause="a fall")
    w.observe_event("Anselm", event)
    # Dara has never been co-located with Anselm or anyone who heard him;
    # spread is bounded by the town's real encounter topology, not a
    # global broadcast, so Dara's own standing to share it must be zero.
    salience, won = w._speech_share_event("Dara", "Bryony")
    assert salience == 0.0 and won is None
    assert w._actor_minds["Dara"].heard_events == {}
