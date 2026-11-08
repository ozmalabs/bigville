"""Phase 046: detraining and ageing of the body, behind the detraining switch (DETRAIN.enabled in the pack; off by default).

The switch is a pack value, as DEPENDANTS.enabled is for Phase 045, so it does not appear in physical_subsystems and
the scenario defaults stay as they are. With it off, every method here returns at once and writes nothing, so the world
is unchanged. With it on:

- Each Effort (Phase 032) that a resident exerts records the calendar day on the resident's Body node: `str_effort_day`
  when the effort uses strength, `sta_effort_day` for every effort (every effort uses stamina). Nothing else is written.
- Once a day, from the dawn tick, for each living resident:
  * ageing: the base (str_base, sta_base) above BODY_AGE.peak_until is the resident's peak base times the age's
    decline (domains/detraining.aged_base). The peak base is stored once, on `str_base_peak` or `sta_base_peak`, the
    first day ageing applies. Below peak_until nothing is written, so Phase 045's growth (below the adult age) is not
    touched.
  * detraining: the trained part (str_train, sta_train) is held through DETRAIN's grace from the last effort of its
    kind, then falls by DETRAIN's rate each day, never below 0 (domains/detraining.detrained). The base is never touched.
    A resident with no effort, confined or collapsed included, detrains by the same rule. A resident never exerted
    has no record, so any trained part is treated as idle from the start.

The body's effective stats are read from the base and the trained part (world._effective_body_stat), so both changes
reach strength and stamina without further rules. Which work a resident chooses is the backend's; this module only
keeps the body's physical record.
"""
from __future__ import annotations

from domains.detraining import aged_base, detrained

# (kind, trained key, base key, peak-base key, effort-day key, the Effort flag that counts as this kind of effort)
_KINDS = (
    ("strength", "str_train", "str_base", "str_base_peak", "str_effort_day", "uses_strength"),
    ("stamina", "sta_train", "sta_base", "sta_base_peak", "sta_effort_day", "uses_stamina"),
)


class DetrainingMixin:
    """Methods mixed into BigvilleWorld. Names are prefixed to keep them clear of the world's own."""

    def _detraining_on(self):
        return bool(self.E.DETRAIN.get("enabled", False))

    def _calendar_day(self):
        return int(float(self.eng.node(self._town)["attrs"].get("day", 0.0)))

    def _detraining_note_effort(self, actor, body, event):
        """Record the day of an effort on the body, for each stat the effort uses. Called once per effort, when its
        stamina cost is paid (the exerted edge), whether or not the training switch is on."""
        if not self._detraining_on() or body is None or not self.eng.has_node(body):
            return
        effort = self.eng.node(event)["attrs"]
        day = float(self._calendar_day())
        for _kind, _train, _base, _peak, day_key, uses in _KINDS:
            if float(effort.get(uses, 0.0)) == 1.0:
                self.eng.set_attr(body, day_key, day)

    def _detraining_day(self):
        """The daily step (called from the dawn tick, after the dependants' step). A no-op with the switch off."""
        if not self._detraining_on():
            return
        today = self._calendar_day()
        for name, node in self._actors.items():
            attrs = self.eng.node(node)["attrs"]
            if float(attrs.get("alive", 1.0)) != 1.0:
                continue
            body = self._bodies.get(name)
            if body is None or not self.eng.has_node(body):
                continue
            self._age_body(body, float(attrs.get("age", 0.0)))
            for kind, _train, _base, _peak, _day, _uses in _KINDS:
                self._detrain_body(body, kind, today)

    def _age_body(self, body, age):
        """The base of a resident past BODY_AGE.peak_until declines from the peak base. Younger residents are not
        written at all, so growth (Phase 045) and the founders' drawn bases stay as they are."""
        table = self.E.BODY_AGE
        peak_until = float(table["peak_until"])
        if float(age) <= peak_until:
            return
        for kind, _train, base_key, peak_key, _day, _uses in _KINDS:
            if peak_key not in self.eng.node(body)["attrs"]:
                self.eng.set_attr(body, peak_key, float(self.eng.node(body)["attrs"].get(base_key, 1.0)))
            spec = table[kind]
            value = aged_base(float(self.eng.node(body)["attrs"][peak_key]), age, peak_until,
                              float(spec["decline_per_year"]), float(spec["floor"]))
            if float(self.eng.node(body)["attrs"].get(base_key, 1.0)) != value:
                self.eng.set_attr(body, base_key, value)
                self.eng.set_attr(body, "stats_dirty", 1.0)

    def _detrain_body(self, body, kind, today):
        """Let the trained part of one stat fall, when the resident has been idle past the grace."""
        spec = self.E.DETRAIN[kind]
        _kind, train_key, _base, _peak, day_key, _uses = next(row for row in _KINDS if row[0] == kind)
        attrs = self.eng.node(body)["attrs"]
        trained = float(attrs.get(train_key, 0.0))
        if trained <= 0.0:
            return
        last = attrs.get(day_key)
        idle = float("inf") if last is None else float(today) - float(last)
        value = detrained(trained, idle, float(spec["grace_days"]), float(spec["rate"]))
        if value != trained:
            self.eng.set_attr(body, train_key, value)
            self.eng.set_attr(body, "stats_dirty", 1.0)
