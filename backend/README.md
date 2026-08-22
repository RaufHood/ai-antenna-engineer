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

Likewise, running the real sim engine (`SIM_SOLVER=app.sim.rf_adapter:solve`)
needs the sim team's **Python 3.11 + openEMS/CSXCAD** venv at `rf/.venv`
(Windows-only prebuilt wheels — see `rf/README.md` Setup). Auto-detected at
`rf/.venv/Scripts/python.exe` (or `rf/.venv/bin/python`); override with
`RF_PYTHON=<python>` if it lives elsewhere. `RF_TIMEOUT_S` (default 600)
bounds each subprocess call — FDTD solves run minutes, not milliseconds.

Offline self-test (no Devin, no bpy, ~10 s): `uv run python scripts/selftest.py`

No-HTTP smoke tests:

```bash
uv run python scripts/dev_run.py                                           # canned spec, mock
BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
AGENT=devin BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
```

Assets: the real iPhone 15 Pro `.blend` + `materials.json` lives on branch
`feat/simulation` under `data/apple_iphone_15_pro/` (verified end to end);
`data/phone_synth_v1/` is a synthetic 15-part fixture, regenerable with
`uv run --no-project --python 3.11 --with bpy python ../tools/make_phone_blend.py --out ../data/phone_synth_v1`.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/devices` | multipart `blend` (+ optional `materials` sidecar, `wait=true`) → `{device_id, status, spec, anchors, ambiguities, size_mm, frame, artifacts}` |
| GET | `/devices/{id}` | same snapshot (poll when `wait=false`) |
| GET | `/devices/{id}/artifacts/{name}` | `device.glb` (viewer, canonical frame), `geometry.json`, `materials.json`, `parts/<node>.stl` |
| POST | `/runs` | `{"device_id"?: str, "prompt": str, "bands": ["wifi24"], "agent": "devin"\|"mock", "extract"?: "agent"\|"backend"}` → `{run_id}`; no `device_id` ⇒ canned spec |
| GET | `/runs` | list runs |
| GET | `/runs/{id}` | snapshot: status, stage, spec, anchors, spec_source, ambiguities, candidates, results, final (incl. `agent_report`), artifacts |
| POST | `/runs/{id}/messages` | `{"text": str}` — mid-run user feedback; delivered with the agent's next evidence message, echoed as `agent_message{role: user}` |
| GET | `/runs/{id}/artifacts/{name}` | `report.md`, `run.json`, `s11_<candidate_id>.csv` |
| WS | `/runs/{id}/events?since=N` | event stream; replays everything after seq N on (re)connect |
| GET | `/healthz` | liveness |

Bands: `lte_low gps_l1 wifi24 n78 wifi5` (mirror of the frontend catalogue).

Event envelope: `{run_id, seq, ts, stage, type, payload}` with `type` one of
`stage_started stage_progress agent_message candidates_proposed sim_started
sim_result iteration_scored decision artifact run_finished error`.
Stages: `extract` (agent reads the build file; `decision{spec accepted,
crosscheck, overrides}`), `spec` (`artifact{name: device_spec, spec, anchors,
ambiguities, source}`), `agent_loop`, `report` (`run_finished{ranking, best,
best_candidate, rationale, truncated}` then `artifact{name: agent_report}` and
`artifact{name: report.md, url}` as addenda). `sim_result` payload is a
`SimResult`; `iteration_scored` carries the full evidence report
(diffs/trend/hints) the agent reasons over.

## Seams

- **Agent**: `app/agent/port.py` — Devin (`app/agent/devin.py`, default) or
  the offline mock. The orchestrator owns the workflow either way.
- **Simulation**: one callable, `solve(spec, band, candidate) -> SimResult`,
  selected with `SIM_SOLVER=module:function` (default: bundled reference
  oracle `app.sim.oracle:solve`). **Sim team:** your `rf.run_simulation(config)`
  is wired and **live-verified against the real openEMS solver**
  (2026-08-22) — start the backend with
  `SIM_SOLVER=app.sim.rf_adapter:solve` (optional `SIM_OPTS='{"mesh_res":
  "coarse","freq_points":21}'`, `MAX_BATCH=8` to cap candidates per agent
  turn); `app/sim/rf_adapter.py` is the only file that knows your
  config/result shape. `config.device.manifest_path` points at the
  device's `geometry.json` (your `device.json` manifest shape, plus
  `parts/*.stl`); `spec.components[].role == "ground"` names the reference
  plane. Expect minutes per solve with FDTD — batch sizes in the agent
  protocol should shrink accordingly.
  Cross-venv note: openEMS/CSXCAD are Python-3.11-only wheels in `rf/.venv`;
  this backend is Python 3.12, so `rf_adapter.solve()` shells out to
  `rf/.venv`'s interpreter (`RF_PYTHON` to override, else auto-detected)
  running `rf/cli.py`, the same subprocess pattern `app/geometry/extract.py`
  uses for `bpy`. Result comes back via a `--out <file>` handoff, not
  stdout — openEMS's C++ engine writes its own progress logging straight to
  stdout, confirmed live, so a JSON result can't share that stream reliably.
  `RF_TIMEOUT_S` (default 600s) bounds the subprocess. Live coarse-mesh run
  confirmed end-to-end (`status: "complete"`, real S11 curve back through
  the full backend `Candidate`/`DeviceSpec` shapes) — see
  `AGENT_SIM_INTEGRATION_PLAN.md` for the verification steps and what's
  still open (a two-tier fast-search/real-solver-confirmation strategy for
  when the agent loop runs against this instead of the fast oracle).
- **Geometry**: `tools/extract_blend.py` is the single extraction script
  (Devin and backend run the identical file); `app/geometry/classify.py` is
  the single place a `DeviceSpec` is assembled (heuristics + agent overrides).
- **Frontend**: `DeviceSpec`/`Anchor`/`Candidate`/`SimResult` mirror
  `frontend/src/lib/types.ts`; additive optional fields only (`role`,
  `em_source`, `region_pref`, `color`). The glb's node names equal
  `components[].name` and its coordinates equal `bbox_mm` (mm, no Y-up flip).
