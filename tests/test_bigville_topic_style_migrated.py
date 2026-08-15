"""Rung 1 (topic content: role/trade idiolect smalltalk + first-person experience
sharing) and Rung 2 (talk rate scaled by relationship, plus the population-relationship-
seeding prerequisite) from ``docs/research/bigville/BIGVILLE_TOPIC_AND_STYLE_SCOPING.md``,
composing with the already-landed gossip drive (``tests/test_bigville_gossip_migrated.py``)
without changing any of its own mechanism.

R1 gates: ``_speech_goal``'s ``smalltalk`` branch now reads the SPEAKER's own trade
instead of always defaulting to weather, with a regression control showing a forced
constant trade collapses output to indistinguishable (the pre-Rung-1 baseline shape);
new ``create_event`` call sites at skill/apprenticeship and production/trade completion,
each passing ``observer=actor`` (closing the gap the prior gossip scoping doc found
``injure``/``_record_death_event`` both leave open) and landing in
``_speech_share_event``'s already-unified candidate pool with ZERO changes to that
function; and a self/third-party discriminator on the "news" render, with a regression
test that shows the WRONG third-person form the discriminator fixes.

R2 gates: the population-relationship-seeding prerequisite (``seeds/
bigville_townspeople_50.json``'s 22-edge ``relationships`` list, previously dead data --
no code path built a live world from it at all -- turned into real ``set_relationship``
calls; a sparse, opt-in workplace-proximate pass for the general town100 population); and
the ``accommodation_gain`` coupling on ``decide_speech``'s smalltalk gate. This file also
reports the HONEST, MEASURED finding the naive falsifiable prediction misses: a real
``set_relationship``-populated tie ALSO sets ``affect_affection > 0`` (decide_speech's own
pre-existing, untouched coupling), which wins the branch immediately ABOVE smalltalk
(greeting) in the existing ladder -- so end-to-end, a tied pair greets, not smalltalk-s,
and the new gain's effect is only observable in the narrow band the ladder leaves it:
tie_strength > 0 without a coexisting positive affect_affection. Both the isolated
mechanism (which works exactly as designed) and the full pathway (which does not show the
literal predicted smalltalk-rate delta, for a real, diagnosed, pre-existing reason) are
measured here, not just the convenient one.
"""
from __future__ import annotations

import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import worlds.bigville_world as bw                             # noqa: E402
from worlds.bigville_world import BigvilleWorld as World        # noqa: E402
from worlds.bigville_world import BigvilleOcelotActor           # noqa: E402
from bigville.runtime import _realize_meaning                   # noqa: E402


def _town():
    w = World()
    w.add_actor("Anselm", role="smith")
    w.add_actor("Bryony", role="collier")
    w.add_actor("Colm", role="woodworker")
    w.add_actor("Dara", role="baker")
    return w


# ============================================================ R1a: role/trade smalltalk
def test_smalltalk_content_reflects_the_speakers_own_trade():
    w = _town()
    smith_meaning = w._speech_goal("Bryony", "smalltalk", speaker="Anselm")
    baker_meaning = w._speech_goal("Anselm", "smalltalk", speaker="Dara")
    assert smith_meaning == {"topic": {"of": "smith"}}
    assert baker_meaning == {"topic": {"of": "baker"}}
    assert "weather" not in str(smith_meaning) and "weather" not in str(baker_meaning)
    assert _realize_meaning(smith_meaning) != _realize_meaning(baker_meaning), (
        "two residents of different trades should not say the same smalltalk")


def test_smalltalk_falls_back_to_weather_with_no_speaker_or_unknown_trade():
    w = _town()
    # No speaker at all -- the legacy, pre-Rung-1 call shape (existing callers that
    # never learn about `speaker` keep behaving exactly as before).
    legacy = w._speech_goal("Bryony", "smalltalk")
    assert legacy == {"weather": {"of": "clear"}}
    # A speaker with no role/trade at all still degrades to weather, not a crash.
    w.eng.set_attr(w._actors["Anselm"], "trade", "")
    w.eng.set_attr(w._actors["Anselm"], "role", "")
    blank = w._speech_goal("Bryony", "smalltalk", speaker="Anselm")
    assert blank == {"weather": {"of": "clear"}}


