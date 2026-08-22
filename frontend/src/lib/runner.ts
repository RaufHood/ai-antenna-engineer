/**
 * Server-side run store. Owns the candidate list and the simulation queue so
 * state survives a page refresh, and so swapping the local heuristic solver for
 * openEMS / the Devin session is a change confined to this file.
 */
import { phoneV1 } from "./device";
import { generateCandidates, isolationDb, scorePoint, simulate } from "./rf";
import type {
  AgentMessage,
  BandRequirement,
  Candidate,
  DeviceSpec,
  Job,
  SimResult,
} from "./types";

const PLANNING_MS = 1600;
const PER_JOB_MS = 1500;
const CONCURRENCY = 3;

interface Run {
  id: string;
  prompt: string;
  bandIds: string[];
  createdAt: number;
  spec: DeviceSpec;
  candidates: Candidate[];
  queue: Candidate[];
}

const runs = new Map<string, Run>();
const resultCache = new Map<string, SimResult>();

function bandById(spec: DeviceSpec, id: string) {
  const b = spec.requirements.bands.find((x) => x.id === id);
  if (!b) throw new Error(`unknown band ${id}`);
  return b;
}

function resultFor(run: Run, cand: Candidate): SimResult {
  const key = `${run.id}::${cand.candidate_id}`;
  const cached = resultCache.get(key);
  if (cached) return cached;
  const r = simulate(run.spec, bandById(run.spec, cand.band_id), cand);
  resultCache.set(key, r);
  return r;
}

/** Client-side constraint edits are applied to a per-run copy of the spec. */
export function applyOverrides(
  overrides: RunOverrides | undefined,
): DeviceSpec {
  if (!overrides) return phoneV1;
  return {
    ...phoneV1,
    requirements: {
      ...phoneV1.requirements,
      sar_limit: overrides.sar_limit ?? phoneV1.requirements.sar_limit,
      bands: phoneV1.requirements.bands.map((b) => ({
        ...b,
        ...(overrides.bands?.[b.id] ?? {}),
      })),
    },
  };
}

export interface RunOverrides {
  sar_limit?: DeviceSpec["requirements"]["sar_limit"];
  bands?: Record<string, Partial<BandRequirement>>;
}

export function createRun(
  prompt: string,
  bandIds: string[],
  perBand = 6,
  overrides?: RunOverrides,
): { runId: string; candidates: Candidate[] } {
  const spec = applyOverrides(overrides);
  const all = generateCandidates(spec, bandIds);
  const perBandTop = bandIds.map((bandId) =>
    all
      .filter((c) => c.band_id === bandId)
      .sort((a, b) => b.prior - a.prior)
      .slice(0, perBand),
  );
  // Interleave bands so early results cover the whole system, not one band.
  const queue: Candidate[] = [];
  for (let i = 0; i < perBand; i++) {
    for (const list of perBandTop) if (list[i]) queue.push(list[i]);
  }

  const id = `run_${Date.now().toString(36)}`;
  runs.set(id, {
    id,
    prompt,
    bandIds,
    createdAt: Date.now(),
    spec,
    candidates: all,
    queue,
  });
  return { runId: id, candidates: all };
}

function jobStates(run: Run, now: number): Job[] {
  return run.queue.map((c, i) => {
    const start = run.createdAt + PLANNING_MS + Math.floor(i / CONCURRENCY) * PER_JOB_MS;
    const end = start + PER_JOB_MS;
    let status: Job["status"] = "queued";
    let progress = 0;
    if (now >= end) {
      status = "complete";
      progress = 1;
    } else if (now >= start) {
      status = "running";
      progress = (now - start) / PER_JOB_MS;
    }
    return {
      job_id: `${run.id}__${c.candidate_id}`,
      candidate_id: c.candidate_id,
      band_id: c.band_id,
      status,
      progress: +progress.toFixed(3),
      started_at: now >= start ? start : undefined,
      finished_at: now >= end ? end : undefined,
    };
  });
}

export interface RunSnapshot {
  runId: string;
  done: boolean;
  planning: boolean;
  jobs: Job[];
  results: Record<string, SimResult>;
  candidates: Candidate[];
  messages: AgentMessage[];
  placements: Record<string, string>;
  isolation: { a: string; b: string; db: number }[];
}

