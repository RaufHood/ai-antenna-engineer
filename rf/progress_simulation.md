# Simulation workstream — progress & plan

Owner: RF/sim workstream. Consumed by: FastAPI backend (teammate), frontend
mock swap-out (`frontend/src/lib/runner.ts` / `rf.ts`), Devin agent loop later.

## Where we are

- **Oracle validated (as originally authored):** `rf/validate_dipole.py`
  reproduces the textbook half-wave dipole (R ~70-73 ohm at L ~0.47-0.48
  lambda) using PyNEC (NEC2, Method-of-Moments, wire-only, PEC ground/wires
  — **no bulk dielectrics**). `rf/bench_scaling.py` benchmarks a monopole
  fed against a wire-grid ground plane at 868 MHz and confirms MoM cost
  scales ~O(N^3) in segment count, i.e. grid density is the runtime knob.
  **PyNEC does not currently build in this environment** — see the PyNEC
  note below; these scripts are trusted from when they were authored
  (git log), not re-verified here yet.
- **First antenna type decided: IFA (Inverted-F Antenna).** For the GPS L1
  band (`gps_l1`, 1.559-1.610 GHz, see `frontend/src/lib/device.ts:168`),
  the frontend spec already lists preferred types
  `["IFA", "ceramic_chip", "patch_array"]` — IFA is first choice there too.
  Rationale: PCB-etched/planar, compact enough for a phone edge, doesn't
  need the height a PIFA wants, and (unlike ceramic chip / patch) is simple
  enough to hand-mesh in both PyNEC (wire model: short pin + feed pin +
  radiating arm, all straight segments) and openEMS (a thin PEC strip) —
  same geometry, two solvers, cheap cross-check.
- **First bandwidth decided: GPS L1 only, narrowed.** Target center
  1575.42 MHz. Sweep window **1565-1585 MHz (20 MHz)** for the first pass,
  not the full multi-constellation 1559-1610 MHz (51 MHz, which also spans
  GLONASS ~1602 MHz and would need a dual-resonance design). Narrower sweep
  = fewer frequency points per run = faster iteration while we're still
  validating the pipeline; widen back to the full band once a candidate
  geometry resonates in the right place.
- **Direction as of today (superseding a pure-PyNEC path):** the real
  Blender model will bring in bulk dielectrics (FR4 board, glass back,
  battery) that PyNEC/NEC2 cannot represent (metal/wire-only, no
  dielectrics). Per `deep_research_on_challenge.md` §2, **openEMS (FDTD)**
  is the solver that has to carry the real device geometry. PyNEC stays in
  the loop as a fast, already-working *sanity oracle* for the bare
  IFA-over-ground-plane case (no dielectrics) — if openEMS and PyNEC agree
  on resonance/impedance for that stripped-down case, we trust the openEMS
  setup before adding materials.
