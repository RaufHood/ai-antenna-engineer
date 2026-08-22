import { NextResponse } from "next/server";
import { backendBase } from "@/lib/backend";
import { errorFromBody } from "@/lib/httpError";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string; name: string[] }> },
) {
  const { id, name } = await ctx.params;
  const artifact = name.map(encodeURIComponent).join("/");
  try {
    const res = await fetch(
      `${backendBase()}/devices/${encodeURIComponent(id)}/artifacts/${artifact}`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      const body: unknown = await res.json().catch(() => null);
      return NextResponse.json(
        { error: errorFromBody(body, res.statusText) },
        { status: res.status },
      );
    }
    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "content-type":
          res.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": "public, max-age=60",
      },
    });
  } catch (e) {
    return NextResponse.json(
      { error: `backend unreachable: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 },
    );
  }
}
