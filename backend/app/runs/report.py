"""Run artifacts rendered on demand from the run record (no files on disk):
report.md (human), run.json (machine), s11_<candidate>.csv (plots)."""
from __future__ import annotations

import json
import time

from app.geometry.spec import clearance_at
from app.runs.store import Run


def artifact_names(run: Run) -> list[str]:
    names = ["report.md", "run.json"]
    if run.final and run.final.get("ranking"):
        names += [f"s11_{cid}.csv" for cid in run.final["ranking"][:5]]
    return names


def render(run: Run, name: str) -> tuple[str, str] | None:
    """-> (body, media_type) or None if unknown."""
    if name == "report.md":
        return markdown(run), "text/markdown"
    if name == "run.json":
        return json.dumps(run_json(run), indent=1), "application/json"
    if name.startswith("s11_") and name.endswith(".csv"):
        cid = name[4:-4]
        r = run.results.get(cid)
        if r is None:
            return None
        rows = ["f_ghz,s11_db"] + [f"{p.f_ghz},{p.s11_db}" for p in r.s11_curve]
        return "\n".join(rows) + "\n", "text/csv"
    return None


def run_json(run: Run) -> dict:
    return {
        "run_id": run.id, "status": run.status, "truncated": run.truncated,
        "device_id": run.device.id if run.device else None,
        "prompt": run.prompt, "bands": run.band_ids,
        "spec_source": run.spec_source, "ambiguities": run.ambiguities,
        "iterations": run.iteration, "total_sims": len(run.results),
        "final": run.final,
        "spec": run.spec.model_dump(),
        "anchors": [a.model_dump() for a in run.anchors],
        "candidates": {k: c.model_dump() for k, c in run.candidates.items()},
        "results": {k: r.model_dump(exclude={"s11_curve"}) for k, r in run.results.items()},
        "iterations_detail": [
            {"iteration": rep.iteration, "trend": rep.trend, "best": rep.best_so_far,
             "scores": {cr.candidate_id: cr.score for cr in rep.reports}}
            for rep in run.reports],
    }


def _worst_in_band(r, band) -> float:
    """The S11 the requirement is judged on: worst point inside the band."""
    pts = [p.s11_db for p in r.s11_curve
           if band.f_low_ghz <= p.f_ghz <= band.f_high_ghz]
    return max(pts) if pts else r.s11_min_db


def _best_for_band(run: Run, band_id: str):
    """(candidate_id, result) for this band's best complete solve, or (None, None).
    Prefers a design that meets the requirements, then depth of in-band match."""
    band = next((b for b in run.spec.requirements.bands if b.id == band_id), None)
    best = (None, None)
    best_key = None
    for cid, c in run.candidates.items():
        if c.band_id != band_id:
            continue
        r = run.results.get(cid)
        if r is None or r.status != "complete":
            continue
        key = (1 if r.meets_requirements else 0,
               -(_worst_in_band(r, band) if band else r.s11_min_db))
        if best_key is None or key > best_key:
            best_key, best = key, (cid, r)
    return best


