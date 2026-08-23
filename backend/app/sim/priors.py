"""Physics screening of anchors — the loop's cheap filter, before any solve.

`geometry/spec.py:make_anchors()` lays candidate positions around the device
perimeter on a fixed 18 mm pitch. That is pure geometry: it does not know that
one of those anchors is buried in the taptic engine, that another is 0.4 mm
from the titanium rail, or that a third faces nothing but battery. Handing all
twenty to the agent means it spends solves — and Devin turns — discovering by
simulation what a bounding-box test answers in a millisecond.

This module bridges the backend's `DeviceSpec` to `rf/placement.py` and turns
the anchor list into a *screened, ranked, explained* one:

    screen_anchors(spec, band) -> list[AnchorPrior]   # best first, illegal last

Each prior carries the three numbers the agent should reason with, and the
sentence that says why:

    legal            does the antenna volume fit without hitting a component
    escape_fraction  share of directions the signal leaves without meeting metal
    nearest_metal_mm distance to the closest conductor (a mirror, not a radome)

Two rules make this worth having, and both come from the physics:

- **Metal near a radiator dominates its impedance.** Anything inside roughly
  lambda/20 detunes it; at 2.4 GHz that is ~6 mm. So we push the emitter away
  from conductors.
- **A dielectric neighbour is a radome, not a wall.** Glass, ABS and foam let
  the field through; that is the difference between an antenna facing the
  plastic back and one facing the titanium frame. So we pull the emitter
  towards dielectrics — which is exactly what escape_fraction measures.

Falls back gracefully: if the device has no real manifest (no `geometry_path`,
or `rf.placement` unavailable), every anchor comes back `legal=True` with
`screened=False`, and the caller behaves exactly as it did before.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.models import Anchor, BandRequirement, DeviceSpec

# rf/ lives at the repo root, one level above backend/
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Metal this close to the radiator dominates its impedance. lambda/20 is the
# usual rule of thumb; computed per band rather than hardcoded.
_NEARFIELD_FRAC = 1.0 / 20.0
_C = 299_792_458.0


@dataclass
class AnchorPrior:
    """One anchor, screened. `score` orders them; `why` explains the order."""
    anchor_id: str
    label: str
    region: str
    pos_mm: tuple
    legal: bool = True
    escape_fraction: float = 0.0
    nearest_metal_mm: float = float("inf")
    metal_fraction: float = 0.0
    score: float = 0.0
    why: str = ""
    blockers: list = field(default_factory=list)
    screened: bool = True

    def to_dict(self) -> dict:
        d = {
            "anchor_id": self.anchor_id, "label": self.label, "region": self.region,
            "pos_mm": list(self.pos_mm), "legal": self.legal,
            "score": round(self.score, 4), "why": self.why, "screened": self.screened,
        }
        if self.screened:
            d |= {
                "escape_fraction": self.escape_fraction,
                "nearest_metal_mm": (None if self.nearest_metal_mm == float("inf")
                                     else round(self.nearest_metal_mm, 2)),
                "metal_fraction": self.metal_fraction,
                "blockers": self.blockers[:3],
            }
        return d


def _manifest_for(spec: DeviceSpec) -> Path | None:
    """The blend_loader manifest behind this spec, if there is one."""
    for cand in (getattr(spec, "geometry_path", None),
                 _REPO / "rf" / "blend_loader" / "out" / "device.json"):
        if not cand:
            continue
        p = Path(cand)
        if not p.is_absolute():
            p = _REPO / p
        if p.exists() and p.suffix == ".json":
            return p
    return None


def _quarter_wave_mm(band: BandRequirement) -> float:
    """A sane default arm length for screening: quarter wave at band centre."""
    f_mid = (band.f_low_ghz + band.f_high_ghz) / 2.0
    return _C / (f_mid * 1e9) / 4.0 * 1000.0


def screen_anchors(spec: DeviceSpec, band: BandRequirement,
                   anchors: list[Anchor] | None = None) -> list[AnchorPrior]:
    """Screen every anchor against the real device geometry. Best first.

    Illegal anchors are kept (sorted last) rather than dropped: the agent
    should be able to see that a position was considered and *why* it was
    ruled out — that is the difference between a filter and an explanation.
    """
    from app.geometry.spec import make_anchors

    anchors = anchors if anchors is not None else make_anchors(spec)
    manifest = _manifest_for(spec)

    if manifest is None:
        return _unscreened(anchors, "no device manifest; geometry screening skipped")
    try:
        from rf.placement import Device, screen
    except Exception as exc:                              # rf/ not importable
        return _unscreened(anchors, f"rf.placement unavailable ({exc})")
    try:
        device = Device.from_manifest(manifest)
    except Exception as exc:
        return _unscreened(anchors, f"manifest unreadable ({exc})")

    lam_mm = _C / (((band.f_low_ghz + band.f_high_ghz) / 2.0) * 1e9) * 1000.0
    nearfield_mm = lam_mm * _NEARFIELD_FRAC
    arm_mm = _quarter_wave_mm(band)

    out: list[AnchorPrior] = []
    for a in anchors:
        cand = {
            "candidate_id": a.id, "antenna_type": "monopole",
            "position_mm": list(a.pos_mm), "feed_point_mm": list(a.pos_mm),
            "length_mm": arm_mm, "orientation": "edge",
        }
        try:
            v = screen(cand, device)
        except Exception as exc:
            out.append(AnchorPrior(anchor_id=a.id, label=a.label, region=a.region,
                                   pos_mm=a.pos_mm, why=f"screen failed: {exc}",
                                   screened=False, score=0.0))
            continue

        gap = v["nearest_metal_mm"]
        esc = v["escape_fraction"]
        # Reward escape, reward metal clearance, saturating at lambda/20 (past
        # that the conductor stops mattering). Illegal anchors score 0 so they
        # sort last without being hidden.
        clear_term = min(gap, nearfield_mm) / nearfield_mm if nearfield_mm else 1.0
        score = 0.0 if not v["legal"] else esc * (0.4 + 0.6 * clear_term)

        out.append(AnchorPrior(
            anchor_id=a.id, label=a.label, region=a.region, pos_mm=a.pos_mm,
            legal=v["legal"], escape_fraction=esc,
            nearest_metal_mm=gap, metal_fraction=v["metal_fraction"],
            score=score, why=_explain(v, nearfield_mm),
            blockers=[b["part"] for b in v["escape"].get("top_blockers", [])],
        ))

    out.sort(key=lambda p: (-p.score, p.anchor_id))
    return out


def _explain(v: dict, nearfield_mm: float) -> str:
    """One sentence the agent can act on, not a metric dump."""
    if not v["legal"]:
        reasons = v.get("reasons") or []
        return reasons[0] if reasons else "illegal placement"
    bits = [f"{v['escape_fraction']:.0%} of directions radiate out"]
    gap = v["nearest_metal_mm"]
    if gap < nearfield_mm:
        who = v["clearance"].get("nearest_metal_part") or "a conductor"
        bits.append(f"but {who} sits {gap:.1f} mm away "
                    f"(inside the {nearfield_mm:.0f} mm near field)")
    else:
        bits.append(f"nearest conductor {gap:.1f} mm away, clear of the near field")
    top = (v["escape"].get("top_blockers") or [None])[0]
    if top and top["share"] > 0.2:
        bits.append(f"{top['part']} blocks {top['share']:.0%}")
    return "; ".join(bits)


def _unscreened(anchors: list[Anchor], why: str) -> list[AnchorPrior]:
    return [AnchorPrior(anchor_id=a.id, label=a.label, region=a.region,
                        pos_mm=a.pos_mm, legal=True, score=0.0, why=why,
                        screened=False)
            for a in anchors]


_SCAN_CACHE: dict[tuple, list] = {}


def anchors_from_scan(spec: DeviceSpec, band: BandRequirement, *,
                      n: int = 14, step_mm: float = 4.0,
                      min_separation_mm: float = 12.0) -> list[Anchor] | None:
    """Derive anchors FROM the physics instead of filtering a fixed list.

    `make_anchors()` walks the perimeter on an 18 mm pitch at a 6 mm margin —
    which, on this device, plants most of them inside the titanium frame band.
    Screening then rejects them and the agent is left with a handful of
    near-identical positions on one edge.

    Sweeping `rf.placement.scan()` over the whole device instead asks the
    geometry where an antenna *can* go, keeps the best-scoring legal points,
    and spreads them out (`min_separation_mm`) so the agent gets genuinely
    different options rather than fourteen samples of one hotspot. This is the
    same field `rf/viz/heatmap.py` renders as placement_map.png.

    Returns None when the manifest or rf.placement is unavailable, so callers
    can fall back to make_anchors().
    """
    manifest = _manifest_for(spec)
    if manifest is None:
        return None
    try:
        from rf.placement import Device, scan
        device = Device.from_manifest(manifest)
    except Exception:
        return None

    # The grid sweep costs seconds (1000+ screens); the agent loop runs many
    # times against the same device+band. Cache on what actually changes it.
    # Sweep at the height the solver will actually build at. scan() defaults to
    # 0.55 T — mid-stack, which in this phone is 6.0 mm, BELOW the ground plane
    # at 8.6 mm. Anchors from there sit in the shadow of their own counterpoise
    # and solved at 24% efficiency where the surface plane gives 96%. The rest
    # of the system already agrees on antenna_z(); the scan has to as well, or
    # the map and the candidates describe different antennas.
    from app.geometry.spec import antenna_z
    # antenna_z is where the radiator's OUTER face belongs — just inside the
    # back cover. scan() takes the feed plane and builds the 0.9 mm strip
    # upward from it, so drop by that thickness or the strip pokes through the
    # cover and every point screens as illegal.
    from rf.placement import ARM_H_MM
    z = round(max(0.5, antenna_z(spec) - ARM_H_MM), 2)
    # Judge metal against this band's own near field (lambda/20), not a fixed
    # 12 mm — otherwise the anchors, like the map, come out the same for every
    # frequency in the same phone.
    from rf.placement import nearfield_for
    near = round(nearfield_for((band.f_low_ghz + band.f_high_ghz) / 2), 2)
    key = (str(manifest), manifest.stat().st_mtime_ns, band.id, step_mm, z, near,
           round(_quarter_wave_mm(band), 2))
    rows = _SCAN_CACHE.get(key)
    if rows is None:
        rows = scan(device, band_length_mm=_quarter_wave_mm(band), step_mm=step_mm,
                    z_mm=z, nearfield_mm=near)
        _SCAN_CACHE[key] = rows
    legal = [r for r in rows if r["legal"]]
    if not legal:
        return None

    picked: list[dict] = []
    for r in legal:                       # already sorted best-first by scan()
        x, y, _z = r["position_mm"]
        if all((x - px) ** 2 + (y - py) ** 2 >= min_separation_mm ** 2
               for px, py, _ in (p["position_mm"] for p in picked)):
            picked.append(r)
        if len(picked) >= n:
            break

    w, h, _t = _device_size(spec)
    out: list[Anchor] = []
    for i, r in enumerate(picked):
        x, y, z = r["position_mm"]
        # outward normal = towards the nearest edge; region names match the
        # backend's RegionId vocabulary so downstream prompts keep working.
        d = {"left": x, "right": w - x, "bottom": y, "top": h - y}
        region = min(d, key=d.get)
        outward = {"left": (-1.0, 0.0, 0.0), "right": (1.0, 0.0, 0.0),
                   "bottom": (0.0, -1.0, 0.0), "top": (0.0, 1.0, 0.0)}[region]
        out.append(Anchor(
            id=f"p{i + 1}", region=region, corner=False,
            label=f"{region} {x:.0f},{y:.0f} mm (escape {r['escape_fraction']:.0%})",
            pos_mm=(round(x, 2), round(y, 2), round(z, 2)), outward=outward,
        ))
    return out


def _device_size(spec: DeviceSpec) -> tuple[float, float, float]:
    from app.geometry.spec import device_size
    return device_size(spec)


def brief_for_agent(priors: list[AnchorPrior], max_rows: int = 12) -> str:
    """Render the screening as the block that goes into the agent's prompt.

    Deliberately a table and not JSON: this is read by a model that has to
    choose, and the `why` column is what makes the choice reasoned rather
    than a lookup of the top score.
    """
    if not priors:
        return "No anchors available."
    if not priors[0].screened:
        return (f"Anchor screening unavailable ({priors[0].why}). "
                f"All {len(priors)} anchors are candidates.")

    legal = [p for p in priors if p.legal]
    illegal = [p for p in priors if not p.legal]
    lines = [
        f"Geometry screening of {len(priors)} anchors against the real device "
        f"({len(legal)} legal, {len(illegal)} ruled out). Ranked best first — "
        f"higher escape fraction and more metal clearance is better.",
        "",
        f"{'anchor':7} {'position mm':>14} {'region':8} {'escape':>7} {'metal':>8}  why",
    ]
    for p in legal[:max_rows]:
        gap = "-" if p.nearest_metal_mm == float("inf") else f"{p.nearest_metal_mm:.1f}mm"
        pos = f"({p.pos_mm[0]:.0f},{p.pos_mm[1]:.0f},{p.pos_mm[2]:.0f})"
        lines.append(f"{p.anchor_id:7} {pos:>14} {p.region:8} "
                     f"{p.escape_fraction:>6.0%} {gap:>8}  {p.why}")
    if illegal:
        lines += ["", "Ruled out (do not propose these):"]
        for p in illegal[:6]:
            lines.append(f"  {p.anchor_id:10} {p.why}")
    return "\n".join(lines)


if __name__ == "__main__":
    from app.geometry.bands import CATALOG
    from app.geometry.spec import phone_v1

    import time
    spec = phone_v1()
    band = CATALOG["wifi24"]

    print("=" * 72)
    print("A) screening the fixed perimeter anchors")
    print("=" * 72)
    t0 = time.perf_counter()
    priors = screen_anchors(spec, band)
    print(brief_for_agent(priors))
    print(f"\n{len(priors)} anchors screened in {(time.perf_counter()-t0)*1000:.0f} ms")

    print("\n" + "=" * 72)
    print("B) anchors derived FROM the geometry (what the agent should get)")
    print("=" * 72)
    t0 = time.perf_counter()
    derived = anchors_from_scan(spec, band)
    dt = time.perf_counter() - t0
    if derived is None:
        print("unavailable (no manifest)")
    else:
        p2 = screen_anchors(spec, band, anchors=derived)
        print(brief_for_agent(p2))
        print(f"\n{len(derived)} anchors derived in {dt:.1f} s")


def anchors_for(spec: DeviceSpec, band_ids: list[str]) -> tuple[list[Anchor], str]:
    """The positions the agent is allowed to choose from, and where they came from.

    This is the product thesis in one function. `make_anchors()` answers "where
    could an antenna go on a box this size" — a perimeter lattice that would be
    the same for any phone with these outside dimensions, which is why the
    placements it yields look generic: they are. The scan answers "where can an
    antenna go in THIS phone", by sweeping the real internals, rejecting every
    point that collides or sits too close to metal, and ranking what survives by
    how much of the field escapes the chassis. It is the same field the
    placement map draws, so the spots on screen and the spots the agent may pick
    are one set of numbers.

    The lowest band picks the anchors when several are studied: it needs the
    longest radiator and the most clearance, so its legal set is the strictest.

    Falls back to the lattice — and says so — when there is no manifest to scan.
    """
    from app.geometry.bands import CATALOG
    from app.geometry.spec import make_anchors

    bands = [CATALOG[b] for b in band_ids if b in CATALOG]
    if bands:
        lowest = min(bands, key=lambda b: b.f_low_ghz)
        scanned = anchors_from_scan(spec, lowest)
        if scanned:
            return scanned, f"scan:{lowest.id}"
    return make_anchors(spec), "lattice"
