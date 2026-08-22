"""Animated technical-briefing card — "the numbers tell the story".

    from rf.viz.anim_dashboard import render_dashboard
    render_dashboard(load_run("runs/demo"), "runs/demo/media/dashboard.gif")

One dark 16:9 card, three zones:
- LEFT   the S11 curve draws itself behind a sweeping frequency cursor;
         band shading and the spec line are static from frame 0; the amber
         resonance marker pops in when the reveal crosses it.
- RIGHT  four metric tiles (S11 min / Resonance / Bandwidth / Efficiency)
         count up and settle once the cursor passes resonance; each tile's
         border flips to PALETTE good/bad against its target.
- BOTTOM a fact ticker fading through real project milestones.
- END    a PASS/FAIL stamp from result.meets_requirements, then a hold.

Always writes the GIF; writes an H.264 MP4 twin when ffmpeg is on PATH.
Styling comes exclusively from rf.viz.theme (dark, Computer Modern).
"""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path

import numpy as np

from .theme import BG, FG, GRID, PALETTE, apply_theme

# ---------------------------------------------------------------- geometry
_FIGSIZE = (12.8, 7.2)        # 16:9
_GIF_DPI = 90                 # 1152 x 648 -- comfortably >= 640 px tall
_MP4_DPI = 150                # 1920 x 1080

_AX_S11 = (0.055, 0.20, 0.535, 0.60)     # left zone (~60 % of the card)
_AX_TILES = (0.625, 0.185, 0.35, 0.645)  # right zone (~40 %)
_AX_TICKER = (0.045, 0.022, 0.91, 0.095)

# ---------------------------------------------------------------- timeline (s)
_T_TOTAL = 12.0
_T0_REVEAL = 0.35             # reveal start
_T_REVEAL = 5.3               # reveal duration
_TILE_STAGGER = 0.18          # per-tile count-up offset after resonance
_TILE_RAMP = 1.1              # count-up duration per tile
_FACT_DUR = 2.1               # seconds per ticker fact (fade in/out inside)
_FACT_FADE = 0.42
_T_STAMP = 10.55              # PASS/FAIL stamp entrance
_STAMP_RAMP = 0.45

# Real project facts (verbatim numbers from rf/progress_simulation.md);
# symbols are typeset with mathtext because cmr10's OT1 layout has no
# usable  ->  <  >  ~  glyphs.
_FACTS = [
    r"Real device model: Apple iPhone 15 Pro - 191 parts, 13 materials",
    r"Bare ground plane $S_{11}$ $-9.8$ dB $\rightarrow$ $-7.5$ dB with real "
    r"device materials loaded: the phone detunes the antenna",
    r"Solver: openEMS FDTD - coarse mesh $\lambda/20 \approx 19$ mm - MUR boundaries",
    r"Board footprint 71.45 $\times$ 146.6 mm - GPS L1 target 1575.42 MHz",
    r"Feed-pin geometry bug found and fixed: VSWR 314 $\rightarrow$ 24",
]


def _plain_len(fact: str) -> int:
    """Approximate on-screen character count of a mathtext-bearing string."""
    return len(re.sub(r"\\[A-Za-z]+", "~", fact.replace("$", "")))


def _clip01(u: float) -> float:
    return 0.0 if u < 0.0 else 1.0 if u > 1.0 else u


def _smoothstep(u: float) -> float:
    u = _clip01(u)
    return u * u * (3.0 - 2.0 * u)


def _ease_out(u: float) -> float:
    u = _clip01(u)
    return 1.0 - (1.0 - u) ** 3


# ------------------------------------------------------------------ fallback

def _render_empty(out: Path, fps: int, message: str) -> str:
    """Honest empty-state animation when the run has no S11 curve."""
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    fig = plt.figure(figsize=_FIGSIZE)
    txt = fig.text(0.5, 0.55, message, ha="center", va="center",
                   fontsize=17, color=FG, alpha=0.0)
    fig.text(0.5, 0.42, "dashboard unavailable for this run",
             ha="center", va="center", fontsize=12, color=FG, alpha=0.45)

    n = max(int(round(2.0 * fps)), 8)

    def update(i):
        txt.set_alpha(_ease_out(3.0 * i / n))
        return []

    anim = FuncAnimation(fig, update, frames=n, interval=1000.0 / fps)
    anim.save(str(out), writer=PillowWriter(fps=fps), dpi=_GIF_DPI)
    plt.close(fig)
    return str(out)


# ---------------------------------------------------------------- the render

