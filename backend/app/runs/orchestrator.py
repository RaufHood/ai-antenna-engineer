"""The run state machine (DESIGN.md §5). This module — not the agent vendor —
owns the workflow: it services agent requests, enforces the simulation gate,
emits every progress event, and guarantees the run ends with a best-so-far
result even when barriers trip.

Loop contract: the agent is asked for one action at a time (AgentPort). The
only hard rule is the gate — no `done` is accepted for an unsimulated design;
the orchestrator simulates it and lets the evidence speak first."""
from __future__ import annotations

import asyncio
import os
import time

from app.agent.port import AgentPort, RunContext
from app.geometry.classify import Override, classify
from app.geometry.spec import make_anchors
from app.models import (Candidate, DoneRequest, EventType, IterationReport,
                        SimulateRequest, SpecRequest, SweepRequest,
                        WriteBuilderRequest)
from app.runs.store import Run
from app.sim import pool
from app.sim.score import build_report

MAX_WALL_CLOCK_S = 8 * 60          # crash barrier, not pacing (agent self-paces)
MAX_BATCH = 40                      # sanity cap per simulate/sweep request
# agent-side extraction: pip install bpy (~220 MB) + Blender load + reasoning
EXTRACT_TIMEOUT_S = float(os.environ.get("EXTRACT_TIMEOUT_S", "600"))


async def drive(run: Run, agent: AgentPort) -> None:
    try:
        await _drive(run, agent)
    except Exception as e:
        # never fail empty: agent-channel death degrades to best-so-far
        run.log.emit(run.stage, EventType.error, {"error": str(e)})
        ranking = _best_ranking(run)
        if ranking:
            run.truncated = True
            band = next(b for b in run.spec.requirements.bands
                        if b.id in run.band_ids)
            await _finish(run, band, ranking,
                          f"agent channel failed ({e}); best simulated design "
                          f"returned", agent)
        else:
            run.status = "failed"
            run.log.emit(run.stage, EventType.run_finished,
                         {"status": "failed", "error": str(e)})


async def _drive(run: Run, agent: AgentPort) -> None:
    band = next(b for b in run.spec.requirements.bands if b.id in run.band_ids)
    device = run.device
    ctx = RunContext(
        run_id=run.id, prompt=run.prompt, spec=run.spec, anchors=run.anchors,
        band_ids=run.band_ids,
        budget_note=f"~{MAX_WALL_CLOCK_S // 60} minutes wall clock for the design "
                    f"loop; simulate before concluding; spend it as you judge best.",
        extract_mode=run.extract_mode if device else "backend",
        blend_path=device.blend_path() if device else None,
        sidecar_path=device.sidecar_path() if device else None,
        geometry=device.geometry if device else None,
        ambiguities=list(run.ambiguities))

    if ctx.extract_mode == "agent":
        # ---- EXTRACT: the agent reads the build file itself (ADR-2) ----
        run.stage = "extract"
        run.log.emit("extract", EventType.stage_started, {
            "stage": "extract", "blend": ctx.blend_path.name if ctx.blend_path else None,
            "backend_extraction": {"n_parts": ctx.geometry["n_parts"],
                                   "size_mm": ctx.geometry["size_mm"]}})
        await agent.start(ctx)
        await _narrate(run, agent)
        try:
            action = await asyncio.wait_for(agent.next_action(None), EXTRACT_TIMEOUT_S)
        except asyncio.TimeoutError:
            action = None
            run.log.emit("extract", EventType.decision, {
                "decision": f"agent extraction exceeded {EXTRACT_TIMEOUT_S:.0f}s — "
                            f"backend extraction used"})
        await _narrate(run, agent)
        crosscheck = _accept_spec(run, action)
        ctx.spec, ctx.anchors, ctx.ambiguities = run.spec, run.anchors, list(run.ambiguities)
        ctx.meta["crosscheck"] = crosscheck
        _emit_spec(run)
        await agent.brief(ctx)
        await _narrate(run, agent)
    else:
        run.stage = "spec"
        run.log.emit("spec", EventType.stage_started, {"stage": "spec"})
        _emit_spec(run)
        await agent.start(ctx)
        await _narrate(run, agent)

    run.stage = "agent_loop"
    run.log.emit("agent_loop", EventType.stage_started, {"stage": "agent_loop"})
    t0 = time.time()

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

        elif isinstance(action, SpecRequest):  # late/duplicate spec (e.g. after timeout)
            report = _protocol_error(
                run, report,
                "spec already accepted (backend classification in effect); continue "
                "with simulate / sweep / done")

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