def test_forcing_a_constant_trade_collapses_smalltalk_to_indistinguishable_output():
    """Falsifiable control (scoping doc 3.2a): with the differentiator forced to a
    single constant value across the population, smalltalk should collapse to
    indistinguishable output regardless of WHICH resident is speaking -- exactly
    the shape of the pre-Rung-1 baseline, where every smalltalk utterance was the
    same weather line no matter who said it.
    """
    w = _town()
    for name in ("Anselm", "Bryony", "Colm", "Dara"):
        w.eng.set_attr(w._actors[name], "trade", "smith")
    utterances = {name: _realize_meaning(w._speech_goal("Dara", "smalltalk", speaker=name))
                  for name in ("Anselm", "Bryony", "Colm")}
    assert len(set(utterances.values())) == 1, (
        "a forced-constant trade must make smalltalk indistinguishable by speaker "
        f"identity, got: {utterances}")
    # And the converse: letting trade vary re-differentiates it (the mechanism is
    # doing real work, not just always collapsing).
    varied = {name: _realize_meaning(w._speech_goal("Dara", "smalltalk", speaker=name))
              for name in ("Anselm", "Bryony", "Colm", "Dara")}
    w2 = _town()
    varied2 = {name: _realize_meaning(w2._speech_goal("Dara", "smalltalk", speaker=name))
               for name in ("Anselm", "Bryony", "Colm")}
    assert len(set(varied2.values())) > 1, "distinct trades should differentiate smalltalk"


# ================================================== R1c: self / third-party discriminator
def test_a_residents_own_event_renders_first_person():
    w = _town()
    event = w.create_event("learned_skill", subject="Anselm",
                           detail="Anselm grew more skilled at smith.",
                           observer="Anselm", severity=0.15)
    meaning = w._speech_goal("Bryony", "share", event=event, speaker="Anselm")
    assert meaning["news"]["of"]["self"] is True
    text = _realize_meaning(meaning)
    assert text == "I grew more skilled at smith.", text
    assert "I heard that" not in text


def test_a_relayed_event_about_someone_else_stays_third_person():
    w = _town()
    event = w.create_event("learned_skill", subject="Anselm",
                           detail="Anselm grew more skilled at smith.",
                           observer="Anselm", severity=0.15)
    # Bryony re-telling Anselm's news to Colm: Bryony is the speaker, Anselm the
    # subject -- the discriminator must NOT collapse to first person here.
    meaning = w._speech_goal("Colm", "share", event=event, speaker="Bryony")
    assert meaning["news"]["of"]["self"] is False
    text = _realize_meaning(meaning)
    assert text == "I heard that Anselm grew more skilled at smith.", text


def test_omitting_the_discriminator_renders_the_wrong_third_person_form():
    """Regression control: WITHOUT the self/third-party discriminator (the pre-
    Rung-1c call shape, no ``speaker`` passed at all), a resident's own achievement
    renders in the WRONG third-person form -- "I heard that Anselm..." spoken BY
    Anselm about himself -- which is exactly the bug 1c closes. This shows the bug,
    not just the fix in isolation.
    """
    w = _town()
    event = w.create_event("learned_skill", subject="Anselm",
                           detail="Anselm grew more skilled at smith.",
                           observer="Anselm", severity=0.15)
    broken_meaning = w._speech_goal("Bryony", "share", event=event)  # no speaker=...
    assert "self" not in broken_meaning["news"]["of"]
    broken_text = _realize_meaning(broken_meaning)
    assert broken_text == "I heard that Anselm grew more skilled at smith.", broken_text
    # The fixed form, same event, same speaker -- genuinely different rendering.
    fixed_text = _realize_meaning(w._speech_goal("Bryony", "share", event=event, speaker="Anselm"))
    assert fixed_text != broken_text
    assert fixed_text == "I grew more skilled at smith."


