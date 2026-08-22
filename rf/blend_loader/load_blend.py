"""Load a labeled .blend + its materials.json sidecar into a solver-agnostic
device manifest, and export one STL per part for the EM mesher.

Runs inside rf/blend_loader/.venv (has bpy). openEMS runs elsewhere
(rf/.venv, no bpy) and never imports bpy — the manifest + STLs written here
are the hand-off artifact between the two, so the two dependency sets never
mix. (This used to be a top-level backend/ folder; moved under rf/ and
renamed to avoid clashing with "the backend" meaning the FastAPI service a
teammate is building separately — see rf/progress_simulation.md.)

Convention (from data/*/materials.json "how_material_identity_is_carried"):
  - object NAME is "<node_path>__<material_key>"
  - object custom properties "material_key" and "node_path" (authoritative
    when present; the name is the fallback parse)
  - materials.json["parts"][i]["em_from_vocabulary"] carries eps_r /
    sigma_S_per_m per part — that's the EM data, the vocabulary block is
    just where it's deduplicated from.

Usage (from the repo root):
    rf/blend_loader/.venv/Scripts/python -m rf.blend_loader.load_blend \
        data/bellota_hunting_axe_8133/bellota_hunting_axe_8133.blend \
        --materials data/bellota_hunting_axe_8133/materials.json \
        --out rf/blend_loader/out/bellota_hunting_axe_8133
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def _bbox_mm(obj) -> list[list[float]]:
    """World-space AABB of obj.bound_box, in the file's native units.

    materials.json declares "units": "mm" for this asset family, i.e. 1
    Blender unit = 1 mm by modeling convention (not by scene unit_settings,
    which is the usual hard-surface/CAD-asset practice). We pass raw
    coordinates through and trust that declaration rather than
    scene.unit_settings.scale_length, which is frequently left at its
    default irrespective of the modeling convention actually used.
    """
    import mathutils
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]


def _parse_identity(obj) -> tuple[str, str]:
    if "node_path" in obj and "material_key" in obj:
        return obj["node_path"], obj["material_key"]
    if "__" in obj.name:
        node_path, _, material_key = obj.name.rpartition("__")
        return node_path, material_key
    return obj.name, "unknown"


def load_device_from_blend(
    blend_path: str,
    materials_json_path: str | None = None,
    export_stl_dir: str | None = None,
) -> dict:
    bpy.ops.wm.open_mainfile(filepath=str(Path(blend_path).resolve()))

    manifest = {}
    if materials_json_path:
        manifest = json.loads(Path(materials_json_path).read_text())
    parts_by_node = {p["node_path"]: p for p in manifest.get("parts", [])}

    if export_stl_dir:
        Path(export_stl_dir).mkdir(parents=True, exist_ok=True)

    parts = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        node_path, material_key = _parse_identity(obj)
        meta = parts_by_node.get(node_path, {})
        em = meta.get("em_from_vocabulary") or manifest.get(
            "material_vocabulary_used", {}
        ).get(material_key, {})

        part = {
            "node_path": node_path,
            "blender_object": obj.name,
            "material_key": material_key,
            "eps_r": em.get("eps_r"),
            "sigma_S_per_m": em.get("sigma_S_per_m"),
            # mu_r isn't in the vocabulary at all (assumed 1 by omission);
            # materials.json's material_gaps flags this explicitly for
            # steel as the single most consequential gap on this object.
            "mu_r": 1.0,
            "mu_r_gap_flagged": material_key == "steel",
            "bbox_mm": _bbox_mm(obj),
            "tris": len(obj.data.polygons),
            "mass_g": meta.get("mass_g"),
            "stl_path": None,
        }

        if export_stl_dir:
            stl_path = str(Path(export_stl_dir) / f"{node_path}.stl")
            for o in bpy.data.objects:
                o.select_set(o is obj)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.wm.stl_export(
                filepath=stl_path,
                export_selected_objects=True,
                global_scale=1.0,
            )
            part["stl_path"] = stl_path

        parts.append(part)

    return {
        "device_id": manifest.get("model", Path(blend_path).stem),
        "name": manifest.get("object", Path(blend_path).stem),
        "units": manifest.get("units", "mm"),
        "source_blend": str(blend_path),
        "blender_version_used": bpy.app.version_string,
        "blender_version_authored": manifest.get("blender_version"),
        "material_gaps": manifest.get("material_gaps", []),
        "parts": parts,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("blend_path")
    ap.add_argument("--materials", default=None, help="materials.json sidecar")
    ap.add_argument("--out", default=None,
                     help="output dir; writes device.json + one STL per part")
    args = ap.parse_args()

    export_stl_dir = args.out if args.out else None
    device = load_device_from_blend(args.blend_path, args.materials, export_stl_dir)

    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        out_json = Path(args.out) / "device.json"
        out_json.write_text(json.dumps(device, indent=2))
        print(f"wrote {out_json}", file=sys.stderr)

    print(json.dumps(device, indent=2))


if __name__ == "__main__":
    main()