def render_dashboard(run: dict, out_gif: str, fps: int = 15) -> str:
    """Render the animated briefing card for `run` (rf.viz.data.load_run dict).

    Returns the GIF path; an MP4 twin (same stem) is written when ffmpeg
    is available on PATH.
    """
    apply_theme()
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyBboxPatch, Rectangle

    fps = max(int(fps), 4)
    out = Path(out_gif)
    out.parent.mkdir(parents=True, exist_ok=True)

    result = run.get("result") or {}
    band = run.get("band") or {}
    candidate = run.get("candidate") or {}

    curve = result.get("s11_curve") or []
    if len(curve) < 2:
        return _render_empty(out, fps,
                             "No $S_{11}$ curve in this run (result.s11_curve is empty)")

    pts = sorted(curve, key=lambda p: p["f_ghz"])
    f = np.array([p["f_ghz"] for p in pts], dtype=float)
    s = np.array([p["s11_db"] for p in pts], dtype=float)
    f_min, f_max = float(f[0]), float(f[-1])

    f_lo = band.get("f_low_ghz")
    f_hi = band.get("f_high_ghz")
    spec_db = band.get("s11_db_max", -8.0)
    eff_min = band.get("efficiency_min", 0.45)

    s11_min = result.get("s11_min_db")
    if s11_min is None:
        s11_min = float(s.min())
    f_res = result.get("resonant_ghz")
    if f_res is None:
        f_res = float(f[int(np.argmin(s))])
    bw_mhz = result.get("bandwidth_mhz")
    eff = result.get("efficiency")
    meets = bool(result.get("meets_requirements"))

    # ------------------------------------------------------------ metric tiles
    def _tile(label, value, fmt, start, target_txt, ok):
        return {"label": label, "value": value, "fmt": fmt, "start": start,
                "target": target_txt, "ok": ok}

    in_band = (f_lo is not None and f_hi is not None
               and f_lo <= float(f_res) <= f_hi)
    tiles = [
        _tile(r"$S_{11}$ min", s11_min, lambda v: f"${v:.1f}$ dB", 0.0,
              rf"target $\leq {spec_db:g}$ dB",
              None if s11_min is None else float(s11_min) <= float(spec_db)),
        _tile("Resonance", f_res, lambda v: f"${v:.4f}$ GHz",
              f_lo if f_lo is not None else f_min,
              (rf"target ${f_lo:.3f}$-${f_hi:.3f}$ GHz"
               if f_lo is not None and f_hi is not None else "target band n/a"),
              None if f_res is None else in_band),
        _tile("Bandwidth", bw_mhz, lambda v: f"${v:.1f}$ MHz", 0.0,
              r"target $\geq 2$ MHz (GPS C/A)",
              None if bw_mhz is None else float(bw_mhz) >= 2.0),
        _tile("Efficiency", None if eff is None else 100.0 * float(eff),
              lambda v: f"${v:.1f}$%", 0.0,
              rf"target $\geq {100.0 * eff_min:g}$%",
              None if eff is None else float(eff) >= float(eff_min)),
    ]

    # ------------------------------------------------------------- timeline
    n_frames = int(round(_T_TOTAL * fps))
    times = np.arange(n_frames) / fps

    def cursor_at(t: float) -> float:
        return f_min + (f_max - f_min) * _smoothstep((t - _T0_REVEAL) / _T_REVEAL)

    # moment the reveal crosses resonance (tiles + marker trigger)
    tt = np.linspace(_T0_REVEAL, _T0_REVEAL + _T_REVEAL, 4001)
    cc = np.array([cursor_at(x) for x in tt])
    hit = np.nonzero(cc >= min(max(float(f_res), f_min), f_max))[0]
    t_res = float(tt[hit[0]]) if hit.size else _T0_REVEAL + 0.6 * _T_REVEAL
    t_reveal_end = _T0_REVEAL + _T_REVEAL

    # --------------------------------------------------------------- figure
    fig = plt.figure(figsize=_FIGSIZE)
    surface = mpl.rcParams["legend.facecolor"]   # theme's elevated-panel tone

    # header ---------------------------------------------------------------
    ant = candidate.get("antenna_type") or "Antenna"
    band_id = (band.get("id") or "band").replace("_", " ").upper()
    cid = result.get("candidate_id") or candidate.get("candidate_id") or "unknown"
    fig.text(0.045, 0.935, f"{ant} placement - technical briefing",
             fontsize=17.5, color=FG, ha="left", va="center")
    demo_tag = " | DEMO data" if "DEMO" in (result.get("notes") or "") else ""
    fig.text(0.955, 0.935,
             f"candidate {cid} | {band_id} | openEMS FDTD{demo_tag}",
             fontsize=10.5, color=FG, alpha=0.55, ha="right", va="center")
    fig.add_artist(Line2D([0.045, 0.955], [0.905, 0.905],
                          transform=fig.transFigure, color=GRID, lw=0.8))
    fig.add_artist(Line2D([0.045, 0.955], [0.135, 0.135],
                          transform=fig.transFigure, color=GRID, lw=0.8))

    # LEFT: S11 reveal -------------------------------------------------------
    ax = fig.add_axes(_AX_S11)
    ax.set_title(r"$S_{11}$ frequency response", loc="left", fontsize=13.5, pad=8)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel(r"$S_{11}$ (dB)")
    y_lo = float(s.min()) - 2.5
    ax.set_xlim(f_min, f_max)
    ax.set_ylim(y_lo, 0.0)
    ax.xaxis.set_major_locator(mpl.ticker.MaxNLocator(6))

    if f_lo is not None and f_hi is not None:
        ax.axvspan(f_lo, f_hi, color=PALETTE["band"], alpha=0.14, zorder=1)
        ax.text(0.5 * (f_lo + f_hi), y_lo + 0.955 * (0.0 - y_lo),
                f"{band_id} band", ha="center", va="top",
                fontsize=10, color=PALETTE["band"], alpha=0.95, zorder=2)
    if spec_db is not None:
        ax.axhline(spec_db, color=PALETTE["spec"], linestyle="--",
                   linewidth=1.5, zorder=4)
        ax.text(f_max - 0.015 * (f_max - f_min), float(spec_db) + 0.4,
                f"spec ${spec_db:g}$ dB", ha="right", va="bottom",
                fontsize=9.5, color=PALETTE["spec"], zorder=4)

    glow, = ax.plot([], [], color=PALETTE["s11"], lw=6.5, alpha=0.16,
                    solid_capstyle="round", zorder=4)
    line, = ax.plot([], [], color=PALETTE["s11"], lw=2.4, zorder=5)
    cursor = ax.axvline(f_min, color=FG, lw=1.0, alpha=0.0, zorder=6)
    pen, = ax.plot([], [], marker="o", ms=6, color=PALETTE["s11"],
                   mec="none", ls="none", zorder=7)
    marker, = ax.plot([], [], marker="o", ms=0, color=PALETTE["resonance"],
                      mec=FG, mew=0.8, ls="none", zorder=8)
    res_label = ax.annotate(
        rf"$f_{{\mathrm{{res}}}} = {float(f_res):.4f}$ GHz",
        xy=(float(f_res), float(s.min())), xytext=(-10, 34),
        textcoords="offset points", ha="right", va="bottom",
        fontsize=11, color=PALETTE["resonance"], alpha=0.0, zorder=8)

    # RIGHT: metric tiles ------------------------------------------------------
    axp = fig.add_axes(_AX_TILES)
    axp.set_axis_off()
    axp.set_xlim(0, 1)
    axp.set_ylim(0, 1)
    tile_geo = [(0.015, 0.535), (0.525, 0.535), (0.015, 0.025), (0.525, 0.025)]
    tw, th = 0.46, 0.44
    tile_art = []
    for (tx, ty), tile in zip(tile_geo, tiles):
        box = FancyBboxPatch(
            (tx, ty), tw, th, transform=axp.transAxes,
            boxstyle="round,pad=0.012,rounding_size=0.035",
            facecolor=surface, edgecolor=GRID, linewidth=1.6, zorder=2)
        axp.add_patch(box)
        cx = tx + tw / 2.0
        axp.text(cx, ty + th - 0.055, tile["label"], ha="center", va="top",
                 fontsize=12, color=FG, alpha=0.8, zorder=3)
        val = axp.text(cx, ty + 0.52 * th, "--", ha="center", va="center",
                       fontsize=21, color=FG, alpha=0.35, zorder=3)
        axp.text(cx, ty + 0.052, tile["target"], ha="center", va="bottom",
                 fontsize=9, color=FG, alpha=0.45, zorder=3)
        tile_art.append((box, val))

    # BOTTOM: fact ticker -----------------------------------------------------
    axt = fig.add_axes(_AX_TICKER)
    axt.set_axis_off()
    axt.set_xlim(0, 1)
    axt.set_ylim(0, 1)
    ticker = axt.text(0.5, 0.5, "", ha="center", va="center",
                      fontsize=13, color=FG, alpha=0.0)

    # END: verdict stamp --------------------------------------------------------
    verdict = "PASS" if meets else "FAIL"
    v_color = PALETTE["good"] if meets else PALETTE["bad"]
    overlay = Rectangle((0, 0), 1, 1, transform=fig.transFigure,
                        facecolor=BG, edgecolor="none", alpha=0.0, zorder=20)
    fig.add_artist(overlay)
    stamp = fig.text(0.5, 0.545, verdict, ha="center", va="center",
                     fontsize=84, color=v_color, alpha=0.0,
                     rotation=8, zorder=22)
    stamp_sub = fig.text(0.5, 0.36,
                         "requirements met" if meets else "requirements not met",
                         ha="center", va="center", fontsize=15, color=FG,
                         alpha=0.0, zorder=22)

    # ------------------------------------------------------------------ update
    def update(i):
        t = float(times[min(i, n_frames - 1)])

        # -- left: line reveal + cursor
        x_c = cursor_at(t)
        idx = int(np.searchsorted(f, x_c))
        xs, ys = f[:idx], s[:idx]
        if 0 < idx < len(f):
            y_c = float(np.interp(x_c, f, s))
            xs = np.append(xs, x_c)
            ys = np.append(ys, y_c)
        elif idx >= len(f):
            y_c = float(s[-1])
        else:
            y_c = float(s[0])
        line.set_data(xs, ys)
        glow.set_data(xs, ys)

        sweep_a = 0.55 if t < t_reveal_end else \
            0.55 * (1.0 - _clip01((t - t_reveal_end) / 0.5))
        cursor.set_xdata([x_c, x_c])
        cursor.set_alpha(sweep_a)
        if sweep_a > 0.02 and len(xs):
            pen.set_data([xs[-1]], [ys[-1]])
            pen.set_alpha(sweep_a / 0.55)
        else:
            pen.set_data([], [])

        # -- resonance marker pop (then a subtle idle pulse)
        if t >= t_res:
            u = _clip01((t - t_res) / 0.5)
            if u < 1.0:
                ms = 9.5 * (0.25 + 1.05 * _ease_out(u))
            else:
                ms = 9.5 + 0.7 * math.sin(2.0 * math.pi * 0.7 * (t - t_res - 0.5))
            marker.set_data([float(f_res)], [float(s.min())])
            marker.set_markersize(ms)
            marker.set_alpha(min(1.0, 3.0 * u))
            res_label.set_alpha(_ease_out(u))

        # -- right: tiles counting up, borders flipping on settle
        for k, ((box, val), tile) in enumerate(zip(tile_art, tiles)):
            t_start = t_res + k * _TILE_STAGGER
            if t < t_start:
                continue
            if tile["value"] is None:
                val.set_text("n/a")
                val.set_alpha(0.6)
                continue
            u = _clip01((t - t_start) / _TILE_RAMP)
            v = tile["start"] + (float(tile["value"]) - tile["start"]) * _ease_out(u)
            val.set_text(tile["fmt"](v))
            val.set_alpha(0.55 + 0.45 * u)
            if u >= 1.0 and tile["ok"] is not None:
                box.set_edgecolor(PALETTE["good"] if tile["ok"] else PALETTE["bad"])
                box.set_linewidth(2.2)

        # -- bottom: fact ticker
        fact_i = int(t // _FACT_DUR)
        if fact_i < len(_FACTS):
            fact = _FACTS[fact_i]
            local = t - fact_i * _FACT_DUR
            a_in = _clip01(local / _FACT_FADE)
            a_out = _clip01((_FACT_DUR - local) / (_FACT_FADE + 0.05))
            a = 0.95 * min(_ease_out(a_in), _ease_out(a_out))
            ticker.set_text(fact)
            ticker.set_fontsize(13.0 if _plain_len(fact) <= 80 else 11.4)
            ticker.set_alpha(a)
            ticker.set_position((0.5, 0.42 + 0.10 * _ease_out(a_in)))
        else:
            ticker.set_alpha(0.0)

        # -- ending: verdict stamp over a dimming overlay
        if t >= _T_STAMP:
            u = _ease_out((t - _T_STAMP) / _STAMP_RAMP)
            overlay.set_alpha(0.55 * u)
            stamp.set_alpha(u)
            stamp.set_fontsize(100.0 - 22.0 * u)
            stamp.set_bbox(dict(boxstyle="round,pad=0.45", facecolor=BG,
                                edgecolor=v_color, linewidth=3.5,
                                alpha=0.85 * u))
            stamp_sub.set_alpha(0.8 * u)
        return []

    anim = FuncAnimation(fig, update, frames=n_frames, interval=1000.0 / fps)
    anim.save(str(out), writer=PillowWriter(fps=fps), dpi=_GIF_DPI)

    if shutil.which("ffmpeg"):
        mp4 = out.with_suffix(".mp4")
        try:
            anim.save(str(mp4), dpi=_MP4_DPI,
                      writer=FFMpegWriter(fps=fps, codec="h264",
                                          extra_args=["-pix_fmt", "yuv420p"]))
        except Exception as exc:                      # GIF already on disk
            print(f"note: mp4 twin skipped ({type(exc).__name__}: {exc})")

    plt.close(fig)
    return str(out)


if __name__ == "__main__":
    import sys

    from .data import load_run

    run_dir = sys.argv[1] if len(sys.argv) > 1 else "runs/demo"
    run = load_run(run_dir)
    gif = render_dashboard(run, str(Path(run_dir) / "media" / "dashboard.gif"))
    print(gif)
    mp4 = Path(gif).with_suffix(".mp4")
    if mp4.exists():
        print(str(mp4))
