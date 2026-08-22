"""Data shapes shared across the sim pipeline. No logic here — geometry.py,
solve.py, postprocess.py and run_simulation.py all import from this module;
it must never import any of them back.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vec3 = tuple[float, float, float]
Bbox = tuple[Vec3, Vec3]

C0 = 299_792_458.0

# IFA geometry conventions -- Candidate (frontend/src/lib/types.ts) has no
# dedicated short-pin field, so these fill the gap. Documented here rather
# than buried in geometry.py so they're easy to find and revisit.
IFA_HEIGHT_MM = 5.0       # pin height used when feed_point_mm.z is 0
IFA_SHORT_GAP_MM = 3.0    # short-to-feed spacing when position_mm and
                          # feed_point_mm collapse to the same (x, y)
IFA_ARM_WIDTH_MM = 2.0    # radiating-arm strip width


@dataclass
class Candidate:
    candidate_id: str
    antenna_type: str  # "IFA" first; see progress_simulation.md
    position_mm: Vec3
    feed_point_mm: Vec3
    length_mm: float
    orientation: Literal["edge", "corner", "face"] = "edge"
    keepout_mm: Bbox | None = None


@dataclass
class Band:
    id: str
    f_low_ghz: float
    f_high_ghz: float
    s11_db_max: float = -8.0
    efficiency_min: float = 0.45


@dataclass
class SimOptions:
    mesh_res: Literal["coarse", "fine"] = "coarse"
    boundary: Literal["MUR", "PML_8"] = "MUR"
    freq_points: int = 21


@dataclass
class SimResult:
    candidate_id: str
    status: Literal["queued", "running", "complete", "failed"]
    runtime_s: float
    s11_curve: list[dict]  # [{"f_ghz": ..., "s11_db": ...}, ...]
    s11_min_db: float
    resonant_ghz: float
    bandwidth_mhz: float
    efficiency: float
    peak_gain_dbi: float
    vswr: float
    sar_w_per_kg: float
    meets_requirements: bool
    notes: str

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "runtime_s": self.runtime_s,
            "s11_curve": self.s11_curve,
            "s11_min_db": self.s11_min_db,
            "resonant_ghz": self.resonant_ghz,
            "bandwidth_mhz": self.bandwidth_mhz,
            "efficiency": self.efficiency,
            "peak_gain_dbi": self.peak_gain_dbi,
            "vswr": self.vswr,
            "sar_w_per_kg": self.sar_w_per_kg,
            "meets_requirements": self.meets_requirements,
            "notes": self.notes,
        }


@dataclass
class FDTDStructure:
    """Bundles what solve.py/postprocess.py need. Not part of the frontend
    contract -- purely an internal hand-off between the pipeline stages."""
    FDTD: object
    port: object
    nf2ff: object
    sim_path: str
    freq: object = None  # set by solve.run_fdtd() after CalcPort
