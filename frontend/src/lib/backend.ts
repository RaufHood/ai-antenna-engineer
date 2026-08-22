/**
 * Proxy to the FastAPI backend — the seam that makes the UI show the real run.
 *
 * `lib/rf.ts` is a self-contained TypeScript heuristic: it fabricates a
 * SimResult from a score function. It was built so the UI could be developed
 * before the solver existed, and its own header says so. The consequence is
 * that a demo driven by it is the frontend simulating itself — no agent, no
 * electromagnetics — which is exactly the thing a judge asks about.
 *
 * This module talks to the Python backend instead: real Devin (or the mock
 * agent), real PyNEC solves, real device geometry. It translates between the
 * two shapes so nothing in `components/` has to change:
 *
 *   POST /runs              {prompt, bands, agent, device_id}  -> {run_id}
 *   GET  /runs/{id}                                            -> status, candidates, results, final, spec
 *   GET  /runs/{id}/log                                        -> the event log (agent commentary lives here)
 *   POST /runs/{id}/messages {text}                            -> mid-run note for the agent
 *   POST /devices            multipart blend (+materials)      -> spec, anchors, device.glb
 *
 * `BACKEND_URL` (server-side env, defaults to http://127.0.0.1:8000) points at
 * it. When the backend is unreachable the caller falls back to the local
 * heuristic and says so, rather than showing an empty screen — but the
 * fallback is labelled, never silent, because a mock that looks real is worse
 * than one that admits it.
 */
import type { RunSnapshot } from "./runner";
import { rank } from "./runner";
import { isolationDb } from "./rf";
import type {
  AgentMessage,
  Anchor,
  BandRequirement,
  Bbox,
  Candidate,
  DeviceComponent,
  DeviceSpec,
  Job,
  SimResult,
  Vec3,
} from "./types";

export const BACKEND_URL =
  process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

export type AgentKind = "devin" | "mock";

/** Which agent drives the loop by default. "devin" needs backend/.env credentials. */
export const AGENT: AgentKind = (process.env.AGENT as AgentKind) ?? "mock";

const TIMEOUT_MS = 8000;

// ---------------------------------------------------------------- wire shapes

/** GET /runs/{id}. Candidates/results are keyed by candidate_id. */
export type BackendRun = {
  run_id: string;
  device_id: string | null;
  status: "running" | "finished" | "failed";
  stage: string;
  iteration: number;
  truncated: boolean;
  spec_source: string;
  ambiguities: unknown[];
  artifacts: string[];
  n_events: number;
  spec: BackendSpec;
  anchors: Anchor[];
  candidates: Record<string, BackendCandidate>;
  results: Record<string, BackendResult>;
  final: BackendFinal | null;
};

/** The backend's DeviceSpec: same as ours minus the viewer-only hints. */
export type BackendSpec = Omit<DeviceSpec, "components"> & {
  components: (Omit<DeviceComponent, "color"> & {
    color?: string;
    role?: string;
    em_source?: string;
  })[];
  geometry_path?: string | null;
};

type BackendCandidate = Omit<Candidate, "keepout_mm"> & {
  params?: Record<string, number>;
};

type BackendResult = Omit<SimResult, "sar_w_per_kg"> & {
  impedance_ohm?: [number, number];
};

type BackendFinal = {
  ranking: string[];
  rationale: string;
  truncated: boolean;
  best: BackendResult | null;
  best_candidate: BackendCandidate | null;
  iterations: number;
  total_sims: number;
  spec_source: string;
  agent_report?: Record<string, unknown> | null;
};

export type BackendEvent = {
  run_id: string;
  seq: number;
  ts: number;
  stage: string;
  type:
    | "stage_started"
    | "stage_progress"
    | "agent_message"
    | "candidates_proposed"
    | "sim_started"
    | "sim_result"
    | "iteration_scored"
    | "decision"
    | "artifact"
    | "run_finished"
    | "error";
  payload: Record<string, unknown>;
};

/** POST /devices. */
export type BackendDevice = {
  device_id: string;
  status: "extracting" | "ready" | "failed";
  error?: string | null;
  spec: BackendSpec | null;
  anchors: Anchor[];
  ambiguities: unknown[];
  size_mm: Vec3 | null;
  artifacts: string[];
};

