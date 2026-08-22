import { NextResponse } from "next/server";
import { createRun, readRun } from "@/lib/runner";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const bands: string[] = Array.isArray(body.bands) ? body.bands : [];
  const prompt: string = typeof body.prompt === "string" ? body.prompt : "";
  if (!bands.length) {
    return NextResponse.json({ error: "no bands selected" }, { status: 400 });
  }
  const { runId } = createRun(prompt, bands, body.perBand ?? 6, body.overrides);
  return NextResponse.json({ runId });
}

export async function GET(req: Request) {
  const runId = new URL(req.url).searchParams.get("runId");
  if (!runId) return NextResponse.json({ error: "runId required" }, { status: 400 });
  const snap = readRun(runId);
  if (!snap) return NextResponse.json({ error: "unknown run" }, { status: 404 });
  return NextResponse.json(snap);
}
