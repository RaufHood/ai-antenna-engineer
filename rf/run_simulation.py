"""The sim workstream's single entry point.

    run_simulation(config: dict) -> dict

Contract is fixed by frontend/src/lib/types.ts (Candidate / BandRequirement /
DeviceSpec in, SimResult out) so a FastAPI endpoint can call this directly
(`from rf import run_simulation` or `from rf.run_simulation import
run_simulation`) and frontend/src/lib/runner.ts's resultFor() can swap the
mock simulate() for a real HTTP call to that endpoint without changing shape
on either side.

Solver: openEMS (FDTD), installed in rf/.venv from the vendored Windows
wheels (rf/vendor/openEMS/python/*.whl — see rf/requirements.txt and
rf/openems_env.py, which geometry.py runs before `import CSXCAD` / `import
openEMS`). geometry.build_ifa_geometry / solve.run_fdtd / postprocess.
postprocess are a real bare-PEC IFA-over-ground-plane solve, not a stub —
but step 2 (run an UNMODIFIED openEMS tutorial and check it against its own
documented result) still hasn't happened, so nothing here is cross-checked
against a known-good number yet. See rf/progress_simulation.md for the
step-by-step plan and rf/bench_scaling.py / rf/validate_dipole.py for the
PyNEC cross-check oracle (step 4) this geometry is meant to agree with.

Run as `python -m rf.run_simulation` from the repo root (needs the package
context for the relative imports below to resolve).
"""
from __future__ import annotations

import time

from .device import load_device
from .geometry import build_ifa_geometry
from .models import Band, Candidate, SimOptions, SimResult
from .postprocess import postprocess
from .solve import run_fdtd


def run_simulation(config: dict, out_dir: str | None = None) -> dict:
    """Single entry point the FastAPI backend calls. See
    rf/progress_simulation.md for the config/result contract (mirrors
    frontend/src/lib/types.ts Candidate/BandRequirement -> SimResult).

    out_dir (optional): when given, the run's artifacts are persisted there
    in the rf/viz run-directory layout (config.json, result.json, Et.h5 if
    dumped, device.json if available) so `python -m rf.viz <out_dir>` can
    render every figure/animation from this exact run -- on any machine,
    with no solver installed. This is the seam between the solve and the
    media pipeline; keep it stable."""
    t0 = time.time()
    if out_dir:
        # Resolve NOW: openEMS's FDTD.Run() leaves the process cwd inside its
        # (deleted) temp sim dir, so a relative path resolved after the solve
        # points at a directory that no longer exists.
        from pathlib import Path
        out_dir = str(Path(out_dir).resolve())
    cand = Candidate(**config["candidate"])
    band = Band(**{k: config["band"][k] for k in
                   ("id", "f_low_ghz", "f_high_ghz", "s11_db_max", "efficiency_min")
                   if k in config["band"]})
    sim = SimOptions(**config.get("sim", {}))
    device = load_device(config)

    try:
        structure = build_ifa_geometry(cand, band, device, sim)
        port_result = run_fdtd(structure, band, sim)
        metrics = postprocess(port_result, band)
        result = SimResult(
            candidate_id=cand.candidate_id,
            status="complete",
            runtime_s=time.time() - t0,
            **metrics,
        )

        _persist(out_dir, config, result.to_dict(), port_result.sim_path)
        return result.to_dict()
    except NotImplementedError as e:
        result = SimResult(
            candidate_id=cand.candidate_id,
            status="failed",
            runtime_s=time.time() - t0,
            s11_curve=[], s11_min_db=0.0, resonant_ghz=0.0, bandwidth_mhz=0.0,
            efficiency=0.0, peak_gain_dbi=0.0, vswr=0.0, sar_w_per_kg=0.0,
            meets_requirements=False, notes=f"not runnable yet: {e}",
        )
        _persist(out_dir, config, result.to_dict(), None)
    return result.to_dict()


def _persist(out_dir: str | None, config: dict, result: dict,
             sim_path: str | None) -> None:
    """Write the rf/viz run-directory artifacts. Never raises: persisting
    media inputs must not be able to fail an otherwise-good solve."""
    if not out_dir:
        return
    try:
        import json
        import shutil
        from pathlib import Path
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "config.json").write_text(json.dumps(config, indent=2))
        (out / "result.json").write_text(json.dumps(result, indent=2))
        if sim_path:
            et = Path(sim_path) / "Et.h5"
            if et.exists():
                shutil.copy2(et, out / "Et.h5")
        manifest = config.get("device", {}).get("manifest_path")
        if manifest and Path(manifest).exists():
            shutil.copy2(manifest, out / "device.json")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_simulation] artifact persist failed (non-fatal): {exc}")


if __name__ == "__main__":
    # Tutorial checkpoint (step 2/4): bare IFA over a 100x50mm ground plane,
    # no dielectrics, narrowed GPS L1 sweep (1565-1585 MHz) chosen in
    # progress_simulation.md for a fast first pass.
    demo_config = {
        "candidate": {
            "candidate_id": "gps_l1_ifa_demo",
            "antenna_type": "IFA",
            "position_mm": [95, 25, 0],
            "feed_point_mm": [95, 25, 5],
            "length_mm": 42.6,
            "orientation": "edge",
        },
        "band": {"id": "gps_l1", "f_low_ghz": 1.565, "f_high_ghz": 1.585,
                  "s11_db_max": -8, "efficiency_min": 0.45},
        "device": {"board": {"size_mm": [100, 50, 1.6]}},
        "sim": {"mesh_res": "coarse", "boundary": "MUR", "freq_points": 11,
                "dump_fields": True},
    }
    import json
    from pathlib import Path
    out_dir = Path("runs") / demo_config["candidate"]["candidate_id"]
    result = run_simulation(demo_config, out_dir=str(out_dir))
    print(json.dumps({k: v for k, v in result.items() if k != "s11_curve"}, indent=2))
    print(f"\nartifacts -> {out_dir}/")
    print(f"render everything:  .venv-viz/bin/python -m rf.viz {out_dir}")
