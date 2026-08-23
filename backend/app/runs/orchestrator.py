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
from app.geometry.spec import clearance_at, make_anchors
from app.models import (BandRequirement, Candidate, DoneRequest, EventType,
                        IterationReport, SimulateRequest, SpecRequest,
                        SweepRequest, WriteBuilderRequest)
from app.runs.store import Run
from app.sim import pool
from app.sim.score import build_report

MAX_WALL_CLOCK_S = 8 * 60          # crash barrier, not pacing (agent self-paces)
# cap per simulate/sweep request: 40 is fine for the ms-per-solve reference
# oracle; set MAX_BATCH=8 or so when an FDTD engine (minutes per solve) is wired
MAX_BATCH = int(os.environ.get("MAX_BATCH", "40"))
# agent-side extraction: pip install bpy (~220 MB) + Blender load + reasoning
EXTRACT_TIMEOUT_S = float(os.environ.get("EXTRACT_TIMEOUT_S", "600"))
# Two-tier solver strategy (integration plan §6): SIM_SOLVER (the fast oracle,
# by default) drives the whole in-loop search unchanged; if CONFIRM_SOLVER is
# also set, the agent's WINNER only is re-solved once with it after the loop
# concludes -- e.g. CONFIRM_SOLVER=app.sim.rf_adapter:solve for a one-shot
# real-openEMS-FDTD confirmation of a design the fast oracle found. Unset by
# default (opt-in); never a gate -- failure degrades to a note, same as the
# agent's own structured_output addendum.
CONFIRM_SOLVER = os.environ.get("CONFIRM_SOLVER")


async def drive(run: Run, agent: AgentPort) -> None:
    try:
        await _drive(run, agent)
    except Exception as e:
        run.log.emit(run.stage, EventType.error, {"error": str(e)})
        ranking = _best_ranking(run)
        if ranking:
            # never fail empty: agent-channel death degrades to best-so-far
            run.truncated = True
            await _finish(run, ranking,
                          f"agent channel failed ({e}); best simulated design "
                          f"returned", agent)
            return
        if type(agent).__name__ != "MockAgent":
            # nothing simulated yet -> the heuristic agent finishes the run
            # (DESIGN.md §6.3/§10): the demo always ends with a result
            from app.agent.mock import MockAgent
            run.log.emit(run.stage, EventType.decision, {
                "decision": f"agent channel failed before any simulation ({e}); "
                            f"falling back to the built-in heuristic agent"})
            run.spec_source += "+mock-fallback"
            try:
                await agent.close("agent failure — mock fallback")
            except Exception:
                pass
            await drive(run, MockAgent())
            return
        run.status = "failed"
        run.log.emit(run.stage, EventType.run_finished,
                     {"status": "failed", "error": str(e)})


async def _drive(run: Run, agent: AgentPort) -> None:
    device = run.device
    # a mock taking over after the spec was accepted must not re-extract
    do_extract = (device is not None and run.extract_mode == "agent"
                  and run.spec_source.startswith("backend"))
    ctx = RunContext(
        run_id=run.id, prompt=run.prompt, spec=run.spec, anchors=run.anchors,
        band_ids=run.band_ids,
        budget_note=f"~{MAX_WALL_CLOCK_S // 60} minutes wall clock for the design "
                    f"loop; simulate before concluding; spend it as you judge best.",
        extract_mode="agent" if do_extract else "backend",
        blend_path=device.blend_path() if device else None,
        sidecar_path=device.sidecar_path() if device else None,
        geometry=device.geometry if device else None,
        ambiguities=list(run.ambiguities))

    if do_extract:
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

    _note_tape_mismatch(run, ctx)

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
            await _finish(run, _best_ranking(run),
                          "wall-clock barrier: returning best-so-far", agent)
            return

        report = _with_user_notes(run, report)
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
            results = await _simulate_batch(run, cands)
            report = _score(run, results, history_best)

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
            results = await _simulate_batch(run, variants)
            report = _score(run, results, history_best)

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
                results = await _simulate_batch(run, [run.candidates[top]])
                report = _score(run, results, history_best)
                continue  # agent sees the evidence and must conclude again
            await _finish(run, ranking, action.rationale, agent)
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
    merged = classify(device.geometry, run.band_ids, ov, action.ground,
                      geometry_path=str(device.dir / "out" / "geometry.json"))
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


def band_for(run: Run, cand: Candidate) -> BandRequirement:
    """Each candidate is simulated against its own band (multi-band runs);
    unknown band_id falls back to the run's first band."""
    bands = {b.id: b for b in run.spec.requirements.bands}
    if cand.band_id in bands and cand.band_id in run.band_ids:
        return bands[cand.band_id]
    return next(b for b in run.spec.requirements.bands if b.id in run.band_ids)


def _with_user_notes(run: Run, report: IterationReport | None) -> IterationReport | None:
    """Mid-run user feedback (POST /runs/{id}/messages) rides along with the
    next evidence message — no extra agent turn, no rate-limit exposure."""
    if not run.inbox:
        return report
    notes = [f"NOTE FROM THE USER: {t}" for t in run.inbox]
    run.inbox.clear()
    if report is None:
        return IterationReport(iteration=run.iteration, reports=[], best_so_far=None,
                               trend="first_iteration", notes=notes)
    return report.model_copy(update={"notes": [*report.notes, *notes]})


