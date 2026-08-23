"""Transient |E|-field animation over the board plane, from an openEMS dump.

    from rf.viz.anim_field import render_field_animation
    render_field_animation(load_run("runs/demo"), "runs/demo/media/field.gif")

Reads run['field_h5'] (/FieldData/TD/<8-digit-step> field arrays plus
/Mesh/x|y|z in metres; the spatial axis order varies, so it is recovered by
matching axis lengths against the mesh rather than assumed) and renders |E| on the z-slice
as a GIF (plus an .mp4 next to it when ffmpeg is on PATH).

Two deliberate correctness choices over the old debug plot:
- pcolormesh on the TRUE (possibly non-uniform) FDTD mesh -- imshow assumed
  uniform spacing and distorted the geometry near graded-mesh regions.
- colour scale clipped at the 99th percentile across all frames, because the
  feed singularity otherwise owns the whole dynamic range.
"""
from __future__ import annotations

import shutil
import json
from pathlib import Path

import numpy as np

from ..models import IFA_ARM_WIDTH_MM
from .theme import FG, GRID, PALETTE, apply_theme, cm_text

# Layout constants (inches / figure fractions) -- geometry, not style.
_FIGSIZE = (6.6, 9.2)
_GIF_DPI = 100                     # 9.2 in * 100 dpi = 920 px tall (>= 640)
_VMAX_PCT = 99.0                   # near-field clip percentile
_BATTERY_MATERIALS = ("battery", "lithium", "lipo")
_BATTERY_TAGS = ("battery", "lithium", "lipo")


# ------------------------------------------------------------------ field IO

def _read_field_frames(h5_path, max_frames: int) -> dict | None:
    """Load the |E| z-slice for up to `max_frames` evenly-spaced time steps.

    -> {x_mm, y_mm, z_mm, steps, times_ns(|None), mags: [(ny, nx) float64]}
    or None when the dump holds no time steps.
    """
    import h5py

    with h5py.File(h5_path, "r") as h5:
        x_mm = np.asarray(h5["Mesh/x"], dtype=float) * 1e3
        y_mm = np.asarray(h5["Mesh/y"], dtype=float) * 1e3
        z_mm = np.asarray(h5["Mesh/z"], dtype=float) * 1e3
        td = h5["FieldData/TD"]
        keys = sorted(td.keys())           # zero-padded -> lexicographic == numeric
        if not keys:
            return None
        if len(keys) > max_frames:
            sel = np.unique(np.linspace(0, len(keys) - 1, max_frames)
                            .round().astype(int))
            keys = [keys[i] for i in sel]
        iz = int(np.argmin(np.abs(z_mm - np.median(z_mm))))   # central dump slice

        mags, steps, times_ns = [], [], []
        have_time = True
        for k in keys:
            ds = td[k]
            arr = np.asarray(ds)
            # openEMS does not guarantee the spatial axis order, and it is not
            # the one this reader used to assume: a phone-sized dump comes back
            # (3, nx, ny, nz), the reverse of the (3, nz, ny, nx) that a wide
            # flat demo board happened to look like. Guessing gave a (24, 1)
            # slab against a 17-point x axis and pcolormesh refused it.
            #
            # The dump writes its own sub-sampled mesh alongside the data, so
            # the axis lengths identify the axes outright. Match z first: the
            # dump is a plane, so its z axis is the degenerate one and unique.
            # x before y afterwards makes openEMS's own (x, y, z) order the
            # tie-break if a square dump ever makes the two ambiguous.
            used: set[int] = set()
            axis: dict[str, int] = {}
            for name, n in (("z", len(z_mm)), ("x", len(x_mm)), ("y", len(y_mm))):
                for i, d in enumerate(arr.shape[1:]):
                    if d == n and i not in used:
                        axis[name] = i
                        used.add(i)
                        break
            if len(axis) < 3:
                raise ValueError(
                    f"field dump {arr.shape[1:]} does not match its mesh "
                    f"(x={len(x_mm)}, y={len(y_mm)}, z={len(z_mm)})")
            comp = np.moveaxis(arr, [1 + axis["z"], 1 + axis["y"], 1 + axis["x"]],
                               [1, 2, 3]).astype(np.float64)   # (3, nz, ny, nx)
            mags.append(np.sqrt((comp[:, iz] ** 2).sum(axis=0)))   # (ny, nx)
            steps.append(int(k))
            t = ds.attrs.get("time")                          # openEMS may stamp it
            if t is None:
                have_time = False
            else:
                times_ns.append(float(np.ravel(t)[0]) * 1e9)
        return {
            "x_mm": x_mm, "y_mm": y_mm, "z_mm": float(z_mm[iz]),
            "steps": steps,
            "times_ns": times_ns if have_time and len(times_ns) == len(steps) else None,
            "mags": mags,
        }


