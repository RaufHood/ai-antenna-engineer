# AI Antenna Engineer

**An AI agent that designs and places phone antennas — and proves its design works with real electromagnetic physics simulation, not guesswork.**

---

## Table of contents

- [The problem, in plain terms](#the-problem-in-plain-terms)
- [The solution, in one picture](#the-solution-in-one-picture)
- [What's real vs. simulated for the demo](#whats-real-vs-simulated-for-the-demo)
- [Repo structure](#repo-structure)
- [How to run it](#how-to-run-it)
  - [1. Frontend (UI, works standalone)](#1-frontend-ui-works-standalone)
  - [2. Backend + real agent loop](#2-backend--real-agent-loop)
  - [3. RF simulation engine (optional, real openEMS)](#3-rf-simulation-engine-optional-real-openems)
- [Components explained](#components-explained)
- [The agent, explained](#the-agent-explained)
- [Metrics — what the agent has actually achieved](#metrics--what-the-agent-has-actually-achieved)
- [Status & honest caveats](#status--honest-caveats)
- [Further reading](#further-reading)

---

## The problem, in plain terms

Every phone needs antennas (cellular, Wi-Fi, GPS, 5G...) squeezed into a tiny metal-and-glass box that is already full of batteries, cameras, and circuit boards. **Where you put the antenna, and what shape it is, decides whether it actually works** — a badly placed antenna wastes power, has a weak signal, or fails safety limits.

Today this is a slow, manual job for a specialist RF engineer: guess a spot, run an expensive physics simulation, look at the result, tweak it, simulate again — repeat for days.

**Our idea:** give an AI coding agent ([Devin](https://devin.ai)) the phone's 3D model and a target radio band, and let it *behave like that RF engineer* — propose a placement, run a real electromagnetic simulation to check it, read the results, and iterate — fully autonomously, until it has a design it can justify with evidence.

## The solution, in one picture

```
   .blend 3D model                                  ┌─────────────────────┐
   of the phone            ┌──────────────┐  HTTPS   │   Devin (AI agent)  │
   + "put a 2.4GHz    ────►│   Backend    │◄────────►│  - reads geometry   │
     antenna in this"      │  (FastAPI)   │ sessions  │  - proposes spots  │
                           │              │           │  - reads sim data  │
   ┌──────────────┐  REST/ │  Orchestrator│           │  - decides & tunes │
   │   Frontend    │  WS   │  (state      │           └──────────────────┘
   │  3D viewer +  │◄─────►│   machine)   │
   │  live results │       └──────┬───────┘
   └──────────────┘               │  solve(spec, band, candidate) -> SimResult
                                   ▼
                    ┌───────────────────────────────┐
                    │   Physics engine (rf/)         │
                    │   openEMS — real FDTD Maxwell   │
                    │   solver, S11 / VSWR / gain /   │
                    │   efficiency out of a real       │
                    │   electromagnetic field solve    │
                    └───────────────────────────────┘
```

The agent never has to "trust its own guess." Every candidate placement it proposes gets simulated by a real physics engine before the agent is allowed to move on — this is enforced by the backend as a hard rule (the **simulation gate**, see [The agent, explained](#the-agent-explained)).

## What's real vs. simulated for the demo

Being upfront about this matters for judging, so here it is directly:

| Piece | Status |
|---|---|
| 3D geometry ingestion from a real `.blend` file (parts, materials, bounding boxes) | ✅ Real — tested on a real iPhone 15 Pro model (191 parts) |
| Candidate placement search (grid of positions around the device perimeter, keep-out/clearance aware) | ✅ Real, deterministic geometry logic |
| Devin agent loop (propose → simulate → read evidence → refine → decide) | ✅ Real, live-verified end-to-end against the Devin v3 API |
| Fast in-loop physics solver (PyNEC, method-of-moments) — what the agent iterates against | ✅ Real physics, runs in milliseconds, no bulk dielectrics (metal/wire only) |
| Full-wave electromagnetic solver (openEMS, FDTD) — physically accurate, used to confirm the agent's final answer | ✅ Real, verified against real openEMS on real device geometry (~60s/run); **not yet cross-checked against a textbook reference case**, so treat absolute numbers as indicative, not certified |
| 3D viewer, keep-out overlays, S11 charts, ranked results table (frontend) | ✅ Real UI, wired to live backend data |
| Frontend's own built-in physics stand-in (`src/lib/rf.ts`) | ⚠️ A lightweight formula, used only if you run the frontend *without* the backend — see [§1](#1-frontend-ui-works-standalone) |

## Repo structure

```
challenge/
├── frontend/     Next.js UI — 3D device viewer, run configuration, live results
├── backend/      FastAPI service — orchestrates the agent loop, HTTP/WebSocket API
├── rf/           The physics: openEMS FDTD solver + PyNEC fast oracle
├── tools/        Shared scripts (Blender extraction, fixture generation)
├── data/         Sample 3D phone models (.blend) used for demos/tests
└── deep_research_on_challenge.md   Background research this project is built on
```

Each of `frontend/`, `backend/`, and `rf/` has its own deeper README/DESIGN doc — linked in [Further reading](#further-reading).

## How to run it

You can run these independently — the frontend has its own built-in mock physics so it works with zero setup, and the backend can run with a heuristic mock agent so you don't need Devin credentials just to see the pipeline move.

### 1. Frontend (UI, works standalone)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. This gives you the full 3D viewer, keep-out zones, run configuration panel, and results table, using the frontend's own lightweight formula for S11 instead of a real solver — good for exploring the UI/UX with no other services running.

### 2. Backend + real agent loop

```bash
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
```

- By default the run uses a **heuristic mock agent** (no API key needed) — pass `"agent": "mock"` when starting a run, or just don't set Devin credentials.
- To use the **real Devin agent**, add a `.env` file in `backend/` (gitignored) with:
  ```
  DEVIN_API_KEY=cog_...
  DEVIN_ORG_ID=...
  # optional
  DEVIN_MAX_ACU=...
  DEVIN_MODE=...
  DEVIN_REPO=owner/repo   # lets Devin use the repo's Skills for extraction
  ```
- Quick no-HTTP smoke test (mock agent, canned phone spec, ~seconds):
  ```bash
  uv run python scripts/dev_run.py
  ```
- Same, but with a real `.blend` model and the real agent:
  ```bash
  AGENT=devin BLEND=../data/phone_synth_v1/phone_synth_v1.blend uv run python scripts/dev_run.py
  ```
- Offline self-test (no Devin, no simulation dependencies, ~10s): `uv run python scripts/selftest.py`

Then point the frontend at the backend, or drive it directly — see the [API table](backend/README.md#api) in `backend/README.md`.

**Windows note:** the backend's fast in-loop solver depends on `pynec`, which has no prebuilt Windows wheel — `uv sync` compiles it from source and needs the MSVC C++ compiler. If `uv sync` fails with `Microsoft Visual C++ 14.0 or greater is required`, install the "Desktop development with C++" workload for Visual Studio Build Tools, then retry.

### 3. RF simulation engine (optional, real openEMS)

The backend's fast in-loop solver (PyNEC) has **no extra setup** — it's a normal Python dependency (`pynec`, declared in `backend/pyproject.toml`). The full-wave openEMS solver used for the final "real physics" confirmation needs its own environment (Windows-only prebuilt wheels):

```bash
# one-time setup — see rf/README.md for full detail
py -3.11 -m venv rf/.venv
mkdir -p rf/vendor
curl -L -o rf/vendor/openEMS_v0.0.36.zip https://github.com/thliebig/openEMS-Project/releases/download/v0.0.36/openEMS_v0.0.36.zip
unzip -q -o rf/vendor/openEMS_v0.0.36.zip -d rf/vendor/
cd rf && .venv/Scripts/pip install -r requirements.txt
cd .. && rf/.venv/Scripts/python -m rf.openems_env   # smoke test

# run one demo simulation end to end (~2 min)
rf/.venv/Scripts/python -m rf.run_simulation
```

To have the backend use the real openEMS solver as the final confirmation step on the agent's winning candidate (rather than only the fast oracle), set:

```bash
CONFIRM_SOLVER=app.sim.rf_adapter:solve uv run uvicorn app.main:app --port 8000
```

## Components explained

### Frontend (`frontend/`) — Next.js + Three.js
The judge-facing demo surface. Loads a phone 3D model (`.glb`), lets you pick a target radio band and constraints (S11 target, efficiency floor, SAR standard), kicks off a run, and streams results back live: 3D placement markers, keep-out conflict highlighting, per-band S11 sweep charts, an isolation view for multi-antenna setups, and a plain-English engineering report. See [`frontend/README.md`](frontend/README.md).

### Backend (`backend/`) — FastAPI orchestrator
The state machine that runs the show. It:
1. Ingests the `.blend` model, extracts geometry (component boxes, materials, ground plane).
2. Generates a set of **candidate positions** around the device perimeter, each annotated with real clearance-to-metal distances.
3. Drives the agent loop: sends the agent evidence, asks for the next action, executes it (simulate a batch, sweep a parameter, or finish), repeats.
4. Enforces one hard rule — the agent's final answer must have been simulated (the **simulation gate**).
5. Emits every step as a structured event over a WebSocket, so the frontend can show the process live, and renders a final report/artifacts.

See [`backend/README.md`](backend/README.md) for the full HTTP/WebSocket API, and [`backend/DESIGN.md`](backend/DESIGN.md) for the architecture rationale (it's written as a living decision log — useful if you want to see *why* things are built this way).

### RF simulation (`rf/`) — the physics
Two solvers, used for different jobs:
- **PyNEC (Method-of-Moments)** — the backend's fast "in-loop oracle." Runs in milliseconds, so the agent can test dozens of candidate positions per turn. Models the phone chassis and antenna as wire geometry (no dielectrics — metal only).
- **openEMS (FDTD)** — a real full-wave Maxwell's-equations solver. Models the actual materials (FR4 board, glass, battery — with real ε_r/conductivity), computes S11, resonance, bandwidth, gain, and radiation efficiency from an actual simulated electromagnetic field. Takes ~1-2 minutes per run, so it's used sparingly: once, to confirm the agent's winning design, not for every candidate in the search.

See [`rf/README.md`](rf/README.md) for the exact input/output contract and [`rf/progress_simulation.md`](rf/progress_simulation.md) for what's been validated so far.

### Tools & data (`tools/`, `data/`)
- `tools/extract_blend.py` — the one script (used by both the backend and by Devin itself, inside its own sandbox) that turns a `.blend` file into structured geometry: every part's bounding box (mm), material, and dielectric properties.
- `tools/make_phone_blend.py` — generates a synthetic 15-part phone fixture for testing without needing a real device model.
- `data/` — sample 3D assets, including a real Apple iPhone 15 Pro model (`data/apple_iphone_15_pro/`) used for the live-verified runs below, and a synthetic phone fixture (`data/phone_synth_v1/`).

## The agent, explained

The agent is [**Devin**](https://devin.ai), an AI software engineer, driven through Devin's v3 session API. It is *not* wired up with a traditional function-calling API — instead:

1. The backend opens **one long-lived Devin session per run** and gives it a prompt describing the task, the device spec, the target radio band(s), and a small protocol: *"reply with exactly one fenced JSON action: `simulate`, `sweep`, or `done`."*
2. Devin reasons about the geometry (which spots are clear of metal/batteries/cameras, what antenna type fits the available space) and replies with an action, e.g. *"simulate these 12 candidate positions."*
3. The backend runs those simulations (via the fast oracle), and sends back **evidence, not verdicts** — the raw S11 curve, how far off each requirement is (e.g. *"S11 at 2400 MHz is −4.1 dB, need ≤ −6 dB, short by 1.9 dB"*), whether it's converging or oscillating, and deterministic physics hints (e.g. *"resonance is 7% off target → arm is roughly 7% too short"*).
4. Devin reads that and decides its next move — try more spots, sweep a dimension across a range, or conclude it has a winner.
5. **The one rule the backend enforces:** Devin cannot declare `done` on a candidate that has never actually been simulated. Everything else — how many iterations, when it's "good enough" — is left to the agent's own engineering judgment.
6. Once Devin is done, the backend (optionally) runs the winning design through the **real openEMS solver** one last time as an independent, physics-accurate confirmation, and attaches that to the final report.

If Devin's API is unavailable or a key isn't configured, a heuristic **mock agent** implements the exact same interface, so the whole pipeline still runs end-to-end for demoing offline.

## Metrics — what the agent has actually achieved

These are results from live, verified runs (see `backend/DESIGN.md` §11 for the full log), not projections:

| Run | Device model | Outcome |
|---|---|---|
| M1 (synthetic canned spec) | Simple reference phone | 3 iterations, 32 simulations, converged to an IFA antenna at a right-edge position, **S11 = −21.5 dB, VSWR = 1.24**, full target band under −10 dB |
| M2 (synthetic 15-part fixture) | Generated phone fixture | Devin read the model unassisted, flagged 4 real layout issues on its own (oversized ground pour, unslotted rails, etc.), 3 iterations / 46 simulations → monopole antenna, **S11 = −24.3 dB, VSWR = 1.21** |
| M2 (real device) | **Real Apple iPhone 15 Pro model, 191 parts** | Devin extracted geometry in its own VM, applied 12 material/role corrections, ran 3 iterations / 32 simulations, tested and *rejected* the IFA family on evidence, converged on a **28 mm corner monopole**: **S11 = −17.6 dB at 2.46 GHz, VSWR = 1.30, efficiency = 0.98**, all requirements passing including the 12 mm keep-out constraint |
| Real-solver confirmation | iPhone 15 Pro model | The winning candidate re-solved with real openEMS FDTD (not the fast oracle): ~61s runtime, genuine S11 curve returned end-to-end through the full pipeline |

**Engineering targets used for pass/fail:** return loss (S11) ≤ −6 to −10 dB, VSWR < 2–3, radiation efficiency > 40–50%, and a minimum keep-out clearance around the antenna (≥ 12–15 mm depending on band) — standard handset RF design thresholds (see [`deep_research_on_challenge.md`](deep_research_on_challenge.md) for where these numbers come from).

## Status & honest caveats

- **The fast in-loop solver (PyNEC) has no bulk dielectrics** — it models the chassis as bare metal/wires. It's what makes rapid iteration possible, but the numbers it produces during the search are a simplification; the openEMS confirmation step is what accounts for real materials (glass, FR4, battery).
- **openEMS's own resonance numbers are not yet cross-checked against a textbook reference case** (that validation step is still open — see `rf/progress_simulation.md`). Treat absolute performance numbers as directionally correct engineering signal, not certification-grade results.
- **The real-solver confirmation is Windows-only** today (openEMS ships only prebuilt Windows wheels used here).
- **The agent's in-loop reasoning sees the fast oracle's numbers, not openEMS's**, by design — openEMS is spent once, at the end, to keep the search fast and watchable. This is a scope decision, documented in [`AGENT_SIM_INTEGRATION_PLAN.md`](AGENT_SIM_INTEGRATION_PLAN.md).
- Simulation is not a substitute for physical measurement — hand/head detuning, SAR compliance, and manufacturing tolerance all still require lab testing in a real product.

## Further reading

- [`deep_research_on_challenge.md`](deep_research_on_challenge.md) — the RF/antenna and EM-simulation background research this project is grounded in (antenna types, frequency bands, SAR limits, solver comparisons).
- [`backend/DESIGN.md`](backend/DESIGN.md) — full backend/agent architecture, decision log, and API contracts.
- [`AGENT_SIM_INTEGRATION_PLAN.md`](AGENT_SIM_INTEGRATION_PLAN.md) — how the agent loop and the real openEMS solver were wired together.
- [`rf/progress_simulation.md`](rf/progress_simulation.md) — simulation workstream's own progress notes and open validation items.
