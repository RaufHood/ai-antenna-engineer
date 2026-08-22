"""Photoreal x-ray renders of the antenna placement, straight from the .blend.

The matplotlib placement figure (placement3d.py) is the *technical* view —
bboxes, coordinates, dimensions. This module is the *beauty* view: it opens
the actual device .blend (real meshes, not boxes), switches everything to a
Blender-viewport-style x-ray look (per-material flat colors, transparency,
silhouette outlines), injects the antenna candidate + keep-out at their
corner-anchored coordinates, and renders camera views on black.

Runs in the bpy env, NOT .venv-viz:

    ~/micromamba/envs/bpy/bin/python -m rf.viz.blender_render \
        data/apple_iphone_15_pro/apple_iphone_15_pro.blend \
        runs/demo/config.json runs/demo/media/

Palette mirrors rf/viz/theme.py (keep them in sync by eye).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# theme.py palette, RGBA 0-1 (hand-converted: keep in sync with theme.PALETTE)
COL = {
    "metal":      (0.549, 0.620, 1.000, 1.0),   # 8c9eff
    "dielectric": (0.412, 0.941, 0.682, 1.0),   # 69f0ae
    "battery":    (1.000, 0.541, 0.396, 1.0),   # ff8a65
    "antenna":    (1.000, 0.843, 0.251, 1.0),   # ffd740
    "keepout":    (1.000, 0.843, 0.251, 1.0),
}

METALS = ("alumin", "copper", "steel", "titan", "gold", "metal")


def _family(mat_key: str) -> str:
    k = (mat_key or "").lower()
    if "battery" in k or "lithium" in k or "lipo" in k:
        return "battery"
    if any(m in k for m in METALS):
        return "metal"
    return "dielectric"


def _load_part_families(device_json: Path) -> dict:
    """part name -> family, from blend_loader's device.json (authoritative)."""
    if not device_json.exists():
        return {}
    parts = json.loads(device_json.read_text()).get("parts", [])
    return {p["name"]: _family(p.get("material_key", "")) for p in parts if p.get("name")}


def _material_key_of(obj, mat_table: dict) -> str:
    name = obj.name.lower()
    for key in mat_table:
        if key.lower() in name:
            return key
    for slot in obj.material_slots:
        if slot.material:
            mname = slot.material.name.lower()
            for key in mat_table:
                if key.lower() in mname:
                    return key
    return ""