async def _simulate_batch(run: Run, cands: list[Candidate]):
    results = {}
    async def one(c: Candidate):
        run.log.emit("agent_loop", EventType.sim_started,
                     {"candidate_id": c.candidate_id, "band_id": c.band_id})
        band = band_for(run, c)
        r = await pool.solve_async(run.spec, band, c)
        # The solve measures S11 and efficiency; the keep-out is geometry and
        # the solver has no opinion on it. Stamp the geometric verdict here,
        # before the result is stored or emitted, so the event log, the report
        # and the UI all state one verdict — rather than an electrical pass
        # that reads as "all requirements met" while the radiator sits 12.6 mm
        # from a steel speaker under a 14 mm keep-out.
        gap, _blocker = clearance_at(run.spec, c.position_mm)
        r.clearance_mm = round(gap, 1)
        r.meets_clearance = gap >= band.clearance_mm
        run.results[c.candidate_id] = r
        results[c.candidate_id] = r
        run.log.emit("agent_loop", EventType.sim_result, r.model_dump())
    await asyncio.gather(*(one(c) for c in cands))
    return results


def _note_tape_mismatch(run: Run, ctx) -> None:
    """A replayed transcript reasons about the device it was recorded on.

    The solver re-runs against the device actually loaded, so every number is
    live — but the agent's words are not, and a recording that talks about a
    different phone's anchors would read as if it were about this one. Mark the
    run's provenance so the UI can label the transcript instead of passing it
    off. Same channel as the mock-fallback banner: provenance belongs in
    spec_source, not in the agent's mouth.
    """
    was = ctx.meta.get("tape_device")
    if not was:
        return
    run.spec_source += "+tape-other-device"
    run.log.emit("spec", EventType.decision, {
        "decision": f"Replaying {ctx.meta.get('tape_name', 'a tape')}, recorded "
                    f"against {was}. Every result below is re-solved against "
                    f"{run.spec.name}; the agent's commentary is the recording's."})


def _score(run: Run, results, history_best: list[float]) -> IterationReport:
    report = build_report(run.spec, lambda c: band_for(run, c), run.iteration,
                          run.candidates, results, history_best)
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


async def _finish(run: Run, ranking: list[str], rationale: str,
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
        "spec_source": run.spec_source,
    }
    run.final = payload
    run.status = "finished"
    run.finished_at = time.time()
    run.log.emit("report", EventType.decision,
                 {"decision": "accepted", "rationale": rationale})
    run.log.emit("report", EventType.run_finished, payload)

    if CONFIRM_SOLVER and best:
        await _confirm_winner(run, best)

    # the agent's own structured report arrives on its schedule; it is an
    # addendum artifact, never a gate on run_finished
    try:
        agent_report = await agent.close("finished")
    except Exception as e:
        agent_report = None
        run.log.emit("report", EventType.error, {"error": f"agent close: {e}"})
    if agent_report:
        run.final["agent_report"] = agent_report
        run.log.emit("report", EventType.artifact,
                     {"name": "agent_report", "report": agent_report})
    run.log.emit("report", EventType.artifact, {
        "name": "report.md", "url": f"/runs/{run.id}/artifacts/report.md"})

    if run.media:
        await _render_media(run)


async def _render_media(run: Run) -> None:
    """Draw this run's evidence — after run_finished, never before.

    Same contract as _confirm_winner: the study is already complete and
    reported, so a missing renderer, a missing openEMS or a slow field solve
    costs the gallery an image, never the run. Each artifact is announced the
    moment it lands, so the placement maps appear while the field is still
    solving instead of everything arriving at the end.
    """
    from app.runs import media as media_mod

    run.stage = "media"
    run.log.emit("media", EventType.stage_started,
                 {"stage": "media", "bands": list(run.band_ids)})

    def announce(art) -> None:
        item = {"name": art.name, "kind": art.kind, "title": art.title,
                "caption": art.caption, "band_id": art.band_id,
                "url": f"/runs/{run.id}/media/{art.name}"}
        run.media_artifacts.append(item)
        run.log.emit("media", EventType.artifact, item)

    try:
        made = await media_mod.render(run, with_field=True, on_artifact=announce)
    except Exception as e:
        run.log.emit("media", EventType.error, {"error": f"media render: {e}"})
        run.stage = "report"
        return
    if not made:
        run.log.emit("media", EventType.decision, {
            "decision": "no media rendered — the renderer venv (.venv-viz) or a "
                        "winning candidate was missing; the study itself is "
                        "unaffected"})
    # Leave the media stage explicitly: the UI keeps polling while it is set,
    # because `running` went false back when the study concluded.
    run.stage = "report"
    run.log.emit("report", EventType.decision,
                 {"decision": f"evidence rendered: {len(made)} artifact(s)"})


async def _confirm_winner(run: Run, best: str) -> None:
    """One real-solver confirmation of the agent's already-decided winner
    (integration plan §6) -- runs after run_finished, never before: it must
    never gate or slow down the in-loop search, only add evidence to the
    report. Failure (no rf/.venv on this machine, solver crash/timeout)
    degrades to a note in the artifact, the same way a missing agent_report
    degrades today -- it is never allowed to fail the run."""
    cand = run.candidates[best]
    run.log.emit("report", EventType.decision, {
        "decision": f"confirming winner {best!r} against CONFIRM_SOLVER={CONFIRM_SOLVER}"})
    result = await pool.solve_with(CONFIRM_SOLVER, run.spec, band_for(run, cand), cand)
    run.final["openems_confirmation"] = result.model_dump()
    run.log.emit("report", EventType.artifact, {
        "name": "openems_confirmation", "candidate_id": best,
        "result": result.model_dump()})


async def _narrate(run: Run, agent: AgentPort) -> None:
    for line in await agent.narrate():
        run.log.emit(run.stage, EventType.agent_message,
                     {"role": "agent", "text": line})
