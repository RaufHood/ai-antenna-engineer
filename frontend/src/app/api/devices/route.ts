import { NextResponse } from "next/server";
import { backendBase } from "@/lib/backend";
import { errorFromBody } from "@/lib/httpError";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 600;

export async function GET() {
  try {
    const res = await fetch(`${backendBase()}/devices`, { cache: "no-store" });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      return NextResponse.json(
        { error: errorFromBody(body, res.statusText) },
        { status: res.status },
      );
    }
    return NextResponse.json(body);
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 },
    );
  }
}

export async function POST(req: Request) {
  const contentType = req.headers.get("content-type");
  if (!contentType || !req.body) {
    return NextResponse.json({ error: "expected multipart body" }, { status: 400 });
  }
  try {
    const res = await fetch(`${backendBase()}/devices`, {
      method: "POST",
      headers: { "content-type": contentType },
      body: req.body,
      duplex: "half",
      cache: "no-store",
    } as RequestInit);
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      return NextResponse.json(
        { error: errorFromBody(body, res.statusText) },
        { status: res.status },
      );
    }
    return NextResponse.json(body);
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 },
    );
  }
}
