"""WorldAdapter — the thin host layer for the seed-booted curiosity agent.

This is the burn's step 1+2: a reusable world adapter over `boot_core`, with no
agent decisions in it. It does exactly the permitted mechanical things:

  • boot the `curiosity_agent` seeds onto a bare Rust substrate (the agent IS
    the loaded graph data — no `CuriousAgent` Python class);
  • **ingest** a world's published substrate by MIRRORING it into the agent's
    substrate as `WorldInstance` nodes keyed by (type, world-id), carrying the
    world node's scalar attrs, with world edges mirrored between the instances.
    This is the instance-tracking half of the old `observe()` fold — pure I/O
    translation (world nodes → graph tokens), not reasoning;
  • **tick** — run the seeded Rules to fixed point;
  • **query** the result back out.

The agent's perception RECOGNITIONS (gauge, novelty, saturation, …) are seeded
Terms that read these `WorldInstance` nodes; the adapter only stamps them. This
replaces a world's `CuriousAgent` usage with: boot seeds → ingest → tick → read.
"""
from __future__ import annotations

import math as _math
import re as _re

from substrate.boot_core import boot_core, CORE_SEEDS

_SCALAR = (int, float, str, bool)

# Scalar Lit policies (thresholds/weights) seeded onto the agent node as graph
# data the agent reads (vs Python parameters). Editing a Lit changes behaviour.
_DEFAULT_SCALAR_POLICIES = {
    "insight_threshold": 0.7,
    "discovery_top_k_agent_world": 20,
    "discovery_top_k_type_pairs": 40,
    "discovery_min_count": 8,
    "discovery_triple_threshold": 30,
    "theorem_hold_threshold": 3,
    "meta_curiosity_weight": 0.15,
}


class WorldAdapter:
    def __init__(self, seeds=CORE_SEEDS, *, shadow_read=None, deep_ingest=None):
        # SHADOW READ (Wave 2, Deep-Reader): OPT-IN light deep-read of every
        # chat turn on the live substrate, purely additive (comp_* stays
        # authoritative -- see `converse`/`_shadow_read_turn`). Default OFF so
        # the ~1748-test bench never pays the one-time WordNet warm-up
        # (~1.5s) per fresh-boot test; an explicit `shadow_read=True/False`
        # kwarg wins, else `OZMA_SHADOW_READ=1` turns it on (the daemon's
        # `--shadow-read` flag, default on there).
        if shadow_read is None:
            import os as _os
            shadow_read = _os.environ.get("OZMA_SHADOW_READ") == "1"
        self.shadow_read = bool(shadow_read)
        # DEEP INGEST (Wave 4, Deep-Reader unification): OPT-IN full deep-read
        # of an uploaded text document at ingest (`domains/file_ingest.py::
        # _ingest_text` -> `_deep_read_document`), same opt-in family as
        # `shadow_read` (a one-shot ~100ms-1s cost, not paid by a bench test
        # that never sets it). Defaults to whatever `shadow_read` resolved to
        # (the two flags travel together unless a caller explicitly wants
        # only one); an explicit `deep_ingest=True/False` kwarg wins.
        if deep_ingest is None:
            deep_ingest = self.shadow_read
        self.deep_ingest = bool(deep_ingest)
        self.s, self.agent = boot_core(seeds)
        self.inner = self.s._inner
        # adapter-side I/O index: (world_type, world_id) -> WorldInstance NodeID.
        # This is the world↔graph mapping (an I/O concern), not agent state.
        self._instances: dict = {}
        self._concepts: dict = {}     # word -> Concept NodeID (taught-word index)
        self._seen: set = set()       # (world_type, key, value) triples perceived
        self._sensed_types: set = set()  # every world node type perceived
        self.last_freshening_count: int = 0  # instances that gained new info last ingest
        self._body_types: dict = {}   # world_type -> shared BodyType NodeID
        self._attributes: dict = {}   # (world_type, attr) -> Attribute NodeID
        self._attr_values: dict = {}  # (world_type, attr) -> set of values seen
        # discovery: activity log + co-occurrence counters (the bookkeeping the
        # seeded salience_predicate decides over). An event is (kind, types).
        self._activity: list = []          # list of (kind, tuple(types))
        self._kt_count: dict = {}          # (kind, type) -> count
        self._pair_count: dict = {}        # (fk, ft, tk, tt) -> lag-1 count
        self._n_events: int = 0
        self._discovered_relations: dict = {}  # rel_id -> metadata dict
        self._pair_to_rel: dict = {}       # pair key -> rel_id (dedup)
        self._rel_seq: int = 0
        self._meta_productions: set = set()  # rel_ids grown into Γ productions
        self._type_pair_count: dict = {}     # frozenset{type_a,type_b} -> co-occur count
        self._agent_world_to_rel: dict = {}  # (kind,type) -> rel_id (agent_to_body dedup)
        self._type_pair_to_rel: dict = {}    # frozenset pair -> rel_id (body_to_body dedup)
        # structural-triple discovery: (src_type, edge_type, tgt_type) -> count, the
        # mechanical analogue of CuriousAgent.triple_counts. Counts structural
        # edges between world nodes (incl. id-less ones, e.g. Conway cells) so a
        # recurrent typed structure can be reified into a Γ production by the same
        # seeded threshold policy. Pure observation bookkeeping; no decisions.
        self._triple_count: dict = {}        # (src_type, edge_type, tgt_type) -> count
        self._triple_to_rel: dict = {}       # triple key -> rel_id (dedup)
        self.current_goal_wi = None   # the single current-goal pointer
        self._action_frontier_ema: dict = {}  # action -> EMA of post-action freshening
        self._action_failure_ema: dict = {}
        self._action_boredom_ema: dict = {}
        self._action_stat_nodes: dict = {}    # action -> ActionStat NodeID (running sums)
        # per-(observed_type, action_kind) exploration counters (ActionTypeStat).
        self._action_type_stat_nodes: dict = {}  # (type_name, action_kind) -> NodeID
        self._storage_mmap = None             # long-term store handle (non-serialisable I/O)
        self._anticipation_windows: dict = {}  # name -> AnticipationWindow NodeID (F window)
        self.last_my_attrs_at_decision: dict = {}  # my_* snapshot at decision time
        self._resource_nodes: dict = {}            # my_* attr_name -> Resource NodeID
        self._last_observed_wi: set = set()        # instances in view at last observe
        self._event_clock: int = 0                 # monotone history timestamp
        self._policy_lits: dict = {}               # policy edge -> Term.Lit NodeID
        # theorem-discovery bookkeeping (mirrors CuriousAgent's hold-count map +
        # promoted set): consecutive-hold tally per candidate, the promoted set,
        # and a monotone thm_N identity counter.
        self._theorem_candidate_holds: dict = {}
        self._promoted_candidates: set = set()
        self._theorem_promotions: int = 0
        self._seed_scalar_policies(_DEFAULT_SCALAR_POLICIES)
        # map-planning I/O bookkeeping (locus + transition counts)
        self.current_locus_wi = None
        self.last_locus_wi = None
        self.current_intent_wi = None  # intended next-locus, checked post-action
        self.last_action_kind = None
        self.last_orientation: tuple = ()
        self._locus_transition_counts: dict = {}  # (locus, orient, action) -> {next: count}
        self._mirrored_edge_types: set = set()    # instance->instance edge set (BFS map)
        # vision I/O: the GraphEye cortex + its own kernel substrate, built lazily
        # (a world with no vision frame pays nothing). The receptive fields are
        # graph-resident Kernel nodes the agent introspects via the standard DSL.
        self._eye = None
        self._upload_eye = None          # static-upload cortex (separate from game eye)
        self._vision_substrate = None
        self._vision_projection: list = []   # one VisionPercept per azimuth (main graph)
        self._shape_nodes: list = []         # VisionPolygon nodes for the current frame
        self._motion_depth_nodes: list = []  # current generic RGB-motion depth observations
        self._vision_motion_nodes: list = []   # current 2-D retinal-motion projections
        self._vision_salience_nodes: list = [] # current 2-D residual-salience projections
        self._vision_held_residual_nodes: list = [] # current held-prediction residual sheet
        self._vision_foveal_exposure_nodes: list = [] # current dense fovea tensor
        self._vision_foveal_tile_nodes: list = [] # current predictive tile assessments
        self._vision_illumination_nodes: list = [] # current observed luminance evidence
        self._vision_photon_counts = None      # prior external count sheet (I/O diff)
        self._vision_layout_signature = None   # enacted optical geometry cache
        self._vision_peripheral_layout_signature = None
        self._vision_peripheral_layout = None
        self.n_games: int = 0                # game counter (driver bookkeeping)
        self._taught_lookup: dict = {}       # taught concept -> teacher's answer
        self._semiotic_definitions: dict = {}  # taught concept -> evaluable Term-JSON
        self._teacher_threads: list = []     # in-flight async self-teacher calls
        # Γ_meta core (the self-growing substrate) — graph-resident on self.s.
        self.gamma_root = None               # the Grammar node Γ_dynamic hangs off
        self.n_observations: int = 0         # agent-level observation tick counter
        self._gamma_meta_done: bool = False  # meta-grammar productions installed?
        self._gamma_attr_values: dict = {}   # (type, attr) -> set of observed values

    # --- vision: drive the GraphEye cortex, ingest percepts/shapes/attention ---

    def vision_substrate(self):
        """The vision-only substrate the cortex's Kernel nodes live on (or None
        before the cortex is built). Separate from the main substrate so vision
        types (Image/Kernel) don't collide with semantic types."""
        return self._vision_substrate

    def vision_kernels(self) -> dict:
        """Receptor-class -> photoreceptor NodeIDs (or {} before build).

        The deprecated RGBEye returns its fixed-kernel dictionary through the
        same compatibility surface."""
        return self._eye.kernels() if self._eye is not None else {}

    def stop_vision(self) -> None:
        """Stop autonomous visual substrates owned by this adapter."""
        for eye_name in ("_eye", "_upload_eye"):
            eye = getattr(self, eye_name, None)
            if eye is not None:
                eye.stop()
                setattr(self, eye_name, None)
        for node in self._vision_foveal_exposure_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_foveal_exposure_nodes.clear()
        for node in self._vision_foveal_tile_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_foveal_tile_nodes.clear()
        for node in self._vision_illumination_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_illumination_nodes.clear()
        self._vision_photon_counts = None
        self._vision_layout_signature = None
        self._vision_peripheral_layout_signature = None
        self._vision_peripheral_layout = None

    def close(self) -> None:
        """Idempotent runtime teardown: vision, native loop, host workers."""
        self.stop_vision()
        try:
            if self.s.agent_running():
                self.s.stop_agent()
        except Exception:
            pass
        self.stop_concurrency()

    def update_vision(self, screen=None, frame=None, calibration=None, *,
                      photon_packets=None, photon_dirty=None,
                      photon_counts=None, photon_epoch=None) -> None:
        """Hand the visual cortex the current frame and ingest whatever snapshot
        it has produced. Mechanical I/O only: GraphEye emits graph-native
        photon-transduction tasks; this builds it lazily, projects
        its per-azimuth percepts as VisionPercept nodes + its polygons as
        VisionPolygon nodes on the main substrate, and mirrors the salience
        pop-out onto the agent root as attention_* attrs. The agent's orienting
        DECISION (turn toward attention when salient) is a seeded Term that reads
        those attrs — not here.

        A world may instead publish an already-transduced 2-D photon sheet. That
        path is deliberately separate because the 2-D GraphEye has no 1-D
        ``latest()`` snapshot: its graph-native carve, motion, and salience
        products are read directly after settling the configured event window.
        ``photon_counts``/``photon_dirty`` are mechanical sensor reports used
        only by the optional exact dirty-index accelerator."""
        cal = calibration or {}
        if bool(cal.get("retina_2d", False)) and photon_packets is not None:
            self._update_vision_photon_sheet(
                photon_packets, cal, photon_dirty=photon_dirty,
                photon_counts=photon_counts, photon_epoch=photon_epoch)
            return
        if frame is None and screen is None:
            return
        if self._eye is None:
            import substrate_rs as _srs
            from domains.vision_graph import GraphEye
            scale = float(cal.get("depth_scale", 1.0))
            self.inner.set_attr(self.agent, "vision_clearance",
                                float(cal.get("wall_clearance", 0.0)))
            self._vision_substrate = _srs.Substrate()
            # Hand the eye the world's CONTEXT (modality + scale) so the same cortex
            # picks the right front-end — a discrete grid extracts colour components,
            # a camera traces luminance contours.
            self._eye = GraphEye(substrate=self._vision_substrate,
                                 depth_scale=scale, context=dict(cal)).build()
            from domains.vision_graph import PERCEPT
            self._vision_projection = [self.s.add_node(PERCEPT, {})
                                       for _ in range(self._eye.n_az)]
            for pid in self._vision_projection:
                self.inner.add_edge_unchecked(self.agent, "perceives", pid)
        posture = float(self.s.node(self.agent)["attrs"].get("my_angle", 0.0))
        self._eye.context.update(dict(calibration or {}))
        self._eye.submit(depth=frame, screen=screen, posture_deg=posture)
        self.inner.set_attr(
            self.agent, "vision_sensor_epoch", int(getattr(self._eye, "_epoch", 0)))
        snap = self._eye.latest()
        if snap is None:
            return                      # cortex hasn't produced a frame yet
        self.inner.set_attr(
            self.agent, "vision_settled_epoch", int(snap.get("sensor_epoch", 0)))
        for node in self._motion_depth_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._motion_depth_nodes = []
        for azimuth, depth in snap.get("motion_depths", []):
            node = self.s.add_node("MotionDepthObservation", {
                "azimuth": float(azimuth), "depth": float(depth),
                "sensor_epoch": int(snap.get("sensor_epoch", 0)),
            })
            self.inner.add_edge_unchecked(self.agent, "observed_motion_depth", node)
            self._motion_depth_nodes.append(node)
        percs = snap["percepts"]
        for i, pid in enumerate(self._vision_projection):
            if i >= len(percs):
                break
            for k, v in percs[i].items():
                self.inner.set_attr(pid, k, v)
        # Materialise detected shapes as VisionPolygon nodes (fresh each frame).
        from domains.vision_graph import POLYGON
        for sid in self._shape_nodes:
            self.inner.remove_node(sid)
        self._shape_nodes = []
        # LINK vision to the world. A perceived figure is bound to the WORLD THING
        # it depicts (the instance at its position) via ``depicts``/``seen_as``
        # edges. This is what makes the async eye usable: a decision about "the
        # things I can see / act on" reads through these links, so it has NO input
        # (cannot fire on nothing) until vision has actually linked a percept to a
        # world object — vision-dependence is structural, not a timing hack. Mapping
        # the eye's normalized coords back to cells needs the grid dims (hint).
        cal = calibration or {}
        _gs = cal.get("grid_shape")
        _pos_index = {}
        if _gs:
            for _inst in set(self._instances.values()):
                # the agent's own rules may del_node an ingested instance (e.g.
                # prune_consumed_changes drops spent ChangeEvents); skip a stale
                # cache entry rather than deref a deleted node.
                if not self.s.has_node(_inst):
                    continue
                _ia = self.s.node(_inst)["attrs"]
                _r, _c = _ia.get("row"), _ia.get("col")
                if _r is not None and _c is not None:
                    _pos_index[(int(_r), int(_c))] = _inst
        for poly in snap["polygons"]:
            _attrs = {
                "n_vertices": poly["n_vertices"], "area": poly["area"],
                "center_az": poly["center_az"],
                "cx_norm": poly.get("cx_norm", 0.5),
                "cy_norm": poly.get("cy_norm", 0.5),
                "bbox_norm": poly.get("bbox_norm", (0.0, 0.0, 1.0, 1.0))}
            # the eye's measured bbox in GRID cells — mechanical unit conversion
            # (normalized -> cells, the same translation as the cy_norm->cell
            # mapping below), so the agent's own cell_in_region concept can read a
            # figure's bounds. No grouping decision here; just the sensorium's
            # measurement in the agent's coordinate.
            if _gs:
                bx, by, bw, bh = poly.get("bbox_norm", (0.0, 0.0, 1.0, 1.0))
                _nr, _nc = int(_gs[0]), int(_gs[1])
                _attrs.update(minrow=int(by * _nr), mincol=int(bx * _nc),
                              maxrow=int((by + bh) * _nr),
                              maxcol=int((bx + bw) * _nc))
            sid = self.s.add_node(POLYGON, _attrs)
            self.inner.add_edge_unchecked(self.agent, "sees_shape", sid)
            self._shape_nodes.append(sid)
            # bind the percept to the world thing it depicts (nearest instance to
            # the figure's centroid, in cell coords).
            if _pos_index:
                nr, nc = int(_gs[0]), int(_gs[1])
                cr = int(poly.get("cy_norm", 0.5) * nr)
                cc = int(poly.get("cx_norm", 0.5) * nc)
                inst = _pos_index.get((cr, cc))
                if inst is None:
                    best, bestd = None, 1 << 30
                    for (r, c), n in _pos_index.items():
                        d = (r - cr) ** 2 + (c - cc) ** 2
                        if d < bestd:
                            bestd, best = d, n
                    inst = best
                if inst is not None:
                    self.inner.add_edge_unchecked(sid, "depicts", inst)
                    self.inner.add_edge_unchecked(inst, "seen_as", sid)
        # Mirror the bottom-up salience pop-out onto agent attrs (mechanical
        # reduction of cortex output; the orienting decision is seeded).
        best_sal, best_dir, best_az = 0.0, None, None
        fwd_sal, fwd_az = 0.0, 1e9
        sals = []
        for pid in self._vision_projection:
            pa = self.s.node(pid)["attrs"]
            sv = float(pa.get("salience", 0.0))
            sals.append(sv)
            if sv > best_sal:
                best_sal, best_dir, best_az = sv, pa.get("world_dir"), pa.get("gaze_az")
            az = abs(float(pa.get("gaze_az", 9.0)))
            if az < fwd_az:
                fwd_az, fwd_sal = az, sv
        if best_dir is not None:
            self.inner.set_attr(self.agent, "attention_x", float(best_dir[0]))
            self.inner.set_attr(self.agent, "attention_y", float(best_dir[1]))
        if best_az is not None:
            self.inner.set_attr(self.agent, "attention_az", float(best_az))
        med = sorted(sals)[len(sals) // 2] if sals else 0.0
        self.inner.set_attr(self.agent, "attention_salience",
                            best_sal / med if med > 1e-6 else 0.0)
        self.inner.set_attr(self.agent, "control_ahead",
                            fwd_sal / med if med > 1e-6 else 0.0)

    def apply_allocentric_retinal_prior(
            self, pose, *, source_epoch, world_view=None,
            cell_size=64.0) -> int:
        """Render a held graph world-view into the photon eye before sensing.

        This is a mechanical coordinate transform, not an inference policy.
        The generic path reads ``Agent -holds_world_view_cell->`` supports
        whose graph rules have admitted a unique transsaccadic photometric
        value. An optional legacy ``WorldInstance`` may also be supplied; only
        its explicit wall surfaces are renderable. Unknown space stays absent.
        The resulting expectation initializes ``HeldSurfaceCell`` state so
        ordinary photon residual rules compare bottom-up evidence with a
        top-down prediction on the next exposure.
        """
        if (self._eye is None
                or not bool(getattr(self._eye, "_retina_2d", False))):
            return 0
        px, py, pz, yaw_deg, pitch_deg = (
            float(pose[0]), float(pose[1]), float(pose[2]),
            float(pose[3]), float(pose[4]))
        cell_size = float(cell_size)
        supports = []
        illumination_epoch = int(self.s.node(
            self.agent)["attrs"].get("illumination_hypothesis_epoch", -1))
        for cell in self.inner.neighbours(
                self.agent, "holds_world_view_cell"):
            attrs = self.s.node(cell)["attrs"]
            # Absence is meaningful. The world-view graph, not this adapter,
            # decides whether an unambiguous photometric surface value exists.
            if attrs.get("surface_value") is None:
                continue
            render_value = float(attrs["surface_value"])
            render_confidence = float(attrs.get(
                "confidence", attrs.get("freshness", 0.0)))
            # Graph rules alone author the illumination-conditioned field.
            # This boundary merely renders the current admitted prediction;
            # the observed surface_value remains a separate, untouched fact.
            if (attrs.get("illumination_conditioned_value") is not None
                    and int(attrs.get(
                        "illumination_prediction_epoch", -2))
                    == illumination_epoch):
                render_value = float(
                    attrs["illumination_conditioned_value"])
                render_confidence = min(
                    render_confidence,
                    float(attrs.get(
                        "illumination_prediction_confidence",
                        render_confidence)))
            supports.append((
                float(attrs["world_x"]), float(attrs["world_y"]), pz,
                float(attrs.get("registration_uncertainty_world", 0.0)),
                render_value,
                render_confidence,
            ))

        # Compatibility with the earlier grid-held surface faculty. Free cells
        # are occupancy/visibility evidence, not visible supports: rendering
        # them would let the observer's walk cell occlude the whole scene.
        if (world_view is not None and self.s.has_node(world_view)
                and self.inner.has_edge(
                    self.agent, "holds_world_view", world_view)):
            for cell in self.inner.neighbours(world_view, "has_allo_cell"):
                attrs = self.s.node(cell)["attrs"]
                if int(attrs.get("geom", 0)) != 1:
                    continue
                coord = attrs.get("pose")
                if not isinstance(coord, (list, tuple)) or len(coord) < 2:
                    continue
                supports.append((
                    (float(coord[0]) + 0.5) * cell_size,
                    (float(coord[1]) + 0.5) * cell_size,
                    pz, 0.5 * cell_size,
                    float(attrs.get(
                        "value", attrs.get("stored", 0.0))),
                    float(attrs.get("freshness", 0.0)),
                ))

        self.inner.set_attr(
            self.agent, "top_down_prior_available_cells", len(supports))
        if not supports:
            self.inner.set_attr(
                self.agent, "top_down_prior_projected_receptors", 0)
            return 0

        projection = self._eye.project_allocentric_surfaces_2d(
            surface_x=[row[0] for row in supports],
            surface_y=[row[1] for row in supports],
            surface_z=[row[2] for row in supports],
            surface_radius=[row[3] for row in supports],
            surface_value=[row[4] for row in supports],
            surface_confidence=[row[5] for row in supports],
            pose_x=px, pose_y=py, pose_z=pz,
            pose_yaw=_math.radians(yaw_deg),
            pose_pitch=_math.radians(pitch_deg),
        )
        copied = self._eye.ingest_allocentric_prior_2d(
            projection["values"], projection["confidences"],
            projection["present"], source_epoch=int(source_epoch),
            source_indices=projection["source_indices"])
        self.inner.set_attr(
            self.agent, "top_down_prior_projected_receptors", copied)
        self.inner.set_attr(
            self.agent, "top_down_prior_source_epoch", int(source_epoch))
        return int(copied)

    def _update_vision_photon_sheet(
            self, photon_packets, calibration, *, photon_dirty=None,
            photon_counts=None, photon_epoch=None) -> None:
        """Drive and project an event-native 2-D photon receptor sheet.

        This is a mechanical boundary only: the external world supplies photon
        counts, GraphEye's native tasks/rules decide the carve/motion/salience
        products, and this method copies those products into the main graph. No
        frame, labels, depth oracle, object category, or control policy crosses
        this boundary.
        """
        cal = dict(calibration or {})
        # WorldAdapter owns the tick boundary, so its 2-D cortex is settled
        # synchronously here rather than racing an autonomous eye loop.
        cal.setdefault("synchronous", True)
        n_az = int(cal.get("retina_n_az", cal.get("n_az", 32)))
        n_el = int(cal.get("retina_n_el", cal.get("n_el", 12)))
        if n_az <= 0 or n_el <= 0:
            raise ValueError("2-D photon retina dimensions must be positive")
        if bool(cal.get("split_foveated_pathways", False)):
            (
                photon_packets, photon_counts, cal, n_az, n_el,
            ) = self._split_foveated_photon_sheet(
                photon_counts, cal, photon_epoch)
            # The external dirty report addresses the packed full sheet. The
            # exact periphery report is recomputed below in its local address.
            photon_dirty = None
        self.inner.set_attr(
            self.agent, "vision_clearance",
            float(cal.get("wall_clearance", 0.0)))

        if self._eye is None:
            import substrate_rs as _srs
            from domains.vision_graph import GraphEye

            self._vision_substrate = _srs.Substrate()
            self._eye = GraphEye(
                substrate=self._vision_substrate, n_az=n_az, n_el=n_el,
                fov_h_deg=float(cal.get("fov_h_deg", 90.0)),
                fov_v_deg=float(cal.get("fov_v_deg", 60.0)),
                depth_scale=float(cal.get("depth_scale", 1.0)),
                adapt_rate=float(cal.get("adapt_rate", 0.12)),
                context=cal).build()
            self._vision_layout_signature = self._receptor_layout_signature(cal)
        elif not bool(getattr(self._eye, "_retina_2d", False)):
            raise ValueError(
                "WorldAdapter vision cortex is already a 1-D eye; "
                "create a fresh adapter before switching to a 2-D photon sheet")
        elif self._eye.n_az != n_az or self._eye.n_el != n_el:
            raise ValueError(
                "2-D photon retina dimensions changed after cortex construction")

        self._eye.context.update(cal)
        layout_signature = self._receptor_layout_signature(cal)
        if (bool(getattr(self._eye, "_layout_explicit", False))
                and layout_signature != self._vision_layout_signature):
            # Mechanical enactment of the already-issued eye pose. The cache
            # avoids rewriting thousands of unchanged receptor attributes.
            self._eye.update_receptor_layout_2d(calibration=cal)
            self._vision_layout_signature = layout_signature
        # Mechanical efferent copy: retinal_focus_control on the MAIN graph
        # already chose or refused the focus.  This adapter does not derive an
        # active flag, rank a location, or retain a prior answer; it copies the
        # six published command scalars onto GraphEye's focus apparatus.
        agent_attrs = self.s.node(self.agent)["attrs"]
        self._eye.update_focus_window_2d(
            active=agent_attrs.get("retinal_focus_active", 0.0),
            center_col=agent_attrs.get("retinal_focus_column", -1),
            center_row=agent_attrs.get("retinal_focus_row", -1),
            half_width=agent_attrs.get(
                "retinal_focus_half_width",
                cal.get("retinal_focus_half_width", 2)),
            half_height=agent_attrs.get(
                "retinal_focus_half_height",
                cal.get("retinal_focus_half_height", 2)),
            source_epoch=agent_attrs.get("retinal_focus_source_epoch", -1),
        )
        # Predictive-coding feedback: after enacting the current receptor
        # geometry but before ingesting this exposure, render the persistent
        # graph world-view into held retinal state. The opt-in flag configures
        # an apparatus connection only; support admission, photometry, and
        # uncertainty were already decided by graph rules.
        if bool(cal.get("top_down_world_view", False)):
            prior_epoch = int(agent_attrs.get(
                "vision_settled_epoch", -1))
            if prior_epoch >= 0:
                self.apply_allocentric_retinal_prior(
                    (
                        float(cal.get("proprio_x_world", 0.0)),
                        float(cal.get("proprio_y_world", 0.0)),
                        float(cal.get("proprio_z_world", 0.0)),
                        float(cal.get("proprio_angle_deg", 0.0)),
                        0.0,
                    ),
                    source_epoch=prior_epoch)
        dirty = photon_dirty
        if photon_counts is not None:
            # Exact external count-sheet change report. This is sensor I/O
            # bookkeeping, not a salience judgement: every unequal count is
            # reported and no threshold/dead-band is applied.
            import numpy as _np

            counts = _np.asarray(photon_counts)
            if counts.size != n_az * n_el:
                raise ValueError(
                    "photon count sheet size does not match 2-D retina")
            counts = counts.reshape(n_el, n_az)
            if dirty is None:
                if self._vision_photon_counts is None:
                    dirty = list(range(counts.size))
                else:
                    dirty = _np.flatnonzero(
                        counts.reshape(-1)
                        != self._vision_photon_counts.reshape(-1)).tolist()
            self._vision_photon_counts = counts.copy()

        self._eye.submit_photons_2d(
            photon_packets, dirty=dirty, sensor_epoch=photon_epoch)
        eye_inner = self._eye.substrate._inner
        eye_inner.run_cognitive_tasks(1)
        eye_inner.run_rules()

        settled_epoch = int(getattr(self._eye, "_epoch", 0))
        window = max(1, int(cal.get(
            "event_window_epochs", cal.get("event_window", 1))))
        since_epoch = max(1, settled_epoch - window + 1)
        self._eye.settle_carve_2d(since_epoch=since_epoch)
        self._eye.settle_motion_2d(since_epoch=since_epoch)
        self._eye.settle_salience_2d(since_epoch=since_epoch)
        eye_inner.run_cognitive_tasks(1)
        eye_inner.run_rules()

        polygons = [
            p for p in self._eye.carve_polygons_2d()
            if int(p.get("epoch", 0)) == settled_epoch
        ]
        motions = [
            p for p in self._eye.motion_percepts_2d()
            if int(p.get("epoch", 0)) == settled_epoch
        ]
        saliences = [
            p for p in self._eye.salience_percepts_2d()
            if int(p.get("epoch", 0)) == settled_epoch
        ]
        held_residuals = self._eye.held_prediction_residuals_2d()
        self._eye.prune_settled_tasks()
        # The main graph receives copies below; keep the vision work graph at a
        # bounded event window instead of retaining stale transient emissions.
        for type_name in (
                "VisionPolygon", "RetinalMotionPercept", "RetinalSalience"):
            for node in list(self._eye.substrate.nodes(type_name)):
                self._eye.substrate.remove_node(node)
        keep_since = max(1, settled_epoch - window + 2)
        for node in list(self._eye.substrate.nodes("RetinalOnsetEvent")):
            attrs = self._eye.substrate.node(node)["attrs"]
            if int(attrs.get("epoch", 0)) < keep_since:
                self._eye.substrate.remove_node(node)

        self.inner.set_attr(self.agent, "vision_sensor_epoch", settled_epoch)
        self.inner.set_attr(self.agent, "vision_settled_epoch", settled_epoch)
        if photon_epoch is not None:
            self.inner.set_attr(
                self.agent, "vision_source_epoch", int(photon_epoch))
        # Mechanical proprioceptive/efferent calibration accompanying this
        # photon exposure.  Units remain explicit because event slopes use the
        # source epoch, whose clock can jump when a latest-only world queue
        # drops frames.  The spatial-grounding graph, not this boundary, decides
        # whether the evidence is rigid/coherent enough to admit.
        source_delta = max(1, int(cal.get("source_epoch_delta", 1)))
        translation = float(cal.get("efference_translation", 0.0))
        rotation = float(cal.get("efference_rotation_deg", 0.0))
        for key, value in (
                ("optic_source_epoch_delta", source_delta),
                ("optic_translation_world", translation),
                ("optic_translation_world_per_source_epoch",
                 float(cal.get(
                     "efference_translation_per_source_epoch",
                     translation / source_delta))),
                ("optic_rotation_deg", rotation),
                ("optic_rotation_deg_per_source_epoch",
                 float(cal.get(
                     "efference_rotation_deg_per_source_epoch",
                     rotation / source_delta))),
                ("optic_pose_x_world",
                 float(cal.get("proprio_x_world", 0.0))),
                ("optic_pose_y_world",
                 float(cal.get("proprio_y_world", 0.0))),
                ("optic_pose_angle_deg",
                 float(cal.get("proprio_angle_deg", 0.0))),
                ("optic_focal_cells",
                 float(cal.get("retina_focal_cells", 0.0)))):
            self.inner.set_attr(self.agent, key, value)
        self._project_photon_sheet_outputs(
            polygons, motions, saliences, held_residuals,
            settled_epoch, n_az, n_el)

    @staticmethod
    def _receptor_layout_signature(calibration) -> tuple:
        """Opaque optical-apparatus cache key; no perceptual decision."""
        cal = calibration or {}
        explicit = cal.get("receptor_layout")
        if explicit is None:
            explicit_signature = None
        else:
            explicit_signature = tuple(
                (
                    int(record["cell_index"]),
                    float(record["gaze_az"]), float(record["gaze_el"]),
                    float(record["angular_width"]),
                    float(record["angular_height"]),
                    str(record["eye_id"]), str(record["pathway"]),
                    tuple(int(i) for i in record["adjacent"]),
                )
                for record in explicit
            )
        return (*tuple(cal.get(key) for key in (
            "retinal_layout", "eye_id", "gaze_az_deg", "gaze_el_deg",
            "periphery_gaze_az_deg", "periphery_gaze_el_deg",
            "event_pathway",
            "fovea_width", "fovea_height", "peripheral_rings",
            "peripheral_spokes", "fovea_fov_fraction",
            "fovea_fov_h_deg", "fovea_fov_v_deg",
            "source_width", "source_height", "fov_h_deg", "fov_v_deg",
        )), explicit_signature)

    def _split_foveated_photon_sheet(
            self, photon_counts, calibration, photon_epoch):
        """Split one packed exposure into a dense tensor and coarse graph eye.

        The dense fovea remains graph-resident as one `FovealExposure` value
        tensor, avoiding thousands of per-pixel graph nodes. The transient
        log-polar scout retains ordinary RetinalColumn nodes and therefore
        drives the existing motion/salience/saccade graph unchanged.
        """
        if photon_counts is None:
            raise ValueError(
                "split foveated pathways require the compact photon count sheet")
        import numpy as _np
        from domains import doom_photon_world as _dpw
        from domains.photon_eye import receptor_layout_from_calibration

        cal = dict(calibration)
        full_n_az = int(cal.get("retina_n_az", cal.get("n_az", 0)))
        full_n_el = int(cal.get("retina_n_el", cal.get("n_el", 0)))
        counts = _np.asarray(photon_counts).reshape(full_n_el, full_n_az)
        fovea_w = int(cal.get("fovea_width", 0))
        fovea_h = int(cal.get("fovea_height", 0))
        fovea_n = fovea_w * fovea_h
        remaining = counts.size - fovea_n
        if (fovea_w != full_n_az or fovea_h <= 0 or remaining <= 0
                or remaining % full_n_az):
            raise ValueError(
                "split foveated sheet requires a full-width dense fovea "
                "followed by whole packed peripheral rows")

        # One current dense exposure node: graph data, but not 6,912 graph
        # objects. The Rust batch-net path can consume tiled rows from this
        # tensor without turning pixels into host-side cognition.
        for node in self._vision_foveal_exposure_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_foveal_exposure_nodes.clear()
        for node in self._vision_foveal_tile_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_foveal_tile_nodes.clear()
        fovea = counts.reshape(-1)[:fovea_n].reshape(fovea_h, fovea_w)
        exposure = self.s.add_node("FovealExposure", {
            "source_epoch": int(photon_epoch or 0),
            "width": fovea_w,
            "height": fovea_h,
            "source_width": int(cal.get("source_width", 0)),
            "source_height": int(cal.get("source_height", 0)),
            "gaze_az_deg": float(cal.get("gaze_az_deg", 0.0)),
            "gaze_el_deg": float(cal.get("gaze_el_deg", 0.0)),
            "eye_id": str(cal.get("eye_id", "cyclopean")),
            "unit": "photon_count_quanta",
            "native_pixel_sampling": 1.0,
            "settled_count": 0,
            "values": fovea.reshape(-1).astype(_np.int64).tolist(),
        })
        self.inner.add_edge_unchecked(
            self.agent, "has_foveal_exposure", exposure)
        self._vision_foveal_exposure_nodes.append(exposure)
        self._ingest_predictive_fovea(
            exposure, fovea, cal, photon_epoch)

        # The peripheral layout is independent of foveal gaze. Construct and
        # remap it once; subsequent saccades update only FovealExposure.
        periphery_signature = tuple(cal.get(key) for key in (
            "retinal_layout", "eye_id",
            "periphery_gaze_az_deg", "periphery_gaze_el_deg",
            "fovea_width", "fovea_height",
            "peripheral_rings", "peripheral_spokes",
            "fovea_fov_fraction", "fovea_fov_h_deg", "fovea_fov_v_deg",
            "source_width", "source_height", "fov_h_deg", "fov_v_deg",
        ))
        if periphery_signature != self._vision_peripheral_layout_signature:
            layout_cal = dict(cal)
            layout_cal["gaze_az_deg"] = 0.0
            layout_cal["gaze_el_deg"] = 0.0
            full_layout = receptor_layout_from_calibration(
                layout_cal, full_n_az, full_n_el)
            peripheral = []
            for local, source in enumerate(full_layout[fovea_n:]):
                record = dict(source)
                row, col = divmod(local, full_n_az)
                record.update({
                    "cell_index": local, "row": row, "col": col,
                    "adjacent": [
                        int(other) - fovea_n
                        for other in source["adjacent"]
                        if int(other) >= fovea_n
                    ],
                })
                peripheral.append(record)
            self._vision_peripheral_layout = peripheral
            self._vision_peripheral_layout_signature = periphery_signature

        peripheral_n_el = remaining // full_n_az
        peripheral_counts = counts.reshape(-1)[fovea_n:].reshape(
            peripheral_n_el, full_n_az)
        self._ingest_visual_illumination_evidence(
            fovea, peripheral_counts, photon_epoch)
        eye_cal = dict(cal)
        eye_cal.update({
            "retina_n_az": full_n_az,
            "retina_n_el": peripheral_n_el,
            "retina_w": full_n_az,
            "retina_h": peripheral_n_el,
            "receptor_layout": self._vision_peripheral_layout,
            "retinal_layout": "log_polar_periphery",
            "event_pathway": "all",
            "gaze_az_deg": float(cal.get("periphery_gaze_az_deg", 0.0)),
            "gaze_el_deg": float(cal.get("periphery_gaze_el_deg", 0.0)),
        })
        return (
            _dpw.packets_from_counts(peripheral_counts),
            peripheral_counts,
            eye_cal,
            full_n_az,
            peripheral_n_el,
        )

    def _ingest_visual_illumination_evidence(
            self, fovea, peripheral_counts, photon_epoch) -> None:
        """Publish the split eye's two physical luminance measurements.

        This boundary performs only sensor reduction: the dense fovea and the
        broad, sparse scout each become one observed evidence node. Whether
        their changes share a global cause, and how that cause should alter
        predictions, is decided by ``global_illumination_eye`` graph rules.
        """
        params = list(self.inner.neighbours(
            self.agent, "has_global_illumination_params"))
        if len(params) != 1:
            return
        params_attrs = self.s.node(params[0])["attrs"]
        if float(params_attrs.get("enabled", 0.0)) != 1.0:
            return

        import numpy as _np

        for node in self._vision_illumination_nodes:
            if self.s.has_node(node):
                self.inner.remove_node(node)
        self._vision_illumination_nodes.clear()

        source_epoch = int(photon_epoch or 0)
        foveal = _np.asarray(fovea, dtype=_np.float64).reshape(-1)
        global_scout = _np.asarray(
            peripheral_counts, dtype=_np.float64).reshape(-1)

        # Confidence is a bounded shot-noise proxy derived solely from the
        # number of observed photon quanta. It is measurement metadata, not a
        # judgment about the cause of the brightness change.
        def _measurement(values):
            sample_count = int(values.size)
            mean_quanta = float(values.mean()) if sample_count else 0.0
            total_quanta = float(values.sum()) if sample_count else 0.0
            confidence = (
                total_quanta / (total_quanta + float(sample_count))
                if sample_count else 0.0)
            return mean_quanta, confidence, sample_count

        foveal_mean, foveal_confidence, foveal_count = _measurement(foveal)
        global_mean, global_confidence, global_count = _measurement(
            global_scout)
        exposure = self.s.add_node("VisualIlluminationExposure", {
            "source_epoch": source_epoch,
            "status": "raw",
            "unit": "photon_count_quanta",
            "provenance_kind": "observed",
        })
        foveal_evidence = self.s.add_node("FovealLuminanceEvidence", {
            "source_epoch": source_epoch,
            "mean_quanta": foveal_mean,
            "confidence": foveal_confidence,
            "sample_count": foveal_count,
            "pathway": "dense_high_acuity_fovea",
            "field_scope": "fixated_aperture",
            "unit": "photon_count_quanta",
            "provenance_kind": "observed",
        })
        global_evidence = self.s.add_node("GlobalLuminanceEvidence", {
            "source_epoch": source_epoch,
            "mean_quanta": global_mean,
            "confidence": global_confidence,
            "sample_count": global_count,
            "pathway": "sparse_broad_field_scout",
            "field_scope": "whole_visual_field",
            "unit": "photon_count_quanta",
            "provenance_kind": "observed",
        })
        self.inner.add_edge_unchecked(
            self.agent, "has_visual_illumination_exposure", exposure)
        self.inner.add_edge_unchecked(
            exposure, "has_foveal_luminance_evidence", foveal_evidence)
        self.inner.add_edge_unchecked(
            exposure, "has_global_luminance_evidence", global_evidence)
        self._vision_illumination_nodes.extend(
            (exposure, foveal_evidence, global_evidence))

    def _foveal_predictive_apparatus(self):
        """Resolve the opt-in graph apparatus for the dense foveal pathway.

        This is a mechanical connection lookup. The graph's enabled parameter
        decides whether the apparatus is connected; all learned state remains
        in its WeightTensor and AllocentricWorldViewCell nodes.
        """
        params = list(self.inner.neighbours(
            self.agent, "has_foveal_predictive_params"))
        if len(params) != 1:
            return None
        params_node = params[0]
        attrs = self.s.node(params_node)["attrs"]
        if float(attrs.get("enabled", 0.0)) != 1.0:
            return None
        encoders = [
            node for node in self.s.nodes("NetworkAssemblage")
            if self.s.node(node)["attrs"].get("apparatus_role")
            == "foveal_tile_encoder"
        ]
        decoders = [
            node for node in self.s.nodes("ReflexNet")
            if self.s.node(node)["attrs"].get("name")
            == "foveal_predictive_decoder"
        ]
        if len(encoders) != 1 or len(decoders) != 1:
            return None
        decoder_assemblages = list(self.inner.neighbours(
            decoders[0], "net_assemblage"))
        if len(decoder_assemblages) != 1:
            return None
        return (
            params_node, attrs, encoders[0], decoders[0],
            decoder_assemblages[0])

    def _project_foveal_tile_sources(
            self, calibration, tile_rows, tile_cols, tile_height,
            tile_width):
        """Project graph-held world supports onto dense tile apertures.

        The compiled allocentric projection performs occlusion and association;
        this boundary only supplies the physical foveal receptor geometry.
        Returned cell identities are graph NodeIDs in projection order.
        """
        supports = []
        cells = []
        for cell in self.inner.neighbours(
                self.agent, "holds_world_view_cell"):
            attrs = self.s.node(cell)["attrs"]
            if attrs.get("world_x") is None or attrs.get("world_y") is None:
                continue
            cells.append(cell)
            supports.append((
                float(attrs["world_x"]),
                float(attrs["world_y"]),
                float(calibration.get("proprio_z_world", 0.0)),
                float(attrs.get("registration_uncertainty_world", 0.0)),
                float(attrs.get("surface_value", 0.0)),
                float(attrs.get(
                    "confidence", attrs.get("freshness", 0.0))),
            ))
        tile_count = int(tile_rows) * int(tile_cols)
        if not supports:
            return ([-1] * tile_count, [0.0] * tile_count, cells)

        fovea_width = int(tile_cols) * int(tile_width)
        fovea_height = int(tile_rows) * int(tile_height)
        fov_h_deg = float(calibration.get("fov_h_deg", 90.0))
        fov_v_deg = float(calibration.get("fov_v_deg", 60.0))
        source_width = int(calibration.get("source_width", 0))
        source_height = int(calibration.get("source_height", 0))
        fraction = min(
            0.8, max(0.02, float(
                calibration.get("fovea_fov_fraction", 0.18))))
        fovea_h_deg = float(calibration.get(
            "fovea_fov_h_deg",
            fov_h_deg * fovea_width / source_width
            if source_width > 0 else fov_h_deg * fraction))
        fovea_v_deg = float(calibration.get(
            "fovea_fov_v_deg",
            fov_v_deg * fovea_height / source_height
            if source_height > 0 else fov_v_deg * fraction))
        fovea_h = _math.radians(fovea_h_deg)
        fovea_v = _math.radians(fovea_v_deg)
        fixation_az = _math.radians(float(
            calibration.get("gaze_az_deg", 0.0)))
        fixation_el = _math.radians(float(
            calibration.get("gaze_el_deg", 0.0)))
        receptor_az = []
        receptor_el = []
        for row in range(int(tile_rows)):
            for col in range(int(tile_cols)):
                receptor_az.append(
                    fixation_az
                    + fovea_h * ((col + 0.5) / tile_cols - 0.5))
                receptor_el.append(
                    fixation_el
                    + fovea_v * ((row + 0.5) / tile_rows - 0.5))

        from substrate_rs import _native

        _values, confidences, _present, source_indices = (
            _native.allocentric_retinal_projection(
                [row[0] for row in supports],
                [row[1] for row in supports],
                [row[2] for row in supports],
                [row[3] for row in supports],
                [row[4] for row in supports],
                [row[5] for row in supports],
                float(calibration.get("proprio_x_world", 0.0)),
                float(calibration.get("proprio_y_world", 0.0)),
                float(calibration.get("proprio_z_world", 0.0)),
                _math.radians(float(
                    calibration.get("proprio_angle_deg", 0.0))),
                0.0,
                receptor_az,
                receptor_el,
                [fovea_h / tile_cols] * tile_count,
                [fovea_v / tile_rows] * tile_count,
            ))
        return (
            [int(value) for value in source_indices],
            [float(value) for value in confidences],
            cells)

    def _ingest_predictive_fovea(
            self, exposure, fovea, calibration, photon_epoch):
        """Translate one dense exposure into graph-native prediction evidence.

        Tensor tiling, batch-net calls, coordinate projection, and error
        measurement are optical I/O. The graph rules in
        ``foveal_predictive_coding`` alone select tiles, persist latents, and
        authorize the decoder's local-collapse learning step.
        """
        apparatus = self._foveal_predictive_apparatus()
        if apparatus is None:
            return
        params_node, params, encoder, decoder, decoder_asm = apparatus
        tile_width = int(params.get("tile_width", 0))
        tile_height = int(params.get("tile_height", 0))
        latent_dim = int(params.get("latent_dim", 0))
        scale = float(params.get("photon_scale", 0.0))
        height, width = int(fovea.shape[0]), int(fovea.shape[1])
        if (tile_width <= 0 or tile_height <= 0 or latent_dim <= 0
                or scale <= 0.0 or width % tile_width
                or height % tile_height):
            self.inner.set_attr(
                params_node, "apparatus_status",
                "incompatible_foveal_tensor_shape")
            return

        import numpy as _np

        tile_rows = height // tile_height
        tile_cols = width // tile_width
        patches = (
            _np.asarray(fovea, dtype=_np.float64)
            .reshape(tile_rows, tile_height, tile_cols, tile_width)
            .transpose(0, 2, 1, 3)
            .reshape(tile_rows * tile_cols, tile_height * tile_width)
            / scale)
        encoder_id = (
            encoder.value if hasattr(encoder, "value") else int(encoder))
        decoder_id = (
            decoder_asm.value
            if hasattr(decoder_asm, "value") else int(decoder_asm))
        latents = _np.asarray(
            self.inner.net_forward_batch(encoder_id, patches.tolist()),
            dtype=_np.float64)
        if latents.shape != (len(patches), latent_dim):
            self.inner.set_attr(
                params_node, "apparatus_status",
                "encoder_shape_mismatch")
            return

        source_indices, source_confidence, world_cells = (
            self._project_foveal_tile_sources(
                calibration, tile_rows, tile_cols,
                tile_height, tile_width))
        prior_rows = []
        prior_tile_indices = []
        for tile_index, source_index in enumerate(source_indices):
            if source_index < 0 or source_index >= len(world_cells):
                continue
            cell_attrs = self.s.node(
                world_cells[source_index])["attrs"]
            latent = cell_attrs.get("foveal_latent")
            if (not isinstance(latent, (list, tuple))
                    or len(latent) != latent_dim):
                continue
            prior_rows.append([float(value) for value in latent])
            prior_tile_indices.append(tile_index)

        predictions = {}
        if prior_rows:
            decoded = self.inner.net_forward_batch(decoder_id, prior_rows)
            for tile_index, prediction in zip(
                    prior_tile_indices, decoded):
                if len(prediction) != tile_width * tile_height:
                    continue
                predictions[tile_index] = _np.clip(
                    _np.asarray(prediction, dtype=_np.float64),
                    0.0, 1.0)

        predicted_values = _np.zeros_like(
            _np.asarray(fovea, dtype=_np.float64))
        predicted_present = _np.zeros((tile_rows, tile_cols), dtype=_np.bool_)
        residuals = []
        grounded = 0
        source_epoch = int(photon_epoch or 0)
        for tile_index, patch in enumerate(patches):
            tile_row, tile_col = divmod(tile_index, tile_cols)
            attrs = {
                "status": "raw",
                "source_epoch": source_epoch,
                "tile_index": tile_index,
                "tile_row": tile_row,
                "tile_col": tile_col,
                "tile_width": tile_width,
                "tile_height": tile_height,
                "latent": latents[tile_index].tolist(),
                "input_vec": latents[tile_index].tolist(),
                "target": patch.tolist(),
                "information_mass": float(_np.var(patch)),
                "prediction_present": (
                    1.0 if tile_index in predictions else 0.0),
                "world_grounded": 0.0,
                "world_confidence": 0.0,
                "residual_unit": "normalized_photon_mse",
            }
            prediction = predictions.get(tile_index)
            if prediction is not None:
                residual = float(_np.mean(
                    (patch - prediction) * (patch - prediction)))
                attrs["predicted_residual"] = residual
                attrs["predicted_patch"] = prediction.tolist()
                residuals.append(residual)
                predicted_present[tile_row, tile_col] = True
                r0, c0 = tile_row * tile_height, tile_col * tile_width
                predicted_values[
                    r0:r0 + tile_height,
                    c0:c0 + tile_width] = prediction.reshape(
                        tile_height, tile_width) * scale
            source_index = source_indices[tile_index]
            cell = None
            if 0 <= source_index < len(world_cells):
                cell = world_cells[source_index]
                attrs["world_grounded"] = 1.0
                attrs["world_confidence"] = source_confidence[tile_index]
                grounded += 1

            assessment = self.s.add_node(
                "FovealTileAssessment", attrs)
            self.inner.add_edge_unchecked(
                exposure, "has_foveal_tile_assessment", assessment)
            self.inner.add_edge_unchecked(
                assessment, "observes", decoder)
            if cell is not None:
                self.inner.add_edge_unchecked(
                    assessment, "grounds_in_world_view", cell)
            self._vision_foveal_tile_nodes.append(assessment)

        self.inner.set_attr(
            exposure, "tile_rows", tile_rows)
        self.inner.set_attr(
            exposure, "tile_cols", tile_cols)
        self.inner.set_attr(
            exposure, "predicted_values",
            predicted_values.reshape(-1).tolist())
        self.inner.set_attr(
            exposure, "predicted_present_tiles",
            predicted_present.reshape(-1).tolist())
        self.inner.set_attr(
            exposure, "predicted_tile_count",
            int(predicted_present.sum()))
        self.inner.set_attr(
            exposure, "grounded_tile_count", grounded)
        self.inner.set_attr(
            self.agent, "foveal_prediction_tile_count",
            int(predicted_present.sum()))
        self.inner.set_attr(
            self.agent, "foveal_grounded_tile_count", grounded)
        self.inner.set_attr(
            self.agent, "foveal_max_predicted_residual",
            max(residuals) if residuals else 0.0)
        self.inner.set_attr(
            params_node, "apparatus_status", "connected")

    def _project_photon_sheet_outputs(
            self, polygons, motions, saliences, held_residuals,
            sensor_epoch, n_az, n_el) -> None:
        """Mechanically copy current 2-D eye products onto the main substrate."""
        from domains.vision_graph import POLYGON

        for nodes in (self._shape_nodes, self._vision_motion_nodes,
                      self._vision_salience_nodes,
                      self._vision_held_residual_nodes):
            for node in nodes:
                if self.s.has_node(node):
                    self.inner.remove_node(node)
            nodes.clear()

        for poly in polygons:
            col_min, col_max = int(poly["col_min"]), int(poly["col_max"])
            row_min, row_max = int(poly["row_min"]), int(poly["row_max"])
            attrs = dict(poly)
            attrs.update({
                "mincol": col_min, "maxcol": col_max,
                "minrow": row_min, "maxrow": row_max,
                "sensor_epoch": int(sensor_epoch),
            })
            node = self.s.add_node(POLYGON, attrs)
            self.inner.add_edge_unchecked(self.agent, "sees_shape", node)
            self._shape_nodes.append(node)

        for motion in motions:
            attrs = dict(motion)
            attrs["sensor_epoch"] = int(sensor_epoch)
            node = self.s.add_node("RetinalMotionPercept", attrs)
            self.inner.add_edge_unchecked(
                self.agent, "perceives_motion", node)
            self._vision_motion_nodes.append(node)

        for salience in saliences:
            attrs = dict(salience)
            col = int(attrs["column_index"])
            row = int(attrs["row_index"])
            attrs.update({
                "n_az": int(n_az), "n_el": int(n_el),
                "gaze_az": float(attrs.get(
                    "gaze_az", self._eye._cell_gaze(col, row)[0])),
                "gaze_el": float(attrs.get(
                    "gaze_el", self._eye._cell_gaze(col, row)[1])),
                "sensor_epoch": int(sensor_epoch),
            })
            node = self.s.add_node("RetinalSalience", attrs)
            self.inner.add_edge_unchecked(
                self.agent, "perceives_salience", node)
            self._vision_salience_nodes.append(node)

        # Preserve the predictor's distinct physical contract.  These are
        # photon-count/luminance quanta, not retinal-motion cells/epoch.  Every
        # held cell crosses the mechanical boundary; graph rules decide which,
        # if any, deserves attention.
        for residual in held_residuals:
            attrs = dict(residual)
            col = int(attrs["column_index"])
            row = int(attrs["row_index"])
            attrs.update({
                "n_az": int(n_az), "n_el": int(n_el),
                "gaze_az": float(attrs.get(
                    "gaze_az", self._eye._cell_gaze(col, row)[0])),
                "gaze_el": float(attrs.get(
                    "gaze_el", self._eye._cell_gaze(col, row)[1])),
                "sensor_epoch": int(sensor_epoch),
                "residual_unit": "photon_count_quanta",
            })
            node = self.s.add_node("HeldPredictionResidual", attrs)
            self.inner.add_edge_unchecked(
                self.agent, "perceives_prediction_residual", node)
            self._vision_held_residual_nodes.append(node)

        self.inner.set_attr(
            self.agent, "vision_polygon_count", len(self._shape_nodes))
        self.inner.set_attr(
            self.agent, "vision_motion_count", len(self._vision_motion_nodes))
        self.inner.set_attr(
            self.agent, "vision_salience_count", len(self._vision_salience_nodes))
        self.inner.set_attr(
            self.agent, "vision_prediction_residual_count",
            len(self._vision_held_residual_nodes))

    def perceive_upload_image(self, arr, doc_id, *, replace: bool = False) -> list:
        """Run GraphEye on a static upload with foveated fixations and bind
        detected shapes to the UploadedDocument. Mechanical I/O only."""
        import time

        import numpy as np

        from domains.vision_graph import POLYGON

        if arr is None or not self.inner.has_node(doc_id):
            return []
        if replace:
            self._clear_upload_shapes(doc_id)
        h, w = int(arr.shape[0]), int(arr.shape[1])
        self.inner.set_attr(doc_id, "vision_native_height", float(h))
        self.inner.set_attr(doc_id, "vision_native_width", float(w))
        modality = self._upload_vision_modality(arr)
        frames = (
            [{"name": "full", "arr": arr, "offset": (0, 0), "scale": (1.0, 1.0)}]
            if modality == "grid"
            else self._upload_foveation_frames(arr)
        )
        out = []
        seen = set()
        for frame in frames:
            sub = frame["arr"]
            fh, fw = int(sub.shape[0]), int(sub.shape[1])
            eye = self._ensure_upload_eye(modality, fh, fw)
            before = eye.processed_count()
            eye.submit(screen=sub, posture_deg=0.0)
            deadline = time.perf_counter() + 3.0
            while eye.processed_count() <= before and time.perf_counter() < deadline:
                time.sleep(0.005)
            snap = eye.latest() or {"polygons": []}
            ox, oy = frame["offset"]
            sx, sy = frame["scale"]
            for poly in snap.get("polygons", []):
                area = float(poly.get("area", 0))
                cx_n = poly.get("cx_norm")
                cy_n = poly.get("cy_norm")
                if cx_n is not None and cy_n is not None:
                    cx = (float(cx_n) * fw + ox) * sx
                    cy = (float(cy_n) * fh + oy) * sy
                    key = (frame["name"], int(area), int(cx), int(cy))
                else:
                    cx = cy = 0.0
                    key = (frame["name"], int(area), int(poly.get("center_az", 0)))
                if key in seen:
                    continue
                seen.add(key)
                _attrs = {
                    "n_vertices": poly["n_vertices"], "area": area,
                    "center_az": poly["center_az"],
                    "fixation": frame["name"],
                    "native_cx": cx, "native_cy": cy,
                }
                if poly.get("cx_norm") is not None:
                    _attrs["cx_norm"] = poly["cx_norm"]
                    _attrs["cy_norm"] = poly["cy_norm"]
                    _attrs["bbox_norm"] = poly.get("bbox_norm", (0.0, 0.0, 1.0, 1.0))
                sid = self.s.add_node(POLYGON, _attrs)
                self.inner.add_edge_unchecked(doc_id, "has_shape", sid)
                self.inner.add_edge_unchecked(sid, "depicts", doc_id)
                self.inner.add_edge_unchecked(self.agent, "sees_shape", sid)
                out.append(sid)
        self.inner.set_attr(doc_id, "vision_fixation_count", float(len(frames)))
        self.inner.set_attr(doc_id, "vision_modality", modality)
        import json as _json
        _crops = [
            {"name": f["name"], "x0": int(f["offset"][0]), "y0": int(f["offset"][1]),
             "w": int(f["arr"].shape[1]), "h": int(f["arr"].shape[0])}
            for f in frames
            if str(f.get("name") or "") in ("center_fovea", "upper_fovea", "lower_fovea")
        ]
        if _crops:
            self.inner.set_attr(doc_id, "foveation_crops", _json.dumps(_crops))
        if not out and modality == "camera":
            out = self._perceive_upload_colour_regions(arr, doc_id, seen)
        self._write_upload_vision_summary(arr, doc_id, out, frames)
        if not out:
            self.inner.set_attr(doc_id, "vision_shape_count", 0.0)
        return out

    def _perceive_upload_colour_regions(self, arr, doc_id, seen: set) -> list:
        """Second pass: quantised colour components when edge contours find nothing."""
        import numpy as np

        from domains.vision_graph import RGBEye, POLYGON

        h, w = arr.shape[:2]
        qarr = (np.asarray(arr)[..., :3] // 32) * 32
        eye = RGBEye(substrate=None, n_az=8, context={"modality": "grid", "cell_px": 1},
                       min_area=max(40.0, h * w * 0.002)).build()
        eye.stop()
        snap = eye._process_frame(None, np.asarray(qarr, dtype=np.uint8), 0.0)
        out = []
        polys = sorted(snap.get("polygons", []), key=lambda p: -p.get("area", 0))[:8]
        for poly in polys:
            area = float(poly.get("area", 0))
            key = ("colour_regions", int(area))
            if key in seen:
                continue
            seen.add(key)
            sid = self.s.add_node(POLYGON, {
                "n_vertices": poly["n_vertices"], "area": area,
                "center_az": poly["center_az"], "fixation": "colour_regions",
                "cx_norm": poly.get("cx_norm", 0.5),
                "cy_norm": poly.get("cy_norm", 0.5),
            })
            self.inner.add_edge_unchecked(doc_id, "has_shape", sid)
            self.inner.add_edge_unchecked(sid, "depicts", doc_id)
            self.inner.add_edge_unchecked(self.agent, "sees_shape", sid)
            out.append(sid)
        return out

    def refresh_upload_vision_if_needed(self, doc_id) -> None:
        """Re-run upload vision from the stored Image node when a follow-up
        arrives but ingest found no shapes — mechanical I/O only."""
        if not self.inner.has_node(doc_id):
            return
        da = self.s.node(doc_id)["attrs"]
        if da.get("kind") != "image":
            return
        if float(da.get("vision_shape_count") or 0) > 0:
            return
        for iid in self.inner.neighbours(doc_id, "has_image"):
            if not self.inner.has_node(iid):
                continue
            try:
                from substrate_rs import vision as _vision
                arr = _vision.image_to_array(self.inner, iid)
                self.perceive_upload_image(arr, doc_id, replace=True)
            except Exception:  # noqa: BLE001
                pass
            break

    def _clear_upload_shapes(self, doc_id) -> None:
        for sid in list(self.inner.neighbours(doc_id, "has_shape")):
            if self.inner.has_node(sid):
                self.inner.remove_node(sid)

    @staticmethod
    def _upload_vision_modality(arr) -> str:
        """Mechanical pick: flat few-colour tiles -> grid; photos -> camera."""
        import numpy as np

        h, w = arr.shape[:2]
        flat = arr.reshape(-1, 3)
        if flat.shape[0] > 50_000:
            idx = np.linspace(0, flat.shape[0] - 1, 50_000, dtype=int)
            sample = flat[idx]
        else:
            sample = flat
        n_colors = len(np.unique(sample, axis=0))
        if n_colors <= 8 and h * w <= 128 * 128:
            return "grid"
        return "camera"

    @staticmethod
    def _upload_foveation_frames(arr, *, max_overview: int = 1024, fovea: int = 512):
        """Foveated fixations: overview (if large) + native-res center/upper/lower."""
        import cv2
        import numpy as np

        h, w = arr.shape[:2]
        frames = []
        if max(h, w) > max_overview:
            scale = max_overview / max(h, w)
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            ov = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA)
            frames.append({
                "name": "overview", "arr": ov, "offset": (0, 0),
                "scale": (w / nw, h / nh),
            })
        else:
            frames.append({
                "name": "full", "arr": arr, "offset": (0, 0),
                "scale": (1.0, 1.0),
            })
        side = min(fovea, h, w)
        if side >= 32:
            for name, cy_frac in (("center_fovea", 0.5), ("upper_fovea", 0.28),
                                  ("lower_fovea", 0.72)):
                cy, cx = int(cy_frac * h), w // 2
                y0 = max(0, min(h - side, cy - side // 2))
                x0 = max(0, min(w - side, cx - side // 2))
                crop = arr[y0:y0 + side, x0:x0 + side]
                frames.append({
                    "name": name, "arr": np.asarray(crop), "offset": (x0, y0),
                    "scale": (1.0, 1.0),
                })
        return frames

    def _ensure_upload_eye(self, modality: str, fh: int, fw: int):
        """Dedicated upload cortex — never shares the game/ARC eye context."""
        import substrate_rs as _srs
        from domains.vision_graph import RGBEye

        if not hasattr(self, "_upload_eye"):
            self._upload_eye = None
        area = max(1, fh * fw)
        min_area = max(8.0, area * 0.00008)
        edge_thresh = 18.0 if modality == "camera" else 40.0
        ctx = {"modality": modality, "cell_px": 1}
        if self._upload_eye is None:
            sub = _srs.Substrate()
            self._upload_eye = RGBEye(
                substrate=sub, n_az=16, edge_thresh=edge_thresh,
                min_area=min_area, context=dict(ctx)).build()
        else:
            self._upload_eye.context = dict(ctx)
            self._upload_eye.edge_thresh = edge_thresh
            self._upload_eye.min_area = min_area
        return self._upload_eye

    @staticmethod
    def _shape_kind_word(n_vertices: int) -> str:
        return {3: "triangle", 4: "quadrilateral", 5: "pentagon",
                6: "hexagon"}.get(int(n_vertices), f"polygon ({n_vertices} vertices)")

    def _write_upload_vision_summary(self, arr, doc_id, shape_ids, frames=None) -> None:
        """Mechanical read of GraphEye polygons → vision_summary on the doc."""
        try:
            da = self.s.node(doc_id)["attrs"]
            filename = str(da.get("filename") or "upload")
            h, w = int(arr.shape[0]), int(arr.shape[1])
            mean = arr.mean(axis=(0, 1))
            r, g, b = int(mean[0]), int(mean[1]), int(mean[2])
            n_fix = len(frames or [])
            mod = da.get("vision_modality") or "camera"
            if shape_ids:
                parts = [
                    f"Through my eye ({n_fix} fixation(s), {mod} front-end) I see "
                    f"{len(shape_ids)} shape(s) in your uploaded image "
                    f"({filename}, {w}×{h} native pixels):"]
                for i, sid in enumerate(shape_ids[:12], 1):
                    sa = self.s.node(sid)["attrs"]
                    nv = int(sa.get("n_vertices", 0))
                    area = int(float(sa.get("area", 0)))
                    kind = self._shape_kind_word(nv)
                    fix = sa.get("fixation") or "view"
                    parts.append(
                        f"{i}) at {fix}: a {kind} (~{area} px², {nv} vertices)")
                if len(shape_ids) > 12:
                    parts.append(f"(+{len(shape_ids) - 12} more shapes not listed)")
                parts.append(
                    f"Overall colour about RGB({r},{g},{b}). "
                    f"I have not run taught object naming on this yet.")
                text = " ".join(parts)
            else:
                text = (
                    f"I looked at your uploaded image ({filename}, {w}×{h} native "
                    f"pixels) through my eye across {n_fix} fixation(s) ({mod} "
                    f"front-end) but found no clear closed shapes. Overall colour "
                    f"about RGB({r},{g},{b}).")
            self.inner.set_attr(doc_id, "vision_summary", text)
            self.inner.set_attr(doc_id, "summary", text)
            self.inner.set_attr(doc_id, "vision_shape_count", float(len(shape_ids)))
        except Exception:  # noqa: BLE001 -- summary is best-effort
            pass

    # --- audio/speech: hear a file, ingest AcousticSign + Message chain -------

    def _ensure_speech_seeds(self):
        """Load the audio + speech seed vocabulary onto this agent (idempotent).
        The Rust decode pipeline needs the `audio` seed's productions (AudioContainer
        /AudioStream + admissible edges); recognition needs `speech`."""
        from substrate.boot_core import load_seeds_into
        load_seeds_into(self.s, self.agent, ["speech"])

    def open_audio_lexicon(self, name="default", match_threshold=0.80):
        """Find or open an AcousticLexicon by name (one per name). The lexicon is
        a graph-resident node the speech recogniser grows. Mechanical."""
        self._ensure_speech_seeds()
        for n in self.s.nodes("AcousticLexicon"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        from substrate_rs import speech as _speech
        return _speech.open_lexicon(self.inner, name=name,
                                    match_threshold=match_threshold)

    def ingest_audio_file(self, path, lexicon_name="default",
                          match_threshold=0.80, n_bands=16, n_time_windows=4,
                          sample_rate=22050, comprehend=False):
        """Hear an audio file: decode it and recognise utterances, minting one
        Message{source: audio} per detected utterance with its AcousticSign
        attached via `has_mention` (the speech-bridge Rule mirrors denotes ->
        refers_to so the intent Rules treat it as a Mention).

        Pure mechanical I/O: the cochlea / gammatone / STFT / recognition are all
        Rust primitives (`substrate_rs.audio` + `.speech`); this orchestrates the
        decode chain and translates the detected utterances into graph nodes.
        Returns a list of {message, utterance, sign, is_new}.

        `comprehend=True` makes each Message comprehension-ready — loads the
        intent seed and adds `has_speech_act`->statement + `sent_by`->interlocutor
        (audio carries no orthography to classify on, so the speech act defaults
        to statement, as the old AudioWorld did) — so a later `comprehend()`
        builds an Intent per heard utterance. Default off keeps the perception
        path pure (transcription doesn't need the conversation closure)."""
        from substrate_rs import audio as _audio
        from substrate_rs import speech as _speech
        lex = self.open_audio_lexicon(lexicon_name, match_threshold)
        statement = interlocutor = None
        if comprehend:
            self._ensure_intent_seeds()
            statement = (self._concept_by_name("statement")
                         or self.s.add_node("Concept", {"name": "statement"}))
            interlocutor = self._interlocutor()
        cnid = _audio.open_container(self.inner, path)
        try:
            snid = _audio.add_stream(self.inner, cnid)
            _audio.parse_stream(self.inner, cnid, snid)
            _audio.parse_native(self.inner, cnid, snid)
            results = _speech.ingest_speech(
                self.inner, snid, lex, n_bands=n_bands,
                n_time_windows=n_time_windows, fs=sample_rate,
                threshold=match_threshold)
        finally:
            _audio.close_container(cnid)
        out = []
        for utt_nid, sign_nid, is_new in results:
            mid = self.s.add_node("Message",
                                  {"from": "interlocutor", "source": "audio"})
            self.inner.add_edge_unchecked(self.agent, "sent", mid)
            if sign_nid is not None:
                self.inner.add_edge_unchecked(mid, "has_mention", sign_nid)
            if comprehend:
                self.inner.add_edge_unchecked(mid, "has_speech_act", statement)
                self.inner.add_edge_unchecked(mid, "sent_by", interlocutor)
            out.append({"message": mid, "utterance": utt_nid,
                        "sign": sign_nid, "is_new": is_new})
        return out

    def audio_signs(self, lexicon_name="default"):
        """Every AcousticSign currently in the named Lexicon (or [] if none)."""
        from substrate_rs import speech as _speech
        for n in self.s.nodes("AcousticLexicon"):
            if self.s.node(n)["attrs"].get("name") == lexicon_name:
                return _speech.lexicon_signs(self.inner, n)
        return []

    # --- conversation/intent: receive an utterance, comprehend it ------------

    def _ensure_intent_seeds(self):
        """Load the intent seed (+ its conversation/psychology/relations closure)
        — the speech-act taxonomy, adjacency pairs, and the intent/referent
        RewriteRules — onto this agent (idempotent)."""
        from substrate.boot_core import load_seeds_into
        load_seeds_into(self.s, self.agent, ["intent"])

    def _concept_by_name(self, name):
        """Find a Concept node by its `name` attr (the seed-installed speech-act
        + relation vocabulary). None if absent."""
        for n in self.s.nodes("Concept"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return None

    def _interlocutor(self, name="user"):
        """Find or create the Interlocutor the agent is speaking with."""
        for n in self.s.nodes("Interlocutor"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return self.s.add_node("Interlocutor", {"name": name})

    def receive_utterance(self, text, speech_act="statement",
                          speaker="user", tick=0):
        """Mint an inbound Message carrying a speech act and (optionally) a
        speaker — the graph token the seeded intent Rules build an Intent from.
        Mechanical I/O: translate an external utterance into a Message +
        has_speech_act (+ sent_by) edges; the Rules do the comprehension.

        `speaker=None` mints a Message with NO sent_by — exercising the
        unknown-speaker rule (intent_from_no_claim builds an Unknown speaker)."""
        self._ensure_intent_seeds()
        sa = self._concept_by_name(speech_act)
        if sa is None:
            sa = self.s.add_node("Concept", {"name": speech_act})
        mid = self.s.add_node("Message",
                              {"from": "interlocutor", "text": text, "tick": tick})
        self.inner.add_edge_unchecked(mid, "has_speech_act", sa)
        if speaker is not None:
            spk = self._interlocutor(speaker)
            self.inner.add_edge_unchecked(mid, "sent_by", spk)
        # Put the Message in the conversation Channel (the agent is the
        # addressee — participates_in it), so second-person referents resolve.
        ch = self._channel()
        self.inner.add_edge_unchecked(mid, "in_channel", ch)
        if speaker is not None:
            self.inner.add_edge_unchecked(spk, "participates_in", ch)
        # Turn spine: this Message responds_to the previous one, so anaphora
        # (it/this/that) can walk back to a prior turn's about_concept.
        prev = getattr(self, "_last_message", None)
        if prev is not None:
            self.inner.add_edge_unchecked(mid, "responds_to", prev)
        self._last_message = mid
        self._last_turn_inbound = mid
        # Tokenise the text into Mention nodes (mechanical text->graph at the
        # I/O boundary; the referent Rules decide what each Mention refers to),
        # and ensure the agent knows the seed-installed concepts.
        self._tokenise_mentions(mid, text)
        self._backfill_knows_concept()
        return mid

    def _channel(self):
        """The single conversation Channel the agent participates in (as
        addressee). Find or create; wire the agent's participates_in once."""
        chans = self.s.nodes("Channel")
        if chans:
            return chans[0]
        ch = self.s.add_node("Channel", {})
        self.inner.add_edge_unchecked(self.agent, "participates_in", ch)
        return ch

    def attach_chat_world(self, name="user"):
        """Wire the chat conversational scaffold (mechanical I/O, idempotent):
        the Interlocutor + Channel, the interlocutor's participates_in edge, and
        the agent's addressee edge. Returns {interlocutor, channel}."""
        inter = self._interlocutor(name)
        ch = self._channel()
        if ch not in set(self.inner.neighbours(inter, "participates_in")):
            self.inner.add_edge_unchecked(inter, "participates_in", ch)
        if inter not in set(self.inner.neighbours(self.agent, "addressee")):
            self.inner.add_edge_unchecked(self.agent, "addressee", inter)
        return {"interlocutor": inter, "channel": ch}

    def conversation(self):
        """All Messages in insertion (node-id) order as {text, from} dicts."""
        msgs = sorted(self.s.nodes("Message"), key=lambda n: n.value)
        return [{"text": self.s.node(m)["attrs"].get("text"),
                 "from": self.s.node(m)["attrs"].get("from")} for m in msgs]

    def chat_transcript(self):
        """Mechanical read of interlocutor/agent turn pairs for the web UI.

        Walks inbound Messages in node-id order and pairs each with the first
        outbound Message whose responds_to spine includes that inbound id.
        Pure graph query — no decisions."""
        turns = []
        for m in sorted(self.s.nodes("Message"), key=lambda n: n.value):
            attrs = self.s.node(m)["attrs"]
            if attrs.get("from") != "interlocutor":
                continue
            text = (attrs.get("text") or "").strip()
            if not text:
                continue
            reply = None
            reply_from = "agent"
            for r in self.outbound_messages():
                if m not in self.responds_to(r):
                    continue
                rt = (self.s.node(r)["attrs"].get("text") or "").strip()
                if rt:
                    reply = rt
                    reply_from = self.s.node(r)["attrs"].get("from") or "agent"
                    break
            if reply:
                turns.append({
                    "text": text,
                    "reply": reply,
                    "reply_from": reply_from,
                    "turn_id": int(m.value),
                })
        return turns

    def last_turn_inbound_id(self):
        """Node id of the inbound Message from the most recent converse() turn."""
        mid = getattr(self, "_last_turn_inbound", None)
        return int(mid.value) if mid is not None else None

    def _reply_for_inbound(self, inbound_mid):
        """The agent's text reply Message for an inbound turn, if any."""
        for r in self.outbound_messages():
            if inbound_mid in self.responds_to(r):
                rt = (self.s.node(r)["attrs"].get("text") or "").strip()
                if rt:
                    return r, rt
        # Fallback: Python-path replies (honest_capability / topic_reply / etc.)
        # return prose without always minting a responds_to edge to inbound.
        for r in self.outbound_messages():
            if r.value <= inbound_mid.value:
                continue
            rt = (self.s.node(r)["attrs"].get("text") or "").strip()
            if rt:
                return r, rt
        return None, None

    def reply_turn_trace(self, inbound_id):
        """Mechanical graph read of the thought/routing behind one chat turn.

        Returns a dict for the web UI: parse attrs written onto the inbound
        Message, goals/intents/mentions the graph built, and any SelfConcerns
        already filed about this turn. Pure query — no decisions."""
        try:
            import substrate_rs as srs
            mid = srs.NodeID(int(inbound_id))
        except (ValueError, TypeError):
            return None
        if not self.s.has_node(mid):
            return None
        ma = self.s.node(mid)["attrs"]
        if ma.get("from") != "interlocutor":
            return None
        reply_mid, reply_text = self._reply_for_inbound(mid)
        if not reply_text:
            reply_text = (ma.get("comp_reply_text") or "").strip()
        goals = []
        for g in self.inner.neighbours(self.agent, "has_goal"):
            if not self.s.has_node(g):
                continue
            if mid not in self.inner.neighbours(g, "comprehends"):
                continue
            ga = dict(self.s.node(g)["attrs"])
            ga["id"] = int(g.value)
            goals.append(ga)
        intent = None
        intents = self.inner.neighbours(mid, "has_intent")
        if intents and self.s.has_node(intents[0]):
            ia = self.s.node(intents[0])["attrs"]
            intent = {k: ia.get(k) for k in ("kind", "status", "force", "topic")}
            intent["id"] = int(intents[0].value)
        mentions = []
        for mn in self.inner.neighbours(mid, "has_mention"):
            if not self.s.has_node(mn):
                continue
            mna = self.s.node(mn)["attrs"]
            refs = []
            for c in self.inner.neighbours(mn, "refers_to"):
                if self.s.has_node(c) and self.s.node(c).get("type") == "Concept":
                    refs.append(self.s.node(c)["attrs"].get("name"))
            mentions.append({"text": mna.get("text"), "refers_to": refs})
        topic = None
        for ct in self.inner.neighbours(self.agent, "current_topic"):
            if self.s.has_node(ct):
                topic = self.s.node(ct)["attrs"].get("name")
                break
        concerns = []
        for sc in self.s.nodes("SelfConcern"):
            if not self.s.has_node(sc):
                continue
            if mid not in self.inner.neighbours(sc, "about_message"):
                continue
            sa = self.s.node(sc)["attrs"]
            concerns.append({
                "id": int(sc.value),
                "status": sa.get("status"),
                "source": sa.get("source"),
                "kind": sa.get("kind"),
                "content": sa.get("content"),
            })
        parse_keys = (
            "comp_kind", "comp_predicate", "comp_content", "comp_topic",
            "comp_dispatch_path", "comp_dispatch_meta", "comp_reflexive",
            "comp_intent", "comp_anaphor", "topic_pending", "topic_followup",
            "attachment_pending",
            "self_account_unresolved", "self_account_topic", "reply_flag_note",
            "reply_flag_noted", "comp_reply_text", "reply_from",
        )
        parse = {k: ma.get(k) for k in parse_keys if ma.get(k) is not None}
        return {
            "turn_id": int(mid.value),
            "question": ma.get("text") or "",
            "reply": reply_text or "",
            "reply_from": ma.get("reply_from") or (
                self.s.node(reply_mid)["attrs"].get("from") if reply_mid is not None else "agent"),
            "reply_id": int(reply_mid.value) if reply_mid is not None else None,
            "parse": parse,
            "goals": goals,
            "intent": intent,
            "mentions": mentions,
            "current_topic": topic,
            "concerns": concerns,
        }

    def last_inbound(self):
        """The latest interlocutor Message as {text, from}, or None."""
        ins = [m for m in self.s.nodes("Message")
               if self.s.node(m)["attrs"].get("from") == "interlocutor"]
        if not ins:
            return None
        m = max(ins, key=lambda n: n.value)
        a = self.s.node(m)["attrs"]
        return {"text": a.get("text"), "from": a.get("from")}

    _MENTION_STRIP = ".,?!;:()[]\"'"

    def _tokenise_mentions(self, mid, text):
        """Whitespace-split / lowercase / strip-punctuation a Message's text into
        Mention nodes (has_mention edges). Mechanical I/O translation.

        Also chains the Mentions in reading order with `next_mention` /
        `prev_mention` adjacency edges (mn -> next, mn -> prev) so positional
        faculties (coordination / equation / n-gram context) can traverse a
        token's neighbours directly. Pure tokenisation — no decisions."""
        prev = None
        for raw in text.split():
            clean = raw.strip(self._MENTION_STRIP).lower()
            if not clean:
                continue
            mn = self.s.add_node("Mention", {"text": clean})
            self.inner.add_edge_unchecked(mid, "has_mention", mn)
            if prev is not None:
                self.inner.add_edge_unchecked(prev, "next_mention", mn)
                self.inner.add_edge_unchecked(mn, "prev_mention", prev)
            prev = mn

    def _backfill_knows_concept(self):
        """Wire agent --knows_concept--> every Concept node (mechanical). The
        referent rule iterates knows_concept to resolve Mentions to Concepts."""
        known = set(self.inner.neighbours(self.agent, "knows_concept"))
        for c in self.s.nodes("Concept"):
            if c not in known:
                self.inner.add_edge_unchecked(self.agent, "knows_concept", c)

    # I/O-boundary speech-act classifier (surface cues only; the agent's
    # structural model is the graph data we tag, not this classifier).
    _GREETING_FORMS = frozenset(["hi", "hello", "hey", "greetings",
                                 "good morning", "good afternoon", "good evening"])
    _THANKS_FORMS = frozenset(["thanks", "thank you", "thx"])
    _QUESTION_LEADS = frozenset(["what", "when", "where", "which", "who", "why",
                                 "how", "is", "are", "was", "were", "do", "does",
                                 "did", "can", "could", "will", "would", "should",
                                 "may", "might", "have", "tell"])
    # Steering verbs (seeds/conversation_steering.json) are included so a
    # sentence-initial imperative the POS layer tags as a noun ("Work on the
    # X gap.") still enters the turn as a request at this sanctioned thin
    # boundary — the steering RULES (not this list) decide what to do with it.
    _IMPERATIVE_LEADS = frozenset(["read", "write", "run", "execute", "open",
                                   "show",
                                   "promote", "pursue", "prioritise",
                                   "prioritize", "work", "focus",
                                   "drop", "retire", "stop", "abandon",
                                   "dismiss"])

    def classify_speech_act(self, text):
        """Classify text into a speech-act name at the I/O boundary (surface
        cues only). Mirrors domains.conversation.classify_speech_act."""
        s = text.strip()
        if not s:
            return "statement"
        low = s.lower()
        head = low.split(None, 1)[0]
        # Match social/lead tokens robustly to trailing punctuation
        # ("Thanks!", "Hi!", "hello.") — still a surface cue only, still
        # boundary-thin; the raw "?" test below is unaffected.
        _punct = ".,!?;:…"
        low_c = low.strip(_punct + " ")
        head_c = head.strip(_punct)
        if low_c in self._GREETING_FORMS or head_c in self._GREETING_FORMS:
            return "greeting"
        if low_c in self._THANKS_FORMS or head_c in self._THANKS_FORMS:
            return "thanks"
        if s.endswith("?") or head_c in self._QUESTION_LEADS:
            return "question"
        if head_c in self._IMPERATIVE_LEADS:
            return "request"
        return "statement"

    def add_inbound(self, text, speaker="user"):
        """Receive an inbound utterance, classifying its speech act at the I/O
        boundary. Returns the Message NodeID."""
        return self.receive_utterance(
            text, speech_act=self.classify_speech_act(text), speaker=speaker)

    def add_outbound(self, text, kind="statement", *, source="agent", inbound=None):
        """Mint an outbound Message tagged with speech-act `kind`,
        threaded into the turn spine (responds_to `inbound` or the previous message).
        `source` is 'agent' (graph-native) or 'adapter' (host I/O floor). Mechanical."""
        self._ensure_intent_seeds()
        mid = self.s.add_node("Message", {
            "from": str(source),
            "text": str(text),
            "reply_source": "world_adapter" if source == "adapter" else "agent",
        })
        sa = self._concept_by_name(kind) or self.s.add_node("Concept", {"name": kind})
        self.inner.add_edge_unchecked(mid, "has_speech_act", sa)
        if source == "agent":
            self.inner.add_edge_unchecked(self.agent, "sent", mid)
            self.inner.add_edge_unchecked(mid, "sent_by", self.agent)
        target = inbound if inbound is not None else getattr(self, "_last_turn_inbound", None)
        if target is None:
            target = getattr(self, "_last_message", None)
        if target is not None:
            self.inner.add_edge_unchecked(mid, "responds_to", target)
        self._last_message = mid
        return mid

    def _finish_turn_reply(self, inbound, text, *, source="adapter", substantive=True):
        """Record reply attribution on the inbound turn. Adapter-produced prose
        mints a Message{from:'adapter'}; graph-native replies only annotate.

        TOLD-STATUS (Wave: interlocutor-as-modeled-participant, task 1): this is
        the SINGLE choke point every substantive reply passes through (topic
        answers, document answers, gap confirmations, rule-minted text) before
        the turn ends — so it is also where the agent mechanically records what
        it just told the addressee. `substantive` distinguishes a real answer
        (the default) from the terminal honest-floor acknowledgment (passed
        `substantive=False` at its one call site): a bare 'noted'/'got it' is
        not content told, and must not seed believed_concepts with its own
        register words."""
        if inbound is None or not str(text or "").strip():
            return text
        surface = str(text)
        try:
            self.inner.set_attr(inbound, "comp_reply_text", surface)
            self.inner.set_attr(inbound, "reply_from", str(source))
        except Exception:  # noqa: BLE001
            pass
        if substantive:
            try:
                ad = self._addressee()
                if ad is not None:
                    concepts, _ = self._content_concepts(surface)
                    self._grow_believed_concepts(ad, concepts)
            except Exception:  # noqa: BLE001 -- told-status is best-effort, never load-bearing
                pass
        if source == "adapter":
            existing, _ = self._reply_for_inbound(inbound)
            if existing is None:
                self.add_outbound(surface, kind="answer", source="adapter", inbound=inbound)
        return surface

    def last_turn_reply_meta(self):
        """Mechanical read of the most recent converse() reply attribution."""
        mid = getattr(self, "_last_turn_inbound", None)
        if mid is None or not self.s.has_node(mid):
            return {}
        attrs = self.s.node(mid)["attrs"]
        return {
            "reply": (attrs.get("comp_reply_text") or "").strip(),
            "reply_from": attrs.get("reply_from") or "agent",
        }

    def comprehend(self):
        """Run the seeded rules to a fixed point — fire the intent/referent/
        speech-bridge Rules over whatever Messages are pending. Returns the
        number of rule applications. Mechanical: tick the graph, the Rules
        decide."""
        # A fully seeded agent publishes one graph-owned asynchronous cycle
        # quantum from cognitive supervision. Conversation is another entry
        # point into the same graph, so it consumes that quantum too rather
        # than holding the daemon lock in an unbounded rule closure. Partial
        # or legacy graphs retain their existing native contract.
        try:
            budgets = [node for node in self.s.nodes("AsyncDaemonCycleBudget")
                       if self.s.has_node(node)
                       and self.s.node(node)["attrs"].get("status") == "active"]
            if len(budgets) == 1:
                quantum = self.s.node(budgets[0])["attrs"].get("quantum_units")
                if type(quantum) is int and quantum > 0:
                    return self.inner.run_rules(max_steps=quantum)
        except Exception:
            pass
        return self.inner.run_rules()

    def intent_of(self, mid):
        """The Intent the rules built for a Message (or None)."""
        ns = list(self.inner.neighbours(mid, "has_intent"))
        return ns[0] if ns else None

    def enable_replies(self):
        """Load the turn-taking reply faculty (conversation_reply seed): the
        RewriteRule that gives an inbound Message's adjacency-pair Intent an
        outbound second-pair-part. Idempotent."""
        from substrate.boot_core import load_seeds_into
        load_seeds_into(self.s, self.agent, ["conversation_reply"])

    def outbound_messages(self):
        """Outbound Messages the interlocutor should see (agent or adapter)."""
        return [n for n in self.s.nodes("Message")
                if self.s.node(n)["attrs"].get("from") in ("agent", "adapter")]

    def agent_outbound_messages(self):
        """Outbound Messages minted by the graph-native agent only."""
        return [n for n in self.s.nodes("Message")
                if self.s.node(n)["attrs"].get("from") == "agent"]

    def responds_to(self, mid):
        """The Message(s) `mid` responds to (the turn spine). Pure query."""
        return list(self.inner.neighbours(mid, "responds_to"))

    def emit_reply(self, reply_mid):
        """Render an outbound reply Message to surface text (the EMIT side).

        Ladder (NEVER a bare act name, NEVER None):
          1. the GRAPH RENDERER (`utterance_for`) — a real learned/derived sign
             wins and is byte-identical (e.g. a `learn_sign`-taught greeting →
             'hello'). A render that merely echoes the bare concept name
             ('acknowledgment', 'greeting') is the renderer's fallback, NOT a
             real surface — it is rejected as the act-name leak.
          2. the REGISTER TABLE (`surface_for`) — social acts render in the
             register the agent believes the interlocutor uses ('got it' /
             'noted' / 'understood'), so an untaught social act renders properly
             and MATCHES the interlocutor, never leaking its name.
          3. an HONEST minimal reply (register acknowledgment or 'I have no reply
             to that.') — a true dead end still speaks, never falls silent."""
        sa = list(self.inner.neighbours(reply_mid, "has_speech_act"))
        if not sa:
            return self._honest_minimal_reply()
        concept = self.s.node(sa[0])["attrs"].get("name")
        if not concept:
            return self._honest_minimal_reply()
        rendered = self.utterance_for(concept)
        if rendered and rendered.strip().lower() != str(concept).strip().lower():
            return rendered                      # a real graph surface — keep it
        reg = self.surface_for(concept)          # register table (social acts)
        if reg:
            return reg
        return self._honest_minimal_reply()

    def _honest_minimal_reply(self):
        """The always-honest floor for the conversational surface: a register-
        matched acknowledgment ('got it'/'noted'/'understood'), or a fixed honest
        sentence if even that is unavailable. Mechanical host I/O — an honest
        'I heard you', never a fabricated content claim, never None/silence."""
        return self.surface_for("acknowledgment") or "I have no reply to that."

    def _honest_self_reply(self, comp):
        """The HONEST self-process floor for a reflexive 'how do you <verb>' / 'how does X
        come about' question the agent holds NO specific self-account for (comprehend_text's
        `honest_self` dispatch). Never the self_organisation DOMAIN LIST (a non-sequitur) and
        never an opaque rule-dump — an honest 'I can't say precisely'. Mechanical host I/O,
        the same class as `_honest_no_answer` / `_honest_minimal_reply`."""
        d = (comp.dispatch or {}) if comp is not None else {}
        verb = d.get("verb")
        if d.get("self_process") and verb:
            return f"I can't say precisely how I {verb}."
        return "I can't say precisely how that comes about."

    def _honest_no_answer(self, text):
        """An unanswerable question -> an HONEST produced statement, never silence
        and never the bare act token. Names the focus it could not answer."""
        import re
        raw = str(text).strip()
        m = re.search(
            r"what(?:'s|s| is| are| was)\s+(?:a |an |the )?(.+?)\s+made\s+of\s*\??$",
            raw, re.IGNORECASE)
        if m:
            focus = m.group(1).strip().rstrip("?").strip()
            return (f"I don't hold what {focus} is made of yet."
                    if focus else "I don't hold that.")
        m = re.search(r"what(?:'s|s| is| are| was)\s+(?:a |an |the )?(.+?)\s*\??$",
                      raw, re.IGNORECASE)
        focus = (m.group(1).strip().rstrip("?").strip() if m else "")
        return f"I don't know {focus}." if focus else "I don't hold that."

    # --- PHASE 3: the CONCEPTUALIZER in the LIVE reply path -------------------
    #
    # A substantive reply now FORMS A COMMUNICATIVE INTENT before it is spoken and
    # runs the self-monitor to the commitment gate (domains.conceptualizer — the
    # jabberwock's OWN force/shape/monitor rules). The DELIVERED words stay the
    # formulator's: the rich self-model / answer PROSE is rendered by
    # `_surface_self_state` / `answer_question` UNCHANGED (the conceptualizer only
    # forms + monitor-gates the intent for it); the concept-level describe reply
    # (conversation_action._act_describe_scene) is additionally SHAPED by the
    # committed audience-design outcome. Nothing here decides force/shape/recoverable:
    # `force_kind` is fixed by the reply's SPEECH ACT (a constant per code path), and
    # the shape/monitor decisions live entirely in the jabberwock's authored rules.

    def _interlocutor_snapshot(self, name="user"):
        """Read the tracked Interlocutor node's audience-grounding attrs into the
        {id, observed, known_concepts} shape the conceptualizer's audience model consumes.
        Mechanical graph read — an unobserved/unknown interlocutor is the honest ungrounded
        default (observed False, no known concepts), which makes the pipeline formulate
        EXPLICITLY."""
        # Prefer the persistent interlocutor model's ACTIVE party (it accumulates name/
        # known_concepts/observed across turns, and re-attributes to a new party when the
        # collapse residual says the speaker changed) -- that is the grounded audience feed.
        snap = None
        try:
            from domains import interlocutor_model as _im
            if any(a.get("active") for a in
                   (self.s.node(n)["attrs"] for n in self.s.nodes("Interlocutor"))):
                snap = _im.snapshot(self)
        except Exception:
            snap = None
        if snap is None:
            node = self._interlocutor(name)
            at = self.s.node(node)["attrs"]
            snap = {"id": at.get("name", name),
                    "observed": bool(at.get("observed", False)),
                    "known_concepts": list(at.get("known_concepts") or [])}
        # Thread the tracked REGISTER (a faster manifold-type signal than content concepts — a formal
        # register types a period/formal interlocutor before its concepts accumulate). Additive keys;
        # consumers that don't read them are unaffected.
        snap.update(self._register_fields())
        return snap

    def _register_fields(self) -> dict:
        """The CONVERSATION-LEVEL register: the accumulated formal/casual cue counts summed across the
        tracked Interlocutor parties, plus the derived register label. Summed across parties (not just
        the active one) because a mid-conversation re-attribution can hand the active slot to a fresh
        party while the register the interlocutor established still stands — the register is a property
        of the conversation, not of whichever party is momentarily active. Mechanical aggregate read."""
        frm = cas = 0.0
        for n in self.s.nodes("Interlocutor"):
            a = self.s.node(n)["attrs"]
            frm += float(a.get("formal_cues") or 0.0)
            cas += float(a.get("casual_cues") or 0.0)
        reg = "casual" if cas > frm else "formal" if frm > cas else "neutral"
        return {"register": reg, "formal_cues": frm, "casual_cues": cas}

    def _delivery_snapshot(self, name="user"):
        """The interlocutor view a REPLY is shaped to — the active-party snapshot made robust to
        mid-conversation re-attribution by folding in the conversation-level accumulation: observed if
        ANY tracked party is observed, known_concepts the UNION across parties, and the aggregate
        register (already carried by `_interlocutor_snapshot`). A re-attribution can hand the active
        slot to a fresh, unobserved party while the conversation's common ground and register still
        stand; delivery reads the whole conversation. Mechanical aggregate read — no decision over
        graph state (the DECISION of which concepts are manifold-foreign stays audience_adaptation's)."""
        snap = dict(self._interlocutor_snapshot(name))
        observed = bool(snap.get("observed"))
        known = list(snap.get("known_concepts") or [])
        kset = set(known)
        for n in self.s.nodes("Interlocutor"):
            at = self.s.node(n)["attrs"]
            if at.get("observed"):
                observed = True
            for c in (at.get("known_concepts") or ()):
                if c not in kset:
                    kset.add(c)
                    known.append(c)
        snap["observed"] = observed
        snap["known_concepts"] = known
        return snap

    def _content_concepts(self, text):
        """Derive a small comprehend-safe concept set (+ an identity lexicon) from a produced
        reply — the content the formed intent carries and the self-monitor imagines reception
        of. Mechanical tokenisation of the reply's OWN distinctive words (lower-cased alpha
        runs, ≥4 chars, deduped, capped), never a decision about meaning. Returns
        (concepts, lexicon)."""
        import re
        seen, concepts = set(), []
        for w in re.findall(r"[a-z]+", str(text).lower()):
            if len(w) >= 4 and w not in seen:
                seen.add(w)
                concepts.append(w)
        concepts = concepts[:6]
        return concepts, [{"form": c, "concept": c} for c in concepts]

    def _form_reply_intent(self, force_kind, concepts, lexicon, *, rounds=3):
        """Form a communicative intent for a substantive reply and run the self-monitor to the
        commitment gate. Marshal-only bridge to domains.conceptualizer; caches the result on
        `self._last_reply_intent` (mechanical read-off for scripts/tests). Returns the
        {goal,intent,committed} dict, or None if the conceptualizer stack is unavailable — an
        honest fallback: the reply still speaks. `force_kind` is fixed by the calling reply
        path's speech act (a constant, not a graph-state decision)."""
        result = None
        try:
            from domains import conceptualizer as _cc
            interlocutor = self._interlocutor_snapshot()
            lex = self._lexicon_with_known(list(lexicon), interlocutor)
            result = _cc.conceptualize_reply(self, force_kind, list(concepts), interlocutor,
                                             lex, rounds=rounds)
        except Exception:
            result = None
        self._last_reply_intent = result
        return result

    @staticmethod
    def _lexicon_with_known(lexicon, interlocutor):
        """Extend a reply-derived lexicon so EVERY concept the audience is credited to know is
        renderable. The audience model now ACCUMULATES the interlocutor's own concepts (common
        ground); audience_driven_production restates credited-known concepts in its explicit rung,
        so each must have a surface. Mechanical: add a self-rendering entry per known concept the
        lexicon does not already cover (no decision — every concept renders as its own word)."""
        forms = {e.get("concept") for e in lexicon}
        out = list(lexicon)
        for c in (interlocutor.get("known_concepts") or []):
            if c not in forms:
                out.append({"form": str(c), "concept": str(c)})
        return out

    def _form_reply_intent_for_text(self, force_kind, text, *, rounds=3):
        """Form + monitor-gate a reply intent whose content is the produced reply's own words —
        the GATE for the rich-prose paths (the prose renderer is UNCHANGED). Returns the
        pipeline result or None."""
        concepts, lexicon = self._content_concepts(text)
        return self._form_reply_intent(force_kind, concepts, lexicon, rounds=rounds)

    # speech acts that are terminal / purely social — they keep their canonical
    # adjacency-pair behaviour and are NOT re-interpreted as an act/ask-back.
    _SOCIAL_ACTS = frozenset({"greeting", "thanks", "farewell", "closing",
                              "acknowledgment", "backchannel", "answer"})

    # --- graph-native conversation (Phase 1): parse -> graph, rules decide ---
    #
    # These four helpers are the ADAPTER side of the migration off the Python
    # decision ladder (plan: "comprehend -> mint goal -> reply, no Python
    # ladder"). They are strictly MECHANICAL: write the parse into the graph,
    # ensure the deciding seed is loaded, and read back whatever reply the
    # agent's OWN rules produced. No decision about what the agent should do
    # lives here -- that is the comprehend_instruction seed's rule.

    def _ensure_comprehension_seeds(self):
        """Idempotently install the comprehend_instruction seed (the graph rule
        that decides read/comprehend instructions). Robust across boot paths:
        a full boot loads it via load_all_seeds' glob, a minimal boot via here;
        we guard on the rule already being present (by name) so neither path
        double-installs it (which would double-fire and duplicate replies)."""
        if getattr(self, "_comprehension_seed_loaded", False):
            return
        try:
            names = {r.get("name") for r in self.inner.export_rules()}
        except Exception:  # noqa: BLE001 -- if we can't read rules, try the load
            names = set()
        # (seed id, a rule name it defines) — load each only if absent, so
        # neither the full-boot glob nor a minimal boot double-installs.
        for seed_id, probe_rule in (
            ("speech_act_classify", "sak_kind_question"),
            ("comprehend_instruction", "comprehend_read_instruction"),
            ("conversation_self_concern", "mint_self_improvement_concern_confident"),
            # R7 before topic_route: route_question_to_topic's own deferral
            # guard reads shadow_doc_topic (a pre-tick Message attr, so this
            # is not an install-order race) — listed first here purely for
            # readability, matching the seeds' own dependency story.
            ("conversation_topic_span", "route_shadow_topic_to_answer"),
            ("conversation_topic_route", "route_question_to_topic"),
            # R6: a bare first-person question ("who am I?") the general
            # "know" dispatch would otherwise misroute to a world-concept
            # lookup on the pronoun itself.
            ("first_person_routing", "route_first_person_question_to_interlocutor"),
            ("conversation_capability_route", "route_polar_capability_domain"),
            ("conversation_capability_reply", "reply_held_capability"),
            # topic_search* must install BEFORE conversation_topic_reply (their
            # declared dependency order): reply_topic_unresolved's pending-
            # SearchRequest guard only suppresses if the search rule was
            # evaluated first in the pass -- rule order is install order.
            ("topic_search_verify", "select_verified_search_candidate"),
            ("topic_sync_ground", "sync_ground_request_from_answer_topic"),
            ("topic_search", "search_request_from_answer_topic"),
            # conversation_grice must install BEFORE conversation_topic_reply
            # (same install-order precedent as topic_search* above): its
            # reply_topic_repeat_known rule's set_attr m.topic_replied=1.0 must
            # be visible to reply_topic_from_held_answer's guard within the
            # SAME run_rules pass, so a repeat-topic turn is answered ONCE,
            # with the Gricean-quantity prefix, not twice.
            ("conversation_grice", "reply_topic_repeat_known"),
            ("conversation_topic_reply", "reply_topic_from_held_answer"),
            ("conversation_attachment_route", "route_question_to_attachment"),
            ("conversation_attachment_reply", "reply_attachment_from_vision"),
            ("conversation_honest_floor", "reply_honest_floor"),
            ("conversation_self_reply", "reply_self_process_account"),
            ("conversation_topic_tracking", "resolve_anaphor_to_current_topic"),
            ("conversation_elaborate", "serve_next_detail_chunk"),
            ("gap_awareness", "note_unresolved_topic_gap"),
            ("conversation_steering", "steer_promote_concern"),
            ("conversation_reply_flag", "mint_reply_flag_concern"),
            # interlocutor_trust needs jabberwock_creator's Concept nodes present
            # to ever fire (an Exists lookup, honest no-op otherwise) -- listed
            # after the other seeds so a fresh boot that already carries the
            # identity seed sees it; a minimal boot that never loads
            # jabberwock_creator simply never sets creator_origin reliability.
            ("interlocutor_trust", "creator_self_report_reliability"),
        ):
            if probe_rule not in names:
                try:
                    from substrate.seed_loader import manifest_for
                    self.inner.load_seed_manifest(manifest_for(seed_id), self.agent)
                except Exception:  # noqa: BLE001 -- absence just means the Python fallback handles it
                    pass
        if not any(self.s.node(n)["attrs"].get("name") == "spatial_inference"
                   for n in self.s.nodes("HeldCapability")):
            try:
                from substrate.seed_loader import manifest_for
                self.inner.load_seed_manifest(manifest_for("inference_affordances"), self.agent)
            except Exception:  # noqa: BLE001
                pass
        if not list(self.s.nodes("HeldCapability")):
            try:
                from substrate.seed_loader import manifest_for
                self.inner.load_seed_manifest(manifest_for("movement_affordances"), self.agent)
            except Exception:  # noqa: BLE001
                pass
        # interlocutor_shapes ships NODES only (no executable rule), so it
        # can't use the probe-rule idiom above -- guarded the same way as the
        # HeldCapability seeds just above: install once, by presence.
        if not any(self.s.node(n)["attrs"].get("name") == "default_uncalibrated"
                   for n in self.s.nodes("InterlocutorShape")):
            try:
                from substrate.seed_loader import manifest_for
                self.inner.load_seed_manifest(manifest_for("interlocutor_shapes"), self.agent)
            except Exception:  # noqa: BLE001
                pass
        if not list(self.inner.neighbours(self.agent, "holds_self_process")):
            try:
                from substrate.seed_loader import manifest_for
                self.inner.load_seed_manifest(manifest_for("self_processes"), self.agent)
            except Exception:  # noqa: BLE001
                pass
        # Instruction-route verb Concepts are seed DATA the instruction rules
        # read (comprehend_instruction v2.0.0 / conversation_self_concern
        # v2.1.0 / conversation_self_reply v1.2.0). A resumed checkpoint that
        # predates them can hold same-NAME Concepts WITHOUT the route attr
        # (learned_lexicon etc.), so the daemon's name-keyed Concept
        # reconciliation skips them -- find-or-create here keyed on
        # (name, instruction_route). Mechanical, idempotent seed wiring (the
        # wire_substrate_identity precedent); no decision.
        try:
            from substrate.seed_loader import manifest_for
            held_routes = set()
            for c in self.s.nodes("Concept"):
                a = self.s.node(c)["attrs"]
                if a.get("instruction_route"):
                    held_routes.add((a.get("name"), a.get("instruction_route")))
            for seed_id in ("comprehend_instruction", "conversation_self_concern",
                            "conversation_self_reply"):
                try:
                    man = manifest_for(seed_id)
                except Exception:  # noqa: BLE001 -- a missing seed just ships no verbs
                    continue
                for node in (man.get("nodes") or []):
                    if not isinstance(node, dict) or node.get("type") != "Concept":
                        continue
                    a = node.get("attrs") or {}
                    key = (a.get("name"), a.get("instruction_route"))
                    if not a.get("instruction_route") or key in held_routes:
                        continue
                    self.s.add_node("Concept", dict(a))
                    held_routes.add(key)
        except Exception:  # noqa: BLE001 -- wiring hiccup leaves the seeds as loaded
            pass
        self._comprehension_seed_loaded = True

    @staticmethod
    def _instruction_content(raw, comp):
        """The argument text of a read/comprehend instruction (mechanical parse
        of the instruction's content, the twin of predicate/object extraction).
        Prefer the clause after the first ':' ("read this: <content>"); else the
        comprehended object; else the raw text. Never a decision -- just which
        span is the thing being read."""
        raw = raw or ""
        if ":" in raw:
            after = raw.split(":", 1)[1].strip()
            if after:
                return after
        obj = (getattr(comp, "dispatch", None) or {}).get("object")
        return obj or raw

    def _graph_kind_for(self, mid, text):
        """The speech-act KIND for a live inbound Message, DECIDED BY THE
        AGENT'S OWN HELD RULES (seeds/speech_act_classify.json — Wave 4
        migration of comprehend_text._classify_kind). Mechanical adapter work
        only:

          1. write the classification SIGNALS onto the Message (data the
             parse/POS layer already computed — comprehend_text.kind_signals);
          2. EXPORT the agent's held sak_kind_* rule bodies from its live
             engine (the reconciled / refreshable / experimentable copies —
             self-repairable) and run THEM, isolated, over those signals;
          3. write the minted sak_kind back onto the live Message (the
             auditable record the parity gate reads) and return it.

        The pass is ISOLATED (only the kind rules run) rather than a full
        comprehend() fixpoint: a full pass at this point — BEFORE the comp_*
        parse facts are written — lets mention-keyed rules fire on a
        half-ingested turn, which measurably flipped the elaboration
        serve-vs-anaphor rule race (a behavior change this wave forbids).
        Returns None on any hiccup (comprehend_text then classifies via the
        same seed rules on a scratch Message)."""
        try:
            from domains import comprehend_text as _ct
            sig = _ct.kind_signals(self, text)
            self._ensure_comprehension_seeds()
            self.inner.set_attr(mid, "sak_pending", 1.0)
            self.inner.set_attr(mid, "sak_ends_q", 1.0 if sig.get("ends_q") else 0.0)
            if sig.get("first_role") is not None:
                self.inner.set_attr(mid, "sak_first_role", str(sig["first_role"]))
            if sig.get("first_pos") is not None:
                self.inner.set_attr(mid, "sak_first_pos", str(sig["first_pos"]))
            # The agent's OWN held rule bodies decide (falls back to the seed
            # file inside _classify_kind_rules when none are held).
            try:
                held = [r for r in self.inner.export_rules()
                        if str(r.get("name", "")).startswith("sak_kind_")
                        and r.get("active")]
            except Exception:  # noqa: BLE001 -- seed-file rules then decide
                held = []
            kind = _ct._classify_kind_rules(sig, rules=held or None)
            if kind is not None:
                self.inner.set_attr(mid, "sak_kind", str(kind))
            return kind
        except Exception:  # noqa: BLE001 -- comprehend_text's scratch-rule path takes over
            return None

    def _write_comprehension_to_graph(self, mid, comp):
        """Write the mechanical parse onto the inbound Message so graph rules can
        match + decide: comp_kind (question/instruction/statement), and for an
        instruction its comp_predicate (leading verb) + comp_content (argument).
        Pure translation of the already-computed Comprehension into graph data.
        NOTE (Wave 4): the KIND inside `comp` is already the graph's decision
        (the sak_kind the seeded rules minted, read back by converse/
        comprehend_text); comp_kind here is the FINAL comprehension record —
        an echo of that decision unless a still-Python intercept (table
        fastpath / satisfiable / rule-name promotion) overrode it, exactly as
        before this wave (ledger items for later waves)."""
        try:
            # Bind the agent to this utterance via a real outgoing edge (the
            # `sd` pattern: match on ["ag","observed","obs"], never on
            # ["agent","is_a","Agent"] -- the is_a/type triple expands to many
            # bindings in the matcher and over-fires the rule once per pass).
            # De-duplicated: _graph_kind_for already added it on a converse()
            # turn (two same-type edges can break run_rules matching).
            if mid not in list(self.inner.neighbours(self.agent, "received")):
                self.inner.add_edge_unchecked(self.agent, "received", mid)
            final_kind = getattr(comp, "kind", None) or "statement"
            self.inner.set_attr(mid, "comp_kind", final_kind)
            # WAVE 3 (deep-reader cutover) POLICY 1 -- kind stays Python/sak-
            # decided (93.8% agreement on the divergence corpus; the 10
            # disagreements are comp_kind being deliberately PRAGMATIC --
            # surface imperatives promoted to question for the satisfiable/
            # meta/table dispatch, e.g. "Name one of your rules."). NO
            # cutover. Record the disagreement as a mechanical DATUM only
            # (never consulted by any routing rule) so the agent's own
            # divergence-noticing machinery (gap_awareness precedent) can
            # read it later: the shadow read already wrote shadow_speech_act
            # on this Message (converse() runs it before comprehend_text), so
            # this is a pure readback + compare, no new decision. Both values
            # this datum compares (comp_kind / shadow_speech_act) are already
            # separately readable on the SAME Message -- no need to echo them
            # again under new attr names.
            _shadow_sa = self.s.node(mid)["attrs"].get("shadow_speech_act")
            if _shadow_sa is not None and str(_shadow_sa) != str(final_kind):
                self.inner.set_attr(mid, "speech_act_divergence", 1.0)
            d = getattr(comp, "dispatch", None) or {}
            path = d.get("path")
            if path is not None:
                self.inner.set_attr(mid, "comp_dispatch_path", str(path))
            meta = d.get("meta_target")
            if meta is not None:
                self.inner.set_attr(mid, "comp_dispatch_meta", str(meta))
            meta_arg = d.get("meta_arg")
            if meta_arg is not None:
                self.inner.set_attr(mid, "comp_meta_arg", str(meta_arg))
            if str(meta or "") == "self_kind" and meta_arg is not None:
                try:
                    from domains.acronym_expand import expand_acronym as _expand_acronym
                    phrase = _expand_acronym(str(meta_arg)) or str(meta_arg)
                except Exception:  # noqa: BLE001
                    phrase = str(meta_arg)
                self.inner.set_attr(mid, "comp_kind_phrase", phrase.lower())
            if getattr(comp, "reflexive", False):
                self.inner.set_attr(mid, "comp_reflexive", 1.0)
            if getattr(comp, "intent", None):
                self.inner.set_attr(mid, "comp_intent", str(comp.intent))
            # R6 (blind-spot closure, bare first-person routing): mechanical
            # echo of the general "know" dispatch's own topic-nominal guess
            # (comp.dispatch["concept"], from comprehend_text's non-reflexive
            # `_topic_nominal(rel)` -- item 1.21, unmigrated) onto the
            # Message, lowercased/stripped exactly like every other comp_*
            # echo (comp_predicate/comp_verb). This is NOT a new decision --
            # `d.get("concept")` was already computed by the (unchanged)
            # Python front end; this just makes the VALUE graph-visible so a
            # rule can compare it against a Mention's own resolved text (see
            # seeds/first_person_routing.json::route_first_person_question_
            # to_interlocutor, which decides -- from the Mention's OWN
            # refers_to-speaker resolution, not this string -- whether the
            # "know" path's concept IS the first-person speaker).
            if str(path or "") == "know":
                _know_concept = d.get("concept")
                if _know_concept:
                    self.inner.set_attr(mid, "comp_know_concept",
                                        str(_know_concept).lower().strip(",.;:?! "))
            pred = d.get("predicate")
            # WAVE 3 POLICY 2 -- predicate/content for INSTRUCTIONS: a STRICT
            # ENRICHMENT cutover, zero regression risk. `pred` (the OLD
            # leading-verb parse) is None on this corpus only in degenerate
            # cases (an empty frame); when it IS None for an instruction turn,
            # read the shadow read's OWN predication back (already recorded
            # on this Message by `_shadow_read_turn`, which runs before this
            # method in `converse()`) instead of leaving the turn without a
            # predicate/content at all. When `pred` IS present, this is
            # BYTE-IDENTICAL to pre-Wave-3 -- the old value always wins, per
            # the fixture parity gate (documented in
            # docs/comprehension_decision_ledger.md). shadow_read OFF (or a
            # shadow_error) leaves shadow_predicate/shadow_focus unset ->
            # None -> this enrichment branch is a no-op, so shadow-off stays
            # byte-identical to today.
            if pred is not None:
                self.inner.set_attr(mid, "comp_predicate",
                                    str(pred).lower().strip(",.;:?!"))
            elif getattr(comp, "kind", None) == "instruction":
                _shadow_pred = self.s.node(mid)["attrs"].get("shadow_predicate")
                if _shadow_pred:
                    self.inner.set_attr(mid, "comp_predicate",
                                        str(_shadow_pred).lower().strip(",.;:?!"))
                    self.inner.set_attr(mid, "comp_predicate_source", "shadow_enrichment")
            if getattr(comp, "kind", None) == "instruction":
                if pred is not None:
                    self.inner.set_attr(mid, "comp_content",
                                        self._instruction_content(getattr(comp, "raw", ""), comp))
                else:
                    # OLD predicate absent -- old comp_content would have been
                    # nothing but the instruction's OWN raw text (no argument
                    # extraction possible without a predicate). Prefer the
                    # shadow read's own argument span (shadow_focus) when it
                    # exists; otherwise fall back to the unchanged old path.
                    _shadow_focus = self.s.node(mid)["attrs"].get("shadow_focus")
                    if _shadow_focus:
                        self.inner.set_attr(mid, "comp_content", str(_shadow_focus))
                        self.inner.set_attr(mid, "comp_content_source", "shadow_enrichment")
                    else:
                        self.inner.set_attr(mid, "comp_content",
                                            self._instruction_content(getattr(comp, "raw", ""), comp))
            # Relation parse facts for graph routing rules (capability / topic /
            # imagine) — mechanical read only, never a routing decision here.
            rel = getattr(comp, "relation", None) or {}
            focus = rel.get("focus")
            if focus is not None:
                self.inner.set_attr(mid, "comp_relation_focus", str(focus))
            pred_el = rel.get("predicate")
            if pred_el is not None:
                self.inner.set_attr(mid, "comp_verb",
                                    str(pred_el.get("surface", "")).lower().strip(",.;:?!"))
            raw = getattr(comp, "raw", "") or ""
            hypo = self._hypothetical_assumption(getattr(comp, "frame", None) or {}, raw)
            if hypo:
                self.inner.set_attr(mid, "comp_hypothetical", str(hypo))
            # TOPIC + FOLLOW-UP parse facts for the graph's routing/tracking rules
            # (seeds/conversation_topic_route.json + conversation_topic_tracking.json).
            # Mechanical parse read ONLY -- WHICH goal to mint (route a reflexive
            # question to its external topic / resolve an anaphor to the tracked
            # topic / shift to a new elliptical topic) is the rules' decision, never
            # here. `_topic_facts` reads the FULL contiguous noun phrase (multi-word,
            # e.g. "three body problem", not just the head "problem") off the parsed
            # frame, and flags an anaphoric ("... about IT") or elliptical (verbless
            # "and the three body problem?") follow-up. A missing marker reads as
            # None in the DSL, so a rule simply never fires.
            facts = self._topic_facts(comp)
            if path == "honest_self":
                topic = facts.get("topic") or d.get("verb")
                if topic:
                    self.inner.set_attr(mid, "self_account_topic", str(topic))
                    self.inner.set_attr(mid, "self_account_unresolved", 1.0)
            if rel.get("object") is not None and facts.get("topic"):
                self.inner.set_attr(mid, "comp_object_np", str(facts["topic"]))
            # ATTACHMENT parse facts — when the agent holds a current upload,
            # mark follow-up questions that refer to it so graph rules can route
            # to Goal{answer_attachment} instead of the honest floor / wiki table.
            _att_doc = self._current_attachment_doc()
            _attachment_routed = False
            if (_att_doc and getattr(comp, "kind", None) in ("question", "instruction")
                    and self._attachment_question_refs(comp, raw)):
                self.inner.set_attr(mid, "attachment_pending", 1.0)
                _attachment_routed = True
                self.refresh_upload_vision_if_needed(_att_doc)
            if (_att_doc and getattr(comp, "kind", None) in ("question", "instruction")
                    and self._text_decode_question_refs(comp, raw)):
                self.inner.set_attr(mid, "text_decode_pending", 1.0)
                self.inner.set_attr(mid, "attachment_pending", 1.0)
                self.refresh_upload_vision_if_needed(_att_doc)
            # DELIVERABLE 3 precedence (mechanical reconciliation of the parse
            # outputs, NOT a new decision): the front end (comprehend_text) may
            # have already classified this turn as a self/meta query
            # (comp.dispatch["path"] == "meta"). When it did AND the topic the
            # parser extracted is itself SELF-referential (its head is a self-word
            # like 'your'/'you' -- e.g. "what gaps do you have in your
            # knowledge"), DEFER to that classification: do not write comp_topic /
            # topic_pending, so the turn stays on the self/meta path (where the
            # gap-surfacing reader a parallel agent wires lives) instead of being
            # hijacked into grounding a self-word. A genuine EXTERNAL topic under
            # the same meta dispatch ("what do you know about the moon") has a
            # non-self topic head, so it is unaffected and still routes.
            _path = (getattr(comp, "dispatch", None) or {}).get("path")
            _topic = facts.get("topic")
            _topic_head = _topic.split()[0] if _topic else None
            _defer_to_meta = (_path == "meta" and _topic_head in self._SELF_WORDS)
            if facts.get("anaphor") and getattr(comp, "kind", None) in ("question", "instruction"):
                # "tell me more about it" / "how big is it" / "what about its mass"
                # -> resolve `it`/`that`/`they` to the CURRENT tracked topic. The
                # tracking rule reads agent -current_topic-> node; with no tracked
                # topic no rule fires and the honest path handles the turn.
                self.inner.set_attr(mid, "comp_anaphor", 1.0)
            elif facts.get("topic") and not _defer_to_meta:
                topic = facts["topic"]
                # Reflexive self-faculty questions (honest_self / held self_process)
                # are NOT external-topic routes. Do NOT block when comprehend_text
                # misclassified a turn (e.g. self_identity) but the parse still carries
                # a genuine external topic ('what do you know about the moon').
                _self_paths = frozenset({"honest_self"})
                _dispatch = getattr(comp, "dispatch", None) or {}
                _meta = str(_dispatch.get("meta_target") or "")
                _on_self_faculty = (
                    _path in _self_paths
                    or (_path == "meta" and _meta == "self_process")
                )
                route_topic = (
                    not _on_self_faculty
                    and getattr(comp, "kind", None) == "question"
                    and not hypo
                    and not _attachment_routed
                    and facts.get("topic") not in self._ATTACHMENT_REF_WORDS
                    and not (
                        _path == "meta"
                        and str(_dispatch.get("meta_target") or "") == "self_kind"
                    )
                    and (
                        getattr(comp, "reflexive", False)
                        or facts.get("composition")
                    )
                )
                if route_topic:
                    # Reflexive external-topic route ("what do you know about the
                    # moon") OR a composition ask ("what is the moon made of?").
                    # `topic_pending` is the marker route_question_to_topic matches.
                    self.inner.set_attr(mid, "comp_topic", topic)
                    self.inner.set_attr(mid, "topic_pending", 1.0)
                    if facts.get("aspect"):
                        self.inner.set_attr(mid, "comp_aspect", str(facts["aspect"]))
                elif facts.get("elliptical"):
                    # an elliptical topic shift ("and the three body problem?",
                    # "what about volcanoes?") -- a verbless topic fragment. The
                    # tracking rule shifts the current topic to it, gated on already
                    # being in an ongoing topic conversation (agent -current_topic->).
                    self.inner.set_attr(mid, "comp_topic", topic)
                    self.inner.set_attr(mid, "topic_followup", 1.0)
            elif (path == "table" and d.get("table_kind") == "know"
                  and getattr(comp, "kind", None) == "question"
                  and not hypo and not _attachment_routed and not _defer_to_meta):
                # KNOW-table questions ("what is an LLM?") carry know_concept on
                # the parse spec — mechanical topic write for route_question_to_topic.
                spec = d.get("spec")
                kc = ""
                if spec is not None:
                    kc = getattr(spec, "know_concept", None) or (
                        spec.get("know_concept") if isinstance(spec, dict) else "")
                kc = str(kc or "").strip()
                if kc and kc.lower() not in self._SELF_WORDS:
                    self.inner.set_attr(mid, "comp_topic", kc.lower())
                    self.inner.set_attr(mid, "topic_pending", 1.0)
            elif (getattr(comp, "kind", None) == "question"
                  and not facts.get("topic") and not facts.get("anaphor")
                  and not hypo and not _attachment_routed and not _defer_to_meta
                  and not (path in {"honest_self"}
                          or (path == "meta" and str(meta or "") == "self_process"))):
                # WAVE 3 POLICY 3 -- topic ENRICHMENT ONLY: the old NP-span
                # parse (`_topic_facts`, above) found NO topic nominal at all
                # for this question, and nothing else (anaphor / table-know /
                # a self-faculty reflexive reply -- the SAME `honest_self` /
                # meta+self_process exclusion the sibling `elif facts.get(
                # "topic")` branch above applies as `_on_self_faculty`, e.g.
                # "How does your collapse function work?" is answered by the
                # held SelfProcess account and must NOT also mint a spurious
                # external Goal{answer_topic, concept:'work'} — caught live
                # during this wave's own verification) claimed the turn
                # either -- comp_topic is about to stay unset, same as today.
                # Read the shadow read's OWN
                # `shadow_focus` (already recorded on this Message by
                # `_shadow_read_turn`, which runs before comprehend_text in
                # `converse()`) back, but ONLY when it is a single clean
                # token: shadow_focus is a HEAD-only read (the divergence
                # corpus's documented span-grain gap -- "problem" for "three
                # body problem"), and a head-only topic beats no topic only
                # when it IS the whole span; this wave does not build multi-
                # word NP-span recovery off the shadow SentenceParse, so a
                # multi-word shadow_focus is left alone rather than routed on
                # a truncated topic (the mission's own documented fallback).
                # Existing comp_topic-bearing rows are UNCHANGED (this branch
                # only reaches when the old parse wrote nothing); shadow_read
                # OFF leaves shadow_focus unset -> None -> no-op, byte-
                # identical to today.
                _sf = self.s.node(mid)["attrs"].get("shadow_focus")
                if _sf:
                    _sf = str(_sf).strip().lower()
                    if (_sf and " " not in _sf
                            and _sf not in self._SELF_WORDS
                            and _sf not in self._ANAPHOR_PRONOUNS
                            and _sf not in self._ANAPHOR_POSSESSIVES
                            and _sf not in self._TOPIC_ARTICLE_WORDS):
                        self.inner.set_attr(mid, "comp_topic", _sf)
                        self.inner.set_attr(mid, "topic_pending", 1.0)
                        self.inner.set_attr(mid, "comp_topic_source", "shadow_enrichment")
        except Exception:  # noqa: BLE001 -- a write hiccup just leaves the Python fallback in charge
            pass

    # Second-person / demonstrative words the topic must NOT be (those make the
    # question genuinely self-referential -> leave it to the self/meta path).
    _SELF_WORDS = frozenset({
        "you", "your", "yourself", "yourselves", "yours",
        "me", "my", "mine", "myself", "i", "it", "this", "that", "we", "us"})
    _TOPIC_ARTICLES = ("the ", "a ", "an ")
    # Anaphoric references that resolve to the conversation's CURRENT topic (a
    # follow-up "tell me more about IT / THAT / THEY"). Possessives ("its mass")
    # are treated the same -- the tracking rule resolves them to the tracked topic.
    _ANAPHOR_PRONOUNS = frozenset({"it", "that", "they", "them", "this",
                                   "these", "those"})
    _ANAPHOR_POSSESSIVES = frozenset({"its", "their", "his", "her", "theirs"})
    _TOPIC_ARTICLE_WORDS = frozenset({"the", "a", "an"})
    # Leading DETERMINERS to strip from a topic nominal to get its canonical head
    # ("your collapse function" -> "collapse function") -- the same morphosyntactic
    # normalisation as the article strip, NOT a routing decision (the self-vs-
    # external routing is the graph rule's possessive guard, which reads mentions).
    _TOPIC_DETERMINERS = frozenset({"the", "a", "an", "your", "yours",
                                    "my", "mine", "our", "ours"})
    # Upload-reference words/phrases for attachment follow-up routing (mechanical
    # parse read only — WHICH goal to mint is the graph rule's job).
    _ATTACHMENT_REF_WORDS = frozenset({
        "image", "picture", "photo", "upload", "file", "attachment", "document"})
    _ATTACHMENT_PHRASES = (
        "the image", "this image", "that image", "in the image", "in it",
        "the picture", "the photo", "the file", "the upload", "uploaded file",
        "uploaded image", "what's in", "what is in",
        "about it", "about this", "tell me about it",
        "what can you tell me", "i've uploaded", "i uploaded", "[uploaded:",
        "[file:",
    )
    _TEXT_DECODE_PHRASES = (
        "what does the text say", "what is the text", "what is written",
        "read the text", "read the writing", "decode the text",
        "what does it say", "what do the words say", "transcribe",
        "what is written in", "what text is",
    )

    def _current_attachment_doc(self):
        """The UploadedDocument node agent -current_attachment-> points at, or None."""
        try:
            for doc in self.inner.neighbours(self.agent, "current_attachment"):
                if self.inner.has_node(doc):
                    return doc
        except Exception:  # noqa: BLE001
            pass
        return None

    def _text_decode_question_refs(self, comp, raw: str) -> bool:
        """Mechanical read: does this turn ask to READ/DECODE text in the upload?"""
        low = (raw or "").lower()
        if any(p in low for p in self._TEXT_DECODE_PHRASES):
            return True
        facts = self._topic_facts(comp)
        topic = str(facts.get("topic") or "").lower()
        if topic in ("text", "writing", "words", "lettering", "caption"):
            return True
        if "text" in low and any(w in low for w in ("say", "read", "written", "decode")):
            return True
        return False

    def _attachment_question_refs(self, comp, raw: str) -> bool:
        """Mechanical read: does this turn refer to the held upload?"""
        low = (raw or "").lower()
        if any(p in low for p in self._ATTACHMENT_PHRASES):
            return True
        if "upload" in low and "?" in low:
            return True
        facts = self._topic_facts(comp)
        if facts.get("topic") in self._ATTACHMENT_REF_WORDS:
            return True
        d = getattr(comp, "dispatch", None) or {}
        if d.get("path") == "table" and d.get("table_kind") == "know":
            spec = d.get("spec")
            kc = ""
            if spec is not None:
                kc = getattr(spec, "know_concept", None) or (
                    spec.get("know_concept") if isinstance(spec, dict) else "")
            kc = str(kc).lower()
            if any(w in kc for w in ("image", "picture", "photo", " in it", "upload", "file")):
                return True
        if getattr(comp, "kind", None) == "instruction":
            obj = d.get("object")
            if obj and str(obj).lower() in self._ATTACHMENT_REF_WORDS:
                return True
        return False

    def _set_current_attachment(self, doc_id) -> None:
        """Record the conversation's CURRENT upload (agent -current_attachment-> doc)."""
        if doc_id is None or not self.inner.has_node(doc_id):
            return
        try:
            for old in list(self.inner.neighbours(self.agent, "current_attachment")):
                self.inner.remove_edge(self.agent, "current_attachment", old)
            self.inner.add_edge_unchecked(self.agent, "current_attachment", doc_id)
        except Exception:  # noqa: BLE001 -- tracking is best-effort
            pass

    @staticmethod
    def _np_member(e):
        """True iff a parsed frame element belongs to a contiguous noun phrase:
        a content word other than a verb (noun / adjective / number), a
        determiner, or an unknown-by-position gap (an OOV proper token). Pure
        parse read -- lets the multi-word topic span emerge from the frame."""
        role, pos = e.get("role"), e.get("pos")
        if role == "content" and pos != "verb":
            return True
        if role == "function" and pos == "determiner":
            return True
        if role == "gap":
            return True
        return False

    def _np_span(self, els, head):
        """The maximal CONTIGUOUS noun-phrase run (lowercased surfaces) of the
        frame `els` that contains element `head` -- head plus its adjacent
        compounds/modifiers ("the three body problem", "arc agi v3 ls20"). The
        full topic phrase, not just the composer's single head nominal."""
        i = next((j for j, e in enumerate(els) if e is head), None)
        if i is None:
            s = str(head.get("surface", "")).lower().strip(",.;:?! ")
            return [s] if s else []
        lo = hi = i
        while lo - 1 >= 0 and self._np_member(els[lo - 1]):
            lo -= 1
        while hi + 1 < len(els) and self._np_member(els[hi + 1]):
            hi += 1
        out = []
        for e in els[lo:hi + 1]:
            s = str(e.get("surface", "")).lower().strip(",.;:?! ")
            if s:
                out.append(s)
        return out

    def _topic_facts(self, comp):
        """Mechanical parse read of a turn's TOPIC structure for the routing /
        tracking rules: {topic, anaphor, elliptical}.

          • `topic`     -- the FULL contiguous noun phrase (multi-word, article-
            stripped, lowercased) the question/fragment is about, or None. Taken
            from the composed relation's OBJECT/OBLIQUE head (never the self-word
            subject) expanded to its whole NP, else the trailing NP of a verbless
            fragment.
          • `anaphor`   -- the topic reference is a bare pronoun/possessive
            ("... about IT", "its mass") to resolve to the tracked current topic.
          • `elliptical`-- a verbless topic fragment ("and the three body
            problem?", "what about volcanoes?"), i.e. a topic shift.

        Never a decision -- the graph rules decide what to do with these facts."""
        out = {"topic": None, "anaphor": False, "elliptical": False}
        frame = getattr(comp, "frame", None)
        els = (frame or {}).get("elements") or []
        if not els:
            return out
        rel = getattr(comp, "relation", None) or {}
        # Polar capability ("can/could you dance?") with no matrix object — the
        # question is about the agent's ability, not a noun buried in a conditional
        # ("if you had a body"). Skip topic extraction; graph rules read
        # comp_hypothetical / comp_verb instead.
        if rel.get("focus") == "polar":
            subj = str((rel.get("subject") or {}).get("surface", "")).lower().strip(",.;:?!")
            pred = rel.get("predicate") or {}
            if subj in self._SELF_WORDS:
                # "can you dance?" — capability polar with no external object.
                if rel.get("object") is None and rel.get("oblique") is None:
                    return out
                # "are you an LLM?" — copular self-classification, not a topic
                # route (the kind noun is what the agent is being ASKED whether it
                # is, not what the turn is about externally).
                if pred.get("pos") == "copula":
                    return out
        # "what is X made of?" — the SUBJECT nominal is the external topic; the
        # composition aspect (made_of) is a parse datum for routing/reply, not a
        # single mangled know-concept tail ("moon made of").
        pred = rel.get("predicate")
        surfaces = [
            str(e.get("surface", "")).lower().strip(",.;:?! ")
            for e in els
        ]
        # The sparse parser may leave the passive participle and its
        # preposition as explicit gaps while retaining only the copula as the
        # composed predicate.  Recover the same surface grammar mechanically:
        # ``what is [NP] made of``.  This is parse reconciliation, not a
        # routing decision.
        if "made" in surfaces:
            made_i = surfaces.index("made")
            if made_i + 1 < len(surfaces) and surfaces[made_i + 1] == "of":
                start = 1
                for i in range(made_i):
                    if surfaces[i] in ("is", "are", "was", "were"):
                        start = i + 1
                span = surfaces[start:made_i]
                while span and span[0] in self._TOPIC_DETERMINERS:
                    span = span[1:]
                phrase = " ".join(s for s in span if s).strip()
                if phrase and phrase not in self._SELF_WORDS:
                    out["topic"] = phrase
                    out["composition"] = True
                    out["aspect"] = "made_of"
                    return out
        if pred and str(pred.get("surface", "")).lower().strip(",.;:?! ") == "made":
            subj = rel.get("subject")
            if subj is not None:
                span = self._np_span(els, subj)
                while span and span[0] in self._TOPIC_DETERMINERS:
                    span = span[1:]
                phrase = " ".join(span).strip()
                if phrase and phrase not in self._SELF_WORDS:
                    out["topic"] = phrase
                    out["composition"] = True
                    out["aspect"] = "made_of"
                    return out
        # No governing verb/copula anywhere -> a verbless topic fragment.
        out["elliptical"] = not any(
            (e.get("role") == "content" and e.get("pos") == "verb") or
            (e.get("role") == "function" and e.get("pos") in ("copula", "auxiliary", "aux"))
            for e in els)
        # HEAD of the topic nominal: the oblique (after a preposition) or the
        # direct object of the composed relation; else the last NP-ish/pronoun
        # element of the frame (a verbless fragment has no composed relation).
        head = rel.get("oblique") or rel.get("object")
        # Embedded wh-clause nominal: "do you know what <X> is?" — compose_relation
        # puts the embedded predicate in rel["predicate"] when focus=thing; there is
        # no matrix object/oblique, so the picks above miss it. Run BEFORE the
        # reversed-pronoun fallback (which would otherwise grab "you").
        if head is None and rel.get("focus") == "thing":
            pred = rel.get("predicate")
            pred_surf = str((pred or {}).get("surface", "")).lower().strip(",.;:?! ")
            has_copula = any(
                e.get("role") == "function" and e.get("pos") == "copula"
                for e in els)
            has_know = any(
                (e.get("surface") or "").lower().strip(",.;:?!") == "know"
                and e.get("role") == "content"
                for e in els)
            if pred and has_copula and has_know and pred_surf \
                    and pred_surf not in self._SELF_WORDS:
                head = pred
        if head is None:
            for e in reversed(els):
                if self._np_member(e) or (
                        e.get("role") == "function" and e.get("pos") == "pronoun"):
                    head = e
                    break
        if head is None:
            return out
        hs = str(head.get("surface", "")).lower().strip(",.;:?! ")
        if head.get("role") == "function" and head.get("pos") == "pronoun" \
                and hs in self._ANAPHOR_PRONOUNS:
            out["anaphor"] = True
            return out
        span = self._np_span(els, head)
        if span and span[0] in self._ANAPHOR_POSSESSIVES:
            out["anaphor"] = True
            return out
        while span and span[0] in self._TOPIC_DETERMINERS:
            span = span[1:]
        phrase = " ".join(span).strip()
        if phrase and phrase not in self._SELF_WORDS:
            out["topic"] = phrase
        return out

    def _set_current_topic(self, name):
        """Mechanically record the conversation's CURRENT topic as a graph node
        (agent -current_topic-> CurrentTopic{name}), replacing any prior one, so
        the tracking rules can resolve follow-ups against it. Writing the tracked
        state is admissible adapter I/O; the follow-up ROUTING is the rule's job."""
        if not name:
            return
        try:
            for old in list(self.inner.neighbours(self.agent, "current_topic")):
                self.inner.remove_edge(self.agent, "current_topic", old)
                if self.inner.has_node(old):
                    self.inner.remove_node(old)
            ct = self.s.add_node("CurrentTopic", {"name": str(name)})
            self.inner.add_edge_unchecked(self.agent, "current_topic", ct)
        except Exception:  # noqa: BLE001 -- tracking is best-effort; a hiccup just skips it
            pass

    def _graph_reply_for(self, mid, skip_floor=False):
        """The graph-produced, text-bearing agent reply to this turn.

        When several rules mint replies in one fixpoint, the LAST one wins —
        later rules supersede weaker floors (e.g. gap-ack over honest_floor).
        `skip_floor=True` ignores replies the honest-floor rule marked
        `floor:1.0` — a mechanical read of the rule's own marker, used when a
        fulfilled topic/meta answer must not be shadowed by the bare floor."""
        last = None
        for r in self.agent_outbound_messages():
            a = self.s.node(r)["attrs"]
            if a.get("text") and mid in self.responds_to(r):
                if skip_floor and a.get("floor") == 1.0:
                    continue
                last = a["text"]
        return last

    def _record_self_account_gap(self, mid, comp):
        """MECHANICAL: record onto the inbound Message that the agent hit the
        honest self floor (understood the question is about ITSELF, holds no
        account of that faculty). Writes `self_account_unresolved=1.0` + a
        `self_account_topic` datum (the self-thing asked about: the parsed
        comp_topic if present, else the process verb). No decision -- the graph
        rule note_self_account_gap decides this is a gap and files it. Only
        records when there is a specific self-topic (a bare identity question
        like 'what are you' has none and is answered fine, so files nothing)."""
        try:
            topic = self.s.node(mid)["attrs"].get("comp_topic")
            if not topic:
                d = getattr(comp, "dispatch", None) or {}
                topic = d.get("verb")
            if topic:
                self.inner.set_attr(mid, "self_account_topic", str(topic))
                self.inner.set_attr(mid, "self_account_unresolved", 1.0)
        except Exception:  # noqa: BLE001 -- a write hiccup just skips the datum
            pass

    def _record_instruction_outcome(self, mid):
        """MECHANICAL outcome read-back for an instruction turn (the
        _answer_topic_reply / _record_self_account_gap outcome precedent):
        after the rule passes for this turn have run, record onto the inbound
        Message WHAT HAPPENED -- instruction_outcome='handled' iff some rule
        claimed the turn (the `comprehended` fixpoint marker every covering
        instruction rule sets) or minted a Goal comprehending it; else
        'unhandled'. A factual datum, never a decision: the DECISION that an
        unhandled instruction is a gap lives in the graph rule
        seeds/gap_awareness.json::note_unhandled_instruction_gap, which reads
        this attr, files the SelfConcern and mints the honest in-turn reply.
        Returns True iff an outcome was recorded (the caller then runs one
        more rule pass so the rules can see the datum this same turn)."""
        try:
            if not self.s.has_node(mid):
                return False
            attrs = self.s.node(mid)["attrs"]
            if attrs.get("comp_kind") != "instruction":
                return False
            handled = attrs.get("comprehended") == 1.0
            if not handled:
                for g in self.inner.neighbours(self.agent, "has_goal"):
                    if not self.inner.has_node(g):
                        continue
                    if mid in list(self.inner.neighbours(g, "comprehends")):
                        handled = True
                        break
            self.inner.set_attr(mid, "instruction_outcome",
                                "handled" if handled else "unhandled")
            return True
        except Exception:  # noqa: BLE001 -- a write hiccup just skips the datum
            return False

    def _record_interlocutor_correction(self, mid):
        """MECHANICAL datum (Wave: interlocutor-as-modeled-participant, task 3,
        corrections): does THIS turn carry a gap_awareness DEFICIENCY cue
        (cannot/fail/wrong/broken/...) that ALSO mentions a concept the
        addressee was already TOLD (`believed_concepts`, task 1)? Both facts
        are already graph-decided BEFORE this runs — the deficiency Concept
        class is `seeds/gap_awareness.json`'s (found by its own
        'deficiency cue:' description tag, never a re-hardcoded word list, so
        this reads the SAME vocabulary `note_reported_gap` matches against),
        and told-status is task 1's write. This only records that BOTH
        co-occurred: `contradicted_by_interlocutor` on the matching HeldAnswer
        + Concept, and on this turn's own attitude belief-world entry if one
        was minted (task 3's ingest, `_last_attitude_turn`). A factual
        co-occurrence write, never a decision — a future rule may consume it
        (not built here, per the wave's own 'don't over-build' scope)."""
        try:
            if not self.s.has_node(mid):
                return False
            ad = self._addressee()
            if ad is None:
                return False
            believed = self._believed(ad)
            if not believed:
                return False
            deficiency = False
            told_concept = None
            for mn in self.inner.neighbours(mid, "has_mention"):
                for cc in self.inner.neighbours(mn, "refers_to"):
                    if self.s.node(cc)["type"] != "Concept":
                        continue
                    at = self.s.node(cc)["attrs"]
                    if str(at.get("description") or "").startswith("deficiency cue"):
                        deficiency = True
                    name = at.get("name")
                    if name in believed:
                        told_concept = name
            if not (deficiency and told_concept):
                return False
            self.inner.set_attr(mid, "contradicted_by_interlocutor", told_concept)
            for ha in self.s.nodes("HeldAnswer"):
                if (self.s.node(ha)["attrs"].get("topic") or "").strip().lower() == str(told_concept).lower():
                    self.inner.set_attr(ha, "contradicted_by_interlocutor", True)
            cc_node = self._concept_by_name(told_concept)
            if cc_node is not None:
                self.inner.set_attr(cc_node, "contradicted_by_interlocutor", True)
            # TRACK RECORD (course correction 2026-07-11, task 3 refinement 2a):
            # a mechanical DATUM only -- a party's correction frequency, never
            # auto-applied to their self_report_reliability belief here (that
            # is `interlocutor_model.effective_reliability`'s job, reading this
            # counter fresh on its own n-weighted blend next time it runs; no
            # rule further consumes it this wave -- "ship the datum, leave the
            # updating minimal/honest", per the correction).
            prior_ct = int(self.s.node(ad)["attrs"].get("self_report_contradiction_count", 0) or 0)
            self.inner.set_attr(ad, "self_report_contradiction_count", prior_ct + 1)
            # REVISE the LEVEL-2 MODEL (never the LEVEL-1 Assertion, which
            # stays untouched): find THIS PARTY's own belief/want entries
            # whose referent/content matches the contradicted concept —a
            # graph QUERY by identity (belief_holder/idx_protagonist ==
            # this party's name), not `_last_attitude_turn` (turn-scoped;
            # reset every `_shadow_read_turn` call, so it no longer points at
            # the right entry once even one turn has passed since the
            # self-report). A direct contradiction halves confidence
            # (floored), so a revised model is visibly less trusted without
            # touching what was actually SAID.
            party_name = self.s.node(ad)["attrs"].get("name")
            if party_name:
                for n in self.s.nodes("SmEntity"):
                    at = self.s.node(n)["attrs"]
                    if (at.get("nested") and at.get("belief_holder") == party_name
                            and str(at.get("referent") or "").lower() == str(told_concept).lower()):
                        cur_conf = float(at.get("confidence", 0.5) or 0.5)
                        revised = max(0.05, cur_conf * 0.5)
                        self.inner.set_attr(n, "confidence", revised)
                        self.inner.set_attr(n, "revision_count",
                                            int(at.get("revision_count", 0) or 0) + 1)
                        self.inner.set_attr(n, "contradicted_by_interlocutor", True)
            return True
        except Exception:  # noqa: BLE001 -- a write hiccup just skips the datum
            return False

    @staticmethod
    def _hypothetical_assumption(frame, raw: str = ""):
        """Mechanical parse read of 'if you had X' on a polar question."""
        import re
        text = raw or " ".join((e.get("surface") or "") for e in (frame or {}).get("elements") or [])
        m = re.search(
            r"\bif\s+(?:you|i)\s+had\s+(?:a |an |the )?(.+?)(?:\?|$|,|\s+would|\s+could|\s+can)",
            text, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip("?.,;")
        return None

    def _answer_topic_reply(self, mid):
        """Render the reply to a question the graph ROUTED to an external topic
        (a Goal{kind:answer_topic} minted for `mid` by route_question_to_topic).
        Mechanical: read the graph's routing decision (the goal + its concept),
        answer_about(concept), and on a MISS ground the topic through the agent's
        OWN self-teacher chain (ground_unknowns -> dictionary/wiki, which memoises
        under `taught_<form>` -- exactly what answer_about reads back) then
        re-answer. The agent fixing its own knowledge gap. Returns the reply text,
        or None if no answer_topic goal was minted for this turn (the Python path
        then handles it). No decision here -- the route rule already decided.

        DOUBLE-REPLY GUARD (mechanical dedup, reading the rules' own marker):
        when a topic-reply RULE already claimed this turn (topic_replied on the
        inbound -- e.g. reply_topic_from_held_answer answered from a HeldAnswer
        in the first fixpoint), this fulfiller stands down; conversely, when the
        fulfiller answers it sets the SAME marker so the seeded topic rules
        (which read it) never mint a second reply. The rule path is thus the
        first claimant and this fulfiller the in-turn backstop that can also
        self-heal via grounding."""
        if self.s.has_node(mid) and \
                self.s.node(mid)["attrs"].get("topic_replied") == 1.0:
            return None
        concept = None
        goal = None
        for g in self.inner.neighbours(self.agent, "has_goal"):
            if not self.inner.has_node(g):
                continue
            ga = self.s.node(g)["attrs"]
            if ga.get("kind") != "answer_topic":
                continue
            if mid not in list(self.inner.neighbours(g, "comprehends")):
                continue
            concept = ga.get("concept")
            goal = g
            break
        if not concept:
            return None
        ma = self.s.node(mid)["attrs"] if self.s.has_node(mid) else {}
        aspect = ma.get("comp_aspect")
        answer_key = (f"composition of {concept}" if aspect == "made_of" else str(concept))
        # Track the conversation's current topic as graph state so anaphoric /
        # elliptical follow-ups can resolve against it (the ROUTING of those
        # follow-ups is the tracking rules' job; this is just the mechanical write).
        self._set_current_topic(concept)
        ans = self.answer_about(answer_key)
        if ans is None and aspect:
            try:
                from domains.topic_grounding import ground_topic_aspect as _ground_aspect
            except ImportError:
                _ground_aspect = None
            if _ground_aspect is not None:
                try:
                    _ground_aspect(self, concept, str(aspect))
                except Exception:  # noqa: BLE001
                    pass
                ans = self.answer_about(answer_key)
        if ans is None and not aspect:
            # SELF-HEAL: the agent doesn't hold this topic -> learn it. PREFER
            # PHRASE grounding (a multi-word topic like "three body problem" must
            # be grounded WHOLE, not shredded per word) via domains.topic_grounding
            # -- imported lazily so this works whether or not that module has
            # landed yet; FALL BACK to the per-word ground_unknowns teacher loop
            # when it is absent (or fails). Both memoise under `taught_<form>`,
            # exactly what answer_about's fallback reads.
            try:
                from domains.topic_grounding import ground_topic as _ground_topic
            except ImportError:
                _ground_topic = None
            if _ground_topic is not None:
                try:
                    _ground_topic(self, answer_key)
                except Exception:  # noqa: BLE001 -- phrase grounder failed -> per-word fallback
                    try:
                        self.ground_unknowns(str(answer_key))
                    except Exception:  # noqa: BLE001 -- no teacher -> honest miss below
                        pass
            else:
                try:
                    self.ground_unknowns(str(answer_key))
                except Exception:  # noqa: BLE001 -- no teacher / teacher failure -> honest miss below
                    pass
            ans = self.answer_about(answer_key)
        # MECHANICAL OUTCOME RECORDING (a datum, not a decision): record on the
        # answer_topic Goal WHAT HAPPENED -- did the answer/ground attempt above
        # produce an answer or not. This is recording a factual outcome, no
        # behaviour. The DECISION that an unresolved topic IS a gap lives in the
        # graph rule seeds/gap_awareness.json::note_unresolved_topic_gap, which
        # matches on this outcome and files the SelfConcern.
        if goal is not None and self.inner.has_node(goal):
            try:
                self.inner.set_attr(goal, "outcome",
                                    "resolved" if ans is not None else "unresolved")
            except Exception:  # noqa: BLE001 -- a write hiccup just skips the datum
                pass
        # Claim the turn with the rules' own marker so the seeded topic rules
        # don't mint a second reply for it (see the double-reply guard above).
        try:
            self.inner.set_attr(mid, "topic_replied", 1.0)
        except Exception:  # noqa: BLE001
            pass
        if ans is not None:
            # Outcome bookkeeping: the goal these pending search/ground
            # requests served is resolved -- record that so the search
            # dispatch doesn't re-fetch a topic the agent just answered.
            try:
                for ntype in ("SearchRequest", "GroundRequest"):
                    for req in self.s.nodes(ntype):
                        ra = self.s.node(req)["attrs"]
                        if (ra.get("query") == str(concept)
                                and ra.get("status") == "requested"):
                            self.inner.set_attr(req, "status", "superseded")
            except Exception:  # noqa: BLE001
                pass
            return ans
        # Grounding could not reach this topic (no teacher, or nothing found):
        # an HONEST reply that also records the gap the agent has now tried to
        # close -- never the self-identity non-sequitur the misroute produced.
        return (f"I don't hold anything about \u201c{concept}\u201d yet, and I "
                f"couldn't find it through the sources I have. Tell me about it "
                f"and I'll remember.")

    def _answer_interlocutor_meta_reply(self, mid):
        """R6 (blind-spot closure, bare first-person routing): the SAME
        precedent as `_answer_topic_reply`, but the graph ROUTED this turn to
        the INTERLOCUTOR reflective reader instead of a world topic (a
        Goal{kind:answer_interlocutor_meta} minted for `mid` by
        seeds/first_person_routing.json::route_first_person_question_to_
        interlocutor -- fired when a Mention on this turn resolves, via the
        held `rule_first_person_resolves_to_speaker` chain, to the SAME
        speaker the "know" dispatch's own topic nominal names, e.g. "Who am
        I?" / "What do I want?"). The routing DECISION is entirely the
        rule's (a graph-resolved Mention -refers_to-> speaker fact, never a
        Python pronoun list); this only renders it, via the SAME reflect() +
        _surface_self_state backend every other meta reader uses (the
        interlocutor_model faculty already answers "who are you" /
        "what have you asked me" -- this just lets a BARE first-person
        question reach it instead of the honest floor / a bogus 'I don't
        hold that' world-concept lookup on the pronoun itself). Returns None
        when no such goal was minted for this turn (the general path then
        handles it, byte-unchanged)."""
        goal = None
        for g in self.inner.neighbours(self.agent, "has_goal"):
            if not self.inner.has_node(g):
                continue
            ga = self.s.node(g)["attrs"]
            if ga.get("kind") != "answer_interlocutor_meta":
                continue
            if mid not in list(self.inner.neighbours(g, "comprehends")):
                continue
            goal = g
            break
        if goal is None:
            return None
        from domains import reflective_faculty as _rf
        state = _rf.reflect("interlocutor_model", None, self.s)
        return self._surface_self_state(state)

    def _write_function_reply(self, mid):
        """CODE-3 (writing is reading reversed) — the "sanctioned surface"
        an NL code-write request flows through. `code_writing.
        looks_like_write_request` is the thin I/O-boundary classifier
        CLAUDE.md's own carve-out sanctions (a write-verb word + a
        function/code word — the smallest graph token an opaque NL string
        converts to; no Rust primitive could cheaply do this); WHICH
        construction the request wants is entirely `compose_function_
        from_request`'s ShapeDecode call (graph-native, the SAME Rust Term
        `code_reading.py` uses to recognise a function's compute-core) —
        this method only reads the Message's own text (mechanical query,
        the same status `_answer_topic_reply` gives its goal-concept read)
        and renders the decode's verdict (or its honest abstain) into the
        turn's reply. Returns None for any message that doesn't classify
        as a write request at all (the general path then handles it,
        byte-unchanged) — never claims a turn ShapeDecode never touched."""
        text = self.s.node(mid)["attrs"].get("text") if self.s.has_node(mid) else None
        if not text:
            return None
        from domains import code_writing as _cw
        if not _cw.looks_like_write_request(text, self):
            return None
        result = _cw.write_function_from_request(self, text)
        # CODE-4: MECHANICAL outcome datum (the _record_instruction_outcome /
        # _answer_topic_reply precedent) -- a factual record of what happened
        # to this write request, never a decision. seeds/code_write_gap.json's
        # note_code_write_gap rule reads code_write_outcome=='unhandled' and
        # DECIDES an out-of-vocabulary write request is a capability gap,
        # filing SelfConcern{kind:'code_write'} (content-deduped, mint-once).
        # The rule fires in the SAME turn's next comprehend() pass below (the
        # unconditional one a few lines down in _turn_reply), just like the
        # instruction-gap datum does.
        # CODE-4 (item 5): VALIDATE-BY-RUNNING gates the reply. The written
        # source is exec'd in isolation on the request's own sample inputs and
        # compared against the agent's OWN model answer (the native Term
        # evaluation `write_function_from_request` already produced) -- the
        # read_method_draft.validate_by_running precedent at function grain.
        # Agreement is a boolean comparison of two already-computed values;
        # on disagreement the function is NOT handed over (honest reply +
        # outcome datum 'unhandled', so the gap rule files it).
        validate = None
        if result.get("ok") and result.get("sample_ok"):
            from domains import code_write_growth as _cwg
            validate = _cwg.validate_written_function_by_running(
                result["source"], "generated_function", result["args"],
                result["sample_env"], result["sample_result"])
        handled = bool(result.get("ok")) and (validate is None or validate["agree"])
        try:
            if self.s.has_node(mid):
                self.inner.set_attr(mid, "code_write_request", text)
                self.inner.set_attr(mid, "code_write_outcome",
                                    "handled" if handled else "unhandled")
        except Exception:  # noqa: BLE001 -- a write hiccup just skips the datum
            pass
        if not result.get("ok"):
            return ("I don't hold a shape for that yet (%s)."
                   % result.get("reason", "unrecognised request"))
        if validate is not None and not validate["agree"]:
            return ("I wrote a function for that, but it disagrees with my own "
                   "prediction (%s), so I won't hand it over. I've noted this "
                   "as a gap." % validate.get("reason", "exec vs model mismatch"))
        return "Here is the function:\n\n%s" % result["source"]

    def _code_example_reply(self, mid):
        """CODE-4 -- the TEACH-BY-EXAMPLE sanctioned surface: a chat message
        that IS a runnable Python function definition (`code_write_growth.
        looks_like_code_example`, the same thin I/O-boundary status as
        `looks_like_write_request`) is READ by the agent's own code-reading
        faculty and TAUGHT as a new write shape
        (`teach_write_shape_from_example`: read -> validate-by-running ->
        teach() into code_write_constructions -- adoption = teach(), the cue
        adoption precedent). The trigger tokens come from the MOST RECENT
        pending code_write gap's own request content (a mechanical recency
        read, the current-topic precedent), so the taught shape answers the
        request that filed the gap. Reading closes the write gap. Returns
        None for any message that isn't a function definition (the general
        path handles it, byte-unchanged); an unreadable/unvalidatable
        example gets an honest refusal, never a fabricated shape."""
        text = self.s.node(mid)["attrs"].get("text") if self.s.has_node(mid) else None
        if not text:
            return None
        from domains import code_write_growth as _cwg
        if not _cwg.looks_like_code_example(text):
            return None
        gaps = _cwg.pending_code_write_gaps(self)
        request_text = gaps[-1]["content"] if gaps else None
        result = _cwg.teach_write_shape_from_example(self, text,
                                                     request_text=request_text)
        if not result.get("ok"):
            return ("I read that function but could not take it as a lesson "
                   "(%s)." % result.get("reason", "unreadable example"))
        reply = ("Thank you -- I read that function and learned the shape %r "
                "(triggers: %s)." % (result["shape"],
                                     ", ".join(result["tokens"]).lower()))
        if request_text:
            answered = self._write_function_reply_for_text(request_text)
            if answered:
                reply += ("\n\nYour earlier request (%r) now works:\n\n%s"
                          % (request_text,
                             answered.split("Here is the function:\n\n", 1)[-1]))
        return reply

    def _write_function_reply_for_text(self, text):
        """Mechanical re-run of the write-from-request render for a PRIOR
        request's text (no Message node involved -- no outcome datum, no gap
        re-filing): classify, compose, render. Returns the reply string or
        None. Used by `_code_example_reply` to show the just-taught shape
        answering the request that filed the gap."""
        from domains import code_writing as _cw
        if not _cw.looks_like_write_request(text, self):
            return None
        result = _cw.write_function_from_request(self, text)
        if not result.get("ok"):
            return None
        return "Here is the function:\n\n%s" % result["source"]

    def _meta_reader_reply(self, comp):
        """READBACK of the front end's already-made META routing decision: when
        the held question_targets TABLE resolved this turn to a reflective
        reader (a fastpath spec `kind=='meta'` with a meta_target the reflective
        dispatch holds — e.g. 'what gaps do you have' -> self_gaps), render that
        reader's answer — the same reflect() + _surface_self_state backend
        answer_question uses for the same spec. The ROUTING decision was made
        by the question_targets data; this only renders it. Returns None when
        the turn was not table-meta-routed. Deliberately NOT the general
        `dispatch.path=='meta'` parse (e.g. 'what are you?'): those turns
        belong to the graph's own self-reply rules (conversation_self_reply),
        which self-improvement experiments must be able to ablate — a Python
        readback there would shadow the rules and defeat the ablation delta."""
        if comp is None or not getattr(comp, "fastpath", False):
            return None
        try:
            from domains import reflective_faculty as _rf
            spec = getattr(comp, "table_spec", None)
            mt = getattr(spec, "meta_target", None)
            if getattr(spec, "kind", None) == "meta" and mt in _rf._DISPATCH:
                state = _rf.reflect(mt, getattr(spec, "meta_arg", None), self.s)
                return self._surface_self_state(state)
        except Exception:  # noqa: BLE001 -- a render hiccup leaves the graph paths in charge
            return None
        return None

    def _shadow_read_turn(self, mid, text):
        """SHADOW READ (Wave 2, Deep-Reader): a LIGHT deep-read of THIS turn's
        text on the LIVE substrate, gated by `self.shadow_read` (opt-in — see
        `__init__`). Purely additive: comp_* stays authoritative for the
        reply; this never affects `converse`'s read-off. Mechanical I/O only:

          1. ARM the deictic centre from the turn's own provenance — the
             Message's `sent_by` Interlocutor is the SPEAKER, the agent's own
             `substrate_name` is the ADDRESSEE (`coref_entities.
             arm_deictic_centre`) — so 'you'/'I' in the turn ground to the
             REAL live participants, not an ungrounded SmEntity.
          2. RUN the conversational-aperture reading flow (Wave 2 Task 1:
             `register_source.conversational_aperture` — 'spine' stage only)
             on THIS substrate, via `reading_drive.run_reading_flow` (the
             same entry point a persistent WorldAdapter already uses safely,
             per test_reading_persistent_substrate_migrated).
          3. LINK the Message to the flow's own SentenceParse node(s)
             (`comprehended_as`) — found by the flow's own identity, never a
             global scan.
          4. RECORD the flow's own outputs onto the Message as `shadow_*`
             attrs — a mechanical readback, no decision: `shadow_predicate`
             is the resolved textbase's own leading predicate;
             `shadow_speech_act`/`shadow_focus` are `reading_collapse.
             read_clause`'s own additive turn-grain fields (Wave 1B),
             called `write=False, learn=False` so the shadow read mutates
             nothing beyond what the flow itself already mints.

        Any failure is swallowed (`shadow_error` recorded) — a shadow read
        must NEVER break or change a real turn."""
        import time as _time
        t0 = _time.perf_counter()
        try:
            # Ensure the interlocutor-modeling seeds (shape codebook +
            # creator-trust rule) are installed BEFORE the attitude-ingest
            # block below needs them — idempotent (sets a flag, see its own
            # docstring), so this costs nothing on turn 2+.
            self._ensure_comprehension_seeds()
            from domains import coref_entities as ce
            from domains import reading_drive as rd
            from domains import register_source as rs
            from domains import reading_collapse as rc
            from domains import character_tom as ct_tom
            from domains import interlocutor_model as _im

            speaker_name = "user"
            for n in self.inner.neighbours(mid, "sent_by"):
                nm = self.s.node(n)["attrs"].get("name")
                if nm:
                    speaker_name = nm
                break
            # PARTY-NODE IDENTITY (bugfix, Wave: interlocutor-as-modeled-
            # participant, task 3): `receive_utterance`'s `sent_by` edge
            # resolves via `self._interlocutor(speaker="user")` — a
            # find-or-create keyed by the LITERAL string "user". The
            # `interlocutor_model.py` Party this turn's `_last_interlocutor_
            # turn` tracks STARTS as that same node but is RENAMED once the
            # party self-identifies ("I am Ada" sets its `name` attr to
            # "Ada") — after which `_interlocutor("user")` no longer finds
            # it (the name changed) and mints a SEPARATE, stale "user" node
            # instead. `speaker_name` above therefore silently reverts to
            # "user" the moment a party gives a name — verified live (a
            # self-report's belief_holder landed on a stray "user" SmEntity,
            # not the named party). Prefer the TRACKED PARTY's own `name`
            # attr (the source of truth this whole wave is built on) so
            # "I think X" attributes to the real party.
            party = None
            try:
                lit = getattr(self, "_last_interlocutor_turn", None)
                party = lit.get("party") if lit else None
            except Exception:  # noqa: BLE001
                party = None
            if party is not None:
                _party_name = self.s.node(party)["attrs"].get("name")
                if _party_name:
                    speaker_name = _party_name
                # TOM CAPACITY (Wave: interlocutor-as-modeled-participant,
                # task 3, 4th course correction: "realistically, some humans
                # barely have theory of mind"). A shape-prior-estimable,
                # per-party belief -- written every turn (mechanical, cheap)
                # so seeds/conversation_grice.json's reply_topic_repeat_known
                # guard can read it later in THIS SAME turn's rule pass.
                try:
                    self.inner.set_attr(party, "tom_capacity",
                                        _im.effective_tom_capacity(self, party))
                except Exception:  # noqa: BLE001
                    pass
            addressee_name = self.s.node(self.agent)["attrs"].get("substrate_name") \
                or "jabberwock"
            ce.arm_deictic_centre(self, speaker=speaker_name, addressee=addressee_name)

            # ATTITUDE INGEST -- TWO LEVELS (Wave: interlocutor-as-modeled-
            # participant, task 3, REDESIGNED per course correction 2026-07-11:
            # "it has to understand that i have *said* i think x is y...
            # unreliable narrator... most centroid introspection is surface
            # level at best"). character_tom's construction is reused VERBATIM
            # (not reimplemented) purely as the LEVEL-2 grounding primitive;
            # everything about "this is a LIVE self-report from a REAL tracked
            # party -- weak, revisable evidence" is this adapter's OWN
            # provenance/confidence bookkeeping, per the substrate's own
            # revisable-feature-belief law (coref_entities.py:102-140, the
            # mis-gendered-sparrow machinery: a feature's VALUE is a belief
            # with a SOURCE and CONFIDENCE, never a bare fact).
            #
            # `character_name=speaker_name` maps a first-person subject
            # ("I think X"/"I want Y") onto the REAL interlocutor identity just
            # armed above; a third-person subject ("Sally thinks X") is
            # unaffected. `unit=None` is the deliberate choice of the GLOBAL
            # cross-turn entity pool: the SAME pool `arm_deictic_centre`/
            # `_resolve_pron_name` use, so "I think the moon is cheese" now and
            # "I want it faster" three turns later both accumulate on ONE
            # persistent SmEntity for this speaker -- the per-flow `unit`
            # isolation the comprehension spine uses elsewhere keeps DIFFERENT
            # reads' mentions apart, not one interlocutor's own accumulating
            # model, which must persist. A non-attitude turn returns None and
            # mints nothing at either level (the discriminative case,
            # unchanged from the corpus reader).
            # A self-report is characteristically ASSERTED, never ASKED: "What
            # do you know about me?" contains the attitude-class verb "know"
            # in main-verb position with a subject/complement either side, so
            # the construction WOULD otherwise decode it as a self-report —
            # wrong, it is a question TO the agent, not a claim about the
            # interlocutor's own mind. Read the turn's OWN speech-act
            # classification (already decided, graph-resident) and skip
            # attitude ingest on a question — an honest scope boundary (this
            # wave models what a party ASSERTS, not what they ASK), not a new
            # Python decision (the kind was decided upstream by
            # classify_speech_act / the sak_kind rules; this only reads it).
            _sa_nodes = list(self.inner.neighbours(mid, "has_speech_act"))
            _sa_name = (self.s.node(_sa_nodes[0])["attrs"].get("name")
                       if _sa_nodes else None)
            attitude = None if _sa_name == "question" else ct_tom.ingest_attitude_sentence(
                self, text, t=int(getattr(self, "_shadow_seq_counter", 0)),
                unit=None, character_name=speaker_name)
            if attitude is not None:
                flavor = (attitude.get("membership") or {}).get("flavor")
                self.inner.set_attr(mid, "shadow_attitude_flavor", flavor)
                self.inner.set_attr(mid, "shadow_attitude_subject", attitude.get("subject"))

                # LEVEL 1 -- the ASSERTION RECORD (immutable): "the party SAID
                # this verbatim sentence at this turn." NEVER revised -- a
                # later correction revises the LEVEL-2 model below, never this
                # record (see _record_interlocutor_correction).
                self._attitude_turn_counter = getattr(self, "_attitude_turn_counter", 0) + 1
                turn_no = self._attitude_turn_counter
                hedged = _im.is_hedged(text)
                assertion = self.s.add_node("Assertion", {
                    "content": text, "turn": float(turn_no),
                    "verb": attitude.get("attitude_verb"), "flavor": flavor,
                    "hedged": hedged})
                self.inner.add_edge_unchecked(assertion, "asserted_in", mid)
                if party is not None:
                    self.inner.add_edge_unchecked(party, "asserted", assertion)
                    prior_n = int(self.s.node(party)["attrs"].get("self_report_count", 0) or 0)
                    self.inner.set_attr(party, "self_report_count", prior_n + 1)

                # LEVEL 2 -- the MODELED BELIEF (derived, revisable). The
                # nested SmEntity/SmEvent `ingest_attitude_sentence` already
                # minted (reused, never duplicated) is TAGGED, not rebuilt:
                # source='self_report' + a confidence from PRIORS-BY-SHAPE-
                # MATCHING blended with individual track record
                # (`interlocutor_model.effective_reliability` -- structural
                # evidence, e.g. creator-origin, overrides outright; otherwise
                # a matched InterlocutorShape's prior, n-weighted against this
                # party's own record; hedged phrasing further discounts it).
                # Re-queried by identity (belief_holder / idx_protagonist ==
                # this speaker) rather than trusted from `attitude`'s return
                # dict, whose node references already went through
                # situation_model_reader._v() (a display-safe scalar there,
                # not a graph-writable reference here).
                level2 = None
                if flavor in ("belief", "knowledge"):
                    for n in reversed(self.s.nodes("SmEntity")):
                        at = self.s.node(n)["attrs"]
                        if at.get("nested") and at.get("belief_holder") == speaker_name:
                            level2 = n
                            break
                elif flavor == "desire":
                    for n in reversed(self.s.nodes("SmEvent")):
                        at = self.s.node(n)["attrs"]
                        if at.get("verb") == "want" and at.get("idx_protagonist") == speaker_name:
                            level2 = n
                            break
                if level2 is not None:
                    reliability, rel_source = (0.5, "default")
                    if party is not None:
                        reliability, rel_source = _im.self_report_reliability(self, party)
                    confidence = round(reliability * (0.6 if hedged else 1.0), 3)
                    self.inner.set_attr(level2, "source", "self_report")
                    self.inner.set_attr(level2, "confidence", confidence)
                    self.inner.set_attr(level2, "reliability_source", rel_source)
                    self.inner.add_edge_unchecked(level2, "about_assertion", assertion)
                    self.inner.set_attr(mid, "shadow_attitude_confidence", confidence)
                self.inner.set_attr(mid, "shadow_attitude_assertion", assertion)
                self._last_attitude_turn = {**attitude, "assertion": assertion,
                                            "level2": level2, "hedged": hedged}
            else:
                self._last_attitude_turn = None

            # PRONOUN ENRICHMENT (Wave 4, Deep-Reader unification): snapshot
            # the SmMention pool BEFORE this turn's spine runs, so the ones it
            # mints THIS call are identifiable by plain set difference -- no
            # `unit`/flow attr needed on SmMention (it carries none). Purely
            # mechanical bookkeeping around the read below.
            _mentions_before = set(self.s.nodes("SmMention"))
            # TOPIC SPAN ENRICHMENT (blind-spot closure R7): snapshot the
            # SmEntity pool too, on the SAME "plain set difference" idiom, so
            # this turn's newly-minted entities are identifiable below.
            _entities_before = set(self.s.nodes("SmEntity"))

            ap = rs.conversational_aperture(self)
            bb = rd.run_reading_flow(
                self, text, report="comprehend",
                stages=ap.get("stages"),
                max_sentences=ap.get("max_sentences") or 3,
                window=ap.get("window") or 1,
                register="conversational")

            flow = bb.get("flow")
            for spn in self.s.nodes("SentenceParse"):
                if self.s.node(spn)["attrs"].get("flow") == flow:
                    self.inner.add_edge_unchecked(mid, "comprehended_as", spn)

            # RECORD (mechanical readback only -- see seeds/
            # conversation_pronoun_enrichment.json for the DECISION of
            # whether/when a rule may use this): the first newly-minted
            # SmMention this turn's spine RESOLVED (a real `refers_to` edge,
            # never a held-open one) becomes `shadow_referent` -- the SAME
            # "first-of" readback idiom already used below for `predicate`
            # (`textbase[0]`/`preds[0]`), never a salience contest of its own.
            # DEICTIC mentions ('I'/'you', carrying a `deixis` attr --
            # coref_entities.resolve_pronoun's own marker) are SKIPPED here:
            # they already resolve trivially off the armed DeicticCentre and
            # are already handled by the existing self/addressee reply paths
            # -- recording THEM as the turn's referent would collide with
            # those paths (verified live) rather than fill a genuine gap.
            _new_mentions = sorted(set(self.s.nodes("SmMention")) - _mentions_before,
                                   key=lambda _n: getattr(_n, "value", _n))
            shadow_referent = None
            for _mn in _new_mentions:
                _mn_attrs = self.s.node(_mn)["attrs"]
                if _mn_attrs.get("deixis"):
                    continue
                _refs = list(self.inner.neighbours(_mn, "refers_to"))
                if _refs:
                    _rname = self.s.node(_refs[0])["attrs"].get("name")
                    if _rname:
                        shadow_referent = _rname
                        break
            if shadow_referent is not None:
                self.inner.set_attr(mid, "shadow_referent", shadow_referent)

            # DOCUMENT TOPIC SPAN (blind-spot closure R7): `_topic_facts`'s
            # frame-based NP extraction (item 2.7, B1-blocked) and
            # `shadow_focus` (read_clause's OWN head-only reduction, Wave 3)
            # both reduce a multi-word proper-noun topic to its HEAD noun
            # ("wright" / "brothers" for "the Wright brothers") -- a mismatch
            # against the HeldAnswer bridge's key, which is the deep reader's
            # OWN multi-word entity name (coref_entities' entity-naming
            # convention, e.g. "wright_brothers" -- the SAME function that
            # named the document's salient entities at ingest,
            # _mint_document_held_answers). Rather than re-deriving an NP
            # span with a new Python heuristic, read the RICHER signal the
            # reader already computed: does one of THIS turn's newly-minted
            # SmEntities carry a name that matches a HeldAnswer topic we
            # already persisted? That equality is a graph fact (two readers,
            # same deterministic entity-naming, same string), never a new
            # decision -- routing on it is seeds/conversation_topic_span.
            # json::route_shadow_topic_to_answer's job, not this adapter's.
            _new_entities = sorted(set(self.s.nodes("SmEntity")) - _entities_before,
                                   key=lambda _n: getattr(_n, "value", _n))
            if _new_entities:
                _held_topics = {self.s.node(_h)["attrs"].get("topic")
                                for _h in self.s.nodes("HeldAnswer")}
                for _en in _new_entities:
                    _en_name = self.s.node(_en)["attrs"].get("name")
                    if _en_name and _en_name in _held_topics:
                        self.inner.set_attr(mid, "shadow_doc_topic", _en_name)
                        break

            predicate = None
            textbase = (bb.get("spine") or {}).get("textbase") or []
            if textbase:
                preds = textbase[0].get("predications") or []
                if preds and preds[0]:
                    predicate = preds[0][0]

            clause = rc.read_clause(self, text, write=False, learn=False)
            if predicate is None:
                cpreds = clause.get("predications") or []
                if cpreds and cpreds[0]:
                    predicate = cpreds[0][0]

            self.inner.set_attr(mid, "shadow_speech_act", clause.get("speech_act"))
            self.inner.set_attr(mid, "shadow_focus", clause.get("focus"))
            if predicate is not None:
                self.inner.set_attr(mid, "shadow_predicate", predicate)
            self._record_shadow_health(mid, (_time.perf_counter() - t0) * 1000.0)
        except Exception:  # noqa: BLE001 -- a shadow read must never affect the turn
            self.inner.set_attr(mid, "shadow_error", 1.0)
            self._record_shadow_health(mid, (_time.perf_counter() - t0) * 1000.0)

    def _record_shadow_health(self, mid, latency_ms: float) -> None:
        """SELF-OPTIMISATION (Wave: the agent notices its own comprehension
        process). Two MECHANICAL data writes, no decision -- the WHETHER-this-
        is-a-gap call is entirely seeds/comprehension_health.json's rules:

          1. `shadow_latency_ms` on the Message (same value/semantics as
             before this wave, now written HERE instead of at each call site)
             plus a monotonic `shadow_seq` counter on THIS Message -- every
             shadow-read attempt (success or swallowed error) gets one, so a
             seed rule can pick "the latest shadow-read Message" as a single
             canonical binding (avoids a rule with N simultaneously-matching
             candidates minting N duplicate SelfConcerns in one run_rules
             round -- the same hazard a plain content-dedup guard alone does
             not close when several messages could satisfy it in the SAME
             fixpoint pass).
          2. a rolling average of the last 20 shadow-read latencies,
             maintained as plain Python arithmetic on THIS adapter instance
             (never consulted by any rule directly -- only the WRITTEN
             attr is), written onto the Agent node as
             `shadow_latency_recent_avg` (+ `shadow_latency_recent_n`) --
             the CLAUDE.md-sanctioned "adapter mechanically maintains a
             rolling datum for the rule to read" exception (the same shape
             as `_record_instruction_outcome`), used because a true windowed
             aggregate over 'recent' Messages is awkward to express as a
             single DSL Term."""
        self.inner.set_attr(mid, "shadow_latency_ms", float(latency_ms))
        self._shadow_seq_counter = getattr(self, "_shadow_seq_counter", 0) + 1
        self.inner.set_attr(mid, "shadow_seq", float(self._shadow_seq_counter))
        window = getattr(self, "_shadow_latency_window", None)
        if window is None:
            window = []
        window.append(float(latency_ms))
        window = window[-20:]
        self._shadow_latency_window = window
        avg = sum(window) / len(window)
        self.inner.set_attr(self.agent, "shadow_latency_recent_avg", avg)
        self.inner.set_attr(self.agent, "shadow_latency_recent_n", float(len(window)))

    def ingest_turn(self, text, speech_act="statement", speaker="user", context=None):
        """Mechanically publish one turn without settling cognition.

        Transport uses this asynchronous boundary: it writes the same inbound
        message and parse facts as ``converse`` but never calls ``comprehend``
        or selects a reply.  Daemon graph quanta subsequently decide, and a
        caller can poll ``graph_turn_reply`` for an explicit graph reply.
        """
        self.enable_replies()
        self.install_register_lexicon()
        self.note_register(text)
        try:
            from domains import context_model as _cm
            self._last_context_turn = _cm.observe_turn(self, text, context=context)
            im_context = _cm.interlocutor_context(self._last_context_turn)
        except Exception:
            self._last_context_turn = None
            im_context = {}
        try:
            from domains import interlocutor_model as _im
            self._last_interlocutor_turn = _im.observe_turn(self, text, context=im_context)
            self.set_addressee(self._last_interlocutor_turn["party"])
        except Exception:
            self._last_interlocutor_turn = None
        mid = self.receive_utterance(text, speech_act=speech_act, speaker=speaker)
        if getattr(self, "shadow_read", False):
            self._shadow_read_turn(mid, text)
        if speech_act not in self._SOCIAL_ACTS:
            kind = self._graph_kind_for(mid, text)
            try:
                from domains import comprehend_text as _ct
                comp = _ct.comprehend_text(self, text, kind=kind)
            except Exception:
                comp = None
            if comp is not None:
                self._ensure_comprehension_seeds()
                self._write_comprehension_to_graph(mid, comp)
        return mid

    def graph_turn_reply(self, mid):
        """Read only an explicit rule-minted reply; ``None`` means pending."""
        return self._graph_reply_for(mid)

    def converse(self, text, speech_act="statement", speaker="user", context=None):
        """One full text-in -> text-out turn. Mechanical host I/O only:

        ingest -> write parse facts -> tick (graph rules decide) -> fulfil
        pending search/detail requests + routed goals -> tick again -> read the
        graph's reply.

        No Python routing ladder — the agent's rules mint Goals and outbound
        Messages; this method never decides HOW to answer. The read-off
        PRECEDENCE (mechanical, each leg a rendering of a decision already
        made by rules or by question_targets data, never a new one):
          1. a rule-minted text reply (non-floor) — the graph spoke;
          2. the answer_topic fulfiller (_answer_topic_reply) — renders the
             route rule's Goal, self-healing via grounding on a miss;
          2b. the interlocutor-meta fulfiller (_answer_interlocutor_meta_
             reply, R6) — renders route_first_person_question_to_
             interlocutor's Goal for a bare first-person question ("who am
             I?");
          3. the meta reader readback (_meta_reader_reply) — renders the front
             end's question_targets routing;
          4. the honest-floor rule's reply / the mechanical minimal ack."""
        self.enable_replies()
        self.install_register_lexicon()
        self.note_register(text)
        try:
            from domains import context_model as _cm
            self._last_context_turn = _cm.observe_turn(self, text, context=context)
            im_context = _cm.interlocutor_context(self._last_context_turn)
        except Exception:
            self._last_context_turn = None
            im_context = {}
        try:
            from domains import interlocutor_model as _im
            self._last_interlocutor_turn = _im.observe_turn(self, text, context=im_context)
            # TOLD-STATUS / addressee (Wave: interlocutor-as-modeled-participant,
            # task 1): point the agent at the party THIS turn belongs to, once
            # per turn, mechanically -- so the Gricean quantity gate
            # (_communicative_action / _finish_turn_reply) and any Goal minted
            # this turn (task 2's `wanted_by`) attribute to the right party even
            # across a mid-conversation re-attribution.
            self.set_addressee(self._last_interlocutor_turn["party"])
        except Exception:
            self._last_interlocutor_turn = None

        mid = self.receive_utterance(text, speech_act=speech_act, speaker=speaker)
        if getattr(self, "shadow_read", False):
            # Wave 2: purely additive, opt-in (see __init__) — recorded on the
            # Message, never consulted by anything below. comp_* stays
            # authoritative for the reply.
            self._shadow_read_turn(mid, text)
        comp = None
        if speech_act not in self._SOCIAL_ACTS:
            # KIND is the graph's decision (Wave 4): signals on the live
            # Message -> rule pass -> read sak_kind back, then hand the decided
            # kind to the (otherwise unchanged) Python front end.
            kind = self._graph_kind_for(mid, text)
            try:
                from domains import comprehend_text as _ct
                comp = _ct.comprehend_text(self, text, kind=kind)
            except Exception:
                comp = None
            if comp is not None:
                self._ensure_comprehension_seeds()
                self._write_comprehension_to_graph(mid, comp)

        self.comprehend()
        topic_reply = None
        meta_reply = None
        if speech_act not in self._SOCIAL_ACTS:
            # Fulfil a routed answer_topic Goal from HELD knowledge first
            # (renders the route rule's decision; self-heals via grounding on
            # a miss) BEFORE dispatching the search I/O, so a fact the agent
            # already holds wins over a fresh search and the unresolved-floor
            # rule never claims a turn the fulfiller can answer. Then render
            # the front end's meta routing (question_targets data) the same
            # way. Both are readbacks of decisions already made.
            # CODE-4: a pasted function DEFINITION (teach-by-example) is
            # claimed before everything -- its classifier (a parseable `def`)
            # is disjoint from every NL trigger below (an NL turn is not
            # parseable Python), so it never steals a turn.
            topic_reply = self._code_example_reply(mid)
            # CODE-3: a code-write request is claimed FIRST -- its own thin
            # classifier (write-verb + function/code word) is disjoint from
            # every topic/meta trigger below, so checking it first never
            # steals a turn those paths would otherwise have answered.
            if topic_reply is None:
                topic_reply = self._write_function_reply(mid)
            if topic_reply is None:
                # Fulfil a routed answer_topic Goal from HELD knowledge first
                # (renders the route rule's decision; self-heals via grounding
                # on a miss) BEFORE dispatching the search I/O, so a fact the
                # agent already holds wins over a fresh search and the
                # unresolved-floor rule never claims a turn the fulfiller can
                # answer. Then render the front end's meta routing
                # (question_targets data) the same way. Both are readbacks of
                # decisions already made.
                topic_reply = self._answer_topic_reply(mid)
            if topic_reply is None:
                # R6: renders route_first_person_question_to_interlocutor's
                # Goal, the SAME "rule already decided, adapter renders"
                # precedent as the topic fulfiller just above -- tried before
                # the front end's OWN (Python) meta routing so a bare
                # first-person question the front end mis-routed to "know"
                # still reaches the interlocutor reader.
                topic_reply = self._answer_interlocutor_meta_reply(mid)
            if topic_reply is None:
                meta_reply = self._meta_reader_reply(comp)
            self._dispatch_pending_io()
            self.comprehend()
            # MECHANICAL: record what happened to an instruction turn (a
            # datum -- see _record_instruction_outcome), then let the rules
            # see it in one more pass so a gap decision lands in-turn.
            if self._record_instruction_outcome(mid):
                self.comprehend()
            # CORRECTIONS (Wave: interlocutor-as-modeled-participant, task 3):
            # comprehension work, gated behind the same shadow_read flag family
            # as the rest of this wave's per-turn modelling.
            if getattr(self, "shadow_read", False):
                self._record_interlocutor_correction(mid)

        if topic_reply is not None:
            # The graph routed this turn to an external topic (its OWN
            # Goal{answer_topic} decision) and the fulfiller rendered it —
            # that answer IS the turn's reply. Any other rule-minted text for
            # the same turn (a self-identity reply off the meta dispatch, the
            # floor) is the misroute the topic goal overrode.
            self._form_reply_intent_for_text("inform", topic_reply)
            return self._finish_turn_reply(mid, topic_reply, source="adapter")
        graph_reply = self._graph_reply_for(mid)
        if meta_reply is not None:
            # A rendered meta answer must not be shadowed by the bare
            # honest-floor reply; a SUBSTANTIVE rule-minted reply still wins.
            graph_reply = self._graph_reply_for(mid, skip_floor=True)
        if graph_reply is not None:
            self._form_reply_intent_for_text("inform", graph_reply)
            return self._finish_turn_reply(mid, graph_reply, source="agent")
        if meta_reply is not None:
            self._form_reply_intent_for_text("inform", meta_reply)
            return self._finish_turn_reply(mid, meta_reply, source="adapter")

        replies = [r for r in self.agent_outbound_messages()
                   if mid in self.responds_to(r)]
        if replies:
            out = self.emit_reply(replies[-1])
            if out is not None:
                return self._finish_turn_reply(mid, out, source="agent")

        # Terminal/one-pair-part acts mint no reply Message, but the
        # conversational surface never falls silent: the mechanical honest
        # floor ('noted'-class register acknowledgment). Host I/O only —
        # every rule already had its chance to claim the turn above.
        return self._finish_turn_reply(mid, self._honest_minimal_reply(),
                                       source="adapter", substantive=False)

    # --- production: render a source Term to a surface via graph RenderRules ---

    def install_language(self, name, surface_kind="text", held_in=None,
                         parent_lang=None):
        """Find or create a Language node. `parent_lang` (a language name) records
        a `parent_lang` edge so the renderer inherits the parent's rules for heads
        this language doesn't override. Mechanical."""
        lang = None
        for n in self.s.nodes("Language"):
            if self.s.node(n)["attrs"].get("name") == name:
                lang = n
                break
        if lang is None:
            lang = self.s.add_node("Language", {"name": name,
                                                "surface_kind": surface_kind})
        if parent_lang is not None:
            parent = self.install_language(parent_lang)
            if parent not in set(self.inner.neighbours(lang, "parent_lang")):
                self.inner.add_edge_unchecked(lang, "parent_lang", parent)
        return lang

    def _ensure_inherited(self, language):
        """Copy a language's parent-chain RenderRules onto it (one `has_rule`
        edge per inherited head it doesn't define) so the Rust Render engine —
        which only sees a language's own `has_rule` edges — renders inherited
        heads. Mechanical graph bookkeeping."""
        lang = self.language(language)
        if lang is None:
            return
        own = {self.s.node(r)["attrs"].get("head")
               for r in self.inner.neighbours(lang, "has_rule")}
        cur, guard = lang, 0
        while guard < 16:
            guard += 1
            parents = self.inner.neighbours(cur, "parent_lang")
            if not parents:
                break
            cur = parents[0]
            for r in self.inner.neighbours(cur, "has_rule"):
                h = self.s.node(r)["attrs"].get("head")
                if h not in own:
                    self.inner.add_edge_unchecked(lang, "has_rule", r)
                    own.add(h)

    def impasses(self):
        """Every Impasse node in the graph (e.g. render-gap diagnostics)."""
        return [n for n in self.s.nodes() if self.s.node(n)["type"] == "Impasse"]

    def unresolved_impasses(self):
        """Impasses the agent hasn't resolved yet (no `resolved` attr). Pure
        query — the agent's honest record of unfinished business."""
        return [n for n in self.impasses()
                if not self.s.node(n)["attrs"].get("resolved")]

    def learn_from_teacher(self, question, payload):
        """Absorb a teacher payload's `learn` entries into the graph (ingest of
        teaching). Entry kinds:
          • `rule`   — install a RenderRule (render teaching);
          • `phrase` — ground a word AND install an inquiry Frame for it so the
            agent recognises that kind of question next time: a taught Concept +
            its Microtheory (+ operates_in it) + a Frame (evoked_by the phrase,
            realised_by the concept, holds_in the Mt, with the taught
            binding_pattern + slots) + a memoised answer (or, with `language`, a
            computable semiotic definition — see _ground_semiotic).
        Returns the payload's `answer` (answer_within reports it as "taught").
        The teacher decided what to teach; the adapter writes it as graph data."""
        answer = payload.get("answer") if isinstance(payload, dict) else None
        for item in (payload or {}).get("learn", []):
            item = item or {}
            rule = item.get("rule")
            if rule:
                self.install_render_rule(
                    rule["language"], rule["head"],
                    self._spec_to_renderer_term(rule["template"]),
                    rule["binding_pattern"])
                continue
            phrase = item.get("phrase")
            if not phrase:
                continue
            mt = item.get("microtheory")
            if mt:
                self.install_microtheory(mt, item.get("description", ""),
                                         item.get("genl_mt"))
                self.operates_in(mt)
            concept = ("taught_" + phrase.lower().replace("-", "_")
                       .replace(" ", "_"))
            pattern = item.get("binding_pattern", "function_of_subject")
            if pattern == "predicate_of_subject":
                slots = [{"slot": item.get("slot_name", "arg")}]
            elif pattern == "function_of_two_subjects":
                slots = [{"slot": item.get("slot_a", "a")},
                         {"slot": item.get("slot_b", "b")}]
            else:
                slots = [{"slot": item.get("slot_name", "of")}]
            self.install_frame(concept + "_inquiry", [phrase], concept,
                               holds_in=mt, core_elements=slots,
                               binding_pattern=pattern)
            self.learn_sign(phrase.lower(), concept)
            # Memoise the answer (so the 2nd ask routes "learned"); if the
            # teacher gave a `language`, ALSO ground a computable definition that
            # OVERRIDES the memoised answer in taught_capabilities.
            self._taught_lookup[concept] = answer
            if answer is not None and str(answer).strip():
                self._persist_held_answer(str(phrase).strip(), str(answer))
            language = item.get("language")
            if language is not None:
                self._ground_semiotic(concept, language)
        return answer

    def _persist_held_answer(self, topic: str, text: str):
        """Mechanical graph write: persist a taught topic answer as HeldAnswer
        data the conversation_topic_reply rules can read back."""
        topic = str(topic or "").strip()
        text = str(text or "").strip()
        if not topic or not text:
            return None
        try:
            for n in self.s.nodes("HeldAnswer"):
                if (self.s.node(n)["attrs"].get("topic") or "").strip() == topic:
                    self.inner.set_attr(n, "text", text)
                    return n
            ha = self.s.add_node("HeldAnswer", {"topic": topic, "text": text})
            self.inner.add_edge_unchecked(self.agent, "holds_answer", ha)
            # Composition answers are stored under "composition of <concept>"
            # but answer_topic goals key on the bare concept — mirror mechanically.
            low = topic.lower()
            if low.startswith("composition of "):
                bare = topic[len("composition of "):].strip()
                if bare:
                    self._persist_held_answer(bare, text)
            return ha
        except Exception:  # noqa: BLE001
            return None

    # Salience/rendering caps for the document HeldAnswer bridge (Wave 4) --
    # plain aperture-style config, the same status as `max_sentences`/
    # `window` elsewhere: bounds on host-side rendering, not a comprehension
    # decision.
    _DOC_HELD_ANSWER_TOP_N = 8
    _DOC_HELD_ANSWER_MAX_LINES = 6
    _DOC_HELD_ANSWER_MAX_CHARS = 400

    def _deep_read_document(self, doc_id, text):
        """DEEP READ (Wave 4, Deep-Reader unification): route an ingested
        document through the FULL deep reader -- `register_source.
        route_reading`, the SAME by-shape encyclopedic/narrative/casual
        register routing a standalone document read already uses (ShapeDecode
        over `seeds/register_source.json`, never a Python if/else) -- then
        mint the HELDANSWER BRIDGE (`_mint_document_held_answers`) so the
        flow's own content becomes queryable through the EXISTING topic-
        answer machinery. Mechanical I/O only: WHICH register/approach wins
        is register_source's own decision; this only records the verdict and
        re-finds the flow's own SentenceParse nodes to link back
        (`doc -read_as-> SentenceParse`, the SAME re-scan-by-flow-attr
        technique `_shadow_read_turn` already uses for `comprehended_as`).
        Any failure is swallowed -- a deep document read must never break an
        upload."""
        try:
            from domains import register_source as rs
            route = rs.route_reading(self, text)
            flow = route.get("flow")
            if route.get("register") is not None:
                self.inner.set_attr(doc_id, "register", route.get("register"))
            if route.get("read_approach") is not None:
                self.inner.set_attr(doc_id, "read_approach", route.get("read_approach"))
            if flow is not None:
                self.inner.set_attr(doc_id, "deep_read_flow", flow)
                for spn in self.s.nodes("SentenceParse"):
                    if self.s.node(spn)["attrs"].get("flow") == flow:
                        self.inner.add_edge_unchecked(doc_id, "read_as", spn)
            self.inner.set_attr(doc_id, "deep_read", 1.0)
            self._mint_document_held_answers(doc_id, flow)
        except Exception:  # noqa: BLE001 -- ingest succeeded; the deep read is best-effort
            self.inner.set_attr(doc_id, "deep_read_error", 1.0)

    def _mint_document_held_answers(self, doc_id, flow):
        """THE HELDANSWER BRIDGE (Wave 4): mechanical rendering, NO new reply
        machinery. Selects the flow's SALIENT entities off the SAME signal
        `register_source.subject_by_salience` already ranks the encyclopedic
        subject by (`SmEntity.coref_mentions`, this flow's `unit`-scoped
        pool) -- a plain re-count, not a token-by-token mint (bounded to the
        top `_DOC_HELD_ANSWER_TOP_N`). Each salient entity's resolved
        predications (this flow's own SentenceParse nodes' coref-resolved
        `[rel, arg0, arg1]` triples -- the SAME data `reading_drive.
        _textbase_from_graph`/`_ingests_from_graph` re-read) render into a
        capped '<subj> <pred> <obj>. ...' string, mechanically, then persist
        via the EXISTING `_persist_held_answer` -- already read back by the
        `reply_topic_from_held_answer` seed rule and by `_answer_topic_reply`
        / `answer_about`, so "What do you know about <entity>?" answers from
        the document's own read structure with ZERO new reply/routing code.
        A document with no flow (deep_ingest off, or a deep-read error before
        this point) mints nothing."""
        if flow is None:
            return
        import json as _json
        sub = self.s
        entities = []
        for n in sub.nodes("SmEntity"):
            at = sub.node(n)["attrs"]
            if at.get("unit") != flow:
                continue
            name = at.get("name")
            if not name:
                continue
            mentions = float(at.get("coref_mentions") or 0.0)
            entities.append((str(name), mentions))
        if not entities:
            return
        entities.sort(key=lambda e: -e[1])
        salient = [name for name, _m in entities[: self._DOC_HELD_ANSWER_TOP_N]]

        predications = []
        for spn in sub.nodes("SentenceParse"):
            at = sub.node(spn)["attrs"]
            if at.get("flow") != flow:
                continue
            try:
                preds = _json.loads(at.get("resolved_predications") or "[]")
            except Exception:  # noqa: BLE001
                preds = []
            for p in preds:
                if isinstance(p, (list, tuple)) and len(p) >= 3:
                    predications.append((str(p[0]), str(p[1]), str(p[2])))

        # REFORM COMPONENTS (blind-spot closure R8, 2026-07-12): a reform's
        # decomposed part_of structure now lives as REAL SmEntity + `part_of`
        # edges in the situation model (reading_drive._execute_pending_
        # reform_ingests, stamped `from_reform=1` on the part), not just the
        # SentenceParse's own `reform_predications` attr — read the GRAPH
        # STRUCTURE itself (mechanical query, no new decision) so a document's
        # held answer for e.g. "device" also names its parts.
        for n in sub.nodes("SmEntity"):
            at = sub.node(n)["attrs"]
            if at.get("unit") != flow or at.get("from_reform") != 1:
                continue
            part_name = at.get("name")
            if not part_name:
                continue
            for whole in sub.neighbours(n, "part_of"):
                whole_name = sub.node(whole)["attrs"].get("name")
                if whole_name:
                    predications.append(("part_of", str(part_name), str(whole_name)))

        for name in salient:
            lines = []
            seen_lines = set()
            for rel, a0, a1 in predications:
                if a0 == name or a1 == name:
                    line = f"{a0} {rel} {a1}."
                    # dedupe (mechanical rendering): the base read's own
                    # resolved predication and the reform's part_of edge can
                    # name the SAME fact -- render it once.
                    if line in seen_lines:
                        continue
                    seen_lines.add(line)
                    lines.append(line)
                if len(lines) >= self._DOC_HELD_ANSWER_MAX_LINES:
                    break
            if not lines:
                continue
            text = " ".join(lines)
            if len(text) > self._DOC_HELD_ANSWER_MAX_CHARS:
                text = text[: self._DOC_HELD_ANSWER_MAX_CHARS].rstrip() + "…"
            self._persist_held_answer(name.lower(), text)

    def _dispatch_pending_io(self):
        """Mechanical fulfilment of graph-minted SearchRequest / DetailRequest
        nodes. No routing decisions — the agent's rules mint requests; this
        performs the host I/O and persists results back into the graph."""
        try:
            from domains.fetch_dispatch import (scan_and_search, scan_and_ingest_detail,
                                                scan_and_sync_ground)
            scan_and_sync_ground(self)
            scan_and_search(self)
            scan_and_ingest_detail(self)
        except Exception:  # noqa: BLE001
            pass
        try:
            from domains.upload_text_read import pump_upload_text_read
            pump_upload_text_read(self)
        except Exception:  # noqa: BLE001
            pass

    def wire_upload_text_read_faculty(self):
        """Install the upload_text_read_advance reflex response handler. Idempotent."""
        try:
            from domains.upload_text_read import wire_upload_text_read_faculty
            wire_upload_text_read_faculty(self)
        except Exception:  # noqa: BLE001
            pass

    def _ensure_concept(self, name, **attrs):
        """Find or create a Concept node by name (mechanical)."""
        c = self._concept_by_name(name)
        if c is None:
            a = {"name": name}
            a.update(attrs)
            c = self.s.add_node("Concept", a)
        return c

    def operates_in(self, name):
        """Bring a Microtheory into the agent's competence scope (idempotent
        operates_in edge) — ingest of teaching. Mechanical."""
        mt = self.microtheory(name)
        if mt is not None and mt not in set(
                self.inner.neighbours(self.agent, "operates_in")):
            self.inner.add_edge_unchecked(self.agent, "operates_in", mt)
        return mt

    def wire_substrate_identity(self):
        """Ensure the agent operates_in its substrate-identity Microtheory so
        graph self-reply rules can read substrate_name. Idempotent host wiring
        for resumed checkpoints that predate the boot_all operates_in edge."""
        try:
            for m in self.s.nodes("Microtheory"):
                a = self.s.node(m)["attrs"]
                sn = a.get("substrate_name")
                if not sn:
                    continue
                if m not in set(self.inner.neighbours(self.agent, "operates_in")):
                    self.inner.add_edge_unchecked(self.agent, "operates_in", m)
                self.inner.set_attr(self.agent, "substrate_name", str(sn))
        except Exception:  # noqa: BLE001
            pass

    def refresh_stale_acronym_answers(self):
        """Drop poisoned HeldAnswer / taught_lookup entries for known tech
        acronyms whose stored text does not match the canonical expansion."""
        try:
            from domains.acronym_expand import _EXPANSIONS
            from domains.topic_grounding import _clear_stale_acronym_answer
            for acr, exp in _EXPANSIONS.items():
                _clear_stale_acronym_answer(self, acr, exp)
        except Exception:  # noqa: BLE001
            pass

    def install_frame(self, name, evoked_by, realised_by, holds_in=None,
                      core_elements=None, binding_pattern="function_of_subject"):
        """Write a Frame into the graph (idempotent) — used to INGEST a frame
        the teacher taught at runtime (NOT to construct the default library,
        which is the seeds/frames.json manifest). realised_by -> the capability
        Concept (auto-created, agent knows_concept it); holds_in -> its Mt (and
        the Concept holds_in the same Mt). Mechanical graph write."""
        f = self.frame(name)
        if f is not None:
            return f
        f = self.s.add_node("Frame", {
            "name": name, "evoked_by": list(evoked_by),
            "binding_pattern": binding_pattern,
            "core_elements": core_elements or []})
        concept = self._ensure_concept(realised_by)
        self.inner.add_edge_unchecked(f, "realised_by", concept)
        if self.agent not in set(self.inner.in_neighbours(concept, "knows_concept")):
            self.inner.add_edge_unchecked(self.agent, "knows_concept", concept)
        if holds_in:
            mt = self.microtheory(holds_in)
            if mt is not None:
                self.inner.add_edge_unchecked(f, "holds_in", mt)
                if mt not in set(self.inner.neighbours(concept, "holds_in")):
                    self.inner.add_edge_unchecked(concept, "holds_in", mt)
        return f

    # --- language grounding: learn unknown words from a teacher, per word -----

    def install_microtheory(self, name, description="", genl=None):
        """Find or create a Microtheory node (idempotent); if `genl` names a
        broader Mt, add the `genlMt` edge to it (CYC scope inheritance).
        Mechanical."""
        mt = self.microtheory(name)
        if mt is None:
            mt = self.s.add_node("Microtheory",
                                 {"name": name, "description": description})
        if genl:
            parent = self.microtheory(genl)
            if parent is not None and parent not in set(
                    self.inner.neighbours(mt, "genlMt")):
                self.inner.add_edge_unchecked(mt, "genlMt", parent)
        return mt

    def microtheory_names(self):
        """Every Microtheory name in the graph (pure query)."""
        return {self.s.node(n)["attrs"].get("name") for n in self.s.nodes("Microtheory")}

    # --- Frame / Microtheory register layer — PURE QUERIES over the loaded
    # `frames` seed (graph data installed by the Rust loader; the adapter does
    # NOT construct it). recognise_frame (the recognition DECISION) is separate.

    def microtheory(self, name):
        """NodeID of the Microtheory named `name`, or None. Pure query."""
        for n in self.s.nodes("Microtheory"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return None

    def frame(self, name):
        """NodeID of the Frame named `name`, or None. Pure query."""
        for n in self.s.nodes("Frame"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return None

    def frames(self):
        """Every Frame node (pure query)."""
        return list(self.s.nodes("Frame"))

    def _agent_scope_mts(self):
        """Every Microtheory in the agent's scope: those it `operates_in`, their
        `genlMt` ancestors, and the specialised children that `genlMt` an
        in-scope Mt (CYC scope-of-applicability). Pure graph closure."""
        scope, stack = set(), list(self.inner.neighbours(self.agent, "operates_in"))
        while stack:
            mt = stack.pop()
            if mt in scope:
                continue
            scope.add(mt)
            stack.extend(self.inner.neighbours(mt, "genlMt"))
        for n in self.s.nodes("Microtheory"):
            if any(p in scope for p in self.inner.neighbours(n, "genlMt")):
                scope.add(n)
        return scope

    def _meaning_from_frame(self, frame_id, slots):
        """The meaning a recognised Frame realises: {realised_by-Concept-name:
        slots} — the Term `solve` dispatches to the capability. Mechanical graph
        read."""
        concept = next(iter(self.inner.neighbours(frame_id, "realised_by")), None)
        if concept is None:
            return {}
        return {self.s.node(concept)["attrs"].get("name"): slots}

    def taught_capabilities(self):
        """Capabilities the agent acquired from teaching: memoised answers
        (_taught_lookup) OVERRIDDEN by computable semiotic definitions (a
        grounded `language` Term evaluated against the subject) where present —
        so one teaching computes many answers. Mechanical: closures over stored
        graph data, no decisions."""
        caps = {c: (lambda _a, v=ans: v) for c, ans in self._taught_lookup.items()}
        for c, tjson in getattr(self, "_semiotic_definitions", {}).items():
            caps[c] = self._semiotic_evaluator(tjson)
        return caps

    def _ground_semiotic(self, concept, language):
        """Ground a taught `language` spec (DSL nested-list) into an evaluable
        Term on the concept — a COMPUTABLE capability. Stores the spec on the
        Concept node (so it round-trips through save/load) + caches the
        Term-JSON for taught_capabilities. Mechanical translation."""
        import json
        from substrate.jsonio import term_to_json
        cid = self._ensure_concept(concept)
        # Store the spec as a JSON string so it round-trips EXACTLY (substrate
        # attrs coerce nested lists to tuples otherwise).
        self.inner.set_attr(cid, "language", json.dumps(language))
        if not hasattr(self, "_semiotic_definitions"):
            self._semiotic_definitions = {}
        self._semiotic_definitions[concept] = term_to_json(self._spec_to_term(language))

    def semiotic_spec(self, concept):
        """The taught `language` spec (nested list) for a concept, or None.
        Pure query — decodes the JSON stored on the Concept node."""
        import json
        cid = self._concept_by_name(concept)
        if cid is None:
            return None
        raw = self.s.node(cid)["attrs"].get("language")
        return json.loads(raw) if raw is not None else None

    def _semiotic_evaluator(self, term_json):
        """A capability that EVALUATES a grounded Term against the question's
        subject: bind `x` to a fresh Num node carrying the subject value, run the
        Term in Rust. The Term is the decision; this is mechanical I/O."""
        def cap(args):
            subj = args.get("of") if "of" in args else args.get("arg")
            if subj is None:
                return None
            nn = self.s.add_node("Num", {"value": subj})
            return self.inner.evaluate(term_json, {"x": nn})
        return cap

    def _reindex_semiotic_definitions(self):
        """Rebuild the _semiotic_definitions cache from the `language` spec
        stored on Concept nodes (after load). Mechanical."""
        from substrate.jsonio import term_to_json
        import json
        self._semiotic_definitions = {}
        for c in self.s.nodes("Concept"):
            attrs = self.s.node(c)["attrs"]
            raw = attrs.get("language")
            if raw is not None:
                name = attrs["name"]
                self._semiotic_definitions[name] = term_to_json(
                    self._spec_to_term(json.loads(raw)))
                # mark it taught so answer_within routes it "learned" post-load
                # (the value is unused — the semiotic def overrides it).
                self._taught_lookup.setdefault(name, None)

    def _record_op(self, op, ms):
        """Self-profiling: tally an engine op's call count + total wall-cost on
        the agent node (graph-resident, introspectable). Mechanical."""
        a = self.s.node(self.agent)["attrs"]
        self.inner.set_attr(self.agent, f"op_{op}_count",
                            int(a.get(f"op_{op}_count", 0)) + 1)
        self.inner.set_attr(self.agent, f"op_{op}_total_cost",
                            float(a.get(f"op_{op}_total_cost", 0.0)) + ms)

    def runtime_capabilities(self):
        """Capabilities that answer about the agent's OWN engine — op call
        count / total cost / mean cost, read from the graph-resident profile the
        instrumented paths record. The agent introspects itself through the same
        Frame layer. Mechanical reads, no decisions."""
        def _count(args):
            return int(self.s.node(self.agent)["attrs"].get(
                f"op_{args.get('of')}_count", 0))

        def _total(args):
            return float(self.s.node(self.agent)["attrs"].get(
                f"op_{args.get('of')}_total_cost", 0.0))

        def _mean(args):
            c = _count(args)
            return _total(args) / c if c else 0.0

        def _describe_self(_args):
            """The meaning the self_identity_query_frame realises: the agent is a
            MIND (it bears mental states). A mechanical graph-read constant — the
            graph-native migration of the Python install_self_capabilities wiring
            the seed-boot dropped (it monkey-patched this same dict). produce()
            renders whatever pieces of the meaning the lexicon can express."""
            return {"mind": {}}

        return {"op_count": _count, "op_total_cost": _total, "op_mean_cost": _mean,
                "describe_self": _describe_self}

    def use_rust_runner(self):
        """Opt into the substrate's self-designed Rust recogniser delegation.
        Returns False when the .so isn't loadable (the agent keeps using the
        graph-native Python recognise_frame). Mechanical capability probe."""
        try:
            from domains import rust_runner
            self._rust_runner_enabled = bool(rust_runner.is_available())
        except Exception:
            self._rust_runner_enabled = False
        return self._rust_runner_enabled

    def taught_signs(self):
        """Every grounded sign as a {form, concept} dict (pure query) — across
        BOTH sign representations: the flat `Sign` nodes the teacher-grounding
        path mints, and the `Lexeme` entries a seed's lexicon carries (e.g. the
        psychology verb signs). Forms the agent can express are the union."""
        return [{"form": self.s.node(n)["attrs"].get("form"),
                 "concept": self.s.node(n)["attrs"].get("concept")}
                for t in ("Sign", "Lexeme") for n in self.s.nodes(t)]

    def has_theory_of_mind(self):
        """True iff the graph holds the theory_of_mind concept AND its
        `demonstrates` edges point at belief + attribution + perspective — the
        agent introspecting whether it has ToM. Pure query."""
        tom = self._concept_by_name("theory_of_mind")
        if tom is None:
            return False
        names = {self.s.node(t)["attrs"].get("name")
                 for t in self.inner.neighbours(tom, "demonstrates")}
        return {"belief", "attribution", "perspective"} <= names

    def mental_states(self):
        """Names of the mental-state concepts (those subtype_of mental_state).
        Pure query over the seed taxonomy."""
        parent = self._concept_by_name("mental_state")
        if parent is None:
            return []
        return sorted(
            self.s.node(c)["attrs"].get("name")
            for c in self.inner.in_neighbours(parent, "subtype_of")
            if self.s.node(c)["attrs"].get("name"))

    def _frame_choice_term(self):
        """The seeded Frame-recognition scoring Term (JSON, cached): over a
        FrameMatch candidate `c`, the FOK = hit_len * coverage + slot_bonus WHEN
        coverage clears the recognition threshold (0.20 — a coincidence gate,
        Koriat cue-utilisation), else -1 so it can never win. The DECISION (the
        FOK formula + the gate) is this graph-resident Term; the adapter only
        parses the question into candidate attrs + Argmaxes this Term."""
        if getattr(self, "_frame_choice_json", None) is None:
            from substrate import IfThenElse, Gte, Times, Plus, Attr, Var, Lit
            from substrate.jsonio import term_to_json
            c = Var("c")
            fok = Plus(items=(Times(items=(Attr(c, "hit_len"), Attr(c, "coverage"))),
                              Attr(c, "slot_bonus")))
            self._frame_choice_json = term_to_json(IfThenElse(
                cond=Gte(a=Attr(c, "coverage"), b=Lit(0.20)),
                then=fok, other=Lit(-1.0)))
        return self._frame_choice_json

    def recognise_frame(self, question):
        """Recognise an inquiry Frame from a question — returns (frame_id, slots,
        fok), or (None, {}, 0.0) on abstention. The adapter PARSES (I/O-boundary
        classification: find the longest evoking phrase present, bind the
        subject(s) per the Frame's binding_pattern, measure coverage) into
        FrameMatch candidate nodes; the seeded _frame_choice_term Argmax scores +
        gates them and picks the best. Scope is the genlMt closure over
        operates_in. The recognition CHOICE is graph data; only the text parse is
        Python."""
        import time
        t0 = time.perf_counter()
        result = self._recognise_frame_inner(question)
        self._record_op("recognise_frame", (time.perf_counter() - t0) * 1000.0)
        return result

    def _recognise_frame_inner(self, question):
        content = self._strip_preamble(question)
        content_len = max(len(content), 1)
        lower = question.lower()
        scope = self._agent_scope_mts()
        for stale in [n for n in self.s.nodes("FrameMatch")]:
            self.inner.remove_node(stale)
        by_node = {}
        for f in self.frames():
            attrs = self.s.node(f)["attrs"]
            hit_form, hit_pos = None, -1
            for form in attrs.get("evoked_by") or []:
                pos = lower.find(form.lower())
                if pos >= 0 and (hit_form is None or len(form) > len(hit_form)):
                    hit_form, hit_pos = form, pos
            if hit_form is None:
                continue
            held = list(self.inner.neighbours(f, "holds_in"))
            if held and not any(mt in scope for mt in held):
                continue
            slots = self._bind_slots(
                attrs.get("binding_pattern", "function_of_subject"),
                question, hit_form, hit_pos, attrs.get("core_elements") or [])
            if slots is None:
                continue
            numeric_chars = sum(len(str(v)) for v in slots.values()
                                if isinstance(v, (int, float)))
            coverage = (len(hit_form) + numeric_chars) / content_len
            cand = self.s.add_node("FrameMatch", {
                "hit_len": float(len(hit_form)), "coverage": float(coverage),
                "slot_bonus": 1.0 if slots else 0.0})
            by_node[cand] = (f, slots)
        if not by_node:
            return (None, {}, 0.0)
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "FrameMatch"},
                  "var_name": "c", "value": self._frame_choice_term()}
        winner = self.inner.evaluate(choose, {})
        fok = float(self.inner.evaluate(self._frame_choice_term(), {"c": winner})) \
            if winner is not None else -1.0
        frame_id, slots = by_node.get(winner, (None, {}))
        for cand in list(by_node):
            self.inner.remove_node(cand)
        if frame_id is None or fok <= 0.0:
            return (None, {}, 0.0)
        return (frame_id, slots, fok)

    # --- I/O-boundary parsing for frame recognition (text -> graph tokens;
    # a thin classifier converting an opaque question into the bound subject(s),
    # per CLAUDE.md's allowance — no graph decisions live here) ----------------

    @staticmethod
    def _strip_preamble(text):
        """Strip interrogative preamble + trailing punctuation so coverage
        measures CONTENT, not boilerplate. 'what is the trace of M' -> 'trace of
        M'."""
        s = text.strip().rstrip(".?!")
        low = s.lower()
        for prefix in ("what is the ", "what is ", "find the ", "find ",
                       "compute the ", "compute ", "calculate the ", "calculate ",
                       "determine the ", "determine "):
            if low.startswith(prefix):
                return s[len(prefix):].strip()
        return s

    def _bind_slots(self, pattern, q, hit_form, hit_pos, core):
        if pattern == "function_of_subject":
            return self._bind_function_of_subject(q, hit_form, hit_pos, core)
        if pattern == "predicate_of_subject":
            return self._bind_predicate_of_subject(q, hit_form, hit_pos, core)
        if pattern == "function_of_two_subjects":
            return self._bind_function_of_two_subjects(q, hit_form, hit_pos, core)
        return None

    @staticmethod
    def _bind_function_of_subject(q, form, pos, core):
        """'X of SUBJECT': text after the evoking phrase; strip a leading
        of/for marker; int-parse else use as name."""
        tail = q[pos + len(form):].strip()
        for marker in ("of ", "for "):
            if tail.lower().startswith(marker):
                tail = tail[len(marker):]
                break
        tail = tail.rstrip(".?!,;: ")
        if not core:
            return {}
        if not tail:
            return None
        slot = core[0].get("slot", "of")
        try:
            return {slot: int(tail.replace(",", ""))}
        except ValueError:
            return {slot: tail}

    @staticmethod
    def _bind_function_of_two_subjects(q, form, pos, core):
        """'X of A and B': two subjects split on ' and '/' by '/','."""
        import re
        tail = q[pos + len(form):].strip()
        for marker in ("of ", "for "):
            if tail.lower().startswith(marker):
                tail = tail[len(marker):]
                break
        tail = tail.rstrip(".?!,;: ")
        parts = re.split(r"\s+and\s+|\s+by\s+|,\s+", tail, maxsplit=1,
                         flags=re.IGNORECASE)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            return None
        if len(core) < 2:
            return None
        slot_a, slot_b = core[0].get("slot", "a"), core[1].get("slot", "b")

        def parse(t):
            try:
                return int(t.replace(",", ""))
            except ValueError:
                return t
        return {slot_a: parse(parts[0].strip()), slot_b: parse(parts[1].strip())}

    @staticmethod
    def _bind_predicate_of_subject(q, form, pos, core):
        """'Is/Are/Does SUBJECT (a) PREDICATE': subject BEFORE the evoking
        phrase, after the Is/Are/Does/Do; strip a trailing article."""
        before = q[:pos].strip()
        low = before.lower()
        prefix = next((p for p in ("is ", "are ", "does ", "do ")
                       if low.startswith(p)), None)
        if prefix is None:
            return None
        subj = before[len(prefix):].strip()
        for trailing in (" a", " an", " the"):
            if subj.lower().endswith(trailing):
                subj = subj[:-len(trailing)].strip()
                break
        if not subj:
            return None
        if not core:
            return {}
        slot = core[0].get("slot", "arg")
        try:
            return {slot: int(subj.replace(",", ""))}
        except ValueError:
            return {slot: subj}

    def impasse(self, over=None, reason="", question=""):
        """Record a graph-resident Impasse node (the agent's SOAR-style 'I don't
        know' marker). Mechanical."""
        return self.s.add_node("Impasse", {"reason": reason, "question": question})

    def mark_impasse_resolved(self, imp_id):
        """Mark an Impasse resolved (set its `resolved` attr). Mechanical."""
        try:
            self.inner.set_attr(imp_id, "resolved", True)
        except Exception:
            pass

    def receive(self, msg):
        """Receive an external message. For an assert, ground its unknown words
        and report what was learned + the concept-bearing meanings recognised
        (the known concepts it names). Mechanical I/O over the grounding faculty;
        full comprehension into relational meaning Terms is the heavier
        comprehend/produce path."""
        text = (msg or {}).get("text", "") if isinstance(msg, dict) else str(msg)
        learned = self.ground_unknowns(text)
        known = {s["concept"] for s in self.taught_signs()}
        meanings = []
        strip = ".,?!;:()[]\"'"
        for raw in text.split():
            w = raw.strip(strip).lower()
            c = "taught_" + w.replace("-", "_").replace(" ", "_")
            if c in known:
                meanings.append({c: {}})
        return {"learned": learned, "meanings": meanings}

    def ground_unknowns(self, text, teacher=None, min_len=3):
        """Per-word grounding: for each unknown token in `text` (len >= min_len,
        not already a known sign form), call `teacher(form)` — the BARE word, not
        a wrapped question — and absorb its payload via learn_from_teacher. Skips
        known words; survives a per-word teacher failure. Returns the forms newly
        grounded. The teacher decides the meaning; the adapter is the per-word
        I/O loop. Defaults to the registered self-teacher."""
        teacher = teacher or getattr(self, "_self_teacher", None)
        if teacher is None:
            return []
        known = {s["form"] for s in self.taught_signs()}
        learnt = []
        strip = ".,?!;:()[]\"'"
        for raw in text.split():
            w = raw.strip(strip).lower()
            if len(w) < min_len or w in known:
                continue
            try:
                payload = teacher(w)
            except Exception:
                payload = None
            if not payload:
                # The teacher couldn't ground this word — queue an inquire
                # goal so the agent can ASK the interlocutor about it.
                self._queue_inquiry(w)
                continue
            self.learn_from_teacher(w, payload)
            if any(s["form"] == w for s in self.taught_signs()):
                learnt.append(w)
                known.add(w)
        return learnt

    def language(self, name):
        """Find-only lookup of a Language node by name (or None). Pure query —
        complements install_language for existence checks."""
        for n in self.s.nodes("Language"):
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return None

    def install_render_rule(self, language, head, template, binding_pattern):
        """Install a RenderRule for a source-Term `head` in `language`: a
        graph-resident node carrying the `head`, the slot `binding_pattern`, and
        a `template` Term-subgraph (Surface/Cat/Slot/Render), wired to the
        Language by `has_rule`. Mechanical graph-data installation — the engine
        is the Rust `Render` evaluator."""
        from substrate.jsonio import term_to_json
        lang = self.install_language(language)
        rid = self.s.add_node("RenderRule", {"head": head,
                                             "binding_pattern": tuple(binding_pattern),
                                             "priority": 0})
        troot = self.inner.add_term_subgraph(term_to_json(template))
        self.inner.add_edge_unchecked(rid, "template", troot)
        self.inner.add_edge_unchecked(lang, "has_rule", rid)
        return rid

    def render(self, source_term, language):
        """Render a source Term to its surface string in `language`, via the
        graph-resident RenderRules. Stores the source as a Term subgraph and
        evaluates the Rust `Render` engine over it — it dispatches per head, binds
        the rule's slots to the source's children, and recurses on nested Render
        sub-terms. Returns the rendered surface (or None on a render gap)."""
        from substrate.jsonio import term_to_json
        lang = self.install_language(language)
        self._ensure_inherited(language)   # parent-chain rules visible to the engine
        root = self.inner.add_term_subgraph(term_to_json(source_term))
        return self.inner.evaluate(
            {"type": "Render", "term": {"type": "Var", "name": "src"},
             "lang": {"type": "Var", "name": "render_lang"}},
            {"src": root, "render_lang": lang})

    def render_rules_for(self, language, head):
        """The RenderRule NodeIDs registered for a source-Term `head` in
        `language` (pure query over the graph)."""
        lang = self.install_language(language)
        return [r for r in self.inner.neighbours(lang, "has_rule")
                if self.s.node(r)["attrs"].get("head") == head]

    # --- per-language code renderers (Python / Rust / x86_64) -----------------

    def seed_python_renderer(self,
                             language: str = "python",
                             held_in: str = "programming_languages") -> NodeID:
        """Install a complete Python renderer as graph data — one
        ``Language`` + ~17 ``RenderRule`` nodes. Mirrors the static
        ``domains.renderer.render_python`` output one-for-one; the
        parity test (``tests/test_graph_renderer_parity.py``) compares
        them on the factorial Term-tree + a corpus of arithmetic and
        boolean Terms. This is the same algebra; the surface
        translation is now graph-native data, editable as everything
        else."""
        from substrate import (Cat, IfThenElse, Join, Lit, LitRepr, Render,
                               Slot, Surface, Var)
        lang_id = self.install_language(
            language, surface_kind="text", held_in=held_in)
        # Literal: emit a FAITHFUL Python repr of the value via LitRepr
        # (CODE-3) — type-aware quoting a bare Slot binding can't do: a
        # string requoted (was left bare, invalid Python source), None/
        # Bool spelled correctly (was a raw Rust Debug leak, "Bool(true)"
        # / a render gap) — see runners/dsl/src/term.rs's `python_repr`
        # for the exact (Rust-evaluated) algorithm this composes.
        self.install_render_rule(
            language, "Lit",
            template=Cat(items=(LitRepr(value=Slot(name="value")),)),
            binding_pattern=["value"])
        # Var(name): emit the variable name as a literal identifier
        self.install_render_rule(
            language, "Var",
            template=Cat(items=(Slot(name="name"),)),
            binding_pattern=["name"])
        # Attr(node, key): in the spec convention `Attr(Var("x"), "value")`
        # is the SUBJECT placeholder rendered as "value". Other Attr forms
        # fall through to plain `node.key` access (a future iteration adds
        # a guard for the specific subject convention vs general attr).
        self.install_render_rule(
            language, "Attr",
            template=Cat(items=(Slot(name="key"),)),
            binding_pattern=["node", "key"])
        # Two-arg ops — each maps to "(a OP b)"
        for head, op in (("Eq", " == "), ("Gt", " > "), ("Gte", " >= "),
                         ("Lt", " < "), ("Lte", " <= "), ("Mod", " % "),
                         ("Minus", " - "), ("Pow", " ** "), ("Div", " / ")):
            self.install_render_rule(
                language, head,
                template=Cat(items=(
                    Surface(kind="text", payload="("),
                    Render(term=Slot(name="a")),
                    Surface(kind="text", payload=op),
                    Render(term=Slot(name="b")),
                    Surface(kind="text", payload=")"),
                )),
                binding_pattern=["a", "b"])
        # Variadic ops — Join over items
        for head, op in (("Plus", " + "), ("Times", " * "),
                         ("And", " and "), ("Or", " or ")):
            self.install_render_rule(
                language, head,
                template=Cat(items=(
                    Surface(kind="text", payload="("),
                    Join(separator=Surface(kind="text", payload=op),
                         items=Slot(name="items")),
                    Surface(kind="text", payload=")"),
                )),
                binding_pattern=["items"])
        # Unary
        self.install_render_rule(
            language, "Not",
            template=Cat(items=(
                Surface(kind="text", payload="(not "),
                Render(term=Slot(name="arg")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["arg"])
        # IfThenElse — Python conditional expression
        self.install_render_rule(
            language, "IfThenElse",
            template=Cat(items=(
                Surface(kind="text", payload="("),
                Render(term=Slot(name="then")),
                Surface(kind="text", payload=" if "),
                Render(term=Slot(name="cond")),
                Surface(kind="text", payload=" else "),
                Render(term=Slot(name="other")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["cond", "then", "other"])
        # Holds(concept, node, node2) — recursive call. node2 is optional;
        # when present this is binary recursion (gcd-style) and we'd emit
        # "concept(a, b)"; for the unary case we emit "concept(a)".
        self.install_render_rule(
            language, "Holds",
            template=Cat(items=(
                Slot(name="concept"),
                Surface(kind="text", payload="("),
                Render(term=Slot(name="node")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["concept", "node", "node2"])
        # CODE-2 additions — the widened emitter's new heads.
        # Neg(arg): unary minus.
        self.install_render_rule(
            language, "Neg",
            template=Cat(items=(
                Surface(kind="text", payload="(-"),
                Render(term=Slot(name="arg")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["arg"])
        # CODE-3: Abs(arg) — Python's builtin abs(). Held DSL Term (`Abs`)
        # with no prior Python RenderRule; the write codebook's
        # `abs_value` construction is the first caller.
        self.install_render_rule(
            language, "Abs",
            template=Cat(items=(
                Surface(kind="text", payload="abs("),
                Render(term=Slot(name="arg")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["arg"])
        # Let(name, value, body): Python has no let-expression, so a
        # sequential binding renders as a walrus-assignment tuple-index
        # expression -- `(name := value, body)[-1]` is a single Python
        # EXPRESSION (composable inside `return %s`, matching every other
        # render rule's contract) that binds `name` in the enclosing scope
        # via PEP 572 and then evaluates `body` with it visible. Nested
        # Lets compose correctly: the inner Let's own `(...)  [-1]` IS its
        # parent's `body`, so `(x := 1, (y := x + 1, y)[-1])[-1]` sees x
        # when computing y -- the same sequential-rebind semantics the
        # native Fold/Let evaluator already has.
        self.install_render_rule(
            language, "Let",
            template=Cat(items=(
                Surface(kind="text", payload="("),
                Slot(name="name"),
                Surface(kind="text", payload=" := "),
                Render(term=Slot(name="value")),
                Surface(kind="text", payload=", "),
                Render(term=Slot(name="body")),
                Surface(kind="text", payload=")[-1]"),
            )),
            binding_pattern=["name", "value", "body"])
        # Vec(items): an ordered literal (the accumulation construction's
        # materialised range(n) domain) -- a Python list literal.
        self.install_render_rule(
            language, "Vec",
            template=Cat(items=(
                Surface(kind="text", payload="["),
                Join(separator=Surface(kind="text", payload=", "),
                     items=Slot(name="items")),
                Surface(kind="text", payload="]"),
            )),
            binding_pattern=["items"])
        # Fold(source, var_name, acc_name, init, body): no direct Python
        # expression form, so render via functools.reduce -- imported
        # inline (`__import__`) so the rendered text is self-contained and
        # composes inside `return %s` without requiring the exec namespace
        # to pre-import anything (matching every other render rule's
        # single-expression contract).
        self.install_render_rule(
            language, "Fold",
            template=Cat(items=(
                Surface(kind="text",
                       payload="__import__('functools').reduce(lambda "),
                Slot(name="acc_name"),
                Surface(kind="text", payload=", "),
                Slot(name="var_name"),
                Surface(kind="text", payload=": "),
                Render(term=Slot(name="body")),
                Surface(kind="text", payload=", "),
                Render(term=Slot(name="source")),
                Surface(kind="text", payload=", "),
                Render(term=Slot(name="init")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["source", "var_name", "acc_name", "init", "body"])
        return lang_id

    def seed_rust_renderer(self,
                           language: str = "rust",
                           held_in: str = "programming_languages") -> NodeID:
        """Install a complete Rust renderer as graph data. Mirrors the
        static ``domains.renderer.render_rust`` output on integer
        expressions. (Float/bool literal handling is a richer rule set
        with type guards; deferred until the corpus needs it.)"""
        from substrate import Cat, Join, Render, Slot, Surface
        lang_id = self.install_language(
            language, surface_kind="text", held_in=held_in)
        # Lit (integer): "<value>i64" (str(value) + i64 suffix).
        self.install_render_rule(
            language, "Lit",
            template=Cat(items=(
                Slot(name="value"),
                Surface(kind="text", payload="i64"),
            )),
            binding_pattern=["value"])
        self.install_render_rule(
            language, "Var",
            template=Cat(items=(Slot(name="name"),)),
            binding_pattern=["name"])
        self.install_render_rule(
            language, "Attr",
            template=Cat(items=(Slot(name="key"),)),
            binding_pattern=["node", "key"])
        # Binary ops — Rust operators
        for head, op in (("Eq", " == "), ("Gt", " > "), ("Gte", " >= "),
                         ("Lt", " < "), ("Lte", " <= "), ("Mod", " % "),
                         ("Minus", " - "), ("Div", " / ")):
            self.install_render_rule(
                language, head,
                template=Cat(items=(
                    Surface(kind="text", payload="("),
                    Render(term=Slot(name="a")),
                    Surface(kind="text", payload=op),
                    Render(term=Slot(name="b")),
                    Surface(kind="text", payload=")"),
                )),
                binding_pattern=["a", "b"])
        # Variadics — Rust syntax for booleans uses &&/||
        for head, op in (("Plus", " + "), ("Times", " * "),
                         ("And", " && "), ("Or", " || ")):
            self.install_render_rule(
                language, head,
                template=Cat(items=(
                    Surface(kind="text", payload="("),
                    Join(separator=Surface(kind="text", payload=op),
                         items=Slot(name="items")),
                    Surface(kind="text", payload=")"),
                )),
                binding_pattern=["items"])
        # Not is `!arg` in Rust
        self.install_render_rule(
            language, "Not",
            template=Cat(items=(
                Surface(kind="text", payload="(!"),
                Render(term=Slot(name="arg")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["arg"])
        # IfThenElse is a brace-block expression in Rust
        self.install_render_rule(
            language, "IfThenElse",
            template=Cat(items=(
                Surface(kind="text", payload="(if "),
                Render(term=Slot(name="cond")),
                Surface(kind="text", payload=" { "),
                Render(term=Slot(name="then")),
                Surface(kind="text", payload=" } else { "),
                Render(term=Slot(name="other")),
                Surface(kind="text", payload=" })"),
            )),
            binding_pattern=["cond", "then", "other"])
        # Holds — same call shape as Python
        self.install_render_rule(
            language, "Holds",
            template=Cat(items=(
                Slot(name="concept"),
                Surface(kind="text", payload="("),
                Render(term=Slot(name="node")),
                Surface(kind="text", payload=")"),
            )),
            binding_pattern=["concept", "node", "node2"])
        return lang_id

    def seed_x86_64_renderer(self,
                             language: str = "x86_64",
                             held_in: str = "computer_architecture") -> NodeID:
        """Install the x86_64 ASM renderer as graph data — System V ABI,
        AT&T syntax, integer arg in %rdi, return in %rax, recursion via
        stack-saved %rdi. Rules use the Phase 6.7 stateful primitives:
        Label/Let for unique jump labels, Lines for statement-level
        concatenation, Nth for binary access to variadic Times/Plus."""
        from substrate import (Cat, Label, Let, Lines, Nth, Render, Slot,
                               Surface, Var)
        lang_id = self.install_language(
            language, surface_kind="text", held_in=held_in)

        # --- Lit: emit "    movq $<value>, %rax"
        self.install_render_rule(
            language, "Lit",
            template=Cat(items=(
                Surface(kind="text", payload="    movq $"),
                Slot(name="value"),
                Surface(kind="text", payload=", %rax"),
            )),
            binding_pattern=["value"])

        # --- Attr(Var("x"), "value"): subject placeholder → load %rdi
        # (the function argument) into %rax. Matches the spec convention.
        self.install_render_rule(
            language, "Attr",
            template=Surface(kind="text", payload="    movq %rdi, %rax"),
            binding_pattern=["node", "key"])

        # --- Comparison ops — same shape, different setcc mnemonic.
        # template emits: render b → push %rax; render a → pop %rcx;
        # cmpq %rcx, %rax; <setcc> %al; movzbq %al, %rax
        for head, setcc in (("Eq", "sete"), ("Gt", "setg"),
                            ("Gte", "setge"), ("Lt", "setl"),
                            ("Lte", "setle")):
            self.install_render_rule(
                language, head,
                template=Lines(items=(
                    Render(term=Slot(name="b")),
                    Surface(kind="text", payload="    pushq %rax"),
                    Render(term=Slot(name="a")),
                    Surface(kind="text", payload="    popq %rcx"),
                    Surface(kind="text", payload="    cmpq %rcx, %rax"),
                    Surface(kind="text", payload=f"    {setcc} %al"),
                    Surface(kind="text", payload="    movzbq %al, %rax"),
                )),
                binding_pattern=["a", "b"])

        # --- Mod: idivq sequence; remainder ends in %rdx → mov to %rax
        self.install_render_rule(
            language, "Mod",
            template=Lines(items=(
                Render(term=Slot(name="b")),
                Surface(kind="text", payload="    pushq %rax"),
                Render(term=Slot(name="a")),
                Surface(kind="text", payload="    popq %rcx"),
                Surface(kind="text", payload="    cqto"),
                Surface(kind="text", payload="    idivq %rcx"),
                Surface(kind="text", payload="    movq %rdx, %rax"),
            )),
            binding_pattern=["a", "b"])

        # --- Minus
        self.install_render_rule(
            language, "Minus",
            template=Lines(items=(
                Render(term=Slot(name="b")),
                Surface(kind="text", payload="    pushq %rax"),
                Render(term=Slot(name="a")),
                Surface(kind="text", payload="    popq %rcx"),
                Surface(kind="text", payload="    subq %rcx, %rax"),
            )),
            binding_pattern=["a", "b"])

        # --- Variadic ops: 2-item form (factorial only needs binary).
        # For 3+ items, a future folder primitive lands as its own commit;
        # the agent's existing render-gap → impasse loop will surface the
        # need when a 3-item Term tries to render.
        for head, op_instr in (("Plus", "addq"), ("Times", "imulq")):
            self.install_render_rule(
                language, head,
                template=Lines(items=(
                    Render(term=Nth(items=Slot(name="items"), index=0)),
                    Surface(kind="text", payload="    pushq %rax"),
                    Render(term=Nth(items=Slot(name="items"), index=1)),
                    Surface(kind="text", payload="    popq %rcx"),
                    Surface(kind="text", payload=f"    {op_instr} %rcx, %rax"),
                )),
                binding_pattern=["items"])

        # --- IfThenElse: fresh else + end labels via Let/Label; the body
        # references them via Var. Same structure the static emitter used.
        self.install_render_rule(
            language, "IfThenElse",
            template=Let(
                name="else_lbl",
                value=Label(prefix="else"),
                body=Let(
                    name="end_lbl",
                    value=Label(prefix="end"),
                    body=Lines(items=(
                        Render(term=Slot(name="cond")),
                        Surface(kind="text", payload="    testq %rax, %rax"),
                        Cat(items=(Surface(kind="text", payload="    jz "),
                                   Var(name="else_lbl"))),
                        Render(term=Slot(name="then")),
                        Cat(items=(Surface(kind="text", payload="    jmp "),
                                   Var(name="end_lbl"))),
                        Cat(items=(Var(name="else_lbl"),
                                   Surface(kind="text", payload=":"))),
                        Render(term=Slot(name="other")),
                        Cat(items=(Var(name="end_lbl"),
                                   Surface(kind="text", payload=":"))),
                    )),
                ),
            ),
            binding_pattern=["cond", "then", "other"])

        # --- Holds: recursive call; save/restore %rdi around the call site
        self.install_render_rule(
            language, "Holds",
            template=Lines(items=(
                Render(term=Slot(name="node")),
                Surface(kind="text", payload="    pushq %rdi"),
                Surface(kind="text", payload="    movq %rax, %rdi"),
                Cat(items=(Surface(kind="text", payload="    call "),
                           Slot(name="concept"))),
                Surface(kind="text", payload="    popq %rdi"),
            )),
            binding_pattern=["concept", "node", "node2"])

        return lang_id

    # --- teach a renderer through render-gap -> self-teacher -> absorb --------

    def set_self_teacher(self, fn):
        """Register a teacher callable consulted on render gaps. `fn(question) ->
        {"answer": ..., "learn": [{"rule": {language, head, template, binding_pattern}}]}`."""
        self._self_teacher = fn

    def _spec_to_renderer_term(self, spec):
        """Convert a nested-list RENDER template spec to a DSL Term (Cat/Surface/
        Slot/Render/Join/Nth/Lines/Let/Label/Lit/Var). Mechanical translation of
        a teacher-supplied template into the graph-resident Term the engine runs."""
        from substrate import (Cat, Surface, Slot, Render, Join, Nth, Lines,
                                Let, Label, Lit, Var)
        head, rest = spec[0], spec[1:]
        S = self._spec_to_renderer_term
        if head == "Cat":
            return Cat(items=tuple(S(s) for s in rest))
        if head == "Lines":
            return Lines(items=tuple(S(s) for s in rest))
        if head == "Surface":
            return Surface(kind=rest[0], payload=rest[1])
        if head == "Slot":
            return Slot(name=rest[0])
        if head == "Render":
            return Render(term=S(rest[0]))
        if head == "Join":
            return Join(separator=S(rest[0]), items=S(rest[1]))
        if head == "Nth":
            return Nth(items=S(rest[0]), index=rest[1])
        if head == "Let":
            return Let(name=rest[0], value=S(rest[1]), body=S(rest[2]))
        if head == "Label":
            return Label(prefix=rest[0])
        if head == "Lit":
            return Lit(rest[0])
        if head == "Var":
            return Var(rest[0])
        raise KeyError(f"unknown renderer template head '{head}'")

    def render_in_graph(self, source, language):
        """Render `source` (a Term) in `language` via the Rust engine, gated by a
        DFS pre-check: if any sub-term head lacks a RenderRule in `language`,
        record a `render_gap:<head> in <language>` question for the self-teacher
        and return None (the engine would emit a partial surface otherwise).
        Else returns {"kind": "text", "payload": <surface>}."""
        import dataclasses as _dc
        self._ensure_inherited(language)   # pull in parent-chain rules first
        seen, missing = set(), []
        def walk(t):
            if not _dc.is_dataclass(t):
                return
            h = type(t).__name__
            if h not in seen:
                seen.add(h)
                if not self.render_rules_for(language, h):
                    missing.append(h)
            for f in _dc.fields(t):
                v = getattr(t, f.name)
                if _dc.is_dataclass(v):
                    walk(v)
                elif isinstance(v, (list, tuple)):
                    for x in v:
                        walk(x)
        walk(source)
        if missing:
            gaps = getattr(self, "_render_gaps", None)
            if gaps is None:
                gaps = self._render_gaps = []
            for h in missing:
                q = "render_gap:%s in %s" % (h, language)
                if q not in gaps:
                    gaps.append(q)
                # an Impasse node makes the gap graph-resident + diagnosable
                # (the agent's impasse-resolver / teacher loop reads these).
                already = any(
                    self.s.node(i)["attrs"].get("render_gap_head") == h
                    and self.s.node(i)["attrs"].get("render_gap_lang") == language
                    for i in self.impasses())
                if not already:
                    self.s.add_node("Impasse", {"reason": "render_gap",
                                                "render_gap_head": h,
                                                "render_gap_lang": language,
                                                "question": q})
            return None
        surface = self.render(source, language)
        if surface is None:
            return None
        return {"kind": "text", "payload": surface}

    def drain_all_taught_threads(self, timeout: float = 2.0) -> int:
        """The self-teaching reflex: consult the self-teacher for every pending
        impasse and absorb what it returns. Two impasse channels:

          • render gaps (`_render_gaps`, populated by render_in_graph) — absorb
            the returned RenderRule spec(s) via install_render_rule;
          • any other unresolved Impasse node that carries a free-text
            `question` — absorb via learn_from_teacher (a `rule` OR a `phrase`
            grounding) and mark it resolved.

        Returns the number of items absorbed. The teacher decides the answer;
        the adapter only installs it as graph data."""
        teacher = getattr(self, "_self_teacher", None)
        # 0) async channel — block on teacher threads master_tick spawned
        # off-thread (non-blocking), then absorb their results on this thread.
        for tt in list(getattr(self, "_teacher_threads", [])):
            tt["thread"].join(timeout)
        self._drain_completed_teacher_threads()
        if teacher is None:
            return 0
        absorbed = 0
        # 1) render-gap channel — RenderRule specs keyed by source-Term head.
        for q in list(getattr(self, "_render_gaps", None) or []):
            ans = teacher(q) or {}
            for item in ans.get("learn", []):
                rule = (item or {}).get("rule")
                if not rule:
                    continue
                self.install_render_rule(
                    rule["language"], rule["head"],
                    self._spec_to_renderer_term(rule["template"]),
                    rule["binding_pattern"])
                absorbed += 1
        self._render_gaps = []
        # 2) general impasse channel — free-text questions → learn_from_teacher.
        # Render-gap impasses (render_gap_head) are channel 1; in-flight ones are
        # owned by the async channel above.
        for imp in self.impasses():
            attrs = self.s.node(imp)["attrs"]
            if (attrs.get("render_gap_head") is not None or attrs.get("resolved")
                    or attrs.get("teaching_in_flight")):
                continue
            q = attrs.get("question")
            if not q:
                continue
            ans = teacher(q)
            if ans:
                self.learn_from_teacher(q, ans)   # returns the answer, not a count
                absorbed += 1
            self.mark_impasse_resolved(imp)
        return absorbed

    def _spawn_teacher_thread(self, imp):
        """Spawn an off-thread self-teacher call for one impasse (non-blocking) —
        the agent keeps ticking while a slow teacher (LLM round-trip) runs. The
        teacher call is the only off-thread work; its result is ABSORBED on the
        master thread by _drain_completed_teacher_threads (graph mutation stays
        single-threaded). Mechanical I/O scheduling, no decisions."""
        import threading
        teacher = getattr(self, "_self_teacher", None)
        q = self.s.node(imp)["attrs"].get("question")
        if teacher is None or not q:
            return
        holder = {"result": None, "done": False}

        def run():
            try:
                holder["result"] = teacher(q)
            finally:
                holder["done"] = True
        th = threading.Thread(target=run, daemon=True)
        self.inner.set_attr(imp, "teaching_in_flight", True)
        if not hasattr(self, "_teacher_threads"):
            self._teacher_threads = []
        self._teacher_threads.append({"imp": imp, "q": q, "holder": holder,
                                      "thread": th})
        th.start()

    def _drain_completed_teacher_threads(self):
        """Absorb the results of any FINISHED teacher threads (learn + mark the
        impasse resolved); leave in-flight ones. Runs on the master thread."""
        still = []
        for tt in getattr(self, "_teacher_threads", []):
            if not tt["holder"]["done"]:
                still.append(tt)
                continue
            res = tt["holder"]["result"]
            imp = tt["imp"]
            if res:
                # frontier-stall impasses (the speech-autonomy teacher path) carry no
                # render/phrase `learn` payload — record the method-advice on the impasse
                # so the seeded ground_hint_to_investigation rule mints a new axis to TEST.
                # Mechanical write of the answer text; the GROUNDING is a graph rule.
                if self.s.node(imp)["attrs"].get("kind") == "frontier_stall":
                    ans = res.get("answer") if isinstance(res, dict) else str(res)
                    try:
                        self.inner.set_attr(imp, "advice", ans or "")
                        self.inner.set_attr(imp, "advice_ready", 1)
                        # DISTINCT-FRONTIER: extract the distinguishing CUE from the advice (a
                        # thin I/O-boundary classifier — the only adapter step) into a Cue node
                        # carrying DISTINCT keys (parent keys + cue). The grounding Rule mints one
                        # frontier per cue and DEDUPS by it, so the same advice no longer
                        # proliferates identical copies; different advice -> different frontiers.
                        cue = self._advice_cue_node(imp, ans or "")
                        if cue is not None:
                            self.inner.add_edge_unchecked(imp, "names_cue", cue)
                    except Exception:
                        pass
                elif isinstance(res, dict):
                    # structured render/phrase teaching payload (the original path).
                    self.learn_from_teacher(tt["q"], res)
                # else: a plain-string teacher answer for some other impasse kind — record
                # it on the impasse, but do NOT feed it to learn_from_teacher (which wants a
                # structured payload). The agent's own rules decide what to do with it.
                else:
                    try:
                        self.inner.set_attr(imp, "advice", str(res))
                    except Exception:
                        pass
            self.mark_impasse_resolved(imp)
        self._teacher_threads = still

    _CUE_STOP = frozenset({
        "the", "and", "for", "with", "try", "use", "its", "your", "you", "that", "this",
        "what", "should", "next", "then", "more", "most", "than", "into", "over", "under",
        "acoustic", "approach", "speech", "sound", "audio", "distinguishing", "method",
        "feature", "detector", "cue", "between", "based", "using", "could", "would", "from",
        "each", "them", "their", "which", "where", "when", "have", "will", "must", "some"})

    def _advice_cue_node(self, imp, advice):
        """Thin I/O-boundary classifier: turn the teacher's free-text advice into the smallest
        graph token — the distinguishing CUE (its 1-2 most salient content words) — and find-or-
        create an AdviceCue node carrying DISTINCT capability_keys (the stalled axis's keys + the
        cue). Same advice -> same cue node (dedup); different advice -> different cue (distinct
        frontier). The grounding DECISION stays in the rule; this only mints the token."""
        import re
        words = [w for w in re.sub(r"[^a-z ]", " ", (advice or "").lower()).split()
                 if len(w) > 3 and w not in self._CUE_STOP]
        token = "_".join(words[:2]) if words else "generic"
        for c in self.s.nodes("AdviceCue"):
            if self.s.node(c)["attrs"].get("token") == token:
                return c
        parent = list(self.s.node(imp)["attrs"].get("for_frontier") or [])
        return self.s.add_node("AdviceCue", {"token": token, "capability_keys": parent + [token],
                                             "origin": "advice_cue"})

    # --- sign-based production: render a relational meaning via the lexicon ---

    def install_relations_renderer(self):
        """Install the generic relational render language: a Relation rule
        (`left form right`) and a Leaf rule (`form`). One pair of RenderRules
        renders any relational meaning — the per-relation word (and any marker)
        rides on the meaning node's `form` attr (bound as a scalar slot), so the
        Rust Render engine folds the whole tree. Idempotent."""
        from substrate import Cat, Surface, Slot, Render
        if self.render_rules_for("relations", "Relation"):
            return self.install_language("relations")
        s = lambda p: Surface(kind="text", payload=p)
        self.install_render_rule(
            "relations", "Relation",
            template=Cat(items=(Render(term=Slot(name="left")), s(" "),
                                Slot(name="form"), s(" "),
                                Render(term=Slot(name="right")))),
            binding_pattern=["left", "form", "right"])
        self.install_render_rule(
            "relations", "Leaf", template=Cat(items=(Slot(name="form"),)),
            binding_pattern=["form"])
        # Predicate-argument rule (`form arg`): a predicate with one named-role
        # argument, e.g. {believe: {of: X}} -> "believe of X". The predicate
        # word + role marker ride baked on `form` ("believe of"); the single
        # argument renders on the `arg` slot.
        self.install_render_rule(
            "relations", "Pred",
            template=Cat(items=(Slot(name="form"), s(" "),
                                Render(term=Slot(name="arg")))),
            binding_pattern=["form", "arg"])
        return self.install_language("relations")

    def learn_sign(self, form, concept, marker=""):
        """Add a Sign to the lexicon: a graph-resident node binding a `concept`
        to its surface `form` (+ optional `marker` particle for marked relations,
        e.g. runs_on -> 'runs' + 'on'). Deduped by form (find-or-create), so a
        re-teach of the same word doesn't pile up duplicate signs. Mechanical."""
        for n in self.s.nodes("Sign"):
            if self.s.node(n)["attrs"].get("form") == form:
                return n
        return self.s.add_node("Sign", {"form": form, "concept": concept,
                                        "marker": marker})

    def _sign_for(self, concept):
        """(form, marker) for a concept from the lexicon, or (concept, '')."""
        for n in self.s.nodes("Sign"):
            a = self.s.node(n)["attrs"]
            if a.get("concept") == concept:
                return a.get("form", concept), a.get("marker", "")
        return concept, ""

    def _meaning_to_graph(self, m):
        """Mirror an external meaning into a Term.Relation / Term.Leaf subgraph
        (mechanical I/O translation, resolving each concept to its sign form).
        A string is a leaf concept; a {concept: {left, right}} dict is a binary
        relation. The word order / surface is decided by the RenderRules, not
        here — this only mirrors structure."""
        if isinstance(m, str):
            form, _ = self._sign_for(m)
            return self.s.add_node("Term.Leaf", {"form": form})
        concept = next(k for k in m if k != "force")
        args = m[concept]
        form, marker = self._sign_for(concept)
        if isinstance(args, dict) and "left" in args and "right" in args:
            full = form + (" " + marker if marker else "")
            node = self.s.add_node("Term.Relation", {"form": full})
            self.inner.add_edge_unchecked(
                node, "child.left", self._meaning_to_graph(args["left"]))
            self.inner.add_edge_unchecked(
                node, "child.right", self._meaning_to_graph(args["right"]))
            return node
        # Predicate-argument: a single named role, e.g. {believe: {of: X}}.
        # The role word is the connector ("of"); the predicate's sign form +
        # the role bake onto `form`, the single argument renders recursively.
        role = next(k for k in args if k != "force")
        arg = args[role]
        full = form + (" " + marker if marker else "") + " " + str(role)
        node = self.s.add_node("Term.Pred", {"form": full})
        self.inner.add_edge_unchecked(
            node, "child.arg", self._meaning_to_graph(arg))
        return node

    def _render_node(self, node):
        """Render a meaning subgraph node to surface via the relational engine."""
        lang = self.install_relations_renderer()
        return self.inner.evaluate(
            {"type": "Render", "term": {"type": "Var", "name": "src"},
             "lang": {"type": "Var", "name": "render_lang"}},
            {"src": node, "render_lang": lang})

    def utterance_for(self, meaning):
        """Render a relational meaning to its surface string via the lexicon +
        the graph-resident relational RenderRules. The structure is mirrored to
        graph; the rendering is the Rust Render engine."""
        out = self._render_node(self._meaning_to_graph(meaning))
        if isinstance(meaning, dict) and meaning.get("force") == "ask" and out:
            out += "?"
        return out

    # --- factual Q&A: answer 'what is X?' from a known fact (definitional) ----

    def learn_fact(self, meaning):
        """Store a relational fact the agent knows: mirror the meaning to a
        persistent Term.Relation subgraph and tag it with a `knows_fact` edge
        from the agent. Mechanical — the fact is graph data the agent can later
        retrieve and render as an answer."""
        node = self._meaning_to_graph(meaning)
        self.inner.add_edge_unchecked(self.agent, "knows_fact", node)
        return node

    def answer_about(self, subject):
        """Render a known fact whose subject (the relation's left leaf) is
        `subject`, or None if the agent knows no such fact. The definitional
        slice of question-answering: 'what is X?' -> a fact about X, rendered by
        the graph engine. (Full answer_within — Frame recognition + capability
        dispatch + math kernels — stays the heavier reason.py faculty.)"""
        for fact in self.inner.neighbours(self.agent, "knows_fact"):
            left = self.inner.neighbours(fact, "child.left")
            if left and self.s.node(left[0])["attrs"].get("form") == subject:
                return self._render_node(fact)
        # Fall back to a meaning the agent was TAUGHT (learn_from_teacher memoised it under
        # `taught_<form>` in taught_capabilities) — so a word grounded from the interlocutor in
        # conversation is answerable through the SAME question path as a known fact. Retrieval of
        # graph-resident knowledge, not a decision.
        concept = "taught_" + str(subject).lower().replace("-", "_").replace(" ", "_")
        caps = self.taught_capabilities()
        if concept in caps:
            try:
                ans = caps[concept](None)
            except Exception:
                ans = None
            if ans is not None:
                return ans
        return None

    def answer_question(self, text):
        """Answer a question. A SELF/META question ('how are you organised', 'how do you modify yourself',
        'what are your limits') routes to the agent's own reflective faculties over its REAL graph state and is
        surfaced through this same chat reply path — content from the graph, never authored prose. A world
        'what is X?' question is the existing graph-retrieval + render path.

        FRONT END: `comprehend_text.comprehend_text` (domains/comprehend_text.py) — the held construction
        TABLE first (fast path, byte-identical to the prior behaviour below), then the GENERAL gap-as-part-
        of-speech parser + relation composer for whatever the table does NOT ground (including a reflexive
        self-question the table has no fragment for, e.g. 'Tell me about the rule hop_descend_gradient' or
        'can you describe how you're put together?'). Both paths bottom out in the SAME reflect()/
        answer_about() backend — comprehend_text only decides WHICH faculty + WHAT argument, never renders."""
        from domains import reflective_faculty as _rf
        try:
            from domains import comprehend_text as _ct
            comp = _ct.comprehend_text(self, text)
        except Exception:
            comp = None
        if comp is not None:
            if comp.fastpath:
                spec = comp.table_spec
                mt = getattr(spec, "meta_target", None)
                if getattr(spec, "kind", None) == "meta" and mt in _rf._DISPATCH:
                    state = _rf.reflect(mt, getattr(spec, "meta_arg", None), self.s)
                    return self._surface_self_state(state)
            else:
                d = comp.dispatch or {}
                if d.get("path") == "meta" and d.get("meta_target") in _rf._DISPATCH:
                    state = _rf.reflect(d["meta_target"], d.get("meta_arg"), self.s)
                    return self._surface_self_state(state)
                if d.get("path") == "honest_self":
                    return self._honest_self_reply(comp)
                if d.get("path") == "know":
                    ans = d.get("pre_resolved")
                    if not ans and d.get("concept"):
                        ans = self.answer_about(d["concept"])
                    if ans is not None:
                        return ans
        import re
        m = re.search(r"what(?:'s|s| is| are| was)\s+(?:a |an |the )?(.+?)\s*\??$",
                      text.strip(), re.IGNORECASE)
        subject = (m.group(1) if m else text).strip().rstrip("?").strip()
        return self.answer_about(subject)

    # corpus that GROUNDS the self-account vocabulary + MORPHOLOGY (inflected forms) for production. No LLM —
    # the stub teacher learns word order + each verb's 3sg-present form from these examples (as it learns
    # "loves"/"sat" in the grammar bank). Content of the reply is built from REAL state; these only teach words.
    # The agent speaks about ITSELF, so the self-account is FIRST PERSON ("I
    # modify the rule"), not the generic third-person "the agent" — it has an
    # identity (it is named Jabberwock; see jabberwock_identity.json) and refers
    # to itself accordingly. First-person-singular present is the BARE verb in
    # English ("I modify", not "modifies"), so morphology falls out for free.
    # Each sentence debuts ONE new verb + ONE new noun, so the world's coverage
    # probe (teacher fires only when grounded-lexicon coverage < 0.6) stays low
    # and the teacher grounds BOTH words. Production then composes frames the
    # corpus never showed (e.g. hold+rule).
    _SELF_ACCOUNT_CORPUS = [
        {"text": "I modify the rule.", "language": "en",
         "expected_meaning": {"event": "modify", "agent": "I", "patient": "rule", "tense": "present"}},
        {"text": "I hold the microtheory.", "language": "en",
         "expected_meaning": {"event": "hold", "agent": "I", "patient": "microtheory", "tense": "present"}},
        {"text": "I ground the term.", "language": "en",
         "expected_meaning": {"event": "ground", "agent": "I", "patient": "term", "tense": "present"}},
        {"text": "I compose the faculty.", "language": "en",
         "expected_meaning": {"event": "compose", "agent": "I", "patient": "faculty", "tense": "present"}},
        # the copular naming construction, so the identity reply is PRODUCED from
        # the graph's substrate_name datum (not a Python f-string). "Jabberwock"
        # is the proper-noun filler; the actual name comes from the graph.
        {"text": "I am Jabberwock.", "language": "en",
         "expected_meaning": {"event": "be", "agent": "I", "patient": "Jabberwock", "tense": "present"}},
    ]

    # the corpus vocabulary, keyed by surface -> concept|(concept,tense), so the
    # stub teacher grounds it like the bank's "loves"/"sat". First-person verbs
    # are bare, so the surface IS the lemma; "i" -> the first-person concept "I".
    _SELF_ACCOUNT_LEXICON = {
        "en": {
            "i": "I",
            "modify": ("modify", "present"), "compose": ("compose", "present"),
            "ground": ("ground", "present"), "hold": ("hold", "present"),
            "am": ("be", "present"), "jabberwock": "Jabberwock",
            "rule": "rule", "faculty": "faculty",
            "concept": "concept", "microtheory": "microtheory", "term": "term",
        },
    }

    def _self_account_producer(self):
        """Lazy-train + cache a LanguageProduction (NO LLM — stub teacher) over the grammar bank + the self-
        account corpus, so self/meta replies are GENERATED by the agent's production faculty, not listed."""
        prod = getattr(self, "_sa_producer", None)
        if prod is not None:
            return prod or None
        try:
            import os as _os, sys as _sys
            import substrate_rs as _srs
            from domains.language_world import LanguageWorld, make_stub_teacher
            from domains.language_production import LanguageProduction
            _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from scripts.language_test import training_bank
            # NO LLM — the stub teacher, extended so the self-account corpus's
            # INFLECTED verb surfaces (modifies/composes/grounds/holds) ground
            # against their concepts (like the bank's "loves"/"sat"); that is
            # what makes production emit the inflected form, not the bare lemma.
            teacher = make_stub_teacher(self._SELF_ACCOUNT_LEXICON)
            world = LanguageWorld(_srs._native.Substrate(),
                                  list(training_bank()) + self._SELF_ACCOUNT_CORPUS, teacher)
            world.run()
            prod = LanguageProduction(world)
        except Exception:
            prod = False                                          # mark unavailable; fall back to terse
        self._sa_producer = prod
        return prod or None

    def _self_account_frames(self, state):
        """Build goal frames FROM the real self-state: capability frames gated on real graph presence (it really
        modifies rules / grounds concepts this session), plus inventory frames for the categories it holds.

        Also covers the self_model.py self-query shapes ('what does <rule> do?' / 'which parts of me touch
        <attr>?'): a HEADLINE frame ('I hold the rule.') through the production faculty. The rule's specific
        name / match / reads / writes are beyond this tiny closed-vocabulary corpus (they name arbitrary held
        rules, not the fixed noun set 'rule'/'term'/'faculty'/'microtheory'/'concept' this grammar was taught),
        so those facts stay carried by the faculty's own graph-grounded `note` — `_surface_self_state` appends
        it after this produced headline, never dropping them."""
        frames = []
        mm = state.get("modifiable_machinery") or state.get("composable_machinery") or {}
        if mm.get("rules"):
            frames.append({"event": "modify", "agent": "I", "patient": "rule", "tense": "present", "intent": "inform"})
            frames.append({"event": "hold", "agent": "I", "patient": "rule", "tense": "present", "intent": "inform"})
        if mm.get("microtheories"):
            frames.append({"event": "hold", "agent": "I", "patient": "microtheory", "tense": "present", "intent": "inform"})
        if mm.get("term_variants"):
            frames.append({"event": "hold", "agent": "I", "patient": "term", "tense": "present", "intent": "inform"})
        smq = state.get("self_model_query")
        if smq == "rule" and state.get("found"):
            frames.append({"event": "hold", "agent": "I", "patient": "rule", "tense": "present", "intent": "inform"})
        elif smq == "touches" and state.get("count"):
            frames.append({"event": "hold", "agent": "I", "patient": "rule", "tense": "present", "intent": "inform"})
        return frames

    _NOTE_MACHINE_TAIL_RE = _re.compile(r";\s*[A-Za-z_][A-Za-z0-9_]*=")

    @classmethod
    def _clean_self_note(cls, note):
        """A faculty's `note` is already agent-authored prose (self_model.py / reflective_faculty.py compose it
        as a fluent sentence, deliberately FIRST among a state's keys for exactly this rendering path — see
        self_model.py's `_describe_rule_summary` comment). Defensively strip a leading 'note=' echo or a
        trailing ' key=value; key2=value2' machine tail, should a faculty ever append one; a note's own prose
        clauses ('it fires when ...; it reads ...') never match ('; word=' requires a literal '=', which a
        prose clause doesn't contain) so real sentences pass through untouched."""
        if not isinstance(note, str):
            return None
        n = note.strip()
        if n.lower().startswith("note="):
            n = n[len("note="):].strip()
        m = cls._NOTE_MACHINE_TAIL_RE.search(n)
        if m:
            n = n[:m.start()].rstrip("; ").strip()
        return n or None

    def _surface_self_state(self, state):
        """Render a reflective faculty's REAL self-state as a chat reply — NEVER a raw k=v dict dump. Priority:
        (a) frames from real state -> the production faculty (produce()) -> fluent sentence(s); (b) the state's
        own `note` (a faculty-authored, graph-grounded prose sentence — the honest fluent account for richly-
        structured states this tiny production grammar can't losslessly frame, e.g. the seven-meta-shape
        decomposition); a produced headline and a note are BOTH kept when both exist, so a produced generic
        sentence ('I hold the rule.') never drops the note's specific facts (rule name / match / reads / writes).
        (c) only if there is neither a frame nor a note, a terse factual statement built from real state — still
        never a raw dict. Content is always the graph's real data; the words are the production grammar's or the
        faculty's own, never authored here."""
        if not isinstance(state, dict) or "unwired" in state:
            return state.get("unwired") if isinstance(state, dict) else str(state)
        prod = self._self_account_producer()
        # identity — PRODUCE the reply from the graph's self-name datum via the
        # language faculty (copular frame), not a Python-assembled string.
        if state.get("identity_name") and prod is not None:
            frame = {"event": "be", "agent": "I", "patient": state["identity_name"],
                     "tense": "present", "intent": "inform"}
            try:
                overt = (prod.produce("en", frame) or {}).get("overt_speech")
            except Exception:
                overt = None
            if overt:
                return overt
        frames = self._self_account_frames(state)
        produced = []
        if prod is not None and frames:
            for f in frames:
                try:
                    overt = (prod.produce("en", f) or {}).get("overt_speech")
                except Exception:
                    overt = None
                if overt:
                    produced.append(overt)
        note = self._clean_self_note(state.get("note"))
        # self_model_topic's note ELIDES its own listed matches down to 12 (see
        # self_model.py's `run_self_model_topic`, "shown = hits[:12]") — a
        # readable HEADLINE, not the full inventory. Content preservation (a
        # named rule anywhere in the real match set, not just the first 12) needs
        # the fuller list `matches` already carries (same 40-item cap the old raw
        # dict happened to expose); append it as real-state fact, not authored
        # prose, so a rule named e.g. 60th-alphabetically is still in the reply.
        if state.get("self_model_query") == "topic" and isinstance(state.get("matches"), list):
            full = ", ".join(state["matches"][:40])
            if full:
                note = (note + " (full list: " + full + ")") if note else \
                    f"I have {state.get('count', len(state['matches']))} rule(s) about it: {full}"
        # self_organisation's own area listing: a pre-existing, already-fluent,
        # FIRST-PERSON rendering that names every held item by name (its `note`
        # is a generic third-person summary sentence with no item names in it) —
        # kept ahead of the generic note when there is no produced frame for this
        # state (self_organisation carries no modifiable/composable_machinery, so
        # `frames`/`produced` are always empty here; this branch never fires for
        # the machinery states, which route through `produced` below instead).
        # register-shaped, SMOOTH delivery: the substantive self-account is joined
        # into connected prose (never bare per-item fragments), and its elaboration
        # matches the interlocutor's tracked register (formal -> restated subject;
        # casual/neutral -> one collapsed subject). SELECTION is the agent's (read
        # off its own register model); the connective join is mechanical.
        try:
            from domains import conversation_action as _ca
            reg = self.register()
        except Exception:
            _ca, reg = None, "neutral"
        if not produced and state.get("areas"):
            areas = [str(a) for a in state["areas"][:12]]
            # MANIFOLD-RELATIVE CONTENT: shape the self-organisation areas RELATIVE to the tracked
            # interlocutor's manifold before rendering (domains.audience_adaptation) — modern-technical
            # domains foreign to a period/non-technical manifold (a Victorian-typed interlocutor) are
            # abstracted to an umbrella instead of dumped flat; a technical / default / unobserved
            # manifold adapts NOTHING (byte-identical, no regression). The DECISION of which concepts
            # are foreign is the module's manifold residual — this only passes areas through it.
            try:
                from domains import audience_adaptation as _aa
                areas = _aa.adapt_concepts(self, areas, self._delivery_snapshot())["adapted"]
            except Exception:
                pass
            body = _ca._oxford(areas) if _ca is not None else ", ".join(areas)
            return "I am organised into " + body
        if _ca is not None and produced:
            smoothed = _ca.smooth_first_person(produced, reg)
            return (smoothed + " " + note) if note else smoothed
        if produced and note:
            return " ".join(produced) + " " + note
        if produced:
            return " ".join(produced)
        if note:
            return note
        # (c) terse machinery-count fallback — only reached when the production
        # faculty itself is unavailable (prod is None/False), so no frame could
        # be produced even though real inventory counts exist.
        parts = []
        for key in ("composable_machinery", "modifiable_machinery"):
            m = state.get(key)
            if isinstance(m, dict):
                parts.append(", ".join(f"{v} {k}" for k, v in m.items()))
        if parts:
            return "; ".join(parts)
        # last resort: no frame, no note, no known inventory shape — state a plain fact
        # value (never a 'key=value' pair) so the reply is still prose, not a dict dump.
        for v in state.values():
            if isinstance(v, str) and v.strip() and " " in v.strip():
                return v.strip()
        return "I hold real state for that, but no fluent account of it yet."


    # --- structural-triple discovery + saturation tallies (multi-world) ----

    def observe_structure(self, world_substrate) -> None:
        """Count the STRUCTURAL (src_type, edge_type, tgt_type) triples present in
        a world substrate — including between id-less world nodes (e.g. Conway's
        AliveCell/DeadCell, which carry row/col but no `id` and so are sensed but
        never instanced by `ingest`). This is the mechanical analogue of
        `CuriousAgent.triple_counts`: every typed edge bumps its type-triple's
        tally, and the node types are sensed. Pure observation bookkeeping — no
        decisions over graph state (the threshold that turns a tally into a
        production is the seeded `discovery_triple_threshold` policy, read in
        `grow_structural_grammar`)."""
        wg = world_substrate.graph
        for wn in wg.nodes():
            if wn.type.startswith("Term."):
                continue
            self._sensed_types.add(wn.type)
            for e in wg.out_edges(wn.id):
                tgt = wg.node(e.key.tgt)
                if tgt is None or tgt.type.startswith("Term."):
                    continue
                key = (wn.type, e.key.edge_type, tgt.type)
                self._triple_count[key] = self._triple_count.get(key, 0) + 1

    def grow_structural_grammar(self) -> set:
        """Reify every structural triple seen at least `discovery_triple_threshold`
        times (the seeded scalar policy) into a new Γ production admitting
        `(src_type)-[rel_id]->(tgt_type)`, plus a `structural_triple` Pattern node,
        via the same `_grow_grammar` path the relation-promotion uses. Returns the
        set of SRC node types that gained a grown production. Mirrors the
        triple-discovery branch of `CuriousAgent.grow_gamma`: the DECISION (the
        threshold) is graph-resident policy data; the adapter only counts and
        reifies. Re-running updates counts, no duplicate rel ids."""
        threshold = int(self.get_scalar_policy("discovery_triple_threshold", 30))
        grown_src_types: set = set()
        for key, count in list(self._triple_count.items()):
            if count < threshold:
                continue
            src_type, _edge_type, tgt_type = key
            existing = self._triple_to_rel.get(key)
            if existing is not None:
                self._discovered_relations[existing]["count"] = count
                grown_src_types.add(src_type)
                continue
            self._rel_seq += 1
            rid = f"rel_{self._rel_seq}"
            self._discovered_relations[rid] = {
                "shape": "structural_triple", "from_type": src_type,
                "to_type": tgt_type, "count": count}
            self._triple_to_rel[key] = rid
            self._grow_grammar(rid, src_type, tgt_type, "structural_triple", count)
            grown_src_types.add(src_type)
        return grown_src_types

    def novelty_count(self, world_substrate) -> int:
        """Count novelty signal in ``world_substrate`` — pure mechanical
        counting that reads the SEEDED saturation predicate (no decisions).
        Two channels add: (1) a (type, attr) pair carrying a value not yet
        observed; (2) an id-bearing node whose WorldInstance is not yet
        saturated (the under-known-entity texture). Mirrors the per-(type,
        attr, value) + per-instance novelty bookkeeping; classification of
        "saturated" is the seeded Term-tree, this only tallies."""
        novel = 0
        for node in world_substrate.graph.nodes():
            if node.type.startswith("Term."):
                continue
            for k, v in node.attrs.items():
                if not isinstance(v, (int, str, bool)):
                    continue
                if k == "id":
                    # the id channel: a never-before-seen instance id is novel
                    # (the per-instance index is the adapter's record of seen ids).
                    if (node.type, str(v)) not in self._instances:
                        novel += 1
                elif v not in self._attr_values.get((node.type, k), set()):
                    novel += 1
            world_id = node.attrs.get("id")
            if world_id is not None:
                inst = self._instances.get((node.type, str(world_id)))
                if inst is not None and not self.is_instance_saturated(inst):
                    novel += 1
        return novel

    def boredom_count(self, world_substrate) -> int:
        """Count saturated observations in ``world_substrate`` — pure
        mechanical counting that reads the SEEDED saturation predicate (no
        decisions). Two channels add: (1) every attribute whose (type, attr)
        Attribute node is saturated; (2) every id-bearing node whose
        WorldInstance is saturated. Same policy, both scopes; this only
        tallies what the seeded predicate classifies."""
        boring = 0
        for node in world_substrate.graph.nodes():
            if node.type.startswith("Term."):
                continue
            for k, v in node.attrs.items():
                if isinstance(v, (int, str, bool)) and k != "id":
                    if self.is_saturated(node.type, k):
                        boring += 1
            world_id = node.attrs.get("id")
            if world_id is not None:
                inst = self._instances.get((node.type, str(world_id)))
                if inst is not None and self.is_instance_saturated(inst):
                    boring += 1
        return boring


    # --- batch-2 additive faculties (number grounding gate / persistence / insight) --

    def _term_attr_keys(self, term_json) -> set:
        """Every `Attr.key` a definition Term-tree refers to — read off the
        externally-supplied definition JSON by mechanical traversal (the I/O
        analogue of `CuriousAgent._term_references`' attribute channel). This is
        ingestion: reading a told definition for the attribute tokens it names,
        not a decision over graph state."""
        keys: set = set()
        def walk(t):
            if isinstance(t, dict):
                if t.get("type") == "Attr" and isinstance(t.get("key"), str):
                    keys.add(t["key"])
                for v in t.values():
                    walk(v)
            elif isinstance(t, (list, tuple)):
                for c in t:
                    walk(c)
        walk(term_json)
        return keys

    def _is_attr_perceived(self, key: str) -> bool:
        """Has the agent ever perceived an attribute named `key`? — a pure graph
        query: any non-Term node currently carrying it (the exact mirror of
        `CuriousAgent._is_attr_perceived`, the bookkeeping the grounding gate
        reads)."""
        for n in self.s.nodes():
            node = self.s.node(n)
            if node["type"].startswith("Term."):
                continue
            if key in node["attrs"]:
                return True
        return False

    def learn_word_grounds(self, name: str, definition_term_json: dict) -> bool:
        """Ground a taught word only if it is anchored in experience — every
        attribute its definition names must have been PERCEIVED. If anything is
        unmet the word is HELD (no Concept registered) rather than fabricated,
        mirroring `CuriousAgent.learn_word_term`'s grounding gate
        (`_unmet_dependencies` over `_is_attr_perceived`). Returns True iff it
        grounded. Pure mechanical admissibility bookkeeping — the gate reads
        graph state (what has been perceived), it makes no agent decision; the
        reasoning is still the Term the agent owns and evaluates."""
        unmet = [k for k in self._term_attr_keys(definition_term_json)
                 if not self._is_attr_perceived(k)]
        if unmet:
            return False
        self.learn_word(name, definition_term_json)
        return True

    # --- direct instance creation + lazy instance edge-type admission ---------

    def ensure_world_instance(self, world_type, world_id):
        """Find or create the WorldInstance keyed by (world_type, world_id) — the
        same instance token `ingest` mints, but addressable directly (without a
        world substrate to mirror). Mechanical: returns the SAME node on re-call
        (the (type,id)->NodeID index dedupes), wires `agent --knows--> instance`
        and `instance --instance_of--> BodyType`, exactly as `ingest` does. No
        decisions — pure world↔graph bookkeeping."""
        key = (world_type, str(world_id))
        inst = self._instances.get(key)
        if inst is not None:
            return inst
        inst = self.s.add_node("WorldInstance", {
            "world_type": world_type, "world_id": str(world_id), "n_observations": 0})
        self._instances[key] = inst
        self.inner.add_edge_unchecked(self.agent, "knows", inst)
        bt = self._body_types.get(world_type)
        if bt is None:
            bt = self.s.add_node("BodyType", {"name": world_type})
            self._body_types[world_type] = bt
        self.inner.add_edge_unchecked(inst, "instance_of", bt)
        return inst

    def ensure_instance_edge_type(self, edge_type):
        """Lazily admit a WorldInstance→WorldInstance edge-type into Γ (a new
        production) so the adapter may mirror that world relation between
        instances. Idempotent. Mechanical: this is the meta-grammar growth the
        runtime already does in `ingest`/`_grow_grammar`; the DECISION of which
        relations are worth admitting is the world's structure, not Python."""
        if edge_type in self._mirrored_edge_types:
            return
        try:
            self.inner.add_production({
                "src": {"type": "WorldInstance", "var": "s"},
                "edge_type": edge_type,
                "tgt": {"type": "WorldInstance", "var": "t"},
                "provenance": f"instance_edge:{edge_type}"})
        except Exception:
            pass
        self._mirrored_edge_types.add(edge_type)

    def add_instance_edge(self, src_inst, edge_type, tgt_inst):
        """Mirror a world relation between two instances, admitting its edge-type
        first (mechanical). Uses the GATED `add_edge` so the dynamic Γ admission
        is actually exercised."""
        self.ensure_instance_edge_type(edge_type)
        self.s.add_edge(src_inst, edge_type, tgt_inst)

    # --- persistence: the agent's graph as a durable artifact ----------------

    def save(self, path):
        """Serialise the whole mind to `path`: the graph (node/edge ids
        preserved), the dynamic Γ grammar (so lazily-admitted edge-types stay
        admissible after a load), the `add_rule` rule store (every rule
        the seed loader installed AND everything the agent authored at
        runtime — `export_rules` captures every slot, including tombstoned
        ones, so `RuleIdx`s stay stable across the round-trip), and the
        adapter's world↔graph I/O indexes (instances / taught concepts /
        admitted instance edge-types) as plain ints. Pure mechanical I/O —
        read graph state out, write bytes."""
        import json
        blob = {
            "agent": self.agent.value,
            "graph": self.s.graph_to_dict(),
            "grammar": self.s.grammar_to_json(),
            "rules": self.inner.export_rules(),
            "instances": [[t, wid, n.value]
                          for (t, wid), n in self._instances.items()],
            "concepts": [[name, n.value] for name, n in self._concepts.items()],
            # (SHAPE_AUDIT.md §4.2 fix) `_recursive_concepts` is a lazily-created
            # session index (see `learn_recursive_concept`) — `getattr(..., {})`
            # so a WorldAdapter that never taught a recursive concept still saves.
            "recursive_concepts": [[name, n.value] for name, n in
                                   getattr(self, "_recursive_concepts", {}).items()],
            "body_types": [[t, n.value] for t, n in self._body_types.items()],
            "mirrored_edge_types": sorted(self._mirrored_edge_types),
            "sensed_types": sorted(self._sensed_types),
        }
        with open(path, "w") as f:
            json.dump(blob, f)

    @classmethod
    def load(cls, path):
        """Reconstruct a WorldAdapter from a `save()` blob: restore the graph
        (node ids preserved), replay the saved Γ productions (the dynamic
        grammar), reinstall the `add_rule` rule store (everything the seed
        loader installed plus every rule the agent authored at runtime —
        without this the resumed agent has zero rules and can't converse;
        see `save`'s "rules" key / `Substrate.export_rules`), and rebuild the
        world↔graph indexes from the stored ints. Mechanical: no decisions,
        just translate bytes back into substrate + bookkeeping. The restored
        adapter can keep operating.

        Old checkpoints saved before the rule store was persisted have no
        "rules" key — those still load (the graph and Γ grammar are intact),
        just with a warning that the agent will boot rule-less until re-taught
        or re-seeded, rather than crashing on a missing key."""
        import json
        import logging
        import substrate_rs as srs
        with open(path) as f:
            blob = json.load(f)
        wa = cls.__new__(cls)
        s = srs.Substrate()
        s.graph_from_dict(blob["graph"])
        for p in blob["grammar"]["productions"]:
            try:
                # Mirror-free replay: `graph_from_dict` above already
                # restored any Γ-mirror nodes a prior `save()` dumped as
                # part of the graph. This loop's only job is to repopulate
                # `checker.grammar` (a separate Rust struct `graph_from_dict`
                # never touches) from the SEPARATE `grammar_to_json` snapshot
                # `save()` also wrote. Using the general (possibly
                # mirror-writing) `add_production` here would re-mint a
                # second mirror subgraph on every single load — unbounded
                # compounding growth, see GAMMA_PYO3_REROUTE_RESULTS.md §2.5
                # and GAMMA_LOAD_GROWTH_FIX_RESULTS.md.
                s._inner.add_production_no_mirror(p)
            except Exception:
                pass
        wa.s = s
        wa.inner = s._inner
        if "rules" in blob:
            # Investigated (IMPORT_RULES_NO_MIRROR_RESULTS.md): unlike the
            # Γ-production replay just above, this call does NOT need a
            # `_no_mirror` sibling today. `import_rules` (py.rs) and the
            # live-authoring PyO3 `add_rule` binding both call the SAME
            # Rust-inherent `Substrate::add_rule` (substrate.rs) — read in
            # full, it never writes a graph node (no `add_term_subgraph`,
            # no `rule_reflect.rs`; `declare_attr_index` is an in-memory
            # bookkeeping structure, not a graph mutation) — so replaying it
            # once per rule on every load is graph-inert, confirmed live
            # (flat node/edge/rule counts across 6 save/load cycles).
            # CONTRACT FOR ANY FUTURE RULE-MIRRORING BUILD: because
            # `import_rules` and the general `add_rule` binding share ONE
            # Rust-inherent function (not two layers, unlike Γ's
            # `add_production` / `Substrate::add_production` split before
            # its own fix), a mirror added directly inside
            # `Substrate::add_rule` would make checkpoint replay mirror too,
            # by construction, with no way to opt out short of re-splitting
            # the two callers apart. Any future rule-mirroring mechanism
            # MUST route through a mirror-free variant here (an
            # `import_rules_no_mirror`-shaped method), exactly as
            # `add_production_no_mirror` does three lines above — do not
            # let this call regress to mirroring silently.
            wa.inner.import_rules(blob["rules"])
        else:
            logging.getLogger(__name__).warning(
                "WorldAdapter.load(%s): checkpoint has no 'rules' key "
                "(saved before rule-store persistence) — resuming with "
                "ZERO installed rules; re-seed or re-teach to recover.",
                path,
            )
        wa.agent = srs.NodeID(blob["agent"])
        # rebuild the adapter's I/O indexes (NodeIDs by value)
        wa._instances = {(t, wid): srs.NodeID(v)
                         for t, wid, v in blob.get("instances", [])}
        wa._concepts = {name: srs.NodeID(v) for name, v in blob.get("concepts", [])}
        # (SHAPE_AUDIT.md §4.2 fix) restore the recursive-concept index the same
        # way `_concepts` is restored above — `.get(..., [])` so an OLD
        # checkpoint (saved before this fix, with no "recursive_concepts" key)
        # still loads cleanly (empty index; `learn_recursive_concept`'s
        # `_concept_by_name` fallback covers that case going forward).
        wa._recursive_concepts = {name: srs.NodeID(v)
                                  for name, v in blob.get("recursive_concepts", [])}
        wa._body_types = {t: srs.NodeID(v) for t, v in blob.get("body_types", [])}
        wa._mirrored_edge_types = set(blob.get("mirrored_edge_types", []))
        wa._sensed_types = set(blob.get("sensed_types", []))
        # vision I/O fields — never persisted; restored to unbuilt state (the
        # cortex rebuilds lazily on the next update_vision()).
        wa._eye = None
        wa._upload_eye = None
        wa._vision_substrate = None
        wa._vision_projection = []
        wa._shape_nodes = []
        wa._motion_depth_nodes = []
        wa._vision_motion_nodes = []
        wa._vision_salience_nodes = []
        wa._vision_held_residual_nodes = []
        wa._vision_foveal_exposure_nodes = []
        wa._vision_foveal_tile_nodes = []
        wa._vision_photon_counts = None
        wa._vision_layout_signature = None
        wa._vision_peripheral_layout_signature = None
        wa._vision_peripheral_layout = None
        wa._taught_lookup = {}   # memoised teacher answers are session-local
        wa._semiotic_definitions = {}
        wa._reindex_semiotic_definitions()   # rebuild computable defs from graph
        # `load()` bypasses `__init__` (`cls.__new__`), so the Wave 2 shadow-read
        # flag is never set by the constructor here — default OFF, exactly the
        # `__init__` default, so a resumed checkpoint never silently starts
        # paying the shadow-read cost. The daemon's `--shadow-read` flag (default
        # ON there) sets this explicitly right after `boot()`/`load()` either way.
        wa.shadow_read = False
        # Wave 4: `deep_ingest` follows the SAME bypass-`__init__` reasoning --
        # default OFF on a resumed checkpoint; the daemon sets it explicitly
        # (with `shadow_read`) right after `boot()`/`load()` either way.
        wa.deep_ingest = False
        return wa

    # --- insight: type-level promotion + category discovery (generalization) --

    def _instance_edge_counters(self, wi) -> dict:
        """Derive the per-instance ``in_<edge>`` / ``out_<edge>`` participation
        counters from the mirrored instance->instance edges `ingest` already
        creates (the migrated analogue of the per-instance edge tallies the old
        observe() stamped). Pure mechanical counting over graph edges — no
        decisions. Only edges between WorldInstances are counted (the mirrored
        world map)."""
        instances = set(self._instances.values())
        counters: dict = {}
        for et in self._all_instance_edge_types():
            n_out = sum(1 for t in self.inner.neighbours(wi, et) if t in instances)
            if n_out:
                counters[f"out_{et}"] = n_out
            n_in = sum(1 for s in self.inner.in_neighbours(wi, et) if s in instances)
            if n_in:
                counters[f"in_{et}"] = n_in
        return counters

    def _all_instance_edge_types(self) -> set:
        """Every edge type present between mirrored WorldInstances (read from the
        graph dump). Mechanical query over graph data."""
        instances = set(str(nid).lstrip("#") for nid in self._instances.values())
        types: set = set()
        for e in self.inner.graph_to_dict().get("edges", []):
            if e.get("type") == "instance_of":
                continue
            if str(e["src"]) in instances and str(e["tgt"]) in instances:
                types.add(e["type"])
        return types

    def insight(self) -> dict:
        """Periodic generalization pass (the old insight() layer 1's two
        graph-data operations): type-level promotion + category discovery.

        Both are mechanical aggregations over the mirrored WorldInstance graph
        that write graph data (a ``typical_<attr>`` flag on a BodyType, a new
        ``cat_*`` BodyType + ``instance_of`` edges). The DECISION threshold is
        the seeded ``insight_threshold`` policy (a Lit the agent reads), not a
        Python constant. No conditionals over agent state — only counting and
        reification, exactly as the old _promote_to_type_level /
        _discover_categories did. Returns ``{promoted, categories}``."""
        threshold = float(self.get_scalar_policy("insight_threshold", 0.7))
        promoted = self._promote_to_type_level(threshold)
        categories = self._discover_categories(threshold)
        return {"layer": 1, "promoted": promoted, "categories": categories}

    def _promote_to_type_level(self, threshold: float) -> list:
        """For each BodyType, write ``typical_<attr>`` to its node whenever that
        attribute (or in_/out_ edge counter) is present (truthy) on at least
        ``threshold`` fraction of its instances. Returns the (type_name,
        attr_name) pairs newly promoted this pass."""
        from collections import Counter
        by_type: dict = {}
        for (wt, _wid), wi in self._instances.items():
            bt = self._body_types.get(wt)
            if bt is not None:
                by_type.setdefault(bt, []).append(wi)
        skip_keys = {"world_type", "world_id", "n_observations",
                     "saturation_count"}
        promoted: list = []
        for bt, instance_ids in by_type.items():
            if len(instance_ids) < 2:
                continue
            presence: Counter = Counter()
            for wi in instance_ids:
                attrs = dict(self.s.node(wi)["attrs"])
                attrs.update(self._instance_edge_counters(wi))
                for k, v in attrs.items():
                    if k in skip_keys or k.startswith("act_"):
                        continue
                    if v is not None and v != 0 and v is not False and v != "":
                        presence[k] += 1
            bt_attrs = self.s.node(bt)["attrs"]
            for attr, count in presence.items():
                if count / len(instance_ids) >= threshold:
                    marker = f"typical_{attr}"
                    if marker not in bt_attrs:
                        self.inner.set_attr(bt, marker, True)
                        promoted.append((bt_attrs.get("name"), attr))
        return promoted

    def _discover_categories(self, threshold: float) -> list:
        """Cluster WorldInstances by edge fingerprint (the set of in_/out_ edge
        kinds they participate in). Each cluster of size >= 2 with >= 1 shared
        edge becomes a new ``cat_*`` BodyType; members gain an additional
        ``instance_of`` edge to it. Returns the (cat_name, size) clusters formed
        this pass."""
        fingerprints: dict = {}
        for (_wt, _wid), wi in self._instances.items():
            edges = frozenset(self._instance_edge_counters(wi).keys())
            if edges:
                fingerprints[wi] = edges
        by_fp: dict = {}
        for wi, fp in fingerprints.items():
            by_fp.setdefault(fp, []).append(wi)
        discovered: list = []
        for fp, members in by_fp.items():
            if len(members) < 2 or len(fp) < 1:
                continue
            cat_name = f"cat_{abs(hash(fp)) % 100000:05d}"
            if cat_name in self._body_types:
                continue  # already promoted in a prior pass
            cat_id = self._ensure_body_type(cat_name)
            for wi in members:
                exists = any(t == cat_id
                             for t in self.inner.neighbours(wi, "instance_of"))
                if not exists:
                    self.inner.add_edge_unchecked(wi, "instance_of", cat_id)
            discovered.append((cat_name, len(members)))
        return discovered


    # --- theorem discovery (promote tracked invariants to Theorems) -----------

    def _bootstrap_theorem_candidates(self) -> list:
        """The bootstrap theorem candidates: three fixed DSL Term-trees over the
        agent's own boundary edges (senses/models/acts_on cardinality compares).
        Pure graph data (`substrate.dsl` constructors), the simplest invariants a
        curious agent asks about its own structure — mirrors the bootstrap layer
        of `CuriousAgent._theorem_candidates`. (The arbitrary random-composition
        `cand_*` layer is genuine Python cognition and stays out of the adapter.)"""
        from substrate.dsl import Count, Gte, Neighbours, Var
        ag = Var("agent")
        return [
            {"name": "senses_ge_models",
             "predicate": Gte(Count(Neighbours(ag, "senses")),
                              Count(Neighbours(ag, "models"))),
             "description": "The agent senses at least as many body-types as it models."},
            {"name": "senses_ge_acts_on",
             "predicate": Gte(Count(Neighbours(ag, "senses")),
                              Count(Neighbours(ag, "acts_on"))),
             "description": "The agent senses at least as many body-types as it acts on."},
            {"name": "models_ge_acts_on",
             "predicate": Gte(Count(Neighbours(ag, "models")),
                              Count(Neighbours(ag, "acts_on"))),
             "description": "The agent models at least as many body-types as it acts on."},
        ]

    def discover_theorems(self) -> list:
        """Promote stable invariants in the agent's own structure to new Theorem
        nodes, mirroring `CuriousAgent.discover_theorems`. Each bootstrap
        candidate predicate is a graph-resident DSL Term-tree the substrate
        evaluates (`inner.evaluate`) — the DSL decides hold/not-hold, never
        Python. The adapter only keeps the consecutive-hold tally (bookkeeping)
        and, when a candidate clears the SEEDED `theorem_hold_threshold` policy,
        reifies it: a `thm_N` Theorem carrying the same predicate Term subgraph
        via a `predicate` edge, asserted by the agent via `asserts`. Same shape
        as the seeded theorems; promotion is the sanctioned counter-bookkeeping +
        reification glue (cf. `discover_relations`). Returns the names promoted
        this pass; never re-promotes (the `_promoted_candidates` dedup set)."""
        from substrate.jsonio import term_to_json
        threshold = int(self.get_scalar_policy("theorem_hold_threshold", 3))
        env = {"agent": self.agent}
        to_promote = []
        for cand in self._bootstrap_theorem_candidates():
            name = cand["name"]
            if name in self._promoted_candidates:
                continue
            try:
                holds = bool(self.inner.evaluate(
                    term_to_json(cand["predicate"]), env))
            except Exception:
                holds = False
            if holds:
                self._theorem_candidate_holds[name] = \
                    self._theorem_candidate_holds.get(name, 0) + 1
            else:
                self._theorem_candidate_holds[name] = 0
            if self._theorem_candidate_holds[name] >= threshold:
                to_promote.append(cand)
        promoted = []
        for cand in to_promote:
            self._promote_theorem_candidate(cand)
            self._promoted_candidates.add(cand["name"])
            promoted.append(cand["name"])
        return promoted

    def _promote_theorem_candidate(self, cand: dict):
        """Mint a `thm_N` Theorem + its predicate Term subgraph + the `asserts`
        edge from the agent — the same graph shape the theorem_core seed installs
        for the seeded theorems. Mechanical graph mutation."""
        from substrate.jsonio import term_to_json
        thm_id = f"thm_{self._theorem_promotions}"
        self._theorem_promotions += 1
        tid = self.s.add_node("Theorem", {
            "name": thm_id, "discovered_from": cand["name"],
            "description": cand["description"],
            "held": True, "last_held": True, "check_count": 0})
        root = self.inner.add_term_subgraph(term_to_json(cand["predicate"]))
        self.inner.add_edge_unchecked(tid, "predicate", root)
        self.inner.add_edge_unchecked(self.agent, "asserts", tid)
        return tid



    def thread_cortex(self, thread):
        """The cortex this thread runs in (its `in_cortex` edge), or None. Pure
        query over the graph."""
        ns = list(self.inner.neighbours(thread, "in_cortex"))
        return ns[0] if ns else None

    def child_threads(self, parent):
        """The sub-threads forked from `parent` (its `child_thread` edges). Pure
        query."""
        return list(self.inner.neighbours(parent, "child_thread"))

    def spawn_python_thread(self, target, args=(), kwargs=None, task: str = "",
                            priority: float = 1.0, cortex=None):
        """Start a genuinely parallel OS-level Python thread running
        `target(*args, **kwargs)` while the agent continues. The Thread node
        tracks state; when the worker returns, `join_thread` stamps `state=done`
        + the result onto the node. The worker delivers its value into an
        adapter-side mailbox (a plain dict keyed by thread id) — it never
        mutates the substrate off the main thread; the mechanical state stamp
        happens on join. Pure I/O orchestration; no decisions."""
        import threading
        nid = self.fork_thread(task or getattr(target, "__name__", "spawn"),
                               priority=priority, cortex=cortex)
        mailbox = getattr(self, "_thread_mailbox", None)
        if mailbox is None:
            mailbox = self._thread_mailbox = {}

        def _run():
            try:
                mailbox[nid] = ("done", target(*args, **(kwargs or {})))
            except Exception as exc:                    # surface the error
                mailbox[nid] = ("error", repr(exc))

        th = threading.Thread(target=_run, daemon=True)
        self._thread_os = getattr(self, "_thread_os", {})
        self._thread_os[nid] = th
        th.start()
        return nid

    def join_thread(self, thread, timeout: float = 5.0):
        """Wait until `thread`'s worker finishes (or timeout), stamp its outcome
        (`state` + `result`/`error`) onto the Thread node on the MAIN thread, and
        return its delivered payload (None on timeout/error). Mechanical."""
        th = getattr(self, "_thread_os", {}).get(thread)
        if th is not None:
            th.join(timeout)
        mailbox = getattr(self, "_thread_mailbox", {})
        outcome = mailbox.get(thread)
        if outcome is None:
            return None
        state, payload = outcome
        if state == "done":
            self.inner.set_attr(thread, "state", "done")
            return payload
        self.inner.set_attr(thread, "state", "error")
        self.inner.set_attr(thread, "error", str(payload))
        return None

    # --- meta-cognitive structure: cortices + their isolated lexicons --------
    # The entity carves out specialised CORTICES (functional modules, each with
    # its own sub-lexicon, isolated from one another) and a DEFAULT lexicon used
    # by the speech faculty. Both are graph-resident nodes the adapter creates,
    # lists, and looks words up in — mechanical bookkeeping over Cortex / Lexicon
    # / Sign nodes (the same shape the old CuriousAgent maintained on mind_graph,
    # here on the substrate). No decisions over graph state.

    def _ensure_lexicon(self):
        """The DEFAULT graph-resident lexicon (the one not owned by any Cortex).
        Created lazily on first use. Cortex-owned lexicons (which carry an
        incoming `lexicon` edge from their Cortex) are skipped."""
        cortex_lexes = {self.cortex_lexicon(c) for c in self.cortexes()}
        for n in self.s.nodes("Lexicon"):
            if n not in cortex_lexes:
                return n
        return self.s.add_node("Lexicon", {})

    def create_cortex(self, name: str, purpose: str = ""):
        """Instantiate a specialised CORTEX with its own (initially empty)
        sub-lexicon, wired by a `lexicon` edge. Mechanical."""
        cx = self.s.add_node("Cortex", {"name": name, "purpose": purpose})
        lex = self.s.add_node("Lexicon", {})
        self.inner.add_edge_unchecked(cx, "lexicon", lex)
        return cx

    def cortexes(self) -> list:
        """Every cortex the entity currently maintains. Pure query."""
        return list(self.s.nodes("Cortex"))

    def cortex_lexicon(self, cortex):
        """The Lexicon owned by `cortex` (its specialised vocabulary), or None."""
        ns = list(self.inner.neighbours(cortex, "lexicon"))
        return ns[0] if ns else None

    # Cortex routing: the candidate with the most matched words wins.
    _CORTEX_CHOICE_TERM = {"type": "Attr",
                           "node": {"type": "Var", "name": "c"}, "key": "score"}

    def route_question(self, question, default=None):
        """Pick the CORTEX whose vocabulary most matches `question` — count the
        question's words known to each cortex's lexicon (by sign-form match),
        return the highest-scoring (else `default`). Autonomous domain routing:
        the agent sends questions where they belong. The adapter counts the
        matches (mechanical, over the grounded signs); the seeded Argmax over the
        stamped candidates picks the winner."""
        import re
        words = set(re.findall(r"[A-Za-z][A-Za-z_]*", question))
        for stale in [n for n in self.s.nodes("CortexCandidate")]:
            self.inner.remove_node(stale)
        by_node = {}
        for cx in self.cortexes():
            lex = self.cortex_lexicon(cx)
            cwords = set()
            if lex is not None:
                for sign in self.inner.neighbours(lex, "entry"):
                    for part in str(self.s.node(sign)["attrs"].get("form", "")).split():
                        cwords.add(part)
            score = len(words & cwords)
            if score > 0:
                cand = self.s.add_node("CortexCandidate", {"score": float(score)})
                by_node[cand] = cx
        if not by_node:
            return default
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "CortexCandidate"},
                  "var_name": "c", "value": self._CORTEX_CHOICE_TERM}
        winner = self.inner.evaluate(choose, {})
        cx = by_node.get(winner, default)
        for cand in list(by_node):
            self.inner.remove_node(cand)
        return cx

    def _lexicon_for(self, cortex):
        """Resolve a cortex spec (None = default, or a cortex id) to its lexicon
        anchor. The lexicon-scoping that isolates vocabularies."""
        return self._ensure_lexicon() if cortex is None else self.cortex_lexicon(cortex)

    def ground_from_spec(self, form: str, spec, args=None, domain: str = "number",
                         cortex=None):
        """Ground a TAUGHT word: mirror the teacher's definition `spec` to a
        persistent Term subgraph (no decision — opaque external definition →
        graph token) and learn a Sign binding `form` to it, scoped to the
        target lexicon (default, or a cortex's sub-lexicon). The `lexicon` →
        `entry` → Sign wiring is what isolates one cortex's vocabulary from
        another's. Mechanical I/O + bookkeeping."""
        from substrate.jsonio import term_to_json
        lex = self._lexicon_for(cortex)
        sign = self.s.add_node("Sign", {"form": form, "concept": form,
                                        "domain": domain})
        troot = self.inner.add_term_subgraph(term_to_json(self._spec_to_term(spec)))
        self.inner.add_edge_unchecked(sign, "denotes", troot)
        self.inner.add_edge_unchecked(lex, "entry", sign)
        return sign

    def _lexicons_for(self, cortex):
        """The lexicon anchor(s) a `cortex` spec scopes to: None -> the default
        lexicon; a single cortex -> its lexicon; a list/tuple/set of cortices ->
        each (so a query can SPAN multiple cortices)."""
        if cortex is None:
            return [self._ensure_lexicon()]
        if isinstance(cortex, (list, tuple, set)):
            return [self.cortex_lexicon(cx) for cx in cortex]
        return [self.cortex_lexicon(cortex)]

    def word_meaning(self, form: str, cortex=None):
        """The grounded meaning a word denotes in the scoped lexicon(s) — the
        NodeID of its denoted Term subgraph (or None if the word isn't learned).
        `cortex` may be a single cortex or a LIST (span them). Pure scoped query;
        the scoping is the isolation the cortex routing relies on."""
        for lex in self._lexicons_for(cortex):
            if lex is None:
                continue
            for sign in self.inner.neighbours(lex, "entry"):
                if self.s.node(sign)["attrs"].get("form") == form:
                    den = list(self.inner.neighbours(sign, "denotes"))
                    return den[0] if den else None
        return None

    def _spec_to_term(self, spec):
        """Ingest a taught definition spec (nested lists in grounded vocabulary)
        into a DSL Term — the mechanical translation of an opaque external
        definition form into a graph-resident Term (mirrors
        CuriousAgent._spec_to_term). `"value"` = the subject's number; numbers
        are literals; a head names a DSL op."""
        from substrate.dsl import (And, Attr, Eq, Gt, Gte, Holds, IfThenElse,
                                    Lit, Lt, Lte, Minus, Mod, Not, Or, Plus,
                                    Times, Var)
        if isinstance(spec, bool) or isinstance(spec, (int, float)):
            return Lit(spec)
        if isinstance(spec, str) and spec != "value":
            return Lit(spec)
        if spec == "value":
            return Attr(Var("x"), "value")
        head, *rest = spec
        binary = {"Eq": Eq, "Mod": Mod, "Minus": Minus,
                  "Gt": Gt, "Lt": Lt, "Gte": Gte, "Lte": Lte}
        variadic = {"Plus": Plus, "Times": Times, "And": And, "Or": Or}
        if head == "IfThenElse":
            return IfThenElse(cond=self._spec_to_term(rest[0]),
                              then=self._spec_to_term(rest[1]),
                              other=self._spec_to_term(rest[2]))
        if head == "Holds":
            # ["Holds", concept_name, arg_spec, [arg2_spec]?] — recursive
            # predicate; rest[0] is the concept NAME (not a sub-spec).
            node2 = self._spec_to_term(rest[2]) if len(rest) > 2 else None
            return Holds(concept=rest[0], node=self._spec_to_term(rest[1]),
                         node2=node2)
        a = [self._spec_to_term(s) for s in rest]
        if head in binary:
            return binary[head](a=a[0], b=a[1])
        if head in variadic:
            return variadic[head](items=tuple(a))
        if head == "Not":
            return Not(arg=a[0])
        raise KeyError(f"unknown definition head '{head}'")

    # --- self-integration: evaluate a grounded predicate word on a subject ---

    def evaluate_word(self, form: str, value, cortex=None):
        """Evaluate a grounded predicate word against a numeric subject: look up
        the Sign in the scoped lexicon, bind a temporary `Num` node carrying
        `value` to `x`, evaluate the denoted Term subgraph via `EvalSubgraph`,
        clean up the temp node, and return the boolean result (or None if the
        word is not grounded). Pure mechanical evaluation — the reasoning is the
        Term the agent owns; the adapter only creates the subject binding."""
        term_root = self.word_meaning(form, cortex=cortex)
        if term_root is None:
            return None
        num_nid = self.s.add_node("Num", {"value": value})
        try:
            eval_term = {"type": "EvalSubgraph",
                         "node": {"type": "Var", "name": "term_root"}}
            env = {"term_root": term_root, "x": num_nid, "agent": self.agent}
            return bool(self.inner.evaluate(eval_term, env))
        finally:
            self.inner.remove_node(num_nid)

    # Dropped/function words — known by convention at the I/O boundary (the parser
    # drops these the same way `domains.language.core_lexicon` marks them "drop").
    # They are never taught as predicate concepts, so they should not appear as
    # "unknown" words when the agent inspects its own lexicon gaps.
    _FUNCTION_WORDS = frozenset([
        "the", "is", "are", "a", "an", "does", "do", "have", "what", "to",
        "of", "and", "in", "by", "under"])

    def discover_unknown_words(self, question: str, cortex=None) -> list:
        """The alphabetic tokens in `question` that are NOT grounded sign forms
        in the scoped lexicon (and not known function words). Seeing what it
        doesn't know is the trigger to ask. Mechanical I/O: extract word tokens,
        compare against the lexicon's `form` attrs — no decisions over graph
        state."""
        import re
        known: set = set(self._FUNCTION_WORDS)
        for lex in self._lexicons_for(cortex):   # may span multiple cortices
            if lex is None:
                continue
            for sign in self.inner.neighbours(lex, "entry"):
                form = self.s.node(sign)["attrs"].get("form", "")
                for part in form.split():
                    known.add(part)
        toks = re.findall(r"[A-Za-z][A-Za-z_]*", question)
        seen, out = set(), []
        for t in toks:
            if t not in known and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def answer_predicate(self, question: str, teacher=None, cortex=None,
                         learning_cortex=None):
        """Parse a simple predicate question `is N word?` at the I/O boundary,
        optionally ground unknown words via `teacher`, and evaluate the predicate.
        The I/O parse extracts the numeric subject and predicate word; the
        reasoning is the grounded Term the agent evaluates. Returns True/False,
        or None if the question doesn't match the expected form or the predicate
        is unknown.

        Teacher signature: form -> spec (a nested-list DSL spec, or None).
        Unknown words that the teacher resolves are grounded into `learning_cortex`
        (or `cortex` by default)."""
        import re
        if learning_cortex is None:
            if isinstance(cortex, (list, tuple, set)):
                learning_cortex = next(iter(cortex), None)
            else:
                learning_cortex = cortex
        if teacher is not None:
            for form in self.discover_unknown_words(question, cortex=cortex):
                if self.word_meaning(form, cortex=cortex) is None:
                    spec = teacher(form)
                    if spec is not None:
                        self.ground_from_spec(form, spec, cortex=learning_cortex)
        # I/O-boundary parse: "is N word?" or "is N.N word?"
        m = re.match(r"is\s+(-?\d+(?:\.\d+)?)\s+([A-Za-z][A-Za-z_0-9]*)\s*\??\s*$",
                     question.strip(), re.IGNORECASE)
        if m is None:
            return None
        try:
            num = int(m.group(1)) if "." not in m.group(1) else float(m.group(1))
        except ValueError:
            return None
        word = m.group(2)
        return self.evaluate_word(word, num, cortex=cortex)

    # --- multi-agent: a Term payload to share + a grow alias ------------------

    def message_payload(self):
        """A Term-tree to share with others in the world — the first bootstrap
        theorem-candidate predicate, or None. The candidates are fixed DSL
        constructors (graph data the agent owns); this just hands one back for a
        world to serialise into a Message. No graph-state decision."""
        cands = self._bootstrap_theorem_candidates()
        return cands[0]["predicate"] if cands else None

    def observe_gamma(self, world_substrate):
        """The Γ_meta core's observation: tally structural triples (reuse
        observe_structure) + per-type attribute-value sets (for where-clauses) +
        bump the observation counter. Pure bookkeeping — no decisions."""
        self.observe_structure(world_substrate)
        wg = world_substrate.graph
        for wn in wg.nodes():
            if wn.type.startswith("Term."):
                continue
            self.register_relation(wn.type, "senses")   # boundary: perceived it
            for k, v in wn.attrs.items():
                if isinstance(v, bool) or not isinstance(v, (int, str)):
                    continue
                self._gamma_attr_values.setdefault((wn.type, k), set()).add(v)
        self.n_observations += 1

    def live_gamma(self, world=None, n_games: int = 5, max_plies: int = 80,
                   grow_every_game: int = 1, narrate=None):
        """The Γ_meta-core autopoietic loop: reset -> observe -> step the world
        -> observe -> grow Γ, for n_games. No goal, no reward — the agent only
        observes + grows its grammar. Domain-agnostic (the world is four
        callables). Plays any legal move (acceptance is what it LEARNS, not
        whether it plays well); the moved/captured body-types are registered as
        `acts_on`. Defaults to the chess body. (Named live_gamma to avoid the
        existing autopoietic `live` from an earlier burn.)

        `narrate(self, sub)` — optional perception hook called after every observe,
        to read out what the agent sees via its own concepts. The loop stays
        domain-agnostic; any narration lives in the world adapter."""
        self.boot_gamma_meta()
        if world is None:
            from domains.worlds import chess_world
            world = chess_world()
        for _ in range(n_games):
            sub, ctx = world["reset"]()
            self.observe_gamma(sub)
            if narrate:
                narrate(self, sub)
            for _ in range(max_plies):
                actions = world["legal_actions"](sub, ctx)
                if not actions:
                    break
                action = actions[0]      # observe-and-grow; not playing to win
                for t in world["interpret_acts_on"](sub, ctx, action):
                    self.register_relation(t, "acts_on")
                sub, ctx = world["apply_action"](sub, ctx, action)
                self.observe_gamma(sub)
                if narrate:
                    narrate(self, sub)
            self._gamma_n_games = getattr(self, "_gamma_n_games", 0) + 1
            if self._gamma_n_games % grow_every_game == 0:
                self.grow_gamma()

    def grow_gamma(self, triple_threshold: int = 30, attr_max_distinct: int = 8):
        """Grow the grammar from accumulated observation. When the Γ_meta core is
        active (gamma_root set), this is the two-phase substrate growth: (1)
        triples seen >= threshold become unconstrained Productions
        (_append_production, meta-gated); (2) per-source-type attribute
        constraints WIDEN — the where-clause is recomputed from the UNION of all
        observed values and superseded in. Without the core booted, it falls
        back to relation discovery (the cross_world/multi_agent path)."""
        if self.gamma_root is None:
            return self.discover_relations()
        from substrate import In, Attr, Var, Lit, SetT, Production, NodePattern
        existing = {(p.src.type, p.edge_type, p.tgt.type)
                    for p in self.gamma_dynamic.productions}
        # Phase 1: unconstrained triples over threshold.
        for (src_t, edge_t, tgt_t), count in list(self._triple_count.items()):
            if (src_t, edge_t, tgt_t) in existing or count < triple_threshold:
                continue
            self._append_production(Production(
                src=NodePattern(src_t, "s"), edge_type=edge_t,
                tgt=NodePattern(tgt_t, "t"), where=None,
                provenance=f"discovered:{src_t}-{edge_t}->{tgt_t}"))
            existing.add((src_t, edge_t, tgt_t))
            self.register_relation(src_t, "models")
            self.register_relation(tgt_t, "models")
        # Phase 2: per-source-type attribute WIDENING — recompute the where-set
        # from the UNION of observed values; supersede when it changed. Iterate
        # the Production NODES directly (so the supersede targets the right one,
        # not a positional index that can drift from the view's order).
        import json
        for pid in list(self.inner.neighbours(self.gamma_root, "production")):
            src = next(iter(self.inner.neighbours(pid, "pattern.src")), None)
            tgt = next(iter(self.inner.neighbours(pid, "pattern.tgt")), None)
            if src is None or tgt is None:
                continue
            pa = self.s.node(pid)["attrs"]
            src_type = self.s.node(src)["attrs"].get("type")
            best = None
            for (n_t, attr_k), vals in self._gamma_attr_values.items():
                if n_t != src_type or not (0 < len(vals) <= attr_max_distinct):
                    continue
                if best is None or len(vals) < len(best[1]):
                    try:
                        best = (attr_k, sorted(vals))
                    except TypeError:
                        best = (attr_k, sorted(vals, key=str))
            if best is None:
                continue
            attr_k, sorted_vals = best
            # Old value-set from the stored where_json (robust to Term identity).
            old_vals = None
            raw = pa.get("where_json")
            if raw:
                try:
                    old_vals = [it["value"] for it in
                                json.loads(raw)["container"]["items"]]
                except Exception:
                    old_vals = None
            if old_vals == sorted_vals:
                continue
            ta = self.s.node(tgt)["attrs"]
            new_where = In(member=Attr(node=Var("s"), key=attr_k),
                           container=SetT(items=tuple(Lit(v) for v in sorted_vals)))
            self._append_production(Production(
                src=NodePattern(src_type, "s"), edge_type=pa.get("edge_type"),
                tgt=NodePattern(ta.get("type"), "t"), where=new_where,
                provenance=str(pa.get("provenance", "")).split("|where")[0]
                + f"|where {attr_k}∈{sorted_vals}"))
            self.inner.remove_edge(self.gamma_root, "production", pid)  # orphan old
        return []

    # --- substrate awareness: tick cost / memory / compute / long-term store --

    def agent_attr(self, key):
        """Read a scalar attr off the agent node (the graph-resident store the
        awareness bookkeeping writes to — what the agent's DSL sees via Attr)."""
        return self.s.node(self.agent)["attrs"].get(key)

    def measure_tick(self, work):
        """Run ``work(self)``, time it, record cost on the agent node, return
        the work's signal. Pure mechanical bookkeeping."""
        import time
        t0 = time.perf_counter()
        signal = work(self)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        a = self.s.node(self.agent)["attrs"]
        self.inner.set_attr(self.agent, "last_tick_cost_ms", elapsed_ms)
        self.inner.set_attr(self.agent, "tick_count", int(a.get("tick_count", 0)) + 1)
        self.inner.set_attr(self.agent, "total_tick_cost_ms",
                            float(a.get("total_tick_cost_ms", 0.0)) + elapsed_ms)
        return signal

    def refresh_memory_stats(self):
        """Read the process's resident memory; record it on the agent node."""
        import resource
        import sys
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mult = 1 if sys.platform == "darwin" else 1024
        bytes_used = int(rss * mult)
        self.inner.set_attr(self.agent, "memory_bytes", bytes_used)
        return bytes_used

    def set_memory_limit(self, bytes_) -> None:
        self.inner.set_attr(self.agent, "memory_limit_bytes", int(bytes_))

    def memory_pressure(self):
        a = self.s.node(self.agent)["attrs"]
        used, limit = a.get("memory_bytes"), a.get("memory_limit_bytes")
        if used is None or limit is None or limit == 0:
            return None
        return used / limit

    def set_compute_limit(self, ms) -> None:
        self.inner.set_attr(self.agent, "compute_limit_ms", float(ms))

    def compute_pressure(self):
        a = self.s.node(self.agent)["attrs"]
        spent, limit = a.get("total_tick_cost_ms"), a.get("compute_limit_ms")
        if spent is None or limit is None or limit == 0:
            return None
        return spent / limit

    def open_long_term_storage(self, path: str, size=None):
        """A persistent backing store, mmap'd from a file (created at `size` if
        absent). Records storage_path/storage_bytes scalars; the mmap handle is
        held adapter-side (non-serialisable I/O)."""
        import mmap
        import os
        if not os.path.exists(path):
            if size is None:
                raise FileNotFoundError(path)
            with open(path, "wb") as f:
                f.write(b"\0" * int(size))
        fd = os.open(path, os.O_RDWR)
        try:
            st_size = os.fstat(fd).st_size
            mm = mmap.mmap(fd, st_size, access=mmap.ACCESS_WRITE)
        finally:
            os.close(fd)
        self._storage_mmap = mm
        self.inner.set_attr(self.agent, "storage_path", path)
        self.inner.set_attr(self.agent, "storage_bytes", int(st_size))
        return mm

    def storage_write(self, offset: int, data: bytes) -> int:
        self._storage_mmap[offset:offset + len(data)] = data
        return len(data)

    def storage_read(self, offset: int, length: int) -> bytes:
        return bytes(self._storage_mmap[offset:offset + length])

    # --- ingest: mirror a world substrate into WorldInstance nodes -----------

    def ingest(self, world_substrate) -> None:
        wg = world_substrate.graph
        node_map: dict = {}            # world NodeID -> agent WorldInstance NodeID
        seen_now: set = set()          # instances touched this ingest
        fresh: set = set()             # instances that gained NEW info this ingest
        attr_seen: dict = {}           # (world_type, attr) -> set of values seen this ingest
        # 1) every world node carrying an `id` becomes/updates a WorldInstance.
        for wn in wg.nodes():
            self._sensed_types.add(wn.type)   # senses its type (incl Term.* shared payloads)
            if wn.type.startswith("Term."):   # Term.* are graph machinery, never instanced (no id)
                continue
            wid = wn.attrs.get("id")
            if wid is None:
                continue
            key = (wn.type, str(wid))
            attrs = {"world_type": wn.type, "world_id": str(wid)}
            for k, v in wn.attrs.items():
                if k != "id" and isinstance(v, _SCALAR):
                    attrs[k] = v
                    self._seen.add((wn.type, k, v))
                    attr_seen.setdefault((wn.type, k), set()).add(v)
            inst = self._instances.get(key)
            # A cached instance whose node was freed elsewhere (e.g. removed across a world
            # RESET / re-perception) leaves a STALE entry — set_attr on it panics ("node id
            # refers to a freed slot"). Drop the stale entry and recreate. Mechanical perception
            # hygiene (the same has_node check the ghost-cleanup below uses, applied at the get site).
            if inst is not None and not self.s.has_node(inst):
                del self._instances[key]
                inst = None
            if inst is None:
                inst = self.s.add_node("WorldInstance", {**attrs, "n_observations": 0})
                self._instances[key] = inst
                # perceiving an instance = knowing it exists (the agent's
                # `knows` set, which grounded definitions quantify over).
                self.inner.add_edge_unchecked(self.agent, "knows", inst)
                # OO: each instance --instance_of--> its shared BodyType, so
                # type-level attrs apply to every instance by traversal.
                bt = self._body_types.get(wn.type)
                if bt is None:
                    bt = self.s.add_node("BodyType", {"name": wn.type})
                    self._body_types[wn.type] = bt
                self.inner.add_edge_unchecked(inst, "instance_of", bt)
                fresh.add(inst)        # a never-seen instance is new info
            else:
                for k, v in attrs.items():   # attr changes update but don't freshen
                    self.inner.set_attr(inst, k, v)
            node_map[wn.id] = inst
            seen_now.add(inst)
        # 1b) A cell's identity is its POSITION; its value is mutable. When a cell
        #     changes value its world-node TYPE changes (CellC12 -> CellC3), so the
        #     (type, id) key above mints a FRESH instance and leaves the old-typed
        #     instance lingering at that position — a ghost that corrupts counts and
        #     centroids (a body that moves leaves stale cells at every old position).
        #     Drop any instance whose position was just re-perceived as a different
        #     instance. Mechanical perception hygiene: one cell per position.
        pos_now: dict = {}
        for inst in seen_now:
            a = self.s.node(inst)["attrs"]
            if "row" in a and "col" in a:
                pos_now[a.get("world_id")] = inst
        # A ghost can only sit at a position RE-PERCEIVED this frame (pos_now). The cache
        # key is (type, world_id), so we read world_id straight off the key — no node()
        # deref — and skip the vast majority of instances (unchanged cells) cheaply. This
        # turns the old O(all-instances) node() scan (~8ms/frame on 64x64) into O(changed).
        for k in list(self._instances.keys()):
            wid = k[1] if isinstance(k, tuple) and len(k) == 2 else None
            if wid not in pos_now:
                continue
            inst = self._instances[k]
            if inst in seen_now:
                continue
            if not self.s.has_node(inst):
                del self._instances[k]
                continue
            if pos_now[wid] != inst:
                self.inner.remove_node(inst)
                del self._instances[k]
        # 2) mirror world edges whose BOTH ends are instances (deduped). A NEW
        #    instance-instance edge is new structural info → freshens its source.
        for wn in wg.nodes():
            src_inst = node_map.get(wn.id)
            if src_inst is None:
                continue
            for e in wg.out_edges(wn.id):
                tgt_inst = node_map.get(e.key.tgt)
                if (tgt_inst is not None and tgt_inst != src_inst   # skip self-loops
                        and not self.inner.has_edge(
                            src_inst, e.key.edge_type, tgt_inst)):
                    self.inner.add_edge_unchecked(src_inst, e.key.edge_type, tgt_inst)
                    fresh.add(src_inst)    # new structural info for BOTH endpoints
                    fresh.add(tgt_inst)
        # 3) per-instance bookkeeping: n_observations always climbs; saturation_count
        #    resets to 0 when the instance gained new info this tick, else climbs
        #    (attr churn does not count as new info). The seeded saturation_predicate
        #    reads saturation_count; the curiosity drive reads freshening.
        for inst in seen_now:
            a = self.s.node(inst)["attrs"]
            self.inner.set_attr(inst, "n_observations", int(a.get("n_observations", 0)) + 1)
            if inst in fresh:
                self.inner.set_attr(inst, "saturation_count", 0)
            else:
                self.inner.set_attr(inst, "saturation_count",
                                    int(a.get("saturation_count", 0)) + 1)
        # 4) per-(type, attr) Attribute bookkeeping — the per-attribute analogue:
        #    observed_count climbs each ingest the (type,attr) is seen; distinct_count
        #    = #distinct values ever; saturation_count resets to 0 when a NEW value
        #    appears, else climbs. The same seeded saturation_predicate reads it.
        for (typ, k), vals in attr_seen.items():
            akey = (typ, k)
            known = self._attr_values.setdefault(akey, set())
            new_vals = vals - known
            known |= vals
            att = self._attributes.get(akey)
            if att is None:
                att = self.s.add_node("Attribute", {
                    "type_name": typ, "attr_name": k,
                    "observed_count": 0, "saturation_count": 0, "distinct_count": 0})
                self._attributes[akey] = att
            aa = self.s.node(att)["attrs"]
            self.inner.set_attr(att, "observed_count", int(aa.get("observed_count", 0)) + 1)
            self.inner.set_attr(att, "distinct_count", len(known))
            if new_vals:
                self.inner.set_attr(att, "saturation_count", 0)
            else:
                self.inner.set_attr(att, "saturation_count",
                                    int(aa.get("saturation_count", 0)) + 1)
        self.last_freshening_count = len(fresh)
        self.tick()

    def tick(self, max_steps: int = 100_000) -> int:
        return int(self.inner.run_cycle("default", max_steps)["steps"])

    def dual_process_tick(self, max_steps: int = 100_000, *,
                          trace: bool = False) -> dict:
        """Run the engine's System-1-first cycle.

        The adapter neither selects a response nor decides to deliberate. It
        only invokes the native schedule: authored hard-real-time rules settle,
        and the remaining rule population runs iff those rules minted a
        ``SystemTwoEscalation`` request in the graph.
        """
        return dict(self.inner.run_cycle(
            "dual_process", max_steps, trace=bool(trace)))

    def cognitive_tick(self, max_steps: int = 100_000) -> int:
        """ONE WHOLE COGNITIVE CYCLE — the tick a reflex+rule faculty (e.g. the
        reading cortices) rides on. Advance the clock (surfaced as the agent
        `tick` attr the reflex stimulus Terms read), settle the rule fixpoint
        (`run_rules`), then fire the agent's reflexes (`fire_reflexes`) — the
        cortices. This is the `agent_understands_autonomously` / question_driver
        pump precedent collapsed into ONE agent-side method, so a driver rides
        the AGENT's cognitive cycle instead of hand-pumping `run_rules` +
        `fire_reflexes` itself. Returns the rule-fixpoint step count."""
        m = self._master
        m["tick"] += 1
        self.inner.set_attr(self.agent, "tick", int(m["tick"]))
        report = self.inner.run_cycle("cognitive_legacy", max_steps)
        self.fire_reflexes()
        return int(report["steps"])

    # --- query: read instances back out --------------------------------------

    def instances(self, world_type: str) -> dict:
        """(world_id -> WorldInstance NodeID) for a world type."""
        return {wid: nid for (t, wid), nid in self._instances.items() if t == world_type}

    def instance_attr(self, nid, key):
        return self.s.node(nid)["attrs"].get(key)

    def instance_neighbours(self, nid, edge_type):
        return self.inner.neighbours(nid, edge_type)

    def is_instance_saturated(self, nid) -> bool:
        """Is this instance saturated? — `EvalSubgraph` of the seeded
        `saturation_predicate` with the instance bound to `attr` (same policy,
        both scopes). The agent's epistemic discipline, run on graph data."""
        term = {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
            "type": "Neighbours", "node": {"type": "Var", "name": "a"},
            "edge_type": "saturation_predicate"}}}
        return bool(self.inner.evaluate(term, {"a": self.agent, "attr": nid}))

    # --- action frontier EMA (how much new info an action tends to reveal) ---

    def record_action_outcome(self, action: str, novelty_delta: float = 0.0,
                              failure_delta: float = 0.0, boredom_delta: float = 0.0,
                              frontier_after: float = 0.0, alpha: float = 0.1) -> None:
        """Persist an action's outcome: running sums on a per-action ActionStat
        node (n / novelty_sum / failure_sum / boredom_sum) + EMAs of each signal
        (frontier / failure / boredom). The agent's predictive-curiosity +
        boredom drives read these — mechanical outcome bookkeeping."""
        stat = self._action_stat_nodes.get(action)
        if stat is None:
            stat = self.s.add_node("ActionStat", {
                "action": action, "n": 0, "novelty_sum": 0,
                "failure_sum": 0.0, "boredom_sum": 0})
            self._action_stat_nodes[action] = stat
        a = self.s.node(stat)["attrs"]
        self.inner.set_attr(stat, "n", int(a.get("n", 0)) + 1)
        self.inner.set_attr(stat, "novelty_sum", a.get("novelty_sum", 0) + novelty_delta)
        self.inner.set_attr(stat, "failure_sum", a.get("failure_sum", 0) + failure_delta)
        self.inner.set_attr(stat, "boredom_sum", a.get("boredom_sum", 0) + boredom_delta)
        for ema, val in ((self._action_frontier_ema, frontier_after),
                         (self._action_failure_ema, failure_delta),
                         (self._action_boredom_ema, boredom_delta)):
            ema[action] = (1 - alpha) * ema.get(action, float(val)) + alpha * float(val)

    def action_frontier_estimate(self, action: str) -> float:
        return self._action_frontier_ema.get(action, 0.0)

    def action_failure_estimate(self, action: str) -> float:
        return self._action_failure_ema.get(action, 0.0)

    def action_boredom_estimate(self, action: str) -> float:
        return self._action_boredom_ema.get(action, 0.0)

    def action_stat(self, action: str) -> dict:
        stat = self._action_stat_nodes.get(action)
        return dict(self.s.node(stat)["attrs"]) if stat is not None else {}

    # --- per-(type, action) exploration: "what can I do with this?" ----------

    def _ensure_action_type_stat(self, type_name: str, action_kind: str):
        """ActionTypeStat node for (type, action), lazily created + attached to
        the agent via tracks_action_type; tracks attempts + freshening_ema."""
        key = (type_name, action_kind)
        existing = self._action_type_stat_nodes.get(key)
        if existing is not None:
            return existing
        nid = self.s.add_node("ActionTypeStat", {
            "type_name": type_name, "action_kind": action_kind,
            "attempts": 0, "freshening_ema": 0.0})
        self.inner.add_edge_unchecked(self.agent, "tracks_action_type", nid)
        self._action_type_stat_nodes[key] = nid
        return nid

    def _record_action_type_attempt(self, type_name: str, action_kind: str) -> None:
        nid = self._ensure_action_type_stat(type_name, action_kind)
        a = self.s.node(nid)["attrs"]
        self.inner.set_attr(nid, "attempts", int(a.get("attempts", 0)) + 1)

    def _record_action_type_outcome(self, type_name: str, action_kind: str,
                                    freshening: float, alpha: float = 0.01) -> None:
        nid = self._ensure_action_type_stat(type_name, action_kind)
        old = float(self.s.node(nid)["attrs"].get("freshening_ema", 0.0))
        self.inner.set_attr(nid, "freshening_ema",
                            alpha * float(freshening) + (1.0 - alpha) * old)

    def _action_type_attempts(self, type_name: str, action_kind: str) -> int:
        nid = self._action_type_stat_nodes.get((type_name, action_kind))
        return int(self.s.node(nid)["attrs"].get("attempts", 0)) if nid else 0

    def _action_type_freshening_ema(self, type_name: str, action_kind: str) -> float:
        nid = self._action_type_stat_nodes.get((type_name, action_kind))
        return float(self.s.node(nid)["attrs"].get("freshening_ema", 0.0)) if nid else 0.0

    def choose_action_exploring(self, legal_actions, preview_fn):
        """Pick via the seeded curiosity score, then record an attempt for every
        sensed type × the chosen action's kind (the old agent's coupling)."""
        chosen = self.choose_action(legal_actions, preview_fn)
        if chosen is None:
            return None
        kind = chosen if isinstance(chosen, str) else chosen[0]
        for t in self.senses():
            self._record_action_type_attempt(t, kind)
        return chosen

    # --- anticipation: order-2-time of frustration flags incipient insight ---

    def _anticipation_window(self, name: str):
        win = self._anticipation_windows.get(name)
        if win is None:
            win = self.s.add_node("AnticipationWindow", {"name": name})
            self._anticipation_windows[name] = win
        return win

    def set_frustration_window(self, name: str, previous_previous: float,
                               previous: float) -> None:
        win = self._anticipation_window(name)
        self.inner.set_attr(win, "previous_previous_frustration", float(previous_previous))
        self.inner.set_attr(win, "previous_frustration", float(previous))

    def _has_frustration_window(self, win) -> bool:
        a = self.s.node(win)["attrs"]
        return "previous_frustration" in a and "previous_previous_frustration" in a

    def order_time_of_f(self, name: str, order: int, current_frustration: float):
        """Order-N finite difference of frustration via the substrate's native
        evaluator (the shared windowed-filter kernel). None if window not ready."""
        from domains.windowed_filter import attr_sample, order_n_kernel, var_sample
        win = self._anticipation_window(name)
        if not self._has_frustration_window(win):
            return None
        if order == 1:
            samples = [attr_sample("mt", "previous_frustration"), var_sample("current_F")]
        else:
            samples = [attr_sample("mt", "previous_previous_frustration"),
                       attr_sample("mt", "previous_frustration"), var_sample("current_F")]
        term = order_n_kernel(samples, order)
        if term is None:
            return None
        return float(self.inner.evaluate(
            term.to_dict(), {"mt": win, "current_F": float(current_frustration)}))

    def _anticipation_signature_term(self, min_frustration, drop_threshold, curvature_threshold):
        """Anticipation DECISION as a DSL Term over a candidate's attrs — the
        substrate decides; the adapter only stamps the candidate."""
        from substrate.dsl import And, Attr, Eq, Gte, Lit, Lt, Var
        c = Var("c")
        return And(items=(
            Gte(Attr(c, "current_frustration"), Lit(float(min_frustration))),
            Lt(Attr(c, "order_1_time"), Lit(float(drop_threshold))),
            Lt(Attr(c, "order_2_time"), Lit(float(curvature_threshold))),
            Eq(Attr(c, "insight_detected"), Lit(0)),
        ))

    def detect_anticipation(self, name: str, current_frustration: float,
                            insight_detected: bool, min_frustration: float = 0.5,
                            drop_threshold: float = -0.05, curvature_threshold: float = -0.02):
        from substrate.jsonio import term_to_json
        win = self._anticipation_window(name)
        if not self._has_frustration_window(win):
            return None
        o1 = self.order_time_of_f(name, 1, current_frustration)
        o2 = self.order_time_of_f(name, 2, current_frustration)
        if o1 is None or o2 is None:
            return None
        cand = self.s.add_node("AnticipationCandidate", {
            "current_frustration": float(current_frustration),
            "order_1_time": float(o1), "order_2_time": float(o2),
            "insight_detected": 1 if insight_detected else 0})
        sig = self._anticipation_signature_term(min_frustration, drop_threshold, curvature_threshold)
        fires = bool(self.inner.evaluate(term_to_json(sig), {"c": cand}))
        self.inner.remove_node(cand)
        if not fires:
            return None
        a = self.s.node(win)["attrs"]
        return {"current_frustration": float(current_frustration),
                "previous_frustration": float(a["previous_frustration"]),
                "previous_previous_frustration": float(a["previous_previous_frustration"]),
                "order_1_time": float(o1), "order_2_time": float(o2)}

    def record_anticipation(self, name: str, event: dict):
        win = self._anticipation_window(name)
        node = self.s.add_node("AnticipationEvent", {
            "current_frustration": float(event["current_frustration"]),
            "previous_frustration": float(event["previous_frustration"]),
            "previous_previous_frustration": float(event["previous_previous_frustration"]),
            "order_1_time": float(event["order_1_time"]),
            "order_2_time": float(event["order_2_time"])})
        self.inner.add_edge_unchecked(win, "has_anticipation", node)
        return node

    def roll_frustration(self, name: str, current_frustration: float) -> None:
        win = self._anticipation_window(name)
        prev = float(self.s.node(win)["attrs"].get("previous_frustration", current_frustration))
        self.inner.set_attr(win, "previous_previous_frustration", prev)
        self.inner.set_attr(win, "previous_frustration", float(current_frustration))

    def anticipations(self, name: str) -> list:
        win = self._anticipation_windows.get(name)
        if win is None:
            return []
        out = []
        for node in self.inner.neighbours(win, "has_anticipation"):
            a = self.s.node(node)["attrs"]
            out.append({"current_frustration": float(a.get("current_frustration", 0.0)),
                        "order_1_time": float(a.get("order_1_time", 0.0)),
                        "order_2_time": float(a.get("order_2_time", 0.0))})
        return out

    # --- map planning: locus tracking + BFS over the mirrored instance map ----

    def note_action(self, action_kind, orientation: tuple = ()) -> None:
        """Record the action (+orientation) just taken, so the next observed
        locus-change is attributed to it. Mechanical bookkeeping."""
        self.last_action_kind = action_kind
        self.last_orientation = tuple(orientation)

    def observe_locus(self, world_substrate) -> None:
        """Ingest a world AND track the agent's locus from `at_location` edges,
        counting (last_locus, orientation, action) -> next_locus transitions and
        recording the instance->instance edge types (the BFS map). Pure I/O +
        counting — no decisions."""
        wg = world_substrate.graph
        id_nodes = {wn.id for wn in wg.nodes()
                    if not wn.type.startswith("Term.") and wn.attrs.get("id") is not None}
        for wn in wg.nodes():
            if wn.id not in id_nodes:
                continue
            for e in wg.out_edges(wn.id):
                if e.key.tgt in id_nodes and e.key.tgt != wn.id:
                    self._mirrored_edge_types.add(e.key.edge_type)
        new_locus_key = None
        for wn in wg.nodes():
            done = False
            for e in wg.out_edges(wn.id, "at_location"):
                tgt = wg.node(e.key.tgt)
                tgt_wid = tgt.attrs.get("id")
                if tgt_wid is None or tgt.type.startswith("Term."):
                    continue
                new_locus_key = (tgt.type, str(tgt_wid))
                done = True
                break
            if done:
                break
        self.ingest(world_substrate)
        new_locus = self._instances.get(new_locus_key) if new_locus_key else None
        if new_locus is not None:
            if self.last_locus_wi is not None and self.last_action_kind is not None:
                state_key = (self.last_locus_wi, self.last_orientation, self.last_action_kind)
                inner = self._locus_transition_counts.setdefault(state_key, {})
                inner[new_locus] = inner.get(new_locus, 0) + 1
            # Intent-failure freshening: an intended next-locus that the action
            # did NOT achieve makes the failure-locus interesting again (reset
            # its saturation_count). Mechanical bookkeeping; the "ask why?"
            # curiosity spike is the seeded per-instance saturation predicate.
            if (self.current_intent_wi is not None
                    and self.current_intent_wi != new_locus
                    and self.last_locus_wi is not None):
                self.inner.set_attr(self.last_locus_wi, "saturation_count", 0)
            self.current_intent_wi = None
            self.current_locus_wi = new_locus
            self.last_locus_wi = new_locus

    def modal_next_locus(self, locus_wi, orientation: tuple, action_kind):
        inner = self._locus_transition_counts.get((locus_wi, tuple(orientation), action_kind))
        if not inner:
            return None
        best_next, best_count = None, 0
        for nxt, count in inner.items():
            if count > best_count:
                best_count, best_next = count, nxt
        return best_next

    def plan_next_step(self, locus_wi, horizon: int):
        """BFS over the mirrored instance edges from `locus_wi` to the nearest
        under-saturated instance; return the first hop, or None. Saturation is
        the SEEDED predicate (is_instance_saturated); this only traverses."""
        edge_types = self._mirrored_edge_types
        if not edge_types:
            return None
        from collections import deque
        seen = {locus_wi}
        queue = deque()
        for et in edge_types:
            for nbr in self.inner.neighbours(locus_wi, et):
                if nbr in seen:
                    continue
                if not self.is_instance_saturated(nbr):
                    return nbr
                seen.add(nbr)
                queue.append((nbr, nbr, 1))
        while queue:
            cur, first_hop, depth = queue.popleft()
            if depth >= horizon:
                continue
            for et in edge_types:
                for nbr in self.inner.neighbours(cur, et):
                    if nbr in seen:
                        continue
                    seen.add(nbr)
                    if not self.is_instance_saturated(nbr):
                        return first_hop
                    queue.append((nbr, first_hop, depth + 1))
        return None

    def saturate_instance(self, nid, count: int = 1000) -> None:
        self.inner.set_attr(nid, "saturation_count", int(count))

    # --- boundary relations: senses / models / acts_on (meta-curiosity) -------

    _BOUNDARY_RELATIONS = ("senses", "models", "acts_on")

    def register_relation(self, type_name: str, relation: str) -> None:
        """Stamp a boundary edge agent --relation--> BodyType. Mechanical I/O:
        the world reports touched/modeled types; the adapter records the edge.
        The asymmetry these expose is read by the seeded action_score_term."""
        if relation not in self._BOUNDARY_RELATIONS:
            raise ValueError(f"unknown boundary relation: {relation}")
        bt = self._ensure_body_type(type_name)
        for tgt in self.inner.neighbours(self.agent, relation):
            if tgt == bt:
                return
        self.inner.add_edge_unchecked(self.agent, relation, bt)

    def _relation_set(self, relation: str) -> set:
        return {self.s.node(bt)["attrs"]["name"]
                for bt in self.inner.neighbours(self.agent, relation)}

    def models_set(self) -> set:
        return self._relation_set("models")

    def acts_on_set(self) -> set:
        return self._relation_set("acts_on")

    def boundary_asymmetry(self) -> set:
        """(senses − acts_on) ∪ (senses − models) — the self-completion frontier."""
        sensed = self.senses()
        return (sensed - self.acts_on_set()) | (sensed - self.models_set())

    def asymmetry_count(self, touched_types) -> int:
        """How many touched types lie on the boundary-asymmetry frontier — the
        asym_count the seeded action_score_term weights by meta_curiosity_weight."""
        return len(set(touched_types) & self.boundary_asymmetry())

    def _authorize_world_action(self, world, substrate, ctx, action) -> dict:
        """Mechanical enactment boundary for the graph's commitment verdict."""
        from domains.information_commitment import assess
        footprint_fn = world.get("effect_footprint")
        if footprint_fn is not None:
            footprint = dict(footprint_fn(substrate, ctx, action) or {})
        else:
            footprint = {
                "deleted_facts": 0.0,
                "overwritten_facts": 0.0,
                "recoverability": 1.0 if world.get("preview_safe", True) else 0.5,
                "externality": 0.0,
            }
        return assess(
            self,
            commit={
                "name": str(action),
                "expected_goal_work": float(footprint.pop("expected_goal_work", 1.0)),
                "expected_information_gain": float(
                    footprint.pop("expected_information_gain", 0.0)),
                "uncertainty": float(footprint.pop("uncertainty", 0.0)),
                "requires_approval": float(footprint.pop("requires_approval", 0.0)),
                "footprint": footprint,
            },
            wait={"delay_cost": 0.1},
            refine={"refinement_cost": 1.0},
            retain_trace=False,
        )

    def choose_action_meta_curious(self, legal_actions, preview_fn, touches_fn,
                                   target_fn=None):
        """choose_action WITH meta-curiosity: stamp each candidate's asym_count
        from touches_fn(action) ∩ the frontier, then Argmax the seeded
        action_score_term. Adapter measures + stamps; the seed decides.

        ``target_fn(action)`` (optional) returns the specific world INSTANCE the
        action acts on, or None. Type-level touches can't tell a targeted act on a
        SEEN distinct thing from a no-op (every action 'touches CellC1'); the
        instance-level ``seen_as`` link (vision bound to the world) can — acting on
        a thing the agent has SEEN is meta-curious, so it lifts asym_count. This
        closes see→link→ACT: the decision reads what vision linked."""
        if not legal_actions:
            return None
        for c in list(self.s.nodes()):
            if self.s.node(c)["type"] == "ActionCandidate":
                self.inner.remove_node(c)
        asym = self.boundary_asymmetry()
        by_node = {}
        for i, action in enumerate(legal_actions):
            try:
                nov = self._preview_novelty(preview_fn(action))
            except Exception:
                nov = 0
            try:
                asym_count = len(set(touches_fn(action)) & asym)
            except Exception:
                asym_count = 0
            if target_fn is not None:
                try:
                    tgt = target_fn(action)
                    if tgt is not None and self.inner.neighbours(tgt, "seen_as"):
                        asym_count += 1     # acts on a thing I have SEEN
                except Exception:
                    pass
            c = self.s.add_node("ActionCandidate", {"q": 0.0, "asym_count": asym_count,
                                                    "novelty": nov, "idx": i})
            by_node[c] = action
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "ActionCandidate"},
                  "var_name": "c",
                  "value": {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
                      "type": "Neighbours", "node": {"type": "Var", "name": "a"},
                      "edge_type": "action_score_term"}}}}
        picked = self.inner.evaluate(choose, {"a": self.agent})
        return by_node.get(picked, legal_actions[0])

    # --- tau-3: theorem checking (the SEEDED predicate Terms, evaluated) -------

    _THEOREM_PREDICATE_TERM = {"type": "EvalSubgraph", "node": {"type": "Pick",
        "source": {"type": "Neighbours", "node": {"type": "Var", "name": "t"},
                   "edge_type": "predicate"}}}

    def _theorem_nodes(self) -> list:
        return [n for n in self.s.nodes() if self.s.node(n)["type"] == "Theorem"]

    def register_senses(self, types) -> None:
        for t in types:
            self.register_relation(t, "senses")

    def register_models_from_grown(self) -> None:
        for pat in self.patterns():
            for key in ("from_type", "to_type"):
                t = pat.get(key)
                if t and t != "Agent":
                    self.register_relation(t, "models")

    def quality_of_gamma(self) -> float:
        q = 0.0
        for rid, meta in self._discovered_relations.items():
            if rid in self._meta_productions:
                q += float(meta.get("count", 0))
        # Γ_meta core: experiential support of the discovered triples — each
        # production weighted by how many observations support it (monotone:
        # triple_counts only grow, and a triple once in Γ keeps accumulating).
        if self.gamma_root is not None:
            for p in self.gamma_dynamic.productions:
                q += float(self._triple_count.get(
                    (p.src.type, p.edge_type, p.tgt.type), 0))
        return q

    # --- Γ_meta core (slice A): the self-growing grammar as graph data, gated
    # by a meta-grammar on the agent's OWN Rust substrate (self.s). Γ_dynamic is
    # a VIEW over Production nodes hanging off a Grammar root; every Γ-edit goes
    # through the CHECKED add_edge, so the meta-grammar refuses ill-formed edits.

    _GAMMA_META_PRODUCTIONS = (
        ("Grammar", "production", "Production"),
        ("Production", "pattern.src", "NodePattern"),
        ("Production", "pattern.tgt", "NodePattern"),
        ("Agent", "senses", "BodyType"),
        ("Agent", "models", "BodyType"),
        ("Agent", "acts_on", "BodyType"),
    )

    def boot_gamma_meta(self):
        """Install the Γ-evolution meta-grammar onto self.s + mint the Grammar
        root Γ_dynamic hangs off. Idempotent. The meta-grammar admits exactly the
        typed edges of Γ-growth (Grammar-production->Production, Production-
        pattern.src/tgt->NodePattern, Agent-{senses,models,acts_on}->BodyType) —
        so the agent's act of growing its own grammar is a transaction gated by
        the same admissibility machinery as the world it observes."""
        if self._gamma_meta_done:
            return self.gamma_root
        for s, e, t in self._GAMMA_META_PRODUCTIONS:
            try:
                self.inner.add_production({
                    "src": {"type": s, "var": "a"}, "edge_type": e,
                    "tgt": {"type": t, "var": "b"},
                    "provenance": f"meta:{s}-{e}-{t}"})
            except Exception:
                pass
        self.gamma_root = self.s.add_node("Grammar", {})
        self._gamma_meta_done = True
        return self.gamma_root

    @property
    def gamma_dynamic(self):
        """Γ_dynamic as a VIEW over the mind-graph: rebuild a Grammar of
        Productions from the Production nodes hanging off gamma_root each access
        (the substrate is the source of truth, not a Python list)."""
        from substrate import Grammar, Production, NodePattern
        if self.gamma_root is None:
            return Grammar([])
        prods = []
        for pid in self.inner.neighbours(self.gamma_root, "production"):
            pa = self.s.node(pid)["attrs"]
            src = next(iter(self.inner.neighbours(pid, "pattern.src")), None)
            tgt = next(iter(self.inner.neighbours(pid, "pattern.tgt")), None)
            if src is None or tgt is None:
                continue
            sa, ta = self.s.node(src)["attrs"], self.s.node(tgt)["attrs"]
            prods.append(Production(
                src=NodePattern(sa.get("type"), sa.get("var", "s")),
                edge_type=pa.get("edge_type"),
                tgt=NodePattern(ta.get("type"), ta.get("var", "t")),
                where=self._where_from_mind(pid),
                provenance=pa.get("provenance", "")))
        return Grammar(prods)

    def _where_from_mind(self, pid):
        """Reconstruct a production's `where` Term from the JSON stored on its
        Production node (graph-resident, like a semiotic spec; None if absent)."""
        raw = self.s.node(pid)["attrs"].get("where_json")
        if not raw:
            return None
        import json
        from substrate.jsonio import term_from_json
        return term_from_json(json.loads(raw))

    def _append_production(self, production) -> object:
        """Grow Γ_dynamic by one production — a CHECKED transaction on self.s
        (gated by the meta-grammar), exactly like the body's edges. Builds the
        Production node + its pattern.src/tgt NodePattern subgraph; the optional
        `where` rides as JSON on the node (round-trips, reconstructable)."""
        self.boot_gamma_meta()
        attrs = {"edge_type": production.edge_type,
                 "provenance": production.provenance}
        if getattr(production, "where", None) is not None:
            import json
            from substrate.jsonio import term_to_json
            attrs["where_json"] = json.dumps(term_to_json(production.where))
        pid = self.s.add_node("Production", attrs)
        src = self.s.add_node("NodePattern",
                              {"type": production.src.type, "var": production.src.var})
        tgt = self.s.add_node("NodePattern",
                              {"type": production.tgt.type, "var": production.tgt.var})
        n = sum(1 for _ in self.inner.neighbours(self.gamma_root, "production"))
        self.inner.add_edge(self.gamma_root, "production", pid, {"index": n})
        self.inner.add_edge(pid, "pattern.src", src)
        self.inner.add_edge(pid, "pattern.tgt", tgt)
        return pid

    def _supersede_production(self, prod_idx, new_production) -> object:
        """Refine the prod_idx-th production: build the new one (gated) first,
        then DETACH the old from gamma_root — the old Production subgraph stays
        in the graph as an orphan (the substrate preserves its own history)."""
        edges = sorted(
            ((e["tgt"], e.get("attrs", {}).get("index", 0))
             for e in self.s.graph_to_dict()["edges"]
             if e["type"] == "production"
             and int(str(self.gamma_root).lstrip("#")) == e["src"]),
            key=lambda x: x[1])
        pid = self._append_production(new_production)
        if prod_idx < len(edges):
            old_tgt = edges[prod_idx][0]
            self.inner.remove_edge(self.gamma_root, "production",
                                   __import__("substrate_rs").NodeID(old_tgt))
        return pid

    def _stamp_theorem_temporal_state(self, tnode) -> None:
        a = self.s.node(tnode)["attrs"]
        name = a.get("name", "")
        if name == "quality_monotone_non_decreasing":
            self.inner.set_attr(tnode, "prev_quality", float(a.get("current_quality", 0.0)))
            self.inner.set_attr(tnode, "current_quality", float(self.quality_of_gamma()))
        elif name == "discovery_converges":
            n_now = len(self._discovered_relations)
            n_prev = int(a.get("_prev_n_relations", 0))
            self.inner.set_attr(tnode, "prev_delta", int(a.get("current_delta", 0)))
            self.inner.set_attr(tnode, "current_delta", n_now - n_prev)
            self.inner.set_attr(tnode, "_prev_n_relations", n_now)

    def check_theorems(self) -> dict:
        """Evaluate each Theorem's SEEDED predicate Term (via EvalSubgraph) after
        stamping the temporal scalars it reads; record last_held/held/check_count
        as graph state. The verdict is the seeded Term, not Python."""
        results = {}
        for tnode in self._theorem_nodes():
            self._stamp_theorem_temporal_state(tnode)
            try:
                held = bool(self.inner.evaluate(
                    self._THEOREM_PREDICATE_TERM,
                    {"t": tnode, "agent": self.agent, "self": tnode}))
            except Exception:
                held = False
            a = self.s.node(tnode)["attrs"]
            prior = a.get("held", True)
            self.inner.set_attr(tnode, "last_held", held)
            self.inner.set_attr(tnode, "held", bool(prior) and held)
            self.inner.set_attr(tnode, "check_count", int(a.get("check_count", 0)) + 1)
            results[a.get("name", "")] = held
        return results

    def theorem_state(self) -> dict:
        out = {}
        for tnode in self._theorem_nodes():
            a = self.s.node(tnode)["attrs"]
            out[a["name"]] = {"held": bool(a.get("held", True)),
                              "last_held": bool(a.get("last_held", True)),
                              "checks": int(a.get("check_count", 0))}
        return out

    def live_examined(self, world, n_games: int = 3, max_plies: int = 40,
                      grow_every_game: int = 1) -> None:
        """live() that also registers senses/models boundary edges and checks
        the theorems after each game's discovery — orchestration only."""
        acts_on = world.get("interpret_acts_on", lambda *a: [])
        preview_safe = world.get("preview_safe", True)
        games = 0
        for _ in range(n_games):
            substrate, ctx = world["reset"]()
            self.observe(substrate)
            self.register_senses(self.senses())
            for _ in range(max_plies):
                actions = world["legal_actions"](substrate, ctx)
                if not actions:
                    break
                cur_s, cur_c = substrate, ctx
                touches_fn = lambda a, s=cur_s, c=cur_c: acts_on(s, c, a)
                if preview_safe:
                    preview_fn = lambda a, s=cur_s, c=cur_c: world["apply_action"](s, c, a)[0]
                    action = self.choose_action_meta_curious(actions, preview_fn, touches_fn)
                else:
                    action = self.choose_action_meta_curious(actions, lambda a: None, touches_fn)
                touched = list(touches_fn(action))
                for t in touched:
                    self.register_relation(t, "acts_on")
                self.record_activity("act", touched)
                gate = self._authorize_world_action(world, substrate, ctx, action)
                if gate["decision"] != "commit" or not gate["authorized"]:
                    self.cognitive_tick()
                    continue
                substrate, ctx = world["apply_action"](substrate, ctx, action)
                self.observe(substrate)
                self.register_senses(self.senses())
            games += 1
            if games % grow_every_game == 0:
                self.discover_relations()
                self.register_models_from_grown()
                self.check_theorems()
                self.discover_theorems()

    # --- master thread: the `init`-shaped orchestrator -----------------------

    @property
    def _master(self) -> dict:
        m = getattr(self, "_master_state", None)
        if m is None:
            m = {"tick": 0, "reflex_responses": {}, "reflex_nodes": {}, "thread_steps": {},
                 "goal_resolvers": {}}
            self._master_state = m
        return m

    @property
    def activity_tick(self) -> int:
        return self._master["tick"]

    def register_reflex_response(self, name: str, fn) -> None:
        self._master["reflex_responses"][name] = fn

    def install_reflex(self, name: str, stimulus_term_json: dict,
                       response: str, refractory_ticks: int = 0):
        """Install a graph-resident Reflex: stimulus is a Term the substrate
        evaluates, response is a registered callable key. The firing decision is
        the Term; the response side effect is the I/O boundary."""
        existing = self._master["reflex_nodes"].get(name)
        root = self.inner.add_term_subgraph(stimulus_term_json)
        if existing is not None:
            self.inner.set_attr(existing, "response", response)
            self.inner.set_attr(existing, "refractory_ticks", int(refractory_ticks))
            for tgt in list(self.inner.neighbours(existing, "stimulus_term")):
                self.inner.remove_edge(existing, "stimulus_term", tgt)
            self.inner.add_edge_unchecked(existing, "stimulus_term", root)
            return existing
        nid = self.s.add_node("Reflex", {
            "name": name, "response": response, "refractory_ticks": int(refractory_ticks),
            "last_fired_tick": -(10 ** 9), "fire_count": 0})
        self.inner.add_edge_unchecked(self.agent, "has_reflex", nid)
        self.inner.add_edge_unchecked(nid, "stimulus_term", root)
        self._master["reflex_nodes"][name] = nid
        return nid

    def reflex(self, name: str):
        cached = self._master["reflex_nodes"].get(name)
        if cached is not None:
            return cached
        for n in self.s.nodes("Reflex"):    # seed-loaded reflexes live in the graph
            if self.s.node(n)["attrs"].get("name") == name:
                return n
        return None

    def reflexes(self) -> list:
        return list(self._master["reflex_nodes"].values())

    # --- the enact faculty: execute a plan tree on tick (seeds/enact.json) -----

    def _enact_advance(self):
        """The execute-on-tick reflex RESPONSE — the I/O boundary. Walk the plan tree by
        one step: prune Branches, re-arm Fixes whose guard is unmet, then run the next
        pending PlanAct's bound operator's enactment Term (the DECISION is that Term,
        graph-resident; selected by the seeded operator-selection join) and emit/write its
        result, marking the act executed. No decision here — it only EVALUATES the agent's
        own Terms (the cond/guard/enact) and applies their results."""
        import json
        # [V2] BRANCH-PRUNE: evaluate each unpruned Branch's cond Term; mark the UNTAKEN
        # child subtree executed so only the taken branch runs.
        for br in self.s.nodes("PlanBranch"):
            if self.s.node(br)["attrs"].get("pruned"):
                continue
            ct = self.s.node(br)["attrs"].get("cond_term")
            if ct is None:
                continue
            taken = bool(self.inner.evaluate(json.loads(ct), {}))
            for c in self.inner.neighbours(br, "else" if taken else "then"):
                self.inner.set_attr(c, "status", "executed")
            self.inner.set_attr(br, "pruned", True)
        # [V2] FIX-REARM: a Fix re-fires its body to a FIXPOINT — once the body is drained
        # but the guard Term does NOT yet hold, re-pend the body so it runs again; when the
        # guard holds, the Fix is done (body stays executed). "repeatedly B until P".
        for fx in self.s.nodes("PlanFix"):
            gt = self.s.node(fx)["attrs"].get("guard_term")
            if gt is None:
                continue
            if self.inner.evaluate(json.loads(gt), {}):
                self.inner.set_attr(fx, "active", 0.0)   # guard holds -> Fix reached fixpoint
                continue
            body = self.inner.neighbours(fx, "body")
            if body and all(self.s.node(b)["attrs"].get("status") == "executed" for b in body):
                for b in body:
                    self.inner.set_attr(b, "status", "pending")   # re-arm toward the fixpoint
        # run the next pending act
        for a in self.s.nodes("PlanAct"):
            if self.s.node(a)["attrs"].get("status") != "pending":
                continue
            ops = self.inner.neighbours(a, "enact")
            if not ops:
                continue                      # not yet bound by select_operator
            op = ops[0]
            et = self.s.node(op)["attrs"].get("enact_term")
            if et:
                env = {}                      # the act's role bindings -> the enact Term's vars
                for role in ("theme", "goal", "patient", "co_theme", "instrument", "source"):
                    b = self.inner.neighbours(a, role)
                    if b:
                        env[role] = b[0]
                result = self.inner.evaluate(json.loads(et), env)
                writes = self.s.node(op)["attrs"].get("writes")
                if writes:                    # graph side-effect (e.g. advance a counter)
                    self.inner.set_attr(self.agent, writes, result)
                else:                         # emit to the world
                    self.inner.set_attr(self.agent, "chosen_action", result)
            self.inner.set_attr(a, "status", "executed")
            return                            # one act per tick — the loop walks the plan

    _ENACT_STIMULUS = {
        "type": "Or", "items": [
            {"type": "Gte", "a": {"type": "Count", "source": {"type": "Filter",
                "source": {"type": "NodesOfType", "node_type": "PlanAct"}, "var_name": "x",
                "predicate": {"type": "Eq", "a": {"type": "Attr",
                    "node": {"type": "Var", "name": "x"}, "key": "status"},
                    "b": {"type": "Lit", "value": "pending"}}}}, "b": {"type": "Lit", "value": 1}},
            # also fire while a Fix is still iterating, so the body gets re-armed even when
            # no Act is momentarily pending (the body just executed) — keeps the loop alive.
            {"type": "Gte", "a": {"type": "Count", "source": {"type": "Filter",
                "source": {"type": "NodesOfType", "node_type": "PlanFix"}, "var_name": "f",
                "predicate": {"type": "Eq", "a": {"type": "Attr",
                    "node": {"type": "Var", "name": "f"}, "key": "active"},
                    "b": {"type": "Lit", "value": 1.0}}}}, "b": {"type": "Lit", "value": 1}}]}

    def wire_enact_faculty(self):
        """Install the execute-on-tick reflex (the `enact` seed's runner): STIMULUS = a
        pending PlanAct exists (a graph-native firing Term); RESPONSE = `_enact_advance`
        (the I/O boundary that runs the bound operator's Term and emits). Idempotent.
        Call once the `enact` seed is loaded; thereafter master_tick() walks any plan."""
        self.register_reflex_response("enact_advance", lambda ag: ag._enact_advance())
        self.install_reflex("enact_advance", self._ENACT_STIMULUS, "enact_advance")

    # --- the question-driving faculty: advance a dispatched Goal on tick ------
    # (seeds/question_driving.json's `question_pursue` reflex + resolver join).

    def wire_question_faculty(self, pack_caps: dict) -> None:
        """Register a question-driving pack's resolver CALLABLES (the pack's
        verify/answer_call/reflect/feed/deep_reads capabilities, keyed by the
        Resolver NAME they bind — `elevator_compute`/`know_ground`/`reflect`/
        `contrast`/`gap_parse`, seeds/question_driving.json) into
        `self._master["goal_resolvers"]`. Mechanical registration (per-drive,
        like `register_reflex_response`) — no decision; `_question_pursue_
        advance` only LOOKS UP which resolver is bound, it never branches on
        graph state to choose one."""
        self._master["goal_resolvers"].update(pack_caps)

    def _question_pursue_advance(self):
        """The `question_pursue` reflex's RESPONSE (the I/O boundary), shaped
        EXACTLY like `_enact_advance`: walk Goal nodes with status "dispatched";
        for each, read its BOUND Resolver (the `qd_bind_resolver` JOIN already
        wired `goal -resolve_with-> resolver`, not a Python if/elif), look up
        that resolver's NAME in the `goal_resolvers` registry (`wire_question_
        faculty` populated it), and call it with (self, goal_node). The callable
        (a module-level function in `domains/question_driver.py`) writes
        answer/verified/confidence/wall_kind/status onto the Goal node and
        returns — this executor never branches on graph state beyond "which
        resolver name is bound" (a lookup, not a decision). One goal advanced
        per firing (matches the one-Act-per-tick `_enact_advance` precedent);
        the C2 pump loops until the root Goal resolves or walls."""
        for g in self.s.nodes("Goal"):
            if self.s.node(g)["attrs"].get("status") != "dispatched":
                continue
            resolvers = self.inner.neighbours(g, "resolve_with")
            if not resolvers:
                continue                      # not yet bound (qd_bind_resolver hasn't joined it)
            resolver_name = self.s.node(resolvers[0])["attrs"].get("name")
            fn = self._master["goal_resolvers"].get(resolver_name)
            if fn is None:
                continue                      # this pack doesn't wire this resolver — honest no-op
            fn(self, g)
            if self.s.node(g)["attrs"].get("status") != "dispatched":
                return                        # this goal advanced — one advancing act per firing
            # a deliberate no-op resolver (e.g. "contrast" — the decision there is
            # a graph RULE, qd_contrast_compare, not this callable) left the Goal
            # dispatched; try the NEXT dispatched goal in this same firing instead
            # of starving it forever behind a pass-through resolver.

    def _frontier_advance(self):
        """Materialize the agent's own frontier pick — the `autonomy` seed's runner.
        Read the graph-resident `frontier_pick` Term (the MIGRATED gap-ranking decision,
        stored as data on the understand Drive), evaluate it, and write its result as an
        `ag -frontier_pick-> axis` edge. The seeded `mint_goal_from_frontier` rule then
        promotes that edge to a wanted goal. This is the sanctioned I/O boundary that the
        rule engine can't do itself (add_edge needs a bound target, not a computed Argmax);
        no decision here — the DECISION is the Term, graph-resident."""
        import json
        if not self.s.nodes("CapabilityAxis"):
            return
        drives = [n for n in self.s.nodes("Drive")
                  if self.s.node(n)["attrs"].get("name") == "understand"]
        if not drives:
            return
        term_json = self.s.node(drives[0])["attrs"].get("frontier_pick_term")
        if not term_json:
            return
        pick = self.inner.evaluate(json.loads(term_json), {})
        if pick is None:
            return
        for old in self.inner.neighbours(self.agent, "frontier_pick"):
            if old != pick:                       # keep a single live pick
                self.s.remove_edge(self.agent, "frontier_pick", old)
        self.s.add_edge(self.agent, "frontier_pick", pick)

    _FRONTIER_STIMULUS = {
        "type": "Gte", "a": {"type": "Count", "source": {"type": "Filter",
            "source": {"type": "NodesOfType", "node_type": "CapabilityAxis"}, "var_name": "x",
            "predicate": {"type": "Eq", "a": {"type": "Attr",
                "node": {"type": "Var", "name": "x"}, "key": "is_axis"},
                "b": {"type": "Lit", "value": 1.0}}}}, "b": {"type": "Lit", "value": 1}}

    def wire_autonomy_faculty(self):
        """Install the frontier materializer reflex (the `autonomy` seed's runner):
        STIMULUS = a synthesized CapabilityAxis exists; RESPONSE = `_frontier_advance`
        (evaluate the migrated frontier_pick Term, write the pick edge for the mint rule).
        Idempotent. With this wired, master_tick() + tick() self-drives the loop:
        materialize pick -> mint goal -> select -> pursue (enact) -> satisfy -> re-mint."""
        self.register_reflex_response("frontier_advance", lambda ag: ag._frontier_advance())
        self.install_reflex("frontier_advance", self._FRONTIER_STIMULUS, "frontier_advance")

    def _run_investigation_reflex(self):
        """Mechanical RESPONSE: run the bound investigation faculty against the speech
        world and lay measures_axis. The DECISION (which faculty, which axis) is the
        graph join that bound `investigates_op` (bind_investigation_faculty); this only
        ENACTS it — the heavy DSP / piper / whisper cannot live in a DSL Term, so the
        executor is mechanical I/O (it fires the agent's HELD ops + writes the measured
        scalar). One act per tick, like _enact_advance. Investigation acts carry NO
        `enact` edge, so _enact_advance ignores them (and vice-versa)."""
        sw = self._investigation_world()   # any world (speech/maze/arc/toy); may be None for subroutine ops
        for a in self.s.nodes("PlanAct"):
            attrs = self.s.node(a)["attrs"]
            if attrs.get("status") != "pending":
                continue
            ops = self.inner.neighbours(a, "investigates_op")
            if not ops:
                continue                       # not an investigation act (or not yet bound)
            themes = self.inner.neighbours(a, "theme")
            if not themes:
                continue
            op_attrs = self.s.node(ops[0])["attrs"]
            ax = themes[0]
            ax_attrs = self.s.node(ax)["attrs"]
            req = {"operator": op_attrs.get("runner"),
                   "capability_keys": ax_attrs.get("capability_keys") or [],
                   "measurement_key": op_attrs.get("metric", ""),
                   "target": float(op_attrs.get("target", 0.6) or 0.6),
                   "approach": op_attrs.get("approach", ""),
                   "lang": op_attrs.get("lang", "")}
            sub_name = op_attrs.get("subroutine")
            is_composed = op_attrs.get("runner") == "composed"
            if not sub_name and not is_composed and sw is None:
                continue                        # no world + not subroutine/composed-backed: nothing to run
            try:
                if sub_name:                    # the agent's AUTHORED faculty -> RUN its Term-tree
                    # hand the faculty the work-item it is BOUND to (this PlanAct's axis), so it
                    # reads its OWN frontier element, not a global pointer that may have shifted.
                    result = self.run_subroutine(sub_name, {"axis": ax})
                    measured = (float(result) if isinstance(result, (int, float))
                                else (1.0 if result else 0.0))
                    mc = self.s.add_node("MeasuredCapability", {
                        "measured": measured,
                        "target": float(op_attrs.get("target", 0.6) or 0.6),
                        "metric": op_attrs.get("metric", "authored"), "synth_pending": 1,
                        "note": f"ran authored subroutine {sub_name!r} -> {str(result)[:60]}"})
                elif is_composed:               # GAP 2: the agent's SELF-COMPOSED faculty (no teacher)
                    # Generic composed runner (domain-agnostic, subsumes the maze composed_routing
                    # branch): run each held part the composition was assembled from, combine the
                    # results. A part runs via its own subroutine (pure graph) or the world executor.
                    measured = self._run_composed_op(ops[0], ax, req, sw)
                    mc = self.s.add_node("MeasuredCapability", {
                        "measured": measured,
                        "target": float(op_attrs.get("target", 0.6) or 0.6),
                        "metric": op_attrs.get("metric", "composed"), "synth_pending": 1,
                        "note": f"ran SELF-COMPOSED op over {len(self.inner.neighbours(ops[0], 'composed_from'))} held parts"})
                elif sw is not None:
                    mc = sw.execute(req)
                else:
                    mc = None
            except Exception as e:             # noqa: BLE001
                self.inner.set_attr(a, "status", "executed")
                self.inner.set_attr(a, "run_error", f"{type(e).__name__}: {e}")
                return
            if mc is not None:
                try:
                    self.s.add_edge(mc, "measures_axis", ax)
                except Exception:
                    pass
                # WORLD-AGNOSTIC FRESHNESS: bank_measurement_to_axis single-fires per node via a
                # `banked` exclusion edge and needs ONE measurement banked per trial to advance
                # mf_stall (the plateau counter the escalation ladder climbs on). A world whose
                # execute() reuses a MeasuredCapability node (i.e. didn't pass fresh=True to
                # record_measured_capability) leaves the OLD `banked` edge in place, so the next
                # trial never re-banks and mf_stall freezes -> the ladder cannot climb. The
                # investigation EXECUTOR (this reflex), not each world, guarantees per-trial
                # banking: strip any stale `banked` edge so this trial's measurement banks exactly
                # once. (Fresh nodes have none -> no-op; the within-tick single-fire is unaffected,
                # the edge is re-laid inside the fixpoint.) Now ANY world's loop climbs.
                try:
                    for old in list(self.inner.neighbours(mc, "banked")):
                        self.s.remove_edge(mc, "banked", old)
                except Exception:
                    pass
            self.inner.set_attr(a, "status", "executed")
            return                              # one investigation per tick

    def wire_investigation_faculty(self, world):
        """Install the investigation-run reflex: STIMULUS = a pending PlanAct exists
        (same firing Term as enact); RESPONSE = `_run_investigation_reflex`, which acts
        ONLY on acts bound via `investigates_op` and runs the wired world's executor. The
        faculty/affordance selection is the seeded bind_investigation_faculty JOIN; this
        reflex only enacts it. Idempotent.

        The world is ANY surface with `execute(req)` (+ optional `author_faculty`) — speech,
        maze, arc, a toy abstract world. The self-debug ladder it feeds (investigate ->
        stall -> escalate -> AUTHOR a tool) is domain-agnostic (see
        escalation_domain_agnostic), so the agent debugs itself in WHATEVER world it is
        wired to. `_speech_world` is kept as a back-compat alias of `_world`."""
        self._world = world
        self._speech_world = world          # legacy alias (scripts that set/read it still work)
        self.register_reflex_response(
            "run_investigation", lambda ag: ag._run_investigation_reflex())
        self.install_reflex("run_investigation", self._ENACT_STIMULUS, "run_investigation")

    def _investigation_world(self):
        """The world the agent debugs/self-extends in — generic, not speech-bound. Prefers the
        decoupled `_world` handle; falls back to the legacy `_speech_world` attribute that some
        scripts still set directly. Either way the surface is just `execute`(+`author_faculty`)."""
        return getattr(self, "_world", None) or getattr(self, "_speech_world", None)

    def _run_composed_op(self, op, ax, req, sw):
        """GAP 2 generic composed runner (domain-agnostic, subsumes the maze composed_routing branch):
        run each held part the composition was assembled from (composed_from), combine the results
        (mean). A part runs via its own subroutine (pure graph), the world executor, or a fixed
        contribution attr. Reads composed_from off the graph — no per-domain compose branch."""
        vals = []
        for p in self.inner.neighbours(op, "composed_from"):
            pa = self.s.node(p)["attrs"]
            psub = pa.get("subroutine")
            try:
                # A held part runs by its OWN faculty first — a subroutine (pure graph) or a known
                # contribution (its proven efficacy the agent holds) — and only falls back to the world
                # executor if it has neither. The world executor is the FRONTIER's measurer, not the part's.
                if psub:
                    r = self.run_subroutine(psub, {"axis": ax})
                    vals.append(float(r) if isinstance(r, (int, float)) else (1.0 if r else 0.0))
                elif pa.get("contribution") is not None:
                    vals.append(float(pa.get("contribution")))
                elif sw is not None and pa.get("runner"):
                    preq = dict(req)
                    preq["operator"] = pa.get("runner")
                    preq["measurement_key"] = pa.get("metric", "")
                    pmc = sw.execute(preq)
                    vals.append(float(self.s.node(pmc)["attrs"].get("measured", 0.0)) if pmc else 0.0)
            except Exception:
                pass
        if not vals:
            return 0.0
        # weight the parts' mean by COVERAGE: a composition missing a needed key cannot fully solve the
        # capability, so a partial composition measures below a full one — which lets it genuinely plateau
        # short of target and surface the honest partial impasse rather than falsely confirming.
        cov = 1.0
        req = self.inner.neighbours(ax, "requires_key")
        if req:
            cov = len(self.inner.neighbours(ax, "covered_key")) / len(req)
        return (sum(vals) / len(vals)) * cov

    def wire_self_extension(self):
        """GAP 2: load the self_extension rules and BACKFILL the CapKey join from existing
        capability_keys list-attrs, so the compose rules work on real seeded axes/faculties without
        rewriting every seed. CapabilityAxis.capability_keys -> requires_key; a held faculty's provided
        keys (provides_keys / capability_keys) -> provides_key + reliability (its best saturation).
        Get-or-create CapKey by name (idempotent). Mechanical graph construction; no decision.

        MARKER-GUARDED (2026-08-14, SHAPE_AUDIT.md §4.6 fix): `load_seed_manifest`
        mints every manifest node with `add_node` unconditionally -- ALL
        idempotency in this system is the CALLER'S marker check (every other
        call site honours that: `boot_core.load_seeds_into` checks `Seed{id}` +
        `SeedSummary{seed_id}`; `reflective_faculty._ensure_shape_decode_loop`
        checks `_installed_seed_ids`). This call site had none -- a second
        `wire_self_extension()` on the same agent (e.g. a resumed checkpoint
        that already ran it) would mint a second copy of every self_extension
        rule, the exact bug class the Wave-3 `load_seeds_into` fix documents
        (`tests/test_capkey_backfill_migrated.py:82` even calls this
        "(idempotent)" while it wasn't). Guarded the same way
        `_ensure_shape_decode_loop` is: a `Seed{id:"self_extension"}` marker
        node, checked via the SAME `_installed_seed_ids` reader (also catches
        a `SeedSummary` marker from a full `load_all_seeds` boot, so this
        doesn't double-install on top of THAT convention either)."""
        from substrate.seed_loader import manifest_for
        from domains.reflective_faculty import _installed_seed_ids
        if "self_extension" not in _installed_seed_ids(self.s):
            try:
                self.inner.load_seed_manifest(manifest_for("self_extension"), self.agent)
                self.s.add_node("Seed", {"id": "self_extension", "version": "1.0.0"})
            except Exception:
                pass
        keymap = {}
        for ck in self.s.nodes("CapKey"):
            nm = self.s.node(ck)["attrs"].get("name")
            if nm:
                keymap[nm] = ck

        def capkey(name):
            if name not in keymap:
                keymap[name] = self.s.add_node("CapKey", {"name": name})
            return keymap[name]

        def edge_once(src, etype, tgt):
            if tgt not in self.inner.neighbours(src, etype):
                self.inner.add_edge_unchecked(src, etype, tgt)

        for ax in self.s.nodes("CapabilityAxis"):
            for k in (self.s.node(ax)["attrs"].get("capability_keys") or []):
                edge_once(ax, "requires_key", capkey(str(k)))
        for ntype in ("Operator", "OperationPrimitive", "RoutingPrimitive", "Primitive"):
            for op in self.s.nodes(ntype):
                at = self.s.node(op)["attrs"]
                if at.get("composed") == 1:           # a composed op must not advertise as a primitive
                    continue
                provided = at.get("provides_keys") or at.get("capability_keys") or []
                for k in provided:
                    edge_once(op, "provides_key", capkey(str(k)))
                if provided and "reliability" not in at:
                    self.inner.set_attr(op, "reliability",
                                        float(at.get("sat_best", at.get("saturation", 0.5)) or 0.5))

    _IMPASSE_STIMULUS = {
        "type": "Gte", "a": {"type": "Count", "source": {
            "type": "NodesOfType", "node_type": "Impasse"}},
        "b": {"type": "Lit", "value": 1}}

    def wire_teacher_resolution(self):
        """Enable the graph-native teacher loop: install the auto_resolve_impasse Reflex
        (the GATE _auto_resolve_impasse_tick checks each master_tick before spawning ONE
        off-thread teacher call for the next unresolved, free-text Impasse). The response
        is a noop — the tick itself does the spawning/draining. Pair with set_self_teacher.
        Idempotent."""
        self.register_reflex_response("auto_resolve_impasse", lambda ag: None)
        self.install_reflex("auto_resolve_impasse", self._IMPASSE_STIMULUS,
                            "auto_resolve_impasse")

    def _self_extend_reflex(self):
        """ORDER-4 authoring faculty: consume a self_extend Impasse (needs_tool -> axis) by
        AUTHORING a new Operator for that capability and binding the axis to it. The teacher
        decides the new approach (method only); the agent authors it as graph data and the
        next confidence trial tests it. Mechanical I/O + the agent's authoring decision; no
        decision over graph state about WHAT to investigate. One per tick."""
        for mi in self.s.nodes("Impasse"):
            a = self.s.node(mi)["attrs"]
            if a.get("authored") == 1:
                continue
            axes = self.inner.neighbours(mi, "needs_tool")
            if not axes:
                continue
            ax = axes[0]
            # GAP 2: DEFER to the self_extension compose rules. If they already composed a faculty from
            # held primitives for this axis, or surfaced an honest HumanImpasse because nothing covers
            # the need, this reflex authors NOTHING — no teacher, no placeholder that fakes success.
            ax_at = self.s.node(ax)["attrs"]
            if (ax_at.get("needs_human") == 1
                    or any(self.s.node(o)["attrs"].get("composed") == 1
                           for o in self.inner.neighbours(ax, "investigated_by"))):
                self.inner.set_attr(mi, "authored", 1)
                return
            keys = ax_at.get("capability_keys") or []
            worlds = self.inner.neighbours(self.agent, "operates_in")
            if not worlds:
                self.inner.set_attr(mi, "authored", 1)
                return
            w = worlds[0]
            # GAP 2: NO hosted teacher. The approach is COMPOSED from what the agent holds — a
            # graph-derived label over the capability keys. The self_extension compose rules
            # (compose_from_held_primitives / wire_composed_primitive) assemble the held primitives
            # whose advertised CapKeys cover these keys, with a known confidence (coverage x
            # reliability); and compose_zero_coverage_impasse surfaces an honest HumanImpasse when
            # nothing held touches the need — never a placeholder that fakes success. No claude -p.
            approach = "compose_held:" + "_".join(str(k) for k in keys)[:64]
            # GENUINE self-authoring: if the world can mechanically enact a real
            # faculty request (e.g. EXTEND THE EAR — change what it hears), the
            # returned spec is a runnable operator.  Absence or refusal is an
            # honest impasse; a fabricated "authored" operator would launder a
            # capability failure into apparent success.
            spec = None
            world = self._investigation_world()   # the world the agent debugs in — any world, not speech
            has_author = world is not None and hasattr(world, "author_faculty")
            if has_author:
                try:
                    real = world.author_faculty(keys, approach)
                    if real:
                        spec = real
                        approach = real.get("approach", approach)
                except Exception:
                    pass
            if spec is None:
                # No authoring surface and an authoring surface that refused are
                # observationally the same at this seam: no executable faculty
                # exists.  The graph can escalate from the explicit exhaustion
                # marker; Python must not choose a pretend replacement.
                self.inner.set_attr(ax, "authoring_exhausted", 1.0)
                self.inner.set_attr(mi, "authored", 1)
                return
            newop = self.s.add_node("Operator", {
                "name": f"authored_{spec.get('name') or '_'.join(str(k) for k in keys)[:24]}",
                "runner": spec.get("runner", "authored"),
                "metric": spec.get("metric", "authored_metric"),
                "target": float(spec.get("target", 0.6)),
                "authored_by_escalation": 1.0, "approach": approach})
            try:
                self.inner.add_edge_unchecked(newop, "applies_in", w)
                for old in list(self.inner.neighbours(ax, "investigated_by")):
                    self.inner.remove_edge(ax, "investigated_by", old)
                self.inner.add_edge_unchecked(ax, "investigated_by", newop)
            except Exception:
                pass
            self.inner.set_attr(ax, "mf_stall", 0)
            self.inner.set_attr(ax, "shortfall", 0.7)   # keep it the active concern for its trial
            self.inner.set_attr(mi, "authored", 1)
            # do NOT resolve here: the next confidence trial tests the authored tool. If it
            # works, escalation_resolve_high_confidence resolves; if not, the climb continues.
            return

    def _self_rethink_reflex(self):
        """ORDER-6: consume a self_rethink Impasse by running the agent's OWN self-reflection
        (re-examine how it is organised / shaped — its self-model) and recording the
        reassessment. Mechanical invocation of the agent's reflective faculty. One per tick."""
        for mi in self.s.nodes("Impasse"):
            a = self.s.node(mi)["attrs"]
            if a.get("kind") != "self_rethink" or a.get("reflected") == 1:
                continue
            summary = "re-examined my approach to this class of problem"
            try:
                from domains import reflective_faculty as rf
                res = rf.reflect("self_shape", None, self.s) if hasattr(rf, "reflect") else None
                if isinstance(res, dict) and res.get("summary"):
                    summary = str(res["summary"])[:160]
            except Exception:
                pass
            node = self.s.add_node("SelfReassessment",
                                   {"trigger": "order6_rethink_self", "summary": summary})
            try:
                self.inner.add_edge_unchecked(self.agent, "reassessed", node)
            except Exception:
                pass
            self.inner.set_attr(mi, "reflected", 1)
            return

    def wire_escalation_faculties(self):
        """Install the order-4 (author a new operator) and order-6 (rethink self) reflexes
        that consume the escalation ladder's routing markers (needs_tool / self_rethink).
        Idempotent. Pair with the impasse_escalation seed."""
        self.register_reflex_response("self_extend", lambda ag: ag._self_extend_reflex())
        self.install_reflex("self_extend", self._IMPASSE_STIMULUS, "self_extend")
        self.register_reflex_response("self_rethink", lambda ag: ag._self_rethink_reflex())
        self.install_reflex("self_rethink", self._IMPASSE_STIMULUS, "self_rethink")


    def _merge_seed_loaded_reflexes(self) -> None:
        """Lazily discover graph-resident Reflex nodes a SEED shipped (the
        `"reflexes"` manifest key, load_seed_manifest) that aren't yet in the
        `reflex_nodes` cache `install_reflex` populates — merge them in by name
        so a manifest-shipped reflex (e.g. `question_pursue`,
        seeds/question_driving.json) actually fires without a separate Python
        `install_reflex` call. Mechanical cache sync (the graph is the source of
        truth); no decision over which reflexes exist."""
        cache = self._master["reflex_nodes"]
        for n in self.s.nodes("Reflex"):
            nm = self.s.node(n)["attrs"].get("name")
            if nm and nm not in cache:
                cache[nm] = n

    def fire_reflexes(self) -> list:
        self._merge_seed_loaded_reflexes()
        now = self._master["tick"]
        fired = []
        excluded = []
        agent_id = self.agent.value if hasattr(self.agent, "value") \
            else int(str(self.agent).lstrip("#"))
        ordered = [
            nid.value if hasattr(nid, "value") else int(str(nid).lstrip("#"))
            for nid in self._master["reflex_nodes"].values()
        ]
        while True:
            dispatch = self.inner.next_ready_reflex(
                agent_id, int(now), ordered, excluded)
            if dispatch is None:
                break
            nid_value, name, response = dispatch
            excluded.append(int(nid_value))
            fn = self._master["reflex_responses"].get(response)
            if fn is not None:
                fn(self)
            fired.append(name)
        return fired

    def fork_thread(self, task: str, priority: float = 1.0, step=None,
                    parent=None, cortex=None):
        nid = self.s.add_node("Thread", {"task": task, "priority": float(priority), "state": "active"})
        self.inner.add_edge_unchecked(self.agent, "has_thread", nid)
        if step is not None:
            self._master["thread_steps"][nid] = step
        # optional graph-resident structure: a child of a parent thread
        # (recursive sub-concern) and/or rooted in a cortex. Mechanical edge
        # bookkeeping — the same `child_thread` / `in_cortex` edges the old
        # CuriousAgent wrote, here on the substrate.
        if parent is not None:
            self.inner.add_edge_unchecked(parent, "child_thread", nid)
        if cortex is not None:
            self.inner.add_edge_unchecked(nid, "in_cortex", cortex)
        return nid

    def threads(self, state: str = "active") -> list:
        return [n for n in self.inner.neighbours(self.agent, "has_thread")
                if self.s.node(n)["attrs"].get("state") == state]

    def complete_thread(self, thread) -> None:
        self.inner.set_attr(thread, "state", "done")

    def tick_threads(self):
        """Run ONE step of the highest-priority active thread (priority pick is a
        DSL Argmax — the substrate decides); capture a raising step as errored."""
        actives = [t for t in self.threads("active") if t in self._master["thread_steps"]]
        if not actives:
            return None, None
        for t in actives:
            self.inner.add_edge_unchecked(self.agent, "master_candidate", t)
        choose = {"type": "Argmax", "var_name": "t",
                  "source": {"type": "Neighbours", "node": {"type": "Var", "name": "a"},
                             "edge_type": "master_candidate"},
                  "value": {"type": "Attr", "node": {"type": "Var", "name": "t"}, "key": "priority"}}
        chosen = self.inner.evaluate(choose, {"a": self.agent})
        for t in actives:
            self.inner.remove_edge(self.agent, "master_candidate", t)
        if chosen is None:
            return None, None
        step = self._master["thread_steps"][chosen]
        try:
            signal = step(self)
        except Exception as e:
            a = self.s.node(chosen)["attrs"]
            self.inner.set_attr(chosen, "state", "errored")
            self.inner.set_attr(chosen, "error_count", int(a.get("error_count", 0)) + 1)
            self.inner.set_attr(chosen, "last_error", f"{type(e).__name__}: {e}")
            self.inner.set_attr(chosen, "last_error_tick", int(self._master["tick"]))
            return chosen, chosen
        if signal == "done":
            self.complete_thread(chosen)
        return chosen, None

    def master_tick(self) -> dict:
        """init-shaped master tick: advance clock (surfaced as the agent `tick`
        attr for reflex stimulus Terms), FOLD the closed-loop corrections at the
        clock edge (the engine's graph-native `tock`), fire reflexes, run one thread step."""
        m = self._master
        m["tick"] += 1
        self.inner.set_attr(self.agent, "tick", int(m["tick"]))
        cycle = self.inner.run_cycle("master_legacy")
        fired = self.fire_reflexes()
        self._auto_resolve_impasse_tick()
        ran, captured = self.tick_threads()
        layer = getattr(self, "_concurrency", None)
        conc = layer.tick(self) if layer is not None else None
        return {"tick": int(m["tick"]), "reflexes_fired": fired,
                "thread_ran": ran, "thread_captured": captured,
                "concurrency": conc, "cycle": cycle}

    def _auto_resolve_impasse_tick(self):
        """The auto_resolve_impasse reflex's effect, fired each master tick: drain
        any finished teacher threads, then (if a self-teacher is registered and
        the reflex is installed) spawn ONE off-thread teacher call for the
        next unresolved, not-in-flight, free-text impasse. One spawn per tick so
        the loop stays non-blocking and the agent keeps running. The decision to
        resolve impasses is the graph-resident auto_resolve_impasse Reflex; this
        is its mechanical effect."""
        self._drain_completed_teacher_threads()
        if (getattr(self, "_self_teacher", None) is None
                or self.reflex("auto_resolve_impasse") is None):
            return
        in_flight = {tt["imp"] for tt in getattr(self, "_teacher_threads", [])}
        for imp in self.unresolved_impasses():
            attrs = self.s.node(imp)["attrs"]
            if attrs.get("render_gap_head") is not None or imp in in_flight:
                continue
            self._spawn_teacher_thread(imp)
            break

    # --- concurrency layer: off-thread work, results applied on the master ----

    def _ensure_concurrency_layer(self):
        """Lazy-init the ConcurrencyLayer (pure infrastructure from
        domains/concurrency.py; no substrate dependency, no decisions)."""
        if getattr(self, "_concurrency", None) is None:
            from domains.concurrency import ConcurrencyLayer
            self._concurrency = ConcurrencyLayer()
            self._default_worker_pool = None
            self._default_async_runner = None
        return self._concurrency

    def start_worker_pool(self, n=4, name="default"):
        """Start (or return the existing) named WorkerPool. Idempotent by name."""
        layer = self._ensure_concurrency_layer()
        for p in layer.pools:
            if p.name == name:
                return p
        from domains.concurrency import WorkerPool
        p = layer.add_pool(WorkerPool(n_workers=n, name=name))
        if self._default_worker_pool is None:
            self._default_worker_pool = p
        return p

    def start_async_runner(self, m=16, name="default"):
        """Start (or return the existing) named AsyncRunner. Idempotent by name."""
        layer = self._ensure_concurrency_layer()
        for r in layer.runners:
            if r.name == name:
                return r
        from domains.concurrency import AsyncRunner
        r = layer.add_runner(AsyncRunner(max_concurrent=m, name=name))
        if self._default_async_runner is None:
            self._default_async_runner = r
        return r

    def submit_work(self, fn, payload=None):
        """Dispatch CPU work to the default pool (lazy-init). Returns a task id."""
        if getattr(self, "_default_worker_pool", None) is None:
            self.start_worker_pool()
        return self._default_worker_pool.submit(fn, payload)

    def submit_async(self, coro_fn, payload=None):
        """Dispatch async work to the default runner (lazy-init). Returns a task id."""
        if getattr(self, "_default_async_runner", None) is None:
            self.start_async_runner()
        return self._default_async_runner.submit(coro_fn, payload)

    def start_memory_consolidation(self, period_s=5.0, consolidate_fn=None):
        """Start a CLS-shape periodic consolidation on the async runner; its
        consolidate_fn returns an apply(adapter) closure the master runs."""
        self._ensure_concurrency_layer()
        runner = self.start_async_runner()
        from domains.concurrency import MemoryConsolidationRunner
        mc = MemoryConsolidationRunner(runner=runner, consolidate_fn=consolidate_fn,
                                       period_s=period_s)
        mc.start()
        self._memory_consolidation = mc
        return mc

    def stop_concurrency(self):
        """Tear down all pools/runners/consolidation. Idempotent."""
        mc = getattr(self, "_memory_consolidation", None)
        if mc is not None:
            mc.stop()
            self._memory_consolidation = None
        layer = getattr(self, "_concurrency", None)
        if layer is not None:
            layer.stop_all()
        self._concurrency = None
        self._default_worker_pool = None
        self._default_async_runner = None

    def concurrency_state(self):
        """Snapshot of the concurrency layer (or {'active': False} when off)."""
        layer = getattr(self, "_concurrency", None)
        if layer is None:
            return {"active": False}
        return {"active": True,
                "pools": [{"name": p.name, "n_workers": p.n_workers}
                          for p in layer.pools],
                "runners": [{"name": r.name, "max_concurrent": r.max_concurrent}
                            for r in layer.runners]}

    # --- resource awareness: per-(action, self-attr) signed-delta EMAs -------

    _RESOURCE_NON_MARKERS = (
        "x_bin", "y_bin", "z_bin", "angle", "facing", "direction",
        "orientation", "time", "tick", "ticks_since")

    def set_self_attrs(self, attrs: dict) -> None:
        """Mirror the agent's own self-state (its `my_*` numeric attrs) onto the
        agent node. Mechanical I/O — nothing is decided here."""
        for k, v in attrs.items():
            if k.startswith("my_") and isinstance(v, _SCALAR):
                self.inner.set_attr(self.agent, k, v)

    def snapshot_self_attrs_at_decision(self) -> None:
        cur = self.s.node(self.agent)["attrs"]
        self.last_my_attrs_at_decision = {
            k: float(v) for k, v in cur.items()
            if k.startswith("my_") and isinstance(v, (int, float)) and not isinstance(v, bool)}

    def _ensure_action_stat(self, action: str):
        stat = self._action_stat_nodes.get(action)
        if stat is None:
            stat = self.s.add_node("ActionStat", {
                "action": action, "n": 0, "novelty_sum": 0,
                "failure_sum": 0.0, "boredom_sum": 0})
            self._action_stat_nodes[action] = stat
        return stat

    def record_self_attr_deltas(self, action: str, alpha: float = 0.01) -> None:
        """EMA-update per-(action, attr) signed deltas (current − decision-time
        snapshot) on the action's ActionStat node. Resource bidirectionality
        EMERGES from observation; mechanical bookkeeping."""
        stat = self._ensure_action_stat(action)
        cur = self.s.node(self.agent)["attrs"]
        sattrs = self.s.node(stat)["attrs"]
        for k, prev_val in self.last_my_attrs_at_decision.items():
            cur_val = cur.get(k)
            if cur_val is None or not isinstance(cur_val, (int, float)) or isinstance(cur_val, bool):
                continue
            delta = float(cur_val) - float(prev_val)
            ema_key = f"delta_{k}_ema"
            old = float(sattrs.get(ema_key, 0.0))
            self.inner.set_attr(stat, ema_key, alpha * delta + (1.0 - alpha) * old)

    def _bidirectional_resource_attrs(self, threshold: float = 0.01) -> set:
        pos_seen, neg_seen = set(), set()
        for stat in self._action_stat_nodes.values():
            for k, v in self.s.node(stat)["attrs"].items():
                if not (k.startswith("delta_my_") and k.endswith("_ema")
                        and isinstance(v, (int, float)) and not isinstance(v, bool)):
                    continue
                attr_name = k[len("delta_my_"):-len("_ema")]
                if attr_name in ("x", "y", "z"):
                    continue
                if any(m in attr_name for m in self._RESOURCE_NON_MARKERS):
                    continue
                if v > threshold:
                    pos_seen.add(attr_name)
                elif v < -threshold:
                    neg_seen.add(attr_name)
        return pos_seen & neg_seen

    def action_self_attr_delta_sum(self, action: str) -> float:
        stat = self._action_stat_nodes.get(action)
        if stat is None:
            return 0.0
        resource_attrs = self._bidirectional_resource_attrs()
        if not resource_attrs:
            return 0.0
        sattrs = self.s.node(stat)["attrs"]
        return sum(float(sattrs.get(f"delta_my_{a}_ema", 0.0)) for a in resource_attrs)

    def ensure_resource(self, attr_name: str, current_value: float):
        """Materialise a Resource node for a self-attr (current/observed_max/min),
        attached by manages_resource. The scarcity VALUE is the seeded
        resource_value_term — no formula reimplemented here."""
        rid = self._resource_nodes.get(attr_name)
        if rid is not None:
            a = self.s.node(rid)["attrs"]
            self.inner.set_attr(rid, "current", float(current_value))
            self.inner.set_attr(rid, "observed_max",
                                max(float(a.get("observed_max", current_value)), float(current_value)))
            self.inner.set_attr(rid, "observed_min",
                                min(float(a.get("observed_min", current_value)), float(current_value)))
            return rid
        rid = self.s.add_node("Resource", {
            "attr_name": attr_name, "current": float(current_value),
            "observed_max": float(current_value), "observed_min": float(current_value)})
        self.inner.add_edge_unchecked(self.agent, "manages_resource", rid)
        self._resource_nodes[attr_name] = rid
        return rid

    def resource_scarcity(self, attr_name: str) -> float:
        """Scarcity = EvalSubgraph of the SEEDED resource_value_term on the
        Resource node (1 − current/observed_max). The decision is the seed."""
        rid = self._resource_nodes.get(attr_name)
        if rid is None:
            return 0.0
        term = {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
            "type": "Neighbours", "node": {"type": "Var", "name": "a"},
            "edge_type": "resource_value_term"}}}
        return float(self.inner.evaluate(term, {"a": self.agent, "self": rid}))

    # --- action affinities: per-instance per-action freshening -> BodyType ----

    def _cc_relax_term(self):
        """The component-label flood Term (graph-resident decision; Rust iterates it),
        cached. cc_label(cell) = min over SAME-VALUE `neighbour` cells' cc_label —
        relaxed to a fixpoint this labels connected same-colour components. Same idiom
        as the routing relax Term, on a `cc_label` register instead of `_dist`."""
        if getattr(self, "_cc_relax", None) is None:
            v = lambda n: {"type": "Var", "name": n}
            a = lambda n, k: {"type": "Attr", "node": v(n), "key": k}
            same = {"type": "Filter", "source": {"type": "Neighbours",
                    "node": v("cell"), "edge_type": "neighbour", "any_type": False},
                    "var_name": "n", "predicate": {"type": "Eq",
                    "a": a("n", "value"), "b": a("cell", "value")}}
            mo = {"type": "MinOver", "source": same, "var_name": "n",
                  "value": a("n", "cc_label"), "default": a("cell", "cc_label")}
            self._cc_relax = {"type": "IfThenElse",
                "cond": {"type": "Lt", "a": mo, "b": a("cell", "cc_label")},
                "then": mo, "other": a("cell", "cc_label")}
        return self._cc_relax

    def perceive_frame(self, world_substrate) -> None:
        """The perception pipeline — the I/O boundary that ingests a frame and fires the
        agent's OWN graph-resident perception (figure/ground region grouping +
        avatar discovery) on tick. Mechanical orchestration ONLY (like routing stamps
        `_dist` then fires the relax Term): ingest -> clear stale region membership ->
        stamp each cell's component-label register -> flood it to a fixpoint (the agent's
        cc_relax Term) -> mark ready -> tick. Every DECISION is a graph-resident rule or
        Term (cc_materialise / cc_region_bounds / region_correspondence / avatar_agency);
        this only sequences them. Call instead of observe() when the region_grouping +
        avatar_agency seeds are loaded."""
        # THE EYE'S VALUE SOURCE. By default the eye reads cell values from the
        # world's raw integer grid (the oracle, cheap) — the standing behaviour,
        # BYTE-IDENTICAL when `pixel_eye` is off (getattr default False). When
        # `pixel_eye` is ON (opt-in, seeing-not-oracle) the eye instead recovers
        # the value grid from the RENDERED RGB pixels ALONE (worlds.arc.
        # recover_grid_from_render, the mechanical inverse of _render_screen) and
        # NEVER reads `arc3_grid` — the oracle grid is demoted to scoring only,
        # exactly as VizDoom depth/labels. Choosing the source is mechanical I/O
        # (a modality switch), not a perception decision: the carve/segmentation
        # is unchanged graph-native machinery over whichever value grid it is fed.
        if getattr(self, "pixel_eye", False):
            screen = getattr(world_substrate, "vision_screen", None)
            if screen is not None:
                from worlds.arc import recover_grid_from_render
                self._last_grid = recover_grid_from_render(screen)
            else:                              # no render published: honest fallback
                self._last_grid = getattr(world_substrate, "arc3_grid", None)
        else:
            self._last_grid = getattr(world_substrate, "arc3_grid", None)
        self.observe(world_substrate)
        # COLD START (frame 0 / Reset): seed component labels with a full flood so the
        # agent's cc_bootstrap rule can mint the initial persistent Regions. On every
        # LATER frame the agent's incremental membership rules (cell_leaves_region /
        # cell_joins_region / changed_cell_new_region, all has_change-driven) maintain
        # those persistent Regions in place — no full restamp, so the tick is O(changed),
        # not O(cells). Branching on the world's frame counter is mechanical I/O
        # sequencing (cold-start setup), not a perception decision — every figure/ground
        # judgement stays in the graph rules.
        games = [n for n in self.s.nodes("WorldInstance")
                 if self.s.node(n)["attrs"].get("world_type") == "Game"]
        game = games[0] if games else None
        frame = float(self.s.node(game)["attrs"].get("frame", 0)) if game else 0.0
        if game is not None:
            # THE EYE SEGMENTS AND TRACKS — every frame, natively. Connected-component
            # labelling (cv2, ~ms) + cross-frame identity (cell-overlap match to last
            # frame) are done HERE, in the eye, not as O(cells) graph rules (the old
            # cc/comp/merge machinery was ~3.4s/frame; correspondence-as-graph-rules hit
            # the same O(cells) match-enumeration wall). Tracking is stateful frame-to-
            # frame bookkeeping — trivial and fast imperatively, awkward in a fixpoint
            # engine — so we steal the efficient implementation. The eye hands cognition
            # already-identified PERSISTENT Region nodes (stable identity, drow/dcol,
            # within-membership); every figure/ground, occlusion, agency and order-N
            # JUDGEMENT over those Regions stays graph-native. This Python is the spec
            # for the native Rust `segment` primitive that replaces it.
            self._perceive_regions(game)
        self.tick()

    def _perceive_regions(self, game) -> None:
        """The eye: segment the grid (cv2 connected-components) AND track identity
        across frames (match each new component to last frame's region by cell-overlap),
        emitting/refreshing PERSISTENT Region nodes in place. Stateful (holds last
        frame's region footprints on self._prev_regions). Ground membership is CONSERVED
        (add-only: an occluded floor cell stays within the ground); figures re-point
        (their within follows their cells). Motion drow/dcol = centroid - prev centroid.
        Birth = a component matching no prior region; death = a prior region matched by
        no component. O(changed), not O(cells). Mechanical perception I/O — figure/ground
        meaning, occlusion, agency are the agent's graph rules over these Regions."""
        import numpy as np
        import cv2
        # Cell POSITIONS are stable -> build the (r,c)->node index ONCE and cache it.
        cells = getattr(self, "_cell_index", None)
        grid = getattr(self, "_last_grid", None)
        if cells is None or getattr(self, "_cell_dims", None) is None:
            cells = {}; maxr = maxc = -1
            for nid in self.s.nodes("WorldInstance"):
                a = self.s.node(nid)["attrs"]
                if a.get("world_type") != "Cell":
                    continue
                r, c = int(a["row"]), int(a["col"])
                cells[(r, c)] = nid
                maxr = max(maxr, r); maxc = max(maxc, c)
            if not cells:
                return
            self._cell_index = cells
            self._cell_dims = (maxr + 1, maxc + 1)
        H, W = self._cell_dims
        # cell VALUES come from the world's raw grid (handed over by build_world), not
        # from re-reading the substrate node-by-node every frame.
        if grid is not None:
            arr = np.asarray(grid, dtype=np.int32)
        else:
            arr = np.zeros((H, W), dtype=np.int32)
            for (r, c), nid in cells.items():
                arr[r, c] = self.s.node(nid)["attrs"]["value"]
        # NATIVE FAST PATH — the whole eye (segment + cross-frame track + graph mutation)
        # in one Rust call (faithful port of the cv2/Python tracker below). No per-cell FFI;
        # ~3ms -> sub-ms. Falls back to the Python path if the primitive isn't built in.
        seg = getattr(self.inner, "segment", None)
        if seg is not None:
            cell_ids = getattr(self, "_cell_ids_flat", None)
            if cell_ids is None:
                cell_ids = [-1] * (H * W)
                for (r, c), nid in cells.items():
                    cell_ids[r * W + c] = int(str(nid).lstrip("#"))
                self._cell_ids_flat = cell_ids
            seg(game, H, W, arr.reshape(-1).tolist(), cell_ids)
            return
        # 1) SEGMENT — one connected-components pass per value.
        comps = []
        for val in np.unique(arr):
            mask = (arr == val).astype(np.uint8)
            n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=4)
            for k in range(1, n):
                ys, xs = np.where(labels == k)
                cset = frozenset(zip(ys.tolist(), xs.tolist()))
                comps.append({"rvalue": float(val), "cells": cset,
                              "count": float(len(cset)),
                              "cy": float(cents[k][1]), "cx": float(cents[k][0]),
                              "minr": int(stats[k, cv2.CC_STAT_TOP]),
                              "minc": int(stats[k, cv2.CC_STAT_LEFT])})
        if not comps:
            return
        ground = max(comps, key=lambda c: c["count"])   # largest = the ground layer
        # 2) TRACK — match each component to a prior region by max cell-overlap (same value).
        prev = getattr(self, "_prev_regions", [])
        used = set(); new_prev = []
        for comp in comps:
            best = None; best_ov = 0
            for i, p in enumerate(prev):
                if i in used or p["rvalue"] != comp["rvalue"]:
                    continue
                ov = len(comp["cells"] & p["cells"])
                if ov > best_ov:
                    best_ov = ov; best = i
            matched = (best is not None
                       and 2 * best_ov >= min(comp["count"], len(prev[best]["cells"])))
            if matched:
                p = prev[best]; used.add(best); nid = p["nid"]
                if not self.s.has_node(nid):       # defensive: pruned out from under us
                    matched = False
            if matched:
                # inherit identity; refresh stats + motion in place.
                drow = comp["cy"] - p["cy"]; dcol = comp["cx"] - p["cx"]
                # CHANGED = this region responded perceptibly (moved / resized / recolored)
                # vs last frame. The agent's agency rules read this (on an acted frame) to
                # decide what responds to its actions — the eye states the fact, cognition
                # judges. Recolour (rvalue flip, no motion) and resize both count.
                changed = (drow != 0.0 or dcol != 0.0
                           or comp["count"] != p["count"] or comp["rvalue"] != p["rvalue"])
                self.inner.set_attr(nid, "rvalue", comp["rvalue"])
                self.inner.set_attr(nid, "count", comp["count"])
                self.inner.set_attr(nid, "cy", comp["cy"])
                self.inner.set_attr(nid, "cx", comp["cx"])
                self.inner.set_attr(nid, "drow", drow)
                self.inner.set_attr(nid, "dcol", dcol)
                if changed:
                    self.inner.set_attr(nid, "changed_frame", float(self.s.node(game)["attrs"].get("frame", 0)))
                if comp is ground:
                    # CONSERVE: add-only. Occluded floor cells stay within the ground;
                    # only newly-revealed cells need an edge.
                    member = set(p["cells"]) | set(comp["cells"])
                    for rc in comp["cells"] - p["cells"]:
                        self.inner.add_edge_unchecked(cells[rc], "within", nid)
                else:
                    # RE-POINT: a figure's membership follows its cells (drop lost, add gained).
                    for rc in p["cells"] - comp["cells"]:
                        if rc in cells:
                            self.inner.remove_edge(cells[rc], "within", nid)
                    for rc in comp["cells"] - p["cells"]:
                        self.inner.add_edge_unchecked(cells[rc], "within", nid)
                    member = comp["cells"]
            else:
                # BIRTH — a fresh persistent Region.
                nid = self.s.add_node("Region", {
                    "rid": float(comp["minr"] * 10000 + comp["minc"]),
                    "rvalue": comp["rvalue"], "count": comp["count"],
                    "cy": comp["cy"], "cx": comp["cx"], "drow": 0.0, "dcol": 0.0})
                self.inner.add_edge_unchecked(game, "has_region", nid)
                for rc in comp["cells"]:
                    self.inner.add_edge_unchecked(cells[rc], "within", nid)
                member = comp["cells"]
            # the ground (largest region) is the medium, not a figure — mark it so agency
            # excludes it (the floor-never-votes theorem becomes a one-attr read).
            self.inner.set_attr(nid, "is_ground", 1.0 if comp is ground else 0.0)
            new_prev.append({"nid": nid, "cells": frozenset(member),
                             "rvalue": comp["rvalue"], "count": comp["count"],
                             "cy": comp["cy"], "cx": comp["cx"]})
        # 3) DEATH — a prior region matched by no component this frame is gone.
        for i, p in enumerate(prev):
            if i not in used and self.s.has_node(p["nid"]):
                self.inner.remove_node(p["nid"])
        self._prev_regions = new_prev

    def observe(self, world_substrate) -> None:
        """Ingest a world AND remember which WorldInstances were in view, so a
        subsequent action's freshening can be attributed back to them."""
        observed = set()
        for wn in world_substrate.graph.nodes():
            if wn.type.startswith("Term."):
                continue
            wid = wn.attrs.get("id")
            if wid is None:
                continue
            observed.add((wn.type, str(wid)))
        self.ingest(world_substrate)
        # Drive VISION too when the world publishes a frame/screen (the agent isn't
        # human — it has the optic path as well as symbolic ingest). Mechanical I/O:
        # the world hands over its render + context hint, the GraphEye does the
        # graph-resident perception. Worlds without a screen pay nothing.
        screen = getattr(world_substrate, "vision_screen", None)
        frame = getattr(world_substrate, "vision_frame", None)
        photon_packets = getattr(
            world_substrate, "vision_photon_packets", None)
        if screen is not None or frame is not None or photon_packets is not None:
            self.update_vision(screen=screen, frame=frame,
                               calibration=getattr(world_substrate,
                                                   "vision_calibration", None),
                               photon_packets=photon_packets,
                               photon_dirty=getattr(
                                   world_substrate,
                                   "vision_photon_dirty", None),
                               photon_counts=getattr(
                                   world_substrate,
                                   "vision_photon_counts", None),
                               photon_epoch=getattr(
                                   world_substrate,
                                   "vision_photon_epoch", None))
        self._last_observed_wi = {self._instances[k] for k in observed if k in self._instances}

    def record_action_freshening(self, action: str, frontier_after: float,
                                 alpha: float = 0.01) -> None:
        """Attribute an action's freshening to every instance in view at the last
        observe: per-instance act_<action>_freshening_ema + act_<action>_n."""
        ema_key, n_key = f"act_{action}_freshening_ema", f"act_{action}_n"
        for wi in self._last_observed_wi:
            a = self.s.node(wi)["attrs"]
            old = float(a.get(ema_key, 0.0))
            self.inner.set_attr(wi, ema_key, alpha * float(frontier_after) + (1.0 - alpha) * old)
            self.inner.set_attr(wi, n_key, int(a.get(n_key, 0)) + 1)

    def record_action_outcome_observed(self, action: str, novelty_delta: float = 0.0,
                                        failure_delta: float = 0.0, boredom_delta: float = 0.0,
                                        frontier_after: float = 0.0, alpha: float = 0.1,
                                        instance_alpha: float = 0.01) -> None:
        self.record_action_outcome(action, novelty_delta=novelty_delta,
                                   failure_delta=failure_delta, boredom_delta=boredom_delta,
                                   frontier_after=frontier_after, alpha=alpha)
        self.record_action_freshening(action, frontier_after, alpha=instance_alpha)

    def discover_action_affinities(self, min_samples: int = 5, margin: float = 0.7) -> list:
        """Per BodyType, aggregate per-instance per-action freshening EMAs and
        promote the leader action to typical_best_action when it beats the
        runner-up by (1+margin)x and clears min_samples. Idempotent. Mechanical
        aggregation + graph-data storage."""
        by_type: dict = {}
        for wi in set(self._instances.values()):
            for bt in self.inner.neighbours(wi, "instance_of"):
                by_type.setdefault(bt, []).append(wi)
        promoted = []
        for bt, instance_ids in by_type.items():
            if len(instance_ids) < 2:
                continue
            ema_sums, ema_counts, ns = {}, {}, {}
            for wi in instance_ids:
                for k, v in self.s.node(wi)["attrs"].items():
                    if k.startswith("act_") and k.endswith("_freshening_ema"):
                        action = k[len("act_"):-len("_freshening_ema")]
                        ema_sums[action] = ema_sums.get(action, 0.0) + float(v)
                        ema_counts[action] = ema_counts.get(action, 0) + 1
                    elif k.startswith("act_") and k.endswith("_n"):
                        action = k[len("act_"):-len("_n")]
                        ns[action] = ns.get(action, 0) + int(v)
            means = {action: ema_sums.get(action, 0.0) / ema_counts[action]
                     for action, n in ns.items()
                     if n >= min_samples and ema_counts.get(action, 0) > 0}
            if len(means) < 2:
                continue
            ranked = sorted(means.items(), key=lambda kv: -kv[1])
            leader, leader_mean = ranked[0]
            runner_up_mean = ranked[1][1]
            if leader_mean <= 0:
                continue
            if runner_up_mean > 0 and leader_mean < (1.0 + margin) * runner_up_mean:
                continue
            bt_attrs = self.s.node(bt)["attrs"]
            if bt_attrs.get("typical_best_action") != leader:
                self.inner.set_attr(bt, "typical_best_action", leader)
                self.inner.set_attr(bt, "typical_best_action_mean_freshening", leader_mean)
                promoted.append((bt_attrs.get("name"), leader, leader_mean))
        return promoted

    # --- history as graph data + scalar Lit policies -------------------------

    def _ensure_body_type(self, type_name: str):
        bt = self._body_types.get(type_name)
        if bt is None:
            bt = self.s.add_node("BodyType", {"name": type_name})
            self._body_types[type_name] = bt
        return bt

    def log_event(self, kind: str, types=()):
        """Stamp ONE Event node: agent --logged--> Event --involves--> BodyType(s),
        with a monotone timestamp. History lives in the graph, not a Python list.
        Also updates the discovery co-occurrence counters via record_activity."""
        types = tuple(types)
        self._event_clock += 1
        ev = self.s.add_node("Event", {"kind": kind, "timestamp": self._event_clock})
        self.inner.add_edge_unchecked(self.agent, "logged", ev)
        for t in types:
            self.inner.add_edge_unchecked(ev, "involves", self._ensure_body_type(t))
        self.record_activity(kind, types)
        return ev

    @property
    def _event_log(self) -> list:
        out = []
        for ev in self.inner.neighbours(self.agent, "logged"):
            a = self.s.node(ev)["attrs"]
            body_types = sorted(self.s.node(bt)["attrs"]["name"]
                                for bt in self.inner.neighbours(ev, "involves"))
            out.append({"kind": a["kind"], "body_types": tuple(body_types),
                        "timestamp": a["timestamp"]})
        out.sort(key=lambda e: e["timestamp"])
        return out

    def events(self) -> list:
        return list(self.inner.neighbours(self.agent, "logged"))

    def _seed_scalar_policies(self, policies: dict) -> None:
        """Attach each scalar policy as a Term.Lit node to the agent by a named
        edge (graph data, editable in place)."""
        for edge_name, value in policies.items():
            if self.inner.neighbours(self.agent, edge_name):
                continue
            lit = self.inner.add_term_subgraph({"type": "Lit", "value": value})
            self.inner.add_edge_unchecked(self.agent, edge_name, lit)
            self._policy_lits[edge_name] = lit

    def policy_lit(self, edge_name: str):
        ns = self.inner.neighbours(self.agent, edge_name)
        return ns[0] if ns else None

    def get_scalar_policy(self, edge_name: str, default=None):
        """Read a scalar policy off its agent-attached Term.Lit node (graph data)."""
        lit = self.policy_lit(edge_name)
        if lit is None:
            return default
        n = self.s.node(lit)
        if n["type"] != "Term.Lit":
            return default
        return n["attrs"].get("value", default)

    def set_scalar_policy(self, edge_name: str, value) -> None:
        lit = self.policy_lit(edge_name)
        if lit is not None and self.s.node(lit)["type"] == "Term.Lit":
            self.inner.set_attr(lit, "value", value)
            return
        new_lit = self.inner.add_term_subgraph({"type": "Lit", "value": value})
        self.inner.add_edge_unchecked(self.agent, edge_name, new_lit)

    # --- the live loop: mechanical orchestration of seeded faculties ---------

    def live(self, world, n_games: int = 1, max_plies: int = 40) -> None:
        """Run the curiosity loop over a world (dict of callables: reset /
        legal_actions / apply_action / interpret_acts_on, optional preview_safe).
        Pure ORCHESTRATION — no decisions here: each ply chooses via the SEEDED
        `action_score_term` (`choose_action_meta_curious`), registers the
        body-types it acts on, logs the activity, steps the world, re-observes;
        after the games, runs salience discovery. The reasoning is the seeds;
        the adapter only sequences the world's callables and the seeded choice.

        This is the graph-native analogue of `CuriousAgent.live` MINUS the
        dynamic-grammar growth (`grow_representation` / `gamma_dynamic`), which
        is genuine Γ-extension reasoning, not orchestration, and is not modelled
        here."""
        acts_on = world.get("interpret_acts_on", lambda *a: [])
        preview_safe = world.get("preview_safe", True)
        for _ in range(n_games):
            substrate, ctx = world["reset"]()
            self.observe(substrate)
            for _ in range(max_plies):
                actions = world["legal_actions"](substrate, ctx)
                if not actions:
                    break
                # capture loop vars for the closures (avoid late-binding)
                cur_s, cur_c = substrate, ctx
                touches_fn = lambda a, s=cur_s, c=cur_c: acts_on(s, c, a)
                if preview_safe:
                    preview_fn = lambda a, s=cur_s, c=cur_c: world["apply_action"](s, c, a)[0]
                    action = self.choose_action_meta_curious(actions, preview_fn, touches_fn)
                else:
                    action = self.choose_action_meta_curious(actions, lambda a: None, touches_fn)
                touched = list(touches_fn(action))
                for t in touched:
                    self.register_relation(t, "acts_on")
                self.record_activity("act", touched)
                gate = self._authorize_world_action(world, substrate, ctx, action)
                if gate["decision"] != "commit" or not gate["authorized"]:
                    self.cognitive_tick()
                    continue
                substrate, ctx = world["apply_action"](substrate, ctx, action)
                self.observe(substrate)
        self.discover_relations()

    # --- current-goal pointer (single "wants" edge) --------------------------

    def set_goal(self, wi, priority: float = 1.0) -> None:
        """Set (or clear, if `wi` is None) the agent's current goal: a single
        `wants` edge to a WorldInstance with a priority. Replaces any prior
        goal. Mechanical pointer-setting — recording a chosen goal, not deciding
        which (that's the seeded goal-pressure faculty)."""
        for tgt in list(self.inner.neighbours(self.agent, "wants")):
            self.inner.remove_edge(self.agent, "wants", tgt)
        self.current_goal_wi = wi
        if wi is not None:
            try:
                self.inner.add_edge_unchecked(self.agent, "wants", wi, {"priority": priority})
            except TypeError:
                self.inner.add_edge_unchecked(self.agent, "wants", wi)

    # --- concurrent goals + adhd priority modulation + goal choice ------------

    def _wants_priorities(self) -> dict:
        """(WorldInstance -> RAW priority) for every `wants` edge off the agent,
        read straight from the graph. Pure query."""
        prio_by_index = {}
        for e in self.inner.graph_to_dict()["edges"]:
            if e["type"] == "wants":
                prio_by_index[e["tgt"]] = float(e.get("attrs", {}).get("priority", 1.0))
        out = {}
        for nid in self.inner.neighbours(self.agent, "wants"):
            out[nid] = prio_by_index.get(int(str(nid).lstrip("#")), 1.0)
        return out

    def add_goal(self, wi, priority: float = 1.0) -> None:
        """Add `wi` as a goal (one `wants` edge per goal, each with priority);
        update priority if already a goal. Mechanical bookkeeping."""
        for tgt in list(self.inner.neighbours(self.agent, "wants")):
            if tgt == wi:
                self.inner.remove_edge(self.agent, "wants", tgt)
        try:
            self.inner.add_edge_unchecked(self.agent, "wants", wi, {"priority": priority})
        except TypeError:
            self.inner.add_edge_unchecked(self.agent, "wants", wi)
        self.current_goal_wi = wi

    # adhd priority modulation as graph-resident decision data: the transformed
    # priority of a goal at intensity i is  raw*(1-i) + extreme*i,  where the
    # extreme is the bimodal snap (>=1 -> 2.0 fixation, else 0.05 ignored). The
    # IfThenElse snap + the interpolation are the DECISION, expressed as a Term
    # the Rust DSL evaluates; the adapter only supplies the raw priority + the
    # intensity policy (two scalars).
    _ADHD_PRIORITY_TERM = {
        "type": "Plus", "items": [
            {"type": "Times", "items": [
                {"type": "Var", "name": "raw"},
                {"type": "Minus", "a": {"type": "Lit", "value": 1.0},
                 "b": {"type": "Var", "name": "intensity"}}]},
            {"type": "Times", "items": [
                {"type": "IfThenElse",
                 "cond": {"type": "Gte", "a": {"type": "Var", "name": "raw"},
                          "b": {"type": "Lit", "value": 1.0}},
                 "then": {"type": "Lit", "value": 2.0},
                 "other": {"type": "Lit", "value": 0.05}},
                {"type": "Var", "name": "intensity"}]}]}

    def get_goals(self) -> list:
        """The agent's goals as (WorldInstance, priority) pairs — priorities run
        through the seeded adhd modulation Term (intensity from the scalar
        policy; intensity 0 passes raw through exactly)."""
        intensity = float(self.get_scalar_policy("adhd_intensity", 0.0))
        out = []
        for wi, raw in self._wants_priorities().items():
            p = self.inner.evaluate(self._ADHD_PRIORITY_TERM,
                                    {"raw": raw, "intensity": intensity})
            out.append((wi, float(p)))
        return out

    def remove_goal(self, wi) -> None:
        """Drop `wi` from the agent's goals. Mechanical."""
        for tgt in list(self.inner.neighbours(self.agent, "wants")):
            if tgt == wi:
                self.inner.remove_edge(self.agent, "wants", tgt)
        if self.current_goal_wi == wi:
            remaining = list(self.inner.neighbours(self.agent, "wants"))
            self.current_goal_wi = remaining[0] if remaining else None

    def bfs_distances_to_goal(self, goal_wi, horizon: int) -> dict:
        """Reverse BFS from `goal_wi` over the mirrored instance edges:
        {instance -> hops to goal} within `horizon`. Pure traversal."""
        ets = self._mirrored_edge_types
        if not ets:
            return {}
        from collections import deque
        dists = {goal_wi: 0}
        q = deque([(goal_wi, 0)])
        while q:
            cur, d = q.popleft()
            if d >= horizon:
                continue
            for et in ets:
                for pred in self.inner.in_neighbours(cur, et):
                    if pred not in dists:
                        dists[pred] = d + 1
                        q.append((pred, d + 1))
        return dists

    def plan_to_goal(self, locus_wi, goal_wi, horizon: int):
        """First-hop instance from `locus_wi` toward `goal_wi` (BFS), or the goal
        if adjacent, or None if unreachable within `horizon`. Pure traversal."""
        if locus_wi == goal_wi:
            return None
        ets = self._mirrored_edge_types
        if not ets:
            return None
        from collections import deque
        seen = {locus_wi}
        q = deque()
        for et in ets:
            for nbr in self.inner.neighbours(locus_wi, et):
                if nbr in seen:
                    continue
                seen.add(nbr)
                if nbr == goal_wi:
                    return nbr
                q.append((nbr, nbr, 1))
        while q:
            cur, first_hop, depth = q.popleft()
            if depth >= horizon:
                continue
            for et in ets:
                for nbr in self.inner.neighbours(cur, et):
                    if nbr in seen:
                        continue
                    seen.add(nbr)
                    if nbr == goal_wi:
                        return first_hop
                    q.append((nbr, first_hop, depth + 1))
        return None

    # --- passability-aware spatial routing (routes AROUND learned walls) ------
    #
    # bfs_distances_to_goal / plan_to_goal above are wall-BLIND. For grid worlds
    # (ARC) the agent learns impassable Boundaries and must route around them.
    # The routing DECISION is graph-resident Terms (domains/spatial_routing.py):
    # relax_step_term (the monotone Bellman step) and passable_hop_term (the hop
    # Argmax). The fixpoint ITERATION is the native relax_to_fixpoint primitive
    # (Rust). The adapter does ONLY mechanical I/O: stamp the _dist register,
    # fire the Rust driver, evaluate the hop Term. No Python loop, no Python
    # decision — neither the iteration nor the choice lives here.

    def _routing_terms(self):
        """The (relax-step JSON, hop JSON) graph-resident routing Terms, authored
        once from the spatial_routing builders and cached. Both are graph data;
        Rust evaluates them."""
        if getattr(self, "_relax_json", None) is None:
            from domains.spatial_routing import (relax_step_term,
                                                 passable_hop_term)
            from substrate.jsonio import term_to_json
            self._relax_json = term_to_json(relax_step_term())
            self._hop_json = term_to_json(passable_hop_term())
        return self._relax_json, self._hop_json

    def passable_distances_to(self, goal_wi, horizon: int = 0, cells=None) -> dict:
        """{cell_wi: distance_to_goal} over PASSABLE adjacency only — cells walled
        off from the goal stay UNREACHABLE and are dropped (the not-present =>
        unreachable contract). Mechanical: stamp each cell's _dist register
        (goal 0, else UNREACHABLE), run the native relax_to_fixpoint driver (the
        Rust iteration of the graph-resident relax Term), read the registers
        back, restore the scratch. `cells` defaults to every SpatialLocation
        WorldInstance."""
        from domains.spatial_routing import UNREACHABLE
        relax_json, _ = self._routing_terms()
        if cells is None:
            cells = [n for n in self.s.nodes("WorldInstance")
                     if self.s.node(n)["attrs"].get("world_type")
                     == "SpatialLocation"]
        cells = list(cells)
        if goal_wi not in cells:
            cells.append(goal_wi)
        saved = {c: self.s.node(c)["attrs"].get("_dist") for c in cells}
        for c in cells:
            self.inner.set_attr(c, "_dist", 0.0 if c == goal_wi else UNREACHABLE)
        cell_ids = [int(str(c).lstrip("#")) for c in cells]
        self.inner.relax_to_fixpoint(relax_json, cell_ids, "_dist", horizon)
        dists = {c: self.s.node(c)["attrs"]["_dist"] for c in cells
                 if self.s.node(c)["attrs"]["_dist"] < UNREACHABLE}
        for c, old in saved.items():
            self.inner.set_attr(c, "_dist",
                                UNREACHABLE if old is None else old)
        return dists

    def plan_passable_step(self, locus_wi, goal_wi, horizon: int = 0):
        """First-hop cell from `locus_wi` toward `goal_wi` that descends the
        passability-aware distance gradient — the adjacent cell one step closer
        along a route that does NOT cross a known wall. None if locus IS the
        goal or is walled off from it. The relaxation (Rust primitive) fills
        _dist; the hop CHOICE is the graph-resident Argmax Term evaluated in
        Rust. The adapter only stamps the register, fires the driver, evaluates
        the Term, and gates on reachability."""
        from domains.spatial_routing import UNREACHABLE
        if locus_wi == goal_wi:
            return None
        relax_json, hop_json = self._routing_terms()
        cells = [n for n in self.s.nodes("WorldInstance")
                 if self.s.node(n)["attrs"].get("world_type") == "SpatialLocation"]
        if goal_wi not in cells:
            cells.append(goal_wi)
        saved = {c: self.s.node(c)["attrs"].get("_dist") for c in cells}
        for c in cells:
            self.inner.set_attr(c, "_dist", 0.0 if c == goal_wi else UNREACHABLE)
        self.inner.relax_to_fixpoint(
            relax_json, [int(str(c).lstrip("#")) for c in cells], "_dist", horizon)
        here = self.s.node(locus_wi)["attrs"].get("_dist", UNREACHABLE)
        hop = None
        if here is not None and float(here) < UNREACHABLE:
            hop = self.inner.evaluate(hop_json, {"cell": locus_wi})
        for c, old in saved.items():
            self.inner.set_attr(c, "_dist",
                                UNREACHABLE if old is None else old)
        return hop

    # goal choice: nearest-unsaturated, else most-salient — a seeded Argmax. The
    # adapter does the BFS + stamps each reachable instance with dist / saturated
    # (the SEEDED saturation predicate) / salience; the seeded scoring Term ranks
    # them (unsaturated -> 1e6 - dist, so nearest wins; all-saturated -> salience).
    _GOAL_CHOICE_TERM = {
        "type": "IfThenElse",
        "cond": {"type": "Eq", "a": {"type": "Attr", "node": {"type": "Var", "name": "c"},
                                     "key": "saturated"}, "b": {"type": "Lit", "value": 0}},
        "then": {"type": "Minus", "a": {"type": "Lit", "value": 1000000.0},
                 "b": {"type": "Attr", "node": {"type": "Var", "name": "c"}, "key": "dist"}},
        "other": {"type": "Attr", "node": {"type": "Var", "name": "c"}, "key": "salience"}}

    def pick_goal(self, horizon: int = 10):
        """Choose a goal instance: the nearest reachable UNSATURATED instance,
        else the most-salient (longest out of mind). The adapter does the forward
        BFS + stamps candidates; the seeded _GOAL_CHOICE_TERM (Argmax) decides."""
        locus = self.current_locus_wi
        if locus is None:
            return None
        from collections import deque
        ets = self._mirrored_edge_types
        dists = {locus: 0}
        q = deque([(locus, 0)])
        while q:
            cur, d = q.popleft()
            if d >= horizon:
                continue
            for et in ets:
                for nbr in self.inner.neighbours(cur, et):
                    if nbr not in dists:
                        dists[nbr] = d + 1
                        q.append((nbr, d + 1))
        cands = [wi for wi in dists if wi != locus]
        if not cands:
            return None
        for c in list(self.s.nodes()):
            if self.s.node(c)["type"] == "GoalCandidate":
                self.inner.remove_node(c)
        by_node = {}
        for wi in cands:
            sat = 1 if self.is_instance_saturated(wi) else 0
            lot = float(self.s.node(wi)["attrs"].get("last_observed_tick", 0) or 0)
            gc = self.s.add_node("GoalCandidate",
                                 {"dist": float(dists[wi]), "saturated": sat,
                                  "salience": -lot})
            by_node[gc] = wi
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "GoalCandidate"},
                  "var_name": "c", "value": self._GOAL_CHOICE_TERM}
        picked = self.inner.evaluate(choose, {})
        return by_node.get(picked)

    # --- autonomous inquiry: ask about words you can't ground ----------------
    #
    # When per-word grounding fails (no teacher payload), the gap becomes an
    # inquire CommunicativeGoal — a graph node, so it round-trips through
    # save/load (unlike a Python queue). compose_inquiry surfaces ONE pending
    # gap per turn as an ask-meaning Term and marks it asked; the same gap is
    # never asked twice. WHICH gap to surface (most recent first — what the
    # user just said gets priority) is the seeded Argmax below, not a Python
    # comparison.

    # Recency is the choice value: the highest created_seq (newest) wins.
    _INQUIRY_CHOICE_TERM = {
        "type": "Attr", "node": {"type": "Var", "name": "c"}, "key": "created_seq"}

    def _inquire_goals(self) -> list:
        """Every inquire CommunicativeGoal node (graph query)."""
        return [n for n in self.s.nodes("CommunicativeGoal")
                if self.s.node(n)["attrs"].get("communicate_kind") == "inquire"]

    # --- communicative action: speak to satisfy an inform goal ----------------
    #
    # An `inform` goal wants the addressee to believe a meaning. The agent speaks
    # the meaning (rendered via the lexicon), models the addressee's uptake
    # (their believed_concepts grow), and falls silent once every goal is met.
    # No addressee -> silent. The meaning is graph data on the goal; the
    # rendering is the graph render engine; the belief update is mechanical.

    _UTTER = ("__utter__",)

    def set_addressee(self, other):
        """Point the agent at the entity it's speaking to (the addressee edge).
        Mechanical."""
        for e in list(self.inner.neighbours(self.agent, "addressee")):
            self.inner.remove_edge(self.agent, "addressee", e)
        self.inner.add_edge_unchecked(self.agent, "addressee", other)

    def _addressee(self):
        return next(iter(self.inner.neighbours(self.agent, "addressee")), None)

    def _meaning_concepts(self, meaning) -> set:
        """The grounded concepts a meaning mentions (a bare concept name, or a
        predicate-argument dict; numbers/bools carry none)."""
        if isinstance(meaning, bool) or isinstance(meaning, (int, float)):
            return set()
        if isinstance(meaning, str):
            return {meaning}
        out: set = set()
        for k, v in meaning.items():
            if k == "force":
                continue
            out.add(k)
            if isinstance(v, dict):
                for child in v.values():
                    out |= self._meaning_concepts(child)
            else:
                out |= self._meaning_concepts(v)
        return out

    def add_communicative_goal(self, meaning, kind: str = "inform",
                               priority: float = 1.0):
        """A communicative goal: the agent intends the addressee to believe
        (`inform`) the `meaning`. Graph-resident — a CommunicativeGoal node
        carrying the meaning as JSON (so structured meanings round-trip)."""
        import json
        gid = self.s.add_node("CommunicativeGoal", {
            "communicate_kind": kind, "meaning_json": json.dumps(meaning),
            "priority": float(priority)})
        self.inner.add_edge_unchecked(self.agent, "has_goal", gid)
        return gid

    def _inform_goals(self) -> list:
        return [n for n in self.s.nodes("CommunicativeGoal")
                if self.s.node(n)["attrs"].get("communicate_kind") == "inform"]

    def _goal_meaning(self, gid):
        import json
        raw = self.s.node(gid)["attrs"].get("meaning_json")
        return json.loads(raw) if raw is not None else None

    def _believed(self, ad):
        return set(self.s.node(ad)["attrs"].get("believed_concepts") or [])

    def _grow_believed_concepts(self, ad, concepts):
        """TOLD-STATUS write (Wave: interlocutor-as-modeled-participant, task 1):
        mechanically grow addressee `ad`'s `believed_concepts` with `concepts`
        (a set union, graph-resident and per-party — `ad` is the specific
        Interlocutor/Agent node the turn addressed, so a second party never
        inherits what THIS one was told). Shared by `_communicative_action`
        (structured CommunicativeGoal meanings) and `_finish_turn_reply` (a
        substantive reply's own rendered content), so both paths write the
        SAME contract instead of two divergent ones. No-op on an empty
        concept set or a missing addressee."""
        if ad is None or not concepts:
            return set(self._believed(ad)) if ad is not None else set()
        believed = self._believed(ad) | set(concepts)
        self.inner.set_attr(ad, "believed_concepts", frozenset(believed))
        return believed

    def _communicative_action(self):
        """Speak AS goal-directed action: for each UNMET inform goal (the
        addressee doesn't yet believe every concept it mentions), render the
        meaning to an utterance via the lexicon, model the addressee's uptake
        (grow its believed_concepts), and return the utterance strings. Silent
        (None) if nothing is unmet or there's no addressee."""
        ad = self._addressee()
        if ad is None:
            return None
        believed = self._believed(ad)
        spoken = []
        told: set = set()
        for g in self._inform_goals():
            meaning = self._goal_meaning(g)
            concepts = self._meaning_concepts(meaning)
            if concepts <= believed:
                continue                       # addressee already believes it
            spoken.append(self.utterance_for(meaning))
            believed |= concepts
            told |= concepts
        self._grow_believed_concepts(ad, told)
        return spoken or None

    def _utterance_pending(self) -> bool:
        """Is there an unmet inform goal the agent could speak to an addressee?
        (Read-only — does NOT model uptake.)"""
        ad = self._addressee()
        if ad is None:
            return False
        believed = self._believed(ad)
        return any(not (self._meaning_concepts(self._goal_meaning(g)) <= believed)
                   for g in self._inform_goals())

    def choose_action_or_utter(self, legal_actions, preview_fn=None):
        """The unified action choice: SPEAK (`_UTTER`) when an inform goal is
        unmet for the addressee — communicative pressure no world action can
        relieve — else pick a world action by the seeded curiosity score. With
        nothing to say, the autopoietic action loop is unchanged."""
        if self._utterance_pending():
            return self._UTTER
        if preview_fn is not None:
            return self.choose_action(legal_actions, preview_fn)
        return legal_actions[0] if legal_actions else None

    def _has_inquire_goal_for(self, form: str) -> bool:
        """Is there already an inquire goal for `form`? (dedupe, asked or not)."""
        return any(self.s.node(n)["attrs"].get("inquires_about_form") == form
                   for n in self._inquire_goals())

    def _queue_inquiry(self, form: str):
        """Create an inquire communicate goal for an ungrounded form — a graph
        node, deduped per form (asked or pending). Mechanical: the fixed faculty
        policy is 'ask about what you couldn't ground'; the goal is data."""
        try:
            if self.word_meaning(form) is not None:
                return                        # already grounded since the miss
        except Exception:
            pass
        if self._has_inquire_goal_for(form):
            return
        seq = max([int(self.s.node(n)["attrs"].get("created_seq", -1))
                   for n in self._inquire_goals()] + [-1]) + 1
        gid = self.s.add_node("CommunicativeGoal",
                              {"communicate_kind": "inquire",
                               "inquires_about_form": form,
                               "asked": 0, "created_seq": seq, "priority": 1.0})
        self.inner.add_edge_unchecked(self.agent, "has_goal", gid)
        return gid

    def _know_verb(self) -> str:
        """The concept the agent uses to express 'I don't know X' — the grounded
        'know' sign's concept if present, else a plain marker."""
        for n in self.s.nodes("Sign"):
            if self.s.node(n)["attrs"].get("form") == "know":
                return self.s.node(n)["attrs"].get("concept") or "unknown_word"
        return "unknown_word"

    def _inquiry_meaning(self, form: str) -> dict:
        """Build the ask-meaning Term for an inquire goal: force=ask, the unknown
        form riding the 'of' slot of the know-concept. Reconstructed from the
        goal's attr, so it survives save/load with no stored subgraph."""
        return {"force": "ask", self._know_verb(): {"of": form}}

    @staticmethod
    def _inquiry_form_from_meaning(meaning):
        """Pluck the form an inquire meaning asks about (its 'of' slot)."""
        for k, v in (meaning or {}).items():
            if k == "force":
                continue
            if isinstance(v, dict) and "of" in v:
                return v["of"]
        return None

    def compose_inquiry(self):
        """Surface the most-recent un-asked inquire goal as an ask-meaning Term
        and mark it asked (one per turn; never re-asked). None when nothing is
        pending. The adapter stamps the un-asked candidates; the seeded
        _INQUIRY_CHOICE_TERM (Argmax on recency) picks which to ask."""
        pending = [g for g in self._inquire_goals()
                   if not int(self.s.node(g)["attrs"].get("asked", 0))]
        if not pending:
            return None
        for c in [n for n in self.s.nodes("InquireCandidate")]:
            self.inner.remove_node(c)
        by_node = {}
        for g in pending:
            seq = float(self.s.node(g)["attrs"].get("created_seq", 0))
            ic = self.s.add_node("InquireCandidate", {"created_seq": seq})
            by_node[ic] = g
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType",
                             "node_type": "InquireCandidate"},
                  "var_name": "c", "value": self._INQUIRY_CHOICE_TERM}
        picked_ic = self.inner.evaluate(choose, {})
        goal = by_node.get(picked_ic)
        for ic in list(by_node):
            self.inner.remove_node(ic)
        if goal is None:
            return None
        form = self.s.node(goal)["attrs"].get("inquires_about_form")
        self.inner.set_attr(goal, "asked", 1)
        return self._inquiry_meaning(form)

    # --- communicative INITIATIVE: volunteer relevant known knowledge ---------

    _CONTRIBUTION_CHOICE_TERM = {
        "type": "Attr", "node": {"type": "Var", "name": "c"}, "key": "relevance"}

    def compose_contribution(self, text):
        """INITIATIVE (Grice-relation + given/new): when the interlocutor's turn touches a topic
        the agent KNOWS something about (a taught meaning it holds) and hasn't shared yet,
        volunteer the most-relevant such fact — the mirror of compose_inquiry, but for KNOWNS
        instead of unknowns. The adapter stamps ContributionCandidate nodes; the seeded
        _CONTRIBUTION_CHOICE_TERM (Argmax on relevance = topicality) picks which to offer; it is
        marked shared so it is never volunteered twice. Returns (form, fact) or None.

        Using held knowledge to contribute, not just react — what a human does."""
        import re
        shared = self.__dict__.setdefault("_shared_contributions", set())
        known = {s.get("form") for s in self.taught_signs()}
        caps = self.taught_capabilities()
        fns = set(self._FUNCTION_WORDS)
        cand, seen = [], set()
        toks = [w for w in re.findall(r"[A-Za-z][A-Za-z_]*", text.lower())
                if len(w) >= 3 and w not in fns]
        cues = self._CASUAL_CUES | self._FORMAL_CUES   # register markers aren't content to offer
        for i, w in enumerate(toks):
            if w in seen or w in shared or w not in known or w in cues:
                continue
            seen.add(w)
            if self.interlocutor_knows(w):       # given/new: don't tell them what they know
                continue
            concept = "taught_" + w
            if concept not in caps:
                continue
            try:
                fact = caps[concept](None)
            except Exception:
                fact = None
            if fact:
                cand.append((w, fact, 1.0 / (1 + i)))   # earlier mention = more topical
        if not cand:
            return None
        for n in [n for n in self.s.nodes("ContributionCandidate")]:
            self.inner.remove_node(n)
        by = {}
        for (w, fact, rel) in cand:
            nid = self.s.add_node("ContributionCandidate", {"relevance": float(rel), "form": w})
            by[nid] = (w, fact)
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "ContributionCandidate"},
                  "var_name": "c", "value": self._CONTRIBUTION_CHOICE_TERM}
        picked = self.inner.evaluate(choose, {})
        chosen = by.get(picked)
        for nid in list(by):
            self.inner.remove_node(nid)
        if not chosen:
            return None
        shared.add(chosen[0])
        self.note_interlocutor_knows(chosen[0])    # having told them, they now know it (given/new)
        return chosen

    # --- model of the INTERLOCUTOR's knowledge (theory of mind / given-new) ----

    def note_interlocutor_knows(self, form):
        """Record that the interlocutor knows about `form` — they demonstrated it (asserted /
        defined / answered) or the agent has now told them. A graph edge on the Interlocutor node
        (the agent's model of the other mind). Mechanical ingest."""
        spk = self._interlocutor()
        try:
            self.s.add_production({"src": {"type": "Interlocutor", "var": "a"},
                                   "edge_type": "knows", "tgt": {"type": "Concept", "var": "b"},
                                   "where": None, "weight": {"type": "Lit", "value": 1.0},
                                   "provenance": "interlocutor_model:knows"})
        except Exception:
            pass
        c = self._ensure_concept(str(form).lower())
        if c not in set(self.inner.neighbours(spk, "knows")):
            self.inner.add_edge_unchecked(spk, "knows", c)
        return c

    def interlocutor_knows(self, form):
        """Does the agent believe the interlocutor already knows about `form`? (given vs new)."""
        spk = self._interlocutor()
        names = {self.s.node(n)["attrs"].get("name")
                 for n in self.inner.neighbours(spk, "knows")}
        return str(form).lower() in names

    def interlocutor_knowledge(self):
        """The forms the agent believes the interlocutor knows (its model of the other mind)."""
        spk = self._interlocutor()
        return sorted(self.s.node(n)["attrs"].get("name")
                      for n in self.inner.neighbours(spk, "knows"))

    def note_stated_knowledge(self, text):
        """Boundary I/O: if the interlocutor ASSERTS a definition ('(a) X is/are a Y'), they know
        X — record it on the interlocutor model so the agent won't redundantly tell them. The
        smallest graph token from the utterance; the DECISION to suppress lives in the gate."""
        import re
        m = re.match(r"\s*(?:a |an |the )?([a-z][a-z']{2,})\s+(?:is|are)\s+(?:a |an |the )",
                     str(text).strip().lower())
        if m:
            self.note_interlocutor_knows(m.group(1))
            return m.group(1)
        return None

    # --- REGISTER / pragmatic shaping (match the interlocutor; hedge face-threats) ---

    _CASUAL_CUES = frozenset(["hey", "hi", "yeah", "yep", "nah", "gonna", "wanna", "cool",
                              "thanks", "thx", "ok", "okay", "sup", "dunno", "kinda", "gimme"])
    _FORMAL_CUES = frozenset(["hello", "greetings", "please", "could", "would", "may", "pardon",
                              "kindly", "thank", "good", "evening", "morning", "afternoon",
                              "indeed", "certainly", "regards"])
    # (speech_act, register) -> surface; {word} is filled for the inquire act.
    # The agent's register LEXICON (data, not per-reply prose): every social act
    # that could otherwise leak its bare NAME as the reply text gets a register-
    # matched surface here, so the emit ladder always has a proper surface.
    _REGISTER_SURFACES = [
        ("greeting", "casual", "hey!"), ("greeting", "neutral", "hello"),
        ("greeting", "formal", "good day"),
        ("acknowledgment", "casual", "got it"), ("acknowledgment", "neutral", "noted"),
        ("acknowledgment", "formal", "understood"),
        # a bare `statement` reply is an acknowledgment of what was said.
        ("statement", "casual", "got it"), ("statement", "neutral", "noted"),
        ("statement", "formal", "understood"),
        # a received answer / backchannel is acknowledged, not echoed by name.
        ("answer", "casual", "got it"), ("answer", "neutral", "noted"),
        ("answer", "formal", "understood"),
        ("backchannel", "casual", "mm-hm"), ("backchannel", "neutral", "I see"),
        ("backchannel", "formal", "indeed"),
        ("thanks", "casual", "no worries"), ("thanks", "neutral", "you're welcome"),
        ("thanks", "formal", "much obliged"),
        ("farewell", "casual", "bye"), ("farewell", "neutral", "goodbye"),
        ("farewell", "formal", "farewell"),
        ("closing", "casual", "bye"), ("closing", "neutral", "goodbye"),
        ("closing", "formal", "farewell"),
        ("inquire_unknown", "casual", "what's '{word}'?"),
        ("inquire_unknown", "neutral", "I don't know '{word}' — what does it mean?"),
        ("inquire_unknown", "formal",
         "I'm not familiar with '{word}'; might I ask what it means?"),
    ]

    def install_register_lexicon(self):
        """Mint the register-variant surfaces as graph data (idempotent). The DECISION (which
        register) is read off the interlocutor model; this is the surface inventory it chooses
        from — the agent's own register lexicon."""
        if any(self.s.nodes("RegisterSurface")):
            return
        for act, reg, surface in self._REGISTER_SURFACES:
            self.s.add_node("RegisterSurface",
                            {"speech_act": act, "register": reg, "surface": surface})

    def note_register(self, text):
        """Read the interlocutor's register from surface cues and accumulate it on the model
        (Interlocutor node). Boundary I/O -> a graph attr the agent's output then matches."""
        import re
        toks = set(re.findall(r"[a-z']+", str(text).lower()))
        spk = self._interlocutor()
        a = self.s.node(spk)["attrs"]
        cas = float(a.get("casual_cues", 0.0)) + len(toks & self._CASUAL_CUES)
        frm = float(a.get("formal_cues", 0.0)) + len(toks & self._FORMAL_CUES)
        self.inner.set_attr(spk, "casual_cues", cas)
        self.inner.set_attr(spk, "formal_cues", frm)
        reg = "casual" if cas > frm else "formal" if frm > cas else "neutral"
        self.inner.set_attr(spk, "register", reg)
        return reg

    def register(self):
        """The register the agent believes the interlocutor is using (its model)."""
        return self.s.node(self._interlocutor())["attrs"].get("register", "neutral")

    def surface_for(self, speech_act, word=None, persona=None):
        """Render a speech act in a register/persona: pick the RegisterSurface matching
        (speech_act, persona), falling back to neutral. `persona` defaults to the interlocutor's
        detected register; pass it explicitly to express in a LEARNED persona. The variant
        inventory is graph data (grown by example / mined from TVTropes). Returns the surface."""
        self.install_register_lexicon()
        reg = persona or self.register()
        cands = [self.s.node(n)["attrs"] for n in self.s.nodes("RegisterSurface")
                 if self.s.node(n)["attrs"].get("speech_act") == speech_act]
        if not cands:
            return None
        pick = (next((c for c in cands if c.get("register") == reg), None)
                or next((c for c in cands if c.get("register") == "neutral"), None)
                or cands[0])
        s = pick.get("surface", "")
        return s.replace("{word}", word) if word is not None else s

    # --- LEARN to express in registers / personas (by example + from corpora) ----

    def learn_persona_by_example(self, persona, mapping):
        """Learn a persona's surfaces BY EXAMPLE: ground a RegisterSurface per (speech_act ->
        surface) the demonstrator gives. The agent can then express in `persona`. Idempotent."""
        self.install_register_lexicon()
        existing = {(self.s.node(n)["attrs"].get("speech_act"),
                     self.s.node(n)["attrs"].get("register"))
                    for n in self.s.nodes("RegisterSurface")}
        for act, surface in mapping.items():
            if (act, persona) not in existing:
                self.s.add_node("RegisterSurface",
                                {"speech_act": act, "register": persona, "surface": surface})
        return persona

    @staticmethod
    def _mine_persona(text):
        """Mine a persona's VOICE from self-demonstrating text (a TVTropes definition written in
        character, or a Wikipedia passage): the opening interjection = a greeting; distinctive
        words (repeated letters / elisions / frequent) = flavor markers; a vocative = the tag."""
        import re
        from collections import Counter
        t = str(text or "")
        gm = re.match(r"\s*([A-Z][^.!?]{0,28}!)", t)
        greeting = gm.group(1).strip() if gm else None
        words = re.findall(r"[A-Za-z][A-Za-z']+", t.lower())
        funcs = set(WorldAdapter._FUNCTION_WORDS)
        distinctive = [w for w in dict.fromkeys(words)
                       if re.search(r"(.)\1\1", w) or w.endswith("in'") or "'" in w]
        freq = [w for w, _ in Counter(w for w in words if w not in funcs and len(w) >= 3)
                .most_common(8)]
        markers = list(dict.fromkeys(distinctive + freq))[:6]
        tag = next((v for v in ("matey", "mate", "dude", "man", "sir", "pal", "bro", "darling")
                    if v in words), None)
        if not tag:  # else a characteristic word: no contraction, not a bare pronoun
            tag = next((w for w in markers if "'" not in w and len(w) >= 3
                        and w not in ("you", "that", "this", "they", "what", "her", "his")), None)
        return greeting, tag, markers

    def _set_persona_style(self, persona, tag, markers):
        for n in self.s.nodes("PersonaStyle"):
            if self.s.node(n)["attrs"].get("persona") == persona:
                self.inner.remove_node(n)
        self.s.add_node("PersonaStyle", {"persona": persona, "tag": tag or "",
                                         "markers": ",".join(markers or [])})

    def persona_tag(self, persona):
        for n in self.s.nodes("PersonaStyle"):
            a = self.s.node(n)["attrs"]
            if a.get("persona") == persona:
                return a.get("tag") or None
        return None

    def learn_persona_from_text(self, persona, text):
        """Learn a persona's voice from self-demonstrating TEXT (corpus passage). Grounds a
        greeting surface + the persona's flavor markers/tag. Returns what it mined."""
        greeting, tag, markers = self._mine_persona(text)
        if greeting:
            self.learn_persona_by_example(persona, {"greeting": greeting})
        self._set_persona_style(persona, tag, markers)
        return {"greeting": greeting, "tag": tag, "markers": markers}

    def learn_persona_from_tropes(self, persona, trope, teacher=None):
        """Learn a persona from TVTropes: look the trope up (its definition is written IN the
        persona's voice — self-demonstrating) and mine it. Uses the on-disk tropes teacher."""
        if teacher is None:
            from domains.tropes_teacher import TropesTeacher
            teacher = TropesTeacher.from_cache()
        if teacher is None:
            return None
        payload = teacher(trope)
        if not payload:
            return None
        text = payload.get("answer") if isinstance(payload, dict) else str(payload)
        return self.learn_persona_from_text(persona, text)

    def express_as(self, persona, speech_act, word=None):
        """Express a speech act AS a learned persona: its surface in that persona (greeting,
        acknowledgment, ask…), tailed with the persona's signature tag on backchannels."""
        s = (self.surface_for(speech_act, word=word, persona=persona)
             or self.surface_for(speech_act, word=word, persona="neutral") or speech_act)
        tag = self.persona_tag(persona)
        if tag and speech_act in ("acknowledgment", "statement"):
            return f"{s}, {tag}"
        return s

    # --- discovery: record activity, promote salient relations --------------

    def record_activity(self, kind: str, types=()) -> None:
        """Log an activity event (a kind + the body-types it touched) and
        maintain co-occurrence counters: per-(kind,type) counts and lag-1
        (kind,type)→(kind,type) transition counts across consecutive events.
        Mechanical bookkeeping (the agent's activity log)."""
        types = tuple(types)
        if self._activity:
            pk, pts = self._activity[-1]
            for ft in pts:
                for tt in types:
                    key = (pk, ft, kind, tt)
                    self._pair_count[key] = self._pair_count.get(key, 0) + 1
        self._activity.append((kind, types))
        for t in types:
            self._kt_count[(kind, t)] = self._kt_count.get((kind, t), 0) + 1
        # intra-event body-type co-occurrence (for the body_to_body shape)
        uniq = sorted(set(types))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                pk = frozenset((uniq[i], uniq[j]))
                self._type_pair_count[pk] = self._type_pair_count.get(pk, 0) + 1
        self._n_events += 1

    def discover_relations(self, min_count: int = 8, shapes=("temporal_lag",)) -> list:
        """Promote discovered relations to rel_N entries in `_discovered_relations`,
        growing the grammar for each. The DECISION (salience) is the seeded
        predicate; the adapter counts + reifies. `shapes` selects which discovery
        dimensions to promote (default: temporal only, to keep callers stable):
        - 'temporal_lag': (kind,type)->(kind,type) lag-1 pairs, salience-gated.
        - 'agent_to_body': the agent co-occurs with a (kind,type) >= min_count.
        - 'body_to_body': two body-types co-occur within an event >= min_count.
        Re-running updates counts — no duplicate rel ids."""
        sal = {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
            "type": "Neighbours", "node": {"type": "Var", "name": "a"},
            "edge_type": "salience_predicate"}}}
        promoted = []
        temporal_items = self._pair_count.items() if "temporal_lag" in shapes else ()
        for (fk, ft, tk, tt), co in temporal_items:
            if co < min_count:
                continue
            pair = self.s.add_node("PairStat", {
                "co": co, "n_from": self._kt_count.get((fk, ft), 0),
                "n_to": self._kt_count.get((tk, tt), 0), "n_events": self._n_events})
            salient = bool(self.inner.evaluate(sal, {"a": self.agent, "pair": pair}))
            self.inner.remove_node(pair)
            if not salient:
                continue
            key = (fk, ft, tk, tt)
            existing = self._pair_to_rel.get(key)
            if existing is not None:
                self._discovered_relations[existing]["count"] = co   # update on rediscovery
                continue
            self._rel_seq += 1
            rid = f"rel_{self._rel_seq}"
            self._discovered_relations[rid] = {
                "shape": "temporal_lag", "from_kind": fk, "from_type": ft,
                "to_kind": tk, "to_type": tt, "count": co, "lag": 1}
            self._pair_to_rel[key] = rid
            self._grow_grammar(rid, ft, tt, "temporal_lag", co)
            promoted.append(rid)
        if "agent_to_body" in shapes:
            for (kind, t), co in list(self._kt_count.items()):
                if co < min_count or (kind, t) in self._agent_world_to_rel:
                    continue
                self._rel_seq += 1
                rid = f"rel_{self._rel_seq}"
                self._discovered_relations[rid] = {
                    "shape": "agent_to_body", "event_kind": kind, "body_type": t, "count": co}
                self._agent_world_to_rel[(kind, t)] = rid
                self._grow_grammar(rid, "Agent", t, "agent_to_body", co)
                promoted.append(rid)
        if "body_to_body" in shapes:
            for pk, co in list(self._type_pair_count.items()):
                if co < min_count or pk in self._type_pair_to_rel:
                    continue
                ta, tb = sorted(pk)
                self._rel_seq += 1
                rid = f"rel_{self._rel_seq}"
                self._discovered_relations[rid] = {
                    "shape": "body_to_body", "type_a": ta, "type_b": tb, "count": co}
                self._type_pair_to_rel[pk] = rid
                self._grow_grammar(rid, ta, tb, "body_to_body", co)
                promoted.append(rid)
        return promoted

    def _grow_grammar(self, rel_id: str, src_type: str, tgt_type: str,
                      shape: str, count: int) -> None:
        """Meta-Γ growth (the mechanical half of grow_representation): reify a
        discovered relation into (1) a new Γ production admitting
        `(src_type)-[rel_id]->(tgt_type)`, and (2) a Pattern node holding the
        metadata, asserted by agent_root via `asserts_pattern`. The DECISION
        (which relations are salient) is the seeded predicate; this only reifies
        what was accepted — the agent extending the grammar that gates it."""
        try:
            self.inner.add_production({
                "src": {"type": src_type, "var": "s"}, "edge_type": rel_id,
                "tgt": {"type": tgt_type, "var": "t"},
                "provenance": f"discovered:{rel_id}:{shape}"})
        except Exception:
            pass
        pat = self.s.add_node("Pattern", {
            "rel_id": rel_id, "shape": shape, "count": count,
            "from_type": src_type, "to_type": tgt_type})
        self.inner.add_edge_unchecked(self.agent, "asserts_pattern", pat)
        self._meta_productions.add(rel_id)

    def meta_productions(self) -> set:
        """The edge types Γ has grown to admit from discovered relations."""
        return set(self._meta_productions)

    def patterns(self) -> list:
        """The Pattern nodes the agent has asserted from discovery."""
        return [dict(self.s.node(p)["attrs"])
                for p in self.inner.neighbours(self.agent, "asserts_pattern")]

    def body_type(self, world_type):
        """The shared BodyType NodeID for a world type (type-level attrs live
        here; instances reach it via `instance_of`)."""
        return self._body_types.get(world_type)

    def attribute_state(self, world_type, attr) -> dict:
        att = self._attributes.get((world_type, attr))
        return dict(self.s.node(att)["attrs"]) if att is not None else {}

    def is_saturated(self, world_type, attr) -> bool:
        """Is this (type, attr) saturated? — the SEEDED saturation_predicate on
        its Attribute node (same policy as per-instance; one policy, both
        scopes)."""
        att = self._attributes.get((world_type, attr))
        if att is None:
            return False
        return self.is_instance_saturated(att)

    def unsaturated_attributes(self) -> list:
        return [k for k in self._attributes if not self.is_saturated(*k)]

    def senses(self) -> set:
        """The world types the agent has perceived — every ingested node type
        (the graph-native analogue of the old `senses()`; includes types whose
        nodes carry no `id`, e.g. a positional `Body`)."""
        return set(self._sensed_types)

    # --- action choice: preview -> score (seeded) -> Argmax ------------------

    def _preview_novelty(self, world_substrate) -> int:
        """How many scalar (type,attr,value) triples a previewed world state
        carries that the agent hasn't seen — mechanical perception measure."""
        n = 0
        for wn in world_substrate.graph.nodes():
            for k, v in wn.attrs.items():
                if k != "id" and isinstance(v, _SCALAR) and (wn.type, k, v) not in self._seen:
                    n += 1
        return n

    def choose_action(self, legal_actions, preview_fn):
        """Pick an action by the SEEDED curiosity score. `preview_fn(action)`
        returns the previewed world substrate (world-agnostic — the caller knows
        its world's `apply_action` shape). For each action, measure the preview's
        novelty, stamp an ActionCandidate, then `Argmax` over the seeded
        `action_score_term`. The adapter measures + previews; the seed decides."""
        if not legal_actions:
            return None
        # clear stale candidates
        for c in list(self.s.nodes()):
            if self.s.node(c)["type"] == "ActionCandidate":
                self.inner.remove_node(c)
        by_node = {}
        for i, action in enumerate(legal_actions):
            try:
                nov = self._preview_novelty(preview_fn(action))
            except Exception:
                nov = 0
            c = self.s.add_node("ActionCandidate", {"q": 0.0, "asym_count": 0,
                                                    "novelty": nov, "idx": i})
            by_node[c] = action
        choose = {"type": "Argmax",
                  "source": {"type": "NodesOfType", "node_type": "ActionCandidate"},
                  "var_name": "c",
                  "value": {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
                      "type": "Neighbours", "node": {"type": "Var", "name": "a"},
                      "edge_type": "action_score_term"}}}}
        picked = self.inner.evaluate(choose, {"a": self.agent})
        return by_node.get(picked, legal_actions[0])

    # --- language: learn a word as a Term, classify by it --------------------

    def learn_word(self, name: str, definition_term_json: dict):
        """Ground a taught word: materialise its definition Term as a graph
        subgraph and attach it to a named `Concept` node by a `definition`
        edge. Mechanical ingest of a taught definition into the agent's graph —
        the reasoning is the Term, which the agent owns and evaluates.

        Find-or-create by `name` (2026-08-12, SHAPE_AUDIT.md §4.3 fix):
        `self._concepts` IS already persisted/restored across save/load
        (unlike `_recursive_concepts` before its own §4.2 fix), but this
        function never consulted it before minting — re-teaching an
        already-known word minted a second `Concept` + a second definition
        subgraph every time. Falls back to `_concept_by_name` too, same
        "graph is the source of truth" reasoning `_ensure_concept`/
        `learn_recursive_concept` already use, so a Concept minted by some
        OTHER path under this name is found rather than shadowed."""
        cid = self._concepts.get(name)
        if cid is None:
            cid = self._concept_by_name(name)
        if cid is not None:
            for tgt in list(self.inner.neighbours(cid, "definition")):
                self.inner.remove_edge_unchecked(cid, "definition", tgt)
                self.inner.remove_node(tgt)
        else:
            cid = self.s.add_node("Concept", {"name": name})
        root = self.inner.add_term_subgraph(definition_term_json)
        self.inner.add_edge_unchecked(cid, "definition", root)
        self._concepts[name] = cid
        return cid

    def concept_holds(self, name: str, x=None, **binds) -> bool:
        """Does the taught concept apply? — `EvalSubgraph` of the concept's
        definition Term with `x` (and any extra `binds`, e.g. `y` for a binary
        relation like member/subset) bound, plus the agent on `agent`/`self`.
        The agent classifying by an understood definition; the adapter only runs
        the agent's own graph-resident Term."""
        cid = self._concepts.get(name)
        if cid is None:
            return False
        term = {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
            "type": "Neighbours", "node": {"type": "Var", "name": "c"},
            "edge_type": "definition"}}}
        env = {"c": cid, "agent": self.agent, "self": self.agent}
        if x is not None:
            env["x"] = x
            env["boundary"] = x
        env.update(binds)
        return bool(self.inner.evaluate(term, env))

    # --- procedures: concepts a subroutine can INVOKE (via Holds) + run ------

    def concept_holds_composed(self, definition_term_json: dict, x=None, **binds) -> bool:
        """Classify by a COMPOSED definition Term that invokes other grounded
        concepts via `Holds` — evaluate it in the MAIN arena (`inner.evaluate`)
        rather than wrapping in `EvalSubgraph`, whose temp arena can't resolve the
        concept registry. Each invoked concept must have been `register_concept`'d.
        The decision is the Term; the adapter only binds and runs it."""
        env = {"agent": self.agent, "self": self.agent}
        if x is not None:
            env["x"] = x
            env["boundary"] = x
        env.update(binds)
        return bool(self.inner.evaluate(definition_term_json, env))

    def register_concept(self, name: str, definition_term_json: dict) -> None:
        """Make a grounded concept INVOKABLE by `Holds` inside a procedure —
        register its definition Term in the substrate's concept registry (the
        resolver the Rust `Holds` arm consults). Mechanical wiring; the concept's
        Term still decides."""
        self.inner.define_concept(name, definition_term_json)

    def author_subroutine(self, name: str, query_term_json: dict, purpose: str = ""):
        """Author (or edit) a named procedure: store its query Term-tree as graph
        data (agent -authored_subroutine-> Subroutine -query-> Term) + the query
        JSON on the node for the run path. Re-authoring replaces the query.
        Mechanical ingest; the reasoning is the query the agent owns."""
        import json
        index = getattr(self, "_subroutines", None)
        if index is None:
            index = {}
            self._subroutines = index
        query_blob = json.dumps(query_term_json)
        existing = index.get(name)
        if existing is not None:
            for tgt in list(self.inner.neighbours(existing, "query")):
                self.inner.remove_edge_unchecked(existing, "query", tgt)
                self.inner.remove_node(tgt)
            self.inner.set_attr(existing, "query_json", query_blob)
            nid = existing
        else:
            nid = self.inner.add_node("Subroutine",
                                      {"name": name, "purpose": purpose, "query_json": query_blob})
            self.inner.add_edge_unchecked(self.agent, "authored_subroutine", nid)
        root = self.inner.add_term_subgraph(query_term_json)
        self.inner.add_edge_unchecked(nid, "query", root)
        index[name] = nid
        return nid

    def run_subroutine(self, name: str, bindings: dict | None = None):
        """Run a stored procedure — evaluate its query Term against the graph.
        Evaluated via inner.evaluate on the query JSON (the MAIN arena, where
        `Holds` concept defs live — EvalSubgraph's temp arena can't resolve them).
        The adapter runs the agent's own graph-resident Term; no decision here."""
        import json
        index = getattr(self, "_subroutines", None)
        nid = None if index is None else index.get(name)
        if nid is None:
            return None
        blob = self.inner.node(nid)["attrs"].get("query_json")
        if blob is None:
            return None
        query = json.loads(blob)
        env = {"agent": self.agent, "self": self.agent, "subr": nid}
        if bindings:
            env.update(bindings)
        return self.inner.evaluate(query, env)

    # --- recursion: a concept whose definition references its OWN name --------
    # Rust `Holds` has a visited-set cycle guard (a concept re-entering its own
    # name bails to None), so SELF-recursion is expressed by re-evaluating the
    # concept's OWN `definition` subgraph with the recursing var(s) rebound via
    # EvalSubgraph (which shares only the depth budget, cap 32). Graph-native
    # recursion: a self-referential definition that walks its own structure to a
    # base case. Additive — register_concept/Holds unchanged.

    _SELF_VAR = "recur_self"

    @classmethod
    def self_call(cls, *rebinds):
        """The SELF-recursive call Term for use INSIDE a recursive definition:
        re-evaluate this concept's own `definition` subgraph with the recursion
        variable(s) rebound. `rebinds` = (var_name, value_term_json) pairs."""
        body = {"type": "EvalSubgraph", "node": {"type": "Pick", "source": {
            "type": "Neighbours", "node": {"type": "Var", "name": cls._SELF_VAR},
            "edge_type": "definition"}}}
        for name, value in reversed(list(rebinds)):
            body = {"type": "Let", "name": name, "value": value, "body": body}
        return body

    @classmethod
    def call_concept(cls, concept_var: str, *rebinds):
        """Call ANOTHER recursive concept (composition): re-eval the concept at
        env[concept_var] with vars rebound AND recur_self switched to it."""
        return cls.self_call((cls._SELF_VAR, {"type": "Var", "name": concept_var}), *rebinds)

    def learn_recursive_concept(self, name: str, definition_term_json: dict):
        """Ground a recursive concept: store its self-referential definition as a
        Concept node's `definition` subgraph (+ JSON for direct main-arena eval).

        Find-or-create by `name` (2026-08-12, SHAPE_AUDIT.md §4.2 fix): the
        session index `_recursive_concepts` is now persisted/restored across
        save/load (`save`/`load` below) like `_concepts` already was, but a
        checkpoint saved BEFORE this fix (or any other route that minted this
        Concept) would still miss the index — so the lookup falls back to
        `_concept_by_name`, the same "graph is the source of truth, Python may
        cache" pattern `_ensure_concept` already establishes. Re-teaching an
        already-known name now REPLACES its definition subgraph instead of
        minting a duplicate `Concept` node."""
        import json
        index = getattr(self, "_recursive_concepts", None)
        if index is None:
            index = {}
            self._recursive_concepts = index
        cid = index.get(name)
        if cid is None:
            cid = self._concept_by_name(name)
        if cid is not None:
            for tgt in list(self.inner.neighbours(cid, "definition")):
                self.inner.remove_edge_unchecked(cid, "definition", tgt)
                self.inner.remove_node(tgt)
            index[name] = cid
        else:
            cid = self.s.add_node("Concept", {"name": name})
            index[name] = cid
        root = self.inner.add_term_subgraph(definition_term_json)
        self.inner.add_edge_unchecked(cid, "definition", root)
        self.inner.set_attr(cid, "definition_json", json.dumps(definition_term_json))
        return cid

    def recursive_concept(self, name: str):
        index = getattr(self, "_recursive_concepts", None)
        return None if index is None else index.get(name)

    def eval_recursive(self, name: str, bindings: dict | None = None):
        """Evaluate a grounded recursive concept by re-running its definition
        subgraph, with recur_self bound to the Concept node so self_call resolves."""
        import json
        cid = self.recursive_concept(name)
        if cid is None:
            return None
        blob = self.inner.node(cid)["attrs"].get("definition_json")
        if blob is None:
            return None
        definition = json.loads(blob)
        env = {"agent": self.agent, "self": self.agent, self._SELF_VAR: cid}
        if bindings:
            env.update(bindings)
        return self.inner.evaluate(definition, env)
