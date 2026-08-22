# AI Antenna Engineer — backend

FastAPI backend that turns Devin into an RF engineer: it proposes antenna
placements for a phone build file, a solver simulates them, evidence goes
back, and the agent iterates until it judges the design good enough.
Architecture, contracts and decisions: [DESIGN.md](DESIGN.md).

## Run

```bash
uv sync
uv run uvicorn app.main:app --port 8000
```

Live agent needs `.env` (gitignored) with `DEVIN_API_KEY`, `DEVIN_ORG_ID`,
optional `DEVIN_MAX_ACU` / `DEVIN_MODE`. Without it, pass `"agent": "mock"`.

No-HTTP smoke test: `uv run python scripts/dev_run.py` (env `AGENT=devin`
for the real agent).

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/runs` | `{"prompt": str, "bands": ["wifi24"], "agent": "devin"\|"mock"}` → `{run_id}` |
| GET | `/runs/{id}` | snapshot: status, stage, candidates, results, final |
| WS | `/runs/{id}/events?since=N` | event stream; replays everything after seq N on (re)connect |
| GET | `/healthz` | liveness |

Event envelope: `{run_id, seq, ts, stage, type, payload}` with `type` one of
`stage_started stage_progress agent_message candidates_proposed sim_started
sim_result iteration_scored decision artifact run_finished error`.
`sim_result` payload is a `SimResult`; `iteration_scored` carries the full
evidence report (diffs/trend/hints) the agent reasons over.

## Seams

- **Agent**: `app/agent/port.py` — Devin (`app/agent/devin.py`, default) or
  the offline mock. The orchestrator owns the workflow either way.
- **Simulation**: one callable, `solve(spec, band, candidate) -> SimResult`.
  Select with `SIM_SOLVER=module:function` (default: bundled reference
  oracle `app.sim.oracle:solve`). Sim team: implement the contract, point
  the env var at it, done.