// ---------------------------------------------------------------- transport

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`backend ${res.status}: ${(await res.text()).slice(0, 200)}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** Is the backend up? Used to decide real-vs-heuristic without a stack trace. */
export async function backendHealthy(): Promise<boolean> {
  try {
    await call<unknown>("/healthz");
    return true;
  } catch {
    return false;
  }
}

export async function createBackendRun(
  prompt: string,
  bands: string[],
  agent: AgentKind = AGENT,
  deviceId: string | null = null,
): Promise<string> {
  const body = JSON.stringify({ prompt, bands, agent, device_id: deviceId });
  const out = await call<{ run_id: string }>("/runs", { method: "POST", body });
  return out.run_id;
}

export async function readBackendRun(runId: string): Promise<BackendRun> {
  return call<BackendRun>(`/runs/${runId}`);
}

export async function readBackendLog(runId: string, since = 0): Promise<BackendEvent[]> {
  const out = await call<{ events: BackendEvent[] }>(`/runs/${runId}/log?since=${since}`);
  return out.events;
}

export async function postBackendMessage(runId: string, text: string): Promise<void> {
  await call<unknown>(`/runs/${runId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

/**
 * Upload a .blend (+ optional materials.json) and wait for extraction. The
 * multipart body is passed through untouched; the backend needs a Python 3.11
 * + bpy interpreter for this (see backend/README.md), and says so in its
 * error when it has none.
 */
export async function uploadBackendDevice(form: FormData): Promise<BackendDevice> {
  // Extraction is a Blender run: far longer than the 8 s call() budget.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10 * 60 * 1000);
  try {
    const res = await fetch(`${BACKEND_URL}/devices`, {
      method: "POST",
      body: form,
      signal: ctrl.signal,
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`backend ${res.status}: ${(await res.text()).slice(0, 300)}`);
    }
    return (await res.json()) as BackendDevice;
  } finally {
    clearTimeout(timer);
  }
}

export function backendArtifactUrl(deviceId: string, name: string): string {
  return `${BACKEND_URL}/devices/${deviceId}/artifacts/${name}`;
}

// ---------------------------------------------------------------- mapping

/** Viewer-only hints the backend does not carry: a colour per EM class. */
const EM_COLOR: Record<string, string> = {
  pec: "#d9a441",
  lossy_metal: "#3f4a63",
  dielectric: "#1f6f4a",
  air: "#1e293b",
};

/** Backend spec -> the spec the viewer draws (adds the display hints). */
export function normalizeSpec(spec: BackendSpec): DeviceSpec {
  return {
    ...spec,
    components: spec.components.map((c) => ({
      ...c,
      color: c.color ?? EM_COLOR[c.em] ?? "#475569",
      opacity: c.em === "dielectric" ? 0.35 : undefined,
      metalness: c.em === "pec" ? 0.85 : c.em === "lossy_metal" ? 0.5 : 0.1,
      roughness: c.em === "pec" ? 0.3 : 0.6,
      shape: "box",
      explode: [0, 0, 0],
    })),
  };
}

function keepoutFor(band: BandRequirement, p: Vec3, size: Vec3): Bbox {
  const [W, H, T] = size;
  const r = band.clearance_mm;
  const rz = Math.min(r, T / 2 + 1.5);
  const cl = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  return [
    [cl(p[0] - r, 0, W), cl(p[1] - r, 0, H), cl(p[2] - rz, -1, T)],
    [cl(p[0] + r, 0, W), cl(p[1] + r, 0, H), cl(p[2] + rz, 0, T + 1)],
  ];
}

function fmt(v: number, d = 1) {
  return Number.isFinite(v) ? v.toFixed(d) : "n/a";
}

/**
 * Event log -> the agent feed. Devin's own words (`agent_message`) are what
 * the panel is for; the rest is the orchestrator narrating the loop so a
 * minutes-long real run never looks stuck.
 */
function messagesFrom(
  events: BackendEvent[],
  candidates: Record<string, BackendCandidate>,
  bands: Record<string, BandRequirement>,
): AgentMessage[] {
  const out: AgentMessage[] = [];
  const push = (ev: BackendEvent, role: AgentMessage["role"], kind: AgentMessage["kind"], text: string) =>
    out.push({ id: `e${ev.seq}`, role, kind, text, ts: Math.round(ev.ts * 1000) });
  const bandName = (id: unknown) => (typeof id === "string" && bands[id]?.name) || String(id ?? "");

  for (const ev of events) {
    const p = ev.payload;
    switch (ev.type) {
      case "stage_started": {
        const s = String(p.stage ?? ev.stage);
        if (s === "extract") push(ev, "agent", "step", "Reading the build file (agent-side extraction).");
        else if (s === "agent_loop") push(ev, "agent", "step", "Design loop started: propose, simulate, score, refine.");
        else if (s === "report") push(ev, "agent", "step", "Writing the report.");
        break;
      }
      case "agent_message":
        push(ev, p.role === "user" ? "user" : "agent", "text", String(p.text ?? ""));
        break;
      case "candidates_proposed": {
        const cands = (p.candidates as BackendCandidate[] | undefined) ?? [];
        const sweep = p.sweep as { param?: string; candidate_id?: string } | undefined;
        const by = new Map<string, number>();
        for (const c of cands) by.set(c.band_id, (by.get(c.band_id) ?? 0) + 1);
        const where = [...by].map(([b, n]) => `${n} for ${bandName(b)}`).join(", ");
        push(
          ev,
          "agent",
          "step",
          sweep?.param
            ? `Iteration ${p.iteration}: sweeping ${sweep.param} on ${sweep.candidate_id} (${cands.length} variants).`
            : `Iteration ${p.iteration}: proposed ${cands.length} candidates (${where}).`,
        );
        break;
      }
      case "sim_result": {
        const r = p as unknown as BackendResult;
        const c = candidates[r.candidate_id];
        if (r.status === "failed") {
          push(ev, "agent", "result", `${r.candidate_id}: solve failed. ${r.notes ?? ""}`);
          break;
        }
        push(
          ev,
          "agent",
          "result",
          `${r.candidate_id}${c ? ` (${c.antenna_type}, ${bandName(c.band_id)})` : ""}: ` +
            `S11 ${fmt(r.s11_min_db)} dB at ${fmt(r.resonant_ghz, 3)} GHz, BW ${fmt(r.bandwidth_mhz, 0)} MHz, ` +
            `eff ${fmt(r.efficiency * 100, 0)}%, VSWR ${fmt(r.vswr, 2)} -> ${r.meets_requirements ? "PASS" : "FAIL"}.` +
            (r.notes ? ` ${r.notes}` : ""),
        );
        break;
      }
      case "iteration_scored": {
        const notes = (p.notes as string[] | undefined) ?? [];
        push(
          ev,
          "agent",
          "step",
          `Iteration ${p.iteration} scored: trend ${String(p.trend)}` +
            (p.best_so_far ? `, best so far ${String(p.best_so_far)}` : "") +
            (notes.length ? `. ${notes.join(" ")}` : "."),
        );
        break;
      }
      case "decision":
        push(ev, "agent", "text", `${String(p.decision ?? "decision")}: ${String(p.rationale ?? p.agent_summary ?? "")}`);
        break;
      case "run_finished": {
        if (p.status === "failed") {
          push(ev, "agent", "text", `Run failed: ${String(p.error ?? "unknown error")}`);
          break;
        }
        const best = p.best_candidate as BackendCandidate | null | undefined;
        const r = p.best as BackendResult | null | undefined;
        push(
          ev,
          "agent",
          "text",
          best && r
            ? `Recommendation: ${best.antenna_type} at ${best.position_mm.map((v) => v.toFixed(1)).join(", ")} mm ` +
              `for ${bandName(best.band_id)}, length ${best.length_mm} mm — S11 ${fmt(r.s11_min_db)} dB, ` +
              `efficiency ${fmt(r.efficiency * 100, 0)}%${r.meets_requirements ? ", all requirements met" : ", best effort"}. ` +
              `${String(p.rationale ?? "")}${p.truncated ? " (budget exhausted)" : ""}`
            : `Run finished without a simulated design. ${String(p.rationale ?? "")}`,
        );
        break;
      }
      case "artifact":
        if (p.name === "report.md") push(ev, "agent", "step", "Report ready (report.md, run.json, S11 CSVs).");
        break;
      case "error":
        push(ev, "agent", "text", `Error: ${String(p.error ?? "")}`);
        break;
      default:
        break;
    }
  }
  return out;
}

/**
 * Backend run + event log -> the snapshot shape the UI store already consumes.
 *
 * The backend has no notion of per-candidate queueing beyond `sim_started`:
 * a candidate exists once proposed and gains a result once solved. Placement
 * (one winner per band) and inter-antenna isolation are not the backend's
 * concern either — its ranking is a flat list — so they are derived here with
 * the same rank()/isolationDb() the heuristic path uses, which keeps the two
 * code paths comparable on screen.
 */
export function toSnapshot(
  run: BackendRun,
  events: BackendEvent[],
): RunSnapshot & {
  source: "backend";
  engine: string;
  status: BackendRun["status"];
  stage: string;
  iteration: number;
  artifacts: string[];
  spec: DeviceSpec;
  anchors: Anchor[];
  deviceId: string | null;
} {
  const size = run.spec.board.size_mm;
  const bands: Record<string, BandRequirement> = {};
  for (const b of run.spec.requirements.bands) bands[b.id] = b;

  const started = new Set<string>();
  for (const ev of events)
    if (ev.type === "sim_started") started.add(String(ev.payload.candidate_id));

  const candidates: Candidate[] = Object.values(run.candidates).map((c) => {
    const band = bands[c.band_id];
    return {
      ...c,
      keepout_mm: band
        ? keepoutFor(band, c.position_mm, size)
        : [c.position_mm, c.position_mm],
    };
  });

  const results: Record<string, SimResult> = {};
  for (const [id, r] of Object.entries(run.results)) {
    // SAR is not modelled by the solver; 0 renders as "n/a" in the dock.
    results[id] = { ...r, sar_w_per_kg: 0 };
  }

  const jobs: Job[] = candidates.map((c) => {
    const r = results[c.candidate_id];
    const status: Job["status"] = r
      ? r.status
      : started.has(c.candidate_id)
        ? "running"
        : "queued";
    return {
      job_id: `${run.run_id}__${c.candidate_id}`,
      candidate_id: c.candidate_id,
      band_id: c.band_id,
      status,
      progress: status === "complete" || status === "failed" ? 1 : status === "running" ? 0.5 : 0,
    };
  });

  // One winner per band. Prefer the agent's own ranking when it has concluded;
  // otherwise the best complete result so far, so the viewer has something to
  // highlight while the loop is still running.
  const placements: Record<string, string> = {};
  const ranking = run.final?.ranking ?? [];
  for (const bandId of Object.keys(bands)) {
    const fromAgent = ranking.find((cid) => run.candidates[cid]?.band_id === bandId);
    if (fromAgent && results[fromAgent]?.status === "complete") {
      placements[bandId] = fromAgent;
      continue;
    }
    const best = candidates
      .filter((c) => c.band_id === bandId && results[c.candidate_id]?.status === "complete")
      .sort((a, b) => rank(results[b.candidate_id]) - rank(results[a.candidate_id]))[0];
    if (best) placements[bandId] = best.candidate_id;
  }

  const isolation: RunSnapshot["isolation"] = [];
  const placed = Object.entries(placements);
  const mid = (b: BandRequirement) => (b.f_low_ghz + b.f_high_ghz) / 2;
  for (let i = 0; i < placed.length; i++) {
    for (let k = i + 1; k < placed.length; k++) {
      const ca = run.candidates[placed[i][1]];
      const cb = run.candidates[placed[k][1]];
      const ba = bands[placed[i][0]];
      const bb = bands[placed[k][0]];
      if (!ca || !cb || !ba || !bb) continue;
      isolation.push({
        a: ca.candidate_id,
        b: cb.candidate_id,
        db: isolationDb(ca.position_mm, cb.position_mm, mid(ba), mid(bb)),
      });
    }
  }

  return {
    runId: run.run_id,
    done: run.status !== "running",
    planning: run.status === "running" && candidates.length === 0,
    jobs,
    results,
    candidates,
    messages: messagesFrom(events, run.candidates, bands),
    placements,
    isolation,
    // What the UI should say out loud, so nobody mistakes one for the other.
    source: "backend",
    engine: `PyNEC via ${BACKEND_URL}`,
    status: run.status,
    stage: run.stage,
    iteration: run.iteration,
    artifacts: run.artifacts,
    spec: normalizeSpec(run.spec),
    anchors: run.anchors,
    deviceId: run.device_id,
  };
}