# ------------------------------------------------------------------ overlays

def _beauty_overlay(media_dir: Path):
    """Load the orthographic Blender x-ray render + the mm rectangle it covers.

    Produced by:
        <bpy python> -m rf.viz.blender_render <blend> <config.json> <media> overlay
    Returns (RGBA array, [x0, x1, y0, y1]) or None when absent.
    """
    png = Path(media_dir) / "field_overlay.png"
    meta = png.with_suffix(".json")
    if not (png.exists() and meta.exists()):
        return None
    try:
        import matplotlib.image as mpimg
        extent = json.loads(meta.read_text())["extent_mm"]
        return mpimg.imread(png), extent
    except Exception:
        return None

def _is_battery_cell(part: dict) -> bool:
    """The battery body itself (by material), not its adhesive tabs/flex."""
    return any(k in (part.get("material_key") or "").lower()
               for k in _BATTERY_MATERIALS)


def _is_battery_tagged(part: dict) -> bool:
    tag = " ".join(str(part.get(k) or "") for k in
                   ("material_key", "node_path", "name")).lower()
    return any(k in tag for k in _BATTERY_TAGS)


def _device_overlays(device: dict | None):
    """Device outline + battery xy rectangles, shifted to the corner frame
    (same shift rule as placement3d.build_scene, so overlays land in the
    frame the candidate coordinates live in).

    -> (outline | None, [battery rects], [conductor rects]) — all in the
    same ((x0, y0), (x1, y1)) form
    """
    parts = (device or {}).get("parts") or []
    drawable = [p for p in parts if p.get("bbox_mm")]
    usable = [p for p in drawable if p.get("eps_r") is not None]
    ref = usable or drawable
    if not ref:
        return None, [], []
    allc = np.array([c for p in ref for c in p["bbox_mm"]], dtype=float)
    shift = -allc.min(axis=0)
    hi = allc.max(axis=0) + shift
    outline = ((0.0, 0.0), (float(hi[0]), float(hi[1])))

    # Every conductor's footprint, not just one box round the whole phone.
    # The field animation exists to show what the wave has to get past, and
    # "past" is these: shield cans, the board, the camera plateau, the frame.
    # A single bounding rectangle is a picture of a slab, and the slab is not
    # the device anyone is designing against.
    #
    # Enclosure layers are skipped by the same rule rf/placement.py screens
    # with: a part covering most of the device footprint is a shell, and
    # drawing it just puts another big rectangle on top of the outline.
    area_device = float(hi[0]) * float(hi[1]) or 1.0
    conductors = []
    for p in drawable:
        if (p.get("sigma_S_per_m") or 0.0) <= 1e4:
            continue
        lo = np.asarray(p["bbox_mm"][0], dtype=float) + shift
        chi = np.asarray(p["bbox_mm"][1], dtype=float) + shift
        if abs((chi[0] - lo[0]) * (chi[1] - lo[1])) >= 0.40 * area_device:
            continue
        conductors.append(((float(lo[0]), float(lo[1])),
                           (float(chi[0]), float(chi[1]))))

    cells = [p for p in drawable if _is_battery_cell(p)]
    if not cells:                       # fall back to the biggest tagged part
        tagged = [p for p in drawable if _is_battery_tagged(p)]
        if tagged:
            def _area(p):
                (x0, y0, _), (x1, y1, _) = p["bbox_mm"]
                return abs((x1 - x0) * (y1 - y0))
            cells = [max(tagged, key=_area)]
    rects = []
    for p in cells:
        lo = np.asarray(p["bbox_mm"][0], dtype=float) + shift
        bhi = np.asarray(p["bbox_mm"][1], dtype=float) + shift
        rects.append(((float(lo[0]), float(lo[1])), (float(bhi[0]), float(bhi[1]))))
    return outline, rects, conductors


