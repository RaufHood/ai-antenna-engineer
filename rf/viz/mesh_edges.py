"""Crease edges of the real meshes, for renderers that were drawing boxes.

The offline figures reconstructed each part from its bounding box. That is
191 axis-aligned slabs where the device has 234,814 triangles, and it looks
like what it is: a blocky stand-in, in the artifacts whose whole job is to
show the actual phone the antenna is fighting.

The meshes are already on disk — blend_loader writes one STL per part beside
the manifest — so the shape is there to draw. What is *not* drawable is every
triangle: matplotlib's 3D backend is not a renderer, and a hundred thousand
filled faces would take minutes per frame.

So this extracts the same thing the live viewer draws with EdgesGeometry, and
the offline stills draw with Freestyle: creases and silhouettes. An edge
survives when it is a boundary (one adjacent face) or when its two faces meet
at more than `angle_deg`. Coplanar tessellation — the overwhelming majority —
drops out, and what remains is the drawing.

Two costs are managed rather than paid every time:

  cache    the extraction is ~0.2 s for the whole device, but a figure is
           rendered several times per run and an animation once per frame, so
           the result is memoised to an .npz next to the manifest and
           invalidated on the manifest's mtime.
  budget   ~103k segments is still more than a figure wants. The longest
           edges carry the silhouette, so a budget keeps those and drops the
           short interior detail, which is invisible at figure scale anyway.

Returns nothing when the STLs are absent (they are regenerable and gitignored,
so a fresh clone has the manifest but not the meshes). Callers fall back to
the bounding boxes and say so — a coarser drawing, never a missing one.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DEFAULT_ANGLE_DEG = 25.0
DEFAULT_BUDGET = 26_000


def _read_binary_stl(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """(tris (N,3,3), normals (N,3)) from a binary STL, or None."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) < 84:
        return None
    if raw[:5].lower() == b"solid" and b"facet" in raw[:512]:
        return None                       # ascii STL: blend_loader never writes one
    count = int.from_bytes(raw[80:84], "little")
    if count <= 0 or len(raw) < 84 + count * 50:
        return None
    rec = np.frombuffer(
        raw,
        dtype=np.dtype([("n", "<3f4"), ("v", "<3,3f4"), ("attr", "<u2")]),
        count=count,
        offset=84,
    )
    return rec["v"].astype(np.float32), rec["n"].astype(np.float32)


def _edges_of(tris: np.ndarray, normals: np.ndarray, angle_deg: float) -> np.ndarray:
    """Crease and boundary edges as (M, 2, 3) segments.

    Vertices are welded on a 1 micron grid first: STL stores every triangle
    independently, so without welding no edge is ever shared and everything
    reads as a boundary.
    """
    flat = tris.reshape(-1, 3)
    keys = np.round(flat, 3)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    faces = inverse.reshape(-1, 3)

    edges = np.sort(
        np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1
    )
    owner = np.repeat(np.arange(len(faces)), 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]

    shared = np.all(edges[1:] == edges[:-1], axis=1)
    pair = np.flatnonzero(shared)
    keep = np.zeros(len(edges), dtype=bool)

    if len(pair):
        n1, n2 = normals[owner[pair]], normals[owner[pair + 1]]
        cos = np.abs(np.einsum("ij,ij->i", n1, n2))
        keep[pair[cos < np.cos(np.radians(angle_deg))]] = True

    # Boundary edges: in neither half of a shared pair.
    paired = np.zeros(len(edges), dtype=bool)
    paired[pair] = True
    paired[pair + 1] = True
    keep |= ~paired

    picked = edges[keep]
    if not len(picked):
        return np.empty((0, 2, 3), dtype=np.float32)
    verts = flat[first]
    return np.stack([verts[picked[:, 0]], verts[picked[:, 1]]], axis=1)


def _budgeted(segments: np.ndarray, budget: int) -> np.ndarray:
    """Keep the longest `budget` segments — those carry the silhouette."""
    if len(segments) <= budget:
        return segments
    lengths = np.linalg.norm(segments[:, 1] - segments[:, 0], axis=1)
    return segments[np.argpartition(-lengths, budget)[:budget]]


def crease_edges(
    manifest: str | Path,
    *,
    angle_deg: float = DEFAULT_ANGLE_DEG,
    budget: int = DEFAULT_BUDGET,
) -> dict[str, np.ndarray] | None:
    """{part name -> (M, 2, 3) segments in manifest coordinates}, or None.

    None means the meshes are not on this machine; the caller draws boxes.
    """
    manifest = Path(manifest)
    if not manifest.exists():
        return None
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None
    parts = doc.get("parts") or []
    if not parts:
        return None

    cache = manifest.with_suffix(f".edges{int(angle_deg)}-{budget}.npz")
    stamp = str(manifest.stat().st_mtime_ns)
    if cache.exists():
        try:
            blob = np.load(cache, allow_pickle=False)
            if str(blob["__stamp__"][0]) == stamp:
                return {k: blob[k] for k in blob.files if k != "__stamp__"}
        except Exception:
            pass  # unreadable or stale cache is not an error, just a rebuild

    repo = manifest.resolve().parents[3]

    # Two asset shapes reach this point. The phone was built by load_blend and
    # ships one STL per part beside the manifest; the MacBook was built from
    # its .glb, where the geometry stays in the one file. Read whichever the
    # manifest points at — the caller only wants edges.
    gltf = None
    src = doc.get("source_glb")
    if src:
        gp = Path(src)
        if not gp.is_absolute():
            gp = repo / src
        if gp.exists():
            from rf.blend_loader.from_glb import (part_triangles, read_glb,
                                                  node_world_matrices, YUP_TO_ZUP)
            gdoc, gblob = read_glb(gp)
            gltf = (gdoc, gblob, node_world_matrices(gdoc),
                    doc.get("up_axis_fixed", "").startswith("y-up"))

    out: dict[str, np.ndarray] = {}
    total = 0
    for part in parts:
        name = part.get("blender_object") or part.get("node_path") or ""
        if not name:
            continue
        mesh = None
        if gltf is not None and part.get("glb_node") is not None:
            gdoc, gblob, worlds, yup = gltf
            i = int(part["glb_node"])
            tris = part_triangles(gdoc, gblob, gdoc["nodes"][i]["mesh"], worlds[i])
            if len(tris):
                if yup:
                    tris = tris @ YUP_TO_ZUP.T
                # glTF carries no face normals; derive them for the crease test.
                e1 = tris[:, 1] - tris[:, 0]
                e2 = tris[:, 2] - tris[:, 0]
                n = np.cross(e1, e2)
                ln = np.linalg.norm(n, axis=1, keepdims=True)
                mesh = (tris.astype(np.float32),
                        (n / np.where(ln == 0, 1, ln)).astype(np.float32))
        if mesh is None:
            rel = part.get("stl_path")
            if not rel:
                continue
            stl = Path(rel)
            if not stl.is_absolute():
                stl = repo / rel
            mesh = _read_binary_stl(stl)
        if mesh is None:
            continue
        segs = _edges_of(mesh[0], mesh[1], angle_deg)
        if len(segs):
            out[name] = segs
            total += len(segs)
    if not out:
        return None

    # Spend the budget across parts in proportion to what each asked for, so a
    # single dense part cannot crowd out the rest of the phone.
    if total > budget:
        for name, segs in out.items():
            out[name] = _budgeted(segs, max(24, int(budget * len(segs) / total)))

    try:
        np.savez_compressed(cache, __stamp__=np.array([stamp]), **out)
    except Exception:
        pass  # a read-only checkout still renders, it just recomputes
    return out
