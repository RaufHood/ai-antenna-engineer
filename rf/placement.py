"""Physics-informed placement screening — the agent's cheap oracle.

An FDTD solve is the ground truth, but it is not free and it is not
*explanatory*: it says "S11 is -1.4 dB", never "because your arm is 0.6 mm
from the stainless midframe and the only way out is through the battery".
This module answers the second question in milliseconds, straight from the
device manifest's bounding boxes, so the agent loop can

1. **reject illegal candidates before spending a solve** — outside the
   chassis, intersecting the battery, buried in the logic board;
2. **rank the legal ones** by how likely they are to radiate, and simulate
   the promising ones first;
3. **explain a bad solve afterwards**, naming the offending part.

Three analyses, all derived from the same part list:

    legality()   — is this position physically buildable?
    clearance()  — what is around the antenna, and is it metal or plastic?
    escape()     — can the signal actually leave the phone?

`screen()` runs all three and returns one verdict dict. `scan()` sweeps a
grid of positions and returns the field the agent (or a heatmap) can search.

Everything works in the corner-anchored millimetre frame that
`candidate.position_mm` uses: (0, 0, 0) is the device's minimum corner.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

# Conductivity above which a part behaves as a mirror at GHz, not a radome.
# Chosen well below any real metal (stainless ~1.4e6 S/m) and well above any
# real plastic (ABS ~5e-3 S/m), so the split is never ambiguous.
METAL_SIGMA = 1.0e4

# Metal this close to a radiator dominates its impedance. lambda/20 at
# GPS L1 (190 mm) is ~9.5 mm; we report the raw distance and let the caller
# compare against the band in play.
NEARFIELD_MM = 12.0      # fallback when the band is unknown


def nearfield_for(f_ghz: float | None) -> float:
    """The near-field radius that matters at this frequency: lambda/20.

    Metal inside a twentieth of a wavelength dominates the radiator's
    impedance — that is the threshold this codebase reasons with everywhere
    else. Holding it at a constant 12 mm made the screening frequency-blind:
    a 900 MHz design and a 5 GHz design were judged against the same 12 mm,
    so every band produced the same placement map of the same phone. It is
    17.6 mm at B5 and 2.7 mm at Wi-Fi 5, and those are different maps.
    """
    if not f_ghz or f_ghz <= 0:
        return NEARFIELD_MM
    return (299.792458 / float(f_ghz)) / 20.0

WALL_INSET_MM = 1.5      # chassis side wall the antenna must stay clear of
# Through-thickness the same 1.5 mm is not a margin, it is a ban: an 11 mm
# phone has ~2.4 mm above the ground plane, so insetting 1.5 mm from both faces
# leaves nowhere legal and the scan returns an empty device. A back cover is a
# sub-millimetre shell and a handset antenna sits against its inner face.
WALL_INSET_Z_MM = 0.5

# The printed strip itself: 1.8 mm wide, 0.9 mm proud of the feed plane.
ARM_W_MM = 1.8
ARM_H_MM = 0.9

# Per-axis, in the corner frame: x, y are side walls; z is the cover.
WALL_INSET_XYZ = (WALL_INSET_MM, WALL_INSET_MM, WALL_INSET_Z_MM)
SOFT_MATERIALS = ("foam", "abs", "rubber", "nylon", "pet", "adhesive")

# A part whose footprint covers at least this share of the device is an
# enclosure layer, not a component you can collide with.
SHELL_FOOTPRINT_FRAC = 0.40


# --------------------------------------------------------------- device model

@dataclass
class Part:
    name: str
    material_key: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    sigma: float
    eps_r: float

    @property
    def is_metal(self) -> bool:
        return self.sigma >= METAL_SIGMA

    is_shell: bool = False   # spans most of the device: an enclosure layer,
                             # not a discrete component (set by Device)

    @property
    def is_soft(self) -> bool:
        """Crushable/press-fit materials — overlapping these is a design
        change (shave the foam), not a physical impossibility."""
        k = self.material_key.lower()
        return any(s in k for s in SOFT_MATERIALS)


@dataclass
class Device:
    parts: list[Part]
    size_mm: tuple[float, float, float]
    name: str = ""

    @classmethod
    def from_manifest(cls, path: str | Path) -> "Device":
        doc = json.loads(Path(path).read_text())
        raw = [p for p in doc.get("parts", []) if p.get("bbox_mm")]
        if not raw:
            raise ValueError(f"{path}: no parts with bbox_mm")
        allc = [c for p in raw for c in p["bbox_mm"]]
        ox = min(c[0] for c in allc)
        oy = min(c[1] for c in allc)
        oz = min(c[2] for c in allc)
        parts = []
        for p in raw:
            (x0, y0, z0), (x1, y1, z1) = p["bbox_mm"]
            parts.append(Part(
                name=p.get("node_path") or p.get("blender_object") or "?",
                material_key=p.get("material_key") or "",
                lo=(x0 - ox, y0 - oy, z0 - oz),
                hi=(x1 - ox, y1 - oy, z1 - oz),
                sigma=float(p.get("sigma_S_per_m") or 0.0),
                eps_r=float(p.get("eps_r") or 1.0),
            ))
        hi = (max(p.hi[0] for p in parts),
              max(p.hi[1] for p in parts),
              max(p.hi[2] for p in parts))
        # Enclosure layers (back glass, display stack, chassis rails, their
        # adhesives) span the whole footprint. An embedded antenna lives
        # *inside* that envelope by definition, so intersecting them is not
        # a collision — only discrete components are. They still count for
        # clearance and for blocking escape, which is where they matter.
        foot = hi[0] * hi[1]
        for p in parts:
            area = (p.hi[0] - p.lo[0]) * (p.hi[1] - p.lo[1])
            p.is_shell = foot > 0 and area >= SHELL_FOOTPRINT_FRAC * foot
        return cls(parts=parts, size_mm=hi, name=doc.get("name", ""))


# ------------------------------------------------------------------ geometry

Box = tuple[tuple[float, float, float], tuple[float, float, float]]


def antenna_box(candidate: dict, device: Device, *,
                arm_w: float = ARM_W_MM, arm_h: float = ARM_H_MM) -> Box:
    """The candidate's printed strip as a box, in the corner frame.

    Mirrors the arm-direction convention the Blender renderer and
    geometry.py use: run along whichever in-plane axis has the longer free
    run from the feed, clamped to it.
    """
    W, L, T = device.size_mm
    px, py, pz = (float(v) for v in candidate["position_mm"])
    length = float(candidate["length_mm"])
    k0, k1 = candidate.get("keepout_mm") or ([0, 0, 0], [W, L, T])
    b0 = [max(k0[i], WALL_INSET_XYZ[i]) for i in range(3)]
    b1 = [min(k1[i], device.size_mm[i] - WALL_INSET_XYZ[i]) for i in range(3)]

    runs = [(b1[1] - py, "y", 1.0), (py - b0[1], "y", -1.0),
            (b1[0] - px, "x", 1.0), (px - b0[0], "x", -1.0)]
    run, axis, sgn = max(runs)
    la = max(4.0, min(length, run))
    if axis == "y":
        lo = (px - arm_w / 2, min(py, py + sgn * la), pz)
        hi = (px + arm_w / 2, max(py, py + sgn * la), pz + arm_h)
    else:
        lo = (min(px, px + sgn * la), py - arm_w / 2, pz)
        hi = (max(px, px + sgn * la), py + arm_w / 2, pz + arm_h)
    return lo, hi


def _overlap_volume(a: Box, b: Box) -> float:
    d = [max(0.0, min(a[1][i], b[1][i]) - max(a[0][i], b[0][i])) for i in range(3)]
    return d[0] * d[1] * d[2]


def _gap(a: Box, b: Box) -> float:
    """Shortest distance between two axis-aligned boxes (0 if they touch)."""
    d = [max(a[0][i] - b[1][i], b[0][i] - a[1][i], 0.0) for i in range(3)]
    return math.sqrt(sum(v * v for v in d))


def _ray_hits(origin, direction, box: Box) -> float | None:
    """Slab method. Returns entry distance along `direction`, or None."""
    t0, t1 = 0.0, float("inf")
    for i in range(3):
        d = direction[i]
        if abs(d) < 1e-12:
            if origin[i] < box[0][i] or origin[i] > box[1][i]:
                return None
            continue
        lo = (box[0][i] - origin[i]) / d
        hi = (box[1][i] - origin[i]) / d
        if lo > hi:
            lo, hi = hi, lo
        t0, t1 = max(t0, lo), min(t1, hi)
        if t0 > t1:
            return None
    return t0


# ------------------------------------------------------------------ analyses

def legality(candidate: dict, device: Device) -> dict:
    """Is this candidate physically buildable?

    Hard failures: any part of the strip outside the chassis, or intersecting
    a rigid part (battery, board, camera, frame). Soft failures: intersecting
    foam/adhesive/plastic, which a mechanical engineer can shave — reported
    separately so the agent can decide rather than being blocked.
    """
    box = antenna_box(candidate, device)
    W, L, T = device.size_mm
    out = []
    for i, axis in enumerate("xyz"):
        inset = WALL_INSET_XYZ[i]
        if box[0][i] < inset:
            out.append(f"{axis}-min {box[0][i]:.1f} mm < {inset} mm wall inset")
        limit = device.size_mm[i] - inset
        if box[1][i] > limit:
            out.append(f"{axis}-max {box[1][i]:.1f} mm > {limit:.1f} mm wall inset")

    hard, soft = [], []
    for p in device.parts:
        if p.is_shell:            # the envelope the antenna lives inside
            continue
        v = _overlap_volume(box, (p.lo, p.hi))
        if v <= 1e-6:
            continue
        rec = {"part": p.name, "material": p.material_key,
               "overlap_mm3": round(v, 3), "metal": p.is_metal}
        (soft if p.is_soft and not p.is_metal else hard).append(rec)

    hard.sort(key=lambda r: -r["overlap_mm3"])
    soft.sort(key=lambda r: -r["overlap_mm3"])
    return {
        "legal": not out and not hard,
        "outside_chassis": out,
        "collisions": hard[:6],
        "soft_collisions": soft[:6],
        "antenna_box_mm": [list(box[0]), list(box[1])],
    }


def clearance(candidate: dict, device: Device,
              radius_mm: float = NEARFIELD_MM) -> dict:
    """What sits in the antenna's near field, and is it a mirror or a radome?

    The single most predictive number for "this placement will not work" is
    the distance to the nearest conductor. `metal_fraction` adds how *much*
    metal is crowding the strip, and `dominant_dielectric` names what the
    field is actually launching through (glass, ABS, foam are fine; that is
    the difference between a plastic window and a titanium wall).
    """
    box = antenna_box(candidate, device)
    near_metal, near_diel = [], []
    for p in device.parts:
        g = _gap(box, (p.lo, p.hi))
        if g > radius_mm:
            continue
        rec = {"part": p.name, "material": p.material_key,
               "gap_mm": round(g, 2), "eps_r": p.eps_r}
        (near_metal if p.is_metal else near_diel).append(rec)
    near_metal.sort(key=lambda r: r["gap_mm"])
    near_diel.sort(key=lambda r: r["gap_mm"])

    nearest_metal = near_metal[0]["gap_mm"] if near_metal else float("inf")
    n_near = len(near_metal) + len(near_diel)
    return {
        "nearest_metal_mm": nearest_metal,
        "nearest_metal_part": near_metal[0]["part"] if near_metal else None,
        "metal_fraction": round(len(near_metal) / n_near, 3) if n_near else 0.0,
        "n_parts_in_nearfield": n_near,
        "nearest_metal_parts": near_metal[:5],
        "nearest_dielectric_parts": near_diel[:5],
    }


def _directions(n_theta: int = 12, n_phi: int = 24) -> list[tuple]:
    """Roughly uniform directions over the full sphere."""
    dirs = []
    for i in range(n_theta):
        theta = math.pi * (i + 0.5) / n_theta
        st, ct = math.sin(theta), math.cos(theta)
        for j in range(n_phi):
            phi = 2 * math.pi * j / n_phi
            dirs.append((st * math.cos(phi), st * math.sin(phi), ct))
    return dirs


def escape(candidate: dict, device: Device) -> dict:
    """Can the signal get out?

    Fires rays from the strip's centre in every direction and asks what each
    one meets on its way out of the chassis. A ray that only ever crosses
    dielectrics escapes (a plastic or glass window is a radome); a ray that
    hits a conductor is reflected back in. `escape_fraction` is the share of
    directions that make it — a cheap, physically-motivated proxy for total
    efficiency, and the number that separates "boxed in by the titanium
    frame" from "facing the plastic back".
    """
    box = antenna_box(candidate, device)
    centre = tuple((box[0][i] + box[1][i]) / 2 for i in range(3))
    metals = [(p, (p.lo, p.hi)) for p in device.parts if p.is_metal]

    free, blocked = 0, {}
    for d in _directions():
        hit = None
        for p, b in metals:
            t = _ray_hits(centre, d, b)
            if t is not None and t > 0.35:      # ignore the strip's own cell
                if hit is None or t < hit[0]:
                    hit = (t, p.name)
        if hit is None:
            free += 1
        else:
            blocked[hit[1]] = blocked.get(hit[1], 0) + 1

    total = len(_directions())
    top = sorted(blocked.items(), key=lambda kv: -kv[1])[:5]
    return {
        "escape_fraction": round(free / total, 3),
        "n_directions": total,
        "top_blockers": [{"part": n, "directions_blocked": c,
                          "share": round(c / total, 3)} for n, c in top],
    }


# -------------------------------------------------------------------- verdict

def screen(candidate: dict, device: Device, *,
           nearfield_mm: float = NEARFIELD_MM) -> dict:
    """All three analyses plus one ranking score. Cost: ~1 ms.

    `score` is deliberately simple and monotone so it is defensible in a
    pitch: illegal placements score 0; otherwise it rewards escape fraction
    and punishes metal in the near field, saturating at `nearfield_mm`
    (lambda/20 for the band in play — see nearfield_for).
    Use it to *order* candidates for the solver, never as a substitute for
    the solve.
    """
    leg = legality(candidate, device)
    clr = clearance(candidate, device, radius_mm=nearfield_mm)
    esc = escape(candidate, device)

    if not leg["legal"]:
        score = 0.0
    else:
        gap = min(clr["nearest_metal_mm"], nearfield_mm)
        score = round(esc["escape_fraction"] * (0.35 + 0.65 * gap / nearfield_mm), 4)

    reasons = []
    if leg["outside_chassis"]:
        reasons.append("antenna leaves the chassis: " + "; ".join(leg["outside_chassis"]))
    for c in leg["collisions"]:
        reasons.append(f"intersects {c['part']} ({c['material']}, "
                       f"{c['overlap_mm3']:.1f} mm3)")
    if clr["nearest_metal_mm"] < 2.0:
        reasons.append(f"metal {clr['nearest_metal_mm']:.1f} mm away "
                       f"({clr['nearest_metal_part']}) — expect heavy detuning")
    if esc["escape_fraction"] < 0.25 and esc["top_blockers"]:
        b = esc["top_blockers"][0]
        reasons.append(f"only {esc['escape_fraction']:.0%} of directions escape; "
                       f"{b['part']} blocks {b['share']:.0%}")

    return {
        "candidate_id": candidate.get("candidate_id"),
        "score": score,
        "legal": leg["legal"],
        "escape_fraction": esc["escape_fraction"],
        "nearest_metal_mm": clr["nearest_metal_mm"],
        "metal_fraction": clr["metal_fraction"],
        "reasons": reasons,
        "legality": leg,
        "clearance": clr,
        "escape": esc,
    }


def scan(device: Device, *, band_length_mm: float = 27.5, z_mm: float | None = None,
         step_mm: float = 4.0, keepout: list | None = None,
         nearfield_mm: float = NEARFIELD_MM) -> list[dict]:
    """Sweep a grid of feed positions over the device — the agent's map.

    Returns one screen() summary per grid point (without the verbose
    sub-dicts), ordered best-first. This is what turns "try somewhere else"
    into "try here next".
    """
    W, L, T = device.size_mm
    z = T * 0.55 if z_mm is None else z_mm
    out = []
    x = WALL_INSET_MM + 2.0
    while x < W - WALL_INSET_MM - 2.0:
        y = WALL_INSET_MM + 2.0
        while y < L - WALL_INSET_MM - 2.0:
            cand = {"candidate_id": f"scan_{x:.0f}_{y:.0f}", "antenna_type": "IFA",
                    "position_mm": [x, y, z], "feed_point_mm": [x, y, z],
                    "length_mm": band_length_mm, "orientation": "edge"}
            if keepout:
                cand["keepout_mm"] = keepout
            v = screen(cand, device, nearfield_mm=nearfield_mm)
            out.append({k: v[k] for k in
                        ("candidate_id", "score", "legal", "escape_fraction",
                         "nearest_metal_mm", "metal_fraction", "reasons")}
                       | {"position_mm": [x, y, z]})
            y += step_mm
        x += step_mm
    out.sort(key=lambda r: -r["score"])
    return out


if __name__ == "__main__":
    import sys
    manifest = sys.argv[1] if len(sys.argv) > 1 else "rf/blend_loader/out/device.json"
    dev = Device.from_manifest(manifest)
    print(f"{dev.name or manifest}: {len(dev.parts)} parts, "
          f"{dev.size_mm[0]:.1f} x {dev.size_mm[1]:.1f} x {dev.size_mm[2]:.1f} mm")
    metal = sum(1 for p in dev.parts if p.is_metal)
    print(f"  {metal} conductive parts, {len(dev.parts) - metal} dielectric\n")

    cfg_path = Path("runs/demo/config.json")
    if cfg_path.exists():
        cand = json.loads(cfg_path.read_text())["candidate"]
        v = screen(cand, dev)
        print(f"candidate {v['candidate_id']}: score {v['score']}  "
              f"legal={v['legal']}  escape={v['escape_fraction']:.0%}  "
              f"nearest metal {v['nearest_metal_mm']:.1f} mm")
        for r in v["reasons"]:
            print(f"    ! {r}")

    print("\ngrid scan (best 8 of the device):")
    rows = scan(dev, step_mm=6.0)
    legal = [r for r in rows if r["legal"]]
    print(f"  {len(legal)}/{len(rows)} grid positions legal")
    for r in rows[:8]:
        print(f"  {r['position_mm'][0]:5.1f},{r['position_mm'][1]:6.1f}  "
              f"score {r['score']:.3f}  escape {r['escape_fraction']:.0%}  "
              f"metal {r['nearest_metal_mm']:5.1f} mm")
