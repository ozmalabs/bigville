"""Phase 044: pregnancy and birth. The world's physical side, behind the births switch.

Off by default (physical_subsystems.births). With it off, every method here returns its neutral value
and the world's behaviour is unchanged. With it on, once a day (from the dawn tick):

- a fertile woman in a recorded union (Phase 009's `in_union` Union node, with a living partner) may
  conceive. The chance is the BIRTHS conception rate for her age band, turned into a daily chance.
- a pregnancy lasts gestation_days, costs food (pregnancy_food) and, late in term, work capacity
  (pregnancy_load). Strength and stamina read the capacity factor.
- at term the birth is delivered: a stillbirth is recorded and no resident is added. A live birth
  calls birth() (the newborn is a resident with a name, the mother's household, and a stock of
  traits), records the genealogy (bore, fathered, and the kin fields Phase 009 reads), and draws the
  risks: the mother's death (cause childbirth) and the first-year death (cause illness) through harm().
  A midwife (midwifery skill) in reach halves those risks (midwife_factor).
- an infant whose mother lives with it is nursed: its hunger rate is nursed_hunger. Otherwise an infant
  eats at its life-stage food rate, as the rest of the table does.

Every draw is stateless: _stable_draw keys each draw on the world seed, a stream name, the involved resident's
state and the day. The world's RNG stream is never consumed, and the same seed and state give the same births.
Which union a resident forms, and whether a resident wants a child, are the residents' (Phase 009 and the
backends).
"""
from __future__ import annotations

import math


