"""body.py -- the body as a unit (Phases 069 and 070): what the world's physics and the resident's mind each get.

A body is one embodiment of one resident. It has two outputs, never one:

* capacities()   exact values for the world's physics (strength, stamina, speed, whether it lives).
* afferents()    what the mind may feel: a background feeling and the felt signals (domains/interoception.py).

It also has observable() (the marks and signs an observer may see), referee() (the full truth, for tests),
screen() (the silent conditions the referee state shows, for a healer's checkup) and dump()/load() (plain values,
for checkpoints).

Phase 070 adds the located ledger: `harm()` in the world lowers the one health scalar and then calls the body
with the locus the harm landed on (given, or drawn from HARM_LOCUS). The body keeps a per-locus ledger, which is
descriptive and never a second health. Healing lowers the ledger too (BODY_RATES.care_share), and the ledger
also falls with time (located_heal_per_tick). Each steady signal habituates, and a change is noticed at full
strength. The body keeps its own sleep debt, the chronic short-sleep store.

The first embodiment, `WorldBackedBody` ("human"), reads the world's existing accessors and moves no world state
except through the world's own calls. The authority rule: a quantity that already lives in a world node stays
authoritative there, and the body only reads it. State the body needs of its own (the acuity drawn for the
resident, the last turn's intensities for the trend, the ledger, habituation and sleep debt) lives in a plain dict
on the world, `world.embodiment[actor]`, so a checkpoint can carry it. The body objects are built from that dict on
demand (`BodyMixin.body_of`), so the world never holds an object of a class the persistence code does not know.

Adding an embodiment: write a subclass of `Body` with `reads()`, and register it in `EMBODIMENTS`.
"""
from __future__ import annotations

import copy

from domains import interoception as I
from domains.pack import load_pack

NO_BODY = "none"           # an ANIMALS row with no body object yet (animals keep their graph nodes only)
EVENT_KINDS = ("intake", "exertion", "exposure", "harm", "heal", "rest", "sleep")
_TABLE_CACHE = {}


def pack_tables(pack):
    """The interoception tables of a pack, as the derive() functions read them (cached per pack name)."""
    key = str(pack)
    if key not in _TABLE_CACHE:
        loaded = load_pack(pack)
        _TABLE_CACHE[key] = {
            "anatomy": loaded["ANATOMY"],
            "quality_tree": loaded["QUALITY_TREE"],
            "vocalisations": loaded["VOCALISATIONS"],
            "channels": loaded["CHANNELS"],
            "sources": loaded["SIGNAL_SOURCES"],
            "patterns": loaded["PATTERNS"],
            "feeling": loaded["FEELING"],
            "rules": loaded["INTEROCEPTION"],
            "harm_locus": loaded["HARM_LOCUS"],
            "rates": loaded["BODY_RATES"],
            "signs": loaded["OBSERVABLE_SIGNS"],
        }
    return _TABLE_CACHE[key]


def _anatomy_rows(tables):
    return {name: row for name, row in tables["anatomy"].items() if not str(name).startswith("_")}


