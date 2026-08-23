/**
 * How a simulated candidate is judged — in one place, because three panels
 * show the same verdict and they must never disagree.
 *
 * Two rules hold everywhere below:
 *   1. The solver owns the verdict. `meets_requirements` is reported, never
 *      re-derived, so the UI cannot promote a design the physics rejected.
 *   2. A failure names the requirement it missed. "Fail" on its own is not
 *      an answer an engineer can act on.
 */
import type { BandRequirement, SimResult } from "./types";

export type Verdict = "pass" | "fail" | "pending" | "error";

/** Handset practice: usable bandwidth is measured at the -6 dB crossing. */
export const BW_LEVEL_DB = -6;

export function verdictOf(r: SimResult | undefined): Verdict {
  if (!r || r.status === "queued" || r.status === "running") return "pending";
  if (r.status === "failed") return "error";
  return r.meets_requirements ? "pass" : "fail";
}

/**
 * The S11 the requirement is judged on: the worst point inside the band.
 * The solver's `meets_requirements` is computed from this, not from the
 * minimum — a −17 dB null 60 MHz below Wi-Fi 2.4 is a fine antenna for the
 * wrong band, and judging it on its minimum put "8.7 dB margin" next to a
 * Fail. Falls back to the minimum only when there is no sweep to read.
 */
export function worstInBandDb(r: SimResult, band: BandRequirement): number {
  const inBand = (r.s11_curve ?? []).filter(
    (p) => p.f_ghz >= band.f_low_ghz && p.f_ghz <= band.f_high_ghz,
  );
  if (!inBand.length) return r.s11_min_db;
  return Math.max(...inBand.map((p) => p.s11_db));
}

/** dB in hand against the band's S11 target, at the band's worst point. Positive = met, with room. */
export function marginDb(r: SimResult, band: BandRequirement): number {
  return band.s11_db_max - worstInBandDb(r, band);
}

/** Signed MHz from the nearest band edge; 0 when the resonance sits inside. */
export function detuneMhz(r: SimResult, band: BandRequirement): number {
  if (r.resonant_ghz < band.f_low_ghz) return (r.resonant_ghz - band.f_low_ghz) * 1000;
  if (r.resonant_ghz > band.f_high_ghz) return (r.resonant_ghz - band.f_high_ghz) * 1000;
  return 0;
}

/** Every stated requirement this result misses, binding one first. */
export function unmetRequirements(
  r: SimResult,
  band: BandRequirement,
  vswrMax: number,
): string[] {
  const out: string[] = [];
  const worst = worstInBandDb(r, band);
  if (worst > band.s11_db_max)
    out.push(
      worst === r.s11_min_db
        ? `S11 ${worst.toFixed(1)} dB, target ${band.s11_db_max.toFixed(1)} dB`
        : `In-band S11 ${worst.toFixed(1)} dB, target ${band.s11_db_max.toFixed(1)} dB (dip ${r.s11_min_db.toFixed(1)} dB at ${r.resonant_ghz.toFixed(3)} GHz)`,
    );
  if (r.efficiency < band.efficiency_min)
    out.push(
      `Efficiency ${Math.round(r.efficiency * 100)}%, target ${Math.round(band.efficiency_min * 100)}%`,
    );
  if (r.vswr > vswrMax) out.push(`VSWR ${r.vswr.toFixed(2)}, target ${vswrMax.toFixed(1)}`);
  return out;
}

/** One line saying why: the binding constraint, or the margin when it holds. */
export function reasonFor(
  r: SimResult,
  band: BandRequirement,
  vswrMax: number,
): string {
  if (r.status === "failed") return r.notes.trim() || "The solver returned no sweep";
  const unmet = unmetRequirements(r, band, vswrMax);
  if (unmet.length) return unmet[0];
  const detune = detuneMhz(r, band);
  const margin = `${marginDb(r, band).toFixed(1)} dB margin`;
  return detune === 0
    ? `${margin}, ${Math.round(r.efficiency * 100)}% efficient`
    : `${margin}, resonance ${Math.abs(detune).toFixed(0)} MHz ${detune < 0 ? "low" : "high"}`;
}

/**
 * Sort key for "which candidate won this band": a design that meets the
 * requirements always outranks one that does not, then depth of match.
 */
export function rankKey(r: SimResult | undefined, band: BandRequirement): number {
  if (!r || r.status !== "complete") return -Infinity;
  return (r.meets_requirements ? 1000 : 0) + marginDb(r, band);
}

/**
 * The contiguous frequency span around resonance where the sweep stays under
 * `level`, interpolated at the crossings. Null when the trace never gets there.
 */
export function bandwidthSpan(
  curve: SimResult["s11_curve"],
  level: number = BW_LEVEL_DB,
): { lo: number; hi: number } | null {
  if (!curve || curve.length < 2) return null;
  let iMin = 0;
  for (let i = 1; i < curve.length; i++) if (curve[i].s11_db < curve[iMin].s11_db) iMin = i;
  if (curve[iMin].s11_db > level) return null;

  const cross = (a: SimResult["s11_curve"][number], b: SimResult["s11_curve"][number]) => {
    const span = b.s11_db - a.s11_db;
    if (Math.abs(span) < 1e-9) return a.f_ghz;
    return a.f_ghz + ((level - a.s11_db) * (b.f_ghz - a.f_ghz)) / span;
  };

  let lo = curve[0].f_ghz;
  for (let i = iMin; i > 0; i--) {
    if (curve[i - 1].s11_db > level) {
      lo = cross(curve[i - 1], curve[i]);
      break;
    }
  }
  let hi = curve[curve.length - 1].f_ghz;
  for (let i = iMin; i < curve.length - 1; i++) {
    if (curve[i + 1].s11_db > level) {
      hi = cross(curve[i], curve[i + 1]);
      break;
    }
  }
  return hi > lo ? { lo, hi } : null;
}

/** Axis ticks on 1/2/5 steps, so labels land on numbers an engineer reads. */
export function niceTicks(lo: number, hi: number, count: number): number[] {
  const span = hi - lo;
  if (!(span > 0) || count < 1) return [lo];
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : norm >= 1 ? 1 : 0.5) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
    out.push(+v.toFixed(6));
  }
  return out;
}
