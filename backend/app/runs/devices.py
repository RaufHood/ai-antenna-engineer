"""Device lifecycle: upload -> extraction (shared script) -> classification ->
anchors. Used by the HTTP layer and the dev driver alike."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.geometry import extract as ex
from app.geometry.classify import classify
from app.geometry.spec import make_anchors
from app.runs import store
from app.runs.store import Device


def register(blend: Path, sidecar: Path | None) -> Device:
    """Ingest the files and register the device; extraction runs separately
    (`await prepare(device)`) so callers choose sync vs background."""
    device_id = ex.device_id_for(blend)
    if (d := store.get_device(device_id)) is not None:
        return d
    d = Device(id=device_id, name=blend.stem, dir=ex.ingest(blend, sidecar, device_id))
    store.put_device(d)
    return d


async def prepare(device: Device, band_ids: list[str] | None = None) -> Device:
    if device.status == "ready":
        return device
    try:
        device.geometry = await ex.extract(device.dir)
        c = classify(device.geometry, band_ids,
                     geometry_path=str(device.dir / "out" / "geometry.json"))
        device.spec, device.ambiguities = c.spec, c.ambiguities
        device.anchors = make_anchors(device.spec)
        device.name = device.spec.name
        device.status = "ready"
    except Exception as e:
        device.status, device.error = "failed", str(e)
    return device


def snapshot(d: Device) -> dict:
    return {
        "device_id": d.id, "name": d.name, "status": d.status, "error": d.error,
        "spec": d.spec.model_dump() if d.spec else None,
        "anchors": [a.model_dump() for a in d.anchors],
        "ambiguities": d.ambiguities,
        "size_mm": d.geometry["size_mm"] if d.geometry else None,
        "n_parts": d.geometry["n_parts"] if d.geometry else None,
        "frame": d.geometry.get("frame") if d.geometry else None,
        "artifacts": d.artifacts(),
    }


async def prepare_background(device: Device) -> None:
    if device.task is None and device.status == "extracting":
        device.task = asyncio.create_task(prepare(device))
