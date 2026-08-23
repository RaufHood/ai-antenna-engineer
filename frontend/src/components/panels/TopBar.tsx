"use client";

import { KevinLockup } from "@/components/Logo";
import { useApp } from "@/lib/store";

/**
 * Orientation only: what device is loaded, what the run is doing right now,
 * and the one way back to a clean slate. Everything an engineer would act on
 * lives in the panel that owns it.
 */
export function TopBar() {
  const spec = useApp((s) => s.spec);
  const running = useApp((s) => s.running);
  const planning = useApp((s) => s.planning);
  const runId = useApp((s) => s.runId);
  const jobs = useApp((s) => s.jobs);
  const engine = useApp((s) => s.engine);
  const reset = useApp((s) => s.reset);

  const total = jobs.length;
  const done = jobs.filter((j) => j.status === "complete").length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const settled = done + failed;
  const [w, h, t] = spec.board.size_mm;
  // The catalogue name carries its own dimensions; they are shown once.
  const device = spec.name.replace(/\s*\([^)]*\)\s*$/, "");

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-800 px-4">
      <KevinLockup height={18} className="text-fg" />
      <span className="h-4 w-px bg-ink-700" aria-hidden />
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="truncate text-[12px] text-fg">{device}</span>
        <span className="shrink-0 font-mono text-[10px] text-fg-muted">
          {w} × {h} × {t} mm
        </span>
      </div>

      <div className="ml-auto flex items-center gap-3">
        {runId && (
          <div className="flex items-center gap-2.5 text-[11px]">
            <span
              aria-hidden
              className={`h-1.5 w-1.5 rounded-full ${
                running ? "animate-pulse bg-accent" : failed ? "bg-warn" : "bg-pass"
              }`}
            />
            {total === 0 ? (
              <span className="text-fg-muted">
                {planning || running ? "Planning placements" : "No simulations"}
              </span>
            ) : (
              <>
                <span className="font-mono text-fg-muted">
                  <span className="text-fg">{done}</span>/{total} solved
                </span>
                <span
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={total}
                  aria-valuenow={settled}
                  aria-label="Simulations finished"
                  className="h-[3px] w-16 overflow-hidden rounded-full bg-ink-700"
                >
                  <span
                    className="block h-full bg-accent transition-[width] duration-300"
                    style={{ width: `${(settled / total) * 100}%` }}
                  />
                </span>
                {failed > 0 && (
                  <span className="text-fail" title="Solves that returned no sweep">
                    {failed} failed
                  </span>
                )}
              </>
            )}
            {engine && (
              <span className="font-mono text-[10px] text-fg-muted" title="Solver engine">
                {engine}
              </span>
            )}
          </div>
        )}

        {runId && (
          <button
            type="button"
            onClick={reset}
            title={
              running
                ? "Clears this run from the workspace. The solve keeps running on the backend."
                : "Clears this run's candidates, results and report."
            }
            className="rounded-sm border border-ink-700 px-2.5 py-1 text-[11px] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg"
          >
            Clear run
          </button>
        )}
      </div>
    </header>
  );
}