# ========================= R1b: new self-observed events join the unified share pool
def test_skill_progress_mints_a_self_observed_event_the_speaker_can_share():
    w = World(autonomous_actors=False)
    w.add_actor("Anselm", role="smith", skill=0.5)
    w.add_actor("Master", role="smith", skill=0.9)
    w.add_actor("Bryony", role="collier")
    w.apprentice("Anselm", "Master")
    w.pass_period(1)
    assert w.skill("Anselm") > 0.5
    # Zero changes to _speech_share_event -- this event lands in the SAME pool
    # observed_event/injure events already use.
    salience, won = w._speech_share_event("Anselm", "Bryony")
    assert salience > 0.0
    assert won is not None
    assert w.eng.node(won)["attrs"]["kind"] == "learned_skill"
    assert w.eng.node(won)["attrs"]["subject"] == "Anselm"


def test_a_capped_apprentice_does_not_mint_a_new_event_every_period():
    w = World(autonomous_actors=False)
    w.add_actor("Anselm", role="smith", skill=0.9)
    w.add_actor("Master", role="smith", skill=0.9)   # already at the master's level
    w.apprentice("Anselm", "Master")
    w.pass_period(1)
    events_after_first = len(w.eng.neighbours(w._actors["Anselm"], "observed_event"))
    w.pass_period(1)
    events_after_second = len(w.eng.neighbours(w._actors["Anselm"], "observed_event"))
    assert events_after_first == 0 and events_after_second == 0, (
        "no real skill change happened (already capped at the master's level) -- "
        "the delta guard must not mint an event anyway")


def test_literacy_progress_mints_a_self_observed_event():
    w = World(autonomous_actors=False)
    w.add_actor("Pupil", role="labourer", literacy=0.0, learn=1.0)
    w.add_actor("Teacher", role="teacher", literacy=1.0, capability=1.0)
    w.enrol("Pupil", "Teacher")
    w.pass_period(1)
    assert w.literacy("Pupil") > 0.0
    events = w.eng.neighbours(w._actors["Pupil"], "observed_event")
    assert len(events) == 1
    assert w.eng.node(events[0])["attrs"]["kind"] == "learned_lesson"


def test_finishing_a_production_run_mints_a_self_observed_event():
    w = World()
    w.add_actor("Smith", role="smith", skill=0.8)
    for kind in ("iron", "charcoal", "timber", "ore"):
        w.set_stock(kind, 50)
    w.observe("Smith", harvest=0.9)
    w.decide("Smith")
    made = w.produce_run("Smith")
    assert made > 0
    events = w.eng.neighbours(w._actors["Smith"], "observed_event")
    kinds = [w.eng.node(e)["attrs"]["kind"] for e in events]
    assert "produced_goods" in kinds


def test_a_completed_sale_mints_a_self_observed_event():
    w = World()
    w.add_actor("Farmer", role="farmer")
    w.add_shop("bakery", (1, 1), input_kind="grain", output_kind="bread", price=1)
    w.eng.set_attr(w._shops["bakery"], "coin", 100.0)
    w.set_stock("grain", 20)
    w.stock_person("Farmer", "grain", 10, price=1.0, willing=True)
    ok = w.sell_to_shop("Farmer", "bakery", "grain", 5)
    assert ok
    events = w.eng.neighbours(w._actors["Farmer"], "observed_event")
    kinds = [w.eng.node(e)["attrs"]["kind"] for e in events]
    assert "sold_goods" in kinds


