"""Dependency-free emergent speech adapter for Bigville."""
from __future__ import annotations

from bigville.runtime import BigvilleGraph
from worlds.bigville_bond_world import BigvilleBondWorld

SPEECH_MENU = [
    dict(name="stay_silent", kind_code=0.0), dict(name="greeting", kind_code=1.0),
    dict(name="smalltalk", kind_code=2.0), dict(name="barb", kind_code=3.0),
    dict(name="hedged", kind_code=4.0), dict(name="share", kind_code=5.0),
    dict(name="answer", kind_code=6.0),
]
_OPT_KEYS = ("kind_code", "is_silence", "talk_aff", "base_value", "warm_aff",
             "hostile_aff", "hedge_aff", "confide_aff", "greet_answer_aff",
             "q_answer_aff", "goal_aff", "face_cost")
KIND_LABEL = {0: "stay_silent", 1: "greeting", 2: "smalltalk", 3: "barb",
              4: "hedged", 5: "share", 6: "answer"}
ENCOUNTER_DEFAULTS = dict(occasion=1.0, obligation=0.0, fpp_is_greeting=0.0,
    fpp_is_question=0.0, share_salience=0.0, goal_pressure=0.0,
    speaker_arousal=0.0, stranger=0.0, face_weight=0.3,
    loquacity_threshold=1.0, decide_armed=0.0, chosen_speech_code=-1.0,
    absence_minted=0.0)


class BigvilleSpeechWorld:
    def __init__(self, schedule=False):
        self.schedule = bool(schedule)
        self.bw = BigvilleBondWorld()
        self.s = self.bw.s
        self.inner = self.s
        self.options, self.encs, self.utts = {}, {}, {}
        self._mint_menu()

    def _mint_menu(self):
        for option in SPEECH_MENU:
            attrs = {key: 0.0 for key in _OPT_KEYS}
            attrs.update(option)
            self.options[option["name"]] = self.s.add_node("SpeechOption", attrs)

    def add_agent(self, name, **attrs):
        return self.bw.add_agent(name, **attrs)

    def hold_bond(self, speaker, target, prior="chosen", **slots):
        for name in (speaker, target):
            if name not in self.bw.agents:
                self.add_agent(name)
        bond = self.bw.elaborate(speaker, target, prior)
        for key, value in slots.items():
            self.s.set_attr(bond, key, float(value))
        return bond

    def earn_kindness(self, speaker, target, magnitude=1.5, times=1):
        for _ in range(times):
            self.bw.cohabit(speaker, target, 6.0)
            self.bw.experience_event(speaker, target, "care", 1.0, magnitude)
            self.bw.tick()

    def encounter(self, speaker, target, **overrides):
        attrs = dict(ENCOUNTER_DEFAULTS)
        attrs.update(overrides)
        if self.schedule:
            attrs["loquacity_threshold"] = -1.0
        enc = self.s.add_node("Encounter", attrs)
        self.encs[(speaker, target)] = enc
        return enc

    def trade(self, buyer, shopkeeper, **overrides):
        values = {"goal_pressure": 1.0, "stranger": 0.0}
        values.update(overrides)
        return self.encounter(buyer, shopkeeper, **values)

    def decide(self, speaker, target):
        enc = self.encs[(speaker, target)]
        attrs = self.s.node(enc)["attrs"]
        bond = self.s.node(self.bw.bonds[(speaker, target)])["attrs"]
        if self.schedule:
            kind = "smalltalk"
        elif attrs.get("obligation") and attrs.get("fpp_is_question"):
            kind = "answer"
        elif attrs.get("obligation") and attrs.get("fpp_is_greeting"):
            kind = "greeting" if attrs.get("loquacity_threshold", 1.0) <= 5.0 else "stay_silent"
        elif attrs.get("stranger"):
            kind = "stay_silent"
        elif float(bond.get("affect_resentment", 0.0)) >= 2.0:
            kind = "barb"
        elif float(attrs.get("share_salience", 0.0)) * float(bond.get("tie_strength", 0.0)) >= 2.0:
            kind = "share"
        elif attrs.get("goal_pressure", 0.0):
            kind = "smalltalk"
        elif float(bond.get("affect_affection", 0.0)) >= 1.0:
            kind = "greeting"
        elif float(attrs.get("loquacity_threshold", 1.0)) <= 0.2:
            kind = "smalltalk"
        else:
            kind = "stay_silent"
        attrs["chosen_speech_code"] = float(next(code for code, name in KIND_LABEL.items() if name == kind))
        if kind == "stay_silent" and attrs.get("obligation"):
            absence = self.s.add_node("NoticeableAbsence", {"speaker": speaker, "target": target})
            self.inner.add_edge_unchecked(enc, "has_absence", absence)
            self.inner.add_edge_unchecked(self.bw.agents[target], "notices", absence)
        return kind

    def utter(self, name, arousal, *, base_loudness=1.0, loud_arousal_gain=0.6, max_loudness=100.0):
        if name not in self.bw.agents:
            self.add_agent(name)
        node = self.s.add_node("Utterance", {"speaker_arousal": float(arousal),
            "base_loudness": float(base_loudness), "loud_arousal_gain": float(loud_arousal_gain),
            "max_loudness": float(max_loudness),
            "eff_loudness": min(float(max_loudness), float(base_loudness) + float(loud_arousal_gain) * float(arousal))})
        self.utts[name] = node
        return node

    def tick(self):
        self.bw.tick()

    def chosen_code(self, speaker, target):
        return int(round(float(self.s.node(self.encs[(speaker, target)])["attrs"].get("chosen_speech_code", -1))))

    def chosen_kind(self, speaker, target):
        return KIND_LABEL.get(self.chosen_code(speaker, target), "undecided")

    def spoke(self, speaker, target):
        return self.chosen_code(speaker, target) not in (-1, 0)

    def noticeable_absence(self, speaker, target):
        enc = self.encs[(speaker, target)]
        absence = self.inner.neighbours(enc, "has_absence")
        return {"minted": bool(absence), "target_notices": bool(absence)}

    def eff_loudness(self, name):
        return round(float(self.s.node(self.utts[name])["attrs"]["eff_loudness"]), 4)

    def bond_slots(self, speaker, target):
        return self.bw.slots(speaker, target)

    def close(self):
        return self.bw.close()
