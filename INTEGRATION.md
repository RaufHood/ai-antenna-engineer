# Integration guide — the seams

How the three workstreams plug into each other, and what each can rely on.
Deep detail lives in [backend/DESIGN.md](backend/DESIGN.md) (architecture,
ADRs) and [backend/README.md](backend/README.md) (API reference); how to run
the thing is in the [README](README.md).

## The system in one picture

```
 .blend + prompt                                        Devin API (v3)
       │                                                      ▲
       ▼                                                      │ session + messages
┌──────────────────┐   REST + WS   ┌───────────────────────────────┐
│ Frontend         │◄─────────────►│ Backend (FastAPI)             │
│ Next.js + three  │  events/steps │  orchestrator = THE LOOP      │
└──────────────────┘               │  Devin proposes → sim scores  │
                                   │  → evidence back → iterate    │
                                   └───────────────┬───────────────┘
                                                   │ solve(spec, band, candidate)
                                                   ▼
                                  PyNEC (default)  ·  rf/ openEMS (SIM_SOLVER)
```

**Who owns what.** Devin owns engineering judgment (where/what antenna, is it
good enough). The backend owns the loop, the scoring and the event stream.
The sim workstream owns the physics. The frontend owns the display. Nobody
reaches across a seam except through the two contracts below.

**One run, end to end:** upload `.blend` → `tools/extract_blend.py` produces
`geometry.json` + `device.glb` + per-part STLs → `classify.py` turns that into
a `DeviceSpec` → Devin reads the build file itself and returns its own
classification → design loop (propose → simulate batch → evidence → refine)
→ `done` (rejected unless the recommended design has a simulation on record)
→ `report.md`.

---

## Simulation team — how you plug in

The backend calls **exactly one callable**, in a process pool:

```python
solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> SimResult
```

Your `rf.run_simulation(config) -> dict` is **already wired** through
`backend/app/sim/rf_adapter.py`. Nothing on your side needs to change:

```bash
cd backend
SIM_SOLVER=app.sim.rf_adapter:solve uv run uvicorn app.main:app --port 8000
```

Optional env: `SIM_OPTS='{"mesh_res":"coarse","freq_points":21}'` (passed
through as `config["sim"]`), `MAX_BATCH=8` (candidates per agent turn — the
default 40 assumes the millisecond reference solver; FDTD needs a small
number).

This is the **optional** slow path: the default solver is PyNEC in-process
(milliseconds), and `SIM_SOLVER` unset keeps it that way. Without openEMS the
adapter surfaces one `failed` candidate naming the missing module, never a
crashed run. A second, cheaper hook: `CONFIRM_SOLVER` re-solves only the
agent's chosen winner with the real solver after `run_finished`, as an
addendum artifact.

Your placement screening (`rf/placement.py`) is also wired, solver-free, via
`backend/app/sim/priors.py`: the agent is told which anchors intersect real
parts before it proposes. It reads the manifest at
`rf/blend_loader/out/device.json`, which is therefore **tracked** (the STLs
beside it are not) — `python -m app.sim.priors` must say `5 legal, 15 ruled
out`; "screening unavailable" means that file is missing.

What the adapter sends you:

| config key | what it is |
|---|---|
| `candidate` | types.ts `Candidate` fields only — your dataclass rejects extras. Our `params.height_mm` is mapped onto `feed_point_mm[2]`, since that is where your IFA reads pin height. |
| `band` | `id, f_low_ghz, f_high_ghz, s11_db_max, efficiency_min` |
| `device.manifest_path` | the device's `geometry.json` — same manifest shape your `blend_loader` writes (`parts[].{node_path, material_key, eps_r, sigma_S_per_m, bbox_mm, stl_path}`), plus `parts/*.stl` beside it. This is the real per-part geometry for step 6. |
| `device.board.size_mm` | device outline (W, H, T) in mm |
| `device.components` | our classified list; `role == "ground"` names the reference plane |
| `sim` | whatever you put in `SIM_OPTS` |

Back from you we read the `SimResult` keys you already return. Two notes:
you report no input impedance, so ours stays `(0,0)` and the scorer simply
skips the impedance hints (resonance/bandwidth/clearance hints still work);
and `runtime_s` is used as-is.

**Two things worth fixing on your side** (neither blocks us):

1. `rf/__init__.py` does `from .run_simulation import run_simulation`, which
   shadows the submodule: `import rf.run_simulation as rs` returns the
   *function*, not the module. `from rf.run_simulation import run_simulation`
   (what the adapter uses) is fine. Renaming the function or dropping the
   re-export avoids a confusing footgun.
2. `rf/blend_loader/load_blend.py` duplicates `tools/extract_blend.py`, which
   already writes your manifest shape *plus* the STLs, the glb for the
   viewer, and unit/axis normalisation. Suggest deleting yours and calling
   ours — one extraction path, no drift.

To test without the backend: `run_simulation(config)` with a config shaped
like the table above. To test the *seam* without openEMS, see
`backend/scripts/selftest.py`, which stubs your function.

---

## Frontend — how it is plugged in

The browser never talks to port 8000. Next.js route handlers do, and
`frontend/src/lib/backend.ts` maps the backend's shapes onto the
`RunSnapshot` the store and every panel consume:

