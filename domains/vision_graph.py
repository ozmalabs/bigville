"""RGBEye — DEPRECATED fixed-kernel RGB/depth visual apparatus.

A migration of :mod:`domains.vision`'s Eye onto the substrate's
graph-resident kernel primitives (:mod:`substrate_rs.vision`). Same
submit/latest API and percept/polygon
snapshot shape — but every convolution-shaped kernel is now a
:data:`Kernel` NODE in the agent's substrate. The agent OWNS its
receptive fields as graph data: it can read them, edit them, count
them, ask the DSL about them, all via :func:`Attr` on the kernel
nodes.

What's lifted to graph nodes
----------------------------
* **Sobel x / Sobel y** — V1 horizontal / vertical edge gradients.
  The convolve math runs in the Rust ``ChangeDetect`` Term, which
  reads the kernel weights via ``Attr(k, "weights")`` directly off
  the graph-resident Kernel node — no Python/cv2 filter2D, no numpy
  weight cache. The agent edits a kernel node; the next frame sees
  the new weights live.
* **DoG salience** — LGN-shape center-surround on the colour channels
  (the original used cv2.GaussianBlur(σ=2) − cv2.GaussianBlur(σ=16);
  the module stores those two Gaussians AS Kernel nodes with their
  σ on the attrs, so the worker can use the fast separable-blur path
  while the agent sees the canonical receptive field). The σ is read
  live from the kernel node's ``name`` attr each frame.

What stays as opaque cv2 calls
------------------------------
* **Harris corners** — not a single static-matrix convolution; cv2
  decomposes it into autocorrelation matrices internally. Future
  work could express it as a graph-resident derivation; for now it
  stays as ``cv2.cornerHarris``.
* **Contour finding** — fundamentally an iterative algorithm on a
  thresholded edge map (find connected regions, walk boundaries).
  Not a kernel; stays as ``cv2.findContours``.
* **GaussianBlur (salience DoG)** — a separable blur parameterised by
  σ, not a fixed-kernel filter2D. The Gaussian kernel NODE for σ=16
  is ~97×97 — larger than a typical frame, so it cannot run through
  ``ChangeDetect`` (valid cross-correlation needs kernel ≤ image).
  The σ is graph-resident (on the kernel node's name); the fast
  separable-blur arithmetic stays cv2. (Moving it to a Rust separable
  Term is a named future step, out of S1.0 scope.)

Concurrency
-----------
GraphEye owns no worker thread. It emits generic ``CognitiveTask`` nodes for
independent receptive-field work; the native cognitive runtime executes them
on its generic worker capacity and folds results deterministically. One worker
and many workers produce the same percept.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

import substrate_rs as srs
from substrate_rs import vision as v
from substrate_rs import Attr, Lit, Vec, Term


# Node-type constants for the percept / polygon emissions if a caller
# wants to mirror them into another substrate's graph (matches the
# constants the original :mod:`domains.vision` exported).
PERCEPT = "VisionPercept"
POLYGON = "VisionPolygon"


@dataclass
class RGBEye:
    """Deprecated RGB/pixel visual apparatus with graph-resident receptive
    fields. Drop-in replacement for :class:`domains.vision.Eye`.

    The only API additions vs Eye are :meth:`kernels` (returns the
    NodeIDs of the graph-resident receptive fields) and
    :meth:`refresh_kernels` (re-snapshot weights from the substrate
    after the agent edits them). All other methods — ``build``,
    ``submit``, ``latest``, ``processed_count``, ``stop`` —
    behave identically.
    """

    # Optional — when None, GraphEye creates its own fresh Substrate
    # at build time. Lets callers (e.g. CuriousAgent) opt into
    # graph-resident kernels without explicitly minting a substrate
    # themselves.
    substrate: srs.Substrate | None = None
    n_az: int = 32
    fov_h_deg: float = 90.0
    vband: float = 0.34
    depth_scale: float = 1.0
    edge_thresh: float = 40.0
    min_area: float = 80.0
    # Optional namespace prefix for vision-type names — useful when
    # this Eye shares a substrate with other domains that might
    # already have an "Image" type.
    namespace: str | None = None
    # Salience DoG sigmas. Match the original Eye's choice.
    salience_sigma_center: float = 2.0
    salience_sigma_surround: float = 16.0
    # CONTEXT HINT — the world tells the eye what KIND of scene it is looking at,
    # so the same cortex picks the right front-end. Camera/depth frames (Doom,
    # jellyfin) want contour-on-luminance (edges in natural light). A DISCRETE
    # GRID (ARC) has no useful luminance edges — its figures ARE exact connected
    # colour components — so on a "grid" hint the eye extracts those directly
    # (no edge-tracing, nothing dropped). ``cell_px`` lets it size the area floor
    # to the grid's own scale instead of a camera-pixel default.
    context: dict = field(default_factory=dict)

    # --- graph-resident kernels (NodeIDs in the substrate) ---
    _sobel_x_nid: Any = field(default=None, init=False, repr=False)
    _sobel_y_nid: Any = field(default=None, init=False, repr=False)
    _gauss_center_nid: Any = field(default=None, init=False, repr=False)
    _gauss_surround_nid: Any = field(default=None, init=False, repr=False)

    # --- ordinary Eye plumbing ---
    _gaze: list = field(default_factory=list, init=False, repr=False)
    _latest_frame: object = field(default=None, init=False, repr=False)
    _snapshot: object = field(default=None, init=False, repr=False)
    _next_id: int = field(default=0, init=False, repr=False)
    _last_id: int = field(default=-1, init=False, repr=False)
    _processed: int = field(default=0, init=False, repr=False)

    __deprecated__ = True
    deprecation_reason = (
        "fixed RGB/depth arrays + hand-authored Sobel/DoG/cv2; "
        "use domains.photon_eye.GraphEye"
    )

    def build(self) -> "RGBEye":
        """Seed the vision grammar, mint the receptive-field nodes,
        prepare the generic cognitive-task surface.

        If no substrate was provided, mint a fresh one — callers who
        don't care about cross-domain integration get a clean
        vision-only substrate they can introspect via
        :meth:`kernels`."""
        if self.substrate is None:
            self.substrate = srs.Substrate()
        v.seed_vision_grammar(self.substrate, namespace=self.namespace)

        # The four canonical receptive fields — biology-named,
        # graph-resident, agent-introspectable.
        self._sobel_x_nid = self._namespace_kernel(
            v.sobel(self.substrate, dx=1, dy=0, ksize=3))
        self._sobel_y_nid = self._namespace_kernel(
            v.sobel(self.substrate, dx=0, dy=1, ksize=3))
        # Salience DoG: center σ and surround σ. We store them as two
        # separate Gaussian kernels (rather than a single 97×97 DoG)
        # so the worker can use the fast cv2 separable-blur path with
        # the σ value directly. The graph still carries the canonical
        # Gaussian representation for introspection.
        self._gauss_center_nid = self._namespace_kernel(v.gaussian(
            self.substrate, sigma=self.salience_sigma_center))
        self._gauss_surround_nid = self._namespace_kernel(v.gaussian(
            self.substrate, sigma=self.salience_sigma_surround))
        # Decorate them with their salience role so the agent's
        # introspection can find them by purpose.
        self.substrate.set_attr(self._gauss_center_nid, "role", "salience_center")
        self.substrate.set_attr(self._gauss_surround_nid, "role", "salience_surround")
        self.substrate.set_attr(self._sobel_x_nid, "role", "v1_edge_x")
        self.substrate.set_attr(self._sobel_y_nid, "role", "v1_edge_y")

        self._build_gaze()
        return self

    def _namespace_kernel(self, nid):
        """If this Eye uses a namespace, retype the kernel node so
        its type carries the prefix. (substrate_rs.vision constructors
        always emit ``"Kernel"``; we apply the namespace here. Full
        namespace plumbing through every vision helper is a separate
        refactor.) Returns the same NodeID for chainability."""
        if self.namespace:
            cur = self.substrate.node(nid)["type"]
            if ":" not in cur:
                self.substrate.set_type(nid, f"{self.namespace}:{cur}")
        return nid

    def _build_gaze(self) -> None:
        for ai in range(self.n_az):
            az = math.radians(-self.fov_h_deg / 2
                              + self.fov_h_deg * (ai + 0.5) / self.n_az)
            self._gaze.append((az, math.cos(az), math.sin(az)))

    # ---- introspection / editing surface (agent thread) ----

    def kernels(self) -> dict[str, Any]:
        """The NodeIDs of every graph-resident receptive field. The
        agent uses these to ``Attr`` the kernels and read / edit
        their weights / σ from inside its DSL. The ``ChangeDetect``
        Term reads the same ``Attr(k, "weights")`` the agent reads,
        so an edit is visible to the next frame with no refresh
        step."""
        return {
            "sobel_x": self._sobel_x_nid,
            "sobel_y": self._sobel_y_nid,
            "gauss_center": self._gauss_center_nid,
            "gauss_surround": self._gauss_surround_nid,
        }

    def _kernel_sigma(self, nid) -> float:
        """Read the Gaussian σ straight off the graph-resident kernel
        node's ``name`` attr (live — no cache). The native substrate
        is an ``Arc<Mutex>`` so this is safe from the worker thread."""
        return _extract_sigma(self.substrate.node(nid)["attrs"]["name"])

    # ---- standard Eye interface (agent thread) ----

    def submit(self, depth=None, screen=None, posture_deg: float = 0.0) -> None:
        self._next_id += 1
        self._latest_frame = (depth, screen, float(posture_deg), self._next_id)
        self._snapshot = self._process_frame(depth, screen, float(posture_deg))
        self._last_id = self._next_id
        self._processed += 1

    def latest(self):
        return self._snapshot

    def processed_count(self) -> int:
        return self._processed

    def stop(self, join_timeout: float = 1.0) -> None:
        """No-op compatibility surface; cognition workers are runtime-owned."""
        return None

    @staticmethod
    def _to_hwc(screen):
        if screen.ndim == 3 and screen.shape[0] == 3:
            return np.transpose(screen, (1, 2, 0))
        return screen

    def _convolve_same(self, gray_f: np.ndarray, kernel_nid) -> np.ndarray:
        """Run the Rust ``ChangeDetect`` Term against a graph-resident
        Kernel node and return a 2-D response shaped like
        ``cv2.filter2D`` 'same' (i.e. the input (H, W)).

        ``ChangeDetect`` is VALID cross-correlation — it shrinks the
        output by ``(kh-1, kw-1)``. To reproduce 'same' coverage the
        image is replicate-padded by ``(kh//2, kw//2)`` first, so the
        valid response lands back at (H, W). Kernel weights + kh/kw
        are read live off the Kernel NODE via ``Attr`` (no numpy cache):
        the agent OWNS the receptive field as graph data the Term
        composes over. Image pixels are external I/O (the screen) —
        flattened to a literal the Term ingests (mechanical adapter
        work, no decision).
        """
        ka = self.substrate.node(kernel_nid)["attrs"]
        kh, kw = int(ka["kh"]), int(ka["kw"])
        h, w = gray_f.shape
        ph, pw = kh // 2, kw // 2
        if ph or pw:
            padded = np.pad(gray_f, ((ph, ph), (pw, pw)), mode="edge")
        else:
            padded = gray_f
        ph_, pw_ = padded.shape
        term = Term(
            "ChangeDetect",
            image_vals=Lit(padded.flatten().tolist()),
            kernel_weights=Attr(Lit(kernel_nid), "weights"),
            dims=Vec([Lit(ph_), Lit(pw_), Lit(kh), Lit(kw), Lit(1)]),
        )
        resp = self.substrate.evaluate(term)
        if resp is None:
            # Shape mismatch (e.g. kernel larger than the padded image)
            # — fall back to a zero map so the pipeline degrades
            # gracefully rather than crashing the worker thread.
            return np.zeros((h, w), dtype=np.float32)
        out_h = (ph_ - kh) + 1
        out_w = (pw_ - kw) + 1
        return np.asarray(resp, dtype=np.float32).reshape(out_h, out_w)

    def _convolve_pair_tasks(self, gray_f: np.ndarray, kernels) -> list[np.ndarray]:
        """Emit independent receptive-field work as generic CognitiveTasks.

        ``worker_capacity`` is an external resource envelope, not an eye
        decision. Task creation and status are graph state; execution/fold are
        the generic Rust cognitive runtime.
        """
        task_nodes = []
        shapes = []
        h, w = gray_f.shape
        for logical_time, kernel_nid in enumerate(kernels):
            attrs = self.substrate.node(kernel_nid)["attrs"]
            kh, kw = int(attrs["kh"]), int(attrs["kw"])
            ph, pw = kh // 2, kw // 2
            padded = np.pad(gray_f, ((ph, ph), (pw, pw)), mode="edge") \
                if ph or pw else gray_f
            ph_, pw_ = padded.shape
            payload = [ph_, pw_, kh, kw, 1]
            payload.extend(float(v) for v in padded.reshape(-1))
            payload.extend(float(v) for v in attrs["weights"])
            task = self.substrate.add_node("CognitiveTask", {
                "status": "requested", "kind": "vision_convolve",
                "payload": payload, "input_epoch": self._next_id,
                "logical_time": logical_time, "area": "vision",
                "order": 1, "salience": 1.0,
            })
            task_nodes.append(task)
            shapes.append(((ph_ - kh) + 1, (pw_ - kw) + 1))
        capacity = int(self.context.get("worker_capacity", 1))
        self.substrate._inner.run_cognitive_tasks(max(1, capacity))
        outputs = []
        for task, shape in zip(task_nodes, shapes):
            values = self.substrate.node(task)["attrs"].get("output")
            if values is None:
                outputs.append(np.zeros((h, w), dtype=np.float32))
            else:
                outputs.append(np.asarray(values, dtype=np.float32).reshape(shape))
            self.substrate.remove_node(task)
        return outputs

    def _process_frame(self, depth, screen, posture_deg) -> dict:
        """Front-end pipeline — IDENTICAL OUTPUT SHAPE to the original Eye.

        The edge-gradient convolve MATH now runs in the Rust
        ``ChangeDetect`` Term, which reads the graph-resident Sobel
        kernel weights via ``Attr(k, "weights")`` directly off the
        Kernel NODES — no ``cv2.filter2D``, no numpy weight cache, no
        ``refresh_kernels``. The agent edits a kernel node and the
        next frame sees the new weights live (the native substrate is
        an ``Arc<Mutex>``, safe from the worker thread).

        ``ChangeDetect`` is VALID cross-correlation (no padding), so
        to keep the response covering the full frame like
        ``cv2.filter2D`` 'same' did, the image is replicate-padded by
        ``(kh//2, kw//2)`` before the Term evaluates — the output then
        comes out at the original (H, W).

        What stays as cv2 (documented exceptions, do not expand scope):

        * **Harris corners** — ``cv2.cornerHarris`` (no single-matrix
          graph form).
        * **Contour finding** — ``cv2.findContours`` /
          ``cv2.connectedComponentsWithStats`` (iterative, not a kernel).
        * **GaussianBlur salience DoG** — a separable blur parameterised
          by σ read live from the Gaussian kernel NODES' ``name`` attr
          (the σ=16 Gaussian kernel is ~97×97, larger than a typical
          frame, so it can't go through the valid ``ChangeDetect``).
        """
        if screen is not None:
            img = self._to_hwc(screen).astype(np.uint8)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        elif depth is not None:
            img = None
            gray = depth.astype(np.uint8)
        else:
            return {"percepts": [], "polygons": []}

        # Edge gradients via the graph-resident Sobel kernels, run through
        # the Rust ChangeDetect Term (reads Attr(k,"weights") live).
        gray_f = gray.astype(np.float32)
        gx, gy = self._convolve_pair_tasks(
            gray_f, (self._sobel_x_nid, self._sobel_y_nid))
        edge_mag = np.sqrt(gx * gx + gy * gy)

        # Harris corners — stays as cv2 (no single-matrix graph form).
        harris = cv2.cornerHarris(gray.astype(np.float32), 3, 3, 0.04)

        # Salience DoG via the Gaussian σ read live from the kernel NODES.
        base = (img.astype(np.float32) if img is not None
                else gray.astype(np.float32)[:, :, None])
        # cv2.GaussianBlur squeezes the singleton channel dim on (H,W,1)
        # input; restore it so axis=2 works on the depth-only path.
        sal_map = np.linalg.norm(
            _blur_keep_dims(base, self._kernel_sigma(self._gauss_center_nid))
            - _blur_keep_dims(base, self._kernel_sigma(self._gauss_surround_nid)),
            axis=2)

        H, W = gray.shape
        lo, hi = int(H * (0.5 - self.vband / 2)), int(H * (0.5 + self.vband / 2))
        hi = max(hi, lo + 1)
        facing = math.radians(posture_deg)
        cf, sf = math.cos(facing), math.sin(facing)
        percepts = []
        for ai, (az, gx_, gy_) in enumerate(self._gaze):
            c0 = int(W * ai / self.n_az)
            c1 = max(c0 + 1, int(W * (ai + 1) / self.n_az))
            p = {"gaze_az": az, "gaze_x": gx_, "gaze_y": gy_,
                 "distance": float("inf"), "depth_spread": 0.0,
                 "luminance": 0.0, "red": 0.0, "green": 0.0, "blue": 0.0}
            if depth is not None:
                col = depth[lo:hi, c0:c1].astype(np.float32)
                p["distance"] = float(col.min()) * self.depth_scale
                p["depth_spread"] = float(col.var()) * self.depth_scale ** 2
            if img is not None:
                reg = img[lo:hi, c0:c1].reshape(-1, 3)
                r, g, b = (float(reg[:, 0].mean()), float(reg[:, 1].mean()),
                           float(reg[:, 2].mean()))
                p["red"], p["green"], p["blue"] = r, g, b
                p["luminance"] = 0.299 * r + 0.587 * g + 0.114 * b
            p["edge_density"] = float(edge_mag[lo:hi, c0:c1].mean())
            p["contrast"] = p["edge_density"]
            p["corner_density"] = float(
                harris[lo:hi, c0:c1].clip(min=0).mean()) * 1e5
            p["world_dir"] = (gx_ * cf - gy_ * sf, gx_ * sf + gy_ * cf)
            p["salience"] = float(sal_map[lo:hi, c0:c1].max())
            percepts.append(p)
        # FRONT-END by CONTEXT: a discrete grid's figures are its exact connected
        # colour components (edge-tracing on flat blocks finds only the outer
        # outline); a camera scene's are luminance contours.
        if self.context.get("modality") == "grid" and img is not None:
            polys = self._detect_figures_grid(img, W)
        else:
            polys = self._detect_polygons(edge_mag, W)
        return {"percepts": percepts, "polygons": polys}

    def _detect_figures_grid(self, img, W) -> list:
        """GRID front-end: every figure is an exact connected component of one
        colour. No edge threshold, no contour tracing — the grid gives the shapes
        directly, so nothing small is lost. Returns the same polygon record shape
        as the camera path (n_vertices via a contour approx, area, azimuth, plus
        normalized centre/bbox), so downstream shape concepts are front-end-blind."""
        H, Wpix = img.shape[0], img.shape[1]
        cell = int(self.context.get("cell_px", 1) or 1)
        floor_area = max(1.0, float(cell * cell))   # a one-cell figure clears it
        out = []
        flat = img.reshape(-1, 3)
        colours = np.unique(flat, axis=0)
        for col in colours:
            if int(col.sum()) == 0:
                continue                              # background (black) — skip
            mask = np.all(img == col, axis=2).astype(np.uint8)
            n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 4)
            for k in range(1, n):
                area = float(stats[k, cv2.CC_STAT_AREA])
                if area < floor_area:
                    continue
                cx, cy = float(cents[k][0]), float(cents[k][1])
                az = self.fov_h_deg * (cx / W) - self.fov_h_deg / 2
                comp = (labels == k).astype(np.uint8)
                cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
                nv = 0
                if cnts:
                    peri = cv2.arcLength(cnts[0], True)
                    nv = len(cv2.approxPolyDP(cnts[0], 0.04 * peri, True))
                x = stats[k, cv2.CC_STAT_LEFT]; y = stats[k, cv2.CC_STAT_TOP]
                bw = stats[k, cv2.CC_STAT_WIDTH]; bh = stats[k, cv2.CC_STAT_HEIGHT]
                out.append({"n_vertices": int(nv), "area": area,
                            "center_az": float(az),
                            "cx_norm": cx / Wpix, "cy_norm": cy / H,
                            "bbox_norm": (x / Wpix, y / H, bw / Wpix, bh / H)})
        return out

    def _detect_polygons(self, edge_mag, W) -> list:
        ebin = (edge_mag > self.edge_thresh).astype(np.uint8) * 255
        ebin = cv2.morphologyEx(ebin, cv2.MORPH_CLOSE,
                                np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(
            ebin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            m = cv2.moments(cnt)
            cx = m["m10"] / m["m00"] if m["m00"] else 0.0
            az = self.fov_h_deg * (cx / W) - self.fov_h_deg / 2
            out.append({"n_vertices": int(len(approx)),
                        "area": float(area), "center_az": float(az)})
        return out


def _blur_keep_dims(arr: np.ndarray, sigma: float) -> np.ndarray:
    """cv2.GaussianBlur squeezes the singleton channel dim on (H,W,1)
    input; restore it so axis=2 reductions still work. Fix for the
    depth-only path that the original Eye also had."""
    out = cv2.GaussianBlur(arr, (0, 0), sigma)
    if arr.ndim == 3 and out.ndim == 2:
        out = out[..., None]
    return out


def _extract_sigma(kernel_name: str) -> float:
    """Pull the σ value out of a Gaussian kernel's name attr.
    The name has the shape ``gaussian:σ=N.NN`` — defensive parsing
    so a re-authored kernel without our naming convention still gets
    a reasonable default."""
    if "σ=" in kernel_name:
        try:
            return float(kernel_name.split("σ=")[1].split(",")[0].split(")")[0])
        except ValueError:
            return 1.0
    return 1.0


# Public cutover: GraphEye now names the photon/photoreceptor apparatus.
# RGBEye remains available only for explicit legacy consumers.
from domains.photon_eye import GraphEye  # noqa: E402
DeprecatedGraphEye = RGBEye
