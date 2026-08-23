"""Turns solved port/nf2ff data into the SimResult metrics dict."""
from __future__ import annotations

from .models import Band, FDTDStructure


def postprocess(structure: FDTDStructure, band: Band) -> dict:
    """Step 5: S11 curve -> resonant_ghz / bandwidth_mhz / vswr /
    s11_min_db from the port data solve.run_fdtd() populated.
    peak_gain_dbi and efficiency need an NF2FF run at the resonant
    frequency (radiated vs. accepted power); sar_w_per_kg stays 0.0 until
    a tissue phantom exists.
    """
    import numpy as np
    port = structure.port
    freq = structure.freq

    s11 = port.uf_ref / port.uf_inc
    s11_db = 20.0 * np.log10(np.abs(s11))
    s11_curve = [{"f_ghz": float(f / 1e9), "s11_db": float(db)}
                 for f, db in zip(freq, s11_db)]

    i_min = int(np.argmin(s11_db))
    s11_min_db = float(s11_db[i_min])
    resonant_ghz = float(freq[i_min] / 1e9)
    gamma = min(float(np.abs(s11[i_min])), 0.999)
    vswr = (1.0 + gamma) / (1.0 - gamma)

    below = s11_db <= band.s11_db_max
    bandwidth_mhz = float((freq[below].max() - freq[below].min()) / 1e6) if below.any() else 0.0

    efficiency = 0.0
    peak_gain_dbi = -99.0
    if s11_min_db <= band.s11_db_max:
        # Coarse angular grid for speed; nf2ff needs a resonance to probe.
        theta = np.arange(-180.0, 180.0, 10.0)
        phi = np.array([0.0, 90.0])
        nf2ff_res = structure.nf2ff.CalcNF2FF(structure.sim_path, freq[i_min], theta, phi)
        p_rad = float(nf2ff_res.Prad[0])
        p_acc = float(port.P_acc[i_min])
        if p_acc > 0:
            efficiency = max(0.0, min(1.0, p_rad / p_acc))
        dmax_db = float(nf2ff_res.Dmax[0])
        peak_gain_dbi = dmax_db + 10.0 * np.log10(efficiency) if efficiency > 0 else dmax_db - 99.0

    meets = s11_min_db <= band.s11_db_max and efficiency >= band.efficiency_min

    return {
        "s11_curve": s11_curve,
        "s11_min_db": s11_min_db,
        "resonant_ghz": resonant_ghz,
        "bandwidth_mhz": bandwidth_mhz,
        "efficiency": efficiency,
        "peak_gain_dbi": peak_gain_dbi,
        "vswr": vswr,
        "sar_w_per_kg": 0.0,  # stub -- needs a tissue phantom, see progress_simulation.md step 5
        "meets_requirements": meets,
        "notes": f"resonance {resonant_ghz:.4f} GHz, S11 {s11_min_db:.1f} dB"
                 + ("" if meets else " (below thresholds)"),
    }
