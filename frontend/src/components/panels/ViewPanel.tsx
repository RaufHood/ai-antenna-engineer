"use client";

import { useApp, type Layer } from "@/lib/store";
import { VIEW_PRESETS } from "@/components/viewer/Scene";
import { SectionTitle } from "./SpecPanel";

/**
 * Everything that changes how the device is drawn, in one place: the camera,
 * what is annotated on top of it, how far apart the stack is pulled, and —
 * once there are candidates — which of them are shown. None of this changes
 * the study; it only changes the picture, so it lives with the inspector
 * rather than floating over the canvas.
 */

const LAYERS: [Layer, string][] = [
  ["showPins", "Antennas"],
  ["showKeepouts", "Keep-out"],
  ["showLabels", "Labels"],
  ["showShaded", "Shaded"],
];

function Chip({
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
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-md border px-2.5 py-1 text-[12px] transition ${
        active
          ? "border-ink-600 bg-ink-800 text-fg"
          : "border-ink-800 text-fg-muted hover:border-ink-600 hover:text-fg"
      }`}
    >
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-3 flex items-start gap-3">
      <span className="w-14 shrink-0 pt-1 text-[11px] text-fg-muted">{label}</span>
      <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

export function ViewPanel() {
  const explode = useApp((s) => s.explode);
  const setExplode = useApp((s) => s.setExplode);
  const toggle = useApp((s) => s.toggle);
  const showPins = useApp((s) => s.showPins);
  const showKeepouts = useApp((s) => s.showKeepouts);
  const showLabels = useApp((s) => s.showLabels);
  const showShaded = useApp((s) => s.showShaded);
  const layers: Record<Layer, boolean> = { showPins, showKeepouts, showLabels, showShaded };
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const viewMode = useApp((s) => s.viewMode);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);
  const setViewMode = useApp((s) => s.setViewMode);
  const modelUrl = useApp((s) => s.modelUrl);
  const candidates = useApp((s) => s.candidates);

  return (
    <section className="border-t border-ink-800 px-4 pb-5 pt-5">
      <SectionTitle>View</SectionTitle>

      <Row label="Camera">
        {Object.keys(VIEW_PRESETS).map((k) => (
          <Chip
            key={k}
            onClick={() => window.dispatchEvent(new CustomEvent("view-preset", { detail: k }))}
          >
            {k}
          </Chip>
        ))}
      </Row>

      <Row label="Show">
        {LAYERS.map(([key, label]) => (
          <Chip key={key} active={layers[key]} onClick={() => toggle(key)}>
            {label}
          </Chip>
        ))}
      </Row>

      {/* Pulls the stack apart along its thinnest axis — the one view where
          you can see which layer the antenna is fighting. Hidden for an
          uploaded .glb: that path draws one shaded mesh, nothing to separate. */}
      {!modelUrl && (
        <div className="mt-3 flex items-center gap-3">
          <label htmlFor="explode" className="w-14 shrink-0 text-[11px] text-fg-muted">
            Explode
          </label>
          <input
            id="explode"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={explode}
            onChange={(e) => setExplode(parseFloat(e.target.value))}
            className="min-w-0 flex-1"
          />
          <span className="w-8 text-right font-mono text-[11px] text-fg-faint">
            {(explode * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {candidates.length > 0 && (
        <Row label="Antennas">
          <Chip active={viewMode === "system"} onClick={() => setViewMode("system")}>
            Chosen
          </Chip>
          <Chip active={viewMode === "focus"} onClick={() => setViewMode("focus")}>
            All for band
          </Chip>
          {viewMode === "focus" && (
            <select
              value={focusBand ?? ""}
              onChange={(e) => setFocusBand(e.target.value)}
              className="rounded-md border border-ink-800 bg-ink-900 px-2 py-1 text-[12px] text-fg outline-none"
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
        </Row>
      )}
    </section>
  );
}
