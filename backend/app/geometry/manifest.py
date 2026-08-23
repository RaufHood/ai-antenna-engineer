"""Turn a blend_loader manifest into the geometry dict `classify()` reads.

`app/geometry/extract.py` produces geometry.json by running Blender, which
needs a bpy interpreter and a .blend on disk. But the iPhone 15 Pro manifest
is already committed at rf/blend_loader/out/device.json — 191 parts with real
bounding boxes and real material keys — so the default device does not have to
be a nine-box slab while the viewer draws an actual phone.

That mismatch was not cosmetic. The solver read "Handset A", a generic
147.6 x 71.6 x 7.8 mm block with 9 components, while the screen showed a
device with a titanium frame, a battery, shield cans and a camera plateau. Every
clearance number, every anchor, and every "nearest metal" the agent reasoned
about belonged to a phone nobody was looking at.

The two shapes differ only in derived fields, so this is an adapter, not an
importer: `size_mm` and per-part `extent_mm` come straight from the bounding
boxes, and coordinates are shifted so the device's minimum corner sits at the
origin — the corner-anchored frame every downstream contract already uses
(candidate.position_mm, rf/placement.py, rf/viz).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = REPO / "rf" / "blend_loader" / "out" / "device.json"

# The devices that ship with the app. Each is a manifest the solver reads plus
# the glTF the viewer draws, and the two describe the same object — that
# agreement is the whole point of loading from a manifest rather than a canned
# spec. `id` is what the API and the client pass around.
BUILTIN: list[dict] = [
    {
        "id": "apple_iphone_15_pro",
        "name": "Apple iPhone 15 Pro",
        "short": "iPhone 15 Pro",
        "manifest": REPO / "rf" / "blend_loader" / "out" / "device.json",
        "model_url": "/models/iphone15pro.glb",
        "blurb": "191 parts. Titanium frame, one battery, shield cans.",
    },
    {
        "id": "macbook_pro_14",
        "name": "Apple MacBook Pro 14 (2024, M4 Pro)",
        "short": "MacBook Pro 14",
        "manifest": REPO / "rf" / "blend_loader" / "out" / "macbook_pro_14" / "device.json",
        "model_url": "/models/macbook_pro_14.glb",
        # The glTF is Y-up; the manifest was turned to Z-up when it was built,
        # so the viewer has to turn the model the same way to agree with it.
        "viewer_yup": True,
        "blurb": "449 parts. Aluminium unibody, six speakers, three-cell battery.",
    },
]


def builtin(device_id: str | None) -> dict | None:
    """One entry of the built-in catalogue, or None."""
    if not device_id:
        return None
    return next((d for d in BUILTIN if d["id"] == device_id), None)


def available() -> list[dict]:
    """The built-ins whose manifest is actually on this machine."""
    return [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}
        for d in BUILTIN
        if Path(d["manifest"]).exists()
    ]


def geometry_from_manifest(path: str | Path | None = None) -> dict | None:
    """blend_loader device.json -> the geometry dict classify() expects.

    Returns None when the manifest is missing or unusable, so the caller can
    fall back to the canned spec instead of failing to start.
    """
    p = Path(path) if path else DEFAULT_MANIFEST
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    raw = [q for q in doc.get("parts", []) if q.get("bbox_mm")]
    if not raw:
        return None

    corners = [c for q in raw for c in q["bbox_mm"]]
    origin = [min(c[i] for c in corners) for i in range(3)]
    hi = [max(c[i] for c in corners) for i in range(3)]
    size_mm = [round(hi[i] - origin[i], 3) for i in range(3)]

    parts = []
    for q in raw:
        (x0, y0, z0), (x1, y1, z1) = q["bbox_mm"]
        lo = [x0 - origin[0], y0 - origin[1], z0 - origin[2]]
        up = [x1 - origin[0], y1 - origin[1], z1 - origin[2]]
        node = q.get("node_path") or q.get("blender_object") or "part"
        parts.append({
            # classify() keys parts by blender_object and reads node_path for
            # role hints; the manifest's node_path carries both meanings.
            "blender_object": q.get("blender_object") or node,
            "node_path": node,
            "material_key": q.get("material_key") or "",
            "bbox_mm": [[round(v, 3) for v in lo], [round(v, 3) for v in up]],
            "extent_mm": [round(up[i] - lo[i], 3) for i in range(3)],
            "eps_r": q.get("eps_r"),
            "sigma_S_per_m": q.get("sigma_S_per_m"),
            "tris": q.get("tris"),
        })

    return {
        "device_id": str(doc.get("device_id") or p.parent.name),
        "name": str(doc.get("name") or "device"),
        "size_mm": size_mm,
        "parts": parts,
        # The manifest is authored in millimetres with a known orientation, so
        # nothing was guessed and classify() should raise no unit or
        # orientation ambiguity for it.
        "frame": {"unit_confidence": "high", "unit_source": "manifest",
                  "orientation_fix": {}},
        "source_manifest": str(p),
    }


def default_device_spec(band_ids: list[str] | None = None,
                        device_id: str | None = None):
    """A built-in device as a DeviceSpec, or None if its manifest is absent.

    Used so the solver and the viewer describe the same object. Falls back to
    the canned spec at the call site.
    """
    entry = builtin(device_id)
    geometry = geometry_from_manifest(entry["manifest"] if entry else None)
    if geometry is None:
        return None
    from app.geometry.classify import classify
    try:
        return classify(geometry, band_ids=band_ids,
                        geometry_path=geometry["source_manifest"])
    except Exception:
        return None
