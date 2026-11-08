"""Phase 045: infants, dependants and coming of age. The world's physical side, behind the dependants switch.

Off by default (DEPENDANTS.enabled in the pack). With it off, every method here returns its neutral value
(no refusal, a work factor of 1, no options, no read-offs, no growth or care) and the world's behaviour is
unchanged. With it on:

- an infant is refused every major action with the reason `infant` (_dependant_refusal, read by the
  major-action gate).
- a dependant (a life stage in DEPENDANTS.stages) acts at its life stage's work_fraction: strength and
  stamina read the factor (_dependant_work_factor, applied where the body's stats are read).
- strength and stamina base values grow from a fraction of the adult default to the whole at the adult
  age (growth_fraction), each dawn for every resident still under the adult age.
- a dependant's care need is met on a day when a household member, awake and on the same cell, stands
  with it (_caregivers_of). An unattended dependant has neglect days counted, and past the stage's span
  takes neglect harm through harm() (cause neglect).
- a caregiver standing with a hungry dependant can feed it from its own food (feed_dependant, the care
  action with care_kind feed). A caregiver away from an unattended dependant is offered the walk to it.
- a dependant that reaches the adult age gets the adult flag and one `coming_of_age` event (only residents
  who were dependants, so founders are not announced).

Everything is physical. Which caregiver feeds or walks, and how a grown child's priors are shaped, belong
to the resident's backend (bigville/backends/dependants_policy.py for the simple backend).
"""
from __future__ import annotations

from domains.dependants import growth_fraction, neglect_harm


