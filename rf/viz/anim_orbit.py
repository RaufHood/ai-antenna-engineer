"""360-degree orbit of the 3D placement x-ray.

    from rf.viz.anim_orbit import render_orbit
    render_orbit(load_run("runs/demo"), "runs/demo/media/orbit.gif")

The scene is built ONCE with placement3d.build_scene; every frame only
mutates the camera (ax.view_init) -- rebuilding ~200 wireframe collections
per frame would make an 8 s GIF take minutes and buys nothing.

The azimuth sweep is eased (zero angular velocity at both ends), so the
loop dwells briefly on the canonical iso view (azim = -58) before setting
off again -- deliberate, not a metronome.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .placement3d import build_scene
from .theme import FG, apply_theme

# Layout constants -- geometry, not style.
_FIGSIZE = (9.8, 8.0)
_GIF_DPI = 100                     # 8.0 in * 100 dpi = 800 px tall (>= 640)
_MAX_FRAMES = 120
_AZIM_ISO = -58.0                  # matches placement3d's iso view


def render_orbit(run: dict, out_gif: str, seconds: float = 8, fps: int = 15,
                 elev: float = 22) -> str:
    """Render the orbiting placement x-ray for `run`; returns the GIF path."""
    apply_theme()
    import matplotlib.pyplot as plt
    from matplotlib import animation

    out = Path(out_gif)
    out.parent.mkdir(parents=True, exist_ok=True)

    n = int(round(seconds * fps))
    n = max(24, min(n, _MAX_FRAMES))

    fig = plt.figure(figsize=_FIGSIZE)
    ax = fig.add_subplot(111, projection="3d")
    build_scene(ax, run, elev=elev, azim=_AZIM_ISO)

    candidate = run.get("candidate") or {}
    device = run.get("device")
    result = run.get("result") or {}
    ant = candidate.get("antenna_type") or "Antenna"
    cid = candidate.get("candidate_id") or "?"
    name = ((device or {}).get("name") or "unknown device").split(" (")[0]
    n_parts = len((device or {}).get("parts") or [])

    # Title block top-left (same spot as the still renders; legend owns the
    # top-right corner).
    ax.text2D(0.01, 1.055, f"{ant} placement - x-ray orbit",
              transform=ax.transAxes, ha="left", va="top", fontsize=14.5)
    if n_parts:
        ax.text2D(0.012, 1.018, f"{n_parts} parts", transform=ax.transAxes,
                  ha="left", va="top", fontsize=10, color=FG, alpha=0.6)
    # Fixed dim caption, bottom-centre: what device, which candidate.
    fig.text(0.5, 0.015, f"{name} - candidate {cid}", ha="center",
             va="bottom", fontsize=10.5, color=FG, alpha=0.55)
    if "DEMO" in (result.get("notes") or "").upper():
        fig.text(0.015, 0.012, "demo data", ha="left", va="bottom",
                 fontsize=9, style="italic", color=FG, alpha=0.3)

    # Eased full turn: s(u) = u - sin(2*pi*u)/(2*pi) has s'(0) = s'(1) = 0,
    # so the orbit slows into and out of the iso view it starts from.
    u = np.linspace(0.0, 1.0, n)
    azims = _AZIM_ISO + 360.0 * (u - np.sin(2.0 * np.pi * u) / (2.0 * np.pi))

    def _update(i):
        ax.view_init(elev=elev, azim=azims[i])
        return []

    anim = animation.FuncAnimation(fig, _update, frames=n,
                                   interval=1000.0 / fps, blit=False)
    from .output import save_animation
    save_animation(anim, out, fps, _GIF_DPI)
    plt.close(fig)
    return str(out)


if __name__ == "__main__":
    from .data import load_run

    run = load_run("runs/demo")
    p = render_orbit(run, "runs/demo/media/orbit.gif")
    print(f"orbit -> {Path(p).resolve()} ({Path(p).stat().st_size} bytes)")
