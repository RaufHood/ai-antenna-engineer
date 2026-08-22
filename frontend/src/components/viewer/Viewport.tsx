"use client";

import dynamic from "next/dynamic";
import { useApp, type Layer } from "@/lib/store";
import { VIEW_PRESETS } from "./Scene";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] text-slate-600">
      loading 3D viewer…
    </div>
  ),
});

const LAYERS: [Layer, string][] = [
  ["showPins", "Antennas"],
  ["showKeepouts", "Keep-out"],
  ["showLabels", "Labels"],
];

function HudButton({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-[11px] transition ${
        active
          ? "bg-slate-100 text-slate-900"
          : "bg-slate-900/70 text-slate-300 hover:bg-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

export function Viewport() {
  const explode = useApp((s) => s.explode);
  const setExplode = useApp((s) => s.setExplode);
  const toggle = useApp((s) => s.toggle);
  const showPins = useApp((s) => s.showPins);
  const showKeepouts = useApp((s) => s.showKeepouts);
  const showLabels = useApp((s) => s.showLabels);
  const layers: Record<Layer, boolean> = { showPins, showKeepouts, showLabels };
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const viewMode = useApp((s) => s.viewMode);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);
  const setViewMode = useApp((s) => s.setViewMode);
  const modelUrl = useApp((s) => s.modelUrl);
  const candidates = useApp((s) => s.candidates);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#070a12]">
      <Scene />

      <div className="pointer-events-none absolute inset-0 p-3">
        {/* camera presets */}
        <div className="pointer-events-auto flex items-center gap-1">
          {Object.keys(VIEW_PRESETS).map((k) => (
            <HudButton
              key={k}
              onClick={() => window.dispatchEvent(new CustomEvent("view-preset", { detail: k }))}
            >
              {k}
            </HudButton>
          ))}
        </div>

        {/* what to draw */}
        <div className="pointer-events-auto absolute right-3 top-3 flex flex-col items-end gap-1">
          {LAYERS.map(([key, label]) => (
            <HudButton key={key} active={layers[key]} onClick={() => toggle(key)}>
              {label}
            </HudButton>
          ))}
        </div>

        {/* which candidates: the chosen set, or every candidate for one band */}
        {candidates.length > 0 && (
          <div className="pointer-events-auto absolute bottom-3 right-3 flex items-center gap-1">
            <HudButton active={viewMode === "system"} onClick={() => setViewMode("system")}>
              Chosen
            </HudButton>
            <HudButton active={viewMode === "focus"} onClick={() => setViewMode("focus")}>
              All for band
            </HudButton>
            {viewMode === "focus" && (
              <select
                value={focusBand ?? ""}
                onChange={(e) => setFocusBand(e.target.value)}
                className="rounded-md bg-slate-900/70 px-2 py-1 text-[11px] text-slate-200 outline-none"
              >
                {bands
                  .filter((b) => enabled.includes(b.id))
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
              </select>
            )}
          </div>
        )}

        {/* exploded view only makes sense for the procedural handset */}
        {!modelUrl && (
          <div className="pointer-events-auto absolute bottom-3 left-3 flex w-56 items-center gap-3 rounded-md bg-slate-900/70 px-3 py-2 backdrop-blur">
            <span className="text-[11px] text-slate-400">Explode</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={explode}
              onChange={(e) => setExplode(parseFloat(e.target.value))}
              className="min-w-0 flex-1"
            />
            <span className="w-8 text-right font-mono text-[10px] text-slate-500">
              {(explode * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