# ========================================================= R2 prerequisite: relationships
def test_townspeople_50_relationships_translate_to_real_set_relationship_calls():
    """seeds/bigville_townspeople_50.json's 22-edge relationships list was, until
    this rung, dead data: no code path built a live world from it at all (checked
    directly -- no scenario file references it, ``from_scenario`` reads
    ``scenarios/*.json`` not ``seeds/*.json``). ``from_townspeople_50`` is the new,
    minimal construction path.
    """
    w = World.from_townspeople_50()
    assert len(w._actors) == 50
    assert len(w._relationships) == 22
    rival = w.relationship("Mary", "John")
    assert rival is not None
    rival_attrs = w.eng.node(rival)["attrs"]
    assert rival_attrs["kind"] == "feud"
    assert rival_attrs["strength"] < 0.0
    friend = w.relationship("Prudence Inkwell", "Barnaby Stoat")
    assert friend is not None
    friend_attrs = w.eng.node(friend)["attrs"]
    assert friend_attrs["kind"] != "feud"
    assert friend_attrs["strength"] > 0.0


def test_a_bare_from_town100_still_seeds_zero_relationships():
    """Regression guard: seeding must stay OPT-IN.  test_bigville_reporting.py
    asserts an EXACT ``directed_bonds`` count against a bare ``from_town100()``
    town; auto-wiring population relationships into ``populate_town100`` would
    silently break that baseline.
    """
    w = World.from_town100(autonomous_actors=False)
    assert len(w._relationships) == 0


def test_town100_workplace_relationships_are_sparse_not_all_pairs():
    w = World.from_town100(autonomous_actors=False)
    minted = w.seed_workplace_relationships()
    assert minted > 0
    # 100 residents, an all-pairs graph would be ~4950 undirected pairs; the ring
    # construction must stay far below that -- bounded by population size, not
    # by the square of the largest single-workplace group (25 labourers).
    assert minted < 150, f"expected a sparse ring (O(n)), got {minted} edges"
    # Every resident who got a tie has only a HANDFUL of them, not a clique.
    outgoing = {}
    for (src, _tgt) in w._relationships:
        outgoing[src] = outgoing.get(src, 0) + 1
    assert max(outgoing.values()) <= 2, (
        "a ring gives each resident at most one outgoing tie per direction "
        f"(mutual=True), not a clique: {outgoing}")


# ============================================================= R2: accommodation_gain
def test_zero_gain_collapses_the_smalltalk_rate_gap_between_tie_conditions():
    """Isolated-mechanism measurement (bypasses decide_speech's OWN, pre-existing,
    untouched affect_affection>0 -> greeting branch by holding affection at zero
    directly, so only the new coupling under test is exercised). A real,
    population-level run: arousal drawn Uniform(0,1) across 1000 trials per
    condition, comparing tie_strength=0.0 against tie_strength=3.0.
    """
    def smalltalk_rate(tie, n=1000, seed=7):
        rng = random.Random(seed)
        hits = 0
        for _ in range(n):
            arousal = rng.uniform(0.0, 1.0)
            mind = BigvilleOcelotActor("A")
            bond = mind._speech_bond("B", None)
            mind.s.set_attr(bond, "tie_strength", tie)
            mind.s.set_attr(bond, "affect_affection", 0.0)
            choice = mind.decide_speech("B", relationship=None, arousal=arousal,
                                        loquacity_threshold=1.0)
            if choice["kind"] == "smalltalk":
                hits += 1
        return hits / n

    old_gain = bw.ACCOMMODATION_GAIN
    bw.ACCOMMODATION_GAIN = 0.0
    try:
        zero_tie = smalltalk_rate(0.0)
        high_tie = smalltalk_rate(3.0)
    finally:
        bw.ACCOMMODATION_GAIN = old_gain
    assert zero_tie == high_tie, (
        "gain=0.0 must fully collapse the tie-strength coupling back to the "
        f"current baseline (independent of interlocutor identity): {zero_tie} vs {high_tie}")


