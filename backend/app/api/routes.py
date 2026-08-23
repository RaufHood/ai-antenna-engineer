"""HTTP + WS surface (DESIGN.md §9)."""
from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from pathlib import Path

from fastapi import (APIRouter, File, Form, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.agent.devin import DevinAgent, DevinConfigError
from app.agent.mock import MockAgent
from app.geometry import bands as bands_mod
from app.geometry import bands
from app.geometry import extract as ex
from app.geometry.spec import default_spec, make_anchors
from app.sim.priors import anchors_for
from app.models import EventType
from app.runs import devices, orchestrator, report, store
from app.runs.store import Run

router = APIRouter()

_MEDIA = {".glb": "model/gltf-binary", ".json": "application/json",
          ".stl": "model/stl"}


# ------------------------------------------------------------------ devices --

@router.post("/devices")
async def create_device(blend: UploadFile = File(...),
                        materials: UploadFile | None = File(None),
                        wait: bool = Form(True)) -> dict:
    """Upload a .blend (+ optional materials.json sidecar). Runs the shared
    extraction script, classifies, and returns spec + anchors + artifact list.
    `wait=false` returns immediately with status=extracting; poll GET."""
    if not (blend.filename or "").lower().endswith(".blend"):
        raise HTTPException(400, "expected a .blend file")
    up = ex.VAR_DIR / "uploads" / secrets.token_hex(4)
    up.mkdir(parents=True, exist_ok=True)
    bpath = up / Path(blend.filename).name
    with bpath.open("wb") as f:
        shutil.copyfileobj(blend.file, f)
    spath = None
    if materials is not None and materials.filename:
        spath = up / "materials.json"
        with spath.open("wb") as f:
            shutil.copyfileobj(materials.file, f)
    device = devices.register(bpath, spath)
    shutil.rmtree(up, ignore_errors=True)
    if wait:
        await devices.prepare(device)
        if device.status == "failed":
            raise HTTPException(422, f"extraction failed: {device.error}")
    else:
        await devices.prepare_background(device)
    return devices.snapshot(device)


@router.get("/builtin-devices")
async def builtin_devices() -> list[dict]:
    """The devices that ship with the app, for the client's picker.

    Only the ones whose manifest is actually present: a fresh clone that has
    not built the MacBook manifest simply does not offer it, rather than
    offering it and failing on click.
    """
    from app.geometry.manifest import available
    return [{k: v for k, v in d.items() if k != "manifest"} for d in available()]


@router.get("/default-device")
async def default_device(bands: str = "wifi24", device: str | None = None) -> dict:
    """The device a run gets when none was uploaded — spec and anchors.

    The UI used to draw a hard-coded slab here while the solver read the real
    iPhone manifest, so the panel claimed a 9-part "Handset A" was the solver
    geometry. One of them was wrong and it was not the solver.
    """
    ids = [b for b in bands.split(",") if b]
    if bad := bands_mod.unknown(ids):
        raise HTTPException(400, f"unknown bands {bad}")
    # `requirements.bands` is the MENU the panel offers, not the selection —
    # the selection is the client's `enabledBands`, and a run narrows the spec
    # itself at creation. Returning only the requested ids collapsed the menu
    # to whatever happened to be enabled, so every other band vanished from the
    # panel and could never be switched back on.
    from app.geometry.manifest import builtin
    entry = builtin(device)
    if device and entry is None:
        raise HTTPException(404, f"unknown built-in device {device!r}")
    spec = default_spec(ids, device).model_copy(
        update={"requirements": bands_mod.requirements_for()})
    anchors, source = anchors_for(spec, ids)
    return {"spec": spec.model_dump(),
            "anchors": [a.model_dump() for a in anchors],
            "anchor_source": source,
            "builtin": {k: v for k, v in (entry or {}).items() if k != "manifest"} or None}


@router.get("/devices")
async def list_devices() -> list[dict]:
    return [{"device_id": d.id, "name": d.name, "status": d.status}
            for d in store.all_devices()]


@router.get("/devices/{device_id}")
async def get_device(device_id: str) -> dict:
    d = store.get_device(device_id)
    if d is None:
        raise HTTPException(404, "unknown device")
    return devices.snapshot(d)


@router.get("/devices/{device_id}/artifacts/{name:path}")
async def device_artifact(device_id: str, name: str) -> FileResponse:
    d = store.get_device(device_id)
    if d is None:
        raise HTTPException(404, "unknown device")
    p = ex.artifact_path(d.dir, name)
    if p is None:
        raise HTTPException(404, f"no artifact {name!r}; have {d.artifacts()}")
    return FileResponse(p, media_type=_MEDIA.get(p.suffix, "application/octet-stream"),
                        filename=p.name)


# --------------------------------------------------------------------- runs --

class CreateRun(BaseModel):
    prompt: str = ""
    bands: list[str] = ["wifi24"]
    agent: str = "devin"          # devin (live) | replay (recorded run) | mock
    device_id: str | None = None  # from POST /devices; None -> a built-in
    # Which built-in to solve when no uploaded device was given. None keeps
    # the first one, which is the phone.
    builtin: str | None = None
    # agent: Devin reads the .blend itself (skill), backend result is the
    # cross-check/fallback. backend: spec is final before the session starts.
    extract: str | None = None    # default from EXTRACT_MODE env, else "agent"
    # Render this run's own placement maps, x-ray, S11 and field animation
    # once it concludes, instead of shipping a demo run's pictures.
    media: bool = False


@router.post("/runs")
async def create_run(body: CreateRun) -> dict:
    if body.device_id:
        device = store.get_device(body.device_id)
        if device is None:
            raise HTTPException(404, "unknown device")
        if device.status != "ready":
            raise HTTPException(409, f"device is {device.status}: {device.error or ''}")
        if bad := bands.unknown(body.bands):
            raise HTTPException(400, f"unknown bands {bad}; have {sorted(bands.CATALOG)}")
        spec = device.spec.model_copy(
            update={"requirements": bands.requirements_for(body.bands)})
        anchors, anchor_source = await asyncio.to_thread(anchors_for, spec, body.bands)
        if not anchors:
            anchors, anchor_source = device.anchors, "device"
        mode = body.extract or os.environ.get("EXTRACT_MODE", "agent")
    else:
        if bad := bands.unknown(body.bands):
            raise HTTPException(400, f"unknown bands {bad}; have {sorted(bands.CATALOG)}")
        from app.geometry.manifest import builtin as builtin_entry
        if body.builtin and builtin_entry(body.builtin) is None:
            raise HTTPException(404, f"unknown built-in device {body.builtin!r}")
        spec = default_spec(body.bands, body.builtin).model_copy(
            update={"requirements": bands.requirements_for(body.bands)})
        # Where the agent is allowed to put an antenna. Derived by sweeping
        # this device's real internals, not from a lattice on its bounding box
        # — otherwise every phone of the same outside size gets the same
        # placements, which is the opposite of what this tool claims to do.
        # The first scan of a device+band costs ~5 s and is cached after; it
        # goes to a thread so it cannot stall the event loop.
        anchors, anchor_source = await asyncio.to_thread(anchors_for, spec, body.bands)
        device, mode = None, "backend"
    if mode not in ("agent", "backend"):
        raise HTTPException(400, "extract must be 'agent' or 'backend'")

    if body.agent == "devin":
        try:
            agent = DevinAgent()
        except DevinConfigError as e:
            raise HTTPException(503, f"Devin not configured: {e}. "
                                     f"Pass agent='mock' for the offline loop.")
    elif body.agent == "mock":
        agent = MockAgent()
    elif body.agent == "replay":
        # A recorded live run, played back instantly and for free. Not the
        # heuristic: these are the real agent's decisions and prose, which is
        # the part worth showing when quota is gone or a demo has to be
        # repeatable.
        from app.agent.replay import ReplayAgent, tape_for
        tape = os.environ.get("REPLAY_TAPE") or tape_for(spec, body.bands)
        try:
            agent = ReplayAgent(tape)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(503, f"no usable tape: {e}")
    else:
        raise HTTPException(400, f"unknown agent {body.agent!r}; "
                                 f"expected devin, replay or mock")

    run = Run(id=f"run_{secrets.token_hex(4)}", prompt=body.prompt,
              band_ids=body.bands, spec=spec, anchors=anchors, device=device,
              extract_mode=mode, ambiguities=list(device.ambiguities) if device else [],
              spec_source="backend" if device else "canned", media=body.media)
    store.put(run)
    run.task = asyncio.create_task(orchestrator.drive(run, agent))
    return {"run_id": run.id, "device_id": device.id if device else None,
            "extract_mode": mode, "anchor_source": anchor_source}


@router.get("/runs")
async def list_runs() -> list[dict]:
    return [{"run_id": r.id, "status": r.status, "stage": r.stage,
             "device_id": r.device.id if r.device else None,
             "bands": r.band_ids, "created_at": r.created_at}
            for r in store.all_runs()]


class UserMessage(BaseModel):
    text: str


@router.post("/runs/{run_id}/messages")
async def post_message(run_id: str, body: UserMessage) -> dict:
    """Mid-run user feedback for the agent. Delivered with the next evidence
    message (no extra agent turn); echoed on the event stream immediately."""
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    if run.status != "running":
        raise HTTPException(409, f"run is {run.status}")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "empty message")
    run.inbox.append(text[:2000])
    ev = run.log.emit(run.stage, EventType.agent_message, {"role": "user", "text": text})
    return {"queued": len(run.inbox), "seq": ev.seq}