class Body:
    """One embodiment. `state` is a plain dict: {"embodiment", "seed", "acuity", "previous", "habituation",
    "ledger", "sleep_debt", "findings"}. `world` is the BigvilleWorld it reads (None for a body built from tables
    alone, as a test does)."""

    kind = "base"

    def __init__(self, state, *, tables, world=None, actor=None):
        self.state = state
        self.tables = tables
        self.world = world
        self.actor = actor

    @classmethod
    def initial_state(cls, world, actor, life_stage):
        """The plain state a new resident starts with: the seed, the acuity (drawn once and kept), no trend yet, an
        empty ledger, no habituation, no sleep debt and no screening findings."""
        seed = int(getattr(world, "_burial_seed", 0))
        rules = pack_tables(world.data_pack)["rules"]
        return {"embodiment": cls.kind, "seed": seed,
                "acuity": round(I.acuity_of(rules["acuity"], seed, actor, life_stage), 6),
                "previous": None, "habituation": {}, "ledger": {}, "sleep_debt": 0.0, "findings": []}

    def clock(self):
        """(seed, turn): the seed the draws use and the turn they are keyed on."""
        turn = int(getattr(self.world, "_turn", 0)) if self.world is not None else 0
        return int(self.state["seed"]), turn

    def reads(self):
        raise NotImplementedError

    def located(self):
        """The located reads: {"injury": {locus: value}}, from the ledger (plain values, zero loci dropped)."""
        return {"injury": {locus: round(float(value), 6) for locus, value in sorted(self.state["ledger"].items())
                           if float(value) > 0.0}}

    def attention(self):
        return "idle"

    def record(self):
        """The interoceptor record for this turn: acuity (kept), attention (asleep, absorbed or idle) and
        impairment. The attention values and the impairment terms are pack data."""
        rules = self.tables["rules"]
        kind = self.attention()
        impairment = self.impairment()
        return {"acuity": float(self.state["acuity"]), "attention_kind": kind,
                "attention": float(rules["attention"][kind]), "impairment": impairment}

    def impairment(self):
        return 0.0

    def facts(self):
        """Plain facts a person has of their situation (asleep, collapsed). Empty for a body that has none."""
        return {}

    def capacities(self):
        """Exact values for the physics: a dict of plain numbers. Empty for a body that has none."""
        return {}

    def _derive(self):
        seed, turn = self.clock()
        return I.derive(self.tables, self.reads(), self.record(), seed, self.actor, turn,
                        previous=self.state.get("previous"), located=self.located(),
                        habituation=self.state.get("habituation"))

    def afferents(self):
        """What the mind may feel: {feeling?, signals}. Only sounds and places; no cause."""
        return I.felt_body(self._derive())

    def referee(self):
        """The full truth: the reads, the located ledger, the record, each source's true quality and locus, the
        depths chosen, the raw and habituated intensities, and the capacities and facts."""
        record = self.record()
        derived = self._derive()
        block = I.referee_block(derived, record)
        block["reads"] = {key: round(float(value), 6) for key, value in sorted(self.reads().items())}
        block["located"] = self.located()
        block["habituation"] = dict(sorted((self.state.get("habituation") or {}).items()))
        block["capacities"] = self.capacities()
        block["facts"] = self.facts()
        return block

    def screen(self):
        """Phase 070: the silent conditions the referee state shows, for a healer's checkup. A silent condition is a
        source with a raw intensity above zero that the resident does not feel (below its awareness, or habituated
        away). The finding is kept in the body (plain values, checkpointed); the resident's own view is unchanged."""
        block = self.referee()
        silent = {row["source"]: row["raw_intensity"] for row in block["sources"]
                  if row["raw_intensity"] > 0.0 and not row["felt"]}
        seed, turn = self.clock()
        finding = {"turn": turn, "silent": dict(sorted(silent.items()))}
        self.state["findings"] = (list(self.state.get("findings") or []) + [finding])[-10:]
        return finding

    def observable(self, distance=None, light=1.0):
        """What an observer may see of this body. The base body shows nothing."""
        return []

    def apply(self, event):
        """A world event for the body (EVENT_KINDS). A harm with a locus adds to the located ledger; a heal lowers
        the ledger by its care_share. Other kinds record nothing here: the world's own state changes come from the
        world's rules. Validates the event so a new kind is noticed."""
        if not isinstance(event, dict) or event.get("kind") not in EVENT_KINDS:
            raise ValueError(f"body event must be a dict with kind in {EVENT_KINDS}, not {event!r}")
        kind = event["kind"]
        amount = max(0.0, float(event.get("amount", 0.0) or 0.0))
        if kind == "harm" and event.get("locus") is not None and amount > 0.0:
            locus = str(event["locus"])
            if locus not in _anatomy_rows(self.tables):
                raise ValueError(f"harm locus {locus!r} is not an ANATOMY node")
            ledger = self.state["ledger"]
            ledger[locus] = round(float(ledger.get(locus, 0.0)) + amount, 6)
        elif kind == "heal" and amount > 0.0:
            self._lower_ledger(amount * float(self.tables["rates"]["care_share"]))
        return None

    def _lower_ledger(self, share):
        """Take `share` off the located ledger, from the largest locus first (ties by name)."""
        ledger = self.state["ledger"]
        for locus in sorted(ledger, key=lambda name: (-float(ledger[name]), name)):
            if share <= 0.0:
                break
            taken = min(share, float(ledger[locus]))
            ledger[locus] = round(float(ledger[locus]) - taken, 6)
            share -= taken
        for locus in [name for name, value in ledger.items() if float(value) <= 0.0]:
            del ledger[locus]

    def _sleep_step(self):
        """The chronic short-sleep store: it grows on each awake tick and falls on each asleep tick (BODY_RATES).
        Only the body's own state changes."""
        rates = self.tables["rates"]
        debt = float(self.state.get("sleep_debt", 0.0))
        if self.attention() == "asleep":
            debt -= float(rates["sleep_debt_fall"])
        else:
            debt += float(rates["sleep_debt_rise"])
        self.state["sleep_debt"] = round(max(0.0, debt), 6)

    def _habituation_step(self):
        """Each steady signal's felt fraction falls toward 0 while its stimulus holds, and recovers when it stops.
        A change larger than trend_delta resets it, so a sudden change is noticed at full strength."""
        rates, rules = self.tables["rates"], self.tables["rules"]
        raw = I.intensities(self.tables, self.reads(), self.located())
        previous = self.state.get("previous")
        habit = dict(self.state.get("habituation") or {})
        new = {}
        for name, value in raw.items():
            level = float(habit.get(name, 0.0))
            last = None if previous is None else previous.get(name)
            if last is None or float(value) - float(last) > float(rules["trend_delta"]):
                level = 0.0                                   # new or rising: noticed at full strength
            elif value > 0.0 and abs(value - float(last)) <= float(rules["trend_delta"]):
                level += (1.0 - level) * float(rates["habituation_rate"])      # steady: habituates
            else:
                level *= 1.0 - float(rates["habituation_recover"])            # stopped or eased: recovers
            if level > 0.0:
                new[name] = round(level, 6)
        self.state["habituation"] = new
        self.state["previous"] = raw

    def tick(self):
        """Once per clock tick: the trend and habituation are kept against the last tick, the sleep debt moves, and
        the located ledger falls at its time rate. No physical state of the world changes."""
        self._habituation_step()
        self._sleep_step()
        rate = float(self.tables["rates"]["located_heal_per_tick"])
        ledger = self.state["ledger"]
        for locus in list(ledger):
            ledger[locus] = round(float(ledger[locus]) - rate, 6)
            if ledger[locus] <= 0.0:
                del ledger[locus]

    def dump(self):
        return copy.deepcopy(self.state)

    @classmethod
    def load(cls, state, **kwargs):
        """A body from a dump(). The state is copied, so the caller's dict is not changed by later ticks."""
        return cls(copy.deepcopy(state), **kwargs)