def test_nonzero_gain_measurably_raises_the_smalltalk_rate_for_a_high_tie():
    """Same isolated measurement as above, with the shipped ACCOMMODATION_GAIN
    (2.0). Real, run numbers (not a formula check): 1000 draws per condition,
    tie=0.0 vs tie=3.0, loquacity_threshold=1.0.
    """
    def smalltalk_rate(tie, n=1000, seed=7):
        rng = random.Random(seed)
        hits = 0
        for _ in range(n):
            arousal = rng.uniform(0.0, 1.0)
            mind = BigvilleOcelotActor("A")
            bond = mind._speech_bond("B", None)
            mind.s.set_attr(bond, "tie_strength", tie)
            mind.s.set_attr(bond, "affect_affection", 0.0)
            choice = mind.decide_speech("B", relationship=None, arousal=arousal,
                                        loquacity_threshold=1.0)
            if choice["kind"] == "smalltalk":
                hits += 1
        return hits / n

    assert bw.ACCOMMODATION_GAIN > 0.0, "the shipped gain must be a real, nonzero value"
    zero_tie = smalltalk_rate(0.0)
    high_tie = smalltalk_rate(3.0)
    assert high_tie > zero_tie + 0.1, (
        f"expected a measurable (>10pp) rate increase for a high tie, got "
        f"{zero_tie:.3f} -> {high_tie:.3f}")


def test_full_pathway_via_spontaneous_speech_tick_reaches_smalltalk_for_a_tied_pair():
    """The REQUIRED real, run, end-to-end measurement (matching the gossip work's
    own pattern: run _spontaneous_speech_tick() N times and compare observed
    rates) -- using an ACTUAL set_relationship-populated tie, not the isolated
    mechanism above.

    First measured run of this test found the coupling correctly wired but
    end-to-end INERT: decide_speech's pre-existing greeting branch
    (affect_affection > 0) fires unconditionally on ANY positive relationship,
    every single encounter, forever, outranking the arousal-gated smalltalk
    branch this rung's coupling feeds -- a pre-existing composition hazard
    that had simply never been exercised, because set_relationship was never
    called in production code until this rung's own relationship-seeding fix.
    A real friendship is a standing REASON to greet, not a standing
    INSTRUCTION to greet every encounter; the fix reuses already-held state
    (speech_choices, the same per-target "what did I last say" dict the
    gossip work's own told_events/heard_events idiom already established) so
    greeting no longer outranks smalltalk once the pair's last exchange was
    itself a greeting. Both the zero-tie and high-tie cases below are
    measured, not asserted.
    """
    def run_and_count(tie_strength, n=100):
        w = World()
        w.add_actor("Anselm", role="smith")
        w.add_actor("Bryony", role="collier")
        w._move_actor_to("Anselm", (5, 5))
        w._move_actor_to("Bryony", (5, 5))
        if tie_strength > 0.0:
            w.set_relationship("Anselm", "Bryony", kind="friend", strength=tie_strength, mutual=True)
        kinds = {}
        for _ in range(n):
            w._spontaneous_speech_tick()
            choice = w._actor_minds["Anselm"].speech_choices.get("Bryony")
            if choice is not None:
                kinds[choice["kind"]] = kinds.get(choice["kind"], 0) + 1
        return kinds

    zero_tie_kinds = run_and_count(0.0)
    high_tie_kinds = run_and_count(3.0)

    # The zero-tie pair reaches smalltalk (nothing else outranks it: no
    # obligation, no resentment, no salient event, arousal clears the
    # unmodified threshold) and never greets -- there is no affection to
    # trigger it.
    assert zero_tie_kinds.get("smalltalk", 0) > 0
    assert zero_tie_kinds.get("greeting", 0) == 0

    # The high-tie pair now reaches BOTH kinds -- greeting is no longer an
    # unconditional every-encounter sink, and smalltalk (the branch this
    # rung's accommodation coupling actually feeds) becomes reachable.
    assert high_tie_kinds.get("greeting", 0) > 0
    assert high_tie_kinds.get("smalltalk", 0) > 0
