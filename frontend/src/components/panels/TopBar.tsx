"use client";

import { KevinLockup } from "@/components/Logo";
import { useApp } from "@/lib/store";

/**
 * Orientation only: the mark, how far the run has got, and the one way back
 * to a clean slate. The device has its card in the left rail; it is not
 * repeated here. Solve progress lives here and nowhere else.
 */
export function TopBar() {
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

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-800 px-4">
      <KevinLockup height={18} className="text-fg" />

      <div className="ml-auto flex items-center gap-4">
        {runId && (
          <div
            className="flex items-center gap-2.5 text-[11px]"
            title={engine ? `Solver: ${engine}` : undefined}
          >
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
            className="rounded-md border border-ink-700 px-2.5 py-1 text-[11px] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg"
          >
            Clear run
          </button>
        )}
      </div>
    </header>
  );
}