class WorldBackedBody(Body):
    """The human body. Every read is a world accessor or a world node's value; nothing here changes the world."""

    kind = "human"

    def __init__(self, state, *, world, actor):
        super().__init__(state, tables=pack_tables(world.data_pack), world=world, actor=actor)

    def _band(self):
        return self.world._exhaustion_band(self.actor)

    def reads(self):
        w, a = self.world, self.actor
        rates = self.tables["rates"]
        attrs = w.eng.node(w._actors[a])["attrs"]
        body_attrs = w.eng.node(w._bodies[a])["attrs"]
        stamina = float(w.effective_stamina(a))
        reserve = float(body_attrs.get("stamina_reserve", 1.0))
        exertion = max(0.0, (stamina - reserve) / stamina) if stamina > 0.0 else 0.0
        marks = w.E.MARKS
        wetness = w.mark_level(a, "wetness") if "wetness" in marks else 0.0
        days = float(body_attrs.get("illness_days", 0.0))
        incubation = min(1.0, (days + 1.0) / float(rates["incubation_days"]))
        hangover_ticks = float(body_attrs.get("hangover_ticks", 0.0))
        hangover = (min(1.0, hangover_ticks / float(w.E.INTOXICATION["hangover_ticks"]))
                    if w._hangover_on(a) else 0.0)
        return {"hunger": float(w.hunger(a)), "exertion": exertion,
                "exhaustion": float(self._band()["step"]) / 3.0,
                "chill": float(w.chill(a)), "wetness": float(wetness),
                "illness": incubation if attrs.get("disease") else 0.0,
                "intoxication": float(w.intoxication(a)),
                "harm": max(0.0, 1.0 - float(w.health(a))),
                "deficiency": min(1.0, max(0.0, float(body_attrs.get("deficiency", 0.0)))),
                "hangover": hangover,
                "withdrawal": float(w._withdrawal_share(a)),
                "sleep_debt": min(1.0, float(self.state.get("sleep_debt", 0.0)) / float(rates["sleep_debt_full"]))}

    def attention(self):
        if self.world.asleep(self.actor):
            return "asleep"
        if self.world.busy(self.actor):
            return "absorbed"
        return "idle"

    def impairment(self):
        reads = self.reads()
        return reads["intoxication"] + reads["exhaustion"] + reads["illness"]

    def facts(self):
        return {"asleep": bool(self.world.asleep(self.actor)), "collapsed": bool(self.world.collapsed(self.actor))}

    def capacities(self):
        w, a = self.world, self.actor
        return {"strength": round(float(w.effective_strength(a)), 4),
                "stamina": round(float(w.effective_stamina(a)), 4),
                "speed_factor": round(float(self._band()["speed"]), 4),
                "alive": 1.0 if w.is_alive(a) else 0.0}

    def observable(self, distance=None, light=1.0):
        """The Phase 063 marks, then the signs of the ledger and reads (OBSERVABLE_SIGNS) that the observer's
        distance and the light let through. A sign is a row {sign, label, level}."""
        rows = list(self.world.observable_marks(self.actor, distance, light))
        if distance is None:
            return rows
        reads, located = self.reads(), self.located()["injury"]
        signs = {name: row for name, row in self.tables["signs"].items() if not str(name).startswith("_")}
        for name, spec in sorted(signs.items()):
            if float(distance) > float(spec["see_range"]) or float(light) < float(spec["see_light"]):
                continue
            if spec["from"] == "injury":
                loci = [spec["locus"]] if spec["locus"] is not None else list(located)
                level = min(1.0, sum(float(located.get(locus, 0.0)) for locus in loci))
            else:
                level = float(reads.get(str(spec["from"]), 0.0))
            if level >= float(spec["min"]):
                rows.append({"sign": name, "label": str(spec["label"]), "level": round(level, 4)})
        return rows


