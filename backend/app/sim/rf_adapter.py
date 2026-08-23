"""Adapter from our solver seam to the sim workstream's entry point.

Their contract (rf/run_simulation.py, branch feat/simulation):

    run_simulation(config: dict) -> dict          # SimResult-shaped
    config = {"candidate": {...}, "band": {...}, "device": {...}, "sim": {...}}

Select it with  SIM_SOLVER=app.sim.rf_adapter:solve . Nothing else in the
backend changes: this module runs inside the process pool like any solver.

**Cross-venv, not in-process.** openEMS/CSXCAD are Windows wheels built for
Python 3.11, installed only in rf/.venv (rf/README.md Setup); the backend
itself runs Python 3.12 (backend/pyproject.toml). `from rf.run_simulation
import run_simulation` would raise ModuleNotFoundError the instant this ran
inside the backend's own interpreter (in the ProcessPoolExecutor, that's the
same interpreter as the parent process) -- there is no way to install
openEMS into the backend's venv without an ABI mismatch. So `solve()` below
shells out to rf/.venv's python via `rf/cli.py` (stdin JSON in, result JSON
written to a --out file -- **not stdout**: openEMS's C++ engine writes its
own verbose progress logging directly to the process's stdout, confirmed by
running it for real, so a JSON result can't reliably share that stream).
Same subprocess-to-a-separate-interpreter pattern `app/geometry/extract.py`
already uses for the bpy/Python-3.11 boundary; same file-not-stdout handoff
that script already uses for the same reason (bpy's own console spam).

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

Env: `RF_PYTHON` overrides the interpreter (default: `rf/.venv/Scripts/python.exe`
on Windows, `rf/.venv/bin/python` elsewhere); `RF_TIMEOUT_S` overrides the
subprocess timeout (default 600s -- FDTD solves run minutes, not the
oracle's milliseconds).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path

from app.models import BandRequirement, Candidate, DeviceSpec, S11Point, SimResult

REPO_DIR = Path(__file__).resolve().parents[3]
DEFAULT_TIMEOUT_S = 600.0


def _rf_python() -> Path | None:
    """Resolve an openEMS-capable interpreter. Never assumes -- returns None
    (not a guess) if nothing is found, so the caller can fail with a clear
    message instead of a confusing ModuleNotFoundError two layers down."""
    if py := os.environ.get("RF_PYTHON"):
        p = Path(py)
        return p if p.exists() else None
    for candidate in (REPO_DIR / "rf" / ".venv" / "Scripts" / "python.exe",  # Windows
                     REPO_DIR / "rf" / ".venv" / "bin" / "python",           # posix
                     # openEMS is built and installed by hand (there is no
                     # wheel), so the interpreter that has it is often a venv
                     # beside the checkout rather than inside it. Probe those
                     # too — but confirm the import instead of trusting the
                     # path, or a stale venv silently means "no field data".
                     REPO_DIR.parent / "venv" / "bin" / "python",
                     REPO_DIR.parent / ".venv" / "bin" / "python"):
        if candidate.exists() and _can_import_openems(candidate):
            return candidate
    return None


@lru_cache(maxsize=8)
def _can_import_openems(py: Path) -> bool:
    """Does this interpreter actually have the openEMS bindings?

    Cached: the answer cannot change inside a process, and the check costs a
    subprocess launch that would otherwise repeat on every solve.
    """
    try:
        r = subprocess.run([str(py), "-c", "import openEMS, CSXCAD"],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


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
    py = _rf_python()
    if py is None:
        return SimResult(candidate_id=cand.candidate_id, status="failed",
                         runtime_s=round(time.perf_counter() - t0, 3),
                         notes="rf/.venv not found (set RF_PYTHON to an "
                               "openEMS-capable Python 3.11 interpreter)")
    timeout_s = float(os.environ.get("RF_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    cfg_json = json.dumps(build_config(spec, band, cand))
    with tempfile.TemporaryDirectory(prefix="rf_solve_") as tmpdir:
        out_path = Path(tmpdir) / "result.json"
        try:
            proc = subprocess.run(
                [str(py), "-m", "rf.cli", "--out", str(out_path)], input=cfg_json,
                capture_output=True, text=True, timeout=timeout_s, cwd=str(REPO_DIR))
        except subprocess.TimeoutExpired:
            return SimResult(candidate_id=cand.candidate_id, status="failed",
                             runtime_s=round(time.perf_counter() - t0, 3),
                             notes=f"rf.cli timed out after {timeout_s:.0f}s")
        except OSError as e:  # interpreter vanished/unrunnable between check and exec
            return SimResult(candidate_id=cand.candidate_id, status="failed",
                             runtime_s=round(time.perf_counter() - t0, 3),
                             notes=f"rf.cli could not be started: {e}")
        if proc.returncode != 0 or not out_path.exists():
            # openEMS/CSXCAD write their own progress logging straight to
            # stdout, interleaved with anything Python prints -- neither
            # stream is reliably a clean error message, but it's all we have
            tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-12:])
            return SimResult(candidate_id=cand.candidate_id, status="failed",
                             runtime_s=round(time.perf_counter() - t0, 3),
                             notes=f"rf.cli failed (rc={proc.returncode}): "
                                   f"{tail or '(no output)'}")
        try:
            out = json.loads(out_path.read_text())
        except json.JSONDecodeError as e:
            return SimResult(candidate_id=cand.candidate_id, status="failed",
                             runtime_s=round(time.perf_counter() - t0, 3),
                             notes=f"rf.cli result file invalid JSON: {e}")
    return from_result(cand, out, t0)