@router.get("/runs/{run_id}/artifacts/{name}")
async def run_artifact(run_id: str, name: str) -> Response:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    rendered = report.render(run, name)
    if rendered is None:
        raise HTTPException(404, f"no artifact {name!r}; have {report.artifact_names(run)}")
    body, media = rendered
    return Response(content=body, media_type=media)


@router.get("/runs/{run_id}/media/{name}")
async def run_media(run_id: str, name: str) -> FileResponse:
    """Serve one rendered artifact. `artifact_path` refuses anything that
    resolves outside the run's own media directory."""
    from app.runs import media as media_mod

    p = media_mod.artifact_path(run_id, name)
    if p is None:
        raise HTTPException(404, "no such media artifact")
    kind = {".png": "image/png", ".gif": "image/gif",
            ".mp4": "video/mp4"}.get(p.suffix, "application/octet-stream")
    return FileResponse(p, media_type=kind, filename=p.name)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    return {
        "run_id": run.id,
        "device_id": run.device.id if run.device else None,
        "status": run.status,
        "stage": run.stage,
        "iteration": run.iteration,
        "truncated": run.truncated,
        "spec_source": run.spec_source,
        "ambiguities": run.ambiguities,
        "artifacts": report.artifact_names(run),
        "media": run.media_artifacts,
        "media_requested": run.media,
        "n_events": len(run.log.events),
        "spec": run.spec.model_dump(),
        "anchors": [a.model_dump() for a in run.anchors],
        "candidates": {k: c.model_dump() for k, c in run.candidates.items()},
        "results": {k: r.model_dump() for k, r in run.results.items()},
        "final": run.final,
    }


@router.get("/runs/{run_id}/log")
async def run_log(run_id: str, since: int = 0) -> dict:
    """REST replay of the event log (same events as the WS, `seq > since`).
    For pollers that cannot hold a socket — a Next.js route handler serving
    the UI's snapshot, a script tailing a run — without a second code path
    on the backend: both views read the one append-only log."""
    run = store.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    events = [e.model_dump(mode="json") for e in run.log.events if e.seq > since]
    return {"run_id": run.id, "status": run.status, "stage": run.stage,
            "last_seq": len(run.log.events), "events": events}


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
    return {"ok": True, "runs": len(store.all_runs()), "devices": len(store.all_devices())}
