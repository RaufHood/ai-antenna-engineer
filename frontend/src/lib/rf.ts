/**
 * Heuristic RF model used to drive the UI before openEMS is wired in.
 *
 * Everything here is a stand-in for a real solver: the scores come from
 * geometry (clearance to metal, edge access, chassis length, band preference)
 * and the S11 curves are synthesised from a single-resonator model. The shapes
 * of the outputs match the `SimResult` contract, so swapping in real openEMS
 * results is a change of data source only.
 */
import { H, T, W, anchors } from "./device";
import { clamp, dist3, distanceToBox, quarterWaveMm } from "./geometry";
import type {
  Anchor,
  BandRequirement,
  Bbox,
  Candidate,
  DeviceSpec,
  RegionId,
  SimResult,
  Vec3,
} from "./types";

function hash01(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

/** Metal and lossy blocks that detune an antenna. The shell frame is excluded. */
export function obstacles(spec: DeviceSpec) {
  return spec.components.filter(
    (c) => (c.em === "pec" || c.em === "lossy_metal") && c.name !== "frame",
  );
}

export function clearanceAt(spec: DeviceSpec, p: Vec3) {
  let best = Infinity;
  let who = "";
  for (const o of obstacles(spec)) {
    const d = distanceToBox(p, o.bbox_mm);
    if (d < best) {
      best = d;
      who = o.label;
    }
  }
  return { mm: best === Infinity ? 50 : best, component: who };
}

export function regionOf(p: Vec3): RegionId {
  const d = [
    { r: "left" as const, v: p[0] },
    { r: "right" as const, v: W - p[0] },
    { r: "bottom" as const, v: p[1] },
    { r: "top" as const, v: H - p[1] },
  ];
  d.sort((a, b) => a.v - b.v);
  return d[0].r;
}

export interface ScoreBreakdown {
  total: number;
  clearance: number;
  openness: number;
  ground: number;
  preference: number;
  clearance_mm: number;
  blocker: string;
}

/** 0..1 placement quality for a point and a band. */
export function scorePoint(
  spec: DeviceSpec,
  band: BandRequirement,
  p: Vec3,
): ScoreBreakdown {
  const { mm, component } = clearanceAt(spec, p);
  const clearance = clamp(mm / band.clearance_mm, 0, 1) ** 0.8;

  const edgeDist = Math.min(p[0], W - p[0], p[1], H - p[1]);
  const openness = clamp(1 - (edgeDist - 3) / 22, 0, 1);

  const region = regionOf(p);
  const chassis =
    region === "top" || region === "bottom"
      ? Math.max(p[1], H - p[1])
      : Math.max(p[0], W - p[0], H * 0.55);
  const fc = (band.f_low_ghz + band.f_high_ghz) / 2;
  const ground = clamp(chassis / quarterWaveMm(fc), 0, 1);

  const preference = band.region_pref[region] ?? 0.5;

  let total =
    0.42 * clearance + 0.22 * openness + 0.16 * ground + 0.2 * preference;
  if (mm < band.clearance_mm * 0.35) total *= 0.55;

  return {
    total: clamp(total, 0, 1),
    clearance,
    openness,
    ground,
    preference,
    clearance_mm: mm,
    blocker: component,
  };
}

export function keepoutFor(band: BandRequirement, p: Vec3): Bbox {
  const r = band.clearance_mm;
  return [
    [
      clamp(p[0] - r, 0, W),
      clamp(p[1] - r, 0, H),
      clamp(p[2] - Math.min(r, T / 2 + 1.5), -1, T),
    ],
    [
      clamp(p[0] + r, 0, W),
      clamp(p[1] + r, 0, H),
      clamp(p[2] + Math.min(r, T / 2 + 1.5), 0, T + 1),
    ],
  ];
}

function pickAntennaType(band: BandRequirement, a: Anchor) {
  if (band.id === "wifi5" && a.corner) return band.antenna_types[0];
  if (a.corner) return band.antenna_types[0];
  return band.antenna_types[Math.min(1, band.antenna_types.length - 1)];
}

export function generateCandidates(
  spec: DeviceSpec,
  bandIds: string[],
): Candidate[] {
  const out: Candidate[] = [];
  for (const band of spec.requirements.bands) {
    if (!bandIds.includes(band.id)) continue;
    const fc = (band.f_low_ghz + band.f_high_ghz) / 2;
    for (const a of anchors) {
      const s = scorePoint(spec, band, a.pos_mm);
      const len = Math.round(quarterWaveMm(fc) * 0.86 * 10) / 10;
      out.push({
        candidate_id: `${band.id}__${a.id}`,
        anchor_id: a.id,
        band_id: band.id,
        antenna_type: pickAntennaType(band, a),
        position_mm: a.pos_mm,
        feed_point_mm: [
          a.pos_mm[0] - a.outward[0] * 2,
          a.pos_mm[1] - a.outward[1] * 2,
          a.pos_mm[2],
        ],
        length_mm: len,
        orientation: a.corner ? "corner" : "edge",
        keepout_mm: keepoutFor(band, a.pos_mm),
        prior: s.total,
        rationale:
          `${a.label}: ${s.clearance_mm.toFixed(1)} mm to ${s.blocker} ` +
          `(needs ${band.clearance_mm} mm), chassis score ${(s.ground * 100).toFixed(0)}%, ` +
          `region weight ${(s.preference * 100).toFixed(0)}%`,
      });
    }
  }
  return out;
}

/** Synthesised single-resonator S11, standing in for an FDTD sweep. */
export function simulate(
  spec: DeviceSpec,
  band: BandRequirement,
  cand: Candidate,
): SimResult {
  const s = scorePoint(spec, band, cand.position_mm);
  const jitter = hash01(cand.candidate_id);
  const fc = (band.f_low_ghz + band.f_high_ghz) / 2;

  const detune = 1 - 0.055 * (1 - s.total) + (jitter - 0.5) * 0.02;
  const fr = fc * detune;
  const depth = 3 + 22 * s.total * (0.9 + 0.2 * jitter);
  const bwMhz = fc * 1000 * (0.02 + 0.115 * s.total);
  const Q = (fr * 1000) / Math.max(bwMhz, 1);

  const span = Math.max(fc * 0.55, (band.f_high_ghz - band.f_low_ghz) * 2.2);
  const fStart = Math.max(0.05, fc - span / 2);
  const fEnd = fc + span / 2;
  const N = 121;
  const curve: { f_ghz: number; s11_db: number }[] = [];
  for (let i = 0; i < N; i++) {
    const f = fStart + ((fEnd - fStart) * i) / (N - 1);
    const x = f / fr - fr / f;
    const s11 = -depth / (1 + (Q * x) ** 2);
    curve.push({ f_ghz: +f.toFixed(4), s11_db: +s11.toFixed(2) });
  }

  const threshold = band.s11_db_max;
  const below = curve.filter((c) => c.s11_db <= threshold);
  const measuredBw =
    below.length > 1
      ? (below[below.length - 1].f_ghz - below[0].f_ghz) * 1000
      : 0;

  const efficiency = clamp(0.25 + 0.55 * s.total, 0.05, 0.92);
  const gain = +(0.4 + 3.4 * s.total).toFixed(2);
  const g = 10 ** (-depth / 20);
  const vswr = +((1 + g) / (1 - g)).toFixed(2);
  const region = regionOf(cand.position_mm);
  const sar = +clamp(
    1.95 - 0.9 * s.total - (region === "bottom" ? 0.3 : 0),
    0.2,
    2.4,
  ).toFixed(2);

  const coversBand =
    below.length > 1 &&
    below[0].f_ghz <= band.f_low_ghz + 0.02 &&
    below[below.length - 1].f_ghz >= band.f_high_ghz - 0.02;
  const meets =
    -depth <= threshold &&
    efficiency >= band.efficiency_min &&
    coversBand &&
    sar <= spec.requirements.sar_limit.w_per_kg;

  const notes = !coversBand
    ? `Resonance at ${fr.toFixed(2)} GHz, -${band.s11_db_max * -1} dB band does not fully cover ${band.f_low_ghz}-${band.f_high_ghz} GHz`
    : efficiency < band.efficiency_min
      ? `Efficiency ${(efficiency * 100).toFixed(0)}% below the ${(band.efficiency_min * 100).toFixed(0)}% floor; loading from ${s.blocker}`
      : sar > spec.requirements.sar_limit.w_per_kg
        ? `SAR ${sar} W/kg exceeds the ${spec.requirements.sar_limit.w_per_kg} W/kg limit`
        : `Meets all targets; ${s.clearance_mm.toFixed(1)} mm clearance to ${s.blocker}`;

  return {
    candidate_id: cand.candidate_id,
    status: "complete",
    runtime_s: Math.round(180 + jitter * 420),
    s11_curve: curve,
    s11_min_db: +(-depth).toFixed(2),
    resonant_ghz: +fr.toFixed(3),
    bandwidth_mhz: Math.round(measuredBw),
    efficiency: +efficiency.toFixed(3),
    peak_gain_dbi: gain,
    vswr,
    sar_w_per_kg: sar,
    meets_requirements: meets,
    notes,
  };
}

/** Coupling between two placed antennas, in dB (more negative is better). */
export function isolationDb(a: Vec3, b: Vec3, fa: number, fb: number) {
  const d = dist3(a, b);
  const spatial = 6 + 44 * clamp(d / (H * 0.8), 0, 1);
  const freqSep = clamp(Math.abs(fa - fb) / Math.max(fa, fb), 0, 1) * 14;
  return +(-(spatial + freqSep)).toFixed(1);
}
