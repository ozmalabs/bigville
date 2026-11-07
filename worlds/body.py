"""body.py -- the body as a unit (Phase 069): what the world's physics and the resident's mind each get.

A body is one embodiment of one resident. It has two outputs, never one:

* capacities()   exact values for the world's physics (strength, stamina, speed, whether it lives).
* afferents()    what the mind may feel: a background feeling and the felt signals (domains/interoception.py).

It also has observable() (the marks an observer may see, from Phase 063), referee() (the full truth, for tests),
and dump()/load() (plain values, for checkpoints).

The first embodiment, `WorldBackedBody` ("human"), reads the world's existing accessors and moves no state. The
authority rule: a quantity that already lives in a world node stays authoritative there, and the body only reads
it. State the body needs of its own (the acuity drawn for the resident, the last turn's intensities for the trend)
lives in a plain dict on the world, `world.embodiment[actor]`, so a checkpoint can carry it. The body objects are
built from that dict on demand (`BodyMixin.body_of`), so the world never holds an object of a class the
persistence code does not know.

Adding an embodiment: write a subclass of `Body` with `tables()` and `reads()`, and register it in `EMBODIMENTS`.
The world, the agent view and the leak test call only the methods above, so nothing else changes.
"""
from __future__ import annotations

import copy

from domains import interoception as I
from domains.pack import load_pack

NO_BODY = "none"           # an ANIMALS row with no body object yet (animals keep their graph nodes only)
EVENT_KINDS = ("intake", "exertion", "exposure", "harm", "rest", "sleep")
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
        }
    return _TABLE_CACHE[key]


class Body:
    """One embodiment. `state` is a plain dict: {"embodiment", "seed", "acuity", "previous"}. `world` is the
    BigvilleWorld it reads (None for a body built from tables alone, as a test does)."""

    kind = "base"

    def __init__(self, state, *, tables, world=None, actor=None):
        self.state = state
        self.tables = tables
        self.world = world
        self.actor = actor

    @classmethod
    def initial_state(cls, world, actor, life_stage):
        """The plain state a new resident starts with: the seed, the acuity (drawn once and kept) and no trend yet."""
        seed = int(getattr(world, "_burial_seed", 0))
        rules = pack_tables(world.data_pack)["rules"]
        return {"embodiment": cls.kind, "seed": seed,
                "acuity": round(I.acuity_of(rules["acuity"], seed, actor, life_stage), 6),
                "previous": None}

    def clock(self):
        """(seed, turn): the seed the draws use and the turn they are keyed on."""
        turn = int(getattr(self.world, "_turn", 0)) if self.world is not None else 0
        return int(self.state["seed"]), turn

    def reads(self):
        raise NotImplementedError

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

    def afferents(self):
        """What the mind may feel: {feeling?, signals}. Only sounds and places; no cause."""
        seed, turn = self.clock()
        derived = I.derive(self.tables, self.reads(), self.record(), seed, self.actor, turn,
                           previous=self.state.get("previous"))
        return I.felt_body(derived)

    def referee(self):
        """The full truth: the reads, the record, each source's true quality and locus and the depths chosen."""
        seed, turn = self.clock()
        record = self.record()
        derived = I.derive(self.tables, self.reads(), record, seed, self.actor, turn,
                           previous=self.state.get("previous"))
        block = I.referee_block(derived, record)
        block["reads"] = {key: round(float(value), 6) for key, value in sorted(self.reads().items())}
        block["capacities"] = self.capacities()
        block["facts"] = self.facts()
        return block

    def observable(self, distance=None, light=1.0):
        """What an observer may see of this body. The base body shows nothing."""
        return []

    def apply(self, event):
        """A world event for the body (EVENT_KINDS). The world's own state changes come from the world's rules;
        this records nothing, and it validates the event so a new kind is noticed."""
        if not isinstance(event, dict) or event.get("kind") not in EVENT_KINDS:
            raise ValueError(f"body event must be a dict with kind in {EVENT_KINDS}, not {event!r}")
        return None

    def tick(self):
        """Keep the last turn's intensities, for the trend. Changes no physical state."""
        self.state["previous"] = I.intensities(self.tables, self.reads())

    def dump(self):
        return copy.deepcopy(self.state)

    @classmethod
    def load(cls, state, **kwargs):
        """A body from a dump(). The state is copied, so the caller's dict is not changed by later ticks."""
        return cls(copy.deepcopy(state), **kwargs)


class WorldBackedBody(Body):
    """The human body. Every read is a world accessor; nothing here changes the world."""

    kind = "human"

    def __init__(self, state, *, world, actor):
        super().__init__(state, tables=pack_tables(world.data_pack), world=world, actor=actor)

    def _band(self):
        return self.world._exhaustion_band(self.actor)

    def reads(self):
        w, a = self.world, self.actor
        attrs = w.eng.node(w._actors[a])["attrs"]
        stamina = float(w.effective_stamina(a))
        reserve = float(w.eng.node(w._bodies[a])["attrs"].get("stamina_reserve", 1.0))
        exertion = max(0.0, (stamina - reserve) / stamina) if stamina > 0.0 else 0.0
        marks = w.E.MARKS
        wetness = w.mark_level(a, "wetness") if "wetness" in marks else 0.0
        return {"hunger": float(w.hunger(a)), "exertion": exertion,
                "exhaustion": float(self._band()["step"]) / 3.0,
                "chill": float(w.chill(a)), "wetness": float(wetness),
                "illness": 1.0 if attrs.get("disease") else 0.0,
                "intoxication": float(w.intoxication(a)),
                "harm": max(0.0, 1.0 - float(w.health(a)))}

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
        return self.world.observable_marks(self.actor, distance, light)


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
        """Once per world tick: each living resident's body keeps its last intensities for the trend."""
        for actor in self._actors:
            if self.is_alive(actor) and actor in getattr(self, "embodiment", {}):
                self.body_of(actor).tick()

    def _body_event(self, actor, event):
        """Route a world event to the resident's body (validated there)."""
        body = self.body_of(actor)
        if body is not None:
            body.apply(event)
