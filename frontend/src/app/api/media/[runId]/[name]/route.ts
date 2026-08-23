/**
 * Rendered evidence — a streaming proxy to the backend's media artifacts.
 *
 * The browser never talks to port 8000 directly (`BACKEND_URL` is
 * server-side), and these are binaries: a placement map is ~300 KB, a field
 * animation is megabytes. So the body is piped through untouched rather than
 * buffered and re-encoded, and the upstream content-type is preserved so a
 * <video> gets video/mp4 and an <img> gets image/png.
 */
import { BACKEND_URL } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ runId: string; name: string }> },
) {
  const { runId, name } = await params;
  // The backend refuses anything that escapes the run's own media directory;
  // reject the obvious traversal here too rather than forwarding it.
  if (name.includes("/") || name.includes("..")) {
    return new Response("bad artifact name", { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(
      `${BACKEND_URL}/runs/${encodeURIComponent(runId)}/media/${encodeURIComponent(name)}`,
      { cache: "no-store" },
    );
  } catch {
    return new Response(`backend unreachable at ${BACKEND_URL}`, { status: 503 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response("no such artifact", { status: upstream.status || 404 });
  }
  return new Response(upstream.body, {
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
      // Artifacts are written once and never rewritten under the same run id,
      // so they are safe to cache hard — which matters for a multi-megabyte
      // animation the user may scrub back and forth.
      "cache-control": "public, max-age=31536000, immutable",
    },
  });
}
