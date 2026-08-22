/** Normalise FastAPI `{detail}` and our `{error}` bodies into a single string. */
export function errorFromBody(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const o = body as Record<string, unknown>;
    if (typeof o.error === "string" && o.error) return o.error;
    if (typeof o.detail === "string" && o.detail) return o.detail;
    if (Array.isArray(o.detail)) {
      const parts = o.detail.map((d) => {
        if (d && typeof d === "object" && "msg" in d) {
          return String((d as { msg: unknown }).msg);
        }
        return String(d);
      });
      if (parts.length) return parts.join("; ");
    }
  }
  return fallback;
}

export async function errorFromResponse(res: Response, fallback: string): Promise<string> {
  const body: unknown = await res.json().catch(() => null);
  return errorFromBody(body, fallback || res.statusText || `HTTP ${res.status}`);
}
