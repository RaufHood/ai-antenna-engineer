/**
 * Shared placement assignment: one antenna per band, isolation-aware.
 * Used by the local heuristic runner and the backend snapshot adapter.
 */
import { phoneV1 } from "./device";
import { isolationDb } from "./rf";
import type { BandRequirement, Candidate, DeviceSpec, Job, SimResult } from "./types";

export function bandById(spec: DeviceSpec, id: string): BandRequirement {
  const b =
    spec.requirements.bands.find((x) => x.id === id) ??
    phoneV1.requirements.bands.find((x) => x.id === id);
  if (!b) throw new Error(`unknown band ${id}`);
  return b;
}

/** Composite ranking used to pick the winner per band. */
export function rank(r: SimResult) {
  return (
    (r.meets_requirements ? 1 : 0) * 2 +
    Math.min(-r.s11_min_db / 20, 1) +
    r.efficiency +
    Math.min(r.bandwidth_mhz / 600, 1) * 0.5
  );
}

export interface AssignInput {
  bandIds: string[];
  spec: DeviceSpec;
  candidates: Candidate[];
}

export interface Relocation {
  band_id: string;
  from: string;
  to: string;
  why: string;
}

/**
 * One antenna per band, each on its own anchor. Bands are assigned
 * lowest-frequency first because they are the most clearance-hungry, and a
 * candidate is skipped when it couples too strongly into an already-placed
 * antenna or reuses an occupied anchor.
 */
export function assign(
  input: AssignInput,
  jobs: Job[],
  results: Record<string, SimResult>,
): { placements: Record<string, string>; relocations: Relocation[] } {
  const placements: Record<string, string> = {};
  const relocations: Relocation[] = [];
  const taken: Candidate[] = [];
  const byId = new Map(input.candidates.map((c) => [c.candidate_id, c]));

  const present = new Set(input.candidates.map((c) => c.band_id));
  const order = (input.bandIds.length ? input.bandIds : [...present])
    .filter((id) => present.has(id) || input.spec.requirements.bands.some((b) => b.id === id))
    .slice()
    .sort(
      (a, b) => bandById(input.spec, a).f_low_ghz - bandById(input.spec, b).f_low_ghz,
    );

  for (const bandId of order) {
    const band = bandById(input.spec, bandId);
    const fc = (band.f_low_ghz + band.f_high_ghz) / 2;
    const ranked = jobs
      .filter((j) => j.band_id === bandId && j.status === "complete")
      .map((j) => byId.get(j.candidate_id))
      .filter((c): c is Candidate => Boolean(c))
      .sort(
        (a, b) => rank(results[b.candidate_id]) - rank(results[a.candidate_id]),
      );
    if (!ranked.length) continue;

    let chosen: Candidate | undefined;
    let reason = "";
    for (const cand of ranked) {
      if (taken.some((t) => t.anchor_id === cand.anchor_id)) {
        reason = reason || `${cand.anchor_id} already occupied`;
        continue;
      }
      const worst = taken.reduce((acc, t) => {
        const tb = bandById(input.spec, t.band_id);
        const db = isolationDb(
          cand.position_mm,
          t.position_mm,
          fc,
          (tb.f_low_ghz + tb.f_high_ghz) / 2,
        );
        return Math.max(acc, db);
      }, -99);
      if (worst > input.spec.requirements.isolation_db_max) {
        reason =
          reason ||
          `${cand.anchor_id} would only give ${worst.toFixed(1)} dB isolation`;
        continue;
      }
      chosen = cand;
      break;
    }

    if (!chosen) chosen = ranked[0];
    if (chosen.candidate_id !== ranked[0].candidate_id) {
      relocations.push({
        band_id: bandId,
        from: ranked[0].anchor_id,
        to: chosen.anchor_id,
        why: reason,
      });
    }
    placements[bandId] = chosen.candidate_id;
    taken.push(chosen);
  }

  return { placements, relocations };
}

export function isolationPairs(
  spec: DeviceSpec,
  candidates: Candidate[],
  placements: Record<string, string>,
): { a: string; b: string; db: number }[] {
  const isolation: { a: string; b: string; db: number }[] = [];
  const byId = new Map(candidates.map((c) => [c.candidate_id, c]));
  const placed = Object.entries(placements);
  for (let i = 0; i < placed.length; i++) {
    for (let k = i + 1; k < placed.length; k++) {
      const ca = byId.get(placed[i][1]);
      const cb = byId.get(placed[k][1]);
      if (!ca || !cb) continue;
      const ba = bandById(spec, ca.band_id);
      const bb = bandById(spec, cb.band_id);
      isolation.push({
        a: ca.candidate_id,
        b: cb.candidate_id,
        db: isolationDb(
          ca.position_mm,
          cb.position_mm,
          (ba.f_low_ghz + ba.f_high_ghz) / 2,
          (bb.f_low_ghz + bb.f_high_ghz) / 2,
        ),
      });
    }
  }
  return isolation;
}
