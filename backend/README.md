# AI Antenna Engineer — backend

FastAPI backend that turns Devin into an RF engineer: it reads a phone build
file (`.blend`), proposes antenna placements, a solver simulates them,
evidence goes back, and the agent iterates until it judges the design good
enough. Architecture, contracts and decisions: [DESIGN.md](DESIGN.md).

## Run

```bash
uv sync
uv run uvicorn app.main:app --port 8000
```

Live agent needs `.env` (gitignored) with `DEVIN_API_KEY`, `DEVIN_ORG_ID`,
optional `DEVIN_MAX_ACU` / `DEVIN_MODE` / `DEVIN_REPO` (`owner/repo`; when
set, Devin clones it and uses the `blend-extract` skill — otherwise the
extraction script is inlined in the prompt). Without `.env`, pass
`"agent": "mock"`.

`.blend` extraction needs a **Python 3.11 + `bpy`** interpreter (the backend
itself is 3.12). Resolution order: `BPY_PYTHON=<python>`, `BLENDER=<blender>`
(headless), else an ephemeral `uv run --python 3.11 --with bpy` (first run
downloads ~220 MB). Outputs cache under `var/devices/`.

No-HTTP smoke tests:

```bash
uv run python scripts/dev_run.py                                           # canned spec, mock
BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
AGENT=devin BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
```

Synthetic fixture (until the real iPhone asset lands):
`uv run --no-project --python 3.11 --with bpy python ../tools/make_phone_blend.py --out ../data/phone_synth_v1`

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/devices` | multipart `blend` (+ optional `materials` sidecar, `wait=true`) → `{device_id, status, spec, anchors, ambiguities, size_mm, frame, artifacts}` |
| GET | `/devices/{id}` | same snapshot (poll when `wait=false`) |
| GET | `/devices/{id}/artifacts/{name}` | `device.glb` (viewer, canonical frame), `geometry.json`, `materials.json`, `parts/<node>.stl` |
| POST | `/runs` | `{"device_id"?: str, "prompt": str, "bands": ["wifi24"], "agent": "devin"\|"mock", "extract"?: "agent"\|"backend"}` → `{run_id}`; no `device_id` ⇒ canned spec |
| GET | `/runs/{id}` | snapshot: status, stage, spec, anchors, spec_source, ambiguities, candidates, results, final |
| WS | `/runs/{id}/events?since=N` | event stream; replays everything after seq N on (re)connect |
| GET | `/healthz` | liveness |

Bands: `lte_low gps_l1 wifi24 n78 wifi5` (mirror of the frontend catalogue).

Event envelope: `{run_id, seq, ts, stage, type, payload}` with `type` one of
`stage_started stage_progress agent_message candidates_proposed sim_started
sim_result iteration_scored decision artifact run_finished error`.
Stages: `extract` (agent reads the build file; `decision{spec accepted,
crosscheck, overrides}`), `spec` (`artifact{name: device_spec, spec, anchors,
ambiguities, source}`), `agent_loop`, `report`. `sim_result` payload is a
`SimResult`; `iteration_scored` carries the full evidence report
(diffs/trend/hints) the agent reasons over.

## Seams

- **Agent**: `app/agent/port.py` — Devin (`app/agent/devin.py`, default) or
  the offline mock. The orchestrator owns the workflow either way.
- **Simulation**: one callable, `solve(spec, band, candidate) -> SimResult`.
  Select with `SIM_SOLVER=module:function` (default: bundled reference
  oracle `app.sim.oracle:solve`). Sim team: implement the contract, point
  the env var at it, done. `spec.components[].role == "ground"` names the
  reference plane; `geometry.json` / `parts/*.stl` under the device dir are
  the full-fidelity geometry for an FDTD engine (same manifest shape as
  `rf/run_simulation.py:load_device`).
- **Geometry**: `tools/extract_blend.py` is the single extraction script
  (Devin and backend run the identical file); `app/geometry/classify.py` is
  the single place a `DeviceSpec` is assembled (heuristics + agent overrides).
- **Frontend**: `DeviceSpec`/`Anchor`/`Candidate`/`SimResult` mirror
  `frontend/src/lib/types.ts`; additive optional fields only (`role`,
  `em_source`, `region_pref`, `color`). The glb's node names equal
  `components[].name` and its coordinates equal `bbox_mm` (mm, no Y-up flip).
