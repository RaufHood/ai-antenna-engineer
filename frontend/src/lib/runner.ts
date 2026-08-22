/**
 * Server-side run store. Owns the candidate list and the simulation queue so
 * state survives a page refresh, and so swapping the local heuristic solver for
 * openEMS / the Devin session is a change confined to this file.
 */
import { phoneV1 } from "./device";
import { assign, bandById, isolationPairs, rank } from "./placement";
import { generateCandidates, scorePoint, simulate } from "./rf";
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
  truncated?: boolean;
  error?: string;
  rationale?: string;
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

  const { placements, relocations } = assign(
    { bandIds: run.bandIds, spec: run.spec, candidates: run.queue },
    jobs,
    results,
  );

  const isolation = isolationPairs(run.spec, run.queue, placements);

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

export { rank };

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
