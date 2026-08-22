"""Turns raw solver output into things a human can look at: the E-field
time-domain dump (SimOptions.dump_fields=True, see geometry.py) into a GIF
of the wave leaving the feed, and the S11 curve into a PNG. Nothing here is
part of the run_simulation() contract -- both are opt-in, human-facing
extras, called from the __main__ demo in run_simulation.py.
"""
from __future__ import annotations

from pathlib import Path


def render_field_animation(
    sim_path: str,
    out_gif: str | None = None,
    dump_name: str = "Et",
    geometry_mm: dict | None = None,
    max_frames: int = 100,
    fps: int = 12,
) -> str:
    """Reads <sim_path>/<dump_name>.h5 (openEMS time-domain E-field dump,
    written when geometry.build_ifa_geometry ran with sim.dump_fields=True)
    and renders |E| on the antenna's xy-plane as an animated GIF.

    openEMS's HDF5 dump layout (empirically confirmed, not documented in
    the Python bindings): /FieldData/TD/<8-digit-timestep> holds one
    (3, nz, ny, nx) array per dumped step (Ex/Ey/Ez; already decimated in
    time by the engine -- a 15000-step run wrote 251 frames, no manual
    stride needed), and /Mesh/x,y,z hold the (non-uniform, SmoothMeshLines)
    grid coordinates in metres.
    """
    import h5py
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    h5_path = Path(sim_path) / f"{dump_name}.h5"
    if not h5_path.exists():
        raise FileNotFoundError(
            f"{h5_path} not found -- was this structure built with "
            "SimOptions(dump_fields=True)?"
        )

    with h5py.File(h5_path, "r") as f:
        x_mm = f["Mesh/x"][:] * 1e3
        y_mm = f["Mesh/y"][:] * 1e3
        keys = sorted(f["FieldData/TD"].keys(), key=int)
        stride = max(1, len(keys) // max_frames)
        keys = keys[::stride]
        timesteps = [int(k) for k in keys]
        # (3, nz, ny, nx) -> |E| on the single z-layer this dump box covers.
        frames = np.stack(
            [np.sqrt((f["FieldData/TD"][k][:] ** 2).sum(axis=0))[0] for k in keys]
        )

    # Robust scale: the feed cell's near-field is orders of magnitude above
    # the radiating field: without normalizing, the whole rest of the wave
    # is invisible.
    vmax = float(np.percentile(frames, 99.0)) or float(frames.max()) or 1.0

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    # imshow assumes a uniform grid, but SmoothMeshLines' spacing is not --
    # a cheap distortion trade for a much simpler/faster per-frame update
    # than pcolormesh's flattened-array bookkeeping. Fine for "briefly see
    # the wave move," not for reading off exact positions.
    im = ax.imshow(
        frames[0], origin="lower", cmap="inferno", vmin=0, vmax=vmax,
        extent=[x_mm.min(), x_mm.max(), y_mm.min(), y_mm.max()],
        aspect="equal", animated=True,
    )
    fig.colorbar(im, ax=ax, label="|E| (V/m, near-field-clipped scale)")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    title = ax.set_title("")

    if geometry_mm:
        bw, bl = geometry_mm["board_w"], geometry_mm["board_l"]
        ax.add_patch(plt.Rectangle((0, 0), bw, bl, fill=False,
                                    edgecolor="cyan", linewidth=1.2))
        sx, sy = geometry_mm["short_xy"]
        ox, oy = geometry_mm["open_xy"]
        fx, fy = geometry_mm["feed_xy"]
        ax.plot([sx, ox], [sy, oy], color="lime", linewidth=2, label="IFA arm")
        ax.plot(fx, fy, marker="o", color="white", markersize=5, label="feed")
        ax.legend(loc="upper right", fontsize=7, framealpha=0.5)

    def update(i):
        im.set_data(frames[i])
        title.set_text(f"timestep {timesteps[i]}")
        return im, title

    anim = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps)
    out_gif = out_gif or str(Path(sim_path) / "field_animation.gif")
    anim.save(out_gif, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return out_gif


def render_s11_plot(s11_curve: list[dict], band, out_png: str) -> str:
    """Quick S11-vs-frequency PNG from postprocess.postprocess()'s
    s11_curve, with the pass/fail threshold and target band marked."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    freqs_ghz = [p["f_ghz"] for p in s11_curve]
    s11_db = [p["s11_db"] for p in s11_curve]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(freqs_ghz, s11_db, marker="o", markersize=3)
    ax.axhline(band.s11_db_max, color="red", linestyle="--",
               label=f"S11 threshold ({band.s11_db_max} dB)")
    ax.axvspan(band.f_low_ghz, band.f_high_ghz, color="green", alpha=0.1,
               label=f"{band.id} band")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("S11 (dB)")
    ax.set_title("Return loss")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)
    return out_png
