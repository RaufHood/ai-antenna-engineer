# Kevin — AI antenna engineer

An autonomous agent (Devin) places antennas inside a real phone. It reads the
build file, proposes where each antenna goes and what type it is, a solver
scores every proposal against the band requirements, the evidence goes back,
and the agent iterates until the design is good enough — then writes the
report. A web UI shows the loop live on the 3D model.

```
 .blend + prompt                                        Devin API
       │                                                    ▲
       ▼                                                    │ session + messages
┌──────────────────┐   REST + WS   ┌─────────────────────────────┐
│ frontend/        │◄─────────────►│ backend/  (FastAPI)         │
│ Next.js + three  │  events/steps │  orchestrator = THE LOOP    │
└──────────────────┘               │  agent proposes → sim scores│
                                   │  → evidence back → iterate  │
                                   └──────────────┬──────────────┘
                                                  │ solve(spec, band, candidate)
                                                  ▼
                                   PyNEC (default, ms)  ·  rf/ openEMS (optional, minutes)
```

Devin owns the engineering judgment. The backend owns the loop, the scoring
and the event stream. `rf/` owns the physics. The frontend owns the display.
Nobody reaches across a seam except through the contracts in
[INTEGRATION.md](INTEGRATION.md).

## Run it

Everything below was verified on a clean clone of `dev`.

```bash
cd backend
uv sync
uv run python scripts/selftest.py      # offline, ~10 s: must print ALL OK
uv run python scripts/dev_run.py       # full agent loop, mock agent, ~1 s
```

`dev_run.py` ends with `status=finished`, ~19 simulations, best S11 around
-16 dB with `meets=True`, and writes `backend/var/artifacts/<run_id>/`
(report.md, run.json, S11 CSVs). If that works, the loop works.

The UI, two terminals:

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev      # http://localhost:3000
```

Pick bands, press **Run placement study**. Everything on screen comes from
the backend; if it is down the UI says so and draws nothing, rather than
showing a stand-in that could be mistaken for a simulation.

### The real agent

`backend/.env` is gitignored and does not come with the clone:

```bash
cd backend && cp .env.example .env    # fill in DEVIN_API_KEY, DEVIN_ORG_ID
```

Then `AGENT=devin uv run python scripts/dev_run.py`, or flip the toggle in
the UI to **Devin**. Expect a few minutes: ~98 % of that is Devin reasoning,
~2 % is physics.

### The solver

PyNEC is the default and the fast path — 83 ms per Wi-Fi 2.4 GHz solve, a
whole two-iteration loop in under a second — and it installs with the backend.
`SIM_SOLVER` must be **unset** for it; if it is set to
`app.sim.rf_adapter:solve` you are on openEMS and every solve costs minutes.

**Do not build openEMS or create `rf/.venv` / a bpy environment** to run the
loop. Those are for `rf/`'s own work (FDTD confirmation, media rendering,
regenerating device geometry from a `.blend`); the geometry the loop needs is
committed as `rf/blend_loader/out/device.json`. Check it is live:

```bash
cd backend && uv run python -m app.sim.priors
```

must report `5 legal, 15 ruled out` with named blockers such as
`exterior.frame.band_seg_2`. "Screening unavailable" means the manifest is
missing — say so rather than working around it.

## Layout

| path | what |
|---|---|
| [backend/](backend/README.md) | FastAPI service: agent port (Devin / mock), orchestrator, scoring, event log, API. [DESIGN.md](backend/DESIGN.md) has the ADRs. |
| [frontend/](frontend/README.md) | Next.js + three.js UI. `src/lib/backend.ts` is the proxy to the backend. |
| [rf/](rf/README.md) | openEMS FDTD solve, geometry screening, media suite. Three environments of its own — none needed for the loop. |
| `data/` | Device assets: the iPhone 15 Pro `.blend` + materials sidecar, a synthetic 15-part fixture, a test axe, a human base-mesh bundle (unused so far). |
| `runs/` | Committed run artifacts and the demo media (reviewers see results without running anything). |
| `tools/` | `.blend` extraction script shared by backend and rf; synthetic fixture generator. |
| `brand/` | The Kevin marks (icon + lockup); the frontend inlines them. |
| [pitch-deck/](pitch-deck/README.md) | The nine slides we present, as a self-contained HTML deck plus a PDF and one PNG per slide. Every figure on them traces back to this repo. |
| [ENTIRE.md](ENTIRE.md) | Entire session capture — mandatory for the submission, two machine-local steps. |
| [deep_research_on_challenge.md](deep_research_on_challenge.md) | The research the JSON contracts in `types.ts` / `models.py` mirror. |

## Branches

`dev` is the integration branch. Work on your own branch, merge into `dev`,
then run the selftest. Anything gitignored does not come with a clone — when
a teammate's machine behaves differently, look at `.gitignore` first.
