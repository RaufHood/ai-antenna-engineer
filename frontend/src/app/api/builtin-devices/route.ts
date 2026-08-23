/**
 * The devices that ship with the app. A thin proxy, like every backend call
 * here; the client uses it to populate the device picker.
 */
import { NextResponse } from "next/server";

import { BACKEND_URL } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/builtin-devices`, { cache: "no-store" });
    if (!res.ok) return NextResponse.json([]);
    return NextResponse.json(await res.json());
  } catch {
    // Backend down: no picker, which the panel handles by showing the one
    // device it already has.
    return NextResponse.json([]);
  }
}
