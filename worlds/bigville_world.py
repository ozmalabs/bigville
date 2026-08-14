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

import math
import os
import random
import sys
from collections import deque

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import substrate_rs                                     # noqa: E402
from substrate.seed_loader import manifest_for          # noqa: E402
from substrate.boot_core import boot_core, load_seeds_into  # noqa: E402
from substrate.world_adapter import WorldAdapter       # noqa: E402
from domains import bigville_entities as E               # noqa: E402
from worlds.bigville_bond_world import KNOBS as BOND_KNOBS, SLOT_DEFAULTS as BOND_SLOTS  # noqa: E402
from worlds.bigville_speech_world import (  # noqa: E402
    ENCOUNTER_DEFAULTS as SPEECH_ENCOUNTER_DEFAULTS,
    KIND_LABEL as SPEECH_KIND_LABEL,
    SPEECH_MENU,
    _OPT_KEYS as SPEECH_OPTION_KEYS,
)

MINUTES_PER_TICK = 15.0


class BigvilleOcelotActor:
    """One resident mind, backed by an independent Ocelot substrate graph.

    This is deliberately a small host wrapper.  The resident's choice is made
    by the seeded ``bigville_actor_decision`` rule over the affordances the
    world publishes; the wrapper only provides the graph and runs one native
    cognition pass.
    """

    def __init__(self, name):
        self.name = str(name)
        self.s, self.agent = boot_core()
        self.inner = self.s._inner
        self.inner.load_seed_manifest(manifest_for("bigville_actor_decision"), self.agent)
        # The speech faculty is held by the resident as graph data.  The town
        # publishes encounters; these rules decide whether this resident
        # speaks and what kind of turn it makes.  No clock or Python schedule
        # is part of that choice.
        self.inner.load_seed_manifest(manifest_for("bigville_speech_decide"), self.agent)
        self.inner.load_seed_manifest(manifest_for("bigville_loud_comm"), self.agent)
        # Keep the speech-act vocabulary (including request/question) in the
        # resident's conceptual substrate.  It interprets free text; it is not
        # a Bigville affordance.
        load_seeds_into(self.s, self.agent, ["conversation"])
        self.s.set_attr(self.agent, "name", self.name)
        self.s.set_attr(self.agent, "chosen_action", "")
        self.s.set_attr(self.agent, "chosen_kind", "")
        self.s.set_attr(self.agent, "chosen_trade", "")
        self.s.set_attr(self.agent, "chosen_recipe", "")
        self.s.set_attr(self.agent, "chosen_target", "")
        self.s.set_attr(self.agent, "decision_armed", 0.0)
        self.speech_options = []
        self.speech_bonds = {}
        self.speech_encounters = {}
        self.speech_choices = {}
        # The speech decision above selects an occasion/kind.  The actual
        # utterance is produced by the existing goal-driven communicative
        # faculty, which renders a structured meaning from its graph-resident
        # language machinery and models addressee uptake.
        self.voice = WorldAdapter(seeds=())
        self._voice_targets = {}
        self._mint_speech_menu()

    def _mint_speech_menu(self):
        """Install this resident's held speech-option vocabulary."""
        for option in SPEECH_MENU:
            attrs = {key: 0.0 for key in SPEECH_OPTION_KEYS}
            attrs.update(option)
            node = self.s.add_node("SpeechOption", attrs)
            self.speech_options.append(node)

    def _speech_bond(self, target, relationship=None):
        """Mirror the resident's directed relationship model into its mind."""
        bond = self.speech_bonds.get(target)
        if bond is None:
            attrs = dict(BOND_SLOTS)
            attrs.update(BOND_KNOBS)
            attrs.update({"holder_name": self.name, "toward_name": str(target),
                          "prior_kind": "chosen"})
            bond = self.s.add_node("Bond", attrs)
            self.inner.add_edge_unchecked(self.agent, "holds_bond", bond)
            target_node = self.s.add_node("Townsperson", {"name": str(target)})
            self.inner.add_edge_unchecked(bond, "toward", target_node)
            self.speech_bonds[target] = bond

        # Relationship state is world I/O.  The speech rule reads the copied
        # slots; it still owns the selection of a speech option.
        if relationship:
            strength = float(relationship.get("strength", 0.0))
            kind = str(relationship.get("kind", "acquaintance"))
            self.s.set_attr(bond, "tie_strength", max(0.0, strength))
            self.s.set_attr(bond, "affect_affection", max(0.0, strength))
            self.s.set_attr(bond, "affect_resentment",
                            max(0.0, -strength) if kind == "feud" else 0.0)
            self.s.set_attr(bond, "prior_kind", kind)
        return bond

    def decide_speech(self, target, *, relationship=None, obligation=False,
                      fpp_is_greeting=False, fpp_is_question=False,
                      share_salience=0.0, goal_pressure=0.0, stranger=False,
                      arousal=0.4, loquacity_threshold=1.0):
        """Run the held spontaneous-speech faculty for one physical encounter.

        The caller only supplies observed encounter inputs.  The chosen kind
        comes back from ``bigville_speech_decide`` and is not selected here.
        """
        bond = self._speech_bond(target, relationship)
        old = self.speech_encounters.get(target)
        if old is not None:
            self.inner.remove_node(old)
        attrs = dict(SPEECH_ENCOUNTER_DEFAULTS)
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
        encounter = self.s.add_node("Encounter", attrs)
        self.inner.add_edge_unchecked(encounter, "at_bond", bond)
        self.speech_encounters[target] = encounter
        self.inner.run_rules(1000000)
        code = int(round(float(self.s.node(encounter)["attrs"].get("chosen_speech_code", -1.0))))
        kind = SPEECH_KIND_LABEL.get(code, "undecided")
        choice = {"target": target, "code": code, "kind": kind,
                  "spoken": code not in (-1, 0), "encounter": encounter}
        if choice["spoken"]:
            utterance = self.s.add_node("Utterance", {
                "speaker_arousal": attrs["speaker_arousal"],
                "base_loudness": 1.0, "loud_arousal_gain": 0.6,
                "max_loudness": 100.0, "loudness_on": 1.0,
                "choice_on": 1.0, "loud_armed": 1.0,
                "chosen_loudness": 0.0, "eff_loudness": 0.0,
            })
            self.inner.add_edge_unchecked(utterance, "spoken_by", self.agent)
            self.inner.run_rules(1000000)
            choice["loudness"] = float(self.s.node(utterance)["attrs"].get("eff_loudness", 1.0))
        self.speech_choices[target] = choice
        return choice

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

    def decide(self):
        """Run the Ocelot graph and read its selected affordance."""
        self.inner.run_rules(1000000)
        attrs = self.s.node(self.agent)["attrs"]
        return {"action": attrs.get("chosen_action", ""),
                "kind": attrs.get("chosen_kind", ""),
                "trade": attrs.get("chosen_trade", ""),
                "recipe": attrs.get("chosen_recipe", ""),
                "target": attrs.get("chosen_target", "")}

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
            "held_frames": typed_nodes(("Frame", "Microtheory", "Concept")),
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
    def __init__(self, *, map_seed=305000, autonomous_actors=True):
        self.eng = substrate_rs.Substrate()._inner
        self.eng.load_seed_manifest(manifest_for("bigville_action_general"), None)   # the ONE making engine
        self.eng.load_seed_manifest(manifest_for("bigville_action_decide"), None)    # observed-demand decision
        self.eng.load_seed_manifest(manifest_for("bigville_action_container"), None) # containers + lock/key
        self.eng.load_seed_manifest(manifest_for("bigville_action_animal"), None)    # animals eat / starve
        self.eng.load_seed_manifest(manifest_for("bigville_action_merchant"), None)  # a merchant delivers goods
        self.eng.load_seed_manifest(manifest_for("bigville_action_life"), None)      # crops grow; residents eat
        self.eng.load_seed_manifest(manifest_for("bigville_action_decay"), None)     # wear over time + spoilage
        self.eng.load_seed_manifest(manifest_for("bigville_action_clothing"), None)  # clothes: dyed, worn, protective
        self.eng.load_seed_manifest(manifest_for("bigville_action_skill"), None)     # apprenticeship: skill grows under a master
        # Physical exertion belongs to the resident's Body layer.  Movement
        # and carrying must feed Effort into bd_exert_cost rather than invent
        # a second Agent-level energy ledger.
        self.eng.load_seed_manifest(manifest_for("bigville_body"), None)
        self._town = self.eng.add_node("Town", {"name": "Bigville", "clock": 0.0, "period": 0.0,
                                                "day": 0.0, "hour": 6.0, "week": 0.0, "year": 1.0,
                                                "season": "spring", "observed_harvest": 0.0,
                                                "observed_building": 0.0, "observed_storage": 0.0,
                                                "weather": "clear", "rain": 0.0,
                                                "temperature": 15.0, "cold": 0.0, "wet": 0.0,
                                                "firewood_demand": 1.0})   # the weather clothes protect against
        self._store = self.eng.add_node("Store", {"name": "store"})           # holds Stock NODES, no commodity floats
        self.eng.add_edge_unchecked(self._town, "has_store", self._store)
        self._stock = {}; self._last_stock_qty = {}
        self._actors = {}; self._items = {}; self._actions = {}; self._tools = {}
        self._reference_specs = {}
        self._actor_references = {}
        self._actor_policies = {}
        self._documents = {}
        self._deeds = {}
        self._titles = {}
        self._land_disputes = {}
        self._actor_land_titles = {}
        self._households = {}
        self._infrastructure = {}
        self._animals = {}
        self._crops = {}
        self._land = {}
        self._water_sources = {}
        self._affordances = {}
        self._observation_schemas = {}
        self._map_cells = {}
        self._distance_fields = {}
        self._map_grid = None
        self._map_layout = None
        self._map_affordances = {}
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
        # The normal canonical world lets its private Ocelot minds act during
        # tick().  Game sessions disable this and submit proposals through the
        # backend API instead; the physical world remains identical.
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
        self._journals = {}
        self._rng = random.Random(int(map_seed))
        # Unified social graph.  These are world-mediated records; beliefs,
        # intentions, and relationship models remain on the resident edges and
        # attributes rather than being smuggled into body state.
        self._notes = {}
        self._conversations = {}
        self._utterances = {}
        self._speech_events = []
        self._purchase_utterances = {}
        self._market_expectation_specs = {}
        self._actor_market_expectations = {}
        self._requests = {}
        self._relationships = {}
        self._turn_actions = {}
        self._turn = 0
        self._major_dispatch = False
        self._next_home_index = 0
        self._next_farm_index = 0
        self._policy_specs = {p["name"]: p for p in E.POLICIES}
        self._law_specs = {p["name"]: p for p in E.LAWS}
        self._charter_specs = {p["name"]: p for p in E.CHARTERS}
        self._item_specs = dict(E.ITEMS)   # runtime item registry (data + runtime-added)
        self._tool_kinds = set()
        self.set_stock("none", 1e9)
        self._install_map(map_seed)
        for kind, spec in E.ITEMS.items():
            self._install_item(kind, spec)
        for r in E.RECIPES:
            self._install_recipe(r)
        for reference in E.all_reference_templates():
            self._register_reference(reference)
        for name, spec in E.AFFORDANCES.items():
            node = self.eng.add_node("Affordance", {"name": name, "domain": spec["domain"]})
            self.eng.add_edge_unchecked(self._town, "has_affordance", node)
            self._affordances[name] = node
        for name, spec in E.OBSERVATION_TYPES.items():
            node = self.eng.add_node("ObservationSchema", {"name": name, "source": spec["source"]})
            self.eng.add_edge_unchecked(self._town, "has_observation_schema", node)
            self._observation_schemas[name] = node
        for tk in self._tool_kinds:                     # provide the instruments the recipes call for
            t = self.eng.add_node("Tool", {"kind": tk, "condition": 1.0, "wear": 0.02})
            self.eng.add_edge_unchecked(self._town, "has_tool", t)
            self._tools[tk] = t
        self._places = {}; self._containers = {}
        for kind, spec in E.BUILDINGS.items():           # install the town's buildings from the data
            self._install_building(kind, spec)

        # The square and its board are ordinary world entities, not a second
        # noticeboard world.  Their location is an affordance on the imported
        # map, so notes can be carried, posted, and read in the same geography
        # as every other village activity.
        self._square = self.eng.add_node("Square", {"name": "town square"})
        self._noticeboard = self.eng.add_node("Noticeboard", {"name": "town noticeboard"})
        self.eng.add_edge_unchecked(self._town, "has_square", self._square)
        self.eng.add_edge_unchecked(self._square, "has_board", self._noticeboard)
        square_cell = self._map_layout.get("work", {}).get("market") if self._map_layout else None
        if square_cell in self._map_cells:
            self.eng.add_edge_unchecked(self._square, "at_cell", self._map_cells[square_cell])
            self.eng.add_edge_unchecked(self._noticeboard, "at_cell", self._map_cells[square_cell])

        # The canonical store is also a physical place on the integrated map.
        market = self._map_layout.get("work", {}).get("market") if self._map_layout else None
        if market in self._map_cells:
            self.eng.add_edge_unchecked(self._store, "at_cell", self._map_cells[market])
        self._seed_written_documents()

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
        for _ in range(6):
            self.eng.force_all_dirty(); self.eng.run_rules(1000000)
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
        self._claim_canonical_job_outputs()

    def _claim_canonical_job_outputs(self):
        """Move completed canonical production into the maker's physical carrier.

        The generic action rules correctly produce bulk output in the town's
        physical stock.  In the integrated village, however, a baker or cook
        must then possess the result before another resident can speak to them
        and receive it.  This adapter step is deliberately a physical transfer
        into the actor's carrier, not an economic or shop transaction.
        """
        if not getattr(self, "_cast100", None):
            return
        for job in list(self.eng.nodes("Job")):
            attrs = self.eng.node(job)["attrs"]
            if float(attrs.get("remaining", 1.0)) > 0.0 or float(attrs.get("canonical_output_claimed", 0.0)) == 1.0:
                continue
            actor = attrs.get("canonical_actor", "")
            kind = attrs.get("canonical_output_kind", "")
            amount = float(attrs.get("canonical_output_qty", 0.0))
            if actor not in self._actors or not kind or amount <= 0.0:
                self.eng.set_attr(job, "canonical_output_claimed", 1.0)
                continue
            if self._move_stock_to_inventory(actor, kind, amount):
                self.eng.set_attr(job, "canonical_output_claimed", 1.0)
                self.eng.set_attr(self._actor(actor), "sell_willing", 1.0)
                trade = next((trade for trade, shop in self._shops.items()
                              if self.eng.node(shop)["attrs"].get("output_kind") == kind), None)
                if trade is not None:
                    self.eng.set_attr(self._actor(actor), "sell_price", self.quote(trade))

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
    def _install_map(self, seed):
        """Install the 100-world geography as canonical Map/Cell graph data."""
        from worlds.bigville_town100_world import build_town_100
        grid, affordances, layout = build_town_100(seed)
        self._map_grid, self._map_layout = grid, layout
        self._map_node = self.eng.add_node("Map", {"name": "Bigville map", "seed": float(seed),
                                                     "width": float(layout["w"]), "height": float(layout["h"])})
        self.eng.add_edge_unchecked(self._town, "has_map", self._map_node)
        solid = {2, 6}  # the 100-world builder's WALL and WATER tile codes
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                walkable = tile not in solid
                cell = self.eng.add_node("MapCell", {"x": float(x), "y": float(y), "tile": float(tile),
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
        aliases = {"records_office": "townhall", "watchhouse": "watch", "wellhouse": "market",
                   "latrine": "market", "compost_yard": "farm", "root_cellar": "farm",
                   "granary": "farm", "smokehouse": "bakery", "scriptorium": "press",
                   "shambles": "market", "dyehouse": "press", "cooperage": "carpenter",
                   "woodshop": "carpenter", "sawpit": "carpenter", "tannery": "market",
                   "cobbler": "market", "tailorshop": "market", "weavery": "market",
                   "forge": "mason", "kitchen": "bakery", "dairy": "farm", "wharf": "fish"}
        target = work.get(kind) or work.get(aliases.get(kind, "")) or work.get("market")
        if isinstance(target, list):
            target = tuple(target)
        if target in self._map_cells:
            return target
        for pt in self._map_layout.get("farms", []) + self._map_layout.get("homes", []):
            if tuple(pt) in self._map_cells:
                return tuple(pt)
        return next(iter(self._map_cells), None)

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
        shelf_lives = [self.stock_condition(kind) / E.decay_rate(kind)
                       for kind, spec in self._item_specs.items()
                       if spec.get("food") and self.qty(kind) > 0 and E.decay_rate(kind) > 0]
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
            feed_days[feed] = self.qty(feed) / demand if demand else 0.0
            if demand and feed_days[feed] < 4.0:
                warnings.append(f"less than four days of animal feed: {feed}")

        capability_gaps = [name for name, node in self._actors.items()
                           if not list(self.eng.neighbours(node, "knows"))]
        essential_actions = ("grind_flour", "bake_bread", "make_pottage")
        essential_recipe_gaps = [action for action in essential_actions
                                 if not any(self.knows(name, action) for name in self._actors)]
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

    def actor_position(self, actor): return self._actor_positions.get(actor)

    def _node_item_weight(self, item):
        attrs = self.eng.node(item)["attrs"]
        if "weight" in attrs:
            return float(attrs["weight"])
        return self._phys(attrs.get("kind", ""))[0]

    def _held_discrete_weight(self, actor):
        node = self._actor(actor)
        return sum(self._node_item_weight(item)
                   for edge in ("holds_in_hand", "holds_tableware")
                   for item in self.eng.neighbours(node, edge))

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
        overload = max(0.0, ratio - float(E.CARRYING["overload_ratio"]))
        interval = max(1, int(math.ceil(ratio))) if math.isfinite(ratio) else 999999
        speed = 1.0 / interval
        effort = float(E.CARRYING["base_move_energy"]) * (
            1.0 + float(E.CARRYING["overload_energy_factor"]) * overload)
        return {"weight": round(weight, 4), "capacity": round(capacity, 4),
                "ratio": round(ratio, 4), "overloaded": ratio > float(E.CARRYING["overload_ratio"]),
                "drop_threshold": round(capacity * float(E.CARRYING["drop_ratio"]), 4),
                "speed": round(speed, 4), "move_interval": interval,
                "move_energy": round(effort, 4),
                "will_drop": ratio > float(E.CARRYING["drop_ratio"])}

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

    def move_actor(self, actor, destination):
        """Move one resident toward a destination, with load affecting travel."""
        current = self._actor_positions.get(actor)
        if current is None or destination not in self._map_cells:
            return None
        state = self._refresh_carry_state(actor)
        attrs = self.eng.node(self._actor(actor))["attrs"]
        effort = state["move_energy"]
        # The body's seeded exertion rule owns depletion, hunger, and recovery.
        # This adapter only mints the physical event and supplies its cost.
        body = self._bodies.get(actor)
        if body is not None:
            exertion = self.eng.add_node("Effort", {
                "uses_strength": 0.0, "uses_stamina": 1.0,
                "intensity": min(1.0, effort), "stamina_cost": effort * 0.1,
                "str_done": 0.0, "sta_done": 0.0, "cost_done": 0.0})
            self.eng.add_edge_unchecked(self._actor(actor), "exerted", exertion)
            if not self._actor_tick_in_progress:
                self._run()
        cooldown = int(round(float(attrs.get("carry_move_cooldown", 0.0))))
        if cooldown > 0:
            self.eng.set_attr(self._actor(actor), "carry_move_cooldown", float(cooldown - 1))
            return current
        if state["move_interval"] > 1:
            self.eng.set_attr(self._actor(actor), "carry_move_cooldown",
                              float(state["move_interval"] - 1))
        candidates = [(current[0] + 1, current[1]), (current[0] - 1, current[1]),
                      (current[0], current[1] + 1), (current[0], current[1] - 1)]
        distances = {p: self.distance(p, destination) for p in candidates if p in self._map_cells}
        viable = [p for p, d in distances.items() if d is not None]
        if viable:
            nxt = min(viable, key=lambda p: distances[p])
            self._move_actor_to(actor, nxt)
        return self._actor_positions.get(actor)

    @classmethod
    def from_town100(cls, seed=305000, *, autonomous_actors=True):
        """Build the canonical world with the expanded map and seeded 100-person cast."""
        world = cls(map_seed=seed, autonomous_actors=autonomous_actors)
        world.populate_town100(seed=seed)
        return world

    def populate_town100(self, *, seed=305000):
        """Import the 100-world's map-aligned cast as ordinary canonical entities.

        The 100-world remains a generator of scenario data.  Once imported, residents,
        households, land, shops, deposits, animals, and farms are owned by this world and
        use its normal APIs and graph vocabulary.
        """
        if getattr(self, "_cast100", None) is not None:
            return self._cast100
        from worlds.bigville_town100_world import generate_cast100

        layout = self._map_layout
        cast = generate_cast100(layout, seed)
        self._cast100 = cast
        self._t100_households = {}
        self._t100_farms = []

        for kind, cell in layout.get("deposits", {}).items():
            self.add_deposit(kind, tuple(cell), stock=60.0, growback=3.0, capacity=120.0)
        self.add_store(tuple(layout["work"]["market"]), ("fish", "lumber", "stone"))
        for trade, input_kind, output_kind in (
                ("fishmonger", "fish", "fish_ready"),
                ("carpenter", "lumber", "furniture"),
                ("mason", "stone", "blocks"),
                ("bakery", "grain", "bread")):
            if trade in layout["work"]:
                self.add_shop(trade, tuple(layout["work"][trade]),
                              input_kind=input_kind, output_kind=output_kind)

        station = {"low": "labouring", "middle": "middle", "high": "educated"}
        for record in cast["residents"]:
            idx = int(record["index"])
            role = record["role"]
            if role in {"farmer", "farm_labourer"}:
                household_kind = "farm_household"
            elif role in {"clerk", "councillor", "mayor", "constable", "teacher"}:
                household_kind = "institutional_household"
            elif record["group"] == "high":
                household_kind = "craft_household"
            else:
                household_kind = "landless_household"
            household = f"household_{idx:03d}"
            self.add_household(household, kind=household_kind,
                               home_cell=tuple(record["home_cell"]))
            self._t100_households[record["name"]] = household
            self.add_actor(record["name"], role=role, skill=0.7,
                           station=station.get(record["group"], "labouring"),
                           literacy=float(record["literacy"]),
                           capability=0.9 if record["literacy"] else 0.55,
                           home_cell=tuple(record["home_cell"]),
                           work_cell=tuple(record["workplace_cell"]),
                           klass=record["class"], group=record["group"],
                           role_identity=float(record["role_identity"]), traits=record["params"],
                           trades=E.CAST_ROLE_TRADES.get(role, ()))
            for tableware in E.SERVING_EQUIPMENT:
                self.give_tableware(record["name"], tableware)
            self.assign_household(record["name"], household)

        farmers = [r for r in cast["residents"] if r["role"] == "farmer"]
        for index, cell in enumerate(layout.get("farms", [])):
            owner = self._t100_households[farmers[index % len(farmers)]["name"]] if farmers else None
            land = self.add_land(f"farm_plot_{index:02d}", use="arable", soil="loam",
                                 area=1.0, cell=tuple(cell), household=owner)
            self._t100_farms.append(land)
        pasture_cell = tuple(layout.get("farms", [])[0]) if layout.get("farms") else None
        if pasture_cell is not None:
            self.add_land("village_pasture", use="pasture", soil="loam", area=4.0,
                          cell=pasture_cell)
        clerks = [name for name, node in self._actors.items()
                  if self.eng.node(node)["attrs"].get("role") == "clerk"]
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
            for index, species in enumerate(("cow", "chicken", "pig", "sheep", "horse", "bee")):
                self.add_animal(f"{species}_{index}", species, cell=pasture_cell,
                                household=farm_household, land="village_pasture")
        for kind, qty in E.STARTING_STOCK.items():
            self.set_stock(kind, qty)
        # The reserve is physical stock, but food intended for sale must be
        # carried by actual residents.  Seed the first two bakery workers with
        # a finite opening inventory; later output is collected from completed
        # recipes by the canonical job bridge above.
        bakers = [name for name, node in self._actors.items()
                  if self.eng.node(node)["attrs"].get("role") == "baker"]
        bakery_price = self.quote("bakery") if "bakery" in self._shops else 1.0
        for baker in bakers:
            if self.qty("bread") <= 0.0:
                break
            self.stock_person(baker, "bread", min(40.0, self.qty("bread")),
                              price=bakery_price, willing=True)
        # Seed the first rotation so the founding bread reserve is connected to actual local
        # production.  Later sowing, watering, harvesting, milling, and cooking remain actions.
        for index, crop in enumerate(E.STARTING_CROPS):
            if index < len(self._t100_farms) and farmers:
                self.sow(farmers[index % len(farmers)]["name"], crop,
                         land=f"farm_plot_{index:02d}")
        # Expand the founding rotation into physical crop beds.  Beds may
        # share a mapped parcel; the map locates the field, while each Crop
        # node is an independently watered and harvested unit.
        self._seed_village_crops(target=80)
        return cast

    # ---------------------------------------------------- install the data as graph nodes
    def _install_item(self, kind, spec):
        n = self.eng.add_node("ItemSpec", {"kind": kind, **{k: (float(v) if not isinstance(v, bool)
                                                               and isinstance(v, (int, float)) else v)
                                                             for k, v in spec.items()}})
        self.eng.set_attr(n, "scarcity", E.scarcity(kind))   # the raw material's general scarcity (data)
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
                 "min_skill": E.min_skill(r["name"]),   # the skill FLOOR to attempt it (apprenticeship)
                 "common": 0.0 if r.get("common") is False else 1.0}   # commonly known by the trade, or must be learned
        if discrete:                                    # carry the item's tool data onto the action
            attrs.update(verb=out.get("verb", ""), base_mult=float(out.get("base_mult", 1.0)),
                         wear_rate=float(out.get("wear_rate", 0.0)), decay=E.decay_rate(out_kind))
        # carry the output's DEMAND data onto the action (for the pd_decide collapse)
        attrs.update(out_driver=out.get("demand_driver", ""),
                     out_demand_weight=float(out.get("demand_weight", 0.0)),
                     out_base_demand=float(out.get("base_demand", 0.0)))
        asp = self.eng.add_node("ActionSpec", attrs)
        self.eng.add_edge_unchecked(self._town, "has_actionspec", asp)
        for kind, qty in r["in"]:                       # N input needs (data)
            icls = self._item_specs.get(kind, {}).get("class")
            is_item = 1.0 if icls not in (None, "material") and self._item_specs.get(kind, {}).get("discrete", True) else 0.0
            need = self.eng.add_node("Need", {"kind": kind, "qty": float(qty), "is_item": is_item})
            self.eng.add_edge_unchecked(asp, "in_need", need)
        for tk in r.get("tools", []):                   # Y tool uses (data)
            tu = self.eng.add_node("ToolUse", {"kind": tk})
            self.eng.add_edge_unchecked(asp, "in_tool", tu)
            self._tool_kinds.add(tk)
        if not discrete:
            self.set_stock(out_kind, self.qty(out_kind))
        self._actions[r["name"]] = asp
        return asp

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
        for tk in r.get("tools", []):                   # provide any newly-required instrument
            if tk not in self._tools:
                t = self.eng.add_node("Tool", {"kind": tk, "condition": 1.0, "wear": 0.02})
                self.eng.add_edge_unchecked(self._town, "has_tool", t)
                self._tools[tk] = t
        if r.get("common") is not False:                # a new COMMON recipe is common knowledge for its trade
            for name, a in self._actors.items():
                if self.eng.node(a)["attrs"].get("role") == r.get("requires"):
                    self.eng.add_edge_unchecked(a, "knows", asp)
        return asp

    def add_reference(self, reference):
        """Add a shared reference and seed it only to eligible existing residents."""
        self._register_reference(reference)
        present_roles = {self.eng.node(a)["attrs"].get("role", "") for a in self._actors.values()}
        roles = set(reference.get("seed_roles", ()))
        for actor in self._actors.values():
            role = self.eng.node(actor)["attrs"].get("role", "")
            if ("*" in roles or role in roles) and \
                    (not reference.get("requires_role") or reference["requires_role"] in present_roles):
                self._seed_reference(actor, reference)
        return reference["name"]

    # ---------------------------------------------------- village schemas and material institutions
    def affordance_data(self, name):
        return dict(E.AFFORDANCES[name])

    def observation_schema(self, name):
        return dict(E.OBSERVATION_TYPES[name])

    def set_weather(self, weather):
        """Set an environmental condition; residents may observe it, but it is not a resident fact."""
        spec = E.WEATHER[weather]
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

    # ---------------------------------------------------- calendar, weather, and public observations
    def calendar(self):
        """Read the canonical clock without turning time into a town fact."""
        a = self.eng.node(self._town)["attrs"]
        return {k: a.get(k) for k in ("clock", "day", "hour", "week", "year", "season", "weather")}

    def _advance_calendar(self):
        a = self.eng.node(self._town)["attrs"]
        clock = float(a.get("clock", 0.0))
        day = int(clock // 96)
        hour = 6.0 + (clock % 96.0) * 0.25
        year_day = day % 360
        season = ("spring" if year_day < 90 else "summer" if year_day < 180
                  else "autumn" if year_day < 270 else "winter")
        self.eng.set_attr(self._town, "day", float(day))
        self.eng.set_attr(self._town, "hour", hour % 24.0)
        self.eng.set_attr(self._town, "week", float(day // 7))
        self.eng.set_attr(self._town, "year", float(day // 360 + 1))
        if season != a.get("season"):
            self.eng.set_attr(self._town, "season", season)
        if abs(hour % 24.0 - 6.0) < 1e-9:
            self._set_daily_weather(day, season)

    def _set_daily_weather(self, day, season):
        options = E.SEASONS.get(season, {}).get("weather", ("clear",))
        # Deterministic weather is still variable: the map seed controls it,
        # and the resulting weather remains an observation residents must make.
        aliases = {"cool": "clear", "hot": "dry"}
        options = tuple(aliases.get(option, option) for option in options if aliases.get(option, option) in E.WEATHER)
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
        if float(self.eng.node(self._actors[reader])["attrs"].get("literacy", 0.0)) < E.LIT_FUNCTIONAL:
            return None
        editions = list(self.eng.neighbours(copy, "of_edition"))
        if not editions:
            return None
        edition = editions[0]
        articles = list(self.eng.neighbours(edition, "contains"))
        for article in articles:
            self.eng.add_edge_unchecked(self._actors[reader], "read_article", article)
            for event in self.eng.neighbours(article, "about"):
                self.eng.add_edge_unchecked(self._actors[reader], "knows_event", event)
        return [dict(self.eng.node(article)["attrs"]) for article in articles]

    def _publish_village_weekly(self):
        """Print a factual weekly account from a reporter's live observations."""
        reporters = [name for name, node in self._actors.items()
                     if self.eng.node(node)["attrs"].get("role") == "reporter"
                     and self.is_alive(name)]
        if not reporters:
            return None
        reporter = reporters[0]
        food = sum(self.qty(k) for k, spec in self._item_specs.items() if spec.get("food") and k in self._stock)
        event = self.create_event("weekly_village_report", subject="Bigville",
                                  detail=(f"The village holds {food:.0f} edible rations, "
                                          f"{len(self._living_crops())} living crops, and "
                                          f"{sum(self.animal_alive(n) for n in self._animals)} living animals."),
                                  observer=reporter, public=True)
        return self.print_newspaper(reporter, event,
                                    headline=f"The Week in Bigville: {int(self.calendar()['day'])}",
                                    copies=20)

    def add_household(self, name, *, kind="landless_household", assets=None, home_cell=None):
        spec = E.HOUSEHOLDS[kind]
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
        assert use in E.LAND_USES and soil in E.SOILS
        spec = E.SOILS[soil]
        n = self.eng.add_node("Land", {"name": name, "use": use, "soil": soil,
                                        "area": float(area), "fertility": float(spec["fertility"]),
                                        "moisture": 0.0, "erosion": float(spec["erosion"]), "fallow": 0.0})
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
        assert self.eng.node(self._actors[clerk])["attrs"].get("role") == "clerk", \
            f"{clerk} is not the village clerk"

    def _seed_land_title_fact(self, actor_node, land, title):
        actor_facts = self._actor_land_titles.setdefault(actor_node, {})
        title_id = self.eng.node(title)["attrs"]["record_id"]
        if title_id in actor_facts:
            return actor_facts[title_id]
        ta = self.eng.node(title)["attrs"]
        fact = self.eng.add_node("Fact", {"name": f"title_{title_id}", "kind": "resident_land_title",
                                           "abstraction": "operational", "subject": land,
                                           "predicate": "held_by", "object": ta["holder"],
                                           "tenure": ta["tenure"], "record_id": title_id})
        self.eng.add_edge_unchecked(actor_node, "knows_land_title", fact)
        actor_facts[title_id] = fact
        return fact

    def _seed_title_knowledge(self, land, title, names):
        recipients = set(names)
        for name in list(recipients):
            if name in self._actors:
                self._seed_land_title_fact(self._actors[name], land, title)
            elif name in self._households:
                for member in self.household_members(name):
                    if member in self._actors:
                        self._seed_land_title_fact(self._actors[member], land, title)

    def _register_title(self, clerk, land, holder, *, holder_kind=None, tenure="freehold",
                        basis="grant", effective=None, witnesses=(), deed=None, occupant=None):
        self._require_clerk(clerk)
        assert land in self._land and tenure in E.LAND_TENURE
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
        self._seed_title_knowledge(land, title, {clerk, holder, *witnesses})
        return title

    def register_land(self, clerk, land, holder, *, holder_kind=None, tenure="freehold",
                      basis="grant", effective=None, witnesses=()):
        """Create the initial registered title for a parcel."""
        assert land not in self._titles, f"{land} already has a registered title"
        return self._register_title(clerk, land, holder, holder_kind=holder_kind, tenure=tenure,
                                     basis=basis, effective=effective, witnesses=witnesses)

    def write_deed(self, clerk, deed_type, land, *, from_holder="", to_holder="", witnesses=(),
                   term=None, consideration=0.0, notes=""):
        """Create a physical deed; it changes no title until the clerk registers it."""
        self._require_clerk(clerk)
        assert deed_type in E.DEED_TYPES and land in self._land
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
        """Register a deed at the records office and materialise its title consequence."""
        self._require_clerk(clerk)
        attrs = self.eng.node(deed)["attrs"]
        assert attrs.get("registered") == 0.0 and attrs["parcel"] in self._land
        deed_type = attrs["deed_type"]
        to_holder = attrs.get("to_holder", "")
        from_holder = attrs.get("from_holder", "")
        assert to_holder in self._actors or to_holder in self._households, "deed needs a known receiving holder"
        current = self._titles.get(attrs["parcel"])
        if deed_type != "grant":
            assert current is not None, "non-grant deed needs an existing title"
            assert from_holder == self.eng.node(current)["attrs"].get("holder"), \
                "only the registered holder can transfer or lease the parcel"
        tenure = "lease" if deed_type == "lease" else "freehold"
        occupant = to_holder if deed_type == "lease" else ""
        title_holder = from_holder if deed_type == "lease" else to_holder
        title = self._register_title(clerk, attrs["parcel"], title_holder, tenure=tenure,
                                     basis=deed_type, witnesses=tuple(filter(None, attrs.get("witnesses", "").split(","))),
                                     deed=deed, occupant=occupant)
        self.eng.set_attr(deed, "registered", 1.0)
        self.eng.add_edge_unchecked(deed, "produced_title", title)
        self._seed_title_knowledge(attrs["parcel"], title, {clerk, from_holder, to_holder})
        return title

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
        if attrs.get("registered") == 1.0 and attrs["parcel"] in self._titles:
            self._seed_land_title_fact(self._actors[reader], attrs["parcel"], self._titles[attrs["parcel"]])
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

    def knows_land_title(self, actor, land):
        title = self._titles.get(land)
        if title is None:
            return False
        record_id = self.eng.node(title)["attrs"]["record_id"]
        return record_id in self._actor_land_titles.get(self._actors[actor], {})

    def inspect_land_record(self, reader, land):
        """Public inspection creates a resident-owned fact about the current registered title."""
        assert land in self._land and self._titles.get(land) is not None
        assert self._can_read(reader), f"{reader} cannot read the land register"
        self._seed_land_title_fact(self._actors[reader], land, self._titles[land])
        return self.land_record(land)

    def file_land_dispute(self, complainant, land, *, kind="boundary", against="", grounds=""):
        assert land in self._land and kind in E.LAND_DISPUTES
        dispute_id = f"dispute:{len(self._land_disputes) + 1}"
        n = self.eng.add_node("LandDispute", {"record_id": dispute_id, "parcel": land, "kind": kind,
                                               "complainant": complainant, "against": against,
                                               "grounds": grounds, "status": "open", "outcome": ""})
        self.eng.add_edge_unchecked(self._town, "has_land_dispute", n)
        self.eng.add_edge_unchecked(self._land[land], "has_dispute", n)
        if complainant in self._actors:
            self.eng.add_edge_unchecked(self._actors[complainant], "filed_dispute", n)
        self._land_disputes[dispute_id] = n
        return n

    def resolve_land_dispute(self, adjudicator, dispute, *, outcome, winner="", remedy=""):
        role = self.eng.node(self._actors[adjudicator])["attrs"].get("role")
        assert role in {"mayor", "councillor", "clerk"}, "only a local authority can resolve a land dispute"
        attrs = self.eng.node(dispute)["attrs"]
        assert attrs.get("status") == "open"
        self.eng.set_attr(dispute, "status", "resolved")
        self.eng.set_attr(dispute, "outcome", outcome)
        self.eng.set_attr(dispute, "winner", winner)
        self.eng.set_attr(dispute, "remedy", remedy)
        self.eng.add_edge_unchecked(self._actors[adjudicator], "resolved_dispute", dispute)
        return dispute

    def add_water_source(self, name, *, kind="well", capacity=None):
        spec = E.WATER_SOURCES[kind]
        n = self.eng.add_node("WaterSource", {"name": name, "kind": kind,
                                               "capacity": float(capacity if capacity is not None else spec["yield"]),
                                               "quality": float(spec["quality"]), "available": 1.0})
        self.eng.add_edge_unchecked(self._town, "has_water_source", n)
        self._water_sources[name] = n
        anchor = self._anchor_for_building("wellhouse")
        self._attach_at_cell(n, anchor)
        return n

    def add_infrastructure(self, name, *, kind, condition=1.0):
        spec = E.INFRASTRUCTURE[kind]
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
        roles = {str(attrs.get("role", "")), *filter(None, str(attrs.get("trades", "")).split(","))}
        if not roles.intersection({"craftsperson", "carpenter", "woodworker", "mason", "labourer", "farm_labourer"}):
            return False
        node = self._infrastructure[name]
        if self._turn > 0 and self.actor_position(operator) != self.map_position_node(node):
            return False
        spec = E.INFRASTRUCTURE[self.eng.node(node)["attrs"]["kind"]]
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
        spec = E.SHOCKS[kind]
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
                 recipe_out=1.0, price=2.0, is_open=1):
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
                       if float(self.eng.node(self._actors[name])["attrs"].get("sell_willing", 0.0)) == 1.0
                       and self.inventory_qty(name, kind) >= 1.0]
            if offered:
                return offered[0]
            # Being present is not enough to make a person a seller.  The
            # shop convention tells the buyer where to go; the actual person
            # must be there and visibly holding the offered good.
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
            if trade in trades or role == trade or (trade == "bakery" and role == "baker"):
                candidates.append(name)
        return next((name for name in candidates if self.is_alive(name)), None) or (candidates[0] if candidates else None)

    def stock_person(self, seller, kind, amount, *, price=1.0, willing=True):
        """Put a physical good in a person's inventory as a voluntary offer."""
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

    def _shop_give(self, giver, trade, kind, amount, *, payment_kind="coin", payment_amount=0.0):
        """Compatibility route: use the conventional shop to find its person."""
        shop = self.eng.node(self._shops[trade])["attrs"]
        amount = max(0.0, float(amount))
        price = amount * float(shop.get("price", 0.0))
        output = shop["output_kind"]
        payment_amount = price if payment_amount is None else max(0.0, float(payment_amount))
        seller = self._market_counterparty(giver, trade, kind)
        if seller is None or kind != output:
            return False
        return self._person_purchase(giver, seller, kind, amount,
                                      payment_kind=payment_kind,
                                      payment_amount=payment_amount,
                                      trade=trade)

    def _person_purchase(self, buyer, seller, kind, amount, *, payment_kind="coin",
                         payment_amount=None, trade=None):
        """Complete a spoken person-to-person purchase through physical give."""
        self._actor(buyer); self._actor(seller)
        amount = max(0.0, float(amount))
        seller_attrs = self.eng.node(self._actor(seller))["attrs"]
        price = amount * float(seller_attrs.get("sell_price", 0.0))
        payment_amount = price if payment_amount is None else max(0.0, float(payment_amount))
        speech = self._purchase_utterances.get((buyer, seller, kind))
        if (payment_kind != "coin" or speech is None
                or float(seller_attrs.get("sell_willing", 1.0)) != 1.0
                or self.coin(buyer) < payment_amount
                or self.inventory_qty(seller, kind) < amount
                or (self._turn > 0 and self.actor_position(buyer) != self.actor_position(seller))):
            return False
        if not self._move_inventory_to_inventory(seller, buyer, kind, amount):
            return False
        self.set_coin(buyer, self.coin(buyer) - payment_amount)
        self.set_coin(seller, self.coin(seller) + payment_amount)
        self.eng.add_edge_unchecked(self._actor(seller), "gave", self._actor(buyer))
        self.eng.add_edge_unchecked(self._actor(buyer), "gave", self._actor(seller))
        transaction = self._record_transaction("purchase", buyer, seller, kind, amount, payment_amount)
        self.eng.add_edge_unchecked(transaction, "preceded_by", speech)
        self._purchase_utterances.pop((buyer, seller, kind), None)
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
        """Give a held good or coin to a resident, or use give for a purchase.

        Purchases are person-to-person: an utterance to the seller precedes a
        physical transfer. A shop argument is only a location convention that
        resolves to the person working there.
        """
        amount = max(0.0, float(amount))
        if amount <= 0.0:
            return False
        if recipient in self._shops:
            self._actor(giver)
            if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(giver, "give"):
                return False
            return self._shop_give(giver, recipient, kind, amount,
                                   payment_kind=payment_kind or "coin",
                                   payment_amount=payment_amount)
        self._actor(giver); self._actor(recipient)
        if not self._major_dispatch and self._turn > 0 and not self._claim_major_action(giver, "give"):
            return False
        if (self._turn > 0 and self.actor_position(giver) != self.actor_position(recipient)):
            return False
        if not isinstance(kind, str):
            return self._give_discrete_item(giver, recipient, kind)
        if payment_kind == "coin":
            return self._person_purchase(giver, recipient, kind, amount,
                                          payment_kind=payment_kind,
                                          payment_amount=payment_amount)
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

    def buy(self, buyer, trade, amount=1.0):
        """Compatibility wrapper; ``buy`` is not a resident action.

        Live resident plans use a purchase utterance followed by ``give``.
        This wrapper remains for small setup callers and delegates to exactly
        that transfer path, recording ``give`` once the clock is running.
        """
        self._actor(buyer)
        if trade not in self._shops:
            return False
        shop = self.eng.node(self._shops[trade])["attrs"]
        amount = max(0.0, float(amount))
        price = amount * float(shop.get("price", 0.0))
        output = shop.get("output_kind", "")
        if self.coin(buyer) < price:
            return False
        seller = self._market_counterparty(buyer, trade, output)
        # Setup-time compatibility calls may resolve the conventional worker
        # before the clock has opened physical turns.  This does not create a
        # transaction or bypass live co-location; it only lets fixtures seed a
        # resident's inventory through the old convenience spelling.
        if seller is None and self._turn == 0:
            candidate = self._shopkeeper_for_trade(trade)
            if candidate is not None and self.inventory_qty(candidate, output) >= amount:
                seller = candidate
        if seller is None:
            return False
        if not self._major_dispatch:
            if self._turn > 0 and self.actor_turn_state(buyer)["major_action_used"]:
                return False
            utterance = self.purchase_utterance(buyer, seller, output, amount)
            if utterance is False:
                return False
            self.eng.set_attr(utterance, "market_trade", str(trade))
        return self.give(buyer, seller, output, amount,
                         payment_kind="coin", payment_amount=price)

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
        self._purchase_utterances[(buyer, seller, kind)] = utterance
        self._speech_events.append({
            "turn": int(self._turn), "speaker": buyer, "target": seller,
            "kind": "purchase", "content": content,
            "heard": bool(self.eng.node(utterance)["attrs"].get("heard", 0.0)),
        })
        return utterance

    def sell_to_shop(self, seller, trade, kind, amount=1.0):
        shop = self.eng.node(self._shops[trade])["attrs"]
        amount = max(0.0, float(amount))
        if shop.get("input_kind") != kind or self.inventory_qty(seller, kind) < amount:
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(seller, "sell"):
            return False
        price = amount * float(shop.get("price", 0.0)) * 0.5
        if float(shop.get("coin", 0.0)) < price:
            return False
        if not self._move_inventory_to_stock(seller, kind, amount):
            return False
        self.eng.set_attr(self._shops[trade], "coin", float(shop.get("coin", 0.0)) - price)
        self.set_coin(seller, self.coin(seller) + price)
        self._record_transaction("sale", seller, trade, kind, amount, price)
        return True

    def sell_labor(self, actor, trade, wage=2.0):
        """Sell one labour shift to a shop as an explicit actor action.

        The shop pays from its accumulated coin; this is the small founding
        labour market that lets residents continue buying food after their
        starting coin is spent.  It is not a town-wide wage side effect.
        """
        shop_node = self._shops.get(trade)
        if shop_node is None:
            return False
        shop = self.eng.node(shop_node)["attrs"]
        wage = max(0.0, float(wage))
        if float(shop.get("coin", 0.0)) < wage:
            return False
        self.eng.set_attr(shop_node, "coin", float(shop.get("coin", 0.0)) - wage)
        self.set_coin(actor, self.coin(actor) + wage)
        self._record_transaction("labor", actor, trade, "labor", 1.0, wage)
        return True

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
        service = E.food_service(kind)
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
            if not E.can_serve(kind, vessel, utensil, source_kind=source_kind):
                return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "eat"):
            return False
        stock = self._inventory_stock(actor, kind)
        self.eng.set_attr(stock, "qty", self.inventory_qty(actor, kind) - 1.0)
        self._refresh_carry_state(actor)
        self.eng.set_attr(self._actor(actor), "hunger", 0.0)
        self.eng.add_edge_unchecked(self._actor(actor), "ate", stock)
        return True

    def pay_wage(self, employer, worker, amount):
        amount = max(0.0, float(amount))
        if self.coin(employer) < amount:
            return False
        self.set_coin(employer, self.coin(employer) - amount)
        self.set_coin(worker, self.coin(worker) + amount)
        attrs = self.eng.node(self._actors[worker])["attrs"]
        self.eng.set_attr(self._actors[worker], "wage_due", max(0.0, float(attrs.get("wage_due", 0.0)) - amount))
        self._record_transaction("wage", employer, worker, "coin", amount, amount)
        return True

    def _record_transaction(self, kind, actor, target, good, quantity, value):
        node = self.eng.add_node("Transaction", {"kind": kind, "actor": str(actor), "target": str(target),
                                                   "good": str(good), "quantity": float(quantity),
                                                   "value": float(value), "day": float(self.calendar()["day"])})
        self.eng.add_edge_unchecked(self._town, "has_transaction", node)
        self._transactions[f"transaction:{len(self._transactions) + 1}"] = node
        return node

    # ---------------------------------------------------- civic process and justice
    def propose_local_law(self, author, name, *, title=None, scope="bigville", concepts=()):
        if name in self._law_specs and self.law_origin(name) == "giantville":
            raise ValueError("inherited Giantville laws cannot be edited locally")
        proposal = self.eng.add_node("LawProposal", {"name": name, "title": title or name.replace("_", " ").title(),
                                                        "scope": scope, "status": "open", "votes_for": 0.0,
                                                        "votes_against": 0.0, "author": author})
        self.eng.add_edge_unchecked(self._town, "has_proposal", proposal)
        self.eng.add_edge_unchecked(self._actors[author], "proposed", proposal)
        for concept in concepts:
            self.eng.add_edge_unchecked(proposal, "has_concept", self.eng.add_node("Concept", dict(concept)))
        self._proposals[f"proposal:{len(self._proposals) + 1}"] = proposal
        return proposal

    def vote_on_law(self, voter, proposal, support):
        role = self.eng.node(self._actors[voter])["attrs"].get("role")
        if role not in {"mayor", "councillor", "clerk"}:
            return False
        if self.eng.node(proposal)["attrs"].get("status") != "open":
            return False
        edge = "voted_for" if support else "voted_against"
        self.eng.add_edge_unchecked(self._actors[voter], edge, proposal)
        return True

    def hold_council(self, chair=None, proposal=None):
        members = [name for name, node in self._actors.items()
                   if self.eng.node(node)["attrs"].get("role") in {"mayor", "councillor", "clerk"}]
        meeting = self.eng.add_node("CouncilMeeting", {"day": float(self.calendar()["day"]), "quorum": float(len(members)),
                                                         "chair": chair or (members[0] if members else "")})
        self.eng.add_edge_unchecked(self._town, "has_meeting", meeting)
        for name in members:
            self.eng.add_edge_unchecked(meeting, "has_member", self._actors[name])
        self._meetings[f"meeting:{len(self._meetings) + 1}"] = meeting
        if proposal is not None:
            attrs = self.eng.node(proposal)["attrs"]
            votes_for = len(self.eng.in_neighbours(proposal, "voted_for"))
            votes_against = len(self.eng.in_neighbours(proposal, "voted_against"))
            self.eng.set_attr(proposal, "votes_for", float(votes_for))
            self.eng.set_attr(proposal, "votes_against", float(votes_against))
            if votes_for > votes_against and votes_for >= max(1, len(members) // 2 + 1):
                name = attrs["name"]
                self._law_specs[name] = {"name": name, "title": attrs["title"], "scope": attrs["scope"],
                                         "origin": "bigville", "immutable": False, "enforcement": "bigville",
                                         "concepts": [dict(self.eng.node(c)["attrs"]) for c in self.eng.neighbours(proposal, "has_concept")]}
                self.eng.set_attr(proposal, "status", "enacted")
                self._seed_written_documents()
            else:
                self.eng.set_attr(proposal, "status", "rejected")
        return meeting

    def file_case(self, complainant, respondent, *, charge, law="", evidence=""):
        case = self.eng.add_node("Case", {"charge": charge, "law": law, "evidence": evidence,
                                           "complainant": complainant, "respondent": respondent,
                                           "status": "open", "verdict": "", "remedy": ""})
        self.eng.add_edge_unchecked(self._town, "has_case", case)
        self.eng.add_edge_unchecked(self._actors[complainant], "filed_case", case)
        self.eng.add_edge_unchecked(self._actors[respondent], "answerable_case", case)
        self._cases[f"case:{len(self._cases) + 1}"] = case
        return case

    def resolve_case(self, adjudicator, case, *, verdict, remedy=""):
        if self.eng.node(self._actors[adjudicator])["attrs"].get("role") not in {"mayor", "constable", "clerk", "councillor"}:
            raise ValueError("only a local authority may resolve a Bigville case")
        attrs = self.eng.node(case)["attrs"]
        if attrs.get("status") != "open":
            return False
        self.eng.set_attr(case, "status", "resolved")
        self.eng.set_attr(case, "verdict", str(verdict))
        self.eng.set_attr(case, "remedy", str(remedy))
        self.eng.set_attr(case, "resolved_day", float(self.calendar()["day"]))
        self.eng.add_edge_unchecked(self._actors[adjudicator], "resolved_case", case)
        return True

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

    def lawmaking_procedures(self): return {k: dict(v) for k, v in E.LAWMAKING_PROCEDURES.items()}
    def justice_procedures(self): return {k: dict(v) for k, v in E.JUSTICE_PROCEDURES.items()}

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
        for concept in E.all_reference_templates():
            if concept.get("source_name") == bundle["name"]:
                self._seed_reference(actor, concept)
        understood = self.eng.add_node("PolicyUnderstanding", {"name": bundle["name"], "kind": bundle["kind"]})
        self.eng.add_edge_unchecked(actor, "understands", understood)
        self._actor_policies.setdefault(actor, set()).add(bundle["name"])

    def write_document(self, author, name, *, kind="policy"):
        """Create a physical written policy/law record; the document is not knowledge until read."""
        assert name in {"policy": self._policy_specs, "law": self._law_specs,
                        "charter": self._charter_specs}[kind]
        if kind in ("law", "charter") and not self.can_read_law(author):
            return None
        if kind == "policy" and not self.can_read(author):
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
        if attrs.get("kind") in ("law", "charter") and not self.can_read_law(reader):
            return None
        if attrs.get("kind") == "policy" and not self.can_read(reader):
            return None
        self._seed_bundle(self._actors[reader], self._bundle(attrs["name"], attrs["kind"]))
        self.eng.add_edge_unchecked(self._actors[reader], "read_document", document)
        return attrs["name"]

    def _knows_bundle(self, actor, name):
        known = self.known_references(actor)
        required = {c["name"] for c in E.all_reference_templates() if c.get("source_name") == name}
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
        perishable = 1.0 if E.adjectival(kind) == "perishable" else 0.0
        if kind in self._stock:
            self.eng.set_attr(self._stock[kind], "qty", float(qty))
        else:
            colour = self._item_specs.get(kind, {}).get("colour", "")   # a dye names a colour (madder->red)
            s = self.eng.add_node("Stock", {"kind": kind, "qty": float(qty),   # a first-class physical pile
                                            "weight": w, "volume": v, "fluid": fl, "food": food, "colour": colour,
                                            # spoilage: a perishable pile has a freshness that decays over time
                                            "perishable": perishable, "condition": 1.0,
                                            "decay": E.decay_rate(kind), "decay_epoch": 0.0})
            self.eng.add_edge_unchecked(self._store, "stock", s)
            self._stock[kind] = s
        return self._stock[kind]

    # ---------------------------------------------------- condition adjectives (wear + decay stages)
    def tool_adjective(self, tool):
        """The adjective describing a discrete tool at its current condition (pristine/worn/rusty/...)."""
        a = self.eng.node(tool)["attrs"]
        return E.adjective(a["kind"], a["condition"])

    def stock_adjective(self, kind):
        """The adjective describing a perishable stock (fresh/stale/rotten/putrid)."""
        return E.adjective(kind, self.eng.node(self._stock[kind])["attrs"].get("condition", 1.0))

    def stock_condition(self, kind):
        return round(float(self.eng.node(self._stock[kind])["attrs"].get("condition", 1.0)), 4)
    def stored_condition(self, container, kind):
        return round(float(self.eng.node(self._containers[container][1][kind])["attrs"].get("condition", 1.0)), 4)
    def stored_adjective(self, container, kind):
        return E.adjective(kind, self.eng.node(self._containers[container][1][kind])["attrs"].get("condition", 1.0))
    def item_wear_rate(self, kind): return float(self._item_specs.get(kind, {}).get("wear_rate", 0.0))
    def item_decay_rate(self, kind): return E.decay_rate(kind)
    def adjectival_class(self, kind): return E.adjectival(kind)

    # ------------------------------- BACKEND value read-offs (for the operator; NOT an agent input)
    # scarcity is a raw-material fact a seller knows; reference_value is an analyst baseline the human
    # holds the market's discovered price against -- the agents price for themselves, the market clears.
    def scarcity(self, kind): return E.scarcity(kind)
    def reference_value(self, kind): return E.reference_value(kind)
    def material_value(self, kind): return E.material_value(kind)
    def embodied_labour(self, kind): return E.embodied_labour(kind)

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
        self._attach_at_cell(p, cell if cell is not None else self._anchor_for_building(kind))
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
        spec = E.BUILDING_PROJECTS[project]
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
        """Spend materials and labour on a project; completion mints a Place node."""
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
        spec = E.BUILDING_PROJECTS[attrs["project"]]
        labour = min(float(labour), float(attrs["labour"]) - float(attrs["progress"]))
        if labour <= 0:
            return None
        scale = labour / float(attrs["labour"])
        required = {k: float(v) * scale for k, v in spec.get("inputs", {}).items()}
        if any(self.qty(k) < q for k, q in required.items()):
            return None
        for kind, qty in required.items():
            self.set_stock(kind, self.qty(kind) - qty)
        self.eng.set_attr(n, "progress", float(attrs["progress"]) + labour)
        self.eng.add_edge_unchecked(self._actors[builder], "worked_on", n)
        if float(attrs["progress"]) + labour + 1e-9 < float(attrs["labour"]):
            self.eng.set_attr(n, "status", "under_construction")
            return None
        self.eng.set_attr(n, "status", "complete")
        building_kind = attrs["building"]
        base = dict(E.BUILDINGS.get(building_kind, {
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
        spec = self._item_specs.get(kind, {}) or E.CONTAINERS.get(kind, {})
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
        storage_class = (self._item_specs.get(kind, {}) or E.CONTAINERS.get(kind, {})).get("storage_class")
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
        per = 1.0 if E.adjectival(kind) == "perishable" else 0.0
        # A pile created during a later period is fresh now.  Starting its
        # decay clock at zero would make the periodic decay rule age it once
        # for every elapsed period immediately, often spoiling a just-bought
        # resident inventory before the resident can consume it.
        current_period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        inner = self.eng.add_node("Stock", {"kind": kind, "qty": 0.0, "weight": w, "volume": vol, "fluid": fl,
                                            "perishable": per, "condition": 1.0, "decay": E.decay_rate(kind),
                                            "storage_factor": E.storage_decay_factor(container_kind, kind),
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

    # ---------------------------------------------------- animals (from the ANIMALS data) + carts/horses
    def add_animal(self, name, species, *, cell=None, household=None, land=None):
        spec = E.ANIMALS[species]
        a = self.eng.add_node("Animal", {"name": name, "species": species, "role": spec.get("role", ""),
                                         "pull": float(spec.get("pull", 0.0)), "alive": 1.0,
                                         "matures": float(spec.get("matures", 0)), "lifespan": float(spec.get("lifespan", 0)),
                                         # feeding state (data-driven): what it eats, how much, and its starve limit
                                         "hunger": 0.0, "hunger_epoch": 0.0, "eats": spec.get("eats", ""),
                                         "ration": float(spec.get("ration", 1)), "starve_limit": float(spec.get("starve_limit", 3))})
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
        return a

    def _husbandry_yield(self, actor, animal, task):
        """Perform one data-defined animal-care yield with a period cooldown."""
        assert actor in self._actors and animal in self._animals
        if (self._turn > 0
                and self.actor_position(actor) != self.map_position_node(self._animals[animal])):
            return 0.0
        spec = E.ANIMAL_HUSBANDRY[task]
        an = self._animals[animal]
        aa = self.eng.node(an)["attrs"]
        assert aa["species"] == spec["species"], f"{task} requires a {spec['species']}"
        assert float(aa.get("alive", 0.0)) == 1.0, f"{animal} is not alive"
        actor_attrs = self.eng.node(self._actors[actor])["attrs"]
        roles = {actor_attrs.get("role", ""), actor_attrs.get("trade", "")}
        roles.update(filter(None, actor_attrs.get("trades", "").split(",")))
        assert roles.intersection(spec["roles"]), f"{actor} is not trained for {task}"
        period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
        epoch_key = f"{task}_epoch"
        last = float(aa.get(epoch_key, -float(spec["cooldown"])))
        if period - last < float(spec["cooldown"]):
            return 0.0
        product = spec["product"]
        amount = float(E.ANIMALS[aa["species"]].get("gives", {}).get(product, 0.0))
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
        for kind, per_area in E.PASTURE_YIELDS.items():
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
        farmers = [name for name, node in self._actors.items()
                   if self.eng.node(node)["attrs"].get("role") in {"farmer", "farm_labourer"}]
        if not farmers:
            return 0
        crops = ("wheat", "barley", "oats")
        added = 0
        land_names = [name for name in self._land if name.startswith("farm_plot_")]
        while len(self._living_crops()) < target:
            crop = crops[added % len(crops)]
            seed = E.CROPS[crop]["seed"]
            if self.qty(seed) < 1.0:
                break
            land = land_names[added % len(land_names)]
            if self.sow(farmers[added % len(farmers)], crop, land=land) is None:
                break
            added += 1
        return added

    def _recipe_inputs_available(self, recipe):
        data = next((r for r in E.RECIPES if r["name"] == recipe), None)
        if data is None:
            return False
        return all(self.qty(kind) >= float(qty) for kind, qty in data.get("in", []))

    def _village_start(self, actor, recipe):
        if self.busy(actor) or not self._recipe_inputs_available(recipe):
            return False
        return bool(self.start(actor, recipe))

    def _village_work_tick(self, period):
        """Perform the small, explicit founding policy used by ``run_village``.

        This is a scenario policy, not a hidden body rule.  Each successful
        operation claims the actor's current major-action slot; speech,
        requests, and other free actions remain available between these calls.
        """
        farmers = [name for name, node in self._actors.items()
                   if self.is_alive(name) and self.eng.node(node)["attrs"].get("role") == "farm_labourer"]
        # Keep the named farmers available for food preparation when the
        # labourers can cover field work; small scenarios with no labourers
        # still fall back to farmers for cultivation.
        if not farmers:
            farmers = [name for name, node in self._actors.items()
                       if self.is_alive(name) and self.eng.node(node)["attrs"].get("role") == "farmer"]
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
            crop = next((candidate for candidate in ("wheat", "barley", "oats")
                         if self.qty(E.CROPS[candidate]["seed"]) >= 1.0
                         and E.CROPS[candidate]["season"] == self.season()), None)
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
        millers = [name for name, node in self._actors.items()
                   if self.is_alive(name) and self.eng.node(node)["attrs"].get("role") == "miller"]
        bakers = [name for name, node in self._actors.items()
                  if self.is_alive(name) and self.eng.node(node)["attrs"].get("role") == "baker"]
        cooks = [name for name, node in self._actors.items()
                 if self.is_alive(name) and "cook" in self.eng.node(node)["attrs"].get("trades", "").split(",")]
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
            grain_reserve = max(4.0, grain_feed_demand * 4.0)
            for name in millers:
                if (not self.actor_turn_state(name)["major_action_used"]
                        and self.qty("grain") >= 3.0 + grain_reserve):
                    self._village_start(name, "grind_flour")
        for name in bakers:
            if not self.actor_turn_state(name)["major_action_used"] and self.qty("flour") >= 2:
                self._village_start(name, "bake_bread")

    def run_village(self, periods=1, *, ticks_per_period=96):
        """Advance the seeded village while each resident decides independently.

        ``tick`` pumps private Ocelot minds; this method supplies only the
        world clock and the publication cadence.
        """
        if not getattr(self, "_cast100", None):
            raise ValueError("run_village requires BigvilleWorld.from_town100()")
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
            if int(self.calendar()["day"]) % 7 == 0:
                self._publish_village_weekly()
        return self.sanity_report()

    def pass_period(self, n=1):
        """Advance world metabolism and ecology without performing resident actions.

        Residents become hungry here, but no resident buys, carries, serves, or eats
        food as a side effect of time passing.  Those are actor actions.
        """
        for _ in range(int(n)):
            if getattr(self, "_cast100", None):
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
        spec = E.CROPS[crop]
        if spec["season"] != self.season():
            return None                                     # out of season -- nothing is sown
        self.set_stock(spec["seed"], max(0.0, self.qty(spec["seed"]) - 1.0))    # a seed is used
        c = self.eng.add_node("Crop", {"crop": crop, "age": 0.0, "thirst": 0.0, "thirst_epoch": 0.0,
                                       "alive": 1.0, "water": float(spec["water"]), "wilt": float(spec["wilt"]),
                                       "grow_periods": float(spec["grow_periods"]), "harvest": spec["harvest"],
                                       "water_armed": 0.0,
                                       "yield": float(spec["yield"])})
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
            self.set_stock(a["harvest"], self.qty(a["harvest"]) + float(a["yield"]))
            # Harvesting is also the seed loop that makes a farm renewable.
            # The returned seed is a physical reserve, not a hidden crop
            # respawn; sowing still consumes it and remains seasonal.
            seed = E.CROPS[a["crop"]]["seed"]
            self.set_stock(seed, self.qty(seed) + float(E.CROPS[a["crop"]].get("seed_return", 1.0)))
            self.eng.set_attr(crop_node, "alive", 0.0)
            self.eng.remove_edge_unchecked(self._town, "has_crop", crop_node)
            return float(a["yield"])
        return 0.0

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

    def give_product(self, animal, product):
        """The animal yields one of its products (a cow's milk, a chicken's eggs) into the store."""
        spec = E.ANIMALS[self.eng.node(self._animals[animal])["attrs"]["species"]]
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

    _SLAUGHTER = {"pork", "beef", "mutton", "poultry", "fish", "ham", "bacon", "sausage", "hide"}

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
        for product, qty in E.ANIMALS[self.eng.node(an)["attrs"]["species"]]["gives"].items():
            if product in self._SLAUGHTER:
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
        self._run()

    # ---------------------------------------------------- books (physical, record a recipe, read to learn)
    def write_in_book(self, author, book, recipe):
        """An author who KNOWS a recipe writes it into a made book (a physical record with weight).
        Refused (None) if the author cannot write (below functional literacy)."""
        assert self.knows(author, recipe), f"{author} does not know {recipe}"
        if not self._can_read(author):
            return None
        self.eng.set_attr(book, "recipe", recipe)
        self.eng.add_edge_unchecked(self._actors[author], "wrote", book)
        return book

    def read_book(self, reader, book):
        """Read a book -- a LITERATE reader learns the recipe written in it. Refused (None, no learning)
        if the reader cannot read (below functional literacy)."""
        if not self._can_read(reader):
            return None
        recipe = self.eng.node(book)["attrs"].get("recipe", "")
        if recipe:
            self.eng.add_edge_unchecked(self._actors[reader], "knows", self._actions[recipe])
        return recipe

    def book_recipe(self, book): return self.eng.node(book)["attrs"].get("recipe", "")

    def animal_role(self, animal): return self.eng.node(self._animals[animal])["attrs"]["role"]
    def animal_gives(self, species): return dict(E.ANIMALS[species]["gives"])
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

    def add_tradesperson(self, name, trade, *, skill=None, station="educated", literacy=None, capability=None):
        """Add a tradesperson: role = the trade, skill from the TRADES table (unifies trade + skill).
        Townsfolk are UPPITY -- educated by default; `station` (labouring/middle/educated) or an
        explicit literacy/capability sets a lower tier, and literate trades (scribe, teacher) carry
        their own in the TRADES data."""
        t = E.TRADES.get(trade, {})
        s = skill if skill is not None else float(t.get("base_skill", 0.7))
        prof = E.STATION_EDUCATION.get(station, E.STATION_EDUCATION["educated"])
        lit = literacy if literacy is not None else float(t.get("literacy", prof["literacy"]))
        cap = capability if capability is not None else float(t.get("capability", prof["capability"]))
        return self.add_actor(name, role=trade, skill=s, literacy=lit, capability=cap)

    def add_actor(self, name, *, role, skill=0.7, station="educated", literacy=None, capability=None,
                  learn=1.0, home_cell=None, work_cell=None, klass="", age=30.0,
                  life_stage="adult", role_identity=None, group="", traits=None, trades=()):
        """Add a resident. LITERACY + general CAPABILITY are class-graded (station), but this town is
        UPPITY -- residents default to EDUCATED. `station` (labouring/middle/educated) or an explicit
        literacy/capability picks a lower tier; `learn` is the aptitude that scales schooling (0 = cannot learn)."""
        prof = E.STATION_EDUCATION.get(station, E.STATION_EDUCATION["labouring"])
        lit = prof["literacy"] if literacy is None else float(literacy)
        cap = prof["capability"] if capability is None else float(capability)
        stage = E.LIFE_STAGES.get(life_stage, E.LIFE_STAGES["adult"])
        healthy = E.HEALTH_CONDITIONS["healthy"]
        a = self.eng.add_node("Agent", {"name": name, "role": role, "skill": float(skill),
                                        "age": float(age), "life_stage": life_stage, "health": "healthy",
                                        "health_value": 1.0, "disease": "", "injury": 0.0,
                                        "coin": 10.0, "wage_due": 0.0, "reputation": 0.5,
                                        "klass": klass, "group": group,
                                        "trade": next(iter(trades), role),
                                        "trades": ",".join((role,) + tuple(trades)),
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
                                        "hunger": 0.0, "hunger_epoch": 0.0, "alive": 1.0, "starve_limit": 4.0,
                                        "eat_armed": 0.0,
                                        "appr_epoch": 0.0,   # apprenticeship: skill grows under a master
                                        # reading/writing + general capability (class-graded; raised at school)
                                        "literacy": lit, "capability": cap, "learn": float(learn), "school_epoch": 0.0,

                                        # observed-demand decision state
                                        "decide_armed": 0.0, "observe_armed": 0.0, "will_make": "",
                                        "want_qty": 0.0, "last_driver": "", "unsold": 0.0,
                                        "belief_harvest": 0.0, "belief_building": 0.0, "belief_storage": 0.0,
                                        # container-op state
                                        "fill_armed": 0.0, "fill_amount": 0.0, "fill_kind": "",
                                        "empty_armed": 0.0, "empty_amount": 0.0, "empty_kind": "",
                                        "lock_armed": 0.0, "unlock_armed": 0.0})
        self.eng.add_edge_unchecked(self._town, "has_actor", a)
        self._actors[name] = a
        body = self.eng.add_node("Body", {
            "health": 1.0, "mood": 0.5, "satiety": 0.0,
            "last_food": -1.0, "food_run": 0.0,
            "str_base": 1.0, "sta_base": 1.0, "str_train": 0.0,
            "sta_train": 0.0, "strength": 1.0, "stamina": 1.0,
            "stats_dirty": 0.0, "stamina_reserve": 1.0})
        self.eng.add_edge_unchecked(a, "has_body", body)
        self._bodies[name] = body
        self._actor_minds[name] = BigvilleOcelotActor(name)
        self._actor_decisions[name] = {"action": "", "kind": "", "trade": "", "recipe": "", "target": ""}
        self._actor_targets[name] = {}
        # Food is held by residents, never implicitly by the town on their
        # behalf.  The inventory is an ordinary physical carrier so quantity
        # and capacity remain inspectable graph state.
        inventory_name = f"inventory:{name}"
        self.add_carrier(inventory_name, holds=(), max_load=50.0, capacity=50.0)
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
        self._made = getattr(self, "_made", {}); self._made[name] = 0
        present_roles = {self.eng.node(existing)["attrs"].get("role", "") for existing in self._actors.values()}
        for existing in self._actors.values():
            existing_role = self.eng.node(existing)["attrs"].get("role", "")
            for reference in E.shared_concepts_for(existing_role, present_roles):
                self._seed_reference(existing, reference)
        recipe_roles = {role, *trades}
        for r in E.RECIPES:                              # a resident KNOWS their trade's COMMON recipes
            if r.get("requires") in recipe_roles and r.get("common") is not False:
                self.eng.add_edge_unchecked(a, "knows", self._actions[r["name"]])
        return a

    # ---------------------------------------------------- recipe knowledge (taught + written down)
    def knows(self, actor, recipe):
        return self.eng.has_edge(self._actors[actor], "knows", self._actions[recipe])

    def teach(self, teacher, learner, recipe):
        """A resident who KNOWS a recipe teaches it to another -- the learner now knows it."""
        if self.knows(teacher, recipe):
            self.eng.add_edge_unchecked(self._actors[learner], "knows", self._actions[recipe])
        return self.knows(learner, recipe)

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
              conversation=None, message=None):
        """Create a communication event without touching the major-action budget.

        A game-session conversation adapter may additionally render a
        structured message for a recipient whose cognition backend cannot
        consume free text. It does not expose ``ask`` as a world action.
        """
        self._actor(speaker)
        if target is not None:
            self._actor(target)
            conversation = conversation or self._conversation(speaker, target)
        speech_meta = {}
        if self._conversation_adapter is not None:
            speech_meta = dict(self._conversation_adapter(speaker, target, content, message) or {})
            content = speech_meta.pop("content", content)
        conv = conversation
        attrs = {
            "content": str(content), "loudness": float(loudness),
            "speaker": speaker, "target": target or "", "turn": float(self._turn),
            "heard": 1.0 if target is None or self.actor_position(speaker) == self.actor_position(target) else 0.0,
        }
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
    def injure(self, actor, *, severity=0.25, cause="accident"):
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
        if self.eng.node(self._actors[doctor])["attrs"].get("role") not in {"doctor", "midwife"}:
            return False
        self.eng.set_attr(self._actors[patient], "disease", condition)
        self.eng.set_attr(self._actors[patient], "health", condition)
        illness = self.eng.add_node("Illness", {"patient": patient, "condition": condition,
                                                 "started_day": float(self.calendar()["day"]), "active": 1.0})
        self.eng.add_edge_unchecked(self._town, "has_illness", illness)
        self._illnesses[f"illness:{len(self._illnesses) + 1}"] = illness
        return illness

    def treat(self, doctor, patient, *, medicine=0.0):
        if self.eng.node(self._actors[doctor])["attrs"].get("role") not in {"doctor", "midwife"}:
            return False
        if medicine and self.qty("medicine") < medicine:
            return False
        if medicine:
            self.set_stock("medicine", self.qty("medicine") - float(medicine))
        node = self._actors[patient]
        self.eng.set_attr(node, "health", "healthy")
        self.eng.set_attr(node, "disease", "")
        self.eng.set_attr(node, "injury", 0.0)
        self.eng.set_attr(node, "health_value", min(1.0, float(self.eng.node(node)["attrs"].get("health_value", 0.5)) + 0.25))
        self.eng.add_edge_unchecked(self._actors[doctor], "treated", node)
        return True

    def care_for(self, caregiver, patient):
        """Perform one co-located care action for an injured or ill resident."""
        if caregiver not in self._actors or patient not in self._actors:
            return False
        role = self.eng.node(self._actors[caregiver])["attrs"].get("role")
        if role not in {"doctor", "midwife"}:
            return False
        if self._turn > 0 and self.actor_position(caregiver) != self.actor_position(patient):
            return False
        attrs = self.eng.node(self._actors[patient])["attrs"]
        if (attrs.get("health") == "healthy" and float(attrs.get("injury", 0.0)) <= 0.0
                and float(attrs.get("hunger", 0.0)) < 2.0):
            return False
        medicine = 1.0 if self.qty("medicine") >= 1.0 and attrs.get("disease") else 0.0
        if medicine:
            return self.treat(caregiver, patient, medicine=medicine)
        self.eng.set_attr(self._actors[patient], "injury", max(0.0, float(attrs.get("injury", 0.0)) - 0.2))
        self.eng.set_attr(self._actors[patient], "health_value",
                          min(1.0, float(attrs.get("health_value", 1.0)) + 0.1))
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

    def record_death(self, actor, *, cause="unknown"):
        node = self._actors[actor]
        if float(self.eng.node(node)["attrs"].get("alive", 1.0)) != 1.0:
            return False
        self.eng.set_attr(node, "alive", 0.0)
        self.eng.set_attr(node, "health", "dead")
        event = self.create_event("death", subject=actor, detail=f"{actor} died ({cause}).", public=True)
        self._deaths.append({"actor": actor, "day": self.calendar()["day"], "cause": cause, "event": str(event)})
        return True

    def _daily_life_tick(self):
        """Advance age and mild recovery at dawn; severe outcomes remain explicit actions."""
        for name, node in self._actors.items():
            a = self.eng.node(node)["attrs"]
            if float(a.get("alive", 1.0)) != 1.0:
                continue
            age = float(a.get("age", 30.0)) + 1.0 / 360.0
            self.eng.set_attr(node, "age", age)
            injury = float(a.get("injury", 0.0))
            if injury > 0.0:
                self.eng.set_attr(node, "injury", max(0.0, injury - 0.05))
                self.eng.set_attr(node, "health_value", min(1.0, float(a.get("health_value", 1.0)) + 0.02))
                if injury <= 0.05:
                    self.eng.set_attr(node, "health", "healthy")
            if float(a.get("hunger", 0.0)) >= 2.0:
                self.eng.set_attr(node, "health", "malnourished")
            if a.get("disease"):
                health = max(0.0, float(a.get("health_value", 1.0)) - 0.05)
                self.eng.set_attr(node, "health_value", health)
                if health <= 0.0:
                    self.record_death(name, cause=str(a.get("disease")))
            age_stage = next((stage for stage, spec in E.LIFE_STAGES.items()
                              if float(spec["age_min"]) <= age <= float(spec["age_max"])), "elder")
            if age_stage != a.get("life_stage"):
                self.eng.set_attr(node, "life_stage", age_stage)

    def add_waste(self, kind="kitchen_scraps", amount=1.0):
        cycle = E.WASTE_CYCLES[kind]
        source = cycle["output"] if cycle["output"] in self._stock else "compost"
        if source in self._stock:
            self.set_stock(source, self.qty(source) + float(amount))
        return source

    def process_waste(self, operator, kind="kitchen_scraps", amount=1.0):
        role = self.eng.node(self._actors[operator])["attrs"].get("role")
        if role not in {"farmer", "farm_labourer", "labourer", "compost_keeper"}:
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(operator, "process_waste"):
            return False
        return self.add_waste(kind, amount)

    def school_lesson(self, teacher, pupil, *, subject="literacy"):
        """Run one institutional lesson; learning remains held by the pupil."""
        if self.eng.node(self._actors[teacher])["attrs"].get("role") != "teacher":
            return False
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(teacher, "teach"):
            return False
        ta = self.eng.node(self._actors[teacher])["attrs"]
        pa = self.eng.node(self._actors[pupil])["attrs"]
        if float(pa.get("alive", 1.0)) != 1.0 or float(pa.get("learn", 0.0)) <= 0.0:
            return False
        field = "literacy" if subject == "literacy" else "capability"
        ceiling = float(ta.get(field, 0.0))
        value = float(pa.get(field, 0.0))
        self.eng.set_attr(self._actors[pupil], field, min(ceiling, value + 0.02 * float(pa.get("learn", 1.0))))
        self.eng.set_attr(self._actors[pupil], "school_epoch", float(self.calendar()["day"]))
        self.eng.add_edge_unchecked(self._actors[pupil], "learned_from", self._actors[teacher])
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
        service = E.food_service(kind)
        if service is None:
            return None
        vessels = [k for k in self._actor_tableware.get(actor, {})
                   if self._has_tableware(actor, k) and self._item_specs.get(k, {}).get("container")]
        utensils = [k for k in self._actor_tableware.get(actor, {})
                    if self._has_tableware(actor, k) and self._item_specs.get(k, {}).get("utensil")]
        for vessel in vessels:
            for utensil in utensils:
                if E.can_serve(kind, vessel, utensil):
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
        hungry = float(attrs.get("hunger", 0.0)) > 0.0
        held_food = any(spec.get("food") and self.inventory_qty(actor, kind) >= 1.0
                        for kind, spec in self._item_specs.items())
        for kind, spec in self._item_specs.items():
            if spec.get("food") and self.inventory_qty(actor, kind) >= 1.0:
                if spec.get("prepared") and self._serving_equipment(actor, kind) is None:
                    continue
                options.append({"action": "eat", "kind": kind, "trade": "", "recipe": "", "target": "",
                                "score": 100.0 if hungry else -1.0})
        # A seller is a resident, not a shop.  A shop may be a useful local
        # convention for where a seller usually works, but it is not required
        # for a purchase or for this affordance to exist.
        if hungry and not held_food:
            # Hunger can be met from a physical household store, but only by
            # travelling to it and fetching the held stock first.
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
                                    "target": key, "score": 98.0})
                elif reachable_destination(destination):
                    key = target_key(destination)
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "target": key, "score": 98.0})
                break
            for seller, seller_node in self._actors.items():
                if seller == actor or not self.is_alive(seller):
                    continue
                seller_attrs = self.eng.node(seller_node)["attrs"]
                if float(seller_attrs.get("sell_willing", 0.0)) != 1.0:
                    continue
                for kind, spec in self._item_specs.items():
                    if (not spec.get("food") or self.inventory_qty(seller, kind) < 1.0
                            or not self._inventory_can_receive(actor, kind)):
                        continue
                    price = float(seller_attrs.get("sell_price", 0.0))
                    seller_position = self.actor_position(seller)
                    if seller_position is None:
                        continue
                    co_located = self.actor_position(actor) == seller_position
                    if not co_located and not reachable_destination(seller_position):
                        continue
                    key = target_key(seller if co_located else seller_position)
                    options.append({"action": "give" if co_located else "move", "kind": kind,
                                    "trade": seller, "recipe": "", "target": key,
                                    "score": (92.0 - price) if co_located else 96.0})
        for trade, shop_node in self._shops.items():
            shop = self.eng.node(shop_node)["attrs"]
            price = float(shop.get("price", 0.0))
            output = shop.get("output_kind", "")
            if (not held_food
                    and self._at_shop(actor, trade)
                    and self._market_counterparty(actor, trade, output) is not None
                    and self.coin(actor) >= price
                    and self.qty(output) >= 1.0
                    and self._inventory_can_receive(actor, output)):
                options.append({"action": "give", "kind": output, "trade": trade, "recipe": "", "target": "",
                                "score": (90.0 - price) if hungry else -price})
            elif (hungry and not held_food
                  and self._item_specs.get(output, {}).get("food")
                  and self.qty(output) >= 1.0
                  and (self.coin(actor) >= price
                       or float(shop.get("coin", 0.0)) >= 2.0)
                  and self.actor_position(actor) != self.shop_position(trade)
                  and reachable_destination(self.shop_position(trade))):
                # Food is not teleported to the resident.  Reaching the shop
                # is the resident's major movement choice; only then can a
                # heard purchase utterance be followed by give().
                key = target_key(self.shop_position(trade))
                options.append({"action": "move", "kind": "", "trade": trade, "recipe": "",
                                "target": key, "score": 96.0})

        # A tradesperson who has made or is collecting a good must physically
        # fetch it from the mapped store before carrying it to other people.
        roles = set(str(attrs.get("trades", "")).split(","))
        market_cell = self.map_position_node(self._store)
        if market_cell is not None:
            for trade, shop_node in self._shops.items():
                output = self.eng.node(shop_node)["attrs"].get("output_kind", "")
                if output not in self._item_specs or self.qty(output) < 1.0:
                    continue
                trade_names = roles | {str(attrs.get("role", ""))}
                if trade not in trade_names and not (trade == "bakery" and "baker" in trade_names):
                    continue
                if (self.actor_position(actor) == market_cell
                        and self._inventory_can_receive(actor, output)):
                    key = target_key(("store", output))
                    options.append({"action": "fetch", "kind": output, "trade": trade, "recipe": "",
                                    "target": key, "score": 17.0})
                elif not hungry and not held_food and reachable_destination(market_cell):
                    key = target_key(market_cell)
                    options.append({"action": "move", "kind": "", "trade": trade, "recipe": "",
                                    "target": key, "score": 13.0})
                break
        if hungry and not any(option["action"] in {"eat", "give"} for option in options):
            for trade, shop_node in self._shops.items():
                if (self._at_shop(actor, trade)
                        and float(self.eng.node(shop_node)["attrs"].get("coin", 0.0)) >= 2.0):
                    options.append({"action": "sell_labor", "kind": "", "trade": trade,
                                    "recipe": "", "target": "", "score": 95.0})

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
                                    "target": key, "score": 5.0})
                elif (not hungry and self._container_can_receive(container, kind)
                      and reachable_destination(destination)):
                    key = target_key(destination)
                    options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                    "target": key, "score": 7.0})
                break
        # Workplaces are observed map facts, but travelling to one is still a
        # resident choice.  Publish one step of that journey as an ordinary
        # affordance; the actor's Ocelot chooses it when no more urgent
        # sustenance or farm action outranks it.  Without this, canonical
        # residents stay forever at their unique home cells and the speech
        # faculty never gets a physical encounter with another resident.
        work_x = attrs.get("work_x")
        work_y = attrs.get("work_y")
        if work_x is not None and work_y is not None:
            work_cell = (int(round(float(work_x))), int(round(float(work_y))))
            if (self.actor_position(actor) != work_cell and work_cell in self._map_cells
                    and reachable_destination(work_cell)):
                key = target_key(work_cell)
                options.append({"action": "move", "kind": "", "trade": "", "recipe": "",
                                "target": key, "score": 15.0})
        if roles & {"farmer", "farm_labourer"}:
            for animal, animal_node in self._animals.items():
                aa = self.eng.node(animal_node)["attrs"]
                species = aa.get("species")
                task = "milk" if species == "cow" else "shear" if species == "sheep" else ""
                if not task or not self.animal_alive(animal):
                    continue
                period = float(self.eng.node(self._town)["attrs"].get("period", 0.0))
                cooldown = float(E.ANIMAL_HUSBANDRY[task]["cooldown"])
                if period - float(aa.get(f"{task}_epoch", -cooldown)) < cooldown:
                    continue
                animal_cell = self.map_position_node(animal_node)
                if animal_cell is not None:
                    if self.actor_position(actor) != animal_cell and not reachable_destination(animal_cell):
                        continue
                    key = target_key(animal if self.actor_position(actor) == animal_cell else animal_cell)
                    options.append({"action": "tend_animals", "kind": task, "trade": "", "recipe": "",
                                    "target": key, "score": 34.0 if self.actor_position(actor) == animal_cell else 16.0})
            for crop in self._living_crops():
                crop_attrs = self.eng.node(crop)["attrs"]
                if (float(crop_attrs.get("thirst", 0.0)) > 0.0
                        and self.qty("water") >= float(crop_attrs.get("water", 0.0))):
                    destination = self.map_position_node(crop)
                    if destination is not None and reachable_destination(destination):
                        key = target_key(crop if self.actor_position(actor) == destination else destination)
                        options.append({"action": "water" if self.actor_position(actor) == destination else "move",
                                        "kind": "", "trade": "", "recipe": "",
                                        "target": key, "score": 30.0 if self.actor_position(actor) == destination else 14.0})
            for crop in self._living_crops():
                if self.crop_mature(crop):
                    destination = self.map_position_node(crop)
                    if destination is not None and reachable_destination(destination):
                        key = target_key(crop if self.actor_position(actor) == destination else destination)
                        options.append({"action": "harvest" if self.actor_position(actor) == destination else "move",
                                        "kind": "", "trade": "", "recipe": "",
                                        "target": key, "score": 35.0 if self.actor_position(actor) == destination else 14.0})
            # A mapped parcel can contain many beds.  The parcel's occupancy
            # is not a one-crop gate; each sowing is its own physical Crop
            # affordance on that parcel.
            for land_name in sorted(name for name in self._land if name.startswith("farm_plot_")):
                for crop_name in ("wheat", "barley", "oats"):
                    seed = E.CROPS[crop_name]["seed"]
                    if (E.CROPS[crop_name]["season"] == self.season()
                            and self.qty(seed) >= 1.0):
                        destination = self.map_position_node(self._land[land_name])
                        if destination is not None and reachable_destination(destination):
                            key = target_key((crop_name, land_name) if self.actor_position(actor) == destination
                                             else destination)
                            options.append({"action": "sow" if self.actor_position(actor) == destination else "move",
                                            "kind": "", "trade": "", "recipe": "",
                                            "target": key, "score": 25.0 if self.actor_position(actor) == destination else 12.0})
                        break

        # Construction projects are physical places and require a resident
        # builder to travel there before spending materials and labour.
        if roles & {"mason", "carpenter", "woodworker", "labourer", "farm_labourer"}:
            for project, project_node in self._building_projects.items():
                data = self.eng.node(project_node)["attrs"]
                if data.get("status") == "complete":
                    continue
                spec = E.BUILDING_PROJECTS[data["project"]]
                remaining = max(0.0, float(data["labour"]) - float(data["progress"]))
                scale = (min(1.0, remaining) / float(data["labour"])) if data.get("labour") else 0.0
                if any(self.qty(kind) < float(qty) * scale for kind, qty in spec.get("inputs", {}).items()):
                    continue
                cells = list(self.eng.neighbours(project_node, "at_cell"))
                destination = self.map_position_node(cells[0]) if cells else None
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(project if self.actor_position(actor) == destination else destination)
                options.append({"action": "build", "kind": "", "trade": "", "recipe": project,
                                "target": key, "score": 18.0 if self.actor_position(actor) == destination else 8.0})
            for name, infra_node in self._infrastructure.items():
                if self.infrastructure_condition(name) >= 0.8:
                    continue
                infra_spec = E.INFRASTRUCTURE[self.eng.node(infra_node)["attrs"]["kind"]]
                if any(self.qty(kind) < 1.0 for kind in infra_spec.get("maintenance", ())):
                    continue
                destination = self.map_position_node(infra_node)
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(name if self.actor_position(actor) == destination else destination)
                options.append({"action": "maintain", "kind": "", "trade": "", "recipe": "",
                                "target": key, "score": 20.0 if self.actor_position(actor) == destination else 9.0})

        if attrs.get("role") in {"doctor", "midwife"}:
            for patient, patient_node in self._actors.items():
                if patient == actor or not self.is_alive(patient):
                    continue
                pa = self.eng.node(patient_node)["attrs"]
                needs_care = (pa.get("health") != "healthy"
                              or float(pa.get("injury", 0.0)) > 0.0
                              or float(pa.get("hunger", 0.0)) >= 2.0)
                if not needs_care:
                    continue
                destination = self.actor_position(patient)
                if destination is None:
                    continue
                if self.actor_position(actor) != destination and not reachable_destination(destination):
                    continue
                key = target_key(patient if self.actor_position(actor) == destination else destination)
                options.append({"action": "care", "kind": "", "trade": "", "recipe": "",
                                "target": key, "score": 38.0 if self.actor_position(actor) == destination else 20.0})
                break
        for recipe in E.RECIPES:
            if (not busy and recipe.get("requires") in roles and self.knows(actor, recipe["name"])
                    and self._recipe_inputs_available(recipe["name"])):
                out_kind = recipe.get("out", [""])[0]
                options.append({"action": "work", "kind": out_kind, "trade": "", "target": "",
                                "recipe": recipe["name"],
                                "score": 12.0 if out_kind in {"bread", "gruel"} else 10.0})
        options.append({"action": "rest", "kind": "", "trade": "", "recipe": "", "target": "", "score": 0.0})
        self._actor_targets[actor] = targets
        return options

    def _decide_actor(self, actor):
        """Ask the resident's Ocelot instance to choose from current affordances."""
        mind = self._actor_minds[actor]
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
        self._actor_options(actor)
        return self._enact_plan(actor, dict(plan))

    def _enact_plan(self, actor, plan):
        """Shared physical enactment for Ocelot and arbitrary cognition backends."""
        if plan["action"] == "give":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._actors:
                seller = target
                seller_attrs = self.eng.node(self._actor(seller))["attrs"]
                if self.purchase_utterance(actor, seller, plan["kind"], 1.0) is False:
                    return False
                return self.major_action(actor, "give", recipient=seller,
                                         kind=plan["kind"], amount=1.0,
                                         payment_kind="coin",
                                         payment_amount=float(seller_attrs.get("sell_price", 0.0)))
            trade = plan.get("trade", "")
            if self.purchase_utterance(actor, trade, 1.0) is False:
                return False
            shop = self.eng.node(self._shops[trade])["attrs"]
            return self.major_action(actor, "give", recipient=trade,
                                     kind=plan["kind"], amount=1.0,
                                     payment_kind="coin",
                                     payment_amount=float(shop.get("price", 0.0)))
        if plan["action"] == "sell_labor":
            return self.major_action(actor, "sell_labor", trade=plan["trade"], amount=2.0)
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
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "put":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target is not None:
                return self.major_action(actor, "put", container=target, kind=plan["kind"], amount=1.0)
        if plan["action"] == "fetch":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            source = target if target in self._containers else None
            return self.major_action(actor, "fetch", kind=plan["kind"], amount=1.0, source=source)
        if plan["action"] == "tend_animals":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._animals:
                return self.major_action(actor, "tend_animals", animal=target, task=plan["kind"])
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "build":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._building_projects:
                return self.major_action(actor, "build", project=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "maintain":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._infrastructure:
                return self.major_action(actor, "maintain", name=target, labour=1.0)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] == "care":
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target in self._actors:
                return self.major_action(actor, "care", patient=target)
            if target is not None:
                return self.major_action(actor, "move", destination=target)
        if plan["action"] in {"water", "harvest", "sow"}:
            target = self._actor_targets[actor].get(plan.get("target", ""))
            if target is not None:
                return self.major_action(actor, plan["action"], target=target)
        return False

    def resolve_actor_turn(self):
        """Settle deferred physical effects and publish free speech once."""
        self._run()
        self._spontaneous_speech_tick()

    def _ocelot_actor_tick(self):
        """Pump each private mind and enact major choices plus free speech."""
        self._actor_tick_in_progress = True
        try:
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

    def _speech_goal(self, target, kind):
        """Build a grounded communicative meaning for a speech occasion.

        Ocelot selects the occasion.  This bridge contributes only concepts
        already available in the town observation; ``WorldAdapter`` owns the
        graph-resident goal, rendering, and addressee uptake.
        """
        town = self.eng.node(self._town)["attrs"]
        weather = str(town.get("weather", "clear"))
        if kind == "greeting":
            return {"greeting": {"of": str(target)}}
        if kind == "smalltalk":
            return {"weather": {"of": weather}}
        if kind == "barb":
            return {"warning": {"of": str(target)}}
        if kind == "hedged":
            return {"uncertainty": {"of": "work"}}
        if kind == "share":
            return {"news": {"of": {"village": {"weather": weather}}}}
        if kind == "answer":
            return {"acknowledgement": {"of": str(target)}}
        return None

    def _spontaneous_speech_tick(self):
        """Publish co-presence encounters and let each resident decide freely."""
        by_position = {}
        for actor in list(self._actors):
            if self.is_alive(actor) and self.actor_position(actor) is not None:
                by_position.setdefault(self.actor_position(actor), []).append(actor)
        for present in by_position.values():
            if len(present) < 2:
                continue
            # A crowd is a physical opportunity, not an instruction to run a
            # private cognition pass for every ordered pair.  Form one observed
            # encounter per occupied cell and let both residents' speech
            # faculties decide their own turns.  The random pairing gives a
            # crowd changing conversational partners without a world schedule.
            speaker, target = self._rng.sample(present, 2)
            for speaker, target in ((speaker, target), (target, speaker)):
                choice = self._actor_minds[speaker].decide_speech(
                    target, relationship=self._speech_relationship(speaker, target),
                    stranger=False,
                    arousal=float(self.eng.node(self._actors[speaker])["attrs"].get("arousal", 0.4)),
                    loquacity_threshold=float(self.eng.node(self._actors[speaker])["attrs"].get(
                        "loquacity_threshold", 1.0)))
                if not choice["spoken"]:
                    continue
                meaning = self._speech_goal(target, choice["kind"])
                if meaning is None:
                    continue
                content = self._actor_minds[speaker].goal_utterance(target, meaning)
                if not content:
                    continue
                utterance = self.speak(
                    speaker, target, content,
                    loudness=max(1.0, choice.get("loudness", 1.0)),
                    message={"act": choice["kind"], "slots": {
                        "target": str(target), "meaning": meaning,
                    }})
                self._speech_events.append({
                    "turn": int(self._turn), "speaker": speaker, "target": target,
                    "kind": choice["kind"], "content": content,
                    "heard": bool(self.eng.node(utterance)["attrs"].get("heard", 0.0)),
                })

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
                           "literacy": a.get("literacy", 0.0), "coin": a.get("coin", 0.0),
                           "reputation": a.get("reputation", 0.5), "position": position,
                           "home": position, "x": position[0] if position else 0, "y": position[1] if position else 0,
                           "household": a.get("household", ""),
                           "inventory": self.inventory(name),
                           "references": sorted(self.known_references(name)),
                           "journal": (dict(self.eng.node(self._journals[name][-1])["attrs"])
                                       if self._journals.get(name) else None)})
        buildings = []
        for kind in sorted(self._places):
            position = self.building_position(kind)
            x, y = position if position else (0, 0)
            buildings.append({"id": kind, "type": kind, "position": position,
                              "x": x, "y": y, "w": 3, "h": 3, "name": kind.title()})
        events = []
        for key, node in list(self._events.items())[-event_tail if event_tail else None:]:
            events.append({"id": key, **dict(self.eng.node(node)["attrs"])})
        articles = [{"id": key, **dict(self.eng.node(node)["attrs"])} for key, node in self._articles.items()]
        utterances = [{"id": int(node.value), **dict(self.eng.node(node)["attrs"])}
                      for node in self._utterances.values()]
        map_width = len(self._map_grid[0]) if self._map_grid else 0
        map_height = len(self._map_grid or [])
        return {"schema": "townview/1", "clock": dict(self.calendar()),
                "weather": {k: town.get(k) for k in ("rain", "temperature", "firewood_demand")},
                "map": {"width": map_width, "height": map_height, "w": map_width, "h": map_height,
                        "grid": self._map_grid, "tiles": self._map_grid,
                        "buildings": buildings},
                "residents": actors,
                "stocks": {kind: self.qty(kind) for kind in sorted(self._stock) if kind != "none"},
                "animals": [{"id": name, **dict(self.eng.node(node)["attrs"]),
                             "position": self.map_position_node(node)} for name, node in self._animals.items()],
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
                "sanity": self.sanity_report()}

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
        if action == "give":
            recipient = kwargs.get("recipient", kwargs.get("target", args[0] if args else None))
            kind = kwargs.get("kind", args[1] if len(args) > 1 else None)
            amount = kwargs.get("amount", args[2] if len(args) > 2 else 1.0)
            if recipient is None or kind is None or not self._claim_major_action(actor, "give"):
                return False
            self._major_dispatch = True
            try:
                return self.give(actor, recipient, kind, amount,
                                 payment_kind=kwargs.get("payment_kind"),
                                 payment_amount=kwargs.get("payment_amount"))
            finally:
                self._major_dispatch = False
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
                if task == "milk":
                    return self.milk(actor, animal) > 0.0
                if task == "shear":
                    return self.shear(actor, animal) > 0.0
                return False
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
        if action in {"water", "harvest", "sow"}:
            target = kwargs.get("target", args[0] if args else None)
            if not self._claim_major_action(actor, action):
                return False
            self._major_dispatch = True
            try:
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
        """Transfer a reference held by one resident to another."""
        if self.knows_reference(teacher, name):
            self._seed_reference(self._actors[learner], self._reference_specs[name])
        return self.knows_reference(learner, name)

    def write_recipe(self, author, recipe):
        """Write a known recipe down -- a Recipe record anyone LITERATE can later read to learn it.
        Refused (None) if the author cannot write (below functional literacy)."""
        assert self.knows(author, recipe), f"{author} does not know {recipe} to write it"
        if not self._can_read(author):
            return None                                 # a labourer's low literacy -- cannot write it down
        rec = self.eng.add_node("WrittenRecipe", {"recipe": recipe})
        self.eng.add_edge_unchecked(self._actors[author], "wrote", rec)
        return rec

    def read_recipe(self, reader, record):
        """Read a written recipe -- a LITERATE reader learns it. Refused (None, no learning) if the
        reader cannot read (below functional literacy). Knowing it is still not being able to MAKE it
        (master work needs the skill -- apprenticeship)."""
        if not self._can_read(reader):
            return None                                 # cannot read it -- must be TAUGHT instead (orally)
        recipe = self.eng.node(record)["attrs"]["recipe"]
        self.eng.add_edge_unchecked(self._actors[reader], "knows", self._actions[recipe])
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
    def _can_read(self, actor): return self._lit(actor) >= E.LIT_FUNCTIONAL

    def literacy(self, actor): return round(self._lit(actor), 4)
    def capability(self, actor): return round(self._cap(actor), 4)
    def literacy_tier(self, actor): return E.literacy_tier(self._lit(actor))
    def can_read(self, actor):
        """Functional literacy -- read/write a note, read a written recipe, read the newspaper."""
        return self._can_read(actor)
    def can_read_law(self, actor):
        """Read AND understand the council laws -- only the well educated (needs high capability)."""
        return self._cap(actor) >= E.LIT_EDUCATED and self._lit(actor) >= E.LIT_EDUCATED
    def can_account(self, actor):
        """Keep accounts (reckoning) -- only the well educated."""
        return self._cap(actor) >= E.LIT_EDUCATED
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
        """Whether the actor could make it right now -- knows it AND is skilled enough."""
        return self._can_attempt(actor, action_name)

    # ---------------------------------------------------- observed-demand production loop
    def observe(self, maker, *, harvest=None, building=None, storage=None):
        """The maker OBSERVES the town's signals and updates his beliefs (po_observe)."""
        for k, v in (("observed_harvest", harvest), ("observed_building", building),
                     ("observed_storage", storage)):
            if v is not None:
                self.eng.set_attr(self._town, k, float(v))
        self.eng.set_attr(self._actors[maker], "observe_armed", 1.0); self._run()

    def decide(self, maker):
        """The maker DECIDES what and how many to make from his beliefs (pd_decide collapse)."""
        self.eng.set_attr(self._actors[maker], "decide_armed", 1.0); self._run()
        return self.will_make(maker)

    def produce_run(self, maker):
        """Make want_qty of the decided action; returns how many were produced."""
        m = self._actors[maker]
        qty = int(round(float(self.eng.node(m)["attrs"]["want_qty"])))
        made = 0
        for _ in range(qty):
            before = len(list(self.eng.neighbours(self._town, "has_tool_item")))
            self.do(maker, self.will_make(maker))
            made += len(list(self.eng.neighbours(self._town, "has_tool_item"))) - before
        self._made[maker] += made
        return made

    def sell(self, maker, n):
        unsold = max(0, self._made[maker] - int(n))
        self.eng.set_attr(self._actors[maker], "unsold", float(unsold))
        return unsold

    def belief(self, maker, driver="harvest"):
        return round(float(self.eng.node(self._actors[maker])["attrs"][f"belief_{driver}"]), 4)
    def will_make(self, maker): return self.eng.node(self._actors[maker])["attrs"].get("will_make", "")
    def want_qty(self, maker): return round(float(self.eng.node(self._actors[maker])["attrs"]["want_qty"]), 4)

    # ---------------------------------------------------- do an action (the ONE engine)
    def _open_job(self, actor, action_name, remaining):
        asp = self._actions[action_name]
        action_attrs = self.eng.node(asp)["attrs"]
        job = self.eng.add_node("Job", {"remaining": float(remaining), "last_tick": 0.0,
                                        "min_quality": 1.0, "item_inputs": 0.0,
                                        "canonical_actor": str(actor),
                                        "canonical_output_kind": str(action_attrs.get("out_kind", "")),
                                        "canonical_output_qty": float(action_attrs.get("out_qty", 0.0)),
                                        "canonical_output_claimed": 0.0})
        self.eng.add_edge_unchecked(self._actors[actor], "on_job", job)
        self.eng.add_edge_unchecked(job, "runs", asp)
        self.eng.set_attr(self._actors[actor], "busy", 1.0)
        for need in self.eng.neighbours(asp, "in_need"):
            a = self.eng.node(need)["attrs"]
            jn = self.eng.add_node("Need", {"kind": a["kind"], "qty": float(a["qty"]), "met": 0.0,
                                            "is_item": float(a.get("is_item", 0.0))})
            self.eng.add_edge_unchecked(job, "need", jn)
        for tu in self.eng.neighbours(asp, "in_tool"):
            a = self.eng.node(tu)["attrs"]
            jt = self.eng.add_node("ToolUse", {"kind": a["kind"], "met": 0.0})
            self.eng.add_edge_unchecked(job, "uses", jt)

    def _knows_or_none(self, actor, action_name):
        """An actor can only attempt a recipe they KNOW (a graph fact). Returns False if they don't."""
        return self.eng.has_edge(self._actors[actor], "knows", self._actions[action_name])

    def _skilled_enough(self, actor, action_name):
        """An actor can only attempt a recipe they are SKILLED enough for -- their skill must reach the
        recipe's min_skill floor. Reading the recipe is not enough; the hand needs the training."""
        skill = float(self.eng.node(self._actors[actor])["attrs"]["skill"])
        floor = float(self.eng.node(self._actions[action_name])["attrs"].get("min_skill", 0.0))
        return skill >= floor

    def _can_attempt(self, actor, action_name):
        """Admissible to attempt iff the actor KNOWS the recipe AND is SKILLED enough for it."""
        return self._knows_or_none(actor, action_name) and self._skilled_enough(actor, action_name)

    def do(self, actor, action_name):
        """Perform an action INSTANTLY (no timer). Refused if the actor does not KNOW the recipe or is
        not SKILLED enough (below its min_skill floor)."""
        if not self._can_attempt(actor, action_name):
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
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(actor, "start"):
            return False
        mins = float(self.eng.node(self._actions[action_name])["attrs"]["time_minutes"])
        self._open_job(actor, action_name, math.ceil(mins / MINUTES_PER_TICK)); self._run()
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
            self._run()
            # The town advances time. In normal mode each resident's private
            # Ocelot graph selects its own action; an interactive game mode
            # submits equivalent proposals through CognitionBackend instead.
            if self._autonomous_actors:
                self._ocelot_actor_tick()
            else:
                self._run()

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
    def instrument_condition(self, kind): return round(float(self.eng.node(self._tools[kind])["attrs"]["condition"]), 4)

    # ---------------------------------------------------- clothes: dyed, worn, protective
    def dye_garment(self, dyer, garment, dye_kind):
        """A dyer dyes a garment a colour from a dye pile -- the RULE (cl_dye) takes the colour from the
        dye's data and consumes one dye. The adapter only arms the garment against the dye Stock."""
        if self._turn > 0 and not self._major_dispatch and not self._claim_major_action(dyer, "dye"):
            return None
        dye = self.set_stock(dye_kind, self.qty(dye_kind))
        self.eng.set_attr(garment, "dye_armed", 1.0)
        self.eng.add_edge_unchecked(garment, "dyed_with", dye)
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
