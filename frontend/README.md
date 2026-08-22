# Antenna Placement Studio

UI for the agent-driven antenna placement pipeline: load a handset model, set
per-band RF targets, ask the agent where the antennas should go, and inspect the
resulting placements, S11 sweeps and keep-out conflicts in 3D.

```bash
npm install
npm run dev     # http://localhost:3000
```

## What is real and what is a stand-in

Real today:

- The full UI: 3D viewer, exploded view, component labelling, keep-out volumes
  and their conflicts, per-band placement, isolation arcs, spectrum strip,
  ranked results table, engineering report.
- The async job pipeline. Candidates are queued server-side, results stream back
  as each "simulation" finishes, and state survives a page refresh because the
  run lives in the API route, not in React.
- The placement logic. Scores come from actual geometry: clearance to metal and
  lossy blocks, edge access, available chassis length against a quarter
  wavelength, and per-band region preference. Antennas are then assigned one per
  anchor, lowest band first, skipping anchors that would break the isolation
  target.

Stand-in, to be replaced:

- `src/lib/rf.ts` synthesises S11 from a single-resonator model instead of
  solving Maxwell's equations. Swap this for openEMS output.
- `src/lib/runner.ts` fakes elapsed simulation time. Swap the timing model for
  real job state from the solver / Devin session.

## Swapping in the real solver

Everything the solver touches is behind two functions:

| Replace | With |
|---|---|
| `simulate(spec, band, candidate)` in `src/lib/rf.ts` | parse `result.json` from an openEMS run |
| `jobStates()` / `resultFor()` in `src/lib/runner.ts` | real queue state and artifacts from the solver or the Devin session |

The UI reads only the `SimResult` shape, so as long as openEMS output is mapped
into that shape nothing else changes. `POST /api/run` already forwards the
user's edited constraints (keep-out, S11 target, efficiency floor, SAR standard)
as `overrides`, so the solver receives whatever the operator set in the panel.

## Contracts

`src/lib/types.ts` is the shared contract with the other workstreams. It mirrors
the JSON schemas in `../deep_research_on_challenge.md` §5.

For the 3D workstream:

- Units are millimetres, origin at the bottom-left-back corner of the device.
- Each Blender object must be a separate named node, and the name must match
  `components[].name` in the device spec (`pcb`, `ground_plane`, `battery`,
  `camera_module`, `frame`, `screen_glass`, `back_glass`, ...).
- Export glTF/GLB for the viewer and per-part STL for the solver.
- `Load Blender .glb` in the Device panel drops a real export into the viewer.
  The model is auto-centred and scaled to the spec height, so unit mismatches do
  not break candidate alignment.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/device` | device spec + candidate anchors |
| `POST` | `/api/run` | start a study: `{prompt, bands[], perBand?, overrides?}` |
| `GET` | `/api/run?runId=` | snapshot: jobs, results, placements, isolation, agent messages |

## Screenshots

`node scripts/shot.mjs` drives a headless browser through a full run and writes
PNGs to `shots/`. Useful for the demo video and for checking the 3D view without
opening a browser.
