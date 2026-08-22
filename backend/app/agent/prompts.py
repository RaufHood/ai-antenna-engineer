"""Prompt assembly + wire-protocol text for the Devin session (DESIGN.md §4.3,
§6.3-6.4). Everything the agent needs to act as the antenna engineer goes into
the CREATE prompt; per-iteration messages carry only evidence."""
from __future__ import annotations

import json

from app.agent.port import RunContext
from app.geometry.spec import clearance_at
from app.models import IterationReport

PROTOCOL = """\
## Protocol (strict)
You are the RF engineer in a design loop. A backend runs electromagnetic
simulations FOR you — you never run them yourself. Each of your replies MUST
contain exactly one fenced ```json block with ONE action:

1. Simulate a batch of candidate designs (batch as many as useful, <= 30):
```json
{"action": "simulate", "candidates": [{"candidate_id": "c001",
  "anchor_id": "<anchor id>", "band_id": "<band id>", "antenna_type":
  "IFA" | "monopole", "position_mm": [x, y, z], "feed_point_mm": [x, y, z],
  "length_mm": 30.7, "orientation": "edge" | "corner" | "face",
  "prior": 0.8, "rationale": "why this placement/type",
  "params": {"gap_mm": 5.0, "height_mm": 2.0}}]}
```
2. Sweep ONE parameter of a known candidate (cheap — prefer this over
guessing; sims cost milliseconds, your turns cost minutes):
```json
{"action": "sweep", "candidate_id": "c001", "param": "length_mm",
 "from": 26.0, "to": 34.0, "step": 0.5}
```
   `param` may be "length_mm" or any key of `params` (e.g. "gap_mm").
3. Conclude — ONLY when the evidence supports it (your recommendation must
already have a simulation on record; unsimulated conclusions are rejected):
```json
{"action": "done", "ranking": ["best_id", "runner_up_id"],
 "rationale": "engineering justification"}
```

After each simulate/sweep you receive per-candidate evidence: the S11 curve,
requirement diffs with signed margins, trend vs previous iterations, and
deterministic physics hints. Reason over the evidence — results are not
pass/fail verdicts. Narrate your engineering thinking briefly in plain text
around the json block; it is shown to the user live.
"""

ANTENNA_NOTES = """\
## Design notes
- The IFA feed-short gap ("gap_mm") transforms the feed impedance: larger gap
  -> higher R. length_mm sets resonance: too-high resonance -> lengthen.
- lambda/4 at 2.44 GHz is 30.7 mm. Straight quarter-wave monopoles rarely fit
  a phone edge; IFA/meander variants are the realistic family.
- Corners clear in two directions; respect each band's clearance_mm keep-out
  to metal components (violations detune hard).
"""


def initial_prompt(ctx: RunContext) -> str:
    spec = ctx.spec
    bands = [b for b in spec.requirements.bands if b.id in ctx.band_ids]
    anchor_rows = []
    for a in ctx.anchors:
        clear, blocker = clearance_at(spec, a.pos_mm)
        anchor_rows.append({
            "id": a.id, "label": a.label, "region": a.region,
            "pos_mm": a.pos_mm, "corner": a.corner,
            "clearance_mm": round(clear, 1), "nearest_metal": blocker or None})
    return "\n".join([
        f"# Task\n{ctx.prompt or 'Design the antenna system for this device.'}",
        f"\nBudget: {ctx.budget_note}",
        "\n## Device spec (mm, origin bottom-left-back)\n```json",
        json.dumps(spec.model_dump(), indent=1),
        "```",
        "\n## Candidate anchors (place antennas AT these; pick by clearance"
        " and band physics)\n```json",
        json.dumps(anchor_rows, indent=1),
        "```",
        f"\n## Requirements\nbands: {[b.model_dump() for b in bands]}",
        f"vswr_max: {spec.requirements.vswr_max}",
        "\n" + ANTENNA_NOTES,
        PROTOCOL,
        "\nBegin with your first simulate action now.",
    ])


def report_message(report: IterationReport) -> str:
    """Compact rendering: message POSTs have a size limit (a full report with
    ~20 S11 curves drew a 400 live, 2026-08-22). Per-candidate rows carry the
    derived quantities + diffs + hints; only the single best candidate gets
    its curve, decimated."""
    rows = []
    for cr in report.reports:
        r = cr.result
        row = {
            "id": cr.candidate_id, "status": r.status, "score": cr.score,
            "s11_min_db": r.s11_min_db, "resonant_ghz": r.resonant_ghz,
            "bw_mhz": r.bandwidth_mhz, "Z_ohm": r.impedance_ohm,
            "vswr": r.vswr, "eff": r.efficiency,
            "fail": [f"{d.requirement}: {d.actual}{d.unit} vs {d.target}{d.unit} "
                     f"(margin {d.margin})" for d in cr.diffs if not d.passing],
            "hints": cr.hints,
        }
        if r.status != "complete":
            row["notes"] = r.notes
        rows.append(row)
    best_curve = None
    if report.reports and report.reports[0].result.s11_curve:
        pts = report.reports[0].result.s11_curve
        best_curve = {"id": report.reports[0].candidate_id,
                      "s11_db_by_ghz": {str(p.f_ghz): p.s11_db
                                        for p in pts[::2]}}
    body = {"iteration": report.iteration, "trend": report.trend,
            "best_so_far": report.best_so_far, "candidates": rows,
            "best_curve": best_curve, "notes": report.notes}
    text = json.dumps(body, indent=1)
    if len(text) > 28000:  # stay well under the message limit
        for row in rows:
            row.pop("hints", None)
        body["best_curve"] = None
        body["truncation_note"] = ("large batch: hints/curves omitted — "
                                   "request a smaller sweep for detail")
        text = json.dumps(body, indent=1)
    return "\n".join([
        f"## Simulation evidence — iteration {report.iteration} "
        f"(trend: {report.trend})",
        "```json", text, "```",
        "All requirements not listed under 'fail' are passing.",
        "Reply with your next action (one fenced json block).",
    ])


STRUCTURED_OUTPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "status": {"type": "string",
                   "enum": ["analyzing", "iterating", "concluded"]},
        "current_best": {"type": ["string", "null"]},
        "iterations_done": {"type": "integer"},
        "final": {
            "type": ["object", "null"],
            "properties": {
                "ranking": {"type": "array", "items": {"type": "string"}},
                "antenna_type": {"type": "string"},
                "position_summary": {"type": "string"},
                "rationale": {"type": "string"},
            },
        },
    },
    "required": ["status"],
}
