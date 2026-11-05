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
from collections import deque
from pathlib import Path

from bigville.runtime import (BigvilleGraph, WorldAdapter, boot_core,
                               load_seeds_into, manifest_for)
from bigville.scenarios import load_scenario
from domains.data_view import entities as _entities_view  # noqa: E402
from bigville.backends.speech import DeterministicSpeechBackend  # noqa: E402
from worlds.bigville_bond_world import SLOT_DEFAULTS as BOND_SLOTS  # noqa: E402

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
    }

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

    def __init__(self, *, map_seed=305000, autonomous_actors=False, scenario=None,
                 cognition_factory=None, physical_subsystems=None,
                 physical_subsystem_extensions=None, data_pack=None):
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
        self._physical_object_locations = {}
        self._actor_cells = {}
        self._actor_positions = {}
        self._actor_goals = {}
        self._land_cells = {}
        self._household_cells = {}
        self._resource_deposits = {}
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
        self._transactions = {}
        self._prices = {}
        self._illnesses = {}
        self._births = []
        self._deaths = []
        self._alive_snapshot = {}
        self._report_history = []
        self._journals = {}
        self._rng = random.Random(int(map_seed))
        # Unified social graph.  These are world-mediated records; beliefs,
        # intentions, and relationship models remain on the resident edges and
        # attributes rather than being smuggled into body state.
        self._notes = {}
        self._conversations = {}
        self._utterances = {}
        self._speech_events = []
        self._market_expectation_specs = {}
        self._actor_market_expectations = {}
        self._requests = {}
        self._relationships = {}
        self._turn_actions = {}
        self._turn = 0
        self._resolved_period = 0.0
        self._job_tick_armed = False
        self._major_dispatch = False
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

    def move_physical_object(self, object_id, location):
        """Move an ordinary object; no game-specific admissibility is applied."""
        object_id = str(object_id)
        object_id = self.resolve_physical_object_id(object_id)
        if object_id not in self._physical_objects:
            return False
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
            return False
        object_id = self.resolve_physical_object_id(object_id)
        if object_id not in self._physical_objects:
            return False
        source = self._physical_object_locations.get(object_id, "world")
        if not self._physical_object_accessible(actor, source, object_id=object_id):
            return False
        destination = self.resolve_physical_object_id(destination)
        if destination not in {"table", "world", *self._actors} \
                and destination not in self._physical_objects:
            return False
        if destination in self._physical_objects:
            # A container cannot be moved inside itself or any of its own
            # descendants; reject before changing either location index.
            cursor = destination
            seen = set()
            while cursor in self._physical_objects and cursor not in seen:
                if cursor == object_id:
                    return False
                seen.add(cursor)
                cursor = self._physical_object_locations.get(cursor, "")
        if destination in self._physical_objects and not self._physical_object_accessible(
                actor, destination):
            return False
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
                    return False
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

    def _run(self):
        before = {kind: float(self.eng.node(node)["attrs"].get("qty", 0.0))
                  for kind, node in self._stock.items()}
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
        self._resolve_clothing_and_bodies()
        self._resolve_period_effects()
        # Stock piles are intentionally bulk physical nodes, but a new harvest
        # or fresh bake must not inherit a fully-rotted condition from an older
        # batch mixed into the same pile.  Reset freshness when a perishable
        # pile gained quantity during this rule pass; this keeps bulk storage
        # simple without making new production instantly spoil.
        for kind, node in self._stock.items():
            attrs = self.eng.node(node)["attrs"]
            qty = float(attrs.get("qty", 0.0))
            if qty < 0.0:
                self.eng.set_attr(node, "qty", 0.0)
                qty = 0.0
            if kind in before and qty > before[kind] and attrs.get("perishable", 0.0) == 1.0:
                self.eng.set_attr(node, "condition", 1.0)
            self._last_stock_qty[kind] = qty
        self._record_unlogged_deaths()

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
            remaining = float(ja.get("remaining", 0.0))
            if remaining > 0.0:
                if not self._job_tick_armed:
                    continue
                remaining -= 1.0
                self.eng.set_attr(job, "remaining", max(0.0, remaining))
                actor_nodes = self.eng.in_neighbours(job, "on_job")
                if actor_nodes:
                    actor_attrs = self.eng.node(actor_nodes[0])["attrs"]
                    asp_nodes = self.eng.neighbours(job, "runs")
                    difficulty = float(self.eng.node(asp_nodes[0])["attrs"].get("difficulty", 1.0)) if asp_nodes else 1.0
                    self.eng.set_attr(actor_nodes[0], "fatigue",
                                      float(actor_attrs.get("fatigue", 0.0)) + difficulty * 2.0)
                if remaining > 0.0:
                    continue
            asp_nodes = self.eng.neighbours(job, "runs")
            if not asp_nodes:
                continue
            asp = asp_nodes[0]
            action = self.eng.node(asp)["attrs"]
            # Plan every input before changing anything. Each bulk unit comes from the worker's own
            # stock, then an accessible container at their cell, then the store (see `_plan_inputs`).
            # An unfulfilled job stays busy and can be completed after the missing good arrives.
            job_actor = str(ja.get("canonical_actor", ""))
            need_specs = []
            for need in self.eng.neighbours(job, "need"):
                na = self.eng.node(need)["attrs"]
                need_specs.append((need, na.get("kind", ""), float(na.get("qty", 0.0)),
                                   float(na.get("is_item", 0.0)) == 1.0, na.get("slot_type", "")))
            plans = self._plan_inputs(job_actor, [(k, q, i, s) for _, k, q, i, s in need_specs])
            missing = plans is None
            # Validate the required instruments before consuming any of the
            # recipe inputs. A tool can be removed or broken while a timed job
            # is underway, so the start-time check alone is not sufficient.
            # Leave the job armed at zero remaining: it can finish later if
            # the instrument is restored, without losing its materials.
            job_own_tools = (bool(self._recipe_specs.get(action.get("name", ""), {}).get("open"))
                             and job_actor in self._actors)
            for tool_use in self.eng.neighbours(job, "uses"):
                kind = self.eng.node(tool_use)["attrs"].get("kind", "")
                if job_own_tools:                       # open recipes use the worker's own tool
                    if self._held_tool(job_actor, kind) is None:
                        missing = True
                elif self._worker_tool(job_actor, kind) is None:
                    missing = True
            if missing:
                continue
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
            out_kind, out_qty = action.get("out_kind", ""), float(action.get("out_qty", 0.0))
            if float(action.get("out_discrete", 0.0)) == 1.0:
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
            for kind, qty in self._recipe_specs.get(action.get("name", ""), {}).get("byproducts", {}).items():
                self.set_stock(kind, self.qty(kind) + float(qty))      # e.g. bran from milling
            own_tools = bool(self._recipe_specs.get(action.get("name", ""), {}).get("open"))
            for tool_use in self.eng.neighbours(job, "uses"):
                kind = self.eng.node(tool_use)["attrs"].get("kind")
                if own_tools and actor_name in self._actors:
                    tool = self._held_tool(actor_name, kind)
                elif actor_name in self._actors:
                    tool = self._worker_tool(actor_name, kind)
                else:
                    tool = None
                if tool is not None:
                    ta = self.eng.node(tool)["attrs"]
                    condition = max(0.0, float(ta.get("condition", 1.0)) - float(ta.get("wear", 0.02)))
                    self.eng.set_attr(tool, "condition", condition)
                    if self.eng.node(tool)["type"] == "ToolItem" and condition <= 0.0:
                        self.eng.set_attr(tool, "broken", 1.0)      # a worn-out own tool must be replaced
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
                self.eng.set_attr(actor_node, "busy", 0.0)
                self.eng.remove_edge_unchecked(actor_node, "on_job", job)

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
                if container is not None and amount > 0.0 and self.qty(kind) >= amount:
                    max_load = float(self.eng.node(self._containers[container][0])["attrs"].get("max_load", 1e18))
                    if (self.used_volume(container) + amount * self.item_volume(kind) <= self.capacity(container) + 1e-9
                            and self.contents_weight(container) + amount * self.item_weight(kind) <= max_load + 1e-9
                            and (not self.is_fluid(kind) or float(self.eng.node(self._containers[container][0])["attrs"].get("watertight", 0.0)) == 1.0)):
                        inner = self._containers[container][1][kind]
                        self.set_stock(kind, self.qty(kind) - amount)
                        self.eng.set_attr(inner, "qty", self.contents(container, kind) + amount)
                self.eng.set_attr(node, "fill_armed", 0.0)
            if float(attrs.get("empty_armed", 0.0)) == 1.0:
                kind, amount = attrs.get("empty_kind", ""), float(attrs.get("empty_amount", 0.0))
                for container, (cn, inners) in self._containers.items():
                    if kind not in inners or not self._container_accessible(actor, container):
                        continue
                    amount = min(amount, self.contents(container, kind))
                    self.eng.set_attr(inners[kind], "qty", self.contents(container, kind) - amount)
                    self.set_stock(kind, self.qty(kind) + amount)
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
                        cost = float(ea.get("stamina_cost", 0.0))
                        self.eng.set_attr(body, "stamina_reserve",
                                          max(0.0, float(ba.get("stamina_reserve", 1.0)) - cost))
                        self.eng.set_attr(ea and event, "cost_done", 1.0)
                    else:
                        amount = float(ea.get("amount", 1.0))
                        self.eng.set_attr(body, "stamina_reserve",
                                          min(float(ba.get("stamina", 1.0)), float(ba.get("stamina_reserve", 1.0)) + amount * 0.1))
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
            self.eng.set_attr(node, "chill", max(0.0, float(town.get("cold", 0.0)) - warmth))
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
                for name, node in self._animals.items():
                    aa = self.eng.node(node)["attrs"]
                    if float(aa.get("alive", 0.0)) != 1.0:
                        continue
                    # Metabolism changes the animal's condition only. Feed is
                    # consumed by an explicit animal action at an accessible pile.
                    hunger = float(aa.get("hunger", 0.0)) + 1.0
                    self.eng.set_attr(node, "hunger", hunger)
                    if hunger >= float(aa.get("starve_limit", 3.0)):
                        self.eng.set_attr(node, "alive", 0.0)
                for actor, node in self._actors.items():
                    aa = self.eng.node(node)["attrs"]
                    if float(aa.get("alive", 0.0)) != 1.0:
                        continue
                    hunger = float(aa.get("hunger", 0.0)) + 1.0
                    self.eng.set_attr(node, "hunger", hunger)
                    if hunger > float(aa.get("starve_limit", self.E.CARE["starve_limit"])):
                        self.eng.set_attr(node, "alive", 0.0)
                self._collect_night_soil()
            if self.physical_subsystems["ecology"]:
                self._advance_soil_nitrogen()
                for crop in list(self._living_crops()):
                    ca = self.eng.node(crop)["attrs"]
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
                    if condition <= 0.0:
                        self.eng.set_attr(stock, "qty", 0.0)
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

        food_qty = (sum(self.qty(kind) for kind, spec in self._item_specs.items() if spec.get("food"))
                    + sum(self.inventory_qty(name, kind)
                          for name in self._actors
                          for kind, spec in self._item_specs.items() if spec.get("food")))
        food_days = food_qty / len(alive) if alive else 0.0
        shelf_lives = [self.stock_condition(kind) / self.E.decay_rate(kind)
                       for kind, spec in self._item_specs.items()
                       if spec.get("food") and self.qty(kind) > 0 and self.E.decay_rate(kind) > 0]
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
                           if not any(self._can_attempt(name, action)
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

    def actor_position(self, actor): return self._actor_positions.get(actor)

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
        old = self._actor_positions.get(actor)
        if old in self._map_cells:
            self.eng.remove_edge_unchecked(self._actors[actor], "at_cell", self._map_cells[old])
        self._attach_at_cell(self._actors[actor], cell)
        self._actor_positions[actor] = tuple(cell)
        # Footfall is a physical effect of arriving, so it belongs to the single
        # enactment site rather than to any one caller that happens to move someone.
        self._wear_cell_by_traversal(actor, cell)

    def move_actor(self, actor, destination):
        """Move one resident toward a destination, with load affecting travel."""
        current = self._actor_positions.get(actor)
        if current is None or destination not in self._map_cells:
            return None
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
                "intensity": min(1.0, effort), "stamina_cost": effort * 0.1,
                "terrain": terrain["terrain"], "terrain_speed": float(terrain["speed"]),
                "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
            self.eng.add_edge_unchecked(self._actor(actor), "exerted", exertion)
            if not self._actor_tick_in_progress:
                self._run()
        cooldown = int(round(float(attrs.get("carry_move_cooldown", 0.0))))
        if cooldown > 0:
            self.eng.set_attr(self._actor(actor), "carry_move_cooldown", float(cooldown - 1))
            return current
        terrain_interval = max(1, int(math.ceil(state["move_interval"] * terrain["move_time"])))
        if terrain_interval > 1:
            self.eng.set_attr(self._actor(actor), "carry_move_cooldown",
                              float(terrain_interval - 1))
        if nxt is not None:
            self._move_actor_to(actor, nxt)
        return self._actor_positions.get(actor)

    @classmethod
    def from_town100(cls, seed=305000, *, autonomous_actors=False,
                     cognition_factory=None, data_pack=None):
        """Build the founding town of a data pack: its map, its seeded cast of residents, and its
        institutions. The default pack is bigville (the 100-resident town of the canonical world).
        A pack with no founding town (empty FOUNDING_JOBS) is refused by populate_town100."""
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors,
                    cognition_factory=cognition_factory, data_pack=data_pack)
        world.populate_town100(seed=seed)
        return world

    @classmethod
    def from_scenario(cls, scenario, *, seed=305000, autonomous_actors=False,
                      cognition_factory=None):
        """Build any compact or large scenario from data.

        Actor cognition remains a game/backend concern; this method only
        installs the physical world and the scenario's initial actors.
        """
        definition = load_scenario(scenario)
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors,
                    scenario=definition, cognition_factory=cognition_factory)
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
        # Expand the founding rotation into physical crop beds.  Beds may
        # share a mapped parcel; the map locates the field, while each Crop
        # node is an independently watered and harvested unit.
        self._seed_village_crops(target=80)
        self._found_kinship(cast["residents"], seed)
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
        if self.qty("newspaper") < 1.0 or edition not in self.eng.nodes():
            return None
        self.set_stock("newspaper", self.qty("newspaper") - 1.0)
        copy = self.eng.add_node("NewspaperCopy", {"day": float(self.calendar()["day"])})
        self.eng.add_edge_unchecked(self._actors[reader], "holds", copy)
        self.eng.add_edge_unchecked(copy, "of_edition", edition)
        self._newspaper_copies[f"copy:{len(self._newspaper_copies) + 1}"] = copy
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
                                             "fuel_need": 0.0, "shelter": 1.0,
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
            return False
        attrs = self.eng.node(self._actors[operator])["attrs"]
        node = self._infrastructure[name]
        if self._turn > 0 and self.actor_position(operator) != self.map_position_node(node):
            return False
        spec = self.E.INFRASTRUCTURE[self.eng.node(node)["attrs"]["kind"]]
        amount = min(float(labour), max(0.0, 1.0 - self.infrastructure_condition(name)))
        if amount <= 0.0:
            return False
        required = {kind: amount for kind in spec.get("maintenance", ())}
        if any(self.qty(kind) < qty for kind, qty in required.items()):
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(operator, "maintain"):
            return False
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

    def add_store(self, cell, kinds=()):
        cell = tuple(cell)
        assert cell in self._map_cells, f"store cell {cell} not walkable"
        self.eng.add_edge_unchecked(self._store, "at_cell", self._map_cells[cell])
        self.eng.set_attr(self._store, "market_x", float(cell[0]))
        self.eng.set_attr(self._store, "market_y", float(cell[1]))
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
        if not self._move_stock_to_inventory(seller, kind, amount):
            return False
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
        if amount <= 0.0 or self.qty(kind) < amount:
            return False
        inventory = self._inventory_container(actor)[0]
        used = self.used_volume(self._actor_inventories[actor])
        if used + amount * self.item_volume(kind) > self.capacity(self._actor_inventories[actor]) + 1e-9:
            return False
        self.set_stock(kind, self.qty(kind) - amount)
        stock = self._inventory_stock(actor, kind, create=True)
        self.eng.set_attr(stock, "qty", float(self.eng.node(stock)["attrs"].get("qty", 0.0)) + amount)
        self.eng.add_edge_unchecked(self._actor(actor), "holds_food", stock)
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
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - amount)
        self.set_stock(kind, self.qty(kind) + amount)
        self._refresh_carry_state(actor)
        return True

    def _move_inventory_to_inventory(self, giver, recipient, kind, amount):
        """Move a held stock pile directly between two resident carriers."""
        amount = float(amount)
        if amount <= 0.0 or self.inventory_qty(giver, kind) < amount:
            return False
        if (self.used_volume(self._actor_inventories[recipient])
                + amount * self.item_volume(kind)
                > self.capacity(self._actor_inventories[recipient]) + 1e-9):
            return False
        source = self._inventory_stock(giver, kind)
        target = self._inventory_stock(recipient, kind, create=True)
        self.eng.set_attr(source, "qty", self.inventory_qty(giver, kind) - amount)
        self.eng.set_attr(target, "qty", self.inventory_qty(recipient, kind) + amount)
        self._refresh_carry_state(giver)
        self._refresh_carry_state(recipient)
        return True

    def _give_discrete_item(self, giver, recipient, item):
        if self._item_owner_edge(giver, item) is None:
            return False
        accepted = self._accept_discrete_item(recipient, item, giver=giver)
        if accepted:
            self.eng.add_edge_unchecked(self._actor(giver), "gave_item", item)
            self.eng.add_edge_unchecked(item, "given_to", self._actor(recipient))
        return accepted

    def give(self, giver, recipient, kind, amount=1.0, *, payment_kind=None,
             payment_amount=None):
        """Physically hand a held good or coin to a nearby resident.

        Legacy payment arguments are accepted for call compatibility but have
        no world-side agreement semantics. The cognition layer must choose any
        payment as a separate physical transfer.
        """
        amount = max(0.0, float(amount))
        if amount <= 0.0:
            return False
        if recipient in self._shops:
            return False
        self._actor(giver); self._actor(recipient)
        if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(giver, "give"):
            return False
        if (self._turn > 0 and self.actor_position(giver) != self.actor_position(recipient)):
            return False
        if not isinstance(kind, str):
            return self._give_discrete_item(giver, recipient, kind)
        if kind == "coin":
            if self.coin(giver) < amount:
                return False
            self.set_coin(giver, self.coin(giver) - amount)
            self.set_coin(recipient, self.coin(recipient) + amount)
        elif not self._move_inventory_to_inventory(giver, recipient, kind, amount):
            return False
        else:
            state = self._refresh_carry_state(recipient)
            if state["will_drop"]:
                self._remove_inventory_stock(recipient, kind, amount)
                dropped = self._drop_stock(recipient, kind, amount)
                self.eng.set_attr(self._actor(recipient), "last_carry_outcome", "dropped")
                self.eng.set_attr(self._actor(recipient), "last_dropped_kind", str(kind))
                self.eng.set_attr(self._actor(recipient), "last_dropped_node",
                                  int(dropped.value) if dropped is not None else -1.0)
            else:
                self.eng.set_attr(self._actor(recipient), "last_carry_outcome", "held")
        self.eng.add_edge_unchecked(self._actor(giver), "gave", self._actor(recipient))
        return True

    def _physical_transfer_precheck(self, source, recipient, kind, amount=1.0):
        if source not in self._actors or recipient not in self._actors:
            return False
        if (self.actor_position(source) is None
                or self.actor_position(source) != self.actor_position(recipient)):
            return False
        if isinstance(kind, str):
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                return False
            if amount <= 0.0:
                return False
            if kind == "coin":
                return self.coin(source) >= amount
            return (self.inventory_qty(source, kind) >= amount
                    and self.used_volume(self._actor_inventories[recipient])
                    + amount * self.item_volume(kind)
                    <= self.capacity(self._actor_inventories[recipient]) + 1e-9)
        return self._item_owner_edge(source, kind) is not None

    def _physical_transfer(self, source, recipient, kind, amount=1.0):
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
            return self.give(source, recipient, kind, amount)
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

    def _drop_discrete_item(self, actor, item):
        """Drop an item from a hand onto the actor's current map cell."""
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
        cell = self.actor_position(actor)
        if cell in self._map_cells:
            self._attach_at_cell(item, cell)
        self._refresh_carry_state(actor)
        return item

    def _accept_discrete_item(self, actor, item, *, giver=None):
        """Put an item in the accepting person's hand, then apply load limits."""
        self._actor(actor)
        if self.eng.node(item).get("type") != "ToolItem":
            return False
        if giver is not None:
            self._actor(giver)
            edge = self._item_owner_edge(giver, item)
            if edge is None:
                return False
            self.eng.remove_edge_unchecked(self._actor(giver), edge, item)
            if self._actor_hands.get(giver) == item:
                self._actor_hands[giver] = None
            kind = self.eng.node(item)["attrs"].get("kind", "")
            if kind in self._actor_tableware.get(giver, {}):
                self._actor_tableware[giver][kind] = [held for held in self._actor_tableware[giver][kind]
                                                      if held != item]
            self._refresh_carry_state(giver)
        elif self._item_owner_edge(actor, item) is not None:
            return False
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
        return self._accept_discrete_item(actor, item, giver=giver)

    accept = accept_item

    def pick_up(self, actor, item):
        """Try to pick up a ground item; overload may immediately drop it."""
        self._actor(actor)
        if self._item_owner_edge(actor, item) is not None:
            return False
        if not self.eng.has_edge(self._town, "has_tool_item", item):
            cells = list(self.eng.neighbours(item, "at_cell"))
            actor_cells = list(self.eng.neighbours(self._actor(actor), "at_cell"))
            if not cells or not actor_cells or cells[0] != actor_cells[0]:
                return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "pick_up"):
            return False
        return self._accept_discrete_item(actor, item)

    def drop_item(self, actor, item):
        """Drop an item voluntarily as a handling action."""
        if self._item_owner_edge(actor, item) is None:
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "drop"):
            return False
        self._drop_discrete_item(actor, item)
        self.eng.set_attr(self._actor(actor), "last_carry_outcome", "dropped")
        return True

    def _has_tableware(self, actor, kind):
        return bool(self._actor_tableware.get(actor, {}).get(kind))

    def eat(self, actor, kind=None, *, vessel=None, utensil=None, source=None):
        """Eat one held food unit as an explicit major action.

        Soups require a bowl-sized serving vessel and a ladle/serving spoon (a
        bowl may itself scoop from a larger bowl). Drinks require a mug and a
        dipper or mug. ``source`` may name a larger physical container and is
        checked for the corresponding serving capacity.
        """
        if kind is None:
            candidates = [k for k, spec in self._item_specs.items()
                          if spec.get("food") and self.inventory_qty(actor, k) >= 1.0]
            candidates.sort(key=lambda k: (0 if self._item_specs[k].get("prepared") else 1, k))
            kind = candidates[0] if candidates else None
        if kind is None or not self._item_specs.get(kind, {}).get("food"):
            return False
        if self.inventory_qty(actor, kind) < 1.0:
            return False
        service = self.E.food_service(kind)
        if service is not None:
            if vessel is None or utensil is None:
                return False
            if not self._has_tableware(actor, vessel) or not self._has_tableware(actor, utensil):
                return False
            source_kind = None
            if source is not None:
                if source not in self._containers or self.contents(source, kind) < 1.0:
                    return False
                source_kind = self.eng.node(self._containers[source][0])["attrs"].get("kind", "")
            if not self.E.can_serve(kind, vessel, utensil, source_kind=source_kind):
                return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "eat"):
            return False
        stock = self._inventory_stock(actor, kind)
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - 1.0)
        leftover = self.E.scrap_kind(kind)
        if leftover is not None:                         # the bones/rind stay in the eater's hands
            fraction = float(self._item_specs[kind]["leaves_scraps"])
            scraps = self._inventory_stock(actor, leftover, create=True)
            self.eng.set_attr(scraps, "qty", self.inventory_qty(actor, leftover) + fraction)
        self._refresh_carry_state(actor)
        self.eng.set_attr(self._actor(actor), "hunger", 0.0)
        self.eng.add_edge_unchecked(self._actor(actor), "ate", stock)
        return True

    def pay_wage(self, employer, worker, amount):
        """Retired: use an explicit coin transfer chosen by the backend."""
        return False

    def _record_transaction(self, kind, actor, target, good, quantity, value):
        node = self.eng.add_node("Transaction", {"kind": kind, "actor": str(actor), "target": str(target),
                                                   "good": str(good), "quantity": float(quantity),
                                                   "value": float(value), "day": float(self.calendar()["day"])})
        self.eng.add_edge_unchecked(self._town, "has_transaction", node)
        self._transactions[f"transaction:{len(self._transactions) + 1}"] = node
        return node

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

    def set_stock(self, kind, qty):
        w, v, fl = self._phys(kind)
        food = 1.0 if self._item_specs.get(kind, {}).get("food") else 0.0
        perishable = 1.0 if self.E.adjectival(kind) == "perishable" else 0.0
        if kind in self._stock:
            self.eng.set_attr(self._stock[kind], "qty", float(qty))
        else:
            colour = self._item_specs.get(kind, {}).get("colour", "")   # a dye names a colour (madder->red)
            s = self.eng.add_node("Stock", {"kind": kind, "qty": float(qty),   # a first-class physical pile
                                            "weight": w, "volume": v, "fluid": fl, "food": food, "colour": colour,
                                            # spoilage: a perishable pile has a freshness that decays over time
                                            "perishable": perishable, "condition": 1.0,
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
            return None
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(builder, "build"):
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
            return None
        scale = labour / float(attrs["labour"])
        required = {k: float(v) * scale for k, v in spec.get("inputs", {}).items()}
        if any(self.qty(k) + 1e-9 < q for k, q in required.items()):
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

    def _wire_container(self, name, node, kind, holds, lock_id, locked, max_load=None, capacity=None):
        cap, wt, df = self._vessel_data(kind)
        if capacity is not None:
            cap = float(capacity)
        ml = max_load if max_load is not None else float(self._item_specs.get(kind, {}).get("max_load", 1e9))
        for k, v in (("capacity", cap), ("watertight", wt), ("decay_factor", df), ("max_load", ml),
                     ("lock_id", float(lock_id)), ("locked", 1.0 if locked else 0.0)):
            self.eng.set_attr(node, k, v)
        storage_class = (self._item_specs.get(kind, {}) or self.E.CONTAINERS.get(kind, {})).get("storage_class")
        if storage_class:
            self.eng.set_attr(node, "storage_class", storage_class)
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

    def add_container(self, name, *, kind="barrel", holds, lock_id=0.0, locked=False, cell=None):
        c = self.eng.add_node("Container", {"kind": kind, "name": name})
        c = self._wire_container(name, c, kind, holds, lock_id, locked)
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

    def add_animal(self, name, species, *, cell=None, household=None, land=None, enclosure=None):
        spec = self.E.ANIMALS[species]
        a = self.eng.add_node("Animal", {"name": name, "species": species, "role": spec.get("role", ""),
                                         "pull": float(spec.get("pull", 0.0)), "alive": 1.0,
                                         "matures": float(spec.get("matures", 0)), "lifespan": float(spec.get("lifespan", 0)),
                                         # feeding state (data-driven): what it eats, how much, and its starve limit
                                         "hunger": 0.0, "hunger_epoch": 0.0, "eats": spec.get("eats", ""),
                                         "ration": float(spec.get("ration", 1)), "starve_limit": float(spec.get("starve_limit", 3)),
                                         "last_npc_action": "", "npc_model": "psi_can_weighted"})
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
        """Perform one data-defined animal-care yield with a period cooldown."""
        assert actor in self._actors and animal in self._animals
        if (self._turn > 0
                and self.actor_position(actor) != self.map_position_node(self._animals[animal])):
            return 0.0
        spec = self.E.ANIMAL_HUSBANDRY[task]
        an = self._animals[animal]
        aa = self.eng.node(an)["attrs"]
        assert aa["species"] == spec["species"], f"{task} requires a {spec['species']}"
        assert float(aa.get("alive", 0.0)) == 1.0, f"{animal} is not alive"
        period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        epoch_key = f"{task}_epoch"
        last = float(aa.get(epoch_key, -float(spec["cooldown"])))
        if period - last < float(spec["cooldown"]):
            return 0.0
        product = spec["product"]
        amount = float(self.E.ANIMALS[aa["species"]].get("gives", {}).get(product, 0.0))
        if amount <= 0.0:
            return 0.0
        self.set_stock(product, self.qty(product) + amount)
        self.eng.set_attr(an, epoch_key, period)
        self.eng.add_edge_unchecked(self._actors[actor], "performed_husbandry", an)
        return amount

    def milk(self, milker, cow):
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(milker, "milk"):
            return 0.0
        return self._husbandry_yield(milker, cow, "milk")

    def shear(self, shearer, sheep):
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(shearer, "shear"):
            return 0.0
        return self._husbandry_yield(shearer, sheep, "shear")

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

    def _seed_village_crops(self, target=80):
        """Fill the founding fields with enough beds for a 100-person rotation.

        The eight founding crops are intentionally small and readable in the
        map.  Additional beds are still ordinary Crop nodes on those parcels;
        they represent cultivated area rather than new map tiles.  Eighty
        beds uses the founding seed reserve and gives the 100-person cast a
        plausible working margin after milling and baking losses.
        """
        if not self._land:
            return 0
        farmers = self._workers_with_roles(self.E.LABOUR_TASKS["farm"]["worker_roles"], alive_only=False)
        if not farmers:
            return 0
        crops = ("wheat", "barley", "oats")
        added = 0
        land_names = [name for name in self._land if name.startswith("farm_plot_")]
        while len(self._living_crops()) < target:
            crop = crops[added % len(crops)]
            seed = self.E.CROPS[crop]["seed"]
            if self.qty(seed) < 1.0:
                break
            land = land_names[added % len(land_names)]
            if self.sow(farmers[added % len(farmers)], crop, land=land) is None:
                break
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
        resident (or a call with no actor) draws from the store only."""
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
            self.eng.set_attr(self._town, "period", float(self.eng.node(self._town)["attrs"]["period"]) + 1.0)
            self._run()

    # ---------------------------------------------------- crops (seed -> grow -> harvest)
    def season(self): return self.eng.node(self._town)["attrs"]["season"]

    def set_season(self, season):
        """Turn the year to a season (spring/summer/autumn/winter) -- crops are sown in their season."""
        self.eng.set_attr(self._town, "season", season)

    def sow(self, sower, crop, *, land=None):
        """Sow a crop from its SEED -- but only IN ITS SEASON (you cannot sow a spring crop in autumn).
        Consumes one seed and plants a growing Crop (which then needs water each period, or it wilts).
        Returns None if it is the wrong season."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(sower, "sow"):
            return None
        land_cell = (self.map_position_node(self._land[land])
                     if land in self._land else None)
        if self._turn > 0 and land_cell is not None and self.actor_position(sower) != land_cell:
            return None
        spec = self.E.CROPS[crop]
        if spec["season"] != self.season():
            return None                                     # out of season -- nothing is sown
        if self.qty(spec["seed"]) < 1.0:
            return None                                     # another actor may have used the last seed
        self.set_stock(spec["seed"], max(0.0, self.qty(spec["seed"]) - 1.0))    # a seed is used
        c = self.eng.add_node("Crop", {"crop": crop, "age": 0.0, "thirst": 0.0, "thirst_epoch": 0.0,
                                       "alive": 1.0, "water": float(spec["water"]), "wilt": float(spec["wilt"]),
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
        if (float(attrs.get("alive", 0.0)) != 1.0 or float(attrs.get("thirst", 0.0)) <= 0.0
                or self.qty("water") < float(attrs.get("water", 0.0))):
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "water"):
            return False
        self.eng.set_attr(self._actor(actor), "water_armed", 1.0)
        self.eng.set_attr(crop_node, "water_armed", 1.0)
        self.set_stock("water", self.qty("water") - float(attrs.get("water", 0.0)))
        self.eng.set_attr(crop_node, "thirst", 0.0)
        self.eng.set_attr(crop_node, "water_armed", 0.0)
        self._run()
        return float(self.eng.node(crop_node)["attrs"].get("thirst", 0.0)) == 0.0

    def harvest_crop(self, crop_node, *, harvester=None):
        """Harvest a MATURE living crop -> its yield of the product enters the store; the crop is done."""
        crop_cell = self.map_position_node(crop_node)
        if (self._turn > 0 and harvester is not None and crop_cell is not None
                and self.actor_position(harvester) != crop_cell):
            return 0.0
        if self._turn > 0 and not self._major_dispatch:
            if harvester is None or not self._claim_major_action(harvester, "harvest"):
                return 0.0
        a = self.eng.node(crop_node)["attrs"]
        if float(a["alive"]) == 1.0 and float(a["age"]) >= float(a["grow_periods"]):
            factor = self.crop_nitrogen_factor(crop_node)
            harvested = float(a["yield"]) * factor
            self.set_stock(a["harvest"], self.qty(a["harvest"]) + harvested)
            for kind, qty in self.E.CROPS[a["crop"]].get("byproducts", {}).items():
                self.set_stock(kind, self.qty(kind) + float(qty) * factor)
            # Harvesting is also the seed loop that makes a farm renewable.
            # The returned seed is a physical reserve, not a hidden crop
            # respawn; sowing still consumes it and remains seasonal.
            seed = self.E.CROPS[a["crop"]]["seed"]
            self.set_stock(seed, self.qty(seed) + float(self.E.CROPS[a["crop"]].get("seed_return", 1.0)))
            self.eng.set_attr(crop_node, "alive", 0.0)
            self.eng.remove_edge_unchecked(self._town, "has_crop", crop_node)
            return round(harvested, 4)
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
            return 0.0
        node = self._land[land]
        cell = self.map_position_node(node)
        if self._turn > 0 and cell is not None and self.actor_position(actor) != cell:
            return 0.0
        type_name = self.E.NITROGEN["fertiliser_type"]
        la = self.eng.node(node)["attrs"]
        room = float(la.get("nitrogen_capacity", 0.0)) - float(la.get("nitrogen", 0.0))
        amount = min(float(amount if amount is not None else self.E.NITROGEN["fertilise_amount"]),
                     room, self.type_available(type_name))
        if amount <= 0.0:
            return 0.0
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "fertilise"):
            return 0.0
        if self._consume_type(type_name, amount) is None:
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
            self.eng.remove_edge_unchecked(node, "carries", stock)
            self.eng.remove_node(stock)
        self._run()

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

    def use_as_store(self, name, item, holds, *, lock_id=0.0, locked=False):
        """Press a MADE container-item (a cooper's barrel, a joiner's chest) into service as a real
        container -- the SAME node gains a capacity (from the item data) + an inner Stock + a
        has_container edge, so the container rules fill it. A made barrel IS a container."""
        kind = self.tool_kind(item)
        spec = self._item_specs.get(kind, {})
        assert spec.get("container"), f"{kind} is not a container item"
        return self._wire_container(name, item, kind, holds, lock_id, locked)

    def give_key(self, actor, opens):
        k = self.eng.add_node("Key", {"opens": float(opens)})
        self.eng.add_edge_unchecked(self._actors[actor], "holds_key", k)
        return k

    def _container_accessible(self, actor, container):
        if container not in self._containers:
            return False
        if not self.is_locked(container):
            return True
        node = self._containers[container][0]
        lock_id = float(self.eng.node(node)["attrs"].get("lock_id", 0.0))
        return any(float(self.eng.node(key)["attrs"].get("opens", 0.0)) == lock_id
                   for key in self.eng.neighbours(self._actor(actor), "holds_key"))

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
        if (amount <= 0.0 or not self._container_accessible(actor, container)
                or self.inventory_qty(actor, kind) < amount):
            return False
        if self.used_volume(container) + amount * self.item_volume(kind) > self.capacity(container) + 1e-9:
            return False
        if (self.is_fluid(kind)
                and float(self.eng.node(self._containers[container][0])["attrs"].get("watertight", 0.0)) != 1.0):
            return False
        if (self.contents_weight(container) + amount * self.item_weight(kind)
                > float(self.eng.node(self._containers[container][0])["attrs"].get("max_load", 1e18)) + 1e-9):
            return False
        if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(actor, "put"):
            return False
        inners = self._containers[container][1]
        if kind not in inners:
            node = self._containers[container][0]
            container_kind = self.eng.node(node)["attrs"].get("kind", "")
            inners[kind] = self._new_inner_stock(node, container_kind, kind)
        source = self._inventory_stock(actor, kind)
        target = inners[kind]
        self.eng.set_attr(source, "qty", self.inventory_qty(actor, kind) - amount)
        self.eng.set_attr(target, "qty", self.contents(container, kind) + amount)
        self._refresh_carry_state(actor)
        self.eng.add_edge_unchecked(self._actor(actor), "put_into", self._containers[container][0])
        return True

    def fill(self, actor, container, kind, amount):
        """Fill `amount` of `kind` into a container (if it fits by volume and, for a fluid, the vessel
        is watertight). Containers accept content not listed in their initial `holds`; storage
        preferences affect decay, not permission."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "fill"):
            return False
        if kind not in self._containers[container][1]:
            node = self._containers[container][0]
            container_kind = self.eng.node(node)["attrs"].get("kind", "")
            self._containers[container][1][kind] = self._new_inner_stock(node, container_kind, kind)
        self.eng.set_attr(self._actors[actor], "fill_kind", kind)
        self.eng.set_attr(self._actors[actor], "fill_amount", float(amount))
        self.eng.set_attr(self._actors[actor], "fill_armed", 1.0); self._run()
        return True

    def empty(self, actor, container, kind, amount):
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "empty"):
            return False
        self.eng.set_attr(self._actors[actor], "empty_kind", kind)
        self.eng.set_attr(self._actors[actor], "empty_amount", float(amount))
        self.eng.set_attr(self._actors[actor], "empty_armed", 1.0); self._run()
        return True

    def fetch(self, actor, kind, amount=1.0, *, source=None):
        """Carry physical stock from a store/container into the actor's carrier.

        Fetching is deliberately separate from buying: it is a handling action
        that changes location and ownership of physical stock, with no market
        or transaction record.  The default source is the town's mapped store;
        a named container may also be used when the actor can access it.
        """
        self._actor(actor)
        amount = float(amount)
        if amount <= 0.0:
            return False
        if source is None:
            source_cell = self.map_position_node(self._store)
            if self._turn > 0 and self.actor_position(actor) != source_cell:
                return False
            if self.qty(kind) < amount:
                return False
            if not self._move_stock_to_inventory(actor, kind, amount):
                return False
        else:
            if source not in self._containers or not self._container_accessible(actor, source):
                return False
            if self.container_position(source) != self.actor_position(actor):
                return False
            if self.contents(source, kind) < amount:
                return False
            if (self.used_volume(self._actor_inventories[actor])
                    + amount * self.item_volume(kind) > self.capacity(self._actor_inventories[actor]) + 1e-9):
                return False
            inner = self._containers[source][1][kind]
            self.eng.set_attr(inner, "qty", self.contents(source, kind) - amount)
            target = self._inventory_stock(actor, kind, create=True)
            self.eng.set_attr(target, "qty", self.inventory_qty(actor, kind) + amount)
            self._refresh_carry_state(actor)
        self.eng.add_edge_unchecked(self._actor(actor), "fetched", self._store)
        return True

    def lock(self, actor): self.eng.set_attr(self._actors[actor], "lock_armed", 1.0); self._run()
    def unlock(self, actor): self.eng.set_attr(self._actors[actor], "unlock_armed", 1.0); self._run()

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
                                        "skill_levels": self.E.initial_skill_levels((role,) + tuple(trades), skill)[0],
                                        "metaskill_levels": self.E.initial_skill_levels((role,) + tuple(trades), skill)[1],
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
                                        "fatigue": 0.0, "busy": 0.0,
                                        "carried_weight": 0.0, "carry_ratio": 0.0,
                                        "carry_speed": 1.0, "carry_move_energy": 1.0,
                                        "carry_overloaded": 0.0, "carry_move_cooldown": 0.0,
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
                                        "eat_armed": 0.0,
                                        "appr_epoch": 0.0,   # apprenticeship: skill grows under a master
                                        # reading/writing + general capability (class-graded; raised at school)
                                        "literacy": lit, "capability": cap, "learn": float(learn), "school_epoch": 0.0,

                                        # container-op state
                                        "fill_armed": 0.0, "fill_amount": 0.0, "fill_kind": "",
                                        "empty_armed": 0.0, "empty_amount": 0.0, "empty_kind": "",
                                        "lock_armed": 0.0, "unlock_armed": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_actor", a)
        self._actors[name] = a
        self._alive_snapshot[name] = True
        body = self.eng.add_node("Body", {
            "health": float(defaults["body"]["health"]), "mood": float(defaults["body"]["mood"]), "satiety": 0.0,
            "last_food": -1.0, "food_run": 0.0,
            "str_base": float(defaults["body"]["str_base"]), "sta_base": float(defaults["body"]["sta_base"]),
            "str_train": 0.0,
            "sta_train": 0.0, "strength": 1.0, "stamina": 1.0,
            "stats_dirty": 0.0, "stamina_reserve": float(defaults["body"]["stamina_reserve"])})
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
            self._actor_positions[name] = home_cell
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
        attrs = {
            "content": str(content), "loudness": float(loudness),
            "speaker": speaker, "target": target or "", "turn": float(self._turn),
            "heard": 1.0 if target is None or self.actor_position(speaker) == self.actor_position(target) else 0.0,
        }
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
            if self.eng.node(utterance)["attrs"]["heard"] == 1.0:
                self.eng.add_edge_unchecked(self._actor(target), "heard", utterance)
        self._utterances[len(self._utterances) + 1] = utterance
        return utterance

    def heard_utterances(self, actor, *, limit=20):
        """Return recent speech delivered to ``actor`` as cognition input.

        This is deliberately a projection of communication records, not a
        semantic interpretation by the world.  A backend receives the exact
        text and opaque provider payload that were delivered to it.
        """
        self._actor(actor)
        records = []
        for node in self._utterances.values():
            attrs = self.eng.node(node)["attrs"]
            target = str(attrs.get("target", ""))
            heard = bool(float(attrs.get("heard", 0.0)))
            if not heard or (target not in {"", str(actor)}):
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
            return False
        if not self._claim_major_action(actor, "complete_request"):
            return False
        self.eng.set_attr(req, "status", 2.0)
        self.eng.set_attr(req, "result", str(result))
        self.eng.add_edge_unchecked(self._actor(actor), "completed_request", req)
        return True

    def requests_for(self, actor):
        return list(self.eng.neighbours(self._actor(actor), "received_request"))

    # ---------------------------------------------------- health, life history, and ecology
    def injure(self, actor, *, severity=None, cause="accident"):
        if severity is None:
            severity = self.E.CARE["injury_severity"]
        node = self._actors[actor]
        a = self.eng.node(node)["attrs"]
        health = max(0.0, float(a.get("health_value", 1.0)) - float(severity))
        self.eng.set_attr(node, "health_value", health)
        self.eng.set_attr(node, "health", "injured")
        self.eng.set_attr(node, "injury", float(severity))
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
        if medicine and self.qty("medicine") < medicine:
            return False
        if medicine:
            self.set_stock("medicine", self.qty("medicine") - float(medicine))
        node = self._actors[patient]
        self.eng.set_attr(node, "health", "healthy")
        self.eng.set_attr(node, "disease", "")
        self.eng.set_attr(node, "injury", 0.0)
        self.eng.set_attr(node, "health_value", min(1.0, float(self.eng.node(node)["attrs"].get(
            "health_value", self.E.CARE["treat_health_base"])) + float(self.E.CARE["treat_health_gain"])))
        self.eng.add_edge_unchecked(self._actors[doctor], "treated", node)
        return True

    def care_for(self, caregiver, patient):
        """Perform one co-located care action for an injured or ill resident."""
        if caregiver not in self._actors or patient not in self._actors:
            return False
        if self._turn > 0 and self.actor_position(caregiver) != self.actor_position(patient):
            return False
        attrs = self.eng.node(self._actors[patient])["attrs"]
        if (attrs.get("health") == "healthy" and float(attrs.get("injury", 0.0)) <= 0.0
                and float(attrs.get("hunger", 0.0)) < float(self.E.CARE["care_hunger_need"])):
            return False
        medicine = 1.0 if self.qty("medicine") >= 1.0 and attrs.get("disease") else 0.0
        if medicine:
            return self.treat(caregiver, patient, medicine=medicine)
        care = self.E.CARE
        self.eng.set_attr(self._actors[patient], "injury",
                          max(0.0, float(attrs.get("injury", 0.0)) - float(care["care_injury_relief"])))
        self.eng.set_attr(self._actors[patient], "health_value",
                          min(1.0, float(attrs.get("health_value", 1.0)) + float(care["care_health_gain"])))
        if float(self.eng.node(self._actors[patient])["attrs"].get("injury", 0.0)) <= 0.0:
            self.eng.set_attr(self._actors[patient], "health", "healthy")
        self.eng.add_edge_unchecked(self._actors[caregiver], "cared_for", self._actors[patient])
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
        self.eng.set_attr(node, "death_event", float(event.value))
        self.eng.set_attr(node, "death_recorded", 1.0)
        self._deaths.append({"actor": actor, "day": self.calendar()["day"],
                             "cause": str(cause), "event": str(event)})
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
            injury = float(a.get("injury", 0.0))
            care = self.E.CARE
            if injury > 0.0:
                self.eng.set_attr(node, "injury", max(0.0, injury - float(care["daily_injury_recovery"])))
                self.eng.set_attr(node, "health_value",
                                  min(1.0, float(a.get("health_value", 1.0)) + float(care["daily_health_recovery"])))
                if injury <= float(care["recovered_injury_below"]):
                    self.eng.set_attr(node, "health", "healthy")
            if float(a.get("hunger", 0.0)) >= float(care["malnourished_hunger"]):
                self.eng.set_attr(node, "health", "malnourished")
            if a.get("disease"):
                health = max(0.0, float(a.get("health_value", 1.0)) - float(care["disease_health_loss"]))
                self.eng.set_attr(node, "health_value", health)
                if health <= 0.0:
                    self.record_death(name, cause=str(a.get("disease")))
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
                                "score": 0.0})
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
        if market_cell is not None:
            market_move_added = False
            for kind in self._item_specs:
                if self.qty(kind) < 1.0 or not self._inventory_can_receive(actor, kind):
                    continue
                if any(option.get("action") == "fetch" and option.get("kind") == kind
                       for option in options):
                    continue
                is_food = bool(self._item_specs.get(kind, {}).get("food"))
                if self.actor_position(actor) == market_cell:
                    key = target_key(("store", kind))
                    options.append({"action": "fetch", "kind": kind, "trade": "", "recipe": "",
                                    "stock_source": "town", "food": is_food,
                                    "target": key, "score": 0.0})
                elif reachable_destination(market_cell) and not market_move_added:
                    key = target_key(market_cell)
                    has_edible = any(
                        bool(spec.get("food")) and self.qty(k) >= 1.0
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
        if market_cell is not None:
            for trade, shop_node in self._shops.items():
                output = self.eng.node(shop_node)["attrs"].get("output_kind", "")
                if output not in self._item_specs or self.qty(output) < 1.0:
                    continue
                is_food = bool(self._item_specs.get(output, {}).get("food"))
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
        # Ordinary object movement is a physical option, not a purchase,
        # permission check, or interpretation of ownership.  Keep these
        # choices in the same backend affordance boundary as other actions;
        # the cognition policy decides whether to use them.
        options.extend(option for option in self.physical_object_affordances(actor)
                       if option.get("action") == "move_object")
        for recipe in self.E.RECIPES:
            if (not busy and self._can_attempt(actor, recipe["name"])
                    and self._recipe_inputs_available(recipe["name"], actor)):
                out_kind = recipe.get("out", [""])[0]
                options.append({"action": "work", "kind": out_kind, "trade": "", "target": "",
                                "recipe": recipe["name"],
                                "score": 0.0})
        # Rest is afforded only when the same reserve threshold that gates
        # physical recovery says it can apply. A resident with a full reserve
        # idles by proposing no major action; do not publish a rest choice that
        # enactment will reject as a no-op.
        if self.stamina_reserve(actor) < 0.8:
            options.append({"action": "rest", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        # Target keys are intentionally opaque and may be rebuilt on every
        # observation.  Expose the physical destination alongside a movement
        # affordance so a cognition backend can safely retain a route across
        # turns without retaining the world's temporary target map.
        for option in options:
            if option.get("action") == "move":
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
        self._actor_targets[actor] = targets
        return options

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

    def actor_affordances(self, actor):
        """Return the current legal, observed choices for a backend or UI."""
        self._actor(actor)
        return [dict(option) for option in self._actor_options(actor)]

    def perform_plan(self, actor):
        """Enact the action selected by the resident's Ocelot graph."""
        plan = self._decide_actor(actor)
        return self._enact_plan(actor, plan)

    def enact_plan(self, actor, plan):
        """Enact an external backend proposal after rebuilding its target map."""
        self._actor(actor)
        plan = dict(plan)
        action = plan.get("action")
        needs_targets = not (
            (action == "move" and plan.get("destination") is not None)
            or action in {"rest", "eat", "work", "move_object"}
            or (action == "transfer" and plan.get("recipient"))
            or (action == "take")
        )
        if needs_targets:
            self._actor_options(actor)
        return self._enact_plan(actor, plan)

    def _enact_plan(self, actor, plan):
        """Shared physical enactment for Ocelot and arbitrary cognition backends."""
        if plan["action"] == "give":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._actors:
                return self.major_action(actor, "give", recipient=target,
                                         kind=plan["kind"], amount=plan.get("amount", 1.0))
            # A shop is not a physical recipient. Purchase intent, speech,
            # acceptance, and any payment are choices owned by cognition.
            return False
        if plan["action"] in {"transfer", "take"}:
            if plan["action"] == "transfer":
                recipient = plan.get("recipient") or self._actor_targets[actor].get(plan.get("target", ""))
                return self.major_action(actor, "transfer", source=actor,
                                         recipient=recipient, kind=plan.get("kind"),
                                         amount=plan.get("amount", 1.0))
            return self.major_action(
                actor, plan["action"], source=plan.get("source"),
                recipient=plan.get("recipient"), kind=plan.get("kind"),
                amount=plan.get("amount", 1.0))
        if plan["action"] == "rest":
            # Rest is a real major action, but a healthy resident's default
            # idle option is not a physical rest event.  This prevents every
            # unoccupied turn from consuming the slot while preserving rest
            # as the chosen action once the body actually needs recovery.
            if self.stamina_reserve(actor) >= 0.8:
                return False
            return self.major_action(actor, "rest", amount=1.0)
        if plan["action"] == "eat":
            equipment = self._serving_equipment(actor, plan["kind"])
            kwargs = {"kind": plan["kind"]}
            if equipment is not None:
                kwargs.update(vessel=equipment[0], utensil=equipment[1])
            return self.major_action(actor, "eat", **kwargs)
        if plan["action"] == "work":
            return self.major_action(actor, "start", action_name=plan["recipe"])
        if plan["action"] == "move":
            target = plan.get("destination")
            if target is None:
                target = self._actor_targets[actor].get(plan.get("target", ""))
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "move_object":
            return self.major_action(actor, "move_object",
                                     object_id=plan.get("object_id", plan.get("item")),
                                     destination=plan.get("destination", plan.get("target")))
        if plan["action"] == "put":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target is not None:
                return self.major_action(actor, "put", container=target, kind=plan["kind"], amount=1.0)
        if plan["action"] == "fetch":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            source = target if target in self._containers else None
            return self.major_action(actor, "fetch", kind=plan["kind"], amount=1.0, source=source)
        if plan["action"] == "tend_animals":
            target = plan.get("animal") or self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._animals:
                destination = self.map_position_node(self._animals[target])
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "tend_animals", animal=target, task=plan["kind"])
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "build":
            target = plan.get("project") or self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._building_projects:
                cells = list(self.eng.neighbours(self._building_projects[target], "at_cell"))
                destination = self.map_position_node(cells[0]) if cells else None
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "build", project=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "maintain":
            target = plan.get("name") or self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._infrastructure:
                destination = self.map_position_node(self._infrastructure[target])
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "maintain", name=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "care":
            target = plan.get("patient") or self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._actors:
                destination = self.actor_position(target)
                if destination is not None and self.actor_position(actor) != destination:
                    return self.major_action(actor, "move", destination=destination)
                return self.major_action(actor, "care", patient=target)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] in {"water", "harvest", "sow", "fertilise"}:
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if plan["action"] in {"water", "harvest"}:
                crop_node = plan.get("crop_node")
                if crop_node is not None and crop_node in {int(node) for node in self._crops.values()}:
                    target = crop_node
            elif plan.get("sow_kind") and plan.get("land"):
                target = (plan["sow_kind"], plan["land"])
            if target is not None:
                return self.major_action(actor, plan["action"], target=target)
        return False

    def resolve_actor_turn(self):
        """Settle deferred physical effects after an explicitly submitted turn."""
        self._run()

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
                or not self.is_alive(target)
                or self.actor_position(speaker) != self.actor_position(target)):
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
                or not self.is_alive(target)
                or self.actor_position(speaker) != self.actor_position(target)):
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
    def export_state(self, *, event_tail=None):
        """Return a JSON-safe snapshot of the canonical world graph."""
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
        return {"schema": "townview/1", "scenario": {
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
                "transactions": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._transactions.items()],
                "proposals": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._proposals.items()],
                "cases": [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._cases.items()],
                "births": list(self._births), "deaths": list(self._deaths),
                "sanity": self.sanity_report(),
                "report": self.report(), "report_history": self.report_history()}

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

    def major_action(self, actor, action, *args, **kwargs):
        """Dispatch one substantial action through the unified turn budget.

        Existing low-level ``do``/``start`` calls remain useful for scenario
        setup and timed-job tests.  Simulation code should use this method (or
        ``perform_major_action``) so the one-action rule is enforced.
        """
        if action == "move":
            destination = kwargs.get("destination", args[0] if args else None)
            current = self.actor_position(actor)
            if (destination is None or current is None or destination not in self._map_cells
                    or self.distance(current, destination) is None
                    or not self._claim_major_action(actor, "move")):
                return False
            return self.move_actor(actor, destination)
        if action == "move_object":
            object_id = kwargs.get("object_id", kwargs.get("item", args[0] if args else None))
            destination = kwargs.get("destination", kwargs.get("target", args[1] if len(args) > 1 else None))
            if (object_id is None or destination is None
                    or not self._claim_major_action(actor, "move_object")):
                return False
            return self.move_physical_object_as_actor(actor, object_id, destination)
        if action == "give":
            recipient = kwargs.get("recipient", kwargs.get("target", args[0] if args else None))
            kind = kwargs.get("kind", args[1] if len(args) > 1 else None)
            amount = kwargs.get("amount", args[2] if len(args) > 2 else 1.0)
            if (recipient not in self._actors or kind is None
                    or actor not in self._actors
                    or not self._physical_transfer_precheck(actor, recipient, kind, amount)
                    or not self._claim_major_action(actor, "give")):
                return False
            return self._physical_transfer(actor, recipient, kind, amount)
        if action == "transfer":
            source = kwargs.get("source", args[0] if args else None)
            recipient = kwargs.get("recipient", args[1] if len(args) > 1 else None)
            kind = kwargs.get("kind", args[2] if len(args) > 2 else None)
            amount = kwargs.get("amount", args[3] if len(args) > 3 else 1.0)
            if (source is None or recipient is None or kind is None
                    or actor != source
                    or not self._physical_transfer_precheck(source, recipient, kind, amount)
                    or not self._claim_major_action(actor, action)):
                return False
            return self._physical_transfer(source, recipient, kind, amount)
        if action == "take":
            # A resident's carried stock is not unattended merely because a
            # backend can name its holder.  Taking held goods needs an explicit
            # contested physical mechanism; this action does not invent one.
            return False
        if action == "put":
            container = kwargs.get("container", args[0] if args else None)
            kind = kwargs.get("kind", args[1] if len(args) > 1 else None)
            amount = kwargs.get("amount", args[2] if len(args) > 2 else 1.0)
            if container is None or kind is None or not self._claim_major_action(actor, "put"):
                return False
            self._major_dispatch = True
            try:
                return self.put(actor, container, kind, amount)
            finally:
                self._major_dispatch = False
        if action == "pick_up":
            item = kwargs.get("item", args[0] if args else None)
            if item is None or not self._claim_major_action(actor, "pick_up"):
                return False
            self._major_dispatch = True
            try:
                return self.pick_up(actor, item)
            finally:
                self._major_dispatch = False
        if action == "drop":
            item = kwargs.get("item", args[0] if args else None)
            if item is None or not self._claim_major_action(actor, "drop"):
                return False
            self._major_dispatch = True
            try:
                return self.drop_item(actor, item)
            finally:
                self._major_dispatch = False
        if action == "sell":
            trade = kwargs.get("trade", args[0] if args else None)
            kind = kwargs.get("kind", args[1] if len(args) > 1 else None)
            amount = kwargs.get("amount", args[2] if len(args) > 2 else 1.0)
            if not self._claim_major_action(actor, action):
                return False
            self._major_dispatch = True
            try:
                return self.sell_to_shop(actor, trade, kind, amount)
            finally:
                self._major_dispatch = False
        if action == "sell_labor":
            if not self._claim_major_action(actor, action):
                return False
            return self.sell_labor(actor, kwargs.get("trade", args[0] if args else None),
                                   kwargs.get("amount", args[1] if len(args) > 1 else 2.0))
        if action == "eat":
            if not self._claim_major_action(actor, "eat"):
                return False
            self._major_dispatch = True
            try:
                return self.eat(actor, kwargs.get("kind", args[0] if args else None),
                                vessel=kwargs.get("vessel"), utensil=kwargs.get("utensil"),
                                source=kwargs.get("source"))
            finally:
                self._major_dispatch = False
        if action == "rest":
            if not self._claim_major_action(actor, "rest"):
                return False
            return self.rest(actor, kwargs.get("amount", args[0] if args else 1.0))
        if action == "fetch":
            kind = kwargs.get("kind", args[0] if args else None)
            amount = kwargs.get("amount", args[1] if len(args) > 1 else 1.0)
            source = kwargs.get("source")
            if kind is None or not self._claim_major_action(actor, "fetch"):
                return False
            self._major_dispatch = True
            try:
                return self.fetch(actor, kind, amount, source=source)
            finally:
                self._major_dispatch = False
        if action == "build":
            project = kwargs.get("project", args[0] if args else None)
            labour = kwargs.get("labour", args[1] if len(args) > 1 else 1.0)
            if project is None or not self._claim_major_action(actor, "build"):
                return False
            self._major_dispatch = True
            try:
                return self.advance_building(project, actor, labour=labour) is not None
            finally:
                self._major_dispatch = False
        if action == "maintain":
            name = kwargs.get("name", args[0] if args else None)
            labour = kwargs.get("labour", args[1] if len(args) > 1 else 1.0)
            if name is None or not self._claim_major_action(actor, "maintain"):
                return False
            self._major_dispatch = True
            try:
                return self.maintain_infrastructure(actor, name, labour=labour)
            finally:
                self._major_dispatch = False
        if action == "care":
            patient = kwargs.get("patient", args[0] if args else None)
            if patient is None or not self._claim_major_action(actor, "care"):
                return False
            self._major_dispatch = True
            try:
                return self.care_for(actor, patient)
            finally:
                self._major_dispatch = False
        if action == "tend_animals":
            animal = kwargs.get("animal", args[0] if args else None)
            task = kwargs.get("task", args[1] if len(args) > 1 else "milk")
            if animal is None or animal not in self._animals or not self._claim_major_action(actor, "tend_animals"):
                return False
            self._major_dispatch = True
            try:
                if task not in self.E.ANIMAL_HUSBANDRY:
                    return False
                return self._husbandry_yield(actor, animal, task) > 0.0
            finally:
                self._major_dispatch = False
        if action in ("work", "make", "start"):
            recipe = kwargs.get("action_name", kwargs.get("recipe", args[0] if args else None))
            if recipe is None:
                return False
            operation = self.start if action == "start" else self.do
            if not self._can_attempt(actor, recipe):
                return False
            if not self._claim_major_action(actor, action):
                return False
            self._major_dispatch = True
            try:
                return operation(actor, recipe)
            finally:
                self._major_dispatch = False
        if action in {"water", "harvest", "sow", "fertilise"}:
            target = kwargs.get("target", args[0] if args else None)
            if not self._claim_major_action(actor, action):
                return False
            self._major_dispatch = True
            try:
                if action == "fertilise":
                    return self.fertilise(actor, target, kwargs.get("amount")) > 0.0
                if action == "water":
                    return self.water_crop(actor, target)
                if action == "harvest":
                    return bool(self.harvest_crop(target, harvester=actor))
                crop, land = target
                return self.sow(actor, crop, land=land) is not None
            finally:
                self._major_dispatch = False
        if action == "complete_request":
            request = kwargs.get("request", args[0] if args else None)
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
        raise ValueError(f"unknown free action: {action}")

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
        """Whether the actor could make it mechanically: skilled enough to attempt."""
        return self._can_attempt(actor, action_name)

    # ---------------------------------------------------- do an action (the ONE engine)
    def _open_job(self, actor, action_name, remaining):
        asp = self._actions[action_name]
        action_attrs = self.eng.node(asp)["attrs"]
        job = self.eng.add_node("Job", {"remaining": float(remaining), "last_tick": 0.0,
                                        "min_quality": 1.0, "item_inputs": 0.0,
                                        "canonical_actor": str(actor)})
        self.eng.add_edge_unchecked(self._actors[actor], "on_job", job)
        self.eng.add_edge_unchecked(job, "runs", asp)
        self.eng.set_attr(self._actors[actor], "busy", 1.0)
        for need in self.eng.neighbours(asp, "in_need"):
            a = self.eng.node(need)["attrs"]
            jn = self.eng.add_node("Need", {"kind": a["kind"], "qty": float(a["qty"]), "met": 0.0,
                                            "is_item": float(a.get("is_item", 0.0)),
                                            "slot_type": a.get("slot_type", ""), "drawn_from": ""})
            self.eng.add_edge_unchecked(job, "need", jn)
        for tu in self.eng.neighbours(asp, "in_tool"):
            a = self.eng.node(tu)["attrs"]
            jt = self.eng.add_node("ToolUse", {"kind": a["kind"], "met": 0.0})
            self.eng.add_edge_unchecked(job, "uses", jt)

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

    def set_capacities(self, actor, *, aptitude=None, talents=None, limitations=None):
        """Set an actor's capacities (setup, or a scenario authoring a particular person)."""
        node = self._actors[actor]
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

    def draw_capacities(self, actor, *, seed=0, sex=None):
        """Draw an actor's capacities from the population distributions (E.draw_person_capacities),
        deterministically from `seed` and their name."""
        import zlib
        import numpy as np
        rng = np.random.default_rng((int(seed) * 1_000_003) ^ zlib.crc32(str(actor).encode()))
        age = float(self.eng.node(self._actors[actor])["attrs"].get("age", 30.0))
        drawn = self.E.draw_person_capacities(rng, age=age, sex=sex)
        return self.set_capacities(actor, aptitude=drawn["aptitude"], talents=drawn["talents"],
                                   limitations=drawn["limitations"])

    def effective_skill(self, actor, skill):
        """The actor's working level at a skill: own level, lifted by their closest skill through the
        metaskill (sharpened by aptitude), lowered by any limitations."""
        a = self.eng.node(self._actors[actor])["attrs"]
        return round(self.E.effective_skill(self._levels(actor), a.get("metaskill_levels", {}), skill,
                                       self._person(actor)), 4)

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
        """Admissibility depends on mechanical capability, not assumed knowledge: the actor must be
        SKILLED enough and (for seasonal gathering) it must be the right season. Open (household)
        recipes also need a body strong enough for the work and the recipe's tools in the actor's
        own hands."""
        if not (action_name in self._actions and self._skilled_enough(actor, action_name)
                and self._recipe_in_season(action_name)):
            return False
        recipe = self._recipe_specs.get(action_name, {})
        if recipe.get("open"):
            strength_needed, _stamina = self.E.recipe_exertion(action_name)
            if self.strength(actor) + 1e-9 < strength_needed:
                return False
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

    def do(self, actor, action_name):
        """Perform an action INSTANTLY (no timer). Refused if the actor does not KNOW the recipe or is
        not SKILLED enough (below its min_skill floor)."""
        if not self._can_attempt(actor, action_name):
            return False
        if not self._recipe_tools_usable(actor, action_name):
            return False
        # Calls made before the first simulation tick remain convenient setup
        # operations.  Once the clock is running, a direct craft is a major
        # action too; the explicit dispatcher suppresses this second charge.
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "work"):
            return False
        self._open_job(actor, action_name, 0.0); self._run()
        return True

    def start(self, actor, action_name):
        """START a TIMED action; refused if the actor does not know OR is not skilled enough for it."""
        if not self._can_attempt(actor, action_name):
            return False
        if not self._recipe_tools_usable(actor, action_name):
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "start"):
            return False
        mins = float(self.eng.node(self._actions[action_name])["attrs"]["time_minutes"])
        self._open_job(actor, action_name, math.ceil(mins / float(self.E.TIME["minutes_per_tick"]))); self._run()
        return True

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
            if int(float(self.eng.node(self._town)["attrs"].get("day", 0.0))) > old_day:
                self._daily_life_tick()
            self._job_tick_armed = True
            self._run()
            self._job_tick_armed = False
            # A world tick advances physical time only. Animal and resident
            # decisions are submitted by an explicit game/backend session.
            self._run()
            # Last, so every crossing this turn is counted before untrodden
            # ground grows back.
            self._terrain_recovery_tick()

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
        for _ in range(int(times)):
            self.eng.set_attr(tool, "use_armed", 1.0); self._run()

    def repair_tool(self, maker, tool):
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(maker, "repair"):
            return False
        self.eng.add_edge_unchecked(self._actors[maker], "repairs", tool)
        self.eng.set_attr(tool, "repair_armed", 1.0); self._run()
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
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(dyer, "dye"):
            return None
        dye = self.set_stock(dye_kind, self.qty(dye_kind))
        self.eng.set_attr(garment, "dye_armed", 1.0)
        self.eng.add_edge_unchecked(garment, "dyed_with", dye)
        colour = self._item_specs.get(dye_kind, {}).get("colour", dye_kind)
        self.eng.set_attr(garment, "colour", colour)
        self.set_stock(dye_kind, max(0.0, self.qty(dye_kind) - 1.0))
        self._run()
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
        self._run()
        return True

    def take_off(self, actor, garment):
        """Take a garment off -- no longer worn, no longer protecting."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "take_off"):
            return False
        self.eng.remove_edge_unchecked(self._actors[actor], "wears", garment)
        self._run()
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
        self._run()

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
    def fatigue(self, actor): return round(float(self.eng.node(self._actors[actor])["attrs"]["fatigue"]), 4)

    def rest(self, actor, amount=1.0):
        """Rest as a physical body event; it recovers held stamina reserve."""
        self._actor(actor)
        rest = self.eng.add_node("Rest", {"amount": float(amount), "rest_done": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "rested", rest)
        self._run()
        return self.stamina_reserve(actor)
    def body_state(self, actor):
        body = self._bodies[actor]
        attrs = self.eng.node(body)["attrs"]
        return {"health": round(float(attrs.get("health", 1.0)), 4),
                "mood": round(float(attrs.get("mood", 0.5)), 4),
                "strength": round(float(attrs.get("strength", 1.0)), 4),
                "stamina": round(float(attrs.get("stamina", 1.0)), 4),
                "stamina_reserve": round(float(attrs.get("stamina_reserve", 1.0)), 4)}

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
