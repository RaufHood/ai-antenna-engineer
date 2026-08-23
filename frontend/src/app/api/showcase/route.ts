/**
 * The pre-rendered Evidence gallery — a thin proxy, like every other backend
 * call here. The files themselves come through /api/media/_showcase/<name>,
 * which is the ordinary media route and therefore already speaks byte ranges.
 */
import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/showcase`, { cache: "no-store" });
    if (!res.ok) return NextResponse.json({ artifacts: [], built: false });
    return NextResponse.json(await res.json());
  } catch {
    // Backend down: no prepared gallery, which is a missing convenience and
    // never an error the user has to act on.
    return NextResponse.json({ artifacts: [], built: false });
  }
}
