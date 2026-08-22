#!/usr/bin/env python
"""Extract device geometry from a .blend into geometry.json (+ device.glb, STLs).

ONE script, two runners (backend DESIGN.md §8): Devin runs it in its VM via the
`blend-extract` skill; the backend runs the identical file as fallback. Output
is a superset of the sim workstream's device manifest (rf/run_simulation.py
`load_device`), so the same file feeds the FDTD side untouched.

Runs under the `bpy` wheel (`pip install bpy`, Python 3.11) or inside Blender:

    python tools/extract_blend.py phone.blend --out out/phone
    blender -b --python tools/extract_blend.py -- phone.blend --out out/phone

Asset convention (data/*/materials.json, "how_material_identity_is_carried"):
  object NAME = "<node_path>__<material_key>", custom props `node_path` /
  `material_key` are authoritative when present, and the sidecar's
  material vocabulary carries eps_r / sigma_S_per_m per key. Everything here
  degrades gracefully when the sidecar is absent: identity from names, EM
  data from Blender material names, classification left to the consumer.

Frame normalisation (the contract all consumers share, frontend types.ts):
  units mm; x = width, y = height (longest extent), z = thickness (shortest);
  origin at the device's min corner (bottom-left-back). The applied transform
  is reported under "frame" so nothing is hidden. glb/STL are written in the
  SAME frame (glTF exported with +Y up disabled, i.e. raw coordinates).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import mathutils

VERSION = "2"  # bump when the output shape changes

# Blender material / key name -> (eps_r, sigma) when no sidecar vocabulary has it.
_FALLBACK_VOCAB: dict[str, tuple[float, float]] = {
    "copper": (1.0, 5.8e7), "aluminum": (1.0, 3.5e7), "aluminium": (1.0, 3.5e7),
    "steel": (1.0, 1.45e6), "stainless": (1.0, 1.4e6), "titanium": (1.0, 2.4e6),
    "gold": (1.0, 4.1e7), "nickel": (1.0, 1.4e7), "brass": (1.0, 1.5e7),
    "metal": (1.0, 1.0e7), "lithium": (1.0, 1.0e5), "battery": (1.0, 1.0e5),
    "fr4": (4.4, 0.004), "pcb": (4.4, 0.004), "glass": (5.5, 0.002),
    "gorilla": (6.7, 0.003), "sapphire": (9.4, 0.0), "ceramic": (6.0, 0.001),
    "abs": (2.8, 0.001), "plastic": (3.0, 0.002), "polycarbonate": (2.9, 0.001),
    "nylon": (2.9, 0.002), "pet": (3.2, 0.002), "rubber": (3.0, 0.01),
    "silicone": (3.0, 0.005), "foam": (1.1, 0.0), "air": (1.0, 0.0),
    "walnut": (2.2, 0.012), "wood": (2.3, 0.012), "g10": (4.5, 0.011),
}


# ------------------------------------------------------------------ helpers --

def _log(msg: str) -> None:
    print(f"[extract_blend] {msg}", file=sys.stderr)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_identity(obj) -> tuple[str, str]:
    if "node_path" in obj.keys() and "material_key" in obj.keys():
        return str(obj["node_path"]), str(obj["material_key"])
    if "__" in obj.name:
        node_path, _, key = obj.name.rpartition("__")
        return node_path, key
    return obj.name, ""


def _world_corners(obj, depsgraph) -> list[mathutils.Vector]:
    ev = obj.evaluated_get(depsgraph)
    return [ev.matrix_world @ mathutils.Vector(c) for c in ev.bound_box]


def _bbox(corners) -> tuple[list[float], list[float]]:
    xs = [c.x for c in corners]; ys = [c.y for c in corners]; zs = [c.z for c in corners]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def _mesh_objects():
    return [o for o in bpy.data.objects
            if o.type == "MESH" and o.data is not None and len(o.data.polygons) > 0]


def _tri_count(obj) -> int:
    return sum(max(len(p.vertices) - 2, 1) for p in obj.data.polygons)


# ------------------------------------------------------------- unit scaling --

def _unit_scale_to_mm(raw_extent_max: float, sidecar: dict) -> tuple[float, str, str]:
    """Factor that turns Blender units into mm, plus where it came from."""
    units = str(sidecar.get("units", "")).lower()
    if units in ("mm", "millimeter", "millimeters", "millimetre", "millimetres"):
        return 1.0, "sidecar:units=mm", "high"
    if units in ("m", "meter", "meters", "metre", "metres"):
        return 1000.0, "sidecar:units=m", "high"
    if units in ("cm", "centimeter", "centimeters"):
        return 10.0, "sidecar:units=cm", "high"
    us = bpy.context.scene.unit_settings
    if us.system != "NONE" and abs(us.scale_length - 1.0) > 1e-9:
        # scene declares a scale: 1 BU = scale_length metres
        return us.scale_length * 1000.0, f"scene:scale_length={us.scale_length}", "medium"
    # plain file, 1 BU == 1 m by Blender default — but modellers often work in
    # "mm as units". Disambiguate from the device extent: a handset is 50-300 mm.
    if 30.0 <= raw_extent_max <= 400.0:
        return 1.0, "heuristic:extent-looks-like-mm", "low"
    if 0.03 <= raw_extent_max <= 0.4:
        return 1000.0, "heuristic:extent-looks-like-m", "low"
    if 3.0 <= raw_extent_max <= 40.0:
        return 10.0, "heuristic:extent-looks-like-cm", "low"
    return 1000.0, "default:blender-metres", "none"


# ------------------------------------------------------- axis normalisation --

_AXES = {0: "X", 1: "Y", 2: "Z"}


def _axis_permutation(extent: list[float]) -> tuple[mathutils.Matrix, dict]:
    """Rotation taking (width, height, thickness) source axes onto (x, y, z).
    Height = longest extent, thickness = shortest. Proper rotation only (det +1)
    so handedness is preserved; the sign flip needed for that is reported."""
    order = sorted(range(3), key=lambda i: extent[i])      # [thin, mid, long]
    src_z, src_x, src_y = order[0], order[1], order[2]
    rows = [[0.0] * 3 for _ in range(3)]
    rows[0][src_x] = 1.0
    rows[1][src_y] = 1.0
    rows[2][src_z] = 1.0
    m = mathutils.Matrix(rows)
    flipped = None
    if m.determinant() < 0:
        rows[2][src_z] = -1.0   # mirror thickness -> rotation; front/back swap
        m = mathutils.Matrix(rows)
        flipped = "z"
    axis_map = {"x": f"+{_AXES[src_x]}", "y": f"+{_AXES[src_y]}",
                "z": ("-" if flipped else "+") + _AXES[src_z]}
    return m, {"axis_map": axis_map, "identity": m == mathutils.Matrix.Identity(3),
               "handedness_flip": flipped}


_FRONT_HINTS = ("display", "screen", "lcd", "oled", "front", "cover_glass", "touch")
_BOTTOM_HINTS = ("usb", "lightning", "charging", "speaker", "mic", "taptic", "haptic")
_TOP_HINTS = ("camera", "earpiece", "face_id", "lidar", "flash")


def _orientation_votes(parts_bbox: list[tuple[str, list, list]], lo: list[float],
                       size: list[float]) -> tuple[bool, bool]:
    """(flip_y, flip_z): name votes on the convention the frontend assumes —
    screen at z = thickness (front up), cameras at high y / ports at low y
    (portrait, bottom edge at y = 0). No named parts -> no flips."""
    vy = vz = 0
    for name, b_lo, b_hi in parts_bbox:
        n = name.lower()
        cy = (b_lo[1] + b_hi[1]) / 2 - lo[1]
        cz = (b_lo[2] + b_hi[2]) / 2 - lo[2]
        if any(h in n for h in _FRONT_HINTS):
            vz += -1 if cz < size[2] / 2 else 1
        if any(h in n for h in _BOTTOM_HINTS):
            vy += 1 if cy < size[1] / 2 else -1
        if any(h in n for h in _TOP_HINTS):
            vy += 1 if cy > size[1] / 2 else -1
    return vy < 0, vz < 0


def _apply_world_transform(m4: mathutils.Matrix) -> None:
    for o in bpy.data.objects:
        if o.parent is None:
            o.matrix_world = m4 @ o.matrix_world
    bpy.context.view_layer.update()


# ------------------------------------------------------------------ export --

def _export_stl(obj, path: Path) -> None:
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    if hasattr(bpy.ops.wm, "stl_export"):
        bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True,
                              global_scale=1.0, apply_modifiers=True)
    else:  # Blender < 4.0
        bpy.ops.export_mesh.stl(filepath=str(path), use_selection=True,
                                global_scale=1.0, use_mesh_modifiers=True)


def _decimate_for_viewer(objs, max_tris: int) -> dict[str, int]:
    """Viewer budget: share max_tris across objects proportionally; heavy meshes
    get a Decimate modifier. In-memory only — the .blend is never saved."""
    total = sum(_tri_count(o) for o in objs)
    applied: dict[str, int] = {}
    if total <= max_tris:
        return applied
    ratio = max_tris / total
    for o in objs:
        n = _tri_count(o)
        if n * ratio < 200:       # tiny parts stay exact
            continue
        mod = o.modifiers.new("viewer_decimate", "DECIMATE")
        mod.ratio = max(ratio, 0.01)
        mod.use_collapse_triangulate = True
        applied[o.name] = int(n * mod.ratio)
    return applied


def _export_glb(path: Path) -> None:
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", export_yup=False,
        export_apply=True, export_materials="EXPORT", export_texcoords=False,
        export_normals=True, export_animations=False, export_skins=False,
        export_cameras=False, export_lights=False, use_selection=False,
    )


# -------------------------------------------------------------------- main --

def extract(blend_path: Path, sidecar_path: Path | None, out_dir: Path | None,
            want_glb: bool, want_stl: bool, max_tris: int) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(blend_path.resolve()), load_ui=False)
    sidecar: dict = {}
    if sidecar_path and sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text())
        _log(f"sidecar: {sidecar_path}")
    vocab = dict(sidecar.get("material_vocabulary_used", {}))
    sidecar_parts = {p["node_path"]: p for p in sidecar.get("parts", [])}

    objs = _mesh_objects()
    if not objs:
        raise SystemExit("no mesh objects in file")
    depsgraph = bpy.context.evaluated_depsgraph_get()

    # ---- raw frame ------------------------------------------------------
    raw = {o.name: _bbox(_world_corners(o, depsgraph)) for o in objs}
    lo = [min(b[0][i] for b in raw.values()) for i in range(3)]
    hi = [max(b[1][i] for b in raw.values()) for i in range(3)]
    raw_extent = [hi[i] - lo[i] for i in range(3)]
    scale, unit_source, unit_conf = _unit_scale_to_mm(max(raw_extent), sidecar)
    rot3, axis_info = _axis_permutation(raw_extent)

    # full transform: scale -> rotate -> translate min corner to origin
    m = mathutils.Matrix.Scale(scale, 4) if scale != 1.0 else mathutils.Matrix.Identity(4)
    m = rot3.to_4x4() @ m
    _apply_world_transform(m)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    boxes = {o.name: _bbox(_world_corners(o, depsgraph)) for o in objs}
    lo = [min(b[0][i] for b in boxes.values()) for i in range(3)]
    hi = [max(b[1][i] for b in boxes.values()) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    flip_y, flip_z = _orientation_votes(
        [(o.name, *boxes[o.name]) for o in objs], lo, size)
    shift = mathutils.Matrix.Translation(mathutils.Vector([-lo[0], -lo[1], -lo[2]]))
    centre = mathutils.Matrix.Translation(
        mathutils.Vector([size[0] / 2, size[1] / 2, size[2] / 2]))
    if flip_y:   # 180 deg about z through the centre: x -> W - x, y -> H - y
        shift = centre @ mathutils.Matrix.Rotation(math.pi, 4, "Z") @ centre.inverted() @ shift
    if flip_z:   # 180 deg about y through the centre: x -> W - x, z -> T - z
        shift = centre @ mathutils.Matrix.Rotation(math.pi, 4, "Y") @ centre.inverted() @ shift
    _apply_world_transform(shift)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    boxes = {o.name: _bbox(_world_corners(o, depsgraph)) for o in objs}
    lo = [min(b[0][i] for b in boxes.values()) for i in range(3)]
    hi = [max(b[1][i] for b in boxes.values()) for i in range(3)]
    size = [round(hi[i] - lo[i], 3) for i in range(3)]

    frame = {
        "units": "mm", "unit_scale_to_mm": scale, "unit_source": unit_source,
        "unit_confidence": unit_conf, **axis_info,
        "origin_shift_mm": [round(-v, 3) for v in
                            (mathutils.Vector(lo) - mathutils.Vector([0, 0, 0]))],
        "orientation_fix": {"rotated_180_about_z": flip_y, "rotated_180_about_y": flip_z},
        "raw_extent_bu": [round(v, 4) for v in raw_extent],
        "convention": "x=width y=height z=thickness, origin bottom-left-back, mm",
    }

    # ---- parts -----------------------------------------------------------
    stl_dir = out_dir / "parts" if (out_dir and want_stl) else None
    if stl_dir:
        stl_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for o in objs:
        node_path, key = _parse_identity(o)
        meta = sidecar_parts.get(node_path, {})
        slot_mats = [s.material.name for s in o.material_slots if s.material]
        em = meta.get("em_from_vocabulary") or vocab.get(key) or {}
        em_source = "sidecar" if em else ""
        if not em:
            probe = [key.lower()] + [s.lower() for s in slot_mats] + [o.name.lower()]
            for name in probe:
                for word, (eps, sig) in _FALLBACK_VOCAB.items():
                    if word in name:
                        em = {"eps_r": eps, "sigma_S_per_m": sig, "what": f"guessed from '{name}'"}
                        em_source = "name-heuristic"
                        break
                if em:
                    break
        b_lo, b_hi = boxes[o.name]
        part = {
            "node_path": node_path,
            "blender_object": o.name,
            "material_key": key or (slot_mats[0].removeprefix("MAT_") if slot_mats else ""),
            "eps_r": em.get("eps_r"),
            "sigma_S_per_m": em.get("sigma_S_per_m"),
            "mu_r": 1.0,
            "mu_r_gap_flagged": key == "steel",
            "em_source": em_source or "none",
            "em_note": em.get("what"),
            "bbox_mm": [[round(v, 3) for v in b_lo], [round(v, 3) for v in b_hi]],
            "extent_mm": [round(b_hi[i] - b_lo[i], 3) for i in range(3)],
            "tris": _tri_count(o),
            "mass_g": meta.get("mass_g"),
            "blender_materials": slot_mats,
            "custom_props": {k: (o[k] if isinstance(o[k], (int, float, str)) else str(o[k]))
                             for k in o.keys() if not k.startswith("_")},
            "stl_path": None,
        }
        if stl_dir:
            p = stl_dir / f"{node_path.replace('/', '_')}.stl"
            _export_stl(o, p)
            part["stl_path"] = str(p.relative_to(out_dir))
        parts.append(part)
    parts.sort(key=lambda p: -(p["extent_mm"][0] * p["extent_mm"][1] * p["extent_mm"][2]))

    result = {
        "schema": f"geometry.json/v{VERSION}",
        "device_id": str(sidecar.get("model") or blend_path.stem),
        "name": str(sidecar.get("object") or blend_path.stem),
        "units": "mm",
        "source_blend": blend_path.name,
        "source_sha256": _sha256(blend_path),
        "blender_version_used": bpy.app.version_string,
        "blender_version_authored": sidecar.get("blender_version"),
        "size_mm": size,
        "bbox_mm": [[0.0, 0.0, 0.0], size],
        "frame": frame,
        "tris_total": sum(p["tris"] for p in parts),
        "n_parts": len(parts),
        "skipped_objects": [o.name for o in bpy.data.objects if o not in objs],
        "material_gaps": sidecar.get("material_gaps", []),
        "parts": parts,
        "glb_path": None,
        "viewer_decimation": {},
    }

    if out_dir and want_glb:
        result["viewer_decimation"] = _decimate_for_viewer(objs, max_tris)
        glb = out_dir / "device.glb"
        _export_glb(glb)
        result["glb_path"] = glb.name
        _log(f"glb: {glb} ({glb.stat().st_size / 1e6:.1f} MB)")
    return result


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend")
    ap.add_argument("--materials", help="materials.json sidecar "
                    "(default: materials.json next to the .blend, if present)")
    ap.add_argument("--out", help="output dir for geometry.json, device.glb, parts/*.stl")
    ap.add_argument("--no-glb", action="store_true")
    ap.add_argument("--no-stl", action="store_true")
    ap.add_argument("--max-tris", type=int, default=150_000,
                    help="viewer glb triangle budget (decimated in memory)")
    args = ap.parse_args(argv)

    blend = Path(args.blend)
    if not blend.exists():
        raise SystemExit(f"no such file: {blend}")
    sidecar = Path(args.materials) if args.materials else blend.with_name("materials.json")
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    result = extract(blend, sidecar, out, not args.no_glb, not args.no_stl, args.max_tris)
    text = json.dumps(result, indent=1)
    if out:
        (out / "geometry.json").write_text(text)
        _log(f"wrote {out / 'geometry.json'}: {result['n_parts']} parts, "
             f"size {result['size_mm']} mm, frame {result['frame']['axis_map']}")
    else:
        print(text)


if __name__ == "__main__":
    # `blender -b --python x.py -- args` puts our args after "--"
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(argv)
