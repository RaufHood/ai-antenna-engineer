# rf/ — EM simulation workstream

Determines whether an antenna placement candidate works, by actually
running an FDTD solve (openEMS) on an IFA-over-ground-plane geometry and
reporting S11 / resonance / bandwidth / gain / efficiency. One entry point:

```python
from rf import run_simulation
result = run_simulation(config)  # dict in -> dict out, see contract below
```

No server code lives here — a FastAPI backend (built separately) is meant
to import `run_simulation` directly. For the *why* behind every decision
below (antenna type, band, solver choice, bugs found and fixed, open
questions) see **`progress_simulation.md`** — this file is just the map.

## Quickstart

```sh
# from the repo root
rf/.venv/Scripts/python -m rf.run_simulation
```

Runs a demo GPS-L1 IFA candidate end-to-end (~2 min) and prints the
`SimResult` JSON. First time, set up the venvs per "Setup" below.

## Module layout

```
rf/
├── __init__.py         # `from rf import run_simulation`
├── models.py            # Candidate, Band, SimOptions, SimResult, FDTDStructure, IFA_* constants
├── device.py             # load_device() — reads blend_loader-produced device.json
├── geometry.py            # build_ifa_geometry() — CSXCAD/openEMS structure for one candidate
├── solve.py                # run_fdtd() — runs the solve, CalcPort over the band
├── postprocess.py           # postprocess() — port data -> SimResult metrics
├── visualize.py               # render_field_animation() / render_s11_plot() — human-facing, opt-in
├── run_simulation.py           # run_simulation() orchestrator + __main__ CLI demo
├── cli.py                       # python -m rf.cli --out result.json < config.json
│                                 # -- for callers on a different Python (e.g. the
│                                 # FastAPI backend); see backend/app/sim/rf_adapter.py
├── openems_env.py               # DLL-path setup openEMS/CSXCAD need on Windows before import
├── requirements.txt              # numpy/h5py/matplotlib/cython + vendored openEMS/CSXCAD wheels
├── vendor/                        # gitignored — vendored openEMS build (~150MB, see Setup)
├── .venv/                          # gitignored — openEMS venv
└── blend_loader/                    # separate tool + venv: .blend -> device.json (has bpy)
    ├── load_blend.py
    ├── requirements.txt              # bpy
    ├── .venv/                         # gitignored
    └── out/                            # generated device.json + STLs, gitignored
```

All modules use relative imports (`from .models import ...`), so invocation
is **always `python -m rf.<module>`**, never `python rf/<module>.py`.

## Setup

```sh
# openEMS venv
py -3.11 -m venv rf/.venv
mkdir -p rf/vendor
curl -L -o rf/vendor/openEMS_v0.0.36.zip \
  https://github.com/thliebig/openEMS-Project/releases/download/v0.0.36/openEMS_v0.0.36.zip
unzip -q -o rf/vendor/openEMS_v0.0.36.zip -d rf/vendor/
cd rf && .venv/Scripts/pip install -r requirements.txt   # cwd matters: wheel paths are relative to this file
cd .. && rf/.venv/Scripts/python -m rf.openems_env       # smoke test: imports CSXCAD + openEMS

# blend_loader venv (separate — needs bpy, not openEMS)
py -3.11 -m venv rf/blend_loader/.venv
rf/blend_loader/.venv/Scripts/pip install -r rf/blend_loader/requirements.txt
```

## Config / result contract

Mirrors `frontend/src/lib/types.ts` (snake_case), so a `run_simulation`
output can drop straight into `frontend/src/lib/runner.ts` in place of the
mock `simulate()`:

```jsonc
// in
{
  "candidate": {"candidate_id": "c001", "antenna_type": "IFA",
                "position_mm": [5,35,4], "feed_point_mm": [5,33,4],
                "length_mm": 26, "orientation": "edge"},
  "band": {"id": "gps_l1", "f_low_ghz": 1.565, "f_high_ghz": 1.585,
           "s11_db_max": -8, "efficiency_min": 0.45},
  "device": { ... },  // types.ts DeviceSpec; board/enclosure/components
  "sim": {"mesh_res": "coarse", "boundary": "MUR", "freq_points": 21,
          "dump_fields": false}  // see Visualizing below
}
```

```jsonc
// out — matches types.ts SimResult exactly
{
  "candidate_id": "c001", "status": "complete", "runtime_s": 240,
  "s11_curve": [{"f_ghz": 1.565, "s11_db": -3.1}, ...],
  "s11_min_db": -12.4, "resonant_ghz": 1.5754, "bandwidth_mhz": 18,
  "efficiency": 0.52, "peak_gain_dbi": 1.8, "vswr": 1.65,
  "sar_w_per_kg": 0.0, "meets_requirements": true, "notes": "..."
}
```

## Visualizing a run

`SimOptions.dump_fields=True` (off by default — adds solver overhead and
disk I/O) makes `geometry.py` write a time-domain E-field dump, and
`run_simulation()` renders it to a GIF, adding `field_animation_path` to
the result dict:

```python
config["sim"]["dump_fields"] = True
result = run_simulation(config)
result["field_animation_path"]  # GIF of |E| spreading out from the feed
```

`visualize.render_s11_plot(s11_curve, band, out_png)` turns any
`postprocess()` output into a return-loss PNG (threshold + target band
marked) — called separately, not gated by `dump_fields`, see the
`__main__` block in `run_simulation.py` for the usage pattern.

## Real device materials

If `config["device"]["manifest_path"]` (or an inline `device["parts"]`)
points at a `device.json` from `rf/blend_loader/load_blend.py`,
`geometry._add_device_materials()` adds one real CSXCAD dielectric/
lossy-metal material per distinct `material_key`, one box per part —
automatic, no `SimOptions` flag needed. It's a **bbox-only**
approximation (not the actual STL mesh shape — importing ~200 real part
meshes as polyhedra would blow the runtime budget) and has **no
collision-awareness** with the antenna itself (placement/keepout is on
the caller). Ran end-to-end against `data/apple_iphone_15_pro/` (191
parts) — see `progress_simulation.md` step 6 for the result and both
caveats in detail.

## Status

Pipeline runs end-to-end (geometry + real device materials → FDTD solve →
S11/VSWR/gain/efficiency → optional field GIF), but **the IFA is not yet
cross-checked against a known-good result** — resonance/dimensions are a
first guess, not tuned or validated. See `progress_simulation.md` →
"Steps" for exactly what's done, what bugs were found and fixed, and
what's still open (tutorial cross-check, PyNEC cross-check).

**Backend wiring: live-verified 2026-08-22.** `rf/cli.py` (stdin JSON in,
`--out <file>` JSON result — not stdout, since openEMS/CSXCAD write their own
progress logging straight to stdout) is a thin CLI wrapper over
`run_simulation()` for callers on a different Python (the FastAPI backend is
3.12; this package needs the 3.11 openEMS wheels in `rf/.venv`).
`backend/app/sim/rf_adapter.py` shells out to it via subprocess — confirmed
with a real coarse-mesh solve through the full backend `Candidate`/
`DeviceSpec` → `rf_adapter.solve()` → `rf.cli` → `run_simulation()` path,
returning `status: "complete"` with a real S11 curve. (The S11 numbers
themselves are still the untuned first-guess IFA above, not evidence of a
resonance fix — that's the separate, still-open item.)
