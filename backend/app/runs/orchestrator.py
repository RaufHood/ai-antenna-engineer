"""The run state machine (DESIGN.md §5). This module — not the agent vendor —
owns the workflow: it services agent requests, enforces the simulation gate,
emits every progress event, and guarantees the run ends with a best-so-far
result even when barriers trip.

Loop contract: the agent is asked for one action at a time (AgentPort). The
only hard rule is the gate — no `done` is accepted for an unsimulated design;
the orchestrator simulates it and lets the evidence speak first."""
from __future__ import annotations

import asyncio
import time

from app.agent.port import AgentPort, RunContext
from app.models import (Candidate, DoneRequest, EventType, IterationReport,
                        SimulateRequest, SweepRequest, WriteBuilderRequest)
from app.runs.store import Run
from app.sim import pool
from app.sim.score import build_report

MAX_WALL_CLOCK_S = 8 * 60          # crash barrier, not pacing (agent self-paces)
MAX_BATCH = 40                      # sanity cap per simulate/sweep request


async def drive(run: Run, agent: AgentPort) -> None:
    try:
        await _drive(run, agent)
    except Exception as e:
        run.status = "failed"
        run.log.emit(run.stage, EventType.error, {"error": str(e)})
        run.log.emit(run.stage, EventType.run_finished,
                     {"status": "failed", "error": str(e)})


async def _drive(run: Run, agent: AgentPort) -> None:
    t0 = time.time()
    band = next(b for b in run.spec.requirements.bands if b.id in run.band_ids)

    run.stage = "spec"
    run.log.emit("spec", EventType.stage_started, {"stage": "spec"})
    run.log.emit("spec", EventType.artifact, {
        "name": "device_spec", "spec": run.spec.model_dump(),
        "anchors": [a.model_dump() for a in run.anchors]})

    ctx = RunContext(
        run_id=run.id, prompt=run.prompt, spec=run.spec, anchors=run.anchors,
        band_ids=run.band_ids,
        budget_note=f"~{MAX_WALL_CLOCK_S // 60} minutes wall clock; simulate "
                    f"before concluding; spend the budget as you judge best.")
    await agent.start(ctx)
    await _narrate(run, agent)

    run.stage = "agent_loop"
    run.log.emit("agent_loop", EventType.stage_started, {"stage": "agent_loop"})

    report: IterationReport | None = None
    history_best: list[float] = []

    while True:
        if time.time() - t0 > MAX_WALL_CLOCK_S:
            run.truncated = True
            run.log.emit("agent_loop", EventType.decision,
                         {"decision": "wall-clock barrier tripped"})
            await _finish(run, band, _best_ranking(run), 
                          "wall-clock barrier: returning best-so-far", agent)
            return

        action = await agent.next_action(report)
        await _narrate(run, agent)

        if isinstance(action, SimulateRequest):
            cands = action.candidates[:MAX_BATCH]
            run.iteration += 1
            for c in cands:
                run.candidates[c.candidate_id] = c
            run.log.emit("agent_loop", EventType.candidates_proposed, {
                "iteration": run.iteration,
                "candidates": [c.model_dump() for c in cands]})
            results = await _simulate_batch(run, band, cands)
            report = _score(run, band, results, history_best)

        elif isinstance(action, SweepRequest):
            base = run.candidates.get(action.candidate_id)
            if base is None:
                report = _protocol_error(
                    run, report, f"sweep references unknown candidate "
                                 f"{action.candidate_id!r}")
                continue
            variants: list[Candidate] = []
            v = action.start
            while v <= action.stop + 1e-9 and len(variants) < MAX_BATCH:
                cid = f"{base.candidate_id}__{action.param}={round(v, 2)}"
                if action.param == "length_mm":
                    c = base.model_copy(update={
                        "candidate_id": cid, "length_mm": round(v, 2)})
                else:
                    c = base.model_copy(update={
                        "candidate_id": cid,
                        "params": {**base.params, action.param: round(v, 2)}})
                variants.append(c)
                run.candidates[cid] = c
                v += action.step
            run.iteration += 1
            run.log.emit("agent_loop", EventType.candidates_proposed, {
                "iteration": run.iteration, "sweep": action.model_dump(by_alias=True),
                "candidates": [c.model_dump() for c in variants]})
            results = await _simulate_batch(run, band, variants)
            report = _score(run, band, results, history_best)

        elif isinstance(action, WriteBuilderRequest):
            report = _protocol_error(
                run, report,
                "write_builder is not available yet (M3); use existing builders: "
                "IFA, monopole")

        elif isinstance(action, DoneRequest):
            ranking = [cid for cid in action.ranking if cid in run.candidates]
            if not ranking:
                ranking = _best_ranking(run)
            # ---- the simulation gate ----
            top = ranking[0] if ranking else None
            if top and (top not in run.results
                        or run.results[top].status != "complete"):
                run.log.emit("agent_loop", EventType.decision, {
                    "decision": "gate: recommended design has no simulation on "
                                "record — simulating before accepting"})
                results = await _simulate_batch(
                    run, band, [run.candidates[top]])
                report = _score(run, band, results, history_best)
                continue  # agent sees the evidence and must conclude again
            await _finish(run, band, ranking, action.rationale, agent)
            return


async def _simulate_batch(run: Run, band, cands: list[Candidate]):
    results = {}
    async def one(c: Candidate):
        run.log.emit("agent_loop", EventType.sim_started,
                     {"candidate_id": c.candidate_id})
        r = await pool.solve_async(run.spec, band, c)
        run.results[c.candidate_id] = r
        results[c.candidate_id] = r
        run.log.emit("agent_loop", EventType.sim_result, r.model_dump())
    await asyncio.gather(*(one(c) for c in cands))
    return results


def _score(run: Run, band, results, history_best: list[float]) -> IterationReport:
    report = build_report(run.spec, band, run.iteration, run.candidates,
                          results, history_best)
    if report.reports:
        history_best.append(report.reports[0].score)
    run.reports.append(report)
    run.log.emit("agent_loop", EventType.iteration_scored, report.model_dump())
    return report


def _protocol_error(run: Run, report: IterationReport | None,
                    msg: str) -> IterationReport | None:
    run.log.emit("agent_loop", EventType.error, {"protocol": msg})
    if report is not None:
        return report.model_copy(update={"notes": [*report.notes, msg]})
    return IterationReport(iteration=run.iteration, reports=[],
                           best_so_far=None, trend="first_iteration",
                           notes=[msg])


def _best_ranking(run: Run) -> list[str]:
    done = [(cid, r) for cid, r in run.results.items() if r.status == "complete"]
    done.sort(key=lambda t: t[1].s11_min_db)
    return [cid for cid, _ in done[:5]]


async def _finish(run: Run, band, ranking: list[str], rationale: str,
                  agent: AgentPort) -> None:
    run.stage = "report"
    best = ranking[0] if ranking else None
    payload = {
        "ranking": ranking,
        "rationale": rationale,
        "truncated": run.truncated,
        "best": run.results[best].model_dump() if best else None,
        "best_candidate": run.candidates[best].model_dump() if best else None,
        "iterations": run.iteration,
        "total_sims": len(run.results),
    }
    run.final = payload
    run.status = "finished"
    run.log.emit("report", EventType.decision,
                 {"decision": "accepted", "rationale": rationale})
    run.log.emit("report", EventType.run_finished, payload)
    await agent.close("finished")


async def _narrate(run: Run, agent: AgentPort) -> None:
    for line in await agent.narrate():
        run.log.emit(run.stage, EventType.agent_message,
                     {"role": "agent", "text": line})
