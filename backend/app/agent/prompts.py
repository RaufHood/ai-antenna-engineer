"""Prompt assembly + wire-protocol text for the Devin session (DESIGN.md §4.3,
§6.3-6.4, §8). Everything the agent needs to act as the antenna engineer goes
into the CREATE prompt (or the design brief after an agent-side extraction);
per-iteration messages carry only evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.agent.port import RunContext
from app.geometry.spec import clearance_at
from app.models import IterationReport

_PROTOCOL_TEMPLATE = """\
## Protocol (strict)
You are the RF engineer in a design loop. A backend runs electromagnetic
simulations FOR you — you never run them yourself. Each of your replies MUST
contain exactly one fenced ```json block with ONE action:

1. Simulate a batch of candidate designs (batch as many as useful, <= {max_batch}):
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
PROTOCOL = _PROTOCOL_TEMPLATE.replace(
    "{max_batch}", str(min(30, int(os.environ.get("MAX_BATCH", "40")))))

SPEC__PROTOCOL_TEMPLATE = """\
## Step 1 — read the build file and classify it (reply with this FIRST)
Reply with exactly one fenced ```json block:
```json
{"action": "spec",
 "extracted": {"method": "skill" | "script" | "failed", "n_parts": 15,
               "size_mm": [71.6, 147.6, 7.8], "notes": "anything odd"},
 "ground": "<blender object that is the main ground reference (largest metal sheet the antenna sits over)>",
 "components": [{"name": "<blender object name>", "em": "pec" | "lossy_metal" | "dielectric" | "air",
                 "role": "ground" | "display" | "frame" | "battery" | "back_cover" | "board" | "shield" | "module" | "other",
                 "epsilon_r": 4.4, "note": "why"}],
 "summary": "2-4 sentences: device layout as it matters for antenna placement — where the
             metal blocks are, where the clear zones are, what the frame is made of"}
```
Classification rules (eps_r / sigma come from geometry.json):
sigma >= 1e6 S/m -> pec; 1e3 <= sigma < 1e6 -> lossy_metal; otherwise
dielectric with its eps_r; eps_r ~ 1 and sigma ~ 0 -> air. Only list
components whose classification you want to SET or CHANGE; omit the rest.
If extraction fails (no bpy, broken file), still reply with the action,
"method": "failed", and say what went wrong — the backend has a fallback.
Do NOT propose antennas in this reply; the design brief (anchors,
requirements) follows once your spec is accepted.
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


BRIEF_MIN_EXTENT_MM = 5.0   # parts smaller than this are RF-irrelevant clutter
BRIEF_MAX_COMPONENTS = 80   # message cap is ~50 KB; a real phone has ~200 parts


def _compact_spec(ctx: RunContext) -> dict:
    """Spec as the agent sees it: RF-relevant components only (metal and
    large dielectrics; screws/gaskets/adhesives summarised), no viewer or
    provenance fields. The full spec is in the run snapshot for the UI."""
    spec = ctx.spec.model_dump()
    keep, omitted = [], []
    for c in spec["components"]:
        (x0, y0, z0), (x1, y1, z1) = c["bbox_mm"]
        big = max(x1 - x0, y1 - y0, z1 - z0) >= BRIEF_MIN_EXTENT_MM
        if c["role"] == "ground" or (big and c["em"] != "air"):
            keep.append(c)
        else:
            omitted.append(c["name"])
    keep.sort(key=lambda c: (c["role"] != "ground", c["em"] == "dielectric",
                             -_volume(c["bbox_mm"])))
    if len(keep) > BRIEF_MAX_COMPONENTS:
        omitted += [c["name"] for c in keep[BRIEF_MAX_COMPONENTS:]]
        keep = keep[:BRIEF_MAX_COMPONENTS]
    for c in keep:
        c.pop("sigma_s_per_m", None); c.pop("em_source", None); c.pop("label", None)
        c["bbox_mm"] = [[round(v, 1) for v in p] for p in c["bbox_mm"]]
        if c.get("epsilon_r") is None:
            c.pop("epsilon_r", None); c.pop("loss_tangent", None)
        elif c.get("loss_tangent") is None:
            c.pop("loss_tangent", None)
    spec["components"] = keep
    spec.pop("geometry_path", None)
    if omitted:
        spec["components_omitted"] = (f"{len(omitted)} small/irrelevant parts not "
                                      f"listed (< {BRIEF_MIN_EXTENT_MM} mm or air): "
                                      + ", ".join(omitted[:12])
                                      + (" …" if len(omitted) > 12 else ""))
    spec["requirements"] = {
        k: v for k, v in spec["requirements"].items() if k != "bands"}
    return spec


def _volume(b) -> float:
    (x0, y0, z0), (x1, y1, z1) = b
    return (x1 - x0) * (y1 - y0) * (z1 - z0)


