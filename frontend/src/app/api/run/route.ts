/**
 * Run endpoint — real backend first, local heuristic only as a labelled fallback.
 *
 * Previously this route called `createRun` from `@/lib/runner`, which runs
 * `simulate()` from `@/lib/rf` — a TypeScript heuristic. The UI was therefore
 * simulating itself: no agent, no electromagnetics. `@/lib/backend` talks to
 * the FastAPI service (real Devin or mock agent, real PyNEC solves, real
 * device geometry); the heuristic stays reachable so the UI still runs with
 * the backend down, but every response says which one produced it.
 *
 *   POST  {prompt, bands, agent?, deviceId?}  -> {runId, source, warning?}
 *   GET   ?runId=                             -> RunSnapshot + source
 *   PATCH {runId, text}                       -> mid-run note for the agent (backend runs only)
 */
import { NextResponse } from "next/server";

import {
  AGENT,
  createBackendRun,
  postBackendMessage,
  readBackendLog,
  readBackendRun,
  toSnapshot,
} from "@/lib/backend";
import { createRun, readRun } from "@/lib/runner";

export const dynamic = "force-dynamic";

/** runId -> which engine served it, so GET routes to the same place as POST. */
const backendRuns = new Set<string>();

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const bands: string[] = Array.isArray(body.bands) ? body.bands : [];
  const prompt: string = typeof body.prompt === "string" ? body.prompt : "";
  if (!bands.length) {
    return NextResponse.json({ error: "no bands selected" }, { status: 400 });
  }
  const agent = body.agent === "devin" ? "devin" : body.agent === "mock" ? "mock" : AGENT;
  const deviceId: string | null = typeof body.deviceId === "string" ? body.deviceId : null;

  try {
    const runId = await createBackendRun(prompt, bands, agent, deviceId);
    backendRuns.add(runId);
    return NextResponse.json({ runId, source: "backend", agent });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    // The backend answered but refused (no Devin credentials, unknown device,
    // bad band): that is a real error the user must see, not a reason to
    // quietly show a different engine.
    if (/^backend \d{3}/.test(msg)) {
      return NextResponse.json({ error: msg }, { status: 502 });
    }
    // Backend down: fall back, but never pretend.
    const { runId } = createRun(prompt, bands, body.perBand ?? 6, body.overrides);
    return NextResponse.json({
      runId,
      source: "heuristic",
      agent: "heuristic",
      warning:
        `backend unavailable (${msg}); ` +
        `showing the local heuristic solver, not a real simulation`,
    });
  }
}

export async function GET(req: Request) {
  const runId = new URL(req.url).searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });

  if (backendRuns.has(runId)) {
    try {
      const [run, events] = await Promise.all([readBackendRun(runId), readBackendLog(runId)]);
      return NextResponse.json(toSnapshot(run, events));
    } catch (err) {
      return NextResponse.json(
        { error: `backend run ${runId} unreadable: ${err instanceof Error ? err.message : err}` },
        { status: 502 },
      );
    }
  }

  const snap = readRun(runId);
  if (!snap) return NextResponse.json({ error: "unknown run" }, { status: 404 });
  return NextResponse.json({ ...snap, source: "heuristic" });
}

export async function PATCH(req: Request) {
  const body = await req.json().catch(() => ({}));
  const runId: string = typeof body.runId === "string" ? body.runId : "";
  const text: string = typeof body.text === "string" ? body.text.trim() : "";
  if (!runId || !text) return NextResponse.json({ error: "runId and text required" }, { status: 400 });
  if (!backendRuns.has(runId)) {
    return NextResponse.json(
      { error: "notes reach the agent only on backend runs; the heuristic has nobody to talk to" },
      { status: 409 },
    );
  }
  try {
    await postBackendMessage(runId, text);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
