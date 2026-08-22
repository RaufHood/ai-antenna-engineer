"""Adapter from our solver seam to the sim workstream's entry point.

Their contract (rf/run_simulation.py, branch feat/simulation):

    run_simulation(config: dict) -> dict          # SimResult-shaped
    config = {"candidate": {...}, "band": {...}, "device": {...}, "sim": {...}}

Select it with  SIM_SOLVER=app.sim.rf_adapter:solve . Nothing else in the
backend changes: this module runs inside the process pool like any solver.

Mapping notes (keep in sync with rf/models.py):
- their Candidate dataclass rejects unknown keys -> only the types.ts fields
  are forwarded (anchor_id / band_id / prior / rationale / params stay here).
- their IFA builder reads the pin height from feed_point_mm.z (0 -> default),
  so our `params.height_mm` is mapped onto it.
- `device.manifest_path` -> the device's geometry.json (same manifest shape
  their blend_loader writes: parts[].{node_path, material_key, eps_r,
  sigma_S_per_m, bbox_mm, stl_path}); `device.board.size_mm` is the device
  outline; `device.components` is our classified list for when their step 6
  (real materials) lands.
- their result has no input impedance -> ours stays (0, 0) and the scorer
  skips the impedance hints.
- `SIM_OPTS` env (JSON) passes solver knobs, e.g.
  {"mesh_res": "coarse", "boundary": "MUR", "freq_points": 21}.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from app.models import BandRequirement, Candidate, DeviceSpec, S11Point, SimResult

REPO_DIR = Path(__file__).resolve().parents[3]


def build_config(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> dict:
    feed = list(cand.feed_point_mm)
    if "height_mm" in cand.params:
        feed[2] = float(cand.params["height_mm"])
    device: dict = {
        "device_id": spec.device_id,
        "name": spec.name,
        "board": {"size_mm": list(spec.board.size_mm), "stackup": spec.board.stackup,
                  "epsilon_r": spec.board.epsilon_r,
                  "loss_tangent": spec.board.loss_tangent},
        "enclosure": spec.enclosure.model_dump(),
        "components": [c.model_dump() for c in spec.components],
    }
    if spec.geometry_path:
        device["manifest_path"] = spec.geometry_path
    return {
        "candidate": {
            "candidate_id": cand.candidate_id,
            "antenna_type": cand.antenna_type,
            "position_mm": list(cand.position_mm),
            "feed_point_mm": feed,
            "length_mm": cand.length_mm,
            "orientation": cand.orientation,
        },
        "band": {
            "id": band.id, "f_low_ghz": band.f_low_ghz, "f_high_ghz": band.f_high_ghz,
            "s11_db_max": band.s11_db_max, "efficiency_min": band.efficiency_min,
        },
        "device": device,
        "sim": json.loads(os.environ.get("SIM_OPTS", "{}")),
    }


def from_result(cand: Candidate, out: dict, t0: float) -> SimResult:
    curve = [S11Point(f_ghz=round(float(p["f_ghz"]), 4), s11_db=round(float(p["s11_db"]), 2))
             for p in out.get("s11_curve", [])]
    return SimResult(
        candidate_id=cand.candidate_id,
        status=out.get("status", "failed"),
        runtime_s=round(float(out.get("runtime_s") or (time.perf_counter() - t0)), 3),
        s11_curve=curve,
        s11_min_db=round(float(out.get("s11_min_db", 0.0)), 2),
        resonant_ghz=round(float(out.get("resonant_ghz", 0.0)), 4),
        bandwidth_mhz=round(float(out.get("bandwidth_mhz", 0.0)), 1),
        efficiency=round(float(out.get("efficiency", 0.0)), 3),
        peak_gain_dbi=round(float(out.get("peak_gain_dbi", 0.0)), 2),
        vswr=round(min(float(out.get("vswr") or 99.0), 99.0), 2),
        impedance_ohm=tuple(out.get("impedance_ohm", (0.0, 0.0))),
        meets_requirements=bool(out.get("meets_requirements", False)),
        notes=f"[rf.run_simulation] {out.get('notes', '')}",
    )


def solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> SimResult:
    t0 = time.perf_counter()
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))
    try:
        from rf.run_simulation import run_simulation  # sim workstream, repo root
    except Exception as e:
        return SimResult(candidate_id=cand.candidate_id, status="failed",
                         runtime_s=round(time.perf_counter() - t0, 3),
                         notes=f"rf.run_simulation not importable: {e}")
    try:
        out = run_simulation(build_config(spec, band, cand))
        return from_result(cand, out, t0)
    except Exception as e:  # their builder raises ImportError without openEMS
        return SimResult(candidate_id=cand.candidate_id, status="failed",
                         runtime_s=round(time.perf_counter() - t0, 3),
                         notes=f"rf.run_simulation error: {type(e).__name__}: {e}")
