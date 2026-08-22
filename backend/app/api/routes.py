"""HTTP + WS surface (DESIGN.md §9)."""
from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.agent.devin import DevinAgent, DevinConfigError
from app.agent.mock import MockAgent
from app.geometry.spec import make_anchors, phone_v1
from app.runs import orchestrator, store
from app.runs.store import Run

router = APIRouter()


class CreateRun(BaseModel):
    prompt: str = ""
    bands: list[str] = ["wifi24"]
    agent: str = "devin"  # devin (default) | mock (offline fallback)


@router.post("/runs")
async def create_run(body: CreateRun) -> dict:
    spec = phone_v1()  # M2 replaces with .blend extraction
    known = {b.id for b in spec.requirements.bands}
    if not set(body.bands) & known:
        raise HTTPException(400, f"no known band in {body.bands}; have {sorted(known)}")
    run = Run(id=f"run_{secrets.token_hex(4)}", prompt=body.prompt,
              band_ids=body.bands, spec=spec, anchors=make_anchors(spec))
    store.put(run)
    if body.agent == "devin":
        try:
            agent = DevinAgent()
        except DevinConfigError as e:
            raise HTTPException(503, f"Devin not configured: {e}. "
                                     f"Pass agent='mock' for the offline loop.")
    elif body.agent == "mock":
        agent = MockAgent()
    else:
        raise HTTPException(400, f"unknown agent {body.agent!r}")
    run.task = asyncio.create_task(orchestrator.drive(run, agent))
    return {"run_id": run.id}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    return {
        "run_id": run.id,
        "status": run.status,
        "stage": run.stage,
        "iteration": run.iteration,
        "truncated": run.truncated,
        "n_events": len(run.log.events),
        "candidates": {k: c.model_dump() for k, c in run.candidates.items()},
        "results": {k: r.model_dump() for k, r in run.results.items()},
        "final": run.final,
    }


@router.websocket("/runs/{run_id}/events")
async def run_events(ws: WebSocket, run_id: str, since: int = 0) -> None:
    run = store.get(run_id)
    if run is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    backlog, q = run.log.subscribe(since)
    try:
        for ev in backlog:
            await ws.send_text(ev.model_dump_json())
        while True:
            ev = await q.get()
            await ws.send_text(ev.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        run.log.unsubscribe(q)


@router.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "runs": len(store.all_runs())}