def _emit_spec(run: Run) -> None:
    run.log.emit(run.stage, EventType.artifact, {
        "name": "device_spec", "source": run.spec_source,
        "spec": run.spec.model_dump(),
        "anchors": [a.model_dump() for a in run.anchors],
        "ambiguities": run.ambiguities})


def _accept_spec(run: Run, action) -> str:
    """Merge the agent's `spec` judgment into the backend extraction (facts)
    and cross-check the two extractions. Returns the note sent back with the
    design brief. Backend classification is the fallback in every branch —
    never block a run on the agent's reading of the file."""
    device = run.device
    assert device is not None and device.geometry is not None
    base = classify(device.geometry, run.band_ids)
    if not isinstance(action, SpecRequest):
        run.spec_source = "agent+backend-fallback"
        note = ("No `spec` action received from the agent; backend extraction + "
                "heuristic classification are in effect.")
        run.log.emit("extract", EventType.decision, {"decision": note})
        return note

    ov = {c.name: Override(em=c.em, role=c.role, epsilon_r=c.epsilon_r, note=c.note)
          for c in action.components}
    merged = classify(device.geometry, run.band_ids, ov, action.ground)
    run.spec, run.anchors, run.ambiguities = merged.spec, make_anchors(merged.spec), merged.ambiguities
    run.spec_source = "agent"

    lines = []
    ext = action.extracted or {}
    method = ext.get("method", "unknown")
    if method == "failed":
        lines.append("Your extraction failed; the backend ran the same script "
                     "successfully — its geometry is used, your classification "
                     "overrides applied where names matched.")
    else:
        ours = device.geometry
        size_ok = n_ok = None
        if isinstance(ext.get("size_mm"), list) and len(ext["size_mm"]) == 3:
            size_ok = all(abs(float(a) - b) <= 0.02 * max(b, 1.0)
                          for a, b in zip(ext["size_mm"], ours["size_mm"]))
        if isinstance(ext.get("n_parts"), int):
            n_ok = ext["n_parts"] == ours["n_parts"]
        if size_ok and n_ok is not False:
            lines.append(f"Cross-check: your extraction ({method}) agrees with the "
                         f"backend's ({ours['n_parts']} parts, {ours['size_mm']} mm).")
        elif size_ok is None and n_ok is None:
            lines.append("Cross-check: no size/part count reported; backend geometry used.")
        else:
            lines.append(f"Cross-check MISMATCH: you reported size {ext.get('size_mm')} / "
                         f"{ext.get('n_parts')} parts, backend has {ours['size_mm']} / "
                         f"{ours['n_parts']}. Backend geometry is authoritative; "
                         f"flag it if you disagree.")
    changed = []
    by_name = {c.name: c for c in base.spec.components}
    for c in merged.spec.components:
        b = by_name.get(c.name)
        if b and (b.em != c.em or b.role != c.role or b.epsilon_r != c.epsilon_r):
            changed.append(f"{c.name}: {b.em}/{b.role} -> {c.em}/{c.role}")
    if action.ground and action.ground != next(
            c.name for c in base.spec.components if c.role == "ground"):
        changed.append(f"ground reference -> {action.ground}")
    lines.append(f"Applied {len(changed)} classification override(s)"
                 + (": " + "; ".join(changed) if changed else "."))
    note = " ".join(lines)
    run.log.emit("extract", EventType.decision, {
        "decision": "spec accepted", "crosscheck": note, "overrides": changed,
        "agent_summary": action.summary, "extracted": ext})
    return note


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
