# Kevin — frontend

The screen for the agent loop: load a handset, pick the bands, press **Run
placement study**, and watch the agent propose, the solver score and the
design converge on the 3D model. Everything on screen comes from the
backend; the browser never talks to port 8000 directly.

```bash
cp .env.example .env.local   # BACKEND_URL, default AGENT
npm install
npm run dev                  # http://localhost:3000  (backend on :8000 first)
```

## What is on screen

| Panel | Shows | Source |
|---|---|---|
| Device | Name, outline, parts; `Load .blend / .glb` | built-in Handset A, or the backend's spec after a `.blend` upload |
| Bands | Which bands the run must satisfy, and each band's S11 / efficiency / clearance targets | the backend's band catalogue (`backend/app/geometry/bands.py`) |
| Components | Parts as the solver sees them; hover/select/hide/isolate drive the viewer | `spec.components` |
| Viewer | Procedural handset (or the uploaded `device.glb`), candidate antennas, keep-out volumes and their conflicts, camera presets, exploded view | candidates + results from the run |
| Spectrum | Target bands on a log axis and where each chosen design actually resonated | results |
| Results | Every simulated candidate: S11, f₀, bandwidth, efficiency, VSWR, pass/fail | `sim_result` events |
| Report | The agent's own `report.md` | `GET /runs/{id}/artifacts/report.md` |
| Agent | Live feed (Devin's words + the orchestrator narrating), sim queue, prompt, mid-run notes; `Mock` / `Devin` picks the agent per run | the run's event log |

Not on screen, because nothing models it: SAR, hand/head detuning, inter-antenna
isolation. The report says which solver produced the numbers and what its
limits are.

## Layout

```
src/app/api/run/route.ts     POST start · GET snapshot / report.md · PATCH note   -> backend /runs
src/app/api/device/route.ts  POST .blend upload · GET artifact stream             -> backend /devices
src/lib/backend.ts           wire shapes + the mapping onto RunSnapshot
src/lib/store.ts             one zustand store: device, viewer state, the run
src/lib/device.ts            Handset A, mirrored box for box from backend/app/geometry/spec.py
src/lib/types.ts             contracts shared with backend/app/models.py
src/components/panels/       TopBar, SpecPanel (device + bands), ComponentTree, ResultsDock, AgentPanel
src/components/viewer/       three.js scene: PhoneModel, CustomModel, Antennas, Keepouts
src/components/Logo.tsx      the Kevin marks, inlined from ../brand
```

If the backend is down the run button reports that and nothing else is
drawn — there is deliberately no local stand-in that could be mistaken for
a simulation.

## Checks

```bash
npx tsc --noEmit && npx eslint src
```

Then click Run in the browser: a type-checked snapshot can still miss a
field a panel dereferences.
