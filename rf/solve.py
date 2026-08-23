"""Runs the FDTD solve and extracts S-parameter data at the port."""
from __future__ import annotations

from .models import Band, FDTDStructure, SimOptions


def run_fdtd(structure: FDTDStructure, band: Band, sim: SimOptions) -> FDTDStructure:
    """Step 5: run the FDTD solve, then CalcPort over the band's
    frequency window (sim.freq_points samples across
    [band.f_low_ghz, band.f_high_ghz]) to populate S-parameter data on
    structure.port. This is the slow step -- typically minutes even at
    sim.mesh_res == "coarse"; see progress_simulation.md step 7 for the
    runtime knobs.
    """
    import numpy as np
    structure.FDTD.Run(structure.sim_path, verbose=3, cleanup=True)

    n = max(sim.freq_points, 3)
    freq = np.linspace(band.f_low_ghz * 1e9, band.f_high_ghz * 1e9, n)
    structure.port.CalcPort(structure.sim_path, freq)
    structure.freq = freq
    return structure
