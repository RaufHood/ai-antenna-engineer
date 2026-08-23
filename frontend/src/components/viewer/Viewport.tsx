"use client";

import dynamic from "next/dynamic";
import { useRef } from "react";
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

  return (
    <div {...handlers} className="relative h-full w-full overflow-hidden bg-[#070a12]">
      <Scene />

      <div className="pointer-events-none absolute inset-0 p-4">
        <DeviceBadge onPick={() => fileRef.current?.click()} onClear={clear} problem={problem} />
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