def render(blend_path: str, config_path: str, out_dir: str,
           res: int = 2200) -> list[str]:
    cfg = json.loads(Path(config_path).read_text())
    cand = cfg["candidate"]
    mats_path = Path(blend_path).parent / "materials.json"
    mat_table = (json.loads(mats_path.read_text()).get("materials", {})
                 if mats_path.exists() else {})

    bpy.ops.wm.open_mainfile(filepath=str(Path(blend_path).resolve()))
    scene = bpy.context.scene

    meshes = [o for o in scene.objects if o.type == "MESH"]
    # device bounds in world space -> corner anchor for candidate coords
    wpts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(p.x for p in wpts), min(p.y for p in wpts), min(p.z for p in wpts)))
    hi = Vector((max(p.x for p in wpts), max(p.y for p in wpts), max(p.z for p in wpts)))
    span = hi - lo
    # candidate coords are mm, corner-anchored; blend units may be metres
    unit = 0.001 if max(span) < 1.0 else 1.0   # heuristic: phone <1 => metres

    fam_map = _load_part_families(Path("rf/blend_loader/out/device.json"))
    for o in meshes:
        fam = fam_map.get(o.name) or _family(_material_key_of(o, mat_table))
        o.color = COL[fam]

    def add_box(name, p0_mm, p1_mm, color, wire=False):
        p0 = lo + Vector([v * unit for v in p0_mm])
        p1 = lo + Vector([v * unit for v in p1_mm])
        centre = (p0 + p1) / 2
        size = (p1 - p0)
        bpy.ops.mesh.primitive_cube_add(location=centre)
        ob = bpy.context.object
        ob.name = name
        ob.scale = size / 2
        ob.color = color
        if wire:
            ob.display_type = "WIRE"   # honored by workbench render outlines
        return ob

    # antenna: a thin printed strip that must live INSIDE the keep-out.
    # Run the arm along whichever keep-out axis has the longer free run from
    # the feed position, clamp its length to that run (1.5 mm margin), and
    # keep a realistic strip cross-section (1.8 x 0.9 mm) -- nothing pokes
    # out of the device or across the camera plateau.
    px, py, pz = cand["position_mm"]
    L = float(cand["length_mm"]); W_arm = 1.8; H_arm = 0.9
    dev_w, dev_l, dev_t = span.x / unit, span.y / unit, span.z / unit
    k0, k1 = cand.get("keepout_mm") or ([0, 0, 0], [dev_w, dev_l, dev_t])
    margin = 1.5
    run_x = max(k1[0] - margin - px, px - (k0[0] + margin))
    run_y = max(k1[1] - margin - py, py - (k0[1] + margin))
    if run_y >= run_x:      # arm along y
        sgn = 1.0 if (k1[1] - px if False else k1[1] - margin - py) >= (py - k0[1] - margin) else -1.0
        La = min(L, abs(run_y))
        a0 = [px - W_arm / 2, py, pz]
        a1 = [px + W_arm / 2, py + sgn * La, pz + H_arm]
    else:                    # arm along x
        sgn = 1.0 if (k1[0] - margin - px) >= (px - k0[0] - margin) else -1.0
        La = min(L, abs(run_x))
        a0 = [px, py - W_arm / 2, pz]
        a1 = [px + sgn * La, py + W_arm / 2, pz + H_arm]
    # clamp z inside the device too
    a0[2] = min(max(a0[2], 0.5), dev_t - 1.5)
    a1[2] = min(max(a1[2], 0.5), dev_t - 0.5)
    ant = add_box("ANTENNA_CANDIDATE", a0, a1, COL["antenna"])
    if cand.get("keepout_mm"):
        k0, k1 = cand["keepout_mm"]
        add_box("KEEPOUT", k0, k1, COL["keepout"], wire=True)

    # ---- Freestyle line-art look ---------------------------------------------
    # The device is drawn as smooth REAL-geometry edges (silhouettes +
    # creases + borders, anti-aliased curves — exactly the Blender-viewport
    # wireframe aesthetic), interiors fully transparent. Antenna solid.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12          # lines dominate; fills are invisible
    scene.cycles.transparent_max_bounces = 64   # ~30 stacked clear shells:
    # the default 8 terminates rays into black before they exit the device
    scene.render.film_transparent = True
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"

    # one shared invisible material for every device part
    clear = bpy.data.materials.new("XRAY_CLEAR")
    clear.use_nodes = True
    bsdf = clear.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value = 0.028
    bsdf.inputs["Emission Strength"].default_value = 0.0
    clear.blend_method = "BLEND"
    clear.use_backface_culling = False

    amber = bpy.data.materials.new("ANTENNA_AMBER")
    amber.use_nodes = True
    nb = amber.node_tree.nodes["Principled BSDF"]
    nb.inputs["Base Color"].default_value = COL["antenna"]
    nb.inputs["Emission Color"].default_value = COL["antenna"]
    nb.inputs["Emission Strength"].default_value = 2.2

    fam_of = {}
    for o in meshes:
        fam = fam_map.get(o.name) or _family(_material_key_of(o, mat_table))
        fam_of[o.name] = fam
        o.data.materials.clear()
        o.data.materials.append(clear)

    # collections drive per-family Freestyle line colors
    def _collection(name):
        col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if name not in {c.name for c in scene.collection.children}:
            scene.collection.children.link(col)
        return col

    col_metal = _collection("FS_METAL")
    col_diel = _collection("FS_DIEL")
    col_batt = _collection("FS_BATT")
    col_ant = _collection("FS_ANT")
    for o in meshes:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        {"metal": col_metal, "dielectric": col_diel,
         "battery": col_batt}[fam_of[o.name]].objects.link(o)

    ant.data.materials.clear(); ant.data.materials.append(amber)
    for c in list(ant.users_collection): c.objects.unlink(ant)
    col_ant.objects.link(ant)
    keep = bpy.data.objects.get("KEEPOUT")
    if keep:
        keep.data.materials.clear(); keep.data.materials.append(clear)
        for c in list(keep.users_collection): c.objects.unlink(keep)
        col_ant.objects.link(keep)

    view_layer = bpy.context.view_layer
    fs = view_layer.freestyle_settings
    fs.use_smoothness = True
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)

    def lineset(name, collection, color, thick, *, hidden=False, alpha=0.95,
                dashed=False):
        ls = fs.linesets.new(name)
        ls.select_by_collection = True
        ls.collection = collection
        ls.select_silhouette = True
        ls.select_crease = True
        ls.select_border = True
        if hidden:      # draw occluded edges too -- the x-ray depth cue
            ls.visibility = "HIDDEN"
        st = ls.linestyle
        st.color = color[:3]
        st.thickness = thick
        st.alpha = alpha
        if dashed:
            st.use_dashed_line = True
            st.dash1, st.gap1 = 8, 6
        return ls

    # visible edges: crisp and bright; hidden edges: thin and dim.
    # Battery gets the loudest treatment -- it is the classic antenna killer.
    lineset("metal",   col_metal, (0.549, 0.620, 1.000), 1.9)
    lineset("metal_h", col_metal, (0.549, 0.620, 1.000), 0.8, hidden=True, alpha=0.42)
    lineset("diel",    col_diel,  (0.412, 0.941, 0.682), 1.3)
    lineset("diel_h",  col_diel,  (0.412, 0.941, 0.682), 0.6, hidden=True, alpha=0.30)
    lineset("batt",    col_batt,  (1.000, 0.541, 0.396), 2.6)
    lineset("batt_h",  col_batt,  (1.000, 0.541, 0.396), 1.5, hidden=True, alpha=0.60)
    lineset("ant",     col_ant,   (1.000, 0.843, 0.251), 2.4)
    lineset("ant_h",   col_ant,   (1.000, 0.843, 0.251), 1.6, hidden=True, alpha=0.75)
    fs.crease_angle = math.radians(134)

    world = scene.world or bpy.data.worlds.new("black")
    scene.world = world

    # ---- cameras ------------------------------------------------------------------
    centre = (lo + hi) / 2
    diag = span.length
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []
    views = {
        "beauty_iso": (centre + Vector((diag * 0.9, -diag * 0.75, diag * 0.8)), res, res),
        "beauty_top": (centre + Vector((0.001, 0.001, diag * 1.35)), int(res * 0.62), res),
    }
    from PIL import Image
    for name, (loc, rx, ry) in views.items():
        cam_data = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cam_data)
        scene.collection.objects.link(cam)
        cam.location = loc
        d = centre - loc
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = 46
        scene.camera = cam
        scene.render.resolution_x = rx
        scene.render.resolution_y = ry
        raw = str(out / f"_fs_{name}.png")
        scene.render.filepath = raw
        bpy.ops.render.render(write_still=True)
        base = Image.new("RGBA", (rx, ry), (0, 0, 0, 255))
        base.alpha_composite(Image.open(raw).convert("RGBA"))
        final = str(out / f"placement_{name}.png")
        base.convert("RGB").save(final, dpi=(220, 220))
        Path(raw).unlink()
        written.append(final)
    return written


if __name__ == "__main__":
    blend, config, outd = sys.argv[1], sys.argv[2], sys.argv[3]
    for p in render(blend, config, outd):
        print(f"wrote {p}")
