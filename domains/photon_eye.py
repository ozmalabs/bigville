"""GraphEye — graph-native photon/photoreceptor visual apparatus.

External adapters may supply photon packets directly. RGB frames are accepted
only as an I/O compatibility boundary: they are integrated into three
wavelength-count packets per retinal column, and no pixel/Image/Patch node ever
enters cognition. Native tasks transduce packets through adapting rod/L/M/S
receptors; graph rules synthesize opponent retinal percepts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import substrate_rs as srs

from substrate.seed_loader import manifest_for

PERCEPT = "VisionPercept"
POLYGON = "VisionPolygon"

_RECEPTORS = {
    # center nm, bandwidth nm, half saturation, dark current
    "rod": (498.0, 42.0, 1024.0, 0.15),
    "l": (564.0, 42.0, 512.0, 0.0),
    "m": (534.0, 36.0, 512.0, 0.0),
    "s": (420.0, 28.0, 512.0, 0.0),
}
_EDGE_FOR_CLASS = {
    "rod": "rod_receptor", "l": "l_receptor",
    "m": "m_receptor", "s": "s_receptor",
}

# The shipped real-frame held-prediction apparatus (block 200000).  These are
# graph DATA, not Python policy: staleness_decay's rules read them from the
# HeldDecayParams node.  Keeping the defaults here lets any 2-D photon world
# opt into the already-gated composition without duplicating its mechanical
# construction in a measure script.
_HELD_DECAY_DEFAULTS = {
    "enabled": 1.0,
    "lr_min": 0.15,
    "hl_scale": 32.0,
    "hl_min": 1.0,
    "c0": 1024.0,
    "refresh_thresh": 15.0,
    "attn_thresh": 768.0,
    "uniform": 0.0,
    "uniform_hl": 256.0,
    "pin_freshness": 0.0,
}


def _nid(node):
    return node.value if hasattr(node, "value") else int(str(node).lstrip("#"))


def _add_edge(inner, src, edge_type, tgt):
    try:
        inner.add_edge_unchecked(src, edge_type, tgt)
    except TypeError:
        inner.add_edge_unchecked(src, edge_type, tgt, {})


def _grid_adjacency(n_az: int, n_el: int) -> list[set[int]]:
    adjacent = [set() for _ in range(n_az * n_el)]
    for row in range(n_el):
        for col in range(n_az):
            flat = row * n_az + col
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = row + dr, col + dc
                if 0 <= rr < n_el and 0 <= cc < n_az:
                    adjacent[flat].add(rr * n_az + cc)
    return adjacent


def _layout_record(
        flat, n_az, *, eye_id, pathway, gaze_az, gaze_el,
        angular_width, angular_height, adjacent):
    row, col = divmod(flat, n_az)
    return {
        "cell_index": flat,
        "col": col,
        "row": row,
        "eye_id": str(eye_id),
        "pathway": str(pathway),
        "gaze_az": float(gaze_az),
        "gaze_el": float(gaze_el),
        "angular_width": float(angular_width),
        "angular_height": float(angular_height),
        "adjacent": sorted(int(i) for i in adjacent),
    }


def uniform_receptor_layout(
        n_az: int, n_el: int, *, fov_h_deg: float = 90.0,
        fov_v_deg: float = 60.0, eye_id: str = "cyclopean",
        gaze_az_deg: float = 0.0, gaze_el_deg: float = 0.0) -> list[dict]:
    """Explicit uniform layout exactly matching the legacy receptor centres."""
    if n_az <= 0 or n_el <= 0:
        raise ValueError("receptor layout dimensions must be positive")
    fov_h = math.radians(float(fov_h_deg))
    fov_v = math.radians(float(fov_v_deg))
    gaze_az = math.radians(float(gaze_az_deg))
    gaze_el = math.radians(float(gaze_el_deg))
    adjacent = _grid_adjacency(n_az, n_el)
    records = []
    for row in range(n_el):
        for col in range(n_az):
            flat = row * n_az + col
            az = gaze_az - fov_h / 2 + fov_h * (col + 0.5) / n_az
            el = gaze_el - fov_v / 2 + fov_v * (row + 0.5) / n_el
            records.append(_layout_record(
                flat, n_az, eye_id=eye_id, pathway="uniform",
                gaze_az=az, gaze_el=el,
                angular_width=fov_h / n_az,
                angular_height=fov_v / n_el,
                adjacent=adjacent[flat]))
    return records


def fovea_logpolar_receptor_layout(
        n_az: int, n_el: int, *, fov_h_deg: float = 90.0,
        fov_v_deg: float = 60.0, eye_id: str = "cyclopean",
        gaze_az_deg: float = 0.0, gaze_el_deg: float = 0.0,
        fovea_width: int = 5, fovea_height: int = 5,
        peripheral_rings: int = 5, peripheral_spokes: int = 0,
        fovea_fov_fraction: float = 0.18,
        fovea_fov_h_deg: float | None = None,
        fovea_fov_v_deg: float | None = None,
        source_width: int | None = None,
        source_height: int | None = None,
        periphery_gaze_az_deg: float = 0.0,
        periphery_gaze_el_deg: float = 0.0) -> list[dict]:
    """Foveal Cartesian patch plus geometrically spaced peripheral rings.

    Logical ``row``/``col`` remain a stable count-sheet address. Physical
    neighbourhood and geometry are explicit and need not follow that storage
    grid. The total receptor count is always ``n_az*n_el``.
    """
    total = int(n_az) * int(n_el)
    if total <= 0:
        raise ValueError("receptor layout dimensions must be positive")
    fw = max(1, min(int(fovea_width), n_az))
    fh = max(1, min(int(fovea_height), n_el))
    fovea_n = min(total - 1 if total > 1 else 1, fw * fh)
    # If clipping changed the requested product, retain a compact row-major
    # patch with no fabricated duplicate receptors.
    fw = min(fw, fovea_n)
    fh = max(1, (fovea_n + fw - 1) // fw)
    fov_h = math.radians(float(fov_h_deg))
    fov_v = math.radians(float(fov_v_deg))
    fix_az = math.radians(float(gaze_az_deg))
    fix_el = math.radians(float(gaze_el_deg))
    # The rendered Doom canvas is head-centred. Only the dense patch follows
    # the commanded eye gaze; the peripheral scout remains centred on the
    # camera so an edge fixation does not discard the opposite visual field.
    scout_az = math.radians(float(periphery_gaze_az_deg))
    scout_el = math.radians(float(periphery_gaze_el_deg))
    frac = min(0.8, max(0.02, float(fovea_fov_fraction)))
    # Independent axes matter: Doom's 320x240 source spans a 90x60 degree
    # field, so one source pixel is .28125 x .25 degrees.  A single fraction
    # cannot preserve that native sampling density on both axes.
    if fovea_fov_h_deg is None and source_width:
        fovea_fov_h_deg = float(fov_h_deg) * fw / int(source_width)
    if fovea_fov_v_deg is None and source_height:
        fovea_fov_v_deg = float(fov_v_deg) * fh / int(source_height)
    fovea_h = math.radians(
        float(fovea_fov_h_deg) if fovea_fov_h_deg is not None
        else float(fov_h_deg) * frac)
    fovea_v = math.radians(
        float(fovea_fov_v_deg) if fovea_fov_v_deg is not None
        else float(fov_v_deg) * frac)
    if not (0.0 < fovea_h < fov_h and 0.0 < fovea_v < fov_v):
        raise ValueError("foveal field of view must lie inside the full field")
    frac_h = fovea_h / fov_h
    frac_v = fovea_v / fov_v
    adjacent = [set() for _ in range(total)]
    records: list[dict | None] = [None] * total

    # Dense fovea.
    for flat in range(fovea_n):
        rr, cc = divmod(flat, fw)
        row_count = min(fw, fovea_n - rr * fw)
        az = fix_az + fovea_h * (
            (cc + 0.5) / max(1, row_count) - 0.5)
        el = fix_el + fovea_v * (
            (rr + 0.5) / max(1, fh) - 0.5)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r2, c2 = rr + dr, cc + dc
            other = r2 * fw + c2
            if 0 <= r2 < fh and 0 <= c2 < fw and other < fovea_n:
                adjacent[flat].add(other)
        records[flat] = _layout_record(
            flat, n_az, eye_id=eye_id, pathway="fovea",
            gaze_az=az, gaze_el=el,
            angular_width=fovea_h / max(1, fw),
            angular_height=fovea_v / max(1, fh),
            adjacent=())

    remaining = total - fovea_n
    if remaining:
        rings = max(1, min(int(peripheral_rings), remaining))
        nominal = max(
            3, int(peripheral_spokes) if peripheral_spokes else
            max(3, remaining // rings))
        counts = [nominal] * rings
        delta = remaining - sum(counts)
        cursor = rings - 1
        while delta != 0:
            if delta > 0:
                counts[cursor] += 1
                delta -= 1
            elif counts[cursor] > 1:
                counts[cursor] -= 1
                delta += 1
            cursor = (cursor - 1) % rings
        # Tiny sheets may not support 3 per ring; exact count wins.
        while sum(counts) > remaining:
            for i in range(rings - 1, -1, -1):
                if counts[i] > 1 and sum(counts) > remaining:
                    counts[i] -= 1

        ring_ids: list[list[int]] = []
        ring_theta: list[list[float]] = []
        flat = fovea_n
        # Elliptical radial coordinate. The inner ring begins just outside the
        # larger normalised foveal half-extent, so it never overlaps the dense
        # patch even when the horizontal and vertical pixel angles differ.
        inner_radius = max(frac_h, frac_v)
        edges = [
            inner_radius * (1.0 / inner_radius) ** (i / rings)
            for i in range(rings + 1)
        ]
        for ring, count in enumerate(counts):
            ids, thetas = [], []
            radius = math.sqrt(edges[ring] * edges[ring + 1])
            radial_span = edges[ring + 1] - edges[ring]
            for spoke in range(count):
                theta = 2 * math.pi * spoke / count
                az = scout_az + radius * (fov_h / 2) * math.cos(theta)
                el = scout_el + radius * (fov_v / 2) * math.sin(theta)
                arc = 2 * math.pi * radius / count
                aw = max(radial_span, arc) * fov_h / 2
                ah = max(radial_span, arc) * fov_v / 2
                ids.append(flat)
                thetas.append(theta)
                records[flat] = _layout_record(
                    flat, n_az, eye_id=eye_id,
                    pathway="log_polar_periphery",
                    gaze_az=az, gaze_el=el,
                    angular_width=aw, angular_height=ah, adjacent=())
                flat += 1
            ring_ids.append(ids)
            ring_theta.append(thetas)

        for ring, ids in enumerate(ring_ids):
            for pos, flat in enumerate(ids):
                adjacent[flat].add(ids[(pos - 1) % len(ids)])
                adjacent[flat].add(ids[(pos + 1) % len(ids)])
                if ring:
                    prior = ring_ids[ring - 1]
                    theta = ring_theta[ring][pos]
                    nearest = min(
                        range(len(prior)),
                        key=lambda j: abs(math.atan2(
                            math.sin(theta - ring_theta[ring - 1][j]),
                            math.cos(theta - ring_theta[ring - 1][j]))))
                    adjacent[flat].add(prior[nearest])
                    adjacent[prior[nearest]].add(flat)
                else:
                    # Innermost ring attaches to the nearest dense-grid address.
                    # The closed-form projection avoids an O(periphery*fovea)
                    # gaze-change rebuild while preserving the same geometry.
                    cc = round(
                        ((records[flat]["gaze_az"] - fix_az) / fovea_h + 0.5)
                        * fw - 0.5)
                    rr = round(
                        ((records[flat]["gaze_el"] - fix_el) / fovea_v + 0.5)
                        * fh - 0.5)
                    cc = max(0, min(fw - 1, cc))
                    rr = max(0, min(fh - 1, rr))
                    target = min(fovea_n - 1, rr * fw + cc)
                    adjacent[flat].add(target)
                    adjacent[target].add(flat)

    for flat, record in enumerate(records):
        record["adjacent"] = sorted(adjacent[flat])
    return records


def receptor_layout_from_calibration(
        calibration: dict | None, n_az: int, n_el: int, *,
        fov_h_deg: float = 90.0, fov_v_deg: float = 60.0) -> list[dict]:
    """Canonical apparatus layout from calibration data."""
    cal = dict(calibration or {})
    explicit = cal.get("receptor_layout")
    if explicit is not None:
        layout = [dict(r) for r in explicit]
        if len(layout) != n_az * n_el:
            raise ValueError("explicit receptor layout size does not match retina")
        return layout
    mode = str(cal.get("retinal_layout", "uniform")).lower()
    common = {
        "fov_h_deg": float(cal.get("fov_h_deg", fov_h_deg)),
        "fov_v_deg": float(cal.get("fov_v_deg", fov_v_deg)),
        "eye_id": str(cal.get("eye_id", "cyclopean")),
        "gaze_az_deg": float(cal.get("gaze_az_deg", 0.0)),
        "gaze_el_deg": float(cal.get("gaze_el_deg", 0.0)),
    }
    if mode in ("uniform", "legacy"):
        return uniform_receptor_layout(n_az, n_el, **common)
    if mode in ("foveated", "fovea_logpolar", "log_polar"):
        return fovea_logpolar_receptor_layout(
            n_az, n_el, **common,
            fovea_width=int(cal.get("fovea_width", 5)),
            fovea_height=int(cal.get("fovea_height", 5)),
            peripheral_rings=int(cal.get("peripheral_rings", 5)),
            peripheral_spokes=int(cal.get("peripheral_spokes", 0)),
            fovea_fov_fraction=float(cal.get("fovea_fov_fraction", 0.18)),
            fovea_fov_h_deg=(
                float(cal["fovea_fov_h_deg"])
                if "fovea_fov_h_deg" in cal else None),
            fovea_fov_v_deg=(
                float(cal["fovea_fov_v_deg"])
                if "fovea_fov_v_deg" in cal else None),
            source_width=(
                int(cal["source_width"]) if "source_width" in cal else None),
            source_height=(
                int(cal["source_height"]) if "source_height" in cal else None),
            periphery_gaze_az_deg=float(
                cal.get("periphery_gaze_az_deg", 0.0)),
            periphery_gaze_el_deg=float(
                cal.get("periphery_gaze_el_deg", 0.0)))
    raise ValueError(f"unknown retinal_layout {mode!r}")


@dataclass
class GraphEye:
    """Photon-event eye with graph-resident adapting retinal topology."""

    substrate: srs.Substrate | None = None
    n_az: int = 32
    n_el: int = 12
    fov_h_deg: float = 90.0
    fov_v_deg: float = 60.0
    vband: float = 0.34
    depth_scale: float = 1.0  # accepted for API compatibility; depth is not light
    context: dict = field(default_factory=dict)
    adapt_rate: float = 0.12

    _agent: Any = field(default=None, init=False, repr=False)
    _retina: Any = field(default=None, init=False, repr=False)
    _area: Any = field(default=None, init=False, repr=False)
    _columns: list = field(default_factory=list, init=False, repr=False)
    _cells: list = field(default_factory=list, init=False, repr=False)
    _retina_2d: bool = field(default=False, init=False, repr=False)
    _receptors: dict = field(default_factory=dict, init=False, repr=False)
    _percepts: list = field(default_factory=list, init=False, repr=False)
    _snapshot: dict | None = field(default=None, init=False, repr=False)
    _epoch: int = field(default=0, init=False, repr=False)
    _settled_epoch: int = field(default=0, init=False, repr=False)
    _processed: int = field(default=0, init=False, repr=False)
    _last_exposure: Any = field(default=None, init=False, repr=False)
    _owns_agent_loop: bool = field(default=False, init=False, repr=False)
    _previous_field: list | None = field(default=None, init=False, repr=False)
    _field_shape: tuple | None = field(default=None, init=False, repr=False)
    _onset_enabled: bool = field(default=False, init=False, repr=False)
    _onset_kind: str = field(default="photon_transduce", init=False, repr=False)
    _motion_enabled: bool = field(default=False, init=False, repr=False)
    _carve_enabled: bool = field(default=False, init=False, repr=False)
    _salience_enabled: bool = field(default=False, init=False, repr=False)
    # ACCELERATOR (block 184000): droppable vectorized mirror of the 2-D
    # transduce+onset sheet. OFF by default — the graph path is the oracle.
    _accel: bool = field(default=False, init=False, repr=False)
    _accel_perturb: bool = field(default=False, init=False, repr=False)
    # PER-SENSOR EPOCH (block 188000): 2-D only, OFF by default. The 1-D build
    # never reads these, and with the flag off both key names are `input_epoch`,
    # so every committed path is byte-unchanged.
    _per_sensor_epoch: bool = field(default=False, init=False, repr=False)
    _wrong_epoch: bool = field(default=False, init=False, repr=False)
    _retina_epoch_key: str = field(default="input_epoch", init=False, repr=False)
    _column_epoch_key: str = field(default="input_epoch", init=False, repr=False)
    # BINDING PROJECTION (block 195000): ship the eye LINEAR. DEFAULT ON.
    _binding_projection: bool = field(default=True, init=False, repr=False)
    _binding_projection_wrong: bool = field(default=False, init=False, repr=False)
    # HELD PREDICTION (block 200000 live reuse): additive 2-D apparatus,
    # absent by default.  These are mechanical indexes into graph-resident
    # state; prediction, surprise, decay and attention remain graph rules.
    _held_prediction_mode: str | None = field(default=None, init=False, repr=False)
    _held_prediction_params: Any = field(default=None, init=False, repr=False)
    _held_surface_cells: list = field(default_factory=list, init=False, repr=False)
    _last_allocentric_prior: Any = field(default=None, init=False, repr=False)
    # ATTENTION-DIRECTED EVENT FOCUS: optional graph-resident apparatus.  The
    # main cognition graph chooses/refuses a focus; the adapter only copies its
    # command here, and the Rust event batch reads this node directly.
    _focus_window: Any = field(default=None, init=False, repr=False)
    _focus_settled_cells: set = field(default_factory=set, init=False, repr=False)
    # Explicit non-uniform optics are additive and absent by default. Logical
    # cell addresses stay row-major; these records own their physical geometry.
    _layout_explicit: bool = field(default=False, init=False, repr=False)
    _receptor_layout: list = field(default_factory=list, init=False, repr=False)
    _layout_adjacency_edges: set = field(
        default_factory=set, init=False, repr=False)

    def _apply_binding_projection(self, inner) -> None:
        """SHIP THE LINEAR EYE (block 195000) — mechanical adapter config, no
        agent logic. The eye's per-tick match is dominated by the scheduler rule
        `ct_area_effort_tracks_live_salience`, which binds `task` but references
        it in NEITHER its where-clause NOR its effects; it is PROJECTABLE to
        `["area"]`. `binding_projection` (the 188000 engine flag, a droppable
        BYTE-IDENTICAL-on-observables mirror) fires that rule's guard once per
        AREA instead of once per task-on-area, collapsing an O(cells^2)
        `term_eval:Attr` count to O(cells). DEFAULT ON; the world opts OUT via
        `context['binding_projection']=False` (the gate ORACLE — the OFF path IS
        the committed path; ON is byte-identical to it on the observable manifold
        and, once the nondeterministic wall-clock attrs are stripped, on the whole
        graph — see block 195000 RESULTS). `binding_projection_wrong` sets
        the UNSOUND falsifier (`set_projection_overaggressive`: project on the
        EMPTY variable set — one fire per visit however many areas match), which
        MUST break an observable. Off ⇒ the committed (quadratic) path."""
        self._binding_projection = bool(
            self.context.get("binding_projection", True))
        self._binding_projection_wrong = bool(
            self.context.get("binding_projection_wrong", False))
        if self._binding_projection_wrong:
            self._binding_projection = True
        if not self._binding_projection:
            return
        setter = getattr(inner, "set_binding_projection", None)
        if setter is None:
            return  # engine predates block 188000 — leave the committed path
        setter(True)
        if self._binding_projection_wrong:
            over = getattr(inner, "set_projection_overaggressive", None)
            if over is not None:
                over(True)

    def _install_held_prediction_2d(self, inner) -> None:
        """Mechanically install the existing graph-native held prediction.

        ``held_prediction=True`` and ``held_prediction="decay"`` select the
        real-frame staleness-decay composition proven in block 200000.  Worlds
        may override its graph-data parameters with
        ``context["held_prediction_params"]`` (or by supplying a dict as
        ``held_prediction`` with an optional ``mode`` key).

        This method creates apparatus only.  The residual, half-life,
        freshness, adaptive blend and attention decisions are the existing
        ``staleness_decay`` graph rules.  With the option absent/false it makes
        no graph mutation, preserving the committed eye byte-for-byte.
        """
        configured = self.context.get("held_prediction", False)
        if not configured:
            return

        overrides = self.context.get("held_prediction_params", {})
        if isinstance(configured, dict):
            configured = dict(configured)
            mode = configured.pop("mode", "decay")
            overrides = {**configured, **dict(overrides)}
        else:
            mode = "decay" if configured is True else str(configured)
            overrides = dict(overrides)
        if mode != "decay":
            raise ValueError(
                "held_prediction must be false, true, 'decay', or a decay config")
        if self._per_sensor_epoch:
            raise ValueError(
                "held_prediction='decay' currently requires input_epoch clocks")

        params = dict(_HELD_DECAY_DEFAULTS)
        params.update(overrides)
        self._held_prediction_mode = mode
        inner.load_seed_manifest(manifest_for("staleness_decay"), self._agent)
        self._held_prediction_params = self.substrate.add_node(
            "HeldDecayParams", params)
        _add_edge(
            inner, self._retina, "has_held_decay_params",
            self._held_prediction_params)

        for flat, cell in enumerate(self._cells):
            row, col = divmod(flat, self.n_az)
            held_attrs = {
                "value": 0.0,
                "obs": 0.0,
                "row": row,
                "col": col,
                "cell_index": flat,
                "epoch": 0.0,
                "residual": 0.0,
                "last_refresh_epoch": 0.0,
                "half_life": params["hl_scale"],
                "freshness": params["c0"],
                "needs_attention": 0.0,
            }
            if self._layout_explicit:
                geometry = self._receptor_layout[flat]
                held_attrs.update({
                    "eye_id": str(geometry["eye_id"]),
                    "pathway": str(geometry["pathway"]),
                    "gaze_az": float(geometry["gaze_az"]),
                    "gaze_el": float(geometry["gaze_el"]),
                    "angular_width": float(geometry["angular_width"]),
                    "angular_height": float(geometry["angular_height"]),
                })
            held = self.substrate.add_node("HeldSurfaceCell", held_attrs)
            _add_edge(inner, cell, "has_held_surface_cell", held)
            self._held_surface_cells.append(held)

    def build(self) -> "GraphEye":
        # THE 2-D EXPANSION (additive, OFF by default): when the world asks for a
        # 2-D az×el retina, build the receptor SHEET instead of the 1-D azimuth
        # strip. With the flag off this branch is never taken and the 1-D build
        # below is byte-identical to before this rung (§9).
        self._retina_2d = bool(self.context.get("retina_2d", False))
        # GRAPH-NATIVE EVENT PATH (block 191000). DEFAULT ON (the shipped fix):
        # set BEFORE the 1-D / 2-D branch so every settle path has it. The six
        # carve/motion/salience settle methods hand the whole RetinalOnsetEvent
        # sweep to ONE Rust op (`retina_event_task_batch`) instead of marshalling
        # every event out of the graph one node at a time in Python.
        # `event_native=False` runs the old Python loop — the byte-identity
        # ORACLE. `event_native_perturb` is the wrong-read FALSIFIER.
        self._event_native = bool(self.context.get("event_native", True))
        self._event_perturb = bool(self.context.get("event_native_perturb", False))
        if self._retina_2d:
            return self._build_2d()
        if self.substrate is None:
            self.substrate = srs.Substrate()
        inner = self.substrate._inner
        self._apply_binding_projection(inner)
        self._agent = self.substrate.add_node("Agent", {"role": "vision_root"})
        # OFF by default: the async-onset seed + task kind are additive and
        # engaged only when the world asks for them. With it off, the retina
        # loads and behaves byte-identically to before this rung.
        self._onset_enabled = bool(self.context.get("visual_onset", False))
        # Async MOTION (Rung 2) is derived FROM the onset-event stream, so it
        # implies the onset path — the motion task reads RetinalOnsetEvents.
        self._motion_enabled = bool(self.context.get("visual_motion", False))
        if self._motion_enabled:
            self._onset_enabled = True
        # Async COMMON-FATE CARVE (Rung 3) groups the onset-event stream into
        # VisionPolygon azimuth spans, so it implies the onset path — it reads
        # RetinalOnsetEvents, not the raster.
        self._carve_enabled = bool(self.context.get("visual_carve", False))
        if self._carve_enabled:
            self._onset_enabled = True
        # Async PER-AREA RESIDUAL SALIENCE (Rung 4) computes salience as the
        # residual of the onset-event stream after the dominant common-fate
        # motion is explained, so it implies the onset path — it reads
        # RetinalOnsetEvents, not the raster.
        self._salience_enabled = bool(self.context.get("visual_salience", False))
        if self._salience_enabled:
            self._onset_enabled = True
        self._onset_kind = (
            "photon_transduce_onset" if self._onset_enabled else "photon_transduce")
        seeds = ["cognitive_areas", "cognitive_scheduler", "photon_retina"]
        if self._onset_enabled:
            seeds.append("retinal_onset")
        if self._motion_enabled:
            seeds.append("retinal_motion")
        if self._carve_enabled:
            seeds.append("retinal_carve")
        if self._salience_enabled:
            seeds.append("retinal_salience")
        for seed in seeds:
            inner.load_seed_manifest(manifest_for(seed), self._agent)
        self._area = self.substrate.add_node("CognitiveArea", {
            "name": "retina", "status": "active", "logical_tick": 0,
            "input_epoch": 0,
            "desired_workers": int(self.context.get("worker_capacity", 1)),
            "effort": 1.0, "last_residual_epoch": -1,
        })
        _add_edge(inner, self._agent, "has_cognitive_area", self._area)
        self._retina = self.substrate.add_node("Retina", {
            "name": "photon_retina", "n_columns": self.n_az,
            "input_epoch": 0,
        })
        for index in range(self.n_az):
            az = math.radians(
                -self.fov_h_deg / 2
                + self.fov_h_deg * (index + 0.5) / self.n_az)
            column = self.substrate.add_node("RetinalColumn", {
                "index": index, "gaze_az": az, "input_epoch": 0,
            })
            percept = self.substrate.add_node("RetinalPercept", {
                "index": index, "input_epoch": -1, "intensity": 0.0,
                "red_green": 0.0, "blue_yellow": 0.0, "salience": 0.0,
            })
            _add_edge(inner, self._retina, "has_column", column)
            _add_edge(inner, column, "has_retinal_percept", percept)
            self._columns.append(column)
            self._percepts.append(percept)
            for receptor_class, (center, bandwidth, half, dark) in _RECEPTORS.items():
                receptor = self.substrate.add_node("Photoreceptor", {
                    "receptor_class": receptor_class,
                    "column": index,
                    "sensitivity_center_nm": center,
                    "bandwidth_nm": bandwidth,
                    "half_saturation": half,
                    "dark_current": dark,
                    "adapt_rate": self.adapt_rate,
                    "activation": 0.0,
                    "prev_activation": 0.0,
                    "adaptation": 0.0,
                    "caught_quanta": 0.0,
                })
                _add_edge(inner, column, "has_receptor", receptor)
                _add_edge(inner, column, _EDGE_FOR_CLASS[receptor_class], receptor)
                self._receptors[(index, receptor_class)] = receptor
        if self._onset_enabled:
            # One RetinaOnsetParams node is the graph-data gate + config for
            # the mint rule (§0: an ablation is DATA on a params node, never a
            # Python branch). Absent it, `retinal_mint_onset` cannot match.
            params = self.substrate.add_node("RetinaOnsetParams", {
                "enabled": 1.0,
                "threshold_db": float(self.context.get("onset_threshold_db", 6.0)),
                "refractory_epochs":
                    float(self.context.get("onset_refractory_epochs", 0.0)),
            })
            _add_edge(inner, self._retina, "has_onset_params", params)
            for column in self._columns:
                # Seed the refractory clock far in the past so the first
                # qualifying epoch can fire.
                self.substrate.set_attr(column, "last_onset_epoch", -1.0e9)
        if self._motion_enabled:
            # One RetinaMotionParams node is the graph-data gate + config for
            # `retinal_mint_motion` (§0: thresholds are DATA, never a Python
            # branch). Absent it, the mint rule cannot match. `min_events` is a
            # Gt threshold, so 2.5 requires at least 3 events to fit a slope.
            mparams = self.substrate.add_node("RetinaMotionParams", {
                "enabled": 1.0,
                "min_coherence":
                    float(self.context.get("motion_min_coherence", 0.5)),
                "min_events": float(self.context.get("motion_min_events", 2.5)),
            })
            _add_edge(inner, self._retina, "has_motion_params", mparams)
        if self._carve_enabled:
            # One RetinaCarveParams node is the graph-data gate + config for
            # `retinal_mint_carve` (§0: thresholds are DATA, never a Python
            # branch). Absent it the mint rule cannot match. `min_events` /
            # `min_coherence` gate which runs become VisionPolygons (a scrambled
            # field fragments below `min_events` / decorrelates below
            # `min_coherence` -> no polygon). `max_gap` / `vel_tol` are the
            # kernel's common-fate segmentation params, packed into the payload.
            cparams = self.substrate.add_node("RetinaCarveParams", {
                "enabled": 1.0,
                "min_coherence":
                    float(self.context.get("carve_min_coherence", 0.5)),
                "min_events": float(self.context.get("carve_min_events", 2.5)),
                "max_gap": float(self.context.get("carve_max_gap", 1.0)),
                "vel_tol": float(self.context.get("carve_vel_tol", 0.35)),
            })
            _add_edge(inner, self._retina, "has_carve_params", cparams)
        if self._salience_enabled:
            # One RetinaSalienceParams node is the graph-data gate + config for
            # `retinal_mint_salience` (§0: thresholds are DATA, never a Python
            # branch). Absent it the mint rule cannot match. `max_gap` /
            # `vel_tol` are the kernel's common-fate segmentation params (the
            # dominant run defines v_dom), packed into the payload — the SAME
            # segmentation the carve uses, so a firing column's residual is its
            # departure from the dominant coherent motion.
            sparams = self.substrate.add_node("RetinaSalienceParams", {
                "enabled": 1.0,
                "max_gap": float(self.context.get("salience_max_gap", 1.0)),
                "vel_tol": float(self.context.get("salience_vel_tol", 0.35)),
            })
            _add_edge(inner, self._retina, "has_salience_params", sparams)

        workers = max(1, int(self.context.get("worker_capacity", 1)))
        if not self.context.get("synchronous", False) and not self.substrate.agent_running():
            self.substrate.start_agent(
                tick_rate_hz=float(self.context.get("retina_tick_hz", 120.0)),
                n_threads_per_runner=workers,
            )
            self._owns_agent_loop = True
        return self

    def _build_2d(self) -> "GraphEye":
        """Build the 2-D az×el RECEPTOR SHEET (the 2-D expansion of Rungs 1-4).

        Each `(col, row)` is a cell — a `RetinalColumn` carrying `col`=azimuth
        index, `row`=elevation index, `cell_index`=flat row-major index — with its
        OWN adapting rod receptor and onset history. Loads the 2-D onset + 2-D
        carve seeds (NOT the 1-D onset/carve seeds), so only the 2-D onset rule
        fires. Mechanical construction only — no decision.
        """
        if self.substrate is None:
            self.substrate = srs.Substrate()
        inner = self.substrate._inner
        self._apply_binding_projection(inner)
        self._agent = self.substrate.add_node("Agent", {"role": "vision_root"})
        self._onset_enabled = True
        self._onset_kind = "photon_transduce_onset"
        # ACCELERATOR (block 184000): the droppable vectorized-mirror path for
        # the per-cell transduce+onset sheet. OFF by default; the world opts in
        # via context['retina_accel']. `retina_accel_perturb` injects a wrong
        # mirror (the byte-identity non-vacuity falsifier).
        self._accel = bool(self.context.get("retina_accel", False))
        self._accel_perturb = bool(self.context.get("retina_accel_perturb", False))
        # DIRTY-INDEX (block 185000): process only the cells that CHANGED (the
        # sensor's own change report) plus the cells not yet SETTLED (the eye's
        # own state, returned by the batch op). OFF by default — with it off the
        # 184000 full sweep runs byte-unchanged. `retina_dirty_stamp_epoch`
        # restores the one attribute a skip would leave stale (`input_epoch` on
        # a skipped rod); `retina_dirty_naive` is the WRONG-predicate falsifier.
        self._dirty_index = bool(self.context.get("retina_dirty", False))
        self._dirty_stamp_epoch = bool(
            self.context.get("retina_dirty_stamp_epoch", False))
        self._dirty_naive = bool(self.context.get("retina_dirty_naive", False))
        # BRANCH B — BOUNDED SHEDDING. OFF by default. With it ON the eye trusts
        # the sensor's report ALONE and does NOT carry its own not-yet-settled
        # cells: an unreported cell is skipped even though its adapting floor is
        # still moving. That DEFERS/SHEDS a small residual — a SEMANTIC CHANGE,
        # not a droppable mirror, and NO byte-identity is claimed for it.
        self._dirty_shed = bool(self.context.get("retina_dirty_shed", False))
        # The eye's own per-area dirty state: which cells are not yet settled,
        # and the last input actually FOLDED into each cell (so an unsettled but
        # unreported cell is re-presented with exactly the input a full sweep
        # would give it). Both start "everything is dirty".
        self._unsettled = None
        self._last_input = {}
        self._skip_log = []
        self._carve_enabled = True
        # CLOSING THE 2-D LOOP (block 170000): the 2-D MOTION and 2-D SALIENCE
        # seeds are ADDITIVE and load ONLY when the world asks for them AND the
        # retina is 2-D. With their flags off, this 2-D build is byte-identical
        # to the 166000 2-D-carve build (§9) — proven by the gate + oracle.
        self._motion_enabled = bool(self.context.get("visual_motion", False))
        self._salience_enabled = bool(self.context.get("visual_salience", False))
        focus_enabled = bool(self.context.get("retinal_focus", False))
        # PER-SENSOR EPOCH (block 188000). OFF by default. With it ON each
        # sensor's clock carries its OWN attribute key — the retina's own
        # `retina_epoch`, the cell's `column_epoch`, the rod's `rod_epoch` —
        # instead of one shared `input_epoch` written to a shared root, and the
        # rod's clock advances only when the rod's own state changed (the exact
        # bitwise predicate, in `retina_onset_batch`). A SEMANTIC change, not a
        # droppable mirror: NO whole-graph byte-identity is claimed for it.
        # `per_sensor_epoch_wrong` is the FALSIFIER (a rod clock that never
        # advances); it MUST break an observable output.
        self._per_sensor_epoch = bool(self.context.get("per_sensor_epoch", False))
        self._wrong_epoch = bool(
            self.context.get("per_sensor_epoch_wrong", False))
        if self._wrong_epoch:
            self._per_sensor_epoch = True
        retina_seed = ("photon_retina_wrong_epoch" if self._wrong_epoch
                       else "photon_retina_per_sensor" if self._per_sensor_epoch
                       else "photon_retina")
        onset_seed = ("retinal_onset_2d_per_sensor" if self._per_sensor_epoch
                      else "retinal_onset_2d")
        carve_seed = (
            "retinal_carve_2d_focused" if focus_enabled
            else "retinal_carve_2d")
        seeds = ["cognitive_areas", "cognitive_scheduler", retina_seed,
                 onset_seed, carve_seed]
        if self._motion_enabled:
            seeds.append("retinal_motion_2d")
        if self._salience_enabled:
            seeds.append(
                "retinal_salience_2d_focused" if focus_enabled
                else "retinal_salience_2d")
        for seed in seeds:
            inner.load_seed_manifest(manifest_for(seed), self._agent)
        self._area = self.substrate.add_node("CognitiveArea", {
            "name": "retina", "status": "active", "logical_tick": 0,
            "input_epoch": 0,
            "desired_workers": int(self.context.get("worker_capacity", 1)),
            "effort": 1.0, "last_residual_epoch": -1,
        })
        _add_edge(inner, self._agent, "has_cognitive_area", self._area)
        # The RETINA's own clock. Under the per-sensor epoch it is named
        # `retina_epoch` — 187000's isolation probe measured that this ONE write,
        # on a node NO rule reads that key on, takes the graph from 0 dirty rules
        # to 8 across all 6 areas purely because the KEY is shared.
        self._retina_epoch_key = (
            "retina_epoch" if self._per_sensor_epoch else "input_epoch")
        self._column_epoch_key = (
            "column_epoch" if self._per_sensor_epoch else "input_epoch")
        calibration = self.context.get("retinal_calibration", self.context)
        self._layout_explicit = (
            isinstance(calibration, dict)
            and ("retinal_layout" in calibration
                 or "receptor_layout" in calibration))
        if self._layout_explicit:
            self._receptor_layout = receptor_layout_from_calibration(
                calibration, self.n_az, self.n_el,
                fov_h_deg=self.fov_h_deg, fov_v_deg=self.fov_v_deg)
            self._validate_receptor_layout_2d(self._receptor_layout)
        retina_attrs = {
            "name": "photon_retina_2d", "n_columns": self.n_az,
            "n_rows": self.n_el, self._retina_epoch_key: 0,
        }
        if self._layout_explicit:
            pathway_counts: dict[str, int] = {}
            for record in self._receptor_layout:
                pathway = str(record["pathway"])
                pathway_counts[pathway] = pathway_counts.get(pathway, 0) + 1
            retina_attrs.update({
                "retinal_layout": str(
                    calibration.get("retinal_layout", "explicit")),
                "eye_id": str(self._receptor_layout[0]["eye_id"]),
                # Graph-data allocation of the costly common-fate/motion/
                # salience stream. The full fovea remains transduced and held;
                # the persistent peripheral scout can own transient grouping.
                "event_pathway": str(
                    calibration.get("event_pathway", "all")),
                "fovea_receptors": pathway_counts.get("fovea", 0),
                "peripheral_receptors":
                    pathway_counts.get("log_polar_periphery", 0),
                "uniform_receptors": pathway_counts.get("uniform", 0),
            })
        self._retina = self.substrate.add_node("Retina", retina_attrs)
        center, bandwidth, half, dark = _RECEPTORS["rod"]
        for row in range(self.n_el):
            for col in range(self.n_az):
                flat = row * self.n_az + col
                if self._layout_explicit:
                    geometry = self._receptor_layout[flat]
                    az = float(geometry["gaze_az"])
                    el = float(geometry["gaze_el"])
                else:
                    az = math.radians(
                        -self.fov_h_deg / 2
                        + self.fov_h_deg * (col + 0.5) / self.n_az)
                    el = math.radians(
                        -self.fov_v_deg / 2
                        + self.fov_v_deg * (row + 0.5) / self.n_el)
                cell_attrs = {
                    "index": col, "col": col, "row": row, "cell_index": flat,
                    "gaze_az": az, "gaze_el": el, self._column_epoch_key: 0,
                }
                if self._layout_explicit:
                    cell_attrs.update({
                        "eye_id": str(geometry["eye_id"]),
                        "pathway": str(geometry["pathway"]),
                        "angular_width": float(geometry["angular_width"]),
                        "angular_height": float(geometry["angular_height"]),
                    })
                cell = self.substrate.add_node("RetinalColumn", cell_attrs)
                _add_edge(inner, self._retina, "has_column", cell)
                self._cells.append(cell)
                rod_attrs = {
                    "receptor_class": "rod", "column": col, "row": row,
                    "sensitivity_center_nm": center, "bandwidth_nm": bandwidth,
                    "half_saturation": half, "dark_current": dark,
                    "adapt_rate": self.adapt_rate, "activation": 0.0,
                    "prev_activation": 0.0, "adaptation": 0.0,
                    "caught_quanta": 0.0,
                }
                if self._layout_explicit:
                    rod_attrs.update({
                        "cell_index": flat,
                        "eye_id": str(geometry["eye_id"]),
                        "pathway": str(geometry["pathway"]),
                        "gaze_az": az, "gaze_el": el,
                        "angular_width": float(geometry["angular_width"]),
                        "angular_height": float(geometry["angular_height"]),
                    })
                rod = self.substrate.add_node("Photoreceptor", rod_attrs)
                _add_edge(inner, cell, "has_receptor", rod)
                _add_edge(inner, cell, "rod_receptor", rod)
                self._receptors[(flat, "rod")] = rod
                # Seed the refractory clock far in the past so the first
                # qualifying epoch can fire (mirrors the 1-D onset build).
                self.substrate.set_attr(cell, "last_onset_epoch", -1.0e9)
        if self._layout_explicit:
            self._install_layout_adjacency_2d()
        if focus_enabled:
            # The focused mint rules enumerate this explicit settlement
            # relation, never the whole receptor sheet.  It starts as the full
            # sheet, which is the exact attention-refusal fallback.
            for flat, cell in enumerate(self._cells):
                _add_edge(inner, self._retina, "settles_column", cell)
                self._focus_settled_cells.add(flat)
        params = self.substrate.add_node("RetinaOnsetParams2d", {
            "enabled": 1.0,
            "threshold_db": float(self.context.get("onset_threshold_db", 6.0)),
            "refractory_epochs":
                float(self.context.get("onset_refractory_epochs", 0.0)),
        })
        _add_edge(inner, self._retina, "has_onset_params_2d", params)
        cparams = self.substrate.add_node("RetinaCarveParams2d", {
            "enabled": 1.0,
            "min_coherence": float(self.context.get("carve_min_coherence", 0.5)),
            "min_events": float(self.context.get("carve_min_events", 2.5)),
            "max_gap": float(self.context.get("carve_max_gap", 1.0)),
            "vel_tol": float(self.context.get("carve_vel_tol", 0.35)),
        })
        _add_edge(inner, self._retina, "has_carve_params_2d", cparams)
        if self._motion_enabled:
            # Graph-data gate + config for `retinal_mint_motion_2d` (§0:
            # thresholds are DATA). `min_events` Gt 2.5 requires ≥3 events.
            mparams = self.substrate.add_node("RetinaMotionParams2d", {
                "enabled": 1.0,
                "min_coherence":
                    float(self.context.get("motion_min_coherence", 0.5)),
                "min_events": float(self.context.get("motion_min_events", 2.5)),
            })
            _add_edge(inner, self._retina, "has_motion_params_2d", mparams)
        if self._salience_enabled:
            # Graph-data gate + config for `retinal_mint_salience_2d`. The
            # common-fate segmentation params are read as DATA off this node.
            sparams = self.substrate.add_node("RetinaSalienceParams2d", {
                "enabled": 1.0,
                "max_gap": float(self.context.get("salience_max_gap", 1.0)),
                "vel_tol": float(self.context.get("salience_vel_tol", 0.35)),
            })
            _add_edge(inner, self._retina, "has_salience_params_2d", sparams)
        if focus_enabled:
            self._focus_window = self.substrate.add_node(
                "RetinalFocusWindow", {
                    "active": 0.0,
                    "center_col": -1,
                    "center_row": -1,
                    "half_width": int(
                        self.context.get("retinal_focus_half_width", 2)),
                    "half_height": int(
                        self.context.get("retinal_focus_half_height", 2)),
                    "source_epoch": -1,
                })
            _add_edge(
                inner, self._retina, "has_focus_window", self._focus_window)
        self._install_held_prediction_2d(inner)
        return self

    def _validate_receptor_layout_2d(self, layout) -> None:
        """Validate the mechanical receptor-sheet address/geometry contract."""
        n = self.n_az * self.n_el
        if len(layout) != n:
            raise ValueError("receptor layout size does not match retina")
        required = {
            "cell_index", "col", "row", "eye_id", "pathway", "gaze_az",
            "gaze_el", "angular_width", "angular_height", "adjacent",
        }
        for flat, record in enumerate(layout):
            missing = required.difference(record)
            if missing:
                raise ValueError(
                    f"receptor {flat} is missing {sorted(missing)!r}")
            row, col = divmod(flat, self.n_az)
            if (int(record["cell_index"]) != flat
                    or int(record["col"]) != col
                    or int(record["row"]) != row):
                raise ValueError(
                    "receptor layout must use canonical row-major addresses")
            values = (
                float(record["gaze_az"]), float(record["gaze_el"]),
                float(record["angular_width"]),
                float(record["angular_height"]))
            if not all(math.isfinite(value) for value in values):
                raise ValueError("receptor geometry must be finite")
            if values[2] <= 0.0 or values[3] <= 0.0:
                raise ValueError("receptor apertures must be positive")
            neighbours = [int(i) for i in record["adjacent"]]
            if (len(neighbours) != len(set(neighbours))
                    or flat in neighbours
                    or any(i < 0 or i >= n for i in neighbours)):
                raise ValueError("invalid receptor adjacency")
        for flat, record in enumerate(layout):
            for other in record["adjacent"]:
                if flat not in layout[int(other)]["adjacent"]:
                    raise ValueError("receptor adjacency must be symmetric")

    def _install_layout_adjacency_2d(self) -> None:
        for src, tgt in self._layout_adjacency_edges:
            self.substrate.remove_edge(
                self._cells[src], "adjacent_receptor", self._cells[tgt])
        self._layout_adjacency_edges.clear()
        for flat, record in enumerate(self._receptor_layout):
            for other in record["adjacent"]:
                pair = (flat, int(other))
                _add_edge(
                    self.substrate._inner, self._cells[pair[0]],
                    "adjacent_receptor", self._cells[pair[1]])
                self._layout_adjacency_edges.add(pair)

    def update_receptor_layout_2d(
            self, layout=None, *, calibration=None) -> None:
        """Mechanically install new graph-issued gaze geometry.

        This changes only receptor optics and physical adjacency. All pathways,
        including the peripheral scout ring, remain live members of the same
        photon/event sheet. Selection of the new gaze belongs to the graph.
        """
        if not (self._retina_2d and self._layout_explicit):
            raise ValueError(
                "receptor layout updates require an explicit 2-D layout")
        if layout is None:
            if calibration is None:
                raise ValueError("layout or calibration is required")
            layout = receptor_layout_from_calibration(
                calibration, self.n_az, self.n_el,
                fov_h_deg=self.fov_h_deg, fov_v_deg=self.fov_v_deg)
        layout = [dict(record) for record in layout]
        self._validate_receptor_layout_2d(layout)
        self._receptor_layout = layout
        for flat, geometry in enumerate(layout):
            attrs = {
                "eye_id": str(geometry["eye_id"]),
                "pathway": str(geometry["pathway"]),
                "gaze_az": float(geometry["gaze_az"]),
                "gaze_el": float(geometry["gaze_el"]),
                "angular_width": float(geometry["angular_width"]),
                "angular_height": float(geometry["angular_height"]),
            }
            for key, value in attrs.items():
                self.substrate.set_attr(self._cells[flat], key, value)
                self.substrate.set_attr(
                    self._receptors[(flat, "rod")], key, value)
                if flat < len(self._held_surface_cells):
                    self.substrate.set_attr(
                        self._held_surface_cells[flat], key, value)
        counts = self.receptor_pathway_counts_2d()
        self.substrate.set_attr(
            self._retina, "eye_id", str(self._receptor_layout[0]["eye_id"]))
        if calibration is not None:
            self.substrate.set_attr(
                self._retina, "event_pathway",
                str(calibration.get("event_pathway", "all")))
        for key, value in {
                "fovea_receptors": counts.get("fovea", 0),
                "peripheral_receptors":
                    counts.get("log_polar_periphery", 0),
                "uniform_receptors": counts.get("uniform", 0)}.items():
            self.substrate.set_attr(self._retina, key, value)
        self._install_layout_adjacency_2d()

    def receptor_pathway_counts_2d(self) -> dict[str, int]:
        """Mechanical census proving dense and scout pathways stay exposed."""
        counts: dict[str, int] = {}
        for record in self._receptor_layout:
            pathway = str(record["pathway"])
            counts[pathway] = counts.get(pathway, 0) + 1
        return counts

    def project_allocentric_surfaces_2d(
            self, *, surface_x, surface_y, surface_z, surface_radius,
            surface_value, surface_confidence, pose_x, pose_y, pose_z,
            pose_yaw, pose_pitch):
        """Mechanically project world supports into the current receptor sheet.

        All coordinates are caller-calibrated world units; yaw, pitch and
        receptor geometry are radians. The compiled primitive chooses only the
        nearest overlapping support. An absent support remains absent via the
        returned ``present`` mask; this method invents no unknown values.
        """
        if not self._retina_2d:
            raise ValueError("allocentric projection requires a 2-D retina")
        if self._layout_explicit:
            layout = self._receptor_layout
        else:
            layout = uniform_receptor_layout(
                self.n_az, self.n_el, fov_h_deg=self.fov_h_deg,
                fov_v_deg=self.fov_v_deg)
        values, confidences, present, source_indices = (
            srs._native.allocentric_retinal_projection(
                list(surface_x), list(surface_y), list(surface_z),
                list(surface_radius), list(surface_value),
                list(surface_confidence),
                float(pose_x), float(pose_y), float(pose_z),
                float(pose_yaw), float(pose_pitch),
                [float(record["gaze_az"]) for record in layout],
                [float(record["gaze_el"]) for record in layout],
                [float(record["angular_width"]) for record in layout],
                [float(record["angular_height"]) for record in layout],
            ))
        return {
            "values": list(values),
            "confidences": list(confidences),
            "present": list(present),
            "source_indices": list(source_indices),
        }

    def ingest_allocentric_prior_2d(
            self, values, confidences, present, *, source_epoch,
            source_indices=None) -> int:
        """Copy an already-projected graph prior into held prediction state.

        Presence is explicit: absent/unknown receptors are untouched. For each
        present receptor, value and confidence are copied without thresholds,
        scaling, ranking or fallback. Photon evidence subsequently meets the
        ordinary graph-native residual/decay/blend rules.
        """
        if not (self._retina_2d and self._held_surface_cells):
            return 0
        n = self.n_az * self.n_el
        values = list(values)
        confidences = list(confidences)
        present = list(present)
        if len(values) != n or len(confidences) != n or len(present) != n:
            raise ValueError("allocentric prior size does not match retina")
        if (not all(math.isfinite(float(v)) for v in values)
                or not all(
                    math.isfinite(float(v)) and float(v) >= 0.0
                    for v in confidences)):
            raise ValueError(
                "allocentric prior values must be finite and confidence "
                "must be finite and non-negative")
        if source_indices is None:
            source_indices = [-1] * n
        else:
            source_indices = list(source_indices)
            if len(source_indices) != n:
                raise ValueError(
                    "allocentric prior source indices do not match retina")
        source_epoch = int(source_epoch)

        if (self._last_allocentric_prior is not None
                and self.substrate.has_node(self._last_allocentric_prior)):
            self.substrate.remove_node(self._last_allocentric_prior)
        self._last_allocentric_prior = self.substrate.add_node(
            "AllocentricRetinalPrior", {
                "source_epoch": source_epoch,
                "values": [float(v) for v in values],
                "confidences": [float(v) for v in confidences],
                "present": [bool(v) for v in present],
                "source_indices": [int(v) for v in source_indices],
                "predicted_count": sum(bool(v) for v in present),
            })
        _add_edge(
            self.substrate._inner, self._retina, "has_allocentric_prior",
            self._last_allocentric_prior)

        copied = 0
        for flat, is_present in enumerate(present):
            if not bool(is_present):
                continue
            value = float(values[flat])
            confidence = float(confidences[flat])
            source_index = int(source_indices[flat])
            held = self._held_surface_cells[flat]
            _add_edge(
                self.substrate._inner, self._last_allocentric_prior,
                "predicts_held_surface", held)
            for key, attr_value in {
                    "value": value,
                    "freshness": confidence,
                    "last_refresh_epoch": source_epoch,
                    "epoch": source_epoch,
                    "prior_value": value,
                    "prior_confidence": confidence,
                    "prior_epoch": source_epoch,
                    "prior_source_index": source_index}.items():
                self.substrate.set_attr(held, key, attr_value)
            copied += 1
        return copied

    def _cell_gaze(self, col: int, row: int) -> tuple[float, float]:
        """Return one packed cell's exact physical gaze, never grid inference."""
        col = max(0, min(self.n_az - 1, int(col)))
        row = max(0, min(self.n_el - 1, int(row)))
        if self._layout_explicit:
            record = self._receptor_layout[row * self.n_az + col]
            return float(record["gaze_az"]), float(record["gaze_el"])
        return self._column_az(col), self._row_el(row)

    def update_focus_window_2d(
            self, *, active, center_col, center_row, half_width, half_height,
            source_epoch) -> None:
        """Mechanically copy a graph-issued sensor-allocation command.

        There is deliberately no winner, threshold, fallback or persistence
        logic here.  Those decisions live in ``retinal_focus_control`` on the
        main cognition graph.  This boundary writes the six commanded scalar
        fields onto the eye's graph-resident ``RetinalFocusWindow``.  The Rust
        event-batch primitive reads that node when constructing carve, motion
        and salience tasks.  With ``retinal_focus`` absent at build time this is
        an exact no-op.
        """
        if self._focus_window is None:
            return
        # Seed attrs are allowed to exist with a graph Null before their first
        # verdict.  At the sensor boundary Null means the apparatus's declared
        # inactive/default scalar, never an inferred focus.
        active = 0.0 if active is None else active
        center_col = -1 if center_col is None else center_col
        center_row = -1 if center_row is None else center_row
        half_width = 2 if half_width is None else half_width
        half_height = 2 if half_height is None else half_height
        source_epoch = -1 if source_epoch is None else source_epoch
        values = {
            "active": float(active),
            "center_col": int(center_col),
            "center_row": int(center_row),
            "half_width": max(0, int(half_width)),
            "half_height": max(0, int(half_height)),
            "source_epoch": int(source_epoch),
        }
        for key, value in values.items():
            self.substrate.set_attr(self._focus_window, key, value)
        n = self.n_az * self.n_el
        if values["active"] == 1.0:
            c0 = max(0, values["center_col"] - values["half_width"])
            c1 = min(self.n_az - 1, values["center_col"] + values["half_width"])
            r0 = max(0, values["center_row"] - values["half_height"])
            r1 = min(self.n_el - 1, values["center_row"] + values["half_height"])
            desired = {
                row * self.n_az + col
                for row in range(r0, r1 + 1)
                for col in range(c0, c1 + 1)
            }
        else:
            desired = set(range(n))
        for flat in self._focus_settled_cells - desired:
            self.substrate.remove_edge(
                self._retina, "settles_column", self._cells[flat])
        for flat in desired - self._focus_settled_cells:
            _add_edge(
                self.substrate._inner, self._retina,
                "settles_column", self._cells[flat])
        self._focus_settled_cells = desired

    def submit_photons_2d(
            self, packets, dirty=None, sensor_epoch: int | None = None) -> None:
        """Ingest `{col,row,wavelength_nm,count}` photon packets onto the 2-D
        sheet (mechanical I/O, the 2-D twin of `submit_photons`).

        Every cell gets one `photon_transduce_onset` task per frame (an empty
        packet list is a dark frame — the adapting floor still advances), so the
        onset events carry each cell's own `(col, row, epoch)`.

        `dirty` (block 185000) is the SENSOR'S OWN CHANGE REPORT: an iterable of
        flat cell indices whose input may have changed since the last submission.
        `dirty=None` means "no report" — the full sweep, byte-unchanged. Absence
        of a packet for a cell INSIDE the report still means DARK; the two
        semantics are never conflated. Mechanical I/O; the eye's own work list is
        this report UNIONED with the cells its batch op reported as not-yet-
        settled, and it makes no decision here.
        `sensor_epoch`, when supplied, is the monotonically increasing clock
        minted by the sensor.  This preserves real elapsed sensor time when a
        latest-only transport drops intermediate frames; omitting it retains
        the historical one-epoch-per-call behaviour.
        """
        if sensor_epoch is None:
            self._epoch += 1
        else:
            next_epoch = int(sensor_epoch)
            if next_epoch <= self._epoch:
                raise ValueError(
                    "sensor_epoch must increase strictly and start above zero")
            self._epoch = next_epoch
        grouped: dict = {}
        for packet in packets:
            col = int(packet["col"])
            row = int(packet["row"])
            if not (0 <= col < self.n_az and 0 <= row < self.n_el):
                continue
            wavelength = float(packet["wavelength_nm"])
            count = max(0, int(packet["count"]))
            grouped.setdefault((col, row), []).append((wavelength, count))
        self.substrate.set_attr(self._retina, self._retina_epoch_key, self._epoch)
        # ACCELERATOR (block 184000): when the world opts into the vectorized
        # mirror, the whole per-cell transduce+onset sheet is settled in ONE FFI
        # crossing (no CognitiveTask nodes, no run_rules join) — byte-identical
        # to the graph path below, which stays the correctness oracle when the
        # flag is off (`retina_accel`).
        if self._accel:
            if self._dirty_index:
                self._submit_photons_2d_dirty(grouped, dirty)
            else:
                self._submit_photons_2d_accel(grouped)
            return
        for row in range(self.n_el):
            for col in range(self.n_az):
                flat = row * self.n_az + col
                cell = self._cells[flat]
                self.substrate.set_attr(cell, self._column_epoch_key, self._epoch)
                rod = self._receptors[(flat, "rod")]
                attrs = self.substrate.node(rod)["attrs"]
                payload = [
                    _RECEPTORS["rod"][0], _RECEPTORS["rod"][1],
                    float(attrs.get("adaptation", 0.0)), self.adapt_rate,
                    _RECEPTORS["rod"][2], _RECEPTORS["rod"][3],
                ]
                for wavelength, count in grouped.get((col, row), []):
                    payload.extend([wavelength, count])
                task = self.substrate.add_node("CognitiveTask", {
                    "status": "requested", "kind": "photon_transduce_onset",
                    "payload": payload, "input_epoch": self._epoch,
                    "logical_time": flat, "area": "retina", "order": 0,
                    "salience": 1.0,
                })
                _add_edge(self.substrate._inner, rod, "has_task", task)
                _add_edge(self.substrate._inner, self._area, "has_task", task)

    def _onset_params_2d(self):
        """Read the 2-D onset threshold + refractory as DATA off the graph
        (the same node the `retinal_mint_onset_2d` rule binds). Mechanical."""
        for p in self.substrate.nodes("RetinaOnsetParams2d"):
            a = self.substrate.node(p)["attrs"]
            return (float(a.get("threshold_db", 6.0)),
                    float(a.get("refractory_epochs", 0.0)))
        return 6.0, 0.0

    def _submit_photons_2d_accel(self, grouped) -> None:
        """ACCELERATOR (block 184000): the DROPPABLE, BYTE-IDENTICAL vectorized
        mirror of the per-cell transduce+onset sheet.

        Builds the SAME per-cell `photon_transduce_onset` payload the graph path
        packs (center/bandwidth/adaptation/adapt_rate/half/dark + wavelength/count
        pairs), reading each rod's adaptation in ONE bulk crossing, then hands the
        whole sheet to the Rust `retina_onset_batch` graph op. That op reuses the
        shared kernel VERBATIM and mirrors `photon_apply_receptor_transduction` +
        `retinal_mint_onset_2d` — same rod attrs, same `RetinalOnsetEvent` set —
        in O(cells), with NO CognitiveTask nodes and NO run_rules join. Pure
        mechanical I/O + one batch call; makes no decision."""
        n = self.n_az * self.n_el
        rods = [self._receptors[(f, "rod")] for f in range(n)]
        cols = self._cells
        adapts = self.substrate.get_attr_many(rods, "adaptation")
        center, bandwidth, half, dark = (
            _RECEPTORS["rod"][0], _RECEPTORS["rod"][1],
            _RECEPTORS["rod"][2], _RECEPTORS["rod"][3])
        payloads = []
        for f in range(n):
            row, col = divmod(f, self.n_az)
            a = adapts[f]
            payload = [center, bandwidth,
                       float(a if a is not None else 0.0), self.adapt_rate,
                       half, dark]
            for wavelength, count in grouped.get((col, row), []):
                payload.extend([float(wavelength), float(count)])
            payloads.append(payload)
        threshold_db, refractory = self._onset_params_2d()
        self.substrate._inner.retina_onset_batch(
            [_nid(r) for r in rods], [_nid(c) for c in cols], payloads,
            int(self._epoch), float(threshold_db), float(refractory),
            bool(self._accel_perturb), None, False, None, False,
            bool(self._per_sensor_epoch))

    def _cache_sheet_ids(self):
        """Intern the sheet's rod/column node ids ONCE (they never change).
        Mechanical; keeps the per-tick marshalling O(work list), not O(cells)."""
        if getattr(self, "_rod_nids", None) is None:
            n = self.n_az * self.n_el
            self._rod_nodes = [self._receptors[(f, "rod")] for f in range(n)]
            self._rod_nids = [_nid(r) for r in self._rod_nodes]
            self._col_nids = [_nid(c) for c in self._cells]

    def _submit_photons_2d_dirty(self, grouped, dirty) -> None:
        """DIRTY-INDEX (block 185000): process only the CHANGED cells, so the
        per-tick cost tracks SURPRISE instead of resolution.

        The work list is the sensor's own change report UNIONED with the cells
        the batch op reported as NOT-YET-SETTLED (the eye's per-area dirty
        state). A cell that is unsettled but unreported is re-presented with
        EXACTLY the input the last submission gave it, so its trajectory is the
        one a full sweep would produce. Only the work list's payloads are built,
        marshalled and crossed into Rust — the whole point.

        Pure mechanical I/O: retain last input, union two index sets, build
        payloads, one batch call, store what came back. No decision.
        """
        self._cache_sheet_ids()
        n = self.n_az * self.n_el
        reported = None if dirty is None else {int(f) for f in dirty}
        if self._unsettled is None or reported is None:
            # First submission (or a sensor with no change report): full sweep.
            work = list(range(n))
        elif self._dirty_shed:
            # BRANCH B: the sensor's report ALONE — the not-yet-settled residual
            # of an unreported cell is SHED (declared, measured, never claimed
            # byte-identical).
            work = sorted(reported)
        else:
            # BRANCH A: report ∪ the eye's own not-yet-settled set. A cell is
            # skipped only when re-processing it is a bitwise no-op.
            work = sorted(self._unsettled | reported)
        center, bandwidth, half, dark = (
            _RECEPTORS["rod"][0], _RECEPTORS["rod"][1],
            _RECEPTORS["rod"][2], _RECEPTORS["rod"][3])
        rods = [self._rod_nodes[f] for f in work]
        adapts = self.substrate.get_attr_many(rods, "adaptation")
        payloads = []
        for k, f in enumerate(work):
            row, col = divmod(f, self.n_az)
            if reported is None or f in reported:
                pkts = tuple(grouped.get((col, row), ()))
                self._last_input[f] = pkts
            else:
                pkts = self._last_input.get(f, ())
            a = adapts[k]
            payload = [center, bandwidth,
                       float(a if a is not None else 0.0), self.adapt_rate,
                       half, dark]
            for wavelength, count in pkts:
                payload.extend([float(wavelength), float(count)])
            payloads.append(payload)
        threshold_db, refractory = self._onset_params_2d()
        _minted, unsettled = self.substrate._inner.retina_onset_batch(
            [self._rod_nids[f] for f in work],
            [self._col_nids[f] for f in work],
            payloads, int(self._epoch), float(threshold_db), float(refractory),
            bool(self._accel_perturb),
            [int(f) for f in work], True,
            (list(self._rod_nids) if self._dirty_stamp_epoch else None),
            bool(self._dirty_naive), bool(self._per_sensor_epoch))
        self._unsettled = {int(f) for f in unsettled}
        self._skip_log.append(n - len(work))

    def _settle_event_task(self, *, edge_type, kind, marker_key, dims,
                           sort_mode, prefix, logical_time, order, since_epoch):
        """Build the settle `CognitiveTask` from the onset-event stream.

        GRAPH-NATIVE (block 191000, DEFAULT): hand the whole `RetinalOnsetEvent`
        sweep to ONE Rust op — the event stream never leaves Rust; no per-event
        Python `node(...)["attrs"]` crossing. The op reads `(column_index,
        [row_index,] epoch)` directly off the graph, filters by `since_epoch`,
        sorts by the SAME key the old loop used, packs the payload and MINTS the
        task node + retina edge BYTE-IDENTICALLY to the Python path (verified by
        the gate). `event_native=False` runs the old loop below — the oracle.
        This is pure mechanical I/O: it packs a payload, makes no decision.
        """
        inner = self.substrate._inner
        if self._event_native:
            se = None if since_epoch is None else float(since_epoch)
            return inner.retina_event_task_batch(
                _nid(self._retina), edge_type, kind, marker_key,
                int(dims), int(sort_mode), [float(p) for p in prefix],
                int(self._epoch), int(logical_time), int(order), se,
                bool(self._event_perturb))
        # --- OLD Python per-event loop (the byte-identity ORACLE) ---
        events = []
        for node in self.substrate.nodes("RetinalOnsetEvent"):
            attrs = self.substrate.node(node)["attrs"]
            epoch = float(attrs["epoch"])
            if since_epoch is not None and epoch < float(since_epoch):
                continue
            if dims == 3:
                events.append((float(attrs["column_index"]),
                               float(attrs.get("row_index", 0.0)), epoch))
            else:
                events.append((float(attrs["column_index"]), epoch))
        pathway = str(self.context.get("event_pathway", "all"))
        if self._layout_explicit and pathway in ("fovea", "periphery"):
            def in_pathway(event):
                col = int(event[0])
                row = int(event[1]) if dims == 3 else 0
                record = self._receptor_layout[row * self.n_az + col]
                is_fovea = record["pathway"] == "fovea"
                return is_fovea if pathway == "fovea" else not is_fovea
            events = [event for event in events if in_pathway(event)]
        if dims == 3:
            events.sort(key=(lambda cre: (cre[1], cre[0], cre[2]))
                        if sort_mode == 0 else
                        (lambda cre: (cre[2], cre[1], cre[0])))
        else:
            events.sort(key=(lambda ce: (ce[0], ce[1]))
                        if sort_mode == 0 else
                        (lambda ce: (ce[1], ce[0])))
        payload = [float(p) for p in prefix] + [float(len(events))]
        for ev in events:
            payload.extend(ev)
        task = self.substrate.add_node("CognitiveTask", {
            "status": "requested", "kind": kind,
            "payload": payload, "input_epoch": self._epoch,
            "logical_time": logical_time,
            "area": "retina", "order": order, "salience": 1.0,
            marker_key: 1.0,
        })
        _add_edge(inner, self._retina, edge_type, task)
        return task

    def settle_carve_2d(self, since_epoch=None):
        """Settle the async 2-D COMMON-FATE CARVE from the onset-event stream.

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s (`column_index`,
        `row_index`, `epoch`) — the async EVENT STREAM, and nothing from any
        raster or frame — serialise them into one `retinal_common_fate_carve_2d`
        CognitiveTask (prefixed with `n_az`, `n_el`, and the two segmentation
        params read as DATA off `RetinaCarveParams2d`), and link it so the
        `retinal_mint_carve_2d` rule can bind it. The DECISION (which cells group
        into which VisionPolygon) is the Rust kernel + the graph rule; this method
        packs a payload, makes no decision. Returns the task node id, or None when
        the 2-D path is off.
        """
        if not self._retina_2d:
            return None
        max_gap, vel_tol = 1.0, 0.35
        for pnode in self.substrate.nodes("RetinaCarveParams2d"):
            pa = self.substrate.node(pnode)["attrs"]
            max_gap = float(pa.get("max_gap", 1.0))
            vel_tol = float(pa.get("vel_tol", 0.35))
            break
        return self._settle_event_task(
            edge_type="has_carve_task_2d", kind="retinal_common_fate_carve_2d",
            marker_key="retinal_carve_event_2d", dims=3, sort_mode=0,
            prefix=[self.n_az, self.n_el, max_gap, vel_tol],
            logical_time=self.n_az * self.n_el + 4, order=3,
            since_epoch=since_epoch)

    def carve_polygons_2d(self):
        """Read minted 2-D `VisionPolygon`s back out (mechanical emit).

        Each polygon carries its azimuth span (`col_min`/`col_max`) AND its
        elevation span (`row_min`/`row_max`), mapped to gaze angles; sorted by
        (row_min, col_min)."""
        out = []
        for node in self.substrate.nodes("VisionPolygon"):
            attrs = self.substrate.node(node)["attrs"]
            col_min = int(attrs.get("col_min", 0))
            col_max = int(attrs.get("col_max", 0))
            row_min = int(attrs.get("row_min", 0))
            row_max = int(attrs.get("row_max", 0))
            out.append({
                "col_min": col_min, "col_max": col_max,
                "row_min": row_min, "row_max": row_max,
                "az_min": self._column_az(col_min),
                "az_max": self._column_az(col_max),
                "el_min": self._row_el(row_min),
                "el_max": self._row_el(row_max),
                "direction": float(attrs.get("direction", 0.0)),
                "speed": float(attrs.get("speed", 0.0)),
                "coherence": float(attrs.get("coherence", 0.0)),
                "n_events": int(attrs.get("n_events", 0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        out.sort(key=lambda p: (p["row_min"], p["col_min"]))
        return out

    def _row_el(self, index: int) -> float:
        i = max(0, min(self.n_el - 1, int(index)))
        return math.radians(
            -self.fov_v_deg / 2 + self.fov_v_deg * (i + 0.5) / self.n_el)

    def settle_motion_2d(self, since_epoch=None):
        """Settle async 2-D MOTION from the onset-event stream (2-D expansion of
        Rung 2 — CLOSING THE 2-D LOOP).

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s (`column_index`,
        `row_index`, `epoch`) — the async EVENT STREAM, nothing from any raster
        or frame — serialise them into one `retinal_event_motion_2d` CognitiveTask
        and link it so the `retinal_mint_motion_2d` rule can bind it. The DECISION
        (v_az / v_el / coherence / residual) is the Rust kernel + the graph rule;
        this method packs a payload, makes no decision. Returns the task node id,
        or None when the 2-D motion path is off.

        `since_epoch` is the host-supplied observation WINDOW (same framing as the
        1-D `settle_motion`): I/O framing, not a decision over graph state.
        """
        if not (self._retina_2d and self._motion_enabled):
            return None
        return self._settle_event_task(
            edge_type="has_motion_task_2d", kind="retinal_event_motion_2d",
            marker_key="retinal_motion_event_2d", dims=3, sort_mode=1,
            prefix=[], logical_time=self.n_az * self.n_el + 5, order=2,
            since_epoch=since_epoch)

    def motion_percepts_2d(self):
        """Read minted 2-D `RetinalMotionPercept`s back out (mechanical emit).

        Each carries the recovered 2-D velocity (`v_az`, `v_el`), its azimuth
        `direction`, `speed` (2-D norm), `residual`, and `coherence`."""
        out = []
        for node in self.substrate.nodes("RetinalMotionPercept"):
            attrs = self.substrate.node(node)["attrs"]
            if "v_az" not in attrs:      # a 1-D percept — skip in 2-D readout
                continue
            out.append({
                "v_az": float(attrs.get("v_az", 0.0)),
                "v_el": float(attrs.get("v_el", 0.0)),
                "direction": float(attrs.get("direction", 0.0)),
                "direction_el": float(attrs.get("direction_el", 0.0)),
                "speed": float(attrs.get("speed", 0.0)),
                "residual": float(attrs.get("residual", 0.0)),
                "coherence": float(attrs.get("coherence", 0.0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        return out

    def settle_salience_2d(self, since_epoch=None):
        """Settle PER-AREA RESIDUAL SALIENCE on the 2-D az×el field from the
        onset-event stream (2-D expansion of Rung 4 — CLOSING THE 2-D LOOP).

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s (`column_index`,
        `row_index`, `epoch`) — the async EVENT STREAM — serialise them into one
        `retinal_residual_salience_2d` CognitiveTask (prefixed with `n_az`,
        `n_el`, and the two segmentation params read as DATA off
        `RetinaSalienceParams2d`), and link it so the `retinal_mint_salience_2d`
        rule can bind it. The DECISION (which cell is surprising — its 2-D
        velocity's departure from the dominant common-fate motion) is the Rust
        kernel + the graph rule; this method makes no decision. Returns the task
        node id, or None when the 2-D salience path is off.
        """
        if not (self._retina_2d and self._salience_enabled):
            return None
        max_gap, vel_tol = 1.0, 0.35
        for pnode in self.substrate.nodes("RetinaSalienceParams2d"):
            pa = self.substrate.node(pnode)["attrs"]
            max_gap = float(pa.get("max_gap", 1.0))
            vel_tol = float(pa.get("vel_tol", 0.35))
            break
        return self._settle_event_task(
            edge_type="has_salience_task_2d",
            kind="retinal_residual_salience_2d",
            marker_key="retinal_salience_event_2d", dims=3, sort_mode=0,
            prefix=[self.n_az, self.n_el, max_gap, vel_tol],
            logical_time=self.n_az * self.n_el + 6, order=4,
            since_epoch=since_epoch)

    def salience_percepts_2d(self):
        """Read minted 2-D `RetinalSalience` nodes back out (mechanical emit).

        Each carries the firing cell's `(column_index, row_index)`, its
        `raw_salience` (its own 2-D common-fate speed) and `residual_salience`
        (its 2-D vector departure from the dominant motion — the surprise).
        Sorted by (row_index, column_index)."""
        out = []
        for node in self.substrate.nodes("RetinalSalience"):
            attrs = self.substrate.node(node)["attrs"]
            if "row_index" not in attrs:   # a 1-D salience — skip in 2-D readout
                continue
            col = int(attrs.get("column_index", 0))
            row = int(attrs.get("row_index", 0))
            flat = row * self.n_az + col
            gaze_az, gaze_el = self._cell_gaze(col, row)
            geometry = (
                self._receptor_layout[flat] if self._layout_explicit else None)
            out.append({
                "column_index": col,
                "row_index": row,
                "cell_index": flat,
                "gaze_az": gaze_az,
                "gaze_el": gaze_el,
                "eye_id": (
                    str(geometry["eye_id"]) if geometry else "cyclopean"),
                "pathway": (
                    str(geometry["pathway"]) if geometry else "uniform"),
                "raw_salience": float(attrs.get("raw_salience", 0.0)),
                "residual_salience": float(attrs.get("residual_salience", 0.0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        out.sort(key=lambda s: (s["row_index"], s["column_index"]))
        return out

    def held_prediction_residuals_2d(self):
        """Read every 2-D held-surface prediction residual (mechanical emit).

        The held predictor's graph rules own ``residual`` and ``freshness``.
        This method performs no threshold, ranking, or top-k: when the optional
        held-prediction apparatus exists it copies all receptor cells, retaining
        the predictor's photon-count/luminance-quanta unit explicitly.  A main
        cognition graph can then admit and resolve the evidence with its own
        rules without conflating it with motion salience's cells/epoch unit.
        """
        out = []
        for node in self._held_surface_cells:
            if not self.substrate.has_node(node):
                continue
            attrs = self.substrate.node(node)["attrs"]
            col = int(attrs.get("col", 0))
            row = int(attrs.get("row", 0))
            gaze_az, gaze_el = self._cell_gaze(col, row)
            out.append({
                "column_index": col,
                "row_index": row,
                "cell_index": int(attrs.get("cell_index", 0)),
                "gaze_az": float(attrs.get("gaze_az", gaze_az)),
                "gaze_el": float(attrs.get("gaze_el", gaze_el)),
                "eye_id": attrs.get("eye_id", "cyclopean"),
                "pathway": attrs.get("pathway", "uniform"),
                "prediction_epoch": int(attrs.get("epoch", 0)),
                "prediction_residual_quanta": int(attrs.get("residual", 0)),
                "observed_quanta": float(attrs.get("obs", 0.0)),
                "held_value_quanta": float(attrs.get("value", 0.0)),
                "freshness_scale2": int(attrs.get("freshness", 0)),
                "needs_attention": int(attrs.get("needs_attention", 0)),
            })
        out.sort(key=lambda s: (s["row_index"], s["column_index"]))
        return out

    def kernels(self) -> dict[str, Any]:
        """Compatibility query: receptor populations replace fixed kernels."""
        if self._retina_2d:
            return {
                "rod": [
                    self._receptors[(i, "rod")]
                    for i in range(self.n_az * self.n_el)
                ]
            }
        return {
            receptor_class: [
                self._receptors[(i, receptor_class)] for i in range(self.n_az)
            ]
            for receptor_class in _RECEPTORS
        }

    def submit_photons(self, packets, posture_deg: float = 0.0,
                       retinal_field=None, field_shape=None) -> None:
        """Ingest `{column,wavelength_nm,count}` photon packets."""
        self._epoch += 1
        grouped = {i: [] for i in range(self.n_az)}
        flat_packets = []
        for packet in packets:
            column = int(packet["column"])
            if not 0 <= column < self.n_az:
                continue
            wavelength = float(packet["wavelength_nm"])
            count = max(0, int(packet["count"]))
            grouped[column].append((wavelength, count))
            flat_packets.extend([column, wavelength, count])

        if self._last_exposure is not None and self.substrate.has_node(self._last_exposure):
            self.substrate.remove_node(self._last_exposure)
        self._last_exposure = self.substrate.add_node("PhotonExposure", {
            "input_epoch": self._epoch,
            "packets": flat_packets,
            "total_quanta": sum(p[1] for ps in grouped.values() for p in ps),
            "retinal_field": list(retinal_field or []),
            "field_h": int(field_shape[0]) if field_shape else 0,
            "field_w": int(field_shape[1]) if field_shape else 0,
        })
        _add_edge(self.substrate._inner, self._retina, "has_exposure", self._last_exposure)
        self.substrate.set_attr(self._retina, "input_epoch", self._epoch)

        for index, column in enumerate(self._columns):
            self.substrate.set_attr(column, "input_epoch", self._epoch)
            self.substrate.set_attr(column, "posture_deg", float(posture_deg))
            for receptor_class, params in _RECEPTORS.items():
                receptor = self._receptors[(index, receptor_class)]
                attrs = self.substrate.node(receptor)["attrs"]
                payload = [
                    params[0], params[1], float(attrs.get("adaptation", 0.0)),
                    self.adapt_rate, params[2], params[3],
                ]
                for wavelength, count in grouped[index]:
                    payload.extend([wavelength, count])
                task = self.substrate.add_node("CognitiveTask", {
                    "status": "requested", "kind": self._onset_kind,
                    "payload": payload, "input_epoch": self._epoch,
                    "logical_time": index * len(_RECEPTORS)
                                    + list(_RECEPTORS).index(receptor_class),
                    "area": "retina", "order": 0, "salience": 1.0,
                })
                _add_edge(self.substrate._inner, receptor, "has_task", task)
                _add_edge(self.substrate._inner, self._area, "has_task", task)

        if (retinal_field is not None and field_shape is not None
                and self._previous_field is not None
                and self._field_shape == tuple(field_shape)):
            payload = [
                int(field_shape[0]), int(field_shape[1]),
                float(self.context.get("efference_translation", 0.0)),
                int(self.context.get("flow_max_shift", 4)),
            ]
            payload.extend(float(v) for v in self._previous_field)
            payload.extend(float(v) for v in retinal_field)
            motion = self.substrate.add_node("CognitiveTask", {
                "status": "requested", "kind": "retinal_flow_depth",
                "payload": payload, "input_epoch": self._epoch,
                "logical_time": self.n_az * len(_RECEPTORS),
                "area": "retina", "order": 1, "salience": 1.0,
                "retinal_motion": 1.0,
            })
            _add_edge(self.substrate._inner, self._area, "has_task", motion)
        if retinal_field is not None and field_shape is not None:
            self._previous_field = list(retinal_field)
            self._field_shape = tuple(field_shape)

    def settle_motion(self, since_epoch=None):
        """Settle async motion from the held onset-event stream (Rung 2).

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s
        (`column_index`, `epoch`) — the async EVENT STREAM, and nothing from the
        coarse raster or any frame — serialise them into one
        `retinal_event_motion` CognitiveTask, and link it to the retina so the
        `retinal_mint_motion` rule can bind it. The DECISION (direction / speed /
        coherence / residual) is the Rust kernel + the graph rule; this method
        makes no decision — it packs a payload, exactly as `submit_photons`
        packs the flow payload. Returns the task node id, or None when the motion
        path is off. The caller drives `run_cognitive_tasks` + `run_rules` to
        mint the `RetinalMotionPercept`.

        `since_epoch` is the host-supplied observation WINDOW: with it set, only
        events at `epoch >= since_epoch` are settled (the current window's event
        cloud), the async twin of the on-clock-frame-window framing. It is I/O
        framing, not a decision over graph state — the kernel is fed exactly the
        events the host declares in view this settle.
        """
        if not self._motion_enabled:
            return None
        return self._settle_event_task(
            edge_type="has_motion_task", kind="retinal_event_motion",
            marker_key="retinal_motion_event", dims=2, sort_mode=1,
            prefix=[], logical_time=self.n_az * len(_RECEPTORS) + 1, order=2,
            since_epoch=since_epoch)

    def motion_percepts(self):
        """Read minted `RetinalMotionPercept`s back out (mechanical emit)."""
        out = []
        for node in self.substrate.nodes("RetinalMotionPercept"):
            attrs = self.substrate.node(node)["attrs"]
            out.append({
                "direction": float(attrs.get("direction", 0.0)),
                "speed": float(attrs.get("speed", 0.0)),
                "residual": float(attrs.get("residual", 0.0)),
                "coherence": float(attrs.get("coherence", 0.0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        return out

    def settle_carve(self, since_epoch=None):
        """Settle the async COMMON-FATE CARVE from the onset-event stream (Rung 3).

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s
        (`column_index`, `epoch`) — the async EVENT STREAM, and nothing from the
        coarse raster or any frame — serialise them into one
        `retinal_common_fate_carve` CognitiveTask (prefixed with the retina width
        and the two segmentation params read as DATA off the `RetinaCarveParams`
        node), and link it to the retina so the `retinal_mint_carve` rule can
        bind it. The DECISION (which columns group into which VisionPolygon) is
        the Rust kernel + the graph rule; this method makes no decision — it
        packs a payload, exactly as `settle_motion` packs the event stream.
        Returns the task node id, or None when the carve path is off. The caller
        drives `run_cognitive_tasks` + `run_rules` to mint the `VisionPolygon`s.

        `since_epoch` is the host-supplied observation WINDOW (same framing as
        `settle_motion`): with it set, only events at `epoch >= since_epoch` are
        settled — I/O framing, not a decision over graph state.
        """
        if not self._carve_enabled:
            return None
        max_gap, vel_tol = 1.0, 0.35
        for pnode in self.substrate.nodes("RetinaCarveParams"):
            pa = self.substrate.node(pnode)["attrs"]
            max_gap = float(pa.get("max_gap", 1.0))
            vel_tol = float(pa.get("vel_tol", 0.35))
            break
        return self._settle_event_task(
            edge_type="has_carve_task", kind="retinal_common_fate_carve",
            marker_key="retinal_carve_event", dims=2, sort_mode=0,
            prefix=[self.n_az, max_gap, vel_tol],
            logical_time=self.n_az * len(_RECEPTORS) + 2, order=3,
            since_epoch=since_epoch)

    def carve_polygons(self):
        """Read minted `VisionPolygon`s back out (mechanical emit).

        Maps each polygon's column span (`col_min`/`col_max`) to the retina's
        azimuth angles for the outside world — a pure graph query."""
        out = []
        for node in self.substrate.nodes("VisionPolygon"):
            attrs = self.substrate.node(node)["attrs"]
            col_min = int(attrs.get("col_min", 0))
            col_max = int(attrs.get("col_max", 0))
            out.append({
                "col_min": col_min,
                "col_max": col_max,
                "az_min": self._column_az(col_min),
                "az_max": self._column_az(col_max),
                "direction": float(attrs.get("direction", 0.0)),
                "speed": float(attrs.get("speed", 0.0)),
                "coherence": float(attrs.get("coherence", 0.0)),
                "n_events": int(attrs.get("n_events", 0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        out.sort(key=lambda p: p["col_min"])
        return out

    def settle_salience(self, since_epoch=None):
        """Settle PER-AREA RESIDUAL SALIENCE from the onset-event stream (Rung 4).

        Mechanical I/O ONLY: read every `RetinalOnsetEvent`'s
        (`column_index`, `epoch`) — the async EVENT STREAM, and nothing from the
        coarse raster or any frame or any raster salience — serialise them into
        one `retinal_residual_salience` CognitiveTask (prefixed with the retina
        width and the two common-fate segmentation params read as DATA off the
        `RetinaSalienceParams` node), and link it to the retina so the
        `retinal_mint_salience` rule can bind it. The DECISION (which column is
        surprising — its residual against the dominant common-fate motion) is the
        Rust kernel + the graph rule; this method makes no decision — it packs a
        payload, exactly as `settle_carve` packs the event stream. Returns the
        task node id, or None when the salience path is off. The caller drives
        `run_cognitive_tasks` + `run_rules` to mint the `RetinalSalience` nodes.

        `since_epoch` is the host-supplied observation WINDOW (same framing as
        `settle_carve`): with it set, only events at `epoch >= since_epoch` are
        settled — I/O framing, not a decision over graph state.
        """
        if not self._salience_enabled:
            return None
        max_gap, vel_tol = 1.0, 0.35
        for pnode in self.substrate.nodes("RetinaSalienceParams"):
            pa = self.substrate.node(pnode)["attrs"]
            max_gap = float(pa.get("max_gap", 1.0))
            vel_tol = float(pa.get("vel_tol", 0.35))
            break
        return self._settle_event_task(
            edge_type="has_salience_task", kind="retinal_residual_salience",
            marker_key="retinal_salience_event", dims=2, sort_mode=0,
            prefix=[self.n_az, max_gap, vel_tol],
            logical_time=self.n_az * len(_RECEPTORS) + 3, order=4,
            since_epoch=since_epoch)

    def salience_percepts(self):
        """Read minted `RetinalSalience` nodes back out (mechanical emit).

        Each node carries the firing column's `raw_salience` (its own
        common-fate speed) and `residual_salience` (its departure from the
        dominant common-fate motion — the surprise). A pure graph query the
        fovea can consume; sorted by column."""
        out = []
        for node in self.substrate.nodes("RetinalSalience"):
            attrs = self.substrate.node(node)["attrs"]
            out.append({
                "column_index": int(attrs.get("column_index", 0)),
                "raw_salience": float(attrs.get("raw_salience", 0.0)),
                "residual_salience": float(attrs.get("residual_salience", 0.0)),
                "epoch": int(attrs.get("epoch", 0)),
            })
        out.sort(key=lambda s: s["column_index"])
        return out

    def _column_az(self, index: int) -> float:
        i = max(0, min(self.n_az - 1, int(index)))
        return math.radians(
            -self.fov_h_deg / 2 + self.fov_h_deg * (i + 0.5) / self.n_az)

    def submit(self, depth=None, screen=None, posture_deg: float = 0.0) -> None:
        """Compatibility boundary: integrate RGB radiance into photon packets.

        `depth` is deliberately ignored: a range buffer is not light.
        """
        if screen is not None:
            packets, field, shape = self._rgb_to_photons(screen)
        else:
            packets, field, shape = [], None, None
        self.submit_photons(
            packets, posture_deg=posture_deg,
            retinal_field=field, field_shape=shape)

    def _rgb_to_photons(self, screen):
        arr = np.asarray(screen)
        if arr.ndim == 3 and arr.shape[0] == 3:
            arr = np.transpose(arr, (1, 2, 0))
        if arr.ndim != 3 or arr.shape[2] < 3:
            return [], None, None
        h = arr.shape[0]
        band_h = max(1, int(round(h * self.vband)))
        r0 = max(0, (h - band_h) // 2)
        band = arr[r0:r0 + band_h, :, :3].astype(np.float64)
        exposure = float(self.context.get("exposure_quanta", 1024.0))
        packets = []
        for index in range(self.n_az):
            c0 = int(index * band.shape[1] / self.n_az)
            c1 = max(c0 + 1, int((index + 1) * band.shape[1] / self.n_az))
            rgb = band[:, c0:c1].mean(axis=(0, 1)) / 255.0
            for wavelength, fraction in zip((610.0, 550.0, 460.0), rgb):
                packets.append({
                    "column": index,
                    "wavelength_nm": wavelength,
                    "count": int(round(max(0.0, fraction) * exposure)),
                })
        rh = max(2, int(self.context.get("retina_h", 12)))
        rw = max(2, int(self.context.get("retina_w", self.n_az)))
        gray = band.mean(axis=2)
        field = []
        for ry in range(rh):
            y0 = int(ry * gray.shape[0] / rh)
            y1 = max(y0 + 1, int((ry + 1) * gray.shape[0] / rh))
            for rx in range(rw):
                x0 = int(rx * gray.shape[1] / rw)
                x1 = max(x0 + 1, int((rx + 1) * gray.shape[1] / rw))
                field.append(float(gray[y0:y1, x0:x1].mean()))
        return packets, field, (rh, rw)

    def _read_snapshot(self, epoch: int) -> dict:
        percepts = []
        for column, percept in zip(self._columns, self._percepts):
            ca = self.substrate.node(column)["attrs"]
            pa = self.substrate.node(percept)["attrs"]
            az = float(ca["gaze_az"])
            posture = math.radians(float(ca.get("posture_deg", 0.0)))
            world = posture + az
            percepts.append({
                "gaze_az": az,
                "world_dir": (math.cos(world), math.sin(world)),
                "intensity": float(pa.get("intensity", 0.0)),
                "red_green": float(pa.get("red_green", 0.0)),
                "blue_yellow": float(pa.get("blue_yellow", 0.0)),
                "salience": float(pa.get("salience", 0.0)),
                "distance": None,
                "sensor": "photon_retina",
            })
        motion_depths = []
        for task in self.substrate.nodes("CognitiveTask"):
            attrs = self.substrate.node(task)["attrs"]
            if (attrs.get("retinal_motion") == 1.0
                    and int(attrs.get("input_epoch", 0)) == epoch
                    and attrs.get("status") == "done"):
                values = list(attrs.get("output") or [])
                motion_depths = [
                    (values[i], values[i + 1])
                    for i in range(0, len(values) - 1, 2)
                    if values[i + 1] > 0
                ]
                break
        # Rung 3: read the minted VisionPolygon nodes (the async common-fate
        # carve) back out. Empty when the carve path is off (no rule fires) —
        # byte-identical to the pre-Rung-3 `"polygons": []`.
        polygons = self.carve_polygons() if self._carve_enabled else []
        return {
            "percepts": percepts, "polygons": polygons,
            "motion_depths": motion_depths,
            "sensor_epoch": epoch,
        }

    def latest(self):
        self._refresh_settled()
        return self._snapshot

    def processed_count(self) -> int:
        self._refresh_settled()
        return self._processed

    def stop(self, join_timeout: float = 1.0) -> None:
        if self._owns_agent_loop and self.substrate.agent_running():
            self.substrate.stop_agent(timeout=join_timeout)
        self._owns_agent_loop = False

    def prune_settled_tasks(self) -> int:
        """Prune settled/done retina CognitiveTask nodes (mechanical host I/O).

        THE SETTLEMENT AXIOM MADE CONCRETE: a settled task whose output is
        already written and will not be read again is an UNCLEARED RESIDUAL.
        Left in the graph it re-enters every `run_rules` match — the onset rule
        joins retina -> column -> rod -> has_task -> task, so an un-pruned task
        on a rod is re-examined on every tick — and per-tick cost grows with the
        accumulated task count (the diagnosed quadratic, block 182000). Removing
        the done/failed/stale/superseded/shed retina tasks each tick keeps that
        cost flat (~linear in cells instead of ~quadratic).

        This is PURE graph housekeeping: it removes only tasks the engine has
        already finished with (a terminal `status`), publishes nothing, decides
        nothing, and changes no percept / polygon / motion / salience output —
        those are minted into their OWN node types (RetinalPercept /
        VisionPolygon / RetinalOnsetEvent / ...) by `run_rules` BEFORE the task
        reaches a terminal status, and persist independently of the task. It is
        2-D-safe: unlike the 1-D `_refresh_settled` epoch gate it does not read
        `self._percepts` (empty on the 2-D sheet), so it is the prune the 2-D
        carve/measure scaling path uses. Returns the count removed.
        """
        removed = 0
        for task in list(self.substrate.nodes("CognitiveTask")):
            attrs = self.substrate.node(task)["attrs"]
            if (attrs.get("area") == "retina"
                    and attrs.get("status") in (
                        "done", "failed", "stale", "superseded", "shed")):
                self.substrate.remove_node(task)
                removed += 1
        return removed

    def _refresh_settled(self) -> None:
        """Publish only a complete retinal epoch; never a half-folded column set."""
        if self._retina_2d:
            # The 2-D sheet has no RetinalPercept epoch clock (`self._percepts`
            # is empty), so the 1-D "publish a complete epoch" gate below never
            # applies to it. On the 2-D scaling path the settle step is pure
            # task-pruning: clear finished retina tasks so they stop re-entering
            # run_rules. No snapshot is published and `_processed` is not
            # advanced (2-D consumers read carve_polygons_2d / motion_percepts_2d
            # / salience_percepts_2d directly), so this is BYTE-IDENTICAL to the
            # prior early-return for every 2-D output — it only removes settled
            # residue that would otherwise accumulate quadratically.
            self.prune_settled_tasks()
            return
        epochs = [
            int(self.substrate.node(percept)["attrs"].get("input_epoch", -1))
            for percept in self._percepts
        ]
        if not epochs or min(epochs) != max(epochs):
            return
        settled = epochs[0]
        if settled <= self._settled_epoch:
            return
        self._snapshot = self._read_snapshot(settled)
        self._settled_epoch = settled
        self._processed += 1
        for task in list(self.substrate.nodes("CognitiveTask")):
            attrs = self.substrate.node(task)["attrs"]
            if (attrs.get("area") == "retina"
                    and int(attrs.get("input_epoch", 0)) <= settled
                    and attrs.get("status") in (
                        "done", "failed", "stale", "superseded", "shed")):
                self.substrate.remove_node(task)
