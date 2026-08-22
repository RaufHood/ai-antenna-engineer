"""Process-pool execution of the simulation boundary.

THE SIM SEAM (DESIGN.md §7): simulation is the sim workstream's subsystem, not
ours. Our contract with it is exactly one callable:

    solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> SimResult

Point SIM_SOLVER at any "module:function" honouring that contract (default:
our bundled reference oracle, app.sim.oracle:solve) and the backend uses it —
no code changes here. Process isolation stays either way: solver crashes are
contained, C extensions can't stall the event loop."""
from __future__ import annotations

import asyncio
import importlib
import os
from concurrent.futures import ProcessPoolExecutor

from app.models import BandRequirement, Candidate, DeviceSpec, SimResult

_pool: ProcessPoolExecutor | None = None


def _resolve_solver():
    spec = os.environ.get("SIM_SOLVER", "app.sim.oracle:solve")
    mod_name, fn_name = spec.split(":")
    return getattr(importlib.import_module(mod_name), fn_name)


def _worker(spec_json: str, band_json: str, cand_json: str) -> str:
    # runs in a child process — import here keeps parent import time down
    solve = _resolve_solver()
    spec = DeviceSpec.model_validate_json(spec_json)
    band = BandRequirement.model_validate_json(band_json)
    cand = Candidate.model_validate_json(cand_json)
    return solve(spec, band, cand).model_dump_json()


def start_pool(workers: int = 4) -> None:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=workers)


def shutdown_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


async def solve_async(spec: DeviceSpec, band: BandRequirement,
                      cand: Candidate) -> SimResult:
    assert _pool is not None, "pool not started"
    loop = asyncio.get_running_loop()
    try:
        raw = await loop.run_in_executor(
            _pool, _worker, spec.model_dump_json(), band.model_dump_json(),
            cand.model_dump_json())
        return SimResult.model_validate_json(raw)
    except Exception as e:  # BrokenProcessPool et al.
        return SimResult(candidate_id=cand.candidate_id, status="failed",
                         notes=f"pool failure: {e}")
