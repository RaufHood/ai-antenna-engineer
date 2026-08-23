"""PyNEC oracle: wire-grid chassis + parametric antenna, impedance sweep -> S11.

NEC facts that shape this code (see rf/bench_scaling.py):
- junctions form ONLY where wire endpoints coincide -> plane built edge-by-edge
  between lattice nodes; antenna wires must land on lattice nodes.
- MoM solve is O(N^3) in segments -> grid pitch is the feasibility knob.
- NEC units are metres; our contracts are mm.

M0 scope (DESIGN.md log 2026-08-22): the solved structure is ground plane +
antenna. Other metal components enter via clearance priors/diagnosis, not the
MoM matrix; wire-cage obstacles are a later fidelity step.
"""
from __future__ import annotations

import math
import time
from PyNEC import nec_context

from app.models import BandRequirement, Candidate, DeviceSpec, S11Point, SimResult
from app.sim import builders
from app.sim.chassis import Z0, build_plane, chassis_from_spec

def solve(spec: DeviceSpec, band: BandRequirement, cand: Candidate,
          n_freq: int = 21, guard_ghz: float = 0.15) -> SimResult:
    t0 = time.perf_counter()
    f_lo = band.f_low_ghz - guard_ghz
    f_hi = band.f_high_ghz + guard_ghz
    f_step = (f_hi - f_lo) / (n_freq - 1)

    try:
        ctx = nec_context()
        geo = ctx.get_geometry()
        model = chassis_from_spec(spec, f_hi)
        next_tag = build_plane(geo, model)
        feed_tag, feed_seg = builders.build(geo, model, cand, next_tag)
        ctx.geometry_complete(0)
        ctx.ex_card(0, feed_tag, feed_seg, 0, 0, 1.0, 0, 0, 0, 0, 0)
        ctx.fr_card(0, n_freq, f_lo * 1000.0, f_step * 1000.0)
        ctx.xq_card(0)

        curve: list[S11Point] = []
        zs: list[complex] = []
        for k in range(n_freq):
            z = ctx.get_input_parameters(k).get_impedance()[0]
            zs.append(z)
            gamma = (z - Z0) / (z + Z0)
            s11_db = 20.0 * math.log10(max(abs(gamma), 1e-9))
            curve.append(S11Point(f_ghz=round(f_lo + k * f_step, 4),
                                  s11_db=round(s11_db, 2)))
    except Exception as e:  # NEC can reject bad geometry outright
        return SimResult(candidate_id=cand.candidate_id, status="failed",
                         runtime_s=time.perf_counter() - t0,
                         notes=f"solver error: {e}")

    return _postprocess(cand, band, curve, zs, f_lo, f_step, t0)


def _postprocess(cand: Candidate, band: BandRequirement, curve: list[S11Point],
                 zs: list[complex], f_lo: float, f_step: float, t0: float) -> SimResult:
    mid = band.f_mid_ghz
    k_mid = min(range(len(curve)), key=lambda k: abs(curve[k].f_ghz - mid))
    z_mid = zs[k_mid]
    g_mid = abs((z_mid - Z0) / (z_mid + Z0))
    vswr = (1 + g_mid) / max(1 - g_mid, 1e-6)

    # f0 is where the match is deepest, not where Im(Z) crosses zero. For an
    # IFA fed off-centre the two sit a grid step or more apart, and reporting
    # the zero-reactance point put f0 at 2.499 GHz on a design whose S11 dip
    # was dead centre at 2.442: the UI said "resonance 16 MHz high", the hint
    # told the agent to lengthen the element, and lengthening it pushed the
    # dip out of the band. The openEMS path (rf/postprocess.py) and report.md
    # ("S11 minimum at f0") already mean the dip; this now agrees with them.
    k_min = min(range(len(curve)), key=lambda k: curve[k].s11_db)
    resonant = curve[k_min].f_ghz
    s11_min = curve[k_min].s11_db

    # -6 dB bandwidth around the S11 minimum (contiguous)
    lo = hi = k_min
    if curve[k_min].s11_db <= -6.0:
        while lo > 0 and curve[lo - 1].s11_db <= -6.0:
            lo -= 1
        while hi < len(curve) - 1 and curve[hi + 1].s11_db <= -6.0:
            hi += 1
    bw_mhz = (hi - lo) * f_step * 1000.0 if curve[k_min].s11_db <= -6.0 else 0.0

    # PEC model is lossless: report mismatch-limited total efficiency, honestly.
    efficiency = 1.0 - g_mid ** 2

    # requirement check across the actual band, not the padded sweep
    in_band = [p for p in curve if band.f_low_ghz <= p.f_ghz <= band.f_high_ghz]
    worst_in_band = max((p.s11_db for p in in_band), default=0.0)
    meets = worst_in_band <= band.s11_db_max and efficiency >= band.efficiency_min

    return SimResult(
        candidate_id=cand.candidate_id, status="complete",
        runtime_s=round(time.perf_counter() - t0, 4),
        s11_curve=curve, s11_min_db=round(s11_min, 2),
        resonant_ghz=resonant, bandwidth_mhz=round(bw_mhz, 1),
        efficiency=round(efficiency, 3), peak_gain_dbi=0.0,
        vswr=round(min(vswr, 99.0), 2),
        impedance_ohm=(round(z_mid.real, 1), round(z_mid.imag, 1)),
        meets_requirements=meets,
        notes=f"PEC wire-grid model; worst in-band S11 {worst_in_band:.1f} dB",
    )