class BirthsMixin:
    """Methods mixed into BigvilleWorld. Names are prefixed to keep them clear of the world's own."""

    def _births_on(self):
        return bool(self.physical_subsystems.get("births"))

    def _birth_day(self):
        return int(float(self.calendar()["day"]))

    def _term_fraction(self, attrs):
        """How far through its term a pregnancy is: 0 at conception, 1 at the due day (clipped)."""
        gestation = float(self.E.BIRTHS["gestation_days"])
        elapsed = self._birth_day() - float(attrs.get("conceived_day", 0.0))
        return min(1.0, max(0.0, elapsed / gestation)) if gestation > 0.0 else 1.0

    def _union_partner(self, mother):
        """The node of the living partner in the mother's recorded union (a Union with ended 0), or None.

        A partner is opposite in kin_sex. A partner in the village is an Agent and must be alive. An
        out-of-village partner is a Kin node and must not be recorded dead."""
        node = self._actors[mother]
        own_sex = self.eng.node(node)["attrs"].get("kin_sex")
        for union in self.eng.neighbours(node, "in_union"):
            record = self.eng.node(union)["attrs"]
            if float(record.get("ended", 0.0)) == 1.0:
                continue
            other = int(record["b"]) if int(record["a"]) == int(node) else int(record["a"])
            if not self.eng.has_node(other):
                continue
            attrs = self.eng.node(other)["attrs"]
            if attrs.get("kin_sex") == own_sex:
                continue
            if self.eng.node(other)["type"] == "Agent":
                if float(attrs.get("alive", 1.0)) != 1.0:
                    continue
            elif float(attrs.get("kin_dead", 0.0)) == 1.0:
                continue
            return other
        return None

    def _partner_name(self, partner_node):
        """The partner's name if the partner is a resident of the village, else ''."""
        name = str(self.eng.node(partner_node)["attrs"].get("name", ""))
        return name if name in self._actors and int(self._actors[name]) == int(partner_node) else ""

    def _conception_rate(self, age):
        """Conceptions per woman-year in her age band (BIRTHS.conception_per_year), 0 outside it."""
        for band in self.E.BIRTHS["conception_per_year"]:
            if float(band["age_min"]) <= age < float(band["age_max"]) + 1.0:
                return float(band["rate"])
        return 0.0

    def _births_day(self):
        """One day of pregnancy and birth, at the dawn tick. Does nothing with the births switch off."""
        if not self._births_on():
            return
        day = self._birth_day()
        days_per_year = float(self.E.TIME["days_per_year"])
        for name in list(self._actors):
            node = self._actors[name]
            attrs = self.eng.node(node)["attrs"]
            if float(attrs.get("alive", 1.0)) != 1.0:
                continue
            if float(attrs.get("pregnant", 0.0)) == 1.0:
                if day >= float(attrs.get("due_day", 0.0)):
                    self._deliver_birth(name, day)
                continue
            if attrs.get("kin_sex") != "female":
                continue
            age = float(attrs.get("age", 0.0))
            fertile = (float(self.E.BIRTHS["fertile_age_min"]) <= age
                       < float(self.E.BIRTHS["fertile_age_max"]) + 1.0)
            rate = self._conception_rate(age) if fertile else 0.0
            if rate <= 0.0 or day < float(attrs.get("birth_block_until", 0.0)):
                continue
            partner = self._union_partner(name)
            if partner is None:
                continue
            chance = 1.0 - math.exp(-rate / days_per_year)
            if self._stable_draw("births", "conceive", name, day, actors=(name,)) < chance:
                self._conceive(name, partner, day)

    def _conceive(self, mother, partner_node, day):
        node = self._actors[mother]
        self.eng.set_attr(node, "pregnant", 1.0)
        self.eng.set_attr(node, "conceived_day", float(day))
        self.eng.set_attr(node, "due_day", float(day) + float(self.E.BIRTHS["gestation_days"]))
        self.eng.set_attr(node, "partner", float(partner_node))

    def _midwife_in_reach(self, mother):
        """A living resident with the midwifery skill, on the mother's cell or within midwife_reach, or None."""
        here = self.actor_position(mother)
        if here is None:
            return None
        reach = float(self.E.BIRTHS["midwife_reach"])
        for name in self._actors:
            if name == mother or not self.is_alive(name):
                continue
            if self.skill_level(name, "midwifery") <= 0.0:
                continue
            there = self.actor_position(name)
            distance = self.distance(here, there) if there is not None else None
            if distance is not None and float(distance) <= reach:
                return name
        return None

    def _newborn_name(self, mother, day):
        """A first name from FOUNDING_FIRST_NAMES (a seeded start, then the next unused one) and the mother's
        surname. The name is unused in the village: a clash moves on to the next first name, then to a number."""
        firsts = list(self.E.FOUNDING_FIRST_NAMES)
        surname = str(mother).split()[-1] if " " in str(mother) else ""
        start = int(self._stable_draw("births", "name", mother, day, actors=(mother,)) * len(firsts)) % len(firsts)
        for offset in range(len(firsts)):
            candidate = " ".join(part for part in (firsts[(start + offset) % len(firsts)], surname) if part)
            if candidate not in self._actors:
                return candidate
        number = 2
        while True:
            candidate = " ".join(part for part in (firsts[start], surname, str(number)) if part)
            if candidate not in self._actors:
                return candidate
            number += 1

    def _deliver_birth(self, mother, day):
        """Delivery at term: the stillbirth draw, the newborn (birth() and the genealogy), and the risks.
        Every draw is keyed on the involved residents' state and the day, so the same seed and state give the
        same delivery."""
        node = self._actors[mother]
        attrs = self.eng.node(node)["attrs"]
        partner_ref = int(attrs.get("partner", -1.0)) if "partner" in attrs else -1
        partner_node = partner_ref if partner_ref >= 0 and self.eng.has_node(partner_ref) else None
        father = self._partner_name(partner_node) if partner_node is not None else ""
        table = self.E.BIRTHS
        midwife = self._midwife_in_reach(mother)
        factor = float(table["midwife_factor"]) if midwife is not None else 1.0
        self.eng.set_attr(node, "pregnant", 0.0)
        self.eng.set_attr(node, "birth_block_until", float(day) + float(table["postpartum_block_days"]))
        if self._stable_draw("births", "stillbirth", mother, day, actors=(mother,)) < float(table["stillbirth"]):
            self._stillbirth_log = list(getattr(self, "_stillbirth_log", [])) + [
                {"mother": mother, "father": father, "day": day}]
            self.create_event("stillbirth", subject=mother,
                              detail=f"{mother} bore a stillborn child.", public=False)
        else:
            sex = "female" if self._stable_draw("births", "sex", mother, day, actors=(mother,)) < 0.5 else "male"
            child = self.birth(mother, self._newborn_name(mother, day),
                               father=father or None, home_cell=self.actor_position(mother))
            if child:
                child_node = child
                self._record_newborn_kin(child_node, node, partner_node, sex, mother)
                child_name = str(self.eng.node(child_node)["attrs"]["name"])
                if self._stable_draw("births", "infant", child_name, day,
                                     actors=(mother, child_name)) < float(table["infant_first_year_death"]) * factor:
                    self.harm(child_name, 1.0, "illness", fragility=False)
        if self._stable_draw("births", "maternal", mother, day,
                             actors=(mother,)) < float(table["maternal_death"]) * factor:
            self.harm(mother, 1.0, "childbirth", fragility=False)

    def _record_newborn_kin(self, child_node, mother_node, partner_node, sex, mother):
        """Genealogy for a newborn (Phase 009's vocabulary): the kin fields that _kin_index reads, and bore and
        fathered edges from each parent. The father's edge comes from the partner, in or out of the village."""
        self.eng.set_attr(child_node, "kin_sex", sex)
        self.eng.set_attr(child_node, "kin_birth", float(self._kin_clock()))
        self.eng.set_attr(child_node, "kin_dead", 0.0)
        self.eng.set_attr(child_node, "kin_death", 0.0)
        self.eng.set_attr(child_node, "mother", str(mother))
        self.eng.add_edge_unchecked(mother_node, "bore", child_node)
        if partner_node is not None:
            self.eng.add_edge_unchecked(partner_node, "fathered", child_node)

    def _nursed(self, actor):
        """An infant is nursed while its mother lives and is with it (the same cell, or the same household)."""
        attrs = self.eng.node(self._actors[actor])["attrs"]
        mother = str(attrs.get("mother", ""))
        if not mother or mother not in self._actors or not self.is_alive(mother):
            return False
        mattrs = self.eng.node(self._actors[mother])["attrs"]
        household = str(attrs.get("household", ""))
        if household and household == str(mattrs.get("household", "")):
            return True
        return self.actor_position(actor) is not None and self.actor_position(actor) == self.actor_position(mother)

    def _hunger_rate(self, actor):
        """The hunger a period adds to a resident. 1.0 with the switch off (the world's rule, unchanged). With it
        on: the life stage's food need, raised by pregnancy_food while pregnant, and nursed_hunger for a nursed infant."""
        if not self._births_on():
            return 1.0
        attrs = self.eng.node(self._actors[actor])["attrs"]
        stage = str(attrs.get("life_stage", "adult"))
        if self._life_stage_is(stage, "infant") and self._nursed(actor):
            return float(self.E.BIRTHS["nursed_hunger"])
        rate = float(self.E.LIFE_STAGES.get(stage, self.E.LIFE_STAGES["adult"])["food"])
        if float(attrs.get("pregnant", 0.0)) == 1.0:
            rate *= float(self.E.BIRTHS["pregnancy_food"])
        return rate

    def _capacity_factor(self, actor):
        """The share of work capacity a pregnancy leaves (1.0 with the switch off or no pregnancy). It falls by
        pregnancy_load.max_load over the part of the term after pregnancy_load.from_term."""
        if not self._births_on():
            return 1.0
        attrs = self.eng.node(self._actors[actor])["attrs"]
        if float(attrs.get("pregnant", 0.0)) != 1.0:
            return 1.0
        spec = self.E.BIRTHS["pregnancy_load"]
        start = float(spec["from_term"])
        if start >= 1.0:
            return 1.0
        frac = min(1.0, max(0.0, (self._term_fraction(attrs) - start) / (1.0 - start)))
        return 1.0 - float(spec["max_load"]) * frac

    def pregnancy(self, actor):
        """A pregnant resident's read-off: the due day, the conception day, and the partner's name (or '' when the
        partner is not in the village). None when the resident is not pregnant."""
        attrs = self.eng.node(self._actor(actor))["attrs"]
        if float(attrs.get("pregnant", 0.0)) != 1.0:
            return None
        partner_ref = int(attrs.get("partner", -1.0)) if "partner" in attrs else -1
        partner = self._partner_name(partner_ref) if partner_ref >= 0 and self.eng.has_node(partner_ref) else ""
        return {"conceived_day": float(attrs.get("conceived_day", 0.0)), "due_day": float(attrs.get("due_day", 0.0)),
                "term_fraction": round(self._term_fraction(attrs), 4), "partner": partner}

    def _birth_readoffs(self, actor):
        """Phase 044 read-offs for body_state: pregnant (0 or 1), term_fraction and nursed (0 or 1). Empty when the
        births switch is off, so body_state's shape is unchanged then."""
        if not self._births_on():
            return {}
        attrs = self.eng.node(self._actors[actor])["attrs"]
        pregnant = float(attrs.get("pregnant", 0.0)) == 1.0
        return {"pregnant": int(pregnant),
                "term_fraction": round(self._term_fraction(attrs), 4) if pregnant else 0.0,
                "nursed": int(self._nursed(actor))}
