"""Build a device manifest from a .glb, without Blender.

`load_blend.py` is the authoritative path: it reads the labelled .blend and
its materials.json sidecar inside an interpreter that has bpy. That is the
right tool when you have both, and it is what produced the iPhone manifest.

It is the wrong tool for adding a second device an hour before a deadline.
bpy is a 220 MB download that is not installed here, and the asset that
matters — the MacBook — already ships the glTF the viewer loads. A .glb is
JSON plus a binary blob: it carries the node names, and every accessor
declares the min/max of its positions, which is the bounding box already
computed. The one thing it does not carry is the EM vocabulary, and that is
thirteen constants shared with the phone.

So this reads what the .glb has and looks up the rest. Same output schema as
load_blend, so everything downstream — classify, the placement scan, the
renderers — cannot tell which built it.

    python -m rf.blend_loader.from_glb <in.glb> --out <dir> \\
        --device-id macbook_pro_14 --name "Apple MacBook Pro 14 (2024)"

Both paths agree on the convention: an object is named
`<node_path>__<material_key>`.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
from pathlib import Path

import numpy as np

# The EM vocabulary, shared with data/*/materials.json. Values are the ones
# already in rf/blend_loader/out/device.json for the phone, so the two devices
# are judged against the same physics.
EM: dict[str, dict[str, float]] = {
    "abs": {"eps_r": 2.9, "sigma_S_per_m": 0.005},
    "aluminium": {"eps_r": 1.0, "sigma_S_per_m": 35_000_000.0},
    "cfrp": {"eps_r": 4.5, "sigma_S_per_m": 10_000.0},
    "copper": {"eps_r": 1.0, "sigma_S_per_m": 58_000_000.0},
    "foam": {"eps_r": 1.1, "sigma_S_per_m": 0.0001},
    "fr4": {"eps_r": 4.4, "sigma_S_per_m": 0.02},
    # G10 is FR4's un-flame-retarded sibling: same glass-epoxy laminate, same
    # dielectric behaviour to within the tolerance any of these numbers carry.
    "g10": {"eps_r": 4.8, "sigma_S_per_m": 0.02},
    "lens": {"eps_r": 5.5, "sigma_S_per_m": 0.003},
    "lipo": {"eps_r": 1.0, "sigma_S_per_m": 100_000.0},
    "nylon": {"eps_r": 2.9, "sigma_S_per_m": 0.002},
    "pet": {"eps_r": 3.0, "sigma_S_per_m": 0.006},
    "rubber": {"eps_r": 3.0, "sigma_S_per_m": 0.005},
    "stainless": {"eps_r": 1.0, "sigma_S_per_m": 1_100_000.0},
    "steel": {"eps_r": 1.0, "sigma_S_per_m": 1_450_000.0},
}


def read_glb(path: Path) -> tuple[dict, bytes]:
    """(glTF JSON, binary chunk). Also accepts a .gltf with an embedded buffer."""
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        return json.loads(raw.decode("utf-8")), b""
    _magic, _ver, _len = struct.unpack("<4sII", raw[:12])
    off, doc, blob = 12, None, b""
    while off + 8 <= len(raw):
        clen, ctype = struct.unpack("<II", raw[off:off + 8])
        chunk = raw[off + 8:off + 8 + clen]
        if ctype == 0x4E4F534A:            # 'JSON'
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:          # 'BIN'
            blob = chunk
        off += 8 + clen + (-clen % 4)
    if doc is None:
        raise ValueError(f"{path}: no JSON chunk")
    return doc, blob


def _buffer_bytes(doc: dict, blob: bytes, index: int) -> bytes:
    buf = doc["buffers"][index]
    uri = buf.get("uri")
    if uri is None:
        return blob
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    raise ValueError("external buffer files are not supported; export a .glb")


_COMPONENT = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_accessor(doc: dict, blob: bytes, index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    n = acc["count"]
    per = _COUNT[acc["type"]]
    dtype = np.dtype("<" + _COMPONENT[acc["componentType"]])
    view = doc["bufferViews"][acc["bufferView"]]
    data = _buffer_bytes(doc, blob, view.get("buffer", 0))
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or per * dtype.itemsize
    if stride == per * dtype.itemsize:
        flat = np.frombuffer(data, dtype=dtype, count=n * per, offset=start)
        return flat.reshape(n, per) if per > 1 else flat
    # Interleaved: walk the stride.
    out = np.empty((n, per), dtype=dtype)
    for i in range(n):
        o = start + i * stride
        out[i] = np.frombuffer(data, dtype=dtype, count=per, offset=o)
    return out


def node_world_matrices(doc: dict) -> dict[int, np.ndarray]:
    """Every node's world transform, walking the scene graph from the roots."""
    nodes = doc.get("nodes", [])
    out: dict[int, np.ndarray] = {}

    def local(node: dict) -> np.ndarray:
        if "matrix" in node:
            return np.array(node["matrix"], dtype=float).reshape(4, 4).T
        m = np.eye(4)
        if "scale" in node:
            m = m @ np.diag([*node["scale"], 1.0])
        if "rotation" in node:
            x, y, z, w = node["rotation"]
            r = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
                [0, 0, 0, 1],
            ])
            m = r @ m
        if "translation" in node:
            t = np.eye(4)
            t[:3, 3] = node["translation"]
            m = t @ m
        return m

    def walk(index: int, parent: np.ndarray) -> None:
        world = parent @ local(nodes[index])
        out[index] = world
        for child in nodes[index].get("children", []) or []:
            walk(child, world)

    roots = set(range(len(nodes)))
    for node in nodes:
        for child in node.get("children", []) or []:
            roots.discard(child)
    for r in sorted(roots):
        walk(r, np.eye(4))
    return out


