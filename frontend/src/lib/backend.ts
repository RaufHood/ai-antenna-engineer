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
 *   POST /runs        {prompt, bands, agent}  -> {run_id}
 *   GET  /runs/{id}                           -> {status, candidates, results, final, ...}
 *
 * `BACKEND_URL` (server-side env, defaults to http://127.0.0.1:8000) points at
 * it. When the backend is unreachable the caller falls back to the local
 * heuristic and says so, rather than showing an empty screen — but the
 * fallback is labelled, never silent, because a mock that looks real is worse
 * than one that admits it.
 */
import type { Candidate, Job, SimResult } from "./types";

export const BACKEND_URL =
  process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";

/** Which agent drives the loop. "devin" needs backend/.env credentials. */
export const AGENT: "devin" | "mock" =
  (process.env.AGENT as "devin" | "mock") ?? "mock";

const TIMEOUT_MS = 8000;

export type BackendRun = {
  run_id: string;
  status: "running" | "finished" | "failed";
  stage: string;
  iteration: number;
  candidates: Record<string, Candidate>;
  results: Record<string, SimResult>;
  artifacts: string[];
  final: Record<string, unknown> | null;
  spec_source: string;
};

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
  agent: "devin" | "mock" = AGENT,
): Promise<string> {
  const body = JSON.stringify({ prompt, bands, agent });
  const out = await call<{ run_id: string }>("/runs", { method: "POST", body });
  return out.run_id;
}

export async function readBackendRun(runId: string): Promise<BackendRun> {
  return call<BackendRun>(`/runs/${runId}`);
}

/**
 * Backend run -> the snapshot shape the UI store already consumes.
 *
 * The backend has no notion of "queued/running" per candidate: a candidate
 * exists once proposed and gains a result once solved. That maps cleanly onto
 * the Job states the UI draws, so the progress view keeps working.
 */
export function toSnapshot(run: BackendRun) {
  const jobs: Job[] = Object.values(run.candidates).map((c) => {
    const r = run.results[c.candidate_id];
    return {
      candidate_id: c.candidate_id,
      status: r ? (r.status === "failed" ? "failed" : "complete") : "running",
      progress: r ? 1 : 0.5,
    } as Job;
  });

  return {
    runId: run.run_id,
    planning: run.stage !== "agent_loop" && run.status === "running",
    done: run.status !== "running",
    status: run.status,
    stage: run.stage,
    iteration: run.iteration,
    jobs,
    candidates: Object.values(run.candidates),
    results: run.results,
    final: run.final,
    artifacts: run.artifacts,
    // What the UI should say out loud, so nobody mistakes one for the other.
    source: "backend" as const,
    engine: `PyNEC via ${BACKEND_URL}`,
  };
}