| UI route | backend | notes |
|---|---|---|
| `POST /api/run` | `POST /runs` | `{prompt, bands, agent, deviceId}`; a backend error (no Devin credentials, unknown device, bad band) is returned as that error, a backend that is down as 503. No local stand-in. |
| `GET /api/run?runId=` | `GET /runs/{id}` + `GET /runs/{id}/log` | snapshot + event log → jobs, results, candidates (with `keepout_mm` derived from the band's clearance), messages, one placement per band (the agent's ranking, or best-so-far while running), anchors |
| `GET /api/run?runId=&artifact=report.md` | `GET /runs/{id}/artifacts/report.md` | the agent's report, shown in the Report tab |
| `PATCH /api/run` | `POST /runs/{id}/messages` | mid-run note to the agent |
| `DELETE /api/run?runId=` | `POST /runs/{id}/stop` | Stop: cancels the loop and terminates the agent session, so a live Devin stops reasoning and stops spending. The run comes back `stopped`, never presented as a conclusion |
| `POST /api/device` | `POST /devices` | `.blend` (+ `materials.json`) passthrough; reply has the backend's spec + anchors and a same-origin `glbUrl` for the viewer |
| `GET /api/device?id=&artifact=` | `GET /devices/{id}/artifacts/{name}` | streamed |

`BACKEND_URL` and `AGENT` in `frontend/.env.local` (see `.env.example`).
The `Mock`/`Devin` toggle picks the agent per run. Band targets are shown
read-only — they are the backend's catalogue, and `POST /runs` takes only
band ids. SAR and inter-antenna isolation are not modelled by the solver and
are therefore not on screen.

The canned device on both sides is **Handset A** — `backend/app/geometry/spec.py`
mirrors `frontend/src/lib/device.ts` box for box (ADR-8), so candidates the
backend proposes land where the procedural viewer draws the battery, camera
and speaker; `device.ts` also ports `make_anchors` so the anchor dots shown
before a run are the set the agent picks from. Change both files together.
An uploaded `.blend` replaces it with the backend's spec and `device.glb`.

Below is the raw contract, for anyone driving the backend directly. Types
already match `frontend/src/lib/types.ts`; the backend adds only **optional**
fields (`role`, `em_source` on components; `region_pref`, `color` on bands).

**1. Upload a device** (multipart; `materials` sidecar optional):

```bash
curl -F blend=@data/apple_iphone_15_pro/apple_iphone_15_pro.blend \
     -F materials=@data/apple_iphone_15_pro/materials.json \
     localhost:8000/devices
```

Returns `{device_id, status, spec, anchors, ambiguities, size_mm, frame, artifacts}`.
Load the 3D model from `GET /devices/{id}/artifacts/device.glb` — **its node
names equal `spec.components[].name` and its coordinates equal `bbox_mm`**
(millimetres, origin bottom-left-back, no Y-up flip), so `CustomModel.tsx`
can align highlights with spec parts directly, no fitting heuristic needed.

**2. Start a run:**

```bash
curl -X POST -H 'content-type: application/json' \
  -d '{"device_id":"dev_...","bands":["wifi24"],"agent":"devin","prompt":"Integrate a 2.4 GHz antenna"}' \
  localhost:8000/runs
```

`"agent":"mock"` runs the offline heuristic agent — **use this while
developing the UI**: no Devin key needed, finishes in seconds, emits exactly
the same events, and designs for every requested band (lowest frequency gets
the clearest anchors). Bands: `lte_low gps_l1 wifi24 n78 wifi5`; without a
`device_id` the run is on Handset A.

**3. Subscribe:** `ws://localhost:8000/runs/{id}/events?since={lastSeq}`,
or poll the same log over REST: `GET /runs/{id}/log?since={lastSeq}`.
Every event is `{run_id, seq, ts, stage, type, payload}` with a contiguous
`seq`; reconnect with `?since=` and you miss nothing. A real sequence:

```
spec        stage_started       {stage}
spec        artifact            {name:"device_spec", source, spec, anchors, ambiguities}
agent_loop  stage_started       {stage}
agent_loop  agent_message       {role:"agent"|"user", text}      ← live commentary
agent_loop  candidates_proposed {iteration, candidates[], sweep?}
agent_loop  sim_started         {candidate_id, band_id}          ← ×N
agent_loop  sim_result          {…SimResult}                     ← ×N, draw as they land
agent_loop  iteration_scored    {iteration, trend, best_so_far, reports[], notes}
report      decision            {decision, rationale}
report      run_finished        {ranking, best, best_candidate, rationale, truncated, …}
report      artifact            {name:"report.md", url} / {name:"agent_report", report}
```

With `extract=agent` (the default for uploaded devices) an `extract` stage
comes first, ending in `decision {decision:"spec accepted", crosscheck,
overrides, agent_summary}` — that is Devin reading the build file, and it is
the most interesting thing to show on screen.

`iteration_scored.reports[]` is the evidence the agent reasons over:
per candidate `{result, diffs[], score, hints[]}` where `diffs` are
`{requirement, target, actual, margin, unit, passing}`. That maps straight
onto a requirements table with signed margins.

**4. Everything else:** `GET /runs/{id}` full snapshot (same shapes, for
refresh/late join), `GET /runs` list, `POST /runs/{id}/messages {"text": …}`
to send the user's mid-run note to the agent, and
`GET /runs/{id}/artifacts/{report.md | run.json | s11_<candidate_id>.csv}`.

Devin runs take minutes and the WS is the only progress signal — render
`agent_message` prominently.

---

## Merging into `dev`

Before merging: `git fetch && git merge origin/dev`, resolve on your side,
then push. Sanity check afterwards:

```bash
cd backend && uv run python scripts/selftest.py      # offline, ~10 s, no Devin/bpy
cd frontend && npx tsc --noEmit && npx eslint src    # then click Run in the browser
```

Two things that have bitten us: don't hand-resolve a config file by keeping
both halves (`.entire/settings.json` became two concatenated JSON objects
that way, and Entire capture is required for submission); and a `curl`/`tsc`
check is not a UI check — a snapshot that type-checks can still be missing
the fields a panel dereferences.
