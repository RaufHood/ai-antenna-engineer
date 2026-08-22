import { NextResponse } from "next/server";
import { createRun as createBackendRun, readRun as readBackendRun } from "@/lib/backend";
import { createRun as createLocalRun, readRun as readLocalRun } from "@/lib/runner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const bands: string[] = Array.isArray(body.bands)
    ? body.bands.filter((b): b is string => typeof b === "string")
    : [];
  const prompt: string = typeof body.prompt === "string" ? body.prompt : "";
  if (!bands.length) {
    return NextResponse.json({ error: "no bands selected" }, { status: 400 });
  }

  const agent =
    body.agent === "devin" || body.agent === "local" || body.agent === "mock"
      ? body.agent
      : "mock";

  if (agent === "local") {
    const { runId } = createLocalRun(
      prompt,
      bands,
      typeof body.perBand === "number" ? body.perBand : 6,
      body.overrides as Parameters<typeof createLocalRun>[3],
    );
    return NextResponse.json({ runId });
  }

  try {
    const { runId } = await createBackendRun(
      prompt,
      bands,
      agent,
      typeof body.device_id === "string" ? body.device_id : null,
    );
    return NextResponse.json({ runId });
  } catch (e) {
    const status = (e as { status?: number }).status ?? 502;
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status },
    );
  }
}

export async function GET(req: Request) {
  const runId = new URL(req.url).searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });

  const local = readLocalRun(runId);
  if (local) return NextResponse.json(local);

  try {
    const snap = await readBackendRun(runId);
    return NextResponse.json(snap);
  } catch (e) {
    const status = (e as { status?: number }).status ?? 502;
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status },
    );
  }
}
