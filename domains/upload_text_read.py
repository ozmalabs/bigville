"""upload_text_read — thin world adapter for foveated upload text decode.

REFLEXIVE identification (glyph strokes in a foveated fixation) is graph rules
(seeds/upload_foveated_text.json). FULL decode is an active cognitive decision:
a Goal{decode_upload_text} dispatches UploadTextReadStage; this module's
`_advance_upload_text_read_stage` is the reflex RESPONSE — mechanical pixel I/O
through the agent's eye (substrate_rs.vision Sobel+Gabor) + LetterformGrounding
(the same stack as scripts/agent_reads_through_its_eye.py). No routing decisions.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np

_FOVEATED_FIXATIONS = frozenset({"center_fovea", "upper_fovea", "lower_fovea", "full"})
_EYE = None
_GROUNDING = None


def _eye_state():
    """Lazy singleton eye + alphabet grounding (learned once by example)."""
    global _EYE, _GROUNDING
    if _EYE is None:
        from scripts.agent_reads_through_its_eye import Eye, LetterformGrounding
        _EYE = Eye()
        _GROUNDING = LetterformGrounding(_EYE)
        _GROUNDING.learn_alphabet("abcdefghilmnopqrstuvwxyz")
    return _EYE, _GROUNDING


def wire_upload_text_read_faculty(agent) -> None:
    """Register the upload_text_read_advance reflex response. Idempotent."""
    master = getattr(agent, "_master", None)
    if master is None:
        return
    if "upload_text_read_advance" not in master.get("reflex_responses", {}):
        agent.register_reflex_response(
            "upload_text_read_advance",
            lambda ag: _advance_upload_text_read_stage(ag))


def _doc_image_array(agent, doc_id) -> Optional[np.ndarray]:
    """Mechanical read: UploadedDocument -has_image-> Image pixels."""
    from substrate_rs import vision as v
    for iid in agent.inner.neighbours(doc_id, "has_image"):
        if agent.inner.has_node(iid):
            return v.image_to_array(agent.inner, iid)
    return None


def _best_foveated_fixation(agent, doc_id) -> Optional[str]:
    """Mechanical: fixation name with the most glyph_stroke shapes."""
    counts: dict[str, int] = {}
    for sid in agent.inner.neighbours(doc_id, "has_shape"):
        if not agent.inner.has_node(sid):
            continue
        sa = agent.s.node(sid)["attrs"]
        if sa.get("read_as") != "glyph_stroke":
            continue
        fix = str(sa.get("fixation") or "")
        if fix not in _FOVEATED_FIXATIONS:
            continue
        counts[fix] = counts.get(fix, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _crop_for_fixation(agent, doc_id, fixation: str) -> Optional[np.ndarray]:
    """Mechanical crop from stored foveation_crops metadata."""
    da = agent.s.node(doc_id)["attrs"]
    raw = da.get("foveation_crops")
    if not raw:
        return None
    try:
        crops = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001
        return None
    spec = next((c for c in crops if c.get("name") == fixation), None)
    if spec is None:
        return None
    arr = _doc_image_array(agent, doc_id)
    if arr is None:
        return None
    x0 = int(spec.get("x0", 0))
    y0 = int(spec.get("y0", 0))
    w = int(spec.get("w", 0))
    h = int(spec.get("h", 0))
    if w <= 0 or h <= 0:
        return None
    return np.asarray(arr[y0:y0 + h, x0:x0 + w])


def _to_ink_binary(crop: np.ndarray) -> np.ndarray:
    """Mechanical luminance threshold — ink bright on dark background."""
    if crop.ndim == 3:
        gray = crop[..., :3].astype(np.float32).mean(axis=2)
    else:
        gray = crop.astype(np.float32)
    if float(gray.mean()) > 127.0:
        gray = 255.0 - gray
    thresh = max(32.0, float(np.percentile(gray, 70)))
    return (gray >= thresh).astype(np.uint8) * 255


def _glyph_patches(binary: np.ndarray) -> list[np.ndarray]:
    """Connected components sorted left-to-right — mechanical segmentation."""
    try:
        import cv2
    except ImportError:
        return []
    if binary.size == 0:
        return []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 127).astype(np.uint8), connectivity=8)
    boxes = []
    h, w = binary.shape[:2]
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 12 or area > max(h, w) * max(h, w) * 0.4:
            continue
        if bw < 2 or bh < 4:
            continue
        pad = 2
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + bw + pad)
        y1 = min(h, y + bh + pad)
        patch = binary[y0:y1, x0:x1]
        if patch.size == 0:
            continue
        boxes.append((x, patch))
    boxes.sort(key=lambda t: t[0])
    return [p for _, p in boxes]


def _resize_for_eye(patch: np.ndarray, target_h: int = 21, target_w: int = 15) -> np.ndarray:
    try:
        import cv2
        return cv2.resize(patch, (target_w, target_h), interpolation=cv2.INTER_AREA)
    except Exception:  # noqa: BLE001
        from PIL import Image
        img = Image.fromarray(patch)
        return np.asarray(img.resize((target_w, target_h)))


def decode_foveated_crop(crop: np.ndarray) -> tuple[str, list[float]]:
    """Pixels -> grounded letters via the agent's eye. Mechanical I/O only."""
    eye, grounding = _eye_state()
    binary = _to_ink_binary(crop)
    patches = _glyph_patches(binary)
    if not patches:
        return "", []
    letters: list[str] = []
    sims: list[float] = []
    for patch in patches:
        if float(patch.mean()) < 1.0:
            letters.append(" ")
            sims.append(1.0)
            continue
        sig = eye.perceive(_resize_for_eye(patch))
        ch, sim = grounding.ground(sig)
        letters.append(ch)
        sims.append(sim)
    text = "".join(letters)
    text = " ".join(text.split())
    return text, sims


