/**
 * Device endpoint.
 *
 *   GET                      -> the built-in Handset A (spec + anchors), for the viewer's default
 *   POST multipart           -> passthrough to backend POST /devices: .blend (+ materials.json)
 *                               in, spec + anchors + artifact list out, plus a same-origin
 *                               URL for device.glb so the viewer can load it without CORS
 *   GET ?id=&artifact=name   -> streams that artifact from the backend
 *
 * Extraction needs the backend's Python 3.11 + bpy interpreter (see
 * backend/README.md); when it has none the backend says so and that error is
 * returned verbatim rather than swapped for a different device.
 */
import { NextResponse } from "next/server";

import { BACKEND_URL, normalizeSpec, uploadBackendDevice } from "@/lib/backend";
import { anchors, phoneV1 } from "@/lib/device";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  const artifact = url.searchParams.get("artifact");
  if (!id || !artifact) return NextResponse.json({ spec: phoneV1, anchors });

  const res = await fetch(`${BACKEND_URL}/devices/${id}/artifacts/${artifact}`, {
    cache: "no-store",
  }).catch((e: unknown) => e);
  if (!(res instanceof Response)) {
    return NextResponse.json({ error: `backend unreachable at ${BACKEND_URL}` }, { status: 503 });
  }
  if (!res.ok) {
    return NextResponse.json({ error: await res.text() }, { status: res.status });
  }
  return new Response(res.body, {
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": "no-store",
    },
  });
}

export async function POST(req: Request) {
  const form = await req.formData().catch(() => null);
  const blend = form?.get("blend");
  if (!form || !(blend instanceof File)) {
    return NextResponse.json({ error: "multipart field 'blend' (.blend file) required" }, { status: 400 });
  }
  try {
    const dev = await uploadBackendDevice(form);
    if (dev.status !== "ready" || !dev.spec) {
      return NextResponse.json(
        { error: `extraction ${dev.status}: ${dev.error ?? "no spec"}` },
        { status: 422 },
      );
    }
    return NextResponse.json({
      deviceId: dev.device_id,
      spec: normalizeSpec(dev.spec),
      anchors: dev.anchors,
      ambiguities: dev.ambiguities,
      artifacts: dev.artifacts,
      glbUrl: dev.artifacts.includes("device.glb")
        ? `/api/device?id=${encodeURIComponent(dev.device_id)}&artifact=device.glb`
        : null,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: /^backend \d{3}/.test(msg) ? msg : `backend unreachable at ${BACKEND_URL}` },
      { status: /^backend \d{3}/.test(msg) ? 502 : 503 },
    );
  }
}
