# rf/ — EM simulation, placement screening and media

Decides whether an antenna placement works, by running a real FDTD solve
(openEMS) on the actual device geometry, and turns the result into figures
and animations you can put on a slide.

```python
from rf import run_simulation
result = run_simulation(config, out_dir="runs/my_run")   # dict in -> dict out
```

No server code lives here — a FastAPI backend imports `run_simulation`
directly. For the *why* behind every decision (antenna type, band, solver
choice, bugs found and fixed, what is still open) see
**`progress_simulation.md`**; this file is the map.

## Module layout

```
rf/
├── run_simulation.py     run_simulation(config, out_dir=None) — the one entry point
├── models.py             Candidate / Band / SimOptions / SimResult / FDTDStructure
├── device.py             load_device() — reads a blend_loader device.json
├── geometry.py           build_ifa_geometry() — CSXCAD structure + device materials
├── solve.py              run_fdtd() — runs the solve, CalcPort over the band
├── postprocess.py        port data -> SimResult metrics
├── placement.py          legality / clearance / escape screening (no solver, ~1 ms)
├── openems_env.py        Windows DLL-path setup; a no-op elsewhere
├── blend_loader/         .blend -> device.json + STLs (separate venv, needs bpy)
└── viz/                  the media suite (separate venv, no solver needed)
    ├── theme.py              dark + Computer Modern palette; import this, never hardcode
    ├── data.py               load_run() / synth_demo_run() — the run-artifact seam
    ├── s11.py                hero frequency-response figure
    ├── placement3d.py        technical 3D x-ray: bboxes, coordinate frame, dimensions
    ├── blender_render.py     beauty x-ray from the real .blend (bpy venv)
    ├── anim_field.py         |E| propagating through the device
    ├── anim_orbit.py         technical scene orbiting
    ├── anim_orbit_beauty.py  assembles Blender orbit frames -> gif + mp4
    ├── anim_dashboard.py     animated technical briefing card
    ├── heatmap.py            placement legality / score map
    ├── output.py             one animation writer: gif + even-dimension mp4
    └── __main__.py           `python -m rf.viz <run>` renders everything
```

Modules use relative imports, so invocation is always `python -m rf.<module>`,
never `python rf/<module>.py`.

## Three environments, on purpose

They cannot be merged: `bpy` and the openEMS bindings pin different Python
versions, and the media suite must run on a machine with no solver at all.

| env | what it has | used by |
|---|---|---|
| solver | openEMS + CSXCAD | `run_simulation` and everything under it |
| `.venv-viz` | matplotlib, numpy, h5py, pillow | all of `rf/viz` except `blender_render` |
| `bpy` env | bpy | `blend_loader`, `viz/blender_render` |

### Solver — macOS (Apple Silicon)

```sh
brew install cmake boost hdf5 vtk cgal qt@5      # NOT tinyxml: the formula is
                                                  # gone and an unknown formula
                                                  # aborts the whole install
git clone --recursive https://github.com/thliebig/openEMS-Project.git
cd openEMS-Project
export CMAKE_PREFIX_PATH="$(brew --prefix qt@5):$(brew --prefix vtk):$(brew --prefix hdf5)"
./update_openEMS.sh ~/opt/openEMS --python --disable-GUI   # --disable-GUI is
                                                            # required: QCSXCAD
                                                            # is not needed
                                                            # headless and its
                                                            # configure failure
                                                            # kills the build
```

Verified against the bundled tutorial: `Simple_Patch_Antenna.py` gives
2.4300 GHz / -27.7 dB vs. the documented ~2.40 GHz deep dip. A coarse
GPS-L1 demo solves in about 1 s (48 MCells/s).

### Solver — Windows

Prebuilt MSVC wheels, vendored: see `progress_simulation.md` "Setup".

### Media + screening

```sh
python3 -m venv .venv-viz
.venv-viz/bin/pip install matplotlib numpy h5py pillow scipy
```

### bpy

```sh
micromamba create -y -n bpy -c conda-forge python=3.11 pip
micromamba run -n bpy pip install bpy pillow
```

## Quickstart

```sh
# 1. device geometry: .blend -> device.json (+ one STL per part)
<bpy python> -m rf.blend_loader.load_blend \
    data/apple_iphone_15_pro/apple_iphone_15_pro.blend \
    --materials data/apple_iphone_15_pro/materials.json \
    --out rf/blend_loader/out

# 2. screen placements — no solver, ~1 ms per candidate
.venv-viz/bin/python -m rf.placement

# 3. solve one candidate, persisting artifacts for the media suite
<solver python> -m rf.run_simulation           # writes runs/<candidate_id>/

# 4. beauty renders from the real .blend (stills + orbit frames + overlay)
<bpy python> -m rf.viz.blender_render \
    data/apple_iphone_15_pro/apple_iphone_15_pro.blend \
    runs/demo/config.json runs/demo/media all 60 1000

# 5. every figure and animation for that run
.venv-viz/bin/python -m rf.viz runs/demo
```

Step 5 with no solver anywhere: `python -m rf.viz.data` fabricates
`runs/demo` (clearly watermarked DEMO) so the whole media pipeline can be
built and previewed on any machine.

## Run directory layout

The seam between the solve and everything downstream:

```
runs/<id>/
├── config.json     the config that produced it
├── result.json     SimResult
├── device.json     the manifest used (optional)
├── Et.h5           time-domain E-field dump (gitignored — tens of MB)
└── media/          every figure and animation
```

`orbit_frames/` is gitignored too: they are build intermediates, the
gif/mp4 carry the same content, and step 4 regenerates them.

## Gotchas worth knowing before you touch this

- **`FDTD.Run()` hijacks the process cwd** into a temp directory it then
  deletes. Resolve every output path to absolute *before* the solve.
- **NEC forms junctions only at segment endpoints.** A ground plane built
  from long crossing wires makes `geometry_complete()` raise a bare
  `RuntimeError: Unknown exception`. Build it edge by edge between nodes.
- **Cycles' default `transparent_max_bounces` (8)** terminates rays inside a
  device this layered, and the x-ray interior comes out black. It is 64.
- **Blender writes PNG row 0 at the top**, so the orthographic overlay is
  drawn `origin="upper"` over data drawn `origin="lower"`, or it comes out
  mirrored about the device centre.
- **`film_transparent` needs `image_settings.color_mode = "RGBA"`.** Blender
  defaults to RGB and silently drops alpha, shipping an opaque overlay that
  hides whatever it covers.
- **H.264/yuv420p needs even pixel dimensions** and fails *silently* on odd
  ones, leaving a 0-byte mp4 next to a healthy gif. `viz/output.py` pads.
