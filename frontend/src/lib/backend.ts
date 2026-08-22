/**
 * Server-side adapter to the FastAPI backend. The browser never talks to
 * :8000; Next API routes call this module, which owns a per-run WebSocket
 * and replays events into a frontend RunSnapshot.
 */
import "server-only";

import WS, { type RawData } from "ws";
import { errorFromBody, errorFromResponse } from "./httpError";
import { assign, bandById, isolationPairs } from "./placement";
import type { RunSnapshot } from "./runner";
import { keepoutFor } from "./rf";
import { hydrateSpec } from "./specHydrate";
import type {
  AgentMessage,
  Candidate,
  DeviceSpec,
  Job,
  SimResult,
} from "./types";

export type AgentMode = "mock" | "devin" | "local";

export interface RunEvent {
  run_id: string;
  seq: number;
  ts: number;
  stage: string;
  type: string;
  payload: Record<string, unknown>;
}

interface Session {
  events: RunEvent[];
  ws: WS | null;
  lastSeq: number;
  status: string;
  bandIds: string[];
  reconnectAttempt: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
}

const sessions = new Map<string, Session>();

export function backendBase(): string {
  return (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
}

function wsBase(): string {
  const http = backendBase();
  if (http.startsWith("https://")) return `wss://${http.slice("https://".length)}`;
  if (http.startsWith("http://")) return `ws://${http.slice("http://".length)}`;
  return http;
}

function rawToString(data: RawData): string {
  if (typeof data === "string") return data;
  if (Buffer.isBuffer(data)) return data.toString("utf8");
  if (Array.isArray(data)) return Buffer.concat(data).toString("utf8");
  return Buffer.from(data).toString("utf8");
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

export async function createRun(
  prompt: string,
  bands: string[],
  agentMode: Exclude<AgentMode, "local">,
  deviceId?: string | null,
): Promise<{ runId: string }> {
  const body: Record<string, unknown> = {
    prompt,
    bands,
    agent: agentMode,
  };
  if (deviceId) body.device_id = deviceId;

  let res: Response;
  try {
    res = await fetch(`${backendBase()}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch (e) {
    throw new Error(
      `backend unreachable at ${backendBase()}: ${e instanceof Error ? e.message : String(e)}`,
    );
  }

  const json: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw Object.assign(new Error(errorFromBody(json, `HTTP ${res.status}`)), {
      status: res.status,
    });
  }

  const runId = String(asRecord(json).run_id ?? "");
  if (!runId) throw new Error("backend did not return run_id");

  sessions.set(runId, {
    events: [],
    ws: null,
    lastSeq: 0,
    status: "running",
    bandIds: bands,
    reconnectAttempt: 0,
    reconnectTimer: null,
  });
  connectWs(runId);
  return { runId };
}

export async function readRun(runId: string): Promise<RunSnapshot> {
  let session = sessions.get(runId);
  if (!session) {
    session = {
      events: [],
      ws: null,
      lastSeq: 0,
      status: "running",
      bandIds: [],
      reconnectAttempt: 0,
      reconnectTimer: null,
    };
    sessions.set(runId, session);
  }
  if (session.status === "running") connectWs(runId);

  let res: Response;
  try {
    res = await fetch(`${backendBase()}/runs/${encodeURIComponent(runId)}`, {
      cache: "no-store",
    });
  } catch (e) {
    throw new Error(
      `backend unreachable at ${backendBase()}: ${e instanceof Error ? e.message : String(e)}`,
    );
  }

  if (res.status === 404) {
    session.status = "failed";
    closeWs(runId);
    const err = new Error(await errorFromResponse(res, "unknown run"));
    (err as Error & { status?: number }).status = 404;
    throw err;
  }
  if (!res.ok) {
    const err = new Error(await errorFromResponse(res, `HTTP ${res.status}`));
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }

  const snap = asRecord(await res.json());
  session.status = String(snap.status ?? session.status);
  if (!session.bandIds.length) {
    const spec = snap.spec ? hydrateSpec(snap.spec as DeviceSpec) : null;
    session.bandIds = spec?.requirements.bands.map((b) => b.id) ?? [];
  }
  if (session.status !== "running") closeWs(runId);

  return adaptSnapshot(runId, snap, session);
}

function connectWs(runId: string) {
  const session = sessions.get(runId);
  if (!session) return;
  if (
    session.ws &&
    (session.ws.readyState === WS.OPEN || session.ws.readyState === WS.CONNECTING)
  ) {
    return;
  }
  if (session.reconnectTimer) {
    clearTimeout(session.reconnectTimer);
    session.reconnectTimer = null;
  }

  const url = `${wsBase()}/runs/${encodeURIComponent(runId)}/events?since=${session.lastSeq}`;
  let ws: WS;
  try {
    ws = new WS(url);
  } catch {
    scheduleReconnect(runId);
    return;
  }
  session.ws = ws;

  ws.on("message", (data) => {
    const sessionNow = sessions.get(runId);
    if (!sessionNow) return;
    let ev: RunEvent;
    try {
      ev = JSON.parse(rawToString(data)) as RunEvent;
    } catch {
      return;
    }
    if (typeof ev.seq !== "number" || ev.seq <= sessionNow.lastSeq) return;
    sessionNow.events.push(ev);
    sessionNow.lastSeq = ev.seq;
    sessionNow.reconnectAttempt = 0;
    if (ev.type === "run_finished") {
      const payload = asRecord(ev.payload);
      sessionNow.status =
        payload.status === "failed" ? "failed" : "finished";
    }
  });

  ws.on("close", (code) => {
    const sessionNow = sessions.get(runId);
    if (!sessionNow || sessionNow.ws !== ws) return;
    sessionNow.ws = null;
    if (code === 4404) {
      sessionNow.status = "failed";
      return;
    }
    if (sessionNow.status === "running") scheduleReconnect(runId);
  });

  ws.on("error", () => {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  });
}

function scheduleReconnect(runId: string) {
  const session = sessions.get(runId);
  if (!session || session.status !== "running") return;
  if (session.reconnectTimer) return;
  const delay = Math.min(8000, 500 * 2 ** session.reconnectAttempt);
  session.reconnectAttempt += 1;
  session.reconnectTimer = setTimeout(() => {
    const s = sessions.get(runId);
    if (!s) return;
    s.reconnectTimer = null;
    if (s.status === "running") connectWs(runId);
  }, delay);
}

function closeWs(runId: string) {
  const session = sessions.get(runId);
  if (!session) return;
  if (session.reconnectTimer) {
    clearTimeout(session.reconnectTimer);
    session.reconnectTimer = null;
  }
  if (session.ws) {
    const ws = session.ws;
    session.ws = null;
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  }
}

function adaptCandidate(raw: Record<string, unknown>, spec: DeviceSpec): Candidate {
  const bandId = String(raw.band_id ?? "");
  let keepout = raw.keepout_mm as Candidate["keepout_mm"] | undefined;
  if (!keepout) {
    try {
      const band = bandById(spec, bandId);
      keepout = keepoutFor(band, raw.position_mm as Candidate["position_mm"]);
    } catch {
      keepout = [
        [0, 0, 0],
        [0, 0, 0],
      ];
    }
  }
  return {
    candidate_id: String(raw.candidate_id ?? ""),
    anchor_id: String(raw.anchor_id ?? ""),
    band_id: bandId,
    antenna_type: raw.antenna_type as Candidate["antenna_type"],
    position_mm: raw.position_mm as Candidate["position_mm"],
    feed_point_mm: raw.feed_point_mm as Candidate["feed_point_mm"],
    length_mm: Number(raw.length_mm ?? 0),
    orientation: (raw.orientation as Candidate["orientation"]) ?? "edge",
    keepout_mm: keepout,
    prior: Number(raw.prior ?? 0),
    rationale: String(raw.rationale ?? ""),
  };
}

function adaptResult(raw: Record<string, unknown>): SimResult {
  return {
    candidate_id: String(raw.candidate_id ?? ""),
    status: (raw.status as SimResult["status"]) ?? "complete",
    runtime_s: Number(raw.runtime_s ?? 0),
    s11_curve: Array.isArray(raw.s11_curve)
      ? (raw.s11_curve as SimResult["s11_curve"])
      : [],
    s11_min_db: Number(raw.s11_min_db ?? 0),
    resonant_ghz: Number(raw.resonant_ghz ?? 0),
    bandwidth_mhz: Number(raw.bandwidth_mhz ?? 0),
    efficiency: Number(raw.efficiency ?? 0),
    peak_gain_dbi: Number(raw.peak_gain_dbi ?? 0),
    vswr: Number(raw.vswr ?? 0),
    sar_w_per_kg: Number(raw.sar_w_per_kg ?? 0),
    meets_requirements: Boolean(raw.meets_requirements),
    notes: String(raw.notes ?? ""),
  };
}

function adaptSnapshot(
  runId: string,
  snap: Record<string, unknown>,
  session: Session,
): RunSnapshot {
  const spec = hydrateSpec((snap.spec as DeviceSpec) ?? ({} as DeviceSpec));
  const candDict = asRecord(snap.candidates);
  const resultDict = asRecord(snap.results);

  const candMap = new Map<string, Candidate>();
  for (const raw of Object.values(candDict)) {
    const c = adaptCandidate(asRecord(raw), spec);
    if (c.candidate_id) candMap.set(c.candidate_id, c);
  }
  for (const ev of session.events) {
    if (ev.type !== "candidates_proposed") continue;
    const list = ev.payload.candidates;
    if (!Array.isArray(list)) continue;
    for (const item of list) {
      const c = adaptCandidate(asRecord(item), spec);
      if (c.candidate_id) candMap.set(c.candidate_id, c);
    }
  }

  const results: Record<string, SimResult> = {};
  for (const [id, raw] of Object.entries(resultDict)) {
    results[id] = adaptResult(asRecord(raw));
  }
  for (const ev of session.events) {
    if (ev.type !== "sim_result") continue;
    const r = adaptResult(ev.payload);
    if (r.candidate_id) results[r.candidate_id] = r;
  }

  const startedAt = new Map<string, number>();
  const startedBand = new Map<string, string>();
  const finishedAt = new Map<string, number>();
  for (const ev of session.events) {
    if (ev.type === "sim_started") {
      const cid = String(ev.payload.candidate_id ?? "");
      if (!cid) continue;
      startedAt.set(cid, ev.ts * 1000);
      startedBand.set(cid, String(ev.payload.band_id ?? ""));
    }
    if (ev.type === "sim_result") {
      const cid = String(ev.payload.candidate_id ?? "");
      if (cid) finishedAt.set(cid, ev.ts * 1000);
    }
  }

  const now = Date.now();
  const jobs: Job[] = [];
  for (const c of candMap.values()) {
    const r = results[c.candidate_id];
    let status: Job["status"] = "queued";
    let progress = 0;
    if (r?.status === "failed") {
      status = "failed";
      progress = 1;
    } else if (r?.status === "complete" || finishedAt.has(c.candidate_id)) {
      status = "complete";
      progress = 1;
    } else if (startedAt.has(c.candidate_id) || r?.status === "running") {
      status = "running";
      const t0 = startedAt.get(c.candidate_id);
      progress = t0
        ? Math.min(0.95, Math.max(0.15, (now - t0) / 30_000))
        : 0.5;
    }
    jobs.push({
      job_id: `${runId}__${c.candidate_id}`,
      candidate_id: c.candidate_id,
      band_id: startedBand.get(c.candidate_id) || c.band_id,
      status,
      progress: +progress.toFixed(3),
      started_at: startedAt.get(c.candidate_id),
      finished_at: finishedAt.get(c.candidate_id),
    });
  }

  const candidates = [...candMap.values()];
  const bandIds =
    session.bandIds.length > 0
      ? session.bandIds
      : [...new Set(candidates.map((c) => c.band_id))];

  const { placements } = assign(
    { bandIds, spec, candidates },
    jobs,
    results,
  );
  const isolation = isolationPairs(spec, candidates, placements);

  const status = String(snap.status ?? session.status);
  const stage = String(snap.stage ?? "");
  const truncated = Boolean(snap.truncated);
  const final = asRecord(snap.final);
  const rationale =
    typeof final.rationale === "string" ? final.rationale : undefined;

  let error: string | undefined;
  for (const ev of session.events) {
    if (ev.type !== "error") continue;
    const p = ev.payload;
    const msg =
      (typeof p.error === "string" && p.error) ||
      (typeof p.protocol === "string" && p.protocol) ||
      JSON.stringify(p);
    error = msg;
  }
  if (status === "failed" && !error) error = "run failed";

  return {
    runId,
    done: status === "finished" || status === "failed",
    planning: stage === "extract" || stage === "spec",
    jobs,
    results,
    candidates,
    messages: buildMessages(session.events, candidates, results, spec, rationale),
    placements,
    isolation,
    truncated,
    error,
    rationale,
  };
}

function buildMessages(
  events: RunEvent[],
  candidates: Candidate[],
  results: Record<string, SimResult>,
  spec: DeviceSpec,
  rationale?: string,
): AgentMessage[] {
  const byId = new Map(candidates.map((c) => [c.candidate_id, c]));
  const out: AgentMessage[] = [];

  for (const ev of events) {
    const ts = Math.round(ev.ts * 1000);
    const id = String(ev.seq);
    if (ev.type === "agent_message") {
      const role = ev.payload.role === "user" ? "user" : "agent";
      out.push({
        id,
        role,
        kind: "text",
        text: String(ev.payload.text ?? ""),
        ts,
      });
      continue;
    }
    if (ev.type === "sim_result") {
      const r = adaptResult(ev.payload);
      const cand = byId.get(r.candidate_id);
      const band = cand
        ? spec.requirements.bands.find((b) => b.id === cand.band_id)
        : undefined;
      const text = cand
        ? `${cand.candidate_id}: S11 ${r.s11_min_db.toFixed(1)} dB at ${r.resonant_ghz.toFixed(2)} GHz, ` +
          `BW ${r.bandwidth_mhz} MHz, eff ${(r.efficiency * 100).toFixed(0)}%, gain ${r.peak_gain_dbi} dBi` +
          `${band ? ` (${band.name})` : ""} -> ${r.meets_requirements ? "PASS" : "FAIL"}. ${r.notes}`
        : `${r.candidate_id}: S11 ${r.s11_min_db.toFixed(1)} dB -> ${r.meets_requirements ? "PASS" : "FAIL"}. ${r.notes}`;
      out.push({ id, role: "agent", kind: "result", text, ts });
      continue;
    }
    if (
      ev.type === "stage_started" ||
      ev.type === "decision" ||
      ev.type === "candidates_proposed" ||
      ev.type === "iteration_scored"
    ) {
      out.push({
        id,
        role: "agent",
        kind: "step",
        text: stepText(ev, results),
        ts,
      });
    }
  }

  if (rationale) {
    const lastTs = out.length ? out[out.length - 1].ts + 1 : Date.now();
    out.push({
      id: "rationale",
      role: "agent",
      kind: "text",
      text: rationale,
      ts: lastTs,
    });
  }
  return out;
}

function stepText(ev: RunEvent, results: Record<string, SimResult>): string {
  const p = ev.payload;
  if (ev.type === "stage_started") {
    const stage = String(p.stage ?? ev.stage);
    if (stage === "extract") return "Extracting geometry from the build file...";
    if (stage === "spec") return "Assembling the device spec and placement anchors...";
    if (stage === "agent_loop") return "Agent loop started — proposing placements.";
    if (stage === "report") return "Writing the engineering report...";
    return `Starting ${stage}.`;
  }
  if (ev.type === "decision") {
    return String(p.decision ?? p.rationale ?? "decision");
  }
  if (ev.type === "candidates_proposed") {
    const n = Array.isArray(p.candidates) ? p.candidates.length : 0;
    const sweep = p.sweep ? " sweep" : "";
    return `Proposed ${n} candidate${n === 1 ? "" : "s"} (iteration ${p.iteration ?? "?"}${sweep}).`;
  }
  if (ev.type === "iteration_scored") {
    const reports = Array.isArray(p.reports) ? p.reports : [];
    const best =
      typeof p.best_so_far === "string"
        ? p.best_so_far
        : reports[0] && typeof reports[0] === "object"
          ? String(asRecord(reports[0]).candidate_id ?? "")
          : "";
    const r = best ? results[best] : undefined;
    const scoreBit = r
      ? ` best ${best} at ${r.s11_min_db.toFixed(1)} dB`
      : best
        ? ` best ${best}`
        : "";
    return `Scored iteration ${p.iteration ?? "?"}${scoreBit}. Trend: ${p.trend ?? "n/a"}.`;
  }
  return ev.type;
}
