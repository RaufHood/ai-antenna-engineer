"""In-memory run registry. Deliberately a dict for the hackathon; this module
is the interface to change if that ever needs to be more."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.models import Anchor, Candidate, DeviceSpec, IterationReport, SimResult
from app.runs.events import EventLog


@dataclass
class Run:
    id: str
    prompt: str
    band_ids: list[str]
    spec: DeviceSpec
    anchors: list[Anchor]
    created_at: float = field(default_factory=time.time)
    status: str = "running"          # running | finished | failed
    stage: str = "ingest"
    iteration: int = 0
    truncated: bool = False
    candidates: dict[str, Candidate] = field(default_factory=dict)
    results: dict[str, SimResult] = field(default_factory=dict)
    reports: list[IterationReport] = field(default_factory=list)
    final: dict | None = None
    log: EventLog = None  # type: ignore[assignment]
    task: asyncio.Task | None = None

    def __post_init__(self) -> None:
        self.log = EventLog(self.id)


_runs: dict[str, Run] = {}


def put(run: Run) -> None:
    _runs[run.id] = run


def get(run_id: str) -> Run | None:
    return _runs.get(run_id)


def all_runs() -> list[Run]:
    return list(_runs.values())
