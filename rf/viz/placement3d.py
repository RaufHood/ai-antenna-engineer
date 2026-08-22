"""Wireframe x-ray of the antenna candidate inside the real device.

    from rf.viz.placement3d import render_placement
    render_placement(load_run("runs/demo"), "runs/demo/media/placement.png")

`build_scene(ax, run)` is the reusable core: it draws onto a provided 3D
axes and returns bounds + animatable artists, so the orbit animation can
import it and only spin the camera.

Coordinate convention (mirrors rf.geometry._add_device_materials): device
part bboxes are Blender-centred; candidate coordinates are corner-anchored
[0..W] x [0..L]. All parts are shifted by -min(bbox over usable parts) so
both frames share the origin.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..models import IFA_ARM_WIDTH_MM, IFA_HEIGHT_MM
from .theme import FG, GRID, PALETTE, apply_theme, part_color

_ARM_THICK_MM = 0.9          # visual slab thickness of the radiating arm
_BATTERY_KEYS = ("battery", "lithium", "lipo")
# Conductivity above which a part is visually a conductor even when its
# material_key is outside part_color()'s name list (e.g. "stainless").
_METAL_SIGMA = 1.0e4


# ------------------------------------------------------------------ box math

def _corners(lo, hi) -> np.ndarray:
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    return np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ])


_EDGE_IDX = [(0, 1), (1, 2), (2, 3), (3, 0),
             (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
_FACE_IDX = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]


def _edges(lo, hi) -> list:
    c = _corners(lo, hi)
    return [(c[i], c[j]) for i, j in _EDGE_IDX]


def _faces(lo, hi) -> list:
    c = _corners(lo, hi)
    return [[c[i] for i in quad] for quad in _FACE_IDX]


def _is_battery(part: dict) -> bool:
    tag = " ".join(str(part.get(k) or "") for k in
                   ("material_key", "node_path", "name")).lower()
    return any(k in tag for k in _BATTERY_KEYS)


def _edge_color(part: dict) -> str:
    """theme.part_color, with a conductivity fallback: highly conductive
    parts whose material_key isn't in its name list (e.g. 'stainless')
    still read as metal in the x-ray."""
    color = part_color(part.get("material_key") or "")
    if color == PALETTE["dielectric"]:
        sigma = part.get("sigma_S_per_m") or 0.0
        if sigma >= _METAL_SIGMA:
            return PALETTE["metal"]
    return color


# ---------------------------------------------------------------- the scene

def build_scene(ax, run: dict, *, elev: float = 22, azim: float = -58) -> dict:
    """Draw the placement x-ray onto 3D axes `ax`. Pure: no figure/file IO.

    Returns {'bounds': (lo, hi), 'antenna_artists': [...],
             'feed_artist': ..., 'n_parts': int}.
    """
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

    device = run.get("device")
    candidate = run.get("candidate") or {}
    parts = (device or {}).get("parts") or []

    # ---- device parts, shifted to corner-anchored frame ---------------------
    usable = [p for p in parts if p.get("bbox_mm") and p.get("eps_r") is not None]
    drawable = [p for p in parts if p.get("bbox_mm")]
    if usable:
        allc = np.array([c for p in usable for c in p["bbox_mm"]], dtype=float)
        shift = -allc.min(axis=0)
        dev_hi = allc.max(axis=0) + shift
    elif drawable:
        allc = np.array([c for p in drawable for c in p["bbox_mm"]], dtype=float)
        shift = -allc.min(axis=0)
        dev_hi = allc.max(axis=0) + shift
    else:
        shift = np.zeros(3)
        dev_hi = None

    seg_by_color: dict[str, list] = {}
    battery_boxes: list[tuple[np.ndarray, np.ndarray]] = []
    for p in drawable:
        lo = np.asarray(p["bbox_mm"][0], dtype=float) + shift
        hi = np.asarray(p["bbox_mm"][1], dtype=float) + shift
        if _is_battery(p):
            battery_boxes.append((lo, hi))
            continue
        seg_by_color.setdefault(_edge_color(p), []).extend(_edges(lo, hi))

    for color, segs in seg_by_color.items():
        ax.add_collection3d(Line3DCollection(
            segs, colors=color, linewidths=0.7, alpha=0.55))

    # Battery: faint solid + heavier edges — the classic antenna killer.
    for lo, hi in battery_boxes:
        ax.add_collection3d(Poly3DCollection(
            _faces(lo, hi), facecolors=PALETTE["battery"], alpha=0.10,
            edgecolors="none"))
        ax.add_collection3d(Line3DCollection(
            _edges(lo, hi), colors=PALETTE["battery"],
            linewidths=1.4, alpha=0.85))

    # Enclosure outline (overall device bbox).
    if dev_hi is not None:
        ax.add_collection3d(Line3DCollection(
            _edges((0.0, 0.0, 0.0), dev_hi), colors=PALETTE["outline"],
            linewidths=1.6, alpha=0.9))

    # ---- the antenna (already corner-anchored) --------------------------------
    antenna_artists = []
    pos = np.asarray(candidate.get("position_mm") or (0, 0, IFA_HEIGHT_MM),
                     dtype=float)
    feed = np.asarray(candidate.get("feed_point_mm") or pos, dtype=float)
    arm_len = float(candidate.get("length_mm") or 0.0)
    w = IFA_ARM_WIDTH_MM

    def _amber_box(lo, hi, alpha=0.95):
        poly = Poly3DCollection(_faces(lo, hi), facecolors=PALETTE["antenna"],
                                edgecolors=PALETTE["antenna"],
                                linewidths=0.4, alpha=alpha)
        ax.add_collection3d(poly)
        antenna_artists.append(poly)
        return poly

    arm_lo = arm_hi = None
    if arm_len > 0:
        # Arm runs from the short pin (position), away from the feed
        # (rf.geometry convention), snapped to the dominant axis.
        d = pos[:2] - feed[:2]
        axis = int(np.argmax(np.abs(d))) if np.any(d) else 1
        sign = float(np.sign(d[axis])) if d[axis] else 1.0
        z_top = pos[2] if pos[2] > 0 else IFA_HEIGHT_MM
        lo = np.array([pos[0] - w / 2, pos[1] - w / 2, z_top - _ARM_THICK_MM])
        hi = np.array([pos[0] + w / 2, pos[1] + w / 2, z_top])
        if sign > 0:
            hi[axis] = pos[axis] + arm_len
        else:
            lo[axis] = pos[axis] - arm_len
        arm_lo, arm_hi = lo, hi
        _amber_box(lo, hi)
        # Short + feed pins down to the ground plane.
        for base in (pos, feed):
            zt = base[2] if base[2] > 0 else IFA_HEIGHT_MM
            _amber_box((base[0] - w / 2, base[1] - w / 2, 0.0),
                       (base[0] + w / 2, base[1] + w / 2, zt))

    feed_artist = ax.scatter(
        [feed[0]], [feed[1]], [feed[2] if feed[2] > 0 else IFA_HEIGHT_MM],
        s=55, c=PALETTE["antenna"], edgecolors=FG, linewidths=0.9,
        depthshade=False, zorder=10)

    # Keep-out volume: dotted amber edges.
    keepout = candidate.get("keepout_mm")
    if keepout:
        ax.add_collection3d(Line3DCollection(
            _edges(keepout[0], keepout[1]), colors=PALETTE["antenna"],
            linewidths=1.0, linestyles=":", alpha=0.5))

    # ---- bounds + aspect --------------------------------------------------------
    pts = [np.zeros(3)]
    if dev_hi is not None:
        pts.append(np.asarray(dev_hi))
    if keepout:
        pts += [np.asarray(keepout[0], float), np.asarray(keepout[1], float)]
    if arm_lo is not None:
        pts += [arm_lo, arm_hi]
    pts += [pos, feed]
    lo_b = np.min(pts, axis=0)
    hi_b = np.max(pts, axis=0)
    span = np.maximum(hi_b - lo_b, 1.0)

    pad = 0.04 * float(max(span[:2]))
    ax.set_xlim(lo_b[0] - pad, hi_b[0] + pad)
    ax.set_ylim(lo_b[1] - pad, hi_b[1] + pad)
    ax.set_zlim(lo_b[2] - pad / 2, hi_b[2] + pad / 2)
    ax.set_box_aspect(tuple(span + 2 * pad), zoom=1.12)

    # ---- coordinate origin + axis triad -------------------------------------
    # The working frame is corner-anchored: (0,0,0) is the device's minimum
    # corner (same convention geometry._add_device_materials shifts to, and
    # the frame all candidate position_mm/feed_point_mm values live in).
    # Making the origin explicit on the plot kills the recurring confusion
    # with the Blender-centred coordinates the raw manifest uses.
    tri = 0.16 * float(max(span[:2]))          # triad arm length, scene-scaled
    triad = [((tri, 0, 0), "$x$"), ((0, tri, 0), "$y$")]
    if abs(elev) < 60:                         # z arm is edge-on from the top
        triad.append(((0, 0, 0.9 * tri), "$z$"))
    for (dx, dy, dz), lab in triad:
        ax.quiver(0, 0, 0, dx, dy, dz, color=FG, alpha=0.9,
                  linewidth=1.6, arrow_length_ratio=0.14)
        ax.text(dx * 1.22, dy * 1.22, dz * 1.18, lab, color=FG,
                fontsize=11, ha="center", va="center")
    ax.scatter([0], [0], [0], color=FG, s=26, depthshade=False, zorder=6)
    # Screen-space caption: immune to 3D projection collisions/cropping.
    ax.text2D(0.985, 0.01, "origin (0, 0, 0) = device min corner",
              transform=ax.figure.transFigure, color=FG, alpha=0.55,
              fontsize=8.5, ha="right", va="bottom")


    # ---- dimension annotations ----------------------------------------------
    # W below the front edge, L along the -x side (the +x side belongs to the
    # y axis ticks), T beside the origin corner -- and only in oblique views,
    # where the z direction is not edge-on.
    dim_kw = dict(color=FG, alpha=0.75, fontsize=8.5)
    line_kw = dict(color=FG, alpha=0.3, linewidth=0.8)
    top_down = abs(elev) >= 60
    if dev_hi is not None:
        W, L, T = float(dev_hi[0]), float(dev_hi[1]), float(dev_hi[2])
        off = 0.09 * max(W, 1.0)
        if top_down:
            # Front edge: the back edge would project above the axes here.
            ax.plot([0, W], [-off, -off], [0, 0], **line_kw)
            ax.text(W / 2, -2.6 * off, 0, f"W = {W:.1f} mm",
                    ha="center", va="top", **dim_kw)
        else:
            # Back-top edge: empty sky in the oblique view, far from the
            # x tick row that lives along the front edge.
            ax.plot([0, W], [L + off, L + off], [T, T], **line_kw)
            ax.text(W / 2, L + 2.4 * off, T + 1.5, f"W = {W:.1f} mm",
                    ha="center", va="bottom", **dim_kw)
        ax.plot([-off, -off], [0, L], [0, 0], **line_kw)
        ax.text(-3.1 * off, L / 2, 0, f"L = {L:.1f} mm", zdir="y",
                ha="center", va="top", **dim_kw)
        if not top_down:
            # T beside the front-right vertical edge (only meaningful when
            # the view is oblique; edge-on from the top).
            ax.plot([W + off, W + off], [0, 0], [0, T], **line_kw)
            ax.text(W + 2.3 * off, 0, 0.45 * T, f"T = {T:.1f} mm",
                    ha="left", va="center", **dim_kw)
    else:
        ax.text2D(0.03, 0.06, "device manifest unavailable - antenna only",
                  transform=ax.transAxes, color=FG, alpha=0.6, fontsize=9.5)

    if arm_lo is not None:
        mid = (arm_lo + arm_hi) / 2
        px, py, pz = (float(v) for v in pos)
        # Anchor above the enclosure top: keeps the label in front of every
        # depth-sorted wireframe (explicit zorder is ignored in 3D axes).
        top_z = (float(dev_hi[2]) if dev_hi is not None else float(arm_hi[2])) + 7.0
        ax.text(mid[0] + 2.5 * w, mid[1], top_z,
                f"IFA arm {arm_len:g} mm\npos ({px:.0f}, {py:.0f}, {pz:.0f}) mm",
                color=PALETTE["antenna"], fontsize=8.5, ha="left",
                va="bottom", zorder=30, linespacing=1.35)

    # ---- axes cosmetics: transparent panes, dim grid, mm ticks --------------
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_pane_color((0, 0, 0, 0))
        axis.line.set_color(GRID)
        try:
            axis._axinfo["grid"].update(color=GRID, linewidth=0.5)
        except Exception:
            pass
    ax.tick_params(labelsize=8, pad=-1)
    if dev_hi is not None:
        ax.set_xticks(np.arange(0, dev_hi[0] + 1, 20))
        ax.set_yticks(np.arange(0, dev_hi[1] + 1, 20))
        ax.set_zticks(np.arange(0, dev_hi[2] + 1, 5))
    ax.set_xlabel("x (mm)", fontsize=9, labelpad=8)
    ax.set_ylabel("y (mm)", fontsize=9, labelpad=4)
    if top_down:
        ax.set_zticks([])
        ax.set_zlabel("")
    else:
        ax.set_zlabel("z (mm)", fontsize=9, labelpad=-4)

    # ---- legend -----------------------------------------------------------------
    handles = [
        Line2D([0], [0], color=PALETTE["metal"], lw=1.6, label="Titanium / metal"),
        Line2D([0], [0], color=PALETTE["dielectric"], lw=1.6, label="Dielectric"),
        Patch(facecolor=PALETTE["battery"], edgecolor=PALETTE["battery"],
              alpha=0.45, label="Battery"),
        Patch(facecolor=PALETTE["antenna"], edgecolor=PALETTE["antenna"],
              alpha=0.95, label="Antenna"),
        Line2D([0], [0], color=PALETTE["antenna"], lw=1.2, linestyle=":",
               alpha=0.8, label="Keep-out"),
    ]
    if top_down:
        ax.legend(handles=handles, loc="upper left", fontsize=8.5,
                  borderpad=0.6, labelspacing=0.55, bbox_to_anchor=(1.0, 1.0))
    else:
        ax.legend(handles=handles, loc="upper right", fontsize=8.5,
                  borderpad=0.6, labelspacing=0.55, bbox_to_anchor=(1.02, 0.99))

    ax.view_init(elev=elev, azim=azim)
    return {
        "bounds": (lo_b, hi_b),
        "antenna_artists": antenna_artists,
        "feed_artist": feed_artist,
        "n_parts": len(drawable),
    }


def render_placement(run: dict, out_png: str,
                     views=(("iso", 22, -58), ("top", 88, -90))) -> list[str]:
    """Render the placement x-ray from each view; returns the written paths.

    View files derive from `out_png`: placement.png -> placement_iso.png, ...
    """
    apply_theme()
    import matplotlib.pyplot as plt

    candidate = run.get("candidate") or {}
    device = run.get("device")
    ant = candidate.get("antenna_type") or "Antenna"
    name = ((device or {}).get("name") or "unknown device").split(" (")[0]
    n_parts = len((device or {}).get("parts") or [])
    title = f"{ant} placement - {name}"

    base = Path(out_png)
    base.parent.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for tag, elev, azim in views:
        top_down = abs(elev) >= 60
        fig = plt.figure(figsize=(7.6, 10.4) if top_down else (10.2, 8.2))
        ax = fig.add_subplot(111, projection="3d")
        build_scene(ax, run, elev=elev, azim=azim)
        # Title block in the top-left corner (the legend owns the top-right).
        ax.text2D(0.01, 1.055, title, transform=ax.transAxes,
                  ha="left", va="top", fontsize=14.5)
        sub = f"{tag} view" if not n_parts else f"{n_parts} parts - {tag} view"
        ax.text2D(0.012, 1.018, sub, transform=ax.transAxes,
                  ha="left", va="top", fontsize=10, color=FG, alpha=0.6)
        path = base.with_name(f"{base.stem}_{tag}{base.suffix or '.png'}")
        fig.savefig(path)
        plt.close(fig)
        written.append(str(path))
    return written


if __name__ == "__main__":
    from .data import load_run

    run = load_run("runs/demo")
    for p in render_placement(run, "runs/demo/media/placement.png"):
        print(f"placement -> {Path(p).resolve()} ({Path(p).stat().st_size} bytes)")
