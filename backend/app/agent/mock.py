"""Heuristic stand-in for Devin. Not a toy: it follows the same protocol,
reads the same evidence layers, and uses the same request vocabulary, so the
orchestrator cannot tell the difference. Demo insurance (DESIGN.md §10) and
the M0 development driver.

Strategy: propose IFA+monopole on the clearest anchors at lambda/4; read the
hint layer and sweep length on the best candidate; if the best is an IFA and
R is off 50 ohm, sweep the feed-short gap; then conclude."""
from __future__ import annotations

from app.geometry.classify import classify
from app.geometry.spec import clearance_at
from app.models import (AgentRequest, Candidate, DoneRequest, IterationReport,
                        SimulateRequest, SpecComponent, SpecRequest, SweepRequest)
from app.agent.port import RunContext

C_MM_GHZ = 299.792458  # c in mm*GHz


def _vol(b) -> float:
    (x0, y0, z0), (x1, y1, z1) = b
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


class MockAgent:
    def __init__(self) -> None:
        self.ctx: RunContext | None = None
        self.turn = 0
        self.last: IterationReport | None = None
        self.cands: dict[str, Candidate] = {}
        self._story: list[str] = []
        self._swept_gap = False
        self._spec_pending = False

    async def start(self, ctx: RunContext) -> None:
        self.ctx = ctx
        if ctx.extract_mode == "agent" and ctx.geometry:
            # "reads the build file": same script output Devin would produce
            self._spec_pending = True
            self._story.append(
                f"Extracted {ctx.blend_path.name if ctx.blend_path else 'build file'}: "
                f"{ctx.geometry['n_parts']} parts, {ctx.geometry['size_mm']} mm.")
        else:
            self._story.append(
                f"Read spec for {ctx.spec.name}: {len(ctx.spec.components)} components, "
                f"{len(ctx.anchors)} candidate anchors. Target band(s): {ctx.band_ids}.")

    async def brief(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self._story.append(
            f"Design brief received: {len(ctx.spec.components)} components, "
            f"{len(ctx.anchors)} anchors, bands {ctx.band_ids}.")

    def _spec(self) -> SpecRequest:
        ctx = self.ctx
        assert ctx is not None and ctx.geometry is not None
        c = classify(ctx.geometry, ctx.band_ids)
        metal = sorted((x for x in c.spec.components if x.em in ("pec", "lossy_metal")
                        and x.role in ("battery", "module", "shield")),
                       key=lambda x: -_vol(x.bbox_mm))[:8]
        self._story.append(
            f"Classified {len(c.spec.components)} parts; ground reference "
            f"{next(x.name for x in c.spec.components if x.role == 'ground')}; "
            f"{len(metal)} metal blocks to keep clear of.")
        return SpecRequest(
            action="spec",
            extracted={"method": "script", "n_parts": ctx.geometry["n_parts"],
                       "size_mm": ctx.geometry["size_mm"]},
            ground=next(x.name for x in c.spec.components if x.role == "ground"),
            components=[SpecComponent(name=x.name, em=x.em, role=x.role,
                                      epsilon_r=x.epsilon_r)
                        for x in c.spec.components if x.em_source != "sidecar"],
            summary=f"{c.spec.name}: {c.spec.board.size_mm[0]:.0f} x "
                    f"{c.spec.board.size_mm[1]:.0f} x {c.spec.board.size_mm[2]:.1f} mm; "
                    f"metal blocks: {', '.join(x.label for x in metal) or 'none'}.")

    async def next_action(self, report: IterationReport | None) -> AgentRequest:
        if self._spec_pending:
            self._spec_pending = False
            return self._spec()
        self.last = report
        self.turn += 1
        if report is None:
            return self._propose()
        best = self._best()
        if best is None:
            return DoneRequest(action="done", ranking=[], rationale="all sims failed")
        if self.turn == 2:
            return self._sweep_length(best)
        if self.turn == 3 and best.antenna_type == "IFA" and not self._swept_gap:
            top = report.reports[0]  # best-scored variant from the length sweep
            if top.result.status == "complete" and not all(d.passing for d in top.diffs):
                self._swept_gap = True
                return self._sweep_gap_on(top.candidate_id)
        return self._done()

    def _propose(self) -> SimulateRequest:
        ctx = self.ctx
        assert ctx is not None
        band = next(b for b in ctx.spec.requirements.bands if b.id in ctx.band_ids)
        quarter = C_MM_GHZ / band.f_mid_ghz / 4.0
        ranked = sorted(ctx.anchors,
                        key=lambda a: clearance_at(ctx.spec, a.pos_mm)[0],
                        reverse=True)
        out: list[Candidate] = []
        for a in ranked[:3]:
            clear, blocker = clearance_at(ctx.spec, a.pos_mm)
            for typ in ("IFA", "monopole"):
                cid = f"c{len(out):03d}_{typ.lower()}_{a.id}"
                cand = Candidate(
                    candidate_id=cid, anchor_id=a.id, band_id=band.id,
                    antenna_type=typ, position_mm=a.pos_mm, feed_point_mm=a.pos_mm,
                    length_mm=round(quarter, 1),
                    orientation="corner" if a.corner else "edge",
                    prior=round(min(clear / (2 * band.clearance_mm), 1.0), 2),
                    rationale=f"{a.label}: {clear:.0f} mm to {blocker or 'nothing'}; "
                              f"start at lambda/4 = {quarter:.1f} mm",
                    params={"gap_mm": 5.0} if typ == "IFA" else {})
                self.cands[cid] = cand
                out.append(cand)
        self._story.append(
            f"Proposing {len(out)} candidates on the {len(ranked[:3])} clearest anchors "
            f"(IFA + monopole each), lambda/4 start.")
        return SimulateRequest(action="simulate", candidates=out)

    def _best(self) -> Candidate | None:
        if not self.last or not self.last.reports:
            return None
        for cr in self.last.reports:
            if cr.result.status == "complete":
                base = cr.candidate_id.split("__")[0]
                got = self.cands.get(cr.candidate_id) or self.cands.get(base)
                if got:
                    return got.model_copy(
                        update={"length_mm": self._current_length(cr.candidate_id)})
        return None

    def _current_length(self, cid: str) -> float:
        if "__length_mm=" in cid:
            return float(cid.split("__length_mm=")[1])
        base = self.cands.get(cid)
        return base.length_mm if base else 30.0

    def _sweep_length(self, best: Candidate) -> SweepRequest:
        centre = best.length_mm
        for cr in (self.last.reports if self.last else []):
            if cr.candidate_id.startswith(best.candidate_id):
                for h in cr.hints:
                    if "try length_mm ≈" in h:
                        centre = float(h.rsplit("≈", 1)[1].strip())
        self._story.append(
            f"Best so far {best.candidate_id}; sweeping length "
            f"{centre - 3:.1f}..{centre + 3:.1f} mm around the hint.")
        return SweepRequest(action="sweep", candidate_id=best.candidate_id,
                            param="length_mm", **{"from": round(centre - 3, 1),
                                                  "to": round(centre + 3, 1)},
                            step=0.5)

    def _sweep_gap_on(self, cid: str) -> SweepRequest:
        self._story.append(f"{cid}: match not closed — sweeping IFA feed-short gap.")
        return SweepRequest(action="sweep", candidate_id=cid,
                            param="gap_mm", **{"from": 2.0, "to": 10.0}, step=1.0)

    def _done(self) -> DoneRequest:
        assert self.last is not None
        ranking = [cr.candidate_id for cr in self.last.reports
                   if cr.result.status == "complete"][:5]
        top = self.last.reports[0]
        passing = all(d.passing for d in top.diffs)
        self._story.append(
            "Requirements met — concluding." if passing else
            "Budget spent; best available design selected (not all margins positive).")
        return DoneRequest(
            action="done", ranking=ranking,
            rationale=f"Top: {top.candidate_id} score {top.score} "
                      f"({'all requirements pass' if passing else 'best effort'}); "
                      f"trend {self.last.trend}.")

    async def narrate(self) -> list[str]:
        out, self._story = self._story, []
        return out

    async def close(self, reason: str) -> dict | None:
        if not self.last or not self.last.reports:
            return None
        top = self.last.reports[0]
        return {"status": "concluded", "current_best": top.candidate_id,
                "iterations_done": self.turn,
                "final": {"ranking": [cr.candidate_id for cr in self.last.reports[:3]],
                          "antenna_type": self.cands.get(
                              top.candidate_id.split("__")[0], top).antenna_type
                          if top.candidate_id.split("__")[0] in self.cands else "",
                          "position_summary": "", "rationale": "heuristic agent"}}