class DependantsMixin:
    """Methods mixed into BigvilleWorld. Names are prefixed to keep them clear of the world's own."""

    def _dependants_on(self):
        return bool(self.E.DEPENDANTS.get("enabled"))

    def _dependant_stages(self):
        return tuple(self.E.DEPENDANTS["stages"])

    def _life_stage(self, actor):
        return str(self.eng.node(self._actors[actor])["attrs"].get("life_stage", "adult"))

    def _is_dependant(self, actor):
        return self._life_stage(actor) in self._dependant_stages()

    def _age_stage(self, age):
        """The life stage an age gives. With the dependants switch off: the whole-year bands as HEAD reads them, so
        an age in a gap between two bands (3.5, say) is in none and reads as elder. With it on: each band runs from
        its age_min up to the next band's age_min, so the gap (3 to 4) belongs to the band below (infant)."""
        stages = self.E.LIFE_STAGES
        if not self._dependants_on():
            return next((stage for stage, spec in stages.items()
                         if float(spec["age_min"]) <= age <= float(spec["age_max"])), "elder")
        ordered = sorted(stages.items(), key=lambda item: float(item[1]["age_min"]))
        chosen = ordered[0][0]
        for stage, spec in ordered:
            if float(age) >= float(spec["age_min"]):
                chosen = stage
        return chosen

    def _dependant_refusal(self, actor):
        """The refusal reason for a major action by this resident, or None. An infant is refused them all."""
        if not self._dependants_on() or not isinstance(actor, str) or actor not in self._actors:
            return None
        return "infant" if self._life_stage(actor) == "infant" else None

    def _dependant_work_factor(self, actor):
        """The share of an adult's force and stamina a dependant brings: its life stage's work_fraction."""
        if not self._dependants_on() or actor not in self._actors:
            return 1.0
        stage = self._life_stage(actor)
        if stage not in self._dependant_stages():
            return 1.0
        return float(self.E.LIFE_STAGES[stage]["work_fraction"])

    def _growth_base(self, age, key):
        """A body base (str_base or sta_base) at `age`: the adult default times the growth fraction."""
        growth = self.E.DEPENDANTS["growth"]
        adult_age = float(self.E.LIFE_STAGES["adult"]["age_min"])
        start = float(growth["strength_start"] if key == "str_base" else growth["stamina_start"])
        return float(self.E.ACTOR_DEFAULTS["body"][key]) * growth_fraction(age, start, adult_age,
                                                                           float(growth["exponent"]))

    def _within_reach(self, a, b):
        """Whether `b` stands close enough to care for `a`: the same cell (reach_cells is 0)."""
        pa, pb = self.actor_position(a), self.actor_position(b)
        if pa is None or pb is None:
            return False
        if pa == pb:
            return True
        distance = self.distance(pa, pb)
        return distance is not None and distance <= int(self.E.DEPENDANTS["reach_cells"])

    def _caregivers_of(self, name):
        """The household members who are alive, awake, not dependants, and in reach of `name`."""
        household = str(self.eng.node(self._actors[name])["attrs"].get("household") or "")
        if not household:
            return []
        out = []
        for other in self._actors:
            if other == name or not self.is_alive(other):
                continue
            if str(self.eng.node(self._actors[other])["attrs"].get("household") or "") != household:
                continue
            if self._is_dependant(other) or self._sleep_code(other) is not None:
                continue
            if self._within_reach(name, other):
                out.append(other)
        return out

    def _dependants_day(self):
        """Once a day, from the dawn tick: growth, care and neglect for each dependant, and coming of age."""
        if not self._dependants_on():
            return
        adult_age = float(self.E.LIFE_STAGES["adult"]["age_min"])
        for name, node in self._actors.items():
            a = self.eng.node(node)["attrs"]
            if float(a.get("alive", 1.0)) != 1.0:
                continue
            age = float(a.get("age", 0.0))
            if age < adult_age:
                body = self._bodies[name]
                self.eng.set_attr(body, "str_base", self._growth_base(age, "str_base"))
                self.eng.set_attr(body, "sta_base", self._growth_base(age, "sta_base"))
            if self._is_dependant(name):
                self._dependant_day(name)
            if (float(a.get("dependant_days", 0.0)) > 0.0 and age >= adult_age
                    and float(a.get("adult", 0.0)) != 1.0):
                self.eng.set_attr(node, "adult", 1.0)
                self.create_event("coming_of_age", subject=name, detail=f"{name} came of age.")

    def _dependant_day(self, name):
        node = self._actors[name]
        a = self.eng.node(node)["attrs"]
        stage = self._life_stage(name)
        self.eng.set_attr(node, "dependant_days", float(a.get("dependant_days", 0.0)) + 1.0)
        if self._caregivers_of(name):
            self.eng.set_attr(node, "care_days", float(a.get("care_days", 0.0)) + 1.0)
            self.eng.set_attr(node, "neglect_days", 0.0)
            return
        days = float(a.get("neglect_days", 0.0)) + 1.0
        self.eng.set_attr(node, "neglect_days", days)
        harm = neglect_harm(float(self.E.LIFE_STAGES[stage]["care"]), days,
                            float(self.E.DEPENDANTS["neglect_after_days"][stage]),
                            float(self.E.DEPENDANTS["neglect_harm"]))
        if harm > 0.0:
            self.harm(name, harm, "neglect")

    def _held_food_kind(self, actor):
        """The food kind the resident holds (unprepared food only, so no serving equipment is needed), or None."""
        kinds = sorted(kind for kind, spec in self._item_specs.items()
                       if spec.get("food") and not spec.get("prepared") and self.inventory_qty(actor, kind) >= 1.0)
        return kinds[0] if kinds else None

    def _dependant_options(self, actor):
        """The dependant acts the resident may take now, published as affordances. Feeding is offered to a
        caregiver on the dependant's cell, holding food, when the dependant is hungry. A walk is offered to
        a dependant that no one attends. Empty with the switch off."""
        if not self._dependants_on() or actor not in self._actors or not self.is_alive(actor):
            return []
        if self._sleep_code(actor) is not None or self._is_dependant(actor):
            return []
        household = str(self.eng.node(self._actors[actor])["attrs"].get("household") or "")
        here = self.actor_position(actor)
        if not household or here is None:
            return []
        food = self._held_food_kind(actor)
        options = []
        for name in self._actors:
            if name == actor or not self.is_alive(name) or not self._is_dependant(name):
                continue
            attrs = self.eng.node(self._actors[name])["attrs"]
            if str(attrs.get("household") or "") != household:
                continue
            there = self.actor_position(name)
            if there is None:
                continue
            if there == here:
                hunger = float(attrs.get("hunger", 0.0))
                if food is not None and hunger > 0.0:
                    options.append({"action": "care", "kind": "", "trade": "", "recipe": "", "target": "",
                                    "patient": name, "care_kind": "feed", "dependant": name, "food": food,
                                    "hunger": round(hunger, 4), "score": 0.0})
            elif not self._caregivers_of(name) and self.distance(here, there) is not None:
                options.append({"action": "move", "kind": "", "trade": "", "recipe": "", "target": "",
                                "destination": there, "dependant": name, "score": 0.0})
        return options

    def feed_dependant(self, caregiver, dependant):
        """A caregiver on the dependant's cell gives it one unit of its own unprepared food. The food
        relieves the dependant's hunger by its meal value (eat's rule). Refused when the dependant is not
        hungry, the caregiver holds no food, or the caregiver is away."""
        if caregiver not in self._actors or dependant not in self._actors:
            return self._refuse("unknown_target")
        if not self._dependants_on():
            return self._refuse("unsupported")
        if not self.is_alive(caregiver) or not self.is_alive(dependant):
            return self._refuse("not_possible")
        if self._is_dependant(caregiver):
            return self._refuse("not_possible")
        if not self._is_dependant(dependant):
            return self._refuse("not_needed")
        if self._turn > 0 and self.actor_position(caregiver) != self.actor_position(dependant):
            return self._refuse("not_in_reach")
        hunger = float(self.eng.node(self._actors[dependant])["attrs"].get("hunger", 0.0))
        if hunger <= 0.0:
            return self._refuse("not_needed")
        kind = self._held_food_kind(caregiver)
        if kind is None:
            return self._refuse("not_held")
        stock = self._inventory_stock(caregiver, kind)
        freshness = self._pile_condition(stock)
        self.eng.set_attr(stock, "qty", self.inventory_qty(caregiver, kind) - 1.0)
        self._refresh_carry_state(caregiver)
        value = float(self.E.meal_value(kind, freshness))
        self.eng.set_attr(self._actors[dependant], "hunger", max(0.0, hunger - value))
        self.eng.add_edge_unchecked(self._actors[caregiver], "fed", self._actors[dependant])
        return True

    def _dependant_readoffs(self, actor):
        """Phase 045 read-offs for body_state: dependant (0 or 1) and care_received, the share of the days
        this resident was a dependant that a household caregiver was in reach. Empty with the switch off."""
        if not self._dependants_on():
            return {}
        attrs = self.eng.node(self._actors[actor])["attrs"]
        days = float(attrs.get("dependant_days", 0.0))
        care = float(attrs.get("care_days", 0.0))
        return {"dependant": int(self._is_dependant(actor)),
                "care_received": round(care / days, 4) if days > 0.0 else 0.0}
