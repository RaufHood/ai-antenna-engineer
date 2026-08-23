"""Anchor generation + clearance metric over a DeviceSpec, and the canned
Handset A spec (the offline baseline; real devices come from
tools/extract_blend.py via classify.py).

Every function here derives from the spec — device size is the union of the
component boxes, the antenna height sits just above the ground reference —
so a 147 mm handset and a 374 mm axe get sensible anchors alike."""
from __future__ import annotations

from app.geometry.bands import requirements_for
from app.geometry.classify import device_size, ground_of
from app.models import Anchor, DeviceSpec, Vec3

# Canned outline. Mirrors frontend/src/lib/device.ts `phoneV1` (ADR-8): the
# viewer draws its procedural handset from those same boxes, so candidates
# the backend proposes on this spec land exactly where the 3D scene shows the
# battery, camera and speaker. Change both files together.
W, H, T = 71.6, 147.6, 7.8  # x width, y height, z thickness (iPhone 15 class)

# roles whose boxes the antenna volume necessarily sits on/inside — they are
# the environment, not obstacles (the frame is usually the antenna's own metal)
_NOT_OBSTACLES = {"ground", "display", "back_cover", "board", "frame"}
_MIN_OBSTACLE_MM = 4.0   # screws, springs, pins: too small to detune anything


def default_spec(band_ids: list[str] | None = None) -> DeviceSpec:
    """The device a run gets when the engineer has not loaded their own.

    Prefers the real iPhone 15 Pro manifest committed at
    rf/blend_loader/out/device.json — 176 RF-relevant parts with real bounding
    boxes and materials — and falls back to the canned slab only when that is
    missing. The viewer draws that phone either way; letting the solver read a
    nine-box abstraction of a different device made every clearance number and
    every anchor belong to something nobody was looking at.
    """
    from app.geometry.manifest import default_device_spec
    classified = default_device_spec(band_ids)
    if classified is None:
        return phone_v1()
    return getattr(classified, "spec", classified)


def phone_v1() -> DeviceSpec:
    """Handset A. Obstacle boxes (battery, camera, taptic, speaker) are the
    frontend's verbatim; the ground/display sheets are the RF model's view of
    the same handset (the viewer draws frame + glass instead, which are not
    obstacles either way). Requirements: the full band catalogue; a run picks
    which bands it must satisfy."""
    return DeviceSpec.model_validate({
        "device_id": "phone_v1",
        "name": "Handset A (147.6 x 71.6 x 7.8 mm)",
        "board": {"size_mm": (W, H, T), "stackup": "FR4",
                  "epsilon_r": 4.4, "loss_tangent": 0.02},
        "enclosure": {"back": "glass", "frame": "aluminum", "epsilon_r_back": 5.5},
        "components": [
            {"name": "pcb_ground", "label": "PCB ground plane", "em": "pec",
             "role": "ground", "bbox_mm": ((2, 3, 3.0), (W - 2, H - 3, 4.0))},
            {"name": "battery", "label": "Battery pack", "em": "lossy_metal",
             "role": "battery", "bbox_mm": ((5, 36, 1.6), (66, 98, 5.8))},
            {"name": "camera_module", "label": "Camera module", "em": "pec",
             "role": "module", "bbox_mm": ((6, 104, 3.6), (30, 132, 7.4))},
            {"name": "taptic_engine", "label": "Taptic engine", "em": "lossy_metal",
             "role": "module", "bbox_mm": ((6, 20, 2.2), (30, 33, 5.4))},
            {"name": "speaker", "label": "Loudspeaker", "em": "lossy_metal",
             "role": "module", "bbox_mm": ((38, 20, 2.2), (66, 33, 5.4))},
            {"name": "display", "label": "Display metal sheet", "em": "pec",
             "role": "display", "bbox_mm": ((1.4, 1.4, T - 1.4), (W - 1.4, H - 1.4, T))},
        ],
        "requirements": requirements_for().model_dump(),
    })


def antenna_z(spec: DeviceSpec) -> float:
    """Height of the antenna volume: just above the ground reference, inside
    the device."""
    _, _, t = device_size(spec)
    g_top = ground_of(spec).bbox_mm[1][2]
    return min(g_top + 2.0, max(t - 0.5, g_top + 0.5))


def make_anchors(spec: DeviceSpec, spacing_mm: float = 18.0) -> list[Anchor]:
    """Discrete candidate positions along the device perimeter at antenna
    height. Corners flagged — they clear in two directions."""
    w, h, _t = device_size(spec)
    z = round(antenna_z(spec), 2)
    anchors: list[Anchor] = []

    def add(aid: str, label: str, region: str, pos: Vec3, outward: Vec3, corner: bool):
        anchors.append(Anchor(id=aid, label=label, region=region,
                              pos_mm=tuple(round(v, 2) for v in pos),
                              outward=outward, corner=corner))

    margin = min(6.0, w / 8)
    add("c_bl", "bottom-left corner", "bottom", (margin, margin, z), (-0.7, -0.7, 0), True)
    add("c_br", "bottom-right corner", "bottom", (w - margin, margin, z), (0.7, -0.7, 0), True)
    add("c_tl", "top-left corner", "top", (margin, h - margin, z), (-0.7, 0.7, 0), True)
    add("c_tr", "top-right corner", "top", (w - margin, h - margin, z), (0.7, 0.7, 0), True)
    n_bottom = int((w - 2 * margin) // spacing_mm)
    for i in range(1, n_bottom):
        x = margin + i * spacing_mm
        add(f"e_b{i}", f"bottom edge {i}", "bottom", (x, margin, z), (0, -1, 0), False)
        add(f"e_t{i}", f"top edge {i}", "top", (x, h - margin, z), (0, 1, 0), False)
    n_side = int((h - 2 * margin) // spacing_mm)
    for i in range(1, n_side):
        y = margin + i * spacing_mm
        add(f"e_l{i}", f"left edge {i}", "left", (margin, y, z), (-1, 0, 0), False)
        add(f"e_r{i}", f"right edge {i}", "right", (w - margin, y, z), (1, 0, 0), False)
    return anchors


def clearance_at(spec: DeviceSpec, p: Vec3) -> tuple[float, str]:
    """Distance from point to nearest metal/lossy obstacle. Sheets the antenna
    volume sits on (ground, display, covers, board, frame) and any full-face
    sheet (shield, backplate — >= 50 % of the device footprint) are excluded,
    as are sub-4 mm parts (screws); lateral blocks (battery, camera, speaker,
    cans) are what detune.
    Feeds priors and hints, not the solver (ported from the frontend's early
    heuristic, which has since been retired)."""
    best, who = 50.0, ""
    w, h, _t = device_size(spec)
    for c in spec.components:
        if c.em not in ("pec", "lossy_metal") or c.role in _NOT_OBSTACLES:
            continue
        (x0, y0, z0), (x1, y1, z1) = c.bbox_mm
        if (x1 - x0) * (y1 - y0) >= 0.5 * w * h:
            continue
        if max(x1 - x0, y1 - y0, z1 - z0) < _MIN_OBSTACLE_MM:
            continue
        dx = max(x0 - p[0], 0, p[0] - x1)
        dy = max(y0 - p[1], 0, p[1] - y1)
        dz = max(z0 - p[2], 0, p[2] - z1)
        d = (dx * dx + dy * dy + dz * dz) ** 0.5
        if d < best:
            best, who = d, c.label
    return best, who
