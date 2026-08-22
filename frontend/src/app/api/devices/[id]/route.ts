import { NextResponse } from "next/server";
import { backendBase } from "@/lib/backend";
import { errorFromBody } from "@/lib/httpError";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  try {
    const res = await fetch(
      `${backendBase()}/devices/${encodeURIComponent(id)}`,
      { cache: "no-store" },
    );
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
