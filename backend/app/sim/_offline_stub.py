"""Deterministic, dependency-free solver used only by scripts/selftest.py to
exercise app.sim.pool.solve_with() / the orchestrator's confirm-winner path
(integration plan §6) without needing PyNEC or openEMS installed. Never
selected by SIM_SOLVER/CONFIRM_SOLVER in normal operation."""
from __future__ import annotations

from app.models import BandRequirement, Candidate, DeviceSpec, SimResult


def solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate) -> SimResult:
    return SimResult(
        candidate_id=cand.candidate_id, status="complete", runtime_s=0.001,
        resonant_ghz=band.f_mid_ghz, bandwidth_mhz=20.0, efficiency=0.6,
        s11_min_db=-15.0, vswr=1.3, meets_requirements=True,
        notes="offline stub for selftest.py, not a real solve")
