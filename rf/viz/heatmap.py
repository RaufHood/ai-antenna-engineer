"""Where CAN the antenna go? — the placement map the agent searches.

`rf/placement.py` screens one candidate in about a millisecond: is it legal,
what metal is crowding it, can the signal escape. Sweep that over a grid and
you get a map of the whole device, which is what turns an agent's "try
somewhere else" into "try here next" — and, for a human, is the single
clearest picture of why phone antennas live where they live.

Two panels over the real x-ray backdrop:

    legality   which positions are buildable at all, and what blocks the rest
    score      the ranking field: escape fraction weighted by metal clearance

    .venv-viz/bin/python -m rf.viz.heatmap runs/demo
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .theme import FG, PALETTE, apply_theme


def _overlay(media_dir: Path):
    png = Path(media_dir) / "field_overlay.png"
    meta = png.with_suffix(".json")
    if not (png.exists() and meta.exists()):
        return None
    import matplotlib.image as mpimg
    return mpimg.imread(png), json.loads(meta.read_text())["extent_mm"]


def render_placement_map(run, out_png: str | None = None, *,
                         step_mm: float = 3.0,
                         manifest: str = "rf/blend_loader/out/device.json") -> str:
    """`run` may be a run directory or the dict `data.load_run()` returns —
    the CLI hands renderers the loaded run, humans hand them a path."""
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.pyplot as plt

    from ..placement import Device, scan

    apply_theme()
    run_dir = Path(run["run_dir"] if isinstance(run, dict) else run)
    out = Path(out_png or run_dir / "media" / "placement_map.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    dev = Device.from_manifest(manifest)
    cfg_path = run_dir / "config.json"
    cand = json.loads(cfg_path.read_text())["candidate"] if cfg_path.exists() else {}
    # Sweep at the candidate's own height, not scan()'s mid-stack default: a
    # map drawn at a different z from the antenna it accompanies is a map of a
    # different antenna. The feed z is where the radiator sits.
    z = cand.get("feed_point_mm") or cand.get("position_mm")
    rows = scan(dev, band_length_mm=float(cand.get("length_mm", 27.5)),
                step_mm=step_mm, z_mm=float(z[2]) if z else None)

    xs = sorted({r["position_mm"][0] for r in rows})
    ys = sorted({r["position_mm"][1] for r in rows})
    ix = {v: i for i, v in enumerate(xs)}
    iy = {v: i for i, v in enumerate(ys)}
    legal = np.full((len(ys), len(xs)), np.nan)
    score = np.full((len(ys), len(xs)), np.nan)
    for r in rows:
        j, i = iy[r["position_mm"][1]], ix[r["position_mm"][0]]
        legal[j, i] = 1.0 if r["legal"] else 0.0
        score[j, i] = r["score"] if r["legal"] else np.nan

    extent = [min(xs), max(xs), min(ys), max(ys)]
    beauty = _overlay(run_dir / "media")

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 8.6))
    cmap_legal = LinearSegmentedColormap.from_list(
        "legal", [PALETTE["bad"], PALETTE["good"]])
    cmap_score = LinearSegmentedColormap.from_list(
        "score", ["#0b0b12", PALETTE["band"], PALETTE["s11"], PALETTE["resonance"]])

    n_legal = int(np.nansum(legal))
    panels = [
        (axes[0], legal, cmap_legal, "Buildable positions",
         f"{n_legal} of {len(rows)} grid points clear every component",
         None, None),
        (axes[1], score, cmap_score, "Placement score",
         "escape fraction weighted by metal clearance",
         0.0, float(np.nanmax(score)) if np.isfinite(np.nanmax(score)) else 1.0),
    ]
    for ax, data, cmap, title, sub, vmin, vmax in panels:
        im = ax.imshow(data, origin="lower", extent=extent, cmap=cmap,
                       vmin=vmin, vmax=vmax, interpolation="bilinear",
                       aspect="equal", alpha=0.92, zorder=2)
        if beauty is not None:
            # origin="upper": Blender's PNG row 0 is the top edge (see
            # anim_field._beauty_overlay); the heatmaps are origin="lower".
            ax.imshow(beauty[0], extent=beauty[1], origin="upper", zorder=3,
                      interpolation="bilinear", aspect="equal", alpha=0.75)
        ax.set_title(title, fontsize=13.5, pad=26)
        ax.text(0.5, 1.008, sub, transform=ax.transAxes, ha="center",
                va="bottom", fontsize=9, color=FG, alpha=0.62)
        ax.set_xlabel("x (mm)")
        ax.set_ylabel("y (mm)")
        ax.grid(False)
        cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
        cb.ax.tick_params(labelsize=8.5)
        if data is legal:
            cb.set_ticks([0, 1])
            cb.ax.set_yticklabels(["blocked", "legal"], fontsize=9)

    # mark the best few positions on the score panel
    best = [r for r in rows if r["legal"]][:5]
    for k, r in enumerate(best):
        x, y = r["position_mm"][0], r["position_mm"][1]
        axes[1].plot(x, y, marker="o", ms=9, mfc="none", zorder=6,
                     mec=PALETTE["resonance"], mew=1.9)
        axes[1].annotate(f"{k + 1}", (x, y), textcoords="offset points",
                         xytext=(9, 7), color=PALETTE["resonance"], fontsize=9,
                         zorder=6)
    if best:
        b = best[0]
        axes[1].text(0.02, 0.02,
                     f"best: ({b['position_mm'][0]:.0f}, {b['position_mm'][1]:.0f}) mm  "
                     f"escape {b['escape_fraction']:.0%}",
                     transform=axes[1].transAxes, fontsize=9,
                     color=PALETTE["resonance"], alpha=0.95)

    fig.suptitle(f"Antenna placement map - {dev.name or 'device'}",
                 fontsize=15.5, y=0.985)
    fig.text(0.5, 0.012,
             f"{len(dev.parts)} parts - "
             f"{sum(1 for p in dev.parts if p.is_metal)} conductive - "
             f"grid step {step_mm:.0f} mm - screened by rf/placement.py, no solver",
             ha="center", fontsize=8.6, color=FG, alpha=0.55)
    fig.tight_layout(rect=[0, 0.03, 1, 0.96])
    fig.savefig(out)
    plt.close(fig)
    return str(out)


if __name__ == "__main__":
    import sys
    p = render_placement_map(sys.argv[1] if len(sys.argv) > 1 else "runs/demo")
    print(f"placement map -> {Path(p).resolve()} ({Path(p).stat().st_size} bytes)")
