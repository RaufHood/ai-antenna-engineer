"use client";

import dynamic from "next/dynamic";
import { useRef } from "react";
import { useApp } from "@/lib/store";
import { DeviceBadge, useDeviceDrop, useDeviceLoad } from "./DeviceBadge";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] text-fg-faint">
      loading 3D viewer…
    </div>
  ),
});

/**
 * The device and nothing else. Its name sits in the corner, with the one way
 * to replace it; every control that changes how it is drawn lives in the
 * View section of the inspector. The whole canvas is a drop target for a
 * build file.
 */
export function Viewport() {
  const fileRef = useRef<HTMLInputElement>(null);
  const { load, clear, problem } = useDeviceLoad();
  const { dragging, handlers } = useDeviceDrop((f) => void load(f));
  const inspectorOpen = useApp((s) => s.inspectorOpen);
  const toggleInspector = useApp((s) => s.toggleInspector);

  return (
    <div {...handlers} className="relative h-full w-full overflow-hidden bg-[#070a12]">
      <Scene />

      <div className="pointer-events-none absolute inset-0 p-4">
        <DeviceBadge onPick={() => fileRef.current?.click()} onClear={clear} problem={problem} />
        {!inspectorOpen && (
          <button
            type="button"
            onClick={toggleInspector}
            aria-label="Show the inspector"
            title="Show the inspector — view and parts"
            className="pointer-events-auto absolute right-4 top-4 rounded-md border border-ink-800 bg-ink-900/80 p-1.5 text-fg-muted backdrop-blur transition hover:border-ink-600 hover:text-fg"
          >
            <svg viewBox="0 0 16 16" width={14} height={14} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M13 8H3" />
              <path d="M7 4 3 8l4 4" />
            </svg>
          </button>
        )}
      </div>

      {dragging && (
        <div className="pointer-events-none absolute inset-3 flex items-center justify-center rounded-lg border border-dashed border-accent bg-accent/5">
          <span className="rounded-md bg-ink-950/80 px-3 py-1.5 text-[12px] text-fg">
            Drop to load — .blend is solved, .glb is drawn only
          </span>
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".blend,.glb,.gltf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void load(f);
        }}
      />
    </div>
  );
}
