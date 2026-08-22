"""Canned device spec + anchor generation for M0.

Replaced by real .blend extraction in M2 (tools/extract_blend.py); the shapes
here ARE the contract, so swapping the source changes no downstream code.
Approximate iPhone-class device: 147 x 72 x 7.8 mm, origin bottom-left-back.
"""
from __future__ import annotations

from app.models import Anchor, BandRequirement, DeviceSpec, Vec3

W, H, T = 72.0, 147.0, 7.8  # x (width), y (height), z (thickness)


def phone_v1() -> DeviceSpec:
    return DeviceSpec.model_validate({
        "device_id": "phone_v1",
        "name": "Generic slab phone (canned M0 spec)",
        "board": {"size_mm": (W - 4, H - 6, 1.0), "stackup": "FR4",
                  "epsilon_r": 4.4, "loss_tangent": 0.02},
        "enclosure": {"back": "glass", "frame": "aluminum", "epsilon_r_back": 5.5},
        "components": [
            {"name": "pcb_ground", "label": "PCB ground plane", "em": "pec",
             "bbox_mm": ((2, 3, 3.0), (W - 2, H - 3, 4.0))},
            {"name": "battery", "label": "Battery", "em": "lossy_metal",
             "bbox_mm": ((6, 40, 4.2), (48, 105, 7.2))},
            {"name": "camera", "label": "Camera module", "em": "pec",
             "bbox_mm": ((4, 118, 4.2), (34, 143, 7.6))},
            {"name": "speaker_bottom", "label": "Speaker", "em": "lossy_metal",
             "bbox_mm": ((40, 4, 4.2), (66, 16, 7.0))},
            {"name": "usb", "label": "USB-C block", "em": "pec",
             "bbox_mm": ((28, 2, 4.2), (44, 10, 6.5))},
            {"name": "display", "label": "Display metal sheet", "em": "pec",
             "bbox_mm": ((1, 1, 0.8), (W - 1, H - 1, 2.2))},
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


def make_anchors(spec: DeviceSpec, spacing_mm: float = 18.0) -> list[Anchor]:
    """Discrete candidate positions along the device perimeter at antenna height
    (above the board, z mid-gap). Corners flagged — they clear in two directions."""
    w, h, _t = spec.board.size_mm
    z = 5.5  # antenna volume sits above ground plane (3..4) and below back glass
    anchors: list[Anchor] = []

    def add(aid: str, label: str, region: str, pos: Vec3, outward: Vec3, corner: bool):
        anchors.append(Anchor(id=aid, label=label, region=region, pos_mm=pos,
                              outward=outward, corner=corner))

    margin = 6.0
    # corners first — the classic antenna real estate
    add("c_bl", "bottom-left corner", "bottom", (margin, margin, z), (-0.7, -0.7, 0), True)
    add("c_br", "bottom-right corner", "bottom", (W - margin, margin, z), (0.7, -0.7, 0), True)
    add("c_tl", "top-left corner", "top", (margin, H - margin, z), (-0.7, 0.7, 0), True)
    add("c_tr", "top-right corner", "top", (W - margin, H - margin, z), (0.7, 0.7, 0), True)
    # edge anchors
    n_bottom = int((W - 2 * margin) // spacing_mm)
    for i in range(1, n_bottom):
        x = margin + i * spacing_mm
        add(f"e_b{i}", f"bottom edge {i}", "bottom", (x, margin, z), (0, -1, 0), False)
        add(f"e_t{i}", f"top edge {i}", "top", (x, H - margin, z), (0, 1, 0), False)
    n_side = int((H - 2 * margin) // spacing_mm)
    for i in range(1, n_side):
        y = margin + i * spacing_mm
        add(f"e_l{i}", f"left edge {i}", "left", (margin, y, z), (-1, 0, 0), False)
        add(f"e_r{i}", f"right edge {i}", "right", (W - margin, y, z), (1, 0, 0), False)
    return anchors


def clearance_at(spec: DeviceSpec, p: Vec3) -> tuple[float, str]:
    """Distance from point to nearest metal/lossy component (frame excluded).
    Port of frontend rf.ts clearanceAt — feeds priors and hints, not the solver.
    Ground plane and display sheet excluded: the antenna volume necessarily sits
    above them; lateral blocks (battery, camera, speaker) are what detune."""
    best, who = 50.0, ""
    for c in spec.components:
        if c.em not in ("pec", "lossy_metal") or c.name in ("pcb_ground", "display"):
            continue
        (x0, y0, z0), (x1, y1, z1) = c.bbox_mm
        dx = max(x0 - p[0], 0, p[0] - x1)
        dy = max(y0 - p[1], 0, p[1] - y1)
        dz = max(z0 - p[2], 0, p[2] - z1)
        d = (dx * dx + dy * dy + dz * dz) ** 0.5
        if d < best:
            best, who = d, c.label
    return best, who