export function readRun(runId: string): RunSnapshot | null {
  const run = runs.get(runId);
  if (!run) return null;
  const now = Date.now();
  const jobs = jobStates(run, now);
  const planning = now < run.createdAt + PLANNING_MS;
  const done = jobs.every((j) => j.status === "complete");

  const results: Record<string, SimResult> = {};
  for (const j of jobs) {
    const cand = run.queue.find((c) => c.candidate_id === j.candidate_id)!;
    if (j.status === "complete") results[j.candidate_id] = resultFor(run, cand);
    else
      results[j.candidate_id] = {
        ...emptyResult(j.candidate_id),
        status: j.status,
      };
  }

  const { placements, relocations } = assign(run, jobs, results);

  const isolation: { a: string; b: string; db: number }[] = [];
  const placed = Object.entries(placements);
  for (let i = 0; i < placed.length; i++) {
    for (let k = i + 1; k < placed.length; k++) {
      const ca = run.queue.find((c) => c.candidate_id === placed[i][1])!;
      const cb = run.queue.find((c) => c.candidate_id === placed[k][1])!;
      const ba = bandById(run.spec, ca.band_id);
      const bb = bandById(run.spec, cb.band_id);
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

  return {
    runId: run.id,
    done,
    planning,
    jobs,
    results,
    candidates: run.candidates,
    messages: buildMessages(
      run,
      jobs,
      results,
      placements,
      isolation,
      relocations,
      planning,
      done,
    ),
    placements,
    isolation,
  };
}

/**
 * One antenna per band, each on its own anchor. Bands are assigned
 * lowest-frequency first because they are the most clearance-hungry, and a
 * candidate is skipped when it couples too strongly into an already-placed
 * antenna or reuses an occupied anchor.
 */
function assign(run: Run, jobs: Job[], results: Record<string, SimResult>) {
  const placements: Record<string, string> = {};
  const relocations: { band_id: string; from: string; to: string; why: string }[] =
    [];
  const taken: Candidate[] = [];

  const order = run.bandIds
    .slice()
    .sort(
      (a, b) =>
        bandById(run.spec, a).f_low_ghz - bandById(run.spec, b).f_low_ghz,
    );

  for (const bandId of order) {
    const band = bandById(run.spec, bandId);
    const fc = (band.f_low_ghz + band.f_high_ghz) / 2;
    const ranked = jobs
      .filter((j) => j.band_id === bandId && j.status === "complete")
      .map((j) => run.queue.find((c) => c.candidate_id === j.candidate_id)!)
      .filter(Boolean)
      .sort((a, b) => rank(results[b.candidate_id]) - rank(results[a.candidate_id]));
    if (!ranked.length) continue;

    let chosen: Candidate | undefined;
    let reason = "";
    for (const cand of ranked) {
      if (taken.some((t) => t.anchor_id === cand.anchor_id)) {
        reason = reason || `${cand.anchor_id} already occupied`;
        continue;
      }
      const worst = taken.reduce((acc, t) => {
        const tb = bandById(run.spec, t.band_id);
        const db = isolationDb(
          cand.position_mm,
          t.position_mm,
          fc,
          (tb.f_low_ghz + tb.f_high_ghz) / 2,
        );
        return Math.max(acc, db);
      }, -99);
      if (worst > run.spec.requirements.isolation_db_max) {
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

/** Composite ranking used to pick the winner per band. */
export function rank(r: SimResult) {
  return (
    (r.meets_requirements ? 1 : 0) * 2 +
    Math.min(-r.s11_min_db / 20, 1) +
    r.efficiency +
    Math.min(r.bandwidth_mhz / 600, 1) * 0.5
  );
}

function emptyResult(id: string): SimResult {
  return {
    candidate_id: id,
    status: "queued",
    runtime_s: 0,
    s11_curve: [],
    s11_min_db: 0,
    resonant_ghz: 0,
    bandwidth_mhz: 0,
    efficiency: 0,
    peak_gain_dbi: 0,
    vswr: 0,
    sar_w_per_kg: 0,
    meets_requirements: false,
    notes: "",
  };
}

function buildMessages(
  run: Run,
  jobs: Job[],
  results: Record<string, SimResult>,
  placements: Record<string, string>,
  isolation: { a: string; b: string; db: number }[],
  relocations: { band_id: string; from: string; to: string; why: string }[],
  planning: boolean,
  done: boolean,
): AgentMessage[] {
  const m: AgentMessage[] = [];
  const spec = run.spec;
  let t = run.createdAt;
  const push = (kind: AgentMessage["kind"], text: string) =>
    m.push({ id: `m${m.length}`, role: "agent", kind, text, ts: (t += 1) });

  push(
    "text",
    `Reading ${spec.name}. ${spec.components.length} named components, ` +
      `board ${spec.board.size_mm.join(" x ")} mm on ${spec.board.stackup} ` +
      `(er ${spec.board.epsilon_r}, tan-d ${spec.board.loss_tangent}).`,
  );
  push(
    "step",
    `Metal and lossy blocks that constrain placement: ` +
      `battery, camera module, PCB ground plane, taptic engine, loudspeaker. ` +
      `Enclosure back is glass (er 5.5), frame is aluminium and is treated as a radiator, not a blocker.`,
  );

  for (const bandId of run.bandIds) {
    const band = bandById(spec, bandId);
    const top = run.queue.filter((c) => c.band_id === bandId);
    push(
      "step",
      `${band.name} (${band.f_low_ghz}-${band.f_high_ghz} GHz) needs >= ${band.clearance_mm} mm clearance. ` +
        `Shortlisted ${top.length} anchors, best prior at ${top[0]?.rationale ?? "n/a"}.`,
    );
  }

  if (planning) return m;

  for (const j of jobs) {
    const cand = run.queue.find((c) => c.candidate_id === j.candidate_id)!;
    const band = bandById(spec, j.band_id);
    if (j.status === "running") {
      push(
        "step",
        `Running FDTD sweep for ${cand.candidate_id} (${cand.antenna_type}, ${band.name}) at ${cand.position_mm.map((v) => v.toFixed(0)).join(", ")} mm.`,
      );
    } else if (j.status === "complete") {
      const r = results[j.candidate_id];
      push(
        "result",
        `${cand.candidate_id}: S11 ${r.s11_min_db.toFixed(1)} dB at ${r.resonant_ghz.toFixed(2)} GHz, ` +
          `BW ${r.bandwidth_mhz} MHz, eff ${(r.efficiency * 100).toFixed(0)}%, gain ${r.peak_gain_dbi} dBi, ` +
          `SAR ${r.sar_w_per_kg} W/kg -> ${r.meets_requirements ? "PASS" : "FAIL"}. ${r.notes}`,
      );
    }
  }

  if (done) {
    for (const r of relocations) {
      const band = bandById(spec, r.band_id);
      push(
        "step",
        `${band.name}: best-scoring anchor was ${r.from}, but ${r.why}. Moved to ${r.to}.`,
      );
    }
    for (const [bandId, candId] of Object.entries(placements)) {
      const cand = run.queue.find((c) => c.candidate_id === candId)!;
      const band = bandById(spec, bandId);
      const s = scorePoint(spec, band, cand.position_mm);
      push(
        "text",
        `Recommendation for ${band.name}: ${cand.antenna_type} at ${cand.position_mm.map((v) => v.toFixed(1)).join(", ")} mm, ` +
          `radiator length ${cand.length_mm} mm, feed at ${cand.feed_point_mm.map((v) => v.toFixed(1)).join(", ")} mm. ` +
          `Keep-out ${band.clearance_mm} mm; nearest blocker is ${s.blocker} at ${s.clearance_mm.toFixed(1)} mm.`,
      );
    }
    const worst = isolation.slice().sort((a, b) => b.db - a.db)[0];
    if (worst) {
      push(
        "text",
        `Worst-case isolation between placed antennas is ${worst.db} dB (${worst.a} / ${worst.b}); ` +
          `target is <= ${spec.requirements.isolation_db_max} dB.`,
      );
    }
  }
  return m;
}
