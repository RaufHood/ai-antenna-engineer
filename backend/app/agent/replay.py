"""Record a real Devin run once; replay it forever.

Devin costs money and quota, and a live session takes ~2.5 minutes of which
~98% is the model thinking. Neither is a good fit for a demo you want to run
repeatedly, or for a laptop with no credit left — but the built-in heuristic
`MockAgent` is not a substitute either: it produces plausible numbers with
none of Devin's reasoning, which is precisely the part worth showing.

So: wrap the real agent once, write every turn to a tape, and replay that tape
afterwards. What comes back is Devin's actual decisions and actual prose, at
zero cost and zero latency.

    # once, with quota:
    AGENT=devin RECORD_TAPE=var/tapes/wifi24.json python scripts/dev_run.py

    # forever after:
    AGENT=replay REPLAY_TAPE=var/tapes/wifi24.json python scripts/dev_run.py

The tape is a list of turns in call order. Replay is strict about that order —
the orchestrator is deterministic given the same spec, so a mismatch means the
inputs changed and the tape no longer describes this run. It says so instead
of quietly serving the wrong answer, which is the failure mode that makes
recorded demos untrustworthy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.port import AgentPort, RunContext
from app.models import AgentRequest, IterationReport

TAPE_VERSION = 1


def _dump(obj: Any) -> Any:
    """pydantic -> plain JSON, leaving anything already plain alone."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


class RecordingAgent:
    """Passes every call through to `inner` and writes the answers to a tape."""

    def __init__(self, inner: AgentPort, tape_path: str | Path) -> None:
        self.inner = inner
        self.path = Path(tape_path)
        self.turns: list[dict] = []
        self._meta: dict = {"version": TAPE_VERSION}

    # ---------------------------------------------------------- AgentPort --

    async def start(self, ctx: RunContext) -> None:
        self._meta |= {
            "run_prompt": ctx.prompt,
            "band_ids": list(ctx.band_ids),
            "device": ctx.spec.name,
            "n_anchors": len(ctx.anchors),
            "agent": type(self.inner).__name__,
        }
        await self.inner.start(ctx)
        self._flush()

    async def brief(self, ctx: RunContext) -> None:
        await self.inner.brief(ctx)

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        action = await self.inner.next_action(report)
        self.turns.append({"kind": "action", "action": _dump(action)})
        self._flush()                    # after every turn: a crash mid-run
        return action                    # still leaves a usable partial tape

    async def narrate(self) -> list[str]:
        lines = await self.inner.narrate()
        if lines:
            self.turns.append({"kind": "narrate", "lines": list(lines)})
            self._flush()
        return lines

    async def close(self, reason: str) -> dict | None:
        out = await self.inner.close(reason)
        self.turns.append({"kind": "close", "reason": reason, "report": _dump(out)})
        self._flush()
        return out

    # --------------------------------------------------------------------- --

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({**self._meta, "turns": self.turns}, indent=1),
            encoding="utf-8",
        )


def _parse_action(raw: dict) -> AgentRequest:
    """dict -> the right AgentRequest member, by its `action` discriminator.

    Explicit rather than a pydantic union parse because SweepRequest aliases
    from/to (populate_by_name), and a union would happily coerce a malformed
    tape into the wrong member instead of failing.
    """
    from app.models import (DoneRequest, SimulateRequest, SpecRequest,
                            SweepRequest, WriteBuilderRequest)
    by_action = {
        "simulate": SimulateRequest, "sweep": SweepRequest,
        "write_builder": WriteBuilderRequest, "done": DoneRequest,
        "spec": SpecRequest,
    }
    action = raw.get("action")
    model = by_action.get(action)
    if model is None:
        raise ValueError(f"tape holds unknown action {action!r}; "
                         f"expected one of {sorted(by_action)}")
    return model.model_validate(raw)


class ReplayAgent:
    """Plays a recorded tape back through the same seam, instantly."""

    def __init__(self, tape_path: str | Path) -> None:
        self.path = Path(tape_path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"no tape at {self.path}. Record one first: "
                f"AGENT=devin RECORD_TAPE={self.path} python scripts/dev_run.py"
            )
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        if doc.get("version") != TAPE_VERSION:
            raise ValueError(f"{self.path}: tape version {doc.get('version')}, "
                             f"this build reads {TAPE_VERSION}")
        self.meta = doc
        self.turns: list[dict] = doc["turns"]
        self._i = 0

    def _take(self, kind: str) -> dict | None:
        """Next turn of this kind, or None once the tape runs out.

        `narrate` is optional — the orchestrator calls it opportunistically —
        so a missing one is not an error; a missing `action` is.
        """
        while self._i < len(self.turns):
            turn = self.turns[self._i]
            if turn["kind"] == kind:
                self._i += 1
                return turn
            if kind == "action" and turn["kind"] == "narrate":
                self._i += 1            # skip narration the caller didn't drain
                continue
            return None
        return None

    async def start(self, ctx: RunContext) -> None:
        recorded = self.meta.get("band_ids")
        if recorded and list(ctx.band_ids) != recorded:
            raise ValueError(
                f"tape {self.path.name} was recorded for bands {recorded}, "
                f"this run asks for {list(ctx.band_ids)} — the decisions on it "
                f"do not describe this run"
            )
        # The device is not fatal the way the band is — the loop still runs and
        # the solver still re-solves every candidate live, so the numbers on
        # screen are this device's. What does not carry over is the agent's
        # prose: a transcript reasoning about "the 5 legal anchors on the right
        # edge" of one phone must never be shown as if it were about another.
        # Record the mismatch so the run can say so instead of implying it.
        was = self.meta.get("device")
        if was and was != ctx.spec.name:
            ctx.meta["tape_device"] = was
            ctx.meta["tape_name"] = self.path.name

    async def brief(self, ctx: RunContext) -> None:
        return None

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        turn = self._take("action")
        if turn is None:
            raise RuntimeError(
                f"tape {self.path.name} ran out of turns after {self._i}. "
                f"It was recorded against a different spec, or the loop "
                f"diverged; re-record rather than trusting this."
            )
        return _parse_action(turn["action"])

    async def narrate(self) -> list[str]:
        turn = self._take("narrate")
        return list(turn["lines"]) if turn else []

    async def close(self, reason: str) -> dict | None:
        turn = self._take("close")
        return turn.get("report") if turn else None