def _antenna_footprint(candidate: dict, device: dict | None = None):
    """xy footprint of the strip, using the SAME clamped box the 3D renderer
    and the placement screener use (rf.placement.antenna_box) so the amber
    rectangle can never fall outside the chassis. Falls back to the raw
    feed/arm construction only when no device manifest is available.

    -> ((x0, y0), (x1, y1)) | None
    """
    if not candidate:
        return None
    if device and device.get("parts"):
        try:
            from ..placement import Device, Part, antenna_box
            allc = [c for p in device["parts"] if p.get("bbox_mm")
                    for c in p["bbox_mm"]]
            o = [min(c[i] for c in allc) for i in range(3)]
            parts = [Part(name=p.get("node_path") or "?",
                          material_key=p.get("material_key") or "",
                          lo=tuple(p["bbox_mm"][0][i] - o[i] for i in range(3)),
                          hi=tuple(p["bbox_mm"][1][i] - o[i] for i in range(3)),
                          sigma=float(p.get("sigma_S_per_m") or 0.0),
                          eps_r=float(p.get("eps_r") or 1.0))
                     for p in device["parts"] if p.get("bbox_mm")]
            size = tuple(max(p.hi[i] for p in parts) for i in range(3))
            lo, hi = antenna_box(candidate, Device(parts=parts, size_mm=size))
            return (lo[0], lo[1]), (hi[0], hi[1])
        except Exception:
            pass                       # fall through to the raw construction

    pos = np.asarray(candidate.get("position_mm") or (0.0, 0.0, 0.0), dtype=float)
    feed = np.asarray(candidate.get("feed_point_mm") or pos, dtype=float)
    w = IFA_ARM_WIDTH_MM
    xs = [pos[0] - w / 2, pos[0] + w / 2, feed[0] - w / 2, feed[0] + w / 2]
    ys = [pos[1] - w / 2, pos[1] + w / 2, feed[1] - w / 2, feed[1] + w / 2]
    arm_len = float(candidate.get("length_mm") or 0.0)
    if arm_len > 0:
        d = pos[:2] - feed[:2]
        axis = int(np.argmax(np.abs(d))) if np.any(d) else 1
        sign = float(np.sign(d[axis])) if d[axis] else 1.0
        tip = pos.copy()
        tip[axis] += sign * arm_len
        xs += [tip[0] - w / 2, tip[0] + w / 2]
        ys += [tip[1] - w / 2, tip[1] + w / 2]
    return (min(xs), min(ys)), (max(xs), max(ys))

def _write_message_gif(out: Path, message: str) -> str:
    """Single-frame GIF with an honest empty-state message (no crash)."""
    import matplotlib.pyplot as plt
    from matplotlib.animation import PillowWriter

    fig = plt.figure(figsize=(6.4, 4.2))
    fig.text(0.5, 0.5, message, ha="center", va="center",
             fontsize=13, color=FG, alpha=0.85, linespacing=1.6)
    writer = PillowWriter(fps=1)
    with writer.saving(fig, str(out), dpi=_GIF_DPI):
        writer.grab_frame()
    plt.close(fig)
    return str(out)


# ------------------------------------------------------------------ renderer