def markdown(run: Run) -> str:
    spec, f = run.spec, run.final or {}
    bands = [b for b in spec.requirements.bands if b.id in run.band_ids]
    out = [f"# Antenna design report — {spec.name}", "",
           f"Run `{run.id}` · status **{run.status}**"
           + (" (truncated: best-so-far)" if run.truncated else "")
           + f" · {run.iteration} iterations · {len(run.results)} simulations"
           + f" · spec source: {run.spec_source}", "",
           f"**Task.** {run.prompt or 'Design the antenna system for this device.'}", "",
           "## Requirements", ""]
    for b in bands:
        out.append(f"- **{b.name}** ({b.f_low_ghz}–{b.f_high_ghz} GHz): S11 ≤ {b.s11_db_max} dB, "
                   f"efficiency ≥ {b.efficiency_min}, clearance ≥ {b.clearance_mm} mm, "
                   f"VSWR ≤ {spec.requirements.vswr_max}")
    # Per-band verdict, ALWAYS, before the single recommendation below.
    # A multi-band run recommends one antenna; without this the report listed
    # two required bands, recommended a 5 GHz monopole and said "meets
    # requirements: yes", never mentioning that 2.4 GHz was left without a
    # working design. The reader has to be told which of the bands they asked
    # for actually came out with one.
    if len(bands) > 1:
        out += ["", "## Per-band outcome", "",
                "| Band | Best design | In-band S11 | Verdict |", "|---|---|---|---|"]
        for b in bands:
            best_cid, best_r = _best_for_band(run, b.id)
            if best_r is None:
                out.append(f"| **{b.name}** | — | — | **no simulated design** |")
                continue
            worst = _worst_in_band(best_r, b)
            ok = best_r.meets_requirements
            out.append(
                f"| **{b.name}** | `{best_cid}` | {worst:.1f} dB "
                f"(target {b.s11_db_max}) | **{'met' if ok else 'NOT met'}** |")
        unmet = [b.name for b in bands
                 if (lambda r: r is None or not r.meets_requirements)(_best_for_band(run, b.id)[1])]
        out += ["", (f"**{len(bands) - len(unmet)} of {len(bands)} bands have a design that "
                     f"meets the requirements.**"
                     + (f" Still unmet: {', '.join(unmet)}." if unmet else "")), ""]

    out += ["", "## Recommendation", ""]
    if f.get("best"):
        b, c = f["best"], f["best_candidate"]
        anchor = next((a for a in run.anchors if a.id == c["anchor_id"]), None)
        clear, blocker = clearance_at(spec, tuple(c["position_mm"]))
        out += [
            f"**{c['antenna_type']}** at **{anchor.label if anchor else c['anchor_id']}** "
            f"(x={c['position_mm'][0]:.1f}, y={c['position_mm'][1]:.1f}, "
            f"z={c['position_mm'][2]:.1f} mm), length **{c['length_mm']} mm**"
            + (f", params {c['params']}" if c.get("params") else "") + ".", "",
            "| Metric | Value |", "|---|---|",
            f"| S11 minimum | {b['s11_min_db']} dB at {b['resonant_ghz']} GHz |",
            f"| −6 dB bandwidth | {b['bandwidth_mhz']} MHz |",
            f"| VSWR (band centre) | {b['vswr']} |",
            f"| Input impedance | {b['impedance_ohm'][0]} + j{b['impedance_ohm'][1]} Ω |",
            f"| Total efficiency | {b['efficiency']} |",
            f"| Clearance to nearest metal | {clear:.1f} mm ({blocker or 'none'}) |",
            f"| Meets requirements | {'yes' if b['meets_requirements'] else 'no'} |",
            "", f"**Solver note.** {b['notes']}", "",
        ]
        if len(f.get("ranking", [])) > 1:
            out += ["### Ranking", ""]
            for i, cid in enumerate(f["ranking"], 1):
                r = run.results.get(cid)
                if r:
                    out.append(f"{i}. `{cid}` — S11 {r.s11_min_db} dB @ {r.resonant_ghz} GHz, "
                               f"VSWR {r.vswr}, eff {r.efficiency}")
            out.append("")
    else:
        out += ["No simulated design on record.", ""]
    out += ["## Agent rationale", "", f.get("rationale", "—"), ""]
    if f.get("agent_report"):
        ar = f["agent_report"]
        fin = ar.get("final") or {}
        out += ["### Agent's structured report", "",
                f"- status: {ar.get('status')}; current best: `{ar.get('current_best')}`; "
                f"iterations: {ar.get('iterations_done')}"]
        if fin.get("position_summary"):
            out.append(f"- position: {fin['position_summary']}")
        if fin.get("rationale"):
            out.append(f"- rationale: {fin['rationale']}")
        out.append("")
    if f.get("openems_confirmation"):
        oc = f["openems_confirmation"]
        out += ["### Real-solver confirmation", "",
                "One-shot re-solve of the winner above against the real solver "
                "(integration plan §6) — the in-loop search above ran on the fast "
                "reference oracle; this checks its ranking against full-wave FDTD.",
                "",
                f"- status: **{oc.get('status')}**; S11 min {oc.get('s11_min_db')} dB "
                f"at {oc.get('resonant_ghz')} GHz; VSWR {oc.get('vswr')}"
                + (f"; efficiency {oc.get('efficiency')}"
                   if oc.get("status") == "complete" else ""),
                f"- {oc.get('notes', '')}", ""]
    out += ["## Iteration history", ""]
    for rep in run.reports:
        top = rep.reports[0] if rep.reports else None
        out.append(f"- iteration {rep.iteration} ({rep.trend}): {len(rep.reports)} sims"
                   + (f", best `{top.candidate_id}` score {top.score}" if top else ""))
    out += ["", "## Device model", "",
            f"{spec.name} — {spec.board.size_mm[0]:.1f} × {spec.board.size_mm[1]:.1f} × "
            f"{spec.board.size_mm[2]:.1f} mm, {len(spec.components)} components; "
            f"ground reference: "
            f"`{next((c.name for c in spec.components if c.role == 'ground'), '?')}`."]
    if run.ambiguities:
        out += ["", "Classification caveats:", ""] + [f"- {a}" for a in run.ambiguities]
    out += ["", "## Limits of this result", "",
            "- Simulation fidelity is that of the configured solver (reference: PEC "
            "wire-grid MoM — ground plane + antenna; other components enter via "
            "clearance priors and hints, not the field solve). Directional, not "
            "certification-grade.",
            "- Efficiency from the reference solver is mismatch-limited (lossless model).",
            "", f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S')}_", ""]
    return "\n".join(out)
