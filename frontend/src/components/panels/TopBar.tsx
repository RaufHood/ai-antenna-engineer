"use client";

import { KevinLockup } from "@/components/Logo";
import { useApp } from "@/lib/store";

export function TopBar() {
  const spec = useApp((s) => s.spec);
  const running = useApp((s) => s.running);
  const runId = useApp((s) => s.runId);
  const jobs = useApp((s) => s.jobs);
  const engine = useApp((s) => s.engine);
  const reset = useApp((s) => s.reset);
  const done = jobs.filter((j) => j.status === "complete").length;

  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-slate-800/80 px-4">
      <div className="flex items-center gap-3">
        <KevinLockup height={20} className="text-slate-100" />
        <span className="hidden text-[11px] text-slate-500 sm:inline">AI antenna engineer</span>
      </div>

      <div className="ml-auto flex items-center gap-3 text-[11px]">
        <span className="font-mono text-slate-500">{spec.name}</span>
        {runId && (
          <span className="flex items-center gap-2 rounded-full border border-slate-800 px-2.5 py-1 font-mono text-[10px] text-slate-400">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                running ? "animate-pulse bg-sky-400" : "bg-emerald-400"
              }`}
            />
            {done}/{jobs.length} sims
            {engine && <span className="text-slate-600">· {engine}</span>}
          </span>
        )}
        {runId && (
          <button
            onClick={reset}
            className="rounded-md border border-slate-800 px-2.5 py-1 text-slate-400 transition hover:border-slate-600 hover:text-slate-200"
          >
            Clear
          </button>
        )}
      </div>
    </header>
  );
}
