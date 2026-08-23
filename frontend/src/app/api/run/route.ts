/**
 * Run endpoint — a thin proxy to the backend. The browser never talks to
 * port 8000 directly; `BACKEND_URL` is server-side.
 *
 *   POST  {prompt, bands, agent?, deviceId?, media?}  -> {runId, agent}
 *   GET   ?runId=                             -> RunSnapshot
 *   GET   ?runId=&artifact=report.md          -> the agent's report, as text
 *   PATCH {runId, text}                       -> mid-run note for the agent
 *   DELETE ?runId=                            -> stop the run (backend cancels the loop and
 *                                                terminates the agent session)
 *
 * A backend that is down is reported as such (503) — there is no local
 * stand-in, so nothing on screen can be mistaken for a simulation.
 */
import { NextResponse } from "next/server";

import {
  AGENT,
  type AgentKind,
  BACKEND_URL,
  createBackendRun,
  postBackendMessage,
  readBackendLog,
  readBackendReport,
  readBackendRun,
  stopBackendRun,
  toSnapshot,
} from "@/lib/backend";

export const dynamic = "force-dynamic";

function fail(err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  // "backend NNN: ..." is the backend refusing (no Devin credentials, unknown
  // device, bad band) — pass it through. Anything else is the backend not
  // answering at all.
  if (/^backend \d{3}/.test(msg)) return NextResponse.json({ error: msg }, { status: 502 });
  return NextResponse.json(
    { error: `backend unreachable at ${BACKEND_URL} — start it with \`cd backend && uv run uvicorn app.main:app --port 8000\`` },
    { status: 503 },
  );
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const bands: string[] = Array.isArray(body.bands) ? body.bands : [];
  const prompt: string = typeof body.prompt === "string" ? body.prompt : "";
  if (!bands.length) {
    return NextResponse.json({ error: "no bands selected" }, { status: 400 });
  }
  // "replay" used to fall through this ladder to AGENT, so picking the
  // recorded Devin run in the UI silently started the heuristic instead —
  // the one substitution this app must never make quietly.
  const agent: AgentKind =
    body.agent === "devin" || body.agent === "mock" || body.agent === "replay"
      ? body.agent
      : AGENT;
  const deviceId: string | null = typeof body.deviceId === "string" ? body.deviceId : null;
  const media: boolean = body.media === true;
  const builtin: string | null = typeof body.builtin === "string" ? body.builtin : null;

  try {
    const runId = await createBackendRun(prompt, bands, agent, deviceId, media, builtin);
    return NextResponse.json({ runId, agent });
  } catch (err) {
    return fail(err);
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });

  try {
    if (url.searchParams.get("artifact") === "report.md") {
      const text = await readBackendReport(runId);
      return new Response(text, {
        headers: { "content-type": "text/markdown; charset=utf-8", "cache-control": "no-store" },
      });
    }
    const [run, events] = await Promise.all([readBackendRun(runId), readBackendLog(runId)]);
    return NextResponse.json(toSnapshot(run, events));
  } catch (err) {
    return fail(err);
  }
}

export async function PATCH(req: Request) {
  const body = await req.json().catch(() => ({}));
  const runId: string = typeof body.runId === "string" ? body.runId : "";
  const text: string = typeof body.text === "string" ? body.text.trim() : "";
  if (!runId || !text) return NextResponse.json({ error: "runId and text required" }, { status: 400 });
  try {
    await postBackendMessage(runId, text);
    return NextResponse.json({ ok: true });
  } catch (err) {
    return fail(err);
  }
}

export async function DELETE(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });
  try {
    return NextResponse.json(await stopBackendRun(runId));
  } catch (err) {
    return fail(err);
  }
}
