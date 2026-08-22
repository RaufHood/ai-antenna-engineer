/**
 * Run endpoint — real backend first, local heuristic only as a labelled fallback.
 *
 * Previously this route called `createRun` from `@/lib/runner`, which runs
 * `simulate()` from `@/lib/rf` — a TypeScript heuristic. The UI was therefore
 * simulating itself: no agent, no electromagnetics. `@/lib/backend` talks to
 * the FastAPI service (real Devin or mock agent, real PyNEC solves, real
 * device geometry); the heuristic stays reachable so the UI still runs with
 * the backend down, but every response says which one produced it.
 */
import { NextResponse } from "next/server";

import { AGENT, createBackendRun, readBackendRun, toSnapshot } from "@/lib/backend";
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

  try {
    const runId = await createBackendRun(prompt, bands, body.agent ?? AGENT);
    backendRuns.add(runId);
    return NextResponse.json({ runId, source: "backend" });
  } catch (err) {
    // Backend down or misconfigured: fall back, but never pretend.
    const { runId } = createRun(prompt, bands, body.perBand ?? 6, body.overrides);
    return NextResponse.json({
      runId,
      source: "heuristic",
      warning:
        `backend unavailable (${err instanceof Error ? err.message : String(err)}); ` +
        `showing the local heuristic solver, not a real simulation`,
    });
  }
}

export async function GET(req: Request) {
  const runId = new URL(req.url).searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });

  if (backendRuns.has(runId)) {
    try {
      return NextResponse.json(toSnapshot(await readBackendRun(runId)));
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
