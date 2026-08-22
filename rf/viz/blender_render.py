"""The beauty renderer: x-ray line art of the real device, straight from the .blend.

`placement3d.py` is the *technical* view (bboxes, coordinate frame, dimension
callouts). This module is the *beauty* view, and it is the visual language of
the whole project: the actual iPhone meshes rendered as smooth Freestyle
edges — silhouettes, creases and borders, anti-aliased curves — coloured by
material family, interiors fully transparent, on true black. The antenna
candidate and its keep-out are injected at their corner-anchored coordinates
and drawn solid amber so the placement reads instantly.

It serves three consumers, so nothing else has to re-implement the look:

    stills    two hero frames (iso + top)                -> placement_beauty_*.png
    orbit     N frames orbiting the device               -> orbit_frames/*.png
    overlay   ONE orthographic top view, transparent bg  -> field_overlay.png
              + the exact mm extent it covers, so the field animation can
              composite the real device over the |E| map in physical units

Runs in the bpy env, NOT .venv-viz:

    ~/micromamba/envs/bpy/bin/python -m rf.viz.blender_render \
        <blend> <config.json> <out_dir> [stills|orbit|overlay|all] [n_frames] [res]

Palette mirrors rf/viz/theme.py (keep the two in sync by eye — this module
cannot import it, it runs under a different interpreter).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# theme.py PALETTE as RGBA 0-1
COL = {
    "metal":      (0.549, 0.620, 1.000, 1.0),   # 8c9eff
    "dielectric": (0.412, 0.941, 0.682, 1.0),   # 69f0ae
    "battery":    (1.000, 0.541, 0.396, 1.0),   # ff8a65
    "antenna":    (1.000, 0.843, 0.251, 1.0),   # ffd740
}
LINE = {k: v[:3] for k, v in COL.items()}

METALS = ("alumin", "copper", "steel", "titan", "gold", "metal", "stainless")


def _family(mat_key: str) -> str:
    k = (mat_key or "").lower()
    if "battery" in k or "lithium" in k or "lipo" in k:
        return "battery"
    if any(m in k for m in METALS):
        return "metal"
    return "dielectric"


def _load_part_families(device_json: Path) -> dict:
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


# --------------------------------------------------------------------- scene

def build_scene(blend_path: str, config_path: str,
                device_json: str = "rf/blend_loader/out/device.json") -> dict:
    """Open the .blend, apply the x-ray look, inject the antenna candidate.

    Returns the geometry context every renderer needs: world-space device
    bounds, the mm<->blend unit scale, and the antenna object.
    """
    cfg = json.loads(Path(config_path).read_text())
    cand = cfg["candidate"]
    mats_path = Path(blend_path).parent / "materials.json"
    mat_table = (json.loads(mats_path.read_text()).get("materials", {})
                 if mats_path.exists() else {})

    bpy.ops.wm.open_mainfile(filepath=str(Path(blend_path).resolve()))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]

    wpts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(p.x for p in wpts), min(p.y for p in wpts), min(p.z for p in wpts)))
    hi = Vector((max(p.x for p in wpts), max(p.y for p in wpts), max(p.z for p in wpts)))
    span = hi - lo
    unit = 0.001 if max(span) < 1.0 else 1.0     # blend in metres vs mm
    dev_mm = Vector((span.x / unit, span.y / unit, span.z / unit))

    fam_map = _load_part_families(Path(device_json))
    fam_of = {o.name: (fam_map.get(o.name) or _family(_material_key_of(o, mat_table)))
              for o in meshes}

    # ---- antenna: a printed strip that must stay INSIDE the device --------------
    # Clamp hard against the real device bounds (not just the keep-out): the
    # keep-out can legitimately be flush with the enclosure edge, and an arm
    # that reaches its far face pokes out through the chassis. Everything is
    # inset by EDGE_INSET from the true walls.
    EDGE_INSET = 2.0            # mm of chassis wall to stay clear of
    W_ARM, H_ARM = 1.8, 0.9     # realistic printed-strip cross-section
    px, py, pz = (float(v) for v in cand["position_mm"])
    L = float(cand["length_mm"])
    k0, k1 = cand.get("keepout_mm") or ([0, 0, 0], list(dev_mm))
    # usable box = keep-out intersected with the inset device volume
    b0 = [max(k0[i], EDGE_INSET) for i in range(3)]
    b1 = [min(k1[i], dev_mm[i] - EDGE_INSET) for i in range(3)]
    px = min(max(px, b0[0] + W_ARM), b1[0] - W_ARM)
    py = min(max(py, b0[1] + W_ARM), b1[1] - W_ARM)
    pz = min(max(pz, b0[2]), b1[2] - H_ARM)

    run_x_pos, run_x_neg = b1[0] - px, px - b0[0]
    run_y_pos, run_y_neg = b1[1] - py, py - b0[1]
    best = max((run_y_pos, "y", 1.0), (run_y_neg, "y", -1.0),
               (run_x_pos, "x", 1.0), (run_x_neg, "x", -1.0))
    run, axis, sgn = best
    La = max(4.0, min(L, run))          # never longer than the free run
    if axis == "y":
        a0 = [px - W_ARM / 2, min(py, py + sgn * La), pz]
        a1 = [px + W_ARM / 2, max(py, py + sgn * La), pz + H_ARM]
    else:
        a0 = [min(px, px + sgn * La), py - W_ARM / 2, pz]
        a1 = [max(px, px + sgn * La), py + W_ARM / 2, pz + H_ARM]

    def add_box(name, p0_mm, p1_mm):
        p0 = lo + Vector([v * unit for v in p0_mm])
        p1 = lo + Vector([v * unit for v in p1_mm])
        bpy.ops.mesh.primitive_cube_add(location=(p0 + p1) / 2)
        ob = bpy.context.object
        ob.name = name
        ob.scale = (p1 - p0) / 2
        return ob

    ant = add_box("ANTENNA_CANDIDATE", a0, a1)

    # ---- Freestyle line-art look -----------------------------------------------
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.transparent_max_bounces = 64   # ~30 stacked clear shells; the
    # default 8 terminates rays inside the device and the interior goes black
    scene.render.film_transparent = True
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"

    clear = bpy.data.materials.new("XRAY_CLEAR")
    clear.use_nodes = True
    clear.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.028
    clear.blend_method = "BLEND"

    amber = bpy.data.materials.new("ANTENNA_AMBER")
    amber.use_nodes = True
    nb = amber.node_tree.nodes["Principled BSDF"]
    nb.inputs["Base Color"].default_value = COL["antenna"]
    nb.inputs["Emission Color"].default_value = COL["antenna"]
    nb.inputs["Emission Strength"].default_value = 2.2

    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(clear)
    ant.data.materials.clear()
    ant.data.materials.append(amber)

    def _collection(name):
        col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if name not in {c.name for c in scene.collection.children}:
            scene.collection.children.link(col)
        return col

    cols = {f: _collection(f"FS_{f.upper()}")
            for f in ("metal", "dielectric", "battery", "antenna")}
    for o in meshes:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        cols[fam_of[o.name]].objects.link(o)
    for c in list(ant.users_collection):
        c.objects.unlink(ant)
    cols["antenna"].objects.link(ant)

    fs = bpy.context.view_layer.freestyle_settings
    fs.use_smoothness = True                 # smooth, anti-aliased curves
    fs.crease_angle = math.radians(134)
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)

    def lineset(name, fam, thick, *, hidden=False, alpha=0.95):
        ls = fs.linesets.new(name)
        ls.select_by_collection = True
        ls.collection = cols[fam]
        ls.select_silhouette = ls.select_crease = ls.select_border = True
        if hidden:                           # occluded edges = the x-ray depth cue
            ls.visibility = "HIDDEN"
        ls.linestyle.color = LINE[fam]
        ls.linestyle.thickness = thick
        ls.linestyle.alpha = alpha

    lineset("metal", "metal", 1.9)
    lineset("metal_h", "metal", 0.8, hidden=True, alpha=0.42)
    lineset("diel", "dielectric", 1.3)
    lineset("diel_h", "dielectric", 0.6, hidden=True, alpha=0.30)
    lineset("batt", "battery", 2.6)          # the classic antenna killer: loudest
    lineset("batt_h", "battery", 1.5, hidden=True, alpha=0.60)
    lineset("ant", "antenna", 2.4)
    lineset("ant_h", "antenna", 1.6, hidden=True, alpha=0.75)

    return {"scene": scene, "lo": lo, "hi": hi, "span": span, "unit": unit,
            "dev_mm": dev_mm, "centre": (lo + hi) / 2, "diag": span.length,
            "antenna": ant, "candidate": cand}


# ------------------------------------------------------------------- rendering

def _camera(scene, name, loc, look_at, lens=46.0, ortho=None):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (look_at - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    if ortho is not None:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.lens = lens
    scene.camera = cam
    return cam


def _render(scene, path, rx, ry, *, on_black: bool):
    scene.render.resolution_x, scene.render.resolution_y = rx, ry
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if on_black:
        from PIL import Image
        base = Image.new("RGBA", (rx, ry), (0, 0, 0, 255))
        base.alpha_composite(Image.open(path).convert("RGBA"))
        base.convert("RGB").save(path, dpi=(220, 220))
    return str(path)


def render_stills(ctx, out_dir, res=2200) -> list[str]:
    scene, centre, diag = ctx["scene"], ctx["centre"], ctx["diag"]
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []
    for tag, loc, rx, ry in [
        ("iso", centre + Vector((diag * .9, -diag * .75, diag * .8)), res, res),
        ("top", centre + Vector((1e-3, 1e-3, diag * 1.35)), int(res * .62), res),
    ]:
        _camera(scene, tag, loc, centre)
        written.append(_render(scene, out / f"placement_beauty_{tag}.png",
                               rx, ry, on_black=True))
    return written


def render_orbit_frames(ctx, out_dir, n_frames=72, res=1100, elev=0.42) -> list[str]:
    """N frames orbiting the device, eased so the loop reads as deliberate."""
    scene, centre, diag = ctx["scene"], ctx["centre"], ctx["diag"]
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    written = []
    for i in range(n_frames):
        u = i / n_frames
        eased = u - math.sin(2 * math.pi * u) / (2 * math.pi)   # slow at the seam
        a = 2 * math.pi * eased - math.radians(140)
        loc = centre + Vector((math.cos(a) * diag * 1.05,
                               math.sin(a) * diag * 1.05,
                               diag * elev))
        _camera(scene, f"orb{i}", loc, centre, lens=50)
        written.append(_render(scene, out / f"orbit_{i:04d}.png",
                               res, res, on_black=True))
    return written


def render_overlay(ctx, out_path, res=1600) -> dict:
    """One ORTHOGRAPHIC top view on a transparent background.

    Orthographic is the point: the projection is linear, so the PNG maps 1:1
    onto a known millimetre rectangle and `anim_field` can composite the real
    device over the |E| map in physical units with no perspective error.
    Returns {'path', 'extent_mm': [x0, x1, y0, y1]} in the corner-anchored
    frame candidate coordinates use.
    """
    scene, centre, dev = ctx["scene"], ctx["centre"], ctx["dev_mm"]
    unit = ctx["unit"]
    # Lines only: the faint volumetric fills that give the hero stills their
    # depth would tint the |E| map underneath. Zero the clear material's
    # alpha so the composite carries nothing but Freestyle strokes.
    clear = bpy.data.materials.get("XRAY_CLEAR")
    if clear:
        clear.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.0
    # film_transparent only reaches the file if the output format carries an
    # alpha channel: Blender defaults to RGB and silently drops it, which
    # ships a fully opaque overlay that hides whatever it is composited over.
    scene.render.image_settings.color_mode = "RGBA"
    # This overlay is composited over a bright |E| heatmap, not over black:
    # the stroke weights tuned for the hero stills disappear against orange.
    # Thicken and fully opacify every lineset for this pass only.
    for ls in bpy.context.view_layer.freestyle_settings.linesets:
        ls.linestyle.thickness *= 2.4
        ls.linestyle.alpha = 1.0
    pad_mm = 6.0
    w_mm, l_mm = float(dev.x) + 2 * pad_mm, float(dev.y) + 2 * pad_mm
    ortho = max(w_mm, l_mm) * unit                   # ortho_scale spans the long side
    rx = max(2, int(round(res * w_mm / max(w_mm, l_mm))) // 2 * 2)
    ry = max(2, int(round(res * l_mm / max(w_mm, l_mm))) // 2 * 2)

    _camera(scene, "ortho_top", centre + Vector((0, 0, ctx["diag"])), centre,
            ortho=ortho)
    out = Path(out_path); out.parent.mkdir(parents=True, exist_ok=True)
    _render(scene, out, rx, ry, on_black=False)      # keep alpha

    # the ortho frame is centred on the device; convert to the corner frame
    half_w = ortho / unit * (rx / max(rx, ry)) / 2
    half_l = ortho / unit * (ry / max(rx, ry)) / 2
    cx, cy = float(dev.x) / 2, float(dev.y) / 2
    extent = [cx - half_w, cx + half_w, cy - half_l, cy + half_l]
    meta = {"path": str(out), "extent_mm": extent}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    blend, config, outd = sys.argv[1], sys.argv[2], sys.argv[3]
    what = sys.argv[4] if len(sys.argv) > 4 else "all"
    n_frames = int(sys.argv[5]) if len(sys.argv) > 5 else 72
    res = int(sys.argv[6]) if len(sys.argv) > 6 else 0

    ctx = build_scene(blend, config)
    if what in ("stills", "all"):
        for p in render_stills(ctx, outd, res or 2200):
            print(f"wrote {p}")
    if what in ("overlay", "all"):
        m = render_overlay(ctx, Path(outd) / "field_overlay.png", res or 1600)
        print(f"wrote {m['path']}  extent_mm={m['extent_mm']}")
    if what in ("orbit", "all"):
        frames = render_orbit_frames(ctx, Path(outd) / "orbit_frames",
                                     n_frames, res or 1100)
        print(f"wrote {len(frames)} orbit frames -> {Path(outd) / 'orbit_frames'}")
