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

  // <video> does not fetch a file, it asks for byte ranges. The backend answers
  // them correctly (206 + Content-Range), but this proxy used to drop the
  // Range header on the way in and the range headers on the way out, so every
  // request came back as a bare 200 with no Content-Length. Browsers will not
  // scrub — and often will not start — a video served that way, which is why
  // the field and dashboard clips would not play while the PNGs were fine.
  const range = _req.headers.get("range");

  let upstream: Response;
  try {
    upstream = await fetch(
      `${BACKEND_URL}/runs/${encodeURIComponent(runId)}/media/${encodeURIComponent(name)}`,
      { cache: "no-store", headers: range ? { range } : undefined },
    );
  } catch {
    return new Response(`backend unreachable at ${BACKEND_URL}`, { status: 503 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response("no such artifact", { status: upstream.status || 404 });
  }

  const headers = new Headers({
    "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
    // Artifacts are written once and never rewritten under the same run id, so
    // they are safe to cache hard — which matters for a multi-megabyte clip the
    // viewer may scrub back and forth.
    "cache-control": "public, max-age=31536000, immutable",
    "accept-ranges": upstream.headers.get("accept-ranges") ?? "bytes",
  });
  for (const h of ["content-length", "content-range"]) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, v);
  }
  // 206 must be preserved: rewriting it to 200 tells the browser the partial
  // body is the whole file.
  return new Response(upstream.body, { status: upstream.status, headers });
}
