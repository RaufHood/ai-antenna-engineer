"""The agent seam (DESIGN.md §4.1). The orchestrator drives ANY agent through
this request/response contract; Devin's async message stream is adapted to it
inside DevinAgent. Keeping the seam this narrow is what makes the mock a
drop-in and the workflow fully controlled by OUR code, not the vendor's."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import AgentRequest, Anchor, DeviceSpec, IterationReport


@dataclass
class RunContext:
    run_id: str
    prompt: str
    spec: DeviceSpec
    anchors: list[Anchor]
    band_ids: list[str]
    budget_note: str = ""
    meta: dict = field(default_factory=dict)


class AgentPort(Protocol):
    async def start(self, ctx: RunContext) -> None:
        """Open the session; deliver spec, anchors, requirements, budget."""
        ...

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        """Deliver the previous iteration's evidence (None on the first call)
        and return the agent's next request. Blocks while the agent thinks."""
        ...

    async def narrate(self) -> list[str]:
        """Drain any human-readable agent commentary since the last call."""
        ...

    async def close(self, reason: str) -> None:
        ...
