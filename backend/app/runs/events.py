"""Append-only per-run event log with WS fan-out. Replayable via `since`:
a reconnecting client passes the last seq it saw and misses nothing —
a dropped socket must never kill a demo (DESIGN.md §5)."""
from __future__ import annotations

import asyncio
import time

from app.models import EventType, RunEvent


class EventLog:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[RunEvent] = []
        self._subs: set[asyncio.Queue[RunEvent]] = set()

    def emit(self, stage: str, type_: EventType, payload: dict) -> RunEvent:
        ev = RunEvent(run_id=self.run_id, seq=len(self.events) + 1,
                      ts=time.time(), stage=stage, type=type_, payload=payload)
        self.events.append(ev)
        for q in list(self._subs):
            q.put_nowait(ev)
        return ev

    def subscribe(self, since: int = 0) -> tuple[list[RunEvent], asyncio.Queue[RunEvent]]:
        """Returns (backlog from seq>since, live queue). Subscribe BEFORE
        consuming backlog so no event can fall between the two."""
        q: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._subs.add(q)
        return [e for e in self.events if e.seq > since], q

    def unsubscribe(self, q: asyncio.Queue[RunEvent]) -> None:
        self._subs.discard(q)
