"""Run-artifact access for rf/viz — the seam that decouples visuals from the solver.

Every renderer in rf/viz consumes a *run directory*:

    runs/<run_id>/
    ├── result.json     # SimResult dict (the run_simulation contract)
    ├── config.json     # the config dict that produced it (candidate/band/device/sim)
    ├── device.json     # blend_loader manifest (parts w/ bbox_mm + materials) — optional
    └── Et.h5           # openEMS time-domain E-field dump — optional

Renderers never call the solver. On a machine with openEMS, run_simulation
writes these artifacts; on any other machine, `synth_demo_run()` fabricates
a physically-plausible stand-in (clearly labelled DEMO in result.notes) so
the whole media pipeline can be built and previewed anywhere.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np


def load_run(run_dir: str | Path) -> dict:
    """-> {result, config, candidate, band, device(|None), field_h5(|None)}"""
    run_dir = Path(run_dir)
    result = json.loads((run_dir / "result.json").read_text())
    config = json.loads((run_dir / "config.json").read_text())
    device = None
    dev_path = run_dir / "device.json"
    if dev_path.exists():
        device = json.loads(dev_path.read_text())
    h5 = run_dir / "Et.h5"
    return {
        "run_dir": run_dir,
        "result": result,
        "config": config,
        "candidate": config["candidate"],
        "band": config["band"],
        "device": device,
        "field_h5": h5 if h5.exists() else None,
    }


# ------------------------------------------------------------------ demo run

BOARD_W, BOARD_L = 71.45, 146.6          # real iPhone 15 Pro footprint (mm)

def _demo_device() -> dict:
    """Plausible iPhone-15-Pro-shaped part list (bbox_mm, Blender-centred
    coords like blend_loader emits). Superseded by the real device.json."""
    def part(name, key, x0, y0, z0, x1, y1, z1, eps, sig):
        return {"name": name, "material_key": key,
                "bbox_mm": [[x0, y0, z0], [x1, y1, z1]],
                "eps_r": eps, "sigma_S_per_m": sig}
    W, L, T = BOARD_W, BOARD_L, 8.25
    x0, y0, z0 = -W / 2, -L / 2, -T / 2
    return {"source": "DEMO synth (viz/data.py) — replace with blend_loader output",
            "parts": [
        part("frame_rail_left",  "titanium", x0, y0, z0, x0 + 3, y0 + L, z0 + T, 1.0, 2.4e6),
        part("frame_rail_right", "titanium", x0 + W - 3, y0, z0, x0 + W, y0 + L, z0 + T, 1.0, 2.4e6),
        part("frame_rail_top",   "titanium", x0, y0 + L - 3, z0, x0 + W, y0 + L, z0 + T, 1.0, 2.4e6),
        part("frame_rail_bottom","titanium", x0, y0, z0, x0 + W, y0 + 3, z0 + T, 1.0, 2.4e6),
        part("display_stack", "glass", x0 + 2, y0 + 2, z0 + T - 1.2, x0 + W - 2, y0 + L - 2, z0 + T, 6.7, 1e-12),
        part("back_glass",    "glass", x0 + 2, y0 + 2, z0, x0 + W - 2, y0 + L - 2, z0 + 0.8, 6.7, 1e-12),
        part("battery", "battery_lithium", x0 + 8, y0 + 34, z0 + 1.5, x0 + W - 20, y0 + 104, z0 + 6.0, 20.0, 0.3),
        part("logic_board", "fr4", x0 + W - 19, y0 + 40, z0 + 1.5, x0 + W - 6, y0 + 118, z0 + 4.5, 4.4, 0.02),
        part("camera_module", "aluminium", x0 + 6, y0 + 108, z0 + 1.0, x0 + 34, y0 + 138, z0 + 7.5, 1.0, 3.5e7),
        part("taptic_engine", "steel", x0 + 8, y0 + 8, z0 + 2.0, x0 + 30, y0 + 26, z0 + 6.0, 1.0, 1.4e6),
        part("speaker_box", "abs", x0 + 34, y0 + 6, z0 + 2.0, x0 + W - 8, y0 + 24, z0 + 6.5, 2.9, 0.005),
        part("midframe_shield", "aluminium", x0 + 5, y0 + 30, z0 + 4.6, x0 + W - 5, y0 + 120, z0 + 5.0, 1.0, 3.5e7),
    ]}


def synth_demo_run(out_dir: str | Path = "runs/demo", *, with_field: bool = True,
                   n_freq: int = 81) -> Path:
    """Fabricates a complete, physically-plausible run for building visuals.

    S11: single series-RLC-style resonance placed just above band centre
    (a *nearly*-tuned candidate: more interesting than a perfect one).
    Field dump: outgoing damped cylindrical wave from the feed over the
    board plane, mimicking openEMS's /FieldData/TD + /Mesh HDF5 layout.
    """
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    f_lo, f_hi = 1.565, 1.585
    f0, q, s11_floor_db = 1.5779, 62.0, -16.8      # resonance slightly high of centre
    f = np.linspace(f_lo - 0.012, f_hi + 0.012, n_freq)
    # reflection magnitude of a resonator matched to |Γ|=10^(floor/20) at f0
    gamma_min = 10 ** (s11_floor_db / 20)
    x = q * (f / f0 - f0 / f)
    gamma = np.sqrt((gamma_min ** 2 + x ** 2) / (1 + x ** 2))
    s11_db = 20 * np.log10(gamma)
    curve = [{"f_ghz": round(float(fi), 6), "s11_db": round(float(si), 3)}
             for fi, si in zip(f, s11_db)]

    in_band = (f >= f_lo) & (f <= f_hi)
    s11_min_in_band = float(s11_db[in_band].min())
    res_ghz = float(f[np.argmin(s11_db)])
    below = f[(s11_db <= -8.0)]
    bw_mhz = float((below.max() - below.min()) * 1e3) if below.size else 0.0
    vswr = float((1 + gamma[in_band].min()) / (1 - gamma[in_band].min()))
    efficiency = 0.512
    meets = s11_min_in_band <= -8.0 and efficiency >= 0.45

    candidate = {"candidate_id": "demo-c003", "antenna_type": "IFA",
                 "position_mm": [4.0, 118.0, 4.0], "feed_point_mm": [4.0, 115.0, 4.0],
                 "length_mm": 27.5, "orientation": "edge",
                 "keepout_mm": [[0.0, 100.0, 0.0], [16.0, 146.6, 8.25]]}
    band = {"id": "gps_l1", "f_low_ghz": f_lo, "f_high_ghz": f_hi,
            "s11_db_max": -8.0, "efficiency_min": 0.45}
    config = {"candidate": candidate, "band": band,
              "device": {"manifest": "device.json"},
              "sim": {"mesh_res": "coarse", "boundary": "MUR", "freq_points": n_freq}}
    result = {"candidate_id": candidate["candidate_id"], "status": "complete",
              "runtime_s": 142.7, "s11_curve": curve,
              "s11_min_db": round(s11_min_in_band, 2),
              "resonant_ghz": round(res_ghz, 4), "bandwidth_mhz": round(bw_mhz, 1),
              "efficiency": efficiency, "peak_gain_dbi": 2.1,
              "vswr": round(vswr, 2), "sar_w_per_kg": 0.0,
              "meets_requirements": bool(meets),
              "notes": "DEMO artifact synthesized by rf/viz/data.py — not a solver result"}

    (out / "config.json").write_text(json.dumps(config, indent=2))
    (out / "result.json").write_text(json.dumps(result, indent=2))
    (out / "device.json").write_text(json.dumps(_demo_device(), indent=2))

    if with_field:
        import h5py
        nx, ny, nz, nt = 141, 261, 1, 72
        x_m = np.linspace(-0.015, BOARD_W / 1e3 + 0.015, nx)
        y_m = np.linspace(-0.015, BOARD_L / 1e3 + 0.015, ny)
        z_m = np.array([0.004])
        fx, fy = candidate["feed_point_mm"][0] / 1e3, candidate["feed_point_mm"][1] / 1e3
        X, Y = np.meshgrid(x_m, y_m)                      # (ny, nx)
        R = np.hypot(X - fx, Y - fy)
        lam = 0.19; v = 1.0
        with h5py.File(out / "Et.h5", "w") as h5:
            h5["Mesh/x"], h5["Mesh/y"], h5["Mesh/z"] = x_m, y_m, z_m
            g = h5.create_group("FieldData/TD")
            for it in range(nt):
                t = it / nt * 2.2                          # wavefront sweeps board twice
                phase = 2 * math.pi * (R / lam - 3.2 * t)
                env = np.exp(-((R - v * t * 0.16) ** 2) / (2 * 0.018 ** 2))
                standing = 0.35 * np.exp(-R / 0.02) * abs(math.sin(2 * math.pi * 3.2 * t))
                mag = (env * np.cos(phase) ** 2 + standing) / (R * 25 + 1.0)
                arr = np.zeros((3, nz, ny, nx), dtype=np.float32)
                arr[2, 0] = mag.astype(np.float32)
                g.create_dataset(f"{it * 60:08d}", data=arr)
    return out


if __name__ == "__main__":
    p = synth_demo_run()
    print(f"demo run -> {p.resolve()}")
