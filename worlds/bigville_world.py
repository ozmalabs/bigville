"""BigvilleWorld -- bigville R72/R76 (blocks 390000, 394000): the canonical, data-driven, FLOAT-FREE
world, on the ONE general action engine.

Every entity comes from the ONE data file (domains/bigville_entities.py): items, containers,
recipes, buildings. There is now a SINGLE making engine -- the generic action (bigville_action_
general): perform an action on N things with Y tools, optionally timed, producing a bulk material or
a discrete tool (quality = maker's skill) that wears. A recipe is just an action. Commodities are
PHYSICAL Stock piles, never store floats. Adding a tool/material/recipe (any inputs, any tools) is a
DATA EDIT, no code change.
"""
from __future__ import annotations

import json
import math
import random
import heapq
import threading
import weakref
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from bigville.runtime import (BigvilleGraph, NodeRef, WorldAdapter, boot_core,
                               load_seeds_into, manifest_for)
from bigville.scenarios import load_scenario
from domains.data_view import entities as _entities_view  # noqa: E402
from bigville.backends.speech import DeterministicSpeechBackend  # noqa: E402
from worlds.bigville_bond_world import (BigvilleBondWorld,
                                        SLOT_DEFAULTS as BOND_SLOTS)  # noqa: E402
from domains.world_affordances import round_bp  # noqa: E402
from worlds import daynight as _dn  # noqa: E402  Phase 042: day, night and lamps

# Phase 048: the default for a job's or an attempt's tool: the right one the worker has, else bare hands.
_DEFAULT_TOOL = object()

# TG02 debug switch: worlds added here use the brute-force proximity scan instead
# of the occupancy index. Kept off the instance so it is never checkpointed.
_FORCE_LINEAR_PROXIMITY_WORLDS = weakref.WeakSet()

# TG03: the lazy shortest-path fields are shared derived state. Context building
# may run in a pool, so the cache (and the BFS that fills it) is guarded. The
# lock is module-level and never checkpointed; the field contents stay the same.
_DISTANCE_FIELDS_LOCK = threading.RLock()

# TG05: event and utterance logs assign their next key from ``len(log) + 1``.
# Under a concurrent commit two writers could otherwise mint the same key and
# silently drop one record. The graph lock already makes node creation safe;
# this lock only serialises the small log insertion. It is module level and
# never checkpointed.
_EVENT_LOG_LOCK = threading.RLock()

DEFAULT_DATA_PACK = "bigville"


def requested_data_pack(data_pack=None, scenario_data=None):
    """The data pack a world reads. `data_pack` (constructor) and the scenario's "data_pack" are
    alternatives: giving both is an error, as for physical_subsystems. Default: "bigville"."""
    scenario_data = scenario_data or {}
    if data_pack is not None and "data_pack" in scenario_data:
        raise ValueError("data_pack may be specified either in the scenario or constructor")
    if data_pack is not None:
        if not isinstance(data_pack, str) or not data_pack:
            raise TypeError("data_pack must be a pack name or directory")
        return data_pack
    configured = scenario_data.get("data_pack")
    if configured is None:
        return DEFAULT_DATA_PACK
    if not isinstance(configured, str) or not configured:
        raise TypeError("scenario data_pack must be a pack name or directory")
    return configured


class BigvilleOcelotActor:
    """One resident mind, backed by an independent private cognition graph.

    This is deliberately a small host wrapper.  The resident's choice is made
    by the seeded ``bigville_actor_decision`` rule over the affordances the
    world publishes; the wrapper only provides the graph and runs one native
    cognition pass. Its seed list is the pack's RESIDENT_SEEDS (the default
    pack when no ``data_pack`` is given, so a mind also works without a world).
    """

    def __init__(self, name, data_pack=None):
        self.name = str(name)
        self.s, self.agent = boot_core()
        self.inner = self.s._inner
        resident = _entities_view(data_pack)
        # The speech faculty is held by the resident as graph data.  The town
        # publishes encounters; these rules decide whether this resident
        # speaks and what kind of turn it makes.  No clock or Python schedule
        # is part of that choice.
        for seed_id in resident.RESIDENT_SEEDS:
            self.inner.load_seed_manifest(manifest_for(seed_id), self.agent)
        # Keep the speech-act vocabulary (including request/question) in the
        # resident's conceptual graph.  It interprets free text; it is not
        # a Bigville affordance.
        load_seeds_into(self.s, self.agent, resident.RESIDENT_CONCEPT_SEEDS)
        self.s.set_attr(self.agent, "name", self.name)
        self.s.set_attr(self.agent, "chosen_action", "")
        self.s.set_attr(self.agent, "chosen_kind", "")
        self.s.set_attr(self.agent, "chosen_trade", "")
        self.s.set_attr(self.agent, "chosen_recipe", "")
        self.s.set_attr(self.agent, "chosen_target", "")
        self.s.set_attr(self.agent, "decision_armed", 0.0)
        for type_name, attrs in (
                ("Concept", {"name": "conversation"}),
                ("Concept", {"name": "request"}),
                ("Frame", {"name": "resident_turn"}),
                ("Goal", {"name": "maintain_village_life"}),
                ("Belief", {"name": "world_is_physical"})):
            node = self.s.add_node(type_name, attrs)
            self.inner.add_edge_unchecked(self.agent, "holds", node)
        self.speech_bonds = {}
        self.speech_encounters = {}
        self.speech_choices = {}
        self.speech_backend = DeterministicSpeechBackend(self)
        # How many times THIS resident has told a given listener about a
        # given event -- common ground is per-dyad (Clark & Brennan 1991),
        # so retelling a DIFFERENT listener the same news stays undamped.
        self.told_events = {}
        self._read_documents = {}
        # Second-hand events this resident has been told about, distinct
        # from first-hand ``observed_event`` edges: {event: {"day_heard",
        # "strength"}}.  Strength compounds multiplicatively across hops
        # (DeGroot 1974) -- a three-hop rumor's strength is the PRODUCT of
        # three trust terms, degrading the way a real rumor's credibility
        # does, without any global broadcast.
        self.heard_events = {}
        # The speech decision above selects an occasion/kind.  The actual
        # utterance is produced by the existing goal-driven communicative
        # faculty, which renders a structured meaning from its graph-resident
        # language machinery and models addressee uptake.
        self.voice = WorldAdapter(seeds=())
        self._voice_targets = {}

    #: Converts a terrain stamina multiplier into affordance-score units. The one
    #: scalar in this valuation; the SHAPE around it -- proportional to both the
    #: terrain's own cost and to how spent the resident is -- is what carries the
    #: behaviour, and the constant only sets how loudly it speaks.
    EFFORT_TO_SCORE = 6.0

    def publish_body_state(self, stamina_reserve):
        """Record the body read-off this resident's valuation reads. Mechanical."""
        self.s.set_attr(self.agent, "stamina_reserve", float(stamina_reserve))

    def _option_value(self, option_attrs):
        """Score an option as the world's score less what the route costs THIS body.

        Mirrors `oa_choose_option` in `seeds/bigville_actor_decision.json`, which is
        the real, graph-native form of this valuation; this Python copy is what runs
        under the dependency-free local runtime, whose `settle()` is a no-op.
        """
        score = float(option_attrs.get("score", 0.0))
        stamina = float(option_attrs.get("terrain_stamina_multiplier", 0.0) or 0.0)
        reserve = float(self.s.node(self.agent)["attrs"].get("stamina_reserve", 1.0))
        return score - self.EFFORT_TO_SCORE * stamina * (1.0 - reserve)

    def replace_options(self, options):
        """Publish the current legal affordance set as ordinary mind-graph data."""
        for option in list(self.inner.neighbours(self.agent, "has_option")):
            self.inner.remove_node(option)
        for option in options:
            node = self.s.add_node("ActorOption", dict(option))
            self.inner.add_edge_unchecked(self.agent, "has_option", node)
        for key, value in (("chosen_action", ""), ("chosen_kind", ""),
                           ("chosen_trade", ""), ("chosen_recipe", ""),
                           ("chosen_target", "")):
            self.s.set_attr(self.agent, key, value)
        self.s.set_attr(self.agent, "decision_armed", 1.0)

    def ingest_document(self, text, *, name="physically_read_document"):
        """Store a physical reading without claiming comprehension.

        This is the dependency-free fallback.  A real Ocelot provider replaces
        this method and returns evidence from its own comprehension graph.  A
        document node alone is deliberately not an ``Understanding``.
        """
        text = str(text or "")
        if not text:
            return None
        key = (str(name), text)
        if key in self._read_documents:
            return self._read_documents[key]
        document = self.s.add_node("Document", {
            "name": str(name),
            "source": "physical_object",
            "text": text,
            "status": "stored_not_understood",
        })
        residual = self.s.add_node("ComprehensionResidual", {
            "kind": "physical_prose",
            "source": str(name),
            "status": "not_understood",
            "reason": "no cognition provider is attached",
        })
        self.inner.add_edge_unchecked(self.agent, "read", document)
        self.inner.add_edge_unchecked(self.agent, "holds", residual)
        result = {"status": "not_understood", "document": document,
                  "residual": residual, "reason": "no cognition provider is attached"}
        self._read_documents[key] = result
        return result

    def has_read_document(self, text, *, name="physically_read_document"):
        return (str(name), str(text or "")) in self._read_documents

    def ingest_rulebook(self, text):
        """Compatibility alias for callers that know the document's role."""
        return self.ingest_document(text, name="physically_read_rulebook")

    def decide(self):
        """Select one published affordance in the cheap local backend."""
        attrs = self.s.node(self.agent)["attrs"]
        chosen_attrs = None
        options = self.inner.neighbours(self.agent, "has_option")
        if options:
            chosen = max(options, key=lambda n: (
                self._option_value(self.s.node(n)["attrs"]), -int(n)))
            chosen_attrs = self.s.node(chosen)["attrs"]
            for key in ("chosen_action", "chosen_kind", "chosen_trade",
                        "chosen_recipe", "chosen_target"):
                self.s.set_attr(self.agent, key, chosen_attrs.get(key[8:], "")
                                if key.startswith("chosen_") else "")
            # The option keys are named without the ``chosen_`` prefix.
            for key in ("action", "kind", "trade", "recipe", "target"):
                self.s.set_attr(self.agent, "chosen_" + key,
                                chosen_attrs.get(key, ""))
            self.s.set_attr(self.agent, "decision_armed", 0.0)
            attrs = self.s.node(self.agent)["attrs"]
        # Preserve every affordance parameter.  The cognition backend must
        # be able to return a concrete object/property/recipient selected
        # from the world publication; reducing it to a fixed vocabulary would
        # turn an Ocelot decision back into a harness-side guess.
        result = dict(chosen_attrs or {})
        result.update({"action": attrs.get("chosen_action", ""),
                       "kind": attrs.get("chosen_kind", ""),
                       "trade": attrs.get("chosen_trade", ""),
                       "recipe": attrs.get("chosen_recipe", ""),
                       "target": attrs.get("chosen_target", "")})
        return result

    def goal_utterance(self, target, meaning, *, priority=1.0):
        """Turn a held communicative goal into produced surface text.

        Bigville only supplies the target and structured goal.  It does not
        choose words or interpolate a sentence; ``WorldAdapter``'s existing
        communicative-action faculty renders the goal and records addressee
        uptake in the resident's private voice graph.
        """
        interlocutor = self._voice_targets.get(target)
        if interlocutor is None:
            interlocutor = self.voice.s.add_node(
                "Interlocutor", {"name": str(target),
                                  "believed_concepts": frozenset()})
            self._voice_targets[target] = interlocutor
        self.voice.set_addressee(interlocutor)
        self.voice.add_communicative_goal(meaning, priority=priority)
        spoken = self.voice._communicative_action()
        return spoken[-1] if spoken else None

    @staticmethod
    def _state_value(value):
        """Convert a held graph value to a JSON-safe inspection value."""
        if isinstance(value, dict):
            return {str(k): BigvilleOcelotActor._state_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [BigvilleOcelotActor._state_value(v) for v in value]
        if hasattr(value, "value"):
            return value.value
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return repr(value)

    def dump_held_state(self):
        """Reverse cognition API: dump what this resident currently holds.

        This is deliberately a read-only projection owned by the cognition
        implementer.  The town can request it for inspection or persistence,
        but it cannot use the dump to manufacture a world fact or mutate the
        resident's private graph.
        """
        action_attrs = dict(self.s.node(self.agent)["attrs"])

        def typed_nodes(types):
            result = []
            for type_name in types:
                for node in self.s.nodes(type_name):
                    result.append({"type": type_name, "id": int(node.value),
                                   "attrs": self._state_value(dict(self.s.node(node)["attrs"]))})
            return result

        return {
            "character_id": self.name,
            "backend": "ocelot",
            "identity": {"name": self.name},
            "personality": self._state_value(action_attrs),
            "memories": typed_nodes(("Memory", "JournalEntry", "Fact")),
            "held_frames": typed_nodes(("Frame", "Microtheory", "Concept", "Document", "Understanding", "ComprehensionResidual")),
            "concepts": typed_nodes(("Concept", "Sign")),
            "goals": typed_nodes(("Goal", "CommunicativeGoal", "LifeGoal")),
            "beliefs": typed_nodes(("Belief", "Fact", "Interlocutor")),
            "decision": {
                "action": self._state_value(action_attrs),
                "speech_choices": self._state_value(self.speech_choices),
            },
            "backend_state": {
                "mind_graph": self._state_value(self.s.graph_to_dict()),
                "voice_graph": self._state_value(self.voice.s.graph_to_dict()),
            },
        }


class _HandoverCount:
    """len() of the fiscal coin handovers recorded so far (Phase 026).

    village_eval.py reads ``len(world._transactions)`` for its registered transaction count. That count
    used to come from the Transaction ledger, which only the fiscal actions wrote. This stands in for it:
    a count, not a ledger, and it never shrinks when old Handover facts are dropped.
    """

    def __init__(self, count):
        self._count = int(count)

    def __len__(self):
        return self._count


class _ActorPositions(dict):
    """Actor name -> map cell, with a derived cell -> resident-name bucket index (TG02).

    The canonical ``_actor_positions`` mapping is a plain dictionary at rest and
    checkpoints as one. This subclass keeps a bucket map in sync with every
    mutation so nearby-resident queries do not scan every resident. The bucket
    map is derived state: it lives on the instance, not in the mapping, so it
    never enters a checkpoint.

    All dictionary mutation entry points are overridden: assignment, deletion,
    ``pop``, ``update``, ``clear`` and ``setdefault``. ``rebuild`` recomputes the
    index from the current contents, and ``near`` returns the names in the
    Chebyshev bounding square around a cell.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._cell_buckets: dict[object, set[str]] = {}
        if args or kwargs:
            self.update(*args, **kwargs)

    @staticmethod
    def _cell_key(cell):
        if isinstance(cell, (tuple, list)) and len(cell) == 2:
            return (cell[0], cell[1])
        try:
            hash(cell)
        except TypeError:
            return None
        return cell

    def _bucket_add(self, name, cell):
        key = self._cell_key(cell)
        if key is None:
            return
        self._cell_buckets.setdefault(key, set()).add(name)

    def _bucket_discard(self, name, cell):
        key = self._cell_key(cell)
        if key is None:
            return
        bucket = self._cell_buckets.get(key)
        if bucket is None:
            return
        bucket.discard(name)
        if not bucket:
            del self._cell_buckets[key]

    def __setitem__(self, name, cell):
        if dict.__contains__(self, name):
            self._bucket_discard(name, dict.__getitem__(self, name))
        dict.__setitem__(self, name, cell)
        self._bucket_add(name, cell)

    def __delitem__(self, name):
        cell = dict.__getitem__(self, name)
        dict.__delitem__(self, name)
        self._bucket_discard(name, cell)

    def pop(self, name, *default):
        if not dict.__contains__(self, name):
            if default:
                return default[0]
            raise KeyError(name)
        cell = dict.__getitem__(self, name)
        value = dict.pop(self, name)
        self._bucket_discard(name, cell)
        return value

    def popitem(self):
        name, cell = dict.popitem(self)
        self._bucket_discard(name, cell)
        return name, cell

    def update(self, *args, **kwargs):
        for name, cell in dict(*args, **kwargs).items():
            self[name] = cell

    def setdefault(self, name, default=None):
        if dict.__contains__(self, name):
            return dict.__getitem__(self, name)
        self[name] = default
        return default

    def clear(self):
        dict.clear(self)
        self._cell_buckets.clear()

    def rebuild(self):
        """Recompute the bucket index from the mapping's current contents."""
        buckets: dict[object, set[str]] = {}
        for name, cell in dict.items(self):
            key = self._cell_key(cell)
            if key is None:
                continue
            buckets.setdefault(key, set()).add(name)
        self._cell_buckets = buckets

    def near(self, cell, radius):
        """Names in the Chebyshev bounding square around ``cell``, sorted.

        This is a candidate superset for walkable-distance filtering, not a
        final answer: a resident in the square may still be unreachable.
        """
        if not isinstance(cell, (tuple, list)) or len(cell) != 2:
            return []
        try:
            x, y = int(cell[0]), int(cell[1])
            reach = max(0, int(radius))
        except (TypeError, ValueError):
            return []
        names: set[str] = set()
        for cx in range(x - reach, x + reach + 1):
            for cy in range(y - reach, y + reach + 1):
                names.update(self._cell_buckets.get((cx, cy), ()))
        return sorted(names)


class _PhysicalObjectLocations(dict):
    """Object id -> location, with a derived location -> object-id bucket index (LA03).

    The canonical mapping is a plain dictionary at rest and checkpoints as one.
    This subclass keeps the location buckets in sync with every mutation, so
    observation can answer "what is at this location?" without scanning every
    physical object. The bucket map is derived state: it lives on the instance,
    not in the mapping, so it never enters a checkpoint. A restored plain dict
    is rewrapped (and rebuilt) by ``BigvilleWorld._ensure_physical_object_locations``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._location_buckets: dict[str, set[str]] = {}
        if args or kwargs:
            self.update(*args, **kwargs)

    @staticmethod
    def _location_key(location):
        if isinstance(location, (tuple, list)) and len(location) == 2:
            return (location[0], location[1])
        try:
            hash(location)
        except TypeError:
            return None
        return location

    def _bucket_add(self, object_id, location):
        key = self._location_key(location)
        if key is None:
            return
        self._location_buckets.setdefault(key, set()).add(object_id)

    def _bucket_discard(self, object_id, location):
        key = self._location_key(location)
        if key is None:
            return
        bucket = self._location_buckets.get(key)
        if bucket is None:
            return
        bucket.discard(object_id)
        if not bucket:
            del self._location_buckets[key]

    def __setitem__(self, object_id, location):
        if dict.__contains__(self, object_id):
            self._bucket_discard(object_id, dict.__getitem__(self, object_id))
        dict.__setitem__(self, object_id, location)
        self._bucket_add(object_id, location)

    def __delitem__(self, object_id):
        location = dict.__getitem__(self, object_id)
        dict.__delitem__(self, object_id)
        self._bucket_discard(object_id, location)

    def pop(self, object_id, *default):
        if not dict.__contains__(self, object_id):
            if default:
                return default[0]
            raise KeyError(object_id)
        location = dict.__getitem__(self, object_id)
        value = dict.pop(self, object_id)
        self._bucket_discard(object_id, location)
        return value

    def popitem(self):
        object_id, location = dict.popitem(self)
        self._bucket_discard(object_id, location)
        return object_id, location

    def update(self, *args, **kwargs):
        for object_id, location in dict(*args, **kwargs).items():
            self[object_id] = location

    def setdefault(self, object_id, default=None):
        if dict.__contains__(self, object_id):
            return dict.__getitem__(self, object_id)
        self[object_id] = default
        return default

    def clear(self):
        dict.clear(self)
        self._location_buckets.clear()

    def rebuild(self):
        """Recompute the location bucket index from the current mapping."""
        buckets: dict[str, set[str]] = {}
        for object_id, location in dict.items(self):
            key = self._location_key(location)
            if key is None:
                continue
            buckets.setdefault(key, set()).add(object_id)
        self._location_buckets = buckets

    def ids_at(self, location):
        """Object ids at one location, sorted; the index's read path."""
        return sorted(self._location_buckets.get(self._location_key(location), ()))


class BigvilleWorld:
    PHYSICAL_SUBSYSTEM_DEFAULTS = {
        "metabolism": True,
        "ecology": True,
        "decay": True,
        # Hands get better with practice: completed work consolidates into skill levels at the
        # end of each period (E.practice_gain). Off, levels change only when set explicitly.
        "practice": True,
        # Understanding (skills tagged learning="cognitive") consolidates only when this is on.
        # Off, completed cognitive work still logs its minutes, the world leaves the levels alone,
        # and it publishes the practice to the actor as a "practice" observation, so the resident's
        # backend decides what it learned. Physical skills consolidate under "practice" regardless.
        "cognitive_practice": False,
        # Loudness is the hearing radius (Phase 028, seeds/bigville_loud_comm.json). Off, every speech act
        # carries the flat radius from the HEARING table, whatever the speaker chose.
        "loudness": True,
        # Use builds the body (Phase 032, seeds bd_train_strength, bd_train_stamina): each effort raises the
        # trained strength or stamina it uses, toward base x TRAIN_HEADROOM. Off, no effort trains anyone.
        "training": True,
        # Phase 043: illness onset (DISEASE) and its daily course, and the doctor's and midwife's acts
        # (MEDICAL_CARE). Off, no resident catches an illness from the dawn tick and the new care options are
        # not offered; the existing disease rules (diagnose, the burial condition) are unchanged.
        "illness": False,
        # Phase 047: people acting together (JOINT_TASKS: a heavy load carried by several, a crewed recipe worked by
        # several). Off, no joint option is published, a joint proposal is refused as unsupported, and every recipe
        # runs as before, whatever its crew field says.
        "joint_actions": False,
        # Phase 035: specific satiety lowers a repeated food's energy (feeds x freshness x (1 - satiety)). Off by
        # default: the founding village eats mostly bread and runs close to the starvation limit (peak hunger 3.78
        # of 4.0 in 384 turns), so the rule changes the simple village's eating and survival. With it off, satiety
        # is still tracked and still lowers the meal's pleasure and the mood; only the energy is unchanged.
        "monotony": False,
        # Phase 036: alcohol's longer effects (INTOXICATION aftereffect keys): tolerance and its fade, dependence, craving
        # and withdrawal, the hangover after a heavy night, poisoning above poison_above, speech clarity by the
        # speaker's intoxication and the listener's distance, and the body fields read by the coping policy. Off,
        # a drink still raises intoxication as Phase 034 has it, and none of these rules, read-offs or fields exist.
        "alcohol_aftereffects": False,
        # Phase 040: objects as arms (OBJECT_FORCE). Off, a strike ignores `with`, and a throw is refused as unsupported.
        "object_force": False,
    }

    @property
    def _force_linear_proximity(self):
        """TG02 debug switch: use the brute-force proximity scan instead of the index."""
        return self in _FORCE_LINEAR_PROXIMITY_WORLDS

    @_force_linear_proximity.setter
    def _force_linear_proximity(self, enabled):
        if enabled:
            _FORCE_LINEAR_PROXIMITY_WORLDS.add(self)
        else:
            _FORCE_LINEAR_PROXIMITY_WORLDS.discard(self)

    def _validate_physical_subsystems(self, configured):
        if not isinstance(configured, dict):
            raise TypeError("physical_subsystems must be a mapping of names to booleans")
        known = set(self.PHYSICAL_SUBSYSTEM_DEFAULTS) | set(self._physical_subsystem_extensions)
        unknown = sorted(set(configured) - known)
        if unknown:
            raise ValueError(f"Unknown physical subsystem(s): {', '.join(map(str, unknown))}")
        result = dict(self.PHYSICAL_SUBSYSTEM_DEFAULTS)
        result.update({name: False for name in self._physical_subsystem_extensions})
        for name, enabled in configured.items():
            if not isinstance(enabled, bool):
                raise TypeError(f"physical_subsystems.{name} must be a boolean")
            result[name] = enabled
        return result

    def register_physical_subsystem(self, name, callback, *, enabled=False):
        """Register a future period-driven physical subsystem.

        The callback receives ``(world, 1)`` once for each elapsed period. Register before
        advancing time; custom names can also be enabled in scenario config
        when the callback is supplied to the constructor.
        """
        name = str(name)
        if not name or name in self.PHYSICAL_SUBSYSTEM_DEFAULTS or name in self._physical_subsystem_extensions:
            raise ValueError(f"Invalid or duplicate physical subsystem: {name}")
        if not callable(callback):
            raise TypeError("physical subsystem callback must be callable")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        self._physical_subsystem_extensions[name] = callback
        self.physical_subsystems[name] = enabled

    # ------------------------------------------------------------------ attempt state
    # TG05: these three flags are per attempt, not per world.  A threaded commit
    # may run independent residents' attempts at the same time, so storing them
    # on the shared instance let one resident see another's open outcome,
    # refusal code or major-dispatch guard.  The properties keep every existing
    # assignment and read working while the storage is a ``threading.local``.
    @property
    def _outcome_open(self) -> bool:
        return bool(getattr(self._attempt_state, "outcome_open", False))

    @_outcome_open.setter
    def _outcome_open(self, value) -> None:
        self._attempt_state.outcome_open = bool(value)

    @property
    def _refusal_code(self):
        return getattr(self._attempt_state, "refusal_code", None)

    @_refusal_code.setter
    def _refusal_code(self, value) -> None:
        self._attempt_state.refusal_code = value

    @property
    def _major_dispatch(self) -> bool:
        return bool(getattr(self._attempt_state, "major_dispatch", False))

    @_major_dispatch.setter
    def _major_dispatch(self, value) -> None:
        self._attempt_state.major_dispatch = bool(value)

    def __init__(self, *, map_seed=305000, autonomous_actors=False, scenario=None,
                 cognition_factory=None, physical_subsystems=None,
                 physical_subsystem_extensions=None, data_pack=None, exhaustion_slow_on=None):
        scenario_definition = load_scenario(scenario) if scenario is not None else None
        self._scenario_data = scenario_definition.to_dict() if scenario_definition else {
            "id": "bigville", "name": "Bigville", "metadata": {"domain": "village"}}
        # Every entity table and rule this world reads comes from one data pack (see domains/data_view.py).
        self.data_pack = requested_data_pack(data_pack, self._scenario_data)
        self.E = _entities_view(self.data_pack)
        # These switches gate only their named physical period effects. Extension
        # callbacks are opt-in and receive the number of elapsed periods.
        self._physical_subsystem_extensions = dict(physical_subsystem_extensions or {})
        if any(not callable(callback) for callback in self._physical_subsystem_extensions.values()):
            raise TypeError("physical subsystem extensions must be callable")
        configured_subsystems = self._scenario_data.get("physical_subsystems", {})
        if physical_subsystems is not None:
            if "physical_subsystems" in self._scenario_data:
                raise ValueError("physical_subsystems may be specified either in the scenario or constructor")
            configured_subsystems = physical_subsystems
        self.physical_subsystems = self._validate_physical_subsystems(configured_subsystems)
        # Exhaustion slowdown (Phase 024) is the seed's slow_on switch. An explicit constructor value wins,
        # then the scenario's `exhaustion.slow_on`, then the pack default. Off, there is no slowdown.
        if exhaustion_slow_on is None:
            exhaustion_slow_on = (self._scenario_data.get("exhaustion") or {}).get(
                "slow_on", self.E.EXHAUSTION["slow_on"])
        if not isinstance(exhaustion_slow_on, bool):
            raise TypeError("exhaustion slow_on must be a boolean")
        self.exhaustion_slow_on = exhaustion_slow_on
        # Optional external cognition seam.  Bigville remains installable
        # without Ocelot; an Ocelot host supplies a callable name -> mind.
        self._cognition_factory = cognition_factory
        self._scenario_actor_backends = {
            str(actor.get("name")): str(actor.get("backend"))
            for actor in self._scenario_data.get("actors", [])
            if actor.get("name") and actor.get("backend")
        }
        self._scenario_simple_profiles = {
            str(actor.get("name")): str(actor.get("simple_profile"))
            for actor in self._scenario_data.get("actors", [])
            if actor.get("name") and actor.get("simple_profile")
        }
        self._scenario_character_data = {}
        self.eng = BigvilleGraph()
        # The making engine and the rules each physical subsystem needs, in load order (the pack's
        # ENGINE_SEEDS). Exertion belongs to the resident's Body layer: movement and carrying feed
        # Effort into bd_exert_cost rather than a second Agent-level energy ledger.
        for seed_id in self.E.ENGINE_SEEDS:
            self.eng.load_seed_manifest(manifest_for(seed_id), None)
        for seed_id in self._scenario_data.get("seeds", []):
            self.eng.load_seed_manifest(manifest_for(str(seed_id)), None)
        initial = dict(self._scenario_data.get("initial", {}))
        self._town = self.eng.add_node("Town", {"name": self._scenario_data.get("name", "Bigville"),
                                                **dict(self.E.TOWN_INITIAL), **initial})   # the weather clothes protect against
        self._store = self.eng.add_node("Store", {"name": "store"})           # holds Stock NODES, no commodity floats
        self.eng.add_edge_unchecked(self._town, "has_store", self._store)
        # Phase 030: the store's lock is a Lock node of its own (the store keeps no lock attributes), with the
        # founding state from packs/*/world/locks.json. The default is unlocked.
        store_lock = self.eng.add_node("Lock", {"lock_id": float(self.E.STORE_LOCK["lock_id"]),
                                                "locked": 1.0 if self.E.STORE_LOCK["locked"] else 0.0,
                                                "keys_required": float(self.E.STORE_LOCK["keys_required"])})
        self.eng.add_edge_unchecked(self._store, "has_lock", store_lock)
        # True only while the founding village policy (_village_work_tick) runs: its store access is not guarded.
        self._store_bypass = False
        self._stock = {}; self._last_stock_qty = {}
        self._actors = {}; self._items = {}; self._actions = {}
        self._reference_specs = {}
        self._actor_references = {}
        self._actor_policies = {}
        self._documents = {}
        self._deeds = {}
        self._titles = {}
        self._land_disputes = {}
        self._households = {}
        self._infrastructure = {}
        self._animals = {}
        self._fences = {}
        self._enclosures = {}
        self._enclosure_cells = {}
        self._crops = {}
        self._land = {}
        self._water_sources = {}
        self._affordances = {}
        self._observation_schemas = {}
        self._map_cells = {}
        # Phase 029: the pending contested take (a plain dict, None when none), and the actors' cells at the
        # start of the turn, which decide whether a target could see a taker coming.
        self._contest = None
        self._turn_start_positions = {}
        # Cells crossed during the current turn. Ground that saw traffic this turn does
        # not also recover this turn; everything else grows back.
        self._traversed_this_tick = set()
        self._distance_fields = {}
        self._travel_time_fields = {}
        self._map_grid = None
        self._map_layout = None
        self._map_affordances = {}
        # Scenario-authored physical objects are deliberately neutral. The
        # world does not know whether a box and its contents are Monopoly,
        # another game, or unrelated objects; interpretation and use stay in
        # participants' held frames.
        self._physical_objects = {}
        self._physical_object_aliases = {}
        self._physical_object_locations = _PhysicalObjectLocations()
        self._actor_cells = {}
        self._actor_positions = _ActorPositions()
        self._actor_goals = {}
        self._land_cells = {}
        self._household_cells = {}
        self._resource_deposits = {}
        self._gathering_sites = {}          # Phase 004: gathering kind -> its ResourceDeposit-style site node
        self._shops = {}
        self._actor_inventories = {}
        self._actor_tableware = {}
        self._actor_hands = {}
        self._dropped_stocks = {}
        self._bodies = {}
        # Each resident has a private Ocelot mind graph.  The town never picks
        # an action for them; it publishes affordances and enacts their read-off.
        self._actor_minds = {}
        self._actor_decisions = {}
        self._actor_targets = {}
        # Defer movement exertion rule sweeps until all residents have chosen
        # for this tick; the physical Effort events remain individually
        # represented in the graph.
        self._actor_tick_in_progress = False
        # Retained for compatibility with older constructors. World ticks do
        # not select resident behavior; unattended cognition belongs to
        # BigvilleGame and its configured backends.
        self._autonomous_actors = bool(autonomous_actors)
        self._conversation_adapter = None
        self._building_projects = {}
        # Durable public-sphere, civic, economic, and life-history records.
        # These are world records; resident beliefs and knowledge remain on
        # resident edges/facts and are never collapsed into town facts.
        self._events = {}
        self._articles = {}
        self._editions = {}
        self._newspaper_copies = {}
        self._proposals = {}
        self._meetings = {}
        self._cases = {}
        self._handovers = {}
        self._handover_totals = {"count": 0, "fiscal": 0, "by_good": {}, "by_kind": {}, "by_endpoint": {}}
        self._prices = {}
        self._illnesses = {}
        self._births = []
        self._deaths = []
        self._alive_snapshot = {}
        self._report_history = []
        self._journals = {}
        self._rng = random.Random(int(map_seed))
        # Animal births derive their sexes from this seed (see _give_birth), so births keep no RNG state
        # of their own and never shift `_rng`.
        self._animal_life_seed = int(map_seed)
        # Burial onset draws (see _burial_roll) are stateless, keyed on this seed, the resident, and the day.
        self._burial_seed = int(map_seed)
        self._corpses = {}         # resident name -> the corpse's ToolItem node (Phase 010)
        # Unified social graph.  These are world-mediated records; beliefs,
        # intentions, and relationship models remain on the resident edges and
        # attributes rather than being smuggled into body state.
        self._notes = {}
        self._conversations = {}
        self._utterances = {}
        # LA03: derived recipient -> utterance index. It is maintained by
        # ``speak`` for every delivery with heard=1; ``heard_utterances`` uses
        # it when the log size still matches and falls back to a scan otherwise.
        self._heard_utterance_index = {}
        self._heard_utterance_log_size = 0
        self._speech_events = []
        self._market_expectation_specs = {}
        self._actor_market_expectations = {}
        self._requests = {}
        self._relationships = {}
        self._turn_actions = {}
        self._turn = 0
        self._resolved_period = 0.0
        self._job_tick_armed = False
        # EN03: opt-in turn batching.  ``_rule_batch_depth`` counts open
        # ``batch_rules()`` scopes; while it is positive a primitive ``_run()``
        # records that one full sweep is owed (``_rule_batch_pending``) instead
        # of sweeping immediately.  Both are ephemeral: a checkpoint excludes
        # them and a restored world starts at 0/False.
        self._rule_batch_depth = 0
        self._rule_batch_pending = False
        # TG05: the per-attempt flags belong to the thread running one actor's
        # attempt, never to the world.  They are exposed through the same
        # private names below so existing assignments and reads are unchanged.
        self._attempt_state = threading.local()
        self._major_dispatch = False
        # Phase 021: the reason the current major-action attempt was refused, and whether an attempt is open.
        self._refusal_code = None
        self._outcome_open = False
        self._next_home_index = 0
        self._next_farm_index = 0
        self._policy_specs = self._scenario_table("policies", self.E.POLICIES)
        self._law_specs = self._scenario_table("laws", self.E.LAWS)
        self._charter_specs = self._scenario_table("charters", self.E.CHARTERS)
        # Lawmaking and justice stages: the pack's tables, with a scenario's "procedures" applied.
        self._procedures = self._procedure_tables()
        self._item_specs = dict(self.E.ITEMS)   # runtime item registry (data + runtime-added)
        self._recipe_specs = {}            # recipe name -> its data row (data + runtime-added)
        self.set_stock("none", 1e9)
        self._install_map(map_seed, self._scenario_data.get("map") or None)
        self._install_physical_objects()
        for kind, spec in self.E.ITEMS.items():
            self._install_item(kind, spec)
        for r in self.E.RECIPES:
            self._install_recipe(r)
        for reference in self.E.all_reference_templates():
            self._register_reference(reference)
        for name, spec in self.E.AFFORDANCES.items():
            node = self.eng.add_node("Affordance", {"name": name, "domain": spec["domain"]})
            self.eng.add_edge_unchecked(self._town, "has_affordance", node)
            self._affordances[name] = node
        for name, spec in self.E.OBSERVATION_TYPES.items():
            node = self.eng.add_node("ObservationSchema", {"name": name, "source": spec["source"]})
            self.eng.add_edge_unchecked(self._town, "has_observation_schema", node)
            self._observation_schemas[name] = node
        self._places = {}; self._containers = {}
        # Phase 048: plain counts of improvised work, accidents from strain, and broken tools (see tool_tally).
        self._tool_tally = {"improvised_jobs": 0, "accidents": 0, "broken_tools": 0}
        # Phase 034: resident-ticks spent in each intoxication band, and grams of alcohol drunk (plain counts)
        self._intox_ticks = {band: 0 for band in self.E.INTOXICATION_BANDS}
        self._intox_drunk_grams = 0.0
        # Building anchors are physical sites, not just labels. Keep each
        # authored footprint clear so adjacent facades cannot overlap.
        self._building_sites = {}
        scenario_buildings = self._scenario_data.get("buildings")
        if scenario_buildings is None:
            scenario_buildings = [{"kind": kind, "spec": spec}
                                  for kind, spec in self.E.founding_buildings().items()]
        for building in scenario_buildings:
            kind = str(building.get("kind", "place"))
            spec = dict(self.E.BUILDINGS.get(kind, {}))
            spec.update(dict(building.get("spec", {})))
            self._install_building(kind, spec, key=building.get("name"),
                                   cell=building.get("cell"))
        # Each standing building gets the tools its trades work with (see
        # _equip_workshop); recipes never create tools that float free of a place.
        for place in list(self._places.values()):
            self._equip_workshop(place, self._workshop_kit(self._place_kind(place)))

        # The square and its board are ordinary world entities, not a second
        # noticeboard world.  Their location is an affordance on the imported
        # map, so notes can be carried, posted, and read in the same geography
        # as every other village activity.
        self._square = self.eng.add_node("Square", {"name": "town square"})
        self._noticeboard = self.eng.add_node("Noticeboard", {"name": "town noticeboard"})
        self._square_fixtures = {}
        self.eng.add_edge_unchecked(self._town, "has_square", self._square)
        self.eng.add_edge_unchecked(self._square, "has_board", self._noticeboard)
        square_cell = self._map_layout.get("work", {}).get("market") if self._map_layout else None
        if square_cell in self._map_cells:
            self.eng.add_edge_unchecked(self._square, "at_cell", self._map_cells[square_cell])
            self.eng.add_edge_unchecked(self._noticeboard, "at_cell", self._map_cells[square_cell])
        self._install_square_fixtures()
        _dn.install(self)   # Phase 042: lamps and the lamplighter, when the pack switch is on

        # The canonical store is also a physical place on the integrated map.
        market = self._map_layout.get("work", {}).get("market") if self._map_layout else None
        if market in self._map_cells:
            self.eng.add_edge_unchecked(self._store, "at_cell", self._map_cells[market])
        self._seed_written_documents()
        for kind, quantity in self._scenario_data.get("stocks", {}).items():
            self.set_stock(str(kind), float(quantity))

    def _scenario_table(self, key, default):
        """Select named seeded concepts or accept inline concept bundles."""
        requested = self._scenario_data.get(key)
        if requested is None:
            return {item["name"]: item for item in default}
        by_name = {item["name"]: item for item in default}
        result = {}
        for item in requested:
            if isinstance(item, str) and item in by_name:
                result[item] = dict(by_name[item])
            elif isinstance(item, dict) and item.get("name"):
                result[str(item["name"])] = dict(item)
        return result

    def _install_physical_objects(self):
        """Install neutral scenario objects without assigning them a game.

        This is ordinary world inventory: a container may hold arbitrary
        objects, and nothing here knows what any collection is for. A held
        cognition frame may interpret the objects as a board game, tools,
        theatre props, or something else entirely.
        """
        # LA03: the object-location index is derived from this mapping. Start
        # clean here so construction and rebuilds share one maintenance path.
        self._physical_object_locations = _PhysicalObjectLocations()
        for spec in self._scenario_data.get("physical_objects", ()):
            if not isinstance(spec, dict):
                continue
            object_id = str(spec.get("id", spec.get("name", "object")))
            quantity = max(1, int(spec.get("quantity", 1)))
            names = list(spec.get("names", ()))
            if names:
                quantity = len(names)
            for index in range(quantity):
                suffix = names[index] if names else f"{object_id}:{index + 1}"
                node_id = str(names[index] if names else
                              (object_id if quantity == 1 else suffix))
                if node_id in self._physical_objects:
                    node_id = f"{object_id}:{index + 1}"
                attrs = {key: value for key, value in spec.items()
                         if key not in {"id", "name", "names", "quantity", "contains", "text_file"}}
                attrs.update({"object_id": node_id,
                              "name": names[index] if names else spec.get("name", object_id),
                              "kind": str(spec.get("kind", "object")),
                              "location": str(spec.get("location", "world"))})
                node = self.eng.add_node("PhysicalObject", attrs)
                self._physical_objects[node_id] = node
                if index == 0:
                    self._physical_object_aliases[object_id] = node_id
                self._physical_object_locations[node_id] = attrs["location"]
                container_id = spec.get("contains")
                container_key = self._physical_object_aliases.get(str(container_id), str(container_id))
                if container_id and container_key in self._physical_objects:
                    container = self._physical_objects[container_key]
                    self.eng.add_edge_unchecked(container, "contains_object", node)
                    self._physical_object_locations[node_id] = container_key
                    self.eng.set_attr(node, "location", container_key)

    def resolve_physical_object_id(self, object_id):
        """Resolve an authored object id to its concrete physical instance."""
        key = str(object_id)
        return self._physical_object_aliases.get(key, key)

    def physical_objects(self):
        """Return neutral physical object records for observation/debugging."""
        return [{"id": object_id, **dict(self.eng.node(node)["attrs"])}
                for object_id, node in self._physical_objects.items()
                if self.eng.has_node(node)]

    def _physical_object_accessible(self, actor, location, seen=(), object_id=None):
        location = str(location)
        # Scenario objects may opt into map-backed placement with `cell`,
        # `x`/`y`, or a containing object that has such a placement. Keep the
        # legacy room labels (`table`/`world`) global when no cell is authored.
        cell = (self._physical_location_cell(object_id)
                if object_id is not None else None) or self._physical_location_cell(location)
        if cell is not None:
            actor_cell = self.actor_position(actor)
            if actor_cell is None or self.distance(actor_cell, cell) is None \
                    or self.distance(actor_cell, cell) > 1:
                return False
        if location == actor or location in {"table", "world"}:
            return True
        if location in seen or location not in self._physical_objects:
            return False
        container_attrs = self.eng.node(self._physical_objects[location])["attrs"]
        if "open" in container_attrs and not bool(container_attrs.get("open")):
            return False
        parent = self._physical_object_locations.get(location)
        return parent is not None and self._physical_object_accessible(
            actor, parent, seen + (location,))

    def _physical_location_cell(self, location, seen=()):
        """Return an authored map cell for an object/actor location if present."""
        location = str(location)
        if location in seen:
            return None
        if location in self._actors:
            return self.actor_position(location)
        if location not in self._physical_objects:
            return None
        # Current containment/holding determines where an object is. Its
        # authored placement is only used while it sits at a shared location.
        parent = self._physical_object_locations.get(location)
        if parent in self._actors:
            return self.actor_position(parent)
        if parent in self._physical_objects:
            return self._physical_location_cell(parent, seen + (location,))
        attrs = self.eng.node(self._physical_objects[location])["attrs"]
        cell = attrs.get("cell")
        if isinstance(cell, (list, tuple)) and len(cell) == 2:
            try:
                return int(cell[0]), int(cell[1])
            except (TypeError, ValueError):
                return None
        if "x" in attrs and "y" in attrs:
            try:
                return int(attrs["x"]), int(attrs["y"])
            except (TypeError, ValueError):
                return None
        return None

    def physical_object_observations(self, actor):
        """Return the physical objects visible from an actor's location."""
        if actor not in self._actors:
            return []
        return [item for item in self.physical_objects()
                if self._physical_object_accessible(actor, item.get("location", "world"),
                                                    object_id=item["id"])]

    def _ensure_physical_object_locations(self):
        """Return the indexed object-location mapping, rebuilding when needed (LA03).

        A checkpoint decodes ``_physical_object_locations`` as a plain dict,
        and tests or scenario authors may replace it outright. Whenever the
        mapping is not the indexed subclass, or the object registry has grown
        or shrunk under it, the derived index is rebuilt from the current
        mapping (with the node's ``location`` attribute filling any missing
        entry). The index is never canonical state.
        """
        locations = self.__dict__.get("_physical_object_locations")
        if isinstance(locations, _PhysicalObjectLocations):
            if len(locations) != len(self._physical_objects):
                return self._rebuild_physical_object_locations(locations)
            return locations
        return self._rebuild_physical_object_locations(locations)

    def _rebuild_physical_object_locations(self, source=None):
        indexed = _PhysicalObjectLocations()
        if isinstance(source, dict):
            for object_id, location in source.items():
                indexed[str(object_id)] = str(location)
        for object_id, node in self._physical_objects.items():
            if object_id in indexed:
                continue
            attrs = self.eng.node(node)["attrs"]
            indexed[str(object_id)] = str(attrs.get("location", "world"))
        self._physical_object_locations = indexed
        return indexed

    @property
    def _physical_object_index(self):
        """location -> object ids, the LA03 derived index (read-only view)."""
        return self._ensure_physical_object_locations()._location_buckets

    def _visible_physical_object_records(self, actor):
        """Objects visible to ``actor`` with the same contents as the public scan.

        The location index gives a candidate set (the actor, the shared table
        and world, and everything contained under them). The existing
        accessibility predicate still decides reachability, so this agrees
        with ``physical_object_observations`` while avoiding a containment walk
        from every object in the world.
        """
        if actor not in self._actors:
            return []
        locations = self._ensure_physical_object_locations()
        queue = deque([str(actor), "table", "world"])
        seen_locations = set()
        candidates = set()
        while queue:
            location = str(queue.popleft())
            if location in seen_locations:
                continue
            seen_locations.add(location)
            for object_id in locations.ids_at(location):
                if object_id in candidates or object_id not in self._physical_objects:
                    continue
                candidates.add(object_id)
                # An object can itself be a container: walk its contents too.
                queue.append(object_id)
        records = []
        for object_id, node in self._physical_objects.items():
            if object_id not in candidates:
                continue
            attrs = self.eng.node(node)["attrs"]
            if self._physical_object_accessible(
                    actor, attrs.get("location", "world"), object_id=object_id):
                records.append({"id": object_id, **dict(attrs)})
        return records

    def _physical_object_capabilities(self, record):
        """The capability tags LA03 publishes for one visible object."""
        attrs = dict(record)
        kind = str(attrs.get("kind", "object"))
        spec = self._item_specs.get(kind, {})
        container = (kind in {"box", "tray", "container"}
                     or bool(attrs.get("container"))
                     or "open" in attrs)
        reachable = bool(attrs.get("_reachable", False))
        grabbable = reachable and not bool(attrs.get("fixed")) and kind not in {
            "fixture", "building", "door"}
        return {
            "reachable": reachable,
            "grabbable": grabbable,
            "container": bool(container),
            "open": bool(attrs.get("open", False)),
            "locked": bool(attrs.get("locked", False)),
            "edible": bool(spec.get("food") or attrs.get("edible")),
            "tool": bool(spec.get("class") == "tool" or attrs.get("tool")),
        }

    def move_physical_object(self, object_id, location):
        """Move an ordinary object; no game-specific admissibility is applied."""
        object_id = str(object_id)
        object_id = self.resolve_physical_object_id(object_id)
        if object_id not in self._physical_objects:
            return False
        # LA03: move through the indexed mapping so the object-location index
        # follows the canonical location assignment.
        self._ensure_physical_object_locations()
        node = self._physical_objects[object_id]
        old_location = self._physical_object_locations.get(object_id)
        if old_location in self._physical_objects:
            old_node = self._physical_objects[old_location]
            self.eng.remove_edge_unchecked(old_node, "contains_object", node)
        elif old_location in self._actors:
            self.eng.remove_edge_unchecked(self._actors[old_location],
                                           "holds_object", node)
        destination = self.resolve_physical_object_id(location)
        self._physical_object_locations[object_id] = str(destination)
        self.eng.set_attr(node, "location", str(destination))
        if str(destination) in self._physical_objects:
            self.eng.add_edge_unchecked(self._physical_objects[str(destination)],
                                        "contains_object", node)
        elif str(destination) in self._actors:
            self.eng.add_edge_unchecked(self._actors[str(destination)],
                                        "holds_object", node)
        return True

    def physical_object_affordances(self, actor, destinations=None):
        """Return generic ways for an actor to move accessible objects.

        This is intentionally a physical API, not an inventory for a
        particular activity.  The world exposes objects, their locations, and
        possible destinations; it does not label any movement as a purchase,
        trade, turn, payment, or other domain action.  A held frame may give
        these operations meaning later.

        ``table`` and ``world`` are shared physical locations, so objects
        there are observable to every actor.  Objects held by an actor are
        also observable to that actor.  Other shared locations can be passed
        explicitly through ``destinations`` without adding semantics to the
        world.
        """
        if actor not in self._actors:
            return []
        if destinations is None:
            # Self is a physical destination too: taking an accessible room
            # object into one's hands is movement, with no ownership ruling.
            destinations = list(self._actors)
            destinations += ["table", "world"]
            # A destination is another actor or an authored physical
            # container.  Ordinary objects remain movable, but the world
            # does not manufacture a pairwise destination for every object
            # in the room (which would turn a modest tabletop into a huge
            # Cartesian product).
            destinations += [item["id"] for item in self.physical_objects()
                             if item.get("kind") in {"box", "tray", "container"}
                             or item.get("container")]
        destinations = [str(destination) for destination in destinations]

        options = []
        for item in self.physical_objects():
            location = str(item.get("location", "world"))
            if not self._physical_object_accessible(actor, location, object_id=item["id"]):
                continue
            for destination in destinations:
                if destination == location:
                    continue
                if destination in self._actors:
                    here, there = self.actor_position(actor), self.actor_position(destination)
                    if (here is None or there is None or self.distance(here, there) is None
                            or self.distance(here, there) > 1):
                        continue
                elif destination not in {"table", "world"}:
                    if destination not in self._physical_objects:
                        continue
                    if not self._physical_object_accessible(
                            actor, destination, object_id=destination):
                        continue
                    destination_attrs = self.eng.node(
                        self._physical_objects[destination])["attrs"]
                    if ("open" in destination_attrs
                            and not bool(destination_attrs.get("open"))):
                        continue
                    # Do not publish moves that would create a containment cycle.
                    cursor, seen = destination, set()
                    cyclic = False
                    while cursor in self._physical_objects and cursor not in seen:
                        if cursor == item["id"]:
                            cyclic = True
                            break
                        seen.add(cursor)
                        cursor = self._physical_object_locations.get(cursor, "")
                    if cyclic:
                        continue
                options.append({
                    "action": "move_object",
                    "object_id": item["id"],
                    "destination": destination,
                    "object": item.get("name", item["id"]),
                    "kind": item.get("kind", "object"),
                    "source": location,
                })
            attrs = self.eng.node(self._physical_objects[item["id"]])["attrs"]
            if (item.get("kind") in {"box", "container", "tray"}
                    and "open" in attrs and not bool(attrs.get("open"))):
                options.append({
                    "action": "open_object",
                    "object_id": item["id"],
                    "object": item.get("name", item["id"]),
                    "kind": item.get("kind", "object"),
                    "source": location,
                    "score": 1.0,
                })
        return options

    def open_physical_object_as_actor(self, actor, object_id):
        """Open an authored physical container without interpreting contents."""
        if actor not in self._actors:
            return False
        object_id = self.resolve_physical_object_id(object_id)
        if object_id not in self._physical_objects:
            return False
        if not self._physical_object_accessible(
                actor, self._physical_object_locations.get(object_id, "world"),
                object_id=object_id):
            return False
        node = self._physical_objects[object_id]
        attrs = self.eng.node(node)["attrs"]
        if "open" not in attrs:
            return False
        self.eng.set_attr(node, "open", True)
        return True

    def move_physical_object_as_actor(self, actor, object_id, destination):
        """Apply one neutral object-movement proposal from an actor.

        Access policy is deliberately minimal here.  A scenario may model
        access through its own held concepts or a richer physical interface;
        this primitive only validates that the proposer is an actor and then
        moves the ordinary object.  In particular, it never interprets the
        destination as ownership or the movement as a transaction.
        """
        if actor not in self._actors:
            return self._refuse("unknown_target")
        object_id = self.resolve_physical_object_id(object_id)
        if object_id not in self._physical_objects:
            return self._refuse("unknown_target")
        source = self._physical_object_locations.get(object_id, "world")
        if not self._physical_object_accessible(actor, source, object_id=object_id):
            return self._refuse("not_in_reach")
        destination = self.resolve_physical_object_id(destination)
        if destination not in {"table", "world", *self._actors} \
                and destination not in self._physical_objects:
            return self._refuse("unknown_target")
        if destination in self._physical_objects:
            # A container cannot be moved inside itself or any of its own
            # descendants; reject before changing either location index.
            cursor = destination
            seen = set()
            while cursor in self._physical_objects and cursor not in seen:
                if cursor == object_id:
                    return self._refuse("invalid_destination")
                seen.add(cursor)
                cursor = self._physical_object_locations.get(cursor, "")
        if destination in self._physical_objects and not self._physical_object_accessible(
                actor, destination):
            return self._refuse("not_in_reach")
        # A coordinate-backed source or destination makes the handover
        # spatial. Both endpoints must be within one walkable step of the actor.
        actor_cell = self.actor_position(actor)
        endpoint_cells = [self._physical_location_cell(object_id),
                          self._physical_location_cell(source)]
        if destination in self._physical_objects:
            endpoint_cells.append(self._physical_location_cell(destination))
        elif destination in self._actors:
            endpoint_cells.append(self.actor_position(destination))
        if any(cell is not None for cell in endpoint_cells):
            for cell in endpoint_cells:
                if cell is not None and (actor_cell is None
                        or self.distance(actor_cell, cell) is None
                        or self.distance(actor_cell, cell) > 1):
                    return self._refuse("not_in_reach")
        # A carried/contained object's authored cell is its last shared-place
        # position. Persist the current physical position when it is dropped
        # into a shared room location so later reach checks use the drop site.
        if destination in {"table", "world"}:
            drop_cell = self._physical_location_cell(object_id)
            if drop_cell is None:
                drop_cell = self._physical_location_cell(source)
            if drop_cell is not None:
                self.eng.set_attr(self._physical_objects[object_id], "cell",
                                  list(drop_cell))
        return self.move_physical_object(object_id, destination)

    def _install_square_fixtures(self):
        """Install the market and civic fixtures at the scenario's square."""
        square = self._map_layout.get("square", {}) if self._map_layout else {}
        center = tuple(square.get("center", ()))
        if len(center) != 2:
            return
        for fixture in self.E.TOWN_SQUARE_FIXTURES:
            offset = fixture.get("offset", (0, 0))
            cell = (int(center[0]) + int(offset[0]), int(center[1]) + int(offset[1]))
            node = self.eng.add_node("SquareFixture", {
                "name": fixture["name"], "kind": fixture["kind"],
                "goods": tuple(fixture.get("goods", ())),
                "x": float(cell[0]), "y": float(cell[1]),
            })
            self.eng.add_edge_unchecked(self._square, "has_fixture", node)
            if cell in self._map_cells:
                self.eng.add_edge_unchecked(node, "at_cell", self._map_cells[cell])
            self._square_fixtures[fixture["name"]] = node

    def _run(self, *, force=False):
        # EN03: inside a turn batch a primitive action records that a full
        # sweep is owed instead of running one per action.  The finish boundary
        # calls ``_run(force=True)``; ``batch_rules`` runs the single owed sweep
        # if the caller exits without one.
        if not force and self._rule_batch_depth > 0:
            self._rule_batch_pending = True
            return
        # A stock node survives after its last batch spoils, so an empty pile
        # may retain condition=0.  Treat the next batch as newly made rather
        # than allowing the spoil rule to discard it in the same rule sweep.
        for kind, node in self._stock.items():
            attrs = self.eng.node(node)["attrs"]
            if float(attrs.get("qty", 0.0)) <= 0.0 and attrs.get("perishable", 0.0) == 1.0:
                self.eng.set_attr(node, "condition", 1.0)
        # Bigville owns the executable part of the graph contract.  The graph
        # is intentionally only a data store; these small passes are the
        # ported world mechanics that used to be supplied by graph rules.
        self._resolve_jobs()
        self._resolve_actor_events()
        self._resolve_body_stats()
        self._resolve_sleep()
        self._resolve_intoxication()
        self._resolve_clothing_and_bodies()
        self._resolve_period_effects()
        # Freshness is mixed in where stock arrives (set_stock and the transfers), so a pile that gained
        # quantity keeps its blended condition. Only the quantity bookkeeping remains here.
        for kind, node in self._stock.items():
            attrs = self.eng.node(node)["attrs"]
            qty = float(attrs.get("qty", 0.0))
            if qty < 0.0:
                self.eng.set_attr(node, "qty", 0.0)
                qty = 0.0
            self._last_stock_qty[kind] = qty
        self._record_unlogged_deaths()
        self._rule_batch_pending = False

    @contextmanager
    def batch_rules(self):
        """Defer primitive ``_run()`` sweeps until one authoritative finish sweep.

        Re-entrant: nested scopes share the outer batch.  Only the outermost
        exit runs the owed sweep (when no caller forced one), so a normal
        turn still runs exactly one full pass after its actions.  Exceptions
        propagate unchanged; the depth is always balanced, and an exception
        leaves ``_rule_batch_pending`` set so the next scope settles it.
        """
        self._rule_batch_depth += 1
        try:
            yield self
        finally:
            self._rule_batch_depth -= 1
        if self._rule_batch_depth == 0 and self._rule_batch_pending:
            self._run(force=True)

    @property
    def rules_pending(self) -> bool:
        """True when a batched turn owes its authoritative ``_run()`` sweep."""
        return bool(self._rule_batch_pending)

    def _request_rule_sweep(self, *, force=False):
        """Ask for a rule sweep without invoking ``_run`` inside an open batch.

        Primitive actions use this instead of calling ``_run`` directly, so the
        measured sweep count stays constant in turn mode.  ``_run`` retains the
        same guard for any direct caller.
        """
        if not force and self._rule_batch_depth > 0:
            self._rule_batch_pending = True
            return
        self._run(force=force)

    def _job_input(self, job, kind, is_item=False):
        """Find one physical input for a job without inventing ownership."""
        if not is_item:
            return None
        for item in self.eng.neighbours(self._town, "has_tool_item"):
            if self.eng.node(item)["attrs"].get("kind") == kind:
                return item
        for actor in self._actors.values():
            for edge in ("holds_in_hand", "holds_tableware", "holds"):
                for item in self.eng.neighbours(actor, edge):
                    if self.eng.node(item)["attrs"].get("kind") == kind:
                        return item
        return None

    def _resolve_jobs(self):
        """Complete generic data-defined actions and consume their inputs."""
        for job in list(self.eng.nodes("Job")):
            if not self.eng.has_node(job):
                continue
            ja = self.eng.node(job)["attrs"]
            if float(ja.get("complete", 0.0)) == 1.0:
                continue
            # Phase 023: a job advances, completes and spends stamina only while its worker stands on the
            # cell where the job started. A paused job keeps its materials and its remaining ticks.
            paused = self._job_away(job)
            self._set_job_paused(str(ja.get("canonical_actor", "")), paused)
            if paused:
                continue
            remaining = float(ja.get("remaining", 0.0))
            if remaining > 0.0:
                if not self._job_tick_armed:
                    continue
                # Phase 024: a tired worker advances the job at the movement speed (1, 2/3, 1/3 of a tick),
                # and a worker too exhausted to walk does not advance it. The stamina is not spent then.
                speed = self._job_speed(job) / float(self._jobs_sharing(job))     # Phase 049: shared among open jobs
                if speed <= 0.0:
                    continue
                # Phase 050b: a job's pace multiplies its progress per tick (1.0 is the committed rate).
                pace = float(ja.get("pace", 1.0))
                # Phase 048: the tools' fitness sets this tick's progress (1.0 for the right tool at full quality and
                # condition, so the committed time is unchanged). The stamina spent follows the progress made.
                fit = self._refresh_job_fit(job, speed * pace)
                # Phase 049: a worker weaker than the recipe's strength demand progresses more slowly (1.0 at or above it).
                rate = self._job_strength_rate(job, speed * pace * fit)
                # Phase 047: the workers present (a crew) multiply the labour; each helper pays its share of the stamina.
                own = speed * pace * fit * rate
                remaining -= own * self._crew_factor(job)
                self.eng.set_attr(job, "remaining", max(0.0, remaining))
                # The recipe's stamina cost is spread evenly over the ticks of the job (Phase 022), and over
                # the progress it makes (Phase 024): a slowed worker spends less per tick.
                self._spend_job_stamina(job, share=own)
                self._crew_spend(job, own)
                if remaining > 1e-9:
                    continue
                remaining = 0.0
            asp_nodes = self.eng.neighbours(job, "runs")
            if not asp_nodes:
                continue
            # Phase 048: an instant job (or the tick that finished a timed one) reads the fitness of its tools now.
            self._refresh_job_fit(job, 0.0)
            asp = asp_nodes[0]
            action = self.eng.node(asp)["attrs"]
            # Plan every input before changing anything. Each bulk unit comes from the worker's own
            # stock, then an accessible container at their cell, then the store (see `_plan_inputs`).
            # An unfulfilled job stays busy and can be completed after the missing good arrives.
            job_actor = str(ja.get("canonical_actor", ""))
            # Phase 048: a missing tool is not a stall. The job uses the tool its worker has, or bare hands (see
            # _job_tool_item and _refresh_job_fit), so it goes on at the fitness those hands give.
            need_specs = []
            for need in self.eng.neighbours(job, "need"):
                na = self.eng.node(need)["attrs"]
                need_specs.append((need, na.get("kind", ""), float(na.get("qty", 0.0)),
                                   float(na.get("is_item", 0.0)) == 1.0, na.get("slot_type", "")))
            plans = self._plan_inputs(job_actor, [(k, q, i, s) for _, k, q, i, s in need_specs])
            missing = plans is None
            # A burial job waits (armed, its inputs kept) until the worker stands in the graveyard and the
            # bury job's grave and body are still there.
            if not missing and not (self._at_recipe_building(job_actor, action.get("name", ""))
                                    and self._burial_ready(action.get("name", ""))):
                missing = True
            # Phase 030: a job that puts goods or waste into the town store waits while its worker has no access to it.
            writes_store = ((bool(action.get("out_kind", "")) and float(action.get("out_discrete", 0.0)) != 1.0)
                            or bool(self._recipe_specs.get(action.get("name", ""), {}).get("byproducts"))
                            or (plans is not None and any(mode == "type" for mode, _ in plans)))
            if not missing and writes_store and not self._store_open(job_actor):
                missing = True
            if missing:
                continue
            # Any stamina the job has not yet spent is charged at completion (an instant `do` spends all of it here).
            self._spend_job_stamina(job, final=True)
            # Read component quality before consuming those physical nodes.
            actor_name = str(ja.get("canonical_actor", ""))
            actor_node = self._actors.get(actor_name)
            recipe_row = self._recipe_specs.get(action.get("name", ""), {})
            quality = self.recipe_skill_level(actor_name, recipe_row) if actor_node else 0.0
            part_qualities = [float(self.eng.node(detail)["attrs"].get("quality", quality))
                              for mode, detail in plans
                              if mode == "item" and self.eng.has_node(detail)]
            for (need, kind, qty, _is_item, slot_type), (mode, detail) in zip(need_specs, plans):
                if mode == "bulk":
                    self._take_draws(job_actor, kind, detail)
                    self._record_drawn_from(need, [(kind, src, units) for src, units in detail])
                elif mode == "type":
                    used, entries = {}, []
                    for member, draws in detail:
                        self._take_draws(job_actor, member, draws)
                        used[member] = sum(units for _, units in draws)
                        entries += [(member, src, units) for src, units in draws]
                    self._record_drawn_from(need, entries)
                    for byproduct, amount in self.E.type_byproducts(slot_type, qty).items():
                        self.set_stock(byproduct, self.qty(byproduct) + amount)
                    # record which members filled the slot, for inspection
                    self.eng.set_attr(need, "filled_with",
                                      ";".join(f"{k}:{round(v, 4)}" for k, v in used.items()))
                else:
                    item = detail
                    self.eng.remove_edge_unchecked(self._town, "has_tool_item", item)
                    for owner in list(self._actors.values()):
                        for edge in ("holds_in_hand", "holds_tableware", "holds"):
                            self.eng.remove_edge_unchecked(owner, edge, item)
                    self.eng.remove_node(item)
            if part_qualities:
                quality = min([quality] + part_qualities)
            # Phase 050b: the pace moves the batch's quality and its yield; a batch the pace spoils yields nothing.
            from worlds import resolution as R
            table = self.E.RESOLUTION
            quality_at_reference = quality
            quality = R.pace_quality(quality, float(ja.get("pace", 1.0)), table["haste_penalty"])
            spoiled = R.ruined(quality, quality_at_reference, table["ruin_below"])
            # Phase 048: the lowest tool fitness over the job lowers the quality and the yield; below waste_below the
            # batch is wasted, so its inputs are gone and it yields nothing. The right tool at full condition leaves both.
            fit_low = float(self.eng.node(job)["attrs"].get("fit_low", 1.0))
            quality = R.fit_quality(quality, fit_low, table["fit_quality_loss"])
            wasted = R.fit_wasted(fit_low, table["waste_below"])
            out_kind = action.get("out_kind", "")
            out_qty = float(action.get("out_qty", 0.0)) * R.pace_yield(float(ja.get("pace", 1.0)),
                                                                        table["haste_yield_loss"])
            out_qty *= R.fit_yield(fit_low, table["waste_below"])
            # Phase 049: a worker below the recipe's skill floor gets the share of the batch the skill reaches, and
            # below skill_ruin_ratio of the floor the batch is spoiled. A seasonal recipe worked out of its season
            # yields off_season_yield of its batch.
            skill_share = self._skill_share_of_floor(actor_name, action.get("name", "")) if actor_node else 1.0
            if skill_share < float(table["skill_ruin_ratio"]):
                spoiled = True
            out_qty *= min(1.0, skill_share)
            out_qty *= float(ja.get("season_yield", 1.0))     # Phase 049: the season the batch was started in
            if spoiled:
                self.eng.set_attr(job, "ruined", 1.0)
                self.create_event("batch_spoiled", subject=job_actor,
                                  detail=f"{job_actor}'s {action.get('name', '')} batch spoiled from being rushed.",
                                  observer=job_actor, severity=0.1)
            elif wasted:
                self.create_event("batch_wasted", subject=job_actor,
                                  detail=f"{job_actor}'s {action.get('name', '')} batch was wasted: the tool did not fit.",
                                  observer=job_actor, severity=0.1)
            elif float(action.get("out_discrete", 0.0)) == 1.0:
                item_attrs = {"kind": out_kind, "weight": self.item_weight(out_kind),
                              "quality": quality, "condition": 1.0, "broken": 0.0,
                              "wear": 0.0, "decay": float(action.get("decay", 0.0)),
                              "use_armed": 0.0, "repair_armed": 0.0}
                item = self.eng.add_node("ToolItem", item_attrs)
                self.eng.add_edge_unchecked(self._town, "has_tool_item", item)
                fit = self.eng.add_node("ToolFit", {"mult": float(action.get("base_mult", 1.0)) * quality})
                self.eng.add_edge_unchecked(item, "fit_for", fit)
                self._items[out_kind] = self._items.get(out_kind, item)
                if out_kind in self._item_specs and self._item_specs[out_kind].get("container"):
                    # The same physical item can later be promoted to a store.
                    pass
            elif out_kind:
                self.set_stock(out_kind, self.qty(out_kind) + out_qty)
            for kind, qty in ({} if spoiled or wasted else self._recipe_specs.get(action.get("name", ""), {})
                              .get("byproducts", {})).items():
                self.set_stock(kind, self.qty(kind) + float(qty))      # e.g. bran from milling
            own_tools = bool(self._recipe_specs.get(action.get("name", ""), {}).get("open"))
            for tool_use in self.eng.neighbours(job, "uses"):
                kind = self.eng.node(tool_use)["attrs"].get("kind")
                # Phase 048: the tool the job used (its own, the one it was given, or none for bare hands).
                tool = (self._job_tool_item(job, actor_name, kind, own_tools)
                        if actor_name in self._actors else None)
                if tool is not None:
                    ta = self.eng.node(tool)["attrs"]
                    self._wear_tool(tool, float(ta.get("wear", 0.02)))
            burial = self._recipe_specs.get(action.get("name", ""), {}).get("burial")
            if burial and not wasted:                       # Phase 048: a wasted dig leaves no grave
                self._enact_burial(job_actor, burial)
            self.eng.set_attr(job, "complete", 1.0)
            self.eng.set_attr(job, "remaining", 0.0)
            if actor_node is not None:
                practised = self.E.recipe_skill(recipe_row) if recipe_row else None
                if practised:
                    log = dict(self.eng.node(actor_node)["attrs"].get("skill_practice", {}))
                    log[practised] = log.get(practised, 0.0) + float(action.get("time_minutes", 0.0))
                    self.eng.set_attr(actor_node, "skill_practice", log)
                    if (self.E.skill_learning(practised) == "cognitive"
                            and not self.physical_subsystems.get("cognitive_practice", False)):
                        # The world does not model this learning, so the practice goes to the actor.
                        self.record_observation(actor_name, "practice", skill=practised,
                                                minutes=float(action.get("time_minutes", 0.0)),
                                                learning="cognitive", recipe=action.get("name", ""),
                                                turn=int(self._turn),
                                                day=float(self.calendar().get("day") or 0.0))
                self.eng.remove_edge_unchecked(actor_node, "on_job", job)
                # Phase 049: a worker stays busy while another of their jobs is open.
                self.eng.set_attr(actor_node, "busy", 1.0 if self._job_of(actor_name) is not None else 0.0)
                self._set_job_paused(actor_name, self.job_paused(actor_name))

    def _resolve_actor_events(self):
        """Apply event nodes armed by the public convenience APIs."""
        for actor, node in self._actors.items():
            attrs = self.eng.node(node)["attrs"]
            # Container filling/emptying is a physical transfer armed by the
            # public API.  It is intentionally separate from ``put``: setup
            # fixtures can move town stock, while residents put held stock.
            if float(attrs.get("fill_armed", 0.0)) == 1.0:
                kind, amount = attrs.get("fill_kind", ""), float(attrs.get("fill_amount", 0.0))
                container = next((name for name, (cn, _) in self._containers.items()
                                  if self._container_accessible(actor, name)
                                  and self.actor_position(actor) == self.container_position(name)
                                  and (kind in self._containers[name][1])), None)
                # Setup containers without a mapped location are also valid.
                if container is None:
                    container = next((name for name, (cn, _) in self._containers.items()
                                      if self._container_accessible(actor, name)
                                      and kind in self._containers[name][1]
                                      and self.container_position(name) is None), None)
                if container is not None and amount > 0.0 and self.qty(kind) >= amount and self._store_open(actor):
                    max_load = float(self.eng.node(self._containers[container][0])["attrs"].get("max_load", 1e18))
                    if (self.used_volume(container) + amount * self.item_volume(kind) <= self.capacity(container) + 1e-9
                            and self.contents_weight(container) + amount * self.item_weight(kind) <= max_load + 1e-9
                            and (not self.is_fluid(kind) or float(self.eng.node(self._containers[container][0])["attrs"].get("watertight", 0.0)) == 1.0)):
                        inner = self._containers[container][1][kind]
                        self._mix_freshness(inner, amount, self._pile_condition(self._stock.get(kind)))
                        self.set_stock(kind, self.qty(kind) - amount)
                        self.eng.set_attr(inner, "qty", self.contents(container, kind) + amount)
                        self._record_handover("fill", kind, amount, ("store", "store"), ("container", str(container)))
                self.eng.set_attr(node, "fill_armed", 0.0)
            if float(attrs.get("empty_armed", 0.0)) == 1.0:
                kind, amount = attrs.get("empty_kind", ""), float(attrs.get("empty_amount", 0.0))
                for container, (cn, inners) in self._containers.items():
                    if kind not in inners or not self._container_accessible(actor, container):
                        continue
                    if not self._store_open(actor):
                        break
                    amount = min(amount, self.contents(container, kind))
                    arriving = self._pile_condition(inners[kind])
                    self.eng.set_attr(inners[kind], "qty", self.contents(container, kind) - amount)
                    self.set_stock(kind, self.qty(kind) + amount, condition=arriving)
                    if amount > 0.0:
                        self._record_handover("empty", kind, amount, ("container", str(container)), ("store", "store"))
                    break
                self.eng.set_attr(node, "empty_armed", 0.0)
            if float(attrs.get("lock_armed", 0.0)) == 1.0:
                for container, (cn, _) in self._containers.items():
                    ca = self.eng.node(cn)["attrs"]
                    if (float(ca.get("lock_id", 0.0))
                            and (self.container_position(container) is None
                                 or self.actor_position(actor) == self.container_position(container))):
                        self.eng.set_attr(cn, "locked", 1.0); break
                self.eng.set_attr(node, "lock_armed", 0.0)
            if float(attrs.get("unlock_armed", 0.0)) == 1.0:
                for container, (cn, _) in self._containers.items():
                    ca = self.eng.node(cn)["attrs"]
                    lock_id = float(ca.get("lock_id", 0.0))
                    has_key = any(float(self.eng.node(key)["attrs"].get("opens", 0.0)) == lock_id
                                  for key in self.eng.neighbours(node, "holds_key"))
                    if (has_key and (self.container_position(container) is None
                                     or self.actor_position(actor) == self.container_position(container))):
                        self.eng.set_attr(cn, "locked", 0.0); break
                self.eng.set_attr(node, "unlock_armed", 0.0)
            for edge in ("exerted", "rested"):
                for event in self.eng.neighbours(node, edge):
                    ea = self.eng.node(event)["attrs"]
                    if float(ea.get("cost_done", ea.get("rest_done", 0.0))) == 1.0:
                        continue
                    body = self._bodies.get(actor)
                    if body is None:
                        continue
                    ba = self.eng.node(body)["attrs"]
                    if edge == "exerted":
                        # bd_exert_cost (Phase 022): hungrier residents tire faster, and exertion makes you hungrier.
                        # Hunger is scaled by starve_limit so a resident at starvation spends twice the declared cost.
                        cost = float(ea.get("stamina_cost", 0.0))
                        starve = float(attrs.get("starve_limit", self.E.CARE["starve_limit"]))
                        hunger = float(attrs.get("hunger", 0.0))
                        if starve > 0.0:
                            cost *= 1.0 + hunger / starve
                        reserve = float(ba.get("stamina_reserve", 1.0))
                        spent = min(reserve, max(0.0, cost))
                        self.eng.set_attr(body, "stamina_reserve", max(0.0, reserve - spent))
                        self.eng.set_attr(node, "hunger", hunger + spent * float(self.E.HUNGER_PER_STAMINA))
                        self.eng.set_attr(ea and event, "cost_done", 1.0)
                        # bd_train_strength / bd_train_stamina (Phase 032): the effort trains what it uses, once.
                        if self.physical_subsystems.get("training", True):
                            self._train_from_effort(body, event)
                    else:
                        amount = float(ea.get("amount", 1.0))
                        self.eng.set_attr(body, "stamina_reserve",
                                          min(self.effective_stamina(actor), float(ba.get("stamina_reserve", 1.0)) + amount * float(self.E.REST_RECOVERY_PER_UNIT)))
                        self.eng.set_attr(event, "rest_done", 1.0)

            for option in self.eng.neighbours(node, "has_option"):
                pass

    def _resolve_clothing_and_bodies(self):
        town = self.eng.node(self._town)["attrs"]
        for actor, node in self._actors.items():
            attrs = self.eng.node(node)["attrs"]
            warmth = rain = finery = 0.0
            for garment in self.eng.neighbours(node, "wears"):
                ga = self.eng.node(garment)["attrs"]
                warmth += float(ga.get("warmth", 0.0)); rain += float(ga.get("rain", 0.0)); finery += float(ga.get("finery", 0.0))
            self.eng.set_attr(node, "warmth", warmth); self.eng.set_attr(node, "rain_cover", rain); self.eng.set_attr(node, "finery", finery)
            unheated = self._household_unheated_share(attrs.get("household"))
            self.eng.set_attr(node, "chill", max(0.0, float(town.get("cold", 0.0)) - warmth)
                              + unheated * float(self.E.HEATING["unheated_chill"]))
            self.eng.set_attr(node, "soaked", max(0.0, float(town.get("wet", 0.0)) - rain))
            for garment in self.eng.neighbours(node, "wears"):
                if float(self.eng.node(garment)["attrs"].get("dye_armed", 0.0)) == 1.0:
                    dye_nodes = self.eng.neighbours(garment, "dyed_with")
                    if dye_nodes:
                        colour = self.eng.node(dye_nodes[0])["attrs"].get("kind", "")
                        colour = self._item_specs.get(colour, {}).get("colour", colour)
                        self.eng.set_attr(garment, "colour", colour)
                    self.eng.set_attr(garment, "dye_armed", 0.0)
        for tool in self.eng.nodes("ToolItem"):
            ta = self.eng.node(tool)["attrs"]
            if float(ta.get("use_armed", 0.0)) == 1.0:
                condition = max(0.0, float(ta.get("condition", 1.0)) - float(ta.get("wear_rate", 0.1)))
                self.eng.set_attr(tool, "condition", condition); self.eng.set_attr(tool, "broken", 1.0 if condition <= 0 else 0.0); self.eng.set_attr(tool, "use_armed", 0.0)
                for fit in self.eng.neighbours(tool, "fit_for"):
                    self.eng.set_attr(fit, "mult", float(self._item_specs.get(ta.get("kind", ""), {}).get("base_mult", 1.0)) * float(ta.get("quality", 0.0)) * condition)
            if float(ta.get("repair_armed", 0.0)) == 1.0:
                self.eng.set_attr(tool, "condition", 1.0); self.eng.set_attr(tool, "broken", 0.0); self.eng.set_attr(tool, "repair_armed", 0.0)

    def _resolve_period_effects(self):
        period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        if period <= self._resolved_period:
            return
        steps = int(period - self._resolved_period)
        self._resolved_period = period
        for _ in range(steps):
            if self.physical_subsystems["metabolism"]:
                # Fed = the animal ate since the last period (its hunger is zero before this period's
                # metabolism adds one). Breeding uses this, not the hunger after the period.
                fed = {name: float(self.eng.node(node)["attrs"].get("hunger", 0.0)) <= 0.0
                       for name, node in self._animals.items() if self.animal_alive(name)}
                for name, node in self._animals.items():
                    aa = self.eng.node(node)["attrs"]
                    if float(aa.get("alive", 0.0)) != 1.0:
                        continue
                    # Metabolism changes the animal's condition only. Feed is
                    # consumed by an explicit animal action at an accessible pile.
                    hunger = float(aa.get("hunger", 0.0)) + 1.0
                    self.eng.set_attr(node, "hunger", hunger)
                    if hunger >= float(aa.get("starve_limit", 3.0)):
                        self._record_animal_death(node, "starvation")
                for actor, node in self._actors.items():
                    aa = self.eng.node(node)["attrs"]
                    if float(aa.get("alive", 0.0)) != 1.0:
                        continue
                    hunger = float(aa.get("hunger", 0.0)) + 1.0
                    self.eng.set_attr(node, "hunger", hunger)
                    # Phase 035: the protein store, deficiency and satiety settle once per period (seeds nu_metabolize).
                    self._nutrition_period(actor)
                    if hunger > float(aa.get("starve_limit", self.E.CARE["starve_limit"])):
                        # Phase 037: starvation is acute harm each period past the limit (HEALTH.starve_harm).
                        self.harm(actor, float(self.E.HEALTH["starve_harm"]), "starvation")
                self._collect_night_soil()
                self._burn_household_heat()
                self._advance_animal_life(fed)
            if self.physical_subsystems["ecology"]:
                self._advance_soil_nitrogen()
                for crop in list(self._living_crops()):
                    ca = self.eng.node(crop)["attrs"]
                    if float(ca.get("season_fail", 0.0)) == 1.0:
                        # Phase 049: a crop sown out of its season fails to the season's weather at the next period.
                        self.eng.set_attr(crop, "alive", 0.0)
                        continue
                    if float(ca.get("water_armed", 0.0)) == 1.0:
                        self.eng.set_attr(crop, "thirst", 0.0); self.eng.set_attr(crop, "water_armed", 0.0)
                    else:
                        thirst = float(ca.get("thirst", 0.0)) + 1.0; self.eng.set_attr(crop, "thirst", thirst)
                        if thirst > float(ca.get("wilt", 2.0)):
                            self.eng.set_attr(crop, "alive", 0.0)
                    if self.crop_alive(crop):
                        self.eng.set_attr(crop, "age", float(ca.get("age", 0.0)) + 1.0)
                        self._crop_draw_nitrogen(crop)
            # Freshness/condition is a property of the physical pile.  A
            # storage class changes the rate, never admissibility.
            if self.physical_subsystems["decay"]:
                for stock in self.eng.nodes("Stock"):
                    sa = self.eng.node(stock)["attrs"]
                    if float(sa.get("perishable", 0.0)) != 1.0 or float(sa.get("qty", 0.0)) <= 0.0:
                        continue
                    rate = float(sa.get("decay", 0.0)) * float(sa.get("storage_factor", 1.0))
                    condition = max(0.0, float(sa.get("condition", 1.0)) - rate)
                    self.eng.set_attr(stock, "condition", condition)
                    # A pile that reaches condition 0 is spoiled, not deleted (Phase 027): it stays,
                    # is graded when eaten, and leaves with the waste path. Its quantity is kept.
                for item in self.eng.nodes("ToolItem"):
                    ia = self.eng.node(item)["attrs"]
                    kind = ia.get("kind", "")
                    if kind in self._item_specs:
                        decay = self.E.decay_rate(kind)
                        if decay:
                            self.eng.set_attr(item, "condition", max(0.0, float(ia.get("condition", 1.0)) - decay))
                            if float(self.eng.node(item)["attrs"].get("condition", 0.0)) <= 0.0:
                                self.eng.set_attr(item, "broken", 1.0)
            if self.physical_subsystems.get("practice", False):
                self._consolidate_practice()
            for name, callback in self._physical_subsystem_extensions.items():
                if self.physical_subsystems.get(name, False):
                    callback(self, 1)
            # Apprenticeship and schooling remain physical/social
            # relationships. Period advancement must not infer a learner's
            # understanding or change held capability; that choice belongs to
            # the resident's cognitive backend.
            # ``attends`` and ``apprenticed_to`` remain observable relation
            # edges. No period effect is applied to either learner here.

    def _cleanup_village_transients(self):
        """Bound graph growth from completed work and old turn bookkeeping.

        Jobs are execution state, not durable world records.  The generic
        action rules detach a completed job from its actor, but deliberately
        leave the graph nodes behind so the low-level engine stays data-only.
        A long-running seeded village needs the adapter to retire those
        detached jobs, their copied checklists, and old major-action records.
        Durable notes, requests, observations, and resident concepts are not
        touched.
        """
        for job in list(self.eng.nodes()):
            if not self.eng.has_node(job):
                continue
            if self.eng.node(job)["type"] != "Job":
                continue
            if self.eng.in_neighbours(job, "on_job"):
                continue
            for need in list(self.eng.neighbours(job, "need")):
                if self.eng.has_node(need):
                    self.eng.remove_node(need)
            for tool_use in list(self.eng.neighbours(job, "uses")):
                if self.eng.has_node(tool_use):
                    self.eng.remove_node(tool_use)
            if self.eng.has_node(job):
                self.eng.remove_node(job)

        # Keep a short recent action history per actor.  The action itself is
        # already reflected in the actor's held attributes and the produced
        # stock; retaining thousands of identical scheduler records makes a
        # seasonal soak needlessly expensive.
        keep = 32
        for actor, records in self._turn_actions.items():
            stale = records[:-keep]
            self._turn_actions[actor] = records[-keep:]
            for record in stale:
                if self.eng.has_node(record):
                    self.eng.remove_node(record)

    def _seed_written_documents(self):
        """Mint the founding written records without turning them into town facts."""
        for kind, table in (("policy", self._policy_specs), ("law", self._law_specs),
                            ("charter", self._charter_specs)):
            for name, bundle in table.items():
                if (kind, name) in self._documents:
                    continue
                doc = self.eng.add_node("WrittenDocument", {
                    "name": name, "kind": kind, "title": bundle["title"],
                    "scope": bundle["scope"], "version": 1.0,
                    "origin": bundle.get("origin", "bigville"),
                    "immutable": 1.0 if bundle.get("immutable", False) else 0.0,
                    "enforcement": bundle.get("enforcement", "bigville"),
                    "seeded": 1.0, "author": bundle.get("origin", "bigville")})
                self.eng.add_edge_unchecked(self._town, "has_document", doc)
                self._documents[(kind, name)] = doc

    # ---------------------------------------------------- integrated map and spatial affordances
    def _install_map(self, seed, scenario_map=None):
        """Install canonical Map/Cell data from the village or a scenario map."""
        from worlds.bigville_town100_world import build_town_100
        from worlds.bigville_sim_world import SOLID as SOLID_TILES, TILE_NAME
        if scenario_map is None and self.E.FOUNDING_MAP:
            grid, affordances, layout = build_town_100(seed, self.E)
        elif scenario_map is None:
            # A pack with no founding town has no founding map: no tiles, no sites, no deposits.
            grid, affordances, layout = [], [], {}
        else:
            terrain_codes = {"grass": 0, "path": 1, "wall": 2, "floor": 3,
                             "square": 4, "tree": 5, "water": 6}
            source_grid = scenario_map.get("grid", [])
            grid = []
            for row in source_grid:
                converted = []
                for tile in row:
                    if isinstance(tile, str):
                        converted.append(terrain_codes.get(tile, 0))
                    else:
                        converted.append(int(tile))
                if converted:
                    grid.append(converted)
            if not grid or any(len(row) != len(grid[0]) for row in grid):
                raise ValueError("scenario map grid must be a non-empty rectangular matrix")
            layout = dict(scenario_map.get("layout", {}))
            layout.setdefault("w", len(grid[0]))
            layout.setdefault("h", len(grid))
            layout.setdefault("work", {})
            layout["work"] = {name: tuple(cell) if isinstance(cell, list) else cell
                               for name, cell in layout["work"].items()}
            layout.setdefault("homes", [])
            affordances = [dict(affordance) for affordance in scenario_map.get("affordances", [])]
        self._map_grid, self._map_layout = grid, layout
        self._map_node = self.eng.add_node("Map", {"name": f"{self._scenario_data.get('name', 'Bigville')} map", "seed": float(seed),
                                                     "width": float(layout.get("w", 0)), "height": float(layout.get("h", 0))})
        self.eng.add_edge_unchecked(self._town, "has_map", self._map_node)
        solid = set(SOLID_TILES)
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                terrain = TILE_NAME.get(tile, "grass")
                movement = self.E.TERRAIN_MOVEMENT.get(terrain, self.E.TERRAIN_MOVEMENT["grass"])
                walkable = tile not in solid
                cell = self.eng.add_node("MapCell", {"x": float(x), "y": float(y), "tile": float(tile),
                                                      "terrain": terrain,
                                                      # The terrain this cell was SEEDED as, and how
                                                      # far footfall has carried it toward the terrain
                                                      # `TERRAIN_WEAR` says it wears into. `terrain`
                                                      # above is the read-off of the two.
                                                      "base_terrain": terrain,
                                                      "wear": 0.0,
                                                      "speed": float(movement["speed"]),
                                                      "move_time": float(movement["move_time"]),
                                                      "stamina_multiplier": float(movement["stamina_multiplier"]),
                                                      "walkable": 1.0 if walkable else 0.0})
                self.eng.add_edge_unchecked(self._map_node, "has_cell", cell)
                if walkable:
                    self._map_cells[(x, y)] = cell
        for (x, y), cell in self._map_cells.items():
            for pt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if pt in self._map_cells:
                    self.eng.add_edge_unchecked(cell, "adjacent", self._map_cells[pt])
        for affordance in affordances:
            node = self.eng.add_node("MapAffordance", {k: affordance[k] for k in ("name", "kind", "x", "y")})
            self.eng.add_edge_unchecked(self._map_node, "has_affordance", node)
            cell = self._map_cells.get((affordance["x"], affordance["y"]))
            if cell is not None:
                self.eng.add_edge_unchecked(node, "at_cell", cell)
            self._map_affordances[affordance["name"]] = node

    def _anchor_for_building(self, kind):
        work = self._map_layout.get("work", {}) if self._map_layout else {}
        fixed_sites = self._map_layout.get("building_sites", {}) if self._map_layout else {}
        aliases = self.E.FOUNDING_ANCHOR_ALIASES
        target = fixed_sites.get(kind) or work.get(kind) or work.get(aliases.get(kind, "")) or work.get("market")
        if isinstance(target, list):
            target = tuple(target)
        if target in self._map_cells:
            return target
        for pt in self._map_layout.get("farms", []) + self._map_layout.get("homes", []):
            if tuple(pt) in self._map_cells:
                return tuple(pt)
        return next(iter(self._map_cells), None)

    def _allocate_building_site(self, kind, spec, requested):
        """Choose the nearest clear walkable site for a building footprint.

        Several services historically shared one anchor cell. That was valid
        graph data, but it made their physical facades render on top of one
        another. Each place remains distinct; only its map site is resolved
        here so buildings have room to stand.
        """
        footprint = spec.get("footprint", spec.get("size", (3, 3)))
        if isinstance(footprint, (int, float)):
            footprint = (int(footprint), int(footprint))
        if not isinstance(footprint, (list, tuple)) or len(footprint) != 2:
            footprint = (3, 3)
        width, height = max(1, int(footprint[0])), max(1, int(footprint[1]))
        target = tuple(requested) if requested is not None else (0, 0)
        map_width = len(self._map_grid[0]) if self._map_grid else 0
        map_height = len(self._map_grid or [])

        def clear(site):
            x, y = site
            if x < 0 or y < 0 or x + width > map_width or y + height > map_height:
                return False
            if any((x + dx, y + dy) not in self._map_cells
                   for dy in range(height) for dx in range(width)):
                return False
            for ox, oy, ow, oh in self._building_sites.values():
                if x < ox + ow and ox < x + width and y < oy + oh and oy < y + height:
                    return False
            return True

        candidates = [(x, y) for y in range(max(0, map_height - height + 1))
                      for x in range(max(0, map_width - width + 1))]
        candidates.sort(key=lambda site: (abs(site[0] - target[0]) + abs(site[1] - target[1]),
                                          site[1], site[0]))
        for site in candidates:
            if clear(site):
                return (site[0], site[1], width, height)
        # Custom scenarios may deliberately pack buildings tightly. Preserve
        # the requested anchor rather than making world construction fail.
        return (target[0], target[1], width, height)

    def _attach_at_cell(self, node, cell, edge="at_cell"):
        if cell in self._map_cells:
            self.eng.add_edge_unchecked(node, edge, self._map_cells[cell])

    def map_position(self, name):
        node = (self._actor_cells.get(name) or self._land_cells.get(name) or
                self._household_cells.get(name) or getattr(self, "_places", {}).get(name))
        if node is None:
            return None
        attrs = self.eng.node(node)["attrs"]
        if "x" in attrs and "y" in attrs:
            return (int(attrs["x"]), int(attrs["y"]))
        cells = list(self.eng.neighbours(node, "at_cell"))
        if not cells:
            return None
        ca = self.eng.node(cells[0])["attrs"]
        return (int(ca["x"]), int(ca["y"]))

    def map_tile(self, cell): return self._map_grid[cell[1]][cell[0]]
    def map_affordances(self): return dict(self._map_affordances)
    def building_position(self, kind): return self.map_position(kind)

    def reachable(self, a, b):
        return self.distance(a, b) is not None

    def sanity_report(self):
        """Return mechanical initialization checks for a village scenario.

        This deliberately reports missing provisioning/capability rather than silently creating
        supplies.  A scenario can be viable while still warning that it will fail without labour,
        harvest, preservation, trade, or imports.
        """
        errors, warnings = [], []
        alive = [name for name, node in self._actors.items()
                 if float(self.eng.node(node)["attrs"].get("alive", 1.0)) == 1.0]
        unreachable = []
        for name, node in self._actors.items():
            pos = self.actor_position(name)
            works = list(self.eng.neighbours(node, "works_at"))
            if pos is None or not works:
                unreachable.append(name)
                continue
            target = self.map_position_node(works[0])
            if self.distance(pos, target) is None:
                unreachable.append(name)
        if unreachable:
            errors.append("residents have unreachable or missing workplaces")
        map_connected = True
        if self._map_cells:
            start = next(iter(self._map_cells))
            seen, frontier = {start}, [start]
            while frontier:
                point = frontier.pop()
                for nx, ny in ((point[0] + 1, point[1]), (point[0] - 1, point[1]),
                               (point[0], point[1] + 1), (point[0], point[1] - 1)):
                    if (nx, ny) in self._map_cells and (nx, ny) not in seen:
                        seen.add((nx, ny)); frontier.append((nx, ny))
            map_connected = len(seen) == len(self._map_cells)
            if not map_connected:
                errors.append("walkable map cells are disconnected")

        for name, node in self._animals.items():
            if not list(self.eng.neighbours(node, "at_cell")):
                errors.append(f"animal has no location: {name}")
            if not list(self.eng.neighbours(node, "grazes_on")):
                warnings.append(f"animal has no grazing/keeping land: {name}")

        negative_stocks = sorted(kind for kind, node in self._stock.items()
                                 if float(self.eng.node(node)["attrs"].get("qty", 0.0)) < -1e-6)
        if negative_stocks:
            errors.append("physical stock quantities went negative")

        food_qty = (sum(self.qty(kind) * self.E.feeds(kind) * self._pile_condition(self._stock.get(kind))
                        for kind, spec in self._item_specs.items() if spec.get("food"))
                    + sum(self.inventory_qty(name, kind) * self.E.feeds(kind)
                          * self._pile_condition(self._inventory_stock(name, kind))
                          for name in self._actors
                          for kind, spec in self._item_specs.items() if spec.get("food")))
        food_days = food_qty / len(alive) if alive else 0.0
        shelf_lives = [self.stock_condition(kind) / self.E.decay_rate(kind)
                       for kind, spec in self._item_specs.items()
                       if spec.get("food") and self.qty(kind) > 0 and self.E.decay_rate(kind) > 0
                       and self.stock_condition(kind) > 0]
        food_shelf_life = min(shelf_lives) if shelf_lives else float("inf")
        if alive and food_days < 4.0:
            warnings.append("less than four resident-rations of edible stock are available")
        if alive and food_shelf_life <= 4.0:
            warnings.append("the fastest-spoiling edible stock expires within four periods")
        feed_days = {}
        for feed in {self.eng.node(a)["attrs"].get("eats", "") for a in self._animals.values()}:
            demand = sum(float(self.eng.node(a)["attrs"].get("ration", 1.0))
                          for a in self._animals.values()
                          if self.eng.node(a)["attrs"].get("eats", "") == feed)
            feed_days[feed] = self._feed_qty(feed) / demand if demand else 0.0
            if demand and feed_days[feed] < 4.0:
                warnings.append(f"less than four days of animal feed: {feed}")

        capability_gaps = [name for name in self._actors
                           if not any(self._capable(name, action)
                                      for action in self._actions)]
        essential_actions = ("grind_flour", "bake_bread", "make_pottage")
        essential_recipe_gaps = [action for action in essential_actions
                                 if action not in self._actions]
        if essential_recipe_gaps:
            warnings.append("essential food-production capabilities are unseeded")
        return {
            "population": len(self._actors), "alive": len(alive),
            "map_cells": len(self._map_cells), "map_connected": map_connected,
            "unreachable_residents": unreachable,
            "households": len(self._households), "land": len(self._land),
            # ``crops`` is the variety count used by the public sanity view;
            # ``crop_beds`` exposes the actual physical beds in the expanded
            # rotation.  A parcel may contain many beds of the same crop.
            "crops": len({self.eng.node(c)["attrs"].get("crop")
                           for c in getattr(self, "_crops", {}).values()}),
            "crop_beds": len(getattr(self, "_crops", {})),
            "animals": len(self._animals),
            "animals_with_grazing_land": sum(bool(list(self.eng.neighbours(a, "grazes_on")))
                                              for a in self._animals.values()),
            "enclosures": len(self._enclosures),
            "fences": len(self._fences),
            "animals_in_enclosures": sum(bool(list(self.eng.neighbours(a, "kept_in")))
                                          for a in self._animals.values()),
            "intact_enclosures": sum(self.enclosure_intact(name) for name in self._enclosures),
            "deposits": len(self._resource_deposits), "shops": len(self._shops),
            "storage_containers": sum(
                1 for name, (node, _) in self._containers.items()
                if self.eng.node(node)["attrs"].get("kind") != "carrier"),
            "resident_inventories": len(self._actor_inventories),
            "written_documents": len(self._documents), "edible_stock": round(food_qty, 4),
            "registered_land": len(self._titles),
            "unregistered_land": sorted(set(self._land) - set(self._titles)),
            "resident_food_days": round(food_days, 4),
            "resident_food_shelf_life": None if food_shelf_life == float("inf") else round(food_shelf_life, 4),
            "negative_stocks": negative_stocks,
            "animal_feed_days": feed_days,
            "recipe_capability_gaps": capability_gaps,
            "essential_recipe_gaps": essential_recipe_gaps,
            "errors": errors, "warnings": warnings,
        }

    def report(self, *, sample_size=30, seed=None):
        """Return the current exact census, economy, and social report."""
        from bigville.reporting import SimulationReporter
        return SimulationReporter(self).report(sample_size=sample_size, seed=seed)

    def record_report_snapshot(self, *, label=None, sample_size=30, seed=None):
        """Record a read-only time-series snapshot for later comparison."""
        from bigville.reporting import SimulationReporter
        return SimulationReporter(self).record_snapshot(label=label, sample_size=sample_size, seed=seed)

    def report_history(self):
        from bigville.reporting import SimulationReporter
        return SimulationReporter(self).history()

    def distance(self, a, b):
        """Shortest walkable-cell distance; map distance is a world fact, not a preference."""
        if a not in self._map_cells or b not in self._map_cells:
            return None
        with _DISTANCE_FIELDS_LOCK:
            field = self._distance_fields.get(b)
            if field is None:
                field = {b: 0}
                frontier = deque([b])
                while frontier:
                    pt = frontier.popleft()
                    d = field[pt] + 1
                    for nx, ny in ((pt[0] + 1, pt[1]), (pt[0] - 1, pt[1]),
                                   (pt[0], pt[1] + 1), (pt[0], pt[1] - 1)):
                        neighbour = (nx, ny)
                        if neighbour in self._map_cells and neighbour not in field:
                            field[neighbour] = d
                            frontier.append(neighbour)
                self._distance_fields[b] = field
            return field.get(a)

    def terrain_movement_rules(self):
        """Return the seeded movement records used by map cells and actions."""
        return {name: dict(values) for name, values in self.E.TERRAIN_MOVEMENT.items()}

    def terrain_state(self, cell):
        """Return the movement read-off for a map cell, including its terrain name."""
        if not isinstance(cell, tuple) or cell not in self._map_cells:
            return {"terrain": "unknown", **dict(self.E.TERRAIN_MOVEMENT["grass"])}
        attrs = self.eng.node(self._map_cells[cell])["attrs"]
        base = str(attrs.get("base_terrain", attrs.get("terrain", "grass")))
        wear = float(attrs.get("wear", 0.0))
        record = self.E.TERRAIN_WEAR.get(base)
        if record is None or wear <= 0.0:
            terrain = str(attrs.get("terrain", base))
            return {"terrain": terrain,
                    "speed": float(attrs.get("speed", 1.0)),
                    "move_time": float(attrs.get("move_time", 1.0)),
                    "stamina_multiplier": float(attrs.get("stamina_multiplier", 1.0))}
        # Part-worn ground is part-easier. Interpolating the movement read-off across
        # the accumulator -- rather than switching it at the end -- is what lets traffic
        # recruit traffic: the first crossings make the next ones cheaper.
        worn = self.E.TERRAIN_MOVEMENT.get(str(record["wears_to"]), self.E.TERRAIN_MOVEMENT["grass"])
        fresh = self.E.TERRAIN_MOVEMENT.get(base, self.E.TERRAIN_MOVEMENT["grass"])
        blend = min(1.0, max(0.0, wear))
        return {"terrain": str(attrs.get("terrain", base)),
                "speed": fresh["speed"] + (worn["speed"] - fresh["speed"]) * blend,
                "move_time": fresh["move_time"] + (worn["move_time"] - fresh["move_time"]) * blend,
                "stamina_multiplier": (fresh["stamina_multiplier"]
                                       + (worn["stamina_multiplier"]
                                          - fresh["stamina_multiplier"]) * blend)}

    def _terrain_move_time(self, cell):
        """Read only the edge cost used by weighted routing.

        ``travel_time`` explores many cells for each destination, and does not
        need the terrain label, speed, or stamina fields returned by
        ``terrain_state``. Keep its movement-cost interpolation identical
        while avoiding a temporary four-field dictionary for every explored
        edge.
        """
        if not isinstance(cell, tuple) or cell not in self._map_cells:
            return float(self.E.TERRAIN_MOVEMENT["grass"]["move_time"])
        attrs = self.eng.node(self._map_cells[cell])["attrs"]
        base = str(attrs.get("base_terrain", attrs.get("terrain", "grass")))
        wear = float(attrs.get("wear", 0.0))
        record = self.E.TERRAIN_WEAR.get(base)
        if record is None or wear <= 0.0:
            return float(attrs.get("move_time", 1.0))
        worn = self.E.TERRAIN_MOVEMENT.get(str(record["wears_to"]), self.E.TERRAIN_MOVEMENT["grass"])
        fresh = self.E.TERRAIN_MOVEMENT.get(base, self.E.TERRAIN_MOVEMENT["grass"])
        blend = min(1.0, max(0.0, wear))
        return fresh["move_time"] + (worn["move_time"] - fresh["move_time"]) * blend

    # ------------------------------------------------------------- terrain wear
    def _wear_record(self, cell_node):
        """The TERRAIN_WEAR record governing this cell, or None if it is inert."""
        base = str(self.eng.node(cell_node)["attrs"].get("base_terrain", ""))
        return self.E.TERRAIN_WEAR.get(base)

    def _advance_wear(self, cell_node, delta):
        """Move a cell's wear accumulator and republish its terrain read-off."""
        record = self._wear_record(cell_node)
        if record is None:
            return
        attrs = self.eng.node(cell_node)["attrs"]
        base = str(attrs.get("base_terrain", "grass"))
        wear = min(1.0, max(0.0, float(attrs.get("wear", 0.0)) + delta))
        self.eng.set_attr(cell_node, "wear", wear)
        # The label flips only at the far end of the accumulator; below that the cell is
        # still its seeded terrain, merely easier to cross.
        terrain = str(record["wears_to"]) if wear >= 1.0 else base
        self.eng.set_attr(cell_node, "terrain", terrain)
        movement = self.E.TERRAIN_MOVEMENT.get(terrain, self.E.TERRAIN_MOVEMENT["grass"])
        for key in ("speed", "move_time", "stamina_multiplier"):
            self.eng.set_attr(cell_node, key, float(movement[key]))

    def _wear_cell_by_traversal(self, actor, cell):
        """One crossing of a cell by one walker."""
        node = self._map_cells.get(tuple(cell))
        if node is None:
            return
        record = self._wear_record(node)
        if record is None:
            return
        passes = float(record.get("passes_to_form", 0.0))
        if passes <= 0.0:
            return
        load = 1.0
        if record.get("load_sensitive"):
            carried = self.eng.node(self._actor(actor))["attrs"].get("carry_ratio", 0.0)
            load = 1.0 + float(carried or 0.0)
        self._advance_wear(node, load / passes)
        self._traversed_this_tick.add(tuple(cell))

    def _terrain_recovery_tick(self):
        """Ground nobody walked on this turn grows back."""
        for cell, node in self._map_cells.items():
            if cell in self._traversed_this_tick:
                continue
            record = self._wear_record(node)
            if record is None:
                continue
            if float(self.eng.node(node)["attrs"].get("wear", 0.0)) <= 0.0:
                continue
            ticks = float(record.get("ticks_to_fade", 0.0))
            if ticks > 0.0:
                self._advance_wear(node, -1.0 / ticks)
        self._traversed_this_tick = set()

    def terrain_wear(self, cell):
        """Read-off: how far this cell has been worn toward the terrain it forms."""
        node = self._map_cells.get(tuple(cell))
        return 0.0 if node is None else float(
            self.eng.node(node)["attrs"].get("wear", 0.0))

    def travel_time(self, a, b):
        """Terrain-weighted travel time used for route choice.

        ``distance`` remains the unweighted map fact.  This separate read-off lets an actor or
        backend prefer a longer path when the seeded terrain makes it faster and less tiring.
        """
        if a not in self._map_cells or b not in self._map_cells:
            return None
        field = self._travel_time_fields.get(b)
        if field is None:
            field = {b: 0.0}
            frontier = [(0.0, b)]
            while frontier:
                cost, point = heapq.heappop(frontier)
                if cost > field.get(point, float("inf")):
                    continue
                for nx, ny in ((point[0] + 1, point[1]), (point[0] - 1, point[1]),
                               (point[0], point[1] + 1), (point[0], point[1] - 1)):
                    neighbour = (nx, ny)
                    if neighbour not in self._map_cells:
                        continue
                    step = self._terrain_move_time(neighbour)
                    candidate = cost + step
                    if candidate < field.get(neighbour, float("inf")):
                        field[neighbour] = candidate
                        heapq.heappush(frontier, (candidate, neighbour))
            self._travel_time_fields[b] = field
        return field.get(a)

    def _movement_step(self, current, destination):
        """Choose the next admissible step using the seeded terrain travel costs."""
        if current not in self._map_cells or destination not in self._map_cells:
            return None
        candidates = [(current[0] + 1, current[1]), (current[0] - 1, current[1]),
                      (current[0], current[1] + 1), (current[0], current[1] - 1)]
        travel = {point: self.travel_time(point, destination)
                  for point in candidates if point in self._map_cells}
        viable = [point for point, value in travel.items() if value is not None]
        return min(viable, key=lambda point: (travel[point], self.distance(point, destination))) \
            if viable else None

    def _ensure_position_index(self):
        """Return the indexed position mapping, rewrapping a restored plain dict (TG02).

        Checkpoints decode ``_actor_positions`` as a plain dict. The first
        movement or proximity query after a restore replaces it with an
        ``_ActorPositions`` that rebuilds the derived bucket map in one pass.
        """
        positions = self.__dict__.get("_actor_positions")
        if isinstance(positions, _ActorPositions):
            return positions
        indexed = _ActorPositions()
        if positions:
            indexed.update(positions)
        self._actor_positions = indexed
        return indexed

    def _actor_candidates(self, cell, radius):
        """Names in the Chebyshev bounding square; brute force under the debug switch."""
        positions = self._ensure_position_index()
        if self._force_linear_proximity:
            return sorted(positions)
        return positions.near(cell, radius)

    def actors_near(self, position, radius, *, alive_only=True, exclude=None):
        """Sorted names of actors within walkable ``radius`` of ``position``.

        Candidates come from the occupancy index's Chebyshev bounding square, a
        strict superset of the walkable-distance ball, then are filtered with
        ``distance``. The result is exactly the brute-force set and is sorted.
        """
        if not isinstance(position, tuple) or len(position) != 2:
            return []
        names = []
        for name in self._actor_candidates(position, radius):
            if exclude is not None and name == exclude:
                continue
            if name not in self._actors:
                continue
            if alive_only and not self.is_alive(name):
                continue
            other_position = self.actor_position(name)
            distance = self.distance(position, other_position) if other_position is not None else None
            if distance is not None and distance <= radius:
                names.append(name)
        return sorted(names)

    def actor_position(self, actor): return self._ensure_position_index().get(actor)

    def _node_item_weight(self, item):
        attrs = self.eng.node(item)["attrs"]
        if "weight" in attrs:
            return float(attrs["weight"])
        return self._phys(attrs.get("kind", ""))[0]

    def _held_discrete_weight(self, actor):
        node = self._actor(actor)
        seen = set()
        total = 0.0
        for edge in ("holds_in_hand", "holds_tableware"):
            for item in self.eng.neighbours(node, edge):
                if item in seen:
                    continue
                seen.add(item)
                total += self._node_item_weight(item)
        return total

    def carried_weight(self, actor):
        """The physical weight currently borne by a resident."""
        self._actor(actor)
        return round(self.contents_weight(self._actor_inventories[actor])
                     + self._held_discrete_weight(actor), 4)

    def carrying_capacity(self, actor):
        return self.max_load(self._actor_inventories[actor])

    def carry_state(self, actor):
        """Return held weight, overload, speed, and exertion read-offs."""
        weight = self.carried_weight(actor)
        capacity = self.carrying_capacity(actor)
        ratio = weight / capacity if capacity > 0.0 else float("inf")
        overload = max(0.0, ratio - float(self.E.CARRYING["overload_ratio"]))
        interval = max(1, int(math.ceil(ratio))) if math.isfinite(ratio) else 999999
        speed = 1.0 / interval
        effort = float(self.E.CARRYING["base_move_energy"]) * (
            1.0 + float(self.E.CARRYING["overload_energy_factor"]) * overload)
        return {"weight": round(weight, 4), "capacity": round(capacity, 4),
                "ratio": round(ratio, 4), "overloaded": ratio > float(self.E.CARRYING["overload_ratio"]),
                "drop_threshold": round(capacity * float(self.E.CARRYING["drop_ratio"]), 4),
                "speed": round(speed, 4), "move_interval": interval,
                "move_energy": round(effort, 4),
                "will_drop": ratio > float(self.E.CARRYING["drop_ratio"])}

    def _refresh_carry_state(self, actor):
        state = self.carry_state(actor)
        attrs = self.eng.node(self._actor(actor))["attrs"]
        for key, value in (("carried_weight", state["weight"]),
                           ("carry_ratio", state["ratio"]),
                           ("carry_speed", state["speed"]),
                           ("carry_move_energy", state["move_energy"]),
                           ("carry_overloaded", 1.0 if state["overloaded"] else 0.0)):
            self.eng.set_attr(self._actor(actor), key, float(value))
        return state

    def _move_actor_to(self, actor, cell):
        positions = self._ensure_position_index()
        old = positions.get(actor)
        if old in self._map_cells:
            self.eng.remove_edge_unchecked(self._actors[actor], "at_cell", self._map_cells[old])
        self._attach_at_cell(self._actors[actor], cell)
        positions[actor] = tuple(cell)
        # Footfall is a physical effect of arriving, so it belongs to the single
        # enactment site rather than to any one caller that happens to move someone.
        self._wear_cell_by_traversal(actor, cell)
        self._set_job_paused(actor, self.job_paused(actor))

    def move_actor(self, actor, destination):
        """Move one resident toward a destination, with load affecting travel."""
        positions = self._ensure_position_index()
        current = positions.get(actor)
        if current is None or destination not in self._map_cells:
            return None
        # The band is read before this walker's own effort is spent, so a step is taken at the pace the
        # resident had when they set off (Phase 024).
        # Phase 033: a restrained resident cannot walk, and neither can one who is holding someone.
        if self.holder_of(actor) is not None or self.holding_of(actor) is not None:
            return current
        band = self._exhaustion_band(actor)
        if band["stopped"]:
            # Too exhausted to walk (Phase 024): no step, no effort. The walk is refused before this point.
            return current
        state = self._refresh_carry_state(actor)
        attrs = self.eng.node(self._actor(actor))["attrs"]
        nxt = self._movement_step(current, destination)
        terrain = self.terrain_state(nxt or current)
        effort = state["move_energy"] * float(terrain.get("stamina_multiplier", 1.0))
        self.eng.set_attr(self._actor(actor), "terrain", terrain["terrain"])
        self.eng.set_attr(self._actor(actor), "terrain_speed", float(terrain["speed"]))
        self.eng.set_attr(self._actor(actor), "terrain_stamina_multiplier",
                          float(terrain["stamina_multiplier"]))
        # The body's seeded exertion rule owns depletion, hunger, and recovery.
        # This adapter only mints the physical event and supplies its cost.
        body = self._bodies.get(actor)
        if body is not None:
            exertion = self.eng.add_node("Effort", {
                "uses_strength": 0.0, "uses_stamina": 1.0,
                "intensity": min(1.0, effort * 0.1), "stamina_cost": effort * 0.1,
                "terrain": terrain["terrain"], "terrain_speed": float(terrain["speed"]),
                "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
            self.eng.add_edge_unchecked(self._actor(actor), "exerted", exertion)
            if not self._actor_tick_in_progress:
                self._request_rule_sweep()
        cooldown = float(attrs.get("carry_move_cooldown", 0.0))
        if cooldown >= 1.0 - 1e-9:
            self.eng.set_attr(self._actor(actor), "carry_move_cooldown", cooldown - 1.0)
            return current
        terrain_interval = max(1, int(math.ceil(state["move_interval"] * terrain["move_time"])))
        # Phase 024: a tired walker's interval is multiplied (x1, x1.5 or x3). Waiting ticks accumulate in
        # the float cooldown, so a step at interval I owes I - 1 waiting ticks. Whole intervals wait exactly
        # as they did before the factor existed.
        interval = terrain_interval * band["interval"] / self.stagger_speed(actor) * _dn.travel_factor(self, actor)
        self.eng.set_attr(self._actor(actor), "carry_move_cooldown",
                          cooldown + interval - 1.0 if interval > 1.0 + 1e-9 else 0.0)
        if nxt is not None:
            self._move_actor_to(actor, nxt)
        return self._actor_positions.get(actor)
    @classmethod
    def from_town100(cls, seed=305000, *, autonomous_actors=False,
                     cognition_factory=None, data_pack=None, physical_subsystems=None):
        """Build the founding town of a data pack: its map, its seeded cast of residents, and its
        institutions. The default pack is bigville (the 100-resident town of the canonical world).
        A pack with no founding town (empty FOUNDING_JOBS) is refused by populate_town100."""
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors,
                    cognition_factory=cognition_factory, data_pack=data_pack,
                    physical_subsystems=physical_subsystems)
        world.populate_town100(seed=seed)
        return world

    @classmethod
    def from_scenario(cls, scenario, *, seed=305000, autonomous_actors=False,
                      cognition_factory=None, physical_subsystems=None):
        """Build any compact or large scenario from data.

        Actor cognition remains a game/backend concern; this method only
        installs the physical world and the scenario's initial actors.
        """
        definition = load_scenario(scenario)
        if physical_subsystems is not None and "physical_subsystems" in definition.to_dict():
            # The constructor deliberately treats scenario settings and explicit
            # constructor settings as mutually exclusive. For a management run,
            # materialize the scenario copy with its authored settings removed;
            # the caller supplies the already-resolved effective values below.
            data = definition.to_dict()
            authored_switches = data.get("physical_subsystems")
            if not isinstance(authored_switches, dict) or not isinstance(physical_subsystems, dict):
                raise TypeError("physical_subsystems must be a mapping of names to booleans")
            physical_subsystems = {**authored_switches, **physical_subsystems}
            data.pop("physical_subsystems", None)
            definition = load_scenario(data)
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors,
                    scenario=definition, cognition_factory=cognition_factory,
                    physical_subsystems=physical_subsystems)
        for actor in definition.actors:
            data = dict(actor)
            name = data.pop("name")
            backend = data.pop("backend", None)
            simple_profile = data.pop("simple_profile", None)
            world._scenario_character_data[name] = {
                "identity": dict(data.get("identity", {})),
                "personality": dict(data.get("personality", {})),
                "memories": list(data.get("memories", [])),
                "held_frames": list(data.get("held_frames", data.get("frames", []))),
                # Explicitly authored private beliefs belong to character setup,
                # never to role/population inference by the physical world.
                "reference_priors": list(data.get("reference_priors", [])),
                "recipe_priors": (list(data["recipe_priors"])
                                  if "recipe_priors" in data else None),
            }
            supported = {
                "role", "skill", "station", "literacy", "capability", "learn",
                "home_cell", "work_cell", "klass", "age", "life_stage",
                "role_identity", "group", "traits", "trades",
            }
            kwargs = {key: data[key] for key in supported if key in data}
            kwargs.setdefault("role", "resident")
            world.add_actor(name, **kwargs)
            if backend:
                world._scenario_actor_backends[name] = str(backend)
            if simple_profile:
                world._scenario_simple_profiles[name] = str(simple_profile)
        return world

    @classmethod
    def from_townspeople_50(cls, *, seed=305000, autonomous_actors=False,
                            cognition_factory=None):
        """Build the hand-authored 50-resident register, relationships included.

        ``seeds/bigville_townspeople_50.json`` carries a 50-entry ``inhabitants``
        list AND a 22-edge ``relationships`` list ({src, edge, tgt} triples), but
        (checked directly, not assumed) nothing in this repo instantiates either
        into a live world -- no scenario file references it, ``from_scenario``
        reads ``scenarios/*.json`` not ``seeds/*.json``, and this JSON's own id
        is not even loaded via ``load_seed_manifest`` (that call only records a
        provenance string; see ``bigville.runtime``).  This is that missing
        construction path: it turns the already-authored cast and relationship
        list into ``add_actor``/``set_relationship`` calls, mechanically, one
        time, at town construction.
        """
        path = (Path(__file__).resolve().parent.parent
               / "seeds" / "bigville_townspeople_50.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors,
                    cognition_factory=cognition_factory)
        for inhabitant in data["inhabitants"]:
            world.add_actor(str(inhabitant["name"]), role=str(inhabitant.get("role", "resident")))
        for edge in data["relationships"]:
            src, tgt = str(edge["src"]), str(edge["tgt"])
            if src not in world._actors or tgt not in world._actors:
                continue
            tie = world.E.RELATIONSHIP_KINDS.get(str(edge["edge"]), world.E.RELATIONSHIP_DEFAULT)
            kind, strength = tie["kind"], float(tie["strength"])
            world.set_relationship(src, tgt, kind=kind, strength=strength)
        return world

    def balance_scenario(self):
        """The BALANCE_SCENARIO shape this built town actually has (Phase 007).

        Every value is read from the world's own state: residents (actors), households, living crop
        beds by crop kind (all crops, including the one-off garden beds), arable farm plots (count,
        area, soil), animals by species, pasture area, water sources by kind in the order they were
        added, and woodland (lumber deposits, one woodlot each). Parameters of the balance model
        (food_per_resident, work_minutes_per_resident, staple) are not facts of the world and are not
        reported. Raises ValueError if the arable plots differ in area or soil, since the scenario
        takes one value for each.
        """
        from collections import Counter

        eng = self.eng

        def attrs(node):
            return eng.node(node)["attrs"]

        plots = [attrs(n) for n in eng.neighbours(self._town, "has_land") if attrs(n).get("use") == "arable"]
        areas = {round(float(p["area"]), 6) for p in plots}
        soils = {str(p["soil"]) for p in plots}
        if len(areas) > 1 or len(soils) > 1:
            raise ValueError(f"the arable plots differ: areas {sorted(areas)}, soils {sorted(soils)}")
        beds = Counter(str(attrs(crop)["crop"]) for crop in self._living_crops())
        animals = Counter(str(attrs(n)["species"]) for n in eng.neighbours(self._town, "has_animal"))
        pasture = sum(float(attrs(n)["area"]) for n in eng.neighbours(self._town, "has_land")
                      if attrs(n).get("use") == "pasture")
        water = [str(attrs(n)["kind"]) for n in eng.neighbours(self._town, "has_water_source")]
        woodland = sum(1 for n in eng.neighbours(self._town, "has_deposit") if attrs(n).get("kind") == "lumber")
        return {
            "residents": len(self._actors),
            "households": len(eng.neighbours(self._town, "has_household")),
            "beds": dict(beds),
            "plots": len(plots),
            "plot_area": next(iter(areas)) if areas else 0.0,
            "soil": next(iter(soils)) if soils else "",
            "animals": dict(animals),
            "pasture_area": float(pasture),
            "water_sources": water,
            "woodland": woodland,
        }

    def seed_residents(self, population, *, prefix=None, capacity_seed=0):
        """Seed `population` founding residents from the data's JOBS (E.seed_jobs).

        Each resident gets their job(s) as trades (the first is their role), their trade's base skill,
        and the jobs' starting tools in their own hands. Returns the seed plan plus the resident
        names; what they do afterwards is up to them. Raises ValueError if the jobs need more people
        than `population` (E.check_job_seed explains why)."""
        plan = self.E.seed_jobs(int(population))
        if plan["short"]:
            raise ValueError(f"the jobs need {int(population) + plan['short']} residents; "
                             f"only {int(population)} were asked for")
        names, counts = [], {}
        for resident in plan["residents"]:
            primary = resident["jobs"][0]
            counts[primary] = counts.get(primary, 0) + 1
            name = f"{prefix or primary}_{counts[primary] if not prefix else len(names) + 1}"
            role = resident["trades"][0]
            skill = float(self.E.TRADES.get(role, {}).get("base_skill", 0.7))
            self.add_actor(name, role=role, skill=skill, trades=tuple(resident["trades"][1:]))
            self.eng.set_attr(self._actors[name], "jobs", ",".join(resident["jobs"]))
            self.draw_capacities(name, seed=capacity_seed)
            for tool in resident["tools"]:
                self.give_tool(name, tool)
            names.append(name)
        return dict(plan, names=names)

    def populate_town100(self, *, seed=305000):
        """Import the 100-world's map-aligned cast as ordinary canonical entities.

        The 100-world remains a generator of scenario data.  Once imported, residents,
        households, land, shops, deposits, animals, and farms are owned by this world and
        use its normal APIs and graph vocabulary.
        """
        if getattr(self, "_cast100", None) is not None:
            return self._cast100
        if not self.E.FOUNDING_JOBS or not self.E.FOUNDING_MAP:
            raise ValueError(f"data pack '{self.data_pack}' has no founding town (FOUNDING_JOBS or "
                             f"FOUNDING_MAP is empty), so there is no 100-resident town to build")
        from worlds.bigville_town100_world import generate_cast100

        layout = self._map_layout
        cast = generate_cast100(layout, seed, self.E)
        self._cast100 = cast
        self._t100_households = {}
        self._t100_farms = []

        for kind, cell in layout.get("deposits", {}).items():
            deposit = self.E.RESOURCE_DEPOSITS.get(kind, {})
            self.add_deposit(kind, tuple(cell), stock=float(deposit.get("stock", 60.0)),
                             growback=float(deposit.get("growback", 3.0)),
                             capacity=float(deposit.get("capacity", 120.0)))
        self._place_gathering_sites(layout)
        self.add_store(tuple(layout["work"]["market"]), tuple(self.E.RESOURCE_DEPOSITS))
        for trade, chain in self.E.SHOP_CHAINS.items():
            if trade in layout["work"]:
                self.add_shop(trade, tuple(layout["work"][trade]),
                              input_kind=chain["in"], output_kind=chain["out"])

        station = self.E.FOUNDING_CLASS["station_by_group"]
        # One household per founding household (Phase 016b), on the home the map gave it. Its kind
        # follows its head's role and group (HOUSEHOLDS).
        by_name = {r["name"]: r for r in cast["residents"]}
        for hh in cast["households"]:
            head = by_name[hh["head"]]
            self.add_household(f"household_{int(hh['index']):03d}",
                               kind=self.household_kind_for(head["role"], head["group"]),
                               home_cell=tuple(hh["home_cell"]))
        for record in cast["residents"]:
            role = record["role"]
            household = f"household_{int(record['household']):03d}"
            self._t100_households[record["name"]] = household
            # AFFECT_COUPLING Phase 5 (TOWN100_DISPOSITION_SWITCHON_PREREG.md,
            # ocelot repo): _scenario_character_data must be populated BEFORE
            # add_actor -- add_actor itself reads it (via _cognition_factory's
            # seed_character(**character_data), see add_actor's own body) to
            # seed a resident's identity/personality. Previously only
            # from_scenario() ever populated this dict, so a cast-100
            # resident's own drawn _PARAM_SPEC params (already flattened onto
            # this actor's graph node below via `traits=`) never reached an
            # Ocelot cognition_factory's personality contract at all.
            # emotional_core_enabled is set EXPLICITLY (not left to seed_
            # character's own silent 1.0 default) so this is a visible,
            # deliberate choice, not an accident of omission.
            self._scenario_character_data[record["name"]] = {
                "identity": {"role": role, "klass": record["class"],
                            "group": record["group"]},
                "personality": {**record["params"], "emotional_core_enabled": 1.0},
            }
            self.add_actor(record["name"], role=role, skill=float(record["skill"]),
                           station=station[record["group"]],
                           literacy=float(record["literacy"]),
                           capability=float(record["capability"]),
                           age=float(record["age"]),
                           home_cell=tuple(record["home_cell"]),
                           work_cell=tuple(record["workplace_cell"]),
                           klass=record["class"], group=record["group"],
                           role_identity=float(record["role_identity"]), traits=record["params"],
                           trades=tuple(record["trades"]))
            # the founding cast are real people: aptitude, talents, and limitations drawn from the
            # observed distributions (E.LIMITATION_PREVALENCE), deterministic in the map seed
            self.draw_capacities(record["name"], seed=seed)
            # Phase 019: the founder's implied history is held on the node, and an earlier apprenticeship
            # in another trade leaves its skill levels (they are physical, so the world holds them).
            if record.get("history") is not None:
                self.eng.set_attr(self._actors[record["name"]], "history", dict(record["history"]))
            if record.get("former_skills"):
                self.seed_skill_floor(record["name"], dict(record["former_skills"]))
            for tableware in self.E.SERVING_EQUIPMENT:
                self.give_tableware(record["name"], tableware)
            self.assign_household(record["name"], household)

        land_roles = self._land_holder_roles()
        farmers = [r for r in cast["residents"] if r["role"] in land_roles]
        for index, cell in enumerate(layout.get("farms", [])):
            owner = self._t100_households[farmers[index % len(farmers)]["name"]] if farmers else None
            land = self.add_land(f"farm_plot_{index:02d}", use="arable", soil="loam",
                                 area=1.0, cell=tuple(cell), household=owner)
            self._t100_farms.append(land)
        pasture_cell = tuple(layout.get("farms", [])[0]) if layout.get("farms") else None
        if pasture_cell is not None:
            self.add_land("village_pasture", use="pasture", soil="loam", area=4.0,
                          cell=pasture_cell)
            px, py = pasture_cell
            pasture_cells = [(x, y) for y in range(py - 2, py + 3)
                             for x in range(px - 2, px + 3)
                             if (x, y) in self._map_cells]
            self.add_enclosure("village_paddock", pasture_cells,
                               kind="paddock", gates=((px, py - 2),))
        registrars = self._registrar_roles()
        clerks = [name for name, node in self._actors.items()
                  if self.eng.node(node)["attrs"].get("role") in registrars]
        if clerks and farmers:
            clerk = clerks[0]
            common_holder = self._t100_households[farmers[0]["name"]]
            for land_name, land_node in self._land.items():
                holder = self.eng.node(land_node)["attrs"].get("household") or common_holder
                self.register_land(clerk, land_name, holder, holder_kind="household",
                                   tenure="commons" if land_name == "village_pasture" else "freehold",
                                   basis="founding_grant", witnesses=(farmers[0]["name"],))

        # Basic material supports are present from the beginning of the scenario; their
        # quantities remain physical stocks and can still be exhausted by later actions.
        self.add_water_source("village_well", kind="well")
        # A hundred-person settlement needs more than a single 40-unit well
        # yield once crop watering is included.  The spring is a second mapped
        # source, not an infinite stock: run_village draws each source once per
        # period and the source's data-defined yield is the cap.
        self.add_water_source("village_spring", kind="spring")
        self.add_water_source("village_spring_2", kind="spring")
        # The lake on the imported map is a lower-quality but abundant backup
        # for field watering.  Without it, 48 cultivated beds plus cooking can
        # legitimately exceed the well/spring yield during a dry rotation.
        self.add_water_source("village_stream", kind="stream")
        for name, kind in (("village_latrine", "latrine"), ("village_compost", "compost_yard"),
                           ("village_granary", "granary"), ("village_root_cellar", "root_cellar")):
            self.add_infrastructure(name, kind=kind)
        # The buildings are not type gates: each physical store can accept any content, while its
        # affinity only changes decay.  Empty founding stores are still real places residents can
        # fill and inspect.
        self.add_container("village_granary_store", kind="granary", holds=("grain", "barley", "oats"),
                           cell=self._anchor_for_building("granary"))
        self.add_container("village_root_cellar_store", kind="root_cellar",
                           holds=("potato", "cabbage", "carrot", "onion"),
                           cell=self._anchor_for_building("root_cellar"))
        self.add_container("village_pantry_store", kind="pantry", holds=("bread", "cheese", "butter"),
                           cell=self._anchor_for_building("kitchen"))
        if farmers:
            farm_household = self._t100_households[farmers[0]["name"]]
            for index, species in enumerate(("cow", "chicken", "pig", "sheep", "horse", "bee", "dog")):
                self.add_animal(f"{species}_{index}", species, cell=pasture_cell,
                                household=farm_household, land="village_pasture",
                                enclosure="village_paddock")
        for kind, qty in self.E.STARTING_STOCK.items():
            self.set_stock(kind, qty)
        # The reserve is physical stock, but food intended for sale must be
        # carried by actual residents.  Seed the first two bakery workers with
        # a finite opening inventory; later output is collected from completed
        # recipes by the canonical job bridge above.
        bakers = self._workers_with_roles(self.E.LABOUR_TASKS["bake"]["worker_roles"], alive_only=False)
        for baker in bakers:
            if self.qty("bread") <= 0.0:
                break
            # Seed finite carried stock as a physical inventory fact.  Whether
            # its holder offers or sells it belongs to that resident's mind.
            self._move_stock_to_inventory(baker, "bread", min(40.0, self.qty("bread")))
        # Seed the first rotation so the founding bread reserve is connected to actual local
        # production.  Later sowing, watering, harvesting, milling, and cooking remain actions.
        for index, crop in enumerate(self.E.STARTING_CROPS):
            if index < len(self._t100_farms) and farmers:
                self.sow(farmers[index % len(farmers)]["name"], crop,
                         land=f"farm_plot_{index:02d}")
        # Expand the founding rotation into the grain beds the balance scenario describes (Phase 007).
        # Beds may share a mapped parcel; the map locates the field, while each Crop
        # node is an independently watered and harvested unit.
        self._seed_village_crops()
        self._found_kinship(cast["residents"], seed)
        from domains.relationship_seeding import seed_founding_relationships   # Phase 058: founding ties
        seed_founding_relationships(self, seed)
        return cast

    # ------------------------------------------------------------------ kinship (Phase 009)
    # Genealogy is a world fact: bore/fathered edges from each parent to each child, union_with edges
    # between partners (each union is a Union node carrying its start and end periods), and the birth
    # period and sex on every person. Kin terms are HELD: each founder holds KinTerm nodes, reachable
    # only through that founder's node. The founding seed writes the genealogical terms as authored
    # priors; later changes belong to the resident's backend. The world never decides who counts as
    # someone's uncle, and recording a held term never checks it against the genealogy.

    def _kin_clock(self):
        """Years since the founding clock (the founding year is 0)."""
        a = self.eng.node(self._town)["attrs"]
        per_year = float(self.E.TIME["ticks_per_day"]) * float(self.E.TIME["days_per_year"])
        return (float(a.get("clock", 0.0)) - float(getattr(self, "_kin_clock0", 0.0))) / per_year

    def _found_kinship(self, residents, seed):
        """Record the founding genealogy and seed each founder's genealogical kin terms.

        The draw uses its own generator (map seed + KINSHIP_STREAM), so the world's random streams, and
        every resident's name, role, household, home, and stock, are unchanged. Founders are the existing
        Agent nodes; the other persons are new Kin nodes."""
        import numpy as np
        self._kin_clock0 = float(self.eng.node(self._town)["attrs"].get("clock", 0.0))
        rng = np.random.default_rng(int(seed) + int(self.E.KINSHIP_STREAM))
        founders = [{"name": r["name"],
                     "age": float(self.eng.node(self._actors[r["name"]])["attrs"]["age"])}
                    for r in residents]
        kin = self.E.draw_founding_kin(founders, rng, present=0.0)
        node_of = {}
        for person in kin["persons"]:
            if person["founder"]:
                node = self._actors[person["name"]]
                attrs = {"kin_sex": person["sex"], "kin_birth": person["birth"]}
            else:
                node = self.eng.add_node("Kin", {"name": f"kin {person['id']}", "in_village": 0.0,
                                                 "kin_sex": person["sex"], "kin_birth": person["birth"]})
                attrs = {}
            for key, value in attrs.items():
                self.eng.set_attr(node, key, value)
            self.eng.set_attr(node, "kin_dead", 0.0 if person["death"] is None else 1.0)
            self.eng.set_attr(node, "kin_death", float(person["death"] or 0.0))
            node_of[person["id"]] = node
        for birth in kin["births"]:
            parent_sex = kin["persons"][birth["parent"]]["sex"]
            self.eng.add_edge_unchecked(node_of[birth["parent"]],
                                        "bore" if parent_sex == "female" else "fathered",
                                        node_of[birth["child"]])
        for union in kin["unions"]:
            a, b = node_of[union["a"]], node_of[union["b"]]
            record = self.eng.add_node("Union", {"a": int(a), "b": int(b), "start": union["start"],
                                                 "ended": 0.0 if union["end"] is None else 1.0,
                                                 "end": 0.0 if union["end"] is None else union["end"]})
            self.eng.add_edge_unchecked(a, "union_with", b)
            self.eng.add_edge_unchecked(b, "union_with", a)
            self.eng.add_edge_unchecked(a, "in_union", record)
            self.eng.add_edge_unchecked(b, "in_union", record)
        index = self.E.index_kinship(kin["persons"], kin["births"], kin["unions"])
        for pid in kin["founders"]:
            for target, (term, path) in sorted(self.E.kin_relatives(index, pid, 0.0).items()):
                self._hold_kin(node_of[pid], node_of[target], term, attribution="genealogy", path=path)
        return kin

    def _hold_kin(self, holder_node, target_node, term, *, attribution, path="", source=""):
        """A KinTerm node: `holder_node` holds `term` for `target_node`. Reachable only from the holder."""
        name = lambda node: str(self.eng.node(node)["attrs"].get("name", ""))  # noqa: E731
        ref = self.eng.add_node("KinTerm", {"term": term, "attribution": attribution, "path": path,
                                            "holder": name(holder_node), "target": name(target_node),
                                            "holder_node": int(holder_node), "target_node": int(target_node),
                                            "source": source})
        self.eng.add_edge_unchecked(holder_node, "holds_kin_term", ref)
        self.eng.add_edge_unchecked(ref, "of_kin", target_node)
        return ref

    def _person_node(self, who):
        """The graph node of a resident (by name) or of any kin person (by node id)."""
        if isinstance(who, str):
            if who not in self._actors:
                raise KeyError(f"unknown resident: {who}")
            return self._actors[who]
        node = int(who)
        if not self.eng.has_node(node) or "kin_birth" not in self.eng.node(node)["attrs"]:
            raise KeyError(f"no kinship record for node {who}")
        return node

    def _kin_index(self):
        """The genealogy as it stands in the graph, indexed for path queries (E.index_kinship)."""
        persons, births, unions = {}, [], []
        for node in self.eng.nodes():
            attrs = self.eng.node(node)["attrs"]
            if "kin_birth" not in attrs:
                continue
            nid = int(node)
            dead = float(attrs.get("kin_dead", 0.0)) == 1.0
            persons[nid] = {"id": nid, "name": str(attrs.get("name", "")), "sex": str(attrs["kin_sex"]),
                            "birth": float(attrs["kin_birth"]),
                            "death": float(attrs.get("kin_death", 0.0)) if dead else None,
                            "in_village": self.eng.node(node)["type"] == "Agent",
                            "founder": self.eng.node(node)["type"] == "Agent"}
        for pid in persons:
            for kind in ("bore", "fathered"):
                for child in self.eng.neighbours(pid, kind):
                    births.append({"parent": pid, "child": int(child),
                                   "period": persons[int(child)]["birth"]})
        for node in self.eng.nodes("Union"):
            attrs = self.eng.node(node)["attrs"]
            unions.append({"a": int(attrs["a"]), "b": int(attrs["b"]), "start": float(attrs["start"]),
                           "end": float(attrs["end"]) if attrs.get("ended") == 1.0 else None})
        return self.E.index_kinship(persons, births, unions)

    def genealogical_kin(self, holder, target):
        """The term the genealogy gives `holder` for `target` as (term, path), or None if no path."""
        return self.E.kin_relatives(self._kin_index(), self._person_node(holder),
                                    self._kin_clock()).get(self._person_node(target))

    def kin_terms_held(self, holder):
        """The kin terms `holder` holds: dicts with term, attribution, path, holder, and target. Held
        references are private to the holder's node; this returns them for that holder only."""
        rows = []
        for ref in self.eng.neighbours(self._person_node(holder), "holds_kin_term"):
            rows.append(dict(self.eng.node(ref)["attrs"]))
        return sorted(rows, key=lambda r: (r["target"], r["term"], r["attribution"]))

    def hold_kin_term(self, holder, target, term, *, attribution="honorific", source=""):
        """Record that `holder` calls `target` by `term`, held by an attribution (KIN_ATTRIBUTION): adoption,
        fostering, godparenthood, step-family, or an honorific title. The term is the holder's own reference
        and is not checked against the genealogy, so the two layers may disagree. Returns the held record."""
        assert term in self.E.KIN_TERMS, f"unknown kin term {term}"
        assert attribution in self.E.KIN_ATTRIBUTION and term in self.E.KIN_ATTRIBUTION[attribution]["terms"], \
            f"attribution {attribution} does not give {term}"
        holder_node, target_node = self._person_node(holder), self._person_node(target)
        assert holder_node != target_node, "a resident does not hold a kin term for themselves"
        ref = self._hold_kin(holder_node, target_node, term, attribution=attribution, source=source)
        return dict(self.eng.node(ref)["attrs"])

    def publish_heirs(self, name, *, custom=None):
        """Publish who the genealogical heirs of `name` are under `custom` (default: INHERITANCE_CUSTOM's
        default). The result is a HeirRecord and an observed event, and it names the successors for the
        existing 'inheritance' deed type. It moves no land, title, stock, coin, or household."""
        node = self._person_node(name)
        if "kin_birth" not in self.eng.node(node)["attrs"]:
            return None
        now = self._kin_clock()
        index = self._kin_index()
        custom_name = custom or self.E.INHERITANCE_CUSTOM["default"]
        heirs = [{"resident": index["persons"][h["id"]]["name"], "kind": h["kind"],
                  "share": round(float(h["share"]), 4), "life_interest": bool(h["life_interest"])}
                 for h in self.E.genealogical_heirs(index, int(node), now, custom_name)]
        listed = ";".join(f"{h['resident']}|{h['kind']}|{h['share']:.4f}|{int(h['life_interest'])}"
                          for h in heirs)
        record = self.eng.add_node("HeirRecord", {"predecessor": str(name), "custom": custom_name,
                                                  "deed_type": "inheritance", "period": now, "heirs": listed})
        self.eng.add_edge_unchecked(self._town, "has_heir_record", record)
        self.eng.add_edge_unchecked(node, "heir_record", record)
        who = ", ".join(f"{h['resident']} ({h['kind']}, share {h['share']:.2f})" for h in heirs) or "none"
        self.create_event("heirs_published", subject=str(name), public=True,
                          detail=f"{name}'s genealogical heirs under {custom_name}: {who}.")
        return {"predecessor": str(name), "custom": custom_name, "deed_type": "inheritance",
                "period": now, "heirs": heirs}

    def _record_kin_death(self, actor):
        """Mark a founder's genealogical death and publish their heirs. Residents with no kin record: no-op."""
        node = self._actors[actor]
        if "kin_birth" not in self.eng.node(node)["attrs"]:
            return None
        self.eng.set_attr(node, "kin_dead", 1.0)
        self.eng.set_attr(node, "kin_death", self._kin_clock())
        return self.publish_heirs(actor)

    def seed_workplace_relationships(self, *, strength=0.4):
        """Sparse, deterministic pre-existing colleague ties for the town100 cast.

        town100 has no shared-household grouping to key off (each resident's
        ``home_cell`` is unique -- ``bigville_town100_world.py`` draws one home
        per index from a >=100-plot pool, so "household-proximate" collapses to
        "workplace-proximate" for this cast specifically).  Workplace CELL
        (not just workplace *kind*: many farm/market roles share a kind across
        several physical cells) is the real proximity signal.  A naive
        all-pairs pass would be a bad shape here -- 25 labourers share one
        market cell, which is a 300-edge clique for one profession alone.
        Instead each resident is linked to exactly one neighbour within their
        own workplace-cell group, in a ring (wrapping), mutually -- matching
        the repo's own precedent for pre-existing history
        (``bigville_sim_world.py``: "Sparse ties only ... NOT an all-pairs
        graph"). This is opt-in, not called from ``populate_town100``/
        ``from_town100`` -- ``test_bigville_reporting.py`` asserts an EXACT
        ``directed_bonds`` count against a bare ``from_town100()`` town, so
        auto-wiring this would silently change that baseline.
        """
        cast = getattr(self, "_cast100", None)
        if not cast:
            return 0
        by_cell = {}
        for record in cast["residents"]:
            by_cell.setdefault(tuple(record["workplace_cell"]), []).append(record["name"])
        minted = 0
        for names in by_cell.values():
            if len(names) < 2:
                continue
            for i, name in enumerate(names):
                colleague = names[(i + 1) % len(names)]
                if colleague == name or (name, colleague) in self._relationships:
                    continue
                self.set_relationship(name, colleague, kind="friend", strength=strength, mutual=True)
                minted += 1
        return minted

    # ---------------------------------------------------- install the data as graph nodes
    def _install_item(self, kind, spec):
        n = self.eng.add_node("ItemSpec", {"kind": kind, **{k: (float(v) if not isinstance(v, bool)
                                                               and isinstance(v, (int, float)) else v)
                                                             for k, v in spec.items()}})
        self.eng.set_attr(n, "scarcity", self.E.scarcity(kind))   # the raw material's general scarcity (data)
        self.eng.add_edge_unchecked(self._town, "has_itemspec", n)
        self._items[kind] = n
        return n

    def _install_recipe(self, r):
        out_kind, out_qty = r["out"]
        out = self._item_specs.get(out_kind, {})
        # anything that is not a bulk material (tool/component/good/furniture) is a discrete item
        discrete = out.get("class", "material") != "material" and out.get("discrete", True)
        attrs = {"name": r["name"], "requires": r.get("requires", ""), "out_kind": out_kind,
                 "out_qty": float(out_qty), "out_discrete": 1.0 if discrete else 0.0,
                 "difficulty": float(r.get("difficulty", 1.0)), "time_minutes": float(r.get("time_minutes", 0.0)),
                 "min_skill": self.E.min_skill(r["name"]),   # the skill FLOOR to attempt it (apprenticeship)
                 "common": 0.0 if r.get("common") is False else 1.0}   # commonly known by the trade, or must be learned
        if discrete:                                    # carry the item's tool data onto the action
            attrs.update(verb=out.get("verb", ""), base_mult=float(out.get("base_mult", 1.0)),
                         wear_rate=float(out.get("wear_rate", 0.0)), decay=self.E.decay_rate(out_kind))
        asp = self.eng.add_node("ActionSpec", attrs)
        self.eng.add_edge_unchecked(self._town, "has_actionspec", asp)
        for kind, qty in r["in"]:                       # N input needs (data)
            icls = self._item_specs.get(kind, {}).get("class")
            is_item = 1.0 if icls not in (None, "material") and self._item_specs.get(kind, {}).get("discrete", True) else 0.0
            need_attrs = {"kind": kind, "qty": float(qty), "is_item": is_item}
            if self.E.is_input_type(kind):                   # a TYPE slot: any member item fills it
                need_attrs.update(slot_type=kind, is_item=0.0)
            need = self.eng.add_node("Need", need_attrs)
            self.eng.add_edge_unchecked(asp, "in_need", need)
        for tk in r.get("tools", []):                   # Y tool uses (data)
            tu = self.eng.add_node("ToolUse", {"kind": tk})
            self.eng.add_edge_unchecked(asp, "in_tool", tu)
        if not discrete:
            self.set_stock(out_kind, self.qty(out_kind))
        self._actions[r["name"]] = asp
        self._recipe_specs[r["name"]] = r
        return asp

    # ---------------------------------------------------- typed input slots
    def type_available(self, type_name, actor=None):
        """Units of a type slot (heat for fuel, nitrogen for fertiliser, ...) that can be drawn.

        Without `actor` only the town store counts. With `actor`, the worker's own stock and the
        accessible containers at their cell count too, in the same draw order a recipe uses."""
        return round(sum(self._bulk_available(actor, kind) * units
                         for kind, units in self.E.type_members(type_name)), 4)

    def _consume_type(self, type_name, qty):
        """Fill `qty` units of a type slot from store stock and leave its byproducts.

        Returns the {kind: amount} actually burnt/used, or None (and changes nothing) if short."""
        plan = self.E.type_plan(type_name, qty, self.qty)
        if plan is None:
            return None
        for kind, amount in plan:
            self.set_stock(kind, self.qty(kind) - amount)
        for kind, amount in self.E.type_byproducts(type_name, qty).items():
            self.set_stock(kind, self.qty(kind) + amount)
        return dict(plan)

    def _household_fuel_sources(self, household):
        """A household's own fuel sources, in draw order: each member's own inventory, then each container
        at the household's home cell that some member may access. These are the Phase 002 sources
        (`_bulk_sources`, `_container_accessible`), with the home cell standing in for a member's position,
        since a member may be away from home. The town store is not included."""
        h = self._households[household]
        members = [name for name, node in self._actors.items() if self.eng.has_edge(h, "has_member", node)]
        sources, seen = [], set()
        for name in members:
            for label, carrier in self._bulk_sources(name, "fuel"):
                if label == "own" and (label, carrier) not in seen:
                    seen.add((label, carrier))
                    sources.append((name, (label, carrier)))
        home = self.map_position(household)
        carriers = set(self._actor_inventories.values())
        if home is not None:
            for container in self._containers:
                if container in carriers or self.container_position(container) != home:
                    continue
                accessors = [name for name in members if self._container_accessible(name, container)]
                if accessors:
                    sources.append((accessors[0], ("box", container)))
        return sources

    def _burn_household_heat(self, households=None):
        """Each household burns fuel for space heat once per period (one day), at HEATING base_burn x the
        day's firewood_demand. It draws its own fuel first (see `_household_fuel_sources`), then the town
        store, and leaves the fuel's byproducts (ash) in the town store as `_consume_type` does. The
        household's fuel_need and fuel_short (the unmet share of its need) are written on its node; the
        members' chill reads fuel_short (`_resolve_clothing_and_bodies`). `households` limits the burn to
        the named households (default: all of them)."""
        if float(self.E.HEATING["base_burn"]) <= 0.0:      # a pack with no fuel economy burns nothing
            return
        demand = float(self.eng.node(self._town)["attrs"].get("firewood_demand", 1.0))
        slot = self.E.HEATING["fuel_type"]
        members = self.E.type_members(slot)
        for household in (self._households if households is None else households):
            h = self._households[household]
            need = float(self.E.HEATING["base_burn"]) * demand
            sources = self._household_fuel_sources(household)
            own_plan = self.E.type_plan(slot, min(need, sum(
                self._source_qty(src, kind) * units for _, src in sources for kind, units in members)),
                lambda kind: sum(self._source_qty(src, kind) for _, src in sources)) if need > 1e-9 else []
            burnt = 0.0
            for kind, amount in own_plan or []:
                left = float(amount)
                for who, src in sources:
                    take = min(left, self._source_qty(src, kind))
                    if take > 1e-9:
                        self._take_draws(who, kind, [(src, take)])
                        left -= take
                        burnt += take * dict(members)[kind]
                    if left <= 1e-9:
                        break
            rest = need - burnt
            store_units = sum(self.qty(kind) * units for kind, units in members)
            store_plan = self.E.type_plan(slot, min(rest, store_units), self.qty) if rest > 1e-9 else []
            for kind, amount in store_plan or []:
                self.set_stock(kind, self.qty(kind) - amount)
                burnt += amount * dict(members)[kind]
            for kind, amount in self.E.type_byproducts(slot, burnt).items():
                self.set_stock(kind, self.qty(kind) + amount)
            self.eng.set_attr(h, "fuel_need", need)
            self.eng.set_attr(h, "fuel_short", max(0.0, need - burnt) / need if need > 1e-9 else 0.0)

    def _household_unheated_share(self, household):
        """The unmet share of a household's heating need last period (0 when it is fully heated or has none)."""
        h = self._households.get(household)
        if h is None:
            return 0.0
        return float(self.eng.node(h)["attrs"].get("fuel_short", 0.0))

    def _open_work_read_offs(self, actor, recipe):
        """Physical read-offs that an open (household) recipe option carries (Phase 006). Empty for any other
        recipe. The world states quantities; it does not score them or say what the worker should do.

        fuel_held: fuel units in the worker's own inventory (what they hold).
        fuel_store: fuel units in the town store. Present only while the worker stands on the store's cell.
        household_fuel_short: the household's last unmet heating share (0 when fully heated, 1 with no fuel).
            Members feel this as cold. Present only for a resident in a household.
        night_soil_held: night soil in the worker's own inventory.
        night_soil_store: night soil in the town store, where it accumulates (`_collect_night_soil`). Present
            only while the worker stands on the store's cell.

        A recipe whose output is the HEATING fuel slot gets the fuel read-offs. A recipe that consumes night soil
        (HOUSEHOLD_WORK night_soil_kind) gets the night-soil read-offs. `open_recipe` marks every open recipe."""
        if not recipe.get("open"):
            return {}
        offs = {"open_recipe": True}
        slot = self.E.type_members(self.E.HEATING["fuel_type"])
        carrier = self._actor_inventories.get(actor)
        store_cell = self.map_position_node(self._store)
        at_store = store_cell is not None and self.actor_position(actor) == store_cell
        out_kind = recipe.get("out", [""])[0]
        if out_kind in {kind for kind, _units in slot}:
            held = sum(self.contents(carrier, kind) * units for kind, units in slot) if carrier else 0.0
            offs["fuel_held"] = round(held, 4)
            if at_store:
                offs["fuel_store"] = round(sum(self.qty(kind) * units for kind, units in slot), 4)
            household = self.eng.node(self._actors[actor])["attrs"].get("household")
            if household in self._households:
                offs["household_fuel_short"] = self._household_unheated_share(household)
        soil = self.E.HOUSEHOLD_WORK["night_soil_kind"]
        if any(kind == soil for kind, _qty in recipe.get("in", [])):
            offs["night_soil_held"] = self.contents(carrier, soil) if carrier else 0.0
            if at_store:
                offs["night_soil_store"] = self.qty(soil)
        return offs

    def _recipe_in_season(self, recipe_name):
        seasons = self._recipe_specs.get(recipe_name, {}).get("seasons")
        return not seasons or self.season() in seasons

    def _register_reference(self, reference):
        """Register a reference template; registration creates no town-owned fact."""
        self._reference_specs[reference["name"]] = dict(reference)
        return reference["name"]

    def _seed_reference(self, actor, reference):
        """Create a fact owned by one resident and avoid duplicate seeding."""
        name = reference["name"]
        refs = self._actor_references.setdefault(actor, {})
        if name in refs:
            return refs[name]
        statement = dict(reference.get("reference", {}))
        fact = self.eng.add_node("Fact", {
            "name": name, "kind": "resident_reference",
            "abstraction": reference.get("abstraction", "operational"),
            "source_kind": reference.get("source_kind", "shared"),
            "source_name": reference.get("source_name", ""),
            "source_origin": reference.get("source_origin", "bigville"),
            "source_immutable": 1.0 if reference.get("source_immutable", False) else 0.0,
            **statement})
        self.eng.add_edge_unchecked(actor, "knows_reference", fact)
        refs[name] = fact
        return fact

    def add_item(self, kind, spec):
        """Add a NEW item as pure data (a dict) -- no code change."""
        self._item_specs[kind] = spec
        return self._install_item(kind, spec)

    def add_recipe(self, r):
        """Add a NEW recipe/action (any inputs, any tools) as pure data (a dict) -- no code change."""
        asp = self._install_recipe(r)
        # A trade recipe's tools are placed at the buildings where that trade works. A trade
        # with no building (or a building not yet standing) gets no tool here; its worker
        # must hold one.
        trade = r.get("requires")
        if not r.get("open"):
            for place in self._places.values():
                if trade in self._building_trades(self._place_kind(place)):
                    self._equip_workshop(place, r.get("tools", []))
        return asp

    def add_reference(self, reference):
        """Register a physical reference template without assigning resident beliefs."""
        self._register_reference(reference)
        return reference["name"]

    # ---------------------------------------------------- village schemas and material institutions
    def affordance_data(self, name):
        return dict(self.E.AFFORDANCES[name])

    def observation_schema(self, name):
        return dict(self.E.OBSERVATION_TYPES[name])

    def set_weather(self, weather):
        """Set an environmental condition; residents may observe it, but it is not a resident fact."""
        spec = self.E.WEATHER[weather]
        self.eng.set_attr(self._town, "weather", weather)
        self.eng.set_attr(self._town, "rain", float(spec["rain"]))
        self.eng.set_attr(self._town, "temperature", float(spec["temperature"]))
        self.eng.set_attr(self._town, "firewood_demand", float(spec["firewood_demand"]))
        self.eng.set_attr(self._town, "cold", 1.0 if weather in {"cold", "frost"} else 0.0)
        self.eng.set_attr(self._town, "wet", 1.0 if weather in {"rain", "wet", "storm"} else 0.0)

    def record_observation(self, observer, kind, **values):
        """Record a town observation and attach who observed it; this creates no shared fact."""
        assert kind in self._observation_schemas, f"unknown observation schema: {kind}"
        obs = self.eng.add_node("Observation", {"kind": kind, **values})
        self.eng.add_edge_unchecked(self._town, "has_observation", obs)
        if observer is not None:
            self.eng.add_edge_unchecked(self._actors[observer], "made_observation", obs)
        return obs

    def actor_observations(self, actor, kind=None):
        """The observations this resident made (their own record, not a town fact), oldest first."""
        self._actor(actor)
        out = []
        for node in self.eng.neighbours(self._actors[actor], "made_observation"):
            attrs = dict(self.eng.node(node)["attrs"])
            if kind is None or attrs.get("kind") == kind:
                out.append(attrs)
        return out
    def calendar(self):
        """Read the canonical clock without turning time into a town fact."""
        a = self.eng.node(self._town)["attrs"]
        return {k: a.get(k) for k in ("clock", "day", "hour", "week", "year", "season", "weather")}

    def _advance_calendar(self):
        a = self.eng.node(self._town)["attrs"]
        clock = float(a.get("clock", 0.0))
        time = self.E.TIME
        ticks_per_day = float(time["ticks_per_day"])
        day = int(clock // ticks_per_day)
        hour = float(time["start_hour"]) + (clock % ticks_per_day) * (float(time["hours_per_day"]) / ticks_per_day)
        year_day = day % int(time["days_per_year"])
        season = None
        for name, start in time["season_start_day"].items():
            if year_day >= int(start):
                season = name
        self.eng.set_attr(self._town, "day", float(day))
        self.eng.set_attr(self._town, "hour", hour % float(time["hours_per_day"]))
        self.eng.set_attr(self._town, "week", float(day // int(time["days_per_week"])))
        self.eng.set_attr(self._town, "year", float(day // int(time["days_per_year"]) + 1))
        if season != a.get("season"):
            self.eng.set_attr(self._town, "season", season)
        if abs(hour % float(time["hours_per_day"]) - float(time["start_hour"])) < 1e-9:
            self._set_daily_weather(day, season)

    def _set_daily_weather(self, day, season):
        options = self.E.SEASONS.get(season, {}).get("weather", ("clear",))
        # Deterministic weather is still variable: the map seed controls it,
        # and the resulting weather remains an observation residents must make.
        options = tuple(option for option in options if option in self.E.WEATHER)
        weather = options[self._rng.randrange(len(options))] if options else "clear"
        self.set_weather(weather)

    def observe_weather(self, observer):
        a = self.eng.node(self._town)["attrs"]
        return self.record_observation(observer, "weather", weather=a.get("weather", "clear"),
                                       rain=float(a.get("rain", 0.0)),
                                       temperature=float(a.get("temperature", 0.0)))

    def create_event(self, kind, *, subject="", detail="", observer=None, public=True, severity=0.0):
        """Create an observed event; it is not automatically known by residents."""
        event = self.eng.add_node("Event", {"kind": str(kind), "subject": str(subject),
                                             "detail": str(detail), "public": 1.0 if public else 0.0,
                                             "severity": float(severity), "day": float(self.calendar()["day"])})
        self.eng.add_edge_unchecked(self._town, "has_event", event)
        with _EVENT_LOG_LOCK:
            self._events[f"event:{len(self._events) + 1}"] = event
        if observer is not None:
            self.eng.add_edge_unchecked(self._actors[observer], "observed_event", event)
        return event

    def observe_event(self, observer, event):
        """Give one resident an explicit observation of an existing event."""
        self._actor(observer)
        if event not in self._events.values():
            raise KeyError("unknown world event")
        self.eng.add_edge_unchecked(self._actors[observer], "observed_event", event)
        return event

    def utterances_from(self, first_utterance):
        """A stable snapshot of the utterance log from one position (TG05).

        A threaded commit may append while a unit records speech witnesses;
        copying under the event-log lock keeps that observer from seeing a
        transient dictionary.
        """
        with _EVENT_LOG_LOCK:
            return list(self._utterances.values())[first_utterance:]

    def event_data(self, event):
        return dict(self.eng.node(event)["attrs"])

    def write_article(self, reporter, event, *, headline=None, body=None, bias=0.0, confidence=1.0):
        """Render an article from a reporter's observation, without minting a town fact."""
        if event not in self.eng.nodes() or not self.eng.has_edge(self._actors[reporter], "observed_event", event):
            return None
        ev = self.eng.node(event)["attrs"]
        headline = headline or f"{ev.get('kind', 'Event').replace('_', ' ').title()} in Bigville"
        body = body or ev.get("detail", "No further details were recorded.")
        article = self.eng.add_node("Article", {"headline": str(headline), "body": str(body),
                                                 "bias": float(bias), "confidence": float(confidence),
                                                 "day": float(self.calendar()["day"]), "published": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_article", article)
        self.eng.add_edge_unchecked(article, "about", event)
        self.eng.add_edge_unchecked(self._actors[reporter], "wrote_article", article)
        self._articles[f"article:{len(self._articles) + 1}"] = article
        return article

    def publish_article(self, article, *, paper="The Bigville Times", copies=0):
        if article not in self.eng.nodes():
            return None
        edition = self.eng.add_node("Edition", {"title": paper, "day": float(self.calendar()["day"]),
                                                  "printed": 1.0, "copies": float(copies)})
        self.eng.add_edge_unchecked(self._town, "has_edition", edition)
        self.eng.add_edge_unchecked(edition, "contains", article)
        self.eng.set_attr(article, "published", 1.0)
        self._editions[f"edition:{len(self._editions) + 1}"] = edition
        if copies:
            self.set_stock("newspaper", self.qty("newspaper") + float(copies))
        return edition

    def print_newspaper(self, reporter, event, *, headline=None, body=None, copies=20, bias=0.0):
        article = self.write_article(reporter, event, headline=headline, body=body, bias=bias)
        return self.publish_article(article, copies=copies) if article is not None else None

    def give_newspaper(self, reader, edition):
        if not self._store_open(reader):
            self._refuse("store_locked")
            return None
        if self.qty("newspaper") < 1.0 or edition not in self.eng.nodes():
            return None
        self.set_stock("newspaper", self.qty("newspaper") - 1.0)
        copy = self.eng.add_node("NewspaperCopy", {"day": float(self.calendar()["day"])})
        self.eng.add_edge_unchecked(self._actors[reader], "holds", copy)
        self.eng.add_edge_unchecked(copy, "of_edition", edition)
        self._newspaper_copies[f"copy:{len(self._newspaper_copies) + 1}"] = copy
        self._record_handover("give_newspaper", "newspaper", 1.0, ("store", "store"), self._actor_endpoint(reader))
        return copy

    def read_newspaper(self, reader, copy):
        if copy not in self.eng.nodes() or not self.eng.has_edge(self._actors[reader], "holds", copy):
            return None
        if float(self.eng.node(self._actors[reader])["attrs"].get("literacy", 0.0)) < self.E.LIT_FUNCTIONAL:
            return None
        editions = list(self.eng.neighbours(copy, "of_edition"))
        if not editions:
            return None
        edition = editions[0]
        articles = list(self.eng.neighbours(edition, "contains"))
        for article in articles:
            self.eng.add_edge_unchecked(self._actors[reader], "read_article", article)
        return [dict(self.eng.node(article)["attrs"]) for article in articles]

    def household_kind_for(self, role=None, group=None):
        """The household kind a resident lives in (HOUSEHOLDS): the first kind that lists the role,
        else the first kind that lists the cast group, else the kind marked fallback."""
        kinds = self.E.HOUSEHOLDS
        for kind, spec in kinds.items():
            if role is not None and role in spec.get("roles", ()):
                return kind
        for kind, spec in kinds.items():
            if group is not None and group in spec.get("groups", ()):
                return kind
        for kind, spec in kinds.items():
            if spec.get("fallback"):
                return kind
        raise KeyError("HOUSEHOLDS has no fallback kind for residents outside its roles and groups")

    def _land_holder_roles(self):
        """Roles whose holders own founding parcels (land_roles of each household kind)."""
        return {role for spec in self.E.HOUSEHOLDS.values() for role in spec.get("land_roles", ())}

    def _registrar_roles(self):
        """Roles that keep the land register (GOVERNANCE_OFFICES entries marked registrar)."""
        return {role for role, spec in self.E.GOVERNANCE_OFFICES.items() if spec.get("registrar")}

    def add_household(self, name, *, kind=None, assets=None, home_cell=None):
        if kind is None:
            kind = self.household_kind_for()
        spec = self.E.HOUSEHOLDS[kind]
        h = self.eng.add_node("Household", {"name": name, "kind": kind,
                                             "food_need": 0.0, "water_need": 0.0,
                                     "fuel_need": 0.0, "fuel_short": 0.0, "shelter": 1.0,
                                             "assets": ",".join(assets or spec["assets"])})
        self.eng.add_edge_unchecked(self._town, "has_household", h)
        self._households[name] = h
        homes = self._map_layout.get("homes", []) if self._map_layout else []
        if home_cell is None and homes:
            home_cell = tuple(homes[self._next_home_index % len(homes)])
            self._next_home_index += 1
        if home_cell is not None and tuple(home_cell) in self._map_cells:
            cell = tuple(home_cell)
            self._household_cells[name] = h
            self._attach_at_cell(h, cell)
            self.eng.add_edge_unchecked(h, "home_at", self._map_cells[cell])
        return h

    def assign_household(self, actor, household):
        h = self._households[household]
        for old in list(self.eng.neighbours(self._actors[actor], "member_of")):
            self.eng.remove_edge_unchecked(self._actors[actor], "member_of", old)
            self.eng.remove_edge_unchecked(old, "has_member", self._actors[actor])
        self.eng.add_edge_unchecked(self._actors[actor], "member_of", h)
        self.eng.add_edge_unchecked(h, "has_member", self._actors[actor])
        self.eng.set_attr(self._actors[actor], "household", household)
        return household

    def household_members(self, household):
        h = self._households[household]
        return {self.eng.node(n)["attrs"].get("name", "")
                for n in self.eng.neighbours(h, "has_member")}

    def add_land(self, name, *, use="arable", soil="loam", area=1.0, cell=None, household=None):
        assert use in self.E.LAND_USES and soil in self.E.SOILS
        spec = self.E.SOILS[soil]
        capacity = float(self.E.NITROGEN["capacity_per_area"]) * float(area)
        n = self.eng.add_node("Land", {"name": name, "use": use, "soil": soil,
                                        "area": float(area), "fertility": float(spec["fertility"]),
                                        "moisture": 0.0, "erosion": float(spec["erosion"]), "fallow": 0.0,
                                        "nitrogen": min(capacity, float(spec.get("nitrogen", 0.0)) * float(area)),
                                        "nitrogen_capacity": capacity})
        self.eng.add_edge_unchecked(self._town, "has_land", n)
        self._land[name] = n
        farms = self._map_layout.get("farms", []) if self._map_layout else []
        if cell is None and farms:
            cell = tuple(farms[self._next_farm_index % len(farms)])
            self._next_farm_index += 1
        if cell is not None:
            cell = tuple(cell)
            self._land_cells[name] = n
            self._attach_at_cell(n, cell)
        if household is not None:
            self.eng.add_edge_unchecked(n, "held_by_household", self._households[household])
            self.eng.add_edge_unchecked(self._households[household], "holds_land", n)
            self.eng.set_attr(n, "household", household)
        return n

    # ---------------------------------------------------- land ownership and the records office
    def _holder_node(self, holder, holder_kind=None):
        if holder_kind == "household" or (holder_kind is None and holder in self._households):
            return self._households[holder], "household"
        if holder_kind == "resident" or (holder_kind is None and holder in self._actors):
            return self._actors[holder], "resident"
        raise KeyError(f"unknown land holder: {holder}")

    def _require_clerk(self, clerk):
        """The actor must hold a registrar office in the pack's GOVERNANCE_OFFICES."""
        registrars = self._registrar_roles()
        role = self.eng.node(self._actors[clerk])["attrs"].get("role")
        assert role in registrars, f"{clerk} does not hold a registrar office ({', '.join(sorted(registrars))})"

    def _register_title(self, clerk, land, holder, *, holder_kind=None, tenure="freehold",
                        basis="grant", effective=None, witnesses=(), deed=None, occupant=None):
        # Role labels do not make a register entry authoritative.
        assert land in self._land and tenure in self.E.LAND_TENURE
        holder_node, resolved_kind = self._holder_node(holder, holder_kind)
        old = self._titles.get(land)
        if old is not None:
            self.eng.set_attr(old, "current", 0.0)
            self.eng.remove_edge_unchecked(self._land[land], "current_title", old)
        record_id = f"{land}:{len([t for t in self._titles.values() if t]) + 1}"
        title = self.eng.add_node("LandTitle", {"record_id": record_id, "parcel": land,
                                                 "holder": holder, "holder_kind": resolved_kind,
                                                 "tenure": tenure, "basis": basis,
                                                 "effective": effective if effective is not None else float(self.eng.node(self._town)["attrs"].get("period", 0.0)),
                                                 "current": 1.0, "occupant": occupant or "",
                                                 "witnesses": ",".join(witnesses)})
        self.eng.add_edge_unchecked(self._town, "has_land_title", title)
        self.eng.add_edge_unchecked(self._land[land], "has_title", title)
        self.eng.add_edge_unchecked(self._land[land], "current_title", title)
        self.eng.add_edge_unchecked(holder_node, "holds_land_title", title)
        if old is not None:
            self.eng.add_edge_unchecked(title, "supersedes", old)
        self._titles[land] = title
        return title

    def register_land(self, clerk, land, holder, *, holder_kind=None, tenure="freehold",
                      basis="grant", effective=None, witnesses=()):
        """Create an initial title record; readers form their own interpretation."""
        assert land not in self._titles, f"{land} already has a registered title"
        return self._register_title(clerk, land, holder, holder_kind=holder_kind, tenure=tenure,
                                     basis=basis, effective=effective, witnesses=witnesses)

    def write_deed(self, clerk, deed_type, land, *, from_holder="", to_holder="", witnesses=(),
                   term=None, consideration=0.0, notes=""):
        """Create a physical deed record, independent of the writer's role."""
        assert deed_type in self.E.DEED_TYPES and land in self._land
        deed_id = f"deed:{len(self._deeds) + 1}"
        deed = self.eng.add_node("WrittenDeed", {"record_id": deed_id, "kind": "deed",
                                                  "deed_type": deed_type, "parcel": land,
                                                  "from_holder": from_holder, "to_holder": to_holder,
                                                  "witnesses": ",".join(witnesses),
                                                  "term": float(term if term is not None else 0.0),
                                                  "consideration": float(consideration),
                                                  "notes": notes, "registered": 0.0})
        self.eng.add_edge_unchecked(self._actors[clerk], "wrote_deed", deed)
        self.eng.add_edge_unchecked(self._land[land], "has_deed", deed)
        self._deeds[deed_id] = deed
        return deed

    def register_deed(self, clerk, deed):
        """Append a deed to the register as evidence, without deciding title."""
        attrs = self.eng.node(deed)["attrs"]
        assert attrs.get("registered") == 0.0 and attrs["parcel"] in self._land
        self.eng.set_attr(deed, "registered", 1.0)
        self.eng.add_edge_unchecked(self._town, "has_registered_deed", deed)
        return deed

    def read_deed(self, reader, deed):
        """Read a deed from the archive; reading the deed is distinct from holding its title."""
        assert self._can_read(reader), f"{reader} cannot read the deed archive"
        attrs = self.eng.node(deed)["attrs"]
        fact = self.eng.add_node("Fact", {"name": f"deed_{attrs['record_id']}",
                                           "kind": "resident_deed_knowledge",
                                           "abstraction": "operational", "subject": attrs["parcel"],
                                           "predicate": "has_deed", "object": attrs["record_id"],
                                           "deed_type": attrs["deed_type"],
                                           "registered": attrs.get("registered", 0.0)})
        self.eng.add_edge_unchecked(self._actors[reader], "knows_deed", fact)
        self.eng.add_edge_unchecked(self._actors[reader], "read_deed", deed)
        return attrs["record_id"]

    def title_record(self, land): return self._titles.get(land)

    def land_owner(self, land):
        title = self._titles.get(land)
        return self.eng.node(title)["attrs"].get("holder") if title is not None else None

    def land_tenure(self, land):
        title = self._titles.get(land)
        return self.eng.node(title)["attrs"].get("tenure") if title is not None else None

    def land_record(self, land):
        title = self._titles.get(land)
        if title is None:
            return None
        return dict(self.eng.node(title)["attrs"])

    def inspect_land_record(self, reader, land):
        """Observe the public register; observation alone does not assign belief."""
        assert land in self._land and self._titles.get(land) is not None
        assert self._can_read(reader), f"{reader} cannot read the land register"
        self.eng.add_edge_unchecked(self._actors[reader], "inspected_land_record", self._titles[land])
        return self.land_record(land)

    def file_land_dispute(self, complainant, land, *, kind="boundary", against="", grounds=""):
        assert land in self._land and kind in self.E.LAND_DISPUTES
        dispute_id = f"dispute:{len(self._land_disputes) + 1}"
        n = self.eng.add_node("LandDispute", {"record_id": dispute_id, "parcel": land, "kind": kind,
                                               "complainant": complainant, "against": against,
                                               "grounds": grounds, "status": "open", "outcome": "",
                                               **self._civic_record("justice", "case")})
        self.eng.add_edge_unchecked(self._town, "has_land_dispute", n)
        self.eng.add_edge_unchecked(self._land[land], "has_dispute", n)
        if complainant in self._actors:
            self.eng.add_edge_unchecked(self._actors[complainant], "filed_dispute", n)
        self._land_disputes[dispute_id] = n
        return n

    def resolve_land_dispute(self, adjudicator, dispute, *, outcome, winner="", remedy=""):
        """Record a resident's interpretation of a land dispute.

        Kept under its historical name for callers, this does not resolve the
        dispute globally, change title, or apply a remedy. Those are decisions
        residents may make and actions they may separately take.
        """
        speaker = self._actors[adjudicator]
        attrs = self.eng.node(dispute)["attrs"]
        statement_id = f"land-dispute-statement:{len(self.eng.neighbours(dispute, 'has_statement')) + 1}"
        statement = self.eng.add_node("LandDisputeStatement", {
            "record_id": statement_id,
            "speaker": adjudicator,
            "reported_outcome": str(outcome),
            "claimed_winner": str(winner),
            "suggested_remedy": str(remedy),
            "day": float(self.calendar()["day"]),
            **self._civic_record("justice", "statement"),
        })
        self.eng.add_edge_unchecked(dispute, "has_statement", statement)
        self.eng.add_edge_unchecked(self._town, "has_land_dispute_statement", statement)
        self.eng.add_edge_unchecked(speaker, "made_land_dispute_statement", statement)
        return statement

    def add_water_source(self, name, *, kind="well", capacity=None):
        spec = self.E.WATER_SOURCES[kind]
        n = self.eng.add_node("WaterSource", {"name": name, "kind": kind,
                                               "capacity": float(capacity if capacity is not None else spec["yield"]),
                                               "quality": float(spec["quality"]), "available": 1.0})
        self.eng.add_edge_unchecked(self._town, "has_water_source", n)
        self._water_sources[name] = n
        anchor = self._anchor_for_building("wellhouse")
        self._attach_at_cell(n, anchor)
        return n

    def add_infrastructure(self, name, *, kind, condition=1.0):
        spec = self.E.INFRASTRUCTURE[kind]
        n = self.eng.add_node("Infrastructure", {"name": name, "kind": kind,
                                                  "condition": float(condition),
                                                  "capacity": float(spec["capacity"]),
                                                  "failure_risk": float(spec["failure_risk"]),
                                                  "affordance": spec["affordance"]})
        self.eng.add_edge_unchecked(self._town, "has_infrastructure", n)
        self._infrastructure[name] = n
        self._attach_at_cell(n, self._anchor_for_building(kind))
        return n

    def infrastructure_condition(self, name):
        return round(float(self.eng.node(self._infrastructure[name])["attrs"]["condition"]), 4)

    def maintain_infrastructure(self, operator, name, *, labour=1.0):
        """Repair a mapped infrastructure node using its data-defined materials."""
        self._actor(operator)
        if name not in self._infrastructure:
            return self._refuse("unknown_target")
        attrs = self.eng.node(self._actors[operator])["attrs"]
        node = self._infrastructure[name]
        if self._turn > 0 and self.actor_position(operator) != self.map_position_node(node):
            return self._refuse("not_in_reach")
        spec = self.E.INFRASTRUCTURE[self.eng.node(node)["attrs"]["kind"]]
        amount = min(float(labour), max(0.0, 1.0 - self.infrastructure_condition(name)))
        if amount <= 0.0:
            return self._refuse("not_needed")
        required = {kind: amount for kind in spec.get("maintenance", ())}
        if required and not self._store_open(operator):
            return self._refuse("store_locked")
        if any(self.qty(kind) < qty for kind, qty in required.items()):
            return self._refuse("out_of_stock")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(operator, "maintain"):
            return self._refuse("slot_used")
        for kind, qty in required.items():
            self.set_stock(kind, self.qty(kind) - qty)
        self.eng.set_attr(node, "condition", min(1.0, self.infrastructure_condition(name) + amount))
        self.eng.add_edge_unchecked(self._actors[operator], "maintained", node)
        return True

    def add_shock(self, name, *, kind, duration=None):
        spec = self.E.SHOCKS[kind]
        d = duration if duration is not None else spec["duration"][0]
        n = self.eng.add_node("Shock", {"name": name, "kind": kind, "remaining": float(d),
                                         "active": 1.0, "effects": ",".join(spec["effects"])})
        self.eng.add_edge_unchecked(self._town, "has_shock", n)
        return n

    # ---------------------------------------------------- map economy: deposits, shops, and goods
    def add_deposit(self, kind, cell, *, stock=0.0, growback=0.0, capacity=0.0):
        """Add a renewable natural-resource site to the canonical map."""
        cell = tuple(cell)
        assert cell in self._map_cells, f"deposit cell {cell} not walkable"
        n = self.eng.add_node("ResourceDeposit", {"kind": kind, "stock": float(stock),
                                                    "growback": float(growback),
                                                    "capacity": float(capacity), "epoch": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_deposit", n)
        self._attach_at_cell(n, cell)
        self._resource_deposits[kind] = n
        return n

    def resource_stock(self, kind):
        return round(float(self.eng.node(self._resource_deposits[kind])["attrs"]["stock"]), 4)

    def extract_resource(self, kind, amount=1.0, *, extractor=None):
        """Extract available resource; a running simulation requires an extractor."""
        if extractor is not None and self._turn > 0 and not self._major_dispatch \
                and not self._claim_major_action(extractor, "extract"):
            return 0.0
        n = self._resource_deposits[kind]
        attrs = self.eng.node(n)["attrs"]
        amount = min(float(amount), float(attrs["stock"]))
        if amount <= 0:
            return 0.0
        self.eng.set_attr(n, "stock", float(attrs["stock"]) - amount)
        self.set_stock(kind, self.qty(kind) + amount)
        return amount

    # ---------------------------------------------------- gathering sites (Phase 004)
    def add_gathering_site(self, kind, cell, *, stock=None, growback=None, capacity=None):
        """Place the site that a gathering recipe's `gathered_from` names, on a walkable cell.
        Stock, growback, and capacity default to the pack's GATHERING_SITES row. The founding town places
        its own sites (see _place_gathering_sites); a bare or scenario world adds one here."""
        if kind not in self.E.GATHERING_SITES:
            raise ValueError(f"'{kind}' is not a GATHERING_SITES kind in data pack '{self.data_pack}'")
        if kind in self._gathering_sites:
            raise ValueError(f"gathering site '{kind}' is already placed")
        row = self.E.GATHERING_SITES[kind]
        cell = tuple(cell)
        assert cell in self._map_cells, f"gathering site cell {cell} not walkable"
        capacity = float(row["capacity"] if capacity is None else capacity)
        stock = float(row["stock"] if stock is None else stock)
        growback = float(row["growback"] if growback is None else growback)
        n = self.eng.add_node("ResourceDeposit", {"kind": kind, "stock": stock, "growback": growback,
                                                    "capacity": capacity, "epoch": 0.0, "gathering": 1.0})
        self.eng.add_edge_unchecked(self._town, "has_gathering_site", n)
        self._attach_at_cell(n, cell)
        self._gathering_sites[kind] = {"node": n, "cell": cell}
        return n

    def _place_gathering_sites(self, layout):
        """Place the founding map's gathering sites (layout["sites"], from build_town_100)."""
        for kind, cell in layout.get("sites", {}).items():
            self.add_gathering_site(kind, tuple(cell))

    def gathering_site_cell(self, kind):
        """The cell of the site a gathering kind names, or None if no site is placed."""
        site = self._gathering_sites.get(kind)
        return None if site is None else site["cell"]

    def gathering_stock(self, kind):
        """The stock left at a gathering site, or None if no site is placed."""
        site = self._gathering_sites.get(kind)
        if site is None:
            return None
        return round(float(self.eng.node(site["node"])["attrs"]["stock"]), 4)

    def _site_has_batch(self, kind, recipe_name):
        """True if the site of `kind` holds one batch of `recipe_name`'s output (location not checked)."""
        site = self._gathering_sites.get(kind)
        if site is None:
            return False
        batch = float(self._recipe_specs[recipe_name]["out"][1])
        return float(self.eng.node(site["node"])["attrs"]["stock"]) + 1e-9 >= batch

    def _site_supplies(self, kind, recipe_name, cell):
        """True if the site of `kind` stands on `cell` and holds one batch of `recipe_name`'s output."""
        site = self._gathering_sites.get(kind)
        if site is None or cell is None or tuple(cell) != site["cell"]:
            return False
        return self._site_has_batch(kind, recipe_name)

    def _at_gathering_site(self, actor, recipe_name):
        """A gathering recipe is admissible only for an actor standing on the site of its kind, with a
        batch of stock there. A recipe with no gathered_from is not bound to a site."""
        kind = self._recipe_specs.get(recipe_name, {}).get("gathered_from")
        if not kind:
            return True
        return self._site_supplies(kind, recipe_name, self.actor_position(actor))

    def _draw_gathering_site(self, kind, recipe_name):
        """A batch of a gathering recipe is taken from its site's stock as the job opens."""
        site = self._gathering_sites[kind]
        batch = float(self._recipe_specs[recipe_name]["out"][1])
        stock = float(self.eng.node(site["node"])["attrs"]["stock"])
        self.eng.set_attr(site["node"], "stock", stock - batch)

    def _regrow_gathering_sites(self):
        """Once a period (a day, TIME.ticks_per_period), each gathering site regrows by its growback, up to
        its capacity."""
        for site in self._gathering_sites.values():
            a = self.eng.node(site["node"])["attrs"]
            self.eng.set_attr(site["node"], "stock",
                              min(float(a["capacity"]), float(a["stock"]) + float(a["growback"])))
            self.eng.set_attr(site["node"], "epoch", float(a.get("epoch", 0.0)) + 1.0)

    def add_store(self, cell, kinds=(), *, locked=None, keys_required=None):
        """Place the town store on a cell. `locked` and `keys_required` (Phase 030) override the pack's
        STORE_LOCK founding state; left as None, the store keeps that state (unlocked by default)."""
        cell = tuple(cell)
        assert cell in self._map_cells, f"store cell {cell} not walkable"
        self.eng.add_edge_unchecked(self._store, "at_cell", self._map_cells[cell])
        self.eng.set_attr(self._store, "market_x", float(cell[0]))
        self.eng.set_attr(self._store, "market_y", float(cell[1]))
        if locked is not None:
            self.eng.set_attr(self._store_lock_node(), "locked", 1.0 if locked else 0.0)
        if keys_required is not None:
            self.eng.set_attr(self._store_lock_node(), "keys_required", float(keys_required))
        for kind in kinds:
            self.set_stock(kind, self.qty(kind))
        return self._store

    def add_shop(self, trade, cell, *, input_kind, output_kind, recipe_in=1.0,
                 recipe_out=1.0, price=None, is_open=None):
        if price is None:
            price = self.E.PRICE_DEFAULTS["shop_price"]
        if is_open is None:
            is_open = self.E.PRICE_DEFAULTS["shop_is_open"]
        cell = tuple(cell)
        assert cell in self._map_cells, f"shop cell {cell} not walkable"
        shop = self.eng.add_node("Shop", {"trade": trade, "input_kind": input_kind,
                                            "output_kind": output_kind,
                                            "recipe_in": float(recipe_in),
                                            "recipe_out": float(recipe_out),
                                            "price": float(price),
                                            "coin": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_shop", shop)
        self._attach_at_cell(shop, cell)
        self._shops[trade] = shop
        # This is a public expectation about a conventional place, not a fact
        # naming its future attendant.  The person encountered there is found
        # only when the resident arrives and speaks.
        self._market_expectation_specs[trade] = {
            "trade": trade, "kind": output_kind, "cell": cell,
            # Opening is a resident-held frame seeded from the scenario.  It
            # is intentionally not an attribute of the town/shop node.
            "opening_expected": float(is_open),
            "predicate": "offers_during_opening_hours"}
        for actor in self._actors:
            self._seed_market_expectation(actor, trade)
        return shop

    def shop_position(self, trade):
        return self.map_position_node(self._shops[trade])

    def _at_shop(self, actor, trade):
        """Whether the resident and shop occupy the same physical map cell."""
        return (trade in self._shops
                and self.actor_position(actor) == self.shop_position(trade))

    def _seed_market_expectation(self, actor, trade):
        """Seed a resident's expectation without naming a shop attendant."""
        if actor not in self._actors or trade not in self._market_expectation_specs:
            return None
        held = self._actor_market_expectations.setdefault(actor, {})
        if trade in held:
            return held[trade]
        spec = self._market_expectation_specs[trade]
        fact = self.eng.add_node("Fact", {
            "name": f"expects_{trade}_offers_{spec['kind']}",
            "kind": "market_expectation", "trade": trade,
            "subject": trade, "predicate": spec["predicate"],
            "object": spec["kind"], "location_x": float(spec["cell"][0]),
            "location_y": float(spec["cell"][1]),
            "opening_expected": float(spec["opening_expected"]), "confidence": 0.7})
        self.eng.add_edge_unchecked(self._actors[actor], "expects_market", fact)
        held[trade] = fact
        return fact

    def market_expectations(self, actor):
        """Return the resident's held shop-level expectations."""
        self._actor(actor)
        return {trade: dict(self.eng.node(fact)["attrs"])
                for trade, fact in self._actor_market_expectations.get(actor, {}).items()}

    def _market_counterparty(self, buyer, trade, kind=None):
        """Find a person physically present at a conventional market location.

        The buyer's expectation supplies the place and commodity.  This lookup
        is an observation of who is there now, not a seeded identity belief.
        """
        if trade not in self._shops:
            return None
        cell = self.shop_position(trade)
        present = [name for name in self._actors
                   if name != buyer and self.is_alive(name)
                   and self.actor_position(name) == cell]
        if kind is not None:
            offered = [name for name in present
                       if self.inventory_qty(name, kind) >= 1.0]
            if offered:
                return offered[0]
            # This lookup reports only physical presence and possession.
            return None
        return present[0] if present else None

    def _shopkeeper_for_trade(self, trade):
        """Find the person conventionally working at a shop's mapped cell.

        The shop is only a location convention.  The conversational and
        economic counterpart is always a resident, when one is present.
        """
        if trade not in self._shops:
            return None
        cell = self.shop_position(trade)
        candidates = []
        for name, node in self._actors.items():
            attrs = self.eng.node(node)["attrs"]
            work_cell = (int(round(float(attrs.get("work_x", -999)))) ,
                         int(round(float(attrs.get("work_y", -999)))))
            if work_cell != cell and self.actor_position(name) != cell:
                continue
            trades = set(str(attrs.get("trades", "")).split(","))
            role = str(attrs.get("role", ""))
            if trade in trades or role == trade or role in self.E.SHOP_CHAINS.get(trade, {}).get("keeper_roles", ()):
                candidates.append(name)
        return next((name for name in candidates if self.is_alive(name)), None) or (candidates[0] if candidates else None)

    def stock_person(self, seller, kind, amount, *, price=None, willing=True):
        """Put a physical good in a person's inventory as a voluntary offer."""
        if price is None:
            price = self.E.PRICE_DEFAULTS["stock_price"]
        self._actor(seller)
        if not self._store_open(seller):
            self._refuse("store_locked")
            return False
        if not self._move_stock_to_inventory(seller, kind, amount):
            return False
        self._record_handover("stock", kind, amount, ("store", "store"), self._actor_endpoint(seller))
        node = self._actor(seller)
        self.eng.set_attr(node, "sell_price", float(price))
        self.eng.set_attr(node, "sell_willing", 1.0 if willing else 0.0)
        return True

    def coin(self, actor):
        return round(float(self.eng.node(self._actors[actor])["attrs"].get("coin", 0.0)), 4)

    def set_coin(self, actor, amount):
        self.eng.set_attr(self._actors[actor], "coin", max(0.0, float(amount)))

    def quote(self, trade):
        shop = self._shops[trade]
        a = self.eng.node(shop)["attrs"]
        return round(float(a.get("price", 0.0)), 4)

    def _inventory_container(self, actor):
        return self._containers[self._actor_inventories[actor]]

    def _inventory_stock(self, actor, kind, *, create=False):
        _, inners = self._inventory_container(actor)
        if kind not in inners and create:
            container = self._inventory_container(actor)[0]
            container_kind = self.eng.node(container)["attrs"].get("kind", "carrier")
            inners[kind] = self._new_inner_stock(container, container_kind, kind)
        return inners.get(kind)

    def inventory_qty(self, actor, kind):
        stock = self._inventory_stock(actor, kind)
        return round(float(self.eng.node(stock)["attrs"].get("qty", 0.0)), 4) if stock else 0.0

    def inventory(self, actor):
        """Return the actor's held physical goods, excluding empty inventory piles."""
        _, inners = self._inventory_container(actor)
        return {kind: self.inventory_qty(actor, kind) for kind in inners
                if self.inventory_qty(actor, kind) > 0.0}

    def held_items(self, actor):
        """Return discrete physical items currently carried by an actor.

        Bulk stock remains exposed by :meth:`inventory`; this read-off covers
        tools, tableware, and other individual objects held in a hand or on a
        carrier.  It deliberately returns instance data so a renderer can
        show the actual pick, not merely the abstract fact that picks exist.
        """
        node = self._actor(actor)
        result = []
        seen = set()
        for edge, location in (("holds_in_hand", "hand"),
                               ("holds_tableware", "tableware"),
                               ("holds", "carried")):
            for item in self.eng.neighbours(node, edge):
                if item in seen:
                    continue
                seen.add(item)
                attrs = dict(self.eng.node(item)["attrs"])
                result.append({
                    "id": int(item.value),
                    "kind": str(attrs.get("kind", "item")),
                    "quantity": 1.0,
                    "location": location,
                    "condition": attrs.get("condition", 1.0),
                })
        return result

    def _move_stock_to_inventory(self, actor, kind, amount):
        amount = float(amount)
        if amount <= 0.0:
            return self._refuse("malformed")
        if self.qty(kind) < amount:
            return self._refuse("out_of_stock")
        inventory = self._inventory_container(actor)[0]
        # Phase 049: the carrier takes what fits by volume; the rest drops at their feet (the carry model's drop).
        used = self.used_volume(self._actor_inventories[actor])
        item_vol = float(self.item_volume(kind))
        room = max(0.0, self.capacity(self._actor_inventories[actor]) - used)
        fit = amount if item_vol <= 0.0 else min(amount, room / item_vol + 1e-9)
        excess = amount - fit
        arriving = self._pile_condition(self._stock.get(kind))
        self.set_stock(kind, self.qty(kind) - amount)
        if fit > 0.0:
            stock = self._inventory_stock(actor, kind, create=True)
            self._mix_freshness(stock, fit, arriving)
            self.eng.set_attr(stock, "qty", float(self.eng.node(stock)["attrs"].get("qty", 0.0)) + fit)
            self.eng.add_edge_unchecked(self._actor(actor), "holds_food", stock)
        if excess > 0.0:
            self._drop_stock(actor, kind, excess)
        self._refresh_carry_state(actor)
        return True

    def _inventory_can_receive(self, actor, kind, amount=1.0):
        """Admissibility check for moving a bulk item into a resident carrier."""
        if actor not in self._actor_inventories or kind not in self._item_specs:
            return False
        amount = float(amount)
        if amount <= 0.0:
            return False
        inventory = self._actor_inventories[actor]
        return (self.used_volume(inventory) + amount * self.item_volume(kind)
                <= self.capacity(inventory) + 1e-9)

    def _can_put(self, actor, container, kind, amount=1.0):
        """Mirror ``put``'s physical preconditions for affordance publication."""
        if container not in self._containers or kind not in self._item_specs:
            return False
        amount = float(amount)
        node = self._containers[container][0]
        if (amount <= 0.0 or self.inventory_qty(actor, kind) < amount
                or not self._container_accessible(actor, container)):
            return False
        cell = self.container_position(container)
        if self._turn > 0 and cell is not None and self.actor_position(actor) != cell:
            return False
        return self._container_can_receive(container, kind, amount)

    def _container_can_receive(self, container, kind, amount=1.0):
        """Physical capacity gate independent of who is standing at the vessel."""
        if container not in self._containers or kind not in self._item_specs:
            return False
        amount = float(amount)
        attrs = self.eng.node(self._containers[container][0])["attrs"]
        return (amount > 0.0
                and self.used_volume(container) + amount * self.item_volume(kind)
                <= self.capacity(container) + 1e-9
                and (not self.is_fluid(kind) or float(attrs.get("watertight", 0.0)) == 1.0)
                and self.contents_weight(container) + amount * self.item_weight(kind)
                <= float(attrs.get("max_load", 1e18)) + 1e-9)

    def _drop_stock(self, actor, kind, amount):
        """Leave a physical pile at the resident's feet."""
        amount = float(amount)
        if amount <= 0.0:
            return None
        node = self.eng.add_node("DroppedStock", {
            "kind": str(kind), "qty": amount, "weight": self.item_weight(kind),
            "volume": self.item_volume(kind), "dropped_by": str(actor),
            "turn": float(self._turn)})
        self.eng.add_edge_unchecked(self._town, "has_dropped_stock", node)
        cell = self.actor_position(actor)
        if cell in self._map_cells:
            self._attach_at_cell(node, cell)
        key = f"dropped:{len(self._dropped_stocks) + 1}"
        self._dropped_stocks[key] = node
        return node

    def _remove_inventory_stock(self, actor, kind, amount):
        stock = self._inventory_stock(actor, kind)
        amount = float(amount)
        if stock is None or amount <= 0.0 or self.inventory_qty(actor, kind) < amount:
            return False
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - amount)
        self._refresh_carry_state(actor)
        return True

    def _accept_stock(self, actor, kind, amount):
        """Accept stock into the carrier, dropping the newly accepted pile if extreme."""
        if not self._move_stock_to_inventory(actor, kind, amount):
            return False
        state = self._refresh_carry_state(actor)
        if state["will_drop"]:
            self._remove_inventory_stock(actor, kind, amount)
            dropped = self._drop_stock(actor, kind, amount)
            self.eng.set_attr(self._actor(actor), "last_carry_outcome", "dropped")
            self.eng.set_attr(self._actor(actor), "last_dropped_kind", str(kind))
            self.eng.set_attr(self._actor(actor), "last_dropped_node", int(dropped.value) if dropped is not None else -1.0)
        else:
            self.eng.set_attr(self._actor(actor), "last_carry_outcome", "held")
        return True

    def _move_inventory_to_stock(self, actor, kind, amount):
        amount = float(amount)
        stock = self._inventory_stock(actor, kind)
        if amount <= 0.0 or stock is None or self.inventory_qty(actor, kind) < amount:
            return False
        arriving = self._pile_condition(stock)
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - amount)
        self.set_stock(kind, self.qty(kind) + amount, condition=arriving)
        self._refresh_carry_state(actor)
        return True

    def _move_inventory_to_inventory(self, giver, recipient, kind, amount):
        """Move a held stock pile directly between two resident carriers. The giver gives all of `amount`; the
        recipient takes what fits by volume and the rest drops at their feet (Phase 049). Returns the amount the
        recipient took into their hands, or False when the giver does not hold it."""
        amount = float(amount)
        if amount <= 0.0 or self.inventory_qty(giver, kind) < amount:
            return self._refuse("out_of_stock")
        room = max(0.0, self.capacity(self._actor_inventories[recipient])
                    - self.used_volume(self._actor_inventories[recipient]))
        item_vol = float(self.item_volume(kind))
        fit = amount if item_vol <= 0.0 else min(amount, room / item_vol + 1e-9)
        excess = amount - fit
        source = self._inventory_stock(giver, kind)
        arriving = self._pile_condition(source)
        self.eng.set_attr(source, "qty", self.inventory_qty(giver, kind) - amount)
        if fit > 0.0:
            target = self._inventory_stock(recipient, kind, create=True)
            self._mix_freshness(target, fit, arriving)
            self.eng.set_attr(target, "qty", self.inventory_qty(recipient, kind) + fit)
        if excess > 0.0:
            self._drop_stock(recipient, kind, excess)
        self._refresh_carry_state(giver)
        self._refresh_carry_state(recipient)
        return fit

    def _give_discrete_item(self, giver, recipient, item, handover_kind="give"):
        if self._item_owner_edge(giver, item) is None:
            return self._refuse("not_held")
        kind = self.eng.node(item)["attrs"].get("kind", "")
        accepted = self._accept_discrete_item(recipient, item, giver=giver)
        if accepted:
            self.eng.add_edge_unchecked(self._actor(giver), "gave_item", item)
            self.eng.add_edge_unchecked(item, "given_to", self._actor(recipient))
            self._record_handover(handover_kind, kind, 1.0, self._actor_endpoint(giver), self._actor_endpoint(recipient))
        return accepted

    def give(self, giver, recipient, kind, amount=1.0, *, payment_kind=None,
             payment_amount=None, handover_kind="give"):
        """Physically hand a held good or coin to a nearby resident.

        Legacy payment arguments are accepted for call compatibility but have
        no world-side agreement semantics. The cognition layer must choose any
        payment as a separate physical transfer. ``handover_kind`` names the
        action recorded for the handover ("give", or "transfer" from that action).
        """
        amount = max(0.0, float(amount))
        if amount <= 0.0:
            return self._refuse("malformed")
        if recipient in self._shops:
            return self._refuse("wrong_target")
        self._actor(giver); self._actor(recipient)
        if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(giver, "give"):
            return self._refuse("slot_used")
        if (self._turn > 0 and self.actor_position(giver) != self.actor_position(recipient)):
            return self._refuse("not_in_reach")
        if not isinstance(kind, str):
            return self._give_discrete_item(giver, recipient, kind, handover_kind)
        if kind == "coin":
            if self.coin(giver) < amount:
                return self._refuse("out_of_stock")
            self.set_coin(giver, self.coin(giver) - amount)
            self.set_coin(recipient, self.coin(recipient) + amount)
        else:
            received = self._move_inventory_to_inventory(giver, recipient, kind, amount)
            if received is False:
                return False
            state = self._refresh_carry_state(recipient)
            if state["will_drop"] and received > 0.0:
                self._remove_inventory_stock(recipient, kind, received)
                dropped = self._drop_stock(recipient, kind, received)
                self.eng.set_attr(self._actor(recipient), "last_carry_outcome", "dropped")
                self.eng.set_attr(self._actor(recipient), "last_dropped_kind", str(kind))
                self.eng.set_attr(self._actor(recipient), "last_dropped_node",
                                  int(dropped.value) if dropped is not None else -1.0)
            elif received < amount - 1e-9:
                # Phase 049: the part that did not fit by volume was dropped at the recipient's feet.
                self.eng.set_attr(self._actor(recipient), "last_carry_outcome", "dropped")
                self.eng.set_attr(self._actor(recipient), "last_dropped_kind", str(kind))
            else:
                self.eng.set_attr(self._actor(recipient), "last_carry_outcome", "held")
        self.eng.add_edge_unchecked(self._actor(giver), "gave", self._actor(recipient))
        self._record_handover(handover_kind, kind, amount,
                              self._actor_endpoint(giver), self._actor_endpoint(recipient))
        return True

    def _physical_transfer_precheck(self, source, recipient, kind, amount=1.0):
        if source not in self._actors or recipient not in self._actors:
            return self._refuse("unknown_target")
        if (self.actor_position(source) is None
                or self.actor_position(source) != self.actor_position(recipient)):
            return self._refuse("not_in_reach")
        if isinstance(kind, str):
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return self._refuse("malformed")
            if amount <= 0.0:
                return self._refuse("malformed")
            if kind == "coin":
                if self.coin(source) < amount:
                    return self._refuse("out_of_stock")
                return True
            if self.inventory_qty(source, kind) < amount:
                return self._refuse("out_of_stock")
            # Phase 049: a recipient over capacity is no refusal; the part that does not fit drops at their feet.
            return True
        if self._item_owner_edge(source, kind) is None:
            return self._refuse("not_held")
        return True

    def _physical_transfer(self, source, recipient, kind, amount=1.0, *, handover_kind="give"):
        """Move an already-held physical good or object between nearby people.

        This deliberately has no trade, price, willingness, ownership, or
        utterance semantics.  The caller supplies the direction explicitly;
        world facts are limited to reach, possession, and the existing
        inventory capacity checks.
        """
        if not self._physical_transfer_precheck(source, recipient, kind, amount):
            return False
        # Reuse the compatibility implementation for the actual conserved
        # movement, but bypass its second turn-budget claim; transfer already
        # claimed the source actor's slot.
        old_dispatch = self._major_dispatch
        self._major_dispatch = True
        try:
            return self.give(source, recipient, kind, amount, handover_kind=handover_kind)
        finally:
            self._major_dispatch = old_dispatch

    def buy(self, buyer, trade, amount=1.0):
        """Retired compatibility name; purchase is a cognition choice.

        This method intentionally cannot create speech, decide acceptance, or
        move goods or coins. Use an explicit backend-selected transfer for
        each physical movement.
        """
        return False

    def purchase_utterance(self, buyer, seller, kind=None, amount=1.0):
        """Speak a purchase proposal to a person, without completing it.

        The legacy ``(buyer, trade, amount)`` spelling is accepted as a
        convenience and resolves the trade's conventional workplace to its
        resident. The shop is never the speech target.
        """
        self._actor(buyer)
        trade = seller if seller in self._shops else None
        if trade is not None:
            if isinstance(kind, (int, float)):
                amount = kind
            shop = self.eng.node(self._shops[trade])["attrs"]
            kind = str(shop.get("output_kind", "good"))
            seller = self._market_counterparty(buyer, trade, kind)
            if seller is None and self._turn == 0:
                candidate = self._shopkeeper_for_trade(trade)
                if candidate is not None and self.inventory_qty(candidate, kind) >= float(amount):
                    seller = candidate
        if seller not in self._actors or kind is None:
            return False
        self._actor(seller)
        kind = str(kind)
        quantity = int(amount) if float(amount).is_integer() else float(amount)
        # The purchase is a communicative goal held by the buyer's private
        # mind.  The occasion is part of the meaning so two otherwise
        # identical purchases are distinct goals; the language faculty may
        # choose which grounded parts of that meaning reach the surface.
        meaning = {
            "purchase": {
                "of": {kind: {"from": str(seller)}},
                "occasion": f"turn_{self._turn}_{buyer}_{seller}_{kind}_{quantity}",
            }
        }
        content = self._actor_minds[buyer].goal_utterance(seller, meaning)
        if not content:
            return False
        utterance = self.speak(
            buyer, seller, content,
            message={"act": "purchase", "slots": {
                "quantity": quantity, "item": kind, "seller": str(seller),
            }})
        if trade is not None:
            self.eng.set_attr(utterance, "market_trade", str(trade))
        self.eng.set_attr(utterance, "market_quantity", float(amount))
        self._speech_events.append({
            "turn": int(self._turn), "speaker": buyer, "target": seller,
            "kind": "purchase", "content": content,
            "heard": bool(self.eng.node(utterance)["attrs"].get("heard", 0.0)),
        })
        return utterance

    def sell_to_shop(self, seller, trade, kind, amount=1.0):
        """Retired settlement helper; sale terms and acceptance belong to agents.

        Goods and coins can still move through separately chosen physical
        transfers. A shop is not an agent, so this compatibility API cannot
        infer that it accepts goods or choose a price.
        """
        return False

    def sell_labor(self, actor, trade, wage=None):
        """Retired: labor agreement and wage terms require agent choices."""
        return False

    def give_food(self, giver, recipient, kind, amount=1.0):
        """Transfer owned food between residents; it is not a town-wide ration."""
        if not self.give(giver, recipient, kind, amount):
            return False
        self.eng.add_edge_unchecked(self._actor(giver), "gave_food", self._actor(recipient))
        return True

    def give_tableware(self, actor, kind):
        """Give an actor one physical mug/bowl/utensil from the founding stores."""
        spec = self._item_specs.get(kind, {})
        if not (spec.get("container") or spec.get("utensil")):
            raise ValueError(f"{kind} is not serving equipment")
        item = self.eng.add_node("ToolItem", {"kind": kind, "weight": self.item_weight(kind),
                                                "quality": 1.0,
                                                "condition": 1.0, "broken": 0.0})
        self.eng.add_edge_unchecked(self._actor(actor), "holds_tableware", item)
        self._actor_tableware.setdefault(actor, {}).setdefault(kind, []).append(item)
        self._refresh_carry_state(actor)
        return item

    def _item_owner_edge(self, actor, item):
        node = self._actor(actor)
        for edge in ("holds_in_hand", "holds_tableware", "holds"):
            if self.eng.has_edge(node, edge, item):
                return edge
        return None

    def _remove_item_location(self, item):
        for cell in list(self.eng.neighbours(item, "at_cell")):
            self.eng.remove_edge_unchecked(item, "at_cell", cell)

    def _drop_discrete_item(self, actor, item, cell=None):
        """Drop an item from a hand onto `cell`, or the actor's current map cell (Phase 040: a throw lands elsewhere)."""
        node = self._actor(actor)
        kind = self.eng.node(item)["attrs"].get("kind", "")
        for edge in ("holds_in_hand", "holds_tableware", "holds"):
            self.eng.remove_edge_unchecked(node, edge, item)
        if kind in self._actor_tableware.get(actor, {}):
            self._actor_tableware[actor][kind] = [held for held in self._actor_tableware[actor][kind]
                                                  if held != item]
        if self._actor_hands.get(actor) == item:
            self._actor_hands[actor] = None
        self._remove_item_location(item)
        self.eng.add_edge_unchecked(self._town, "has_tool_item", item)
        cell = self.actor_position(actor) if cell is None else tuple(cell)
        if cell in self._map_cells:
            self._attach_at_cell(item, cell)
        self._refresh_carry_state(actor)
        return item

    def _accept_discrete_item(self, actor, item, *, giver=None):
        """Put an item in the accepting person's hand, then apply load limits."""
        self._actor(actor)
        if self.eng.node(item).get("type") != "ToolItem":
            return self._refuse("wrong_target")
        if giver is not None:
            self._actor(giver)
            edge = self._item_owner_edge(giver, item)
            if edge is None:
                return self._refuse("not_held")
            self.eng.remove_edge_unchecked(self._actor(giver), edge, item)
            if self._actor_hands.get(giver) == item:
                self._actor_hands[giver] = None
            kind = self.eng.node(item)["attrs"].get("kind", "")
            if kind in self._actor_tableware.get(giver, {}):
                self._actor_tableware[giver][kind] = [held for held in self._actor_tableware[giver][kind]
                                                      if held != item]
            self._refresh_carry_state(giver)
        elif self._item_owner_edge(actor, item) is not None:
            return self._refuse("already_held")
        self._remove_item_location(item)
        self.eng.remove_edge_unchecked(self._town, "has_tool_item", item)
        self.eng.add_edge_unchecked(self._actor(actor), "holds_in_hand", item)
        self._actor_hands[actor] = item
        kind = self.eng.node(item)["attrs"].get("kind", "")
        spec = self._item_specs.get(kind, {})
        if spec.get("container") or spec.get("utensil"):
            self._actor_tableware.setdefault(actor, {}).setdefault(kind, []).append(item)
        state = self._refresh_carry_state(actor)
        self.eng.set_attr(self._actor(actor), "last_accepted_item", int(item.value))
        if state["will_drop"]:
            self._drop_discrete_item(actor, item)
            self.eng.set_attr(self._actor(actor), "last_carry_outcome", "dropped")
            self.eng.set_attr(self._actor(actor), "last_dropped_kind",
                              str(self.eng.node(item)["attrs"].get("kind", "item")))
        else:
            self.eng.set_attr(self._actor(actor), "last_carry_outcome", "held")
        return True

    def accept_item(self, actor, item, *, giver=None):
        """Free handoff acceptance; extreme overload makes the item fall."""
        accepted = self._accept_discrete_item(actor, item, giver=giver)
        if accepted and giver is not None:
            kind = self.eng.node(item)["attrs"].get("kind", "")
            self._record_handover("accept", kind, 1.0, self._actor_endpoint(giver), self._actor_endpoint(actor))
        return accepted

    accept = accept_item

    def pick_up(self, actor, item):
        """Try to pick up a ground item; overload may immediately drop it."""
        self._actor(actor)
        if self._item_owner_edge(actor, item) is not None:
            return self._refuse("already_held")
        if not self.eng.has_edge(self._town, "has_tool_item", item):
            cells = list(self.eng.neighbours(item, "at_cell"))
            actor_cells = list(self.eng.neighbours(self._actor(actor), "at_cell"))
            if not cells or not actor_cells or cells[0] != actor_cells[0]:
                return self._refuse("not_in_reach")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "pick_up"):
            return self._refuse("slot_used")
        return self._accept_discrete_item(actor, item)

    def drop_item(self, actor, item):
        """Drop an item voluntarily as a handling action."""
        if self._item_owner_edge(actor, item) is None:
            return self._refuse("not_held")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "drop"):
            return self._refuse("slot_used")
        self._drop_discrete_item(actor, item)
        self.eng.set_attr(self._actor(actor), "last_carry_outcome", "dropped")
        return True

    def _has_tableware(self, actor, kind):
        return bool(self._actor_tableware.get(actor, {}).get(kind))

    def eat(self, actor, kind=None, *, vessel=None, utensil=None, source=None, spiced=False):
        """Eat one held food unit as an explicit major action.

        Soups require a bowl-sized serving vessel and a ladle/serving spoon (a
        bowl may itself scoop from a larger bowl). Drinks require a mug and a
        dipper or mug. ``source`` may name a larger physical container and is
        checked for the corresponding serving capacity. ``spiced`` (Phase 035)
        adds the spice bonus to the meal's pleasure if a spice unit is held, and
        consumes that unit; the backend chooses whether to spice a meal.
        """
        if kind is None:
            candidates = [k for k, spec in self._item_specs.items()
                          if spec.get("food") and self.inventory_qty(actor, k) >= 1.0]
            candidates.sort(key=lambda k: (0 if self._item_specs[k].get("prepared") else 1, k))
            kind = candidates[0] if candidates else None
        if kind is None or not self._item_specs.get(kind, {}).get("food"):
            return self._refuse("not_held")
        if self.inventory_qty(actor, kind) < 1.0:
            return self._refuse("not_held")
        service = self.E.food_service(kind)
        unserved = False
        if service is not None:
            # Phase 049: a meal served without its vessel and utensil, or from a vessel too small for it, is allowed.
            # The unserved share of the meal is wasted (RESOLUTION.unserved_waste).
            if (vessel is None or utensil is None or not self._has_tableware(actor, vessel)
                    or not self._has_tableware(actor, utensil)):
                unserved = True
            source_kind = None
            if source is not None:
                if source not in self._containers:
                    return self._refuse("unknown_target")
                if self.contents(source, kind) < 1.0:
                    return self._refuse("out_of_stock")
                source_kind = self.eng.node(self._containers[source][0])["attrs"].get("kind", "")
            if not unserved and not self.E.can_serve(kind, vessel, utensil, source_kind=source_kind):
                unserved = True
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "eat"):
            return self._refuse("slot_used")
        stock = self._inventory_stock(actor, kind)
        # Graded eating (Phase 027): the meal is the held pile, at its own freshness. Spoiled food is still
        # eaten and relieves little; only an empty stock (refused above) yields nothing.
        freshness = self._pile_condition(stock)
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - 1.0)
        leftover = self.E.scrap_kind(kind)
        if leftover is not None:                         # the bones/rind stay in the eater's hands
            fraction = float(self._item_specs[kind]["leaves_scraps"])
            scraps = self._inventory_stock(actor, leftover, create=True)
            self.eng.set_attr(scraps, "qty", self.inventory_qty(actor, leftover) + fraction)
        self._refresh_carry_state(actor)
        pre_satiety = self._satiety_level(actor, kind)
        value = self.E.meal_value(kind, freshness) * (1.0 - self._energy_satiety(pre_satiety))   # Phase 035
        if unserved:
            value *= 1.0 - float(self.E.RESOLUTION["unserved_waste"])     # Phase 049: the share spilled or wasted
        hunger = float(self.eng.node(self._actor(actor))["attrs"].get("hunger", 0.0))
        self.eng.set_attr(self._actor(actor), "hunger", max(0.0, hunger - value))
        self._record_meal(actor, kind, value, freshness)
        self._nutrition_meal(actor, kind, pre_satiety, spiced)
        self._drink_alcohol(actor, kind)
        self.eng.add_edge_unchecked(self._actor(actor), "ate", stock)
        return True

    def _record_meal(self, actor, kind, value, freshness):
        """Publish what one meal did to the eater: the hunger it relieved, its pleasantness and its illness
        risk. Pleasantness is the freshness (Phase 027); the taste-based meal pleasure is set in _nutrition_meal (Phase 035). Phase 037: the illness risk is rolled
        once per meal (a stateless draw keyed on the seed, the eater, the period and the meal count); a meal that
        makes its eater ill is acute harm (HEALTH.illness_harm, cause `illness`)."""
        node = self._actor(actor)
        self.eng.set_attr(node, "last_meal_value", float(value))
        self.eng.set_attr(node, "last_meal_freshness", float(freshness))
        self.eng.set_attr(node, "meal_pleasantness", float(freshness))
        risk = float(self.E.meal_illness_risk(kind, freshness))
        self.eng.set_attr(node, "illness_risk", risk)
        meals = int(float(self.eng.node(node)["attrs"].get("meal_count", 0.0))) + 1
        self.eng.set_attr(node, "meal_count", float(meals))
        if risk > 0.0 and self._stable_draw(actor, self._town_period(), kind, meals) < risk:
            self.harm(actor, float(self.E.HEALTH["illness_harm"]), "illness")

    def last_meal(self, actor):
        """The most recent meal's read-offs: the hunger it relieved, its freshness, its pleasantness, and the
        illness risk (0 when nobody has eaten yet)."""
        attrs = self.eng.node(self._actor(actor))["attrs"]
        return {"value": round(float(attrs.get("last_meal_value", 0.0)), 4),
                "freshness": round(float(attrs.get("last_meal_freshness", 0.0)), 4),
                "pleasantness": round(float(attrs.get("meal_pleasantness", 0.0)), 4),
                "illness_risk": round(float(attrs.get("illness_risk", 0.0)), 4)}

    # ---------------------------------------------------- nutrition (Phase 035)
    # The body keeps a protein store, a deficiency, the last meal's pleasure and monotony, and its mood. Each food
    # kind has a Satiety node (specific satiety) linked from the Body. A meal's energy is feeds x freshness x (1 -
    # satiety); its protein enters the store; its satisfaction moves the mood. Deficiency, pleasure and monotony are
    # read-offs for the backend's mind rule (seed nu_psych). Choosing a food, and whether to spice a meal, is the
    # backend's choice; the world only applies it.
    def _satiety_level(self, actor, kind):
        """The specific satiety of `kind` for `actor`, 0 (never eaten or faded) to NUTRITION monotony_cap."""
        node = self._satiety_node(actor, kind)
        return 0.0 if node is None else float(self.eng.node(node)["attrs"].get("level", 0.0))

    def _satiety_node(self, actor, kind, *, create=False):
        body = self._bodies[actor]
        for node in self.eng.neighbours(body, "has_satiety"):
            if self.eng.node(node)["attrs"].get("kind") == kind:
                return node
        if not create:
            return None
        node = self.eng.add_node("Satiety", {"kind": kind, "level": 0.0})
        self.eng.add_edge_unchecked(body, "has_satiety", node)
        return node

    def _take_spice(self, actor):
        """Consume one unit of the first spice the actor holds (NUTRITION spice_kinds). True if one was used."""
        for kind in self.E.NUTRITION["spice_kinds"]:
            if self.inventory_qty(actor, kind) >= 1.0:
                stock = self._inventory_stock(actor, kind)
                self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - 1.0)
                self._refresh_carry_state(actor)
                return True
        return False

    def _nutrition_meal(self, actor, kind, pre_satiety, spiced):
        """A meal's body effects, applied after its hunger is relieved. The spice bonus is taken only if the meal is
        spiced and a unit is held. The mood moves toward the meal's satisfaction (seed af_meal_mood). The food's
        satiety rises by monotony_rise, up to monotony_cap."""
        n = self.E.NUTRITION
        bonus = float(n["spice_bonus"]) if (spiced and self._take_spice(actor)) else 0.0
        body = self._bodies[actor]
        attrs = self.eng.node(body)["attrs"]
        satisfaction = self.E.satisfaction_of_meal(kind, pre_satiety, bonus)
        mood = float(attrs.get("mood", 0.5))
        self.eng.set_attr(body, "mood", mood + (satisfaction - mood) * float(n["mood_rate"]))
        self.eng.set_attr(body, "protein_store", float(attrs.get("protein_store", 0.0)) + self.E.protein(kind))
        self.eng.set_attr(body, "meal_pleasure", min(1.0, self.E.taste(kind) + bonus))
        level = min(float(n["monotony_cap"]), pre_satiety + float(n["monotony_rise"]))
        self.eng.set_attr(self._satiety_node(actor, kind, create=True), "level", level)
        self.eng.set_attr(body, "monotony", level)

    def _nutrition_period(self, actor):
        """One period of nutrition (seeds nu_metabolize and nu_deficiency). The protein store is read at the period's
        close: while it is below protein_need, deficiency rises by deficiency_rate times the shortfall share; once it
        is not, deficiency falls by deficiency_recovery. Then the store keeps protein_retain of itself, each food's
        satiety keeps monotony_retain, and the pleasure and monotony read-offs fade."""
        n = self.E.NUTRITION
        body = self._bodies[actor]
        attrs = self.eng.node(body)["attrs"]
        store = float(attrs.get("protein_store", 0.0))
        need = float(n["protein_need"])
        deficiency = float(attrs.get("deficiency", 0.0))
        if store < need:
            deficiency += float(n["deficiency_rate"]) * (need - store) / need
        else:
            deficiency -= float(n["deficiency_recovery"])
        self.eng.set_attr(body, "deficiency", min(1.0, max(0.0, deficiency)))
        self.eng.set_attr(body, "protein_store", store * float(n["protein_retain"]))
        for node in self.eng.neighbours(body, "has_satiety"):
            level = float(self.eng.node(node)["attrs"].get("level", 0.0))
            self.eng.set_attr(node, "level", level * float(n["monotony_retain"]))
        self.eng.set_attr(body, "monotony", float(attrs.get("monotony", 0.0)) * float(n["monotony_retain"]))
        self.eng.set_attr(body, "meal_pleasure", float(attrs.get("meal_pleasure", 0.0)) * float(n["pleasure_retain"]))

    def nutrition(self, actor):
        """Read-offs (Phase 035), plain values: the protein store in grams, the deficiency (0 to 1), the last meal's
        pleasure (0 to 1) and the monotony (the specific satiety of the last food eaten, 0 to 1)."""
        attrs = self.eng.node(self._bodies[actor])["attrs"]
        return {"protein_store": round(float(attrs.get("protein_store", 0.0)), 4),
                "deficiency": round(float(attrs.get("deficiency", 0.0)), 4),
                "meal_pleasure": round(float(attrs.get("meal_pleasure", 0.0)), 4),
                "monotony": round(float(attrs.get("monotony", 0.0)), 4)}

    def meal_value(self, actor, kind):
        """The hunger a held unit of `kind` would relieve if eaten now: feeds x freshness, less the actor's specific
        satiety for that kind (Phase 035)."""
        stock = self._inventory_stock(actor, kind)
        if not stock:
            return 0.0
        return round(self.E.meal_value(kind, self._pile_condition(stock))
                     * (1.0 - self._energy_satiety(self._satiety_level(actor, kind))), 4)

    def _energy_satiety(self, satiety):
        """The satiety that lowers a meal's energy: the food's satiety with the `monotony` switch on, else 0."""
        return float(satiety) if self.physical_subsystems.get("monotony") else 0.0

    def _relieves_hunger(self, kind):
        """True when eating a unit of the store's `kind` now would relieve some hunger (a food with value at the
        pile's freshness). Spoiled food and scraps are not a hunger source a resident should walk to."""
        if not self._item_specs.get(kind, {}).get("food"):
            return False
        return self.E.meal_value(kind, self._pile_condition(self._stock.get(kind))) > 0.0

    def _pile_condition(self, node):
        """Freshness of a pile node (0 to 1). A pile without a condition attribute is fresh."""
        if node is None:
            return 1.0
        return float(self.eng.node(node)["attrs"].get("condition", 1.0))

    def _mix_freshness(self, node, added, added_condition=1.0):
        """Blend `added` units of freshness `added_condition` into pile `node`. A perishable pile's
        freshness is the quantity-weighted mean of what it held and what arrives, so spoiled food moved or
        mixed with fresh food reads between the two rather than resetting to fresh. An empty pile takes the
        arriving freshness outright. Non-perishable piles keep no freshness."""
        attrs = self.eng.node(node)["attrs"]
        added = float(added)
        if float(attrs.get("perishable", 0.0)) != 1.0 or added <= 0.0:
            return
        old_qty = max(0.0, float(attrs.get("qty", 0.0)))
        old_condition = float(attrs.get("condition", 1.0)) if old_qty > 0.0 else 0.0
        total = old_qty + added
        blended = (old_qty * old_condition + added * float(added_condition)) / total
        self.eng.set_attr(node, "condition", min(1.0, max(0.0, blended)))

    def pay_wage(self, employer, worker, amount):
        """Retired: use an explicit coin transfer chosen by the backend."""
        return False

    # ---------------------------------------------------- fiscal purses and obligations (Phase 011)
    # The world records what is owed, moves whole coins when the parties stand together and the coin is
    # there, and records arrears when a payment or collection falls short. It never sets a rate, decides
    # to pay, evicts, forecloses, or takes a house: those choices are the backend's (FISCAL_BACKEND_OWNED).
    # A purse and an obligation are graph nodes of their own type with scalar attributes only.
    def found_purse(self, name, holder):
        """Open the purse `name` (FISCAL_PURSES) and give it to `holder`, a resident whose role is the
        purse's holder_role. Returns the purse node, or None when the name is unknown, already open, or the
        holder does not fit."""
        spec = self.E.FISCAL_PURSES.get(name)
        if spec is None or name in self._actors or self._purse_node(name) is not None:
            return None
        if holder not in self._actors or self.eng.node(self._actors[holder])["attrs"].get("role") != spec["holder_role"]:
            return None
        opening = float(spec.get("opening_coin", 0))
        purse = self.eng.add_node("Purse", {"name": name, "kind": spec.get("kind", ""), "holder": holder,
                                            "coin": opening, "recorded": opening})
        self.eng.add_edge_unchecked(self._town, "has_purse", purse)
        self.eng.add_edge_unchecked(self._actors[holder], "holds_purse", purse)
        return purse

    def _purse_node(self, name):
        for node in self.eng.nodes("Purse"):
            if self.eng.node(node)["attrs"].get("name") == name:
                return node
        return None

    def _fiscal_party(self, ref):
        """(kind, node) for a resident name or an open purse name, else None. A name that is both is refused."""
        is_resident = isinstance(ref, str) and ref in self._actors
        purse = self._purse_node(ref) if isinstance(ref, str) else None
        if is_resident == (purse is not None):
            return None
        return ("resident", self._actors[ref]) if is_resident else ("purse", purse)

    def _party_location(self, party):
        """The cell where a party's coin is handed over: a resident's cell, or a purse holder's cell."""
        kind, node = party
        attrs = self.eng.node(node)["attrs"]
        return self.actor_position(attrs["holder"] if kind == "purse" else attrs["name"])

    def _acts_for(self, actor, party):
        """True when resident `actor` is the party itself, or the holder of the party's purse."""
        if not isinstance(actor, str) or actor not in self._actors:
            return False
        kind, node = party
        attrs = self.eng.node(node)["attrs"]
        return actor == (attrs["holder"] if kind == "purse" else attrs["name"])

    def _move_fiscal_coin(self, source, target, amount):
        """Move `amount` whole coins from one party to another. A purse's recorded ledger moves with its coin."""
        for party, delta in ((source, -amount), (target, amount)):
            kind, node = party
            attrs = self.eng.node(node)["attrs"]
            self.eng.set_attr(node, "coin", float(attrs.get("coin", 0.0)) + delta)
            if kind == "purse":
                self.eng.set_attr(node, "recorded", float(attrs.get("recorded", 0.0)) + delta)

    def _obligation_attrs(self, obligation):
        try:
            record = self.eng.node(obligation)
        except (KeyError, TypeError, ValueError):
            return None
        return record["attrs"] if record["type"] == "Obligation" else None

    def _record_arrears(self, obligation):
        attrs = self._obligation_attrs(obligation)
        self.eng.set_attr(obligation, "arrears", float(attrs["arrears"]) + 1.0)

    def assess_obligation(self, institution, debtor, creditor, *, amount=None, base=None, rate_bp=None,
                          collector=None):
        """Record that `debtor` owes `creditor` one period of `institution` (FISCAL_INSTITUTIONS).

        Give either a whole-coin `amount`, or a whole-coin `base` and a `rate_bp` (0..10000), which the world
        rounds with round_bp. The agent chooses the figures; the world checks only that the parties exist,
        are not the same party, and that the numbers are whole coins. Returns the Obligation node, or None.
        """
        if institution not in self.E.FISCAL_INSTITUTIONS:
            return None
        d, c = self._fiscal_party(debtor), self._fiscal_party(creditor)
        if d is None or c is None or d[1] == c[1] or (d[0] == "purse" and c[0] == "purse"):
            return None
        try:
            from_rate = amount is None
            if from_rate:
                if base is None or rate_bp is None:
                    return None
                amount = round_bp(base, rate_bp)
            else:
                amount = round_bp(amount, 10000)   # whole, not negative: round_bp returns it unchanged
        except ValueError:
            return None
        if collector is not None:
            hired = self._fiscal_party(collector)
            if d[0] != "resident" or hired is None or hired[0] != "resident" or collector == debtor:
                return None
        node = self.eng.add_node("Obligation", {
            "institution": institution, "debtor": debtor, "creditor": creditor,
            "debtor_kind": d[0], "creditor_kind": c[0], "collector": collector or "",
            "base": float(base) if from_rate else 0.0,
            "rate_bp": float(rate_bp) if from_rate else 0.0,
            "amount": float(amount), "paid": 0.0, "periods_paid": 0.0, "arrears": 0.0,
            "held": 0.0, "delivered": 0.0, "skimmed": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_obligation", node)
        return node

    def pay_obligation(self, actor, obligation):
        """Hand one period of `obligation` from its debtor to its creditor, face to face.

        `actor` is the debtor, or the holder of a purse debtor. A receiver elsewhere refuses the payment and
        nothing is recorded. A payer short of coin, with the receiver present, records one period of arrears
        and moves no coin. Otherwise the coin moves, the obligation's paid and periods_paid rise, and a
        Handover is recorded. Returns True only when coin moved.
        """
        attrs = self._obligation_attrs(obligation)
        if attrs is None:
            return self._refuse("unknown_target")
        payer, receiver = self._fiscal_party(attrs["debtor"]), self._fiscal_party(attrs["creditor"])
        if payer is None or receiver is None or payer[1] == receiver[1] or not self._acts_for(actor, payer):
            return self._refuse("wrong_target")
        here = self._party_location(payer)
        if here is None or here != self._party_location(receiver):
            return self._refuse("not_in_reach")
        amount = float(attrs["amount"])
        if self.eng.node(payer[1])["attrs"].get("coin", 0.0) < amount:
            self._record_arrears(obligation)
            return self._refuse("out_of_stock")
        self._move_fiscal_coin(payer, receiver, amount)
        self.eng.set_attr(obligation, "paid", float(attrs["paid"]) + amount)
        self.eng.set_attr(obligation, "periods_paid", float(attrs["periods_paid"]) + 1.0)
        self._record_handover("pay_obligation", "coin", amount, self._party_endpoint(payer, attrs["debtor"]),
                              self._party_endpoint(receiver, attrs["creditor"]))
        return True

    def collect(self, collector, obligation):
        """Collect one period of `obligation` from its debtor, who must stand on the collector's cell.

        The collector is the creditor (or the holder of a purse creditor) or the hired collector named on the
        obligation. Coin goes to the creditor, or to the hired collector as held until deliver. A debtor short
        of coin, reached on the collector's cell, records one period of arrears. A debtor on another cell is
        not reached and nothing is recorded. Returns True only when coin moved.
        """
        attrs = self._obligation_attrs(obligation)
        if attrs is None or collector not in self._actors:
            return self._refuse("unknown_target")
        debtor, creditor = self._fiscal_party(attrs["debtor"]), self._fiscal_party(attrs["creditor"])
        if debtor is None or creditor is None or debtor[0] != "resident" or debtor[1] == creditor[1]:
            return self._refuse("wrong_target")
        hired = attrs["collector"]
        if not (collector == hired or self._acts_for(collector, creditor)):
            return self._refuse("wrong_target")
        here = self.actor_position(collector)
        if here is None or here != self._party_location(debtor):
            return self._refuse("not_in_reach")
        amount = float(attrs["amount"])
        if self.eng.node(debtor[1])["attrs"].get("coin", 0.0) < amount:
            self._record_arrears(obligation)
            return self._refuse("out_of_stock")
        if hired and collector == hired:
            self._move_fiscal_coin(debtor, ("resident", self._actors[collector]), amount)
            self.eng.set_attr(obligation, "held", float(attrs["held"]) + amount)
            target = self._actor_endpoint(collector)
        else:
            self._move_fiscal_coin(debtor, creditor, amount)
            target = self._party_endpoint(creditor, attrs["creditor"])
        self.eng.set_attr(obligation, "paid", float(attrs["paid"]) + amount)
        self.eng.set_attr(obligation, "periods_paid", float(attrs["periods_paid"]) + 1.0)
        self._record_handover("collect", "coin", amount, self._party_endpoint(debtor, attrs["debtor"]), target)
        return True

    def deliver_collected(self, collector, obligation, share_bp=10000):
        """The hired collector hands on `share_bp` basis points of the coin held for the creditor.

        The share is round_bp(held, share_bp) and moves from the collector's coin to the creditor, who must
        stand with the collector. The rest of the held coin stays with the collector and is recorded as
        skimmed. Returns True only when coin was delivered.
        """
        attrs = self._obligation_attrs(obligation)
        if attrs is None or not attrs["collector"] or collector != attrs["collector"] or collector not in self._actors:
            return self._refuse("wrong_target")
        creditor = self._fiscal_party(attrs["creditor"])
        if creditor is None:
            return self._refuse("unknown_target")
        try:
            held = float(attrs["held"])
            if held <= 0.0:
                return self._refuse("out_of_stock")
            delivered = float(round_bp(held, share_bp))
        except ValueError:
            return self._refuse("malformed")
        here = self.actor_position(collector)
        if here is None or here != self._party_location(creditor):
            return self._refuse("not_in_reach")
        if self.eng.node(self._actors[collector])["attrs"].get("coin", 0.0) < delivered:
            return self._refuse("out_of_stock")
        self._move_fiscal_coin(("resident", self._actors[collector]), creditor, delivered)
        self.eng.set_attr(obligation, "held", 0.0)
        self.eng.set_attr(obligation, "delivered", float(attrs["delivered"]) + delivered)
        self.eng.set_attr(obligation, "skimmed", float(attrs["skimmed"]) + held - delivered)
        self._record_handover("deliver_collected", "coin", delivered, self._actor_endpoint(collector),
                              self._party_endpoint(creditor, attrs["creditor"]))
        return True

    # ---------------------------------------------------- physical handovers (Phase 026)
    # Each completed physical handover of coin or goods is one Handover fact: turn, kind (the action that moved
    # it), good, quantity, and both endpoints. The world records what moved and where. It never decides that a
    # handover was a sale, a wage or a gift, and never pairs handovers into trades.
    def _actor_endpoint(self, name):
        return ("actor", str(name))

    def _party_endpoint(self, party, name):
        """The endpoint of a fiscal party: a resident is an actor, a purse is a purse."""
        return ("actor" if party[0] == "resident" else "purse", str(name))

    def _record_handover(self, kind, good, quantity, source, target):
        """Record one completed handover. `source` and `target` are (endpoint kind, name) pairs.

        The newest HANDOVER_LOG_LIMIT Handover facts are kept; the counts in `_handover_totals` are cumulative
        and are what the report reads.
        """
        if kind not in self.E.HANDOVER_KINDS:
            raise ValueError(f"unknown handover kind: {kind}")
        quantity = float(quantity)
        from_kind, from_name = source
        to_kind, to_name = target
        node = self.eng.add_node("Handover", {"turn": float(self._turn), "kind": str(kind), "good": str(good),
                                              "quantity": quantity, "from": str(from_name), "from_kind": from_kind,
                                              "to": str(to_name), "to_kind": to_kind})
        self.eng.add_edge_unchecked(self._town, "has_handover", node)
        totals = self._handover_totals
        totals["count"] += 1
        if kind in ("pay_obligation", "collect", "deliver_collected"):
            totals["fiscal"] += 1
        for bucket, key in ((totals["by_good"], str(good)), (totals["by_kind"], str(kind)),
                            (totals["by_endpoint"], f"{from_kind}->{to_kind}")):
            entry = bucket.setdefault(key, {"count": 0, "quantity": 0.0})
            entry["count"] += 1
            entry["quantity"] += quantity
        self._handovers[f"handover:{totals['count']}"] = node
        while len(self._handovers) > int(self.E.HANDOVER_LOG_LIMIT):
            oldest = next(iter(self._handovers))
            self.eng.remove_node(self._handovers.pop(oldest))
        return node

    @property
    def _transactions(self):
        """Fiscal coin handovers so far, as a count. village_eval.py reads its length; see _HandoverCount."""
        return _HandoverCount(self._handover_totals["fiscal"])

    # ---------------------------------------------------- civic process and justice
    def propose_local_law(self, author, name, *, title=None, scope="bigville", concepts=()):
        # A proposal records what a resident said; it does not edit the
        # inherited registry or resolve the proposal's legal meaning.
        proposal = self.eng.add_node("LawProposal", {"name": name, "title": title or name.replace("_", " ").title(),
                                                        "scope": scope, "status": "open", "votes_for": 0.0,
                                                        "votes_against": 0.0, "author": author,
                                                        **self._civic_record("lawmaking", "proposal")})
        self.eng.add_edge_unchecked(self._town, "has_proposal", proposal)
        self.eng.add_edge_unchecked(self._actors[author], "proposed", proposal)
        for concept in concepts:
            self.eng.add_edge_unchecked(proposal, "has_concept", self.eng.add_node("Concept", dict(concept)))
        self._proposals[f"proposal:{len(self._proposals) + 1}"] = proposal
        return proposal

    def vote_on_law(self, voter, proposal, support):
        # A vote is an actor's recorded expression. The world does not decide
        # who is entitled to vote or whether a proposal remains votable.
        edge = "voted_for" if support else "voted_against"
        self.eng.add_edge_unchecked(self._actors[voter], edge, proposal)
        record = self.eng.add_node("CouncilVote", {"voter": voter, "support": 1.0 if support else 0.0,
                                                     "proposal": str(self.eng.node(proposal)["attrs"].get("name", "")),
                                                     "day": float(self.calendar()["day"]),
                                                     **self._civic_record("lawmaking", "vote")})
        self.eng.add_edge_unchecked(self._town, "has_vote", record)
        self.eng.add_edge_unchecked(self._actors[voter], "cast_vote", record)
        self.eng.add_edge_unchecked(record, "on_proposal", proposal)
        return True

    def hold_council(self, chair=None, proposal=None):
        # Persist the convening and any observed tally as records only. Quorum,
        # enactment, and promulgation are interpretations for residents.
        meeting = self.eng.add_node("CouncilMeeting", {"day": float(self.calendar()["day"]),
                                                         "chair": chair or "",
                                                         **self._civic_record("lawmaking", "meeting")})
        self.eng.add_edge_unchecked(self._town, "has_meeting", meeting)
        self._meetings[f"meeting:{len(self._meetings) + 1}"] = meeting
        if proposal is not None:
            votes_for = len(self.eng.in_neighbours(proposal, "voted_for"))
            votes_against = len(self.eng.in_neighbours(proposal, "voted_against"))
            self.eng.set_attr(meeting, "proposal", str(self.eng.node(proposal)["attrs"].get("name", "")))
            self.eng.set_attr(meeting, "votes_for_observed", float(votes_for))
            self.eng.set_attr(meeting, "votes_against_observed", float(votes_against))
        return meeting

    def file_case(self, complainant, respondent, *, charge, law="", evidence=""):
        case = self.eng.add_node("Case", {"charge": charge, "law": law, "evidence": evidence,
                                           "complainant": complainant, "respondent": respondent,
                                           "status": "open", "verdict": "", "remedy": "",
                                           **self._civic_record("justice", "case")})
        self.eng.add_edge_unchecked(self._town, "has_case", case)
        self.eng.add_edge_unchecked(self._actors[complainant], "filed_case", case)
        self.eng.add_edge_unchecked(self._actors[respondent], "answerable_case", case)
        self._cases[f"case:{len(self._cases) + 1}"] = case
        return case

    def resolve_case(self, adjudicator, case, *, verdict, remedy=""):
        """Record a resident's case interpretation without making it binding.

        The legacy method name does not grant institutional authority: any
        resident may state a verdict or proposed remedy, and the case remains
        open until residents themselves choose what to believe or do.
        """
        speaker = self._actors[adjudicator]
        statement_id = f"case-statement:{len(self.eng.neighbours(case, 'has_statement')) + 1}"
        statement = self.eng.add_node("CaseStatement", {
            "record_id": statement_id,
            "speaker": adjudicator,
            "reported_verdict": str(verdict),
            "suggested_remedy": str(remedy),
            "day": float(self.calendar()["day"]),
            **self._civic_record("justice", "statement"),
        })
        self.eng.add_edge_unchecked(case, "has_statement", statement)
        self.eng.add_edge_unchecked(self._town, "has_case_statement", statement)
        self.eng.add_edge_unchecked(speaker, "made_case_statement", statement)
        return statement

    def map_position_node(self, node):
        attrs = self.eng.node(node)["attrs"]
        if "x" in attrs and "y" in attrs:
            return int(attrs["x"]), int(attrs["y"])
        cells = list(self.eng.neighbours(node, "at_cell"))
        if not cells:
            return None
        attrs = self.eng.node(cells[0])["attrs"]
        return int(attrs["x"]), int(attrs["y"])

    # ---------------------------------------------------- policies, laws, and written documents
    def policy_data(self, name): return dict(self._policy_specs[name])
    def law_data(self, name): return dict(self._law_specs[name])
    def charter_data(self, name): return dict(self._charter_specs[name])
    def document_names(self): return {name for _, name in self._documents}

    def policy_names(self): return set(self._policy_specs)
    def law_names(self): return set(self._law_specs)
    def charter_names(self): return set(self._charter_specs)
    def inherited_policy_names(self):
        return {n for n, p in self._policy_specs.items() if p.get("origin") == "giantville"}
    def local_policy_names(self):
        return {n for n, p in self._policy_specs.items() if p.get("origin") == "bigville"}
    def inherited_law_names(self):
        return {n for n, law in self._law_specs.items() if law.get("origin") == "giantville"}
    def local_law_names(self):
        return {n for n, law in self._law_specs.items() if law.get("origin") == "bigville"}
    def law_origin(self, name): return self._law_specs[name].get("origin", "bigville")
    def law_immutable(self, name): return bool(self._law_specs[name].get("immutable", False))
    def law_enforcement(self, name): return self._law_specs[name].get("enforcement", "bigville")

    def lawmaking_procedures(self):
        return {k: dict(v) for k, v in self._procedures["lawmaking"].items()}

    def justice_procedures(self):
        return {k: dict(v) for k, v in self._procedures["justice"].items()}

    def _procedure_tables(self):
        """The lawmaking and justice stages in effect. A scenario's "procedures" entry overrides them
        by stage: a stage given in full replaces or adds that stage, and null removes it. Stages are
        data for recording; the world does not check that a stage was carried out validly."""
        overrides = self._scenario_data.get("procedures") or {}
        unknown = set(overrides) - {"lawmaking", "justice"}
        if unknown:
            raise ValueError(f"unknown procedure table(s) in scenario: {sorted(unknown)}")
        tables = {}
        for key, base in (("lawmaking", self.E.LAWMAKING_PROCEDURES), ("justice", self.E.JUSTICE_PROCEDURES)):
            table = {stage: dict(spec) for stage, spec in base.items()}
            for stage, spec in dict(overrides.get(key) or {}).items():
                if spec is None:
                    table.pop(stage, None)
                else:
                    table[stage] = dict(spec)
            tables[key] = table
        return tables

    def _civic_record(self, table, action):
        """The civic-record fields for one action: the action's name and the stage of `table` that
        lists it in civic_actions (empty when no stage does)."""
        stage = next((name for name, spec in self._procedures[table].items()
                      if action in spec.get("civic_actions", ())), "")
        return {"civic_action": action, "stage": stage}

    def _policy_parameters(self, name):
        """The named numbers a policy carries in the data pack (its `parameters`)."""
        # A scenario may select a policy list without this policy; its numbers still come from the pack.
        spec = self._policy_specs.get(name)
        if spec is None or "parameters" not in spec:
            spec = next((p for p in self.E.POLICIES if p.get("name") == name), None)
        if spec is None or "parameters" not in spec:
            raise KeyError(f"policy '{name}' has no parameters in the data pack")
        return spec["parameters"]

    def policy_concepts(self, name):
        return [dict(c) for c in self._policy_specs[name]["concepts"]]

    def law_concepts(self, name):
        return [dict(c) for c in self._law_specs[name]["concepts"]]

    def charter_concepts(self, name):
        return [dict(c) for c in self._charter_specs[name]["concepts"]]

    def _bundle(self, name, kind):
        table = {"policy": self._policy_specs, "law": self._law_specs,
                 "charter": self._charter_specs}[kind]
        return table[name]

    def _seed_bundle(self, actor, bundle):
        understood = self.eng.add_node("PolicyUnderstanding", {"name": bundle["name"], "kind": bundle["kind"]})
        self.eng.add_edge_unchecked(actor, "understands", understood)
        self._actor_policies.setdefault(actor, set()).add(bundle["name"])

    def _can_meet_document_literacy(self, actor, kind):
        """True when the resident meets the literacy the pack's DOCUMENT_LITERACY sets for this kind.
        A kind with no entry has no literacy gate."""
        tier = self.E.DOCUMENT_LITERACY.get(kind)
        if tier is None:
            return True
        if tier == "functional":
            return self.can_read(actor)
        return self.can_read_law(actor)

    def write_document(self, author, name, *, kind="policy"):
        """Create a physical written policy/law record; the document is not knowledge until read."""
        assert name in {"policy": self._policy_specs, "law": self._law_specs,
                        "charter": self._charter_specs}[kind]
        if not self._can_meet_document_literacy(author, kind):
            return None
        bundle = self._bundle(name, kind)
        doc = self.eng.add_node("WrittenDocument", {"name": name, "kind": kind,
                                                     "title": bundle["title"], "scope": bundle["scope"],
                                                     "version": 1.0,
                                                     "origin": bundle.get("origin", "bigville"),
                                                     "immutable": 1.0 if bundle.get("immutable", False) else 0.0,
                                                     "enforcement": bundle.get("enforcement", "bigville")})
        self.eng.add_edge_unchecked(self._town, "has_document", doc)
        self.eng.add_edge_unchecked(self._actors[author], "wrote_document", doc)
        self._documents[(kind, name)] = doc
        return doc

    def read_document(self, reader, document):
        attrs = self.eng.node(document)["attrs"]
        if not self._can_meet_document_literacy(reader, attrs.get("kind")):
            return None
        self.eng.add_edge_unchecked(self._actors[reader], "read_document", document)
        return attrs["name"]

    def _knows_bundle(self, actor, name):
        known = self.known_references(actor)
        required = {c["name"] for c in self.E.all_reference_templates() if c.get("source_name") == name}
        return bool(required) and required <= known

    def knows_policy(self, actor, name):
        return name in self._actor_policies.get(self._actors[actor], set()) or self._knows_bundle(actor, name)

    def knows_law(self, actor, name):
        return name in self._actor_policies.get(self._actors[actor], set()) or self._knows_bundle(actor, name)

    def knows_charter(self, actor, name):
        return name in self._actor_policies.get(self._actors[actor], set()) or self._knows_bundle(actor, name)

    # ---------------------------------------------------- physical stock (piles), NOT floats
    def _phys(self, kind):
        """The physical properties of a commodity, from the item data (defaults 1/1, not a fluid)."""
        spec = self._item_specs.get(kind, {})
        return (float(spec.get("weight", 1.0)), float(spec.get("volume", 1.0)),
                1.0 if spec.get("fluid") else 0.0)

    def set_stock(self, kind, qty, *, condition=None):
        """Set a store pile's quantity. A pile that gains units takes their freshness mixed in: new production
        arrives fresh (condition 1.0) unless the caller passes the arriving food's `condition`, as a transfer
        does. A new pile starts at that condition (fresh by default)."""
        w, v, fl = self._phys(kind)
        food = 1.0 if self._item_specs.get(kind, {}).get("food") else 0.0
        perishable = 1.0 if self.E.adjectival(kind) == "perishable" else 0.0
        arriving = 1.0 if condition is None else float(condition)
        if kind in self._stock:
            added = float(qty) - self.qty(kind)
            if added > 0.0:
                self._mix_freshness(self._stock[kind], added, arriving)
            self.eng.set_attr(self._stock[kind], "qty", float(qty))
        else:
            colour = self._item_specs.get(kind, {}).get("colour", "")   # a dye names a colour (madder->red)
            s = self.eng.add_node("Stock", {"kind": kind, "qty": float(qty),   # a first-class physical pile
                                            "weight": w, "volume": v, "fluid": fl, "food": food, "colour": colour,
                                            # spoilage: a perishable pile has a freshness that decays over time
                                            "perishable": perishable, "condition": arriving,
                                            "decay": self.E.decay_rate(kind), "decay_epoch": 0.0})
            self.eng.add_edge_unchecked(self._store, "stock", s)
            self._stock[kind] = s
        return self._stock[kind]

    # ---------------------------------------------------- condition adjectives (wear + decay stages)
    def tool_adjective(self, tool):
        """The adjective describing a discrete tool at its current condition (pristine/worn/rusty/...)."""
        a = self.eng.node(tool)["attrs"]
        return self.E.adjective(a["kind"], a["condition"])

    def stock_adjective(self, kind):
        """The adjective describing a perishable stock (fresh/stale/rotten/putrid)."""
        return self.E.adjective(kind, self.eng.node(self._stock[kind])["attrs"].get("condition", 1.0))

    def stock_condition(self, kind):
        return round(float(self.eng.node(self._stock[kind])["attrs"].get("condition", 1.0)), 4)
    def stored_condition(self, container, kind):
        return round(float(self.eng.node(self._containers[container][1][kind])["attrs"].get("condition", 1.0)), 4)
    def stored_adjective(self, container, kind):
        return self.E.adjective(kind, self.eng.node(self._containers[container][1][kind])["attrs"].get("condition", 1.0))
    def item_wear_rate(self, kind): return float(self._item_specs.get(kind, {}).get("wear_rate", 0.0))
    def item_decay_rate(self, kind): return self.E.decay_rate(kind)
    def adjectival_class(self, kind): return self.E.adjectival(kind)

    # ------------------------------- BACKEND value read-offs (for the operator; NOT an agent input)
    # scarcity is a raw-material fact a seller knows; reference_value is an analyst baseline the human
    # holds the market's discovered price against -- the agents price for themselves, the market clears.
    def scarcity(self, kind): return self.E.scarcity(kind)
    def reference_value(self, kind): return self.E.reference_value(kind)
    def material_value(self, kind): return self.E.material_value(kind)
    def embodied_labour(self, kind): return self.E.embodied_labour(kind)

    # ---------------------------------------------------- buildings (from the BUILDINGS data)
    def _install_building(self, kind, spec, *, key=None, cell=None):
        place_key = key or kind
        p = self.eng.add_node("Place", {"kind": kind, "name": place_key.capitalize(),
                                        "sheltered": 1.0 if spec.get("sheltered") else 0.0})
        self.eng.add_edge_unchecked(self._town, "has_place", p)
        staff = self.eng.add_node("Agent", {"name": f"{kind}_staff", "role": spec.get("staff_role", "")})
        self.eng.add_edge_unchecked(p, "staffed_by", staff)
        if spec.get("provides"):                          # town -has_<provides>-> the staff (a maker role)
            self.eng.add_edge_unchecked(self._town, f"has_{spec['provides']}", staff)
        for room in spec.get("rooms", []):
            r = self.eng.add_node("Room", {"kind": room})
            self.eng.add_edge_unchecked(p, "has_room", r)
        self._places[place_key] = p
        requested = cell if cell is not None else self._anchor_for_building(kind)
        site = self._allocate_building_site(place_key, spec, requested)
        self._building_sites[place_key] = site
        self._attach_at_cell(p, site[:2])
        return p

    def building(self, kind): return self._places.get(kind)
    def building_provides(self, kind):
        staff = list(self.eng.neighbours(self._places[kind], "staffed_by"))
        return self.eng.node(staff[0])["attrs"]["role"] if staff else None
    def building_sheltered(self, kind):
        return float(self.eng.node(self._places[kind])["attrs"]["sheltered"]) == 1.0
    def buildings(self): return set(self._places)

    def propose_building(self, project, *, site=None, sponsor=None, name=None):
        """Create a data-driven building project at a map site."""
        spec = self.E.BUILDING_PROJECTS[project]
        if site is None:
            site = self._anchor_for_building(spec.get("building", project))
        site = tuple(site)
        assert site in self._map_cells, f"building site {site} not walkable"
        project_id = name or f"{project}_project_{len(self._building_projects) + 1}"
        n = self.eng.add_node("BuildingProject", {
            "name": project_id, "project": project, "building": spec.get("building", project),
            "status": "proposed", "progress": 0.0, "labour": float(spec.get("labour", 1.0)),
            "inputs": ";".join(f"{k}:{v}" for k, v in spec.get("inputs", {}).items())})
        self.eng.add_edge_unchecked(self._town, "has_building_project", n)
        self._attach_at_cell(n, site)
        if sponsor in self._actors:
            self.eng.add_edge_unchecked(self._actors[sponsor], "sponsored_project", n)
        self._building_projects[project_id] = n
        return n

    def building_project_data(self, project):
        key = project if project in self._building_projects else project
        return dict(self.eng.node(self._building_projects[key])["attrs"])

    def advance_building(self, project, builder, *, labour=1.0):
        """Spend materials and labour on a project; completion mints a Place node.

        A successful work step returns ``True`` while the project remains in
        progress, and the created Place when the step completes the project.
        ``None`` means that no work was accepted.
        """
        assert project in self._building_projects and builder in self._actors
        project_cells = list(self.eng.neighbours(self._building_projects[project], "at_cell"))
        project_cell = self.map_position_node(project_cells[0]) if project_cells else None
        if (self._turn > 0 and project_cell is not None
                and self.actor_position(builder) != project_cell):
            self._refuse("not_in_reach")
            return None
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(builder, "build"):
            self._refuse("slot_used")
            return None
        n = self._building_projects[project]
        attrs = self.eng.node(n)["attrs"]
        if attrs["status"] == "complete":
            return self._places.get(attrs["name"])
        spec = self.E.BUILDING_PROJECTS[attrs["project"]]
        starting_progress = float(attrs["progress"])
        total_labour = float(attrs["labour"])
        labour = min(float(labour), total_labour - starting_progress)
        if labour <= 0:
            self._refuse("malformed")
            return None
        scale = labour / float(attrs["labour"])
        required = {k: float(v) * scale for k, v in spec.get("inputs", {}).items()}
        if required and not self._store_open(builder):
            self._refuse("store_locked")
            return None
        if any(self.qty(k) + 1e-9 < q for k, q in required.items()):
            self._refuse("out_of_stock")
            return None
        for kind, qty in required.items():
            # Repeated fractional costs can leave a tiny negative remainder
            # (or make the final exact cost appear unavailable) through
            # floating point roundoff.
            self.set_stock(kind, max(0.0, self.qty(kind) - qty))
        new_progress = starting_progress + labour
        self.eng.set_attr(n, "progress", new_progress)
        self.eng.add_edge_unchecked(self._actors[builder], "worked_on", n)
        if new_progress + 1e-9 < total_labour:
            self.eng.set_attr(n, "status", "under_construction")
            return True
        self.eng.set_attr(n, "status", "complete")
        building_kind = attrs["building"]
        base = dict(self.E.BUILDINGS.get(building_kind, {
            "staff_role": spec.get("staff_role", ""), "sheltered": spec.get("sheltered", False),
            "rooms": spec.get("rooms", [])}))
        site_nodes = list(self.eng.neighbours(n, "at_cell"))
        site = None
        if site_nodes:
            ca = self.eng.node(site_nodes[0])["attrs"]
            site = (int(ca["x"]), int(ca["y"]))
        place = self._install_building(building_kind, base, key=attrs["name"], cell=site)
        self.eng.add_edge_unchecked(n, "built_place", place)
        return place

    # ---------------------------------------------------- containers (volume capacity, many kinds, fluids)
    def _vessel_data(self, kind):
        """Capacity, watertightness, and decay_factor of a vessel kind, from the data (or CONTAINERS)."""
        spec = self._item_specs.get(kind, {}) or self.E.CONTAINERS.get(kind, {})
        return (float(spec.get("capacity", 10.0)), 1.0 if spec.get("watertight") else 0.0,
                float(spec.get("decay_factor", 1.0)))

    def _wire_container(self, name, node, kind, holds, lock_id, locked, max_load=None, capacity=None,
                        keys_required=1):
        assert name != "store", "'store' names the town store's lock (Phase 030)"
        cap, wt, df = self._vessel_data(kind)
        if capacity is not None:
            cap = float(capacity)
        ml = max_load if max_load is not None else float(self._item_specs.get(kind, {}).get("max_load", 1e9))
        for k, v in (("capacity", cap), ("watertight", wt), ("decay_factor", df), ("max_load", ml),
                     ("lock_id", float(lock_id)), ("locked", 1.0 if locked else 0.0),
                     ("keys_required", float(keys_required))):
            self.eng.set_attr(node, k, v)
        storage_class = (self._item_specs.get(kind, {}) or self.E.CONTAINERS.get(kind, {})).get("storage_class")
        if storage_class:
            self.eng.set_attr(node, "storage_class", storage_class)
        # Phase 050: the container's structure (1 whole, 0 broken), its lock's strength (CONTAINERS, lockable
        # kinds), and the lock's own wear and progress toward opening (see _run_attempt).
        self.eng.set_attr(node, "structure", 1.0)
        self.eng.set_attr(node, "destroyed", 0.0)
        self.eng.set_attr(node, "lock_strength", float(self.E.CONTAINERS.get(kind, {}).get("lock_strength", 1.0)))
        self.eng.set_attr(node, "lock_condition", 1.0)
        self.eng.set_attr(node, "lock_progress", 0.0)
        self.eng.add_edge_unchecked(self._town, "has_container", node)
        inners = {}
        for hk in ([holds] if isinstance(holds, str) else holds):
            inners[hk] = self._new_inner_stock(node, kind, hk)
        self._containers[name] = (node, inners)
        return node

    def _new_inner_stock(self, container_node, container_kind, kind):
        """Create a content pile without restricting what the container may hold."""
        w, vol, fl = self._phys(kind)
        per = 1.0 if self.E.adjectival(kind) == "perishable" else 0.0
        # A pile created during a later period is fresh now.  Starting its
        # decay clock at zero would make the periodic decay rule age it once
        # for every elapsed period immediately, often spoiling a just-bought
        # resident inventory before the resident can consume it.
        current_period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        base_factor = float((self._item_specs.get(container_kind, {}) or self.E.CONTAINERS.get(container_kind, {})).get("decay_factor", 1.0))
        inner = self.eng.add_node("Stock", {"kind": kind, "qty": 0.0, "weight": w, "volume": vol, "fluid": fl,
                                            "perishable": per, "condition": 1.0, "decay": self.E.decay_rate(kind),
                                            "storage_factor": base_factor * self.E.storage_decay_factor(container_kind, kind),
                                            "decay_epoch": current_period})
        self.eng.add_edge_unchecked(container_node, "contains", inner)
        return inner

    def add_container(self, name, *, kind="barrel", holds, lock_id=0.0, locked=False, cell=None, keys_required=1):
        c = self.eng.add_node("Container", {"kind": kind, "name": name})
        c = self._wire_container(name, c, kind, holds, lock_id, locked, keys_required=keys_required)
        if cell is not None:
            self._attach_at_cell(c, tuple(cell))
        return c

    def container_position(self, name):
        return self.map_position_node(self._containers[name][0])

    def container_storage_class(self, name):
        """Return the declared storage class, such as dry_grain or root_crop."""
        return self.eng.node(self._containers[name][0])["attrs"].get("storage_class")

    def add_carrier(self, name, *, holds, max_load, capacity=1e9):
        """A weight-bounded CARRIER -- a person's carry-bag (small max_load) or a cart (large). WEIGHT
        drives what fits: a person carries little, a horse-drawn cart carries a lot."""
        c = self.eng.add_node("Carrier", {"kind": "carrier", "name": name})
        return self._wire_container(name, c, "carrier", holds, 0.0, False,
                                    max_load=float(max_load), capacity=float(capacity))

    def max_load(self, carrier): return round(float(self.eng.node(self._containers[carrier][0])["attrs"]["max_load"]), 4)

    # ---------------------------------------------------- fences, enclosures, and animal NPCs
    def add_fence(self, name, *, cell=None, kind="wooden_fence", enclosure=None,
                  gate=False):
        spec = self.E.FENCE_TYPES[kind]
        node = self.eng.add_node("Fence", {
            "name": str(name), "kind": str(kind), "material": spec.get("material", ""),
            "durability": float(spec.get("durability", 1.0)), "condition": 1.0,
            "animal_barrier": 0.0 if gate or not spec.get("animal_barrier", True) else 1.0,
            "gate": 1.0 if gate else 0.0,
        })
        self.eng.add_edge_unchecked(self._town, "has_fence", node)
        self._fences[str(name)] = node
        if cell is not None:
            self._attach_at_cell(node, tuple(cell))
        if enclosure is not None:
            if enclosure not in self._enclosures:
                raise KeyError(f"unknown enclosure: {enclosure}")
            self.eng.add_edge_unchecked(node, "bounds", self._enclosures[enclosure])
        return node

    def add_enclosure(self, name, cells, *, kind="paddock", fence_kind=None, gates=()):
        spec = self.E.ENCLOSURE_TYPES[kind]
        selected = {tuple(cell) for cell in cells if tuple(cell) in self._map_cells}
        if not selected:
            raise ValueError("an enclosure needs at least one walkable cell")
        node = self.eng.add_node("Enclosure", {
            "name": str(name), "kind": str(kind), "purpose": spec.get("purpose", ""),
            "fence_kind": fence_kind or spec.get("fence", "wooden_fence"),
            "area": float(len(selected)),
        })
        self.eng.add_edge_unchecked(self._town, "has_enclosure", node)
        self._enclosures[str(name)] = node
        self._enclosure_cells[str(name)] = selected
        gate_cells = {tuple(cell) for cell in gates}
        for cell in sorted(selected):
            self.eng.add_edge_unchecked(node, "contains_cell", self._map_cells[cell])
        for x, y in sorted(selected):
            boundary = any((x + dx, y + dy) not in selected
                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if boundary:
                fence_name = f"{name}:fence:{x}:{y}"
                self.add_fence(fence_name, cell=(x, y),
                               kind="gate" if (x, y) in gate_cells else (fence_kind or spec.get("fence", "wooden_fence")),
                               enclosure=name, gate=(x, y) in gate_cells)
        return node

    def enclosures(self):
        return set(self._enclosures)

    def enclosure_cells(self, name):
        return set(self._enclosure_cells[name])

    def animal_position(self, name):
        return self.map_position_node(self._animals[name])

    def animal_enclosure(self, name):
        enclosures = list(self.eng.neighbours(self._animals[name], "kept_in"))
        for enclosure_name, node in self._enclosures.items():
            if node in enclosures:
                return enclosure_name
        return None

    def fence_intact(self, name):
        attrs = self.eng.node(self._fences[name])["attrs"]
        return float(attrs.get("condition", 1.0)) > 0.0 or bool(attrs.get("gate", 0.0))

    def enclosure_intact(self, name):
        return all(self.fence_intact(fence_name)
                   for fence_name, fence_node in self._fences.items()
                   if self.eng.has_edge(fence_node, "bounds", self._enclosures[name]))

    def break_fence(self, name):
        self.eng.set_attr(self._fences[name], "condition", 0.0)
        return True

    def repair_fence(self, name):
        self.eng.set_attr(self._fences[name], "condition", 1.0)
        return True

    def _animal_allowed_cell(self, name, cell):
        enclosure = self.animal_enclosure(name)
        if enclosure is None or not self.enclosure_intact(enclosure):
            return True
        allowed = self._enclosure_cells.get(enclosure, set())
        cell = tuple(cell)
        if cell in allowed:
            return True
        current = self.animal_position(name)
        if current is not None and current not in allowed and cell != current and allowed:
            cur_dist = min((self.distance(current, p) for p in allowed
                            if self.distance(current, p) is not None), default=None)
            nxt_dist = min((self.distance(cell, p) for p in allowed
                            if self.distance(cell, p) is not None), default=None)
            if cur_dist is not None and nxt_dist is not None and nxt_dist < cur_dist:
                return True
        return False

    def _move_animal_to(self, name, cell):
        cell = tuple(cell)
        if cell not in self._map_cells or not self._animal_allowed_cell(name, cell):
            return self.animal_position(name)
        node = self._animals[name]
        old = self.animal_position(name)
        if old in self._map_cells:
            self.eng.remove_edge_unchecked(node, "at_cell", self._map_cells[old])
        self._attach_at_cell(node, cell)
        self.eng.set_attr(node, "last_npc_action", "move")
        return cell

    def _animal_step_toward(self, name, destination):
        current = self.animal_position(name)
        if current is None or destination not in self._map_cells:
            return current
        candidates = [(current[0] + 1, current[1]), (current[0] - 1, current[1]),
                      (current[0], current[1] + 1), (current[0], current[1] - 1)]
        viable = [cell for cell in candidates
                  if cell in self._map_cells and self._animal_allowed_cell(name, cell)]
        if not viable:
            return current
        return self._move_animal_to(name, min(
            viable, key=lambda cell: self.distance(cell, destination)
            if self.distance(cell, destination) is not None else 10**9))

    def _animal_move_to_neighbor(self, name, destination):
        """Apply one adjacent animal step, enforcing the published movement boundary."""
        current = self.animal_position(name)
        destination = tuple(destination)
        if (current is None or abs(current[0] - destination[0]) + abs(current[1] - destination[1]) != 1
                or destination not in self._map_cells or not self._animal_allowed_cell(name, destination)):
            return current
        return self._move_animal_to(name, destination)

    def add_animal(self, name, species, *, cell=None, household=None, land=None, enclosure=None,
                   sex=None, age_days=None):
        """Add a living animal. `sex` defaults to the species' founding_sex; `age_days` defaults to the
        species' maturity (a founding animal is adult). Both are life-cycle facts (Phase 008)."""
        spec = self.E.ANIMALS[species]
        sex = str(spec["founding_sex"] if sex is None else sex)
        if sex not in ("male", "female"):
            raise ValueError(f"an animal's sex is 'male' or 'female', not {sex!r}")
        age = float(spec["matures"]) * self._animal_month_days() if age_days is None else float(age_days)
        a = self.eng.add_node("Animal", {"name": name, "species": species, "role": spec.get("role", ""),
                                         "pull": float(spec.get("pull", 0.0)), "alive": 1.0,
                                         "matures": float(spec.get("matures", 0)), "lifespan": float(spec.get("lifespan", 0)),
                                         # feeding state (data-driven): what it eats, how much, and its starve limit
                                         "hunger": 0.0, "hunger_epoch": 0.0, "eats": spec.get("eats", ""),
                                         "ration": float(spec.get("ration", 1)), "starve_limit": float(spec.get("starve_limit", 3)),
                                         "last_npc_action": "", "npc_model": "psi_can_weighted",
                                         # life cycle: age in days (one period), breeding state, and the record of birth and death
                                         "sex": sex, "age_days": age, "gestating_days": 0.0, "sire": "", "dam": "",
                                         "births": 0.0, "conceived_age": -1.0e9, "born_period": self._town_period(),
                                         "death_cause": "", "death_period": -1.0})
        self.eng.add_edge_unchecked(self._town, "has_animal", a)
        self._animals = getattr(self, "_animals", {}); self._animals[name] = a
        if cell is None and household in self._household_cells:
            cell = self.map_position(household)
        if cell is not None:
            self._attach_at_cell(a, tuple(cell))
        if household is not None:
            self.eng.add_edge_unchecked(self._households[household], "keeps_animal", a)
        if land in self._land:
            self.eng.add_edge_unchecked(a, "grazes_on", self._land[land])
        if enclosure is not None:
            if enclosure not in self._enclosures:
                raise KeyError(f"unknown enclosure: {enclosure}")
            self.eng.add_edge_unchecked(a, "kept_in", self._enclosures[enclosure])
        return a

    # ---------------------------------------------------- animal life cycle (Phase 008)
    def _town_period(self):
        return float(self.eng.node(self._town)["attrs"].get("period", 0.0))

    def _animal_month_days(self):
        """One sim month: the calendar year split into twelve (TIME.days_per_year / 12 = 30 days)."""
        return float(self.E.TIME["days_per_year"]) / 12.0

    def _is_mature(self, attrs):
        return float(attrs.get("age_days", 0.0)) >= float(self.E.ANIMALS[attrs["species"]]["matures"]) * self._animal_month_days()

    def _record_animal_death(self, node, cause):
        """Mark an animal dead, with why and when. Other animal deaths are recorded the same way."""
        self.eng.set_attr(node, "alive", 0.0)
        self.eng.set_attr(node, "death_cause", str(cause))
        self.eng.set_attr(node, "death_period", self._town_period())

    def _advance_animal_life(self, fed):
        """One period of animal life: ageing, death at lifespan, births after gestation, and conception.

        `fed` maps each animal alive at the start of the period to whether it had eaten since the last
        period (hunger zero before this period's metabolism). A female breeds only when she is mature, fed,
        not already carrying, past her breeding interval, and shares an enclosure with a mature, fed male
        of her species. The sire is the first such male by name, and dams are considered in name order,
        so breeding is deterministic. Breeding is a physical event: the world does not choose a mate.
        """
        # 1. Ageing, and death at the lifespan.
        for name in sorted(self._animals):
            if not self.animal_alive(name):
                continue
            node = self._animals[name]
            attrs = self.eng.node(node)["attrs"]
            age = float(attrs.get("age_days", 0.0)) + 1.0
            self.eng.set_attr(node, "age_days", age)
            if age >= float(self.E.ANIMALS[attrs["species"]]["lifespan"]) * self._animal_month_days():
                self._record_animal_death(node, "old_age")
        # 2. Gestation: a carrying dam gives birth when the gestation is complete.
        for name in sorted(self._animals):
            if not self.animal_alive(name):
                continue
            node = self._animals[name]
            carrying = float(self.eng.node(node)["attrs"].get("gestating_days", 0.0))
            if carrying <= 0.0:
                continue
            carrying -= 1.0
            self.eng.set_attr(node, "gestating_days", max(0.0, carrying))
            if carrying <= 0.0:
                self._give_birth(name)
        # 3. Conception.
        for dam in sorted(self._animals):
            if not self.animal_alive(dam) or not fed.get(dam, False):
                continue
            node = self._animals[dam]
            attrs = self.eng.node(node)["attrs"]
            spec = self.E.ANIMALS[attrs["species"]]
            if (not spec.get("breeds") or attrs.get("sex") != "female" or not self._is_mature(attrs)
                    or float(attrs.get("gestating_days", 0.0)) > 0.0):
                continue
            if float(attrs["age_days"]) - float(attrs["conceived_age"]) < float(spec["breeding_interval_days"]):
                continue
            enclosure = self.animal_enclosure(dam)
            if enclosure is None:
                continue
            sire = next((male for male in sorted(self._animals)
                         if male != dam and self.animal_alive(male) and fed.get(male, False)
                         and self.eng.node(self._animals[male])["attrs"].get("species") == attrs["species"]
                         and self.eng.node(self._animals[male])["attrs"].get("sex") == "male"
                         and self._is_mature(self.eng.node(self._animals[male])["attrs"])
                         and self.animal_enclosure(male) == enclosure), None)
            if sire is None:
                continue
            self.eng.set_attr(node, "gestating_days", float(spec["gestation_days"]))
            self.eng.set_attr(node, "sire", sire)
            self.eng.set_attr(node, "conceived_age", float(attrs["age_days"]))

    def _give_birth(self, dam):
        """Add the litter of `dam` at her place, in her household, on her land, and in her enclosure.

        Each young is a new Animal with age zero. Its sex is a pure function of the map seed, the dam, her
        litter number, and the index within the litter; the NPC setup for its species is applied when the
        game next syncs animal backends.
        """
        node = self._animals[dam]
        attrs = self.eng.node(node)["attrs"]
        spec = self.E.ANIMALS[attrs["species"]]
        cell = self.animal_position(dam)
        enclosure = self.animal_enclosure(dam)
        household = next((name for name, hnode in self._households.items()
                          if self.eng.has_edge(hnode, "keeps_animal", node)), None)
        land = next((name for name, lnode in self._land.items() if self.eng.has_edge(node, "grazes_on", lnode)), None)
        period = int(self._town_period())
        litter_no = int(float(attrs.get("births", 0.0)))
        self.eng.set_attr(node, "births", float(litter_no + 1))
        for index in range(int(spec["litter"])):
            # The sex is a pure function of the map seed, the dam, her litter number, and the index, so a
            # restored checkpoint gives the same sexes as an uninterrupted run.
            draw = random.Random(f"{self._animal_life_seed}:{dam}:{litter_no}:{index}").random()
            sex = "male" if draw < float(spec["birth_male_share"]) else "female"
            young = f"{attrs['species']}_b{period}_{len(self._animals) + 1}"
            while young in self._animals:
                young += "_"
            self.add_animal(young, attrs["species"], cell=cell, household=household, land=land,
                            enclosure=enclosure, sex=sex, age_days=0.0)
            young_node = self._animals[young]
            self.eng.set_attr(young_node, "dam", dam)
            self.eng.set_attr(young_node, "sire", attrs["sire"])

    def animal_affordances(self, name):
        if name not in self._animals:
            raise KeyError(f"unknown animal: {name}")
        attrs = self.eng.node(self._animals[name])["attrs"]
        if float(attrs.get("alive", 0.0)) != 1.0:
            return [{"action": "stay"}]
        position = self.animal_position(name)
        enclosure = self.animal_enclosure(name)
        options = []
        if position is not None:
            adjacent = ((position[0] + 1, position[1]), (position[0] - 1, position[1]),
                        (position[0], position[1] + 1), (position[0], position[1] - 1))
            for cell in adjacent:
                if cell in self._map_cells and self._animal_allowed_cell(name, cell):
                    options.append({"action": "move", "target": cell})
        store_cell = self.map_position_node(self._store)
        feed_reachable = (position is not None and store_cell is not None
                          and self.distance(position, store_cell) is not None
                          and self.distance(position, store_cell) <= 1)
        if (feed_reachable and self._feed_qty(attrs.get("eats", "")) >= float(attrs.get("ration", 1.0))):
            options.append({"action": "eat", "kind": attrs.get("eats", "")})
        # Herding is a possible animal action whenever another living animal
        # can physically be moved toward an enclosure. Which target matters
        # to this animal is a backend preference, not a world affordance.
        for target, target_node in sorted(self._animals.items()):
            if target == name:
                continue
            target_attrs = self.eng.node(target_node)["attrs"]
            target_enclosure = self.animal_enclosure(target) or enclosure
            if (float(target_attrs.get("alive", 0.0)) == 1.0
                    and target_enclosure in self._enclosures
                    and self.animal_position(target) is not None):
                options.append({"action": "herd", "target": target,
                                "target_species": target_attrs.get("species", ""),
                                "target_position": self.animal_position(target),
                                "target_enclosure": target_enclosure,
                                "enclosure_intact": bool(self.enclosure_intact(target_enclosure)),
                                "enclosure_cells": sorted(self._enclosure_cells.get(target_enclosure, set()))})
        options.append({"action": "stay"})
        return options

    def _herd(self, dog, target):
        dog_position = self.animal_position(dog)
        target_position = self.animal_position(target)
        if dog_position is None or target_position is None:
            return False
        if dog_position != target_position:
            self._animal_step_toward(dog, target_position)
            return True
        enclosure = self.animal_enclosure(target) or self.animal_enclosure(dog)
        if not enclosure:
            return False
        allowed = self._enclosure_cells[enclosure]
        if target_position in allowed:
            return False
        destination = min(allowed, key=lambda cell: self.distance(target_position, cell)
                          if self.distance(target_position, cell) is not None else 10**9)
        self._animal_step_toward(target, destination)
        self.eng.add_edge_unchecked(self._animals[dog], "herded", self._animals[target])
        return True

    def apply_animal_action(self, name, action, params=None):
        """Validate and enact one backend-selected animal action physically."""
        if name not in self._animals:
            raise KeyError(f"unknown animal: {name}")
        node = self._animals[name]
        if not self.animal_alive(name):
            return False
        action = str(action or "stay")
        params = dict(params or {})
        options = self.animal_affordances(name)
        if not any(option.get("action") == action
                   and {key: value for key, value in option.items()
                        if key in {"target", "kind"}} ==
                   {key: value for key, value in params.items()
                    if key in {"target", "kind"}}
                   for option in options):
            return False
        self.eng.set_attr(node, "last_npc_action", action)
        target = params.get("target")
        if action == "move" and target is not None:
            before = self.animal_position(name)
            return self._animal_move_to_neighbor(name, tuple(target)) != before
        if action == "herd" and target in self._animals:
            return self._herd(name, target)
        if action == "eat":
            kind = str(params.get("kind", ""))
            attrs = self.eng.node(node)["attrs"]
            ration = float(attrs.get("ration", 1.0))
            self._consume_feed(kind, ration)           # a diet (e.g. scraps) may draw on several stocks
            self.eng.set_attr(node, "hunger", 0.0)
            manure = float(self.E.ANIMALS.get(attrs.get("species", ""), {}).get("manure", 0.0))
            if manure > 0.0:                            # a fed animal leaves manure to be collected
                self.set_stock("manure", self.qty("manure") + manure)
            return True
        return action == "stay"

    def _husbandry_yield(self, actor, animal, task):
        """Perform one data-defined animal-care yield with a period cooldown.

        Returns 0.0 for any refusal: an unknown resident, animal or task, a task
        for another species, a dead animal, a resident not standing with the
        animal, a cooldown, or an empty product.
        """
        if actor not in self._actors or animal not in self._animals or task not in self.E.ANIMAL_HUSBANDRY:
            self._refuse("unknown_target")
            return 0.0
        if (self._turn > 0
                and self.actor_position(actor) != self.map_position_node(self._animals[animal])):
            self._refuse("not_in_reach")
            return 0.0
        spec = self.E.ANIMAL_HUSBANDRY[task]
        an = self._animals[animal]
        aa = self.eng.node(an)["attrs"]
        if aa["species"] != spec["species"] or float(aa.get("alive", 0.0)) != 1.0:
            self._refuse("wrong_target")
            return 0.0
        period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        epoch_key = f"{task}_epoch"
        last = float(aa.get(epoch_key, -float(spec["cooldown"])))
        if period - last < float(spec["cooldown"]):
            # Phase 049: tending again too soon is allowed. It yields nothing, costs the time, and the animal is fussed.
            self._husbandry_fussed = True
            self.eng.set_attr(an, "fussed", float(aa.get("fussed", 0.0)) + 1.0)
            return 0.0
        product = spec["product"]
        amount = float(self.E.ANIMALS[aa["species"]].get("gives", {}).get(product, 0.0))
        if amount <= 0.0:
            self._refuse("wrong_target")
            return 0.0
        if not self._store_open(actor):
            self._refuse("store_locked")
            return 0.0
        self.set_stock(product, self.qty(product) + amount)
        self.eng.set_attr(an, epoch_key, period)
        self.eng.add_edge_unchecked(self._actors[actor], "performed_husbandry", an)
        return amount

    def _tend_outcome(self, actor, animal, task):
        """A tending major action is enacted when it yields, and also when it is too soon (Phase 049: the animal is
        fussed and the time is spent). Refusals of impossible tending still return False through _husbandry_yield."""
        self._husbandry_fussed = False
        amount = self._husbandry_yield(actor, animal, task)
        return amount > 0.0 or bool(self._husbandry_fussed)

    def milk(self, milker, cow):
        return self._husbandry_act(milker, cow, "milk")

    def shear(self, shearer, sheep):
        return self._husbandry_act(shearer, sheep, "shear")

    def _husbandry_act(self, actor, animal, task):
        """One standalone milking or shearing. The slot is claimed only for a yield that happens."""
        if self._turn == 0 or self._major_dispatch:
            return self._husbandry_yield(actor, animal, task)
        result = {"amount": 0.0}

        def attempt():
            result["amount"] = self._husbandry_yield(actor, animal, task)
            return result["amount"] > 0.0

        self._claimed_attempt(actor, task, attempt)
        return result["amount"]

    def _draw_village_water(self):
        """Draw one period's renewable water yield into the physical store."""
        if not self._water_sources:
            return 0.0
        drawn = 0.0
        for source in self._water_sources.values():
            attrs = self.eng.node(source)["attrs"]
            if float(attrs.get("available", 0.0)) != 1.0:
                continue
            drawn += max(0.0, float(attrs.get("capacity", 0.0)))
        if drawn:
            self.set_stock("water", self.qty("water") + drawn)
        return drawn

    def _draw_village_pasture(self):
        """Regrow forage on the mapped pasture as physical stocks."""
        pasture = self._land.get("village_pasture")
        if pasture is None:
            return 0.0
        area = float(self.eng.node(pasture)["attrs"].get("area", 0.0))
        produced = 0.0
        for kind, per_area in self.E.PASTURE_YIELDS.items():
            if kind not in self._stock:
                continue
            amount = area * float(per_area)
            self.set_stock(kind, self.qty(kind) + amount)
            produced += amount
        return produced

    def _advance_infrastructure(self):
        """Apply small data-defined failure events to physical infrastructure."""
        for name, node in self._infrastructure.items():
            attrs = self.eng.node(node)["attrs"]
            if float(attrs.get("condition", 1.0)) <= 0.0:
                continue
            risk = float(attrs.get("failure_risk", 0.0))
            if risk > 0.0 and self._rng.random() < risk:
                condition = max(0.0, float(attrs.get("condition", 1.0)) - 0.25)
                self.eng.set_attr(node, "condition", condition)
                self.record_observation(None, "storage" if attrs.get("kind") in {"granary", "root_cellar"}
                                        else "authority", infrastructure=name,
                                        condition=condition)

    def _living_crops(self):
        return [crop for crop in self.eng.neighbours(self._town, "has_crop")
                if float(self.eng.node(crop)["attrs"].get("alive", 0.0)) == 1.0]

    def _crop_land_name(self, crop):
        for land in self.eng.neighbours(crop, "on_land"):
            for name, node in self._land.items():
                if node == land:
                    return name
        return None

    def _seed_village_crops(self, target=None):
        """Sow the founding grain beds the pack's balance scenario describes (BALANCE_SCENARIO beds).

        The founding crops are intentionally small and readable in the map. Additional beds are
        still ordinary Crop nodes on those parcels; they represent cultivated area rather than new
        map tiles. The beds are sown round-robin across crops, skipping a crop once it has its count
        or its seed runs out, so the town the balance model assumes is the town that is built
        (Phase 007). `target` caps the total grain beds sown (default: the scenario's total).
        """
        if not self._land:
            return 0
        farmers = self._workers_with_roles(self.E.LABOUR_TASKS["farm"]["worker_roles"], alive_only=False)
        if not farmers:
            return 0
        wanted = {crop: int(n) for crop, n in (self.E.BALANCE_SCENARIO or {}).get("beds", {}).items()}
        if not wanted:
            return 0
        if target is None:
            target = sum(wanted.values())
        crops = tuple(wanted)
        # Beds already sown (the founding crops) count toward each crop's number.
        sown = {crop: 0 for crop in crops}
        for node in self._living_crops():
            kind = str(self.eng.node(node)["attrs"].get("crop", ""))
            if kind in sown:
                sown[kind] += 1
        added = 0
        land_names = [name for name in self._land if name.startswith("farm_plot_")]
        turn = 0
        while sum(sown.values()) < target:
            open_crops = [c for c in crops if sown[c] < wanted[c]
                          and self.qty(self.E.CROPS[c]["seed"]) >= 1.0]
            if not open_crops:
                break
            crop = open_crops[turn % len(open_crops)]
            turn += 1
            land = land_names[added % len(land_names)]
            if self.sow(farmers[added % len(farmers)], crop, land=land) is None:
                break
            sown[crop] += 1
            added += 1
        return added

    def _recipe_inputs_available(self, recipe, actor):
        """Whether the recipe's inputs can be drawn for `actor` right now, by the same plan a job
        uses when it completes (see `_plan_inputs`), and whether its tools are usable."""
        data = self._recipe_specs.get(recipe)
        if data is None or not self._recipe_in_season(recipe):
            return False
        # Tools are per worker: a trade worker's instrument is at their workplace or in hand,
        # and an open (household) recipe needs the worker's own tool.
        needs = [self._input_need(kind, qty) for kind, qty in data.get("in", [])]
        return self._plan_inputs(actor, needs) is not None and self._recipe_tools_usable(actor, recipe)

    def _input_need(self, kind, qty):
        """One recipe input as (kind, qty, is_item, slot_type), classified as `_install_recipe` does."""
        if self.E.is_input_type(kind):
            return (kind, float(qty), False, kind)
        icls = self._item_specs.get(kind, {}).get("class")
        is_item = icls not in (None, "material") and bool(self._item_specs.get(kind, {}).get("discrete", True))
        return (kind, float(qty), is_item, "")

    def _bulk_sources(self, actor, kind):
        """Where a bulk unit is drawn from, in order: the worker's own inventory, then each container
        standing on the worker's current cell that the worker may access, then the town store.

        A source is ("own", carrier), ("box", container) or ("store", None). Containers without a
        mapped cell are never at the worker's cell, so they are not drawn on. An actor who is not a
        resident (or a call with no actor) draws from the store only. A resident with no access to the
        locked town store (`_store_open`) is not offered the store tier, so the job waits (Phase 030)."""
        sources = []
        if actor in self._actors and actor in self._actor_inventories:
            sources.append(("own", self._actor_inventories[actor]))
            cell = self.actor_position(actor)
            carriers = set(self._actor_inventories.values())
            if cell is not None:
                for name in self._containers:
                    if name in carriers or self.container_position(name) != cell:
                        continue
                    if self._container_accessible(actor, name):
                        sources.append(("box", name))
        if self._store_open(actor):
            sources.append(("store", None))
        return sources

    def _source_qty(self, src, kind):
        label, name = src
        return self.qty(kind) if label == "store" else self.contents(name, kind)

    def _source_label(self, src):
        label, name = src
        return "box:" + name if label == "box" else label

    def _bulk_available(self, actor, kind):
        """Units of a bulk kind the actor can draw on right now, across every source."""
        return round(sum(self._source_qty(src, kind) for src in self._bulk_sources(actor, kind)), 4)

    def _draw_units(self, actor, kind, amount, claimed):
        """Plan `amount` units of `kind` in source order, after `claimed` units already promised to
        earlier inputs of the same job. Returns [(source, units)], or None if the sources fall short.
        Changes nothing; the caller records the claim."""
        draws, remaining = [], float(amount)
        for src in self._bulk_sources(actor, kind):
            if remaining <= 1e-6:
                break
            have = max(0.0, self._source_qty(src, kind) - claimed.get((src, kind), 0.0))
            take = min(have, remaining)
            if take > 1e-9:
                draws.append((src, take))
                remaining -= take
        return draws if remaining <= 1e-6 else None

    @staticmethod
    def _claim(claimed, kind, draws):
        for src, units in draws:
            claimed[(src, kind)] = claimed.get((src, kind), 0.0) + units

    def _plan_input(self, actor, need, claimed):
        """Plan one input need against the units `claimed` by earlier needs. Returns
        ("item", item), ("bulk", draws) or ("type", [(member, draws), ...]), or None if short.
        `claimed` is updated only when the input fits."""
        kind, qty, is_item, slot_type = need
        if slot_type:
            local = dict(claimed)
            plan = self.E.type_plan(slot_type, qty, lambda member: sum(
                max(0.0, self._source_qty(src, member) - local.get((src, member), 0.0))
                for src in self._bulk_sources(actor, member)))
            if plan is None:
                return None
            members = []
            for member, amount in plan:
                draws = self._draw_units(actor, member, amount, local)
                if draws is None:
                    return None
                self._claim(local, member, draws)
                members.append((member, draws))
            claimed.clear()
            claimed.update(local)
            return ("type", members)
        if is_item:
            item = self._job_input(None, kind, True)
            return None if item is None else ("item", item)
        draws = self._draw_units(actor, kind, qty, claimed)
        if draws is None:
            return None
        self._claim(claimed, kind, draws)
        return ("bulk", draws)

    def _plan_inputs(self, actor, needs):
        """Plan every input of one job, in order: `needs` is [(kind, qty, is_item, slot_type)].

        Returns one plan per need (see `_plan_input`), or None if any need is short. Nothing is
        drawn here. The job takes exactly these units when it completes, and inputs are planned
        and taken one job at a time, so a unit counted for one job is gone before the next job
        plans. Two jobs cannot both count the same held units."""
        claimed, plans = {}, []
        for need in needs:
            plan = self._plan_input(actor, need, claimed)
            if plan is None:
                return None
            plans.append(plan)
        return plans

    def _take_draws(self, actor, kind, draws):
        """Remove planned units from their sources (store, carrier, or container)."""
        for src, units in draws:
            label, name = src
            if label == "store":
                self.set_stock(kind, self.qty(kind) - units)
            else:
                inner = self._containers[name][1][kind]
                self.eng.set_attr(inner, "qty", self.contents(name, kind) - units)
        if any(src[0] == "own" for src, _ in draws):
            self._refresh_carry_state(actor)

    def _record_drawn_from(self, need, entries):
        """Write on the Job's Need node where each unit came from: "kind:source=units;..."."""
        self.eng.set_attr(need, "drawn_from", ";".join(
            f"{kind}:{self._source_label(src)}={round(units, 4)}"
            for kind, src, units in entries if units > 1e-9))

    def _place_kind(self, place):
        return self.eng.node(place)["attrs"].get("kind", "")

    def _building_trades(self, kind):
        """Trades that work in a building kind: those it provides or staffs, and those whose
        TRADES entry names it as their workplace."""
        spec = self.E.BUILDINGS.get(kind, {})
        trades = {t for t, tspec in self.E.TRADES.items() if tspec.get("building") == kind}
        for role in (spec.get("provides"), spec.get("staff_role")):
            if role in self.E.TRADES:
                trades.add(role)
        return trades

    def _workshop_kit(self, kind):
        """Tool kinds a building of this kind holds at founding: the kit of each trade it houses, plus
        the tools that the trade's own (non-open) recipes name. A recipe tool outside every founding
        kit (for example a press for dairy recipes) therefore still has a physical home."""
        kit = []
        trades = self._building_trades(kind)
        for trade in sorted(trades):
            kit += list(self.E.TRADES[trade].get("tools", []))
        for name in sorted(self._recipe_specs):
            recipe = self._recipe_specs[name]
            if recipe.get("requires") in trades and not recipe.get("open"):
                kit += list(recipe.get("tools", []))
        return list(dict.fromkeys(kit))

    def _equip_workshop(self, place, kinds):
        """Place one unbroken tool of each kind at a building, unless the building already holds one
        of that kind. Idempotent, so repeated equipping never adds a second instrument."""
        for kind in kinds:
            present = any(self.eng.node(item)["attrs"].get("kind") == kind
                          for item in self.eng.neighbours(place, "has_tool_item"))
            if not present:
                item = self._new_tool_item(kind)
                self.eng.add_edge_unchecked(place, "has_tool_item", item)

    def _workplace(self, actor):
        """The installed building where the actor's trade works, or None (no trade, or not built)."""
        role = self.eng.node(self._actor(actor))["attrs"].get("role", "")
        kind = self.E.TRADES.get(role, {}).get("building")
        if kind is None:
            return None
        if kind in self._places:
            return self._places[kind]
        return next((place for place in self._places.values() if self._place_kind(place) == kind), None)

    def _inside_building(self, actor, place):
        """Whether the actor stands within the building's footprint on the map."""
        pos = self.actor_position(actor)
        if pos is None:
            return False
        for key, node in self._places.items():
            if node == place and key in self._building_sites:
                x, y, w, h = self._building_sites[key]
                return x <= pos[0] < x + w and y <= pos[1] < y + h
        return pos == self.map_position_node(place)

    def _at_workplace(self, actor):
        """The actor's workplace building if they can use its tools now. Before the clock runs
        (setup calls) location is not checked. Once it runs, a worker who has a map position must
        stand inside the building; a worker with no map position at all is not location-gated."""
        place = self._workplace(actor)
        if place is None:
            return None
        if (self._turn > 0 and self.actor_position(actor) is not None
                and not self._inside_building(actor, place)):
            return None
        return place

    @staticmethod
    def _serviceable(item_attrs):
        return float(item_attrs.get("condition", 0.0)) > 0.0 and float(item_attrs.get("broken", 0.0)) != 1.0

    def _worker_tool(self, actor, kind):
        """The tool of `kind` a trade worker uses now: an unbroken one at their workplace (when they
        are there), else one they hold. None if they have neither."""
        place = self._at_workplace(actor)
        if place is not None:
            for item in self.eng.neighbours(place, "has_tool_item"):
                attrs = self.eng.node(item)["attrs"]
                if attrs.get("kind") == kind and self._serviceable(attrs):
                    return item
        return self._held_tool(actor, kind)

    def workshop_tool(self, kind, building=None):
        """A tool of `kind` standing at a building: the unbroken one if there is one, else the first
        found, else None. `building` names a building kind to look in; default is every building."""
        found = None
        for place in self._places.values():
            if building is not None and self._place_kind(place) != building:
                continue
            for item in self.eng.neighbours(place, "has_tool_item"):
                attrs = self.eng.node(item)["attrs"]
                if attrs.get("kind") != kind:
                    continue
                if self._serviceable(attrs):
                    return item
                found = found if found is not None else item
        return found

    def _village_start(self, actor, recipe):
        if self.busy(actor) or not self._recipe_inputs_available(recipe, actor):
            return False
        return bool(self.start(actor, recipe))

    def _workers_with_roles(self, roles, *, alive_only=True):
        """Resident names whose role is in `roles`, in cast order; `alive_only` drops the dead."""
        roles = set(roles)
        return [name for name, node in self._actors.items()
                if self.eng.node(node)["attrs"].get("role") in roles
                and (not alive_only or self.is_alive(name))]

    def _labour_workers(self, task, *, alive_only=True):
        """The residents who do a labour task: those of the first role in the task's worker_roles
        (pack order) that has any. A task with no such residents has no workers."""
        for role in self.E.LABOUR_TASKS[task]["worker_roles"]:
            names = self._workers_with_roles([role], alive_only=alive_only)
            if names:
                return names
        return []

    def _village_work_tick(self, period):
        """The founding village policy's work step. It acts as a non-resident process, so its store access is
        not guarded by `_store_open` (Phase 030); the flag is restored when the step ends."""
        previous, self._store_bypass = self._store_bypass, True
        try:
            return self._village_policy_pass(period)
        finally:
            self._store_bypass = previous

    def _village_policy_pass(self, period):
        """Perform the small, explicit founding policy used by ``run_village``.

        This is a scenario policy, not a hidden body rule.  Each successful
        operation claims the actor's current major-action slot; speech,
        requests, and other free actions remain available between these calls.
        """
        farmers = self._labour_workers("farm")
        # Keep the named farmers available for food preparation when the
        # labourers can cover field work; small scenarios with no labourers
        # still fall back to farmers for cultivation.
        # Replanting is a separate sowing action. A farmer who harvested this
        # turn cannot also sow; another available farmer may do it later.
        occupied_lands = {self._crop_land_name(crop) for crop in self._living_crops()}
        for land_name in [name for name in self._land if name.startswith("farm_plot_")]:
            if land_name in occupied_lands:
                continue
            actor = next((name for name in farmers
                          if not self.actor_turn_state(name)["major_action_used"]), None)
            if actor is None:
                break
            crop = self._rotation_crop(land_name)
            if crop is not None:
                self.sow(actor, crop, land=land_name)

        # Harvest one mature bed per available farmer.
        for crop in list(self._living_crops()):
            if not self.crop_mature(crop):
                continue
            if not farmers:
                break
            actor = next((name for name in farmers
                          if not self.actor_turn_state(name)["major_action_used"]), None)
            if actor is None:
                break
            crop_name = self.eng.node(crop)["attrs"]["crop"]
            self.harvest_crop(crop, harvester=actor)

        # Animals are handled once per period by the available husbandry roles.
        if period >= 0:
            for task, species in (("milk", "cow"), ("shear", "sheep")):
                animal = next((name for name, node in self._animals.items()
                               if self.eng.node(node)["attrs"].get("species") == species
                               and self.animal_alive(name)), None)
                actor = next((name for name in farmers
                              if not self.actor_turn_state(name)["major_action_used"]), None)
                if animal is not None and actor is not None:
                    if task == "milk":
                        self.milk(actor, animal)
                    else:
                        self.shear(actor, animal)

        # Grain chain: one miller, the bakers, then one farmer-cook at a time
        # provides a lower-throughput gruel fallback.  The one-at-a-time
        # fallback matters because timed jobs reserve inputs only when they
        # complete; launching every cook against the same visible grain pile
        # would overbook it under a batched rule pass.
        millers = self._labour_workers("mill")
        bakers = self._labour_workers("bake")
        cook_trade = self._recipe_specs["make_gruel"]["requires"]
        cooks = [name for name, node in self._actors.items()
                 if self.is_alive(name) and cook_trade in self.eng.node(node)["attrs"].get("trades", "").split(",")]
        if self.qty("bread") < max(200.0, len(self._actors) * 3.0):
            for name in cooks:
                if self.actor_turn_state(name)["major_action_used"]:
                    continue
                if self.qty("grain") >= 1 and self.qty("water") >= 2:
                    self._village_start(name, "make_gruel")
                    break
        if millers:
            grain_feed_demand = sum(float(self.eng.node(node)["attrs"].get("ration", 1.0))
                                    for node in self._animals.values()
                                    if self.eng.node(node)["attrs"].get("alive", 0.0) == 1.0
                                    and self.eng.node(node)["attrs"].get("eats", "") == "grain")
            # Poultry feed is a real competing demand. Keep several periods
            # of grain aside before the miller turns the remainder into flour.
            # Otherwise a healthy chicken can be starved by a well-intentioned
            # bread pipeline even while the total grain stock looks ample.
            reserve = self._policy_parameters("winter_food_reserve")
            grain_reserve = max(float(reserve["minimum_grain"]),
                                grain_feed_demand * float(reserve["feed_periods"]))
            for name in millers:
                grain_per_run = sum(float(q) for k, q in self._recipe_specs["grind_flour"]["in"] if k == "grain")
                if (not self.actor_turn_state(name)["major_action_used"]
                        and self.qty("grain") >= grain_per_run + grain_reserve):
                    self._village_start(name, "grind_flour")
        for name in bakers:
            if not self.actor_turn_state(name)["major_action_used"]:
                self._village_start(name, "bake_bread")     # starts only if a full oven load is in store

    def run_village(self, periods=1, *, ticks_per_period=None):
        """Advance the seeded village while each resident decides independently.

        ``tick`` pumps private Ocelot minds; this method supplies only the
        world clock and the publication cadence. ``ticks_per_period`` defaults
        to the pack's TIME ticks_per_period.
        """
        if ticks_per_period is None:
            ticks_per_period = self.E.TIME["ticks_per_period"]
        if not getattr(self, "_cast100", None):
            raise ValueError("run_village requires BigvilleWorld.from_town100()")
        if periods and not self._report_history:
            self.record_report_snapshot(label="initial")
        for _ in range(int(periods)):
            # First let the world advance: crops grow, livestock metabolise,
            # residents become hungry, and spoilage is applied. Residents do
            # not eat here; a resident policy must explicitly buy/receive and
            # then eat through the major-action API.
            self.pass_period()
            for _ in range(int(ticks_per_period)):
                self.tick()
            # Retire execution-only graph state once per workday, rather than
            # scanning the whole graph on every 15-minute engine tick.
            self._cleanup_village_transients()
            self.record_report_snapshot(label=f"clock:{int(self.calendar()['clock'])}")
        return self.sanity_report()

    def _leak_containers(self):
        """Phase 049: a vessel that is not watertight loses leak_per_period of each fluid it holds, every period. The
        lost fluid is gone; the vessel stays. Watertight vessels keep their fluid."""
        share = float(self.E.RESOLUTION["leak_per_period"])
        for name, (cn, inners) in self._containers.items():
            if float(self.eng.node(cn)["attrs"].get("watertight", 0.0)) == 1.0:
                continue
            for kind, inner in inners.items():
                if not self.is_fluid(kind):
                    continue
                qty = self.contents(name, kind)
                if qty > 0.0:
                    self.eng.set_attr(inner, "qty", qty * (1.0 - share))

    def pass_period(self, n=1):
        """Advance world metabolism and ecology without performing resident actions.

        Residents become hungry here, but no resident buys, carries, serves, or eats
        food as a side effect of time passing.  Those are actor actions.
        """
        for _ in range(int(n)):
            if self.physical_subsystems["ecology"] and getattr(self, "_cast100", None):
                self._draw_village_water()
                self._draw_village_pasture()
            self._advance_infrastructure()
            self._leak_containers()
            self.eng.set_attr(self._town, "period", float(self.eng.node(self._town)["attrs"]["period"]) + 1.0)
            self._request_rule_sweep()

    # ---------------------------------------------------- crops (seed -> grow -> harvest)
    def season(self): return self.eng.node(self._town)["attrs"]["season"]

    def set_season(self, season):
        """Turn the year to a season (spring/summer/autumn/winter) -- crops are sown in their season."""
        self.eng.set_attr(self._town, "season", season)

    def sow(self, sower, crop, *, land=None):
        """Sow a crop from its SEED. Phase 049: sowing out of its season is allowed; the seed is used and the crop fails at
        the next period (season_fail). Consumes one seed and plants a growing Crop (which then needs water each period,
        or it wilts). Returns the crop node, or None when the sowing is refused (slot, store, or no seed)."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(sower, "sow"):
            self._refuse("slot_used")
            return None
        land_cell = (self.map_position_node(self._land[land])
                     if land in self._land else None)
        if self._turn > 0 and land_cell is not None and self.actor_position(sower) != land_cell:
            return None
        spec = self.E.CROPS[crop]
        # Phase 049: sowing out of season is allowed. The seed is used and the crop fails to the season's weather at
        # the next period (season_fail), so the loss shows later.
        failing = spec["season"] != self.season()
        if not self._store_open(sower):
            self._refuse("store_locked")
            return None                                     # the seed is in the store, which this sower cannot open
        if self.qty(spec["seed"]) < 1.0:
            self._refuse("out_of_stock")
            return None                                     # another actor may have used the last seed
        self.set_stock(spec["seed"], max(0.0, self.qty(spec["seed"]) - 1.0))    # a seed is used
        c = self.eng.add_node("Crop", {"crop": crop, "age": 0.0, "thirst": 0.0, "thirst_epoch": 0.0,
                                       "alive": 1.0, "water": float(spec["water"]), "wilt": float(spec["wilt"]),
                                       "season_fail": 1.0 if failing else 0.0,
                                       "grow_periods": float(spec["grow_periods"]), "harvest": spec["harvest"],
                                       "water_armed": 0.0,
                                       "yield": float(spec["yield"]),
                                       "nitrogen": float(spec.get("nitrogen", 0.0)),
                                       "fixes": float(spec.get("fixes", 0.0)),
                                       "n_wanted": 0.0, "n_supplied": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_crop", c)
        if land in self._land:
            self.eng.add_edge_unchecked(c, "on_land", self._land[land])
            land_cells = list(self.eng.neighbours(self._land[land], "at_cell"))
            if land_cells:
                self.eng.add_edge_unchecked(c, "at_cell", land_cells[0])
        self._crops = getattr(self, "_crops", {}); self._crops[len(self._crops)] = c
        return c

    def water_crop(self, actor, crop_node):
        """Water one thirsty crop as the actor's explicit major action."""
        attrs = self.eng.node(crop_node)["attrs"]
        crop_cell = self.map_position_node(crop_node)
        if self._turn > 0 and crop_cell is not None and self.actor_position(actor) != crop_cell:
            return False
        if float(attrs.get("alive", 0.0)) != 1.0:
            return self._refuse("wrong_target")
        # Phase 049 (supervisor decision): watering an unthirsty crop stays refused (not_needed). The village trace and
        # tests/test_simple_work_food_exchange.py depend on this gate.
        if float(attrs.get("thirst", 0.0)) <= 0.0:
            return self._refuse("not_needed")
        if not self._store_open(actor):
            return self._refuse("store_locked")
        if self.qty("water") < float(attrs.get("water", 0.0)):
            return self._refuse("out_of_stock")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "water"):
            return False
        self.eng.set_attr(self._actor(actor), "water_armed", 1.0)
        self.eng.set_attr(crop_node, "water_armed", 1.0)
        self.set_stock("water", self.qty("water") - float(attrs.get("water", 0.0)))
        self.eng.set_attr(crop_node, "thirst", 0.0)
        self.eng.set_attr(crop_node, "water_armed", 0.0)
        self._request_rule_sweep()
        return float(self.eng.node(crop_node)["attrs"].get("thirst", 0.0)) == 0.0

    def harvest_crop(self, crop_node, *, harvester=None):
        """Harvest a MATURE living crop -> its yield of the product enters the store; the crop is done."""
        crop_cell = self.map_position_node(crop_node)
        if (self._turn > 0 and harvester is not None and crop_cell is not None
                and self.actor_position(harvester) != crop_cell):
            return 0.0
        if harvester is not None and not self._store_open(harvester):
            self._refuse("store_locked")
            return 0.0
        if self._turn > 0 and not self._major_dispatch:
            if harvester is None or not self._claim_major_action(harvester, "harvest"):
                return 0.0
        a = self.eng.node(crop_node)["attrs"]
        if float(a["alive"]) == 1.0:
            # Phase 049: a crop harvested before it is mature yields its maturity share of the full yield (the crop is
            # gone either way). A mature crop (maturity 1) yields the committed amounts.
            maturity = min(1.0, float(a["age"]) / max(float(a["grow_periods"]), 1e-9))
            factor = self.crop_nitrogen_factor(crop_node) * maturity
            harvested = float(a["yield"]) * factor
            self.set_stock(a["harvest"], self.qty(a["harvest"]) + harvested)
            for kind, qty in self.E.CROPS[a["crop"]].get("byproducts", {}).items():
                self.set_stock(kind, self.qty(kind) + float(qty) * factor)
            # Harvesting is also the seed loop that makes a farm renewable.
            # The returned seed is a physical reserve, not a hidden crop
            # respawn; sowing still consumes it and remains seasonal.
            seed = self.E.CROPS[a["crop"]]["seed"]
            self.set_stock(seed, self.qty(seed) + float(self.E.CROPS[a["crop"]].get("seed_return", 1.0)) * maturity)
            self.eng.set_attr(crop_node, "alive", 0.0)
            self.eng.remove_edge_unchecked(self._town, "has_crop", crop_node)
            return round(harvested, 4)
        self._refuse("wrong_target")
        return 0.0

    # ---------------------------------------------------- the nitrogen cycle (data: E.NITROGEN)
    def land_nitrogen(self, land):
        return round(float(self.eng.node(self._land[land])["attrs"].get("nitrogen", 0.0)), 4)

    def land_nitrogen_fraction(self, land):
        a = self.eng.node(self._land[land])["attrs"]
        capacity = float(a.get("nitrogen_capacity", 0.0))
        return float(a.get("nitrogen", 0.0)) / capacity if capacity > 0 else 0.0

    def crop_nitrogen_factor(self, crop_node):
        """Yield multiplier from the share of its nitrogen demand the soil met (1.0 off-land)."""
        a = self.eng.node(crop_node)["attrs"]
        wanted = float(a.get("n_wanted", 0.0))
        if wanted <= 0.0:
            return 1.0
        floor = float(self.E.NITROGEN["yield_floor"])
        return floor + (1.0 - floor) * min(1.0, float(a.get("n_supplied", 0.0)) / wanted)

    def _advance_soil_nitrogen(self):
        """Mineralisation adds to every parcel; leaching (scaled by drainage) takes from it."""
        for node in self._land.values():
            a = self.eng.node(node)["attrs"]
            capacity = float(a.get("nitrogen_capacity", 0.0))
            if capacity <= 0.0:
                continue
            nitrogen = float(a.get("nitrogen", 0.0))
            nitrogen += float(self.E.NITROGEN["mineralisation_per_area"]) * float(a.get("area", 1.0))
            drainage = float(self.E.SOILS.get(a.get("soil", ""), {}).get("drainage", 0.5))
            nitrogen -= nitrogen * float(self.E.NITROGEN["leaching"]) * drainage
            self.eng.set_attr(node, "nitrogen", min(capacity, max(0.0, nitrogen)))

    def _crop_draw_nitrogen(self, crop):
        """One period of a growing bed: draw its demand from its parcel; a legume fixes some back."""
        lands = list(self.eng.neighbours(crop, "on_land"))
        if not lands:
            return
        land, ca = lands[0], self.eng.node(crop)["attrs"]
        la = self.eng.node(land)["attrs"]
        nitrogen, capacity = float(la.get("nitrogen", 0.0)), float(la.get("nitrogen_capacity", 0.0))
        want = float(ca.get("nitrogen", 0.0))
        take = min(want, nitrogen)
        nitrogen = min(capacity, nitrogen - take + float(ca.get("fixes", 0.0)))
        self.eng.set_attr(land, "nitrogen", max(0.0, nitrogen))
        self.eng.set_attr(crop, "n_wanted", float(ca.get("n_wanted", 0.0)) + want)
        self.eng.set_attr(crop, "n_supplied", float(ca.get("n_supplied", 0.0)) + take)

    def _collect_night_soil(self):
        """Residents' waste is kept as night soil while a latrine stands; otherwise it is lost."""
        latrine_up = any(self.eng.node(node)["attrs"].get("kind") == "latrine"
                         and float(self.eng.node(node)["attrs"].get("condition", 1.0)) > 0.0
                         for node in self._infrastructure.values())
        if not latrine_up:
            return 0.0
        alive = sum(1 for node in self._actors.values()
                    if float(self.eng.node(node)["attrs"].get("alive", 0.0)) == 1.0)
        amount = alive * float(self.E.WASTE_CYCLES["human_waste"].get("per_resident", 0.0))
        if amount > 0.0:
            self.set_stock("night_soil", self.qty("night_soil") + amount)
        return amount

    def fertilise(self, actor, land, amount=None):
        """Spread fertiliser (any `nitrogen`-tagged stock: manure, compost, dung) on a land parcel.

        Returns the nitrogen added. The actor must stand on the parcel once the clock is running."""
        if land not in self._land:
            self._refuse("unknown_target")
            return 0.0
        node = self._land[land]
        cell = self.map_position_node(node)
        if self._turn > 0 and cell is not None and self.actor_position(actor) != cell:
            self._refuse("not_in_reach")
            return 0.0
        if not self._store_open(actor):
            self._refuse("store_locked")
            return 0.0
        type_name = self.E.NITROGEN["fertiliser_type"]
        la = self.eng.node(node)["attrs"]
        room = float(la.get("nitrogen_capacity", 0.0)) - float(la.get("nitrogen", 0.0))
        amount = min(float(amount if amount is not None else self.E.NITROGEN["fertilise_amount"]),
                     room, self.type_available(type_name))
        if amount <= 0.0:
            self._refuse("out_of_stock")
            return 0.0
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "fertilise"):
            self._refuse("slot_used")
            return 0.0
        if self._consume_type(type_name, amount) is None:
            self._refuse("out_of_stock")
            return 0.0
        self.eng.set_attr(node, "nitrogen", float(la.get("nitrogen", 0.0)) + amount)
        self.eng.add_edge_unchecked(self._actors[actor], "fertilised", node)
        return round(amount, 4)

    def _rotation_crop(self, land):
        """The crop a farmer would sow on this parcel now: a restorative legume when its nitrogen is
        low, else the main rotation -- the first in season with seed in store."""
        low = (land in self._land
               and self.land_nitrogen_fraction(land) < float(self.E.NITROGEN["restore_below"]))
        groups = ("restorative", "main") if low else ("main",)
        for group in groups:
            for crop in self.E.ARABLE_ROTATION[group]:
                spec = self.E.CROPS[crop]
                if spec["season"] == self.season() and self.qty(spec["seed"]) >= 1.0:
                    return crop
        return None

    def crop_age(self, crop_node): return round(float(self.eng.node(crop_node)["attrs"]["age"]), 4)
    def crop_alive(self, crop_node): return float(self.eng.node(crop_node)["attrs"]["alive"]) == 1.0
    def crop_mature(self, crop_node):
        a = self.eng.node(crop_node)["attrs"]
        return float(a["alive"]) == 1.0 and float(a["age"]) >= float(a["grow_periods"])
    def hunger(self, actor): return round(float(self.eng.node(self._actors[actor])["attrs"]["hunger"]), 4)
    def is_alive(self, actor): return float(self.eng.node(self._actors[actor])["attrs"]["alive"]) == 1.0

    def import_good(self, kind, qty):
        """Acquire an IMPORTED good from outside bigville (ink/paper/dye/salt). Only goods marked
        imported in the data can be imported -- the rest must be made locally."""
        assert self._item_specs.get(kind, {}).get("imported"), f"{kind} is not an imported good"
        return self.set_stock(kind, self.qty(kind) + float(qty))

    def animal_hunger(self, name): return round(float(self.eng.node(self._animals[name])["attrs"]["hunger"]), 4)
    def animal_alive(self, name): return float(self.eng.node(self._animals[name])["attrs"]["alive"]) == 1.0
    def is_imported(self, kind): return bool(self._item_specs.get(kind, {}).get("imported"))

    def _feed_qty(self, eats):
        """Store stock available to an animal with diet `eats` (a scraps diet takes any scraps)."""
        return sum(self.qty(kind) for kind in self.E.feed_kinds(eats))

    def _consume_feed(self, eats, ration):
        """Draw `ration` from the stocks that diet accepts, in the data's preference order."""
        remaining = float(ration)
        for kind in self.E.feed_kinds(eats):
            take = min(remaining, self.qty(kind))
            if take > 0:
                self.set_stock(kind, self.qty(kind) - take)
                remaining -= take
            if remaining <= 1e-9:
                break
        return float(ration) - remaining

    def give_product(self, animal, product):
        """The animal yields one of its products (a cow's milk, a chicken's eggs) into the store."""
        spec = self.E.ANIMALS[self.eng.node(self._animals[animal])["attrs"]["species"]]
        yield_ = float(spec.get("gives", {}).get(product, 0.0))
        if yield_ > 0:
            self.set_stock(product, self.qty(product) + yield_)
        return yield_

    def hitch(self, horse, cart):
        """Hitch a draught animal to a cart -- the cart can now haul up to the animal's PULL."""
        pull = float(self.eng.node(self._animals[horse])["attrs"]["pull"])
        self.eng.set_attr(self._containers[cart][0], "max_load", pull)
        self.eng.add_edge_unchecked(self._animals[horse], "pulls", self._containers[cart][0])
        return pull

    def butcher(self, butcher, animal):
        """BUTCHERY is a skill: a butcher turns a (living) animal into its meat + hide (the on-death
        products from ANIMALS), killing it. Only a butcher can do it."""
        assert self.eng.node(self._actors[butcher])["attrs"].get("role") == "butcher", f"{butcher} is not a butcher"
        if not self._store_open(butcher):
            self._refuse("store_locked")
            return {}
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(butcher, "butcher"):
            return {}
        an = self._animals[animal]
        if float(self.eng.node(an)["attrs"]["alive"]) != 1.0:
            return {}
        got = {}
        for product, qty in self.E.ANIMALS[self.eng.node(an)["attrs"]["species"]]["gives"].items():
            if product in self.E.SLAUGHTER_PRODUCTS:
                self.set_stock(product, self.qty(product) + float(qty)); got[product] = float(qty)
        self.eng.set_attr(an, "alive", 0.0)
        return got

    # ---------------------------------------------------- a merchant delivers imported goods
    def add_merchant(self, name, *, brings=None):
        m = self.eng.add_node("Merchant", {"name": name})
        self.eng.add_edge_unchecked(self._town, "has_merchant", m)
        self._merchants = getattr(self, "_merchants", {}); self._merchants[name] = m
        for good, qty in (brings or {}).items():
            self.set_stock(good, self.qty(good))                    # ensure a store pile exists to receive it
            g = self.eng.add_node("Stock", {"kind": good, "qty": float(qty)})
            self.eng.add_edge_unchecked(m, "carries", g)
        return m

    def deliver(self, merchant):
        """The merchant unloads what he carries into the store (mc_deliver)."""
        node = self._merchants[merchant]
        for stock in list(self.eng.neighbours(node, "carries")):
            attrs = self.eng.node(stock)["attrs"]
            kind, amount = attrs.get("kind", ""), float(attrs.get("qty", 0.0))
            self.set_stock(kind, self.qty(kind) + amount)
            if amount > 0.0:
                self._record_handover("deliver", kind, amount, ("merchant", str(merchant)), ("store", "store"))
            self.eng.remove_edge_unchecked(node, "carries", stock)
            self.eng.remove_node(stock)
        self._request_rule_sweep()

    # ---------------------------------------------------- books (physical records; cognition owns learning)
    def write_in_book(self, author, book, recipe):
        """Write recipe content into a made book (a physical record with weight)."""
        self.eng.set_attr(book, "recipe", recipe)
        self.eng.add_edge_unchecked(self._actors[author], "wrote", book)
        self.create_event("recipe_written", subject=author,
                          detail=f"{author} wrote {recipe} in a book.",
                          observer=author, severity=0.05)
        return book

    def read_book(self, reader, book):
        """Return the inscription as an observation; comprehension is learner-owned."""
        recipe = self.eng.node(book)["attrs"].get("recipe", "")
        self.create_event("recipe_read", subject=reader,
                          detail=f"{reader} inspected a book containing {recipe}.",
                          observer=reader, severity=0.02)
        return recipe

    def book_recipe(self, book): return self.eng.node(book)["attrs"].get("recipe", "")

    def animal_role(self, animal): return self.eng.node(self._animals[animal])["attrs"]["role"]
    def animal_gives(self, species): return dict(self.E.ANIMALS[species]["gives"])
    def animal_pull(self, animal): return round(float(self.eng.node(self._animals[animal])["attrs"]["pull"]), 4)

    def use_as_store(self, name, item, holds, *, lock_id=0.0, locked=False, keys_required=1):
        """Press a MADE container-item (a cooper's barrel, a joiner's chest) into service as a real
        container -- the SAME node gains a capacity (from the item data) + an inner Stock + a
        has_container edge, so the container rules fill it. A made barrel IS a container."""
        kind = self.tool_kind(item)
        spec = self._item_specs.get(kind, {})
        assert spec.get("container"), f"{kind} is not a container item"
        return self._wire_container(name, item, kind, holds, lock_id, locked, keys_required=keys_required)

    def give_key(self, actor, opens):
        """Setup: put a new key that opens the lock `opens` in an actor's carried things. A key is a discrete
        ToolItem of kind KEY_KIND, held like a tool, so it can be given, dropped, picked up and taken."""
        self._actor(actor)
        item = self.eng.add_node("ToolItem", {"kind": self.E.KEY_KIND, "weight": float(self.E.KEY_WEIGHT),
                                              "quality": 1.0, "condition": 1.0, "broken": 0.0, "wear": 0.0,
                                              "decay": 0.0, "use_armed": 0.0, "repair_armed": 0.0,
                                              "opens": float(opens)})
        self.eng.add_edge_unchecked(self._actors[actor], "holds", item)
        self._refresh_carry_state(actor)
        return item

    def _holds_key(self, actor, lock_id):
        """Whether `actor` holds, in a hand or carried, a key whose `opens` is `lock_id`."""
        if not lock_id or actor not in self._actors:
            return False
        node = self._actors[actor]
        for edge in ("holds_in_hand", "holds_tableware", "holds"):
            for item in self.eng.neighbours(node, edge):
                attrs = self.eng.node(item)["attrs"]
                if attrs.get("kind") == self.E.KEY_KIND and float(attrs.get("opens", 0.0)) == float(lock_id):
                    return True
        return False

    def _node_accessible(self, actor, node):
        """Whether `actor` may use a container or the store now. An unlocked one is open to everyone. A locked
        one opens to a holder of its key, but only when one key is enough (keys_required 1): a lock that needs
        several keyholders stays shut until they have unlocked it (see `unlock`)."""
        attrs = self.eng.node(node)["attrs"]
        if float(attrs.get("locked", 0.0)) != 1.0:
            return True
        if float(attrs.get("keys_required", 1.0)) > 1.0:
            return False
        return self._holds_key(actor, float(attrs.get("lock_id", 0.0)))

    def _container_accessible(self, actor, container):
        if container not in self._containers:
            return False
        # Phase 050: a container broken by an attempt is no longer opened (its contents are not spilled; see the report).
        if float(self.eng.node(self._containers[container][0])["attrs"].get("destroyed", 0.0)) == 1.0:
            return False
        return self._node_accessible(actor, self._containers[container][0])

    def _store_open(self, actor):
        """The one check every resident-initiated path uses before it reads or writes the town stock (Phase 030).
        Non-residents (and the founding village policy while `_store_bypass` is set) are not guarded: decay,
        period effects and the founding policy act on the store directly."""
        if self._store_bypass or actor not in self._actors:
            return True
        return self._node_accessible(actor, self._store_lock_node())

    def _store_lock_node(self):
        return next(iter(self.eng.neighbours(self._store, "has_lock")))

    def _lockable(self, name):
        """(lock node, cell node) of a lockable thing: a container by name (its own node holds the lock and sits on
        the cell), or the town store (name "store"), whose Lock node holds the lock and whose store node sits on
        the cell. None for a name that is neither."""
        if name == "store":
            return self._store_lock_node(), self._store
        if name in self._containers:
            node = self._containers[name][0]
            return node, node
        return None

    def _clear_authorisations(self, node):
        for keyholder in list(self.eng.neighbours(node, "authorised_by")):
            self.eng.remove_edge_unchecked(node, "authorised_by", keyholder)

    def lock(self, actor, container):
        """Lock a container or the town store ("store") with a key `actor` holds, from its cell (Phase 030).
        Refused with no_lock, not_in_reach, no_key, or already_locked."""
        self._actor(actor)
        found = self._lockable(container)
        if found is None:
            return self._refuse("unknown_target")
        node, place = found
        attrs = self.eng.node(node)["attrs"]
        lock_id = float(attrs.get("lock_id", 0.0))
        if lock_id <= 0.0:
            return self._refuse("no_lock")
        cell = self.map_position_node(place)
        if cell is not None and self.actor_position(actor) != cell:
            return self._refuse("not_in_reach")
        if not self._holds_key(actor, lock_id):
            return self._refuse("no_key")
        if float(attrs.get("locked", 0.0)) == 1.0:
            return self._refuse("already_locked")
        self._clear_authorisations(node)
        self.eng.set_attr(node, "locked", 1.0)
        return True

    def unlock(self, actor, container):
        """Unlock a container or the town store ("store") with a key `actor` holds, from its cell (Phase 030).
        A lock with keys_required above 1 records this keyholder's turn of the key, and opens once that many
        distinct keyholders have turned it. Refused with no_lock, not_in_reach, no_key, already_unlocked,
        or already_authorised."""
        self._actor(actor)
        found = self._lockable(container)
        if found is None:
            return self._refuse("unknown_target")
        node, place = found
        attrs = self.eng.node(node)["attrs"]
        lock_id = float(attrs.get("lock_id", 0.0))
        if lock_id <= 0.0:
            return self._refuse("no_lock")
        cell = self.map_position_node(place)
        if cell is not None and self.actor_position(actor) != cell:
            return self._refuse("not_in_reach")
        if not self._holds_key(actor, lock_id):
            return self._refuse("no_key")
        if float(attrs.get("locked", 0.0)) != 1.0:
            return self._refuse("already_unlocked")
        needed = max(1, int(float(attrs.get("keys_required", 1.0))))
        if needed <= 1:
            self.eng.set_attr(node, "locked", 0.0)
            return True
        keyholder = self._actor(actor)
        turned = list(self.eng.neighbours(node, "authorised_by"))
        if keyholder in turned:
            return self._refuse("already_authorised")
        self.eng.add_edge_unchecked(node, "authorised_by", keyholder)
        if len(turned) + 1 >= needed:
            self._clear_authorisations(node)
            self.eng.set_attr(node, "locked", 0.0)
        return True

    def put(self, actor, container, kind, amount=1.0):
        """Put held stock into a physical container as a major action.

        Containers are capability-based rather than whitelist-based: the
        material only needs to fit by volume/load, and fluids need a watertight
        vessel.  Storage class changes decay, never permission.  ``fill``
        remains the store-to-container setup/access primitive; ``put`` is the
        resident action for moving something they hold into that container.
        """
        self._actor(actor)
        amount = float(amount)
        container_cell = self.container_position(container)
        if (self._turn > 0 and container_cell is not None and self.actor_position(actor) != container_cell):
            return False
        if amount <= 0.0:
            return self._refuse("malformed")
        if not self._container_accessible(actor, container):
            return self._refuse("container_locked")
        if self.inventory_qty(actor, kind) < amount:
            return self._refuse("out_of_stock")
        # Phase 049: what the vessel cannot hold (by volume or load) spills onto the cell; a fluid in a vessel that is not
        # watertight is put in and leaks each period (leak_per_period). Nothing here refuses for want of room.
        item_vol = float(self.item_volume(kind))
        item_wt = float(self.item_weight(kind))
        attrs = self.eng.node(self._containers[container][0])["attrs"]
        room_vol = max(0.0, self.capacity(container) - self.used_volume(container))
        room_load = max(0.0, float(attrs.get("max_load", 1e18)) - self.contents_weight(container))
        fit_vol = amount if item_vol <= 0.0 else room_vol / item_vol
        fit_load = amount if item_wt <= 0.0 else room_load / item_wt
        fit = max(0.0, min(amount, fit_vol + 1e-9, fit_load + 1e-9))
        excess = amount - fit
        if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(actor, "put"):
            return False
        inners = self._containers[container][1]
        if kind not in inners:
            node = self._containers[container][0]
            container_kind = self.eng.node(node)["attrs"].get("kind", "")
            inners[kind] = self._new_inner_stock(node, container_kind, kind)
        source = self._inventory_stock(actor, kind)
        target = inners[kind]
        if fit > 0.0:
            self._mix_freshness(target, fit, self._pile_condition(source))
            self.eng.set_attr(target, "qty", self.contents(container, kind) + fit)
        self.eng.set_attr(source, "qty", self.inventory_qty(actor, kind) - amount)
        if excess > 0.0:
            self._drop_stock(actor, kind, excess)
        self._refresh_carry_state(actor)
        self.eng.add_edge_unchecked(self._actor(actor), "put_into", self._containers[container][0])
        self._record_handover("put", kind, fit, self._actor_endpoint(actor), ("container", str(container)))
        return True

    def fill(self, actor, container, kind, amount):
        """Fill `amount` of `kind` into a container (if it fits by volume and, for a fluid, the vessel
        is watertight). Containers accept content not listed in their initial `holds`; storage
        preferences affect decay, not permission."""
        if not self._store_open(actor):
            return self._refuse("store_locked")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "fill"):
            return False
        if kind not in self._containers[container][1]:
            node = self._containers[container][0]
            container_kind = self.eng.node(node)["attrs"].get("kind", "")
            self._containers[container][1][kind] = self._new_inner_stock(node, container_kind, kind)
        self.eng.set_attr(self._actors[actor], "fill_kind", kind)
        self.eng.set_attr(self._actors[actor], "fill_amount", float(amount))
        self.eng.set_attr(self._actors[actor], "fill_armed", 1.0); self._request_rule_sweep()
        return True

    def empty(self, actor, container, kind, amount):
        if not self._store_open(actor):
            return self._refuse("store_locked")
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "empty"):
            return False
        self.eng.set_attr(self._actors[actor], "empty_kind", kind)
        self.eng.set_attr(self._actors[actor], "empty_amount", float(amount))
        self.eng.set_attr(self._actors[actor], "empty_armed", 1.0); self._request_rule_sweep()
        return True

    def fetch(self, actor, kind, amount=1.0, *, source=None):
        """Carry physical stock from a store/container into the actor's carrier.

        Fetching is deliberately separate from buying: it is a handling action
        that changes location and ownership of physical stock. It records a
        Handover and no market record.  The default source is the town's mapped store;
        a named container may also be used when the actor can access it.
        """
        self._actor(actor)
        amount = float(amount)
        if amount <= 0.0:
            return self._refuse("malformed")
        if source is None:
            source_cell = self.map_position_node(self._store)
            if self._turn > 0 and self.actor_position(actor) != source_cell:
                return self._refuse("not_at_site")
            if not self._store_open(actor):
                return self._refuse("store_locked")
            if self.qty(kind) < amount:
                return self._refuse("out_of_stock")
            self._move_stock_to_inventory(actor, kind, amount)
        else:
            if source not in self._containers or not self._container_accessible(actor, source):
                return self._refuse("container_locked")
            if self.container_position(source) != self.actor_position(actor):
                return self._refuse("not_in_reach")
            if self.contents(source, kind) < amount:
                return self._refuse("out_of_stock")
            # Phase 049: a carrier over capacity takes what fits; the rest drops at their feet.
            used = self.used_volume(self._actor_inventories[actor])
            item_vol = float(self.item_volume(kind))
            room = max(0.0, self.capacity(self._actor_inventories[actor]) - used)
            fit = amount if item_vol <= 0.0 else min(amount, room / item_vol + 1e-9)
            inner = self._containers[source][1][kind]
            target = self._inventory_stock(actor, kind, create=True)
            if fit > 0.0:
                self._mix_freshness(target, fit, self._pile_condition(inner))
                self.eng.set_attr(target, "qty", self.inventory_qty(actor, kind) + fit)
            self.eng.set_attr(inner, "qty", self.contents(source, kind) - amount)
            if amount - fit > 0.0:
                self._drop_stock(actor, kind, amount - fit)
            self._refresh_carry_state(actor)
        self._record_handover("fetch", kind, amount, ("store", "store") if source is None else ("container", str(source)),
                              self._actor_endpoint(actor))
        self.eng.add_edge_unchecked(self._actor(actor), "fetched", self._store)
        return True

    def contents(self, container, kind):
        inners = self._containers[container][1]
        return round(float(self.eng.node(inners[kind])["attrs"]["qty"]), 4) if kind in inners else 0.0
    def capacity(self, container): return round(float(self.eng.node(self._containers[container][0])["attrs"]["capacity"]), 4)
    def is_locked(self, container): return float(self.eng.node(self._containers[container][0])["attrs"]["locked"]) == 1.0
    def used_volume(self, container):
        return round(sum(float(self.eng.node(i)["attrs"]["qty"]) * float(self.eng.node(i)["attrs"]["volume"])
                         for i in self._containers[container][1].values()), 4)
    def contents_weight(self, container):
        return round(sum(float(self.eng.node(i)["attrs"]["qty"]) * float(self.eng.node(i)["attrs"]["weight"])
                         for i in self._containers[container][1].values()), 4)
    def item_weight(self, kind): return self._phys(kind)[0]
    def item_volume(self, kind): return self._phys(kind)[1]
    def is_fluid(self, kind): return self._phys(kind)[2] == 1.0

    def add_tradesperson(self, name, trade, *, skill=None, station=None, literacy=None, capability=None):
        """Add a tradesperson: role = the trade, skill from the TRADES table (unifies trade + skill).
        Townsfolk are UPPITY -- educated by default; `station` (labouring/middle/educated) or an
        explicit literacy/capability sets a lower tier, and literate trades (scribe, teacher) carry
        their own in the TRADES data. The defaults come from the pack's ACTOR_DEFAULTS."""
        t = self.E.TRADES.get(trade, {})
        station = self.E.ACTOR_DEFAULTS["station"] if station is None else station
        s = skill if skill is not None else float(t.get("base_skill", self.E.ACTOR_DEFAULTS["skill"]))
        prof = self.E.STATION_EDUCATION.get(station, self.E.STATION_EDUCATION["educated"])
        lit = literacy if literacy is not None else float(t.get("literacy", prof["literacy"]))
        cap = capability if capability is not None else float(t.get("capability", prof["capability"]))
        return self.add_actor(name, role=trade, skill=s, literacy=lit, capability=cap)

    def add_actor(self, name, *, role, skill=None, station=None, literacy=None, capability=None,
                  learn=None, home_cell=None, work_cell=None, klass="", age=None,
                  life_stage=None, role_identity=None, group="", traits=None, trades=()):
        """Add a resident. LITERACY + general CAPABILITY are class-graded (station), but this town is
        UPPITY -- residents default to EDUCATED. `station` (labouring/middle/educated) or an explicit
        literacy/capability picks a lower tier; `learn` is the aptitude that scales schooling (0 = cannot learn).
        Every default that is not given comes from the pack's ACTOR_DEFAULTS (and CARE for starvation)."""
        defaults = self.E.ACTOR_DEFAULTS
        skill = defaults["skill"] if skill is None else skill
        station = defaults["station"] if station is None else station
        learn = defaults["learn"] if learn is None else learn
        age = defaults["age"] if age is None else age
        life_stage = defaults["life_stage"] if life_stage is None else life_stage
        prof = self.E.STATION_EDUCATION.get(station, self.E.STATION_EDUCATION["labouring"])
        lit = prof["literacy"] if literacy is None else float(literacy)
        cap = prof["capability"] if capability is None else float(capability)
        stage = self.E.LIFE_STAGES.get(life_stage, self.E.LIFE_STAGES["adult"])
        healthy = self.E.HEALTH_CONDITIONS["healthy"]
        founding_levels, founding_metas = self._founding_levels(role, trades, skill)
        a = self.eng.add_node("Agent", {"name": name, "role": role, "skill": float(skill),
                                        "age": float(age), "life_stage": life_stage, "health": "healthy",
                                        "health_value": float(defaults["health_value"]), "disease": "",
                                        "injury": float(defaults["injury"]),
                                        "coin": float(defaults["coin"]), "wage_due": 0.0,
                                        "reputation": float(defaults["reputation"]),
                                        "klass": klass, "group": group,
                                        "trade": next(iter(trades), role),
                                        "trades": ",".join((role,) + tuple(trades)),
                                        # a level per skill and per metaskill (E.initial_skill_levels),
                                        # and minutes of practice awaiting consolidation this period
                                        "skill_levels": founding_levels,
                                        "metaskill_levels": founding_metas,
                                        "skill_practice": {},
                                        # the meta-metaskill, metaskill talents, and limitations
                                        # (average and unlimited unless drawn: draw_capacities)
                                        "aptitude": float(defaults["aptitude"]),
                                        "aptitude_base": float(defaults["aptitude"]), "talents": {},
                                        "limitations": [],
                                        "role_identity": float(role_identity if role_identity is not None else 0.0),
                                        "work_fraction": float(stage["work_fraction"]),
                                        "care_need": float(stage["care"]), "food_need": float(stage["food"]),
                                        "health_work_fraction": float(healthy["work_fraction"]),
                                        "available_time": 1.0, "household": "",
                                        "busy": 0.0,
                                        "carried_weight": 0.0, "carry_ratio": 0.0,
                                        "carry_speed": 1.0, "carry_move_energy": 1.0,
                                        "carry_overloaded": 0.0, "carry_move_cooldown": 0.0,
                                        # Phase 024: sleep and collapse flags, and the exhaustion read-offs
                                        "asleep": 0.0, "collapsed": 0.0, "sleep_kind": 0.0,
                                        "slow_on": 1.0 if self.exhaustion_slow_on else 0.0,
                                        "exhaustion_step": 0.0, "speed_factor": 1.0,
                                        "last_carry_outcome": "", "last_accepted_item": -1.0,
                                        "last_dropped_kind": "", "last_dropped_node": -1.0,
                                        # one major action per actor turn;
                                        # communication and consent are free actions
                                        "turn": 0.0, "major_action_used": 0.0,
                                        "major_action_kind": "", "last_major_action": "",
                                        # residents get hungry, eat food, and starve without it
                                        "hunger": 0.0, "hunger_epoch": 0.0, "alive": 1.0,
                                        "starve_limit": float(self.E.CARE["starve_limit"]),
                                        "death_event": -1.0, "death_recorded": 0.0,
                                        # Phase 037: the exhaustion run (collapses without a full rest)
                                        "collapse_run": 0.0, "last_collapse_period": -1.0,
                                        "eat_armed": 0.0,
                                        "appr_epoch": 0.0,   # apprenticeship: skill grows under a master
                                        # reading/writing + general capability (class-graded; raised at school)
                                        "literacy": lit, "capability": cap, "learn": float(learn), "school_epoch": 0.0,

                                        # container-op state
                                        "fill_armed": 0.0, "fill_amount": 0.0, "fill_kind": "",
                                        "empty_armed": 0.0, "empty_amount": 0.0, "empty_kind": ""})
        self.eng.add_edge_unchecked(self._town, "has_actor", a)
        self._actors[name] = a
        self._alive_snapshot[name] = True
        body = self.eng.add_node("Body", {
            "mood": float(defaults["body"]["mood"]), "satiety": 0.0,
            "last_food": -1.0, "food_run": 0.0,
            "str_base": float(defaults["body"]["str_base"]), "sta_base": float(defaults["body"]["sta_base"]),
            "size": float(defaults["body"]["size"]),
            "str_train": 0.0,
            "sta_train": 0.0, "strength": 1.0, "stamina": 1.0,
            "stats_dirty": 0.0, "stamina_reserve": float(defaults["body"]["stamina_reserve"]),
            # Phase 034: alcohol in the body (0 sober to 1), on the Body node
            "intoxication": 0.0,
            # Phase 035: nutrition on the Body node (protein store, deficiency, last meal's pleasure and monotony)
            "protein_store": 0.0, "deficiency": 0.0, "meal_pleasure": 0.0, "monotony": 0.0,
            # Phase 036: alcohol aftereffects (plain values; all 0 and unread while alcohol_aftereffects is off).
            "tolerance": 0.0, "craving": 0.0, "dependent": 0.0, "hangover_ticks": 0.0, "episode_peak": 0.0})
        self.eng.add_edge_unchecked(a, "has_body", body)
        self._bodies[name] = body
        self._actor_minds[name] = (
            self._cognition_factory(name) if self._cognition_factory is not None
            else BigvilleOcelotActor(name, data_pack=self.data_pack))
        # Character identity, memories, personality, and held frame seeds are
        # resident-owned cognition inputs.  The physical world does not
        # interpret them; an external cognition provider may opt into the
        # generic seeding hook when it is available.  The optional method keeps
        # older/simple providers source-compatible.
        character_data = self._scenario_character_data.get(name, {})
        seed_character = getattr(self._actor_minds[name], "seed_character", None)
        if callable(seed_character) and character_data:
            seed_character(**character_data)
        self._actor_decisions[name] = {"action": "", "kind": "", "trade": "", "recipe": "", "target": ""}
        self._actor_targets[name] = {}
        # Food is held by residents, never implicitly by the town on their
        # behalf.  The inventory is an ordinary physical carrier so quantity
        # and capacity remain inspectable graph state.
        inventory_name = f"inventory:{name}"
        self.add_carrier(inventory_name, holds=(), max_load=float(defaults["inventory_max_load"]),
                         capacity=float(defaults["inventory_capacity"]))
        self.eng.add_edge_unchecked(a, "holds_inventory", self._containers[inventory_name][0])
        self._actor_inventories[name] = inventory_name
        self._actor_tableware[name] = {}
        self._actor_hands[name] = None
        self._refresh_carry_state(name)
        for trait, value in (traits or {}).items():
            if isinstance(value, (int, float)):
                self.eng.set_attr(a, trait, float(value))
        self._actor_cells[name] = a
        homes = self._map_layout.get("homes", []) if self._map_layout else []
        if home_cell is None and homes:
            home_cell = tuple(homes[self._next_home_index % len(homes)])
            self._next_home_index += 1
        if home_cell is not None and tuple(home_cell) in self._map_cells:
            home_cell = tuple(home_cell)
            self._attach_at_cell(a, home_cell)
            self.eng.add_edge_unchecked(a, "home_at", self._map_cells[home_cell])
            self._ensure_position_index()[name] = home_cell
        if work_cell is not None and tuple(work_cell) in self._map_cells:
            work_cell = tuple(work_cell)
            self.eng.add_edge_unchecked(a, "works_at", self._map_cells[work_cell])
            self.eng.set_attr(a, "work_x", float(work_cell[0]))
            self.eng.set_attr(a, "work_y", float(work_cell[1]))
        self._actor_references.setdefault(a, {})
        self._actor_policies.setdefault(a, set())
        self._actor_market_expectations.setdefault(name, {})
        for trade in self._market_expectation_specs:
            self._seed_market_expectation(name, trade)
        self._turn_actions.setdefault(name, [])
        return a

    # ---------------------------------------------------- recipe belief compatibility queries
    def knows(self, actor, recipe):
        return self.eng.has_edge(self._actors[actor], "knows", self._actions[recipe])

    def teach(self, teacher, learner, recipe):
        """Record an attempted explanation without deciding what the learner learned."""
        if (teacher not in self._actors or learner not in self._actors
                or recipe not in self._actions):
            return False
        self.create_event("recipe_explained", subject=teacher,
                          detail=f"{teacher} explained {recipe} to {learner}.",
                          observer=teacher, severity=0.05)
        return False

    # ---------------------------------------------------- unified social graph
    def _actor(self, name):
        if name not in self._actors:
            raise KeyError(f"unknown resident: {name}")
        return self._actors[name]

    def _node_name(self, node):
        return self.eng.node(node)["attrs"].get("name")

    def _note_node(self, note):
        if not isinstance(note, str):
            return note
        if note in self._notes:
            return self._notes[note]
        matches = [n for n in self._notes.values()
                   if self.eng.node(n)["attrs"].get("content") == note]
        if matches:
            return matches[-1]
        raise KeyError(f"unknown note: {note}")

    def _request_node(self, request):
        if not isinstance(request, str):
            return request
        if request in self._requests:
            return self._requests[request]
        raise KeyError(f"unknown request: {request}")

    def _conversation_key(self, a, b):
        return tuple(sorted((a, b)))

    def _conversation(self, a, b, *, create=True):
        key = self._conversation_key(a, b)
        conv = self._conversations.get(key)
        if conv is None and create:
            conv = self.eng.add_node("Conversation", {"name": f"conversation:{a}:{b}",
                                                        "status": "open", "turn": float(self._turn)})
            self.eng.add_edge_unchecked(conv, "between", self._actor(a))
            self.eng.add_edge_unchecked(conv, "between", self._actor(b))
            self._conversations[key] = conv
        return conv

    def set_relationship(self, a, b, *, kind="acquaintance", strength=1.0,
                         reliability=1.0, expected_ask=1.0, min_ask=1.0,
                         mutual=False):
        """Give a resident a held relationship model of another resident.

        This is deliberately not body state.  The bond is a graph object held
        by the source resident and can carry the source's expectations and
        willingness to help.  ``mutual`` creates a second, independently held
        model rather than making one relationship globally true.
        """
        bond = self.eng.add_node("Bond", {"kind": str(kind), "strength": float(strength),
                                          "reliability": float(reliability),
                                          "expected_ask": float(expected_ask),
                                          "min_ask": float(min_ask)})
        self.eng.add_edge_unchecked(self._actor(a), "holds_bond", bond)
        self.eng.add_edge_unchecked(bond, "toward", self._actor(b))
        self._relationships[(a, b)] = bond
        if mutual:
            self.set_relationship(b, a, kind=kind, strength=strength,
                                   reliability=reliability, expected_ask=expected_ask,
                                   min_ask=min_ask)
        return bond

    def relationship(self, a, b):
        return self._relationships.get((a, b))

    def write_note(self, author, content, *, title="", note_id=None):
        """Create a physical, held note.  Writing is a free action."""
        self._actor(author)
        key = note_id or f"note:{len(self._notes) + 1}"
        note = self.eng.add_node("Note", {"name": key, "content": str(content),
                                          "title": str(title), "author": author,
                                          "posted": 0.0, "post_armed": 0.0,
                                          "written_turn": float(self._turn)})
        self.eng.add_edge_unchecked(self._actor(author), "holds", note)
        self._notes[key] = note
        return note

    def give_note(self, sender, recipient, note):
        """Hand a note to another resident; hand-off is a free action."""
        n = self._note_node(note)
        self.eng.remove_edge_unchecked(self._actor(sender), "holds", n)
        self.eng.add_edge_unchecked(self._actor(recipient), "holds", n)
        self.eng.add_edge_unchecked(n, "given_by", self._actor(sender))
        self.eng.add_edge_unchecked(n, "given_to", self._actor(recipient))
        return n

    def post_note(self, poster, note):
        """Pin a held note at the mapped town square's noticeboard."""
        n = self._note_node(note)
        square_cells = list(self.eng.neighbours(self._square, "at_cell"))
        actor_cells = list(self.eng.neighbours(self._actor(poster), "at_cell"))
        if not square_cells or not actor_cells or actor_cells[0] != square_cells[0]:
            return False
        if not self.eng.has_edge(self._actor(poster), "holds", n):
            return False
        self.eng.remove_edge_unchecked(self._actor(poster), "holds", n)
        self.eng.add_edge_unchecked(n, "posted_on", self._noticeboard)
        self.eng.set_attr(n, "posted", 1.0)
        return True

    def read_note(self, reader, note):
        """Read a public or held note; learning its content is a free action."""
        n = self._note_node(note)
        public = self.eng.has_edge(n, "posted_on", self._noticeboard)
        held = self.eng.has_edge(self._actor(reader), "holds", n)
        if not (public or held):
            return False
        self.eng.add_edge_unchecked(self._actor(reader), "read", n)
        return self.eng.node(n)["attrs"].get("content", "")

    def note_contents(self, note):
        return self.eng.node(self._note_node(note))["attrs"].get("content", "")

    def board_contents(self):
        return sorted(self.note_contents(n)
                      for n in self.eng.in_neighbours(self._noticeboard, "posted_on"))

    def set_conversation_adapter(self, adapter):
        """Install a host-level speech compatibility adapter for game sessions."""
        self._conversation_adapter = adapter

    def speak(self, speaker, target=None, content="", *, loudness=1.0,
              conversation=None, message=None, raw_data=None,
              backend_owned=False, delivery_metadata=None):
        """Create a communication event without touching the major-action budget.

        ``content`` and ``raw_data`` are supplied by the cognition provider.
        The latter is opaque to the world: it is retained for accounting and
        made available to the recipient's cognition, but never rendered into
        replacement text or interpreted as a world action.  Legacy callers may
        still pass ``message``; the host adapter can support that older input
        shape without affecting backend-owned speech.
        """
        self._actor(speaker)
        if target is not None:
            self._actor(target)
            conversation = conversation or self._conversation(speaker, target)
        speech_meta = {}
        backend_speech = backend_owned or raw_data is not None
        if self._conversation_adapter is not None and not backend_speech:
            # Keep the four-argument legacy adapter contract intact.  Complete
            # backend-owned speech never enters this compatibility renderer.
            speech_meta = dict(self._conversation_adapter(
                speaker, target, content, message) or {})
            content = speech_meta.pop("content", content)
        conv = conversation
        radius = self.speech_radius(loudness)
        deliveries = self._speech_deliveries(speaker, target, radius)
        if self._aftereffects_on():
            # Phase 036: clarity is set by the speaker's intoxication, and each listener's copy by distance over the
            # radius. The text is never changed; only the clarity figures are added.
            speaker_pos = self.actor_position(speaker)
            for name, delivery in deliveries.items():
                pos = self.actor_position(name)
                dist = (max(abs(pos[0] - speaker_pos[0]), abs(pos[1] - speaker_pos[1]))
                        if pos is not None and speaker_pos is not None else 0.0)
                delivery["clarity"] = self.speech_clarity(speaker, distance=dist, radius=radius)
        attrs = {
            "content": str(content), "loudness": float(loudness), "eff_loudness": radius,
            "speaker": speaker, "target": target or "", "turn": float(self._turn),
            # Derived summary for reporting: whether any listener heard the content. The per-listener
            # record in `deliveries` is the source of truth.
            "heard": 1.0 if any(d["heard"] for d in deliveries.values()) else 0.0,
            "deliveries": deliveries,
        }
        if self._aftereffects_on():
            attrs["clarity"] = self.speech_clarity(speaker)
        if backend_speech:
            attrs["speech_origin"] = "backend"
            attrs["communication_mode"] = "free_text"
        if raw_data is not None:
            # Store the provider payload exactly as data.  No world rule reads
            # its internal keys; reports and cognition adapters may inspect it.
            attrs["raw_data"] = raw_data
        if delivery_metadata:
            attrs.update(dict(delivery_metadata))
        attrs.update(speech_meta)
        utterance = self.eng.add_node("Utterance", attrs)
        self.eng.add_edge_unchecked(self._actor(speaker), "spoke", utterance)
        if target is not None:
            self.eng.add_edge_unchecked(utterance, "to", self._actor(target))
            if conv is not None:
                self.eng.add_edge_unchecked(conv, "has_utterance", utterance)
        for name, delivery in deliveries.items():
            if delivery["heard"]:
                self.eng.add_edge_unchecked(self._actor(name), "heard", utterance)
        with _EVENT_LOG_LOCK:
            # LA03: keep the recipient -> utterance index in step with the log.
            # If the log changed outside ``speak`` (a restore or an older
            # checkpoint), rebuild it once from the canonical records.
            index = self._prepare_heard_utterance_index()
            self._utterances[len(self._utterances) + 1] = utterance
            for name, delivery in deliveries.items():
                if delivery["heard"]:
                    index.setdefault(str(name), []).append(utterance)
            self._heard_utterance_log_size = len(self._utterances)
        return utterance

    def speech_radius(self, loudness):
        """The Chebyshev distance, in cells, that a speech act carries (Phase 028, seeds/bigville_loud_comm.json).

        With the `loudness` subsystem on, the chosen loudness is clamped to the HEARING table's max_loudness and
        to zero from below (a not-a-number request is taken as normal loudness). With it off, the flat radius from
        the table applies whatever was chosen.
        """
        table = self.E.HEARING
        if not self.physical_subsystems.get("loudness", True):
            return float(table["flat_radius"])
        chosen = float(loudness)
        if math.isnan(chosen):
            chosen = float(table["normal_loudness"])
        return max(0.0, min(chosen, float(table["max_loudness"])))

    def speech_clarity(self, speaker, distance=0.0, radius=0.0):
        """Phase 036: how clear an utterance is, 0 to 1. The speaker's share of sobriety (1 - intoxication) is reduced
        by clarity_distance_loss at the edge of the hearing radius (distance over radius, capped at 1). With the
        switch off, speech is always fully clear (1.0). The world publishes this figure; it does not change the text."""
        if not self._aftereffects_on():
            return 1.0
        base = max(0.0, 1.0 - self.intoxication(speaker))
        fraction = min(1.0, float(distance) / float(radius)) if float(radius) > 0.0 else 0.0
        return round(max(0.0, base * (1.0 - float(self.E.INTOXICATION["clarity_distance_loss"]) * fraction)), 4)

    def _occluder_codes(self, terrain_names):
        from worlds.bigville_sim_world import TILE_NAME
        names = set(terrain_names)
        return {code for code, name in TILE_NAME.items() if name in names}

    def _line_blocked(self, a, b, codes):
        """True when a cell of `codes` lies on the grid line from a to b, endpoints excluded.

        With no map, or no occluder cells, there is no occlusion data and nothing is blocked: distance alone
        decides.
        """
        grid = self._map_grid
        if not grid or not codes or a is None or b is None:
            return False
        from worlds.bigville_sim_world import _line
        for x, y in _line(a[0], a[1], b[0], b[1])[1:-1]:
            if 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] in codes:
                return True
        return False

    def speech_occlusion_status(self):
        """What occlusion data the map holds for speech (Phase 028). A count of zero means distance alone."""
        grid = self._map_grid or []
        table = self.E.HEARING

        def cells(names):
            codes = self._occluder_codes(names)
            return sum(1 for row in grid for tile in row if tile in codes)

        return {"map_installed": bool(grid),
                "sight_occluder_cells": cells(table["sight_occluders"]),
                "hear_occluder_cells": cells(table["hear_occluders"])}

    def _speech_deliveries(self, speaker, target, radius):
        """Who hears and who witnesses one speech act (Phase 028), as plain per-listener records.

        A listener is any other living resident. Content reaches the target of a targeted utterance, or every
        listener for a broadcast, when the Chebyshev distance is at most `radius` and no hear occluder lies
        between them. A resident witnesses the act when the distance is at most the table's sight_range and no
        sight occluder lies between; a witness also sees the target when the target is in view. Only residents
        who heard or witnessed get an entry: {"heard": 0.0|1.0, "seen": 0.0|1.0, "target_seen": 0.0|1.0}.
        """
        speaker_pos = self.actor_position(speaker)
        if speaker_pos is None:
            return {}
        table = self.E.HEARING
        sight_range = int(table["sight_range"])
        sight_codes = self._occluder_codes(table["sight_occluders"])
        hear_codes = self._occluder_codes(table["hear_occluders"])
        target_pos = self.actor_position(target) if target is not None else None
        deliveries = {}
        for name in self._actors:
            if name == speaker or not self.is_alive(name):
                continue
            pos = self.actor_position(name)
            if pos is None:
                continue
            dist = max(abs(pos[0] - speaker_pos[0]), abs(pos[1] - speaker_pos[1]))
            heard = ((target is None or name == target) and dist <= radius
                     and not self._line_blocked(speaker_pos, pos, hear_codes))
            seen = dist <= _dn.sight_range(self, name, sight_range) and not self._line_blocked(
                speaker_pos, pos, sight_codes)   # Phase 042: shorter sight in the dark
            if not (heard or seen):
                continue
            entry = {"heard": 1.0 if heard else 0.0, "seen": 1.0 if seen else 0.0}
            if seen and target_pos is not None and name != target:
                target_dist = max(abs(target_pos[0] - pos[0]), abs(target_pos[1] - pos[1]))
                entry["target_seen"] = 1.0 if (
                    target_dist <= sight_range
                    and not self._line_blocked(pos, target_pos, sight_codes)) else 0.0
            deliveries[str(name)] = entry
        return deliveries

    def _rebuild_heard_utterance_index(self):
        """Rebuild actor -> heard utterance nodes from the canonical log (LA03)."""
        index = {}
        for node in self._utterances.values():
            attrs = self.eng.node(node)["attrs"]
            for name, delivery in (attrs.get("deliveries") or {}).items():
                if float(delivery.get("heard", 0.0)):
                    index.setdefault(str(name), []).append(node)
        self._heard_utterance_index = index
        self._heard_utterance_log_size = len(self._utterances)
        return index

    def _prepare_heard_utterance_index(self):
        """Return a recipient index consistent with the current utterance log."""
        index = self.__dict__.get("_heard_utterance_index")
        size = self.__dict__.get("_heard_utterance_log_size")
        if not isinstance(index, dict) or size != len(self._utterances):
            return self._rebuild_heard_utterance_index()
        return index

    def heard_utterances(self, actor, *, limit=20):
        """Return recent speech delivered to ``actor`` as cognition input.

        This is deliberately a projection of communication records, not a
        semantic interpretation by the world.  A backend receives the exact
        text and opaque provider payload that were delivered to it.

        LA03 indexes deliveries by recipient in ``speak``; the old full-log
        scan remains the fallback when the index is absent or out of date.
        """
        self._actor(actor)
        try:
            index = self._prepare_heard_utterance_index()
            nodes = index.get(str(actor), ())
        except Exception:
            nodes = self._utterances.values()
        records = []
        for node in nodes:
            if not self.eng.has_node(node):
                continue
            attrs = self.eng.node(node)["attrs"]
            target = str(attrs.get("target", ""))
            mine = (attrs.get("deliveries") or {}).get(str(actor), {})
            if not float(mine.get("heard", 0.0)) or (target not in {"", str(actor)}):
                continue
            records.append({
                "speaker": attrs.get("speaker", ""),
                "target": attrs.get("target", ""),
                "text": attrs.get("content", ""),
                "raw_data": attrs.get("raw_data"),
                "raw_understanding": attrs.get("raw_understanding"),
                "turn": attrs.get("turn", 0.0),
                "loudness": attrs.get("loudness", 1.0),
            })
            if "clarity" in mine:         # Phase 036: only with alcohol_aftereffects on
                records[-1]["clarity"] = mine["clarity"]
        return records[-int(limit):]

    def utter(self, speaker, content, *, target=None, loudness=1.0):
        return self.speak(speaker, target, content, loudness=loudness)

    def reply(self, speaker, target, content, **kwargs):
        return self.speak(speaker, target, content, **kwargs)

    def conversation_between(self, a, b):
        conv = self._conversation(a, b, create=False)
        if conv is None:
            return []
        return list(self.eng.neighbours(conv, "has_utterance"))

    def request_status(self, request):
        """Read a request already conceptualized from an utterance.

        Request nodes are downstream interpretation state.  They are not
        minted by a Bigville ``ask`` action; a resident's conversation seed
        is responsible for interpreting a received utterance and any host
        bridge may then register that interpretation here.
        """
        return int(round(float(self.eng.node(self._request_node(request))["attrs"].get("status", 0.0))))

    def _respond_request(self, actor, request, status):
        req = self._request_node(request)
        if not self.eng.has_edge(req, "to", self._actor(actor)):
            return False
        if self.request_status(req) != 0:
            return False
        self.eng.set_attr(req, "status", float(status))
        self.eng.set_attr(req, "response_turn", float(self._turn))
        self.eng.add_edge_unchecked(self._actor(actor), "accepted_request" if status == 1 else "declined_request", req)
        return True

    def accept_request(self, actor, request):
        """Consent to a request; acceptance is a free action."""
        return self._respond_request(actor, request, 1)

    def decline_request(self, actor, request):
        """Refuse a request; refusal is also a free action."""
        return self._respond_request(actor, request, -1)

    def complete_request(self, actor, request, *, result=""):
        """Carry out an accepted request as the actor's one major action."""
        req = self._request_node(request)
        if self.request_status(req) != 1 or not self.eng.has_edge(req, "to", self._actor(actor)):
            return self._refuse("wrong_target")
        if not self._claim_major_action(actor, "complete_request"):
            return self._refuse("slot_used")
        self.eng.set_attr(req, "status", 2.0)
        self.eng.set_attr(req, "result", str(result))
        self.eng.add_edge_unchecked(self._actor(actor), "completed_request", req)
        return True

    def requests_for(self, actor):
        return list(self.eng.neighbours(self._actor(actor), "received_request"))

    # ---------------------------------------------------- health, life history, and ecology
    # Phase 037: one health variable (the actor's health_value, 0 to 1). Every route down goes through harm()
    # (or the daily age decline), every route up through _heal(), and death is health at or below 0, recorded
    # with the cause tag. The routes, their figures and the fragility by life stage are the HEALTH table.
    def health(self, actor):
        """The one health variable (health_value): 1 is fully healthy, 0 is dead."""
        return float(self.eng.node(self._actor(actor))["attrs"].get("health_value", self.E.HEALTH["max_health"]))

    def harm(self, actor, amount, cause, *, fragility=True):
        """Acute harm: lower the resident's health by `amount` times their life stage's fragility (HEALTH), and
        tag the cause. Health at or below 0 is death by `cause` (record_death). Returns False when the resident
        is dead. `cause` must be one of HEALTH.causes. Phase 043: `fragility=False` applies `amount` as given,
        for the illness course, whose infant penalty is its own (MEDICAL_CARE.infant_fragility)."""
        if str(cause) not in self.E.HEALTH["causes"]:
            raise ValueError(f"harm: unknown cause {cause!r}; HEALTH.causes are {list(self.E.HEALTH['causes'])}")
        stage = str(self.eng.node(self._actor(actor))["attrs"].get("life_stage", "adult"))
        mult = float(self.E.HEALTH["fragility"].get(stage, 1.0)) if fragility else 1.0
        return self._drop_health(actor, float(amount) * mult, cause)

    def _drop_health(self, actor, drop, cause):
        if not self.is_alive(actor):
            return False
        node = self._actor(actor)
        health = max(0.0, self.health(actor) - max(0.0, float(drop)))
        self.eng.set_attr(node, "health_value", health)
        self.eng.set_attr(node, "last_cause", str(cause))
        if health <= 0.0:
            self.record_death(actor, cause=str(cause))
        return True

    def _heal(self, actor, gain):
        """Recovery by care, rest or treatment: health rises by `gain`, capped at HEALTH.max_health."""
        if not self.is_alive(actor):
            return
        cap = float(self.E.HEALTH["max_health"])
        self.eng.set_attr(self._actor(actor), "health_value", min(cap, self.health(actor) + max(0.0, float(gain))))

    def _stable_draw(self, *parts):
        """A stateless draw in [0, 1) keyed on the world seed and `parts` (as _burial_roll; nothing is stored)."""
        return random.Random(":".join([str(self._burial_seed), *(str(p) for p in parts)])).random()

    def _exhaustion_collapse(self, actor):
        """Phase 037's exhaustion route. A collapse extends the run of collapses while the previous collapse was
        within exhaustion_window_periods days; a full rest ends the run (see _resolve_sleep). The first collapse
        in a run is free. Each later one in the run is acute harm, exhaustion_harm, from cause `exhaustion`."""
        h = self.E.HEALTH
        node = self._actor(actor)
        attrs = self.eng.node(node)["attrs"]
        now = self._town_period()
        last = float(attrs.get("last_collapse_period", -1.0))
        in_window = last >= 0.0 and now - last <= float(h["exhaustion_window_periods"])
        run = (float(attrs.get("collapse_run", 0.0)) if in_window else 0.0) + 1.0
        self.eng.set_attr(node, "collapse_run", run)
        self.eng.set_attr(node, "last_collapse_period", now)
        if run > float(h["exhaustion_free_collapses"]):
            self.harm(actor, float(h["exhaustion_harm"]), "exhaustion")

    def injure(self, actor, *, severity=None, cause="accident"):
        """A blow or fall (cause text is for the event). The injury is the health drop from `severity`, tagged
        `injury`, and it can kill."""
        if severity is None:
            severity = self.E.CARE["injury_severity"]
        node = self._actors[actor]
        self.eng.set_attr(node, "health", "injured")
        self.eng.set_attr(node, "injury", float(severity))
        self.harm(actor, float(severity), "injury")
        event = self.create_event("injury", subject=actor, detail=f"{actor} was injured ({cause}).", severity=severity)
        self.eng.add_edge_unchecked(node, "has_illness", event)
        return event

    def diagnose(self, doctor, patient, condition="fever"):
        self.eng.set_attr(self._actors[patient], "disease", condition)
        self.eng.set_attr(self._actors[patient], "health", condition)
        illness = self.eng.add_node("Illness", {"patient": patient, "condition": condition,
                                                 "started_day": float(self.calendar()["day"]), "active": 1.0})
        self.eng.add_edge_unchecked(self._town, "has_illness", illness)
        self._illnesses[f"illness:{len(self._illnesses) + 1}"] = illness
        return illness

    def treat(self, doctor, patient, *, medicine=0.0):
        if medicine and not self._store_open(doctor):
            self._refuse("store_locked")
            return False
        if medicine and self.qty("medicine") < medicine:
            return False
        if medicine:
            self.set_stock("medicine", self.qty("medicine") - float(medicine))
        node = self._actors[patient]
        self.eng.set_attr(node, "health", "healthy")
        self.eng.set_attr(node, "disease", "")
        self.eng.set_attr(node, "injury", 0.0)
        self._heal(patient, float(self.E.CARE["treat_health_gain"]))
        self.eng.add_edge_unchecked(self._actors[doctor], "treated", node)
        return True

    def care_for(self, caregiver, patient):
        """Perform one co-located care action for an injured or ill resident."""
        if caregiver not in self._actors or patient not in self._actors:
            return self._refuse("unknown_target")
        if self._turn > 0 and self.actor_position(caregiver) != self.actor_position(patient):
            return self._refuse("not_in_reach")
        # Phase 049: care for someone who is not in need is allowed. It costs the caregiver's time, and does nothing
        # to a healthy, fed patient beyond the ordinary care's small effects.
        attrs = self.eng.node(self._actors[patient])["attrs"]
        # Medicine comes from the town store; a caregiver with no access gives ordinary care instead.
        medicine = (1.0 if self._store_open(caregiver) and self.qty("medicine") >= 1.0 and attrs.get("disease")
                    else 0.0)
        if medicine:
            return self.treat(caregiver, patient, medicine=medicine)
        care = self.E.CARE
        self.eng.set_attr(self._actors[patient], "injury",
                          max(0.0, float(attrs.get("injury", 0.0)) - float(care["care_injury_relief"])))
        self._heal(patient, float(care["care_health_gain"]))
        if float(self.eng.node(self._actors[patient])["attrs"].get("injury", 0.0)) <= 0.0:
            self.eng.set_attr(self._actors[patient], "health", "healthy")
        self.eng.add_edge_unchecked(self._actors[caregiver], "cared_for", self._actors[patient])
        return True

    # ---------------------------------------------------- illness, screening and treatment (Phase 043)
    # Off by default (physical_subsystems.illness). On, each dawn may start an illness (DISEASE) by a stateless
    # seeded draw, and a diagnosed illness costs health each day by the table's drop, less what screening,
    # treatment and care remove. The doctor's and midwife's acts (checkup, treat, well_baby) are the care action
    # with a care_kind; each sets a flag on the body for a table-set number of days (MEDICAL_CARE).
    def _illness_on(self):
        return bool(self.physical_subsystems.get("illness"))

    def _care_flag_value(self, actor, flag):
        """A Phase 043 care flag on the resident's body (screened, treated, well_baby): 1 or 0."""
        return int(float(self.eng.node(self._bodies[actor])["attrs"].get(flag, 0.0)) == 1.0)

    def _set_care_flag(self, actor, flag, value, days=None):
        """Set a care flag; with `days`, it lapses at the calendar day that many days on."""
        node = self._bodies[actor]
        self.eng.set_attr(node, flag, 1.0 if value else 0.0)
        if days is not None:
            self.eng.set_attr(node, f"{flag}_until", float(self.calendar()["day"]) + float(days))

    def _lapse_care_flags(self, actor):
        today = float(self.calendar()["day"])
        attrs = self.eng.node(self._bodies[actor])["attrs"]
        for flag in ("screened", "treated", "well_baby"):
            if self._care_flag_value(actor, flag) and today >= float(attrs.get(f"{flag}_until", 0.0)):
                self._set_care_flag(actor, flag, False)

    def _illness_onset(self, name, stage):
        """Phase 043: a resident who is not ill may catch an illness this dawn. The draw is stateless and seeded
        (_stable_draw, keyed on the world seed, the resident, the disease and the day), so the world's own state
        is not touched. The onset uses diagnose(), as the burial condition does. Returns the disease or None."""
        season = str(self.season())
        day = int(float(self.calendar()["day"]))
        for disease, spec in self.E.DISEASE.items():
            chance = float(spec["onset_per_day"][season]) * float(spec["stage_risk"].get(stage, 1.0))
            if chance > 0.0 and self._stable_draw("illness", name, disease, day) < chance:
                self.diagnose(None, name, disease)
                self.eng.set_attr(self._bodies[name], "illness_days", 0.0)
                return disease
        return None

    def _illness_day(self, name, disease, stage):
        """Phase 043: one day of an illness course. The cost is the disease's severity, plus progression while the
        resident is unscreened, less treat_relief while treated, plus MEDICAL_CARE.infant_fragility for an infant
        no well-baby visit has seen (added, not multiplied). harm() is given the cost as it is (fragility=False).
        A treated resident regains treated_heal a day, an untreated one natural_care. After course_days the
        illness clears and the resident is healthy again."""
        spec = self.E.DISEASE[disease]
        care = self.E.MEDICAL_CARE
        treated = self._care_flag_value(name, "treated")
        cost = float(spec["severity"]) + (0.0 if self._care_flag_value(name, "screened") else float(spec["progression"]))
        if treated:
            cost -= float(spec["treat_relief"])
        if stage == "infant" and not self._care_flag_value(name, "well_baby"):
            cost += float(care["infant_fragility"])
        self.harm(name, max(0.0, cost), "illness", fragility=False)
        if not self.is_alive(name):
            return
        self._heal(name, float(care["treated_heal"] if treated else care["natural_care"]))
        node = self._bodies[name]
        days = float(self.eng.node(node)["attrs"].get("illness_days", 0.0)) + 1.0
        self.eng.set_attr(node, "illness_days", days)
        if days >= float(spec["course_days"]):
            self.eng.set_attr(self._actors[name], "disease", "")
            self.eng.set_attr(self._actors[name], "health", "healthy")
            self.eng.set_attr(node, "illness_days", 0.0)

    def _holds_care_skill(self, actor, act):
        """A doctor or midwife holds the act's skill when any of MEDICAL_CARE.skills[act] is above level 0."""
        return any(self.skill_level(actor, skill) > 0.0 for skill in self.E.MEDICAL_CARE["skills"][act])

    def _care_act_refusal(self, doctor, patient, act):
        """The checks every Phase 043 act shares. Returns the refusal code, or None when the act may happen."""
        if doctor not in self._actors or patient not in self._actors:
            return "unknown_target"
        if not self._illness_on():
            return "unsupported"
        if not self.is_alive(doctor) or not self.is_alive(patient):
            return "not_possible"
        if not self._holds_care_skill(doctor, act):
            return "unskilled"
        if self._turn > 0 and self.actor_position(doctor) != self.actor_position(patient):
            return "not_in_reach"
        return None

    def checkup(self, doctor, patient):
        """A preventive visit by a resident with the medical skill, co-located with the patient. The patient is
        screened for MEDICAL_CARE.screen_days: an illness they catch progresses less while it lasts."""
        code = self._care_act_refusal(doctor, patient, "checkup")
        if code is not None:
            return self._refuse(code)
        self._set_care_flag(patient, "screened", True, self.E.MEDICAL_CARE["screen_days"])
        self.eng.add_edge_unchecked(self._actors[doctor], "examined", self._actors[patient])
        return True

    def treat_patient(self, doctor, patient):
        """Treatment by a resident with the medical skill, co-located with an ill patient. It consumes
        MEDICAL_CARE.medicine_per_treatment from the town store (the store guard applies, as for care_for) and
        sets the patient treated for MEDICAL_CARE.treated_days. A patient with no illness is refused."""
        code = self._care_act_refusal(doctor, patient, "treat")
        cost = float(self.E.MEDICAL_CARE["medicine_per_treatment"])
        if code is None and not self.eng.node(self._actors[patient])["attrs"].get("disease"):
            code = "not_needed"
        if code is None and not self._store_open(doctor):
            code = "store_locked"
        if code is None and self.qty("medicine") < cost:
            code = "out_of_stock"
        if code is not None:
            return self._refuse(code)
        self.set_stock("medicine", self.qty("medicine") - cost)
        self._set_care_flag(patient, "treated", True, self.E.MEDICAL_CARE["treated_days"])
        self.eng.add_edge_unchecked(self._actors[doctor], "treated_patient", self._actors[patient])
        return True

    def well_baby_visit(self, doctor, infant):
        """A well-baby visit by a resident with the medical skill or midwifery, co-located with an infant. The
        infant is seen for MEDICAL_CARE.well_baby_days: it pays no infant_fragility while the visit holds."""
        code = self._care_act_refusal(doctor, infant, "well_baby")
        if code is None and self.eng.node(self._actors[infant])["attrs"].get("life_stage") != "infant":
            code = "not_needed"
        if code is None and self._care_flag_value(infant, "well_baby"):
            code = "not_needed"
        if code is not None:
            return self._refuse(code)
        self._set_care_flag(infant, "well_baby", True, self.E.MEDICAL_CARE["well_baby_days"])
        self.eng.add_edge_unchecked(self._actors[doctor], "examined", self._actors[infant])
        return True

    def birth(self, mother, child_name, *, father=None, home_cell=None):
        """Register a physical birth and add the newborn as a resident entity."""
        self._actor(mother)
        if child_name in self._actors:
            return False
        mother_attrs = self.eng.node(self._actors[mother])["attrs"]
        cell = home_cell or self.actor_position(mother)
        child = self.add_actor(child_name, role="child", skill=0.0,
                               station="labouring", literacy=0.0, capability=0.0,
                               home_cell=cell, life_stage="infant", age=0.0,
                               klass=mother_attrs.get("klass", ""),
                               group=mother_attrs.get("group", ""), learn=1.0)
        household = mother_attrs.get("household", "")
        if household in self._households:
            self.assign_household(child_name, household)
        record = {"child": child_name, "mother": mother, "father": father or "",
                  "day": self.calendar()["day"]}
        self._births.append(record)
        self.eng.add_edge_unchecked(self._actors[mother], "gave_birth", child)
        if father in self._actors:
            self.eng.add_edge_unchecked(self._actors[father], "parent_of", child)
        return child

    def _death_cause(self, attrs):
        cause = attrs.get("death_cause") or attrs.get("last_cause")
        if cause:
            return str(cause)
        if float(attrs.get("hunger", 0.0)) >= float(attrs.get("starve_limit", self.E.CARE["starve_limit"])):
            return "starvation"
        return "unknown"

    def _record_death_event(self, actor, *, cause="unknown"):
        """Record a death as a world event without distributing knowledge."""
        node = self._actors[actor]
        attrs = self.eng.node(node)["attrs"]
        if float(attrs.get("death_recorded", 0.0)) == 1.0:
            return attrs.get("death_event", -1.0)
        event = self.create_event("death", subject=actor,
                                  detail=f"{actor} died ({cause}).", public=False)
        self.eng.set_attr(node, "death_cause", str(cause))
        self.eng.set_attr(node, "death_event", float(event.value))
        self.eng.set_attr(node, "death_recorded", 1.0)
        self._deaths.append({"actor": actor, "day": self.calendar()["day"],
                             "cause": str(cause), "event": str(event)})
        self._create_corpse(actor)
        self._record_kin_death(actor)
        self._alive_snapshot[actor] = False
        return event

    def _record_unlogged_deaths(self):
        """Bridge physical death transitions into explicit world events."""
        for actor, node in self._actors.items():
            attrs = self.eng.node(node)["attrs"]
            alive = float(attrs.get("alive", 1.0)) == 1.0
            if self._alive_snapshot.get(actor, alive) and not alive:
                self._record_death_event(actor, cause=self._death_cause(attrs))
            self._alive_snapshot[actor] = alive

    def record_death(self, actor, *, cause="unknown"):
        node = self._actors[actor]
        if float(self.eng.node(node)["attrs"].get("alive", 1.0)) != 1.0:
            return False
        self.eng.set_attr(node, "alive", 0.0)
        self.eng.set_attr(node, "health", "dead")
        self._record_death_event(actor, cause=cause)
        return True

    # ---------------------------------------------------- bodies, graves, and burial (Phase 010)
    def _create_corpse(self, actor):
        """A dead resident leaves a body on the cell where they died: a ToolItem of kind 'corpse', weighing
        BURIAL.body_weight. Carrying it is the ordinary pick_up/drop_item handling; who moves or buries it
        is the resident's choice, not the world's. A pack with no BURIAL entries leaves no body."""
        burial = self.E.BURIAL
        if not burial or actor in self._corpses:
            return None
        attrs = self.eng.node(self._actors[actor])["attrs"]
        item = self.eng.add_node("ToolItem", {"kind": "corpse", "weight": float(burial["body_weight"]),
                                              "quality": 1.0, "condition": 1.0, "broken": 0.0, "wear": 0.0,
                                              "decay": 0.0, "use_armed": 0.0, "repair_armed": 0.0,
                                              "resident": str(actor),
                                              "household": str(attrs.get("household") or ""),
                                              "died_period": self._town_period(), "buried": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_tool_item", item)
        cell = self.actor_position(actor)
        if cell in self._map_cells:
            self._attach_at_cell(item, cell)
        self._corpses[actor] = item
        return item

    def corpse_of(self, actor):
        """The body node of a dead resident, or None (no body, or the resident is alive)."""
        return self._corpses.get(actor)

    def corpse_cell(self, actor):
        """Where a resident's unburied body is: the cell it lies on, or the cell of the one carrying it."""
        item = self._corpses.get(actor)
        if item is None or float(self.eng.node(item)["attrs"].get("buried", 0.0)) == 1.0:
            return None
        return self._item_cell(item)

    def _corpse_holder(self, item):
        for actor, node in self._actors.items():
            for edge in ("holds_in_hand", "holds_tableware", "holds"):
                if self.eng.has_edge(node, edge, item):
                    return actor
        return None

    def _item_cell(self, item):
        holder = self._corpse_holder(item)
        if holder is not None:
            return self.actor_position(holder)
        cells = list(self.eng.neighbours(item, "at_cell"))
        return self.map_position_node(cells[0]) if cells else None

    def _graveyard(self):
        return self.building(self.E.BURIAL["place"]) if self.E.BURIAL else None

    def _open_graves(self):
        """Dug graves not yet filled, on the graveyard building (a count; dig_grave adds one, bury fills one)."""
        place = self._graveyard()
        if place is None:
            return 0
        return int(round(float(self.eng.node(place)["attrs"].get("open_graves", 0.0))))

    def _in_graveyard(self, cell):
        site = self._building_sites.get(self.E.BURIAL["place"]) if self.E.BURIAL else None
        if cell is None or site is None:
            return False
        x, y, w, h = site
        return x <= cell[0] < x + w and y <= cell[1] < y + h

    def _corpse_for_burial(self):
        """The unburied body on the graveyard ground (or carried there), earliest death first, or None."""
        found = []
        for actor, item in self._corpses.items():
            a = self.eng.node(item)["attrs"]
            if float(a.get("buried", 0.0)) != 1.0 and self._in_graveyard(self._item_cell(item)):
                found.append((float(a.get("died_period", 0.0)), actor, item))
        return min(found)[2] if found else None

    def _burial_ready(self, recipe_name):
        """Whether a burial recipe's physical state holds now: digging needs nothing here (its tool and
        place are checked by _capable and _at_recipe_building); burying needs an open grave and a body in the
        graveyard. A recipe that is not a burial is always ready."""
        kind = self._recipe_specs.get(recipe_name, {}).get("burial")
        if kind == "bury":
            return self._open_graves() >= 1 and self._corpse_for_burial() is not None
        return True

    def _at_recipe_building(self, actor, recipe_name):
        """A recipe with at_building is done inside that building's footprint."""
        kind = self._recipe_specs.get(recipe_name, {}).get("at_building")
        if not kind:
            return True
        place = self.building(kind)
        return place is not None and self._inside_building(actor, place)

    def _detach_body(self, item):
        """Take a body off the ground and out of any hand: it is no longer a physical object on the map."""
        if self.eng.has_edge(self._town, "has_tool_item", item):
            self.eng.remove_edge_unchecked(self._town, "has_tool_item", item)
        self._remove_item_location(item)
        for actor, node in self._actors.items():
            for edge in ("holds_in_hand", "holds_tableware", "holds"):
                if self.eng.has_edge(node, edge, item):
                    self.eng.remove_edge_unchecked(node, edge, item)
                    if self._actor_hands.get(actor) == item:
                        self._actor_hands[actor] = None
                    self._refresh_carry_state(actor)

    def _enact_burial(self, actor, kind):
        """The physical effect of a finished burial job: dig adds an open grave, bury fills one with the body
        on the graveyard ground. The body keeps its node, marked buried, so the record survives."""
        place = self._graveyard()
        if place is None:
            return
        if kind == "dig":
            self.eng.set_attr(place, "open_graves", float(self._open_graves() + 1))
            return
        if kind == "bury":
            item = self._corpse_for_burial()
            if item is None:
                return
            a = self.eng.node(item)["attrs"]
            self._detach_body(item)
            self.eng.set_attr(item, "buried", 1.0)
            self.eng.set_attr(item, "buried_period", self._town_period())
            self.eng.set_attr(place, "open_graves", float(self._open_graves() - 1))
            name = str(a.get("resident", ""))
            self.create_event("burial", subject=name, public=True,
                              detail=f"{name} was buried in the graveyard.")

    def _burial_roll(self, name):
        """A stateless draw in [0, 1) for one resident on one day (no RNG state is kept on the world)."""
        day = int(self.calendar()["day"])
        return random.Random(f"{self._burial_seed}:burial:{name}:{day}").random()

    def burial_risk(self, household):
        """The chance per dawn that each living member of `household` catches the burial condition. It is
        zero before BURIAL.risk_after_periods have passed since a household member's unburied death, and
        zero again once that body is buried. The disease itself uses the ordinary disease mechanism."""
        if not household or not self.E.BURIAL:
            return 0.0
        now = self._town_period()
        for item in self._corpses.values():
            a = self.eng.node(item)["attrs"]
            if (a.get("household") == household and float(a.get("buried", 0.0)) != 1.0
                    and now - float(a.get("died_period", 0.0)) >= float(self.E.BURIAL["risk_after_periods"])):
                return float(self.E.BURIAL["onset_chance"])
        return 0.0

    def _daily_life_tick(self):
        """Advance age and mild recovery at dawn; severe outcomes remain explicit actions."""
        if not self.physical_subsystems["metabolism"]:
            return
        for name, node in self._actors.items():
            a = self.eng.node(node)["attrs"]
            if float(a.get("alive", 1.0)) != 1.0:
                continue
            age = float(a.get("age", self.E.ACTOR_DEFAULTS["age"])) + 1.0 / float(self.E.TIME["days_per_year"])
            self.eng.set_attr(node, "age", age)
            # Phase 037: chronic decline by life stage (HEALTH.age_rate, per year, spread over the days).
            rate = float(self.E.HEALTH["age_rate"].get(str(a.get("life_stage", "adult")), 0.0))
            if rate > 0.0:
                self._drop_health(name, rate / float(self.E.TIME["days_per_year"]), "age")
                if not self.is_alive(name):
                    continue
            injury = float(a.get("injury", 0.0))
            care = self.E.CARE
            if injury > 0.0:
                self.eng.set_attr(node, "injury", max(0.0, injury - float(care["daily_injury_recovery"])))
                self._heal(name, float(care["daily_health_recovery"]))
                if injury <= float(care["recovered_injury_below"]):
                    self.eng.set_attr(node, "health", "healthy")
            if float(a.get("hunger", 0.0)) >= float(care["malnourished_hunger"]):
                self.eng.set_attr(node, "health", "malnourished")
            self._lapse_care_flags(name)
            if self._illness_on() and str(a.get("disease") or "") in self.E.DISEASE:
                # Phase 043: a table-driven course (DISEASE) replaces the flat daily loss below.
                self._illness_day(name, str(a["disease"]), str(a.get("life_stage", "adult")))
                if not self.is_alive(name):
                    continue
            elif a.get("disease"):
                # A disease is an ongoing illness route: its daily loss is acute harm tagged illness.
                self.harm(name, float(care["disease_health_loss"]), "illness")
                if not self.is_alive(name):
                    continue
            # An unburied body in the household is a health risk: an onset is an ordinary diagnose() of
            # the burial condition (BURIAL.condition), which the disease rule above then runs.
            chance = self.burial_risk(a.get("household"))
            if chance > 0.0 and not a.get("disease") and self._burial_roll(name) < chance:
                self.diagnose(None, name, str(self.E.BURIAL["condition"]))
            # Phase 043: illness onset, when the switch is on. The attribute is read fresh, since the burial
            # diagnosis above may have just set it.
            if self._illness_on() and not self.eng.node(node)["attrs"].get("disease"):
                self._illness_onset(name, str(a.get("life_stage", "adult")))
            age_stage = next((stage for stage, spec in self.E.LIFE_STAGES.items()
                              if float(spec["age_min"]) <= age <= float(spec["age_max"])), "elder")
            if age_stage != a.get("life_stage"):
                self.eng.set_attr(node, "life_stage", age_stage)

    def add_waste(self, kind="kitchen_scraps", amount=1.0):
        cycle = self.E.WASTE_CYCLES[kind]
        source = cycle["output"] if cycle["output"] in self._stock else "compost"
        if source in self._stock:
            self.set_stock(source, self.qty(source) + float(amount))
        return source

    def process_waste(self, operator, kind="kitchen_scraps", amount=1.0):
        if not self._store_open(operator):
            self._refuse("store_locked")
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(operator, "process_waste"):
            return False
        return self.add_waste(kind, amount)

    def school_lesson(self, teacher, pupil, *, subject="literacy"):
        """Record a bounded lesson delivery; understanding is backend-owned.

        The legacy world API cannot return a learner's cognitive decision, so
        this records only the physical lesson and leaves literacy/capability
        untouched. Interactive sessions should deliver lesson content through
        speech and let the pupil backend decide whether to retain it.
        """
        pa = self.eng.node(self._actors[pupil])["attrs"]
        teacher_pos = self.actor_position(teacher)
        pupil_pos = self.actor_position(pupil)
        distance = self.distance(teacher_pos, pupil_pos) if teacher_pos is not None and pupil_pos is not None else None
        if (float(pa.get("alive", 1.0)) != 1.0
                or teacher_pos is None or pupil_pos is None
                or (teacher_pos != pupil_pos and (distance is None or distance > 1))):
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(teacher, "teach"):
            return False
        self.create_event("lesson_delivered", subject=teacher,
                          detail=f"{teacher} delivered a {subject} lesson to {pupil}.",
                          observer=teacher, severity=0.05)
        return True

    def write_journal(self, author, text=""):
        """Store a resident's authored note about their held state."""
        a = self.eng.node(self._actors[author])["attrs"]
        if not text:
            text = (f"Day {int(self.calendar()['day'])}: I am {a.get('health', 'healthy')}; "
                    f"my hunger is {float(a.get('hunger', 0.0)):.1f}.")
        journal = self.eng.add_node("JournalEntry", {"author": author, "day": float(self.calendar()["day"]),
                                                      "text": str(text)})
        self.eng.add_edge_unchecked(self._actors[author], "wrote_journal", journal)
        self._journals.setdefault(author, []).append(journal)
        return journal

    def _serving_equipment(self, actor, kind):
        """Return a legal held vessel/utensil pair, if one is observed."""
        service = self.E.food_service(kind)
        if service is None:
            return None
        vessels = [k for k in self._actor_tableware.get(actor, {})
                   if self._has_tableware(actor, k) and self._item_specs.get(k, {}).get("container")]
        utensils = [k for k in self._actor_tableware.get(actor, {})
                    if self._has_tableware(actor, k) and self._item_specs.get(k, {}).get("utensil")]
        for vessel in vessels:
            for utensil in utensils:
                if self.E.can_serve(kind, vessel, utensil):
                    return vessel, utensil
        return None

    def _actor_options(self, actor):
        """Publish legal affordances for one resident; this method chooses none."""
        attrs = self.eng.node(self._actors[actor])["attrs"]
        targets = {}

        def target_key(value):
            key = f"target:{len(targets)}"
            targets[key] = value
            return key

        route_cache = {}

        def reachable_destination(destination):
            """Admissibility gate for travel options published to the mind."""
            current = self.actor_position(actor)
            if current is None or not isinstance(destination, tuple) or destination not in self._map_cells:
                return False
            key = (current, destination)
            if key not in route_cache:
                route_cache[key] = self.distance(current, destination) is not None
            return route_cache[key]

        if float(attrs.get("alive", 1.0)) != 1.0:
            self._actor_targets[actor] = targets
            return [{"action": "rest", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0}]
        # Phase 024: a sleeping or collapsed resident has no legal major action until they wake.
        if self._sleep_code(actor) is not None:
            self._actor_targets[actor] = targets
            return []
        # A timed job continues mechanically, but urgent sustenance remains an
        # available actor affordance: a worker may eat or buy food between
        # work pulses.  Recipe-start options are suppressed below while busy.
        busy = self.busy(actor)
        options = []
        for kind, spec in self._item_specs.items():
            if spec.get("food") and self.inventory_qty(actor, kind) >= 1.0:
                if spec.get("prepared") and self._serving_equipment(actor, kind) is None:
                    continue
                options.append({"action": "eat", "kind": kind, "trade": "", "recipe": "", "target": "",
                                "meal_value": self.meal_value(actor, kind),
                                "monotony": round(self._satiety_level(actor, kind), 4),
                                "meal_pleasure": round(self.E.taste(kind), 4), "score": 0.0})
        # Publishing a sale is an economic decision, not a physical affordance.
        # The resident's cognition can observe nearby people and choose whether
        # to propose a physical transfer; the world must not turn a seeded
        # sell_willing/sell_price pair into a buyer plan.
        #
        # Transfer affordances below describe only a co-located, capacity-safe
        # movement of stock already carried by this actor.  They carry no
        # willingness, price, purchase, or seller-acceptance semantics.
        # The carried stock is invariant while publishing choices for each
        # possible recipient, so inspect the actor's inventory once here.
        carried_kinds = [kind for kind in self._item_specs
                         if self.inventory_qty(actor, kind) >= 1.0]
        for recipient, recipient_node in self._actors.items():
            if recipient == actor or not self.is_alive(recipient):
                continue
            recipient_position = self.actor_position(recipient)
            if recipient_position is None:
                continue
            recipient_kinds = [kind for kind in carried_kinds
                               if self._inventory_can_receive(recipient, kind)]
            if not recipient_kinds:
                continue
            if recipient_position != self.actor_position(actor):
                # Route choices are published only when the actor already
                # carries something this particular resident can physically
                # receive. Cognition still chooses whether and whom to visit;
                # this does not create a transfer or assign the carried good.
                if reachable_destination(recipient_position):
                    key = target_key(recipient_position)
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "target": key, "destination": recipient_position,
                                    "recipient": recipient, "score": 0.0})
                continue
            for kind in recipient_kinds:
                key = target_key(recipient)
                options.append({"action": "transfer", "kind": kind,
                                "trade": "", "recipe": "", "target": key,
                                "recipient": recipient,
                                "score": 0.0})

        # A household store exposes its physical fetch/travel affordance
        # independently of hunger. Whether the resident wants food (and
        # whether to eat it now) belongs to cognition, which already observes
        # hunger. Stock, reachability, and receiving capacity remain physical
        # gates here; cognition decides whether carried food makes another
        # fetch redundant.
        for container, (container_node, _) in self._containers.items():
            if self.eng.node(container_node)["attrs"].get("kind") == "carrier":
                continue
            kind = next((kind for kind, spec in self._item_specs.items()
                         if spec.get("food") and self.contents(container, kind) >= 1.0), None)
            if kind is None:
                continue
            destination = self.container_position(container)
            if destination is None:
                continue
            if self.actor_position(actor) == destination and self._inventory_can_receive(actor, kind):
                key = target_key(container)
                options.append({"action": "fetch", "kind": kind, "trade": "", "recipe": "",
                                "physical_source": "container", "source_container": container,
                                "target": key, "score": 0.0})
            elif reachable_destination(destination):
                key = target_key(destination)
                options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                "physical_source": "container", "source_container": container,
                                "fetch_kind": kind,
                                "target": key, "score": 0.0})
            break
        # Shop stocks and prices remain available to explicit compatibility
        # helpers, but the normal cognition path does not turn them into
        # purchases or steer residents to buy goods.  A resident can travel to
        # physical workplaces through the ordinary map affordance below.

        # Town stock is a physical source for any carried item, including
        # recipe ingredients.  Publish only the handling and travel choices:
        # task relevance belongs to the actor's cognition, and stock remains
        # in the store until a selected fetch succeeds.
        market_cell = self.map_position_node(self._store)
        if market_cell is not None and self._store_open(actor):
            market_move_added = False
            for kind in self._item_specs:
                if self.qty(kind) < 1.0 or not self._inventory_can_receive(actor, kind):
                    continue
                if any(option.get("action") == "fetch" and option.get("kind") == kind
                       for option in options):
                    continue
                is_food = self._relieves_hunger(kind)
                if self.actor_position(actor) == market_cell:
                    key = target_key(("store", kind))
                    options.append({"action": "fetch", "kind": kind, "trade": "", "recipe": "",
                                    "stock_source": "town", "food": is_food,
                                    "target": key, "score": 0.0})
                elif reachable_destination(market_cell) and not market_move_added:
                    key = target_key(market_cell)
                    has_edible = any(
                        self._relieves_hunger(k) and self.qty(k) >= 1.0
                        and self._inventory_can_receive(actor, k)
                        for k, spec in self._item_specs.items()
                    )
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "food": has_edible,
                                    "target": key, "destination": market_cell, "score": 0.0})
                    market_move_added = True

        # A tradesperson who has made or is collecting a good must physically
        # fetch it from the mapped store before carrying it to other people.
        market_cell = self.map_position_node(self._store)
        if market_cell is not None and self._store_open(actor):
            for trade, shop_node in self._shops.items():
                output = self.eng.node(shop_node)["attrs"].get("output_kind", "")
                if output not in self._item_specs or self.qty(output) < 1.0:
                    continue
                is_food = self._relieves_hunger(output)
                # Output collection is a physical carrying opportunity. Trade
                # identity can influence cognition, but does not grant access.
                if (self.actor_position(actor) == market_cell
                        and self._inventory_can_receive(actor, output)):
                    key = target_key(("store", output))
                    options.append({"action": "fetch", "kind": output, "trade": trade, "recipe": "",
                                    "food": is_food, "target": key, "score": 0.0})
                elif reachable_destination(market_cell):
                    key = target_key(market_cell)
                    options.append({"action": "move", "kind": "", "trade": trade, "recipe": "",
                                    "food": is_food, "target": key, "score": 0.0})
        # Physical household storage is an ordinary carrying choice.  A
        # resident may put any held food into any accessible container; the
        # container's storage class only changes decay, never permission.
        held_kinds = [kind for kind, spec in self._item_specs.items()
                      if spec.get("food") and self.inventory_qty(actor, kind) >= 1.0]
        storage = [name for name, (node, _) in self._containers.items()
                   if self.eng.node(node)["attrs"].get("kind") != "carrier"]
        if held_kinds and storage:
            for container in storage:
                destination = self.container_position(container)
                kind = held_kinds[0]
                if destination is None:
                    continue
                if self.actor_position(actor) == destination and self._can_put(actor, container, kind):
                    key = target_key(container)
                    options.append({"action": "put", "kind": kind, "trade": "", "recipe": "",
                                    "target": key, "score": 0.0})
                elif (self._container_can_receive(container, kind)
                      and reachable_destination(destination)):
                    key = target_key(destination)
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "target": key, "score": 0.0})
                break
        # Phase 030: lock and unlock are published only where they are physically possible: a key this resident
        # holds that fits the lock, with the resident at the lock's cell (or the lock has no cell). An unlock is
        # not offered again to a keyholder who has already turned a key in a lock that needs several.
        for name in ["store"] + list(self._containers):
            node, place = self._lockable(name)
            lock_attrs = self.eng.node(node)["attrs"]
            if float(lock_attrs.get("lock_id", 0.0)) <= 0.0 or not self._holds_key(actor, float(lock_attrs["lock_id"])):
                continue
            cell = self.map_position_node(place)
            if cell is not None and self.actor_position(actor) != cell:
                continue
            locked = float(lock_attrs.get("locked", 0.0)) == 1.0
            if locked and self._actor(actor) in self.eng.neighbours(node, "authorised_by"):
                continue
            options.append({"action": "unlock" if locked else "lock", "kind": "", "trade": "", "recipe": "",
                            "target": target_key(name), "score": 0.0})
        # Work coordinates describe an authored goal rather than a physical
        # property of the destination. Do not publish them as a special route.
        if self._actors:
            for animal, animal_node in self._animals.items():
                aa = self.eng.node(animal_node)["attrs"]
                species = aa.get("species")
                task = next((name for name, spec in self.E.ANIMAL_HUSBANDRY.items()
                             if spec["species"] == species), "")
                if not task or not self.animal_alive(animal):
                    continue
                period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
                cooldown = float(self.E.ANIMAL_HUSBANDRY[task]["cooldown"])
                if period - float(aa.get(f"{task}_epoch", -cooldown)) < cooldown:
                    continue
                animal_cell = self.map_position_node(animal_node)
                if animal_cell is not None:
                    if self.actor_position(actor) != animal_cell and not reachable_destination(animal_cell):
                        continue
                    key = target_key(animal if self.actor_position(actor) == animal_cell else animal_cell)
                    options.append({"action": "tend_animals" if self.actor_position(actor) == animal_cell else "move",
                                    "kind": task, "trade": "", "recipe": "",
                                    "target": key, "animal": animal, "score": 0.0})
            for crop in self._living_crops():
                crop_attrs = self.eng.node(crop)["attrs"]
                if (float(crop_attrs.get("thirst", 0.0)) > 0.0
                        and self.qty("water") >= float(crop_attrs.get("water", 0.0))):
                    destination = self.map_position_node(crop)
                    if destination is not None and reachable_destination(destination):
                        key = target_key(crop if self.actor_position(actor) == destination else destination)
                        options.append({"action": "water" if self.actor_position(actor) == destination else "move",
                                        "kind": "", "trade": "", "recipe": "",
                                        "target": key, "crop_node": int(crop), "score": 0.0})
            for crop in self._living_crops():
                if self.crop_mature(crop):
                    destination = self.map_position_node(crop)
                    if destination is not None and reachable_destination(destination):
                        key = target_key(crop if self.actor_position(actor) == destination else destination)
                        options.append({"action": "harvest" if self.actor_position(actor) == destination else "move",
                                        "kind": "", "trade": "", "recipe": "",
                                        "target": key, "crop_node": int(crop), "score": 0.0})
            # A mapped parcel can contain many beds.  The parcel's occupancy
            # is not a one-crop gate; each sowing is its own physical Crop
            # affordance on that parcel.
            farm_plots = sorted(name for name in self._land if name.startswith("farm_plot_"))
            for land_name in farm_plots:
                crop_name = self._rotation_crop(land_name)
                if crop_name is not None:
                    destination = self.map_position_node(self._land[land_name])
                    if destination is not None and reachable_destination(destination):
                        key = target_key((crop_name, land_name) if self.actor_position(actor) == destination
                                         else destination)
                        options.append({"action": "sow" if self.actor_position(actor) == destination else "move",
                                        "kind": "", "trade": "", "recipe": "",
                                        "target": key, "sow_kind": crop_name,
                                        "land": land_name, "score": 0.0})
            # Fertilise the most depleted plot below the threshold, if there is fertiliser to spread.
            fertiliser = self.E.NITROGEN["fertiliser_type"]
            hungry_plots = [name for name in farm_plots
                            if self.land_nitrogen_fraction(name) < float(self.E.NITROGEN["fertilise_below"])]
            if hungry_plots and self.type_available(fertiliser) >= 1.0:
                land_name = min(hungry_plots, key=lambda name: (self.land_nitrogen_fraction(name), name))
                destination = self.map_position_node(self._land[land_name])
                if destination is not None and reachable_destination(destination):
                    here = self.actor_position(actor) == destination
                    key = target_key(land_name if here else destination)
                    options.append({"action": "fertilise" if here else "move",
                                    "kind": "", "trade": "", "recipe": "",
                                    "target": key, "fertilise_land": land_name,
                                    "land": land_name, "score": 0.0})

        # Construction projects are physical places and require a resident
        # builder to travel there before spending materials and labour.
        if self._building_projects or self._infrastructure:
            for project, project_node in self._building_projects.items():
                data = self.eng.node(project_node)["attrs"]
                if data.get("status") == "complete":
                    continue
                spec = self.E.BUILDING_PROJECTS[data["project"]]
                remaining = max(0.0, float(data["labour"]) - float(data["progress"]))
                scale = (min(1.0, remaining) / float(data["labour"])) if data.get("labour") else 0.0
                if any(self.qty(kind) + 1e-9 < float(qty) * scale
                       for kind, qty in spec.get("inputs", {}).items()):
                    continue
                cells = list(self.eng.neighbours(project_node, "at_cell"))
                destination = self.map_position_node(cells[0]) if cells else None
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(project if self.actor_position(actor) == destination else destination)
                options.append({"action": "build" if self.actor_position(actor) == destination else "move",
                                "kind": "", "trade": "", "recipe": project,
                                "target": key, "project": project, "score": 0.0})
            for name, infra_node in self._infrastructure.items():
                if self.infrastructure_condition(name) >= 0.8:
                    continue
                infra_spec = self.E.INFRASTRUCTURE[self.eng.node(infra_node)["attrs"]["kind"]]
                if any(self.qty(kind) < 1.0 for kind in infra_spec.get("maintenance", ())):
                    continue
                destination = self.map_position_node(infra_node)
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(name if self.actor_position(actor) == destination else destination)
                options.append({"action": "maintain" if self.actor_position(actor) == destination else "move",
                                "kind": "", "trade": "", "recipe": "",
                                "target": key, "name": name, "score": 0.0})

        if self._actors:
            for patient, patient_node in self._actors.items():
                if patient == actor or not self.is_alive(patient):
                    continue
                pa = self.eng.node(patient_node)["attrs"]
                # Mirror care_for's physical precondition: it accepts an
                # ill/injured resident, or one whose hunger has reached the
                # threshold that makes the aid action applicable.
                needs_care = (pa.get("health") != "healthy"
                              or float(pa.get("injury", 0.0)) > 0.0
                              or float(pa.get("hunger", 0.0)) >= float(self.E.CARE["care_hunger_need"]))
                if not needs_care:
                    continue
                destination = self.actor_position(patient)
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(patient if self.actor_position(actor) == destination else destination)
                options.append({"action": "care" if self.actor_position(actor) == destination else "move",
                                "kind": "", "trade": "", "recipe": "",
                                "target": key, "patient": patient, "score": 0.0})
                break
        # Phase 043: the medical acts. Each is a care option with a care_kind, offered only to a resident with the
        # skill, standing with the patient, and only when the act has something to do (an unscreened patient,
        # an ill patient with medicine in the store, an infant with no visit). Off, none is offered.
        if self._illness_on() and self._actors:
            for patient, patient_node in self._actors.items():
                if patient == actor or not self.is_alive(patient):
                    continue
                if self.actor_position(actor) is None or self.actor_position(patient) != self.actor_position(actor):
                    continue
                pa = self.eng.node(patient_node)["attrs"]
                kinds = []
                if self._holds_care_skill(actor, "checkup") and not self._care_flag_value(patient, "screened"):
                    kinds.append("checkup")
                if (self._holds_care_skill(actor, "treat") and pa.get("disease") and self._store_open(actor)
                        and self.qty("medicine") >= float(self.E.MEDICAL_CARE["medicine_per_treatment"])):
                    kinds.append("treat")
                if (str(pa.get("life_stage", "")) == "infant" and not self._care_flag_value(patient, "well_baby")
                        and self._holds_care_skill(actor, "well_baby")):
                    kinds.append("well_baby")
                for kind in kinds:
                    options.append({"action": "care", "kind": "", "trade": "", "recipe": "",
                                    "target": target_key(patient), "patient": patient,
                                    "care_kind": kind, "score": 0.0})
        # Ordinary object movement is a physical option, not a purchase,
        # permission check, or interpretation of ownership.  Keep these
        # choices in the same backend affordance boundary as other actions;
        # the cognition policy decides whether to use them.
        options.extend(option for option in self.physical_object_affordances(actor)
                       if option.get("action") == "move_object")
        # A gathering site is reached by a move option, as a farm plot is. A resident who could gather there
        # (capable, with inputs and tools, and the site holding a batch) but stands elsewhere is offered the
        # walk. On the site, the work option from the loop below is offered instead.
        if not busy:
            for kind, site in self._gathering_sites.items():
                if self.actor_position(actor) == site["cell"] or not reachable_destination(site["cell"]):
                    continue
                if any(self._capable(actor, name) and self._site_has_batch(kind, name)
                       and self._recipe_inputs_available(name, actor)
                       for name, spec in self._recipe_specs.items() if spec.get("gathered_from") == kind):
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "target": target_key(site["cell"]), "score": 0.0})
        for recipe in self.E.RECIPES:
            if (not busy and self._can_attempt(actor, recipe["name"])
                    and self._recipe_inputs_available(recipe["name"], actor)):
                out_kind = recipe.get("out", [""])[0]
                options.append({"action": "work", "kind": out_kind, "trade": "", "target": "",
                                "recipe": recipe["name"],
                                "score": 0.0})
                options[-1].update(self._open_work_read_offs(actor, recipe))
        # Rest is afforded only when the same reserve threshold that gates
        # physical recovery says it can apply. A resident with a full reserve
        # idles by proposing no major action; do not publish a rest choice that
        # enactment will reject as a no-op.
        if self.stamina_reserve(actor) < 0.8:
            options.append({"action": "rest", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        # Phase 024: sleep is offered below the rested level. The world publishes the two facts the seed's
        # sleep decision reads (`lateness` into the night, and `safe`); the backend chooses.
        if self.stamina_reserve(actor) < float(self.E.EXHAUSTION["rest_cap"]) - 1e-12:
            facts = self.sleep_facts(actor)
            options.append({"action": "sleep", "kind": "", "trade": "", "recipe": "", "target": "",
                            "lateness": facts["lateness"], "safe": facts["safe"], "score": 0.0})
        # Phase 023: a paused timed job is resumed by walking back to its start cell. The return is a legal
        # move; every option is marked while the job waits, so the backend can see the paused state.
        if self.job_paused(actor):
            start = self.job_start_cell(actor)
            if start is not None and reachable_destination(start):
                options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                "target": target_key(start), "resumes_job": True, "score": 0.0})
            for option in options:
                option["job_paused"] = True
        # Phase 033: a held resident may struggle free, and a holder may let go. While either holds, no travel is
        # offered (the walk is refused, Phase 033), so the published options stay legal.
        if self.holder_of(actor) is not None:
            options.append({"action": "struggle", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        if self.holding_of(actor) is not None:
            options.append({"action": "release", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        if self.holder_of(actor) is not None or self.holding_of(actor) is not None:
            options = [option for option in options if option.get("action") != "move"]
        band = self._exhaustion_band(actor)
        if band["below_e_low"]:
            # Phase 024: a resident too exhausted to walk (reserve below e_low) is offered no travel. Phase 049: the walk
            # itself is allowed at the slowest rate, so the offer stays withheld to keep the simple backend's choices.
            options = [option for option in options if option.get("action") != "move"]
        # Target keys are intentionally opaque and may be rebuilt on every
        # observation.  Expose the physical destination alongside a movement
        # affordance so a cognition backend can safely retain a route across
        # turns without retaining the world's temporary target map.
        for option in options:
            if option.get("action") == "move":
                option["speed_factor"] = float(band["speed"]) * self.stagger_speed(actor)
                option["exhaustion_step"] = float(band["step"])
                destination = targets.get(option.get("target"))
                if isinstance(destination, tuple):
                    option["destination"] = destination
                    movement = self.terrain_state(destination)
                    step = self._movement_step(self.actor_position(actor), destination)
                    step_movement = self.terrain_state(step) if step is not None else movement
                    option.update({
                        "terrain": movement["terrain"],
                        "terrain_speed": float(movement["speed"]),
                        "terrain_move_time": float(movement["move_time"]),
                        "terrain_stamina_multiplier": float(movement["stamina_multiplier"]),
                        "route_terrain": step_movement["terrain"],
                        "path_preferred": (movement["terrain"] == "path"
                                           or step_movement["terrain"] == "path"),
                    })
        options.extend(self.joint_options(actor))
        self._actor_targets[actor] = targets
        return options

    def joint_options(self, actor):
        """The joint options a resident can see (Phase 047): a load on the ground that one person cannot lift, and a
        crewed job at the resident's cell. Nothing is published with the joint_actions switch off."""
        if not self.joint_actions_on() or not self._joint_ready(actor):
            return []
        return self._carry_options(actor) + self._crew_options(actor)

    def _decide_actor(self, actor):
        """Ask the resident's Ocelot instance to choose from current affordances."""
        mind = self._actor_minds[actor]
        # Publish the body read-off the resident's own valuation needs. Terrain
        # cost is published per option; how much that cost BITES depends on how
        # depleted this particular body is, which is a world fact the mind
        # cannot observe for itself. Mechanical translation, no decision.
        publish_body = getattr(mind, "publish_body_state", None)
        if callable(publish_body):
            publish_body(self.stamina_reserve(actor))
        else:
            mind.s.set_attr(mind.agent, "stamina_reserve", self.stamina_reserve(actor))
        mind.replace_options(self._actor_options(actor))
        choice = mind.decide()
        self._actor_decisions[actor] = dict(choice)
        return choice

    def resident_plan(self, actor):
        """Return the resident graph's current decision, for inspection."""
        choice = self._decide_actor(actor)
        if choice["action"] == "rest" and not self.is_alive(actor):
            choice["action"] = "none"
            choice["reason"] = "dead"
        else:
            choice["reason"] = "ocelot_decision"
        return choice

    def _known_recipe_names(self, actor):
        """Recipe names this world believes ``actor`` can attempt (LA03).

        Every recipe is commonly known unless its data says otherwise; an
        uncommon recipe is included when the actor holds a ``knows`` edge to
        its ActionSpec. This reads knowledge, not full per-recipe validation:
        ingredients, tools and location are proposal-time checks.
        """
        node = self._actors[actor]
        known = {name for name, action in self._actions.items()
                 if self.eng.has_edge(node, "knows", action)}
        return sorted(name for name, spec in self._recipe_specs.items()
                      if name in known or bool(spec.get("common", True)))

    @staticmethod
    def _observe_shared_bucket_count(actor_attrs, other_attrs):
        count = 0
        for key in ("role", "klass", "group"):
            a, b = actor_attrs.get(key), other_attrs.get(key)
            if a and b and a == b:
                count += 1
        return count

    def _observe_relationship(self, actor, other):
        """Mechanical relationship read-off for an observation (nothing decided)."""
        relationship = self.relationship(actor, other)
        if relationship is None:
            return {"tie_strength": 0.0, "band_code": 0.0}
        attrs = self.eng.node(relationship)["attrs"]
        strength = float(attrs.get("strength", 0.0))
        tie_strength = max(0.0, strength)
        resentment = max(0.0, -strength) if attrs.get("kind") == "feud" else 0.0
        return {"tie_strength": tie_strength,
                "band_code": BigvilleBondWorld._band_code(
                    {"tie_strength": tie_strength, "affect_resentment": resentment})}

    def _observe_nearby_actors(self, actor, position):
        if position is None:
            return []
        actor_attrs = self.eng.node(self._actors[actor])["attrs"]
        nearby = []
        for name in self.actors_near(position, 8, exclude=actor):
            other_position = self.actor_position(name)
            other_attrs = self.eng.node(self._actors[name])["attrs"]
            nearby.append({
                "id": name, "name": name,
                "role": other_attrs.get("role", ""),
                "klass": other_attrs.get("klass", ""),
                "group": other_attrs.get("group", ""),
                "position": other_position,
                "distance": self.distance(position, other_position),
                "health": other_attrs.get("health", "healthy"),
                "injury": round(float(other_attrs.get("injury", 0.0)), 4),
                "shared_bucket_count": self._observe_shared_bucket_count(
                    actor_attrs, other_attrs),
                **self._observe_relationship(actor, name),
            })
        nearby.sort(key=lambda resident: (resident["distance"], resident["id"]))
        return nearby

    def _observe_job(self, actor):
        job = self._job_of(actor)
        if job is None:
            return None
        attrs = self.eng.node(job)["attrs"]
        runs = self.eng.neighbours(job, "runs")
        recipe = (self.eng.node(runs[0])["attrs"].get("name", "") if runs else "")
        start = attrs.get("start_cell")
        return {"recipe": str(recipe),
                "remaining": round(float(attrs.get("remaining", 0.0)), 4),
                "start_cell": tuple(start) if isinstance(start, (list, tuple)) else None,
                "paused": bool(self.job_paused(actor))}

    def _observe_cell(self, position):
        terrain = self.terrain_state(position)
        if not isinstance(position, tuple) or position not in self._map_cells:
            return {"position": None, "terrain": terrain, "buildings": [],
                    "land": [], "gathering_sites": [], "fixtures": [],
                    "exits": [], "occupancy": 0, "animals": [], "crops": [],
                    "building_projects": [], "infrastructure": [], "shops": []}
        buildings = []
        for key, site in sorted(self._building_sites.items()):
            x, y, width, height = site
            if x <= position[0] < x + width and y <= position[1] < y + height:
                attrs = self.eng.node(self._places[key])["attrs"]
                buildings.append({"id": key, "name": attrs.get("name", key),
                                  "kind": attrs.get("kind", "")})
        land = []
        for name, node in sorted(self._land_cells.items()):
            if self.map_position_node(node) == position:
                attrs = self.eng.node(node)["attrs"]
                entry = {"id": name, "use": attrs.get("use", ""),
                         "soil": attrs.get("soil", "")}
                # LA04: the pack's sowable crop for this parcel when it names
                # one.  This is pack data, not a per-recipe admissibility check.
                if attrs.get("use") == "arable":
                    crop = self._rotation_crop(name)
                    if crop is not None:
                        entry["sow_kind"] = crop
                land.append(entry)
        gathering_sites = []
        for kind, site in sorted(self._gathering_sites.items()):
            if tuple(site["cell"]) == position:
                attrs = self.eng.node(site["node"])["attrs"]
                gathering_sites.append({
                    "kind": kind,
                    "cell": tuple(site["cell"]),
                    "stock": round(float(attrs.get("stock", 0.0)), 4),
                    "capacity": round(float(attrs.get("capacity", 0.0)), 4),
                })
        fixtures = []
        for name, node in sorted(self._square_fixtures.items()):
            attrs = self.eng.node(node)["attrs"]
            if (int(attrs.get("x", -1)), int(attrs.get("y", -1))) == position:
                fixtures.append({"id": name, "name": name,
                                 "kind": attrs.get("kind", "fixture"),
                                 "goods": list(attrs.get("goods", ()))})
        animals = []
        for name, node in sorted(self._animals.items()):
            if self.map_position_node(node) != position:
                continue
            attrs = self.eng.node(node)["attrs"]
            species = str(attrs.get("species", ""))
            task = next((task for task, spec in self.E.ANIMAL_HUSBANDRY.items()
                         if spec["species"] == species), "")
            animals.append({"id": name, "name": attrs.get("name", name),
                            "species": species,
                            "alive": float(attrs.get("alive", 0.0)) == 1.0,
                            "task": task})
        crops = []
        for crop in sorted(self._living_crops(), key=lambda node: int(node.value)):
            if self.map_position_node(crop) != position:
                continue
            attrs = self.eng.node(crop)["attrs"]
            age = float(attrs.get("age", 0.0))
            grow_periods = float(attrs.get("grow_periods", 0.0))
            crops.append({"id": int(crop.value),
                          "kind": str(attrs.get("crop", "")),
                          "stage": "mature" if age >= grow_periods else "growing",
                          "mature": age >= grow_periods,
                          "age": round(age, 4),
                          "grow_periods": round(grow_periods, 4),
                          "thirst": round(float(attrs.get("thirst", 0.0)), 4)})
        projects = []
        for project_id, node in sorted(self._building_projects.items()):
            if self.map_position_node(node) != position:
                continue
            attrs = self.eng.node(node)["attrs"]
            spec = self.E.BUILDING_PROJECTS.get(attrs.get("project", ""), {})
            projects.append({"id": project_id,
                             "name": attrs.get("name", project_id),
                             "project": attrs.get("project", ""),
                             "status": attrs.get("status", ""),
                             "progress": round(float(attrs.get("progress", 0.0)), 4),
                             "labour": round(float(attrs.get("labour", 0.0)), 4),
                             "inputs": dict(spec.get("inputs", {}))})
        infrastructure = []
        for name, node in sorted(self._infrastructure.items()):
            if self.map_position_node(node) != position:
                continue
            attrs = self.eng.node(node)["attrs"]
            spec = self.E.INFRASTRUCTURE.get(attrs.get("kind", ""), {})
            infrastructure.append({
                "id": name, "kind": attrs.get("kind", ""),
                "condition": round(float(attrs.get("condition", 0.0)), 4),
                "maintenance": list(spec.get("maintenance", ()))})
        shops = []
        for trade, node in sorted(self._shops.items()):
            if self.map_position_node(node) != position:
                continue
            attrs = self.eng.node(node)["attrs"]
            shops.append({"trade": trade,
                          "input_kind": attrs.get("input_kind", ""),
                          "output_kind": attrs.get("output_kind", "")})
        exits = sorted(
            (position[0] + dx, position[1] + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if (position[0] + dx, position[1] + dy) in self._map_cells)
        return {"position": position, "terrain": terrain,
                "buildings": buildings, "land": land,
                "gathering_sites": gathering_sites, "fixtures": fixtures,
                "exits": exits,
                "occupancy": len(self.actors_near(position, 0, alive_only=False)),
                "animals": animals, "crops": crops,
                "building_projects": projects, "infrastructure": infrastructure,
                "shops": shops}

    def _observe_place_cell(self, actor, attrs, prefix):
        """A stable cell named by ``home_x``/``home_y`` or ``work_x``/``work_y``, else the edge (LA04)."""
        x_key, y_key = f"{prefix}_x", f"{prefix}_y"
        if x_key in attrs and y_key in attrs:
            cell = (int(round(float(attrs[x_key]))), int(round(float(attrs[y_key]))))
            if cell in self._map_cells:
                return cell
        edge = "home_at" if prefix == "home" else "works_at"
        for node in self.eng.neighbours(self._actors[actor], edge):
            cell = self.map_position_node(node)
            if cell in self._map_cells:
                return cell
        return None

    def _observe_places(self, actor, attrs):
        """Named destinations a local candidate generator may propose (LA04).

        Every value is a stable map cell, or a short sorted list of records
        with stable ids and cells.  Unknown places are omitted.
        """
        home = self._observe_place_cell(actor, attrs, "home")
        work = self._observe_place_cell(actor, attrs, "work")
        market = None
        if self._map_layout:
            value = self._map_layout.get("work", {}).get("market")
            if isinstance(value, (list, tuple)) and len(value) == 2:
                candidate = (int(value[0]), int(value[1]))
                if candidate in self._map_cells:
                    market = candidate
        buildings = []
        for key in sorted(self._building_sites):
            cell = self.building_position(key)
            if cell is None or cell not in self._map_cells:
                continue
            node = self._places.get(key)
            place = self.eng.node(node)["attrs"] if node is not None else {}
            buildings.append({"id": key, "name": place.get("name", key),
                              "kind": place.get("kind", ""), "cell": cell})
            if len(buildings) >= 24:
                break
        gathering_sites = []
        for kind, site in sorted(self._gathering_sites.items()):
            cell = tuple(site["cell"])
            if cell not in self._map_cells:
                continue
            gathering_sites.append({"kind": kind, "cell": cell})
            if len(gathering_sites) >= 8:
                break
        farms = []
        for name, node in sorted(self._land_cells.items()):
            cell = self.map_position_node(node)
            if cell not in self._map_cells:
                continue
            attrs = self.eng.node(node)["attrs"]
            farms.append({"id": name, "cell": cell, "use": attrs.get("use", "")})
            if len(farms) >= 24:
                break
        return {"home": home, "work": work, "market": market,
                "buildings": buildings, "gathering_sites": gathering_sites,
                "farms": farms}

    def _observe_inventory_details(self, actor):
        """Carried kinds with the capability facts a local generator needs (LA04).

        This reads item specs, quantities and the already-defined meal value;
        it runs no recipe, tool or site validation.
        """
        details = []
        for kind, qty in sorted(self.inventory(actor).items()):
            spec = self._item_specs.get(kind, {})
            edible = bool(spec.get("food"))
            details.append({
                "kind": kind,
                "qty": round(float(qty), 4),
                "edible": edible,
                "meal_value": self.meal_value(actor, kind) if edible else 0.0,
                "prepared": bool(spec.get("prepared")),
                "tool": bool(spec.get("class") == "tool"),
            })
        return details

    # LA07: a bounded, deterministic work prefilter.  It is a publish cap, not a
    # rule: the menu publishes every recipe that passes the same physical gate.
    _OBSERVE_WORK_LIMIT = 16

    def _observe_work_candidates(self, actor, cell=None):
        """Recipes this actor could start right now, bounded and sorted (LA07).

        The list is the lazy backend's work prefilter: it applies the same
        cheap site/tool/ingredient conditions the menu's work loop publishes,
        via ``recipe_preview``.  A busy resident gets an empty list because the
        menu suppresses new work while a job is open.  This does not enumerate
        items x destinations and never touches ``_actor_options``.

        Scanning all ~160 recipes with the full preview would cost about as
        much as the menu's own work loop, so one safe over-approximation runs
        first: a recipe is skipped only when a bulk input's total available
        quantity (own inventory, reachable containers, open town store) is
        already below the need.  Item/type inputs are left to the full preview.
        """
        if self.busy(actor):
            return []
        if cell is None:
            cell = self._observe_cell(self.actor_position(actor))
        local_buildings = set()
        for building in cell.get("buildings") or []:
            for key in ("id", "kind"):
                value = building.get(key)
                if value:
                    local_buildings.add(str(value))
        names = set(self._known_recipe_names(actor))
        job = self._job_of(actor)
        if job is not None:
            runs = self.eng.neighbours(job, "runs")
            if runs:
                name = str(self.eng.node(runs[0])["attrs"].get("name", ""))
                if name:
                    names.add(name)
        bulk_available = self._observe_bulk_available(actor)
        candidates = []
        for name in sorted(names):
            spec = self._recipe_specs.get(name)
            if spec is None:
                continue
            at_building = spec.get("at_building")
            if at_building and str(at_building) not in local_buildings:
                continue
            if not self._recipe_maybe_available(spec, bulk_available):
                continue
            if not self.recipe_preview(actor, name)["ok"]:
                continue
            outputs = spec.get("out") or []
            out_kind = str(outputs[0]) if outputs and outputs[0] else ""
            minutes = 0.0
            action = self._actions.get(name)
            if action is not None:
                minutes = float(self.eng.node(action)["attrs"].get("time_minutes", 0.0))
            candidates.append({"recipe": name, "out": out_kind,
                               "time_minutes": round(minutes, 4)})
            if len(candidates) >= self._OBSERVE_WORK_LIMIT:
                break
        return candidates

    def _observe_bulk_available(self, actor):
        """Bulk units the actor can draw on now, keyed by kind (LA07).

        This is the same source order ``_plan_input`` draws from, without the
        per-recipe claim bookkeeping.  It is a read-only prefilter only.
        """
        kinds = set()
        for spec in self._recipe_specs.values():
            for kind, qty in spec.get("in", []):
                need = self._input_need(kind, qty)
                if need[2] or need[3]:
                    continue
                kinds.add(kind)
        return {kind: self._bulk_available(actor, kind) for kind in kinds}

    @staticmethod
    def _recipe_maybe_available(spec, bulk_available):
        """False only when a bulk input cannot possibly be met (safe prefilter)."""
        for kind, qty in spec.get("in", []):
            if kind in bulk_available and bulk_available[kind] + 1e-9 < float(qty):
                return False
        return True

    def observe(self, actor):
        """Publish a cheap, JSON-safe, deterministic observation of ``actor`` (LA03).

        This is the lazy-mode counterpart of the exhaustive menu: it reports
        what exists and what capabilities it has, never the legal action list.
        It is read-only with respect to canonical world state (the distance
        caches are derived). It deliberately never calls ``actor_affordances``
        or ``_actor_options``.
        """
        self._actor(actor)
        attrs = self.eng.node(self._actors[actor])["attrs"]
        position = self.actor_position(actor)
        carrying = self.carry_state(actor)
        visible = self._visible_physical_object_records(actor)
        visible_objects = []
        containers_in_reach = []
        locations = self._ensure_physical_object_locations()
        for item in visible:
            record = {
                "id": item["id"],
                "name": item.get("name", item["id"]),
                "kind": item.get("kind", "object"),
                "location": item.get("location", "world"),
            }
            record.update(self._physical_object_capabilities(
                {**item, "_reachable": True}))
            visible_objects.append(record)
            if not record["container"]:
                continue
            contents = []
            if record["open"]:
                for child_id in locations.ids_at(item["id"]):
                    child = self._physical_objects.get(child_id)
                    if child is None:
                        continue
                    child_attrs = self.eng.node(child)["attrs"]
                    contents.append({"id": child_id,
                                     "kind": child_attrs.get("kind", "object"),
                                     "name": child_attrs.get("name", child_id)})
            containers_in_reach.append({
                "id": item["id"], "name": record["name"],
                "kind": record["kind"], "open": record["open"],
                "locked": record["locked"], "reachable": record["reachable"],
                "contents": contents, "world_container": False,
            })
        # LA04: the world's own containers (barrels, chests, the store) are
        # what fetch/put accept.  Publish only accessible containers on this
        # actor's cell, with a bounded contents summary.
        for name in sorted(self._containers):
            node, inners = self._containers[name]
            container_attrs = self.eng.node(node)["attrs"]
            if container_attrs.get("kind") == "carrier":
                continue
            if self.container_position(name) != position:
                continue
            if not self._container_accessible(actor, name):
                continue
            locked = self.is_locked(name)
            contents = [
                {"id": f"{name}:{kind}", "kind": kind, "name": kind,
                 "qty": round(self.contents(name, kind), 4)}
                for kind in sorted(inners)
                if self.contents(name, kind) > 0.0
            ]
            containers_in_reach.append({
                "id": name, "name": container_attrs.get("name", name),
                "kind": container_attrs.get("kind", "container"), "open": not locked,
                "locked": locked, "reachable": True, "contents": contents,
                "world_container": True,
            })
        containers_in_reach.sort(key=lambda item: item["id"])
        by_id = {}
        for item in containers_in_reach:
            existing = by_id.get(item["id"])
            if existing is None or (item.get("world_container")
                                    and not existing.get("world_container")):
                by_id[item["id"]] = item
        containers_in_reach = [by_id[key] for key in sorted(by_id)]
        holder = self.holder_of(actor)
        cell = self._observe_cell(position)
        busy = bool(self.busy(actor))
        observation = {
            "turn": int(self._turn),
            "actor": actor,
            "calendar": self.calendar(),
            "position": position,
            "terrain": self.terrain_state(position),
            "terrain_movement": self.terrain_movement_rules(),
            "health": attrs.get("health", "healthy"),
            "hunger": attrs.get("hunger", 0.0),
            "energy": self.energy(actor),
            "intoxication": self.intoxication(actor),
            "intoxication_band": self.intoxication_band(actor),
            "inventory": self.inventory(actor),
            "inventory_details": self._observe_inventory_details(actor),
            "held_items": self.held_items(actor),
            "worn": self.worn(actor),
            "carrying": carrying,
            "carried_weight": carrying["weight"],
            "carry_ratio": carrying["ratio"],
            "held": holder is not None,
            "holder": holder,
            "holding": self.holding_of(actor),
            "turn_state": self.actor_turn_state(actor),
            "job": self._observe_job(actor),
            "busy": busy,
            "skills": self.skill_levels(actor),
            "known_recipes": self._known_recipe_names(actor),
            "work_candidates": self._observe_work_candidates(actor, cell),
            "last_outcome": self.last_outcome(actor),
            "nearby_actors": self._observe_nearby_actors(actor, position),
            "visible_objects": visible_objects,
            "containers_in_reach": containers_in_reach,
            "cell": cell,
            "places": self._observe_places(actor, attrs),
            "heard": self.heard_utterances(actor, limit=20),
        }
        aftereffects = self.aftereffects(actor)
        if aftereffects:
            observation["aftereffects"] = aftereffects
        return observation

    def actor_affordances(self, actor):
        """Return the current legal, observed choices for a backend or UI."""
        self._actor(actor)
        return [dict(option) for option in self._actor_options(actor)] + _dn.lamp_options(self, actor)   # Phase 042

    def perform_plan(self, actor):
        """Enact the action selected by the resident's Ocelot graph."""
        plan = self._decide_actor(actor)
        return self._enact_plan(actor, plan)

    _EPHEMERAL_TARGET_KEYS = (
        "target", "recipient", "container", "source", "destination",
        "patient", "project", "name", "animal", "land", "crop_node",
        "sow_kind", "with", "joint",
    )

    def resolve_targets(self, actor, action, params):
        """Install and return the target map this proposal needs.

        A proposal that names stable identities (an actor, object, container,
        project, infrastructure, crop, animal or cell) needs no menu at all:
        this installs an empty map and ``_enact_plan`` reads the proposal's own
        fields.  The actor's previous map is replaced rather than merged, so no
        stale ``target:N`` entry can outlive the turn that published it.

        A legacy proposal carries an ephemeral key such as ``"target:3"``,
        copied from ``actor_affordances()``.  Only that menu knows what the key
        stood for, so this falls back to ``_actor_options(actor)`` and returns
        its map.  This keeps UI pickers, Ocelot's current adapter and legacy
        backends on exactly their old semantics.  An unknown action or a
        malformed proposal also installs an empty map; ``_enact_plan`` refuses
        it with its existing code rather than raising here.
        """
        self._actor(actor)
        values = params if isinstance(params, dict) else {}
        legacy = any(
            str(values.get(key)).startswith("target:")
            for key in self._EPHEMERAL_TARGET_KEYS
            if values.get(key) is not None
        )
        if legacy:
            self._actor_options(actor)
            return self._actor_targets.get(actor, {})
        targets = {}
        self._actor_targets[actor] = targets
        return targets

    def enact_plan(self, actor, plan):
        """Enact an external backend proposal after resolving only its targets."""
        self._actor(actor)
        plan = dict(plan)
        action = plan.get("action")
        self.resolve_targets(actor, action, plan)
        return self._attempt(actor, action, lambda: self._enact_plan(actor, plan))

    def _enact_plan(self, actor, plan):
        """Shared physical enactment for Ocelot and arbitrary cognition backends.

        A proposal with a missing key, a value of the wrong type, or a target
        this resident does not have is refused with False. Nothing here raises
        for backend input; the checks in ``major_action`` decide every refusal.
        """
        if actor not in self._actors:
            return self._refuse("unknown_target")
        if not isinstance(plan, dict):
            return self._refuse("malformed")
        action = plan.get("action")
        targets = self._actor_targets.get(actor, {})

        def target_of(key="target"):
            value = plan.get(key, "")
            if isinstance(value, (tuple, list)):
                return tuple(value)
            name = self._as_key(value)
            if name is None:
                return None
            if name in targets:
                return targets[name]
            # A direct stable name/id is its own target.  An unresolved
            # ephemeral key keeps the old refusal behaviour instead of
            # becoming a literal destination.
            if isinstance(name, str) and name.startswith("target:"):
                return None
            return name

        if action == "give":
            target = self._as_key(plan.get("recipient")) or target_of()
            if target in self._actors:
                return self.major_action(actor, "give", recipient=target,
                                         kind=plan.get("kind"), amount=plan.get("amount", 1.0))
            # A shop is not a physical recipient. Purchase intent, speech,
            # acceptance, and any payment are choices owned by cognition.
            return self._refuse("wrong_target")
        if action == "strike":
            return self.major_action(actor, "strike", target=plan.get("target"),
                                     intensity=plan.get("intensity", 1.0), with_kind=plan.get("with"))
        if action == "throw":
            return self.major_action(actor, "throw", target=plan.get("target"),
                                     with_kind=plan.get("with"), intensity=plan.get("intensity", 1.0))
        if action == "restrain":
            # Phase 033: a grab on a resident in reach (a reaction turn when the game runs it, none here).
            return self.major_action(actor, "restrain", target=plan.get("target"))
        if action == "release":
            return self.major_action(actor, "release")
        if action == "struggle":
            return self.major_action(actor, "struggle")
        if action in {"transfer", "take"}:
            if action == "transfer":
                recipient = plan.get("recipient") or target_of()
                return self.major_action(actor, "transfer", source=actor,
                                         recipient=recipient, kind=plan.get("kind"),
                                         amount=plan.get("amount", 1.0))
            return self.major_action(
                actor, action, source=plan.get("source"),
                recipient=plan.get("recipient"), kind=plan.get("kind"),
                amount=plan.get("amount", 1.0))
        if action == "rest":
            # Rest is a real major action. Phase 049 (supervisor decision): the plan path still refuses a rest at a
            # reserve of 0.8 or more as not_needed. The refusal makes the simple backend consult again next turn
            # (task_failed), which tests/test_phase055_concurrency.py depends on. A direct major_action rest is allowed.
            if self.stamina_reserve(actor) >= 0.8:
                return self._refuse("not_needed")
            return self.major_action(actor, "rest", amount=1.0)
        if action == "eat":
            kind = plan.get("kind")
            if not isinstance(kind, str):
                return self._refuse("malformed")
            equipment = self._serving_equipment(actor, kind)
            kwargs = {"kind": kind}
            if equipment is not None:
                kwargs.update(vessel=equipment[0], utensil=equipment[1])
            return self.major_action(actor, "eat", **kwargs)
        if action == "work":
            pace = 1.0 if plan.get("intensity") is None else plan["intensity"]
            kwargs = {"action_name": plan.get("recipe"), "intensity": pace}
            if "tool" in plan:                     # Phase 048: a kind of held tool, "none" for bare hands, or omitted
                kwargs["tool"] = plan["tool"]
            return self.major_action(actor, "start", **kwargs)
        if action == "sleep":
            return self.major_action(actor, "sleep")
        if action == "move":
            target = plan.get("destination")
            if target is None:
                target = target_of()
            if target is not None:
                # Phase 049 (supervisor decision): a backend's walk below e_low is refused here, as before the
                # conversion, so the backend's continuation is interrupted. Direct world calls still walk slowly.
                if self._exhaustion_band(actor)["below_e_low"]:
                    return self._refuse("exhausted")
                return self.major_action(actor, "move", destination=target)
        if action == "move_object":
            return self.major_action(actor, "move_object",
                                     object_id=plan.get("object_id", plan.get("item")),
                                     destination=plan.get("destination", plan.get("target")))
        if action in {"lock", "unlock"}:
            target = self._as_key(plan.get("container")) or target_of()
            if target is not None:
                return self.major_action(actor, action, container=target)
        if action == "put":
            target = self._as_key(plan.get("container")) or target_of()
            if target is not None:
                return self.major_action(actor, "put", container=target, kind=plan.get("kind"), amount=1.0)
        if action == "fetch":
            target = self._as_key(plan.get("source")) or target_of()
            source = target if target in self._containers else None
            return self.major_action(actor, "fetch", kind=plan.get("kind"), amount=1.0, source=source)
        if action == "joint":
            # Phase 047: a solo joint proposal (a lone member, or one the game did not group). Its result is the
            # member's own; a short group still runs and fails physically.
            joint = plan.get("joint")
            if not isinstance(joint, dict):
                return self._refuse("malformed")
            return bool(self.enact_joint(joint, [actor]).get(actor))
        if action == "tend_animals":
            target = self._as_key(plan.get("animal")) or target_of()
            if target in self._animals:
                destination = self.map_position_node(self._animals[target])
                if destination is not None and self.actor_position(actor) != destination:
                    if self._exhaustion_band(actor)["below_e_low"]:
                        return self._refuse("exhausted")
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "tend_animals", animal=target, task=plan.get("kind"))
            if target is not None:
                if self._exhaustion_band(actor)["below_e_low"]:
                    return self._refuse("exhausted")
                return self.major_action(actor, "move", destination=target)
        if action == "build":
            target = self._as_key(plan.get("project")) or target_of()
            if target in self._building_projects:
                cells = list(self.eng.neighbours(self._building_projects[target], "at_cell"))
                destination = self.map_position_node(cells[0]) if cells else None
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "build", project=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if action == "maintain":
            target = self._as_key(plan.get("name")) or target_of()
            if target in self._infrastructure:
                destination = self.map_position_node(self._infrastructure[target])
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "maintain", name=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if action == "care":
            target = self._as_key(plan.get("patient")) or target_of()
            if target in self._actors:
                destination = self.actor_position(target)
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "care", patient=target, care_kind=plan.get("care_kind"))
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if action in {"water", "harvest", "sow", "fertilise"}:
            target = target_of()
            if action in {"water", "harvest"}:
                crop_node = self._as_key(plan.get("crop_node"))
                if crop_node is not None and crop_node in {int(node) for node in self._crops.values()}:
                    target = crop_node
            elif plan.get("sow_kind") and plan.get("land"):
                target = (plan["sow_kind"], plan["land"])
            if target is not None:
                return self.major_action(actor, action, target=target)
        if action == "attempt":
            # Phase 050: a native verb (walk, eat, sleep...) routes to the world's own action; a physics verb is an attempt.
            verb = plan.get("verb")
            spec = self.E.VERBS.get(verb) if isinstance(verb, str) else None
            if spec is not None and spec.get("primitive") == "native":
                route = spec.get("route")
                if route is None:
                    return self.major_action(actor, "attempt", verb=verb, target=None)
                return self._enact_plan(actor, {**plan, "action": route})
            return self.major_action(actor, "attempt", verb=verb, target=self._as_key(plan.get("target")),
                                     with_kind=plan.get("with"), intensity=plan.get("intensity", 1.0))
        # The plan names no action this resident can take, or no target for it.
        return self._refuse("malformed")

    def resolve_actor_turn(self):
        """Settle deferred physical effects after an explicitly submitted turn."""
        self._run(force=True)

    def _ocelot_actor_tick(self):
        """Pump each private mind and enact major choices plus free speech."""
        self._actor_tick_in_progress = True
        try:
            # Small fixture worlds use ticks to exercise cognition and
            # conversation; the seeded town additionally lets those minds
            # enact their physical major choices.  This keeps an explicitly
            # started setup job from being silently replaced by an idle actor.
            if getattr(self, "_cast100", None) is not None:
                for actor in list(self._actors):
                    if not self.is_alive(actor) or self.actor_turn_state(actor)["major_action_used"]:
                        continue
                    self.perform_plan(actor)
        finally:
            self._actor_tick_in_progress = False
        # Resolve deferred body events once, then let free speech observe the
        # settled physical state.
        self.resolve_actor_turn()

    def _speech_relationship(self, speaker, target):
        relationship = self._relationships.get((speaker, target))
        if relationship is None:
            return None
        return dict(self.eng.node(relationship)["attrs"])

    def _speech_share_event(self, speaker, listener):
        """The speaker's most salient recent observation FOR THIS LISTENER,
        and its (possibly retelling-damped) salience.

        Salience is gated the same way Rime (2009) found emotionally
        significant experiences get shared: recently (age <= 1 day) and
        roughly in proportion to severity, floored so any recent event is at
        least mildly worth mentioning. It is then damped by how many times
        THIS listener has already heard it -- common ground is per-dyad
        (Clark & Brennan 1991), so a fresh listener always sees the
        undamped salience even after many retellings to someone else.  The
        damping rate itself scales toward 1 (slower decline) as severity
        rises, matching Rime's own finding that a more intense episode's
        sharing declines more slowly, not faster -- high-salience news gets
        retold MORE before tapering, not deduplicated harder.

        Candidates come from BOTH first-hand ``observed_event`` (full
        strength) and second-hand ``heard_events`` (DeGroot-compounded
        strength, age measured from when THIS speaker heard it, not the
        event's own day -- news is fresh to the teller even if the event
        happened earlier).  Returns ``(0.0, None)`` when nothing recent and
        un-exhausted remains -- the ``share`` speech option then loses its
        Argmax term and cannot be chosen, exactly as it should when there is
        nothing left to share.
        """
        day = float(self.eng.node(self._town)["attrs"].get("day", 0.0))
        mind = self._actor_minds[speaker]
        candidates = [(event, float(self.eng.node(event)["attrs"].get("day", day)), 1.0)
                      for event in self.eng.neighbours(self._actors[speaker], "observed_event")]
        candidates += [(event, held["day_heard"], held["strength"])
                       for event, held in mind.heard_events.items()]
        best_salience, best_event = 0.0, None
        for event, origin_day, strength in candidates:
            age = day - origin_day
            if age < 0.0 or age > 1.0:
                continue
            severity = float(self.eng.node(event)["attrs"].get("severity", 0.0))
            base_salience = max(0.25, severity) * strength
            retold = mind.told_events.get((listener, event), 0)
            retell_decay = min(0.95, 0.3 + severity)
            salience = base_salience * (retell_decay ** retold)
            if salience > best_salience:
                best_salience, best_event = salience, event
        return best_salience, best_event

    def _speech_provider(self, actor):
        """Return the resident supplied speech provider or local cognition."""
        mind = self._actor_minds[actor]
        provider = getattr(mind, "speech_backend", None)
        if provider is not None and callable(getattr(provider, "propose", None)):
            return provider
        # Explicit integration seam for an externally installed Ocelot mind.
        external = getattr(mind, "speech_provider", None)
        if external is not None and callable(getattr(external, "propose", None)):
            return external
        return DeterministicSpeechBackend(mind)

    def resident_free_text_proposal(self, actor, context):
        """External Ocelot seam: forward situated observations to its provider.

        An installed provider owns the returned text and raw meaning. A
        graph-only Ocelot resident may omit this capability and remain silent.
        """
        self._actor(actor)
        mind = self._actor_minds[actor]
        provider = getattr(mind, "speech_provider", None)
        propose = getattr(provider, "propose_free_text", None)
        if not callable(propose):
            propose = getattr(mind, "propose_free_text", None)
        if not callable(propose):
            return None
        return propose(context)

    def resident_speech_proposal(self, speaker, target):
        """Ask a resident provider for complete speech to a situated target.

        The provider owns the speech act, meaning and surface text. The world
        supplies observed encounter facts and returns the proposal; a caller
        must explicitly enact it through the ordinary speak action.
        """
        self._actor(speaker)
        if (target not in self._actors or target == speaker
                or not self.is_alive(target)):
            return None
        share_salience, share_event = self._speech_share_event(speaker, target)
        attrs = self.eng.node(self._actors[speaker])["attrs"]
        context = {
            "weather": str(self.eng.node(self._town)["attrs"].get("weather", "clear")),
            "trade": str(attrs.get("trade", "") or attrs.get("role", "")),
            "event": None,
            "event_ref": share_event,
        }
        if share_event is not None:
            event_attrs = self.eng.node(share_event)["attrs"]
            context["event"] = {
                "kind": str(event_attrs.get("kind", "")),
                "subject": str(event_attrs.get("subject", "")),
                "detail": str(event_attrs.get("detail", "")),
                "self": str(event_attrs.get("subject", "")) == str(speaker),
            }
        encounter = {
            "relationship": self._speech_relationship(speaker, target),
            "stranger": False,
            "share_salience": share_salience,
            "arousal": float(attrs.get("arousal", 0.4)),
            "loquacity_threshold": float(attrs.get("loquacity_threshold", 1.0)),
        }
        provider = self._speech_provider(speaker)
        if isinstance(provider, DeterministicSpeechBackend):
            return provider.propose_free_text(target, context=context,
                                              encounter=encounter)
        propose = getattr(provider, "propose_free_text", None)
        if not callable(propose):
            return None
        return propose({"target": target, "encounter": encounter, **context})

    def enact_speech_proposal(self, speaker, proposal):
        """Enact the text and meaning already proposed by a speech provider."""
        if not isinstance(proposal, dict) or not proposal.get("text"):
            return None
        target = proposal.get("target")
        if (target not in self._actors or not self.is_alive(speaker)
                or not self.is_alive(target)):
            return None
        utterance = self.speak(
            speaker, target, str(proposal["text"]),
            loudness=max(1.0, float(proposal.get("loudness", 1.0))),
            raw_data=proposal.get("raw"), backend_owned=True)
        heard = bool(self.eng.node(utterance)["attrs"].get("heard", 0.0))
        act = (proposal.get("raw") or {}).get("act")
        # The world establishes that the utterance was physically heard.
        # Belief uptake, confidence, and memory/retention are private
        # recipient cognition; do not infer them from delivery here.
        self._speech_events.append({"turn": int(self._turn), "speaker": speaker,
                                    "target": target, "kind": str(act or ""),
                                    "content": str(proposal["text"]), "heard": heard})
        return utterance

    def speech_choices(self, actor):
        """Read the resident's latest graph-native speech choices."""
        self._actor(actor)
        return {target: dict(choice)
                for target, choice in self._actor_minds[actor].speech_choices.items()}

    # ---------------------------------------------------- canonical state export
    def export_state(self, *, event_tail=None, include_report=True):
        """Return a JSON-safe snapshot of the canonical world graph.

        ``include_report=False`` omits the ``report`` and ``report_history``
        keys: they are derived summaries rather than canonical world state and
        are the expensive part of an export.  The no-argument call is unchanged
        and still includes both.  Ask ``report()``/``report_history()``
        explicitly when only the summary is wanted.
        """
        town = self.eng.node(self._town)["attrs"]
        actors = []
        for name, node in self._actors.items():
            a = self.eng.node(node)["attrs"]
            position = self.actor_position(name)
            actors.append({"id": name, "name": name, "role": a.get("role", ""),
                           "alive": bool(float(a.get("alive", 1.0))), "age": a.get("age", 0.0),
                           "life_stage": a.get("life_stage", "adult"), "health": a.get("health", "healthy"),
                           "hunger": a.get("hunger", 0.0), "skill": a.get("skill", 0.0),
                           "energy": self.energy(name), "exertion": self.exertion(name),
                           "carried_weight": a.get("carried_weight", 0.0),
                           "carry_ratio": a.get("carry_ratio", 0.0),
                           "carry_speed": a.get("carry_speed", 1.0),
                           "terrain": a.get("terrain", "grass"),
                           "terrain_speed": a.get("terrain_speed", 1.0),
                           "terrain_stamina_multiplier": a.get("terrain_stamina_multiplier", 1.0),
                           "literacy": a.get("literacy", 0.0), "coin": a.get("coin", 0.0),
                           "reputation": a.get("reputation", 0.5), "position": position,
                           "home": position, "x": position[0] if position else 0, "y": position[1] if position else 0,
                           "household": a.get("household", ""),
                           "inventory": self.inventory(name),
                           "held_items": self.held_items(name),
                           "worn": self.worn(name),
                           "references": sorted(self.known_references(name)),
                           "journal": (dict(self.eng.node(self._journals[name][-1])["attrs"])
                                       if self._journals.get(name) else None)})
        buildings = []
        for kind in sorted(self._places):
            position = self.building_position(kind)
            x, y = position if position else (0, 0)
            spec = self.E.BUILDINGS.get(kind, {})
            footprint = spec.get("footprint", spec.get("size", (3, 3)))
            if isinstance(footprint, (int, float)):
                footprint = (int(footprint), int(footprint))
            footprint = tuple(footprint) if len(footprint) == 2 else (3, 3)
            buildings.append({"id": kind, "type": kind, "position": position,
                              "x": x, "y": y, "w": int(footprint[0]), "h": int(footprint[1]),
                              "name": spec.get("display_name", kind.title())})
        square = self._map_layout.get("square", {}) if self._map_layout else {}
        square_fixtures = []
        for name, node in getattr(self, "_square_fixtures", {}).items():
            attrs = self.eng.node(node)["attrs"]
            square_fixtures.append({"id": name, "name": name,
                                    "kind": attrs.get("kind", "fixture"),
                                    "goods": list(attrs.get("goods", ())),
                                    "x": int(attrs.get("x", 0)), "y": int(attrs.get("y", 0))})
        events = []
        for key, node in list(self._events.items())[-event_tail if event_tail else None:]:
            events.append({"id": key, **dict(self.eng.node(node)["attrs"])})
        articles = [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._articles.items()]
        utterances = [{"id": int(node.value), **dict(self.eng.node(node)["attrs"])}
                      for node in self._utterances.values()]
        map_width = len(self._map_grid[0]) if self._map_grid else 0
        map_height = len(self._map_grid or [])
        map_seed = self.eng.node(self._map_node)["attrs"].get("seed", 0.0) if self._map_node else 0.0
        state = {"schema": "townview/1", "scenario": {
                    "id": self._scenario_data.get("id", "bigville"),
                    "name": self._scenario_data.get("name", "Bigville"),
                    "metadata": dict(self._scenario_data.get("metadata", {})),
                },
                "clock": dict(self.calendar()),
                "weather": {k: town.get(k) for k in ("rain", "temperature", "firewood_demand")},
                "map": {"width": map_width, "height": map_height, "w": map_width, "h": map_height,
                        "seed": map_seed,
                        "terrain_movement": self.terrain_movement_rules(),
                        "square": dict(square), "square_fixtures": square_fixtures,
                        "grid": self._map_grid, "tiles": self._map_grid,
                        "buildings": buildings},
                "physical_objects": self.physical_objects(),
                "residents": actors,
                "stocks": {kind: self.qty(kind) for kind in sorted(self._stock) if kind != "none"},
                "animals": [{"id": name, **dict(self.eng.node(node)["attrs"]),
                             "position": self.map_position_node(node),
                             "enclosure": self.animal_enclosure(name)}
                            for name, node in self._animals.items()],
                "fences": [{"id": name, **dict(self.eng.node(node)["attrs"]),
                            "position": self.map_position_node(node)}
                           for name, node in self._fences.items()],
                "enclosures": [{"id": name, **dict(self.eng.node(node)["attrs"]),
                                "cells": sorted(self._enclosure_cells.get(name, ())),
                                "intact": self.enclosure_intact(name)}
                               for name, node in self._enclosures.items()],
                "laws": [dict(v) for v in self._law_specs.values()],
                "policies": [dict(v) for v in self._policy_specs.values()],
                "documents": [{"kind": kind, "name": name} for kind, name in self._documents],
                "events": events, "articles": articles, "utterances": utterances,
                "speech_events": list(self._speech_events[-event_tail if event_tail else None:]),
                "paper": articles,
                "editions": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._editions.items()],
                "handovers": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._handovers.items()],
                "proposals": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._proposals.items()],
                "cases": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._cases.items()],
                "births": list(self._births), "deaths": list(self._deaths),
                "sanity": self.sanity_report()}
        if include_report:
            # Derived summaries, historically part of the export.  They are the
            # expensive half of the state read and are omitted on demand.
            state["report"] = self.report()
            state["report_history"] = self.report_history()
        return state

    # ---------------------------------------------------- turns and action budgets
    def _claim_major_action(self, actor, kind):
        node = self._actor(actor)
        attrs = self.eng.node(node)["attrs"]
        if float(attrs.get("major_action_used", 0.0)) == 1.0:
            return False
        self.eng.set_attr(node, "major_action_used", 1.0)
        self.eng.set_attr(node, "major_action_kind", str(kind))
        self.eng.set_attr(node, "last_major_action", str(kind))
        record = self.eng.add_node("MajorAction", {"kind": str(kind), "turn": float(self._turn),
                                                     "actor": actor, "complete": 0.0})
        self.eng.set_attr(record, "complete", 1.0)
        self.eng.add_edge_unchecked(node, "performed_major_action", record)
        self._turn_actions.setdefault(actor, []).append(record)
        return True

    def actor_turn_state(self, actor):
        attrs = self.eng.node(self._actor(actor))["attrs"]
        return {"turn": int(round(float(attrs.get("turn", 0.0)))),
                "major_action_used": bool(float(attrs.get("major_action_used", 0.0))),
                "major_action_kind": attrs.get("major_action_kind", ""),
                "free_actions_available": True}

    def actor_mind(self, actor):
        """Return the resident's private Ocelot instance for inspection."""
        self._actor(actor)
        return self._actor_minds[actor]

    def actor_tick(self, actor=None):
        """Open the next actor turn without changing physiology or held concepts."""
        names = [actor] if actor is not None else list(self._actors)
        for name in names:
            attrs = self.eng.node(self._actor(name))["attrs"]
            self.eng.set_attr(self._actor(name), "turn", float(self._turn))
            self.eng.set_attr(self._actor(name), "major_action_used", 0.0)
            self.eng.set_attr(self._actor(name), "major_action_kind", "")

    @staticmethod
    def _as_key(value):
        """A name or node reference from a backend proposal, else None (no bools, no empty names)."""
        if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
            return None
        return value

    @staticmethod
    def _as_amount(value):
        """A finite real number from a backend proposal, else None (no bools, no numeric strings)."""
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return float(value)

    def _known_ref(self, value, type_name=None):
        """Whether `value` is a node of this world (of `type_name`, when given)."""
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        try:
            record = self.eng.node(value)
        except (KeyError, TypeError, ValueError):
            return False
        return type_name is None or record["type"] == type_name

    def _walked_toward(self, actor, destination):
        """Start one step toward ``destination``. Once the move is under way it always uses the slot:
        terrain and load cost effort and may hold the walker on a cooldown with no change of cell."""
        self.move_actor(actor, destination)
        return True

    def _rested(self, actor, amount):
        """A rest is always enacted once claimed; the return value is the reserve, not a refusal."""
        self.rest(actor, amount)
        return True

    def _lie_down_as_major(self, actor):
        """A sleep is enacted once claimed (Phase 024)."""
        self._lie_down(actor, collapsed=False)
        return True

    def _refuse(self, code):
        """Name the physical reason the current attempt is refused, and return False.

        Every refusal point returns ``self._refuse(code)``. ``code`` must be a key of the pack's
        REFUSAL_REASONS table, so an unknown code is a programming error and raises ``ValueError``.
        """
        if code not in self.E.REFUSAL_REASONS:
            raise ValueError(f"unknown refusal reason: {code!r}")
        self._refusal_code = code
        return False

    def _recipe_start_block(self, actor, action_name):
        """The shared structural checks for starting a recipe now, or None.

        These are the checks ``_recipe_refusal`` applies on the enactment path: the
        recipe exists, the resident is awake, and they stand at the gathering
        site/building (and, for a burial, the grave has work ready).  Skill,
        season and strength are deliberately not here: Phase 049 treats them as
        consequences of working, not refusals to start.  ``recipe_preview`` adds
        them as a read-only menu-equivalent filter (LA07).
        """
        if action_name not in self._actions:
            return "not_known"
        # Phase 024: a resident who is asleep or collapsed cannot start work.
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return sleep_code
        # Phase 048: a recipe does not refuse for want of its tool. The job uses the tool its worker has, or bare
        # hands at the fitness they give (see _job_tool_item). What the world offers a backend is a separate matter.
        if not self._at_gathering_site(actor, action_name):
            return "not_at_site"
        if not self._at_recipe_building(actor, action_name):
            return "not_at_site"
        if not self._burial_ready(action_name):
            return "not_ready"
        return None

    def _recipe_refusal(self, actor, action_name):
        """The first physical check this actor fails to start a recipe now, or None when none fails.

        The checks run in the order ``_capable``, ``_can_attempt`` and ``_recipe_tools_usable`` make them."""
        # Phase 049: skill, season, strength and a second open job are consequences, not refusals. A batch below the
        # skill floor is poorer or spoiled (the completion of a job), an out-of-season batch yields little, a weak
        # worker works slower and strains (_job_strength_rate), and a worker with several jobs shares their progress
        # (_jobs_sharing).
        return self._recipe_start_block(actor, action_name)

    def recipe_preview(self, actor, recipe):
        """Read-only preview of whether ``actor`` could start ``recipe`` now (LA07).

        Returns ``{"ok": bool, "reason": str}`` with an existing refusal code
        where one applies.  This mirrors the menu's work publish filter
        (``not busy``, ``_can_attempt``, ``_recipe_inputs_available``) without
        opening a job, consuming stock or claiming the action slot.  It is the
        cheap backend's prefilter, not a replacement for enactment's own
        checks; a proposal that passes here may still be refused.
        """
        self._actor(actor)
        name = self._as_key(recipe)
        if name is None or name not in self._actions:
            return {"ok": False, "reason": "not_known"}
        spec = self._recipe_specs.get(name)
        if spec is None:
            return {"ok": False, "reason": "not_known"}
        if self.busy(actor):
            # The menu suppresses new work while a job is open.  `not_possible`
            # is the existing code for "the actor cannot act like this now".
            return {"ok": False, "reason": "not_possible"}
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return {"ok": False, "reason": sleep_code}
        # `_capable`: skill, season, strength and an open recipe's own held
        # tools.  Skill/season/strength share the `unskilled` code the rest of
        # the world uses for a resident who cannot do the work.
        if not self._skilled_enough(actor, name) or not self._recipe_in_season(name):
            return {"ok": False, "reason": "unskilled"}
        strength_needed, _stamina = self.E.recipe_exertion(name)
        if self.strength(actor) + 1e-9 < strength_needed:
            return {"ok": False, "reason": "unskilled"}
        if spec.get("open") and any(self._held_tool(actor, tool) is None
                                    for tool in spec.get("tools", [])):
            # A missing physical tool is a stock shortage, not a skill gap.
            return {"ok": False, "reason": "out_of_stock"}
        code = self._recipe_start_block(actor, name)
        if code is not None:
            return {"ok": False, "reason": code}
        if not self._recipe_inputs_available(name, actor):
            return {"ok": False, "reason": "out_of_stock"}
        return {"ok": True, "reason": ""}

    def _attempt(self, actor, action, run):
        """Run one major-action attempt and publish its outcome to the actor's own record.

        An attempt that runs inside another (``enact_plan`` calls ``major_action``) belongs to the outer
        attempt, which publishes once. An exception publishes nothing and propagates. A resident who is
        asleep or collapsed is refused any major action (Phase 024) before the attempt runs.
        """
        if self._outcome_open:
            return run()
        self._outcome_open = True
        self._refusal_code = None
        try:
            gated = isinstance(action, str) and action in self.E.MAJOR_ACTIONS
            sleep_code = self._sleep_code(actor) if gated else None
            if sleep_code is not None:
                applied = False
                self._refusal_code = sleep_code
            else:
                applied = bool(run())
            code = None if applied else (self._refusal_code or "not_possible")
        finally:
            self._outcome_open = False
            self._refusal_code = None
        self._publish_outcome(actor, action, applied, code)
        return applied

    def _publish_outcome(self, actor, action, applied, code):
        """Store the attempt's outcome on the actor's node, and log a refusal as a Refusal node.

        Only the acting resident's node carries the outcome. Nothing here tells another resident."""
        if actor not in self._actors:
            return
        node = self._actor(actor)
        self.eng.set_attr(node, "last_outcome", {"turn": int(self._turn), "action": str(action),
                                                 "applied": bool(applied), "reason": code or ""})
        if applied:
            return
        record = self.eng.add_node("Refusal", {"actor": actor, "action": str(action),
                                               "reason": code, "turn": int(self._turn)})
        self.eng.add_edge_unchecked(node, "refused", record)
        counts = {name: dict(by_reason) for name, by_reason in
                  self.eng.node(node)["attrs"].get("refusal_counts", {}).items()}
        by_reason = counts.setdefault(str(action), {})
        by_reason[code] = by_reason.get(code, 0) + 1
        self.eng.set_attr(node, "refusal_counts", counts)
        # Keep the newest REFUSAL_LOG_LIMIT refusals (node ids grow with creation).
        kept = sorted(self.eng.neighbours(node, "refused"))
        for old in kept[:max(0, len(kept) - int(self.E.REFUSAL_LOG_LIMIT))]:
            self.eng.remove_node(old)

    def last_outcome(self, actor):
        """The actor's own most recent major-action outcome (turn, action, applied, reason), or None."""
        outcome = self.eng.node(self._actor(actor))["attrs"].get("last_outcome")
        return None if outcome is None else dict(outcome)

    def refusals(self, actor):
        """The actor's logged refusals, oldest first, at most REFUSAL_LOG_LIMIT of them."""
        node = self._actor(actor)
        return [dict(self.eng.node(record)["attrs"])
                for record in sorted(self.eng.neighbours(node, "refused"))]

    def refusal_counts(self):
        """Refused attempts over all residents: counts by action, by reason, and in total."""
        by_action, by_reason, total = {}, {}, 0
        for name in self._actors:
            counts = self.eng.node(self._actor(name))["attrs"].get("refusal_counts", {})
            for action, reasons in counts.items():
                for reason, count in reasons.items():
                    by_action.setdefault(action, {})
                    by_action[action][reason] = by_action[action].get(reason, 0) + int(count)
                    by_reason[reason] = by_reason.get(reason, 0) + int(count)
                    total += int(count)
        return {"total": total, "by_action": by_action, "by_reason": by_reason}

    def _claimed_attempt(self, actor, kind, attempt, *, consumed=None):
        """Run one major-action attempt inside the actor's turn slot.

        The slot is claimed for the attempt. A refused attempt (``attempt``
        returns False) releases the claim and its turn record, so the actor's
        turn state and history are as they were before. ``consumed``, when
        given, names a refusal that still used the slot because the world
        recorded a consequence (an unpaid obligation's arrears). If ``attempt``
        raises, the claim is released and the exception propagates.
        """
        attrs = self.eng.node(self._actor(actor))["attrs"]
        before = {"major_action_used": attrs.get("major_action_used", 0.0),
                  "major_action_kind": attrs.get("major_action_kind", ""),
                  "last_major_action": attrs.get("last_major_action", "")}
        if not self._claim_major_action(actor, kind):
            return self._refuse("slot_used")
        record = self._turn_actions[actor][-1]
        old_dispatch = self._major_dispatch
        self._major_dispatch = True
        try:
            enacted = bool(attempt())
        except Exception:
            self._release_major_action(actor, before, record)
            raise
        finally:
            self._major_dispatch = old_dispatch
        if not enacted and not (consumed is not None and consumed()):
            self._release_major_action(actor, before, record)
        return enacted

    def _release_major_action(self, actor, before, record):
        node = self._actor(actor)
        for key, value in before.items():
            self.eng.set_attr(node, key, value)
        turns = self._turn_actions.get(actor, [])
        if record in turns:
            turns.remove(record)
        self.eng.remove_node(record)

    def major_action(self, actor, action, *args, **kwargs):
        """Dispatch one substantial action through the unified turn budget.

        Each attempt runs the same physical checks the primitive runs, and the
        action slot is held only while the attempt runs. A proposal with a
        missing or mistyped value, or a target that does not exist, returns
        False; a refused attempt leaves ``actor_turn_state`` unchanged. The
        refusal's physical reason is published to the actor (``last_outcome``)
        and logged (``refusals``). An unknown action name is a programming error
        and raises ``ValueError``.

        Existing low-level ``do``/``start`` calls remain useful for scenario
        setup and timed-job tests.  Simulation code should use this method (or
        ``perform_major_action``) so the one-action rule is enforced.
        """
        return self._attempt(actor, action,
                             lambda: self._major_action_attempt(actor, action, *args, **kwargs))

    def _major_action_attempt(self, actor, action, *args, **kwargs):
        """The branch for each major action. Returns True when the attempt is enacted."""
        if actor not in self._actors:
            return self._refuse("unknown_target")
        if action in _dn.ACTIONS:   # Phase 042: light and douse, at a lamp or with a held candle
            return self._claimed_attempt(actor, action, lambda: _dn.act(self, actor, action, kwargs, args))
        if action == "move":
            # Phase 033: a held resident and a resident holding someone cannot walk.
            if self.holder_of(actor) is not None:
                return self._refuse("restrained")
            if self.holding_of(actor) is not None:
                return self._refuse("holding")
            destination = kwargs.get("destination", args[0] if args else None)
            current = self.actor_position(actor)
            if not isinstance(destination, (int, tuple)):
                return self._refuse("malformed")
            if current is None or destination not in self._map_cells:
                return self._refuse("unknown_target")
            if destination == current:
                return self._refuse("invalid_destination")
            if self.distance(current, destination) is None:
                return self._refuse("invalid_destination")
            # Phase 049: below e_low a resident walks at the slowest rate (not refused as too tired); the collapse at
            # e_collapse stops them (see _exhaustion_band).
            return self._claimed_attempt(actor, "move", lambda: self._walked_toward(actor, destination))
        if action == "move_object":
            object_id = self._as_key(kwargs.get("object_id", kwargs.get("item", args[0] if args else None)))
            destination = self._as_key(kwargs.get("destination", kwargs.get("target",
                                                                             args[1] if len(args) > 1 else None)))
            if object_id is None or destination is None:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "move_object", lambda: self.move_physical_object_as_actor(
                actor, object_id, destination))
        if action == "give":
            recipient = self._as_key(kwargs.get("recipient", kwargs.get("target", args[0] if args else None)))
            kind = self._as_key(kwargs.get("kind", args[1] if len(args) > 1 else None))
            amount = self._as_amount(kwargs.get("amount", args[2] if len(args) > 2 else 1.0))
            if recipient not in self._actors:
                return self._refuse("unknown_target")
            if kind is None or amount is None:
                return self._refuse("malformed")
            if not self._physical_transfer_precheck(actor, recipient, kind, amount):
                return False
            return self._claimed_attempt(actor, "give", lambda: self._physical_transfer(
                actor, recipient, kind, amount))
        if action == "transfer":
            source = self._as_key(kwargs.get("source", args[0] if args else None))
            recipient = self._as_key(kwargs.get("recipient", args[1] if len(args) > 1 else None))
            kind = self._as_key(kwargs.get("kind", args[2] if len(args) > 2 else None))
            amount = self._as_amount(kwargs.get("amount", args[3] if len(args) > 3 else 1.0))
            if source is None or recipient is None or kind is None or amount is None:
                return self._refuse("malformed")
            if actor != source:
                return self._refuse("wrong_target")
            if not self._physical_transfer_precheck(source, recipient, kind, amount):
                return False
            return self._claimed_attempt(actor, "transfer", lambda: self._physical_transfer(
                source, recipient, kind, amount, handover_kind="transfer"))
        if action == "strike":
            # Phase 038: a strike without a game is a blow the target does not answer (no reaction).
            plan = {"target": kwargs.get("target", args[0] if args else None),
                    "intensity": kwargs.get("intensity", args[1] if len(args) > 1 else 1.0),
                    "with": kwargs.get("with_kind")}
            pending, code = self.strike_begin(actor, plan)
            if pending is None:
                return self._refuse(code)
            applied, code = self.strike_resolve(pending, None)
            if not applied:
                self._refusal_code = code
            return applied
        if action == "throw":
            # Phase 040: a throw without a game is an object the target does not answer (no reaction, no contest).
            plan = {"target": kwargs.get("target", args[0] if args else None),
                    "with": kwargs.get("with_kind", args[1] if len(args) > 1 else None),
                    "intensity": kwargs.get("intensity", args[2] if len(args) > 2 else 1.0)}
            pending, code = self.throw_begin(actor, plan)
            if pending is None:
                return self._refuse(code)
            applied, code = self.throw_resolve(pending, None)
            return applied
        if action == "take":
            # Phase 029: a take without a game is a contest the holder does not answer (no reaction).
            recipient = kwargs.get("recipient")
            if recipient is not None and self._as_key(recipient) != actor:
                return self._refuse("wrong_target")
            plan = {"source": kwargs.get("source", args[0] if args else None),
                    "kind": kwargs.get("kind", args[1] if len(args) > 1 else None),
                    "amount": kwargs.get("amount", args[2] if len(args) > 2 else 1.0)}
            pending, code = self.take_begin(actor, plan)
            if pending is None:
                return self._refuse(code)
            applied, code = self.take_resolve(pending, None)
            if not applied:
                self._refusal_code = code
            return applied
        if action == "restrain":
            # Phase 033: a grab without a game is a restraint the target does not answer (no reaction).
            plan = {"target": kwargs.get("target", args[0] if args else None)}
            pending, code = self.restrain_begin(actor, plan)
            if pending is None:
                return self._refuse(code)
            applied, code = self.restrain_resolve(pending, None)
            if not applied:
                self._refusal_code = code
            return applied
        if action == "release":
            if self.holding_of(actor) is None:
                return self._refuse("not_holding")
            return self._claimed_attempt(actor, "release", lambda: self._release_held(actor))
        if action == "struggle":
            return self.struggle(actor)
        if action == "put":
            container = self._as_key(kwargs.get("container", args[0] if args else None))
            kind = self._as_key(kwargs.get("kind", args[1] if len(args) > 1 else None))
            amount = self._as_amount(kwargs.get("amount", args[2] if len(args) > 2 else 1.0))
            if container not in self._containers:
                return self._refuse("unknown_target")
            if kind is None or amount is None:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "put", lambda: self.put(actor, container, kind, amount))
        if action == "pick_up":
            item = self._as_key(kwargs.get("item", args[0] if args else None))
            if not self._known_ref(item):
                return self._refuse("unknown_target")
            return self._claimed_attempt(actor, "pick_up", lambda: self.pick_up(actor, item))
        if action == "drop":
            item = self._as_key(kwargs.get("item", args[0] if args else None))
            if not self._known_ref(item):
                return self._refuse("unknown_target")
            return self._claimed_attempt(actor, "drop", lambda: self.drop_item(actor, item))
        if action == "eat":
            kind = kwargs.get("kind", args[0] if args else None)
            if kind is not None and not isinstance(kind, str):
                return self._refuse("malformed")
            source = kwargs.get("source")
            if source is not None and self._as_key(source) is None:
                return self._refuse("malformed")
            vessel, utensil = kwargs.get("vessel"), kwargs.get("utensil")
            return self._claimed_attempt(actor, "eat", lambda: self.eat(
                actor, kind, vessel=vessel, utensil=utensil, source=source))
        if action == "rest":
            amount = self._as_amount(kwargs.get("amount", args[0] if args else 1.0))
            if amount is None or amount <= 0.0:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "rest", lambda: self._rested(actor, amount))
        if action == "sleep":
            # Phase 024: sleep is enacted here. Whether to sleep is the backend's decision. Phase 049: a sleep at a full
            # reserve is allowed; it uses the slot and the time, and the sleeper wakes at once.
            return self._claimed_attempt(actor, "sleep", lambda: self._lie_down_as_major(actor))
        if action == "fetch":
            kind = self._as_key(kwargs.get("kind", args[0] if args else None))
            amount = self._as_amount(kwargs.get("amount", args[1] if len(args) > 1 else 1.0))
            raw_source = kwargs.get("source")
            source = None if raw_source is None else self._as_key(raw_source)
            if kind is None or amount is None:
                return self._refuse("malformed")
            if raw_source is not None and source not in self._containers:
                return self._refuse("unknown_target")
            return self._claimed_attempt(actor, "fetch", lambda: self.fetch(actor, kind, amount, source=source))
        if action == "build":
            project = self._as_key(kwargs.get("project", args[0] if args else None))
            labour = self._as_amount(kwargs.get("labour", args[1] if len(args) > 1 else 1.0))
            if project not in self._building_projects:
                return self._refuse("unknown_target")
            if labour is None:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "build", lambda: self.advance_building(
                project, actor, labour=labour) is not None)
        if action == "maintain":
            name = self._as_key(kwargs.get("name", args[0] if args else None))
            labour = self._as_amount(kwargs.get("labour", args[1] if len(args) > 1 else 1.0))
            if name not in self._infrastructure:
                return self._refuse("unknown_target")
            if labour is None:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "maintain", lambda: self.maintain_infrastructure(
                actor, name, labour=labour))
        if action == "care":
            patient = self._as_key(kwargs.get("patient", args[0] if args else None))
            if patient not in self._actors:
                return self._refuse("unknown_target")
            # Phase 043: a medical act (checkup, treat, well_baby) is the care action with a care_kind.
            care_kind = kwargs.get("care_kind")
            if care_kind is not None:
                medical = {"checkup": self.checkup, "treat": self.treat_patient,
                           "well_baby": self.well_baby_visit}.get(str(care_kind))
                if medical is None:
                    return self._refuse("malformed")
                return self._claimed_attempt(actor, "care", lambda: medical(actor, patient))
            return self._claimed_attempt(actor, "care", lambda: self.care_for(actor, patient))
        if action == "tend_animals":
            animal = self._as_key(kwargs.get("animal", args[0] if args else None))
            task = self._as_key(kwargs.get("task", args[1] if len(args) > 1 else "milk"))
            if animal not in self._animals:
                return self._refuse("unknown_target")
            if task not in self.E.ANIMAL_HUSBANDRY:
                return self._refuse("malformed")
            return self._claimed_attempt(actor, "tend_animals",
                                         lambda: self._tend_outcome(actor, animal, task))
        if action in ("work", "make", "start"):
            recipe = self._as_key(kwargs.get("action_name", kwargs.get("recipe", args[0] if args else None)))
            if recipe is None:
                return self._refuse("malformed")
            code = self._recipe_refusal(actor, recipe)
            if code is not None:
                return self._refuse(code)
            # Phase 048: the proposal's tool is checked before the slot is claimed (an unheld named tool is refused).
            tool = kwargs.get("tool", _DEFAULT_TOOL)
            _mode, _item, tool_refusal = self._tool_choice(actor, tool)
            if tool_refusal is not None:
                return self._refuse(tool_refusal)
            if action == "start":
                pace = kwargs.get("intensity", 1.0)
                if self._as_amount(pace) is None:
                    return self._refuse("malformed")
                return self._claimed_attempt(actor, action,
                                             lambda: self.start(actor, recipe, intensity=pace, tool=tool))
            return self._claimed_attempt(actor, action, lambda: self.do(actor, recipe, tool=tool))
        if action in {"water", "harvest", "sow", "fertilise"}:
            target = kwargs.get("target", args[0] if args else None)
            if action == "sow":
                crop, land = (target if isinstance(target, tuple) and len(target) == 2 else (None, None))
                crop, land = self._as_key(crop), self._as_key(land)
                if crop not in self.E.CROPS or land not in self._land:
                    return self._refuse("unknown_target")
                return self._claimed_attempt(actor, "sow", lambda: self.sow(actor, crop, land=land) is not None)
            if action == "fertilise":
                land = self._as_key(target)
                amount = kwargs.get("amount")
                if land not in self._land:
                    return self._refuse("unknown_target")
                if amount is not None and self._as_amount(amount) is None:
                    return self._refuse("malformed")
                return self._claimed_attempt(actor, action, lambda: self.fertilise(actor, land, amount) > 0.0)
            crop_node = self._as_key(target)
            if not self._known_ref(crop_node, "Crop"):
                return self._refuse("unknown_target")
            if action == "water":
                return self._claimed_attempt(actor, action, lambda: self.water_crop(actor, crop_node))
            return self._claimed_attempt(actor, action, lambda: bool(self.harvest_crop(crop_node, harvester=actor)))
        if action in ("pay_obligation", "collect", "deliver_collected"):
            obligation = kwargs.get("obligation", args[0] if args else None)
            if isinstance(obligation, bool) or not isinstance(obligation, int):
                return self._refuse("malformed")
            attrs = self._obligation_attrs(obligation)
            if attrs is None:
                return self._refuse("unknown_target")
            if action == "deliver_collected":
                share_bp = kwargs.get("share_bp", args[1] if len(args) > 1 else 10000)
                if isinstance(share_bp, bool) or not isinstance(share_bp, int):
                    return self._refuse("malformed")
                return self._claimed_attempt(actor, action, lambda: self.deliver_collected(
                    actor, obligation, share_bp))
            # A short payer records arrears: a consequence of this attempt, so the slot stays used.
            arrears_before = float(attrs["arrears"])
            attempt = self.pay_obligation if action == "pay_obligation" else self.collect
            return self._claimed_attempt(
                actor, action, lambda: attempt(actor, obligation),
                consumed=lambda: float(self._obligation_attrs(obligation)["arrears"]) > arrears_before)
        if action in ("lock", "unlock"):
            # Phase 030: the named container, or the town store ("store"), from the cell it stands on.
            name = self._as_key(kwargs.get("container", kwargs.get("target", args[0] if args else None)))
            if name is None:
                return self._refuse("malformed")
            if name != "store" and name not in self._containers:
                return self._refuse("unknown_target")
            operation = self.lock if action == "lock" else self.unlock
            return self._claimed_attempt(actor, action, lambda: operation(actor, name))
        if action == "attempt":
            # Phase 050: any verb the world has physics for, on a thing in reach, resolved by worlds/resolution.py.
            verb = kwargs.get("verb", args[0] if args else None)
            target = kwargs.get("target", args[1] if len(args) > 1 else None)
            with_kind = kwargs.get("with_kind", kwargs.get("with", args[2] if len(args) > 2 else None))
            intensity = kwargs.get("intensity", args[3] if len(args) > 3 else 1.0)
            return self._attempt_verb(actor, verb, target, with_kind, intensity)
        if action == "complete_request":
            request = kwargs.get("request", args[0] if args else None)
            if isinstance(request, str):
                if request not in self._requests:
                    return self._refuse("unknown_target")
            elif not self._known_ref(request):
                return self._refuse("unknown_target")
            return self.complete_request(actor, request, result=kwargs.get("result", ""))
        raise ValueError(f"unknown major action: {action}")

    perform_major_action = major_action

    def free_action(self, actor, action, *args, **kwargs):
        """Data-driven dispatcher for actions that do not consume the slot."""
        if action == "speak":
            return self.speak(actor, kwargs.pop("target", args[0] if args else None),
                              kwargs.pop("content", args[1] if len(args) > 1 else ""), **kwargs)
        if action == "reply":
            return self.reply(actor, kwargs.pop("target", args[0]),
                              kwargs.pop("content", args[1] if len(args) > 1 else ""), **kwargs)
        if action == "write_note":
            return self.write_note(actor, kwargs.pop("content", args[0] if args else ""), **kwargs)
        if action == "give_note":
            return self.give_note(actor, kwargs.pop("recipient", args[0]),
                                  kwargs.pop("note", args[1] if len(args) > 1 else None))
        if action == "accept":
            if "item" in kwargs:
                return self.accept_item(actor, kwargs.pop("item"), giver=kwargs.pop("giver", None))
            return self.accept_request(actor, kwargs.pop("request", args[0]))
        if action == "decline":
            return self.decline_request(actor, kwargs.pop("request", args[0]))
        if action == "set_intensity":
            return self.set_job_pace(actor, kwargs.pop("intensity", args[0] if args else None))
        if action == "stop":
            return self.stop_job(actor)
        raise ValueError(f"unknown free action: {action}")

    def set_job_pace(self, actor, intensity):
        """Change a running timed job's pace without losing its progress (free action set_intensity, Phase 050b).

        Returns False when the actor has no unfinished job, or the value is not a finite number. The pace is
        clamped to [1 / care_cap, haste_cap] and the applied value is kept on the job."""
        from worlds import resolution as R
        value = self._as_amount(intensity)
        if value is None or actor not in self._actors:
            return False
        job = self._job_of(actor)
        if job is None or float(self.eng.node(job)["attrs"].get("complete", 0.0)) == 1.0:
            return False
        table = self.E.RESOLUTION
        applied, _clamped = R.pace_clamp(value, table["care_cap"], table["haste_cap"])
        self.eng.set_attr(job, "pace", applied)
        return True

    # ---------------------------------------------------- shared reference knowledge
    def reference_names(self):
        return set(self._reference_specs)

    def reference(self, name):
        return self._reference_specs[name]

    def reference_data(self, name):
        return dict(self._reference_specs[name]["reference"])

    def knows_reference(self, actor, name):
        return name in self._actor_references.get(self._actors[actor], {})

    def known_references(self, actor):
        return {self.eng.node(n)["attrs"]["name"]
                for n in self.eng.neighbours(self._actors[actor], "knows_reference")}

    def known_references_at(self, actor, abstraction):
        """Return the resident's concepts at one abstraction level."""
        return {self.eng.node(n)["attrs"]["name"]
                for n in self.eng.neighbours(self._actors[actor], "knows_reference")
                if self.eng.node(n)["attrs"].get("abstraction") == abstraction}

    def teach_reference(self, teacher, learner, name):
        """Record an explanation without writing learner-held knowledge."""
        if (teacher not in self._actors or learner not in self._actors
                or name not in self._reference_specs):
            return False
        self.create_event("reference_explained", subject=teacher,
                          detail=f"{teacher} explained {name} to {learner}.",
                          observer=teacher, severity=0.05)
        return False

    def write_recipe(self, author, recipe):
        """Create a physical Recipe record containing the supplied inscription."""
        rec = self.eng.add_node("WrittenRecipe", {"recipe": recipe})
        self.eng.add_edge_unchecked(self._actors[author], "wrote", rec)
        self.create_event("recipe_written", subject=author,
                          detail=f"{author} wrote down {recipe}.",
                          observer=author, severity=0.05)
        return rec

    def read_recipe(self, reader, record):
        """Return written recipe content as an observation; do not infer learning."""
        recipe = self.eng.node(record)["attrs"]["recipe"]
        self.create_event("recipe_read", subject=reader,
                          detail=f"{reader} inspected a written recipe record.",
                          observer=reader, severity=0.02)
        return recipe

    # ---------------------------------------------------- apprenticeship (skill built under a master)
    def apprentice(self, learner, master):
        """Apprentice a learner to a master: the learner's skill then rises toward the master's, a
        little each period (the sk_apprentice rule), until they are skilled enough for the master's work."""
        self.eng.add_edge_unchecked(self._actors[learner], "apprenticed_to", self._actors[master])

    def finish_apprenticeship(self, learner, master):
        """End an apprenticeship -- the learner keeps the skill they built."""
        self.eng.remove_edge_unchecked(self._actors[learner], "apprenticed_to", self._actors[master])

    # ---------------------------------------------------- literacy + schooling (reading/writing, education)
    def _lit(self, actor): return float(self.eng.node(self._actors[actor])["attrs"].get("literacy", 0.0))
    def _cap(self, actor): return float(self.eng.node(self._actors[actor])["attrs"].get("capability", 0.0))
    def _can_read(self, actor): return self._lit(actor) >= self.E.LIT_FUNCTIONAL

    def literacy(self, actor): return round(self._lit(actor), 4)
    def capability(self, actor): return round(self._cap(actor), 4)
    def literacy_tier(self, actor): return self.E.literacy_tier(self._lit(actor))
    def can_read(self, actor):
        """Functional literacy -- read/write a note, read a written recipe, read the newspaper."""
        return self._can_read(actor)
    def can_read_law(self, actor):
        """Read AND understand the council laws -- only the well educated (needs high capability)."""
        return self._cap(actor) >= self.E.LIT_EDUCATED and self._lit(actor) >= self.E.LIT_EDUCATED
    def can_account(self, actor):
        """Keep accounts (reckoning) -- only the well educated."""
        return self._cap(actor) >= self.E.LIT_EDUCATED
    def can_learn(self, actor): return float(self.eng.node(self._actors[actor])["attrs"].get("learn", 0.0)) > 0.0

    def enrol(self, pupil, teacher):
        """Send a pupil to school under a teacher -- their literacy and capability then rise toward the
        teacher's, a little each period (the ed_school rule), IF they can learn. Reading is learned here;
        a labourer who goes to school can become functionally literate, then educated."""
        self.eng.add_edge_unchecked(self._actors[pupil], "attends", self._actors[teacher])

    def leave_school(self, pupil, teacher):
        self.eng.remove_edge_unchecked(self._actors[pupil], "attends", self._actors[teacher])

    def skill(self, actor): return round(float(self.eng.node(self._actors[actor])["attrs"]["skill"]), 4)
    def recipe_min_skill(self, action_name):
        return round(float(self.eng.node(self._actions[action_name])["attrs"].get("min_skill", 0.0)), 4)
    def can_make(self, actor, action_name):
        """Whether the actor could make it mechanically: skilled enough to attempt (a gathering recipe
        also needs its site; see _can_attempt)."""
        return self._capable(actor, action_name)


    # ---------------------------------------------------- do an action (the ONE engine)
    def _open_job(self, actor, action_name, remaining, pace=1.0, tool_mode="default", tool_item=None):
        asp = self._actions[action_name]
        action_attrs = self.eng.node(asp)["attrs"]
        site_kind = self._recipe_specs.get(action_name, {}).get("gathered_from")
        if site_kind:
            # A gathering batch is taken from its site as the job opens (do/start have already checked it).
            self._draw_gathering_site(site_kind, action_name)
        # The recipe's declared stamina cost (RECIPE_EXERTION) is spent over the job's ticks (Phase 022).
        stamina = float(self.E.recipe_exertion(action_name)[1])
        job = self.eng.add_node("Job", {"remaining": float(remaining), "last_tick": 0.0,
                                        "min_quality": 1.0, "item_inputs": 0.0,
                                        "canonical_actor": str(actor),
                                        "stamina_total": stamina, "stamina_left": stamina,
                                        "stamina_ticks": float(remaining),
                                        # Phase 050: the strength the recipe demands; the core's cost ratio reads it.
                                        "strength_needed": float(self.E.recipe_exertion(action_name)[0]),
                                        # Phase 050b: the job's pace (intensity on a recipe), read each tick.
                                        "pace": float(pace),
                                        # Phase 048: how the job's tool is chosen ("default", "item" or "hands"), and
                                        # the fitness now and over the job (the lowest), read each tick.
                                        "tool_mode": str(tool_mode), "fit": 1.0, "fit_low": 1.0, "effort_mult": 1.0,
                                        # Phase 049: a seasonal recipe worked out of its season yields this share (read at completion).
                                        "season_yield": 1.0 if self._recipe_in_season(action_name)
                                        else float(self.E.RESOLUTION["off_season_yield"]),
                                        # Phase 032: a recipe with a strength requirement trains strength too.
                                        "uses_strength": 1.0 if self.E.recipe_exertion(action_name)[0] > 0.0 else 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "on_job", job)
        self.eng.add_edge_unchecked(job, "runs", asp)
        self.eng.set_attr(self._actors[actor], "busy", 1.0)
        if tool_item is not None:
            self.eng.add_edge_unchecked(job, "tool_item", tool_item)      # the tool the proposal named
        # The cell the job started on: the job pauses while its worker stands elsewhere (Phase 023).
        here = self.actor_position(actor)
        if here is not None:
            self.eng.set_attr(job, "start_cell", [int(here[0]), int(here[1])])
        for need in self.eng.neighbours(asp, "in_need"):
            a = self.eng.node(need)["attrs"]
            jn = self.eng.add_node("Need", {"kind": a["kind"], "qty": float(a["qty"]), "met": 0.0,
                                            "is_item": float(a.get("is_item", 0.0)),
                                            "slot_type": a.get("slot_type", ""), "drawn_from": ""})
            self.eng.add_edge_unchecked(job, "need", jn)
        improvised = False
        for tu in self.eng.neighbours(asp, "in_tool"):
            a = self.eng.node(tu)["attrs"]
            jt = self.eng.add_node("ToolUse", {"kind": a["kind"], "met": 0.0})
            self.eng.add_edge_unchecked(job, "uses", jt)
            # Phase 048: the job runs without the tool its recipe names when that tool is not the one it uses.
            used = self._job_tool_item(job, actor, a["kind"], bool(self._recipe_specs.get(action_name, {})
                                                                    .get("open")))
            if used is None or self.eng.node(used)["attrs"].get("kind") != a["kind"]:
                improvised = True
        if improvised:
            self._tool_tally["improvised_jobs"] += 1
        self._refresh_job_fit(job, 0.0)        # the job's fitness is known from the start, before any tick

    def _spend_job_stamina(self, job, final=False, share=1.0):
        """Spend a job's declared stamina through the Effort mechanism movement uses (Phase 022).

        Each tick of a timed job spends stamina_total / stamina_ticks; `final` spends whatever is left
        (all of it for an instant `do`). `share` scales a tick's spend by the job's progress that tick
        (Phase 024: a slowed worker advances less than a tick, so spends less). The Effort is resolved by
        `_resolve_actor_events`, which also applies the hunger scaling and the reserve floor of 0."""
        ja = self.eng.node(job)["attrs"]
        left = float(ja.get("stamina_left", 0.0))
        if left <= 0.0:
            return
        ticks = float(ja.get("stamina_ticks", 0.0))
        if final or ticks <= 0.0:
            declared = left
        else:
            declared = min(left, float(ja.get("stamina_total", 0.0)) / ticks * share)
        self.eng.set_attr(job, "stamina_left", max(0.0, left - declared))
        # Phase 048: a poor tool fit costs more stamina for the same work (1 / fit, up to the effort cap).
        amount = declared * float(ja.get("effort_mult", 1.0))
        actor = str(ja.get("canonical_actor", ""))
        if amount <= 0.0 or actor not in self._actors or self._bodies.get(actor) is None:
            return
        # Phase 050: the declared share is scaled by the resolution core's cost ratio, clamp(D/C, 1, effort_cap),
        # with D the recipe's strength demand and C the worker's strength now. At the strength gate the ratio is 1,
        # so the declared cost is paid as before; a worker whose strength has fallen mid-job pays more.
        from worlds import resolution as R
        ratio = R.cost_ratio(float(ja.get("strength_needed", 0.0)), self.strength(actor), 1.0,
                             float(self.E.RESOLUTION["effort_cap"]))
        amount *= ratio
        # Phase 050b: pace (intensity on a recipe) scales the effort by pace^k, as an attempt's intensity does.
        amount *= float(ja.get("pace", 1.0)) ** float(self.E.RESOLUTION["k"])
        effort = self.eng.add_node("Effort", {"uses_strength": float(ja.get("uses_strength", 0.0)), "uses_stamina": 1.0,
                                              "intensity": min(1.0, amount), "stamina_cost": amount,
                                              "terrain": "", "terrain_speed": 1.0,
                                              "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "exerted", effort)

    def _knows_or_none(self, actor, action_name):
        """Compatibility hook; world action admissibility does not inspect beliefs."""
        return True

    def _skilled_enough(self, actor, action_name):
        """An actor can only attempt a recipe they are SKILLED enough for -- their working level at the
        recipe's skill (their own, lifted by a close skill and the metaskill) must reach its min_skill
        floor. Reading the recipe is not enough; the hand needs the training."""
        level = self.recipe_skill_level(actor, self._recipe_specs.get(action_name, {}))
        floor = float(self.eng.node(self._actions[action_name])["attrs"].get("min_skill", 0.0))
        return level + 1e-9 >= floor

    # ---------------------------------------------------- skill levels, clusters, metaskills
    def _levels(self, actor):
        """The actor's skill levels, with their role's main skill read from the legacy scalar `skill`
        (the scalar stays authoritative for that skill; practice writes both)."""
        a = self.eng.node(self._actors[actor])["attrs"]
        levels = dict(a.get("skill_levels", {}))
        main = (self.E.trade_skills(a.get("role", "")) or [None])[0]
        if main is not None:
            levels[main] = float(a.get("skill", levels.get(main, 0.0)))
        return levels

    def skill_levels(self, actor):
        return {k: round(float(v), 4) for k, v in self._levels(actor).items()}

    def metaskill_levels(self, actor):
        return {k: round(float(v), 4) for k, v in
                self.eng.node(self._actors[actor])["attrs"].get("metaskill_levels", {}).items()}

    def skill_level(self, actor, skill):
        """The actor's own level at a skill (0 if never learned)."""
        return self.skill_levels(actor).get(skill, 0.0)

    def _person(self, actor):
        a = self.eng.node(self._actors[actor])["attrs"]
        return {"aptitude": float(a.get("aptitude", 1.0)), "aptitude_base": float(a.get("aptitude_base", 1.0)),
                "talents": dict(a.get("talents", {})), "limitations": list(a.get("limitations", []))}

    def capacities(self, actor):
        """The actor's aptitude (meta-metaskill), metaskill talents, and limitations."""
        return self._person(actor)

    def set_capacities(self, actor, *, aptitude=None, talents=None, limitations=None, size=None):
        """Set an actor's capacities (setup, or a scenario authoring a particular person)."""
        node = self._actors[actor]
        if size is not None:
            # Phase 029: body size is a physical trait of the body (CONTEST uses it), not of the Agent.
            self.eng.set_attr(self._bodies[actor], "size", float(size))
        if aptitude is not None:
            self.eng.set_attr(node, "aptitude", float(aptitude))
            self.eng.set_attr(node, "aptitude_base", float(aptitude))
        if talents is not None:
            assert set(talents) <= set(self.E.METASKILLS), f"unknown metaskill in {talents}"
            self.eng.set_attr(node, "talents", {k: float(v) for k, v in talents.items()})
        if limitations is not None:
            assert set(limitations) <= set(self.E.SKILL_LIMITATIONS), f"unknown limitation in {limitations}"
            self.eng.set_attr(node, "limitations", sorted(limitations))
        return self._person(actor)

    def _founding_levels(self, role, trades, skill):
        """({skill: level}, {metaskill: level}) for a new resident: their trades' skills at `skill`, and every
        resident at least the CONTEST baseline in fighting (Phase 029). A constable's trade gives fighting at
        the trade's level instead. The baseline lifts the metaskill of fighting like any other level."""
        levels, metas = self.E.initial_skill_levels((role,) + tuple(trades), skill)
        base = float(self.E.CONTEST["baseline_level"])
        if base > 0.0 and float(levels.get("fighting", 0.0)) < base:
            levels["fighting"] = base
            meta = self.E.skill_metaskill("fighting")
            if meta:
                metas[meta] = max(float(metas.get(meta, 0.0)), float(self.E.META_FROM_SKILL) * base)
        return levels, metas

    def draw_capacities(self, actor, *, seed=0, sex=None):
        """Draw an actor's capacities from the population distributions (E.draw_person_capacities),
        deterministically from `seed` and their name."""
        import zlib
        import numpy as np
        rng = np.random.default_rng((int(seed) * 1_000_003) ^ zlib.crc32(str(actor).encode()))
        age = float(self.eng.node(self._actors[actor])["attrs"].get("age", 30.0))
        drawn = self.E.draw_person_capacities(rng, age=age, sex=sex)
        return self.set_capacities(actor, aptitude=drawn["aptitude"], talents=drawn["talents"],
                                   limitations=drawn["limitations"], size=drawn["size"])

    def effective_skill(self, actor, skill):
        """The actor's working level at a skill: own level, lifted by their closest skill through the
        metaskill (sharpened by aptitude), lowered by any limitations."""
        a = self.eng.node(self._actors[actor])["attrs"]
        person = {**self._person(actor), "intoxication": self.intoxication(actor)}
        value = self.E.effective_skill(self._levels(actor), a.get("metaskill_levels", {}), skill, person)
        return round(float(value) * self._aftereffect_skill_factor(actor), 4)

    def recipe_skill_level(self, actor, recipe):
        """Working level for a recipe row (its skill per E.recipe_skill); a recipe with no named skill
        falls back to the actor's main skill."""
        skill = self.E.recipe_skill(recipe) if recipe else None
        if skill is None:
            return float(self.eng.node(self._actors[actor])["attrs"].get("skill", 0.0))
        return self.effective_skill(actor, skill)

    def seed_skill_floor(self, actor, levels):
        """Raise an actor's own levels to at least `levels` ({skill: level}), and their metaskill levels
        to match (META_FROM_SKILL x level, the rule add_actor uses). Used for apprenticeships in trades the
        actor no longer works (Phase 019). Levels already higher are kept."""
        node = self._actors[actor]
        attrs = self.eng.node(node)["attrs"]
        current = dict(attrs.get("skill_levels", {}))
        metas = dict(attrs.get("metaskill_levels", {}))
        for skill, level in sorted(levels.items()):
            assert skill in self.E.SKILLS, f"unknown skill: {skill}"
            current[skill] = max(float(current.get(skill, 0.0)), float(level))
            meta = self.E.skill_metaskill(skill)
            if meta:
                metas[meta] = max(float(metas.get(meta, 0.0)), float(self.E.META_FROM_SKILL) * float(level))
        self.eng.set_attr(node, "skill_levels", current)
        self.eng.set_attr(node, "metaskill_levels", metas)
        self._sync_main_skill(actor)
        return current

    def set_skill_level(self, actor, skill, level):
        """Set an actor's own level at a skill (setup, or a backend recording what they have learned)."""
        assert skill in self.E.SKILLS, f"unknown skill: {skill}"
        node = self._actors[actor]
        levels = self._levels(actor)
        levels[skill] = max(0.0, min(1.0, float(level)))
        self.eng.set_attr(node, "skill_levels", levels)
        self._sync_main_skill(actor)
        return levels[skill]

    def _sync_main_skill(self, actor):
        """Keep the legacy scalar `skill` equal to the level of the actor's role's main skill."""
        node = self._actors[actor]
        a = self.eng.node(node)["attrs"]
        main = (self.E.trade_skills(a.get("role", "")) or [None])[0]
        if main is not None:
            self.eng.set_attr(node, "skill", float(a.get("skill_levels", {}).get(main, a.get("skill", 0.0))))

    def _consolidate_practice(self):
        """End of period: turn each actor's logged practice into skill and metaskill levels."""
        step = float(self.E.PRACTICE["event_step"])
        for actor, node in self._actors.items():
            a = self.eng.node(node)["attrs"]
            log = a.get("skill_practice", {})
            if not log:
                continue
            levels = self._levels(actor)
            metas = dict(a.get("metaskill_levels", {}))
            person = self._person(actor)
            cognitive_on = bool(self.physical_subsystems.get("cognitive_practice", False))
            for skill, minutes in sorted(log.items()):
                # Off, cognitive practice is not consolidated: its levels and the aptitude gain it would
                # have carried (learning to learn) stay unchanged. The minutes are dropped with the log.
                if self.E.skill_learning(skill) == "cognitive" and not cognitive_on:
                    continue
                before = float(levels.get(skill, 0.0))
                gain, meta_gain, aptitude_gain = self.E.practice_gain(levels, metas, skill, minutes, person)
                person["aptitude"] += aptitude_gain
                levels[skill] = before + gain
                meta = self.E.skill_metaskill(skill)
                if meta:
                    metas[meta] = float(metas.get(meta, 0.0)) + meta_gain
                # the worker notices their own progress when they cross a tenth
                if int(levels[skill] / step) > int(before / step):
                    self.create_event("learned_skill", subject=actor,
                                      detail=f"{actor} grew more skilled at {skill}.",
                                      observer=actor, severity=0.15)
            self.eng.set_attr(node, "skill_levels", levels)
            self.eng.set_attr(node, "metaskill_levels", metas)
            self.eng.set_attr(node, "aptitude", person["aptitude"])
            self.eng.set_attr(node, "skill_practice", {})
            self._sync_main_skill(actor)

    def _can_attempt(self, actor, action_name):
        """Whether the actor may start this recipe now: capable (see _capable), and, for a gathering
        recipe, standing on the site of its kind with a batch of stock (see _at_gathering_site)."""
        return (self._capable(actor, action_name) and self._at_gathering_site(actor, action_name)
                and self._at_recipe_building(actor, action_name) and self._burial_ready(action_name))

    def _capable(self, actor, action_name):
        """Admissibility depends on mechanical capability, not assumed knowledge: the actor must be
        SKILLED enough and (for seasonal gathering) it must be the right season. Any recipe with a strength
        requirement (RECIPE_EXERTION) needs an effective strength that meets it (Phase 032: trade or open).
        Open (household) recipes also need the recipe's tools in the actor's own hands. Location and site
        stock are not part of capability (see _can_attempt)."""
        if not (action_name in self._actions and self._skilled_enough(actor, action_name)
                and self._recipe_in_season(action_name)):
            return False
        recipe = self._recipe_specs.get(action_name, {})
        strength_needed, _stamina = self.E.recipe_exertion(action_name)
        if self.strength(actor) + 1e-9 < strength_needed:
            return False
        if recipe.get("open"):
            if any(self._held_tool(actor, tool) is None for tool in recipe.get("tools", [])):
                return False
        return True

    def _recipe_tools_usable(self, actor, action_name):
        """Every tool the recipe uses is physically usable by this actor: their own unbroken tool for an
        open (household) recipe, else a trade tool at their workplace or in hand."""
        own_tools = bool(self._recipe_specs.get(action_name, {}).get("open"))
        for tool in self.eng.neighbours(self._actions[action_name], "in_tool"):
            kind = self.eng.node(tool)["attrs"].get("kind", "")
            if own_tools:
                if self._held_tool(actor, kind) is None:
                    return False
            elif self._worker_tool(actor, kind) is None:
                return False
        return True

    # ------------------------------------------------------- Phase 048: tool fitness, improvised work, stop

    def _tool_choice(self, actor, tool):
        """How a job is tooled, from the proposal (Phase 048): (mode, item, refusal).

        Omitted (_DEFAULT_TOOL): the right tool the worker has, else bare hands. None or "none": bare hands. A tool
        kind: the held tool of that kind, or bare hands when the worker holds none (Phase 049). Anything else is malformed."""
        if tool is _DEFAULT_TOOL:
            return "default", None, None
        if tool is None or (isinstance(tool, str) and tool == "none"):
            return "hands", None, None
        if not isinstance(tool, str) or tool == "":
            return None, None, "malformed"
        kind = self._as_key(tool)
        if kind is None:
            return None, None, "malformed"
        item = self._held_tool(actor, kind)
        if item is None:
            # Phase 049: a named tool the worker does not hold is not a refusal; the work goes on with bare hands
            # (fitness RESOLUTION.hands_fit), as a missing tool did under Phase 048.
            return "hands", None, None
        return "item", item, None

    def _holds_item(self, actor, item):
        node = self._actor(actor)
        return any(item in self.eng.neighbours(node, edge) for edge in ("holds_in_hand", "holds_tableware", "holds"))

    def _job_tool_item(self, job, actor, kind, own_tools):
        """The tool a job uses for one tool slot of `kind`, now (Phase 048). None is bare hands.

        A named tool (tool_mode "item") is used while the worker holds it and it is serviceable; "hands" uses none;
        the default uses the open recipe's own held tool, or a trade tool at the workplace or in hand."""
        ja = self.eng.node(job)["attrs"]
        mode = str(ja.get("tool_mode", "default"))
        if mode == "hands":
            return None
        if mode == "item":
            for item in self.eng.neighbours(job, "tool_item"):
                if (self.eng.has_node(item) and self._holds_item(actor, item)
                        and self._serviceable(self.eng.node(item)["attrs"])):
                    return item
            return None
        if own_tools:
            return self._held_tool(actor, kind)
        return self._worker_tool(actor, kind)

    def _tool_fit(self, item, verb, work_hardness, slot_kind=None):
        """(fit, row_effort) of one tool for a verb on work of the given hardness (Phase 048).

        Bare hands (item None) fit every verb at RESOLUTION hands_fit. An authored TOOL_FIT row for the verb gives the
        row's mult, scaled by the tool's quality and condition, and the row's effort. The right tool for a recipe's
        slot (an item of slot_kind) fits at 1 times its quality and condition. Any other tool gives closeness x
        hardness x edge x weight, scaled the same way. The arithmetic is in worlds/resolution.py."""
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        tf = self.E.TOOL_FIT
        if item is None:
            return float(rs["hands_fit"]), 1.0
        attrs = self.eng.node(item)["attrs"]
        kind = str(attrs.get("kind", ""))
        quality = float(attrs.get("quality", 1.0))
        condition = float(attrs.get("condition", 1.0))
        for row in tf["rows"].get(kind, []):
            if row["verb"] == verb:
                return R.fitness(float(row["mult"]), quality, condition), float(row["effort"])
        if slot_kind is not None and kind == slot_kind:
            return R.fitness(1.0, quality, condition), 1.0
        spec = self._item_specs.get(kind, {})
        tool_material = self.E.MATERIALS.get(spec.get("material"), {})
        table = R.closeness_table(tf["pairs"])
        physical = (R.closeness(str(spec.get("verb", "")), verb, table, same=tf["same_verb"],
                                unrelated=rs["unrelated_fit"])
                    * R.hardness_term(float(tool_material.get("hardness", 0.0)), work_hardness,
                                      tf["hardness_zero_gap"])
                    * R.edge_term(verb, tf["edge_verbs"], kind in tf["edged_kinds"], tf["no_edge"])
                    * R.weight_term(verb, tf["weight_verbs"], float(attrs.get("weight", 1.0)), tf["min_weight"]))
        return R.fitness(physical, quality, condition), 1.0

    def _wear_tool(self, item, amount):
        """Wear a tool by `amount` of its condition. A tool at 0 is broken, and the breaking is tallied."""
        attrs = self.eng.node(item)["attrs"]
        condition = max(0.0, float(attrs.get("condition", 1.0)) - float(amount))
        self.eng.set_attr(item, "condition", condition)
        if condition <= 0.0 and float(attrs.get("broken", 0.0)) != 1.0:
            self.eng.set_attr(item, "broken", 1.0)
            self._tool_tally["broken_tools"] += 1

    def _accrue_strain(self, actor, amount):
        """Add strain to a worker (Phase 050; jobs too, Phase 048). A full strain is an accident: the worker takes
        accident_harm through harm(), and the strain resets to zero."""
        rs = self.E.RESOLUTION
        node = self._actors[actor]
        strain = float(self.eng.node(node)["attrs"].get("strain", 0.0)) + float(amount)
        if strain >= float(rs["strain_limit"]):
            self.harm(actor, float(rs["accident_harm"]), "accident")
            strain = 0.0
            self._tool_tally["accidents"] += 1
        self.eng.set_attr(node, "strain", strain)

    def _refresh_job_fit(self, job, share):
        """The fitness of a job's tools now (Phase 048), and the work it does this tick. Returns the fitness: the lowest
        over the job's tool slots, 1.0 for a job with no tool slot.

        The job keeps its fitness, its stamina multiplier (1 / fit up to the effort cap, times an authored row's
        effort) and the lowest fitness so far. A tick of work (share > 0) wears each tool by the excess wear of a poor
        fit, and strains the worker by its effort share x (1 - fit). Nothing here is random."""
        from worlds import resolution as R
        ja = self.eng.node(job)["attrs"]
        actor = str(ja.get("canonical_actor", ""))
        asp = next(iter(self.eng.neighbours(job, "runs")), None)
        if actor not in self._actors or asp is None:
            return 1.0
        rs = self.E.RESOLUTION
        name = str(self.eng.node(asp)["attrs"].get("name", ""))
        own_tools = bool(self._recipe_specs.get(name, {}).get("open"))
        fits, multipliers = [], []
        for tu in self.eng.neighbours(job, "uses"):
            kind = str(self.eng.node(tu)["attrs"].get("kind", ""))
            spec = self._item_specs.get(kind, {})
            work_hardness = float(self.E.MATERIALS.get(spec.get("material"), {}).get("hardness", 0.0))
            item = self._job_tool_item(job, actor, kind, own_tools)
            fit, row_effort = self._tool_fit(item, str(spec.get("verb", "")), work_hardness, kind)
            fits.append(fit)
            multipliers.append(R.effort_multiplier(fit, rs["effort_cap"], row_effort))
            if item is not None and share > 0.0:
                tool_material = self.E.MATERIALS.get(self._item_specs.get(
                    str(self.eng.node(item)["attrs"].get("kind", "")), {}).get("material"), {})
                gap = max(0.0, work_hardness - float(tool_material.get("hardness", 0.0)))
                wear = float(self.eng.node(item)["attrs"].get("wear", spec.get("wear_rate", 0.02)))
                excess = R.tool_wear_excess(wear, share, fit, rs["mismatch_wear"], 1.0 + float(rs["hardness_wear"]) * gap)
                if excess > 0.0:
                    self._wear_tool(item, excess)
        fit_now = (min(fits) if fits else 1.0) * _dn.work_visibility(self, actor)   # Phase 042: dark work
        self.eng.set_attr(job, "fit", fit_now)
        self.eng.set_attr(job, "effort_mult", max(multipliers) if multipliers else 1.0)
        self.eng.set_attr(job, "fit_low", min(float(ja.get("fit_low", 1.0)), fit_now))
        ticks = float(ja.get("stamina_ticks", 0.0))
        if share > 0.0 and ticks > 0.0 and fit_now < 1.0:
            self._accrue_strain(actor, R.strain(share / ticks, fit_now))
        return fit_now

    def _skill_share_of_floor(self, actor, action_name):
        """The working skill of `actor` at a recipe, as a share of the recipe's min_skill floor (Phase 049). 1.0 when
        the recipe has no floor, and it can exceed 1 above the floor."""
        from worlds import resolution as R
        floor = float(self.eng.node(self._actions[action_name])["attrs"].get("min_skill", 0.0))
        if floor <= 0.0:
            return 1.0
        level = self.recipe_skill_level(actor, self._recipe_specs.get(action_name, {}))
        return R.clamp(level / floor, 0.0, math.inf)

    def _job_strength_rate(self, job, share):
        """The progress rate a job keeps under its worker's strength (Phase 049), and the strain of a heavy trade.

        A recipe with a strength demand keeps min(1, strength / demand) of its progress (Phase 050's progress term
        at the reference of 1). A worker at or above the demand keeps all of it, so the committed times do not move.
        A heavy trade also strains its worker by the shortfall in strength or in skill (Phase 050's strain term),
        accrued like a poor tool fit. `share` is this tick's progress share, read for the strain only."""
        from worlds import resolution as R
        ja = self.eng.node(job)["attrs"]
        actor = str(ja.get("canonical_actor", ""))
        needed = float(ja.get("strength_needed", 0.0))
        if actor not in self._actors or needed <= 0.0:
            return 1.0
        rho_strength = self.strength(actor) / needed
        asp = next(iter(self.eng.neighbours(job, "runs")), None)
        name = str(self.eng.node(asp)["attrs"].get("name", "")) if asp is not None else ""
        rho = min(rho_strength, self._skill_share_of_floor(actor, name)) if name else rho_strength
        ticks = float(ja.get("stamina_ticks", 0.0))
        if share > 0.0 and ticks > 0.0 and rho < 1.0:
            self._accrue_strain(actor, R.strain(share / ticks, rho))
        return R.progress_rate(rho_strength, 1.0, 1.0)

    def _jobs_sharing(self, job):
        """How many of the worker's jobs advance at once (Phase 049): the unfinished, unpaused jobs they hold. A
        worker's progress per tick is divided among them. At least 1."""
        actor = str(self.eng.node(job)["attrs"].get("canonical_actor", ""))
        if actor not in self._actors:
            return 1
        open_jobs = 0
        for other in self.eng.neighbours(self._actors[actor], "on_job"):
            oa = self.eng.node(other)["attrs"]
            if float(oa.get("complete", 0.0)) != 1.0 and float(oa.get("remaining", 0.0)) > 0.0 \
                    and not self._job_away(other):
                open_jobs += 1
        return max(1, open_jobs)

    def stop_job(self, actor, job=None):
        """Abandon one of the actor's timed jobs (free action stop, Phase 048). ``job`` names it; by default it is the
        actor's first job (Phase 049: a worker may hold several). Its inputs are taken only at completion, so only
        the progress is lost; the stamina already spent stays spent. False when there is no unfinished job."""
        if actor not in self._actors:
            return False
        if job is None:
            job = self._job_of(actor)
        elif job not in self.eng.neighbours(self._actors[actor], "on_job"):
            return False
        if job is None or float(self.eng.node(job)["attrs"].get("complete", 0.0)) == 1.0:
            return False
        node = self._actors[actor]
        self.eng.set_attr(job, "complete", 1.0)
        self.eng.set_attr(job, "remaining", 0.0)
        self.eng.set_attr(job, "stopped", 1.0)
        self.eng.remove_edge_unchecked(node, "on_job", job)
        self.eng.set_attr(node, "busy", 1.0 if self._job_of(actor) is not None else 0.0)
        self._set_job_paused(actor, self.job_paused(actor))
        return True

    def tool_tally(self):
        """Counts over the whole town (Phase 048): jobs run without their named tool (improvised_jobs), strains that
        became accidents, and tools broken by use. Plain counts; nothing about any resident's capability."""
        return dict(self._tool_tally)

    def _held_tool(self, actor, kind):
        """An unbroken tool of `kind` the actor holds (hand, belt, or carried), or None."""
        node = self._actor(actor)
        for edge in ("holds_in_hand", "holds_tableware", "holds"):
            for item in self.eng.neighbours(node, edge):
                ia = self.eng.node(item)["attrs"]
                if ia.get("kind") == kind and float(ia.get("broken", 0.0)) != 1.0:
                    return item
        return None

    def _new_tool_item(self, kind, *, quality=1.0):
        """A new, unbroken ToolItem of `kind` with its wear rate and fit from the item data."""
        spec = self._item_specs.get(kind, {})
        item = self.eng.add_node("ToolItem", {"kind": kind, "weight": self.item_weight(kind),
                                                "quality": float(quality), "condition": 1.0, "broken": 0.0,
                                                "wear": float(spec.get("wear_rate", 0.02)),
                                                "decay": self.E.decay_rate(kind),
                                                "use_armed": 0.0, "repair_armed": 0.0})
        fit = self.eng.add_node("ToolFit", {"mult": float(spec.get("base_mult", 1.0)) * float(quality)})
        self.eng.add_edge_unchecked(item, "fit_for", fit)
        return item

    def give_tool(self, actor, kind, *, quality=1.0):
        """Put a new tool of `kind` in an actor's possession (founding kit, or a gift/purchase setup)."""
        item = self._new_tool_item(kind, quality=quality)
        self.eng.add_edge_unchecked(self._actor(actor), "holds", item)
        self._refresh_carry_state(actor)
        return item

    def stow_tool(self, actor, item):
        """Put a tool the actor holds onto the shelf of their workplace building.

        The worker must be at the workplace once the clock runs, and the stow is a major action."""
        place = self._at_workplace(actor)
        if place is None or self._item_owner_edge(actor, item) is None:
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "stow_tool"):
            return False
        node = self._actor(actor)
        for edge in ("holds_in_hand", "holds_tableware", "holds"):
            self.eng.remove_edge_unchecked(node, edge, item)
        kind = self.eng.node(item)["attrs"].get("kind", "")
        if kind in self._actor_tableware.get(actor, {}):
            self._actor_tableware[actor][kind] = [held for held in self._actor_tableware[actor][kind]
                                                  if held != item]
        if self._actor_hands.get(actor) == item:
            self._actor_hands[actor] = None
        self.eng.add_edge_unchecked(place, "has_tool_item", item)
        self._refresh_carry_state(actor)
        return True

    def do(self, actor, action_name, tool=_DEFAULT_TOOL):
        """Perform an action INSTANTLY (no timer). Refused if the actor does not KNOW the recipe or is
        not SKILLED enough (below its min_skill floor).

        ``tool`` (Phase 048): omitted, the job uses the right tool its worker has, else bare hands; None or "none"
        for bare hands; a tool kind for the held tool of that kind (refused as no_tool when none is held)."""
        code = self._recipe_refusal(actor, action_name)
        if code is not None:
            return self._refuse(code)
        mode, item, refusal = self._tool_choice(actor, tool)
        if refusal is not None:
            return self._refuse(refusal)
        # Calls made before the first simulation tick remain convenient setup
        # operations.  Once the clock is running, a direct craft is a major
        # action too; the explicit dispatcher suppresses this second charge.
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "work"):
            return self._refuse("slot_used")
        self._open_job(actor, action_name, 0.0, tool_mode=mode, tool_item=item); self._request_rule_sweep()
        return True

    def start(self, actor, action_name, intensity=1.0, tool=_DEFAULT_TOOL):
        """START a TIMED action; refused if the actor does not know OR is not skilled enough for it.

        ``intensity`` is the job's pace (Phase 050b): above 1 the job finishes sooner, at a cost in quality and
        stamina; below 1 it is slower and better. It is clamped to [1 / care_cap, haste_cap]. ``tool`` is as for do."""
        code = self._recipe_refusal(actor, action_name)
        if code is not None:
            return self._refuse(code)
        mode, item, refusal = self._tool_choice(actor, tool)
        if refusal is not None:
            return self._refuse(refusal)
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "start"):
            return self._refuse("slot_used")
        mins = float(self.eng.node(self._actions[action_name])["attrs"]["time_minutes"])
        self._open_job(actor, action_name, math.ceil(mins / float(self.E.TIME["minutes_per_tick"])),
                       pace=self._pace_value(intensity), tool_mode=mode, tool_item=item); self._request_rule_sweep()
        return True

    def _pace_value(self, value):
        """A recipe pace from a proposal: the number clamped to [1 / care_cap, haste_cap]; anything that is not a
        finite number is the normal pace (1.0). The major action refuses such values before they get here."""
        from worlds import resolution as R
        number = self._as_amount(value)
        if number is None:
            number = 1.0
        applied, _clamped = R.pace_clamp(number, self.E.RESOLUTION["care_cap"], self.E.RESOLUTION["haste_cap"])
        return applied

    def tick(self, n=1):
        for _ in range(int(n)):
            # The canonical simulation turn is the same clock tick used by
            # timed work.  Opening a turn resets only the actor's action slot;
            # it does not overwrite hunger, health, beliefs, memories, or
            # intentions.  Those remain held/world state and are changed only
            # by their own rules and actions.
            self._turn += 1
            self.actor_tick()
            self.eng.set_attr(self._town, "clock", float(self.eng.node(self._town)["attrs"]["clock"]) + 1.0)
            old_day = int(float(self.eng.node(self._town)["attrs"].get("day", 0.0)))
            self._advance_calendar()
            _dn.tick(self)   # Phase 042: the sky, lamp oil and candles, once day and night is on
            if int(float(self.eng.node(self._town)["attrs"].get("day", 0.0))) > old_day:
                self._daily_life_tick()
                self._regrow_gathering_sites()
            self._job_tick_armed = True
            self._run()
            self._job_tick_armed = False
            # A world tick advances physical time only. Animal and resident
            # decisions are submitted by an explicit game/backend session.
            self._run()
            # Phase 047: a load carried last turn drops if a carrier collapsed, slept or left reach during this tick.
            self._settle_joint_loads()
            # Last, so every crossing this turn is counted before untrodden
            # ground grows back.
            self._terrain_recovery_tick()
            # Phase 033: each tick of a restraint costs the holder and the held resident by the contest rule.
            self._holds_tick()

    def run_turns(self, n=1):
        """Advance unified actor turns; an alias with an explicit simulation name."""
        self.tick(n)

    def forge(self, actor, action_name):
        self.do(actor, action_name); return self.newest_tool()

    # ---------------------------------------------------- discrete tools (use / repair) + read-offs
    def newest_tool(self):
        tools = list(self.eng.neighbours(self._town, "has_tool_item"))
        return tools[-1] if tools else None

    def use_tool(self, tool, times=1):
        # EN03: each use arms the tool and relies on the rule sweep to consume
        # one use.  A multi-use call must therefore sweep per use; only the
        # ordinary single use can share the turn's authoritative sweep.
        uses = int(times)
        for _ in range(uses):
            self.eng.set_attr(tool, "use_armed", 1.0); self._request_rule_sweep(force=uses > 1)

    def repair_tool(self, maker, tool):
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(maker, "repair"):
            return False
        self.eng.add_edge_unchecked(self._actors[maker], "repairs", tool)
        self.eng.set_attr(tool, "repair_armed", 1.0); self._request_rule_sweep()
        return True

    def tool_kind(self, tool): return self.eng.node(tool)["attrs"]["kind"]
    def tool_quality(self, tool): return round(float(self.eng.node(tool)["attrs"]["quality"]), 4)
    def tool_condition(self, tool): return round(float(self.eng.node(tool)["attrs"]["condition"]), 4)
    def tool_broken(self, tool): return float(self.eng.node(tool)["attrs"]["broken"]) == 1.0
    def tool_fitness(self, tool):
        fits = list(self.eng.neighbours(tool, "fit_for"))
        return round(float(self.eng.node(fits[0])["attrs"]["mult"]), 4) if fits else 0.0
    def instrument_condition(self, kind):
        """Condition of the workshop tool of `kind` (the unbroken one if several), 0.0 if none stands."""
        item = self.workshop_tool(kind)
        return 0.0 if item is None else round(float(self.eng.node(item)["attrs"]["condition"]), 4)

    # ---------------------------------------------------- clothes: dyed, worn, protective
    def dye_garment(self, dyer, garment, dye_kind):
        """A dyer dyes a garment a colour from a dye pile -- the RULE (cl_dye) takes the colour from the
        dye's data and consumes one dye. The adapter only arms the garment against the dye Stock."""
        if not self._store_open(dyer):
            self._refuse("store_locked")
            return None
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(dyer, "dye"):
            return None
        dye = self.set_stock(dye_kind, self.qty(dye_kind))
        self.eng.set_attr(garment, "dye_armed", 1.0)
        self.eng.add_edge_unchecked(garment, "dyed_with", dye)
        colour = self._item_specs.get(dye_kind, {}).get("colour", dye_kind)
        self.eng.set_attr(garment, "colour", colour)
        self.set_stock(dye_kind, max(0.0, self.qty(dye_kind) - 1.0))
        self._request_rule_sweep()
        return self.garment_colour(garment)

    def wear(self, actor, garment):
        """An agent PUTS ON a garment -- seen wearing it (a wears edge). The garment's warmth/rain rating
        (from the item data) is written onto the instance so the protection rules can read it."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "wear"):
            return False
        spec = self._item_specs.get(self.tool_kind(garment), {})
        self.eng.set_attr(garment, "warmth", float(spec.get("warmth", 0.0)))
        self.eng.set_attr(garment, "rain", float(spec.get("rain", 0.0)))
        self.eng.set_attr(garment, "finery", float(spec.get("finery", 0.0)))
        self.eng.add_edge_unchecked(self._actors[actor], "wears", garment)
        self._request_rule_sweep()
        return True

    def take_off(self, actor, garment):
        """Take a garment off -- no longer worn, no longer protecting."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "take_off"):
            return False
        self.eng.remove_edge_unchecked(self._actors[actor], "wears", garment)
        self._request_rule_sweep()
        return True

    def worn(self, actor):
        """What an agent is SEEN wearing -- the kinds of the garments they wear."""
        return [self.tool_kind(g) for g in self.eng.neighbours(self._actors[actor], "wears")]

    def garment_colour(self, garment):
        return self.eng.node(garment)["attrs"].get("colour", "")

    def expose(self, *, cold=0.0, wet=0.0):
        """The weather turns cold/wet -- the town's exposure. cl_chill turns it into each resident's
        chill/soaked AFTER their clothes take their share."""
        self.eng.set_attr(self._town, "cold", float(cold))
        self.eng.set_attr(self._town, "wet", float(wet))
        self._request_rule_sweep()

    def garment_station(self, garment):
        """How fine a garment is (plain/ordinary/fine) -- from the item data."""
        return self._item_specs.get(self.tool_kind(garment), {}).get("station", "ordinary")
    def dressed_stations(self, actor):
        """The stations of what an agent is seen wearing -- plain (a tradesperson) vs fine (the rich)."""
        return sorted({self.garment_station(g) for g in self.eng.neighbours(self._actors[actor], "wears")})
    def finery(self, actor): return round(float(self.eng.node(self._actors[actor])["attrs"].get("finery", 0.0)), 4)

    def warmth(self, actor):  return round(float(self.eng.node(self._actors[actor])["attrs"].get("warmth", 0.0)), 4)
    def rain_cover(self, actor): return round(float(self.eng.node(self._actors[actor])["attrs"].get("rain_cover", 0.0)), 4)
    def chill(self, actor):   return round(float(self.eng.node(self._actors[actor])["attrs"].get("chill", 0.0)), 4)
    def soaked(self, actor):  return round(float(self.eng.node(self._actors[actor])["attrs"].get("soaked", 0.0)), 4)

    def busy(self, actor): return float(self.eng.node(self._actors[actor])["attrs"]["busy"]) == 1.0

    # ---------------------------------------------------- one resolution rule (Phase 050)
    def _attempt_verb(self, actor, verb, target, with_kind=None, intensity=1.0):
        """An attempt (Phase 050): a verb from VERBS, a target, a held tool and an intensity.

        The checks that refuse an attempt run here, before the action slot is claimed, so a refused attempt costs
        nothing: a malformed value, a verb with no physics (unsupported), an unknown or out-of-reach target, a
        broken target, a lock that is not there or already open, and a tool the actor does not hold (no_tool).
        Anything else is enacted, however unwise: the world charges for it and reports what it saw. A target is a
        container for damage and open, and a physical object on the ground for displace (Phase 050b)."""
        if not isinstance(verb, str) or verb == "":
            return self._refuse("malformed")
        spec = self.E.VERBS.get(verb)
        if spec is None or spec.get("primitive") not in ("damage", "open", "displace") \
                or spec.get("implemented") is False:
            return self._refuse("unsupported")
        if spec.get("route") == "throw":
            # Phase 040: the throw verb is the throw action (it takes the object, the target and the intensity).
            return self.major_action(actor, "throw", target=target, with_kind=with_kind, intensity=intensity)
        name = self._as_key(target)
        if name is None:
            return self._refuse("malformed")
        if spec["primitive"] == "displace":
            return self._displace_verb(actor, verb, spec, name, with_kind, intensity)
        if name not in self._containers:
            return self._refuse("unknown_target")
        node = self._containers[name][0]
        attrs = self.eng.node(node)["attrs"]
        cell = self.container_position(name)
        if cell is not None and self.actor_position(actor) != cell:
            return self._refuse("not_in_reach")
        if float(attrs.get("destroyed", 0.0)) == 1.0:
            return self._refuse("destroyed")
        if spec["primitive"] == "open":
            if float(attrs.get("lock_id", 0.0)) <= 0.0:
                return self._refuse("no_lock")
            if float(attrs.get("locked", 0.0)) != 1.0:
                return self._refuse("already_unlocked")
        tool = None
        if with_kind is not None:
            kind = self._as_key(with_kind)
            if kind is None:
                return self._refuse("malformed")
            # Phase 049: a named tool the actor does not hold is not a refusal; the attempt uses bare hands.
            tool = self._held_tool(actor, kind)
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or math.isnan(float(intensity)):
            return self._refuse("malformed")
        return self._enact_attempt(actor, self._container_plan(actor, verb, spec, name, tool, float(intensity)))

    def _enact_attempt(self, actor, plan):
        """Enact a planned attempt, applying the slot rule of Phase 029 (item 5).

        An attempt whose cost share (stamina share, with intensity) is below slot_above leaves the actor's action
        slot unspent, so it can run after a major action this turn. A costlier one claims the slot as usual, and
        is refused with slot_used when the slot is already spent."""
        if float(plan["share"]) < float(self.E.RESOLUTION["slot_above"]):
            return self._run_attempt(actor, plan)
        return self._claimed_attempt(actor, "attempt", lambda: self._run_attempt(actor, plan))

    def _capability_terms(self, actor, spec, tool, requested, target_material):
        """The capability terms every attempt shares (Phase 050): the intensity applied (clamped to the ceiling,
        which the speed factor and health lower), force, technique, fit, and the tool's kind. The fit is the tool's
        fitness for the verb's work on the target's material (Phase 048); bare hands fit at hands_fit."""
        rs = self.E.RESOLUTION
        body = self.eng.node(self._bodies[actor])["attrs"]
        speed = self.speed_factor(actor)
        ceiling = float(rs["max_intensity"]) * speed * self.health(actor)
        from worlds import resolution as R
        applied, clamped = R.intensity_applied(requested, rs["max_intensity"], ceiling)
        stage = str(self.eng.node(self._actors[actor])["attrs"].get("life_stage", "adult"))
        force = (self.effective_strength(actor) * float(body.get("size", 1.0))
                 * float(self.E.CONTEST["life_stage_force"].get(stage, 1.0)) * speed)
        skill = spec.get("skill")
        technique = 1.0 if skill is None else R.technique_term(self.effective_skill(actor, skill),
                                                               rs["technique_floor"])
        tool_kind = "" if tool is None else str(self.eng.node(tool)["attrs"].get("kind", ""))
        target_hardness = float(self.E.MATERIALS[target_material]["hardness"])
        fit, row_effort = self._tool_fit(tool, str(spec.get("work", "")), target_hardness, None)
        return {"applied": applied, "clamped": clamped, "force": force, "technique": technique, "fit": fit,
                "effort": row_effort, "tool_kind": tool_kind}

    def _resolve_terms(self, terms, spec, demand):
        """One resolution step for the terms and a demand. Returns (step, share): the step's outputs, and the cost
        share with intensity (the stamina share times intensity^k), which the trivial and slot rules read."""
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        step = R.resolve_step({
            "force": terms["force"], "technique": terms["technique"], "fit": terms["fit"],
            "team": rs["neutral_team"], "conditions": rs["neutral_conditions"],
            "intensity": terms["applied"], "demand": demand,
            "cap_rate": rs["attempt_cap_rate"], "exponent": rs["progress_exponent"],
            "base_cost": rs["base_cost"], "floor": rs["floor"], "effort_cap": rs["effort_cap"],
            "k": rs["k"], "i_safe": rs["i_safe"], "m": rs["m"],
        })
        share = float(step["cost_share"]) * float(terms["applied"]) ** float(rs["k"])
        return step, share

    def _container_plan(self, actor, verb, spec, name, tool, requested):
        """The plan of a damage or open attempt on a container: capability, demand, and what the target is made of."""
        rs = self.E.RESOLUTION
        node = self._containers[name][0]
        attrs = self.eng.node(node)["attrs"]
        if spec["primitive"] == "damage":
            target_material = (self._item_specs.get(str(attrs.get("kind", "")), {}).get("material")
                               or rs["default_material"])
        else:
            target_material = rs["lock_material"]
        terms = self._capability_terms(actor, spec, tool, requested, target_material)
        if spec["primitive"] == "damage":
            condition = float(attrs.get("structure", 1.0))
            demand = float(self.E.MATERIALS[target_material]["toughness"]) * condition
        else:
            condition = float(attrs.get("lock_condition", 1.0))
            demand = float(attrs.get("lock_strength", 1.0)) * condition
        step, share = self._resolve_terms(terms, spec, demand)
        return {"primitive": spec["primitive"], "verb": verb, "name": name, "node": node, "tool": tool,
                "terms": terms, "step": step, "share": share, "demand": demand, "condition": condition,
                "material": self.E.MATERIALS[target_material], "requested": requested, "actor": actor}

    def _run_attempt(self, actor, plan):
        """One resolution step of an enacted attempt. Returns True: an attempt that makes no progress is still enacted.

        Damage and open lower the target's condition by the step's progress (fragile material faster). A container
        that breaks spills its contents on its cell. A displace attempt moves the object (see _run_displace).
        Tool wear, stamina (free below trivial_below), strain and noise follow. Nothing here is random."""
        if plan["primitive"] == "displace":
            return self._run_displace(actor, plan)
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        name, node = plan["name"], plan["node"]
        attrs = self.eng.node(node)["attrs"]
        step, terms, mat = plan["step"], plan["terms"], plan["material"]
        condition = plan["condition"]
        progress = float(step["progress"])
        # The target's wear: its condition falls by progress, faster for fragile material.
        loss = float(rs["damage_per_attempt"]) * progress * (0.5 + float(mat["fragility"]))
        outcome = "no_progress"
        if plan["primitive"] == "damage":
            after = max(0.0, condition - loss)
            self.eng.set_attr(node, "structure", after)
            if after <= 0.0:
                self.eng.set_attr(node, "destroyed", 1.0)
                outcome = "broke"
                self._spill_contents(name, actor)
            elif loss > 0.0:
                outcome = "damaged"
        else:
            after = max(0.0, condition - loss)
            self.eng.set_attr(node, "lock_condition", after)
            done = float(attrs.get("lock_progress", 0.0)) + progress
            if after <= 0.0:
                self.eng.set_attr(node, "locked", 0.0)
                outcome = "broke_lock"
            elif done >= 1.0:
                self.eng.set_attr(node, "locked", 0.0)
                self.eng.set_attr(node, "lock_progress", 0.0)
                outcome = "opened"
            else:
                self.eng.set_attr(node, "lock_progress", done)
                if progress > 0.0:
                    outcome = "progress"
        self._finish_attempt(actor, plan, outcome, progress, condition - after)
        return True

    def _finish_attempt(self, actor, plan, outcome, progress, damage, moved=0):
        """What every enacted attempt leaves behind: tool wear, stamina, strain (an accident at the limit), noise
        for a loud (damage or open) attempt, and the actor's record."""
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        tool, tool_kind, step, applied = plan["tool"], plan["terms"]["tool_kind"], plan["step"], plan["terms"]["applied"]
        mat, fit = plan["material"], plan["terms"]["fit"]
        # The tool's wear: rises with intensity, with a poor fit, and with a material harder than the tool's.
        if tool is not None:
            tool_material = self._item_specs.get(tool_kind, {}).get("material")
            tool_hardness = float(self.E.MATERIALS[tool_material]["hardness"]) if tool_material in self.E.MATERIALS else 0.0
            gap = max(0.0, float(mat["hardness"]) - tool_hardness)
            wear = R.tool_wear(rs["tool_wear"], applied, fit, rs["mismatch_wear"], float(rs["hardness_wear"]) * gap)
            self._wear_tool(tool, wear)
        # A trivial attempt (cost share below trivial_below, Phase 029) spends no stamina. The tool's effort (Phase 048)
        # multiplies it: a row for a verb may cost more than the normal stroke.
        if plan["share"] >= float(rs["trivial_below"]):
            self._spend_attempt_stamina(actor, float(step["stamina"]) * float(plan["terms"].get("effort", 1.0)), applied)
        # Overexertion and the rest of the strain build up; a full strain is an accident.
        self._accrue_strain(actor, float(step["strain"]))
        if plan["primitive"] != "displace":
            self._publish_noise(actor, plan["verb"], plan["name"],
                                R.noise_radius(rs["noise_base"], applied, mat["noise"]))
        self._record_attempt(actor, plan["verb"], plan["name"], tool_kind, plan["requested"], applied,
                             plan["terms"]["clamped"], progress, damage, outcome, moved=moved)

    def _spill_contents(self, name, actor):
        """A container broken by an attempt drops its contents on its cell as dropped stock (Phase 050b).

        Each content pile's quantity moves to a dropped-stock pile where the container stands (where the actor
        stands, when the container is held and so has no cell). The pile is physical and visible; no resident
        is given the goods."""
        spilled = []
        for kind, stock in self._containers[name][1].items():
            qty = float(self.eng.node(stock)["attrs"].get("qty", 0.0))
            if qty <= 0.0:
                continue
            self._drop_stock(actor, kind, qty)
            self.eng.set_attr(stock, "qty", 0.0)
            spilled.append((kind, qty))
        return spilled

    def _displace_verb(self, actor, verb, spec, name, with_kind, intensity):
        """A displace attempt (Phase 050b): push, pull or drag a physical object on the ground.

        The object must be on the ground (location world) with a cell, within reach: a push needs the object next to
        the actor, a pull or drag within two cells. Refused before the slot is claimed: unknown target, an object
        that is not movable, out of reach, a tool named but not held, and a malformed intensity."""
        if name not in self._physical_objects:
            return self._refuse("unknown_target")
        node = self._physical_objects[name]
        attrs = self.eng.node(node)["attrs"]
        kind = str(attrs.get("kind", ""))
        if "mass" in attrs:
            mass = float(attrs["mass"])
        elif kind in self._item_specs:
            mass = float(self.item_weight(kind))   # the ITEMS weight, in the pack's weight units
        else:
            return self._refuse("unsupported")
        if self._physical_object_locations.get(name, "world") != "world":
            return self._refuse("not_in_reach")
        cell = self._physical_location_cell(name)
        here = self.actor_position(actor)
        if cell is None or here is None:
            return self._refuse("not_in_reach")
        dx, dy = cell[0] - here[0], cell[1] - here[1]
        gap = max(abs(dx), abs(dy))
        reach = 1 if verb == "push" else 2
        if gap < 1 or gap > reach:
            return self._refuse("not_in_reach")
        tool = None
        if with_kind is not None:
            tool_kind = self._as_key(with_kind)
            if tool_kind is None:
                return self._refuse("malformed")
            tool = self._held_tool(actor, tool_kind)     # Phase 049: no held tool means bare hands, not a refusal
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or math.isnan(float(intensity)):
            return self._refuse("malformed")
        # Push drives the object away from the actor; pull and drag draw it toward the actor.
        away = (self._sign(dx), self._sign(dy))
        direction = away if verb == "push" else (-away[0], -away[1])
        plan = self._displace_plan(actor, verb, spec, name, tool, float(intensity), mass, cell, here, direction)
        return self._enact_attempt(actor, plan)

    @staticmethod
    def _sign(value):
        return (value > 0) - (value < 0)

    def _displace_plan(self, actor, verb, spec, name, tool, requested, mass, cell, here, direction):
        """The plan of a displace attempt: the demand is the load over the ground (mass in weight units over the
        reference push, times the ground's friction, the terrain's move time), and the capability is the usual one."""
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        terms = self._capability_terms(actor, spec, tool, requested, rs["default_material"])
        friction = float(self.terrain_state(cell)["move_time"])
        demand = R.friction_demand(mass, rs["push_mass_unit"], friction)
        step, share = self._resolve_terms(terms, spec, demand)
        return {"primitive": "displace", "verb": verb, "name": name, "node": self._physical_objects[name],
                "tool": tool, "terms": terms, "step": step, "share": share, "demand": demand, "condition": 1.0,
                "material": self.E.MATERIALS[rs["default_material"]], "requested": requested, "actor": actor,
                "cell": tuple(cell), "here": tuple(here), "direction": direction}

    def _run_displace(self, actor, plan):
        """Slide the object by the surplus force: floor(surplus x push_cells_per_surplus) cells, at most
        push_max_cells, where the surplus is the capability left over after the demand. It stops at a cell the
        ground does not allow (speed 0), and never enters the actor's cell."""
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        node = plan["node"]
        surplus = max(0.0, float(plan["step"]["capability"]) - float(plan["demand"]))
        wanted = R.push_cells(surplus, rs["push_cells_per_surplus"], rs["push_max_cells"])
        dx, dy = plan["direction"]
        pos, moved = plan["cell"], 0
        for _ in range(wanted):
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt not in self._map_cells or nxt == plan["here"]:
                break
            if float(self.terrain_state(nxt)["speed"]) <= 0.0:
                break
            pos, moved = nxt, moved + 1
        if moved:
            self.eng.set_attr(node, "cell", [int(pos[0]), int(pos[1])])
        outcome = "moved" if moved else "stuck"
        self._finish_attempt(actor, plan, outcome, 0.0, 0.0, moved=moved)
        return True

    def _spend_attempt_stamina(self, actor, amount, applied):
        """Spend an attempt's stamina through an Effort node, as rest does. The hunger scaling and reserve floor
        of the exerted branch apply (Phase 022)."""
        if amount <= 0.0:
            return
        effort = self.eng.add_node("Effort", {"uses_strength": 0.0, "uses_stamina": 1.0,
                                              "intensity": float(applied), "stamina_cost": float(amount),
                                              "terrain": "", "terrain_speed": 1.0,
                                              "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "exerted", effort)
        self._request_rule_sweep()

    def _publish_noise(self, actor, verb, name, radius):
        """A loud attempt is an event that every awake resident within the hearing radius observes (Phase 028).
        The radius is the attempt's loudness in cells, through speech_radius (so the loudness switch applies)."""
        reach = self.speech_radius(radius)
        event = self.create_event("noise", subject=str(name), detail=f"a {verb} at {name} was heard",
                                  severity=min(1.0, float(radius) / 10.0))
        here = self.actor_position(actor)
        if here is None:
            return event
        for other in self._actors:
            if other == actor or not self.is_alive(other) or self._sleep_code(other) is not None:
                continue
            there = self.actor_position(other)
            if there is None:
                continue
            if max(abs(here[0] - there[0]), abs(here[1] - there[1])) <= reach:
                self.observe_event(other, event)
        return event

    def _record_attempt(self, actor, verb, name, tool_kind, requested, applied, clamped, progress, damage, outcome,
                        moved=0):
        """What the actor sees of its own attempt: the applied intensity (and whether it was clamped), the progress
        and the damage, and the outcome. Never the capability or the demand. Also counted by verb and outcome."""
        node = self._actors[actor]
        attrs = self.eng.node(node)["attrs"]
        self.eng.set_attr(node, "last_attempt", {
            "turn": int(self._turn), "verb": str(verb), "target": str(name), "tool": str(tool_kind),
            "requested_intensity": float(requested), "applied_intensity": round(float(applied), 4),
            "clamped": bool(clamped), "progress": round(float(progress), 4), "damage": round(float(damage), 4),
            "cells_moved": int(moved), "outcome": str(outcome)})
        counts = {key: dict(value) for key, value in attrs.get("attempt_counts", {}).items()}
        by_outcome = counts.setdefault(str(verb), {})
        by_outcome[str(outcome)] = by_outcome.get(str(outcome), 0) + 1
        self.eng.set_attr(node, "attempt_counts", counts)

    def attempt_counts(self):
        """Attempts over all residents, counted by verb and then by outcome (Phase 050)."""
        totals = {}
        for name in self._actors:
            for verb, outcomes in self.eng.node(self._actors[name])["attrs"].get("attempt_counts", {}).items():
                for outcome, count in outcomes.items():
                    by_outcome = totals.setdefault(verb, {})
                    by_outcome[outcome] = by_outcome.get(outcome, 0) + int(count)
        return totals

    def last_attempt(self, actor):
        """The actor's own most recent attempt, as the actor observed it, or None."""
        value = self.eng.node(self._actor(actor))["attrs"].get("last_attempt")
        return None if value is None else dict(value)

    # ---------------------------------------------------- joint actions (Phase 047)
    def joint_actions_on(self):
        """The joint_actions switch (physical_subsystems). Off, no joint option is published and no joint act runs."""
        return bool(self.physical_subsystems.get("joint_actions", False))

    def _joint_ready(self, actor):
        """A resident who can take part in a joint task now: alive, awake, and not on a timed job."""
        return (actor in self._actors and self.is_alive(actor) and self._sleep_code(actor) is None
                and not self.busy(actor))

    def _within(self, actor, cell, reach):
        """Whether a resident stands within `reach` cells of `cell` (Chebyshev, the world's grid distance)."""
        from worlds import joint as J
        here = self.actor_position(actor)
        return here is not None and cell is not None and J.chebyshev(here, cell) <= int(reach)

    def _joint_check(self, actor, cell, reach):
        """Why a proposing resident cannot take part in a joint act, or None when it can (Phase 047).

        Asleep, collapsed and passed-out residents are refused with their sleep code. A dead resident, or one on a
        timed job, cannot act (not_possible). A resident whose action slot is spent cannot claim it (slot_used). A
        resident out of reach of the cell is not_in_reach."""
        if actor not in self._actors or not self.is_alive(actor):
            return "not_possible"
        code = self._sleep_code(actor)
        if code is not None:
            return code
        if self.busy(actor):
            return "not_possible"
        if float(self.eng.node(self._actors[actor])["attrs"].get("major_action_used", 0.0)) == 1.0:
            return "slot_used"
        if cell is not None and not self._within(actor, cell, reach):
            return "not_in_reach"
        return None

    def _member_force(self, actor):
        """A member's force in a joint act: the terms the core's force term uses (Phase 050), without intensity."""
        body = self.eng.node(self._bodies[actor])["attrs"]
        stage = str(self.eng.node(self._actors[actor])["attrs"].get("life_stage", "adult"))
        return (self.effective_strength(actor) * float(body.get("size", 1.0))
                * float(self.E.CONTEST["life_stage_force"].get(stage, 1.0)) * self.speed_factor(actor))

    def _joint_outcomes(self, names, applied, codes, publish):
        """Each named resident's outcome: applied, or the code that refused it. Returns {resident: applied}.

        `publish` is False inside another attempt, which publishes its own outcome; then a refusal sets the code."""
        results = {}
        for name in names:
            ok = name in applied
            results[name] = ok
            if publish:
                self._publish_outcome(name, "joint", ok, None if ok else codes.get(name, "not_possible"))
            elif not ok:
                self._refusal_code = codes.get(name, "not_possible")
        return results

    def _record_joint(self, name, task, target, joined, needed, outcome):
        """What a joint act tells each member: how many took part, how many the act needs, and what happened."""
        self.eng.set_attr(self._actors[name], "last_joint", {
            "turn": int(self._turn), "task": str(task), "target": str(target), "joined": int(joined),
            "needed": int(needed), "outcome": str(outcome)})

    def last_joint(self, actor):
        """The resident's own most recent joint act, as it observed it (joined k of needed), or None."""
        value = self.eng.node(self._actor(actor))["attrs"].get("last_joint")
        return None if value is None else dict(value)

    def _joint_event(self, kind, cell, subject, detail, severity):
        """A joint act is a physical event that every awake resident with sight of the site observes (Phase 028)."""
        event = self.create_event(kind, subject=str(subject), detail=detail, severity=severity)
        if cell is None:
            return event
        sight = int(self.E.HEARING["sight_range"])
        from worlds import joint as J
        for other in self._actors:
            where = self.actor_position(other)
            if (where is not None and self.is_alive(other) and self._sleep_code(other) is None
                    and J.chebyshev(where, cell) <= sight):
                self.observe_event(other, event)
        return event

    def _queue_effort(self, actor, amount, intensity, uses_strength=0.0):
        """Queue stamina a resident spends through an Effort node. Nothing runs here, so it is safe inside a tick."""
        if float(amount) <= 0.0:
            return
        effort = self.eng.add_node("Effort", {"uses_strength": float(uses_strength), "uses_stamina": 1.0,
                                              "intensity": float(intensity), "stamina_cost": float(amount),
                                              "terrain": "", "terrain_speed": 1.0,
                                              "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "exerted", effort)

    def _carry_cell(self, name):
        """The cell of a physical object lying on the ground, or None when it is held or in a container."""
        if self._physical_object_locations.get(name, "world") != "world":
            return None
        cell = self._physical_location_cell(name)
        return None if cell is None else tuple(cell)

    def _carry_load(self, name):
        """A physical object's load in ITEMS weight units: its own mass, or its kind's weight. None when neither."""
        attrs = self.eng.node(self._physical_objects[name])["attrs"]
        if "mass" in attrs:
            return float(attrs["mass"])
        kind = str(attrs.get("kind", ""))
        return float(self.item_weight(kind)) if kind in self._item_specs else None

    def _joint_steps(self, cell):
        """The steps a load on `cell` may take: each neighbouring map cell the ground lets through and no resident
        stands on, in sorted order. A load cannot be pushed into the people carrying it."""
        occupied = {self.actor_position(name) for name in self._actors if self.is_alive(name)}
        steps = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nxt = (cell[0] + dx, cell[1] + dy)
                if ((dx, dy) != (0, 0) and nxt in self._map_cells and nxt not in occupied
                        and self.terrain_state(nxt)["speed"] > 0.0):
                    steps.append([dx, dy])
        return steps

    def _carry_options(self, actor):
        """Joint carry options: a load within reach that one person cannot lift (needs at least two)."""
        from worlds import joint as J
        task = self.E.JOINT_TASKS["carry"]
        reach = int(task["reach"])
        options = []
        for name in sorted(self._physical_objects):
            cell = self._carry_cell(name)
            load = self._carry_load(name)
            if cell is None or load is None or not self._within(actor, cell, reach):
                continue
            needs = J.members_needed(self._member_force(actor), load / float(task["load_unit"]),
                                     task["max_members"], task["coordination_loss"], 0.0, task["skill_relief"])
            if needs is None or needs < 2:
                continue
            steps = self._joint_steps(cell)
            if not steps:
                continue
            present = [other for other in self._actors if other != actor and self._joint_ready(other)
                       and self._within(other, cell, reach)]
            options.append({"action": "joint", "task": "carry", "object": name, "toward": steps,
                            "needs": int(needs), "present": len(present), "max": int(task["max_members"]),
                            "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        return options

    def _job_recipe_name(self, job):
        runs = self.eng.neighbours(job, "runs")
        return str(self.eng.node(runs[0])["attrs"].get("name", "")) if runs else ""

    def _crew_members(self, job):
        """The helpers who joined a crewed job and still work it: awake, free, and on the worker's cell."""
        ja = self.eng.node(job)["attrs"]
        worker = str(ja.get("canonical_actor", ""))
        if worker not in self._actors:
            return []
        here = self.actor_position(worker)
        return [helper for helper in (ja.get("crew") or []) if helper in self._actors and helper != worker
                and self._joint_ready(helper) and self.actor_position(helper) == here]

    def _crew_factor(self, job):
        """The progress multiplier of a timed job from its crew (Phase 047). 1.0 with the switch off or no crew field."""
        if not self.joint_actions_on():
            return 1.0
        from worlds import joint as J
        recipe = self._job_recipe_name(job)
        row = self._recipe_specs.get(recipe, {})
        crew = row.get("crew")
        if not crew:
            return 1.0
        task = self.E.JOINT_TASKS["crew"]
        worker = str(self.eng.node(job)["attrs"].get("canonical_actor", ""))
        skill = min(1.0, max(0.0, float(self.recipe_skill_level(worker, row)))) if worker in self._actors else 0.0
        members = min(int(crew["max"]), 1 + len(self._crew_members(job)))
        return J.crew_factor(members, task["crew_penalty"], skill, task["coordination_loss"], task["skill_relief"])

    def _crew_spend(self, job, own):
        """Each helper on a crewed job pays stamina for the tick in step with the worker's own labour (Phase 047)."""
        if own <= 0.0 or not self.joint_actions_on():
            return
        helpers = self._crew_members(job)
        if not helpers:
            return
        ja = self.eng.node(job)["attrs"]
        ticks, total = float(ja.get("stamina_ticks", 0.0)), float(ja.get("stamina_total", 0.0))
        if ticks <= 0.0 or total <= 0.0:
            return
        amount = total / ticks * own * float(ja.get("effort_mult", 1.0))
        for helper in helpers:
            self._queue_effort(helper, amount, min(1.0, amount), float(ja.get("uses_strength", 0.0)))

    def _crew_options(self, actor):
        """Crew options: a timed job whose worker stands on the resident's cell, whose recipe asks for more people,
        and which has room. `needs` is the workers the job still lacks to reach its minimum."""
        here = self.actor_position(actor)
        if here is None:
            return []
        options = []
        for job in sorted(self.eng.nodes("Job")):
            ja = self.eng.node(job)["attrs"]
            if float(ja.get("complete", 0.0)) == 1.0 or float(ja.get("remaining", 0.0)) <= 0.0:
                continue
            worker = str(ja.get("canonical_actor", ""))
            if worker == actor or worker not in self._actors or self.actor_position(worker) != here:
                continue
            recipe = self._job_recipe_name(job)
            crew = self._recipe_specs.get(recipe, {}).get("crew")
            if not crew:
                continue
            crewing = self._crew_members(job)
            count = 1 + len(crewing)
            if count >= int(crew["max"]) or actor in crewing:
                continue
            present = [other for other in self._actors if other not in (actor, worker)
                       and self._joint_ready(other) and self.actor_position(other) == here]
            options.append({"action": "joint", "task": "crew", "worker": worker, "recipe": recipe,
                            "needs": max(0, int(crew["min"]) - count), "present": len(present),
                            "max": int(crew["max"]), "kind": "", "trade": "", "target": "", "score": 0.0})
        return options

    def enact_joint(self, task, participants):
        """Resolve one joint act for the residents who proposed it (Phase 047). Returns {resident: applied}.

        `task` names the act: {"task": "carry", "object": name, "toward": [dx, dy]} or {"task": "crew", "worker": name}.
        Each proposing resident takes part, or is left out with a REFUSAL_REASONS code (asleep, collapsed, out of
        reach, busy, slot_used). An act with fewer people than it needs still runs and fails physically: a load stays
        where it is, and a crewed job crawls. The result does not depend on the order of `participants`."""
        names = sorted({name for name in participants if isinstance(name, str) and name in self._actors})
        if not names:
            return {}
        publish = not self._outcome_open
        kind = task.get("task") if isinstance(task, dict) else None
        if not self.joint_actions_on() or kind not in ("carry", "crew"):
            return self._joint_outcomes(names, set(), {name: "unsupported" for name in names}, publish)
        if kind == "carry":
            return self._enact_carry(task, names, publish)
        return self._enact_crew(task, names, publish)

    def _enact_carry(self, task, names, publish):
        """A group lifts a load one cell along `toward` if its summed capability reaches the load (Phase 047)."""
        from worlds import joint as J
        from worlds import resolution as R
        spec = self.E.JOINT_TASKS["carry"]
        rs = self.E.RESOLUTION
        obj, steps = self._as_key(task.get("object")), task.get("toward")
        cell = self._carry_cell(obj) if obj in self._physical_objects else None
        load = self._carry_load(obj) if cell is not None else None
        if cell is None or load is None:
            return self._joint_outcomes(names, set(), {name: "unknown_target" for name in names}, publish)
        if not (isinstance(steps, (list, tuple)) and len(steps) == 2 and tuple(steps) != (0, 0)
                and all(isinstance(s, int) and not isinstance(s, bool) and s in (-1, 0, 1) for s in steps)):
            return self._joint_outcomes(names, set(), {name: "malformed" for name in names}, publish)
        reach = int(spec["reach"])
        group, codes = [], {}
        for name in names:
            code = self._joint_check(name, cell, reach)
            if code is None:
                group.append(name)
            else:
                codes[name] = code
        if not group:
            return self._joint_outcomes(names, set(), codes, publish)
        for name in group:
            self._claim_major_action(name, "joint")
        forces = [self._member_force(name) for name in group]
        total, team = J.team_term(forces, spec["coordination_loss"], 0.0, spec["skill_relief"])
        demand = load / float(spec["load_unit"])
        # The core's rule (Phase 050), with the group's summed force and the team term from joint.team_term.
        step = R.resolve_step({
            "force": total, "technique": 1.0, "fit": 1.0, "team": team, "conditions": rs["neutral_conditions"],
            "intensity": 1.0, "demand": demand, "cap_rate": rs["attempt_cap_rate"],
            "exponent": rs["progress_exponent"], "base_cost": rs["base_cost"], "floor": rs["floor"],
            "effort_cap": rs["effort_cap"], "k": rs["k"], "i_safe": rs["i_safe"], "m": rs["m"]})
        pace = J.carry_pace(R.rho(step["capability"], demand), spec["pace_cap"])
        cells_of_group = [self.actor_position(name) for name in group]
        node = self._physical_objects[obj]
        pos, moved = cell, 0
        for _ in range(pace):
            nxt = (pos[0] + int(steps[0]), pos[1] + int(steps[1]))
            if nxt not in self._map_cells or nxt in cells_of_group or self.terrain_state(nxt)["speed"] <= 0.0:
                break
            pos, moved = nxt, moved + 1
        if moved:
            self.eng.set_attr(node, "cell", [int(pos[0]), int(pos[1])])
            self.eng.set_attr(node, "carriers", list(group))
            # The carriers walk with the load: each stands on the cell the load left, one step behind it.
            behind = (pos[0] - int(steps[0]), pos[1] - int(steps[1]))
            for name in group:
                self._move_actor_to(name, behind)
        outcome = "moved" if moved else "stuck"
        # Each member pays its share of the summed force: stamina, and strain (an accident at the strain limit).
        for name, force in zip(group, forces):
            share = force / total if total > 0.0 else 1.0 / len(group)
            self._queue_effort(name, float(step["stamina"]) * share, 1.0)
            self._accrue_strain(name, float(step["strain"]) * share)
        self._request_rule_sweep()
        needed = J.members_needed(total / len(group), demand, spec["max_members"], spec["coordination_loss"], 0.0,
                                  spec["skill_relief"])
        needed = int(spec["max_members"]) if needed is None else int(needed)
        for name in group:
            self._record_joint(name, "carry", obj, len(group), needed, outcome)
        self._joint_event("joint", cell, obj, f"{len(group)} people tried to move {obj}; it "
                          f"{'moved' if moved else 'stayed where it was'}", 0.1)
        return self._joint_outcomes(names, set(group), codes, publish)

    def _enact_crew(self, task, names, publish):
        """Residents join a worker's crewed job. They pay for their share of each tick once they have joined."""
        spec = self.E.JOINT_TASKS["crew"]
        worker = self._as_key(task.get("worker"))
        job = self._job_of(worker) if worker in self._actors else None
        if job is None or float(self.eng.node(job)["attrs"].get("remaining", 0.0)) <= 0.0:
            return self._joint_outcomes(names, set(), {name: "not_possible" for name in names}, publish)
        recipe = self._job_recipe_name(job)
        crew = self._recipe_specs.get(recipe, {}).get("crew")
        if not crew:
            return self._joint_outcomes(names, set(), {name: "unsupported" for name in names}, publish)
        here = self.actor_position(worker)
        crewing = self._crew_members(job)
        room = int(crew["max"]) - (1 + len(crewing))
        group, codes = [], {}
        for name in names:
            if name == worker or name in crewing:
                codes[name] = "not_possible"
                continue
            code = self._joint_check(name, here, 0)
            if code is not None:
                codes[name] = code
            elif len(group) >= room:
                codes[name] = "not_possible"
            else:
                group.append(name)
        for name in group:
            self._claim_major_action(name, "joint")
        if group:
            already = list(self.eng.node(job)["attrs"].get("crew") or [])
            self.eng.set_attr(job, "crew", sorted(set(already + group)))
            for name in group:
                self._record_joint(name, "crew", worker, len(group), int(crew["min"]), "joined")
            self._joint_event("joint", here, worker, f"{len(group)} joined {worker} at {recipe}", 0.0)
        return self._joint_outcomes(names, set(group), codes, publish)

    def _settle_joint_loads(self):
        """A load carried this turn stays up only while its carriers hold it. One who collapsed, slept or left reach
        before the turn's tick ends drops it where it lies (event load_dropped). Nothing else changes."""
        if not self.joint_actions_on():
            return
        for name in sorted(self._physical_objects):
            node = self._physical_objects[name]
            carriers = list(self.eng.node(node)["attrs"].get("carriers") or [])
            if not carriers:
                continue
            self.eng.set_attr(node, "carriers", [])
            cell = self._carry_cell(name)
            held = cell is not None and all(self.is_alive(c) and self._sleep_code(c) is None
                                            and self._within(c, cell, self.E.JOINT_TASKS["carry"]["reach"])
                                            for c in carriers)
            if not held:
                self._joint_event("load_dropped", cell, name, f"{name} fell: someone holding it could not hold on",
                                  0.2)

    def _job_of(self, actor):
        """The actor's timed job (its `on_job` edge), or None."""
        if actor not in self._actors:
            return None
        jobs = self.eng.neighbours(self._actors[actor], "on_job")
        return jobs[0] if jobs else None

    def _job_away(self, job):
        """Whether a job's worker stands off the cell where the job started (Phase 023). A job opened
        without a position (no cell to return to) is never paused."""
        ja = self.eng.node(job)["attrs"]
        start = ja.get("start_cell")
        actor = str(ja.get("canonical_actor", ""))
        # Phase 024: a sleeping or collapsed worker is away from the job, so the job pauses the same way.
        if self._sleep_code(actor) is not None:
            return True
        if not start or actor not in self._actors:
            return False
        here = self.actor_position(actor)
        return here is None or tuple(start) != tuple(here)

    def _set_job_paused(self, actor, paused):
        """Publish the paused read-off on the actor node (`job_paused`, 1.0 or 0.0)."""
        if actor not in self._actors:
            return
        node = self._actors[actor]
        value = 1.0 if paused else 0.0
        if float(self.eng.node(node)["attrs"].get("job_paused", 0.0)) != value:
            self.eng.set_attr(node, "job_paused", value)

    def job_paused(self, actor):
        """True while the actor's timed job waits because its worker is not on the job's start cell."""
        job = self._job_of(actor)
        return job is not None and self._job_away(job)

    def job_start_cell(self, actor):
        """The cell the actor's timed job started on, or None when there is no such job."""
        job = self._job_of(actor)
        start = self.eng.node(job)["attrs"].get("start_cell") if job is not None else None
        return tuple(start) if start else None
    def fatigue(self, actor):
        """Read-off of stamina spent (Phase 022): the same as `exertion`. There is no separate accumulator."""
        return self.exertion(actor)

    # ---------------------------------------------- body training and effective stats (Phase 032)
    # Seeds bd_train_strength and bd_train_stamina (use builds the stat) and bd_effective_stats (health scales
    # the stat; the reserve cannot exceed the effective stamina). Constants and the formulas: world_affordances
    # (train_gain, effective_stat). The effort's `intensity` is its stamina cost, capped at 1.
    def effective_strength(self, actor):
        """(str_base + str_train) x health (seed bd_effective_stats). Read by the recipe gate and the contest."""
        return self._effective_body_stat(actor, "str_base", "str_train")

    def effective_stamina(self, actor):
        """(sta_base + sta_train) x health: the stamina capacity the reserve is clamped to and the band reads.
        Phase 036: withdrawal lowers it while alcohol_aftereffects is on."""
        return self._effective_body_stat(actor, "sta_base", "sta_train") * self._withdrawal_stamina_factor(actor)

    def _effective_body_stat(self, actor, base_key, train_key):
        ba = self.eng.node(self._bodies[actor])["attrs"]
        return self.E.effective_stat(float(ba.get(base_key, 1.0)), float(ba.get(train_key, 0.0)), self.health(actor))

    def _train_from_effort(self, body, event):
        """Apply the training rules to one resolved Effort: each stat the effort uses gains train_gain once,
        and the effort is marked done for that stat (str_done, sta_done), as the seed's `where` clauses require."""
        ea = self.eng.node(event)["attrs"]
        ba = self.eng.node(body)["attrs"]
        intensity = float(ea.get("intensity", 0.0))
        for uses, done, base_key, train_key in (("uses_strength", "str_done", "str_base", "str_train"),
                                                ("uses_stamina", "sta_done", "sta_base", "sta_train")):
            if float(ea.get(uses, 0.0)) != 1.0 or float(ea.get(done, 0.0)) == 1.0:
                continue
            base = float(ba.get(base_key, 1.0))
            trained = float(ba.get(train_key, 0.0))
            self.eng.set_attr(body, train_key, trained + self.E.train_gain(base, trained, intensity))
            self.eng.set_attr(body, "stats_dirty", 1.0)
            self.eng.set_attr(event, done, 1.0)

    def _resolve_body_stats(self):
        """bd_effective_stats: strength and stamina are the effective values, and the reserve is clamped to the
        effective stamina. Recomputed on every run (not only when stats_dirty is set), so a health change is seen
        on the next run; the flag is cleared here, as the seed's rule does."""
        for actor, body in self._bodies.items():
            if not self.eng.has_node(body):
                continue
            ba = self.eng.node(body)["attrs"]
            strength = self.effective_strength(actor)
            stamina = self.effective_stamina(actor)
            if float(ba.get("strength", -1.0)) != strength:
                self.eng.set_attr(body, "strength", strength)
            if float(ba.get("stamina", -1.0)) != stamina:
                self.eng.set_attr(body, "stamina", stamina)
            if float(self.eng.node(body)["attrs"].get("stamina_reserve", 1.0)) > stamina:
                self.eng.set_attr(body, "stamina_reserve", stamina)
            if float(ba.get("stats_dirty", 0.0)) != 0.0:
                self.eng.set_attr(body, "stats_dirty", 0.0)

    # ---------------------------------------------- exhaustion, sleep and collapse (Phase 024)
    # The seeded rules are bigville_move_energy (mv_energy_budget, mv_deplete) and bigville_time_sleep
    # (bt_collapse, bt_replenish, bt_wake, bt_decide_sleep). The decision to sleep belongs to the backend;
    # this block only enacts sleep, collapse and wake, and publishes the facts the seeds name.
    # ---------------------------------------------- contested take (Phase 029)
    # A take is a physical contest between two residents on one cell. The world computes the forces, the
    # reaction offer and the outcome; the game asks the holder's backend which reaction it chooses. Nothing
    # here is random, and no ownership, crime or law is attached (the residents' institutions own those).
    # The pending contest is a plain dict held on `self._contest` between the attacker's claim and its
    # resolution, so a human holder's reaction can wait for input.
    def mark_turn_start(self):
        """Record every resident's cell at the start of the turn (the observation a target can have made)."""
        self._ensure_position_index()
        self._turn_start_positions = {name: tuple(pos) for name, pos in self._actor_positions.items()
                                      if pos is not None}

    def contest_pending(self):
        """The pending contest (a plain dict), or None."""
        return self._contest

    def _contest_efficiency(self, skill):
        """Technique discounts a side's share of a load: 1.0 at no skill, min_efficiency at full skill."""
        skill = min(1.0, max(0.0, float(skill)))
        return 1.0 - (1.0 - float(self.E.CONTEST["min_efficiency"])) * skill

    def _contest_share(self, load, own, skill):
        """A side's cost share: the load it bears as a share of its own force, times its efficiency."""
        if load <= 0.0:
            return 0.0
        ratio = 1.0 if own <= 0.0 else min(1.0, float(load) / float(own))
        return ratio * self._contest_efficiency(skill)

    def _contest_side(self, actor):
        """One side's traits: force (strength, size, life stage, exhaustion step), skill and score."""
        ct = self.E.CONTEST
        body = self._bodies.get(actor)
        ba = self.eng.node(body)["attrs"] if body is not None else {}
        aa = self.eng.node(self._actors[actor])["attrs"]
        strength = self.effective_strength(actor)
        size = float(ba.get("size", 1.0))
        life = float(ct["life_stage_force"].get(str(aa.get("life_stage", "adult")), 1.0))
        step = float(self._exhaustion_band(actor)["speed"])
        base_force = max(0.0, strength) * (size ** float(ct["size_exponent"])) * life
        force = base_force * step
        skill = float(self.effective_skill(actor, "fighting"))
        score = force * (1.0 + float(ct["technique_weight"]) * skill)
        # power: the blow's strength without the exhaustion step (Phase 038: a tired blow is weak, not nothing).
        return {"force": force, "skill": skill, "score": score, "reserve": float(ba.get("stamina_reserve", 1.0)),
                "power": base_force * (1.0 + float(ct["technique_weight"]) * skill)}

    def _aware_of(self, attacker, target):
        """Whether the target could see the attacker coming: the attacker stood within sight range of the
        target at the start of the turn. A taker who walked in during the turn was not seen."""
        sight = int(self.E.HEARING["sight_range"])
        starts = self._turn_start_positions
        here = starts.get(attacker, self.actor_position(attacker))
        there = starts.get(target, self.actor_position(target))
        if here is None or there is None:
            return False
        return max(abs(here[0] - there[0]), abs(here[1] - there[1])) <= sight

    def _evade_cell(self, target):
        """The first walkable cell one step from the target (sorted), or None. Evading steps onto it."""
        here = self.actor_position(target)
        if here is None:
            return None
        options = [(here[0] + dx, here[1] + dy) for dx, dy in ((-1, 0), (0, -1), (0, 1), (1, 0))]
        open_cells = [cell for cell in sorted(options) if cell in self._map_cells]
        return open_cells[0] if open_cells else None

    def _contest_offer(self, attacker, target, attacker_side, target_side):
        """Whether the target reacts, how late, and with which options (the world's reaction rules)."""
        ct = self.E.CONTEST
        offer = {"eligible": False, "reason": "", "late": False, "penalty": 1.0, "options": [],
                 "aware": self._aware_of(attacker, target), "evade_cell": None, "slot_free": True}
        if not self.is_alive(target):
            offer["reason"] = "dead"
            return offer
        code = self._sleep_code(target)
        if code is not None:
            offer["reason"] = code
            return offer
        if not offer["aware"]:
            offer["reason"] = "unaware"
            return offer
        situation = 1.0
        if self._job_of(target) is not None:
            situation *= float(ct["busy_factor"])
        if self.carry_state(target)["overloaded"]:
            situation *= float(ct["overloaded_factor"])
        reaction = target_side["score"] * situation
        initiative = attacker_side["score"]
        if reaction + 1e-12 >= initiative:
            late = False
        elif reaction + 1e-12 >= float(ct["reaction_floor"]) * initiative:
            late = True
        else:
            offer["reason"] = "too_slow"
            return offer
        offer["slot_free"] = float(self.eng.node(self._actor(target))["attrs"].get("major_action_used", 0.0)) != 1.0
        resist_share = self._contest_share(attacker_side["force"], target_side["force"], target_side["skill"])
        if not offer["slot_free"] and resist_share >= float(ct["slot_above"]):
            late = True
        offer["eligible"] = True
        offer["late"] = late
        if late:
            offer["penalty"] = float(ct["late_penalty"])
            offer["options"] = [option for option in ct["late_options"]]
        else:
            offer["options"] = ["resist", "brace", "yield"]
            offer["evade_cell"] = self._evade_cell(target)
            if offer["evade_cell"] is not None:
                offer["options"].insert(2, "evade")
        return offer

    def take_begin(self, actor, plan):
        """Start a contested take of `plan`'s goods from `plan["source"]`, a resident on the actor's cell.

        Refusals (no one in reach, nothing held, no room, asleep, slot used) return ``(None, reason)`` and
        claim nothing. Otherwise the actor's major action is claimed and the pending contest, with the
        target's reaction offer, is returned as a plain dict. The caller then resolves it with
        ``take_resolve`` and publishes the outcome with ``take_outcome``."""
        self._contest = None
        if actor not in self._actors:
            return None, "unknown_target"
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return None, sleep_code
        plan = plan if isinstance(plan, dict) else {}
        source = self._as_key(plan.get("source"))
        kind = plan.get("kind")
        amount = self._as_amount(plan.get("amount", 1.0))
        if source is None or kind is None or amount is None:
            return None, "malformed"
        if source in self._shops:
            return None, "wrong_target"
        if source not in self._actors or source == actor:
            return None, "unknown_target" if source not in self._actors else "wrong_target"
        if isinstance(kind, str):
            if amount <= 0.0:
                return None, "malformed"
        elif not self._known_ref(kind):
            return None, "malformed"
        self._refusal_code = None
        if not self._physical_transfer_precheck(source, actor, kind, amount if isinstance(kind, str) else 1.0):
            return None, self._refusal_code or "not_possible"
        attrs = self.eng.node(self._actor(actor))["attrs"]
        before = {"major_action_used": attrs.get("major_action_used", 0.0),
                  "major_action_kind": attrs.get("major_action_kind", ""),
                  "last_major_action": attrs.get("last_major_action", "")}
        if not self._claim_major_action(actor, "take"):
            return None, "slot_used"
        attacker_side = self._contest_side(actor)
        target_side = self._contest_side(source)
        pending = {
            "attacker": str(actor), "target": str(source),
            "kind": kind if isinstance(kind, str) else int(kind),
            "kind_is_item": not isinstance(kind, str),
            "amount": float(amount) if isinstance(kind, str) else 1.0,
            "turn": int(self._turn),
            "witnesses": self._witnesses(actor),
            "slot_before": before, "slot_record": self._turn_actions[actor][-1],
            "attacker_side": attacker_side, "target_side": target_side,
            "offer": self._contest_offer(actor, source, attacker_side, target_side),
            "result": None,
        }
        self._contest = pending
        return pending, None

    def _contest_spend(self, actor, cost):
        """Spend stamina on a contest through the same Effort mechanism movement uses."""
        if cost <= 0.0 or self._bodies.get(actor) is None:
            return
        effort = self.eng.add_node("Effort", {"uses_strength": 0.0, "uses_stamina": 1.0,
                                              "intensity": min(1.0, cost), "stamina_cost": float(cost),
                                              "terrain": "", "terrain_speed": 1.0,
                                              "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "exerted", effort)
        self._request_rule_sweep()

    def _contest_log_practice(self, actor, minutes):
        """Contests are practice in fighting (Phase 012, physical learning, consolidated at period end)."""
        node = self._actors[actor]
        log = dict(self.eng.node(node)["attrs"].get("skill_practice", {}))
        log["fighting"] = float(log.get("fighting", 0.0)) + float(minutes)
        self.eng.set_attr(node, "skill_practice", log)

    def _contest_kind(self, pending):
        """The good as the give path takes it: a good's kind name, or a discrete item's node reference.

        The pending dict keeps a plain int for an item (checkpoint-safe); the node reference is rebuilt here."""
        return NodeRef(pending["kind"]) if pending["kind_is_item"] else pending["kind"]

    def _contest_move(self, pending, handover):
        """Move the goods from the target to the attacker through the give path (conserved, capacity-checked)."""
        self._refusal_code = None
        moved = self._physical_transfer(pending["target"], pending["attacker"], self._contest_kind(pending),
                                        pending["amount"], handover_kind=handover)
        return bool(moved), (None if moved else (self._refusal_code or "not_possible"))

    def _contest_drop(self, pending):
        """The goods fall on the cell, from the target's hands or stock (a narrow margin)."""
        target, kind = pending["target"], self._contest_kind(pending)
        if pending["kind_is_item"]:
            self._drop_discrete_item(target, kind)
        else:
            self._remove_inventory_stock(target, kind, pending["amount"])
            self._drop_stock(target, kind, pending["amount"])

    def take_resolve(self, pending, reaction=None):
        """Resolve a pending take after the target has chosen its reaction (or None for none).

        Returns ``(applied, reason)``: applied is True when the goods changed hands, and reason is a
        REFUSAL_REASONS code otherwise. The full result (outcome, costs, redirection) is kept in
        ``pending["result"]``. A reaction the target was not offered is treated as no reaction."""
        if pending.get("action") == "strike":
            return self.strike_resolve(pending, reaction)
        if pending.get("action") == "throw":
            return self.throw_resolve(pending, reaction)
        if pending.get("action") == "restrain":
            return self.restrain_resolve(pending, reaction)
        if self._contest is pending:
            self._contest = None
        ct = self.E.CONTEST
        attacker, target = pending["attacker"], pending["target"]
        offer = pending["offer"]
        choice = reaction if (offer["eligible"] and reaction in offer["options"]) else None
        A, T = pending["attacker_side"], pending["target_side"]
        base, grip, tw = float(ct["base_cost"]), float(ct["grip"]), float(ct["technique_weight"])
        trivial, slot_above = float(ct["trivial_below"]), float(ct["slot_above"])
        penalty = float(offer["penalty"]) if choice is not None else 1.0
        result = {"reaction": choice or "", "outcome": "", "applied": False, "reason": "",
                  "late": bool(offer["late"]) if choice is not None else False, "redirected": False,
                  "attacker_cost": 0.0, "target_cost": 0.0}
        pending["result"] = result
        if choice == "yield":
            applied, code = self._contest_move(pending, "yield")
            result.update(outcome="yielded", applied=applied, reason=code or "")
            self._contest_practice_after(pending, choice)
            return applied, code
        if choice == "evade":
            share_t = self._contest_share(A["force"], T["force"], T["skill"])
            cost_t = base * share_t if share_t >= trivial else 0.0
            self._contest_spend(target, cost_t)
            self._move_actor_to(target, offer["evade_cell"])
            result.update(outcome="evaded", reason="evaded", target_cost=cost_t)
            self._release_contest_slot(pending)
            self._contest_practice_after(pending, choice)
            return False, "evaded"
        if choice is None:
            brought = grip * T["force"]
            hold = grip * T["force"]
        elif choice == "resist":
            brought = T["force"]
            hold = T["force"] * (1.0 + tw * T["skill"]) * penalty
        else:  # brace: a technique-assisted hold; it bears the push but brings grip x force
            brought = grip * T["force"]
            hold = grip * T["force"] * (1.0 + tw * T["skill"]) * penalty
        att = A["force"] * (1.0 + tw * A["skill"])
        total = att + hold
        margin = 0.0 if total <= 0.0 else (att - hold) / total
        decisive, narrow = float(ct["decisive_margin"]), float(ct["narrow_margin"])
        if margin >= decisive:
            outcome = "completed"
        elif margin >= narrow:
            outcome = "dropped"
        else:
            outcome = "held"
        if outcome == "dropped" and not pending["kind_is_item"] and pending["kind"] == "coin":
            outcome = "held"          # coin cannot fall on the cell in this model
        if (outcome == "held" and margin <= -decisive and choice in ("resist", "brace")
                and T["skill"] - A["skill"] >= float(ct["redirect_gap"])):
            outcome = "redirected"
            result["redirected"] = True
        share_a = self._contest_share(brought, A["force"], A["skill"])
        share_t = self._contest_share(A["force"], T["force"], T["skill"])
        cost_a = base * share_a if share_a >= trivial else 0.0
        if result["redirected"]:
            cost_a += float(ct["overextend"]) * base * share_a
        cost_t = base * share_t if share_t >= trivial else 0.0
        self._contest_spend(attacker, cost_a)
        self._contest_spend(target, cost_t)
        result.update(attacker_cost=cost_a, target_cost=cost_t, outcome=outcome)
        if choice in ("resist", "brace") and not offer["late"] and share_t >= slot_above:
            self._claim_major_action(target, choice)
        self._contest_practice_after(pending, choice)
        if outcome == "completed":
            applied, code = self._contest_move(pending, "take")
            if not applied:
                result.update(outcome="held", reason=code or "held")
                self._release_contest_slot(pending)
                return False, code or "held"
            result.update(applied=True)
            return True, None
        if outcome == "dropped":
            self._contest_drop(pending)
            result.update(reason="dropped")
            self._release_contest_slot(pending)
            return False, "dropped"
        if outcome == "redirected" and self._object_on():
            # Phase 040: a grab turned back disarms the attacker. The object in its hand falls on the cell.
            hand = list(self.eng.neighbours(self._actor(attacker), "holds_in_hand"))
            if hand:
                self._drop_discrete_item(attacker, hand[0])
        result.update(reason="held")
        self._release_contest_slot(pending)
        return False, "held"

    def _contest_practice_after(self, pending, choice):
        """Both sides practise fighting in a contest the holder answered (yield is no contest)."""
        if choice == "yield":
            return
        minutes = float(self.E.CONTEST["practice_minutes"])
        for name in (pending["attacker"], pending["target"]):
            self._contest_log_practice(name, minutes)

    def _release_contest_slot(self, pending):
        """A take that did not happen frees the actor's major action, as a refused attempt does."""
        self._release_major_action(pending["attacker"], pending["slot_before"], pending["slot_record"])

    def take_outcome(self, actor, applied, reason=None, action=None):
        """Publish a take's outcome to the actor (the same record every major action gets, Phase 021).
        `action` names the contest that produced it ("take" by default, "strike" for Phase 038)."""
        self._publish_outcome(actor, str(action or "take"), bool(applied),
                              None if applied else (reason or "not_possible"))

    # ---------------------------------------------- objects as arms (Phase 040)
    # An object held in a hand can be swung (strike, with `with`) or thrown (the throw action). Its physics come from
    # the pack's OBJECT_FORCE table, the ITEMS weight, the MATERIALS hardness and fragility, and TOOL_FIT's edge data.
    # The switch physical_subsystems.object_force gates all of it. Nothing here is random, and no assault is recorded.
    def _object_on(self):
        return bool(self.physical_subsystems.get("object_force", False))

    def _hand_held_item(self, actor, kind):
        """An unbroken item of `kind` in one of the actor's hands (a pack does not count), or None."""
        node = self._actor(actor)
        for edge in ("holds_in_hand", "holds_tableware"):
            for item in self.eng.neighbours(node, edge):
                ia = self.eng.node(item)["attrs"]
                if ia.get("kind") == kind and float(ia.get("broken", 0.0)) != 1.0:
                    return item
        return None

    def _object_material(self, kind):
        return self._item_specs.get(kind, {}).get("material")

    def _object_weight_term(self, weight):
        """Harm grows as the weight over the reference weight to weight_exponent (diminishing returns), clamped."""
        from worlds import resolution as R
        of = self.E.OBJECT_FORCE
        ratio = max(0.0, float(weight)) / float(of["weight_reference"])
        return R.clamp(ratio ** float(of["weight_exponent"]), float(of["weight_term_min"]), float(of["weight_term_max"]))

    def _object_hardness_term(self, kind):
        """The material's hardness over the reference hardness (0 to 2). A material the MATERIALS table lacks is soft."""
        of = self.E.OBJECT_FORCE
        mat = self._object_material(kind)
        hardness = float(self.E.MATERIALS[mat]["hardness"]) if mat in self.E.MATERIALS else float(of["unknown_hardness"])
        return max(0.0, min(2.0, hardness / float(of["hardness_reference"])))

    def _object_edge_term(self, kind, verb):
        """An edged kind used with a cutting verb (TOOL_FIT edge_verbs) harms more by edge_bonus."""
        tf = self.E.TOOL_FIT
        if verb in tf["edge_verbs"] and kind in tf["edged_kinds"]:
            return 1.0 + float(self.E.OBJECT_FORCE["edge_bonus"])
        return 1.0

    def _object_mult(self, kind, verb):
        """The object's physical multiplier for a verb: weight term x hardness term x edge term."""
        return (self._object_weight_term(self.item_weight(kind)) * self._object_hardness_term(kind)
                * self._object_edge_term(kind, verb))

    def _weapon_mult(self, kind):
        """(multiplier, effort) of an object swung in a blow. An authored TOOL_FIT row for `strike` is used as it is,
        with its effort. Otherwise the multiplier is harm_scale x the object's physical multiplier, at normal effort."""
        for row in self.E.TOOL_FIT["rows"].get(kind, []):
            if row["verb"] == "strike":
                return float(row["mult"]), float(row["effort"])
        return float(self.E.OBJECT_FORCE["harm_scale"]) * self._object_mult(kind, "strike"), 1.0

    def _object_breaks(self, kind):
        """Whether the object breaks when it hits something: its material's fragility is at any_fragility or more, or
        it is a container and the fragility is at container_fragility or more."""
        of = self.E.OBJECT_FORCE
        mat = self._object_material(kind)
        if mat not in self.E.MATERIALS:
            return False
        fragility = float(self.E.MATERIALS[mat]["fragility"])
        container = bool(self._item_specs.get(kind, {}).get("container"))
        return fragility >= float(of["any_fragility"]) or (container and fragility >= float(of["container_fragility"]))

    def _object_material_entry(self, kind):
        mat = self._object_material(kind)
        if mat in self.E.MATERIALS:
            return self.E.MATERIALS[mat]
        return self.E.MATERIALS[self.E.RESOLUTION["default_material"]]

    def _weapon_for_strike(self, actor, kind, item):
        """The object as a weapon for a blow: its multiplier divided by how clumsy its weight is for this swinger (the
        weight over unwieldy_above x effective strength, when that exceeds 1), and its effort, the same clumsiness
        (capped at effort_cap) times the row's effort."""
        rs, of = self.E.RESOLUTION, self.E.OBJECT_FORCE
        mult, row_effort = self._weapon_mult(kind)
        limit = max(1e-9, float(of["unwieldy_above"]) * max(0.0, self.effective_strength(actor)))
        clumsy = max(1.0, float(self.item_weight(kind)) / limit)
        return {"item": int(item), "kind": kind, "mult": mult / clumsy,
                "effort": row_effort * min(clumsy, float(rs["effort_cap"]))}

    def _throw_range(self, actor, kind, applied):
        """Cells the object carries: range_base x effective strength x intensity, over its weight (at least the reference
        weight, so a light object does not carry further than a reference one), at most range_max."""
        of = self.E.OBJECT_FORCE
        divisor = max(1.0, float(self.item_weight(kind)) / float(of["weight_reference"]))
        cells = math.floor(float(of["range_base"]) * max(0.0, self.effective_strength(actor)) * float(applied) / divisor)
        return int(max(0, min(int(of["range_max"]), cells)))

    def _cell_occludes(self, cell, codes):
        grid = self._map_grid
        x, y = cell
        return bool(grid) and 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] in codes

    def _throw_flight(self, here, target, reach):
        """The flight along the grid line from `here` toward `target`: (landing, reached, impact).

        The object goes at most `reach` cells. It stops at the last open cell before an off-map cell or a sight occluder
        (Phase 028) on the line, which is an impact. `reached` is True when it gets to `target`, and False when it stops
        short (out of range) or against an obstacle."""
        from worlds.bigville_sim_world import _line
        codes = self._occluder_codes(self.E.HEARING["sight_occluders"])
        landing = (int(here[0]), int(here[1]))
        for step, cell in enumerate(_line(here[0], here[1], target[0], target[1])[1:], start=1):
            if step > reach:
                return landing, False, False
            if cell not in self._map_cells or self._cell_occludes(cell, codes):
                return landing, False, True
            landing = (int(cell[0]), int(cell[1]))
        return landing, True, False

    def _throw_miss_cell(self, cell):
        """The first open cell beside `cell` in sorted order: where a miss lands. `cell` itself when none is open."""
        codes = self._occluder_codes(self.E.HEARING["sight_occluders"])
        around = sorted((cell[0] + dx, cell[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))
        for nxt in around:
            if nxt in self._map_cells and not self._cell_occludes(nxt, codes) \
                    and float(self.terrain_state(nxt)["speed"]) > 0.0:
                return nxt
        return (int(cell[0]), int(cell[1]))

    def _release_thrown(self, actor, item, cell, broken):
        """The object leaves the hand onto `cell`. When `broken`, it is destroyed there: kept as a broken tool, off the map."""
        self._drop_discrete_item(actor, item, cell=cell)
        if broken:
            self._wear_tool(item, 1.0)           # condition to 0: broken, and tallied (Phase 048)
            self._remove_item_location(item)
            self.eng.remove_edge_unchecked(self._town, "has_tool_item", item)

    def _publish_throw(self, actor, kind, cell, outcome, witnesses):
        """A throw is a physical event: who threw what, where it landed, and what happened. Witnesses see it; nobody else."""
        event = self.create_event("throw", subject=str(kind), detail=f"{actor} threw {kind} to {cell}: {outcome}",
                                  public=True)
        for witness in witnesses:
            self.observe_event(witness, event)
        return event

    @staticmethod
    def _as_cell(value):
        """A map cell from a proposal: two whole numbers [x, y], else None."""
        if isinstance(value, (list, tuple)) and len(value) == 2 \
                and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return (int(value[0]), int(value[1]))
        return None

    def throw_begin(self, actor, plan):
        """Start a throw by `actor` of the object named in plan["with"], from a hand, at plan["target"]: a resident who
        is within sight, or a map cell. Returns (pending, None), or (None, reason) when refused: the switch is off
        (unsupported), an unknown actor or an actor asleep, a malformed value, an object not in a hand (not_held), a
        target the world does not know or cannot reach at all (no cell), or a used action slot. Range and line never
        refuse: the object lands where its flight stops."""
        self._contest = None
        if not self._object_on():
            return None, "unsupported"
        if actor not in self._actors:
            return None, "unknown_target"
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return None, sleep_code
        plan = plan if isinstance(plan, dict) else {}
        kind = self._as_key(plan.get("with"))
        if not isinstance(kind, str):
            return None, "malformed"
        item = self._hand_held_item(actor, kind)
        if item is None:
            return None, "not_held"
        here = self.actor_position(actor)
        if here is None:
            return None, "not_in_reach"
        cell = self._as_cell(plan.get("target"))
        target = None
        if cell is None:
            target = self._as_key(plan.get("target"))
            if not isinstance(target, str):
                return None, "malformed"
            if target not in self._actors or target == actor:
                return None, "unknown_target" if target not in self._actors else "wrong_target"
            if not self.is_alive(target):
                return None, "wrong_target"
            cell = self.actor_position(target)
            if cell is None:
                return None, "unknown_target"
        elif cell not in self._map_cells:
            return None, "unknown_target"
        requested = plan.get("intensity", 1.0)
        if isinstance(requested, bool) or not isinstance(requested, (int, float)) or math.isnan(float(requested)):
            return None, "malformed"
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        ceiling = float(rs["max_intensity"]) * self.speed_factor(actor) * self.health(actor)
        applied, clamped = R.intensity_applied(float(requested), rs["max_intensity"], ceiling)
        reach = self._throw_range(actor, kind, applied)
        landing, reached, impact = self._throw_flight(here, cell, reach)
        attrs = self.eng.node(self._actor(actor))["attrs"]
        before = {"major_action_used": attrs.get("major_action_used", 0.0),
                  "major_action_kind": attrs.get("major_action_kind", ""),
                  "last_major_action": attrs.get("last_major_action", "")}
        if not self._claim_major_action(actor, "throw"):
            return None, "slot_used"
        attacker_side = self._contest_side(actor)
        if target is not None and reached:
            target_side = self._contest_side(target)
            offer = self._contest_offer(actor, target, attacker_side, target_side)
            # The only reaction a thrown object asks for is stepping aside. The take's other options do not apply.
            offer["options"] = [option for option in offer["options"] if option == "evade"]
            offer["eligible"] = bool(offer["eligible"] and offer["options"])
        else:
            target_side = None
            offer = {"eligible": False, "reason": "no_target" if target is None else "out_of_reach", "late": False,
                     "penalty": 1.0, "options": [], "aware": False, "evade_cell": None, "slot_free": True}
        pending = {
            "action": "throw", "attacker": str(actor), "target": str(target) if target is not None else "",
            "kind": kind, "kind_is_item": False, "by": "throw", "amount": 1.0,
            "turn": int(self._turn), "witnesses": self._strike_witnesses(actor),
            "slot_before": before, "slot_record": self._turn_actions[actor][-1],
            "attacker_side": attacker_side, "target_side": target_side, "offer": offer, "result": None,
            "item": int(item), "cell": (int(cell[0]), int(cell[1])), "here": (int(here[0]), int(here[1])),
            "landing": (int(landing[0]), int(landing[1])), "reached": bool(reached), "impact": bool(impact),
            "range": int(reach), "distance": max(abs(cell[0] - here[0]), abs(cell[1] - here[1])),
            "requested": float(requested), "intensity": float(applied), "clamped": bool(clamped),
        }
        self._contest = pending
        return pending, None

    def throw_resolve(self, pending, reaction=None):
        """Resolve a pending throw once the target, if any, has chosen its reaction (or None).

        Returns (True, None): a throw is enacted when the object leaves the hand, whatever it hits or misses. The outcome
        is in ``pending["result"]``: hit, evaded, missed (a person was aimed at), stopped (an obstacle on the line), short
        (out of range) or landed (a cell).

        The aim is (1 + technique_weight x skill) x exhaustion step x distance falloff, divided by the accuracy loss at
        intensity above 1. A person who does not step aside has a passive defence; one who steps aside has
        (1 + technique_weight x skill) x exhaustion step. The throw hits when the aim reaches the defence."""
        if self._contest is pending:
            self._contest = None
        from worlds import resolution as R
        rs, of, ct = self.E.RESOLUTION, self.E.OBJECT_FORCE, self.E.CONTEST
        actor, item, kind = pending["attacker"], pending["item"], pending["kind"]
        target = pending["target"] or None
        offer = pending["offer"]
        choice = reaction if (offer["eligible"] and reaction in offer["options"]) else None
        A = pending["attacker_side"]
        here, cell, applied = tuple(pending["here"]), tuple(pending["cell"]), float(pending["intensity"])
        distance = int(pending["distance"])
        falloff = 1.0 / (1.0 + distance / float(of["distance_reference"]))
        tw = float(ct["technique_weight"])
        actor_step = float(self._exhaustion_band(actor)["speed"])
        aim = ((1.0 + tw * float(A["skill"])) * actor_step * falloff
               / (1.0 + float(of["accuracy_intensity_loss"]) * max(0.0, applied - 1.0)))
        result = {"action": "throw", "reaction": choice or "", "outcome": "", "applied": True, "reason": "",
                  "late": bool(offer["late"]) if choice is not None else False, "redirected": False,
                  "attacker_cost": 0.0, "target_cost": 0.0, "harm": 0.0, "hit": False, "broken": False,
                  "landed_at": [], "weapon": kind}
        pending["result"] = result
        harm, hit = 0.0, False
        if target is None or not pending["reached"]:
            landing = tuple(pending["landing"])
            if target is None and pending["reached"]:
                outcome = "landed"
            elif pending["impact"]:
                outcome = "stopped"
            else:
                outcome = "short"
        else:
            T = pending["target_side"] or self._contest_side(target)
            defence = (of["passive_defence"] if choice != "evade"
                       else (1.0 + tw * float(T["skill"])) * float(self._exhaustion_band(target)["speed"]))
            defence = float(defence)
            hit = aim >= defence
            if hit:
                margin = (aim - defence) / (aim + defence) if aim + defence > 0.0 else 0.0
                quality = R.clamp((1.0 + margin) / 2.0, 0.0, 1.0)
                harm = (float(of["throw_harm"]) * self._object_mult(kind, "throw") * applied * falloff * quality
                        * actor_step)
                outcome = "hit"
                landing = cell                       # the object falls where the person stands
                if harm > 0.0:
                    self.harm(target, harm, "violence")
            else:
                outcome = "evaded" if choice == "evade" else "missed"
                if choice == "evade":
                    self._move_actor_to(target, offer["evade_cell"])
                landing = self._throw_miss_cell(cell)
            self._contest_practice_after(pending, choice)
        impact = bool(pending["impact"]) or hit
        broken = impact and self._object_breaks(kind)
        mat_entry = self._object_material_entry(kind)
        # The stamina and strain are the resolution core's: a demand of the object's weight, against the thrower's force.
        demand = float(self.item_weight(kind)) / float(of["throw_demand_unit"])
        terms = {"applied": applied, "clamped": bool(pending["clamped"]), "force": float(A["force"]),
                 "technique": R.technique_term(float(A["skill"]), rs["technique_floor"]), "fit": 1.0, "effort": 1.0,
                 "tool_kind": kind}
        step, share = self._resolve_terms(terms, None, demand)
        plan = {"primitive": "displace", "verb": "throw", "name": target or "cell", "node": item, "tool": item,
                "terms": terms, "step": step, "share": share, "demand": demand, "condition": 1.0,
                "material": mat_entry, "requested": pending["requested"], "actor": actor}
        self._finish_attempt(actor, plan, outcome, 0.0, harm)
        if share >= float(rs["trivial_below"]):
            result["attacker_cost"] = float(step["stamina"])
        self._release_thrown(actor, item, landing, broken)
        if broken:
            self._publish_noise(actor, "throw", kind, R.noise_radius(rs["noise_base"], applied,
                                                                     float(mat_entry["noise"])))
        self._publish_throw(actor, kind, landing, outcome, pending["witnesses"])
        result.update(outcome=outcome, harm=float(harm), hit=bool(hit), broken=bool(broken),
                      landed_at=[int(landing[0]), int(landing[1])])
        return True, None

    # ---------------------------------------------- strikes (Phase 038)
    # A strike is a blow by one resident on another standing on the same cell (reach is the cell, as for a take).
    # It reuses the contest: the blow's power is the attacker's score (force x technique), the target's hold is
    # its resist or brace score (none when it does not react, so an unprepared target takes the blow in full), and
    # the share that lands is (1 + margin) / 2 of the take's margin. The stamina rules are the take's, with the
    # blow's intensity raising the cost by intensity^k. A blow with less stamina than attack_cost lands weakly. The
    # world does not decide to strike: the backend proposes it. Nothing here is random.
    def contest_begin(self, actor, action, plan):
        """The begin step of a contested major action: `take` (Phase 029) or `strike` (Phase 038)."""
        if action == "strike":
            return self.strike_begin(actor, plan)
        if action == "restrain":
            return self.restrain_begin(actor, plan)
        if action == "throw":
            return self.throw_begin(actor, plan)
        return self.take_begin(actor, plan)

    def strike_begin(self, actor, plan):
        """Start a strike by `actor` on the resident `plan["target"]`, who must stand on the actor's cell.

        Returns (pending, None) with the target's reaction offer, or (None, reason) when refused: an unknown
        resident, the actor itself, a dead person, someone off the cell, a malformed intensity, a sleeping or
        collapsed actor, or a used action slot. Stamina never refuses a blow. The intensity is clamped as an
        attempt's is (RESOLUTION max_intensity, lowered by speed and health)."""
        self._contest = None
        if actor not in self._actors:
            return None, "unknown_target"
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return None, sleep_code
        plan = plan if isinstance(plan, dict) else {}
        target = self._as_key(plan.get("target"))
        requested = plan.get("intensity", 1.0)
        if target is None or isinstance(requested, bool) or not isinstance(requested, (int, float)) \
                or math.isnan(float(requested)):
            return None, "malformed"
        if target not in self._actors or target == actor:
            return None, "unknown_target" if target not in self._actors else "wrong_target"
        if not self.is_alive(target):
            return None, "wrong_target"
        here, there = self.actor_position(actor), self.actor_position(target)
        if here is None or here != there:
            return None, "not_in_reach"
        from worlds import resolution as R
        rs = self.E.RESOLUTION
        ceiling = float(rs["max_intensity"]) * self.health(actor)   # tiredness weakens the blow (weak), not its ceiling
        applied, _clamped = R.intensity_applied(float(requested), rs["max_intensity"], ceiling)
        weapon = None
        if plan.get("with") is not None and self._object_on():
            kind = self._as_key(plan.get("with"))
            if not isinstance(kind, str):
                return None, "malformed"
            item = self._hand_held_item(actor, kind)
            if item is None:
                return None, "not_held"
            weapon = self._weapon_for_strike(actor, kind, item)     # Phase 040: a blow with an object in hand
        attrs = self.eng.node(self._actor(actor))["attrs"]
        before = {"major_action_used": attrs.get("major_action_used", 0.0),
                  "major_action_kind": attrs.get("major_action_kind", ""),
                  "last_major_action": attrs.get("last_major_action", "")}
        if not self._claim_major_action(actor, "strike"):
            return None, "slot_used"
        attacker_side = self._contest_side(actor)
        target_side = self._contest_side(target)
        pending = {
            "action": "strike", "attacker": str(actor), "target": str(target),
            "kind": "blow", "kind_is_item": False, "by": "blow",
            "amount": float(applied), "intensity": float(applied),
            "turn": int(self._turn),
            "witnesses": self._strike_witnesses(actor),
            "slot_before": before, "slot_record": self._turn_actions[actor][-1],
            "attacker_side": attacker_side, "target_side": target_side,
            "offer": self._contest_offer(actor, target, attacker_side, target_side),
            "result": None, "weapon": weapon,
        }
        self._contest = pending
        return pending, None

    def _strike_witnesses(self, actor):
        """Living, awake residents with sight of the actor: within HEARING sight_range by the Chebyshev distance and
        with no sight occluder on the line (Phase 028). The target is among them when it can see. Nobody else learns."""
        here = self.actor_position(actor)
        if here is None:
            return []
        table = self.E.HEARING
        sight_range = int(table["sight_range"])
        codes = self._occluder_codes(table["sight_occluders"])
        seen = []
        for other in self._actors:
            if other == actor or not self.is_alive(other) or self._sleep_code(other) is not None:
                continue
            pos = self.actor_position(other)
            if pos is None:
                continue
            dist = max(abs(pos[0] - here[0]), abs(pos[1] - here[1]))
            if dist <= _dn.sight_range(self, other, sight_range) and not self._line_blocked(here, pos, codes):
                seen.append(other)
        return seen

    def strike_resolve(self, pending, reaction=None):
        """Resolve a pending strike once the target has chosen its reaction (or None for none).

        Returns (applied, reason). applied is True when the blow was enacted: it landed (outcome struck) or a
        skilled holder turned it back on the attacker (redirected). A target that stepped out of reach gives
        (False, "evaded"). The attacker's blow is on the record either way. The full result is kept in
        ``pending["result"]``."""
        if self._contest is pending:
            self._contest = None
        from worlds import resolution as R
        ct = self.E.CONTEST
        attacker, target = pending["attacker"], pending["target"]
        offer = pending["offer"]
        choice = reaction if (offer["eligible"] and reaction in offer["options"]) else None
        A, T = pending["attacker_side"], pending["target_side"]
        base, grip, tw = float(ct["base_cost"]), float(ct["grip"]), float(ct["technique_weight"])
        trivial, slot_above = float(ct["trivial_below"]), float(ct["slot_above"])
        k = float(self.E.RESOLUTION["k"])
        intensity = float(pending["intensity"])
        penalty = float(offer["penalty"]) if choice is not None else 1.0
        body = self._bodies.get(attacker)
        reserve = float(self.eng.node(body)["attrs"].get("stamina_reserve", 1.0)) if body is not None else 0.0
        weak = R.clamp(reserve / float(ct["attack_cost"]), 0.0, 1.0)
        result = {"action": "strike", "reaction": choice or "", "outcome": "", "applied": False, "reason": "",
                  "late": bool(offer["late"]) if choice is not None else False, "redirected": False,
                  "attacker_cost": 0.0, "target_cost": 0.0, "harm": 0.0, "landed": 0.0, "weak": weak}
        pending["result"] = result
        # The attacker's load is the take's: a yielding target brings none, a resisting one its full force, and
        # any other target its passive grip. The swing costs that share, discounted by the attacker's technique.
        if choice == "yield":
            brought = 0.0
        elif choice == "resist":
            brought = T["force"]
        else:
            brought = grip * T["force"]
        share_a = self._contest_share(brought, A["force"], A["skill"])
        cost_a = base * share_a * (intensity ** k) if share_a >= trivial else 0.0
        weapon = pending.get("weapon")
        if weapon is not None:
            cost_a *= float(weapon["effort"])      # Phase 040: a heavy object tires the swinger
        if choice == "evade":
            share_t = self._contest_share(A["force"], T["force"], T["skill"])
            cost_t = base * share_t if share_t >= trivial else 0.0
            self._contest_spend(attacker, cost_a)
            self._contest_spend(target, cost_t)
            self._move_actor_to(target, offer["evade_cell"])
            result.update(outcome="evaded", reason="evaded", attacker_cost=cost_a, target_cost=cost_t)
            self._contest_practice_after(pending, choice)
            self._record_sight(attacker, "strike", pending["witnesses"])
            return False, "evaded"
        # What the target's hold stops: none unprepared or yielding; the resist or brace score otherwise.
        if choice in (None, "yield"):
            hold = 0.0
        elif choice == "resist":
            hold = T["force"] * (1.0 + tw * T["skill"]) * penalty
        else:
            hold = grip * T["force"] * (1.0 + tw * T["skill"]) * penalty
        att = A["power"] * (float(pending["weapon"]["mult"]) if pending.get("weapon") is not None else 1.0)
        total = att + hold
        margin = 0.0 if total <= 0.0 else (att - hold) / total
        landed = R.clamp((1.0 + margin) / 2.0, 0.0, 1.0)
        redirected = (margin <= -float(ct["decisive_margin"]) and choice in ("resist", "brace")
                      and T["skill"] - A["skill"] >= float(ct["redirect_gap"]))
        harm = 0.0 if redirected else float(ct["strike_harm"]) * intensity * weak * landed * att
        share_t = self._contest_share(A["force"], T["force"], T["skill"])
        cost_t = base * share_t if (choice in ("resist", "brace") and share_t >= trivial) else 0.0
        if redirected:
            cost_a += float(ct["overextend"]) * base * share_a * (intensity ** k)
        self._contest_spend(attacker, cost_a)
        self._contest_spend(target, cost_t)
        if choice in ("resist", "brace") and not offer["late"] and share_t >= slot_above:
            self._claim_major_action(target, choice)
        self._contest_practice_after(pending, choice)
        result.update(attacker_cost=cost_a, target_cost=cost_t, landed=landed, harm=harm,
                      redirected=redirected, outcome="redirected" if redirected else "struck", applied=True,
                      weapon=pending["weapon"]["kind"] if pending.get("weapon") is not None else "")
        self._record_sight(attacker, "strike", pending["witnesses"])
        if harm > 0.0:
            self.harm(target, harm, "violence")
        if redirected:
            self.harm(attacker, float(ct["redirect_harm"]) * intensity, "violence")
        weapon = pending.get("weapon")
        if weapon is not None:
            # Phase 040: the object takes the wear of the blow, and breaks when it hit and is breakable.
            held = self._hand_held_item(attacker, weapon["kind"])
            if held is not None and int(held) == int(weapon["item"]):
                self._wear_tool(held, R.tool_wear(self.E.RESOLUTION["tool_wear"], intensity, 1.0,
                                                  self.E.RESOLUTION["mismatch_wear"], 0.0))
                if harm > 0.0 and self._object_breaks(weapon["kind"]):
                    self._release_thrown(attacker, held, self.actor_position(attacker), broken=True)
        return True, None

    # ---------------------------------------------- restraint (Phase 033)
    # A restraint is a grab by one resident on another standing on the same cell (reach is the cell, as for a
    # take). It reuses the contest: the grab's power is the holder's score, the held resident's hold is its resist
    # or brace score (a passive grip when it does not react, none when it yields), and the grab holds on a decisive
    # margin. A held resident cannot walk, and neither can the holder. Each tick of holding costs both awake sides
    # by the contest's effort rule, each bearing the other's passive grip. A struggle is the held resident's major
    # action: it frees them on a decisive margin, and the holder's active hold keeps them otherwise. The hold is two
    # attributes on the two actor nodes (`held_by`, `holding`), so the graph keeps it. Nothing here is random, and no
    # custody, arrest or crime is recorded: the residents' institutions own those.
    def holder_of(self, target):
        """The resident holding `target` in a restraint, or None."""
        if not isinstance(target, str) or target not in self._actors:
            return None
        return str(self.eng.node(self._actors[target])["attrs"].get("held_by", "")) or None

    def holding_of(self, holder):
        """The resident that `holder` is restraining, or None."""
        if not isinstance(holder, str) or holder not in self._actors:
            return None
        return str(self.eng.node(self._actors[holder])["attrs"].get("holding", "")) or None

    def _set_hold(self, holder, target):
        self.eng.set_attr(self._actors[target], "held_by", str(holder))
        self.eng.set_attr(self._actors[holder], "holding", str(target))

    def _clear_hold(self, holder, target):
        if holder in self._actors and self.holding_of(holder) == target:
            self.eng.set_attr(self._actors[holder], "holding", "")
        if target in self._actors and self.holder_of(target) == holder:
            self.eng.set_attr(self._actors[target], "held_by", "")

    def restrain_begin(self, actor, plan):
        """Start a restraint by `actor` on `plan["target"]`, who must stand on the actor's cell.

        Returns (pending, None) with the target's reaction offer, or (None, reason) when refused: an unknown
        resident, the actor itself, a dead person, someone off the cell, someone already held, an actor who is
        already holding someone, a sleeping actor, or a used action slot. Nothing is claimed on a refusal."""
        self._contest = None
        if actor not in self._actors:
            return None, "unknown_target"
        sleep_code = self._sleep_code(actor)
        if sleep_code is not None:
            return None, sleep_code
        plan = plan if isinstance(plan, dict) else {}
        target = self._as_key(plan.get("target"))
        if target is None:
            return None, "malformed"
        if target not in self._actors or target == actor:
            return None, "unknown_target" if target not in self._actors else "wrong_target"
        if not self.is_alive(target):
            return None, "wrong_target"
        here, there = self.actor_position(actor), self.actor_position(target)
        if here is None or here != there:
            return None, "not_in_reach"
        if self.holding_of(actor) is not None:
            return None, "already_holding"
        if self.holder_of(target) is not None:
            return None, "already_restrained"
        attrs = self.eng.node(self._actor(actor))["attrs"]
        before = {"major_action_used": attrs.get("major_action_used", 0.0),
                  "major_action_kind": attrs.get("major_action_kind", ""),
                  "last_major_action": attrs.get("last_major_action", "")}
        if not self._claim_major_action(actor, "restrain"):
            return None, "slot_used"
        attacker_side = self._contest_side(actor)
        target_side = self._contest_side(target)
        pending = {
            "action": "restrain", "attacker": str(actor), "target": str(target),
            "kind": "grip", "kind_is_item": False, "by": "hands", "amount": 1.0,
            "turn": int(self._turn),
            "witnesses": self._strike_witnesses(actor),
            "slot_before": before, "slot_record": self._turn_actions[actor][-1],
            "attacker_side": attacker_side, "target_side": target_side,
            "offer": self._contest_offer(actor, target, attacker_side, target_side),
            "result": None,
        }
        self._contest = pending
        return pending, None

    def restrain_resolve(self, pending, reaction=None):
        """Resolve a pending restraint once the target has chosen its reaction (or None for none).

        Returns (applied, reason). applied is True when the target is now held. A target that stepped out of reach
        gives (False, "evaded"); a grab that does not win gives (False, "slipped"). The stamina is paid either way.
        The full result is kept in ``pending["result"]``."""
        if self._contest is pending:
            self._contest = None
        ct = self.E.CONTEST
        attacker, target = pending["attacker"], pending["target"]
        offer = pending["offer"]
        choice = reaction if (offer["eligible"] and reaction in offer["options"]) else None
        A, T = pending["attacker_side"], pending["target_side"]
        base, grip, tw = float(ct["base_cost"]), float(ct["grip"]), float(ct["technique_weight"])
        trivial, slot_above = float(ct["trivial_below"]), float(ct["slot_above"])
        penalty = float(offer["penalty"]) if choice is not None else 1.0
        result = {"action": "restrain", "reaction": choice or "", "outcome": "", "applied": False, "reason": "",
                  "late": bool(offer["late"]) if choice is not None else False,
                  "attacker_cost": 0.0, "target_cost": 0.0}
        pending["result"] = result
        if choice == "evade":
            share_t = self._contest_share(A["force"], T["force"], T["skill"])
            cost_t = base * share_t if share_t >= trivial else 0.0
            self._contest_spend(target, cost_t)
            self._move_actor_to(target, offer["evade_cell"])
            result.update(outcome="evaded", reason="evaded", target_cost=cost_t)
            self._release_contest_slot(pending)
            self._contest_practice_after(pending, choice)
            self._record_sight(attacker, "restrain", pending["witnesses"])
            return False, "evaded"
        # What the held resident's hold stops, and what it brings to bear (its load on the grab's holder).
        if choice == "yield":
            brought, hold = 0.0, 0.0
        elif choice is None:
            brought, hold = grip * T["force"], grip * T["force"]
        elif choice == "resist":
            brought, hold = T["force"], T["force"] * (1.0 + tw * T["skill"]) * penalty
        else:  # brace: a technique-assisted hold; it bears the grab but brings grip x force
            brought, hold = grip * T["force"], grip * T["force"] * (1.0 + tw * T["skill"]) * penalty
        att = A["score"]
        total = att + hold
        margin = 0.0 if total <= 0.0 else (att - hold) / total
        share_a = self._contest_share(brought, A["force"], A["skill"])
        cost_a = base * share_a if share_a >= trivial else 0.0
        share_t = self._contest_share(A["force"], T["force"], T["skill"])
        cost_t = base * share_t if (choice in ("resist", "brace") and share_t >= trivial) else 0.0
        self._contest_spend(attacker, cost_a)
        self._contest_spend(target, cost_t)
        if choice in ("resist", "brace") and not offer["late"] and share_t >= slot_above:
            self._claim_major_action(target, choice)
        self._contest_practice_after(pending, choice)
        result.update(attacker_cost=cost_a, target_cost=cost_t)
        self._record_sight(attacker, "restrain", pending["witnesses"])
        if margin >= float(ct["decisive_margin"]):
            self._set_hold(attacker, target)
            result.update(outcome="restrained", applied=True)
            return True, None
        result.update(outcome="slipped", reason="slipped")
        self._release_contest_slot(pending)
        return False, "slipped"

    def _release_held(self, holder):
        """The holder lets go: the hold ends, and those who can see the holder see it."""
        target = self.holding_of(holder)
        self._clear_hold(holder, target)
        self._record_sight(holder, "release", self._strike_witnesses(holder))
        return True

    def struggle(self, actor):
        """The held resident's struggle, one major action (Phase 033). Returns True when it frees the resident.

        The struggler's score is its full force with technique, against the holder's active hold (its full force
        with technique). A decisive margin frees the struggler and ends the hold; otherwise the hold stands and the
        struggle is refused as `pinned`. Both sides pay the load the other brings to bear, and the action slot is
        spent either way."""
        holder = self.holder_of(actor)
        if holder is None:
            return self._refuse("not_restrained")
        if not self._claim_major_action(actor, "struggle"):
            return self._refuse("slot_used")
        ct = self.E.CONTEST
        base, tw = float(ct["base_cost"]), float(ct["technique_weight"])
        trivial = float(ct["trivial_below"])
        A, H = self._contest_side(actor), self._contest_side(holder)
        att = A["score"]
        hold = H["force"] * (1.0 + tw * H["skill"])
        total = att + hold
        margin = 0.0 if total <= 0.0 else (att - hold) / total
        share_a = self._contest_share(H["force"], A["force"], A["skill"])
        share_h = self._contest_share(A["force"], H["force"], H["skill"])
        self._contest_spend(actor, base * share_a if share_a >= trivial else 0.0)
        self._contest_spend(holder, base * share_h if share_h >= trivial else 0.0)
        for name in (actor, holder):
            self._contest_log_practice(name, float(ct["practice_minutes"]))
        self._record_sight(actor, "struggle", self._strike_witnesses(actor))
        if margin >= float(ct["decisive_margin"]):
            self._clear_hold(holder, actor)
            return True
        return self._refuse("pinned")

    def _holds_tick(self):
        """One tick of every restraint. The hold ends when the holder or the held resident is dead, the holder is
        asleep or collapsed, or they no longer share a cell. Otherwise each awake side pays for the passive grip the
        other brings to bear, by the contest's effort rule, and the hold ends if that leaves the holder collapsed."""
        ct = self.E.CONTEST
        base, grip, trivial = float(ct["base_cost"]), float(ct["grip"]), float(ct["trivial_below"])
        for target in list(self._actors):
            holder = self.holder_of(target)
            if holder is None:
                continue
            if (self.holding_of(holder) != target or not self.is_alive(holder) or not self.is_alive(target)
                    or self._sleep_code(holder) is not None or self.actor_position(holder) is None
                    or self.actor_position(holder) != self.actor_position(target)):
                self._clear_hold(holder, target)
                continue
            H, T = self._contest_side(holder), self._contest_side(target)
            share_h = self._contest_share(grip * T["force"], H["force"], H["skill"])
            self._contest_spend(holder, base * share_h if share_h >= trivial else 0.0)
            if self._sleep_code(target) is None:
                share_t = self._contest_share(grip * H["force"], T["force"], T["skill"])
                self._contest_spend(target, base * share_t if share_t >= trivial else 0.0)
            if self._sleep_code(holder) is not None:
                self._clear_hold(holder, target)

    def _sleep_code(self, actor):
        """'collapsed' or 'asleep' while the resident is down (refusal reasons), else None."""
        try:
            known = actor in self._actors
        except TypeError:          # an unhashable proposal value is not a resident
            return None
        if not known:
            return None
        attrs = self.eng.node(self._actors[actor])["attrs"]
        if float(attrs.get("collapsed", 0.0)) == 1.0:
            return "collapsed"
        if float(attrs.get("asleep", 0.0)) == 1.0:
            return "passed_out" if float(attrs.get("sleep_kind", 0.0)) == 3.0 else "asleep"
        return None

    def asleep(self, actor):
        """True while the resident sleeps, including a collapse (their flag `asleep`)."""
        return self._sleep_code(actor) is not None

    def collapsed(self, actor):
        """True while the resident is down from exhaustion (flag `collapsed`). A collapse is also a sleep."""
        return self._sleep_code(actor) == "collapsed"

    def _exhaustion_band(self, actor):
        """The resident's exhaustion band, from the reserve (the seed's mv_energy_budget).

        step 0 at or above e_high, 1 at or above e_mid, 2 at or above e_low, 3 below e_low. `speed` is the
        moves per tick as a share of the full budget (1, 2/3, 1/3, 0, from moves_per_tick). `interval` is
        the multiplier on the movement interval (1, 1.5, 3). Thresholds are fractions of the body's stamina
        capacity, so a resident with a larger capacity has larger absolute thresholds. With slow_on off
        every resident is in band 0."""
        ex = self.E.EXHAUSTION
        moves = [float(m) for m in ex["moves_per_tick"]]
        node = self._actors.get(actor)
        slow_default = 1.0 if self.exhaustion_slow_on else 0.0
        slow_on = float(self.eng.node(node)["attrs"].get("slow_on", slow_default)) == 1.0 if node is not None else False
        if not slow_on:
            return {"step": 0, "speed": 1.0, "interval": 1.0, "stopped": False, "below_e_low": False}
        body = self._bodies.get(actor)
        ba = self.eng.node(body)["attrs"] if body is not None else {}
        reserve = float(ba.get("stamina_reserve", 1.0))
        capacity = self.effective_stamina(actor)
        step = len(moves) - 1
        for band, key in enumerate(("e_high", "e_mid", "e_low")):
            if reserve >= float(ex[key]) * capacity:
                step = band
                break
        speed = moves[step] / moves[0]
        return {"step": step, "speed": speed,
                "interval": moves[0] / moves[step] if moves[step] > 0.0 else math.inf,
                "stopped": moves[step] <= 0.0, "below_e_low": step == len(moves) - 1}

    def _refresh_exhaustion(self, actor):
        """Publish the band on the actor node: `exhaustion_step` and `speed_factor` (read-offs)."""
        band = self._exhaustion_band(actor)
        node = self._actors[actor]
        attrs = self.eng.node(node)["attrs"]
        if float(attrs.get("exhaustion_step", -1.0)) != float(band["step"]):
            self.eng.set_attr(node, "exhaustion_step", float(band["step"]))
        if float(attrs.get("speed_factor", -1.0)) != float(band["speed"]):
            self.eng.set_attr(node, "speed_factor", float(band["speed"]))

    def exhaustion_step(self, actor):
        return int(self._exhaustion_band(actor)["step"])

    def speed_factor(self, actor):
        return round(float(self._exhaustion_band(actor)["speed"]), 4)

    def _job_speed(self, job):
        """The speed a timed job advances at: its worker's movement speed (Phase 024 extension)."""
        actor = str(self.eng.node(job)["attrs"].get("canonical_actor", ""))
        return self._exhaustion_band(actor)["speed"] if actor in self._actors else 1.0

    def _witnesses(self, actor):
        """Awake, living residents on the actor's cell. Sight has no range model yet, so a witness must
        stand on the same cell (Phase 024). Sight does not shorten at night."""
        here = self.actor_position(actor)
        if here is None:
            return []
        return [other for other in self._actors
                if other != actor and self.is_alive(other) and self.actor_position(other) == here
                and self._sleep_code(other) is None]

    def _record_sight(self, actor, kind, witnesses):
        """A physical event seen by the witnesses. Their concern is theirs to form, not the world's.
        Nobody's sight, no event: an unseen sleep leaves no town record."""
        if not witnesses:
            return None
        event = self.create_event(kind, subject=actor, detail=f"{actor} {kind}", public=True)
        for witness in witnesses:
            self.observe_event(witness, event)
        return event

    def _lie_down(self, actor, *, collapsed):
        """Set the resident asleep (a collapse when `collapsed`). Their timed job pauses, through the
        Phase 023 pause, because `_job_away` counts a sleeper as away."""
        node = self._actors[actor]
        self.eng.set_attr(node, "asleep", 1.0)
        self.eng.set_attr(node, "collapsed", 1.0 if collapsed else 0.0)
        self.eng.set_attr(node, "sleep_kind", 2.0 if collapsed else 1.0)
        self._record_sight(actor, "collapse" if collapsed else "sleep", self._witnesses(actor))
        self._set_job_paused(actor, self.job_paused(actor))

    def _wake(self, actor):
        node = self._actors[actor]
        self.eng.set_attr(node, "asleep", 0.0)
        self.eng.set_attr(node, "collapsed", 0.0)
        self.eng.set_attr(node, "sleep_kind", 0.0)
        self._set_job_paused(actor, self.job_paused(actor))

    def _recover_strain(self, actor):
        """Strain (Phase 050) falls by strain_sleep_recovery per clock tick of sleep, down to zero (Phase 050b)."""
        attrs = self.eng.node(self._actors[actor])["attrs"]
        strain = float(attrs.get("strain", 0.0))
        if strain <= 0.0:
            return
        rate = float(self.E.RESOLUTION["strain_sleep_recovery"])
        self.eng.set_attr(self._actors[actor], "strain", max(0.0, strain - rate))

    def _resolve_sleep(self):
        """Collapse, sleep and wake, once per run (seed bigville_time_sleep).

        An awake resident whose reserve is below e_collapse collapses where they stand. A sleeper regains
        rest_gain per clock tick up to rest_cap, or collapse_gain up to collapse_cap while collapsed, and
        wakes at that cap. Regaining happens on clock ticks only (the armed run), not on every run."""
        ex = self.E.EXHAUSTION
        for actor, node in self._actors.items():
            body = self._bodies.get(actor)
            if body is not None and self.is_alive(actor):
                ba = self.eng.node(body)["attrs"]
                reserve = float(ba.get("stamina_reserve", 1.0))
                code = self._sleep_code(actor)
                if code is None and reserve < float(ex["e_collapse"]):
                    # Phase 037: the collapse is the exhaustion route; the sleep follows only if the resident lives.
                    self._exhaustion_collapse(actor)
                    if self.is_alive(actor):
                        self._lie_down(actor, collapsed=True)
                    code = "collapsed"
                elif code is not None and code != "passed_out" and self._job_tick_armed:
                    self._recover_strain(actor)
                    collapsed = code == "collapsed"
                    gain = float(ex["collapse_gain" if collapsed else "rest_gain"])
                    # Phase 036: a hangover lets a sleeper regain only hangover_recovery of the stamina.
                    gain *= self._hangover_recovery_factor(actor)
                    # Phase 037: a body holds no more stamina than its health-scaled capacity (Phase 032), so a sleeper
                    # wakes at the lower of the cap and that capacity. A healthy body (capacity >= 1) is unchanged.
                    cap = min(float(ex["collapse_cap" if collapsed else "rest_cap"]), self.effective_stamina(actor))
                    regained = max(reserve, min(cap, reserve + gain))
                    if regained != reserve:
                        self.eng.set_attr(body, "stamina_reserve", regained)
                    if not collapsed:
                        # Phase 037: ordinary sleep restores health a tick at a time (HEALTH.rest_health_gain).
                        self._heal(actor, float(self.E.HEALTH["rest_health_gain"]))
                    if regained >= cap:
                        if not collapsed:
                            self.eng.set_attr(node, "collapse_run", 0.0)     # a full rest ends a run of collapses
                        self._wake(actor)
            self._refresh_exhaustion(actor)

    # ---------------------------------------------------- intoxication (Phase 034)
    # Alcohol is a fact of the body. A drink adds its grams of alcohol to the body's intoxication (INTOXICATION,
    # Widmark scale). The level falls by a steady amount each clock tick, and at pass_out the resident passes out
    # (reason passed_out) until it falls below wake_below. The world publishes the level and its band. What a
    # resident drinks, says or does is the backend's choice.
    def intoxication(self, actor):
        """The body's intoxication, 0 (sober) to 1 at full scale. It stays 0 while metabolism is off."""
        return round(float(self.eng.node(self._bodies[actor])["attrs"].get("intoxication", 0.0)), 4)

    def intoxication_band(self, actor):
        """'sober', 'tipsy', 'drunk' or 'stupefied' (the table's bands)."""
        return self.E.intoxication_band(self.intoxication(actor))

    def stagger_speed(self, actor):
        """The movement factor alcohol gives: stagger_speed above stagger_above, else 1. It multiplies the
        Phase 024 speed factor; it does not replace it."""
        ip = self.E.INTOXICATION
        return float(ip["stagger_speed"]) if self.intoxication(actor) > float(ip["stagger_above"]) else 1.0

    def _drink_alcohol(self, actor, kind):
        """A drink's alcohol enters the body (a food with no alcohol changes nothing). Metabolism off: nothing.
        Phase 036: with alcohol_aftereffects on, a tolerant body takes less of the dose, the drink adds tolerance,
        and it relieves craving."""
        grams = self.E.alcohol(kind)
        if grams <= 0.0 or not self.physical_subsystems["metabolism"]:
            return
        body = self._bodies[actor]
        attrs = self.eng.node(body)["attrs"]
        gain = self.E.intoxication_gain(grams, float(attrs.get("size", 1.0)))
        on = self._aftereffects_on()
        if on:
            ip = self.E.INTOXICATION
            gain *= 1.0 - float(ip["tolerance_relief"]) * float(attrs.get("tolerance", 0.0))
        self.eng.set_attr(body, "intoxication", min(1.0, float(attrs.get("intoxication", 0.0)) + gain))
        self._intox_drunk_grams += grams
        if on:
            ip = self.E.INTOXICATION
            tolerance = min(float(ip["tolerance_max"]),
                            float(attrs.get("tolerance", 0.0)) + float(ip["tolerance_per_drink"]))
            self.eng.set_attr(body, "tolerance", tolerance)
            if tolerance >= float(ip["dependence_tolerance"]):
                self.eng.set_attr(body, "dependent", 1.0)
            self.eng.set_attr(body, "craving", max(0.0, float(attrs.get("craving", 0.0))
                                                   - float(ip["craving_relief_per_drink"])))

    def _pass_out(self, actor):
        """Put a resident into the sleep state for drink (sleep_kind 3). Their timed job pauses, as in any sleep."""
        node = self._actors[actor]
        self.eng.set_attr(node, "asleep", 1.0)
        self.eng.set_attr(node, "collapsed", 0.0)
        self.eng.set_attr(node, "sleep_kind", 3.0)
        self._set_job_paused(actor, self.job_paused(actor))

    def _resolve_intoxication(self):
        """Sober by sober_per_tick on each clock tick, and pass out or wake at the table's thresholds. The check runs
        on every pass, so a drink that crosses pass_out takes effect at once. Sleep does not sober a resident faster:
        the passed-out resident simply waits for the level to fall (the sleep regains no stamina; see _resolve_sleep).
        Phase 036 (switch on): the aftereffects of _alcohol_tick, then poisoning above poison_above on each clock tick,
        after pass_out has been applied."""
        ip = self.E.INTOXICATION
        armed = self._job_tick_armed
        on = self._aftereffects_on()
        for actor in self._actors:
            body = self._bodies.get(actor)
            if body is None or not self.is_alive(actor):
                continue
            before = float(self.eng.node(body)["attrs"].get("intoxication", 0.0))
            level = before
            if level > 0.0 and armed:
                level = max(0.0, level - self.E.sober_per_tick())
                self.eng.set_attr(body, "intoxication", level)
            if on:
                self._alcohol_tick(actor, body, before, level, armed)
            code = self._sleep_code(actor)
            if code is None and level >= float(ip["pass_out"]):
                self._pass_out(actor)
            elif code == "passed_out" and level < float(ip["wake_below"]):
                self._wake(actor)
            if on and armed and level >= float(ip["poison_above"]):
                # Phase 036: poisoning is acute harm, cause intoxication, scaled from 0 at poison_above to poison_harm at 1.
                share = (level - float(ip["poison_above"])) / max(1e-9, 1.0 - float(ip["poison_above"]))
                self.harm(actor, float(ip["poison_harm"]) * min(1.0, share), "intoxication")
            if armed:
                self._intox_ticks[self.E.intoxication_band(level)] += 1

    # ---------------------------------------------------- alcohol aftereffects (Phase 036)
    # Switch alcohol_aftereffects (off by default). Tolerance rises with each drink and fades while sober; a body
    # that reaches dependence_tolerance is dependent, and while dependent craving rises while sober and falls with a
    # drink. Withdrawal is a skill and stamina penalty while craving is high. A drinking episode that peaks at
    # hangover_above leaves a hangover when the level falls back to the tipsy band: a skill penalty, and sleep
    # regains less stamina, for hangover_ticks. Every figure is the INTOXICATION table's; all state is body attributes.
    def _aftereffects_on(self):
        return bool(self.physical_subsystems.get("alcohol_aftereffects"))

    def _alcohol_tick(self, actor, body, before, level, armed):
        """Phase 036: the per-pass part of the aftereffects. `before` is the level before this pass sobered it, so an
        episode's peak is seen even when the same pass brings the level down; `level` is after it."""
        ip = self.E.INTOXICATION
        attrs = self.eng.node(body)["attrs"]
        hangover = float(attrs.get("hangover_ticks", 0.0))
        if armed and hangover > 0.0:
            hangover -= 1.0
        peak = max(float(attrs.get("episode_peak", 0.0)), before)
        if level < float(ip["bands"]["tipsy"]):
            if peak >= float(ip["hangover_above"]):
                hangover = float(ip["hangover_ticks"])
            peak = 0.0
            if armed:
                tolerance = max(0.0, float(attrs.get("tolerance", 0.0)) - float(ip["tolerance_fade_per_tick"]))
                self.eng.set_attr(body, "tolerance", tolerance)
                if float(attrs.get("dependent", 0.0)) == 1.0:
                    craving = min(1.0, float(attrs.get("craving", 0.0)) + float(ip["craving_rise_per_tick"]))
                    self.eng.set_attr(body, "craving", craving)
        self.eng.set_attr(body, "episode_peak", peak)
        self.eng.set_attr(body, "hangover_ticks", hangover)

    def _withdrawing(self, actor):
        ip = self.E.INTOXICATION
        return float(self.eng.node(self._bodies[actor])["attrs"].get("craving", 0.0)) >= float(ip["withdrawal_above"])

    def _withdrawal_share(self, actor):
        """The craving that is in withdrawal (0 when not withdrawing, else the craving level, 0 to 1)."""
        if not self._aftereffects_on() or not self._withdrawing(actor):
            return 0.0
        return float(self.eng.node(self._bodies[actor])["attrs"].get("craving", 0.0))

    def _hangover_on(self, actor):
        return self._aftereffects_on() and float(self.eng.node(self._bodies[actor])["attrs"].get("hangover_ticks", 0.0)) > 0.0

    def aftereffects(self, actor):
        """Phase 036 read-offs: tolerance (0 to tolerance_max), craving (0 to 1), dependent (0 or 1), hangover_ticks
        left, withdrawal (0 or 1) and the mood (read by the coping policy). Empty while alcohol_aftereffects is off."""
        if not self._aftereffects_on():
            return {}
        attrs = self.eng.node(self._bodies[actor])["attrs"]
        return {"tolerance": round(float(attrs.get("tolerance", 0.0)), 4),
                "craving": round(float(attrs.get("craving", 0.0)), 4),
                "dependent": int(float(attrs.get("dependent", 0.0)) == 1.0),
                "hangover_ticks": int(float(attrs.get("hangover_ticks", 0.0))),
                "withdrawal": int(self._withdrawing(actor)),
                "mood": round(float(attrs.get("mood", 0.5)), 4)}

    def _aftereffect_skill_factor(self, actor):
        """Working skill's multiplier from the aftereffects: a hangover, and withdrawal at craving x withdrawal_skill."""
        if not self._aftereffects_on():
            return 1.0
        ip = self.E.INTOXICATION
        factor = 1.0
        if self._hangover_on(actor):
            factor *= 1.0 - float(ip["hangover_skill"])
        factor *= 1.0 - float(ip["withdrawal_skill"]) * self._withdrawal_share(actor)
        return factor

    def _withdrawal_stamina_factor(self, actor):
        if not self._aftereffects_on():
            return 1.0
        return 1.0 - float(self.E.INTOXICATION["withdrawal_stamina"]) * self._withdrawal_share(actor)

    def _hangover_recovery_factor(self, actor):
        """The share of a sleep's stamina regain a hangover keeps (1 when there is no hangover)."""
        return float(self.E.INTOXICATION["hangover_recovery"]) if self._hangover_on(actor) else 1.0

    def intoxication_tally(self):
        """Counts over the town (Phase 034): residents now in each band (passed_out counts residents asleep from
        drink), resident-ticks spent in each band so far, and grams of alcohol drunk so far. Plain counts only."""
        now = {band: 0 for band in self.E.INTOXICATION_BANDS}
        now["passed_out"] = 0
        for actor in self._actors:
            if not self.is_alive(actor):
                continue
            now[self.intoxication_band(actor)] += 1
            if self._sleep_code(actor) == "passed_out":
                now["passed_out"] += 1
        return {"now": now, "resident_ticks": dict(self._intox_ticks),
                "alcohol_grams": round(self._intox_drunk_grams, 4)}

    def sleep_facts(self, actor):
        """The facts the seed says the adapter writes for a sleep decision (Phase 024).

        `lateness`: hours into the night, from the clock (0 before night_start_hour and after night_end_hour).
        `safe`: the resident stands indoors, at their home or in a sheltered building."""
        ex = self.E.EXHAUSTION
        self._actor(actor)
        hour = self.calendar().get("hour")
        hour = float(self.E.TIME["start_hour"]) if hour is None else float(hour)
        start, end = float(ex["night_start_hour"]), float(ex["night_end_hour"])
        if hour >= start:
            lateness = hour - start
        elif hour < end:
            lateness = hour + 24.0 - start
        else:
            lateness = 0.0
        safe = False
        here = self.actor_position(actor)
        if here is not None:
            home = self._map_cells.get(here)
            if home is not None and home in self.eng.neighbours(self._actor(actor), "home_at"):
                safe = True
            for key in self._places:
                site = self._building_sites.get(key)
                if site and self.building_sheltered(key):
                    x, y, w, h = site[:4]
                    if x <= here[0] < x + w and y <= here[1] < y + h:
                        safe = True
        lateness = _dn.lateness(self, lateness)   # Phase 042: from the real sunset when day and night is on
        return {"lateness": round(lateness, 4), "safe": bool(safe)}

    def fatigue(self, actor):
        """Read-off of stamina spent (Phase 022): the same as `exertion`. There is no separate accumulator."""
        return self.exertion(actor)

    def rest(self, actor, amount=1.0):
        """Rest as a physical body event; it recovers held stamina reserve."""
        self._actor(actor)
        rest = self.eng.add_node("Rest", {"amount": float(amount), "rest_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "rested", rest)
        self._request_rule_sweep()
        return self.stamina_reserve(actor)
    def body_state(self, actor):
        body = self._bodies[actor]
        attrs = self.eng.node(body)["attrs"]
        band = self._exhaustion_band(actor)
        return {"health": round(self.health(actor), 4),
                "mood": round(float(attrs.get("mood", 0.5)), 4),
                "strength": round(self.effective_strength(actor), 4),
                "stamina": round(self.effective_stamina(actor), 4),
                "stamina_reserve": round(float(attrs.get("stamina_reserve", 1.0)), 4),
                # Phase 024 read-offs: the exhaustion step (0 full speed .. 3 too exhausted to walk), the
                # movement speed it gives (1, 2/3, 1/3, 0), and the sleep flags.
                "exhaustion_step": int(band["step"]), "speed_factor": round(float(band["speed"]), 4),
                "asleep": self.asleep(actor), "collapsed": self.collapsed(actor),
                # Phase 034 read-offs: intoxication (0 sober to 1) and its band.
                "intoxication": self.intoxication(actor), "intoxication_band": self.intoxication_band(actor),
                # Phase 035 read-offs: protein_store (grams), deficiency, meal_pleasure and monotony.
                **self.nutrition(actor),
                # Phase 043 read-offs: the illness flag and the care flags (screened, treated, well_baby), 0 or 1.
                "illness": int(bool(self.eng.node(self._actors[actor])["attrs"].get("disease"))),
                "screened": self._care_flag_value(actor, "screened"),
                "treated": self._care_flag_value(actor, "treated"), "well_baby": self._care_flag_value(actor, "well_baby"),
                # Phase 036 read-offs (tolerance, craving, dependent, hangover_ticks, withdrawal, mood); empty when off.
                **self.aftereffects(actor)}

    def stamina(self, actor): return self.body_state(actor)["stamina"]
    def stamina_reserve(self, actor): return self.body_state(actor)["stamina_reserve"]
    def strength(self, actor): return self.body_state(actor)["strength"]
    def energy(self, actor):
        """Movement energy read from body stamina reserve, not an Agent ledger."""
        return round(self.stamina_reserve(actor) * 100.0, 4)
    def exertion(self, actor):
        """Current exertion read-off: effective stamina capacity less reserve."""
        state = self.body_state(actor)
        return round(max(0.0, state["stamina"] - state["stamina_reserve"]), 4)
    def qty(self, kind):
        return round(float(self.eng.node(self._stock[kind])["attrs"]["qty"]), 4) if kind in self._stock else 0.0
    def item_kinds(self): return {self.eng.node(n)["attrs"]["kind"] for n in self.eng.nodes("ItemSpec")}
    def recipe_names(self): return {self.eng.node(n)["attrs"]["name"] for n in self.eng.nodes("ActionSpec")}
    def store_attrs(self): return self.eng.node(self._store)["attrs"]
