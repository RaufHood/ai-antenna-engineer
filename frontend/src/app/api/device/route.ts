import { NextResponse } from "next/server";
import { anchors, phoneV1 } from "@/lib/device";

export async function GET() {
  return NextResponse.json({ spec: phoneV1, anchors });
}
