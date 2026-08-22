"use client";

import { useApp } from "@/lib/store";

export function TopBar() {
  const spec = useApp((s) => s.spec);
  const enabled = useApp((s) => s.enabledBands);
  const toggleBand = useApp((s) => s.toggleBand);
  const running = useApp((s) => s.running);
  const jobs = useApp((s) => s.jobs);
  const reset = useApp((s) => s.reset);
  const done = jobs.filter((j) => j.status === "complete").length;

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-950 px-4">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tracking-tight text-slate-100">
          Antenna Placement Studio
        </span>
        <span className="font-mono text-[10px] text-slate-500">{spec.device_id}</span>
      </div>

      <div className="ml-4 flex items-center gap-1">
        {spec.requirements.bands.map((b) => {
          const on = enabled.includes(b.id);
          return (
            <button
              key={b.id}
              onClick={() => toggleBand(b.id)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] transition ${
                on
                  ? "border-slate-600 bg-slate-800 text-slate-100"
                  : "border-slate-800 text-slate-600 hover:text-slate-400"
              }`}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: on ? b.color : "#475569" }}
              />
              {b.name}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-3">
        {!!jobs.length && (
          <span className="font-mono text-[10px] text-slate-500">
            {done}/{jobs.length} simulations
            {running && <span className="ml-1 text-sky-400">running</span>}
          </span>
        )}
        <button
          onClick={reset}
          className="rounded-md border border-slate-700 px-2.5 py-1 text-[10px] text-slate-400 hover:border-slate-500 hover:text-slate-200"
        >
          Clear run
        </button>
      </div>
    </header>
  );
}
