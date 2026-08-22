#!/usr/bin/env python
"""Generate a synthetic handset .blend + materials.json in the team asset
convention (object name "<node_path>__<material_key>", custom props, sidecar
vocabulary with eps_r / sigma). Test fixture for tools/extract_blend.py and a
demo fallback until a real iPhone .blend is available.

    uv run --no-project --python 3.11 --with bpy python tools/make_phone_blend.py \
        --out data/phone_synth_v1 [--standing] [--metres] [--upside-down] [--no-sidecar]

--standing / --metres deliberately break the frame convention so the
extractor's axis/unit normalisation gets exercised.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy
import mathutils

W, H, T = 71.6, 147.6, 7.8   # iPhone-15-class outline, mm

VOCAB = {
    "aluminum": {"eps_r": 1.0, "sigma_S_per_m": 3.5e7, "what": "6000-series aluminium frame"},
    "glass": {"eps_r": 5.5, "sigma_S_per_m": 0.0, "what": "aluminosilicate cover glass"},
    "fr4": {"eps_r": 4.4, "sigma_S_per_m": 0.004, "what": "FR-4 laminate"},
    "copper": {"eps_r": 1.0, "sigma_S_per_m": 5.8e7, "what": "copper ground pour"},
    "lithium": {"eps_r": 1.0, "sigma_S_per_m": 1.0e5, "what": "Li-ion pouch (lossy metal proxy)"},
    "steel": {"eps_r": 1.0, "sigma_S_per_m": 1.45e6, "what": "stainless shield cans"},
    "abs": {"eps_r": 2.8, "sigma_S_per_m": 0.001, "what": "ABS plastic carrier"},
}

# (node_path, key, bbox_min, bbox_max) in the CANONICAL frame (mm, flat, origin min corner)
PARTS = [
    ("frame.rail_left", "aluminum", (0, 0, 0), (1.8, H, T)),
    ("frame.rail_right", "aluminum", (W - 1.8, 0, 0), (W, H, T)),
    ("frame.rail_bottom", "aluminum", (1.8, 0, 0), (W - 1.8, 1.8, T)),
    ("frame.rail_top", "aluminum", (1.8, H - 1.8, 0), (W - 1.8, H, T)),
    ("back.glass", "glass", (1.2, 1.2, 0), (W - 1.2, H - 1.2, 1.1)),
    ("display.panel", "glass", (1.4, 1.4, T - 1.4), (W - 1.4, H - 1.4, T)),
    ("display.shield", "steel", (1.6, 1.6, T - 1.7), (W - 1.6, H - 1.6, T - 1.4)),
    ("pcb.logic_board", "fr4", (36, 100, 2.4), (64, 132, 3.5)),
    ("pcb.ground_pour", "copper", (4, 8, 3.5), (W - 4, H - 8, 3.8)),
    ("battery.cell", "lithium", (5, 36, 1.6), (66, 98, 5.8)),
    ("camera.module", "steel", (6, 104, 3.6), (30, 132, 7.4)),
    ("haptics.taptic_engine", "steel", (6, 20, 2.2), (30, 33, 5.4)),
    ("audio.speaker", "steel", (38, 20, 2.2), (66, 33, 5.4)),
    ("io.usb_c", "steel", (28, 1.8, 2.5), (44, 9.5, 5.5)),
    ("carrier.plastic", "abs", (4, 4, 1.2), (W - 4, 18, 2.2)),
]


def _box(name: str, lo, hi):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    o = bpy.context.active_object
    o.name = name
    o.data.name = name
    o.scale = [(hi[i] - lo[i]) for i in range(3)]
    o.location = [(hi[i] + lo[i]) / 2 for i in range(3)]
    bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)
    return o


def build(out: Path, standing: bool, metres: bool, sidecar: bool,
          upside_down: bool = False) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS" if metres else "MILLIMETERS"
    scene.unit_settings.scale_length = 1.0 if metres else 0.001

    mats = {}
    for key, em in VOCAB.items():
        m = bpy.data.materials.new(f"MAT_{key}")
        m.use_fake_user = True
        mats[key] = m

    parts_meta = []
    for node_path, key, lo, hi in PARTS:
        o = _box(f"{node_path}__{key}", lo, hi)
        o["node_path"] = node_path
        o["material_key"] = key
        o.data.materials.append(mats[key])
        vol = 1.0
        for i in range(3):
            vol *= hi[i] - lo[i]
        parts_meta.append({
            "node_path": node_path, "blender_object": o.name, "material_key": key,
            "em_from_vocabulary": VOCAB[key], "volume_mm3": round(vol, 1),
            "tris": 12,
        })

    # deliberately non-canonical frames for extractor tests
    m = mathutils.Matrix.Identity(4)
    if standing:   # height along +Z, thickness along -Y: rotate +90 deg about X
        m = mathutils.Matrix.Rotation(1.5707963, 4, "X") @ m
    if upside_down:  # 180 deg about X: screen ends at low z, camera at low y
        m = mathutils.Matrix.Rotation(3.1415927, 4, "X") @ m
    if metres:
        m = mathutils.Matrix.Scale(0.001, 4) @ m
    m = mathutils.Matrix.Translation(mathutils.Vector((-0.2, 1.0, 0.05))) @ m  # arbitrary offset
    for o in bpy.data.objects:
        o.matrix_world = m @ o.matrix_world
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
    bpy.ops.object.transform_apply(location=True, scale=True, rotation=True)

    out.mkdir(parents=True, exist_ok=True)
    blend = out / f"{out.name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    if sidecar:
        (out / "materials.json").write_text(json.dumps({
            "object": "Synthetic handset (iPhone-15-class outline)",
            "model": out.name,
            "units": "m" if metres else "mm",
            "blend_file": blend.name,
            "blender_version": bpy.app.version_string,
            "how_material_identity_is_carried": [
                "object NAME encodes it: <node_path>__<material_key>",
                "object custom property 'material_key' (and 'node_path')",
                "material MAT_<key>, kept in the file with a fake user",
            ],
            "material_vocabulary_used": VOCAB,
            "parts": parts_meta,
            "material_gaps": [
                {"part": "battery.cell", "key_used": "lithium",
                 "gap": "pouch cell modelled as a homogeneous lossy conductor (1e5 S/m); "
                        "real cells are layered foil/electrolyte.",
                 "action": "FLAGGED, homogeneous."},
                {"part": "display.shield", "key_used": "steel",
                 "gap": "mu_r not in vocabulary; stainless 304 is ~1, fine.",
                 "action": "none"},
            ],
        }, indent=2))
    print(f"wrote {blend} ({blend.stat().st_size / 1e3:.0f} kB), "
          f"{len(PARTS)} parts, standing={standing} metres={metres} upside_down={upside_down}")


if __name__ == "__main__":
    import sys
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--standing", action="store_true")
    ap.add_argument("--metres", action="store_true")
    ap.add_argument("--no-sidecar", action="store_true")
    ap.add_argument("--upside-down", action="store_true")
    a = ap.parse_args(argv)
    build(Path(a.out), a.standing, a.metres, not a.no_sidecar, a.upside_down)
