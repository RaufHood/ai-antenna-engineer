"use client";

import dynamic from "next/dynamic";
import { H, T, W } from "@/lib/device";
import { useApp } from "@/lib/store";
import { VIEW_PRESETS } from "./Scene";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      loading 3D viewer...
    </div>
  ),
});

const LAYERS = [
  ["showKeepouts", "Keep-out"],
  ["showHeatmap", "Heatmap"],
  ["showPins", "Antennas"],
  ["showIsolation", "Isolation"],
  ["showLabels", "Labels"],
  ["showGrid", "Grid"],
] as const;

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
      className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
        active
          ? "bg-sky-500/90 text-white shadow"
          : "bg-slate-800/70 text-slate-300 hover:bg-slate-700/80"
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
  const layers: Record<(typeof LAYERS)[number][0], boolean> = {
    showKeepouts: useApp((s) => s.showKeepouts),
    showHeatmap: useApp((s) => s.showHeatmap),
    showPins: useApp((s) => s.showPins),
    showIsolation: useApp((s) => s.showIsolation),
    showLabels: useApp((s) => s.showLabels),
    showGrid: useApp((s) => s.showGrid),
  };
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const viewMode = useApp((s) => s.viewMode);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#070a12]">
      <Scene />

      <div className="pointer-events-none absolute inset-0 p-3">
        <div className="pointer-events-auto flex flex-wrap items-center gap-1.5">
          {Object.keys(VIEW_PRESETS).map((k) => (
            <HudButton
              key={k}
              onClick={() =>
                window.dispatchEvent(new CustomEvent("view-preset", { detail: k }))
              }
            >
              {k}
            </HudButton>
          ))}
          <div className="mx-1 h-4 w-px bg-slate-700" />
          <HudButton
            active={viewMode === "system"}
            onClick={() => useApp.getState().setViewMode("system")}
          >
            System view
          </HudButton>
          <HudButton
            active={viewMode === "focus"}
            onClick={() => useApp.getState().setViewMode("focus")}
          >
            Focus band
          </HudButton>
          {viewMode === "focus" && (
            <select
              value={focusBand ?? ""}
              onChange={(e) => setFocusBand(e.target.value)}
              className="rounded-md bg-slate-800/80 px-2 py-1 text-[11px] text-slate-200 outline-none"
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

        <div className="pointer-events-auto absolute right-3 top-3 flex flex-col items-end gap-1.5">
          {LAYERS.map(([key, label]) => (
            <HudButton
              key={key}
              active={layers[key]}
              onClick={() => toggle(key)}
            >
              {label}
            </HudButton>
          ))}
        </div>

        <div className="pointer-events-auto absolute bottom-3 left-3 w-64 rounded-lg border border-slate-800 bg-slate-950/80 p-3 backdrop-blur">
          <div className="mb-1.5 flex items-center justify-between text-[11px] text-slate-400">
            <span>Exploded view</span>
            <span className="font-mono text-slate-500">
              {(explode * 100).toFixed(0)}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={explode}
            onChange={(e) => setExplode(parseFloat(e.target.value))}
            className="w-full accent-sky-500"
          />
          <div className="mt-2 font-mono text-[10px] text-slate-600">
            {W} x {H} x {T} mm - origin at bottom-left-back
          </div>
        </div>

        <div className="pointer-events-none absolute bottom-3 right-3 rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-[10px] backdrop-blur">
          <div className="mb-1 text-slate-400">Bands</div>
          {bands
            .filter((b) => enabled.includes(b.id))
            .map((b) => (
              <div key={b.id} className="flex items-center gap-2 py-0.5">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: b.color }}
                />
                <span className="text-slate-300">{b.name}</span>
                <span className="ml-auto font-mono text-slate-500">
                  {b.f_low_ghz}-{b.f_high_ghz} GHz
                </span>
              </div>
            ))}
          {layers.showHeatmap && (
            <div className="mt-2 border-t border-slate-800 pt-2">
              <div className="mb-1 text-slate-400">Placement score</div>
              <div className="h-1.5 w-40 rounded bg-gradient-to-r from-red-600 via-amber-500 to-green-500" />
              <div className="mt-0.5 flex justify-between text-slate-600">
                <span>poor</span>
                <span>good</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
