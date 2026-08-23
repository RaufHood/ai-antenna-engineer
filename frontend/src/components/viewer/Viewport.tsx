"use client";

import dynamic from "next/dynamic";
import { useApp, type Layer } from "@/lib/store";
import { VIEW_PRESETS } from "./Scene";

const Scene = dynamic(() => import("./Scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] text-fg-faint">
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
      // Layer toggles are not the primary action — the accent belongs to
      // "Run study". Three saturated chips in the corner were the loudest
      // thing on screen and the least important.
      className={`rounded-md border px-2.5 py-1 text-[11px] transition ${
        active
          ? "border-ink-600 bg-ink-800 text-fg"
          : "border-transparent bg-ink-900/70 text-fg-muted hover:bg-ink-850 hover:text-fg"
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
                className="rounded-md bg-ink-850/80 px-2 py-1 text-[11px] text-fg outline-none"
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

        {/* Pulls the real 191-part stack apart along its thinnest axis, which
            is how a teardown lays a phone out — and the only view where you
            can see which layer the antenna is actually fighting. Hidden for an
            uploaded model: that path draws a shaded mesh, not per-part line
            art, so there is nothing to separate. */}
        {!modelUrl && (
          <div className="pointer-events-auto absolute bottom-3 left-3 flex w-56 items-center gap-3 rounded-md bg-ink-850/80 px-3 py-2 backdrop-blur">
            <span className="text-[11px] text-fg-muted">Explode</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={explode}
              onChange={(e) => setExplode(parseFloat(e.target.value))}
              className="min-w-0 flex-1"
            />
            <span className="w-8 text-right font-mono text-[10px] text-fg-faint">
              {(explode * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
