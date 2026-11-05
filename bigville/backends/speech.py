"""Local deterministic speech cognition for residents without an external provider.

The physical world supplies an encounter and the resident-held relationship
facts. This backend chooses whether and how to speak. It does not inspect the
physical world or enact an utterance there.
"""
from __future__ import annotations

from worlds.bigville_bond_world import KNOBS as BOND_KNOBS, SLOT_DEFAULTS as BOND_SLOTS
from worlds.bigville_speech_world import (
    ENCOUNTER_DEFAULTS, KIND_LABEL,
)


class DeterministicSpeechBackend:
    """Fallback speech decision provider, kept outside the world module."""

    accommodation_gain = 2.0

    def __init__(self, mind):
        self.mind = mind

    def _bond(self, target, relationship=None):
        mind = self.mind
        bond = mind.speech_bonds.get(target)
        if bond is None:
            attrs = dict(BOND_SLOTS)
            attrs.update(BOND_KNOBS)
            attrs.update({"holder_name": mind.name, "toward_name": str(target),
                          "prior_kind": "chosen"})
            bond = mind.s.add_node("Bond", attrs)
            mind.inner.add_edge_unchecked(mind.agent, "holds_bond", bond)
            target_node = mind.s.add_node("Townsperson", {"name": str(target)})
            mind.inner.add_edge_unchecked(bond, "toward", target_node)
            mind.speech_bonds[target] = bond
        if relationship:
            strength = float(relationship.get("strength", 0.0))
            kind = str(relationship.get("kind", "acquaintance"))
            mind.s.set_attr(bond, "tie_strength", max(0.0, strength))
            mind.s.set_attr(bond, "affect_affection", max(0.0, strength))
            mind.s.set_attr(bond, "affect_resentment",
                            max(0.0, -strength) if kind == "feud" else 0.0)
            mind.s.set_attr(bond, "prior_kind", kind)
        return bond

    def propose(self, target, *, relationship=None, obligation=False,
                fpp_is_greeting=False, fpp_is_question=False,
                share_salience=0.0, goal_pressure=0.0, stranger=False,
                arousal=0.4, loquacity_threshold=1.0):
        """Choose a speech act from situated encounter facts."""
        mind = self.mind
        bond = self._bond(target, relationship)
        old = mind.speech_encounters.get(target)
        if old is not None:
            mind.inner.remove_node(old)
        attrs = dict(ENCOUNTER_DEFAULTS)
        attrs.update({
            "obligation": 1.0 if obligation else 0.0,
            "fpp_is_greeting": 1.0 if fpp_is_greeting else 0.0,
            "fpp_is_question": 1.0 if fpp_is_question else 0.0,
            "share_salience": float(share_salience),
            "goal_pressure": float(goal_pressure),
            "stranger": 1.0 if stranger else 0.0,
            "speaker_arousal": float(arousal),
            "loquacity_threshold": float(loquacity_threshold),
            "decide_armed": 1.0,
            "chosen_speech_code": -1.0,
            "absence_minted": 0.0,
        })
        encounter = mind.s.add_node("Encounter", attrs)
        mind.inner.add_edge_unchecked(encounter, "at_bond", bond)
        mind.speech_encounters[target] = encounter
        ba = mind.s.node(bond)["attrs"]
        tie = max(0.0, float(ba.get("tie_strength", 0.0)))
        threshold = float(loquacity_threshold) / (1.0 + self.accommodation_gain * tie)
        if fpp_is_question:
            code = 6
        elif obligation:
            code = 1
        elif stranger:
            code = 0
        elif float(ba.get("affect_resentment", 0.0)) > 0.5:
            code = 3
        elif float(share_salience) * tie > 0.2:
            code = 5
        elif float(goal_pressure) > 0.2:
            code = 7
        elif fpp_is_greeting or (float(ba.get("affect_affection", 0.0)) > 0.0
                                 and mind.speech_choices.get(target, {}).get("kind") != "greeting"):
            code = 1
        elif float(arousal) >= threshold * 0.25:
            code = 2
        else:
            code = 0
        mind.s.set_attr(encounter, "chosen_speech_code", float(code))
        kind = KIND_LABEL.get(code, "undecided")
        choice = {"target": target, "code": code, "kind": kind,
                  "spoken": code not in (-1, 0), "encounter": encounter}
        if choice["spoken"]:
            loud = min(100.0, 1.0 + 0.6 * float(arousal))
            choice["loudness"] = loud
        mind.speech_choices[target] = choice
        return choice

    @staticmethod
    def _meaning(target, kind, *, context):
        """Compose a grounded meaning from the backend's selected speech act."""
        if kind == "greeting":
            return {"greeting": {"of": str(target)}}
        if kind == "smalltalk":
            topic = str(context.get("trade", "") or "")
            return {"topic": {"of": topic}} if topic else {
                "weather": {"of": str(context.get("weather", "clear"))}}
        if kind == "barb":
            return {"warning": {"of": str(target)}}
        if kind == "hedged":
            return {"uncertainty": {"of": "work"}}
        if kind == "share":
            event = context.get("event")
            return {"news": {"of": event if event is not None else {
                "village": {"weather": str(context.get("weather", "clear"))}}}}
        if kind == "answer":
            return {"acknowledgement": {"of": str(target)}}
        if kind == "request":
            return {"request": {"of": str(target)}}
        if kind == "offer":
            return {"offer": {"to": str(target)}}
        if kind == "question":
            return {"question": {"of": str(target)}}
        if kind == "thanks":
            return {"thanks": {"to": str(target)}}
        if kind == "apology":
            return {"apology": {"to": str(target)}}
        if kind == "farewell":
            return {"farewell": {"to": str(target)}}
        if kind == "complaint":
            return {"complaint": {"to": str(target)}}
        if kind == "promise":
            return {"promise": {"to": str(target)}}
        return None

    def propose_free_text(self, target, *, context, encounter=None):
        """Return a complete local speech proposal for the world to enact."""
        choice = self.propose(target, **dict(encounter or {}))
        if not choice["spoken"]:
            return None
        meaning = self._meaning(target, choice["kind"], context=context)
        if meaning is None:
            return None
        text = self.mind.goal_utterance(target, meaning)
        if not text:
            return None
        return {"target": target, "text": str(text),
                "raw": {"act": choice["kind"], "target": str(target),
                        "meaning": meaning},
                "loudness": max(1.0, choice.get("loudness", 1.0)),
                "event": context.get("event_ref") if choice["kind"] == "share" else None}
