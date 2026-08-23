"use client";

import { useRef, useState } from "react";
import { useApp } from "@/lib/store";

/**
 * The device, named where it is drawn. Sits in the corner of the viewport:
 * what is loaded, how big it is, which of the shipped devices it is, and one
 * quiet link to replace it with your own. Dropping
 * a file anywhere on the viewport does the same — `useDeviceDrop` wires the
 * handlers onto the viewport root so the whole canvas is the target.
 *
 * A .blend goes to the backend, is extracted there (~16 s cold, instant if
 * that exact file was seen before) and becomes the geometry the solver
 * meshes and the mesh the viewer draws. A .glb is drawn only, and the badge
 * says so.
 */

/** Strips the dimensions the catalogue repeats inside the device name. */
const bareName = (n: string) => n.replace(/\s*\([^)]*\)\s*$/, "").trim() || n;

export function useDeviceLoad() {
  const uploadBlend = useApp((s) => s.uploadBlend);
  const setModel = useApp((s) => s.setModel);
  const [problem, setProblem] = useState<string | null>(null);

  async function load(file: File) {
    const name = file.name.toLowerCase();
    if (name.endsWith(".blend")) {
      setProblem(null);
      await uploadBlend(file);
      const err = useApp.getState().error;
      if (err) setProblem(`${file.name} was not extracted — ${err}`);
      return;
    }
    if (name.endsWith(".glb") || name.endsWith(".gltf")) {
      const prev = useApp.getState().modelUrl;
      if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
      setModel(URL.createObjectURL(file), file.name);
      setProblem(null);
      return;
    }
    setProblem(`${file.name} is not a .blend or .glb.`);
  }

  function clear() {
    const prev = useApp.getState().modelUrl;
    if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
    setModel(null, null);
    setProblem(null);
  }

  return { load, clear, problem };
}

/** Drag-and-drop onto a whole element. Depth-counted so child enter/leave
 *  events do not flicker the state. */
export function useDeviceDrop(onFile: (f: File) => void) {
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  return {
    dragging,
    handlers: {
      onDragEnter: (e: React.DragEvent) => {
        e.preventDefault();
        depth.current += 1;
        setDragging(true);
      },
      onDragOver: (e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      },
      onDragLeave: () => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      },
      onDrop: (e: React.DragEvent) => {
        e.preventDefault();
        depth.current = 0;
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      },
    },
  };
}

function Spinner() {
  return (
    <svg viewBox="0 0 16 16" width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true" className="animate-spin">
      <circle cx="8" cy="8" r="5.25" className="opacity-25" />
      <path d="M8 2.75A5.25 5.25 0 0 1 13.25 8" strokeLinecap="round" />
    </svg>
  );
}

export function DeviceBadge({
  onPick,
  onClear,
  problem,
}: {
  onPick: () => void;
  onClear: () => void;
  problem: string | null;
}) {
  const spec = useApp((s) => s.spec);
  const deviceId = useApp((s) => s.deviceId);
  const modelUrl = useApp((s) => s.modelUrl);
  const modelName = useApp((s) => s.modelName);
  const uploading = useApp((s) => s.uploading);
  const builtins = useApp((s) => s.builtins);
  const builtinId = useApp((s) => s.builtinId);
  const selectBuiltin = useApp((s) => s.selectBuiltin);
  const running = useApp((s) => s.running);

  const [w, h, t] = spec.board.size_mm;
  const parts = spec.components.length;
  const extracted = deviceId !== null;
  const displayOnly = !!modelUrl && !extracted;

  return (
    <div className="pointer-events-auto max-w-[360px]">
      <div className="flex items-baseline gap-2">
        <span className="truncate text-[13px] font-medium text-fg">
          {extracted && modelName ? modelName : bareName(spec.name)}
        </span>
        {uploading ? (
          <span className="flex items-center gap-1.5 text-[11px] text-accent">
            <Spinner />
            Extracting…
          </span>
        ) : (
          <button
            type="button"
            onClick={onPick}
            title="Load a different build file — .blend is solved, .glb is drawn only. Or drop one anywhere here."
            className="shrink-0 text-[11px] text-fg-muted transition hover:text-fg"
          >
            Replace
          </button>
        )}
      </div>
      <p className="mt-0.5 font-mono text-[11px] text-fg-muted">
        {w} × {h} × {t} mm · {parts} parts
      </p>
      {/* Two objects ship with the app and they are genuinely different RF
          problems — a 147 mm phone with one battery against a 313 mm laptop
          with three and a metal lid — so switching is one click, next to the
          name of the thing being switched. Quiet text, like Replace: this is
          navigation, not the primary action. Hidden when an uploaded device is
          loaded, which is the engineer's own and outranks both, and when only
          one ships. */}
      {!extracted && !modelUrl && builtins.length > 1 && (
        <p className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-[11px]">
          {builtins.map((d, i) => {
            const on = d.id === builtinId;
            return (
              <span key={d.id} className="flex items-baseline gap-1.5">
                {i > 0 && <span className="text-fg-faint">·</span>}
                {on ? (
                  <span className="text-fg">{d.short}</span>
                ) : (
                  <button
                    type="button"
                    disabled={running || uploading}
                    title={d.blurb ?? d.name}
                    onClick={() => void selectBuiltin(d.id)}
                    className="text-fg-muted transition hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {d.short}
                  </button>
                )}
              </span>
            );
          })}
        </p>
      )}
      {displayOnly && (
        <p className="mt-1 flex items-center gap-2 text-[11px]">
          <span className="rounded px-1.5 py-px text-warn ring-1 ring-warn/30">display only</span>
          <span className="truncate text-fg-muted">{modelName} is drawn, not solved</span>
          <button type="button" onClick={onClear} className="shrink-0 text-fg-muted transition hover:text-fg">
            Remove
          </button>
        </p>
      )}
      {problem && (
        <p role="alert" className="mt-1 max-w-[40ch] text-[11px] leading-relaxed text-fail">
          {problem}
        </p>
      )}
    </div>
  );
}