def _advance_upload_text_read_stage(agent) -> None:
    """Reflex RESPONSE: advance ONE dispatched UploadTextReadStage."""
    for st in agent.s.nodes("UploadTextReadStage"):
        at = agent.s.node(st)["attrs"]
        if at.get("status") != "dispatched":
            continue
        doc_ids = list(agent.inner.neighbours(st, "about_document"))
        if not doc_ids:
            agent.s.set_attr(st, "status", "done")
            return
        doc_id = doc_ids[0]
        fixation = _best_foveated_fixation(agent, doc_id)
        crop = _crop_for_fixation(agent, doc_id, fixation) if fixation else None
        if crop is None:
            crop = _doc_image_array(agent, doc_id)
        decoded = ""
        mean_sim = 0.0
        if crop is not None:
            decoded, sims = decode_foveated_crop(crop)
            mean_sim = float(sum(sims) / len(sims)) if sims else 0.0
        agent.inner.set_attr(doc_id, "decoded_text", decoded or "")
        agent.inner.set_attr(doc_id, "decode_fixation", fixation or "")
        agent.inner.set_attr(doc_id, "decode_confidence", mean_sim)
        if decoded:
            base = str(agent.s.node(doc_id)["attrs"].get("vision_summary") or "")
            extra = f" I chose to read the foveated text and recovered: {decoded!r}."
            agent.inner.set_attr(doc_id, "vision_summary", base + extra)
            agent.inner.set_attr(doc_id, "summary", base + extra)
        agent.s.set_attr(st, "status", "done")
        agent.s.set_attr(st, "decoded_text", decoded or "")
        return


def pump_upload_text_read(agent, *, max_ticks: int = 8) -> int:
    """Mechanical pump: rules dispatch stages; cognitive_tick fires the reflex."""
    wire_upload_text_read_faculty(agent)
    ticks = 0
    for _ in range(max_ticks):
        before = sum(
            1 for st in agent.s.nodes("UploadTextReadStage")
            if agent.s.node(st)["attrs"].get("status") == "dispatched")
        if before == 0:
            break
        agent.cognitive_tick(max_steps=10_000)
        ticks += 1
        after = sum(
            1 for st in agent.s.nodes("UploadTextReadStage")
            if agent.s.node(st)["attrs"].get("status") == "dispatched")
        if after == 0:
            break
    return ticks