def render_field_animation(run: dict, out_gif: str, max_frames: int = 64,
                           fps: int = 14) -> str:
    """Render the transient |E| animation for `run` (rf.viz.data.load_run dict).

    Writes `out_gif`; when ffmpeg is on PATH also writes the same animation
    as .mp4 next to it. Returns the GIF path.
    """
    apply_theme()
    import matplotlib.pyplot as plt
    from matplotlib import animation
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    out = Path(out_gif)
    out.parent.mkdir(parents=True, exist_ok=True)

    h5_path = run.get("field_h5")
    if not h5_path or not Path(h5_path).exists():
        return _write_message_gif(
            out, "No field dump in this run\n"
                 "(Et.h5 missing - rerun with sim.dump_fields enabled)")
    try:
        data = _read_field_frames(h5_path, max_frames)
    except Exception as exc:                       # unreadable / foreign layout
        return _write_message_gif(
            out, f"Unreadable field dump\n({type(exc).__name__}: {exc})")
    if data is None:
        return _write_message_gif(out, "Field dump contains no time steps")

    x_mm, y_mm, mags = data["x_mm"], data["y_mm"], data["mags"]
    steps, times_ns = data["steps"], data["times_ns"]
    n = len(mags)

    vmax = float(np.percentile(np.stack(mags), _VMAX_PCT))
    if not np.isfinite(vmax) or vmax <= 0:
        vmax = 1.0

    result = run.get("result") or {}
    band = run.get("band") or {}
    candidate = run.get("candidate") or {}
    device = run.get("device")

    # ---- figure: manual layout so the colorbar/progress strip stay put ----
    fig = plt.figure(figsize=_FIGSIZE)
    ax = fig.add_axes([0.105, 0.095, 0.70, 0.815])
    X, Y = np.meshgrid(x_mm, y_mm)
    quad = ax.pcolormesh(X, Y, mags[0], cmap="inferno", shading="gouraud",
                         vmin=0.0, vmax=vmax, rasterized=True)
    ax.set_aspect("equal", adjustable="box", anchor="C")
    ax.grid(False)
    ax.set_xlim(float(x_mm.min()), float(x_mm.max()))
    ax.set_ylim(float(y_mm.min()), float(y_mm.max()))
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.tick_params(labelsize=9)

    # Companion axes placed against the *apparent* (aspect-locked) plot box.
    ax.apply_aspect()
    pos = ax.get_position()
    cax = fig.add_axes([pos.x1 + 0.035, pos.y0, 0.030, pos.height])
    bar_ax = fig.add_axes([pos.x0, 0.034, pos.width, 0.008])

    cb = fig.colorbar(quad, cax=cax)
    cb.set_label("$|E|$ (arb. units) - near-field-clipped scale "
                 f"({_VMAX_PCT:.0f}th pct)", fontsize=9.5)
    cb.ax.tick_params(labelsize=8.5)

    # ---- overlays ----------------------------------------------------------
    handles = []

    # Preferred backdrop: the Blender x-ray line art of the REAL device,
    # rendered orthographically so it maps 1:1 onto a known mm rectangle
    # (see rf/viz/blender_render.render_overlay). Falls back to the bbox
    # outline below when that render hasn't been produced for this run.
    beauty = _beauty_overlay(Path(out_gif).parent)
    if beauty is not None:
        img, extent = beauty
        # origin="upper": Blender writes row 0 at the TOP of the PNG, while
        # the |E| map underneath is drawn origin="lower". Matching them by
        # eye is how the overlay ends up mirrored about the device centre.
        ax.imshow(img, extent=extent, origin="upper", zorder=5,
                  interpolation="bilinear", aspect="equal")
        handles.append(Line2D([0], [0], color=PALETTE["metal"], lw=1.6,
                              label="Device (x-ray)"))

    outline, battery_rects, conductor_rects = _device_overlays(device)
    if beauty is not None:
        # the render already shows every part
        outline, battery_rects, conductor_rects = None, [], []
    for (cx0, cy0), (cx1, cy1) in conductor_rects:
        ax.add_patch(Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0,
                               fill=False, edgecolor=PALETTE["metal"],
                               linewidth=0.7, alpha=0.5, zorder=5))
    if conductor_rects:
        handles.append(Line2D([0], [0], color=PALETTE["metal"], lw=1.2,
                              alpha=0.8,
                              label=f"Conductors ({len(conductor_rects)})"))
    if outline is not None:
        (ox0, oy0), (ox1, oy1) = outline
        ax.add_patch(Rectangle((ox0, oy0), ox1 - ox0, oy1 - oy0,
                               fill=False, edgecolor=PALETTE["outline"],
                               linewidth=1.6, alpha=0.95, zorder=5))
        handles.append(Line2D([0], [0], color=PALETTE["outline"], lw=1.6,
                              label="Device outline"))
    elif beauty is None:
        ax.text(0.03, 0.03, "device manifest unavailable",
                transform=ax.transAxes, color=FG, alpha=0.6, fontsize=9)
    for (bx0, by0), (bx1, by1) in battery_rects:
        ax.add_patch(Rectangle((bx0, by0), bx1 - bx0, by1 - by0,
                               fill=False, edgecolor=PALETTE["battery"],
                               linewidth=1.5, linestyle="--", alpha=0.9,
                               zorder=6))
    if battery_rects:
        handles.append(Line2D([0], [0], color=PALETTE["battery"], lw=1.5,
                              linestyle="--", label="Battery"))
    ant_rect = _antenna_footprint(candidate, device)
    if ant_rect is not None:
        (ax0, ay0), (ax1, ay1) = ant_rect
        ax.add_patch(Rectangle((ax0, ay0), ax1 - ax0, ay1 - ay0,
                               facecolor=PALETTE["antenna"], alpha=0.30,
                               edgecolor=PALETTE["antenna"], linewidth=1.3,
                               zorder=7))
        handles.append(Line2D([0], [0], color=PALETTE["antenna"], lw=3.5,
                              alpha=0.8, label="Antenna"))
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8.5,
                  borderpad=0.55, labelspacing=0.5)

    # ---- static annotations -------------------------------------------------
    ant = candidate.get("antenna_type") or "Antenna"
    cid = candidate.get("candidate_id") or "?"
    fig.text(0.5, 0.968,
             f"{ant} {cm_text(cid)} - transient $|E|$, z = {data['z_mm']:.2f} mm slice",
             ha="center", va="top", fontsize=14)
    f_lo, f_hi = band.get("f_low_ghz"), band.get("f_high_ghz")
    if f_lo is not None and f_hi is not None:
        pretty = (band.get("id") or "target band").replace("_", " ").upper()
        ax.text(0.03, 0.975, f"{pretty} - centre {(f_lo + f_hi) / 2:.3f} GHz",
                transform=ax.transAxes, ha="left", va="top", fontsize=9.5,
                color=FG,
                bbox=dict(facecolor="#101014", edgecolor=GRID, alpha=0.85,
                          boxstyle="round,pad=0.35"), zorder=9)
    if "DEMO" in (result.get("notes") or "").upper():
        fig.text(0.985, 0.006, "demo data", ha="right", va="bottom",
                 fontsize=9, style="italic", color=FG, alpha=0.3)

    # ---- per-frame artists ---------------------------------------------------
    def _time_label(i: int) -> str:
        if times_ns is not None:
            return f"t = {times_ns[i]:.3f} ns"
        return f"t = {steps[i]} steps"

    title = ax.set_title(_time_label(0), fontsize=11.5, pad=8)
    bar_ax.set_xlim(0, 1)
    bar_ax.set_ylim(0, 1)
    bar_ax.set_axis_off()
    bar_ax.axhspan(0, 1, color=GRID, alpha=0.9)                # track
    bar_line, = bar_ax.plot([0, 1 / n], [0.5, 0.5], color=PALETTE["s11"],
                            linewidth=3.2, solid_capstyle="butt")

    def _update(i):
        quad.set_array(mags[i])
        title.set_text(_time_label(i))
        bar_line.set_data([0, (i + 1) / n], [0.5, 0.5])
        return quad, title, bar_line

    anim = animation.FuncAnimation(fig, _update, frames=n,
                                   interval=1000.0 / fps, blit=False)
    from .output import save_animation
    save_animation(anim, out, fps, _GIF_DPI)

    plt.close(fig)
    return str(out)


if __name__ == "__main__":
    from .data import load_run

    run = load_run("runs/demo")
    p = render_field_animation(run, "runs/demo/media/field.gif")
    print(f"field -> {Path(p).resolve()} ({Path(p).stat().st_size} bytes)")
    mp4 = Path(p).with_suffix(".mp4")
    if mp4.exists():
        print(f"field -> {mp4.resolve()} ({mp4.stat().st_size} bytes)")