def part_triangles(doc: dict, blob: bytes, mesh_index: int,
                   world: np.ndarray) -> np.ndarray:
    """(N, 3, 3) world-space triangles for one mesh."""
    tris: list[np.ndarray] = []
    for prim in doc["meshes"][mesh_index].get("primitives", []):
        pos = prim.get("attributes", {}).get("POSITION")
        if pos is None:
            continue
        v = np.asarray(read_accessor(doc, blob, pos), dtype=float)
        idx = (np.asarray(read_accessor(doc, blob, prim["indices"])).ravel()
               if "indices" in prim else np.arange(len(v)))
        hom = np.concatenate([v, np.ones((len(v), 1))], axis=1) @ world.T
        tris.append(hom[idx.astype(int), :3].reshape(-1, 3, 3))
    if not tris:
        return np.empty((0, 3, 3))
    return np.concatenate(tris, axis=0)


# glTF's own convention is Y-up; Blender exports Z-up when told to. Everything
# downstream here — candidate.position_mm, rf/placement.py, the viewer, the
# renderers — reads z as thickness, so a Y-up export has to be turned once, at
# the point it becomes a manifest, rather than corrected in five places later.
YUP_TO_ZUP = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)


def build(glb: Path, device_id: str, name: str, *, scale: float = 1.0,
          yup: bool = False) -> dict:
    doc, blob = read_glb(glb)
    worlds = node_world_matrices(doc)
    gaps: set[str] = set()
    parts: list[dict] = []

    for i, node in enumerate(doc.get("nodes", [])):
        if "mesh" not in node:
            continue
        obj = node.get("name") or f"node_{i}"
        node_path, _, key = obj.partition("__")
        key = key.lower()
        tris = part_triangles(doc, blob, node["mesh"], worlds[i]) * scale
        if yup and len(tris):
            tris = tris @ YUP_TO_ZUP.T
        if not len(tris):
            continue
        flat = tris.reshape(-1, 3)
        lo, hi = flat.min(axis=0), flat.max(axis=0)
        em = EM.get(key)
        if em is None:
            gaps.add(key or "(unnamed)")
        parts.append({
            "blender_object": obj,
            "node_path": node_path or obj,
            "material_key": key,
            "bbox_mm": [[round(float(v), 4) for v in lo],
                        [round(float(v), 4) for v in hi]],
            "eps_r": (em or {}).get("eps_r"),
            "sigma_S_per_m": (em or {}).get("sigma_S_per_m"),
            "mu_r": 1.0,
            "tris": int(len(tris)),
            "stl_path": None,          # geometry stays in the .glb
            "glb_node": i,
        })

    return {
        "device_id": device_id,
        "name": name,
        "units": "mm",
        "source_glb": str(glb),
        "up_axis_fixed": "y-up -> z-up" if yup else "z-up (as exported)",
        "material_gaps": sorted(gaps),
        "parts": parts,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("glb", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device-id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--scale", type=float, default=1.0,
                    help="multiply coordinates (use if the export is in metres)")
    ap.add_argument("--yup", action="store_true",
                    help="the export is glTF-standard Y-up; turn it to Z-up")
    args = ap.parse_args()

    doc = build(args.glb, args.device_id, args.name, scale=args.scale,
                yup=args.yup)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "device.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    lo = np.array([p["bbox_mm"][0] for p in doc["parts"]]).min(axis=0)
    hi = np.array([p["bbox_mm"][1] for p in doc["parts"]]).max(axis=0)
    print(f"{len(doc['parts'])} parts, "
          f"{sum(p['tris'] for p in doc['parts'])} triangles")
    print(f"extent {hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} x {hi[2] - lo[2]:.1f} mm")
    if doc["material_gaps"]:
        print(f"material gaps (no EM data): {doc['material_gaps']}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
