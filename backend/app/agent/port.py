"""The agent seam (DESIGN.md §4.1). The orchestrator drives ANY agent through
this request/response contract; Devin's async message stream is adapted to it
inside DevinAgent. Keeping the seam this narrow is what makes the mock a
drop-in and the workflow fully controlled by OUR code, not the vendor's."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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
    # agent-side extraction (DESIGN.md §8): the build file goes to the agent,
    # which must answer with a `spec` action before the design brief is sent
    extract_mode: str = "backend"          # agent | backend
    blend_path: Path | None = None
    sidecar_path: Path | None = None
    geometry: dict | None = None           # backend extraction (facts) if any
    ambiguities: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class AgentPort(Protocol):
    async def start(self, ctx: RunContext) -> None:
        """Open the session. backend mode: deliver spec, anchors, requirements,
        budget. agent mode: deliver the build file + extraction instructions;
        the spec follows via `brief` once the agent has answered with `spec`."""
        ...

    async def brief(self, ctx: RunContext) -> None:
        """Deliver the design brief (final spec + anchors + requirements) after
        an agent-side extraction. No-op for backend mode."""
        ...

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        """Deliver the previous iteration's evidence (None on the first call)
        and return the agent's next request. Blocks while the agent thinks."""
        ...

    async def narrate(self) -> list[str]:
        """Drain any human-readable agent commentary since the last call."""
        ...

    async def close(self, reason: str) -> dict | None:
        """End the session. Returns the agent's own final structured report
        if it produced one (Devin: structured_output), else None."""
        ...
