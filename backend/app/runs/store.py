"""In-memory registries for runs and devices. Deliberately dicts for the
hackathon; this module is the interface to change if that ever needs more.
Device artifacts (geometry.json, glb, STLs) live on disk under var/devices."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.models import Anchor, Candidate, DeviceSpec, IterationReport, SimResult
from app.runs.events import EventLog


@dataclass
class Device:
    id: str
    name: str
    dir: Path
    status: str = "extracting"       # extracting | ready | failed
    geometry: dict | None = None     # raw extraction output (facts)
    spec: DeviceSpec | None = None   # backend classification (judgment, heuristic)
    anchors: list[Anchor] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None

    def artifacts(self) -> list[str]:
        out = self.dir / "out"
        names = [n for n in ("geometry.json", "device.glb") if (out / n).exists()]
        if (self.dir / "materials.json").exists():
            names.append("materials.json")
        names += sorted(f"parts/{p.name}" for p in (out / "parts").glob("*.stl")) \
            if (out / "parts").exists() else []
        return names

    def blend_path(self) -> Path | None:
        return next(self.dir.glob("*.blend"), None)

    def sidecar_path(self) -> Path | None:
        p = self.dir / "materials.json"
        return p if p.exists() else None


@dataclass
class Run:
    id: str
    prompt: str
    band_ids: list[str]
    spec: DeviceSpec
    anchors: list[Anchor]
    device: Device | None = None
    extract_mode: str = "backend"    # agent | backend (DESIGN.md §8)
    created_at: float = field(default_factory=time.time)
    status: str = "running"          # running | finished | failed | stopped
    stage: str = "ingest"
    iteration: int = 0
    truncated: bool = False
    ambiguities: list[str] = field(default_factory=list)
    spec_source: str = "canned"      # canned | backend | agent | agent+backend-fallback
    candidates: dict[str, Candidate] = field(default_factory=dict)
    results: dict[str, SimResult] = field(default_factory=dict)
    reports: list[IterationReport] = field(default_factory=list)
    final: dict | None = None
    inbox: list[str] = field(default_factory=list)   # user notes for the agent
    # Render the visual evidence for THIS run after it concludes: the per-band
    # placement maps, the winner drawn inside the real mesh, its S11, and the
    # field leaving it. Opt-in because the field animation costs an openEMS
    # solve; everything cheaper still lands first.
    media: bool = False
    media_artifacts: list[dict] = field(default_factory=list)
    finished_at: float | None = None
    log: EventLog = None  # type: ignore[assignment]
    task: asyncio.Task | None = None

    def __post_init__(self) -> None:
        self.log = EventLog(self.id)


_runs: dict[str, Run] = {}
_devices: dict[str, Device] = {}


def put(run: Run) -> None:
    _runs[run.id] = run


def get(run_id: str) -> Run | None:
    return _runs.get(run_id)


def all_runs() -> list[Run]:
    return list(_runs.values())


def put_device(d: Device) -> None:
    _devices[d.id] = d


def get_device(device_id: str) -> Device | None:
    return _devices.get(device_id)


def all_devices() -> list[Device]:
    return list(_devices.values())
