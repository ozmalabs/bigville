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

from domains import determinism
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
            "attend": loaded["ATTEND"],
            "strike_aim": loaded["STRIKE_AIM"],
            "injury_effects": loaded["INJURY_EFFECTS"],
            "action_body_use": loaded["ACTION_BODY_USE"],
            "recipe_body_use": loaded["RECIPE_BODY_USE"],
            "tick_hours": float(loaded["TIME"]["minutes_per_tick"]) / 60.0,
        }
    return _TABLE_CACHE[key]


def action_row(tables, action):
    """Phase 070c: the ACTION_BODY_USE row of an action ({ANATOMY node: [capacities]}). An action with no row, and the
    default, use the 'default' row (the arm). Plain lookups; the table is never changed here."""
    rows = tables["action_body_use"]
    row = rows.get(str(action)) if action is not None else None
    return rows["default"] if row is None else row


def recipe_action(tables, recipe):
    """Phase 070c: the ACTION_BODY_USE key a recipe's work uses (RECIPE_BODY_USE, else 'work')."""
    return str(tables["recipe_body_use"].get(str(recipe), "work"))


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
                "previous": None, "habituation": {}, "ledger": {}, "sleep_debt": 0.0, "findings": [],
                "attending": None, "pressed": {}, "probe": None, "pending": None, "glance": None,
                "counts": {"attends": 0, "presses": 0, "depth_gained": 0, "remedied": 0, "glances": 0}}

    def clock(self):
        """(seed, turn): the seed the draws use and the turn they are keyed on.

        A body built from tables alone keeps the fixed body seed (the
        creation-time acuity seed).  A body attached to a world derives its
        *runtime* seed from the world seed, the purpose, the actor's canonical
        state and the turn.  Per-tick felt-signal jitter, and the sound form of
        each quality, are therefore state-derived rather than merely stable for
        a given body seed, and a restored or reordered run draws the same
        values.  The creation-time acuity is still drawn from the body seed in
        ``initial_state`` and never recomputed here.
        """
        turn = int(getattr(self.world, "_turn", 0)) if self.world is not None else 0
        if self.world is not None:
            return int(determinism.state_seed(
                self.world, "interoception", self.actor, turn)), turn
        return int(self.state["seed"]), turn

    def reads(self):
        raise NotImplementedError

    def located(self):
        """The located reads: {"injury": {locus: value}}, from the ledger (plain values, zero loci dropped). A locus
        that a press has just probed (Phase 071) reads higher by ATTEND.press_boost while the press lasts."""
        pressed = self.state.get("pressed") or {}
        boost = float(self.tables["attend"]["press_boost"]) if pressed else 0.0
        out = {}
        for locus, value in sorted(self.state["ledger"].items()):
            if float(value) > 0.0:
                extra = boost if int(pressed.get(locus, 0)) > 0 else 0.0
                out[locus] = round(float(value) + extra, 6)
        return {"injury": out}

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

    def focus(self):
        """Phase 071: while the resident attends, the focus the derivation uses (the attended source and the attention
        budget); None otherwise. Plain values from ATTEND."""
        attending = self.state.get("attending")
        if not attending:
            glance = self.state.get("glance")
            if not glance:
                return None
            # Phase 070b: a glance adds one step of acuity to one signal for this view. It keeps the attention the
            # resident has and caps no other signal.
            return {"source": str(glance["source"]), "acuity_bonus": float(self.tables["attend"]["glance_bonus"]),
                    "focus_attention": 0.0, "other_attention": 1.0, "keep_attention": True}
        rules = self.tables["attend"]
        return {"source": str(attending["source"]), "acuity_bonus": float(rules["acuity_bonus"]),
                "focus_attention": float(rules["focus_attention"]), "other_attention": float(rules["other_attention"])}

    def locus_for(self):
        """Phase 070b: {source name: locus} for sources that take a place other than their row's (a disease with a
        locus). Empty for a body with none."""
        return {}

    def _derive(self, use_focus=True):
        seed, turn = self.clock()
        return I.derive(self.tables, self.reads(), self.record(), seed, self.actor, turn,
                        previous=self.state.get("previous"), located=self.located(),
                        habituation=self.state.get("habituation"), focus=self.focus() if use_focus else None,
                        locus_for=self.locus_for())

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
        block["attending"] = self.focus()
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

    def sleep_need(self):
        """Hours of sleep a day this resident's life stage needs (BODY_RATES.sleep_need_hours). 'adult' with no world."""
        stage = "adult"
        if self.world is not None:
            stage = str(self.world.eng.node(self.world._actors[self.actor])["attrs"].get("life_stage", "adult"))
        return float(self.tables["rates"]["sleep_need_hours"].get(stage, self.tables["rates"]["sleep_need_hours"]["adult"]))

    def _sleep_step(self):
        """The chronic short-sleep store, in hours of missing sleep (BODY_RATES). Each awake tick adds tick_hours x
        need / 24 and each asleep tick takes off tick_hours x (24 - need) / 24, floored at 0. So sleeping exactly
        `need` hours a day holds it level, and a day with no sleep adds one night's need. Only the body's state moves."""
        need = self.sleep_need()
        hours = float(self.tables["tick_hours"])
        debt = float(self.state.get("sleep_debt", 0.0))
        if self.attention() == "asleep":
            debt -= hours * (24.0 - need) / 24.0
        else:
            debt += hours * need / 24.0
        self.state["sleep_debt"] = round(max(0.0, debt), 6)

    def start_glance(self, source):
        """Phase 070b: a glance at one felt signal. It takes no major action, no tick and no stamina (ATTEND
        glance_stamina_cost), and lasts until the next tick. Returns the probe the resident now has."""
        rules = self.tables["attend"]
        seed, turn = self.clock()
        self.state["glance"] = {"source": str(source)}
        counts = self.state["counts"]
        counts["glances"] = int(counts.get("glances", 0)) + 1
        row = next(row for row in self._derive()["sources"] if row["source"] == source)
        return {"turn": int(turn), "action": "glance", "sound": row["sound"], "where": row["where"],
                "stamina_cost": float(rules["glance_stamina_cost"])}

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
        the located ledger falls at its time rate. No physical state of the world changes. A glance lasts until the
        next tick (Phase 070b)."""
        self.state["glance"] = None
        self._habituation_step()
        self._sleep_step()
        self._attend_tick()
        rate = float(self.tables["rates"]["located_heal_per_tick"])
        ledger = self.state["ledger"]
        for locus in list(ledger):
            ledger[locus] = round(float(ledger[locus]) - rate, 6)
            if ledger[locus] <= 0.0:
                del ledger[locus]

    # ------------------------------------------------------------------ Phase 071: attending and pressing
    def _signal_rows(self):
        """The felt signal rows in the order the view shows them (no focus: the list a handle names)."""
        return self._derive(use_focus=False)["signals"]

    def attend_options(self):
        """The attend rows the agent view offers: one per felt signal, handle signal:N (N from 1). None while the
        resident is asleep, collapsed or already attending (the world would refuse each one)."""
        if self.attention() == "asleep" or self.state.get("attending"):
            return []
        return [{"action": "attend", "target": f"signal:{index}", "where": str(row["where"])}
                for index, row in enumerate(self._signal_rows(), start=1)]

    def probe(self, handle):
        """Phase 071d: the sound and the place a felt signal (handle signal:N) has now, from the body's own rows, as
        {sound, place}; None when no such signal is felt. Reads only; no state changes."""
        source = self.signal_named(handle)
        if source is None:
            return None
        for row in self._derive()["sources"]:
            if row["source"] == source:
                return {"sound": row.get("sound") or None, "place": str(row.get("where", ""))}
        return None

    def signal_named(self, handle):
        """The source name of the felt signal a handle names (signal:N), or None when no such signal is felt."""
        text = str(handle)
        if not text.startswith("signal:") or not text[len("signal:"):].isdigit():
            return None
        index = int(text[len("signal:"):])
        rows = self._signal_rows()
        return rows[index - 1]["source"] if 1 <= index <= len(rows) else None

    def _depth_sum(self, derived, name):
        row = next(row for row in derived["sources"] if row["source"] == name)
        return int(row["quality_depth"]) + int(row["locus_depth"])

    def start_attend(self, source):
        """Phase 071: begin attending to one felt signal. Returns the probe (the sound and place it now has). The
        attention runs ATTEND.ticks world ticks; the depth it adds is counted for the report."""
        rules = self.tables["attend"]
        seed, turn = self.clock()
        plain = self._depth_sum(self._derive(use_focus=False), source)
        self.state["attending"] = {"source": str(source), "ticks": int(rules["ticks"])}
        focused = self._derive(use_focus=True)
        gained = self._depth_sum(focused, source) - plain
        row = next(row for row in focused["sources"] if row["source"] == source)
        counts = self.state["counts"]
        counts["attends"] = int(counts.get("attends", 0)) + 1
        counts["depth_gained"] = int(counts.get("depth_gained", 0)) + int(gained)
        self.state["pending"] = {"source": str(source), "until": int(turn) + int(rules["remedy_window"])}
        probe = {"turn": int(turn), "action": "attend", "sound": row["sound"], "where": row["where"]}
        self.state["probe"] = probe
        return probe

    def press(self, region):
        """Phase 071: probe a region of this body. The reaction is the press_sounds row for the summed raw intensity of
        the true sources whose locus lies under the region. A located injury under the region is pressed (it reads
        higher for ATTEND.press_ticks ticks). Returns the probe: {turn, action, sound (None for silence), where}."""
        anatomy = _anatomy_rows(self.tables)
        seed, turn = self.clock()
        block = self.referee()
        total = sum(float(row["raw_intensity"]) for row in block["sources"]
                    if I.within(anatomy, row["locus_true"], region))
        rules = self.tables["attend"]
        pressed = dict(self.state.get("pressed") or {})
        for locus in self.state["ledger"]:
            if I.within(anatomy, locus, region):
                pressed[locus] = int(rules["press_ticks"])
        self.state["pressed"] = pressed
        counts = self.state["counts"]
        counts["presses"] = int(counts.get("presses", 0)) + 1
        probe = {"turn": int(turn), "action": "press", "sound": I.press_sound(self.tables, total),
                 "where": str(anatomy[region]["label"])}
        self.state["probe"] = probe
        return probe

    def note_action(self, action, applied):
        """Phase 071 (referee measure): a major action that succeeds within remedy_window turns of an attend, and that
        the ATTEND.remedies table names for the attended source, counts once as acting on the true source."""
        pending = self.state.get("pending")
        if not pending:
            return
        _seed, turn = self.clock()
        if int(turn) > int(pending["until"]):
            self.state["pending"] = None
            return
        base = str(pending["source"]).split("@", 1)[0]          # a located source 'injury_sharp@arm' is injury_sharp
        if applied and action in self.tables["attend"]["remedies"].get(base, []):
            self.state["counts"]["remedied"] = int(self.state["counts"].get("remedied", 0)) + 1
            self.state["pending"] = None

    def _attend_tick(self):
        """The attention and the press timers run down one world tick. Falling asleep ends an attention."""
        attending = self.state.get("attending")
        if attending and self.attention() == "asleep":
            self.state["attending"] = None
        elif attending:
            left = int(attending["ticks"]) - 1
            self.state["attending"] = None if left <= 0 else {"source": attending["source"], "ticks": left}
        pressed = {locus: int(ticks) - 1 for locus, ticks in dict(self.state.get("pressed") or {}).items()}
        self.state["pressed"] = {locus: ticks for locus, ticks in pressed.items() if ticks > 0}

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
                "sleep_debt": min(1.0, float(self.state.get("sleep_debt", 0.0))
                                  / (float(rates["sleep_debt_read_nights"]) * self.sleep_need()))}

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

    def locus_for(self):
        """Phase 070b: a disease with a locus (DISEASE[disease].locus) feels from that place. A disease with none, or no
        disease, keeps the illness source's own row."""
        w, a = self.world, self.actor
        disease = str(w.eng.node(w._actors[a])["attrs"].get("disease", "") or "")
        row = w.E.DISEASE.get(disease) if disease else None
        locus = row.get("locus") if row else None
        return {"illness": str(locus)} if locus else {}

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
        """Phase 070: where a harm with no named locus lands, from HARM_LOCUS by cause. A stateless state-derived
        draw keyed on the resident's state, the cause and the tick (never the world's random stream). None for a
        whole-body cause (an empty row)."""
        weights = pack_tables(self.data_pack)["harm_locus"].get(str(cause)) or {}
        items = sorted((str(node), float(weight)) for node, weight in weights.items() if float(weight) > 0.0)
        if not items:
            return None
        total = sum(weight for _node, weight in items)
        point = determinism.state_uniform(
            self, "harm_locus", actor, str(cause), int(getattr(self, "_turn", 0))) * total
        running = 0.0
        for node, weight in items:
            running += weight
            if point < running:
                return node
        return items[-1][0]

    def _body_locus_ok(self, locus):
        """Whether a locus name is an ANATOMY node of this pack."""
        return str(locus) in _anatomy_rows(pack_tables(self.data_pack))

    def _disease_locus(self, actor):
        """Phase 070b: the locus a resident's disease harm lands on (DISEASE[disease].locus), or None for a whole-body
        disease (or no disease). None sends the harm to HARM_LOCUS as before."""
        if actor not in self._actors:
            return None
        disease = str(self.eng.node(self._actors[actor])["attrs"].get("disease", "") or "")
        row = self.E.DISEASE.get(disease) if disease else None
        locus = row.get("locus") if row else None
        return str(locus) if locus else None

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

    # ------------------------------------------------------------------ Phase 071: the world's hooks for attending
    def _attending_refusal(self, actor, action):
        """'attending' while the resident attends and the action is not attend or press (the attention holds the
        resident's one major action for its ticks). None otherwise. Reads the plain state only."""
        if action in ("attend", "press"):
            return None
        state = getattr(self, "embodiment", {}).get(actor)
        return "attending" if state and state.get("attending") else None

    def _body_attend(self, actor, handle):
        """Phase 071: the attend enactment (called inside the claimed slot). A refusal returns False with its reason.
        The stamina cost is the world's own: it lowers the body node's stamina_reserve by ATTEND.stamina_cost."""
        body = self.body_of(actor)
        if body is None:
            return self._refuse("wrong_target")
        if not isinstance(handle, str):
            return self._refuse("malformed")
        code = self._sleep_code(actor)
        if code is not None:
            return self._refuse(code)
        if body.state.get("attending"):
            return self._refuse("attending")
        source = body.signal_named(handle)
        if source is None:
            return self._refuse("unknown_target")
        node = self._bodies[actor]
        reserve = float(self.eng.node(node)["attrs"].get("stamina_reserve", 1.0))
        self.eng.set_attr(node, "stamina_reserve", max(0.0, reserve - float(body.tables["attend"]["stamina_cost"])))
        body.start_attend(source)
        self.embodiment[actor] = body.dump()
        return True

    def _body_press(self, actor, region):
        """Phase 071: the press enactment (called inside the claimed slot). A region that is not an ANATOMY node is
        unknown_target; the reaction is the body's own probe."""
        body = self.body_of(actor)
        if body is None:
            return self._refuse("wrong_target")
        if not isinstance(region, str):
            return self._refuse("malformed")
        code = self._sleep_code(actor)
        if code is not None:
            return self._refuse(code)
        if not self._body_locus_ok(region):
            return self._refuse("unknown_target")
        body.press(region)
        self.embodiment[actor] = body.dump()
        return True

    def _body_note_outcome(self, actor, action, applied):
        """Phase 071: called once per published major-action outcome. Only the referee count changes."""
        state = getattr(self, "embodiment", {}).get(actor)
        if state and state.get("pending"):
            body = self.body_of(actor)
            body.note_action(str(action), bool(applied))
            self.embodiment[actor] = body.dump()

    # ------------------------------------------------------------------ Phase 070b: glances, injury and aimed blows
    def _body_glance(self, actor, handle):
        """Phase 070b: the free glance at one felt signal (called from free_action). Refused (False) asleep, for a
        handle that names no felt signal, or for a non-string handle. It uses no major action and no stamina."""
        body = self.body_of(actor)
        if body is None or not isinstance(handle, str) or self._sleep_code(actor) is not None:
            return False
        source = body.signal_named(handle)
        if source is None:
            return False
        body.start_glance(source)
        self.embodiment[actor] = body.dump()
        return True

    def _body_capacity_factor(self, actor, capacity, action=None):
        """Phase 070b/070c: the share of a capacity ('speed', 'strength' or 'stamina') a located injury leaves: the
        INJURY_EFFECTS weights times the ledger at each locus, floor at INJURY_EFFECTS.floor. Exactly 1.0 with an empty
        ledger or no weight on this capacity. Reads the plain ledger; the press boost is not counted.

        Phase 070c: with an `action` (an ACTION_BODY_USE key), only the regions that action uses for this capacity
        count. With no action, every region counts (the whole-body factor, the general read). An action with no row
        uses the 'default' row (the arm)."""
        state = getattr(self, "embodiment", {}).get(actor)
        if not state or not state.get("ledger"):
            return 1.0
        tables = pack_tables(self.data_pack)
        spec = tables["injury_effects"]
        row = None if action is None else action_row(tables, action)
        total = 0.0
        for locus, value in state["ledger"].items():
            if row is not None and capacity not in (row.get(locus) or []):
                continue
            weight = (spec["weights"].get(locus) or {}).get(capacity)
            if weight:
                total += float(weight) * float(value)
        if total <= 0.0:
            return 1.0
        return round(max(float(spec["floor"]), 1.0 - total), 6)

    def _speed_of(self, actor, action=None):
        """Phase 070c: the exhaustion speed (unrounded) times the located speed factor for an action (1.0 with no
        action, which is the whole-body read; the leg factor for walking and contests)."""
        return float(self._exhaustion_band(actor)["speed"]) * self._body_capacity_factor(actor, "speed", action)

    def _recipe_body_use(self, recipe):
        """Phase 070c: the ACTION_BODY_USE key of a recipe's work (RECIPE_BODY_USE, else 'work')."""
        return recipe_action(pack_tables(self.data_pack), recipe)

    def _strike_locus(self, pending, choice):
        """Phase 070b: where an aimed strike lands. None for an unaimed blow (the table draws, as before). For an aimed
        one the chance is STRIKE_AIM base + skill_weight x the striker's skill, times brace_factor when the target
        resists or braces; the draw is stateless and state-derived (the striker and target state, the turn and the
        region). A miss gives None, so the table draws."""
        region = pending.get("region")
        if region is None:
            return None
        aim = pack_tables(self.data_pack)["strike_aim"]
        skill = float(pending["attacker_side"]["skill"])
        chance = max(0.0, min(1.0, float(aim["base"]) + float(aim["skill_weight"]) * skill))
        if choice in ("resist", "brace"):
            chance *= float(aim["brace_factor"])
        turn = int(getattr(self, "_turn", 0))
        point = determinism.state_uniform(
            self, "strike_aim", pending["attacker"], pending["target"], turn, str(region),
            actors=(pending["attacker"], pending["target"]))
        return str(region) if point < chance else None

    def attention_report(self):
        """Phase 071 (game_report only): attends, presses, the depth gained by attending (summed over residents), the
        attends that a remedy for the attended source followed (acted on the true source, a referee measure), and how
        many residents are attending now. Read-only."""
        totals = {"attends": 0, "presses": 0, "glances": 0, "depth_gained": 0, "acted_on_true_source": 0,
                  "attending_now": 0}
        for actor in self._actors:
            state = getattr(self, "embodiment", {}).get(actor)
            if not state:
                continue
            counts = state.get("counts") or {}
            totals["attends"] += int(counts.get("attends", 0))
            totals["presses"] += int(counts.get("presses", 0))
            totals["glances"] += int(counts.get("glances", 0))
            totals["depth_gained"] += int(counts.get("depth_gained", 0))
            totals["acted_on_true_source"] += int(counts.get("remedied", 0))
            totals["attending_now"] += 1 if state.get("attending") else 0
        return totals
