"""Anchor generation + clearance metric over a DeviceSpec, and the canned M0
spec (kept as the offline regression baseline; real devices come from
tools/extract_blend.py via classify.py).

Every function here derives from the spec — device size is the union of the
component boxes, the antenna height sits just above the ground reference —
so a 147 mm handset and a 374 mm axe get sensible anchors alike."""
from __future__ import annotations

from app.geometry.classify import device_size, ground_of
from app.models import Anchor, DeviceSpec, Vec3

W, H, T = 72.0, 147.0, 7.8  # canned phone outline (x width, y height, z thickness)

# roles whose boxes the antenna volume necessarily sits on/inside — they are
# the environment, not obstacles (the frame is usually the antenna's own metal)
_NOT_OBSTACLES = {"ground", "display", "back_cover", "board", "frame"}
_MIN_OBSTACLE_MM = 4.0   # screws, springs, pins: too small to detune anything


def phone_v1() -> DeviceSpec:
    return DeviceSpec.model_validate({
        "device_id": "phone_v1",
        "name": "Generic slab phone (canned M0 spec)",
        "board": {"size_mm": (W - 4, H - 6, 1.0), "stackup": "FR4",
                  "epsilon_r": 4.4, "loss_tangent": 0.02},
        "enclosure": {"back": "glass", "frame": "aluminum", "epsilon_r_back": 5.5},
        "components": [
            {"name": "pcb_ground", "label": "PCB ground plane", "em": "pec",
             "role": "ground", "bbox_mm": ((2, 3, 3.0), (W - 2, H - 3, 4.0))},
            {"name": "battery", "label": "Battery", "em": "lossy_metal",
             "role": "battery", "bbox_mm": ((6, 40, 4.2), (48, 105, 7.2))},
            {"name": "camera", "label": "Camera module", "em": "pec",
             "role": "module", "bbox_mm": ((4, 118, 4.2), (34, 143, 7.6))},
            {"name": "speaker_bottom", "label": "Speaker", "em": "lossy_metal",
             "role": "module", "bbox_mm": ((40, 4, 4.2), (66, 16, 7.0))},
            {"name": "usb", "label": "USB-C block", "em": "pec",
             "role": "module", "bbox_mm": ((28, 2, 4.2), (44, 10, 6.5))},
            {"name": "display", "label": "Display metal sheet", "em": "pec",
             "role": "display", "bbox_mm": ((1, 1, 0.8), (W - 1, H - 1, 2.2))},
        ],
        "requirements": {
            "bands": [
                {"id": "wifi24", "name": "Wi-Fi 2.4 GHz", "short": "2.4G",
                 "service": "WLAN/BT", "f_low_ghz": 2.400, "f_high_ghz": 2.4835,
                 "clearance_mm": 5.0, "s11_db_max": -6.0, "efficiency_min": 0.4,
                 "antenna_types": ["IFA", "monopole", "loop"]},
            ],
            "vswr_max": 3.0,
            "isolation_db_max": -10.0,
            "sar_limit": {"standard": "FCC", "w_per_kg": 1.6, "mass_g": 1},
        },
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
    Port of frontend rf.ts clearanceAt — feeds priors and hints, not the solver."""
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