- **openEMS is installed.** No WSL/Docker needed after all — openEMS
  publishes prebuilt Windows (MSVC) wheels for CSXCAD + openEMS on its
  GitHub releases (not on PyPI). Fetched `openEMS_v0.0.36.zip` from
  [github.com/thliebig/openEMS-Project releases/tag/v0.0.36](https://github.com/thliebig/openEMS-Project/releases/tag/v0.0.36),
  vendored the extracted contents at `rf/vendor/openEMS/` (gitignored, ~150
  MB — re-fetch with the command in "Setup" below rather than committing
  it), and installed `CSXCAD-0.6.3-cp311-cp311-win_amd64.whl` +
  `openEMS-0.0.36-cp311-cp311-win_amd64.whl` into `rf/.venv` (Python 3.11,
  matches the wheels' ABI tag) alongside `numpy`/`h5py`/`matplotlib`/
  `cython`. `rf/openems_env.py` adds `rf/vendor/openEMS/` as a DLL search
  directory before import — required on Python 3.8+/Windows, which no
  longer searches PATH for an extension module's sibling DLLs. Verified:
  `rf/.venv/Scripts/python -m rf.openems_env` imports both modules cleanly.
- **Geometry-loading hand-off built and tested (step 6, early):**
  `rf/blend_loader/load_blend.py` (runs in `rf/blend_loader/.venv`, has
  `bpy`) opens a `.blend`, reads its `materials.json` sidecar, parses each
  part's `node_path`/`material_key`, pulls `eps_r`/`sigma_S_per_m` per
  part, flags the steel `mu_r` gap materials.json itself calls out,
  computes bbox_mm, and exports one STL per part to a `device.json`
  manifest. Ran against `data/bellota_hunting_axe_8133/` (a
  materials-schema test fixture, not phone geometry) — 3 parts loaded
  correctly. `rf/device.py`'s `load_device()` reads that `device.json` via
  `config.device.manifest_path`, plain JSON, no `bpy` import — keeps the
  bpy venv and the openEMS venv from ever needing to mix. (This folder was
  originally a top-level `backend/`; moved under `rf/` and renamed to
  `blend_loader` on 2026-08-22 to avoid clashing with "the backend"
  meaning the FastAPI service a teammate is building separately, and to
  keep the sim workstream's Python code in one place — see "Module
  layout" below.)
- **Real device materials are now in the FDTD solve (bbox-approximated).**
  `geometry._add_device_materials()` turns `device['parts']` into real
  CSXCAD dielectric/lossy-metal boxes — see step 6 below for the
  iPhone-model result and its two known limitations (bbox-only, no
  collision-awareness with the antenna).
- **PyNEC could not be installed in `rf/.venv`.** It has no prebuilt wheel
  (sdist only) and needs the MSVC C++ Build Tools; this machine has the
  VS2022 Build Tools installer shell but not the actual "Desktop
  development with C++" workload/toolset (`vswhere` finds no
  `VC.Tools.x86.x64` component, no `cl.exe`). Not a blocker — PyNEC's job
  was a one-time bare-geometry cross-check (step 4 below), not the primary
  solver. Install it later with `pip install PyNEC` once that VS workload
  is added, or cross-check on a machine that already has it.

## Goal for this stage

A single Python function:

```python
def run_simulation(config: dict) -> dict:
    ...  # returns a dict matching SimResult below
```

that a FastAPI endpoint can call directly (`from rf.run_simulation import
run_simulation`) — no server code lives in `rf/`. It must be swappable 1:1
for the mock `simulate()` in `frontend/src/lib/rf.ts:169`, which returns
the `SimResult` shape already wired through `runner.ts` into the UI.

**Config contract** (mirrors `frontend/src/lib/types.ts`, snake_case,
already the shared contract with the frontend/agent workstreams):

```jsonc
{
  "candidate": {              // types.ts Candidate
    "candidate_id": "c001",
    "antenna_type": "IFA",
    "position_mm": [5, 35, 4],
    "feed_point_mm": [5, 33, 4],
    "length_mm": 26,
    "orientation": "edge",
    "keepout_mm": [[0,0,0],[15,70,8]]
  },
  "band": {                   // types.ts BandRequirement subset
    "id": "gps_l1", "f_low_ghz": 1.565, "f_high_ghz": 1.585,
    "s11_db_max": -8, "efficiency_min": 0.45
  },
  "device": { ... },           // types.ts DeviceSpec — board/enclosure/components;
                                // components[].bbox_mm + em class drive geometry
                                // once the Blender export lands (Step 6)
  "sim": {                     // solver knobs, not in the frontend schema
    "mesh_res": "coarse",      // coarse|fine — coarse = fast first-pass
    "boundary": "MUR",         // MUR (fast) or PML_8 (accurate)
    "freq_points": 21
  }
}
```

**Result contract** — must equal `SimResult` in `types.ts:103` exactly
(same keys) so `runner.ts` doesn't need to change:

```jsonc
{
  "candidate_id": "c001", "status": "complete", "runtime_s": 240,
  "s11_curve": [{"f_ghz": 1.565, "s11_db": -3.1}, ...],
  "s11_min_db": -12.4, "resonant_ghz": 1.5754, "bandwidth_mhz": 18,
  "efficiency": 0.52, "peak_gain_dbi": 1.8, "vswr": 1.65,
  "sar_w_per_kg": 0.0, "meets_requirements": true, "notes": "..."
}
```

## Module layout

`rf/` was one file (`run_simulation.py`) through the first working version;
split on 2026-08-22 once it had three real classes of content mixed
together (data shapes, geometry construction, solver mechanics) plus a
sibling tool (`blend_loader/`) that a colleague is going to keep building
on:

```
rf/
├── __init__.py        # `from rf import run_simulation`
├── models.py           # Candidate, Band, SimOptions, SimResult, FDTDStructure, IFA_* constants
├── device.py            # load_device() — reads blend_loader-produced device.json
├── geometry.py           # build_ifa_geometry()
├── solve.py               # run_fdtd()
├── postprocess.py         # postprocess()
├── run_simulation.py      # run_simulation() orchestrator + __main__ CLI demo
├── openems_env.py         # unchanged — DLL-path setup
├── validate_dipole.py      # unchanged — PyNEC oracle
├── bench_scaling.py        # unchanged — PyNEC oracle
├── vendor/                 # unchanged, gitignored — vendored openEMS build
├── .venv/                  # unchanged, gitignored
└── blend_loader/            # moved from top-level backend/, renamed (see above)
    ├── __init__.py
    ├── load_blend.py
    ├── requirements.txt     # bpy
    ├── .venv/                # gitignored — separate bpy env, python -m rf.blend_loader.load_blend
    └── out/                  # generated device.json + STLs, gitignored
```

All sibling modules use plain relative imports (`from .models import ...`).
That means invocation is **always `python -m rf.<module>`**, never
`python rf/<module>.py` directly — the latter doesn't set up the package
context the relative imports need.

## Setup (done — reproducible)

```sh
# from repo root
py -3.11 -m venv rf/.venv

mkdir -p rf/vendor
curl -L -o rf/vendor/openEMS_v0.0.36.zip \
  https://github.com/thliebig/openEMS-Project/releases/download/v0.0.36/openEMS_v0.0.36.zip
unzip -q -o rf/vendor/openEMS_v0.0.36.zip -d rf/vendor/

cd rf && .venv/Scripts/pip install -r requirements.txt   # cwd matters: wheel
                                                           # paths in the file
                                                           # are relative to it
cd .. && rf/.venv/Scripts/python -m rf.openems_env        # smoke test

# blend_loader has its own venv (needs bpy, not openEMS)
py -3.11 -m venv rf/blend_loader/.venv
rf/blend_loader/.venv/Scripts/pip install -r rf/blend_loader/requirements.txt
```

## Steps

1. ~~Get openEMS installed and runnable.~~ **Done** — see Setup above.
   Verified `import openEMS, CSXCAD` via `rf/openems_env.py`.
2. **Run an unmodified openEMS tutorial** — still not done (skipped ahead
   to 3/5 instead; worth circling back to for an independent known-result
   check). Bundled at
   `rf/vendor/openEMS/python/Tutorials/Simple_Patch_Antenna.py` (there's
   also `Bent_Patch_Antenna.py` and `Helical_Antenna.py`, no bare-IFA
   tutorial, so Simple_Patch_Antenna is the closest match).
3. ~~Parametrize the tutorial into a geometry builder~~ **Done** —
   `build_ifa_geometry()` in `rf/geometry.py`: ground plane + short pin +
   radiating arm as CSXCAD PEC boxes, fed by an `AddLumpedPort`, no
   dielectrics yet. Geometry conventions (Candidate has no dedicated
   short-pin field) are documented as `IFA_*` constants in `rf/models.py`
   + inline comments in that function.
5. ~~Wrap end-to-end as `run_simulation(config) -> result dict`~~ **Done**
   — `rf/solve.py`'s `run_fdtd()` + `rf/postprocess.py`'s `postprocess()`
   also implemented (S11 curve, resonance,
   bandwidth, VSWR from `CalcPort`; gain/efficiency from `CalcNF2FF` vs.
   `port.P_acc`; SAR still stubbed `0.0`, no tissue phantom yet). **Ran
   end-to-end against the GPS-L1 demo candidate and it produced a complete
   result** — but getting it running surfaced three real bugs, now fixed,
   worth knowing about if this geometry gets extended:
   - The pin height (5 mm) and arm width (2 mm) are far smaller than the
     general lambda/N mesh (~19 mm coarse), so nothing bracketed them and
     the solver silently dropped the port (`Lumped Element snapping
     failed! Dimension is: 0` — *every* primitive logged "Unused"). Fixed
     with explicit `mesh.AddLine('z', [..., 0, h, ...])` plus
     `metal_edge_res` on every `AddEdges2Grid` call, mirroring the
     official tutorial's pattern for resolving sub-wavelength features.
   - The arm direction, first derived from an arbitrary feed/short offset,
     could point the arm straight off the board into free space for an
     edge-placed candidate. Fixed by deriving arm direction from the board
     geometry (short pin → board interior) instead.
   - The feed pin was offset *perpendicular* to the arm so its top end
     never touched the arm conductor — the port drove a stub connected to
     nothing (S11 flat at -0.05 dB, VSWR 314, across the whole band: total
     reflection, no coupling at all). Fixed by offsetting the feed *along*
     the arm axis instead, between the short pin and the open end.
   - **Current state after all three fixes:** the port now genuinely
     couples into the structure (VSWR dropped from 314 to ~24), but S11 is
     still only about -0.7 dB and monotonic across the narrow 1565-1585 MHz
     sweep — no resonance dip lands inside the window yet. That's a
     **tuning** problem (untuned first-guess dimensions), not a plumbing
     bug: nothing in the pipeline is known to be broken, but nothing has
     confirmed it's *right* either. Step 2 (tutorial cross-check) and step
     4 (PyNEC cross-check) are exactly the two remaining checks that would
     tell the difference — do those before trusting a specific resonance
     number.
4. **Cross-check against PyNEC.** Same IFA geometry (bare PEC, no
   dielectrics), same frequency, run through both solvers. Resonance and
   input resistance should be in the same ballpark. This is the
   openEMS-specific counterpart to step 2 and catches setup mistakes
   (units, mesh, port definition) that a lone tutorial re-run wouldn't.
   Blocked on the PyNEC/MSVC gap noted above.
6. ~~Swap in real materials from the Blender export~~ **Done, bbox-only.**
   `geometry._add_device_materials()` reads `device['parts']` (from
   `rf/blend_loader/load_blend.py`'s `device.json`) and adds one CSXCAD
   `AddMaterial` per distinct `material_key` (epsilon/kappa/mue from
   `eps_r`/`sigma_S_per_m`/`mu_r`), with one `AddBox` per part using its
   `bbox_mm`. Runs automatically whenever `device['parts']` is
   non-empty — no new `SimOptions` flag. Ran end-to-end against the real
   Apple iPhone 15 Pro asset (`data/apple_iphone_15_pro/`, 191 parts, 13
   material keys, antennas excluded per the asset's own brief) with the
   GPS-L1 IFA candidate resized to its real footprint (71.45 x 146.6mm,
   computed from the parts' own combined bbox): S11 shifted from -9.8dB
   (bare PEC ground plane) to -7.5dB once the real dielectrics/lossy
   metal were in the solve — evidence the materials are actually loading
   the antenna, not inert. Two things worth knowing:
   - **bbox-only, not real mesh shape.** The STLs `load_blend.py` exports
     per part aren't imported as polyhedra — 191 `AddPolyhedronReader`
     calls (500k+ triangles total) would blow the runtime budget step 7
     is meant to protect. Each part becomes one axis-aligned box with
     that material's `eps_r`/`sigma_S_per_m`/`mu_r`, coordinate-shifted so
     the parts' own bbox starts at `(0, 0, 0)` (a device manifest's
     coordinates are Blender-native/centred; the ground plane/antenna use
     a corner-anchored `[0, board_w] x [0, board_l]` frame).
   - **No collision-awareness.** Nothing checks whether a device part
     (e.g. the battery, the titanium frame) overlaps the antenna's own
     geometry at the chosen `candidate.position_mm` — that's on
     placement/`candidate.keepout_mm`, not this function. Also hit and
     fixed along the way: `load_blend.py` assumed the axe fixture's
     schema (`material_vocabulary_used` + a `parts` list) and silently
     returned `eps_r=None`/`sigma_S_per_m=None` for all 191 iPhone parts,
     whose `materials.json` nests the same fields differently
     (`materials: {key: {em_from_vocabulary: {...}}}`, no `parts` list —
     identity is name-only). Fixed to check both shapes; the axe fixture
     re-verified unaffected.
7. **Keep runtime bounded.** Expose `sim.mesh_res` and the band's frequency
   window as the two speed knobs (per `deep_research_on_challenge.md`
   Stage 2: keep each run under ~5-10 min). The narrowed GPS-L1-only
   bandwidth chosen above is exactly this lever applied to band selection.
8. **Hand off.** `run_simulation` ships as a pure function + a thin CLI
   (`python -m rf.run_simulation config.json`) so the FastAPI teammate can
   `import` it directly — no HTTP/server code needed from this workstream.

## Frontend (mock, reviewed today)

`frontend/` is a Next.js app, currently fully mocked, no backend calls yet:

- `src/lib/types.ts` — the shared contracts above (`DeviceSpec`,
  `BandRequirement`, `Candidate`, `SimResult`, `Job`). Treat as the source
  of truth for field names.
- `src/lib/device.ts` — hardcoded `phoneV1` device spec (board, enclosure,
  components, band list incl. `gps_l1`).
- `src/lib/rf.ts` — `generateCandidates()` and the **mock** `simulate()`
  (types.ts:169) that fabricates an `SimResult` from a heuristic score
  instead of an EM solver. This is exactly what `run_simulation` replaces.
- `src/lib/runner.ts` — in-memory run store; `resultFor()` is the single
  call site of `simulate()` — that's the seam where the FastAPI call goes
  in once it exists.
- `src/app/api/{device,run}/route.ts` — existing Next.js API routes (thin,
  currently just serve the mock); will likely proxy to the FastAPI service
  instead.
- `src/components/viewer/*` — Three.js phone viewer (candidates, keep-outs,
  isolation arcs, placement heatmap) — currently driven by `PhoneModel.tsx`
  placeholder geometry; `CustomModel.tsx` exists as the hook point for the
  real Blender glTF export.
- `src/components/panels/*` — S11 chart, results dock, spec/agent panels —
  all already consuming the `SimResult`/`Candidate` shape, so a correctly-
  shaped `run_simulation` output should "just work" once wired in.

## Next inputs needed

- Blender export (glTF for UI + per-part STL for sim) — step 6 blocks on
  this. `rf/blend_loader/load_blend.py` already does this end-to-end for a
  differently-shaped test asset (`data/bellota_hunting_axe_8133/`); it
  should need only the node_path/material_key naming convention to carry
  over, not a rewrite.
- VS2022 "Desktop development with C++" workload, if we want PyNEC (the
  cross-check oracle in step 4) working again on this machine — see the
  PyNEC note above. Not needed for openEMS itself.
