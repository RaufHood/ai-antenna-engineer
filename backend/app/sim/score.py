"""Scoring + diagnosis: turn SimResults into the evidence layers the agent
reasons over (DESIGN.md §6.4). Hints are deterministic physics arithmetic —
never LLM output. The scalar score exists for ranking/UI only."""
from __future__ import annotations

from app.geometry.spec import clearance_at
from app.models import (BandRequirement, Candidate, CandidateReport,
                        DeviceSpec, IterationReport, RequirementDiff, SimResult)


def diffs_for(spec: DeviceSpec, band: BandRequirement, cand: Candidate,
              r: SimResult) -> list[RequirementDiff]:
    in_band = [p for p in r.s11_curve
               if band.f_low_ghz <= p.f_ghz <= band.f_high_ghz]
    worst = max((p.s11_db for p in in_band), default=0.0)
    clear_mm, _blocker = clearance_at(spec, cand.position_mm)
    band_mhz = (band.f_high_ghz - band.f_low_ghz) * 1000.0
    return [
        RequirementDiff(requirement="worst in-band S11", target=band.s11_db_max,
                        actual=round(worst, 2), margin=round(band.s11_db_max - worst, 2),
                        unit="dB", passing=worst <= band.s11_db_max),
        RequirementDiff(requirement="-6 dB bandwidth covers band", target=band_mhz,
                        actual=r.bandwidth_mhz, margin=round(r.bandwidth_mhz - band_mhz, 1),
                        unit="MHz", passing=r.bandwidth_mhz >= band_mhz),
        RequirementDiff(requirement="total efficiency", target=band.efficiency_min,
                        actual=r.efficiency, margin=round(r.efficiency - band.efficiency_min, 3),
                        unit="", passing=r.efficiency >= band.efficiency_min),
        RequirementDiff(requirement="VSWR", target=spec.requirements.vswr_max,
                        actual=r.vswr, margin=round(spec.requirements.vswr_max - r.vswr, 2),
                        unit="", passing=r.vswr <= spec.requirements.vswr_max),
        RequirementDiff(requirement="clearance to nearest metal", target=band.clearance_mm,
                        actual=round(clear_mm, 1), margin=round(clear_mm - band.clearance_mm, 1),
                        unit="mm", passing=clear_mm >= band.clearance_mm),
    ]


def hints_for(spec: DeviceSpec, band: BandRequirement, cand: Candidate,
              r: SimResult) -> list[str]:
    hints: list[str] = []
    if r.status != "complete":
        return [f"simulation failed: {r.notes}"]
    f_t = band.f_mid_ghz
    f_lo_sweep = r.s11_curve[0].f_ghz
    f_hi_sweep = r.s11_curve[-1].f_ghz

    if abs(r.resonant_ghz - f_lo_sweep) < 1e-6 or abs(r.resonant_ghz - f_hi_sweep) < 1e-6:
        hints.append(
            f"resonance pinned at sweep edge ({r.resonant_ghz:.2f} GHz) — true "
            f"resonance likely outside window; change length_mm decisively")
    elif abs(r.resonant_ghz - f_t) / f_t > 0.015:
        scale = r.resonant_ghz / f_t
        hints.append(
            f"resonance {r.resonant_ghz:.2f} GHz vs target {f_t:.2f} → element "
            f"{'short' if scale > 1 else 'long'} by ~{abs(scale-1)*100:.0f}%; "
            f"try length_mm ≈ {cand.length_mm * scale:.1f}")

    R, X = r.impedance_ohm
    if R < 20:
        fix = ("increase gap_mm (moves feed tap up the impedance curve)"
               if cand.antenna_type == "IFA"
               else "consider IFA — a shorting post transforms low R upward")
        hints.append(f"radiation resistance low (R={R:.0f} Ω vs 50) → {fix}")
    elif R > 110:
        if cand.antenna_type == "IFA":
            hints.append(f"R={R:.0f} Ω too high → decrease gap_mm")

    clear_mm, blocker = clearance_at(spec, cand.position_mm)
    if clear_mm < band.clearance_mm:
        hints.append(
            f"keep-out violated: {clear_mm:.1f} mm to {blocker} "
            f"(need ≥ {band.clearance_mm:.0f}) — detuning risk; prefer another anchor")

    if r.bandwidth_mhz == 0 and -6.0 < r.s11_min_db <= -4.0:
        hints.append("match is marginal, not absent — small length/gap moves may cross -6 dB")
    return hints


def score_of(diffs: list[RequirementDiff]) -> float:
    s = 0.5
    for d in diffs:
        if d.requirement == "worst in-band S11":
            s += max(min(0.08 * d.margin, 0.3), -0.3)
        elif d.requirement == "total efficiency":
            s += max(min(0.5 * d.margin, 0.1), -0.1)
        elif d.requirement == "clearance to nearest metal":
            s += max(min(0.03 * d.margin, 0.1), -0.15)
        elif d.requirement == "-6 dB bandwidth covers band":
            s += 0.05 if d.passing else -0.05
    return round(max(0.0, min(1.0, s)), 3)


def build_report(spec: DeviceSpec, band: BandRequirement, iteration: int,
                 cands: dict[str, Candidate], results: dict[str, SimResult],
                 history_best: list[float]) -> IterationReport:
    reports: list[CandidateReport] = []
    for cid, r in results.items():
        cand = cands[cid]
        ds = diffs_for(spec, band, cand, r) if r.status == "complete" else []
        reports.append(CandidateReport(
            candidate_id=cid, result=r, diffs=ds,
            score=score_of(ds) if ds else 0.0,
            hints=hints_for(spec, band, cand, r)))
    reports.sort(key=lambda cr: cr.score, reverse=True)
    best = reports[0].candidate_id if reports else None

    trend = "first_iteration"
    if history_best:
        prev = history_best[-1]
        cur = reports[0].score if reports else 0.0
        if cur > prev + 0.02:
            trend = "converging"
        elif cur < prev - 0.02:
            trend = "regressing"
        else:
            trend = "plateaued"
    return IterationReport(iteration=iteration, reports=reports,
                           best_so_far=best, trend=trend)