# The embodiment key (ACTOR_DEFAULTS.embodiment, ANIMALS.embodiment) to its class.
EMBODIMENTS = {WorldBackedBody.kind: WorldBackedBody}


class BodyMixin:
    """The world's hooks for bodies. The world inherits this (worlds/bigville_world.py). Each method is small and
    changes no physical state."""

    def _body_init(self, actor, embodiment, life_stage):
        """Start a resident's body state (called when the resident is added)."""
        if not hasattr(self, "embodiment"):
            self.embodiment = {}
        cls = EMBODIMENTS.get(str(embodiment))
        if cls is None:
            raise ValueError(f"no embodiment {embodiment!r} for {actor!r}; registered: {sorted(EMBODIMENTS)}")
        state = cls.initial_state(self, actor, life_stage)
        state["embodiment"] = str(embodiment)
        self.embodiment[actor] = state

    def body_of(self, actor):
        """The body object of a resident, built from its plain state. None for a resident with no body."""
        state = getattr(self, "embodiment", {}).get(actor)
        if state is None:
            return None
        cls = EMBODIMENTS[state["embodiment"]]
        return cls(state, world=self, actor=actor)

    def _body_tick(self):
        """Once per world tick: each living resident's body keeps its trend, habituation, sleep debt and ledger."""
        for actor in self._actors:
            if self.is_alive(actor) and actor in getattr(self, "embodiment", {}):
                self.body_of(actor).tick()

    def _body_event(self, actor, event):
        """Route a world event to the resident's body (validated there)."""
        body = self.body_of(actor)
        if body is not None:
            body.apply(event)

    def _body_harm_locus(self, actor, cause):
        """Phase 070: where a harm with no named locus lands, from HARM_LOCUS by cause. A stateless draw keyed on the
        burial seed, the resident, the cause and the tick (never the world's random stream). None for a whole-body
        cause (an empty row)."""
        weights = pack_tables(self.data_pack)["harm_locus"].get(str(cause)) or {}
        return I.pick_locus(weights, int(getattr(self, "_burial_seed", 0)), actor, str(cause),
                            int(getattr(self, "_turn", 0)))

    def _body_locus_ok(self, locus):
        """Whether a locus name is an ANATOMY node of this pack."""
        return str(locus) in _anatomy_rows(pack_tables(self.data_pack))

    def _body_screen(self, actor):
        """Phase 070: a healer's checkup records the resident's silent conditions from the referee state."""
        body = self.body_of(actor)
        return None if body is None else body.screen()

    def screening_findings(self, actor):
        """The silent-condition findings a checkup has recorded for a resident (newest last)."""
        body = self.body_of(actor)
        return [] if body is None else list(body.state.get("findings") or [])

    def injuries_by_locus(self):
        """Phase 070: the located ledger summed over the living residents: {locus: total ledger value}, and the number
        of residents with any located injury. Read-only."""
        totals, count = {}, 0
        for actor in self._actors:
            body = self.body_of(actor)
            if body is None or not self.is_alive(actor):
                continue
            located = body.located()["injury"]
            if located:
                count += 1
            for locus, value in located.items():
                totals[locus] = round(totals.get(locus, 0.0) + float(value), 6)
        return {"by_locus": dict(sorted(totals.items())), "residents": count}
