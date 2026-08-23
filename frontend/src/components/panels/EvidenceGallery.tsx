"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MediaArtifact } from "@/lib/backend";
import { useApp } from "@/lib/store";

/**
 * The rendered evidence for this run — the placement maps, the winner drawn
 * inside the real mesh, its S11, and the field leaving it.
 *
 * These are the artifacts an RF engineer hands to a mechanical engineer, so
 * they are shown at a size worth looking at. The dock is short, so the strip
 * holds thumbnails and the full view opens in a <dialog>: a modal is usually
 * laziness, but an image gallery is the case where the artifact genuinely has
 * to escape a 280 px rail, and <dialog> escapes the dock's overflow clipping
 * without a portal.
 *
 * The field clip is delivered as MP4 rather than the GIF beside it — same
 * frames, a third of the bytes, and it gets scrubbing and a loop for free.
 */

function isVideo(a: MediaArtifact) {
  return a.name.endsWith(".mp4");
}

/** Prefer the MP4 of a field pair and drop the GIF: they are the same frames. */
function preferred(media: MediaArtifact[]): MediaArtifact[] {
  const mp4s = new Set(media.filter(isVideo).map((a) => a.name.replace(/\.mp4$/, "")));
  return media.filter((a) => !(a.name.endsWith(".gif") && mp4s.has(a.name.replace(/\.gif$/, ""))));
}

/** How many artifacts the gallery will actually show. The tab label must
 *  agree with what is on screen: counting the raw list said 18 while the
 *  groups showed 12, because each clip ships as an mp4 and a gif of the same
 *  frames and only the mp4 is displayed. */
export function shownCount(media: MediaArtifact[]): number {
  return preferred(media).length;
}

function Frame({ art, className = "" }: { art: MediaArtifact; className?: string }) {
  if (isVideo(art)) {
    return (
      // Muted + playsInline so autoplay is allowed everywhere; controls stay
      // on because scrubbing a wavefront is the point of having it.
      <video
        src={art.url}
        className={className}
        autoPlay
        loop
        muted
        playsInline
        controls
        preload="metadata"
      />
    );
  }
  // eslint-disable-next-line @next/next/no-img-element -- proxied binary, not a static asset
  return <img src={art.url} alt={art.title} className={className} loading="lazy" />;
}

function Lightbox({
  art,
  onClose,
  onStep,
}: {
  art: MediaArtifact;
  onClose: () => void;
  onStep: (delta: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && !el.open) el.showModal();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") onStep(1);
      if (e.key === "ArrowLeft") onStep(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onStep]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        // Click the backdrop — the dialog element itself — to dismiss.
        if (e.target === ref.current) ref.current?.close();
      }}
      className="max-h-[92vh] max-w-[92vw] rounded-lg border border-ink-700 bg-ink-900 p-0 text-fg backdrop:bg-ink-950/85 backdrop:backdrop-blur-sm"
    >
      <div className="flex max-h-[92vh] flex-col">
        <div className="flex shrink-0 items-start gap-4 border-b border-ink-800 px-5 py-3.5">
          <div className="min-w-0">
            <h2 className="text-[13px] font-semibold text-fg">{art.title}</h2>
            <p className="mt-1 max-w-[68ch] text-[11px] leading-5 text-fg-muted">{art.caption}</p>
          </div>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            aria-label="Close"
            className="-mr-1 ml-auto shrink-0 rounded-md p-1.5 text-fg-faint transition hover:bg-ink-800 hover:text-fg"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-ink-950 p-5">
          <Frame art={art} className="mx-auto max-h-[70vh] w-auto max-w-full rounded" />
        </div>
      </div>
    </dialog>
  );
}

export function EvidenceGallery() {
  const media = useApp((s) => s.media);
  const stage = useApp((s) => s.stage);
  const running = useApp((s) => s.running);
  const [open, setOpen] = useState<number | null>(null);
  const bands = useApp((s) => s.spec.requirements.bands);

  const items = preferred(media);
  const step = useCallback(
    (delta: number) =>
      setOpen((i) => (i === null ? i : (i + delta + items.length) % items.length)),
    [items.length],
  );

  if (!items.length) {
    const rendering = stage === "media" || running;
    return (
      <div className="flex h-full items-center justify-center px-6">
        <p className="max-w-[40ch] text-center text-[12px] leading-5 text-fg-muted">
          {rendering ? (
            "Rendering evidence…"
          ) : (
            "No evidence was rendered for this run — the transcript says why."
          )}
        </p>
      </div>
    );
  }

  // A multi-band run is several antenna designs, and every picture belongs to
  // exactly one of them. Grouping by band is the difference between a gallery
  // and a pile: you read one antenna's evidence at a time.
  const groups: { band: string; label: string; items: MediaArtifact[] }[] = [];
  for (const art of items) {
    const key = art.band_id || "";
    let g = groups.find((x) => x.band === key);
    if (!g) {
      const band = bands.find((b) => b.id === key);
      g = { band: key, label: band?.short ?? band?.name ?? "This run", items: [] };
      groups.push(g);
    }
    g.items.push(art);
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      {groups.map((g) => (
        <section key={g.band} className="mb-4 last:mb-0">
          <h3 className="mb-2 flex items-baseline gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-fg-faint">
            {g.label}
            <span className="font-mono text-[10px] font-normal normal-case tracking-normal text-fg-faint/70">
              {g.items.length} artifacts
            </span>
          </h3>
          <ul className="flex gap-3 overflow-x-auto pb-1">
            {g.items.map((art) => {
              const i = items.indexOf(art);
              return (
          <li key={art.name} className="shrink-0">
            <button
              type="button"
              onClick={() => setOpen(i)}
              className="group flex h-[210px] w-[186px] flex-col overflow-hidden rounded-md border border-ink-800 bg-ink-900 text-left transition hover:border-ink-600"
            >
              <span className="relative min-h-0 flex-1 bg-ink-950">
                <Frame
                  art={art}
                  className="h-full w-full object-cover object-top opacity-90 transition group-hover:opacity-100"
                />
                {isVideo(art) && (
                  <span className="absolute right-1.5 top-1.5 rounded bg-ink-950/75 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-fg-muted">
                    clip
                  </span>
                )}
              </span>
              <span className="shrink-0 truncate border-t border-ink-800 px-2.5 py-1.5 text-[11px] text-fg-muted transition group-hover:text-fg">
                {art.title.split(" — ")[0]}
              </span>
            </button>
          </li>
              );
            })}
          </ul>
        </section>
      ))}
      {open !== null && items[open] && (
        <Lightbox art={items[open]} onClose={() => setOpen(null)} onStep={step} />
      )}
    </div>
  );
}
