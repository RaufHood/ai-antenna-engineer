"use client";

import { useRef } from "react";
import { useApp } from "@/lib/store";

function NumberField({
  label,
  value,
  step = 1,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  suffix?: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[10px] text-slate-400">{label}</span>
      <span className="flex items-center gap-1">
        <input
          type="number"
          value={value}
          step={step}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="w-16 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-right font-mono text-[10px] text-slate-200 outline-none focus:border-sky-500"
        />
        {suffix && (
          <span className="w-8 font-mono text-[9px] text-slate-500">{suffix}</span>
        )}
      </span>
    </label>
  );
}

export function SpecPanel() {
  const spec = useApp((s) => s.spec);
  const enabled = useApp((s) => s.enabledBands);
  const toggleBand = useApp((s) => s.toggleBand);
  const updateBand = useApp((s) => s.updateBand);
  const updateSar = useApp((s) => s.updateSar);
  const updateBoard = useApp((s) => s.updateBoard);
  const focusBand = useApp((s) => s.focusBand);
  const setFocusBand = useApp((s) => s.setFocusBand);
  const setModel = useApp((s) => s.setModel);
  const modelName = useApp((s) => s.modelName);
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <section className="border-b border-slate-800 px-3 py-2">
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Device
        </h2>
        <div className="rounded-md border border-slate-800 bg-slate-900/60 p-2">
          <div className="text-xs text-slate-200">{spec.name}</div>
          <div className="mt-1 font-mono text-[10px] text-slate-500">
            {spec.device_id} - {spec.enclosure.frame} frame, {spec.enclosure.back} back
          </div>
          <div className="mt-2 space-y-0.5">
            <NumberField
              label="Board er"
              value={spec.board.epsilon_r}
              step={0.1}
              onChange={(v) => updateBoard({ epsilon_r: v })}
            />
            <NumberField
              label="Board tan-d"
              value={spec.board.loss_tangent}
              step={0.001}
              onChange={(v) => updateBoard({ loss_tangent: v })}
            />
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".glb,.gltf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) setModel(URL.createObjectURL(f), f.name);
            }}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={() => fileRef.current?.click()}
              className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-700"
            >
              Load Blender .glb
            </button>
            {modelName && (
              <button
                onClick={() => setModel(null, null)}
                className="text-[10px] text-slate-500 hover:text-sky-400"
              >
                clear
              </button>
            )}
          </div>
          {modelName && (
            <div className="mt-1 truncate font-mono text-[9px] text-emerald-400">
              {modelName}
            </div>
          )}
        </div>
      </section>

      <section className="border-b border-slate-800 px-3 py-2">
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Bands &amp; targets
        </h2>
        <div className="space-y-1.5">
          {spec.requirements.bands.map((b) => {
            const on = enabled.includes(b.id);
            const isFocus = focusBand === b.id;
            return (
              <div
                key={b.id}
                className={`rounded-md border p-2 transition ${
                  on ? "border-slate-700 bg-slate-900/70" : "border-slate-800 bg-slate-900/30 opacity-55"
                } ${isFocus ? "ring-1 ring-sky-500/60" : ""}`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggleBand(b.id)}
                    className="accent-sky-500"
                  />
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: b.color }}
                  />
                  <button
                    onClick={() => setFocusBand(isFocus ? null : b.id)}
                    className="truncate text-left text-xs text-slate-200 hover:text-sky-400"
                    title="focus this band in the viewer"
                  >
                    {b.name}
                  </button>
                  <span className="ml-auto font-mono text-[9px] text-slate-500">
                    {b.f_low_ghz}-{b.f_high_ghz}
                  </span>
                </div>
                {on && (
                  <div className="mt-1.5 space-y-0.5 border-t border-slate-800 pt-1.5">
                    <NumberField
                      label="Keep-out"
                      value={b.clearance_mm}
                      suffix="mm"
                      onChange={(v) => updateBand(b.id, { clearance_mm: v })}
                    />
                    <NumberField
                      label="S11 target"
                      value={b.s11_db_max}
                      suffix="dB"
                      onChange={(v) => updateBand(b.id, { s11_db_max: v })}
                    />
                    <NumberField
                      label="Min efficiency"
                      value={b.efficiency_min}
                      step={0.05}
                      onChange={(v) => updateBand(b.id, { efficiency_min: v })}
                    />
                    <div className="pt-0.5 font-mono text-[9px] text-slate-500">
                      types: {b.antenna_types.join(", ")}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="px-3 py-2">
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Regulatory
        </h2>
        <label className="flex items-center justify-between gap-2 py-0.5">
          <span className="text-[10px] text-slate-400">SAR standard</span>
          <select
            value={spec.requirements.sar_limit.standard}
            onChange={(e) => updateSar(e.target.value)}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-200 outline-none focus:border-sky-500"
          >
            <option value="FCC">FCC / ISED</option>
            <option value="ICNIRP">ICNIRP / CE</option>
          </select>
        </label>
        <div className="mt-1 font-mono text-[10px] text-slate-500">
          limit {spec.requirements.sar_limit.w_per_kg} W/kg over{" "}
          {spec.requirements.sar_limit.mass_g} g
        </div>
        <div className="mt-1 font-mono text-[10px] text-slate-500">
          VSWR &lt;= {spec.requirements.vswr_max} - isolation &lt;={" "}
          {spec.requirements.isolation_db_max} dB
        </div>
      </section>
    </>
  );
}
