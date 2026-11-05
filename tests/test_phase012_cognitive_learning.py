"""Phase 012: skills are learned physically or cognitively.

Physical practice always consolidates into skill levels. Cognitive practice (understanding) consolidates
only when the `cognitive_practice` subsystem is on. Off, the completed work still logs its minutes, the
world leaves the levels alone, and it publishes the practice to the actor as a "practice" observation.
Aptitude's learning-to-learn gain comes only through skills whose learning the world models.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld as World      # noqa: E402


def _inside(w, key):
    """A walkable cell inside the building's footprint."""
    x, y, fw, fh = w._building_sites[key]
    return next((x + dx, y + dy) for dy in range(fh) for dx in range(fw) if (x + dx, y + dy) in w._map_cells)


def _smith(**kwargs):
    w = World(**kwargs)
    w.add_actor("Smith", role="smith", skill=0.9)
    w.set_stock("iron", 40)
    w.set_stock("charcoal", 40)
    w._move_actor_to("Smith", _inside(w, "forge"))
    return w


def _scribe(**kwargs):
    w = World(**kwargs)
    w.add_actor("Quill", role="scribe", skill=0.6)
    w.set_stock("feather", 5)
    w.give_tool("Quill", "knife")
    return w


def _raw_level(w, actor, skill):
    """The unrounded own level (skill_level rounds to four places, too coarse for a small gain)."""
    return float(w._levels(actor).get(skill, 0.0))


def _raw_aptitude(w, actor):
    return float(w.eng.node(w._actors[actor])["attrs"]["aptitude"])


def _end_period(w):
    """Advance one period and run the period effects, including practice consolidation."""
    attrs = w.eng.node(w._town)["attrs"]
    w.eng.set_attr(w._town, "period", float(attrs.get("period", 0.0)) + 1.0)
    w._resolve_period_effects()


def _practice_observations(w, actor):
    return w.actor_observations(actor, "practice")


def test_smithing_practice_raises_smithing_with_the_cognitive_switch_off():
    w = _smith()
    assert w.physical_subsystems["cognitive_practice"] is False
    before = _raw_level(w, "Smith", "smithing")
    assert w.do("Smith", "forge_nails")
    assert float(w.eng.node(w._actors["Smith"])["attrs"]["skill_practice"]["smithing"]) == 10.0
    _end_period(w)
    assert _raw_level(w, "Smith", "smithing") > before
    assert _practice_observations(w, "Smith") == [], "physical practice is consolidated, not published"


def test_writing_practice_leaves_writing_unchanged_and_is_observed_with_the_switch_off():
    w = _scribe()
    writing = _raw_level(w, "Quill", "writing")
    letters = float(w.eng.node(w._actors["Quill"])["attrs"].get("metaskill_levels", {}).get("letters", 0.0))
    assert w.do("Quill", "cut_quill")

    # the minutes are still logged for the period
    logged = w.eng.node(w._actors["Quill"])["attrs"]["skill_practice"]
    assert logged.get("writing", 0.0) > 0.0

    observations = _practice_observations(w, "Quill")
    assert len(observations) == 1
    assert observations[0]["skill"] == "writing"
    assert observations[0]["learning"] == "cognitive"
    assert observations[0]["minutes"] == logged["writing"]

    _end_period(w)
    assert _raw_level(w, "Quill", "writing") == writing, "the world does not change a cognitive level"
    assert float(w.eng.node(w._actors["Quill"])["attrs"].get("metaskill_levels", {}).get("letters", 0.0)) == letters
    assert w.eng.node(w._actors["Quill"])["attrs"].get("skill_practice") == {}, "the period clears the log"


def test_writing_rises_with_the_cognitive_switch_on_and_is_not_published():
    w = _scribe(physical_subsystems={"cognitive_practice": True})
    writing = _raw_level(w, "Quill", "writing")
    assert w.do("Quill", "cut_quill")
    assert _practice_observations(w, "Quill") == []
    _end_period(w)
    assert _raw_level(w, "Quill", "writing") > writing


def test_aptitude_gain_comes_only_through_skills_the_world_models():
    # Physical practice is modelled, so it carries the learning-to-learn gain.
    smith = _smith()
    assert _raw_aptitude(smith, "Smith") == 1.0
    assert smith.do("Smith", "forge_nails")
    _end_period(smith)
    assert _raw_aptitude(smith, "Smith") > 1.0

    # Cognitive practice with the switch off is not modelled, so aptitude does not move.
    off = _scribe()
    assert _raw_aptitude(off, "Quill") == 1.0
    assert off.do("Quill", "cut_quill")
    _end_period(off)
    assert _raw_aptitude(off, "Quill") == 1.0

    # With the switch on, the same cognitive practice carries the gain.
    on = _scribe(physical_subsystems={"cognitive_practice": True})
    assert on.do("Quill", "cut_quill")
    _end_period(on)
    assert _raw_aptitude(on, "Quill") > 1.0


def test_the_practice_observation_reaches_the_actors_backend_context_for_one_turn():
    from bigville.game import BigvilleGame

    w = _scribe()
    w.add_actor("Other", role="farmer")
    game = BigvilleGame(w, autonomous=True)
    assert game._context("Quill").observations["practice"] == []
    assert w.do("Quill", "cut_quill")
    w._turn += 1                                  # the work completes; the next turn's contexts carry it

    first = game._context("Quill").observations["practice"]
    assert [(r["skill"], r["learning"], r["recipe"]) for r in first] == [("writing", "cognitive", "cut_quill")]
    assert game._context("Quill").observations["practice"] == first, "every context of one turn agrees"
    assert game._context("Other").observations["practice"] == [], "only the practising actor is told"

    w._turn += 1
    assert game._context("Quill").observations["practice"] == [], "each record is carried for one turn"