def _device_section(ctx: RunContext) -> list[str]:
    spec = ctx.spec
    bands = [b for b in spec.requirements.bands if b.id in ctx.band_ids]

    # Physics screening of every anchor against the real device geometry:
    # legality (does the antenna volume hit a component), escape fraction
    # (can the signal leave without meeting a conductor) and metal clearance.
    # Costs ~8 ms per anchor and saves the agent from discovering by
    # simulation what a bounding-box test answers instantly. Best-effort:
    # if there is no manifest, priors come back unscreened and the rows below
    # are exactly what they were before.
    priors_by_id: dict[str, dict] = {}
    screening_brief = ""
    try:
        from app.sim.priors import brief_for_agent, screen_anchors
        band0 = bands[0] if bands else spec.requirements.bands[0]
        priors = screen_anchors(spec, band0, anchors=ctx.anchors)
        priors_by_id = {p.anchor_id: p.to_dict() for p in priors}
        if priors and priors[0].screened:
            screening_brief = brief_for_agent(priors)
    except Exception:
        pass                                  # screening is an optimisation

    anchor_rows = []
    for a in ctx.anchors:
        clear, blocker = clearance_at(spec, a.pos_mm)
        row = {
            "id": a.id, "label": a.label, "region": a.region,
            "pos_mm": a.pos_mm, "corner": a.corner,
            "clearance_mm": round(clear, 1), "nearest_metal": blocker or None}
        pr = priors_by_id.get(a.id)
        if pr and pr.get("screened"):
            row |= {"legal": pr["legal"],
                    "escape_fraction": pr["escape_fraction"],
                    "nearest_metal_mm": pr["nearest_metal_mm"],
                    "why": pr["why"]}
        anchor_rows.append(row)
    band_rows = [{k: v for k, v in b.model_dump().items()
                  if k not in ("region_pref", "color")} for b in bands]
    out = [
        "\n## Device spec (mm, origin bottom-left-back; x width, y height, z thickness)\n```json",
        json.dumps(_compact_spec(ctx), separators=(",", ":")),
        "```",
        "\n## Candidate anchors (place antennas AT these; pick by clearance"
        " and band physics)\n```json",
        json.dumps(anchor_rows, separators=(",", ":")),
        "```",]
    if screening_brief:
        out += [
            "\n## Geometry screening (computed from the real device, not a guess)",
            "Two rules decide most of the outcome, and both are physics:",
            "- **Metal inside ~lambda/20 of the radiator dominates its impedance.**"
            " Prefer anchors with more metal clearance.",
            "- **A dielectric neighbour is a radome, a conductor is a wall.**"
            " `escape_fraction` is the share of directions the signal leaves"
            " without meeting metal — prefer high values.",
            "",
            "```", screening_brief, "```",
            "Anchors marked `legal: false` intersect a real component: do not"
            " propose them. If every legal anchor is poor, say so and explain"
            " what would have to move — that is a real engineering answer, not"
            " a failure.",
        ]
    out += [
        f"\n## Requirements\nbands: {json.dumps(band_rows)}",
        f"vswr_max: {spec.requirements.vswr_max}",
    ]
    if ctx.ambiguities:
        out += ["\n## Classification caveats (heuristic — question them if the "
                "geometry suggests otherwise)"] + [f"- {a}" for a in ctx.ambiguities]
    return out


def initial_prompt(ctx: RunContext) -> str:
    """backend-extraction mode: everything in one create prompt."""
    return "\n".join([
        f"# Task\n{ctx.prompt or 'Design the antenna system for this device.'}",
        f"\nBudget: {ctx.budget_note}",
        *_device_section(ctx),
        "\n" + ANTENNA_NOTES,
        PROTOCOL,
        "\nBegin with your first simulate action now.",
    ])


def extraction_prompt(ctx: RunContext, repo: str | None, script_text: str | None) -> str:
    """agent-extraction mode: the build file is attached; the agent must run
    the shared script (via the repo skill, or the inlined copy) and classify."""
    blend = ctx.blend_path.name if ctx.blend_path else "device.blend"
    side = (" and its `materials.json` sidecar (material vocabulary with eps_r / "
            "sigma per part — read it)") if ctx.sidecar_path else ""
    if repo:
        how = (f"The repo `{repo}` is cloned in your workspace. Follow the "
               f"`blend-extract` skill (.agents/skills/blend-extract/SKILL.md): it "
               f"runs `tools/extract_blend.py` under Python 3.11 with the `bpy` wheel.")
    else:
        how = ("Save the script below as `extract_blend.py`, then in a Python 3.11 "
               "environment: `pip install bpy` (or `uv run --python 3.11 --with bpy "
               "python extract_blend.py ...`) and run\n"
               f"`python extract_blend.py {blend} --out out --no-glb --no-stl` "
               "(add `--materials materials.json` if the sidecar is attached). "
               "Read `out/geometry.json`.")
    parts = [
        f"# Task\n{ctx.prompt or 'Design the antenna system for this device.'}",
        f"\nBudget: {ctx.budget_note}",
        f"\n## Build file\nAttached: `{blend}`{side}. {how}",
        "geometry.json gives every part's world bbox (mm, device frame: x width, "
        "y height, z thickness, origin at the min corner), material key, eps_r, "
        "sigma_S_per_m and triangle count. Sanity-check size_mm against a "
        "handset; note anything odd under extracted.notes.",
        "\n" + SPEC_PROTOCOL,
        "\n## Step 2 — design loop (after the brief arrives)",
        ANTENNA_NOTES,
        PROTOCOL,
    ]
    if script_text and not repo:
        parts += ["\n## tools/extract_blend.py (save verbatim)\n```python",
                  script_text, "```"]
    parts.append("\nReply with the `spec` action first.")
    return "\n".join(parts)


def brief_message(ctx: RunContext, crosscheck: str) -> str:
    return "\n".join([
        "## Design brief — spec accepted", crosscheck,
        *_device_section(ctx),
        "\nBegin with your first simulate action now (one fenced json block).",
    ])


def script_source() -> str | None:
    p = Path(__file__).resolve().parents[3] / "tools" / "extract_blend.py"
    try:
        return p.read_text()
    except OSError:
        return None


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
