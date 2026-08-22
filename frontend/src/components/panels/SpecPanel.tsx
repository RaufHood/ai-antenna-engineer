"use client";

import { useRef } from "react";
import { useApp } from "@/lib/store";

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
      {children}
    </h2>
  );
}

/** Device card: what is loaded, and the one way to change it. */
function DeviceCard() {
  const spec = useApp((s) => s.spec);
  const setModel = useApp((s) => s.setModel);
  const modelName = useApp((s) => s.modelName);
  const uploadBlend = useApp((s) => s.uploadBlend);
  const uploading = useApp((s) => s.uploading);
  const deviceId = useApp((s) => s.deviceId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [w, h, t] = spec.board.size_mm;

  return (
    <section className="border-b border-slate-800/80 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <SectionTitle>Device</SectionTitle>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="text-[11px] text-sky-400 transition hover:text-sky-300 disabled:cursor-wait disabled:text-slate-500"
        >
          {uploading ? "Extracting…" : "Load .blend / .glb"}
        </button>
      </div>
      <div className="text-xs text-slate-200">{spec.name}</div>
      <div className="mt-0.5 font-mono text-[10px] text-slate-500">
        {w} × {h} × {t} mm · {spec.enclosure.frame} frame, {spec.enclosure.back} back ·{" "}
        {spec.components.length} parts
      </div>
      {modelName && (
        <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px]">
          <span className="truncate text-emerald-400">{modelName}</span>
          <span className="shrink-0 text-slate-600">
            {deviceId ? "solver geometry" : "display only"}
          </span>
          <button
            onClick={() => setModel(null, null)}
            className="ml-auto shrink-0 text-slate-500 hover:text-slate-300"
          >
            clear
          </button>
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
          if (!f) return;
          // .blend goes through the backend (extraction + classification);
          // a .glb is display-only and never reaches the solver.
          if (f.name.toLowerCase().endsWith(".blend")) void uploadBlend(f);
          else setModel(URL.createObjectURL(f), f.name);
        }}
      />
    </section>
  );
}

/** Band selection. Targets come from the backend's catalogue and are shown, not edited. */
function Bands() {
  const bands = useApp((s) => s.spec.requirements.bands);
  const enabled = useApp((s) => s.enabledBands);
  const toggleBand = useApp((s) => s.toggleBand);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);
  const running = useApp((s) => s.running);

  return (
    <section className="border-b border-slate-800/80 px-4 py-3">
      <div className="mb-2 flex items-baseline justify-between">
        <SectionTitle>Bands</SectionTitle>
        <span className="text-[10px] text-slate-600">
          {enabled.length} of {bands.length}
        </span>
      </div>
      <ul className="space-y-1">
        {bands.map((b) => {
          const on = enabled.includes(b.id);
          const isFocus = focusBand === b.id;
          return (
            <li
              key={b.id}
              className={`rounded-md border transition ${
                on ? "border-slate-800 bg-slate-900/50" : "border-transparent"
              } ${isFocus ? "ring-1 ring-sky-500/50" : ""}`}
            >
              <div className="flex items-center gap-2 px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={on}
                  disabled={running}
                  onChange={() => toggleBand(b.id)}
                  className="accent-sky-500"
                />
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: b.color }} />
                <button
                  onClick={() => on && setFocusBand(isFocus ? null : b.id)}
                  className={`truncate text-left text-xs ${
                    on ? "text-slate-200 hover:text-sky-300" : "text-slate-500"
                  }`}
                  title={on ? "focus this band in the viewer" : undefined}
                >
                  {b.name}
                </button>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-500">
                  {b.f_low_ghz}–{b.f_high_ghz}
                </span>
              </div>
              {on && (
                <dl className="grid grid-cols-3 gap-1 border-t border-slate-800/80 px-2 py-1.5 font-mono text-[10px]">
                  <div>
                    <dt className="text-slate-600">S11</dt>
                    <dd className="text-slate-300">≤ {b.s11_db_max} dB</dd>
                  </div>
                  <div>
                    <dt className="text-slate-600">efficiency</dt>
                    <dd className="text-slate-300">≥ {Math.round(b.efficiency_min * 100)}%</dd>
                  </div>
                  <div>
                    <dt className="text-slate-600">clearance</dt>
                    <dd className="text-slate-300">≥ {b.clearance_mm} mm</dd>
                  </div>
                </dl>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function SpecPanel() {
  return (
    <>
      <DeviceCard />
      <Bands />
    </>
  );
}
